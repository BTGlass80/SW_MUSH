#!/usr/bin/env python3
"""
force_wire_patch.py
-------------------
Wires register_force_commands() into game_server.py.

The import already exists; this patch adds the missing call in the
command registration block inside GameServer.__init__().

Run from the SW_MUSH project root:
    python3 force_wire_patch.py

Safe to re-run: skips if the call is already present.
"""

import ast
import re
import sys
from pathlib import Path

TARGET = Path("server/game_server.py")

# ── Sanity checks ──────────────────────────────────────────────────────────────

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

source = TARGET.read_text(encoding="utf-8")

# ── Already patched? ───────────────────────────────────────────────────────────

if "register_force_commands(" in source:
    print("✓ register_force_commands() already present — nothing to do.")
    sys.exit(0)

# ── Verify the import exists ───────────────────────────────────────────────────

if "from parser.force_commands import register_force_commands" not in source:
    print("ERROR: import for register_force_commands not found in game_server.py.")
    print("Expected: from parser.force_commands import register_force_commands")
    print("Add that import first, then re-run this patch.")
    sys.exit(1)

# ── Locate the anchor line ─────────────────────────────────────────────────────
#
# The registration block ends with register_crew_commands(self.registry).
# We insert register_force_commands(self.registry) immediately after it.

ANCHOR = "        register_crew_commands(self.registry)"
INSERT = "        register_force_commands(self.registry)"

if ANCHOR not in source:
    # Fallback: try inserting after register_space_commands
    ANCHOR = "        register_space_commands(self.registry)"
    if ANCHOR not in source:
        print("ERROR: Could not find anchor line in game_server.py.")
        print("Expected one of:")
        print("  register_crew_commands(self.registry)")
        print("  register_space_commands(self.registry)")
        print("Please add the following line manually after the existing")
        print("register_*_commands() calls in GameServer.__init__():")
        print(f"\n    {INSERT.strip()}\n")
        sys.exit(1)

patched = source.replace(
    ANCHOR,
    f"{ANCHOR}\n{INSERT}",
    1  # replace only the first occurrence
)

# ── Syntax validation ──────────────────────────────────────────────────────────

try:
    ast.parse(patched)
except SyntaxError as e:
    print(f"ERROR: Patched source failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

# ── Write ──────────────────────────────────────────────────────────────────────

# Backup original
backup = TARGET.with_suffix(".py.bak")
backup.write_text(source, encoding="utf-8")
print(f"  Backup written → {backup}")

TARGET.write_text(patched, encoding="utf-8")
print(f"✓ Patched {TARGET}")
print(f"  Added: {INSERT.strip()}")
print()
print("Force commands are now registered. Restart main.py to activate.")
print("Commands available: force <power> [target], powers, forcestatus")
