# -*- coding: utf-8 -*-
"""
engine/housing.py — Player Housing & Homesteads system.  [v21 Drops 1-4]

Architecture
============
Housing state lives in two new DB tables (player_housing, housing_lots) plus
a housing_id column on rooms.  Housing rooms are ordinary rooms; housing_id
is the only thing that marks them as player-owned.

All rent deductions go through process_housing_rent() — no shortcuts.
See player_housing_design_v1.md for full specification.

Drop 1: Tier 1 rented rooms (rent/checkout/storage/sethome/home)
Drop 2: Description editor, trophies, room naming
Drop 3: Tier 2 faction quarters (auto-assign on rank, revoke on leave/demote)
Drop 4: Tier 3 private residences (purchase/sell, multi-room, guest list)
"""

from __future__ import annotations
import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────────────────

TIER1_DEPOSIT      = 500     # credits; returned on checkout
TIER1_WEEKLY_RENT  = 50      # credits/week
TIER1_STORAGE_MAX  = 20      # item slots
TIER1_RENT_GRACE   = 2       # weeks of missed rent before eviction warning
TIER1_EVICT_WEEKS  = 4       # weeks of missed rent before eviction

RENT_TICK_INTERVAL = 604_800  # game ticks per week (1 tick = 1 second)

# ── Drop 3: Faction Quarter definitions ──────────────────────────────────────
# tier=2, housing_type='faction_quarters', weekly_rent=0
#
# FACTION_QUARTER_TIERS maps (faction_code, min_rank) -> tier config.
# Checked in descending rank order so highest qualifying tier wins.

FACTION_QUARTER_TIERS = {
    # ── Empire ──
    ("empire", 0): {
        "label": "Imperial Barracks — Shared Bunk",
        "storage_max": 10,
        "room_name": "{name}'s Bunk",
        "room_desc": (
            "A narrow bunk in the Imperial garrison barracks. A thin mattress sits on "
            "a durasteel frame, with a locker bolted to the wall. The steady hum of "
            "the garrison's power generator vibrates through the floor. Stormtrooper "
            "boots echo in the corridor outside."
        ),
    },
    ("empire", 2): {
        "label": "Imperial Garrison — Private Quarters",
        "storage_max": 30,
        "room_name": "{name}'s Quarters",
        "room_desc": (
            "A private room in the Imperial garrison's officer wing. A proper bed, "
            "a desk with a holoterminal, and a reinforced locker. The door has a "
            "coded lock. A viewport shows {planet_view}."
        ),
    },
    ("empire", 4): {
        "label": "Imperial Garrison — Officer's Suite",
        "storage_max": 50,
        "room_name": "{name}'s Officer Suite",
        "room_desc": (
            "A spacious officer's suite in the garrison command level. A large desk "
            "dominates one wall, flanked by a personal holoterminal and a weapons rack. "
            "The bed is military-neat with Imperial-issue sheets. A viewport offers "
            "a commanding view of {planet_view}. A private refresher adjoins."
        ),
    },
    ("empire", 6): {
        "label": "Imperial Garrison — Commander's Quarters",
        "storage_max": 100,
        "room_name": "Commander {name}'s Quarters",
        "room_desc": (
            "The garrison commander's private quarters. Spartan Imperial efficiency "
            "meets the privileges of rank: a full-size desk with encrypted terminal, "
            "a conference table for four, personal weapons vault, and a viewport "
            "spanning the entire wall showing {planet_view}. A private meeting room "
            "adjoins through a blast-rated door."
        ),
    },
    # ── Rebel ──
    ("rebel", 1): {
        "label": "Rebel Safehouse — Shared Bunk",
        "storage_max": 20,
        "room_name": "Safehouse Bunk",
        "room_desc": (
            "A cramped bunk in a hidden Rebel safehouse. The walls are bare ferrocrete, "
            "the lighting dim and powered by a tapped junction. Cargo crates serve as "
            "furniture. A small locker is bolted under the bunk. The air tastes of "
            "recycled atmosphere and quiet defiance."
        ),
    },
    ("rebel", 3): {
        "label": "Rebel Safehouse — Private Cell",
        "storage_max": 40,
        "room_name": "{name}'s Cell",
        "room_desc": (
            "A private room in the safehouse's inner section. A bunk, a secured locker, "
            "and a small desk with an encrypted datapad. Alliance propaganda posters "
            "line one wall — hand-painted Starbird symbols. The door has an old-fashioned "
            "mechanical lock, harder to slice than electronic ones."
        ),
    },
    ("rebel", 5): {
        "label": "Rebel Command Quarters",
        "storage_max": 80,
        "room_name": "Commander {name}'s Quarters",
        "room_desc": (
            "The cell commander's quarters deep in the safehouse. A planning table "
            "covered in holographic terrain maps, an encrypted terminal with a "
            "direct HoloNet relay, and a weapons cache behind a false wall. The "
            "spartan furnishings can't hide the weight of responsibility that "
            "fills this room."
        ),
    },
    # ── Hutt Cartel ──
    ("hutt", 2): {
        "label": "Hutt Cartel — Enforcer's Safehouse",
        "storage_max": 30,
        "room_name": "Enforcer's Room",
        "room_desc": (
            "A functional safehouse room in the Hutt-controlled undercity. The door "
            "is reinforced durasteel with three separate locks. A weapons rack, a bunk, "
            "and a hidden floor compartment for 'special deliveries.' The walls are "
            "covered in cheap soundproofing material. Comfort was never the point."
        ),
    },
    ("hutt", 3): {
        "label": "Hutt Cartel — Lieutenant's Suite",
        "storage_max": 50,
        "room_name": "{name}'s Suite",
        "room_desc": (
            "A well-appointed suite in a Hutt-controlled building. The decor is "
            "gaudy — gold trim, velvet cushions, a bubbling hookah stand. A heavy "
            "curtain hides a hidden compartment large enough to hold a small arsenal. "
            "A viewport shows {planet_view}. The Hutts take care of their own."
        ),
    },
    ("hutt", 5): {
        "label": "Hutt Vigo — Luxury Penthouse",
        "storage_max": 100,
        "room_name": "Vigo {name}'s Penthouse",
        "room_desc": (
            "A luxury penthouse dripping with Hutt-style opulence. Gold-plated fixtures, "
            "a sunken conversation pit with plush cushions, a fully stocked bar of "
            "exotic spirits, and a panoramic viewport showing {planet_view}. A private "
            "turbolift connects to the street below. Armed guards patrol the corridor "
            "outside. This is what power looks like in the Outer Rim."
        ),
    },
}

# Faction housing attachment points: (faction_code, planet) -> room_id
FACTION_QUARTER_LOTS = {
    ("empire", "tatooine"):    22,   # Tatooine Militia HQ / Garrison
    ("empire", "corellia"):    107,  # CorSec HQ (Imperial liaison)
    ("rebel", "tatooine"):     47,   # Outskirts - Abandoned Compound
    ("rebel", "nar_shaddaa"):  69,   # Undercity - Deep Warrens access
    ("hutt", "tatooine"):      19,   # Jabba's Townhouse - Audience Chamber
    ("hutt", "nar_shaddaa"):   72,   # Hutt Emissary Tower area
}

FACTION_HOME_PLANET = {
    "empire": "tatooine",
    "rebel":  "tatooine",
    "hutt":   "nar_shaddaa",
}

# ── Lot definitions for Drop 1 ────────────────────────────────────────────────
HOUSING_LOTS_DROP1 = [
    (29,  "tatooine",    "Spaceport Hotel",                "secured",   5),
    (21,  "tatooine",    "Mos Eisley Inn",                 "secured",   5),
    (60,  "nar_shaddaa", "Nar Shaddaa Promenade Hostel",   "contested", 5),
    (93,  "kessel",      "Kessel Station Barracks",        "contested", 5),
    (103, "corellia",    "Coronet City Spacers' Rest",     "secured",   5),
]

# ── Drop 4: Tier 3 Private Residence definitions ────────────────────────────
# tier=3, housing_type='private_residence'

TIER3_TYPES = {
    "small": {
        "label": "Small Dwelling",
        "rooms": 1,
        "cost": 5_000,
        "weekly_rent": 100,
        "storage_max": 40,
        "has_guest_list": False,
        "vendor_slots": 0,
    },
    "standard": {
        "label": "Standard Home",
        "rooms": 2,
        "cost": 12_000,
        "weekly_rent": 175,
        "storage_max": 80,
        "has_guest_list": True,
        "vendor_slots": 0,
    },
    "large": {
        "label": "Large Home",
        "rooms": 3,
        "cost": 25_000,
        "weekly_rent": 250,
        "storage_max": 120,
        "has_guest_list": True,
        "vendor_slots": 1,
    },
}

# Per-planet room descriptions for generated Tier 3 rooms
_TIER3_ROOM_DESCS = {
    "tatooine": [
        ("Main Room", "A whitewashed adobe chamber, cool despite the twin suns outside. "
         "Moisture farming equipment hangs from hooks on the wall. A bunk sits against "
         "the curved wall, and filtered light enters through a narrow slit window."),
        ("Back Room", "A smaller chamber carved deeper into the pourstone, naturally "
         "cooler than the main room. Storage crates line the walls. A faint smell of "
         "spice lingers from a previous tenant."),
        ("Cellar", "A subterranean room below the dwelling, dug into the sandstone. "
         "It's dark, quiet, and pleasantly cool. Perfect for storage, meditation, "
         "or hiding from unwanted visitors."),
    ],
    "nar_shaddaa": [
        ("Main Room", "A converted cargo bay with surprisingly high ceilings. Neon light "
         "from the promenade seeps through plasteel shutters. The walls are bare "
         "duracrete, patched and repainted by a succession of tenants."),
        ("Side Room", "A secondary chamber, originally part of the building's ductwork. "
         "Someone has widened it into a livable space. The hum of the city's infrastructure "
         "is a constant background presence."),
        ("Storage Bay", "A sealed compartment with its own door lock. The walls are "
         "insulated — sounds don't carry in or out. Previous owners clearly valued "
         "privacy over comfort."),
    ],
    "kessel": [
        ("Main Module", "A pressurized habitation module, standard Imperial mining colony "
         "issue. Functional gray walls, a fold-out bunk, and a small viewport showing "
         "the barren surface of Kessel."),
        ("Secondary Module", "An adjoining module connected by a sealed corridor. "
         "Climate control hums steadily. The air tastes of recycled atmosphere "
         "and distant spice processing."),
        ("Utility Pod", "A cramped utility pod adapted for storage. Environmental "
         "seals keep the contents safe from Kessel's unpredictable atmosphere."),
    ],
    "corellia": [
        ("Living Room", "A proper Corellian townhouse room with real wooden floors "
         "and plastered walls. Light streams through tall windows. A fireplace — real "
         "fire, not holographic — occupies one wall."),
        ("Bedroom", "An upstairs room with a proper bed, not a bunk. Corellian "
         "craftsmanship shows in the woodwork around the windows and doorframe. "
         "A small balcony overlooks the street."),
        ("Study", "A cozy room lined with shelves. A desk faces the window, with "
         "enough space for a holoterminal and personal effects. The door has a "
         "mechanical lock — Corellians trust old technology."),
    ],
}

# Lots where Tier 3 homes can be purchased (room_id, planet, label, security, max_homes)
HOUSING_LOTS_TIER3 = [
    (11,  "tatooine",    "South End Residences",             "secured",   4),
    (42,  "tatooine",    "Outskirts Homesteads",             "contested", 3),
    (61,  "nar_shaddaa", "Corellian Sector Apartments",      "contested", 4),
    (69,  "nar_shaddaa", "Undercity Hab-Block",              "lawless",   3),
    (86,  "kessel",      "Station Habitat Ring",             "contested", 2),
    (104, "corellia",    "Residential Quarter",              "secured",   4),
    (114, "corellia",    "Old Quarter Townhouses",           "contested", 3),
]

