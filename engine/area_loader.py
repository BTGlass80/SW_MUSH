# -*- coding: utf-8 -*-
"""
engine/area_loader.py — AreaGeometry loader for the redesigned datapad map.

Drop F.MAP.1 (Tier 1 #4, Step 1 of map redesign implementation).

Per architecture v41 §3.6 "Server-side data path":

    AreaGeometry is per-area static (rare changes); the player's
    room_id/x/y and the contacts: [] array are per-tick live state.
    Server pushes:
      - area_geometry event when the player crosses an area boundary
      - player_position event on movement
      - contacts_update event on roster change

This module loads the static side: an AreaGeometry YAML that mirrors
the design-handoff fixture (`mos-eisley.js`) into a typed dataclass
and emits a JSON-serializable dict on demand.

Seam discipline (v41 §4.5): this drop ships the loader contract WITH
NO LIVE CONSUMER. No server route emits area_geometry yet; no
client-side renderer consumes it yet. Wiring is a subsequent drop.
The loader exists so:

  1. The data contract is locked in YAML, not JS.
  2. Tests verify the YAML round-trips through the loader without
     drift relative to the design fixture.
  3. The next drop (renderer wire-up) has a stable seam to call.

Public API:
    load_area_geometry(area_key: str, era: str = ...) -> AreaGeometry
    discover_area_keys(era: str = ...) -> list[str]
    AreaGeometry, District, MapRoom, ExitPath, MapLabel, Landmark, MapBounds

The dataclass shape matches the JS contract one-for-one (see
design_handoff_datapad_map/README.md "The AreaGeometry shape").

CRITICAL AUTHORING RULES (validated at load time):
  - Rooms in `rooms[]` must have unique integer ids.
  - exit_paths keys must be of the form "<int>-<int>".
  - Districts must have at least 3 polygon points.
  - bounds must satisfy x_min < x_max and y_min < y_max.
  - Landmarks that share coords with a room must have min_zoom >= 2
    (the renderer stacks them at tier-1 otherwise — confirmed bug
    from prototype iteration).
  - Labels must reference an existing exit_path id when path_id
    is set; ditto room ids when `between` is set.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


log = logging.getLogger(__name__)

# Where AreaGeometry YAMLs live, by era. Caller can override for tests.
DEFAULT_WORLDS_ROOT = Path("data") / "worlds"
DEFAULT_ERA = "clone_wars"

# exit_paths key is "fromId-toId" with both ids non-negative integers.
_EXIT_PATH_KEY_RE = re.compile(r"^(\d+)-(\d+)$")

# Valid path kinds — must match map_view.js pathStyle keys.
_VALID_PATH_KINDS = frozenset({"street", "alley", "road", "trail", "corridor"})

# Valid label kinds — must match map_view.js LabelOnPath dispatch.
_VALID_LABEL_KINDS = frozenset({"street", "flavor", "warning"})

# Valid landmark icons — match map_view.js LM_GLYPHS keys.
_VALID_LANDMARK_ICONS = frozenset({
    "wreck", "hutt", "cantina", "dock", "ship", "bones",
    "palace", "sarlacc", "beacon",
})


# ── Data classes ────────────────────────────────────────────────────────────


@dataclass
class MapBounds:
    """World-coordinate rectangle covered by the area."""
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    def to_dict(self) -> dict:
        return {
            "x_min": self.x_min, "y_min": self.y_min,
            "x_max": self.x_max, "y_max": self.y_max,
        }


@dataclass
class District:
    """A polygon-bounded zone within an area (Spaceport, Civic, etc.)."""
    id: str
    name: str
    polygon: list[list[float]]            # [[x, y], ...] closed polygon
    label_anchor: list[float]             # [x, y] in empty corner, never on a street
    rotation: float = 0.0                 # label rotation degrees

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "polygon": [list(p) for p in self.polygon],
            "label_anchor": list(self.label_anchor),
            "rotation": self.rotation,
        }


@dataclass
class MapRoom:
    """A single rendered room (footprint + glyph) in world coords.

    The ``slug`` field is optional. When set, it ties this AreaGeometry
    render-room to the production room of the same slug in
    ``data/worlds/<era>/planets/<planet>.yaml``. The runtime registry
    (see ``AreaGeometryRegistry``) builds a reverse index keyed by slug
    so the server can answer 'which area is the player's room in?' in
    O(1) — needed by the live wire-up (F.MAP.2)."""
    id: int
    name: str
    zone: str            # district id
    x: float
    y: float
    w: float
    h: float
    style: str           # see map_view.js STY (dock, cantina, civic, ...)
    symbol: str          # the glyph rendered inside the footprint
    slug: Optional[str] = None  # production room slug, for the runtime registry

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id, "name": self.name, "zone": self.zone,
            "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "style": self.style, "symbol": self.symbol,
        }
        if self.slug is not None:
            d["slug"] = self.slug
        return d


@dataclass
class ExitPath:
    """A polyline corridor between rooms — drawn as a wide ribbon."""
    kind: str             # one of street | road | alley | trail | corridor
    path: list[list[float]]   # polyline in world coords
    width: Optional[float] = None  # optional override; default by kind

    def to_dict(self) -> dict:
        d = {"kind": self.kind, "path": [list(p) for p in self.path]}
        if self.width is not None:
            d["width"] = self.width
        return d


@dataclass
class MapLabel:
    """Label anchored to either an exit_path, a between:[a,b] segment, or
    a fixed pos. Visibility is controlled by [min_zoom, max_zoom]."""
    text: str
    kind: str             # street | flavor | warning
    # Anchor (one of three modes — exactly one should be set):
    path_id: Optional[str] = None
    between: Optional[list[int]] = None
    pos: Optional[list[float]] = None
    rot: float = 0.0
    t: float = 0.5         # fractional position along path (path_id/between modes)
    side: int = 0          # perpendicular offset side (-1, 0, +1)
    offset: float = 0.0    # perpendicular offset distance
    size: float = 8.0      # px-ish; renderer divides by 22 to get world units
    weight: int = 400
    min_zoom: int = 0
    max_zoom: int = 99

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "text": self.text, "kind": self.kind,
            "t": self.t, "side": self.side, "offset": self.offset,
            "size": self.size, "weight": self.weight,
            "min_zoom": self.min_zoom, "max_zoom": self.max_zoom,
        }
        if self.path_id is not None:
            d["path_id"] = self.path_id
        if self.between is not None:
            d["between"] = list(self.between)
        if self.pos is not None:
            d["pos"] = list(self.pos)
            d["rot"] = self.rot
        return d


@dataclass
class Landmark:
    """A POI marker independent of any room footprint."""
    id: str
    icon: str             # wreck | hutt | cantina | dock | ship | bones | palace | sarlacc | beacon
    name: str
    pos: list[float]
    min_zoom: int = 1
    max_zoom: int = 99

    def to_dict(self) -> dict:
        return {
            "id": self.id, "icon": self.icon, "name": self.name,
            "pos": list(self.pos),
            "min_zoom": self.min_zoom, "max_zoom": self.max_zoom,
        }


@dataclass
class AreaGeometry:
    """The full per-area static contract. Live state (player, contacts)
    is layered in by the server at push time, NOT loaded from this file."""
    schema_version: int
    area_key: str           # e.g. "tatooine.mos_eisley"
    display_name: str       # e.g. "MOS EISLEY"
    planet: str             # e.g. "TATOOINE"
    era: str                # e.g. "20 BBY · Clone Wars"
    default_terrain: str    # "sand" | "duracrete" | etc.
    palette: str            # named palette key — must match tokens.js PALETTES
    bounds: MapBounds
    districts: list[District]
    rooms: list[MapRoom]
    exits: list             # raw entries — list-pair OR {from, to, hidden?}
    exit_paths: dict[str, ExitPath]
    labels: list[MapLabel]
    landmarks: list[Landmark]
    # Hybrid raster substrate (architecture v51 lane): optional path to a
    # pre-painted PNG rendered at the world bounds beneath the SVG overlay
    # layers. When set, the client renderer skips the procedural district/
    # building/street/furniture layers (they're baked into the painting)
    # and keeps labels, entities, weather, and chrome on top. Absent =>
    # fully procedural rendering (the default for every area today).
    substrate_image: Optional[str] = None
    # Marks a building-INTERIOR map (vs a city overview). On a slug collision —
    # an interior room slug also claimed by its parent city-overview map, which
    # is additive-only so the slug can't be removed there — the interior wins the
    # registry binding deterministically, so a player IN the interior is bound to
    # the interior map, not the city overview. See AreaGeometryRegistry._add.
    is_interior: bool = False

    def to_dict(self, *, include_player: bool = False,
                player: Optional[dict] = None,
                contacts: Optional[list] = None) -> dict:
        """Serialize for the wire. Live state (player, contacts) is
        injected by the caller — the loader doesn't know it."""
        out: dict[str, Any] = {
            "schema_version": self.schema_version,
            "area_key": self.area_key,
            "display_name": self.display_name,
            "planet": self.planet,
            "era": self.era,
            "default_terrain": self.default_terrain,
            "palette": self.palette,
            "bounds": self.bounds.to_dict(),
            "districts": [d.to_dict() for d in self.districts],
            "rooms": [r.to_dict() for r in self.rooms],
            "exits": [list(e) if isinstance(e, (list, tuple)) else dict(e)
                      for e in self.exits],
            "exit_paths": {k: v.to_dict() for k, v in self.exit_paths.items()},
            "labels": [l.to_dict() for l in self.labels],
            "landmarks": [lm.to_dict() for lm in self.landmarks],
        }
        # Optional hybrid substrate path — emitted only when present so
        # the wire shape for procedural areas is unchanged (the JS
        # renderer keys off truthiness of `substrate_image`).
        if self.substrate_image:
            out["substrate_image"] = self.substrate_image
        # Emit the interior marker so a future client can dispatch on it (e.g.
        # suppress the compass/district chrome for a building interior). Only
        # when true, keeping the procedural-area wire shape unchanged.
        if self.is_interior:
            out["is_interior"] = True
        if include_player:
            out["player"] = dict(player) if player else {}
            out["contacts"] = list(contacts) if contacts else []
        return out


