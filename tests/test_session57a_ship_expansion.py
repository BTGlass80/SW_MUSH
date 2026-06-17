# -*- coding: utf-8 -*-
"""
tests/test_session57a_ship_expansion.py -- ship umbrella tests

ORIGINALLY S57a (the umbrella absorbed sibling ship aliases while the
standalone sibling classes stayed registered for backward compat).

REFRAMED by command-syntax rework DROP 5b: the `+ship` umbrella is now
the SOLE canonical ship-admin command. The pure-delegator siblings
(ShipsCommand/+ships, ShipInfoCommand/+shipinfo, ShipRepairCommand/
+shiprepair, MyShipsCommand/+myships) were DELETED, and ShipNameCommand
is no longer registered (it survives only as the `+ship/rename`
switch-impl). The bare/`+`-shortcut forms are gone (A1: OOC/query
commands are `+`-prefixed; switches are PRIMARY; no redundant forms).

This file keeps the still-valid umbrella + help-file + gunnery
assertions and flips the now-inverted backward-compat assertions to
assert the clean end-state. The positive consolidation invariants live
in tests/test_command_syntax_drop5b_ship_family.py.
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. ShipCommand umbrella — the sole canonical ship-admin command
# ══════════════════════════════════════════════════════════════════════════════

class TestShipUmbrella(unittest.TestCase):
    """Verify +ship is the umbrella and carries every ship verb as a switch."""

    def test_ship_command_class_exists(self):
        from parser.space_commands import ShipCommand
        self.assertTrue(hasattr(ShipCommand, "execute"))

    def test_ship_command_key(self):
        from parser.space_commands import ShipCommand
        self.assertEqual(ShipCommand.key, "+ship")

    def test_valid_switches_includes_rename(self):
        from parser.space_commands import ShipCommand
        self.assertIn("rename", ShipCommand.valid_switches)

    def test_valid_switches_preserves_full_set(self):
        """Every ship verb must remain reachable as a switch."""
        from parser.space_commands import ShipCommand
        for sw in ["status", "info", "list", "mine", "rename", "repair",
                   "mods", "install", "uninstall", "log", "quirks"]:
            self.assertIn(
                sw, ShipCommand.valid_switches,
                f"ship switch /{sw} was removed"
            )

    def test_umbrella_has_no_dead_aliases(self):
        """DROP 5b: the umbrella carries NO bare/shortcut aliases — the
        switch form is the only way in."""
        from parser.space_commands import ShipCommand
        self.assertEqual(
            ShipCommand.aliases, [],
            f"ShipCommand should have no aliases after DROP 5b; got "
            f"{ShipCommand.aliases!r}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. The pure-delegator siblings are DELETED (DROP 5b)
# ══════════════════════════════════════════════════════════════════════════════

class TestSiblingClassesDeleted(unittest.TestCase):
    """ShipsCommand/MyShipsCommand/ShipInfoCommand/ShipRepairCommand were
    pure delegators into +ship; DROP 5b deleted them entirely."""

    def test_sibling_classes_no_longer_exist(self):
        import parser.space_commands as sc
        for name in ("ShipsCommand", "MyShipsCommand",
                     "ShipInfoCommand", "ShipRepairCommand"):
            self.assertFalse(
                hasattr(sc, name),
                f"{name} should be deleted (DROP 5b)"
            )

    def test_standalone_ship_keys_unbound(self):
        """The old standalone keys/shortcuts no longer resolve at all."""
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        r = CommandRegistry()
        register_space_commands(r)
        for name in ["+ships", "+shipinfo", "+shiprepair", "+myships",
                     "+shipname", "shipname"]:
            self.assertIsNone(
                r.get(name),
                f"'{name}' should be unbound after DROP 5b but resolved to "
                f"{type(r.get(name)).__name__}"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 3. The bare ship shorthands are gone (no IC/OOC ambiguity)
# ══════════════════════════════════════════════════════════════════════════════

class TestBareFormsRetired(unittest.TestCase):
    """A1: ship-admin is OOC/query → `+`-prefixed. The bare forms
    (ship/ss/ships/shiplist/myships/ownedships/shipinfo/si/shiprepair/
    srepair) no longer resolve."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        r = CommandRegistry()
        register_space_commands(r)
        return r

    def test_bare_forms_unbound(self):
        r = self._build_registry()
        for name in ["ship", "ss", "shipstatus", "ships", "shiplist",
                     "myships", "ownedships", "shipinfo", "si",
                     "shiprepair", "srepair"]:
            self.assertIsNone(
                r.get(name),
                f"bare '{name}' should be retired (DROP 5b) but resolved to "
                f"{type(r.get(name)).__name__}"
            )

    def test_plus_ship_still_canonical(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("+ship"), ShipCommand)


# ══════════════════════════════════════════════════════════════════════════════
# 4. /rename switch dispatch (delegates to the unregistered impl)
# ══════════════════════════════════════════════════════════════════════════════