# Max homes a player can own per planet (prevents monopoly)
MAX_TIER3_PER_PLANET = 1
MAX_TIER3_TOTAL      = 4

_HOUSING_DIRS = ["northwest", "northeast", "southwest", "southeast",
                 "up", "down", "enter", "in"]

# ── Schema ────────────────────────────────────────────────────────────────────

HOUSING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS player_housing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    tier            INTEGER NOT NULL DEFAULT 1,
    housing_type    TEXT    NOT NULL DEFAULT 'rented_room',
    entry_room_id   INTEGER NOT NULL,
    room_ids        TEXT    NOT NULL DEFAULT '[]',
    storage         TEXT    NOT NULL DEFAULT '[]',
    storage_max     INTEGER NOT NULL DEFAULT 20,
    trophies        TEXT    NOT NULL DEFAULT '[]',
    guest_list      TEXT    NOT NULL DEFAULT '[]',
    purchase_price  INTEGER DEFAULT 0,
    weekly_rent     INTEGER DEFAULT 50,
    deposit         INTEGER DEFAULT 500,
    rent_paid_until REAL    DEFAULT 0,
    rent_overdue    INTEGER DEFAULT 0,
    door_direction  TEXT    NOT NULL DEFAULT 'northwest',
    exit_id_in      INTEGER DEFAULT NULL,
    exit_id_out     INTEGER DEFAULT NULL,
    faction_code    TEXT    DEFAULT NULL,
    created_at      REAL    NOT NULL,
    last_activity   REAL    DEFAULT 0,
    FOREIGN KEY (char_id)      REFERENCES characters(id),
    FOREIGN KEY (entry_room_id) REFERENCES rooms(id)
);

CREATE TABLE IF NOT EXISTS housing_lots (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id       INTEGER NOT NULL UNIQUE,
    planet        TEXT    NOT NULL,
    label         TEXT    NOT NULL,
    security      TEXT    NOT NULL DEFAULT 'contested',
    max_homes     INTEGER NOT NULL DEFAULT 5,
    current_homes INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);
"""

ROOMS_HOUSING_ID_SQL = "ALTER TABLE rooms ADD COLUMN housing_id INTEGER DEFAULT NULL REFERENCES player_housing(id);"
CHARACTERS_HOME_SQL  = "ALTER TABLE characters ADD COLUMN home_room_id INTEGER DEFAULT NULL REFERENCES rooms(id);"
_FACTION_CODE_COL    = "ALTER TABLE player_housing ADD COLUMN faction_code TEXT DEFAULT NULL;"
_HIDDEN_EXIT_COL     = "ALTER TABLE exits ADD COLUMN hidden_faction TEXT DEFAULT NULL;"


async def ensure_schema(db) -> None:
    """Create housing tables and columns if they don't exist. Idempotent."""
    try:
        for stmt in HOUSING_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db._db.execute(stmt)
        await db._db.commit()
    except Exception as e:
        log.warning("[housing] schema create error: %s", e)

    for sql in (ROOMS_HOUSING_ID_SQL, CHARACTERS_HOME_SQL,
                _FACTION_CODE_COL, _HIDDEN_EXIT_COL):
        try:
            await db._db.execute(sql)
            await db._db.commit()
        except Exception:
            pass  # Column already exists
    # Drop 7: intrusion log table
    await ensure_intrusion_schema(db)


async def seed_lots(db) -> None:
    """Insert the Drop 1 + Drop 4 housing lots if they don't exist yet."""
    all_lots = list(HOUSING_LOTS_DROP1) + list(HOUSING_LOTS_TIER3) + list(HOUSING_LOTS_TIER4)
    for room_id, planet, label, security, max_homes in all_lots:
        existing = await db._db.execute_fetchall(
            "SELECT id FROM housing_lots WHERE room_id = ?", (room_id,)
        )
        if not existing:
            try:
                await db._db.execute(
                    """INSERT INTO housing_lots
                       (room_id, planet, label, security, max_homes, current_homes)
                       VALUES (?, ?, ?, ?, ?, 0)""",
                    (room_id, planet, label, security, max_homes),
                )
            except Exception as e:
                log.warning("[housing] seed lot room %d: %s", room_id, e)
    await db._db.commit()
    log.info("[housing] Lots seeded.")


# ── Housing record helpers ────────────────────────────────────────────────────

async def get_housing(db, char_id: int) -> Optional[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM player_housing WHERE char_id = ? ORDER BY id DESC LIMIT 1",
        (char_id,),
    )
    return dict(rows[0]) if rows else None


async def get_housing_by_id(db, housing_id: int) -> Optional[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM player_housing WHERE id = ?", (housing_id,)
    )
    return dict(rows[0]) if rows else None


async def get_housing_for_room(db, room_id: int) -> Optional[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM player_housing WHERE room_ids LIKE ?",
        (f'%{room_id}%',),
    )
    for r in rows:
        ids = json.loads(r["room_ids"] or "[]")
        if room_id in ids:
            return dict(r)
    return None


def _storage(h: dict) -> list:
    s = h.get("storage", "[]")
    return json.loads(s) if isinstance(s, str) else (s or [])

def _room_ids(h: dict) -> list:
    r = h.get("room_ids", "[]")
    return json.loads(r) if isinstance(r, str) else (r or [])

def _trophies(h: dict) -> list:
    t = h.get("trophies", "[]")
    return json.loads(t) if isinstance(t, str) else (t or [])


# ── Lot helpers ───────────────────────────────────────────────────────────────

async def get_available_lots(db) -> list[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM housing_lots WHERE current_homes < max_homes ORDER BY planet, id"
    )
    return [dict(r) for r in rows]

async def get_lot(db, lot_id: int) -> Optional[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM housing_lots WHERE id = ?", (lot_id,)
    )
    return dict(rows[0]) if rows else None

async def get_lot_by_room(db, room_id: int) -> Optional[dict]:
    rows = await db._db.execute_fetchall(
        "SELECT * FROM housing_lots WHERE room_id = ?", (room_id,)
    )
    return dict(rows[0]) if rows else None

async def _pick_door_direction(db, entry_room_id: int) -> str:
    rows = await db._db.execute_fetchall(
        "SELECT direction FROM exits WHERE from_room_id = ?", (entry_room_id,)
    )
    used = {r["direction"] for r in rows}
    for d in _HOUSING_DIRS:
        if d not in used:
            return d
    for i in range(1, 100):
        d = f"door{i}"
        if d not in used:
            return d
    return "enter"


# ── Rent / Checkout ───────────────────────────────────────────────────────────

async def rent_room(db, char: dict, lot_id: int) -> dict:
    char_id = char["id"]
    existing = await get_housing(db, char_id)
    if existing:
        return {"ok": False, "msg": "You already have a place to stay. Use 'housing checkout' first."}

    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid location."}
    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    total_cost = TIER1_DEPOSIT + TIER1_WEEKLY_RENT
    if char.get("credits", 0) < total_cost:
        return {"ok": False,
                "msg": f"You need {total_cost:,}cr ({TIER1_DEPOSIT:,}cr deposit + {TIER1_WEEKLY_RENT:,}cr first week)."}

    entry_room = lot["room_id"]
    planet_label = lot["label"]
    room_name = f"{char['name']}'s Room"
    desc = (f"A modest rented room in {planet_label}. "
            f"A bunk, a small locker, and a view of {_planet_view(lot['planet'])}.")

    new_room_id = await db.create_room(
        name=room_name, desc_short=desc, desc_long=desc, zone_id=None,
        properties=json.dumps({"security": lot["security"], "private": True}),
    )

    door_dir = await _pick_door_direction(db, entry_room)
    exit_in_id  = await db.create_exit(entry_room, new_room_id, door_dir,
                                        f"{char['name']}'s room")
    exit_out_id = await db.create_exit(new_room_id, entry_room, "out", "Exit")

    char["credits"] = char.get("credits", 0) - total_cost
    await db.save_character(char_id, credits=char["credits"])

    now = time.time()
    cursor = await db._db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 1, 'rented_room', ?, ?, '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room, json.dumps([new_room_id]), TIER1_STORAGE_MAX,
         TIER1_WEEKLY_RENT, TIER1_DEPOSIT,
         now + RENT_TICK_INTERVAL, door_dir, exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    await db._db.execute(
        "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, new_room_id)
    )
    await db._db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )
    await db._db.commit()

    try:
        await db._db.execute(
            "UPDATE characters SET home_room_id = ? WHERE id = ?",
            (new_room_id, char_id),
        )
        await db._db.commit()
    except Exception:
        log.warning("rent_room: unhandled exception", exc_info=True)
        pass

    log.info("[housing] char %d rented room %d at lot %d (%s)",
             char_id, new_room_id, lot_id, lot["label"])

    return {
        "ok": True,
        "msg": (f"Room rented at {planet_label}! "
                f"Deposit: {TIER1_DEPOSIT:,}cr. "
                f"Rent: {TIER1_WEEKLY_RENT:,}cr/week. "
                f"Direction from lobby: {door_dir}."),
        "housing_id": housing_id, "room_id": new_room_id, "direction": door_dir,
    }


async def checkout_room(db, char: dict) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a rented room."}
    if h["housing_type"] not in ("rented_room", "faction_quarters", "private_residence"):
        return {"ok": False, "msg": "Use 'housing sell' to sell a purchased home."}

    room_ids = _room_ids(h)
    storage  = _storage(h)
    trophies = _trophies(h)

    # Return all items to inventory
    returned_count = 0
    all_items = storage + trophies
    if all_items:
        try:
            inv_raw = char.get("inventory", "{}")
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
            items = inv.get("items", [])
            items.extend(all_items)
            inv["items"] = items
            await db.save_character(char_id, inventory=json.dumps(inv))
            returned_count = len(all_items)
        except Exception as e:
            log.warning("[housing] checkout item return error: %s", e)

    # Refund deposit (faction quarters have 0)
    refund = h["deposit"] if h["rent_overdue"] == 0 else 0
    if refund > 0:
        char["credits"] = char.get("credits", 0) + refund
        await db.save_character(char_id, credits=char["credits"])

    # Remove exits
    try:
        if h.get("exit_id_in"):
            await db.delete_exit(h["exit_id_in"])
        if h.get("exit_id_out"):
            await db.delete_exit(h["exit_id_out"])
    except Exception as e:
        log.warning("[housing] checkout exit removal error: %s", e)

    # Delete rooms
    for rid in room_ids:
        try:
            await db._db.execute("DELETE FROM rooms WHERE id = ?", (rid,))
        except Exception as e:
            log.warning("[housing] checkout room delete error: %s", e)

    # Decrement lot occupancy (Tier 1 only)
    if h["housing_type"] == "rented_room":
        lot = await get_lot_by_room(db, h["entry_room_id"])
        if lot:
            await db._db.execute(
                "UPDATE housing_lots SET current_homes = MAX(0, current_homes - 1) WHERE id = ?",
                (lot["id"],),
            )

    await db._db.execute("DELETE FROM player_housing WHERE id = ?", (h["id"],))

    try:
        await db._db.execute(
            "UPDATE characters SET home_room_id = NULL WHERE id = ?", (char_id,)
        )
    except Exception:
        log.warning("checkout_room: unhandled exception", exc_info=True)
        pass

    await db._db.commit()
    log.info("[housing] char %d checked out of housing %d", char_id, h["id"])

    msg = "Room vacated."
    if refund > 0:
        msg += f" Deposit refunded: {refund:,}cr."
    if returned_count:
        msg += f" {returned_count} item(s) returned to your inventory."
    if h["rent_overdue"] > 0:
        msg += " Deposit forfeited due to overdue rent."
    return {"ok": True, "msg": msg}


# ── Storage operations ────────────────────────────────────────────────────────

