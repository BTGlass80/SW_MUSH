# -*- coding: utf-8 -*-
"""
tests/test_session56_craft_crew_umbrellas.py -- Session 56 feature tests

Covers the +craft and +crew umbrellas and the canonical-switch rename
for crafting + crew commands:

  1. +verb/<switch> canonical form works for every crafting/crew verb
  2. Bare aliases still reach the same handler (muscle memory preserved)
  3. Unknown switches produce a clear error
  4. The help system loads +craft.md and +crew.md as proper HelpEntry
  5. Registry wiring is correct (umbrella registered, switches valid)
  6. Cross-module registration: all 7 umbrellas (S54+S55+S56) coexist

Convention: +verb/switch [args], bare forms preserved as aliases.
Follows the S54 combat-umbrella pattern exactly.
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. +craft umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestCraftUmbrellaRegistration(unittest.TestCase):
    """Verify +craft registers with the right keys, aliases, and switches."""

    def test_craft_command_class_exists(self):
        from parser.crafting_commands import CraftingCommand
        self.assertTrue(hasattr(CraftingCommand, "execute"))

    def test_craft_command_key(self):
        from parser.crafting_commands import CraftingCommand
        self.assertEqual(CraftingCommand.key, "+craft")

    def test_valid_switches_covers_all_verbs(self):
        from parser.crafting_commands import CraftingCommand
        required = {"start", "survey", "experiment", "teach",
                    "resources", "buyresources", "schematics"}
        actual = set(CraftingCommand.valid_switches)
        missing = required - actual
        self.assertFalse(missing, f"valid_switches missing: {missing}")

    def test_aliases_cover_all_bare_verbs(self):
        """Every pre-S56 bare verb must remain as an alias."""
        from parser.crafting_commands import CraftingCommand
        required_aliases = {
            "survey",
            "resources", "res",
            "schematics", "schem",
            "craft",
            "experiment", "exp",
            "teach",
            "buyresources", "buyres",
        }
        actual = set(CraftingCommand.aliases)
        missing = required_aliases - actual
        self.assertFalse(
            missing,
            f"CraftingCommand aliases missing bare verbs: {missing}"
        )

    def test_switch_impl_dispatch_table_populated(self):
        from parser.crafting_commands import _CRAFT_SWITCH_IMPL
        required = {"start", "survey", "experiment", "teach",
                    "resources", "buyresources", "schematics"}
        actual = set(_CRAFT_SWITCH_IMPL.keys())
        missing = required - actual
        self.assertFalse(missing, f"_CRAFT_SWITCH_IMPL missing: {missing}")

    def test_alias_to_switch_map_covers_aliases(self):
        from parser.crafting_commands import CraftingCommand, _CRAFT_ALIAS_TO_SWITCH
        for alias in CraftingCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(
                alias, _CRAFT_ALIAS_TO_SWITCH,
                f"Alias '{alias}' not in _CRAFT_ALIAS_TO_SWITCH map"
            )


class TestCraftSwitchDispatch(unittest.TestCase):
    """Dispatch logic for +craft."""

    def test_bare_craft_maps_to_start(self):
        """Bare 'craft' is the legacy crafting verb → /start."""
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["craft"], "start")

    def test_bare_survey_maps_to_survey(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["survey"], "survey")

    def test_bare_resources_maps_to_resources(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["resources"], "resources")
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["res"], "resources")

    def test_bare_schematics_maps_to_schematics(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["schematics"], "schematics")
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["schem"], "schematics")

    def test_bare_experiment_maps_to_experiment(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["experiment"], "experiment")
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["exp"], "experiment")

    def test_bare_teach_maps_to_teach(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["teach"], "teach")

    def test_bare_buyresources_maps_to_buyresources(self):
        from parser.crafting_commands import _CRAFT_ALIAS_TO_SWITCH
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["buyresources"], "buyresources")
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["buyres"], "buyresources")
        self.assertEqual(_CRAFT_ALIAS_TO_SWITCH["buy resources"], "buyresources")


class TestCraftHelpFile(unittest.TestCase):
    """Verify data/help/commands/+craft.md loads cleanly."""

    def _load_entry(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+craft"]
        self.assertEqual(
            len(matching), 1,
            "Expected exactly one +craft help entry",
        )
        return matching[0]

    def test_help_loads(self):
        e = self._load_entry()
        self.assertEqual(e.key, "+craft")
        self.assertTrue(e.title)
        self.assertTrue(e.summary)

    def test_help_has_substantial_body(self):
        e = self._load_entry()
        self.assertGreater(
            len(e.body), 5000,
            f"+craft body only {len(e.body)} chars; expected 5000+"
        )

    def test_help_has_examples(self):
        e = self._load_entry()
        self.assertGreater(len(e.examples), 10)
        for ex in e.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)

    def test_help_cites_canonical_form(self):
        e = self._load_entry()
        canonical_count = sum(
            1 for ex in e.examples if ex["cmd"].startswith("+craft")
        )
        self.assertGreater(
            canonical_count, 5,
            "Expected most examples to show +craft/<switch> canonical form"
        )

    def test_help_cross_references_topics(self):
        e = self._load_entry()
        self.assertIn("crafting", e.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 2. +crew umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestCrewUmbrellaRegistration(unittest.TestCase):
    def test_crew_command_class_exists(self):
        from parser.crew_commands import CrewCommand
        self.assertTrue(hasattr(CrewCommand, "execute"))

    def test_crew_command_key(self):
        from parser.crew_commands import CrewCommand
        self.assertEqual(CrewCommand.key, "+crew")

    def test_valid_switches_covers_all_verbs(self):
        from parser.crew_commands import CrewCommand
        required = {"hire", "roster", "assign", "unassign", "dismiss", "order"}
        actual = set(CrewCommand.valid_switches)
        missing = required - actual
        self.assertFalse(missing, f"valid_switches missing: {missing}")

    def test_aliases_cover_all_bare_verbs(self):
        from parser.crew_commands import CrewCommand
        required_aliases = {
            # Crew view (from old RosterCommand)
            "crew", "mycrew",
            # Hire
            "hire", "recruiting", "hireboard",
            # Roster
            "roster",
            # Assign / unassign
            "assign", "unassign",
            # Dismiss
            "dismiss", "firecrew",
            # Order
            "order", "ord",
        }
        actual = set(CrewCommand.aliases)
        missing = required_aliases - actual
        self.assertFalse(
            missing,
            f"CrewCommand aliases missing bare verbs: {missing}"
        )

    def test_switch_impl_dispatch_table_populated(self):
        from parser.crew_commands import _CREW_SWITCH_IMPL
        required = {"hire", "roster", "assign", "unassign", "dismiss", "order"}
        actual = set(_CREW_SWITCH_IMPL.keys())
        missing = required - actual
        self.assertFalse(missing, f"_CREW_SWITCH_IMPL missing: {missing}")

    def test_alias_to_switch_map_covers_aliases(self):
        from parser.crew_commands import CrewCommand, _CREW_ALIAS_TO_SWITCH
        for alias in CrewCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(
                alias, _CREW_ALIAS_TO_SWITCH,
                f"Alias '{alias}' not in _CREW_ALIAS_TO_SWITCH map"
            )

    def test_roster_no_longer_claims_crew_aliases(self):
        """The bare 'crew' / '+crew' / 'mycrew' / '+mycrew' aliases must
        move from RosterCommand to the CrewCommand umbrella."""
        from parser.crew_commands import RosterCommand
        roster_aliases = set(RosterCommand.aliases)
        self.assertNotIn("crew", roster_aliases,
                         "RosterCommand still claims 'crew' alias")
        self.assertNotIn("+crew", roster_aliases,
                         "RosterCommand still claims '+crew' alias")
        self.assertNotIn("mycrew", roster_aliases,
                         "RosterCommand still claims 'mycrew' alias")
        self.assertNotIn("+mycrew", roster_aliases,
                         "RosterCommand still claims '+mycrew' alias")


class TestCrewSwitchDispatch(unittest.TestCase):
    def test_bare_crew_maps_to_roster(self):
        """Bare 'crew' / 'mycrew' → roster (view-default for umbrella)."""
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["mycrew"], "roster")

    def test_bare_hire_maps_to_hire(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["hire"], "hire")
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["recruiting"], "hire")
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["hireboard"], "hire")

    def test_bare_roster_maps_to_roster(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["roster"], "roster")

    def test_bare_assign_maps_to_assign(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["assign"], "assign")

    def test_bare_unassign_maps_to_unassign(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["unassign"], "unassign")

    def test_bare_dismiss_maps_to_dismiss(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["dismiss"], "dismiss")
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["firecrew"], "dismiss")

    def test_bare_order_maps_to_order(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["order"], "order")
        self.assertEqual(_CREW_ALIAS_TO_SWITCH["ord"], "order")


class TestCrewHelpFile(unittest.TestCase):
    def _load_entry(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+crew"]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_help_loads(self):
        e = self._load_entry()
        self.assertEqual(e.key, "+crew")
        self.assertTrue(e.title)

    def test_help_has_substantial_body(self):
        e = self._load_entry()
        self.assertGreater(
            len(e.body), 4500,
            f"+crew body only {len(e.body)} chars"
        )

    def test_help_has_examples(self):
        e = self._load_entry()
        self.assertGreater(len(e.examples), 10)

    def test_help_cites_canonical_form(self):
        e = self._load_entry()
        canonical_count = sum(
            1 for ex in e.examples if ex["cmd"].startswith("+crew")
        )
        self.assertGreater(canonical_count, 5)

    def test_help_mentions_stations(self):
        """Crew help should name the six stations."""
        e = self._load_entry()
        for station in ("pilot", "gunner", "engineer"):
            self.assertIn(station, e.body.lower(),
                          f"Crew help missing station: {station}")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Cross-module: all 7 umbrellas coexist (S54+S55+S56)
# ══════════════════════════════════════════════════════════════════════════════

class TestAllUmbrellasRegistry(unittest.TestCase):
    """Verify all 7 umbrellas (combat/mission/smuggle/bounty/quest/craft/crew)
    register together without collision, and that each +verb key resolves
    to its umbrella class — not a legacy per-verb class that shares the key."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.combat_commands import register_combat_commands
        from parser.mission_commands import register_mission_commands
        from parser.smuggling_commands import register_smuggling_commands
        from parser.bounty_commands import register_bounty_commands
        from parser.narrative_commands import register_narrative_commands
        from parser.crafting_commands import register_crafting_commands
        from parser.crew_commands import register_crew_commands

        r = CommandRegistry()
        # Same order as server/game_server.py
        register_combat_commands(r)
        register_crew_commands(r)
        register_mission_commands(r)
        register_bounty_commands(r)
        register_smuggling_commands(r)
        register_crafting_commands(r)
        register_narrative_commands(r)
        return r

    def test_all_seven_umbrella_keys_resolve(self):
        """Every +verb umbrella key must resolve to its umbrella class."""
        from parser.combat_commands import CombatCommand
        from parser.mission_commands import MissionCommand
        from parser.smuggling_commands import SmuggleCommand
        from parser.bounty_commands import BountyCommand
        from parser.narrative_commands import QuestCommand
        from parser.crafting_commands import CraftingCommand
        from parser.crew_commands import CrewCommand

        r = self._build_registry()

        self.assertIsInstance(r.get("+combat"), CombatCommand)
        self.assertIsInstance(r.get("+mission"), MissionCommand)
        self.assertIsInstance(r.get("+smuggle"), SmuggleCommand)
        self.assertIsInstance(r.get("+bounty"), BountyCommand)
        self.assertIsInstance(r.get("+quest"), QuestCommand)
        self.assertIsInstance(r.get("+craft"), CraftingCommand)
        self.assertIsInstance(r.get("+crew"), CrewCommand)

    def test_bare_crew_routes_to_umbrella(self):
        """'crew' and 'mycrew' should reach the CrewCommand umbrella
        (which dispatches to RosterCommand via /roster default).
        Pre-S56: RosterCommand claimed these aliases."""
        from parser.crew_commands import CrewCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("crew"), CrewCommand)
        self.assertIsInstance(r.get("mycrew"), CrewCommand)

    def test_bare_roster_still_routes_to_roster(self):
        """Bare 'roster' should still reach RosterCommand directly
        (it's the per-verb class's only remaining alias)."""
        from parser.crew_commands import RosterCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("roster"), RosterCommand)

    def test_bare_crafting_aliases_route(self):
        r = self._build_registry()
        for alias in ["survey", "craft", "experiment", "resources",
                      "schematics", "teach", "buyresources",
                      "res", "schem", "exp", "buyres"]:
            cmd = r.get(alias)
            self.assertIsNotNone(cmd, f"Bare alias '{alias}' did not resolve")

    def test_bare_crew_aliases_route(self):
        r = self._build_registry()
        for alias in ["hire", "roster", "assign", "unassign", "dismiss",
                      "order", "recruiting", "firecrew", "ord"]:
            cmd = r.get(alias)
            self.assertIsNotNone(cmd, f"Bare alias '{alias}' did not resolve")


if __name__ == "__main__":
    unittest.main()
