# -*- coding: utf-8 -*-
"""
tests/test_b1e_missions_era_aware.py — B.1.e (FACTION_MISSION_CONFIG
era extension) tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.e extends
`engine.missions.FACTION_MISSION_CONFIG` with CW faction entries so
that `generate_faction_mission()` works for republic / cis / jedi_order
/ hutt_cartel / bounty_hunters_guild.

Brian's Apr 29 design decision: "generic is fine" → CW factions reuse
two new archetype templates (`_CW_LAWFUL_OBJECTIVES`,
`_CW_INSURGENT_OBJECTIVES`) plus the existing `_HUTT_OBJECTIVES` and
`_BH_GUILD_OBJECTIVES`. No bespoke per-faction objective authoring.

Two test layers:

  1. Existing shape invariants in `test_session49_faction_missions.py::TestFactionMissionConfigShape`
     iterate over the entire config, so they auto-validate that CW
     additions satisfy the schema (regression-tested separately —
     this file is purely the additive surface).

  2. B.1.e-specific tests:
     - All 5 CW factions present in FACTION_MISSION_CONFIG
     - Each CW faction has the right archetype objective table
     - `generate_faction_mission()` returns a valid Mission for each
       CW faction (behavioral end-to-end)
     - GCW factions still produce identical missions (byte-equivalence)
"""
from __future__ import annotations

import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


_CW_FACTIONS = [
    "republic", "cis", "jedi_order",
    "hutt_cartel", "bounty_hunters_guild",
]


# ──────────────────────────────────────────────────────────────────────
# 1. CW factions present in FACTION_MISSION_CONFIG
# ──────────────────────────────────────────────────────────────────────

