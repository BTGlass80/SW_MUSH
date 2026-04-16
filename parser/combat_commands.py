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
import asyncio
import json as _json
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.combat import (
    CombatInstance, CombatAction, ActionType, CombatPhase,
)
from engine.weapons import RangeBand
from engine.character import Character, SkillRegistry
from server import ansi

# Achievement hooks (graceful-drop on failure)
async def _ach_combat_hook(db, char_id, event, session=None):
    try:
        from engine.achievements import check_achievement
        await check_achievement(db, char_id, event, session=session)
    except Exception:
        pass  # Never break combat for achievements


log = logging.getLogger(__name__)

# ── Active combats keyed by room_id ──
_active_combats: dict[int, CombatInstance] = {}

# ── NPC behavior tracking keyed by NPC character id ──
# Populated when NPCs are added to combat, read by auto_declare_npcs
from engine.npc_combat_ai import CombatBehavior
_npc_behaviors: dict[int, CombatBehavior] = {}

# ── PvP consent tracking ──
# Maps (attacker_id, target_id) → timestamp of challenge issued.
# Both parties must consent before open PvP is allowed in CONTESTED zones.
# LAWLESS zones bypass this entirely. TTL: 10 minutes.
import time as _time
_pvp_consent: dict[tuple, float] = {}   # pending challenges
_pvp_active:  dict[tuple, float] = {}   # accepted PvP pairs (either direction)
_PVP_CHALLENGE_TTL = 600                # 10 minutes


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
    """Send combat events to the room (immediate, no pacing)."""
    for event in events:
        await session_mgr.broadcast_to_room(room_id, event.text, exclude=exclude)


def _extract_actor_name(text: str):
    """Return the first name-token from a narrative line, or None for headers."""
    stripped = text.lstrip()
    if not stripped or stripped.startswith(("---", "─", "[COMBAT]", "Turn order")):
        return None
    stripped = stripped.lstrip("▸◆ ")
    parts = stripped.split()
    return parts[0] if parts else None


async def _broadcast_separator(session_mgr, room_id):
    """Emit a visual phase-separator line."""
    await session_mgr.broadcast_to_room(
        room_id, "  " + "─" * 45, exclude=None
    )


async def _broadcast_events_paced(events, session_mgr, room_id,
                                   delay: float = 0.6, exclude=None):
    """Send combat events with a short delay between each actor's block.

    For damage events (event.you_text set, event.targets non-empty), the
    target session receives the personalised ◆ YOU variant; all others see
    the standard room narrative.
    """
    current_actor = None
    for event in events:
        actor = _extract_actor_name(event.text)
        if actor and actor != current_actor and current_actor is not None:
            await asyncio.sleep(delay)
        if actor:
            current_actor = actor

        # Per-session delivery: target sees YOU variant, everyone else sees room text
        if event.you_text and event.targets:
            target_ids = set(event.targets)
            for sess in session_mgr.sessions_in_room(room_id):
                char = getattr(sess, "character", None)
                if not char:
                    continue
                # Check exclude list
                if isinstance(exclude, list) and char.get("id") in set(exclude):
                    continue
                if exclude is not None and not isinstance(exclude, list) and sess is exclude:
                    continue
                # Target sees YOU variant; attacker + bystanders see room text
                char_id = char.get("id")
                if char_id in target_ids:
                    await sess.send_line(event.you_text)
                else:
                    await sess.send_line(event.text)
        else:
            await session_mgr.broadcast_to_room(room_id, event.text, exclude=exclude)


async def _send_combat_state(combat, session_mgr):
    """Send combat_state JSON to all WebSocket sessions in the combat room.

    Telnet sessions receive nothing (send_json is a no-op for them).
    Each player gets a personalised payload with viewer_id set.
    """
    room_id = combat.room_id
    sessions = session_mgr.sessions_in_room(room_id)
    for sess in sessions:
        char = getattr(sess, "character", None)
        viewer_id = char["id"] if char else None
        payload = combat.to_hud_dict(viewer_id=viewer_id)
        await sess.send_json("combat_state", payload)


async def _send_combat_ended(room_id, session_mgr):
    """Notify WebSocket clients that combat is over."""
    for sess in session_mgr.sessions_in_room(room_id):
        await sess.send_json("combat_state", {"active": False})


async def _try_auto_resolve(combat, ctx):
    """
    Auto-declare NPC actions, then if all combatants have declared,
    resolve the round and open the posing window.

    v2 lifecycle:
      1. Resolve round (batch)
      2. Send private briefings to each player
      3. Auto-generate NPC poses via FLAVOR_MATRIX
      4. Open posing window with grace timer
      5. When all poses in (or timer expires) → flush Action Log
      6. Advance to next round
    """
    # Auto-declare for any undeclared NPCs
    await _auto_declare_npc_actions(combat, ctx)

    if combat.all_declared():
        events = combat.resolve_round()
        # Don't broadcast events to room yet — they go in the Action Log
        # But we DO need to apply wear and persist wounds immediately
        await _apply_combat_wear(combat, ctx)

        if combat.is_over:
            # Combat ended — broadcast final events directly, no posing
            await _broadcast_events_paced(events, ctx.session_mgr, combat.room_id)
            await _send_combat_ended(combat.room_id, ctx.session_mgr)
            # Achievement: combat_victory for surviving PCs
            try:
                from engine.achievements import on_combat_victory
                for c in combat.combatants.values():
                    if not c.is_npc and c.char and c.char.wound_level.value < 5:
                        _csess = ctx.session_mgr.find_by_character(c.id)
                        if _csess:
                            await on_combat_victory(ctx.db, c.id, session=_csess)
            except Exception as _e:
                log.debug("silent except in parser/combat_commands.py:209: %s", _e, exc_info=True)
            # Cleanup: remove incapacitated/dead NPCs from room
            try:
                for c in combat.combatants.values():
                    if c.is_npc and c.char and c.char.wound_level.value >= 4:
                        await ctx.db.update_npc(c.id, room_id=None)
            except Exception:
                log.warning("NPC cleanup after combat failed", exc_info=True)
            _remove_combat(combat.room_id)
            return

        # Combat continues — send private briefings + open posing window
        await _send_combat_state(combat, ctx.session_mgr)
        await _send_private_briefings(combat, ctx)
        await _auto_generate_npc_poses(combat)
        await _start_posing_window(combat, ctx)


