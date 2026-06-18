# -*- coding: utf-8 -*-
"""
tests/test_command_syntax_drop5_stations.py — command-syntax rework Drop 5a

DROP 5a = the +pilot / +gunner / +sensors / +bridge station-umbrella
**dead-alias cleanup** (same zero-behaviour type-1 pattern as Drop 3's service
umbrellas and Drop 4's combat/crew/mission/espionage umbrellas — see
command_syntax_rework_design_v2.md §"Phased build plan").

Each of the four space station umbrellas (registered FIRST per
register_space_commands) re-declared a set of per-verb aliases that a STANDALONE
maneuver/action command in the same module already owned. Because the standalone
registers LATER, the registry's last-wins binding made the umbrella's copy DEAD
— it never resolved to the umbrella. Deleting those aliases is a pure
zero-behaviour cleanup: every removed alias still resolves through the full
registry to the EXACT same handler.

This drop edits ONLY the `.aliases` lists. The per-umbrella
`_*_ALIAS_TO_SWITCH` / `_*_SWITCH_IMPL` dispatch tables are LEFT INTACT — they
drive the canonical `+pilot/<switch>` / `+gunner/<switch>` / `+sensors/<switch>`
/ `+bridge/<switch>` forms.

The bare verbs matching a standalone's KEY (evade/jink/.../course, gunner/fire/
lockon, sensors/scan/deepscan, commander/hail/.../coordinate) are KEPT, for
parity with the +combat umbrella's kept verbs (Drop 4) — they are NOT tracked
collisions (a primary-key registered after an alias is not flagged) and removing
them would not shrink the baseline.

NOT touched: the genuine cross-command key:order conflict (space OrderCommand vs
crew OrderCommand) is deferred to the type-3 drop — so alias:order REMAINS in the
baseline (the +bridge "order" alias is gone, but crew's "order" alias is still
shadowed by a sibling key). alias:orders cleared (only +bridge caused it).
"""
import json
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# Each alias this drop removes from an umbrella, mapped to the standalone
# command KEY it still resolves to (verified against the live registry).
_REMOVED = {
    "+pilot": {
        "evasive": "evade", "broll": "barrelroll", "immelmann": "loop",
        "sideslip": "slip", "getbehind": "tail", "shake": "outmaneuver",
        "approach": "close", "breakaway": "fleeship",
        "navigate": "course", "setcourse": "course",
    },
    "+gunner": {
        "gunnery": "gunner", "lock": "lockon", "targetlock": "lockon",
    },
    "+sensors": {
        "sensor": "sensors",
    },
    "+bridge": {
        "captain": "commander", "command": "commander",
        "comm": "comms", "radio": "comms",
        "coord": "coordinate", "damagecontrol": "damcon", "repair": "damcon",
        "pwr": "power", "transp": "transponder", "unstation": "vacate",
        "breakfree": "resist",
        # `order` still resolves to the crew OrderCommand (key="order"); the
        # transient `orders` bridge dup is unbound after DROP 7 (terminal state).
        "order": "order",
    },
}

# The bare verbs that MUST remain on each umbrella (match a standalone key;
# unflagged; kept for parity with +combat per Drop 4).
_KEPT = {
    "+pilot": {"pilot", "evade", "jink", "barrelroll", "loop", "slip",
               "tail", "outmaneuver", "close", "fleeship", "course"},
    "+gunner": {"gunner", "fire", "lockon"},
    "+sensors": {"sensors", "scan", "deepscan"},
    "+bridge": {"commander", "hail", "comms", "shields", "power",
                "transponder", "resist", "damcon", "vacate", "assist",
                "coordinate"},
}

# alias:orders cleared; alias:order REMAINS (entangled with the deferred
# key:order space-vs-crew type-3 conflict).
_STILL_IN_BASELINE = {"alias:order"}


def _umbrella_aliases():
    from parser.space_commands import (
        PilotStationCommand, GunnerStationCommand,
        SensorsStationCommand, BridgeCommand,
    )
    return {
        "+pilot": set(PilotStationCommand.aliases),
        "+gunner": set(GunnerStationCommand.aliases),
        "+sensors": set(SensorsStationCommand.aliases),
        "+bridge": set(BridgeCommand.aliases),
    }


class TestDeadAliasesRemoved(unittest.TestCase):
    """The dead duplicates are gone from every station umbrella's alias list."""

    def test_no_umbrella_still_declares_a_removed_alias(self):
        live = _umbrella_aliases()
        for umbrella, removed in _REMOVED.items():
            still = set(removed) & live[umbrella]
            self.assertFalse(
                still, f"{umbrella} still declares removed aliases: {still}")

    def test_kept_verbs_still_present(self):
        live = _umbrella_aliases()
        for umbrella, kept in _KEPT.items():
            self.assertEqual(
                live[umbrella], kept,
                f"{umbrella} alias list is not exactly the kept set")


