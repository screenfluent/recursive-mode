#!/usr/bin/env python3
"""
Companion extractor for recursive-training prompt evaluation.

The training scripts build extraction prompts and hand them to this script.
Supported evaluation modes (first match wins):

1. --response-file PATH — print the file contents (agent/offline JSON)
2. Sibling <prompt-file>.response.json — same as response-file when present
3. RECURSIVE_TRAINING_EXTRACTOR_CMD — shell command; `{prompt_file}` and
   `{repo_root}` are substituted; stdout is the extraction result
4. Otherwise exit 2 (unavailable)

Exit codes:
  0: extraction text printed to stdout
  1: invalid arguments / missing prompt
  2: no extractor wired
"""

from __future__ import annotations

import argparse
import os
import shlex
import subprocess
import sys
from pathlib import Path


def _run_external_command(command: str, repo_root: Path, prompt_path: Path) -> int:
    rendered = command.format(prompt_file=str(prompt_path), repo_root=str(repo_root))
    # Windows-friendly: run via shell when the command is a single string template
    result = subprocess.run(
        rendered if os.name == "nt" else shlex.split(rendered),
        check=False,
        capture_output=True,
        text=True,
        shell=(os.name == "nt"),
    )
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "extractor command failed").strip()
        print(err, file=sys.stderr)
        return result.returncode if result.returncode != 2 else 1
    sys.stdout.write(result.stdout)
    if result.stdout and not result.stdout.endswith("\n"):
        sys.stdout.write("\n")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Companion extractor for recursive-training")
    parser.add_argument("--repo-root", required=True, help="Repository root path")
    parser.add_argument("--prompt-file", required=True, help="Path to the prompt file to evaluate")
    parser.add_argument(
        "--response-file",
        default="",
        help="Optional precomputed JSON/text response to emit instead of calling a model",
    )
    args = parser.parse_args()

    repo_root = Path(args.repo_root).resolve()
    prompt_path = Path(args.prompt_file).resolve()
    if not prompt_path.exists():
        print("ERROR: Prompt file not found for recursive-training extraction.", file=sys.stderr)
        return 1

    response_path = Path(args.response_file).resolve() if args.response_file.strip() else None
    if response_path is None:
        sibling = prompt_path.with_suffix(prompt_path.suffix + ".response.json")
        if not sibling.exists():
            sibling = Path(str(prompt_path) + ".response.json")
        if sibling.exists():
            response_path = sibling

    if response_path is not None:
        if not response_path.exists():
            print(f"ERROR: Response file not found: {response_path}", file=sys.stderr)
            return 1
        payload = response_path.read_text(encoding="utf-8")
        sys.stdout.write(payload)
        if payload and not payload.endswith("\n"):
            sys.stdout.write("\n")
        return 0

    extractor_cmd = os.environ.get("RECURSIVE_TRAINING_EXTRACTOR_CMD", "").strip()
    if extractor_cmd:
        return _run_external_command(extractor_cmd, repo_root, prompt_path)

    print(
        "Training extractor is not available for recursive-training in this environment.\n"
        "Wire one of: --response-file, <prompt>.response.json, or "
        "RECURSIVE_TRAINING_EXTRACTOR_CMD.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
