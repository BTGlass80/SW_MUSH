# -*- coding: utf-8 -*-
"""
engine/buildings.py — Player-constructed building system (SYN.9,
2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.9.3 + §3.9.

Citizens with sufficient rank in a city's owning org can construct
buildings on wilderness landmarks the city has claimed. Each
landmark has 0-5 building slots (room property
`building_slot_capacity`, defaults to 2 on landmarks, 0 on
non-landmarks).

5 building categories per design:
  * residence       — personal storage (lockable, owner-only)
  * crafting_station — +1D bonus to crafts done in this room
                        (lookup helper shipped; consumer integration
                        deferred to SYN.10 or post-launch polish)
  * commerce_stall  — vendor surface, 50/50 split owner / city tax
                        (lookup helper shipped; full vendor surface
                        deferred)
  * garrison_annex  — spawns 2 additional defending NPCs
                        (self-contained; uses db.create_npc from
                        SYN.7.a.fix substrate)
  * cultural_hall   — +1 daily CP for citizens spending 5+ min here
                        (lookup helper shipped; cp_engine integration
                        deferred)

Construction flow:
  1. Citizen issues `+building construct <category>` in a landmark
     room.
  2. System validates: rank 3+ in city's owning org, slot available,
     materials in inventory, credits in char's wallet.
  3. Materials + credits deducted at start.
  4. Construction takes 24 real-time hours
     (`CONSTRUCTION_TIME_SECS`).
  5. The `building_construction_tick` periodically transitions
     `under_construction` → `operational` (and `evicted` slots free
     up after mayor's 2-day notice).
  6. Garrison annex buildings spawn 2 NPCs at completion.

Ownership:
  * Owner is the constructing citizen by default.
  * `owning_org_id` is nullable; only set if the citizen donates to
     org (donate flag — UI surface; substrate supports it).

Destruction:
  * Owner: `+building demolish <id>` — 25% material refund.
  * Mayor: `+building evict <id>` — 2-day notice (sets
     `evict_after_ts`); on tick after expiry, transitions to
     `evicted`. No refund to original owner.

Rebuild discount:
  * If the same owner rebuilds the same category in the same room
     after a previous demolish/eviction, 10% material cost reduction
     ("institutional memory") — REBUILD_DISCOUNT_PCT.

Schema migration:
  * `buildings` table created lazily via `ensure_schema()`.
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

CONSTRUCTION_TIME_SECS: float = 24 * 60 * 60   # 24 hours
DEMOLISH_REFUND_PCT: int = 25                  # owner-initiated refund
REBUILD_DISCOUNT_PCT: int = 10                 # same-owner rebuild discount
EVICT_NOTICE_SECS: float = 2 * 24 * 60 * 60    # 2 days notice
DEFAULT_LANDMARK_SLOT_CAPACITY: int = 2
GARRISON_NPC_COUNT: int = 2                    # NPCs per garrison_annex
CULTURAL_CP_MINUTES: int = 5                   # min in room for +1 CP
MIN_RANK_TO_CONSTRUCT: int = 3                 # design §2.9.3


# ── Building categories ──────────────────────────────────────────────────────
#
# Each entry declares construction cost + a short effect description.
# Materials are validated against the constructing citizen's inventory
# via engine.crafting.add_resource semantics (we use crafting resources,
# not arbitrary inventory items, for material costs).

BUILDING_CATEGORIES: dict = {
    "residence": {
        "display_name": "Residence",
        "description": (
            "Tier-3-equivalent personal housing for one citizen — "
            "lockable, with private storage."
        ),
        "credit_cost": 5000,
        "material_costs": [
            ("metal", 5),
            ("organic", 5),
        ],
        "effect_summary": (
            "Owner can store up to 50 items in private storage."
        ),
        "storage_cap": 50,
    },
    "crafting_station": {
        "display_name": "Crafting Station",
        "description": (
            "Provides a +1D bonus to crafting checks performed at "
            "this building. Faction-flavored at construction time."
        ),
        "credit_cost": 8000,
        "material_costs": [
            ("metal", 10),
            ("composite", 5),
        ],
        "effect_summary": "Crafters in this room get +1D on crafting rolls.",
        "skill_bonus_dice": 1,
    },
    "commerce_stall": {
        "display_name": "Commerce Stall",
        "description": (
            "Mini-vendor station. Takes a 50% cut of all sales to "
            "the owning citizen; the other 50% goes to the city tax "
            "pool."
        ),
        "credit_cost": 6000,
        "material_costs": [
            ("metal", 8),
        ],
        "effect_summary": "Owner earns 50% of sales; city earns 50%.",
        "owner_cut_pct": 50,
        "city_cut_pct": 50,
    },
    "garrison_annex": {
        "display_name": "Garrison Annex",
        "description": (
            "Spawns 2 additional defending NPCs at this landmark. "
            "Faction-flavored to the owning city's faction."
        ),
        "credit_cost": 10000,
        "material_costs": [
            ("metal", 15),
            ("composite", 5),
        ],
        "effect_summary": "2 additional defending NPCs at this room.",
        "npc_count": GARRISON_NPC_COUNT,
    },
    "cultural_hall": {
        "display_name": "Cultural Hall",
        "description": (
            "Citizens who spend 5+ minutes here gain +1 daily CP. "
            "Encourages presence and gathering."
        ),
        "credit_cost": 7500,
        "material_costs": [
            ("metal", 8),
            ("organic", 5),
        ],
        "effect_summary": "Citizens spending 5+ min here gain +1 daily CP.",
        "cp_bonus_per_day": 1,
        "min_time_secs": CULTURAL_CP_MINUTES * 60,
    },
}


# ── Schema ───────────────────────────────────────────────────────────────────

BUILDINGS_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS buildings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id         INTEGER NOT NULL,
    category        TEXT NOT NULL,
    owner_char_id   INTEGER NOT NULL,
    owning_org_id   INTEGER,
    status          TEXT NOT NULL,
    hp              INTEGER NOT NULL DEFAULT 100,
    completion_ts   REAL NOT NULL,
    evict_after_ts  REAL,
    constructed_at  REAL NOT NULL,
    name            TEXT,
    storage_json    TEXT DEFAULT '{}',
    npc_ids_json    TEXT DEFAULT '[]'
);
"""

