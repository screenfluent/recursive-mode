#!/usr/bin/env python3
"""
Repository-local Training-Free GRPO + ReasoningBank
for recursive-mode runs.

Synthesizes two research advances:
  - ReasoningBank: structured memory items (title/description/content/schema)
  - GRPO: variance-filtered group comparison (winners vs losers)

Supports dual extraction modes:
  - Contrastive: winners vs losers (classic GRPO)
  - Winner-only: consistent patterns across successful runs

Key design: groups by SUBSYSTEM only, not by task_type. A single run can
produce learnings about many kinds of work (requirements scoping, planning,
implementation, testing, QA, commit workflow, cleanup). The extractor script extracts
ALL learnings from a subsystem's runs and tags each item with its own task_type.
Items are then distributed to training memory files by their self-declared task_type.

Reads .recursive/run/<id>/, discovers ALL markdown files in each run folder,
groups by subsystem, filters for extraction signal, extracts structured memory
through the companion extractor script, and writes to .recursive/memory/.

Usage:
    python recursive-training-grpo.py --repo-root .
    python recursive-training-grpo.py --repo-root . \
        --incremental --run-id phase15b-commit-remediation
    python recursive-training-grpo.py --repo-root . \
        --winner-only-threshold 3
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MIN_GROUP_SIZE = 2
MIN_WINNER_ONLY_GROUP_SIZE = 2

# ---------------------------------------------------------------------------
# Run parser — discovers ALL .md files in a run folder
# ---------------------------------------------------------------------------

@dataclass
class RecursiveRollout:
    run_id: str
    repo_root: str
    task_type: str
    subsystem: str
    requirements: str = ""
    as_is: str = ""
    to_be_plan: str = ""
    implementation: str = ""
    test_summary: str = ""
    qa_summary: str = ""
    decisions_update: str = ""
    state_update: str = ""
    memory_impact: str = ""
    tests_passed: int = 0
    tests_total: int = 0
    audit_passed: bool = False
    coverage_passed: bool = False
    approval_passed: bool = False
    qa_passed: bool = False
    changed_files: List[str] = field(default_factory=list)
    documents: Dict[str, str] = field(default_factory=dict)

    @property
    def reward(self) -> float:
        if not self.approval_passed or not self.coverage_passed:
            return 0.0
        if self.tests_total == 0:
            return 0.5
        return self.tests_passed / self.tests_total

    @property
    def is_complete_winner(self) -> bool:
        return (
            self.audit_passed and self.coverage_passed and self.approval_passed
            and self.qa_passed
            and (self.tests_passed == self.tests_total if self.tests_total > 0 else True)
        )

    @property
    def all_content(self) -> str:
        """Concatenate all discovered documents for signal extraction."""
        parts = []
        for fname in sorted(self.documents.keys()):
            content = self.documents[fname]
            if content:
                parts.append(f"--- {fname} ---\n{content}")
        return "\n\n".join(parts)


class RunParser:
    # Explicit pass/fail gates
    AUDIT_VERDICT_PATTERN = re.compile(r'##?\s*Audit\s*Verdict.*?\n+\s*[*-]?\s*\*\*?(PASS|FAIL)\*\*?', re.I | re.S)
    COVERAGE_PATTERN = re.compile(r'Coverage:\s*(PASS|FAIL)', re.I)
    APPROVAL_PATTERN = re.compile(r'Approval:\s*(PASS|FAIL)', re.I)
    QA_VERDICT_PATTERN = re.compile(r'QA\s*Verdict\s*.*?\n+\s*[*-]?\s*\*\*?(PASS|FAIL)\*\*?', re.I | re.S)

    # Test counts — multiple patterns for flexibility
    TEST_SLASH_PATTERN = re.compile(r'(\d+)\s*/\s*(\d+)\s*(?:tests?\s*)?pass', re.I)
    TEST_TABLE_PATTERN = re.compile(r'(?:PASS\s*[-—]\s*)?(\d+)\s+(?:files?[,;]?\s+)?(\d+)\s+tests?', re.I)
    TEST_PASSED_PAREN_PATTERN = re.compile(r'(\d+)\s+passed\s+\((\d+)\s+tests?\)', re.I)
    TEST_SINGLE_PATTERN = re.compile(r'(\d+)\s+(?:tests?\s+)?pass(?:ed|ing)?', re.I)
    TEST_LABEL_PATTERN = re.compile(r'(?:tests?|result)[:\s]+(\d+)\s+(?:tests?\s+)?pass', re.I)

    # File references
    FILE_TABLE_PATTERN = re.compile(r'\|\s*`([^`]+)`\s*\|', re.MULTILINE)
    CODE_POINTER_PATTERN = re.compile(r'-\s*`([^`]+)`', re.MULTILINE)
    FILE_INLINE_PATTERN = re.compile(
        r'`([^`]+\.(?:ts|tsx|js|jsx|mjs|cjs|mts|cts|py|go|rs|json|yaml|yml|md|css|html))`',
        re.MULTILINE,
    )
    PHASE4_OVERALL_PASS = re.compile(r'Overall\s+Phase\s+4[^\n]*\bPASS\b', re.I)
    PHASE4_PASS_ROW = re.compile(
        r'\|\s*([^|]+?)\s*\|\s*(\d+)\s*/\s*(\d+)\s+PASS\b',
        re.I,
    )
    IGNORED_PATH_PREFIXES = (
        ".recursive/",
        "evidence/",
        ".git/",
        ".worktrees/",
        "node_modules/",
    )

    def __init__(self, run_dir: Path):
        self.run_dir = run_dir
        self.run_id = run_dir.name

    def read_artifact(self, filename: str) -> str:
        path = self.run_dir / filename
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def discover_documents(self) -> Dict[str, str]:
        """Read ALL .md files in the run directory."""
        docs = {}
        if not self.run_dir.exists():
            return docs
        for md_path in sorted(self.run_dir.glob("*.md")):
            docs[md_path.name] = md_path.read_text(encoding="utf-8")
        return docs

    def _extract_motivation(self, text: str, max_chars: int = 600) -> str:
        """Extract the motivation paragraph after stripping frontmatter."""
        if text.startswith("---"):
            end = text.find("---", 3)
            if end != -1:
                text = text[end+3:]
        lines = text.strip().split("\n")
        skip_patterns = [
            r'^Run:\s*', r'^Phase:\s*', r'^Status:\s*', r'^LockedAt:\s*',
            r'^LockHash:\s*', r'^Workflow\s+version:\s*', r'^Inputs:\s*$',
            r'^Outputs:\s*$', r'^Scope\s+note:\s*',
        ]
        content_lines = []
        in_frontmatter = True
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            is_frontmatter = any(re.match(p, stripped) for p in skip_patterns)
            if in_frontmatter and is_frontmatter:
                continue
            in_frontmatter = False
            if stripped.startswith("|") or stripped.startswith("#") or stripped.startswith("-"):
                continue
            content_lines.append(stripped)
            if len(" ".join(content_lines)) >= max_chars:
                break
        return " ".join(content_lines)[:max_chars]

    def infer_task_type(self, documents: Dict[str, str], run_id: str) -> str:
        """Infer task type from the actual content of run documents.

        Content-first approach: reads the motivation/summary paragraphs from
        requirements, plan, and implementation to determine the nature of work.
        Scores action types (what was done) and domains (where), then composes
        them into a canonical task_type string. Run_id is fallback only.
        """
        requirements = documents.get("00-requirements.md", "")
        plan = documents.get("02-to-be-plan.md", "")
        impl = documents.get("03-implementation-summary.md", "")

        req_motivation = self._extract_motivation(requirements, 600)
        plan_motivation = self._extract_motivation(plan, 400)
        impl_motivation = self._extract_motivation(impl, 400)
        impl_content = impl.lower() if impl else ""
        req_plan_lower = (requirements + "\n" + plan).lower()

        # --- Action detection ---
        action_scores: Dict[str, int] = defaultdict(int)

        def score_action(text: str, weight: int):
            t = text.lower()
            # Audit
            if re.search(r'\bthis run\b.*\baudit\b|\bperforms?\b.*\baudit\b|\brepo-wide\s+audit\b', t):
                action_scores["audit"] += weight + 3
            elif re.search(r'\baudit\b.*\bfinding|\brepository.*\baudit\b', t):
                action_scores["audit"] += weight + 1
            # Commit / cleanup / validate
            if re.search(r'\bcommits?\b.*\b(remediation|changes|work)\b|\bgit\s+commit\b', t):
                action_scores["commit"] += weight + 2
            if re.search(r'\bcleans?\s+up\b|\bcleanup\b|\bremove\s+temporary\b|\bremov\w+\s+temp\b', t):
                action_scores["cleanup"] += weight + 2
            if re.search(r'\bvalidat\w+\b.*\b(tests?|build)\b|\bverify\b.*\bbuild\b', t):
                action_scores["validate"] += weight + 2
            # Implementation
            if re.search(r'\badds?\b|\bimplement\w*\b|\bbuilds?\b|\bcompletes?\b', t):
                action_scores["implement"] += weight + 1
            # Fix / remediate
            if re.search(r'\bthis run\b.*\b(fix|remediat)\w*\b|\bremediation run\b', t):
                action_scores["fix"] += weight + 2
            elif re.search(r'\bfix\b.*\bschema|\bfix\b.*\bgap|\brepair\b', t):
                action_scores["fix"] += weight
            # Integration
            if re.search(r'\bintegrat\w+\b.*\binto\b|\bconnect\w*\b.*\bto\b', t):
                action_scores["integrate"] += weight + 1
            # Refactor
            if re.search(r'\brefactor\b|\brestructur\w+\b', t):
                action_scores["refactor"] += weight + 1

        score_action(req_motivation, 5)
        score_action(plan_motivation, 2)
        score_action(impl_motivation, 1)

        # Tie-breaker: audit vs fix
        if action_scores.get("audit", 0) > 0 and action_scores.get("fix", 0) > 0:
            if impl_content:
                if re.search(r'\bfix\w*\b|\brepair\w*\b|\bremediat\w*\b', impl_content):
                    action_scores["fix"] += 3
                if re.search(r'\baudit\w*\b|\bfindings\b', impl_content):
                    action_scores["audit"] += 3

        # --- Domain detection ---
        domain_scores: Dict[str, int] = defaultdict(int)

        # Primary: implementation file paths
        if any(k in impl_content for k in ("apps/web/src", "packages/ui/src", ".tsx", ".css", "tailwind", "shadcn")):
            domain_scores["frontend"] += 3
        if any(k in impl_content for k in ("apps/api-worker", "packages/domain", "packages/schemas", "hono", "durable object")):
            domain_scores["backend"] += 3
        if any(k in impl_content for k in ("protocol/schemas", "schema-tools", "validate-schemas", "$id")):
            domain_scores["schema"] += 4
        if any(k in impl_content for k in ("wrangler", "wrangler.jsonc", "deploy", "docker", "ci/cd")):
            domain_scores["infrastructure"] += 3
        if any(k in impl_content for k in ("state.md", "decisions.md", "memory", "governance", "control-plane")):
            domain_scores["governance"] += 3

        # Fallback: explicit domain keywords in requirements + plan
        if not impl_content or sum(domain_scores.values()) < 2:
            if any(k in req_plan_lower for k in ("frontend", "react", "component", "ui", "page", "route", "dashboard")):
                domain_scores["frontend"] += 3
            if any(k in req_plan_lower for k in ("api", "route", "worker", "server", "backend")):
                domain_scores["backend"] += 3
            if any(k in req_plan_lower for k in ("schema", "protocol", "json schema", "$id", "canonical")):
                domain_scores["schema"] += 3
            if any(k in req_plan_lower for k in ("wrangler", "deploy", "docker", "ci/cd")):
                domain_scores["infrastructure"] += 3
            if any(k in req_plan_lower for k in ("state.md", "decisions.md", "memory", "governance")):
                domain_scores["governance"] += 3

        best_action = max(action_scores, key=action_scores.get) if action_scores else None
        best_domain = max(domain_scores, key=domain_scores.get) if domain_scores else None
        action_score = action_scores.get(best_action, 0) if best_action else 0
        domain_score = domain_scores.get(best_domain, 0) if best_domain else 0

        parts: List[str] = []
        if best_action == "audit":
            if best_domain and domain_score >= 4:
                parts = [best_domain, "audit"]
            elif "repository" in req_motivation.lower() or "repo-wide" in req_motivation.lower():
                parts = ["repository", "audit"]
            else:
                parts = ["audit"]
        elif best_action in ("commit", "cleanup", "validate"):
            actions = []
            if action_scores.get("commit", 0) > 0: actions.append("commit")
            if action_scores.get("cleanup", 0) > 0: actions.append("cleanup")
            if action_scores.get("validate", 0) > 0: actions.append("validate")
            if actions: parts = ["-".join(actions)]
            else: parts = [best_action]
        elif best_action == "fix" and best_domain and domain_score >= 3:
            parts = [best_domain, "remediation"]
        elif best_action == "implement" and best_domain and domain_score >= 3:
            parts = [best_domain, "feature-implementation"]
        elif best_action == "integrate":
            if best_domain and domain_score >= 3: parts = [best_domain, "integration"]
            else: parts = ["integration"]
        elif best_domain and domain_score >= 3:
            parts = [best_domain, best_action or "work"]
        elif best_action and action_score >= 2:
            parts = [best_action]

        task_type = "-".join(parts) if parts else ""
        if not task_type or action_score < 2:
            cleaned = re.sub(r'[^a-zA-Z0-9_-]', '-', run_id.lower()).strip('-')
            cleaned = re.sub(r'^(phase\d+[a-z]?-?|run-?\d+-?)+', '', cleaned)
            cleaned = re.sub(r'-+', '-', cleaned).strip('-')
            task_type = cleaned[:60] if cleaned else "general"

        return task_type

    @classmethod
    def normalize_repo_path(cls, raw: str) -> str:
        path = raw.strip().strip("`").replace("\\", "/")
        while path.startswith("./"):
            path = path[2:]
        if path.startswith("/"):
            path = path[1:]
        # Drop absolute Windows drive prefixes if they sneak in
        if re.match(r"^[A-Za-z]:/", path):
            parts = path.split("/", 2)
            path = parts[2] if len(parts) == 3 else path
        return path

    @classmethod
    def is_noise_path(cls, path: str) -> bool:
        normalized = cls.normalize_repo_path(path)
        if not normalized:
            return True
        if normalized.startswith(".recursive/") or normalized == ".recursive":
            return True
        if any(normalized.startswith(prefix) for prefix in cls.IGNORED_PATH_PREFIXES):
            return True
        if "/.recursive/" in f"/{normalized}":
            return True
        if re.search(r"(^|/)\.recursive/run/", normalized):
            return True
        return False

    def infer_subsystem(self, implementation: str, as_is: str, documents: Dict[str, str]) -> str:
        preferred_docs = [
            documents.get("03-implementation-summary.md", ""),
            documents.get("00-worktree.md", ""),
            documents.get("04-test-summary.md", ""),
            implementation,
            as_is,
        ]
        files: List[str] = []
        for text in preferred_docs:
            if text:
                files.extend(self.extract_changed_files(text))
        if not files:
            files = self.extract_changed_files("\n".join(documents.values()))

        prefixes: Dict[str, int] = {}
        for raw in files:
            normalized = self.normalize_repo_path(raw)
            if self.is_noise_path(normalized):
                continue
            parts = [p for p in normalized.split("/") if p]
            if len(parts) < 1:
                continue
            if parts[0] in ("packages", "apps", "libs") and len(parts) >= 2:
                key = parts[1]
            else:
                key = parts[0]
            if not key or key in {".recursive", "evidence", "run"}:
                continue
            prefixes[key] = prefixes.get(key, 0) + 1
        return max(prefixes, key=prefixes.get) if prefixes else "general"

    def extract_changed_files(self, text: str) -> List[str]:
        files = set()
        for pat in (self.FILE_TABLE_PATTERN, self.CODE_POINTER_PATTERN, self.FILE_INLINE_PATTERN):
            for m in pat.findall(text):
                candidate = self.normalize_repo_path(m)
                if ("." in candidate or "/" in candidate) and not self.is_noise_path(candidate):
                    files.add(candidate)
        return sorted(files)

    def extract_test_counts_from_text(self, text: str, *, allow_loose: bool = False) -> tuple[int, int]:
        """Extract (passed, total). Prefer explicit N/M PASS rows; loose patterns optional."""
        total_passed, total_tests, seen = 0, 0, set()

        for _label, p, t in self.PHASE4_PASS_ROW.findall(text):
            key = (int(p), int(t))
            if key not in seen and key[0] <= key[1] and key[1] > 0:
                # Skip rows that look like RED/historical in the label column context is handled by PASS-only
                seen.add(key)
                total_passed += key[0]
                total_tests += key[1]

        if total_tests > 0:
            return total_passed, total_tests

        for p, t in self.TEST_SLASH_PATTERN.findall(text):
            key = (int(p), int(t))
            if key not in seen and key[0] <= key[1] and key[1] > 0 and key[0] == key[1]:
                seen.add(key)
                total_passed += key[0]
                total_tests += key[1]

        if total_tests > 0:
            return total_passed, total_tests

        if not allow_loose:
            return 0, 0

        for p, t in self.TEST_PASSED_PAREN_PATTERN.findall(text):
            key = (int(p), int(t))
            if key not in seen and key[0] <= key[1] and key[1] > 0:
                seen.add(key)
                total_passed += key[0]
                total_tests += key[1]

        return total_passed, total_tests

    def extract_test_counts(self, documents: Dict[str, str] | str) -> tuple[int, int]:
        """Prefer Phase 4 primary suite PASS rows; do not soup RED history from all markdown."""
        if isinstance(documents, str):
            return self.extract_test_counts_from_text(documents, allow_loose=False)

        phase4 = documents.get("04-test-summary.md", "")
        if phase4:
            # Drop historical RED sections before counting
            cleaned_lines = []
            for line in phase4.splitlines():
                lower = line.lower()
                if "red" in lower and ("historical" in lower or "fail as expected" in lower):
                    continue
                if re.search(r'\bFAIL as expected\b', line, re.I):
                    continue
                cleaned_lines.append(line)
            cleaned = "\n".join(cleaned_lines)
            passed, total = self.extract_test_counts_from_text(cleaned, allow_loose=False)
            if total > 0:
                return passed, total
            if self.PHASE4_OVERALL_PASS.search(phase4):
                # Gates + overall PASS with no reliable counts → treat as complete (0/0)
                return 0, 0

        # Fallback: green-only slash totals from implementation/test docs (no loose "N pass")
        for key in ("04-test-summary.md", "03-implementation-summary.md"):
            text = documents.get(key, "")
            if not text:
                continue
            passed, total = self.extract_test_counts_from_text(text, allow_loose=False)
            if total > 0:
                return passed, total
        return 0, 0

    def extract_reward_signals(self, documents: Dict[str, str]) -> dict:
        all_text = "\n\n".join(documents.values())

        audit_matches = self.AUDIT_VERDICT_PATTERN.findall(all_text)
        coverage_matches = self.COVERAGE_PATTERN.findall(all_text)
        approval_matches = self.APPROVAL_PATTERN.findall(all_text)
        qa_matches = self.QA_VERDICT_PATTERN.findall(all_text)

        total_passed, total_tests = self.extract_test_counts(documents)

        has_audit_fail = any("FAIL" in m.upper() for m in audit_matches)
        coverage_pass = any("PASS" in m.upper() for m in coverage_matches) and not any("FAIL" in m.upper() for m in coverage_matches)
        approval_pass = any("PASS" in m.upper() for m in approval_matches) and not any("FAIL" in m.upper() for m in approval_matches)

        # Flexible QA verdict detection
        qa_doc_text = documents.get("05-manual-qa.md", "")
        qa_doc_approval = self.APPROVAL_PATTERN.findall(qa_doc_text)

        if qa_matches:
            qa_pass = all("FAIL" not in m.upper() for m in qa_matches)
        elif qa_doc_approval:
            # QA doc has explicit Approval gate - use that
            qa_pass = all("PASS" in m.upper() for m in qa_doc_approval) and not any("FAIL" in m.upper() for m in qa_doc_approval)
        elif qa_doc_text and "FAIL" not in qa_doc_text.upper():
            # Has QA doc but no explicit verdict - assume pass if no FAIL found
            qa_pass = True
        else:
            qa_pass = False

        return {
            "has_audit_fail": has_audit_fail,
            "coverage_pass": coverage_pass,
            "approval_pass": approval_pass,
            "tests_passed": total_passed,
            "tests_total": total_tests,
            "qa_pass": qa_pass,
        }

    def has_implementation_evidence(self, documents: Dict[str, str]) -> bool:
        """Check if any document contains implementation evidence."""
        if documents.get("03-implementation-summary.md"):
            return True
        if any(f.startswith("AUDIT-") and content for f, content in documents.items()):
            return True
        impl_keywords = ["implemented", "refactor", "changed files", "commit", "git diff", "diff --stat", "requirements completed"]
        for fname, content in documents.items():
            lower = content.lower()
            if any(k in lower for k in impl_keywords):
                return True
        return False

    def has_test_evidence(self, documents: Dict[str, str]) -> bool:
        """Check if any document contains test evidence."""
        if documents.get("04-test-summary.md"):
            return True
        test_keywords = ["tests pass", "test suite", "vitest", "npx vitest", "test result", "npm test", "passed", "full suite"]
        for fname, content in documents.items():
            lower = content.lower()
            if any(k in lower for k in test_keywords):
                return True
        return False

    def parse(self) -> Optional[RecursiveRollout]:
        # Discover ALL .md files in the run directory
        documents = self.discover_documents()
        if not documents:
            return None

        # The primary requirements artifact must exist for a valid run
        req = documents.get("00-requirements.md", "")
        if not req:
            return None

        # Named fields from primary artifacts (if present)
        as_is = documents.get("01-as-is.md", "")
        impl = documents.get("03-implementation-summary.md", "")
        test = documents.get("04-test-summary.md", "")
        qa = documents.get("05-manual-qa.md", "")
        decisions = documents.get("06-decisions-update.md", "")
        state = documents.get("07-state-update.md", "")
        memory = documents.get("08-memory-impact.md", "")
        to_be = documents.get("02-to-be-plan.md", "")

        # Reward signals from ALL documents
        signals = self.extract_reward_signals(documents)

        # Critical missing = no implementation evidence AND no test evidence anywhere
        critical_missing = not (self.has_implementation_evidence(documents) or self.has_test_evidence(documents))

        return RecursiveRollout(
            run_id=self.run_id,
            repo_root=str(self.run_dir.parent.parent.parent),
            task_type=self.infer_task_type(documents, self.run_id),
            subsystem=self.infer_subsystem(impl, as_is, documents),
            requirements=req, as_is=as_is, to_be_plan=to_be,
            implementation=impl, test_summary=test, qa_summary=qa,
            decisions_update=decisions, state_update=state, memory_impact=memory,
            tests_passed=signals["tests_passed"], tests_total=signals["tests_total"],
            audit_passed=not signals["has_audit_fail"],
            coverage_passed=signals["coverage_pass"] and not critical_missing,
            approval_passed=signals["approval_pass"] and not critical_missing,
            qa_passed=signals["qa_pass"] and not critical_missing,
            changed_files=self.extract_changed_files(impl) or self.extract_changed_files(as_is) or self.extract_changed_files(req),
            documents=documents,
        )


def phase8_is_locked(run_dir: Path) -> bool:
    phase8 = run_dir / "08-memory-impact.md"
    if not phase8.exists():
        return False
    text = phase8.read_text(encoding="utf-8")
    return bool(re.search(r"(?m)^Status:\s*`?LOCKED`?\s*$", text)) or "LockedAt:" in text


def parse_all_runs(runs_dir: Path, *, require_phase8_locked: bool = True) -> List[RecursiveRollout]:
    rollouts = []
    if not runs_dir.exists():
        return rollouts
    for run_dir in sorted(runs_dir.iterdir()):
        if not (run_dir.is_dir() and any(run_dir.glob("*.md"))):
            continue
        if require_phase8_locked and not phase8_is_locked(run_dir):
            continue
        r = RunParser(run_dir).parse()
        if r:
            rollouts.append(r)
    return rollouts


def filter_rollouts_for_training(
    rollouts: List[RecursiveRollout],
    incremental_run_id: Optional[str] = None,
) -> List[RecursiveRollout]:
    """Incremental mode keeps the target run plus peers in the same subsystem."""
    if not incremental_run_id:
        return list(rollouts)
    target = next((r for r in rollouts if r.run_id == incremental_run_id), None)
    if target is None:
        return []
    return [r for r in rollouts if r.subsystem == target.subsystem]

# ---------------------------------------------------------------------------
# Grouping with hierarchical prefix fallback
# ---------------------------------------------------------------------------

def group_by_subsystem(rollouts: List[RecursiveRollout]) -> Dict[str, List[RecursiveRollout]]:
    """Group rollouts by subsystem only.

    A single run can produce learnings about multiple task types (requirements
    scoping, planning, implementation, testing, QA). Grouping by subsystem
    allows the extractor script to extract ALL learnings from a run's documents and tag
    each item with its own task_type. Items are distributed to training memory
    files by their self-declared task_type after extraction.
    """
    groups: Dict[str, List[RecursiveRollout]] = defaultdict(list)
    for r in rollouts:
        groups[r.subsystem].append(r)
    return dict(groups)


# ---------------------------------------------------------------------------
# Group classification
# ---------------------------------------------------------------------------

def classify_group(group: List[RecursiveRollout], winner_only_threshold: int) -> Tuple[str, List[RecursiveRollout], List[RecursiveRollout]]:
    """Classify a group for extraction mode.

    Returns:
        (mode, winners, losers) where mode is:
        - "contrastive": has both winners and losers (classic GRPO)
        - "winner-only": only winners, but enough for pattern extraction
        - "insufficient": not enough signal for either mode
    """
    winners = [r for r in group if r.is_complete_winner]
    losers = [r for r in group if not r.is_complete_winner]

    if winners and losers:
        return "contrastive", winners, losers
    if len(winners) >= winner_only_threshold:
        return "winner-only", winners, []
    return "insufficient", [], []


# ---------------------------------------------------------------------------
# Companion extraction script.
# The training orchestrator constructs prompts and delegates prompt evaluation
# to the extractor script. It does not choose transports or credentials.
# ---------------------------------------------------------------------------

class ExtractionUnavailableError(RuntimeError):
    """Raised when the companion extractor script is unavailable."""


def _extractor_script_path() -> Path:
    return Path(__file__).with_name("recursive-training-extract.py")


def invoke_extractor_script(repo_root: Path, prompt: str) -> str:
    extractor_script = _extractor_script_path()
    if not extractor_script.exists():
        raise ExtractionUnavailableError(
            "Training extractor script is unavailable for recursive-training."
        )

    with tempfile.TemporaryDirectory(prefix="recursive-training-extract-") as temp_dir:
        prompt_path = Path(temp_dir) / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")
        result = subprocess.run(
            [
                sys.executable,
                str(extractor_script),
                "--repo-root",
                str(repo_root),
                "--prompt-file",
                str(prompt_path),
            ],
            check=False,
            capture_output=True,
            text=True,
        )

    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode == 0:
        return stdout
    if result.returncode == 2:
        raise ExtractionUnavailableError(
            stderr or stdout or "Training extractor script is not available."
        )
    print(f"  Training extraction failed: {stderr or stdout or 'no diagnostics emitted'}")
    return ""


# ---------------------------------------------------------------------------
# Extraction prompts
# ---------------------------------------------------------------------------

CONTRASTIVE_PROMPT = """You are analyzing multiple attempts to work in a specific software repository subsystem. Each attempt is a recursive-mode run with full phase artifacts.

