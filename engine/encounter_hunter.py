# -*- coding: utf-8 -*-
"""
engine/encounter_hunter.py — Bounty Hunter Pursuit Encounter
Space Overhaul v3, Drop 7

Triggered when a bounty hunter NPC detects its target in a zone.
Four-choice branching: Surrender / Fight / Flee / Negotiate.

Fight and Flee promote the hunter to active combatant (pursuit profile).
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

HUNTER_DEADLINE = 45  # seconds — hunters are impatient
NEGOTIATE_DIFFICULTY = 20  # Very Difficult — hunters don't negotiate easily


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


async def hunter_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    hunter_name = enc.context.get("hunter_name", "Pursuit vessel")
    target_name = enc.context.get("target_name", "you")
    bounty_amount = enc.context.get("bounty_amount", 0)

    bounty_str = f" Bounty: {bounty_amount:,} credits." if bounty_amount else ""

    enc.prompt = (
        f"[BOUNTY HUNTER] {hunter_name} has found you.\n"
        f"  \"{RED}I have a contract for {target_name}. "
        f"Surrender and this stays clean.{bounty_str}{RST}\"")
    enc.deciding_station = "any"
    enc.choices = [
        EncounterChoice(key="surrender", label="Surrender",
            description="Give up. Bounty collected. You lose credits, not your life.",
            risk="none", icon="flag"),
        EncounterChoice(key="fight", label="Fight",
            description="Weapons hot. The hunter is skilled.",
            risk="high", icon="crosshair"),
        EncounterChoice(key="flee", label="Flee",
            description="Run. The hunter will pursue aggressively.",
            risk="high", icon="rocket", station_hint="pilot",
            skill="Space Transports", difficulty="Opposed piloting"),
        EncounterChoice(key="negotiate", label="Pay Off the Bounty",
            description=f"Bargain check (Very Difficult, {NEGOTIATE_DIFFICULTY}). Expensive.",
            risk="medium", icon="credit-card",
            skill="Bargain", difficulty=f"Very Difficult ({NEGOTIATE_DIFFICULTY})"),
    ]
    enc.choice_deadline = time.time() + HUNTER_DEADLINE


async def hunter_surrender(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    hunter_name = enc.context.get("hunter_name", "the hunter")
    bounty_amount = enc.context.get("bounty_amount", 0)

    # Deduct bounty amount from player credits
    penalty = max(bounty_amount, 500)
    try:
        char = await db.get_character(cid)
        if char:
            credits = dict(char).get("credits", 0)
            lost = min(credits, penalty)
            await db.save_character(cid, credits=credits - lost)
            await mgr.broadcast_to_bridge(enc,
                f"\n  {AMBER}[COMMS]{RST} You power down weapons and submit.\n"
                f"  {DIM}{hunter_name}: \"Smart. The bounty's collected.\"{RST}\n"
                f"  {RED}Lost {lost:,} credits to bounty collection.{RST}\n"
                f"  {GREEN}[SENSORS]{RST} {hunter_name} breaks off.", sm)
            # Clear bounty on character
            await db.save_character(cid, bounty=0)
    except Exception as e:
        log.warning("[hunter] surrender error: %s", e)
    mgr.resolve(enc, outcome="hunter_surrender")


async def hunter_fight(enc, mgr, db, sm, **kw):
    hunter_name = enc.context.get("hunter_name", "the hunter")
    await mgr.broadcast_to_bridge(enc,
        f"\n  {RED}[COMBAT]{RST} \"{hunter_name}: Your choice. Lethal force authorized.\"\n"
        f"  {AMBER}[HELM]{RST} Weapons hot!", sm)
    await _start_hunter_combat(enc, mgr, db, sm, "pursuit")


async def hunter_flee(enc, mgr, db, sm, **kw):
    hunter_name = enc.context.get("hunter_name", "the hunter")
    await mgr.broadcast_to_bridge(enc,
        f"\n  {AMBER}[HELM]{RST} Full throttle!\n"
        f"  {RED}[SENSORS]{RST} {hunter_name} is closing fast — pursuit profile!", sm)
    await _start_hunter_combat(enc, mgr, db, sm, "pursuit")


async def hunter_negotiate(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    hunter_name = enc.context.get("hunter_name", "the hunter")
    bounty_amount = enc.context.get("bounty_amount", 0)

    r = await _skill_check(cid, "bargain", NEGOTIATE_DIFFICULTY, db)

    if r.get("critical"):
        # Critical: hunter respects you, takes a reduced payment, gives info
        payment = max(200, bounty_amount // 4)
        try:
            char = await db.get_character(cid)
            if char:
                credits = dict(char).get("credits", 0)
                paid = min(credits, payment)
                await db.save_character(cid, credits=credits - paid, bounty=0)
        except Exception:
            paid = 0
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[COMMS]{RST} {hunter_name}: \"You've got guts. "
            f"{paid:,} credits and I'll report the bounty as collected.\"\n"
            f"  {CYAN}[INTEL]{RST} \"And a tip — there's a price on someone "
            f"else in the next sector. Maybe you want the contract yourself.\"\n"
            f"  {DIM}(Bargain: {r['roll']} vs {NEGOTIATE_DIFFICULTY} — critical!){RST}", sm)
        mgr.resolve(enc, outcome="hunter_negotiate_critical")

    elif r["success"]:
        payment = max(300, bounty_amount // 2)
        try:
            char = await db.get_character(cid)
            if char:
                credits = dict(char).get("credits", 0)
                paid = min(credits, payment)
                await db.save_character(cid, credits=credits - paid, bounty=0)
        except Exception:
            paid = 0
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[COMMS]{RST} {hunter_name}: \"Fine. {paid:,} credits "
            f"and we never met. Deal?\"\n"
            f"  {GREEN}[SENSORS]{RST} {hunter_name} breaks off.\n"
            f"  {DIM}(Bargain: {r['roll']} vs {NEGOTIATE_DIFFICULTY} — success){RST}", sm)
        mgr.resolve(enc, outcome="hunter_negotiate_success")

    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[COMMS]{RST} {hunter_name}: \"I don't negotiate with "
            f"targets. Weapons hot.\"\n"
            f"  {DIM}(Bargain: {r['roll']} vs {NEGOTIATE_DIFFICULTY} — failed){RST}", sm)
        await _start_hunter_combat(enc, mgr, db, sm, "pursuit")


async def hunter_timeout(enc, mgr, db, sm, **kw):
    hunter_name = enc.context.get("hunter_name", "the hunter")
    await mgr.broadcast_to_bridge(enc,
        f"\n  {RED}[COMMS]{RST} {hunter_name}: \"Surrender refused. Engaging.\"\n", sm)
    await _start_hunter_combat(enc, mgr, db, sm, "pursuit")


async def _start_hunter_combat(enc, mgr, db, sm, profile="pursuit"):
    npc_ship_id = enc.npc_ship_id
    if not npc_ship_id:
        mgr.resolve(enc, outcome="combat_no_npc")
        return
    from engine.npc_space_combat_ai import get_npc_combat_manager
    from engine.npc_space_traffic import get_traffic_manager, TRAFFIC_SHIP_TEMPLATES, TrafficArchetype
    ts = get_traffic_manager().get_ship(npc_ship_id)
    if not ts:
        mgr.resolve(enc, outcome="combat_no_npc")
        return
    templates = TRAFFIC_SHIP_TEMPLATES.get(TrafficArchetype.BOUNTY_HUNTER, [])
    template_key = templates[0].get("template", "firespray") if templates else "firespray"
    crew_skill = templates[0].get("crew_skill", "5D") if templates else "5D"

    c = get_npc_combat_manager().promote_to_combat(
        npc_ship_id=npc_ship_id, target_ship_id=enc.target_ship_id,
        target_bridge_room=enc.target_bridge_room, zone_id=enc.zone_id,
        template_key=template_key, display_name=ts.display_name,
        crew_skill=crew_skill, profile=profile, starting_range=SpaceRange.SHORT)
    from engine.starships import get_ship_registry
    from engine.dice import DicePool
    tmpl = get_ship_registry().get(template_key)
    if tmpl:
        c.hull_max_pips = DicePool.parse(tmpl.hull).total_pips()
        c.scale_value = tmpl.scale_value
    enc.context["combat_active"] = True
    await mgr.broadcast_to_bridge(enc,
        f"  {RED}[COMBAT]{RST} {ts.display_name} engages!\n"
        f"  Use 'fire', 'flee', 'evade', or 'hyperspace'.\n"
        f"  {DIM}The hunter is skilled (5D) and won't give up easily.{RST}", sm)


def register_hunter_handlers(enc_manager):
    h = enc_manager.register_handler
    h("hunter", "setup",              hunter_setup)
    h("hunter", "choice_surrender",   hunter_surrender)
    h("hunter", "choice_fight",       hunter_fight)
    h("hunter", "choice_flee",        hunter_flee)
    h("hunter", "choice_negotiate",   hunter_negotiate)
    h("hunter", "timeout",            hunter_timeout)
    log.info("[encounters] bounty hunter handlers registered")
