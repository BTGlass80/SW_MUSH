# -*- coding: utf-8 -*-
"""
parser/bounty_commands.py  --  Bounty Board Commands
SW_MUSH  |  Economy Phase 2

Commands:
  bounties          -- view the board
  bountyclaim <id>  -- accept a contract
  mybounty          -- view your active contract
  bountytrack       -- investigate target location (Search/Streetwise roll)
  bountycollect     -- collect reward after defeating target (auto-triggered by
                       combat kill, but also available manually at target room)

Register via: register_bounty_commands(registry)
"""

import json
import logging
import time

from server import ansi
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _load_board(db):
    from engine.bounty_board import get_bounty_board
    board = get_bounty_board()
    try:
        rooms = await db.list_rooms(limit=100)
    except Exception:
        rooms = []
    await board.ensure_loaded(db, rooms)
    return board


async def _get_active_contract(char_id: str, board):
    """Return the character's currently claimed contract, or None."""
    from engine.bounty_board import BountyStatus
    for c in board._contracts.values():
        if c.claimed_by == char_id and c.status == BountyStatus.CLAIMED:
            return c
    return None


# ── Commands ───────────────────────────────────────────────────────────────────

class BountiesCommand(BaseCommand):
    key = "+bounties"
    aliases = ["bounties", "bboard", "bountyboard", "+bboard"]
    help_text = "View the Bounty Board. Lists active contracts."
    usage = "bounties"

    async def execute(self, ctx: CommandContext):
        board = await _load_board(ctx.db)
        contracts = board.posted_contracts()

        # F.8.c.2.b₃: Filter chain-tagged tutorial bounties so only
        # the player whose active chain step expects them sees them.
        try:
            from engine.chain_missions import filter_visible_bounties
            import json as _bj
            char = ctx.session.character
            attrs_raw = char.get("attributes", "{}") if char else "{}"
            if isinstance(attrs_raw, str):
                try:
                    attrs = _bj.loads(attrs_raw) if attrs_raw else {}
                except Exception:
                    attrs = {}
            else:
                attrs = attrs_raw or {}
            contracts = filter_visible_bounties(contracts, attrs)
        except Exception:
            log.debug("chain_missions bounty visibility filter failed",
                      exc_info=True)

        from engine.bounty_board import format_bounty_board
        for line in format_bounty_board(contracts):
            await ctx.session.send_line(line)

        # ── Webify UI-5: WebSocket clients also get a structured
        # board_state for the bounty-board modal. `contracts` is the
        # SAME chain-visibility-filtered list the text path just
        # rendered, so tutorial-tagged bounties never leak to the web
        # surface either. Telnet behavior above is unchanged.
        try:
            from server.session import Protocol
            if ctx.session.protocol == Protocol.WEBSOCKET:
                from engine.bounty_board import build_board_state
                claimed = None
                if ctx.session.character:
                    claimed = await _get_active_contract(
                        str(ctx.session.character["id"]), board)
                payload = build_board_state(contracts, claimed)
                await ctx.session.send_json("board_state", payload)
        except Exception:
            log.debug("BountiesCommand: board_state push failed",
                      exc_info=True)


