#!/usr/bin/env python3
"""Behavior tests for review bundle and action-record generators."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills/recursive-mode/scripts"
BUNDLE = RUNTIME / "recursive-review-bundle.py"
ACTION = RUNTIME / "recursive-subagent-action.py"
ACTION_VALIDATOR = RUNTIME / "recursive_review_action.py"
sys.path.insert(0, str(RUNTIME))


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LINT = load_module(RUNTIME / "lint-recursive-run.py", "review_generator_lint")
STATUS = load_module(RUNTIME / "recursive-status.py", "review_generator_status")


class RecursiveReviewGeneratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.com"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        (self.repo / "product.txt").write_text("before\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "product.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "baseline"], check=True)
        self.baseline = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        self.run = self.repo / ".recursive/run/demo"
        self.run.mkdir(parents=True)
        (self.run / "00-worktree.md").write_text("\n".join((
            "## Diff Basis For Later Audits", "Baseline type: local commit", f"Baseline reference: {self.baseline}",
            "Comparison reference: working-tree", f"Normalized baseline: {self.baseline}", "Normalized comparison: working-tree",
            f"Normalized diff command: git diff --name-only {self.baseline}", "",
        )), encoding="utf-8")
        (self.run / "03.5-code-review.md").write_text("# Review\n", encoding="utf-8")
        (self.repo / "product.txt").write_text("after\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_script(self, script: Path, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, str(script), "--repo-root", str(self.repo), *args], text=True, capture_output=True, check=False)

    def validate_action_record(self, action: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(ACTION_VALIDATOR), "--repo-root", str(self.repo), "--action-record", f"/{action.relative_to(self.repo)}"],
            text=True,
            capture_output=True,
            check=False,
        )

    def create_working_review(self, *, evidence_ref: str | None = None) -> tuple[Path, Path]:
        (self.run / "02-to-be-plan.md").write_text("# Plan\n", encoding="utf-8")
        bundle_args = [
            "--run-id", "demo", "--phase", "02 TO-BE", "--role", "planner",
            "--artifact-path", "/.recursive/run/demo/02-to-be-plan.md",
            "--review-id", "plan-review", "--pass", "0001",
        ]
        if evidence_ref is not None:
            bundle_args.extend(("--evidence-ref", evidence_ref))
        generated = self.run_script(BUNDLE, *bundle_args)
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
        bundle = self.run / "evidence/review-bundles/phase-2/plan-review/0001.md"
        bundle_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
        ledger = self.run / "evidence/reviews/phase-2/plan-review/ledger.md"
        ledger.parent.mkdir(parents=True)
        ledger.write_text(f"""## Review Scope

