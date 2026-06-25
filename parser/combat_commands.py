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

# ── Active combats: W.2.4 tuple key ──
#
# Key shape: (room_id, wilderness_x, wilderness_y).
#
# - Regular rooms always key as (room_id, None, None), so non-wilderness
#   behavior is byte-identical to pre-W.2.4 (the dict accepts both keys).
# - Wilderness combats key as (sentinel_room_id, wx, wy) so two combats
#   at different tiles of the same sentinel don't collide on a single
#   shared CombatInstance.
#
# The pre-W.2.4 contract was ``dict[int, CombatInstance]``. v42 §8.9
# captures the rationale for tuple-key (Option A) over the alternatives
# (separate _wilderness_combats dict, WildernessCombatInstance subclass).
_CombatKey = tuple[int, "int | None", "int | None"]
_active_combats: dict[_CombatKey, CombatInstance] = {}

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


def _combat_key_for(char) -> _CombatKey:
    """W.2.4: derive a combat-instance key from a character.

    Accepts a char dict (the normal Path A shape) or a Character object.
    Returns ``(room_id, wilderness_x, wilderness_y)`` — wilderness coords
    are None for regular rooms.

    Two PCs in the same regular room get the same key. Two PCs in
    wilderness at the same (wx, wy) get the same key. Two PCs in
    wilderness at different (wx, wy) get DIFFERENT keys, even though
    their ``room_id`` field is the same sentinel — this is the bug
    W.2.4 is designed to fix.
    """
    if char is None:
        return (0, None, None)
    if isinstance(char, dict):
        room_id = char.get("room_id", 0)
        slug = char.get("wilderness_region_slug")
        wx = char.get("wilderness_x")
        wy = char.get("wilderness_y")
    else:
        room_id = getattr(char, "room_id", 0)
        slug = getattr(char, "wilderness_region_slug", None)
        wx = getattr(char, "wilderness_x", None)
        wy = getattr(char, "wilderness_y", None)
    # Both wilderness coords must be present to count as wilderness;
    # if either is None we fall back to regular-room keying so the
    # combat doesn't fragment by stale state.
    if slug and wx is not None and wy is not None:
        return (room_id, wx, wy)
    return (room_id, None, None)


def _wilderness_anchor_for(char) -> tuple:
    """Return (slug, wx, wy) tuple for a char's wilderness anchor.

    For regular-room chars, returns (None, None, None). Used by
    ``_get_or_create_combat`` to seed the CombatInstance's wilderness
    fields when creating a new one.
    """
    if char is None:
        return (None, None, None)
    if isinstance(char, dict):
        slug = char.get("wilderness_region_slug")
        wx = char.get("wilderness_x")
        wy = char.get("wilderness_y")
    else:
        slug = getattr(char, "wilderness_region_slug", None)
        wx = getattr(char, "wilderness_x", None)
        wy = getattr(char, "wilderness_y", None)
    if slug and wx is not None and wy is not None:
        return (slug, wx, wy)
    return (None, None, None)


def _get_or_create_combat(char, cover_max: int = 0) -> CombatInstance:
    """W.2.4: get-or-create the combat instance for this character.

    Pre-W.2.4 took ``room_id: int``. Now takes a char (dict or Character
    object) so the keying can include wilderness coords. The new
    CombatInstance is seeded with the char's wilderness anchor so
    ``combat.broadcast_source()`` can filter narration to the right
    tile.
    """
    key = _combat_key_for(char)
    if key not in _active_combats:
        slug, wx, wy = _wilderness_anchor_for(char)
        room_id = key[0]
        _active_combats[key] = CombatInstance(
            room_id, _get_skill_reg(), cover_max=cover_max,
            wilderness_region_slug=slug,
            wilderness_x=wx,
            wilderness_y=wy,
        )
    return _active_combats[key]


def _combat_finished(combat) -> bool:
    """True when the fight is actually over.

    The engine's CombatInstance.is_over only counts heads (<=1 active
    combatant), so a CO-OP PvE kill -- 2+ allied PCs drop the last NPC --
    reads as 'still active' forever: disengage refuses and flee resolves an
    opposed roll vs an ALLY, stranding both players (QA 2026-06-23). A fight
    is over unless two MUTUALLY HOSTILE combatants can both still act: NPCs
    are hostile to every PC; two PCs are hostile only under a live PvP pact
    (_pvp_active).
    """
    active = combat.active_combatants
    if len(active) <= 1:
        return True
    npcs = [c for c in active if c.is_npc]
    pcs = [c for c in active if not c.is_npc]
    if npcs and pcs:
        return False                      # NPC(s) vs PC(s) -- a real fight
    if len(pcs) <= 1:
        return True                       # only NPCs, or a lone PC
    # Only PCs remain: continues iff some PvP pact between them is still live.
    now = _time.time()
    cutoff = now - _PVP_CHALLENGE_TTL
    ids = [c.id for c in pcs]
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            a, b = ids[i], ids[j]
            if (_pvp_active.get((a, b), 0) > cutoff or
                    _pvp_active.get((b, a), 0) > cutoff):
                return False              # live PvP -- a real fight
    return True                           # only allied PCs remain -- finished


def _remove_combat(char_or_combat):
    """W.2.4: remove the combat instance for this char (or combat).

    Accepts either:
      - A char dict / Character object — keys via _combat_key_for
      - A CombatInstance — keys via the instance's own room_id +
        wilderness fields

    The second form matters because some teardown paths (auto-resolve,
    combat-ended) have a ``combat`` in hand and need to remove by the
    same key it was registered under.
    """
    if isinstance(char_or_combat, CombatInstance):
        combat = char_or_combat
        key = (combat.room_id,
               combat.wilderness_x,
               combat.wilderness_y)
    else:
        key = _combat_key_for(char_or_combat)
    combat = _active_combats.pop(key, None)
    if combat:
        # Cancel any pending pose-grace timer so it doesn't fire into dead combat.
        handle = getattr(combat, '_grace_timer_handle', None)
        if handle and not handle.done():
            handle.cancel()
        # Clean up NPC behaviors for this combat's combatants
        for cid in list(combat.combatants.keys()):
            _npc_behaviors.pop(cid, None)


def _ensure_in_combat(char: dict, room_id: int = None) -> tuple:
    """Returns (combat, combatant) or (None, None) if not in combat.

    W.2.4: room_id arg is preserved for back-compat but ignored. The
    char's wilderness state determines the key. If callers pass a
    room_id that doesn't match char['room_id'], the char wins.
    """
    key = _combat_key_for(char)
    combat = _active_combats.get(key)
    if not combat:
        return None, None
    combatant = combat.get_combatant(char["id"])
    return combat, combatant


async def _broadcast_events(events, session_mgr, room_id, exclude=None,
                            source_char=None):
    """Send combat events to the room (immediate, no pacing).

    W.2.4: ``source_char`` is the Path B filter; callers in
    combat_commands.py pass ``combat.broadcast_source()`` so the
    broadcast is restricted to the right wilderness tile. In regular
    rooms source_char is None (or a regular-room dict) and the helper
    behaves byte-identically to pre-W.2.4.
    """
    for event in events:
        await session_mgr.broadcast_to_room(
            room_id, event.text, exclude=exclude, source_char=source_char)


def _extract_actor_name(text: str):
    """Return the first name-token from a narrative line, or None for headers."""
    stripped = text.lstrip()
    if not stripped or stripped.startswith(("---", "─", "[COMBAT]", "Turn order")):
        return None
    stripped = stripped.lstrip("▸◆ ")
    parts = stripped.split()
    return parts[0] if parts else None


async def _broadcast_separator(session_mgr, room_id, source_char=None):
    """Emit a visual phase-separator line. W.2.4: tile-aware."""
    await session_mgr.broadcast_to_room(
        room_id, "  " + "─" * 45, exclude=None,
        source_char=source_char,
    )