async def housing_store(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a home to store things in."}

    storage = _storage(h)
    if len(storage) >= h["storage_max"]:
        return {"ok": False, "msg": f"Storage full ({h['storage_max']} items max)."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        match = None
        for i, it in enumerate(items):
            name = (it.get("name") or it.get("key") or "").lower()
            if item_key.lower() in name:
                match = items.pop(i)
                break
        if not match:
            return {"ok": False, "msg": f"You don't have '{item_key}' in your inventory."}

        inv["items"] = items
        storage.append(match)
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db._db.execute(
            "UPDATE player_housing SET storage = ?, last_activity = ? WHERE id = ?",
            (json.dumps(storage), time.time(), h["id"]),
        )
        await db._db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Stored: {item_name}. ({len(storage)}/{h['storage_max']} slots used)"}
    except Exception as e:
        log.warning("[housing] store error: %s", e)
        return {"ok": False, "msg": "Error storing item."}


async def housing_retrieve(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have any storage."}

    storage = _storage(h)
    match = None
    for i, it in enumerate(storage):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            match = storage.pop(i)
            break
    if not match:
        return {"ok": False, "msg": f"'{item_key}' not found in storage."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        items.append(match)
        inv["items"] = items
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db._db.execute(
            "UPDATE player_housing SET storage = ?, last_activity = ? WHERE id = ?",
            (json.dumps(storage), time.time(), h["id"]),
        )
        await db._db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Retrieved: {item_name}. ({len(storage)}/{h['storage_max']} slots used)"}
    except Exception as e:
        log.warning("[housing] retrieve error: %s", e)
        return {"ok": False, "msg": "Error retrieving item."}


# ── Rent tick ─────────────────────────────────────────────────────────────────

async def tick_housing_rent(db, session_mgr) -> None:
    """Weekly rent collection. Handles Tier 1 and Tier 3 (faction quarters are free)."""
    try:
        now = time.time()
        rows = await db._db.execute_fetchall(
            "SELECT * FROM player_housing WHERE weekly_rent > 0"
        )
        for row in rows:
            h = dict(row)
            if now < h["rent_paid_until"]:
                continue

            char_rows = await db._db.execute_fetchall(
                "SELECT * FROM characters WHERE id = ?", (h["char_id"],)
            )
            if not char_rows:
                continue
            char = dict(char_rows[0])

            if char.get("credits", 0) >= h["weekly_rent"]:
                new_credits = char["credits"] - h["weekly_rent"]
                await db.save_character(char["id"], credits=new_credits)
                await db._db.execute(
                    "UPDATE player_housing SET rent_paid_until = ?, rent_overdue = 0, last_activity = ? WHERE id = ?",
                    (now + RENT_TICK_INTERVAL, now, h["id"]),
                )
                log.info("[housing] Rent collected: char %d paid %dcr", char["id"], h["weekly_rent"])
                sess = session_mgr.find_by_character(char["id"])
                if sess:
                    await sess.send_line(
                        f"  \033[2m[HOUSING] Weekly rent of {h['weekly_rent']:,}cr collected. "
                        f"Balance: {new_credits:,}cr.\033[0m"
                    )
            else:
                overdue = h["rent_overdue"] + 1
                await db._db.execute(
                    "UPDATE player_housing SET rent_overdue = ? WHERE id = ?",
                    (overdue, h["id"]),
                )
                log.warning("[housing] Rent overdue: char %d week %d", char["id"], overdue)
                sess = session_mgr.find_by_character(char["id"])
                if sess:
                    if overdue >= TIER1_EVICT_WEEKS:
                        await sess.send_line(
                            f"  \033[1;31m[HOUSING] EVICTION: Rent overdue {overdue} weeks. "
                            f"Your room has been reclaimed.\033[0m"
                        )
                    else:
                        await sess.send_line(
                            f"  \033[1;33m[HOUSING] Rent overdue ({overdue} week(s)). "
                            f"Pay {h['weekly_rent']:,}cr or vacate within "
                            f"{TIER1_EVICT_WEEKS - overdue} week(s).\033[0m"
                        )
                if overdue >= TIER1_EVICT_WEEKS:
                    await checkout_room(db, dict(char_rows[0]))

        await db._db.commit()
    except Exception as e:
        log.warning("[housing] rent tick error: %s", e)


# ── Status display ────────────────────────────────────────────────────────────

_TIER_LABELS = {
    1: "Tier 1 Rented Room",
    2: "Tier 2 Faction Quarters",
    3: "Tier 3 Private Residence",
    4: "Tier 4 Shopfront",
    5: "Tier 5 Organization HQ",
}


async def get_housing_status_lines(db, char: dict) -> list[str]:
    h = await get_housing(db, char["id"])
    if not h:
        lots = await get_available_lots(db)
        lines = [
            "\033[1;37m── Housing ──\033[0m",
            "  You don't have a home.",
            "",
            "  Available locations:",
        ]
        for lot in lots:
            avail = lot["max_homes"] - lot["current_homes"]
            sec = lot["security"].upper()
            lines.append(
                f"    [{lot['id']}] {lot['label']:<40} "
                f"{avail} slots  [{sec}]"
            )
        lines.append("")
        lines.append("  Use \033[1;37mhousing rent <id>\033[0m to rent a room.")
        # Hint about faction quarters
        faction_id = char.get("faction_id", "independent")
        if faction_id and faction_id != "independent":
            min_rank = _faction_min_rank(faction_id)
            if min_rank is not None:
                lines.append(f"  \033[2mFaction quarters available at rank {min_rank}+.\033[0m")
        return lines

    room_ids = _room_ids(h)
    storage  = _storage(h)
    overdue  = h.get("rent_overdue", 0)
    paid_until = h.get("rent_paid_until", 0)
    days_left = max(0, int((paid_until - time.time()) / 86400))
    tier_label = _TIER_LABELS.get(h["tier"], f"Tier {h['tier']}")

    lines = [
        "\033[1;37m── Your Housing ──\033[0m",
        f"  Type:     {tier_label}",
        f"  Location: {_lot_label_for_housing(h)}",
        f"  Room(s):  {len(room_ids)} room",
    ]
    if h["housing_type"] == "faction_quarters":
        fc = h.get("faction_code", "")
        lines.append(f"  Faction:  {fc.title() if fc else 'Unknown'}")
        lines.append("  Rent:     Free (faction membership)")
    else:
        lines.append(
            f"  Rent:     {h['weekly_rent']:,}cr/week  "
            f"({'overdue ' + str(overdue) + ' week(s)' if overdue else str(days_left) + ' days until next payment'})"
        )
    lines.append(f"  Storage:  {len(storage)}/{h['storage_max']} slots used")
    tlist = _trophies(h)
    if tlist:
        lines.append(f"  Trophies: {len(tlist)}/10 mounted")
    if overdue > 0:
        lines.append(f"  \033[1;31mWARNING: Rent {overdue} week(s) overdue. "
                     f"Eviction in {TIER1_EVICT_WEEKS - overdue} week(s).\033[0m")
    lines.append("")
    lines.append("  Commands: \033[1;37mhousing storage  housing store <item>  housing retrieve <item>  housing checkout\033[0m")
    return lines


def _lot_label_for_housing(h: dict) -> str:
    return f"Room #{h['entry_room_id']}"

def _planet_view(planet: str) -> str:
    views = {
        "tatooine":    "twin suns baking the dusty street below",
        "nar_shaddaa": "neon-lit Nar Shaddaa skyline",
        "kessel":      "grey mine exhaust drifting past the porthole",
        "corellia":    "Coronet City spires glinting in the morning light",
    }
    return views.get(planet, "the street outside")


# ── Drop 2: Description editor + Trophies + Room naming ──────────────────────

DESC_MAX_LEN     = 2000
DESC_MIN_LEN     = 10
DESC_RENAME_COST = 1000
DESC_REDESC_COST = 0


async def set_room_name(db, char: dict, housing_id: int, new_name: str) -> dict:
    h = await get_housing_by_id(db, housing_id)
    if not h or h["char_id"] != char["id"]:
        return {"ok": False, "msg": "You don't own that room."}
    new_name = new_name.strip()[:80]
    if len(new_name) < 3:
        return {"ok": False, "msg": "Room name must be at least 3 characters."}

    room_ids = _room_ids(h)
    if not room_ids:
        return {"ok": False, "msg": "No rooms found."}
    room_id = room_ids[0]
    room_row = await db.get_room(room_id)
    if not room_row:
        return {"ok": False, "msg": "Room not found."}

    props = {}
    try:
        raw = room_row.get("properties", "{}")
        props = json.loads(raw) if isinstance(raw, str) else (raw or {})
    except Exception:
        log.warning("set_room_name: unhandled exception", exc_info=True)
        pass

    rename_count = props.get("rename_count", 0)
    if rename_count > 0 and DESC_RENAME_COST > 0:
        if char.get("credits", 0) < DESC_RENAME_COST:
            return {"ok": False,
                    "msg": f"Renaming again costs {DESC_RENAME_COST:,}cr. "
                           f"You have {char.get('credits', 0):,}cr."}
        char["credits"] -= DESC_RENAME_COST
        await db.save_character(char["id"], credits=char["credits"])

    props["rename_count"] = rename_count + 1
    old_name = room_row.get("name", "your room")
    await db.update_room(room_id, name=new_name, properties=json.dumps(props))
    return {"ok": True, "msg": f"Room renamed: '{old_name}' → '{new_name}'."}


async def set_room_description(db, char: dict, housing_id: int,
                                description: str) -> dict:
    h = await get_housing_by_id(db, housing_id)
    if not h or h["char_id"] != char["id"]:
        return {"ok": False, "msg": "You don't own that room."}

    desc = description.strip()
    if len(desc) < DESC_MIN_LEN:
        return {"ok": False, "msg": f"Description too short (minimum {DESC_MIN_LEN} characters)."}
    if len(desc) > DESC_MAX_LEN:
        desc = desc[:DESC_MAX_LEN]

    room_ids = _room_ids(h)
    if not room_ids:
        return {"ok": False, "msg": "No rooms found."}
    room_id = room_ids[0]

    await db.update_room(room_id, desc_short=desc, desc_long=desc)
    await db._db.execute(
        "UPDATE player_housing SET last_activity = ? WHERE id = ?",
        (time.time(), housing_id),
    )
    await db._db.commit()
    return {"ok": True, "msg": f"Description saved. ({len(desc)}/{DESC_MAX_LEN} characters)"}


async def trophy_mount(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have a home to display trophies in."}

    trophies = _trophies(h)
    if len(trophies) >= 10:
        return {"ok": False, "msg": "Trophy wall is full (10 items maximum)."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        match = None
        for i, it in enumerate(items):
            name = (it.get("name") or it.get("key") or "").lower()
            if item_key.lower() in name:
                match = items.pop(i)
                break
        if not match:
            return {"ok": False, "msg": f"You don't have '{item_key}' in your inventory."}

        inv["items"] = items
        trophies.append(match)
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db._db.execute(
            "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
            (json.dumps(trophies), time.time(), h["id"]),
        )
        await db._db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Mounted: {item_name} ({len(trophies)}/10 trophy slots used)."}
    except Exception as e:
        log.warning("[housing] trophy_mount error: %s", e)
        return {"ok": False, "msg": "Error mounting trophy."}


async def trophy_unmount(db, char: dict, item_key: str) -> dict:
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't have any trophies."}

    trophies = _trophies(h)
    match = None
    for i, it in enumerate(trophies):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            match = trophies.pop(i)
            break
    if not match:
        return {"ok": False, "msg": f"No trophy matching '{item_key}' found."}

    try:
        inv_raw = char.get("inventory", "{}")
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else (inv_raw or {})
        items = inv.get("items", [])
        items.append(match)
        inv["items"] = items
        await db.save_character(char_id, inventory=json.dumps(inv))
        await db._db.execute(
            "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
            (json.dumps(trophies), time.time(), h["id"]),
        )
        await db._db.commit()
        item_name = match.get("name") or match.get("key") or item_key
        return {"ok": True, "msg": f"Unmounted: {item_name}. Returned to inventory."}
    except Exception as e:
        log.warning("[housing] trophy_unmount error: %s", e)
        return {"ok": False, "msg": "Error unmounting trophy."}


async def get_room_housing_display(db, room_id: int) -> Optional[dict]:
    """Return housing display data for a room (used by look command)."""
    try:
        rows = await db._db.execute_fetchall(
            "SELECT housing_id FROM rooms WHERE id = ?", (room_id,)
        )
        if not rows or not rows[0]["housing_id"]:
            return None
        housing_id = rows[0]["housing_id"]
        h = await get_housing_by_id(db, housing_id)
        if not h:
            return None

        char_rows = await db._db.execute_fetchall(
            "SELECT name FROM characters WHERE id = ?", (h["char_id"],)
        )
        owner_name = char_rows[0]["name"] if char_rows else "Unknown"
        trophies = _trophies(h)
        return {
            "owner_name": owner_name,
            "trophies":   trophies,
            "housing_id": housing_id,
            "tier":       h.get("tier", 1),
            "faction_code": h.get("faction_code"),
        }
    except Exception as e:
        log.warning("[housing] get_room_housing_display error: %s", e)
        return None


# ══════════════════════════════════════════════════════════════════════════════
# DROP 3: Faction Quarters (Tier 2)
# ══════════════════════════════════════════════════════════════════════════════

def _faction_min_rank(faction_code: str) -> Optional[int]:
    """Return the minimum rank that qualifies for ANY faction quarter."""
    min_r = None
    for (fc, rank), _ in FACTION_QUARTER_TIERS.items():
        if fc == faction_code:
            if min_r is None or rank < min_r:
                min_r = rank
    return min_r


def _best_tier_for_rank(faction_code: str, rank_level: int) -> Optional[dict]:
    """Return the best faction quarter config for this rank, or None."""
    best = None
    best_rank = -1
    for (fc, min_rank), cfg in FACTION_QUARTER_TIERS.items():
        if fc == faction_code and rank_level >= min_rank and min_rank > best_rank:
            best = cfg
            best_rank = min_rank
    return best


def _planet_for_faction(faction_code: str) -> str:
    return FACTION_HOME_PLANET.get(faction_code, "tatooine")


def _entry_room_for_faction(faction_code: str, planet: str = None) -> Optional[int]:
    if planet is None:
        planet = _planet_for_faction(faction_code)
    return FACTION_QUARTER_LOTS.get((faction_code, planet))


async def assign_faction_quarters(db, char: dict, faction_code: str,
                                   rank_level: int,
                                   session=None) -> Optional[dict]:
    """
    Assign or upgrade faction quarters for a character.
    Called from promote(), join_faction() etc.
    If they have non-faction housing, notifies but does not evict.
    """
    tier_cfg = _best_tier_for_rank(faction_code, rank_level)
    if not tier_cfg:
        return None

    char_id = char["id"]
    existing = await get_housing(db, char_id)

    # Upgrade in-place if already has quarters for this faction
    if existing and existing.get("housing_type") == "faction_quarters" \
       and existing.get("faction_code") == faction_code:
        if existing["storage_max"] < tier_cfg["storage_max"]:
            room_ids = _room_ids(existing)
            if room_ids:
                planet = _planet_for_faction(faction_code)
                new_desc = tier_cfg["room_desc"].replace(
                    "{planet_view}", _planet_view(planet))
                new_name = tier_cfg["room_name"].replace(
                    "{name}", char.get("name", "Unknown"))
                await db.update_room(room_ids[0], name=new_name,
                                     desc_short=new_desc, desc_long=new_desc)
            await db._db.execute(
                "UPDATE player_housing SET storage_max = ?, last_activity = ? WHERE id = ?",
                (tier_cfg["storage_max"], time.time(), existing["id"]),
            )
            await db._db.commit()
            msg = (f"Quarters upgraded: {tier_cfg['label']}. "
                   f"Storage expanded to {tier_cfg['storage_max']} slots.")
            log.info("[housing] Faction quarters upgraded: char %d, %s rank %d",
                     char_id, faction_code, rank_level)
            if session:
                await session.send_line(f"  \033[1;36m[HOUSING] {msg}\033[0m")
            return {"ok": True, "msg": msg}
        return None  # Already at/above tier

    # Don't evict existing non-faction housing
    if existing and existing.get("housing_type") != "faction_quarters":
        if session:
            await session.send_line(
                f"  \033[2m[HOUSING] You qualify for {tier_cfg['label']}, "
                f"but you already have housing. Use 'housing checkout' first "
                f"if you want faction quarters instead.\033[0m")
        return None

    # Create new faction quarters
    planet = _planet_for_faction(faction_code)
    entry_room_id = _entry_room_for_faction(faction_code, planet)
    if entry_room_id is None:
        log.warning("[housing] No entry room for faction %s on %s",
                    faction_code, planet)
        return None

    entry_room = await db.get_room(entry_room_id)
    if not entry_room:
        log.warning("[housing] Entry room %d for faction %s does not exist",
                    entry_room_id, faction_code)
        return None

    char_name = char.get("name", "Unknown")
    room_name = tier_cfg["room_name"].replace("{name}", char_name)
    room_desc = tier_cfg["room_desc"].replace("{planet_view}", _planet_view(planet))

    entry_security = "secured"
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "secured")
    except Exception:
        log.warning("assign_faction_quarters: unhandled exception", exc_info=True)
        pass

    new_room_id = await db.create_room(
        name=room_name, desc_short=room_desc, desc_long=room_desc,
        zone_id=None,
        properties=json.dumps({
            "security": entry_security, "private": True,
            "faction_quarters": faction_code,
        }),
    )

    door_dir = await _pick_door_direction(db, entry_room_id)
    is_rebel = faction_code == "rebel"

    exit_in_id = await db.create_exit(entry_room_id, new_room_id, door_dir,
                                       room_name)
    # Mark rebel exits as hidden
    if is_rebel:
        try:
            await db._db.execute(
                "UPDATE exits SET hidden_faction = ? WHERE id = ?",
                ("rebel", exit_in_id),
            )
        except Exception as e:
            log.warning("[housing] hidden exit set error: %s", e)

    exit_out_id = await db.create_exit(new_room_id, entry_room_id, "out",
                                        entry_room.get("name", "Exit"))

    now = time.time()
    cursor = await db._db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, rent_paid_until, door_direction,
            exit_id_in, exit_id_out, faction_code, created_at, last_activity)
           VALUES (?, 2, 'faction_quarters', ?, ?, '[]', ?,
                   0, 0, 0, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room_id, json.dumps([new_room_id]),
         tier_cfg["storage_max"], door_dir, exit_in_id, exit_out_id,
         faction_code, now, now),
    )
    housing_id = cursor.lastrowid

    await db._db.execute(
        "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, new_room_id)
    )

    # Set as home if none set
    try:
        rows = await db._db.execute_fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (char_id,)
        )
        if not rows or not rows[0]["home_room_id"]:
            await db._db.execute(
                "UPDATE characters SET home_room_id = ? WHERE id = ?",
                (new_room_id, char_id),
            )
    except Exception:
        log.warning("assign_faction_quarters: unhandled exception", exc_info=True)
        pass

    await db._db.commit()

    msg = (f"Assigned: {tier_cfg['label']}. "
           f"Storage: {tier_cfg['storage_max']} slots. "
           f"Direction from {entry_room.get('name', 'lobby')}: {door_dir}.")
    log.info("[housing] Faction quarters assigned: char %d, %s rank %d, room %d",
             char_id, faction_code, rank_level, new_room_id)

    if session:
        await session.send_line(f"  \033[1;36m[HOUSING] {msg}\033[0m")

    return {"ok": True, "msg": msg, "housing_id": housing_id,
            "room_id": new_room_id}


async def revoke_faction_quarters(db, char: dict, faction_code: str,
                                    session=None) -> Optional[dict]:
    """Revoke faction quarters on leave/expulsion. Contents returned."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return None
    if h.get("housing_type") != "faction_quarters":
        return None
    if h.get("faction_code") != faction_code:
        return None

    result = await checkout_room(db, char)
    if session:
        await session.send_line(
            f"  \033[1;33m[HOUSING] Your faction quarters have been revoked. "
            f"{result.get('msg', '')}\033[0m")
    log.info("[housing] Faction quarters revoked: char %d, %s", char_id, faction_code)
    return result


async def check_faction_quarters_on_rank_change(
        db, char: dict, faction_code: str, new_rank: int,
        session=None) -> None:
    """Called after promotion or demotion. Upgrades or revokes quarters."""
    min_rank = _faction_min_rank(faction_code)
    if min_rank is None:
        return
    if new_rank < min_rank:
        await revoke_faction_quarters(db, char, faction_code, session=session)
        return
    await assign_faction_quarters(db, char, faction_code, new_rank,
                                   session=session)


async def is_exit_visible(db, exit_row: dict, char: dict) -> bool:
    """Check if an exit is visible to a character (hidden faction exits)."""
    hidden = exit_row.get("hidden_faction")
    if not hidden:
        return True
    return char.get("faction_id", "independent") == hidden


# ══════════════════════════════════════════════════════════════════════════════
# DROP 4: Private Residences (Tier 3)
# ══════════════════════════════════════════════════════════════════════════════

def _guest_list(h: dict) -> list:
    g = h.get("guest_list", "[]")
    return json.loads(g) if isinstance(g, str) else (g or [])


async def get_tier3_available_lots(db) -> list[dict]:
    """Return Tier 3 lots with open slots."""
    all_lot_ids = [r for r, *_ in HOUSING_LOTS_TIER3]
    rows = await db._db.execute_fetchall(
        "SELECT * FROM housing_lots WHERE current_homes < max_homes ORDER BY planet, id"
    )
    return [dict(r) for r in rows if r["room_id"] in all_lot_ids]


async def purchase_home(db, char: dict, lot_id: int, home_type: str) -> dict:
    """
    Purchase a Tier 3 private residence.
    Returns {"ok": bool, "msg": str, ...}.
    """
    char_id = char["id"]

    # Validate type
    cfg = TIER3_TYPES.get(home_type)
    if not cfg:
        types_str = ", ".join(f"'{k}' ({v['label']}, {v['cost']:,}cr)" for k, v in TIER3_TYPES.items())
        return {"ok": False, "msg": f"Unknown home type '{home_type}'. Options: {types_str}"}

    # Check existing housing — allow if they have Tier 1 or Tier 2 (upgrade path)
    existing = await get_housing(db, char_id)
    if existing and existing["tier"] >= 3:
        return {"ok": False,
                "msg": "You already own a home. Use 'housing sell' first."}

    # Check per-planet limit
    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid lot."}

    lot_planet = lot["planet"]
    existing_on_planet = await db._db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 3",
        (char_id,),
    )
    if existing_on_planet and existing_on_planet[0]["cnt"] >= MAX_TIER3_PER_PLANET:
        return {"ok": False, "msg": f"You already own a home on this planet (max {MAX_TIER3_PER_PLANET})."}

    # Check lot availability
    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    # Credit check
    if char.get("credits", 0) < cfg["cost"]:
        return {"ok": False,
                "msg": f"A {cfg['label']} costs {cfg['cost']:,}cr. You have {char.get('credits', 0):,}cr."}

    entry_room_id = lot["room_id"]
    entry_room = await db.get_room(entry_room_id)
    if not entry_room:
        return {"ok": False, "msg": "Lot room not found."}

    # Get security from entry room
    entry_security = "contested"
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "contested")
    except Exception:
        log.warning("purchase_home: unhandled exception", exc_info=True)
        pass

    # Get planet room descs
    planet_descs = _TIER3_ROOM_DESCS.get(lot_planet, _TIER3_ROOM_DESCS["tatooine"])
    char_name = char.get("name", "Unknown")

    # Create rooms
    room_ids = []
    for i in range(cfg["rooms"]):
        r_name, r_desc = planet_descs[min(i, len(planet_descs) - 1)]
        if i == 0:
            r_name = f"{char_name}'s {cfg['label']}"
        else:
            r_name = f"{char_name}'s {r_name}"

        rid = await db.create_room(
            name=r_name, desc_short=r_desc, desc_long=r_desc,
            zone_id=None,
            properties=json.dumps({
                "security": entry_security, "private": True,
                "owned_home": True,
            }),
        )
        room_ids.append(rid)

    # Link rooms: entry → room 0, then chain room 0 → room 1 → room 2
    door_dir = await _pick_door_direction(db, entry_room_id)
    exit_in_id = await db.create_exit(
        entry_room_id, room_ids[0], door_dir, f"{char_name}'s {cfg['label']}")
    exit_out_id = await db.create_exit(
        room_ids[0], entry_room_id, "out", entry_room.get("name", "Exit"))

    # Internal room exits
    for i in range(len(room_ids) - 1):
        r_name_next = planet_descs[min(i + 1, len(planet_descs) - 1)][0]
        await db.create_exit(room_ids[i], room_ids[i + 1], "in",
                             r_name_next)
        await db.create_exit(room_ids[i + 1], room_ids[i], "out",
                             planet_descs[min(i, len(planet_descs) - 1)][0])

    # Charge credits
    char["credits"] = char.get("credits", 0) - cfg["cost"]
    await db.save_character(char_id, credits=char["credits"])

    # If they have existing Tier 1/2 housing, evict it first
    if existing:
        await checkout_room(db, char)

    # Create housing record
    now = time.time()
    cursor = await db._db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, purchase_price,
            rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 3, 'private_residence', ?, ?, '[]', ?,
                   ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, entry_room_id, json.dumps(room_ids), cfg["storage_max"],
         cfg["weekly_rent"], cfg["cost"],
         now + RENT_TICK_INTERVAL, door_dir,
         exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    # Mark all rooms as housing-owned
    for rid in room_ids:
        await db._db.execute(
            "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, rid)
        )

    # Update lot occupancy
    await db._db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )

    # Set as home
    try:
        await db._db.execute(
            "UPDATE characters SET home_room_id = ? WHERE id = ?",
            (room_ids[0], char_id),
        )
    except Exception:
        log.warning("purchase_home: unhandled exception", exc_info=True)
        pass

    await db._db.commit()

    log.info("[housing] char %d purchased %s at lot %d (%s), rooms %s",
             char_id, home_type, lot_id, lot["label"], room_ids)

    return {
        "ok": True,
        "msg": (f"Purchased: {cfg['label']} at {lot['label']}! "
                f"Cost: {cfg['cost']:,}cr. "
                f"Rent: {cfg['weekly_rent']:,}cr/week. "
                f"{cfg['rooms']} room(s), {cfg['storage_max']} storage slots. "
                f"Direction from {entry_room.get('name', 'lobby')}: {door_dir}."),
        "housing_id": housing_id,
        "room_ids": room_ids,
        "direction": door_dir,
    }


async def sell_home(db, char: dict) -> dict:
    """Sell a Tier 3 private residence. 50% refund, contents returned."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't own a home."}
    if h["housing_type"] != "private_residence":
        return {"ok": False,
                "msg": "Only purchased homes can be sold. "
                       "Use 'housing checkout' for rented rooms."}

    refund = h.get("purchase_price", 0) // 2

    # Checkout returns items and deletes rooms
    result = await checkout_room(db, char)
    if not result["ok"]:
        return result

    # Add refund
    if refund > 0:
        char_row = await db._db.execute_fetchall(
            "SELECT credits FROM characters WHERE id = ?", (char_id,)
        )
        if char_row:
            new_credits = char_row[0]["credits"] + refund
            await db.save_character(char_id, credits=new_credits)
            await db._db.commit()

    msg = f"Home sold. Refund: {refund:,}cr (50% of purchase price)."
    if "item(s)" in result.get("msg", ""):
        msg += f" {result['msg']}"

    log.info("[housing] char %d sold home, refund %dcr", char_id, refund)
    return {"ok": True, "msg": msg}


# ── Guest list management ────────────────────────────────────────────────────

async def guest_add(db, char: dict, guest_name: str) -> dict:
    """Add a player to the housing guest list."""
    h = await get_housing(db, char["id"])
    if not h:
        return {"ok": False, "msg": "You don't have a home."}
    if h["tier"] < 3 and h["housing_type"] != "faction_quarters":
        return {"ok": False,
                "msg": "Guest lists are available for Standard Homes and above."}

    guests = _guest_list(h)
    if len(guests) >= 10:
        return {"ok": False, "msg": "Guest list is full (10 maximum)."}

    # Find the guest character
    rows = await db._db.execute_fetchall(
        "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
        (guest_name.strip(),),
    )
    if not rows:
        return {"ok": False, "msg": f"Player '{guest_name}' not found."}
    guest = dict(rows[0])

    if guest["id"] == char["id"]:
        return {"ok": False, "msg": "You can't add yourself to your own guest list."}

    # Check for duplicates
    for g in guests:
        if g.get("id") == guest["id"]:
            return {"ok": False, "msg": f"{guest['name']} is already on your guest list."}

    guests.append({"id": guest["id"], "name": guest["name"]})
    await db._db.execute(
        "UPDATE player_housing SET guest_list = ?, last_activity = ? WHERE id = ?",
        (json.dumps(guests), time.time(), h["id"]),
    )
    await db._db.commit()
    return {"ok": True, "msg": f"Added {guest['name']} to your guest list."}


async def guest_remove(db, char: dict, guest_name: str) -> dict:
    """Remove a player from the housing guest list."""
    h = await get_housing(db, char["id"])
    if not h:
        return {"ok": False, "msg": "You don't have a home."}

    guests = _guest_list(h)
    match_idx = None
    for i, g in enumerate(guests):
        if g.get("name", "").lower() == guest_name.strip().lower():
            match_idx = i
            break
    if match_idx is None:
        return {"ok": False, "msg": f"'{guest_name}' is not on your guest list."}

    removed = guests.pop(match_idx)
    await db._db.execute(
        "UPDATE player_housing SET guest_list = ?, last_activity = ? WHERE id = ?",
        (json.dumps(guests), time.time(), h["id"]),
    )
    await db._db.commit()
    return {"ok": True, "msg": f"Removed {removed.get('name', guest_name)} from your guest list."}


async def get_guest_list_display(db, char: dict) -> list[str]:
    """Return formatted guest list lines."""
    h = await get_housing(db, char["id"])
    if not h:
        return ["  You don't have a home."]
    guests = _guest_list(h)
    if not guests:
        return ["  Guest list is empty.", "  Use 'housing guest add <player>' to add someone."]
    lines = [f"  \033[1;37mGuest List ({len(guests)}/10):\033[0m"]
    for g in guests:
        lines.append(f"    - {g.get('name', 'Unknown')}")
    return lines


async def get_tier3_listing_lines(db, char: dict) -> list[str]:
    """Return formatted Tier 3 lot listing for the buy command."""
    lots = await get_tier3_available_lots(db)
    if not lots:
        return ["  No lots available for private residences."]

    lines = [
        "\033[1;37m── Available Lots ──\033[0m",
        "",
    ]
    for lot in lots:
        avail = lot["max_homes"] - lot["current_homes"]
        sec = lot["security"].upper()
        discount = ""
        if lot["security"] == "lawless":
            discount = " \033[1;33m(-50% rent)\033[0m"
        elif lot["security"] == "contested":
            discount = " \033[2m(-25% rent)\033[0m"
        lines.append(
            f"    [{lot['id']}] {lot['label']:<40} "
            f"{avail} slots  [{sec}]{discount}"
        )

    lines.append("")
    lines.append("  \033[1;37mHome Types:\033[0m")
    for key, cfg in TIER3_TYPES.items():
        lines.append(
            f"    {key:<10} {cfg['label']:<20} "
            f"{cfg['rooms']} room(s)  {cfg['cost']:>7,}cr  "
            f"{cfg['weekly_rent']:>3}cr/wk  {cfg['storage_max']} storage"
        )
    lines.append("")
    lines.append("  Use \033[1;37mhousing buy <type> <lot_id>\033[0m to purchase.")
    return lines


# ══════════════════════════════════════════════════════════════════════════════
# DROP 5: Shopfront Residences (Tier 4)
# ══════════════════════════════════════════════════════════════════════════════
"""
Tier 4 shopfronts: a home with a public-facing shop room integrated.
The shop room is freely accessible by all; private rooms behind it are
owner/guest-only.  Vendor droids in the shop room appear in the planet-wide
`market search` directory and bypass the per-room droid cap (since the room
IS a dedicated shop).  Shopfront owners get +1 to their personal droid cap.

From design doc §2.5:
  Market Stall:    1 shop + 1 private,  15,000cr, 200cr/wk, 2 droids
  Merchant's Shop: 1 shop + 2 private,  28,000cr, 300cr/wk, 3 droids
  Trading House:   2 shop + 3 private,  40,000cr, 400cr/wk, 4 droids
"""

TIER4_TYPES = {
    "stall": {
        "label":        "Market Stall",
        "shop_rooms":   1,
        "private_rooms": 1,
        "cost":         15_000,
        "weekly_rent":  200,
        "storage_max":  60,
        "droid_slots":  2,    # vendor droids allowed in shop room(s)
    },
    "shop": {
        "label":        "Merchant's Shop",
        "shop_rooms":   1,
        "private_rooms": 2,
        "cost":         28_000,
        "weekly_rent":  300,
        "storage_max":  100,
        "droid_slots":  3,
    },
    "trading_house": {
        "label":        "Trading House",
        "shop_rooms":   2,
        "private_rooms": 3,
        "cost":         40_000,
        "weekly_rent":  400,
        "storage_max":  150,
        "droid_slots":  4,
    },
}

# Security discount multipliers for Tier 4 rent (mirrors Tier 3 pattern)
_TIER4_SECURITY_DISCOUNT = {"lawless": 0.50, "contested": 0.75, "secured": 1.0}

MAX_TIER4_PER_CHAR  = 2   # can own multiple shopfronts (different planets)
MAX_TIER4_PER_PLANET = 1

HOUSING_LOTS_TIER4 = [
    # (room_id, planet, label, security, max_shopfronts)
    (8,   "tatooine",    "Market Row Stalls",         "contested", 4),
    (11,  "tatooine",    "Spaceport Commercial Strip", "secured",   3),
    (46,  "nar_shaddaa", "Promenade Market",           "contested", 4),
    (69,  "nar_shaddaa", "Undercity Black Market",     "lawless",   2),
    (86,  "kessel",      "Station Bazaar",             "contested", 2),
    (104, "corellia",    "Commercial Quarter",         "secured",   4),
]

# Shop room descriptions — publicly accessible front rooms
_TIER4_SHOP_DESCS = {
    "tatooine": [
        ("Shop Floor", "A sun-bleached commerce space opening onto Market Row. "
         "Display racks line the walls; a worn counter runs the width of the room. "
         "The smell of dust and machine oil mingles with spice from neighbouring stalls."),
        ("Front Showroom", "A larger front room with arched doorways opening to the street. "
         "Good light for displaying wares. A rolled-up security shutter hangs above the entrance."),
    ],
    "nar_shaddaa": [
        ("Shop Front", "A converted hab unit repurposed as a storefront. Neon from the Promenade "
         "casts colored light across the display shelves. The floor is polished durasteel, "
         "and a security camera covers the entrance."),
        ("Display Floor", "A wide commercial space with vaulted ceilings typical of the "
         "Promenade's older architecture. Track lighting illuminates display cases. "
         "The place smells faintly of coolant and freshly minted credit chips."),
    ],
    "kessel": [
        ("Station Kiosk", "A pressurized commercial module mounted to the station ring. "
         "Viewport shows the pocked surface of Kessel. Display panels glow with inventory "
         "listings. Climate-controlled and professionally maintained."),
    ],
    "corellia": [
        ("Shopfront", "A proper Corellian commercial space with wide display windows facing "
         "the street. Hardwood floors, plastered walls, and a hand-lettered sign space above "
         "the doorway. Smells like lacquer and honest commerce."),
        ("Trade Floor", "A two-storey commercial space with a mezzanine viewing gallery. "
         "CorSec-approved safety seals are visible on the exits. Good bones."),
    ],
}

# Private room descriptions (back rooms, owner-only)
_TIER4_PRIVATE_DESCS = {
    "tatooine": [
        ("Back Room", "The private quarters behind the shop. A bunk, storage shelves, "
         "and a small workbench. Access is locked from the shop floor."),
        ("Storage Room", "A sealed storage room with reinforced shelving. "
         "No windows. The door lock looks recently upgraded."),
        ("Owner's Suite", "A comfortable back room furnished with a proper bed "
         "and a personal terminal. Considerably nicer than the shop floor suggests."),
    ],
    "nar_shaddaa": [
        ("Owner's Quarters", "A private back room sealed from the shop floor. "
         "Sound-dampened walls, a bunk, and a mini-refrigeration unit. Cozy in the Nar Shaddaa sense."),
        ("Storage Bay", "A locked bay behind the shop. Reinforced door with "
         "a biometric reader. Whatever's in here, it stays in here."),
        ("Private Office", "A small office with a desk, a secure comms terminal, "
         "and a view of the building's internal corridors. No windows — intentional."),
    ],
    "kessel": [
        ("Hab Module", "A standard-issue habitat pod adjoining the commercial kiosk. "
         "Bunk, storage, and a sealed airlock connecting to the shop side."),
        ("Supply Room", "A pressurized storage compartment. Cold, quiet, and very locked."),
    ],
    "corellia": [
        ("Living Quarters", "Upstairs from the shop, a proper apartment. "
         "Wooden floors, tall windows, and a kitchen alcove. Smells like home."),
        ("Storeroom", "A ground-floor back room with reinforced shelving and a "
         "loading door to the alley. Good for bulk goods."),
        ("Upstairs Office", "A private office above the shop floor. A desk faces "
         "a window overlooking the commercial quarter. Lockable from inside."),
    ],
}


async def get_tier4_listing_lines(db, char: dict) -> list[str]:
    """Return formatted Tier 4 shopfront lot listing for a character."""
    lines = [
        "\033[1;37m── Shopfront Residences (Tier 4) ──\033[0m",
        "  A home with an integrated public shop room and vendor droid directory listing.",
        "",
        "  \033[1;36mAvailable Lots:\033[0m",
        f"  {'ID':<5} {'Location':<35} {'Planet':<12} {'Security':<12} {'Slots'}",
        "  " + "─" * 72,
    ]
    for room_id, planet, label, security, max_sf in HOUSING_LOTS_TIER4:
        lot = await db._db.execute_fetchall(
            "SELECT current_homes, max_homes FROM housing_lots WHERE room_id = ?",
            (room_id,),
        )
        current = lot[0]["current_homes"] if lot else 0
        max_h   = lot[0]["max_homes"]     if lot else max_sf
        avail   = max_h - current
        sec_color = {
            "secured":   "\033[1;34m",
            "contested": "\033[1;33m",
            "lawless":   "\033[1;31m",
        }.get(security, "\033[0m")
        discount = " (−50% rent)" if security == "lawless" else " (−25% rent)" if security == "contested" else ""
        lines.append(
            f"  {room_id:<5} {label:<35} {planet.title():<12} "
            f"{sec_color}{security:<12}\033[0m {avail}/{max_h}{discount}"
        )

    lines += [
        "",
        "  \033[1;37mShopfront Types:\033[0m",
    ]
    for key, cfg in TIER4_TYPES.items():
        total_rooms = cfg["shop_rooms"] + cfg["private_rooms"]
        lines.append(
            f"    {key:<14} {cfg['label']:<22} "
            f"{cfg['shop_rooms']} shop + {cfg['private_rooms']} private  "
            f"{cfg['cost']:>8,}cr  {cfg['weekly_rent']:>3}cr/wk  "
            f"{cfg['droid_slots']} droids"
        )
    lines += [
        "",
        "  Shop rooms are publicly accessible. Private rooms are owner/guest-only.",
        "  Vendor droids in shop rooms appear in the planet-wide 'market search' directory.",
        "",
        "  Use \033[1;37mhousing shopfront <type> <lot_id>\033[0m to purchase.",
    ]
    return lines


async def purchase_shopfront(db, char: dict, lot_id: int,
                              sf_type: str) -> dict:
    """
    Purchase a Tier 4 shopfront residence.
    Returns {\"ok\": bool, \"msg\": str, ...}.
    """
    char_id = char["id"]
    cfg = TIER4_TYPES.get(sf_type)
    if not cfg:
        type_str = ", ".join(f"'{k}'" for k in TIER4_TYPES)
        return {"ok": False, "msg": f"Unknown shopfront type '{sf_type}'. Options: {type_str}"}

    # Can't already own a Tier 4 on this planet
    lot = await get_lot(db, lot_id)
    if not lot:
        return {"ok": False, "msg": "Invalid lot ID."}
    if lot["room_id"] not in [r for r, *_ in HOUSING_LOTS_TIER4]:
        return {"ok": False, "msg": "That lot is not a shopfront location."}

    lot_planet = lot["planet"]

    existing_t4_planet = await db._db.execute_fetchall(
        """SELECT COUNT(*) as cnt FROM player_housing
           WHERE char_id = ? AND tier = 4
           AND entry_room_id IN (
               SELECT room_id FROM housing_lots WHERE planet = ?
           )""",
        (char_id, lot_planet),
    )
    if existing_t4_planet and existing_t4_planet[0]["cnt"] >= MAX_TIER4_PER_PLANET:
        return {"ok": False,
                "msg": f"You already own a shopfront on {lot_planet.title()} (max {MAX_TIER4_PER_PLANET})."}

    total_t4 = await db._db.execute_fetchall(
        "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 4",
        (char_id,),
    )
    if total_t4 and total_t4[0]["cnt"] >= MAX_TIER4_PER_CHAR:
        return {"ok": False,
                "msg": f"You already own {MAX_TIER4_PER_CHAR} shopfronts (maximum)."}

    if lot["current_homes"] >= lot["max_homes"]:
        return {"ok": False, "msg": f"{lot['label']} is full. Try another location."}

    if char.get("credits", 0) < cfg["cost"]:
        return {"ok": False,
                "msg": f"A {cfg['label']} costs {cfg['cost']:,}cr. "
                       f"You have {char.get('credits', 0):,}cr."}

    entry_room = await db.get_room(lot["room_id"])
    if not entry_room:
        return {"ok": False, "msg": "Lot room not found."}

    # Determine effective security + rent discount
    try:
        props_raw = entry_room.get("properties", "{}")
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        entry_security = props.get("security", "contested")
    except Exception:
        entry_security = "contested"
    discount = _TIER4_SECURITY_DISCOUNT.get(entry_security, 1.0)
    effective_rent = max(50, int(cfg["weekly_rent"] * discount))

    char_name = char.get("name", "Unknown")
    shop_descs    = _TIER4_SHOP_DESCS.get(lot_planet, _TIER4_SHOP_DESCS["tatooine"])
    private_descs = _TIER4_PRIVATE_DESCS.get(lot_planet, _TIER4_PRIVATE_DESCS["tatooine"])

    all_room_ids = []
    shop_room_ids    = []
    private_room_ids = []

    # Create shop rooms (publicly accessible)
    for i in range(cfg["shop_rooms"]):
        desc_pair = shop_descs[min(i, len(shop_descs) - 1)]
        r_name = f"{char_name}'s {desc_pair[0]}"
        rid = await db.create_room(
            name=r_name, desc_short=desc_pair[1], desc_long=desc_pair[1],
            zone_id=None,
            properties=json.dumps({
                "security": entry_security,
                "private": False,        # shop rooms are PUBLIC
                "owned_home": True,
                "is_shopfront": True,
                "shopfront_owner_id": char_id,
                "droid_slots": cfg["droid_slots"],
            }),
        )
        all_room_ids.append(rid)
        shop_room_ids.append(rid)

    # Create private rooms (owner/guest-only)
    for i in range(cfg["private_rooms"]):
        desc_pair = private_descs[min(i, len(private_descs) - 1)]
        r_name = f"{char_name}'s {desc_pair[0]}"
        rid = await db.create_room(
            name=r_name, desc_short=desc_pair[1], desc_long=desc_pair[1],
            zone_id=None,
            properties=json.dumps({
                "security": entry_security,
                "private": True,
                "owned_home": True,
                "is_shopfront": False,
            }),
        )
        all_room_ids.append(rid)
        private_room_ids.append(rid)

    # Wire exits: public street → first shop room
    door_dir = await _pick_door_direction(db, lot["room_id"])
    exit_in_id = await db.create_exit(
        lot["room_id"], shop_room_ids[0], door_dir,
        f"{char_name}'s {cfg['label']}"
    )
    exit_out_id = await db.create_exit(
        shop_room_ids[0], lot["room_id"], "out",
        entry_room.get("name", "Exit")
    )

    # Chain shop rooms together (if Trading House with 2 shop rooms)
    for i in range(len(shop_room_ids) - 1):
        await db.create_exit(shop_room_ids[i], shop_room_ids[i + 1],
                              "in", "Back of Shop")
        await db.create_exit(shop_room_ids[i + 1], shop_room_ids[i],
                              "out", "Shop Floor")

    # Shop → private transition (locked private door)
    if private_room_ids:
        last_shop = shop_room_ids[-1]
        await db.create_exit(last_shop, private_room_ids[0],
                              "northwest", "Private Quarters")
        await db.create_exit(private_room_ids[0], last_shop,
                              "out", "Shop Floor")

    # Chain private rooms together
    for i in range(len(private_room_ids) - 1):
        pdesc_a = private_descs[min(i,     len(private_descs) - 1)][0]
        pdesc_b = private_descs[min(i + 1, len(private_descs) - 1)][0]
        await db.create_exit(private_room_ids[i],     private_room_ids[i + 1],
                              "in",  pdesc_b)
        await db.create_exit(private_room_ids[i + 1], private_room_ids[i],
                              "out", pdesc_a)

    # Charge credits
    char["credits"] = char.get("credits", 0) - cfg["cost"]
    await db.save_character(char_id, credits=char["credits"])

    # Create housing record
    now = time.time()
    cursor = await db._db.execute(
        """INSERT INTO player_housing
           (char_id, tier, housing_type, entry_room_id, room_ids, storage,
            storage_max, weekly_rent, deposit, purchase_price,
            rent_paid_until, door_direction,
            exit_id_in, exit_id_out, created_at, last_activity)
           VALUES (?, 4, 'shopfront', ?, ?, '[]', ?,
                   ?, 0, ?, ?, ?, ?, ?, ?, ?)""",
        (char_id, lot["room_id"], json.dumps(all_room_ids),
         cfg["storage_max"], effective_rent, cfg["cost"],
         now + RENT_TICK_INTERVAL, door_dir,
         exit_in_id, exit_out_id, now, now),
    )
    housing_id = cursor.lastrowid

    # Mark all rooms as housing-owned
    for rid in all_room_ids:
        await db._db.execute(
            "UPDATE rooms SET housing_id = ? WHERE id = ?", (housing_id, rid)
        )

    # Update lot occupancy
    await db._db.execute(
        "UPDATE housing_lots SET current_homes = current_homes + 1 WHERE id = ?",
        (lot_id,),
    )

    # Set as home if they don't have one
    try:
        char_row = await db._db.execute_fetchall(
            "SELECT home_room_id FROM characters WHERE id = ?", (char_id,)
        )
        if char_row and not char_row[0]["home_room_id"]:
            await db._db.execute(
                "UPDATE characters SET home_room_id = ? WHERE id = ?",
                (private_room_ids[0] if private_room_ids else shop_room_ids[0], char_id),
            )
    except Exception:
        log.warning("purchase_shopfront: unhandled exception", exc_info=True)
        pass

    await db._db.commit()

    log.info("[housing] char %d purchased shopfront '%s' at lot %d (%s), rooms %s",
             char_id, sf_type, lot_id, lot["label"], all_room_ids)

    rent_note = (f" (−{int((1 - discount)*100)}% discount for {entry_security} zone)"
                 if discount < 1.0 else "")
    return {
        "ok":          True,
        "msg":         (f"Purchased: {cfg['label']} at {lot['label']}! "
                        f"Cost: {cfg['cost']:,}cr. "
                        f"Rent: {effective_rent:,}cr/week{rent_note}. "
                        f"{cfg['shop_rooms']} shop room(s) + {cfg['private_rooms']} private. "
                        f"Up to {cfg['droid_slots']} vendor droids in shop. "
                        f"Direction from street: {door_dir}."),
        "housing_id":  housing_id,
        "room_ids":    all_room_ids,
        "shop_room_ids": shop_room_ids,
        "private_room_ids": private_room_ids,
        "direction":   door_dir,
    }


async def sell_shopfront(db, char: dict) -> dict:
    """Sell a Tier 4 shopfront. 50% refund, vendor droids recalled first."""
    char_id = char["id"]
    h = await get_housing(db, char_id)
    if not h:
        return {"ok": False, "msg": "You don't own a shopfront."}
    if h["housing_type"] != "shopfront":
        return {"ok": False,
                "msg": "You don't own a shopfront. Use 'housing sell' for residences."}

    room_ids = json.loads(h["room_ids"]) if isinstance(h["room_ids"], str) else h["room_ids"]

    # Recall any vendor droids from shop rooms first
    recalled = 0
    for rid in room_ids:
        try:
            droids = await db.get_objects_in_room(rid, "vendor_droid")
            for d in droids:
                await db._db.execute(
                    "UPDATE objects SET room_id = NULL WHERE id = ?", (d["id"],)
                )
                recalled += 1
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Return storage items to character inventory
    storage = json.loads(h["storage"]) if isinstance(h["storage"], str) else (h["storage"] or [])
    if storage:
        try:
            inv_raw = char.get("inventory", "{}")
            inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
            inv.setdefault("items", []).extend(storage)
            await db.save_character(char_id, inventory=json.dumps(inv))
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Refund
    refund = h.get("purchase_price", 0) // 2
    if refund > 0:
        char["credits"] = char.get("credits", 0) + refund
        await db.save_character(char_id, credits=char["credits"])

    # Remove exits
    for exit_id in (h.get("exit_id_in"), h.get("exit_id_out")):
        if exit_id:
            try:
                await db._db.execute("DELETE FROM exits WHERE id = ?", (exit_id,))
            except Exception:
                log.warning("sell_shopfront: unhandled exception", exc_info=True)
                pass

    # Remove all housing rooms
    for rid in room_ids:
        try:
            await db._db.execute("DELETE FROM exits WHERE from_room = ? OR to_room = ?",
                                  (rid, rid))
            await db._db.execute("DELETE FROM rooms WHERE id = ?", (rid,))
        except Exception:
            log.warning("sell_shopfront: unhandled exception", exc_info=True)
            pass

    # Update lot occupancy
    try:
        await db._db.execute(
            "UPDATE housing_lots SET current_homes = MAX(0, current_homes - 1) "
            "WHERE room_id = ?",
            (h["entry_room_id"],),
        )
    except Exception:
        log.warning("sell_shopfront: unhandled exception", exc_info=True)
        pass

    # Delete housing record
    await db._db.execute("DELETE FROM player_housing WHERE id = ?", (h["id"],))

    # Clear home_room_id if it pointed here
    try:
        await db._db.execute(
            "UPDATE characters SET home_room_id = NULL "
            "WHERE id = ? AND home_room_id IN (%s)" % ",".join("?" * len(room_ids)),
            [char_id] + room_ids,
        )
    except Exception:
        log.warning("sell_shopfront: unhandled exception", exc_info=True)
        pass

    await db._db.commit()
    log.info("[housing] char %d sold shopfront, refund %dcr, %d droids recalled",
             char_id, refund, recalled)

    recall_note = f" {recalled} vendor droid(s) recalled." if recalled else ""
    return {
        "ok": True,
        "msg": (f"Shopfront sold. Refund: {refund:,}cr.{recall_note} "
                f"Storage items returned to inventory."),
    }


async def get_shopfront_info(db, char: dict) -> Optional[dict]:
    """Return Tier 4 housing record for character, or None."""
    char_id = char["id"]
    try:
        rows = await db._db.execute_fetchall(
            "SELECT * FROM player_housing WHERE char_id = ? AND tier = 4",
            (char_id,),
        )
        return dict(rows[0]) if rows else None
    except Exception:
        log.warning("get_shopfront_info: unhandled exception", exc_info=True)
        return None


async def get_market_directory(db, planet: Optional[str] = None) -> list[dict]:
    """
    Return a list of all shopfront vendor droids across all planets
    (or filtered to a specific planet) for the `market search` command.

    Each entry: {shop_name, owner_name, room_name, planet, droid_id,
                 item_count, tier_key}
    """
    results = []
    try:
        # Find all shopfront rooms
        query = (
            "SELECT r.id as room_id, r.name as room_name, r.properties "
            "FROM rooms r "
            "WHERE r.properties LIKE '%is_shopfront%true%'"
        )
        shop_rooms = await db._db.execute_fetchall(query)

        for sr in shop_rooms:
            props_raw = sr.get("properties", "{}")
            try:
                props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
            except Exception:
                props = {}
            if not props.get("is_shopfront"):
                continue

            # Get planet from lot
            room_id = sr["room_id"]
            lot_rows = await db._db.execute_fetchall(
                """SELECT hl.planet FROM housing_lots hl
                   JOIN player_housing ph ON ph.entry_room_id = hl.room_id
                   WHERE ? = ANY(
                       SELECT value FROM json_each(ph.room_ids)
                   )""",
                (room_id,),
            )
            # Fallback: walk up through housing record
            if not lot_rows:
                ph_rows = await db._db.execute_fetchall(
                    "SELECT * FROM player_housing WHERE room_ids LIKE ?",
                    (f"%{room_id}%",),
                )
                if ph_rows:
                    entry_room = ph_rows[0]["entry_room_id"]
                    lot_row2 = await db._db.execute_fetchall(
                        "SELECT planet FROM housing_lots WHERE room_id = ?",
                        (entry_room,),
                    )
                    room_planet = lot_row2[0]["planet"] if lot_row2 else "unknown"
                else:
                    room_planet = "unknown"
            else:
                room_planet = lot_rows[0]["planet"]

            if planet and room_planet != planet.lower():
                continue

            # Get vendor droids in this room
            droids = await db.get_objects_in_room(room_id, "vendor_droid")
            for d in droids:
                try:
                    from engine.vendor_droids import _load_data
                    data = _load_data(d)
                    if not data.get("shop_name"):
                        continue
                    inventory = data.get("inventory", [])
                    item_count = sum(
                        1 for slot in inventory if slot.get("quantity", 0) > 0
                    )
                    results.append({
                        "droid_id":   d["id"],
                        "shop_name":  data.get("shop_name", "Unknown Shop"),
                        "shop_desc":  data.get("shop_desc", ""),
                        "owner_name": data.get("owner_name", "Unknown"),
                        "room_id":    room_id,
                        "room_name":  sr.get("room_name", "Unknown Location"),
                        "planet":     room_planet,
                        "tier_key":   data.get("tier_key", "gn4"),
                        "item_count": item_count,
                    })
                except Exception:
                    log.warning("get_market_directory: unhandled exception", exc_info=True)
                    pass
    except Exception as e:
        log.warning("[housing] market directory error: %s", e)

    return results


def is_shopfront_room_props(props_raw) -> bool:
    """Quick check: is this room a shopfront shop room?"""
    try:
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        return bool(props.get("is_shopfront"))
    except Exception:
        log.warning("is_shopfront_room_props: unhandled exception", exc_info=True)
        return False


def get_effective_droid_cap(char: dict, owned_shopfronts: int) -> int:
    """
    Return effective vendor droid cap for a character.
    Base cap is MAX_DROIDS_PER_OWNER (3).
    Each shopfront owned adds +1 (capped at 6 total per design doc §2.5).
    """
    from engine.vendor_droids import MAX_DROIDS_PER_OWNER
    return min(6, MAX_DROIDS_PER_OWNER + owned_shopfronts)


# ══════════════════════════════════════════════════════════════════════════════
# DROP 7: Security & Intrusion
# ══════════════════════════════════════════════════════════════════════════════
"""
Housing security gates and intrusion mechanics.

Design doc §6:
  Secured zone housing  — locked, unpickable, no combat inside
  Contested zone housing — Security skill check difficulty 25 to pick
  Lawless zone housing   — Security difficulty 20 to pick, Strength 15 to force

  Theft:
    Contested: Heroic Sneak + Security combined (difficulty 30+)
    Lawless:   Moderate Sneak (difficulty 15) for main room items

  All intrusion attempts logged to `housing_intrusions` table.
  Owner alerted if online.

Architecture: all rolls go through perform_skill_check(). No direct dice rolls here.
"""

HOUSING_INTRUSIONS_SQL = """
CREATE TABLE IF NOT EXISTS housing_intrusions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    housing_id  INTEGER NOT NULL REFERENCES player_housing(id),
    intruder_id INTEGER NOT NULL REFERENCES characters(id),
    action      TEXT    NOT NULL,   -- 'lockpick', 'force', 'theft'
    success     INTEGER NOT NULL DEFAULT 0,
    details     TEXT    DEFAULT '',
    timestamp   REAL    NOT NULL
);
"""

# Difficulty constants (from design doc §6)
LOCKPICK_DIFFICULTY = {
    "secured":   999,   # impossible
    "contested": 25,    # Very Difficult
    "lawless":   20,    # Difficult
}
FORCE_DIFFICULTY = {
    "secured":   999,
    "contested": 999,   # can't force in contested — need pick
    "lawless":   15,    # Moderate Strength check
}
THEFT_DIFFICULTY = {
    "contested": 30,    # Heroic combined check
    "lawless":   15,    # Moderate Sneak
}
THEFT_STORAGE_DIFFICULTY = 30   # Very Difficult Security+Slicing for storage locker


async def ensure_intrusion_schema(db) -> None:
    """Create housing_intrusions table if absent. Idempotent."""
    try:
        await db._db.execute(HOUSING_INTRUSIONS_SQL.strip())
        await db._db.commit()
    except Exception as e:
        log.warning("[housing] intrusion schema error: %s", e)


async def get_housing_for_private_room(db, room_id: int) -> Optional[dict]:
    """
    Return the housing record that owns this room as a PRIVATE room, or None.
    A shopfront shop room is public and returns None.
    Used by MoveCommand to gate entry to private housing rooms.
    """
    try:
        room = await db.get_room(room_id)
        if not room:
            return None
        # Check room properties for private flag
        props_raw = room.get("properties", "{}")
        try:
            props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        except Exception:
            props = {}
        if not props.get("private"):
            return None
        # It's private — find the housing record
        housing_id = room.get("housing_id")
        if housing_id:
            return await get_housing_by_id(db, housing_id)
        # Fallback: search by room_ids JSON
        rows = await db._db.execute_fetchall(
            "SELECT * FROM player_housing WHERE room_ids LIKE ?",
            (f"%{room_id}%",),
        )
        for r in rows:
            rids = json.loads(r["room_ids"]) if isinstance(r["room_ids"], str) else (r["room_ids"] or [])
            if room_id in rids:
                return dict(r)
        return None
    except Exception:
        log.warning("get_housing_for_private_room: unhandled exception", exc_info=True)
        return None


def is_on_guest_list(h: dict, char_id: int) -> bool:
    """Check if a character is on a housing record's guest list."""
    guests = _guest_list(h)
    return char_id in guests


async def can_enter_housing_room(db, char: dict, room_id: int) -> tuple[bool, str]:
    """
    Check if a character can enter a private housing room.
    Returns (allowed: bool, reason: str).
    Shopfront shop rooms (public) always return (True, "").
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return True, ""   # not a private housing room

    char_id = char.get("id")
    # Owner always allowed
    if h["char_id"] == char_id:
        return True, ""
    # Admin/builder always allowed
    if char.get("is_admin") or char.get("is_builder"):
        return True, ""
    # Guest list
    if is_on_guest_list(h, char_id):
        return True, ""

    return False, "The door is locked."


async def _log_intrusion(db, housing_id: int, intruder_id: int,
                          action: str, success: bool, details: str = "") -> None:
    """Record an intrusion attempt to the housing_intrusions table."""
    try:
        now = time.time()
        await db._db.execute(
            """INSERT INTO housing_intrusions
               (housing_id, intruder_id, action, success, details, timestamp)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (housing_id, intruder_id, action, 1 if success else 0, details[:200], now),
        )
        await db._db.commit()
    except Exception as e:
        log.warning("[housing] intrusion log error: %s", e)


