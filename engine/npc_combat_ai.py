"""
NPC Combat AI -- Behavioral action selection for NPC combatants.

Handles:
  - Combat behavior profiles (aggressive, defensive, cowardly, berserk)
  - Action selection based on wound level, enemy count, weapon type
  - Target selection (weakest, nearest threat, random)
  - Hostility triggers (attack players on sight)
  - Auto-declaration for NPC combatants in active combat

Design: Pure logic, no I/O. Returns CombatAction objects that the
combat_commands layer enqueues into the CombatInstance.

Behavior profiles (inspired by WEG GM Handbook encounter design):
  AGGRESSIVE  - Attacks best target, dodges only when wounded, flees at MW
  DEFENSIVE   - Prefers dodge/cover, attacks opportunistically, flees at Incap
  COWARDLY    - Flees at Wounded, takes cover first, only fights if cornered
  BERSERK     - Always attacks strongest target, never dodges, never flees
  SNIPER      - Aims first round, attacks from cover, repositions
"""
import json
import logging
import random
from enum import Enum, auto
from typing import Optional

from engine.character import Character, WoundLevel
from engine.combat import (
    CombatInstance, CombatAction, ActionType, Combatant,
    COVER_NONE, is_ranged_skill, is_melee_skill,
)
from engine.weapons import get_weapon_registry, WeaponData

log = logging.getLogger(__name__)


# -- Combat Behavior Profiles --

class CombatBehavior(Enum):
    AGGRESSIVE = "aggressive"
    DEFENSIVE = "defensive"
    COWARDLY = "cowardly"
    BERSERK = "berserk"
    SNIPER = "sniper"

    @classmethod
    def from_str(cls, s: str) -> "CombatBehavior":
        try:
            return cls(s.lower())
        except ValueError:
            return cls.AGGRESSIVE


# -- Default Archetype Mappings --
# Used by @npc generate to assign sensible defaults

DEFAULT_ARCHETYPE_BEHAVIOR: dict[str, str] = {
    "stormtrooper": "aggressive",
    "scout_trooper": "defensive",
    "imperial_officer": "defensive",
    "bounty_hunter": "aggressive",
    "smuggler": "defensive",
    "pilot": "cowardly",
    "mechanic": "cowardly",
    "thug": "berserk",
    "merchant": "cowardly",
    "medic": "cowardly",
    "scout": "defensive",
    "jedi": "aggressive",
    "dark_jedi": "berserk",
    "noble": "cowardly",
    "creature": "berserk",
}

DEFAULT_ARCHETYPE_WEAPONS: dict[str, str] = {
    "stormtrooper": "blaster_rifle",
    "scout_trooper": "blaster_pistol",
    "imperial_officer": "blaster_pistol",
    "bounty_hunter": "heavy_blaster_pistol",
    "smuggler": "blaster_pistol",
    "pilot": "blaster_pistol",
    "mechanic": "hold_out_blaster",
    "thug": "vibroblade",
    "merchant": "hold_out_blaster",
    "medic": "hold_out_blaster",
    "scout": "blaster_pistol",
    "jedi": "lightsaber",
    "dark_jedi": "lightsaber",
    "noble": "hold_out_blaster",
    "creature": "",  # Creatures use brawling, no weapon
}


# -- Flee Thresholds by Behavior --
# At or above this wound level, the NPC attempts to flee

_FLEE_THRESHOLD: dict[CombatBehavior, WoundLevel] = {
    CombatBehavior.AGGRESSIVE: WoundLevel.MORTALLY_WOUNDED,
    CombatBehavior.DEFENSIVE: WoundLevel.INCAPACITATED,
    CombatBehavior.COWARDLY: WoundLevel.WOUNDED,
    CombatBehavior.BERSERK: WoundLevel.DEAD,  # Never flees
    CombatBehavior.SNIPER: WoundLevel.WOUNDED,
}


# -- NPC Character Builder --

def build_npc_character(npc_row: dict) -> Optional[Character]:
    """
    Build a Character object from an NPC database row.

    Reads char_sheet_json. If empty/missing, returns None
    (NPC has no combat stats and can't fight).
    """
    cs_raw = npc_row.get("char_sheet_json", "{}")
    if isinstance(cs_raw, str):
        try:
            sheet = json.loads(cs_raw)
        except (json.JSONDecodeError, TypeError):
            sheet = {}
    else:
        sheet = cs_raw

    if not sheet or not sheet.get("attributes"):
        return None

    # Ensure name is set from the NPC row
    sheet.setdefault("name", npc_row.get("name", "NPC"))

    # Read weapon from ai_config if not in sheet
    if not sheet.get("weapon"):
        ai_raw = npc_row.get("ai_config_json", "{}")
        if isinstance(ai_raw, str):
            try:
                ai_cfg = json.loads(ai_raw)
            except (json.JSONDecodeError, TypeError):
                ai_cfg = {}
        else:
            ai_cfg = ai_raw
        sheet["weapon"] = ai_cfg.get("weapon", "")

    npc_id = npc_row.get("id", 0)
    return Character.from_npc_sheet(npc_id, sheet)


