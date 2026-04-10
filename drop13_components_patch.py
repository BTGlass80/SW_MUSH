#!/usr/bin/env python3
"""
drop13_components_patch.py  --  Space Expansion v2 Drop 13
Ship Component Schematics + Shipwright NPC

Changes:
  1. data/schematics.yaml   — 7 new ship component schematics (output_type: component)
  2. parser/crafting_commands.py — _deliver_item() handles output_type "component"
  3. data/npcs_gg7.yaml     — Venn Kator (Shipwright NPC) added to Docking Bay 94

Usage:
    python drop13_components_patch.py [--dry-run]

After applying, existing world builds do NOT need a full rebuild.
Venn Kator can be seeded into a running game via:
    python drop13_seed_venn.py   (standalone runner generated below)
"""

import ast
import os
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv
BASE = os.getcwd()

SCHEMATICS_PATH = os.path.join(BASE, "data", "schematics.yaml")
CRAFTING_PATH   = os.path.join(BASE, "parser", "crafting_commands.py")
NPCS_PATH       = os.path.join(BASE, "data", "npcs_gg7.yaml")


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    dst = path + ".bak_drop13"
    shutil.copy2(path, dst)
    print(f"  backup → {dst}")


def validate_py(content, label=""):
    try:
        ast.parse(content)
        print(f"  ✓ AST OK: {label}")
    except SyntaxError as e:
        print(f"  ✗ SYNTAX ERROR: {label}: {e}")
        lines = content.splitlines()
        for i in range(max(0, e.lineno-3), min(len(lines), e.lineno+2)):
            print(f"    {i+1}: {lines[i]}")
        sys.exit(1)


