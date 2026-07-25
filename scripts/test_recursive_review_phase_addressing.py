#!/usr/bin/env python3
"""Behavior tests for generic review phase addressing."""

from __future__ import annotations

import importlib.util
import hashlib
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills/recursive-mode/scripts"
sys.path.insert(0, str(RUNTIME))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


phase_rules = load_module(RUNTIME / "recursive_phase_rules.py", "phase_addressing_phase_rules")
review = load_module(RUNTIME / "recursive_review_ledger.py", "phase_addressing_review_ledger")
surface = load_module(RUNTIME / "recursive_review_surface.py", "phase_addressing_review_surface")


class ReviewFixture:
    def __init__(self, root: Path, artifact_file: str, *, run_id: str = "demo", review_id: str = "audit-review") -> None:
        self.root = root
        self.run = root / ".recursive/run" / run_id
        self.run.mkdir(parents=True, exist_ok=True)
        (self.run / "00-requirements.md").write_text("## Requirements\n\n### R1 Demo\n", encoding="utf-8")
        self.artifact_file = artifact_file
        self.phase_key = phase_rules.audited_phase_key(artifact_file)
        assert self.phase_key is not None
        self.review_id = review_id
        self.review = self.run / "evidence/reviews" / self.phase_key / review_id
        (self.review / "passes").mkdir(parents=True)
        self.artifact = self.run / artifact_file

    @property
    def ledger_rel(self) -> str:
        return f"/.recursive/run/{self.run.name}/evidence/reviews/{self.phase_key}/{self.review_id}/ledger.md"

    def bundle_rel(self, pass_id: str) -> str:
        return f"/.recursive/run/{self.run.name}/evidence/review-bundles/{self.phase_key}/{self.review_id}/{pass_id}.md"

    def pass_rel(self, pass_id: str) -> str:
        return f"/.recursive/run/{self.run.name}/evidence/reviews/{self.phase_key}/{self.review_id}/passes/{pass_id}.md"

    def artifact_content(self, pass_id: str, pass_hash: str, bundle_hash: str, *, author_text: str = "Author-owned audit evidence.") -> str:
        return f"""Run: `{self.run.name}`
Phase: `{self.artifact_file}`
Status: `DRAFT`
LockedAt: `none`
LockHash: `none`

## Review Metadata

- Review ID: {self.review_id}
- Review Ledger Path: `{self.ledger_rel}`
- Latest Verified Pass: `{self.pass_rel(pass_id)}`
- Latest Verified Pass Hash: {pass_hash}
- Review Bundle Path: `{self.bundle_rel(pass_id)}`
- Review Bundle Hash: {bundle_hash}

## Author Audit

- {author_text}
Audit: PASS
Coverage: PASS
Approval: PASS
"""

    def write_terminal(
        self,
        pass_number: int = 1,
        *,
        previous_path: str = "none",
        previous_hash: str = "none",
        author_text: str = "Author-owned audit evidence.",
        findings: str = "- none",
        pending: str = "none",
    ) -> tuple[Path, str]:
        pass_id = f"{pass_number:04d}"
        skeleton = self.artifact_content(pass_id, "0" * 64, "0" * 64, author_text=author_text)
        bundle_rel = self.bundle_rel(pass_id)
        bundle_path = self.root / bundle_rel.lstrip("/")
        bundle_path.parent.mkdir(parents=True, exist_ok=True)
        baseline = subprocess.check_output(["git", "-C", str(self.root), "rev-parse", "HEAD"], text=True).strip()
        surface_section = "\n".join(surface.render(surface.capture(
            self.root,
            run_id=self.run.name,
            baseline=baseline,
            comparison="working-tree",
            references=[],
        )))
        bundle = f"""Run: `/.recursive/run/{self.run.name}/`
Phase: `{self.artifact_file}`
Phase Key: `{self.phase_key}`
Review ID: `{self.review_id}`
Pass: `{pass_id}`
Role: `controller`
Bundle Path: `{bundle_rel}`
Artifact Path: `/.recursive/run/{self.run.name}/{self.artifact_file}`
Artifact Content Hash: `{hashlib.sha256(skeleton.encode('utf-8')).hexdigest()}`
Audit Payload Hash: `{review.audit_payload_hash(skeleton)}`
Audit Payload Profile: `{review.AUDIT_PAYLOAD_PROFILE}`
Review Ledger Path: `{self.ledger_rel}`
GeneratedAt: `2026-07-12T00:00:00Z`

## Bundle Scope
- immutable test bundle

{surface_section}
"""
        bundle_path.write_text(bundle, encoding="utf-8")
        bundle_hash = hashlib.sha256(bundle_path.read_bytes()).hexdigest()
        pass_rel = self.pass_rel(pass_id)
        ledger_content = f"""## Review Scope

- Review ID: {self.review_id}
- Pass: {pass_id}
- Ledger Path: `{self.ledger_rel}`
- Previous Pass: {previous_path if previous_path == 'none' else f'`{previous_path}`'}
- Previous Pass Hash: {previous_hash}
- Reviewed Artifact: `{bundle_rel}`
- Artifact Hash: {bundle_hash}
- Diff Basis: `{bundle_rel}`
- Changed Files:
  - `/.recursive/run/{self.run.name}/{self.artifact_file}`
- Evidence Basis:
  - `{bundle_rel}`

## Findings

{findings}

## Verdict

- Result: PASS
- Open Findings: none
- Pending Scheduled Handoffs: {pending}
- Controller: controller
- Verified Pass: `{pass_rel}`
- Verified Pass Hash: HASH
"""
        digest = review.normalized_snapshot_hash(ledger_content)
        ledger_content = ledger_content.replace("Verified Pass Hash: HASH", f"Verified Pass Hash: {digest}")
        pass_path = self.root / pass_rel.lstrip("/")
        pass_path.write_text(ledger_content, encoding="utf-8")
        ledger_path = self.review / "ledger.md"
        ledger_path.write_text(ledger_content, encoding="utf-8")
        self.artifact.write_text(self.artifact_content(pass_id, digest, bundle_hash, author_text=author_text), encoding="utf-8")
        return ledger_path, digest

    def scheduled_finding(self, owner: str) -> str:
        owner_phase_key = phase_rules.audited_phase_key(owner)
        if owner_phase_key is None:
            raise ValueError(f"scheduled owner is not audited: {owner}")
        destination = f"/.recursive/run/{self.run.name}/evidence/reviews/scheduled/{owner_phase_key}/inventory.md"
        return f"""### F-001

- Discovered in pass: 0001
- Kind: test-gap
- Location: `{self.artifact_file}:audit`
- Observed: later-phase evidence is pending
- Expected: later-phase evidence is captured
- Contract: `/.recursive/RECURSIVE.md`
- Technical impact: audit evidence would be incomplete
- Required outcome: capture the later-phase evidence
- Verification: inspect the owner phase receipt
- Depends on: none
- Disposition: scheduled
- Owner phase: {owner}
- Scheduling basis: `/.recursive/RECURSIVE.md` assigns this evidence to the owner phase
- Destination: `{destination}`
- Claimed outcome: none
- Claimed changes: none
- Claimed verification: none
- Controller verification: controller verified scheduling authority
"""

    def write_handoff(self, owner: str) -> Path:
        owner_phase_key = phase_rules.audited_phase_key(owner)
        if owner_phase_key is None:
            raise ValueError(f"scheduled owner is not audited: {owner}")
        destination = self.run / "evidence/reviews/scheduled" / owner_phase_key / "inventory.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(f"""# Scheduled Finding Handoff Inventory

