# -*- coding: utf-8 -*-
"""
SW_MUSH World Builder v4
============================
Populates the full game world across four planets with security zones
from the Security Zones Design v1 (EVE-inspired secured/contested/lawless).

Planets & Room Counts:
  - Mos Eisley (Tatooine) — 54 rooms, 7 zones  [GG7 core + Outskirts/Wastes]
  - Nar Shaddaa              — 30 rooms, 4 zones  [Dark Empire / EU + Warrens]
  - Kessel                   — 15 rooms, 3 zones  [WEG sourcebooks / canon + Deep Mines]
  - Corellia (Coronet City)  — 24 rooms, 4 zones  [WEG / general SW lore + districts]

Zone security tiers (from security_zones_design_v1.md):
  SECURED   — No PvP, no NPC aggro. Safe areas.
  CONTESTED — NPC combat enabled, PvP requires challenge/accept.
  LAWLESS   — Full PvP, aggressive NPCs, rare resources, high rewards.

Also creates:
  - Combat-ready NPCs (char_sheet_json + ai_config_json)
  - Hostile NPCs (stormtroopers, thugs, creatures) that attack on sight
  - Hireable crew NPCs at cantinas and spaceports
  - Pre-spawned ships docked in bays with bridge rooms
  - NPCs for all four planets including new wilderness/dangerous zones

Auto-build:
  Called automatically by game_server.py on startup if the world
  hasn't been populated yet (room count <= 3 seed rooms).
  Can also be run standalone:
    python build_mos_eisley.py

Usage (standalone):
  1. Delete sw_mush.db
  2. python main.py  (creates clean DB, Ctrl+C to stop)
  3. python build_mos_eisley.py
  4. python main.py  (full world ready)
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from db.database import Database
from engine.npc_loader import load_era_npcs
from engine.ship_loader import load_era_ships
from engine.test_character_loader import load_era_test_character
from engine.world_loader import load_world_dry_run
from engine.world_writer import write_world_bundle


# ==============================================================
# HELPER: Build a char_sheet_json for combat-ready NPCs
# ==============================================================
def _sheet(dex="3D", kno="2D", mec="2D", per="3D", stre="3D", tec="2D",
           skills=None, weapon="", species="Human", wound_level=0):
    """Build a char_sheet_json dict for an NPC."""
    return {
        "attributes": {
            "dexterity": dex, "knowledge": kno, "mechanical": mec,
            "perception": per, "strength": stre, "technical": tec,
        },
        "skills": skills or {},
        "weapon": weapon,
        "species": species,
        "wound_level": wound_level,
    }

def _ai(personality="", knowledge=None, faction="Neutral", style="",
        fallbacks=None, hostile=False, behavior="defensive",
        model_tier=1, temperature=0.7, max_tokens=120,
        space_skills=None,
        trainer=False, train_skills=None):
    """Build an ai_config_json dict."""
    cfg = {
        "personality": personality,
        "knowledge": knowledge or [],
        "faction": faction,
        "dialogue_style": style,
        "fallback_lines": fallbacks or [],
        "hostile": hostile,
        "combat_behavior": behavior,
        "model_tier": model_tier,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if space_skills:
        cfg["skills"] = space_skills
    if trainer:
        cfg["trainer"] = True
        cfg["train_skills"] = train_skills or []
    return cfg

# ==============================================================
# NPC DEFINITIONS -- LOADED FROM YAML
# All GG7 NPCs are now in data/npcs_gg7.yaml, loaded at build time
# by engine/npc_loader.py. The YAML file contains 50 NPCs with full
# stat blocks, AI configs, and room placements.
#
# To add/edit NPCs, modify data/npcs_gg7.yaml instead of this file.
# ==============================================================

# ==============================================================
# HIREABLE CREW NPCs and PLANET-SPECIFIC NPCs
# ==============================================================
# As of F.1a (Apr 2026), these are loaded from YAML via load_era_npcs():
#   data/worlds/gcw/npcs_hireable.yaml   (4 entries — pilot/gunner/mechanic/navigator)
#   data/worlds/gcw/npcs_planet.yaml     (43 entries — Tatooine outskirts/wastes,
#                                         Nar Shaddaa, Kessel, Corellia)
# The era.yaml content_refs section drives the load. Switching to CW becomes
# a one-line era_dir change once F.1b (ships) and F.1c (test character) land.

# ==============================================================
# SHIPS
# ==============================================================
# As of F.1b (Apr 2026), pre-spawned ships are loaded from YAML via
# load_era_ships():  data/worlds/gcw/ships.yaml  (7 entries — YT-1300s,
# Z-95, Ghtroc 720, Lambda shuttles across Tatooine/Nar Shaddaa/Kessel/
# Corellia).  Switching to CW becomes a one-line era_dir change once
# F.1c (test character) lands.



# ==============================================================
# BUILD FUNCTION
# ==============================================================

async def build(db_path="sw_mush.db", era="gcw"):
    """
    Build the world for the given era.

    Args:
        db_path: SQLite DB path. Created if missing.
        era: Era code matching a directory under data/worlds/. As of
             F.1d, "gcw" is the only fully-supported era; "clone_wars"
             content exists at data/worlds/clone_wars/ but is gated
             behind separate work (organizations.yaml engine integration,
             space_zones engine refactor — see CW preflight checklist).

    The era selects:
        * zones / rooms / exits (via load_world_dry_run(era))
        * NPCs (via era.yaml::content_refs.npcs + npcs_hireable)
        * Ships (via era.yaml::content_refs.ships)
        * Test character (via era.yaml::content_refs.test_character)

    All era-specific content is data-driven; this function holds no
    GCW-specific literals after the F.0/F.1 series.
    """
    db = Database(db_path)
    await db.connect()
    await db.initialize()

    print("+============================================+")
    print(f"|    Building Galaxy v4 -- era: {era:<13s}|")
    print("+============================================+")

    # ── World content: zones + rooms + exits ─────────────────────────────────
    # F.0 Drop 4 Pass B: zones/rooms/exits are loaded from data/worlds/<era>/
    # YAML and written by engine.world_writer.  Legacy ROOMS / EXITS /
    # ROOM_ZONES / ROOM_OVERRIDES / MAP_COORDS literals were deleted in Pass B
    # (~1530 lines removed).  Downstream code (NPCs, ships, seed-room linking,
    # test character) now drives off `bundle.rooms` and the writer's
    # `room_id_for_yaml_id` dict instead of positional indexing.
    print(f"\n  Loading world content from data/worlds/{era}/ ...")
    bundle = load_world_dry_run(era)
    if not bundle.report.ok:
        raise RuntimeError(
            f"World validation failed with {len(bundle.report.errors)} errors: "
            f"{bundle.report.errors[:3]}"
        )
    for w in bundle.report.warnings:
        print(f"    [WARN] {w}")
    print(f"    Loaded {len(bundle.zones)} zones, "
          f"{len(bundle.rooms)} rooms, {len(bundle.exits)} exits")

    print("\n  Writing world to DB ...")
    write_result = await write_world_bundle(bundle, db)
    print(f"    Wrote {len(write_result.zone_ids)} zones, "
          f"{len(write_result.room_ids)} rooms, "
          f"{write_result.exits_written} exit rows")

    # Convenience aliases for downstream code (NPC/ship placement, seed-room
    # linking, summary print).  These derive from the bundle directly — no
    # dependency on a legacy `ROOMS` list.
    #   zones[slug]              -> db_id   (e.g. zones["mos_eisley"])
    #   room_ids[yaml_id]        -> db_id   (yaml_id is the int from YAML)
    #   room_name_by_yaml_id[id] -> name    (for human-readable print rows)
    zones = dict(write_result.zone_ids)
    room_ids = dict(write_result.room_id_for_yaml_id)
    room_name_by_yaml_id = {r.id: r.name for r in bundle.rooms.values()}

    # Connect to seed rooms (1=Landing Pad, 2=Mos Eisley Street, 3=Cantina)
    # ── Seed rooms (Landing Pad, Street, Cantina) — GCW-specific ─────────────
    # The seed rooms 1/2/3 are created by Database.initialize() as a
    # bootstrap so the server can serve a minimal world before any build
    # runs.  These three exits link them into the GCW Mos Eisley map.
    # For CW (Nar Shaddaa starting room) and other future eras, this
    # block needs its own per-era pattern — likely a content_refs.seed_links
    # YAML pointing at era-specific yaml_ids.  Until then, gate on era.
    if era == "gcw":
        print("\n  Linking seed rooms to new Mos Eisley...")
        spaceport_row_id = room_ids[7]
        market_id = room_ids[8]
        cantina_entrance_id = room_ids[12]

        await db.create_exit(1, spaceport_row_id, "north", "")
        await db.create_exit(spaceport_row_id, 1, "south", "Landing Pad")
        await db.create_exit(2, market_id, "north", "")
        await db.create_exit(market_id, 2, "south", "Street")
        await db.create_exit(3, cantina_entrance_id, "east", "")
        await db.create_exit(cantina_entrance_id, 3, "west", "")
        print("    Seed rooms linked (Landing Pad, Street, Cantina)")
    else:
        print(f"\n  [SKIP] Seed-room linking is GCW-specific; era={era!r}.")


    # -- NPCs (era-aware loader; F.1a) --
    # `room_name_map` translates a YAML room-name string to the yaml_id that
    # the NPC tuple stores in its `room_idx` field.  load_era_npcs() reads
    # data/worlds/<era>/era.yaml's `content_refs.npcs` (a list, loaded in
    # order with `replaces:` substitution) and `content_refs.npcs_hireable`
    # (single file).  For GCW today this covers npcs_gg7.yaml + npcs_planet.yaml
    # and npcs_hireable.yaml.  Switching to CW becomes a one-line change here
    # once F.1b/F.1c land.
    era_dir = os.path.join(os.path.dirname(__file__), "data", "worlds", era)
    room_name_map = {r.name: r.id for r in bundle.rooms.values()}
    planet_npcs, hireable_npcs = load_era_npcs(era_dir, room_name_map)

    print(f"\n  Creating {len(planet_npcs)} planet NPCs (era-aware load)...")
    npc_count = 0
    for name, room_idx, species, desc, sheet, ai_cfg in planet_npcs:
        rid = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai_cfg),
        )
        hostile_tag = " [HOSTILE]" if ai_cfg.get("hostile") else ""
        print(f"    #{npc_id:3d} {name:30s} in {room_name_by_yaml_id[room_idx][:25]}{hostile_tag}")
        npc_count += 1

    # -- Hireable Crew NPCs --
    print(f"\n  Creating {len(hireable_npcs)} hireable crew NPCs...")
    for name, room_idx, species, desc, sheet, ai_cfg in hireable_npcs:
        rid = room_ids[room_idx]
        npc_id = await db.create_npc(
            name=name, room_id=rid, species=species, description=desc,
            char_sheet_json=json.dumps(sheet),
            ai_config_json=json.dumps(ai_cfg),
        )
        print(f"    #{npc_id:3d} {name:30s} [HIREABLE] in {room_name_by_yaml_id[room_idx][:25]}")
        npc_count += 1

    # -- Ships (era-aware loader; F.1b) --
    # ships are loaded from data/worlds/<era>/ships.yaml via era.yaml's
    # content_refs.ships entry.  Each entry creates a bridge room, a ship
    # row, and bidirectional board/disembark exits between bay and bridge.
    ships = load_era_ships(era_dir, room_name_map)
    print(f"\n  Spawning {len(ships)} ships in docking bays...")
    for entry in ships:
        template_key = entry["template_key"]
        ship_name = entry["name"]
        bay_idx = entry["bay_room_idx"]
        bridge_desc = entry["bridge_desc"]
        bay_room_id = room_ids[bay_idx]
        # Create bridge room
        bridge_id = await db.create_room(
            f"{ship_name} - Bridge",
            f"The bridge of the {ship_name}.",
            bridge_desc,
        )
        # Create the ship record
        cursor = await db.execute(
            """INSERT INTO ships (template, name, bridge_room_id, docked_at,
               hull_damage, shield_damage, systems, crew, cargo)
               VALUES (?, ?, ?, ?, 0, 0, '{}', '{}', '[]')""",
            (template_key, ship_name, bridge_id, bay_room_id),
        )
        await db.commit()
        ship_id = cursor.lastrowid

        # Create exit from bay to bridge and back
        await db.create_exit(bay_room_id, bridge_id, "board")
        await db.create_exit(bridge_id, bay_room_id, "disembark")

        bay_name = room_name_by_yaml_id[bay_idx]
        print(f"    Ship #{ship_id:3d} '{ship_name}' ({template_key}) docked at {bay_name}")


    # -- Test Character (era-aware loader; F.1c) --
    # Spec is loaded from data/worlds/<era>/test_character.yaml via era.yaml's
    # content_refs.test_character entry.  GCW: Test Jedi (admin+builder
    # god-mode) at Docking Bay 94.  Skips chargen and tutorial.
    print("\n  Creating test character...")
    test_spec = load_era_test_character(era_dir, room_name_map)
    if test_spec is None:
        print("    [SKIP] No test_character spec for this era.")
    else:
        try:
            import bcrypt
            acct = test_spec["account"]
            char = test_spec["character"]
            test_pw_hash = bcrypt.hashpw(
                acct["password"].encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            await db.execute(
                """INSERT OR IGNORE INTO accounts
                   (username, password_hash, is_admin, is_builder)
                   VALUES (?, ?, ?, ?)""",
                (acct["username"], test_pw_hash,
                 1 if acct["is_admin"] else 0,
                 1 if acct["is_builder"] else 0),
            )
            await db.commit()
            acct_rows = await db.fetchall(
                "SELECT id FROM accounts WHERE username = ?",
                (acct["username"],),
            )
            test_acct_id = acct_rows[0]["id"]

            # Resolve starting room → DB room_id via the world bundle's mapping
            start_room = room_ids[char["starting_room_idx"]]

            cursor = await db.execute(
                """INSERT OR IGNORE INTO characters
                   (account_id, name, species, template, attributes, skills,
                    wound_level, character_points, force_points,
                    dark_side_points, room_id, description, credits,
                    equipment, inventory, faction_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    test_acct_id,
                    char["name"],
                    char["species"],
                    char["template"],
                    json.dumps(char["attributes"]),
                    json.dumps(char["skills"]),
                    char["wound_level"],
                    char["character_points"],
                    char["force_points"],
                    char["dark_side_points"],
                    start_room,
                    char["description"],
                    char["credits"],
                    json.dumps(char["equipment"]),
                    json.dumps(char["inventory"]),
                    char["faction_id"],
                ),
            )
            await db.commit()
            test_char_id = cursor.lastrowid
            if test_char_id:
                print(f"    Test character {char['name']!r} (id={test_char_id}) created.")
                print(f"    Login: {acct['username']} / {acct['password']}  "
                      f"|  {'Admin+' if acct['is_admin'] else ''}"
                      f"{'Builder' if acct['is_builder'] else ''}")
                if char.get("equipment", {}).get("key") == "lightsaber":
                    print(f"    Credits: {char['credits']:,}  |  "
                          f"Force: {char['force_points']} FP  |  "
                          f"Lightsaber equipped")
            else:
                print(f"    Test character already exists (skipped).")
        except Exception as e:
            print(f"    [WARN] Test character creation failed: {e}")


    # -- Summary --
    total_rooms = len(bundle.rooms) + len(ships)  # rooms + bridge rooms
    seed_exits = 6 if era == "gcw" else 0
    total_exits = len(bundle.exits) * 2 + seed_exits + len(ships) * 2  # pairs + seed links + ship exits
    hostile_count = sum(1 for _, _, _, _, _, a in planet_npcs if a.get('hostile'))
    print(f"\n  +======================================+")
    print(f"  |  BUILD COMPLETE                      |")
    print(f"  |  Rooms:    {total_rooms:4d}                      |")
    print(f"  |  Exits:    {total_exits:4d}                      |")
    print(f"  |  NPCs:     {npc_count:4d} ({hostile_count:d} hostile)           |")
    print(f"  |  Crew:     {len(hireable_npcs):4d} (hireable)           |")
    print(f"  |  Ships:    {len(ships):4d} (docked)              |")
    print(f"  |  Zones:    {len(zones):4d}                       |")
    print(f"  |  Planets:     4 (Tatooine, Nar Shaddaa,|")
    print(f"  |                  Kessel, Corellia)     |")
    print(f"  |                                        |")
    print(f"  |  Security Tiers:                       |")
    print(f"  |    SECURED:   market, cantina, civic,  |")
    print(f"  |      spaceport, residential, coronet   |")
    print(f"  |    CONTESTED: outskirts, promenade,    |")
    print(f"  |      port district, old quarter, kessel|")
    print(f"  |    LAWLESS:   wastes, undercity,        |")
    print(f"  |      warrens, mines, deep mines        |")
    print(f"  +======================================+")

    await db.close()


