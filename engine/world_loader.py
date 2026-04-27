# -*- coding: utf-8 -*-
"""
engine/world_loader.py — Era-parameterized world content loader.

Drop 1 of Priority F.0 (per world_data_extraction_design_v1.md §9).

This module loads world content (era manifest, zones, rooms, exits) from
YAML files under data/worlds/<era>/ and validates that content for
internal consistency. It does NOT write to the database — that's Drop 3.
The intent of Drop 1 is to give the rest of the loader pipeline a stable,
tested foundation: parse, validate, fail loudly.

Schema authority: the YAML on disk is authoritative. The design doc
(world_data_extraction_design_v1.md §4) proposed a slightly different
shape (slug-keyed exits, nested map coords, list-of-zones); Brian's
already-authored content under data/worlds/clone_wars/ uses integer-ID
exits, flat map_x/map_y, and a dict-of-zones. This loader matches what's
on disk. See LOADER_NOTES.md (forthcoming) for the divergence record.

Public API:
    load_era_manifest(era_dir) -> EraManifest
    load_zones(era_dir, manifest) -> dict[str, Zone]
    load_planets(era_dir, manifest) -> tuple[dict[int, Room], list[Exit]]
    validate_world(zones, rooms, exits) -> ValidationReport
    load_world_dry_run(era) -> WorldBundle

Drop 1 stops at load_world_dry_run — parse, validate, return the bundle.
Drops 2-4 add DB writes, equivalence diff, and boot wire-up.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


log = logging.getLogger(__name__)

# Where world content lives. Caller can override for tests.
DEFAULT_WORLDS_ROOT = Path("data") / "worlds"

# Valid exit directions. Compass + vertical + named custom directions
# matching the regex below. Authors can use anything in COMPASS_DIRS
# verbatim; custom directions like "board" or "out" are allowed if they
# match the slug regex.
COMPASS_DIRS = frozenset({
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
    "up", "down",
    "in", "out",
})

# Custom direction names: lowercase letters, digits, underscores, spaces.
# Matches the §5.5 validation rule.
import re
_CUSTOM_DIR_RE = re.compile(r"^[a-z][a-z0-9_ ]*$")


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class EraManifest:
    """Parsed era.yaml. The bag of paths and policy knobs."""
    era_code: str
    era_name: str
    schema_version: int
    era_dir: Path
    zones_path: Path
    organizations_path: Optional[Path]
    planet_paths: list[Path]
    wilderness_paths: list[Path]
    # Drop A (CW content gap remediation): `npcs` in era.yaml is now a
    # list of one or more files. The legacy single-string form is still
    # accepted by load_era_manifest and wrapped to a single-element list.
    # See data/worlds/clone_wars/npcs_cw_replacements.yaml header for
    # the full rationale (replaces:-keyed in-place GG7 substitution).
    npcs_paths: list[Path]
    housing_lots_path: Optional[Path]
    test_character_path: Optional[Path]
    test_jedi_path: Optional[Path]
    policy: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


@dataclass
class Zone:
    """A zone definition from zones.yaml.

    Stored under its zone slug (the YAML key). `name_match` is the
    prefix used for retrofit matching against existing DB rows;
    `narrative_tone` is the Director-AI atmospheric directive.
    """
    slug: str
    name_match: Optional[str] = None
    narrative_tone: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class Room:
    """A room from a planet YAML. ID is the canonical integer reference.

    Slug is human-readable. Both must be unique world-wide.
    """
    id: int
    slug: str
    name: str
    short_desc: str
    description: str
    zone: str
    map_x: Optional[int]
    map_y: Optional[int]
    planet: str  # injected by loader from the planet file's `planet:` field
    raw: dict = field(default_factory=dict)


@dataclass
class Exit:
    """An exit between two rooms. References rooms by integer ID."""
    from_id: int
    to_id: int
    forward: str
    reverse: str
    planet: str  # injected by loader from the planet file
    locked: bool = False
    hidden: bool = False
    raw: dict = field(default_factory=dict)


@dataclass
class ValidationReport:
    """Outcome of validate_world(). Errors fail boot; warnings don't."""
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def __bool__(self) -> bool:
        return self.ok


@dataclass
class WorldBundle:
    """Everything load_world_dry_run() returns. Drop 3 will pass this
    to the DB writer; Drop 1 just builds + validates it.
    """
    manifest: EraManifest
    zones: dict[str, Zone]
    rooms: dict[int, Room]
    exits: list[Exit]
    report: ValidationReport


class WorldLoadError(Exception):
    """Raised when YAML parse fails or required files are missing.

    Validation errors are NOT raised as this exception — they're
    collected in the ValidationReport so the caller decides whether to
    fail boot or surface them.
    """


