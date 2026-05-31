# -*- coding: utf-8 -*-
"""
engine/region_quality.py — Weekly wilderness region quality (SYN.6.b, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.5.5.

The SWG resource lesson: a region's resource yield isn't a fixed value
but rolls weekly, per-resource-type. Some weeks Tatooine's Dune Sea
metal is exceptional (1.3×); other weeks the chemical there is 0.8×
while organic is 1.2×. Crafters travel to follow the high-quality
weeks. This is the "crafter's news feed" — drives wilderness traffic
without forcing combat engagement.

Mechanically:

  * Each Monday at server midnight (in practice: an hourly tick that
    checks ISO year-week and rolls per-region-per-type if the stored
    roll's year-week differs from current), every wilderness region
    rolls a multiplier in 0.7..1.3 for each of the
    ``engine.crafting.HARVESTABLE_RESOURCE_TYPES`` (the T1-T4 set;
    T5 mats are drop-only and don't participate in weekly variance —
    their quality is set at the drop event).
  * SYN.6.a's ``engine.harvest._get_region_quality`` reads from this
    table to scale resource stack quality (1.0× → q50, 1.3× → q65,
    plus skill-margin bonus).
  * Director ``faction resource_outlook`` reads the same data to
    surface best/worst regions of the current week (parser side).

What this module ships in SYN.6.b:

  * Schema:
      - ``region_quality`` table — (region_slug, resource_type) primary
        key with ``quality_multiplier`` (real 0.7..1.3), ``rolled_at``
        (real Unix ts), ``roll_year_week`` (text 'YYYY-Www' ISO 8601).
      - ``ensure_region_quality_schema(db)`` — idempotent create.

  * Pure helpers (no DB):
      - ``_iso_year_week(now)`` → 'YYYY-Www' canonical key
      - ``_compute_weekly_multiplier(rng)`` → float in 0.7..1.3
      - ``_outlook_summary(rows)`` → per-region best/worst type tuples

  * DB-touching:
      - ``roll_region_quality(db, region_slug, *, rng=None, now=None)``
        — single-region roll (called per-region by the weekly tick).
        Idempotent on a per-region-per-week basis (checks
        roll_year_week before rolling).
      - ``get_region_quality_for(db, region_slug)`` → ``dict[type, float]``
        for SYN.6.a's harvest consumer. Returns the per-resource-type
        multipliers (defaults to 1.0× for types not yet rolled).
      - ``get_outlook(db, org_code=None)`` → outlook digest data for
        the parser surface.
      - ``tick_weekly_region_quality(db, session_mgr)`` — the weekly
        tick wrapper. Iterates all wilderness regions (anything with
        a ``region_ownership`` row OR landmark rows in the world) and
        calls ``roll_region_quality`` for each. Idempotent — only
        regions whose current-week roll is missing get rolled.

Tick wiring lives in ``server/tick_handlers_economy.py`` +
``server/game_server.py`` (hourly cadence with per-region idempotence
anchor; mirrors the city_maintenance_tick pattern).

The seam SYN.6.a established (``engine.harvest._get_region_quality``)
becomes a thin wrapper around ``get_region_quality_for``. Existing
SYN.6.a tests pass quality as a float in their unit tests; new tests
exercise the dict form.
"""
from __future__ import annotations

import datetime
import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Design §2.5.5 — weekly multiplier range. Crafters chase the 1.3
# weeks; 0.7 weeks discourage harvest but don't shut it down.
QUALITY_MIN = 0.7
QUALITY_MAX = 1.3

# Baseline returned for any (region, type) not yet rolled. The harvest
# module's _quality_to_resource_quality maps 1.0× → q50 (mid-band) so
# regions/types that haven't seen a roll yet still produce reasonable
# harvest output.
QUALITY_BASELINE = 1.0


# ── Schema ───────────────────────────────────────────────────────────────────

