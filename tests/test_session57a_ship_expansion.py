# -*- coding: utf-8 -*-
"""
tests/test_session57a_ship_expansion.py -- Session 57a feature tests

S57a is the first half of the space rename sweep. Rather than
creating a new umbrella class, S57a EXPANDS the existing
`ShipCommand` umbrella (which was already partially umbrellafied
pre-sweep with valid_switches = ["status", "info", "list", "mine",
"repair", "mods", "install", "uninstall", "log", "quirks"]).

S57a changes:
  1. ShipCommand.aliases expanded from 5 → 19 to absorb sibling
     class aliases (ShipsCommand, MyShipsCommand, ShipInfoCommand,
     ShipRepairCommand, ShipNameCommand)
  2. ShipCommand.valid_switches gains `/rename` (absorbs
     ShipNameCommand functionality; delegates via class call)
  3. Help file +ship.md authored with dense per-umbrella coverage
  4. BoardCommand.aliases pruned — `gunnery` removed (it was a
     collision with GunnerCommand.aliases = ["gunnery"])

Sibling classes (ShipsCommand, MyShipsCommand, ShipInfoCommand,
ShipRepairCommand, ShipNameCommand) remain registered at their
bare keys for backward compatibility.

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
# 1. ShipCommand umbrella expansion
# ══════════════════════════════════════════════════════════════════════════════

class TestShipUmbrellaExpansion(unittest.TestCase):
    """Verify +ship now covers what ShipsCommand/MyShipsCommand/etc. did."""

    def test_ship_command_class_exists(self):
        from parser.space_commands import ShipCommand
        self.assertTrue(hasattr(ShipCommand, "execute"))

    def test_ship_command_key(self):
        from parser.space_commands import ShipCommand
        self.assertEqual(ShipCommand.key, "+ship")

    def test_valid_switches_includes_rename(self):
        """S57a added /rename to the ShipCommand umbrella."""
        from parser.space_commands import ShipCommand
        self.assertIn("rename", ShipCommand.valid_switches)

    def test_valid_switches_preserves_legacy(self):
        """Pre-S57a switches must still be valid."""
        from parser.space_commands import ShipCommand
        for sw in ["status", "info", "list", "mine", "repair",
                   "mods", "install", "uninstall", "log", "quirks"]:
            self.assertIn(
                sw, ShipCommand.valid_switches,
                f"Pre-S57a switch /{sw} was removed"
            )

    def test_aliases_include_ships_catalog(self):
        """Aliases from ShipsCommand absorbed."""
        from parser.space_commands import ShipCommand
        for alias in ["ships", "shiplist"]:
            self.assertIn(
                alias, ShipCommand.aliases,
                f"ShipCommand missing absorbed alias: {alias}"
            )

    def test_aliases_include_myships(self):
        """Aliases from MyShipsCommand absorbed."""
        from parser.space_commands import ShipCommand
        for alias in ["myships", "ownedships"]:
            self.assertIn(
                alias, ShipCommand.aliases,
                f"ShipCommand missing absorbed alias: {alias}"
            )

    def test_aliases_include_shipinfo(self):
        """Aliases from ShipInfoCommand absorbed."""
        from parser.space_commands import ShipCommand
        for alias in ["shipinfo", "si"]:
            self.assertIn(
                alias, ShipCommand.aliases,
                f"ShipCommand missing absorbed alias: {alias}"
            )

    def test_aliases_include_shiprepair(self):
        """Aliases from ShipRepairCommand absorbed."""
        from parser.space_commands import ShipCommand
        for alias in ["shiprepair", "srepair"]:
            self.assertIn(
                alias, ShipCommand.aliases,
                f"ShipCommand missing absorbed alias: {alias}"
            )

    def test_aliases_include_shipname(self):
        """Aliases from ShipNameCommand absorbed (for /rename switch)."""
        from parser.space_commands import ShipCommand
        self.assertIn(
            "shipname", ShipCommand.aliases,
            "ShipCommand missing absorbed alias: shipname"
        )

    def test_aliases_preserve_legacy_ship_status(self):
        """Pre-S57a aliases must still be present."""
        from parser.space_commands import ShipCommand
        for alias in ["ship", "shipstatus", "ss"]:
            self.assertIn(
                alias, ShipCommand.aliases,
                f"Pre-S57a ShipCommand alias '{alias}' was removed"
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Sibling classes still exist and register (backward compat)
# ══════════════════════════════════════════════════════════════════════════════

class TestSiblingClassesRemainRegistered(unittest.TestCase):
    """The S54-S56 pattern: per-verb classes keep their bare keys as a
    fallback even after the umbrella absorbs their aliases. Same here."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        r = CommandRegistry()
        register_space_commands(r)
        return r

    def test_plus_ships_still_reaches_shipscommand(self):
        from parser.space_commands import ShipsCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("+ships"), ShipsCommand)

    def test_plus_myships_still_reaches_myshipscommand(self):
        from parser.space_commands import MyShipsCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("+myships"), MyShipsCommand)

    def test_plus_shipinfo_still_reaches_shipinfocommand(self):
        from parser.space_commands import ShipInfoCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("+shipinfo"), ShipInfoCommand)

    def test_plus_shiprepair_still_reaches_shiprepaircommand(self):
        from parser.space_commands import ShipRepairCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("+shiprepair"), ShipRepairCommand)

    def test_bare_shipname_still_reaches_shipnamecommand(self):
        """ShipNameCommand.key = 'shipname' (bare). Bare `shipname` must
        still reach the per-verb class directly — umbrella-absorbed
        aliases do NOT overwrite the per-verb class's primary key."""
        from parser.space_commands import ShipNameCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("shipname"), ShipNameCommand)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Umbrella owns the common bare aliases (routes via umbrella)
