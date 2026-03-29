# -*- coding: utf-8 -*-
"""
NPC Space Crew Auto-Actions -- Drop 4

When combat starts in space, NPC crew members act automatically
on their station each tick:

  - NPC Pilot: maneuvers based on behavior profile or player order
  - NPC Gunner: fires at nearest hostile (or ordered target)
  - NPC Engineer: repairs the most damaged system
  - NPC Copilot: passive +1D assist (handled by existing station logic)

Player overrides via the 'order' command are stored in the crew JSON
under '_orders' and consumed after execution.

Called from the game tick loop for all ships in active combat.
"""
import json
import logging
import random
from dataclasses import dataclass, field
from typing import Optional

from engine.dice import DicePool, roll_d6_pool
from engine.starships import (
    get_ship_registry, get_space_grid, resolve_space_attack,
    SpaceRange, RelativePosition, can_weapon_fire,
    REPAIRABLE_SYSTEMS, get_system_state,
    get_repair_skill_name, resolve_damage_control,
)
from engine.npc_crew import (
    npc_to_character, resolve_npc_skill, get_crew_json,
    CREW_ROLES, remove_npc_from_all_stations,
)
from engine.character import SkillRegistry

log = logging.getLogger(__name__)


# ── Result types ──

@dataclass
class NPCActionResult:
    """One NPC crew member's action this tick."""
    npc_name: str = ""
    station: str = ""
    action: str = ""         # "fire", "close", "flee", "evade", "damcon", "idle"
    narrative: str = ""
    success: bool = False


# ── Behavior defaults ──
# These map to how the NPC pilot acts when no player order is given.
# Matches the behavior profiles from npc_combat_ai.py conceptually.

_PILOT_BEHAVIOR = {
    "aggressive": ["close", "tail"],
    "defensive": ["evade"],
    "cowardly": ["flee"],
    "berserk": ["close"],
    "sniper": ["evade"],
}


# ── Main entry point ──

async def process_npc_crew_actions(
    ship: dict,
    db,
    session_mgr,
    enemies: list[dict] | None = None,
) -> list[NPCActionResult]:
    """
    Process one round of NPC crew auto-actions for a ship.

    Args:
        ship: The ship dict (from DB) whose NPC crew should act.
        db: Database instance.
        session_mgr: SessionManager for broadcasting messages.
        enemies: List of enemy ship dicts in the area. If None,
                 we look up all ships in space.

    Returns:
        List of NPCActionResult describing what each NPC did.
    """
    results = []
    crew = get_crew_json(ship)
    reg = get_ship_registry()
    template = reg.get(ship["template"])
    if not template:
        return results

    grid = get_space_grid()
    bridge = ship.get("bridge_room_id")

    # Load orders (player overrides) and clear them after use
    orders = crew.pop("_orders", {})

    # Find enemies if not provided
    if enemies is None:
        all_ships = await db.get_ships_in_space()
        enemies = [s for s in all_ships if s["id"] != ship["id"]]

    # ── NPC Pilot ──
    npc_pilot_id = crew.get("npc_pilot")
    if npc_pilot_id and enemies:
        result = await _npc_pilot_act(
            ship, crew, npc_pilot_id, template, grid, enemies, orders, db)
        if result:
            results.append(result)
            if bridge and result.narrative:
                await session_mgr.broadcast_to_room(bridge, result.narrative)

    # ── NPC Gunner(s) ──
    npc_gunners = crew.get("npc_gunners", [])
    for i, gunner_id in enumerate(npc_gunners):
        if i >= len(template.weapons):
            break
        result = await _npc_gunner_act(
            ship, crew, gunner_id, i, template, grid, enemies, orders, db,
            session_mgr)
        if result:
            results.append(result)
            if bridge and result.narrative:
                await session_mgr.broadcast_to_room(bridge, result.narrative)

    # ── NPC Engineer ──
    npc_engineer_id = crew.get("npc_engineer")
    if npc_engineer_id:
        result = await _npc_engineer_act(
            ship, crew, npc_engineer_id, template, orders, db)
        if result:
            results.append(result)
            if bridge and result.narrative:
                await session_mgr.broadcast_to_room(bridge, result.narrative)

    # Save crew JSON with orders consumed
    crew.pop("_orders", None)
    await db.update_ship(ship["id"], crew=json.dumps(crew))

    return results


# ── NPC Pilot ──

