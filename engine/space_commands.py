"""
Space commands — ship operations, crew, flight, and combat.

Player commands:
  ships                   - List available ship templates
  shipinfo <n>         - View detailed stats for a ship type
  board <ship>            - Board a docked ship
  disembark               - Leave the ship back to the docking bay
  pilot                   - Take the pilot seat
  gunner                  - Take a gunner seat
  launch                  - Take off (pilot only, must be docked)
  land                    - Dock at a bay (pilot only, must be in space)
  shipstatus / ss         - Show current ship status
  fire <target>           - Fire a weapon (gunner station, in space)
  evade                   - Evasive maneuvers (pilot only)
  damcon <system>         - Damage control: repair a system mid-combat
  scan                    - Scan for nearby ships

Builder commands:
  @spawn <template> <n> - Spawn a ship in the current docking bay
"""
import json
from parser.commands import BaseCommand, CommandContext, AccessLevel
from engine.starships import (
    get_ship_registry, format_ship_status, resolve_space_attack,
    get_space_grid, SpaceRange, RelativePosition, can_weapon_fire,
    ShipInstance, SCALE_STARFIGHTER, SCALE_CAPITAL,
    REPAIRABLE_SYSTEMS, REPAIR_DIFFICULTIES,
    get_system_state, get_repair_skill_name, get_weapon_repair_skill,
    resolve_damage_control,
)
from engine.dice import DicePool
from server import ansi


async def _get_ship_for_player(ctx):
    room_id = ctx.session.character["room_id"]
    return await ctx.db.get_ship_by_bridge(room_id)

def _get_crew(ship):
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try: return json.loads(crew)
        except Exception: return {}
    return crew or {}

def _get_systems(ship):
    systems = ship.get("systems", "{}")
    if isinstance(systems, str):
        try: return json.loads(systems)
        except Exception: return {}
    return systems or {}


class ShipsCommand(BaseCommand):
    key = "ships"
    aliases = ["shiplist"]
    help_text = "List available starship types."
    usage = "ships"
    async def execute(self, ctx):
        reg = get_ship_registry()
        await ctx.session.send_line(
            f"  {ansi.BOLD}{'Ship':30s} {'Scale':12s} {'Speed':>5s} "
            f"{'Hull':>5s} {'Shields':>7s} {'Hyper':>5s}{ansi.RESET}")
        await ctx.session.send_line(f"  {'-'*30} {'-'*12} {'-'*5} {'-'*5} {'-'*7} {'-'*5}")
        for t in sorted(reg.all_templates(), key=lambda x: (x.scale, -x.speed)):
            hyper = f"x{t.hyperdrive}" if t.hyperdrive else "None"
            await ctx.session.send_line(
                f"  {t.name:30s} {t.scale:12s} {t.speed:>5d} "
                f"{t.hull:>5s} {t.shields:>7s} {hyper:>5s}")
        await ctx.session.send_line(f"\n  {ansi.DIM}{reg.count} types. 'shipinfo <n>' for details.{ansi.RESET}")


class ShipInfoCommand(BaseCommand):
    key = "shipinfo"
    aliases = ["si"]
    help_text = "View detailed stats for a ship type."
    usage = "shipinfo <ship name>"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: shipinfo <ship name>")
            return
        reg = get_ship_registry()
        template = reg.find_by_name(ctx.args.strip())
        if not template:
            await ctx.session.send_line(f"  Unknown ship: '{ctx.args}'. Type 'ships'.")
            return
        await ctx.session.send_line(ansi.header(f"=== {template.name} ==="))
        for line in format_ship_status(template):
            await ctx.session.send_line(line)
        await ctx.session.send_line(f"\n  {ansi.DIM}Cost: {template.cost:,} credits{ansi.RESET}\n")


