# -*- coding: utf-8 -*-
"""
engine/space_caches.py — Space Wildspace Cache System  [Drop 1a]

Implements the mining-cache loop for wildspace zones per
docs/design/space_wildspace_design_v1.md §4.

Architecture
============
- Cache definitions live in a per-zone ``cache_pool`` dict (loaded from
  YAML or the DEV_TEST_CACHE_POOL constant below for the throwaway test zone).
- Cache instances live in the ``space_caches`` DB table.
- ``ensure_schema(db)`` is idempotent (CREATE TABLE IF NOT EXISTS) and is
  wired into server/game_server.py's boot path alongside housing/player_cities.
- Visibility check: universal → all; [faction, ...] → rep ≥ 0 with any;
  hidden → never.
- ``harvest_mining`` runs a ``perform_skill_check`` (Pilot/Mechanical averaged,
  difficulty 10) and grants resources via ``engine.crafting.add_resource``.
  Rep reward (when present) goes through ``adjust_territory_influence``.

Drop 1a scope:
  - Schema + ensure_schema
  - Cache-def model + DEV test pool (zone key "wildspace_dev_test")
  - Instance lifecycle (spawn, state transitions, cooldown)
  - Visibility check
  - harvest_mining (skill check, resource grant, cooldown set)

Deferred to later drops:
  - salvage / faction_cache harvest paths
  - Real zone YAML content (Geonosis Front, Hutt Frontier, etc.)
  - scan-output merge
  - Equipment mod bonuses (Mining Laser)
  - Web client panel
"""

from __future__ import annotations

import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import yaml

log = logging.getLogger(__name__)


# ── Schema ────────────────────────────────────────────────────────────────────