class BountyClaimCommand(BaseCommand):
    key = "bountyclaim"
    aliases = ["claimbounty", "acceptbounty"]
    help_text = "Accept a bounty contract. One active contract at a time."
    usage = "bountyclaim <contract-id>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("  Usage: bountyclaim <contract-id>")
            await ctx.session.send_line("  Type 'bounties' to see available contracts.")
            return

        char = ctx.session.character
        char_id = str(char["id"])
        board = await _load_board(ctx.db)

        # Check if already has one
        existing = await _get_active_contract(char_id, board)
        if existing:
            await ctx.session.send_line(
                f"  You already have an active contract on {existing.target_name}.")
            await ctx.session.send_line("  Type 'mybounty' to review it.")
            return

        cid = ctx.args.strip().lower()
        # Prefix match
        target = board.get(cid)
        if not target:
            for bid, bc in board._contracts.items():
                if bid.startswith(cid):
                    target = bc
                    break

        from engine.bounty_board import BountyStatus
        if not target or target.status != BountyStatus.POSTED:
            await ctx.session.send_line(
                f"  No posted bounty '{cid}'. Type 'bounties' to see the board.")
            return

        claimed = await board.claim(target.id, char_id, ctx.db)
        if not claimed:
            await ctx.session.send_line(
                "  That contract is no longer available.")
            return

        # F.8.c.2.b₂: CW tutorial chain — bounty_accepted completion.
        # Chain-tagged bounties carry a chain_bounty_id field;
        # untagged contracts skip silently inside the hook.
        try:
            from engine.chain_events import on_bounty_accepted
            _chain_bid = getattr(claimed, "chain_bounty_id", "") or ""
            if _chain_bid and ctx.session.character:
                _adv = await on_bounty_accepted(
                    ctx.db, ctx.session.character, _chain_bid,
                )
                if _adv:
                    from engine.chain_graduation import (
                        execute_pending_teleport,
                    )
                    await execute_pending_teleport(
                        ctx, ctx.session.character,
                    )
        except Exception as _ce:
            log.debug("chain_events bounty_accepted hook error: %s",
                      _ce, exc_info=True)

        from engine.bounty_board import format_contract_detail
        for line in format_contract_detail(claimed):
            await ctx.session.send_line(line)
        await ctx.session.send_line(
            ansi.success(
                f"  Contract accepted. Find {claimed.target_name} and bring them to justice."
            )
        )
        await ctx.session.send_line(
            f"  Type 'bountytrack' to get an investigative lead on their location."
        )


class MyBountyCommand(BaseCommand):
    key = "+mybounty"
    aliases = ["mybounty", "activebounty", "myhunt", "+myhunt"]
    help_text = "View your currently active bounty contract."
    usage = "mybounty"

    async def execute(self, ctx: CommandContext):
        char_id = str(ctx.session.character["id"])
        board = await _load_board(ctx.db)
        contract = await _get_active_contract(char_id, board)
        if not contract:
            await ctx.session.send_line("  You have no active bounty contract.")
            await ctx.session.send_line("  Type 'bounties' to see available contracts.")
            return

        from engine.bounty_board import format_contract_detail
        for line in format_contract_detail(contract):
            await ctx.session.send_line(line)