This repository uses recursive-mode: a structured workflow where each run produces phase artifacts (requirements, AS-IS analysis, TO-BE plan, implementation, tests, QA) and may also include supplementary audit reports, addenda, or evidence files.

Subsystem: {subsystem}
Repository: {repo_name}

Below are {num_rollouts} historical runs. Some SUCCEEDED fully. Others FAILED at some phase.

=== WINNER RUNS ===
{winner_summaries}

=== LOSER RUNS ===
{loser_summaries}

Your task: Extract REPOSITORY-SPECIFIC reasoning strategies that explain why winners succeeded where losers failed. These must be actionable lessons unique to THIS codebase.

A single run can contain learnings about MANY different kinds of work — requirements scoping, planning, implementation, testing, QA, cleanup, commit workflow, etc. Extract ALL distinct learnings you can find.

For each memory item, provide:
- **title**: ≤ 6 words, concise identifier (e.g., "Branch-based commit workflow")
- **description**: ≤ 20 words, one-line summary
- **content**: max 100 words, distilled actionable steps with rationale
- **task_type**: the kind of work this learning applies to (e.g., "commit-workflow", "test-validation", "frontend-implementation", "requirements-scoping", "planning", "cleanup", "qa-verification", "api-design"). Be specific and descriptive.
- **applies_to**: array of file paths, commands, or conceptual tags this applies to

