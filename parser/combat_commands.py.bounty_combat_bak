# -*- coding: utf-8 -*-
"""
Combat commands for in-game D6 personal combat.

Commands:
  attack <target> [with <skill>] [damage <dice>]
  dodge             - normal dodge (counts as action, ranged defense)
  fulldodge         - full dodge (entire round, adds to all ranged defense)
  parry             - normal parry (counts as action, melee defense)
  fullparry         - full parry (entire round, adds to all melee defense)
  aim               - +1D to next attack (max +3D)
  flee              - attempt to leave combat
  combat            - show combat status
  pass              - take no action this round
  resolve           - force-resolve the round (admin/when all have declared)
  disengage         - leave combat (only if no opponents or combat is over)
"""
import os
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.combat import (
    CombatInstance, CombatAction, ActionType, CombatPhase,
)
from engine.weapons import RangeBand
from engine.character import Character, SkillRegistry
from server import ansi

log = logging.getLogger(__name__)

# ── Active combats keyed by room_id ──
_active_combats: dict[int, CombatInstance] = {}

# ── NPC behavior tracking keyed by NPC character id ──
# Populated when NPCs are added to combat, read by auto_declare_npcs
from engine.npc_combat_ai import CombatBehavior
_npc_behaviors: dict[int, CombatBehavior] = {}


def _get_skill_reg() -> SkillRegistry:
    reg = SkillRegistry()
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    skills_path = os.path.join(data_dir, "skills.yaml")
    if os.path.exists(skills_path):
        reg.load_file(skills_path)
    return reg


def _get_or_create_combat(room_id: int, cover_max: int = 0) -> CombatInstance:
    if room_id not in _active_combats:
        _active_combats[room_id] = CombatInstance(
            room_id, _get_skill_reg(), cover_max=cover_max
        )
    return _active_combats[room_id]


def _remove_combat(room_id: int):
    combat = _active_combats.pop(room_id, None)
    if combat:
        # Clean up NPC behaviors for this combat's combatants
        for cid in list(combat.combatants.keys()):
            _npc_behaviors.pop(cid, None)


def _ensure_in_combat(char: dict, room_id: int) -> tuple:
    """Returns (combat, combatant) or (None, None) if not in combat."""
    combat = _active_combats.get(room_id)
    if not combat:
        return None, None
    combatant = combat.get_combatant(char["id"])
    return combat, combatant


async def _broadcast_events(events, session_mgr, room_id, exclude=None):
    """Send combat events to the room."""
    for event in events:
        await session_mgr.broadcast_to_room(room_id, event.text, exclude=exclude)


async def _try_auto_resolve(combat, ctx):
    """
    Auto-declare NPC actions, then if all combatants have declared,
    resolve the round.
    """
    # Auto-declare for any undeclared NPCs
    await _auto_declare_npc_actions(combat, ctx)

    if combat.all_declared():
        events = combat.resolve_round()
        await _broadcast_events(events, ctx.session_mgr, combat.room_id)

        # Apply weapon wear to all attackers' equipped weapons
        await _apply_combat_wear(combat, ctx)

        if combat.is_over:
            _remove_combat(combat.room_id)
            return

        # Auto-roll next initiative
        events = combat.roll_initiative()
        await _broadcast_events(events, ctx.session_mgr, combat.room_id)

        # Auto-declare NPCs for the new round
        await _auto_declare_npc_actions(combat, ctx)

        # Prompt undeclared players
        for c in combat.undeclared_combatants():
            if c.is_npc:
                continue
            sess = ctx.session_mgr.find_by_character(c.id)
            if sess:
                await sess.send_line(
                    ansi.combat_msg("Your turn! Declare: attack/dodge/aim/flee")
                )


