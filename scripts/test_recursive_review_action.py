#!/usr/bin/env python3
"""Behavior tests for the installed Recursive Review action-record parser."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "recursive-mode" / "scripts"
sys.path.insert(0, str(RUNTIME))

import recursive_review_action as action


class RecursiveReviewActionTest(unittest.TestCase):
    def action_record(
        self,
        *,
        phase: str,
        execution_mode: str,
        findings: str = "- none",
        review_bundle: str = "none",
        routed_role: str = "planner",
    ) -> str:
        return f"""# Subagent Action Record

## Metadata
- Subagent ID: `worker-1`
- Run ID: `demo`
- Phase: `{phase}`
- Purpose: `delegated task`
- Execution Mode: `{execution_mode}`
- Timestamp: `2026-01-01T00:00:00Z`
- Action Record Path: `/.recursive/run/demo/subagents/worker-1.md`

## Inputs Provided
- Current Artifact: `/.recursive/run/demo/02-to-be-plan.md`
- Artifact Content Hash: `abc`
- Upstream Artifacts:
  - none
- Addenda:
  - none
- Review Bundle: `{review_bundle}`
- Diff Basis: `baseline..working-tree`
- Code Refs:
  - `/product.py`
- Memory Refs:
  - none
- Audit / Task Questions:
  - verify the delegated task

## Routing
- Router Used: `recursive-router`
- Routed Role: `{routed_role}`
- Routed CLI: `codex`
- Routed Model: `gpt-5`
- Routing Config Path: `/.recursive/config/recursive-router.json`
- Routing Discovery Path: `none`
- Routing Resolution Basis: `role route`
- Routing Fallback Reason: `none`
- CLI Probe Summary: `available`
- Prompt Bundle Path: `none`
- Invocation Exit Code: `0`
- Output Capture Paths:
  - none

## Claimed Actions Taken
- completed the delegated task

## Claimed File Impact
### Created
- none
### Modified
- none
### Reviewed
- `/product.py`
### Relevant but Untouched
- none

## Claimed Artifact Impact
### Read
- `/.recursive/run/demo/02-to-be-plan.md`
### Updated
- none
### Evidence Used
- none

## Claimed Findings
{findings}

## Verification Handoff
- Inspect first:
  - `/product.py`
- Notes:
  - controller verification required
"""

    def structured_action(self, execution_mode: str = "review") -> str:
        bundle = "/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md"
        findings = """- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md`
- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-3/current-review/ledger.md`
- Review Pass: 0001
- Claims: none"""
        return self.action_record(
            phase="Phase 3",
            execution_mode=execution_mode,
            findings=findings,
            review_bundle=bundle,
            routed_role="code-reviewer",
        )

    def test_fixed_claim_uses_exact_structured_schema(self) -> None:
        content = """## Claimed Findings

- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md`
- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-3/review/ledger.md`
- Review Pass: 0001

### F-001
- Claimed outcome: `fixed`
- Claimed changes:
  - `/product.py`
- Claimed verification:
  - `python -m unittest`
"""
        claims, issues = action.parse_claims(content)
        self.assertEqual(claims, {"F-001": "fixed"})
        self.assertEqual(issues, [])

    def test_claim_parser_rejects_residual_prose_and_incomplete_fixed_claim(self) -> None:
        content = """## Claimed Findings

- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md`
- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-3/review/ledger.md`
- Review Pass: 0001

Advice before the finding.

### F-001
- Claimed outcome: `fixed`
- Claimed changes:
  - none
- Claimed verification:
  - none
