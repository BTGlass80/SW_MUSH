# -*- coding: utf-8 -*-
"""
parser/entertainer_commands.py  --  Entertainer income for social characters.

Commands:
  perform     Perform for credits in a cantina zone room.

Design (from handoff):
  - Must be in a Cantina zone room
  - Skill check: Persuasion (or Musical Instrument if character has it)
  - Difficulty: 10 baseline
  - Success: 50-200cr scaled by margin; room broadcast flavor text
  - Critical: 250-500cr; special audience reaction
  - Partial: 25cr; "polite applause"
  - Failure: 0cr; "awkward silence"; 5-minute cooldown
  - No-failure cooldown: 10 minutes between successful performs
  - Cantina brawl world event: payout x2
  - Cooldown tracked in character attributes JSON under "last_perform"
"""
import json
import time
import random
import logging
from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)

# Cooldown durations (seconds)
_SUCCESS_COOLDOWN = 600    # 10 minutes after success
_FAILURE_COOLDOWN = 300    # 5 minutes after failure

# Pay ranges
_BASE_PAY_MIN = 50
_BASE_PAY_MAX = 200
_CRIT_PAY_MIN = 250
_CRIT_PAY_MAX = 500
_PARTIAL_PAY = 25

# Performance difficulty
_PERFORM_DIFFICULTY = 10

# Flavor text pools
_SUCCESS_MESSAGES = [
    "The cantina crowd cheers as the performance wraps up.",
    "Patrons bang their mugs on the tables in appreciation.",
    "A few spacers in the back toss credits onto the stage.",
    "The bartender nods approvingly — good for business.",
    "Even the Rodian in the corner stops scowling for a moment.",
    "A table of smugglers raises their glasses in salute.",
]

_CRIT_MESSAGES = [
    "The entire cantina goes silent, then erupts in applause!",
    "A wealthy trader tosses a credit chip and winks. Big tipper.",
    "The performance draws a standing ovation from the regulars!",
    "Even the jaded bartender breaks into a rare smile.",
    "A Hutt messenger whispers that Jabba might be interested...",
]

_PARTIAL_MESSAGES = [
    "Polite applause. At least nobody threw anything.",
    "A few patrons clap halfheartedly. The band was better.",
    "The crowd barely notices, but a kind soul drops a few credits.",
]

_FAIL_MESSAGES = [
    "Awkward silence. Someone coughs. Time to sit down.",
    "A Devaronian at the bar laughs — at you, not with you.",
    "The bartender makes a 'wrap it up' gesture. Rough crowd.",
    "The cantina band gives you a pitying look from the stage.",
]


async def _get_room_zone_name(ctx) -> str:
    """Get the zone name for the character's current room."""
    room_id = ctx.session.character["room_id"]
    try:
        room = await ctx.db.get_room(room_id)
        if not room or not room.get("zone_id"):
            return ""
        zone = await ctx.db.get_zone(room["zone_id"])
        if not zone:
            return ""
        return (zone.get("name") or "").lower()
    except Exception:
        log.warning("_get_room_zone_name: unhandled exception", exc_info=True)
        return ""


def _get_last_perform(char: dict) -> float:
    """Read last_perform timestamp from attributes JSON."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
        return float(attrs.get("last_perform", 0))
    except Exception:
        log.warning("get_last_perform failed", exc_info=True)
        return 0


def _set_last_perform(char: dict, timestamp: float) -> str:
    """Set last_perform in attributes JSON, return updated JSON string."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
    except Exception:
        attrs = {}
    attrs["last_perform"] = timestamp
    return json.dumps(attrs)


def _has_musical_instrument(char: dict) -> bool:
    """Check if character has the Musical Instrument skill."""
    try:
        skills = json.loads(char.get("skills", "{}"))
        return bool(skills.get("musical instrument") or skills.get("musical_instrument"))
    except Exception:
        log.warning("_has_musical_instrument: unhandled exception", exc_info=True)
        return False


