# -*- coding: utf-8 -*-
"""
engine/encounter_texture.py — Texture Space Encounters
Space Overhaul v3, Drops 5 + 6

Encounters that add variety during transit. Not archetype-specific —
these are the "random events" that make each trip unique.

Types:
  mechanical  — System malfunction, crew must repair (Drop 6)
  cargo       — Cargo bay emergency, investigate or vent (Drop 6)
  contact     — Mysterious ship contact, multiple scenarios (Drop 5)
"""

import json
import logging
import random
import time

from engine.json_safe import load_ship_systems

log = logging.getLogger(__name__)

AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
RST = "\033[0m"


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
        log.warning("[texture] credit award: %s", e)


# ══════════════════════════════════════════════════════════════════════════════
# MECHANICAL DIFFICULTY (Drop 6)
# ══════════════════════════════════════════════════════════════════════════════

MALFUNCTION_SYSTEMS = [
    ("hyperdrive", 30, "Hyperdrive motivator temperature critical"),
    ("engines",    25, "Sublight engine power fluctuation detected"),
    ("shields",    20, "Shield generator frequency destabilized"),
    ("sensors",    15, "Sensor array calibration failure"),
    ("weapons",    10, "Weapon capacitor discharge anomaly"),
]

MALFUNCTION_CAUSES = [
    ("wear",     60, "Standard wear"),
    ("mynock",   20, "Mynock infestation on power conduits"),
    ("sabotage", 10, "Evidence of deliberate tampering"),
    ("surge",    10, "Cascading power surge"),
]


async def mechanical_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    # Pick affected system
    weights = [s[1] for s in MALFUNCTION_SYSTEMS]
    system = random.choices(MALFUNCTION_SYSTEMS, weights=weights, k=1)[0]
    sys_key, _, flavor = system

    # Pick cause
    c_weights = [c[1] for c in MALFUNCTION_CAUSES]
    cause = random.choices(MALFUNCTION_CAUSES, weights=c_weights, k=1)[0]
    cause_key = cause[0]

    enc.context["affected_system"] = sys_key
    enc.context["cause"] = cause_key
    enc.context["cause_text"] = cause[2]

    extra_diff = 5 if cause_key == "sabotage" else 0
    diff = 15 + extra_diff
    enc.context["repair_difficulty"] = diff

    enc.prompt = (
        f"[ENGINEERING] Warning: {sys_key} malfunction!\n"
        f"  {AMBER}{flavor}.{RST}")
    enc.deciding_station = "any"

    enc.choices = [
        EncounterChoice(key="repair", label="Repair",
            description=f"Space Transports Repair check ({diff}).",
            risk="low", icon="wrench", station_hint="engineer",
            skill="Space Transports Repair", difficulty=f"Moderate ({diff})"),
        EncounterChoice(key="diagnose", label="Diagnose First",
            description="Sensors check to identify the cause. Reduces repair difficulty.",
            risk="none", icon="search", station_hint="sensors",
            skill="Sensors", difficulty="Moderate (15)"),
        EncounterChoice(key="ignore", label="Ignore",
            description=f"Risk it. {sys_key.title()} stays offline.",
            risk="medium", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 120

    # Disable the affected system
    if enc.target_ship_id:
        ship = await db.get_ship(enc.target_ship_id)
        if ship:
            sd = load_ship_systems(ship)
            sd[sys_key] = False
            await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
    await mgr.broadcast_to_bridge(enc,
        f"  {RED}[SYSTEMS]{RST} {sys_key.title()} offline!", sm)


async def mechanical_repair(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    diff = enc.context.get("repair_difficulty", 15)
    sys_key = enc.context.get("affected_system", "sensors")
    cause = enc.context.get("cause", "wear")

    r = await _skill_check(cid, "space_transports_repair", diff, db)

    if r["success"]:
        # Restore system
        if enc.target_ship_id:
            ship = await db.get_ship(enc.target_ship_id)
            if ship:
                sd = load_ship_systems(ship)
                sd[sys_key] = True
                await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))

        cause_note = ""
        if cause == "sabotage":
            cause_note = f"\n  {RED}[INVESTIGATION]{RST} Signs of deliberate tampering. Someone was aboard."
        elif cause == "mynock":
            cause_note = f"\n  {AMBER}[NOTE]{RST} Found mynock remains on the conduits."

        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[ENGINEERING]{RST} {sys_key.title()} repaired and back online!{cause_note}\n"
            f"  {DIM}(Repair: {r['roll']} vs {diff}){RST}", sm)
        mgr.resolve(enc, outcome="mechanical_repaired")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[ENGINEERING]{RST} Repair attempt failed. {sys_key.title()} still offline.\n"
            f"  {DIM}(Repair: {r['roll']} vs {diff} — failed){RST}\n"
            f"  {DIM}Try again or use 'damcon' when you can.{RST}", sm)
        enc.chosen_key = ""  # Allow retry


