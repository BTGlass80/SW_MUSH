# -*- coding: utf-8 -*-
"""
world_builder_patch.py — Wires auto-build into game_server.py + planet-aware landing
================================================================================
Run from project root:  python world_builder_patch.py

Applies two patches:
  1. game_server.py: Calls auto_build_if_needed() during startup after DB init
  2. space_commands.py: LandCommand uses planet-aware bay lookup via zone metadata

Dry-run safe: validates with ast.parse() before writing.
"""
import os, sys, shutil, ast

PROJECT = os.path.dirname(os.path.abspath(__file__))

# ================================================================
# PATCH 1: game_server.py — auto-build hook
# ================================================================
GS_PATH = os.path.join(PROJECT, "server", "game_server.py")

GS_ANCHOR = '''        log.info("Game data loaded: %d species, %d skills",
                 self.species_reg.count, self.skill_reg.count)'''

GS_REPLACEMENT = '''        log.info("Game data loaded: %d species, %d skills",
                 self.species_reg.count, self.skill_reg.count)

        # Auto-build world if only seed rooms exist
        try:
            from build_mos_eisley import auto_build_if_needed
            built = await auto_build_if_needed(self.config.db_path)
            if built:
                log.info("World auto-build completed successfully.")
        except Exception as _build_err:
            log.warning("World auto-build skipped: %s", _build_err)'''

# ================================================================
# PATCH 2: space_commands.py — planet-aware LandCommand
# ================================================================
SC_PATH = os.path.join(PROJECT, "parser", "space_commands.py")

# Current: just does find_rooms("Docking Bay") and picks first
SC_ANCHOR = '''        rooms = await ctx.db.find_rooms("Docking Bay")
        if not rooms:
            await ctx.session.send_line("  No docking bays found!")
            return
        bay = rooms[0]'''

# Replacement: look up planet from current zone, search for planet-specific bay
SC_REPLACEMENT = '''        # Planet-aware bay lookup: find docking bay for the planet we're orbiting
        _land_planet = None
        try:
            import json as _lj2
            _land_sys = _lj2.loads(ship.get("systems") or "{}")
            _land_zone_id = _land_sys.get("current_zone", "")
            from engine.npc_space_traffic import ZONES as _LZONES
            _land_zone = _LZONES.get(_land_zone_id)
            if _land_zone and _land_zone.planet:
                _land_planet = _land_zone.planet
        except Exception:
            pass
        # Search for planet-specific bay, fall back to any "Docking Bay"
        _BAY_SEARCH = {
            "tatooine": "Docking Bay",
            "nar_shaddaa": "Nar Shaddaa - Docking",
            "kessel": "Kessel - Spaceport",
            "corellia": "Coronet City - Starport Docking",
        }
        _bay_query = _BAY_SEARCH.get(_land_planet, "Docking Bay")
        rooms = await ctx.db.find_rooms(_bay_query)
        if not rooms and _land_planet:
            # Fallback: try generic search
            rooms = await ctx.db.find_rooms("Docking Bay")
        if not rooms:
            await ctx.session.send_line("  No docking bays found!")
            return
        bay = rooms[0]'''


def apply_patch(filepath, anchor, replacement, label):
    """Apply a single anchor-based patch."""
    if not os.path.exists(filepath):
        print(f"  [SKIP] {label}: file not found ({filepath})")
        return False

    with open(filepath, "r", encoding="utf-8") as f:
        src = f.read()

    if anchor not in src:
        # Check if already patched
        if "auto_build_if_needed" in src and "auto-build" in label.lower():
            print(f"  [SKIP] {label}: already patched")
            return False
        if "_BAY_SEARCH" in src and "planet-aware" in label.lower():
            print(f"  [SKIP] {label}: already patched")
            return False
        print(f"  [FAIL] {label}: anchor not found")
        print(f"         Looking for: {anchor[:60]}...")
        return False

    new_src = src.replace(anchor, replacement, 1)

    # Validate
    try:
        ast.parse(new_src)
    except SyntaxError as e:
        print(f"  [FAIL] {label}: syntax error after patch — {e}")
        return False

    # Backup
    bak = filepath + ".bak"
    if not os.path.exists(bak):
        shutil.copy2(filepath, bak)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_src)

    print(f"  [OK]   {label}")
    return True


def main():
    print("=" * 60)
    print("  World Builder Patch — auto-build + planet-aware landing")
    print("=" * 60)

    ok1 = apply_patch(GS_PATH, GS_ANCHOR, GS_REPLACEMENT,
                      "game_server.py: auto-build hook")
    ok2 = apply_patch(SC_PATH, SC_ANCHOR, SC_REPLACEMENT,
                      "space_commands.py: planet-aware LandCommand")

    print()
    if ok1 or ok2:
        print("  Patches applied. Delete sw_mush.db and restart to rebuild.")
    else:
        print("  No patches applied (already done or anchor mismatch).")
    print()


if __name__ == "__main__":
    main()
