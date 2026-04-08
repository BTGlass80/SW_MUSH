#!/usr/bin/env python3
"""
fix_initiative_0d_patch.py
--------------------------
Fixes: Initiative always rolling 0D for all characters.

Root cause: roll_initiative() calls get_skill_pool("perception"),
but "perception" is an ATTRIBUTE, not a skill. The SkillRegistry
doesn't have an entry for "perception" itself (it has skills UNDER
perception like bargain, command, con, etc.), so get_skill_pool()
returns DicePool(0, 0).

Fix: Use get_attribute("perception") directly, which reads from
the Character dataclass field.

Run from the SW_MUSH project root:
    python3 patches/fix_initiative_0d_patch.py
"""

import ast
import sys
from pathlib import Path

TARGET = Path("engine/combat.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")

# ── The bug ──
OLD = '            pool = c.char.get_skill_pool("perception", self.skill_reg)'

# ── The fix ──
NEW = '            pool = c.char.get_attribute("perception")'

if OLD not in src:
    # Check if already fixed
    if 'get_attribute("perception")' in src:
        print("✓ Already fixed — get_attribute('perception') found.")
        sys.exit(0)
    else:
        print("ERROR: Could not find the initiative anchor in combat.py.")
        print(f"  Expected: {OLD}")
        print("  Fix manually: change get_skill_pool to get_attribute")
        sys.exit(1)

src = src.replace(OLD, NEW, 1)

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"ERROR: Syntax check failed: {e}")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print("✓ combat.py fixed: initiative now uses get_attribute('perception')")
print("  All characters will roll their Perception attribute for initiative.")