def get_npc_behavior(npc_row: dict) -> CombatBehavior:
    """Extract combat behavior from NPC ai_config_json."""
    ai_raw = npc_row.get("ai_config_json", "{}")
    if isinstance(ai_raw, str):
        try:
            ai_cfg = json.loads(ai_raw)
        except (json.JSONDecodeError, TypeError):
            ai_cfg = {}
    else:
        ai_cfg = ai_raw
    return CombatBehavior.from_str(ai_cfg.get("combat_behavior", "aggressive"))


def is_hostile(npc_row: dict) -> bool:
    """Check if NPC is flagged as hostile (attacks on sight)."""
    ai_raw = npc_row.get("ai_config_json", "{}")
    if isinstance(ai_raw, str):
        try:
            ai_cfg = json.loads(ai_raw)
        except (json.JSONDecodeError, TypeError):
            ai_cfg = {}
    else:
        ai_cfg = ai_raw
    return bool(ai_cfg.get("hostile", False))


# -- Target Selection --

def _select_target(
    npc_combatant: Combatant,
    combat: CombatInstance,
    behavior: CombatBehavior,
) -> Optional[Combatant]:
    """
    Pick the best target for an NPC based on behavior.

    AGGRESSIVE/SNIPER: target the most wounded (easiest kill)
    DEFENSIVE: target whoever attacked them last (or weakest)
    BERSERK: target the strongest (biggest threat)
    COWARDLY: target the weakest (safest fight)
    """
    enemies = [
        c for c in combat.active_combatants
        if c.id != npc_combatant.id and c.char
    ]
    if not enemies:
        return None

    if behavior == CombatBehavior.BERSERK:
        # Target the healthiest/strongest enemy
        return min(enemies, key=lambda c: c.char.wound_level.value)

    if behavior in (CombatBehavior.COWARDLY, CombatBehavior.AGGRESSIVE,
                    CombatBehavior.SNIPER):
        # Target the most wounded (easiest kill)
        return max(enemies, key=lambda c: c.char.wound_level.value)

    # DEFENSIVE: random target
    return random.choice(enemies)


# -- Weapon Resolution --

def _get_npc_weapon(char: Character) -> tuple[str, str, str]:
    """
    Get the NPC's weapon info: (skill, damage, weapon_key).

    Falls back to brawling if no weapon is equipped.
    """
    if char.equipped_weapon:
        wr = get_weapon_registry()
        weapon = wr.get(char.equipped_weapon)
        if weapon:
            return weapon.skill, weapon.damage, char.equipped_weapon

    # Fall back: check if NPC has melee combat or brawling skills
    # and choose the better option
    brawling_bonus = char.skills.get("brawling")
    melee_bonus = char.skills.get("melee combat")

    if melee_bonus and (not brawling_bonus or
                        melee_bonus.total_pips() > brawling_bonus.total_pips()):
        # Use melee combat with STR+1D default damage
        str_dice = char.strength.dice
        str_pips = char.strength.pips
        return "melee combat", f"{str_dice}D+{str_pips + 3}", ""

    # Default to brawling: STR damage
    return "brawling", str(char.strength), ""


# -- Action Selection --