def patch(content, old, new, label, validate_fn=None):
    if old not in content:
        print(f"  ✗ ANCHOR NOT FOUND: {label}")
        sys.exit(1)
    result = content.replace(old, new, 1)
    if validate_fn:
        validate_fn(result, label)
    print(f"  ✓ PATCHED: {label}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Patch 1 — data/schematics.yaml
# 7 ship component schematics taught by Venn Kator (Drop 13)
# output_type: component  /  stat_target matches get_effective_stats() keys
# ══════════════════════════════════════════════════════════════════════════════

NEW_SCHEMATICS = """

  # ──────────────────────────────────────────────────────────────
  # SHIP COMPONENTS — Taught by Venn Kator at Docking Bay 94
  # Requires ship customization engine (Drop 12).
  # output_type: component produces a ship_component inventory item.
  # stat_target / stat_boost / cargo_weight feed get_effective_stats().
  # ──────────────────────────────────────────────────────────────

  - key: engine_booster_basic
    name: "Engine Booster (Basic)"
    skill_required: space_transports_repair
    difficulty: 16
    trainer_npc: Venn Kator
    components:
      - type: metal
        quantity: 4
        min_quality: 40
      - type: energy
        quantity: 3
        min_quality: 35
    output_type: component
    output_key: engine_booster_basic
    stat_target: speed
    stat_boost: 1
    cargo_weight: 20
    base_cost: 2000

  - key: shield_generator_mk2
    name: "Shield Generator Mk.II"
    skill_required: space_transports_repair
    difficulty: 18
    trainer_npc: Venn Kator
    components:
      - type: metal
        quantity: 3
        min_quality: 45
      - type: energy
        quantity: 4
        min_quality: 40
      - type: rare
        quantity: 1
        min_quality: 50
    output_type: component
    output_key: shield_generator_mk2
    stat_target: shields
    stat_boost: 1
    cargo_weight: 15
    base_cost: 3500

  - key: armor_plating_durasteel
    name: "Durasteel Armor Plating"
    skill_required: space_transports_repair
    difficulty: 14
    trainer_npc: Venn Kator
    components:
      - type: metal
        quantity: 6
        min_quality: 35
      - type: composite
        quantity: 2
        min_quality: 40
    output_type: component
    output_key: armor_plating_durasteel
    stat_target: hull
    stat_boost: 1
    cargo_weight: 20
    base_cost: 1800

  - key: sensor_suite_enhanced
    name: "Enhanced Sensor Suite"
    skill_required: space_transports_repair
    difficulty: 16
    trainer_npc: Venn Kator
    components:
      - type: energy
        quantity: 3
        min_quality: 45
      - type: rare
        quantity: 1
        min_quality: 55
    output_type: component
    output_key: sensor_suite_enhanced
    stat_target: sensors
    stat_boost: 1
    cargo_weight: 5
    base_cost: 2500

  - key: maneuvering_thrusters
    name: "Aftermarket Maneuvering Thrusters"
    skill_required: space_transports_repair
    difficulty: 18
    trainer_npc: Venn Kator
    components:
      - type: metal
        quantity: 3
        min_quality: 45
      - type: energy
        quantity: 3
        min_quality: 40
      - type: composite
        quantity: 1
        min_quality: 50
    output_type: component
    output_key: maneuvering_thrusters
    stat_target: maneuverability
    stat_boost: 1
    cargo_weight: 10
    base_cost: 3000

  - key: weapon_upgrade_fc
    name: "Weapon Fire Control Upgrade"
    skill_required: starship_weapon_repair
    difficulty: 18
    trainer_npc: Venn Kator
    components:
      - type: energy
        quantity: 2
        min_quality: 50
      - type: rare
        quantity: 1
        min_quality: 60
    output_type: component
    output_key: weapon_upgrade_fc
    stat_target: fire_control
    stat_boost: 1
    cargo_weight: 5
    base_cost: 3000

  - key: hyperdrive_tuning
    name: "Hyperdrive Tuning Kit"
    skill_required: space_transports_repair
    difficulty: 20
    trainer_npc: Venn Kator
    components:
      - type: energy
        quantity: 4
        min_quality: 50
      - type: rare
        quantity: 2
        min_quality: 60
    output_type: component
    output_key: hyperdrive_tuning
    stat_target: hyperdrive
    stat_boost: 1
    cargo_weight: 10
    base_cost: 4500
"""

# Anchor: end of the file (append after last schematic entry)
YAML_OLD_ANCHOR = """    output_type: consumable
    output_key: stimpack
    base_cost: 150"""

YAML_NEW_ANCHOR = """    output_type: consumable
    output_key: stimpack
    base_cost: 150""" + NEW_SCHEMATICS


# ══════════════════════════════════════════════════════════════════════════════
# Patch 2 — parser/crafting_commands.py
# Add output_type "component" case to _deliver_item()
# ══════════════════════════════════════════════════════════════════════════════

OLD_DELIVER_END = """    elif output_type == "consumable":
        attrs = char.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        consumables = attrs.setdefault("consumables", {})
        current = consumables.get(output_key, 0)
        consumables[output_key] = current + 1
        char["attributes"] = json.dumps(attrs)

        display_name = _CONSUMABLE_STATS.get(output_key, {}).get("name", output_key)
        await ctx.session.send_line(
            f"  The {display_name} has been added to your consumables. "
            f"(quality {quality:.0f}/100)"
        )"""

NEW_DELIVER_END = """    elif output_type == "consumable":
        attrs = char.get("attributes")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError):
                attrs = {}
        if not isinstance(attrs, dict):
            attrs = {}

        consumables = attrs.setdefault("consumables", {})
        current = consumables.get(output_key, 0)
        consumables[output_key] = current + 1
        char["attributes"] = json.dumps(attrs)

        display_name = _CONSUMABLE_STATS.get(output_key, {}).get("name", output_key)
        await ctx.session.send_line(
            f"  The {display_name} has been added to your consumables. "
            f"(quality {quality:.0f}/100)"
        )

    elif output_type == "component":
        # Ship component — stored as a dict in the character's inventory JSON list.
        # +ship/install reads items where item["type"] == "ship_component".
        # Fields: type, key, name, quality, stat_target, stat_boost,
        #         cargo_weight, craft_difficulty.
        inv_raw = char.get("inventory", "[]")
        try:
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
            if not isinstance(inv, list):
                inv = []
        except Exception:
            inv = []

        component_item = {
            "type":             "ship_component",
            "key":              output_key,
            "name":             schematic["name"],
            "quality":          round(quality, 1),
            "stat_target":      schematic.get("stat_target", ""),
            "stat_boost":       schematic.get("stat_boost", 1),
            "cargo_weight":     schematic.get("cargo_weight", 10),
            "craft_difficulty": schematic.get("difficulty", 16),
            "crafter":          crafter,
        }
        inv.append(component_item)
        char["inventory"] = json.dumps(inv)

        await ctx.session.send_line(
            f"  The {schematic['name']} has been added to your inventory as a "
            f"ship component. (quality {quality:.0f}/100)"
        )
        await ctx.session.send_line(
            f"  Use '+ship/install {schematic[\"name\"]}' while docked to install it."
        )"""


# ══════════════════════════════════════════════════════════════════════════════
# Patch 3 — data/npcs_gg7.yaml
# Add Venn Kator (Shipwright) at Docking Bay 94 - Pit Floor
# ══════════════════════════════════════════════════════════════════════════════

# Anchor: Kayson's entry (unique trainer NPC block we can insert before)
# We insert Venn Kator BEFORE Kayson so he's clearly grouped as a craftsman NPC.
VENN_KATOR_ENTRY = """
  - name: "Venn Kator"
    room: "Docking Bay 94 - Pit Floor"
    species: "Corellian Human"
    description: |
      A stocky Corellian man in his fifties, oil-stained coveralls rolled to the
      elbows. Calloused hands move with practiced economy across the hull plating
      of whatever ship he happens to be working on. A battered tool harness is
      strapped across his chest, each pocket packed with specialized instruments.
      His eyes are sharp — he notices exactly what needs fixing and exactly what
      someone's trying to hide.
    char_sheet:
      Dexterity: 2D
      Knowledge: 3D
      Mechanical: 4D
      Perception: 3D
      Strength: 2D+2
      Technical: 5D
      skills:
        space_transports_repair: "7D"
        starship_weapon_repair: "5D+2"
        capital_ship_repair: "5D"
        astrogation: "4D"
        bargain: "4D"
    ai_config:
      personality: gruff_expert
      trainer: true
      sell_items: false
      hostile: false
      dialog:
        - "Venn wipes his hands on a rag. 'You need something fixed or you just\
           here to watch?'"
        - "Venn squints at your ship. 'Whoever installed that motivator did it\
           wrong. I can see it from here.'"
        - "Venn crosses his arms. 'I've been modding ships since before the\
           Clone Wars. Talk to me when you have real parts.'"
        - "'Corellian Engineering — best in the galaxy. Everything else is\
           catching up.' He returns to his work."
        - "Venn taps the hull plating with a knuckle. 'You hear that? That's\
           a resonance problem. Costs you half a point of speed. Easy fix if\
           you've got the parts.'"
      teach_message: |
        Venn sets down his hydrospanner and studies you for a long moment.
        'All right. You've got the look of someone who actually wants to learn,
        not just someone who wants to watch. Pull up a crate.'
        He walks you through the schematics over the next hour — ship systems,
        modification tolerances, what fails first and why. You come away knowing
        things you didn't know you didn't know.
"""

NPC_YAML_OLD_ANCHOR = """  - name: "Kayson"
    room: "Kayson's Weapon Shop\""""

NPC_YAML_NEW_ANCHOR = VENN_KATOR_ENTRY + """
  - name: "Kayson"
    room: "Kayson's Weapon Shop\""""


# ══════════════════════════════════════════════════════════════════════════════
# Also generate a standalone seed script for live worlds
# ══════════════════════════════════════════════════════════════════════════════

SEED_SCRIPT = '''#!/usr/bin/env python3
"""
drop13_seed_venn.py  --  Seed Venn Kator into a running SW_MUSH world.

Run this ONCE on an existing live database to add Venn Kator without a
full world rebuild. Idempotent — checks if Venn already exists first.

Usage:
    python drop13_seed_venn.py
"""
import asyncio
import os
import sys

BASE = os.getcwd()
sys.path.insert(0, os.path.join(BASE, "repo", "SW_MUSH"))

DB_PATH = os.path.join(BASE, "repo", "SW_MUSH", "mush.db")


async def main():
    try:
        import aiosqlite
    except ImportError:
        print("ERROR: aiosqlite not installed. Run: pip install aiosqlite")
        sys.exit(1)

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row

        # Find Docking Bay 94 - Pit Floor
        rows = await (await conn.execute(
            "SELECT id, name FROM rooms WHERE name LIKE ? LIMIT 5",
            ("%Docking Bay 94%Pit%",)
        )).fetchall()

        if not rows:
            # Fallback: any Docking Bay 94 room
            rows = await (await conn.execute(
                "SELECT id, name FROM rooms WHERE name LIKE ? LIMIT 5",
                ("%Docking Bay 94%",)
            )).fetchall()

        if not rows:
            print("ERROR: No 'Docking Bay 94' room found. Has build_mos_eisley.py been run?")
            sys.exit(1)

        bay_room = rows[0]
        room_id = bay_room["id"]
        print(f"  Placing Venn Kator in: #{room_id} {bay_room['name']}")

        # Idempotent check
        existing = await (await conn.execute(
            "SELECT id FROM npcs WHERE name = ?", ("Venn Kator",)
        )).fetchone()
        if existing:
            print(f"  Venn Kator already exists (NPC #{existing['id']}). Skipping.")
            return

        import json
        sheet = {
            "Dexterity": "2D", "Knowledge": "3D",
            "Mechanical": "4D", "Perception": "3D",
            "Strength": "2D+2", "Technical": "5D",
            "skills": {
                "space_transports_repair": "7D",
                "starship_weapon_repair": "5D+2",
                "capital_ship_repair": "5D",
                "astrogation": "4D",
                "bargain": "4D",
            }
        }
        ai_cfg = {
            "personality": "gruff_expert",
            "trainer": True,
            "sell_items": False,
            "hostile": False,
            "dialog": [
                "Venn wipes his hands on a rag. 'You need something fixed or you just here to watch?'",
                "Venn squints at your ship. 'Whoever installed that motivator did it wrong. I can see it from here.'",
                "Venn crosses his arms. 'I\\'ve been modding ships since before the Clone Wars. Talk to me when you have real parts.'",
                "'Corellian Engineering — best in the galaxy. Everything else is catching up.' He returns to his work.",
                "Venn taps the hull plating with a knuckle. 'You hear that? That\\'s a resonance problem. Costs you half a point of speed.'",
            ],
            "teach_message": (
                "Venn sets down his hydrospanner and studies you for a long moment. "
                "'All right. You\\'ve got the look of someone who actually wants to learn, not just someone who wants to watch. "
                "Pull up a crate.' He walks you through the schematics over the next hour."
            ),
        }
        desc = (
            "A stocky Corellian man in his fifties, oil-stained coveralls rolled to the elbows. "
            "Calloused hands move with practiced economy across hull plating. "
            "A battered tool harness is strapped across his chest. "
            "His eyes are sharp — he notices exactly what needs fixing and exactly what someone\\'s trying to hide."
        )

        cursor = await conn.execute(
            """INSERT INTO npcs (name, room_id, species, description, char_sheet_json, ai_config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            ("Venn Kator", room_id, "Corellian Human", desc,
             json.dumps(sheet), json.dumps(ai_cfg))
        )
        await conn.commit()
        print(f"  ✓ Venn Kator created (NPC #{cursor.lastrowid})")
        print(f"  Players can 'talk Venn Kator' to learn ship component schematics.")


if __name__ == "__main__":
    asyncio.run(main())
'''


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n=== Drop 13 — Ship Component Schematics + Shipwright NPC ===\n")
    if DRY_RUN:
        print("DRY RUN — no files modified.\n")

    # ── Patch 1: schematics.yaml ──────────────────────────────────────────────
    print("data/schematics.yaml:")
    yaml_content = read(SCHEMATICS_PATH)
    yaml_content = patch(yaml_content, YAML_OLD_ANCHOR, YAML_NEW_ANCHOR,
                         "7 ship component schematics")
    if not DRY_RUN:
        backup(SCHEMATICS_PATH)
        write(SCHEMATICS_PATH, yaml_content)
        print(f"  Written: {SCHEMATICS_PATH}")
    else:
        print("  (dry run)")

    # ── Patch 2: crafting_commands.py ─────────────────────────────────────────
    print("\nparser/crafting_commands.py:")
    craft_content = read(CRAFTING_PATH)
    craft_content = patch(craft_content, OLD_DELIVER_END, NEW_DELIVER_END,
                          "_deliver_item() component case", validate_py)
    if not DRY_RUN:
        backup(CRAFTING_PATH)
        write(CRAFTING_PATH, craft_content)
        print(f"  Written: {CRAFTING_PATH}")
    else:
        print("  (dry run)")

    # ── Patch 3: npcs_gg7.yaml ────────────────────────────────────────────────
    print("\ndata/npcs_gg7.yaml:")
    npcs_content = read(NPCS_PATH)
    npcs_content = patch(npcs_content, NPC_YAML_OLD_ANCHOR, NPC_YAML_NEW_ANCHOR,
                         "Venn Kator shipwright NPC")
    if not DRY_RUN:
        backup(NPCS_PATH)
        write(NPCS_PATH, npcs_content)
        print(f"  Written: {NPCS_PATH}")
    else:
        print("  (dry run)")

    # ── Generate seed script ──────────────────────────────────────────────────
    seed_path = os.path.join(BASE, "..", "..", "drop13_seed_venn.py")
    seed_path = os.path.normpath(seed_path)
    if not DRY_RUN:
        with open(seed_path, "w", encoding="utf-8") as f:
            f.write(SEED_SCRIPT)
        print(f"\n  Seed script written: {seed_path}")
        print("  Run 'python drop13_seed_venn.py' once on a live world to place Venn Kator.")

    print("\n=== Drop 13 complete ===")
    if DRY_RUN:
        print("(dry run — rerun without --dry-run to apply)")
    else:
        print("Backups written as *.bak_drop13")
        print("\nNext steps:")
        print("  1. python drop13_seed_venn.py   (live worlds only; skip on fresh build)")
        print("  2. Players 'talk Venn Kator' to learn ship component schematics")
        print("  3. Craft components, then '+ship/install <component>'")


if __name__ == "__main__":
    main()