class BoardCommand(BaseCommand):
    key = "board"
    aliases = []
    help_text = "Board a ship docked in this bay."
    usage = "board [ship name]"
    async def execute(self, ctx):
        char = ctx.session.character
        room_id = char["room_id"]
        ships = await ctx.db.get_ships_docked_at(room_id)
        if not ctx.args:
            if not ships:
                await ctx.session.send_line("  No ships docked here.")
                return
            await ctx.session.send_line("  Ships docked here:")
            reg = get_ship_registry()
            for s in ships:
                t = reg.get(s["template"])
                tname = t.name if t else s["template"]
                await ctx.session.send_line(f"    {ansi.BRIGHT_CYAN}{s['name']}{ansi.RESET} ({tname})")
            await ctx.session.send_line("  Usage: board <ship name>")
            return
        search = ctx.args.strip().lower()
        ship = None
        for s in ships:
            if s["name"].lower() == search or s["name"].lower().startswith(search):
                ship = s
                break
        if not ship:
            await ctx.session.send_line(f"  No ship named '{ctx.args}' docked here.")
            return
        bridge_id = ship["bridge_room_id"]
        if not bridge_id:
            await ctx.session.send_line("  That ship has no accessible interior.")
            return
        old_room = char["room_id"]
        char["room_id"] = bridge_id
        await ctx.db.save_character(char["id"], room_id=bridge_id)
        await ctx.session_mgr.broadcast_to_room(
            old_room, f"  {ansi.player_name(char['name'])} boards the {ship['name']}.",
            exclude=ctx.session)
        await ctx.session.send_line(ansi.success(f"  You board the {ship['name']}."))
        from parser.builtin_commands import LookCommand
        look_ctx = CommandContext(session=ctx.session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr)
        await LookCommand().execute(look_ctx)


class DisembarkCommand(BaseCommand):
    key = "disembark"
    aliases = ["deboard"]
    help_text = "Leave the ship, returning to the docking bay."
    usage = "disembark"
    async def execute(self, ctx):
        char = ctx.session.character
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship["docked_at"]:
            await ctx.session.send_line("  The ship is in space! You can't disembark.")
            return
        crew = _get_crew(ship)
        char_id = char["id"]
        changed = False
        if crew.get("pilot") == char_id:
            crew["pilot"] = None
            changed = True
        gunners = crew.get("gunners", [])
        if char_id in gunners:
            gunners.remove(char_id)
            changed = True
        if changed:
            await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        char["room_id"] = ship["docked_at"]
        await ctx.db.save_character(char["id"], room_id=ship["docked_at"])
        await ctx.session.send_line(ansi.success(f"  You disembark from the {ship['name']}."))
        from parser.builtin_commands import LookCommand
        look_ctx = CommandContext(session=ctx.session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr)
        await LookCommand().execute(look_ctx)


class PilotCommand(BaseCommand):
    key = "pilot"
    aliases = []
    help_text = "Take the pilot seat."
    usage = "pilot"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        if crew.get("pilot") == char_id:
            await ctx.session.send_line("  You're already the pilot.")
            return
        if crew.get("pilot"):
            await ctx.session.send_line("  The pilot seat is occupied.")
            return
        crew["pilot"] = char_id
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        await ctx.session.send_line(ansi.success("  You take the pilot seat. Controls are live."))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes the pilot seat.",
            exclude=ctx.session)


class GunnerCommand(BaseCommand):
    key = "gunner"
    aliases = []
    help_text = "Take a gunner station."
    usage = "gunner"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template or not template.weapons:
            await ctx.session.send_line("  This ship has no weapon stations.")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        gunners = crew.get("gunners", [])
        if char_id in gunners:
            await ctx.session.send_line("  You're already at a gunner station.")
            return
        if len(gunners) >= len(template.weapons):
            await ctx.session.send_line("  All gunner stations are occupied.")
            return
        gunners.append(char_id)
        crew["gunners"] = gunners
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        weapon = template.weapons[len(gunners) - 1]
        await ctx.session.send_line(ansi.success(
            f"  You man gunner station #{len(gunners)}: "
            f"{weapon.name} ({weapon.damage} damage, {weapon.fire_arc} arc)"))



class LaunchCommand(BaseCommand):
    key = "launch"
    aliases = ["takeoff"]
    help_text = "Launch from docking bay (pilot only). Costs fuel credits."
    usage = "launch"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship["docked_at"]:
            await ctx.session.send_line("  Already in space!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can launch. Type 'pilot' first.")
            return
        systems = _get_systems(ship)
        if not systems.get("engines", True):
            await ctx.session.send_line("  Engines are damaged! Cannot launch.")
            return
        # Fuel cost: 50cr base, scaled by ship speed
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        speed = template.speed if template else 5
        fuel_cost = 50 + (speed * 10)
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < fuel_cost:
            await ctx.session.send_line(
                f"  Not enough credits for fuel! Need {fuel_cost:,}cr, have {credits:,}cr.")
            return
        char["credits"] = credits - fuel_cost
        await ctx.db.save_character(char["id"], credits=char["credits"])
        bay_id = ship["docked_at"]
        bay = await ctx.db.get_room(bay_id)
        bay_name = bay["name"] if bay else "the docking bay"
        await ctx.db.update_ship(ship["id"], docked_at=None)
        get_space_grid().add_ship(ship["id"], speed)
        await ctx.session_mgr.broadcast_to_room(
            bay_id, f"  The {ship['name']} lifts off with a roar of engines!")
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            ansi.success(
                f"  {ship['name']} launches from {bay_name}! "
                f"(Fuel: {fuel_cost:,}cr) You are now in space."))