BUILDINGS_INDEXES_SQL = [
    "CREATE INDEX IF NOT EXISTS idx_buildings_room ON buildings(room_id)",
    "CREATE INDEX IF NOT EXISTS idx_buildings_owner ON buildings(owner_char_id)",
    "CREATE INDEX IF NOT EXISTS idx_buildings_status ON buildings(status)",
]


async def ensure_schema(db) -> None:
    """Create the buildings table + indexes if they don't exist."""
    await db.execute(BUILDINGS_SCHEMA_SQL)
    for idx_sql in BUILDINGS_INDEXES_SQL:
        await db.execute(idx_sql)
    await db.commit()


# ── Slot capacity ────────────────────────────────────────────────────────────

async def get_slot_capacity(db, room_id: int) -> int:
    """Return the building-slot capacity of a room.

    Uses room's `properties.building_slot_capacity` if set; else
    DEFAULT_LANDMARK_SLOT_CAPACITY (2) if the room is a wilderness
    landmark; else 0.

    Force-resonant landmarks (`force_resonant: true`) always return 0
    — no building on sacred sites.
    """
    try:
        room = await db.get_room(int(room_id))
    except Exception:
        return 0
    if not room:
        return 0

    props_raw = room.get("properties") or "{}"
    try:
        props = (json.loads(props_raw)
                 if isinstance(props_raw, str) else props_raw) or {}
    except Exception:
        props = {}

    # Force-resonant sites can never host buildings.
    if props.get("force_resonant"):
        return 0

    # Explicit override on the room properties.
    if "building_slot_capacity" in props:
        try:
            return max(0, int(props["building_slot_capacity"]))
        except Exception:
            return 0

    # Default for wilderness landmarks.
    if props.get("wilderness_landmark"):
        return DEFAULT_LANDMARK_SLOT_CAPACITY

    return 0


async def get_buildings_in_room(db, room_id: int) -> list:
    """Return all non-demolished/evicted buildings in a room
    (active or under construction)."""
    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE room_id = ? "
        "AND status IN ('under_construction', 'operational') "
        "ORDER BY id ASC",
        (int(room_id),),
    )
    return [dict(r) for r in rows]


async def count_active_slots_used(db, room_id: int) -> int:
    """How many slots are currently occupied by buildings in the
    room (under-construction or operational)."""
    return len(await get_buildings_in_room(db, int(room_id)))


async def has_slot_available(db, room_id: int) -> bool:
    """True if room has at least 1 free slot."""
    cap = await get_slot_capacity(db, int(room_id))
    used = await count_active_slots_used(db, int(room_id))
    return used < cap


# ── Construction ─────────────────────────────────────────────────────────────

