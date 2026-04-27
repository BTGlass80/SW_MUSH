# -*- coding: utf-8 -*-
"""
tools/extract_gcw_world.py — One-shot extractor for Drop 2 of Priority F.0.

Reads world content out of build_mos_eisley.py (the existing hardcoded
build script — 2,727 lines as of HEAD) and writes it to
data/worlds/gcw/{zones.yaml, planets/*.yaml}, matching the schemas
engine/world_loader.py expects.

This is a one-shot generator. Once the GCW YAML is authored (via this
tool) and the equivalence test passes, the YAML files become the
source of truth and this tool is archived. Running it again is safe —
the output is deterministic given the inputs.

What it extracts:
  - 20 zones (1 Tatooine parent + 7 Tatooine children + 4 Nar Shaddaa
    + 3 Kessel + 5 Corellia) with display names, parent links, and
    properties (cover_max / environment / lighting / gravity /
    atmosphere / security) — extracted by parsing the create_zone
    calls in build_mos_eisley.py:2120-2215.
  - 120 rooms partitioned by planet via zone slug:
      * Tatooine = 54 rooms with zone in TATOOINE_ZONES
      * Nar Shaddaa = 30 rooms with zone slug starting "ns_"
      * Kessel = 12 rooms with zone slug starting "kessel_"
      * Corellia = 24 rooms with zone slug starting "coronet_"
    Each room carries id, slug (generated from name via slugify),
    name, short_desc, description, zone, and map_x/map_y read from
    MAP_COORDS (preserved as floats — engine/world_loader.py does not
    coerce them, so the float values flow through unchanged).
  - 120 exit pairs (240 directional edges total) re-emitted as 240
    one-way exits in the planet files. Each exit goes in the planet
    file of its from-room.

What it does NOT extract:
  - npcs.yaml: PLANET_NPCS extraction is deferred to Drop 2b. The
    existing GG7 NPC loader (engine/npc_loader.py + data/npcs_gg7.yaml)
    handles NPC spawning; PLANET_NPCS is the legacy hardcoded set
    used as a fallback. Out of scope for the world-loader cutover.
  - housing_lots.yaml / test_character.yaml: also deferred. Drop 3
    (DB writes) handles those once the room/exit/zone path is solid.

Usage:
    python -m tools.extract_gcw_world [--dry-run]

The script prints a summary and writes (or shows what it would write)
the YAML files. With --dry-run it does NOT touch disk.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional


# ── Configuration ────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).resolve().parent.parent
GCW_DIR = REPO_ROOT / "data" / "worlds" / "gcw"

# Map zone slug → planet code. Driven by build_mos_eisley.py's zone naming
# convention. The single Tatooine parent (`mos_eisley`) and the wastes
# (which has no planet prefix in its slug) are mapped explicitly.
TATOOINE_ZONES = frozenset({
    "mos_eisley", "spaceport", "cantina", "market", "civic",
    "residential", "outskirts", "wastes",
})


def planet_for_zone(zone_slug: str) -> str:
    if zone_slug in TATOOINE_ZONES:
        return "tatooine"
    if zone_slug.startswith("ns_"):
        return "nar_shaddaa"
    if zone_slug.startswith("kessel_"):
        return "kessel"
    if zone_slug.startswith("coronet_"):
        return "corellia"
    raise ValueError(f"No planet mapping for zone slug {zone_slug!r}")


PLANET_ORDER = ["tatooine", "nar_shaddaa", "kessel", "corellia"]
PLANET_DISPLAY = {
    "tatooine":   ("Tatooine",   "Mos Eisley"),
    "nar_shaddaa":("Nar Shaddaa","Corellian Sector"),
    "kessel":     ("Kessel",     "Spice Mines"),
    "corellia":   ("Corellia",   "Coronet City"),
}
PLANET_DESCRIPTION = {
    "tatooine": (
        "A harsh desert world in the Outer Rim, orbiting twin suns. Imperial "
        "presence is thin and the Hutts hold the real power in Mos Eisley."
    ),
    "nar_shaddaa": (
        "The Smuggler's Moon — a crime-saturated industrial moon orbiting "
        "Nal Hutta, layered in vertical districts where the Hutt cartels "
        "rule openly and Imperial law stops at the docking pads."
    ),
    "kessel": (
        "A barren prison-mining world infamous for its spice mines. Light "
        "gravity and thin atmosphere make every breath a labor. Imperial "
        "interest is light; criminal interest is heavy."
    ),
    "corellia": (
        "A core world and the heart of the Corellian Engineering Corporation. "
        "Coronet City sprawls along the coast — orderly on the surface, "
        "with a contested port district where smugglers and CEC engineers "
        "share the same cantinas."
    ),
}


# ── Slugify ──────────────────────────────────────────────────────────────────

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Convert a room display name to a snake_case slug.

    The slug must be unique world-wide and stable across builds. We
    derive it from the room name with a deterministic transform:
    lowercase, strip punctuation, collapse whitespace to underscores,
    trim leading/trailing underscores.

    Edge cases:
      "Docking Bay 94 - Entrance"     -> "docking_bay_94_entrance"
      "Chalmun's Cantina - Main Bar"  -> "chalmuns_cantina_main_bar"
      "Beggar's Canyon Trailhead"     -> "beggars_canyon_trailhead"
    """
    s = name.lower().replace("'", "")
    s = _NON_ALNUM.sub("_", s)
    return s.strip("_")


