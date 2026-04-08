#!/usr/bin/env python3
"""
patches/patch_game_server_crafting.py — Wire crafting commands into game_server.py

Inserts the crafting import and register_crafting_commands() call alongside
the existing command registration block.

Run from project root:
    python patches/patch_game_server_crafting.py
"""

import sys
import shutil
import ast
import os

TARGET = os.path.join("server", "game_server.py")
BACKUP = TARGET + ".bak_pre_crafting"

# ---------------------------------------------------------------------------

with open(TARGET, "r", encoding="utf-8") as fh:
    src = fh.read()

orig_src = src
changes = []

# ---------------------------------------------------------------------------
# 1. Import
# ---------------------------------------------------------------------------

IMPORT_NEW = "from parser.crafting_commands import register_crafting_commands"

if IMPORT_NEW in src:
    print("[OK] Crafting import already present.")
else:
    # Insert after the last register_*_commands import we can find
    # Try known anchors in order of preference
    import_anchors = [
        "from parser.sabacc_commands import register_sabacc_commands",
        "from parser.cp_commands import register_cp_commands",
        "from parser.entertainer_commands import register_entertainer_commands",
        "from parser.medical_commands import register_medical_commands",
        "from parser.channel_commands import register_channel_commands",
        "from parser.party_commands import register_party_commands",
    ]
    inserted = False
    for anchor in import_anchors:
        # Try exact then with CRLF
        for sep in ["\n", "\r\n"]:
            if anchor + sep in src:
                src = src.replace(anchor + sep, anchor + sep + IMPORT_NEW + sep, 1)
                print(f"[OK] Inserted crafting import after: {anchor[:60]}")
                inserted = True
                changes.append("import")
                break
        if inserted:
            break

    if not inserted:
        print("[WARN] Could not find a suitable import anchor.")
        print(f"       Manually add to game_server.py imports: {IMPORT_NEW}")

# ---------------------------------------------------------------------------
# 2. Registration call
# ---------------------------------------------------------------------------

REGISTER_CALL = "    register_crafting_commands(self.commands)"

if REGISTER_CALL in src:
    print("[OK] register_crafting_commands call already present.")
else:
    # Try to insert after the sabacc, cp, or entertainer registration call
    register_anchors = [
        "register_sabacc_commands(self.commands)",
        "register_cp_commands(self.commands)",
        "register_entertainer_commands(self.commands)",
        "register_medical_commands(self.commands)",
        "register_channel_commands(self.commands)",
        "register_party_commands(self.commands)",
    ]
    inserted = False
    for anchor_core in register_anchors:
        # Full indented form
        anchor = "    " + anchor_core
        for sep in ["\n", "\r\n"]:
            if anchor + sep in src:
                src = src.replace(
                    anchor + sep,
                    anchor + sep + REGISTER_CALL + sep,
                    1
                )
                print(f"[OK] Inserted register_crafting_commands after: {anchor_core}")
                inserted = True
                changes.append("register")
                break
        if inserted:
            break

    if not inserted:
        print("[WARN] Could not find registration anchor.")
        print(f"       Manually add to game_server.py _register_commands(): {REGISTER_CALL}")

# ---------------------------------------------------------------------------
# Validate + write
# ---------------------------------------------------------------------------

if src == orig_src:
    print("[INFO] No changes were made (already wired or anchors not found).")
    sys.exit(0)

try:
    ast.parse(src)
    print("[OK] AST validation passed.")
except SyntaxError as e:
    print(f"[ERROR] Syntax error after patch: {e}")
    print("        Original file NOT modified.")
    sys.exit(1)

shutil.copy(TARGET, BACKUP)
print(f"[OK] Backup created: {BACKUP}")

with open(TARGET, "w", encoding="utf-8") as fh:
    fh.write(src)

print(f"[OK] Written: {TARGET}")
print("\nChanges applied:", ", ".join(changes) if changes else "none")
print("Crafting commands wired. Available: survey, resources, schematics, craft, experiment, teach")