async def construct_building(
    db, char: dict, category: str, room_id: int,
    *,
    donate_to_org: bool = False,
    now: Optional[float] = None,
) -> dict:
    """Validate + start construction of a building.

    Validates:
      * category is a known BUILDING_CATEGORIES entry
      * room has a free slot
      * char is rank MIN_RANK_TO_CONSTRUCT+ in the city's owning org
        (city is looked up from room via player_cities)
      * char has the material costs in their crafting resources
      * char has enough credits

    On success:
      * Deducts materials + credits from char (with rebuild discount
        if applicable).
      * Creates building row with status='under_construction' and
        completion_ts=now+CONSTRUCTION_TIME_SECS.
      * Garrison annex NPCs are spawned only at completion (in
        `_complete_construction`), not here — failure-tolerant.

    Returns dict: {"ok": bool, "msg": str, "building_id": int|None,
                    "completion_ts": float|None}.
    """
    if now is None:
        now = time.time()

    if category not in BUILDING_CATEGORIES:
        return _fail(
            f"Unknown building category: '{category}'. "
            f"Known: {', '.join(sorted(BUILDING_CATEGORIES.keys()))}."
        )
    cat_def = BUILDING_CATEGORIES[category]

    # Validate room is a landmark with slot capacity.
    cap = await get_slot_capacity(db, int(room_id))
    if cap == 0:
        return _fail(
            "This room cannot host buildings. Buildings only "
            "construct on city-claimed wilderness landmarks."
        )

    used = await count_active_slots_used(db, int(room_id))
    if used >= cap:
        return _fail(
            f"This landmark has no free building slots "
            f"({used}/{cap} used)."
        )

    # Determine which city owns this landmark.
    try:
        from engine.player_cities import get_city_for_room
        city = await get_city_for_room(db, int(room_id))
    except Exception:
        log.warning("[buildings] get_city_for_room failed", exc_info=True)
        city = None
    if not city:
        return _fail(
            "This landmark is not part of any city. Construction is "
            "only possible on city-claimed landmarks."
        )

    # Validate rank in the city's owning org.
    try:
        mem = await db.get_membership(int(char["id"]), int(city["org_id"]))
    except Exception:
        log.warning("[buildings] get_membership failed", exc_info=True)
        mem = None
    rank_level = int((mem or {}).get("rank_level", 0))
    if rank_level < MIN_RANK_TO_CONSTRUCT:
        return _fail(
            f"You need rank {MIN_RANK_TO_CONSTRUCT}+ in the city's "
            f"owning organization to construct here. You are rank "
            f"{rank_level}."
        )

    # Check materials + credits — apply rebuild discount if same
    # owner is rebuilding the same category in the same room.
    rebuild = await _is_rebuild(
        db, int(char["id"]), int(room_id), category,
    )
    discount = REBUILD_DISCOUNT_PCT / 100.0 if rebuild else 0.0

    credit_cost_full = int(cat_def["credit_cost"])
    credit_cost = int(round(credit_cost_full * (1.0 - discount)))
    material_costs = [
        (rtype, max(1, int(round(qty * (1.0 - discount)))))
        for (rtype, qty) in cat_def["material_costs"]
    ]

    if int(char.get("credits", 0)) < credit_cost:
        return _fail(
            f"You need {credit_cost:,} credits to start construction "
            f"(you have {int(char.get('credits', 0)):,})."
        )

    has, lacking = _check_materials(char, material_costs)
    if not has:
        cost_str = ", ".join(f"{q}x {t}" for (t, q) in material_costs)
        lack_str = ", ".join(f"{q}x {t}" for (t, q) in lacking)
        return _fail(
            f"You lack materials. Required: {cost_str}. "
            f"Missing: {lack_str}."
        )

    # Deduct.
    char["credits"] = await db.adjust_credits(char["id"], -credit_cost, "player_building_construct")

    _deduct_materials(char, material_costs)
    await db.save_character(char["id"], inventory=char["inventory"])

    # Insert building row.
    completion_ts = float(now) + CONSTRUCTION_TIME_SECS
    cur = await db.execute(
        "INSERT INTO buildings "
        "(room_id, category, owner_char_id, owning_org_id, status, "
        " hp, completion_ts, constructed_at, name, "
        " storage_json, npc_ids_json) "
        "VALUES (?, ?, ?, ?, 'under_construction', "
        " 100, ?, ?, ?, '{}', '[]')",
        (
            int(room_id), category, int(char["id"]),
            int(city["org_id"]) if donate_to_org else None,
            completion_ts, float(now),
            _default_name(category, char.get("name", "?")),
        ),
    )
    await db.commit()
    bid = _extract_lastrowid(cur)

    log.info(
        "[buildings] construction started: id=%d, room=%d, "
        "category=%s, owner=%d, rebuild=%s, "
        "credits=%d, materials=%s",
        bid, room_id, category, char["id"], rebuild,
        credit_cost, material_costs,
    )

    return {
        "ok": True,
        "msg": (
            f"Construction started on a {cat_def['display_name']}. "
            f"Completion in 24 hours."
            + (f" [Rebuild discount: -{REBUILD_DISCOUNT_PCT}% materials]"
               if rebuild else "")
        ),
        "building_id": bid,
        "completion_ts": completion_ts,
        "credit_cost": credit_cost,
        "material_costs": material_costs,
        "rebuild_discount_applied": rebuild,
    }


