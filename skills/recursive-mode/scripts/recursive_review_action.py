#!/usr/bin/env python3
"""Shared parser and validator for persisted review action claims."""

from __future__ import annotations

import argparse
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

import recursive_phase_rules as phase_rules
import recursive_review_ledger as review_ledger


ID_RE = re.compile(r"F-[0-9]{3,}")
OUTCOMES = {"none", "fixed", "blocked"}
PROTOCOL_PATH = "/.agents/skills/recursive-review/references/finding-protocol.md"
CLAIM_SCHEMA_ISSUE = "structured review action must use the exact ordered Claimed Findings schema"
STRUCTURED_EXECUTION_TOKENS = {"review", "reviewer", "audit", "auditor", "repair", "repairer"}
REVIEW_AUDIT_EXECUTION_TOKENS = {"review", "reviewer", "audit", "auditor"}
NON_REVIEW_EXECUTION_TOKENS = {
    "implement",
    "implementation",
    "implementer",
    "qa",
    "repair",
    "repairer",
    "test",
    "tester",
    "testing",
}
ACTION_RECORD_TITLE = "Subagent Action Record"
ACTION_RECORD_SECTIONS = (
    "Metadata",
    "Inputs Provided",
    "Routing",
    "Claimed Actions Taken",
    "Claimed File Impact",
    "Claimed Artifact Impact",
    "Claimed Findings",
    "Verification Handoff",
)
ACTION_RECORD_METADATA_FIELDS = (
    "Subagent ID",
    "Run ID",
    "Phase",
    "Purpose",
    "Execution Mode",
    "Timestamp",
    "Action Record Path",
)
ACTION_RECORD_INPUT_FIELDS = (
    "Current Artifact",
    "Artifact Content Hash",
    "Upstream Artifacts",
    "Addenda",
    "Review Bundle",
    "Diff Basis",
    "Code Refs",
    "Memory Refs",
    "Audit / Task Questions",
)
ACTION_RECORD_ROUTING_FIELDS = (
    "Router Used",
    "Routed Role",
    "Routed CLI",
    "Routed Model",
    "Routing Config Path",
    "Routing Discovery Path",
    "Routing Resolution Basis",
    "Routing Fallback Reason",
    "CLI Probe Summary",
    "Prompt Bundle Path",
    "Invocation Exit Code",
    "Output Capture Paths",
)
ACTION_RECORD_FILE_IMPACT_SECTIONS = (
    "Created",
    "Modified",
    "Reviewed",
    "Relevant but Untouched",
)
ACTION_RECORD_ARTIFACT_IMPACT_SECTIONS = ("Read", "Updated", "Evidence Used")
ACTION_RECORD_HANDOFF_FIELDS = ("Inspect first", "Notes")
REPO_PATH_DRIVE_RE = re.compile(r"^[A-Za-z]:")
REPO_PATH_SCALAR_FIELDS = (
    ("Metadata", "Action Record Path", False),
    ("Inputs Provided", "Current Artifact", True),
    ("Inputs Provided", "Review Bundle", True),
    ("Routing", "Routing Config Path", True),
    ("Routing", "Routing Discovery Path", True),
    ("Routing", "Prompt Bundle Path", True),
)
REPO_PATH_NESTED_LIST_FIELDS = (
    ("Inputs Provided", "Upstream Artifacts"),
    ("Inputs Provided", "Addenda"),
    ("Inputs Provided", "Code Refs"),
    ("Inputs Provided", "Memory Refs"),
    ("Routing", "Output Capture Paths"),
    ("Verification Handoff", "Inspect first"),
)
REPO_PATH_SUBSECTION_LIST_FIELDS = (
    ("Claimed File Impact", ACTION_RECORD_FILE_IMPACT_SECTIONS),
    ("Claimed Artifact Impact", ACTION_RECORD_ARTIFACT_IMPACT_SECTIONS),
)


@dataclass
class ActionValidation:
    issues: list[str]

    @property
    def valid(self) -> bool:
        return not self.issues


@dataclass
class ActionPathValidation:
    path: Path | None
    issues: list[str]

    @property
    def valid(self) -> bool:
        return self.path is not None and not self.issues


def field_values(body: str, name: str) -> list[str]:
    return [review_ledger.trim_value(value) for value in re.findall(rf"(?m)^- {re.escape(name)}:\s*(.*?)\s*$", body)]


