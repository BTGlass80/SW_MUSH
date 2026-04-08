#!/bin/bash
# SW_MUSH Cleanup Script — run from project root
# Removes dead code, backup files, and archives patch scripts.
# Review before running. Safe to re-run.

set -e
echo "=== SW_MUSH Cleanup ==="

# 1. Remove dead code files (not imported anywhere)
echo ""
echo "[1/4] Removing dead code..."
rm -f engine/space_commands.py
rm -f parser/starships.py
echo "  Deleted: engine/space_commands.py (1,073 lines, superseded by parser/space_commands.py)"
echo "  Deleted: parser/starships.py (877 lines, superseded by engine/starships.py)"

# 2. Remove backup files (pre-patch snapshots)
echo ""
echo "[2/4] Removing .bak files..."
rm -f db/database.py.bounty_bak
rm -f parser/combat_commands.py.bounty_combat_bak
rm -f server/game_server.py.bak
rm -f server/game_server.py.bounty_bak
rm -f server/game_server.py.mission_bak
echo "  Deleted 5 backup files."

# 3. Remove duplicate patch file
echo ""
echo "[3/4] Removing duplicate patch..."
rm -f "bounty_combat_patch (1).py"
echo "  Deleted: bounty_combat_patch (1).py"

# 4. Archive applied patch scripts
echo ""
echo "[4/4] Archiving patch scripts to patches/..."
mkdir -p patches
mv -f bounty_combat_patch.py patches/ 2>/dev/null || true
mv -f bounty_wire_patch.py patches/ 2>/dev/null || true
mv -f drop1_apply_patches.py patches/ 2>/dev/null || true
mv -f evasive_engine_patch.py patches/ 2>/dev/null || true
mv -f evasive_parser_patch.py patches/ 2>/dev/null || true
mv -f force_wire_patch.py patches/ 2>/dev/null || true
mv -f hazard_engine_patch.py patches/ 2>/dev/null || true
mv -f hazard_parser_patch.py patches/ 2>/dev/null || true
mv -f mission_wire_patch.py patches/ 2>/dev/null || true
mv -f tailing_apply_patch.py patches/ 2>/dev/null || true
mv -f tailing_parser_patch.py patches/ 2>/dev/null || true
mv -f db/database_traffic_patch.py patches/ 2>/dev/null || true
mv -f db/mission_db_patch.py patches/ 2>/dev/null || true
echo "  Moved 13 patch scripts to patches/"

echo ""
echo "=== Cleanup complete ==="
echo "  Removed:  ~1,950 lines of dead code"
echo "  Removed:  5 backup files + 1 duplicate"
echo "  Archived: 13 patch scripts to patches/"
echo ""
echo "Optional: add these to .gitignore:"
echo "  __pycache__/"
echo "  venv/"
echo "  *.pyc"
echo "  SW_MUSH.db"
