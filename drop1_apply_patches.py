"""
drop1_apply_patches.py  —  SW_MUSH Traffic Drop 1
Run from project root:  python drop1_apply_patches.py
"""

import ast, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))

def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()

def write(rel, text):
    with open(os.path.join(ROOT, rel), "w", encoding="utf-8") as f:
        f.write(text)

def ok(label):        print(f"  OK : {label}")
def skip(label):      print(f"  SKP: {label} (already applied?)")
def fail(label, msg): print(f"  ERR: {label} — {msg}"); sys.exit(1)

def apply(rel, old, new, label):
    text = read(rel)
    if old not in text:
        skip(label)
        return
    result = text.replace(old, new, 1)
    try:
        ast.parse(result)
    except SyntaxError as e:
        fail(label, f"syntax error after patch: {e}")
    write(rel, result)
    ok(label)


# ─────────────────────────────────────────────────────────────────────────────
# 1. db/database.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── db/database.py ──────────────────────────────────────────────────────")
DB = "db/database.py"

# 1a. SCHEMA_VERSION
apply(DB, "SCHEMA_VERSION = 2", "SCHEMA_VERSION = 3", "SCHEMA_VERSION 2 → 3")

# 1b. Add v3 entry to MIGRATIONS dict
apply(DB,
    "        \"ALTER TABLE npcs ADD COLUMN hired_at TEXT DEFAULT ''\",\n"
    "    ],\n"
    "}",
    "        \"ALTER TABLE npcs ADD COLUMN hired_at TEXT DEFAULT ''\",\n"
    "    ],\n"
    "    3: [\n"
    "        \"ALTER TABLE characters ADD COLUMN bounty INTEGER DEFAULT 0\",\n"
    "    ],\n"
    "}",
    "MIGRATIONS: add v3 bounty column")

# 1c. Append traffic DB methods.
#     The LIKE query uses a variable to avoid quote-nesting issues.
TRAFFIC_METHODS = (
    "\n"
    "    # -- Traffic Ship Methods --\n"
    "\n"
    "    async def create_traffic_ship(self, name: str, template: str) -> int:\n"
    "        import json as _j\n"
    "        systems = _j.dumps({\"traffic\": {}})\n"
    "        cursor = await self._db.execute(\n"
    "            \"INSERT INTO ships \"\n"
    "            \"(name, template, hull_damage, shield_damage, systems, crew, owner_char_id, docked_at) \"\n"
    "            \"VALUES (?, ?, 0, 0, ?, '{}', NULL, NULL)\",\n"
    "            (name, template, systems),\n"
    "        )\n"
    "        await self._db.commit()\n"
    "        return cursor.lastrowid\n"
    "\n"
    "    async def create_traffic_npc(self, name: str, ship_id: int, skill: str) -> int:\n"
    "        import json as _j\n"
    "        char_sheet = _j.dumps({\n"
    "            \"attributes\": {\n"
    "                \"DEX\": skill, \"MEC\": skill, \"STR\": \"2D\",\n"
    "                \"KNO\": \"2D\",  \"PER\": \"2D\",  \"TEC\": \"2D\",\n"
    "            },\n"
    "            \"skills\": {\n"
    "                \"starfighter_piloting\": skill,\n"
    "                \"space_transports\":     skill,\n"
    "                \"starship_gunnery\":     skill,\n"
    "            },\n"
    "        })\n"
    "        cursor = await self._db.execute(\n"
    "            \"INSERT INTO npcs \"\n"
    "            \"(name, species, room_id, char_sheet_json, ai_config_json, hostile, assigned_ship) \"\n"
    "            \"VALUES (?, 'Human', 1, ?, '{}', 0, ?)\",\n"
    "            (name, char_sheet, ship_id),\n"
    "        )\n"
    "        await self._db.commit()\n"
    "        return cursor.lastrowid\n"
    "\n"
    "    async def update_traffic_ship_state(self, ship_id: int, traffic_data: dict):\n"
    "        import json as _j\n"
    "        row = await self._db.execute_fetchone(\n"
    "            \"SELECT systems FROM ships WHERE id = ?\", (ship_id,)\n"
    "        )\n"
    "        if not row:\n"
    "            return\n"
    "        systems = _j.loads(row[\"systems\"] or \"{}\")\n"
    "        systems[\"traffic\"] = traffic_data\n"
    "        await self._db.execute(\n"
    "            \"UPDATE ships SET systems = ? WHERE id = ?\",\n"
    "            (_j.dumps(systems), ship_id),\n"
    "        )\n"
    "        await self._db.commit()\n"
    "\n"
    "    async def get_all_traffic_ships(self) -> list:\n"
    "        needle = '\"traffic\"'\n"
    "        rows = await self._db.execute_fetchall(\n"
    "            \"SELECT * FROM ships WHERE systems LIKE ?\",\n"
    "            (f\"%{needle}%\",),\n"
    "        )\n"
    "        return rows or []\n"
    "\n"
    "    async def delete_traffic_ship(self, ship_id: int):\n"
    "        await self._db.execute(\n"
    "            \"DELETE FROM npcs WHERE assigned_ship = ?\", (ship_id,)\n"
    "        )\n"
    "        await self._db.execute(\"DELETE FROM ships WHERE id = ?\", (ship_id,))\n"
    "        await self._db.commit()\n"
    "\n"
    "    async def set_character_bounty(self, char_id: int, amount: int):\n"
    "        await self._db.execute(\n"
    "            \"UPDATE characters SET bounty = ? WHERE id = ?\",\n"
    "            (max(0, amount), char_id),\n"
    "        )\n"
    "        await self._db.commit()\n"
    "\n"
    "    async def get_character_bounty(self, char_id: int) -> int:\n"
    "        row = await self._db.execute_fetchone(\n"
    "            \"SELECT bounty FROM characters WHERE id = ?\", (char_id,)\n"
    "        )\n"
    "        return row[\"bounty\"] if row else 0\n"
)