async def _auto_declare_npc_actions(combat, ctx):
    """Auto-declare actions for all undeclared NPC combatants."""
    from engine.npc_combat_ai import auto_declare_npcs

    declared = auto_declare_npcs(combat, _npc_behaviors)

    # Narrate NPC declarations to the room
    for npc_id, actions in declared.items():
        c = combat.get_combatant(npc_id)
        if not c:
            continue
        for action in actions:
            if action.action_type == ActionType.ATTACK:
                target_c = combat.get_combatant(action.target_id)
                target_name = target_c.name if target_c else "someone"
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(
                        f"{c.name} prepares to attack {target_name}!"
                    ),
                )
            elif action.action_type == ActionType.FLEE:
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(f"{c.name} tries to flee!"),
                )
            elif action.action_type in (ActionType.DODGE, ActionType.FULL_DODGE):
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(f"{c.name} takes a defensive stance."),
                )
            elif action.action_type == ActionType.AIM:
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(f"{c.name} takes careful aim..."),
                )
            elif action.action_type == ActionType.COVER:
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(f"{c.name} dives for cover!"),
                )


async def _apply_combat_wear(combat, ctx):
    """Apply weapon condition wear and persist wound states after resolution."""
    from engine.items import parse_equipment_json, serialize_equipment
    import json as _json

    for c in combat.combatants.values():
        if not c.char:
            continue

        # ── Persist NPC wound level to char_sheet_json ──
        if c.is_npc:
            try:
                npc_row = await ctx.db.get_npc(c.id)
                if npc_row:
                    cs = _json.loads(npc_row.get("char_sheet_json", "{}"))
                    cs["wound_level"] = c.char.wound_level.value
                    await ctx.db.update_npc(
                        c.id, char_sheet_json=_json.dumps(cs)
                    )
            except Exception as e:
                log.warning("Failed to save NPC %s wound: %s", c.name, e)
            continue

        # ── Player weapon wear ──
        attacked = any(
            a.action_type == ActionType.ATTACK for a in c.actions
        )

        # Sync player wound level back to session + DB
        sess = ctx.session_mgr.find_by_character(c.id)
        if sess and sess.character:
            sess.character["wound_level"] = c.char.wound_level.value
            await ctx.db.save_character(
                c.id, wound_level=c.char.wound_level.value
            )

        if not attacked:
            continue

        if not sess or not sess.character:
            continue

        item = parse_equipment_json(sess.character.get("equipment", "{}"))
        if not item:
            continue

        # Apply wear: 1 per attack, 2 for lightsaber
        skill_used = ""
        for a in c.actions:
            if a.action_type == ActionType.ATTACK:
                skill_used = a.skill.lower()
                break
        wear = 2 if "lightsaber" in skill_used else 1
        item.apply_wear(wear)

        # Persist
        sess.character["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(c.id, equipment=sess.character["equipment"])

        # Notify if weapon is getting damaged
        if item.condition <= 25 and item.condition > 0:
            await sess.send_line(
                f"  {ansi.BRIGHT_YELLOW}Your weapon is badly damaged! "
                f"({item.condition}/{item.max_condition}){ansi.RESET}")
        elif item.condition <= 0:
            await sess.send_line(
                f"  {ansi.BRIGHT_RED}Your weapon has BROKEN! "
                f"Type 'repair' to fix it.{ansi.RESET}")


class AttackCommand(BaseCommand):
    key = "attack"
    aliases = ["att", "kill", "shoot"]
    help_text = "Attack a target. Starts or joins combat."
    usage = "attack <target> [with <skill>] [damage <dice>] [cp <N>]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: attack <target> [with <skill>] [damage <dice>] [cp <N>]")
            await ctx.session.send_line("  attack stormtrooper")
            await ctx.session.send_line("  attack han with blaster damage 4D")
            await ctx.session.send_line("  attack han with melee combat damage STR+2D cp 2")
            await ctx.session.send_line("  (Uses equipped weapon if no skill/damage specified)")
            return

        char = ctx.session.character
        room_id = char["room_id"]

        # ── Determine defaults from equipped weapon ──
        default_skill = "blaster"
        default_damage = "4D"
        equipped_weapon = None

        import json as _json
        equip_data = char.get("equipment", "{}")
        if isinstance(equip_data, str):
            try:
                equip_data = _json.loads(equip_data)
            except Exception:
                equip_data = {}
        weapon_key = equip_data.get("weapon", "") if isinstance(equip_data, dict) else ""
        if weapon_key:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            equipped_weapon = wr.get(weapon_key)
            if equipped_weapon:
                default_skill = equipped_weapon.skill
                default_damage = equipped_weapon.damage

        # Parse arguments
        skill = None  # None = use default
        damage = None  # None = use default
        cp_spend = 0

        # Extract "cp <N>" from anywhere in the args
        import re
        args_lower = ctx.args.lower()
        cp_match = re.search(r'\bcp\s+(\d+)', args_lower)
        if cp_match:
            cp_spend = int(cp_match.group(1))
            ctx_args_clean = ctx.args[:cp_match.start()] + ctx.args[cp_match.end():]
        else:
            ctx_args_clean = ctx.args

        args_lower = ctx_args_clean.lower().strip()

        # Extract "with <skill>" and "damage <dice>"
        if " with " in args_lower:
            before_with, after_with = ctx_args_clean.split(" with ", 1)
            target_name = before_with.strip()
            remainder = after_with.strip()
            if " damage " in remainder.lower():
                skill_part, dmg_part = remainder.lower().split(" damage ", 1)
                skill = skill_part.strip()
                damage = dmg_part.strip()
            else:
                skill = remainder
        elif " damage " in args_lower:
            before_dmg, after_dmg = ctx_args_clean.split(" damage ", 1)
            target_name = before_dmg.strip()
            damage = after_dmg.strip()
        else:
            target_name = ctx_args_clean.strip()

        # Apply defaults from equipped weapon
        if skill is None:
            skill = default_skill
        if damage is None:
            damage = default_damage

        # Find target using centralized matcher
        from engine.matching import match_in_room, MatchResult
        match = await match_in_room(
            target_name, room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
        )

        # Also check combatants already in combat (may not be in room DB)
        target_session = None
        target_char = None
        target_is_npc = False
        target_npc_row = None  # Full NPC DB row for combat setup
        if match.found:
            target_char = match.candidate.data
            target_is_npc = match.candidate.obj_type == "npc"
            if target_is_npc:
                target_npc_row = match.candidate.data
            # Find the session if it's a character
            if match.candidate.obj_type == "character":
                for s in ctx.session_mgr.sessions_in_room(room_id):
                    if s.character and s.character["id"] == match.id:
                        target_session = s
                        break
        else:
            # Fall back: check combatants in active combat
            combat = _active_combats.get(room_id)
            if combat:
                for c in combat.combatants.values():
                    if c.name.lower().startswith(target_name.lower()) and c.id != char["id"]:
                        target_char = {"id": c.id, "name": c.name}
                        break

        if not target_char:
            if match.result == MatchResult.AMBIGUOUS:
                await ctx.session.send_line(f"  {match.error_message(target_name)}")
            else:
                await ctx.session.send_line(f"  You don't see '{target_name}' here.")
            return

        if target_char["id"] == char["id"]:
            await ctx.session.send_line("  You can't attack yourself.")
            return

        # Get or create combat — read cover_max via inherited room properties
        cover_max = 0
        if room_id not in _active_combats:
            cover_max = await ctx.db.get_room_property(room_id, "cover_max", 0)
        combat = _get_or_create_combat(room_id, cover_max=cover_max)
        new_combat = combat.round_num == 0

        # Add combatants if not already in
        char_obj = Character.from_db_dict(char)
        if not combat.get_combatant(char["id"]):
            combat.add_combatant(char_obj)

        if not combat.get_combatant(target_char["id"]):
            if target_is_npc and target_npc_row:
                # Build Character from NPC char_sheet_json
                from engine.npc_combat_ai import (
                    build_npc_character, get_npc_behavior,
                )
                npc_char = build_npc_character(target_npc_row)
                if not npc_char:
                    await ctx.session.send_line(
                        f"  {target_char['name']} has no combat stats. "
                        f"(Builder: use '@npc gen' to give them stats)"
                    )
                    return
                combatant = combat.add_combatant(npc_char)
                combatant.is_npc = True
                # Track NPC behavior for auto-declaration
                _npc_behaviors[npc_char.id] = get_npc_behavior(target_npc_row)
            elif target_session:
                target_obj = Character.from_db_dict(target_char)
                combat.add_combatant(target_obj)

        # Roll initiative if new combat
        if new_combat:
            events = combat.roll_initiative()
            await _broadcast_events(events, ctx.session_mgr, room_id)

        # Declare the attack
        action = CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target_char["id"],
            weapon_damage=damage,
            cp_spend=cp_spend,
        )
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        cp_msg = f", spending {cp_spend} CP" if cp_spend > 0 else ""
        weapon_name = equipped_weapon.name if equipped_weapon and damage == default_damage else ""
        weapon_msg = f" [{weapon_name}]" if weapon_name else ""
        await ctx.session.send_line(
            ansi.combat_msg(
                f"You declare: Attack {target_char['name']} "
                f"with {skill} (damage {damage}){weapon_msg}{cp_msg}"
            )
        )
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            ansi.combat_msg(f"{char['name']} prepares to attack {target_char['name']}!"),
            exclude=ctx.session,
        )

        # Notify target if they haven't declared (players only; NPCs auto-declare)
        c_target = combat.get_combatant(target_char["id"])
        if c_target and not c_target.actions and not c_target.is_npc and target_session:
            await target_session.send_line(
                ansi.combat_msg(
                    f"{char['name']} is attacking you! Declare: dodge/attack/flee"
                )
            )

        await _try_auto_resolve(combat, ctx)


