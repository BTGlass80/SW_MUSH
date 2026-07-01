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
#
# Drop-34 (2026-06-23): `who` and `online` are re-added as redirect stubs
# (WhoStubCommand) so new players who type them get a helpful pointer to
# `+who` rather than "Huh? Unknown command."  They are NOT full duplicate
# implementations; they are pure redirects.  Removed from DELETED_EXACT_FORMS
# so the stub is not treated as a regression.  The +online and players forms
# remain deleted (they are not stub-worthy; the stub covers the common case).
DELETED_EXACT_FORMS = [
    # +who family — `who` and `online` are now redirect stubs (drop-34); not deleted.
    "+online", "players",
    # +inv family — fun13 (2026-06-27, Brian's call): the bare `inventory`/`inv`/
    # `i` reflexes are RE-ADDED as back-compat aliases (new players reflexively
    # type them and hit a dead-end at the open-world handoff). `+inv` stays
    # canonical; only the `+inventory` +synonym stays deleted.
    "+inventory",
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


def test_bare_inv_reflexes_map_to_inventory(registry):
    """fun13 (2026-06-27, Brian's call): the bare inventory reflexes
    `inventory`/`inv`/`i` are RE-ADDED as back-compat aliases of the canonical
    `+inv` (new players reflexively type them and used to hit a dead-end). They
    must now resolve to the inventory command."""
    inv_cmd = registry.get("+inv")
    assert inv_cmd is not None and inv_cmd.key == "+inv"
    for reflex in ("inv", "inventory", "i"):
        assert registry.has_exact(reflex), f"{reflex!r} should be a live alias"
        assert registry.get(reflex) is inv_cmd, (
            f"{reflex!r} must resolve to the +inv inventory command")


def test_who_is_single_canonical_command(registry):
    """There is exactly ONE who-listing command and it is `+who`.

    Drop-34 (2026-06-23) re-adds bare `who` as a *redirect stub*
    (WhoStubCommand) so new players who type `who` get a helpful
    pointer to `+who` instead of "Huh? Unknown command."  The
    stub is NOT a second who-listing implementation — it owns `who`
    as a newbie redirect and must not duplicate `+who`'s real logic.
    """
    from parser.builtin_commands import WhoStubCommand, WhoCommand
    assert registry.get("+who") is not None
    # Drop-34: `who` is now a redirect stub (WhoStubCommand), not absent.
    who_cmds = [c for c in registry.all_commands if c.key == "who"]
    assert len(who_cmds) == 1, (
        f"Expected exactly one `who` stub; got {who_cmds!r}"
    )
    assert isinstance(who_cmds[0], WhoStubCommand), (
        f"`who` key must be owned by WhoStubCommand, not {type(who_cmds[0])!r}"
    )
    # The stub must not be the full WhoCommand.
    assert not isinstance(who_cmds[0], WhoCommand)
    # `+who` is still the single canonical full implementation.
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
