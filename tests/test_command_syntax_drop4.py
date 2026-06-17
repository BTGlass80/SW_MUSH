# -*- coding: utf-8 -*-
"""
tests/test_command_syntax_drop4.py — command-syntax rework Drop 4

DROP 4 = the combat / crew / mission / espionage umbrella **dead-alias
cleanup** (same zero-behaviour type-1 pattern as Drop 3's service umbrellas,
see command_syntax_rework_design_v2.md §"Phased build plan").

Each of the +combat / +crew / +mission / +spy umbrellas re-declared a set of
per-verb aliases that a STANDALONE command in the same module already owned
(the standalone registers later, so the registry's last-wins binding made the
umbrella's copy DEAD — it never resolved to the umbrella). Deleting those
aliases is a pure zero-behaviour cleanup: every removed alias still resolves
through the full registry to the EXACT same handler.

This drop edits ONLY the `.aliases` lists. The per-module
`_*_ALIAS_TO_SWITCH` / `_*_SWITCH_IMPL` dispatch tables are LEFT INTACT — they
drive the `+cmd/<switch>` (and arg-keyed `+spy <verb>`) forms and are exercised
by the S54/S55/S56/S58 dispatch tests.

The genuine cross-command key/alias CONFLICTS (key:accept, key:order,
key:investigate, alias:retreat, alias:listen) are NOT touched here — they need
real decisions / switch-ification and are deferred to a later type-3 drop.
"""
import json
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# The aliases this drop removes from each umbrella, mapped to the standalone
# command key each still resolves to (verified against the live registry).
_REMOVED = {
    "+combat": {
        "att": "attack", "kill": "attack", "shoot": "attack", "hit": "attack",
        "cs": "combat", "fdodge": "fulldodge", "fparry": "fullparry",
        "soak": "+soak", "run": "flee", "distance": "range", "hide": "cover",
        "fp": "forcepoint", "combatpose": "cpose", "duel": "challenge",
        "refuse": "decline",
    },
    "+crew": {
        "recruiting": "hire", "hireboard": "hire", "roster": "+roster",
        "firecrew": "dismiss", "ord": "order",
    },
    "+mission": {
        "missions": "+missions", "mb": "+missions", "jobs": "+missions",
        "myjob": "mission", "activemission": "mission", "takejob": "accept",
        "finishjob": "complete", "turnin": "complete",
        "dropmission": "abandon", "quitjob": "abandon",
    },
    "+spy": {
        "size": "assess", "search": "investigate", "inspect": "investigate",
        "intel": "+intel", "wiretap": "intercept", "comtap": "intercept",
    },
}


def _umbrella_aliases():
    from parser.combat_commands import CombatCommand
    from parser.crew_commands import CrewCommand
    from parser.mission_commands import MissionCommand
    from parser.espionage_commands import SpyCommand
    return {
        "+combat": set(CombatCommand.aliases),
        "+crew": set(CrewCommand.aliases),
        "+mission": set(MissionCommand.aliases),
        "+spy": set(SpyCommand.aliases),
    }


class TestDeadAliasesRemoved(unittest.TestCase):
    """The dead duplicates are gone from every umbrella's alias list."""

    def test_no_umbrella_still_declares_a_removed_alias(self):
        live = _umbrella_aliases()
        for umbrella, removed in _REMOVED.items():
            still = set(removed) & live[umbrella]
            self.assertFalse(
                still, f"{umbrella} still declares removed aliases: {still}")


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
                    f"{alias!r} unexpectedly resolves to the umbrella",
                )


class TestDispatchMapsIntact(unittest.TestCase):
    """The per-module switch dispatch tables were NOT touched."""

    def test_combat_alias_to_switch_intact(self):
        from parser.combat_commands import _ALIAS_TO_SWITCH
        for a in ("att", "kill", "shoot", "hit", "cs", "soak", "hide", "fp"):
            self.assertIn(a, _ALIAS_TO_SWITCH)

    def test_crew_alias_to_switch_intact(self):
        from parser.crew_commands import _CREW_ALIAS_TO_SWITCH
        for a in ("recruiting", "hireboard", "firecrew", "ord"):
            self.assertIn(a, _CREW_ALIAS_TO_SWITCH)

    def test_mission_alias_to_switch_intact(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        for a in ("missions", "mb", "jobs", "takejob", "turnin", "quitjob"):
            self.assertIn(a, _MISSION_ALIAS_TO_SWITCH)

    def test_spy_alias_to_switch_intact(self):
        from parser.espionage_commands import _SPY_ALIAS_TO_SWITCH
        for a in ("size", "search", "inspect", "intel", "wiretap", "comtap"):
            self.assertIn(a, _SPY_ALIAS_TO_SWITCH)


class TestBaselineRatchetShrank(unittest.TestCase):
    """The convention baseline dropped the 36 cleaned collisions and added
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
                self.assertNotIn(
                    f"alias:{alias}", baseline,
                    f"alias:{alias} should have cleared from the baseline")

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