class DodgeCommand(BaseCommand):
    key = "dodge"
    aliases = []
    help_text = "Declare a dodge for this combat round (defends against ranged attacks)."
    usage = "dodge"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.DODGE, skill="dodge")
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You declare: Dodge"))
        await _try_auto_resolve(combat, ctx)


class FullDodgeCommand(BaseCommand):
    key = "fulldodge"
    aliases = ["full dodge", "fdodge"]
    help_text = "Full dodge -- your entire round is spent dodging. Adds to difficulty for ALL incoming ranged attacks. No other actions allowed."
    usage = "fulldodge"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.FULL_DODGE, skill="dodge")
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg(
            "You declare: FULL DODGE (no other actions this round)"
        ))
        await _try_auto_resolve(combat, ctx)


class ParryCommand(BaseCommand):
    key = "parry"
    aliases = []
    help_text = "Declare a parry for this combat round (defends against melee attacks). Uses melee parry, brawling parry, or lightsaber skill as appropriate."
    usage = "parry"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.PARRY)
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You declare: Parry"))
        await _try_auto_resolve(combat, ctx)


class FullParryCommand(BaseCommand):
    key = "fullparry"
    aliases = ["full parry", "fparry"]
    help_text = "Full parry -- your entire round is spent parrying. Adds to difficulty for ALL incoming melee attacks. No other actions allowed."
    usage = "fullparry"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.FULL_PARRY)
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg(
            "You declare: FULL PARRY (no other actions this round)"
        ))
        await _try_auto_resolve(combat, ctx)


