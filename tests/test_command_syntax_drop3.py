# -*- coding: utf-8 -*-
"""
Command-syntax rework — Drop 3 (service-family umbrella dead-alias cleanup).

Ratified plan: docs/design/command_syntax_rework_design_v2.md §"Phased build
plan" Drops 3-4 (the long tail — "canonicalized per A1 + deleted-redundant, in
module-grouped batches"). Drop 3 takes the first module-grouped batch: the six
service-family umbrellas whose alias lists re-declared names already OWNED by a
standalone command in the same module.

Because the standalone command registers AFTER the umbrella, it WINS the binding
— so every such umbrella alias was already dead (it never resolved to the
umbrella). Deleting it from the umbrella's `aliases` list is therefore a pure
zero-behaviour-change cleanup that drops the registry collision and removes the
redundant form the rework's rule C calls for. (The internal `_*_ALIAS_TO_SWITCH`
dispatch maps are intentionally LEFT intact — they are still exercised by the
umbrella's `+verb <word>` arg dispatch and by direct-instantiation tests.)

  Umbrella         Dead aliases deleted (now owned by the standalone command)
  +bounty          bounties bboard bountyboard mybounty activebounty myhunt
  +smuggle         smugjobs smugboard underworld smugaccept takerun smugjob
                   myrun cargo smugdump dumpcargo jettison
  +craft           craft survey resources res schematics schem experiment exp teach
  +medical         heal healaccept haccept healrate hrate
  +place           places place join sit depart stand
  +quest           quests personalquests

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

# Every dead alias Drop 3 removes from a service umbrella, mapped to the
# standalone command key it ALREADY resolved to (and must STILL resolve to —
# the whole point is zero behaviour change).
REMOVED_ALIAS_TO_OWNER = {
    # +bounty -> standalone query commands
    "bounties": "+bounties", "bboard": "+bounties", "bountyboard": "+bounties",
    "mybounty": "+mybounty", "activebounty": "+mybounty", "myhunt": "+mybounty",
    # +smuggle -> standalone job commands
    "smugjobs": "+smugjobs", "smugboard": "+smugjobs", "underworld": "+smugjobs",
    "smugaccept": "smugaccept", "takerun": "smugaccept",
    "smugjob": "+smugjob", "myrun": "+smugjob", "cargo": "+smugjob",
    "smugdump": "smugdump", "dumpcargo": "smugdump", "jettison": "smugdump",
    # +craft -> standalone bare IC verbs / query commands
    "craft": "craft", "survey": "survey",
    "resources": "resources", "res": "resources",
    "schematics": "schematics", "schem": "schematics",
    "experiment": "experiment", "exp": "experiment", "teach": "teach",
    # +medical -> standalone medical verbs
    "heal": "heal", "healaccept": "healaccept", "haccept": "healaccept",
    "healrate": "+healrate", "hrate": "+healrate",
    # +place -> standalone place verbs
    "places": "places", "place": "places",
    "join": "join", "sit": "join", "depart": "depart", "stand": "depart",
    # +quest -> standalone query command
    "quests": "+quests", "personalquests": "+quests",
}

# (umbrella module path, umbrella class name) for each touched umbrella.
UMBRELLAS = [
    ("parser.bounty_commands", "BountyCommand"),
    ("parser.smuggling_commands", "SmuggleCommand"),
    ("parser.crafting_commands", "CraftingCommand"),
    ("parser.medical_commands", "MedicalCommand"),
    ("parser.places_commands", "PlaceUmbrellaCommand"),
    ("parser.narrative_commands", "QuestCommand"),
]

# The dead aliases that any umbrella must no longer DECLARE, grouped per class.
UMBRELLA_FORBIDDEN_ALIASES = {
    "BountyCommand": {
        "bounties", "bboard", "bountyboard", "mybounty", "activebounty", "myhunt",
    },
    "SmuggleCommand": {
        "smugjobs", "smugboard", "underworld", "smugaccept", "takerun",
        "smugjob", "myrun", "cargo", "smugdump", "dumpcargo", "jettison",
    },
    "CraftingCommand": {
        "craft", "survey", "resources", "res", "schematics", "schem",
        "experiment", "exp", "teach",
    },
    "MedicalCommand": {"heal", "healaccept", "haccept", "healrate", "hrate"},
    "PlaceUmbrellaCommand": {"places", "place", "join", "sit", "depart", "stand"},
    "QuestCommand": {"quests", "personalquests"},
}


@pytest.fixture(scope="module")
def registry():
    return _build_full_registry()


def _load_class(modpath, clsname):
    import importlib
    return getattr(importlib.import_module(modpath), clsname)


def test_umbrellas_no_longer_declare_dead_aliases():
    """No service umbrella may still DECLARE one of the dead duplicate aliases —
    those names belong to the standalone command, not the umbrella."""
    for modpath, clsname in UMBRELLAS:
        cls = _load_class(modpath, clsname)
        declared = {a.lower() for a in getattr(cls, "aliases", [])}
        forbidden = UMBRELLA_FORBIDDEN_ALIASES[clsname]
        overlap = declared & forbidden
        assert not overlap, (
            f"{clsname} still declares dead duplicate alias(es) {sorted(overlap)} "
            f"— Drop 3 deletes them (owned by a standalone command)"
        )


def test_removed_aliases_resolve_unchanged(registry):
    """Zero behaviour change: every removed umbrella alias STILL resolves to the
    exact same standalone command it did before (the standalone always won)."""
    for alias, owner_key in REMOVED_ALIAS_TO_OWNER.items():
        cmd = registry.get(alias)
        assert cmd is not None, f"{alias!r} no longer resolves at all"
        assert cmd.key == owner_key, (
            f"{alias!r} now resolves to {cmd.key!r}, expected {owner_key!r} "
            f"(removal must not change resolution)"
        )


def test_removed_aliases_de_collided(registry):
    """The recorded key/alias collisions for the removed names are GONE — the
    baseline ratchet only shrinks."""
    sigs = set(registry.collision_signatures)
    # The subset that register() actually recorded as collisions (same-name
    # double declaration), now resolved by deleting the umbrella's copy.
    for name in (
        "bounties", "bboard", "bountyboard", "mybounty", "activebounty", "myhunt",
        "smugjobs", "smugboard", "underworld", "takerun", "smugjob", "myrun",
        "cargo", "dumpcargo", "jettison", "res", "schem", "exp",
        "haccept", "healrate", "hrate", "place", "sit", "stand",
        "quests", "personalquests",
    ):
        assert f"alias:{name}" not in sigs, (
            f"alias:{name} should be de-collided after Drop 3"
        )


def test_baseline_ratchet_excludes_removed(registry):
    """The regenerated baseline must not list any of the Drop-3-removed
    collisions, and the live registry must introduce nothing beyond it."""
    path = os.path.join(PROJECT_ROOT, "tests", "data",
                        "command_convention_baseline.json")
    with open(path, "r", encoding="utf-8") as fh:
        baseline = json.load(fh)
    allowed = set(baseline["collisions"])
    live = set(registry.collision_signatures)
    assert live - allowed == set(), (
        "live registry introduced collisions beyond the baseline: "
        f"{sorted(live - allowed)}"
    )
    for name in ("bounties", "smugjobs", "res", "haccept", "sit", "quests"):
        assert f"alias:{name}" not in allowed, (
            f"alias:{name} still in baseline — regenerate it (Drop 3)"
        )


def test_umbrella_keys_and_live_routing_intact(registry):
    """The umbrellas themselves and their genuine switch-routing aliases still
    resolve to the umbrella (only the DEAD duplicates were removed)."""
    for key in ("+bounty", "+smuggle", "+craft", "+medical", "+place", "+quest"):
        cmd = registry.get(key)
        assert cmd is not None and cmd.key == key, f"umbrella {key!r} missing"
    # ctx.command-keyed umbrellas keep their verb-shorthand aliases routing in.
    live = {
        "claimbounty": "+bounty", "tracktarget": "+bounty",
        "collectbounty": "+bounty",
        "deliver": "+smuggle", "dropoff": "+smuggle",
        "buyres": "+craft",
        "acceptquest": "+quest", "finishquest": "+quest", "abandonquest": "+quest",
    }
    for alias, umbrella in live.items():
        cmd = registry.get(alias)
        assert cmd is not None and cmd.key == umbrella, (
            f"live switch-routing alias {alias!r} should still reach {umbrella!r}, "
            f"got {getattr(cmd, 'key', None)!r}"
        )


def test_arg_keyed_dispatch_maps_intact():
    """The arg-keyed umbrellas (+medical, +place) keep their _ALIAS_TO_SWITCH
    maps — those drive `+medical <verb>` / `+place <verb>` and were NOT touched."""
    from parser.medical_commands import _MEDICAL_ALIAS_TO_SWITCH
    assert _MEDICAL_ALIAS_TO_SWITCH.get("haccept") == "accept"
    assert _MEDICAL_ALIAS_TO_SWITCH.get("healrate") == "rate"
    from parser.places_commands import _PLACE_ALIAS_TO_SWITCH
    assert _PLACE_ALIAS_TO_SWITCH.get("sit") == "join"
    assert _PLACE_ALIAS_TO_SWITCH.get("stand") == "depart"
