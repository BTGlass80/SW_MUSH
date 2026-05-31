# -*- coding: utf-8 -*-
"""
parser/lead_commands.py — SRB.3 (May 22 2026)

Combined-action / Command-bonus surface per
`support_role_buffs_design_v1.md` §4.

Commands:
  +lead <action> for <player1> [<player2>...]  — Lead a combined action.
                                                  Rolls Command at one
                                                  of the standard
                                                  difficulties (auto-
                                                  selected from action
                                                  scope) or use the
                                                  /diff=<n> switch.
  +joinlead [<leader>]                          — Join a leader's
                                                  combined action.

R&E mechanic: a Command roll by the leader grants a bonus on the
NEXT skill roll by any member of the lead.

   Command diff 10 (Easy)      → +1D (+3 pips)
   Command diff 15 (Moderate)  → +2D (+6 pips)
   Command diff 20 (Difficult) → +3D (+9 pips, cap)

State is per-process in-memory via `engine/combined_actions.py`.
Per design §4.2, no schema. Bonus auto-expires after 60 seconds.

Substrate decisions:
- The +lead command does NOT itself roll a skill check that auto-
  consumes the bonus it just created. It calls perform_skill_check
  with `auto_consume_lead=False` so the leader's Command roll
  doesn't immediately eat the bonus they're about to stage. Once
  the offer is created, any subsequent roll by the leader OR
  followers consumes it.
- Leader is the same character whose Command roll succeeded. The
  R&E "follower contributes 1D of own skill" piece is NOT modeled
  in this drop (followers get the leader's bonus applied to their
  own rolls). Follower-skill-pooling is a follow-up.
- Difficulty auto-selection: if the leader doesn't pass /diff=,
  default to Moderate (15). They can always pass /diff=10 for an
  easier roll and smaller bonus.
"""
import logging
import time

from parser.commands import BaseCommand, CommandContext
from server import ansi
from engine.combined_actions import (
    create_lead_offer,
    join_lead,
    get_lead_offer_for,
    cancel_lead_offer,
    DIFFICULTY_TO_BONUS_PIPS,
    STANDARD_DIFFICULTIES,
    MAX_FOLLOWERS_PER_LEAD,
    LEAD_OFFER_DURATION_SECS,
)
from engine.skill_checks import perform_skill_check

log = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────────


def _parse_lead_args(args: str) -> tuple[str | None, list[str], str | None]:
    """Parse '+lead <action> for <p1> [p2...]'.

    Returns (action, [follower_names], error_or_None).

    Accepts the literal word " for " (case-insensitive, surrounded by
    spaces) as the separator. If no "for" appears, returns
    (None, [], "<usage error>").
    """
    if not args.strip():
        return (None, [],
                "Usage: +lead <action> for <player1> [<player2>...]")
    lowered = args.lower()
    # Look for " for " as a separator
    idx = lowered.find(" for ")
    if idx == -1:
        return (None, [],
                "Usage: +lead <action> for <player1> [<player2>...]")
    action = args[:idx].strip()
    followers_str = args[idx + len(" for "):].strip()
    if not action:
        return (None, [],
                "What action do you want to lead?")
    if not followers_str:
        return (None, [],
                "Who do you want to lead? Specify at least one player.")
    # Split on whitespace OR commas
    raw = followers_str.replace(",", " ").split()
    followers = [f for f in raw if f]
    if not followers:
        return (None, [],
                "Who do you want to lead? Specify at least one player.")
    if len(followers) > MAX_FOLLOWERS_PER_LEAD:
        return (None, [],
                f"Maximum {MAX_FOLLOWERS_PER_LEAD} followers per lead.")
    return (action, followers, None)


