# -*- coding: utf-8 -*-
"""
Command-syntax rework — Drop 7 (type-3 genuine-conflict resolution).

Ratified plan: docs/design/command_syntax_rework_design_v2.md §"Phased build
plan". Drops 0-6 drove the register()-collision baseline from 133 down to 9
remaining "type-3" conflicts — names that two genuinely-different commands both
wanted. Drop 7 resolves all nine so the convention-invariant baseline reaches
ZERO (CLEAN — no back-compat aliases, since nobody is playing yet).

The nine baseline collisions and their resolutions:

  key:accept       AcceptMissionCommand keeps bare `accept` (it smart-dispatches
                   a PC challenge to the combat AcceptCommand). Combat's
                   AcceptCommand is no longer registered standalone — it lives
                   on as the +combat/accept switch handler.
  alias:accept     `accept` umbrella aliases on +combat and +mission DELETED
                   (dispatch via the switch maps, not a dead top-level alias).
  key:investigate  anomaly InvestigateCommand keeps bare `investigate <id>`.
                   The espionage room-search is canonicalized to `search`
                   (alias `inspect`); still reachable via +spy investigate.
  key:order        crew OrderCommand keeps bare `order`. The space commander
                   OrderCommand is reachable via +bridge/order only (standalone
                   registration dropped).
  alias:order      `order` umbrella alias on +crew DELETED (dispatch via switch).
  alias:listen     `listen` -> EavesdropCommand (listen to an adjacent room),
                   the universal meaning. Deleted from +spy and the trial-only
                   examine command (which it had been mis-winning).
  alias:p          `p` -> PageCommand (page, the universal MU* convention).
                   Deleted from the +party umbrella.
  alias:retreat    `retreat` -> FleeCommand (combat disengage). Deleted from
                   +combat (dup of the standalone) and from wow_counsel's OOC
                   leave-of-absence command (which keeps its `+retreat` key).
  alias:train      `train` -> cp_commands.TrainCommand (spend CP). Deleted from
                   the Training-Grounds command (which keeps `training`).

Reuses the single authoritative full-registry builder so it sees the exact
command set the live server dispatches.
"""
import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.test_t321_admin_command_access_invariant import (  # noqa: E402
    _build_full_registry,
)

BASELINE_PATH = os.path.join(
    PROJECT_ROOT, "tests", "data", "command_convention_baseline.json"
)


@pytest.fixture(scope="module")
def registry():
    return _build_full_registry()


# ── The headline: the collision baseline has reached zero ──────────────────
def test_collision_baseline_is_zero():
    """Drop 7 is the terminal canonicalization drop — the frozen baseline must
    record zero key/alias collisions (and zero run-on stems)."""
    with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    assert baseline["collisions"] == [], (
        f"baseline still has collisions: {baseline['collisions']}"
    )
    assert baseline["run_on_keys"] == []


def test_live_registry_has_no_collisions(registry):
    """The live registry introduces nothing beyond the (now-empty) baseline."""
    assert registry.collision_signatures == [], (
        f"live collisions: {registry.collision_signatures}"
    )


# ── Each contested name resolves to its canonical owner ────────────────────
# (typed-name -> module.ClassName of the resolved command)
CANONICAL_RESOLUTIONS = {
    "accept":      "parser.mission_commands.AcceptMissionCommand",
    "investigate": "parser.anomaly_commands.InvestigateCommand",
    "order":       "parser.crew_commands.OrderCommand",
    "listen":      "parser.espionage_commands.EavesdropCommand",
    "p":           "parser.mux_commands.PageCommand",
    "retreat":     "parser.combat_commands.FleeCommand",
    "train":       "parser.cp_commands.TrainCommand",
    # The espionage room-search's new clean home + alias.
    "search":      "parser.espionage_commands.InvestigateCommand",
    "inspect":     "parser.espionage_commands.InvestigateCommand",
    "eavesdrop":   "parser.espionage_commands.EavesdropCommand",
}