class LandCommand(BaseCommand):
    key = "land"
    aliases = ["dock"]
    help_text = "Land at a docking bay (pilot only). Docking fee applies."
    usage = "land"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Already docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can land.")
            return
        rooms = await ctx.db.find_rooms("Docking Bay")
        if not rooms:
            await ctx.session.send_line("  No docking bays found!")
            return
        bay = rooms[0]
        # Docking fee: 25cr (per R&E GG7)
        docking_fee = 25
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < docking_fee:
            await ctx.session.send_line(
                f"  Not enough credits for docking fee! Need {docking_fee}cr.")
            return
        char["credits"] = credits - docking_fee
        await ctx.db.save_character(char["id"], credits=char["credits"])
        await ctx.db.update_ship(ship["id"], docked_at=bay["id"])
        get_space_grid().remove_ship(ship["id"])
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            ansi.success(
                f"  {ship['name']} docks at {bay['name']}. "
                f"(Docking fee: {docking_fee}cr)"))
        await ctx.session_mgr.broadcast_to_room(
            bay["id"], f"  The {ship['name']} settles onto the landing pad.")


class ShipStatusCommand(BaseCommand):
    key = "shipstatus"
    aliases = ["ss"]
    help_text = "Show status of your ship including tactical positioning."
    usage = "shipstatus"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        instance = ShipInstance(
            id=ship["id"], template_key=ship["template"],
            name=ship["name"], hull_damage=ship.get("hull_damage", 0))
        systems = _get_systems(ship)
        instance.systems_damaged = [k for k, v in systems.items() if not v]
        await ctx.session.send_line(ansi.header(f"=== {ship['name']} ==="))
        for line in format_ship_status(template, instance):
            await ctx.session.send_line(line)
        crew = _get_crew(ship)
        await ctx.session.send_line("")
        pilot_id = crew.get("pilot")
        if pilot_id:
            pilot = await ctx.db.get_character(pilot_id)
            await ctx.session.send_line(f"  Pilot: {pilot['name'] if pilot else f'#{pilot_id}'}")
        else:
            await ctx.session.send_line(f"  Pilot: (empty)")
        for i, gid in enumerate(crew.get("gunners", [])):
            g = await ctx.db.get_character(gid)
            wname = template.weapons[i].name if i < len(template.weapons) else "?"
            await ctx.session.send_line(f"  Gunner #{i+1}: {g['name'] if g else f'#{gid}'} ({wname})")
        if ship["docked_at"]:
            bay = await ctx.db.get_room(ship["docked_at"])
            await ctx.session.send_line(f"\n  Location: Docked at {bay['name'] if bay else '?'}")
        else:
            await ctx.session.send_line(f"\n  Location: In space")
            grid = get_space_grid()
            tac = grid.format_tactical(ship["id"])
            if tac:
                await ctx.session.send_line(f"  {ansi.BRIGHT_CYAN}Tactical:{ansi.RESET}")
                for line in tac:
                    await ctx.session.send_line(line)
        await ctx.session.send_line("")


class ScanCommand(BaseCommand):
    key = "scan"
    aliases = []
    help_text = "Scan for nearby ships — shows range and position."
    usage = "scan"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Scanners work in space. Launch first.")
            return
        reg = get_ship_registry()
        grid = get_space_grid()
        others = [s for s in await ctx.db.get_ships_in_space() if s["id"] != ship["id"]]
        await ctx.session.send_line(f"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}")
        if not others:
            await ctx.session.send_line("  No other ships detected.")
        else:
            for s in others:
                t = reg.get(s["template"])
                tname = t.name if t else s["template"]
                rng = grid.get_range(ship["id"], s["id"])
                pos = grid.get_position(ship["id"], s["id"])
                dmg = s.get("hull_damage", 0)
                status = "Active" if dmg == 0 else f"Damaged ({dmg} hits)"
                await ctx.session.send_line(
                    f"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})")
                await ctx.session.send_line(
                    f"    Range: {rng.label}  Position: {pos}  Status: {status}")
        await ctx.session.send_line("")