def _parse_difficulty_switch(switches: list[str]) -> tuple[int, str | None]:
    """Pull /diff=<n> from switches. Returns (difficulty, error_or_None).

    Defaults to Moderate (15) if no /diff= switch present.
    """
    for sw in switches:
        if sw.lower().startswith("diff="):
            raw = sw.split("=", 1)[1].strip()
            try:
                d = int(raw)
            except ValueError:
                return (0, f"Invalid difficulty: '{raw}'")
            if d not in DIFFICULTY_TO_BONUS_PIPS:
                opts = ", ".join(str(x) for x in STANDARD_DIFFICULTIES)
                return (0, f"Difficulty must be one of: {opts}")
            return (d, None)
    return (15, None)  # Default: Moderate


async def _resolve_follower_char(
    name: str, ctx: CommandContext, room_id: int,
) -> tuple[dict | None, str | None]:
    """Look up a character by name, must be in `room_id`.

    Returns (char_dict, error_or_None).
    """
    try:
        char = await ctx.db.get_character_by_name(name)
    except Exception:
        log.warning("_resolve_follower_char DB error", exc_info=True)
        return (None, f"Couldn't look up '{name}'.")
    if not char:
        return (None, f"No player named '{name}'.")
    if int(char.get("room_id") or 0) != int(room_id):
        return (None, f"{char['name']} is not in this room.")
    return (char, None)


# ── +lead command ────────────────────────────────────────────────────────


class LeadCommand(BaseCommand):
    key = "+lead"
    aliases: list[str] = []
    help_text = "Lead a combined action."
    usage = "+lead <action> for <player1> [<player2>...]   [/diff=10|15|20]"
    valid_switches: list[str] = ["diff"]

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("You can't lead while not in-game.")
            return

        # Parse args
        action, follower_names, err = _parse_lead_args(ctx.args)
        if err:
            await session.send_line(f"  {err}")
            return

        # Parse difficulty switch
        difficulty, err = _parse_difficulty_switch(ctx.switches)
        if err:
            await session.send_line(f"  {err}")
            return

        room_id = char["room_id"]

        # One-lead-per-leader rule (§4.1)
        existing = get_lead_offer_for(char["id"])
        if existing is not None and existing.leader_id == char["id"]:
            await session.send_line(
                f"  You're already leading: \"{existing.action}\". "
                "Use +lead/cancel or wait for it to resolve."
            )
            return

        # Resolve all follower targets BEFORE rolling — we don't want
        # a successful Command roll wasted on a typo'd name.
        resolved_followers: list[dict] = []
        for fname in follower_names:
            if fname.lower() == char["name"].lower():
                await session.send_line(
                    f"  You can't follow your own lead."
                )
                return
            fchar, err = await _resolve_follower_char(fname, ctx, room_id)
            if err:
                await session.send_line(f"  {err}")
                return
            resolved_followers.append(fchar)

        # Make the Command roll. Suppress auto-consume so the leader's
        # OWN roll doesn't immediately eat the bonus they're about to
        # stage (which would happen if they had a stale prior offer).
        result = perform_skill_check(
            char, "command", difficulty,
            lead_bonus=0,
            auto_consume_lead=False,
        )
        bonus_pips = DIFFICULTY_TO_BONUS_PIPS[difficulty]
        bonus_dice = bonus_pips // 3

        if not result.success:
            margin = result.margin
            await session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[LEAD]{ansi.RESET} "
                f"Your Command roll fails. The group looks to you "
                f"but doesn't quite catch your direction."
            )
            await session.send_line(
                f"  {ansi.DIM}(Command {result.pool_str}: "
                f"{result.roll} vs {difficulty}, margin {margin}){ansi.RESET}"
            )
            return

        # Stage the offer
        offer = create_lead_offer(
            leader_id=char["id"],
            action=action,
            difficulty=difficulty,
            room_id=room_id,
        )
        if offer is None:
            # Should not happen — we already checked one-lead-per-leader
            await session.send_line(
                f"  Unable to stage lead (you may already have an active one)."
            )
            return

        # Pre-populate the followers list — they've been "invited" but
        # need to +joinlead to confirm. Per design intent the leader
        # names the targets; followers opt in.
        # (We don't auto-add to offer.followers; +joinlead must be
        # explicit per the design's "Join a leader's combined action".)

        await session.send_line(
            f"  {ansi.BRIGHT_GREEN}[LEAD]{ansi.RESET} "
            f"You take charge: \"{action}\". "
            f"Bonus to next roll for any follower: "
            f"{ansi.BRIGHT_CYAN}{offer.bonus_dice_str()}{ansi.RESET}."
        )
        await session.send_line(
            f"  {ansi.DIM}(Command {result.pool_str}: "
            f"{result.roll} vs {difficulty}, "
            f"expires in {LEAD_OFFER_DURATION_SECS}s){ansi.RESET}"
        )

        # Broadcast to room — also pings the named followers
        names = ", ".join(f["name"] for f in resolved_followers)
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"  {ansi.player_name(char['name'])} takes charge of "
            f"\"{action}\" and calls on {names} to follow. "
            f"({offer.bonus_dice_str()} bonus available — "
            f"type {ansi.BRIGHT_WHITE}+joinlead{ansi.RESET} to join.)",
            exclude=session,
            source_char=char,
        )


