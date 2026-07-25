#!/usr/bin/env python3
"""Executable package-surface coverage for third-party notices."""

from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ROOT_NOTICE = ROOT / "THIRD_PARTY_NOTICES.md"
SOURCE_DERIVED_SKILLS = {
    "recursive-architecture-survey",
    "recursive-codebase-design",
    "recursive-debugging",
    "recursive-delivery-slicing",
    "recursive-domain-modeling",
    "recursive-grilling",
    "recursive-handoff",
    "recursive-merge-conflicts",
    "recursive-prototype",
    "recursive-research",
    "recursive-review",
    "recursive-spec",
    "recursive-tdd",
    "recursive-wayfinder",
}


class ThirdPartyNoticeTests(unittest.TestCase):
    def test_source_derived_skills_carry_the_complete_root_notice(self) -> None:
        root_notice = ROOT_NOTICE.read_bytes()
        notice_text = root_notice.decode("utf-8")

        self.assertIn("391a2701dd948f94f56a39f7533f8eea9a859c87", notice_text)
        self.assertIn("Copyright (c) 2026 Matt Pocock", notice_text)
        self.assertIn("Permission is hereby granted, free of charge", notice_text)
        self.assertIn('THE SOFTWARE IS PROVIDED "AS IS"', notice_text)

        installed_notice_skills = {
            path.parent.name for path in (ROOT / "skills").glob("*/THIRD_PARTY_NOTICES.md")
        }
        self.assertEqual(SOURCE_DERIVED_SKILLS, installed_notice_skills)

        for skill_name in sorted(SOURCE_DERIVED_SKILLS):
            with self.subTest(skill=skill_name):
                package_notice = ROOT / "skills" / skill_name / "THIRD_PARTY_NOTICES.md"
                self.assertEqual(root_notice, package_notice.read_bytes())


if __name__ == "__main__":
    unittest.main()