class TestRenameSwitch(unittest.TestCase):
    """/rename is a switch on ShipCommand that delegates to ShipNameCommand,
    which survives as a switch-impl only (not registered)."""

    def test_rename_in_valid_switches(self):
        from parser.space_commands import ShipCommand
        self.assertIn("rename", ShipCommand.valid_switches)

    def test_shipname_class_survives_as_impl(self):
        """/rename delegates to ShipNameCommand; the class must remain
        importable even though it is no longer registered."""
        from parser.space_commands import ShipNameCommand
        self.assertTrue(hasattr(ShipNameCommand, "execute"))

    def test_shipname_class_not_registered(self):
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        r = CommandRegistry()
        register_space_commands(r)
        self.assertIsNone(
            r.get("shipname"),
            "ShipNameCommand should not be registered after DROP 5b"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 5. The gunnery alias collision fix (unchanged from S57a)
# ══════════════════════════════════════════════════════════════════════════════

class TestGunneryAliasFix(unittest.TestCase):
    """`gunnery` used to be an alias on both BoardCommand AND GunnerCommand.
    S57a removed it from BoardCommand — `gunnery` means 'take the gunner
    seat'."""

    def test_gunnery_not_in_board_aliases(self):
        from parser.space_commands import BoardCommand
        self.assertNotIn(
            "gunnery", BoardCommand.aliases,
            "BoardCommand.aliases still contains 'gunnery'"
        )

    def test_gunnery_still_in_gunner_aliases(self):
        from parser.space_commands import GunnerCommand
        self.assertIn(
            "gunnery", GunnerCommand.aliases,
            "GunnerCommand.aliases missing 'gunnery'"
        )

    def test_bare_gunnery_routes_to_gunner(self):
        from parser.commands import CommandRegistry
        from parser.space_commands import (
            register_space_commands, GunnerCommand,
        )
        r = CommandRegistry()
        register_space_commands(r)
        self.assertIsInstance(r.get("gunnery"), GunnerCommand)


# ══════════════════════════════════════════════════════════════════════════════
# 6. +ship.md help file
# ══════════════════════════════════════════════════════════════════════════════

class TestShipHelpFile(unittest.TestCase):
    """Verify data/help/commands/+ship.md loads cleanly."""

    def _load_entry(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+ship"]
        self.assertEqual(
            len(matching), 1,
            "Expected exactly one +ship help entry"
        )
        return matching[0]

    def test_help_loads(self):
        e = self._load_entry()
        self.assertEqual(e.key, "+ship")
        self.assertTrue(e.title)
        self.assertTrue(e.summary)

    def test_help_has_substantial_body(self):
        e = self._load_entry()
        self.assertGreater(
            len(e.body), 5000,
            f"+ship body only {len(e.body)} chars; expected 5000+"
        )

    def test_help_has_examples(self):
        e = self._load_entry()
        self.assertGreater(len(e.examples), 10)
        for ex in e.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)

    def test_help_documents_rename_switch(self):
        e = self._load_entry()
        self.assertIn(
            "/rename", e.body,
            "+ship help does not document the /rename switch"
        )

    def test_help_cites_canonical_form(self):
        e = self._load_entry()
        canonical_count = sum(
            1 for ex in e.examples if ex["cmd"].startswith("+ship")
        )
        self.assertGreater(canonical_count, 8)

    def test_help_examples_are_all_canonical(self):
        """DROP 5b: no example should advertise a retired bare/shortcut
        form — every example uses the +ship switch syntax."""
        e = self._load_entry()
        for ex in e.examples:
            self.assertTrue(
                ex["cmd"].startswith("+ship"),
                f"+ship help example demonstrates a non-canonical form: "
                f"{ex['cmd']!r}"
            )

    def test_help_cross_references_ship_topic(self):
        e = self._load_entry()
        self.assertIn("ships", e.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Cross-module: all previously-shipped umbrellas still intact
# ══════════════════════════════════════════════════════════════════════════════

class TestAllUmbrellasStillShip(unittest.TestCase):
    """The 7 umbrellas from S54+S55+S56 plus +ship must still register."""

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
        # Match server/game_server.py order
        register_combat_commands(r)
        register_space_commands(r)
        register_crew_commands(r)
        register_mission_commands(r)
        register_bounty_commands(r)
        register_smuggling_commands(r)
        register_crafting_commands(r)
        register_narrative_commands(r)
        return r

    def test_all_umbrellas_resolve(self):
        from parser.combat_commands import CombatCommand
        from parser.mission_commands import MissionCommand
        from parser.smuggling_commands import SmuggleCommand
        from parser.bounty_commands import BountyCommand
        from parser.narrative_commands import QuestCommand
        from parser.crafting_commands import CraftingCommand
        from parser.crew_commands import CrewCommand
        from parser.space_commands import ShipCommand

        r = self._build_registry()

        self.assertIsInstance(r.get("+combat"), CombatCommand)
        self.assertIsInstance(r.get("+mission"), MissionCommand)
        self.assertIsInstance(r.get("+smuggle"), SmuggleCommand)
        self.assertIsInstance(r.get("+bounty"), BountyCommand)
        self.assertIsInstance(r.get("+quest"), QuestCommand)
        self.assertIsInstance(r.get("+craft"), CraftingCommand)
        self.assertIsInstance(r.get("+crew"), CrewCommand)
        self.assertIsInstance(r.get("+ship"), ShipCommand)


if __name__ == "__main__":
    unittest.main()