async def _is_rebuild(
    db, owner_char_id: int, room_id: int, category: str,
) -> bool:
    """Return True if this owner has previously demolished/evicted a
    same-category building in this same room — the rebuild
    discount applies."""
    rows = await db.fetchall(
        "SELECT id FROM buildings "
        "WHERE room_id = ? AND owner_char_id = ? AND category = ? "
        "AND status IN ('demolished', 'evicted') "
        "LIMIT 1",
        (int(room_id), int(owner_char_id), category),
    )
    return len(rows) > 0


# ── Demolish ─────────────────────────────────────────────────────────────────

async def demolish_building(
    db, char: dict, building_id: int, *,
    now: Optional[float] = None,
) -> dict:
    """Owner-initiated demolition. 25% material refund per design.

    Validates:
      * Building exists.
      * char is the owner.
      * Status is 'operational' OR 'under_construction'.
        (Demolishing under-construction also allowed; no refund
        though, since the design says no refund on cancelled
        construction.)
    """
    if now is None:
        now = time.time()

    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE id = ?", (int(building_id),),
    )
    if not rows:
        return _fail(f"No building #{building_id}.")
    bdg = dict(rows[0])

    if int(bdg["owner_char_id"]) != int(char.get("id", 0)):
        return _fail("You don't own that building.")

    status = bdg["status"]
    if status not in ("operational", "under_construction"):
        return _fail(
            f"Building is already {status} — nothing to demolish."
        )

    # Refund materials only if operational (per design — no refund
    # on cancelled construction).
    refunded = []
    if status == "operational":
        cat_def = BUILDING_CATEGORIES.get(bdg["category"], {})
        material_costs = cat_def.get("material_costs", []) or []
        refund_pct = DEMOLISH_REFUND_PCT / 100.0
        for (rtype, qty) in material_costs:
            refund_qty = max(1, int(round(qty * refund_pct)))
            try:
                from engine.crafting import add_resource
                add_resource(char, rtype, refund_qty, 60.0)
                refunded.append((rtype, refund_qty))
            except Exception:
                log.warning("[buildings] refund add_resource failed",
                            exc_info=True)
        if refunded:
            await db.save_character(char["id"], inventory=char["inventory"])

    # Clean up: any spawned NPCs (garrison_annex) get removed.
    await _cleanup_building_npcs(db, bdg)

    # Mark demolished.
    await db.execute(
        "UPDATE buildings SET status = 'demolished' WHERE id = ?",
        (int(building_id),),
    )
    await db.commit()

    log.info(
        "[buildings] demolished: id=%d, owner=%d, refunded=%s",
        building_id, char["id"], refunded,
    )

    if refunded:
        refund_str = ", ".join(f"{q}x {t}" for (t, q) in refunded)
        return {
            "ok": True,
            "msg": (f"Building demolished. "
                    f"Refund: {refund_str}."),
            "refunded": refunded,
        }
    else:
        return {
            "ok": True,
            "msg": (
                "Building demolished. No refund "
                "(construction was incomplete)."
            ),
            "refunded": [],
        }


# ── Evict ────────────────────────────────────────────────────────────────────

async def evict_building(
    db, mayor: dict, building_id: int, *,
    now: Optional[float] = None,
) -> dict:
    """Mayor-initiated eviction with 2-day notice.

    Validates:
      * Building exists.
      * mayor is the mayor of the city the room belongs to.
      * Building is operational.
      * Building isn't already under an eviction notice.

    Effect:
      * Sets evict_after_ts = now + EVICT_NOTICE_SECS.
      * On a later tick (after evict_after_ts), the building
        transitions to 'evicted' status (no refund to owner).
    """
    if now is None:
        now = time.time()

    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE id = ?", (int(building_id),),
    )
    if not rows:
        return _fail(f"No building #{building_id}.")
    bdg = dict(rows[0])

    # Validate mayor relationship.
    try:
        from engine.player_cities import get_city_for_room
        city = await get_city_for_room(db, int(bdg["room_id"]))
    except Exception:
        log.warning("[buildings] get_city_for_room failed in evict",
                    exc_info=True)
        city = None
    if not city:
        return _fail(
            "This building is not in any active city, so no mayor "
            "can evict it."
        )
    if int(city.get("mayor_id", 0)) != int(mayor.get("id", 0)):
        return _fail("Only the city's mayor may evict.")

    if bdg["status"] != "operational":
        return _fail(
            f"Building #{building_id} is {bdg['status']}, "
            f"not operational — nothing to evict."
        )

    if bdg.get("evict_after_ts"):
        evict_time = float(bdg["evict_after_ts"])
        return _fail(
            f"Building #{building_id} is already under eviction "
            f"notice (expires in "
            f"{int((evict_time - now) // 3600)} hours)."
        )

    evict_ts = float(now) + EVICT_NOTICE_SECS
    await db.execute(
        "UPDATE buildings SET evict_after_ts = ? WHERE id = ?",
        (evict_ts, int(building_id)),
    )
    await db.commit()

    log.info(
        "[buildings] eviction notice issued: id=%d, by mayor=%d, "
        "effective=%.0f",
        building_id, mayor["id"], evict_ts,
    )

    return {
        "ok": True,
        "msg": (
            f"Eviction notice posted on building #{building_id}. "
            f"Effective in 2 days. The owner has been notified."
        ),
        "evict_after_ts": evict_ts,
    }


