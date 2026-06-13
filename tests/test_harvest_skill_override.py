# -*- coding: utf-8 -*-
"""
tests/test_harvest_skill_override.py — CRAFT.harvest_skill_flavor
(2026-06-13, Brian's call: per-region harvest-skill override).

Salvage regions roll their own skill instead of wilderness Survival:
the Coruscant Underworld (recovering usable Republic tech) rolls Search,
not Survival. Every other region keeps the default. Difficulty unchanged.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestHarvestSkillForRegion(unittest.TestCase):
    def test_default_is_survival(self):
        from engine.harvest import harvest_skill_for_region, HARVEST_SKILL
        self.assertEqual(HARVEST_SKILL, "survival")
        for region in ("dune_sea", "geonosis_wastes", "", "unknown_region"):
            self.assertEqual(harvest_skill_for_region(region), "survival")

    def test_coruscant_underworld_uses_search(self):
        from engine.harvest import harvest_skill_for_region
        self.assertEqual(
            harvest_skill_for_region("coruscant_underworld"), "search")

    def test_case_insensitive(self):
        from engine.harvest import harvest_skill_for_region
        self.assertEqual(
            harvest_skill_for_region("Coruscant_Underworld"), "search")

    def test_override_skill_is_canonical(self):
        # The override must resolve as a real skill (not a typo).
        from engine.harvest import _REGION_HARVEST_SKILL
        from engine.character import canonical_skill_key
        for region, skill in _REGION_HARVEST_SKILL.items():
            self.assertEqual(canonical_skill_key(skill), skill,
                             f"{region}'s override skill {skill!r} is "
                             f"not canonical")


if __name__ == "__main__":
    unittest.main()
