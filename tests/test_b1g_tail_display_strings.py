# -*- coding: utf-8 -*-
"""
tests/test_b1g_tail_display_strings.py — B.1.g (tail of display strings)
tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.g sweeps the
remaining small files where GCW-flavored display strings or faction-
keyed lookups need CW analogues. Six change sites:

  1. `parser/combat_commands.py::_check_bh_override` — accepts both
     `bh_guild` (GCW) and `bounty_hunters_guild` (CW) faction codes.

  2. `engine/npc_generator.py::ARCHETYPES` — extended with 5 CW
     archetypes (clone_trooper, arc_trooper, republic_officer,
     b1_battle_droid, jedi_knight).

  3. `engine/npc_combat_ai.py::DEFAULT_ARCHETYPE_BEHAVIOR` and
     `DEFAULT_ARCHETYPE_WEAPONS` — extended with same 5 CW archetypes.

  4. `engine/bounty_board.py::FUGITIVE_ARCHETYPES` — extended with
     CW archetypes (clone_trooper, arc_trooper, republic_officer).

  5. `engine/bounty_board.py::_get_crime_descriptions(era)` and
     `_get_posting_orgs(era)` — new era-aware flavor helpers.
     CW returns `_CW_CRIME_DESCRIPTIONS` (Republic instead of Imperial,
     Separatist instead of Rebel). GCW returns the legacy pool
     (byte-equivalent).

  6. `engine/space_anomalies.py` — new `_ATYPE_ERA_OVERLAY` dict
     supplies CW display strings for the `imperial` anomaly type.
     `Anomaly.display_name` and `Anomaly.description` consult the
     overlay first, fall through to legacy ANOMALY_TYPES on miss.
     The anomaly_type routing key stays `"imperial"` for byte-
     equivalence with `parser/encounter_commands.py` and
     `engine/space_encounters.py`; only the displayed text changes.

Tests are byte-equivalent: existing GCW behavior unchanged. CW
extensions are additive.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. combat_commands BH override accepts both eras
# ──────────────────────────────────────────────────────────────────────

class TestCombatBHOverrideAcceptsBothEras(unittest.TestCase):
    """Source-level check that the BH override accepts both GCW and CW
    faction codes for the bounty hunter guild."""

    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "parser", "combat_commands.py")
        with open(path, encoding="utf-8") as f:
            self.source = f.read()

    def test_accepts_both_codes(self):
        # The check should be against a tuple containing both codes,
        # not a literal equality check against just bh_guild.
        self.assertIn('"bh_guild"', self.source)
        self.assertIn('"bounty_hunters_guild"', self.source)
        # Specifically: there should be a `not in (..., ...)` guard.
        self.assertRegex(
            self.source,
            r'faction_id"\)\s*not in\s*\(.*?"bh_guild".*?"bounty_hunters_guild".*?\)',
        )


# ──────────────────────────────────────────────────────────────────────
# 2. npc_generator CW archetypes
# ──────────────────────────────────────────────────────────────────────

class TestNpcGeneratorCWArchetypes(unittest.TestCase):
    """The 5 CW archetypes are present and have proper structure."""

    def test_gcw_archetypes_still_present(self):
        from engine.npc_generator import ARCHETYPES
        for key in ("stormtrooper", "scout_trooper", "imperial_officer",
                    "bounty_hunter", "smuggler", "jedi", "creature"):
            self.assertIn(key, ARCHETYPES)

    def test_cw_archetypes_added(self):
        from engine.npc_generator import ARCHETYPES
        for key in ("clone_trooper", "arc_trooper", "republic_officer",
                    "b1_battle_droid", "jedi_knight"):
            self.assertIn(key, ARCHETYPES,
                          f"CW archetype '{key}' missing")

    def test_cw_archetypes_have_proper_shape(self):
        from engine.npc_generator import ARCHETYPES, NPCArchetype
        for key in ("clone_trooper", "arc_trooper", "republic_officer",
                    "b1_battle_droid", "jedi_knight"):
            arch = ARCHETYPES[key]
            self.assertIsInstance(arch, NPCArchetype)
            self.assertTrue(arch.name)
            self.assertTrue(arch.primary_skills)

    def test_jedi_knight_is_force_sensitive(self):
        from engine.npc_generator import ARCHETYPES
        self.assertTrue(ARCHETYPES["jedi_knight"].force_sensitive)

    def test_clone_trooper_has_blaster_skills(self):
        """Clone troopers are blaster-focused like stormtroopers."""
        from engine.npc_generator import ARCHETYPES
        skills = ARCHETYPES["clone_trooper"].primary_skills
        self.assertIn("blaster", skills)
        self.assertIn("dodge", skills)


# ──────────────────────────────────────────────────────────────────────
# 3. npc_combat_ai CW archetype defaults
# ──────────────────────────────────────────────────────────────────────

class TestNpcCombatAICWDefaults(unittest.TestCase):
    """Both behavior and weapon defaults must include all 5 CW archetypes."""

    def test_gcw_defaults_unchanged(self):
        from engine.npc_combat_ai import (
            DEFAULT_ARCHETYPE_BEHAVIOR, DEFAULT_ARCHETYPE_WEAPONS,
        )
        # Spot-check key GCW entries.
        self.assertEqual(DEFAULT_ARCHETYPE_BEHAVIOR["stormtrooper"], "aggressive")
        self.assertEqual(DEFAULT_ARCHETYPE_BEHAVIOR["jedi"], "aggressive")
        self.assertEqual(DEFAULT_ARCHETYPE_WEAPONS["stormtrooper"], "blaster_rifle")
        self.assertEqual(DEFAULT_ARCHETYPE_WEAPONS["jedi"], "lightsaber")

    def test_cw_archetypes_have_behavior(self):
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_BEHAVIOR
        for key in ("clone_trooper", "arc_trooper", "republic_officer",
                    "b1_battle_droid", "jedi_knight"):
            self.assertIn(key, DEFAULT_ARCHETYPE_BEHAVIOR,
                          f"CW archetype '{key}' missing combat behavior")

    def test_cw_archetypes_have_weapons(self):
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_WEAPONS
        for key in ("clone_trooper", "arc_trooper", "republic_officer",
                    "b1_battle_droid", "jedi_knight"):
            self.assertIn(key, DEFAULT_ARCHETYPE_WEAPONS,
                          f"CW archetype '{key}' missing weapon default")

    def test_jedi_knight_has_lightsaber(self):
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_WEAPONS
        self.assertEqual(DEFAULT_ARCHETYPE_WEAPONS["jedi_knight"], "lightsaber")

    def test_clone_trooper_has_blaster_rifle(self):
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_WEAPONS
        self.assertEqual(DEFAULT_ARCHETYPE_WEAPONS["clone_trooper"], "blaster_rifle")

    def test_b1_battle_droid_aggressive_per_programming(self):
        """Battle droids are programmed aggressive — not cowardly."""
        from engine.npc_combat_ai import DEFAULT_ARCHETYPE_BEHAVIOR
        self.assertEqual(DEFAULT_ARCHETYPE_BEHAVIOR["b1_battle_droid"], "aggressive")


# ──────────────────────────────────────────────────────────────────────
# 4. bounty_board FUGITIVE_ARCHETYPES + era flavor
# ──────────────────────────────────────────────────────────────────────

class TestBountyBoardFugitiveArchetypes(unittest.TestCase):

    def test_gcw_archetypes_still_present(self):
        from engine.bounty_board import FUGITIVE_ARCHETYPES
        for key in ("thug", "smuggler", "bounty_hunter", "scout",
                    "stormtrooper", "imperial_officer"):
            self.assertIn(key, FUGITIVE_ARCHETYPES)

    def test_cw_archetypes_added(self):
        from engine.bounty_board import FUGITIVE_ARCHETYPES
        for key in ("clone_trooper", "arc_trooper", "republic_officer"):
            self.assertIn(key, FUGITIVE_ARCHETYPES,
                          f"CW archetype '{key}' missing from FUGITIVE_ARCHETYPES")


class TestBountyBoardEraFlavor(unittest.TestCase):
    """The era-aware flavor helpers route to the correct pool."""

    def _patch_active_era(self, era):
        """Patch get_active_era to return the given era."""
        return patch(
            "engine.era_state.get_active_era",
            return_value=era,
        )

    def test_gcw_era_returns_gcw_crime_pool(self):
        from engine.bounty_board import (
            _get_crime_descriptions, _CRIME_DESCRIPTIONS,
        )
        with self._patch_active_era("gcw"):
            result = _get_crime_descriptions()
        self.assertIs(result, _CRIME_DESCRIPTIONS)

    def test_clone_wars_era_returns_cw_crime_pool(self):
        from engine.bounty_board import (
            _get_crime_descriptions, _CW_CRIME_DESCRIPTIONS,
        )
        with self._patch_active_era("clone_wars"):
            result = _get_crime_descriptions()
        self.assertIs(result, _CW_CRIME_DESCRIPTIONS)

    def test_gcw_era_returns_gcw_posting_pool(self):
        from engine.bounty_board import _get_posting_orgs, _POSTING_ORGS
        with self._patch_active_era("gcw"):
            result = _get_posting_orgs()
        self.assertIs(result, _POSTING_ORGS)

    def test_clone_wars_era_returns_cw_posting_pool(self):
        from engine.bounty_board import _get_posting_orgs, _CW_POSTING_ORGS
        with self._patch_active_era("clone_wars"):
            result = _get_posting_orgs()
        self.assertIs(result, _CW_POSTING_ORGS)

    def test_explicit_era_argument_overrides_active(self):
        """When called with an explicit era, that wins over get_active_era."""
        from engine.bounty_board import (
            _get_crime_descriptions, _CW_CRIME_DESCRIPTIONS,
        )
        with self._patch_active_era("gcw"):
            result = _get_crime_descriptions(era="clone_wars")
        self.assertIs(result, _CW_CRIME_DESCRIPTIONS)

    def test_unknown_era_falls_back_to_gcw(self):
        from engine.bounty_board import (
            _get_crime_descriptions, _CRIME_DESCRIPTIONS,
        )
        with self._patch_active_era("nonexistent"):
            result = _get_crime_descriptions()
        self.assertIs(result, _CRIME_DESCRIPTIONS)

    def test_cw_pool_is_era_themed(self):
        """CW pools should mention Republic/Separatist, not Imperial/Rebel."""
        from engine.bounty_board import _CW_CRIME_DESCRIPTIONS, _CW_POSTING_ORGS
        full = " ".join(_CW_CRIME_DESCRIPTIONS) + " " + " ".join(_CW_POSTING_ORGS)
        # Must mention Republic
        self.assertIn("Republic", full)
        # Should mention Separatist (in crime descriptions)
        self.assertIn("Separatist", " ".join(_CW_CRIME_DESCRIPTIONS))
        # Must NOT mention Imperial Garrison (CW posting orgs are Republic)
        self.assertNotIn("Imperial Garrison", " ".join(_CW_POSTING_ORGS))

    def test_gcw_pool_unchanged(self):
        """GCW pools byte-equivalent to pre-B.1.g: 10 crime descriptions,
        6 posting orgs."""
        from engine.bounty_board import _CRIME_DESCRIPTIONS, _POSTING_ORGS
        self.assertEqual(len(_CRIME_DESCRIPTIONS), 10)
        self.assertEqual(len(_POSTING_ORGS), 6)
        # Specific spot check
        self.assertIn("Imperial Garrison, Mos Eisley", _POSTING_ORGS)


# ──────────────────────────────────────────────────────────────────────
# 5. space_anomalies era overlay
# ──────────────────────────────────────────────────────────────────────

class TestSpaceAnomaliesEraOverlay(unittest.TestCase):
    """The `imperial` anomaly type gets era-aware display in CW mode."""

    def _patch_active_era(self, era):
        return patch(
            "engine.era_state.get_active_era",
            return_value=era,
        )

    def _make_anomaly(self, atype="imperial", resolution=0):
        from engine.space_anomalies import Anomaly
        return Anomaly(id=1, zone_id="z1",
                       anomaly_type=atype, resolution=resolution)

    def test_gcw_anomaly_uses_legacy_imperial_display(self):
        a = self._make_anomaly(resolution=2)
        with self._patch_active_era("gcw"):
            self.assertEqual(a.display_name, "Imperial Dead Drop")
            self.assertIn("Imperial", a.description())

    def test_clone_wars_anomaly_uses_republic_display(self):
        """The B.1.g headline: same anomaly_type='imperial' (routing key),
        Republic-flavored display in CW mode."""
        a = self._make_anomaly(resolution=2)
        with self._patch_active_era("clone_wars"):
            self.assertEqual(a.display_name, "Republic Dead Drop")
            desc = a.description()
            self.assertIn("Republic", desc)
            # Must NOT mention Imperial — that's the GCW phrasing.
            self.assertNotIn("Imperial", desc)

    def test_clone_wars_resolution_0_uses_overlay(self):
        a = self._make_anomaly(resolution=0)
        with self._patch_active_era("clone_wars"):
            # Resolution 0 = vague; same string as GCW (no era word here).
            self.assertEqual(
                a.description(),
                "Encrypted tight-beam burst. Source: unknown.",
            )

    def test_clone_wars_resolution_1_uses_overlay(self):
        a = self._make_anomaly(resolution=1)
        with self._patch_active_era("clone_wars"):
            desc = a.description()
            self.assertIn("Republic cipher signature", desc)

    def test_non_overlay_anomaly_uses_legacy(self):
        """An anomaly type without an overlay (e.g. 'pirates') uses the
        legacy display in BOTH eras — overlay is opt-in per type."""
        a = self._make_anomaly(atype="pirates", resolution=2)
        with self._patch_active_era("clone_wars"):
            self.assertEqual(a.display_name, "Pirate Nest")
            self.assertIn("Pirate", a.description())

    def test_unknown_era_falls_back_to_legacy(self):
        a = self._make_anomaly(resolution=2)
        with self._patch_active_era("bogus_era"):
            # No overlay for bogus_era → legacy GCW display.
            self.assertEqual(a.display_name, "Imperial Dead Drop")

    def test_id_substitution_works_in_overlay(self):
        """The {id} placeholder must still be filled when using overlay."""
        a = self._make_anomaly(resolution=2)
        a.id = 42
        with self._patch_active_era("clone_wars"):
            desc = a.description()
            self.assertIn("42", desc)
            self.assertNotIn("{id}", desc)


# ──────────────────────────────────────────────────────────────────────
# 6. Module imports clean
# ──────────────────────────────────────────────────────────────────────

class TestModuleImportsClean(unittest.TestCase):
    def test_all_modules_import(self):
        import importlib
        for mod_name in ("parser.combat_commands", "engine.npc_generator",
                         "engine.npc_combat_ai", "engine.bounty_board",
                         "engine.space_anomalies"):
            mod = importlib.import_module(mod_name)
            self.assertTrue(mod is not None)


if __name__ == "__main__":
    unittest.main()
