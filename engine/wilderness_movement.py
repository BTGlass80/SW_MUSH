# -*- coding: utf-8 -*-
"""
engine/wilderness_movement.py — Wilderness coordinate-grid movement (Drop 2, May 3 2026).

Per ``wilderness_system_design_v1.md`` §4.2–§4.4: the engine seam
for movement and rendering inside a wilderness region. Drop 2
ships the pure-function core; live command integration (look,
north/south/etc, coords, landmarks) ships in Drop 2 phase 2 once
the YAML edge format is finalized.

Architecture
============

Two surfaces:

  1. ``move_in_wilderness(region, x, y, direction)`` — pure function.
     Computes destination coordinates, validates bounds, returns
     a structured result. Does NOT touch the DB. The caller (a
     future MoveCommand wilderness branch) writes the result to
     the character row.

  2. ``render_tile(region, x, y, *, time_of_day=None, weather=None)``
     — pure function. Computes the tile description (terrain
     variant, time overlay, ambient flags) deterministically from
     the region YAML and the coordinates. Used by the look command
     when the character is in wilderness.

Both are designed to be testable without a database, mocking, or
async setup. The DB writes happen in the caller; this module is
the deterministic kernel.

Coordinate convention
=====================

  - ``x``: column (0 = westmost, width-1 = eastmost)
  - ``y``: row    (0 = southmost, height-1 = northmost)
  - Cardinals: north = y+1, south = y-1, east = x+1, west = x-1
  - Diagonals: northeast = (x+1, y+1), etc.

Bounds
======

A movement that would leave the region (x' < 0 or x' >= width or
y' < 0 or y' >= height) is REJECTED at this layer. Edge crossings
to hand-built rooms are a separate mechanism (Drop 2 phase 2): the
caller checks edges in the region YAML's ``edges:`` block before
asking ``move_in_wilderness``, so out-of-bounds here is always a
"you cannot go that way" failure.

Determinism
===========

Tile description selection is deterministic on
``(region_slug, x, y)``. The same tile reads the same way every
visit. Different tiles read differently. We hash the tuple and
modulo against the variant count.

What this drop does NOT do
==========================

  - Does not touch the DB. The character-position writes happen
    in the future MoveCommand wilderness branch.
  - Does not implement edge crossings (hand-built room <-> wilderness).
    No ``edges:`` block exists yet in dune_sea.yaml; Drop 2 phase 2
    adds that content + the boundary handling.
  - Does not implement stamina, hazards, or encounters (Drops 3/5).
  - Does not implement landmark visibility / search (Drop 4).
  - Does not implement the ``travel <landmark>`` aid command.
  - Does not write the live-command surface (look, north, etc.).
    Drop 2 phase 2 wires the engine seam into MoveCommand and
    LookCommand once the edge format lands.

See also
========

  - ``engine/wilderness_loader.py``: parses the region YAML into a
    ``WildernessRegion`` dataclass that this module consumes.
  - ``engine/wilderness_writer.py``: writes landmark rooms + (per
    F.7.a) emits ``properties.slug`` on each.
  - ``data/worlds/clone_wars/wilderness/dune_sea.yaml``: the first
    region YAML.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Optional, Mapping, Any

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Direction tables
# ─────────────────────────────────────────────────────────────────────────────

# Cardinal + diagonal direction → (dx, dy) deltas. Bare cardinals are
# the canonical names; aliases (n, ne, etc.) map to the same delta.
DIRECTION_DELTAS: dict[str, tuple[int, int]] = {
    "north":     (0,  1),
    "south":     (0, -1),
    "east":      (1,  0),
    "west":      (-1, 0),
    "northeast": (1,  1),
    "northwest": (-1, 1),
    "southeast": (1, -1),
    "southwest": (-1, -1),
    # Common abbreviations
    "n":  (0,  1),
    "s":  (0, -1),
    "e":  (1,  0),
    "w":  (-1, 0),
    "ne": (1,  1),
    "nw": (-1, 1),
    "se": (1, -1),
    "sw": (-1, -1),
}


CARDINAL_DIRECTIONS: tuple[str, ...] = ("north", "south", "east", "west")
ALL_DIRECTIONS: tuple[str, ...] = (
    "north", "south", "east", "west",
    "northeast", "northwest", "southeast", "southwest",
)


# ─────────────────────────────────────────────────────────────────────────────
# Move result types
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class MoveResult:
    """Structured result from ``move_in_wilderness``.

    The caller writes ``new_x`` / ``new_y`` to the character row when
    ``ok`` is True. When ``ok`` is False, the caller surfaces
    ``reason`` to the player.
    """
    ok: bool
    new_x: Optional[int] = None
    new_y: Optional[int] = None
    terrain: Optional[str] = None      # terrain at the destination tile
    move_cost: int = 0                  # stamina cost; 0 if move failed
    reason: str = ""                    # human-readable failure reason
    # Did this move leave the region (i.e. would have crossed a region
    # boundary)? Drop 2 phase 2 will resolve this through the edges
    # block. For Drop 2 phase 1, this just signals to the caller that
    # they should look up region edges before committing.
    crossed_boundary: bool = False
    boundary_direction: Optional[str] = None


# ─────────────────────────────────────────────────────────────────────────────
# Movement helper
# ─────────────────────────────────────────────────────────────────────────────


def normalize_direction(direction: str) -> Optional[str]:
    """Map a direction input (cardinal, diagonal, or abbreviation) to a
    canonical name. Returns None if the input isn't a movement direction.

    >>> normalize_direction("n")
    'north'
    >>> normalize_direction("Northeast")
    'northeast'
    >>> normalize_direction("up")  # not a wilderness direction
    """
    if not direction:
        return None
    d = direction.lower().strip()
    # Explicit abbreviation → canonical map
    abbrev = {
        "n": "north", "s": "south", "e": "east", "w": "west",
        "ne": "northeast", "nw": "northwest",
        "se": "southeast", "sw": "southwest",
    }
    if d in abbrev:
        return abbrev[d]
    if d in ALL_DIRECTIONS:
        return d
    return None


def move_in_wilderness(
    region,
    x: int,
    y: int,
    direction: str,
) -> MoveResult:
    """Compute the result of moving ``direction`` from ``(x, y)`` in ``region``.

    Pure function. Does not touch the DB. Caller is responsible for
    persisting the new coordinates if ``result.ok`` is True.

    Args:
        region: a ``WildernessRegion`` dataclass instance (from
            ``engine.wilderness_loader``). Must have ``grid_width``,
            ``grid_height``, ``default_terrain``, and ``terrains``.
        x, y: current wilderness coordinates.
        direction: any of the keys in ``DIRECTION_DELTAS`` (case-
            insensitive, abbreviations OK).

    Returns:
        ``MoveResult`` with ``ok=True`` and new coordinates on
        success, or ``ok=False`` with a reason on failure.

        On a boundary-crossing attempt (would leave the region):
        ``ok=False``, ``crossed_boundary=True``, ``boundary_direction``
        set to the canonical direction. Caller decides whether to
        check edges and resolve to a hand-built room, or surface
        a "you can't go that way" message.
    """
    canonical = normalize_direction(direction)
    if canonical is None:
        return MoveResult(ok=False, reason=f"Unknown direction: {direction!r}")

    dx, dy = DIRECTION_DELTAS[canonical]
    new_x = x + dx
    new_y = y + dy

    width = region.grid_width
    height = region.grid_height

    # Bounds check
    if new_x < 0 or new_x >= width or new_y < 0 or new_y >= height:
        return MoveResult(
            ok=False,
            reason="You can't go that way — the region ends here.",
            crossed_boundary=True,
            boundary_direction=canonical,
        )

    # Resolve destination terrain. Per design §4.2: tile_assignments
    # override the default; otherwise default_terrain. Drop 2 dune_sea
    # has no tile_assignments, so this is currently always
    # default_terrain — but the seam is in place for future regions.
    terrain_name = _terrain_at(region, new_x, new_y)

    terrain_cfg = (region.terrains or {}).get(terrain_name)
    move_cost = 1
    if terrain_cfg is not None:
        # Loader stores terrains as WildernessTerrain dataclass instances;
        # support both dataclass attr access AND dict access defensively.
        move_cost = _terrain_attr(terrain_cfg, "move_cost", 1)

    return MoveResult(
        ok=True,
        new_x=new_x,
        new_y=new_y,
        terrain=terrain_name,
        move_cost=int(move_cost),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tile renderer
# ─────────────────────────────────────────────────────────────────────────────


def render_tile(
    region,
    x: int,
    y: int,
    *,
    time_of_day: Optional[str] = None,
    weather: Optional[str] = None,
) -> dict:
    """Render the description of a wilderness tile.

    Pure function. Returns a structured dict the caller can compose
    into a ``look`` output. Drop 2 phase 2 will write the actual
    text-formatting layer that consumes this.

    Args:
        region: ``WildernessRegion`` dataclass.
        x, y: tile coordinates.
        time_of_day: optional, one of "day"/"night"/"dawn"/"dusk".
            If the terrain has a ``time_overlays[time_of_day]`` entry,
            that overlay is appended to the description.
        weather: optional, e.g. "clear" / "sandstorm". Reserved for
            Drop 5 (encounters / weather); Drop 2 ignores it.

    Returns:
        dict with keys:
          - ``region_name``      str
          - ``coordinates``      tuple (x, y)
          - ``terrain``          str   (terrain slug, e.g. "dune")
          - ``description``      str   (deterministic variant)
          - ``time_overlay``     str|None  (overlay text if time_of_day
                                            matched; else None)
          - ``move_cost``        int
          - ``sight_radius``     int
          - ``ambient_hazard``   str|None
          - ``hazard_severity``  int
          - ``security``         str   (region default for Drop 2)
          - ``out_of_bounds``    bool  (True only if coords invalid)

    On out-of-bounds coordinates, returns a defensive dict with
    ``out_of_bounds: True`` and the rest of the fields blank.
    Callers should never pass out-of-bounds tiles; this just
    avoids crashing.
    """
    if not _in_bounds(region, x, y):
        return {
            "region_name": getattr(region, "name", ""),
            "coordinates": (x, y),
            "terrain": "",
            "description": "",
            "time_overlay": None,
            "move_cost": 0,
            "sight_radius": 0,
            "ambient_hazard": None,
            "hazard_severity": 0,
            "security": "",
            "out_of_bounds": True,
        }

    terrain_name = _terrain_at(region, x, y)
    terrain_cfg = (region.terrains or {}).get(terrain_name)

    # Pull terrain attributes defensively (loader uses a dataclass;
    # in tests we accept dicts too).
    variants = _terrain_attr(terrain_cfg, "variants", []) or [""]
    move_cost = int(_terrain_attr(terrain_cfg, "move_cost", 1))
    sight_radius = int(_terrain_attr(terrain_cfg, "sight_radius", 1))
    ambient_hazard = _terrain_attr(terrain_cfg, "ambient_hazard", None)
    hazard_severity = int(_terrain_attr(terrain_cfg, "hazard_severity", 0))
    time_overlays = _terrain_attr(terrain_cfg, "time_overlays", {}) or {}

    # Deterministic variant selection. Same tile reads the same way
    # every visit — the design's "place feels like a place" property.
    description = _select_variant(region.slug, x, y, variants)

    overlay_text = None
    if time_of_day and isinstance(time_overlays, dict):
        overlay_text = time_overlays.get(time_of_day)

    return {
        "region_name": getattr(region, "name", ""),
        "coordinates": (x, y),
        "terrain": terrain_name,
        "description": description,
        "time_overlay": overlay_text,
        "move_cost": move_cost,
        "sight_radius": sight_radius,
        "ambient_hazard": ambient_hazard,
        "hazard_severity": hazard_severity,
        "security": getattr(region, "default_security", ""),
        "out_of_bounds": False,
    }


def render_adjacent_terrain(region, x: int, y: int) -> dict:
    """Compute the terrain type for each cardinal neighbor.

    Used by the ``look`` command's "Terrain around you" panel
    (per design §4.4 example output). Out-of-bounds neighbors
    return None so the caller can render them as "edge of the
    region" or similar.

    Returns dict mapping cardinal direction → terrain slug or None:
        {"north": "dune", "south": "rocky_outcrop",
         "east": "dune",  "west": None}
    """
    out = {}
    for d in CARDINAL_DIRECTIONS:
        dx, dy = DIRECTION_DELTAS[d]
        nx, ny = x + dx, y + dy
        if _in_bounds(region, nx, ny):
            out[d] = _terrain_at(region, nx, ny)
        else:
            out[d] = None
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────


def _in_bounds(region, x: int, y: int) -> bool:
    """True iff (x, y) is within the region's grid."""
    return 0 <= x < region.grid_width and 0 <= y < region.grid_height


