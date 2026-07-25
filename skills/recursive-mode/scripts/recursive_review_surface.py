#!/usr/bin/env python3
"""Deterministic reviewed-surface snapshots for review bundles."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
from pathlib import Path


PROFILE = "recursive-review-surface-v1"
TRANSIENT_DIRS = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".hypothesis", ".tox", ".nox"}
TRANSIENT_NAMES = {".ds_store", "thumbs.db"}
TRANSIENT_SUFFIXES = (".pyc", ".pyo", ".pyd")
SNAPSHOT_KEYS = {"profile", "run_id", "baseline", "comparison", "changed", "references"}
RECORD_KEYS = {"path", "state", "mode", "sha256"}


def normalize_path(value: str) -> str:
    candidate = value.replace("\\", "/").strip().lstrip("/")
    if not candidate or candidate.startswith("../") or "/../" in candidate or candidate == "..":
        raise ValueError(f"invalid repository path: {value}")
    return candidate


def is_transient(path: str) -> bool:
    parts = Path(path).parts
    name = Path(path).name.lower()
    return any(part in TRANSIENT_DIRS for part in parts) or name in TRANSIENT_NAMES or name.endswith(TRANSIENT_SUFFIXES)


def _git_z(repo_root: Path, *args: str) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(repo_root), *args],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace").strip() or "git command failed"
        raise ValueError(message)
    return [item.decode("utf-8", errors="surrogateescape") for item in result.stdout.split(b"\0") if item]


def changed_paths(repo_root: Path, baseline: str, comparison: str, run_id: str) -> list[str]:
    if not re.fullmatch(r"[0-9a-f]{40}", baseline):
        raise ValueError("reviewed surface baseline must be a full lowercase commit hash")
    if comparison != "working-tree" and not re.fullmatch(r"[0-9a-f]{40}", comparison):
        raise ValueError("reviewed surface comparison must be working-tree or a full lowercase commit hash")
    diff_range = baseline if comparison == "working-tree" else f"{baseline}..{comparison}"
    tracked = _git_z(repo_root, "diff", "--name-only", "-z", diff_range, "--")
    untracked = _git_z(repo_root, "ls-files", "--others", "--exclude-standard", "-z") if comparison == "working-tree" else []
    run_prefix = f".recursive/run/{run_id}/"
    result = {
        normalize_path(path)
        for path in tracked + untracked
        if not normalize_path(path).startswith(run_prefix) and not is_transient(normalize_path(path))
    }
    return sorted(result)


def path_record(repo_root: Path, raw_path: str) -> dict[str, str]:
    path = normalize_path(raw_path)
    target = repo_root / path
    try:
        target.parent.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise ValueError(f"reviewed surface path escapes repository: {path}") from exc
    try:
        metadata = target.lstat()
    except FileNotFoundError:
        return {"path": path, "state": "missing", "mode": "none", "sha256": "none"}
    mode = format(metadata.st_mode & 0o177777, "06o")
    if stat.S_ISLNK(metadata.st_mode):
        payload = os.readlink(target).encode("utf-8", errors="surrogateescape")
        state = "symlink"
    elif stat.S_ISREG(metadata.st_mode):
        payload = target.read_bytes()
        state = "file"
    elif stat.S_ISDIR(metadata.st_mode):
        payload = b""
        state = "directory"
    else:
        payload = b""
        state = "other"
    return {"path": path, "state": state, "mode": mode, "sha256": hashlib.sha256(payload).hexdigest()}


def reference_record(repo_root: Path, raw_path: str) -> dict[str, str]:
    record = path_record(repo_root, raw_path)
    if record["state"] != "file":
        raise ValueError(
            f"explicit reviewed reference must resolve directly to a regular file: {record['path']} "
            f"(found {record['state']})"
        )
    return record


def git_path_record(repo_root: Path, commit: str, raw_path: str) -> dict[str, str]:
    path = normalize_path(raw_path)
    rows = _git_z(repo_root, "ls-tree", "-z", commit, "--", path)
    if not rows:
        return {"path": path, "state": "missing", "mode": "none", "sha256": "none"}
    metadata, separator, listed_path = rows[0].partition("\t")
    parts = metadata.split()
    if not separator or listed_path != path or len(parts) != 3:
        raise ValueError(f"unable to parse Git state for reviewed path: {path}")
    mode, object_type, object_id = parts
    if object_type == "blob":
        result = subprocess.run(
            ["git", "-C", str(repo_root), "cat-file", "blob", object_id],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            raise ValueError(f"unable to read Git blob for reviewed path: {path}")
        state = "symlink" if mode == "120000" else "file"
        return {"path": path, "state": state, "mode": mode, "sha256": hashlib.sha256(result.stdout).hexdigest()}
    return {"path": path, "state": "directory" if object_type == "tree" else "other", "mode": mode, "sha256": hashlib.sha256(b"").hexdigest()}


def capture(
    repo_root: Path,
    *,
    run_id: str,
    baseline: str,
    comparison: str,
    references: list[str],
) -> dict[str, object]:
    changed = changed_paths(repo_root, baseline, comparison, run_id)
    normalized_refs = sorted({normalize_path(path) for path in references if path.strip()})
    return {
        "profile": PROFILE,
        "run_id": run_id,
        "baseline": baseline,
        "comparison": comparison,
        "changed": [
            path_record(repo_root, path) if comparison == "working-tree" else git_path_record(repo_root, comparison, path)
            for path in changed
        ],
        "references": [reference_record(repo_root, path) for path in normalized_refs],
    }


def render(snapshot: dict[str, object]) -> list[str]:
    return [
        "## Reviewed Surface Snapshot",
        "```json",
        json.dumps(snapshot, ensure_ascii=True, sort_keys=True, separators=(",", ":")),
        "```",
    ]


def parse(bundle_content: str) -> tuple[dict[str, object] | None, list[str]]:
    matches = re.findall(
        r"(?ms)^## Reviewed Surface Snapshot\s*\n```json\s*\n(.*?)\n```\s*(?=^## |\Z)",
        bundle_content.replace("\r\n", "\n").replace("\r", "\n"),
    )
    if len(matches) != 1:
        return None, [f"bundle must contain exactly one Reviewed Surface Snapshot; found {len(matches)}"]
    try:
        snapshot = json.loads(matches[0])
    except json.JSONDecodeError as exc:
        return None, [f"reviewed surface snapshot is invalid JSON: {exc}"]
    issues: list[str] = []
    if not isinstance(snapshot, dict) or set(snapshot) != SNAPSHOT_KEYS:
        return None, ["reviewed surface snapshot has invalid top-level fields"]
    if snapshot.get("profile") != PROFILE:
        issues.append("reviewed surface snapshot profile is unsupported")
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", str(snapshot.get("run_id", ""))):
        issues.append("reviewed surface run_id must be kebab-case")
    if not re.fullmatch(r"[0-9a-f]{40}", str(snapshot.get("baseline", ""))):
        issues.append("reviewed surface baseline must be a full lowercase commit hash")
    comparison = str(snapshot.get("comparison", ""))
    if comparison != "working-tree" and not re.fullmatch(r"[0-9a-f]{40}", comparison):
        issues.append("reviewed surface comparison must be working-tree or a full lowercase commit hash")
    for field in ("changed", "references"):
        records = snapshot.get(field)
        if not isinstance(records, list):
            issues.append(f"reviewed surface {field} must be a list")
            continue
        paths: list[str] = []
        for record in records:
            if not isinstance(record, dict) or set(record) != RECORD_KEYS or not all(isinstance(value, str) for value in record.values()):
                issues.append(f"reviewed surface {field} contains an invalid record")
                continue
            try:
                if normalize_path(record["path"]) != record["path"]:
                    issues.append(f"reviewed surface {field} contains a noncanonical path")
            except ValueError:
                issues.append(f"reviewed surface {field} contains an invalid path")
            if record["state"] not in {"file", "symlink", "directory", "other", "missing"}:
                issues.append(f"reviewed surface {field} contains an invalid state")
            if field == "references" and record["state"] != "file":
                issues.append("reviewed surface references must resolve directly to regular files")
            if record["state"] == "missing":
                if record["mode"] != "none" or record["sha256"] != "none":
                    issues.append(f"reviewed surface {field} missing record has content state")
            elif not re.fullmatch(r"[0-7]{6}", record["mode"]) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"]):
                issues.append(f"reviewed surface {field} contains invalid mode or hash")
            paths.append(record["path"])
        if paths != sorted(set(paths)):
            issues.append(f"reviewed surface {field} paths must be sorted and unique")
    return snapshot, issues


def validate(repo_root: Path, bundle_content: str, *, current: bool) -> list[str]:
    snapshot, issues = parse(bundle_content)
    if snapshot is None or issues or not current:
        return issues
    try:
        actual = capture(
            repo_root,
            run_id=str(snapshot["run_id"]),
            baseline=str(snapshot["baseline"]),
            comparison=str(snapshot["comparison"]),
            references=[record["path"] for record in snapshot["references"]],
        )
    except (OSError, ValueError) as exc:
        return [f"unable to recompute current reviewed surface: {exc}"]
    return [] if actual == snapshot else ["current reviewed surface differs from the immutable bundle snapshot"]