# ── Errors ───────────────────────────────────────────────────────────────────


class AreaGeometryLoadError(Exception):
    """Raised on parse or validation failure of an AreaGeometry YAML."""


# ── Public API ───────────────────────────────────────────────────────────────


def load_area_geometry(area_key: str,
                       era: str = DEFAULT_ERA,
                       worlds_root: Optional[Path] = None) -> AreaGeometry:
    """Load and validate an AreaGeometry YAML.

    Args:
        area_key: e.g. "tatooine.mos_eisley". Resolves to
            data/worlds/<era>/maps/<basename>.yaml where basename is
            the part after the final dot (e.g. "mos_eisley").
        era: era code; default "clone_wars".
        worlds_root: override for tests (default: ./data/worlds).

    Returns:
        AreaGeometry (validated).

    Raises:
        AreaGeometryLoadError: on file-not-found or any validation failure.
    """
    root = worlds_root or DEFAULT_WORLDS_ROOT
    basename = area_key.rsplit(".", 1)[-1] if "." in area_key else area_key
    path = Path(root) / era / "maps" / f"{basename}.yaml"
    if not path.exists():
        raise AreaGeometryLoadError(
            f"AreaGeometry YAML not found: {path}"
        )
    try:
        # Python 3.14 on Windows defaults to cp1252 — explicit encoding
        # is non-negotiable per the project standard.
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise AreaGeometryLoadError(
            f"YAML parse error in {path}: {e}"
        ) from e
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: expected top-level mapping, got {type(raw).__name__}"
        )
    geom = _parse_area_geometry(raw, path=path)
    _validate_area_geometry(geom, path=path)
    log.info("[area_loader] loaded %s (%d rooms, %d districts, %d exit_paths)",
             geom.area_key, len(geom.rooms), len(geom.districts),
             len(geom.exit_paths))
    return geom


