#!/usr/bin/env python3
"""
paint_brief_common.py — shared core for generating Nano/Gemini paint briefs
from game data (Drop 4.18).

WHY
---
A painted map substrate is only as faithful as the PROMPT that produced it.
The seed image carries the spatial layout, but img2img models (Gemini 2.5
Flash Image / "Nano Banana") REFLOW unless the words reinforce position. They
have NO numeric spatial addressing — "obelisk at (97, 79)" is noise to them.
What they obey is the seed image plus RELATIVE language ("upper-left",
"eastern third"), DENSITY cues, and vivid visual nouns.

So we generate the prompt from the same projected data that built the seed:
  · placement clause   — relative regions per landmark (from projected pos)
  · per-feature visual — pulled from the authored short_desc/description
  · density / texture  — where features concentrate, from the real coords
All three trace to one source, so the prompt cannot drift from the grid any
more than the seed can. This module holds the domain-agnostic primitives; the
wilderness and city generators supply their own data and call these.

CANONICAL MASTER PROMPT
-----------------------
MASTER_PROMPT below is the single source of the style wrapper (NANO_MAP_PACKAGE
§2.5 now points here). Callers fill {ASPECT} and {GEOGRAPHY}.
"""
from __future__ import annotations

import math
import re

# ── the style wrapper (single source; §2.5 references this) ───────────────
MASTER_PROMPT = """\
Concept art / environment plate for the map screen of a science-fantasy
role-playing game. BASE LAYER ONLY. The image must contain absolutely NO
TEXT of any kind — no labels, letters, numbers, signs, legend, or compass
markings. Names are composited later; a clean text-free plate is the point.

Use the attached base image as the EXACT, FIXED spatial layout. Preserve the
composition precisely — do NOT reflow, rescale, rearrange, or re-proportion
anything. Specifically:
  - the bright lines are the main roads/routes: keep them running exactly
    where they are;
  - each solid colored region is a zone: keep its position, size and shape,
    repainting it as ground/terrain of the character described;
  - the large GOLD blocks mark key features that MUST be clearly visible:
    paint a distinct feature of the type described on that exact spot;
  - the faint pale rectangles are background density: render them as ordinary
    structures filling that area — do NOT make each one a distinct landmark;
  - any marker at the very edge is an off-map direction, NOT a building.

Style: hand-painted tabletop-RPG sourcebook cartography — painterly,
weathered, warm and tactile, like a printed campaign atlas. Top-down with a
gentle ~10-15 degree oblique tilt so structures show a little height.
Cohesive limited palette. Render at {ASPECT} aspect ratio, filling the frame
edge to edge.

Setting: a lived-in, used-future space-opera world. Low-tech, weathered,
functional. No modern Earth elements, no automobiles, no contemporary
signage, no soldiers or uniformed troops, no franchise iconography.

{GEOGRAPHY}

Final reminders: NO TEXT anywhere — no labels, legend, compass letters, grid,
numbers, title, signature, watermark, or border. Clean painterly terrain to
every edge."""


def aspect_phrase(bounds: dict) -> str:
    """'1.167:1' from overview bounds."""
    w = float(bounds["x_max"]) - float(bounds["x_min"])
    h = float(bounds["y_max"]) - float(bounds["y_min"])
    if h <= 0:
        return "1:1"
    r = w / h
    return f"{r:.3f}".rstrip("0").rstrip(".") + ":1"


# ── relative placement language ───────────────────────────────────────────
_COLS = ["left", "center", "right"]
_ROWS = ["upper", "middle", "lower"]   # y-DOWN: row 0 = top = upper


def relative_region(ox: float, oy: float, W: float, H: float,
                    edge_frac: float = 0.07) -> str:
    """Map an overview position to a painter-friendly relative phrase, e.g.
    'upper-left', 'center', 'right edge mid-height', 'far-west edge'.

    Edge points (within edge_frac of a border) read as off-map directions —
    important so a region exit isn't painted as a central feature."""
    fx = ox / W if W else 0.5
    fy = oy / H if H else 0.5
    near_left = fx <= edge_frac
    near_right = fx >= 1 - edge_frac
    near_top = fy <= edge_frac
    near_bot = fy >= 1 - edge_frac

    # explicit edges first (off-map directions)
    if near_left and not (near_top or near_bot):
        return "far-west edge, mid-height"
    if near_right and not (near_top or near_bot):
        return "far-east edge, mid-height"
    if near_top and not (near_left or near_right):
        return "top edge, center"
    if near_bot and not (near_left or near_right):
        return "bottom edge, center"
    if near_left and near_top:
        return "top-left corner"
    if near_right and near_top:
        return "top-right corner"
    if near_left and near_bot:
        return "bottom-left corner"
    if near_right and near_bot:
        return "bottom-right corner"

    col = _COLS[min(2, int(fx * 3))]
    row = _ROWS[min(2, int(fy * 3))]
    if row == "middle" and col == "center":
        return "center"
    if row == "middle":
        return f"{col} of center"
    if col == "center":
        return f"{row}-center"
    return f"{row}-{col}"