## {self.review_id}/F-001

- Source Ledger: `{self.ledger_rel}`
- Finding ID: F-001
- Kind: test-gap
- Location: `{self.artifact_file}:audit`
- Observed: later-phase evidence is pending
- Expected: later-phase evidence is captured
- Contract: `/.recursive/RECURSIVE.md`
- Technical impact: audit evidence would be incomplete
- Required outcome: capture the later-phase evidence
- Verification: inspect the owner phase receipt
- Owner phase: {owner}
- Scheduling basis: `/.recursive/RECURSIVE.md` assigns this evidence to the owner phase
- Status: pending
- Consumed in: none
- Controller verification: none
""", encoding="utf-8")
        return destination


class RecursiveReviewPhaseAddressingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.root), "config", "user.name", "Test"], check=True)
        (self.root / "surface-seed.txt").write_text("seed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.root), "add", "surface-seed.txt"], check=True)
        subprocess.run(["git", "-C", str(self.root), "commit", "-qm", "surface baseline"], check=True)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_audit_payload_hash_excludes_only_controller_control_surfaces(self) -> None:
        artifact = """Run: `demo`
Phase: `03.5`
Status: `DRAFT`
LockedAt: `none`
LockHash: `none`

## Review Metadata

- Review ID: implementation-review
- Review Ledger Path: `/.recursive/run/demo/evidence/reviews/phase-3-5/implementation-review/ledger.md`
- Latest Verified Pass: none
- Latest Verified Pass Hash: none
- Review Bundle Path: `/.recursive/run/demo/evidence/review-bundles/phase-3-5/implementation-review/0001.md`
- Review Bundle Hash: none