class AimCommand(BaseCommand):
    key = "aim"
    aliases = []
    help_text = "Spend a round aiming (+1D to next attack, max +3D)."
    usage = "aim"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.AIM)
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You declare: Aim"))
        await _try_auto_resolve(combat, ctx)


class FleeCommand(BaseCommand):
    key = "flee"
    aliases = ["run"]
    help_text = "Attempt to flee combat."
    usage = "flee"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.FLEE, skill="running")
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You declare: Flee!"))
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            ansi.combat_msg(f"{char['name']} is trying to run!"),
            exclude=ctx.session,
        )
        await _try_auto_resolve(combat, ctx)


class PassCommand(BaseCommand):
    key = "pass"
    aliases = []
    help_text = "Take no action this round (skip your turn)."
    usage = "pass"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        action = CombatAction(action_type=ActionType.OTHER, description="passes")
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You pass this round."))
        await _try_auto_resolve(combat, ctx)


class CombatStatusCommand(BaseCommand):
    key = "combat"
    aliases = ["cs"]
    help_text = "Show current combat status."
    usage = "combat"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        lines = combat.get_status()
        for line in lines:
            await ctx.session.send_line(ansi.combat_msg(line))


class ResolveCommand(BaseCommand):
    key = "resolve"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Force-resolve the combat round (builder/admin)."
    usage = "resolve"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        # Auto-assign pass to undeclared
        for c in combat.undeclared_combatants():
            combat.declare_action(c.id, CombatAction(
                action_type=ActionType.OTHER, description="hesitates"
            ))

        events = combat.resolve_round()
        await _broadcast_events(events, ctx.session_mgr, combat.room_id)

        if combat.is_over:
            _remove_combat(combat.room_id)
            return

        events = combat.roll_initiative()
        await _broadcast_events(events, ctx.session_mgr, combat.room_id)


