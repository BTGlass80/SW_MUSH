# -*- coding: utf-8 -*-
"""
Command-syntax rework — Drop 2 (run-on smash -> verb/switch families).

Ratified plan: docs/design/command_syntax_rework_design_v2.md §"Phased build
plan" Drop 2. The ~9 run-on "smash" stems are DELETED in favour of the canonical
`+verb/<switch>` umbrella form (CLEAN — no back-compat, since nobody is playing
yet). The per-verb command classes survive ONLY as switch implementations
dispatched by their umbrella; they are no longer registered standalone.

Deleted run-on key            Canonical replacement
  bountyclaim            ->     +bounty/claim
  bountytrack            ->     +bounty/track
  bountycollect          ->     +bounty/collect
  questaccept            ->     +quest/accept
  questcomplete          ->     +quest/complete
  questabandon           ->     +quest/abandon
  smugdeliver            ->     +smuggle/deliver
  buyresources           ->     +craft/buyresources
  spacerquest            ->     +spacerquest      (promoted to the + form;
                                                   not a switch family — single
                                                   command with arg subcommands)

This test reuses the single authoritative full-registry builder so it sees the
exact command set the live server dispatches.
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

# The 9 run-on smashes Drop 2 deletes. After deletion NONE may resolve as a
# key, alias, OR prefix match (the whole point: typing `bountyclaim` is now a
# "command not found", not a silent route into the umbrella).
DELETED_RUN_ONS = [
    "bountyclaim", "bountytrack", "bountycollect",
    "questaccept", "questcomplete", "questabandon",
    "smugdeliver", "buyresources", "spacerquest",
]

# Canonical umbrella + switch for each deleted bounty/quest/smuggle/craft verb.
# (form_string, umbrella_key, switch_name)
SWITCH_CANONICALS = [
    ("+bounty/claim", "+bounty", "claim"),
    ("+bounty/track", "+bounty", "track"),
    ("+bounty/collect", "+bounty", "collect"),
    ("+quest/accept", "+quest", "accept"),
    ("+quest/complete", "+quest", "complete"),
    ("+quest/abandon", "+quest", "abandon"),
    ("+smuggle/deliver", "+smuggle", "deliver"),
    ("+craft/buyresources", "+craft", "buyresources"),
]


@pytest.fixture(scope="module")
def registry():
    return _build_full_registry()


def test_run_on_smashes_are_gone(registry):
    """None of the deleted run-on smashes resolve as a key, alias, or prefix
    match — typing one is a clean 'command not found'."""
    for smash in DELETED_RUN_ONS:
        assert not registry.has_exact(smash), (
            f"{smash!r} is still a registered key/alias — Drop 2 deletes it"
        )
        assert registry.get(smash) is None, (
            f"{smash!r} still resolves (key/alias/prefix) — Drop 2 deletes it"
        )


def test_run_on_baseline_ratchet_is_empty():
    """The Drop-0 run-on regression baseline must have ratcheted to ZERO once
    Drop 2 deletes every smash."""
    path = os.path.join(PROJECT_ROOT, "tests", "data",
                        "command_convention_baseline.json")
    with open(path, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    assert baseline["run_on_keys"] == [], (
        "command_convention_baseline.json still lists run-on keys; regenerate "
        "it after Drop 2 (tools/gen_command_convention_baseline.py)"
    )


def test_switch_canonical_forms_resolve_to_umbrella(registry):
    """Each `+verb/switch` canonical form resolves to its umbrella command (the
    switch is carried separately in ctx.switches by the parser)."""
    for form, umbrella_key, _switch in SWITCH_CANONICALS:
        # The parser strips `/switch` before lookup, so the umbrella key is what
        # resolves; verify the umbrella exists and owns its key.
        cmd = registry.get(umbrella_key)
        assert cmd is not None, f"umbrella {umbrella_key!r} for {form!r} missing"
        assert cmd.key == umbrella_key


def test_umbrellas_declare_the_switch(registry):
    """Every canonical switch is a declared valid_switch on its umbrella, so the
    parser's switch-validation accepts `+verb/switch`."""
    for form, umbrella_key, switch in SWITCH_CANONICALS:
        cmd = registry.get(umbrella_key)
        assert switch in cmd.valid_switches, (
            f"{umbrella_key} does not declare switch {switch!r} (for {form})"
        )


