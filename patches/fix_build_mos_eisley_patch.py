#!/usr/bin/env python3
"""
fix_build_mos_eisley_patch.py
-----------------------------
Fixes build_mos_eisley.py for:

1. EXITS list: Renames duplicate reverse directions on hub rooms so
   each exit has a unique direction label. E.g. Spaceport Row won't have
   three "west" exits — they become "west to Bay 86", "west to Bay 91", etc.

2. Ponda Baba's Associate: Adds missing kno/mec/tec attributes so
   initiative doesn't roll 0D.

3. Seed room link conflicts: room 7 and 8 already get "south" from the
   EXITS list, so seed links now use distinct names.

Run from the SW_MUSH project root:
    python3 patches/fix_build_mos_eisley_patch.py

Safe to re-run.
"""

import ast
import sys
from pathlib import Path

TARGET = Path("build_mos_eisley.py")

if not TARGET.exists():
    print(f"ERROR: {TARGET} not found. Run from the SW_MUSH project root.")
    sys.exit(1)

src = TARGET.read_text(encoding="utf-8")
original = src  # keep for comparison


# ══════════════════════════════════════════════════════════════
#  FIX 1: EXITS list — deduplicate reverse directions
# ══════════════════════════════════════════════════════════════

OLD_EXITS = '''EXITS = [
    (0, 1, "down", "up"),         (0, 7, "north", "south"),
    (2, 7, "east", "west"),       (2, 0, "south", "north"),
    (3, 7, "northwest", "southeast"), (4, 7, "west", "east"),
    (5, 7, "east", "west"),       (6, 10, "east", "west"),
    (7, 8, "north", "south"),     (8, 9, "north", "south"),
    (9, 10, "north", "south"),    (8, 11, "south", "north"),
    (12, 8, "east", "west"),      (12, 13, "down", "up"),
    (13, 14, "west", "east"),     (15, 8, "north", "south"),
    (16, 8, "south", "north"),    (17, 7, "south", "north"),
    (18, 8, "southeast", "northwest"), (18, 19, "in", "out"),
    (20, 9, "east", "west"),      (21, 9, "west", "east"),
    (22, 9, "south", "north"),    (23, 22, "north", "south"),
    (24, 9, "northwest", "southeast"), (25, 7, "east", "west"),
    (26, 7, "north", "south"),    (27, 8, "east", "west"),
    (28, 8, "northeast", "southwest"), (29, 8, "west", "east"),
    (30, 10, "south", "north"),   (6, 30, "south", "north"),
    (31, 11, "north", "south"),   (31, 32, "up", "down"),
    (33, 8, "north", "south"),    (34, 11, "east", "west"),
    (35, 9, "east", "west"),      (36, 10, "east", "west"),
    (37, 8, "north", "south"),    (38, 11, "west", "east"),
    (39, 10, "north", "south"),
]'''

# New EXITS with unique reverse directions on hub rooms.
# Only the colliding reverse directions are renamed.
# Format: "direction to <short source room name>"
NEW_EXITS = '''EXITS = [
    # -- Docking Bay 94 connections --
    (0, 1, "down", "up"),
    (0, 7, "north", "south to Bay 94"),
    (2, 7, "east", "west to Bay 86"),
    (2, 0, "south", "north to Bay 86"),
    # -- Other bays to Spaceport Row --
    (3, 7, "northwest", "southeast"),
    (4, 7, "west", "east"),
    (5, 7, "east", "west to Bay 91"),
    # -- Bay 95 to Outer Curve --
    (6, 10, "east", "west to Bay 95"),
    # -- Spaceport Row <-> Market Row --
    (7, 8, "north", "south to Spaceport"),
    # -- Market Row <-> Inner Curve --
    (8, 9, "north", "south to Market"),
    # -- Inner Curve <-> Outer Curve --
    (9, 10, "north", "south to Inner Curve"),
    # -- Market Row <-> Kerner Plaza --
    (8, 11, "south", "north"),
    # -- Cantina --
    (12, 8, "east", "west to Cantina"),
    (12, 13, "down", "up"),
    (13, 14, "west", "east"),
    # -- General Store -> Market --
    (15, 8, "north", "south to General Store"),
    # -- Dim-U Monastery -> Market --
    (16, 8, "south", "north to Monastery"),
    # -- Spacers Quarters -> Spaceport Row --
    (17, 7, "south", "north to Quarters"),
    # -- Jabba's --
    (18, 8, "southeast", "northwest"),
    (18, 19, "in", "out"),
    # -- Government District --
    (20, 9, "east", "west to Prefect"),
    (21, 9, "west", "east"),
    (22, 9, "south", "north to Gov District"),
    (23, 22, "north", "south to Bay 35"),
    # -- Tower --
    (24, 9, "northwest", "southeast"),
    # -- Med Center -> Spaceport Row --
    (25, 7, "east", "west to Med Center"),
    # -- Warehouse Row -> Spaceport Row --
    (26, 7, "north", "south to Warehouses"),
    # -- Arms Dealer -> Market --
    (27, 8, "east", "west to Arms Dealer"),
    # -- Scrap Yard / Dewback Stable -> Market --
    (28, 8, "northeast", "southwest"),
    (29, 8, "west", "east"),
    # -- Docking Bay 96 <-> Outer Curve --
    (30, 10, "south", "north"),
    (6, 30, "south", "north"),
    # -- Lucky Despot -> Kerner Plaza --
    (31, 11, "north", "south"),
    (31, 32, "up", "down"),
    # -- Repair Shop -> Market --
    (33, 8, "north", "south to Repair Shop"),
    # -- Bay 92 -> Kerner Plaza --
    (34, 11, "east", "west"),
    # -- Jawa Trader -> Inner Curve --
    (35, 9, "east", "west to Jawa Trader"),
    # -- Alley -> Outer Curve --
    (36, 10, "east", "west to Alley"),
    # -- Desert Edge -> Market --
    (37, 8, "north", "south to Desert"),
    # -- Ithorian Garden -> Kerner Plaza --
    (38, 11, "west", "east"),
    # -- Notsub Shipping -> Outer Curve --
    (39, 10, "north", "south to Notsub"),
]'''

