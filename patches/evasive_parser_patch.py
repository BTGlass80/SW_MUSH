"""
Evasive Maneuvers — parser/space_commands.py patch
Injects four new commands before SpawnShipCommand:

  JinkCommand   (jink)          — +5 difficulty to attackers this round
  BarrelRollCommand (barrelroll, broll) — +8 difficulty, costs pilot action
  LoopCommand   (loop)          — +8 difficulty + breaks tail lock
  SlipCommand   (slip)          — +10 difficulty + repositions to attacker's flank

All four:
  - Require pilot seat
  - Roll pilot skill + maneuverability vs a fixed difficulty
  - On success: set maneuver_bonus on SpaceGrid for this ship
  - On failure: no bonus, wasted action
  - Destroyed/damaged engines modify difficulty

Run from project root:
    python3 evasive_parser_patch.py
"""
import ast
import os
import sys

TARGET = os.path.join("parser", "space_commands.py")

# Inject the four new command classes immediately before SpawnShipCommand.
# Anchor: the unique SpawnShipCommand class header.

OLD_SPAWN_HEADER = '''\
class SpawnShipCommand(BaseCommand):
    key = "@spawn"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Spawn a ship in the current room (docking bay)."
    usage = "@spawn <template> <ship name>"'''

NEW_COMMANDS = '''\
# ── Evasive Maneuver Commands (Priority C) ────────────────────────────────────
#
# Star Warriors maneuver adaptation for D6 R&E:
#   Pilot rolls skill + maneuverability vs fixed difficulty.
#   On success: sets a one-shot bonus on SpaceGrid that raises attacker difficulty
#   for the FIRST attack resolved against this ship this round.
#   Failure = wasted action, no bonus.
#
# Maneuver table (adapted from Star Warriors):
#   jink        difficulty 10  +5 to attacker difficulty   single action
#   barrelroll  difficulty 13  +8 to attacker difficulty   single action, higher risk
#   loop        difficulty 15  +8 + breaks tail lock        double action
#   slip        difficulty 17  +10 + repositions to flank   double action
#
# Engine state modifiers (same as evade):
#   damaged   +5 to difficulty
#   destroyed maneuver impossible

async def _resolve_maneuver_cmd(ctx, maneuver_name: str, base_diff: int,
                                 attacker_bonus: int, breaks_tail: bool,
                                 repositions_flank: bool, num_actions: int):
    """Shared implementation for all evasive maneuver commands."""
    from engine.character import Character, SkillRegistry

    ship = await _get_ship_for_player(ctx)
    if not ship:
        await ctx.session.send_line("  You're not aboard a ship.")
        return
    if ship["docked_at"]:
        await ctx.session.send_line("  Can't maneuver while docked!")
        return
    crew = _get_crew(ship)
    if crew.get("pilot") != ctx.session.character["id"]:
        await ctx.session.send_line("  Only the pilot can execute evasive maneuvers.")
        return

    reg = get_ship_registry()
    template = reg.get(ship["template"])
    if not template:
        await ctx.session.send_line("  Unknown ship template.")
        return

    # Check engine state
    systems = _get_systems(ship)
    engine_state = systems.get("engines", "working")
    if isinstance(engine_state, bool):
        engine_state = "working" if engine_state else "damaged"

    if engine_state == "destroyed":
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}[HELM]{ansi.RESET} Engines destroyed — "
            f"{maneuver_name} impossible!")
        return

    engine_penalty = 5 if engine_state == "damaged" else 0
    total_diff = base_diff + engine_penalty

    # Build pilot pool
    char_obj = Character.from_db_dict(ctx.session.character)
    sr = SkillRegistry()
    sr.load_file("data/skills.yaml")
    pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
    maneuver_pool = DicePool.parse(template.maneuverability)

    from engine.dice import apply_multi_action_penalty, roll_d6_pool
    pool = DicePool(
        pilot_pool.dice + maneuver_pool.dice,
        pilot_pool.pips + maneuver_pool.pips,
    )
    pool = apply_multi_action_penalty(pool, num_actions)

    from engine.dice import roll_d6_pool
    roll = roll_d6_pool(pool)

    engine_note = f" (damaged engines +5)" if engine_penalty else ""
    diff_display = f"{total_diff}{engine_note}"
    name_upper = maneuver_name.upper()
    ship_id = ship["id"]
    grid = get_space_grid()

    if roll.total >= total_diff:
        # Success — set the maneuver bonus on the grid
        grid.set_maneuver_bonus(ship_id, attacker_bonus)

        # Loop/slip additional effects
        tail_note = ""
        if breaks_tail:
            # Clear all tail locks on this ship
            partners = list({k[1] for k in grid._positions if k[0] == ship_id}
                            | {k[0] for k in grid._positions if k[1] == ship_id})
            for other_id in partners:
                if other_id != ship_id:
                    if grid.get_position(other_id, ship_id) == RelativePosition.FRONT:
                        grid.set_position(other_id, ship_id, RelativePosition.FRONT)
                    grid.set_position(ship_id, other_id, RelativePosition.FRONT)
                    grid.set_position(other_id, ship_id, RelativePosition.FRONT)
            tail_note = " Tail lock broken!"

        flank_note = ""
        if repositions_flank:
            # Reposition this ship to the flank of all current pursuers
            partners = list({k[1] for k in grid._positions if k[0] == ship_id}
                            | {k[0] for k in grid._positions if k[1] == ship_id})
            for other_id in partners:
                if other_id != ship_id:
                    grid.set_position(ship_id, other_id, RelativePosition.FLANK)
                    grid.set_position(other_id, ship_id, RelativePosition.FLANK)
            flank_note = " Slipped to flank position!"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} executes a {maneuver_name}! "
            f"+{attacker_bonus} to attacker difficulty this round.{tail_note}{flank_note} "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )
    else:
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} attempts a {maneuver_name} — failed! "
            f"Wasted action. "
            f"(Roll: {roll.total} vs Diff: {diff_display})"
        )


class JinkCommand(BaseCommand):
    key = "jink"
    aliases = []
    help_text = (
        "Execute a jink maneuver (pilot only). Raises attacker difficulty by +5 "
        "for the next shot against you this round. Difficulty 10."
    )
    usage = "jink"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="jink",
            base_diff=10,
            attacker_bonus=5,
            breaks_tail=False,
            repositions_flank=False,
            num_actions=1,
        )


class BarrelRollCommand(BaseCommand):
    key = "barrelroll"
    aliases = ["broll"]
    help_text = (
        "Execute a barrel roll (pilot only). Raises attacker difficulty by +8 "
        "for the next shot this round. Difficulty 13."
    )
    usage = "barrelroll"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="barrel roll",
            base_diff=13,
            attacker_bonus=8,
            breaks_tail=False,
            repositions_flank=False,
            num_actions=1,
        )


class LoopCommand(BaseCommand):
    key = "loop"
    aliases = ["immelmann"]
    help_text = (
        "Execute a full loop (pilot only). Raises attacker difficulty by +8 AND "
        "breaks all tail locks. Double action — costs your pilot's turn. Difficulty 15."
    )
    usage = "loop"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="loop",
            base_diff=15,
            attacker_bonus=8,
            breaks_tail=True,
            repositions_flank=False,
            num_actions=2,
        )


class SlipCommand(BaseCommand):
    key = "slip"
    aliases = ["sideslip"]
    help_text = (
        "Execute a side-slip (pilot only). Raises attacker difficulty by +10 AND "
        "repositions to their flank. Double action. Difficulty 17."
    )
    usage = "slip"

    async def execute(self, ctx):
        await _resolve_maneuver_cmd(
            ctx,
            maneuver_name="side-slip",
            base_diff=17,
            attacker_bonus=10,
            breaks_tail=False,
            repositions_flank=True,
            num_actions=2,
        )


class SpawnShipCommand(BaseCommand):
    key = "@spawn"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Spawn a ship in the current docking bay."
    usage = "@spawn <template> <ship name>"'''


def apply_patches(src: str) -> str:
    out = src

    if OLD_SPAWN_HEADER not in out:
        raise ValueError("Anchor not found (SpawnShipCommand class header)")
    out = out.replace(OLD_SPAWN_HEADER, NEW_COMMANDS, 1)

    return out


def main():
    if not os.path.exists(TARGET):
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    print(f"Read {len(src)} bytes from {TARGET}")

    try:
        patched = apply_patches(src)
    except ValueError as e:
        print(f"PATCH FAILED: {e}")
        sys.exit(1)

    try:
        ast.parse(patched)
        print("Syntax check: PASSED")
    except SyntaxError as e:
        print(f"SYNTAX ERROR after patching: {e}")
        sys.exit(1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(patched)

    print(f"Patched {TARGET} successfully.")
    print()
    print("Commands added:")
    print("  jink        — +5 difficulty to next attacker, diff 10")
    print("  barrelroll  — +8 difficulty to next attacker, diff 13")
    print("  loop        — +8 difficulty + breaks tail lock, diff 15 (double action)")
    print("  slip        — +10 difficulty + flank reposition, diff 17 (double action)")


if __name__ == "__main__":
    main()
