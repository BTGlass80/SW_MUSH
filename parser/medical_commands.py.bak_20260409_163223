# -*- coding: utf-8 -*-
"""
parser/medical_commands.py  --  Player-to-player healing for credits.

Commands:
  heal <target>       Offer to heal a wounded player in the same room.
  healaccept          Accept a pending heal offer.
  healrate <credits>  Set your healing rate (persisted in attributes JSON).

Design (from handoff):
  - Healer must have First Aid or Medicine skill (at least 1 pip above attribute)
  - Skill check: perform_skill_check(healer, "first aid", difficulty)
  - Difficulty scales with wound level:
      Stunned: 8, Wounded: 11, Incapacitated: 16, Mortally Wounded: 21
  - Success: reduce target wound level by 1 step; credits transferred
  - Partial (margin >= -4): no improvement, "bleeding stabilised" flavor
  - Critical: reduce wound level by 2 steps (minimum 1 step improvement)
  - Failure: no improvement, no refund
  - Cannot self-heal (use bacta tank)
  - Target must consent via 'healaccept'
"""
import json
import time
from parser.commands import BaseCommand, CommandContext
from server import ansi

# In-memory pending heal offers: target_char_id -> offer_dict
# Offers expire after 60 seconds.
_pending_heals: dict[int, dict] = {}

# Wound level constants (matching engine/character.py WoundLevel)
_WL_HEALTHY = 0
_WL_STUNNED = 1
_WL_WOUNDED = 2
_WL_WOUNDED2 = 3      # Second wound (stored as 3 in some paths)
_WL_INCAPACITATED = 4
_WL_MORTALLY_WOUNDED = 5
_WL_DEAD = 6

_WOUND_NAMES = {
    0: "Healthy",
    1: "Stunned",
    2: "Wounded",
    3: "Wounded (x2)",
    4: "Incapacitated",
    5: "Mortally Wounded",
    6: "Dead",
}

_HEAL_DIFFICULTY = {
    1: 8,    # Stunned: Easy
    2: 11,   # Wounded: Moderate
    3: 14,   # Wounded x2: Moderate+
    4: 16,   # Incapacitated: Difficult
    5: 21,   # Mortally Wounded: Very Difficult
}

_DEFAULT_HEAL_RATE = 200


