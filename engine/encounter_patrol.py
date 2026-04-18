# -*- coding: utf-8 -*-
"""
engine/encounter_patrol.py — Imperial Patrol Encounter
Space Overhaul v3, Drop 2

Four-choice branching encounter replacing the old hail→timeout→credits flow.

Choices:
  comply — Submit to inspection. Clean ship = cleared. Contraband = Con check.
  bluff  — Fake codes. Con skill check vs security-scaled difficulty.
  run    — Hit the throttle. Chase sequence (future: NPC combat AI in Drop 3).
  hide   — Go dark, kill power. Sneak/Hide skill check.

Requires: engine/space_encounters.py (Drop 1)

Register with:
    from engine.encounter_patrol import register_patrol_handlers
    register_patrol_handlers(encounter_manager)
"""

import json
import logging
import random
import time
from typing import Optional

from engine.starships import SpaceRange

log = logging.getLogger(__name__)

# ── ANSI shortcuts ───────────────────────────────────────────────────────────
AMBER = "\033[1;33m"
CYAN = "\033[0;36m"
GREEN = "\033[1;32m"
RED = "\033[1;31m"
DIM = "\033[2m"
BOLD = "\033[1m"
RST = "\033[0m"

# ── Tuning ───────────────────────────────────────────────────────────────────

# Bluff difficulty by zone security level
BLUFF_DIFFICULTY = {
    "secured":   20,   # Hard — CorSec/Imperial are competent
    "contested": 15,   # Moderate — standard patrol
    "lawless":   10,   # Easy — lone patrol doesn't want trouble
}

# Deadline (seconds) by zone security
PATROL_DEADLINE = {
    "secured":   45,   # Aggressive — short fuse
    "contested": 60,   # Standard
    "lawless":   90,   # Cautious patrol, generous timeout
}

# Hide/Sneak difficulty by zone security
HIDE_DIFFICULTY = {
    "secured":   25,   # Very Difficult — dense sensor coverage
    "contested": 20,   # Difficult
    "lawless":   15,   # Moderate — sparse sensors
}

# Infraction fines (from WEG40141, already in _run_boarding_inspection)
INFRACTION = {
    5: {"name": "Class Five",  "fine": (100,  500),   "arrest": 0.00},
    4: {"name": "Class Four",  "fine": (1000, 5000),  "arrest": 0.05},
    3: {"name": "Class Three", "fine": (2500, 5000),  "arrest": 0.20},
    2: {"name": "Class Two",   "fine": (5000, 10000), "arrest": 0.40},
    1: {"name": "Class One",   "fine": (0,    0),     "arrest": 1.00},
}

# Cleared status duration (seconds) — reduced patrol risk after clean inspection
CLEARED_DURATION = 900  # 15 minutes


# ── Handler Functions ────────────────────────────────────────────────────────