def discover_area_keys(era: str = DEFAULT_ERA,
                       worlds_root: Optional[Path] = None) -> list[str]:
    """List the area_keys for every YAML under data/worlds/<era>/maps/.

    Returns area_keys (e.g. "tatooine.mos_eisley") sorted alphabetically.
    Files that fail to parse are logged and skipped — do not raise.
    """
    root = worlds_root or DEFAULT_WORLDS_ROOT
    maps_dir = Path(root) / era / "maps"
    if not maps_dir.exists():
        return []
    keys: list[str] = []
    for p in sorted(maps_dir.glob("*.yaml")):
        try:
            with open(p, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f)
            if isinstance(raw, dict) and isinstance(raw.get("area_key"), str):
                keys.append(raw["area_key"])
        except (yaml.YAMLError, OSError) as e:
            log.warning("[area_loader] discover skipped %s: %s", p, e)
    keys.sort()
    return keys


# ── Parsing ──────────────────────────────────────────────────────────────────


def _parse_area_geometry(raw: dict, *, path: Path) -> AreaGeometry:
    """Map raw YAML into typed dataclasses. Raises on missing/wrong
    types; structural validation happens in _validate_area_geometry."""
    schema_version = int(_required(raw, "schema_version", path))
    if schema_version != 1:
        raise AreaGeometryLoadError(
            f"{path}: unsupported schema_version {schema_version} "
            f"(loader supports 1)"
        )

    bounds = _parse_bounds(_required(raw, "bounds", path), path)

    districts = [_parse_district(d, i, path)
                 for i, d in enumerate(_required(raw, "districts", path))]

    rooms = [_parse_room(r, i, path)
             for i, r in enumerate(_required(raw, "rooms", path))]

    exits_raw = _required(raw, "exits", path)
    exits: list = []
    for i, e in enumerate(exits_raw):
        if isinstance(e, list) and len(e) == 2:
            exits.append([int(e[0]), int(e[1])])
        elif isinstance(e, dict) and "from" in e and "to" in e:
            entry = {"from": int(e["from"]), "to": int(e["to"])}
            if e.get("hidden"):
                entry["hidden"] = True
            exits.append(entry)
        else:
            raise AreaGeometryLoadError(
                f"{path}: exits[{i}] must be [from, to] or "
                f"{{from, to, hidden?}}, got {e!r}"
            )

    exit_paths_raw = raw.get("exit_paths") or {}
    if not isinstance(exit_paths_raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: exit_paths must be a mapping"
        )
    exit_paths: dict[str, ExitPath] = {}
    for key, ep in exit_paths_raw.items():
        exit_paths[str(key)] = _parse_exit_path(ep, key, path)

    labels = [_parse_label(l, i, path)
              for i, l in enumerate(raw.get("labels") or [])]

    landmarks = [_parse_landmark(lm, i, path)
                 for i, lm in enumerate(raw.get("landmarks") or [])]

    return AreaGeometry(
        schema_version=schema_version,
        area_key=str(_required(raw, "area_key", path)),
        display_name=str(_required(raw, "display_name", path)),
        planet=str(_required(raw, "planet", path)),
        era=str(_required(raw, "era", path)),
        default_terrain=str(raw.get("default_terrain", "sand")),
        palette=str(_required(raw, "palette", path)),
        bounds=bounds,
        districts=districts,
        rooms=rooms,
        exits=exits,
        exit_paths=exit_paths,
        labels=labels,
        landmarks=landmarks,
        substrate_image=(str(raw["substrate_image"])
                         if raw.get("substrate_image") else None),
        is_interior=bool(raw.get("is_interior", False)),
    )


