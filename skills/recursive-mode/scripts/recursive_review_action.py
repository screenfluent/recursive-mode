#!/usr/bin/env python3
"""Shared parser and validator for persisted review action claims."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

import recursive_phase_rules as phase_rules
import recursive_review_ledger as review_ledger


ID_RE = re.compile(r"F-[0-9]{3,}")
OUTCOMES = {"none", "fixed", "blocked"}
PROTOCOL_PATH = "/.agents/skills/recursive-review/references/finding-protocol.md"
CLAIM_SCHEMA_ISSUE = "structured review action must use the exact ordered Claimed Findings schema"
REVIEW_EXECUTION_TOKENS = {"review", "reviewer", "audit", "auditor", "repair", "repairer"}


@dataclass
class ActionValidation:
    issues: list[str]

    @property
    def valid(self) -> bool:
        return not self.issues


def field_values(body: str, name: str) -> list[str]:
    return [review_ledger.trim_value(value) for value in re.findall(rf"(?m)^- {re.escape(name)}:\s*(.*?)\s*$", body)]


def sections(content: str, name: str) -> list[str]:
    return [body for heading, body in review_ledger.markdown_h2_sections(content) if heading == name]


def section(content: str, name: str) -> str:
    bodies = sections(content, name)
    return bodies[0] if len(bodies) == 1 else ""


def parse_claims(content: str) -> tuple[dict[str, str], list[str]]:
    body = section(content, "Claimed Findings")
    if not body:
        return {}, ["structured review action is missing ## Claimed Findings"]
    lines = body.strip("\n").splitlines()
    issues: list[str] = []
    claims: dict[str, str] = {}
    metadata_fields = ("Review Protocol", "Review Bundle", "Review Ledger", "Review Pass")
    if len(lines) < len(metadata_fields):
        return claims, [CLAIM_SCHEMA_ISSUE]
    for index, field in enumerate(metadata_fields):
        if not re.fullmatch(rf"- {re.escape(field)}: \S.*", lines[index]):
            return claims, [CLAIM_SCHEMA_ISSUE]
    cursor = len(metadata_fields)
    if cursor < len(lines) and lines[cursor] == "- Claims: none":
        return (claims, issues) if cursor == len(lines) - 1 else (claims, [CLAIM_SCHEMA_ISSUE])
    if cursor >= len(lines) or lines[cursor] != "":
        return claims, [CLAIM_SCHEMA_ISSUE]
    cursor += 1
    ids: list[str] = []
    while cursor < len(lines):
        heading = re.fullmatch(r"### (F-[0-9]{3,})", lines[cursor])
        if not heading:
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        finding_id = heading.group(1)
        ids.append(finding_id)
        cursor += 1
        if cursor >= len(lines):
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        outcome_match = re.fullmatch(r"- Claimed outcome: `([^`]+)`", lines[cursor])
        if not outcome_match or outcome_match.group(1) not in OUTCOMES:
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        outcome = outcome_match.group(1)
        claims[finding_id] = outcome
        cursor += 1
        if cursor >= len(lines) or lines[cursor] != "- Claimed changes:":
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        cursor += 1
        change_values: list[str] = []
        while cursor < len(lines) and re.fullmatch(r"  - \S.*", lines[cursor]):
            change_values.append(review_ledger.trim_value(lines[cursor][4:]))
            cursor += 1
        if not change_values or cursor >= len(lines) or lines[cursor] != "- Claimed verification:":
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        cursor += 1
        verification_values: list[str] = []
        while cursor < len(lines) and re.fullmatch(r"  - \S.*", lines[cursor]):
            verification_values.append(review_ledger.trim_value(lines[cursor][4:]))
            cursor += 1
        if not verification_values:
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        has_changes = bool([value for value in change_values if value != "none"])
        has_verification = bool([value for value in verification_values if value != "none"])
        if outcome == "none" and (has_changes or has_verification):
            issues.append(f"{finding_id} none claim cannot contain changes or verification")
        if outcome == "fixed" and (not has_changes or not has_verification):
            issues.append(f"{finding_id} fixed claim requires changes and verification")
        if outcome == "blocked" and not has_verification:
            issues.append(f"{finding_id} blocked claim requires blocking verification")
        if cursor == len(lines):
            break
        if lines[cursor] != "" or cursor + 1 >= len(lines):
            issues.append(CLAIM_SCHEMA_ISSUE)
            break
        cursor += 1
    if ids != sorted(set(ids), key=lambda value: int(value.split("-", 1)[1])):
        issues.append(CLAIM_SCHEMA_ISSUE)
    issues = list(dict.fromkeys(issues))
    return claims, issues


def validate_claim_ids(document, claims: dict[str, object]) -> list[str]:
    issues: list[str] = []
    for finding_id in claims:
        finding = document.findings.get(finding_id)
        if finding is None:
            issues.append(f"action claim {finding_id} does not exist in the cited ledger")
        elif finding.get("Disposition") != "open":
            issues.append(f"action claim {finding_id} is not open in the cited ledger")
    return issues


def validate_action_record(
    repo_root: Path,
    content: str,
    *,
    expected_run: str | None = None,
    expected_phase: str | None = None,
    owning_artifact: str | None = None,
) -> ActionValidation:
    metadata_sections = sections(content, "Metadata")
    input_sections = sections(content, "Inputs Provided")
    finding_sections = sections(content, "Claimed Findings")
    metadata = metadata_sections[0] if len(metadata_sections) == 1 else ""
    inputs = input_sections[0] if len(input_sections) == 1 else ""
    findings = finding_sections[0] if len(finding_sections) == 1 else ""
    run_values = field_values(metadata, "Run ID")
    run_id = run_values[0] if len(run_values) == 1 else ""
    phase_values = field_values(metadata, "Phase")
    execution_mode_values = field_values(metadata, "Execution Mode")
    bundle_inputs = field_values(inputs, "Review Bundle")
    protocol_values = field_values(findings, "Review Protocol")
    bundle_claims = field_values(findings, "Review Bundle")
    ledger_values = field_values(findings, "Review Ledger")
    pass_values = field_values(findings, "Review Pass")
    phase = phase_values[0] if len(phase_values) == 1 else ""
    execution_mode = execution_mode_values[0] if len(execution_mode_values) == 1 else ""
    execution_tokens = set(re.findall(r"[a-z0-9]+", execution_mode.lower()))
    issues: list[str] = []
    for heading, bodies in (
        ("Metadata", metadata_sections),
        ("Inputs Provided", input_sections),
        ("Claimed Findings", finding_sections),
    ):
        if len(bodies) != 1:
            issues.append(f"action record must contain exactly one ## {heading} section")
    if len(run_values) != 1:
        issues.append("action record must cite exactly one Run ID")
    if len(phase_values) != 1:
        issues.append("action record must cite exactly one Phase")
    if len(execution_mode_values) != 1:
        issues.append("action record must cite exactly one Execution Mode")
    if expected_run and run_id != expected_run:
        issues.append("action record run does not match its owning run")
    if expected_phase and phase != expected_phase:
        issues.append("action record phase does not match its owning phase")
    audited_phase = (
        phase_rules.is_audited_artifact(owning_artifact or "")
        or phase_rules.audited_phase_key_from_label(expected_phase or "") is not None
        or phase_rules.audited_phase_key_from_label(phase) is not None
    )
    unstructured_finding = bool(findings.strip() and findings.strip() != "- none")
    has_structured_bindings = bool(pass_values or bundle_claims or ledger_values)
    if audited_phase and unstructured_finding and not has_structured_bindings:
        issues.append("unstructured finding in an audited phase must use the canonical review ledger")
    lossless_required = (
        audited_phase
        and bool(execution_tokens & REVIEW_EXECUTION_TOKENS)
    )
    structured = bool(pass_values or bundle_claims or ledger_values or lossless_required)
    if not structured:
        return ActionValidation(sorted(set(issues)))
    if protocol_values != [PROTOCOL_PATH]:
        issues.append("structured review action must cite the canonical Review Protocol")
    if len(bundle_inputs) != 1 or len(bundle_claims) != 1 or bundle_inputs != bundle_claims:
        issues.append("structured review action must cite one identical bundle in Inputs and Claimed Findings")
    if len(ledger_values) != 1:
        issues.append("structured review action must cite exactly one Review Ledger")
    if len(pass_values) != 1 or not re.fullmatch(r"[0-9]{4}", pass_values[0]) or pass_values[0] == "0000":
        issues.append("structured review action must cite one positive four-digit Review Pass")
    claims, claim_issues = parse_claims(content)
    issues.extend(claim_issues)
    if not ledger_values:
        return ActionValidation(sorted(set(issues)))
    ledger_path = repo_root / ledger_values[0].lstrip("/")
    result = review_ledger.validate_ledger(repo_root, ledger_path)
    if not result.valid or result.document is None:
        issues.extend(f"cited ledger: {issue}" for issue in result.issues)
        return ActionValidation(sorted(set(issues)))
    document = result.document
    if pass_values and document.scope.get("Pass") != pass_values[0]:
        issues.append("structured review action Review Pass does not match cited ledger")
    if bundle_claims and document.scope.get("Reviewed Artifact") != bundle_claims[0]:
        issues.append("structured review action Review Bundle does not match cited ledger")
    issues.extend(validate_claim_ids(document, claims))
    return ActionValidation(sorted(set(issues)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a persisted review action record.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--action-record", required=True)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    path = repo_root / args.action_record.lstrip("/")
    if not path.is_file():
        print(f"[FAIL] Action record not found: {path}")
        return 1
    result = validate_action_record(repo_root, path.read_text(encoding="utf-8"))
    if result.valid:
        print("[PASS] Recursive Review action record is valid")
        return 0
    for issue in result.issues:
        print(f"[FAIL] {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
