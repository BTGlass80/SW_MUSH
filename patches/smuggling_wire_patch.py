#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
smuggling_wire_patch.py
-----------------------
Wires the smuggling system into the game.

Changes:
  1. db/database.py
     — Schema v6: CREATE TABLE smuggling_jobs
     — SCHEMA_VERSION 5 -> 6

  2. server/game_server.py
     — Import + register smuggling_commands
     — Add smuggling board refresh to tick loop

  3. parser/space_commands.py (LaunchCommand)
     — Call check_patrol_on_launch() when launching with active smuggling job

Run from the SW_MUSH project root:
    python patches/smuggling_wire_patch.py
"""
import ast, shutil, sys
from pathlib import Path

DB  = Path("db/database.py")
GS  = Path("server/game_server.py")
SC  = Path("parser/space_commands.py")

for f in (DB, GS, SC):
    if not f.exists():
        print(f"ERROR: {f} not found. Run from project root.")
        sys.exit(1)

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")
def validate(p, s):
    try:
        ast.parse(s); return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {p}: {e}"); return False
def backup(p):
    bak = p.with_suffix(".py.smug_bak")
    if not bak.exists(): shutil.copy2(p, bak)
    print(f"  Backup: {bak.name}")

# ══════════════════════════════════════════════════════════════════════════════
# 1. db/database.py — schema v6
# ══════════════════════════════════════════════════════════════════════════════
print("\n── db/database.py ───────────────────────────────────────────────────────")

src = read(DB)

if "smuggling_jobs" in src:
    print("  ✓ smuggling_jobs table already present — skipping.")
else:
    patched = src

    # Bump schema version
    for old_ver, new_ver in [("SCHEMA_VERSION = 5", "SCHEMA_VERSION = 6"),
                              ("SCHEMA_VERSION = 4", "SCHEMA_VERSION = 6"),
                              ("SCHEMA_VERSION = 3", "SCHEMA_VERSION = 6")]:
        if old_ver in patched:
            patched = patched.replace(old_ver, new_ver, 1)
            print(f"  + {old_ver} -> {new_ver}")
            break

    # Add migration v6 to MIGRATIONS dict
    # Find the closing brace — try multiple anchors
    V6 = (
        "    6: [\n"
        "        \"\"\"CREATE TABLE IF NOT EXISTS smuggling_jobs (\n"
        "            id TEXT PRIMARY KEY,\n"
        "            status TEXT DEFAULT 'available',\n"
        "            accepted_by INTEGER,\n"
        "            data TEXT NOT NULL\n"
        "        )\"\"\",\n"
        "    ],\n"
    )

    ANCHORS = [
        "    5: [\n        \"\"\"CREATE TABLE IF NOT EXISTS zone_influence",
        "    4: [\n        \"ALTER TABLE characters ADD COLUMN tutorial_step",
        "    3: [\n        \"ALTER TABLE characters ADD COLUMN bounty",
    ]

    applied = False
    for anchor_start in ANCHORS:
        # Find the full v5/v4/v3 block ending with "},\n}" or "    ],\n}"
        # Simpler: just find the last '],' + '}' that closes MIGRATIONS
        idx = patched.find(anchor_start)
        if idx == -1:
            continue
        # Find the closing brace of the MIGRATIONS dict after this anchor
        close_idx = patched.find("\n}", idx)
        if close_idx == -1:
            continue
        # Insert V6 before the closing brace
        patched = patched[:close_idx] + "\n" + V6 + patched[close_idx:]
        print(f"  + Migration v6 inserted (smuggling_jobs table)")
        applied = True
        break

    if not applied:
        print("  WARNING: Could not find MIGRATIONS anchor. Add manually:")
        print("    6: [\"\"\"CREATE TABLE IF NOT EXISTS smuggling_jobs (...)\"\"\"]\n")

    if validate(DB, patched):
        backup(DB)
        write(DB, patched)
        print("  ✓ db/database.py patched")
    else:
        print("  db/database.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# 2. server/game_server.py — import + register + tick
# ══════════════════════════════════════════════════════════════════════════════
print("\n── server/game_server.py ────────────────────────────────────────────────")

src = read(GS)
patched = src
changed = False

# Import
if "register_smuggling_commands" not in patched:
    IMPORT_LINE = "from parser.smuggling_commands import register_smuggling_commands"
    for anchor in [
        "from parser.news_commands import register_news_commands",
        "from parser.director_commands import register_director_commands",
        "from parser.bounty_commands import register_bounty_commands",
    ]:
        if anchor in patched:
            patched = patched.replace(anchor, anchor + "\n" + IMPORT_LINE, 1)
            print(f"  + Import inserted after: {anchor}")
            changed = True
            break
    else:
        print("  WARNING: Could not find import anchor for smuggling_commands")
else:
    print("  ✓ register_smuggling_commands import already present")

# Register call
if "register_smuggling_commands(self.registry)" not in patched:
    CALL_LINE = "        register_smuggling_commands(self.registry)"
    for anchor in [
        "        register_news_commands(self.registry)",
        "        register_director_commands(self.registry)",
        "        register_bounty_commands(self.registry)",
    ]:
        if anchor in patched:
            patched = patched.replace(anchor, anchor + "\n" + CALL_LINE, 1)
            print(f"  + Register call inserted after: {anchor.strip()}")
            changed = True
            break
    else:
        print("  WARNING: Could not find register anchor for smuggling_commands")
else:
    print("  ✓ register_smuggling_commands() call already present")

# Tick loop: smuggling board refresh (runs every 60s, not every tick)
if "smuggling_board" in patched or "get_smuggling_board" in patched:
    print("  ✓ Smuggling tick already wired")
else:
    TICK_BLOCK = (
        "\n"
        "            # -- Smuggling board expiry cleanup --\n"
        "            try:\n"
        "                from engine.smuggling import get_smuggling_board\n"
        "                await get_smuggling_board().ensure_loaded(self.db)\n"
        "            except Exception:\n"
        "                log.debug('Smuggling board tick skipped', exc_info=True)\n"
    )
    # Insert after the bounty board tick or mission board tick
    for anchor in [
        "log.debug(\"Bounty board tick skipped\"",
        "log.debug(\"Mission board tick skipped\"",
        "log.debug(\"NPC space traffic tick skipped\"",
    ]:
        if anchor in patched:
            # Find end of that except block
            idx = patched.find(anchor)
            end = patched.find("\n", idx) + 1
            patched = patched[:end] + TICK_BLOCK + patched[end:]
            print("  + Smuggling board tick inserted into tick loop")
            changed = True
            break
    else:
        print("  WARNING: Could not find tick loop anchor. Add manually.")

if changed:
    if validate(GS, patched):
        backup(GS)
        write(GS, patched)
        print("  ✓ server/game_server.py patched")
    else:
        print("  server/game_server.py unchanged")
else:
    print("  No changes needed")

# ══════════════════════════════════════════════════════════════════════════════
# 3. parser/space_commands.py — patrol check on launch
# ══════════════════════════════════════════════════════════════════════════════
print("\n── parser/space_commands.py (patrol hook) ───────────────────────────────")

src = read(SC)

if "check_patrol_on_launch" in src:
    print("  ✓ Patrol hook already present — skipping.")
else:
    # Insert patrol check just before the launch success broadcast
    # Anchor: the broadcast line after ship launches
    OLD_LAUNCH = (
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            ship[\"bridge_room_id\"],\n"
        "            ansi.success(\n"
        "                f\"  {ship['name']} launches from {bay_name}! \"\n"
        "                f\"(Fuel: {fuel_cost:,}cr) You are now in space.\"))"
    )
    NEW_LAUNCH = (
        "        # Patrol encounter check for active smuggling jobs\n"
        "        try:\n"
        "            from parser.smuggling_commands import check_patrol_on_launch\n"
        "            await check_patrol_on_launch(ctx)\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "        await ctx.session_mgr.broadcast_to_room(\n"
        "            ship[\"bridge_room_id\"],\n"
        "            ansi.success(\n"
        "                f\"  {ship['name']} launches from {bay_name}! \"\n"
        "                f\"(Fuel: {fuel_cost:,}cr) You are now in space.\"))"
    )

    patched = src
    for old, new in [(OLD_LAUNCH, NEW_LAUNCH),
                     (OLD_LAUNCH.replace("\n", "\r\n"), NEW_LAUNCH.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + Patrol check hook inserted before launch broadcast")
            break
    else:
        print("  WARNING: Could not find launch broadcast anchor.")
        print("  Add manually in LaunchCommand.execute() before the final broadcast:")
        print("    from parser.smuggling_commands import check_patrol_on_launch")
        print("    await check_patrol_on_launch(ctx)")
        patched = src

    if patched != src:
        if validate(SC, patched):
            backup(SC)
            write(SC, patched)
            print("  ✓ parser/space_commands.py patched")
        else:
            print("  parser/space_commands.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Final syntax check ───────────────────────────────────────────────────")
all_ok = True
for f in (DB, GS, SC):
    try:
        ast.parse(read(f))
        print(f"  OK  {f}")
    except SyntaxError as e:
        print(f"  ERR {f}: {e}")
        all_ok = False

print()
if all_ok:
    print("Smuggling system installed.")
    print()
    print("Commands: smugjobs | smugaccept <id> | smugjob | smugdeliver | smugdump")
    print("Access:   Near any Cantina, Docking Bay, or Jabba's contacts")
    print("Risk:     Patrol check on launch — higher tier = more danger")
else:
    print("WARNING: Syntax errors found. Review above.")
    sys.exit(1)
