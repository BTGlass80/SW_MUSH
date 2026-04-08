# -*- coding: utf-8 -*-
"""
Patch: Wire ambient events into game_server.py tick loop.

Adds:
  - Ambient event tick call after bounty board tick in _game_tick_loop

Usage:
  python patches/ambient_wire_patch.py

Creates a backup before modifying. Validates syntax via ast.parse().
"""
import ast
import shutil
import sys
from pathlib import Path

TARGET = Path("server/game_server.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from project root.")
    sys.exit(1)

# Read source
src = TARGET.read_text(encoding="utf-8")

# Backup
bak = TARGET.with_suffix(".py.ambient_bak")
shutil.copy2(TARGET, bak)
print(f"Backup: {bak}")

changes = 0

# ── Add ambient tick to _game_tick_loop ──
# Anchor: the bounty board tick block (last block in the tick loop)

ANCHOR_PRIMARY = (
    '            try:\n'
    '                from engine.bounty_board import get_bounty_board\n'
    '                bboard = get_bounty_board()\n'
    '                await bboard.ensure_loaded(self.db)\n'
    '            except Exception:\n'
    '                log.debug("Bounty board tick skipped", exc_info=True)'
)

AMBIENT_BLOCK = (
    '\n'
    '            # ── Ambient room events ──\n'
    '            try:\n'
    '                from engine.ambient_events import get_ambient_manager\n'
    '                await get_ambient_manager().tick(self.db, self.session_mgr)\n'
    '            except Exception:\n'
    '                log.debug("Ambient events tick skipped", exc_info=True)'
)

if "get_ambient_manager" in src:
    print("✓ Ambient tick already present — skipping.")
else:
    if ANCHOR_PRIMARY in src:
        src = src.replace(
            ANCHOR_PRIMARY,
            ANCHOR_PRIMARY + AMBIENT_BLOCK,
            1,
        )
        print("  + Ambient tick inserted after bounty board tick.")
        changes += 1
    else:
        # Try with \r\n line endings (Windows)
        anchor_crlf = ANCHOR_PRIMARY.replace('\n', '\r\n')
        ambient_crlf = AMBIENT_BLOCK.replace('\n', '\r\n')
        if anchor_crlf in src:
            src = src.replace(
                anchor_crlf,
                anchor_crlf + ambient_crlf,
                1,
            )
            print("  + Ambient tick inserted after bounty board tick (CRLF).")
            changes += 1
        else:
            print("WARNING: Could not find bounty board tick anchor.")
            print("  Expected block starting with:")
            print('    try:')
            print('        from engine.bounty_board import get_bounty_board')
            print()
            print("  Add manually to _game_tick_loop after the bounty board block:")
            print()
            print('            # ── Ambient room events ──')
            print('            try:')
            print('                from engine.ambient_events import get_ambient_manager')
            print('                await get_ambient_manager().tick(self.db, self.session_mgr)')
            print('            except Exception:')
            print('                log.debug("Ambient events tick skipped", exc_info=True)')

# ── Syntax validation ──
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"\nERROR: Patched game_server.py failed syntax check: {e}")
    print(f"Restoring from backup: {bak}")
    shutil.copy2(bak, TARGET)
    sys.exit(1)

if changes > 0:
    TARGET.write_text(src, encoding="utf-8")
    print(f"\n✓ game_server.py patched ({changes} change(s)).")
else:
    print("\nNo changes needed.")

print()
print("Ambient events system ready. Files needed:")
print("  engine/ambient_events.py   (AmbientEventManager)")
print("  data/ambient_events.yaml   (static flavor text pool)")
print("Restart the server to activate.")