async def _notify_owner(db, session_mgr, h: dict, msg: str) -> None:
    """Alert the housing owner if they are online."""
    try:
        owner_id = h["char_id"]
        for sess in session_mgr.all:
            if sess.is_in_game and sess.character and sess.character.get("id") == owner_id:
                await sess.send_line(msg)
    except Exception:
        log.warning("_notify_owner: unhandled exception", exc_info=True)
        pass


async def attempt_lockpick(db, char: dict, room_id: int,
                            session_mgr=None) -> dict:
    """
    Attempt to pick the lock on a private housing room door.
    Uses Security skill. All rolls through perform_skill_check().
    Returns {\"ok\": bool, \"msg\": str, \"entered\": bool}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "There's no locked door here to pick.", "entered": False}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "It's your own door.", "entered": False}

    # Get zone security
    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    difficulty = LOCKPICK_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False,
                "msg": "Imperial security seals on this door cannot be picked.",
                "entered": False}

    # Skill check via perform_skill_check()
    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, "security", difficulty)

    success = result.success
    margin  = result.margin
    fumble  = result.fumble

    await _log_intrusion(db, h["id"], char["id"], "lockpick", success,
                          f"roll={result.roll} diff={difficulty} zone={zone_sec}")

    if fumble:
        msg = (f"  \033[1;31m[LOCKPICK]\033[0m Critical failure! "
               f"Your pick breaks in the lock. The owner has been alerted.\n"
               f"  Security: {result.pool_str} → {result.roll} vs {difficulty}")
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[SECURITY ALERT]\033[0m Someone attempted "
                                 f"to break into your home and fumbled — the lock is jammed.")
        return {"ok": False, "msg": msg, "entered": False}

    if success:
        flavor = "with ease" if margin >= 10 else "after careful work"
        msg = (f"  \033[1;32m[LOCKPICK]\033[0m You bypass the lock {flavor}.\n"
               f"  Security: {result.pool_str} → {result.roll} vs {difficulty}")
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;33m[SECURITY ALERT]\033[0m Someone has picked "
                                 f"the lock to your home!")
        return {"ok": True, "msg": msg, "entered": True}
    else:
        # Failed but not fumble — alert only if margin is terrible (≤ −10)
        msg = (f"  \033[1;31m[LOCKPICK]\033[0m The lock doesn't give. "
               f"({result.pool_str} → {result.roll} vs {difficulty})")
        if margin <= -10 and session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[2m[SECURITY]\033[0m Something rattled your door lock.")
        return {"ok": False, "msg": msg, "entered": False}


async def attempt_force_door(db, char: dict, room_id: int,
                              session_mgr=None) -> dict:
    """
    Attempt to force a housing door with Strength.
    Only possible in lawless zones. Very loud — always alerts owner.
    Returns {\"ok\": bool, \"msg\": str, \"entered\": bool}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "There's no door to force here.", "entered": False}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "You don't need to break down your own door.", "entered": False}

    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    difficulty = FORCE_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False,
                "msg": "The door is reinforced. Forcing it isn't an option here.",
                "entered": False}

    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, "brawling", difficulty)

    success = result.success
    await _log_intrusion(db, h["id"], char["id"], "force", success,
                          f"roll={result.roll} diff={difficulty}")

    # Always alert owner for forced entry — it's loud
    if session_mgr:
        if success:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[BREAK-IN]\033[0m Someone has forced the door "
                                 f"to your home!")
        else:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;33m[SECURITY ALERT]\033[0m Someone is trying to "
                                 f"force your door!")

    if success:
        msg = (f"  \033[1;31m[FORCE]\033[0m You wrench the door open with brute force.\n"
               f"  Strength: {result.pool_str} → {result.roll} vs {difficulty}")
        return {"ok": True, "msg": msg, "entered": True}
    else:
        msg = (f"  \033[1;31m[FORCE]\033[0m The door holds. "
               f"({result.pool_str} → {result.roll} vs {difficulty})")
        return {"ok": False, "msg": msg, "entered": False}