Focus on:
1. What successful runs did differently (concrete steps, commands, file paths)
2. What repo-specific conventions or quirks mattered
3. Common failure modes and how to avoid them
4. Build/test commands that are specific to this repo's setup
5. Patterns in how requirements are scoped, plans are structured, or tests are organized

Return ONLY a JSON array:
```json
[
  {{
    "title": "Branch-based commit workflow",
    "description": "Always create feature branches before committing remediation work",
    "content": "1. Create branch from stage HEAD: git checkout -b fix/<issue>. 2. Make changes and verify. 3. Push branch and open PR — never commit directly to stage.",
    "task_type": "commit-workflow",
    "applies_to": [".worktrees/", "git workflow", "stage branch"]
  }}
]
```

If no meaningful repo-specific strategies can be extracted, return [].
"""


WINNER_ONLY_PROMPT = """You are analyzing multiple successful attempts to work in a specific software repository subsystem. Each attempt is a recursive-mode run with full phase artifacts.

This repository uses recursive-mode: a structured workflow where each run produces phase artifacts (requirements, AS-IS analysis, TO-BE plan, implementation, tests, QA) and may also include supplementary audit reports, addenda, or evidence files.

Subsystem: {subsystem}
Repository: {repo_name}

Below are {num_rollouts} historical runs. All SUCCEEDED.