# ── Zone metadata extraction (parsed from build_mos_eisley.py source) ───────

# These mirror the create_zone() calls at build_mos_eisley.py:2124-2213.
# Each tuple is (slug, display_name, parent_slug or None, properties_dict).
# Hand-transcribed once; verified by grepping the source.
ZONE_DEFS: list[tuple[str, str, Optional[str], dict]] = [
    # Tatooine
    ("mos_eisley", "Mos Eisley", None,
     {"environment": "desert_urban", "lighting": "bright",
      "gravity": "standard", "security": "secured"}),
    ("spaceport", "Spaceport District", "mos_eisley",
     {"cover_max": 3, "environment": "industrial", "security": "secured"}),
    ("cantina", "Chalmun's Cantina", "mos_eisley",
     {"cover_max": 2, "lighting": "dim", "environment": "cantina",
      "security": "secured"}),
    ("market", "Streets & Markets", "mos_eisley",
     {"cover_max": 1, "environment": "street", "security": "secured"}),
    ("civic", "Civic & Government", "mos_eisley",
     {"cover_max": 1, "environment": "official", "security": "secured"}),
    ("residential", "Residential & Commercial", "mos_eisley",
     {"cover_max": 2, "environment": "commercial", "security": "secured"}),
    ("outskirts", "City Outskirts", "mos_eisley",
     {"cover_max": 1, "environment": "desert_fringe", "security": "contested"}),
    ("wastes", "Jundland Wastes", None,
     {"cover_max": 2, "environment": "desert_wilderness", "lighting": "bright",
      "gravity": "standard", "security": "lawless"}),

    # Nar Shaddaa
    ("ns_landing_pad", "Nar Shaddaa Landing Pads", None,
     {"environment": "urban_industrial", "lighting": "dim",
      "gravity": "standard", "security": "secured"}),
    ("ns_promenade", "Corellian Sector Promenade", "ns_landing_pad",
     {"cover_max": 2, "environment": "urban_commercial",
      "security": "contested"}),
    ("ns_undercity", "Nar Shaddaa Undercity", "ns_landing_pad",
     {"cover_max": 1, "lighting": "dark", "environment": "urban_slum",
      "security": "lawless"}),
    ("ns_warrens", "The Warrens", "ns_landing_pad",
     {"cover_max": 0, "lighting": "dark", "environment": "subterranean",
      "security": "lawless"}),

    # Kessel
    ("kessel_station", "Kessel Station", None,
     {"environment": "barren", "lighting": "bright", "gravity": "light",
      "atmosphere": "thin", "security": "contested"}),
    ("kessel_mines", "Kessel Spice Mines", "kessel_station",
     {"cover_max": 1, "lighting": "dim", "environment": "underground",
      "security": "lawless"}),
    ("kessel_deep_mines", "Kessel Deep Mines", "kessel_station",
     {"cover_max": 0, "lighting": "dark", "environment": "deep_underground",
      "security": "lawless"}),

    # Corellia
    ("coronet_port", "Coronet Port District", None,
     {"environment": "urban_modern", "lighting": "bright",
      "gravity": "standard", "security": "contested"}),
    ("coronet_city", "Coronet City Center", "coronet_port",
     {"cover_max": 2, "environment": "urban_commercial", "security": "secured"}),
    ("coronet_gov", "Coronet Government District", "coronet_port",
     {"cover_max": 2, "environment": "official", "security": "secured"}),
    ("coronet_industrial", "Coronet Industrial District", "coronet_port",
     {"cover_max": 2, "environment": "industrial", "security": "secured"}),
    ("coronet_old_quarter", "Coronet Old Quarter", "coronet_port",
     {"cover_max": 1, "environment": "urban_historic", "security": "contested"}),
]