if OLD_EXITS in src:
    src = src.replace(OLD_EXITS, NEW_EXITS, 1)
    print("  FIXED: EXITS list — unique reverse directions on hub rooms")
else:
    print("  SKIP: EXITS list anchor not found (may already be patched)")


# ══════════════════════════════════════════════════════════════
#  FIX 2: Ponda Baba's Associate — missing attributes
# ══════════════════════════════════════════════════════════════

OLD_PONDA = '''    ("Ponda Baba's Associate", 13, "Aqualish",
     "A scarred Aqualish thug hunched over a drink, watching the room with hostility.",
     _sheet(dex="3D+2", per="2D+1", stre="4D",
            skills={"blaster": "4D+2", "brawling": "5D", "dodge": "4D",
                    "melee combat": "4D+1", "intimidation": "3D+2"},
            weapon="vibroblade", species="Aqualish"),'''

NEW_PONDA = '''    ("Ponda Baba's Associate", 13, "Aqualish",
     "A scarred Aqualish thug hunched over a drink, watching the room with hostility.",
     _sheet(dex="3D+2", kno="2D", mec="2D", per="2D+1", stre="4D", tec="2D",
            skills={"blaster": "4D+2", "brawling": "5D", "dodge": "4D",
                    "melee combat": "4D+1", "intimidation": "3D+2"},
            weapon="vibroblade", species="Aqualish"),'''

if OLD_PONDA in src:
    src = src.replace(OLD_PONDA, NEW_PONDA, 1)
    print("  FIXED: Ponda Baba's Associate — added kno/mec/tec attributes")
else:
    print("  SKIP: Ponda Baba anchor not found (may already be patched)")


# ══════════════════════════════════════════════════════════════
#  FIX 3: Seed room links — avoid direction collisions
#  Room 7 already has "south to Bay 94" and "south to Warehouses"
#  Room 8 already has "south to Spaceport" etc.
#  Seed links use the seed room name for clarity.
# ══════════════════════════════════════════════════════════════

OLD_SEED = '''    await db.create_exit(1, spaceport_row_id, "north")
    await db.create_exit(spaceport_row_id, 1, "south")
    await db.create_exit(2, market_id, "north")
    await db.create_exit(market_id, 2, "south")
    await db.create_exit(3, cantina_entrance_id, "east")
    await db.create_exit(cantina_entrance_id, 3, "west")'''

NEW_SEED = '''    await db.create_exit(1, spaceport_row_id, "north")
    await db.create_exit(spaceport_row_id, 1, "south to Landing Pad")
    await db.create_exit(2, market_id, "north")
    await db.create_exit(market_id, 2, "south to Street")
    await db.create_exit(3, cantina_entrance_id, "east")
    await db.create_exit(cantina_entrance_id, 3, "west")'''

if OLD_SEED in src:
    src = src.replace(OLD_SEED, NEW_SEED, 1)
    print("  FIXED: Seed room links — unique direction names")
elif 'await db.create_exit(spaceport_row_id, 1, "south")' in src:
    # Partial match — the await line might be split differently
    src = src.replace(
        'await db.create_exit(spaceport_row_id, 1, "south")',
        'await db.create_exit(spaceport_row_id, 1, "south to Landing Pad")',
        1
    )
    src = src.replace(
        'await db.create_exit(market_id, 2, "south")',
        'await db.create_exit(market_id, 2, "south to Street")',
        1
    )
    print("  FIXED: Seed room links (individual replacements)")
else:
    print("  SKIP: Seed room link anchor not found")


# ══════════════════════════════════════════════════════════════
#  Syntax validation and write
# ══════════════════════════════════════════════════════════════

if src == original:
    print("\n  No changes needed — build_mos_eisley.py looks clean.")
    sys.exit(0)

try:
    ast.parse(src)
except SyntaxError as e:
    print(f"\nERROR: Patched file failed syntax check: {e}")
    print("Original file unchanged.")
    sys.exit(1)

TARGET.write_text(src, encoding="utf-8")
print(f"\n✓ build_mos_eisley.py patched successfully.")
print("  Delete sw_mush.db and restart to rebuild the world.")