class BountyTrackCommand(BaseCommand):
    key = "bountytrack"
    aliases = ["tracktarget", "hunttrack"]
    help_text = (
        "Use investigation skills to locate your bounty target. "
        "Rolls Search, Streetwise, or Tracking (best available)."
    )
    usage = "bountytrack"

    # Difficulty by tier
    _DIFFICULTIES = {
        "extra":    6,
        "average":  10,
        "novice":   13,
        "veteran":  17,
        "superior": 21,
    }

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = str(char["id"])
        board = await _load_board(ctx.db)
        contract = await _get_active_contract(char_id, board)

        if not contract:
            await ctx.session.send_line("  You have no active bounty contract.")
            return

        if not contract.target_npc_id:
            await ctx.session.send_line(
                "  Contract data error — target NPC not found.")
            return

        # Check if target is even still alive
        target_npc = await ctx.db.get_npc(contract.target_npc_id)
        if not target_npc:
            await ctx.session.send_line(
                f"  {contract.target_name} is no longer in the system. "
                "They may have already been taken down.")
            return

        # Roll investigation skill — use best available
        from engine.dice import DicePool, roll_d6_pool
        from engine.character import Character

        # Load character for skill lookup
        char_row = await ctx.db.get_character(char["id"])
        if not char_row:
            await ctx.session.send_line("  Character data error.")
            return

        # drop 26 (2026-06-13): Character.from_db_dict takes only the
        # row dict — the prior `(char_row, skill_reg)` call crashed
        # ("takes 2 positional arguments but 3 were given"). This line
        # was never reached before because BountyTrackCommand
        # hard-errored on an unbound target_npc_id (tutorial contracts
        # left it None); binding the tutorial bounty's target NPC
        # (engine/chain_missions._spawn_bounty) made it reachable and
        # surfaced this latent crash.
        char_obj = Character.from_db_dict(char_row)

        # Try search, streetwise, tracking — take the best pool
        investigation_skills = ["search", "streetwise", "tracking"]
        best_pool = None
        best_skill = "search"
        for sk in investigation_skills:
            try:
                pool = char_obj.get_skill_pool(sk)
                if best_pool is None or pool.total_pips > best_pool.total_pips:
                    best_pool = pool
                    best_skill = sk
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                continue

        if best_pool is None:
            best_pool = DicePool(2, 0)   # 2D fallback
            best_skill = "search"

        difficulty = self._DIFFICULTIES.get(contract.tier.value, 10)
        result = roll_d6_pool(best_pool)
        success = result.total >= difficulty

        await ctx.session.send_line(
            f"  {ansi.BOLD}Investigating:{ansi.RESET} {contract.target_name} "
            f"({contract.tier.value.title()} target)"
        )
        await ctx.session.send_line(
            f"  {best_skill.title()} roll: {result.display()}  "
            f"vs Difficulty {difficulty}"
        )

        if success:
            # Reveal the room
            target_room = await ctx.db.get_room(target_npc["room_id"])
            room_name = target_room["name"] if target_room else "unknown location"
            await ctx.session.send_line(
                ansi.success(
                    f"  Lead found! {contract.target_name} was last seen at: "
                    f"{ansi.BOLD}{room_name}{ansi.RESET}"
                )
            )
            await ctx.session.send_line(
                f"  Make your way there and engage — they are armed and hostile."
            )
            # Update contract room cache
            contract.target_room_id = target_npc["room_id"]
            await ctx.db.update_bounty(contract.id, contract.to_dict())
        else:
            margin = difficulty - result.total
            if margin <= 5:
                await ctx.session.send_line(
                    f"  Close, but not enough. You pick up a cold trail near "
                    f"the {['cantina', 'market', 'docking bays', 'outskirts'][margin % 4]}."
                )
            else:
                await ctx.session.send_line(
                    "  No leads. The target has covered their tracks well. Try again later."
                )
        await ctx.session.send_line("")


