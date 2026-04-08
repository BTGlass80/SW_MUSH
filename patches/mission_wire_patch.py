#!/usr/bin/env python3
"""
mission_wire_patch.py
---------------------
Wires register_mission_commands() into game_server.py.

Adds:
  1. The import line alongside the other register_* imports
  2. The call in GameServer.__init__() alongside the other register_*() calls

Run from the SW_MUSH project root:
    python3 mission_wire_patch.py

Safe to re-run: skips if already wired.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("server/game_server.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

already_done = "register_mission_commands" in source
if already_done:
    print("✓ register_mission_commands already present — nothing to do.")
    sys.exit(0)

patched = source

# ── Step 1: Add import ────────────────────────────────────────────────────────
# Insert after: from parser.crew_commands import register_crew_commands
# (or force_commands if crew isn't found)

IMPORT_LINE = "from parser.mission_commands import register_mission_commands"

for anchor_import in [
    "from parser.crew_commands import register_crew_commands",
    "from parser.force_commands import register_force_commands",
    "from parser.space_commands import register_space_commands",
]:
    if anchor_import in patched:
        patched = patched.replace(
            anchor_import,
            anchor_import + "\n" + IMPORT_LINE,
            1,
        )
        print(f"  + Import inserted after: {anchor_import}")
        break
else:
    print("WARNING: Could not find import anchor in game_server.py.")
    print(f"Add this import manually:\n    {IMPORT_LINE}")

# ── Step 2: Add registration call ────────────────────────────────────────────
# Insert after: register_crew_commands(self.registry)
# or force_commands as fallback

CALL_LINE = "        register_mission_commands(self.registry)"

for anchor_call in [
    "        register_crew_commands(self.registry)",
    "        register_force_commands(self.registry)",
    "        register_space_commands(self.registry)",
]:
    if anchor_call in patched:
        patched = patched.replace(
            anchor_call,
            anchor_call + "\n" + CALL_LINE,
            1,
        )
        print(f"  + Call inserted after: {anchor_call.strip()}")
        break
else:
    print("WARNING: Could not find call anchor in game_server.py.")
    print(f"Add this call manually in __init__:\n    {CALL_LINE.strip()}")

# ── Step 3: Syntax validation ─────────────────────────────────────────────────

try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"\nERROR: Patched source failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

# ── Step 4: Write ─────────────────────────────────────────────────────────────

backup = TARGET.with_suffix(".py.mission_bak")
backup.write_text(source, encoding="utf-8")
print(f"  Backup written → {backup}")

TARGET.write_text(patched, encoding="utf-8")
print(f"✓ Patched {TARGET}")
print()
print("Mission commands now registered:")
print("  missions / mb / jobs / board")
print("  accept <id>")
print("  mission")
print("  complete")
print("  abandon")
print()
print("Restart main.py to activate.")