class FireCommand(BaseCommand):
    key = "fire"
    aliases = []
    help_text = "Fire your weapon at a target (gunner station, in space). Checks range and fire arc."
    usage = "fire <target ship name>"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: fire <target ship name>")
            return
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't fire while docked!")
            return
        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        gunners = crew.get("gunners", [])
        if char_id not in gunners:
            await ctx.session.send_line("  You're not at a gunner station. Type 'gunner' first.")
            return
        gunner_idx = gunners.index(char_id)
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template or gunner_idx >= len(template.weapons):
            await ctx.session.send_line("  Weapon station error.")
            return
        weapon = template.weapons[gunner_idx]
        target_name = ctx.args.strip().lower()
        target_ship = None
        for s in await ctx.db.get_ships_in_space():
            if s["id"] != ship["id"] and (
                s["name"].lower() == target_name or s["name"].lower().startswith(target_name)):
                target_ship = s
                break
        if not target_ship:
            await ctx.session.send_line(f"  No ship '{ctx.args}' on scanners.")
            return
        target_template = reg.get(target_ship["template"])
        if not target_template:
            await ctx.session.send_line("  Target data error.")
            return
        # Get range and position from grid
        grid = get_space_grid()
        rng = grid.get_range(ship["id"], target_ship["id"])
        rel_pos = grid.get_position(ship["id"], target_ship["id"])
        # Arc check before rolling
        if not can_weapon_fire(weapon.fire_arc, rel_pos):
            await ctx.session.send_line(
                f"  {weapon.name} cannot fire at targets to your {rel_pos}! "
                f"(Weapon arc: {weapon.fire_arc})")
            return
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        gunnery_pool = char_obj.get_skill_pool("starship gunnery", sr)
        target_crew = _get_crew(target_ship)
        target_pilot_pool = DicePool(2, 0)
        if target_crew.get("pilot"):
            tp = await ctx.db.get_character(target_crew["pilot"])
            if tp:
                tp_char = Character.from_db_dict(tp)
                target_pilot_pool = tp_char.get_skill_pool("starfighter piloting", sr)
        result = resolve_space_attack(
            attacker_skill=gunnery_pool, weapon=weapon,
            attacker_scale=template.scale_value,
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(target_template.maneuverability),
            target_hull=DicePool.parse(target_template.hull),
            target_shields=DicePool.parse(target_template.shields),
            target_scale=target_template.scale_value,
            range_band=rng,
            relative_position=rel_pos)
        if result.hull_damage > 0:
            new_dmg = target_ship.get("hull_damage", 0) + result.hull_damage
            updates = {"hull_damage": new_dmg}
            if result.systems_hit:
                systems = _get_systems(target_ship)
                for s in result.systems_hit:
                    systems[s] = False
                updates["systems"] = json.dumps(systems)
            await ctx.db.update_ship(target_ship["id"], **updates)
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_RED}[WEAPONS]{ansi.RESET} "
            f"{ctx.session.character['name']} fires {weapon.name} at {target_ship['name']}! "
            f"{result.narrative.strip()}")
        if target_ship.get("bridge_room_id"):
            if result.hit:
                await ctx.session_mgr.broadcast_to_room(target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_RED}[ALERT]{ansi.RESET} "
                    f"Hit by {weapon.name} from {ship['name']}! {result.narrative.strip()}")
            else:
                await ctx.session_mgr.broadcast_to_room(target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"Incoming fire from {ship['name']} — missed!")