class PerformCommand(BaseCommand):
    key = "perform"
    aliases = ["+perform", "entertain", "play"]
    help_text = (
        "Perform for credits in a cantina. Uses Persuasion or "
        "Musical Instrument skill. 10-minute cooldown between performances."
    )
    usage = "perform"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character

        # ── Zone check: must be in a cantina ──
        zone_name = await _get_room_zone_name(ctx)
        if "cantina" not in zone_name:
            await ctx.session.send_line(
                "  You need to be in a cantina to perform. "
                "Try Chalmun's place."
            )
            return

        # ── Cooldown check ──
        now = time.time()
        last = _get_last_perform(char)
        elapsed = now - last

        # We don't know if last performance was success or fail from the
        # timestamp alone, so use the longer cooldown (10 min) universally
        # after the first successful perform. The 5-min fail cooldown
        # applies only on immediate failure (tracked via result below).
        if last > 0 and elapsed < _SUCCESS_COOLDOWN:
            remaining = int(_SUCCESS_COOLDOWN - elapsed)
            mins = remaining // 60
            secs = remaining % 60
            await ctx.session.send_line(
                f"  The crowd needs a break. Try again in "
                f"{mins}m {secs}s."
            )
            return

        # ── Pick skill: Musical Instrument preferred, else Persuasion ──
        if _has_musical_instrument(char):
            skill_name = "musical instrument"
        else:
            skill_name = "persuasion"

        # ── Perform the skill check ──
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(char, skill_name, _PERFORM_DIFFICULTY)

        # ── Check for cantina brawl world event (2x payout) ──
        brawl_mult = 1.0
        try:
            from engine.world_events import get_world_event_manager
            wem = get_world_event_manager()
            # Check if a cantina_brawl event is active
            status = wem.get_status()
            for evt in status:
                if "cantina_brawl" in evt.get("type", ""):
                    brawl_mult = 2.0
                    break
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        room_id = char["room_id"]
        char_name = char.get("name", "Someone")

        if result.success:
            if result.critical_success:
                # Critical: big payout + special reaction
                payout = random.randint(_CRIT_PAY_MIN, _CRIT_PAY_MAX)
                payout = int(payout * brawl_mult)
                flavor = random.choice(_CRIT_MESSAGES)
            else:
                # Normal success: scale pay by margin
                # margin 0 = min pay, margin 10+ = max pay
                scale = min(1.0, max(0.0, result.margin / 10))
                payout = int(_BASE_PAY_MIN + scale * (_BASE_PAY_MAX - _BASE_PAY_MIN))
                payout = int(payout * brawl_mult)
                flavor = random.choice(_SUCCESS_MESSAGES)

            new_credits = char.get("credits", 0) + payout
            char["credits"] = new_credits

            # Set cooldown
            new_attrs = _set_last_perform(char, now)
            char["attributes"] = new_attrs

            await ctx.db.save_character(
                char["id"], credits=new_credits, attributes=new_attrs
            )

            brawl_note = " (Brawl bonus!)" if brawl_mult > 1.0 else ""
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[PERFORM]{ansi.RESET} "
                f"{flavor} Earned {payout:,} credits.{brawl_note}"
            )
            await ctx.session.send_line(
                f"  {ansi.DIM}({skill_name.title()} {result.pool_str}: "
                f"{result.roll} vs {_PERFORM_DIFFICULTY}){ansi.RESET}"
            )
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  {ansi.player_name(char_name)} puts on a performance "
                f"for the cantina crowd. {flavor}",
                exclude=ctx.session,
                source_char=char,
        )

        elif result.margin >= -4:
            # Partial: small payout, mild reaction
            payout = int(_PARTIAL_PAY * brawl_mult)
            new_credits = char.get("credits", 0) + payout
            char["credits"] = new_credits

            # Shorter cooldown for partial (use success cooldown still)
            new_attrs = _set_last_perform(char, now)
            char["attributes"] = new_attrs

            await ctx.db.save_character(
                char["id"], credits=new_credits, attributes=new_attrs
            )

            flavor = random.choice(_PARTIAL_MESSAGES)
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[PERFORM]{ansi.RESET} "
                f"{flavor} Earned {payout:,} credits."
            )
            await ctx.session.send_line(
                f"  {ansi.DIM}({skill_name.title()} {result.pool_str}: "
                f"{result.roll} vs {_PERFORM_DIFFICULTY}){ansi.RESET}"
            )
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  {ansi.player_name(char_name)} attempts a performance. "
                f"It's... okay.",
                exclude=ctx.session,
                source_char=char,
        )

        else:
            # Failure: no credits, shorter cooldown
            # Set a failure cooldown (5 minutes from now, encoded as
            # a timestamp that's 5 min before the success cooldown window)
            fail_ts = now - (_SUCCESS_COOLDOWN - _FAILURE_COOLDOWN)
            new_attrs = _set_last_perform(char, fail_ts)
            char["attributes"] = new_attrs
            await ctx.db.save_character(char["id"], attributes=new_attrs)

            flavor = random.choice(_FAIL_MESSAGES)
            fumble_extra = ""
            if result.fumble:
                fumble_extra = " Someone throws a mug at you."

            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[PERFORM]{ansi.RESET} "
                f"{flavor}{fumble_extra}"
            )
            await ctx.session.send_line(
                f"  {ansi.DIM}({skill_name.title()} {result.pool_str}: "
                f"{result.roll} vs {_PERFORM_DIFFICULTY}){ansi.RESET}"
            )
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  {ansi.player_name(char_name)} tries to perform, but "
                f"it doesn't go well.",
                exclude=ctx.session,
                source_char=char,
        )


def register_entertainer_commands(registry):
    """Register entertainer commands with the command registry."""
    registry.register(PerformCommand())