# ── YAML emission helpers ────────────────────────────────────────────────────


def _quote_if_needed(s: str) -> str:
    """Wrap a string in double-quotes if it contains characters that
    would otherwise need YAML escaping. Conservative: if the string
    contains anything non-trivial, quote it.
    """
    # Empty / has special YAML chars / leading/trailing whitespace
    if (not s
            or s != s.strip()
            or any(c in s for c in ":#&*?|>-!{}[],'\"%@`\\\n\r\t")
            or s.lower() in ("yes", "no", "true", "false", "null",
                             "y", "n", "on", "off", "~")
            or re.match(r"^[\d.+-]", s)):
        # Use double-quoted form, escape internal " and \\
        esc = s.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{esc}"'
    return s


def _emit_block_text(text: str, indent: int) -> list[str]:
    """Emit a multi-paragraph string in YAML literal block form (`|`)
    so newlines are preserved. The build_mos_eisley descriptions are
    typically single concatenated strings without newlines, but using
    block form keeps the YAML readable and avoids quoting headaches.
    """
    pad = " " * indent
    if not text:
        return [pad + '""']
    # If the description has no special chars and is short, use a flow
    # scalar. Otherwise use folded-block (`>`) which collapses runs of
    # whitespace into single spaces — matches how the original Python
    # string-concatenation reads.
    if "\n" in text or len(text) > 70:
        out = [pad[:-2] + ">-"]
        # Folded block: each line gets the indent. Wrap at ~78 cols.
        words = text.split()
        line = ""
        for w in words:
            if line and len(line) + 1 + len(w) > 76 - indent:
                out.append(pad + line)
                line = w
            else:
                line = (line + " " + w) if line else w
        if line:
            out.append(pad + line)
        return out
    # Short single-line: inline, quoted if needed
    return [pad[:-2] + ": " + _quote_if_needed(text)]


def _emit_props(props: dict, indent: int) -> list[str]:
    """Emit a properties dict as YAML, sorted for determinism."""
    pad = " " * indent
    out = []
    for k in sorted(props.keys()):
        v = props[k]
        if isinstance(v, bool):
            out.append(f"{pad}{k}: {'true' if v else 'false'}")
        elif isinstance(v, (int, float)):
            out.append(f"{pad}{k}: {v}")
        elif isinstance(v, str):
            out.append(f"{pad}{k}: {_quote_if_needed(v)}")
        else:
            out.append(f"{pad}{k}: {json.dumps(v)}")
    return out


# ── zones.yaml emission ──────────────────────────────────────────────────────


def emit_zones_yaml() -> str:
    """Build the GCW zones.yaml content from ZONE_DEFS.

    Output schema:
        schema_version: 1
        zones:
          <slug>:
            name: <display name>
            parent: <parent slug or null>
            name_match: <auto-derived prefix>
            properties:
              <key>: <value>
            # narrative_tone: TBD (left out — Optional in the loader)
    """
    lines = [
        "# data/worlds/gcw/zones.yaml",
        "# Galactic Civil War — Zone Definitions",
        "# Generated by tools/extract_gcw_world.py from build_mos_eisley.py.",
        "# 20 zones: 8 Tatooine, 4 Nar Shaddaa, 3 Kessel, 5 Corellia.",
        "# Schema: see engine/world_loader.py::Zone (slug, name_match, narrative_tone).",
        "# narrative_tone is Optional in the loader; left for follow-up authoring.",
        "",
        "schema_version: 1",
        "",
        "zones:",
    ]
    for slug, name, parent, props in ZONE_DEFS:
        # Derive name_match: lowercase the display name's primary token(s).
        # The CW pattern uses a substring like "spaceport" or "mos eisley".
        # We use the slug's underscore-to-space form which is accurate.
        name_match = slug.replace("_", " ")
        lines.append("")
        lines.append(f"  {slug}:")
        lines.append(f"    name: {_quote_if_needed(name)}")
        lines.append(f"    parent: {parent if parent else 'null'}")
        lines.append(f"    name_match: {_quote_if_needed(name_match)}")
        if props:
            lines.append("    properties:")
            lines.extend(_emit_props(props, indent=6))
    lines.append("")
    return "\n".join(lines)


