# -*- coding: utf-8 -*-
"""
tests/test_command_syntax_drop5b_ship_family.py

command-syntax rework DROP 5b — ship-family consolidation into the
`+ship/<switch>` umbrella.

Per the ratified design (docs/design/command_syntax_rework_design_v2.md):
A1 = OOC/query/HUD commands are `+`-prefixed; switches are PRIMARY (the
MUSH idiom); CLEAN — redundant standalone forms are DELETED, no
back-compat aliases.

The ship-admin family used to expose five standalone commands that were
pure delegators (or, for rename, a separately-registered command) into
the `+ship` umbrella:

    ShipsCommand      +ships     -> +ship/list
    ShipInfoCommand   +shipinfo  -> +ship/info
    ShipRepairCommand +shiprepair-> +ship/repair
    MyShipsCommand    +myships   -> +ship/mine
    ShipNameCommand   shipname   -> +ship/rename

plus a swarm of bare/shortcut aliases (ship/ss/shipstatus/ships/shiplist/
myships/ownedships/shipinfo/si/srepair) and the `+shiprepair` alias on
the spacedock command.

DROP 5b deletes the four delegator classes, unregisters ShipNameCommand
(kept as the `+ship/rename` switch-impl only), strips the umbrella's
aliases, and drops the misleading `+shiprepair` spacedock alias. This
test pins the resulting clean state: the switch forms still reach the
exact same functions, and every retired standalone/bare form is gone.
"""
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def _space_registry():
    from parser.commands import CommandRegistry
    from parser.space_commands import register_space_commands
    r = CommandRegistry()
    register_space_commands(r)
    return r


class TestUmbrellaIsCanonical(unittest.TestCase):
    def test_plus_ship_resolves_to_umbrella(self):
        from parser.space_commands import ShipCommand
        r = _space_registry()
        self.assertIsInstance(r.get("+ship"), ShipCommand)

    def test_all_ship_switches_present(self):
        from parser.space_commands import ShipCommand
        for sw in ["status", "info", "list", "mine", "rename", "repair",
                   "mods", "install", "uninstall", "log", "quirks"]:
            self.assertIn(sw, ShipCommand.valid_switches)

    def test_umbrella_carries_no_aliases(self):
        from parser.space_commands import ShipCommand
        self.assertEqual(ShipCommand.aliases, [])


class TestDelegatorClassesDeleted(unittest.TestCase):
    def test_classes_gone(self):
        import parser.space_commands as sc
        for name in ("ShipsCommand", "ShipInfoCommand",
                     "ShipRepairCommand", "MyShipsCommand"):
            self.assertFalse(
                hasattr(sc, name), f"{name} should be deleted (DROP 5b)"
            )

    def test_shipname_class_kept_but_unregistered(self):
        # The /rename switch instantiates ShipNameCommand directly, so the
        # class must survive — but it must NOT be registered at a key.
        from parser.space_commands import ShipNameCommand
        self.assertTrue(hasattr(ShipNameCommand, "execute"))
        r = _space_registry()
        self.assertIsNone(r.get("shipname"))


class TestRetiredFormsUnbound(unittest.TestCase):
    RETIRED = [
        # bare
        "ship", "ss", "shipstatus", "ships", "shiplist",
        "myships", "ownedships", "shipinfo", "si",
        "shiprepair", "srepair", "shipname",
        # +-prefixed standalone twins
        "+ships", "+shipinfo", "+shiprepair", "+myships",
        "+shipname", "+shipstatus", "+ss",
    ]

    def test_all_retired_forms_resolve_to_nothing(self):
        r = _space_registry()
        for name in self.RETIRED:
            got = r.get(name)
            self.assertIsNone(
                got,
                f"retired form '{name}' should be unbound but resolved to "
                f"{type(got).__name__}"
            )

    def test_plus_shiprepair_not_a_spacedock_alias(self):
        """The misleading `+shiprepair` alias was dropped from the
        spacedock command; `+spacedock` is the dock, `+ship/repair` is the
        engineer roll. `+shiprepair` resolves to neither."""
        from parser.space_commands import SpacedockCommand
        self.assertNotIn("+shiprepair", SpacedockCommand.aliases)
        r = _space_registry()
        self.assertIsNone(r.get("+shiprepair"))

    def test_spacedock_still_intact(self):
        from parser.space_commands import SpacedockCommand
        r = _space_registry()
        self.assertIsInstance(r.get("+spacedock"), SpacedockCommand)
        # keeps its legitimate aliases
        for a in ["spacedock", "+yard", "+repairship"]:
            self.assertIsInstance(r.get(a), SpacedockCommand)


class TestSwitchDispatchReachesFunctions(unittest.TestCase):
    """The umbrella's execute() routes each switch to the same private
    handler the deleted siblings used to delegate to."""

    def _ctx(self, switches, args=""):
        class _Sess:
            def __init__(self):
                self.character = {"id": 1, "name": "Tester"}
                self.lines = []

            async def send_line(self, line):
                self.lines.append(line)

        class _Ctx:
            pass

        c = _Ctx()
        c.session = _Sess()
        c.switches = list(switches)
        c.args = args
        c.db = None
        return c

    def test_rename_switch_delegates_to_shipname_impl(self):
        """`+ship/rename` with no args hits ShipNameCommand's usage branch
        (proving the umbrella delegates to the surviving impl)."""
        import asyncio
        from parser.space_commands import ShipCommand
        ctx = self._ctx(["rename"], args="")
        asyncio.run(ShipCommand().execute(ctx))
        joined = "\n".join(ctx.session.lines).lower()
        self.assertIn("+ship/rename", joined)


class TestBaselineRatchet(unittest.TestCase):
    """The convention baseline must not list any ship-family collision
    after DROP 5b (they were all removed, none added)."""

    def test_no_ship_family_collisions_in_baseline(self):
        import json
        baseline_path = Path(_PROJECT_ROOT) / "tests" / "data" / \
            "command_convention_baseline.json"
        data = json.loads(baseline_path.read_text(encoding="utf-8"))
        collisions = set(data.get("collisions", []))
        ship_sigs = {
            "alias:+myships", "alias:+shipinfo", "alias:+shipname",
            "alias:+shiprepair", "alias:+ships", "alias:myships",
            "alias:ownedships", "alias:shipinfo", "alias:shiplist",
            "alias:shiprepair", "alias:ships", "alias:si", "alias:srepair",
        }
        leftover = ship_sigs & collisions
        self.assertEqual(
            leftover, set(),
            f"ship-family collisions still in baseline: {sorted(leftover)}"
        )


if __name__ == "__main__":
    unittest.main()