async def _broadcast_events_paced(events, session_mgr, room_id,
                                   delay: float = 0.6, exclude=None,
                                   source_char=None):
    """Send combat events with a short delay between each actor's block.

    For damage events (event.you_text set, event.targets non-empty), the
    target session receives the personalised ◆ YOU variant; all others see
    the standard room narrative.

    W.2.4: ``source_char`` is the Path B tile filter.
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
            for sess in session_mgr.sessions_in_room(
                    room_id, source_char=source_char):
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
                # Web clients also receive the structured inspector event (AC4)
                if event.combat_resolution_event is not None:
                    await sess.send_json("combat_resolution_event",
                                         event.combat_resolution_event)
        else:
            await session_mgr.broadcast_to_room(
                room_id, event.text, exclude=exclude,
                source_char=source_char)
            # Web clients also receive the structured inspector event on room-wide hits
            if event.combat_resolution_event is not None:
                await session_mgr.broadcast_json_to_room(
                    room_id, "combat_resolution_event",
                    event.combat_resolution_event, exclude=exclude,
                    source_char=source_char,
                )


async def _send_combat_state(combat, session_mgr):
    """Send combat_state JSON to all WebSocket sessions in the combat room.

    Telnet sessions receive nothing (send_json is a no-op for them).
    Each player gets a personalised payload with viewer_id set.

    W.2.4: uses combat.broadcast_source() to filter to the right tile.
    """
    room_id = combat.room_id
    sessions = session_mgr.sessions_in_room(
        room_id, source_char=combat.broadcast_source())
    async def _one(sess):
        char = getattr(sess, "character", None)
        viewer_id = char["id"] if char else None
        payload = combat.to_hud_dict(viewer_id=viewer_id)
        await sess.send_json("combat_state", payload)
    # Send to all viewers concurrently so one slow/backpressured WS client can't
    # head-of-line-block the combat round + the tick loop (verify-fix 2026-06-18).
    await asyncio.gather(*[_one(s) for s in sessions], return_exceptions=True)


async def _send_combat_ended(room_id, session_mgr, source_char=None):
    """Notify WebSocket clients that combat is over.

    W.2.4: ``source_char`` defaults to None for caller back-compat;
    every combat_commands.py call site now passes
    ``combat.broadcast_source()``.
    """
    for sess in session_mgr.sessions_in_room(
            room_id, source_char=source_char):
        # G4: keep the combat_state schema uniform — the active push always
        # carries `events`, so the termination push does too (empty). The
        # client clears its feed on the active=False branch regardless, but a
        # uniform shape keeps consumers from special-casing the sentinel.
        await sess.send_json("combat_state", {"active": False, "events": []})


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
        # Snapshot NPC combatants BEFORE resolution — resolve_round() runs
        # _cleanup() which removes dead combatants, so the mob-grind reward
        # (which needs the just-killed NPCs) must capture them here first.
        _pre_npcs = [c for c in combat.combatants.values()
                     if c.is_npc and c.char]
        events = combat.resolve_round()
        # Don't broadcast events to room yet — they go in the Action Log
        # But we DO need to apply wear and persist wounds immediately
        await _apply_combat_wear(combat, ctx, _pre_npcs)
        await _award_mob_grind_rewards(combat, ctx, _pre_npcs)
        await _award_early_combat_cp(combat, ctx, _pre_npcs)

        # Phase 7c (May 23 2026): city-guard combat-round triggers.
        # Check if any city guards in this room should now join
        # the fight (attacker-of-citizen or bountied-target triggers
        # per design v1.2 §7.2). Skip if combat is over — no point
        # adding guards to a finished fight.
        if not _combat_finished(combat):
            await _check_city_guard_triggers(combat, ctx)

        if _combat_finished(combat):
            # Combat ended — broadcast final events directly, no posing
            _src = combat.broadcast_source()
            await _broadcast_events_paced(events, ctx.session_mgr,
                                          combat.room_id, source_char=_src)
            await _send_combat_ended(combat.room_id, ctx.session_mgr,
                                     source_char=_src)
            # Achievement: combat_victory for surviving PCs who actually won.
            # "Won" = PC can still act (can_act_now covers wound ladder + stun-KO)
            # AND no hostile NPC survived still able to act (guards against the
            # edge case where a PC goes down but the fight ended on a different
            # trigger). The old `wound_level.value < 5` check admitted
            # INCAPACITATED PCs (value 4 < 5 = True) who had been defeated.
            try:
                from engine.achievements import on_combat_victory
                _active_npcs_remain = any(
                    c.is_npc and c.char and c.char.can_act_now()
                    for c in combat.combatants.values()
                )
                for c in combat.combatants.values():
                    if (not c.is_npc and c.char
                            and c.char.can_act_now()
                            and not _active_npcs_remain):
                        _csess = ctx.session_mgr.find_by_character(c.id)
                        if _csess:
                            await on_combat_victory(ctx.db, c.id, session=_csess)
            except Exception as _e:
                log.debug("silent except in parser/combat_commands.py:209: %s", _e, exc_info=True)
            # F.8.c.2.b: CW tutorial chain — combat_won completion.
            # Iterate surviving PCs × defeated NPCs and fire the hook
            # once per combination of (winner, enemy_template). The
            # template is stashed in ai_config_json.chain_enemy_template
            # for chain-relevant NPCs; non-chain NPCs simply have no
            # tag and the hook no-ops on them. Fires BEFORE the NPC
            # cleanup that nulls room_id, so we still have the
            # ai_config row available.
            try:
                from engine.chain_events import on_combat_won
                import json as _ccj
                # Collect defeated NPC templates (incapacitated/dead)
                _defeated_templates: list = []
                for c in combat.combatants.values():
                    if not c.is_npc or not c.char:
                        continue
                    # "Defeated" = OUT OF THE FIGHT, using combat's own
                    # elimination predicate (active_combatants filters on
                    # can_act_now). can_act_now() is False for Incapacitated+
                    # (wound_level >= 4) AND for a STUN-KO (unconscious_until
                    # set while wound_level stays STUNNED, per R&E p83). The old
                    # `wound_level.value < 4` check missed the stun case — so
                    # capturing a target by STUN, which the Bounty Hunter chain
                    # EXPLICITLY recommends ("attack <t> stun pays more"), never
                    # fired combat_won and stranded the player on the capture
                    # step. (QA live finding 2026-06-20.)
                    if c.char.can_act_now():
                        continue
                    try:
                        _npc_row = await ctx.db.get_npc(c.id)
                    except Exception:
                        _npc_row = None
                    if not _npc_row:
                        continue
                    _ai_raw = _npc_row.get("ai_config_json", "{}") or "{}"
                    if isinstance(_ai_raw, str):
                        try:
                            _ai = _ccj.loads(_ai_raw)
                        except Exception:
                            _ai = {}
                    else:
                        _ai = _ai_raw or {}
                    _tpl = (_ai.get("chain_enemy_template") or "").strip()
                    if _tpl:
                        _defeated_templates.append(_tpl)
                # Fire one hook per (surviving PC, template) pair
                if _defeated_templates:
                    from collections import Counter
                    _tpl_counts = Counter(_defeated_templates)
                    for c in combat.combatants.values():
                        if c.is_npc or not c.char:
                            continue
                        if c.char.wound_level.value >= 5:
                            continue  # PC went down too
                        _csess = ctx.session_mgr.find_by_character(c.id)
                        if not _csess or not _csess.character:
                            continue
                        for _tpl, _ct in _tpl_counts.items():
                            _adv = await on_combat_won(
                                ctx.db, _csess.character, _tpl, _ct,
                            )
                            if _adv:
                                # F.8.c.2.c: graduation teleport via
                                # the per-survivor session, not ctx
                                # — combat resolution is room-scoped
                                # and ctx.session may belong to any
                                # combatant.
                                try:
                                    from engine.chain_graduation import (
                                        execute_pending_teleport,
                                    )
                                    _grad_ctx = type(ctx)(
                                        session=_csess,
                                        raw_input=ctx.raw_input,
                                        command=ctx.command,
                                        args=ctx.args,
                                        args_list=ctx.args_list,
                                        db=ctx.db,
                                        session_mgr=ctx.session_mgr,
                                    )
                                    await execute_pending_teleport(
                                        _grad_ctx, _csess.character,
                                    )
                                except Exception as _gerr:
                                    log.debug(
                                        "[chain_events] combat-graduation "
                                        "teleport failed: %s",
                                        _gerr, exc_info=True,
                                    )
            except Exception as _ce:
                log.debug("silent except in parser/combat_commands.py chain_events combat hook: %s",
                          _ce, exc_info=True)
            # Cleanup: remove incapacitated/dead NPCs from room
            try:
                for c in combat.combatants.values():
                    if c.is_npc and c.char and c.char.wound_level.value >= 4:
                        await ctx.db.update_npc(c.id, room_id=None)
            except Exception:
                log.warning("NPC cleanup after combat failed", exc_info=True)
            _remove_combat(combat)
            return

        # Combat continues — send private briefings + open posing window
        await _check_city_guard_engagement(combat, ctx)
        await _send_combat_state(combat, ctx.session_mgr)
        await _send_private_briefings(combat, ctx)
        await _auto_generate_npc_poses(combat)
        await _start_posing_window(combat, ctx)


async def _check_city_guard_engagement(combat, ctx):
    """Phase 7c (May 23 2026): after each combat round, scan the
    room for city guards that should now engage based on the
    design v1.2 §7.2 combat-round triggers:

      - The attacker has attacked a citizen of this guard's city
        in the current combat session.
      - A combatant has an active bounty whose ``claimed_by`` is
        a citizen of this guard's city (re-evaluated each round
        in case a citizen BH claims the bounty mid-fight).

    Newly-engaged guards are added to the combat via
    ``combat.add_combatant`` so they roll initiative next round
    and the auto-declare layer picks them up.

    Wilderness combat is skipped — city guards are room-scoped
    and the design only places them in city rooms. The check is
    fail-soft: any internal exception logs at warning and combat
    continues unaffected.
    """
    # Phase 7c skips wilderness combat (no city rooms there).
    if combat.wilderness_region_slug is not None:
        return
    try:
        from engine.city_guard_runtime import (
            evaluate_combat_round_triggers,
        )
        from engine.npc_combat_ai import (
            build_npc_character, get_npc_behavior,
        )

        # Pull every NPC currently in the room. Most rooms have
        # zero city guards, so this is cheap. We re-pull each
        # round because guards could have been assigned mid-
        # combat via @city guard-assign (rare but possible).
        room_npc_rows = await ctx.db.get_npcs_in_room(combat.room_id)
        if not room_npc_rows:
            return

        combatant_ids = list(combat.combatants.keys())
        to_add = await evaluate_combat_round_triggers(
            ctx.db, combat.room_id, combatant_ids,
            combat.attacks_made, room_npc_rows,
        )
        if not to_add:
            return

        # Add each engaging guard to the combat. Initiative is
        # rolled at the start of the next round in the standard
        # `resolve_round` path, so we don't need to roll it here.
        for guard_row in to_add:
            gid = guard_row.get("id")
            if gid is None:
                continue
            if combat.get_combatant(int(gid)):
                continue  # Defensive: race against another caller
                          # — already added.

                # build_npc_character handles missing-stats gracefully
            npc_char = build_npc_character(guard_row)
            if npc_char is None:
                log.debug(
                    "[city_guard_phase7c] guard #%s has no combat "
                    "stats; skipping engagement", gid,
                )
                continue
            combatant = combat.add_combatant(npc_char)
            combatant.is_npc = True
            _npc_behaviors[int(gid)] = get_npc_behavior(guard_row)

            # Roll initiative for the new arrival so they act
            # on the next round (the standard resolve_round
            # path increments round_num and re-rolls everyone).
            log.info(
                "[city_guard_phase7c] guard #%s engaged in "
                "combat at room %s (round %s)",
                gid, combat.room_id, combat.round_num,
            )
    except Exception as e:
        log.warning(
            "[city_guard_phase7c] _check_city_guard_engagement "
            "failed (no guards joined this round): %s",
            e, exc_info=True,
        )


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
                    source_char=combat.broadcast_source(),
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

    # W.2.4: cache broadcast_source once for all three sends.
    _src = combat.broadcast_source()

    await ctx.session_mgr.broadcast_to_room(combat.room_id, header,
                                            source_char=_src)

    for init_val, char_id, text in sorted_poses:
        c = combat.get_combatant(char_id)
        name = c.name if c else "Unknown"
        if text:
            line = f"  (Init {init_val:2d}) [{name}] {text}"
        else:
            line = f"  (Init {init_val:2d}) [{name}] hesitates, doing nothing."
        await ctx.session_mgr.broadcast_to_room(combat.room_id, line,
                                                source_char=_src)
        await asyncio.sleep(0.5)  # Pacing between combatant poses

    await ctx.session_mgr.broadcast_to_room(combat.room_id, footer,
                                            source_char=_src)

    # Clear pose state
    combat._pose_state = {}
    combat.pose_deadline = None

    # Advance to next round
    await _advance_to_next_round(combat, ctx)


async def _advance_to_next_round(combat, ctx):
    """Roll initiative, auto-declare NPCs, prompt players."""
    # Phase separator
    _src = combat.broadcast_source()
    await asyncio.sleep(1.1)
    await _broadcast_separator(ctx.session_mgr, combat.room_id,
                               source_char=_src)

    # Auto-roll next initiative
    events = combat.roll_initiative()
    await _broadcast_events_paced(events, ctx.session_mgr, combat.room_id,
                                  delay=0.3, source_char=_src)
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


async def _check_city_guard_triggers(combat, ctx):
    """Phase 7c (May 23 2026): after a combat round resolves,
    check whether any city guards in the room should now join
    the fight per design v1.2 §7.2.

    Triggers (both evaluated per round):
      - Attacker-of-citizen: any combatant attacked a citizen
        of a guard's city during this combat session.
      - Bountied-target-claimed-by-citizen-BH: any combatant
        has a bounty claimed by a citizen of a guard's city.

    Guards that fire engage are added to the existing combat
    instance as new combatants with hostile NPC behavior. They
    will auto-declare attacks against the triggering character
    on the next round via the established `_auto_declare_npc_
    actions` path.

    Fail-soft: any internal exception is logged at debug; the
    combat continues without the added guards. A broken guard
    trigger MUST NOT block combat resolution.
    """
    try:
        from engine.city_guard_runtime import (
            evaluate_combat_round_triggers,
        )
        from engine.npc_combat_ai import (
            build_npc_character, get_npc_behavior,
        )
        from engine.combat import CombatBehavior as _CB

        # Get all NPCs in the combat room. In wilderness combats
        # combat.room_id is the sentinel; this still works since
        # city guards live in real rooms.
        room_npcs = await ctx.db.get_npcs_in_room(combat.room_id)
        combatant_ids = list(combat.combatants.keys())
        attacks = getattr(combat, "attacks_made", set()) or set()

        to_add = await evaluate_combat_round_triggers(
            ctx.db, combat.room_id, combatant_ids,
            attacks, room_npcs,
        )
        if not to_add:
            return

        added_names = []
        for npc_row in to_add:
            npc_id = npc_row.get("id")
            if npc_id is None:
                continue
            if combat.get_combatant(int(npc_id)):
                continue  # Already in
            npc_char = build_npc_character(npc_row)
            if not npc_char:
                continue
            combatant = combat.add_combatant(npc_char)
            combatant.is_npc = True
            # Force aggressive behavior on triggered guards so
            # they actually engage (regardless of their stored
            # combat_behavior). The trigger condition is the
            # whole point of their joining.
            _npc_behaviors[int(npc_id)] = _CB.AGGRESSIVE
            added_names.append(npc_row.get("name", "guard"))

        if added_names:
            log.info(
                "[city_guard] Phase 7c triggered engage: %s "
                "joined combat in room %s",
                added_names, combat.room_id,
            )
    except Exception as e:
        log.debug(
            "[city_guard] _check_city_guard_triggers failed "
            "(no guards added): %s", e, exc_info=True,
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
    for sess in ctx.session_mgr.sessions_in_room(
            combat.room_id, source_char=combat.broadcast_source()):
        char = getattr(sess, "character", None)
        if char and char["id"] in notified:
            continue
        await sess.send_line(generic_line)


async def _award_mob_grind_rewards(combat, ctx, pre_npcs):
    """Solo-PvE mob-grind reward (2026-06-21).

    resolve_round() runs _cleanup() which REMOVES dead combatants before
    _apply_combat_wear, so a reward keyed on NPC death cannot fire from inside
    that loop. We instead receive the pre-resolution NPC-combatant snapshot
    (`pre_npcs`) and, for any that LEFT combat this round while at wound_level
    DEAD (killed, not fled), pay the killer a small daily-capped credit trickle
    + prestige (engine/hunting_rewards). The NPC db row survives death
    (room_id=None), so its ai_config is still readable for the huntable
    predicate. NO character points. Requires a live killer session (the
    actively-grinding PC) — which also sidesteps any NPC/PC id collision on
    last_attacker_id. Best-effort: a reward failure can never break combat.
    """
    if not pre_npcs:
        return
    try:
        from engine.character import WoundLevel as _WLM
        from engine.hunting_rewards import is_huntable_mob, on_huntable_kill
        from datetime import datetime as _dtM, timezone as _tzM
    except Exception:
        return
    _day = None
    for c in pre_npcs:
        try:
            if c.id in combat.combatants:
                continue  # survived the round
            if not (c.char and c.char.wound_level.value >= _WLM.DEAD.value):
                continue  # left combat for another reason (fled), not killed
            _kid = c.last_attacker_id
            if _kid is None or not ctx.session_mgr:
                continue
            _sess = ctx.session_mgr.find_by_character(int(_kid))
            if not (_sess and _sess.character):
                continue  # killer offline / not a live PC
            npc_row = await ctx.db.get_npc(c.id)
            if not npc_row or not is_huntable_mob(npc_row):
                continue  # special NPC (its own reward) or no row
            if _day is None:
                _day = _dtM.now(_tzM.utc).date().isoformat()
            summary = await on_huntable_kill(
                ctx.db, _sess.character, npc_row, day_stamp=_day)
            if summary:
                await _sess.send_line(
                    f"  \033[2m(You recover {summary['reward']} cr from "
                    f"{c.name}. Hunting log: {summary['total_kills']} "
                    f"felled.)\033[0m"
                )
                if summary.get("title_label"):
                    await _sess.send_line(
                        "  \033[1;33m✦ Title earned: "
                        f"{summary['title_label']} — wear it with "
                        f"+title wear {summary['title_key']}.\033[0m"
                    )
        except Exception as _e:
            log.warning("Mob-grind reward error for NPC %s: %s",
                        getattr(c, "id", None), _e, exc_info=True)


async def _award_early_combat_cp(combat, ctx, pre_npcs):
    """Early-game combat CP faucet (fun2-combat-cp, 2026-06-25).

    For each NPC that LEFT combat this round at wound_level DEAD and whose
    killing blow is attributed to a live PC, check whether that PC still has
    early_combat_cp kills remaining under the lifetime cap. If so, award +1 CP
    via the milestone funnel (tagged ``"early_combat"``) and emit a brief
    player-visible line. After the first 5 kills the faucet is permanently dry
    for that character.

    Mirrors ``_award_mob_grind_rewards`` structurally: iterates ``pre_npcs``,
    uses ``last_attacker_id`` for kill attribution, gates on a live online
    session, and wraps every NPC iteration in a per-NPC try/except so a
    single bad NPC row can never abort the rest of the loop or disturb combat.
    The outer function itself is never called unless ``pre_npcs`` is truthy.
    """
    if not pre_npcs:
        return
    try:
        from engine.character import WoundLevel as _WLCP
        from engine.combat_cp import award_early_combat_cp
    except Exception:
        return

    for c in pre_npcs:
        try:
            if c.id in combat.combatants:
                continue  # NPC survived the round — not killed
            if not (c.char and c.char.wound_level.value >= _WLCP.DEAD.value):
                continue  # left combat for another reason (fled), not killed

            _kid = c.last_attacker_id
            if _kid is None or not ctx.session_mgr:
                continue
            _sess = ctx.session_mgr.find_by_character(int(_kid))
            if not (_sess and _sess.character):
                continue  # killer offline / not a live PC

            summary = await award_early_combat_cp(ctx.db, _sess.character)
            if summary:
                if summary["faucet_sealed"]:
                    # Reached the cap on this kill — tell the player once.
                    await _sess.send_line(
                        "  \033[1;32m[+1 CP — combat experience]\033[0m "
                        "Your instincts are sharpened. "
                        "(Early combat bonus complete — advancement continues "
                        "through roleplay and missions.)"
                    )
                else:
                    await _sess.send_line(
                        f"  \033[1;32m[+1 CP — combat experience]\033[0m "
                        f"({summary['kills_credited']}/{summary['cap']} "
                        f"early kills credited.)"
                    )
        except Exception as _ce:
            log.warning("Early-combat CP error for NPC %s: %s",
                        getattr(c, "id", None), _ce, exc_info=True)


async def _apply_combat_wear(combat, ctx, pre_npcs=None):
    """Apply weapon condition wear and persist wound states after resolution.

    `pre_npcs` is the pre-resolution NPC-combatant snapshot (taken at the
    resolve_round call site). resolve_round()'s _cleanup() REMOVES dead
    combatants before this runs, so a just-killed NPC is no longer in
    combat.combatants — its DEAD-gated reward hooks below (bounty / anomaly /
    WoW.3a Jedi-weight) would never fire. We therefore also iterate the
    snapshot NPCs that LEFT combat this round at wound_level DEAD (killed, not
    fled), so those hooks reach them. The NPC db row survives death
    (room_id=None), so get_npc + ai_config are still readable; the per-hook
    DEAD gate still correctly skips the live combatants in the same loop.
    Fixes COMBAT.dead_gated_hooks_inert (2026-06-21).
    """
    from engine.items import read_equipment, write_equipment
    from engine.character import WoundLevel as _WLdead
    import json as _json

    _newly_dead = [
        c for c in (pre_npcs or [])
        if getattr(c, "is_npc", False) and c.char
        and c.id not in combat.combatants
        and c.char.wound_level.value >= _WLdead.DEAD.value
    ]
    for c in list(combat.combatants.values()) + _newly_dead:
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
                                # QA 2026-06-21: attribute the kill via
                                # c.last_attacker_id — the SAME chain the
                                # anomaly, WoW.3a, and mob-grind hooks use — not
                                # a scan of THIS round's combatant actions.
                                # roll_initiative() clears actions each round, so
                                # the scan silently missed a bounty target that
                                # bled out from a mortal wound on a later round
                                # (no PC re-attacked the downed NPC that round)
                                # and mis-attributed/dropped multi-attacker and
                                # killer-also-died kills. notify_target_killed
                                # self-filters to the PC who holds the contract,
                                # so a non-contract or NPC attacker just no-ops.
                                _killer_id = c.last_attacker_id
                                if _killer_id:
                                    _contract = await _board.notify_target_killed(
                                        c.id, _killer_id, ctx.db
                                    )
                                    if _contract:
                                        _reward = _board.total_reward(
                                            _contract, alive=False
                                        )
                                        # Award credits UNCONDITIONALLY: the
                                        # contract was just marked COLLECTED
                                        # (irreversible), so an OFFLINE hunter
                                        # is still paid; only the message is
                                        # gated on an online session.
                                        # (QA bounty 2026-06-23.)
                                        _new_bal = await ctx.db.adjust_credits(
                                            _killer_id, _reward, "bounty")
                                        _sess = ctx.session_mgr.find_by_character(
                                            _killer_id
                                        )
                                        if _sess and _sess.character:
                                            _sess.character["credits"] = _new_bal
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
                    # ── SYN.7.a.fix (May 25 2026): anomaly kill hook ─────
                    # When an NPC tagged with ``is_anomaly_target`` dies,
                    # decrement the parent anomaly's live-hostile list.
                    # When the LAST tagged hostile dies, the anomaly is
                    # marked resolved and the killer gets the full reward
                    # (credits + resources + faction influence) — mirrors
                    # the bounty pattern above. Attribution uses
                    # ``last_attacker_id`` from the dying combatant, the
                    # same chain used by the bounty hook and WoW kill
                    # credit below.
                    try:
                        from engine.character import WoundLevel as _WL_ANOM
                        if c.char.wound_level.value >= _WL_ANOM.DEAD.value:
                            _anom_killer_id = c.last_attacker_id
                            try:
                                _ai_cfg_anom = _json.loads(
                                    npc_row.get("ai_config_json", "{}")
                                )
                            except Exception:
                                _ai_cfg_anom = {}
                            if (_ai_cfg_anom.get("is_anomaly_target")
                                    and _anom_killer_id is not None):
                                from engine.wilderness_anomalies import (
                                    award_combat_anomaly_reward,
                                )
                                _payout = await award_combat_anomaly_reward(
                                    ctx.db, int(_anom_killer_id), c.id,
                                    session_mgr=ctx.session_mgr,
                                )
                                if _payout:
                                    _tier = _payout.get("tier", 1)
                                    _name = _payout.get("display_name", "the anomaly")
                                    _inf = _payout.get("influence", 0)
                                    _named = _payout.get("named_loot")
                                    if _tier >= 2:
                                        # ── Tier 2/3 multi-participant payout ──
                                        # Each participant gets a per-char line;
                                        # killer also gets named-loot line (T2)
                                        # and/or scaled T5 mat line (T3).
                                        _payouts = _payout.get("payouts_per_char", [])
                                        _killer_id = int(_anom_killer_id)
                                        # SYN.8: build a quick lookup of scaled T5 grants
                                        # by char_id for tier=3 surfacing.
                                        _scaled_grants = _payout.get("scaled_t5_grants", []) or []
                                        _scaled_by_char = {
                                            int(g.get("char_id", 0)): g for g in _scaled_grants
                                        }
                                        for _pc in _payouts:
                                            _pcid = int(_pc.get("char_id", 0))
                                            if _pcid <= 0:
                                                continue
                                            _sess_pc = ctx.session_mgr.find_by_character(_pcid)
                                            if not _sess_pc:
                                                continue
                                            _pcred = _pc.get("credits", 0)
                                            _pstacks = _pc.get("resources", [])
                                            _ptrophy = _pc.get("trophy")
                                            # Per-participant headline.
                                            _tier_label = (
                                                "[WORLD BOSS DEFEATED]"
                                                if _tier == 3
                                                else "[ANOMALY CLEARED]"
                                            )
                                            _line = (
                                                f"  \033[1;32m{_tier_label}\033[0m "
                                                f"{_name} — +{_pcred:,} credits"
                                            )
                                            if _pcid == _killer_id and _inf > 0:
                                                _line += f", +{_inf} faction inf (killing blow)"
                                            await _sess_pc.send_line(_line)
                                            if _pstacks:
                                                _stack_str = ", ".join(
                                                    f"{s['quantity']}x {s['type']} "
                                                    f"(q{s['quality']:.0f})"
                                                    for s in _pstacks
                                                )
                                                await _sess_pc.send_line(
                                                    f"  \033[2mResources: {_stack_str}\033[0m"
                                                )
                                            # SYN.8: Tier 3 trophy line — every participant.
                                            if _tier == 3 and _ptrophy:
                                                _t_name = _ptrophy.get("name") or _ptrophy.get("key")
                                                _t_desc = _ptrophy.get("description", "")
                                                await _sess_pc.send_line(
                                                    f"  \033[1;35m[TROPHY]\033[0m {_t_name}"
                                                )
                                                if _t_desc:
                                                    await _sess_pc.send_line(
                                                        f"  \033[2m{_t_desc}\033[0m"
                                                    )
                                            # SYN.8: Tier 3 scaled T5 mat — top participants only.
                                            if _tier == 3 and _pcid in _scaled_by_char:
                                                _g = _scaled_by_char[_pcid]
                                                _gqty = _g.get("quantity", 1)
                                                _gkey = _g.get("key", "")
                                                _gqual = _g.get("quality", 70.0)
                                                _gkills = _g.get("kill_count", 0)
                                                await _sess_pc.send_line(
                                                    f"  \033[1;36m[T5 MATERIAL]\033[0m "
                                                    f"{_gqty}× {_gkey} (q{_gqual:.0f}) "
                                                    f"— top contributor "
                                                    f"({_gkills} kills)"
                                                )
                                            # Tier 2 named loot — killer only.
                                            if _tier == 2 and _pcid == _killer_id and _named:
                                                _ln_name = (
                                                    _named.get("name")
                                                    or _named.get("key")
                                                )
                                                _ln_qty = _named.get("qty", 1)
                                                _ln_desc = _named.get("description", "")
                                                await _sess_pc.send_line(
                                                    f"  \033[1;36m[NAMED LOOT]\033[0m "
                                                    f"{_ln_qty}× {_ln_name}"
                                                )
                                                if _ln_desc:
                                                    await _sess_pc.send_line(
                                                        f"  \033[2m{_ln_desc}\033[0m"
                                                    )
                                    else:
                                        # ── Tier 1 single-participant payout ──
                                        _sess_a = ctx.session_mgr.find_by_character(
                                            int(_anom_killer_id)
                                        )
                                        if _sess_a:
                                            _cred = _payout.get("credits", 0)
                                            _stacks = _payout.get("resources", [])
                                            _line = (
                                                f"  \033[1;32m[ANOMALY CLEARED]\033[0m "
                                                f"{_name} — +{_cred:,} credits"
                                            )
                                            if _inf > 0:
                                                _line += f", +{_inf} faction inf"
                                            await _sess_a.send_line(_line)
                                            if _stacks:
                                                _stack_str = ", ".join(
                                                    f"{s['quantity']}x {s['type']} "
                                                    f"(q{s['quality']:.0f})"
                                                    for s in _stacks
                                                )
                                                await _sess_a.send_line(
                                                    f"  \033[2mResources: {_stack_str}\033[0m"
                                                )
                                    log.info(
                                        "[anomaly] T%d paid out #%s to killer %s: "
                                        "credits=%s, named_loot=%s, inf=%d",
                                        _tier,
                                        _payout.get("anomaly_id"),
                                        _anom_killer_id,
                                        _payout.get("credits", 0),
                                        bool(_named),
                                        _inf,
                                    )
                    except Exception as _ae:
                        log.warning(
                            "Anomaly kill hook error for NPC %s: %s",
                            c.id, _ae, exc_info=True,
                        )
                    # ── End anomaly kill hook ────────────────────────────
                    # ── WoW.3a (May 24 2026): kill credit ────────────────
                    # When a Jedi PC kills an NPC, accrue +1 Weight
                    # to the Jedi (capped at +3 per fight; weekly
                    # cap and 200 hard cap enforced by the
                    # substrate). The hook reads c.last_attacker_id
                    # — the same attribution chain that drives
                    # bounty insurance and the killer-of-PC field
                    # in on_pc_death. Idempotent on
                    # (jedi_id, npc_id), so re-running the
                    # post-resolution pass during a multi-round
                    # decay-to-DEAD scenario won't double-credit.
                    #
                    # Threshold is DEAD (matches the bounty hook
                    # above). Mortally wounded targets that may
                    # recover are not yet "killed" for Weight
                    # purposes.
                    try:
                        from engine.character import WoundLevel as _WL3
                        if c.char.wound_level.value >= _WL3.DEAD.value:
                            _killer_id = c.last_attacker_id
                            if _killer_id is not None:
                                _killer = await ctx.db.get_character(
                                    int(_killer_id)
                                )
                                if _killer:
                                    from engine.wow_combat_hooks import (
                                        credit_kill_for_jedi,
                                    )
                                    _applied = await credit_kill_for_jedi(
                                        ctx.db, combat, _killer, c.id,
                                    )
                                    if _applied > 0:
                                        log.debug(
                                            "[WoW.3a] +%d Weight to "
                                            "char %s for killing NPC %s "
                                            "in room %s",
                                            _applied, _killer_id, c.id,
                                            combat.room_id,
                                        )
                    except Exception as _we:
                        log.warning(
                            "[WoW.3a] kill-credit hook error for "
                            "NPC %s: %s", c.id, _we, exc_info=True,
                        )
                    # ── End WoW.3a kill credit ───────────────────────────
                    # NOTE: the DEAD-gated hooks above (bounty / anomaly /
                    # WoW.3a) now reach just-killed NPCs because the function
                    # also iterates the pre-resolution `_newly_dead` snapshot
                    # (a DEAD NPC has already been removed from combat.combatants
                    # by resolve_round's _cleanup). The solo-PvE mob-grind
                    # trickle fires separately from _award_mob_grind_rewards()
                    # on the same snapshot. COMBAT.dead_gated_hooks_inert fix.
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
        # Persist the AUTHORITATIVE post-round state to the DB ALWAYS — even if
        # the session is gone (player disconnected mid-round). QA 2026-06-20:
        # gating this DB write on the session refunded FORCE/CHARACTER points
        # spent in combat + lost the wound on reconnect (an FP/CP-dup via
        # disconnect). c.char.{character_points,force_points,wound_level} are the
        # authoritative post-spend values (CP/FP floored at 0 by the H8 fix). The
        # in-memory session sync + the PC-death hook below still need a session.
        try:
            await ctx.db.save_character(
                c.id, wound_level=c.char.wound_level.value,
                character_points=c.char.character_points,
                force_points=c.char.force_points,
            )
        except Exception:
            log.warning("combat: failed to persist player %s post-round state",
                        c.id, exc_info=True)
        if sess and sess.character:
            sess.character["wound_level"] = c.char.wound_level.value
            # M-fix (combat CP not persisted): the sync was wound_level-only, so
            # CP spent on combat bonuses was refunded on reconnect (a CP-dup
            # exploit). c.char.character_points is the authoritative post-spend
            # value (floored at 0 by the H8 fix); mirror it into the session.
            sess.character["character_points"] = c.char.character_points
            # FP-persist (QA re-run finding): the same gap as CP — a FORCE POINT
            # spent in combat (declare_force_point) was refunded on reconnect
            # (FP-dup). Mirror force_points into the session alongside CP/wound.
            sess.character["force_points"] = c.char.force_points

            # ── PG.1.death (Drop 2c, May 19 2026 evening) ──
            # If the PC just died, run the death-side-effects hook:
            # snapshot inventory → corpse, clear live inventory,
            # apply wound_state='wounded' debuff. Per design §3.5,
            # secured-zone deaths get no corpse + no debuff
            # (handled inside on_pc_death by inspecting
            # security_level). NPCs do NOT go through this path
            # — they have their own corpse-loot via encounter_*.py.
            #
            # The hook runs BEFORE the session-state transition
            # (the dead-state intercept in parser/commands.py picks
            # it up at the next command), so the next thing the
            # player types is "respawn".
            from engine.character import WoundLevel as _WLD
            if c.char.wound_level.value >= _WLD.DEAD.value:
                # ── Drop 2 follow-up (audit wiring, 2026-06-02): respawn grace ──
                # on_pc_death writes a `grace_until` timestamp on every PvP
                # death; get_respawn_grace_until reads it (failing OPEN to 0.0,
                # so a read error never *grants* invulnerability). If this PC is
                # still inside that window from a recent death, refuse the
                # killing blow — anti-spawn-camp. Cap at INCAPACITATED (alive,
                # downed; does NOT bleed out, since only MORTALLY_WOUNDED does
                # in the round resolver), re-sync the lowered wound_level to
                # DB + session, notify the player, and skip the death
                # side-effects entirely (no corpse / no debuff / no insurance
                # fire). This is the consumer death.py's get_respawn_grace_until
                # docstring always described but Drop 2 left unwired.
                _grace_until = 0.0
                try:
                    from engine.death import get_respawn_grace_until
                    _grace_until = await get_respawn_grace_until(ctx.db, c.id)
                except Exception:
                    log.debug(
                        "PG.1.death: respawn-grace read failed for char %s",
                        c.id, exc_info=True,
                    )
                if _grace_until and _time.time() < _grace_until:
                    c.char.wound_level = _WLD.INCAPACITATED
                    sess.character["wound_level"] = c.char.wound_level.value
                    try:
                        await ctx.db.save_character(
                            c.id, wound_level=c.char.wound_level.value
                        )
                    except Exception:
                        log.warning(
                            "PG.1.death: could not re-save grace-protected "
                            "wound_level for char %s", c.id, exc_info=True,
                        )
                    try:
                        await sess.send_line(
                            "\033[1;36m[RESPAWN PROTECTION]\033[0m The blow"
                            " that would have killed you is turned aside —"
                            " you are still shielded from a recent death."
                        )
                    except Exception:
                        log.debug(
                            "PG.1.death: grace message send failed for "
                            "char %s", c.id, exc_info=True,
                        )
                    log.info(
                        "[PG.1.death] respawn-grace protected char %s from "
                        "re-kill (grace_until=%.0f, now=%.0f).",
                        c.id, _grace_until, _time.time(),
                    )
                else:
                    try:
                        from engine.death import on_pc_death
                        from engine.security import get_effective_security
                        _sec = await get_effective_security(
                            combat.room_id, ctx.db, sess.character,
                        )
                        # PG.2 session 2 (May 21 2026): killer
                        # attribution. Pull `last_attacker_id` off the
                        # combatant (stamped in _apply_damage on every
                        # hit). If the attacker is a BH Guild member,
                        # set killer_is_bh so on_pc_death can fire the
                        # insurance hit for any bounty on the target.
                        _killer_id = c.last_attacker_id
                        _killer_is_bh = False
                        if _killer_id is not None:
                            try:
                                _k = await ctx.db.get_character(
                                    _killer_id
                                )
                                if _k and (_k.get("faction_id") or "") in (
                                    "bh_guild", "bounty_hunters_guild"
                                ):
                                    _killer_is_bh = True
                            except Exception:
                                log.debug(
                                    "PG.2: killer faction lookup "
                                    "failed for char %s",
                                    _killer_id, exc_info=True,
                                )
                        await on_pc_death(
                            ctx.db,
                            char_id=c.id,
                            room_id=combat.room_id,
                            security_level=str(_sec.value)
                                if hasattr(_sec, "value") else str(_sec),
                            killer_id=_killer_id,
                            killer_is_bh=_killer_is_bh,
                            session_mgr=ctx.session_mgr,
                        )
                        # Sync the session's wound_state cache so the
                        # respawn command sees it immediately.
                        sess.character["wound_state"] = "wounded"
                    except Exception:
                        log.warning(
                            "PG.1.death: on_pc_death hook failed for "
                            "char %s in room %s", c.id, combat.room_id,
                            exc_info=True,
                        )
            # ── End PG.1.death hook ──

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
                        # SYN.3 (2026-05-25): Region Anchor kill
                        # detection. Replaces the Drop 6D hostile-
                        # takeover-on-guard-kill block (per-room
                        # claims + zone-keyed contests both retired).
                        # When any NPC dies in combat, check whether
                        # it was the Region Anchor for an active
                        # region contest — if so, the killing-blow
                        # faction wins the contest and the region
                        # transfers cleanly.
                        try:
                            from engine.contest import (
                                on_npc_killed_in_combat)
                            # Walk the combatants; any dead NPC is a
                            # potential Anchor candidate. The handler
                            # is a no-op for non-Anchor NPCs (cheap).
                            for _oc in combat.combatants.values():
                                if (_oc.is_npc and _oc.char
                                        and _oc.char.wound_level.value >= 5):
                                    await on_npc_killed_in_combat(
                                        ctx.db,
                                        _oc.id,
                                        sess.character,
                                        combat.room_id,
                                        session_mgr=ctx.session_mgr,
                                    )
                        except Exception:
                            pass  # graceful-drop
                        # hunter.2 (2026-06-05): DSP-hunter defeat. Any dead NPC
                        # tagged as a runtime-spawned Dark-Side hunter ends its
                        # quarry's pursuit (defeating it IS the prestige-domain
                        # reward). No-op for every other dead NPC (cheap).
                        try:
                            from engine.dsp_hunter_runtime import (
                                on_dsp_hunter_killed)
                            for _oc in combat.combatants.values():
                                if (_oc.is_npc and _oc.char
                                        and _oc.char.wound_level.value >= 5):
                                    await on_dsp_hunter_killed(
                                        ctx.db,
                                        _oc.id,
                                        sess.character,
                                        combat.room_id,
                                        session_mgr=ctx.session_mgr,
                                    )
                        except Exception:
                            pass  # graceful-drop
                        # Lane A Phase C (2026-06-05): creature spoils. Any dead
                        # NPC that is a runtime-spawned wilderness creature is
                        # field-dressed by the killer (Survival check → resource
                        # stack into inventory.resources, a crafting sink — no
                        # credits) and the carcass despawned. No-op for every
                        # non-wilderness-creature NPC (cheap). Closes econ-audit
                        # v1 #16 (loot-on-kill).
                        try:
                            from engine.wilderness_encounter_runtime import (
                                on_wild_creature_killed)
                            for _oc in combat.combatants.values():
                                if (_oc.is_npc and _oc.char
                                        and _oc.char.wound_level.value >= 5):
                                    await on_wild_creature_killed(
                                        ctx.db,
                                        _oc.id,
                                        sess.character,
                                        combat.room_id,
                                        session_mgr=ctx.session_mgr,
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

        # Canonical per-slot read/write: the old parse_equipment_json
        # returned None under canonical storage (wear never applied), and
        # serialize_equipment(item) wrote legacy shape 2, clobbering armor.
        _slots = read_equipment(sess.character.get("equipment", "{}"))
        item = _slots["weapon"]
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

        # Persist (armor slot preserved)
        sess.character["equipment"] = write_equipment(
            weapon=item, armor=_slots["armor"])
        await ctx.db.save_character(c.id, equipment=sess.character["equipment"])

        # Notify if weapon is getting damaged
        if item.condition <= 25 and item.condition > 0:
            await sess.send_line(
                f"  {ansi.BRIGHT_YELLOW}Your weapon is badly damaged! "
                f"({item.condition}/{item.max_condition}){ansi.RESET}")
        elif item.condition <= 0:
            await sess.send_line(
                f"  {ansi.BRIGHT_RED}Your weapon has BROKEN! "
                f"Type '+repair' to fix it.{ansi.RESET}")


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
        "  attack pirate\n"
        "  attack thug with brawling\n"
        "  attack bounty hunter cp 2\n"
        "  attack guard stun"
    )
    usage = "attack <target> [with <skill>] [damage <dice>] [cp <N>] [stun]"

    # ── Pipeline orchestrator ────────────────────────────────────────
    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        room_id = char["room_id"]

        if not ctx.args:
            # FUN2: bare 'attack' auto-targets the first hostile NPC in the
            # room so newcomers following the tutorial panel hint ("attack")
            # don't get a usage error. If there are no hostiles, fall through
            # to the normal usage help.
            auto_target = await self._auto_target_hostile(ctx, room_id, char)
            if auto_target is None:
                await self._usage_help(ctx)
                return
            # Mutate args to the hostile's name; the rest of the pipeline
            # treats this identically to a manually typed target name.
            ctx.args = auto_target

        # CRAFT.HOOK.restraints: bound hands can't wield a weapon. A cuffed
        # prisoner can't initiate an attack (mirrors the retreat-refusal gate
        # below — only the initiation surface is gated; struggle free first).
        from engine.restraints import is_restrained
        if is_restrained(char):
            await ctx.session.send_line(
                "  You're bound — you can't attack until you break free "
                "(try `escape`).")
            return

        # ── WoW.3a/3b (May 24 2026): retreat refusal ──────────────────
        # If this PC is a Jedi who has declared `+retreat`, refuse
        # to initiate combat. The retreat flag (wow_retreat_active
        # in attributes JSON) is set by parser/wow_counsel_retreat
        # .py::RetreatCommand and cleared by ReturnCommand.
        #
        # Scope decision (May 24 2026): only the initiation surface
        # is gated. Once combat is in progress, defensive actions
        # (dodge/parry/flee/soak/aim) remain available. The gate
        # is the choice to swing first.
        #
        # WoW.3b also wires this gate into ChallengeCommand and
        # AcceptCommand below — all three initiation paths share
        # the same helper for consistency.
        from engine.wow_combat_hooks import refuse_if_in_retreat
        if await refuse_if_in_retreat(ctx):
            return

        # ── W.2.4: wilderness combat is now supported ────────────────
        # Pre-W.2.4 this site held a [NO COMBAT] gate that refused
        # combat in wilderness entirely because _active_combats was
        # keyed by room_id alone, so two combats at different
        # wilderness tiles would have collapsed into one shared
        # instance.
        #
        # W.2.4 re-keyed ``_active_combats`` to
        # ``(room_id, wilderness_x, wilderness_y)`` (see
        # ``_combat_key_for`` / ``_get_or_create_combat`` /
        # ``CombatInstance.broadcast_source`` above), and migrated
        # every combat broadcast helper to thread the new
        # ``source_char`` Path B kwarg so narration filters to the
        # right tile. The cross-tile damage bug class is closed.
        #
        # The gate is therefore removed. Combat now works in
        # wilderness against PCs and NPCs at the same tile as the
        # attacker; PCs at other tiles see nothing.

        # Phase 1: Security gate
        from engine.security import SecurityLevel
        sec = await self._check_security_gate(ctx, room_id, char)
        if sec is None:
            return

        # Phase 2: Resolve equipped weapon defaults
        equipped_weapon, default_skill, default_damage, accuracy_pips = \
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
                events, ctx.session_mgr, room_id, delay=0.3,
                source_char=combat.broadcast_source())
            await _send_combat_state(combat, ctx.session_mgr)

        # Phase 8: Stun validation + declare + broadcast
        declared = await self._declare_and_broadcast(
            ctx, combat, char, target_char, target_session,
            skill, damage, cp_spend, stun_mode,
            equipped_weapon, default_damage, room_id,
            accuracy_pips=accuracy_pips)

        # Phase 8b: consume single-use ordnance (Gundark Drop D,
        # 2026-06-11). Faucets and sinks land together: craftable
        # explosives without consumption would be a permanent-weapon
        # printer (ammo is otherwise unmodeled at HEAD — frag/thermal
        # were infinite-use until their rows gained `single_use`).
        # Consumed at DECLARATION — the throw is committed; round
        # resolution rolls the action's CAPTURED skill/damage strings,
        # never a live equipment re-read, so clearing the slot now is
        # safe. The `damage == default_damage` test is the same
        # "this attack actually uses the equipped weapon" condition
        # the declare broadcast uses; an explicit `with .. damage ..`
        # override is some OTHER attack and must not eat the grenade.
        if (declared and equipped_weapon
                and getattr(equipped_weapon, "single_use", False)
                and damage == default_damage):
            from engine.items import read_equipment, write_equipment
            _slots = read_equipment(char.get("equipment", "{}"))
            if _slots["weapon"] is not None and                     _slots["weapon"].key == equipped_weapon.key:
                char["equipment"] = write_equipment(
                    weapon=None, armor=_slots["armor"])
                await ctx.db.save_character(
                    char["id"], equipment=char["equipment"])
                await ctx.session.send_line(
                    f"  \033[2mYour {equipped_weapon.name} is expended "
                    f"with the throw. (Equip another to throw again.)\033[0m")

        # Phase 9: Auto-resolve if everyone has declared
        await _send_combat_state(combat, ctx.session_mgr)
        await _try_auto_resolve(combat, ctx)

    # ── Phase helpers ────────────────────────────────────────────────

    async def _auto_target_hostile(self, ctx, room_id: int, char: dict):
        """Return the first hostile NPC name in the room, or None.

        FUN2: Called when the player types bare 'attack' with no args.
        Hostility is determined by is_hostile() from engine.npc_combat_ai,
        the same classification the AI aggro system uses. Returns the NPC's
        name string so it can be injected into ctx.args and the normal
        _find_target pipeline proceeds without duplication.
        """
        from engine.npc_combat_ai import is_hostile
        npcs = await ctx.db.get_npcs_in_room(room_id)
        # Wilderness: if the character is on a tile, filter NPCs by tile
        # (matches the constraint _find_target already applies via match_in_room
        # source_char= path — belt-and-braces, NPCs are stored with room_id
        # only today, so this loop naturally returns room-scope results).
        for npc in npcs:
            if is_hostile(npc):
                return npc["name"]
        return None

    async def _usage_help(self, ctx):
        await ctx.session.send_line(
            "Usage: attack <target> [with <skill>] [damage <dice>] [cp <N>]")
        await ctx.session.send_line("  attack pirate")
        await ctx.session.send_line("  attack thug with blaster damage 4D")
        await ctx.session.send_line(
            "  attack raider with melee combat damage STR+2D cp 2")
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
        """Return (equipped_weapon, default_skill, default_damage, accuracy_pips).

        default_damage now carries the crafted-quality + experiment damage pip
        delta (OBS.quality_and_boosts_not_combat_read, Option B). accuracy_pips
        is the to-hit delta, applied later at declaration. Vendor/legacy weapons
        (q50, no mods) yield a zero delta, so existing behavior is unchanged.
        """
        default_skill = "blaster"
        default_damage = "4D"
        equipped_weapon = None
        accuracy_pips = 0

        from engine.items import read_equipment, crafted_combat_pips, apply_damage_pips
        inst = read_equipment(char.get("equipment", "{}"))["weapon"]
        weapon_key = inst.key if inst else ""
        if weapon_key:
            from engine.weapons import get_weapon_registry
            equipped_weapon = get_weapon_registry().get(weapon_key)
            if equipped_weapon:
                default_skill = equipped_weapon.skill
                default_damage = equipped_weapon.damage
                dmg_pips, accuracy_pips = crafted_combat_pips(inst)
                default_damage = apply_damage_pips(default_damage, dmg_pips)
        return equipped_weapon, default_skill, default_damage, accuracy_pips

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
                # Slice the original-case `remainder` (not .lower()) so an
                # explicit dice token keeps its case (e.g. 4D+2). The bare
                # `damage` path below already preserves case; keeping the two
                # consistent matters because `damage == default_damage` gates
                # the crafted accuracy-pip bonus AND the single-use consume —
                # a lowercased "4d+2" would never equal the uppercase default.
                _idx = remainder.lower().index(" damage ")
                skill = remainder[:_idx].strip().lower()
                damage = remainder[_idx + len(" damage "):].strip()
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

        W.2.3: ``source_char=char`` is threaded into the match and
        session lookup so that, in wilderness, target acquisition is
        constrained to the attacker's tile. Belt-and-braces with the
        AttackCommand wilderness gate: today the gate makes wilderness
        combat unreachable; if/when the gate is lifted (W.2.4), this
        filter is what prevents combat-at-range across the region.
        """
        from engine.matching import match_in_room, MatchResult
        match = await match_in_room(
            target_name, room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
            source_char=char,
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
                for s in ctx.session_mgr.sessions_in_room(
                        room_id, source_char=char):
                    if s.character and s.character["id"] == match.id:
                        target_session = s
                        break
        else:
            # Fall back: check combatants already in active combat.
            # W.2.4: key by char (tile-aware), not raw room_id.
            combat = _active_combats.get(_combat_key_for(char))
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

        # ── +pvp opt-in flag (v27, May 18 2026) ──
        # If EITHER attacker or target is flagged for opt-in PvP, treat
        # as consented in CONTESTED zones. SECURED zones already returned
        # True above (early-return at sec != CONTESTED); the flag does
        # NOT override SECURED — per design call in
        # HANDOFF_MAY18_ROLLUP §"Future improvements" and now-implemented
        # in HANDOFF_MAY18_PVP_FLAG.
        #
        # Mutual-vs-unilateral interpretation: EITHER-party-flagged
        # unlocks. A flagged player has opted into being-attacked-by-
        # anyone; an unflagged attacker hitting a flagged target also
        # consents-by-action (this is the WoW Outland model). The
        # converse — flagged attacker, unflagged target — also works:
        # flagging yourself is a public declaration that you're
        # "hunting" anyone in the zone.
        #
        # Defensive: char.get("pvp_flagged") handles missing column
        # (older test fixtures, mock chars) by treating absence as 0.
        attacker_flagged = bool(char.get("pvp_flagged") or 0)
        target_flagged = bool(target_char.get("pvp_flagged") or 0)
        if attacker_flagged or target_flagged:
            # Mark both sides as in-active-combat so neither can
            # unflag for the next 5 minutes (anti-tag-and-flee).
            # We use engine.cooldowns directly rather than going through
            # the PvpCommand path because the cooldown timer applies to
            # the ATTACKER and TARGET alike on engagement, regardless
            # of who initiated the flag.
            try:
                from engine.cooldowns import (
                    set_cooldown, CD_PVP_UNFLAG, PVP_UNFLAG_COOLDOWN_S,
                )
                set_cooldown(char, CD_PVP_UNFLAG, PVP_UNFLAG_COOLDOWN_S)
                set_cooldown(target_char, CD_PVP_UNFLAG,
                             PVP_UNFLAG_COOLDOWN_S)
                # Persist both sides' attribute updates. The cooldowns
                # module mutates char["attributes"]; we write back here
                # so the unflag-cooldown survives reload.
                await ctx.db.save_character(
                    char["id"], attributes=char["attributes"])
                await ctx.db.save_character(
                    target_char["id"],
                    attributes=target_char["attributes"])
            except Exception:
                log.warning(
                    "+pvp unflag cooldown application failed",
                    exc_info=True,
                )
            return True

        # ── Bounty Hunter override (Security Drop 5) ──
        bh_override = await self._check_bh_override(
            ctx, char, target_name, room_id)
        # ── Territory contest override (Security Drop 6D) ──
        contest_override = await self._check_territory_contest_override(
            ctx, char, target_char, target_name, room_id)

        if not bh_override and not contest_override:
            await ctx.session.send_line(
                f"  \033[1;33mLocal law prohibits unprovoked assault here.\033[0m\n"
                f"  Use \033[1;37mchallenge {target_name}\033[0m to issue a formal challenge.\n"
                f"  (Or find a lawless zone where local law doesn't reach.)"
            )
            return False
        return True

    async def _check_bh_override(self, ctx, char, target_name, room_id):
        """True if attacker is BH guild with an active claimed contract.
        Broadcasts a [BOUNTY HUNTER] drama line to the room if so.

        B.1.g (Apr 29 2026): accepts both GCW (`bh_guild`) and CW
        (`bounty_hunters_guild`) faction codes.
        """
        try:
            if char.get("faction_id") not in ("bh_guild", "bounty_hunters_guild"):
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
                    f" [Contract: {contract.id}]",
                    source_char=char,
                )
                return True
        except Exception:
            log.warning("_check_bh_override: unhandled exception",
                        exc_info=True)
        return False

    async def _check_territory_contest_override(self, ctx, char, target_char,
                                                target_name, room_id):
        """True if attacker and target belong to two different non-independent
        orgs in an active **region** contest at this room.

        SYN.3 (2026-05-25): retargeted from the deleted zone-keyed
        ``engine.territory`` contest API to the region-keyed
        ``engine.contest.is_region_in_active_contest``. The room's
        ``wilderness_region_id`` is the resolution key — city-map
        rooms (no wilderness_region_id) cannot host a region contest,
        so the gate never fires there.
        """
        try:
            atk_org = char.get("faction_id", "independent")
            def_org = target_char.get("faction_id", "independent")
            if (not atk_org or not def_org
                    or atk_org == "independent"
                    or def_org == "independent"
                    or atk_org == def_org):
                return False
            # Resolve the room's wilderness region.
            try:
                room = await ctx.db.get_room(room_id)
            except Exception:
                room = None
            region_slug = (room or {}).get("wilderness_region_id")
            if not region_slug:
                return False
            from engine.contest import is_region_in_active_contest
            active = await is_region_in_active_contest(
                ctx.db, region_slug, atk_org, def_org)
            if active:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    f"  \033[1;31m[REGION CONTEST]\033[0m "
                    f"{char['name']} attacks {target_name}! "
                    f"[{atk_org.replace('_', ' ').title()} vs "
                    f"{def_org.replace('_', ' ').title()}]",
                    source_char=char,
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
        # W.2.4: combat is keyed by (room_id, wx, wy); the cover_max
        # lookup is per-room (cover is a room property), but the
        # combat-existence check uses the tile-aware key.
        if _combat_key_for(char) not in _active_combats:
            cover_max = await ctx.db.get_room_property(room_id, "cover_max", 0)
        combat = _get_or_create_combat(char, cover_max=cover_max)
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
                                     default_damage, room_id,
                                     accuracy_pips=0):
        """Validate stun, declare the ATTACK action, broadcast to attacker,
        room, and target session if applicable."""
        # v22: validate stun mode against weapon capability
        if stun_mode and equipped_weapon and not equipped_weapon.stun_capable:
            await ctx.session.send_line(
                f"  {equipped_weapon.name} cannot be set to stun.")
            stun_mode = False
        # CRAFT.P0.7: dedicated stun weapons fire stun bolts ONLY —
        # the mode is forced regardless of how the attack was declared.
        if equipped_weapon and getattr(equipped_weapon, "stun_only", False) \
                and not stun_mode:
            await ctx.session.send_line(
                f"  {equipped_weapon.name} only fires stun bolts.")
            stun_mode = True

        action = CombatAction(
            action_type=ActionType.ATTACK,
            skill=skill,
            target_id=target_char["id"],
            weapon_damage=damage,
            cp_spend=cp_spend,
            stun_mode=stun_mode,
            # Drop 19: accuracy pip bonus from crafted weapon quality/experiments.
            # Apply only when this attack uses the equipped weapon (not an explicit
            # override). Same guard as the Drop D consume block and the weapon_name
            # tag: if damage == default_damage, the equipped weapon is in play.
            accuracy_bonus_pips=(
                accuracy_pips if (equipped_weapon and damage == default_damage) else 0
            ),
        )
        err = combat.declare_action(char["id"], action)
        if err:
            await ctx.session.send_line(f"  {err}")
            return False

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
            source_char=char,
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
        return True


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
            source_char=char,
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
    # Pre-S57b key was "+combat"; demoted to "combat" so the +combat
    # umbrella (CombatCommand) can occupy the canonical key. Original
    # aliases preserved for backward compatibility.
    key = "combat"
    aliases = ["cs", "+cs"]
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
        combat = _active_combats.get(_combat_key_for(char))
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        lines = combat.get_status()
        for line in lines:
            await ctx.session.send_line(ansi.combat_msg(line))

    async def _show_rolls(self, ctx):
        char = ctx.session.character
        combat = _active_combats.get(_combat_key_for(char))
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
        combat = _active_combats.get(_combat_key_for(char))
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        # Auto-assign pass to undeclared
        for c in combat.undeclared_combatants():
            combat.declare_action(c.id, CombatAction(
                action_type=ActionType.OTHER, description="hesitates"
            ))

        _pre_npcs = [c for c in combat.combatants.values()
                     if c.is_npc and c.char]
        events = combat.resolve_round()

        # Admin resolve skips posing — auto-generate all poses and flush
        await _apply_combat_wear(combat, ctx, _pre_npcs)
        await _award_mob_grind_rewards(combat, ctx, _pre_npcs)
        await _award_early_combat_cp(combat, ctx, _pre_npcs)

        # Phase 7c: city-guard combat-round triggers (also fires
        # on admin resolve so the behavior is consistent across
        # both resolution paths).
        if not _combat_finished(combat):
            await _check_city_guard_triggers(combat, ctx)

        if _combat_finished(combat):
            _src = combat.broadcast_source()
            await _broadcast_events_paced(events, ctx.session_mgr,
                                          combat.room_id, source_char=_src)
            await _send_combat_ended(combat.room_id, ctx.session_mgr,
                                     source_char=_src)
            _remove_combat(combat)
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
        combat = _active_combats.get(_combat_key_for(char))
        if not combat:
            await ctx.session.send_line("  No active combat here.")
            return

        combatant = combat.get_combatant(char["id"])
        if not combatant:
            await ctx.session.send_line("  You're not in this combat.")
            return

        if _combat_finished(combat):
            combat.remove_combatant(char["id"])
            if len(combat.combatants) == 0:
                _remove_combat(combat)
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
        "  range pirate        -- check range\n"
        "  range pirate short  -- set to short"
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
            source_char=char,
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
            source_char=char,
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

    # Only intercept if player is in active combat.
    # W.2.4: tile-aware key for wilderness compatibility.
    combat = _active_combats.get(_combat_key_for(char))
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