async def attempt_theft(db, char: dict, room_id: int,
                         target_item: str, session_mgr=None) -> dict:
    """
    Attempt to steal an item from the main room of occupied housing.
    Storage lockers require a separate, harder check.
    Returns {\"ok\": bool, \"msg\": str, \"item\": dict|None}.
    """
    h = await get_housing_for_private_room(db, room_id)
    if not h:
        return {"ok": False, "msg": "Nothing to steal here.", "item": None}

    if h["char_id"] == char.get("id"):
        return {"ok": False, "msg": "You can't steal from yourself.", "item": None}

    entry_room = await db.get_room(h["entry_room_id"])
    try:
        props_raw = entry_room.get("properties", "{}") if entry_room else "{}"
        props = json.loads(props_raw) if isinstance(props_raw, str) else (props_raw or {})
        zone_sec = props.get("security", "contested")
    except Exception:
        zone_sec = "contested"

    if zone_sec == "secured":
        return {"ok": False,
                "msg": "Imperial surveillance makes theft impossible here.", "item": None}

    difficulty = THEFT_DIFFICULTY.get(zone_sec, 999)
    if difficulty >= 999:
        return {"ok": False, "msg": "You can't steal here.", "item": None}

    # For contested zones: combined Sneak+Security average (use Sneak as primary)
    # For lawless zones: Sneak only
    from engine.skill_checks import perform_skill_check
    if zone_sec == "contested":
        sneak_r = perform_skill_check(char, "sneak",    difficulty)
        sec_r   = perform_skill_check(char, "security", difficulty)
        # Average margin — both must succeed
        success = sneak_r.success and sec_r.success
        roll_str = (f"Sneak {sneak_r.pool_str}→{sneak_r.roll}, "
                    f"Security {sec_r.pool_str}→{sec_r.roll} vs {difficulty}")
        fumble = sneak_r.fumble or sec_r.fumble
    else:
        sneak_r = perform_skill_check(char, "sneak", difficulty)
        success = sneak_r.success
        roll_str = f"Sneak {sneak_r.pool_str}→{sneak_r.roll} vs {difficulty}"
        fumble = sneak_r.fumble

    # Find the item in trophies (room display)
    trophies = _trophies(h)
    target_trophy = None
    target_idx = -1
    for i, t in enumerate(trophies):
        if target_item.lower() in t.get("name", "").lower():
            target_trophy = t
            target_idx = i
            break

    if target_trophy is None:
        return {"ok": False,
                "msg": f"You don't see '{target_item}' to steal here.", "item": None}

    await _log_intrusion(db, h["id"], char["id"], "theft", success,
                          f"item={target_item} roll={roll_str}")

    if fumble:
        if session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[1;31m[INTRUDER ALERT]\033[0m Someone botched a theft "
                                 f"attempt in your home!")
        msg = (f"  \033[1;31m[THEFT FAILED]\033[0m You fumble noisily — the owner will know.\n"
               f"  {roll_str}")
        return {"ok": False, "msg": msg, "item": None}

    if not success:
        msg = f"  \033[1;31m[THEFT FAILED]\033[0m You can't get away with it unseen.\n  {roll_str}"
        if zone_sec == "contested" and session_mgr:
            await _notify_owner(db, session_mgr, h,
                                 f"\033[2m[SECURITY]\033[0m Something feels disturbed in your home.")
        return {"ok": False, "msg": msg, "item": None}

    # Success — remove from trophies, give to thief
    trophies.pop(target_idx)
    await db._db.execute(
        "UPDATE player_housing SET trophies = ?, last_activity = ? WHERE id = ?",
        (json.dumps(trophies), time.time(), h["id"]),
    )
    # Add to thief inventory
    inv_raw = char.get("inventory", "{}")
    try:
        inv = json.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
    except Exception:
        inv = {}
    inv.setdefault("items", []).append(target_trophy)
    await db.update_character(char["id"], inventory=json.dumps(inv))
    await db._db.commit()

    if session_mgr:
        await _notify_owner(db, session_mgr, h,
                             f"\033[1;31m[THEFT ALERT]\033[0m "
                             f"{target_trophy.get('name', 'an item')} has been stolen from your home!")

    msg = (f"  \033[1;32m[THEFT SUCCEEDED]\033[0m You pocket "
           f"{target_trophy.get('name', 'the item')} unseen.\n  {roll_str}")
    return {"ok": True, "msg": msg, "item": target_trophy}


async def get_intrusion_log(db, char: dict) -> list[str]:
    """Return formatted intrusion log for the character's housing."""
    char_id = char.get("id")
    h = await get_housing(db, char_id)
    if not h:
        return ["  You don't have housing."]

    try:
        rows = await db._db.execute_fetchall(
            """SELECT hi.*, c.name as intruder_name
               FROM housing_intrusions hi
               LEFT JOIN characters c ON c.id = hi.intruder_id
               WHERE hi.housing_id = ?
               ORDER BY hi.timestamp DESC LIMIT 20""",
            (h["id"],),
        )
    except Exception:
        log.warning("intrusion log query failed", exc_info=True)
        return ["  Intrusion log unavailable."]

    if not rows:
        return [
            "\033[1;37m── Intrusion Log ──\033[0m",
            "  No intrusion attempts recorded.",
        ]

    import datetime
    lines = ["\033[1;37m── Intrusion Log ──\033[0m"]
    action_labels = {
        "lockpick": "\033[1;33mLOCKPICK\033[0m",
        "force":    "\033[1;31mFORCE   \033[0m",
        "theft":    "\033[1;31mTHEFT   \033[0m",
    }
    for r in rows:
        ts = datetime.datetime.fromtimestamp(r["timestamp"]).strftime("%m/%d %H:%M")
        outcome = "\033[1;32mSUCCESS\033[0m" if r["success"] else "\033[2mFAILED \033[0m"
        action_str = action_labels.get(r["action"], r["action"].upper())
        intruder = r["intruder_name"] or f"Unknown (#{r['intruder_id']})"
        lines.append(f"  {ts}  {action_str}  {outcome}  {intruder:<20}  \033[2m{r['details'][:50]}\033[0m")

    return lines