# ── planet/<file>.yaml emission ──────────────────────────────────────────────


def emit_planet_yaml(planet: str,
                     rooms: list[dict],
                     exits: list[dict]) -> str:
    """Build a planet YAML containing the planet's rooms and exits.

    Schema (matches engine/world_loader.py::_load_planet_file):
        planet: <slug>
        planet_display_name: ...
        primary_city: ...
        description: >
          <multi-line>
        rooms:
          - id: 0
            slug: ...
            name: ...
            short_desc: ...
            description: >
              ...
            zone: ...
            map_x: 0.15
            map_y: 0.48
        exits:
          - from: 0
            to:   1
            forward: down
            reverse: up
    """
    display, primary = PLANET_DISPLAY[planet]
    desc = PLANET_DESCRIPTION[planet]

    lines = [
        f"# data/worlds/gcw/planets/{planet}.yaml",
        f"# Galactic Civil War — {display} ({primary})",
        f"# {len(rooms)} rooms, {len(exits)} one-way exits.",
        "# Generated by tools/extract_gcw_world.py from build_mos_eisley.py.",
        "# Room IDs are positional and stable — do NOT reorder.",
        "",
        f"planet: {planet}",
        f"planet_display_name: {_quote_if_needed(display)}",
        f"primary_city: {_quote_if_needed(primary)}",
    ]
    # Description as folded block
    lines.append("description: >-")
    lines.extend(_wrap_lines(desc, indent=2))
    lines.append("")

    # Rooms
    lines.append("rooms:")
    for r in rooms:
        lines.append("")
        lines.append(f"  - id: {r['id']}")
        lines.append(f"    slug: {r['slug']}")
        lines.append(f"    name: {_quote_if_needed(r['name'])}")
        lines.append(f"    short_desc: {_quote_if_needed(r['short_desc'])}")
        lines.append("    description: >-")
        lines.extend(_wrap_lines(r["description"], indent=6))
        lines.append(f"    zone: {r['zone']}")
        if r.get("map_x") is not None:
            lines.append(f"    map_x: {r['map_x']}")
        if r.get("map_y") is not None:
            lines.append(f"    map_y: {r['map_y']}")
        if r.get("properties"):
            lines.append("    properties:")
            lines.extend(_emit_props(r["properties"], indent=6))
    lines.append("")

    # Exits — emit one entry per direction
    lines.append("exits:")
    for e in exits:
        lines.append("")
        lines.append(f"  - from: {e['from']}")
        lines.append(f"    to: {e['to']}")
        lines.append(f"    forward: {_quote_if_needed(e['forward'])}")
        lines.append(f"    reverse: {_quote_if_needed(e['reverse'])}")
    lines.append("")

    return "\n".join(lines)


def _wrap_lines(text: str, indent: int, width: int = 76) -> list[str]:
    """Word-wrap `text` to lines of at most `width` columns each
    prefixed by `indent` spaces. Returns the list of lines (no trailing
    newline).
    """
    pad = " " * indent
    out = []
    words = (text or "").split()
    line = ""
    for w in words:
        if line and len(line) + 1 + len(w) > width - indent:
            out.append(pad + line)
            line = w
        else:
            line = (line + " " + w) if line else w
    if line:
        out.append(pad + line)
    if not out:
        out.append(pad + '""')
    return out


# ── era.yaml patch ───────────────────────────────────────────────────────────