# ── Era manifest loader ──────────────────────────────────────────────────────


def load_era_manifest(era_dir: Path) -> EraManifest:
    """Read `era.yaml` from `era_dir` and resolve content_refs paths.

    Raises WorldLoadError if the file is missing or malformed.
    """
    era_yaml = era_dir / "era.yaml"
    if not era_yaml.is_file():
        raise WorldLoadError(
            f"Missing era manifest: {era_yaml}. "
            f"Every era directory must have an era.yaml."
        )

    try:
        raw = yaml.safe_load(era_yaml.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {era_yaml}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{era_yaml}: top-level must be a mapping, got {type(raw).__name__}."
        )

    era_block = raw.get("era") or {}
    refs = raw.get("content_refs") or {}

    def resolve(path_field, required=True):
        rel = refs.get(path_field)
        if not rel:
            if required:
                raise WorldLoadError(
                    f"{era_yaml}: content_refs.{path_field} is required."
                )
            return None
        return era_dir / rel

    def resolve_list(field_name):
        items = refs.get(field_name) or []
        if not isinstance(items, list):
            raise WorldLoadError(
                f"{era_yaml}: content_refs.{field_name} must be a list, "
                f"got {type(items).__name__}."
            )
        return [era_dir / p for p in items]

    def resolve_list_or_legacy_string(field_name):
        """Accept a list of relative file paths OR a legacy single string.

        Drop A (CW content gap): the `npcs` field was originally a
        single string (`npcs: npcs.yaml`). Drop A introduces a multi-file
        form so an era can split additions and replacements across
        separate files without engine plumbing changes downstream.
        Returns a (possibly empty) list of resolved Paths in either case.
        """
        items = refs.get(field_name)
        if items is None:
            return []
        if isinstance(items, str):
            return [era_dir / items]
        if isinstance(items, list):
            return [era_dir / p for p in items]
        raise WorldLoadError(
            f"{era_yaml}: content_refs.{field_name} must be a string or a list, "
            f"got {type(items).__name__}."
        )

    return EraManifest(
        era_code=era_block.get("code", era_dir.name),
        era_name=era_block.get("name", era_dir.name.title()),
        schema_version=int(raw.get("schema_version", 1)),
        era_dir=era_dir,
        zones_path=resolve("zones", required=True),
        organizations_path=resolve("organizations", required=False),
        planet_paths=resolve_list("planets"),
        wilderness_paths=resolve_list("wilderness"),
        npcs_paths=resolve_list_or_legacy_string("npcs"),
        housing_lots_path=resolve("housing_lots", required=False),
        test_character_path=resolve("test_character", required=False),
        test_jedi_path=resolve("test_jedi", required=False),
        policy=raw.get("policy") or {},
        raw=raw,
    )


# ── Zone loader ──────────────────────────────────────────────────────────────