async def _send_private_briefings(combat, ctx):
    """Send each player their personal briefing after resolution."""
    for c in combat.combatants.values():
        if c.is_npc:
            continue
        sess = ctx.session_mgr.find_by_character(c.id)
        if not sess:
            continue
        briefing = combat.build_private_briefing(c.id)
        if briefing:
            await sess.send_line(briefing)


async def _auto_generate_npc_poses(combat):
    """Generate and store auto-poses for all NPC combatants."""
    for c in combat.combatants.values():
        if not c.is_npc:
            continue
        if c.id not in combat._pose_state:
            continue
        auto_pose = combat.generate_auto_pose(c.id)
        combat.set_pose_status(c.id, "passed", text=auto_pose)


async def _start_posing_window(combat, ctx):
    """Open the posing window and start the grace timer.

    If no player combatants are pending (solo-NPC fight edge case),
    flush immediately.
    """
    from engine.combat import CombatPhase
    combat.phase = CombatPhase.POSING

    # Set the deadline timestamp for web client countdown
    from datetime import datetime, timezone, timedelta
    deadline = datetime.now(timezone.utc) + timedelta(seconds=180)
    combat.pose_deadline = deadline.isoformat()

    await _send_combat_state(combat, ctx.session_mgr)

    # Check if all poses are already in (all NPCs, no players)
    if combat.all_poses_in():
        await _flush_action_log(combat, ctx)
        return

    # Spawn the grace timer as a background task
    loop = asyncio.get_event_loop()
    combat._grace_timer_handle = loop.create_task(
        _pose_grace_timer(combat, ctx)
    )


async def _pose_grace_timer(combat, ctx, timeout=180, nudge_at=90):
    """Background task: nudge idle posers, auto-pass on timeout."""
    try:
        await asyncio.sleep(nudge_at)
        pending = combat.get_pending_posers()
        if pending:
            names = ", ".join(p.name for p in pending if not p.is_npc)
            if names:
                await ctx.session_mgr.broadcast_to_room(
                    combat.room_id,
                    ansi.combat_msg(
                        f"Still waiting for narrative poses from: {names}."
                    ),
                )

        await asyncio.sleep(timeout - nudge_at)

        # Force-pass anyone still pending
        for char_id in combat.get_pending_poser_ids():
            c = combat.get_combatant(char_id)
            if c and not c.is_npc:
                auto_pose = combat.generate_auto_pose(char_id)
                combat.set_pose_status(char_id, "passed", text=auto_pose)
                sess = ctx.session_mgr.find_by_character(char_id)
                if sess:
                    await sess.send_line(
                        ansi.combat_msg(
                            "Time's up! The engine narrates your actions."
                        )
                    )

        # Flush the Action Log
        await _flush_action_log(combat, ctx)

    except asyncio.CancelledError:
        pass  # All poses came in early; normal exit


async def _on_pose_submitted(combat, ctx):
    """Called after a player submits a pose or passes.

    Checks if all poses are in; if so, cancels the timer and flushes.
    """
    await _send_combat_state(combat, ctx.session_mgr)

    if combat.all_poses_in():
        # Cancel the grace timer
        if combat._grace_timer_handle and not combat._grace_timer_handle.done():
            combat._grace_timer_handle.cancel()
        await _flush_action_log(combat, ctx)


async def _flush_action_log(combat, ctx):
    """Assemble and broadcast the cinematic Action Log, then advance."""
    sorted_poses = combat.get_sorted_poses()

    # Build the Action Log block
    header = (
        ansi.BOLD
        + f"─── ROUND {combat.round_num} : ACTION LOG "
        + "─" * 40
        + ansi.RESET
    )
    footer = ansi.BOLD + "─" * 70 + ansi.RESET

    await ctx.session_mgr.broadcast_to_room(combat.room_id, header)

    for init_val, char_id, text in sorted_poses:
        c = combat.get_combatant(char_id)
        name = c.name if c else "Unknown"
        if text:
            line = f"  (Init {init_val:2d}) [{name}] {text}"
        else:
            line = f"  (Init {init_val:2d}) [{name}] hesitates, doing nothing."
        await ctx.session_mgr.broadcast_to_room(combat.room_id, line)
        await asyncio.sleep(0.5)  # Pacing between combatant poses

    await ctx.session_mgr.broadcast_to_room(combat.room_id, footer)

    # Clear pose state
    combat._pose_state = {}
    combat.pose_deadline = None

    # Advance to next round
    await _advance_to_next_round(combat, ctx)


