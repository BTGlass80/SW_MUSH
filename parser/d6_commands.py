"""
D6 dice commands - roll, check, opposed.

Lets players use the dice engine directly in-game.
"""
from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.dice import (
    DicePool, roll_d6_pool, difficulty_check, opposed_roll, Difficulty,
)
from engine.character import Character, SkillRegistry
from server import ansi
import logging

log = logging.getLogger(__name__)


def _get_skill_reg(ctx) -> SkillRegistry:
    """Get the skill registry from the game server."""
    # The game server stores it; reach through session_mgr's parent
    # For now, load it fresh if needed (it's cached after first load)
    if not hasattr(ctx, '_skill_reg_cache'):
        import os
        reg = SkillRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            reg.load_file(skills_path)
        ctx._skill_reg_cache = reg
    return ctx._skill_reg_cache


class RollCommand(BaseCommand):
    key = "+roll"
    aliases = ["roll"]
    help_text = (
        "Roll dice using D6 notation. Includes the Wild Die.\n"
        "\n"
        "EXAMPLES:\n"
        "  +roll 4D         -- roll 4 dice\n"
        "  +roll 3D+2       -- roll 3 dice, add 2\n"
        "  +roll 5D blaster -- labeled roll"
    )
    usage = "roll <dice|skill> [modifier]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: roll <dice>  or  roll <skill>")
            await ctx.session.send_line("  Examples: roll 4D+2  |  roll blaster  |  roll dodge -1D")
            return

        parts = ctx.args.split()
        char = ctx.session.character
        modifier = DicePool(0, 0)

        # Check for trailing modifier like +1D or -1D
        if len(parts) >= 2 and (parts[-1].upper().endswith("D") or "D+" in parts[-1].upper() or "D-" in parts[-1].upper()):
            last = parts[-1]
            if last.startswith("+") or last.startswith("-"):
                try:
                    mod_val = DicePool.parse(last.lstrip("+"))
                    if last.startswith("-"):
                        modifier = DicePool(-mod_val.dice, -mod_val.pips)
                    else:
                        modifier = mod_val
                    parts = parts[:-1]
                except (ValueError, IndexError) as _e:
                    log.debug("silent except in parser/d6_commands.py:66: %s", _e, exc_info=True)

        pool_str = " ".join(parts)

        # Try parsing as a raw dice pool first (e.g. "4D+2")
        try:
            pool = DicePool.parse(pool_str)
            if pool.dice > 0 or pool.pips > 0:
                if modifier.dice != 0 or modifier.pips != 0:
                    pool = DicePool(pool.dice + modifier.dice, pool.pips + modifier.pips)
                result = roll_d6_pool(pool)
                await ctx.session.send_line(f"  {ansi.bright_white(result.display())}")
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"  {ansi.player_name(char['name'])} rolls {pool}: {ansi.bright_white(str(result.total))}",
                    exclude=ctx.session,
                )
                return
        except (ValueError, IndexError) as _e:
            log.debug("silent except in parser/d6_commands.py:85: %s", _e, exc_info=True)

        # Try as a skill name
        skill_reg = _get_skill_reg(ctx)
        sd = skill_reg.get(pool_str)
        if not sd:
            # Partial match
            matches = [s for s in skill_reg.all_skills()
                       if s.name.lower().startswith(pool_str.lower())]
            if len(matches) == 1:
                sd = matches[0]
            elif len(matches) > 1:
                names = ", ".join(m.name for m in matches[:5])
                await ctx.session.send_line(f"  Ambiguous skill: {names}")
                return

        if sd:
            char_obj = Character.from_db_dict(char)
            pool = char_obj.get_skill_pool(sd.name, skill_reg)
            if modifier.dice != 0 or modifier.pips != 0:
                pool = DicePool(pool.dice + modifier.dice, pool.pips + modifier.pips)

            result = roll_d6_pool(pool)
            await ctx.session.send_line(
                f"  {ansi.cyan(sd.name)} ({sd.attribute[:3].upper()}): "
                f"{ansi.bright_white(result.display())}"
            )
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                f"  {ansi.player_name(char['name'])} rolls {sd.name}: "
                f"{ansi.bright_white(str(result.total))}",
                exclude=ctx.session,
            )
        else:
            await ctx.session.send_line(
                f"  '{pool_str}' isn't a dice pool or known skill."
            )


