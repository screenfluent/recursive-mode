#!/usr/bin/env python3
"""Behavior and integration tests for the Recursive Review ledger validator."""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
import tempfile
import unittest
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "recursive-mode" / "scripts"
sys.path.insert(0, str(RUNTIME))

import recursive_phase_rules as phase_rules


MODULE_PATH = RUNTIME / "recursive_review_ledger.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


ledger = load_module(MODULE_PATH, "recursive_review_ledger")
surface = load_module(RUNTIME / "recursive_review_surface.py", "recursive_review_surface_test")


def snapshot_hash(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n")
    normalized = re.sub(r"(?m)^- Verified Pass Hash:.*(?:\n|$)", "", normalized)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class ReviewLedgerFixture:
    def __init__(self, root: Path, run_id: str = "demo") -> None:
        self.root = root
        self.run_id = run_id
        self.run = root / ".recursive/run" / run_id
        self.review_id = "implementation-review"
        self.review = self.run / "evidence/reviews/phase-3-5" / self.review_id
        self.review.mkdir(parents=True)
        (self.review / "passes").mkdir()
        self.reviewed = root / "reviewed.txt"
        self.reviewed.write_text("reviewed\n", encoding="utf-8")
        self.artifact = self.run / "03.5-code-review.md"
        self.run.mkdir(parents=True, exist_ok=True)
        (self.run / "00-requirements.md").write_text("## Requirements\n\n### R1 Demo\n", encoding="utf-8")

    @property
    def ledger_rel(self) -> str:
        return f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/{self.review_id}/ledger.md"

    def bundle_rel(self, pass_id: str) -> str:
        return f"/.recursive/run/{self.run_id}/evidence/review-bundles/phase-3-5/{self.review_id}/{pass_id}.md"

    def pass_rel(self, pass_id: str) -> str:
        return f"/.recursive/run/{self.run_id}/evidence/reviews/phase-3-5/{self.review_id}/passes/{pass_id}.md"

    def artifact_content(self, pass_id: str, pass_hash: str, bundle_hash: str) -> str:
        return f"""# Review

## Review Metadata

- Review ID: {self.review_id}
- Review Ledger Path: `{self.ledger_rel}`
- Latest Verified Pass: `{self.pass_rel(pass_id)}`
- Latest Verified Pass Hash: {pass_hash}
- Review Bundle Path: `{self.bundle_rel(pass_id)}`
- Review Bundle Hash: {bundle_hash}
"""

    def write_bundle(self, pass_id: str) -> tuple[Path, str]:
        bundle_rel = self.bundle_rel(pass_id)
        bundle_path = self.root / bundle_rel.lstrip("/")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        skeleton = self.artifact_content(pass_id, "0" * 64, "0" * 64)
        baseline = subprocess.check_output(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True
        ).strip()
        surface_section = "\n".join(surface.render(surface.capture(
            self.root,
            run_id=self.run_id,
            baseline=baseline,
            comparison="working-tree",
            references=[],
        )))
        content = f"""Run: `/.recursive/run/{self.run_id}/`
Phase: `03.5-code-review.md`
Phase Key: `phase-3-5`
Review ID: `{self.review_id}`
Pass: `{pass_id}`
Role: `controller`
Bundle Path: `{bundle_rel}`
Artifact Path: `/.recursive/run/{self.run_id}/03.5-code-review.md`
Artifact Content Hash: `{hashlib.sha256(skeleton.encode('utf-8')).hexdigest()}`
Audit Payload Hash: `{ledger.audit_payload_hash(skeleton)}`
Audit Payload Profile: `{ledger.AUDIT_PAYLOAD_PROFILE}`
Review Ledger Path: `{self.ledger_rel}`
GeneratedAt: `2026-07-12T00:00:00Z`

## Bundle Scope
- immutable test bundle

{surface_section}
"""
        bundle_path.write_text(content, encoding="utf-8")
        return bundle_path, hashlib.sha256(bundle_path.read_bytes()).hexdigest()

    def finding(
        self,
        finding_id: str = "F-001",
        *,
        disposition: str = "fixed",
        depends_on: str = "none",
        observed: str = "old behavior",
        kind: str = "contract-violation",
        scheduled: dict[str, str] | None = None,
    ) -> str:
        lines = [
            f"### {finding_id}", "", "- Discovered in pass: 0001", f"- Kind: {kind}",
        ]
        if kind == "other":
            lines.append("- Kind justification: measurable maintainability regression")
        lines.extend([
            "- Location: `reviewed.txt:1`", f"- Observed: {observed}", "- Expected: new behavior",
            "- Contract: `contract.md`", "- Technical impact: incorrect behavior", "- Required outcome: behavior corrected",
            "- Verification: `python3 test.py`", f"- Depends on: {depends_on}", f"- Disposition: {disposition}",
        ])
        if disposition == "scheduled":
            assert scheduled is not None
            lines.extend([
                f"- Owner phase: {scheduled['owner']}", f"- Scheduling basis: {scheduled['basis']}",
                f"- Destination: `{scheduled['destination']}`",
            ])
        if disposition in {"rejected", "deferred", "out-of-scope"}:
            lines.append("- Disposition rationale: controller-approved rationale")
        if disposition == "deferred":
            lines.extend(["- Owner: human-owner", "- Human approval: Szymon", "- Destination: `tracked-plan.md`"])
        if disposition == "out-of-scope":
            lines.extend(["- Human decision: Szymon", "- Destination: `tracked-plan.md`"])
        if disposition == "open":
            lines.extend(["- Claimed outcome: none", "- Claimed changes: none", "- Claimed verification: none", "- Controller verification: none"])
        elif disposition == "fixed":
            lines.extend(["- Claimed outcome: fixed", "- Claimed changes: `reviewed.txt`", "- Claimed verification: `python3 test.py`", "- Controller verification: controller checked diff and test"])
        else:
            lines.extend(["- Claimed outcome: none", "- Claimed changes: none", "- Claimed verification: none", "- Controller verification: controller checked authority and destination"])
        return "\n".join(lines)

    def render(
        self,
        *,
        pass_number: int = 1,
        findings: str = "- none",
        result: str = "PASS",
        open_findings: str = "none",
        pending: str = "none",
        previous_path: str = "none",
        previous_hash: str = "none",
    ) -> tuple[str, str]:
        pass_id = f"{pass_number:04d}"
        pass_rel = self.pass_rel(pass_id)
        _bundle_path, bundle_hash = self.write_bundle(pass_id)
        bundle_rel = self.bundle_rel(pass_id)
        content = f"""## Review Scope

- Review ID: {self.review_id}
- Pass: {pass_id}
- Ledger Path: `{self.ledger_rel}`
- Previous Pass: {previous_path if previous_path == 'none' else f'`{previous_path}`'}
- Previous Pass Hash: {previous_hash}
- Reviewed Artifact: `{bundle_rel}`
- Artifact Hash: {bundle_hash}
- Diff Basis: `{bundle_rel}`
- Changed Files:
  - `/reviewed.txt`
- Evidence Basis:
  - `{bundle_rel}`

## Findings

{findings}

## Verdict

- Result: {result}
- Open Findings: {open_findings}
- Pending Scheduled Handoffs: {pending}
- Controller: controller
- Verified Pass: `{pass_rel}`
- Verified Pass Hash: HASH
"""
        digest = snapshot_hash(content)
        return content.replace("Verified Pass Hash: HASH", f"Verified Pass Hash: {digest}"), digest

    def write_terminal(self, **kwargs) -> tuple[Path, str]:
        content, digest = self.render(**kwargs)
        pass_number = kwargs.get("pass_number", 1)
        pass_path = self.review / "passes" / f"{pass_number:04d}.md"
        pass_path.write_text(content, encoding="utf-8")
        ledger_path = self.review / "ledger.md"
        ledger_path.write_text(content, encoding="utf-8")
        bundle_hash = hashlib.sha256((self.root / self.bundle_rel(f"{pass_number:04d}").lstrip("/")).read_bytes()).hexdigest()
        self.artifact.write_text(self.artifact_content(f"{pass_number:04d}", digest, bundle_hash), encoding="utf-8")
        return ledger_path, digest

    def write_handoff(
        self,
        finding_id: str,
        *,
        status: str = "pending",
        owner: str = "04-test-summary.md",
        create_owner: bool = True,
        kind: str = "test-gap",
        basis: str = "`/.recursive/RECURSIVE.md` assigns planned suite execution to Phase 4",
    ) -> Path:
        owner_phase_key = phase_rules.audited_phase_key(owner)
        if owner_phase_key is None:
            raise ValueError(f"scheduled owner is not audited: {owner}")
        dest_rel = f"/.recursive/run/{self.run_id}/evidence/reviews/scheduled/{owner_phase_key}/inventory.md"
        path = self.root / dest_rel.lstrip("/")
        path.parent.mkdir(parents=True, exist_ok=True)
        if create_owner:
            (self.run / owner).write_text(f"# {owner}\n", encoding="utf-8")
        consumed = "none" if status == "pending" else f"/.recursive/run/{self.run_id}/{owner}"
        controller = "none" if status == "pending" else "controller verified target evidence"
        path.write_text(f"""# Scheduled Finding Handoff Inventory

## {self.review_id}/{finding_id}

- Source Ledger: `{self.ledger_rel}`
- Finding ID: {finding_id}
- Kind: {kind}
- Location: `reviewed.txt:1`
- Observed: old behavior
- Expected: new behavior
- Contract: `contract.md`
- Technical impact: incorrect behavior
- Required outcome: behavior corrected
- Verification: `python3 test.py`
- Owner phase: {owner}
- Scheduling basis: {basis}
- Status: {status}
- Consumed in: {consumed if consumed == 'none' else f'`{consumed}`'}
- Controller verification: {controller}
""", encoding="utf-8")
        return path


class RecursiveReviewLedgerTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "surface-seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "surface-seed.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "surface baseline"], check=True)
        self.fixture = ReviewLedgerFixture(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def lock_artifact(self, path: Path) -> None:
        content = path.read_text(encoding="utf-8") if path.exists() else f"# {path.name}\n"
        content = re.sub(r"(?m)^Status:.*\n?", "", content)
        content = re.sub(r"(?m)^LockedAt:.*\n?", "", content)
        content = re.sub(r"(?m)^LockHash:.*\n?", "", content)
        content = f"Status: `LOCKED`\nLockedAt: `2026-07-12T00:00:00Z`\nLockHash: HASH\n{content}"
        digest = phase_rules.lock_hash_from_content(content)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content.replace("LockHash: HASH", f"LockHash: `{digest}`"), encoding="utf-8")

    def test_valid_terminal_ledger_and_phase_pointers(self) -> None:
        path, _digest = self.fixture.write_terminal()
        result = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.ledger_path, path)

    def test_rejects_hash_byte_sync_pointer_and_false_pass_errors(self) -> None:
        path, _digest = self.fixture.write_terminal()
        path.write_text(path.read_text(encoding="utf-8").replace("Verified Pass Hash: ", "Verified Pass Hash: dead"), encoding="utf-8")
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("hash" in issue.lower() for issue in issues))
        self.assertTrue(any("byte-for-byte" in issue.lower() for issue in issues))

        self.fixture = ReviewLedgerFixture(self.root, "pointer-demo")
        self.fixture.write_terminal()
        self.fixture.artifact.write_text(self.fixture.artifact.read_text(encoding="utf-8").replace("Latest Verified Pass Hash: ", "Latest Verified Pass Hash: bad"), encoding="utf-8")
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("artifact" in issue.lower() and "hash" in issue.lower() for issue in issues))

        self.fixture = ReviewLedgerFixture(self.root, "open-demo")
        self.fixture.write_terminal(findings=self.fixture.finding(disposition="open"), result="PASS", open_findings="none")
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("pass" in issue.lower() and "open" in issue.lower() for issue in issues))

    def test_rejects_mutated_prior_finding_and_dependency_graph_errors(self) -> None:
        pass1, hash1 = self.fixture.render(findings=self.fixture.finding(disposition="open"), result="FAIL", open_findings="F-001")
        pass1_path = self.fixture.review / "passes/0001.md"
        pass1_path.write_text(pass1, encoding="utf-8")
        previous = f"/.recursive/run/demo/evidence/reviews/phase-3-5/{self.fixture.review_id}/passes/0001.md"
        mutated = self.fixture.finding(disposition="fixed", observed="mutated behavior")
        self.fixture.write_terminal(pass_number=2, findings=mutated, previous_path=previous, previous_hash=hash1)
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("immutable" in issue.lower() for issue in issues))

        for run_id, depends in (("missing-dep", "F-999"), ("self-dep", "F-001")):
            fixture = ReviewLedgerFixture(self.root, run_id)
            fixture.write_terminal(findings=fixture.finding(depends_on=depends))
            issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
            self.assertTrue(any("depends on" in issue.lower() for issue in issues))

        fixture = ReviewLedgerFixture(self.root, "cycle")
        findings = fixture.finding("F-001", depends_on="F-002") + "\n\n" + fixture.finding("F-002", depends_on="F-001")
        fixture.write_terminal(findings=findings)
        issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
        self.assertTrue(any("cycle" in issue.lower() for issue in issues))

        fixture = ReviewLedgerFixture(self.root, "premature-fix")
        findings = fixture.finding("F-001", disposition="open") + "\n\n" + fixture.finding("F-002", depends_on="F-001")
        fixture.write_terminal(findings=findings, result="FAIL", open_findings="F-001")
        issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
        self.assertTrue(any("cannot be fixed until prerequisite" in issue for issue in issues))

        fixture = ReviewLedgerFixture(self.root, "rejected-prerequisite")
        findings = fixture.finding("F-001", disposition="rejected") + "\n\n" + fixture.finding("F-002", depends_on="F-001")
        fixture.write_terminal(findings=findings)
        issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
        self.assertTrue(any("cannot be fixed until prerequisite F-001 is fixed" in issue for issue in issues), issues)

    def test_rejects_n_minus_two_tamper_terminal_reopen_and_schema_tricks(self) -> None:
        finding_open = self.fixture.finding(disposition="open")
        pass1, hash1 = self.fixture.render(findings=finding_open, result="FAIL", open_findings="F-001")
        (self.fixture.review / "passes/0001.md").write_text(pass1, encoding="utf-8")
        previous1 = f"/.recursive/run/demo/evidence/reviews/phase-3-5/{self.fixture.review_id}/passes/0001.md"
        pass2, hash2 = self.fixture.render(pass_number=2, findings=finding_open, result="FAIL", open_findings="F-001", previous_path=previous1, previous_hash=hash1)
        (self.fixture.review / "passes/0002.md").write_text(pass2, encoding="utf-8")
        previous2 = f"/.recursive/run/demo/evidence/reviews/phase-3-5/{self.fixture.review_id}/passes/0002.md"
        self.fixture.write_terminal(pass_number=3, findings=self.fixture.finding(), previous_path=previous2, previous_hash=hash2)
        pass1_path = self.fixture.review / "passes/0001.md"
        pass1_path.write_text(pass1_path.read_text(encoding="utf-8").replace("old behavior", "tampered N-2"), encoding="utf-8")
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("Previous Pass Hash mismatch" in issue for issue in issues))

        fixture = ReviewLedgerFixture(self.root, "reopen")
        pass1, hash1 = fixture.render(findings=fixture.finding())
        (fixture.review / "passes/0001.md").write_text(pass1, encoding="utf-8")
        previous = f"/.recursive/run/reopen/evidence/reviews/phase-3-5/{fixture.review_id}/passes/0001.md"
        fixture.write_terminal(pass_number=2, findings=fixture.finding(disposition="open"), result="FAIL", open_findings="F-001", previous_path=previous, previous_hash=hash1)
        issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
        self.assertTrue(any("terminal finding reopened" in issue for issue in issues))

        fixture = ReviewLedgerFixture(self.root, "schema")
        path, _ = fixture.write_terminal()
        malformed = path.read_text(encoding="utf-8").replace("## Verdict", "## Verdict\n\n```markdown\n## Nits\n```", 1)
        _document, parse_issues = ledger.parse_document(malformed)
        self.assertTrue(any("code fences" in issue for issue in parse_issues))
        duplicate = path.read_text(encoding="utf-8").replace("- Result: PASS", "- Result: PASS\n- Result: PASS")
        _document, parse_issues = ledger.parse_document(duplicate)
        self.assertTrue(any("duplicate" in issue.lower() for issue in parse_issues))

        duplicate_heading = path.read_text(encoding="utf-8").replace("## Verdict", "## Review Scope\n\n- Review ID: duplicate\n\n## Verdict")
        _document, parse_issues = ledger.parse_document(duplicate_heading)
        self.assertTrue(any("top-level sections" in issue for issue in parse_issues))

        duplicate_id = self.fixture.finding("F-001") + "\n\n" + self.fixture.finding("F-001")
        content, _digest = self.fixture.render(findings=duplicate_id)
        _document, parse_issues = ledger.parse_document(content)
        self.assertTrue(any("duplicate finding ID" in issue for issue in parse_issues))

        for residual in ("free prose", "#### Observation", "* malformed bullet"):
            finding = self.fixture.finding().replace("- Observed: old behavior", f"- Observed: old behavior\n{residual}")
            content, _digest = self.fixture.render(findings=finding)
            _document, parse_issues = ledger.parse_document(content)
            self.assertTrue(any("outside its exact field schema" in issue for issue in parse_issues), (residual, parse_issues))

    def test_accepts_working_next_pass_and_historical_artifact_hash(self) -> None:
        finding_open = self.fixture.finding(disposition="open")
        pass1, hash1 = self.fixture.render(findings=finding_open, result="FAIL", open_findings="F-001")
        (self.fixture.review / "passes/0001.md").write_text(pass1, encoding="utf-8")
        self.fixture.reviewed.write_text("repaired\n", encoding="utf-8")
        previous = f"/.recursive/run/demo/evidence/reviews/phase-3-5/{self.fixture.review_id}/passes/0001.md"
        working, _digest = self.fixture.render(
            pass_number=2,
            findings=finding_open,
            result="FAIL",
            open_findings="F-001",
            previous_path=previous,
            previous_hash=hash1,
        )
        working = re.sub(r"- Controller: .*", "- Controller: none", working)
        working = re.sub(r"- Verified Pass: .*", "- Verified Pass: none", working)
        working = re.sub(r"- Verified Pass Hash: .*", "- Verified Pass Hash: none", working)
        ledger_path = self.fixture.review / "ledger.md"
        ledger_path.write_text(working, encoding="utf-8")

        result = ledger.validate_ledger(self.root, ledger_path)
        self.assertTrue(result.valid, result.issues)

    def test_all_terminal_working_fail_is_valid_but_completed_fail_is_not(self) -> None:
        terminal_finding = self.fixture.finding(disposition="fixed")
        pass1, hash1 = self.fixture.render(findings=terminal_finding)
        (self.fixture.review / "passes/0001.md").write_text(pass1, encoding="utf-8")
        previous = f"/.recursive/run/demo/evidence/reviews/phase-3-5/{self.fixture.review_id}/passes/0001.md"
        working, _digest = self.fixture.render(
            pass_number=2,
            findings=terminal_finding,
            result="FAIL",
            open_findings="none",
            previous_path=previous,
            previous_hash=hash1,
        )
        working = re.sub(r"- Controller: .*", "- Controller: none", working)
        working = re.sub(r"- Verified Pass: .*", "- Verified Pass: none", working)
        working = re.sub(r"- Verified Pass Hash: .*", "- Verified Pass Hash: none", working)
        ledger_path = self.fixture.review / "ledger.md"
        ledger_path.write_text(working, encoding="utf-8")
        result = ledger.validate_ledger(self.root, ledger_path)
        self.assertTrue(result.valid, result.issues)

        completed = ReviewLedgerFixture(self.root, "completed-fail")
        completed_path, _digest = completed.write_terminal(
            findings=completed.finding(disposition="fixed"),
            result="FAIL",
            open_findings="none",
        )
        result = ledger.validate_ledger(self.root, completed_path)
        self.assertTrue(any("completed FAIL" in issue for issue in result.issues), result.issues)

    def test_working_pass_cannot_claim_pass_without_snapshot(self) -> None:
        completed_path, _digest = self.fixture.write_terminal()
        completed = ledger.validate_ledger(self.root, completed_path)
        self.assertTrue(completed.valid, completed.issues)

        working_fixture = ReviewLedgerFixture(self.root, "working-pass-bypass")
        working, _digest = working_fixture.render(result="PASS", open_findings="none")
        working = re.sub(r"- Controller: .*", "- Controller: none", working)
        working = re.sub(r"- Verified Pass: .*", "- Verified Pass: none", working)
        working = re.sub(r"- Verified Pass Hash: .*", "- Verified Pass Hash: none", working)
        working_path = working_fixture.review / "ledger.md"
        working_path.write_text(working, encoding="utf-8")

        result = ledger.validate_ledger(self.root, working_path)
        self.assertTrue(any("working ledger must use Result: FAIL" in issue for issue in result.issues), result.issues)

    def test_malformed_history_reports_errors_without_crashing(self) -> None:
        path, _digest = self.fixture.write_terminal()
        path.write_text(path.read_text(encoding="utf-8").replace("- Pass: 0001", "- Pass: nope"), encoding="utf-8")
        result = ledger.validate_ledger(self.root, path)
        self.assertFalse(result.valid)
        self.assertTrue(any("Pass must" in issue for issue in result.issues), result.issues)

        fixture = ReviewLedgerFixture(self.root, "broken-history")
        (fixture.review / "passes/0001.md").write_text("## Review Scope\n\nbroken\n", encoding="utf-8")
        previous = f"/.recursive/run/broken-history/evidence/reviews/phase-3-5/{fixture.review_id}/passes/0001.md"
        fixture.write_terminal(pass_number=2, previous_path=previous, previous_hash="0" * 64)
        result = ledger.validate_ledger(self.root, fixture.review / "ledger.md")
        self.assertFalse(result.valid)
        self.assertTrue(any("could not be parsed" in issue for issue in result.issues), result.issues)

        fixture = ReviewLedgerFixture(self.root, "byte-hash")
        path, _digest = fixture.write_terminal()
        fixture.reviewed.write_bytes(b"reviewed\r\n")
        result = ledger.validate_ledger(self.root, path)
        self.assertTrue(any("current reviewed surface differs" in issue for issue in result.issues), result.issues)

    def test_rejects_path_traversal_symlink_and_malformed_scheduled_handoff(self) -> None:
        self.fixture.write_terminal()
        self.fixture.artifact.write_text(self.fixture.artifact.read_text(encoding="utf-8").replace(self.fixture.ledger_rel, "/.recursive/run/demo/../../outside/ledger.md"), encoding="utf-8")
        issues = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).issues
        self.assertTrue(any("does not match its run and audited phase" in issue for issue in issues), issues)

        fixture = ReviewLedgerFixture(self.root, "symlink")
        external = self.root / "external-ledger.md"
        external.write_text("external\n", encoding="utf-8")
        canonical = fixture.review / "ledger.md"
        canonical.symlink_to(external)
        result = ledger.validate_ledger(self.root, canonical)
        self.assertTrue(any("canonical" in issue or "control plane" in issue for issue in result.issues))

        fixture = ReviewLedgerFixture(self.root, "skipped-owner")
        destination = f"/.recursive/run/skipped-owner/evidence/reviews/scheduled/04-test-summary/{fixture.review_id}-inventory.md"
        # Destination is deliberately invalid and no physical handoff exists.
        scheduled = {"owner": "04-test-summary.md", "basis": "`/.recursive/RECURSIVE.md` assigns test execution", "destination": destination}
        fixture.write_terminal(findings=fixture.finding(disposition="scheduled", kind="test-gap", scheduled=scheduled), pending="F-001")
        issues = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact).issues
        self.assertTrue(any("scheduled Destination must be" in issue for issue in issues), issues)
        self.assertTrue(any("scheduled handoff does not exist" in issue for issue in issues), issues)

    def test_scheduled_handoff_is_run_only_physical_and_consumed_at_target(self) -> None:
        old_fixture = ReviewLedgerFixture(self.root, "old-owner-stem")
        old_destination = f"/.recursive/run/{old_fixture.run_id}/evidence/reviews/scheduled/04-test-summary/inventory.md"
        old_scheduled = {"owner": "04-test-summary.md", "basis": "`/.recursive/RECURSIVE.md` assigns planned suite execution to Phase 4", "destination": old_destination}
        old_fixture.write_terminal(findings=old_fixture.finding(disposition="scheduled", kind="test-gap", scheduled=old_scheduled), pending="F-001")
        old_issues = ledger.validate_phase_artifact(self.root, old_fixture.run, old_fixture.artifact).issues
        self.assertTrue(any("scheduled/phase-4/inventory.md" in issue for issue in old_issues), old_issues)

        destination = f"/.recursive/run/demo/evidence/reviews/scheduled/phase-4/inventory.md"
        scheduled = {"owner": "04-test-summary.md", "basis": "`/.recursive/RECURSIVE.md` assigns planned suite execution to Phase 4", "destination": destination}
        finding = self.fixture.finding(disposition="scheduled", kind="test-gap", scheduled=scheduled)
        self.fixture.write_terminal(findings=finding, pending="F-001")
        missing = ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact)
        self.assertFalse(missing.valid)
        self.assertTrue(any("handoff" in issue.lower() for issue in missing.issues))

        self.fixture.write_handoff("F-001", status="pending")
        self.assertTrue(ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).valid)
        target = ledger.validate_scheduled_handoffs(self.root, self.fixture.run, "04-test-summary.md")
        self.assertFalse(target.valid)
        self.assertTrue(any("unconsumed" in issue.lower() for issue in target.issues))
        self.fixture.write_handoff("F-001", status="consumed")
        self.assertTrue(ledger.validate_scheduled_handoffs(self.root, self.fixture.run, "04-test-summary.md").valid)
        self.assertTrue(ledger.validate_phase_artifact(self.root, self.fixture.run, self.fixture.artifact).valid)

        handoff = self.fixture.write_handoff("F-001", status="consumed")
        handoff.write_text(handoff.read_text(encoding="utf-8").replace("- Expected: new behavior", "- Expected: weakened behavior"), encoding="utf-8")
        target = ledger.validate_scheduled_handoffs(self.root, self.fixture.run, "04-test-summary.md")
        self.assertTrue(any("does not match source finding" in issue for issue in target.issues), target.issues)

        standalone = self.root / ".recursive/local/reviews/local-review"
        (standalone / "passes").mkdir(parents=True)
        run_content = (self.fixture.review / "ledger.md").read_text(encoding="utf-8")
        standalone_ledger = standalone / "ledger.md"
        standalone_ledger.write_text(run_content.replace(self.fixture.ledger_rel, "/.recursive/local/reviews/local-review/ledger.md"), encoding="utf-8")
        result = ledger.validate_ledger(self.root, standalone_ledger)
        self.assertTrue(any("standalone" in issue.lower() and "scheduled" in issue.lower() for issue in result.issues))

    def test_pending_handoff_activates_absent_optional_owner_without_precreation(self) -> None:
        fixture = ReviewLedgerFixture(self.root, "active-optional-owner")
        owner = "04-test-summary.md"
        owner_phase_key = phase_rules.audited_phase_key(owner)
        self.assertIsNotNone(owner_phase_key)
        destination = f"/.recursive/run/{fixture.run_id}/evidence/reviews/scheduled/{owner_phase_key}/inventory.md"
        scheduled = {"owner": owner, "basis": "`/.recursive/RECURSIVE.md` assigns planned suite execution to Phase 4", "destination": destination}
        fixture.write_terminal(findings=fixture.finding(disposition="scheduled", kind="test-gap", scheduled=scheduled), pending="F-001")
        fixture.write_handoff("F-001", owner=owner, create_owner=False, kind="test-gap", basis=scheduled["basis"])

        self.assertFalse((fixture.run / owner).exists())
        result = ledger.validate_phase_artifact(self.root, fixture.run, fixture.artifact)
        self.assertTrue(result.valid, result.issues)
        active, active_issues = ledger.get_active_scheduled_owner_phases(self.root, fixture.run)
        self.assertEqual(active_issues, [])
        self.assertEqual(active, {owner})

        for artifact in phase_rules.PHASE_SEQUENCE[: phase_rules.phase_index(owner)]:
            if artifact in phase_rules.OPTIONAL_PHASES and artifact != "03.5-code-review.md":
                continue
            self.lock_artifact(fixture.run / artifact)
        self.assertEqual(phase_rules.get_next_legal_phase(fixture.run, activated_phases=active), owner)
        blockers = phase_rules.get_prerequisite_blockers("06-decisions-update.md", fixture.run, activated_phases=active)
        self.assertTrue(any(item["artifact"] == owner and item["status"] == "MISSING" for item in blockers), blockers)
        status = subprocess.run([sys.executable, str(RUNTIME / "recursive-status.py"), "--repo-root", str(self.root), "--run-id", fixture.run_id], text=True, capture_output=True, check=False)
        self.assertEqual(status.returncode, 0, status.stderr)
        self.assertIn("Next Legal Phase: 00-requirements.md", status.stdout)
        self.assertIn("Current Phase: 0 (Requirements)", status.stdout)
        self.assertIn("Status: LOCKED*", status.stdout)
        later = fixture.run / "06-decisions-update.md"
        later.write_text("# Premature Phase 6 scaffold\n", encoding="utf-8")
        lock = subprocess.run([sys.executable, str(RUNTIME / "recursive-lock.py"), "--repo-root", str(self.root), "--run-id", fixture.run_id, "--artifact", later.name], text=True, capture_output=True, check=False)
        self.assertNotEqual(lock.returncode, 0)
        self.assertIn(f"{owner}: MISSING", lock.stdout)

        handoff = self.root / destination.lstrip("/")
        valid_handoff = handoff.read_text(encoding="utf-8")
        handoff.write_text(valid_handoff.replace("# Scheduled Finding Handoff Inventory\n", "# Scheduled Finding Handoff Inventory\nmalformed prose\n"), encoding="utf-8")
        active, active_issues = ledger.get_active_scheduled_owner_phases(self.root, fixture.run)
        self.assertEqual(active, set())
        self.assertTrue(any("outside record schema" in issue for issue in active_issues), active_issues)
        blocked_status = subprocess.run(
            [sys.executable, str(RUNTIME / "recursive-status.py"), "--repo-root", str(self.root), "--run-id", fixture.run_id],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(blocked_status.returncode, 0, blocked_status.stderr)
        self.assertIn("Next Legal Phase: BLOCKED", blocked_status.stdout)

    def test_lint_status_lock_and_verify_consume_the_shared_validator(self) -> None:
        self.fixture.write_terminal()
        ledger_path = self.fixture.review / "ledger.md"
        ledger_path.write_text(ledger_path.read_text(encoding="utf-8").replace("Verified Pass Hash: ", "Verified Pass Hash: bad"), encoding="utf-8")
        lint = load_module(RUNTIME / "lint-recursive-run.py", "slice2_lint")
        status = load_module(RUNTIME / "recursive-status.py", "slice2_status")
        lock = load_module(RUNTIME / "recursive-lock.py", "slice2_lock")
        verify = load_module(RUNTIME / "verify-locks.py", "slice2_verify")
        content = self.fixture.artifact.read_text(encoding="utf-8")

        lint_issues = lint.lint_phase_specific_rules(self.fixture.artifact, content, self.fixture.run, self.root, [], [])
        self.assertTrue(any("Recursive review" in issue for issue in lint_issues))
        status_issues = status.collect_phase_specific_blockers("03.5-code-review.md", content, self.fixture.run, self.root, [], [])
        self.assertTrue(any("Recursive review" in issue for issue in status_issues))
        lock_issues, _content = lock.validate_lockable(lint, self.root, self.fixture.run, self.fixture.artifact)
        self.assertTrue(any("Recursive review" in issue for issue in lock_issues))
        for artifact in phase_rules.get_prerequisites("04-test-summary.md", self.fixture.run):
            self.lock_artifact(self.fixture.run / artifact)
        semantic_blockers = lock.get_semantic_prerequisite_blockers(
            phase_rules,
            lint,
            self.root,
            self.fixture.run,
            "04-test-summary.md",
            frozenset(),
        )
        self.assertTrue(
            any(blocker["artifact"] == "03.5-code-review.md" and blocker["status"] == "INVALID" for blocker in semantic_blockers),
            semantic_blockers,
        )
        verify_issues = verify.collect_recursive_review_issues(self.root, self.fixture.run, "03.5-code-review.md", content)
        self.assertTrue(any("Recursive review" in issue for issue in verify_issues))

    def test_verify_fix_does_not_rehash_phase_with_invalid_ledger(self) -> None:
        self.fixture.write_terminal()
        ledger_path = self.fixture.review / "ledger.md"
        ledger_path.write_text(ledger_path.read_text(encoding="utf-8").replace("Verified Pass Hash: ", "Verified Pass Hash: bad"), encoding="utf-8")
        content = self.fixture.artifact.read_text(encoding="utf-8")
        content = "Status: `LOCKED`\nLockedAt: `2026-07-12T00:00:00Z`\nLockHash: `" + ("0" * 64) + "`\n" + content + "\nCoverage: PASS\nApproval: PASS\n"
        self.fixture.artifact.write_text(content, encoding="utf-8")
        before = self.fixture.artifact.read_bytes()
        result = subprocess.run([sys.executable, str(RUNTIME / "verify-locks.py"), "--repo-root", str(self.root), "--run-id", "demo", "--fix"], text=True, capture_output=True, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.fixture.artifact.read_bytes(), before)

    def test_audit_payload_ignores_lock_metadata_insertion(self) -> None:
        draft = "Status: `DRAFT`\n\n## TODO\n\n- [x] reviewed\n\nCoverage: PASS\nApproval: PASS\n"
        locked = "Status: `LOCKED`\nLockedAt: `2026-07-12T00:00:00Z`\nLockHash: `" + ("a" * 64) + "`\n\n## TODO\n\n- [x] reviewed\n\nCoverage: PASS\nApproval: PASS\n"
        self.assertEqual(ledger.audit_payload_hash(draft), ledger.audit_payload_hash(locked))



if __name__ == "__main__":
    unittest.main(verbosity=2)