async def _advance_to_next_round(combat, ctx):
    """Roll initiative, auto-declare NPCs, prompt players."""
    # Phase separator
    await asyncio.sleep(1.1)
    await _broadcast_separator(ctx.session_mgr, combat.room_id)

    # Auto-roll next initiative
    events = combat.roll_initiative()
    await _broadcast_events_paced(events, ctx.session_mgr, combat.room_id, delay=0.3)
    await _send_combat_state(combat, ctx.session_mgr)

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
    """Auto-declare actions for all undeclared NPC combatants.

    Emits a single grouped summary line instead of one line per NPC.
    Per-session delivery substitutes the player's name with "you".
    """
    from engine.npc_combat_ai import auto_declare_npcs

    declared = auto_declare_npcs(combat, _npc_behaviors)
    if not declared:
        return

    # Build per-NPC summaries, then emit one grouped line
    parts = []
    for npc_id, actions in declared.items():
        c = combat.get_combatant(npc_id)
        if not c or not actions:
            continue

        action_descs = []
        for action in actions:
            if action.action_type == ActionType.ATTACK:
                target_c = combat.get_combatant(action.target_id)
                target_name = target_c.name if target_c else "someone"
                action_descs.append(f"attacking {target_name}")
            elif action.action_type == ActionType.FLEE:
                action_descs.append("fleeing")
            elif action.action_type in (ActionType.DODGE, ActionType.FULL_DODGE):
                action_descs.append("dodging")
            elif action.action_type == ActionType.AIM:
                action_descs.append("aiming")
            elif action.action_type == ActionType.COVER:
                action_descs.append("taking cover")
            else:
                action_descs.append("waiting")

        if action_descs:
            parts.append(f"{c.name}: {', '.join(action_descs)}")

    if not parts:
        return

    # Per-session delivery: substitute player name -> "you" in target refs
    summary_generic = " | ".join(parts)
    generic_line = ansi.combat_msg(f"Enemies readying: {summary_generic}")

    # Send personalised version to each player session in the room
    player_combatants = [
        c for c in combat.combatants.values() if not c.is_npc
    ]
    notified = set()
    for pc in player_combatants:
        sess = ctx.session_mgr.find_by_character(pc.id)
        if not sess:
            continue
        notified.add(pc.id)
        personal = summary_generic.replace(
            f"attacking {pc.name}", "attacking you"
        )
        await sess.send_line(
            ansi.combat_msg(f"Enemies readying: {personal}")
        )

    # Broadcast to any remaining sessions (observers, etc.) not yet notified
    # Only send the generic line to sessions that were not individually notified
    for sess in ctx.session_mgr.sessions_in_room(combat.room_id):
        char = getattr(sess, "character", None)
        if char and char["id"] in notified:
            continue
        await sess.send_line(generic_line)


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
                    # ── Bounty kill hook ──────────────────────────────────
                    # If this NPC is a bounty target and just died, auto-
                    # collect the contract for the player who killed them.
                    from engine.character import WoundLevel as _WL
                    if c.char.wound_level.value >= _WL.DEAD.value:
                        try:
                            _ai_cfg = _json.loads(
                                npc_row.get("ai_config_json", "{}")
                            )
                            if _ai_cfg.get("is_bounty_target"):
                                from engine.bounty_board import get_bounty_board
                                _board = get_bounty_board()
                                # Find the player who dealt the killing blow
                                # (first non-NPC attacker in this round)
                                _killer_id = None
                                for _ac in combat.combatants.values():
                                    if not _ac.is_npc and any(
                                        _a.action_type == ActionType.ATTACK
                                        and _a.target_id == c.id
                                        for _a in _ac.actions
                                    ):
                                        _killer_id = _ac.id
                                        break
                                if _killer_id:
                                    _contract = await _board.notify_target_killed(
                                        c.id, _killer_id, ctx.db
                                    )
                                    if _contract:
                                        _reward = _board.total_reward(
                                            _contract, alive=False
                                        )
                                        # Award credits
                                        _sess = ctx.session_mgr.find_by_character(
                                            _killer_id
                                        )
                                        if _sess and _sess.character:
                                            _cr = _sess.character.get("credits", 0)
                                            _sess.character["credits"] = _cr + _reward
                                            await ctx.db.save_character(
                                                _killer_id,
                                                credits=_sess.character["credits"],
                                            )
                                            await _sess.send_line(
                                                f"  \033[1;33m[BOUNTY COLLECTED]\033[0m "
                                                f"{_contract.target_name} — "
                                                f"+{_reward:,} credits awarded."
                                            )
                                            log.info(
                                                "[bounty] Auto-collected %s for "
                                                "char %s: %dcr",
                                                _contract.id, _killer_id, _reward,
                                            )
                        except Exception as _be:
                            log.warning(
                                "Bounty kill hook error for NPC %s: %s",
                                c.id, _be,
                            )
                    # ── End bounty kill hook ──────────────────────────────
                    # ── Dead NPC combatant cleanup ───────────────────────
                    from engine.character import WoundLevel as _WL2
                    if c.char.wound_level.value >= _WL2.DEAD.value:
                        try:
                            combat.remove_combatant(c.id)
                        except Exception:
                            log.warning("_apply_combat_wear: unhandled exception", exc_info=True)
                            pass
                    # ── End dead NPC cleanup ─────────────────────────────
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

            # Narrative: log combat outcome
            try:
                from engine.narrative import log_action, ActionType as NT
                from engine.character import WoundLevel as _WLN
                wl = c.char.wound_level.value
                if wl >= _WLN.INCAPACITATED.value:
                    await log_action(ctx.db, c.id, NT.COMBAT_DEFEAT,
                                     f"Incapacitated in combat in room {combat.room_id}")
                    # ── Scar system: permanent wound record ──────────
                    try:
                        from engine.scars import add_scar
                        from engine.weapons import get_weapon_registry
                        _wr = get_weapon_registry()
                        # Find the attacker who caused this wound
                        _atk_name = "unknown"
                        _wpn_name = "Unknown Weapon"
                        _wpn_type = "blaster"
                        _atk_skill = "blaster"
                        for _oc in combat.combatants.values():
                            if _oc.id == c.id:
                                continue
                            for _a in _oc.actions:
                                if (_a.action_type == ActionType.ATTACK
                                        and _a.target_id == c.id):
                                    _atk_name = _oc.name
                                    _atk_skill = _a.skill or "blaster"
                                    if _a.weapon_key:
                                        _w = _wr.get(_a.weapon_key)
                                        if _w:
                                            _wpn_name = _w.name
                                            _wpn_type = _w.weapon_type
                                    break
                        _room = await ctx.db.get_room(combat.room_id)
                        _loc_name = (_room or {}).get("name", "unknown")
                        _wl_str = ("mortally_wounded"
                                   if wl >= _WLN.MORTALLY_WOUNDED.value
                                   else "incapacitated")
                        _scar = add_scar(
                            sess.character, _wl_str,
                            _wpn_name, _wpn_type, _atk_skill,
                            _atk_name, _loc_name,
                        )
                        await ctx.db.save_character(
                            c.id, attributes=sess.character["attributes"]
                        )
                        await sess.send_line(
                            f"  \033[1;33m[SCAR]\033[0m"
                            f" {_scar['description']}."
                            f" This wound will leave a mark."
                        )
                    except Exception as _se:
                        log.warning("Scar hook error for char %s: %s",
                                    c.id, _se)
                elif wl == 0:
                    # Check if any opponent was beaten
                    beaten = [
                        oc.name for oc in combat.combatants.values()
                        if oc.id != c.id and oc.char and
                        oc.char.wound_level.value >= _WLN.INCAPACITATED.value
                    ]
                    if beaten:
                        await log_action(ctx.db, c.id, NT.COMBAT_VICTORY,
                                         f"Defeated {', '.join(beaten)} in combat")
                        # Drop 6: award faction rep for combat victory
                        try:
                            from engine.organizations import adjust_rep
                            await adjust_rep(
                                sess.character,
                                sess.character.get("faction_id", "independent"),
                                ctx.db,
                                "kill_enemy_faction_npc",
                            )
                        except Exception:
                            pass  # graceful-drop
                        # Drop 6A: territory influence for NPC kill
                        try:
                            from engine.territory import on_npc_kill
                            await on_npc_kill(ctx.db, sess.character,
                                              combat.room_id)
                        except Exception:
                            pass  # graceful-drop
                        # Drop 6D: hostile takeover check — if the killed NPC
                        # was a territory guard, the killer's org can seize the room.
                        try:
                            from engine.territory import (
                                get_claim, get_room_zone_id,
                                get_zone_security, hostile_takeover_claim,
                            )
                            _room_id = combat.room_id
                            _claim = await get_claim(ctx.db, _room_id)
                            if _claim and _claim.get("guard_npc_id"):
                                # Check if the NPC that died is the guard
                                _dead_guard = False
                                for _oc in combat.combatants.values():
                                    if (_oc.is_npc and _oc.id == _claim["guard_npc_id"]
                                            and _oc.char
                                            and _oc.char.wound_level.value >= 5):
                                        _dead_guard = True
                                        break
                                if _dead_guard:
                                    _zone_id = await get_room_zone_id(
                                        ctx.db, _room_id)
                                    _sec = await get_zone_security(
                                        ctx.db, _zone_id) if _zone_id else ""
                                    if _sec == "lawless":
                                        # Notify the killer they can seize
                                        _atk_org = sess.character.get(
                                            "faction_id", "independent")
                                        if (_atk_org
                                                and _atk_org != "independent"
                                                and _atk_org != _claim["org_code"]):
                                            await sess.send_line(
                                                f"  \033[1;31m[TERRITORY]\033[0m The guard"
                                                f" is down. Use "
                                                f"\033[1;37mfaction seize\033[0m to"
                                                f" claim this room for your faction."
                                            )
                        except Exception:
                            pass  # graceful-drop
                        # From Dust to Stars: combat kill hook
                        try:
                            from engine.spacer_quest import check_spacer_quest
                            await check_spacer_quest(sess.session, ctx.db, "combat_kill")
                        except Exception:
                            pass  # graceful-drop
            except Exception:
                log.warning("_apply_combat_wear: unhandled exception", exc_info=True)
                pass

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
    aliases = ["att", "kill", "shoot", "hit"]
    help_text = (
        "Attack a target with your equipped weapon.\n"
        "If no combat is active, this starts one.\n"
        "\n"
        "OPTIONS:\n"
        "  with <skill>  -- override weapon skill\n"
        "  damage <dice> -- override damage dice\n"
        "  cp <N>        -- spend N Character Points on the roll\n"
        "  stun          -- fire in stun mode (blasters only)\n"
        "\n"
        "EXAMPLES:\n"
        "  attack stormtrooper\n"
        "  attack thug with brawling\n"
        "  attack bounty hunter cp 2\n"
        "  attack guard stun"
    )
    usage = "attack <target> [with <skill>] [damage <dice>] [cp <N>] [stun]"

    # ── Pipeline orchestrator ────────────────────────────────────────
    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await self._usage_help(ctx)
            return

        char = ctx.session.character
        room_id = char["room_id"]

        # Phase 1: Security gate
        from engine.security import SecurityLevel
        sec = await self._check_security_gate(ctx, room_id, char)
        if sec is None:
            return

        # Phase 2: Resolve equipped weapon defaults
        equipped_weapon, default_skill, default_damage = \
            self._resolve_equipped_weapon(char)

        # Phase 3: Parse args → target_name, skill, damage, cp, stun
        parsed = self._parse_attack_args(
            ctx.args, default_skill, default_damage)
        target_name, skill, damage, cp_spend, stun_mode = parsed

        # Phase 4: Find target (room matcher → active combat fallback)
        target_info = await self._find_target(
            ctx, target_name, room_id, char)
        if target_info is None:
            return
        target_char, target_session, target_is_npc, target_npc_row = target_info

        # Phase 5: PvP consent check (CONTESTED zones only)
        if not await self._check_pvp_consent(
                ctx, char, target_char, target_name, target_is_npc,
                room_id, sec):
            return

        # Phase 6: Build/attach combat + add combatants
        combat, new_combat = await self._setup_combat(
            ctx, room_id, char, target_char, target_is_npc, target_npc_row)
        if combat is None:
            return

        # Phase 7: Initiative (new combat only)
        if new_combat:
            events = combat.roll_initiative()
            await _broadcast_events_paced(
                events, ctx.session_mgr, room_id, delay=0.3)
            await _send_combat_state(combat, ctx.session_mgr)

        # Phase 8: Stun validation + declare + broadcast
        await self._declare_and_broadcast(
            ctx, combat, char, target_char, target_session,
            skill, damage, cp_spend, stun_mode,
            equipped_weapon, default_damage, room_id)

        # Phase 9: Auto-resolve if everyone has declared
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)

    # ── Phase helpers ────────────────────────────────────────────────

    async def _usage_help(self, ctx):
        await ctx.session.send_line(
            "Usage: attack <target> [with <skill>] [damage <dice>] [cp <N>]")
        await ctx.session.send_line("  attack stormtrooper")
        await ctx.session.send_line("  attack han with blaster damage 4D")
        await ctx.session.send_line(
            "  attack han with melee combat damage STR+2D cp 2")
        await ctx.session.send_line(
            "  (Uses equipped weapon if no skill/damage specified)")

    async def _check_security_gate(self, ctx, room_id, char):
        """Return SecurityLevel, or None if SECURED (message already sent)."""
        from engine.security import (
            get_effective_security, SecurityLevel, security_refuse_msg)
        sec = await get_effective_security(room_id, ctx.db, character=char)
        if sec == SecurityLevel.SECURED:
            await ctx.session.send_line(
                security_refuse_msg(sec, target_is_npc=True))
            return None
        return sec

    def _resolve_equipped_weapon(self, char):
        """Return (equipped_weapon_or_None, default_skill, default_damage)."""
        default_skill = "blaster"
        default_damage = "4D"
        equipped_weapon = None

        equip_data = char.get("equipment", "{}")
        if isinstance(equip_data, str):
            try:
                equip_data = _json.loads(equip_data)
            except Exception:
                log.warning("attack: equipment JSON parse failed", exc_info=True)
                equip_data = {}
        weapon_key = (equip_data.get("key", "")
                      if isinstance(equip_data, dict) else "")
        if weapon_key:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            equipped_weapon = wr.get(weapon_key)
            if equipped_weapon:
                default_skill = equipped_weapon.skill
                default_damage = equipped_weapon.damage
        return equipped_weapon, default_skill, default_damage

    def _parse_attack_args(self, raw_args, default_skill, default_damage):
        """Parse 'attack <target> [cp N] [stun] [with <skill>] [damage <dice>]'.

        Returns (target_name, skill, damage, cp_spend, stun_mode).
        `cp` and `stun` can appear anywhere in args; order-independent.
        `with` and `damage` are positional after target.
        """
        import re

        skill = None
        damage = None
        cp_spend = 0

        # Extract "cp <N>" from anywhere in the args
        args_lower = raw_args.lower()
        cp_match = re.search(r'\bcp\s+(\d+)', args_lower)
        if cp_match:
            cp_spend = int(cp_match.group(1))
            args_clean = raw_args[:cp_match.start()] + raw_args[cp_match.end():]
        else:
            args_clean = raw_args

        # v22: Extract "stun" keyword from args
        stun_mode = False
        if re.search(r'\bstun\b', args_clean.lower()):
            stun_mode = True
            args_clean = re.sub(
                r'\bstun\b', '', args_clean, flags=re.IGNORECASE).strip()

        al = args_clean.lower().strip()

        # Extract "with <skill>" and "damage <dice>"
        if " with " in al:
            before_with, after_with = args_clean.split(" with ", 1)
            target_name = before_with.strip()
            remainder = after_with.strip()
            if " damage " in remainder.lower():
                skill_part, dmg_part = remainder.lower().split(" damage ", 1)
                skill = skill_part.strip()
                damage = dmg_part.strip()
            else:
                skill = remainder
        elif " damage " in al:
            before_dmg, after_dmg = args_clean.split(" damage ", 1)
            target_name = before_dmg.strip()
            damage = after_dmg.strip()
        else:
            target_name = args_clean.strip()

        if skill is None:
            skill = default_skill
        if damage is None:
            damage = default_damage
        return target_name, skill, damage, cp_spend, stun_mode

    async def _find_target(self, ctx, target_name, room_id, char):
        """Locate the target in the room, or fall back to active combat.

        Returns (target_char, target_session, target_is_npc, target_npc_row)
        or None (error already sent).
        """
        from engine.matching import match_in_room, MatchResult
        match = await match_in_room(
            target_name, room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
        )

        target_session = None
        target_char = None
        target_is_npc = False
        target_npc_row = None

        if match.found:
            target_char = match.candidate.data
            target_is_npc = match.candidate.obj_type == "npc"
            if target_is_npc:
                target_npc_row = match.candidate.data
            if match.candidate.obj_type == "character":
                for s in ctx.session_mgr.sessions_in_room(room_id):
                    if s.character and s.character["id"] == match.id:
                        target_session = s
                        break
        else:
            # Fall back: check combatants already in active combat
            combat = _active_combats.get(room_id)
            if combat:
                for c in combat.combatants.values():
                    if (c.name.lower().startswith(target_name.lower())
                            and c.id != char["id"]):
                        target_char = {"id": c.id, "name": c.name}
                        break

        if not target_char:
            if match.result == MatchResult.AMBIGUOUS:
                await ctx.session.send_line(
                    f"  {match.error_message(target_name)}")
            else:
                await ctx.session.send_line(
                    f"  You don't see '{target_name}' here.")
            return None

        if target_char["id"] == char["id"]:
            await ctx.session.send_line("  You can't attack yourself.")
            return None

        return target_char, target_session, target_is_npc, target_npc_row

    async def _check_pvp_consent(self, ctx, char, target_char, target_name,
                                 target_is_npc, room_id, sec):
        """PvP consent gate for CONTESTED zones. Honors BH-contract override
        and active territory-contest override.

        Returns True if attack may proceed, False if refused (message sent).
        """
        if target_is_npc:
            return True
        from engine.security import SecurityLevel
        if sec != SecurityLevel.CONTESTED:
            return True

        now = _time.time()
        # Purge stale entries
        for k in list(_pvp_active.keys()):
            if now - _pvp_active[k] > _PVP_CHALLENGE_TTL:
                _pvp_active.pop(k, None)
        a_id, t_id = char["id"], target_char["id"]
        consented = (
            _pvp_active.get((a_id, t_id), 0) > now - _PVP_CHALLENGE_TTL or
            _pvp_active.get((t_id, a_id), 0) > now - _PVP_CHALLENGE_TTL
        )
        if consented:
            return True

        # ── Bounty Hunter override (Security Drop 5) ──
        bh_override = await self._check_bh_override(
            ctx, char, target_name, room_id)
        # ── Territory contest override (Security Drop 6D) ──
        contest_override = await self._check_territory_contest_override(
            ctx, char, target_char, target_name, room_id)

        if not bh_override and not contest_override:
            await ctx.session.send_line(
                f"  \033[1;33mImperial law prohibits unprovoked assault here.\033[0m\n"
                f"  Use \033[1;37mchallenge {target_name}\033[0m to issue a formal challenge.\n"
                f"  (Or find a lawless zone where Imperial law doesn't reach.)"
            )
            return False
        return True

    async def _check_bh_override(self, ctx, char, target_name, room_id):
        """True if attacker is BH guild with an active claimed contract.
        Broadcasts a [BOUNTY HUNTER] drama line to the room if so."""
        try:
            if char.get("faction_id") != "bh_guild":
                return False
            from parser.bounty_commands import (
                _get_active_contract, _load_board)
            brd = await _load_board(ctx.db)
            contract = await _get_active_contract(str(char["id"]), brd)
            if contract and contract.status.value == "claimed":
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;31m[BOUNTY HUNTER]\033[0m "
                    f"{char['name']} draws on {target_name}!"
                    f" [Contract: {contract.id}]"
                )
                return True
        except Exception:
            log.warning("_check_bh_override: unhandled exception",
                        exc_info=True)
        return False

    async def _check_territory_contest_override(self, ctx, char, target_char,
                                                target_name, room_id):
        """True if attacker and target belong to two different non-independent
        orgs in an active territory contest for this zone."""
        try:
            atk_org = char.get("faction_id", "independent")
            def_org = target_char.get("faction_id", "independent")
            if (not atk_org or not def_org
                    or atk_org == "independent"
                    or def_org == "independent"
                    or atk_org == def_org):
                return False
            from engine.territory import (
                get_room_zone_id, is_in_active_contest)
            zone_id = await get_room_zone_id(ctx.db, room_id)
            if not zone_id:
                return False
            active = await is_in_active_contest(
                ctx.db, zone_id, atk_org, def_org)
            if active:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;31m[TERRITORY WAR]\033[0m "
                    f"{char['name']} attacks {target_name}! "
                    f"[{atk_org.replace('_', ' ').title()} vs "
                    f"{def_org.replace('_', ' ').title()}]",
                )
                return True
        except Exception:
            log.warning(
                "_check_territory_contest_override: unhandled exception",
                exc_info=True)
        return False

    async def _setup_combat(self, ctx, room_id, char, target_char,
                            target_is_npc, target_npc_row):
        """Get/create combat for room, add both combatants.
        Returns (combat, new_combat_flag) or (None, False) on failure."""
        cover_max = 0
        if room_id not in _active_combats:
            cover_max = await ctx.db.get_room_property(room_id, "cover_max", 0)
        combat = _get_or_create_combat(room_id, cover_max=cover_max)
        new_combat = combat.round_num == 0

        # v22 S15: use cached Character object when available
        char_obj = ctx.session.get_char_obj() or Character.from_db_dict(char)
        if not combat.get_combatant(char["id"]):
            combat.add_combatant(char_obj)

        if not combat.get_combatant(target_char["id"]):
            if target_is_npc and target_npc_row:
                from engine.npc_combat_ai import (
                    build_npc_character, get_npc_behavior,
                )
                npc_char = build_npc_character(target_npc_row)
                if not npc_char:
                    await ctx.session.send_line(
                        f"  {target_char['name']} has no combat stats. "
                        f"(Builder: use '@npc gen' to give them stats)"
                    )
                    return None, False
                combatant = combat.add_combatant(npc_char)
                combatant.is_npc = True
                _npc_behaviors[npc_char.id] = get_npc_behavior(target_npc_row)
            else:
                # Player character (target_session is non-None if in-room;
                # for out-of-room combatant fallback we still attach)
                target_obj = Character.from_db_dict(target_char)
                combat.add_combatant(target_obj)

        return combat, new_combat

    async def _declare_and_broadcast(self, ctx, combat, char, target_char,
                                     target_session, skill, damage, cp_spend,
                                     stun_mode, equipped_weapon,
                                     default_damage, room_id):
        """Validate stun, declare the ATTACK action, broadcast to attacker,
        room, and target session if applicable."""
        # v22: validate stun mode against weapon capability
        if stun_mode and equipped_weapon and not equipped_weapon.stun_capable:
            await ctx.session.send_line(
                f"  {equipped_weapon.name} cannot be set to stun.")
            stun_mode = False

        action = CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target_char["id"],
            weapon_damage=damage,
            cp_spend=cp_spend,
            stun_mode=stun_mode,
        )
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        cp_msg = f", spending {cp_spend} CP" if cp_spend > 0 else ""
        stun_msg = " [STUN]" if stun_mode else ""
        weapon_name = (equipped_weapon.name
                       if equipped_weapon and damage == default_damage
                       else "")
        weapon_msg = f" [{weapon_name}]" if weapon_name else ""
        await ctx.session.send_line(
            ansi.combat_msg(
                f"You declare: Attack {target_char['name']} "
                f"with {skill} (damage {damage}){weapon_msg}{stun_msg}{cp_msg}"
            )
        )
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            ansi.combat_msg(
                f"{char['name']} prepares to attack {target_char['name']}!"),
            exclude=ctx.session,
        )

        # Notify target if they haven't declared (players only; NPCs auto-declare)
        c_target = combat.get_combatant(target_char["id"])
        if (c_target and not c_target.actions
                and not c_target.is_npc and target_session):
            await target_session.send_line(
                ansi.combat_msg(
                    f"{char['name']} is attacking you! "
                    f"Declare: dodge/attack/flee"
                )
            )


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
        await _send_combat_state(combat, ctx.session_mgr)
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
        await _send_combat_state(combat, ctx.session_mgr)
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
        await _send_combat_state(combat, ctx.session_mgr)
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
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)