class CheckCommand(BaseCommand):
    key = "+check"
    aliases = ["check"]
    help_text = (
        "Roll your skill against a difficulty number.\n"
        "Uses full skill pool (attribute + skill ranks).\n"
        "\n"
        "EXAMPLES:\n"
        "  +check blaster 15    -- blaster vs diff 15\n"
        "  +check persuasion 10 -- persuasion vs diff 10"
    )
    usage = "check <skill> <difficulty|number>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line(
                "Usage: check <skill> <difficulty>")
            await ctx.session.send_line(
                "  Difficulties: very_easy(5) easy(10) moderate(15) "
                "difficult(20) very_difficult(25) heroic(30)")
            await ctx.session.send_line(
                "  Examples: check blaster moderate  |  check dodge 18")
            return

        parts = ctx.args.rsplit(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line("  Need both a skill and a difficulty.")
            return

        skill_str = parts[0].strip()
        diff_str = parts[1].strip()

        # Parse difficulty
        target = None
        try:
            target = int(diff_str)
        except ValueError:
            try:
                target = Difficulty.from_name(diff_str).value
            except (ValueError, KeyError):
                await ctx.session.send_line(
                    f"  Unknown difficulty: '{diff_str}'. "
                    f"Use a number or: easy, moderate, difficult, very_difficult, heroic")
                return

        # Resolve skill
        char = ctx.session.character
        skill_reg = _get_skill_reg(ctx)
        sd = skill_reg.get(skill_str)
        if not sd:
            matches = [s for s in skill_reg.all_skills()
                       if s.name.lower().startswith(skill_str.lower())]
            if len(matches) == 1:
                sd = matches[0]
            elif len(matches) > 1:
                names = ", ".join(m.name for m in matches[:5])
                await ctx.session.send_line(f"  Ambiguous skill: {names}")
                return

        if not sd:
            await ctx.session.send_line(f"  Unknown skill: '{skill_str}'")
            return

        char_obj = Character.from_db_dict(char)
        pool = char_obj.get_skill_pool(sd.name, skill_reg)
        result = difficulty_check(pool, target)

        diff_name = Difficulty.describe(target)
        if result.success:
            outcome = ansi.green(f"SUCCESS by {result.margin}")
        else:
            outcome = ansi.red(f"FAILURE by {abs(result.margin)}")

        await ctx.session.send_line(
            f"  {ansi.cyan(sd.name)} vs {diff_name} ({target}): "
            f"{result.roll.display()} -> {outcome}"
        )

        # Room sees abbreviated result
        if result.success:
            room_msg = f"{ansi.player_name(char['name'])} succeeds at a {sd.name} check!"
        else:
            room_msg = f"{ansi.player_name(char['name'])} fails a {sd.name} check."
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"], f"  {room_msg}", exclude=ctx.session,
        )


class OpposedCommand(BaseCommand):
    key = "+opposed"
    aliases = ["opposed", "vs"]
    help_text = "Roll an opposed check (your skill vs a target number or pool)."
    usage = "opposed <your_skill> <target_dice>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line(
                "Usage: opposed <skill> <target_dice>")
            await ctx.session.send_line(
                "  Example: opposed dodge 5D+1  (your dodge vs 5D+1)")
            return

        parts = ctx.args.rsplit(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line("  Need your skill and the opposing dice pool.")
            return

        skill_str = parts[0].strip()
        opp_str = parts[1].strip()

        # Parse opposing pool
        try:
            opp_pool = DicePool.parse(opp_str)
        except (ValueError, IndexError):
            await ctx.session.send_line(f"  Invalid opposing dice: '{opp_str}'")
            return

        # Resolve skill
        char = ctx.session.character
        skill_reg = _get_skill_reg(ctx)
        sd = skill_reg.get(skill_str)
        if not sd:
            matches = [s for s in skill_reg.all_skills()
                       if s.name.lower().startswith(skill_str.lower())]
            if len(matches) == 1:
                sd = matches[0]

        if not sd:
            await ctx.session.send_line(f"  Unknown skill: '{skill_str}'")
            return

        char_obj = Character.from_db_dict(char)
        pool = char_obj.get_skill_pool(sd.name, skill_reg)
        result = opposed_roll(pool, opp_pool)

        if result.attacker_wins:
            outcome = ansi.green(f"You WIN by {result.margin}")
        else:
            outcome = ansi.red(f"You LOSE by {abs(result.margin)}")

        await ctx.session.send_line(
            f"  {ansi.cyan(sd.name)} ({pool}) vs {opp_pool}:"
        )
        await ctx.session.send_line(
            f"    You:       {result.attacker_roll.display()}"
        )
        await ctx.session.send_line(
            f"    Opponent:  {result.defender_roll.display()}"
        )
        await ctx.session.send_line(f"    -> {outcome}")

        if result.attacker_wins:
            room_msg = f"{ansi.player_name(char['name'])} wins an opposed {sd.name} roll!"
        else:
            room_msg = f"{ansi.player_name(char['name'])} loses an opposed {sd.name} roll."
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"], f"  {room_msg}", exclude=ctx.session,
        )


def register_d6_commands(registry):
    """Register all D6 dice commands."""
    registry.register(RollCommand())
    registry.register(CheckCommand())
    registry.register(OpposedCommand())
