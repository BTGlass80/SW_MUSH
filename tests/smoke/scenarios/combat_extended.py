# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/combat_extended.py — PvP and combat-status scenarios
(CX1–CX4). Drop 2 Block C.

Existing G1–G3 in `ground_combat.py` cover the PC-vs-NPC happy path:
attack starts combat, HUD event fires, wounded state renders. Block C
extends to:

  CX1 — Security gate refuses combat in SECURED zones (NPC target).
        Uses set_security_override so the test isn't dependent on
        per-era property data — CW spawn is mostly CONTESTED, so we
        flip a zone to SECURED for the duration of the test.
  CX2 — PvP consent gate refuses unprovoked attack between two PCs
        in CONTESTED zones. The "Imperial law prohibits" message
        signals the consent flow is alive (challenge + accept is
        the unblock path, deferred to a positive-path scenario).
  CX3 — `fulldodge` while in active combat doesn't traceback. The
        engine may accept the declaration OR reject it ("must be
        your only action") depending on what was auto-declared
        during attack — both are clean responses.
  CX4 — `+combat` with active combat shows round-by-round status.

Block C deliberately doesn't try to drive a combat to resolution —
the full attack→damage→wound→respawn loop has rich state and RNG
that's hard to assert robustly. The G3 wound-state check covers
the equivalent display end of that flow.
"""
from __future__ import annotations

import asyncio
import json


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

async def _find_hostile_npc(h):
    """Locate any hostile NPC in the spawned world.

    Mirrors tests/smoke/scenarios/ground_combat._find_hostile_npc.
    Returns (npc_name, room_id) or (None, None).
    """
    rows = await h.db.fetchall(
        "SELECT id, name, room_id, ai_config_json FROM npcs"
    )
    for r in rows:
        try:
            ai = json.loads(r["ai_config_json"] or "{}")
        except Exception:
            ai = {}
        if ai.get("hostile") is True:
            return r["name"], int(r["room_id"])
    return None, None


# ──────────────────────────────────────────────────────────────────────────
# CX1 — SECURED zone refuses attack
# ──────────────────────────────────────────────────────────────────────────

async def cx1_attack_refused_in_secured_zone(h):
    """CX1 — `attack <hostile>` in a SECURED zone produces a refusal,
    not a combat-init.

    Validates the AttackCommand._check_security_gate path. Uses
    set_security_override to flip the target room's zone to SECURED
    for this scenario so the test isn't dependent on data in the
    YAML/properties layer (CW seed is mostly CONTESTED by default).

    Cleanup: the override is cleared at the end so subsequent
    scenarios in the same class-scoped harness don't inherit a
    SECURED Mos Eisley.
    """
    from engine.security import (
        set_security_override, SecurityLevel, clear_all_overrides,
    )

    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        # Same finding G1 catches; fail loud.
        assert False, (
            "No hostile NPCs found in the world after auto-build."
        )

    # Find the NPC's zone and flip it to SECURED.
    room = await h.db.get_room(npc_room)
    zone_id = room.get("zone_id") if room else None
    assert zone_id, (
        f"Hostile NPC's room {npc_room} has no zone_id; "
        f"can't apply security override."
    )

    try:
        set_security_override(zone_id, SecurityLevel.SECURED)

        s = await h.login_as("CX1Refused", room_id=npc_room)
        target_token = npc_name.split()[0].lower()
        out = await h.cmd(s, f"attack {target_token}")
        assert "traceback" not in out.lower(), (
            f"`attack` in SECURED zone raised: {out[:500]!r}"
        )
        # The refusal message references Imperial security or law
        # enforcement. Don't pin exact wording; assert intent.
        out_lc = out.lower()
        assert (
            "imperial" in out_lc or "security" in out_lc or
            "stop" in out_lc or "law" in out_lc or
            "prohibit" in out_lc or "patrol" in out_lc
        ), (
            f"SECURED-zone attack refusal doesn't reference "
            f"security/law/imperial. Output: {out[:500]!r}"
        )
    finally:
        clear_all_overrides()


# ──────────────────────────────────────────────────────────────────────────
# CX2 — CONTESTED + no consent: PvP refused
# ──────────────────────────────────────────────────────────────────────────

async def cx2_pvp_attack_refused_without_consent(h):
    """CX2 — In a CONTESTED zone, A attacking B (both PCs) without
    consent produces the "Imperial law prohibits" message and does
    NOT start combat.

    Default CW spawn (room 1) is CONTESTED, so no override needed.
    The consent flow is `challenge → accept` (a positive-path scenario
    is deferred — needs the accept-side timing handled).
    """
    a = await h.login_as("CX2Aggro", room_id=1)
    b = await h.login_as("CX2Target", room_id=1)

    out = await h.cmd(a, f"attack {b.character['name']}")
    assert "traceback" not in out.lower(), (
        f"PvP attack raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The consent-required message references "Imperial law
    # prohibits" or "challenge". Either substring is enough.
    assert (
        "prohibit" in out_lc or "challenge" in out_lc or
        "imperial law" in out_lc or "consent" in out_lc
    ), (
        f"PvP attack without consent didn't surface the consent gate. "
        f"Output: {out[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# CX3 — fulldodge declaration during active combat doesn't crash
# ──────────────────────────────────────────────────────────────────────────

async def cx3_fulldodge_in_active_combat(h):
    """CX3 — After starting combat with `attack`, `fulldodge` runs
    cleanly (no traceback).

    The engine may accept the declaration (player hadn't already
    declared this round), reject it ("must be your only action"),
    OR even surface "you're not in combat" if the auto-resolve loop
    killed the player and ended combat between attack and fulldodge.
    All three are valid responses; what we're catching is a
    regression in `_ensure_in_combat` lookup or `declare_action`
    dispatch that would crash the command path.

    Why this is useful even with the loose assertion: combat init
    + declaration parsing has shipped real NameError / KeyError
    bugs historically (G1's NPC-vs-PC discovery was also "no
    traceback" focused). Crash-class regressions get caught here;
    full-flow correctness lives in unit tests.
    """
    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        assert False, "No hostile NPCs found — see CX1 setup."

    s = await h.login_as("CX3Dodger", room_id=npc_room)
    target_token = npc_name.split()[0].lower()
    init = await h.cmd(s, f"attack {target_token}")
    assert "traceback" not in init.lower(), (
        f"attack to start combat raised: {init[:500]!r}"
    )

    out = await h.cmd(s, "fulldodge")
    assert "traceback" not in out.lower(), (
        f"`fulldodge` raised: {out[:500]!r}"
    )
    assert out and out.strip(), "`fulldodge` produced no output"


# ──────────────────────────────────────────────────────────────────────────
# CX4 — `+combat` status display in active combat
# ──────────────────────────────────────────────────────────────────────────

async def cx4_combat_status_renders_in_active_combat(h):
    """CX4 — `+combat` mid-combat shows round-by-round combatant info.

    Reads the active combat instance from the room's combat manager.
    Pre-fix-class regressions of this command typically surface as
    KeyError on missing combatant fields (init, CP, FP) when the
    sheet is partially populated.
    """
    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        assert False, "No hostile NPCs found — see CX1 setup."

    s = await h.login_as("CX4Status", room_id=npc_room)
    target_token = npc_name.split()[0].lower()
    init = await h.cmd(s, f"attack {target_token}")
    assert "traceback" not in init.lower(), (
        f"attack raised before status check: {init[:500]!r}"
    )

    out = await h.cmd(s, "+combat")
    assert "traceback" not in out.lower(), (
        f"`+combat` in active combat raised: {out[:500]!r}"
    )
    assert out and out.strip(), "`+combat` produced no output"
    out_lc = out.lower()
    # The display includes "Round" + an init/CP/FP block. Don't pin
    # exact formatting; assert at least one of the round/init/combat
    # tokens appears.
    assert (
        "round" in out_lc or "init" in out_lc or
        "combat" in out_lc
    ), (
        f"`+combat` output doesn't look like a combat-status display. "
        f"Output: {out[:500]!r}"
    )