class SoakCommand(BaseCommand):
    """v22 audit #12: Pre-declare CP spending on soak (Strength to resist damage).

    Per R&E p55: 'Five to increase a Strength roll to resist damage.'
    CP are only spent if the character is actually hit. Max 5 per round.
    """
    key = "+soak"
    aliases = ["soak"]
    help_text = (
        "Pre-declare Character Points to spend on soak if you get hit.\n"
        "CP are only spent if you take damage. Max 5 per R&E.\n"
        "Use during declaration phase alongside dodge/parry."
    )
    usage = "soak <1-5>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        if not ctx.args or not ctx.args.strip().isdigit():
            await ctx.session.send_line("  Usage: soak <1-5>  (CP to spend on damage resistance)")
            return

        cp_amount = int(ctx.args.strip())
        if cp_amount < 1 or cp_amount > 5:
            await ctx.session.send_line("  R&E limit: 1-5 CP on soak.")
            return

        available = combatant.char.character_points if combatant.char else 0
        if cp_amount > available:
            await ctx.session.send_line(
                f"  Not enough CP (have {available}, want {cp_amount}).")
            return

        combatant.soak_cp = cp_amount
        await ctx.session.send_line(
            ansi.combat_msg(
                f"You set {cp_amount} CP for soak. "
                f"(Will be spent only if you take a hit.)"
            )
        )


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
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)


