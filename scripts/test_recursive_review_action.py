#!/usr/bin/env python3
"""Behavior tests for the installed Recursive Review action-record parser."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "skills" / "recursive-mode" / "scripts"
sys.path.insert(0, str(RUNTIME))

import recursive_review_action as action


class RecursiveReviewActionTest(unittest.TestCase):
    def test_fixed_claim_uses_exact_structured_schema(self) -> None:
        content = """## Claimed Findings

- Review Protocol: `/.agents/skills/recursive-review/references/finding-protocol.md`
- Review Bundle: `/.recursive/run/demo/evidence/review-bundles/phase-3/review/0001.md`
- Review Ledger: `/.recursive/run/demo/evidence/reviews/phase-3/review/ledger.md`
- Review Pass: 0001

### F-001
- Claimed outcome: `fixed`
- Claimed changes:
  - `product.py`
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
        content = """## Metadata

- Run ID: demo
- Phase: Phase 3
- Execution Mode: review

## Inputs Provided

- none

## Claimed Findings

- issue found
"""
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
        content = """## Metadata

- Run ID: demo
- Phase: Phase 5
- Execution Mode: manual QA

## Inputs Provided

- none

## Claimed Findings

- observation only
"""
        result = action.validate_action_record(
            ROOT,
            content,
            expected_run="demo",
            expected_phase="Phase 5",
            owning_artifact="05-manual-qa.md",
        )
        self.assertTrue(result.valid, result.issues)


if __name__ == "__main__":
    unittest.main(verbosity=2)
