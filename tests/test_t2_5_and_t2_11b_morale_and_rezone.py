# -*- coding: utf-8 -*-
"""
tests/test_t2_5_and_t2_11b_morale_and_rezone.py

Two decisions implemented 2026-06-05 (Brian delegated the calls, asked for the
complete choice):

T2.11.b — morale-flavored skill set broadened to the cantina-social core
          (+bargain, +gambling, +streetwise). Intimidation deliberately
          EXCLUDED (uplift ≠ fear).

T2.5    — Coruscant zones migrated to the §3 function-based taxonomy
          (security_model_design_v1.md §3.1): jedi_temple / senate_district /
          commercial_district / monumental_district / entertainment_district /
          southern_underground (Contested) / coruscant_underworld (Lawless),
          with the old vertical-tier slugs (coruscant_upper/midlevels/lower/
          works/gilded_cage/senate/temple) gone and `coruscant_works` merged
          into `commercial_district`. §3 security tiers applied.
"""
from __future__ import annotations

import os
import unittest

import yaml

from engine.skill_checks import is_morale_flavored, MORALE_FLAVORED_SKILLS

_CW = os.path.join("data", "worlds", "clone_wars")
_ZONES_YAML = os.path.join(_CW, "zones.yaml")
_CORUSCANT_YAML = os.path.join(_CW, "planets", "coruscant.yaml")

_SEC3_CORUSCANT = {
    "jedi_temple": "secured",
    "senate_district": "secured",
    "commercial_district": "secured",
    "monumental_district": "secured",
    "entertainment_district": "secured",
    "southern_underground": "contested",
    "coruscant_underworld": "lawless",
}
_OLD_SLUGS = {
    "coruscant_senate", "coruscant_temple", "coruscant_upper",
    "coruscant_midlevels", "coruscant_lower", "coruscant_works",
    "coruscant_gilded_cage",
}


# ═══════════════════════════════════════════════════════════════════════════
# T2.11.b — morale skills
# ═══════════════════════════════════════════════════════════════════════════

class TestMoraleSkillSet(unittest.TestCase):

    def test_added_skills_are_morale_flavored(self):
        for s in ("bargain", "gambling", "streetwise"):
            self.assertIn(s, MORALE_FLAVORED_SKILLS)
            self.assertTrue(is_morale_flavored(s))
            self.assertTrue(is_morale_flavored(s.upper()))  # case-insensitive

    def test_v1_skills_retained(self):
        for s in ("willpower", "command", "persuasion", "con"):
            self.assertIn(s, MORALE_FLAVORED_SKILLS)

    def test_intimidation_deliberately_excluded(self):
        # The aura uplifts; intimidation instills fear. Excluded by design.
        self.assertFalse(is_morale_flavored("intimidation"))

    def test_unrelated_skills_not_morale(self):
        for s in ("blaster", "dodge", "lightsaber", "first aid", "astrogation",
                  "starship gunnery", "medicine", "security", "brawling"):
            self.assertFalse(is_morale_flavored(s),
                             f"{s} should not be morale-flavored")


# ═══════════════════════════════════════════════════════════════════════════
# T2.5 — Coruscant §3 re-zoning
# ═══════════════════════════════════════════════════════════════════════════

class TestCoruscantRezone(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(_ZONES_YAML, encoding="utf-8") as f:
            z = yaml.safe_load(f)
        cls.zones = z.get("zones", z)
        with open(_CORUSCANT_YAML, encoding="utf-8") as f:
            cls.coruscant = yaml.safe_load(f)

    def test_all_seven_section3_zones_present(self):
        for zone in _SEC3_CORUSCANT:
            self.assertIn(zone, self.zones,
                          f"§3 zone {zone!r} missing from zones.yaml")

    def test_old_vertical_tier_slugs_gone_from_zones(self):
        for old in _OLD_SLUGS:
            self.assertNotIn(old, self.zones,
                             f"old zone slug {old!r} still in zones.yaml")

    def test_zone_security_matches_section3(self):
        for zone, tier in _SEC3_CORUSCANT.items():
            props = (self.zones.get(zone) or {}).get("properties") or {}
            self.assertEqual(
                props.get("security"), tier,
                f"{zone}: properties.security={props.get('security')!r}, "
                f"§3 wants {tier!r}")

    def test_rooms_only_use_section3_zones(self):
        bad = {}
        for r in self.coruscant["rooms"]:
            z = r.get("zone")
            if z and z not in _SEC3_CORUSCANT:
                bad[r.get("slug", r.get("id"))] = z
        self.assertEqual(bad, {},
                         f"rooms still pointing at non-§3 zones: {bad}")

    def test_works_merged_into_commercial(self):
        # No room should carry a coruscant_works zone; the industrial rooms
        # now live under commercial_district (Secured per §3).
        zones_used = {r.get("zone") for r in self.coruscant["rooms"]}
        self.assertNotIn("coruscant_works", zones_used)
        self.assertIn("commercial_district", zones_used)

    def test_room_security_levels_are_section3_consistent(self):
        # Per-room security_level (where present) must equal the room's §3
        # zone tier — no leftover pre-§3 values.
        for r in self.coruscant["rooms"]:
            z = r.get("zone")
            lvl = r.get("security_level")
            if z in _SEC3_CORUSCANT and lvl is not None:
                self.assertEqual(
                    lvl, _SEC3_CORUSCANT[z],
                    f"room {r.get('slug')} zone={z} security_level={lvl!r} "
                    f"≠ §3 {_SEC3_CORUSCANT[z]!r}")

    def test_world_loads_clean(self):
        import engine.world_loader as wl
        bundle = wl.load_world_dry_run("clone_wars")
        self.assertEqual(len(bundle.report.errors), 0,
                         f"world load errors: {bundle.report.errors[:5]}")


if __name__ == "__main__":
    unittest.main()
