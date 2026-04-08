#!/usr/bin/env python3
"""
bounty_npcconfig_fix_patch.py
-----------------------------
Fixes: NPCConfig.__init__() got an unexpected keyword argument 'hostile'

The bounty board's generate_bounty() passes hostile=True and
combat_behavior=behavior to NPCConfig(), but those aren't fields on the
dataclass. They need to be set on the dict AFTER to_dict(), which is the
same pattern used by npc_commands.py's @npc hostile / @npc behavior.

Run from the SW_MUSH project root:
    python3 patches/bounty_npcconfig_fix_patch.py

Safe to re-run: skips if already fixed.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("engine/bounty_board.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

# ── Check if already fixed ──
if "hostile=True" not in src:
    print("✓ bounty_board.py does not contain hostile=True — already fixed or different code.")
    sys.exit(0)

# ── The broken code (anchor) ──
OLD = '''    config = NPCConfig(
        personality=f"A desperate fugitive with nothing to lose.",
        fallback_lines=[
            f"{target_name} watches you warily.",
            f"{target_name} edges toward the exit.",
            f"{target_name} says nothing, eyes darting around.",
        ],
        hostile=True,
        combat_behavior=behavior,
    )
    ai_cfg = config.to_dict()
    ai_cfg["weapon"] = weapon_key
    ai_cfg["is_bounty_target"] = True   # Flag for cleanup on collection'''

# ── The fixed code (replacement) ──
NEW = '''    config = NPCConfig(
        personality=f"A desperate fugitive with nothing to lose.",
        fallback_lines=[
            f"{target_name} watches you warily.",
            f"{target_name} edges toward the exit.",
            f"{target_name} says nothing, eyes darting around.",
        ],
    )
    ai_cfg = config.to_dict()
    ai_cfg["hostile"] = True
    ai_cfg["combat_behavior"] = behavior
    ai_cfg["weapon"] = weapon_key
    ai_cfg["is_bounty_target"] = True   # Flag for cleanup on collection'''

if OLD not in src:
    print("ERROR: Could not find exact anchor block in bounty_board.py.")
    print("The code may have already been partially modified.")
    print("Look for the NPCConfig() call in generate_bounty() and remove")
    print("hostile=True and combat_behavior=behavior from the constructor,")
    print("then add them as dict keys on ai_cfg after to_dict().")
    sys.exit(1)

src = src.replace(OLD, NEW, 1)

# ── Syntax validation ──
try:
    ast.parse(src)
except SyntaxError as e:
    print(f"ERROR: Patched file failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("✓ bounty_board.py patched: moved hostile/combat_behavior out of NPCConfig constructor.")
print("  Bounty NPC generation should now work correctly.")
