# -*- coding: utf-8 -*-
"""
engine/wilderness_encounter_runtime.py — Lane A **Phase B** IO orchestration.

The encounter→spawner bridge. engine/creature_library.py stays PURE (loader +
faithful damage resolver + char_sheet/ai builders); this module owns the DB
spawn and the combat kick-off — the side-effecting half of Phase B.

Flow (called from parser/builtin_commands.py after a wilderness move's encounter
narrative fires):
  * a ``hostile`` / ``non_hostile`` encounter whose ``payload.npc_template``
    resolves in the creature library spawns the creature(s) via db.create_npc
    with FAITHFUL stats (build_creature_char_sheet injects the resolved
    natural-attack marker the combat engine now honors), then
  * for a ``hostile`` encounter, ground combat starts immediately — mirroring
    engine/dsp_hunter_runtime._start_hunter_combat / encounter_boarding so the
    fight begins the instant the creature appears, not on the player's next move.

Everything is failure-tolerant: encounters must never sink a move, so every
external call is guarded and a bad row simply yields no spawn.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from engine import creature_library as CL
from engine import creature_spoils as CS

log = logging.getLogger(__name__)


def _parse_json(raw) -> dict:
    """Tolerant ai_config_json parse (dict passthrough / bad-json → {})."""
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


async def _announce_room(session_mgr, room_id, line: str) -> None:
    """Send a line to every session in a room. Best-effort (never raises)."""
    if session_mgr is None or not line or room_id is None:
        return
    try:
        for sess in session_mgr.sessions_in_room(room_id):
            try:
                await sess.send_line(line)
            except Exception:
                log.debug("[wenc_rt] room announce send failed", exc_info=True)
    except Exception:
        log.debug("[wenc_rt] sessions_in_room failed", exc_info=True)


async def spawn_encounter_creatures(db, entry, room_id: int) -> list[int]:
    """Spawn the creature(s) named by a hostile/non_hostile encounter entry.

    Returns the list of spawned NPC ids (empty if nothing spawned). Pure of
    combat — testable with a fake db that records create_npc calls.
    """
    etype = getattr(entry, "type", "")
    if etype not in ("hostile", "non_hostile"):
        return []
    payload = getattr(entry, "payload", None) or {}
    tmpl = payload.get("npc_template")
    if not tmpl:
        return []
    creature = CL.get_creature(tmpl)
    if not creature:
        log.debug("[wenc_rt] encounter %s npc_template %r not in creature library",
                  getattr(entry, "id", "?"), tmpl)
        return []

    hostile = (etype == "hostile")
    count = CL.creature_spawn_count(creature, payload)
    species = creature.get("species", "Creature")
    description = creature.get("description", "")
    base_name = creature.get("name", str(tmpl))
    enc_id = getattr(entry, "id", "")

    sheet_json = json.dumps(CL.build_creature_char_sheet(creature))

    spawned: list[int] = []
    for i in range(count):
        name = base_name if count == 1 else f"{base_name} #{i + 1}"
        ai_json = json.dumps(
            CL.build_creature_ai_config(creature, encounter_id=enc_id,
                                        hostile=hostile))
        try:
            npc_id = await db.create_npc(
                name=name,
                room_id=int(room_id),
                species=species,
                description=description,
                char_sheet_json=sheet_json,
                ai_config_json=ai_json,
            )
            spawned.append(int(npc_id))
        except Exception:
            log.warning("[wenc_rt] create_npc failed for creature %r (#%d)",
                        tmpl, i + 1, exc_info=True)
            continue
    return spawned


async def _start_encounter_combat(db, session_mgr, room_id: int,
                                  npc_ids: list[int]) -> None:
    """Kick off ground combat between everyone in the room and the spawned
    hostile creature(s). Mirrors engine/dsp_hunter_runtime._start_hunter_combat:
    reuses the same combat primitives so the fight starts immediately."""
    if not npc_ids:
        return
    try:
        from engine.npc_combat_ai import build_npc_character, get_npc_behavior
        from engine.character import Character
        from parser.combat_commands import (
            _get_or_create_combat, _npc_behaviors,
            _broadcast_events, _auto_declare_npc_actions,
        )
    except Exception:
        log.warning("[wenc_rt] combat primitives import failed", exc_info=True)
        return

    try:
        chars = await db.get_characters_in_room(room_id)
    except Exception:
        log.debug("[wenc_rt] get_characters_in_room failed", exc_info=True)
        return
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
                log.debug("[wenc_rt] add player combatant failed", exc_info=True)

    for npc_id in npc_ids:
        try:
            npc_row = await db.get_npc(npc_id)
        except Exception:
            npc_row = None
        if not npc_row or combat.get_combatant(npc_id):
            continue
        npc_char = build_npc_character(dict(npc_row))
        if npc_char is not None:
            combatant = combat.add_combatant(npc_char)
            combatant.is_npc = True
            _npc_behaviors[npc_id] = get_npc_behavior(dict(npc_row))

    if new_combat:
        try:
            events = combat.roll_initiative()
            await _broadcast_events(events, session_mgr, room_id)
        except Exception:
            log.debug("[wenc_rt] initiative/broadcast failed", exc_info=True)

    class _MinCtx:
        def __init__(self, d, sm):
            self.db = d
            self.session_mgr = sm

    try:
        await _auto_declare_npc_actions(combat, _MinCtx(db, session_mgr))
    except Exception:
        log.debug("[wenc_rt] auto-declare failed", exc_info=True)


async def resolve_encounter_spawn(db, session_mgr, entry, room_id: int) -> list[int]:
    """Top-level bridge: spawn the creature(s) and (if hostile) start combat.

    Called from the wilderness move path. Returns spawned ids. Never raises —
    the caller also guards, but we defend in depth so encounters can't sink a
    move.
    """
    try:
        npc_ids = await spawn_encounter_creatures(db, entry, room_id)
    except Exception:
        log.warning("[wenc_rt] spawn_encounter_creatures failed", exc_info=True)
        return []
    if npc_ids and getattr(entry, "type", "") == "hostile":
        try:
            await _start_encounter_combat(db, session_mgr, room_id, npc_ids)
        except Exception:
            log.warning("[wenc_rt] _start_encounter_combat failed", exc_info=True)
    return npc_ids


async def on_wild_creature_killed(db, npc_id, killer_char, room_id,
                                  session_mgr=None) -> bool:
    """Combat-death hook: field-dress a downed **wilderness-encounter creature**.

    Mirrors ``dsp_hunter_runtime.on_dsp_hunter_killed`` — fires for every dead
    combatant in the combat death-sweep, but is a cheap no-op (returns False)
    for any NPC that is not a runtime-spawned wilderness creature. The gate is
    the ``is_wilderness_encounter`` marker, which is stamped *only* by
    ``creature_library.build_creature_ai_config`` at spawn, so this hook can
    never touch a persistent world NPC.

    For a wilderness creature it:

      * grants **resource spoils** to ``killer_char`` when the creature carries
        an authored ``harvest`` block AND the killer passes a Survival
        field-dressing check. Spoils land in ``inventory.resources`` via
        ``crafting.add_resource`` — the existing crafting SINK — so this adds a
        faucet that flows straight into a live sink, never a raw-credit faucet
        (economy_audit_v2 §1 faucet/sink discipline);
      * **always despawns the carcass** afterwards. A wilderness creature is a
        transient encounter spawn (like the DSP hunter), and nothing else
        removes its row, so this hook owns that cleanup — otherwise dead
        creatures would litter the room.

    Returns True if it handled a wilderness creature (attempted/granted spoils
    and/or despawned), False if the NPC wasn't one. Idempotent: a row already
    removed earlier in the sweep (e.g. by the anomaly hook) → ``get_npc``
    returns None → returns False, with no double-grant. Prestige/craft-economy
    domain: confers no credits.
    """
    try:
        row = await db.get_npc(npc_id)
    except Exception:
        return False
    if not row:
        return False

    ai = _parse_json(row.get("ai_config_json"))
    if not ai.get("is_wilderness_encounter"):
        return False  # not a runtime wilderness-creature spawn — leave it alone

    creature_name = row.get("name") or "creature"
    creature_id = ai.get("creature_id") or ""
    creature = CL.get_creature(creature_id) if creature_id else None

    killer_name = (killer_char or {}).get("name", "Someone") \
        if isinstance(killer_char, dict) else "Someone"

    announce = ""
    granted = False
    # ── Field-dressing (spoils) ──────────────────────────────────────────────
    # Only when the creature has an authored harvest block AND we have a real
    # killer dict to roll for + award. A killer-less death (creature-vs-creature
    # or an environmental kill) silently despawns the carcass with no grant.
    if creature is not None and CS.creature_has_spoils(creature) \
            and isinstance(killer_char, dict):
        sc = None
        try:
            from engine.skill_checks import perform_skill_check
            sc = perform_skill_check(
                killer_char, CS.SPOILS_SKILL,
                CS.spoils_difficulty(creature),
                auto_consume_lead=False,
            )
        except Exception:
            log.warning("[wenc_rt] spoils skill check failed", exc_info=True)

        if sc is not None and sc.success:
            spoils = CS.resolve_spoils(creature, sc.margin)
            if spoils:
                try:
                    from engine.crafting import add_resource
                    add_resource(killer_char, spoils["resource_type"],
                                 spoils["quantity"], spoils["quality"])
                    await db.save_character(
                        killer_char["id"], inventory=killer_char["inventory"])
                    announce = CS.spoils_success_line(
                        killer_name, creature_name, spoils)
                    granted = True
                except Exception:
                    # Same posture as engine/harvest.py: log and continue —
                    # the carcass is still despawned below.
                    log.warning("[wenc_rt] spoils grant/persist failed",
                                exc_info=True)
        elif sc is not None:
            announce = CS.spoils_failure_line(killer_name, creature_name)

    # ── Despawn the carcass (always, for wilderness spawns) ──────────────────
    try:
        await db.delete_npc(npc_id)
    except Exception:
        log.debug("[wenc_rt] delete spoiled creature failed for %s", npc_id,
                  exc_info=True)

    if announce:
        await _announce_room(session_mgr, room_id, announce)
    log.info("[wenc_rt] wilderness creature %s (npc=%s) killed by %s; "
             "spoils granted=%s", creature_name, npc_id, killer_name, granted)
    return True
