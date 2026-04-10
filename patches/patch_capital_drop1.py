#!/usr/bin/env python3
"""
Capital Ship Rules — Drop 1: Weapon Stations
Patches parser/space_commands.py with:
  1. _get_crew() migration helper for gunner_stations
  2. GunnerCommand: accepts weapon index arg
  3. FireCommand: weapon selection by station/name/index, skill routing
  4. VacateCommand: handles gunner_stations dict
  5. ShipStatusCommand: numbered weapon display with crew names

Run from project root:
    python patches/patch_capital_drop1.py
"""
import os, sys, shutil, ast

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGET = os.path.join(ROOT, "parser", "space_commands.py")
errors = []


def patch(old, new, label):
    global src
    if old not in src:
        if new in src:
            print(f"  [{label}] Already applied.")
            return
        errors.append(f"[{label}] Anchor not found")
        return
    src = src.replace(old, new, 1)
    print(f"  [{label}] OK")


def main():
    global src
    bak = TARGET + ".bak_capital1"
    if not os.path.exists(bak):
        shutil.copy2(TARGET, bak)
        print(f"  Backup: {os.path.basename(bak)}")

    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    # ═══════════════════════════════════════════════════════════
    #  1. Add gunner_stations migration to _get_crew
    # ═══════════════════════════════════════════════════════════

    patch(
        '''def _get_crew(ship):
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try: return json.loads(crew)
        except Exception: return {}
    return crew or {}''',

        '''def _get_crew(ship):
    crew = ship.get("crew", "{}")
    if isinstance(crew, str):
        try: crew = json.loads(crew)
        except Exception: return {}
    crew = crew or {}
    # Auto-migrate old gunners list → gunner_stations dict
    if "gunners" in crew and "gunner_stations" not in crew:
        stations = {}
        for i, gid in enumerate(crew["gunners"]):
            stations[str(i)] = gid
        crew["gunner_stations"] = stations
        del crew["gunners"]
    return crew''',
        "get_crew_migration"
    )

    # ═══════════════════════════════════════════════════════════
    #  2. GunnerCommand: accept weapon index
    # ═══════════════════════════════════════════════════════════

    patch(
        '''class GunnerCommand(BaseCommand):
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
            f"{weapon.name} ({weapon.damage} damage, {weapon.fire_arc} arc)"))''',

        '''class GunnerCommand(BaseCommand):
    key = "gunner"
    aliases = ["gunnery"]
    help_text = (
        "Take a gunner station. On multi-weapon ships, specify\\n"
        "which weapon station by number or name.\\n"
        "\\n"
        "EXAMPLES:\\n"
        "  gunner          -- take the first open weapon station\\n"
        "  gunner 3        -- take weapon station #3\\n"
        "  gunner turbo    -- take the station matching 'turbo'"
    )
    usage = "gunner [station# | weapon name]"
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
        stations = crew.get("gunner_stations", {})
        # Already stationed?
        for idx_s, gid in stations.items():
            if gid == char_id:
                wname = template.weapons[int(idx_s)].name if int(idx_s) < len(template.weapons) else "?"
                await ctx.session.send_line(
                    f"  You're already at station #{int(idx_s)+1}: {wname}. "
                    f"Type 'vacate' first to switch.")
                return
        # Determine which station to take
        target_idx = None
        if ctx.args:
            arg = ctx.args.strip()
            # Try numeric
            try:
                n = int(arg)
                if 1 <= n <= len(template.weapons):
                    target_idx = n - 1
                else:
                    await ctx.session.send_line(
                        f"  Station #{n} doesn't exist. "
                        f"This ship has {len(template.weapons)} weapon(s).")
                    return
            except ValueError:
                # Try name match
                arg_lower = arg.lower()
                for i, w in enumerate(template.weapons):
                    if arg_lower in w.name.lower():
                        target_idx = i
                        break
                if target_idx is None:
                    await ctx.session.send_line(
                        f"  No weapon matching '{arg}'. Use '+shipstatus' to see weapons.")
                    return
        else:
            # Auto-assign: first unoccupied station
            for i in range(len(template.weapons)):
                if str(i) not in stations:
                    target_idx = i
                    break
            if target_idx is None:
                await ctx.session.send_line("  All weapon stations are occupied.")
                return
        # Check if target station is occupied
        if str(target_idx) in stations:
            occupant_id = stations[str(target_idx)]
            occ = await ctx.db.get_character(occupant_id)
            occ_name = occ["name"] if occ else f"#{occupant_id}"
            await ctx.session.send_line(
                f"  Station #{target_idx+1} is occupied by {occ_name}.")
            return
        # Assign
        stations[str(target_idx)] = char_id
        crew["gunner_stations"] = stations
        await ctx.db.update_ship(ship["id"], crew=json.dumps(crew))
        weapon = template.weapons[target_idx]
        await ctx.session.send_line(ansi.success(
            f"  You man gunner station #{target_idx+1}: "
            f"{weapon.name} ({weapon.damage} damage, {weapon.fire_arc} arc)"))
        await ctx.session_mgr.broadcast_to_room(
            ship["bridge_room_id"],
            f"  {ctx.session.character['name']} takes gunner station "
            f"#{target_idx+1}: {weapon.name}.",
            exclude=ctx.session)''',
        "gunner_command"
    )

    # ═══════════════════════════════════════════════════════════
    #  3. FireCommand: weapon station routing + skill routing
    # ═══════════════════════════════════════════════════════════

    patch(
        '''        crew = _get_crew(ship)
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
        target_name = ctx.args.strip().lower()''',

        '''        crew = _get_crew(ship)
        char_id = ctx.session.character["id"]
        stations = crew.get("gunner_stations", {})
        # Find which station(s) this player occupies
        my_station = None
        for idx_s, gid in stations.items():
            if gid == char_id:
                my_station = int(idx_s)
                break
        if my_station is None:
            await ctx.session.send_line("  You're not at a gunner station. Type 'gunner' first.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        # Parse: "fire <target>" or "fire <target> with <weapon>" or "fire <target> <N>"
        raw_args = ctx.args.strip()
        weapon_override = None
        # Check for "with <weapon>" suffix
        if " with " in raw_args.lower():
            parts = raw_args.lower().rsplit(" with ", 1)
            raw_args = parts[0].strip()
            weapon_search = parts[1].strip()
            # Match by name
            for i, w in enumerate(template.weapons):
                if weapon_search in w.name.lower():
                    weapon_override = i
                    break
            if weapon_override is None:
                await ctx.session.send_line(
                    f"  No weapon matching '{weapon_search}'.")
                return
        # Check for trailing number: "fire target 2"
        elif raw_args and raw_args.split()[-1].isdigit():
            parts = raw_args.rsplit(None, 1)
            if len(parts) == 2:
                n = int(parts[1])
                if 1 <= n <= len(template.weapons):
                    weapon_override = n - 1
                    raw_args = parts[0].strip()
        # Resolve weapon index
        if weapon_override is not None:
            # Verify this player is assigned to that station
            # (or it's their station)
            if weapon_override != my_station:
                # On capital ships, allow firing any unoccupied weapon too
                if str(weapon_override) in stations and stations[str(weapon_override)] != char_id:
                    occ = await ctx.db.get_character(stations[str(weapon_override)])
                    await ctx.session.send_line(
                        f"  Weapon #{weapon_override+1} is manned by "
                        f"{occ['name'] if occ else '?'}. Use your own station.")
                    return
            gunner_idx = weapon_override
        else:
            gunner_idx = my_station
        if gunner_idx >= len(template.weapons):
            await ctx.session.send_line("  Weapon station error.")
            return
        weapon = template.weapons[gunner_idx]
        target_name = raw_args.lower()''',
        "fire_weapon_routing"
    )

    # Fix the hardcoded gunnery skill to read from weapon
    patch(
        '''        gunnery_pool = char_obj.get_skill_pool("starship gunnery", sr)''',

        '''        # Route skill by weapon type
        gunnery_skill = weapon.skill.replace("_", " ") if weapon.skill else "starship gunnery"
        gunnery_pool = char_obj.get_skill_pool(gunnery_skill, sr)''',
        "fire_skill_routing"
    )

    # Also fix target pilot skill for capital ships
    patch(
        '''                target_pilot_pool = tp_char.get_skill_pool("starfighter piloting", sr)''',

        '''                # Route piloting skill by target scale
                tp_pilot_skill = "capital ship piloting" if target_template.scale == "capital" else "starfighter piloting"
                target_pilot_pool = tp_char.get_skill_pool(tp_pilot_skill, sr)''',
        "target_pilot_skill"
    )

    # ═══════════════════════════════════════════════════════════
    #  4. VacateCommand: handle gunner_stations dict
    # ═══════════════════════════════════════════════════════════

    patch(
        '''        # Check gunner list
        if not left:
            gunners = crew.get("gunners", [])
            if char_id in gunners:
                gunners.remove(char_id)
                crew["gunners"] = gunners
                left = "gunner"''',

        '''        # Check gunner stations
        if not left:
            stations = crew.get("gunner_stations", {})
            for idx_s, gid in list(stations.items()):
                if gid == char_id:
                    del stations[idx_s]
                    crew["gunner_stations"] = stations
                    left = f"gunner #{int(idx_s)+1}"
                    break''',
        "vacate_gunner_stations"
    )

    # ═══════════════════════════════════════════════════════════
    #  5. ShipStatusCommand: numbered weapons with crew names
    # ═══════════════════════════════════════════════════════════

    patch(
        '''        for i, gid in enumerate(crew.get("gunners", [])):
            g = await ctx.db.get_character(gid)
            wname = template.weapons[i].name if i < len(template.weapons) else "?"
            await ctx.session.send_line(f"  Gunner #{i+1}: {g['name'] if g else f'#{gid}'} ({wname})")''',

        '''        stations = crew.get("gunner_stations", {})
        if template.weapons:
            await ctx.session.send_line(f"  {ansi.BOLD}Weapons:{ansi.RESET}")
            for i, w in enumerate(template.weapons):
                gid = stations.get(str(i))
                if gid:
                    g = await ctx.db.get_character(gid)
                    crew_str = f"[{g['name'] if g else f'#{gid}'}]"
                else:
                    crew_str = f"{ansi.DIM}[empty]{ansi.RESET}"
                flags = ""
                if w.tractor:
                    flags += f"  {ansi.BRIGHT_YELLOW}TRACTOR{ansi.RESET}"
                if w.ion:
                    flags += f"  {ansi.BRIGHT_BLUE}ION{ansi.RESET}"
                await ctx.session.send_line(
                    f"    {i+1}. {crew_str:14s} {w.name:30s} "
                    f"{w.damage:>5s}  FC:{w.fire_control}  {w.fire_arc}{flags}")''',
        "shipstatus_weapons"
    )

    # ── Write + validate ──
    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    try:
        ast.parse(src)
        print("  AST valid")
    except SyntaxError as e:
        errors.append(f"Syntax error: {e}")

    if errors:
        print("\n  ERRORS:")
        for e in errors:
            print(f"    {e}")
        sys.exit(1)
    else:
        print("\n  Capital Ship Drop 1 (Weapon Stations) applied!")
        print("    - _get_crew() auto-migrates gunners→gunner_stations")
        print("    - gunner [N|name] — pick weapon station")
        print("    - fire <target> [with <weapon>|N] — weapon selection")
        print("    - Gunnery skill routed by weapon.skill field")
        print("    - +shipstatus shows numbered weapon list with crew")


if __name__ == "__main__":
    main()