REGION_QUALITY_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS region_quality (
    region_slug         TEXT    NOT NULL,
    resource_type       TEXT    NOT NULL,
    quality_multiplier  REAL    NOT NULL DEFAULT 1.0,
    rolled_at           REAL    NOT NULL DEFAULT 0,
    roll_year_week      TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (region_slug, resource_type)
);
CREATE INDEX IF NOT EXISTS idx_region_quality_slug
    ON region_quality(region_slug);
CREATE INDEX IF NOT EXISTS idx_region_quality_week
    ON region_quality(roll_year_week);
"""


async def ensure_region_quality_schema(db) -> None:
    """Create the ``region_quality`` table + indexes. Idempotent.

    Follows the SYN.1.a ``ensure_region_ownership_schema`` pattern —
    a per-feature schema bootstrap call rather than a global migration
    entry. Lets the SYN.6.b drop apply without touching the
    SCHEMA_VERSION constant. The migration system will pick this up on
    next normal init via the IF NOT EXISTS guard.
    """
    try:
        for stmt in REGION_QUALITY_SCHEMA_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
    except Exception:
        log.warning("[region_quality] schema create failed", exc_info=True)


# ── Pure helpers ─────────────────────────────────────────────────────────────

def _iso_year_week(now: Optional[float] = None) -> str:
    """Return the ISO 8601 year-week string for ``now`` ('YYYY-Www').

    ISO weeks start on Monday — exactly matching the design §2.5.5
    'Monday at server midnight' cadence. A region rolled in the same
    ISO week as ``now`` is "already rolled this week" and the tick
    skips it.

    Edge case: late-Sunday-night vs early-Monday rolls. ISO weeks
    don't roll until 00:00 Monday, so a server tick at Monday 00:01
    UTC sees a new week immediately. Servers in non-UTC timezones see
    the week boundary at their local UTC offset — that's acceptable
    drift for a weekly cadence.
    """
    if now is None:
        now = time.time()
    dt = datetime.datetime.fromtimestamp(now, tz=datetime.timezone.utc)
    year, week, _weekday = dt.isocalendar()
    return f"{year:04d}-W{week:02d}"


def _compute_weekly_multiplier(rng: random.Random) -> float:
    """Sample one weekly multiplier uniformly in [QUALITY_MIN, QUALITY_MAX].

    Returns a float rounded to 2 decimals to keep the DB readable and
    the outlook display stable. The rounding is at sample time so
    a value stored as 1.27 round-trips byte-identical.
    """
    raw = rng.uniform(QUALITY_MIN, QUALITY_MAX)
    return round(raw, 2)


def _outlook_summary(
    rows: list[dict],
) -> dict[str, dict]:
    """Per-region best/worst-type summary for the Director outlook.

    Input: list of region_quality rows (each with region_slug,
    resource_type, quality_multiplier).
    Output: ``{region_slug: {"best": (type, mult), "worst": (type, mult),
                              "all": {type: mult}}}``

    A region with no rows is omitted (caller filters before this).
    Ties on best/worst are broken alphabetically by type for stable
    display.
    """
    by_region: dict[str, dict[str, float]] = {}
    for r in rows:
        slug = r["region_slug"]
        rtype = r["resource_type"]
        try:
            mult = float(r["quality_multiplier"])
        except (TypeError, ValueError):
            mult = QUALITY_BASELINE
        by_region.setdefault(slug, {})[rtype] = mult

    out: dict[str, dict] = {}
    for slug, type_map in by_region.items():
        # Sort by (multiplier, type) — best is highest mult, ties
        # broken by alphabetical type for stable display.
        sorted_pairs = sorted(
            type_map.items(),
            key=lambda kv: (kv[1], kv[0]),
        )
        worst_type, worst_mult = sorted_pairs[0]
        best_type, best_mult = sorted_pairs[-1]
        out[slug] = {
            "best": (best_type, best_mult),
            "worst": (worst_type, worst_mult),
            "all": dict(type_map),
        }
    return out


# ── DB-touching helpers ──────────────────────────────────────────────────────

async def get_region_quality_for(
    db, region_slug: str,
) -> dict[str, float]:
    """Return per-resource-type quality multipliers for a region.

    Used by ``engine.harvest._get_region_quality`` (the seam SYN.6.a
    shipped). Returns a dict keyed by resource_type — every type in
    ``engine.crafting.HARVESTABLE_RESOURCE_TYPES`` is included,
    defaulting to
    ``QUALITY_BASELINE`` (1.0) for any type without a roll.

    Behavior on schema-absent: returns the all-baseline dict so a
    pre-SYN.6.b DB or test fixture without the schema still functions.
    This is the same "fail soft to baseline" posture the seam had in
    SYN.6.a (returned 1.0 as a single float).
    """
    # Import locally to dodge a circular dep if engine.crafting ever
    # imports from us.
    from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
    baseline_dict = {rtype: QUALITY_BASELINE for rtype in RESOURCE_TYPES}

    try:
        rows = await db.fetchall(
            "SELECT resource_type, quality_multiplier "
            "FROM region_quality WHERE region_slug = ?",
            (region_slug,),
        )
    except Exception:
        # Table may not exist yet (pre-SYN.6.b state or test fixture)
        log.debug("[region_quality] table read failed for %s; "
                  "returning baseline dict", region_slug)
        return baseline_dict

    for r in rows:
        try:
            baseline_dict[r["resource_type"]] = float(r["quality_multiplier"])
        except (TypeError, ValueError, KeyError):
            continue
    return baseline_dict


async def roll_region_quality(
    db, region_slug: str,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict[str, float]:
    """Roll fresh weekly quality for ``region_slug``, all resource types.

    Idempotent on a per-week basis: if every resource type for this
    region already has a row with ``roll_year_week`` matching the
    current ISO week, the function returns the existing values and
    writes nothing.

    Returns the post-roll ``{resource_type: multiplier}`` dict.
    """
    if rng is None:
        rng = random.Random()
    if now is None:
        now = time.time()

    from engine.crafting import HARVESTABLE_RESOURCE_TYPES as RESOURCE_TYPES
    current_week = _iso_year_week(now)

    # Read existing rows for this region
    try:
        existing_rows = await db.fetchall(
            "SELECT resource_type, quality_multiplier, roll_year_week "
            "FROM region_quality WHERE region_slug = ?",
            (region_slug,),
        )
    except Exception:
        log.warning("[region_quality] read failed for %s",
                    region_slug, exc_info=True)
        existing_rows = []

    existing = {r["resource_type"]: dict(r) for r in existing_rows}

    # Compute the set of types that need a roll this week
    need_roll = [
        rtype for rtype in RESOURCE_TYPES
        if existing.get(rtype, {}).get("roll_year_week") != current_week
    ]

    if not need_roll:
        # Fully up-to-date — return existing values.
        return {
            rtype: float(existing.get(rtype, {}).get("quality_multiplier",
                                                     QUALITY_BASELINE))
            for rtype in RESOURCE_TYPES
        }

    # Roll fresh values for the types that need it
    rolled_values: dict[str, float] = {}
    for rtype in need_roll:
        mult = _compute_weekly_multiplier(rng)
        rolled_values[rtype] = mult
        # UPSERT-equivalent (sqlite supports REPLACE)
        try:
            await db.execute(
                "INSERT OR REPLACE INTO region_quality "
                "(region_slug, resource_type, quality_multiplier, "
                " rolled_at, roll_year_week) VALUES (?, ?, ?, ?, ?)",
                (region_slug, rtype, mult, now, current_week),
            )
        except Exception:
            log.warning(
                "[region_quality] write failed for %s/%s",
                region_slug, rtype, exc_info=True,
            )

    try:
        await db.commit()
    except Exception:
        log.warning("[region_quality] commit failed", exc_info=True)

    # Assemble the full return dict (rolled + previously-stored)
    out: dict[str, float] = {}
    for rtype in RESOURCE_TYPES:
        if rtype in rolled_values:
            out[rtype] = rolled_values[rtype]
        else:
            stored = existing.get(rtype, {}).get("quality_multiplier")
            out[rtype] = float(stored) if stored is not None else QUALITY_BASELINE
    return out


# ── Outlook digest (Director surface data) ───────────────────────────────────

async def get_outlook(
    db, org_code: Optional[str] = None,
) -> dict[str, dict]:
    """Return the outlook summary for the current week.

    If ``org_code`` is given, restrict the summary to regions owned by
    that org. Otherwise return all regions with rolls.

    Output shape: same as ``_outlook_summary`` —
    ``{region_slug: {"best": (type, mult), "worst": (type, mult),
                      "all": {type: mult}}}``.
    """
    try:
        if org_code is None:
            rows = await db.fetchall(
                "SELECT region_slug, resource_type, quality_multiplier "
                "FROM region_quality"
            )
        else:
            # Join against region_ownership to filter
            rows = await db.fetchall(
                "SELECT rq.region_slug, rq.resource_type, "
                "       rq.quality_multiplier "
                "FROM region_quality rq "
                "JOIN region_ownership ro "
                "  ON ro.region_slug = rq.region_slug "
                "WHERE ro.org_code = ?",
                (org_code,),
            )
    except Exception:
        log.warning("[region_quality] outlook read failed", exc_info=True)
        return {}

    return _outlook_summary([dict(r) for r in rows])


# ── Weekly tick ──────────────────────────────────────────────────────────────

async def _iter_wilderness_regions(db) -> list[str]:
    """Enumerate every distinct wilderness_region_id present in rooms.

    This is broader than ``region_ownership`` (which only lists CLAIMED
    regions) — un-owned regions still need quality rolls because
    harvest can be done in them (the SYN.6.a logic awards
    ``_UNOWNED_FALLBACK_TIER`` yields). Pulling from the rooms table
    catches every region that has at least one materialised room.
    """
    try:
        rows = await db.fetchall(
            "SELECT DISTINCT wilderness_region_id FROM rooms "
            "WHERE wilderness_region_id IS NOT NULL "
            "  AND wilderness_region_id != ''"
        )
        return sorted({
            r["wilderness_region_id"] for r in rows
            if r["wilderness_region_id"]
        })
    except Exception:
        log.warning("[region_quality] region enumeration failed",
                    exc_info=True)
        return []


async def tick_weekly_region_quality(
    db, session_mgr=None,
    *,
    now: Optional[float] = None,
) -> int:
    """Weekly tick: roll per-region per-resource-type quality.

    Idempotent — only rolls (region, type) pairs whose stored
    ``roll_year_week`` doesn't match the current ISO week. Safe to call
    hourly (or any cadence ≤ weekly); only the first call per week
    actually writes.

    Returns the count of regions that received at least one roll on
    this call (for tick-log observability + tests).
    """
    if now is None:
        now = time.time()
    await ensure_region_quality_schema(db)

    regions = await _iter_wilderness_regions(db)
    if not regions:
        return 0

    rolled_count = 0
    for slug in regions:
        try:
            # Check before rolling so we can count regions actually
            # rolled (not just inspected). roll_region_quality is
            # already idempotent but the count needs the pre-check.
            current_week = _iso_year_week(now)
            existing = await db.fetchall(
                "SELECT 1 FROM region_quality "
                "WHERE region_slug = ? AND roll_year_week = ? LIMIT 1",
                (slug, current_week),
            )
            needs_roll = not existing
            await roll_region_quality(db, slug, now=now)
            if needs_roll:
                rolled_count += 1
        except Exception:
            log.warning("[region_quality] roll failed for %s", slug,
                        exc_info=True)
            continue

    if rolled_count > 0:
        log.info("[region_quality] weekly tick rolled %d region(s) for week %s",
                 rolled_count, _iso_year_week(now))

    return rolled_count