class DisengageCommand(BaseCommand):
    key = "disengage"
    aliases = []
    help_text = "Leave combat peacefully (only when combat is over or no enemies)."
    usage = "disengage"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        combatant = combat.get_combatant(char["id"])
        if not combatant:
            await ctx.session.send_line("  You're not in this combat.")
            return

        if combat.is_over or len(combat.active_combatants) <= 1:
            combat.remove_combatant(char["id"])
            if len(combat.combatants) == 0:
                _remove_combat(char["room_id"])
            await ctx.session.send_line(ansi.combat_msg("You disengage from combat."))
        else:
            await ctx.session.send_line(
                "  Combat is still active. Use 'flee' to attempt escape."
            )


class RangeCommand(BaseCommand):
    key = "range"
    aliases = ["distance"]
    help_text = "Set your range to a target in combat."
    usage = "range <target> <band>  (bands: pointblank, short, medium, long)"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        if not ctx.args:
            # Show current ranges
            lines = ["  Current ranges:"]
            for cid, c in combat.combatants.items():
                if cid != char["id"]:
                    band = combat.get_range(char["id"], cid)
                    lines.append(f"    {c.name}: {band.label} (diff {int(band)})")
            for line in lines:
                await ctx.session.send_line(line)
            return

        parts = ctx.args.split()
        if len(parts) < 2:
            await ctx.session.send_line(
                "  Usage: range <target> <pointblank|short|medium|long>"
            )
            return

        target_name = parts[0].lower()
        band_name = parts[1].lower()

        # Find target
        target_c = None
        for c in combat.combatants.values():
            if c.name.lower().startswith(target_name) and c.id != char["id"]:
                target_c = c
                break
        if not target_c:
            await ctx.session.send_line(f"  No combatant matching '{parts[0]}' found.")
            return

        # Parse range band
        band_map = {
            "pointblank": RangeBand.POINT_BLANK, "pb": RangeBand.POINT_BLANK,
            "short": RangeBand.SHORT, "s": RangeBand.SHORT,
            "medium": RangeBand.MEDIUM, "med": RangeBand.MEDIUM, "m": RangeBand.MEDIUM,
            "long": RangeBand.LONG, "l": RangeBand.LONG,
        }
        band = band_map.get(band_name)
        if not band:
            await ctx.session.send_line(
                "  Valid bands: pointblank (pb), short (s), medium (med), long (l)"
            )
            return

        combat.set_range(char["id"], target_c.id, band)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            ansi.combat_msg(
                f"{char['name']} moves to {band.label} range from {target_c.name}."
            ),
        )