class CloseRangeCommand(BaseCommand):
    key = "close"
    aliases = ["approach"]
    help_text = "Close range to a target (pilot only). Opposed piloting roll, speed advantage matters."
    usage = "close <target ship>"
    async def execute(self, ctx):
        await self._maneuver(ctx, "close")

    async def _maneuver(self, ctx, action):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  You're docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can maneuver.")
            return
        if not ctx.args:
            await ctx.session.send_line(f"  Usage: {action} <target ship>")
            return
        target_name = ctx.args.strip().lower()
        target_ship = None
        for s in await ctx.db.get_ships_in_space():
            if s["id"] != ship["id"] and (
                s["name"].lower() == target_name or s["name"].lower().startswith(target_name)):
                target_ship = s
                break
        if not target_ship:
            await ctx.session.send_line(f"  No ship '{ctx.args}' on scanners.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        target_template = reg.get(target_ship["template"])
        if not template or not target_template:
            await ctx.session.send_line("  Ship data error.")
            return
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        pilot_pool = char_obj.get_skill_pool("starfighter piloting", sr)
        target_crew = _get_crew(target_ship)
        target_pilot_pool = DicePool(2, 0)
        if target_crew.get("pilot"):
            tp = await ctx.db.get_character(target_crew["pilot"])
            if tp:
                tp_char = Character.from_db_dict(tp)
                target_pilot_pool = tp_char.get_skill_pool("starfighter piloting", sr)
        grid = get_space_grid()
        success, narrative = grid.resolve_maneuver(
            pilot_id=ship["id"],
            pilot_skill=pilot_pool,
            pilot_maneuverability=DicePool.parse(template.maneuverability),
            pilot_speed=template.speed,
            target_id=target_ship["id"],
            target_pilot_skill=target_pilot_pool,
            target_maneuverability=DicePool.parse(target_template.maneuverability),
            target_speed=target_template.speed,
            action=action)
        color = ansi.BRIGHT_GREEN if success else ansi.BRIGHT_YELLOW
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {color}[HELM]{ansi.RESET} {narrative}")
        if target_ship.get("bridge_room_id"):
            if success:
                await ctx.session_mgr.broadcast_to_room(target_ship["bridge_room_id"],
                    f"  {ansi.BRIGHT_YELLOW}[SENSORS]{ansi.RESET} "
                    f"{ship['name']} is maneuvering! {narrative}")


class FleeShipCommand(BaseCommand):
    key = "fleeship"
    aliases = ["breakaway"]
    help_text = "Increase range from a target (pilot only). Speed advantage matters."
    usage = "fleeship <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "flee")


class TailCommand(BaseCommand):
    key = "tail"
    aliases = ["getbehind"]
    help_text = "Get behind a target ship (pilot only). Puts you in their rear arc."
    usage = "tail <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "tail")


class OutmaneuverCommand(BaseCommand):
    key = "outmaneuver"
    aliases = ["shake"]
    help_text = "Shake a pursuer off your tail (pilot only). Resets to head-on engagement."
    usage = "outmaneuver <target ship>"
    async def execute(self, ctx):
        cmd = CloseRangeCommand()
        await cmd._maneuver(ctx, "outmaneuver")


class EvadeCommand(BaseCommand):
    key = "evade"
    aliases = ["evasive"]
    help_text = "Evasive maneuvers — broadcast to crew (pilot only)."
    usage = "evade"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Can't evade while docked!")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can evade.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        maneuver = template.maneuverability if template else "1D"
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_YELLOW}[HELM]{ansi.RESET} "
            f"{ctx.session.character['name']} throws the ship into evasive maneuvers! "
            f"(Maneuverability: {maneuver})")


class SpawnShipCommand(BaseCommand):
    key = "@spawn"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Spawn a ship in the current room (docking bay)."
    usage = "@spawn <template> <ship name>"
    async def execute(self, ctx):
        if not ctx.args or " " not in ctx.args:
            await ctx.session.send_line("Usage: @spawn <template> <ship name>")
            await ctx.session.send_line("  @spawn yt_1300 Millennium Falcon")
            await ctx.session.send_line("  @spawn x_wing Red Five")
            return
        parts = ctx.args.split(None, 1)
        template_key = parts[0].lower()
        ship_name = parts[1].strip()
        reg = get_ship_registry()
        template = reg.get(template_key) or reg.find_by_name(template_key)
        if not template:
            await ctx.session.send_line(f"  Unknown template: '{template_key}'. Type 'ships'.")
            return
        char = ctx.session.character
        room_id = char["room_id"]
        crew_note = f"A co-pilot station sits to the right. " if template.crew > 1 else ""
        gun_note = f"Gunner stations are visible along the walls. " if len(template.weapons) > 1 else ""
        bridge_id = await ctx.db.create_room(
            f"{ship_name} - Bridge",
            f"The bridge of the {ship_name}.",
            f"The cockpit of this {template.name} hums with instruments. "
            f"The pilot's seat faces a wide transparisteel viewport. "
            f"{crew_note}{gun_note}"
            f"The air recyclers hum steadily.")
        ship_id = await ctx.db.create_ship(
            template=template.key, name=ship_name, owner_id=char["id"],
            bridge_room_id=bridge_id, docked_at=room_id)
        await ctx.session.send_line(ansi.success(
            f"  {ship_name} ({template.name}) spawned as ship #{ship_id}, "
            f"docked here. Bridge: #{bridge_id}."))
        await ctx.session_mgr.broadcast_to_room(room_id,
            f"  The {ship_name} settles onto the landing pad.",
            exclude=ctx.session)


