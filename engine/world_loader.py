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
    # Drop F.6a.1: paths for the Director / Lore pivot YAML files. All
    # three are optional — eras may omit any of them and the consuming
    # loader returns None. See clone_wars_director_lore_pivot_design_v1.md
    # §3 for the engine refactor that consumes these.
    lore_path: Optional[Path] = None
    director_config_path: Optional[Path] = None
    ambient_events_path: Optional[Path] = None
    # Drop F.7 (Apr 30 2026): optional chargen-templates pivot ref.
    # Eras may omit and the consuming loader (engine/chargen_templates_loader.py)
    # returns None. See F.7 handoff for the data-fy plan.
    chargen_templates_path: Optional[Path] = None
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


# ── F.4 (Apr 30 2026) — Per-room exit directive (staging type) ───────────────
# The newer planet-YAML schema (per clone_wars_era_design_v3.md §6) authors
# exits as a per-room dict: `exits: {direction: target_slug}`. These cannot
# be resolved to integer-ID `Exit` records until ALL planet files have been
# loaded, since cross-planet exits reference slugs not yet known to a single
# file. _load_planet_file collects these directives and load_planets resolves
# them after building a global slug→(id, planet) index.
@dataclass
class _PerRoomExitDirective:
    """A pre-resolution exit declaration from a per-room exits block."""
    from_slug: str
    direction: str
    to_slug: str
    planet: str  # the file the directive came from
    locked: bool = False
    hidden: bool = False


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
        # Drop F.6a.1: optional Director / Lore pivot refs.
        lore_path=resolve("lore", required=False),
        director_config_path=resolve("director_config", required=False),
        ambient_events_path=resolve("ambient_events", required=False),
        # Drop F.7 (Apr 30 2026): optional chargen-templates ref.
        chargen_templates_path=resolve("chargen_templates", required=False),
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