async def patrol_setup(encounter, manager, db, session_mgr, **kwargs):
    """Setup handler: build the 4-choice patrol encounter."""
    from engine.space_encounters import EncounterChoice
    from engine.npc_space_traffic import get_space_security

    zone_sec = get_space_security(encounter.zone_id)
    patrol_name = encounter.context.get("patrol_name", "Imperial Sector Patrol")
    ship_name = encounter.context.get("player_ship_name", "your vessel")

    encounter.prompt = (
        f"[IMPERIAL PATROL] {patrol_name} is hailing {ship_name}.\n"
        f"  \"{AMBER}Attention freighter — transmit your identification codes "
        f"and stand by for inspection.{RST}\""
    )
    encounter.deciding_station = "any"

    bluff_diff = BLUFF_DIFFICULTY.get(zone_sec, 15)
    hide_diff = HIDE_DIFFICULTY.get(zone_sec, 20)
    deadline = PATROL_DEADLINE.get(zone_sec, 60)

    encounter.choices = [
        EncounterChoice(
            key="comply",
            label="Comply",
            description="Transmit codes and submit to inspection.",
            risk="none" if not encounter.context.get("has_contraband") else "medium",
            icon="shield-check",
            station_hint="",
        ),
        EncounterChoice(
            key="bluff",
            label="Bluff",
            description=f"Fake your codes. Con check vs difficulty {bluff_diff}.",
            risk="medium",
            icon="mask",
            station_hint="commander",
            skill="Con",
            difficulty=f"{'Easy' if bluff_diff <= 10 else 'Moderate' if bluff_diff <= 15 else 'Difficult'} ({bluff_diff})",
        ),
        EncounterChoice(
            key="run",
            label="Run for It",
            description="Hit the throttle. They will pursue.",
            risk="high",
            icon="rocket",
            station_hint="pilot",
            skill="Space Transports",
            difficulty="Opposed piloting",
        ),
        EncounterChoice(
            key="hide",
            label="Go Dark",
            description=f"Kill power and hope they pass. Sneak vs difficulty {hide_diff}.",
            risk="high",
            icon="eye-off",
            station_hint="engineer",
            skill="Hide/Sneak",
            difficulty=f"{'Moderate' if hide_diff <= 15 else 'Difficult' if hide_diff <= 20 else 'Very Difficult'} ({hide_diff})",
        ),
    ]

    encounter.choice_deadline = time.time() + deadline
    encounter.context["zone_security"] = zone_sec
    encounter.context["bluff_difficulty"] = bluff_diff
    encounter.context["hide_difficulty"] = hide_diff


async def patrol_comply(encounter, manager, db, session_mgr, **kwargs):
    """Player chose to comply with inspection."""
    session = kwargs.get("session")
    char_id = kwargs.get("char_id", 0)
    patrol_name = encounter.context.get("patrol_name", "Imperial Patrol")

    await manager.broadcast_to_bridge(
        encounter,
        f"\n  {AMBER}[COMMS]{RST} You transmit identification codes to {patrol_name}.\n"
        f"  {DIM}\"Codes received. Stand by for inspection.\"{RST}",
        session_mgr,
    )

    # Look up player ship for contraband/transponder check
    ship_row = await db.get_ship(encounter.target_ship_id) if encounter.target_ship_id else None
    sys_data = {}
    if ship_row:
        raw = dict(ship_row).get("systems") or "{}"
        try:
            sys_data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            sys_data = {}

    false_tp = sys_data.get("false_transponder")
    smug_job = sys_data.get("smuggling_job")

    # Determine infraction
    if false_tp and isinstance(false_tp, dict):
        # False transponder detected — Class 2
        await _apply_infraction(encounter, manager, db, session_mgr,
                                inf_class=2,
                                reason=f"False transponder detected ({false_tp.get('alias', 'unknown ID')})",
                                char_id=char_id)
    elif smug_job:
        # Contraband — try to hide it (Con check, Moderate)
        tier = smug_job.get("cargo_tier", 1) if isinstance(smug_job, dict) else 1
        inf_class = 3 if tier >= 2 else 4

        # Give the player a Con check to hide the cargo
        hide_result = await _skill_check(char_id, "con", 15, db)

        if hide_result["success"]:
            await manager.broadcast_to_bridge(
                encounter,
                f"  {GREEN}[INSPECTION]{RST} The stormtroopers search the hold but miss "
                f"the contraband. You're cleared.\n"
                f"  {DIM}(Con check: {hide_result['roll']} vs {hide_result['difficulty']} — success){RST}",
                session_mgr,
            )
            manager.resolve(encounter, outcome="comply_clean")
            return
        else:
            await _apply_infraction(encounter, manager, db, session_mgr,
                                    inf_class=inf_class,
                                    reason="Contraband detected in cargo hold",
                                    char_id=char_id,
                                    hide_result=hide_result)
    else:
        # Clean ship — cleared!
        await manager.broadcast_to_bridge(
            encounter,
            f"  {GREEN}[INSPECTION]{RST} Stormtroopers inspect the hold and find nothing.\n"
            f"  {DIM}\"All clear. You're free to go. Safe travels.\"{RST}\n"
            f"  {GREEN}Cleared status granted — reduced patrol risk for 15 minutes.{RST}",
            session_mgr,
        )
        # Set cleared flag on the ship to reduce future patrol encounters
        if ship_row:
            sys_data["patrol_cleared_until"] = time.time() + CLEARED_DURATION
            await db.update_ship(encounter.target_ship_id,
                                 systems=json.dumps(sys_data))
        manager.resolve(encounter, outcome="comply_clean")
        return

    manager.resolve(encounter, outcome="comply_inspected")


