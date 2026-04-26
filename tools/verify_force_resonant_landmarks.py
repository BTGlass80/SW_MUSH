"""
verify_force_resonant_landmarks.py — schema + cross-reference validation
for data/worlds/clone_wars/wilderness/force_resonant_landmarks.yaml.

Validates:
  1. File parses as YAML.
  2. Top-level shape: {schema_version: 1, landmarks: [...]}.
  3. Each landmark has: id, name, region, coordinates, short_desc,
     description, properties, ambient_lines.
  4. coordinates is [int, int].
  5. properties.force_resonant == true (this is the whole point of the file).
  6. properties.wilderness_landmark == true.
  7. ambient_lines is non-empty list of {text: str} dicts.
  8. Region is one of the known wilderness regions.
  9. Cross-reference: every landmark id in this file is referenced by
     jedi_village.yaml force_sign_seeds[shrine_entry].rooms — and every
     id in that list resolves to a landmark in this file.
 10. Special-case fields: dune_sea_anchor_stones has
     village_quest_anchor: true.

Usage:
    python3 verify_force_resonant_landmarks.py
or:
    SW_MUSH_REPO=/path/to/SW_MUSH python3 verify_force_resonant_landmarks.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml


REPO = Path(os.environ.get("SW_MUSH_REPO", os.getcwd()))
LANDMARKS = REPO / "data" / "worlds" / "clone_wars" / "wilderness" / "force_resonant_landmarks.yaml"
VILLAGE = REPO / "data" / "worlds" / "clone_wars" / "quests" / "jedi_village.yaml"

# Wilderness regions — must match those used in the wilderness system.
# Region names are author-side conventions; the engine uses them to
# route landmarks into the correct wilderness coordinate grid.
KNOWN_REGIONS = {
    "coruscant_underworld",
    "tatooine_dune_sea",
    "tatooine_jundland",
    "tatooine_outer_wastes",          # potential future region
    "kashyyyk_canopy",                # potential future region
}

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


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_top_level(data):
    print("\n[1] Top-level shape")
    check("schema_version present", "schema_version" in data)
    check("schema_version == 1", data.get("schema_version") == 1)
    check("'landmarks' key present", "landmarks" in data)
    landmarks = data.get("landmarks", [])
    check("landmarks is a list", isinstance(landmarks, list))
    check("at least 4 landmarks (per Village design §3.1)",
          len(landmarks) >= 4,
          f"got {len(landmarks)}")


def test_landmark_shape(landmark, idx):
    lid = landmark.get("id", f"<#{idx}>")
    label = f"landmark[{idx}] ({lid})"
    print(f"\n[2.{idx}] {label}")

    required = {
        "id", "name", "region", "coordinates",
        "short_desc", "description", "properties", "ambient_lines",
    }
    keys = set(landmark.keys())
    missing = required - keys
    check("all required fields present", not missing,
          f"missing: {sorted(missing)}" if missing else "")

    # coordinates is [int, int]
    coords = landmark.get("coordinates")
    coords_ok = (isinstance(coords, list) and len(coords) == 2
                 and all(isinstance(c, int) for c in coords))
    check("coordinates is [int, int]", coords_ok,
          f"got {coords!r}")

    # region is known
    region = landmark.get("region")
    check(f"region '{region}' is known",
          region in KNOWN_REGIONS,
          f"not in {sorted(KNOWN_REGIONS)}")

    # properties checks
    props = landmark.get("properties", {})
    check("properties.force_resonant is true",
          props.get("force_resonant") is True,
          f"got {props.get('force_resonant')!r}")
    check("properties.wilderness_landmark is true",
          props.get("wilderness_landmark") is True,
          f"got {props.get('wilderness_landmark')!r}")
    check("properties.director_managed is false",
          props.get("director_managed") is False,
          f"got {props.get('director_managed')!r}")

    # ambient_lines non-empty list of {text: str}
    al = landmark.get("ambient_lines", [])
    check("ambient_lines is non-empty",
          isinstance(al, list) and len(al) >= 3,
          f"got {len(al) if isinstance(al, list) else type(al).__name__}")
    for i, line in enumerate(al):
        check(f"ambient_lines[{i}] is {{text: str}}",
              isinstance(line, dict) and isinstance(line.get("text"), str)
              and len(line["text"].strip()) > 0,
              f"got {line!r}")


def test_cross_reference_with_village(landmarks_data, village_data):
    print("\n[3] Cross-reference with jedi_village.yaml")

    # Every landmark id in our file must appear in the Village's
    # force_sign_seeds for shrine_entry.
    landmark_ids = {l["id"] for l in landmarks_data.get("landmarks", [])}

    seeds = village_data["quest"]["force_sign_seeds"]
    shrine_seed = next((s for s in seeds if s.get("id") == "shrine_entry"),
                      None)
    check("Village quest has shrine_entry seed", shrine_seed is not None)
    if not shrine_seed:
        return

    seed_rooms = set(shrine_seed.get("rooms", []))

    # Every landmark we defined should be in the Village's seed list
    landmark_not_in_village = landmark_ids - seed_rooms
    check("every landmark id is referenced by Village quest",
          not landmark_not_in_village,
          f"orphan landmarks: {sorted(landmark_not_in_village)}")

    # Every shrine_entry room should be defined here
    village_room_not_landmark = seed_rooms - landmark_ids
    check("every Village shrine_entry room is defined as a landmark",
          not village_room_not_landmark,
          f"unresolved: {sorted(village_room_not_landmark)}")


def test_anchor_stones_specials(data):
    print("\n[4] dune_sea_anchor_stones — Village navigation anchor")
    landmarks = {l["id"]: l for l in data.get("landmarks", [])}
    anchor = landmarks.get("dune_sea_anchor_stones")
    check("dune_sea_anchor_stones present", anchor is not None)
    if not anchor:
        return

    props = anchor.get("properties", {})
    check("dune_sea_anchor_stones.village_quest_anchor == true",
          props.get("village_quest_anchor") is True,
          f"got {props.get('village_quest_anchor')!r}")


def test_uniqueness(data):
    print("\n[5] Landmark uniqueness")
    landmarks = data.get("landmarks", [])
    ids = [l.get("id") for l in landmarks]
    names = [l.get("name") for l in landmarks]
    check("all landmark ids unique", len(ids) == len(set(ids)),
          f"duplicates: {[i for i in set(ids) if ids.count(i) > 1]}")
    check("all landmark names unique", len(names) == len(set(names)),
          f"duplicates: {[n for n in set(names) if names.count(n) > 1]}")


def main():
    if not LANDMARKS.is_file():
        print(f"ERROR: {LANDMARKS} not found")
        sys.exit(2)
    if not VILLAGE.is_file():
        print(f"ERROR: {VILLAGE} not found — Village quest must be applied first")
        sys.exit(2)

    landmarks_data = yaml.safe_load(LANDMARKS.read_text())
    village_data = yaml.safe_load(VILLAGE.read_text())

    print(f"Loaded landmarks file with {len(landmarks_data.get('landmarks', []))} landmarks")

    test_top_level(landmarks_data)
    for idx, lm in enumerate(landmarks_data.get("landmarks", [])):
        test_landmark_shape(lm, idx)
    test_cross_reference_with_village(landmarks_data, village_data)
    test_anchor_stones_specials(landmarks_data)
    test_uniqueness(landmarks_data)

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