async def mechanical_diagnose(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    r = await _skill_check(cid, "sensors", 15, db)

    cause = enc.context.get("cause", "wear")
    cause_text = enc.context.get("cause_text", "Standard wear")

    if r["success"]:
        # Reduce repair difficulty by 5
        old_diff = enc.context.get("repair_difficulty", 15)
        new_diff = max(5, old_diff - 5)
        enc.context["repair_difficulty"] = new_diff

        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[DIAGNOSTICS]{RST} Cause identified: {cause_text}.\n"
            f"  Repair difficulty reduced to {new_diff}.\n"
            f"  {DIM}(Sensors: {r['roll']} vs 15 — success){RST}\n"
            f"  {DIM}Now use 'respond repair' to fix it.{RST}", sm)

        # Update the repair choice description
        for c in enc.choices:
            if c.key == "repair":
                c.description = f"Space Transports Repair check ({new_diff}). Diagnosed!"
                c.difficulty = f"Easy ({new_diff})"
        enc.chosen_key = ""  # Allow choosing repair next
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[DIAGNOSTICS]{RST} Inconclusive. Can't pinpoint the cause.\n"
            f"  {DIM}(Sensors: {r['roll']} vs 15 — failed){RST}\n"
            f"  {DIM}Try 'respond repair' at standard difficulty.{RST}", sm)
        enc.chosen_key = ""


async def mechanical_ignore(enc, mgr, db, sm, **kw):
    sys_key = enc.context.get("affected_system", "sensors")
    cause = enc.context.get("cause", "wear")

    if cause == "surge":
        # Cascading failure — second system goes down
        others = [s[0] for s in MALFUNCTION_SYSTEMS if s[0] != sys_key]
        second = random.choice(others)
        if enc.target_ship_id:
            ship = await db.get_ship(enc.target_ship_id)
            if ship:
                sd = load_ship_systems(ship)
                sd[second] = False
                await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[ENGINEERING]{RST} Cascading failure! {second.title()} also offline!\n"
            f"  {AMBER}Two systems down. Use 'damcon' to repair.{RST}", sm)
        mgr.resolve(enc, outcome="mechanical_cascade")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[ENGINEERING]{RST} {sys_key.title()} remains offline. "
            f"Use 'damcon' when you're ready.\n", sm)
        mgr.resolve(enc, outcome="mechanical_ignored")


