#!/usr/bin/env python3
"""
force_wire_patch.py
Patches game_server.py to register Force commands alongside combat commands.
Run once from the project root: python3 force_wire_patch.py

What it does:
  1. Finds the line that calls register_combat_commands(registry) in game_server.py
  2. Inserts register_force_commands(registry) immediately after it
  3. Adds the import for register_force_commands if not already present
  4. Validates syntax before writing
"""
import ast
import re
import sys

TARGET = "server/game_server.py"

def read(path):
    with open(path, "r") as f:
        return f.read()

def write(path, content):
    with open(path, "w") as f:
        f.write(content)

def apply(path, old, new, label):
    src = read(path)
    if old not in src:
        print(f"  SKIP ({label}): anchor not found — may already be patched")
        return
    result = src.replace(old, new, 1)
    try:
        ast.parse(result)
    except SyntaxError as e:
        print(f"  ERR ({label}): syntax error after patch — {e}")
        sys.exit(1)
    write(path, result)
    print(f"  OK : {label}")

print(f"\n── Patching {TARGET} ──────────────────────────────────────────────")

# 1. Add import alongside the combat_commands import
apply(
    TARGET,
    "from parser.combat_commands import register_combat_commands",
    "from parser.combat_commands import register_combat_commands\n"
    "from parser.force_commands import register_force_commands",
    "add force_commands import",
)

# 2. Register force commands right after combat commands
apply(
    TARGET,
    "register_combat_commands(registry)",
    "register_combat_commands(registry)\n"
    "        register_force_commands(registry)",
    "register_force_commands call",
)

print(f"\nPatch complete. Force commands are now registered.")
print("No DB migration needed — uses existing force_points, dark_side_points, "
      "control, sense, alter columns.\n")
