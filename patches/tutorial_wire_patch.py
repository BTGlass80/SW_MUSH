#!/usr/bin/env python3
"""
tutorial_wire_patch.py
----------------------
Wires the TutorialManager into the game server and adds
the tutorial_step column to the characters table.

Changes:
  1. db/database.py: Adds migration v5 for tutorial_step column
  2. game_server.py: Imports TutorialManager, instantiates it,
     calls on_enter_game after character selection,
     calls on_command after command execution.

Run from the SW_MUSH project root:
    python3 patches/tutorial_wire_patch.py

Safe to re-run.
"""

import ast
import sys
from pathlib import Path

DB_FILE = Path("db/database.py")
GS_FILE = Path("server/game_server.py")

errors = []
for f in (DB_FILE, GS_FILE):
    if not f.exists():
        errors.append(f"ERROR: {f} not found.")
if errors:
    for e in errors:
        print(e)
    sys.exit(1)


# ══════════════════════════════════════════════════════════════
#  PATCH 1: database.py — add migration for tutorial_step
# ══════════════════════════════════════════════════════════════

db_src = DB_FILE.read_text(encoding="utf-8")

if "tutorial_step" in db_src:
    print("  ✓ database.py already has tutorial_step — skipping.")
else:
    # Find the MIGRATIONS dict and add version 5
    # Current migrations go up to v4 (or v3 with bounty)
    # Look for the last migration entry
    if "    3: [" in db_src and "    4: [" not in db_src:
        # Add v4 migration
        MIGS_ANCHOR = '''    3: [
        "ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0",
    ],
}'''
        MIGS_NEW = '''    3: [
        "ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0",
    ],
    4: [
        "ALTER TABLE characters ADD COLUMN tutorial_step INTEGER DEFAULT 0",
    ],
}'''
        if MIGS_ANCHOR in db_src:
            db_src = db_src.replace(MIGS_ANCHOR, MIGS_NEW, 1)
            print("  + database.py: Added migration v4 for tutorial_step")
        else:
            print("  WARNING: Could not find migration anchor. Add manually:")
            print('    4: ["ALTER TABLE characters ADD COLUMN tutorial_step INTEGER DEFAULT 0"]')
    elif "    4: [" in db_src and "tutorial_step" not in db_src:
        # v4 exists but no tutorial_step — add v5
        # Find end of v4 block
        print("  WARNING: Migration v4 exists but no tutorial_step.")
        print("  Add manually to MIGRATIONS dict:")
        print('    5: ["ALTER TABLE characters ADD COLUMN tutorial_step INTEGER DEFAULT 0"]')
    else:
        print("  WARNING: Could not determine migration state. Add manually.")

    # Also add tutorial_step to save_character's writable columns
    if "_CHAR_WRITABLE_COLUMNS" in db_src and "tutorial_step" not in db_src:
        # Find the frozenset and add tutorial_step
        if '"credits",' in db_src:
            db_src = db_src.replace(
                '"credits",',
                '"credits", "tutorial_step",',
                1
            )
            print("  + database.py: Added tutorial_step to writable columns")

    try:
        ast.parse(db_src)
    except SyntaxError as e:
        print(f"  ERROR: database.py syntax check failed: {e}")
        sys.exit(1)

    DB_FILE.write_text(db_src, encoding="utf-8")


# ══════════════════════════════════════════════════════════════
#  PATCH 2: game_server.py — wire TutorialManager
# ══════════════════════════════════════════════════════════════

gs_src = GS_FILE.read_text(encoding="utf-8")

if "TutorialManager" in gs_src:
    print("  ✓ game_server.py already has TutorialManager — skipping.")
else:
    # Step 2a: Add import
    IMPORT_ANCHOR = "from engine.character import SkillRegistry, Character"
    IMPORT_LINE = "from engine.tutorial import TutorialManager"

    if IMPORT_ANCHOR in gs_src:
        gs_src = gs_src.replace(
            IMPORT_ANCHOR,
            IMPORT_ANCHOR + "\n" + IMPORT_LINE,
            1,
        )
        print("  + Import: TutorialManager added")
    else:
        print("  WARNING: Could not find import anchor.")

    # Step 2b: Instantiate in __init__
    INIT_ANCHOR = "        self._running = False"
    INIT_LINE = "\n        # Tutorial system\n        self.tutorial = TutorialManager()"

    if INIT_ANCHOR in gs_src:
        gs_src = gs_src.replace(
            INIT_ANCHOR,
            INIT_LINE + "\n\n" + INIT_ANCHOR,
            1,
        )
        print("  + __init__: self.tutorial = TutorialManager()")
    else:
        print("  WARNING: Could not find __init__ anchor.")

    # Step 2c: Add skip tutorial command check in the input loop
    # We need to add a check for "skip tutorial" before the normal
    # command dispatch, and call tutorial.on_command after dispatch.
    # This is harder to do surgically — let's add a note for manual wiring.
    print("")
    print("  MANUAL WIRING NEEDED in game_server.py:")
    print("  After a character enters the game (after character selection),")
    print("  add this call:")
    print("")
    print("    await self.tutorial.on_enter_game(session, self.db, self.session_mgr)")
    print("")
    print("  In the main input loop, after command execution, add:")
    print("")
    print("    # Tutorial advancement")
    print("    if session.character and session.character.get('tutorial_step', 0) < 7:")
    print("        await self.tutorial.on_command(session, cmd, args, self.db, self.session_mgr)")
    print("")
    print("  Also handle 'skip tutorial' before command dispatch:")
    print("")
    print("    if line.lower().strip() == 'skip tutorial':")
    print("        await self.tutorial.skip(session, self.db)")
    print("        continue")

    try:
        ast.parse(gs_src)
    except SyntaxError as e:
        print(f"  ERROR: game_server.py syntax check failed: {e}")
        sys.exit(1)

    GS_FILE.write_text(gs_src, encoding="utf-8")


print("\n✓ Tutorial system ready.")
print("  Files: engine/tutorial.py (new), db/database.py (patched), game_server.py (patched)")
print("  Delete sw_mush.db and restart to apply the migration.")
