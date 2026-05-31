# -*- coding: utf-8 -*-
"""
engine/wilderness_loader.py — Wilderness region YAML loader (minimal substrate).

Per wilderness_system_design_v1.md §3 and the v40 §3.5 Village build
prerequisite stack.

This is the **minimal-substrate** loader: it reads a wilderness region
YAML, validates structure, and returns a `WildernessRegion` object
that the writer (engine/wilderness_writer.py) can persist as ordinary
landmark rooms with adjacency exits and `wilderness_region_id`
populated.

What this loader does:
  - Parse the region YAML
  - Validate structural invariants (slug uniqueness, coords in
    range, adjacency references resolve, no two landmarks share
    coords)
  - Merge force-resonant landmark content from
    force_resonant_landmarks.yaml when ids collide (so a region can
    declare a brief description and have the rich force-resonant
    content win at write time)
  - Emit a typed WildernessRegion dataclass

What this loader does NOT do (deferred to wilderness_system_design
Drops 2-7):
  - Coordinate-grid tile generation (no per-tile rooms — only
    landmarks become rooms in this drop)
  - Hazard severity tuning beyond the YAML's terrain-level severity
    integer (use cases beyond extreme_heat / urban_danger map to
    HAZARD_TYPES entries; aspirational tags are inert until the
    matching HAZARD_TYPE ships)
  - Edge connections to hand-built rooms (use adjacency between
    landmarks instead, for now)

What this loader DOES handle (post-minimal-substrate additions):
  - Edges (W.2 phase 2, May 3 2026)
  - Unwalkable tiles (W.2 phase 2, May 3 2026)
  - landmark_includes (W.3, May 24 2026)
  - Encounter pool parsing (T2.WENC, May 24 2026) — see
    engine/wilderness_encounters.py for the selector that consumes
    the parsed pool.

The full coordinate-movement engine is the post-Village roadmap
track. This loader is the bridge.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Optional, Sequence

import yaml

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WildernessTerrain:
    """One terrain definition. Most fields are reserved for the future
    look engine; this drop just stores them faithfully."""
    name: str
    move_cost: int = 1
    sight_radius: int = 1
    ambient_hazard: str = "none"
    hazard_severity: int = 0
    variants: list = field(default_factory=list)
    time_overlays: dict = field(default_factory=dict)
    encounter_bias: list = field(default_factory=list)


@dataclass
class WildernessLandmark:
    """One named landmark within a region. Becomes a room at write time."""
    id: str
    name: str
    coordinates: tuple = (0, 0)
    terrain: str = "default"
    short_desc: str = ""
    description: str = ""
    properties: dict = field(default_factory=dict)
    adjacency: list = field(default_factory=list)
    # Some landmarks (force-resonant ones) carry an ambient_lines pool.
    # Loaded from force_resonant_landmarks.yaml when ids match.
    ambient_lines: list = field(default_factory=list)


@dataclass
class WildernessEdge:
    """A connection between a hand-built room and a wilderness tile.

    Per W.2 phase 2 (May 3 2026): when a player in ``room_slug`` types
    ``direction_from_room``, they enter wilderness at ``coords``.
    When a player at ``coords`` types ``direction_back_to_room``, they
    exit back to ``room_slug``.

    Validated by the loader:
      - room_slug must be a non-empty string
      - coords must be in-bounds for the region
      - direction_from_room and direction_back_to_room must be present
    """
    room_slug: str
    coords: tuple
    direction_from_room: str
    direction_back_to_room: str
    enter_message: str = ""
    exit_message: str = ""


@dataclass
class WildernessRegion:
    """A complete loaded wilderness region."""
    slug: str
    name: str
    planet: str
    zone: str
    default_security: str
    grid_width: int
    grid_height: int
    tile_scale_km: int
    default_terrain: str
    terrains: dict          # name -> WildernessTerrain
    landmarks: list         # WildernessLandmark in YAML order
    narrative_tone_key: str = ""
    schema_version: int = 1
    # ── W.2 phase 2 additions (May 3 2026, post Evennia review) ─────────
    edges: list = field(default_factory=list)         # WildernessEdge
    unwalkable_tiles: dict = field(default_factory=dict)  # (x, y) -> reason
    # ── T2.WENC (May 24 2026) — encounter pool ───────────────────────
    # Region-level encounter configuration. Default-constructed
    # ``EncounterPool`` (base_chance=0, empty entries) is a no-op:
    # regions without ``encounters:`` in their YAML simply don't roll
    # for encounters. See engine/wilderness_encounters.py.
    encounter_pool: object = None  # EncounterPool; None until loader sets it


@dataclass
class WildernessLoadReport:
    ok: bool
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    region: Optional[WildernessRegion] = None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def load_wilderness_region(
    yaml_path: str,
    *,
    force_resonant_path: Optional[str] = None,
) -> WildernessLoadReport:
    """Load and validate a wilderness region YAML file.

    Args:
        yaml_path: absolute path to the region YAML
            (e.g. data/worlds/clone_wars/wilderness/dune_sea.yaml).
        force_resonant_path: optional path to
            force_resonant_landmarks.yaml. If supplied, landmark
            descriptions there override descriptions in this file
            for any matching id (so brief descriptions in the region
            file are upgraded to the rich content in the
            force-resonant file at load time). This keeps the
            authoring source-of-truth in one place per landmark.

    Returns:
        WildernessLoadReport. If ok=False, region is None and errors
        is populated.
    """
    report = WildernessLoadReport(ok=False)

    if not os.path.exists(yaml_path):
        report.errors.append(f"Region YAML not found: {yaml_path}")
        return report

    try:
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        report.errors.append(f"YAML parse error in {yaml_path}: {e}")
        return report

    if not isinstance(data, dict):
        report.errors.append(
            f"Region YAML root is not a mapping: {yaml_path}"
        )
        return report

    schema_version = data.get("schema_version", 1)
    if schema_version != 1:
        report.errors.append(
            f"Unsupported schema_version {schema_version} in {yaml_path}; "
            f"expected 1"
        )
        return report

    # ── Region metadata ──────────────────────────────────────────────────
    region_meta = data.get("region")
    if not isinstance(region_meta, dict):
        report.errors.append("Missing or malformed 'region' block")
        return report

    required_meta = ("slug", "name", "planet", "zone", "default_security")
    for k in required_meta:
        if not region_meta.get(k):
            report.errors.append(f"region.{k} is required")
            return report

    # ── Grid ─────────────────────────────────────────────────────────────
    grid = data.get("grid", {})
    grid_width = int(grid.get("width", 40))
    grid_height = int(grid.get("height", 40))
    tile_scale_km = int(grid.get("tile_scale_km", 2))
    default_terrain = grid.get("default_terrain", "dune")

    if grid_width <= 0 or grid_height <= 0:
        report.errors.append(
            f"grid dimensions must be positive; got {grid_width}x{grid_height}"
        )
        return report
    if grid_width > 200 or grid_height > 200:
        report.warnings.append(
            f"Unusually large grid {grid_width}x{grid_height}; "
            f"the future tile engine may struggle at this size."
        )

    # ── Terrains ─────────────────────────────────────────────────────────
    terrains: dict = {}
    for name, t in (data.get("terrains") or {}).items():
        if not isinstance(t, dict):
            report.warnings.append(
                f"Terrain {name!r} is not a mapping; skipping"
            )
            continue
        terrains[name] = WildernessTerrain(
            name=name,
            move_cost=int(t.get("move_cost", 1)),
            sight_radius=int(t.get("sight_radius", 1)),
            ambient_hazard=t.get("ambient_hazard", "none"),
            hazard_severity=int(t.get("hazard_severity", 0)),
            variants=list(t.get("variants") or []),
            time_overlays=dict(t.get("time_overlays") or {}),
            encounter_bias=list(t.get("encounter_bias") or []),
        )

    if default_terrain not in terrains:
        report.warnings.append(
            f"default_terrain {default_terrain!r} is not defined in terrains; "
            f"the future look engine will fall back to a generic description."
        )

    # ── Landmarks ────────────────────────────────────────────────────────
    # Per W.3 (May 24 2026): landmarks may come from the region YAML's
    # own ``landmarks:`` block AND/OR from one or more include files
    # declared via ``landmark_includes:``. The include files have the
    # same shape (``schema_version`` + ``landmarks:`` + optional
    # ``transit_nodes:`` block which is treated as additional landmarks
    # with the ``transit_node: true`` property already set).
    #
    # Include file paths are resolved relative to the wilderness/
    # directory containing the region YAML. The legacy
    # ``force_resonant_path`` parameter (kept for backward-compat) is
    # also resolved through the same code path as an implicit include
    # at the end of the merge list, but only enriches existing
    # landmarks (matches the pre-W.3 semantics).
    landmarks: list = []
    seen_ids: set = set()
    seen_coords: set = set()

    # First pass: region's own landmarks
    _parse_landmarks_block(
        data.get("landmarks") or [],
        landmarks, seen_ids, seen_coords,
        grid_width, grid_height, default_terrain, terrains,
        report,
        source_label="region YAML",
        is_transit_nodes=False,
    )

    # Second pass: landmark_includes (each file contributes landmarks
    # AND transit_nodes; both are appended to the landmark list, with
    # transit_nodes auto-tagged as ``transit_node: true``).
    region_dir = os.path.dirname(yaml_path)
    includes = data.get("landmark_includes") or []
    if not isinstance(includes, list):
        report.warnings.append(
            f"landmark_includes is not a list; got {type(includes).__name__}; "
            f"ignoring"
        )
        includes = []
    for include_rel in includes:
        if not isinstance(include_rel, str):
            report.warnings.append(
                f"landmark_includes entry not a string: {include_rel!r}; "
                f"skipping"
            )
            continue
        include_path = (
            include_rel
            if os.path.isabs(include_rel)
            else os.path.join(region_dir, include_rel)
        )
        if not os.path.exists(include_path):
            report.errors.append(
                f"landmark_includes file not found: {include_path}"
            )
            continue
        try:
            with open(include_path, "r", encoding="utf-8") as f:
                inc_data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            report.errors.append(
                f"landmark_includes parse failed for {include_path}: {e}"
            )
            continue
        if not isinstance(inc_data, dict):
            report.errors.append(
                f"landmark_includes file root is not a mapping: "
                f"{include_path}"
            )
            continue
        # Parse landmarks
        _parse_landmarks_block(
            inc_data.get("landmarks") or [],
            landmarks, seen_ids, seen_coords,
            grid_width, grid_height, default_terrain, terrains,
            report,
            source_label=f"include {os.path.basename(include_path)}",
            is_transit_nodes=False,
            region_filter=region_meta.get("slug"),
        )
        # Parse transit_nodes (treated as landmarks with transit_node
        # property auto-set). Transit nodes that lack coordinates are
        # skipped with a warning — in the single-level wilderness
        # model, every landmark needs a coordinate to be placed.
        _parse_landmarks_block(
            inc_data.get("transit_nodes") or [],
            landmarks, seen_ids, seen_coords,
            grid_width, grid_height, default_terrain, terrains,
            report,
            source_label=f"include {os.path.basename(include_path)} "
                         f"(transit_nodes)",
            is_transit_nodes=True,
            region_filter=region_meta.get("slug"),
        )

    # ── Adjacency reference validation ───────────────────────────────────
    landmark_ids = {l.id for l in landmarks}
    for lm in landmarks:
        for adj in lm.adjacency:
            if adj not in landmark_ids:
                # Could be an external (hand-built) room slug. We
                # warn but don't fail — the writer reports unresolved
                # adjacencies separately because it has the room-id
                # map.
                report.warnings.append(
                    f"Landmark {lm.id!r}: adjacency {adj!r} not a defined "
                    f"landmark; will be treated as external room slug "
                    f"by the writer."
                )

    if report.errors:
        return report

    # ── Merge force-resonant content ─────────────────────────────────────
    if force_resonant_path:
        _merge_force_resonant_content(landmarks, force_resonant_path, report)

    # ── Parse edges (W.2 phase 2) ────────────────────────────────────────
    edges = _parse_edges(
        data.get("edges") or [],
        grid_width, grid_height, report,
    )

    # ── Parse unwalkable_tiles (W.2 phase 2 / Evennia review) ────────────
    unwalkable_tiles = _parse_unwalkable_tiles(
        data.get("unwalkable_tiles") or [],
        grid_width, grid_height, report,
    )

    # ── Parse encounter pool (T2.WENC, May 24 2026) ──────────────────────
    # Optional ``encounters:`` block per wilderness_system_design_v1.md §5.
    # Absent / empty block yields a no-op EncounterPool — no special
    # case needed at the call site.
    from engine.wilderness_encounters import parse_encounter_pool
    encounter_pool = parse_encounter_pool(
        data.get("encounters") or {},
        terrains=terrains,
        report=report,
    )

    # ── Build region ─────────────────────────────────────────────────────
    region = WildernessRegion(
        slug=region_meta["slug"],
        name=region_meta["name"],
        planet=region_meta["planet"],
        zone=region_meta["zone"],
        default_security=region_meta["default_security"],
        grid_width=grid_width,
        grid_height=grid_height,
        tile_scale_km=tile_scale_km,
        default_terrain=default_terrain,
        terrains=terrains,
        landmarks=landmarks,
        narrative_tone_key=region_meta.get("narrative_tone_key", ""),
        schema_version=schema_version,
        edges=edges,
        unwalkable_tiles=unwalkable_tiles,
        encounter_pool=encounter_pool,
    )

    report.ok = True
    report.region = region
    return report


# ─────────────────────────────────────────────────────────────────────────────
# W.2 phase 2: edge + unwalkable parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse_edges(raw_edges, grid_width, grid_height, report) -> list:
    """Parse YAML `edges:` block into WildernessEdge instances.

    Bad edges produce warnings and are dropped; load succeeds with the
    valid subset rather than failing wholesale.
    """
    edges = []
    for i, raw in enumerate(raw_edges):
        if not isinstance(raw, dict):
            report.warnings.append(f"Edge #{i}: not a dict, skipping")
            continue

        room_slug = (raw.get("room_slug") or "").strip()
        if not room_slug:
            report.warnings.append(f"Edge #{i}: missing room_slug, skipping")
            continue

        coords_raw = raw.get("coords")
        if not (isinstance(coords_raw, (list, tuple)) and len(coords_raw) == 2):
            report.warnings.append(
                f"Edge #{i} ({room_slug!r}): coords must be [x, y], skipping"
            )
            continue

        try:
            x, y = int(coords_raw[0]), int(coords_raw[1])
        except (TypeError, ValueError):
            report.warnings.append(
                f"Edge #{i} ({room_slug!r}): coords not integers, skipping"
            )
            continue

        if not (0 <= x < grid_width and 0 <= y < grid_height):
            report.warnings.append(
                f"Edge #{i} ({room_slug!r}): coords ({x}, {y}) out of bounds, skipping"
            )
            continue

        direction_from = (raw.get("direction_from_room") or "").strip()
        direction_back = (raw.get("direction_back_to_room") or "").strip()
        if not direction_from or not direction_back:
            report.warnings.append(
                f"Edge #{i} ({room_slug!r}): direction_from_room and "
                f"direction_back_to_room are both required, skipping"
            )
            continue

        edges.append(WildernessEdge(
            room_slug=room_slug,
            coords=(x, y),
            direction_from_room=direction_from.lower(),
            direction_back_to_room=direction_back.lower(),
            enter_message=str(raw.get("enter_message") or "").strip(),
            exit_message=str(raw.get("exit_message") or "").strip(),
        ))
    return edges


def _parse_unwalkable_tiles(raw_unwalkable, grid_width, grid_height, report) -> dict:
    """Parse `unwalkable_tiles:` block into a coords→reason dict.

    Supports two entry shapes:
      - {coords: [x, y], reason: "..."}
      - {region_block: {x1, y1, x2, y2}, reason: "..."}
    """
    unwalkable: dict = {}
    for i, raw in enumerate(raw_unwalkable):
        if not isinstance(raw, dict):
            report.warnings.append(f"unwalkable_tiles #{i}: not a dict, skipping")
            continue

        reason = str(raw.get("reason") or "You can't go that way.").strip()

        if "coords" in raw:
            coords_raw = raw["coords"]
            if not (isinstance(coords_raw, (list, tuple)) and len(coords_raw) == 2):
                report.warnings.append(
                    f"unwalkable_tiles #{i}: coords must be [x, y], skipping"
                )
                continue
            try:
                x, y = int(coords_raw[0]), int(coords_raw[1])
            except (TypeError, ValueError):
                report.warnings.append(
                    f"unwalkable_tiles #{i}: coords not integers, skipping"
                )
                continue
            if not (0 <= x < grid_width and 0 <= y < grid_height):
                report.warnings.append(
                    f"unwalkable_tiles #{i}: ({x}, {y}) out of bounds, skipping"
                )
                continue
            unwalkable[(x, y)] = reason

        elif "region_block" in raw:
            blk = raw["region_block"] or {}
            try:
                x1 = int(blk["x1"]); y1 = int(blk["y1"])
                x2 = int(blk["x2"]); y2 = int(blk["y2"])
            except (KeyError, TypeError, ValueError):
                report.warnings.append(
                    f"unwalkable_tiles #{i}: region_block needs x1/y1/x2/y2 ints, skipping"
                )
                continue
            x_lo, x_hi = min(x1, x2), max(x1, x2)
            y_lo, y_hi = min(y1, y2), max(y1, y2)
            for xx in range(x_lo, x_hi + 1):
                for yy in range(y_lo, y_hi + 1):
                    if 0 <= xx < grid_width and 0 <= yy < grid_height:
                        unwalkable[(xx, yy)] = reason
        else:
            report.warnings.append(
                f"unwalkable_tiles #{i}: needs `coords` or `region_block`, skipping"
            )

    return unwalkable


def _parse_landmarks_block(
    raw_entries: list,
    landmarks: list,
    seen_ids: set,
    seen_coords: set,
    grid_width: int,
    grid_height: int,
    default_terrain: str,
    terrains: dict,
    report,
    *,
    source_label: str = "region YAML",
    is_transit_nodes: bool = False,
    region_filter: Optional[str] = None,
) -> None:
    """Parse a list of raw landmark dicts and append to landmarks.

    Per W.3 (May 24 2026): factored out of load_wilderness_region so
    both the region YAML's own ``landmarks:`` block and each
    ``landmark_includes:`` file can be parsed through the same
    validation path.

    Mutates landmarks/seen_ids/seen_coords. Errors append to report.

    Args:
        raw_entries: list of dicts from the YAML ``landmarks:`` or
            ``transit_nodes:`` block.
        landmarks: accumulator list; new WildernessLandmark objects
            appended here.
        seen_ids: id-uniqueness accumulator across all sources.
        seen_coords: (x, y) accumulator across all sources.
        grid_width / grid_height: region bounds for coordinate check.
        default_terrain: name used when a landmark omits ``terrain``.
        terrains: dict of defined terrain names; unknown terrains
            warn but don't fail.
        report: WildernessLoadReport for error/warning collection.
        source_label: human-readable label of the source file, used
            in error messages to disambiguate which include caused
            a duplicate id / coord etc.
        is_transit_nodes: if True, auto-set ``transit_node: true``
            and ``ambient_disabled: true`` on each entry's properties
            unless already declared. Transit-node entries without
            coordinates are skipped with a warning (single-level
            wilderness model requires placement).
        region_filter: if non-None, entries whose ``region:`` field
            does not match are silently skipped. Used when an include
            file (e.g. force_resonant_landmarks.yaml) hosts entries
            for multiple regions — the loader filters to entries
            relevant to the region currently being assembled.
    """
    # Track ids added during THIS call separately from the
    # cross-call seen_ids accumulator. Within a single source (one
    # landmarks: or transit_nodes: block) a duplicate id is a content
    # bug and errors. Across sources (region YAML + include files)
    # a duplicate id is enrichment intent.
    ids_in_this_call: set = set()

    for raw in raw_entries:
        if not isinstance(raw, dict):
            report.errors.append(
                f"[{source_label}] landmark entry is not a mapping: {raw!r}"
            )
            continue

        # ── Region filter (W.3) ────────────────────────────────────
        # Include files may host entries for multiple regions. Skip
        # entries that don't match the region currently being loaded.
        # Entries with no ``region`` field are treated as matching
        # any filter (they're region-agnostic content the region YAML
        # is asking to include).
        if region_filter is not None:
            entry_region = raw.get("region")
            if entry_region is not None and entry_region != region_filter:
                continue

        lid = raw.get("id")
        if not lid:
            report.errors.append(
                f"[{source_label}] landmark missing 'id': {raw!r}"
            )
            continue

        # Within-call duplicate: content-authoring bug, error.
        if lid in ids_in_this_call:
            report.errors.append(
                f"[{source_label}] duplicate landmark id: {lid!r} "
                f"(appears twice in the same source block)"
            )
            continue

        # ── Existing-id enrichment (W.3) ───────────────────────────
        # If this id has already been added by an EARLIER call (region
        # YAML's own block, or an earlier include file), treat the
        # current entry as ENRICHMENT rather than a duplicate-error.
        # Enrichment policy (mirrors the pre-W.3
        # _merge_force_resonant_content behavior):
        #   - description: overrides if non-empty
        #   - short_desc: overrides only if existing is empty
        #   - properties: setdefault per key (existing wins)
        #   - ambient_lines: replaces only if existing list is empty
        #   - coordinates: NOT overridden; the first source wins
        #   - terrain: NOT overridden; the first source wins
        #   - adjacency: extended (deduped)
        if lid in seen_ids:
            existing = next((l for l in landmarks if l.id == lid), None)
            if existing is None:
                # seen_ids contained the id but landmarks doesn't —
                # earlier validation rejected the entry. Don't enrich
                # an orphan id; just skip.
                continue
            if raw.get("description"):
                existing.description = raw["description"]
            if raw.get("short_desc") and not existing.short_desc:
                existing.short_desc = raw["short_desc"]
            for k, v in (raw.get("properties") or {}).items():
                existing.properties.setdefault(k, v)
            ambient_raw = raw.get("ambient_lines") or []
            if ambient_raw and not existing.ambient_lines:
                existing.ambient_lines = [
                    a["text"] if isinstance(a, dict) and "text" in a
                    else str(a)
                    for a in ambient_raw
                ]
            for adj in (raw.get("adjacency") or []):
                if adj not in existing.adjacency:
                    existing.adjacency.append(adj)
            ids_in_this_call.add(lid)
            continue
        if not lid:
            report.errors.append(
                f"[{source_label}] landmark missing 'id': {raw!r}"
            )
            continue

        # Transit nodes may legitimately omit coordinates in legacy
        # multi-level files; in the single-level model they need a
        # placement. Skip with a warning rather than failing the load.
        coords_raw = raw.get("coordinates")
        if coords_raw is None:
            if is_transit_nodes:
                report.warnings.append(
                    f"[{source_label}] transit node {lid!r} has no "
                    f"coordinates; skipping (single-level wilderness "
                    f"model requires placement)"
                )
                continue
            else:
                report.errors.append(
                    f"[{source_label}] landmark {lid!r}: coordinates "
                    f"are required"
                )
                continue

        if not isinstance(coords_raw, (list, tuple)) or len(coords_raw) != 2:
            report.errors.append(
                f"[{source_label}] landmark {lid!r}: coordinates must "
                f"be [x, y]"
            )
            continue
        try:
            x, y = int(coords_raw[0]), int(coords_raw[1])
        except (TypeError, ValueError):
            report.errors.append(
                f"[{source_label}] landmark {lid!r}: coordinates must "
                f"be integers; got {coords_raw!r}"
            )
            continue
        if not (0 <= x < grid_width and 0 <= y < grid_height):
            report.errors.append(
                f"[{source_label}] landmark {lid!r}: coordinates "
                f"({x}, {y}) out of grid bounds "
                f"({grid_width}x{grid_height})"
            )
            continue
        if (x, y) in seen_coords:
            report.errors.append(
                f"[{source_label}] landmark {lid!r}: duplicate "
                f"coordinates ({x}, {y})"
            )
            continue

        terrain_name = raw.get("terrain", default_terrain)
        if terrain_name not in terrains:
            report.warnings.append(
                f"[{source_label}] landmark {lid!r}: terrain "
                f"{terrain_name!r} not defined; will use defaults "
                f"at look time"
            )

        # Properties: copy explicit ones; auto-tag transit nodes.
        props = dict(raw.get("properties") or {})
        if is_transit_nodes:
            props.setdefault("transit_node", True)
            props.setdefault("ambient_disabled", True)
            props.setdefault("wilderness_landmark", False)

        # Ambient lines may be present in include files (the
        # force-resonant-style enrichment block). Accept both
        # ``[{text: "..."}]`` and ``[str]`` forms.
        ambient_raw = raw.get("ambient_lines") or []
        ambient_lines = [
            a["text"] if isinstance(a, dict) and "text" in a else str(a)
            for a in ambient_raw
        ]

        # Only commit the seen-trackers AFTER all validation succeeds,
        # so a malformed entry doesn't accidentally block a later
        # well-formed one from claiming the same id/coords.
        seen_ids.add(lid)
        seen_coords.add((x, y))
        ids_in_this_call.add(lid)

        landmarks.append(WildernessLandmark(
            id=lid,
            name=raw.get("name", lid),
            coordinates=(x, y),
            terrain=terrain_name,
            short_desc=raw.get("short_desc", ""),
            description=raw.get("description", ""),
            properties=props,
            adjacency=list(raw.get("adjacency") or []),
            ambient_lines=ambient_lines,
        ))


def _merge_force_resonant_content(
    landmarks: list,
    force_resonant_path: str,
    report: WildernessLoadReport,
) -> None:
    """Upgrade landmark descriptions/ambient lines from the force-resonant
    content file. Mutates the landmarks list in place. Silently skips
    if the force-resonant file isn't present."""
    if not os.path.exists(force_resonant_path):
        report.warnings.append(
            f"force_resonant_landmarks YAML not found at "
            f"{force_resonant_path}; using region-file descriptions as-is."
        )
        return

    try:
        with open(force_resonant_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        report.warnings.append(
            f"force_resonant_landmarks YAML parse failed: {e}"
        )
        return

    fr_by_id = {
        entry["id"]: entry
        for entry in (data.get("landmarks") or [])
        if isinstance(entry, dict) and entry.get("id")
    }

    merged_count = 0
    for lm in landmarks:
        fr = fr_by_id.get(lm.id)
        if fr is None:
            continue
        # Override description with the richer authored version
        if fr.get("description"):
            lm.description = fr["description"]
        if fr.get("short_desc") and not lm.short_desc:
            lm.short_desc = fr["short_desc"]
        # Merge properties (force-resonant flags add to whatever the
        # region file declared)
        for k, v in (fr.get("properties") or {}).items():
            lm.properties.setdefault(k, v)
        # Pull ambient lines through
        ambient = fr.get("ambient_lines") or []
        if ambient and not lm.ambient_lines:
            lm.ambient_lines = [
                a["text"] if isinstance(a, dict) else str(a)
                for a in ambient
            ]
        merged_count += 1

    if merged_count:
        log.info(
            "[wilderness] merged force-resonant content into %d landmarks",
            merged_count,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Convenience: load all wilderness regions referenced in era.yaml
# ─────────────────────────────────────────────────────────────────────────────

def load_era_wilderness_regions(
    era_dir: str,
) -> list:
    """Read era.yaml.content_refs.wilderness (a list of region YAML
    paths relative to the era dir) and return a list of
    WildernessLoadReport. Empty list if the era declares no
    wilderness content.

    The build script walks this list and feeds successful regions
    to the writer. Failures are logged but do not abort the build —
    a malformed region YAML should not prevent the rest of the
    world from loading.
    """
    era_yaml_path = os.path.join(era_dir, "era.yaml")
    if not os.path.exists(era_yaml_path):
        return []

    try:
        with open(era_yaml_path, "r", encoding="utf-8") as f:
            era_data = yaml.safe_load(f) or {}
    except yaml.YAMLError as e:
        log.warning("[wilderness] era.yaml parse failed: %s", e)
        return []

    refs = (era_data.get("content_refs") or {}).get("wilderness") or []
    if not isinstance(refs, list):
        log.warning(
            "[wilderness] era.yaml content_refs.wilderness is not a list; "
            "got %r", type(refs).__name__,
        )
        return []

    # The force-resonant file is conventionally named and lives in
    # the same wilderness/ subdirectory.
    force_resonant_path = os.path.join(
        era_dir, "wilderness", "force_resonant_landmarks.yaml",
    )

    reports = []
    for ref in refs:
        region_path = os.path.join(era_dir, ref)
        rep = load_wilderness_region(
            region_path,
            force_resonant_path=force_resonant_path,
        )
        reports.append(rep)
        if rep.ok:
            log.info(
                "[wilderness] loaded region %r (%d landmarks)",
                rep.region.slug, len(rep.region.landmarks),
            )
        else:
            log.warning(
                "[wilderness] region load failed (%s): %s",
                region_path, rep.errors,
            )
    return reports