# ═══════════════════════════════════════════════════════════════════════════
# +combat — Umbrella for combat actions (S54 + S57b)
# ═══════════════════════════════════════════════════════════════════════════
#
# This umbrella implements the S54 design: a single +-prefix entry
# point with switch-style dispatch (`+combat/attack`, `+combat/dodge`,
# etc.) plus a comprehensive alias list so muscle memory continues to
# work. Each bare verb (attack, dodge, flee...) maps to a switch via
# _ALIAS_TO_SWITCH; switches resolve to handlers via _SWITCH_IMPL.
#
# Per-verb command classes (AttackCommand, DodgeCommand, ...) remain
# registered at their bare keys for backward compatibility. The
# registry's `get()` prefers exact key matches over aliases, so typing
# "attack" still reaches AttackCommand directly. The umbrella is for
# the canonical `+combat/attack` form and the discoverability surface.

# Switch → handler-class mapping. Populated by _init_switch_impl().
_SWITCH_IMPL: dict = {}

# Bare-alias → canonical-switch mapping. Lets the umbrella resolve
# what `+combat` (no switch) or a bare alias should dispatch to.
_ALIAS_TO_SWITCH: dict[str, str] = {
    # Status / overview
    "combat":      "status",
    "cs":          "status",
    "status":      "status",
    # Attack family
    "attack":      "attack",
    "att":         "attack",
    "kill":        "attack",
    "shoot":       "attack",
    "hit":         "attack",
    # Dodge family
    "dodge":       "dodge",
    "fulldodge":   "fulldodge",
    "fdodge":      "fulldodge",
    # Parry family
    "parry":       "parry",
    "fullparry":   "fullparry",
    "fparry":      "fullparry",
    # Defensive / utility
    "soak":        "soak",
    "aim":         "aim",
    # Movement / withdrawal
    "flee":        "flee",
    "run":         "flee",
    "retreat":     "flee",
    "pass":        "pass",
    "disengage":   "disengage",
    # Round resolution
    "resolve":     "resolve",
    # Tactical
    "range":       "range",
    "distance":    "range",
    "cover":       "cover",
    "hide":        "cover",
    # Force points
    "forcepoint":  "forcepoint",
    "fp":          "forcepoint",
    # Pose & rolls
    "cpose":       "pose",
    "combatpose":  "pose",
    "crolls":      "rolls",
    # Challenge subsystem
    "challenge":   "challenge",
    "duel":        "challenge",
    "accept":      "accept",
    "decline":     "decline",
    "refuse":      "decline",
}


