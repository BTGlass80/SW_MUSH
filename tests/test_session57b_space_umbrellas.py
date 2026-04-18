# -*- coding: utf-8 -*-
"""
tests/test_session57b_space_umbrellas.py -- Session 57b feature tests

Covers the +pilot, +gunner, +sensors, +bridge umbrellas (S57b).

S57b adds four new umbrella classes to parser/space_commands.py:
  PilotStationCommand    — key="+pilot",   11 switches, 21 aliases
  GunnerStationCommand   — key="+gunner",   3 switches,  6 aliases
  SensorsStationCommand  — key="+sensors",  3 switches,  4 aliases
  BridgeCommand          — key="+bridge",  12 switches, 24 aliases

Combined with S57a's expanded +ship umbrella, this completes the
space rename sweep. All 51 space command classes now have canonical
+verb/switch forms while preserving bare-word aliases.

Convention: +verb/switch [args], bare forms preserved as aliases.
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. +pilot umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestPilotUmbrellaRegistration(unittest.TestCase):
    def test_class_exists(self):
        from parser.space_commands import PilotStationCommand
        self.assertTrue(hasattr(PilotStationCommand, "execute"))

    def test_key(self):
        from parser.space_commands import PilotStationCommand
        self.assertEqual(PilotStationCommand.key, "+pilot")

    def test_valid_switches(self):
        from parser.space_commands import PilotStationCommand
        required = {"claim", "evade", "jink", "barrelroll", "loop", "slip",
                    "tail", "outmaneuver", "close", "flee", "course"}
        actual = set(PilotStationCommand.valid_switches)
        self.assertFalse(required - actual)

    def test_aliases_cover_bare_verbs(self):
        from parser.space_commands import PilotStationCommand
        required = {
            "pilot",
            "evade", "evasive",
            "jink",
            "barrelroll", "broll",
            "loop", "immelmann",
            "slip", "sideslip",
            "tail", "getbehind",
            "outmaneuver", "shake",
            "close", "approach",
            "fleeship", "breakaway",
            "course", "navigate", "setcourse",
        }
        actual = set(PilotStationCommand.aliases)
        missing = required - actual
        self.assertFalse(missing, f"Missing aliases: {missing}")

    def test_switch_impl_populated(self):
        from parser.space_commands import _PILOT_SWITCH_IMPL
        required = {"claim", "evade", "jink", "barrelroll", "loop",
                    "slip", "tail", "outmaneuver", "close", "flee", "course"}
        self.assertFalse(required - set(_PILOT_SWITCH_IMPL.keys()))

    def test_alias_map_covers_aliases(self):
        from parser.space_commands import PilotStationCommand, _PILOT_ALIAS_TO_SWITCH
        for alias in PilotStationCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _PILOT_ALIAS_TO_SWITCH,
                          f"Alias '{alias}' not in alias→switch map")


class TestPilotSwitchDispatch(unittest.TestCase):
    def test_evade_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["evade"], "evade")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["evasive"], "evade")

    def test_barrelroll_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["barrelroll"], "barrelroll")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["broll"], "barrelroll")

    def test_loop_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["loop"], "loop")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["immelmann"], "loop")

    def test_slip_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["slip"], "slip")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["sideslip"], "slip")

    def test_tail_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["tail"], "tail")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["getbehind"], "tail")

    def test_outmaneuver_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["outmaneuver"], "outmaneuver")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["shake"], "outmaneuver")

    def test_close_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["close"], "close")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["approach"], "close")

    def test_flee_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["fleeship"], "flee")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["breakaway"], "flee")

    def test_course_aliases(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["course"], "course")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["navigate"], "course")
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["setcourse"], "course")

    def test_bare_pilot_maps_to_claim(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        self.assertEqual(_PILOT_ALIAS_TO_SWITCH["pilot"], "claim")


class TestPilotHelpFile(unittest.TestCase):
    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+pilot"]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+pilot")
        self.assertTrue(e.title)

    def test_body_dense(self):
        e = self._load()
        self.assertGreater(len(e.body), 3000)

    def test_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)

    def test_canonical_form_in_examples(self):
        e = self._load()
        n = sum(1 for ex in e.examples if ex["cmd"].startswith("+pilot"))
        self.assertGreater(n, 7)


# ══════════════════════════════════════════════════════════════════════════════
# 2. +gunner umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestGunnerUmbrellaRegistration(unittest.TestCase):
    def test_class_exists(self):
        from parser.space_commands import GunnerStationCommand
        self.assertTrue(hasattr(GunnerStationCommand, "execute"))

    def test_key(self):
        from parser.space_commands import GunnerStationCommand
        self.assertEqual(GunnerStationCommand.key, "+gunner")

    def test_valid_switches(self):
        from parser.space_commands import GunnerStationCommand
        required = {"claim", "fire", "lockon"}
        self.assertFalse(required - set(GunnerStationCommand.valid_switches))

    def test_aliases_cover_bare_verbs(self):
        from parser.space_commands import GunnerStationCommand
        required = {"gunner", "gunnery", "fire", "lockon", "lock", "targetlock"}
        missing = required - set(GunnerStationCommand.aliases)
        self.assertFalse(missing, f"Missing: {missing}")

    def test_switch_impl_populated(self):
        from parser.space_commands import _GUNNER_SWITCH_IMPL
        self.assertEqual(set(_GUNNER_SWITCH_IMPL.keys()),
                         {"claim", "fire", "lockon"})

    def test_alias_map_covers_aliases(self):
        from parser.space_commands import GunnerStationCommand, _GUNNER_ALIAS_TO_SWITCH
        for alias in GunnerStationCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _GUNNER_ALIAS_TO_SWITCH)


class TestGunnerSwitchDispatch(unittest.TestCase):
    def test_bare_gunner_maps_to_claim(self):
        from parser.space_commands import _GUNNER_ALIAS_TO_SWITCH
        self.assertEqual(_GUNNER_ALIAS_TO_SWITCH["gunner"], "claim")
        # gunnery post-S57a should also now route to gunner (not board)
        self.assertEqual(_GUNNER_ALIAS_TO_SWITCH["gunnery"], "claim")

    def test_fire_alias(self):
        from parser.space_commands import _GUNNER_ALIAS_TO_SWITCH
        self.assertEqual(_GUNNER_ALIAS_TO_SWITCH["fire"], "fire")

    def test_lockon_aliases(self):
        from parser.space_commands import _GUNNER_ALIAS_TO_SWITCH
        for alias in ("lockon", "lock", "targetlock"):
            self.assertEqual(_GUNNER_ALIAS_TO_SWITCH[alias], "lockon")


class TestGunnerHelpFile(unittest.TestCase):
    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+gunner"]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+gunner")

    def test_body_present(self):
        e = self._load()
        self.assertGreater(len(e.body), 1500)

    def test_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)


# ══════════════════════════════════════════════════════════════════════════════
# 3. +sensors umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestSensorsUmbrellaRegistration(unittest.TestCase):
    def test_class_exists(self):
        from parser.space_commands import SensorsStationCommand
        self.assertTrue(hasattr(SensorsStationCommand, "execute"))

    def test_key(self):
        from parser.space_commands import SensorsStationCommand
        self.assertEqual(SensorsStationCommand.key, "+sensors")

    def test_valid_switches(self):
        from parser.space_commands import SensorsStationCommand
        required = {"claim", "scan", "deepscan"}
        self.assertFalse(required - set(SensorsStationCommand.valid_switches))

    def test_aliases_cover_bare_verbs(self):
        from parser.space_commands import SensorsStationCommand
        required = {"sensors", "sensor", "scan", "deepscan"}
        self.assertFalse(required - set(SensorsStationCommand.aliases))

    def test_switch_impl_populated(self):
        from parser.space_commands import _SENSORS_SWITCH_IMPL
        self.assertEqual(set(_SENSORS_SWITCH_IMPL.keys()),
                         {"claim", "scan", "deepscan"})

    def test_alias_map_covers_aliases(self):
        from parser.space_commands import SensorsStationCommand, _SENSORS_ALIAS_TO_SWITCH
        for alias in SensorsStationCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _SENSORS_ALIAS_TO_SWITCH)


class TestSensorsSwitchDispatch(unittest.TestCase):
    def test_bare_sensors_maps_to_claim(self):
        from parser.space_commands import _SENSORS_ALIAS_TO_SWITCH
        self.assertEqual(_SENSORS_ALIAS_TO_SWITCH["sensors"], "claim")
        self.assertEqual(_SENSORS_ALIAS_TO_SWITCH["sensor"], "claim")

    def test_scan_alias(self):
        from parser.space_commands import _SENSORS_ALIAS_TO_SWITCH
        self.assertEqual(_SENSORS_ALIAS_TO_SWITCH["scan"], "scan")

    def test_deepscan_alias(self):
        from parser.space_commands import _SENSORS_ALIAS_TO_SWITCH
        self.assertEqual(_SENSORS_ALIAS_TO_SWITCH["deepscan"], "deepscan")


class TestSensorsHelpFile(unittest.TestCase):
    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+sensors"]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+sensors")

    def test_body_present(self):
        e = self._load()
        self.assertGreater(len(e.body), 1500)

    def test_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)


# ══════════════════════════════════════════════════════════════════════════════
# 4. +bridge umbrella
# ══════════════════════════════════════════════════════════════════════════════

class TestBridgeUmbrellaRegistration(unittest.TestCase):
    def test_class_exists(self):
        from parser.space_commands import BridgeCommand
        self.assertTrue(hasattr(BridgeCommand, "execute"))

    def test_key(self):
        from parser.space_commands import BridgeCommand
        self.assertEqual(BridgeCommand.key, "+bridge")

    def test_valid_switches(self):
        from parser.space_commands import BridgeCommand
        required = {"claim", "order", "hail", "comms", "shields", "power",
                    "transponder", "resist", "damcon", "vacate", "assist",
                    "coordinate"}
        actual = set(BridgeCommand.valid_switches)
        self.assertFalse(required - actual)

    def test_aliases_cover_bare_verbs(self):
        from parser.space_commands import BridgeCommand
        required = {
            "commander", "command", "captain",
            "order", "orders",
            "hail",
            "comms", "comm", "radio",
            "shields",
            "power", "pwr",
            "transponder", "transp",
            "resist", "breakfree",
            "damcon", "damagecontrol", "repair",
            "vacate", "unstation",
            "assist",
            "coordinate", "coord",
        }
        actual = set(BridgeCommand.aliases)
        missing = required - actual
        self.assertFalse(missing, f"Missing aliases: {missing}")

    def test_switch_impl_populated(self):
        from parser.space_commands import _BRIDGE_SWITCH_IMPL
        required = {"claim", "order", "hail", "comms", "shields", "power",
                    "transponder", "resist", "damcon", "vacate", "assist",
                    "coordinate"}
        self.assertFalse(required - set(_BRIDGE_SWITCH_IMPL.keys()))

    def test_alias_map_covers_aliases(self):
        from parser.space_commands import BridgeCommand, _BRIDGE_ALIAS_TO_SWITCH
        for alias in BridgeCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _BRIDGE_ALIAS_TO_SWITCH)


class TestBridgeSwitchDispatch(unittest.TestCase):
    def test_commander_aliases_map_to_claim(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        for alias in ("commander", "command", "captain"):
            self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH[alias], "claim")

    def test_order_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["order"], "order")
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["orders"], "order")

    def test_comms_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        for alias in ("comms", "comm", "radio"):
            self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH[alias], "comms")

    def test_power_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["power"], "power")
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["pwr"], "power")

    def test_damcon_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        for alias in ("damcon", "damagecontrol", "repair"):
            self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH[alias], "damcon")

    def test_vacate_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["vacate"], "vacate")
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["unstation"], "vacate")

    def test_resist_aliases(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["resist"], "resist")
        self.assertEqual(_BRIDGE_ALIAS_TO_SWITCH["breakfree"], "resist")


class TestBridgeHelpFile(unittest.TestCase):
    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+bridge"]
        self.assertEqual(len(matching), 1)
        return matching[0]

    def test_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+bridge")

    def test_body_dense(self):
        e = self._load()
        self.assertGreater(len(e.body), 4000)

    def test_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 15)

    def test_documents_order_collision(self):
        """The +bridge help must explain the order collision with +crew."""
        e = self._load()
        body_lower = e.body.lower()
        self.assertIn("crew", body_lower)
        self.assertIn("order", body_lower)


# ══════════════════════════════════════════════════════════════════════════════
# 5. Cross-module: all 12 umbrellas register (S54+S55+S56+S57a+S57b)
# ══════════════════════════════════════════════════════════════════════════════

class TestAllTwelveUmbrellasRegister(unittest.TestCase):
    """The complete umbrella set after the rename sweep."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.combat_commands import register_combat_commands
        from parser.mission_commands import register_mission_commands
        from parser.smuggling_commands import register_smuggling_commands
        from parser.bounty_commands import register_bounty_commands
        from parser.narrative_commands import register_narrative_commands
        from parser.crafting_commands import register_crafting_commands
        from parser.crew_commands import register_crew_commands
        from parser.space_commands import register_space_commands

        r = CommandRegistry()
        register_combat_commands(r)
        register_space_commands(r)
        register_crew_commands(r)
        register_mission_commands(r)
        register_bounty_commands(r)
        register_smuggling_commands(r)
        register_crafting_commands(r)
        register_narrative_commands(r)
        return r

    def test_all_twelve_umbrellas_resolve(self):
        from parser.combat_commands import CombatCommand
        from parser.mission_commands import MissionCommand
        from parser.smuggling_commands import SmuggleCommand
        from parser.bounty_commands import BountyCommand
        from parser.narrative_commands import QuestCommand
        from parser.crafting_commands import CraftingCommand
        from parser.crew_commands import CrewCommand
        from parser.space_commands import (
            ShipCommand, PilotStationCommand, GunnerStationCommand,
            SensorsStationCommand, BridgeCommand,
        )

        r = self._build_registry()

        self.assertIsInstance(r.get("+combat"), CombatCommand)
        self.assertIsInstance(r.get("+mission"), MissionCommand)
        self.assertIsInstance(r.get("+smuggle"), SmuggleCommand)
        self.assertIsInstance(r.get("+bounty"), BountyCommand)
        self.assertIsInstance(r.get("+quest"), QuestCommand)
        self.assertIsInstance(r.get("+craft"), CraftingCommand)
        self.assertIsInstance(r.get("+crew"), CrewCommand)
        self.assertIsInstance(r.get("+ship"), ShipCommand)
        self.assertIsInstance(r.get("+pilot"), PilotStationCommand)
        self.assertIsInstance(r.get("+gunner"), GunnerStationCommand)
        self.assertIsInstance(r.get("+sensors"), SensorsStationCommand)
        self.assertIsInstance(r.get("+bridge"), BridgeCommand)

    def test_bare_order_still_goes_to_crew(self):
        """Per S57b design: bare `order` continues to route to
        crew_commands.OrderCommand by registration order. Canonical
        forms +crew/order and +bridge/order disambiguate."""
        import parser.crew_commands as cc
        r = self._build_registry()
        cmd = r.get("order")
        self.assertIsInstance(cmd, cc.OrderCommand)

    def test_pilot_bare_aliases_route(self):
        """Bare maneuver verbs (evade, jink, etc.) must resolve."""
        r = self._build_registry()
        for alias in ["pilot", "evade", "jink", "barrelroll", "loop",
                      "slip", "tail", "outmaneuver", "close", "fleeship",
                      "course"]:
            self.assertIsNotNone(r.get(alias), f"Unresolved: {alias}")

    def test_gunner_bare_aliases_route(self):
        r = self._build_registry()
        for alias in ["gunner", "gunnery", "fire", "lockon", "lock"]:
            self.assertIsNotNone(r.get(alias), f"Unresolved: {alias}")

    def test_sensors_bare_aliases_route(self):
        r = self._build_registry()
        for alias in ["sensors", "sensor", "scan", "deepscan"]:
            self.assertIsNotNone(r.get(alias), f"Unresolved: {alias}")

    def test_bridge_bare_aliases_route(self):
        r = self._build_registry()
        for alias in ["commander", "command", "captain", "hail", "shields",
                      "power", "transponder", "resist", "damcon", "vacate",
                      "assist", "coordinate"]:
            self.assertIsNotNone(r.get(alias), f"Unresolved: {alias}")


if __name__ == "__main__":
    unittest.main()
