# -*- coding: utf-8 -*-
"""
engine/encounter_anomaly.py — Anomaly Encounter Completion
Space Overhaul v3, Drop 8

Encounter handlers for 6 non-derelict anomaly types.
Triggered by 'investigate <anomaly_id>' on fully-resolved anomalies.

Types: distress, cache, pirates, mineral_vein, imperial, mynock
(derelict already handled by 'salvage' command)
"""

import json
import logging
import random
import time

from engine.json_safe import load_ship_systems
from engine.starships import SpaceRange

log = logging.getLogger(__name__)

AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
RST = "\033[0m"


# ── Skill check helper ──────────────────────────────────────────────────────

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


async def _award_credits(char_id, amount, db):
    try:
        char = await db.get_character(char_id)
        if char:
            await db.save_character(char_id, credits=dict(char).get("credits", 0) + amount)
    except Exception as e:
        log.warning("[anomaly] credit award: %s", e)


async def _award_resources(char_id, rtype, qty, quality, db):
    try:
        char = await db.get_character(char_id)
        if char:
            from engine.crafting import add_resource
            add_resource(dict(char), rtype, qty, float(quality))
            await db.save_character(char_id)
    except Exception as e:
        log.warning("[anomaly] resource award: %s", e)


async def _spawn_pirate_combat(encounter, manager, db, session_mgr,
                                profile="aggressive", starting_range=SpaceRange.SHORT):
    from engine.npc_space_combat_ai import get_npc_combat_manager
    from engine.npc_space_traffic import get_traffic_manager, TRAFFIC_SHIP_TEMPLATES, TrafficArchetype
    ts = await get_traffic_manager().spawn_pirate_for_encounter(encounter.zone_id, db, session_mgr)
    if not ts:
        await manager.broadcast_to_bridge(encounter,
            f"  {AMBER}[SENSORS]{RST} The pirates scatter before you can engage.", session_mgr)
        manager.resolve(encounter, outcome="pirates_scattered")
        return
    templates = TRAFFIC_SHIP_TEMPLATES.get(TrafficArchetype.PIRATE, [])
    template_key = templates[0].get("template", "z95") if templates else "z95"
    crew_skill = templates[0].get("crew_skill", "4D") if templates else "4D"
    c = get_npc_combat_manager().promote_to_combat(
        npc_ship_id=ts.ship_id, target_ship_id=encounter.target_ship_id,
        target_bridge_room=encounter.target_bridge_room, zone_id=encounter.zone_id,
        template_key=template_key, display_name=ts.display_name,
        crew_skill=crew_skill, profile=profile, starting_range=starting_range)
    from engine.starships import get_ship_registry
    from engine.dice import DicePool
    tmpl = get_ship_registry().get(template_key)
    if tmpl:
        c.hull_max_pips = DicePool.parse(tmpl.hull).total_pips()
        c.scale_value = tmpl.scale_value
    encounter.npc_ship_id = ts.ship_id
    encounter.context["combat_active"] = True
    await manager.broadcast_to_bridge(encounter,
        f"  {RED}[COMBAT]{RST} {ts.display_name} engages!\n"
        f"  Use 'fire', 'flee', 'evade', or 'hyperspace'.", session_mgr)


# ══════════════════════════════════════════════════════════════════════════════
# DISTRESS SIGNAL
# ══════════════════════════════════════════════════════════════════════════════

async def distress_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = (f"[DISTRESS SIGNAL] Emergency broadcast.\n"
                  f"  \"{AMBER}Mayday — engines critical, life support failing.{RST}\"")
    enc.context["is_trap"] = random.random() < 0.30
    enc.choices = [
        EncounterChoice(key="respond", label="Respond", description="Move in to assist.",
            risk="medium", icon="life-buoy", skill="Perception", difficulty="Moderate (15)"),
        EncounterChoice(key="scan_first", label="Scan First",
            description="Sensors sweep before committing.", risk="low", icon="search",
            skill="Sensors", difficulty="Moderate (15)"),
        EncounterChoice(key="ignore", label="Ignore", description="Not your problem.",
            risk="none", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 90

async def distress_respond(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    if enc.context.get("is_trap"):
        r = await _skill_check(cid, "perception", 15, db)
        if r["success"]:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {AMBER}[SENSORS]{RST} Signal is looping — no life signs. It's a trap!\n"
                f"  {DIM}(Perception: {r['roll']} vs 15 — detected!){RST}", sm)
            await _spawn_pirate_combat(enc, mgr, db, sm, "aggressive", SpaceRange.SHORT)
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {RED}[ALERT]{RST} AMBUSH! Pirate from the debris field!\n"
                f"  {DIM}(Perception: {r['roll']} vs 15 — ambushed!){RST}", sm)
            await _spawn_pirate_combat(enc, mgr, db, sm, "ambush", SpaceRange.CLOSE)
    else:
        reward = random.randint(500, 2000)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[SENSORS]{RST} Vessel located — crew alive.\n"
            f"  {CYAN}[REWARD]{RST} Grateful crew transfers {reward:,} credits.", sm)
        await _award_credits(cid, reward, db)
        mgr.resolve(enc, outcome="distress_rescued")