class FleeCommand(BaseCommand):
    key = "flee"
    aliases = ["run", "retreat"]
    help_text = (
        "Attempt to escape combat. Opposed roll: your running\n"
        "vs. opponents. Fail = lose your action this round.\n"
        "\n"
        "TIP: Use fulldodge for a round to survive, then flee next."
    )
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
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)


class PassCommand(BaseCommand):
    key = "pass"
    aliases = []
    help_text = "Declaration phase: take no action. Posing phase: use auto-generated pose."
    usage = "pass"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        from engine.combat import CombatPhase

        # ── Posing phase: submit an auto-generated pose ──
        if combat.phase == CombatPhase.POSING:
            pose_state = combat._pose_state.get(char["id"])
            if not pose_state:
                await ctx.session.send_line("  You have no pose pending.")
                return
            if pose_state["status"] != "pending":
                await ctx.session.send_line(
                    ansi.combat_msg("You've already submitted your pose.")
                )
                return

            auto_pose = combat.generate_auto_pose(char["id"])
            combat.set_pose_status(char["id"], "passed", text=auto_pose)
            await ctx.session.send_line(
                ansi.combat_msg(
                    "You pass. The engine will narrate your actions this round."
                )
            )
            await _on_pose_submitted(combat, ctx)
            return

        # ── Declaration phase: take no action this round ──
        action = CombatAction(action_type=ActionType.OTHER, description="passes")
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return

        await ctx.session.send_line(ansi.combat_msg("You pass this round."))
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)


