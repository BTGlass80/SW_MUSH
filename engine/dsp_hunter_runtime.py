# -*- coding: utf-8 -*-
"""
engine/dsp_hunter_runtime.py — hunter.2 IO orchestration for the Dark-Side
bounty hunter (the live-spawn climax + reward-on-defeat loop).

engine/dsp_hunter.py stays PURE (deciders + flavor + the combat-sheet/ai-config
builders). This module owns the DB writes, the NPC spawn, the combat kick-off,
and the message delivery — the side-effecting half of hunter.2.

Used by:
  * server/tick_handlers_progression.py::dsp_hunter_tick — spawns the hunter
    when a pursuit reaches `at_heels`, reconciles/despawns on escape, and
    despawns on atonement.
  * parser/combat_commands.py (NPC-death hook) — on_dsp_hunter_killed clears the
    pursuit and removes the defeated hunter (defeating it IS the prestige-domain
    reward; the trail ends and a fresh pursuit only rebuilds next cycle).

All functions are failure-tolerant: every external call is guarded so a bad row
never aborts the tick or the combat-death sweep.
"""
from __future__ import annotations

import json
import logging

from engine import dsp_hunter as H

log = logging.getLogger(__name__)


def _parse_json(raw) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def _announce_room(session_mgr, room_id: int, line: str) -> None:
    """Send a line to every session in a room. Best-effort."""
    if session_mgr is None or not line or room_id is None:
        return
    try:
        for sess in session_mgr.sessions_in_room(room_id):
            try:
                await sess.send_line(line)
            except Exception:
                log.debug("[dsp_hunter_rt] room announce send failed", exc_info=True)
    except Exception:
        log.debug("[dsp_hunter_rt] sessions_in_room failed", exc_info=True)


async def _start_hunter_combat(db, session_mgr, room_id: int, npc_id: int,
                               hunter_name: str) -> None:
    """Kick off ground combat between the quarry (and anyone else in the room)
    and the freshly-spawned hunter. Mirrors the ctx-free pattern used by
    engine/encounter_boarding.py::_trigger_combat_with_boarders, reusing the
    same combat primitives so the climax fight starts the instant the hunter
    appears rather than waiting for the quarry's next move."""
    try:
        from engine.npc_combat_ai import build_npc_character, get_npc_behavior
        from engine.character import Character
        from parser.combat_commands import (
            _get_or_create_combat, _npc_behaviors,
            _broadcast_events, _auto_declare_npc_actions,
        )
    except Exception:
        log.warning("[dsp_hunter_rt] combat primitives import failed",
                    exc_info=True)
        return

    chars = await db.get_characters_in_room(room_id)
    if not chars:
        return
    try:
        cover_max = await db.get_room_property(room_id, "cover_max", 0)
    except Exception:
        cover_max = 0
    combat = _get_or_create_combat(room_id, cover_max=cover_max)
    new_combat = combat.round_num == 0

    for ch in chars:
        if not combat.get_combatant(ch["id"]):
            try:
                combat.add_combatant(Character.from_db_dict(ch))
            except Exception:
                log.debug("[dsp_hunter_rt] add player combatant failed",
                          exc_info=True)

    npc_row = await db.get_npc(npc_id)
    if npc_row and not combat.get_combatant(npc_id):
        npc_row = dict(npc_row)
        npc_char = build_npc_character(npc_row)
        if npc_char is not None:
            combatant = combat.add_combatant(npc_char)
            combatant.is_npc = True
            _npc_behaviors[npc_id] = get_npc_behavior(npc_row)

    if new_combat:
        try:
            events = combat.roll_initiative()
            await _broadcast_events(events, session_mgr, room_id)
        except Exception:
            log.debug("[dsp_hunter_rt] initiative/broadcast failed", exc_info=True)

    class _MinCtx:
        def __init__(self, d, sm):
            self.db = d
            self.session_mgr = sm

    try:
        await _auto_declare_npc_actions(combat, _MinCtx(db, session_mgr))
    except Exception:
        log.debug("[dsp_hunter_rt] auto-declare failed", exc_info=True)

    h = hunter_name or "The hunter"
    for ch in chars:
        try:
            for sess in (session_mgr.sessions_for_character(ch["id"]) or []):
                await sess.send_line(
                    f"  \033[1;31m[COMBAT]\033[0m {h} is on you! "
                    f"Declare: \033[1mattack/dodge/aim/flee\033[0m"
                )
        except Exception:
            log.debug("[dsp_hunter_rt] combat prompt failed", exc_info=True)


