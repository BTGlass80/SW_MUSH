#!/usr/bin/env python3
"""
patches/patch_scan_astro_skill.py  --  Sensors + Astrogation skill integration.

Patches parser/space_commands.py:

  1. ScanCommand  -- Sensors skill check gates info depth:
       Fumble    -> "Sensors offline" — sees nothing (contacts hidden)
       Failure   -> Basic read: ship name + range only
       Success   -> Standard read: name, type, range, position, status
       Critical  -> Deep scan: all of above + hull %, cargo flag for NPC smugglers
     Sensors station operator gets +2D bonus to the check.
     Difficulty: 8 (Easy — space is big and signals are loud)

  2. HyperspaceCommand  -- Route through perform_skill_check:
       Fumble    -> Misjump! Ship jumps to a random zone, hazard table fires.
       Failure   -> Calculation failed, no jump, no fuel charge (existing behaviour)
       Success   -> Normal jump, full fuel charge
       Critical  -> Clean jump, fuel cost halved
     Difficulty: 10 (Easy for known Outer Rim routes — unchanged)
     Navigator at sensors station (crew["sensors"]) grants +1D.

Run from project root:
    python patches/patch_scan_astro_skill.py
"""

import sys
import shutil
import ast
from pathlib import Path

TARGET = Path("parser/space_commands.py")
BACKUP = Path("parser/space_commands.py.bak_scan_astro")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write(p: Path, text: str) -> None:
    p.write_text(text, encoding="utf-8")


def apply(src: str, old: str, new: str, label: str) -> str:
    if old in src:
        return src.replace(old, new, 1)
    old_lf = old.replace("\r\n", "\n")
    src_lf = src.replace("\r\n", "\n")
    if old_lf in src_lf:
        return src_lf.replace(old_lf, new, 1)
    print(f"ERROR: anchor not found for: {label}")
    print(f"  First 120 chars: {repr(old[:120])}")
    sys.exit(1)