async def auto_build_if_needed(db_path="sw_mush.db", era=None):
    """Called by game_server.py on startup. Builds the world if not yet populated.

    Args:
        db_path: SQLite DB path.
        era: Optional era code (e.g. "gcw", "clone_wars"). If None, resolves
             via `engine.era_state.get_active_era()`, which reads the Config
             registered by `main.py` at boot. Defaults to "gcw" when no
             Config is registered, preserving legacy behavior.

    Returns True if the build was performed, False if the world already exists.

    B.2-thread (Apr 28 2026): added `era` kwarg + era_state resolution. F.1
    delivered `build(db_path, era=...)`; this function used to hardcode the
    GCW default by calling `build(db_path)` positionally, which silently
    overrode the F.6a.6 dev flag at the auto-build path. The fix is to
    thread `era` through.
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()

    db = Database(db_path)
    await db.connect()
    await db.initialize()
    count = await db.count_rooms()
    await db.close()

    if count <= 3:
        # Only seed rooms exist — build the full world
        print(f"\n  [Auto-Build] World not yet populated. Running world builder (era={era})...")
        await build(db_path, era=era)
        return True
    else:
        return False


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Build the SW_MUSH world for an era.")
    parser.add_argument("--era", default="gcw",
                        help="Era code (default: gcw). Must match a directory under data/worlds/.")
    parser.add_argument("--db", default="sw_mush.db",
                        help="Path to the SQLite database file (default: sw_mush.db).")
    args = parser.parse_args()
    asyncio.run(build(db_path=args.db, era=args.era))