class TestCWFactionsPresent(unittest.TestCase):
    """Asymmetric: FAILS pre-B.1.e (those keys didn't exist),
    PASSES post-B.1.e."""

    def test_all_cw_factions_in_config(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            self.assertIn(
                fc, FACTION_MISSION_CONFIG,
                f"CW faction '{fc}' missing from FACTION_MISSION_CONFIG"
            )

    def test_gcw_factions_still_present(self):
        """Regression gate: existing factions unchanged."""
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in ("empire", "rebel", "hutt", "bh_guild"):
            self.assertIn(fc, FACTION_MISSION_CONFIG)


# ──────────────────────────────────────────────────────────────────────
# 2. Archetype reuse — CW factions point at the right template tables
# ──────────────────────────────────────────────────────────────────────

class TestCWArchetypeMapping(unittest.TestCase):
    """Per Brian's 'generic is fine' decision, CW factions should reuse
    archetype templates rather than bespoke objectives."""

    def test_cw_lawful_objectives_table_exists(self):
        from engine.missions import _CW_LAWFUL_OBJECTIVES
        # Lawful authority handles combat / investigation / delivery
        from engine.missions import MissionType
        self.assertIn(MissionType.COMBAT,        _CW_LAWFUL_OBJECTIVES)
        self.assertIn(MissionType.INVESTIGATION, _CW_LAWFUL_OBJECTIVES)
        self.assertIn(MissionType.DELIVERY,      _CW_LAWFUL_OBJECTIVES)

    def test_cw_insurgent_objectives_table_exists(self):
        from engine.missions import _CW_INSURGENT_OBJECTIVES
        from engine.missions import MissionType
        self.assertIn(MissionType.COMBAT,        _CW_INSURGENT_OBJECTIVES)
        self.assertIn(MissionType.INVESTIGATION, _CW_INSURGENT_OBJECTIVES)
        self.assertIn(MissionType.SMUGGLING,     _CW_INSURGENT_OBJECTIVES)

    def test_republic_uses_lawful_archetype(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _CW_LAWFUL_OBJECTIVES,
        )
        self.assertIs(
            FACTION_MISSION_CONFIG["republic"]["objectives"],
            _CW_LAWFUL_OBJECTIVES,
        )

    def test_jedi_order_uses_lawful_archetype(self):
        """Jedi serve the Republic — same lawful-authority shape."""
        from engine.missions import (
            FACTION_MISSION_CONFIG, _CW_LAWFUL_OBJECTIVES,
        )
        self.assertIs(
            FACTION_MISSION_CONFIG["jedi_order"]["objectives"],
            _CW_LAWFUL_OBJECTIVES,
        )

    def test_cis_uses_insurgent_archetype(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _CW_INSURGENT_OBJECTIVES,
        )
        self.assertIs(
            FACTION_MISSION_CONFIG["cis"]["objectives"],
            _CW_INSURGENT_OBJECTIVES,
        )

    def test_hutt_cartel_reuses_hutt_archetype(self):
        """hutt_cartel is the same archetype as GCW Hutt — reuses
        existing _HUTT_OBJECTIVES table."""
        from engine.missions import (
            FACTION_MISSION_CONFIG, _HUTT_OBJECTIVES,
        )
        self.assertIs(
            FACTION_MISSION_CONFIG["hutt_cartel"]["objectives"],
            _HUTT_OBJECTIVES,
        )

    def test_bounty_hunters_guild_reuses_bh_guild_archetype(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _BH_GUILD_OBJECTIVES,
        )
        self.assertIs(
            FACTION_MISSION_CONFIG["bounty_hunters_guild"]["objectives"],
            _BH_GUILD_OBJECTIVES,
        )


# ──────────────────────────────────────────────────────────────────────
# 3. CW factions satisfy shape invariants (same as GCW)
# ──────────────────────────────────────────────────────────────────────

class TestCWFactionsShape(unittest.TestCase):
    """B.1.e additions must individually pass the same shape gate the
    existing GCW factions do. test_session49_faction_missions.py
    iterates over every entry, so this is partial duplication for
    isolated diagnosability."""

    REQUIRED_KEYS = {"badge", "givers", "mission_types", "objectives",
                     "reward_mult", "rep_required"}

    def test_cw_required_keys(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            missing = self.REQUIRED_KEYS - set(FACTION_MISSION_CONFIG[fc].keys())
            self.assertEqual(
                missing, set(),
                f"CW faction '{fc}' missing keys: {missing}"
            )

    def test_cw_reward_mults_in_design_range(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            mult = FACTION_MISSION_CONFIG[fc]["reward_mult"]
            self.assertTrue(
                1.4 <= mult <= 1.6,
                f"CW faction '{fc}' reward_mult {mult} outside [1.4, 1.6]"
            )

    def test_cw_rep_required_positive(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            self.assertGreater(
                FACTION_MISSION_CONFIG[fc]["rep_required"], 0
            )

    def test_cw_mission_types_have_objectives(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            cfg = FACTION_MISSION_CONFIG[fc]
            for mtype in cfg["mission_types"]:
                templates = cfg["objectives"].get(mtype)
                self.assertTrue(
                    templates and len(templates) > 0,
                    f"CW '{fc}' lists {mtype} but has no objective templates"
                )

    def test_cw_givers_nonempty(self):
        from engine.missions import FACTION_MISSION_CONFIG
        for fc in _CW_FACTIONS:
            self.assertTrue(
                len(FACTION_MISSION_CONFIG[fc]["givers"]) > 0
            )


# ──────────────────────────────────────────────────────────────────────
# 4. End-to-end: generate_faction_mission works for each CW faction
# ──────────────────────────────────────────────────────────────────────

class TestGenerateFactionMissionForCW(unittest.TestCase):
    """The headline behavior: generate_faction_mission(cw_code) returns
    a valid Mission instead of None."""

    def test_generate_for_each_cw_faction(self):
        from engine.missions import generate_faction_mission
        for fc in _CW_FACTIONS:
            with self.subTest(faction=fc):
                random.seed(42)
                mission = generate_faction_mission(fc)
                self.assertIsNotNone(
                    mission,
                    f"generate_faction_mission({fc!r}) returned None"
                )
                self.assertEqual(mission.faction_code, fc)
                self.assertGreater(mission.faction_rep_required, 0)

    def test_republic_mission_has_republic_themed_text(self):
        """The lawful-CW objective templates mention 'Republic' and
        'Separatist', not 'Imperial' and 'rebel'."""
        from engine.missions import generate_faction_mission
        # Run several times to span template choices
        for seed in range(10):
            random.seed(seed)
            m = generate_faction_mission("republic")
            self.assertIsNotNone(m)
            # The objective body should be CW-themed (contains
            # Republic/Separatist words). It should NOT contain
            # GCW-flavored words like "Imperial" or "Rebel" since the
            # _CW_LAWFUL_OBJECTIVES table is era-correct.
            obj = (m.objective or "") + " " + (m.title or "")
            # At minimum the objective shouldn't mention "Imperial"
            # because the source template doesn't.
            self.assertNotIn(
                "Imperial", obj,
                f"Republic mission contains GCW-flavored 'Imperial': {obj!r}"
            )

    def test_cis_mission_has_cis_themed_text(self):
        from engine.missions import generate_faction_mission
        for seed in range(10):
            random.seed(seed)
            m = generate_faction_mission("cis")
            self.assertIsNotNone(m)
            obj = (m.objective or "") + " " + (m.title or "")
            # CW insurgent objectives target Republic/GAR, not Empire.
            self.assertNotIn(
                "Imperial garrison", obj,
                f"CIS mission contains GCW phrase 'Imperial garrison': {obj!r}"
            )

    def test_unknown_faction_still_returns_none(self):
        """Regression: bogus codes still gracefully return None."""
        from engine.missions import generate_faction_mission
        self.assertIsNone(generate_faction_mission("nonexistent"))
        self.assertIsNone(generate_faction_mission(""))
        self.assertIsNone(generate_faction_mission(None))


# ──────────────────────────────────────────────────────────────────────
# 5. GCW byte-equivalence — empire/rebel/hutt/bh_guild unchanged
# ──────────────────────────────────────────────────────────────────────

class TestGCWByteEquivalence(unittest.TestCase):
    """The GCW faction entries in FACTION_MISSION_CONFIG must be
    byte-identical to pre-B.1.e."""

    def test_empire_config_unchanged(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _EMPIRE_OBJECTIVES,
        )
        cfg = FACTION_MISSION_CONFIG["empire"]
        self.assertEqual(cfg["badge"], "EMPIRE")
        self.assertEqual(cfg["reward_mult"], 1.5)
        self.assertEqual(cfg["rep_required"], 25)
        self.assertIs(cfg["objectives"], _EMPIRE_OBJECTIVES)

    def test_rebel_config_unchanged(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _REBEL_OBJECTIVES,
        )
        cfg = FACTION_MISSION_CONFIG["rebel"]
        self.assertEqual(cfg["badge"], "REBEL")
        self.assertEqual(cfg["reward_mult"], 1.5)
        self.assertEqual(cfg["rep_required"], 25)
        self.assertIs(cfg["objectives"], _REBEL_OBJECTIVES)

    def test_hutt_config_unchanged(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _HUTT_OBJECTIVES,
        )
        cfg = FACTION_MISSION_CONFIG["hutt"]
        self.assertEqual(cfg["badge"], "HUTT")
        self.assertEqual(cfg["reward_mult"], 1.4)
        self.assertEqual(cfg["rep_required"], 20)
        self.assertIs(cfg["objectives"], _HUTT_OBJECTIVES)

    def test_bh_guild_config_unchanged(self):
        from engine.missions import (
            FACTION_MISSION_CONFIG, _BH_GUILD_OBJECTIVES,
        )
        cfg = FACTION_MISSION_CONFIG["bh_guild"]
        self.assertEqual(cfg["badge"], "GUILD")
        self.assertEqual(cfg["reward_mult"], 1.6)
        self.assertEqual(cfg["rep_required"], 30)
        self.assertIs(cfg["objectives"], _BH_GUILD_OBJECTIVES)


if __name__ == "__main__":
    unittest.main()
