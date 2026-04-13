# -*- coding: utf-8 -*-
"""
Area Map — local neighborhood graph for the web client context panel.

Ground UX Drop 2: BFS from the player's current room (depth 2) returning
a compact node-link graph that the client renders as an SVG minimap.

Usage:
    from engine.area_map import build_area_map
    map_data = await build_area_map(room_id, db, depth=2)
    # map_data is a dict ready to include in hud_update or room_detail

The client SVG renderer expects:
    {
        "current": 17,
        "rooms": [
            {"id": 17, "name": "Inn", "x": 0.5, "y": 0.5, "depth": 0},
            {"id": 7, "name": "Spaceport Row", "x": 0.5, "y": 0.8, "depth": 1},
            ...
        ],
        "edges": [
            {"from": 17, "to": 7, "dir": "south"},
            ...
        ],
        "services": {
            17: ["vendor"],
            7: ["docking"],
        }
    }

Coordinates are normalized 0.0–1.0.  If rooms have map_x/map_y columns
in the DB, those are used (hand-tuned layouts).  Otherwise, a simple
force-directed auto-layout is computed.
"""
import logging
import math
from collections import deque

log = logging.getLogger(__name__)


# ── Direction vectors for auto-layout ──
# Maps exit directions to (dx, dy) offsets for initial placement
_DIR_VECTORS = {
    "north":     ( 0.0, -1.0),
    "south":     ( 0.0,  1.0),
    "east":      ( 1.0,  0.0),
    "west":      (-1.0,  0.0),
    "northeast": ( 0.7, -0.7),
    "northwest": (-0.7, -0.7),
    "southeast": ( 0.7,  0.7),
    "southwest": (-0.7,  0.7),
    "up":        ( 0.3, -0.8),
    "down":      ( 0.3,  0.8),
    "in":        ( 0.0,  0.0),  # special — offset slightly
    "out":       ( 0.0,  0.0),
}

# Service derivation from NPC roles and room environment
# (imported from session.py helpers when available, fallback inline)
_SERVICE_ENVIRONMENTS = {
    "cantina": "cantina", "bar": "cantina", "tavern": "cantina",
    "medical": "medical", "medbay": "medical", "hospital": "medical",
    "docking": "docking", "hangar": "docking", "spaceport": "docking",
    "bay": "docking",
    "workshop": "crafting", "forge": "crafting", "crafting": "crafting",
}


async def build_area_map(room_id: int, db, depth: int = 2,
                         max_rooms: int = 25) -> dict:
    """
    Build a local area map centered on the given room.

    Args:
        room_id: The player's current room ID.
        db: Database handle (async).
        depth: BFS depth (2 = current + neighbors + their neighbors).
        max_rooms: Maximum rooms to include (prevents explosion in
                   densely connected areas).

    Returns:
        Dict with 'current', 'rooms', 'edges', 'services' keys.
        Returns empty dict if room_id is invalid.
    """
    if not room_id or not db:
        return {}

    # BFS to discover the local neighborhood
    visited = {}      # room_id -> depth
    queue = deque()
    queue.append((room_id, 0))
    visited[room_id] = 0

    # Collect edges as (from_id, to_id, direction)
    all_edges = []
    # Cache room rows for name/coordinate lookup
    room_cache = {}

    while queue and len(visited) <= max_rooms:
        current_id, current_depth = queue.popleft()

        # Fetch room data if not cached
        if current_id not in room_cache:
            try:
                room_row = await db.get_room(current_id)
                if room_row:
                    room_cache[current_id] = room_row
            except Exception:
                continue

        if current_depth >= depth:
            continue

        # Fetch exits from this room
        try:
            exits = await db.get_exits(current_id)
        except Exception:
            exits = []

        for ex in exits:
            target = ex.get("to_room_id")
            if not target:
                continue
            direction = ex.get("direction", "")
            is_hidden = ex.get("is_hidden", 0)
            if is_hidden:
                continue

            all_edges.append({
                "from": current_id,
                "to": target,
                "dir": direction,
            })

            if target not in visited and len(visited) < max_rooms:
                visited[target] = current_depth + 1
                queue.append((target, current_depth + 1))
                # Pre-fetch target room
                if target not in room_cache:
                    try:
                        tr = await db.get_room(target)
                        if tr:
                            room_cache[target] = tr
                    except Exception:
                        pass

    # Build room node list
    rooms = []
    has_coords = False  # Track if any room has hand-tuned coordinates

    for rid, d in visited.items():
        row = room_cache.get(rid, {})
        name = row.get("name", f"Room #{rid}")
        # Truncate long names for the minimap
        if len(name) > 28:
            name = name[:26] + "\u2026"

        mx = row.get("map_x")
        my = row.get("map_y")
        if mx is not None and my is not None:
            has_coords = True

        rooms.append({
            "id": rid,
            "name": name,
            "x": float(mx) if mx is not None else None,
            "y": float(my) if my is not None else None,
            "depth": d,
        })

    # If we don't have hand-tuned coordinates, compute auto-layout
    if not has_coords:
        _auto_layout(rooms, all_edges, room_id)

    # Deduplicate edges (both directions may appear)
    seen_edges = set()
    unique_edges = []
    for e in all_edges:
        # Only include edges where both endpoints are in our visited set
        if e["from"] not in visited or e["to"] not in visited:
            continue
        key = (min(e["from"], e["to"]), max(e["from"], e["to"]))
        if key not in seen_edges:
            seen_edges.add(key)
            unique_edges.append(e)

    # Derive services per room (lightweight — just check environment)
    services = {}
    for rid in visited:
        row = room_cache.get(rid, {})
        props_raw = row.get("properties", "{}")
        if isinstance(props_raw, str):
            try:
                import json
                props = json.loads(props_raw)
            except Exception:
                props = {}
        else:
            props = props_raw or {}
        env = (props.get("environment") or "").lower()
        svc_tag = _SERVICE_ENVIRONMENTS.get(env)
        if svc_tag:
            services[rid] = [svc_tag]

    return {
        "current": room_id,
        "rooms": rooms,
        "edges": unique_edges,
        "services": services,
    }