async def distress_scan_first(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "sensors", 15, db)
    if r["success"]:
        if enc.context.get("is_trap"):
            await mgr.broadcast_to_bridge(enc,
                f"\n  {RED}[SENSORS]{RST} Cold contacts in debris — pirate trap!\n"
                f"  {DIM}(Sensors: {r['roll']} vs 15 — trap revealed){RST}", sm)
            mgr.resolve(enc, outcome="distress_trap_detected")
        else:
            reward = random.randint(500, 2000)
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[SENSORS]{RST} Confirmed genuine. Rescue successful.\n"
                f"  {CYAN}[REWARD]{RST} {reward:,} credits received.", sm)
            await _award_credits(cid, reward, db)
            mgr.resolve(enc, outcome="distress_rescued_safe")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[SENSORS]{RST} Scan inconclusive. Your call, Captain.\n"
            f"  {DIM}(Sensors: {r['roll']} vs 15 — no clear read){RST}", sm)
        enc.chosen_key = ""  # Allow re-choice

async def distress_ignore(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc, f"\n  {DIM}Signal fades as you continue.{RST}", sm)
    mgr.resolve(enc, outcome="distress_ignored")

async def distress_timeout(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc, f"\n  {DIM}Signal fades to static.{RST}", sm)
    mgr.resolve(enc, outcome="distress_timeout")


# ══════════════════════════════════════════════════════════════════════════════
# HIDDEN CACHE
# ══════════════════════════════════════════════════════════════════════════════

async def cache_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = f"[HIDDEN CACHE] Armored container — cold and dark.\n  {DIM}Someone hid this here.{RST}"
    enc.choices = [
        EncounterChoice(key="crack", label="Crack It Open",
            description="Security bypass. Computer Programming, Difficult (20).",
            risk="medium", icon="unlock", skill="Computer Prog/Repair", difficulty="Difficult (20)"),
        EncounterChoice(key="leave", label="Leave It", description="Not worth the risk.",
            risk="none", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 120

async def cache_crack(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "computer_programming_repair", 20, db)
    if r.get("critical"):
        cr = random.randint(3000, 8000)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[ENGINEERING]{RST} Lock bypassed — jackpot!\n"
            f"  {GREEN}[CARGO]{RST} Military-grade components + {cr:,} credits!\n"
            f"  {DIM}(Computer: {r['roll']} vs 20 — critical!){RST}", sm)
        await _award_credits(cid, cr, db)
        await _award_resources(cid, "rare", random.randint(2, 4), random.randint(70, 95), db)
        mgr.resolve(enc, outcome="cache_jackpot")
    elif r["success"]:
        cr = random.randint(1000, 3000)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[ENGINEERING]{RST} Lock bypassed. {cr:,} credits + supplies.\n"
            f"  {DIM}(Computer: {r['roll']} vs 20 — success){RST}", sm)
        await _award_credits(cid, cr, db)
        await _award_resources(cid, "composite", random.randint(2, 5), random.randint(50, 75), db)
        mgr.resolve(enc, outcome="cache_opened")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[ENGINEERING]{RST} Countermeasure! Container self-destructs.\n"
            f"  {DIM}(Computer: {r['roll']} vs 20 — failed){RST}", sm)
        mgr.resolve(enc, outcome="cache_trapped")

async def cache_leave(enc, mgr, db, sm, **kw):
    mgr.resolve(enc, outcome="cache_left")


# ══════════════════════════════════════════════════════════════════════════════
# MINERAL VEIN
# ══════════════════════════════════════════════════════════════════════════════

