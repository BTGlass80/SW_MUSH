# -*- coding: utf-8 -*-
"""
Patch: Add Director AI schema (v5) and wire Director tick.

Changes:
  1. db/database.py:
     - SCHEMA_VERSION 4 -> 5
     - Add migration v5: CREATE TABLE zone_influence, director_log
  2. server/game_server.py:
     - Add Director tick after world events tick

Usage:
  python patches/director_wire_patch.py

Creates backups. Validates syntax via ast.parse(). Safe to re-run.
"""
import ast
import shutil
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

print("=" * 60)
print("Director AI — Drop 3 Patch")
print("=" * 60)

# ══════════════════════════════════════════════════════════════
#  PATCH 1: database.py — schema v5 migration
# ══════════════════════════════════════════════════════════════

print("\n── db/database.py ──")
db_src = DB_FILE.read_text(encoding="utf-8")
db_bak = DB_FILE.with_suffix(".py.director_bak")
shutil.copy2(DB_FILE, db_bak)
print(f"  Backup: {db_bak}")

db_changes = 0

# 1a. Check if zone_influence already exists
if "zone_influence" in db_src:
    print("  ✓ zone_influence already present — skipping DB patch.")
else:
    # Bump SCHEMA_VERSION
    if "SCHEMA_VERSION = 4" in db_src:
        db_src = db_src.replace("SCHEMA_VERSION = 4", "SCHEMA_VERSION = 5", 1)
        print("  + SCHEMA_VERSION 4 → 5")
        db_changes += 1
    elif "SCHEMA_VERSION = 3" in db_src:
        # Tutorial patch may not have been applied yet
        db_src = db_src.replace("SCHEMA_VERSION = 3", "SCHEMA_VERSION = 5", 1)
        print("  + SCHEMA_VERSION 3 → 5")
        db_changes += 1
    elif "SCHEMA_VERSION = 5" in db_src:
        print("  ✓ SCHEMA_VERSION already 5")
    else:
        print("  WARNING: Could not find SCHEMA_VERSION to update")

    # Add migration v5 to MIGRATIONS dict
    # Find the closing brace of the MIGRATIONS dict
    V5_MIGRATION = (
        '    5: [\n'
        '        """CREATE TABLE IF NOT EXISTS zone_influence (\n'
        '            zone_id TEXT NOT NULL,\n'
        '            faction TEXT NOT NULL,\n'
        '            score INTEGER DEFAULT 0,\n'
        '            last_updated TEXT DEFAULT (datetime(\'now\')),\n'
        '            PRIMARY KEY (zone_id, faction)\n'
        '        )""",\n'
        '        """CREATE TABLE IF NOT EXISTS director_log (\n'
        '            id INTEGER PRIMARY KEY AUTOINCREMENT,\n'
        '            timestamp TEXT DEFAULT (datetime(\'now\')),\n'
        '            event_type TEXT NOT NULL,\n'
        '            summary TEXT,\n'
        '            details_json TEXT,\n'
        '            token_cost_input INTEGER DEFAULT 0,\n'
        '            token_cost_output INTEGER DEFAULT 0\n'
        '        )""",\n'
        '    ],\n'
    )

    # Try multiple anchor patterns for the end of MIGRATIONS dict
    anchors = [
        # After v4 (tutorial_step)
        (
            '    4: [\n'
            '        "ALTER TABLE characters ADD COLUMN tutorial_step INTEGER DEFAULT 0",\n'
            '    ],\n'
            '}'
        ),
        # After v3 (bounty) if v4 not applied
        (
            '    3: [\n'
            '        "ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0",\n'
            '    ],\n'
            '}'
        ),
    ]

    applied_mig = False
    for anchor in anchors:
        if anchor in db_src:
            replacement = anchor[:-1] + V5_MIGRATION + '}'
            db_src = db_src.replace(anchor, replacement, 1)
            print("  + Added migration v5 (zone_influence + director_log)")
            db_changes += 1
            applied_mig = True
            break

    if not applied_mig:
        # Try CRLF variants
        for anchor in anchors:
            anchor_crlf = anchor.replace('\n', '\r\n')
            if anchor_crlf in db_src:
                v5_crlf = V5_MIGRATION.replace('\n', '\r\n')
                replacement = anchor_crlf[:-1] + v5_crlf + '}'
                db_src = db_src.replace(anchor_crlf, replacement, 1)
                print("  + Added migration v5 (CRLF)")
                db_changes += 1
                applied_mig = True
                break

    if not applied_mig:
        print("  WARNING: Could not find MIGRATIONS anchor. Add manually:")
        print('    5: [')
        print('        """CREATE TABLE IF NOT EXISTS zone_influence (...""",')
        print('        """CREATE TABLE IF NOT EXISTS director_log (...""",')
        print('    ],')