async def patrol_bluff(encounter, manager, db, session_mgr, **kwargs):
    """Player chose to bluff — Con skill check."""
    session = kwargs.get("session")
    char_id = kwargs.get("char_id", 0)
    difficulty = encounter.context.get("bluff_difficulty", 15)
    patrol_name = encounter.context.get("patrol_name", "Imperial Patrol")

    result = await _skill_check(char_id, "con", difficulty, db)

    if result.get("critical"):
        # Critical success — patrol apologizes and gives intel
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {GREEN}[COMMS]{RST} {patrol_name}: \"Apologies for the inconvenience, "
            f"Captain. Your codes check out.\"\n"
            f"  {CYAN}[INTEL]{RST} \"Be advised — we've had reports of pirate activity "
            f"in the next sector. Watch your six.\"\n"
            f"  {DIM}(Con check: {result['roll']} vs {difficulty} — critical success!){RST}",
            session_mgr,
        )
        manager.resolve(encounter, outcome="bluff_critical")

    elif result["success"]:
        # Normal success — patrol accepts fake codes
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {GREEN}[COMMS]{RST} {patrol_name}: \"Codes verified. You're cleared "
            f"to proceed. Don't make us stop you again.\"\n"
            f"  {DIM}(Con check: {result['roll']} vs {difficulty} — success){RST}",
            session_mgr,
        )
        manager.resolve(encounter, outcome="bluff_success")

    else:
        # Failure — patrol suspicious, forced boarding
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {RED}[COMMS]{RST} {patrol_name}: \"Those codes are irregular. "
            f"Prepare to be boarded.\"\n"
            f"  {DIM}(Con check: {result['roll']} vs {difficulty} — failed){RST}",
            session_mgr,
        )
        # Run boarding inspection with +5 suspicious behavior penalty
        await _forced_boarding(encounter, manager, db, session_mgr,
                               char_id=char_id, extra_difficulty=5,
                               reason="Suspicious identification codes")