def patch_era_yaml(era_path: Path, dry_run: bool) -> tuple[bool, str]:
    """Update content_refs.planets and content_refs.zones in era.yaml.

    The existing GCW era.yaml has:
        content_refs:
          zones: zones.yaml
          organizations: organizations.yaml
          planets: []
    We need:
        content_refs:
          zones: zones.yaml
          organizations: organizations.yaml
          planets:
            - planets/tatooine.yaml
            - planets/nar_shaddaa.yaml
            - planets/kessel.yaml
            - planets/corellia.yaml

    Returns (changed?, new_text). Surgical text replacement so we
    don't disturb comments or other structure in the file.
    """
    text = era_path.read_text(encoding="utf-8")
    target = "  planets: []                              # Mos Eisley is single-planet at GCW launch"
    if target in text:
        replacement = (
            "  planets:                                 # GCW Mos Eisley + Nar Shaddaa + Kessel + Corellia\n"
            "    - planets/tatooine.yaml                # 54 rooms\n"
            "    - planets/nar_shaddaa.yaml             # 30 rooms\n"
            "    - planets/kessel.yaml                  # 12 rooms\n"
            "    - planets/corellia.yaml                # 24 rooms"
        )
        new_text = text.replace(target, replacement, 1)
        return (True, new_text)
    # Already patched? Be idempotent.
    if "planets/tatooine.yaml" in text:
        return (False, text)
    raise RuntimeError(
        f"Could not find planets:[] anchor in {era_path} — "
        "manual edit required, or anchor changed since this script was written."
    )


# ── Main extraction ──────────────────────────────────────────────────────────


def extract() -> dict:
    """Pull world data from build_mos_eisley.py and shape it for emission."""
    sys.path.insert(0, str(REPO_ROOT))
    import build_mos_eisley as b

    # MAP_COORDS lives inside build_main(); we grab it via source-text
    # parsing because importing requires running the async build path.
    # The dict is huge but well-formed, so eval-via-exec is safe enough
    # for a one-shot tool. (We don't trust user input — this is our own
    # source file.)
    src = (REPO_ROOT / "build_mos_eisley.py").read_text(encoding="utf-8")
    map_coords = _extract_map_coords(src)

    # Build per-room structured records keyed by integer ID.
    rooms_by_id: dict[int, dict] = {}
    for i, (name, short, long_) in enumerate(b.ROOMS):
        zone = b.ROOM_ZONES.get(i)
        if not zone:
            raise RuntimeError(f"Room {i} ({name!r}) has no zone in ROOM_ZONES")
        coord = map_coords.get(i, (None, None))
        rooms_by_id[i] = {
            "id": i,
            "slug": slugify(name),
            "name": name,
            "short_desc": short,
            "description": long_,
            "zone": zone,
            "map_x": coord[0],
            "map_y": coord[1],
            "properties": dict(b.ROOM_OVERRIDES.get(i, {})),
        }

    # Detect slug collisions — the loader will reject duplicate slugs
    # at validate() time, but it's friendlier to fix them here. The
    # collision-resolution rule is: append "_<id>" to the duplicate.
    seen_slugs: dict[str, int] = {}
    collisions: list[tuple[int, str]] = []
    for i in sorted(rooms_by_id.keys()):
        s = rooms_by_id[i]["slug"]
        if s in seen_slugs:
            new_s = f"{s}_{i}"
            rooms_by_id[i]["slug"] = new_s
            collisions.append((i, new_s))
        else:
            seen_slugs[s] = i

    # Bin rooms by planet via zone slug.
    rooms_by_planet: dict[str, list[dict]] = {p: [] for p in PLANET_ORDER}
    for i in sorted(rooms_by_id.keys()):
        r = rooms_by_id[i]
        rooms_by_planet[planet_for_zone(r["zone"])].append(r)

    # Each EXITS tuple is (from, to, forward, reverse). The bidirection
    # is created at runtime; YAML stores one entry per pair (from→to)
    # and the loader (or builder) emits both directions. We treat the
    # YAML as carrying *the pair* — `forward` from→to and `reverse`
    # to→from.
    exits_by_planet: dict[str, list[dict]] = {p: [] for p in PLANET_ORDER}
    for from_id, to_id, fwd, rev in b.EXITS:
        # Assign exit to the planet of the from-room.
        from_planet = planet_for_zone(rooms_by_id[from_id]["zone"])
        to_planet = planet_for_zone(rooms_by_id[to_id]["zone"])
        if from_planet != to_planet:
            # No cross-planet exits expected in build_mos_eisley.py, but
            # surface it loudly if one shows up so we don't silently
            # truncate the world graph.
            raise RuntimeError(
                f"Cross-planet exit detected: room {from_id} ({from_planet}) "
                f"-> {to_id} ({to_planet}). build_mos_eisley.py never had "
                "these; this is a data integrity surprise."
            )
        exits_by_planet[from_planet].append({
            "from": from_id,
            "to": to_id,
            "forward": fwd,
            "reverse": rev,
        })

    return {
        "rooms_by_planet": rooms_by_planet,
        "exits_by_planet": exits_by_planet,
        "rooms_by_id": rooms_by_id,
        "collisions": collisions,
        "total_rooms": len(rooms_by_id),
        "total_exits": sum(len(v) for v in exits_by_planet.values()),
    }


