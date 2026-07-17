#!/usr/bin/env python3
"""Behavior contract for the single current Recursive workflow."""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills/recursive-mode/scripts"
sys.path.insert(0, str(SCRIPTS))


def load_module(file_name: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, SCRIPTS / file_name)
    if spec is None or spec.loader is None:
        raise RuntimeError(file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


phase_rules = load_module("recursive_phase_rules.py", "single_contract_phase_rules")
review = load_module("recursive_review_ledger.py", "single_contract_review_ledger")
lint = load_module("lint-recursive-run.py", "single_contract_lint")
closeout = load_module("recursive-closeout.py", "single_contract_closeout")


class RecursiveReviewSingleContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.run = self.root / ".recursive/run/demo"
        self.run.mkdir(parents=True)
        (self.run / "00-requirements.md").write_text(
            "## Requirements\n\n### R1 Demo\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_requirement_guards_apply_without_profile_detection(self) -> None:
        phase1 = self.run / "01-as-is.md"
        phase1.write_text("", encoding="utf-8")
        phase1_issues = lint.lint_phase_specific_rules(
            phase1,
            "",
            self.run,
            self.root,
            ["R1"],
            [],
        )
        self.assertIn("Missing or empty section: ## Source Requirement Inventory", phase1_issues)

        phase2 = self.run / "02-to-be-plan.md"
        phase2_issues = lint.lint_phase_specific_rules(
            phase2,
            "",
            self.run,
            self.root,
            ["R1"],
            [],
        )
        self.assertIn(
            "Requirement Mapping requires 01-as-is.md to contain ## Source Requirement Inventory",
            phase2_issues,
        )
        self.assertIn("Missing or empty section: ## Plan Drift Check", phase2_issues)

    def test_shared_review_seam_enforces_all_nine_audited_phases(self) -> None:
        for artifact in phase_rules.AUDITED_ARTIFACTS:
            with self.subTest(artifact=artifact):
                issues = review.collect_phase_issues(self.root, self.run, artifact, "")
                self.assertTrue(any("Review Ledger Path" in issue for issue in issues), issues)

    def test_heading_contract_uses_lossless_review_and_test_surface(self) -> None:
        removed = ("Gaps Found", "Repair Work Performed", "Audit Verdict")
        for artifact in phase_rules.AUDITED_ARTIFACTS:
            with self.subTest(artifact=artifact):
                headings = lint.get_artifact_required_sections(artifact)
                self.assertEqual(headings.count("Review Metadata"), 1)
                for heading in removed:
                    self.assertNotIn(heading, headings)
        phase_3_5_headings = lint.get_artifact_required_sections("03.5-code-review.md")
        for secondary_review_channel in (
            "Review Scope",
            "Findings",
            "Plan Alignment Assessment",
            "Code Quality Assessment",
            "Issues Found",
            "Verdict",
        ):
            self.assertNotIn(secondary_review_channel, phase_3_5_headings)
        phase_3_5_issues = lint.lint_phase_specific_rules(
            self.run / "03.5-code-review.md",
            "## Findings\n\n- Unledgered technical defect\n",
            self.run,
            self.root,
            [],
            [],
        )
        self.assertIn(
            "Phase 3.5 artifact must not duplicate ledger-owned section: ## Findings",
            phase_3_5_issues,
        )
        self.assertIn("Test Surface", lint.get_artifact_required_sections("02-to-be-plan.md"))

    def test_closeout_scaffolds_review_roots_for_audited_phases_only(self) -> None:
        for phase in ("04", "06", "07", "08"):
            with self.subTest(phase=phase):
                scaffold = closeout.build_scaffold(lint, self.root, self.run, phase, None, "")
                metadata, issues = review.parse_review_metadata(scaffold)
                self.assertFalse(issues, issues)
                self.assertEqual(list(metadata), review.REVIEW_METADATA_FIELDS)
                artifact = closeout.PHASE_CONFIG[phase]["file_name"]
                closeout.ensure_review_roots(self.run, artifact)
                phase_key = phase_rules.audited_phase_key(artifact)
                self.assertTrue((self.run / f"evidence/reviews/{phase_key}").is_dir())
                self.assertTrue((self.run / f"evidence/review-bundles/{phase_key}").is_dir())

        phase5 = closeout.build_scaffold(lint, self.root, self.run, "05", None, "")
        self.assertNotIn("## Review Metadata", phase5)
        closeout.ensure_review_roots(self.run, "05-manual-qa.md")
        self.assertFalse((self.run / "evidence/reviews/phase-5").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
