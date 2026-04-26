"""
NPC Crew Commands -- hire, manage, and direct NPC crew members.

Player commands:
  hire                    - Browse available crew at this location
  hire <name|#>           - Hire an NPC (starts daily wage)
  roster                  - View your hired crew and assignments
  assign <name> <station> - Assign an NPC to a station on your current ship
  unassign <name>         - Pull an NPC off their station (stays hired)
  dismiss <name>          - Fire an NPC (stops wages, NPC becomes available)
  order <station> <action>- Give a tactical order to NPC crew in combat
"""
import json
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.npc_crew import (
    generate_hiring_board, format_hire_entry, format_roster_entry,
    CREW_ROLES, VALID_STATIONS, TIER_WAGES,
    set_npc_station, remove_npc_from_station, remove_npc_from_all_stations,
    get_crew_json,
)
from server import ansi

log = logging.getLogger(__name__)


# -- Helpers --

def _match_npc_by_name(npcs: list[dict], query: str) -> dict | None:
    """Match an NPC from a list by name (partial, case-insensitive)."""
    q = query.strip().lower()
    # Exact match first
    for npc in npcs:
        if npc["name"].lower() == q:
            return npc
    # Partial match
    for npc in npcs:
        if npc["name"].lower().startswith(q):
            return npc
    return None


def _match_npc_by_index(npcs: list[dict], query: str) -> dict | None:
    """Match an NPC by 1-based index number."""
    try:
        idx = int(query) - 1
        if 0 <= idx < len(npcs):
            return npcs[idx]
    except (ValueError, IndexError) as _e:
        log.debug("silent except in parser/crew_commands.py:50: %s", _e, exc_info=True)
    return None


async def _get_ship_for_player(ctx):
    """Get the ship the player is currently aboard (by bridge room)."""
    room_id = ctx.session.character["room_id"]
    return await ctx.db.get_ship_by_bridge(room_id)


# -- Commands --