- Review ID: plan-review
- Pass: 0001
- Ledger Path: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`
- Previous Pass: none
- Previous Pass Hash: none
- Reviewed Artifact: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`
- Artifact Hash: {bundle_hash}
- Diff Basis: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`
- Changed Files:
  - `/.recursive/run/demo/02-to-be-plan.md`
- Evidence Basis:
  - `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`

## Findings

### F-001

- Discovered in pass: 0001
- Kind: test-gap
- Location: `02-to-be-plan.md:review`
- Observed: plan verification is pending
- Expected: plan verification is reproducible
- Contract: `/.recursive/RECURSIVE.md`
- Technical impact: an unverified plan can drift
- Required outcome: record reproducible verification
- Verification: run the plan contract test
- Depends on: none
- Disposition: open
- Claimed outcome: none
- Claimed changes: none
- Claimed verification: none
- Controller verification: none

## Verdict

- Result: FAIL
- Open Findings: F-001
- Pending Scheduled Handoffs: none
- Controller: none
- Verified Pass: none
- Verified Pass Hash: none
""", encoding="utf-8")
        return ledger, bundle

    def validate_review_ledger(self, ledger: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(RUNTIME / "recursive-review-ledger.py"), "--repo-root", str(self.repo), "--ledger", f"/{ledger.relative_to(self.repo)}"],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_bundle_emits_protocol_pointer_and_canonical_ledger(self) -> None:
        result = self.run_script(BUNDLE, "--run-id", "demo", "--phase", "03.5 Code Review", "--role", "code-reviewer",
            "--artifact-path", "/.recursive/run/demo/03.5-code-review.md", "--review-id", "implementation-review",
            "--pass", "0001")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.run / "evidence/review-bundles/phase-3-5/implementation-review/0001.md").read_text(encoding="utf-8")
        self.assertIn("Review Ledger Path: `/.recursive/run/demo/evidence/reviews/phase-3-5/implementation-review/ledger.md`", content)
        self.assertIn("`/.agents/skills/recursive-review/references/finding-protocol.md`", content)
        for heading in ("`## Review Scope`", "`## Findings`", "`## Verdict`"):
            self.assertIn(heading, content)

    def test_phase_alias_uses_same_canonical_bundle_contract(self) -> None:
        for index, alias in enumerate(("3.5 Code Review", "3.5-code-review", "Phase 3.5 Code Review", "PHASE 03.5 CODE REVIEW"), start=1):
            with self.subTest(alias=alias):
                review_id = f"alias-review-{index}"
                result = self.run_script(BUNDLE, "--run-id", "demo", "--phase", alias, "--role", "code-reviewer",
                    "--artifact-path", "/.recursive/run/demo/03.5-code-review.md", "--review-id", review_id,
                    "--pass", "0001")
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                content = (self.run / f"evidence/review-bundles/phase-3-5/{review_id}/0001.md").read_text(encoding="utf-8")
                self.assertIn(f"/evidence/reviews/phase-3-5/{review_id}/ledger.md", content)

    def test_bundle_is_canonical_per_pass_and_refuses_overwrite(self) -> None:
        args = (
            "--run-id", "demo", "--phase", "03.5 Code Review", "--role", "code-reviewer",
            "--artifact-path", "/.recursive/run/demo/03.5-code-review.md",
            "--review-id", "implementation-review", "--pass", "0001",
        )
        result = self.run_script(BUNDLE, *args)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        path = self.run / "evidence/review-bundles/phase-3-5/implementation-review/0001.md"
        content = path.read_text(encoding="utf-8")
        for phrase in (
            "Phase Key: `phase-3-5`",
            "Review ID: `implementation-review`",
            "Pass: `0001`",
            "Artifact Path: `/.recursive/run/demo/03.5-code-review.md`",
            "Audit Payload Hash:",
            "Audit Payload Profile: `recursive-review-audit-payload-v1`",
            "Review Ledger Path: `/.recursive/run/demo/evidence/reviews/phase-3-5/implementation-review/ledger.md`",
        ):
            self.assertIn(phrase, content)
        before = path.read_bytes()
        repeated = self.run_script(BUNDLE, *args)
        self.assertNotEqual(repeated.returncode, 0)
        self.assertIn("Refusing to overwrite immutable review bundle", repeated.stdout)
        self.assertEqual(path.read_bytes(), before)

        (self.run / "02-to-be-plan.md").write_text("# Plan\n", encoding="utf-8")
        duplicate = self.run_script(
            BUNDLE,
            "--run-id", "demo", "--phase", "02 TO-BE", "--role", "planner",
            "--artifact-path", "/.recursive/run/demo/02-to-be-plan.md",
            "--review-id", "implementation-review", "--pass", "0001",
        )
        self.assertNotEqual(duplicate.returncode, 0)
        self.assertIn("globally unique", duplicate.stdout)

    def test_rejects_phase_artifact_mismatch(self) -> None:
        (self.run / "01-as-is.md").write_text("# AS-IS\n", encoding="utf-8")
        result = self.run_script(
            BUNDLE,
            "--run-id", "demo", "--phase", "08 Memory Impact", "--role", "analyst",
            "--artifact-path", "/.recursive/run/demo/01-as-is.md",
            "--review-id", "as-is-review", "--pass", "0001",
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not match audited artifact", result.stdout)

    def test_bundle_rejects_noncanonical_run_ids_before_filesystem_access(self) -> None:
        for run_id in ("../demo", "demo/../demo", "..\\demo", "demo\\..\\demo"):
            with self.subTest(run_id=run_id):
                result = self.run_script(
                    BUNDLE,
                    "--run-id", run_id, "--phase", "03.5 Code Review", "--role", "code-reviewer",
                    "--artifact-path", "/.recursive/run/demo/03.5-code-review.md",
                    "--review-id", "traversal-review", "--pass", "0001",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Run ID must be a canonical", result.stdout)
        self.assertFalse((self.repo / "outside").exists())

    def test_action_record_emits_structured_claims_without_disposition(self) -> None:
        _ledger, _bundle = self.create_working_review()
        result = self.run_script(ACTION, "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair review findings", "--execution-mode", "review-repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
            "--finding-claim", "F-001=fixed", "--finding-change", "F-001=product.txt",
            "--finding-verification", "F-001=python3 -m unittest tests.test_product",
            "--output-name", "repair.md")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        content = (self.run / "subagents/repair.md").read_text(encoding="utf-8")
        for phrase in ("## Claimed Findings", "Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`", "### F-001", "Claimed outcome: `fixed`", "`/product.txt`"):
            self.assertIn(phrase, content)
        self.assertNotIn("Disposition:", content)
        self.assertIn("- Claimed changes:\n  - `/product.txt`", content)
        self.assertIn("- Claimed verification:\n  - python3 -m unittest tests.test_product", content)

    def test_action_record_rejects_invalid_or_incomplete_claims(self) -> None:
        self.create_working_review()
        common = (
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE", "--purpose", "Repair",
            "--execution-mode", "review-repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
        )
        valid = self.run_script(
            ACTION,
            *common,
            "--finding-claim", "F-001=blocked",
            "--finding-verification", "F-001=dependency pending",
            "--output-name", "valid-claim.md",
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

        invalid_cases = (
            (("--finding-claim", "bug-1=fixed"), "--finding-claim must use F-NNN=value"),
            (("--finding-claim", "F-000=blocked", "--finding-verification", "F-000=blocked"), "--finding-claim must use F-NNN=value"),
            (("--finding-claim", "F-001=fixed"), "F-001 with claimed outcome fixed requires changed paths and verification"),
            (("--finding-claim", "F-001=rejected"), "F-001 claimed outcome must be one of"),
        )
        for extra, expected in invalid_cases:
            with self.subTest(extra=extra):
                result = self.run_script(ACTION, *common, *extra)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stdout)

        for alias in ("Phase 3.5 Code Review", "3.5-code-review"):
            alias_bypass = self.run_script(ACTION, "--run-id", "demo", "--subagent-id", "reviewer", "--phase", alias,
                "--purpose", "Review", "--execution-mode", "review", "--finding", "free prose")
            self.assertNotEqual(alias_bypass.returncode, 0)
            self.assertIn("require --review-ledger", alias_bypass.stdout)

    def test_audited_action_requires_structured_contract_and_phase_5_allows_unstructured_qa(self) -> None:
        self.create_working_review()
        action = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair plan review", "--execution-mode", "review-repair",
            "--artifact-path", "/.recursive/run/demo/02-to-be-plan.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--finding-claim", "F-001=fixed", "--finding-change", "F-001=02-to-be-plan.md",
            "--finding-verification", "F-001=python3 scripts/check.py", "--output-name", "plan-repair.md",
        )
        self.assertEqual(action.returncode, 0, action.stdout + action.stderr)
        action_content = (self.run / "subagents/plan-repair.md").read_text(encoding="utf-8")
        self.assertIn("Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`", action_content)
        self.assertIn("### F-001", action_content)
        self.assertNotIn("Disposition:", action_content)

        unstructured_review_finding = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "reviewer", "--phase", "02 TO-BE",
            "--purpose", "Review plan", "--execution-mode", "review", "--finding", "free prose",
        )
        self.assertNotEqual(unstructured_review_finding.returncode, 0)
        self.assertIn("require --review-ledger", unstructured_review_finding.stdout)

        phase5_finding = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "qa", "--phase", "05 Manual QA",
            "--purpose", "Record QA observation", "--execution-mode", "qa", "--finding", "button works",
            "--output-name", "qa.md",
        )
        self.assertEqual(phase5_finding.returncode, 0, phase5_finding.stdout + phase5_finding.stderr)

    def test_repair_and_audit_aliases_require_lossless_claims(self) -> None:
        for execution_mode in ("repair", "repairer", "review-repair", "self-audit", "delegated-audit"):
            with self.subTest(execution_mode=execution_mode):
                result = self.run_script(
                    ACTION,
                    "--run-id", "demo", "--subagent-id", "worker", "--phase", "02 TO-BE",
                    "--purpose", "Handle plan findings", "--execution-mode", execution_mode,
                    "--finding", "free prose",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("require --review-ledger", result.stdout)

        unstructured_audited_finding = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "implementer", "--phase", "02 TO-BE",
            "--purpose", "Perform non-review work", "--execution-mode", "implementer",
            "--finding", "non-review note", "--output-name", "non-review.md",
        )
        self.assertNotEqual(unstructured_audited_finding.returncode, 0)
        self.assertIn("Audited phases cannot use unstructured --finding", unstructured_audited_finding.stdout)

        non_review = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "implementer", "--phase", "02 TO-BE",
            "--purpose", "Perform non-review work", "--execution-mode", "implementer",
            "--output-name", "non-review.md",
        )
        self.assertEqual(non_review.returncode, 0, non_review.stdout + non_review.stderr)
        non_review_path = self.run / "subagents/non-review.md"
        non_review_path.write_text(
            non_review_path.read_text(encoding="utf-8").replace(
                "## Claimed Findings\n- none",
                "## Claimed Findings\n- Parser accepts invalid input contrary to contract",
            ),
            encoding="utf-8",
        )
        persisted_bypass = self.validate_action_record(non_review_path)
        self.assertNotEqual(persisted_bypass.returncode, 0)
        self.assertIn("unstructured finding in an audited phase", persisted_bypass.stdout)

    def test_persisted_action_phase_context_and_metadata_cardinality_fail_closed(self) -> None:
        generated = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "implementer", "--phase", "02 TO-BE",
            "--purpose", "Perform non-review work", "--execution-mode", "implementer",
            "--output-name", "phase-context.md",
        )
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
        action = self.run / "subagents/phase-context.md"
        base = action.read_text(encoding="utf-8").replace(
            "## Claimed Findings\n- none",
            "## Claimed Findings\n- Parser accepts invalid input contrary to contract",
        )

        phase_spoof = base.replace("- Phase: `02 TO-BE`", "- Phase: `05 Manual QA`")
        action.write_text(phase_spoof, encoding="utf-8")
        phase_content = """# Plan

Phase: `02 TO-BE`

## Audit Context

- Audit Execution Mode: subagent

## Subagent Contribution Verification

- Reviewed Action Records:
  - `/.recursive/run/demo/subagents/phase-context.md`
- Main-Agent Verification Performed:
  - inspected action claim
- Acceptance Decision: accepted
- Refresh Handling:
  - refreshed after review
- Repair Performed After Verification:
  - none
"""
        lint_issues = LINT.lint_subagent_contribution_verification(
            self.run / "02-to-be-plan.md", phase_content, self.run, self.repo, None
        )
        self.assertTrue(
            any("unstructured finding in an audited phase" in issue for issue in lint_issues),
            lint_issues,
        )
        status_issues = STATUS.collect_subagent_contribution_blockers(
            "02-to-be-plan.md", phase_content, self.run, self.repo, None
        )
        self.assertTrue(
            any("unstructured finding in an audited phase" in issue for issue in status_issues),
            status_issues,
        )

        spoofed_phase_content = phase_content.replace(
            "Phase: `02 TO-BE`",
            "Phase: `05 Manual QA`",
        )
        lint_issues = LINT.lint_subagent_contribution_verification(
            self.run / "02-to-be-plan.md", spoofed_phase_content, self.run, self.repo, None
        )
        self.assertTrue(
            any("unstructured finding in an audited phase" in issue for issue in lint_issues),
            lint_issues,
        )
        status_issues = STATUS.collect_subagent_contribution_blockers(
            "02-to-be-plan.md", spoofed_phase_content, self.run, self.repo, None
        )
        self.assertTrue(
            any("unstructured finding in an audited phase" in issue for issue in status_issues),
            status_issues,
        )

        ambiguous_records = {
            "duplicate-run-id": base.replace(
                "- Run ID: `demo`",
                "- Run ID: `demo`\n- Run ID: `demo`",
            ),
            "duplicate-phase": base.replace(
                "- Phase: `02 TO-BE`",
                "- Phase: `02 TO-BE`\n- Phase: `02 TO-BE`",
            ),
            "duplicate-execution-mode": base.replace(
                "- Execution Mode: `implementer`",
                "- Execution Mode: `implementer`\n- Execution Mode: `implementer`",
            ),
            "duplicate-metadata-section": base.replace(
                "## Inputs Provided",
                "## Metadata\n\n- Phase: `02 TO-BE`\n\n## Inputs Provided",
            ),
            "duplicate-claimed-findings-section": base.replace(
                "## Verification Handoff",
                "## Claimed Findings\n\n- duplicate prose\n\n## Verification Handoff",
            ),
        }
        for name, mutated in ambiguous_records.items():
            with self.subTest(name=name):
                action.write_text(mutated, encoding="utf-8")
                result = self.validate_action_record(action)
                self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertRegex(
                    result.stdout,
                    r"exactly one (## (Metadata|Claimed Findings) section|Run ID|Phase|Execution Mode)",
                )

    def test_review_and_repair_require_matching_immutable_bundle(self) -> None:
        ledger, bundle = self.create_working_review()
        base = (
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair plan review", "--execution-mode", "repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--finding-claim", "F-001=blocked", "--finding-verification", "F-001=awaiting dependency",
        )

        missing = self.run_script(ACTION, *base, "--output-name", "missing-bundle.md")
        self.assertNotEqual(missing.returncode, 0)
        self.assertIn("require --review-bundle", missing.stdout)
        self.assertFalse((self.run / "subagents/missing-bundle.md").exists())

        rejected_paths = (
            "/.recursive/run/other/evidence/review-bundles/phase-2/plan-review/0001.md",
            "/.recursive/run/demo/evidence/review-bundles/phase-1/plan-review/0001.md",
            "/.recursive/run/demo/evidence/review-bundles/phase-2/other-review/0001.md",
            "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/latest.md",
            "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0000.md",
            "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/9999.md",
        )
        for bundle_path in rejected_paths:
            with self.subTest(bundle_path=bundle_path):
                result = self.run_script(ACTION, *base, "--review-bundle", bundle_path)
                self.assertNotEqual(result.returncode, 0)

        valid_ledger = ledger.read_text(encoding="utf-8")
        valid_bundle = bundle.read_text(encoding="utf-8")
        ledger.write_text("## Review Scope\n\n## Findings\n\n## Verdict\n", encoding="utf-8")
        invalid_ledger = self.run_script(
            ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
            "--output-name", "invalid-ledger.md",
        )
        self.assertNotEqual(invalid_ledger.returncode, 0)
        self.assertFalse((self.run / "subagents/invalid-ledger.md").exists())
        ledger.write_text(valid_ledger, encoding="utf-8")

        fake_bundle = "Phase Key: `phase-2`\nReview ID: `plan-review`\nPass: `0001`\n"
        bundle.write_text(fake_bundle, encoding="utf-8")
        fake = self.run_script(ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md")
        self.assertNotEqual(fake.returncode, 0)

        for injected in ("Extra Metadata: `unexpected`\n", "Phase Key: `phase-2`\n"):
            with self.subTest(injected=injected.strip()):
                mutated = valid_bundle.replace("Review ID: `plan-review`\n", f"Review ID: `plan-review`\n{injected}")
                bundle.write_text(mutated, encoding="utf-8")
                mutated_hash = hashlib.sha256(bundle.read_bytes()).hexdigest()
                ledger.write_text(
                    valid_ledger.replace(
                        next(line for line in valid_ledger.splitlines() if line.startswith("- Artifact Hash:")),
                        f"- Artifact Hash: {mutated_hash}",
                    ),
                    encoding="utf-8",
                )
                result = self.run_script(ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md")
                self.assertNotEqual(result.returncode, 0)

        bundle.write_text(valid_bundle + "\n# changed after ledger hash\n", encoding="utf-8")
        ledger.write_text(valid_ledger, encoding="utf-8")
        hash_mismatch = self.run_script(ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md")
        self.assertNotEqual(hash_mismatch.returncode, 0)

        bundle.write_text(valid_bundle, encoding="utf-8")
        second = self.run_script(
            BUNDLE,
            "--run-id", "demo", "--phase", "02 TO-BE", "--role", "planner",
            "--artifact-path", "/.recursive/run/demo/02-to-be-plan.md",
            "--review-id", "plan-review", "--pass", "0002",
        )
        self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
        unbound = self.run_script(
            ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0002.md",
        )
        self.assertNotEqual(unbound.returncode, 0)

        valid = self.run_script(
            ACTION, *base, "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
            "--output-name", "valid-repair.md",
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)

        no_claim = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair plan review", "--execution-mode", "repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
        )
        self.assertNotEqual(no_claim.returncode, 0)
        self.assertIn("require at least one --finding-claim", no_claim.stdout)

    def test_action_claims_are_bound_to_open_ledger_rows_and_detect_tampering(self) -> None:
        ledger, _bundle = self.create_working_review()
        common = (
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair plan review", "--execution-mode", "repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
        )
        missing = self.run_script(
            ACTION, *common, "--finding-claim", "F-999=blocked",
            "--finding-verification", "F-999=not in ledger",
        )
        self.assertNotEqual(missing.returncode, 0)

        valid = self.run_script(
            ACTION, *common, "--finding-claim", "F-001=blocked",
            "--finding-verification", "F-001=dependency pending", "--output-name", "bound-action.md",
        )
        self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
        action = self.run / "subagents/bound-action.md"
        content = action.read_text(encoding="utf-8")
        self.assertIn("Review Pass: `0001`", content)
        self.assertIn("Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`", content)
        self.assertEqual(self.validate_action_record(action).returncode, 0)

        for name, mutated in (
            ("missing-id", content.replace("### F-001", "### F-999")),
            ("wrong-pass", content.replace("Review Pass: `0001`", "Review Pass: `0002`")),
            ("cross-ledger", content.replace("/plan-review/ledger.md", "/other-review/ledger.md")),
            ("missing-binding", content.replace("- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`\n", "").replace("- Review Pass: `0001`\n", "")),
            (
                "all-claim-bindings-removed",
                content.replace("- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`\n", "")
                .replace("- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`\n", "")
                .replace("- Review Pass: `0001`\n", ""),
            ),
            ("duplicate", content.replace("## Verification Handoff", content.split("### F-001", 1)[1].split("## Verification Handoff", 1)[0].join(("### F-001", "\n### F-001")) + "\n## Verification Handoff")),
        ):
            with self.subTest(name=name):
                action.write_text(mutated, encoding="utf-8")
                self.assertNotEqual(self.validate_action_record(action).returncode, 0)
        action.write_text(content, encoding="utf-8")

        terminal = ledger.read_text(encoding="utf-8").replace("- Disposition: open", "- Disposition: fixed").replace(
            "- Controller verification: none", "- Controller verification: controller verified"
        ).replace("- Open Findings: F-001", "- Open Findings: none")
        ledger.write_text(terminal, encoding="utf-8")
        self.assertNotEqual(self.validate_action_record(action).returncode, 0)

    def test_persisted_claim_schema_rejects_residual_prose_and_terminal_fields_everywhere(self) -> None:
        _ledger, _bundle = self.create_working_review()
        generated = self.run_script(
            ACTION,
            "--run-id", "demo", "--subagent-id", "repairer", "--phase", "02 TO-BE",
            "--purpose", "Repair plan review", "--execution-mode", "repair",
            "--review-ledger", "/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md",
            "--review-bundle", "/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md",
            "--finding-claim", "F-001=blocked", "--finding-verification", "F-001=dependency pending",
            "--output-name", "schema-action.md",
        )
        self.assertEqual(generated.returncode, 0, generated.stdout + generated.stderr)
        action = self.run / "subagents/schema-action.md"
        content = action.read_text(encoding="utf-8")
        phase_content = """# Plan

Phase: `02 TO-BE`

## Audit Context

- Audit Execution Mode: subagent

## Review Metadata

- Review Bundle Path: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`

## Subagent Contribution Verification

- Reviewed Action Records:
  - `/.recursive/run/demo/subagents/schema-action.md`
- Main-Agent Verification Performed:
  - inspected action claim
- Acceptance Decision: accepted
- Refresh Handling:
  - none
- Repair Performed After Verification:
  - none
"""
        mutations = {
            "terminal-disposition": content.replace("- Claimed outcome: `blocked`", "- Claimed outcome: `blocked`\n- Disposition: fixed"),
            "forged-controller": content.replace("- Claimed outcome: `blocked`", "- Claimed outcome: `blocked`\n- Controller verification: forged"),
            "unknown-bullet": content.replace("- Claimed outcome: `blocked`", "- Claimed outcome: `blocked`\n- Note: hidden"),
            "unknown-heading": content.replace("## Verification Handoff", "#### Hidden note\n\n## Verification Handoff"),
            "free-prose": content.replace("- Claimed outcome: `blocked`", "- Claimed outcome: `blocked`\nthis should not survive"),
            "wrong-metadata-order": content.replace(
                "- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`\n- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`",
                "- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-2/plan-review/ledger.md`\n- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-2/plan-review/0001.md`",
            ),
            "duplicate-metadata": content.replace(
                "- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`",
                "- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`\n- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`",
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(name=name):
                action.write_text(mutated, encoding="utf-8")
                direct = self.validate_action_record(action)
                self.assertNotEqual(direct.returncode, 0)
                self.assertIn("exact ordered Claimed Findings schema", direct.stdout)
                lint_issues = LINT.lint_subagent_action_record_file(action, self.repo, self.run, None)
                self.assertTrue(any("exact ordered Claimed Findings schema" in issue for issue in lint_issues), lint_issues)
                status_issues = STATUS.collect_subagent_contribution_blockers(
                    "02-to-be-plan.md", phase_content, self.run, self.repo, None
                )
                self.assertTrue(any("exact ordered Claimed Findings schema" in issue for issue in status_issues), status_issues)

    def test_current_pass_binds_changed_membership_bytes_and_evidence_state(self) -> None:
        evidence = self.run / "evidence/logs/review.txt"
        evidence.parent.mkdir(parents=True)
        evidence.write_text("evidence-v1\n", encoding="utf-8")
        link = self.repo / "reviewed-link"
        link.symlink_to("product.txt")
        ledger, bundle = self.create_working_review(
            evidence_ref="/.recursive/run/demo/evidence/logs/review.txt"
        )
        self.assertIn("## Reviewed Surface Snapshot", bundle.read_text(encoding="utf-8"))
        self.assertEqual(self.validate_review_ledger(ledger).returncode, 0)

        link.unlink()
        link.symlink_to("other-target.txt")
        changed_link = self.validate_review_ledger(ledger)
        self.assertNotEqual(changed_link.returncode, 0)
        self.assertIn("reviewed surface", changed_link.stdout.lower())
        link.unlink()
        link.symlink_to("product.txt")

        product = self.repo / "product.txt"
        product.write_text("after-byte-change\n", encoding="utf-8")
        changed_bytes = self.validate_review_ledger(ledger)
        self.assertNotEqual(changed_bytes.returncode, 0)
        self.assertIn("reviewed surface", changed_bytes.stdout.lower())

        product.write_text("after\n", encoding="utf-8")
        added = self.repo / "new-reviewed-file.txt"
        added.write_text("new\n", encoding="utf-8")
        changed_membership = self.validate_review_ledger(ledger)
        self.assertNotEqual(changed_membership.returncode, 0)
        self.assertIn("reviewed surface", changed_membership.stdout.lower())
        added.unlink()

        product.unlink()
        removed = self.validate_review_ledger(ledger)
        self.assertNotEqual(removed.returncode, 0)
        self.assertIn("reviewed surface", removed.stdout.lower())
        product.write_text("after\n", encoding="utf-8")

        original_mode = product.stat().st_mode
        product.chmod(original_mode ^ 0o100)
        changed_mode = self.validate_review_ledger(ledger)
        self.assertNotEqual(changed_mode.returncode, 0)
        self.assertIn("reviewed surface", changed_mode.stdout.lower())
        product.chmod(original_mode)

        evidence.write_text("evidence-v2\n", encoding="utf-8")
        changed_evidence = self.validate_review_ledger(ledger)
        self.assertNotEqual(changed_evidence.returncode, 0)
        self.assertIn("reviewed surface", changed_evidence.stdout.lower())

    def test_explicit_review_refs_must_be_regular_files(self) -> None:
        (self.run / "02-to-be-plan.md").write_text("# Plan\n", encoding="utf-8")
        evidence_dir = self.run / "evidence/logs"
        evidence_dir.mkdir(parents=True)
        evidence_file = evidence_dir / "review.txt"
        evidence_file.write_text("evidence\n", encoding="utf-8")
        evidence_link = evidence_dir / "review-link.txt"
        evidence_link.symlink_to(evidence_file.name)
        for name, reference in (
            ("directory", "/.recursive/run/demo/evidence/logs"),
            ("symlink", "/.recursive/run/demo/evidence/logs/review-link.txt"),
        ):
            with self.subTest(name=name):
                result = self.run_script(
                    BUNDLE,
                    "--run-id", "demo", "--phase", "02 TO-BE", "--role", "planner",
                    "--artifact-path", "/.recursive/run/demo/02-to-be-plan.md",
                    "--review-id", f"{name}-review", "--pass", "0001",
                    "--evidence-ref", reference,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("regular file", result.stdout.lower())

if __name__ == "__main__":
    unittest.main(verbosity=2)