## Author Audit

- Requirement R1 remains satisfied.
Audit: FAIL
Coverage: FAIL
Approval: FAIL
"""
        baseline = review.audit_payload_hash(artifact)
        control_only = (
            artifact.replace("Status: `DRAFT`", "Status: `LOCKED`")
            .replace("LockedAt: `none`", "LockedAt: `2026-07-12T00:00:00Z`")
            .replace("LockHash: `none`", f"LockHash: `{'a' * 64}`")
            .replace("Latest Verified Pass: none", "Latest Verified Pass: `/pass.md`")
            .replace("Latest Verified Pass Hash: none", f"Latest Verified Pass Hash: {'b' * 64}")
            .replace("Review Bundle Hash: none", f"Review Bundle Hash: {'c' * 64}")
            .replace("Audit: FAIL", "Audit: PASS")
            .replace("Coverage: FAIL", "Coverage: PASS")
            .replace("Approval: FAIL", "Approval: PASS")
        )
        self.assertEqual(review.AUDIT_PAYLOAD_PROFILE, "recursive-review-audit-payload-v1")
        self.assertEqual(review.audit_payload_hash(control_only), baseline)
        without_lock_metadata = artifact.replace("LockedAt: `none`\n", "").replace("LockHash: `none`\n", "")
        self.assertEqual(review.audit_payload_hash(without_lock_metadata), baseline)
        self.assertNotEqual(
            review.audit_payload_hash(artifact.replace("Requirement R1 remains satisfied.", "Requirement R1 changed.")),
            baseline,
        )
        self.assertNotEqual(
            review.audit_payload_hash(artifact.replace("- Requirement R1 remains satisfied.", "- Requirement R1 remains satisfied.\n- Status: author-owned")),
            baseline,
        )
        fenced = artifact + """
```markdown
Audit: FAIL
Status: `DRAFT`
## Review Metadata
- Review ID: fenced-example
```
"""
        fenced_hash = review.audit_payload_hash(fenced)
        self.assertNotEqual(
            review.audit_payload_hash(fenced.replace("Audit: FAIL\nStatus:", "Audit: PASS\nStatus:")),
            fenced_hash,
        )
        header_fenced = artifact.replace(
            "\n## Review Metadata",
            "\n```markdown\nStatus: `DRAFT`\n## Review Metadata\n- Review ID: fenced-example\n```\n\n## Review Metadata",
            1,
        )
        header_fenced_hash = review.audit_payload_hash(header_fenced)
        for old, new in (
            ("Status: `DRAFT`\n##", "Status: `LOCKED`\n##"),
            ("## Review Metadata\n- Review ID: fenced-example", "## Other Metadata\n- Review ID: fenced-example"),
        ):
            with self.subTest(fenced_header_mutation=old):
                self.assertNotEqual(review.audit_payload_hash(header_fenced.replace(old, new)), header_fenced_hash)
        for prefix in ("    ", "\t"):
            with self.subTest(indented_code=repr(prefix)):
                indented_code = f"## Author Audit\n\n{prefix}Audit: FAIL\n"
                self.assertNotEqual(
                    review.audit_payload_hash(indented_code),
                    review.audit_payload_hash(indented_code.replace("FAIL", "PASS")),
                )
        three_space_list_gate = "## Audit Gates\n\n   - Audit: FAIL\n"
        self.assertEqual(
            review.audit_payload_hash(three_space_list_gate),
            review.audit_payload_hash(three_space_list_gate.replace("FAIL", "PASS")),
        )
        four_space_list_example = "## Author Audit\n\n    - Audit: FAIL\n"
        self.assertNotEqual(
            review.audit_payload_hash(four_space_list_example),
            review.audit_payload_hash(four_space_list_example.replace("FAIL", "PASS")),
        )
        metadata, issues = review.parse_review_metadata(artifact)
        self.assertFalse(issues, issues)
        self.assertEqual(metadata["Review ID"], "implementation-review")
        _metadata, hidden = review.parse_review_metadata(
            artifact.replace("- Review Bundle Hash: none", "- Review Bundle Hash: none\nhidden prose")
        )
        self.assertTrue(any("outside its exact field schema" in issue for issue in hidden), hidden)

        duplicate = artifact + """