class CoverCommand(BaseCommand):
    key = "cover"
    aliases = ["hide"]
    help_text = "Take cover (costs an action). Cover level limited by room. Attacking from cover reduces it to 1/4."
    usage = "cover [quarter|half|3/4|full]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        if combat.cover_max <= 0:
            await ctx.session.send_line("  There's no cover available in this area!")
            return

        # Parse requested level
        desc = ctx.args.strip().lower() if ctx.args else ""
        from engine.combat import (
            COVER_QUARTER, COVER_HALF, COVER_THREE_QUARTER, COVER_FULL,
            COVER_NAMES,
        )

        level_map = {
            "quarter": COVER_QUARTER, "1/4": COVER_QUARTER,
            "half": COVER_HALF, "1/2": COVER_HALF, "": COVER_HALF,  # default
            "3/4": COVER_THREE_QUARTER, "three": COVER_THREE_QUARTER,
            "full": COVER_FULL,
        }
        requested = level_map.get(desc, COVER_HALF)
        actual = min(requested, combat.cover_max)

        action = CombatAction(
            action_type=ActionType.COVER,
            description=COVER_NAMES.get(actual, "Half"),
        )
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(
            ansi.combat_msg(f"You take {COVER_NAMES.get(actual, 'cover')}!")
        )
        await _try_auto_resolve(combat, ctx)


class ForcePointCommand(BaseCommand):
    key = "forcepoint"
    aliases = ["fp"]
    help_text = "Spend a Force Point to double ALL dice this round. Must declare during declaration phase. Cannot be used same round as CP."
    usage = "forcepoint"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        err = combat.declare_force_point(char["id"])
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        fp_left = combatant.char.force_points if combatant.char else "?"
        await ctx.session.send_line(
            ansi.combat_msg(
                f"You spend a FORCE POINT! All dice are DOUBLED this round. "
                f"({fp_left} FP remaining)"
            )
        )
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            ansi.combat_msg(
                f"{char['name']} calls upon the Force!"
            ),
            exclude=ctx.session,
        )