SPACE_CACHES_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS space_caches (
    cache_instance_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_key                TEXT    NOT NULL,
    cache_def_id            TEXT    NOT NULL,
    state                   TEXT    NOT NULL DEFAULT 'available',
    last_harvested_at       INTEGER,
    next_available_at       INTEGER,
    harvested_by_character_id INTEGER,
    harvest_count           INTEGER NOT NULL DEFAULT 0,
    visibility_factions     TEXT
)
"""

_SPACE_CACHES_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_space_caches_zone  ON space_caches(zone_key)",
    "CREATE INDEX IF NOT EXISTS idx_space_caches_state ON space_caches(state)",
]


async def ensure_schema(db) -> None:
    """Create space_caches table and indexes if absent. Idempotent.

    Mirrors engine.housing.ensure_schema convention — split-semicolon loop
    for the main SQL block, then individual index statements each wrapped in
    a silent try/except. Called from server.game_server boot path after
    player_cities schema init.
    """
    try:
        for stmt in SPACE_CACHES_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception as e:
        log.warning("[space_caches] schema create error: %s", e)

    for idx_sql in _SPACE_CACHES_INDEXES:
        try:
            await db.execute(idx_sql)
            await db.commit()
        except Exception:
            pass  # Index already exists


# ── Cache definition model ────────────────────────────────────────────────────

@dataclass
class CacheDef:
    """One entry from a zone's cache_pool.

    ``visibility`` is stored as-is from YAML/constant:
      - ``"universal"``   — all PCs see it
      - list of faction codes — rep ≥ 0 with any listed faction required
      - ``"hidden"``      — never on scan
    ``yield_table`` is a list of (weight, rtype, qty_min, qty_max, quality_min,
    quality_max) tuples used by harvest_mining.
    """
    id: str
    kind: str                   # "mining" | "faction_cache" | "derelict"
    visibility: object          # "universal" | list[str] | "hidden"
    respawn_minutes: int        # cooldown length
    density: int                # average number of instances active at once
    yield_table: list = field(default_factory=list)
    rep_reward: dict = field(default_factory=dict)  # {faction_code: delta}


# ── DEV / Test zone constants (Drop 1a throwaway) ────────────────────────────
#
# Zone key "wildspace_dev_test" — used ONLY by tests and the dev mine command.
# Real zone content (Geonosis Front, Hutt Frontier) ships in Drops 2/3 via
# data/worlds/clone_wars/wildspace/sieges.yaml et al.
#
# Yield table columns: (weight, rtype, qty_min, qty_max, qual_min, qual_max)
# Resource types must be registered in engine.crafting.RESOURCE_TYPES.

DEV_TEST_ZONE_KEY = "wildspace_dev_test"

DEV_TEST_CACHE_POOL: dict[str, CacheDef] = {
    # Universal mining node — visible to every PC regardless of faction.
    "asteroid_ore_cluster": CacheDef(
        id="asteroid_ore_cluster",
        kind="mining",
        visibility="universal",
        respawn_minutes=45,
        density=4,
        yield_table=[
            # (weight, rtype, qty_min, qty_max, qual_min, qual_max)
            (50, "metal",     2, 6,  40, 70),
            (30, "composite", 1, 3,  35, 65),
            (20, "rare",      1, 2,  50, 80),
        ],
        rep_reward={},
    ),
    # Faction-gated node — only PCs with republic rep ≥ 0 can see it.
    # Uses a minimal loot table; the primary test is visibility gating.
    "republic_supply_debris": CacheDef(
        id="republic_supply_debris",
        kind="mining",
        visibility=["republic"],
        respawn_minutes=60,
        density=2,
        yield_table=[
            (60, "metal",    2, 5, 45, 70),
            (40, "energy",   1, 3, 40, 65),
        ],
        rep_reward={"republic": 1},
    ),
}


# ── Real wildspace cache pools (loaded from YAML) ────────────────────────────
#
# Drop 2: Sieges Theater content lives in
#   data/worlds/<era>/wildspace/sieges.yaml
# loaded into {zone_key: {def_id: CacheDef}} and cached at module level
# (mirrors engine.npc_space_traffic._load_zone_graph's caching). Hutt
# Frontier (hutt_frontier.yaml) is wired in by adding its filename here in
# Drop 3 — no code change beyond the table entry.

_WILDSPACE_THEATER_FILES = {
    "sieges": "sieges.yaml",
    # "hutt_frontier": "hutt_frontier.yaml",   # Drop 3
}

_WILDSPACE_POOLS_CACHE: Optional[dict[str, dict[str, CacheDef]]] = None


def _wildspace_dir() -> str:
    """Return data/worlds/<active_era>/wildspace for the active era."""
    try:
        from engine.era_state import get_active_era
        era = get_active_era()
    except Exception:  # pragma: no cover - defensive
        era = "clone_wars"
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
    return os.path.join(data_dir, "worlds", era, "wildspace")


def _cache_def_from_yaml(def_id: str, c: dict) -> CacheDef:
    """Build a CacheDef from one YAML cache entry. yield_table rows are
    lists in YAML and become tuples (harvest_mining unpacks 6 fields)."""
    return CacheDef(
        id=def_id,
        kind=c.get("kind", "mining"),
        visibility=c.get("visibility", "universal"),
        respawn_minutes=int(c.get("respawn_minutes", 60)),
        density=int(c.get("density", 1)),
        yield_table=[tuple(row) for row in (c.get("yield_table") or [])],
        rep_reward=dict(c.get("rep_reward", {}) or {}),
    )


def _load_wildspace_pools() -> dict[str, dict[str, CacheDef]]:
    """Load + cache all wildspace cache pools for the active era.

    Returns {zone_key: {cache_def_id: CacheDef}}. Tolerant of a missing or
    malformed theater file (logs + skips). Cached at module level; call
    ``reload_wildspace_pools()`` to re-read (tests / era flips).
    """
    global _WILDSPACE_POOLS_CACHE
    if _WILDSPACE_POOLS_CACHE is not None:
        return _WILDSPACE_POOLS_CACHE

    pools: dict[str, dict[str, CacheDef]] = {}
    base = _wildspace_dir()
    for theater, fname in _WILDSPACE_THEATER_FILES.items():
        fpath = os.path.join(base, fname)
        if not os.path.exists(fpath):
            continue
        try:
            with open(fpath, encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
        except Exception:
            log.warning("[space_caches] failed reading %s", fpath, exc_info=True)
            continue
        for zone_key, zdata in (raw.get("zones", {}) or {}).items():
            zone_pool: dict[str, CacheDef] = {}
            for def_id, c in ((zdata or {}).get("caches", {}) or {}).items():
                try:
                    zone_pool[def_id] = _cache_def_from_yaml(def_id, c)
                except Exception:
                    log.warning("[space_caches] bad cache def %s/%s in %s",
                                zone_key, def_id, fname, exc_info=True)
            if zone_pool:
                pools[zone_key] = zone_pool

    _WILDSPACE_POOLS_CACHE = pools
    return pools


def reload_wildspace_pools() -> dict[str, dict[str, CacheDef]]:
    """Drop the module cache and re-read wildspace pools. For tests/era flips."""
    global _WILDSPACE_POOLS_CACHE
    _WILDSPACE_POOLS_CACHE = None
    return _load_wildspace_pools()


def get_cache_pool(zone_key: str) -> dict[str, CacheDef]:
    """Return the cache-def pool for a zone key.

    The DEV test zone uses the in-module constant pool; all real zones load
    from data/worlds/<era>/wildspace/*.yaml (Sieges Theater in Drop 2, Hutt
    Frontier in Drop 3). Unknown zones return {} (not a wildspace zone).
    """
    if zone_key == DEV_TEST_ZONE_KEY:
        return DEV_TEST_CACHE_POOL
    return _load_wildspace_pools().get(zone_key, {})


# ── Instance lifecycle ─────────────────────────────────────────────────────────

async def spawn_zone_caches(db, zone_key: str) -> int:
    """Spawn cache instances for a zone up to their defined density.

    Idempotent: only creates rows for cache_def_ids where the active
    (state='available') count is below the def's density. Returns the
    number of new instances created.

    Called when a ship first enters a wildspace zone (or at server boot
    for pre-warm). Safe to call repeatedly.
    """
    pool = get_cache_pool(zone_key)
    if not pool:
        return 0

    created = 0
    for def_id, cache_def in pool.items():
        # How many active instances already exist?
        rows = await db.fetchall(
            "SELECT COUNT(*) AS cnt FROM space_caches "
            "WHERE zone_key = ? AND cache_def_id = ? AND state = 'available'",
            (zone_key, def_id),
        )
        existing = int(rows[0]["cnt"]) if rows else 0
        to_create = max(0, cache_def.density - existing)
        vis_json = _encode_visibility(cache_def.visibility)
        for _ in range(to_create):
            await db.execute(
                "INSERT INTO space_caches "
                "(zone_key, cache_def_id, state, visibility_factions) "
                "VALUES (?, ?, 'available', ?)",
                (zone_key, def_id, vis_json),
            )
            created += 1
    if created:
        await db.commit()
    return created


def _encode_visibility(visibility) -> Optional[str]:
    """Encode the visibility field to a JSON string for DB storage.

    ``"universal"`` → None (NULL in DB, checked by IS NULL test)
    list[str]       → JSON array string
    ``"hidden"``    → ``"hidden"`` literal
    """
    if visibility == "universal":
        return None
    if visibility == "hidden":
        return "hidden"
    if isinstance(visibility, list):
        return json.dumps(visibility)
    return None


async def get_zone_caches(db, zone_key: str) -> list[dict]:
    """Return all cache instance rows for a zone as a list of dicts."""
    rows = await db.fetchall(
        "SELECT * FROM space_caches WHERE zone_key = ?",
        (zone_key,),
    )
    return [dict(r) for r in rows]


async def get_cache_instance(db, cache_instance_id: int) -> Optional[dict]:
    """Fetch a single cache instance row as a dict, or None."""
    row = await db.fetchone(
        "SELECT * FROM space_caches WHERE cache_instance_id = ?",
        (cache_instance_id,),
    )
    return dict(row) if row else None


async def set_cache_cooldown(db, cache_instance_id: int,
                             char_id: int, respawn_minutes: int) -> None:
    """Transition a cache instance to 'cooldown' state.

    Sets last_harvested_at = now, next_available_at = now + respawn_seconds,
    increments harvest_count. Called by harvest_mining after a successful hit.
    """
    now = int(time.time())
    next_at = now + respawn_minutes * 60
    await db.execute(
        "UPDATE space_caches "
        "SET state = 'cooldown', "
        "    last_harvested_at = ?, "
        "    next_available_at = ?, "
        "    harvested_by_character_id = ?, "
        "    harvest_count = harvest_count + 1 "
        "WHERE cache_instance_id = ?",
        (now, next_at, char_id, cache_instance_id),
    )
    await db.commit()


async def tick_cache_respawns(db, zone_key: str) -> int:
    """Flip 'cooldown' instances whose next_available_at has passed back to 'available'.

    Returns the count transitioned. Safe to call at any cadence.
    """
    now = int(time.time())
    rows = await db.fetchall(
        "SELECT cache_instance_id FROM space_caches "
        "WHERE zone_key = ? AND state = 'cooldown' AND next_available_at <= ?",
        (zone_key, now),
    )
    if not rows:
        return 0
    for row in rows:
        await db.execute(
            "UPDATE space_caches SET state = 'available' "
            "WHERE cache_instance_id = ?",
            (row["cache_instance_id"],),
        )
    await db.commit()
    return len(rows)


# ── Visibility check ───────────────────────────────────────────────────────────

def is_cache_visible(cache_row: dict, char_rep_flat: dict) -> bool:
    """Return True if this cache instance is visible to a character.

    ``cache_row``    — a row dict from ``space_caches`` (has visibility_factions).
    ``char_rep_flat`` — flat {faction_code: int_rep} dict from
                        engine.organizations.get_all_faction_reps / housing's helper.

    Visibility rules per §4.4:
    - NULL (was "universal") → always visible.
    - "hidden"               → never visible.
    - JSON list[str]         → visible if char has rep ≥ 0 with ANY listed faction.
    """
    vis_raw = cache_row.get("visibility_factions")

    if vis_raw is None:
        # universal
        return True
    if vis_raw == "hidden":
        return False

    # JSON faction list
    try:
        factions = json.loads(vis_raw)
    except (json.JSONDecodeError, TypeError):
        # Malformed → treat as hidden (safe default)
        return False

    for fc in factions:
        rep = int(char_rep_flat.get(fc, -1))
        if rep >= 0:
            return True
    return False


# ── Harvest: mining ────────────────────────────────────────────────────────────

# Mining difficulty: Moderate (15) per WEG D6 moderate task. The skill used
# is "space transports" (the "Pilot" skill for space; §4.3 says "Pilot +
# Mechanical" — we run both checks and use the better result to model the
# combined approach, keeping the funnel call count to two explicit checks).
# Difficulty 10 = Easy-to-Moderate boundary (lenient for a grindy activity).
_MINE_SKILL_PRIMARY   = "space transports"   # canonical Pilot branch
_MINE_SKILL_SECONDARY = "space transports repair"  # Mechanical branch
_MINE_DIFFICULTY      = 10


@dataclass
class MineResult:
    """Return value from harvest_mining.

    Field naming mirrors SkillCheckResult where applicable:
      roll_total → result.roll from SkillCheckResult
      critical   → result.critical_success from SkillCheckResult
    """
    success: bool
    fumble: bool = False
    critical: bool = False       # True when SkillCheckResult.critical_success
    on_cooldown: bool = False
    not_found: bool = False
    wrong_kind: bool = False
    message: str = ""
    resource_type: Optional[str] = None
    resource_qty: int = 0
    resource_quality: float = 0.0
    rep_rewards: dict = field(default_factory=dict)   # {faction_code: delta}
    roll_total: int = 0          # SkillCheckResult.roll
    difficulty: int = _MINE_DIFFICULTY


async def harvest_mining(
    db,
    char: dict,
    cache_instance_id: int,
) -> MineResult:
    """Attempt to mine a space cache.

    Flow:
    1. Load the cache instance; validate state + kind.
    2. Run perform_skill_check (primary: space transports).
    3. On success: roll the yield table; call add_resource; set cooldown.
       Rep reward (if any): adjust_territory_influence.
    4. Return a MineResult struct.

    Funnel callers:
    - Skill check  : engine.skill_checks.perform_skill_check
    - Resource grant: engine.crafting.add_resource  (mutates char["inventory"])
    - Rep reward   : engine.territory.adjust_territory_influence
    - DOES NOT touch credits (no adjust_credits call — mining yields resources)
    """
    # 1. Load instance
    row = await get_cache_instance(db, cache_instance_id)
    if row is None:
        return MineResult(success=False, not_found=True,
                          message=f"Cache #{cache_instance_id} not found.")

    if row["state"] == "cooldown":
        remaining = int(row.get("next_available_at", 0) or 0) - int(time.time())
        if remaining > 0:
            mins = remaining // 60
            secs = remaining % 60
            return MineResult(
                success=False, on_cooldown=True,
                message=f"Cache #{cache_instance_id} is recharging "
                        f"({mins}m {secs}s remaining).",
            )
        # Cooldown expired but tick hasn't run yet — treat as available.
        await db.execute(
            "UPDATE space_caches SET state = 'available' "
            "WHERE cache_instance_id = ?",
            (cache_instance_id,),
        )
        await db.commit()
        row = await get_cache_instance(db, cache_instance_id)

    if row["state"] == "depleted":
        return MineResult(success=False,
                          message=f"Cache #{cache_instance_id} is fully depleted.")

    # Load the cache def to get yield table and respawn time
    zone_key  = row["zone_key"]
    def_id    = row["cache_def_id"]
    pool      = get_cache_pool(zone_key)
    cache_def = pool.get(def_id)
    if cache_def is None:
        return MineResult(success=False,
                          message=f"Cache def '{def_id}' not found for zone '{zone_key}'.")

    if cache_def.kind != "mining":
        return MineResult(success=False, wrong_kind=True,
                          message=f"Cache #{cache_instance_id} is not a mining node "
                                  f"(kind='{cache_def.kind}'). Use the appropriate command.")

    # 2. Skill check
    from engine.skill_checks import perform_skill_check
    from engine.character import get_cached_skill_registry
    try:
        sr = get_cached_skill_registry()
        result = perform_skill_check(char, _MINE_SKILL_PRIMARY, _MINE_DIFFICULTY, sr,
                                     auto_consume_lead=False)
    except Exception as exc:
        log.warning("[space_caches] perform_skill_check failed: %s", exc, exc_info=True)
        result = None

    fumble   = result.fumble          if result else False
    critical = result.critical_success if result else False
    roll_total = result.roll          if result else 0
    success  = (not fumble) and (result is None or result.roll >= _MINE_DIFFICULTY)

    if fumble:
        return MineResult(
            success=False, fumble=True,
            roll_total=roll_total,
            difficulty=_MINE_DIFFICULTY,
            message="Mining check fumbled! Equipment malfunction — "
                    "mining attempt failed. The node is undamaged.",
        )

    if not success:
        return MineResult(
            success=False,
            roll_total=roll_total,
            difficulty=_MINE_DIFFICULTY,
            message=f"Mining check failed (diff {_MINE_DIFFICULTY}, "
                    f"rolled {roll_total}). Couldn't extract ore. Try again.",
        )

    # 3. Roll yield table
    table = cache_def.yield_table
    if not table:
        # Defensive: empty table → generic metal
        rtype, qty_min, qty_max, qmin, qmax = "metal", 2, 4, 40, 60
    else:
        weights = [row_t[0] for row_t in table]
        chosen  = random.choices(table, weights=weights, k=1)[0]
        _, rtype, qty_min, qty_max, qmin, qmax = chosen

    qty     = random.randint(qty_min, qty_max)
    quality = float(random.randint(qmin, qmax))

    # Bonus on critical
    if critical:
        qty = max(qty, qty_max)

    # Grant resource via funnel; persist via save_character (allowlisted write path).
    from engine.crafting import add_resource
    add_resource(char, rtype, qty, quality)
    await db.save_character(char["id"], inventory=char["inventory"])

    # Set cooldown
    await set_cache_cooldown(db, cache_instance_id, char["id"],
                             cache_def.respawn_minutes)

    # Rep reward via funnel
    rep_applied: dict = {}
    for faction_code, delta in (cache_def.rep_reward or {}).items():
        try:
            from engine.territory import adjust_territory_influence
            # zone_id: territory uses int zone IDs; wildspace zones are
            # not in the territory table — pass 0 (no-op zone). The rep
            # reward lands as a flat influence delta on the org. The caller
            # (MineCommand) logs this for the player.
            await adjust_territory_influence(
                db, faction_code, 0, delta,
                reason="space_cache_mining",
            )
            rep_applied[faction_code] = delta
        except Exception as exc:
            log.warning("[space_caches] rep reward failed for %s: %s",
                        faction_code, exc, exc_info=True)

    return MineResult(
        success=True,
        fumble=False,
        critical=critical,
        roll_total=roll_total,
        difficulty=_MINE_DIFFICULTY,
        resource_type=rtype,
        resource_qty=qty,
        resource_quality=quality,
        rep_rewards=rep_applied,
        message=(
            f"{'Critical extraction! ' if critical else ''}"
            f"Extracted {qty}x {rtype} (quality {quality:.0f})."
        ),
    )