def sections(content: str, name: str) -> list[str]:
    return [body for heading, body in review_ledger.markdown_h2_sections(content) if heading == name]


def section(content: str, name: str) -> str:
    bodies = sections(content, name)
    return bodies[0] if len(bodies) == 1 else ""


def normalize_repo_path_argument(raw_path: str) -> tuple[str | None, str | None]:
    """Normalize one CLI repo path while rejecting ambiguous or escaping forms."""
    if not isinstance(raw_path, str) or not raw_path:
        return None, "repository path cannot be empty"
    if raw_path != raw_path.strip():
        return None, "repository path cannot have leading or trailing whitespace"
    if "\r" in raw_path or "\n" in raw_path or "\x00" in raw_path:
        return None, "repository path cannot contain CR, LF, or NUL"
    if raw_path.startswith(("\\\\", "//")):
        return None, "repository path cannot use an absolute UNC form"

    normalized = raw_path.replace("\\", "/")
    if normalized.startswith("//"):
        return None, "repository path cannot use an absolute UNC form"
    relative = normalized[1:] if normalized.startswith("/") else normalized
    if REPO_PATH_DRIVE_RE.match(relative):
        return None, "repository path cannot use an absolute drive form"
    if not relative:
        return None, "repository path cannot be empty"
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        return None, "repository path cannot contain empty, dot, or dot-dot components"
    return "/".join(parts), None


def repo_path_display(relative_path: str) -> str:
    """Render a normalized repository-relative path in persisted canonical form."""
    return f"/{relative_path}"


def validate_repo_path_display(
    value: str,
    *,
    allow_none: bool = False,
) -> tuple[str | None, str | None]:
    """Validate persisted `/<repo-relative>` display syntax without normalizing it."""
    if allow_none and value == "none":
        return None, None
    normalized, issue = normalize_repo_path_argument(value)
    if issue:
        return None, issue
    assert normalized is not None
    expected = repo_path_display(normalized)
    if value != expected:
        return None, f"repository path must use canonical forward-slash display `{expected}`"
    return normalized, None


def _is_link_or_reparse_point(path: Path) -> bool:
    try:
        metadata = path.lstat()
    except OSError:
        return False
    file_attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(file_attributes & reparse_flag)