def _terrain_at(region, x: int, y: int) -> str:
    """Resolve the terrain slug at (x, y).

    For Drop 2: always returns the region's default terrain. Future
    drops will check ``tile_assignments`` (per-tile overrides in the
    region YAML) before falling back to default. The seam is here
    so future work doesn't need to touch movement or rendering.
    """
    # Future: if region has tile_assignments, look up (x, y).
    # For now, default-only.
    return region.default_terrain


def _terrain_attr(terrain_cfg, attr: str, default):
    """Read an attribute from a terrain config (dataclass or dict).

    The wilderness_loader produces ``WildernessTerrain`` dataclass
    instances; tests sometimes use plain dicts. Supporting both
    keeps tests simple without a type adapter.
    """
    if terrain_cfg is None:
        return default
    if isinstance(terrain_cfg, dict):
        return terrain_cfg.get(attr, default)
    return getattr(terrain_cfg, attr, default)


def _select_variant(region_slug: str, x: int, y: int, variants: list) -> str:
    """Deterministically choose one variant for tile (x, y) in this region.

    Hashes ``(region_slug, x, y)`` and indexes into the variant list.
    Same tile reads the same way every visit — different tiles read
    differently — and the choice is stable across server restarts.

    Design §4.4 mentions hashing ``(region_id, x, y, weather_state)``;
    we leave weather out of the hash for Drop 2 (no weather system
    yet) so descriptions are fully stable. Drop 5 can add weather
    rotation by mixing it into the hash key.
    """
    if not variants:
        return ""
    if len(variants) == 1:
        return variants[0]
    key = f"{region_slug}|{x}|{y}".encode("utf-8")
    h = int(hashlib.sha1(key).hexdigest()[:8], 16)
    return variants[h % len(variants)]
