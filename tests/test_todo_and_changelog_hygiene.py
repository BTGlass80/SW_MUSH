# -*- coding: utf-8 -*-
"""
tests/test_todo_and_changelog_hygiene.py - lock in the discipline
that TODO.json and CHANGELOG.md exist at project root, parse,
and have the expected shape.

Both files are companion artifacts to the architecture doc:
- TODO.json is forward-looking (priority queue + design calls).
- CHANGELOG.md is backward-looking (drop ledger).

Updated at the end of every drop per the standing discipline
established in this seeding drop.
"""
from __future__ import annotations

import json
import os
import re
import unittest
from datetime import datetime


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestTodoJsonExistsAndParses(unittest.TestCase):
    """TODO.json must exist at project root and be valid JSON."""

    def test_todo_json_at_project_root(self) -> None:
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        self.assertTrue(
            os.path.exists(path),
            "TODO.json must exist at project root. See CHANGELOG.md "
            "2026-05-24 entry for the seeding drop.",
        )

    def test_todo_json_parses(self) -> None:
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)

    def test_todo_json_has_schema_version(self) -> None:
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("schema_version", data)
        self.assertIsInstance(data["schema_version"], int)

    def test_todo_json_last_updated_is_iso_date(self) -> None:
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.assertIn("last_updated", data)
        # Confirm parseable as ISO date (YYYY-MM-DD)
        datetime.strptime(data["last_updated"], "%Y-%m-%d")

    def test_todo_json_has_expected_top_level_keys(self) -> None:
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        expected = {
            "schema_version",
            "last_updated",
            "architecture_of_record",
            "tier_1_active",
            "tier_2_queued",
            "tier_3_post_launch",
            "design_calls_pending_brian",
            "baseline_test_skips_accepted",
            "standing_invariants_quick_ref",
            "phantom_pattern_catalog_summary",
            "named_disciplines_quick_ref",
        }
        actual = set(data.keys())
        missing = expected - actual
        self.assertFalse(
            missing,
            f"TODO.json missing top-level keys: {sorted(missing)}",
        )

    def test_todo_json_architecture_of_record_points_to_real_file(
        self,
    ) -> None:
        """The architecture_of_record field should match the
        actual current arch doc. Catches drift if arch is bumped
        but TODO.json forgets to follow."""
        path = os.path.join(PROJECT_ROOT, "TODO.json")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        aor = data["architecture_of_record"]
        self.assertTrue(
            aor.startswith("sw_d6_mush_architecture_v"),
            f"architecture_of_record looks malformed: {aor!r}",
        )
        self.assertTrue(
            aor.endswith(".md"),
            f"architecture_of_record missing .md suffix: {aor!r}",
        )


class TestChangelogExists(unittest.TestCase):
    """CHANGELOG.md must exist at project root."""

    def test_changelog_at_project_root(self) -> None:
        path = os.path.join(PROJECT_ROOT, "CHANGELOG.md")
        self.assertTrue(
            os.path.exists(path),
            "CHANGELOG.md must exist at project root. See CHANGELOG.md "
            "2026-05-24 entry for the seeding drop.",
        )

    def test_changelog_has_at_least_one_dated_entry(self) -> None:
        """Changelog must contain at least one entry header
        matching `### YYYY-MM-DD — <name>`. The seeding drop
        itself satisfies this; later drops add more."""
        path = os.path.join(PROJECT_ROOT, "CHANGELOG.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        # The dash in the header is an em-dash (—), not a hyphen.
        entry_pattern = re.compile(
            r"^### \d{4}-\d{2}-\d{2}\s+[—-]",
            re.MULTILINE,
        )
        matches = entry_pattern.findall(content)
        self.assertGreater(
            len(matches),
            0,
            "CHANGELOG.md must have at least one dated entry "
            "header matching `### YYYY-MM-DD — <name>`",
        )

    def test_changelog_seed_entry_present(self) -> None:
        """The 2026-05-24 seed entry is the anchor; deletion
        would mean the seeding drop itself was lost."""
        path = os.path.join(PROJECT_ROOT, "CHANGELOG.md")
        with open(path, encoding="utf-8") as f:
            content = f.read()
        self.assertIn(
            "2026-05-24",
            content,
            "CHANGELOG.md should retain the 2026-05-24 seed entry",
        )


if __name__ == "__main__":
    unittest.main()