class CombatStatusCommand(BaseCommand):
    key = "+combat"
    aliases = ["combat", "cs", "+cs"]
    help_text = "Show current combat status."
    usage = "+combat [/rolls|/status]"
    valid_switches = ["rolls", "status"]

    async def execute(self, ctx: CommandContext):
        if "rolls" in ctx.switches:
            return await self._show_rolls(ctx)
        # Default (no switch or /status): show status
        return await self._show_status(ctx)

    async def _show_status(self, ctx):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        lines = combat.get_status()
        for line in lines:
            await ctx.session.send_line(ansi.combat_msg(line))

    async def _show_rolls(self, ctx):
        char = ctx.session.character
        combat = _active_combats.get(char["room_id"])
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        rolls = getattr(combat, "_last_initiative_rolls", {})
        if not rolls:
            await ctx.session.send_line("  No initiative rolls recorded yet.")
            return

        await ctx.session.send_line(
            ansi.combat_msg(f"Initiative rolls \u2014 Round {combat.round_num}:")
        )
        for name, display in rolls.items():
            await ctx.session.send_line(f"  {name}: {display}")


class ResolveCommand(BaseCommand):
    key = "resolve"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Force-resolve the combat round (builder/admin). Skips posing window."
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

        # Admin resolve skips posing — auto-generate all poses and flush
        await _apply_combat_wear(combat, ctx)

        if combat.is_over:
            await _broadcast_events_paced(events, ctx.session_mgr, combat.room_id)
            await _send_combat_ended(combat.room_id, ctx.session_mgr)
            _remove_combat(combat.room_id)
            return

        # Auto-generate poses for everyone and flush immediately
        for cid in list(combat._pose_state.keys()):
            auto_pose = combat.generate_auto_pose(cid)
            combat.set_pose_status(cid, "passed", text=auto_pose)

        await _flush_action_log(combat, ctx)


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
    help_text = (
        "View or change range to a target.\n"
        "\n"
        "BANDS: pointblank (5), short (10), medium (15), long (20)\n"
        "\n"
        "EXAMPLES:\n"
        "  range stormtrooper        -- check range\n"
        "  range stormtrooper short  -- set to short"
    )
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
    help_text = (
        "Take cover behind objects. Adds difficulty to ranged\n"
        "attacks against you. Costs an action.\n"
        "\n"
        "LEVELS: quarter (+1D), half (+2D), 3/4 (+3D),\n"
        "full (untargetable but cannot shoot).\n"
        "\n"
        "Attacking from cover reduces it to quarter.\n"
        "Max cover depends on the room environment."
    )
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
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)