async def mineral_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = f"[MINERAL VEIN] High-grade ore exposed by collision.\n  {DIM}Elevated heavy metal concentrations.{RST}"
    enc.choices = [
        EncounterChoice(key="mine", label="Extract", description="Technical check for ore.",
            risk="low", icon="pickaxe", skill="Technical", difficulty="Moderate (12)"),
        EncounterChoice(key="skip", label="Pass", description="Not worth the time.",
            risk="none", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 120

async def mineral_mine(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "technical", 12, db)
    if r["success"]:
        qty = random.randint(8, 15) if r.get("critical") else random.randint(4, 10)
        qual = random.randint(70, 95) if r.get("critical") else random.randint(40, 80)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[MINING]{RST} {'Excellent yield! ' if r.get('critical') else ''}"
            f"Extracted {qty} units of ore (quality {qual}).\n"
            f"  {DIM}(Technical: {r['roll']} vs 12){RST}", sm)
        await _award_resources(cid, "metal", qty, qual, db)
        mgr.resolve(enc, outcome="mineral_harvested")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[MINING]{RST} Can't cut through. Vein too deep.\n"
            f"  {DIM}(Technical: {r['roll']} vs 12 — failed){RST}", sm)
        mgr.resolve(enc, outcome="mineral_failed")

async def mineral_skip(enc, mgr, db, sm, **kw):
    mgr.resolve(enc, outcome="mineral_skipped")


# ══════════════════════════════════════════════════════════════════════════════
# IMPERIAL DEAD DROP
# ══════════════════════════════════════════════════════════════════════════════

async def imperial_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = f"[IMPERIAL DEAD DROP] Encrypted data container.\n  {DIM}Imperial cipher signature.{RST}"
    enc.choices = [
        EncounterChoice(key="slice", label="Slice It",
            description="Computer Programming, Difficult (20). Failure triggers alarm.",
            risk="high", icon="terminal", skill="Computer Prog/Repair", difficulty="Difficult (20)"),
        EncounterChoice(key="grab", label="Take Unopened",
            description="Sell to a fence later. Less reward, no risk.",
            risk="low", icon="package"),
        EncounterChoice(key="leave", label="Leave It",
            description="Imperial intel is trouble.", risk="none", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 120

async def imperial_slice(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "computer_programming_repair", 20, db)
    if r["success"]:
        cr = random.randint(2000, 6000)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[SLICING]{RST} Encryption broken! Patrol routes + credit authorization.\n"
            f"  {CYAN}[INTEL]{RST} Data worth {cr:,} credits.\n"
            f"  {DIM}(Computer: {r['roll']} vs 20){RST}", sm)
        await _award_credits(cid, cr, db)
        mgr.resolve(enc, outcome="imperial_decoded")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[SLICING]{RST} Tamper alarm! Imperial distress beacon activated!\n"
            f"  {RED}[SENSORS]{RST} Patrol inbound!\n"
            f"  {DIM}(Computer: {r['roll']} vs 20 — failed){RST}", sm)
        mgr.resolve(enc, outcome="imperial_alarm")

async def imperial_grab(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    cr = random.randint(500, 1500)
    await mgr.broadcast_to_bridge(enc,
        f"\n  {AMBER}[CARGO]{RST} Container secured. A fence would pay {cr:,} credits.", sm)
    await _award_credits(cid, cr, db)
    mgr.resolve(enc, outcome="imperial_grabbed")

async def imperial_leave(enc, mgr, db, sm, **kw):
    mgr.resolve(enc, outcome="imperial_left")


# ══════════════════════════════════════════════════════════════════════════════
# MYNOCK COLONY
# ══════════════════════════════════════════════════════════════════════════════

async def mynock_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = f"[MYNOCK COLONY] Biological mass detaching from asteroid.\n  {AMBER}Heading for your power cables!{RST}"
    enc.choices = [
        EncounterChoice(key="evade", label="Evade", description="Piloting check to dodge.",
            risk="low", icon="zap", skill="Space Transports", difficulty="Easy (10)"),
        EncounterChoice(key="blast", label="Blast Them", description="Turret fire. Auto-clear.",
            risk="none", icon="crosshair"),
    ]
    enc.choice_deadline = time.time() + 30

async def mynock_evade(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "space_transports", 10, db)
    if r["success"]:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[HELM]{RST} Barrel roll — none attached!\n"
            f"  {DIM}(Piloting: {r['roll']} vs 10){RST}", sm)
        mgr.resolve(enc, outcome="mynock_evaded")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[ALERT]{RST} Mynocks latched! Sensors going dark.\n"
            f"  {DIM}(Piloting: {r['roll']} vs 10 — failed){RST}\n"
            f"  {AMBER}Use 'damcon' to repair sensors.{RST}", sm)
        if enc.target_ship_id:
            ship = await db.get_ship(enc.target_ship_id)
            if ship:
                sd = load_ship_systems(ship)
                sd["sensors"] = False
                await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
        mgr.resolve(enc, outcome="mynock_attached")