def main():
    if not TARGET.exists():
        print(f"ERROR: {TARGET} not found. Run from project root.")
        sys.exit(1)

    shutil.copy(TARGET, BACKUP)
    print(f"Backup: {BACKUP}")

    src = read(TARGET)

    # ══════════════════════════════════════════════════════════════════════════
    # PATCH 1 — ScanCommand: add Sensors skill check, tiered info depth
    # ══════════════════════════════════════════════════════════════════════════

    old_scan = (
        "    async def execute(self, ctx):\n"
        "        ship = await _get_ship_for_player(ctx)\n"
        "        if not ship:\n"
        "            await ctx.session.send_line(\"  You're not aboard a ship.\")\n"
        "            return\n"
        "        if ship[\"docked_at\"]:\n"
        "            await ctx.session.send_line(\"  Scanners work in space. Launch first.\")\n"
        "            return\n"
        "        systems = _get_systems(ship)\n"
        "        player_zone = systems.get(\"current_zone\", \"\")\n"
        "        reg = get_ship_registry()\n"
        "        grid = get_space_grid()\n"
        "        others = [s for s in await ctx.db.get_ships_in_space() if s[\"id\"] != ship[\"id\"]]\n"
        "        await ctx.session.send_line(f\"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}\")\n"
        "        if player_zone:\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.DIM}Zone: {player_zone}{ansi.RESET}\")\n"
        "        any_contacts = False\n"
        "        for s in others:\n"
        "            t = reg.get(s[\"template\"])\n"
        "            tname = t.name if t else s[\"template\"]\n"
        "            rng = grid.get_range(ship[\"id\"], s[\"id\"])\n"
        "            pos = grid.get_position(ship[\"id\"], s[\"id\"])\n"
        "            dmg = s.get(\"hull_damage\", 0)\n"
        "            status = \"Active\" if dmg == 0 else f\"Damaged ({dmg} hits)\"\n"
        "            await ctx.session.send_line(\n"
        "                f\"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})\")\n"
        "            await ctx.session.send_line(\n"
        "                f\"    Range: {rng.label}  Position: {pos}  Status: {status}\")\n"
        "            any_contacts = True\n"
        "        # ── NPC Traffic ships in same zone ────────────────────────────────────\n"
        "        if player_zone:\n"
        "            traffic_ships = get_traffic_manager().get_zone_ships(player_zone)\n"
        "            for ts in traffic_ships:\n"
        "                await ctx.session.send_line(\n"
        "                    f\"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} \"\n"
        "                    f\"[NPC {ts.archetype.value.title()}]\")\n"
        "                await ctx.session.send_line(\n"
        "                    f\"    Zone: {player_zone}  Transponder: {ts.transponder_type}\"\n"
        "                    f\"  Captain: {ts.captain_name}\")\n"
        "                any_contacts = True\n"
        "        if not any_contacts:\n"
        "            await ctx.session.send_line(\"  No other ships detected.\")\n"
        "        await ctx.session.send_line(\"\")"
    )

    new_scan = (
        "    async def execute(self, ctx):\n"
        "        ship = await _get_ship_for_player(ctx)\n"
        "        if not ship:\n"
        "            await ctx.session.send_line(\"  You're not aboard a ship.\")\n"
        "            return\n"
        "        if ship[\"docked_at\"]:\n"
        "            await ctx.session.send_line(\"  Scanners work in space. Launch first.\")\n"
        "            return\n"
        "        systems = _get_systems(ship)\n"
        "        player_zone = systems.get(\"current_zone\", \"\")\n"
        "        reg = get_ship_registry()\n"
        "        grid = get_space_grid()\n"
        "        char = ctx.session.character\n"
        "        crew = _get_crew(ship)\n"
        "\n"
        "        # ── Sensors skill check ───────────────────────────────────────────────\n"
        "        # Sensors station operator gets +2D bonus.\n"
        "        # Difficulty 8 (Easy) — space signals are loud, but reading them takes skill.\n"
        "        from engine.skill_checks import perform_skill_check\n"
        "        from engine.character import SkillRegistry, Character, DicePool\n"
        "        _SCAN_DIFFICULTY = 8\n"
        "        try:\n"
        "            char_obj = Character.from_db_dict(char)\n"
        "            sr = SkillRegistry()\n"
        "            sr.load_default()\n"
        "            base_pool = char_obj.get_skill_pool(\"sensors\", sr)\n"
        "            # Station bonus: +2D if sitting at sensors\n"
        "            if crew.get(\"sensors\") == char[\"id\"]:\n"
        "                bonus = DicePool(2, 0)\n"
        "                boosted = base_pool + bonus\n"
        "                # Temporarily write boosted pool into char for perform_skill_check\n"
        "                import json as _json\n"
        "                _skills = _json.loads(char.get(\"skills\", \"{}\"))\n"
        "                _orig = _skills.get(\"sensors\")\n"
        "                _skills[\"sensors\"] = str(boosted)\n"
        "                char[\"skills\"] = _json.dumps(_skills)\n"
        "                scan_result = perform_skill_check(char, \"sensors\", _SCAN_DIFFICULTY, sr)\n"
        "                # Restore\n"
        "                if _orig is None:\n"
        "                    _skills.pop(\"sensors\", None)\n"
        "                else:\n"
        "                    _skills[\"sensors\"] = _orig\n"
        "                char[\"skills\"] = _json.dumps(_skills)\n"
        "            else:\n"
        "                scan_result = perform_skill_check(char, \"sensors\", _SCAN_DIFFICULTY, sr)\n"
        "        except Exception:\n"
        "            scan_result = None  # Graceful-drop: show full scan on error\n"
        "\n"
        "        # Determine info tier from result\n"
        "        # fumble -> nothing; fail -> basic; success -> standard; crit -> deep\n"
        "        if scan_result is None:\n"
        "            scan_tier = \"success\"   # error fallback\n"
        "        elif scan_result.fumble:\n"
        "            scan_tier = \"fumble\"\n"
        "        elif not scan_result.success:\n"
        "            scan_tier = \"fail\"\n"
        "        elif scan_result.critical_success:\n"
        "            scan_tier = \"critical\"\n"
        "        else:\n"
        "            scan_tier = \"success\"\n"
        "\n"
        "        # Show skill roll feedback to the scanner\n"
        "        if scan_result is not None:\n"
        "            tier_label = {\n"
        "                \"fumble\":   f\"{ansi.BRIGHT_RED}SENSOR FAILURE{ansi.RESET}\",\n"
        "                \"fail\":     f\"{ansi.DIM}Basic read{ansi.RESET}\",\n"
        "                \"success\":  f\"{ansi.BRIGHT_CYAN}Standard sweep{ansi.RESET}\",\n"
        "                \"critical\": f\"{ansi.BRIGHT_GREEN}Deep scan{ansi.RESET}\",\n"
        "            }[scan_tier]\n"
        "            station_note = \" [+2D station]\" if crew.get(\"sensors\") == char[\"id\"] else \"\"\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.DIM}[Sensors: {scan_result.pool_str} vs {_SCAN_DIFFICULTY} \"\n"
        "                f\"— roll {scan_result.roll}]{ansi.RESET}  {tier_label}{station_note}\"\n"
        "            )\n"
        "\n"
        "        if scan_tier == \"fumble\":\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}\"\n"
        "            )\n"
        "            if player_zone:\n"
        "                await ctx.session.send_line(f\"  {ansi.DIM}Zone: {player_zone}{ansi.RESET}\")\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.BRIGHT_RED}Sensor array offline — interference or calibration error.{ansi.RESET}\"\n"
        "            )\n"
        "            await ctx.session.send_line(\"\")\n"
        "            return\n"
        "\n"
        "        others = [s for s in await ctx.db.get_ships_in_space() if s[\"id\"] != ship[\"id\"]]\n"
        "        await ctx.session.send_line(f\"  {ansi.BRIGHT_CYAN}=== Sensor Scan ==={ansi.RESET}\")\n"
        "        if player_zone:\n"
        "            await ctx.session.send_line(\n"
        "                f\"  {ansi.DIM}Zone: {player_zone}{ansi.RESET}\")\n"
        "        any_contacts = False\n"
        "        for s in others:\n"
        "            t = reg.get(s[\"template\"])\n"
        "            tname = t.name if t else s[\"template\"]\n"
        "            rng = grid.get_range(ship[\"id\"], s[\"id\"])\n"
        "            pos = grid.get_position(ship[\"id\"], s[\"id\"])\n"
        "            dmg = s.get(\"hull_damage\", 0)\n"
        "            if scan_tier == \"fail\":\n"
        "                # Basic: name + range only\n"
        "                await ctx.session.send_line(\n"
        "                    f\"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} — \"\n"
        "                    f\"Range: {rng.label}\")\n"
        "            elif scan_tier == \"critical\":\n"
        "                # Deep: full data + hull % + cargo flag\n"
        "                hull_pct = max(0, 100 - dmg * 10)\n"
        "                status = f\"Hull {hull_pct}%\" if dmg > 0 else \"Undamaged\"\n"
        "                sys_json = s.get(\"systems\", \"{}\")\n"
        "                try:\n"
        "                    import json as _j; _sys = _j.loads(sys_json) if isinstance(sys_json, str) else sys_json\n"
        "                except Exception:\n"
        "                    _sys = {}\n"
        "                cargo_flag = \"\"\n"
        "                if _sys.get(\"smuggling_job\"):\n"
        "                    cargo_flag = f\"  {ansi.BRIGHT_YELLOW}[CARGO ANOMALY DETECTED]{ansi.RESET}\"\n"
        "                await ctx.session.send_line(\n"
        "                    f\"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})\")\n"
        "                await ctx.session.send_line(\n"
        "                    f\"    Range: {rng.label}  Position: {pos}  Status: {status}{cargo_flag}\")\n"
        "            else:\n"
        "                # Standard: name, type, range, position, status\n"
        "                status = \"Active\" if dmg == 0 else f\"Damaged ({dmg} hits)\"\n"
        "                await ctx.session.send_line(\n"
        "                    f\"  Contact: {ansi.BRIGHT_WHITE}{s['name']}{ansi.RESET} ({tname})\")\n"
        "                await ctx.session.send_line(\n"
        "                    f\"    Range: {rng.label}  Position: {pos}  Status: {status}\")\n"
        "            any_contacts = True\n"
        "        # ── NPC Traffic ships in same zone ────────────────────────────────────\n"
        "        if player_zone:\n"
        "            traffic_ships = get_traffic_manager().get_zone_ships(player_zone)\n"
        "            for ts in traffic_ships:\n"
        "                if scan_tier == \"fail\":\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} \"\n"
        "                        f\"— Range: local zone\")\n"
        "                elif scan_tier == \"critical\":\n"
        "                    archetype_label = ts.archetype.value.title()\n"
        "                    cargo_flag = \"\"\n"
        "                    if ts.archetype.value.lower() == \"smuggler\":\n"
        "                        cargo_flag = f\"  {ansi.BRIGHT_YELLOW}[IRREGULAR POWER SIGNATURE]{ansi.RESET}\"\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} \"\n"
        "                        f\"[NPC {archetype_label}]{cargo_flag}\")\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"    Zone: {player_zone}  Transponder: {ts.transponder_type}\"\n"
        "                        f\"  Captain: {ts.captain_name}\")\n"
        "                else:\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"  Contact: {ansi.BRIGHT_WHITE}{ts.sensors_name()}{ansi.RESET} \"\n"
        "                        f\"[NPC {ts.archetype.value.title()}]\")\n"
        "                    await ctx.session.send_line(\n"
        "                        f\"    Zone: {player_zone}  Transponder: {ts.transponder_type}\"\n"
        "                        f\"  Captain: {ts.captain_name}\")\n"
        "                any_contacts = True\n"
        "        if not any_contacts:\n"
        "            await ctx.session.send_line(\"  No other ships detected.\")\n"
        "        await ctx.session.send_line(\"\")"
    )

    src = apply(src, old_scan, new_scan, "ScanCommand.execute body")
    print("  [1/2] ScanCommand sensors skill check added (4 tiers)")

    # ══════════════════════════════════════════════════════════════════════════
    # PATCH 2 — HyperspaceCommand: route through perform_skill_check,
    #           add misjump on fumble, halved fuel on critical
    # ══════════════════════════════════════════════════════════════════════════

    old_astro = (
        "        # Astrogation roll\n"
        "        from engine.character import Character, SkillRegistry\n"
        "        char_obj = Character.from_db_dict(ctx.session.character)\n"
        "        sr = SkillRegistry()\n"
        "        sr.load_file(\"data/skills.yaml\")\n"
        "        from engine.dice import roll_d6_pool, DicePool as DP\n"
        "        astro_pool = char_obj.get_skill_pool(\"astrogation\", sr)\n"
        "        roll = roll_d6_pool(astro_pool)\n"
        "        difficulty = 10  # Easy for known routes\n"
        "        if roll.total < difficulty:\n"
        "            await ctx.session_mgr.broadcast_to_room(ship[\"bridge_room_id\"],\n"
        "                f\"  {ansi.BRIGHT_RED}[NAV]{ansi.RESET} Astrogation calculation failed! \"\n"
        "                f\"(Roll: {roll.total} vs {difficulty}) \"\n"
        "                f\"Cannot make the jump safely. (Fuel not consumed.)\")\n"
        "            return\n"
        "        # Charge fuel\n"
        "        char[\"credits\"] = credits - fuel_cost\n"
        "        await ctx.db.save_character(char[\"id\"], credits=char[\"credits\"])\n"
        "        # Remove from space grid\n"
        "        get_space_grid().remove_ship(ship[\"id\"])\n"
        "        # Store location on ship\n"
        "        systems[\"location\"] = dest_key\n"
        "        # Traffic: map dest_key to a zone id\n"
        "        from engine.npc_space_traffic import ZONES as _TZ\n"
        "        _hzone = dest_key + \"_orbit\" if (dest_key + \"_orbit\") in _TZ else \"tatooine_orbit\"\n"
        "        systems[\"current_zone\"] = _hzone\n"
        "        await ctx.db.update_ship(ship[\"id\"], systems=json.dumps(systems))\n"
        "        await ctx.session_mgr.broadcast_to_room(ship[\"bridge_room_id\"],\n"
        "            f\"  {ansi.BRIGHT_CYAN}[HYPERSPACE]{ansi.RESET} \"\n"
        "            f\"Astrogation plotted. (Roll: {roll.total} vs {difficulty})\\n\"\n"
        "            f\"  Stars stretch into lines as the {ship['name']} jumps to lightspeed!\\n\"\n"
        "            f\"  ...\\n\"\n"
        "            f\"  Arriving at {dest['name']}. Reverting to realspace.\")\n"
        "        # Re-add to grid at new location\n"
        "        speed = template.speed if template else 5\n"
        "        get_space_grid().add_ship(ship[\"id\"], speed)"
    )

    new_astro = (
        "        # ── Astrogation skill check (through skill engine) ───────────────────\n"
        "        # Navigator at sensors station grants +1D.\n"
        "        # Fumble = misjump (random zone + hazard table).\n"
        "        # Critical = clean jump, fuel cost halved.\n"
        "        from engine.skill_checks import perform_skill_check\n"
        "        from engine.character import Character, SkillRegistry, DicePool\n"
        "        difficulty = 10  # Easy for known Outer Rim routes\n"
        "        try:\n"
        "            char_obj = Character.from_db_dict(char)\n"
        "            sr = SkillRegistry()\n"
        "            sr.load_default()\n"
        "            crew = _get_crew(ship)\n"
        "            # Navigator bonus: +1D if someone is at sensors station\n"
        "            if crew.get(\"sensors\"):\n"
        "                import json as _jj\n"
        "                _skills = _jj.loads(char.get(\"skills\", \"{}\"))\n"
        "                base_pool = char_obj.get_skill_pool(\"astrogation\", sr)\n"
        "                boosted = base_pool + DicePool(1, 0)\n"
        "                _orig = _skills.get(\"astrogation\")\n"
        "                _skills[\"astrogation\"] = str(boosted)\n"
        "                char[\"skills\"] = _jj.dumps(_skills)\n"
        "                nav_result = perform_skill_check(char, \"astrogation\", difficulty, sr)\n"
        "                if _orig is None:\n"
        "                    _skills.pop(\"astrogation\", None)\n"
        "                else:\n"
        "                    _skills[\"astrogation\"] = _orig\n"
        "                char[\"skills\"] = _jj.dumps(_skills)\n"
        "                nav_note = \" [+1D navigator]\"\n"
        "            else:\n"
        "                nav_result = perform_skill_check(char, \"astrogation\", difficulty, sr)\n"
        "                nav_note = \"\"\n"
        "        except Exception:\n"
        "            # Graceful fallback: treat as plain success\n"
        "            nav_result = None\n"
        "            nav_note = \"\"\n"
        "\n"
        "        # ── Fumble: misjump ───────────────────────────────────────────────────\n"
        "        if nav_result is not None and nav_result.fumble:\n"
        "            import random as _rnd\n"
        "            from engine.starships import roll_hazard_table\n"
        "            from engine.npc_space_traffic import ZONES as _TZ\n"
        "            misjump_zones = [z for z in _TZ if \"deep_space\" in z or \"orbit\" in z]\n"
        "            misjump_zone = _rnd.choice(misjump_zones) if misjump_zones else \"tatooine_deep_space\"\n"
        "            # Charge full fuel for the botched jump\n"
        "            char[\"credits\"] = credits - fuel_cost\n"
        "            await ctx.db.save_character(char[\"id\"], credits=char[\"credits\"])\n"
        "            # Move ship to random zone\n"
        "            get_space_grid().remove_ship(ship[\"id\"])\n"
        "            systems[\"current_zone\"] = misjump_zone\n"
        "            systems[\"location\"] = misjump_zone.split(\"_\")[0]\n"
        "            # Fire hazard table\n"
        "            hazard = roll_hazard_table(systems)\n"
        "            if hazard.hull_damage:\n"
        "                existing_dmg = ship.get(\"hull_damage\", 0)\n"
        "                await ctx.db.update_ship(\n"
        "                    ship[\"id\"], hull_damage=existing_dmg + hazard.hull_damage\n"
        "                )\n"
        "            if hazard.systems_damaged:\n"
        "                for _sys_name in hazard.systems_damaged:\n"
        "                    systems[_sys_name] = False\n"
        "            await ctx.db.update_ship(ship[\"id\"], systems=json.dumps(systems))\n"
        "            speed = template.speed if template else 5\n"
        "            get_space_grid().add_ship(ship[\"id\"], speed)\n"
        "            await ctx.session_mgr.broadcast_to_room(\n"
        "                ship[\"bridge_room_id\"],\n"
        "                f\"  {ansi.BRIGHT_RED}[MISJUMP]{ansi.RESET} \"\n"
        "                f\"Astrogation catastrophically failed! \"\n"
        "                f\"(Roll: {nav_result.roll} vs {difficulty} — FUMBLE{nav_note})\\n\"\n"
        "                f\"  Hyperspace vortex tears open — the ship lurches out of control!\\n\"\n"
        "                f\"  {hazard.narrative}\\n\"\n"
        "                f\"  Reverting to realspace in unknown region: {misjump_zone}.\"\n"
        "            )\n"
        "            return\n"
        "\n"
        "        # ── Failure: calculation aborted ──────────────────────────────────────\n"
        "        if nav_result is not None and not nav_result.success:\n"
        "            await ctx.session_mgr.broadcast_to_room(\n"
        "                ship[\"bridge_room_id\"],\n"
        "                f\"  {ansi.BRIGHT_RED}[NAV]{ansi.RESET} Astrogation calculation failed! \"\n"
        "                f\"(Roll: {nav_result.roll} vs {difficulty}{nav_note}) \"\n"
        "                f\"Cannot make the jump safely. (Fuel not consumed.)\"\n"
        "            )\n"
        "            return\n"
        "\n"
        "        # ── Success or graceful-drop ──────────────────────────────────────────\n"
        "        # Critical: halve fuel cost\n"
        "        if nav_result is not None and nav_result.critical_success:\n"
        "            fuel_cost = max(50, fuel_cost // 2)\n"
        "        roll_str = f\"Roll: {nav_result.roll} vs {difficulty}{nav_note}\" if nav_result else \"auto\"\n"
        "        crit_note = \" (critical — efficient jump!)\" if (\n"
        "            nav_result and nav_result.critical_success) else \"\"\n"
        "\n"
        "        # Charge fuel\n"
        "        char[\"credits\"] = credits - fuel_cost\n"
        "        await ctx.db.save_character(char[\"id\"], credits=char[\"credits\"])\n"
        "        # Remove from space grid\n"
        "        get_space_grid().remove_ship(ship[\"id\"])\n"
        "        # Store location on ship\n"
        "        systems[\"location\"] = dest_key\n"
        "        # Traffic: map dest_key to a zone id\n"
        "        from engine.npc_space_traffic import ZONES as _TZ\n"
        "        _hzone = dest_key + \"_orbit\" if (dest_key + \"_orbit\") in _TZ else \"tatooine_orbit\"\n"
        "        systems[\"current_zone\"] = _hzone\n"
        "        await ctx.db.update_ship(ship[\"id\"], systems=json.dumps(systems))\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            ship[\"bridge_room_id\"],\n"
        "            f\"  {ansi.BRIGHT_CYAN}[HYPERSPACE]{ansi.RESET} \"\n"
        "            f\"Astrogation plotted. ({roll_str}){crit_note}\\n\"\n"
        "            f\"  Stars stretch into lines as the {ship['name']} jumps to lightspeed!\\n\"\n"
        "            f\"  ...\\n\"\n"
        "            f\"  Arriving at {dest['name']}. Reverting to realspace.\"\n"
        "        )\n"
        "        # Re-add to grid at new location\n"
        "        speed = template.speed if template else 5\n"
        "        get_space_grid().add_ship(ship[\"id\"], speed)"
    )

    src = apply(src, old_astro, new_astro, "HyperspaceCommand astrogation block")
    print("  [2/2] HyperspaceCommand astrogation routed through skill engine (misjump + crit)")

    # ── Validate ──────────────────────────────────────────────────────────────
    try:
        ast.parse(src)
        print("  AST validation: OK")
    except SyntaxError as e:
        print(f"  AST FAIL: {e}")
        sys.exit(1)

    write(TARGET, src)
    print(f"\nPatch applied successfully → {TARGET}")
    print("No schema changes. No new files.")


if __name__ == "__main__":
    main()