class CombatCommand(BaseCommand):
    """`+combat` umbrella — see module docstring for dispatch rules."""
    key = "+combat"
    # Command-syntax rework Drop 4 (command_syntax_rework_design_v2.md): the
    # per-verb DUPLICATE aliases that a standalone combat command already owns
    # (att/kill/shoot/hit→AttackCommand, cs→CombatStatusCommand,
    # fdodge→FullDodgeCommand, fparry→FullParryCommand, soak→SoakCommand,
    # run→FleeCommand, distance→RangeCommand, hide→CoverCommand,
    # fp→ForcePointCommand, combatpose→CombatPoseCommand, duel→ChallengeCommand,
    # refuse→DeclineCommand) are DELETED — they were dead duplicates (the
    # standalone registers later and wins the binding), so every one still
    # resolves to the EXACT same handler. The _ALIAS_TO_SWITCH dispatch map is
    # left intact (it drives +combat/<switch> + bare-verb dispatch through the
    # umbrella and is exercised by the S54 dispatch tests). 'cpose'/'crolls'
    # remain — they are genuine umbrella-only shorthands (no standalone owns
    # them).
    # Command-syntax rework Drop 7 (type-3 genuine-conflict resolution):
    # 'retreat' and 'accept' DELETED here. 'retreat' is the combat-disengage
    # synonym already owned by the standalone FleeCommand (aliases run/retreat)
    # — the bare verb now resolves there, and wow_counsel's leave-of-absence
    # command keeps its A1-correct OOC '+retreat' key only. 'accept' (combat-
    # challenge accept) is owned by AcceptMissionCommand's bare 'accept' (which
    # smart-dispatches PC challenges to AcceptCommand) and by the +combat/accept
    # switch — the dead bare alias is removed. _ALIAS_TO_SWITCH still maps both
    # so +combat/<switch> dispatch is unchanged.
    aliases: list[str] = [
        "combat",
        "attack",
        "dodge", "fulldodge",
        "parry", "fullparry",
        "aim",
        "flee",
        "pass", "disengage",
        "resolve",
        "range",
        "cover",
        "forcepoint",
        "cpose", "crolls",
        "challenge",
        "decline",
    ]
    help_text = (
        "Combat verbs. Canonical form '+combat/attack <target>', or "
        "use bare verbs (attack, dodge, parry, ...). Type 'help +combat' "
        "for the full reference."
    )
    usage = "+combat[/<switch>] [args]  — see 'help +combat'"
    valid_switches: list[str] = [
        "attack", "dodge", "fulldodge", "parry", "fullparry",
        "soak", "aim", "flee", "disengage", "pass", "resolve",
        "range", "cover", "forcepoint", "pose", "rolls",
        "challenge", "accept", "decline", "status",
    ]

    async def execute(self, ctx: CommandContext):
        # Resolve switch: explicit /switch wins, then alias map, else status.
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "status",
            )

        impl_cls = _SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return

        # Hand off to the per-verb command class.
        cmd = impl_cls()
        await cmd.execute(ctx)


