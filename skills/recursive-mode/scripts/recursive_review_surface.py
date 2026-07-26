#!/usr/bin/env python3
"""Deterministic reviewed-surface snapshots for review bundles."""

from __future__ import annotations

import hashlib
import json
import ntpath
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
MARKDOWN_ATOM_PREFIX = "json:"


def _missing_record(path: str) -> dict[str, str]:
    return {"path": path, "state": "missing", "mode": "none", "sha256": "none"}


def _is_reparse_point(metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def render_markdown_atom(value: str) -> str:
    """Render one arbitrary string as a canonical, single-line Markdown atom."""
    if not isinstance(value, str):
        raise ValueError("Markdown atom value must be a string")
    return MARKDOWN_ATOM_PREFIX + json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
    )


def parse_markdown_atom(value: str) -> str:
    """Decode one canonical atom without permitting raw Markdown fallback."""
    if not value.startswith(MARKDOWN_ATOM_PREFIX):
        raise ValueError(f"Markdown atom must start with {MARKDOWN_ATOM_PREFIX}")
    payload = value[len(MARKDOWN_ATOM_PREFIX):]
    try:
        decoded = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Markdown atom contains invalid JSON: {exc}") from exc
    if not isinstance(decoded, str) or render_markdown_atom(decoded) != value:
        raise ValueError("Markdown atom must be a canonical JSON string")
    return decoded


def render_markdown_list(values: list[str]) -> list[str]:
    """Render a strict list; ``none`` is reserved for the empty-list sentinel."""
    if not values:
        return ["- none"]
    return [f"- {render_markdown_atom(value)}" for value in values]


def parse_markdown_list(body: str) -> list[str]:
    """Parse the exact output of :func:`render_markdown_list`."""
    lines = body.splitlines()
    if lines == ["- none"]:
        return []
    if not lines or any(not line.startswith("- ") for line in lines):
        raise ValueError("Markdown list must contain exact '- json:<JSON string>' items")
    if any(line == "- none" for line in lines):
        raise ValueError("Markdown list cannot mix the empty sentinel with values")
    return [parse_markdown_atom(line[2:]) for line in lines]


def _validate_canonical_path(value: str) -> str:
    if (
        not value
        or value.startswith("/")
        or ntpath.splitdrive(value)[0]
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise ValueError(f"invalid repository path or path escape: {value}")
    return value


def normalize_path(value: str) -> str:
    """Normalize a user/document path, without rewriting POSIX backslashes."""
    candidate = value.strip()
    if os.name == "nt":
        candidate = candidate.replace("\\", "/")
    if candidate.startswith("/") and not candidate.startswith("//"):
        candidate = candidate[1:]
    return _validate_canonical_path(candidate)


def git_path(value: str) -> str:
    """Validate one lossless path emitted by a NUL-delimited Git command."""
    return _validate_canonical_path(value)


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
    result: set[str] = set()
    for raw_path in tracked + untracked:
        path = git_path(raw_path)
        if not path.startswith(run_prefix) and not is_transient(path):
            result.add(path)
    return sorted(result)


def path_record(repo_root: Path, raw_path: str, *, from_git: bool = False) -> dict[str, str]:
    path = git_path(raw_path) if from_git else normalize_path(raw_path)
    target = repo_root
    metadata: os.stat_result | None = None
    parts = path.split("/")
    for index, part in enumerate(parts):
        target = target / part
        try:
            metadata = target.lstat()
        except (FileNotFoundError, NotADirectoryError):
            return _missing_record(path)
        except OSError as exc:
            raise ValueError(f"unable to inspect reviewed surface path {path}: {exc}") from exc
        if index != len(parts) - 1 and (
            not stat.S_ISDIR(metadata.st_mode)
            or stat.S_ISLNK(metadata.st_mode)
            or _is_reparse_point(metadata)
        ):
            # Git addresses worktree paths lexically. An indirection or non-directory
            # ancestor means the indexed child is absent; following it could hash an
            # unrelated in-repository (or external) substitute.
            return _missing_record(path)
    if metadata is None:
        return _missing_record(path)
    mode = format(metadata.st_mode & 0o177777, "06o")
    if stat.S_ISLNK(metadata.st_mode):
        try:
            payload = os.readlink(target).encode("utf-8", errors="surrogateescape")
        except OSError as exc:
            raise ValueError(f"unable to read reviewed surface symlink {path}: {exc}") from exc
        state = "symlink"
    elif _is_reparse_point(metadata):
        # Never follow an unmodelled Windows reparse leaf. Git-native symlinks are
        # handled above; other reparse objects remain opaque worktree objects.
        payload = b""
        state = "other"
    elif stat.S_ISREG(metadata.st_mode):
        if metadata.st_nlink != 1:
            raise ValueError(f"reviewed surface file must not be hard-linked: {path}")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor: int | None = None
        try:
            descriptor = os.open(target, flags)
            opened = os.fstat(descriptor)
            if (
                not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
            ):
                raise ValueError(f"reviewed surface file changed during capture: {path}")
            with os.fdopen(descriptor, "rb", closefd=True) as handle:
                descriptor = None
                payload = handle.read()
        except OSError as exc:
            raise ValueError(f"unable to read reviewed surface file {path}: {exc}") from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
        state = "file"
    elif stat.S_ISDIR(metadata.st_mode):
        payload = b""
        state = "directory"
    else:
        payload = b""
        state = "other"
    return {"path": path, "state": state, "mode": mode, "sha256": hashlib.sha256(payload).hexdigest()}


def reference_record(repo_root: Path, raw_path: str) -> dict[str, str]:
    path = normalize_path(raw_path)
    cursor = repo_root
    for part in path.split("/"):
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except OSError as exc:
            raise ValueError(f"explicit reviewed reference is not a readable regular file: {path}: {exc}") from exc
        attributes = getattr(metadata, "st_file_attributes", 0)
        reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        if stat.S_ISLNK(metadata.st_mode) or bool(attributes & reparse_flag):
            raise ValueError(f"explicit reviewed reference contains symlink or reparse indirection: {path}")
    if stat.S_ISREG(metadata.st_mode) and metadata.st_nlink != 1:
        raise ValueError(f"explicit reviewed reference must not be hard-linked: {path}")
    record = path_record(repo_root, path)
    if record["state"] != "file":
        raise ValueError(
            f"explicit reviewed reference must resolve directly to a regular file: {record['path']} "
            f"(found {record['state']})"
        )
    return record


def git_path_record(repo_root: Path, commit: str, raw_path: str) -> dict[str, str]:
    path = git_path(raw_path)
    rows = _git_z(repo_root, "--literal-pathspecs", "ls-tree", "-z", commit, "--", path)
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
            path_record(repo_root, path, from_git=True)
            if comparison == "working-tree"
            else git_path_record(repo_root, comparison, path)
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
                if git_path(record["path"]) != record["path"]:
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