async def mechanical_timeout(enc, mgr, db, sm, **kw):
    await mechanical_ignore(enc, mgr, db, sm, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# CARGO EMERGENCY (Drop 6)
# ══════════════════════════════════════════════════════════════════════════════

CARGO_SCENARIOS = [
    ("damaged",    40, "Damaged container — cargo shifting"),
    ("stowaway",   25, "Unauthorized life sign in the hold"),
    ("creature",   20, "Something alive in the shipment"),
    ("contraband", 15, "Hidden compartment detected in cargo"),
]


async def cargo_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    weights = [s[1] for s in CARGO_SCENARIOS]
    scenario = random.choices(CARGO_SCENARIOS, weights=weights, k=1)[0]
    enc.context["scenario"] = scenario[0]
    enc.context["scenario_text"] = scenario[2]

    enc.prompt = (
        f"[CARGO] Warning: cargo bay pressure anomaly.\n"
        f"  {AMBER}{scenario[2]}.{RST}")
    enc.deciding_station = "any"
    enc.choices = [
        EncounterChoice(key="investigate", label="Investigate",
            description="Check the hold. Could be anything.",
            risk="medium", icon="search"),
        EncounterChoice(key="vent", label="Vent the Bay",
            description="Flush the bay. Destroys cargo but eliminates threat.",
            risk="low", icon="wind"),
        EncounterChoice(key="ignore", label="Ignore",
            description="Probably nothing. Risk escalation.",
            risk="medium", icon="x-circle"),
    ]
    enc.choice_deadline = time.time() + 90


async def cargo_investigate(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    scenario = enc.context.get("scenario", "damaged")

    if scenario == "damaged":
        r = await _skill_check(cid, "technical", 12, db)
        if r["success"]:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[CARGO]{RST} Container secured. Cargo intact.\n"
                f"  {DIM}(Technical: {r['roll']} vs 12 — repaired){RST}", sm)
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {AMBER}[CARGO]{RST} Container ruptured. Partial cargo loss.\n"
                f"  {DIM}(Technical: {r['roll']} vs 12 — failed){RST}", sm)
        mgr.resolve(enc, outcome=f"cargo_damaged_{'saved' if r['success'] else 'lost'}")

    elif scenario == "stowaway":
        r = await _skill_check(cid, "perception", 10, db)
        cr = random.randint(200, 800)
        await mgr.broadcast_to_bridge(enc,
            f"\n  {CYAN}[CARGO]{RST} A stowaway! Terrified refugee hiding in a crate.\n"
            f"  {DIM}They offer {cr:,} credits to not be turned in.{RST}", sm)
        await _award_credits(cid, cr, db)
        mgr.resolve(enc, outcome="cargo_stowaway")

    elif scenario == "creature":
        r = await _skill_check(cid, "perception", 15, db)
        if r["success"]:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[CARGO]{RST} Space vermin — contained before damage.\n"
                f"  {DIM}(Perception: {r['roll']} vs 15 — caught){RST}", sm)
            mgr.resolve(enc, outcome="cargo_creature_caught")
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {RED}[CARGO]{RST} Creatures chewed through power conduits!\n"
                f"  {AMBER}Sensors offline until repaired.{RST}\n"
                f"  {DIM}(Perception: {r['roll']} vs 15 — escaped){RST}", sm)
            if enc.target_ship_id:
                ship = await db.get_ship(enc.target_ship_id)
                if ship:
                    sd = load_ship_systems(ship)
                    sd["sensors"] = False
                    await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
            mgr.resolve(enc, outcome="cargo_creature_escaped")

    elif scenario == "contraband":
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[CARGO]{RST} Hidden compartment with spice! Someone planted this.\n"
            f"  {DIM}If patrols find this, you're looking at a Class 3 infraction.\n"
            f"  Use 'smugdump' to jettison or keep it and risk the next inspection.{RST}", sm)
        mgr.resolve(enc, outcome="cargo_contraband_found")


async def cargo_vent(enc, mgr, db, sm, **kw):
    scenario = enc.context.get("scenario", "damaged")
    if scenario == "creature":
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[CARGO]{RST} Bay vented. Whatever was in there is gone.\n"
            f"  {DIM}Cargo destroyed, but ship is safe.{RST}", sm)
    elif scenario == "contraband":
        await mgr.broadcast_to_bridge(enc,
            f"\n  {GREEN}[CARGO]{RST} Bay vented. Contraband and cargo eliminated.\n"
            f"  {DIM}Clean ship, empty hold.{RST}", sm)
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {AMBER}[CARGO]{RST} Bay vented. All cargo lost.\n"
            f"  {DIM}If you had a smuggling job, it just failed.{RST}", sm)
    mgr.resolve(enc, outcome="cargo_vented")


async def cargo_ignore(enc, mgr, db, sm, **kw):
    scenario = enc.context.get("scenario", "damaged")
    if scenario == "creature":
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[CARGO]{RST} The noise gets worse. Hull vibration increasing.\n"
            f"  {AMBER}Weapons system offline — creatures in the power conduits!{RST}", sm)
        if enc.target_ship_id:
            ship = await db.get_ship(enc.target_ship_id)
            if ship:
                sd = load_ship_systems(ship)
                sd["weapons"] = False
                await db.update_ship(enc.target_ship_id, systems=json.dumps(sd))
        mgr.resolve(enc, outcome="cargo_creature_escalated")
    else:
        await mgr.broadcast_to_bridge(enc,
            f"\n  {DIM}[CARGO] Situation stabilizes on its own. For now.{RST}", sm)
        mgr.resolve(enc, outcome="cargo_ignored")