def npc_choose_actions(
    npc_combatant: Combatant,
    combat: CombatInstance,
    behavior: CombatBehavior,
) -> list[CombatAction]:
    """
    Choose combat actions for an NPC based on behavior profile.

    Returns a list of CombatActions to declare. Most NPCs declare
    1-2 actions per round (attack + dodge, or just attack).

    Decision tree per behavior:
      1. Check flee threshold -> FLEE
      2. Check behavior-specific preferences
      3. Select target
      4. Build action list
    """
    char = npc_combatant.char
    if not char or not char.wound_level.can_act:
        return []

    actions: list[CombatAction] = []

    # -- Step 1: Flee check --
    flee_at = _FLEE_THRESHOLD.get(behavior, WoundLevel.MORTALLY_WOUNDED)
    if char.wound_level.value >= flee_at.value:
        actions.append(CombatAction(
            action_type=ActionType.FLEE,
            description=f"{npc_combatant.name} tries to escape!",
        ))
        return actions

    # -- Step 2: Find a target --
    target = _select_target(npc_combatant, combat, behavior)
    if not target:
        # No enemies, just pass
        actions.append(CombatAction(
            action_type=ActionType.OTHER,
            description=f"{npc_combatant.name} looks around warily.",
        ))
        return actions

    # -- Step 3: Get weapon info --
    skill, damage, weapon_key = _get_npc_weapon(char)

    # -- Step 4: Behavior-specific action selection --

    if behavior == CombatBehavior.BERSERK:
        # All-out attack, no defense
        actions.append(CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target.id,
            weapon_damage=damage,
            weapon_key=weapon_key,
        ))
        return actions

    if behavior == CombatBehavior.SNIPER:
        # First round: aim. Subsequent: attack from cover.
        if npc_combatant.aim_bonus < 2 and combat.round_num <= 2:
            actions.append(CombatAction(action_type=ActionType.AIM))
            return actions
        # Attack after aiming
        actions.append(CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target.id,
            weapon_damage=damage,
            weapon_key=weapon_key,
        ))
        return actions

    if behavior == CombatBehavior.COWARDLY:
        # Take cover if available and not already in cover
        if npc_combatant.cover_level == COVER_NONE and combat.cover_max > 0:
            actions.append(CombatAction(
                action_type=ActionType.COVER,
                description="half",
            ))
            return actions
        # Wounded: dodge instead of attack
        if char.wound_level >= WoundLevel.STUNNED:
            actions.append(CombatAction(
                action_type=ActionType.FULL_DODGE,
                skill="dodge",
            ))
            return actions
        # Otherwise attack cautiously (single action)
        actions.append(CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target.id,
            weapon_damage=damage,
            weapon_key=weapon_key,
        ))
        return actions

    if behavior == CombatBehavior.DEFENSIVE:
        # Multi-action: attack + dodge
        if is_ranged_skill(skill):
            actions.append(CombatAction(
                action_type=ActionType.ATTACK,
                skill=skill,
                target_id=target.id,
                weapon_damage=damage,
                weapon_key=weapon_key,
            ))
            actions.append(CombatAction(
                action_type=ActionType.DODGE,
                skill="dodge",
            ))
        else:
            # Melee: attack + parry
            actions.append(CombatAction(
                action_type=ActionType.ATTACK,
                skill=skill,
                target_id=target.id,
                weapon_damage=damage,
                weapon_key=weapon_key,
            ))
            actions.append(CombatAction(
                action_type=ActionType.PARRY,
            ))
        return actions

    # -- AGGRESSIVE (default) --
    # Healthy: just attack (no multi-action penalty)
    # Wounded: attack + dodge
    if char.wound_level >= WoundLevel.WOUNDED:
        actions.append(CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target.id,
            weapon_damage=damage,
            weapon_key=weapon_key,
        ))
        if is_ranged_skill(skill):
            actions.append(CombatAction(
                action_type=ActionType.DODGE,
                skill="dodge",
            ))
        else:
            actions.append(CombatAction(
                action_type=ActionType.PARRY,
            ))
    else:
        # Full offense
        actions.append(CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target.id,
            weapon_damage=damage,
            weapon_key=weapon_key,
        ))

    return actions


# -- Auto-Declaration for all NPCs in a combat --

def auto_declare_npcs(
    combat: CombatInstance,
    npc_behaviors: dict[int, CombatBehavior],
) -> dict[int, list[CombatAction]]:
    """
    Auto-declare actions for all undeclared NPC combatants.

    Args:
        combat: The active CombatInstance
        npc_behaviors: Map of NPC char_id -> CombatBehavior

    Returns:
        Dict of npc_id -> list of declared actions (for narration)
    """
    declared: dict[int, list[CombatAction]] = {}

    for combatant in combat.undeclared_combatants():
        if not combatant.is_npc:
            continue
        if not combatant.char or not combatant.char.wound_level.can_act:
            continue

        behavior = npc_behaviors.get(
            combatant.id, CombatBehavior.AGGRESSIVE
        )
        actions = npc_choose_actions(combatant, combat, behavior)

        for action in actions:
            err = combat.declare_action(combatant.id, action)
            if err:
                log.warning("NPC %s declare error: %s", combatant.name, err)
                break

        declared[combatant.id] = actions

    return declared


# -- Hostility Check --

async def check_room_hostiles(
    room_id: int,
    player_char_id: int,
    db,
) -> list[dict]:
    """
    Check for hostile NPCs in a room that should attack a player.

    Returns list of hostile NPC rows that are ready to fight.
    Called when a player enters a room.
    """
    npcs = await db.get_npcs_in_room(room_id)
    hostiles = []
    for npc_row in npcs:
        if not is_hostile(npc_row):
            continue
        # Only attack if NPC has combat stats
        char = build_npc_character(npc_row)
        if char and char.wound_level.can_act:
            hostiles.append(npc_row)
    return hostiles