def _confined_repo_leaf(
    repo_root: Path,
    repo_path: str,
) -> tuple[Path | None, list[str]]:
    """Resolve a canonical persisted repo path without following path indirection."""
    relative, issue = validate_repo_path_display(repo_path)
    if issue or relative is None:
        return None, [issue or "repository path is invalid"]
    lexical_root = Path(os.path.abspath(repo_root))
    try:
        root_metadata = lexical_root.lstat()
    except OSError:
        return None, ["repository root cannot be inspected safely"]
    if _is_link_or_reparse_point(lexical_root) or not stat.S_ISDIR(root_metadata.st_mode):
        return None, ["repository root must be a regular directory without indirection"]

    candidate = lexical_root / Path(relative)
    current = lexical_root
    try:
        for index, component in enumerate(Path(relative).parts):
            current = current / component
            metadata = current.lstat()
            if _is_link_or_reparse_point(current):
                return None, [f"repository path component cannot be a symlink or reparse point: /{'/'.join(Path(relative).parts[: index + 1])}"]
            if index < len(Path(relative).parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
                return None, [f"repository path parent must be a directory: /{'/'.join(Path(relative).parts[: index + 1])}"]
    except OSError:
        return None, ["repository file does not exist or cannot be inspected safely"]
    try:
        resolved_root = lexical_root.resolve(strict=True)
        resolved_candidate = candidate.resolve(strict=True)
        resolved_candidate.relative_to(resolved_root)
    except (OSError, ValueError):
        return None, ["resolved repository file escapes the repository or cannot be resolved safely"]
    return candidate, []


def read_confined_repo_text(
    repo_root: Path,
    repo_path: str,
) -> tuple[str | None, Path | None, list[str]]:
    """Read one canonical repo path as a unique regular strict-UTF-8 file."""
    path, issues = _confined_repo_leaf(repo_root, repo_path)
    if path is None:
        return None, None, issues
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                return None, None, ["repository file must be a unique regular file"]
            payload = stream.read()
            after_read = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(after_read.st_mode)
                or after_read.st_nlink != 1
                or (after_read.st_dev, after_read.st_ino) != (metadata.st_dev, metadata.st_ino)
            ):
                return None, None, ["repository file became hard-linked or non-regular while being read"]
        leaf_metadata = path.lstat()
        if (
            _is_link_or_reparse_point(path)
            or not stat.S_ISREG(leaf_metadata.st_mode)
            or leaf_metadata.st_nlink != 1
            or (leaf_metadata.st_dev, leaf_metadata.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            return None, None, ["repository file leaf changed or became unsafe while being read"]
        return payload.decode("utf-8"), path, []
    except UnicodeDecodeError:
        return None, None, ["repository file must be valid UTF-8"]
    except OSError:
        return None, None, ["repository file cannot be read safely"]
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def read_action_record_text(path: Path) -> tuple[str | None, list[str]]:
    """Read a persisted action record as strict UTF-8 without raising."""
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = -1
    try:
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as stream:
            descriptor = -1
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                return None, ["action record must be a unique regular file"]
            payload = stream.read()
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                return None, ["action record became hard-linked or non-regular while being read"]
        leaf_metadata = path.lstat()
        if (
            _is_link_or_reparse_point(path)
            or not stat.S_ISREG(leaf_metadata.st_mode)
            or leaf_metadata.st_nlink != 1
            or (leaf_metadata.st_dev, leaf_metadata.st_ino) != (metadata.st_dev, metadata.st_ino)
        ):
            return None, ["action record leaf changed or became unsafe while being read"]
        return payload.decode("utf-8"), []
    except UnicodeDecodeError:
        return None, ["action record must be valid UTF-8"]
    except OSError:
        return None, ["action record file cannot be read safely"]
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def validate_action_record_path(
    repo_root: Path,
    run_dir: Path,
    action_record_path: str | Path | None = None,
) -> ActionPathValidation:
    """Resolve one canonical persisted action record without following indirection."""
    issues: list[str] = []

    lexical_repo_root = Path(os.path.abspath(repo_root))
    lexical_run_dir = Path(os.path.abspath(run_dir))
    try:
        relative_run = lexical_run_dir.relative_to(lexical_repo_root)
    except ValueError:
        return ActionPathValidation(None, ["action record run directory escapes the repository"])
    if relative_run.parts[:2] != (".recursive", "run") or len(relative_run.parts) != 3:
        return ActionPathValidation(None, ["action record run directory is not canonical"])

    repo_root = lexical_repo_root.resolve()
    run_dir = repo_root / relative_run
    expected_subagents = run_dir / "subagents"

    for component in (
        repo_root / ".recursive",
        repo_root / ".recursive" / "run",
        run_dir,
        expected_subagents,
    ):
        if component.exists() or _is_link_or_reparse_point(component):
            if _is_link_or_reparse_point(component):
                issues.append(f"action record path component cannot be a symlink or reparse point: {component}")
                return ActionPathValidation(None, issues)
    if not expected_subagents.exists():
        return ActionPathValidation(None, ["action record directory does not exist"])
    try:
        if not stat.S_ISDIR(expected_subagents.lstat().st_mode):
            return ActionPathValidation(None, ["action record directory must be a regular directory"])
        if expected_subagents.resolve(strict=True) != run_dir.resolve(strict=True) / "subagents":
            return ActionPathValidation(None, ["resolved action record directory escapes its owning run"])
        for entry in expected_subagents.iterdir():
            if _is_link_or_reparse_point(entry):
                issues.append(
                    f"action record directory entry cannot be a symlink or reparse point: {entry}"
                )
                continue
            entry_metadata = entry.lstat()
            if not stat.S_ISREG(entry_metadata.st_mode):
                issues.append(
                    f"action record directory cannot contain nested or non-regular entries: {entry}"
                )
                continue
            if entry_metadata.st_nlink != 1:
                issues.append(f"action record directory cannot contain hard-linked entries: {entry}")
                continue
            if entry.resolve(strict=True).parent != expected_subagents.resolve(strict=True):
                issues.append(f"resolved action record directory entry escapes its canonical directory: {entry}")
    except OSError:
        return ActionPathValidation(None, ["action record directory cannot be resolved safely"])
    if issues:
        return ActionPathValidation(None, sorted(set(issues)))

    if action_record_path is None:
        return ActionPathValidation(expected_subagents, [])

    if isinstance(action_record_path, Path) and action_record_path.is_absolute():
        try:
            relative_value = action_record_path.relative_to(lexical_repo_root).as_posix()
        except ValueError:
            try:
                relative_value = action_record_path.relative_to(repo_root).as_posix()
            except ValueError:
                return ActionPathValidation(None, ["action record path escapes the repository"])
    else:
        relative_value, path_issue = normalize_repo_path_argument(str(action_record_path))
        if path_issue or relative_value is None:
            return ActionPathValidation(None, [f"action record path is not canonical: {path_issue}"])
    relative_candidate = Path(relative_value)
    candidate = repo_root / relative_candidate
    expected_parent = relative_run / "subagents"
    if relative_candidate.parent != expected_parent or relative_candidate.suffix.lower() != ".md":
        return ActionPathValidation(
            None,
            [f"action record must be a direct Markdown child of /{expected_parent.as_posix()}/"],
        )
    if _is_link_or_reparse_point(candidate):
        return ActionPathValidation(None, ["action record file cannot be a symlink or reparse point"])
    try:
        metadata = candidate.lstat()
    except OSError:
        return ActionPathValidation(None, ["action record file does not exist"])
    if not stat.S_ISREG(metadata.st_mode):
        return ActionPathValidation(None, ["action record path must resolve to a regular file"])
    if metadata.st_nlink != 1:
        return ActionPathValidation(None, ["action record file cannot be a hard link"])
    try:
        resolved_candidate = candidate.resolve(strict=True)
        resolved_subagents = expected_subagents.resolve(strict=True)
    except OSError:
        return ActionPathValidation(None, ["action record file cannot be resolved safely"])
    if resolved_candidate.parent != resolved_subagents:
        return ActionPathValidation(None, ["resolved action record file escapes its canonical directory"])
    return ActionPathValidation(resolved_candidate, [])


def _markdown_headings(content: str, level: int) -> list[str]:
    marker = "#" * level
    return re.findall(rf"(?m)^{re.escape(marker)} ([^#\n].*?)\s*$", content)


def _body_lines(body: str) -> list[str]:
    normalized = body.replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    return normalized.split("\n") if normalized else []


def _schema_issue(section_name: str) -> str:
    return f"action record ## {section_name} must use the exact canonical grammar"


def _validate_fields(
    body: str,
    expected: tuple[tuple[str, str], ...],
    section_name: str,
) -> list[str]:
    """Validate scalar and nested-list fields without accepting residual lines."""
    lines = _body_lines(body)
    cursor = 0
    for name, kind in expected:
        if cursor >= len(lines):
            return [_schema_issue(section_name)]
        if kind == "scalar":
            if re.fullmatch(rf"- {re.escape(name)}: \S.*", lines[cursor]) is None:
                return [_schema_issue(section_name)]
            cursor += 1
            continue
        if lines[cursor] != f"- {name}:":
            return [_schema_issue(section_name)]
        cursor += 1
        items: list[str] = []
        item_pattern = r"  - (?:none|`.+`)" if kind == "path_list" else r"  - \S.*"
        while cursor < len(lines) and re.fullmatch(item_pattern, lines[cursor]):
            items.append(lines[cursor][4:])
            cursor += 1
        if not items or ("none" in items and len(items) != 1):
            return [_schema_issue(section_name)]
    return [] if cursor == len(lines) else [_schema_issue(section_name)]


def _validate_text_list(body: str, section_name: str) -> list[str]:
    lines = _body_lines(body)
    if not lines or any(re.fullmatch(r"- \S.*", line) is None for line in lines):
        return [_schema_issue(section_name)]
    return []


def _validate_subsection_lists(
    body: str,
    expected: tuple[str, ...],
    section_name: str,
) -> list[str]:
    lines = _body_lines(body)
    cursor = 0
    for heading in expected:
        if cursor >= len(lines) or lines[cursor] != f"### {heading}":
            return [_schema_issue(section_name)]
        cursor += 1
        items: list[str] = []
        while cursor < len(lines) and re.fullmatch(r"- (?:none|`.+`)", lines[cursor]):
            items.append(lines[cursor][2:])
            cursor += 1
        if not items or ("none" in items and len(items) != 1):
            return [_schema_issue(section_name)]
    return [] if cursor == len(lines) else [_schema_issue(section_name)]


def _raw_scalar_field(body: str, name: str) -> list[str]:
    return re.findall(rf"(?m)^- {re.escape(name)}: `([^`\r\n]*)`$", body)


def _raw_nested_list(body: str, name: str) -> list[str]:
    lines = _body_lines(body)
    try:
        cursor = lines.index(f"- {name}:") + 1
    except ValueError:
        return []
    values: list[str] = []
    while cursor < len(lines) and lines[cursor].startswith("  - "):
        values.append(lines[cursor][4:])
        cursor += 1
    return values


def _raw_subsection_list(body: str, name: str) -> list[str]:
    lines = _body_lines(body)
    try:
        cursor = lines.index(f"### {name}") + 1
    except ValueError:
        return []
    values: list[str] = []
    while cursor < len(lines) and lines[cursor].startswith("- "):
        values.append(lines[cursor][2:])
        cursor += 1
    return values


def _validate_repo_path_atom(
    atom: str,
    *,
    allow_none: bool,
    location: str,
) -> list[str]:
    if atom == "none":
        return [] if allow_none else [f"{location} cannot use the none sentinel"]
    match = re.fullmatch(r"`([^`\r\n]*)`", atom)
    if match is None:
        return [f"{location} must use a backticked canonical repository path"]
    _relative, issue = validate_repo_path_display(match.group(1))
    return [f"{location} is not canonical: {issue}"] if issue else []


def _validate_repo_path_list(values: list[str], *, location: str) -> list[str]:
    if not values:
        return [f"{location} must contain one canonical path or the none sentinel"]
    if "none" in values:
        return [] if values == ["none"] else [f"{location} cannot combine the none sentinel with paths"]
    issues: list[str] = []
    for value in values:
        issues.extend(_validate_repo_path_atom(value, allow_none=False, location=location))
    return issues


def _validate_all_repo_path_fields(content: str) -> list[str]:
    """Apply one persisted `/<repo-relative>` grammar to every path-bearing field."""
    issues: list[str] = []
    for section_name, field_name, allow_none in REPO_PATH_SCALAR_FIELDS:
        body = section(content, section_name)
        values = _raw_scalar_field(body, field_name)
        if len(values) != 1:
            issues.append(f"action record {section_name}.{field_name} must contain one backticked value")
            continue
        _relative, issue = validate_repo_path_display(values[0], allow_none=allow_none)
        if issue:
            issues.append(f"action record {section_name}.{field_name} is not canonical: {issue}")

    for section_name, field_name in REPO_PATH_NESTED_LIST_FIELDS:
        issues.extend(
            _validate_repo_path_list(
                _raw_nested_list(section(content, section_name), field_name),
                location=f"action record {section_name}.{field_name}",
            )
        )

    for section_name, subsection_names in REPO_PATH_SUBSECTION_LIST_FIELDS:
        body = section(content, section_name)
        for subsection_name in subsection_names:
            issues.extend(
                _validate_repo_path_list(
                    _raw_subsection_list(body, subsection_name),
                    location=f"action record {section_name}.{subsection_name}",
                )
            )

    findings = section(content, "Claimed Findings")
    if _looks_structured_findings(findings):
        for field_name in ("Review Protocol", "Review Bundle", "Review Ledger"):
            values = _raw_scalar_field(findings, field_name)
            if len(values) != 1:
                issues.append(f"action record Claimed Findings.{field_name} must contain one backticked value")
                continue
            _relative, issue = validate_repo_path_display(values[0])
            if issue:
                issues.append(f"action record Claimed Findings.{field_name} is not canonical: {issue}")
        for raw_changes in re.findall(
            r"(?m)^- Claimed changes:\n((?:  - [^\r\n]*(?:\n|$))*)",
            findings,
        ):
            atoms = [
                line[4:]
                for line in raw_changes.splitlines()
                if line.startswith("  - ")
            ]
            issues.extend(
                _validate_repo_path_list(
                    atoms,
                    location="action record Claimed Findings.Claimed changes",
                )
            )
    return issues


def _looks_structured_findings(body: str) -> bool:
    structured_fields = ("Review Protocol", "Review Bundle", "Review Ledger", "Review Pass", "Claims")
    return any(
        re.fullmatch(rf"- {re.escape(name)}:.*", line)
        for line in _body_lines(body)
        for name in structured_fields
    )


def validate_full_action_record(
    content: str,
    *,
    expected_action_record_path: str | None = None,
) -> ActionValidation:
    """Validate the complete persisted schema emitted by recursive-subagent-action."""
    issues: list[str] = []
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    first_section = re.search(r"(?m)^## ", normalized)
    expected_prefix = f"# {ACTION_RECORD_TITLE}\n\n"
    if first_section is None or normalized[: first_section.start()] != expected_prefix:
        issues.append("action record must begin with only the canonical title before ## Metadata")
    if _markdown_headings(content, 1) != [ACTION_RECORD_TITLE]:
        issues.append("action record must contain exactly one canonical # Subagent Action Record title")
    if _markdown_headings(content, 2) != list(ACTION_RECORD_SECTIONS):
        issues.append("action record must use the exact canonical top-level section order and cardinality")

    metadata = section(content, "Metadata")
    inputs = section(content, "Inputs Provided")
    routing = section(content, "Routing")
    handoff = section(content, "Verification Handoff")
    issues.extend(
        _validate_fields(
            metadata,
            tuple((name, "scalar") for name in ACTION_RECORD_METADATA_FIELDS),
            "Metadata",
        )
    )
    input_list_fields = {
        "Upstream Artifacts",
        "Addenda",
        "Code Refs",
        "Memory Refs",
        "Audit / Task Questions",
    }
    issues.extend(
        _validate_fields(
            inputs,
            tuple(
                (
                    name,
                    "path_list"
                    if name in input_list_fields - {"Audit / Task Questions"}
                    else "text_list"
                    if name == "Audit / Task Questions"
                    else "scalar",
                )
                for name in ACTION_RECORD_INPUT_FIELDS
            ),
            "Inputs Provided",
        )
    )
    issues.extend(
        _validate_fields(
            routing,
            tuple(
                (name, "path_list" if name == "Output Capture Paths" else "scalar")
                for name in ACTION_RECORD_ROUTING_FIELDS
            ),
            "Routing",
        )
    )
    issues.extend(
        _validate_fields(
            handoff,
            (("Inspect first", "path_list"), ("Notes", "text_list")),
            "Verification Handoff",
        )
    )
    issues.extend(
        _validate_text_list(section(content, "Claimed Actions Taken"), "Claimed Actions Taken")
    )

    file_impact = section(content, "Claimed File Impact")
    issues.extend(
        _validate_subsection_lists(
            file_impact,
            ACTION_RECORD_FILE_IMPACT_SECTIONS,
            "Claimed File Impact",
        )
    )
    artifact_impact = section(content, "Claimed Artifact Impact")
    issues.extend(
        _validate_subsection_lists(
            artifact_impact,
            ACTION_RECORD_ARTIFACT_IMPACT_SECTIONS,
            "Claimed Artifact Impact",
        )
    )

    findings = section(content, "Claimed Findings")
    finding_h3 = _markdown_headings(findings, 3)
    if any(ID_RE.fullmatch(heading) is None for heading in finding_h3):
        issues.append("action record ## Claimed Findings contains a non-canonical finding subsection")
    if _looks_structured_findings(findings):
        _claims, claim_issues = parse_claims(content)
        issues.extend(claim_issues)
    else:
        issues.extend(_validate_text_list(findings, "Claimed Findings"))
    expected_h3 = [
        *ACTION_RECORD_FILE_IMPACT_SECTIONS,
        *ACTION_RECORD_ARTIFACT_IMPACT_SECTIONS,
        *finding_h3,
    ]
    if _markdown_headings(content, 3) != expected_h3:
        issues.append("action record must use canonical major subsections only in their owning sections")
    issues.extend(_validate_all_repo_path_fields(content))
    if expected_action_record_path is not None:
        expected_relative, expected_issue = normalize_repo_path_argument(expected_action_record_path)
        expected_display = (
            repo_path_display(expected_relative)
            if expected_relative is not None and expected_issue is None
            else ""
        )
        action_path_values = _raw_scalar_field(metadata, "Action Record Path")
        if action_path_values != [expected_display]:
            issues.append("action record Metadata.Action Record Path does not match its persisted file path")
    return ActionValidation(sorted(set(issues)))


def execution_mode_tokens(content: str) -> set[str]:
    metadata = section(content, "Metadata")
    values = field_values(metadata, "Execution Mode")
    if len(values) != 1:
        return set()
    return set(re.findall(r"[a-z0-9]+", values[0].lower()))


def is_review_audit_action(content: str) -> bool:
    """Return whether the record represents review/audit work, not repair or implementation."""
    tokens = execution_mode_tokens(content)
    return bool(tokens & REVIEW_AUDIT_EXECUTION_TOKENS) and not bool(tokens & NON_REVIEW_EXECUTION_TOKENS)


def review_pass_from_bundle_path(value: str) -> str:
    match = re.search(r"/(\d{4})\.md$", value)
    return match.group(1) if match and match.group(1) != "0000" else ""


def same_repo_path_binding(values: list[str], expected: str) -> bool:
    return len(values) == 1 and values[0].lstrip("/") == expected.lstrip("/")


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
        while cursor < len(lines) and re.fullmatch(r"  - (?:none|`.+`)", lines[cursor]):
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
        if ("none" in change_values and len(change_values) != 1) or (
            "none" in verification_values and len(verification_values) != 1
        ):
            issues.append(CLAIM_SCHEMA_ISSUE)
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
    expected_review_bundle: str | None = None,
    expected_review_ledger: str | None = None,
    expected_review_pass: str | None = None,
    expected_action_record_path: str | None = None,
) -> ActionValidation:
    full_validation = validate_full_action_record(
        content,
        expected_action_record_path=expected_action_record_path,
    )
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
    issues: list[str] = list(full_validation.issues)
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
        and bool(execution_tokens & STRUCTURED_EXECUTION_TOKENS)
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
    if expected_review_bundle is not None and not same_repo_path_binding(bundle_claims, expected_review_bundle):
        issues.append("structured review action Review Bundle does not match the owning phase")
    if expected_review_ledger is not None and not same_repo_path_binding(ledger_values, expected_review_ledger):
        issues.append("structured review action Review Ledger does not match the owning phase")
    if expected_review_pass is not None and pass_values != [expected_review_pass]:
        issues.append("structured review action Review Pass does not match the owning phase")
    claims, claim_issues = parse_claims(content)
    issues.extend(claim_issues)
    if not ledger_values:
        return ActionValidation(sorted(set(issues)))
    _ledger_content, ledger_path, ledger_read_issues = read_confined_repo_text(
        repo_root,
        ledger_values[0],
    )
    if ledger_path is None:
        issues.extend(f"cited ledger: {issue}" for issue in ledger_read_issues)
        return ActionValidation(sorted(set(issues)))
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


def validate_review_audit_action_record(
    repo_root: Path,
    content: str,
    *,
    expected_run: str,
    expected_phase: str,
    owning_artifact: str,
    expected_review_bundle: str,
    expected_review_ledger: str,
    expected_review_pass: str,
    expected_action_record_path: str | None = None,
) -> ActionValidation:
    """Validate lockable delegated review/audit evidence for one owning phase."""
    result = validate_action_record(
        repo_root,
        content,
        expected_run=expected_run,
        expected_phase=expected_phase,
        owning_artifact=owning_artifact,
        expected_review_bundle=expected_review_bundle,
        expected_review_ledger=expected_review_ledger,
        expected_review_pass=expected_review_pass,
        expected_action_record_path=expected_action_record_path,
    )
    issues = list(result.issues)
    if not is_review_audit_action(content):
        issues.append("delegated audit evidence must use a review/audit Execution Mode")
    return ActionValidation(sorted(set(issues)))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate a persisted review action record.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--action-record", required=True)
    args = parser.parse_args()
    repo_root = Path(args.repo_root).resolve()
    normalized_path, path_issue = normalize_repo_path_argument(args.action_record)
    if path_issue or normalized_path is None:
        print(f"[FAIL] Action record path is not canonical: {path_issue}")
        return 1
    relative_path = Path(normalized_path)
    if len(relative_path.parts) != 5 or relative_path.parts[:2] != (".recursive", "run") or relative_path.parts[3] != "subagents":
        print("[FAIL] Action record must use /.recursive/run/<run-id>/subagents/<record>.md")
        return 1
    run_dir = repo_root / ".recursive" / "run" / relative_path.parts[2]
    path_validation = validate_action_record_path(repo_root, run_dir, relative_path)
    if not path_validation.valid or path_validation.path is None:
        for issue in path_validation.issues:
            print(f"[FAIL] {issue}")
        return 1
    content, read_issues = read_action_record_text(path_validation.path)
    if content is None:
        for issue in read_issues:
            print(f"[FAIL] {issue}")
        return 1
    result = validate_action_record(
        repo_root,
        content,
        expected_action_record_path=repo_path_display(normalized_path),
    )
    if result.valid:
        print("[PASS] Recursive Review action record is valid")
        return 0
    for issue in result.issues:
        print(f"[FAIL] {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
