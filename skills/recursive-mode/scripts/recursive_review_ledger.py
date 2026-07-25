#!/usr/bin/env python3
"""Single-source parser and validator for Recursive Review ledgers."""

from __future__ import annotations

import argparse
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import recursive_phase_rules as phase_rules
import recursive_review_surface as review_surface


TOP_LEVEL_SECTIONS = ["Review Scope", "Findings", "Verdict"]
SCOPE_FIELDS = [
    "Review ID", "Pass", "Ledger Path", "Previous Pass", "Previous Pass Hash",
    "Reviewed Artifact", "Artifact Hash", "Diff Basis", "Changed Files", "Evidence Basis",
]
VERDICT_FIELDS = [
    "Result", "Open Findings", "Pending Scheduled Handoffs", "Controller", "Verified Pass", "Verified Pass Hash",
]
BASE_FINDING_FIELDS = [
    "Discovered in pass", "Kind", "Location", "Observed", "Expected", "Contract", "Technical impact",
    "Required outcome", "Verification", "Depends on", "Disposition", "Claimed outcome", "Claimed changes",
    "Claimed verification", "Controller verification",
]
IMMUTABLE_FINDING_FIELDS = [
    "Discovered in pass", "Kind", "Kind justification", "Location", "Observed", "Expected", "Contract",
    "Technical impact", "Required outcome", "Verification", "Depends on",
]
KINDS = {"contract-violation", "missing-evidence", "plan-drift", "test-gap", "security", "contract-ambiguity", "other"}
DISPOSITIONS = {"open", "fixed", "rejected", "scheduled", "deferred", "out-of-scope"}
CLAIMED_OUTCOMES = {"none", "fixed", "blocked"}
HANDOFF_FIELDS = [
    "Source Ledger", "Finding ID", "Kind", "Location", "Observed", "Expected", "Contract",
    "Technical impact", "Required outcome", "Verification", "Owner phase", "Scheduling basis", "Status",
    "Consumed in", "Controller verification",
]
FIELD_RE = re.compile(r"(?m)^- ([A-Za-z][A-Za-z0-9 /-]*):[ \t]*(.*?)\s*$")
FINDING_HEADING_RE = re.compile(r"(?m)^### (F-[0-9]{3,})\s*$")
HASH_RE = re.compile(r"^[a-f0-9]{64}$")
ID_RE = re.compile(r"^F-[0-9]{3,}$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
VERIFIED_HASH_LINE_RE = re.compile(r"(?m)^- Verified Pass Hash:.*(?:\n|$)")
AUDIT_PAYLOAD_PROFILE = "recursive-review-audit-payload-v1"
REVIEW_METADATA_FIELDS = [
    "Review ID",
    "Review Ledger Path",
    "Latest Verified Pass",
    "Latest Verified Pass Hash",
    "Review Bundle Path",
    "Review Bundle Hash",
]
BUNDLE_HEADER_FIELDS = [
    "Run",
    "Phase",
    "Phase Key",
    "Review ID",
    "Pass",
    "Role",
    "Bundle Path",
    "Artifact Path",
    "Artifact Content Hash",
    "Audit Payload Hash",
    "Audit Payload Profile",
    "Review Ledger Path",
    "GeneratedAt",
]


class ValidationResult:
    def __init__(self, issues: list[str] | None = None, *, ledger_path: Path | None = None, document=None) -> None:
        self.issues = sorted(set(issues or []))
        self.ledger_path = ledger_path
        self.document = document

    @property
    def valid(self) -> bool:
        return not self.issues


class ReviewDocument:
    def __init__(self, content: str, scope: dict[str, str], findings: dict[str, dict[str, str]], verdict: dict[str, str]) -> None:
        self.content = content
        self.scope = scope
        self.findings = findings
        self.verdict = verdict


@dataclass(frozen=True)
class LedgerContext:
    standalone: bool
    run_dir: Path | None
    phase_key: str | None
    artifact_file: str | None
    review_id: str | None


def trim_value(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "`\"'":
        return value[1:-1].strip()
    return value


def normalized_snapshot_hash(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = VERIFIED_HASH_LINE_RE.sub("", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fence_transition(line: str, active: tuple[str, int] | None) -> tuple[str, int] | None:
    """Return the next CommonMark-style fenced-code state for one line."""
    body = line.rstrip("\r\n")
    if active is not None:
        marker, minimum = active
        closing = re.fullmatch(rf"[ ]{{0,3}}{re.escape(marker)}{{{minimum},}}[ \t]*", body)
        return None if closing else active
    opening = re.match(r"^[ ]{0,3}(`{3,}|~{3,})(.*)$", body)
    if opening is None:
        return None
    run = opening.group(1)
    if run[0] == "`" and "`" in opening.group(2):
        return None
    return run[0], len(run)


def is_indented_code_line(line: str) -> bool:
    """Return True when leading whitespace reaches a CommonMark four-column code indent."""
    column = 0
    for character in line.rstrip("\r\n"):
        if character == " ":
            column += 1
        elif character == "\t":
            column = ((column // 4) + 1) * 4
        else:
            break
    return column >= 4


def markdown_h2_sections(content: str) -> list[tuple[str, str]]:
    """Extract real level-two Markdown sections while ignoring fenced examples."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    sections: list[tuple[str, str]] = []
    current_name: str | None = None
    current_body: list[str] = []
    fence: tuple[str, int] | None = None
    for line in normalized.splitlines(keepends=True):
        before = fence
        fence = fence_transition(line, fence)
        if before is not None or fence is not None:
            if current_name is not None:
                current_body.append(line)
            continue
        heading = re.match(r"^## ([^\n]+?)\s*(?:\n)?$", line)
        if heading:
            if current_name is not None:
                sections.append((current_name, "".join(current_body)))
            current_name = heading.group(1).strip()
            current_body = []
        elif current_name is not None:
            current_body.append(line)
    if current_name is not None:
        sections.append((current_name, "".join(current_body)))
    return sections


def normalize_audit_payload(content: str) -> str:
    """Normalize author-owned audit payload while neutralizing controller control values."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    lines = normalized.splitlines(keepends=True)
    section = "header"
    review_metadata_occurrences = 0
    fence: tuple[str, int] | None = None
    output: list[str] = []
    for line in lines:
        before = fence
        fence = fence_transition(line, fence)
        if before is not None or fence is not None:
            output.append(line)
            continue
        if is_indented_code_line(line):
            output.append(line)
            continue
        heading = re.match(r"^## ([^\n]+?)\s*(?:\n)?$", line)
        if heading:
            section = heading.group(1).strip()
            if section == "Review Metadata":
                review_metadata_occurrences += 1
            output.append(line)
            continue
        candidate_fields: tuple[str, ...] = ()
        if section == "header":
            candidate_fields = ("Status", "LockedAt", "LockHash")
        elif section == "Review Metadata" and review_metadata_occurrences == 1:
            candidate_fields = tuple(REVIEW_METADATA_FIELDS)
        replaced = line
        if section == "header":
            for field in candidate_fields:
                if re.fullmatch(rf"[ \t]*(?:[-*][ \t]+)?{re.escape(field)}:[^\n]*(?:\n)?", replaced):
                    replaced = ""
                    break
        else:
            for field in candidate_fields:
                replaced = re.sub(
                    rf"^(?P<prefix>[ \t]*(?:[-*][ \t]+)?){re.escape(field)}:[^\n]*(?P<newline>\n?)$",
                    rf"\g<prefix>{field}:\g<newline>",
                    replaced,
                )
        for gate in ("Audit", "Coverage", "Approval"):
            replaced = re.sub(
                rf"^(?P<prefix>[ \t]*(?:[-*][ \t]+)?){gate}:[ \t]*(?:PASS|FAIL)[ \t]*(?P<newline>\n?)$",
                rf"\g<prefix>{gate}:\g<newline>",
                replaced,
            )
        output.append(replaced)
    return "".join(output)


def audit_payload_hash(content: str) -> str:
    return hashlib.sha256(normalize_audit_payload(content).encode("utf-8")).hexdigest()


def canonical_bundle_display(run_dir: Path, phase_key: str, review_id: str, pass_id: str) -> str:
    return f"/.recursive/run/{run_dir.name}/evidence/review-bundles/{phase_key}/{review_id}/{pass_id}.md"


def repo_path(repo_root: Path, raw: str) -> Path:
    normalized = trim_value(raw).replace("\\", "/").lstrip("/")
    return repo_root / normalized


def canonical_display(repo_root: Path, path: Path) -> str:
    try:
        return f"/{path.resolve().relative_to(repo_root.resolve()).as_posix()}"
    except ValueError:
        return str(path.resolve())


def section_body(content: str, heading: str, level: int = 2) -> str:
    marks = "#" * level
    match = re.search(rf"(?ms)^{marks} {re.escape(heading)}\s*$\n?(.*?)(?=^{'#' * level} |\Z)", content)
    return match.group(1).strip() if match else ""


def parse_fields(body: str) -> tuple[dict[str, str], list[str], list[str]]:
    fields: dict[str, str] = {}
    order: list[str] = []
    duplicates: list[str] = []
    for match in FIELD_RE.finditer(body):
        name, raw = match.groups()
        if name in fields:
            duplicates.append(name)
        else:
            order.append(name)
        fields[name] = trim_value(raw)
    return fields, order, duplicates


def residual_schema_lines(body: str, *, allow_nested_lists: bool = False) -> list[str]:
    residual: list[str] = []
    list_owner = ""
    for line in body.splitlines():
        if not line.strip():
            continue
        field_match = FIELD_RE.fullmatch(line)
        if field_match:
            list_owner = field_match.group(1) if field_match.group(1) in {"Changed Files", "Evidence Basis"} else ""
            continue
        if allow_nested_lists and list_owner and re.fullmatch(r"  - .+", line):
            continue
        residual.append(line)
    return residual


def parse_id_list(value: str) -> list[str]:
    value = trim_value(value)
    if value.lower() == "none":
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def list_values(body: str, field_name: str) -> list[str]:
    match = re.search(
        rf"(?m)^- {re.escape(field_name)}:\s*$\n(?P<items>(?:  - .*\n?)*)",
        body,
    )
    if not match:
        return []
    return [trim_value(line[4:].strip()) for line in match.group("items").splitlines() if line.startswith("  - ")]


def parse_document(content: str) -> tuple[ReviewDocument | None, list[str]]:
    issues: list[str] = []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    if "```" in normalized:
        issues.append("code fences are not valid inside the machine-readable ledger")
    headings = re.findall(r"(?m)^## (.+?)\s*$", normalized)
    if headings != TOP_LEVEL_SECTIONS:
        issues.append(f"top-level sections must be exactly: {', '.join(TOP_LEVEL_SECTIONS)}")
    scope_body = section_body(normalized, "Review Scope")
    findings_body = section_body(normalized, "Findings")
    verdict_body = section_body(normalized, "Verdict")
    if not all((scope_body, findings_body, verdict_body)):
        return None, issues + ["Review Scope, Findings, and Verdict must all be non-empty"]

    scope, scope_order, duplicates = parse_fields(scope_body)
    if residual_schema_lines(scope_body, allow_nested_lists=True):
        issues.append("Review Scope contains content outside its exact field/list schema")
    if duplicates:
        issues.append(f"Review Scope has duplicate field(s): {', '.join(sorted(set(duplicates)))}")
    if scope_order != SCOPE_FIELDS:
        issues.append("Review Scope fields do not match the exact schema/order")
    for field in SCOPE_FIELDS:
        if field not in {"Changed Files", "Evidence Basis"} and not scope.get(field):
            issues.append(f"Review Scope field is empty: {field}")
    changed_files = list_values(scope_body, "Changed Files")
    evidence = list_values(scope_body, "Evidence Basis")
    if not changed_files:
        issues.append("Changed Files must contain a nested list")
    if not evidence:
        issues.append("Evidence Basis must contain a nested list")
    scope["Changed Files items"] = "\n".join(changed_files)
    scope["Evidence Basis items"] = "\n".join(evidence)

    findings: dict[str, dict[str, str]] = {}
    finding_matches = list(FINDING_HEADING_RE.finditer(findings_body))
    if not finding_matches:
        if findings_body.strip() != "- none":
            issues.append("Findings must contain stable F-* records or exactly '- none'")
    else:
        prefix = findings_body[: finding_matches[0].start()].strip()
        if prefix:
            issues.append("finding-bearing prose is not allowed outside F-* records")
        for index, match in enumerate(finding_matches):
            finding_id = match.group(1)
            end = finding_matches[index + 1].start() if index + 1 < len(finding_matches) else len(findings_body)
            body = findings_body[match.end():end].strip()
            fields, order, field_duplicates = parse_fields(body)
            if residual_schema_lines(body):
                issues.append(f"{finding_id} contains content outside its exact field schema")
            if finding_id in findings:
                issues.append(f"duplicate finding ID: {finding_id}")
            findings[finding_id] = fields
            if field_duplicates:
                issues.append(f"{finding_id} has duplicate field(s): {', '.join(sorted(set(field_duplicates)))}")
            expected = list(BASE_FINDING_FIELDS)
            if fields.get("Kind") == "other":
                expected.insert(2, "Kind justification")
            disposition = fields.get("Disposition", "")
            extras: list[str] = []
            if disposition == "rejected":
                extras = ["Disposition rationale"]
            elif disposition == "scheduled":
                extras = ["Owner phase", "Scheduling basis", "Destination"]
            elif disposition == "deferred":
                extras = ["Disposition rationale", "Owner", "Human approval", "Destination"]
            elif disposition == "out-of-scope":
                extras = ["Disposition rationale", "Human decision", "Destination"]
            insert_at = expected.index("Claimed outcome")
            expected[insert_at:insert_at] = extras
            if order != expected:
                issues.append(f"{finding_id} fields do not match the exact schema/order for disposition {disposition or 'missing'}")
            for field in expected:
                if not fields.get(field):
                    issues.append(f"{finding_id} field is empty: {field}")

    verdict, verdict_order, duplicates = parse_fields(verdict_body)
    if residual_schema_lines(verdict_body):
        issues.append("Verdict contains content outside its exact field schema")
    if duplicates:
        issues.append(f"Verdict has duplicate field(s): {', '.join(sorted(set(duplicates)))}")
    if verdict_order != VERDICT_FIELDS:
        issues.append("Verdict fields do not match the exact schema/order")
    for field in VERDICT_FIELDS:
        if not verdict.get(field):
            issues.append(f"Verdict field is empty: {field}")
    return ReviewDocument(normalized, scope, findings, verdict), issues


def validate_finding_states(document: ReviewDocument, *, standalone: bool) -> list[str]:
    issues: list[str] = []
    ids = list(document.findings)
    numeric_ids = [int(value.split("-", 1)[1]) for value in ids]
    if numeric_ids != list(range(1, len(ids) + 1)):
        issues.append("finding IDs must be append-only, ordered, and consecutive from F-001")
    graph: dict[str, list[str]] = {}
    for finding_id, finding in document.findings.items():
        kind = finding.get("Kind", "")
        disposition = finding.get("Disposition", "")
        claimed = finding.get("Claimed outcome", "")
        changes = finding.get("Claimed changes", "")
        verification = finding.get("Claimed verification", "")
        controller = finding.get("Controller verification", "")
        if kind not in KINDS:
            issues.append(f"{finding_id} has illegal Kind: {kind}")
        if kind == "other" and not finding.get("Kind justification"):
            issues.append(f"{finding_id} Kind other requires Kind justification")
        if disposition not in DISPOSITIONS:
            issues.append(f"{finding_id} has illegal Disposition: {disposition}")
        if claimed not in CLAIMED_OUTCOMES:
            issues.append(f"{finding_id} has illegal Claimed outcome: {claimed}")
        if disposition == "open":
            if controller != "none":
                issues.append(f"{finding_id} open disposition requires Controller verification: none")
            if claimed == "none" and (changes != "none" or verification != "none"):
                issues.append(f"{finding_id} claim none cannot cite changes or verification")
            if claimed == "fixed" and (changes == "none" or verification == "none"):
                issues.append(f"{finding_id} claimed fixed requires changes and verification")
            if claimed == "blocked" and verification == "none":
                issues.append(f"{finding_id} claimed blocked requires blocking verification")
        else:
            if controller in {"", "none"}:
                issues.append(f"{finding_id} terminal disposition requires controller evidence")
            if disposition == "fixed" and (claimed != "fixed" or changes == "none" or verification == "none"):
                issues.append(f"{finding_id} fixed disposition requires a complete fixed claim")
            if disposition != "fixed" and claimed != "none":
                issues.append(f"{finding_id} {disposition} disposition requires Claimed outcome: none")
        if disposition in {"rejected", "deferred", "out-of-scope"} and not finding.get("Disposition rationale"):
            issues.append(f"{finding_id} {disposition} requires Disposition rationale")
        if disposition == "deferred" and not all(finding.get(field) for field in ("Owner", "Human approval", "Destination")):
            issues.append(f"{finding_id} deferred requires owner, human approval, and destination")
        if disposition == "out-of-scope" and not all(finding.get(field) for field in ("Human decision", "Destination")):
            issues.append(f"{finding_id} out-of-scope requires human decision and destination")
        if disposition == "scheduled" and standalone:
            issues.append(f"{finding_id} standalone review cannot use scheduled disposition")
        dependencies = parse_id_list(finding.get("Depends on", "none"))
        graph[finding_id] = dependencies
        for dependency in dependencies:
            if dependency not in document.findings:
                issues.append(f"{finding_id} Depends on missing finding {dependency}")
            if dependency == finding_id:
                issues.append(f"{finding_id} Depends on itself")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> None:
        if node in visiting:
            issues.append(f"Depends on cycle includes {node}")
            return
        if node in visited:
            return
        visiting.add(node)
        for target in graph.get(node, []):
            if target in graph:
                visit(target)
        visiting.remove(node)
        visited.add(node)

    for finding_id in graph:
        visit(finding_id)
    return issues


def parse_handoff(path: Path, record_key: str) -> tuple[dict[str, str] | None, list[str]]:
    issues: list[str] = []
    if not path.is_file():
        return None, [f"scheduled handoff does not exist: {path}"]
    content = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    if not content.startswith("# Scheduled Finding Handoff Inventory\n"):
        issues.append(f"scheduled handoff has invalid title: {path}")
    headings = re.findall(r"(?m)^## (.+?)\s*$", content)
    first_heading = re.search(r"(?m)^## .+?\s*$", content)
    prefix_end = first_heading.start() if first_heading else len(content)
    prefix = content[len("# Scheduled Finding Handoff Inventory\n"):prefix_end].strip()
    if prefix:
        issues.append(f"scheduled handoff contains content outside record schema: {path}")
    if len(headings) != len(set(headings)):
        issues.append(f"scheduled handoff inventory has duplicate record headings: {path}")
    if record_key not in headings:
        return None, issues + [f"scheduled handoff inventory is missing record {record_key}: {path}"]
    fields, order, duplicates = parse_fields(section_body(content, record_key))
    if residual_schema_lines(section_body(content, record_key)):
        issues.append(f"scheduled handoff contains content outside its exact field schema: {path}")
    if duplicates or order != HANDOFF_FIELDS:
        issues.append(f"scheduled handoff fields do not match exact schema/order: {path}")
    return fields, issues


def validate_scheduled_finding(
    repo_root: Path,
    run_dir: Path,
    ledger_path: Path,
    source_artifact: str,
    review_id: str,
    finding_id: str,
    finding: dict[str, str],
) -> tuple[list[str], str]:
    issues: list[str] = []
    owner = finding.get("Owner phase", "")
    basis = finding.get("Scheduling basis", "")
    destination = finding.get("Destination", "")
    source_index = phase_rules.phase_index(source_artifact)
    later = phase_rules.PHASE_SEQUENCE[source_index + 1:]
    if owner not in later:
        issues.append(f"{finding_id} scheduled Owner phase must be a later canonical phase")
    if ".recursive/RECURSIVE.md" not in basis:
        issues.append(f"{finding_id} Scheduling basis must cite /.recursive/RECURSIVE.md ownership")
    owner_phase_key = phase_rules.audited_phase_key(owner) if owner else None
    expected = f"/.recursive/run/{run_dir.name}/evidence/reviews/scheduled/{owner_phase_key or 'missing'}/inventory.md"
    if destination != expected:
        issues.append(f"{finding_id} scheduled Destination must be {expected}")
    handoff_path = repo_path(repo_root, destination)
    try:
        handoff_path.resolve().relative_to(run_dir.resolve())
    except ValueError:
        issues.append(f"{finding_id} scheduled inventory must stay inside the active run")
    fields, handoff_issues = parse_handoff(handoff_path, f"{review_id}/{finding_id}")
    issues.extend(handoff_issues)
    if fields is None:
        return issues, "pending"
    expected_values = {
        "Source Ledger": canonical_display(repo_root, ledger_path), "Finding ID": finding_id,
        "Kind": finding.get("Kind", ""), "Location": finding.get("Location", ""), "Observed": finding.get("Observed", ""),
        "Expected": finding.get("Expected", ""), "Contract": finding.get("Contract", ""),
        "Technical impact": finding.get("Technical impact", ""), "Required outcome": finding.get("Required outcome", ""),
        "Verification": finding.get("Verification", ""), "Owner phase": owner, "Scheduling basis": basis,
    }
    for field, expected_value in expected_values.items():
        if fields.get(field) != trim_value(expected_value):
            issues.append(f"{finding_id} scheduled handoff {field} does not match source finding")
    status = fields.get("Status", "")
    if status not in {"pending", "consumed"}:
        issues.append(f"{finding_id} scheduled handoff Status must be pending|consumed")
    consumed_in = fields.get("Consumed in", "")
    controller = fields.get("Controller verification", "")
    if status == "pending" and (consumed_in != "none" or controller != "none"):
        issues.append(f"{finding_id} pending handoff must have no consumption evidence")
    if status == "consumed":
        expected_consumed = f"/.recursive/run/{run_dir.name}/{owner}"
        if consumed_in != expected_consumed or controller in {"", "none"}:
            issues.append(f"{finding_id} consumed handoff requires target artifact and controller evidence")
    return issues, status or "pending"


def validate_bundle_scope(
    repo_root: Path,
    run_dir: Path,
    phase_key: str,
    artifact_file: str,
    review_id: str,
    pass_id: str,
    ledger_path: Path,
    document: ReviewDocument,
    *,
    current_surface: bool,
) -> list[str]:
    issues: list[str] = []
    expected_bundle = canonical_bundle_display(run_dir, phase_key, review_id, pass_id)
    if document.scope.get("Reviewed Artifact") != expected_bundle:
        issues.append(f"Reviewed Artifact must be canonical immutable bundle {expected_bundle}")
        return issues
    bundle_path = repo_path(repo_root, expected_bundle)
    bundle_root = run_dir / "evidence/review-bundles"
    relative_parts = ("evidence", "review-bundles", phase_key, review_id, f"{pass_id}.md")
    cursor = run_dir
    symlinked_component = False
    for part in relative_parts:
        cursor = cursor / part
        symlinked_component = symlinked_component or cursor.is_symlink()
    if symlinked_component:
        issues.append(f"immutable review bundle must be a regular non-symlink file: {expected_bundle}")
        return issues
    if not bundle_path.is_file():
        issues.append(f"immutable review bundle does not exist: {expected_bundle}")
        return issues
    try:
        resolved_bundle = bundle_path.resolve(strict=True)
        resolved_bundle.relative_to(run_dir.resolve(strict=True))
        expected_parent = (bundle_root / phase_key / review_id).resolve(strict=True)
        if resolved_bundle.parent != expected_parent:
            raise ValueError("bundle resolved outside its canonical phase/review directory")
    except (FileNotFoundError, ValueError, OSError):
        issues.append(f"immutable review bundle must resolve inside its canonical run: {expected_bundle}")
        return issues
    if document.scope.get("Artifact Hash") != content_hash(bundle_path):
        issues.append(f"immutable review bundle hash mismatch: {expected_bundle}")
    content = bundle_path.read_text(encoding="utf-8")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    header_lines: list[str] = []
    for line in normalized.split("\n"):
        if not line or line.startswith("## "):
            break
        header_lines.append(line)
    header_matches = [re.fullmatch(r"([A-Za-z][A-Za-z0-9 ]*):\s*(.+)", line) for line in header_lines]
    if any(match is None for match in header_matches):
        issues.append(f"bundle header contains malformed metadata: {expected_bundle}")
        return issues
    header_names = [match.group(1) for match in header_matches if match is not None]
    if header_names != BUNDLE_HEADER_FIELDS:
        issues.append(f"bundle header must contain the exact canonical metadata fields in order: {expected_bundle}")
        return issues
    header = {match.group(1): trim_value(match.group(2)) for match in header_matches if match is not None}
    expected_fields = {
        "Run": f"/.recursive/run/{run_dir.name}/",
        "Phase": artifact_file,
        "Phase Key": phase_key,
        "Review ID": review_id,
        "Pass": pass_id,
        "Bundle Path": expected_bundle,
        "Artifact Path": f"/.recursive/run/{run_dir.name}/{artifact_file}",
        "Review Ledger Path": canonical_display(repo_root, ledger_path),
        "Audit Payload Profile": AUDIT_PAYLOAD_PROFILE,
    }
    for field, expected_value in expected_fields.items():
        if header.get(field) != expected_value:
            issues.append(f"bundle {field} does not match review context: {expected_bundle}")
    bundle_hash = header.get("Artifact Content Hash", "")
    payload_hash = header.get("Audit Payload Hash", "")
    if not HASH_RE.fullmatch(bundle_hash):
        issues.append(f"bundle Artifact Content Hash must be lowercase sha256: {expected_bundle}")
    if not HASH_RE.fullmatch(payload_hash):
        issues.append(f"bundle Audit Payload Hash must be lowercase sha256: {expected_bundle}")
    issues.extend(review_surface.validate(repo_root, content, current=current_surface))
    return issues


def validate_document(
    repo_root: Path,
    ledger_path: Path,
    document: ReviewDocument,
    *,
    standalone: bool,
    run_dir: Path | None,
    source_artifact: str | None = None,
    phase_key: str | None = None,
    validate_physical_handoffs: bool = True,
    validate_reviewed_artifact: bool = True,
    validate_current_surface: bool = True,
) -> list[str]:
    issues = validate_finding_states(document, standalone=standalone)
    scope = document.scope
    verdict = document.verdict
    if scope.get("Ledger Path") != canonical_display(repo_root, ledger_path):
        issues.append("Review Scope Ledger Path does not match the actual canonical ledger path")
    review_id = scope.get("Review ID", "")
    if not SLUG_RE.fullmatch(review_id):
        issues.append("Review ID must be kebab-case")
    pass_id = scope.get("Pass", "")
    if not re.fullmatch(r"[0-9]{4}", pass_id) or pass_id == "0000":
        issues.append("Pass must be a positive zero-padded four-digit ID")
    for finding_id, finding in document.findings.items():
        discovered = finding.get("Discovered in pass", "")
        if not re.fullmatch(r"[0-9]{4}", discovered) or discovered == "0000":
            issues.append(f"{finding_id} Discovered in pass must be a positive zero-padded four-digit ID")
        elif pass_id.isdigit() and pass_id != "0000" and int(discovered) > int(pass_id):
            issues.append(f"{finding_id} Discovered in pass cannot be later than the current pass")
    artifact_hash = scope.get("Artifact Hash", "")
    if not HASH_RE.fullmatch(artifact_hash):
        issues.append("Artifact Hash must be lowercase sha256")
    for field in ("Previous Pass Hash",):
        value = scope.get(field, "")
        if value != "none" and not HASH_RE.fullmatch(value):
            issues.append(f"{field} must be none or lowercase sha256")
    if validate_reviewed_artifact:
        artifact = repo_path(repo_root, scope.get("Reviewed Artifact", ""))
        try:
            artifact.resolve().relative_to(repo_root.resolve())
        except ValueError:
            issues.append("Reviewed Artifact must stay inside the repository")
        if not artifact.is_file():
            issues.append("Reviewed Artifact does not exist as a repo file")
        elif scope.get("Artifact Hash") != content_hash(artifact):
            issues.append("Artifact Hash does not match Reviewed Artifact")
    if (
        run_dir is not None
        and source_artifact is not None
        and phase_key is not None
        and SLUG_RE.fullmatch(review_id)
        and re.fullmatch(r"[0-9]{4}", pass_id)
    ):
        issues.extend(
            validate_bundle_scope(
                repo_root,
                run_dir,
                phase_key,
                source_artifact,
                review_id,
                pass_id,
                ledger_path,
                document,
                current_surface=validate_current_surface,
            )
        )
    if scope.get("Diff Basis") in {"", "none"}:
        issues.append("Diff Basis must be executable or cite a canonical bundle")
    for list_field in ("Changed Files items", "Evidence Basis items"):
        if not scope.get(list_field):
            issues.append(f"{list_field.removesuffix(' items')} list is empty")

    open_ids = [finding_id for finding_id, finding in document.findings.items() if finding.get("Disposition") == "open"]
    declared_open = parse_id_list(verdict.get("Open Findings", "none"))
    if declared_open != open_ids:
        issues.append("Verdict Open Findings does not match open ledger records")
    result = verdict.get("Result", "")
    controller = verdict.get("Controller", "")
    verified_pass = verdict.get("Verified Pass", "")
    verified_hash = verdict.get("Verified Pass Hash", "")
    working = verified_pass == "none" and verified_hash == "none"
    if result not in {"PASS", "FAIL"}:
        issues.append("Verdict Result must be PASS|FAIL")
    if working and result != "FAIL":
        issues.append("working ledger must use Result: FAIL")
    if result == "PASS" and open_ids:
        issues.append("PASS is invalid while open findings remain")
    if result == "FAIL" and not open_ids and not working:
        issues.append("completed FAIL must identify at least one open finding")

    scheduled_ids = [finding_id for finding_id, finding in document.findings.items() if finding.get("Disposition") == "scheduled"]
    if run_dir is not None and validate_physical_handoffs:
        for finding_id, finding in document.findings.items():
            if finding.get("Disposition") == "scheduled":
                scheduled_issues, _status = validate_scheduled_finding(
                    repo_root,
                    run_dir,
                    ledger_path,
                    source_artifact or "03.5-code-review.md",
                    review_id,
                    finding_id,
                    finding,
                )
                issues.extend(scheduled_issues)
    for finding_id, finding in document.findings.items():
        if finding.get("Disposition") in {"deferred", "out-of-scope"} and finding.get("Destination"):
            raw_destination = finding["Destination"]
            if not re.match(r"^https://", raw_destination):
                destination = repo_path(repo_root, raw_destination)
                try:
                    destination.resolve().relative_to(repo_root.resolve())
                except ValueError:
                    issues.append(f"{finding_id} durable destination must stay inside the repository")
                if not destination.exists():
                    issues.append(f"{finding_id} {finding.get('Disposition')} destination does not exist")
        if finding.get("Disposition") == "fixed":
            for dependency in parse_id_list(finding.get("Depends on", "none")):
                dependency_finding = document.findings.get(dependency)
                if dependency_finding and dependency_finding.get("Disposition") != "fixed":
                    issues.append(f"{finding_id} cannot be fixed until prerequisite {dependency} is fixed")
    declared_pending = parse_id_list(verdict.get("Pending Scheduled Handoffs", "none"))
    if declared_pending != scheduled_ids:
        issues.append("Verdict Pending Scheduled Handoffs must list every scheduled finding emitted by this pass")
    if verified_hash != "none" and not HASH_RE.fullmatch(verified_hash):
        issues.append("Verified Pass Hash must be none or lowercase sha256")
    if (verified_pass == "none") != (verified_hash == "none"):
        issues.append("Verified Pass and Verified Pass Hash must both be none or both be completed values")
    if working:
        if controller != "none":
            issues.append("working ledger must use Controller: none")
    elif controller in {"", "none"}:
        issues.append("completed pass requires Controller identity")
    return issues


def validate_pass_history(
    repo_root: Path,
    ledger_path: Path,
    current: ReviewDocument,
    *,
    context: LedgerContext,
) -> list[str]:
    issues: list[str] = []
    raw_current_pass = current.scope.get("Pass", "")
    current_pass = int(raw_current_pass) if re.fullmatch(r"[0-9]{4}", raw_current_pass) else 0
    passes_dir = ledger_path.parent / "passes"
    snapshots = sorted(passes_dir.glob("*.md")) if passes_dir.is_dir() else []
    working = current.verdict.get("Verified Pass") == "none"
    last_snapshot = current_pass - 1 if working else current_pass
    expected_names = [f"{number:04d}.md" for number in range(1, last_snapshot + 1)]
    if [path.name for path in snapshots] != expected_names:
        issues.append("pass snapshots must be consecutive from 0001 through the current pass")
    parsed: dict[int, tuple[Path, ReviewDocument]] = {}
    for number, path in enumerate(snapshots, start=1):
        document, parse_issues = parse_document(path.read_text(encoding="utf-8"))
        issues.extend(f"passes/{path.name}: {issue}" for issue in parse_issues)
        if document is None:
            continue
        parsed[number] = (path, document)
        if document.scope.get("Pass") != f"{number:04d}":
            issues.append(f"passes/{path.name}: Pass field is not consecutive")
        actual_hash = normalized_snapshot_hash(document.content)
        if document.verdict.get("Verified Pass Hash") != actual_hash:
            issues.append(f"passes/{path.name}: Verified Pass Hash mismatch")
        if document.verdict.get("Verified Pass") != canonical_display(repo_root, path):
            issues.append(f"passes/{path.name}: Verified Pass does not point to itself")
        if number == 1:
            if document.scope.get("Previous Pass") != "none" or document.scope.get("Previous Pass Hash") != "none":
                issues.append("passes/0001.md: first pass must have no previous pass")
            for finding_id, finding in document.findings.items():
                if finding.get("Discovered in pass") != "0001":
                    issues.append(f"passes/0001.md: {finding_id} Discovered in pass must be 0001")
        else:
            previous_entry = parsed.get(number - 1)
            if previous_entry is None:
                issues.append(f"passes/{path.name}: preceding snapshot could not be parsed")
                continue
            previous_path, previous = previous_entry
            if document.scope.get("Previous Pass") != canonical_display(repo_root, previous_path):
                issues.append(f"passes/{path.name}: Previous Pass is not the immediately preceding snapshot")
            if document.scope.get("Previous Pass Hash") != normalized_snapshot_hash(previous.content):
                issues.append(f"passes/{path.name}: Previous Pass Hash mismatch")
            previous_ids = list(previous.findings)
            current_ids = list(document.findings)
            if current_ids[: len(previous_ids)] != previous_ids:
                issues.append(f"passes/{path.name}: prior finding IDs disappeared or were reordered")
            for finding_id in previous_ids:
                if finding_id not in document.findings:
                    continue
                for field in IMMUTABLE_FINDING_FIELDS:
                    if previous.findings[finding_id].get(field) != document.findings[finding_id].get(field):
                        issues.append(f"passes/{path.name}: immutable field changed for {finding_id}: {field}")
                if previous.findings[finding_id].get("Disposition") != "open":
                    for field in ("Disposition", "Claimed outcome", "Claimed changes", "Claimed verification", "Controller verification"):
                        if previous.findings[finding_id].get(field) != document.findings[finding_id].get(field):
                            issues.append(f"passes/{path.name}: terminal finding reopened or changed for {finding_id}: {field}")
            for finding_id in current_ids[len(previous_ids):]:
                if document.findings[finding_id].get("Discovered in pass") != f"{number:04d}":
                    issues.append(f"passes/{path.name}: {finding_id} Discovered in pass does not match first appearance")
        issues.extend(
            validate_document(
                repo_root,
                ledger_path,
                document,
                standalone=context.standalone,
                run_dir=context.run_dir,
                source_artifact=context.artifact_file,
                phase_key=context.phase_key,
                validate_physical_handoffs=False,
                validate_reviewed_artifact=not context.standalone,
                validate_current_surface=False,
            )
        )

    if working:
        if current_pass == 1:
            if current.scope.get("Previous Pass") != "none" or current.scope.get("Previous Pass Hash") != "none":
                issues.append("working Pass 0001 must have no previous pass")
        elif current_pass - 1 in parsed:
            previous_path, previous = parsed[current_pass - 1]
            if current.scope.get("Previous Pass") != canonical_display(repo_root, previous_path):
                issues.append("working ledger Previous Pass is not the immediately preceding snapshot")
            if current.scope.get("Previous Pass Hash") != normalized_snapshot_hash(previous.content):
                issues.append("working ledger Previous Pass Hash mismatch")
            previous_ids = list(previous.findings)
            current_ids = list(current.findings)
            if current_ids[: len(previous_ids)] != previous_ids:
                issues.append("working ledger prior finding IDs disappeared or were reordered")
            for finding_id in previous_ids:
                if finding_id not in current.findings:
                    continue
                for field in IMMUTABLE_FINDING_FIELDS:
                    if previous.findings[finding_id].get(field) != current.findings[finding_id].get(field):
                        issues.append(f"working ledger immutable field changed for {finding_id}: {field}")
                if previous.findings[finding_id].get("Disposition") != "open":
                    for field in ("Disposition", "Claimed outcome", "Claimed changes", "Claimed verification", "Controller verification"):
                        if previous.findings[finding_id].get(field) != current.findings[finding_id].get(field):
                            issues.append(f"working ledger terminal finding reopened or changed for {finding_id}: {field}")
            for finding_id in current_ids[len(previous_ids):]:
                if current.findings[finding_id].get("Discovered in pass") != f"{current_pass:04d}":
                    issues.append(f"working ledger {finding_id} Discovered in pass does not match first appearance")
        elif current_pass > 1:
            issues.append("working ledger preceding snapshot could not be parsed")

    verified_pass = current.verdict.get("Verified Pass", "")
    verified_hash = current.verdict.get("Verified Pass Hash", "")
    if verified_pass != "none":
        verified_path = repo_path(repo_root, verified_pass)
        if not verified_path.is_file():
            issues.append("Verified Pass snapshot does not exist")
        else:
            if verified_path != ledger_path.parent / "passes" / f"{current_pass:04d}.md":
                issues.append("Verified Pass does not match the current pass canonical path")
            if verified_hash != normalized_snapshot_hash(verified_path.read_text(encoding="utf-8")):
                issues.append("Verified Pass Hash does not match snapshot content")
            if ledger_path.read_bytes() != verified_path.read_bytes():
                issues.append("terminal ledger must be byte-for-byte identical to its Verified Pass snapshot")
    return issues


def classify_ledger(repo_root: Path, ledger_path: Path) -> tuple[LedgerContext, list[str]]:
    try:
        relative = ledger_path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return LedgerContext(False, None, None, None, None), ["ledger must live inside the repository control plane"]
    run_match = re.fullmatch(
        r"[.]recursive/run/([^/]+)/evidence/reviews/([a-z0-9]+(?:-[a-z0-9]+)*)/([a-z0-9]+(?:-[a-z0-9]+)*)/ledger[.]md",
        relative,
    )
    if run_match:
        run_dir = repo_root / ".recursive/run" / run_match.group(1)
        phase_key = run_match.group(2)
        artifact_file = phase_rules.audited_artifact_for_key(phase_key)
        context = LedgerContext(False, run_dir, phase_key, artifact_file, run_match.group(3))
        if artifact_file is None:
            return context, [f"ledger phase key is not in the audited registry: {phase_key}"]
        return context, []
    standalone_match = re.fullmatch(r"[.]recursive/local/reviews/([a-z0-9]+(?:-[a-z0-9]+)*)/ledger[.]md", relative)
    if standalone_match:
        return LedgerContext(True, None, None, None, standalone_match.group(1)), []
    return LedgerContext(False, None, None, None, None), ["ledger path is not canonical for an audited phase or standalone review"]


def validate_ledger(repo_root: Path, ledger_path: Path) -> ValidationResult:
    repo_root = repo_root.resolve()
    ledger_path = ledger_path.resolve()
    issues: list[str] = []
    if not ledger_path.is_file():
        return ValidationResult([f"ledger does not exist: {ledger_path}"], ledger_path=ledger_path)
    context, path_issues = classify_ledger(repo_root, ledger_path)
    issues.extend(path_issues)
    document, parse_issues = parse_document(ledger_path.read_text(encoding="utf-8"))
    issues.extend(parse_issues)
    if document is None:
        return ValidationResult(issues, ledger_path=ledger_path)
    if context.review_id and document.scope.get("Review ID") != context.review_id:
        issues.append("Review Scope Review ID does not match canonical ledger directory")
    if context.run_dir is not None and context.review_id:
        matches = {
            path.resolve()
            for path in context.run_dir.glob(f"evidence/reviews/*/{context.review_id}/ledger.md")
            if path.is_file()
        }
        if len(matches) > 1:
            issues.append(f"Review ID must be globally unique within the run: {context.review_id}")
    issues.extend(
        validate_document(
            repo_root,
            ledger_path,
            document,
            standalone=context.standalone,
            run_dir=context.run_dir,
            source_artifact=context.artifact_file,
            phase_key=context.phase_key,
        )
    )
    issues.extend(validate_pass_history(repo_root, ledger_path, document, context=context))
    return ValidationResult(issues, ledger_path=ledger_path, document=document)


def get_artifact_field(content: str, field_name: str) -> str:
    match = re.search(rf"(?m)^-?\s*{re.escape(field_name)}:\s*(.+?)\s*$", content)
    return trim_value(match.group(1)) if match else ""


def parse_review_metadata(content: str) -> tuple[dict[str, str], list[str]]:
    issues: list[str] = []
    bodies = [body for name, body in markdown_h2_sections(content) if name == "Review Metadata"]
    if len(bodies) != 1:
        issues.append(f"phase artifact must contain exactly one ## Review Metadata section; found {len(bodies)}")
    if not bodies:
        return {}, issues
    body = bodies[0]
    if not body.strip():
        issues.append("phase artifact is missing non-empty ## Review Metadata")
    fields, order, duplicates = parse_fields(body)
    if duplicates:
        issues.append(f"Review Metadata has duplicate field(s): {', '.join(sorted(set(duplicates)))}")
    if order != REVIEW_METADATA_FIELDS:
        issues.append("Review Metadata fields do not match the exact schema/order")
    if residual_schema_lines(body):
        issues.append("Review Metadata contains content outside its exact field schema")
    for field in REVIEW_METADATA_FIELDS:
        if not fields.get(field):
            issues.append(f"Review Metadata field is empty: {field}")
    return fields, issues


def validate_phase_artifact(repo_root: Path, run_dir: Path, artifact_path: Path) -> ValidationResult:
    artifact_file = artifact_path.name
    phase_key = phase_rules.audited_phase_key(artifact_file)
    if phase_key is None:
        return ValidationResult([f"phase artifact is not in the audited registry: {artifact_file}"])
    content = artifact_path.read_text(encoding="utf-8") if artifact_path.is_file() else ""
    metadata, metadata_issues = parse_review_metadata(content)
    issues = list(metadata_issues)
    ledger_value = metadata.get("Review Ledger Path", "")
    if not ledger_value:
        return ValidationResult(issues + [f"{artifact_file} is missing Review Ledger Path"])
    ledger_path = repo_path(repo_root, ledger_value)
    result = validate_ledger(repo_root, ledger_path)
    issues.extend(result.issues)
    context, context_issues = classify_ledger(repo_root, ledger_path)
    issues.extend(context_issues)
    if (
        context.run_dir is None
        or context.run_dir.resolve() != run_dir.resolve()
        or context.phase_key != phase_key
        or context.artifact_file != artifact_file
    ):
        issues.append("phase artifact Review Ledger Path does not match its run and audited phase")
    document = result.document
    if document is not None:
        artifact_pass = metadata.get("Latest Verified Pass", "") or get_artifact_field(content, "Latest Verified Pass")
        artifact_hash = metadata.get("Latest Verified Pass Hash", "") or get_artifact_field(content, "Latest Verified Pass Hash")
        if artifact_pass != document.verdict.get("Verified Pass"):
            issues.append("phase artifact Latest Verified Pass does not match ledger")
        if artifact_hash != document.verdict.get("Verified Pass Hash"):
            issues.append("phase artifact Latest Verified Pass Hash does not match ledger")
        if document.verdict.get("Result") != "PASS":
            issues.append("phase ledger must reach whole-ledger PASS before closure")
        if context.review_id:
            pass_id = document.scope.get("Pass", "")
            expected_bundle = canonical_bundle_display(run_dir, phase_key, context.review_id, pass_id)
            bundle_value = metadata.get("Review Bundle Path", "")
            if metadata.get("Review ID") != context.review_id:
                issues.append("Review Metadata Review ID does not match ledger")
            if bundle_value != expected_bundle or bundle_value != document.scope.get("Reviewed Artifact"):
                issues.append("Review Metadata Review Bundle Path does not match phase/review/pass")
            bundle_path = repo_path(repo_root, bundle_value)
            if metadata.get("Review Bundle Hash") != document.scope.get("Artifact Hash"):
                issues.append("Review Metadata Review Bundle Hash does not match ledger Artifact Hash")
            if bundle_path.is_file():
                bundle_content = bundle_path.read_text(encoding="utf-8")
                if get_artifact_field(bundle_content, "Artifact Path") != canonical_display(repo_root, artifact_path):
                    issues.append("review bundle Artifact Path does not match phase artifact")
                if get_artifact_field(bundle_content, "Audit Payload Profile") != AUDIT_PAYLOAD_PROFILE:
                    issues.append("review bundle Audit Payload Profile is unsupported")
                if get_artifact_field(bundle_content, "Audit Payload Hash") != audit_payload_hash(content):
                    issues.append("review bundle Audit Payload Hash does not match current phase receipt")
    return ValidationResult(issues, ledger_path=ledger_path, document=document)


def validate_handoff_record(
    repo_root: Path,
    run_dir: Path,
    path: Path,
    record_key: str,
) -> tuple[dict[str, str] | None, list[str]]:
    issues: list[str] = []
    fields, handoff_issues = parse_handoff(path, record_key)
    issues.extend(handoff_issues)
    if fields is None:
        return None, issues
    key_match = re.fullmatch(r"([a-z0-9]+(?:-[a-z0-9]+)*)/(F-[0-9]{3,})", record_key)
    if key_match is None:
        issues.append(f"scheduled handoff record key is not <review-id>/F-*: {record_key}")
    source_path = repo_path(repo_root, fields.get("Source Ledger", ""))
    source_context, source_context_issues = classify_ledger(repo_root, source_path)
    issues.extend(f"scheduled handoff source {record_key}: {issue}" for issue in source_context_issues)
    if (
        source_context.run_dir is None
        or source_context.run_dir.resolve() != run_dir.resolve()
        or source_context.artifact_file is None
    ):
        issues.append(f"scheduled handoff Source Ledger is outside the active run or audited phase: {record_key}")
    source_result = validate_ledger(repo_root, source_path)
    issues.extend(f"scheduled handoff source {record_key}: {issue}" for issue in source_result.issues)
    if key_match is not None and source_result.document is not None:
        review_id, finding_id = key_match.groups()
        source_document = source_result.document
        source_finding = source_document.findings.get(finding_id)
        if source_document.scope.get("Review ID") != review_id:
            issues.append(f"scheduled handoff record key does not match source Review ID: {record_key}")
        if source_finding is None or source_finding.get("Disposition") != "scheduled":
            issues.append(f"scheduled handoff has no scheduled source finding: {record_key}")
        else:
            expected_values = {
                "Finding ID": finding_id,
                "Kind": source_finding.get("Kind", ""),
                "Location": source_finding.get("Location", ""),
                "Observed": source_finding.get("Observed", ""),
                "Expected": source_finding.get("Expected", ""),
                "Contract": source_finding.get("Contract", ""),
                "Technical impact": source_finding.get("Technical impact", ""),
                "Required outcome": source_finding.get("Required outcome", ""),
                "Verification": source_finding.get("Verification", ""),
                "Owner phase": source_finding.get("Owner phase", ""),
                "Scheduling basis": source_finding.get("Scheduling basis", ""),
            }
            for field, expected_value in expected_values.items():
                if fields.get(field) != expected_value:
                    issues.append(f"scheduled handoff {record_key} {field} does not match source finding")
            if source_finding.get("Destination") != canonical_display(repo_root, path):
                issues.append(f"scheduled handoff destination does not match source finding: {record_key}")
    return fields, issues


def get_active_scheduled_owner_phases(repo_root: Path, run_dir: Path) -> tuple[set[str], list[str]]:
    active: set[str] = set()
    issues: list[str] = []
    root = run_dir / "evidence/reviews/scheduled"
    if not root.exists():
        return active, issues
    for path in sorted(root.rglob("inventory.md")):
        content = path.read_text(encoding="utf-8")
        headings = re.findall(r"(?m)^## (.+?)\s*$", content)
        if not headings:
            issues.append(f"scheduled handoff inventory has no records: {canonical_display(repo_root, path)}")
        for record_key in headings:
            fields, record_issues = validate_handoff_record(repo_root, run_dir, path, record_key)
            issues.extend(record_issues)
            if fields is not None and not record_issues and fields.get("Status") == "pending":
                active.add(fields.get("Owner phase", ""))
    return active, sorted(set(issues))


def validate_scheduled_handoffs(repo_root: Path, run_dir: Path, target_artifact: str | None = None) -> ValidationResult:
    issues: list[str] = []
    root = run_dir / "evidence/reviews/scheduled"
    if not root.exists():
        return ValidationResult()
    for path in sorted(root.rglob("inventory.md")):
        content = path.read_text(encoding="utf-8")
        headings = re.findall(r"(?m)^## (.+?)\s*$", content)
        if not headings:
            issues.append(f"scheduled handoff inventory has no records: {canonical_display(repo_root, path)}")
        for record_key in headings:
            fields, handoff_issues = validate_handoff_record(repo_root, run_dir, path, record_key)
            issues.extend(handoff_issues)
            if fields is None:
                continue
            owner = fields.get("Owner phase", "")
            applies = target_artifact is None or owner == target_artifact or target_artifact == "08-memory-impact.md"
            if applies and fields.get("Status") != "consumed":
                issues.append(f"unconsumed scheduled handoff blocks {target_artifact or 'closeout'}: {canonical_display(repo_root, path)}#{record_key}")
    return ValidationResult(issues)


def collect_phase_issues(repo_root: Path, run_dir: Path, artifact_name: str, content: str | None = None) -> list[str]:
    issues: list[str] = []
    if phase_rules.is_audited_artifact(artifact_name):
        artifact_path = run_dir / artifact_name
        issues.extend(validate_phase_artifact(repo_root, run_dir, artifact_path).issues)
    issues.extend(validate_scheduled_handoffs(repo_root, run_dir, artifact_name).issues)
    return [f"Recursive review: {issue}" for issue in issues]


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a Recursive Review ledger or audited phase artifact.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--ledger", default="")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--phase-artifact", default="03.5-code-review.md")
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    if args.ledger:
        result = validate_ledger(repo_root, repo_path(repo_root, args.ledger))
    elif args.run_id is not None:
        if not phase_rules.is_canonical_run_id(args.run_id):
            print(f"[FAIL] {phase_rules.CANONICAL_RUN_ID_ERROR}")
            return 1
        run_dir = repo_root / ".recursive/run" / args.run_id
        result = validate_phase_artifact(repo_root, run_dir, run_dir / args.phase_artifact)
    else:
        parser.error("provide --ledger or --run-id")
    if result.valid:
        print("[PASS] Recursive Review ledger is valid")
        return 0
    for issue in result.issues:
        print(f"[FAIL] {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