=== SUCCESSFUL RUNS ===
{winner_summaries}

Your task: Extract REPOSITORY-SPECIFIC patterns, conventions, and practices that appear consistently across these successful runs. These must be actionable knowledge unique to THIS codebase that future agents should apply when working on similar tasks.

A single run can contain learnings about MANY different kinds of work — requirements scoping, planning, implementation, testing, QA, cleanup, commit workflow, etc. Extract ALL distinct learnings you can find.

For each memory item, provide:
- **title**: ≤ 6 words, concise identifier
- **description**: ≤ 20 words, one-line summary
- **content**: max 100 words, distilled actionable steps with rationale
- **task_type**: the kind of work this learning applies to (e.g., "commit-workflow", "test-validation", "frontend-implementation", "requirements-scoping", "planning", "cleanup", "qa-verification", "api-design"). Be specific and descriptive.
- **applies_to**: array of file paths, commands, or conceptual tags this applies to

Focus on:
1. Build/test commands that are specific to this repo's setup
2. File organization patterns that appear repeatedly across runs
3. Architectural conventions (e.g., how languages/modules interact, how vendored code is managed)
4. Common verification approaches or validation commands used
5. Repo quirks that an external agent would need to know
6. Consistent patterns in how requirements are scoped or how plans are structured

Return ONLY a JSON array:
```json
[
  {{
    "title": "Use corepack pnpm for nested commands",
    "description": "Root scripts must use corepack pnpm instead of bare pnpm for nested workspace calls",
    "content": "1. Root package.json scripts must invoke nested workspace commands through `corepack pnpm ...` instead of bare `pnpm`. 2. This ensures PATH-independent resolution on Windows. 3. Apply to schemas:validate, test, smoke, and build scripts.",
    "task_type": "infrastructure-scripting",
    "applies_to": ["package.json", "pnpm scripts", "root commands"]
  }}
]
```

