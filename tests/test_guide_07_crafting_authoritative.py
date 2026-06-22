# -*- coding: utf-8 -*-
"""
Authoritative cross-check guard for Guide_07_Crafting.md (Opus quality pass,
June 2026).

The existing test_guide_07_crafting_rework.py checks that names/sections are
PRESENT. It cannot catch the drift class this guard exists for: a schematic
reference table that lists the WRONG skill, WRONG difficulty, or WRONG
components versus the live recipe data in data/schematics.yaml.

That drift is invisible to every other test (the convention/registry suites
guard commands, not guide prose), and the 2026-06-22 authoritative pass found
~12 wrong skills and ~25 wrong component lists in the §8/§9 reference tables.

This guard pins, for EVERY schematic in schematics.yaml:
  - its name appears as a reference-table row,
  - the row carries the correct difficulty,
  - the row carries the correct skill_required (where the table has a skill
    column — armor and the T5 table do not),
  - the row lists each component as "<qty> <type>" (for craftable item types
    that the guide tabulates components for).

If a recipe's skill/difficulty/components change in schematics.yaml, this test
fails until the guide is updated to match — the guide can no longer silently
drift from the data.
"""

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_07_Crafting.md")
SCHEMATICS_PATH = os.path.join(PROJECT_ROOT, "data", "schematics.yaml")

# Output types whose reference rows do NOT carry a per-row skill column.
_NO_SKILL_COLUMN = {"armor"}
# Output types whose rows the guide does not tabulate components for
# (ship parts are listed by stat effect, e.g. "Hull +1", not by component).
_NO_COMPONENT_TABLE = {"component"}


def _load_guide_rows():
    """Return {first_cell_name: [full_row_line, ...]} for every table row."""
    with open(GUIDE_PATH, encoding="utf-8") as f:
        body = f.read()
    rows = {}
    for line in body.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        name = cells[0].replace("**", "").strip()
        rows.setdefault(name, []).append((cells, line))
    return rows


def _load_schematics():
    import yaml
    with open(SCHEMATICS_PATH, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("schematics", [])


class TestGuideCraftingAuthoritative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows = _load_guide_rows()
        cls.schematics = _load_schematics()

    def test_every_schematic_row_matches_data(self):
        failures = []
        for schem in self.schematics:
            key = schem["key"]
            name = schem["name"]
            is_t5 = key.startswith("t5_")
            otype = schem.get("output_type", "")
            diff = str(schem.get("difficulty"))
            skill = schem.get("skill_required", "")

            matches = self.rows.get(name)
            if not matches:
                failures.append(
                    f"{key}: name {name!r} not found as a reference-table row"
                )
                continue

            # A schematic may legitimately appear once (its reference row).
            cell_sets = [cells for cells, _line in matches]
            row_lines = [line for _cells, line in matches]

            # Difficulty: str(diff) must be an exact cell in at least one row.
            if not any(diff in cells for cells in cell_sets):
                failures.append(
                    f"{key}: difficulty {diff!r} not present as a cell in "
                    f"row for {name!r} (rows: {row_lines})"
                )

            # Skill: required where the table has a skill column.
            if not is_t5 and otype not in _NO_SKILL_COLUMN:
                if not any(skill in cells for cells in cell_sets):
                    failures.append(
                        f"{key}: skill {skill!r} not present as a cell in "
                        f"row for {name!r} (rows: {row_lines})"
                    )

            # Components: "<qty> <type>" substring for craftable item types.
            if not is_t5 and otype not in _NO_COMPONENT_TABLE:
                for comp in schem.get("components", []):
                    token = f"{comp['quantity']} {comp['type']}"
                    if not any(token in line for line in row_lines):
                        failures.append(
                            f"{key}: component {token!r} not listed in any "
                            f"row for {name!r} (rows: {row_lines})"
                        )

        if failures:
            self.fail(
                "Guide_07 schematic tables drifted from schematics.yaml:\n  "
                + "\n  ".join(failures)
            )

    def test_t5_difficulty_band_documented(self):
        """The guide must state the T5 difficulty band (25-28)."""
        with open(GUIDE_PATH, encoding="utf-8") as f:
            body = f.read()
        self.assertIn("25", body)
        self.assertIn("28", body)

    def test_learn_and_tuition_documented(self):
        """The trainer tuition credit sink + the `learn` verb must be present
        (it was entirely missing before the authoritative pass)."""
        with open(GUIDE_PATH, encoding="utf-8") as f:
            body = f.read().lower()
        self.assertIn("learn", body)
        self.assertIn("tuition", body)

    def test_electronic_buyable_not_misstated(self):
        """The old guide wrongly claimed electronic could not be bought from a
        vendor. NPC_RESOURCE_PRICES sells it — the guide must not say
        otherwise."""
        with open(GUIDE_PATH, encoding="utf-8") as f:
            body = f.read().lower()
        self.assertNotIn("t5, or electronic", body)
        self.assertNotIn("rare, t5, or electronic", body)


if __name__ == "__main__":
    unittest.main()