class TestZeroBehaviourResolution(unittest.TestCase):
    """Every removed alias still resolves to its original standalone handler."""

    def test_removed_aliases_resolve_to_same_owner(self):
        from tests.test_t321_admin_command_access_invariant import (
            _build_full_registry,
        )
        reg = _build_full_registry()
        for umbrella, removed in _REMOVED.items():
            for alias, owner_key in removed.items():
                cmd = reg.get(alias)
                self.assertIsNotNone(cmd, f"{alias!r} no longer resolves")
                self.assertEqual(
                    cmd.key, owner_key,
                    f"{alias!r} resolves to {cmd.key!r}, expected {owner_key!r}",
                )
                self.assertNotEqual(
                    cmd.key, umbrella,
                    f"{alias!r} unexpectedly resolves to the umbrella")

    def test_order_aliases_resolve_to_crew_order_command(self):
        # Precise zero-behaviour check: bare `order` routes to the CREW
        # OrderCommand (unchanged — crew_commands wasn't touched). The `orders`
        # alias is unbound after DROP 7 (it was a transient bridge dup).
        from tests.test_t321_admin_command_access_invariant import (
            _build_full_registry,
        )
        reg = _build_full_registry()
        for alias in ("order",):
            cmd = reg.get(alias)
            self.assertIsNotNone(cmd)
            self.assertEqual(type(cmd).__module__, "parser.crew_commands")


class TestDispatchMapsIntact(unittest.TestCase):
    """The per-umbrella switch dispatch tables were NOT touched, so the
    canonical +cmd/<switch> forms still reach each standalone handler."""

    def test_pilot_alias_to_switch_intact(self):
        from parser.space_commands import _PILOT_ALIAS_TO_SWITCH
        for a in ("evasive", "broll", "immelmann", "sideslip", "getbehind",
                  "shake", "approach", "breakaway", "navigate", "setcourse"):
            self.assertIn(a, _PILOT_ALIAS_TO_SWITCH)

    def test_gunner_alias_to_switch_intact(self):
        from parser.space_commands import _GUNNER_ALIAS_TO_SWITCH
        for a in ("gunnery", "lock", "targetlock"):
            self.assertIn(a, _GUNNER_ALIAS_TO_SWITCH)

    def test_sensors_alias_to_switch_intact(self):
        from parser.space_commands import _SENSORS_ALIAS_TO_SWITCH
        self.assertIn("sensor", _SENSORS_ALIAS_TO_SWITCH)

    def test_bridge_alias_to_switch_intact(self):
        from parser.space_commands import _BRIDGE_ALIAS_TO_SWITCH
        for a in ("command", "captain", "comm", "radio", "pwr", "transp",
                  "breakfree", "damagecontrol", "repair", "unstation",
                  "coord", "order", "orders"):
            self.assertIn(a, _BRIDGE_ALIAS_TO_SWITCH)

    def test_switch_impl_tables_reach_standalones(self):
        from parser.space_commands import (
            _PILOT_SWITCH_IMPL, _GUNNER_SWITCH_IMPL,
            _SENSORS_SWITCH_IMPL, _BRIDGE_SWITCH_IMPL,
        )
        self.assertEqual(type(_PILOT_SWITCH_IMPL["evade"]).__name__,
                         "EvadeCommand")
        self.assertEqual(type(_PILOT_SWITCH_IMPL["course"]).__name__,
                         "CourseCommand")
        self.assertEqual(type(_GUNNER_SWITCH_IMPL["lockon"]).__name__,
                         "LockOnCommand")
        self.assertEqual(type(_SENSORS_SWITCH_IMPL["scan"]).__name__,
                         "ScanCommand")
        self.assertEqual(type(_BRIDGE_SWITCH_IMPL["damcon"]).__name__,
                         "DamConCommand")
        self.assertEqual(type(_BRIDGE_SWITCH_IMPL["order"]).__name__,
                         "OrderCommand")


class TestBaselineRatchetShrank(unittest.TestCase):
    """The convention baseline dropped the 26 cleaned collisions and added
    nothing — the live registry introduces nothing beyond the baseline."""

    def _baseline(self):
        path = os.path.join(
            _PROJECT_ROOT, "tests", "data",
            "command_convention_baseline.json")
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)

    def test_cleaned_collisions_absent_from_baseline(self):
        baseline = set(self._baseline()["collisions"])
        for umbrella, removed in _REMOVED.items():
            for alias in removed:
                sig = f"alias:{alias}"
                if sig in _STILL_IN_BASELINE:
                    continue
                self.assertNotIn(
                    sig, baseline,
                    f"{sig} should have cleared from the baseline")

    def test_orders_cleared_order_remains(self):
        baseline = set(self._baseline()["collisions"])
        self.assertNotIn("alias:orders", baseline)
        # DROP 7 (terminal baseline ZERO) also cleared `alias:order`; the final
        # collision-free baseline is asserted authoritatively by
        # test_command_syntax_drop7.py.

    def test_live_registry_within_baseline(self):
        from tests.test_t321_admin_command_access_invariant import (
            _build_full_registry,
        )
        baseline = set(self._baseline()["collisions"])
        live = set(_build_full_registry().collision_signatures)
        self.assertTrue(
            live <= baseline,
            f"live registry introduced NEW collisions: {live - baseline}")


if __name__ == "__main__":
    unittest.main()
