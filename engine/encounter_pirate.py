# -*- coding: utf-8 -*-
"""
engine/encounter_pirate.py — Pirate Attack Encounter
Space Overhaul v3, Drop 4

Four-choice branching: Pay / Negotiate / Fight / Flee.
Fight and Flee both promote the pirate to active combatant via Drop 3 NPC AI.
"""

import json
import logging
import random
import time

from engine.starships import SpaceRange

log = logging.getLogger(__name__)

AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
RST = "\033[0m"

DEMAND_MIN = 500
DEMAND_MAX = 3000
NEGOTIATE_DIFFICULTY = 15
PIRATE_DEADLINE = 60


async def pirate_setup(encounter, manager, db, session_mgr, **kwargs):
    from engine.space_encounters import EncounterChoice
    pirate_name = encounter.context.get("pirate_name", "Unregistered fighter")
    demand = int(round(random.randint(DEMAND_MIN, DEMAND_MAX) / 100) * 100)
    encounter.context["demand_credits"] = demand
    encounter.prompt = (
        f"[PIRATE] {pirate_name} is hailing you.\n"
        f"  \"{RED}Cut your engines. Transfer {demand:,} credits or we start shooting.{RST}\"")
    encounter.deciding_station = "any"
    encounter.choices = [
        EncounterChoice(key="pay", label="Pay",
            description=f"Transfer {demand:,} credits. The pirate leaves.",
            risk="none", icon="credit-card"),
        EncounterChoice(key="negotiate", label="Negotiate",
            description="Bargain check to reduce the demand.",
            risk="medium", icon="message-circle", station_hint="commander",
            skill="Bargain", difficulty=f"Moderate ({NEGOTIATE_DIFFICULTY})"),
        EncounterChoice(key="fight", label="Fight",
            description="Weapons hot. Engage the pirate.",
            risk="high", icon="crosshair", station_hint="gunner"),
        EncounterChoice(key="flee", label="Flee",
            description="Hit the throttle. The pirate will pursue.",
            risk="high", icon="rocket", station_hint="pilot",
            skill="Space Transports", difficulty="Opposed piloting"),
    ]
    encounter.choice_deadline = time.time() + PIRATE_DEADLINE


async def pirate_pay(encounter, manager, db, session_mgr, **kwargs):
    char_id = kwargs.get("char_id", 0)
    pirate_name = encounter.context.get("pirate_name", "the pirate")
    demand = encounter.context.get("demand_credits", 1000)
    if not char_id:
        manager.resolve(encounter, outcome="pay_failed")
        return
    try:
        char = await db.get_character(char_id)
        if char:
            char = dict(char)
            credits = char.get("credits", 0)
            if credits < demand:
                await manager.broadcast_to_bridge(encounter,
                    f"\n  {RED}[COMMS]{RST} \"Not enough credits? Unfortunate.\"\n"
                    f"  {RED}[ALERT]{RST} {pirate_name} opens fire!", session_mgr)
                await _start_pirate_combat(encounter, manager, db, session_mgr)
                return
            await db.save_character(char_id, credits=credits - demand)
            await manager.broadcast_to_bridge(encounter,
                f"\n  {AMBER}[COMMS]{RST} You transfer {demand:,} credits.\n"
                f"  {DIM}\"Pleasure doing business.\"{RST}\n"
                f"  {GREEN}[SENSORS]{RST} {pirate_name} breaks off.\n"
                f"  {DIM}Balance: {credits - demand:,}cr.{RST}", session_mgr)
            manager.resolve(encounter, outcome="pay_success")
    except Exception as e:
        log.warning("[pirate] pay error: %s", e)
        manager.resolve(encounter, outcome="pay_error")


