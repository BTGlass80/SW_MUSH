#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
drop5_integration_patch.py
--------------------------
Drop 5: Wire existing game systems to read Director/WorldEvents state.

Changes:

  1. engine/npc_space_traffic.py
     TRAFFIC_WEIGHTS PATROL entry multiplied by patrol_spawn_mult from
     WorldEventManager at spawn time. No structural change — modifies
     the effective weight in _pick_archetype() via a wrapper.

  2. engine/missions.py
     _pick_type() reads zone alert level and biases weights:
       LOCKDOWN  -> SMUGGLING +10 (risk premium)
       UNDERWORLD -> SMUGGLING +5, BOUNTY +5
       UNREST     -> add COMBAT +5

  3. parser/space_commands.py (LandCommand)
     Docking fee reads zone alert level multiplier:
       LOCKDOWN  -> fee * 1.5
       LAX       -> fee * 0.75
       STANDARD/HIGH_ALERT -> fee * 1.0

  4. parser/builtin_commands.py (SellCommand)
     Sell price reads sell_price_mult from WorldEventManager
     (trade_boom event gives +25%).

Run from the SW_MUSH project root:
    python patches/drop5_integration_patch.py

Safe to re-run: each step checks if already applied.
"""
import ast, shutil, sys
from pathlib import Path

TRAFFIC  = Path("engine/npc_space_traffic.py")
MISSIONS = Path("engine/missions.py")
SPACE    = Path("parser/space_commands.py")
BUILTIN  = Path("parser/builtin_commands.py")

for f in (TRAFFIC, MISSIONS, SPACE, BUILTIN):
    if not f.exists():
        print(f"ERROR: {f} not found. Run from project root.")
        sys.exit(1)

def read(p): return p.read_text(encoding="utf-8")
def write(p, s): p.write_text(s, encoding="utf-8")
def validate(p, s):
    try:
        ast.parse(s)
        return True
    except SyntaxError as e:
        print(f"  SYNTAX ERROR in {p}: {e}")
        return False
def backup(p):
    bak = p.with_suffix(".py.drop5_bak")
    if not bak.exists():
        shutil.copy2(p, bak)
    print(f"  Backup: {bak.name}")

changes = 0

# ══════════════════════════════════════════════════════════════════════════════
# 1. engine/npc_space_traffic.py — patrol spawn multiplier
# ══════════════════════════════════════════════════════════════════════════════
print("\n── engine/npc_space_traffic.py ──────────────────────────────────────────")

src = read(TRAFFIC)

if "patrol_spawn_mult" in src:
    print("  ✓ patrol_spawn_mult already present — skipping.")
else:
    # Replace _pick_archetype() to read WorldEvents patrol multiplier.
    # The function currently does a simple random.choices over TRAFFIC_WEIGHTS.
    # We inject a local copy with the patrol weight scaled.
    OLD = (
        "def _pick_archetype() -> TrafficArchetype:\n"
        "    archetypes = list(TRAFFIC_WEIGHTS.keys())\n"
        "    weights    = [TRAFFIC_WEIGHTS[a] for a in archetypes]\n"
        "    return random.choices(archetypes, weights=weights, k=1)[0]"
    )
    NEW = (
        "def _pick_archetype() -> TrafficArchetype:\n"
        "    weights = dict(TRAFFIC_WEIGHTS)  # local mutable copy\n"
        "    # Apply WorldEvents patrol spawn multiplier (e.g. imperial_crackdown)\n"
        "    try:\n"
        "        from engine.world_events import get_world_event_manager\n"
        "        mult = get_world_event_manager().get_effect('patrol_spawn_mult', 1.0)\n"
        "        if mult != 1.0:\n"
        "            weights[TrafficArchetype.PATROL] = int(\n"
        "                weights[TrafficArchetype.PATROL] * mult\n"
        "            )\n"
        "    except Exception:\n"
        "        pass\n"
        "    archetypes = list(weights.keys())\n"
        "    wlist      = [weights[a] for a in archetypes]\n"
        "    return random.choices(archetypes, weights=wlist, k=1)[0]"
    )

    # Try LF and CRLF
    patched = src
    for old, new in [(OLD, NEW), (OLD.replace("\n", "\r\n"), NEW.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + _pick_archetype() patched with patrol_spawn_mult")
            break
    else:
        # Softer fallback: inject after TRAFFIC_WEIGHTS dict definition
        fallback_anchor = "    TrafficArchetype.BOUNTY_HUNTER: 10,  # only used for random; hunters normally event-driven\n}"
        fallback_insert = (
            "\n\n"
            "def _pick_archetype() -> TrafficArchetype:\n"
            "    weights = dict(TRAFFIC_WEIGHTS)\n"
            "    try:\n"
            "        from engine.world_events import get_world_event_manager\n"
            "        mult = get_world_event_manager().get_effect('patrol_spawn_mult', 1.0)\n"
            "        if mult != 1.0:\n"
            "            weights[TrafficArchetype.PATROL] = int(weights[TrafficArchetype.PATROL] * mult)\n"
            "    except Exception:\n"
            "        pass\n"
            "    archetypes = list(weights.keys())\n"
            "    return random.choices(archetypes, weights=[weights[a] for a in archetypes], k=1)[0]"
        )
        if fallback_anchor in patched:
            patched = patched.replace(fallback_anchor, fallback_anchor + fallback_insert, 1)
            print("  + _pick_archetype() injected via fallback anchor")
        else:
            print("  WARNING: Could not patch _pick_archetype(). Add manually.")
            patched = src  # no change

    if patched != src:
        if validate(TRAFFIC, patched):
            backup(TRAFFIC)
            write(TRAFFIC, patched)
            print("  ✓ engine/npc_space_traffic.py patched")
            changes += 1
        else:
            print("  engine/npc_space_traffic.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# 2. engine/missions.py — alert-level biased _pick_type()
# ══════════════════════════════════════════════════════════════════════════════
print("\n── engine/missions.py ───────────────────────────────────────────────────")

src = read(MISSIONS)

if "get_director" in src and "alert_level" in src:
    print("  ✓ director alert bias already present — skipping.")
else:
    OLD_PICK = (
        "def _pick_type() -> MissionType:\n"
        "    \"\"\"Weighted random mission type selection.\"\"\"\n"
        "    types = list(SPAWN_WEIGHTS.keys())\n"
        "    weights = [SPAWN_WEIGHTS[t] for t in types]\n"
        "    return random.choices(types, weights=weights, k=1)[0]"
    )
    NEW_PICK = (
        "def _pick_type() -> MissionType:\n"
        "    \"\"\"Weighted random mission type selection, biased by zone alert level.\"\"\"\n"
        "    weights = dict(SPAWN_WEIGHTS)  # mutable local copy\n"
        "    # Bias weights based on Director zone alert level\n"
        "    try:\n"
        "        from engine.director import get_director, AlertLevel\n"
        "        director = get_director()\n"
        "        # Use the most dramatic alert level across all zones\n"
        "        alert_levels = [zs.alert_level for zs in director._zones.values()]\n"
        "        if AlertLevel.LOCKDOWN in alert_levels:\n"
        "            # Lockdown: smuggling pays more (risk premium)\n"
        "            weights[MissionType.SMUGGLING] = weights.get(MissionType.SMUGGLING, 5) + 10\n"
        "        elif AlertLevel.UNDERWORLD in alert_levels:\n"
        "            # Underworld: criminal jobs abundant\n"
        "            weights[MissionType.SMUGGLING] = weights.get(MissionType.SMUGGLING, 5) + 5\n"
        "            weights[MissionType.BOUNTY]    = weights.get(MissionType.BOUNTY, 5) + 5\n"
        "        elif AlertLevel.UNREST in alert_levels:\n"
        "            # Unrest: rebel-adjacent combat jobs\n"
        "            weights[MissionType.COMBAT] = weights.get(MissionType.COMBAT, 8) + 5\n"
        "    except Exception:\n"
        "        pass  # director not loaded yet — use base weights\n"
        "    types = list(weights.keys())\n"
        "    wlist = [weights[t] for t in types]\n"
        "    return random.choices(types, weights=wlist, k=1)[0]"
    )

    patched = src
    for old, new in [(OLD_PICK, NEW_PICK),
                     (OLD_PICK.replace("\n", "\r\n"), NEW_PICK.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + _pick_type() patched with alert-level bias")
            break
    else:
        print("  WARNING: Could not find _pick_type() anchor. Add manually.")
        patched = src

    if patched != src:
        if validate(MISSIONS, patched):
            backup(MISSIONS)
            write(MISSIONS, patched)
            print("  ✓ engine/missions.py patched")
            changes += 1
        else:
            print("  engine/missions.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# 3. parser/space_commands.py — docking fee alert multiplier
# ══════════════════════════════════════════════════════════════════════════════
print("\n── parser/space_commands.py (docking fee) ───────────────────────────────")

src = read(SPACE)

if "alert_level" in src and "docking_fee" in src and "get_director" in src:
    print("  ✓ docking fee alert multiplier already present — skipping.")
else:
    OLD_FEE = "        # Docking fee: 25cr (per R&E GG7)\n        docking_fee = 25"
    NEW_FEE = (
        "        # Docking fee: 25cr base (per R&E GG7), modified by zone alert level\n"
        "        docking_fee = 25\n"
        "        try:\n"
        "            from engine.director import get_director, AlertLevel\n"
        "            _alert = get_director().get_alert_level('spaceport')\n"
        "            if _alert == AlertLevel.LOCKDOWN:\n"
        "                docking_fee = int(docking_fee * 1.5)  # +50% imperial surcharge\n"
        "            elif _alert == AlertLevel.LAX:\n"
        "                docking_fee = int(docking_fee * 0.75)  # -25% low security\n"
        "        except Exception:\n"
        "            pass"
    )

    patched = src
    for old, new in [(OLD_FEE, NEW_FEE),
                     (OLD_FEE.replace("\n", "\r\n"), NEW_FEE.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + Docking fee alert multiplier injected")
            break
    else:
        print("  WARNING: Could not find docking fee anchor. Add manually after 'docking_fee = 25'.")
        patched = src

    if patched != src:
        if validate(SPACE, patched):
            backup(SPACE)
            write(SPACE, patched)
            print("  ✓ parser/space_commands.py patched")
            changes += 1
        else:
            print("  parser/space_commands.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# 4. parser/builtin_commands.py — sell price world event multiplier
# ══════════════════════════════════════════════════════════════════════════════
print("\n── parser/builtin_commands.py (sell price) ──────────────────────────────")

src = read(BUILTIN)

if "sell_price_mult" in src:
    print("  ✓ sell_price_mult already present — skipping.")
else:
    # Inject after the quality bonus block, before the credits deduction.
    # Anchor: the line that computes sale_price from quality bonus
    OLD_SELL = (
        "        # Quality bonus for crafted items\n"
        "        if item.quality >= 80:\n"
        "            sale_price = int(sale_price * 1.3)\n"
        "        elif item.quality >= 60:\n"
        "            sale_price = int(sale_price * 1.15)\n"
        "\n"
        "        credits = char.get(\"credits\", 0)"
    )
    NEW_SELL = (
        "        # Quality bonus for crafted items\n"
        "        if item.quality >= 80:\n"
        "            sale_price = int(sale_price * 1.3)\n"
        "        elif item.quality >= 60:\n"
        "            sale_price = int(sale_price * 1.15)\n"
        "\n"
        "        # World event sell price multiplier (e.g. trade_boom: +25%)\n"
        "        try:\n"
        "            from engine.world_events import get_world_event_manager\n"
        "            _smult = get_world_event_manager().get_effect('sell_price_mult', 1.0)\n"
        "            if _smult != 1.0:\n"
        "                sale_price = int(sale_price * _smult)\n"
        "        except Exception:\n"
        "            pass\n"
        "\n"
        "        credits = char.get(\"credits\", 0)"
    )

    patched = src
    for old, new in [(OLD_SELL, NEW_SELL),
                     (OLD_SELL.replace("\n", "\r\n"), NEW_SELL.replace("\n", "\r\n"))]:
        if old in patched:
            patched = patched.replace(old, new, 1)
            print("  + sell_price_mult injected into SellCommand")
            break
    else:
        print("  WARNING: Could not find sell price anchor. Add manually in SellCommand.execute().")
        patched = src

    if patched != src:
        if validate(BUILTIN, patched):
            backup(BUILTIN)
            write(BUILTIN, patched)
            print("  ✓ parser/builtin_commands.py patched")
            changes += 1
        else:
            print("  parser/builtin_commands.py unchanged")

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
print("\n── Final syntax check ───────────────────────────────────────────────────")
all_ok = True
for f in (TRAFFIC, MISSIONS, SPACE, BUILTIN):
    try:
        ast.parse(read(f))
        print(f"  OK  {f}")
    except SyntaxError as e:
        print(f"  ERR {f}: {e}")
        all_ok = False

print()
if all_ok:
    print(f"Drop 5 complete. {changes} file(s) modified.")
    print()
    print("Effects now active:")
    print("  - Imperial crackdown event -> more patrol spawns in space")
    print("  - Lockdown alert -> smuggling missions more common, +50% docking fee")
    print("  - Underworld alert -> bounty/smuggling missions more common")
    print("  - Trade boom event -> sell prices +25%")
    print("  - Lax alert -> docking fee -25%")
else:
    print("WARNING: Some files failed syntax check.")
    sys.exit(1)