async def spawn_hunter(db, session_mgr, quarry_char: dict, dsp: int):
    """Spawn the live hunter NPC into the quarry's room at the `at_heels` climax,
    record it on the pursuit, announce its arrival, and start the fight.

    Idempotent: if a live hunter is already present in the quarry's room, returns
    the existing NPC id without spawning a second. Returns the NPC id, or None.
    """
    if not isinstance(quarry_char, dict):
        return None
    quarry_id = quarry_char.get("id")
    room_id = quarry_char.get("room_id")
    if quarry_id is None or room_id is None:
        return None

    hunter_name = H.hunter_for(quarry_id)

    # Idempotency: don't double-spawn if a live hunter is already in this room.
    try:
        pursuit = await db.get_dsp_pursuit(quarry_id)
        existing = (pursuit or {}).get("spawned_npc_id")
        if existing:
            row = await db.get_npc(existing)
            if row and row.get("room_id") == room_id:
                return existing
    except Exception:
        log.debug("[dsp_hunter_rt] idempotency check failed", exc_info=True)

    try:
        sheet = H.hunter_combat_sheet(quarry_id, dsp)
        ai = H.hunter_ai_config(quarry_id, quarry_id, dsp, hunter_name)
        desc = H.hunter_description(hunter_name, dsp)
        npc_id = await db.create_npc(
            hunter_name, room_id, "Human", desc,
            json.dumps(sheet), json.dumps(ai),
        )
    except Exception:
        log.warning("[dsp_hunter_rt] spawn create_npc failed for quarry %r",
                    quarry_id, exc_info=True)
        return None

    try:
        await db.set_dsp_pursuit_spawn(quarry_id, npc_id)
    except Exception:
        log.debug("[dsp_hunter_rt] set_dsp_pursuit_spawn failed", exc_info=True)

    await _announce_room(session_mgr, room_id, H.arrival_line(hunter_name))
    await _start_hunter_combat(db, session_mgr, room_id, npc_id, hunter_name)
    log.info("[dsp_hunter_rt] spawned hunter %s (npc=%s) for quarry %s in room %s",
             hunter_name, npc_id, quarry_id, room_id)
    return npc_id


async def despawn_hunter(db, npc_id, *, quarry_id=None, session_mgr=None,
                         room_id=None, line: str = "") -> None:
    """Remove a spawned hunter NPC (atonement / escape reconcile) and clear the
    pursuit's spawn reference. Optionally announce a closing line."""
    if npc_id is None:
        return
    rid = room_id
    try:
        row = await db.get_npc(npc_id)
        if rid is None and row:
            rid = row.get("room_id")
    except Exception:
        row = None
    try:
        await db.delete_npc(npc_id)
    except Exception:
        log.debug("[dsp_hunter_rt] delete_npc failed for %s", npc_id, exc_info=True)
    if quarry_id is not None:
        try:
            await db.set_dsp_pursuit_spawn(int(quarry_id), None)
        except Exception:
            log.debug("[dsp_hunter_rt] clear spawn ref failed", exc_info=True)
    if line and rid is not None:
        await _announce_room(session_mgr, rid, line)