class ShieldsCommand(BaseCommand):
    key = "shields"
    aliases = []
    help_text = "Redistribute shield dice between front and rear arcs."
    usage = "shields <front> <rear>  (e.g. 'shields 2 0' puts all dice forward)"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        shield_pool = DicePool.parse(template.shields)
        total_dice = shield_pool.dice
        if total_dice <= 0:
            await ctx.session.send_line("  This ship has no shields to redistribute.")
            return
        if not ctx.args:
            systems = _get_systems(ship)
            front = systems.get("shield_front", total_dice // 2 + total_dice % 2)
            rear = systems.get("shield_rear", total_dice // 2)
            await ctx.session.send_line(
                f"  Shield dice: {total_dice}D total  "
                f"(Front: {front}D, Rear: {rear}D)")
            await ctx.session.send_line(
                f"  Usage: shields <front> <rear>  (must sum to {total_dice})")
            return
        parts = ctx.args.split()
        if len(parts) < 2:
            await ctx.session.send_line(f"  Usage: shields <front> <rear>  (must sum to {total_dice})")
            return
        try:
            front = int(parts[0])
            rear = int(parts[1])
        except ValueError:
            await ctx.session.send_line("  Shield values must be numbers.")
            return
        if front + rear != total_dice:
            await ctx.session.send_line(
                f"  Front + Rear must equal {total_dice}D. You gave {front}+{rear}={front+rear}.")
            return
        if front < 0 or rear < 0:
            await ctx.session.send_line("  Shield values can't be negative.")
            return
        systems = _get_systems(ship)
        systems["shield_front"] = front
        systems["shield_rear"] = rear
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[SHIELDS]{ansi.RESET} "
            f"Shields redistributed: Front {front}D, Rear {rear}D.")


# ── Hyperspace Locations ──
HYPERSPACE_LOCATIONS = {
    "tatooine": {"name": "Tatooine", "coords": (43, 198)},
    "alderaan": {"name": "Alderaan", "coords": (34, 205)},
    "coruscant": {"name": "Coruscant", "coords": (0, 0)},
    "yavin": {"name": "Yavin IV", "coords": (325, 50)},
    "hoth": {"name": "Hoth", "coords": (295, 160)},
    "bespin": {"name": "Bespin", "coords": (296, 248)},
    "endor": {"name": "Endor", "coords": (260, 335)},
    "kessel": {"name": "Kessel", "coords": (253, 295)},
    "corellia": {"name": "Corellia", "coords": (326, 185)},
    "kashyyyk": {"name": "Kashyyyk", "coords": (260, 175)},
    "naboo": {"name": "Naboo", "coords": (283, 320)},
    "dagobah": {"name": "Dagobah", "coords": (295, 215)},
}


class HyperspaceCommand(BaseCommand):
    key = "hyperspace"
    aliases = ["jump", "hyper"]
    help_text = "Jump to hyperspace (pilot only). Requires hyperdrive and astrogation roll."
    usage = "hyperspace <destination>  |  hyperspace list"
    async def execute(self, ctx):
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship["docked_at"]:
            await ctx.session.send_line("  Must be in space to jump. Launch first.")
            return
        crew = _get_crew(ship)
        if crew.get("pilot") != ctx.session.character["id"]:
            await ctx.session.send_line("  Only the pilot can initiate hyperspace.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template or not template.hyperdrive:
            await ctx.session.send_line("  This ship has no hyperdrive!")
            return
        systems = _get_systems(ship)
        if not systems.get("hyperdrive", True):
            await ctx.session.send_line("  Hyperdrive is damaged! Cannot jump.")
            return
        if not ctx.args or ctx.args.strip().lower() == "list":
            await ctx.session.send_line(f"  {ansi.BOLD}Hyperspace Destinations:{ansi.RESET}")
            for key, loc in sorted(HYPERSPACE_LOCATIONS.items()):
                await ctx.session.send_line(f"    {loc['name']}")
            await ctx.session.send_line(f"\n  Usage: hyperspace <destination>")
            return
        dest_key = ctx.args.strip().lower()
        dest = HYPERSPACE_LOCATIONS.get(dest_key)
        if not dest:
            for k, v in HYPERSPACE_LOCATIONS.items():
                if v["name"].lower().startswith(dest_key) or k.startswith(dest_key):
                    dest = v
                    dest_key = k
                    break
        if not dest:
            await ctx.session.send_line(f"  Unknown destination: '{ctx.args}'. Type 'hyperspace list'.")
            return
        # Fuel cost: 100cr per jump (x2 for backup hyperdrive)
        hdrive = template.hyperdrive if template else 1
        fuel_cost = 100 * hdrive
        char = ctx.session.character
        credits = char.get("credits", 0)
        if credits < fuel_cost:
            await ctx.session.send_line(
                f"  Not enough credits for hyperspace fuel! "
                f"Need {fuel_cost:,}cr, have {credits:,}cr.")
            return
        # Astrogation roll
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")
        from engine.dice import roll_d6_pool, DicePool as DP
        astro_pool = char_obj.get_skill_pool("astrogation", sr)
        roll = roll_d6_pool(astro_pool)
        difficulty = 10  # Easy for known routes
        if roll.total < difficulty:
            await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
                f"  {ansi.BRIGHT_RED}[NAV]{ansi.RESET} Astrogation calculation failed! "
                f"(Roll: {roll.total} vs {difficulty}) "
                f"Cannot make the jump safely. (Fuel not consumed.)")
            return
        # Charge fuel
        char["credits"] = credits - fuel_cost
        await ctx.db.save_character(char["id"], credits=char["credits"])
        # Remove from space grid
        get_space_grid().remove_ship(ship["id"])
        # Store location on ship
        systems["location"] = dest_key
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))
        await ctx.session_mgr.broadcast_to_room(ship["bridge_room_id"],
            f"  {ansi.BRIGHT_CYAN}[HYPERSPACE]{ansi.RESET} "
            f"Astrogation plotted. (Roll: {roll.total} vs {difficulty})\n"
            f"  Stars stretch into lines as the {ship['name']} jumps to lightspeed!\n"
            f"  ...\n"
            f"  Arriving at {dest['name']}. Reverting to realspace.")
        # Re-add to grid at new location
        speed = template.speed if template else 5
        get_space_grid().add_ship(ship["id"], speed)