db_text = read(DB)
if "create_traffic_ship" in db_text:
    skip("traffic ship DB methods (already present)")
else:
    combined = db_text + TRAFFIC_METHODS
    try:
        ast.parse(combined)
    except SyntaxError as e:
        fail("traffic ship DB methods", f"syntax error: {e}")
    write(DB, combined)
    ok("traffic ship DB methods appended")


# ─────────────────────────────────────────────────────────────────────────────
# 2. parser/space_commands.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── parser/space_commands.py ─────────────────────────────────────────────")
SC = "parser/space_commands.py"

# 2a. Import
apply(SC,
    "from engine.starships import",
    "from engine.npc_space_traffic import get_orbit_zone_for_room, get_traffic_manager\n"
    "from engine.starships import",
    "import: get_orbit_zone_for_room, get_traffic_manager")

# 2b. Launch: write current_zone right after docked_at cleared + grid updated
apply(SC,
    "        await ctx.db.update_ship(ship[\"id\"], docked_at=None)\n"
    "        get_space_grid().add_ship(ship[\"id\"], speed)\n"
    "        await ctx.session_mgr.broadcast_to_room(\n"
    "            bay_id, f\"  The {ship['name']} lifts off with a roar of engines!\")",
    "        await ctx.db.update_ship(ship[\"id\"], docked_at=None)\n"
    "        get_space_grid().add_ship(ship[\"id\"], speed)\n"
    "        # Traffic: assign current_zone on launch\n"
    "        import json as _tj\n"
    "        _tsys = _tj.loads(ship.get(\"systems\") or \"{}\")\n"
    "        _troom = await ctx.db.get_room(bay_id)\n"
    "        _troom_name = _troom[\"name\"] if _troom else \"\"\n"
    "        _tsys[\"current_zone\"] = get_orbit_zone_for_room(_troom_name)\n"
    "        await ctx.db.update_ship(ship[\"id\"], systems=_tj.dumps(_tsys))\n"
    "        await ctx.session_mgr.broadcast_to_room(\n"
    "            bay_id, f\"  The {ship['name']} lifts off with a roar of engines!\")",
    "launch: write current_zone")