def _auto_layout(rooms: list, edges: list, center_id: int):
    """
    Compute positions for rooms that lack hand-tuned coordinates.

    Uses direction-based placement: the center room goes at (0.5, 0.5),
    neighbors are placed along the direction vector of their connecting
    exit, scaled by depth.  A simple collision-avoidance pass separates
    overlapping nodes.

    Modifies room dicts in-place (sets 'x' and 'y').
    """
    # Index rooms by ID
    by_id = {r["id"]: r for r in rooms}

    # Build adjacency from edges
    adj = {}  # room_id -> [(target_id, direction)]
    for e in edges:
        adj.setdefault(e["from"], []).append((e["to"], e["dir"]))
        # Reverse direction for the other end
        rev_dir = _reverse_dir(e["dir"])
        adj.setdefault(e["to"], []).append((e["from"], rev_dir))

    # Place center
    if center_id in by_id:
        by_id[center_id]["x"] = 0.5
        by_id[center_id]["y"] = 0.5

    # BFS placement
    placed = {center_id}
    queue = deque([center_id])

    while queue:
        rid = queue.popleft()
        parent = by_id.get(rid)
        if not parent or parent["x"] is None:
            continue

        px, py = parent["x"], parent["y"]
        neighbors = adj.get(rid, [])

        for target_id, direction in neighbors:
            if target_id in placed:
                continue
            target = by_id.get(target_id)
            if not target:
                continue

            # Get direction vector
            dx, dy = _DIR_VECTORS.get(direction, (0.5, 0.0))

            # Scale offset — generous spacing for readability
            # Depth 1 rooms get full spread, depth 2 slightly tighter
            depth = target.get("depth", 1)
            scale = 0.35 if depth <= 1 else 0.22

            target["x"] = px + dx * scale
            target["y"] = py + dy * scale

            placed.add(target_id)
            queue.append(target_id)

    # Handle any unplaced rooms (disconnected or "in"/"out" exits)
    unplaced = [r for r in rooms if r["x"] is None]
    if unplaced:
        angle_step = 2 * math.pi / max(len(unplaced), 1)
        for idx, r in enumerate(unplaced):
            angle = idx * angle_step
            r["x"] = 0.5 + 0.15 * math.cos(angle)
            r["y"] = 0.5 + 0.15 * math.sin(angle)

    # Normalize all coordinates to 0.05–0.95 range
    _normalize_coords(rooms)

    # Simple collision avoidance — push overlapping nodes apart
    _resolve_overlaps(rooms, iterations=15)


def _normalize_coords(rooms: list):
    """Normalize room coordinates to fill the 0.05–0.95 range."""
    if not rooms:
        return

    xs = [r["x"] for r in rooms if r["x"] is not None]
    ys = [r["y"] for r in rooms if r["y"] is not None]
    if not xs or not ys:
        return

    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    range_x = max_x - min_x or 1.0
    range_y = max_y - min_y or 1.0

    margin = 0.08
    for r in rooms:
        if r["x"] is not None:
            r["x"] = margin + (r["x"] - min_x) / range_x * (1.0 - 2 * margin)
        if r["y"] is not None:
            r["y"] = margin + (r["y"] - min_y) / range_y * (1.0 - 2 * margin)


def _resolve_overlaps(rooms: list, iterations: int = 15):
    """Push apart rooms that are too close together."""
    min_dist = 0.10  # Minimum normalized distance between nodes

    for _ in range(iterations):
        moved = False
        for i in range(len(rooms)):
            for j in range(i + 1, len(rooms)):
                ri, rj = rooms[i], rooms[j]
                dx = rj["x"] - ri["x"]
                dy = rj["y"] - ri["y"]
                dist = math.sqrt(dx * dx + dy * dy)
                if dist < min_dist and dist > 0.001:
                    # Push apart
                    overlap = (min_dist - dist) / 2.0
                    nx = dx / dist
                    ny = dy / dist
                    ri["x"] -= nx * overlap * 0.5
                    ri["y"] -= ny * overlap * 0.5
                    rj["x"] += nx * overlap * 0.5
                    rj["y"] += ny * overlap * 0.5
                    moved = True
                elif dist < 0.001:
                    # Exactly overlapping — nudge randomly
                    rj["x"] += 0.05
                    rj["y"] += 0.03
                    moved = True
        if not moved:
            break

    # Re-clamp to valid range
    for r in rooms:
        r["x"] = max(0.04, min(0.96, r["x"]))
        r["y"] = max(0.04, min(0.96, r["y"]))


def _reverse_dir(direction: str) -> str:
    """Get the opposite direction for auto-layout reverse edges."""
    opposites = {
        "north": "south", "south": "north",
        "east": "west", "west": "east",
        "northeast": "southwest", "southwest": "northeast",
        "northwest": "southeast", "southeast": "northwest",
        "up": "down", "down": "up",
        "in": "out", "out": "in",
    }
    return opposites.get(direction, direction)