async def pirate_negotiate(encounter, manager, db, session_mgr, **kwargs):
    char_id = kwargs.get("char_id", 0)
    pirate_name = encounter.context.get("pirate_name", "the pirate")
    demand = encounter.context.get("demand_credits", 1000)
    result = await _skill_check(char_id, "bargain", NEGOTIATE_DIFFICULTY, db)

    if result.get("critical"):
        reduced = max(100, demand // 4)
        await manager.broadcast_to_bridge(encounter,
            f"\n  {GREEN}[COMMS]{RST} {pirate_name}: \"Ha! You've got nerve.\"\n"
            f"  \"{reduced:,} credits and I'll throw in some intel. "
            f"Derelict in the next sector — plenty of salvage.\"\n"
            f"  {DIM}(Bargain: {result['roll']} vs {NEGOTIATE_DIFFICULTY} — critical!){RST}",
            session_mgr)
        ok = await _deduct_credits(char_id, reduced, db)
        if ok:
            await manager.broadcast_to_bridge(encounter,
                f"  {AMBER}Transferred {reduced:,}cr.{RST} {pirate_name} breaks off.",
                session_mgr)
            try:
                from engine.space_anomalies import spawn_anomalies_for_zone
                from engine.npc_space_traffic import ZONES
                zone = ZONES.get(encounter.zone_id)
                if zone:
                    spawn_anomalies_for_zone(encounter.zone_id, zone.type.value,
                                             security="lawless")
            except Exception:
                log.warning("[pirate] anomaly spawn on negotiate_critical failed", exc_info=True)
            manager.resolve(encounter, outcome="negotiate_critical")
        else:
            await manager.broadcast_to_bridge(encounter,
                f"  {RED}Can't afford even the discount. {pirate_name} attacks!{RST}",
                session_mgr)
            await _start_pirate_combat(encounter, manager, db, session_mgr)

    elif result["success"]:
        reduced = max(100, demand // 2)
        await manager.broadcast_to_bridge(encounter,
            f"\n  {AMBER}[COMMS]{RST} \"{reduced:,} credits. Final offer.\"\n"
            f"  {DIM}(Bargain: {result['roll']} vs {NEGOTIATE_DIFFICULTY} — success){RST}",
            session_mgr)
        ok = await _deduct_credits(char_id, reduced, db)
        if ok:
            await manager.broadcast_to_bridge(encounter,
                f"  {AMBER}Transferred {reduced:,}cr.{RST} {pirate_name} breaks off.",
                session_mgr)
            manager.resolve(encounter, outcome="negotiate_success")
        else:
            await manager.broadcast_to_bridge(encounter,
                f"  {RED}Can't pay. {pirate_name} attacks!{RST}", session_mgr)
            await _start_pirate_combat(encounter, manager, db, session_mgr)
    else:
        await manager.broadcast_to_bridge(encounter,
            f"\n  {RED}[COMMS]{RST} \"{pirate_name}: You're wasting my time. "
            f"Light 'em up.\"\n"
            f"  {DIM}(Bargain: {result['roll']} vs {NEGOTIATE_DIFFICULTY} — failed){RST}",
            session_mgr)
        await _start_pirate_combat(encounter, manager, db, session_mgr)


async def pirate_fight(encounter, manager, db, session_mgr, **kwargs):
    pirate_name = encounter.context.get("pirate_name", "the pirate")
    await manager.broadcast_to_bridge(encounter,
        f"\n  {RED}[COMBAT]{RST} \"You want a fight? You got one!\"\n"
        f"  {AMBER}[HELM]{RST} Weapons hot — engaging {pirate_name}!", session_mgr)
    await _start_pirate_combat(encounter, manager, db, session_mgr)


async def pirate_flee(encounter, manager, db, session_mgr, **kwargs):
    pirate_name = encounter.context.get("pirate_name", "the pirate")
    await manager.broadcast_to_bridge(encounter,
        f"\n  {AMBER}[HELM]{RST} Full throttle! Breaking away!\n"
        f"  {RED}[SENSORS]{RST} {pirate_name} is pursuing!", session_mgr)
    await _start_pirate_combat(encounter, manager, db, session_mgr,
                                profile="pursuit")


async def pirate_timeout(encounter, manager, db, session_mgr, **kwargs):
    pirate_name = encounter.context.get("pirate_name", "the pirate")
    await manager.broadcast_to_bridge(encounter,
        f"\n  {RED}[COMMS]{RST} \"{pirate_name}: Time's up. Open fire!\"\n",
        session_mgr)
    await _start_pirate_combat(encounter, manager, db, session_mgr)


# ── Helpers ──────────────────────────────────────────────────────────────────

async def _start_pirate_combat(encounter, manager, db, session_mgr,
                                profile="aggressive"):
    npc_ship_id = encounter.npc_ship_id
    if not npc_ship_id:
        manager.resolve(encounter, outcome="combat_no_npc")
        return
    from engine.npc_space_combat_ai import get_npc_combat_manager
    from engine.npc_space_traffic import get_traffic_manager, TRAFFIC_SHIP_TEMPLATES, TrafficArchetype
    ts = get_traffic_manager().get_ship(npc_ship_id)
    if not ts:
        manager.resolve(encounter, outcome="combat_no_npc")
        return
    templates = TRAFFIC_SHIP_TEMPLATES.get(TrafficArchetype.PIRATE, [])
    template_key = templates[0].get("template", "z95") if templates else "z95"
    crew_skill = templates[0].get("crew_skill", "4D") if templates else "4D"

    combat_mgr = get_npc_combat_manager()
    c = combat_mgr.promote_to_combat(
        npc_ship_id=npc_ship_id,
        target_ship_id=encounter.target_ship_id,
        target_bridge_room=encounter.target_bridge_room,
        zone_id=encounter.zone_id,
        template_key=template_key,
        display_name=ts.display_name,
        crew_skill=crew_skill,
        profile=profile,
        starting_range=SpaceRange.SHORT,
    )
    from engine.starships import get_ship_registry
    from engine.dice import DicePool
    tmpl = get_ship_registry().get(template_key)
    if tmpl:
        c.hull_max_pips = DicePool.parse(tmpl.hull).total_pips()
        c.scale_value = tmpl.scale_value

    await manager.broadcast_to_bridge(encounter,
        f"  {RED}[COMBAT]{RST} {ts.display_name} has engaged!\n"
        f"  Use 'fire', 'flee', 'evade', or 'hyperspace'.\n"
        f"  {DIM}Destroy them for a bounty + salvage.{RST}", session_mgr)
    encounter.context["combat_active"] = True


async def _skill_check(char_id, skill_name, difficulty, db):
    try:
        from engine.skill_checks import perform_skill_check
        r = await perform_skill_check(char_id=char_id, skill_name=skill_name,
                                       difficulty=difficulty, db=db)
        return {"success": r.success, "critical": getattr(r, "critical", False),
                "roll": getattr(r, "roll_total", 0), "difficulty": difficulty}
    except Exception:
        roll = sum(random.randint(1, 6) for _ in range(3))
        return {"success": roll >= difficulty, "critical": roll >= difficulty + 10,
                "roll": roll, "difficulty": difficulty}


async def _deduct_credits(char_id, amount, db):
    try:
        char = await db.get_character(char_id)
        if char:
            credits = dict(char).get("credits", 0)
            if credits >= amount:
                await db.save_character(char_id, credits=credits - amount)
                return True
    except Exception as e:
        log.warning("[pirate] deduct: %s", e)
    return False


def register_pirate_handlers(enc_manager):
    enc_manager.register_handler("pirate", "setup",             pirate_setup)
    enc_manager.register_handler("pirate", "choice_pay",        pirate_pay)
    enc_manager.register_handler("pirate", "choice_negotiate",  pirate_negotiate)
    enc_manager.register_handler("pirate", "choice_fight",      pirate_fight)
    enc_manager.register_handler("pirate", "choice_flee",       pirate_flee)
    enc_manager.register_handler("pirate", "timeout",           pirate_timeout)
    log.info("[encounters] pirate encounter handlers registered")