# 2c. Land: clear current_zone right after docked_at set + grid updated
apply(SC,
    "        await ctx.db.update_ship(ship[\"id\"], docked_at=bay[\"id\"])\n"
    "        get_space_grid().remove_ship(ship[\"id\"])\n"
    "        await ctx.session_mgr.broadcast_to_room(\n"
    "            ship[\"bridge_room_id\"],\n"
    "            ansi.success(\n"
    "                f\"  {ship['name']} docks at {bay['name']}. \"",
    "        await ctx.db.update_ship(ship[\"id\"], docked_at=bay[\"id\"])\n"
    "        get_space_grid().remove_ship(ship[\"id\"])\n"
    "        # Traffic: clear current_zone on land\n"
    "        import json as _lj\n"
    "        _lsys = _lj.loads(ship.get(\"systems\") or \"{}\")\n"
    "        _lsys.pop(\"current_zone\", None)\n"
    "        await ctx.db.update_ship(ship[\"id\"], systems=_lj.dumps(_lsys))\n"
    "        await ctx.session_mgr.broadcast_to_room(\n"
    "            ship[\"bridge_room_id\"],\n"
    "            ansi.success(\n"
    "                f\"  {ship['name']} docks at {bay['name']}. \"",
    "land: clear current_zone")

# 2d. Hyperspace: store zone alongside location
apply(SC,
    "        systems[\"location\"] = dest_key\n"
    "        await ctx.db.update_ship(ship[\"id\"], systems=json.dumps(systems))",
    "        systems[\"location\"] = dest_key\n"
    "        # Traffic: map dest_key to a zone id\n"
    "        from engine.npc_space_traffic import ZONES as _TZ\n"
    "        _hzone = dest_key + \"_orbit\" if (dest_key + \"_orbit\") in _TZ else \"tatooine_orbit\"\n"
    "        systems[\"current_zone\"] = _hzone\n"
    "        await ctx.db.update_ship(ship[\"id\"], systems=json.dumps(systems))",
    "hyperspace: write current_zone")

ok("scan: traffic ships appear automatically via get_ships_in_space() — no patch needed")


# ─────────────────────────────────────────────────────────────────────────────
# 3. server/game_server.py
# ─────────────────────────────────────────────────────────────────────────────
print("\n── server/game_server.py ────────────────────────────────────────────────")
GS = "server/game_server.py"

apply(GS,
    "                from engine.npc_space_crew import tick_npc_space_combat\n"
    "                await tick_npc_space_combat(self.db, self.session_mgr)\n"
    "            except Exception:\n"
    "                log.debug(\"NPC space crew tick skipped\", exc_info=True)",
    "                from engine.npc_space_crew import tick_npc_space_combat\n"
    "                await tick_npc_space_combat(self.db, self.session_mgr)\n"
    "            except Exception:\n"
    "                log.debug(\"NPC space crew tick skipped\", exc_info=True)\n"
    "\n"
    "            # -- NPC Space Traffic tick --\n"
    "            try:\n"
    "                from engine.npc_space_traffic import get_traffic_manager\n"
    "                await get_traffic_manager().tick(self.db, self.session_mgr)\n"
    "            except Exception:\n"
    "                log.debug(\"NPC space traffic tick skipped\", exc_info=True)",
    "game_server: traffic tick hook")


# ─────────────────────────────────────────────────────────────────────────────
# Final validation
# ─────────────────────────────────────────────────────────────────────────────
print("\n── Final syntax check ───────────────────────────────────────────────────")
all_ok = True
for rel in [DB, SC, GS]:
    try:
        ast.parse(read(rel))
        print(f"  OK : {rel}")
    except SyntaxError as e:
        print(f"  ERR: {rel} — {e}")
        all_ok = False

print()
if all_ok:
    print("All patches applied successfully.")
    print()
    print("Install sequence:")
    print("  1. del sw_mush.db          (Windows) / rm sw_mush.db  (Linux)")
    print("  2. python main.py          (creates schema v3 — Ctrl+C after 'Schema initialized')")
    print("  3. python build_mos_eisley.py")
    print("  4. python main.py          (full world + traffic live)")
else:
    print("One or more files have errors — no DB changes needed, fix above and re-run.")
    sys.exit(1)