async def patrol_run(encounter, manager, db, session_mgr, **kwargs):
    """Player chose to run — patrol promoted to active combatant.

    The NPC combat AI (Drop 3) drives the pursuit. The player uses
    normal space combat commands (flee, evade, fire, hyperspace) to
    escape or fight back. The encounter resolves when the NPC flees
    (hull threshold), is destroyed, or disables the player.
    """
    session = kwargs.get("session")
    char_id = kwargs.get("char_id", 0)
    patrol_name = encounter.context.get("patrol_name", "Imperial Patrol")

    await manager.broadcast_to_bridge(
        encounter,
        f"\n  {RED}[HELM]{RST} Full throttle! Breaking away from {patrol_name}!\n"
        f"  {AMBER}[SENSORS]{RST} The patrol is pursuing — weapons hot!",
        session_mgr,
    )

    # Promote the patrol NPC to active combatant
    npc_ship_id = encounter.npc_ship_id
    if npc_ship_id:
        from engine.npc_space_combat_ai import get_npc_combat_manager, SpaceCombatProfile
        from engine.npc_space_traffic import get_traffic_manager

        traffic_mgr = get_traffic_manager()
        ts = traffic_mgr.get_ship(npc_ship_id)

        if ts:
            combat_mgr = get_npc_combat_manager()
            combatant = combat_mgr.promote_to_combat(
                npc_ship_id=npc_ship_id,
                target_ship_id=encounter.target_ship_id,
                target_bridge_room=encounter.target_bridge_room,
                zone_id=encounter.zone_id,
                template_key=ts.transponder_type == "official" and "tie_fighter" or "z95",
                display_name=ts.display_name,
                crew_skill="3D+2",
                profile="patrol",
                starting_range=SpaceRange.SHORT,
            )

            # Look up the actual template from traffic ship config
            from engine.npc_space_traffic import TRAFFIC_SHIP_TEMPLATES, TrafficArchetype
            templates = TRAFFIC_SHIP_TEMPLATES.get(TrafficArchetype.PATROL, [])
            if templates:
                combatant.template_key = templates[0].get("template", "tie_fighter")
                combatant.crew_skill = templates[0].get("crew_skill", "3D+2")
                # Recalculate hull from actual template
                from engine.starships import get_ship_registry
                actual_tmpl = get_ship_registry().get(combatant.template_key)
                if actual_tmpl:
                    from engine.dice import DicePool
                    combatant.hull_max_pips = DicePool.parse(actual_tmpl.hull).total_pips()
                    combatant.scale_value = actual_tmpl.scale_value

            await manager.broadcast_to_bridge(
                encounter,
                f"  {RED}[COMBAT]{RST} {patrol_name} has engaged! "
                f"Use 'flee', 'fire', 'evade', or 'hyperspace' to respond.\n"
                f"  {DIM}The patrol will pursue until you escape or they're "
                f"disabled.{RST}",
                session_mgr,
            )

            # Flag transponder — increased attention for 1 hour
            ship_row = await db.get_ship(encounter.target_ship_id)
            if ship_row:
                sys_data = json.loads(dict(ship_row).get("systems") or "{}")
                sys_data["patrol_flagged_until"] = time.time() + 3600
                await db.update_ship(encounter.target_ship_id,
                                     systems=json.dumps(sys_data))

            # Don't resolve encounter — NPC combat AI handles resolution
            encounter.context["combat_active"] = True
            return

    # Fallback: single skill check if NPC promotion failed
    zone_sec = encounter.context.get("zone_security", "contested")
    chase_diff = {"secured": 20, "contested": 15, "lawless": 10}.get(zone_sec, 15)
    result = await _skill_check(char_id, "space_transports", chase_diff, db)

    if result["success"]:
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {GREEN}[HELM]{RST} You outrun the patrol!\n"
            f"  {DIM}(Piloting: {result['roll']} vs {chase_diff} — escaped!){RST}",
            session_mgr,
        )
        manager.resolve(encounter, outcome="run_escaped")
    else:
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {RED}[HELM]{RST} They're closing! Can't shake them!\n"
            f"  {DIM}(Piloting: {result['roll']} vs {chase_diff} — caught!){RST}",
            session_mgr,
        )
        await _forced_boarding(encounter, manager, db, session_mgr,
                               char_id=char_id, extra_difficulty=10,
                               reason="Fleeing from Imperial patrol",
                               min_infraction_class=3)


