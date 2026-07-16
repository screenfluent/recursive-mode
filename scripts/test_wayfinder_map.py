#!/usr/bin/env python3
"""Behavior tests for the read-only recursive-wayfinder map helper."""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "skills/recursive-wayfinder/scripts/wayfinder_map.py"


class WayfinderMapHelperTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.map_dir = Path(self.temp.name) / "auth-roadmap"
        (self.map_dir / "units").mkdir(parents=True)
        (self.map_dir / "promotions").mkdir()
        self.write_valid_map()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, relative: str, content: str) -> None:
        path = self.map_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")

    def write_valid_map(self) -> None:
        self.write(
            "evidence/choose-token-source/research/report.md",
            """
            # Token source research

            The first-party metadata endpoint owns token metadata.
            """,
        )
        self.write(
            "MAP.md",
            """
            # Auth roadmap
            Status: active
            Created: 2026-07-12
            Updated: 2026-07-12

            ## Destination
            A bounded auth slice is ready for recursive-spec.

            ## Notes
            - Preserve existing clients.

            ## Decisions so far
            - [Choose token source](units/choose-token-source.md) — use first-party metadata.

            ## Candidate slices
            - [First auth slice](promotions/first-auth-slice.md) — ready for approval.

            ## Not yet specified
            - Recovery policy.

            ## Out of scope
            - Admin UI.
            """,
        )
        self.write(
            "units/choose-token-source.md",
            """
            # Choose token source
            Kind: research
            Mode: AFK
            Status: resolved
            Claimed by: none
            Claimed at: none
            Blocked by: none

            ## Question
            Which source owns token metadata?

            ## Resolution
            Use the first-party metadata endpoint.
            Outcome: resolved

            ## Evidence
            - [Token source research](../evidence/choose-token-source/research/report.md)

            ## Consequences
            - The spec can name the metadata seam.
            """,
        )
        self.write(
            "units/compare-session-shapes.md",
            """
            # Compare session shapes
            Kind: prototype
            Mode: HITL
            Status: open
            Claimed by: none
            Claimed at: none
            Blocked by: [Choose token source](choose-token-source.md)

            ## Question
            Which session shape should the human prefer?

            ## Resolution
            Outcome: pending

            ## Evidence

            ## Consequences
            """,
        )
        self.write(
            "units/confirm-user-boundary.md",
            """
            # Confirm user boundary
            Kind: grilling
            Mode: HITL
            Status: open
            Claimed by: none
            Claimed at: none
            Blocked by: none

            ## Question
            Which user boundary should the slice cover?

            ## Resolution
            Outcome: pending

            ## Evidence

            ## Consequences
            """,
        )
        self.write(
            "promotions/first-auth-slice.md",
            """
            # First auth slice
            Status: approved
            Source map: ../MAP.md
            Source units:
            - [Choose token source](../units/choose-token-source.md)

            ## Outcome boundary
            Specify token metadata lookup.

            ## Settled inputs
            - Token metadata source is settled.

            ## Evidence
            - ../units/choose-token-source.md

            ## Remaining unknowns
            Blocking: none
            Non-blocking:
            - Session shape can wait.

            ## Out of scope
            - Admin UI.

            ## Spec handoff
            Human approval: Szymon approved 2026-07-12
            Suggested run id: auth-token-source
            Promoted to: none
            """,
        )

    def run_helper(self, command: str) -> subprocess.CompletedProcess[str]:
        if not HELPER.is_file():
            self.fail(f"missing helper: {HELPER.relative_to(ROOT)}")
        return subprocess.run(
            [sys.executable, str(HELPER), command, str(self.map_dir)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_validate_accepts_contract_and_is_read_only(self) -> None:
        before = {p: p.read_bytes() for p in self.map_dir.rglob("*") if p.is_file()}
        result = self.run_helper("validate")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("valid", result.stdout.lower())
        after = {p: p.read_bytes() for p in self.map_dir.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_validate_requires_real_iso_map_dates(self) -> None:
        path = self.map_dir / "MAP.md"
        original = path.read_text(encoding="utf-8")
        cases = (
            ("Created: 2026-07-12\n", "", "created"),
            ("Updated: 2026-07-12", "Updated: 2026-7-12", "yyyy-mm-dd"),
            ("Updated: 2026-07-12", "Updated: 2026-02-30", "valid date"),
        )
        for old, new, expected in cases:
            with self.subTest(replacement=new or "missing"):
                path.write_text(original.replace(old, new, 1), encoding="utf-8")
                result = self.run_helper("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(expected, result.stderr.lower())
                path.write_text(original, encoding="utf-8")

    def test_frontier_is_open_unclaimed_unblocked_and_sorted(self) -> None:
        compare = self.map_dir / "units/compare-session-shapes.md"
        compare.write_text(
            compare.read_text(encoding="utf-8").replace(
                "# Compare session shapes", "# Zulu session shapes", 1
            ),
            encoding="utf-8",
        )
        confirm = self.map_dir / "units/confirm-user-boundary.md"
        confirm.write_text(
            confirm.read_text(encoding="utf-8").replace(
                "# Confirm user boundary", "# Alpha user boundary", 1
            ),
            encoding="utf-8",
        )
        result = self.run_helper("frontier")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.strip().splitlines(),
            [
                "Zulu session shapes\tunits/compare-session-shapes.md",
                "Alpha user boundary\tunits/confirm-user-boundary.md",
            ],
        )

    def test_validate_rejects_blocker_cycles(self) -> None:
        path = self.map_dir / "units/choose-token-source.md"
        text = path.read_text(encoding="utf-8")
        text = text.replace("Status: resolved", "Status: open").replace(
            "Blocked by: none", "Blocked by: [Compare session shapes](compare-session-shapes.md)"
        ).replace("Outcome: resolved", "Outcome: pending")
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cycle", result.stderr.lower())

    def test_validate_rejects_bad_ids_and_link_title_mismatch(self) -> None:
        path = self.map_dir / "units/confirm-user-boundary.md"
        path.rename(self.map_dir / "units/Confirm_User.md")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("kebab-case", result.stderr.lower())

        path = self.map_dir / "units/choose-token-source.md"
        text = path.read_text(encoding="utf-8").replace(
            "# Choose token source", "# Different heading", 1
        )
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertIn("link text", result.stderr.lower())

    def test_validate_rejects_illegal_status_outcome_and_claim_pairs(self) -> None:
        path = self.map_dir / "units/confirm-user-boundary.md"
        text = path.read_text(encoding="utf-8").replace("Outcome: pending", "Outcome: resolved")
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("outcome", result.stderr.lower())

        text = path.read_text(encoding="utf-8").replace("Status: open", "Status: claimed")
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertIn("claimed by", result.stderr.lower())

    def test_validate_rejects_invalid_or_naive_claim_timestamps(self) -> None:
        path = self.map_dir / "units/confirm-user-boundary.md"
        original = path.read_text(encoding="utf-8")
        for timestamp in (
            "not-a-timestamp",
            "2026-07-12T12:34:56",
            "2026-02-30T12:34:56Z",
            "2026-07-12T24:00:00Z",
            "2026-07-12T12:60:00Z",
            "2026-07-12T12:34:60Z",
            "2026-07-12T12:34:56+02:60",
        ):
            with self.subTest(timestamp=timestamp):
                text = original.replace("Status: open", "Status: claimed", 1)
                text = text.replace("Claimed by: none", "Claimed by: review-agent", 1)
                text = text.replace("Claimed at: none", f"Claimed at: {timestamp}", 1)
                path.write_text(text, encoding="utf-8")

                result = self.run_helper("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("claimed at", result.stderr.lower())
                self.assertIn("claim timestamp profile", result.stderr.lower())
                if timestamp == "2026-07-12T12:34:60Z":
                    self.assertIn("leap seconds are outside", result.stderr.lower())
                path.write_text(original, encoding="utf-8")

    def test_validate_accepts_z_and_offset_claim_timestamps(self) -> None:
        path = self.map_dir / "units/confirm-user-boundary.md"
        original = path.read_text(encoding="utf-8")
        for timestamp in (
            "2026-07-12T12:34:56Z",
            "2026-07-12T00:00:00.123456Z",
            "2026-07-12T23:59:59Z",
            "2026-07-12T12:34:56+02:00",
        ):
            with self.subTest(timestamp=timestamp):
                text = original.replace("Status: open", "Status: claimed", 1)
                text = text.replace("Claimed by: none", "Claimed by: review-agent", 1)
                text = text.replace("Claimed at: none", f"Claimed at: {timestamp}", 1)
                path.write_text(text, encoding="utf-8")
                result = self.run_helper("validate")
                self.assertEqual(result.returncode, 0, result.stderr)
                path.write_text(original, encoding="utf-8")

    def test_validate_rejects_unready_approved_promotion(self) -> None:
        path = self.map_dir / "promotions/first-auth-slice.md"
        text = path.read_text(encoding="utf-8").replace(
            "Blocking: none", "Blocking: session semantics"
        )
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("blocking", result.stderr.lower())

    def test_validate_rejects_open_unit_in_decisions_index(self) -> None:
        path = self.map_dir / "MAP.md"
        text = path.read_text(encoding="utf-8").replace(
            "[Choose token source](units/choose-token-source.md)",
            "[Confirm user boundary](units/confirm-user-boundary.md)",
        )
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("decisions so far", result.stderr.lower())
        self.assertIn("resolved", result.stderr.lower())

    def test_validate_accepts_map_without_promotions_directory(self) -> None:
        map_path = self.map_dir / "MAP.md"
        text = map_path.read_text(encoding="utf-8").replace(
            "- [First auth slice](promotions/first-auth-slice.md) — ready for approval.\n",
            "",
        )
        map_path.write_text(text, encoding="utf-8")
        (self.map_dir / "promotions/first-auth-slice.md").unlink()
        (self.map_dir / "promotions").rmdir()

        result = self.run_helper("validate")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validate_rejects_missing_local_evidence_link(self) -> None:
        path = self.map_dir / "units/choose-token-source.md"
        text = path.read_text(encoding="utf-8").replace(
            "../evidence/choose-token-source/research/report.md",
            "../evidence/choose-token-source/research/missing.md",
        )
        path.write_text(text, encoding="utf-8")

        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local link does not exist", result.stderr.lower())
        self.assertEqual(result.stderr.lower().count("missing.md"), 1)

    def test_validate_rejects_missing_local_non_markdown_asset(self) -> None:
        path = self.map_dir / "units/choose-token-source.md"
        text = path.read_text(encoding="utf-8").replace(
            "## Evidence",
            "## Evidence\n- [Missing screenshot](../evidence/choose-token-source/missing.png)",
            1,
        )
        path.write_text(text, encoding="utf-8")

        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local link does not exist", result.stderr.lower())
        self.assertIn("missing.png", result.stderr.lower())

    def test_validate_checks_local_links_from_map_units_and_promotions(self) -> None:
        cases = (
            ("MAP.md", "## Notes", "## Notes\n- [Missing](evidence/missing.md)"),
            (
                "units/confirm-user-boundary.md",
                "## Evidence",
                "## Evidence\n- [Missing](../evidence/missing.md)",
            ),
            (
                "promotions/first-auth-slice.md",
                "## Evidence",
                "## Evidence\n- [Missing](../evidence/missing.md)",
            ),
        )
        for relative, marker, replacement in cases:
            with self.subTest(relative=relative):
                path = self.map_dir / relative
                original = path.read_text(encoding="utf-8")
                path.write_text(original.replace(marker, replacement, 1), encoding="utf-8")
                result = self.run_helper("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stderr.lower().count("missing.md"), 1)
                path.write_text(original, encoding="utf-8")

    def test_validate_rejects_absolute_links_and_document_symlink_escapes(self) -> None:
        map_path = self.map_dir / "MAP.md"
        original_map = map_path.read_text(encoding="utf-8")
        asset = self.map_dir / "evidence/choose-token-source/research/report.md"
        map_path.write_text(
            original_map.replace(
                "## Notes",
                f"## Notes\n- [Absolute asset]({asset.resolve()})",
                1,
            ),
            encoding="utf-8",
        )
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("absolute local links are not allowed", result.stderr.lower())
        self.assertNotIn("traceback", result.stderr.lower())
        map_path.write_text(original_map, encoding="utf-8")

        source = self.map_dir / "units/confirm-user-boundary.md"
        outside = Path(self.temp.name) / "outside-unit.md"
        outside.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
        (self.map_dir / "units/escaped-unit.md").symlink_to(outside)
        for command in ("validate", "frontier"):
            with self.subTest(command=command):
                result = self.run_helper(command)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("outside the map directory", result.stderr.lower())
                self.assertNotIn("traceback", result.stderr.lower())

    def test_validate_enforces_one_promoted_to_target(self) -> None:
        path = self.map_dir / "promotions/first-auth-slice.md"
        original = path.read_text(encoding="utf-8")
        promoted = original.replace("Status: approved", "Status: promoted", 1)

        for target in (
            "auth-token-source",
            "/.recursive/deliveries/auth-platform/spec.md",
        ):
            with self.subTest(valid=target):
                path.write_text(promoted.replace("Promoted to: none", f"Promoted to: {target}", 1), encoding="utf-8")
                result = self.run_helper("validate")
                self.assertEqual(result.returncode, 0, result.stderr)

        for target in (
            "none",
            "pending",
            "not-a-pointer, second-target",
            "auth-token-source second-target",
            "https://example.com/spec.md",
            "/.recursive/run/auth-token-source/00-requirements.md",
        ):
            with self.subTest(invalid=target):
                path.write_text(promoted.replace("Promoted to: none", f"Promoted to: {target}", 1), encoding="utf-8")
                result = self.run_helper("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("exactly one", result.stderr.lower())

        path.write_text(original, encoding="utf-8")

    def test_validate_requires_exactly_one_promoted_to_field(self) -> None:
        path = self.map_dir / "promotions/first-auth-slice.md"
        original = path.read_text(encoding="utf-8")
        cases = (
            original.replace("Promoted to: none\n", "", 1),
            original.replace(
                "Promoted to: none",
                "Promoted to: none\nPromoted to: pending",
                1,
            ),
            original.replace("Promoted to: none", "Promoted to: pending", 1),
        )
        for index, content in enumerate(cases):
            with self.subTest(case=index):
                path.write_text(content, encoding="utf-8")
                result = self.run_helper("validate")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("promoted to", result.stderr.lower())
                path.write_text(original, encoding="utf-8")

    def test_validate_skips_external_urls_and_document_anchors(self) -> None:
        path = self.map_dir / "units/confirm-user-boundary.md"
        text = path.read_text(encoding="utf-8").replace(
            "## Evidence",
            "## Evidence\n- [External](https://example.com/reference.md)\n- [Question](#question)",
            1,
        )
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_validate_reports_missing_promotion_source_once_without_crashing(self) -> None:
        path = self.map_dir / "promotions/first-auth-slice.md"
        text = path.read_text(encoding="utf-8").replace(
            "../units/choose-token-source.md",
            "../units/missing-source.md",
        )
        path.write_text(text, encoding="utf-8")
        result = self.run_helper("validate")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("local link does not exist", result.stderr.lower())
        self.assertEqual(result.stderr.lower().count("missing-source.md"), 1)
        self.assertNotIn("traceback", result.stderr.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