async def cargo_timeout(enc, mgr, db, sm, **kw):
    await cargo_ignore(enc, mgr, db, sm, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# MYSTERIOUS CONTACT (Drop 5)
# ══════════════════════════════════════════════════════════════════════════════

CONTACT_SCENARIOS = [
    ("yacht",     30, "Luxury yacht with broken nav computer"),
    ("racer",     25, "Smuggler blasting through at max speed, TIEs pursuing"),
    ("adrift",    25, "Freighter adrift — power but no comms response"),
    ("probe",     20, "Imperial probe droid deployment ship"),
]


async def contact_setup(enc, mgr, db, sm, **kw):
    from engine.space_encounters import EncounterChoice
    weights = [s[1] for s in CONTACT_SCENARIOS]
    scenario = random.choices(CONTACT_SCENARIOS, weights=weights, k=1)[0]
    enc.context["scenario"] = scenario[0]

    if scenario[0] == "yacht":
        enc.prompt = (f"[SENSORS] Luxury yacht detected — transmitting distress.\n"
                      f"  {DIM}\"Our nav computer is fried. Can anyone help?\"{RST}")
        enc.choices = [
            EncounterChoice(key="help", label="Help",
                description="Astrogation check to fix their nav. Credits reward.",
                risk="none", icon="compass", skill="Astrogation", difficulty="Moderate (15)"),
            EncounterChoice(key="ignore", label="Ignore",
                description="Not your problem.", risk="none", icon="x-circle"),
        ]
    elif scenario[0] == "racer":
        enc.prompt = (f"[SENSORS] Contact — ship at max speed, two TIE fighters in pursuit!\n"
                      f"  {AMBER}\"Help! They're going to blow me apart!\"{RST}")
        enc.choices = [
            EncounterChoice(key="help", label="Intervene",
                description="Engage the TIEs. Risky but rewarding.",
                risk="high", icon="crosshair"),
            EncounterChoice(key="hail_imps", label="Hail Imperials",
                description="Report to the patrol. Small reputation boost.",
                risk="none", icon="radio"),
            EncounterChoice(key="ignore", label="Stay Out of It",
                description="Not your fight.", risk="none", icon="x-circle"),
        ]
    elif scenario[0] == "adrift":
        enc.prompt = (f"[SENSORS] Freighter adrift — power readings but no comms.\n"
                      f"  {DIM}No transponder broadcast. Something's wrong.{RST}")
        enc.choices = [
            EncounterChoice(key="board", label="Investigate",
                description="Approach and scan. Could be salvage, rescue, or trap.",
                risk="medium", icon="search", skill="Perception", difficulty="Moderate (15)"),
            EncounterChoice(key="ignore", label="Leave It",
                description="Could be anything. Keep moving.",
                risk="none", icon="x-circle"),
        ]
    elif scenario[0] == "probe":
        enc.prompt = (f"[SENSORS] Imperial probe droid carrier detected.\n"
                      f"  {DIM}Deploying surveillance probes across the sector.{RST}")
        enc.choices = [
            EncounterChoice(key="destroy", label="Destroy Probes",
                description="Gunnery check. Rebel contacts will pay for this.",
                risk="medium", icon="crosshair", skill="Starship Gunnery", difficulty="Moderate (15)"),
            EncounterChoice(key="ignore", label="Avoid",
                description="Stay clear. Not worth the attention.",
                risk="none", icon="x-circle"),
        ]

    enc.deciding_station = "any"
    enc.choice_deadline = time.time() + 90


async def contact_help(enc, mgr, db, sm, **kw):
    cid = kw.get("char_id", 0)
    scenario = enc.context.get("scenario", "yacht")

    if scenario == "yacht":
        r = await _skill_check(cid, "astrogation", 15, db)
        if r["success"]:
            cr = random.randint(1000, 3000)
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[NAV]{RST} Nav computer repaired. Grateful passengers transfer {cr:,} credits.\n"
                f"  {DIM}(Astrogation: {r['roll']} vs 15){RST}", sm)
            await _award_credits(cid, cr, db)
            mgr.resolve(enc, outcome="contact_yacht_helped")
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {AMBER}[NAV]{RST} Can't fix their system. They'll drift to the next port.\n"
                f"  {DIM}(Astrogation: {r['roll']} vs 15 — failed){RST}", sm)
            mgr.resolve(enc, outcome="contact_yacht_failed")

    elif scenario == "racer":
        # Combat encounter with TIEs — use pirate combat spawn
        from engine.starships import SpaceRange
        await mgr.broadcast_to_bridge(enc,
            f"\n  {RED}[COMBAT]{RST} Engaging Imperial fighters!", sm)
        from engine.encounter_anomaly import _spawn_pirate_combat
        await _spawn_pirate_combat(enc, mgr, db, sm, "aggressive", SpaceRange.MEDIUM)
        if enc.context.get("combat_active"):
            return  # Combat AI handles resolution

    elif scenario == "adrift":
        # Same as distress respond
        r = await _skill_check(cid, "perception", 15, db)
        if r["success"]:
            cr = random.randint(500, 2000)
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[SENSORS]{RST} Crew alive — unconscious from gas leak. Rescued.\n"
                f"  {CYAN}[REWARD]{RST} {cr:,} credits and cargo samples as thanks.", sm)
            await _award_credits(cid, cr, db)
            from engine.encounter_anomaly import _award_resources
            await _award_resources(cid, "composite", random.randint(1, 3),
                                    random.randint(50, 70), db)
            mgr.resolve(enc, outcome="contact_adrift_rescued")
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {AMBER}[SENSORS]{RST} Ship is cold. Nothing salvageable.\n"
                f"  {DIM}(Perception: {r['roll']} vs 15 — nothing found){RST}", sm)
            mgr.resolve(enc, outcome="contact_adrift_empty")

    elif scenario == "probe":
        r = await _skill_check(cid, "starship_gunnery", 15, db)
        if r["success"]:
            cr = random.randint(1500, 4000)
            await mgr.broadcast_to_bridge(enc,
                f"\n  {GREEN}[WEAPONS]{RST} Probes destroyed before they could transmit!\n"
                f"  {CYAN}[INTEL]{RST} A Rebel contact transfers {cr:,} credits for the service.", sm)
            await _award_credits(cid, cr, db)
            mgr.resolve(enc, outcome="contact_probe_destroyed")
        else:
            await mgr.broadcast_to_bridge(enc,
                f"\n  {RED}[WEAPONS]{RST} Missed! Probes scatter and transmit.\n"
                f"  {AMBER}Imperial attention in this sector just increased.{RST}\n"
                f"  {DIM}(Gunnery: {r['roll']} vs 15 — failed){RST}", sm)
            mgr.resolve(enc, outcome="contact_probe_alerted")