def _init_switch_impl():
    """Populate _SWITCH_IMPL after all per-verb classes are defined."""
    _SWITCH_IMPL["attack"]     = AttackCommand
    _SWITCH_IMPL["dodge"]      = DodgeCommand
    _SWITCH_IMPL["fulldodge"]  = FullDodgeCommand
    _SWITCH_IMPL["parry"]      = ParryCommand
    _SWITCH_IMPL["fullparry"]  = FullParryCommand
    _SWITCH_IMPL["soak"]       = SoakCommand
    _SWITCH_IMPL["aim"]        = AimCommand
    _SWITCH_IMPL["flee"]       = FleeCommand
    _SWITCH_IMPL["pass"]       = PassCommand
    _SWITCH_IMPL["status"]     = CombatStatusCommand
    _SWITCH_IMPL["resolve"]    = ResolveCommand
    _SWITCH_IMPL["disengage"]  = DisengageCommand
    _SWITCH_IMPL["range"]      = RangeCommand
    _SWITCH_IMPL["cover"]      = CoverCommand
    _SWITCH_IMPL["forcepoint"] = ForcePointCommand
    _SWITCH_IMPL["pose"]       = CombatPoseCommand
    _SWITCH_IMPL["rolls"]      = CombatRollsCommand
    _SWITCH_IMPL["challenge"]  = ChallengeCommand
    _SWITCH_IMPL["accept"]     = AcceptCommand
    _SWITCH_IMPL["decline"]    = DeclineCommand


