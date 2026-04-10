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
        from engine.bounty_board import format_bounty_board
        for line in format_bounty_board(board.posted_contracts()):
            await ctx.session.send_line(line)


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
        from engine.character import Character, SkillRegistry

        # Load character for skill lookup
        char_row = await ctx.db.get_character(char["id"])
        if not char_row:
            await ctx.session.send_line("  Character data error.")
            return

        skill_reg = SkillRegistry()
        char_obj = Character.from_db_dict(char_row, skill_reg)

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
        old_credits = char.get("credits", 0)
        new_credits = old_credits + reward
        char["credits"] = new_credits
        await ctx.db.save_character(char["id"], credits=new_credits)

        # Clean up NPC if it still exists
        if npc and contract.target_npc_id:
            try:
                await ctx.db.delete_npc(contract.target_npc_id)
            except Exception:
                pass

        await ctx.session.send_line(
            ansi.success(f"  Bounty collected: {collected.target_name}")
        )
        _result_tag = " [EXCEPTIONAL +20%]" if _check.critical_success else (
            " [PARTIAL]" if _check.margin >= -4 and not _check.success else "")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Reward: +{reward:,} credits{ansi.RESET}{_result_tag}  "
            f"(Balance: {new_credits:,} cr)"
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


# ── Registration ───────────────────────────────────────────────────────────────

def register_bounty_commands(registry) -> None:
    """Register all bounty commands. Call from game_server.py __init__."""
    for cmd in [
        BountiesCommand(),
        BountyClaimCommand(),
        MyBountyCommand(),
        BountyTrackCommand(),
        BountyCollectCommand(),
    ]:
        registry.register(cmd)