async def patrol_hide(encounter, manager, db, session_mgr, **kwargs):
    """Player chose to go dark — Sneak/Hide check."""
    session = kwargs.get("session")
    char_id = kwargs.get("char_id", 0)
    difficulty = encounter.context.get("hide_difficulty", 20)
    patrol_name = encounter.context.get("patrol_name", "Imperial Patrol")

    await manager.broadcast_to_bridge(
        encounter,
        f"\n  {DIM}[ENGINEERING]{RST} Cutting power... shields down, weapons cold, "
        f"engines to minimum.\n"
        f"  {DIM}The bridge goes dark. Only emergency lighting remains.{RST}",
        session_mgr,
    )

    result = await _skill_check(char_id, "hide", difficulty, db)

    if result.get("critical"):
        # Critical success — hidden AND discovered something
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {GREEN}[SENSORS]{RST} The patrol sweeps right past. They never "
            f"saw you.\n"
            f"  {CYAN}[SENSORS]{RST} While powered down, passive sensors detected "
            f"an anomaly nearby — something worth investigating.\n"
            f"  {DIM}(Hide: {result['roll']} vs {difficulty} — critical success!){RST}",
            session_mgr,
        )
        # Spawn a bonus anomaly in the zone
        try:
            from engine.space_anomalies import spawn_anomalies_for_zone
            from engine.npc_space_traffic import ZONES
            zone = ZONES.get(encounter.zone_id)
            if zone:
                spawned = spawn_anomalies_for_zone(
                    encounter.zone_id, zone.type.value, security="lawless")
                if spawned:
                    await manager.broadcast_to_bridge(
                        encounter,
                        f"  {CYAN}[SENSORS]{RST} New anomaly detected: use 'deepscan' "
                        f"to investigate.",
                        session_mgr,
                    )
        except Exception as e:
            log.warning("[patrol] bonus anomaly spawn failed: %s", e)

        manager.resolve(encounter, outcome="hide_critical")

    elif result["success"]:
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {GREEN}[SENSORS]{RST} The patrol sweeps through the sector... "
            f"and moves on. They didn't detect you.\n"
            f"  {DIM}(Hide: {result['roll']} vs {difficulty} — success){RST}\n"
            f"  {DIM}Restoring power...{RST}",
            session_mgr,
        )
        manager.resolve(encounter, outcome="hide_success")

    else:
        await manager.broadcast_to_bridge(
            encounter,
            f"\n  {RED}[SENSORS]{RST} {patrol_name}: \"We're detecting a power-down "
            f"anomaly at bearing zero-four-seven. Investigate.\"\n"
            f"  {RED}[ALERT]{RST} They found you! Boarding teams inbound.\n"
            f"  {DIM}(Hide: {result['roll']} vs {difficulty} — failed){RST}",
            session_mgr,
        )
        # Forced boarding with suspicious behavior penalty
        await _forced_boarding(encounter, manager, db, session_mgr,
                               char_id=char_id, extra_difficulty=5,
                               reason="Suspicious power-down detected")


async def patrol_timeout(encounter, manager, db, session_mgr, **kwargs):
    """No response within deadline — forced boarding."""
    patrol_name = encounter.context.get("patrol_name", "Imperial Patrol")

    await manager.broadcast_to_bridge(
        encounter,
        f"\n  {RED}[COMMS]{RST} {patrol_name}: \"Failure to respond is a violation. "
        f"Prepare to be boarded.\"\n",
        session_mgr,
    )

    # Find any char_id on the bridge for the inspection
    char_id = 0
    if encounter.target_bridge_room:
        try:
            sessions = session_mgr.sessions_in_room(encounter.target_bridge_room)
            if sessions:
                for s in sessions:
                    if s.character:
                        char_id = s.character["id"]
                        break
        except Exception:
            log.warning("[patrol] failed to find bridge char_id", exc_info=True)

    await _forced_boarding(encounter, manager, db, session_mgr,
                           char_id=char_id, extra_difficulty=0,
                           reason="Failure to respond to Imperial hail")


# ── Shared Helpers ───────────────────────────────────────────────────────────

async def _skill_check(char_id: int, skill_name: str, difficulty: int,
                       db) -> dict:
    """Run a skill check via the standard engine, return result dict.

    Returns: {"success": bool, "critical": bool, "roll": int, "difficulty": int}
    """
    try:
        from engine.skill_checks import perform_skill_check
        result = await perform_skill_check(
            char_id=char_id,
            skill_name=skill_name,
            difficulty=difficulty,
            db=db,
        )
        return {
            "success": result.success,
            "critical": getattr(result, "critical", False),
            "fumble": getattr(result, "fumble", False),
            "roll": getattr(result, "roll_total", 0),
            "difficulty": difficulty,
        }
    except Exception as e:
        log.warning("[patrol] skill check fallback: %s", e)
        # Fallback: simple random roll if skill engine unavailable
        roll = sum(random.randint(1, 6) for _ in range(3))
        return {
            "success": roll >= difficulty,
            "critical": roll >= difficulty + 10,
            "fumble": False,
            "roll": roll,
            "difficulty": difficulty,
        }


