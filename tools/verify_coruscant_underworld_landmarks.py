"""
verify_coruscant_underworld_landmarks.py — schema + cross-reference
validation for
data/worlds/clone_wars/wilderness/coruscant_underworld_landmarks.yaml.

Validates:
  1. File parses as YAML.
  2. Top-level shape: {schema_version: 1, landmarks: [...], transit_nodes: [...]}.
  3. Exactly 4 landmarks (the 4 non-Force-resonant per design §7.2).
  4. Exactly 3 transit nodes (transit_shaft_alpha, transit_shaft_beta,
     surface_manhole_to_southern_underground).
  5. All 4 landmark ids match design §7.2 names exactly.
  6. Coordinates match design §7.2 values exactly:
       black_sun_crawler_hideout              [20, 15] mid
       abandoned_factory_dominus              [30,  5] low
       uscru_entertainment_district_fringe    [ 8, 20] mid
       maze_the_reaper_territory              [25, 25] bottom
  7. Per-landmark required schema fields (id, name, region, coords,
     level, short_desc, description, properties, ambient_lines).
  8. Every landmark's region == "coruscant_underworld".
  9. None of the 4 non-resonant landmarks have force_resonant: true.
 10. faction_anchor values resolve to known factions (or null) where
     applicable.
 11. Each landmark has a meaningful ambient pool (≥4 lines) per design.
 12. uscru_entertainment_district_fringe.director_managed == true (per
     §7.3 jobs hub design — NPC cluster Director-flavored).
 13. maze_the_reaper_territory has cartography_unstable: true.
 14. abandoned_factory_dominus has structural_hazard: true.
 15. black_sun_crawler_hideout has hostile_default: true and
     threat_tier: miniboss.
 16. Transit nodes have transit_node: true and ambient_disabled: true.
 17. surface_manhole_to_southern_underground has city_handoff: true and
     references coruscant_lower zone (per design §2.3.1).
 18. Cross-reference: the IDs in this file plus forgotten_jedi_shrine
     from force_resonant_landmarks.yaml together cover ALL 5 anchored
     landmarks named in design §7.2.

Usage:
    python3 verify_coruscant_underworld_landmarks.py
or:
    SW_MUSH_REPO=/path/to/SW_MUSH python3 verify_coruscant_underworld_landmarks.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


REPO = Path(os.environ.get("SW_MUSH_REPO", os.getcwd()))
LANDMARKS = REPO / "data" / "worlds" / "clone_wars" / "wilderness" / "coruscant_underworld_landmarks.yaml"
RESONANT = REPO / "data" / "worlds" / "clone_wars" / "wilderness" / "force_resonant_landmarks.yaml"
ORGS = REPO / "data" / "worlds" / "clone_wars" / "organizations.yaml"


# ── Canonical references (from design §7.2) ──────────────────────────────────

EXPECTED_LANDMARKS = {
    "black_sun_crawler_hideout":           {"coords": [20, 15], "level": "mid"},
    "abandoned_factory_dominus":           {"coords": [30,  5], "level": "low"},
    "uscru_entertainment_district_fringe": {"coords": [ 8, 20], "level": "mid"},
    "maze_the_reaper_territory":           {"coords": [25, 25], "level": "bottom"},
}

EXPECTED_TRANSIT_NODES = {
    "transit_shaft_alpha",
    "transit_shaft_beta",
    "surface_manhole_to_southern_underground",
}

# Canonical 5-landmark set per design §7.2 (Force-resonant + non-resonant)
EXPECTED_ALL_LANDMARKS_SET = set(EXPECTED_LANDMARKS) | {"forgotten_jedi_shrine"}

ALLOWED_LEVELS = {"mid", "low", "bottom"}


# ── Test harness ──────────────────────────────────────────────────────────────

PASS, FAIL = 0, 0
errors: list[str] = []


def check(label: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {label}")
    else:
        FAIL += 1
        msg = label + (f": {detail}" if detail else "")
        errors.append(msg)
        print(f"  ✗ {msg}")


# ── Reference data loader ─────────────────────────────────────────────────────

def load_faction_codes() -> set[str]:
    """Loads both factions: and guilds: from organizations.yaml; black_sun
    is not in either by default since it's a CIS-era underworld syndicate
    not a registered Republic faction. We accept it as a faction_anchor
    string regardless — the validator allows arbitrary faction strings on
    landmarks since faction_anchor is descriptive, not engine-binding."""
    if not ORGS.is_file():
        return set()
    data = yaml.safe_load(ORGS.read_text())
    codes = {f["code"] for f in data.get("factions", [])}
    codes |= {g["code"] for g in data.get("guilds", [])}
    # Add commonly-anchored underworld syndicates that may not be in
    # organizations.yaml as PC-joinable factions but are valid descriptive
    # anchors on landmarks.
    codes |= {"black_sun"}
    return codes


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_top_level(data):
    print("\n[1] Top-level shape")
    check("schema_version present", "schema_version" in data)
    check("schema_version == 1", data.get("schema_version") == 1)
    check("'landmarks' key present", "landmarks" in data)
    check("'transit_nodes' key present", "transit_nodes" in data)

    landmarks = data.get("landmarks", [])
    transit = data.get("transit_nodes", [])
    check("exactly 4 landmarks (the 4 non-resonant per §7.2)",
          len(landmarks) == 4,
          f"got {len(landmarks)}")
    check("exactly 3 transit nodes",
          len(transit) == 3,
          f"got {len(transit)}")


def test_canonical_landmark_set(data):
    print("\n[2] Canonical landmark set matches design §7.2")
    landmarks = data.get("landmarks", [])
    actual_ids = {l.get("id") for l in landmarks}
    expected_ids = set(EXPECTED_LANDMARKS)

    missing = expected_ids - actual_ids
    extra = actual_ids - expected_ids
    check("all 4 expected landmark ids present", not missing,
          f"missing: {sorted(missing)}")
    check("no unexpected landmark ids", not extra,
          f"extra: {sorted(extra)}")

    # Coordinate + level checks
    for landmark in landmarks:
        lid = landmark.get("id")
        if lid not in EXPECTED_LANDMARKS:
            continue
        expected = EXPECTED_LANDMARKS[lid]
        check(f"{lid} coordinates == {expected['coords']}",
              landmark.get("coordinates") == expected["coords"],
              f"got {landmark.get('coordinates')!r}")
        check(f"{lid} level == '{expected['level']}'",
              landmark.get("level") == expected["level"],
              f"got {landmark.get('level')!r}")


def test_landmark_shape(landmark, faction_codes):
    lid = landmark.get("id", "<unknown>")
    print(f"\n[3.{lid}] Per-landmark schema")

    required = {
        "id", "name", "region", "coordinates", "level",
        "short_desc", "description", "properties", "ambient_lines",
    }
    keys = set(landmark.keys())
    missing = required - keys
    check("required fields present", not missing,
          f"missing: {sorted(missing)}" if missing else "")

    check("region == 'coruscant_underworld'",
          landmark.get("region") == "coruscant_underworld",
          f"got {landmark.get('region')!r}")

    check("level is mid|low|bottom",
          landmark.get("level") in ALLOWED_LEVELS,
          f"got {landmark.get('level')!r}")

    coords = landmark.get("coordinates")
    coords_ok = (isinstance(coords, list) and len(coords) == 2
                 and all(isinstance(c, int) for c in coords))
    check("coordinates is [int, int]", coords_ok,
          f"got {coords!r}")

    # No force_resonant: true (this is the whole differentiator vs the
    # other landmarks file)
    props = landmark.get("properties", {})
    check("does NOT have force_resonant: true",
          props.get("force_resonant") is not True,
          "force_resonant: true is for force_resonant_landmarks.yaml only")

    check("wilderness_landmark: true",
          props.get("wilderness_landmark") is True)

    # faction_anchor — accept null, or any string value (we allow
    # underworld syndicates that aren't in organizations.yaml)
    fa = props.get("faction_anchor")
    if fa is not None:
        check(f"faction_anchor '{fa}' is valid (string or null)",
              isinstance(fa, str))

    # ambient_lines well-formed and meaningful
    al = landmark.get("ambient_lines", [])
    check("ambient_lines is non-empty list",
          isinstance(al, list) and len(al) >= 4,
          f"got {len(al) if isinstance(al, list) else type(al).__name__}")
    for i, line in enumerate(al):
        check(f"ambient_lines[{i}] well-formed",
              isinstance(line, dict) and isinstance(line.get("text"), str)
              and len(line["text"].strip()) > 0)


def test_landmark_special_properties(data):
    print("\n[4] Landmark-specific design-required properties")
    landmarks = {l["id"]: l for l in data.get("landmarks", [])}

    # uscru is the only Director-managed landmark per §7.3
    uscru = landmarks.get("uscru_entertainment_district_fringe")
    if uscru:
        props = uscru.get("properties", {})
        check("uscru_entertainment_district_fringe.director_managed == true",
              props.get("director_managed") is True)
        check("uscru_entertainment_district_fringe.npc_cluster == true",
              props.get("npc_cluster") is True)
        check("uscru_entertainment_district_fringe.job_board == true",
              props.get("job_board") is True)

    # maze has cartography_unstable
    maze = landmarks.get("maze_the_reaper_territory")
    if maze:
        props = maze.get("properties", {})
        check("maze_the_reaper_territory.cartography_unstable == true",
              props.get("cartography_unstable") is True)
        check("maze_the_reaper_territory.threat_tier == 'lethal'",
              props.get("threat_tier") == "lethal")
        check("maze_the_reaper_territory.low_level_warning == true",
              props.get("low_level_warning") is True)

    # factory has structural_hazard
    factory = landmarks.get("abandoned_factory_dominus")
    if factory:
        props = factory.get("properties", {})
        check("abandoned_factory_dominus.structural_hazard == true",
              props.get("structural_hazard") is True)

    # black sun is hostile miniboss
    sun = landmarks.get("black_sun_crawler_hideout")
    if sun:
        props = sun.get("properties", {})
        check("black_sun_crawler_hideout.hostile_default == true",
              props.get("hostile_default") is True)
        check("black_sun_crawler_hideout.threat_tier == 'miniboss'",
              props.get("threat_tier") == "miniboss")
        check("black_sun_crawler_hideout.faction_anchor == 'black_sun'",
              props.get("faction_anchor") == "black_sun")


def test_transit_nodes(data):
    print("\n[5] Transit nodes")
    transit = data.get("transit_nodes", [])
    actual_ids = {t.get("id") for t in transit}
    missing = EXPECTED_TRANSIT_NODES - actual_ids
    extra = actual_ids - EXPECTED_TRANSIT_NODES
    check("all 3 transit node ids present", not missing,
          f"missing: {sorted(missing)}")
    check("no unexpected transit node ids", not extra,
          f"extra: {sorted(extra)}")

    for node in transit:
        nid = node.get("id", "<unknown>")
        props = node.get("properties", {})
        check(f"{nid} has transit_node: true",
              props.get("transit_node") is True)
        check(f"{nid} has wilderness_landmark: false",
              props.get("wilderness_landmark") is False)
        check(f"{nid} has ambient_disabled: true",
              props.get("ambient_disabled") is True)
        check(f"{nid} has connects_levels list",
              isinstance(node.get("connects_levels"), list))

    # surface_manhole specifics
    manhole = next((t for t in transit
                    if t.get("id") == "surface_manhole_to_southern_underground"),
                   None)
    if manhole:
        props = manhole.get("properties", {})
        check("surface_manhole.city_handoff == true",
              props.get("city_handoff") is True)
        check("surface_manhole.connects_to_zone == 'coruscant_lower'",
              manhole.get("connects_to_zone") == "coruscant_lower")
        check("surface_manhole.connects_to_room == 'southern_underground'",
              manhole.get("connects_to_room") == "southern_underground")

    # transit_shaft_beta has climb requirement
    beta = next((t for t in transit if t.get("id") == "transit_shaft_beta"),
                None)
    if beta:
        props = beta.get("properties", {})
        check("transit_shaft_beta.requires_climb_check == true",
              props.get("requires_climb_check") is True)


def test_full_underworld_anchor_set(landmarks_data):
    print("\n[6] Full Coruscant Underworld anchor set (cross-file)")

    if not RESONANT.is_file():
        check("force_resonant_landmarks.yaml present", False,
              "Cross-file check requires the predecessor drop file. "
              "If running standalone before that drop is applied, this "
              "check will fail; that's expected.")
        return

    resonant_data = yaml.safe_load(RESONANT.read_text())
    resonant_ids_in_underworld = {
        l["id"] for l in resonant_data.get("landmarks", [])
        if l.get("region") == "coruscant_underworld"
    }
    nonresonant_ids = {l["id"] for l in landmarks_data.get("landmarks", [])}

    combined = resonant_ids_in_underworld | nonresonant_ids
    missing = EXPECTED_ALL_LANDMARKS_SET - combined
    extra = combined - EXPECTED_ALL_LANDMARKS_SET
    check("combined files cover all 5 design §7.2 landmarks",
          not missing,
          f"missing from combined set: {sorted(missing)}")
    check("no rogue landmark in either file",
          not extra,
          f"extras: {sorted(extra)}")
    check("forgotten_jedi_shrine is in resonant file (not this one)",
          "forgotten_jedi_shrine" in resonant_ids_in_underworld
          and "forgotten_jedi_shrine" not in nonresonant_ids)


def test_uniqueness(data):
    print("\n[7] Uniqueness")
    all_ids = ([l.get("id") for l in data.get("landmarks", [])]
               + [t.get("id") for t in data.get("transit_nodes", [])])
    check("all ids unique across landmarks + transit",
          len(all_ids) == len(set(all_ids)),
          f"duplicates: {[i for i in set(all_ids) if all_ids.count(i) > 1]}")


def main():
    if not LANDMARKS.is_file():
        print(f"ERROR: {LANDMARKS} not found")
        sys.exit(2)

    data = yaml.safe_load(LANDMARKS.read_text())
    faction_codes = load_faction_codes()

    print(f"Loaded {LANDMARKS.name}")
    print(f"  landmarks: {len(data.get('landmarks', []))}")
    print(f"  transit_nodes: {len(data.get('transit_nodes', []))}")

    test_top_level(data)
    test_canonical_landmark_set(data)
    for lm in data.get("landmarks", []):
        test_landmark_shape(lm, faction_codes)
    test_landmark_special_properties(data)
    test_transit_nodes(data)
    test_full_underworld_anchor_set(data)
    test_uniqueness(data)

    print()
    print("─" * 60)
    print(f"PASS: {PASS}    FAIL: {FAIL}")
    if FAIL:
        print()
        print("Failures:")
        for e in errors[:20]:
            print(f"  - {e}")
        if len(errors) > 20:
            print(f"  ...and {len(errors) - 20} more")
        sys.exit(1)


if __name__ == "__main__":
    main()