# Validate DB syntax
if db_changes > 0:
    try:
        ast.parse(db_src)
    except SyntaxError as e:
        print(f"\n  ERROR: database.py syntax check failed: {e}")
        print(f"  Restoring from backup: {db_bak}")
        shutil.copy2(db_bak, DB_FILE)
        sys.exit(1)
    DB_FILE.write_text(db_src, encoding="utf-8")
    print(f"  ✓ database.py patched ({db_changes} change(s)).")
else:
    print("  No changes needed.")


# ══════════════════════════════════════════════════════════════
#  PATCH 2: game_server.py — Director tick
# ══════════════════════════════════════════════════════════════

print("\n── server/game_server.py ──")
gs_src = GS_FILE.read_text(encoding="utf-8")
gs_bak = GS_FILE.with_suffix(".py.director_bak")
shutil.copy2(GS_FILE, gs_bak)
print(f"  Backup: {gs_bak}")

gs_changes = 0

DIRECTOR_BLOCK = (
    '\n'
    '            # ── Director AI tick ──\n'
    '            try:\n'
    '                from engine.director import get_director\n'
    '                await get_director().tick(self.db, self.session_mgr)\n'
    '            except Exception:\n'
    '                log.debug("Director tick skipped", exc_info=True)'
)

if "get_director" in gs_src:
    print("  ✓ Director tick already present — skipping.")
else:
    # Anchor priority: after world events tick > after ambient tick > after bounty board
    tick_anchors = [
        ("world events tick",
         '            try:\n'
         '                from engine.world_events import get_world_event_manager\n'
         '                await get_world_event_manager().tick(self.db, self.session_mgr)\n'
         '            except Exception:\n'
         '                log.debug("World events tick skipped", exc_info=True)'),
        ("ambient events tick",
         '            try:\n'
         '                from engine.ambient_events import get_ambient_manager\n'
         '                await get_ambient_manager().tick(self.db, self.session_mgr)\n'
         '            except Exception:\n'
         '                log.debug("Ambient events tick skipped", exc_info=True)'),
        ("bounty board tick",
         '            try:\n'
         '                from engine.bounty_board import get_bounty_board\n'
         '                bboard = get_bounty_board()\n'
         '                await bboard.ensure_loaded(self.db)\n'
         '            except Exception:\n'
         '                log.debug("Bounty board tick skipped", exc_info=True)'),
    ]

    applied_gs = False
    for anchor_name, anchor in tick_anchors:
        if anchor in gs_src:
            gs_src = gs_src.replace(anchor, anchor + DIRECTOR_BLOCK, 1)
            print(f"  + Director tick inserted after {anchor_name}.")
            gs_changes += 1
            applied_gs = True
            break
        anchor_crlf = anchor.replace('\n', '\r\n')
        block_crlf = DIRECTOR_BLOCK.replace('\n', '\r\n')
        if anchor_crlf in gs_src:
            gs_src = gs_src.replace(anchor_crlf, anchor_crlf + block_crlf, 1)
            print(f"  + Director tick inserted after {anchor_name} (CRLF).")
            gs_changes += 1
            applied_gs = True
            break

    if not applied_gs:
        print("  WARNING: Could not find tick loop anchor. Add manually:")
        print('            # ── Director AI tick ──')
        print('            try:')
        print('                from engine.director import get_director')
        print('                await get_director().tick(self.db, self.session_mgr)')
        print('            except Exception:')
        print('                log.debug("Director tick skipped", exc_info=True)')

# Validate GS syntax
if gs_changes > 0:
    try:
        ast.parse(gs_src)
    except SyntaxError as e:
        print(f"\n  ERROR: game_server.py syntax check failed: {e}")
        print(f"  Restoring from backup: {gs_bak}")
        shutil.copy2(gs_bak, GS_FILE)
        sys.exit(1)
    GS_FILE.write_text(gs_src, encoding="utf-8")
    print(f"  ✓ game_server.py patched ({gs_changes} change(s)).")
else:
    print("  No changes needed.")

# ── Summary ──
print()
print("=" * 60)
print("Drop 3 patch complete.")
print()
print("New file needed:")
print("  engine/director.py   (DirectorAI engine)")
print()
print("To activate the Director (after server restart):")
print("  @director enable")
print()
print("To check zone influence:")
print("  (from Python) get_director().get_all_zone_states()")
print()
print("Schema note: Delete sw_mush.db and restart to create new tables,")
print("  or restart and the migration will add them automatically.")
print("=" * 60)
