#!/usr/bin/env python3
"""
Generate a canonical recursive-mode review bundle for delegated audit or review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import recursive_phase_rules as phase_rules
import recursive_review_ledger as review_ledger
import recursive_review_surface as review_surface

DIFF_BASIS_ALLOWED_TYPES = {"local commit", "local branch", "remote ref", "merge-base derived"}
WORKING_TREE_COMPARISON_REFS = {"working-tree", "working-tree@head", "worktree", "working-tree+head"}
BUNDLE_SECTION_ORDER = [
    "Bundle Scope",
    "Routing",
    "Diff Basis",
    "Changed Files Reviewed",
    "Reviewed Surface Snapshot",
    "Upstream Artifacts To Re-read",
    "Relevant Addenda",
    "Prior Recursive Evidence",
    "Control-Plane Docs",
    "Targeted Code References",
    "Evidence References",
    "Audit Questions",
    "Required Output",
    "Notes",
]


def trim_md_value(value: str) -> str:
    return value.strip().strip("`\"'")


def get_md_field_value(content: str, field_name: str) -> str | None:
    pattern = re.compile(rf"(?m)^[ \t]*(?:[-*][ \t]+)?{re.escape(field_name)}:\s*(.+?)\s*$")
    match = pattern.search(content)
    if not match:
        return None
    return trim_md_value(match.group(1))


def run_git(repo_root: Path, *args: str) -> tuple[str | None, str | None]:
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_root), *args],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        return None, f"Unable to execute git: {exc}"
    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or f"git {' '.join(args)} failed"
        return None, message
    return result.stdout.strip(), None


def normalize_baseline_type(value: str | None) -> str | None:
    if value is None:
        return None
    compact = trim_md_value(value).strip().lower().replace("-", " ")
    compact = re.sub(r"\s+", " ", compact)
    if compact in DIFF_BASIS_ALLOWED_TYPES:
        return compact
    aliases = {
        "commit": "local commit",
        "branch": "local branch",
        "remote": "remote ref",
        "remote branch": "remote ref",
        "merge base": "merge-base derived",
    }
    return aliases.get(compact)


def normalize_comparison_reference(value: str | None) -> str | None:
    if value is None:
        return None
    compact = trim_md_value(value).strip()
    if not compact:
        return None
    if compact.lower() in WORKING_TREE_COMPARISON_REFS:
        return "working-tree"
    return compact


def parse_diff_basis_source(content: str) -> str:
    diff_body = re.search(r"(?ms)^##\s+Diff Basis For Later Audits\s*$\n?(.*?)(?=^##\s+|\Z)", content)
    if diff_body:
        return diff_body.group(1)
    diff_body = re.search(r"(?ms)^##\s+Diff Basis\s*$\n?(.*?)(?=^##\s+|\Z)", content)
    if diff_body:
        return diff_body.group(1)
    return content


def get_run_diff_basis(content: str) -> dict[str, str | None]:
    source = parse_diff_basis_source(content)
    return {
        "baseline_type": get_md_field_value(source, "Baseline type"),
        "baseline_reference": get_md_field_value(source, "Baseline reference"),
        "comparison_reference": get_md_field_value(source, "Comparison reference"),
        "normalized_baseline": (
            get_md_field_value(source, "Normalized baseline")
            or get_md_field_value(source, "Normalized baseline commit")
            or get_md_field_value(source, "Base commit")
        ),
        "normalized_comparison": (
            get_md_field_value(source, "Normalized comparison")
            or get_md_field_value(source, "Normalized comparison reference")
            or get_md_field_value(source, "Worktree branch")
        ),
        "normalized_diff_command": (
            get_md_field_value(source, "Normalized diff command")
            or get_md_field_value(source, "Diff command convention")
        ),
        "base_branch": get_md_field_value(source, "Base branch"),
        "worktree_branch": get_md_field_value(source, "Worktree branch"),
        "notes": get_md_field_value(source, "Diff basis notes") or get_md_field_value(source, "Notes"),
    }


def normalize_diff_basis(repo_root: Path, diff_basis: dict[str, str | None]) -> tuple[dict[str, object] | None, str | None]:
    baseline_type = normalize_baseline_type(diff_basis.get("baseline_type"))
    baseline_reference = trim_md_value(diff_basis.get("baseline_reference") or "")
    comparison_reference = normalize_comparison_reference(diff_basis.get("comparison_reference"))
    normalized_baseline = trim_md_value(diff_basis.get("normalized_baseline") or "")
    normalized_comparison = normalize_comparison_reference(diff_basis.get("normalized_comparison"))
    normalized_diff_command = trim_md_value(diff_basis.get("normalized_diff_command") or "")

    missing_fields = []
    if not baseline_type:
        missing_fields.append("Baseline type")
    if not baseline_reference:
        missing_fields.append("Baseline reference")
    if not comparison_reference:
        missing_fields.append("Comparison reference")
    if not normalized_baseline:
        missing_fields.append("Normalized baseline")
    if not normalized_comparison:
        missing_fields.append("Normalized comparison")
    if not normalized_diff_command:
        missing_fields.append("Normalized diff command")
    if missing_fields:
        return None, f"Diff basis is missing required field(s): {', '.join(missing_fields)}"

    comparison_git_ref = "HEAD" if normalized_comparison == "working-tree" else normalized_comparison
    if baseline_type == "merge-base derived":
        computed_baseline, error = run_git(repo_root, "merge-base", comparison_git_ref, baseline_reference)
        if error:
            return None, f"Unable to compute merge-base for diff basis: {error}"
    else:
        computed_baseline, error = run_git(repo_root, "rev-parse", "--verify", f"{baseline_reference}^{{commit}}")
        if error:
            return None, f"Unable to resolve baseline reference '{baseline_reference}': {error}"

    if normalized_baseline != computed_baseline:
        return None, (
            "Recorded Normalized baseline does not match the executable diff basis "
            f"({normalized_baseline} != {computed_baseline})"
        )

    if normalized_comparison == "working-tree":
        expected_command = f"git diff --name-only {computed_baseline}"
        tracked_diff_argv = ["diff", "--name-only", "-z", computed_baseline, "--"]
        untracked_files_argv = ["ls-files", "--others", "--exclude-standard", "-z"]
    else:
        computed_comparison, error = run_git(repo_root, "rev-parse", "--verify", f"{normalized_comparison}^{{commit}}")
        if error:
            return None, f"Unable to resolve comparison reference '{normalized_comparison}': {error}"
        expected_command = f"git diff --name-only {computed_baseline}..{computed_comparison}"
        tracked_diff_argv = ["diff", "--name-only", "-z", f"{computed_baseline}..{computed_comparison}", "--"]
        untracked_files_argv = None
        if normalized_comparison != computed_comparison:
            return None, (
                "Recorded Normalized comparison does not match the executable diff basis "
                f"({normalized_comparison} != {computed_comparison})"
            )

    if normalized_diff_command != expected_command:
        return None, (
            "Recorded Normalized diff command does not match the executable diff basis "
            f"({normalized_diff_command} != {expected_command})"
        )

    return {
        "baseline_type": baseline_type,
        "baseline_reference": baseline_reference,
        "comparison_reference": comparison_reference,
        "normalized_baseline": computed_baseline,
        "normalized_comparison": normalized_comparison,
        "normalized_diff_command": expected_command,
        "comparison_git_ref": comparison_git_ref,
        "tracked_diff_argv": tracked_diff_argv,
        "untracked_files_argv": untracked_files_argv,
    }, None


def normalize_repo_path(raw_path: str) -> str:
    return review_surface.normalize_path(raw_path)


def has_reparse_point(path: Path) -> bool:
    """Return whether an existing path component is a symlink or reparse point."""
    try:
        metadata = path.lstat()
    except OSError:
        return False
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag)


def validate_safe_repo_path(
    repo_root: Path,
    raw_path: str,
    *,
    label: str,
    require_regular_file: bool,
    allow_missing_leaf: bool = False,
) -> tuple[Path | None, str | None]:
    """Validate a lexical repo path without following any nested indirection."""
    try:
        normalized = normalize_repo_path(raw_path)
    except ValueError:
        return None, f"{label} must be a canonical repository-relative path without drive, absolute, empty, dot, or dot-dot components: {raw_path}"
    parts = Path(normalized).parts
    if any(part in {"", ".", ".."} for part in parts):
        return None, f"{label} contains a repository path escape: {raw_path}"
    candidate = repo_root.joinpath(*parts)
    cursor = repo_root
    for index, part in enumerate(parts):
        cursor = cursor / part
        is_leaf = index == len(parts) - 1
        try:
            os.lstat(cursor)
        except FileNotFoundError:
            if allow_missing_leaf and is_leaf:
                break
            if allow_missing_leaf and not is_leaf:
                continue
            return None, f"{label} does not exist: /{normalized}"
        except OSError as exc:
            return None, f"Unable to inspect {label} /{normalized}: {exc}"
        if has_reparse_point(cursor):
            return None, f"{label} contains a symlink or reparse point: /{normalized}"
    try:
        candidate.resolve(strict=not allow_missing_leaf).relative_to(repo_root.resolve(strict=True))
    except (FileNotFoundError, OSError, ValueError):
        return None, f"{label} must remain inside the repository: /{normalized}"
    if require_regular_file:
        try:
            leaf_metadata = os.lstat(candidate)
        except OSError as exc:
            return None, f"Unable to inspect {label} /{normalized}: {exc}"
        if (
            not stat.S_ISREG(leaf_metadata.st_mode)
            or has_reparse_point(candidate)
            or leaf_metadata.st_nlink != 1
        ):
            return None, f"{label} must resolve directly to a regular non-symlink, non-hardlink file: /{normalized}"
    return candidate, None


def read_regular_bytes(repo_root: Path, path: Path, *, label: str) -> tuple[bytes | None, str | None]:
    try:
        relative = str(path.relative_to(repo_root))
    except ValueError:
        return None, f"{label} must remain inside the repository"
    regular_path, path_error = validate_safe_repo_path(
        repo_root,
        relative,
        label=label,
        require_regular_file=True,
    )
    if path_error or regular_path is None:
        return None, path_error or f"{label} must be a canonical regular non-symlink file"
    try:
        return regular_path.read_bytes(), None
    except OSError as exc:
        return None, f"{label} must be readable: {exc}"


def read_regular_utf8(repo_root: Path, path: Path, *, label: str) -> tuple[str | None, str | None]:
    payload, read_error = read_regular_bytes(repo_root, path, label=label)
    if payload is None:
        return None, read_error
    try:
        return payload.decode("utf-8"), None
    except UnicodeDecodeError as exc:
        return None, f"{label} must be readable UTF-8: {exc}"


def get_stage_local_addenda_paths(run_dir: Path, artifact_name: str) -> list[Path]:
    addenda_dir = run_dir / "addenda"
    if not addenda_dir.exists():
        return []
    base_name = artifact_name[:-3] if artifact_name.endswith(".md") else artifact_name
    return sorted(addenda_dir.glob(f"{base_name}.addendum-*.md"))


def get_current_phase_addenda_paths(run_dir: Path, artifact_name: str) -> list[Path]:
    addenda_dir = run_dir / "addenda"
    if not addenda_dir.exists():
        return []
    base_name = artifact_name[:-3] if artifact_name.endswith(".md") else artifact_name
    matches = list(get_stage_local_addenda_paths(run_dir, artifact_name))
    matches.extend(sorted(addenda_dir.glob(f"{base_name}.upstream-gap.*.addendum-*.md")))
    unique: dict[str, Path] = {}
    for path in matches:
        unique[str(path.resolve())] = path
    return [unique[key] for key in sorted(unique)]


def auto_discover_addenda(run_dir: Path, run_id: str, artifact_path: str, upstream_artifacts: list[str]) -> list[str]:
    run_prefix = f".recursive/run/{run_id}/"
    discovered: list[str] = []

    for artifact in upstream_artifacts:
        normalized = normalize_repo_path(artifact)
        if not normalized.startswith(run_prefix):
            continue
        relative = normalized[len(run_prefix):]
        if relative.startswith("addenda/"):
            continue
        for addendum_path in get_stage_local_addenda_paths(run_dir, Path(relative).name):
            discovered.append(f"{run_prefix}addenda/{addendum_path.name}")

    normalized_artifact_path = normalize_repo_path(artifact_path)
    if normalized_artifact_path.startswith(run_prefix):
        artifact_name = Path(normalized_artifact_path[len(run_prefix):]).name
        for addendum_path in get_current_phase_addenda_paths(run_dir, artifact_name):
            discovered.append(f"{run_prefix}addenda/{addendum_path.name}")

    return sorted(set(discovered))


def auto_discover_skill_memory_refs(repo_root: Path, phase: str, role: str) -> list[str]:
    skills_router = ".recursive/memory/skills/SKILLS.md"
    discovered: list[str] = []
    if (repo_root / skills_router).exists():
        discovered.append(skills_router)

    skills_root = repo_root / ".recursive" / "memory" / "skills"
    if not skills_root.exists():
        return discovered

    query_tokens = set(re.findall(r"[a-z0-9]+", f"{phase} {role}".lower()))
    if not query_tokens:
        return discovered

    for path in sorted(skills_root.rglob("*.md")):
        relative = normalize_repo_path(str(path.relative_to(repo_root)))
        if relative == skills_router:
            continue
        stem_tokens = set(re.findall(r"[a-z0-9]+", path.stem.lower()))
        if query_tokens & stem_tokens:
            discovered.append(relative)
    return sorted(set(discovered))


def slugify(value: str) -> str:
    lowered = value.strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", lowered).strip("-")
    return slug or "bundle"


def render_list(title: str, values: list[str], *, indent: str = "- ") -> list[str]:
    if indent != "- ":
        raise ValueError("canonical review-bundle lists use '- ' indentation")
    return [title, *review_surface.render_markdown_list(values)]


def bundle_section_body(content: str, heading: str) -> str:
    match = re.search(
        rf"(?ms)^## {re.escape(heading)}\n(.*?)(?=^## |\Z)",
        content,
    )
    return match.group(1).strip("\n") if match else ""


def validate_rendered_bundle(
    content: str,
    *,
    expected_snapshot: dict[str, object],
    expected_lists: dict[str, list[str]],
) -> list[str]:
    """Validate the complete rendered artifact before its exclusive write."""
    issues: list[str] = []
    if "\r" in content or not content.endswith("\n"):
        issues.append("rendered bundle must use canonical LF endings and end with LF")
    headings = re.findall(r"(?m)^## (.+?)$", content)
    if headings != BUNDLE_SECTION_ORDER:
        issues.append("rendered bundle top-level sections do not match the exact canonical order")

    header, separator, _remainder = content.partition("\n\n")
    if not separator:
        issues.append("rendered bundle is missing the header/section boundary")
    header_matches = [
        re.fullmatch(r"([A-Za-z][A-Za-z0-9 ]*):\s*(.+)", line)
        for line in header.splitlines()
    ]
    if any(match is None for match in header_matches):
        issues.append("rendered bundle header contains malformed metadata")
    else:
        header_names = [match.group(1) for match in header_matches if match is not None]
        if header_names != review_ledger.BUNDLE_HEADER_FIELDS:
            issues.append("rendered bundle header fields do not match the exact canonical order")

    snapshot, snapshot_issues = review_surface.parse(content)
    issues.extend(snapshot_issues)
    if snapshot is not None and snapshot != expected_snapshot:
        issues.append("rendered Reviewed Surface Snapshot differs from the captured source snapshot")

    for heading, expected_values in expected_lists.items():
        body = bundle_section_body(content, heading)
        try:
            actual_values = review_surface.parse_markdown_list(body)
        except ValueError as exc:
            issues.append(f"rendered ## {heading} is not a canonical JSON-atom list: {exc}")
            continue
        if actual_values != expected_values:
            issues.append(f"rendered ## {heading} differs from its source values")

    if snapshot is not None:
        snapshot_changed = [str(record["path"]) for record in snapshot.get("changed", [])]
        if expected_lists.get("Changed Files Reviewed") != snapshot_changed:
            issues.append("rendered Changed Files Reviewed is not bound to the source snapshot")
    return sorted(set(issues))


def ensure_safe_directory_chain(repo_root: Path, directory: Path, *, label: str) -> str | None:
    try:
        relative = directory.relative_to(repo_root)
    except ValueError:
        return f"{label} must remain inside the repository"
    cursor = repo_root
    for part in relative.parts:
        cursor = cursor / part
        try:
            cursor.mkdir()
        except FileExistsError:
            pass
        except OSError as exc:
            return f"Unable to create {label}: {exc}"
        try:
            metadata = cursor.lstat()
        except OSError as exc:
            return f"Unable to inspect {label}: {exc}"
        if not stat.S_ISDIR(metadata.st_mode) or has_reparse_point(cursor):
            return f"{label} contains a symlink, reparse point, or non-directory component"
    return None


def write_exclusive_bundle(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o644)
    opened: os.stat_result | None = None
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise OSError("exclusive bundle target is not a unique regular file")
        view = memoryview(payload)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("short write while persisting review bundle")
            view = view[written:]
        os.fsync(descriptor)
    except BaseException:
        try:
            current = path.lstat()
            if opened is not None and (current.st_dev, current.st_ino) == (opened.st_dev, opened.st_ino):
                path.unlink()
        except OSError:
            pass
        raise
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a canonical recursive-mode review bundle.")
    parser.add_argument("--repo-root", default=".", help="Repository root path.")
    parser.add_argument("--run-id", required=True, help="Run ID under .recursive/run/.")
    parser.add_argument("--phase", required=True, help="Phase name for the bundle, e.g. '03.5 Code Review'.")
    parser.add_argument("--role", required=True, help="Delegated role, e.g. analyst, code-reviewer, tester.")
    parser.add_argument("--artifact-path", required=True, help="Repo-relative artifact path the review is for.")
    parser.add_argument("--upstream-artifact", action="append", default=[], help="Repo-relative upstream artifact path. Repeat as needed.")
    parser.add_argument("--addendum", action="append", default=[], help="Repo-relative addendum path. Repeat as needed.")
    parser.add_argument("--prior-ref", action="append", default=[], help="Repo-relative prior run or recursive memory path. Repeat as needed.")
    parser.add_argument("--control-doc", action="append", default=[], help="Repo-relative control-plane doc path. Repeat as needed.")
    parser.add_argument("--code-ref", action="append", default=[], help="Repo-relative code file to inspect. Repeat as needed.")
    parser.add_argument("--evidence-ref", action="append", default=[], help="Repo-relative evidence artifact path. Repeat as needed.")
    parser.add_argument("--audit-question", action="append", default=[], help="Audit or review question. Repeat as needed.")
    parser.add_argument("--review-id", default="", help="Stable kebab-case review identifier used for the finding ledger.")
    parser.add_argument("--pass", dest="pass_id", required=True, help="Positive zero-padded review pass ID.")
    parser.add_argument("--routing-config-path", default="", help="Repo-relative routing policy path for routed delegation.")
    parser.add_argument("--routing-discovery-path", default="", help="Repo-relative routing discovery path for routed delegation.")
    parser.add_argument("--routed-cli", default="", help="Resolved routed CLI id if applicable.")
    parser.add_argument("--routed-model", default="", help="Resolved routed model id if applicable.")
    parser.add_argument("--no-auto-addenda", action="store_true", help="Disable automatic addenda discovery for upstream artifacts and the current phase.")
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    run_id = args.run_id
    if not phase_rules.is_canonical_run_id(run_id):
        print(f"[FAIL] {phase_rules.CANONICAL_RUN_ID_ERROR}")
        return 1
    run_root = repo_root / ".recursive" / "run"
    run_dir = run_root / run_id
    checked_run_dir, path_error = validate_safe_repo_path(
        repo_root,
        f".recursive/run/{run_id}",
        label="Run directory",
        require_regular_file=False,
    )
    if path_error or checked_run_dir is None or not checked_run_dir.is_dir():
        print(f"[FAIL] {path_error or 'Run directory must be a real directory'}")
        return 1
    run_dir = checked_run_dir
    worktree_path, path_error = validate_safe_repo_path(
        repo_root,
        f".recursive/run/{run_id}/00-worktree.md",
        label="Diff basis artifact",
        require_regular_file=True,
    )
    if path_error:
        print(f"[FAIL] {path_error}")
        return 1
    if worktree_path is None:
        print("[FAIL] Diff basis artifact must be a canonical regular non-symlink file")
        return 1
    worktree_content, read_error = read_regular_utf8(repo_root, worktree_path, label="Diff basis artifact")
    if worktree_content is None:
        print(f"[FAIL] {read_error}")
        return 1
    diff_basis = get_run_diff_basis(worktree_content)
    normalized_diff_basis, diff_basis_error = normalize_diff_basis(repo_root, diff_basis)
    if diff_basis_error:
        print(f"[FAIL] {diff_basis_error}")
        return 1
    try:
        artifact_path = normalize_repo_path(args.artifact_path)
        upstream_artifacts = [normalize_repo_path(item) for item in args.upstream_artifact]
        addenda = [normalize_repo_path(item) for item in args.addendum]
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    artifact_fs_path, path_error = validate_safe_repo_path(
        repo_root,
        args.artifact_path,
        label="Artifact path",
        require_regular_file=True,
    )
    if path_error:
        print(f"[FAIL] {path_error}")
        return 1
    try:
        if not args.no_auto_addenda:
            addenda.extend(auto_discover_addenda(run_dir, run_dir.name, artifact_path, upstream_artifacts))
        addenda = sorted(set(addenda))
        prior_refs = sorted(set(normalize_repo_path(item) for item in args.prior_ref if item.strip()))
        prior_refs.extend(auto_discover_skill_memory_refs(repo_root, args.phase, args.role))
        prior_refs = sorted(set(prior_refs))
        control_docs = [normalize_repo_path(item) for item in args.control_doc]
        code_refs = [normalize_repo_path(item) for item in args.code_ref]
        evidence_refs = [normalize_repo_path(item) for item in args.evidence_ref]
        routing_config_path = normalize_repo_path(args.routing_config_path) if args.routing_config_path.strip() else ""
        routing_discovery_path = normalize_repo_path(args.routing_discovery_path) if args.routing_discovery_path.strip() else ""
    except ValueError as exc:
        print(f"[FAIL] {exc}")
        return 1
    audit_questions = [item for item in args.audit_question if item.strip()]
    referenced_paths = [
        ("Upstream artifact", item) for item in upstream_artifacts
    ] + [
        ("Addendum", item) for item in addenda
    ] + [
        ("Prior reference", item) for item in prior_refs
    ] + [
        ("Control document", item) for item in control_docs
    ] + [
        ("Code reference", item) for item in code_refs
    ] + [
        ("Evidence reference", item) for item in evidence_refs
    ]
    if routing_config_path:
        referenced_paths.append(("Routing config", routing_config_path))
    if routing_discovery_path:
        referenced_paths.append(("Routing discovery", routing_discovery_path))
    for label, reference in referenced_paths:
        _checked_reference, path_error = validate_safe_repo_path(
            repo_root,
            reference,
            label=label,
            require_regular_file=True,
        )
        if path_error:
            print(f"[FAIL] {path_error}")
            return 1
    try:
        surface_snapshot = review_surface.capture(
            repo_root,
            run_id=run_dir.name,
            baseline=normalized_diff_basis["normalized_baseline"],
            comparison=normalized_diff_basis["normalized_comparison"],
            references=[
                *upstream_artifacts,
                *addenda,
                *prior_refs,
                *control_docs,
                *code_refs,
                *evidence_refs,
                *([routing_config_path] if routing_config_path else []),
                *([routing_discovery_path] if routing_discovery_path else []),
            ],
        )
    except (OSError, ValueError) as exc:
        print(f"[FAIL] Unable to snapshot reviewed surface: {exc}")
        return 1
    filtered_changed_files = [record["path"] for record in surface_snapshot["changed"]]
    artifact_file = Path(artifact_path).name
    registered_phase_key = phase_rules.audited_phase_key(artifact_file)
    if registered_phase_key is None:
        print(f"[FAIL] artifact is not in the audited registry: {artifact_file}")
        return 1
    if phase_rules.audited_phase_key_from_label(args.phase) != registered_phase_key:
        print(f"[FAIL] phase label does not match audited artifact: {args.phase.strip()} != {artifact_file}")
        return 1
    if artifact_path != f".recursive/run/{run_dir.name}/{artifact_file}":
        print(f"[FAIL] Artifact Path must be the canonical receipt for run {run_dir.name}: /{artifact_path}")
        return 1
    review_id = args.review_id.strip() or slugify(f"{args.phase}-{args.role}")
    ledger_rel = ""
    pass_id = args.pass_id.strip()
    if not re.fullmatch(r"[0-9]{4}", pass_id) or pass_id == "0000":
        print("[FAIL] review bundle requires --pass as a positive zero-padded four-digit ID.")
        return 1
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", review_id):
        print("[FAIL] Review ID must be a kebab-case identifier.")
        return 1
    selected_phase_key = registered_phase_key
    ledger_rel = f".recursive/run/{run_dir.name}/evidence/reviews/{selected_phase_key}/{review_id}/ledger.md"
    duplicates = [
        path
        for path in run_dir.glob(f"evidence/reviews/*/{review_id}/ledger.md")
        if normalize_repo_path(str(path.relative_to(repo_root))) != ledger_rel
    ]
    if duplicates:
        print(f"[FAIL] Review ID must be globally unique within the run: {review_id}")
        return 1
    bundle_duplicates = [
        path
        for path in run_dir.glob(f"evidence/review-bundles/*/{review_id}")
        if path.is_dir() and path.parent.name != selected_phase_key
    ]
    if bundle_duplicates:
        print(f"[FAIL] Review ID must be globally unique within the run: {review_id}")
        return 1

    bundle_path = run_dir / "evidence/review-bundles" / registered_phase_key / review_id / f"{pass_id}.md"
    bundle_rel = normalize_repo_path(str(bundle_path.relative_to(repo_root)))
    _checked_bundle_path, path_error = validate_safe_repo_path(
        repo_root,
        bundle_rel,
        label="Immutable review bundle path",
        require_regular_file=False,
        allow_missing_leaf=True,
    )
    if path_error:
        print(f"[FAIL] {path_error}")
        return 1
    if artifact_fs_path is None:
        print("[FAIL] Artifact path must be a canonical regular non-symlink file")
        return 1
    artifact_bytes, read_error = read_regular_bytes(repo_root, artifact_fs_path, label="Artifact path")
    if artifact_bytes is None:
        print(f"[FAIL] {read_error}")
        return 1
    try:
        artifact_content = artifact_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        print(f"[FAIL] Artifact path must be readable UTF-8: {exc}")
        return 1
    artifact_content_hash = hashlib.sha256(artifact_bytes).hexdigest()

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines: list[str] = [
        f"Run: `/.recursive/run/{run_dir.name}/`",
        f"Phase: `{artifact_file}`",
        f"Phase Key: `{registered_phase_key}`",
        f"Review ID: `{review_id}`",
        f"Pass: `{pass_id}`",
        f"Role: `{args.role.strip()}`",
        f"Bundle Path: `/{bundle_rel}`",
        f"Artifact Path: `/{artifact_path}`",
        f"Artifact Content Hash: `{artifact_content_hash}`",
    ]
    lines.extend([
        f"Audit Payload Hash: `{review_ledger.audit_payload_hash(artifact_content)}`",
        f"Audit Payload Profile: `{review_ledger.AUDIT_PAYLOAD_PROFILE}`",
        f"Review Ledger Path: `/{ledger_rel}`",
    ])
    lines.extend([
        f"GeneratedAt: `{generated_at}`",
        "",
        "## Bundle Scope",
        "- Canonical delegated review bundle for recursive-mode audit/review work.",
        "- Regenerate this bundle after any change to the reviewed diff, artifact, or evidence basis.",
        "",
        "## Routing",
        f"- Routed CLI: `{args.routed_cli.strip() or 'none'}`",
        f"- Routed Model: `{args.routed_model.strip() or 'none'}`",
        f"- Routing Config Path: `{('/' + routing_config_path) if routing_config_path else 'none'}`",
        f"- Routing Discovery Path: `{('/' + routing_discovery_path) if routing_discovery_path else 'none'}`",
        "",
        "## Diff Basis",
        f"- Baseline type: `{normalized_diff_basis['baseline_type']}`",
        f"- Baseline reference: `{diff_basis['baseline_reference'] or 'UNKNOWN'}`",
        f"- Comparison reference: `{normalized_diff_basis['comparison_reference']}`",
        f"- Normalized baseline: `{normalized_diff_basis['normalized_baseline']}`",
        f"- Normalized comparison: `{normalized_diff_basis['normalized_comparison']}`",
        f"- Normalized diff command: `{normalized_diff_basis['normalized_diff_command']}`",
        f"- Tracked diff argv: `{json.dumps(normalized_diff_basis['tracked_diff_argv'], separators=(',', ':'))}`",
        (
            f"- Untracked files argv: `{json.dumps(normalized_diff_basis['untracked_files_argv'], separators=(',', ':'))}`"
            if normalized_diff_basis["untracked_files_argv"] is not None
            else "- Untracked files argv: none"
        ),
        "",
    ])
    lines.extend(render_list("## Changed Files Reviewed", filtered_changed_files))
    lines.append("")
    lines.extend(review_surface.render(surface_snapshot))
    lines.append("")
    lines.extend(render_list("## Upstream Artifacts To Re-read", upstream_artifacts))
    lines.append("")
    lines.extend(render_list("## Relevant Addenda", addenda))
    lines.append("")
    lines.extend(render_list("## Prior Recursive Evidence", prior_refs))
    lines.append("")
    lines.extend(render_list("## Control-Plane Docs", control_docs))
    lines.append("")
    lines.extend(render_list("## Targeted Code References", code_refs))
    lines.append("")
    lines.extend(render_list("## Evidence References", evidence_refs))
    lines.append("")
    lines.extend(render_list("## Audit Questions", audit_questions))
    lines.append("")
    lines.extend([
        "## Required Output",
        "- Follow `/.agents/skills/recursive-review/references/finding-protocol.md`.",
        "- Use exactly these top-level sections in order: `## Review Scope`, `## Findings`, `## Verdict`.",
        "- Put every technical issue under `## Findings` as an append-only stable `F-*` record; emit no finding-bearing free prose.",
        "- Create new findings with `Disposition: open`; a reviewer or repair agent cannot assign a terminal disposition.",
        "- A repair agent records only structured claims; the controller verifies each row against the repository before closure.",
        f"- Read and update the canonical ledger at `/{ledger_rel}`.",
        "",
    ])
    lines.append("## Notes")
    lines.append(
        "- Review output is invalid if it does not cite the upstream artifacts, diff basis, changed files, and whole-ledger verdict."
    )
    lines.append("- If this bundle is incomplete, reject delegation and perform the audit as self-audit.")
    lines.append("")

    bundle_content = "\n".join(lines)
    expected_lists = {
        "Changed Files Reviewed": filtered_changed_files,
        "Upstream Artifacts To Re-read": upstream_artifacts,
        "Relevant Addenda": addenda,
        "Prior Recursive Evidence": prior_refs,
        "Control-Plane Docs": control_docs,
        "Targeted Code References": code_refs,
        "Evidence References": evidence_refs,
        "Audit Questions": audit_questions,
    }
    render_issues = validate_rendered_bundle(
        bundle_content,
        expected_snapshot=surface_snapshot,
        expected_lists=expected_lists,
    )
    if render_issues:
        print("[FAIL] Refusing to persist an invalid rendered review bundle:")
        for issue in render_issues:
            print(f"- {issue}")
        return 1
    try:
        bundle_payload = bundle_content.encode("utf-8")
    except UnicodeEncodeError as exc:
        print(f"[FAIL] Rendered review bundle is not canonical UTF-8: {exc}")
        return 1
    directory_error = ensure_safe_directory_chain(
        repo_root,
        bundle_path.parent,
        label="Immutable review bundle directory",
    )
    if directory_error:
        print(f"[FAIL] {directory_error}")
        return 1
    _checked_bundle_path, path_error = validate_safe_repo_path(
        repo_root,
        bundle_rel,
        label="Immutable review bundle path",
        require_regular_file=False,
        allow_missing_leaf=True,
    )
    if path_error:
        print(f"[FAIL] {path_error}")
        return 1
    try:
        write_exclusive_bundle(bundle_path, bundle_payload)
    except FileExistsError:
        print(f"[FAIL] Refusing to overwrite immutable review bundle: /{bundle_rel}")
        return 1
    except OSError as exc:
        print(f"[FAIL] Unable to persist immutable review bundle: /{bundle_rel}: {exc}")
        return 1

    print(f"[OK] Wrote review bundle: /{bundle_rel}")
    print(f"Changed files: {len(filtered_changed_files)}")
    print(f"Role: {args.role.strip()}")
    print(f"Phase: {args.phase.strip()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
