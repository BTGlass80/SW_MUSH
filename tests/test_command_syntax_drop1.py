# -*- coding: utf-8 -*-
"""
Command-syntax rework — Drop 1 (prefix canonicalization).

Ratified plan: docs/design/command_syntax_rework_design_v2.md §"Phased build
plan" Drop 1. The newcomer-facing, high-traffic OOC/HUD query commands get a
single canonical `+`-prefixed form (A1 prefix policy: OOC/meta/query/HUD ->
`+`), and the redundant bare forms + `+`-synonyms are DELETED (CLEAN — no
back-compat aliases, since nobody is playing yet).

Targets (canonical -> deleted forms):
  +who    <- who, online, +online, players (the channel duplicate was folded in)
  +inv    <- inventory, inv, i, +inventory
  +sheet  <- sheet, score, stats, +score, +stats, sc
  +finger <- finger
  +roll   <- roll
  +check  <- check

This test reuses the single authoritative full-registry builder so it sees the
exact command set the live server dispatches.
"""
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from tests.test_t321_admin_command_access_invariant import (  # noqa: E402
    _build_full_registry,
)


# Canonical forms that MUST resolve to a single command after Drop 1.
CANONICAL_FORMS = ["+who", "+inv", "+sheet", "+finger", "+roll", "+check"]

# Forms Drop 1 DELETES. After deletion none of these may be an exact primary
# key or alias in the live registry (has_exact does NO prefix matching, so it
# is the precise "is this token still a registered name" probe).
DELETED_EXACT_FORMS = [
    # +who family
    "who", "online", "+online", "players",
    # +inv family
    "inventory", "i", "+inventory",
    # +sheet family
    "sheet", "score", "stats", "+score", "+stats", "sc",
    # +finger / +roll / +check
    "finger", "roll", "check",
]


@pytest.fixture(scope="module")
def registry():
    return _build_full_registry()


def test_canonical_forms_resolve(registry):
    """Every Drop-1 canonical `+`-form resolves to exactly the command whose
    primary key it is."""
    for form in CANONICAL_FORMS:
        cmd = registry.get(form)
        assert cmd is not None, f"canonical form {form!r} no longer resolves"
        assert cmd.key == form, (
            f"{form!r} resolved to {cmd.key!r}, not its own canonical key"
        )


def test_deleted_forms_are_gone(registry):
    """None of the deleted bare/`+`-synonym forms remain registered as an
    exact key or alias."""
    for form in DELETED_EXACT_FORMS:
        assert not registry.has_exact(form), (
            f"{form!r} is still a registered key/alias — Drop 1 deletes it"
        )


def test_bare_inv_no_longer_maps_to_inventory(registry):
    """The bare `inv` was an inventory alias; deleting it means `inv` no longer
    reaches the inventory command. (It now prefix-matches `investigate`, the
    only registered key starting with `inv` — a documented, intentional
    consequence of the CLEAN deletion.)"""
    assert not registry.has_exact("inv")
    inv_cmd = registry.get("+inv")
    resolved = registry.get("inv")
    assert resolved is not inv_cmd, (
        "bare `inv` must not resolve to the inventory command after Drop 1"
    )
    # The surviving prefix-match is investigate (or None if ambiguous) — never
    # inventory.
    if resolved is not None:
        assert resolved.key != "+inv"


def test_who_is_single_canonical_command(registry):
    """There is exactly ONE who-listing command and it is `+who`; the bare
    `who` key (formerly parser.channel_commands.WhoCommand) is gone and was
    folded into the builtin +who."""
    assert registry.get("+who") is not None
    # No exact `who` key/alias survives (a stray bare `who` would re-introduce
    # the dual-impl ambiguity Drop 1 resolved).
    assert not registry.has_exact("who")
    who_cmds = [c for c in registry.all_commands if c.key == "who"]
    assert who_cmds == [], "a command still owns the bare `who` key"
    plus_who = [c for c in registry.all_commands if c.key == "+who"]
    assert len(plus_who) == 1, "expected exactly one +who command"


def test_who_merge_preserves_location_and_status(registry):
    """The merged +who keeps the former channel `who`'s richer display
    (location + combat status) — guard the merge didn't silently drop it."""
    from parser.builtin_commands import _who_player_status, WhoCommand
    # Helper ported from the deleted channel command still exists.
    assert callable(_who_player_status)
    cmd = registry.get("+who")
    assert isinstance(cmd, WhoCommand)
    # help_text advertises the richer view.
    assert "location" in cmd.help_text.lower()


def test_channel_who_helper_removed():
    """The old channel-who status helper is deleted with its command (no dead
    code left behind)."""
    import parser.channel_commands as cc
    assert not hasattr(cc, "WhoCommand"), (
        "parser.channel_commands.WhoCommand should be deleted"
    )
    assert not hasattr(cc, "_get_player_status"), (
        "the orphaned channel-who status helper should be deleted"
    )


def test_online_collision_resolved(registry):
    """Deleting the `online` synonym from both who-commands removes the
    `alias:online` collision the Drop-0 baseline recorded."""
    assert "alias:online" not in registry.collision_signatures