class BuyCommand(BaseCommand):
    key = "buy"
    aliases = ["purchase"]
    help_text = "Buy a weapon or item from a shop."
    usage = "buy <weapon name>"
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: buy <weapon name>")
            await ctx.session.send_line("  Type 'weapons' to see available weapons and prices.")
            return
        from engine.weapons import get_weapon_registry
        from engine.items import ItemInstance, serialize_equipment
        wr = get_weapon_registry()
        weapon = wr.find_by_name(ctx.args.strip())
        if not weapon:
            await ctx.session.send_line(f"  Unknown item: '{ctx.args}'. Type 'weapons' to see the list.")
            return
        if weapon.is_armor:
            await ctx.session.send_line("  Armor purchases coming soon.")
            return
        price = weapon.cost
        if price <= 0:
            price = 500
        char = ctx.session.character
        current_credits = char.get("credits", 1000)
        if current_credits < price:
            await ctx.session.send_line(
                f"  Not enough credits! {weapon.name} costs {price:,} credits, "
                f"you have {current_credits:,}.")
            return
        new_credits = current_credits - price
        item = ItemInstance.new_from_vendor(weapon.key)
        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], credits=new_credits, equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(
                f"  Purchased and equipped {weapon.name} for {price:,} credits. "
                f"({new_credits:,} remaining)")
        )
        await ctx.session.send_line(f"  Condition: {item.condition_bar}")