def load_zones(manifest: EraManifest) -> dict[str, Zone]:
    """Read zones.yaml. Returns a dict keyed by zone slug.

    The YAML stores zones as a top-level dict (zone_slug → zone_def),
    NOT a list. This matches the existing data/worlds/clone_wars/zones.yaml.
    """
    path = manifest.zones_path
    if not path.is_file():
        raise WorldLoadError(f"Missing zones file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict) or "zones" not in raw:
        raise WorldLoadError(
            f"{path}: top-level must be a mapping with a 'zones' key."
        )

    zones_raw = raw["zones"]
    if not isinstance(zones_raw, dict):
        raise WorldLoadError(
            f"{path}: 'zones' must be a mapping (zone_slug → definition), "
            f"got {type(zones_raw).__name__}."
        )

    zones: dict[str, Zone] = {}
    for slug, zd in zones_raw.items():
        if not isinstance(zd, dict):
            zd = {}  # tolerate empty mapping for zones with only a slug
        zones[slug] = Zone(
            slug=slug,
            name_match=zd.get("name_match"),
            narrative_tone=zd.get("narrative_tone"),
            raw=zd,
        )
    return zones


# ── Planet loader (rooms + exits) ────────────────────────────────────────────


def _load_planet_file(path: Path) -> tuple[list[Room], list[Exit]]:
    """Parse a single planet YAML into (rooms, exits) — the planet name
    is read from the file itself and stamped onto each room/exit.
    """
    if not path.is_file():
        raise WorldLoadError(f"Missing planet file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}."
        )

    planet = raw.get("planet")
    if not planet:
        raise WorldLoadError(f"{path}: missing top-level 'planet' field.")

    rooms_out: list[Room] = []
    for rd in (raw.get("rooms") or []):
        if not isinstance(rd, dict):
            raise WorldLoadError(
                f"{path}: every room must be a mapping; got {type(rd).__name__}."
            )
        if "id" not in rd:
            raise WorldLoadError(
                f"{path}: room missing 'id'. "
                f"Found keys: {sorted(rd.keys())}"
            )
        if "slug" not in rd:
            raise WorldLoadError(
                f"{path}: room id={rd['id']} missing 'slug'."
            )
        rooms_out.append(Room(
            id=int(rd["id"]),
            slug=str(rd["slug"]),
            name=str(rd.get("name", rd["slug"])),
            short_desc=str(rd.get("short_desc", "") or "").strip(),
            description=str(rd.get("description", "") or "").strip(),
            zone=str(rd.get("zone", "") or ""),
            map_x=rd.get("map_x"),
            map_y=rd.get("map_y"),
            planet=planet,
            raw=rd,
        ))

    exits_out: list[Exit] = []
    for ed in (raw.get("exits") or []):
        if not isinstance(ed, dict):
            raise WorldLoadError(
                f"{path}: every exit must be a mapping; got {type(ed).__name__}."
            )
        for required in ("from", "to", "forward", "reverse"):
            if required not in ed:
                raise WorldLoadError(
                    f"{path}: exit missing '{required}'. Got: {ed}"
                )
        exits_out.append(Exit(
            from_id=int(ed["from"]),
            to_id=int(ed["to"]),
            forward=str(ed["forward"]),
            reverse=str(ed["reverse"]),
            planet=planet,
            locked=bool(ed.get("locked", False)),
            hidden=bool(ed.get("hidden", False)),
            raw=ed,
        ))

    return rooms_out, exits_out


def load_planets(manifest: EraManifest
                  ) -> tuple[dict[int, Room], list[Exit]]:
    """Walk every planet file in manifest.planet_paths, return merged
    dict-of-rooms (keyed by integer ID) and flat list of exits.

    Duplicate IDs across planet files raise WorldLoadError immediately —
    that's a build-time catastrophe, not a validation warning.
    """
    rooms: dict[int, Room] = {}
    exits: list[Exit] = []
    for path in manifest.planet_paths:
        ps_rooms, ps_exits = _load_planet_file(path)
        for r in ps_rooms:
            if r.id in rooms:
                prev = rooms[r.id]
                raise WorldLoadError(
                    f"Duplicate room id={r.id}. "
                    f"First seen on planet '{prev.planet}' as '{prev.slug}', "
                    f"redefined on planet '{r.planet}' as '{r.slug}' in {path}."
                )
            rooms[r.id] = r
        exits.extend(ps_exits)
    return rooms, exits


# ── Validation pass ──────────────────────────────────────────────────────────


def _is_valid_direction(direction: str) -> bool:
    """A direction is valid if it's a compass term or matches the
    custom-direction regex.
    """
    if not direction:
        return False
    d = direction.strip().lower()
    if d in COMPASS_DIRS:
        return True
    return bool(_CUSTOM_DIR_RE.match(d))


def validate_world(zones: dict[str, Zone],
                   rooms: dict[int, Room],
                   exits: list[Exit]) -> ValidationReport:
    """Run all consistency checks. Errors fail boot; warnings advise.

    Implements §5.5 of world_data_extraction_design_v1.md, adapted to
    the integer-ID exit model:

      Errors:
        1. Unique room slugs (ID uniqueness already enforced at load)
        2. Unique zone slugs (already enforced — dict keys)
        3. Every exit's from_id and to_id resolve to a real room
        4. Every exit's forward and reverse direction is valid
        5. No outgoing-direction collisions per room
        6. Every room's zone exists in zones map
        7. (NPCs/housing — Drop 2)

      Warnings:
        - Rooms with zero exits (orphans)
        - Zones with zero rooms
        - Rooms missing map_x/map_y
    """
    report = ValidationReport()

    # 1. Unique room slugs
    slug_to_ids: dict[str, list[int]] = {}
    for r in rooms.values():
        slug_to_ids.setdefault(r.slug, []).append(r.id)
    for slug, ids in slug_to_ids.items():
        if len(ids) > 1:
            report.errors.append(
                f"Duplicate room slug '{slug}' on room ids: {sorted(ids)}"
            )

    # 3. Exit endpoint references resolve
    for ex in exits:
        if ex.from_id not in rooms:
            report.errors.append(
                f"Exit {ex.planet} from={ex.from_id} → to={ex.to_id} "
                f"references nonexistent from_id."
            )
        if ex.to_id not in rooms:
            report.errors.append(
                f"Exit {ex.planet} from={ex.from_id} → to={ex.to_id} "
                f"references nonexistent to_id."
            )

    # 4. Direction validity
    for ex in exits:
        if not _is_valid_direction(ex.forward):
            report.errors.append(
                f"Exit {ex.from_id}→{ex.to_id}: invalid forward direction "
                f"'{ex.forward}'."
            )
        # Reverse can be a multi-word phrase like "south to Bay 94" — accept
        # if the first token matches the rule. Authors use these phrases
        # to disambiguate when the reverse direction isn't simply the
        # mirror of the forward direction.
        rev_first = ex.reverse.split()[0] if ex.reverse else ""
        if not _is_valid_direction(rev_first):
            report.errors.append(
                f"Exit {ex.from_id}→{ex.to_id}: invalid reverse direction "
                f"'{ex.reverse}'."
            )

    # 5. Direction collisions per room
    # For each room, collect the set of outgoing-direction first-tokens
    # (forward direction for from-exits, first token of reverse for to-exits).
    # Duplicates are an error — a room can't have two "north" exits.
    room_outgoing: dict[int, dict[str, list[str]]] = {}
    for ex in exits:
        if ex.from_id in rooms:
            fwd = ex.forward.split()[0].lower() if ex.forward else ""
            room_outgoing.setdefault(ex.from_id, {}).setdefault(
                fwd, []
            ).append(f"to room {ex.to_id}")
        if ex.to_id in rooms:
            rev = ex.reverse.split()[0].lower() if ex.reverse else ""
            room_outgoing.setdefault(ex.to_id, {}).setdefault(
                rev, []
            ).append(f"back from room {ex.from_id}")
    for room_id, dir_map in room_outgoing.items():
        for direction, sources in dir_map.items():
            if len(sources) > 1:
                room_slug = rooms[room_id].slug
                report.errors.append(
                    f"Room {room_id} ({room_slug}): direction '{direction}' "
                    f"is claimed by {len(sources)} exits: {sources}"
                )

    # 6. Room zone references resolve
    for r in rooms.values():
        if r.zone and r.zone not in zones:
            report.errors.append(
                f"Room {r.id} ({r.slug}) on {r.planet}: "
                f"references nonexistent zone '{r.zone}'."
            )

    # ── Warnings ────────────────────────────────────────────────────────

    # Orphan rooms — zero connections in or out
    rooms_with_exits: set[int] = set()
    for ex in exits:
        rooms_with_exits.add(ex.from_id)
        rooms_with_exits.add(ex.to_id)
    for r in rooms.values():
        if r.id not in rooms_with_exits:
            report.warnings.append(
                f"Room {r.id} ({r.slug}) on {r.planet}: no exits in or out."
            )

    # Empty zones
    zone_room_counts: dict[str, int] = {z: 0 for z in zones}
    for r in rooms.values():
        if r.zone in zone_room_counts:
            zone_room_counts[r.zone] += 1
    for z, cnt in zone_room_counts.items():
        if cnt == 0:
            report.warnings.append(
                f"Zone '{z}' has no rooms."
            )

    # Missing coordinates — only warn if the room is in a planet whose
    # other rooms have coords, to avoid spamming for genuinely-blank
    # planets (kuat/kamino/geonosis prior to coord-tuning).
    planet_has_coords: dict[str, bool] = {}
    for r in rooms.values():
        planet_has_coords.setdefault(r.planet, False)
        if r.map_x is not None and r.map_y is not None:
            planet_has_coords[r.planet] = True
    for r in rooms.values():
        if planet_has_coords.get(r.planet) and (
            r.map_x is None or r.map_y is None
        ):
            report.warnings.append(
                f"Room {r.id} ({r.slug}) on {r.planet}: missing map_x/map_y "
                f"while other rooms on this planet have coords."
            )

    return report


# ── Top-level convenience ────────────────────────────────────────────────────


def load_world_dry_run(era: str,
                        worlds_root: Path = DEFAULT_WORLDS_ROOT
                        ) -> WorldBundle:
    """Parse + validate a complete era. Does NOT write to the DB.

    This is the Drop 1 entry point — Drops 2-4 will add a sibling
    `load_world` that also writes to the DB after dry-run validation
    passes.

    Caller should check `bundle.report.ok` before treating the bundle
    as usable. Boot path will raise on report.errors; tools (lint,
    audit) just print them.
    """
    era_dir = Path(worlds_root) / era
    manifest = load_era_manifest(era_dir)
    zones = load_zones(manifest)
    rooms, exits = load_planets(manifest)
    report = validate_world(zones, rooms, exits)
    return WorldBundle(
        manifest=manifest,
        zones=zones,
        rooms=rooms,
        exits=exits,
        report=report,
    )