## Review Metadata

- Review ID: author-owned-second-section
"""
        _metadata, duplicate_issues = review.parse_review_metadata(duplicate)
        self.assertTrue(any("exactly one" in issue for issue in duplicate_issues), duplicate_issues)
        self.assertNotEqual(
            review.audit_payload_hash(duplicate),
            review.audit_payload_hash(duplicate.replace("author-owned-second-section", "changed-second-section")),
        )

        duplicate_fixture = ReviewFixture(self.root, "03.5-code-review.md", run_id="duplicate-metadata")
        duplicate_fixture.write_terminal()
        duplicate_fixture.artifact.write_text(
            duplicate_fixture.artifact.read_text(encoding="utf-8") + duplicate,
            encoding="utf-8",
        )
        duplicate_result = review.validate_phase_artifact(
            self.root,
            duplicate_fixture.run,
            duplicate_fixture.artifact,
        )
        self.assertTrue(any("exactly one" in issue for issue in duplicate_result.issues), duplicate_result.issues)

    def test_generic_terminal_ledger_and_phase_adapter_cover_all_audited_phases(self) -> None:
        for index, (artifact_file, _phase_key) in enumerate(phase_rules.AUDITED_PHASE_REGISTRY, start=1):
            with self.subTest(artifact=artifact_file):
                fixture = ReviewFixture(self.root, artifact_file, run_id=f"matrix-{index}")
                ledger_path, _digest = fixture.write_terminal()
                ledger_result = review.validate_ledger(self.root, ledger_path)
                self.assertTrue(ledger_result.valid, ledger_result.issues)
                phase_result = review.validate_phase_artifact(self.root, fixture.run, fixture.artifact)
                self.assertTrue(phase_result.valid, phase_result.issues)
                if index == 1:
                    cli = subprocess.run(
                        [
                            sys.executable,
                            str(RUNTIME / "recursive-review-ledger.py"),
                            "--repo-root",
                            str(self.root),
                            "--run-id",
                            fixture.run.name,
                            "--phase-artifact",
                            artifact_file,
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    )
                    self.assertEqual(cli.returncode, 0, cli.stdout + cli.stderr)

    def test_non_phase_3_5_multipass_preserves_historical_bundles(self) -> None:
        fixture = ReviewFixture(self.root, "01-as-is.md", run_id="multipass")
        _ledger_path, hash1 = fixture.write_terminal()
        previous = fixture.pass_rel("0001")
        (self.root / "surface-seed.txt").write_text("changed before pass two\n", encoding="utf-8")
        ledger_path, _hash2 = fixture.write_terminal(2, previous_path=previous, previous_hash=hash1, author_text="Second-pass audit evidence.")
        result = review.validate_phase_artifact(self.root, fixture.run, fixture.artifact)
        self.assertTrue(result.valid, result.issues)

        bundle1 = self.root / fixture.bundle_rel("0001").lstrip("/")
        original = bundle1.read_bytes()
        bundle1.write_bytes(original + b"tamper\n")
        tampered = review.validate_ledger(self.root, ledger_path)
        self.assertTrue(any("bundle hash mismatch" in issue for issue in tampered.issues), tampered.issues)
        bundle1.unlink()
        missing = review.validate_ledger(self.root, ledger_path)
        self.assertTrue(any("bundle does not exist" in issue for issue in missing.issues), missing.issues)

    def test_rejects_wrong_phase_bundle_pass_traversal_and_duplicate_review_id(self) -> None:
        fixture = ReviewFixture(self.root, "02-to-be-plan.md", run_id="wrong-context")
        ledger_path, _digest = fixture.write_terminal()
        wrong_phase = fixture.run / "01-as-is.md"
        wrong_phase.write_text(fixture.artifact.read_text(encoding="utf-8"), encoding="utf-8")
        result = review.validate_phase_artifact(self.root, fixture.run, wrong_phase)
        self.assertTrue(any("does not match its run and audited phase" in issue for issue in result.issues), result.issues)

        content = ledger_path.read_text(encoding="utf-8")
        ledger_path.write_text(content.replace(fixture.bundle_rel("0001"), "/.recursive/run/wrong-context/evidence/review-bundles/phase-2/audit-review/0002.md"), encoding="utf-8")
        result = review.validate_ledger(self.root, ledger_path)
        self.assertTrue(any("canonical immutable bundle" in issue for issue in result.issues), result.issues)
        ledger_path.write_text(content.replace(fixture.ledger_rel, "/.recursive/run/wrong-context/../../escape/ledger.md"), encoding="utf-8")
        result = review.validate_ledger(self.root, ledger_path)
        self.assertTrue(any("Ledger Path" in issue for issue in result.issues), result.issues)

        duplicate_a = ReviewFixture(self.root, "01-as-is.md", run_id="duplicate", review_id="shared-review")
        duplicate_a.write_terminal()
        duplicate_b = ReviewFixture(self.root, "02-to-be-plan.md", run_id="duplicate", review_id="shared-review")
        duplicate_path, _digest = duplicate_b.write_terminal()
        result = review.validate_ledger(self.root, duplicate_path)
        self.assertTrue(any("globally unique" in issue for issue in result.issues), result.issues)

        wrong_bundle = ReviewFixture(self.root, "06-decisions-update.md", run_id="wrong-bundle")
        wrong_bundle.write_terminal()
        bundle_path = self.root / wrong_bundle.bundle_rel("0001").lstrip("/")
        bundle_path.write_text(
            bundle_path.read_text(encoding="utf-8").replace(
                "Artifact Path: `/.recursive/run/wrong-bundle/06-decisions-update.md`",
                "Artifact Path: `/.recursive/run/wrong-bundle/07-state-update.md`",
            ),
            encoding="utf-8",
        )
        result = review.validate_phase_artifact(self.root, wrong_bundle.run, wrong_bundle.artifact)
        self.assertTrue(any("Artifact Path" in issue for issue in result.issues), result.issues)

        wrong_phase_label = ReviewFixture(self.root, "07-state-update.md", run_id="wrong-phase-label")
        wrong_phase_label.write_terminal()
        bundle_path = self.root / wrong_phase_label.bundle_rel("0001").lstrip("/")
        bundle_path.write_text(
            bundle_path.read_text(encoding="utf-8").replace(
                "Phase: `07-state-update.md`",
                "Phase: `08-memory-impact.md`",
            ),
            encoding="utf-8",
        )
        result = review.validate_phase_artifact(self.root, wrong_phase_label.run, wrong_phase_label.artifact)
        self.assertTrue(any("bundle Phase does not match" in issue for issue in result.issues), result.issues)

    def test_rejects_current_and_historical_bundle_symlinks(self) -> None:
        current = ReviewFixture(self.root, "01-as-is.md", run_id="current-symlink")
        current_ledger, _digest = current.write_terminal()
        current_bundle = self.root / current.bundle_rel("0001").lstrip("/")
        current_shadow = current_bundle.with_name("same-content.md")
        current_shadow.write_bytes(current_bundle.read_bytes())
        current_bundle.unlink()
        current_bundle.symlink_to(current_shadow.name)
        result = review.validate_ledger(self.root, current_ledger)
        self.assertTrue(any("regular non-symlink" in issue for issue in result.issues), result.issues)

        historical = ReviewFixture(self.root, "02-to-be-plan.md", run_id="historical-symlink")
        _ledger, hash1 = historical.write_terminal()
        ledger_path, _hash2 = historical.write_terminal(
            2,
            previous_path=historical.pass_rel("0001"),
            previous_hash=hash1,
            author_text="Second pass.",
        )
        old_bundle = self.root / historical.bundle_rel("0001").lstrip("/")
        outside = self.root / "outside-bundle.md"
        outside.write_bytes(old_bundle.read_bytes())
        old_bundle.unlink()
        old_bundle.symlink_to(outside)
        result = review.validate_ledger(self.root, ledger_path)
        self.assertTrue(any("regular non-symlink" in issue for issue in result.issues), result.issues)

    def test_scheduled_owner_must_be_strictly_later_than_generic_source(self) -> None:
        cases = (
            ("same", "02-to-be-plan.md", False),
            ("earlier", "01-as-is.md", False),
            ("later", "04-test-summary.md", True),
        )
        for run_id, owner, expected_valid in cases:
            with self.subTest(owner=owner):
                fixture = ReviewFixture(self.root, "02-to-be-plan.md", run_id=f"scheduled-{run_id}")
                finding = fixture.scheduled_finding(owner)
                ledger_path, _digest = fixture.write_terminal(findings=finding, pending="F-001")
                fixture.write_handoff(owner)
                result = review.validate_ledger(self.root, ledger_path)
                if expected_valid:
                    self.assertTrue(result.valid, result.issues)
                else:
                    self.assertTrue(any("strictly later" in issue or "later canonical phase" in issue for issue in result.issues), result.issues)


if __name__ == "__main__":
    unittest.main(verbosity=2)