"""
        _claims, issues = action.parse_claims(content)
        self.assertTrue(issues)

    def test_audited_phase_rejects_unstructured_findings(self) -> None:
        content = self.action_record(
            phase="Phase 3",
            execution_mode="implementer",
            findings="- issue found",
        )
        result = action.validate_action_record(
            ROOT,
            content,
            expected_run="demo",
            expected_phase="Phase 3",
            owning_artifact="03-implementation-summary.md",
        )
        self.assertFalse(result.valid)
        self.assertIn(
            "unstructured finding in an audited phase must use the canonical review ledger",
            result.issues,
        )

    def test_non_audited_action_may_remain_unstructured(self) -> None:
        content = self.action_record(
            phase="Phase 5",
            execution_mode="manual QA",
            findings="- observation only",
        )
        result = action.validate_action_record(
            ROOT,
            content,
            expected_run="demo",
            expected_phase="Phase 5",
            owning_artifact="05-manual-qa.md",
        )
        self.assertTrue(result.valid, result.issues)

    def test_full_schema_accepts_unstructured_planner_and_implementer_records(self) -> None:
        for phase, execution_mode in (("Phase 2", "planner"), ("Phase 3", "implementer")):
            with self.subTest(execution_mode=execution_mode):
                result = action.validate_action_record(
                    ROOT,
                    self.action_record(phase=phase, execution_mode=execution_mode),
                    expected_run="demo",
                    expected_phase=phase,
                )
                self.assertTrue(result.valid, result.issues)

    def test_full_schema_rejects_residual_lines_unknown_bullets_headings_and_tail(self) -> None:
        valid = self.action_record(phase="Phase 2", execution_mode="planner")
        mutations = {
            "title prose": valid.replace(
                "# Subagent Action Record\n\n## Metadata",
                "# Subagent Action Record\nResidual prose.\n\n## Metadata",
            ),
            "unknown field": valid.replace(
                "- Purpose: `delegated task`",
                "- Purpose: `delegated task`\n- Unknown Metadata: `residual`",
            ),
            "section prose": valid.replace(
                "## Claimed Actions Taken\n- completed the delegated task",
                "## Claimed Actions Taken\nResidual prose.\n- completed the delegated task",
            ),
            "unknown subsection": valid.replace(
                "### Relevant but Untouched\n- none",
                "### Relevant but Untouched\n- none\n### Unknown Impact\n- none",
            ),
            "unknown path bullet": valid.replace(
                "### Created\n- none",
                "### Created\n- residual prose",
            ),
            "unknown nested bullet": valid.replace(
                "- Notes:\n  - controller verification required",
                "- Notes:\n  - controller verification required\n- Unknown Handoff:\n  - residual",
            ),
            "tail prose": f"{valid}\nResidual tail.\n",
        }
        for name, content in mutations.items():
            with self.subTest(name=name):
                result = action.validate_action_record(
                    ROOT,
                    content,
                    expected_run="demo",
                    expected_phase="Phase 2",
                )
                self.assertFalse(result.valid, name)
                self.assertTrue(
                    any("canonical" in issue or "grammar" in issue for issue in result.issues),
                    result.issues,
                )

    def test_cli_path_normalizer_accepts_convenience_forms_but_rejects_ambiguous_paths(self) -> None:
        accepted = {
            "src/app.rs": "src/app.rs",
            "/src/app.rs": "src/app.rs",
            r"src\comma,name.rs": "src/comma,name.rs",
        }
        for raw, expected in accepted.items():
            with self.subTest(raw=raw):
                self.assertEqual(action.normalize_repo_path_argument(raw), (expected, None))

        rejected = (
            "",
            " src/app.rs",
            "src/app.rs ",
            "src/\napp.rs",
            "src/\rapp.rs",
            "src//app.rs",
            "src/./app.rs",
            "src/../app.rs",
            "C:/src/app.rs",
            r"C:\src\app.rs",
            "//server/share/app.rs",
            r"\\server\share\app.rs",
        )
        for raw in rejected:
            with self.subTest(raw=raw):
                normalized, issue = action.normalize_repo_path_argument(raw)
                self.assertIsNone(normalized)
                self.assertIsNotNone(issue)

    def test_full_schema_requires_canonical_display_for_every_path_surface(self) -> None:
        valid = self.action_record(phase="Phase 2", execution_mode="planner")
        mutations = {
            "action record path": valid.replace(
                "`/.recursive/run/demo/subagents/worker-1.md`",
                "`.recursive/run/demo/subagents/worker-1.md`",
            ),
            "current artifact": valid.replace(
                "`/.recursive/run/demo/02-to-be-plan.md`",
                "`C:/absolute.md`",
                1,
            ),
            "input list": valid.replace("  - `/product.py`", "  - `/src/../product.py`", 1),
            "routing scalar": valid.replace(
                "`/.recursive/config/recursive-router.json`",
                "`/.recursive//config/router.json`",
            ),
            "routing list": valid.replace(
                "- Output Capture Paths:\n  - none",
                "- Output Capture Paths:\n  - `output.md`",
            ),
            "file impact": valid.replace("### Reviewed\n- `/product.py`", "### Reviewed\n- `/product.py `"),
            "artifact impact": valid.replace(
                "### Read\n- `/.recursive/run/demo/02-to-be-plan.md`",
                "### Read\n- `/.recursive/run/demo/./02-to-be-plan.md`",
            ),
            "handoff": valid.replace(
                "- Inspect first:\n  - `/product.py`",
                "- Inspect first:\n  - `/product\\file.py`",
            ),
        }
        for name, content in mutations.items():
            with self.subTest(name=name):
                result = action.validate_full_action_record(content)
                self.assertFalse(result.valid, name)
                self.assertTrue(
                    any("path" in issue.lower() or "canonical" in issue.lower() for issue in result.issues),
                    result.issues,
                )

        structured = self.structured_action().replace(
            "- Claims: none",
            """\

### F-001
- Claimed outcome: `fixed`
- Claimed changes:
  - `/product.py`