class HireCommand(BaseCommand):
    key = "hire"
    aliases = ["recruiting", "hireboard"]
    help_text = (
        "Browse and hire NPC crew members. Use 'hire' to see who's available, "
        "'hire <name or #>' to hire. Hired crew earn daily wages from your credits."
    )
    usage = "hire [name or #]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        char_id = char["id"]
        room_id = char["room_id"]

        # -- No argument: show the hiring board --
        if not ctx.args:
            # Check for unhired NPCs already in this room (persistent board)
            available = await ctx.db.get_unhired_npcs_in_room(room_id)

            if not available:
                # Generate a fresh board and persist the NPCs
                room = await ctx.db.get_room(room_id)
                props = {}
                if room:
                    try:
                        props = json.loads(room.get("properties", "{}"))
                    except (json.JSONDecodeError, TypeError) as _e:
                        log.debug("silent except in parser/crew_commands.py:89: %s", _e, exc_info=True)
                profile = props.get("hiring_profile", "default")
                board = generate_hiring_board(profile)

                for entry in board:
                    sheet = entry["sheet"]
                    npc_id = await ctx.db.create_npc(
                        name=sheet.get("name", "Unknown"),
                        room_id=room_id,
                        species=entry["species"],
                    )
                    # Persist char_sheet_json with tier/template/skills
                    await ctx.db.update_npc(
                        npc_id,
                        char_sheet_json=json.dumps(sheet),
                        hire_wage=entry["wage"],
                    )

                # Re-fetch to get full rows
                available = await ctx.db.get_unhired_npcs_in_room(room_id)

            if not available:
                await ctx.session.send_line(
                    "  No crew available for hire at this location.")
                return

            await ctx.session.send_line(
                f"  {ansi.BOLD}=== Available Crew for Hire ==={ansi.RESET}")
            for i, npc in enumerate(available, 1):
                sheet_json = npc.get("char_sheet_json", "{}")
                if isinstance(sheet_json, str):
                    try:
                        sheet = json.loads(sheet_json)
                    except (json.JSONDecodeError, TypeError):
                        sheet = {}
                else:
                    sheet = sheet_json
                tier = sheet.get("tier", "average").title()
                template = sheet.get("template", "").title()
                wage = npc.get("hire_wage", 0)
                # Find primary skill for display
                skills = sheet.get("skills", {})
                best_skill = ""
                best_val = ""
                for role_name, role in CREW_ROLES.items():
                    if role.skill in skills:
                        best_skill = role.skill.title()
                        best_val = skills[role.skill]
                        break
                skill_str = f"{best_skill} {best_val}" if best_skill else template
                await ctx.session.send_line(
                    f"  {i}. {npc['name']:20s} {template:12s} ({tier:8s})  "
                    f"{skill_str:28s}  {wage:,} cr/day")

            await ctx.session.send_line("")
            await ctx.session.send_line(
                f"  {ansi.DIM}Type 'hire <name or #>' to hire. "
                f"'roster' to see your crew.{ansi.RESET}")
            return

        # -- Hire a specific NPC --
        available = await ctx.db.get_unhired_npcs_in_room(room_id)
        if not available:
            await ctx.session.send_line(
                "  No crew available for hire here. Type 'hire' to refresh the board.")
            return

        # Try index first, then name
        npc = _match_npc_by_index(available, ctx.args.strip())
        if not npc:
            npc = _match_npc_by_name(available, ctx.args.strip())
        if not npc:
            await ctx.session.send_line(
                f"  No one matching '{ctx.args}' on the hiring board. "
                f"Type 'hire' to see who's available.")
            return

        # Check if player can afford at least one day
        wage = npc.get("hire_wage", 80)
        credits = char.get("credits", 0)
        if credits < wage:
            await ctx.session.send_line(
                f"  Can't afford {npc['name']}'s first day wage of {wage:,} credits. "
                f"You have {credits:,}.")
            return

        # Hire the NPC
        await ctx.db.hire_npc(npc["id"], char_id, wage)
        # Deduct first day's wage immediately
        new_credits = credits - wage
        char["credits"] = new_credits
        await ctx.db.save_character(char_id, credits=new_credits)

        await ctx.session.send_line(
            ansi.success(
                f"  {npc['name']} joins your crew for {wage:,} credits/day."))
        await ctx.session.send_line(
            f"  First day's wage paid. Balance: {new_credits:,} credits.")
        await ctx.session.send_line(
            f"  {ansi.DIM}Use 'assign {npc['name'].split()[0].lower()} <station>' "
            f"to put them to work.{ansi.RESET}")


class RosterCommand(BaseCommand):
    key = "+roster"
    aliases = ["roster"]
    help_text = "View your hired NPC crew and their station assignments."
    usage = "roster"

    async def execute(self, ctx: CommandContext):
        char_id = ctx.session.character["id"]
        hired = await ctx.db.get_npcs_hired_by(char_id)

        if not hired:
            await ctx.session.send_line(
                "  You have no hired crew. Visit a cantina or spaceport and type 'hire'.")
            return

        # Calculate daily wage total
        total_daily = sum(n.get("hire_wage", 0) for n in hired)
        credits = ctx.session.character.get("credits", 0)

        await ctx.session.send_line(
            f"  {ansi.BOLD}=== Your Crew ==={ansi.RESET}")
        await ctx.session.send_line(
            f"  {'Name':20s} {'Role':12s} {'Tier':10s} "
            f"{'Station':12s} {'Wage':>10s}")
        await ctx.session.send_line(f"  {'-' * 68}")

        for npc in hired:
            line = format_roster_entry(npc)
            await ctx.session.send_line(line)

        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  Daily wages: {total_daily:,} cr/day  "
            f"|  Your credits: {credits:,}")
        days_left = credits // total_daily if total_daily > 0 else 999
        if days_left <= 3:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_YELLOW}Warning: funds cover ~{days_left} day(s) "
                f"of wages!{ansi.RESET}")
        await ctx.session.send_line(
            f"\n  {ansi.DIM}assign <name> <station>  |  unassign <name>  "
            f"|  dismiss <name>{ansi.RESET}")