# ── Listing + inspection ─────────────────────────────────────────────────────

async def list_buildings_in_room(db, room_id: int) -> list:
    """Public listing surface for the `+building list` command.
    Returns full row dicts (including under-construction)."""
    return await get_buildings_in_room(db, int(room_id))


async def get_building(db, building_id: int) -> Optional[dict]:
    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE id = ?", (int(building_id),),
    )
    return dict(rows[0]) if rows else None


# ── Effect lookup helpers ────────────────────────────────────────────────────
#
# These return values/flags that consumers (crafting, cp_engine, etc.)
# can use to apply category effects. Consumer integration is
# deferred — SYN.9 ships the substrate; SYN.10 or later polish wires
# the consumers.

async def get_crafting_station_bonus(
    db, char: dict, room_id: int,
) -> int:
    """Return the +N D bonus a crafter would get for a craft attempt
    in this room. 0 if no operational crafting_station here."""
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE room_id = ? AND category = 'crafting_station' "
        "AND status = 'operational'",
        (int(room_id),),
    )
    if not rows:
        return 0
    return BUILDING_CATEGORIES["crafting_station"]["skill_bonus_dice"]


async def get_cultural_hall_in_room(
    db, room_id: int,
) -> Optional[dict]:
    """Return the operational cultural_hall building in the room,
    or None. Consumer: cp_engine daily tick."""
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE room_id = ? AND category = 'cultural_hall' "
        "AND status = 'operational' "
        "LIMIT 1",
        (int(room_id),),
    )
    return dict(rows[0]) if rows else None


async def get_commerce_stall_in_room(
    db, room_id: int,
) -> Optional[dict]:
    """Return the operational commerce_stall in the room, or None.
    Consumer: vendor surface (deferred)."""
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE room_id = ? AND category = 'commerce_stall' "
        "AND status = 'operational' "
        "LIMIT 1",
        (int(room_id),),
    )
    return dict(rows[0]) if rows else None


async def get_residence_for_owner(
    db, owner_char_id: int, room_id: int,
) -> Optional[dict]:
    """Return the owner's operational residence in this room, or
    None. Consumer: +building store/take commands."""
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE room_id = ? AND owner_char_id = ? "
        "AND category = 'residence' AND status = 'operational' "
        "LIMIT 1",
        (int(room_id), int(owner_char_id)),
    )
    return dict(rows[0]) if rows else None


# ── Construction tick ────────────────────────────────────────────────────────

async def tick_building_construction(
    db, session_mgr=None, *,
    now: Optional[float] = None,
) -> dict:
    """Periodic tick: transition under_construction → operational
    when completion_ts has elapsed; transition evicted-notice
    buildings to evicted-status when evict_after_ts has elapsed.

    Best-effort: per-building exceptions are caught + logged; one
    failure doesn't block the others.

    Returns stats {"completed": int, "evicted": int}.
    """
    if now is None:
        now = time.time()

    completed = 0
    evicted = 0

    # 1. Complete construction.
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE status = 'under_construction' AND completion_ts <= ?",
        (float(now),),
    )
    for r in rows:
        bdg = dict(r)
        try:
            await _complete_construction(db, bdg, session_mgr)
            completed += 1
        except Exception:
            log.warning(
                "[buildings] completion failed for #%s",
                bdg.get("id"), exc_info=True,
            )

    # 2. Process eviction-notice expiries.
    rows = await db.fetchall(
        "SELECT * FROM buildings "
        "WHERE status = 'operational' "
        "AND evict_after_ts IS NOT NULL "
        "AND evict_after_ts <= ?",
        (float(now),),
    )
    for r in rows:
        bdg = dict(r)
        try:
            await _process_eviction_expiry(db, bdg, session_mgr)
            evicted += 1
        except Exception:
            log.warning(
                "[buildings] eviction expiry failed for #%s",
                bdg.get("id"), exc_info=True,
            )

    if completed or evicted:
        log.info(
            "[buildings] tick: completed=%d, evicted=%d",
            completed, evicted,
        )

    return {"completed": completed, "evicted": evicted}