def _get_heal_rate(char: dict) -> int:
    """Read the healer's rate from attributes JSON."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
        return int(attrs.get("heal_rate", _DEFAULT_HEAL_RATE))
    except Exception:
        return _DEFAULT_HEAL_RATE


def _set_heal_rate(char: dict, rate: int) -> str:
    """Set heal_rate in attributes JSON, return updated JSON string."""
    try:
        attrs = json.loads(char.get("attributes", "{}"))
    except Exception:
        attrs = {}
    attrs["heal_rate"] = rate
    return json.dumps(attrs)


def _has_healing_skill(char: dict) -> tuple[bool, str]:
    """
    Check if char has First Aid or Medicine above raw attribute.
    Returns (has_skill, skill_name).
    Medicine is preferred if both are trained.
    """
    try:
        skills = json.loads(char.get("skills", "{}"))
    except Exception:
        skills = {}

    # Check Medicine first (better skill)
    if skills.get("medicine"):
        return True, "medicine"
    if skills.get("first aid"):
        return True, "first aid"
    return False, ""


def _find_target_session(ctx, target_name: str):
    """Find a player session in the same room by name prefix."""
    room_id = ctx.session.character["room_id"]
    target_name_lower = target_name.strip().lower()
    matches = []
    for s in ctx.session_mgr.sessions_in_room(room_id):
        if not s.character or s.character["id"] == ctx.session.character["id"]:
            continue
        cname = s.character.get("name", "").lower()
        if cname == target_name_lower or cname.startswith(target_name_lower):
            matches.append(s)
    if len(matches) == 1:
        return matches[0]
    return None


class HealCommand(BaseCommand):
    key = "heal"
    aliases = []
    help_text = (
        "Offer to heal a wounded player in the same room. "
        "Requires First Aid or Medicine skill. Target must type 'healaccept'."
    )
    usage = "heal <player name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: heal <player name>")
            await ctx.session.send_line(
                f"  Your heal rate: {_get_heal_rate(ctx.session.character):,} credits"
            )
            return

        char = ctx.session.character

        # Must have First Aid or Medicine
        has_skill, skill_name = _has_healing_skill(char)
        if not has_skill:
            await ctx.session.send_line(
                "  You need First Aid or Medicine skill to heal others."
            )
            return

        # Find target
        target_session = _find_target_session(ctx, ctx.args.strip())
        if not target_session:
            await ctx.session.send_line(
                f"  Can't find '{ctx.args}' in this room."
            )
            return

        target_char = target_session.character
        target_name = target_char.get("name", "Unknown")
        target_wound = target_char.get("wound_level", 0)

        # Validation
        if target_char["id"] == char["id"]:
            await ctx.session.send_line("  You can't heal yourself. Try a bacta tank.")
            return

        if target_wound <= _WL_HEALTHY:
            await ctx.session.send_line(
                f"  {target_name} is perfectly healthy."
            )
            return

        if target_wound >= _WL_DEAD:
            await ctx.session.send_line(
                f"  {target_name} is beyond medical help."
            )
            return

        rate = _get_heal_rate(char)
        target_credits = target_char.get("credits", 0)

        if target_credits < rate:
            await ctx.session.send_line(
                f"  {target_name} only has {target_credits:,} credits "
                f"(your rate is {rate:,})."
            )
            return

        wound_name = _WOUND_NAMES.get(target_wound, "Wounded")
        difficulty = _HEAL_DIFFICULTY.get(target_wound, 16)

        # Store pending offer
        _pending_heals[target_char["id"]] = {
            "healer_id": char["id"],
            "healer_session": ctx.session,
            "healer_name": char.get("name", "Unknown"),
            "skill_name": skill_name,
            "difficulty": difficulty,
            "rate": rate,
            "target_wound": target_wound,
            "timestamp": time.time(),
        }

        # Notify both players
        await ctx.session.send_line(
            f"  You offer to treat {ansi.player_name(target_name)}'s "
            f"injuries ({wound_name}) for {rate:,} credits."
        )
        await ctx.session.send_line(
            f"  {ansi.DIM}Skill: {skill_name.title()} "
            f"({_get_pool_str(char, skill_name)}) vs Difficulty {difficulty}{ansi.RESET}"
        )
        await target_session.send_line(
            f"  {ansi.player_name(char.get('name', 'Someone'))} offers to "
            f"treat your wounds ({wound_name}) for {rate:,} credits."
        )
        await target_session.send_line(
            f"  Type {ansi.BRIGHT_CYAN}healaccept{ansi.RESET} to accept, "
            f"or ignore to decline."
        )

        # Broadcast to room
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {ansi.player_name(char.get('name', 'Someone'))} examines "
            f"{ansi.player_name(target_name)}'s injuries.",
            exclude=ctx.session,
        )


def _get_pool_str(char: dict, skill_name: str) -> str:
    """Quick helper to show the healer's skill pool."""
    try:
        from engine.skill_checks import _get_skill_pool, _pool_to_str
        dice, pips = _get_skill_pool(char, skill_name, None)
        return _pool_to_str(dice, pips)
    except Exception:
        return "?"