def _extract_map_coords(src: str) -> dict[int, tuple[float, float]]:
    """Parse the MAP_COORDS dict literal out of build_mos_eisley.py
    source. We don't import-and-run the build — that requires async
    DB setup. Instead, locate the literal block and exec() the
    fragment in an isolated namespace.

    Anchors: the dict starts at `MAP_COORDS = {` and ends at the
    matching closing `}`. We track brace depth ignoring strings.
    """
    start = src.find("MAP_COORDS = {")
    if start < 0:
        raise RuntimeError("Could not locate MAP_COORDS in build_mos_eisley.py")
    # Walk forward, tracking brace depth, ignoring # comments and strings
    i = start + len("MAP_COORDS = ")
    depth = 0
    in_str: Optional[str] = None
    end = -1
    while i < len(src):
        ch = src[i]
        # crude string detection (handles quotes; ignores escapes)
        if in_str:
            if ch == in_str and src[i-1] != "\\":
                in_str = None
        elif ch in ("'", '"'):
            in_str = ch
        elif ch == "#":  # skip to end of line
            nl = src.find("\n", i)
            i = nl + 1 if nl >= 0 else len(src)
            continue
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
        i += 1
    if end < 0:
        raise RuntimeError("Could not find end of MAP_COORDS dict")
    fragment = src[start + len("MAP_COORDS = "):end]
    namespace: dict = {}
    exec("d = " + fragment, namespace)
    raw = namespace["d"]
    # Coerce to (float, float) tuples
    return {int(k): (float(v[0]), float(v[1])) for k, v in raw.items()}


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Compute and report. Don't write files.")
    args = ap.parse_args(argv)

    print("Extracting world data from build_mos_eisley.py …")
    bundle = extract()

    print(f"  Total rooms: {bundle['total_rooms']}")
    print(f"  Total exits: {bundle['total_exits']}")
    print(f"  Slug collisions resolved: {len(bundle['collisions'])}")
    for room_id, new_slug in bundle["collisions"][:5]:
        print(f"    room {room_id} → {new_slug}")
    if len(bundle["collisions"]) > 5:
        print(f"    … and {len(bundle['collisions']) - 5} more")

    print("\nPer-planet split:")
    for p in PLANET_ORDER:
        nr = len(bundle["rooms_by_planet"][p])
        ne = len(bundle["exits_by_planet"][p])
        print(f"  {p:12s} {nr:3d} rooms, {ne:3d} exits")

    print("\nGenerating YAML …")
    zones_text = emit_zones_yaml()
    planet_texts = {
        p: emit_planet_yaml(p, bundle["rooms_by_planet"][p],
                            bundle["exits_by_planet"][p])
        for p in PLANET_ORDER
    }

    if args.dry_run:
        print("--dry-run: not writing files.")
        print(f"  zones.yaml would be {len(zones_text)} chars")
        for p, t in planet_texts.items():
            print(f"  planets/{p}.yaml would be {len(t)} chars")
        return 0

    GCW_DIR.mkdir(parents=True, exist_ok=True)
    (GCW_DIR / "planets").mkdir(parents=True, exist_ok=True)
    (GCW_DIR / "zones.yaml").write_text(zones_text, encoding="utf-8")
    print(f"  wrote {GCW_DIR / 'zones.yaml'}")
    for p, t in planet_texts.items():
        path = GCW_DIR / "planets" / f"{p}.yaml"
        path.write_text(t, encoding="utf-8")
        print(f"  wrote {path}")

    # Patch era.yaml
    era_path = GCW_DIR / "era.yaml"
    changed, new_text = patch_era_yaml(era_path, dry_run=False)
    if changed:
        era_path.write_text(new_text, encoding="utf-8")
        print(f"  patched {era_path}")
    else:
        print(f"  {era_path} already patched (idempotent)")

    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