# ══════════════════════════════════════════════════════════════════════════════

class TestUmbrellaOwnsBareAliases(unittest.TestCase):
    """When a bare alias is both an alias on the umbrella AND
    not a key on a per-verb class, the umbrella wins."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.space_commands import register_space_commands
        r = CommandRegistry()
        register_space_commands(r)
        return r

    def test_bare_ships_routes_to_umbrella(self):
        """'ships' is an alias on ShipCommand; ShipsCommand.key is '+ships'
        (with plus). So bare 'ships' goes to the umbrella."""
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("ships"), ShipCommand)

    def test_bare_myships_routes_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("myships"), ShipCommand)

    def test_bare_shipinfo_routes_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("shipinfo"), ShipCommand)

    def test_bare_shiprepair_routes_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("shiprepair"), ShipCommand)

    def test_bare_ship_routes_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("ship"), ShipCommand)

    def test_bare_ss_routes_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("ss"), ShipCommand)


# ══════════════════════════════════════════════════════════════════════════════
# 4. /rename switch dispatch
# ══════════════════════════════════════════════════════════════════════════════

class TestRenameSwitch(unittest.TestCase):
    """/rename is a new switch on ShipCommand that delegates to
    ShipNameCommand — same pattern as the S54–S56 umbrellas use
    for every switch."""

    def test_rename_in_valid_switches(self):
        from parser.space_commands import ShipCommand
        self.assertIn("rename", ShipCommand.valid_switches)

    def test_shipname_class_still_exists(self):
        """/rename delegates to ShipNameCommand; the class must remain."""
        from parser.space_commands import ShipNameCommand
        self.assertTrue(hasattr(ShipNameCommand, "execute"))
        self.assertEqual(ShipNameCommand.key, "shipname")


# ══════════════════════════════════════════════════════════════════════════════
# 5. The gunnery alias collision fix
# ══════════════════════════════════════════════════════════════════════════════

class TestGunneryAliasFix(unittest.TestCase):
    """Pre-S57a: `gunnery` was an alias on both BoardCommand AND
    GunnerCommand. Registration order decided. S57a removes it
    from BoardCommand — `gunnery` unambiguously means 'take the
    gunner seat'."""

    def test_gunnery_not_in_board_aliases(self):
        from parser.space_commands import BoardCommand
        self.assertNotIn(
            "gunnery", BoardCommand.aliases,
            "BoardCommand.aliases still contains 'gunnery' (S57a should remove it)"
        )

    def test_gunnery_still_in_gunner_aliases(self):
        from parser.space_commands import GunnerCommand
        self.assertIn(
            "gunnery", GunnerCommand.aliases,
            "GunnerCommand.aliases missing 'gunnery' (should remain)"
        )

    def test_bare_gunnery_routes_to_gunner(self):
        """With the collision fixed, `gunnery` must route to
        GunnerCommand (take the gunner seat)."""
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
        """The new /rename switch must appear in the help."""
        e = self._load_entry()
        self.assertIn(
            "/rename", e.body,
            "+ship help does not document the new /rename switch"
        )

    def test_help_cites_canonical_form(self):
        e = self._load_entry()
        canonical_count = sum(
            1 for ex in e.examples if ex["cmd"].startswith("+ship")
        )
        self.assertGreater(canonical_count, 8)

    def test_help_cross_references_ship_topic(self):
        e = self._load_entry()
        self.assertIn("ships", e.see_also)


# ══════════════════════════════════════════════════════════════════════════════
# 7. Cross-module: all previously-shipped umbrellas still intact
# ══════════════════════════════════════════════════════════════════════════════

class TestAllUmbrellasStillShip(unittest.TestCase):
    """The 7 umbrellas from S54+S55+S56 must still register cleanly.
    S57a doesn't add a new umbrella — it expands an existing one —
    but nothing should have regressed."""

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
        """Every +verb umbrella key must resolve to its umbrella class."""
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