async def on_dsp_hunter_killed(db, npc_id, killer_char, room_id,
                               session_mgr=None) -> bool:
    """Combat-death hook: if the dead NPC is a runtime-spawned DSP hunter, the
    quarry (or whoever struck the killing blow) has bested it — clear the pursuit
    (the trail ends; a new pursuit only rebuilds next tick) and remove the row.

    No-op (returns False) for any NPC that isn't a DSP hunter, so it's cheap to
    call for every dead combatant. Prestige-domain: confers no credits."""
    try:
        row = await db.get_npc(npc_id)
    except Exception:
        return False
    if not row:
        return False
    ai = _parse_json(row.get("ai_config_json"))
    quarry_id = ai.get(H.DSP_HUNTER_AI_KEY)
    if quarry_id is None:
        return False  # not a DSP hunter

    hunter_name = row.get("name") or H.hunter_for(quarry_id)
    killer_name = (killer_char or {}).get("name", "Someone") \
        if isinstance(killer_char, dict) else "Someone"

    try:
        await db.clear_dsp_pursuit(int(quarry_id))
    except Exception:
        log.debug("[dsp_hunter_rt] clear_dsp_pursuit on kill failed", exc_info=True)
    try:
        await db.delete_npc(npc_id)
    except Exception:
        log.debug("[dsp_hunter_rt] delete defeated hunter failed", exc_info=True)

    await _announce_room(session_mgr, room_id,
                         H.defeat_line(hunter_name, killer_name))
    log.info("[dsp_hunter_rt] hunter %s (npc=%s) defeated by %s; pursuit on "
             "quarry %s cleared", hunter_name, npc_id, killer_name, quarry_id)
    return True


async def on_quarry_collected(db, victim_id, *, session_mgr=None,
                              room_id=None) -> bool:
    """PC-death hook (the inverse of on_dsp_hunter_killed): if the dead PC had a
    runtime-spawned DSP hunter on them, the hunter has COLLECTED its bounty.

    Fires from engine/death.py::on_pc_death for every PC death, so it must be
    cheap and a no-op when no live hunter is attached. When a hunter IS attached:

      - announce the collect line to the room (the narrative beat the
        escape-reconcile path lacked),
      - despawn the hunter NPC (contract fulfilled — it leaves with its bounty),
      - clear the pursuit so it resets to a FRESH start (NOT the escape-reconcile
        'imminent' reset — the quarry was collected, not slipped; since the PC is
        still on the dark path the tick rebuilds a new pursuit from progress 0).

    Prestige-domain: the quarry's standing death penalty (Wounded + corpse +
    insurance) already applies; the collect takes no credits and changes no DSP.
    Returns True iff a hunter was collected. Best-effort: never raises into the
    death path.
    """
    if victim_id is None:
        return False
    try:
        pursuit = await db.get_dsp_pursuit(int(victim_id))
    except Exception:
        log.debug("[dsp_hunter_rt] collect: get_dsp_pursuit failed for %s",
                  victim_id, exc_info=True)
        return False

    npc_id = (pursuit or {}).get("spawned_npc_id")
    if not pursuit or npc_id is None:
        return False  # no live hunter on this PC — nothing to collect

    hunter_name = pursuit.get("hunter_name") or H.hunter_for(int(victim_id))
    rid = room_id
    if rid is None:
        try:
            row = await db.get_npc(npc_id)
            if row:
                rid = row.get("room_id")
        except Exception:
            rid = None

    await _announce_room(session_mgr, rid, H.hunter_collected_line(hunter_name))

    try:
        await db.delete_npc(npc_id)
    except Exception:
        log.debug("[dsp_hunter_rt] collect: delete hunter %s failed", npc_id,
                  exc_info=True)
    try:
        await db.clear_dsp_pursuit(int(victim_id))
    except Exception:
        log.debug("[dsp_hunter_rt] collect: clear_dsp_pursuit failed for %s",
                  victim_id, exc_info=True)

    log.info("[dsp_hunter_rt] hunter %s (npc=%s) collected quarry %s; pursuit "
             "cleared (fresh rebuild next cycle)", hunter_name, npc_id, victim_id)
    return True