async def _complete_construction(
    db, bdg: dict, session_mgr=None,
) -> None:
    """Transition a building from under_construction → operational.
    For garrison_annex, spawn 2 defending NPCs."""
    category = bdg["category"]
    cat_def = BUILDING_CATEGORIES.get(category, {})

    # Spawn NPCs if applicable (garrison_annex).
    npc_ids = []
    if category == "garrison_annex":
        npc_ids = await _spawn_garrison_npcs(db, bdg)

    await db.execute(
        "UPDATE buildings SET status = 'operational', "
        "npc_ids_json = ? WHERE id = ?",
        (json.dumps(npc_ids), int(bdg["id"])),
    )
    await db.commit()

    log.info(
        "[buildings] completed: id=%d, category=%s, owner=%d, "
        "npcs_spawned=%d",
        bdg["id"], category, bdg["owner_char_id"], len(npc_ids),
    )

    # Notify owner if online.
    if session_mgr is not None:
        try:
            owner_sess = session_mgr.find_by_character(
                int(bdg["owner_char_id"])
            )
            if owner_sess:
                display = cat_def.get("display_name", category)
                await owner_sess.send_line(
                    f"  \033[1;32m[CONSTRUCTION COMPLETE]\033[0m "
                    f"Your {display} is now operational."
                )
        except Exception:
            log.warning("[buildings] notify owner failed",
                        exc_info=True)

    # SYN.10 (May 25 2026): global news broadcast for visible
    # faction-power-projection completions (garrison_annex). Other
    # categories (residence, crafting_station, etc.) stay quiet — only
    # the owner is notified. Per design §2.6 news-digest expansions.
    if session_mgr is not None and category == "garrison_annex":
        try:
            from engine.territory_display import (
                format_building_completion_news,
            )
            # Resolve region + owner name for the news line.
            region_slug = await _resolve_region_for_building(db, bdg)
            owner_name = await _resolve_char_name(db, bdg["owner_char_id"])
            if region_slug:
                news = format_building_completion_news(
                    region_slug,
                    building_category=category,
                    owner_name=owner_name,
                )
                await session_mgr.broadcast(
                    f"\n  \033[1;33m[News] {news}\033[0m"
                )
        except Exception:
            log.warning(
                "[buildings] completion broadcast failed",
                exc_info=True,
            )


async def _process_eviction_expiry(
    db, bdg: dict, session_mgr=None,
) -> None:
    """Transition operational building with expired eviction notice
    → evicted. Remove any spawned NPCs."""
    await _cleanup_building_npcs(db, bdg)

    await db.execute(
        "UPDATE buildings SET status = 'evicted', "
        "evict_after_ts = NULL WHERE id = ?",
        (int(bdg["id"]),),
    )
    await db.commit()

    log.info(
        "[buildings] eviction expiry processed: id=%d, owner=%d",
        bdg["id"], bdg["owner_char_id"],
    )

    if session_mgr is not None:
        try:
            owner_sess = session_mgr.find_by_character(
                int(bdg["owner_char_id"])
            )
            if owner_sess:
                await owner_sess.send_line(
                    f"  \033[1;31m[EVICTED]\033[0m "
                    f"Your {bdg['category']} (#{bdg['id']}) has been "
                    f"evicted by the city's mayor. The slot is now free."
                )
        except Exception:
            log.warning("[buildings] notify owner of evict failed",
                        exc_info=True)