class HealAcceptCommand(BaseCommand):
    key = "healaccept"
    aliases = ["haccept"]
    help_text = "Accept a pending heal offer."
    usage = "healaccept"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = char["id"]

        # Check for pending offer
        offer = _pending_heals.pop(char_id, None)
        if not offer:
            await ctx.session.send_line("  No pending heal offer.")
            return

        # Check expiry (60 seconds)
        if time.time() - offer["timestamp"] > 60:
            await ctx.session.send_line("  That heal offer has expired.")
            return

        # Verify healer is still in the room
        healer_session = offer["healer_session"]
        if (not healer_session.character
                or healer_session.character.get("room_id") != char.get("room_id")):
            await ctx.session.send_line("  The healer is no longer nearby.")
            return

        # Verify credits
        rate = offer["rate"]
        credits = char.get("credits", 0)
        if credits < rate:
            await ctx.session.send_line(
                f"  Not enough credits ({credits:,} < {rate:,})."
            )
            return

        # Re-check wound level (may have changed)
        target_wound = char.get("wound_level", 0)
        if target_wound <= _WL_HEALTHY:
            await ctx.session.send_line("  You're already healthy!")
            return
        if target_wound >= _WL_DEAD:
            await ctx.session.send_line("  You're beyond medical help.")
            return

        difficulty = _HEAL_DIFFICULTY.get(target_wound, offer["difficulty"])
        skill_name = offer["skill_name"]
        healer_char = healer_session.character

        # ── Perform the skill check ──
        from engine.skill_checks import perform_skill_check
        result = perform_skill_check(healer_char, skill_name, difficulty)

        healer_name = healer_char.get("name", "Someone")
        room_id = char["room_id"]
        wound_name = _WOUND_NAMES.get(target_wound, "Wounded")

        if result.success:
            # Reduce wound level
            if result.critical_success and target_wound >= 2:
                # Critical: reduce by 2 steps (min result = Healthy)
                new_wound = max(0, target_wound - 2)
                heal_msg = "Expert treatment! Two levels of injury healed."
            else:
                new_wound = max(0, target_wound - 1)
                heal_msg = "Treatment successful."

            new_wound_name = _WOUND_NAMES.get(new_wound, "Healthy")

            # Transfer credits
            new_patient_credits = credits - rate
            healer_credits = healer_char.get("credits", 0) + rate
            char["credits"] = new_patient_credits
            char["wound_level"] = new_wound
            healer_char["credits"] = healer_credits

            await ctx.db.save_character(char_id,
                                        credits=new_patient_credits,
                                        wound_level=new_wound)
            await ctx.db.save_character(healer_char["id"],
                                        credits=healer_credits)

            # Notify
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_GREEN}[MEDICAL]{ansi.RESET} {heal_msg} "
                f"{wound_name} → {new_wound_name}. "
                f"Paid {rate:,} credits."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_GREEN}[MEDICAL]{ansi.RESET} {heal_msg} "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty}) "
                f"Earned {rate:,} credits."
            )
            await ctx.session_mgr.broadcast_to_room(
                room_id,
                f"  {ansi.player_name(healer_name)} treats "
                f"{ansi.player_name(char.get('name', 'someone'))}'s wounds.",
                exclude=[ctx.session, healer_session],
            )

        elif result.margin >= -4:
            # Partial: no wound improvement, flavor text, no payment
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[MEDICAL]{ansi.RESET} "
                f"The treatment stabilises the bleeding but doesn't fully take. "
                f"No charge."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_YELLOW}[MEDICAL]{ansi.RESET} "
                f"Close, but the treatment doesn't hold. "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty}) "
                f"No charge."
            )

        else:
            # Failure: no improvement, no payment
            fumble_extra = " Something went wrong!" if result.fumble else ""
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[MEDICAL]{ansi.RESET} "
                f"The treatment fails.{fumble_extra} No charge."
            )
            await healer_session.send_line(
                f"  {ansi.BRIGHT_RED}[MEDICAL]{ansi.RESET} "
                f"Treatment failed. "
                f"({skill_name.title()} {result.pool_str}: {result.roll} vs {difficulty})"
                f"{fumble_extra}"
            )


class HealRateCommand(BaseCommand):
    key = "healrate"
    aliases = ["hrate"]
    help_text = "Set your healing rate in credits."
    usage = "healrate <credits>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character

        if not ctx.args:
            rate = _get_heal_rate(char)
            await ctx.session.send_line(
                f"  Your heal rate: {rate:,} credits per treatment."
            )
            await ctx.session.send_line(
                f"  Usage: healrate <amount> to change it."
            )
            return

        try:
            rate = int(ctx.args.strip())
        except ValueError:
            await ctx.session.send_line("  Usage: healrate <number>")
            return

        if rate < 0:
            await ctx.session.send_line("  Rate must be positive.")
            return
        if rate > 100000:
            await ctx.session.send_line("  That's... ambitious. Max 100,000.")
            return

        new_attrs = _set_heal_rate(char, rate)
        char["attributes"] = new_attrs
        await ctx.db.save_character(char["id"], attributes=new_attrs)

        await ctx.session.send_line(
            f"  Heal rate set to {rate:,} credits per treatment."
        )


def register_medical_commands(registry):
    """Register medical commands with the command registry."""
    for cmd in [HealCommand(), HealAcceptCommand(), HealRateCommand()]:
        registry.register(cmd)