class ForcePointCommand(BaseCommand):
    key = "forcepoint"
    aliases = ["fp", "+fp"]
    help_text = (
        "Spend a Force Point to DOUBLE all dice this round.\n"
        "Must declare during declaration phase. Cannot be\n"
        "used same round as CP spending.\n"
        "\n"
        "FP spent heroically may be returned at adventure end.\n"
        "FP spent selfishly are lost and may earn a DSP."
    )
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
        ParryCommand(), FullParryCommand(), SoakCommand(),
        AimCommand(), FleeCommand(), PassCommand(),
        CombatStatusCommand(), ResolveCommand(), DisengageCommand(),
        RangeCommand(), CoverCommand(), ForcePointCommand(),
        CombatPoseCommand(), CombatRollsCommand(),
        ChallengeCommand(), AcceptCommand(), DeclineCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)


class CombatPoseCommand(BaseCommand):
    key = "cpose"
    aliases = ["combatpose"]
    help_text = "Submit your narrative pose during the posing window."
    usage = "cpose <your narrative text>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        combat, combatant = _ensure_in_combat(char, char["room_id"])
        if not combat:
            await ctx.session.send_line("  You're not in combat.")
            return

        from engine.combat import CombatPhase
        if combat.phase != CombatPhase.POSING:
            await ctx.session.send_line(
                "  Not in the posing phase right now. "
                "Wait until after resolution to write your pose."
            )
            return

        pose_state = combat._pose_state.get(char["id"])
        if not pose_state:
            await ctx.session.send_line("  You have no pose pending.")
            return
        if pose_state["status"] != "pending":
            await ctx.session.send_line(
                ansi.combat_msg("You've already submitted your pose this round.")
            )
            return

        if not ctx.args or not ctx.args.strip():
            await ctx.session.send_line(
                "  Usage: cpose <your narrative text>"
            )
            await ctx.session.send_line(
                "  Example: cpose Tundra dives behind the crate, "
                "firing two quick shots at the stormtrooper."
            )
            return

        pose_text = ctx.args.strip()
        combat.set_pose_status(char["id"], "ready", text=pose_text)
        await ctx.session.send_line(
            ansi.combat_msg("Pose submitted! Waiting for other combatants...")
        )
        await _on_pose_submitted(combat, ctx)