async def _spawn_garrison_npcs(db, bdg: dict) -> list:
    """Spawn garrison NPCs for a garrison_annex on completion.
    Faction-flavored based on the city's owning org, where possible.
    """
    npc_ids = []
    try:
        from engine.player_cities import get_city_for_room
        city = await get_city_for_room(db, int(bdg["room_id"]))
    except Exception:
        city = None

    faction = "independent"
    if city:
        try:
            org_rows = await db.fetchall(
                "SELECT code FROM organizations WHERE id = ?",
                (int(city["org_id"]),),
            )
            if org_rows:
                faction = dict(org_rows[0]).get("code", "independent")
        except Exception:
            log.debug(
                "[buildings] org lookup for city %s failed; "
                "garrison defaults to faction=%r",
                city.get("id"), faction, exc_info=True,
            )

    try:
        from engine.npc_generator import generate_npc
        from ai.npc_brain import NPCConfig
    except Exception:
        log.warning("[buildings] npc_generator import failed",
                    exc_info=True)
        return []

    for i in range(GARRISON_NPC_COUNT):
        try:
            npc_data = generate_npc(
                "veteran", "thug", species="Human",
                name=f"Garrison Guard ({faction})",
            )
            npc_data["weapon"] = "blaster_rifle"
            ai_cfg = NPCConfig(
                personality=(
                    f"A garrison guard defending {faction} "
                    f"installation at this landmark."
                ),
                fallback_lines=[
                    "The guard watches the perimeter.",
                    "The guard nods at you, weapon ready.",
                ],
            ).to_dict()
            ai_cfg["hostile"] = False
            ai_cfg["combat_behavior"] = "defensive"
            ai_cfg["weapon"] = "blaster_rifle"
            ai_cfg["is_garrison_npc"] = True
            ai_cfg["building_id"] = int(bdg["id"])
            ai_cfg["faction_code"] = faction

            npc_id = await db.create_npc(
                name=f"Garrison Guard",
                room_id=int(bdg["room_id"]),
                species="Human",
                description=(
                    f"A {faction} garrison guard, posted to defend "
                    f"this landmark."
                ),
                char_sheet_json=json.dumps(npc_data),
                ai_config_json=json.dumps(ai_cfg),
            )
            npc_ids.append(int(npc_id))
        except Exception:
            log.warning(
                "[buildings] garrison NPC spawn failed",
                exc_info=True,
            )
    return npc_ids


async def _cleanup_building_npcs(db, bdg: dict) -> int:
    """Delete any NPCs spawned by this building (currently only
    garrison_annex). Returns count of NPCs removed."""
    try:
        npc_ids = json.loads(bdg.get("npc_ids_json") or "[]")
    except Exception:
        npc_ids = []
    removed = 0
    for nid in npc_ids:
        try:
            await db.delete_npc(int(nid))
            removed += 1
        except Exception:
            log.warning(
                "[buildings] NPC cleanup failed for npc %s",
                nid, exc_info=True,
            )
    return removed


# ── Storage (residence) ──────────────────────────────────────────────────────

async def residence_store_item(
    db, char: dict, building_id: int, item_key: str,
) -> dict:
    """Move an item from char inventory to residence storage."""
    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE id = ?", (int(building_id),),
    )
    if not rows:
        return _fail(f"No building #{building_id}.")
    bdg = dict(rows[0])
    if bdg["category"] != "residence":
        return _fail("That building is not a residence.")
    if bdg["status"] != "operational":
        return _fail("Residence isn't operational yet.")
    if int(bdg["owner_char_id"]) != int(char.get("id", 0)):
        return _fail("You don't own that residence.")

    # Find item in char inventory.
    try:
        inv = json.loads(char.get("inventory", "{}"))
    except Exception:
        inv = {}
    items = inv.get("items", []) or []
    target = None
    for i, it in enumerate(items):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            target = items.pop(i)
            break
    if not target:
        return _fail(f"You don't have '{item_key}'.")

    # Add to residence storage.
    try:
        storage = json.loads(bdg.get("storage_json") or "{}")
    except Exception:
        storage = {}
    storage_items = storage.setdefault("items", [])
    cap = BUILDING_CATEGORIES["residence"]["storage_cap"]
    if len(storage_items) >= cap:
        # Put item back.
        items.append(target)
        inv["items"] = items
        return _fail(
            f"Residence storage is full ({cap} item cap)."
        )

    storage_items.append(target)
    storage["items"] = storage_items
    inv["items"] = items

    char["inventory"] = json.dumps(inv)
    await db.save_character(char["id"], inventory=char["inventory"])
    await db.execute(
        "UPDATE buildings SET storage_json = ? WHERE id = ?",
        (json.dumps(storage), int(building_id)),
    )
    await db.commit()

    return {
        "ok": True,
        "msg": (
            f"Stored {target.get('name') or target.get('key')} "
            f"in your residence ({len(storage_items)}/{cap})."
        ),
    }


