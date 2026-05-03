# -*- coding: utf-8 -*-
"""
engine/wilderness_writer.py — Writes loaded wilderness regions to the DB.

Per wilderness_system_design_v1.md and the v40 §3.5 Village build
prerequisite stack. This is the **minimal-substrate** writer: it
takes a `WildernessRegion` from the loader and persists each landmark
as an ordinary `rooms` row with `wilderness_region_id` populated and
coordinates stored in properties JSON. Adjacency lists become
bidirectional exits.

What this writer does NOT do (deferred):
  - Generate per-tile rooms for non-landmark coordinates (the future
    look engine generates tile views on demand from region YAML +
    runtime state).
  - Wire encounter pools.
  - Wire region-edge connections to hand-built rooms (use landmark
    adjacency to a hand-built room slug instead, which the writer
    resolves through the room-id map at write time).

The writer is idempotent in the trivial sense: if a landmark room
with the same name already exists in the DB and is wilderness-tagged
to the same region, it is reused rather than duplicated. Adjacency
exits are de-duplicated via Database.create_exit's existing skip-if-
already-exists behavior.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Optional

from engine.wilderness_loader import WildernessRegion, WildernessLandmark

log = logging.getLogger(__name__)


@dataclass
class WildernessWriteResult:
    """Outcome of a wilderness region write. The slug→room_id map is
    the primary deliverable downstream — the Village quest engine
    (future drop) needs to resolve `village_outer_watch` to a room id."""
    region_slug: str = ""
    landmarks_written: int = 0
    landmarks_reused: int = 0
    exits_written: int = 0
    landmark_room_ids: dict = field(default_factory=dict)  # slug -> room_id
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    # Drop 2 (May 3 2026): sentinel room id and registry row id
    sentinel_room_id: Optional[int] = None
    region_registry_id: Optional[int] = None


async def write_wilderness_region(
    region: WildernessRegion,
    db,
    *,
    external_room_id_resolver=None,
) -> WildernessWriteResult:
    """Persist a loaded wilderness region to the database.

    Args:
        region: a validated WildernessRegion from
            engine.wilderness_loader.
        db: a connected Database.
        external_room_id_resolver: optional callable(slug) -> int|None.
            Called when an adjacency entry refers to a room slug that
            is NOT a landmark in this region (i.e., a hand-built
            edge-connection room). Returns the room_id if found, or
            None to skip the exit. Most callers won't supply this in
            the minimal-substrate drop because all Village adjacency
            is internal.

    Returns:
        WildernessWriteResult with the slug→room_id map.
    """
    result = WildernessWriteResult(region_slug=region.slug)

    if not region.landmarks:
        result.warnings.append(
            f"Region {region.slug!r} has no landmarks; nothing to write."
        )
        return result

    # ── Resolve zone_id ───────────────────────────────────────────────────
    # Wilderness landmarks anchor to the region's containing zone for
    # security inheritance. The zone must already exist (it's part of
    # the main world build); we look it up by name.
    zone_id = await _lookup_zone_id_by_name(db, region.zone)
    if zone_id is None:
        # Fall back to NULL zone — landmark still works but inherits
        # default security. Warn loudly because this means the world
        # build order is wrong (region wrote before its zone).
        result.warnings.append(
            f"Region {region.slug!r} zone {region.zone!r} not found in DB; "
            f"landmarks will have NULL zone_id and inherit default security."
        )

    # ── Pass 0 (Drop 2): write virtual sentinel + region registry ─────────
    # The sentinel room is the row characters' room_id points to when
    # they're in this wilderness region. Per
    # wilderness_system_design_v1.md §3.3: preserves the
    # "characters.room_id is always valid" invariant. The room itself
    # is never displayed; the wilderness renderer uses
    # (wilderness_region_slug, x, y) on the character instead.
    #
    # The registry row caches region metadata (bounds, default
    # terrain) so movement/render code doesn't have to re-parse the
    # YAML on every move.
    #
    # Both writes are idempotent on rebuild:
    #   - sentinel: matched by name == "Wilderness: <region_name>"
    #     and wilderness_region_id == region.slug
    #   - registry: ON CONFLICT(slug) — re-running the build
    #     refreshes config_json without inserting a duplicate.
    try:
        sentinel_id = await _write_or_reuse_sentinel(db, region, zone_id)
        result.sentinel_room_id = sentinel_id
    except Exception as e:
        result.errors.append(f"Failed to write sentinel for {region.slug!r}: {e}")
        return result

    try:
        registry_id = await _upsert_region_registry(db, region, sentinel_id)
        result.region_registry_id = registry_id
    except Exception as e:
        # Non-fatal: the registry is a cache. If the table doesn't
        # exist (older schema) or insert fails, we can still write
        # the landmarks. Log and continue.
        result.warnings.append(
            f"Failed to upsert wilderness_regions row for {region.slug!r}: {e}"
        )

    # ── Pass 1: write landmark rooms ──────────────────────────────────────
    for lm in region.landmarks:
        try:
            room_id, was_reused = await _write_landmark(
                db, lm, region, zone_id,
            )
            result.landmark_room_ids[lm.id] = room_id
            if was_reused:
                result.landmarks_reused += 1
            else:
                result.landmarks_written += 1
        except Exception as e:
            result.errors.append(
                f"Failed to write landmark {lm.id!r}: {e}"
            )

    if result.errors:
        return result

    # ── Pass 2: write adjacency exits ─────────────────────────────────────
    # Walk every landmark and create bidirectional exits to its
    # adjacency targets. Adjacency is an undirected graph in the
    # YAML (no "from" vs "to") so we de-duplicate via a seen set
    # AND rely on Database.create_exit's skip-if-exists.
    seen_pairs: set = set()
    for lm in region.landmarks:
        from_id = result.landmark_room_ids.get(lm.id)
        if from_id is None:
            continue

        for adj_slug in lm.adjacency:
            # Resolve adjacency target. First check internal landmarks.
            to_id = result.landmark_room_ids.get(adj_slug)

            # If not internal, try the external resolver (for edge
            # connections to hand-built rooms in future drops).
            if to_id is None and external_room_id_resolver is not None:
                try:
                    to_id = external_room_id_resolver(adj_slug)
                except Exception as e:
                    result.warnings.append(
                        f"external_room_id_resolver({adj_slug!r}) raised: {e}"
                    )
                    to_id = None

            if to_id is None:
                # Adjacency to a slug that doesn't exist yet. The
                # loader already warned; we silently skip the exit.
                continue

            # De-duplicate undirected edges
            pair = tuple(sorted([from_id, to_id]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            # Bidirectional exits. Direction names use stairwell-style
            # "to <name>" until the future tile-grid engine assigns
            # cardinal directions based on coordinate deltas.
            from_name = lm.name
            to_landmark = next(
                (l for l in region.landmarks if l.id == adj_slug), None,
            )
            to_name = to_landmark.name if to_landmark else adj_slug

            try:
                await db.create_exit(
                    from_id, to_id,
                    direction=adj_slug,           # exit name = target slug
                    name=f"to {to_name}",
                )
                await db.create_exit(
                    to_id, from_id,
                    direction=lm.id,
                    name=f"to {from_name}",
                )
                result.exits_written += 2
            except Exception as e:
                result.warnings.append(
                    f"Failed to create exit {lm.id!r} <-> {adj_slug!r}: {e}"
                )

    log.info(
        "[wilderness_writer] region %r: wrote %d landmarks (%d reused), "
        "%d exits", region.slug, result.landmarks_written,
        result.landmarks_reused, result.exits_written,
    )
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Internals
# ─────────────────────────────────────────────────────────────────────────────

async def _lookup_zone_id_by_name(db, zone_name: str) -> Optional[int]:
    """Find the DB id of the zone with the given name, or None."""
    rows = await db._db.execute_fetchall(
        "SELECT id FROM zones WHERE name = ? LIMIT 1",
        (zone_name,),
    )
    if not rows:
        # Try slug match as a fallback (zones.yaml uses slugs that
        # often match names but not always).
        rows = await db._db.execute_fetchall(
            "SELECT id FROM zones WHERE name = ? OR name LIKE ? LIMIT 1",
            (zone_name, f"%{zone_name}%"),
        )
        if not rows:
            return None
    return rows[0]["id"]


async def _write_landmark(
    db,
    lm: WildernessLandmark,
    region: WildernessRegion,
    zone_id: Optional[int],
) -> tuple:
    """Insert (or reuse) a single landmark room.

    Returns (room_id, was_reused).
    """
    # Reuse check: if a room with this exact name AND wilderness_region_id
    # already exists, treat as the same landmark (idempotent rebuild).
    rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? AND wilderness_region_id = ? "
        "LIMIT 1",
        (lm.name, region.slug),
    )
    if rows:
        return rows[0]["id"], True

    # Build properties JSON. Coordinates and ambient lines live here;
    # so do the landmark-specific flags from the region YAML.
    props = dict(lm.properties)
    props["wilderness_region_id"] = region.slug
    props["wilderness_coordinates"] = list(lm.coordinates)
    props["wilderness_terrain"] = lm.terrain
    if lm.ambient_lines:
        props["wilderness_ambient_lines"] = lm.ambient_lines
    # Make wilderness_landmark explicit on every wilderness room so
    # downstream code (future hazard handler, future faction overlays)
    # can filter by it without inferring from `wilderness_region_id`.
    props.setdefault("wilderness_landmark", True)
    # Per F.7.a (May 3 2026): emit the YAML landmark id as
    # properties.slug so downstream code (quest engine, navigation
    # helpers, anything that needs slug-based resolution) can find
    # this room by a stable identifier rather than its display name.
    # Mirrors the pattern that the planet world_writer already
    # follows for hand-built rooms (engine/world_writer.py:194).
    # setdefault, not assignment: an explicit `slug:` field in the
    # landmark YAML's properties block (rare but supported) wins.
    props.setdefault("slug", lm.id)

    cursor = await db._db.execute(
        "INSERT INTO rooms (name, desc_short, desc_long, zone_id, "
        "properties, wilderness_region_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            lm.name,
            lm.short_desc,
            lm.description,
            zone_id,
            json.dumps(props),
            region.slug,
        ),
    )
    await db._db.commit()
    return cursor.lastrowid, False


# ─────────────────────────────────────────────────────────────────────────────
# Drop 2 helpers: virtual sentinel + region registry
# ─────────────────────────────────────────────────────────────────────────────

async def _write_or_reuse_sentinel(db, region, zone_id) -> int:
    """Idempotently write the wilderness virtual-sentinel room.

    Sentinel rooms park ``characters.room_id`` while the actual
    location is tracked via ``wilderness_region_slug`` + ``wilderness_x/y``.
    Per wilderness_system_design_v1.md §3.3.

    The sentinel is matched on rebuild by:
      name = "Wilderness: <region.name>"
      wilderness_region_id = region.slug
      properties.slug = "wilderness_<region.slug>_virtual"

    Returns the room_id of the (new or reused) sentinel row.
    """
    sentinel_name = f"Wilderness: {region.name}"
    sentinel_slug = f"wilderness_{region.slug}_virtual"

    # Reuse check
    rows = await db._db.execute_fetchall(
        "SELECT id FROM rooms WHERE name = ? AND wilderness_region_id = ? "
        "LIMIT 1",
        (sentinel_name, region.slug),
    )
    if rows:
        return rows[0]["id"]

    # Build minimal properties — the room is never displayed to players,
    # but properties.slug lets engine code resolve it by name.
    props = {
        "slug": sentinel_slug,
        "wilderness_sentinel": True,
        "wilderness_region_id": region.slug,
    }

    cursor = await db._db.execute(
        "INSERT INTO rooms (name, desc_short, desc_long, zone_id, "
        "properties, wilderness_region_id) VALUES (?, ?, ?, ?, ?, ?)",
        (
            sentinel_name,
            f"[Virtual] {region.name}",
            (
                f"This is the wilderness sentinel room for "
                f"{region.name}. Characters whose room_id points "
                "here are actually located somewhere on the "
                "wilderness coordinate grid. Players never see this "
                "description — the wilderness renderer takes over."
            ),
            zone_id,
            json.dumps(props),
            region.slug,
        ),
    )
    await db._db.commit()
    return cursor.lastrowid


async def _upsert_region_registry(db, region, sentinel_room_id) -> Optional[int]:
    """Insert or update the wilderness_regions registry row.

    Caches region metadata for fast lookup at movement time so the
    engine doesn't have to re-parse the region YAML on every move.

    Returns the registry id, or None if the table doesn't exist
    (older schema; caller should warn rather than fail).
    """
    import time

    # Verify the table exists — older DBs (schema < v20) won't have it.
    rows = await db._db.execute_fetchall(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='wilderness_regions'"
    )
    if not rows:
        return None

    # Cache the full region config as JSON. Only stable, derived
    # data — not the YAML's raw bytes (those can grow large).
    config_json = json.dumps({
        "narrative_tone_key": getattr(region, "narrative_tone_key", "") or "",
        "schema_version": getattr(region, "schema_version", 1),
        "tile_scale_km": region.tile_scale_km,
    })

    # UPSERT on slug
    await db._db.execute(
        "INSERT INTO wilderness_regions ("
        " slug, name, planet, zone_slug, width, height,"
        " tile_scale_km, default_terrain, default_security,"
        " sentinel_room_id, config_json, created_at"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(slug) DO UPDATE SET"
        " name = excluded.name,"
        " planet = excluded.planet,"
        " zone_slug = excluded.zone_slug,"
        " width = excluded.width,"
        " height = excluded.height,"
        " tile_scale_km = excluded.tile_scale_km,"
        " default_terrain = excluded.default_terrain,"
        " default_security = excluded.default_security,"
        " sentinel_room_id = excluded.sentinel_room_id,"
        " config_json = excluded.config_json",
        (
            region.slug,
            region.name,
            region.planet,
            region.zone,
            region.grid_width,
            region.grid_height,
            region.tile_scale_km,
            region.default_terrain,
            region.default_security,
            sentinel_room_id,
            config_json,
            time.time(),
        ),
    )
    await db._db.commit()

    # Read back the id (UPSERT doesn't return lastrowid for the update path)
    rows = await db._db.execute_fetchall(
        "SELECT id FROM wilderness_regions WHERE slug = ? LIMIT 1",
        (region.slug,),
    )
    return rows[0]["id"] if rows else None