# ── +joinlead command ────────────────────────────────────────────────────


class JoinLeadCommand(BaseCommand):
    key = "+joinlead"
    aliases: list[str] = []
    help_text = "Join an active lead in this room."
    usage = "+joinlead [<leader>]"
    valid_switches: list[str] = []

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("You can't join while not in-game.")
            return

        room_id = char["room_id"]
        target_name = ctx.args.strip()

        # If no leader specified, find ONE lead in the room
        if not target_name:
            # Find offers whose leader is in this room
            candidates: list = []
            try:
                # Scan all session-character pairs in the room
                for s in ctx.session_mgr.sessions_in_room(room_id):
                    if not s.character:
                        continue
                    offer = get_lead_offer_for(s.character["id"])
                    if offer and offer.leader_id == s.character["id"]:
                        candidates.append((s.character, offer))
            except Exception:
                log.warning("+joinlead room scan failed", exc_info=True)

            if not candidates:
                await session.send_line(
                    "  No active leads in this room."
                )
                return
            if len(candidates) > 1:
                names = ", ".join(c[0]["name"] for c in candidates)
                await session.send_line(
                    f"  Multiple leads available. Specify: +joinlead <leader>. "
                    f"Active: {names}."
                )
                return
            leader_char, offer = candidates[0]
        else:
            # Resolve by name
            leader_char, err = await _resolve_follower_char(
                target_name, ctx, room_id,
            )
            if err:
                await session.send_line(f"  {err}")
                return
            offer = get_lead_offer_for(leader_char["id"])
            if offer is None or offer.leader_id != leader_char["id"]:
                await session.send_line(
                    f"  {leader_char['name']} is not currently leading anything."
                )
                return

        # Verify same room (§4.1)
        if int(offer.room_id) != int(room_id):
            await session.send_line(
                "  That lead is in a different room."
            )
            return

        # Try to join
        ok, msg = join_lead(
            follower_id=char["id"],
            leader_id=leader_char["id"],
        )
        if not ok:
            await session.send_line(f"  {msg}")
            return

        await session.send_line(
            f"  {ansi.BRIGHT_GREEN}[LEAD]{ansi.RESET} {msg} "
            f"Your next skill roll will gain "
            f"{ansi.BRIGHT_CYAN}{offer.bonus_dice_str()}{ansi.RESET}."
        )
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"  {ansi.player_name(char['name'])} joins "
            f"{ansi.player_name(leader_char['name'])}'s lead.",
            exclude=session,
            source_char=char,
        )


# ── Registration ─────────────────────────────────────────────────────────


def register_lead_commands(registry):
    """Register +lead and +joinlead with the command registry."""
    for cmd in [LeadCommand(), JoinLeadCommand()]:
        registry.register(cmd)