def placement_clause(nodes: list[dict], W: float, H: float,
                     edge_frac: float = 0.07) -> str:
    """'Placement (paint each on its gold block): THE HIDDEN VILLAGE center;
    RUINED OBELISK top-left; ...' — landmarks first, exits last. An exit near
    a frame border reads as an off-map direction (paint a road leaving the
    frame); an exit in the interior reads as an in-place access point (a
    stair/shaft/manhole), since it isn't a direction off the edge."""
    landmarks, exits = [], []
    for n in nodes:
        pos = n.get("pos") or [n.get("x"), n.get("y")]
        phrase = relative_region(pos[0], pos[1], W, H, edge_frac)
        if n.get("kind") == "exit":
            fx, fy = pos[0] / W, pos[1] / H
            on_edge = (fx <= edge_frac or fx >= 1 - edge_frac
                       or fy <= edge_frac or fy >= 1 - edge_frac)
            # an explicit off-map marker (e.g. a "↗" in the name) is a
            # leaving-frame direction even if its coordinate is interior.
            if on_edge or n.get("offmap"):
                exits.append(f"{n['name']} toward the {phrase} (an off-map "
                             f"direction — paint only a road/trail leaving the "
                             f"frame that way, not a structure)")
            else:
                exits.append(f"{n['name']} at {phrase} (a small access point — "
                             f"a stairwell/shaft/manhole down or up, not a landmark)")
        else:
            landmarks.append(f"{n['name']} {phrase}")
    out = ""
    if landmarks:
        out += "Placement — paint each named feature ON its gold block, nowhere else: " \
               + "; ".join(landmarks) + "."
    if exits:
        out += " Access markers: " + "; ".join(exits) + "."
    return out


# ── flavor extraction (option a, enriched) ────────────────────────────────
_NARRATIVE_TAILS = re.compile(
    r"\b(keeps the watch|leads the|used for|where the|someone wanted|"
    r"the tusken|sister |master |smith |brother |elder )", re.I)


def visual_from_desc(short_desc: str | None, description: str | None) -> str:
    """The paintable sentence for a feature: prefer short_desc, trimmed of
    non-visual narrative (proper-name duties, lore asides). Falls back to the
    first sentence of the long description. Returns '' if nothing usable."""
    text = (short_desc or "").strip()
    if not text and description:
        text = description.strip().replace("\n", " ")
        text = text.split(". ")[0]
    if not text:
        return ""
    # trim an em-dash / semicolon narrative tail ("…defaced — someone wanted…")
    for sep in (" — ", "—", "; "):
        if sep in text:
            head = text.split(sep)[0].strip()
            if len(head) >= 12:
                text = head
                break
    # drop a trailing narrative sentence if a clean visual one precedes it
    parts = [p.strip() for p in re.split(r"(?<=[.!])\s+", text) if p.strip()]
    if len(parts) > 1:
        keep = [p for p in parts if not _NARRATIVE_TAILS.search(p)]
        if keep:
            text = " ".join(keep)
    text = text.rstrip(". ").strip()
    return text


# ── density / concentration phrasing ──────────────────────────────────────
def coarse_region_phrase(points: list[tuple[float, float]], W: float, H: float) -> str:
    """Where a set of overview points concentrates, in painter language:
    'concentrated in the eastern third', 'spread across the map', 'along the
    southern edge'. Used for terrain/feature density derived from real coords."""
    if not points:
        return "spread thinly"
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    cx = sum(xs) / len(xs) / W
    cy = sum(ys) / len(ys) / H
    spanx = (max(xs) - min(xs)) / W
    spany = (max(ys) - min(ys)) / H
    # tight cluster → name the third it sits in
    if spanx < 0.45 and spany < 0.6:
        ew = "eastern" if cx > 0.62 else ("western" if cx < 0.38 else "central")
        ns = "northern" if cy < 0.38 else ("southern" if cy > 0.62 else "")
        where = (f"{ns}-{ew}".strip("-") if ns else ew)
        return f"concentrated in the {where} part of the map"
    if spanx > 0.7 and spany > 0.7:
        return "spread across the whole map"
    if spany < 0.35:
        band = "northern" if cy < 0.5 else "southern"
        return f"strung along the {band} half"
    if spanx < 0.35:
        band = "western" if cx < 0.5 else "eastern"
        return f"strung along the {band} half"
    return "loosely spread"


def cardinal_word(ox: float, oy: float, W: float, H: float) -> str:
    """Coarse compass word for a single point (N at top, y-down)."""
    fx, fy = ox / W, oy / H
    ns = "north" if fy < 0.4 else ("south" if fy > 0.6 else "")
    ew = "east" if fx > 0.6 else ("west" if fx < 0.4 else "")
    return (ns + ew) or "central"