def _required(raw: dict, key: str, path: Path):
    if key not in raw:
        raise AreaGeometryLoadError(f"{path}: missing required field '{key}'")
    return raw[key]


def _parse_bounds(raw, path: Path) -> MapBounds:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(f"{path}: bounds must be a mapping")
    return MapBounds(
        x_min=float(_required(raw, "x_min", path)),
        y_min=float(_required(raw, "y_min", path)),
        x_max=float(_required(raw, "x_max", path)),
        y_max=float(_required(raw, "y_max", path)),
    )


def _parse_district(raw, idx: int, path: Path) -> District:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: districts[{idx}] must be a mapping"
        )
    polygon_raw = _required(raw, "polygon", path)
    polygon = [[float(p[0]), float(p[1])] for p in polygon_raw]
    anchor_raw = _required(raw, "label_anchor", path)
    return District(
        id=str(_required(raw, "id", path)),
        name=str(_required(raw, "name", path)),
        polygon=polygon,
        label_anchor=[float(anchor_raw[0]), float(anchor_raw[1])],
        rotation=float(raw.get("rotation", 0)),
    )


def _parse_room(raw, idx: int, path: Path) -> MapRoom:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: rooms[{idx}] must be a mapping"
        )
    slug = raw.get("slug")
    return MapRoom(
        id=int(_required(raw, "id", path)),
        name=str(_required(raw, "name", path)),
        zone=str(_required(raw, "zone", path)),
        x=float(_required(raw, "x", path)),
        y=float(_required(raw, "y", path)),
        w=float(_required(raw, "w", path)),
        h=float(_required(raw, "h", path)),
        style=str(_required(raw, "style", path)),
        symbol=str(_required(raw, "symbol", path)),
        slug=str(slug) if slug is not None else None,
    )