async def contact_hail_imps(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc,
        f"\n  {DIM}[COMMS] You report the smuggler's position to Imperial patrol.\n"
        f"  \"Noted. The Empire appreciates loyal citizens.\"{RST}", sm)
    mgr.resolve(enc, outcome="contact_racer_reported")


async def contact_board(enc, mgr, db, sm, **kw):
    await contact_help(enc, mgr, db, sm, **kw)


async def contact_destroy(enc, mgr, db, sm, **kw):
    await contact_help(enc, mgr, db, sm, **kw)


async def contact_ignore(enc, mgr, db, sm, **kw):
    await mgr.broadcast_to_bridge(enc,
        f"\n  {DIM}[NAV] Contact fades from sensors as you continue.{RST}", sm)
    mgr.resolve(enc, outcome="contact_ignored")


async def contact_timeout(enc, mgr, db, sm, **kw):
    await contact_ignore(enc, mgr, db, sm, **kw)


# ══════════════════════════════════════════════════════════════════════════════
# REGISTRATION
# ══════════════════════════════════════════════════════════════════════════════

def register_texture_handlers(enc_manager):
    h = enc_manager.register_handler
    # Mechanical
    h("mechanical", "setup",            mechanical_setup)
    h("mechanical", "choice_repair",    mechanical_repair)
    h("mechanical", "choice_diagnose",  mechanical_diagnose)
    h("mechanical", "choice_ignore",    mechanical_ignore)
    h("mechanical", "timeout",          mechanical_timeout)
    # Cargo
    h("cargo", "setup",            cargo_setup)
    h("cargo", "choice_investigate", cargo_investigate)
    h("cargo", "choice_vent",      cargo_vent)
    h("cargo", "choice_ignore",    cargo_ignore)
    h("cargo", "timeout",          cargo_timeout)
    # Contact
    h("contact", "setup",            contact_setup)
    h("contact", "choice_help",      contact_help)
    h("contact", "choice_hail_imps", contact_hail_imps)
    h("contact", "choice_board",     contact_board)
    h("contact", "choice_destroy",   contact_destroy)
    h("contact", "choice_ignore",    contact_ignore)
    h("contact", "timeout",          contact_timeout)
    log.info("[encounters] texture handlers registered (mechanical, cargo, contact)")
