# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/ground_combat.py — Ground combat scenarios (G1-G3).

Per design §6.4.

SH2 covers G1-G3 (the baseline: attack starts combat, HUD activates,
damage is taken). G4-G8 (stun, dodge declaration, cover, flee, death+
respawn) are deferred to SH4 because they require richer state setup
that benefits from the same harness extensions space combat needs
(advance_ticks, etc.).

Combat targets: hostile NPCs in the GCW spawn area. The auto-build
seeds 'Ponda Baba's Associate' (room 17, Chalmun's Cantina) and
'Imperial Patrol Trooper' (room 11) as hostile.

Note on tutorial NPCs: build_tutorial.py's auto_build_if_needed
contains a bug — build_all() ignores the db_path parameter and
hardcodes the project's sw_mush.db, so 'Sparring Partner', 'Training
Hunter', etc. don't actually land in temp test DBs. SH2 does NOT
depend on them. (Reported in the SH2 handoff.)
"""
from __future__ import annotations

import asyncio


async def _find_hostile_npc(h):
    """Locate any hostile NPC in the spawned world.

    Returns ``(npc_name, room_id)`` for the first hostile NPC found,
    or ``(None, None)`` if no hostile NPCs exist (which would itself
    be a finding worth reporting).

    "Hostile" is determined by ``ai_config_json.hostile == True``,
    matching ``engine/npc_combat_ai.is_hostile()``. (The char sheet
    is unrelated to hostility — this was a smoke-harness bug found
    during SH2 development.)
    """
    import json as _json
    rows = await h.db.fetchall(
        "SELECT id, name, room_id, ai_config_json FROM npcs"
    )
    for r in rows:
        try:
            ai = _json.loads(r["ai_config_json"] or "{}")
        except Exception:
            ai = {}
        if ai.get("hostile") is True:
            return r["name"], int(r["room_id"])
    return None, None


async def g1_attack_starts_combat(h):
    """G1 — `attack <hostile>` produces non-error output and starts combat.

    Doesn't assert on hit/miss (random) — just that the command runs,
    produces output, and doesn't blow up. If `attack` raises an
    exception or refuses with "no such target," that's the bug we
    catch.
    """
    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        # If the world has no hostile NPCs, that's a separate finding
        # that should NOT silently mask this scenario. Fail loudly.
        assert False, (
            "No hostile NPCs found in the world after auto-build. "
            "G1-G3 cannot run. Check NPC seed data."
        )

    s = await h.login_as("G1Striker", room_id=npc_room)
    # Look at the room first to confirm the target is visible.
    look = await h.cmd(s, "look")
    assert npc_name.lower() in look.lower(), (
        f"Target {npc_name!r} not visible in room {npc_room}. "
        f"Look output: {look[:400]!r}"
    )

    # Attack — use the first word of the NPC name to keep the target
    # token simple (e.g. 'attack ponda' for 'Ponda Baba's Associate').
    target_token = npc_name.split()[0].lower()
    out = await h.cmd(s, f"attack {target_token}")
    assert out and out.strip(), f"`attack` produced no output."
    assert "traceback" not in out.lower() and \
           "exception" not in out.lower(), (
        f"`attack` raised an exception. Output: {out[:500]!r}"
    )
    # We're tolerant about success — the attack might miss or even
    # be refused for security reasons (e.g. combat-disallowed room).
    # The point is that the command path executes cleanly.


async def g2_combat_state_payload_emitted(h):
    """G2 — Engaging combat emits a `combat_state` JSON event.

    The web client's combat HUD lives or dies on this event. If it
    stops firing, the HUD goes blank in production but unit tests
    don't notice.
    """
    npc_name, npc_room = await _find_hostile_npc(h)
    if npc_name is None:
        assert False, "No hostile NPCs found — see G1."

    s = await h.login_as("G2Engager", room_id=npc_room)
    target_token = npc_name.split()[0].lower()
    # Capture the events-since-marker: anything new in s.json_events
    # after this index came from the attack.
    pre_count = len(s.json_events)
    await h.cmd(s, f"attack {target_token}")
    # Allow a tick for the engine to push the HUD event.
    await asyncio.sleep(0.2)
    new_events = s.json_events[pre_count:]
    types_seen = [e.get("type") for e in new_events]

    # combat_state OR hud_update should appear — different code
    # paths emit different envelopes; what matters is the HUD got
    # signal of some kind.
    assert any(t in {"combat_state", "hud_update"} for t in types_seen), (
        f"No combat HUD event emitted on attack. "
        f"Event types received: {types_seen!r}"
    )


async def g3_take_damage_wound_progression(h):
    """G3 — A character with a wound_level shows wound state in the sheet.

    We can't reliably make a hostile NPC hit our PC in a single
    swing of dice (RNG). Instead, this scenario applies damage
    directly via the same path the damage engine uses, then verifies
    the wound state appears in the sheet payload.

    This catches the bug class where the wound display drifts from
    the underlying numeric state — exactly the F-finding the field
    kit audit closed, but worth re-asserting end-to-end.

    NOTE: WebSocket clients receive `+sheet` as a typed
    ``sheet_data`` event (see scenario H7); we check the event
    payload for wound state.
    """
    s = await h.login_as("G3Wounded", room_id=1)
    char_id = s.character["id"]

    # Apply wound_level=2 directly (Wounded). The save_character
    # path is the same one combat uses.
    await h.db.save_character(char_id, wound_level=2)
    s.character = await h.get_char(char_id)
    s.session.invalidate_char_obj()

    pre = len(s.json_events)
    await h.cmd(s, "+sheet")
    new_events = s.json_events[pre:]
    sheet_events = [e for e in new_events if e.get("type") == "sheet_data"]
    assert sheet_events, (
        f"+sheet emitted no sheet_data on wounded char. "
        f"Events: {[e.get('type') for e in new_events]!r}"
    )
    payload = sheet_events[0]
    payload_str = repr(payload).lower()
    has_wound_indicator = (
        "wound" in payload_str
        or "wounded" in payload_str
        or "stunned" in payload_str
        or "condition" in payload_str
    )
    assert has_wound_indicator, (
        f"sheet_data payload of a wounded character shows no wound "
        f"indicator. Payload (truncated): {payload_str[:500]!r}"
    )