def _parse_exit_path(raw, key, path: Path) -> ExitPath:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: exit_paths[{key!r}] must be a mapping"
        )
    pts_raw = _required(raw, "path", path)
    pts = [[float(p[0]), float(p[1])] for p in pts_raw]
    width = raw.get("width")
    return ExitPath(
        kind=str(_required(raw, "kind", path)),
        path=pts,
        width=float(width) if width is not None else None,
    )


def _parse_label(raw, idx: int, path: Path) -> MapLabel:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: labels[{idx}] must be a mapping"
        )
    pos = raw.get("pos")
    between = raw.get("between")
    return MapLabel(
        text=str(_required(raw, "text", path)),
        kind=str(_required(raw, "kind", path)),
        path_id=str(raw["path_id"]) if raw.get("path_id") is not None else None,
        between=[int(between[0]), int(between[1])] if between else None,
        pos=[float(pos[0]), float(pos[1])] if pos else None,
        rot=float(raw.get("rot", 0)),
        t=float(raw.get("t", 0.5)),
        side=int(raw.get("side", 0)),
        offset=float(raw.get("offset", 0)),
        size=float(raw.get("size", 8)),
        weight=int(raw.get("weight", 400)),
        min_zoom=int(raw.get("min_zoom", 0)),
        max_zoom=int(raw.get("max_zoom", 99)),
    )


def _parse_landmark(raw, idx: int, path: Path) -> Landmark:
    if not isinstance(raw, dict):
        raise AreaGeometryLoadError(
            f"{path}: landmarks[{idx}] must be a mapping"
        )
    pos_raw = _required(raw, "pos", path)
    return Landmark(
        id=str(_required(raw, "id", path)),
        icon=str(_required(raw, "icon", path)),
        name=str(_required(raw, "name", path)),
        pos=[float(pos_raw[0]), float(pos_raw[1])],
        min_zoom=int(raw.get("min_zoom", 1)),
        max_zoom=int(raw.get("max_zoom", 99)),
    )


# ── Validation ───────────────────────────────────────────────────────────────


