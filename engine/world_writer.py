# -*- coding: utf-8 -*-
"""
engine/world_writer.py — Drop 3 of Priority F.0.

Writes a `WorldBundle` (from `engine.world_loader.load_world_dry_run`)
to the database, producing the same zones/rooms/exits the legacy
`build_mos_eisley.py` build path produces. This is the cutover-ready
writer; Drop 4 wires it into the boot path.

What this module covers:
  - Zones (with parent slug → parent_id resolution and properties)
  - Rooms (with zone slug → zone_id resolution, descriptions,
    properties, and map_x/map_y)
  - Exits (one DB row per direction; each YAML exit pair becomes
    two `create_exit` calls — forward then reverse — matching the
    legacy script's behavior)

What this module deliberately does NOT cover:
  - NPCs (`PLANET_NPCS`) — Drop 2b will extract these
  - Hireable crew, ships — out of F.0 scope; still live in
    `build_mos_eisley.py` as Python literals
  - Housing lots, test character — design v1 §4.5/§4.6 schemas exist
    but are deferred per design v1 §6.3
  - Seed-room linking (rooms 1/2/3) — handled by the boot path; not
    part of the world-content load
  - Transactional rollback semantics — the design doc §3 calls for
    "transactional semantics" but the existing `db.create_*` helpers
    each commit per call. Bringing this writer fully transactional
    requires refactoring the db helpers to accept an explicit
    transaction handle, which is its own ticket. This writer is
    safe to call against a fresh DB; partial-failure recovery is
    the caller's responsibility.

The writer returns `WriteResult` carrying:
  - `zone_ids` — slug → DB id, useful for downstream code that
    needs to reference zones (housing lots, NPC spawn rooms, etc.)
  - `room_ids` — slug → DB id (and the inverse `slug_for_room_id`)
  - `room_id_for_yaml_id` — yaml_id → db_id, since the YAML's
    "stable" room IDs are positional and the DB autogenerates IDs.
    Drop 4 / quest data uses the yaml_id space; the runtime uses
    the db_id space; this map is the bridge.

Public API:
    write_world_bundle(bundle, db) -> WriteResult
    build_rooms_manifest(result) -> dict           # slug → db_id
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from engine.world_loader import WorldBundle, Zone, Room, Exit

log = logging.getLogger(__name__)


# Compass + vertical directions — the canonical set the parser accepts
# without prefix matching. Mirrors `build_mos_eisley._VALID_DIRECTIONS`.
_VALID_DIRECTIONS = frozenset({
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
    "up", "down",
    "in", "out",
})


def _split_exit(raw: str) -> tuple[str, str]:
    """Split a YAML exit string into (direction_key, label).

    Mirrors `build_mos_eisley._split_exit` so YAML-driven builds
    produce the same DB shape:

        "north"                   -> ("north", "")
        "north to Beggar's Canyon"-> ("north", "Beggar's Canyon")
        "board"                   -> ("board", "")    # custom keyword

    Custom keywords (anything outside _VALID_DIRECTIONS) round-trip as
    the lowercase key with an empty label. The runtime parser falls back
    to prefix matching for those.
    """
    raw = (raw or "").strip()
    if not raw:
        return "", ""
    parts = raw.split(None, 1)
    key = parts[0].lower()
    if key not in _VALID_DIRECTIONS:
        return raw.lower(), ""
    if len(parts) == 1:
        return key, ""
    rest = parts[1].strip()
    label = rest[3:].strip() if rest.lower().startswith("to ") else rest
    return key, label


@dataclass
class WriteResult:
    """Outcome of write_world_bundle. Carries the slug→id maps the
    cutover code needs to translate between the YAML id-space and the
    DB id-space."""
    zone_ids: dict[str, int] = field(default_factory=dict)
    room_ids: dict[str, int] = field(default_factory=dict)
    room_id_for_yaml_id: dict[int, int] = field(default_factory=dict)
    slug_for_room_id: dict[int, str] = field(default_factory=dict)
    exits_written: int = 0

    @property
    def zones_written(self) -> int:
        return len(self.zone_ids)

    @property
    def rooms_written(self) -> int:
        return len(self.room_ids)


# ── Zone writer ──────────────────────────────────────────────────────────────


async def _write_zones(zones: dict[str, Zone], db) -> dict[str, int]:
    """Insert zones, resolving parent links by slug.

    Zones with parents are inserted after their parents so the
    parent_id is available when create_zone is called. We do this by
    walking the parent graph in dependency order. The graph is small
    (≤ 30 zones in any era we ship) and a topological sort is overkill;
    we just iterate, deferring zones whose parent isn't yet written,
    bailing if no progress is made (cycle detection).
    """
    pending: list[tuple[str, Zone]] = list(zones.items())
    written: dict[str, int] = {}
    while pending:
        progressed = False
        next_pending: list[tuple[str, Zone]] = []
        for slug, zone in pending:
            parent_slug = zone.raw.get("parent")
            if parent_slug and parent_slug not in written:
                next_pending.append((slug, zone))
                continue

            display_name = zone.raw.get("name", slug)
            properties = zone.raw.get("properties", {}) or {}
            parent_id = written.get(parent_slug) if parent_slug else None
            zone_id = await db.create_zone(
                display_name,
                parent_id=parent_id,
                properties=json.dumps(properties),
            )
            written[slug] = zone_id
            progressed = True
        if not progressed and next_pending:
            unresolved = sorted(s for s, _ in next_pending)
            raise RuntimeError(
                f"Zone parent resolution stuck — unresolved: {unresolved}. "
                "Likely a parent cycle or a parent slug that doesn't "
                "exist in zones.yaml."
            )
        pending = next_pending
    return written


# ── Room writer ──────────────────────────────────────────────────────────────


async def _write_rooms(rooms: dict[int, Room],
                       zone_ids: dict[str, int],
                       db) -> tuple[dict[str, int], dict[int, int], dict[int, str]]:
    """Insert rooms in YAML id order. Returns three maps:
       - slug → db_id
       - yaml_id → db_id
       - db_id → slug
    """
    slug_to_id: dict[str, int] = {}
    yaml_to_db: dict[int, int] = {}
    id_to_slug: dict[int, str] = {}
    for yaml_id in sorted(rooms.keys()):
        room = rooms[yaml_id]
        zone_id = zone_ids.get(room.zone) if room.zone else None
        if room.zone and zone_id is None:
            raise RuntimeError(
                f"Room {yaml_id} ({room.slug}) references zone "
                f"{room.zone!r} which is not in the zones map. "
                "Did the zones.yaml file forget to declare it?"
            )
        # Per-room properties merge: ROOM_OVERRIDES from build_mos_eisley
        # were emitted as the room's `properties` raw key during Drop 2.
        properties = room.raw.get("properties", {}) or {}
        db_id = await db.create_room(
            room.name,
            desc_short=room.short_desc or "",
            desc_long=room.description or "",
            zone_id=zone_id,
            properties=json.dumps(properties),
        )
        slug_to_id[room.slug] = db_id
        yaml_to_db[yaml_id] = db_id
        id_to_slug[db_id] = room.slug

        # Map coordinates (separate UPDATE because create_room doesn't
        # take map_x/map_y in its signature — mirrors how
        # build_mos_eisley.py does it).
        if room.map_x is not None or room.map_y is not None:
            update_fields = {}
            if room.map_x is not None:
                update_fields["map_x"] = room.map_x
            if room.map_y is not None:
                update_fields["map_y"] = room.map_y
            await db.update_room(db_id, **update_fields)

    return slug_to_id, yaml_to_db, id_to_slug


# ── Exit writer ──────────────────────────────────────────────────────────────


async def _write_exits(exits: list[Exit],
                       yaml_to_db: dict[int, int],
                       db) -> int:
    """Insert exit pairs. Each YAML exit becomes two DB rows
    (forward + reverse). Returns total DB rows written.

    The legacy script's `db.create_exit` is no-op-on-duplicate, so
    re-running the writer against an already-populated DB will not
    double-write.
    """
    written = 0
    for ex in exits:
        from_db = yaml_to_db.get(ex.from_id)
        to_db = yaml_to_db.get(ex.to_id)
        if from_db is None or to_db is None:
            raise RuntimeError(
                f"Exit references unknown room: {ex.from_id} -> {ex.to_id} "
                f"(yaml_to_db missing one or both)."
            )
        fwd_key, fwd_label = _split_exit(ex.forward)
        rev_key, rev_label = _split_exit(ex.reverse)
        await db.create_exit(from_db, to_db, fwd_key, fwd_label)
        # Reverse direction may be the empty string in YAML for one-way
        # exits; create_exit's "" direction would still fail validation
        # downstream. Skip reverse if empty.
        if rev_key:
            await db.create_exit(to_db, from_db, rev_key, rev_label)
            written += 2
        else:
            written += 1
    return written


# ── Top-level entrypoint ─────────────────────────────────────────────────────


async def write_world_bundle(bundle: WorldBundle, db) -> WriteResult:
    """Write a fully-validated WorldBundle to the database.

    Args:
        bundle: from `engine.world_loader.load_world_dry_run(era)`.
            Must have `bundle.report.ok == True` — failing validation
            and writing anyway is a footgun.
        db: a connected, initialized `db.database.Database` (or any
            object exposing the same `create_zone`/`create_room`/
            `create_exit`/`update_room` async methods).

    Returns:
        WriteResult with slug↔id maps. Drop 4's cutover code uses
        these to translate between the YAML id-space (positional,
        stable across versions) and the DB id-space (autogenerated,
        per-build).

    Raises:
        ValueError: if `bundle.report.ok` is False — refusing to
            commit unvalidated content. Validate first; write second.
        RuntimeError: on parent-zone cycle, missing zone reference,
            or missing room reference.
    """
    if not bundle.report.ok:
        raise ValueError(
            "Refusing to write unvalidated WorldBundle. "
            "ValidationReport.errors: " +
            "; ".join(bundle.report.errors[:5])
        )

    log.info(
        "Writing world bundle: era=%s, zones=%d, rooms=%d, exits=%d",
        bundle.manifest.era_code,
        len(bundle.zones), len(bundle.rooms), len(bundle.exits),
    )

    zone_ids = await _write_zones(bundle.zones, db)
    log.info("  Wrote %d zones", len(zone_ids))

    slug_to_id, yaml_to_db, id_to_slug = await _write_rooms(
        bundle.rooms, zone_ids, db,
    )
    log.info("  Wrote %d rooms", len(slug_to_id))

    exits_written = await _write_exits(bundle.exits, yaml_to_db, db)
    log.info("  Wrote %d exit rows", exits_written)

    return WriteResult(
        zone_ids=zone_ids,
        room_ids=slug_to_id,
        room_id_for_yaml_id=yaml_to_db,
        slug_for_room_id=id_to_slug,
        exits_written=exits_written,
    )


def build_rooms_manifest(result: WriteResult) -> dict:
    """Build the `rooms_manifest.json` payload — a slug → db_id map
    plus inverse and metadata. Other code (quest data, design docs,
    test characters) references rooms by slug; this manifest gives
    the runtime translation.

    Output shape:
        {
          "schema_version": 1,
          "rooms": {
            "<slug>": <db_id>,
            ...
          },
          "by_id": {
            "<db_id>": "<slug>",
            ...
          }
        }

    The caller is responsible for serializing this to disk if needed.
    """
    return {
        "schema_version": 1,
        "rooms": dict(sorted(result.room_ids.items())),
        "by_id": {str(k): v for k, v in sorted(result.slug_for_room_id.items())},
    }