def test_umbrella_switch_impl_dispatch_intact():
    """The umbrella switch-impl maps still wire each deleted verb's command class
    (deletion was of the STANDALONE registration, not the implementation)."""
    from parser.bounty_commands import (
        _BOUNTY_SWITCH_IMPL, BountyClaimCommand, BountyTrackCommand,
        BountyCollectCommand,
    )
    assert _BOUNTY_SWITCH_IMPL["claim"] is BountyClaimCommand
    assert _BOUNTY_SWITCH_IMPL["track"] is BountyTrackCommand
    assert _BOUNTY_SWITCH_IMPL["collect"] is BountyCollectCommand

    from parser.narrative_commands import (
        _QUEST_SWITCH_IMPL, QuestAcceptCommand, QuestCompleteCommand,
        QuestAbandonCommand,
    )
    assert _QUEST_SWITCH_IMPL["accept"] is QuestAcceptCommand
    assert _QUEST_SWITCH_IMPL["complete"] is QuestCompleteCommand
    assert _QUEST_SWITCH_IMPL["abandon"] is QuestAbandonCommand

    from parser.smuggling_commands import _SMUGGLE_SWITCH_IMPL, SmugDeliverCommand
    assert _SMUGGLE_SWITCH_IMPL["deliver"] is SmugDeliverCommand

    from parser.crafting_commands import _CRAFT_SWITCH_IMPL, BuyResourcesCommand
    assert _CRAFT_SWITCH_IMPL["buyresources"] is BuyResourcesCommand


def test_surviving_non_runon_aliases_still_route(registry):
    """The non-run-on legacy aliases (Drops 3-4) still reach their umbrella —
    deleting the standalone registration de-collided them, not removed them."""
    survivors = {
        "claimbounty": "+bounty", "acceptbounty": "+bounty",
        "tracktarget": "+bounty", "hunttrack": "+bounty",
        "collectbounty": "+bounty", "claimreward": "+bounty",
        "acceptquest": "+quest", "finishquest": "+quest",
        "abandonquest": "+quest", "completequest": "+quest",
        "deliver": "+smuggle", "dropoff": "+smuggle",
        "buyres": "+craft",
    }
    for alias, umbrella in survivors.items():
        cmd = registry.get(alias)
        assert cmd is not None, f"surviving alias {alias!r} no longer resolves"
        assert cmd.key == umbrella, (
            f"{alias!r} routed to {cmd.key!r}, expected umbrella {umbrella!r}"
        )


def test_spacerquest_promoted_to_plus_form(registry):
    """The FDtS chain's run-on `spacerquest` key was promoted to `+spacerquest`
    (A1: OOC/query takes the + prefix). The bare run-on is gone; the + form and
    its remaining aliases resolve."""
    assert not registry.has_exact("spacerquest")
    cmd = registry.get("+spacerquest")
    assert cmd is not None and cmd.key == "+spacerquest"
    # FDtS aliases preserved.
    for alias in ("quest", "+dusttostars", "+fdts"):
        assert registry.get(alias) is not None, (
            f"FDtS alias {alias!r} no longer resolves"
        )


def test_no_new_run_on_collisions(registry):
    """Deleting the standalone run-on registrations only SHRINKS collisions —
    the run-on-family aliases that used to double-register are now single."""
    sigs = set(registry.collision_signatures)
    for resolved in (
        "alias:claimbounty", "alias:acceptbounty", "alias:tracktarget",
        "alias:collectbounty", "alias:acceptquest", "alias:finishquest",
        "alias:abandonquest", "alias:deliver", "alias:buyres",
    ):
        assert resolved not in sigs, (
            f"{resolved} should be de-collided after Drop 2"
        )