class AssignCrewCommand(BaseCommand):
    key = "assign"
    aliases = []
    help_text = (
        "Assign a hired NPC to a crew station on your current ship. "
        "Stations: pilot, copilot, gunner, engineer, navigator, sensors."
    )
    usage = "assign <name> <station>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or " " not in ctx.args.strip():
            await ctx.session.send_line(
                "Usage: assign <name> <station>\n"
                f"  Stations: {', '.join(sorted(VALID_STATIONS))}")
            return

        # Parse: last word is station, everything before is the name
        parts = ctx.args.strip().rsplit(None, 1)
        name_query = parts[0]
        station_query = parts[1].lower()

        # Validate station
        station = None
        for s in VALID_STATIONS:
            if s == station_query or s.startswith(station_query):
                station = s
                break
        if not station:
            await ctx.session.send_line(
                f"  Unknown station '{station_query}'. "
                f"Options: {', '.join(sorted(VALID_STATIONS))}")
            return

        # Must be aboard a ship
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You must be aboard a ship to assign crew.")
            return

        # Find the NPC in player's hired crew
        char_id = ctx.session.character["id"]
        hired = await ctx.db.get_npcs_hired_by(char_id)
        npc = _match_npc_by_name(hired, name_query)
        if not npc:
            await ctx.session.send_line(
                f"  No one named '{name_query}' in your crew. Type 'roster' to check.")
            return

        # Check if station is already occupied by another NPC
        existing = await ctx.db.get_npc_at_station(ship["id"], station)
        if existing and existing["id"] != npc["id"]:
            await ctx.session.send_line(
                f"  {existing['name']} is already at the {station} station. "
                f"Unassign them first.")
            return

        if npc.get("assigned_station") == station and npc.get("assigned_ship") == ship["id"]:
            await ctx.session.send_line(
                f"  {npc['name']} is already assigned to {station}.")
            return

        # Remove from old station if reassigning
        if npc.get("assigned_ship"):
            old_ship = await ctx.db.get_ship(npc["assigned_ship"])
            if old_ship:
                crew = get_crew_json(old_ship)
                crew = remove_npc_from_all_stations(crew, npc["id"])
                await ctx.db.update_ship(old_ship["id"], crew=json.dumps(crew))

        # Assign in database
        await ctx.db.assign_npc_to_station(npc["id"], ship["id"], station)

        # Update the ship's crew JSON
        crew = get_crew_json(ship)
        crew = set_npc_station(crew, station, npc["id"])
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))

        await ctx.session.send_line(
            ansi.success(
                f"  {npc['name']} takes the {station} station aboard "
                f"the {ship['name']}."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {npc['name']} takes the {station} station.",
            exclude=ctx.session)


class UnassignCrewCommand(BaseCommand):
    key = "unassign"
    aliases = []
    help_text = "Remove an NPC from their crew station. They stay hired but idle."
    usage = "unassign <name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: unassign <name>")
            return

        char_id = ctx.session.character["id"]
        hired = await ctx.db.get_npcs_hired_by(char_id)
        npc = _match_npc_by_name(hired, ctx.args.strip())
        if not npc:
            await ctx.session.send_line(
                f"  No one named '{ctx.args}' in your crew.")
            return

        if not npc.get("assigned_station"):
            await ctx.session.send_line(
                f"  {npc['name']} isn't assigned to any station.")
            return

        old_station = npc["assigned_station"]
        old_ship_id = npc.get("assigned_ship")

        # Remove from crew JSON
        if old_ship_id:
            ship = await ctx.db.get_ship(old_ship_id)
            if ship:
                crew = get_crew_json(ship)
                crew = remove_npc_from_station(crew, old_station, npc["id"])
                await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))

        # Clear assignment in DB
        await ctx.db.unassign_npc(npc["id"])

        await ctx.session.send_line(
            ansi.success(
                f"  {npc['name']} steps away from the {old_station} station. "
                f"(Still hired, {npc.get('hire_wage', 0):,} cr/day)"))