async def _npc_pilot_act(
    ship, crew, npc_id, template, grid, enemies, orders, db
) -> Optional[NPCActionResult]:
    """NPC pilot maneuvers based on behavior or player order."""
    npc_row = await db.get_npc(npc_id)
    if not npc_row:
        return None

    name = npc_row["name"]
    first_name = name.split()[0]
    result = NPCActionResult(npc_name=name, station="pilot")

    # Get pilot's behavior from ai_config
    ai_cfg = {}
    try:
        ai_cfg = json.loads(npc_row.get("ai_config_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        pass
    behavior = ai_cfg.get("combat_behavior", "defensive")

    # Check for player order
    order = orders.get("pilot", {})
    action_str = order.get("action", "").strip().lower() if order else ""

    # Pick a target (nearest enemy)
    target = _pick_nearest_enemy(ship["id"], enemies, grid)
    if not target:
        result.action = "idle"
        result.narrative = (
            f"  {_tag('HELM')} {first_name} holds position -- no contacts.")
        return result

    target_reg = get_ship_registry().get(target["template"])

    # Determine action
    if action_str:
        # Player ordered a specific action
        if "close" in action_str:
            action = "close"
        elif "flee" in action_str:
            action = "flee"
        elif "tail" in action_str:
            action = "tail"
        elif "evade" in action_str:
            action = "evade"
        else:
            action = "evade"  # fallback
    else:
        # Use behavior profile
        options = _PILOT_BEHAVIOR.get(behavior, ["evade"])
        action = random.choice(options)

    # Get NPC's piloting skill
    skill_pool = resolve_npc_skill(
        npc_row, "space transports",
        SkillRegistry()  # empty is fine, resolve_npc_skill reads char_sheet_json
    )

    if action == "evade":
        result.action = "evade"
        maneuver = template.maneuverability
        result.narrative = (
            f"  {_tag('HELM')} {first_name} throws the ship into evasive maneuvers! "
            f"(Maneuverability: {maneuver})")
        result.success = True
        return result

    # For close/flee/tail -- use the grid's maneuver system
    target_pilot_pool = DicePool(2, 0)  # default
    if target.get("crew"):
        try:
            tcrew = json.loads(target["crew"]) if isinstance(target["crew"], str) else target["crew"]
            if tcrew.get("pilot"):
                tp = await db.get_character(tcrew["pilot"])
                if tp:
                    from engine.character import Character
                    tp_char = Character.from_db_dict(tp)
                    sr = SkillRegistry()
                    target_pilot_pool = tp_char.get_skill_pool("space transports", sr)
        except Exception:
            pass

    success, narrative = grid.resolve_maneuver(
        pilot_id=ship["id"],
        target_id=target["id"],
        action=action,
        pilot_skill=skill_pool,
        target_pilot_skill=target_pilot_pool,
        pilot_speed=template.speed,
        target_speed=target_reg.speed if target_reg else 5,
    )

    result.action = action
    result.success = success
    result.narrative = f"  {_tag('HELM')} {first_name}: {narrative}"
    return result


# ── NPC Gunner ──

async def _npc_gunner_act(
    ship, crew, npc_id, weapon_idx, template, grid, enemies, orders, db,
    session_mgr,
) -> Optional[NPCActionResult]:
    """NPC gunner fires their assigned weapon at the best target."""
    npc_row = await db.get_npc(npc_id)
    if not npc_row:
        return None

    name = npc_row["name"]
    first_name = name.split()[0]
    weapon = template.weapons[weapon_idx]
    result = NPCActionResult(npc_name=name, station="gunner")

    # Check for ordered target
    order = orders.get("gunner", {})
    order_action = order.get("action", "").strip().lower() if order else ""

    # Pick target
    target = None
    if order_action and "fire" in order_action:
        target_name = order_action.replace("fire", "").strip()
        if target_name:
            for e in enemies:
                if e["name"].lower().startswith(target_name):
                    target = e
                    break
    if not target:
        target = _pick_best_fire_target(ship["id"], enemies, grid, weapon)

    if not target:
        result.action = "idle"
        result.narrative = (
            f"  {_tag('WEAPONS', 'red')} {first_name} scans for targets -- none in arc.")
        return result

    target_reg = get_ship_registry().get(target["template"])
    if not target_reg:
        return None

    # Get range and position
    rng = grid.get_range(ship["id"], target["id"])
    rel_pos = grid.get_position(ship["id"], target["id"])

    if not can_weapon_fire(weapon.fire_arc, rel_pos):
        result.action = "idle"
        result.narrative = (
            f"  {_tag('WEAPONS', 'red')} {first_name}: {weapon.name} can't reach "
            f"{target['name']} ({rel_pos} arc).")
        return result

    # Get NPC gunnery skill
    gunnery_pool = resolve_npc_skill(npc_row, "starship gunnery", SkillRegistry())

    # Target pilot for defense
    target_pilot_pool = DicePool(2, 0)
    tcrew = {}
    try:
        tcrew = json.loads(target.get("crew", "{}")) if isinstance(target.get("crew"), str) else (target.get("crew") or {})
        if tcrew.get("pilot"):
            tp = await db.get_character(tcrew["pilot"])
            if tp:
                from engine.character import Character
                tp_char = Character.from_db_dict(tp)
                target_pilot_pool = tp_char.get_skill_pool("starfighter piloting", SkillRegistry())
    except Exception:
        pass

    # Resolve the attack
    attack_result = resolve_space_attack(
        attacker_skill=gunnery_pool,
        weapon=weapon,
        attacker_scale=template.scale_value,
        target_pilot_skill=target_pilot_pool,
        target_maneuverability=DicePool.parse(target_reg.maneuverability),
        target_hull=DicePool.parse(target_reg.hull),
        target_shields=DicePool.parse(target_reg.shields),
        target_scale=target_reg.scale_value,
        range_band=rng,
        relative_position=rel_pos,
    )

    result.action = "fire"
    result.success = attack_result.hit

    # Apply damage to target ship
    if attack_result.hull_damage > 0:
        new_dmg = target.get("hull_damage", 0) + attack_result.hull_damage
        updates = {"hull_damage": new_dmg}
        if attack_result.systems_hit:
            systems = target.get("systems", "{}")
            if isinstance(systems, str):
                try:
                    systems = json.loads(systems)
                except Exception:
                    systems = {}
            for s in attack_result.systems_hit:
                systems[s] = False
            updates["systems"] = json.dumps(systems)
        await db.update_ship(target["id"], **updates)

    result.narrative = (
        f"  {_tag('WEAPONS', 'red')} {first_name} fires {weapon.name} "
        f"at {target['name']}! {attack_result.narrative.strip()}")

    # Alert the target ship
    target_bridge = target.get("bridge_room_id")
    if target_bridge:
        if attack_result.hit:
            await _broadcast_safe(
                session_mgr, target_bridge,
                f"  {_tag('ALERT', 'red')} Hit by {weapon.name} from "
                f"{ship['name']}! {attack_result.narrative.strip()}")
        else:
            await _broadcast_safe(
                session_mgr, target_bridge,
                f"  {_tag('SENSORS', 'yellow')} Incoming fire from "
                f"{ship['name']} -- missed!")

    return result


# ── NPC Engineer ──

async def _npc_engineer_act(
    ship, crew, npc_id, template, orders, db
) -> Optional[NPCActionResult]:
    """NPC engineer repairs the most damaged system."""
    npc_row = await db.get_npc(npc_id)
    if not npc_row:
        return None

    name = npc_row["name"]
    first_name = name.split()[0]
    result = NPCActionResult(npc_name=name, station="engineer")

    systems = ship.get("systems", "{}")
    if isinstance(systems, str):
        try:
            systems = json.loads(systems)
        except Exception:
            systems = {}

    # Check for player order
    order = orders.get("engineer", {})
    order_action = order.get("action", "").strip().lower() if order else ""

    # Pick system to repair
    target_system = None
    if order_action and "repair" in order_action:
        sys_name = order_action.replace("repair", "").strip()
        for s in REPAIRABLE_SYSTEMS:
            if s.startswith(sys_name):
                if get_system_state(systems, s) == "damaged":
                    target_system = s
                break

    if not target_system:
        # Auto-pick: repair the first damaged system found
        # Priority: engines > shields > weapons > sensors > hyperdrive
        priority = ["engines", "shields", "weapons", "sensors", "hyperdrive"]
        for s in priority:
            if get_system_state(systems, s) == "damaged":
                target_system = s
                break

    # Check hull damage if no systems damaged
    hull_repair = False
    if not target_system:
        hull_dmg = ship.get("hull_damage", 0)
        if hull_dmg > 0:
            target_system = "hull"
            hull_repair = True

    if not target_system:
        result.action = "idle"
        result.narrative = (
            f"  {_tag('ENGINEERING', 'cyan')} {first_name}: "
            f"All systems nominal. Standing by.")
        return result

    # Get repair skill
    repair_skill_name = get_repair_skill_name(template.scale)
    repair_pool = resolve_npc_skill(npc_row, repair_skill_name, SkillRegistry())

    # Resolve repair
    dc_result = resolve_damage_control(
        system_name=target_system,
        repair_pool=repair_pool,
        in_combat=True,
    )

    result.action = "damcon"
    result.success = dc_result.success

    # Apply results
    if dc_result.success:
        if hull_repair:
            new_hull = max(0, ship.get("hull_damage", 0) - dc_result.hull_repaired)
            await db.update_ship(ship["id"], hull_damage=new_hull)
        else:
            systems[target_system] = True
            await db.update_ship(ship["id"], systems=json.dumps(systems))

    if dc_result.permanent_failure:
        systems[target_system] = "destroyed"
        await db.update_ship(ship["id"], systems=json.dumps(systems))

    tag_color = "green" if dc_result.success else ("red" if dc_result.permanent_failure else "yellow")
    result.narrative = (
        f"  {_tag('ENGINEERING', tag_color)} {first_name}: "
        f"{dc_result.narrative.strip()}")

    return result


# ── Helpers ──

def _pick_nearest_enemy(
    ship_id: int, enemies: list[dict], grid
) -> Optional[dict]:
    """Pick the closest enemy ship by range band."""
    if not enemies:
        return None
    range_order = [
        SpaceRange.CLOSE, SpaceRange.SHORT, SpaceRange.MEDIUM,
        SpaceRange.LONG, SpaceRange.EXTREME,
    ]
    best = None
    best_idx = len(range_order)
    for e in enemies:
        rng = grid.get_range(ship_id, e["id"])
        if rng in range_order:
            idx = range_order.index(rng)
            if idx < best_idx:
                best = e
                best_idx = idx
    return best or (enemies[0] if enemies else None)


def _pick_best_fire_target(
    ship_id: int, enemies: list[dict], grid, weapon
) -> Optional[dict]:
    """Pick the best target that's in weapon arc and range."""
    candidates = []
    for e in enemies:
        rng = grid.get_range(ship_id, e["id"])
        if rng == SpaceRange.OUT_OF_RANGE:
            continue
        pos = grid.get_position(ship_id, e["id"])
        if can_weapon_fire(weapon.fire_arc, pos):
            candidates.append((e, rng))

    if not candidates:
        return None

    # Prefer closest
    range_order = [
        SpaceRange.CLOSE, SpaceRange.SHORT, SpaceRange.MEDIUM,
        SpaceRange.LONG, SpaceRange.EXTREME,
    ]
    candidates.sort(key=lambda x: range_order.index(x[1]) if x[1] in range_order else 99)
    return candidates[0][0]


def _tag(label: str, color: str = "cyan") -> str:
    """Format a colored tag like [HELM] or [WEAPONS]."""
    colors = {
        "cyan": "\033[1;36m",
        "red": "\033[1;31m",
        "yellow": "\033[1;33m",
        "green": "\033[1;32m",
    }
    c = colors.get(color, colors["cyan"])
    return f"{c}[{label}]\033[0m"


async def _broadcast_safe(session_mgr, room_id: int, message: str):
    """Broadcast to a room, silently failing if no one is there."""
    try:
        await session_mgr.broadcast_to_room(room_id, message)
    except Exception:
        log.debug("Failed to broadcast to room %d", room_id)


# ── Integration hook for game tick ──

async def tick_npc_space_combat(db, session_mgr):
    """
    Called from the game tick loop. Processes NPC crew auto-actions
    for all ships in space that have NPC crew assigned.

    Only acts if there are enemies in range (avoids spam in empty space).
    """
    ships_in_space = await db.get_ships_in_space()
    if not ships_in_space:
        return

    grid = get_space_grid()
    reg = get_ship_registry()

    for ship in ships_in_space:
        crew = get_crew_json(ship)

        # Skip ships with no NPC crew
        has_npc_crew = any([
            crew.get("npc_pilot"),
            crew.get("npc_gunners"),
            crew.get("npc_engineer"),
        ])
        if not has_npc_crew:
            continue

        # Only act if there are other ships nearby (combat situation)
        enemies = [s for s in ships_in_space if s["id"] != ship["id"]]
        if not enemies:
            continue

        # Check if any enemy is actually in range
        has_contact = False
        for e in enemies:
            rng = grid.get_range(ship["id"], e["id"])
            if rng != SpaceRange.OUT_OF_RANGE:
                has_contact = True
                break
        if not has_contact:
            continue

        # Process this ship's NPC crew
        try:
            results = await process_npc_crew_actions(
                ship, db, session_mgr, enemies)
            if results:
                log.debug(
                    "NPC crew on %s: %d actions",
                    ship["name"],
                    len(results),
                )
        except Exception:
            log.exception("Error processing NPC crew on ship %s", ship.get("name"))