- Claimed verification:
  - `python -m unittest`""",
        )
        for name, content in {
            "review protocol": structured.replace(
                "`/.agents/skills/recursive-review/references/finding-protocol.md`",
                "`.agents/skills/recursive-review/references/finding-protocol.md`",
            ),
            "review bundle": structured.replace(
                "`/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md`",
                "`/.recursive/run/demo/evidence/review-bundles/phase-3/../0001.md`",
            ),
            "review ledger": structured.replace(
                "`/.recursive/run/demo/evidence/reviews/phase-3/current-review/ledger.md`",
                "`/.recursive/run/demo/evidence/reviews/phase-3/current-review/ledger.md `",
            ),
            "claimed changes": structured.replace(
                "  - `/product.py`",
                "  - `product.py`",
            ),
        }.items():
            with self.subTest(name=name):
                result = action.validate_full_action_record(content)
                self.assertFalse(result.valid, name)

    def test_action_record_path_must_match_actual_persisted_path_when_known(self) -> None:
        content = self.action_record(phase="Phase 2", execution_mode="planner")
        valid = action.validate_full_action_record(
            content,
            expected_action_record_path="/.recursive/run/demo/subagents/worker-1.md",
        )
        self.assertTrue(valid.valid, valid.issues)
        stale = action.validate_full_action_record(
            content,
            expected_action_record_path="/.recursive/run/demo/subagents/other.md",
        )
        self.assertFalse(stale.valid)
        self.assertIn(
            "action record Metadata.Action Record Path does not match its persisted file path",
            stale.issues,
        )

    def test_full_schema_rejects_minimal_pseudo_record_even_with_valid_ledger(self) -> None:
        content = """## Metadata
- Run ID: demo
- Phase: Phase 3
- Execution Mode: review

## Inputs Provided
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md`

## Claimed Findings
- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md`
- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-3/review/ledger.md`
- Review Pass: 0001
- Claims: none
"""
        document = action.review_ledger.ReviewDocument(
            "",
            {
                "Pass": "0001",
                "Reviewed Artifact": "/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md",
            },
            {},
            {},
        )
        with (
            mock.patch.object(
                action.review_ledger,
                "validate_ledger",
                return_value=action.review_ledger.ValidationResult(document=document),
            ),
            mock.patch.object(
                action,
                "read_confined_repo_text",
                return_value=("ledger", ROOT / "ledger.md", []),
            ),
        ):
            result = action.validate_action_record(ROOT, content)
        self.assertFalse(result.valid)
        self.assertTrue(
            any("canonical" in issue or "exact" in issue for issue in result.issues),
            result.issues,
        )

    def test_review_audit_gate_requires_current_phase_binding(self) -> None:
        document = action.review_ledger.ReviewDocument(
            "",
            {
                "Pass": "0001",
                "Reviewed Artifact": "/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md",
            },
            {},
            {},
        )
        ledger_result = action.review_ledger.ValidationResult(document=document)
        expected = {
            "expected_run": "demo",
            "expected_phase": "Phase 3",
            "owning_artifact": "03-implementation-summary.md",
            "expected_review_bundle": ".recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md",
            "expected_review_ledger": ".recursive/run/demo/evidence/reviews/phase-3/current-review/ledger.md",
            "expected_review_pass": "0001",
        }
        with (
            mock.patch.object(action.review_ledger, "validate_ledger", return_value=ledger_result),
            mock.patch.object(
                action,
                "read_confined_repo_text",
                return_value=("ledger", ROOT / "ledger.md", []),
            ),
        ):
            valid = action.validate_review_audit_action_record(ROOT, self.structured_action(), **expected)
            self.assertTrue(valid.valid, valid.issues)

            for field, stale_value in (
                ("expected_review_bundle", "/.recursive/run/demo/evidence/review-bundles/phase-3/new-review/0002.md"),
                ("expected_review_ledger", "/.recursive/run/demo/evidence/reviews/phase-3/new-review/ledger.md"),
                ("expected_review_pass", "0002"),
            ):
                with self.subTest(field=field):
                    stale = action.validate_review_audit_action_record(
                        ROOT,
                        self.structured_action(),
                        **{**expected, field: stale_value},
                    )
                    self.assertFalse(stale.valid)

    def test_implementation_and_repair_records_do_not_count_as_review_audit(self) -> None:
        document = action.review_ledger.ReviewDocument(
            "",
            {
                "Pass": "0001",
                "Reviewed Artifact": "/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md",
            },
            {},
            {},
        )
        ledger_result = action.review_ledger.ValidationResult(document=document)
        with (
            mock.patch.object(action.review_ledger, "validate_ledger", return_value=ledger_result),
            mock.patch.object(
                action,
                "read_confined_repo_text",
                return_value=("ledger", ROOT / "ledger.md", []),
            ),
        ):
            for execution_mode in ("implementer", "repair", "review-repair", "testing"):
                with self.subTest(execution_mode=execution_mode):
                    result = action.validate_review_audit_action_record(
                        ROOT,
                        self.structured_action(execution_mode),
                        expected_run="demo",
                        expected_phase="Phase 3",
                        owning_artifact="03-implementation-summary.md",
                        expected_review_bundle="/.recursive/run/demo/evidence/review-bundles/phase-3/current-review/0001.md",
                        expected_review_ledger="/.recursive/run/demo/evidence/reviews/phase-3/current-review/ledger.md",
                        expected_review_pass="0001",
                    )
                    self.assertFalse(result.valid)
                    self.assertFalse(action.is_review_audit_action(self.structured_action(execution_mode)))


if __name__ == "__main__":
    unittest.main(verbosity=2)