async def try_nl_combat_action(ctx, raw_input: str) -> bool:
    """
    Attempt to interpret `raw_input` as a natural language combat action.

    Called by CommandParser when a command is unrecognised and the player
    has a character.  Returns True if the input was handled (successfully
    parsed and dispatched), False if the caller should fall through to the
    normal "Unknown command" message.

    Architecture notes:
    - SceneContext is built from live DB + session state.
    - IntentParser calls Ollama via AIManager (rate-limited, 10/min).
    - BoundedContextValidator rejects hallucinated IDs before any action fires.
    - On success, the result is dispatched as if the player typed the
      canonical command (e.g. attack/dodge/flee).
    - If Ollama is unavailable, this returns False immediately (< 1ms).
    """
    char = ctx.session.character
    if not char:
        return False

    room_id = char.get("room_id")

    # Only intercept if player is in active combat
    combat = _active_combats.get(room_id)
    if not combat:
        return False

    combatant = combat.get_combatant(char["id"])
    if not combatant:
        return False

    # Get AIManager from session_mgr
    ai_manager = getattr(ctx.session_mgr, "_ai_manager", None)
    if ai_manager is None:
        return False

    # Check if Ollama is at all available (fast cached check)
    provider = ai_manager.get_provider()
    try:
        available = await provider.is_available()
    except Exception:
        available = False
    if not available:
        return False

    # Signal to the player that we're parsing their input
    await ctx.session.send_line(
        ansi.dim("  [Interpreting natural language command...]")
    )

    # Build SceneContext
    from ai.scene_context import SceneContext
    scene_ctx = await SceneContext.build(
        room_id=room_id,
        char_id=char["id"],
        db=ctx.db,
        session_mgr=ctx.session_mgr,
        combat=combat,
    )

    # Parse intent
    from ai.intent_parser import IntentParser
    parser = IntentParser(ai_manager)
    result = await parser.parse(
        raw_text=raw_input,
        scene_ctx=scene_ctx,
        char_id=char["id"],
    )

    if result is None:
        await ctx.session.send_line(
            "  Couldn't parse that as a combat action. "
            "Try: attack <target>, dodge, fulldodge, parry, aim, cover, flee, pass"
        )
        return True  # We handled it (with an error message)

    action = result["action"]

    # Dispatch to existing command infrastructure
    from parser.commands import CommandContext

    # Re-use current ctx but override command/args
    dispatched_ctx = CommandContext(
        session=ctx.session,
        raw_input=raw_input,
        command=action,
        args="",
        args_list=[],
        db=ctx.db,
        session_mgr=ctx.session_mgr,
    )

    if action == "attack":
        # Build explicit attack args string so AttackCommand can parse normally
        target_id = result.get("target_id", 0)
        skill = result.get("skill", scene_ctx.default_skill)
        damage = result.get("damage", scene_ctx.default_damage)
        cp = result.get("cp", 0)

        # Resolve target name from scene context
        entity = scene_ctx.entities.get(target_id)
        target_name = entity.name if entity else str(target_id)

        # Build args string: "<name> with <skill> damage <damage> cp <cp>"
        args_parts = [target_name, "with", skill, "damage", damage]
        if cp:
            args_parts += ["cp", str(cp)]
        dispatched_ctx.args = " ".join(args_parts)
        dispatched_ctx.args_list = dispatched_ctx.args.split()

        await ctx.session.send_line(
            ansi.dim(
                f"  [Parsed: attack {target_name} with {skill} (damage {damage})"
                + (f" cp {cp}" if cp else "") + "]"
            )
        )
        cmd = AttackCommand()

    elif action in ("dodge", "fulldodge", "parry", "fullparry"):
        from parser import combat_commands as _cc
        _cmd_map = {
            "dodge": DodgeCommand,
            "fulldodge": FullDodgeCommand,
            "parry": ParryCommand,
            "fullparry": FullParryCommand,
        }
        cmd_cls = _cmd_map.get(action, DodgeCommand)
        cmd = cmd_cls()
        await ctx.session.send_line(ansi.dim(f"  [Parsed: {action}]"))

    elif action == "aim":
        cmd = AimCommand()
        await ctx.session.send_line(ansi.dim("  [Parsed: aim]"))

    elif action == "cover":
        cmd = CoverCommand()
        await ctx.session.send_line(ansi.dim("  [Parsed: cover]"))

    elif action == "flee":
        cmd = FleeCommand()
        await ctx.session.send_line(ansi.dim("  [Parsed: flee]"))

    elif action == "pass":
        cmd = PassCommand()
        await ctx.session.send_line(ansi.dim("  [Parsed: pass]"))

    else:
        await ctx.session.send_line(
            f"  Parsed action '{action}' is not yet dispatched. "
            f"Please use the explicit command."
        )
        return True

    # Execute
    try:
        await cmd.execute(dispatched_ctx)
    except Exception as e:
        log.exception("NL combat dispatch failed for action=%s: %s", action, e)
        await ctx.session.send_line(
            f"  Error executing parsed action '{action}': {e}"
        )

    return True


def register_combat_commands(registry):
    """Register all combat commands."""
    cmds = [
        AttackCommand(), DodgeCommand(), FullDodgeCommand(),
        ParryCommand(), FullParryCommand(),
        AimCommand(), FleeCommand(), PassCommand(),
        CombatStatusCommand(), ResolveCommand(), DisengageCommand(),
        RangeCommand(), CoverCommand(), ForcePointCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