class DismissCrewCommand(BaseCommand):
    key = "dismiss"
    aliases = ["firecrew"]
    help_text = "Dismiss an NPC from your crew. Stops wages, NPC becomes available again."
    usage = "dismiss <name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: dismiss <name>")
            return

        char_id = ctx.session.character["id"]
        hired = await ctx.db.get_npcs_hired_by(char_id)
        npc = _match_npc_by_name(hired, ctx.args.strip())
        if not npc:
            await ctx.session.send_line(
                f"  No one named '{ctx.args}' in your crew.")
            return

        # Remove from ship crew JSON if assigned
        if npc.get("assigned_ship"):
            ship = await ctx.db.get_ship(npc["assigned_ship"])
            if ship:
                crew = get_crew_json(ship)
                crew = remove_npc_from_all_stations(crew, npc["id"])
                await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
                # Announce on bridge
                await ctx.session_mgr.broadcast_to_room(
                    ship["bridge_room_id"],
                    f"  {npc['name']} has been dismissed from the crew.",
                    exclude=ctx.session)

        # Clear hire in DB (NPC stays in world, becomes available)
        await ctx.db.dismiss_npc(npc["id"])

        await ctx.session.send_line(
            ansi.success(
                f"  {npc['name']} has been dismissed. "
                f"Wages stopped. They'll find work elsewhere."))


class OrderCommand(BaseCommand):
    key = "order"
    aliases = ["ord"]
    help_text = (
        "Give a tactical order to NPC crew during space combat. "
        "Overrides their auto-behavior for one round."
    )
    usage = (
        "order <station> <action>\n"
        "  order pilot close <target>    -- close range to target\n"
        "  order pilot flee              -- break off and flee\n"
        "  order pilot tail <target>     -- get behind target\n"
        "  order pilot evade             -- evasive maneuvers\n"
        "  order gunner fire <target>    -- fire at specific target\n"
        "  order engineer repair <system>-- repair a system"
    )

    async def execute(self, ctx: CommandContext):
        if not ctx.args or " " not in ctx.args.strip():
            await ctx.session.send_line(
                "Usage: order <station> <action>\n"
                "  Examples: order pilot tail Interceptor-3\n"
                "            order gunner fire TIE-Alpha\n"
                "            order engineer repair shields")
            return

        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You must be aboard a ship.")
            return

        parts = ctx.args.strip().split(None, 1)
        station_query = parts[0].lower()
        action_str = parts[1] if len(parts) > 1 else ""

        # Match station
        station = None
        for s in VALID_STATIONS:
            if s == station_query or s.startswith(station_query):
                station = s
                break
        if not station:
            await ctx.session.send_line(
                f"  Unknown station '{station_query}'. "
                f"Options: {', '.join(sorted(VALID_STATIONS))}")
            return

        # Check there's an NPC at that station on this ship
        npc = await ctx.db.get_npc_at_station(ship["id"], station)
        if not npc:
            await ctx.session.send_line(
                f"  No NPC crew assigned to {station} on this ship.")
            return

        # Store the order in the crew JSON for the combat tick to pick up
        crew = get_crew_json(ship)
        orders = crew.get("_orders", {})
        orders[station] = {
            "action": action_str,
            "npc_id": npc["id"],
            "npc_name": npc["name"],
        }
        crew["_orders"] = orders
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))

        # Flavor response
        first_name = npc["name"].split()[0]
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[ORDER]{ansi.RESET} "
            f"{first_name} acknowledges: \"{_order_flavor(station, action_str)}\"")