If no meaningful repo-specific patterns can be extracted, return [].
"""


# ---------------------------------------------------------------------------
# Rollout summarization
# ---------------------------------------------------------------------------

def _summarize_rollout(r: RecursiveRollout, label: str) -> str:
    """Create a rich summary of a rollout from all its documents."""
    files_str = ", ".join(r.changed_files[:8]) if r.changed_files else "N/A"
    test_line = f"{r.tests_passed}/{r.tests_total} pass" if r.tests_total > 0 else "No tests"

    # Include supplementary document names to hint at richness
    extra_docs = [f for f in r.documents if f not in (
        "00-requirements.md", "01-as-is.md", "02-to-be-plan.md",
        "03-implementation-summary.md", "04-test-summary.md",
        "05-manual-qa.md", "06-decisions-update.md",
        "07-state-update.md", "08-memory-impact.md", "00-worktree.md"
    )]
    extra_hint = f" | Extra docs: {', '.join(extra_docs)}" if extra_docs else ""

    plan_snippet = r.to_be_plan[:500].replace("\n", "\n    ") if r.to_be_plan else "N/A"
    impl_snippet = r.implementation[:400].replace("\n", "\n    ") if r.implementation else "N/A"

    # Include task_type and document keys so the extractor sees what kind of work this run covered
    doc_keys = ", ".join(sorted(r.documents.keys())) if r.documents else "N/A"

    return (
        f"Run: {r.run_id} [{label}] (inferred: {r.task_type}){extra_hint}\n"
        f"  Documents: {doc_keys}\n"
        f"  Files: {files_str}\n"
        f"  Tests: {test_line} | Audit: {'PASS' if r.audit_passed else 'FAIL'} | "
        f"Coverage: {'PASS' if r.coverage_passed else 'FAIL'} | Approval: {'PASS' if r.approval_passed else 'FAIL'}\n"
        f"  Plan:\n    {plan_snippet}\n"
        f"  Implementation:\n    {impl_snippet}\n"
    )


async def extract_reasoningbank_items(
    mode: str, subsystem: str,
    winners: List[RecursiveRollout], losers: List[RecursiveRollout],
    existing_items: List[dict]
) -> List[dict]:
    """Extract structured ReasoningBank memory items from a subsystem group.

    The extractor is free to tag each item with its own task_type. A single run can
    contribute items with different task_types (e.g., commit-workflow,
    test-validation, requirements-scoping).
    """
    repo_name = winners[0].repo_root.split("/")[-1] if "/" in winners[0].repo_root else winners[0].repo_root

    winner_text = "\n---\n".join(_summarize_rollout(r, "WIN") for r in winners)

    if mode == "contrastive":
        loser_text = "\n---\n".join(_summarize_rollout(r, "FAIL") for r in losers)
        prompt_template = CONTRASTIVE_PROMPT
    else:
        loser_text = ""
        prompt_template = WINNER_ONLY_PROMPT

    # Deduplication hint
    existing_titles = [item.get("title", "") for item in existing_items]
    dedup_hint = f"\nExisting memory titles (avoid duplicates): {existing_titles}\n" if existing_titles else ""

    prompt = prompt_template.format(
        subsystem=subsystem,
        repo_name=repo_name,
        num_rollouts=len(winners) + len(losers),
        winner_summaries=winner_text,
        loser_summaries=loser_text,
    ) + dedup_hint

    repo_path = Path(winners[0].repo_root).resolve()
    content = invoke_extractor_script(repo_path, prompt)
    if not content:
        return []

    return _parse_reasoningbank_json(content)


def _parse_reasoningbank_json(text: str) -> List[dict]:
    if not text:
        return []
    for pattern in (r'```json\s*([\s\S]*?)\s*```', r'```\s*([\s\S]*?)\s*```'):
        m = re.search(pattern, text)
        if m:
            text = m.group(1)
            break
    try:
        data = json.loads(text)
        if isinstance(data, list):
            items = []
            for item in data:
                if isinstance(item, dict) and "title" in item and "content" in item:
                    # Normalize task_type: lowercase, hyphenated, no fixed enum
                    raw_tt = item.get("task_type", "")
                    if raw_tt:
                        tt = re.sub(r'[^a-zA-Z0-9_-]', '-', raw_tt.lower()).strip('-')
                        tt = re.sub(r'-+', '-', tt).strip('-')
                        item["task_type"] = tt[:60]
                    else:
                        item["task_type"] = "general"
                    items.append(item)
            return items
    except json.JSONDecodeError:
        pass
    return []


# ---------------------------------------------------------------------------
# ReasoningBank: memory plane writer
# ---------------------------------------------------------------------------

class ReasoningBankMemory:
    """Manages .recursive/memory/ as a ReasoningBank-style structured store."""

    MEMORY_DIR = ".recursive/memory"
    DOMAINS_DIR = "domains"
    TRAINING_DIR = "training"

    def __init__(self, repo_root: str):
        self.root = Path(repo_root)
        self.domains_dir = self.root / self.MEMORY_DIR / self.DOMAINS_DIR
        self.training_dir = self.root / self.MEMORY_DIR / self.TRAINING_DIR
        self.memory_index = self.root / self.MEMORY_DIR / "MEMORY.md"
        self.domains_dir.mkdir(parents=True, exist_ok=True)
        self.training_dir.mkdir(parents=True, exist_ok=True)
        self._rb_counter = self._load_max_rb_id()

    @staticmethod
    def _domain_filename(subsystem: str) -> str:
        cleaned = re.sub(r'[^a-zA-Z0-9_-]+', '-', subsystem.strip().lower())
        cleaned = cleaned.strip('-_') or "general"
        return f"{cleaned}.md"

    def _load_max_rb_id(self) -> int:
        max_id = -1
        for d in (self.domains_dir, self.training_dir):
            if not d.exists():
                continue
            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                for m in re.finditer(r'rb_id:\s*"RB-(\d+)"', content):
                    max_id = max(max_id, int(m.group(1)))
        return max_id

    def _next_rb_id(self) -> str:
        self._rb_counter += 1
        return f"RB-{self._rb_counter}"

    def existing_titles(self) -> set[str]:
        titles: set[str] = set()
        for d in (self.domains_dir, self.training_dir):
            if not d.exists():
                continue
            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                for m in re.finditer(r'### RB-\d+:\s*(.+)', content):
                    titles.add(m.group(1).strip().lower())
        return titles

    def assign_rb_ids(self, items: List[dict]) -> List[dict]:
        """Assign a stable rb_id once per item before dual writes."""
        prepared = []
        for item in items:
            cloned = dict(item)
            if not cloned.get("rb_id"):
                cloned["rb_id"] = self._next_rb_id()
            prepared.append(cloned)
        return prepared

    def filter_new_items(self, items: List[dict]) -> List[dict]:
        existing = self.existing_titles()
        fresh = []
        for item in items:
            title = str(item.get("title", "")).strip().lower()
            if not title or title in existing:
                continue
            existing.add(title)
            fresh.append(item)
        return fresh

    def _compute_success_rate(self, source_runs: List[str], winner_runs: List[str]) -> float:
        if not source_runs:
            return 0.0
        return len(winner_runs) / len(source_runs)

    def _product_owns_paths(self, changed_paths: List[str]) -> List[str]:
        owns = []
        for raw in changed_paths:
            path = RunParser.normalize_repo_path(raw)
            if RunParser.is_noise_path(path):
                continue
            if " | " in path or "Status:" in path or "Changed Files:" in path:
                continue
            if len(path) > 180:
                continue
            if not (("/" in path) or re.search(r"\.[A-Za-z0-9]{1,8}$", path)):
                continue
            owns.append(path)
            if len(owns) >= 10:
                break
        return owns

    def write_domain_memory(
        self, subsystem: str, items: List[dict], source_runs: List[str],
        winner_runs: List[str], changed_paths: List[str]
    ) -> List[dict]:
        items = self.filter_new_items(items)
        if not items:
            return []
        items = self.assign_rb_ids(items)
        domain_file = self.domains_dir / self._domain_filename(subsystem)
        existing = domain_file.read_text(encoding="utf-8") if domain_file.exists() else ""
        now = datetime.now(timezone.utc).isoformat()
        success_rate = self._compute_success_rate(source_runs, winner_runs)

        new_section = f"\n## ReasoningBank Items ({now})\n\n"
        for item in items:
            rb_id = item.get("rb_id") or self._next_rb_id()
            item["rb_id"] = rb_id
            applies_to = item.get("applies_to", [])
            new_section += (
                f"### {rb_id}: {item['title']}\n\n"
                f"**Description:** {item['description']}\n\n"
                f"**Content:** {item['content']}\n\n"
                f"```yaml\n"
                f"rb_id: \"{rb_id}\"\n"
                f"title: \"{item['title']}\"\n"
                f"description: \"{item['description']}\"\n"
                f"task_type: \"{item.get('task_type', '')}\"\n"
                f"subsystem: \"{subsystem}\"\n"
                f"source_runs: {json.dumps(source_runs)}\n"
                f"applies_to: {json.dumps(applies_to)}\n"
                f"success_rate: {success_rate:.2f}\n"
                f"status: active\n"
                f"created_at: \"{now}\"\n"
                f"```\n\n"
            )

        if not existing:
            owns_list = self._product_owns_paths(changed_paths)
            owns = ", ".join(owns_list) if owns_list else "TBD"
            header = (
                f"---\nType: domain\nStatus: CURRENT\nScope: {subsystem}\n"
                f"Owns-Paths: {owns}\nWatch-Paths:\n"
                f"Source-Runs: {', '.join(source_runs)}\n"
                f"Validated-At-Commit:\nLast-Validated: {now}\n"
                f"Tags: reasoningbank, training-free-grpo\n---\n\n"
                f"# {subsystem}\n\n"
                f"Domain memory for `{subsystem}`.\n\n"
            )
            content = header + new_section
        else:
            split_marker = "## Router and Parent Refresh"
            if split_marker in existing:
                idx = existing.index(split_marker)
                content = existing[:idx] + new_section + "\n" + existing[idx:]
            else:
                content = existing + "\n" + new_section
        domain_file.write_text(content, encoding="utf-8")
        return items

    def write_training_memory(
        self,
        task_type: str,
        subsystem: str,
        items: List[dict],
        source_runs: List[str],
        winner_runs: List[str],
    ):
        # Training fan-out reuses rb_ids already assigned; do not re-filter titles
        # when items were already filtered for domain write. Still skip empty.
        if not items:
            return
        prepared = []
        for item in items:
            cloned = dict(item)
            if not cloned.get("rb_id"):
                cloned["rb_id"] = self._next_rb_id()
            prepared.append(cloned)
        items = prepared
        task_file = self.training_dir / f"{task_type}.md"
        existing = task_file.read_text(encoding="utf-8") if task_file.exists() else ""
        now = datetime.now(timezone.utc).isoformat()
        success_rate = self._compute_success_rate(source_runs, winner_runs)
        watch_paths = sorted({value for item in items for value in item.get("applies_to", []) if value})

        new_section = f"\n## Extracted Reasoning Items ({now})\n\n"
        for item in items:
            rb_id = item.get("rb_id") or self._next_rb_id()
            applies_to = item.get("applies_to", [])
            new_section += (
                f"### {rb_id}: {item['title']}\n\n"
                f"**Description:** {item['description']}\n\n"
                f"**Content:** {item['content']}\n\n"
                f"```yaml\n"
                f"rb_id: \"{rb_id}\"\n"
                f"title: \"{item['title']}\"\n"
                f"description: \"{item['description']}\"\n"
                f"task_type: \"{task_type}\"\n"
                f"subsystem: \"{subsystem}\"\n"
                f"source_runs: {json.dumps(source_runs)}\n"
                f"applies_to: {json.dumps(applies_to)}\n"
                f"success_rate: {success_rate:.2f}\n"
                f"status: active\n"
                f"created_at: \"{now}\"\n"
                f"```\n\n"
            )

        if not existing:
            watch_lines = "\n".join(f"- {path}" for path in watch_paths) if watch_paths else "- TBD"
            header = (
                f"---\nType: training\nStatus: CURRENT\n"
                f"Scope: {task_type}\n"
                f"Owns-Paths:\n"
                f"Watch-Paths:\n{watch_lines}\n"
                f"Source-Runs: {', '.join(source_runs)}\n"
                f"Validated-At-Commit:\n"
                f"Last-Validated: {now}\n"
                f"Tags: training, reasoningbank, training-free-grpo\n---\n\n"
                f"# Training Memory: {task_type}\n\n"
                f"Reasoning items extracted from recursive-mode runs for `{task_type}` tasks.\n\n"
            )
            content = header + new_section
        else:
            content = existing + "\n" + new_section
        task_file.write_text(content, encoding="utf-8")

    def refresh_memory_index(self) -> None:
        """Refresh MEMORY.md registry bullets for domains/ and training/ shards."""
        if not self.memory_index.exists():
            return
        original = self.memory_index.read_text(encoding="utf-8")
        bullets = []
        for folder, label in ((self.domains_dir, "domains"), (self.training_dir, "training")):
            if not folder.exists():
                continue
            for path in sorted(folder.glob("*.md")):
                rel = f"{label}/{path.name}"
                text = path.read_text(encoding="utf-8")
                if "Status: CURRENT" not in text and "Status: SUSPECT" not in text:
                    continue
                title_match = re.search(r'^#\s+(.+)$', text, re.M)
                title = title_match.group(1).strip() if title_match else path.stem
                source = ""
                source_match = re.search(r'(?m)^Source-Runs:\s*(.+)$', text)
                if source_match:
                    source = f" (Source-Runs: {source_match.group(1).strip()})"
                bullets.append(f"- `{rel}` — {title}{source}")

        if not bullets:
            return

        block = "## Training Extraction Registry\n\n" + "\n".join(bullets) + "\n"
        marker_start = "<!-- RECURSIVE-TRAINING-REGISTRY:START -->"
        marker_end = "<!-- RECURSIVE-TRAINING-REGISTRY:END -->"
        wrapped = f"{marker_start}\n{block}{marker_end}"
        if marker_start in original and marker_end in original:
            pattern = re.compile(
                re.escape(marker_start) + r".*?" + re.escape(marker_end),
                re.DOTALL,
            )
            updated = pattern.sub(wrapped, original)
        elif "## Registry" in original:
            updated = original.replace("## Registry", f"## Registry\n\n{wrapped}\n", 1)
        else:
            updated = original.rstrip() + "\n\n" + wrapped + "\n"
        self.memory_index.write_text(updated, encoding="utf-8")

    def load_all_items_flat(self) -> Dict[str, str]:
        """Load all items as flat dict for tool-file generation."""
        items = {}
        for d in (self.domains_dir, self.training_dir):
            if not d.exists():
                continue
            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                if "Status: CURRENT" not in content:
                    continue
                for block in re.finditer(
                    r'### (RB-\d+):\s*(.+?)\n\n'
                    r'\*\*Description:\*\*\s*(.+?)\n\n'
                    r'\*\*Content:\*\*\s*(.+?)(?=\n\n```|\n### |\Z)',
                    content, re.DOTALL
                ):
                    rb_id = block.group(1)
                    title = block.group(2).strip()
                    desc = block.group(3).strip()
                    content_text = block.group(4).strip()
                    items[rb_id] = f"**{title}**: {desc} {content_text}"
        return items


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

async def train_repo(
    repo_root: str,
    incremental_run_id: Optional[str] = None,
    winner_only_threshold: int = MIN_WINNER_ONLY_GROUP_SIZE,
) -> int:
    repo_path = Path(repo_root).resolve()
    runs_dir = repo_path / ".recursive" / "run"
    if not runs_dir.exists():
        print(f"ERROR: No .recursive/run/ at {runs_dir}")
        return 1

    print(f"Scanning {runs_dir} ...")
    rollouts = parse_all_runs(runs_dir, require_phase8_locked=True)
    if incremental_run_id:
        before = len(rollouts)
        rollouts = filter_rollouts_for_training(rollouts, incremental_run_id)
        print(
            f"Incremental filter for {incremental_run_id}: "
            f"kept {len(rollouts)}/{before} rollouts in the target subsystem"
        )
        if not rollouts:
            print(f"ERROR: Run '{incremental_run_id}' not found among Phase-8-locked training inputs.")
            return 1
    print(f"Loaded {len(rollouts)} rollouts from {len({r.run_id for r in rollouts})} runs")
    if len(rollouts) < 2:
        print("WARNING: < 2 rollouts. Results will be weak.")

    groups = group_by_subsystem(rollouts)
    print(f"Formed {len(groups)} subsystem groups")
    for sub, g in groups.items():
        print(f"  - {sub} ({len(g)} runs)")

    rb_memory = ReasoningBankMemory(repo_path)

    total_items = 0
    processed = 0
    skipped_insufficient = 0
    extractor_failed = False

    for subsystem, group in groups.items():
        print(f"\nSubsystem: {subsystem} ({len(group)} rollouts)")

        mode, winners, losers = classify_group(group, winner_only_threshold)

        if mode == "insufficient":
            w = sum(1 for r in group if r.is_complete_winner)
            l = len(group) - w
            print(f"  Skipping — insufficient signal ({w} wins, {l} losses, threshold={winner_only_threshold})")
            skipped_insufficient += 1
            continue

        print(f"  Mode: {mode} ({len(winners)} wins, {len(losers)} losses)")

        # Load existing items for deduplication hints in the prompt
        existing_items = []
        for d in (rb_memory.domains_dir, rb_memory.training_dir):
            for f in d.glob("*.md"):
                content = f.read_text(encoding="utf-8")
                for block in re.finditer(
                    r'### (RB-\d+):\s*(.+?)\n\n\*\*Description:\*\*\s*(.+?)\n\n\*\*Content:\*\*\s*(.+?)(?=\n\n```|\n### |\Z)',
                    content, re.DOTALL
                ):
                    existing_items.append({
                        "rb_id": block.group(1),
                        "title": block.group(2).strip(),
                        "description": block.group(3).strip(),
                        "content": block.group(4).strip(),
                    })

        print(f"  Extracting ReasoningBank items ...")
        try:
            items = await extract_reasoningbank_items(
                mode, subsystem, winners, losers, existing_items
            )
        except ExtractionUnavailableError as exc:
            print(f"\nTraining failed: {exc}")
            extractor_failed = True
            break

        items = rb_memory.filter_new_items(items)
        if items:
            items_by_task_type: Dict[str, List[dict]] = defaultdict(list)

            source_runs = list({r.run_id for r in group})
            winner_runs = list({r.run_id for r in group if r.is_complete_winner})
            changed_paths = list({f for r in group for f in r.changed_files})

            written = rb_memory.write_domain_memory(
                subsystem, items, source_runs, winner_runs, changed_paths
            )
            if not written:
                print(f"  No new items after dedup")
                continue

            for item in written:
                tt = item.get("task_type", "general")
                items_by_task_type[tt].append(item)

            for tt, task_items in items_by_task_type.items():
                rb_memory.write_training_memory(tt, subsystem, task_items, source_runs, winner_runs)

            print(f"  Added {len(written)} items across {len(items_by_task_type)} task types:")
            for tt, task_items in sorted(items_by_task_type.items()):
                print(f"    [{tt}] ({len(task_items)} items)")
                for item in task_items:
                    print(f"      - [{item.get('rb_id', 'NEW')}] {item['title']}: {item['description'][:60]}...")
            total_items += len(written)
            processed += 1
        else:
            print(f"  No items extracted")

    if extractor_failed:
        print(f"\nTraining aborted: extractor unavailable ({processed} groups processed, {total_items} items extracted)")
        return 2

    if total_items > 0:
        rb_memory.refresh_memory_index()

    print(f"\nTraining complete: {processed} groups processed, {total_items} items extracted")
    if total_items == 0:
        if skipped_insufficient == len(groups) or processed == 0:
            print("No training items written (insufficient groups or empty extraction).")
            return 3
    return 0


def main():
    parser = argparse.ArgumentParser(description="Repository-local Training-Free GRPO + ReasoningBank")
    parser.add_argument("--repo-root", type=str, required=True)
    parser.add_argument("--incremental", action="store_true",
                        help="Limit extraction to the subsystem of --run-id, keeping peer runs in that subsystem")
    parser.add_argument("--run-id", type=str,
                        help="Target run id (required with --incremental)")
    parser.add_argument("--winner-only-threshold", type=int, default=MIN_WINNER_ONLY_GROUP_SIZE,
                        help="Minimum winners for winner-only extraction when no losers exist (default: 2)")
    args = parser.parse_args()

    if args.incremental and not args.run_id:
        print("ERROR: --incremental requires --run-id")
        sys.exit(1)
    if args.run_id and not args.incremental:
        print("NOTE: --run-id without --incremental is ignored; passing all Phase-8-locked runs.")

    incremental_id = args.run_id if args.incremental else None
    raise SystemExit(asyncio.run(train_repo(args.repo_root, incremental_id, args.winner_only_threshold)))


if __name__ == "__main__":
    main()