def _validate_area_geometry(geom: AreaGeometry, *, path: Path) -> None:
    """Structural rules. Anything caught here would either render
    badly (e.g. landmarks doubled-stamped on rooms at tier-1) or
    crash the renderer (e.g. label referencing a missing exit_path).
    Fail loudly at load time, not at render time in the browser."""
    errors: list[str] = []

    # bounds sanity
    b = geom.bounds
    if b.x_min >= b.x_max:
        errors.append(f"bounds: x_min ({b.x_min}) must be < x_max ({b.x_max})")
    if b.y_min >= b.y_max:
        errors.append(f"bounds: y_min ({b.y_min}) must be < y_max ({b.y_max})")

    # districts: at least 3 polygon points; non-empty id; rotation is finite.
    district_ids: set[str] = set()
    for i, d in enumerate(geom.districts):
        if not d.id:
            errors.append(f"districts[{i}]: id is empty")
        if d.id in district_ids:
            errors.append(f"districts[{i}]: duplicate id {d.id!r}")
        district_ids.add(d.id)
        if len(d.polygon) < 3:
            errors.append(
                f"districts[{i}] ({d.id!r}): polygon needs >= 3 points, "
                f"got {len(d.polygon)}"
            )

    # rooms: unique ids; styles must be in STY (renderer falls back to street);
    # zone must reference an existing district id; slugs (when present)
    # must be unique within the area.
    room_ids: set[int] = set()
    rooms_by_coord: dict[tuple[float, float], int] = {}
    seen_slugs: dict[str, int] = {}
    for i, r in enumerate(geom.rooms):
        if r.id in room_ids:
            errors.append(f"rooms[{i}] ({r.name!r}): duplicate id {r.id}")
        room_ids.add(r.id)
        if r.zone and district_ids and r.zone not in district_ids:
            errors.append(
                f"rooms[{i}] ({r.name!r}): zone {r.zone!r} not in districts"
            )
        if r.w <= 0 or r.h <= 0:
            errors.append(
                f"rooms[{i}] ({r.name!r}): w/h must be positive, got {r.w}/{r.h}"
            )
        if r.slug is not None:
            if r.slug in seen_slugs:
                errors.append(
                    f"rooms[{i}] ({r.name!r}): duplicate slug {r.slug!r} "
                    f"(already used by room id {seen_slugs[r.slug]})"
                )
            else:
                seen_slugs[r.slug] = r.id
        rooms_by_coord[(round(r.x, 4), round(r.y, 4))] = r.id

    # exits: both endpoints must be valid room ids
    for i, e in enumerate(geom.exits):
        if isinstance(e, list):
            a, b_id = e[0], e[1]
        else:
            a, b_id = e["from"], e["to"]
        if a not in room_ids:
            errors.append(f"exits[{i}]: 'from' {a} not in rooms")
        if b_id not in room_ids:
            errors.append(f"exits[{i}]: 'to' {b_id} not in rooms")

    # exit_paths: keys must parse, kinds must be valid, both ids must
    # be valid rooms (or one of them is — defensive).
    for key, ep in geom.exit_paths.items():
        m = _EXIT_PATH_KEY_RE.match(key)
        if not m:
            errors.append(
                f"exit_paths[{key!r}]: key must match '<int>-<int>'"
            )
            continue
        a, b_id = int(m.group(1)), int(m.group(2))
        if a not in room_ids:
            errors.append(
                f"exit_paths[{key!r}]: 'from' {a} not in rooms"
            )
        if b_id not in room_ids:
            errors.append(
                f"exit_paths[{key!r}]: 'to' {b_id} not in rooms"
            )
        if ep.kind not in _VALID_PATH_KINDS:
            errors.append(
                f"exit_paths[{key!r}]: kind {ep.kind!r} not in "
                f"{sorted(_VALID_PATH_KINDS)}"
            )
        if len(ep.path) < 2:
            errors.append(
                f"exit_paths[{key!r}]: path needs >= 2 points, "
                f"got {len(ep.path)}"
            )

    # labels: kinds valid; references must resolve.
    exit_path_keys = set(geom.exit_paths.keys())
    for i, lab in enumerate(geom.labels):
        if lab.kind not in _VALID_LABEL_KINDS:
            errors.append(
                f"labels[{i}]: kind {lab.kind!r} not in "
                f"{sorted(_VALID_LABEL_KINDS)}"
            )
        anchor_modes = sum(1 for v in (lab.path_id, lab.between, lab.pos)
                           if v is not None)
        if anchor_modes != 1:
            errors.append(
                f"labels[{i}] ({lab.text!r}): exactly one of "
                f"path_id/between/pos must be set, got {anchor_modes}"
            )
        if lab.path_id and lab.path_id not in exit_path_keys:
            errors.append(
                f"labels[{i}] ({lab.text!r}): path_id {lab.path_id!r} "
                f"not in exit_paths"
            )
        if lab.between is not None:
            for endpoint in lab.between:
                if endpoint not in room_ids:
                    errors.append(
                        f"labels[{i}] ({lab.text!r}): between references "
                        f"unknown room id {endpoint}"
                    )
        if lab.min_zoom > lab.max_zoom:
            errors.append(
                f"labels[{i}] ({lab.text!r}): min_zoom {lab.min_zoom} "
                f"> max_zoom {lab.max_zoom}"
            )

    # landmarks: known icons; coords-with-room must have min_zoom >= 2
    # (the "double-stamped on rooms" bug from the prototype iteration).
    for i, lm in enumerate(geom.landmarks):
        if lm.icon not in _VALID_LANDMARK_ICONS:
            errors.append(
                f"landmarks[{i}] ({lm.id!r}): icon {lm.icon!r} not in "
                f"{sorted(_VALID_LANDMARK_ICONS)}"
            )
        coord = (round(lm.pos[0], 4), round(lm.pos[1], 4))
        if coord in rooms_by_coord and lm.min_zoom < 2:
            errors.append(
                f"landmarks[{i}] ({lm.id!r}) at {coord} shares coords with "
                f"room id {rooms_by_coord[coord]} but min_zoom={lm.min_zoom}; "
                f"must be >= 2 (renderer stacks them at tier-1 otherwise)"
            )
        if lm.min_zoom > lm.max_zoom:
            errors.append(
                f"landmarks[{i}] ({lm.id!r}): min_zoom {lm.min_zoom} "
                f"> max_zoom {lm.max_zoom}"
            )

    if errors:
        joined = "\n  - ".join(errors)
        raise AreaGeometryLoadError(
            f"{path}: {len(errors)} validation error(s):\n  - {joined}"
        )


# ── Runtime registry (F.MAP.2) ──────────────────────────────────────────────


