#!/usr/bin/env python3
"""
patches/patch_npc_trainer_hook.py — Wire crafting trainer hook into TalkCommand

When a player talks to Kayson or Heist (or any future NPC marked as a
schematic trainer in schematics.yaml), TalkCommand calls handle_trainer_teach()
which grants all schematics for that trainer in a single interaction.

The hook fires AFTER the NPC is resolved and BEFORE the Persuasion check /
AI dialogue call, so trainers always teach regardless of the player's
Persuasion skill. This is intentional — schematic access shouldn't be gated
behind a social skill check.

Hook insertion strategy:
  - Find the block where npc_name is resolved from the room
  - Insert a trainer check immediately after npc resolution
  - If trainer returns True (schematics were taught), skip the AI dialogue call

Anchor search order (most to least specific):
  1. The block that calls brain.dialogue() or npc_brain.dialogue()
  2. The persuasion check block entry
  3. The npc_name assignment line

Run from project root:
    python patches/patch_npc_trainer_hook.py
"""

import sys
import shutil
import ast
import os
import re

TARGET = os.path.join("parser", "npc_commands.py")
BACKUP = TARGET + ".bak_pre_trainer"

# ---------------------------------------------------------------------------

with open(TARGET, "r", encoding="utf-8") as fh:
    src = fh.read()

orig_src = src
changes = []

# ---------------------------------------------------------------------------
# 1. Add import for handle_trainer_teach at top of file
# ---------------------------------------------------------------------------

IMPORT_LINE = "from parser.crafting_commands import handle_trainer_teach"

if IMPORT_LINE in src:
    print("[OK] handle_trainer_teach import already present.")
else:
    # Insert after existing parser imports or at the top of the import block
    import_anchors = [
        "from parser.",
        "from engine.skill_checks import perform_skill_check",
        "from engine.",
        "from ai.npc_brain import",
        "import ",
    ]
    inserted = False
    for anchor in import_anchors:
        # Find first occurrence of this import style
        match = None
        for line in src.splitlines():
            if line.startswith(anchor):
                match = line
                break
        if match:
            for sep in ["\n", "\r\n"]:
                if match + sep in src:
                    src = src.replace(match + sep, match + sep + IMPORT_LINE + sep, 1)
                    print(f"[OK] Added trainer import after: {match[:60]}")
                    inserted = True
                    changes.append("import")
                    break
        if inserted:
            break

    if not inserted:
        print("[WARN] Could not insert import automatically.")
        print(f"       Manually add near top of {TARGET}: {IMPORT_LINE}")

# ---------------------------------------------------------------------------
# 2. Insert trainer check into TalkCommand.execute()
#
# The hook needs to go AFTER npc_name is resolved but BEFORE the
# persuasion/dialogue block. We look for the pattern where the NPC name
# variable is assigned and then the dialogue is called.
#
# We want to insert:
#
#     # Crafting trainer hook — check before Persuasion/AI dialogue
#     if await handle_trainer_teach(ctx, npc_name):
#         return
#
# Anchors tried in order:
#   A) Right before the GREETING_PATTERNS / casual check
#   B) Right before the persuasion skill check call
#   C) Right before the brain.dialogue() call
#   D) Right before await dialogue(
# ---------------------------------------------------------------------------

TRAINER_BLOCK = """\
        # Crafting trainer hook — fires before Persuasion gate
        # If this NPC is a schematic trainer, teach and return immediately.
        if await handle_trainer_teach(ctx, npc_name):
            return
"""

if "handle_trainer_teach(ctx, npc_name)" in src:
    print("[OK] Trainer hook already present in TalkCommand.")
else:
    anchor_candidates = [
        # Most specific: right before the GREETING_PATTERNS check
        "GREETING_PATTERNS",
        # Right before persuasion check
        "perform_skill_check(char",
        "perform_skill_check(ctx.character",
        # Right before NPC brain call
        "brain.dialogue(",
        "npc_brain.dialogue(",
        "await dialogue(",
        # Generic: right before the big if/else that handles the persuasion result
        "persuasion_context",
    ]

    inserted = False
    for anchor_text in anchor_candidates:
        # Find the line containing this anchor inside TalkCommand.execute
        # We need to find it in context (inside the class method)
        pattern = re.compile(r'( {8,12}.*' + re.escape(anchor_text) + r'.*\n)', re.MULTILINE)
        matches = list(pattern.finditer(src))
        if not matches:
            continue

        # Use the first match
        match = matches[0]
        anchor_line = match.group(1)

        if TRAINER_BLOCK.strip() in src:
            break  # already there somehow

        src = src.replace(anchor_line, TRAINER_BLOCK + anchor_line, 1)
        print(f"[OK] Inserted trainer hook before anchor: {anchor_text!r}")
        inserted = True
        changes.append("trainer_hook")
        break

    if not inserted:
        print("[WARN] Could not find a suitable anchor in TalkCommand.execute().")
        print("       Manually insert the following block in TalkCommand.execute()")
        print("       after npc_name is resolved, before the persuasion check:")
        print()
        print(TRAINER_BLOCK)
        print()
        print("       Also add this import near the top of the file:")
        print(f"       {IMPORT_LINE}")

# ---------------------------------------------------------------------------
# Validate + write
# ---------------------------------------------------------------------------

if src == orig_src:
    print("[INFO] No changes made (already wired, or anchors not found).")
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
print("\nChanges:", ", ".join(changes) if changes else "none")
print(
    "\nTrainer hook wired. Players can now learn schematics via:\n"
    "  talk kayson  →  teaches all weapon schematics\n"
    "  talk heist   →  teaches all consumable schematics"
)