def _load_planet_file(path: Path) -> tuple[list[Room], list[Exit], list[_PerRoomExitDirective]]:
    """Parse a single planet YAML into (rooms, top_level_exits, per_room_directives)
    — the planet name is read from the file itself and stamped onto each
    room/exit/directive.

    Two exit schemas are supported (a planet file can use either or both):

      1. Top-level `exits:` list, integer-ID-keyed records with explicit
         `forward` and `reverse`. This is the legacy format used by
         tatooine.yaml and nar_shaddaa.yaml.

      2. Per-room `exits: {direction: target_slug}` dict on each room.
         This is the F.4 format used by coruscant/kuat/kamino/geonosis,
         per clone_wars_era_design_v3.md §6 ("Per-room exits blocks;
         every exit declared on the FROM side"). These cannot be resolved
         to Exit records here — load_planets pairs them after all planet
         files have been parsed.
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
    directives_out: list[_PerRoomExitDirective] = []
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
        room_slug = str(rd["slug"])
        rooms_out.append(Room(
            id=int(rd["id"]),
            slug=room_slug,
            name=str(rd.get("name", rd["slug"])),
            short_desc=str(rd.get("short_desc", "") or "").strip(),
            description=str(rd.get("description", "") or "").strip(),
            zone=str(rd.get("zone", "") or ""),
            map_x=rd.get("map_x"),
            map_y=rd.get("map_y"),
            planet=planet,
            raw=rd,
        ))

        # F.4: collect per-room exits (if any). The new schema uses a dict;
        # any non-dict (a list, etc.) is an authoring error.
        room_exits = rd.get("exits")
        if room_exits is not None and isinstance(room_exits, dict):
            for direction, target in room_exits.items():
                if not isinstance(target, str):
                    raise WorldLoadError(
                        f"{path}: room '{room_slug}' exit '{direction}' "
                        f"target must be a slug string; got {type(target).__name__}."
                    )
                directives_out.append(_PerRoomExitDirective(
                    from_slug=room_slug,
                    direction=str(direction),
                    to_slug=target,
                    planet=planet,
                ))

    exits_out: list[Exit] = []
    for ed in (raw.get("exits") or []):
        # Top-level `exits:` MUST be a list (legacy schema). If a planet file
        # mistakenly puts a top-level exits dict, that's an authoring error.
        if not isinstance(raw.get("exits"), list):
            raise WorldLoadError(
                f"{path}: top-level 'exits' must be a list (legacy schema). "
                f"For per-room exits use the room's own 'exits:' dict."
            )
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

    return rooms_out, exits_out, directives_out


def load_planets(manifest: EraManifest,
                  unresolved_report: Optional[list[str]] = None,
                  ) -> tuple[dict[int, Room], list[Exit]]:
    """Walk every planet file in manifest.planet_paths, return merged
    dict-of-rooms (keyed by integer ID) and flat list of exits.

    Duplicate IDs across planet files raise WorldLoadError immediately —
    that's a build-time catastrophe, not a validation warning.

    F.4 (Apr 30 2026): per-room exit directives from any planet file are
    collected first, then resolved to Exit records after all planets are
    parsed. The slug→(id, planet) index used for resolution is built from
    EVERY loaded room across EVERY planet file, so cross-planet exits work.

    If `unresolved_report` is provided, dangling per-room exit targets
    (slugs that don't resolve to any loaded room) are appended to it as
    string messages. Otherwise unresolved targets are silently dropped.
    The boot path passes a list and merges it into ValidationReport.errors;
    tools that just want the room/exit data can ignore it.
    """
    rooms: dict[int, Room] = {}
    exits: list[Exit] = []
    all_directives: list[_PerRoomExitDirective] = []
    for path in manifest.planet_paths:
        ps_rooms, ps_exits, ps_directives = _load_planet_file(path)
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
        all_directives.extend(ps_directives)

    # F.4: resolve per-room directives into Exit records.
    if all_directives:
        resolved = _resolve_per_room_directives(
            all_directives, rooms, unresolved_report=unresolved_report,
        )
        exits.extend(resolved)
    return rooms, exits


def _resolve_per_room_directives(directives: list[_PerRoomExitDirective],
                                  rooms: dict[int, Room],
                                  unresolved_report: Optional[list[str]] = None,
                                  ) -> list[Exit]:
    """Resolve per-room exit directives to Exit records.

    For each directive D = (from_slug, direction, to_slug):

      1. Look up from_slug and to_slug in the slug → (id, planet) index.
         Missing from_slug is a build-time error (the directive came
         from the room itself, so this would mean the same file declared
         a room and didn't register it). Missing to_slug is a soft error
         — the directive is dropped and recorded into unresolved_report
         so validate_world can surface it as part of a single combined
         report rather than crashing the load.

      2. Look for a paired directive D' on the destination room — i.e.,
         a directive with from_slug == D.to_slug and to_slug == D.from_slug.
         The pair's `direction` becomes D's `reverse`.

      3. If no pair is found, emit Exit with reverse="" and let
         validate_world report the dangling exit as a validation error
         (an empty reverse is an invalid direction).

    Directives are processed once each; the (forward, reverse) pair is
    emitted as a single Exit anchored on the alphabetically-first slug
    so we don't duplicate the same physical edge twice.
    """
    if unresolved_report is None:
        unresolved_report = []

    # Build slug → (id, planet) index
    slug_index: dict[str, tuple[int, str]] = {}
    for r in rooms.values():
        slug_index[r.slug] = (r.id, r.planet)

    # Build pair index: (from_slug, to_slug) -> direction (for fast pair lookup)
    forward_by_pair: dict[tuple[str, str], str] = {}
    for d in directives:
        forward_by_pair[(d.from_slug, d.to_slug)] = d.direction

    out: list[Exit] = []
    seen_pairs: set[tuple[str, str]] = set()

    for d in directives:
        # Skip if we've already emitted this physical edge (under either
        # direction's anchor).
        canonical = tuple(sorted([d.from_slug, d.to_slug]))
        if canonical in seen_pairs:
            continue

        # Resolve from-slug — this MUST exist (we got the directive from
        # the room itself).
        if d.from_slug not in slug_index:
            raise WorldLoadError(
                f"Per-room exit on planet '{d.planet}': from_slug "
                f"'{d.from_slug}' not found in any loaded room. "
                f"This is a loader-internal invariant violation."
            )
        from_id, from_planet = slug_index[d.from_slug]

        # Resolve to-slug — soft fail: record and skip. validate_world
        # surfaces these as a single combined report.
        if d.to_slug not in slug_index:
            unresolved_report.append(
                f"Per-room exit on '{d.from_slug}' (planet '{d.planet}'): "
                f"target slug '{d.to_slug}' (direction '{d.direction}') "
                f"not found in any loaded room."
            )
            seen_pairs.add(canonical)
            continue
        to_id, _to_planet = slug_index[d.to_slug]

        # Look for a paired reverse directive.
        reverse = forward_by_pair.get((d.to_slug, d.from_slug), "")

        # F.4: if no pair was authored, auto-derive the reverse for
        # canonical-symmetric cardinal directions. This rescues cases
        # like `north → south`, `up → down` where the author wrote the
        # forward exit on the source but forgot to declare the reverse
        # exit on the destination. Asymmetric directions (named hub/spoke
        # like `commercial/hub`) cannot be auto-derived; if those are
        # missing, validate_world flags them as invalid reverse direction.
        if not reverse:
            cardinal_inverses = {
                "north": "south", "south": "north",
                "east": "west", "west": "east",
                "northeast": "southwest", "southwest": "northeast",
                "northwest": "southeast", "southeast": "northwest",
                "up": "down", "down": "up",
                "in": "out", "out": "in",
            }
            inferred = cardinal_inverses.get(d.direction.strip().lower())
            if inferred:
                # Only auto-fill if the destination doesn't already have an
                # authored exit on that direction (don't clobber explicit
                # authoring).
                already_taken = any(
                    other.from_slug == d.to_slug
                    and other.direction.strip().lower() == inferred
                    for other in directives
                )
                if not already_taken:
                    reverse = inferred

        out.append(Exit(
            from_id=from_id,
            to_id=to_id,
            forward=d.direction,
            reverse=reverse,
            planet=from_planet,
            locked=d.locked,
            hidden=d.hidden,
            raw={
                "from_slug": d.from_slug,
                "to_slug": d.to_slug,
                "forward": d.direction,
                "reverse": reverse,
                "_source": "per_room_directive",
            },
        ))
        seen_pairs.add(canonical)

    return out


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
    #
    # F.4: empty-string forward/reverse is *not* counted as a direction.
    # That's a separate validation error (handled by check #4 above as
    # "invalid forward/reverse direction"). Including empties here would
    # produce spurious collision errors when an unpaired per-room exit
    # leaves a destination with N exits all claiming direction='' — the
    # underlying issue is each unpaired exit, not a multi-claimant collision.
    room_outgoing: dict[int, dict[str, list[str]]] = {}
    for ex in exits:
        if ex.from_id in rooms:
            fwd = ex.forward.split()[0].lower() if ex.forward else ""
            if fwd:
                room_outgoing.setdefault(ex.from_id, {}).setdefault(
                    fwd, []
                ).append(f"to room {ex.to_id}")
        if ex.to_id in rooms:
            rev = ex.reverse.split()[0].lower() if ex.reverse else ""
            if rev:
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
    unresolved: list[str] = []
    rooms, exits = load_planets(manifest, unresolved_report=unresolved)
    report = validate_world(zones, rooms, exits)
    # F.4: dangling per-room exit targets are validation errors. Boot
    # fails on any non-empty unresolved list, but the user sees the full
    # surface area in a single report.
    if unresolved:
        report.errors.extend(unresolved)
    return WorldBundle(
        manifest=manifest,
        zones=zones,
        rooms=rooms,
        exits=exits,
        report=report,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Drop F.6a.1 — Director / Lore Pivot loaders
# ─────────────────────────────────────────────────────────────────────────────
# These three loaders read the era-specific Director / Lore pivot YAMLs:
#
#     data/worlds/<era>/lore.yaml              → load_lore
#     data/worlds/<era>/director_config.yaml   → load_director_config
#     data/worlds/<era>/ambient_events.yaml    → load_ambient_pools
#
# All three return None when the era's manifest does not declare the
# corresponding `content_refs.*` entry. This is intentional — the loaders
# are additive and an era can adopt them piecemeal. The engine refactors
# scheduled for Drops 6a.2 (world_lore.py), 6a.3 (director.py), and 6a.4
# (ambient_events.py) will fall back to legacy hardcoded constants when
# the loader returns None, so callers can opt in safely behind a feature
# flag.
#
# These loaders DO NOT mutate global state, DO NOT seed the database, and
# DO NOT instantiate any engine class. They are pure parse-and-validate.
# Drop 6a.2-4 wire them into the relevant engine init paths.
#
# Per clone_wars_director_lore_pivot_design_v1.md §3 + §5.1.


@dataclass
class LoreEntry:
    """One entry from `<era>/lore.yaml::entries`. Mirrors world_lore SQLite shape.

    Schema:
        title       str           unique entry title
        keywords    str           comma-separated trigger terms (lowercased)
        content     str           the lore text (1-3 paragraphs typical)
        category    str           faction | location | technology | concept |
                                  person | organization
        priority    int           1-10; higher = more prominent in retrieval
        zone_scope  Optional[str] comma-separated zone keys; null = global
    """
    title: str
    keywords: str
    content: str
    category: str
    priority: int
    zone_scope: Optional[str] = None
    raw: dict = field(default_factory=dict)


@dataclass
class LoreCorpus:
    """Result of load_lore — the full parsed lore set for an era.

    `report` collects soft warnings (duplicate titles, empty keywords,
    missing recommended fields). It is informational; callers can ignore
    `.warnings` if they want strict validation, fail boot on `.errors`.
    """
    schema_version: int
    entries: list[LoreEntry]
    report: ValidationReport = field(default_factory=ValidationReport)
    raw: dict = field(default_factory=dict)


@dataclass
class MilestoneEvent:
    """One entry from `director_config.yaml::milestone_events`.

    The CW and GCW eras author this with different optional shapes:
        CW:  id, trigger, cooldown_hours, narrative_priority,
             output_type, flavor_template
        GCW: id, trigger, headline, fires_once,
             narrative_event_type, duration_minutes
    Only `id` and `trigger` are universally required. Everything else
    is optional with a `None` default; the Director's runtime decides
    which fields to consume based on its current era contract. The
    full original mapping is preserved in `raw` so the engine can
    access era-specific fields without going back to YAML.
    """
    id: str
    trigger: dict
    cooldown_hours: Optional[int] = None
    narrative_priority: Optional[str] = None
    output_type: Optional[str] = None
    flavor_template: Optional[str] = None
    headline: Optional[str] = None
    fires_once: Optional[bool] = None
    narrative_event_type: Optional[str] = None
    duration_minutes: Optional[int] = None
    raw: dict = field(default_factory=dict)


@dataclass
class DirectorConfig:
    """Result of load_director_config — the Director's data-fied knobs.

    `valid_factions` and `zone_baselines` map onto the engine's
    VALID_FACTIONS frozenset and DEFAULT_INFLUENCE dict respectively.
    `system_prompt` replaces the multi-line string literal at
    engine/director.py:678-715. Optional features (milestone_events,
    holonet_news_pool, rewicker) default to empty when the era omits
    them — the GCW counterpart YAML, for instance, only authors the
    core fields.
    """
    schema_version: int
    valid_factions: list[str]
    npc_only_factions: list[str]
    influence_min: int
    influence_max: int
    max_delta_per_turn: int
    zone_baselines: dict[str, dict[str, int]]
    system_prompt: str
    milestone_events: list[MilestoneEvent] = field(default_factory=list)
    holonet_news_pool: list[str] = field(default_factory=list)
    rewicker_faction_codes: dict[str, str] = field(default_factory=dict)
    rewicker_zone_keys: dict[str, str] = field(default_factory=dict)
    extras: dict = field(default_factory=dict)  # any unrecognized top-level keys
    report: ValidationReport = field(default_factory=ValidationReport)
    raw: dict = field(default_factory=dict)


@dataclass
class AmbientLine:
    """One entry under `ambient_events.<zone_key>`. `weight` defaults to 1.0."""
    text: str
    weight: float = 1.0
    raw: dict = field(default_factory=dict)


@dataclass
class AmbientPools:
    """Result of load_ambient_pools — per-zone-key list of ambient lines.

    Schema:
        ambient_events:
          <zone_key>:
            - text: "..."
              weight: 0.7   # optional, default 1.0
            - text: "..."

    Zone keys can be specific (e.g. `coruscant_senate`) or generic
    (e.g. `cantina`). Drop 6a.4's merge logic decides which key wins
    when both are defined; this loader simply preserves the era's
    declarations.
    """
    schema_version: int
    pools: dict[str, list[AmbientLine]]
    report: ValidationReport = field(default_factory=ValidationReport)
    raw: dict = field(default_factory=dict)


# ── Lore loader ──────────────────────────────────────────────────────────────


_VALID_LORE_CATEGORIES = frozenset({
    "faction", "location", "technology", "concept",
    "person", "organization",
})


def load_lore(manifest: EraManifest) -> Optional[LoreCorpus]:
    """Parse the era's lore.yaml into a LoreCorpus.

    Returns None when the manifest does not declare a `lore` content_ref.
    Raises WorldLoadError when the file is declared but missing/malformed.

    Soft warnings (duplicate titles, unknown category, empty keywords)
    are collected into corpus.report.warnings. Hard errors (missing
    required field on an entry) are collected into corpus.report.errors.
    """
    path = manifest.lore_path
    if path is None:
        return None
    if not path.is_file():
        raise WorldLoadError(f"Missing lore file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}."
        )

    schema_version = int(raw.get("schema_version", 1))
    entries_raw = raw.get("entries") or []
    if not isinstance(entries_raw, list):
        raise WorldLoadError(
            f"{path}: 'entries' must be a list, got {type(entries_raw).__name__}."
        )

    entries: list[LoreEntry] = []
    seen_titles: set[str] = set()
    report = ValidationReport()

    for i, e in enumerate(entries_raw):
        if not isinstance(e, dict):
            report.errors.append(
                f"{path}: entries[{i}] must be a mapping, got {type(e).__name__}."
            )
            continue

        title = e.get("title")
        if not title or not isinstance(title, str):
            report.errors.append(f"{path}: entries[{i}] missing required 'title'.")
            continue

        keywords = e.get("keywords") or ""
        if not isinstance(keywords, str):
            report.errors.append(
                f"{path}: entries[{i}] '{title}': 'keywords' must be a string."
            )
            continue
        if not keywords.strip():
            report.warnings.append(
                f"{path}: entries[{i}] '{title}': empty keywords — entry will only "
                f"trigger on title-exact match."
            )

        content = e.get("content") or ""
        if not isinstance(content, str) or not content.strip():
            report.errors.append(
                f"{path}: entries[{i}] '{title}': 'content' must be a non-empty string."
            )
            continue

        # Category is an open vocabulary — the GCW lore corpus uses
        # `history`, `item`, `npc` alongside the documented set. Warn
        # only when it's empty/missing; otherwise accept whatever the
        # author wrote.
        category = e.get("category") or ""
        if not category:
            report.warnings.append(
                f"{path}: entries[{i}] '{title}': missing 'category'."
            )

        priority_raw = e.get("priority", 5)
        try:
            priority = int(priority_raw)
        except (TypeError, ValueError):
            report.errors.append(
                f"{path}: entries[{i}] '{title}': 'priority' must be an int, "
                f"got {priority_raw!r}."
            )
            continue
        if not (1 <= priority <= 10):
            report.warnings.append(
                f"{path}: entries[{i}] '{title}': priority {priority} outside 1-10 range."
            )

        zone_scope = e.get("zone_scope")
        if zone_scope is not None and not isinstance(zone_scope, str):
            report.errors.append(
                f"{path}: entries[{i}] '{title}': 'zone_scope' must be a string or null, "
                f"got {type(zone_scope).__name__}."
            )
            continue

        if title in seen_titles:
            report.warnings.append(
                f"{path}: duplicate title {title!r} (entries[{i}])."
            )
        seen_titles.add(title)

        entries.append(LoreEntry(
            title=title,
            keywords=keywords,
            content=content.strip(),
            category=category,
            priority=priority,
            zone_scope=zone_scope,
            raw=e,
        ))

    return LoreCorpus(
        schema_version=schema_version,
        entries=entries,
        report=report,
        raw=raw,
    )


# ── Director config loader ───────────────────────────────────────────────────


_VALID_NARRATIVE_PRIORITIES = frozenset({"low", "medium", "high"})


def load_director_config(manifest: EraManifest) -> Optional[DirectorConfig]:
    """Parse the era's director_config.yaml into a DirectorConfig.

    Returns None when the manifest does not declare a `director_config`
    content_ref. Raises WorldLoadError when the file is declared but
    missing/malformed, or when a structurally required field is absent
    (valid_factions, zone_baselines, system_prompt are required; all
    other top-level fields are optional).
    """
    path = manifest.director_config_path
    if path is None:
        return None
    if not path.is_file():
        raise WorldLoadError(f"Missing director_config file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}."
        )

    schema_version = int(raw.get("schema_version", 1))

    # ── Required fields ──────────────────────────────────────────────────
    valid_factions = raw.get("valid_factions")
    if not isinstance(valid_factions, list) or not valid_factions:
        raise WorldLoadError(
            f"{path}: 'valid_factions' is required and must be a non-empty list."
        )
    if not all(isinstance(f, str) for f in valid_factions):
        raise WorldLoadError(
            f"{path}: 'valid_factions' must contain only strings."
        )

    zone_baselines_raw = raw.get("zone_baselines")
    if not isinstance(zone_baselines_raw, dict):
        raise WorldLoadError(
            f"{path}: 'zone_baselines' is required and must be a mapping "
            f"(zone_key → {{faction: int, ...}})."
        )

    system_prompt = raw.get("system_prompt")
    if not isinstance(system_prompt, str) or not system_prompt.strip():
        raise WorldLoadError(
            f"{path}: 'system_prompt' is required and must be a non-empty string."
        )

    # ── Optional fields with defaults ───────────────────────────────────
    npc_only_factions = raw.get("npc_only_factions") or []
    if not isinstance(npc_only_factions, list):
        raise WorldLoadError(
            f"{path}: 'npc_only_factions' must be a list."
        )

    influence_min = int(raw.get("influence_min", 0))
    influence_max = int(raw.get("influence_max", 100))
    if influence_min >= influence_max:
        raise WorldLoadError(
            f"{path}: influence_min ({influence_min}) must be < "
            f"influence_max ({influence_max})."
        )

    max_delta_per_turn = int(raw.get("max_delta_per_turn", 5))
    if max_delta_per_turn < 1:
        raise WorldLoadError(
            f"{path}: max_delta_per_turn must be >= 1, got {max_delta_per_turn}."
        )

    # ── Zone baselines: validate per-zone shape ─────────────────────────
    report = ValidationReport()
    zone_baselines: dict[str, dict[str, int]] = {}
    valid_set = set(valid_factions)
    for zk, zd in zone_baselines_raw.items():
        if not isinstance(zd, dict):
            report.errors.append(
                f"{path}: zone_baselines[{zk!r}] must be a mapping, got "
                f"{type(zd).__name__}."
            )
            continue
        clean: dict[str, int] = {}
        for fk, fv in zd.items():
            try:
                fv_int = int(fv)
            except (TypeError, ValueError):
                report.errors.append(
                    f"{path}: zone_baselines[{zk!r}][{fk!r}] must be an int, "
                    f"got {fv!r}."
                )
                continue
            if not (influence_min <= fv_int <= influence_max):
                report.warnings.append(
                    f"{path}: zone_baselines[{zk!r}][{fk!r}] = {fv_int} outside "
                    f"[{influence_min}, {influence_max}]."
                )
            if fk not in valid_set:
                report.warnings.append(
                    f"{path}: zone_baselines[{zk!r}] mentions unknown faction "
                    f"{fk!r} (not in valid_factions)."
                )
            clean[fk] = fv_int
        zone_baselines[zk] = clean

    # ── Milestone events ────────────────────────────────────────────────
    # Per CW/GCW shape divergence (CW uses cooldown_hours/output_type/
    # flavor_template; GCW uses headline/fires_once/narrative_event_type/
    # duration_minutes), only `id` and `trigger` are universally
    # required. Everything else is optional and validated only when
    # present. The full original mapping is preserved in `raw` so the
    # Director engine can read era-specific fields directly.
    milestone_events: list[MilestoneEvent] = []
    me_raw = raw.get("milestone_events") or []
    if not isinstance(me_raw, list):
        raise WorldLoadError(
            f"{path}: 'milestone_events' must be a list."
        )
    seen_ids: set[str] = set()
    for i, m in enumerate(me_raw):
        if not isinstance(m, dict):
            report.errors.append(
                f"{path}: milestone_events[{i}] must be a mapping."
            )
            continue
        mid = m.get("id")
        if not mid or not isinstance(mid, str):
            report.errors.append(
                f"{path}: milestone_events[{i}] missing required 'id'."
            )
            continue
        if mid in seen_ids:
            report.warnings.append(
                f"{path}: duplicate milestone id {mid!r}."
            )
        seen_ids.add(mid)

        trigger = m.get("trigger") or {}
        if not isinstance(trigger, dict):
            report.errors.append(
                f"{path}: milestone_events[{i}] '{mid}': 'trigger' must be a mapping."
            )
            continue

        # Optional fields — validate type only when present.
        cooldown: Optional[int] = None
        if "cooldown_hours" in m:
            try:
                cooldown = int(m["cooldown_hours"])
            except (TypeError, ValueError):
                report.errors.append(
                    f"{path}: milestone_events[{i}] '{mid}': cooldown_hours must "
                    f"be int, got {m['cooldown_hours']!r}."
                )
                continue
            if cooldown < 0:
                report.errors.append(
                    f"{path}: milestone_events[{i}] '{mid}': cooldown_hours must "
                    f"be >= 0, got {cooldown}."
                )
                continue

        narrative_priority: Optional[str] = m.get("narrative_priority")
        if narrative_priority is not None and \
                narrative_priority not in _VALID_NARRATIVE_PRIORITIES:
            report.warnings.append(
                f"{path}: milestone_events[{i}] '{mid}': unknown narrative_priority "
                f"{narrative_priority!r}."
            )

        output_type: Optional[str] = m.get("output_type")
        if output_type is not None and not isinstance(output_type, str):
            report.errors.append(
                f"{path}: milestone_events[{i}] '{mid}': output_type must be a string."
            )
            continue

        flavor: Optional[str] = m.get("flavor_template")
        if flavor is not None:
            if not isinstance(flavor, str) or not flavor.strip():
                report.errors.append(
                    f"{path}: milestone_events[{i}] '{mid}': flavor_template, "
                    f"when set, must be a non-empty string."
                )
                continue
            flavor = flavor.strip()

        # GCW-shape fields. Validate type only when present.
        headline: Optional[str] = m.get("headline")
        if headline is not None and not isinstance(headline, str):
            report.errors.append(
                f"{path}: milestone_events[{i}] '{mid}': headline must be a string."
            )
            continue

        fires_once: Optional[bool] = m.get("fires_once")
        if fires_once is not None and not isinstance(fires_once, bool):
            report.errors.append(
                f"{path}: milestone_events[{i}] '{mid}': fires_once must be a bool."
            )
            continue

        narrative_event_type: Optional[str] = m.get("narrative_event_type")
        if narrative_event_type is not None and \
                not isinstance(narrative_event_type, str):
            report.errors.append(
                f"{path}: milestone_events[{i}] '{mid}': narrative_event_type "
                f"must be a string."
            )
            continue

        duration_minutes: Optional[int] = None
        if "duration_minutes" in m:
            try:
                duration_minutes = int(m["duration_minutes"])
            except (TypeError, ValueError):
                report.errors.append(
                    f"{path}: milestone_events[{i}] '{mid}': duration_minutes "
                    f"must be int, got {m['duration_minutes']!r}."
                )
                continue

        milestone_events.append(MilestoneEvent(
            id=mid,
            trigger=trigger,
            cooldown_hours=cooldown,
            narrative_priority=narrative_priority,
            output_type=output_type,
            flavor_template=flavor,
            headline=headline,
            fires_once=fires_once,
            narrative_event_type=narrative_event_type,
            duration_minutes=duration_minutes,
            raw=m,
        ))

    # ── Holonet news pool ───────────────────────────────────────────────
    holonet_pool = raw.get("holonet_news_pool") or []
    if not isinstance(holonet_pool, list):
        raise WorldLoadError(
            f"{path}: 'holonet_news_pool' must be a list of strings."
        )
    if not all(isinstance(s, str) for s in holonet_pool):
        raise WorldLoadError(
            f"{path}: 'holonet_news_pool' entries must be strings."
        )

    # ── Rewicker ────────────────────────────────────────────────────────
    rew = raw.get("rewicker") or {}
    if not isinstance(rew, dict):
        raise WorldLoadError(f"{path}: 'rewicker' must be a mapping.")
    rew_factions = rew.get("faction_codes") or {}
    rew_zones = rew.get("zone_keys") or {}
    if not isinstance(rew_factions, dict) or not isinstance(rew_zones, dict):
        raise WorldLoadError(
            f"{path}: rewicker.faction_codes and rewicker.zone_keys must be mappings."
        )

    # Capture any unrecognized top-level keys for forward compatibility,
    # so future authors can extend the schema without breaking the loader.
    KNOWN_KEYS = {
        "schema_version", "valid_factions", "npc_only_factions",
        "influence_min", "influence_max", "max_delta_per_turn",
        "zone_baselines", "system_prompt",
        "milestone_events", "holonet_news_pool", "rewicker",
    }
    extras = {k: v for k, v in raw.items() if k not in KNOWN_KEYS}

    return DirectorConfig(
        schema_version=schema_version,
        valid_factions=list(valid_factions),
        npc_only_factions=list(npc_only_factions),
        influence_min=influence_min,
        influence_max=influence_max,
        max_delta_per_turn=max_delta_per_turn,
        zone_baselines=zone_baselines,
        system_prompt=system_prompt.strip(),
        milestone_events=milestone_events,
        holonet_news_pool=list(holonet_pool),
        rewicker_faction_codes=dict(rew_factions),
        rewicker_zone_keys=dict(rew_zones),
        extras=extras,
        report=report,
        raw=raw,
    )


# ── Ambient pools loader ─────────────────────────────────────────────────────


def load_ambient_pools(manifest: EraManifest) -> Optional[AmbientPools]:
    """Parse the era's ambient_events.yaml into an AmbientPools.

    Returns None when the manifest does not declare an `ambient_events`
    content_ref. Raises WorldLoadError when the file is declared but
    missing/malformed.

    The schema is forgiving: a zone-key entry can be a list of strings
    OR a list of {text, weight?} mappings. Strings are coerced to
    AmbientLine(text=..., weight=1.0). Per-line weight is optional and
    defaults to 1.0; non-positive weights produce warnings.
    """
    path = manifest.ambient_events_path
    if path is None:
        return None
    if not path.is_file():
        raise WorldLoadError(f"Missing ambient_events file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}."
        )

    schema_version = int(raw.get("schema_version", 1))

    pools_raw = raw.get("ambient_events")
    if not isinstance(pools_raw, dict):
        raise WorldLoadError(
            f"{path}: 'ambient_events' is required and must be a mapping "
            f"(zone_key → list of lines)."
        )

    report = ValidationReport()
    pools: dict[str, list[AmbientLine]] = {}

    for zk, lines_raw in pools_raw.items():
        if not isinstance(lines_raw, list):
            report.errors.append(
                f"{path}: ambient_events[{zk!r}] must be a list, got "
                f"{type(lines_raw).__name__}."
            )
            continue
        lines: list[AmbientLine] = []
        for i, ln in enumerate(lines_raw):
            if isinstance(ln, str):
                lines.append(AmbientLine(text=ln, weight=1.0, raw={"text": ln}))
                continue
            if not isinstance(ln, dict):
                report.errors.append(
                    f"{path}: ambient_events[{zk!r}][{i}] must be a string or "
                    f"mapping, got {type(ln).__name__}."
                )
                continue
            text = ln.get("text") or ""
            if not isinstance(text, str) or not text.strip():
                report.errors.append(
                    f"{path}: ambient_events[{zk!r}][{i}] missing 'text'."
                )
                continue
            try:
                weight = float(ln.get("weight", 1.0))
            except (TypeError, ValueError):
                report.errors.append(
                    f"{path}: ambient_events[{zk!r}][{i}] 'weight' must be a number, "
                    f"got {ln.get('weight')!r}."
                )
                continue
            if weight <= 0:
                report.warnings.append(
                    f"{path}: ambient_events[{zk!r}][{i}] weight {weight} <= 0; "
                    f"line will never trigger."
                )
            lines.append(AmbientLine(text=text.strip(), weight=weight, raw=ln))
        if not lines:
            report.warnings.append(
                f"{path}: ambient_events[{zk!r}] resolved to zero usable lines."
            )
        pools[zk] = lines

    return AmbientPools(
        schema_version=schema_version,
        pools=pools,
        report=report,
        raw=raw,
    )


# ── F.5a.1 (Apr 29 2026) — Housing lots loader ───────────────────────────────
# Per cw_housing_design_v1.md §11 (the housing_lots.yaml schema). This drop
# ships only the Tier 2 faction-quarter mappings (the data bound to F.5b's
# eventual `FACTION_QUARTER_TIERS` data-fy refactor). T1/T3/T4/T5 lot
# inventories come in F.5a.2; the loader tolerates their absence.

@dataclass
class FactionQuarterTier:
    """One rank-tier within a faction's quarter ladder.

    `rank_min` is the minimum rank at which this tier becomes active.
    Engine consumers walk tiers in descending `rank_min` order and pick
    the highest qualifying one. Same semantics as the
    (faction_code, rank) -> cfg dict in `engine/housing.py::FACTION_QUARTER_TIERS`
    that this YAML mirrors.
    """
    rank_min: int
    label: str
    storage_max: int
    room_name: str
    room_desc: str


@dataclass
class FactionQuartersConfig:
    """Tier ladder for one faction's quarter assignments.

    `tiers` is a list of FactionQuarterTier ordered by `rank_min` ascending.
    A faction with no quarters by design (BHG in CW) is represented by
    `tiers=[]` plus the YAML's `null` value for the faction key (the
    parsing layer maps `null` → `FactionQuartersConfig(tiers=[])`).
    """
    tiers: list = field(default_factory=list)


# ── F.5a.2 (Apr 29 2026) — Lot inventory dataclasses ─────────────────────────
# Per cw_housing_design_v1.md §11. F.5a.2 extends the loader to parse the
# remaining four sections of housing_lots.yaml: tier1_rentals (T1 rental
# host buildings), tier3_lots (private residence host rooms), tier4_lots
# (shopfront host rooms), tier5_lots (organization HQ host rooms). Each
# section is optional and may be omitted or empty in the YAML.
#
# These four dataclasses mirror the §11 schema. F.5a.3 will populate the
# YAMLs with actual lot inventories (~46 lots across CW + GCW parity).

@dataclass
class Tier1RentalHost:
    """A T1 rental host building. Per cw_housing_design_v1.md §6.

    A T1 host is a building (cantina back room, hotel, station rentable
    bunkroom) operated by an NPC clerk. `slots` is the number of
    parallel rentals the building offers; `weekly_rent_base` is the
    per-week credit cost before security-tier discount.

    F.5b.3.b (Apr 30 2026) added `display_label` and `security_override`
    as optional overrides for the provider's auto-derived label/security.
    The legacy GCW lots had hand-authored labels (e.g. "Spaceport
    Hotel") and securities ("secured") that don't match the auto-derived
    values; these fields preserve that authoring while keeping the
    underlying slug-based addressing.
    """
    id: str
    planet: str
    zone: str
    host_room: str         # slug — resolved to room ID at boot time
    npc: str               # rental clerk NPC slug
    slots: int
    weekly_rent_base: int
    description_theme: str = ""
    max_stay_weeks: Optional[int] = None  # Kamino transient cap (§6 note)
    display_label: Optional[str] = None      # F.5b.3.b override
    security_override: Optional[str] = None  # F.5b.3.b override


@dataclass
class Tier3Lot:
    """A T3 private-residence host room. Per cw_housing_design_v1.md §7.

    A T3 lot is a host room that can hold up to `max_homes` purchased
    private residences. `allowed_types` enumerates which house tiers
    (studio/standard/deluxe) the lot supports. `rep_gate` is optional
    and locks the lot behind a faction reputation threshold (§7.1 Kuat
    rep-gated lots; §13.1 engine filter).

    F.5b.3.b (Apr 30 2026): `display_label` and `security_override`
    are optional fields for preserving legacy GCW hand-authored labels
    and securities (see Tier1RentalHost docstring).
    """
    id: str
    planet: str
    zone: str
    host_room: str
    max_homes: int
    allowed_types: list = field(default_factory=list)
    description_theme: str = ""
    rep_gate: Optional[dict] = None  # {"faction": str, "min_value": int}
    display_label: Optional[str] = None      # F.5b.3.b override
    security_override: Optional[str] = None  # F.5b.3.b override


@dataclass
class Tier4Lot:
    """A T4 shopfront host room. Per cw_housing_design_v1.md §8.

    A T4 lot is a public-shop-room + private-residence combo. The
    invariant from §3 forbids T4 in lawless zones — the loader does
    NOT enforce this (zone security tier is not part of housing data);
    enforcement lives at lot-author-time and at runtime in
    engine/housing.py.

    F.5b.3.b (Apr 30 2026): `display_label` and `security_override`
    are optional fields for preserving legacy GCW hand-authored labels
    and securities.
    """
    id: str
    planet: str
    zone: str
    host_room: str
    max_homes: int
    allowed_types: list = field(default_factory=list)
    description_theme: str = ""
    market_search_priority: int = 0  # Coco Town Arcade flagship boost (§8)
    display_label: Optional[str] = None      # F.5b.3.b override
    security_override: Optional[str] = None  # F.5b.3.b override


@dataclass
class Tier5Lot:
    """A T5 organization HQ host room. Per cw_housing_design_v1.md §9.

    A T5 lot is an organization headquarters (outpost / chapter_house /
    fortress). `recommended_faction` biases the description templates
    but does not lock out other orgs (§9 — "recommended" not "required").
    `max_homes` defaults to 1 (one HQ per host room) but the schema
    permits >1 for shared compounds.

    F.5b.3.b (Apr 30 2026): `display_label` and `security_override`
    are optional fields for preserving legacy GCW hand-authored labels
    and securities.
    """
    id: str
    planet: str
    zone: str
    host_room: str
    max_homes: int = 1
    allowed_types: list = field(default_factory=list)
    description_theme: str = ""
    recommended_faction: Optional[str] = None
    display_label: Optional[str] = None      # F.5b.3.b override
    security_override: Optional[str] = None  # F.5b.3.b override


@dataclass
class HousingLotsCorpus:
    """Full housing-lot inventory for one era.

    F.5a.1 shipped only `tier2_faction_quarters`. F.5a.2 (this drop)
    extends the corpus with `tier1_rentals`, `tier3_lots`, `tier4_lots`,
    `tier5_lots`. Each is a list (possibly empty) of the matching
    lot-tier dataclass.
    """
    schema_version: int
    era: str
    tier2_faction_quarters: dict  # {faction_code: FactionQuartersConfig}
    report: ValidationReport
    raw: dict = field(default_factory=dict)
    # F.5a.2 additions — default to empty lists for backwards compat.
    tier1_rentals: list = field(default_factory=list)   # list[Tier1RentalHost]
    tier3_lots: list = field(default_factory=list)      # list[Tier3Lot]
    tier4_lots: list = field(default_factory=list)      # list[Tier4Lot]
    tier5_lots: list = field(default_factory=list)      # list[Tier5Lot]


def load_housing_lots(manifest: EraManifest) -> Optional[HousingLotsCorpus]:
    """Parse the era's housing_lots.yaml into a HousingLotsCorpus.

    Returns None when the manifest does not declare a `housing_lots`
    content_ref. Raises WorldLoadError when the file is declared but
    missing/malformed.

    Per F.5a.1 scope, only `tier2_faction_quarters` is parsed. Future
    F.5a.2 will extend this loader to handle `tier1_rentals`,
    `tier3_lots`, `tier4_lots`, `tier5_lots` — each can be empty in
    F.5a.1 YAMLs without warnings.

    Tested by tests/test_f5a1_housing_lots_loader.py.
    """
    path = manifest.housing_lots_path
    if path is None:
        return None
    if not path.is_file():
        raise WorldLoadError(f"Missing housing_lots file: {path}")

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, "
            f"got {type(raw).__name__}."
        )

    schema_version = int(raw.get("schema_version", 1))
    era = raw.get("era") or ""
    report = ValidationReport()

    fq_raw = raw.get("tier2_faction_quarters") or {}
    if not isinstance(fq_raw, dict):
        report.errors.append(
            f"{path}: 'tier2_faction_quarters' must be a mapping, "
            f"got {type(fq_raw).__name__}."
        )
        fq_raw = {}

    tier2_faction_quarters: dict = {}
    for fc, fcfg in fq_raw.items():
        if fcfg is None:
            # Faction explicitly declares no quarters (BHG in CW).
            tier2_faction_quarters[fc] = FactionQuartersConfig(tiers=[])
            continue

        if not isinstance(fcfg, dict):
            report.errors.append(
                f"{path}: tier2_faction_quarters[{fc!r}] must be "
                f"a mapping or null, got {type(fcfg).__name__}."
            )
            continue

        tiers_raw = fcfg.get("tiers") or []
        if not isinstance(tiers_raw, list):
            report.errors.append(
                f"{path}: tier2_faction_quarters[{fc!r}].tiers must "
                f"be a list, got {type(tiers_raw).__name__}."
            )
            continue

        tiers: list = []
        seen_ranks: set = set()
        for i, t in enumerate(tiers_raw):
            if not isinstance(t, dict):
                report.errors.append(
                    f"{path}: tier2_faction_quarters[{fc!r}].tiers[{i}] "
                    f"must be a mapping, got {type(t).__name__}."
                )
                continue

            # Required fields
            missing = [k for k in ("rank_min", "label", "storage_max",
                                    "room_name", "room_desc")
                       if t.get(k) is None]
            if missing:
                report.errors.append(
                    f"{path}: tier2_faction_quarters[{fc!r}].tiers[{i}] "
                    f"missing required field(s): {missing}."
                )
                continue

            rank_min = t["rank_min"]
            if not isinstance(rank_min, int) or rank_min < 0:
                report.errors.append(
                    f"{path}: tier2_faction_quarters[{fc!r}].tiers[{i}] "
                    f"rank_min must be non-negative int, got {rank_min!r}."
                )
                continue

            if rank_min in seen_ranks:
                report.warnings.append(
                    f"{path}: tier2_faction_quarters[{fc!r}] has duplicate "
                    f"rank_min={rank_min}; later entry wins."
                )
            seen_ranks.add(rank_min)

            storage_max = t["storage_max"]
            if not isinstance(storage_max, int) or storage_max < 0:
                report.errors.append(
                    f"{path}: tier2_faction_quarters[{fc!r}].tiers[{i}] "
                    f"storage_max must be non-negative int, got "
                    f"{storage_max!r}."
                )
                continue

            tiers.append(FactionQuarterTier(
                rank_min=rank_min,
                label=str(t["label"]),
                storage_max=storage_max,
                room_name=str(t["room_name"]),
                room_desc=str(t["room_desc"]),
            ))

        tiers.sort(key=lambda x: x.rank_min)
        tier2_faction_quarters[fc] = FactionQuartersConfig(tiers=tiers)

    # ── F.5a.2 — Parse T1/T3/T4/T5 lot inventories ──────────────────────
    # Each section is optional (may be omitted entirely) and may be empty.
    # Validation rules (per cw_housing_design_v1.md §11 schema):
    #   - Required string fields: id, planet, zone, host_room
    #   - Required ints: slots/max_homes, weekly_rent_base (T1 only) — non-negative
    #   - allowed_types must be a list of strings (when present)
    #   - rep_gate (T3 only) must be {"faction": str, "min_value": int}
    #   - id values must be unique within their tier section
    # Records that fail validation are skipped with an error in `report.errors`;
    # the loader still returns a corpus so consumers see partial data + errors.

    tier1_rentals: list = _parse_tier1_rentals(
        raw.get("tier1_rentals") or [], path, report
    )
    tier3_lots: list = _parse_tier3_lots(
        raw.get("tier3_lots") or [], path, report
    )
    tier4_lots: list = _parse_tier4_lots(
        raw.get("tier4_lots") or [], path, report
    )
    tier5_lots: list = _parse_tier5_lots(
        raw.get("tier5_lots") or [], path, report
    )

    return HousingLotsCorpus(
        schema_version=schema_version,
        era=era,
        tier2_faction_quarters=tier2_faction_quarters,
        report=report,
        raw=raw,
        tier1_rentals=tier1_rentals,
        tier3_lots=tier3_lots,
        tier4_lots=tier4_lots,
        tier5_lots=tier5_lots,
    )


# ── F.5a.2 — Lot-section parsers ─────────────────────────────────────────────
# Helpers split out for testability and to keep load_housing_lots readable.
# Each parser is defensive: it appends an error to `report` and skips the
# bad record rather than raising. The exception is when the section itself
# isn't a list — that's a structural error, recorded once, then the section
# is treated as empty.

def _validate_lot_common(rec, idx: int, section: str, path,
                         report: ValidationReport,
                         seen_ids: set) -> Optional[dict]:
    """Common validation for any lot record. Returns the record dict if
    it passes basic shape checks, or None if it should be skipped.

    Checks:
      - record is a mapping
      - required string fields (id, planet, zone, host_room) are present
        and non-empty strings
      - id is unique within section
    """
    if not isinstance(rec, dict):
        report.errors.append(
            f"{path}: {section}[{idx}] must be a mapping, "
            f"got {type(rec).__name__}."
        )
        return None

    for key in ("id", "planet", "zone", "host_room"):
        v = rec.get(key)
        if not isinstance(v, str) or not v.strip():
            report.errors.append(
                f"{path}: {section}[{idx}] field {key!r} must be a "
                f"non-empty string, got {v!r}."
            )
            return None

    rid = rec["id"]
    if rid in seen_ids:
        report.errors.append(
            f"{path}: {section} has duplicate id {rid!r}."
        )
        return None
    seen_ids.add(rid)
    return rec


def _validate_allowed_types(rec, idx: int, section: str, path,
                            report: ValidationReport) -> Optional[list]:
    """Validate the optional `allowed_types` field. Returns the list
    (possibly empty) on success, or None on a hard error."""
    raw_types = rec.get("allowed_types")
    if raw_types is None:
        return []
    if not isinstance(raw_types, list):
        report.errors.append(
            f"{path}: {section}[{idx}] field 'allowed_types' must be a "
            f"list, got {type(raw_types).__name__}."
        )
        return None
    out: list = []
    for j, item in enumerate(raw_types):
        if not isinstance(item, str) or not item.strip():
            report.errors.append(
                f"{path}: {section}[{idx}].allowed_types[{j}] must be a "
                f"non-empty string, got {item!r}."
            )
            return None
        out.append(item)
    return out


def _parse_tier1_rentals(raw_list, path, report: ValidationReport) -> list:
    """Parse the tier1_rentals section. Returns list[Tier1RentalHost]."""
    if not isinstance(raw_list, list):
        report.errors.append(
            f"{path}: 'tier1_rentals' must be a list, "
            f"got {type(raw_list).__name__}."
        )
        return []

    out: list = []
    seen_ids: set = set()
    for idx, rec in enumerate(raw_list):
        rec = _validate_lot_common(rec, idx, "tier1_rentals", path,
                                    report, seen_ids)
        if rec is None:
            continue

        # T1-specific required fields
        npc = rec.get("npc")
        if not isinstance(npc, str) or not npc.strip():
            report.errors.append(
                f"{path}: tier1_rentals[{idx}] field 'npc' must be a "
                f"non-empty string, got {npc!r}."
            )
            continue

        slots = rec.get("slots")
        if not isinstance(slots, int) or isinstance(slots, bool) or slots < 0:
            report.errors.append(
                f"{path}: tier1_rentals[{idx}] field 'slots' must be a "
                f"non-negative int, got {slots!r}."
            )
            continue

        rent = rec.get("weekly_rent_base")
        if not isinstance(rent, int) or isinstance(rent, bool) or rent < 0:
            report.errors.append(
                f"{path}: tier1_rentals[{idx}] field 'weekly_rent_base' "
                f"must be a non-negative int, got {rent!r}."
            )
            continue

        max_stay = rec.get("max_stay_weeks")
        if max_stay is not None:
            if (not isinstance(max_stay, int) or isinstance(max_stay, bool)
                    or max_stay <= 0):
                report.errors.append(
                    f"{path}: tier1_rentals[{idx}] field 'max_stay_weeks' "
                    f"must be a positive int when present, got {max_stay!r}."
                )
                continue

        # F.5b.3.b: optional override fields
        display_label = _validate_optional_string(
            rec, "display_label", idx, "tier1_rentals", path, report,
        )
        if display_label is False:
            continue
        security_override = _validate_optional_string(
            rec, "security_override", idx, "tier1_rentals", path, report,
            valid_values=_VALID_SECURITY_OVERRIDES,
        )
        if security_override is False:
            continue

        out.append(Tier1RentalHost(
            id=rec["id"],
            planet=rec["planet"],
            zone=rec["zone"],
            host_room=rec["host_room"],
            npc=npc,
            slots=slots,
            weekly_rent_base=rent,
            description_theme=str(rec.get("description_theme") or ""),
            max_stay_weeks=max_stay,
            display_label=display_label,
            security_override=security_override,
        ))
    return out


def _validate_max_homes(rec, idx: int, section: str, path,
                        report: ValidationReport,
                        min_value: int = 1) -> Optional[int]:
    """Validate `max_homes` (T3/T4/T5). Returns the int or None on error."""
    mh = rec.get("max_homes")
    if not isinstance(mh, int) or isinstance(mh, bool) or mh < min_value:
        report.errors.append(
            f"{path}: {section}[{idx}] field 'max_homes' must be an int "
            f">= {min_value}, got {mh!r}."
        )
        return None
    return mh


def _validate_optional_string(rec, key: str, idx: int, section: str, path,
                              report: ValidationReport,
                              valid_values: Optional[set] = None
                              ) -> Optional[str]:
    """Validate an optional string field on a lot record.

    F.5b.3.b (Apr 30 2026): used for `display_label` and
    `security_override`. Returns:
      - the string when present and valid
      - None when absent (the default-derive case in the provider)
      - sentinel `False` (cast: pass through with `is False` check)
        on a hard validation error so the caller can `continue`

    Note: this returns None for both "absent" and "error" cases would
    be ambiguous, so on error we append to report.errors and return
    `False` (the literal); callers check `result is False` to skip.
    """
    v = rec.get(key)
    if v is None:
        return None
    if not isinstance(v, str) or not v.strip():
        report.errors.append(
            f"{path}: {section}[{idx}] field {key!r} must be a non-empty "
            f"string when present, got {v!r}."
        )
        return False  # type: ignore[return-value]
    if valid_values is not None and v not in valid_values:
        report.errors.append(
            f"{path}: {section}[{idx}] field {key!r} must be one of "
            f"{sorted(valid_values)}, got {v!r}."
        )
        return False  # type: ignore[return-value]
    return v


# F.5b.3.b: canonical security values per cw_housing_design_v1.md §4
# and engine/security.py SecurityLevel. These are the only values
# `security_override` may take when present.
_VALID_SECURITY_OVERRIDES = {"secured", "contested", "lawless"}


def _validate_rep_gate(rec, idx: int, path,
                       report: ValidationReport) -> Optional[dict]:
    """Validate the optional T3 `rep_gate` field. Returns:
      - the dict if valid
      - {} when not present
      - None on error
    """
    rg = rec.get("rep_gate")
    if rg is None:
        return {}
    if not isinstance(rg, dict):
        report.errors.append(
            f"{path}: tier3_lots[{idx}].rep_gate must be a mapping, "
            f"got {type(rg).__name__}."
        )
        return None
    faction = rg.get("faction")
    min_value = rg.get("min_value")
    if not isinstance(faction, str) or not faction.strip():
        report.errors.append(
            f"{path}: tier3_lots[{idx}].rep_gate.faction must be a "
            f"non-empty string, got {faction!r}."
        )
        return None
    if (not isinstance(min_value, int) or isinstance(min_value, bool)):
        report.errors.append(
            f"{path}: tier3_lots[{idx}].rep_gate.min_value must be an int, "
            f"got {min_value!r}."
        )
        return None
    return {"faction": faction, "min_value": min_value}


def _parse_tier3_lots(raw_list, path, report: ValidationReport) -> list:
    """Parse the tier3_lots section. Returns list[Tier3Lot]."""
    if not isinstance(raw_list, list):
        report.errors.append(
            f"{path}: 'tier3_lots' must be a list, "
            f"got {type(raw_list).__name__}."
        )
        return []

    out: list = []
    seen_ids: set = set()
    for idx, rec in enumerate(raw_list):
        rec = _validate_lot_common(rec, idx, "tier3_lots", path,
                                    report, seen_ids)
        if rec is None:
            continue

        mh = _validate_max_homes(rec, idx, "tier3_lots", path, report)
        if mh is None:
            continue

        types = _validate_allowed_types(rec, idx, "tier3_lots", path, report)
        if types is None:
            continue

        rep_gate = _validate_rep_gate(rec, idx, path, report)
        if rep_gate is None:
            continue

        # F.5b.3.b: optional override fields
        display_label = _validate_optional_string(
            rec, "display_label", idx, "tier3_lots", path, report,
        )
        if display_label is False:
            continue
        security_override = _validate_optional_string(
            rec, "security_override", idx, "tier3_lots", path, report,
            valid_values=_VALID_SECURITY_OVERRIDES,
        )
        if security_override is False:
            continue

        out.append(Tier3Lot(
            id=rec["id"],
            planet=rec["planet"],
            zone=rec["zone"],
            host_room=rec["host_room"],
            max_homes=mh,
            allowed_types=types,
            description_theme=str(rec.get("description_theme") or ""),
            rep_gate=(rep_gate if rep_gate else None),
            display_label=display_label,
            security_override=security_override,
        ))
    return out


def _parse_tier4_lots(raw_list, path, report: ValidationReport) -> list:
    """Parse the tier4_lots section. Returns list[Tier4Lot]."""
    if not isinstance(raw_list, list):
        report.errors.append(
            f"{path}: 'tier4_lots' must be a list, "
            f"got {type(raw_list).__name__}."
        )
        return []

    out: list = []
    seen_ids: set = set()
    for idx, rec in enumerate(raw_list):
        rec = _validate_lot_common(rec, idx, "tier4_lots", path,
                                    report, seen_ids)
        if rec is None:
            continue

        mh = _validate_max_homes(rec, idx, "tier4_lots", path, report)
        if mh is None:
            continue

        types = _validate_allowed_types(rec, idx, "tier4_lots", path, report)
        if types is None:
            continue

        priority = rec.get("market_search_priority", 0)
        if (not isinstance(priority, int) or isinstance(priority, bool)
                or priority < 0):
            report.errors.append(
                f"{path}: tier4_lots[{idx}] field 'market_search_priority' "
                f"must be a non-negative int when present, got {priority!r}."
            )
            continue

        # F.5b.3.b: optional override fields
        display_label = _validate_optional_string(
            rec, "display_label", idx, "tier4_lots", path, report,
        )
        if display_label is False:
            continue
        security_override = _validate_optional_string(
            rec, "security_override", idx, "tier4_lots", path, report,
            valid_values=_VALID_SECURITY_OVERRIDES,
        )
        if security_override is False:
            continue

        out.append(Tier4Lot(
            id=rec["id"],
            planet=rec["planet"],
            zone=rec["zone"],
            host_room=rec["host_room"],
            max_homes=mh,
            allowed_types=types,
            description_theme=str(rec.get("description_theme") or ""),
            market_search_priority=priority,
            display_label=display_label,
            security_override=security_override,
        ))
    return out


def _parse_tier5_lots(raw_list, path, report: ValidationReport) -> list:
    """Parse the tier5_lots section. Returns list[Tier5Lot]."""
    if not isinstance(raw_list, list):
        report.errors.append(
            f"{path}: 'tier5_lots' must be a list, "
            f"got {type(raw_list).__name__}."
        )
        return []

    out: list = []
    seen_ids: set = set()
    for idx, rec in enumerate(raw_list):
        rec = _validate_lot_common(rec, idx, "tier5_lots", path,
                                    report, seen_ids)
        if rec is None:
            continue

        # T5 max_homes defaults to 1 if absent (per design §9 — one HQ per
        # host room is the norm; >1 is rare-but-permitted).
        if rec.get("max_homes") is None:
            mh = 1
        else:
            mh = _validate_max_homes(rec, idx, "tier5_lots", path, report)
            if mh is None:
                continue

        types = _validate_allowed_types(rec, idx, "tier5_lots", path, report)
        if types is None:
            continue

        rec_faction = rec.get("recommended_faction")
        if rec_faction is not None:
            if not isinstance(rec_faction, str) or not rec_faction.strip():
                report.errors.append(
                    f"{path}: tier5_lots[{idx}] field 'recommended_faction' "
                    f"must be a non-empty string when present, got "
                    f"{rec_faction!r}."
                )
                continue

        # F.5b.3.b: optional override fields
        display_label = _validate_optional_string(
            rec, "display_label", idx, "tier5_lots", path, report,
        )
        if display_label is False:
            continue
        security_override = _validate_optional_string(
            rec, "security_override", idx, "tier5_lots", path, report,
            valid_values=_VALID_SECURITY_OVERRIDES,
        )
        if security_override is False:
            continue

        out.append(Tier5Lot(
            id=rec["id"],
            planet=rec["planet"],
            zone=rec["zone"],
            host_room=rec["host_room"],
            max_homes=mh,
            allowed_types=types,
            description_theme=str(rec.get("description_theme") or ""),
            recommended_faction=rec_faction,
            display_label=display_label,
            security_override=security_override,
        ))
    return out


# ── F.7 (Apr 30 2026) — Chargen templates loader ─────────────────────────────
# Per F.7 design: extract the in-Python TEMPLATES literal at
# engine/creation.py L42–L101 to per-era YAML so each era can author
# its own archetype set. F.7 Phase 1 ships the seam + GCW byte-equivalent
# YAML + CW archetype set + the runtime resolver in engine/creation.py.
# F.7.b Phase 2 retires the legacy in-Python literal once
# byte-equivalence is proven in production.

@dataclass
class ChargenTemplate:
    """One chargen archetype loaded from chargen_templates.yaml.

    Mirrors the in-Python TEMPLATES dict-of-dicts shape at
    engine/creation.py — each template carries a label, a default
    species, an attribute-pool map, and a skill-pool map.

    `key` is the YAML key (e.g. "smuggler", "clone_trooper") the
    chargen wizard uses for selection; `attributes` and `skills` are
    raw dice-pool strings (e.g. "3D+1") that engine consumers parse
    into `engine.dice.DicePool` instances.
    """
    key: str
    label: str
    species: str
    attributes: dict
    skills: dict


@dataclass
class ChargenTemplatesCorpus:
    """Parsed chargen_templates.yaml. Holds an ordered list of
    ChargenTemplate plus a per-corpus report.

    Order is preserved from the YAML mapping (Python 3.7+ dict
    iteration). The chargen wizard relies on this order for the
    numbered template-selection menu (smuggler is option 1 in GCW,
    clone_trooper in CW, etc.).
    """
    schema_version: int
    templates: list  # list[ChargenTemplate]
    report: ValidationReport
    raw: dict = field(default_factory=dict)


def load_chargen_templates(manifest: EraManifest) -> Optional[ChargenTemplatesCorpus]:
    """Load chargen templates for the given era manifest.

    Returns None if the era's content_refs has no `chargen_templates:`
    entry — the consuming seam (engine/chargen_templates_loader.py)
    falls back to the legacy in-Python TEMPLATES literal in that case.

    Raises WorldLoadError on a malformed YAML; the seam catches and
    converts to an ERROR log + empty corpus, matching the F.6a.3
    fail-loud convention.

    Per F.5b.3.c precedent: a missing-but-referenced YAML is content
    debt that should surface immediately, not be masked behind silent
    fallback. The seam logs ERROR and returns an empty corpus when
    `chargen_templates:` is declared in era.yaml but the file is
    missing or unparseable.
    """
    path = manifest.chargen_templates_path
    if path is None:
        return None  # No chargen_templates ref — caller falls back.

    if not path.is_file():
        raise WorldLoadError(
            f"Missing chargen_templates file: {path}. "
            f"era.yaml references it but the file does not exist."
        )

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise WorldLoadError(f"Failed to parse {path}: {e}") from e

    report = ValidationReport()

    if not isinstance(raw, dict):
        raise WorldLoadError(
            f"{path}: top-level must be a mapping, got {type(raw).__name__}."
        )

    schema_version = int(raw.get("schema_version", 1))

    tmpl_block = raw.get("templates")
    if tmpl_block is None:
        report.warnings.append(
            f"{path}: top-level `templates:` key absent or null; "
            f"corpus has zero archetypes."
        )
        return ChargenTemplatesCorpus(
            schema_version=schema_version,
            templates=[],
            report=report,
            raw=raw,
        )

    if not isinstance(tmpl_block, dict):
        raise WorldLoadError(
            f"{path}: `templates:` must be a mapping, "
            f"got {type(tmpl_block).__name__}."
        )

    templates: list = []
    for key, body in tmpl_block.items():
        if not isinstance(body, dict):
            report.errors.append(
                f"{path}: templates[{key!r}] must be a mapping, "
                f"got {type(body).__name__}."
            )
            continue

        label = body.get("label")
        species = body.get("species")
        attributes = body.get("attributes")
        skills = body.get("skills")

        # Per-field validation. Each missing/wrong-shape field is a
        # report.errors entry — the loader keeps going so multiple
        # problems surface in one run.
        if not isinstance(label, str) or not label:
            report.errors.append(
                f"{path}: templates[{key!r}].label must be a non-empty "
                f"string."
            )
            continue
        if not isinstance(species, str) or not species:
            report.errors.append(
                f"{path}: templates[{key!r}].species must be a non-empty "
                f"string."
            )
            continue
        if not isinstance(attributes, dict):
            report.errors.append(
                f"{path}: templates[{key!r}].attributes must be a "
                f"mapping, got {type(attributes).__name__}."
            )
            continue
        if not isinstance(skills, dict):
            report.errors.append(
                f"{path}: templates[{key!r}].skills must be a mapping, "
                f"got {type(skills).__name__}."
            )
            continue

        # Shape-check the attribute/skill pool values are dice strings.
        # Don't try to parse them here — that's the consumer's job; the
        # loader only validates "this is a string the consumer can try
        # to parse."
        attr_ok = all(isinstance(v, str) for v in attributes.values())
        skill_ok = all(isinstance(v, str) for v in skills.values())
        if not attr_ok:
            report.errors.append(
                f"{path}: templates[{key!r}].attributes values must "
                f"all be dice-pool strings (e.g. \"3D+1\")."
            )
            continue
        if not skill_ok:
            report.errors.append(
                f"{path}: templates[{key!r}].skills values must "
                f"all be dice-pool strings (e.g. \"1D+2\")."
            )
            continue

        templates.append(ChargenTemplate(
            key=str(key),
            label=label,
            species=species,
            attributes=dict(attributes),
            skills=dict(skills),
        ))

    return ChargenTemplatesCorpus(
        schema_version=schema_version,
        templates=templates,
        report=report,
        raw=raw,
    )