@dataclass
class _RoomLookupEntry:
    """One entry in the registry's reverse index. Returned by
    ``AreaGeometryRegistry.lookup(room_slug)``."""
    area_key: str           # e.g. "tatooine.mos_eisley"
    render_room_id: int     # the AreaGeometry-internal room id (0..n)
    x: float                # world coord (Y-up)
    y: float
    # F.MAP — the room's wilderness region (``rooms.wilderness_region_id``),
    # captured for free in ``resolve_area_room_ids`` from the row already
    # fetched there. NULL/None for city-map rooms (which have no region).
    # Lets the per-tick POI sweep enumerate live anomalies (keyed by region)
    # without an extra DB round-trip per room. Default None keeps the
    # slug-index construction in ``_add`` (no DB row) back-compatible.
    region_slug: Optional[str] = None


class AreaGeometryRegistry:
    """Runtime cache + reverse index over all authored AreaGeometries
    in an era. Built once at boot; consulted on every minimap push.

    Two operations the server needs:

      1. ``lookup(room_slug)`` → ``_RoomLookupEntry | None``
         Answers 'which area is this room in, and what's the player's
         render-coord?' in O(1). Returns None if the room isn't
         covered by any authored AreaGeometry — caller falls back to
         the legacy minimap path.

      2. ``get_payload(area_key)`` → ``dict | None``
         Returns the JSON-serializable AreaGeometry-as-dict for an
         area (no player/contacts — the caller layers those on at
         push time). Cached after first call.

    Failure tolerance: per-area load failures are logged at WARNING
    and the registry continues to load the rest. A registry that's
    half-loaded is still useful — the unaffected areas still resolve.
    A registry that's fully empty (all loads failed) returns None
    from every lookup, which silently degrades to the legacy
    minimap. The server should NOT die over an AreaGeometry parse
    error.
    """

    def __init__(self):
        self._areas: dict[str, AreaGeometry] = {}
        self._payloads: dict[str, dict] = {}
        self._slug_index: dict[str, _RoomLookupEntry] = {}
        # F.MAP.6: per-area cache of slug→render-coords for fast contact
        # marker construction. Populated lazily by resolve_area_room_ids
        # on first HUD push for an area; consulted on every subsequent
        # tick. The dict shape is:
        #   self._area_room_ids[area_key] = {
        #       db_room_id_int: _RoomLookupEntry,  # for x/y → render coords
        #   }
        # Stored as a separate flat dict so the per-tick contact lookup
        # is a single dict.get() against the NPC's room_id.
        self._area_room_ids: dict[str, dict[int, _RoomLookupEntry]] = {}

    @classmethod
    def load_era(cls, era: str = DEFAULT_ERA,
                 worlds_root: Optional[Path] = None) -> "AreaGeometryRegistry":
        """Build a registry by loading every AreaGeometry under
        ``data/worlds/<era>/maps/*.yaml``.

        Failure tolerance: a per-file load failure is logged at
        WARNING and the loop continues. The returned registry has
        whatever loaded successfully.
        """
        registry = cls()
        for area_key in discover_area_keys(era, worlds_root):
            try:
                geom = load_area_geometry(area_key, era, worlds_root)
            except AreaGeometryLoadError as e:
                log.warning(
                    "[area_loader] registry: skipping %s due to load "
                    "failure: %s", area_key, e,
                )
                continue
            registry._add(geom)
        log.info(
            "[area_loader] registry built for era=%s: %d areas, "
            "%d slug-indexed rooms", era,
            len(registry._areas), len(registry._slug_index),
        )
        return registry

    def _add(self, geom: AreaGeometry) -> None:
        """Insert an AreaGeometry into the registry.

        Slug-collision precedence: a building-INTERIOR area (``is_interior``)
        wins over a city-overview area for a shared slug — so a player IN an
        interior room is bound to the interior map, not the parent city overview
        that (additive-only) also lists that room. Otherwise the second
        occurrence wins (the prior deterministic-but-arbitrary behavior;
        collisions among same-kind areas remain rare and shouldn't happen)."""
        self._areas[geom.area_key] = geom
        for r in geom.rooms:
            if r.slug is None:
                continue
            prior = self._slug_index.get(r.slug)
            if prior is not None and prior.area_key != geom.area_key:
                prior_geom = self._areas.get(prior.area_key)
                prior_interior = bool(prior_geom and prior_geom.is_interior)
                new_interior = bool(geom.is_interior)
                if prior_interior and not new_interior:
                    # An interior already holds this slug — a city overview must
                    # not steal it. Keep the prior (interior) binding.
                    log.info(
                        "[area_loader] registry: slug %r kept on interior %s "
                        "over %s", r.slug, prior.area_key, geom.area_key,
                    )
                    continue
                log.warning(
                    "[area_loader] registry: slug %r appears in both %s "
                    "(room %d) and %s (room %d); %s wins",
                    r.slug, prior.area_key, prior.render_room_id,
                    geom.area_key, r.id,
                    "interior" if (new_interior and not prior_interior)
                    else "second",
                )
            self._slug_index[r.slug] = _RoomLookupEntry(
                area_key=geom.area_key,
                render_room_id=r.id,
                x=r.x, y=r.y,
            )

    def lookup(self, room_slug: str) -> Optional[_RoomLookupEntry]:
        """O(1) reverse lookup: room slug → area + render coords.
        Returns None if no AreaGeometry covers this slug."""
        if not room_slug:
            return None
        return self._slug_index.get(room_slug)

    def get_payload(self, area_key: str) -> Optional[dict]:
        """Return the JSON-serializable AreaGeometry dict (no
        player/contacts). Cached on first access. Returns None if
        the area isn't loaded."""
        if area_key in self._payloads:
            return self._payloads[area_key]
        geom = self._areas.get(area_key)
        if geom is None:
            return None
        # Note: we do NOT include player/contacts — the server layers
        # those on per-push from live state. Caller is responsible for
        # adding them before sending to the client.
        payload = geom.to_dict(include_player=False)
        self._payloads[area_key] = payload
        return payload

    def known_areas(self) -> list[str]:
        """List of loaded area_keys."""
        return sorted(self._areas.keys())

    def known_slugs_count(self) -> int:
        """Total number of slug-indexed rooms across all areas."""
        return len(self._slug_index)

    # ── F.MAP.6 — DB resolution + per-area room_id cache ────────────────

    async def resolve_area_room_ids(self, area_key: str, db) -> dict:
        """Resolve every slug in the given area to its production
        ``rooms.id`` via ``db.get_room_by_slug``, caching the result.

        Returns ``{db_room_id: _RoomLookupEntry}`` — keyed by the
        production room id so the per-tick contact lookup is a single
        dict.get() against the NPC's ``room_id``. Empty dict if the
        area is unknown or every lookup failed.

        First call costs N round-trips to the DB (N = rooms with slugs
        in the area; 53 for Mos Eisley). Subsequent calls are O(1) —
        the result is cached on the registry. Cache eviction is
        intentionally not implemented; production rooms persist for
        the life of the server process.
        """
        if area_key in self._area_room_ids:
            return self._area_room_ids[area_key]
        geom = self._areas.get(area_key)
        if geom is None:
            return {}
        out: dict[int, _RoomLookupEntry] = {}
        getter = getattr(db, "get_room_by_slug", None)
        if not callable(getter):
            log.warning(
                "[area_loader] resolve_area_room_ids: db has no "
                "get_room_by_slug; cannot build contact lookup for %s",
                area_key,
            )
            self._area_room_ids[area_key] = out  # cache empty result
            return out
        for r in geom.rooms:
            if not r.slug:
                continue
            try:
                row = await getter(r.slug)
            except Exception as e:
                log.warning(
                    "[area_loader] get_room_by_slug(%r) failed: %s",
                    r.slug, e,
                )
                continue
            if not row:
                # Slug authored in YAML but no production room (e.g.
                # Senate fixture has no rooms in the DB yet). Skip.
                continue
            db_room_id = row.get("id") if isinstance(row, dict) else None
            if db_room_id is None:
                continue
            # Region is on the row we already fetched — capture it for the
            # POI/anomaly sweep at zero extra DB cost. None for city rooms.
            region_slug = (row.get("wilderness_region_id")
                           if isinstance(row, dict) else None)
            out[int(db_room_id)] = _RoomLookupEntry(
                area_key=area_key,
                render_room_id=r.id,
                x=r.x, y=r.y,
                region_slug=region_slug,
            )
        self._area_room_ids[area_key] = out
        log.info(
            "[area_loader] resolve_area_room_ids: %s → %d/%d rooms "
            "resolved (cached)", area_key, len(out),
            sum(1 for r in geom.rooms if r.slug),
        )
        return out


__all__ = [
    "AreaGeometry", "MapBounds", "District", "MapRoom", "ExitPath",
    "MapLabel", "Landmark",
    "AreaGeometryLoadError",
    "AreaGeometryRegistry",
    "load_area_geometry", "discover_area_keys",
]
