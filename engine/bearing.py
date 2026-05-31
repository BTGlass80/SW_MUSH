"""
engine/bearing.py — Phase-1 substrate: player/PC facing for the map markers
============================================================================
The SPA map draws the player (and other PCs) as a chevron rotated by a
``bearing`` in degrees (see static/spa/m3_assets_markers.js: the chevron
"points up before the rotate(bearing) is applied", and SVG ``rotate()`` is
clockwise). The adapter has long defaulted bearing to 0 with the note
"Server emits no bearing. Phase-1-protocol-substrate scope." This module is
that source.

Facing is derived from the direction of the player's **last successful move**:
walk ``north`` and your chevron points up; walk ``east`` and it points right.
No new player command, no facing simulation — just the move they already made.

Coordinate contract (verified against the renderer)
---------------------------------------------------
Map world data is y-up (north = +y; tools/check_map_cardinals.py uses
``DIR_ANGLE["north"] = 90`` over ``atan2(dy, dx)``). The adapter reflects that
into SVG screen space with ``flipY(y) = (y_min + y_max) - y`` — a pure
reflection, so **north renders visually up**, which is the chevron's 0°.
Therefore bearing is screen-space degrees clockwise from up:

    north 0 · northeast 45 · east 90 · southeast 135
    south 180 · southwest 225 · west 270 · northwest 315

Non-planar moves (``up``/``down``/``in``/``out``/``enter``/``back``/named
exits) have no meaningful compass facing — these return ``None`` so the caller
**keeps the previous bearing** rather than snapping the chevron to a wrong
angle (you took a turbolift; you're still facing the way you were).
"""
from __future__ import annotations

from typing import Optional

# Canonical compass word → screen-space degrees (0 = up = north, clockwise).
# Keys are the canonical exit ``direction`` values stored in the DB / world
# YAML (already de-abbreviated by the exit match, so no "n"/"ne" here).
_BEARING_DEGREES = {
    "north": 0,
    "northeast": 45,
    "east": 90,
    "southeast": 135,
    "south": 180,
    "southwest": 225,
    "west": 270,
    "northwest": 315,
}

# Abbreviations, accepted defensively in case a caller passes raw input rather
# than the matched exit's canonical ``direction``.
_ABBREV = {
    "n": "north", "ne": "northeast", "e": "east", "se": "southeast",
    "s": "south", "sw": "southwest", "w": "west", "nw": "northwest",
}


def bearing_for_direction(direction: Optional[str]) -> Optional[int]:
    """Screen-space degrees for a compass ``direction``, or ``None`` for a
    non-planar / unrecognized move (caller should keep the prior bearing).

    Pass the matched exit's canonical ``direction`` (e.g. ``"north"``);
    abbreviations (``"n"``) are tolerated too.
    """
    if not direction:
        return None
    d = direction.strip().lower()
    d = _ABBREV.get(d, d)
    return _BEARING_DEGREES.get(d)


def is_planar_direction(direction: Optional[str]) -> bool:
    """True when ``direction`` maps to a compass facing (so a bearing exists)."""
    return bearing_for_direction(direction) is not None