async def residence_take_item(
    db, char: dict, building_id: int, item_key: str,
) -> dict:
    """Move an item from residence storage back to char inventory."""
    rows = await db.fetchall(
        "SELECT * FROM buildings WHERE id = ?", (int(building_id),),
    )
    if not rows:
        return _fail(f"No building #{building_id}.")
    bdg = dict(rows[0])
    if bdg["category"] != "residence":
        return _fail("That building is not a residence.")
    if bdg["status"] != "operational":
        return _fail("Residence isn't operational yet.")
    if int(bdg["owner_char_id"]) != int(char.get("id", 0)):
        return _fail("You don't own that residence.")

    try:
        storage = json.loads(bdg.get("storage_json") or "{}")
    except Exception:
        storage = {}
    storage_items = storage.get("items", []) or []

    target = None
    for i, it in enumerate(storage_items):
        name = (it.get("name") or it.get("key") or "").lower()
        if item_key.lower() in name:
            target = storage_items.pop(i)
            break
    if not target:
        return _fail(f"Nothing matching '{item_key}' in residence.")

    storage["items"] = storage_items

    try:
        inv = json.loads(char.get("inventory", "{}"))
    except Exception:
        inv = {}
    inv.setdefault("items", []).append(target)

    char["inventory"] = json.dumps(inv)
    await db.save_character(char["id"], inventory=char["inventory"])
    await db.execute(
        "UPDATE buildings SET storage_json = ? WHERE id = ?",
        (json.dumps(storage), int(building_id)),
    )
    await db.commit()

    return {
        "ok": True,
        "msg": f"Took {target.get('name') or target.get('key')} from residence.",
    }


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fail(msg: str) -> dict:
    return {"ok": False, "msg": msg}


def _default_name(category: str, owner_name: str) -> str:
    cat_def = BUILDING_CATEGORIES.get(category, {})
    return f"{owner_name}'s {cat_def.get('display_name', category)}"


def _check_materials(char: dict, costs: list) -> tuple:
    """Check char inventory has the required materials. Returns
    (has_all, lacking_list)."""
    try:
        inv = json.loads(char.get("inventory", "{}"))
    except Exception:
        inv = {}
    resources = inv.get("resources", []) or []

    # Aggregate quantity per type.
    have = {}
    for r in resources:
        rtype = r.get("type", "")
        have[rtype] = have.get(rtype, 0) + int(r.get("quantity", 0))

    lacking = []
    for (rtype, qty) in costs:
        if have.get(rtype, 0) < qty:
            lacking.append((rtype, qty - have.get(rtype, 0)))
    return (len(lacking) == 0, lacking)


def _deduct_materials(char: dict, costs: list) -> None:
    """Deduct material quantities from char inventory.resources.
    Assumes _check_materials returned has_all=True."""
    try:
        inv = json.loads(char.get("inventory", "{}"))
    except Exception:
        inv = {}
    resources = inv.get("resources", []) or []

    for (rtype, qty) in costs:
        remaining = qty
        # Walk stacks (in original order) and deduct.
        new_resources = []
        for r in resources:
            if remaining <= 0:
                new_resources.append(r)
                continue
            if r.get("type") != rtype:
                new_resources.append(r)
                continue
            have = int(r.get("quantity", 0))
            if have <= remaining:
                # Whole stack consumed.
                remaining -= have
                # Drop this stack (don't append).
            else:
                # Partial.
                r2 = dict(r)
                r2["quantity"] = have - remaining
                new_resources.append(r2)
                remaining = 0
        resources = new_resources

    inv["resources"] = resources
    char["inventory"] = json.dumps(inv)


def _extract_lastrowid(cursor) -> int:
    """Pull lastrowid off a DB cursor, defensive against various
    DB wrapper shapes."""
    try:
        return int(cursor.lastrowid)
    except Exception:
        try:
            return int(cursor.cursor.lastrowid)
        except Exception:
            return 0


# ── Test reset hook ──────────────────────────────────────────────────────────

def _reset_state_for_tests() -> None:
    """No module-level transient state — buildings are all in the
    DB. This hook exists for parallelism with other engines (e.g.
    wilderness_anomalies); calling it is a no-op."""
    pass


# ── SYN.10 news-broadcast helpers ────────────────────────────────────────────

async def _resolve_region_for_building(db, bdg: dict) -> Optional[str]:
    """Look up the wilderness_region_id for a building's anchor room.
    Returns None if the room has no region or lookup fails."""
    try:
        room = await db.get_room(int(bdg["room_id"]))
        if room:
            return room.get("wilderness_region_id")
    except Exception:
        log.debug(
            "[buildings] region resolution for building %s failed; "
            "returning None",
            bdg.get("id"), exc_info=True,
        )
    return None


async def _resolve_char_name(db, char_id: int) -> str:
    """Look up a character's display name. Falls back to 'someone'
    on failure so the news line is never broken."""
    try:
        c = await db.get_character(int(char_id))
        if c:
            return c.get("name") or "someone"
    except Exception:
        log.debug(
            "[buildings] char-name resolution for %s failed; "
            "falling back to 'someone'",
            char_id, exc_info=True,
        )
    return "someone"
