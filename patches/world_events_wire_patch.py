# -*- coding: utf-8 -*-
"""
Patch: Wire world events into game_server.py tick loop.

Adds the world events tick call after the ambient events tick.
Requires: ambient_wire_patch.py applied first (provides the anchor).

Usage:
  python patches/world_events_wire_patch.py

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

src = TARGET.read_text(encoding="utf-8")

bak = TARGET.with_suffix(".py.worldevents_bak")
shutil.copy2(TARGET, bak)
print(f"Backup: {bak}")

changes = 0

# ── Add world events tick after ambient events tick ──

WORLD_EVENTS_BLOCK = (
    '\n'
    '            # ── World events lifecycle ──\n'
    '            try:\n'
    '                from engine.world_events import get_world_event_manager\n'
    '                await get_world_event_manager().tick(self.db, self.session_mgr)\n'
    '            except Exception:\n'
    '                log.debug("World events tick skipped", exc_info=True)'
)

if "get_world_event_manager" in src:
    print("✓ World events tick already present — skipping.")
else:
    # Primary anchor: after ambient events tick block
    ANCHOR_AMBIENT = (
        '            try:\n'
        '                from engine.ambient_events import get_ambient_manager\n'
        '                await get_ambient_manager().tick(self.db, self.session_mgr)\n'
        '            except Exception:\n'
        '                log.debug("Ambient events tick skipped", exc_info=True)'
    )

    # Fallback anchor: after bounty board tick (if ambient patch not yet applied)
    ANCHOR_BOUNTY = (
        '            try:\n'
        '                from engine.bounty_board import get_bounty_board\n'
        '                bboard = get_bounty_board()\n'
        '                await bboard.ensure_loaded(self.db)\n'
        '            except Exception:\n'
        '                log.debug("Bounty board tick skipped", exc_info=True)'
    )

    applied = False
    for anchor_name, anchor in [("ambient events tick", ANCHOR_AMBIENT),
                                 ("bounty board tick", ANCHOR_BOUNTY)]:
        if anchor in src:
            src = src.replace(anchor, anchor + WORLD_EVENTS_BLOCK, 1)
            print(f"  + World events tick inserted after {anchor_name}.")
            changes += 1
            applied = True
            break
        # Try CRLF
        anchor_crlf = anchor.replace('\n', '\r\n')
        block_crlf = WORLD_EVENTS_BLOCK.replace('\n', '\r\n')
        if anchor_crlf in src:
            src = src.replace(anchor_crlf, anchor_crlf + block_crlf, 1)
            print(f"  + World events tick inserted after {anchor_name} (CRLF).")
            changes += 1
            applied = True
            break

    if not applied:
        print("WARNING: Could not find anchor. Add manually to _game_tick_loop:")
        print()
        print('            # ── World events lifecycle ──')
        print('            try:')
        print('                from engine.world_events import get_world_event_manager')
        print('                await get_world_event_manager().tick(self.db, self.session_mgr)')
        print('            except Exception:')
        print('                log.debug("World events tick skipped", exc_info=True)')

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
print("World events system ready. File needed:")
print("  engine/world_events.py   (WorldEventManager)")
print("Restart the server to activate.")