async def mynock_blast(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc,
        f"\n  {GREEN}[WEAPONS]{RST} Turret fire clears the swarm. Effective.", sm)
    mgr.resolve(enc, outcome="mynock_blasted")

async def mynock_timeout(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc,
        f"\n  {RED}[ALERT]{RST} Mynocks attached! Sensors offline.\n"
        f"  {AMBER}Use 'damcon' to repair.{RST}", sm)
    if enc.target_ship_id:
        ship = await db.get_ship(enc.target_ship_id)
        if ship:
            sd = load_ship_systems(ship)
            sd["sensors"] = False
            await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
    mgr.resolve(enc, outcome="mynock_timeout")


# ══════════════════════════════════════════════════════════════════════════════
# PIRATE NEST
# ══════════════════════════════════════════════════════════════════════════════

async def pirates_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    enc.prompt = f"[PIRATE NEST] Multiple contacts — they've spotted you!\n  {RED}Hostile fighters powering weapons!{RST}"
    enc.choices = [
        EncounterChoice(key="engage", label="Engage",
            description="Fight. Salvage + bounty on victory.", risk="high", icon="crosshair"),
        EncounterChoice(key="retreat", label="Retreat",
            description="Full reverse. Piloting check to escape.", risk="medium", icon="arrow-left",
            skill="Space Transports", difficulty="Moderate (15)"),
    ]
    enc.choice_deadline = time.time() + 30

async def pirates_engage(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc, f"\n  {RED}[COMBAT]{RST} Weapons hot! Engaging!", sm)
    await _spawn_pirate_combat(enc, mgr, db, sm, "aggressive", SpaceRange.SHORT)

async def pirates_retreat(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "space_transports", 15, db)
    if r["success"]:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[HELM]{RST} Breaking contact!\n"
            f"  {DIM}(Piloting: {r['roll']} vs 15 — escaped){RST}", sm)
        mgr.resolve(enc, outcome="pirates_retreated")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[SENSORS]{RST} Can't break free!\n"
            f"  {DIM}(Piloting: {r['roll']} vs 15 — caught){RST}", sm)
        await _spawn_pirate_combat(enc, mgr, db, sm, "pursuit", SpaceRange.CLOSE)

async def pirates_timeout(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc, f"\n  {RED}Pirates closing — engaging!{RST}", sm)
    await _spawn_pirate_combat(enc, mgr, db, sm, "ambush", SpaceRange.CLOSE)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def register_anomaly_handlers(enc_manager):
    h = enc_manager.register_handler
    # Distress
    h("anomaly_distress", "setup", distress_setup)
    h("anomaly_distress", "choice_respond", distress_respond)
    h("anomaly_distress", "choice_scan_first", distress_scan_first)
    h("anomaly_distress", "choice_ignore", distress_ignore)
    h("anomaly_distress", "timeout", distress_timeout)
    # Cache
    h("anomaly_cache", "setup", cache_setup)
    h("anomaly_cache", "choice_crack", cache_crack)
    h("anomaly_cache", "choice_leave", cache_leave)
    h("anomaly_cache", "timeout", cache_leave)
    # Mineral
    h("anomaly_mineral", "setup", mineral_setup)
    h("anomaly_mineral", "choice_mine", mineral_mine)
    h("anomaly_mineral", "choice_skip", mineral_skip)
    h("anomaly_mineral", "timeout", mineral_skip)
    # Imperial
    h("anomaly_imperial", "setup", imperial_setup)
    h("anomaly_imperial", "choice_slice", imperial_slice)
    h("anomaly_imperial", "choice_grab", imperial_grab)
    h("anomaly_imperial", "choice_leave", imperial_leave)
    h("anomaly_imperial", "timeout", imperial_leave)
    # Mynock
    h("anomaly_mynock", "setup", mynock_setup)
    h("anomaly_mynock", "choice_evade", mynock_evade)
    h("anomaly_mynock", "choice_blast", mynock_blast)
    h("anomaly_mynock", "timeout", mynock_timeout)
    # Pirate nest
    h("anomaly_pirates", "setup", pirates_setup)
    h("anomaly_pirates", "choice_engage", pirates_engage)
    h("anomaly_pirates", "choice_retreat", pirates_retreat)
    h("anomaly_pirates", "timeout", pirates_timeout)
    log.info("[encounters] anomaly handlers registered (6 types)")