class DamConCommand(BaseCommand):
    key = "damcon"
    aliases = ["damagecontrol", "repair"]
    help_text = (
        "Attempt to repair a damaged ship system mid-combat. "
        "Uses Technical + repair skill. Systems: "
        "shields, sensors, engines, weapons, hyperdrive, hull."
    )
    usage = "damcon <system>"

    async def execute(self, ctx):
        # ── Validate: aboard a ship ──
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return

        systems = _get_systems(ship)

        # ── No argument: show damage report ──
        if not ctx.args:
            damaged = []
            for sys_name in REPAIRABLE_SYSTEMS:
                state = get_system_state(systems, sys_name)
                if state == "damaged":
                    diff = REPAIR_DIFFICULTIES[sys_name]
                    damaged.append(
                        f"    {ansi.BRIGHT_YELLOW}{sys_name:12s}{ansi.RESET} "
                        f"DAMAGED  (Difficulty: {diff})"
                    )
                elif state == "destroyed":
                    damaged.append(
                        f"    {ansi.BRIGHT_RED}{sys_name:12s}{ansi.RESET} "
                        f"DESTROYED — needs spacedock"
                    )
            hull_dmg = ship.get("hull_damage", 0)
            if hull_dmg > 0:
                diff = REPAIR_DIFFICULTIES["hull"]
                damaged.append(
                    f"    {ansi.BRIGHT_YELLOW}{'hull':12s}{ansi.RESET} "
                    f"{hull_dmg} damage  (Difficulty: {diff})"
                )
            if not damaged:
                await ctx.session.send_line(
                    "  All systems operational. Nothing to repair."
                )
            else:
                await ctx.session.send_line(
                    f"  {ansi.BOLD}Damage Report:{ansi.RESET}"
                )
                for line in damaged:
                    await ctx.session.send_line(line)
                await ctx.session.send_line(
                    f"\n  {ansi.DIM}Usage: damcon <system> to attempt repair{ansi.RESET}"
                )
            return

        # ── Parse system name ──
        target_sys = ctx.args.strip().lower()
        # Allow partial matching
        matched = None
        for sys_name in REPAIRABLE_SYSTEMS:
            if sys_name == target_sys or sys_name.startswith(target_sys):
                matched = sys_name
                break
        if not matched:
            await ctx.session.send_line(
                f"  Unknown system '{ctx.args}'. "
                f"Options: {', '.join(REPAIRABLE_SYSTEMS)}"
            )
            return

        # ── Check system state ──
        if matched == "hull":
            hull_dmg = ship.get("hull_damage", 0)
            if hull_dmg <= 0:
                await ctx.session.send_line("  Hull integrity is fine.")
                return
            current_state = "damaged"
        else:
            current_state = get_system_state(systems, matched)

        if current_state == "working":
            await ctx.session.send_line(
                f"  {matched.title()} are already operational!"
            )
            return

        if current_state == "destroyed":
            await ctx.session.send_line(
                f"  {matched.title()} are damaged beyond repair. "
                f"You'll need a spacedock for this."
            )
            return

        # ── Look up repair skill ──
        from engine.character import Character, SkillRegistry
        char_obj = Character.from_db_dict(ctx.session.character)
        sr = SkillRegistry()
        sr.load_file("data/skills.yaml")

        if matched == "weapons":
            skill_name = get_weapon_repair_skill()
        else:
            skill_name = get_repair_skill_name(template.scale)

        repair_pool = char_obj.get_skill_pool(
            skill_name.replace("_", " "), sr
        )

        # Check if in combat (other ships in space nearby)
        in_combat = not ship["docked_at"]

        # ── Resolve the repair ──
        result = resolve_damage_control(
            repair_skill=repair_pool,
            system_name=matched,
            current_state=current_state,
            ship_scale=template.scale,
            in_combat=in_combat,
            num_actions=1,
        )

        # ── Apply results to database ──
        if result.success:
            if matched == "hull":
                new_dmg = max(0, ship.get("hull_damage", 0) - result.hull_repaired)
                await ctx.db.update_ship(ship["id"], hull_damage=new_dmg)
            else:
                systems[matched] = True
                await ctx.db.update_ship(
                    ship["id"], systems=json.dumps(systems)
                )
        elif result.permanent_failure:
            systems[matched] = "destroyed"
            await ctx.db.update_ship(
                ship["id"], systems=json.dumps(systems)
            )

        # ── Broadcast result ──
        if result.success:
            color = ansi.BRIGHT_GREEN
            tag = "REPAIR"
        elif result.permanent_failure:
            color = ansi.BRIGHT_RED
            tag = "REPAIR CRITICAL"
        else:
            color = ansi.BRIGHT_YELLOW
            tag = "REPAIR"

        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {color}[{tag}]{ansi.RESET} "
            f"{ctx.session.character['name']} works on {matched}: "
            f"{result.narrative.strip()}"
        )


class CreditsCommand(BaseCommand):
    key = "credits"
    aliases = ["balance", "wallet"]
    help_text = "Check your credit balance."
    usage = "credits"
    async def execute(self, ctx):
        credits = ctx.session.character.get("credits", 1000)
        await ctx.session.send_line(f"  Credits: {credits:,}")


def register_space_commands(registry):
    cmds = [
        ShipsCommand(), ShipInfoCommand(),
        BoardCommand(), DisembarkCommand(),
        PilotCommand(), GunnerCommand(),
        LaunchCommand(), LandCommand(),
        ShipStatusCommand(), ScanCommand(),
        FireCommand(), EvadeCommand(),
        CloseRangeCommand(), FleeShipCommand(),
        TailCommand(), OutmaneuverCommand(),
        ShieldsCommand(), HyperspaceCommand(),
        BuyCommand(), CreditsCommand(),
        DamConCommand(),
        SpawnShipCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