class CombatRollsCommand(BaseCommand):
    key = "crolls"
    aliases = ["combat rolls"]
    help_text = "Show the detailed initiative roll breakdown for this round."
    usage = "crolls  (or +combat/rolls)"

    async def execute(self, ctx: CommandContext):
        ctx.switches = ["rolls"]
        cmd = CombatStatusCommand()
        await cmd.execute(ctx)

class ChallengeCommand(BaseCommand):
    key = "challenge"
    aliases = ["duel"]
    help_text = (
        "Challenge another player to combat in a contested zone.\n"
        "The target must 'accept <your name>' within 10 minutes to consent.\n"
        "Both parties may then freely attack each other.\n"
        "Challenges expire after 10 minutes."
    )
    usage = "challenge <player>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: challenge <player name>")
            return

        char = ctx.session.character
        room_id = char["room_id"]

        # Must be in contested or lawless zone to bother
        from engine.security import get_effective_security, SecurityLevel
        sec = await get_effective_security(room_id, ctx.db, character=char)
        if sec == SecurityLevel.SECURED:
            await ctx.session.send_line(
                "  \033[1;33mImperial security would immediately stop any duel here.\033[0m"
            )
            return

        # Find target player
        from engine.matching import match_in_room, MatchResult
        match = await match_in_room(
            ctx.args.strip(), room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
        )
        if not match.found or match.candidate.obj_type != "character":
            await ctx.session.send_line(f"  No player named '{ctx.args.strip()}' here.")
            return

        target_id = match.id
        target_name = match.candidate.data.get("name", "Unknown")
        a_id = char["id"]

        # Already have active consent?
        now = _time.time()
        if (
            _pvp_active.get((a_id, target_id), 0) > now - _PVP_CHALLENGE_TTL or
            _pvp_active.get((target_id, a_id), 0) > now - _PVP_CHALLENGE_TTL
        ):
            await ctx.session.send_line(
                f"  You already have active combat consent with {target_name}."
            )
            return

        # Record pending challenge
        _pvp_consent[(a_id, target_id)] = now

        await ctx.session.send_line(
            f"  \033[1;37mYou challenge {target_name} to combat.\033[0m "
            f"They must type '\033[1;33maccept {char['name']}\033[0m' to consent."
        )

        # Notify target
        target_sess = None
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] == target_id:
                target_sess = s
                break
        if target_sess:
            await target_sess.send_line(
                f"\n  \033[1;31m{char['name']} challenges you to combat!\033[0m\n"
                f"  Type '\033[1;33maccept {char['name']}\033[0m' to consent. "
                f"(Expires in 10 minutes.)\n"
            )


class AcceptCommand(BaseCommand):
    key = "accept"
    help_text = "Accept a combat challenge from another player."
    usage = "accept <challenger name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: accept <challenger name>")
            return

        char = ctx.session.character
        room_id = char["room_id"]

        from engine.matching import match_in_room
        match = await match_in_room(
            ctx.args.strip(), room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
        )
        if not match.found or match.candidate.obj_type != "character":
            await ctx.session.send_line(f"  No player named '{ctx.args.strip()}' here.")
            return

        challenger_id = match.id
        challenger_name = match.candidate.data.get("name", "Unknown")
        t_id = char["id"]
        now = _time.time()

        # Check pending challenge from them to us
        pending_ts = _pvp_consent.get((challenger_id, t_id), 0)
        if not pending_ts or now - pending_ts > _PVP_CHALLENGE_TTL:
            await ctx.session.send_line(
                f"  {challenger_name} hasn't challenged you, "
                f"or the challenge has expired."
            )
            return

        # Activate consent (both directions)
        _pvp_active[(challenger_id, t_id)] = now
        _pvp_consent.pop((challenger_id, t_id), None)

        await ctx.session.send_line(
            f"  \033[1;31mYou accept {challenger_name}'s challenge.\033[0m "
            f"Combat consent is active for 10 minutes."
        )

        # Notify challenger
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] == challenger_id:
                await s.send_line(
                    f"\n  \033[1;31m{char['name']} accepts your challenge!\033[0m "
                    f"Combat consent is active.\n"
                )
                break

        # Broadcast to room
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"\033[1;33m{challenger_name} and {char['name']} have agreed to settle "
            f"their differences the old-fashioned way.\033[0m",
            exclude=[challenger_id, t_id],
        )


class DeclineCommand(BaseCommand):
    key = "decline"
    aliases = ["refuse"]
    help_text = "Decline a combat challenge from another player."
    usage = "decline [challenger name]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        t_id = char["id"]
        now = _time.time()

        # Find any pending challenge targeting this player
        pending = []
        for (a_id, b_id), ts in list(_pvp_consent.items()):
            if b_id == t_id and now - ts <= _PVP_CHALLENGE_TTL:
                pending.append((a_id, ts))

        if not pending:
            await ctx.session.send_line("  No pending challenges to decline.")
            return

        # If a name was given, match it; otherwise decline the most recent
        challenger_id = None
        challenger_name = "someone"
        if ctx.args:
            from engine.matching import match_in_room
            match = await match_in_room(
                ctx.args.strip(), char["room_id"], char["id"], ctx.db,
                session_mgr=ctx.session_mgr,
            )
            if match.found and match.candidate.obj_type == "character":
                challenger_id = match.id
                challenger_name = match.candidate.data.get("name", "Unknown")
        else:
            # Most recent pending challenge
            pending.sort(key=lambda x: x[1], reverse=True)
            challenger_id = pending[0][0]

        if not challenger_id:
            await ctx.session.send_line("  No matching challenge found.")
            return

        # Remove the pending challenge
        removed = _pvp_consent.pop((challenger_id, t_id), None)
        if not removed:
            await ctx.session.send_line("  No pending challenge from that player.")
            return

        # Look up challenger name if we don't have it
        if challenger_name == "someone":
            try:
                rows = await ctx.db.fetchall(
                    "SELECT name FROM characters WHERE id = ?", (challenger_id,)
                )
                if rows:
                    challenger_name = rows[0]["name"]
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass

        await ctx.session.send_line(
            f"  You decline {challenger_name}'s challenge."
        )

        # Notify challenger
        for s in ctx.session_mgr.sessions_in_room(char["room_id"]):
            if s.character and s.character["id"] == challenger_id:
                await s.send_line(
                    f"  \033[2m{char['name']} declines your challenge.\033[0m"
                )
                break