@pytest.mark.parametrize("name,expected", sorted(CANONICAL_RESOLUTIONS.items()))
def test_contested_name_resolves_to_canonical_owner(registry, name, expected):
    cmd = registry.get(name)
    assert cmd is not None, f"{name!r} no longer resolves to any command"
    got = f"{type(cmd).__module__}.{type(cmd).__name__}"
    assert got == expected, f"{name!r} -> {got}, expected {expected}"


# ── The losing claimants no longer claim the contested names ───────────────
def test_combat_umbrella_dropped_accept_and_retreat_aliases():
    from parser.combat_commands import CombatCommand
    assert "accept" not in CombatCommand.aliases
    assert "retreat" not in CombatCommand.aliases


def test_mission_umbrella_dropped_accept_alias():
    from parser.mission_commands import MissionCommand
    assert "accept" not in MissionCommand.aliases


def test_crew_umbrella_dropped_order_alias():
    from parser.crew_commands import CrewCommand
    assert "order" not in CrewCommand.aliases


def test_spy_umbrella_dropped_listen_alias():
    from parser.espionage_commands import SpyCommand
    assert "listen" not in SpyCommand.aliases


def test_trial_examine_dropped_listen_alias():
    from parser.village_trial_commands import ExamineCommand
    assert "listen" not in ExamineCommand.aliases


def test_party_umbrella_dropped_p_alias():
    from parser.party_commands import PartyInviteCommand
    assert "p" not in PartyInviteCommand.aliases
    assert "party" in PartyInviteCommand.aliases  # the long form survives


def test_wow_retreat_dropped_bare_retreat_alias():
    from parser.wow_counsel_retreat import RetreatCommand
    assert "retreat" not in RetreatCommand.aliases
    assert RetreatCommand.key == "+retreat"  # OOC A1 key survives


def test_training_grounds_dropped_train_alias():
    from parser.tutorial_commands import TrainingCommand
    assert "train" not in TrainingCommand.aliases
    assert "+training" in TrainingCommand.aliases


def test_espionage_search_command_recanonicalized():
    """The espionage room-search command moved off the contested `investigate`
    key onto `search`/`inspect`."""
    from parser.espionage_commands import InvestigateCommand
    assert InvestigateCommand.key == "search"
    assert "inspect" in InvestigateCommand.aliases
    assert "investigate" not in InvestigateCommand.aliases


# ── The moved/de-registered commands stay reachable via their umbrellas ────
def test_combat_accept_switch_still_dispatches_acceptcommand():
    """AcceptCommand is no longer a standalone key, but +combat/accept must
    still route to it."""
    from parser.combat_commands import (
        _SWITCH_IMPL, _init_switch_impl, AcceptCommand,
    )
    _init_switch_impl()  # idempotent; ensures the map is populated
    assert _SWITCH_IMPL.get("accept") is AcceptCommand


def test_accept_command_not_registered_standalone(registry):
    """The combat AcceptCommand must not own a top-level key anymore (that was
    the key:accept collision)."""
    from parser.combat_commands import AcceptCommand
    assert not any(
        isinstance(c, AcceptCommand) for c in registry.all_commands
    ), "combat AcceptCommand is still registered as a standalone command"


def test_space_order_command_reachable_via_bridge():
    """The space commander OrderCommand is no longer standalone, but
    +bridge/order must still dispatch it."""
    from parser.space_commands import (
        _init_bridge_switch_impl, _BRIDGE_SWITCH_IMPL, OrderCommand,
    )
    _init_bridge_switch_impl()
    impl = _BRIDGE_SWITCH_IMPL.get("order")
    assert impl is not None and isinstance(impl, OrderCommand)


def test_space_order_not_registered_standalone(registry):
    from parser.space_commands import OrderCommand as SpaceOrderCommand
    assert not any(
        isinstance(c, SpaceOrderCommand) for c in registry.all_commands
    ), "space OrderCommand is still registered as a standalone command"