async def _apply_infraction(encounter, manager, db, session_mgr,
                             inf_class: int, reason: str, char_id: int,
                             hide_result: dict = None):
    """Apply a WEG40141 infraction fine to the player."""
    inf = INFRACTION.get(inf_class, INFRACTION[5])
    fine_lo, fine_hi = inf["fine"]
    fine = random.randint(fine_lo, fine_hi) if fine_hi > 0 else 0

    lines = [
        f"\n  {RED}[IMPERIAL BOARDING]{RST} Stormtroopers board for inspection.",
        f"  {RED}[IMPERIAL CUSTOMS]{RST} {inf['name']} infraction: {reason}.",
    ]

    if hide_result and not hide_result.get("success"):
        lines.append(
            f"  {DIM}(Con check: {hide_result['roll']} vs "
            f"{hide_result['difficulty']} — failed){RST}"
        )

    if fine == 0 and inf_class == 1:
        lines.append(
            f"  {RED}[IMPERIAL CUSTOMS]{RST} You are being detained."
            f" (Roleplay with staff or wait for release.)"
        )
    elif fine > 0 and char_id:
        # Deduct credits
        try:
            char = await db.get_character(char_id)
            if char:
                char = dict(char)
                credits = char.get("credits", 0)
                paid = min(credits, fine)
                new_credits = credits - paid
                await db.save_character(char_id, credits=new_credits)

                if paid < fine:
                    lines.append(
                        f"  {AMBER}Fine: {fine:,}cr — insufficient credits. "
                        f"Partial payment of {paid:,}cr accepted.{RST}"
                    )
                else:
                    lines.append(
                        f"  {AMBER}Fine: {fine:,}cr paid. "
                        f"Balance: {new_credits:,}cr.{RST}"
                    )
        except Exception as e:
            log.warning("[patrol] credit deduction error: %s", e)

    lines.append(
        f"  {DIM}[IMPERIAL BOARDING] Troops withdraw. "
        f"You are cleared to proceed.{RST}"
    )

    await manager.broadcast_to_bridge(encounter, "\n".join(lines), session_mgr)


async def _forced_boarding(encounter, manager, db, session_mgr,
                            char_id: int, extra_difficulty: int = 0,
                            reason: str = "Non-compliance",
                            min_infraction_class: int = 5):
    """Run a forced boarding inspection after failed bluff/hide/timeout."""

    # Check for contraband/transponder
    ship_row = await db.get_ship(encounter.target_ship_id) if encounter.target_ship_id else None
    sys_data = {}
    if ship_row:
        raw = dict(ship_row).get("systems") or "{}"
        try:
            sys_data = json.loads(raw) if isinstance(raw, str) else raw
        except Exception:
            sys_data = {}

    false_tp = sys_data.get("false_transponder")
    smug_job = sys_data.get("smuggling_job")

    if false_tp and isinstance(false_tp, dict):
        inf_class = min(2, min_infraction_class)
        reason = f"False transponder ({false_tp.get('alias', 'unknown ID')})"
    elif smug_job:
        tier = smug_job.get("cargo_tier", 1) if isinstance(smug_job, dict) else 1
        inf_class = min(3 if tier >= 2 else 4, min_infraction_class)
        reason = "Contraband detected in cargo hold"
    else:
        # Clean ship but still fined for the original offense
        inf_class = min_infraction_class

    await _apply_infraction(encounter, manager, db, session_mgr,
                             inf_class=inf_class, reason=reason,
                             char_id=char_id)
    manager.resolve(encounter, outcome="forced_boarding")


# ── Registration ─────────────────────────────────────────────────────────────

def register_patrol_handlers(enc_manager) -> None:
    """Register all Imperial Patrol encounter handlers."""
    enc_manager.register_handler("patrol", "setup",          patrol_setup)
    enc_manager.register_handler("patrol", "choice_comply",  patrol_comply)
    enc_manager.register_handler("patrol", "choice_bluff",   patrol_bluff)
    enc_manager.register_handler("patrol", "choice_run",     patrol_run)
    enc_manager.register_handler("patrol", "choice_hide",    patrol_hide)
    enc_manager.register_handler("patrol", "timeout",        patrol_timeout)
    log.info("[encounters] patrol encounter handlers registered")