# NOTE: _init_switch_impl() is called at the very end of the module
# (see bottom of file) so all referenced per-verb classes are defined.


def register_combat_commands(registry):
    """Register all combat commands."""
    cmds = [
        CombatCommand(),
        AttackCommand(), DodgeCommand(), FullDodgeCommand(),
        ParryCommand(), FullParryCommand(), SoakCommand(),
        AimCommand(), FleeCommand(), PassCommand(),
        CombatStatusCommand(), ResolveCommand(), DisengageCommand(),
        RangeCommand(), CoverCommand(), ForcePointCommand(),
        CombatPoseCommand(), CombatRollsCommand(),
        ChallengeCommand(), DeclineCommand(),
        # Command-syntax rework Drop 7: AcceptCommand is NOT registered as a
        # standalone top-level command — its bare 'accept' key collided with
        # AcceptMissionCommand. The class lives on for the +combat/accept switch
        # (_SWITCH_IMPL["accept"]) and the smart-dispatch delegation in
        # AcceptMissionCommand (bare `accept <challenger>` → combat consent).
        PvpCommand(),   # v27 (May 18 2026): opt-in PvP flag
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
                "firing two quick shots at the pirate."
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

        # ── WoW.3b (May 24 2026): retreat refusal ─────────────────────
        # A Jedi who has declared `+retreat` cannot challenge
        # another PC to combat. Shares the same helper as
        # AttackCommand and AcceptCommand. See engine/wow_combat_
        # hooks.py::refuse_if_in_retreat for the dual-gate logic.
        from engine.wow_combat_hooks import refuse_if_in_retreat
        if await refuse_if_in_retreat(ctx):
            return

        # Must be in contested or lawless zone to bother
        from engine.security import get_effective_security, SecurityLevel
        sec = await get_effective_security(room_id, ctx.db, character=char)
        if sec == SecurityLevel.SECURED:
            await ctx.session.send_line(
                "  \033[1;33mLocal security would immediately stop any duel here.\033[0m"
            )
            return

        # Find target player
        # W.2.3: source_char=char filters target acquisition to the
        # challenger's wilderness tile (no effect in normal rooms).
        from engine.matching import match_in_room, MatchResult
        match = await match_in_room(
            ctx.args.strip(), room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
            source_char=char,
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
        # W.2.3: source_char=char filters to the challenger's tile in
        # wilderness; harmless in normal rooms. The match above already
        # used source_char, so the target is co-located by construction
        # — this is belt-and-braces.
        target_sess = None
        for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
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

        # ── WoW.3b (May 24 2026): retreat refusal ─────────────────────
        # A Jedi who has declared `+retreat` cannot accept a combat
        # challenge. They may still use `decline` to refuse the
        # challenge cleanly (decline is non-combat — the polite
        # exit door).
        from engine.wow_combat_hooks import refuse_if_in_retreat
        if await refuse_if_in_retreat(ctx):
            return

        # W.2.3: source_char=char ensures we only resolve challengers
        # at the same wilderness tile as the accepter (no effect in
        # normal rooms).
        from engine.matching import match_in_room
        match = await match_in_room(
            ctx.args.strip(), room_id, char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
            source_char=char,
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
        # W.2.3: source_char=char filters to the accepter's wilderness
        # tile (harmless in normal rooms).
        for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
            if s.character and s.character["id"] == challenger_id:
                await s.send_line(
                    f"\n  \033[1;31m{char['name']} accepts your challenge!\033[0m "
                    f"Combat consent is active.\n"
                )
                break

        # Broadcast to room
        # W.2.3: source_char=char restricts the consent announcement
        # to onlookers at the accepter's wilderness tile. A third PC
        # in the same region but a different tile won't see this.
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"\033[1;33m{challenger_name} and {char['name']} have agreed to settle "
            f"their differences the old-fashioned way.\033[0m",
            exclude=[challenger_id, t_id],
            source_char=char,
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
            # W.2.3: source_char=char filters to the decliner's tile
            # in wilderness; harmless in normal rooms.
            from engine.matching import match_in_room
            match = await match_in_room(
                ctx.args.strip(), char["room_id"], char["id"], ctx.db,
                session_mgr=ctx.session_mgr,
                source_char=char,
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
        for s in ctx.session_mgr.sessions_in_room(
                char["room_id"], source_char=char):
            if s.character and s.character["id"] == challenger_id:
                await s.send_line(
                    f"  \033[2m{char['name']} declines your challenge.\033[0m"
                )
                break


class PvpCommand(BaseCommand):
    """``+pvp`` — opt-in PvP flag (v27, May 18 2026).

    Per-character standing flag. When set, the character is open to
    PvP without the per-pair challenge/accept dance, in CONTESTED
    zones only. SECURED zones remain absolute — flagging does NOT
    let anyone attack you in the Jedi Temple or the Senate.

    Subcommands:
      +pvp on         — flag yourself; broadcast to room
      +pvp off        — unflag (subject to 5-minute cooldown after
                        the flag has been active in a combat)
      +pvp status     — show your current flag state + cooldown remaining
      +pvp            — alias for `+pvp status`

    Cooldown: once your flag has been "active" in a combat (either
    you engaged or were engaged-by while flagged), you cannot unflag
    for 5 minutes. This is the WoW-style anti-tag-and-flee mechanic
    — without it, griefers would flag, attack, and immediately
    unflag to dodge consequences.

    The cooldown is set in _check_pvp_consent (above) when the flag
    is consulted to allow an attack. Here we read it on `+pvp off`
    and refuse if still active.
    """
    key = "+pvp"
    aliases = ["pvp"]
    help_text = (
        "Opt-in PvP flag — toggle yourself open to PvP without "
        "needing challenge/accept.\n"
        "\n"
        "USAGE:\n"
        "  +pvp on        Flag yourself open to PvP in CONTESTED zones.\n"
        "  +pvp off       Unflag yourself (5-minute cooldown after a fight).\n"
        "  +pvp status    Show current flag + cooldown.\n"
        "  +pvp           Alias for +pvp status.\n"
        "\n"
        "RULES:\n"
        "  * Flag does NOT override SECURED zones (Jedi Temple, "
        "Senate, etc. remain absolute).\n"
        "  * If EITHER you or your target is flagged, the attack "
        "proceeds without challenge/accept (consensual-by-flag).\n"
        "  * Once your flag has been used in a combat, you cannot "
        "unflag for 5 minutes (anti-tag-and-flee).\n"
    )
    usage = "+pvp [on|off|status]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +pvp.")
            return

        sub = (ctx.args or "").strip().lower()
        if sub in ("", "status"):
            await self._show_status(ctx, char)
            return
        if sub == "on":
            await self._flag_on(ctx, char)
            return
        if sub == "off":
            await self._flag_off(ctx, char)
            return
        await ctx.session.send_line(
            f"  Unknown +pvp subcommand: {sub!r}\n"
            f"  Usage: +pvp [on|off|status]"
        )

    async def _show_status(self, ctx, char):
        flagged = bool(char.get("pvp_flagged") or 0)
        from engine.cooldowns import (
            remaining_cooldown, format_remaining, CD_PVP_UNFLAG,
        )
        rem = remaining_cooldown(char, CD_PVP_UNFLAG)
        if flagged:
            line = "  \033[1;31m[PvP flag: ON]\033[0m"
            if rem > 0:
                line += (
                    f"  \033[2m(cannot unflag for "
                    f"{format_remaining(rem)})\033[0m"
                )
            else:
                line += "  \033[2m(can unflag with `+pvp off`)\033[0m"
        else:
            line = "  \033[1;32m[PvP flag: OFF]\033[0m"
            line += "  \033[2m(use `+pvp on` to opt in)\033[0m"
        await ctx.session.send_line(line)

    async def _flag_on(self, ctx, char):
        if char.get("pvp_flagged"):
            await ctx.session.send_line(
                "  You are already flagged for PvP. "
                "(`+pvp status` to see cooldown.)"
            )
            return
        # Set the flag in DB. char["pvp_flagged"] is updated
        # in-place by get_char on next read; we also patch the
        # session's cached dict so subsequent _check_pvp_consent
        # calls in the same session see it.
        await ctx.db.save_character(char["id"], pvp_flagged=1)
        char["pvp_flagged"] = 1
        ctx.session.invalidate_char_obj()
        await ctx.session.send_line(
            "  \033[1;31m[PvP flag: ON]\033[0m  "
            "You are now open to PvP in CONTESTED zones. SECURED "
            "zones remain protected. Use `+pvp off` to disable "
            "(5-minute cooldown after a fight)."
        )
        # Broadcast to the room so others see the change.
        # W.2 phase 2 Path B: source_char filters to co-located peers
        # when in wilderness; harmless in normal rooms.
        try:
            room_id = char["room_id"]
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  \033[2m{char['name']} flags themselves "
                f"open to PvP.\033[0m",
                exclude=ctx.session,
                source_char=char,
            )
        except Exception:
            log.warning("+pvp on room broadcast failed", exc_info=True)

    async def _flag_off(self, ctx, char):
        if not char.get("pvp_flagged"):
            await ctx.session.send_line(
                "  You are not flagged for PvP."
            )
            return
        from engine.cooldowns import (
            remaining_cooldown, format_remaining, CD_PVP_UNFLAG,
        )
        rem = remaining_cooldown(char, CD_PVP_UNFLAG)
        if rem > 0:
            await ctx.session.send_line(
                f"  You cannot unflag yet — your PvP flag is "
                f"active in a recent combat. "
                f"Try again in {format_remaining(rem)}."
            )
            return
        await ctx.db.save_character(char["id"], pvp_flagged=0)
        char["pvp_flagged"] = 0
        ctx.session.invalidate_char_obj()
        await ctx.session.send_line(
            "  \033[1;32m[PvP flag: OFF]\033[0m  "
            "You are no longer open to opt-in PvP."
        )
        try:
            room_id = char["room_id"]
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  \033[2m{char['name']} unflags themselves "
                f"from PvP.\033[0m",
                exclude=ctx.session,
                source_char=char,
            )
        except Exception:
            log.warning("+pvp off room broadcast failed", exc_info=True)


# ── S54: populate _SWITCH_IMPL after all per-verb classes are defined ──
_init_switch_impl()