class BountyCollectCommand(BaseCommand):
    key = "bountycollect"
    aliases = ["collectbounty", "claimreward"]
    help_text = (
        "Collect your bounty reward. Must be in the same room as the defeated target, "
        "or the target must already be dead."
    )
    usage = "bountycollect"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = str(char["id"])
        board = await _load_board(ctx.db)
        contract = await _get_active_contract(char_id, board)

        if not contract:
            await ctx.session.send_line("  You have no active bounty contract.")
            return

        # Check target is dead/incapacitated or no longer exists
        npc = None
        if contract.target_npc_id:
            npc = await ctx.db.get_npc(contract.target_npc_id)

        target_down = False

        if not npc:
            # NPC was deleted (killed in combat and cleaned up)
            target_down = True
        else:
            # Check wound state from char_sheet_json
            try:
                cs = json.loads(npc.get("char_sheet_json", "{}"))
                wound = cs.get("wound_level", 0)
                # WoundLevel: 5=mortally wounded, 6=dead
                if wound >= 5:
                    target_down = True
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass

            # Also check: are we in the same room?
            if not target_down:
                if npc.get("room_id") == char.get("room_id"):
                    await ctx.session.send_line(
                        f"  {contract.target_name} is still standing. "
                        "You need to defeat them first."
                    )
                else:
                    await ctx.session.send_line(
                        f"  {contract.target_name} hasn't been defeated yet."
                    )
                    await ctx.session.send_line(
                        "  Use 'bountytrack' to find them, then engage."
                    )
                return

        # Collect it — skill check represents claim quality
        collected = await board.collect(contract.id, False, ctx.db)
        if not collected:
            await ctx.session.send_line("  Error collecting bounty. Try again.")
            return

        base_reward = board.total_reward(collected, alive=False)
        from engine.skill_checks import perform_skill_check
        # Bounty hunters roll Streetwise; others roll Search
        import json as _bj
        _attrs = _bj.loads(char.get('attributes', '{}'))
        _skills = _bj.loads(char.get('skills', '{}'))
        _skill = 'streetwise' if _skills.get('streetwise') else 'search'
        _diff = 8 if base_reward < 500 else (11 if base_reward < 1500 else 14)
        _check = perform_skill_check(char, _skill, _diff)
        if _check.success:
            reward = base_reward
            if _check.critical_success:
                reward = int(base_reward * 1.20)
        elif _check.margin >= -4:
            reward = int(base_reward * 0.75)  # partial
        else:
            reward = int(base_reward * 0.50)  # poor paperwork
        # E2: BOUNTY_SURGE world event scales bounty payouts while active.
        # Mirrors the smuggling_pay_mult pattern — read get_effect() before the
        # metered `bounty` faucet; no-op (default 1.0) when no event is active.
        try:
            from engine.world_events import get_world_event_manager
            _bmult = get_world_event_manager().get_effect("bounty_reward_mult", 1.0)
            if _bmult and _bmult != 1.0 and reward > 0:
                _boosted = int(reward * _bmult)
                _bonus = _boosted - reward
                if _bonus > 0:
                    reward = _boosted
                    await ctx.session.send_line(
                        f"  A bounty surge is in effect \u2014 the contract pays "
                        f"{_bonus:,} credits extra."
                    )
        except Exception:
            log.debug("bounty surge multiplier calc failed (non-fatal)",
                      exc_info=True)
        # DIFF.4 (2026-06-13): threat-band reward scaling. The payout
        # scales by the THREAT BAND of where the target was — hunting a
        # mark in the Deep Wilds pays the danger premium; running down a
        # Frontier-zone target pays 0.6x, so a veteran can't farm newbie
        # contracts for full rate. Per difficulty_tiers_design_v1.md §7.
        # Scaled off contract.target_room_id (bound in drop 26); if the
        # contract has no bound room (legacy / unbound), the multiplier
        # is 1.0 (no change). Rides the same `bounty` faucet — no new
        # credit source. Failure-tolerant: any error leaves reward as-is.
        try:
            if reward > 0 and getattr(contract, "target_room_id", None):
                from engine.threat_band import (
                    get_effective_threat, reward_multiplier, threat_name,
                )
                _band = await get_effective_threat(
                    contract.target_room_id, ctx.db)
                _tmult = reward_multiplier(_band)
                if _tmult != 1.0:
                    _scaled = int(reward * _tmult)
                    _delta = _scaled - reward
                    reward = _scaled
                    if _delta > 0:
                        await ctx.session.send_line(
                            f"  Danger premium ({threat_name(_band)}): "
                            f"+{_delta:,} credits.")
                    elif _delta < 0:
                        await ctx.session.send_line(
                            f"  Low-threat contract ({threat_name(_band)}): "
                            f"{_delta:,} credits.")
        except Exception:
            log.debug("bounty threat-band multiplier calc failed "
                      "(non-fatal)", exc_info=True)
        char["credits"] = await ctx.db.adjust_credits(char["id"], reward, "bounty")

        # Clean up NPC if it still exists
        if npc and contract.target_npc_id:
            try:
                await ctx.db.delete_npc(contract.target_npc_id)
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass

        await ctx.session.send_line(
            ansi.success(f"  Bounty collected: {collected.target_name}")
        )
        _result_tag = " [EXCEPTIONAL +20%]" if _check.critical_success else (
            " [PARTIAL]" if _check.margin >= -4 and not _check.success else "")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Reward: +{reward:,} credits{ansi.RESET}{_result_tag}  "
            f"(Balance: {char['credits']:,} cr)"
        )
        await ctx.session.send_line(
            f"  Claim quality: {_skill.title()} [{_check.pool_str}]  "
            f"Roll {_check.roll} vs {_check.difficulty}"
        )
        await ctx.session.send_line(
            f"  Posted by: {collected.posting_org}"
        )
        await ctx.session.send_line(
            f"  {ansi.DIM}Type 'bounties' for your next contract.{ansi.RESET}"
        )

        log.info(
            "[bounty] %s collected %s for %dcr",
            char.get("name"), collected.id, reward,
        )

        # Narrative + faction rep hooks
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.BOUNTY_COLLECT,
                             f"Collected bounty on {collected.target_name} for {reward:,} credits",
                             {"target": collected.target_name, "reward": reward,
                              "org": collected.posting_org})
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.organizations import adjust_rep
            faction_id = char.get("faction_id", "independent")
            if faction_id and faction_id != "independent":
                await adjust_rep(
                    char, faction_id, ctx.db,
                    action_key="complete_bounty",
                    reason=f"Bounty collected: {collected.target_name}",
                    session=ctx.session,
                )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Ships log + profession chain hook
        try:
            from engine.ships_log import log_event as _blog
            await _blog(ctx.db, char, "bounties_collected")
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        try:
            from engine.tutorial_v2 import check_profession_chains
            await check_profession_chains(ctx.session, ctx.db, "bounty_collected")
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass
        # Spacer quest: bounty collected
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(
                ctx.session, ctx.db, "bounty",
                tier=getattr(collected, "tier", 0),
            )
        except Exception as _e:
            log.debug("silent except in parser/bounty_commands.py:422: %s", _e, exc_info=True)
        # Territory influence: mission complete in zone
        try:
            from engine.territory import on_mission_complete
            await on_mission_complete(ctx.db, char, char.get("room_id", 0))
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass


