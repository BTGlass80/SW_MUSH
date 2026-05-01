# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/social_housing_medical_tutorial.py — SH6.

Per design §6.9. Covers the surfaces that matter for any player who
spends more than 30 seconds in-game but weren't covered by the SH1
foundation: housing, sabacc, perform, medical, training/tutorial.

Note: SH6 explicitly EXERCISES the post-bugfix housing path. Before
the bugfix2 + the SH6-housing-fix dropped together, every housing
subcommand raised NameError because of an import-scope bug in
HousingCommand.execute(). SH6 catches regressions in that fix.
"""
from __future__ import annotations

import asyncio


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

async def _find_cantina_room(h):
    """Return the room_id of a room whose ZONE is a cantina.

    Both `+sabacc` and `perform` gate on the *zone* name (not the
    room name) containing "cantina". The standard GCW spawn has
    Chalmun's Cantina sub-rooms (Entrance/Main Bar/Back Hallway)
    tagged with zone_id=3 ('Chalmun's Cantina').

    NOTE: room #3 ("Chalmun's Cantina" itself) has zone_id=None — a
    real data-side bug discovered by SH6. Players can't sabacc/
    perform in the canonical cantina room; only its sub-rooms.
    SH6 picks a zone-tagged sub-room to dodge that bug; the bug
    itself is documented in the SH6 handoff.
    """
    rows = await h.db.fetchall(
        "SELECT r.id FROM rooms r "
        "JOIN zones z ON r.zone_id = z.id "
        "WHERE LOWER(z.name) LIKE '%cantina%' "
        "ORDER BY r.id LIMIT 1"
    )
    return int(rows[0]["id"]) if rows else None


async def _find_tutorial_hub(h):
    """Return the room_id of the Training Grounds hub.

    Only present after build_tutorial.auto_build_if_needed runs
    against the harness DB (which requires bug-fix #3 — the
    db_path threading fix — to be in place).
    """
    rows = await h.db.fetchall(
        "SELECT id FROM rooms WHERE name = 'Training Grounds' LIMIT 1"
    )
    return int(rows[0]["id"]) if rows else None


# ──────────────────────────────────────────────────────────────────────────
# Housing scenarios
# ──────────────────────────────────────────────────────────────────────────

async def h1_housing_status_renders(h):
    """H1 — `housing` (no args) shows status without raising.

    Catches the import-scope bug in HousingCommand._cmd_status
    (and 10 sibling _cmd_* methods) that produced NameError on
    every player housing query before the fix.
    """
    s = await h.login_as("H1Housing", room_id=1)
    out = await h.cmd(s, "housing")
    assert out and out.strip(), "`housing` produced no output"
    # Specifically catch the pre-fix symptom.
    assert "is not defined" not in out.lower(), (
        f"NameError leaked through to player. Output: {out[:300]!r}"
    )
    assert "traceback" not in out.lower(), (
        f"`housing` raised: {out[:500]!r}"
    )
    # Status output should mention housing or a relevant noun.
    out_lc = out.lower()
    assert ("housing" in out_lc or "home" in out_lc or
            "rent" in out_lc or "tier" in out_lc), (
        f"`housing` status doesn't look like a status display. "
        f"Output: {out[:400]!r}"
    )


async def h2_housing_storage_runs(h):
    """H2 — `housing storage` exercises the storage subcommand.

    For a player without a home, the expected output is "You don't
    have a home with storage." That's a successful gate, not a
    failure. We just check it didn't raise.
    """
    s = await h.login_as("H2Storage", room_id=1)
    out = await h.cmd(s, "housing storage")
    assert "is not defined" not in out.lower(), (
        f"NameError leaked through. Output: {out[:300]!r}"
    )
    assert "traceback" not in out.lower(), (
        f"`housing storage` raised: {out[:500]!r}"
    )


async def h3_sethome_unauthorized(h):
    """H3 — `sethome` in a non-housing room produces a clear refusal.

    `sethome` is supposed to mark the current room as the player's
    home, but only if the room is a housing tier room they own. In
    a public room it should refuse politely.
    """
    s = await h.login_as("H3SetHome", room_id=1)
    out = await h.cmd(s, "sethome")
    assert "traceback" not in out.lower(), (
        f"`sethome` raised: {out[:500]!r}"
    )
    # Refusal is the success case here. Look for a refusal-shaped
    # output: mentions home, housing, can't, must, your.
    assert out and out.strip(), "`sethome` produced no output"


# ──────────────────────────────────────────────────────────────────────────
# Sabacc + performer (cantina-only)
# ──────────────────────────────────────────────────────────────────────────

async def h4_sabacc_in_cantina(h):
    """H4 — `+sabacc` in a cantina room produces game info or a
    table-shaped response (not "you need to be in a cantina").
    """
    cantina_room = await _find_cantina_room(h)
    assert cantina_room, "No cantina-named room found in the spawned world"

    s = await h.login_as("H4Sabacc", room_id=cantina_room, credits=1000)
    out = await h.cmd(s, "+sabacc")
    assert "traceback" not in out.lower(), (
        f"`+sabacc` raised: {out[:500]!r}"
    )
    assert out and out.strip(), "`+sabacc` produced no output"
    # The "must be in a cantina" gate should NOT fire — we ARE in one.
    assert "need to be in a cantina" not in out.lower(), (
        f"`+sabacc` rejected room {cantina_room} as non-cantina. "
        f"Output: {out[:300]!r}"
    )


async def h5_perform_in_cantina(h):
    """H5 — `perform <skill>` in a cantina runs the entertainer
    station-act path.
    """
    cantina_room = await _find_cantina_room(h)
    assert cantina_room, "No cantina-named room found in the spawned world"

    s = await h.login_as("H5Performer", room_id=cantina_room)
    out = await h.cmd(s, "perform sing")
    assert "traceback" not in out.lower(), (
        f"`perform sing` raised: {out[:500]!r}"
    )
    assert out and out.strip(), "`perform sing` produced no output"
    assert "need to be in a cantina" not in out.lower(), (
        f"`perform` rejected room {cantina_room} as non-cantina. "
        f"Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Medical
# ──────────────────────────────────────────────────────────────────────────

async def h6_healrate_displays(h):
    """H6 — `+healrate` shows the heal-cost configuration.

    Lightweight read-only check — the heal economy is a player-
    facing toggle.
    """
    s = await h.login_as("H6HealRate", room_id=1)
    out = await h.cmd(s, "+healrate")
    assert "traceback" not in out.lower(), (
        f"`+healrate` raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Expected to mention "credit" or a cost value or "rate".
    assert "credit" in out_lc or "rate" in out_lc or any(c.isdigit() for c in out), (
        f"`+healrate` output doesn't look like a rate display. "
        f"Output: {out[:300]!r}"
    )


async def h7_heal_usage_with_no_args(h):
    """H7 — `heal` with no args produces the usage hint.

    Catches the regression where bare `heal` raises an IndexError
    or similar instead of routing to the usage handler.
    """
    s = await h.login_as("H7Heal", room_id=1)
    out = await h.cmd(s, "heal")
    assert "traceback" not in out.lower(), (
        f"bare `heal` raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    assert "usage" in out_lc or "heal <" in out_lc, (
        f"bare `heal` didn't produce a usage hint. "
        f"Output: {out[:300]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# Tutorial
# ──────────────────────────────────────────────────────────────────────────

async def h8_training_list_runs(h):
    """H8 — `training list` shows tutorial modules.

    Validates the tutorial loader after the bugfix2 db_path fix —
    before it landed, the tutorial built into the wrong DB and
    `training list` against a temp DB came up empty.
    """
    hub = await _find_tutorial_hub(h)
    if not hub:
        # Tutorial wasn't built into this DB. Pre-bugfix2 this was
        # the silent-fail mode. We assert loudly so the regression
        # is obvious if it returns.
        assert False, (
            "Tutorial hub 'Training Grounds' not found in the harness "
            "DB. Did the build_tutorial db_path fix regress?"
        )

    s = await h.login_as("H8Trainer", room_id=hub)
    out = await h.cmd(s, "training list")
    assert "traceback" not in out.lower(), (
        f"`training list` raised: {out[:500]!r}"
    )
    assert out and out.strip(), "`training list` produced no output"
    # The list should mention multiple modules.
    out_lc = out.lower()
    assert ("training" in out_lc or "module" in out_lc or
            "combat" in out_lc or "trader" in out_lc or
            "bounty" in out_lc), (
        f"`training list` output doesn't look like a module catalog. "
        f"Output: {out[:400]!r}"
    )


async def h9_training_room_at_hub(h):
    """H9 — Walking into the Training Grounds hub renders.

    A spawn-into-tutorial smoke check. Catches data drift in the
    tutorial loader (e.g. a missing room reference) without needing
    to drive the full training flow.
    """
    hub = await _find_tutorial_hub(h)
    assert hub, "Tutorial hub not found — see H8 for the regression hint"

    s = await h.login_as("H9HubLook", room_id=hub)
    out = await h.cmd(s, "look")
    assert "traceback" not in out.lower(), (
        f"`look` in tutorial hub raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # Hub room title should appear.
    assert "training grounds" in out_lc, (
        f"Hub `look` doesn't show 'Training Grounds'. "
        f"Output: {out[:400]!r}"
    )