def _order_flavor(station: str, action: str) -> str:
    """Generate a short flavor response for an NPC acknowledging an order."""
    action_lower = action.lower()
    if station == "pilot":
        if "close" in action_lower:
            return "Moving to intercept!"
        if "flee" in action_lower:
            return "Getting us out of here!"
        if "tail" in action_lower:
            return "Going for their six!"
        if "evade" in action_lower:
            return "Evasive action, aye!"
        return f"Copy that -- {action}."
    if station == "gunner":
        if "fire" in action_lower:
            target = action_lower.replace("fire", "").strip()
            return f"Targeting {target}!" if target else "Weapons hot!"
        return f"Understood -- {action}."
    if station == "engineer":
        if "repair" in action_lower:
            system = action_lower.replace("repair", "").strip()
            return f"On it -- rerouting to {system}!" if system else "Starting repairs!"
        return f"Roger -- {action}."
    return f"Acknowledged -- {action}."


# -- Registration --

# S56: Switch & alias dispatch tables for the +crew umbrella.
_CREW_SWITCH_IMPL: dict = {}

_CREW_ALIAS_TO_SWITCH: dict[str, str] = {
    # roster (view your crew)
    "roster":      "roster",
    "mycrew":      "roster",
    "crew":        "roster",
    # hire (visit hireboard / browse hireables)
    "hire":        "hire",
    "recruiting":  "hire",
    "hireboard":   "hire",
    # assign / unassign / dismiss / order
    "assign":      "assign",
    "unassign":    "unassign",
    "dismiss":     "dismiss",
    "firecrew":    "dismiss",
    "order":       "order",
    "ord":         "order",
}


class CrewCommand(BaseCommand):
    """`+crew` umbrella — full S56 dispatch over NPC crew management."""
    key = "+crew"
    aliases: list[str] = [
        "crew", "mycrew", "roster",
        "hire", "recruiting", "hireboard",
        "assign", "unassign",
        "dismiss", "firecrew",
        "order", "ord",
    ]
    help_text = (
        "Crew verbs: '+crew/roster', '+crew/hire <npc>', '+crew/assign "
        "<npc> <station>', '+crew/unassign <npc>', '+crew/dismiss "
        "<npc>', '+crew/order <npc> <directive>'. Bare verbs (hire/"
        "roster/...) still work. Type 'help +crew' for the full reference."
    )
    usage = "+crew[/<switch>] [args]  — see 'help +crew'"
    valid_switches: list[str] = [
        "roster", "hire", "assign", "unassign", "dismiss", "order",
    ]

    async def execute(self, ctx: CommandContext):
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            switch = _CREW_ALIAS_TO_SWITCH.get(
                ctx.command.lower() if ctx.command else "",
                "roster",
            )
        impl_cls = _CREW_SWITCH_IMPL.get(switch)
        if impl_cls is None:
            await ctx.session.send_line(self.help_text)
            return
        await impl_cls().execute(ctx)


def _init_crew_switch_impl():
    _CREW_SWITCH_IMPL["roster"]   = RosterCommand
    _CREW_SWITCH_IMPL["hire"]     = HireCommand
    _CREW_SWITCH_IMPL["assign"]   = AssignCrewCommand
    _CREW_SWITCH_IMPL["unassign"] = UnassignCrewCommand
    _CREW_SWITCH_IMPL["dismiss"]  = DismissCrewCommand
    _CREW_SWITCH_IMPL["order"]    = OrderCommand


_init_crew_switch_impl()


def register_crew_commands(registry):
    """Register NPC crew management commands."""
    cmds = [
        CrewCommand(),
        HireCommand(),
        RosterCommand(),
        AssignCrewCommand(),
        UnassignCrewCommand(),
        DismissCrewCommand(),
        OrderCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