# ── Registration ───────────────────────────────────────────────────────────────

# S55: Switch & alias dispatch tables for the +bounty umbrella.
_BOUNTY_SWITCH_IMPL: dict = {}

_BOUNTY_ALIAS_TO_SWITCH: dict[str, str] = {
    # board
    "bounties":    "board",
    "bboard":      "board",
    "bountyboard": "board",
    "board":       "board",
    # claim
    "bountyclaim":  "claim",
    "claimbounty":  "claim",
    "acceptbounty": "claim",
    "claim":        "claim",
    # view (active hunt)
    "mybounty":     "view",
    "activebounty": "view",
    "myhunt":       "view",
    "view":         "view",
    # track
    "bountytrack":  "track",
    "tracktarget":  "track",
    "hunttrack":    "track",
    "track":        "track",
    # collect
    "bountycollect": "collect",
    "collectbounty": "collect",
    "claimreward":   "collect",
    "collect":       "collect",
}


class BountyCommand(BaseCommand):
    """`+bounty` umbrella — full S55 dispatch over the bounty board."""
    key = "+bounty"
    aliases: list[str] = [
        "bounties", "bboard", "bountyboard",
        "bountyclaim", "claimbounty", "acceptbounty",
        "mybounty", "activebounty", "myhunt",
        "bountytrack", "tracktarget", "hunttrack",
        "bountycollect", "collectbounty", "claimreward",
    ]
    help_text = (
        "Bounty verbs: '+bounty/board' (list), '+bounty/claim <id>', "
        "'+bounty/view' (active), '+bounty/track', '+bounty/collect'. "
        "Bare verbs (bounties/bountyclaim/...) still work. Type "
        "'help +bounty' for the full reference."
    )
    usage = "+bounty[/<switch>] [args]  — see 'help +bounty'"
    valid_switches: list[str] = ["view", "board", "claim", "track", "collect"]

    async def execute(self, ctx: CommandContext):
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _BOUNTY_ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "view",
            )
        impl_cls = _BOUNTY_SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return
        await impl_cls().execute(ctx)


def _init_bounty_switch_impl():
    _BOUNTY_SWITCH_IMPL["board"]   = BountiesCommand
    _BOUNTY_SWITCH_IMPL["claim"]   = BountyClaimCommand
    _BOUNTY_SWITCH_IMPL["view"]    = MyBountyCommand
    _BOUNTY_SWITCH_IMPL["track"]   = BountyTrackCommand
    _BOUNTY_SWITCH_IMPL["collect"] = BountyCollectCommand


_init_bounty_switch_impl()


def register_bounty_commands(registry) -> None:
    """Register all bounty commands. Call from game_server.py __init__."""
    for cmd in [
        BountyCommand(),
        BountiesCommand(),
        BountyClaimCommand(),
        MyBountyCommand(),
        BountyTrackCommand(),
        BountyCollectCommand(),
    ]:
        registry.register(cmd)
