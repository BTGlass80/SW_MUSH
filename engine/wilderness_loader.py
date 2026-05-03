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
  - Encounter pool resolution
  - Hazard severity tuning
  - Edge connections to hand-built rooms (use adjacency between
    landmarks instead, for now)

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
    landmarks: list = []
    seen_ids: set = set()
    seen_coords: set = set()

    for raw in (data.get("landmarks") or []):
        if not isinstance(raw, dict):
            report.errors.append(
                f"Landmark entry is not a mapping: {raw!r}"
            )
            continue

        lid = raw.get("id")
        if not lid:
            report.errors.append(f"Landmark missing 'id': {raw!r}")
            continue
        if lid in seen_ids:
            report.errors.append(f"Duplicate landmark id: {lid!r}")
            continue
        seen_ids.add(lid)

        coords = raw.get("coordinates", [0, 0])
        if not isinstance(coords, (list, tuple)) or len(coords) != 2:
            report.errors.append(
                f"Landmark {lid!r}: coordinates must be [x, y]"
            )
            continue
        x, y = int(coords[0]), int(coords[1])
        if not (0 <= x < grid_width and 0 <= y < grid_height):
            report.errors.append(
                f"Landmark {lid!r}: coordinates ({x}, {y}) out of grid "
                f"bounds ({grid_width}x{grid_height})"
            )
            continue
        if (x, y) in seen_coords:
            report.errors.append(
                f"Landmark {lid!r}: duplicate coordinates ({x}, {y})"
            )
            continue
        seen_coords.add((x, y))

        terrain_name = raw.get("terrain", default_terrain)
        if terrain_name not in terrains:
            report.warnings.append(
                f"Landmark {lid!r}: terrain {terrain_name!r} not defined; "
                f"will use defaults at look time"
            )

        landmarks.append(WildernessLandmark(
            id=lid,
            name=raw.get("name", lid),
            coordinates=(x, y),
            terrain=terrain_name,
            short_desc=raw.get("short_desc", ""),
            description=raw.get("description", ""),
            properties=dict(raw.get("properties") or {}),
            adjacency=list(raw.get("adjacency") or []),
        ))

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
    )

    report.ok = True
    report.region = region
    return report


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
