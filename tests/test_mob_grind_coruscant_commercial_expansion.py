"""
tests/test_mob_grind_coruscant_commercial_expansion.py

Static invariant tests for the Coruscant Commercial District Expansion
hostile mob grind batch
(data/worlds/clone_wars/npcs_drop_mob_grind_coruscant_commercial_expansion.yaml).

Verifies:
  1. YAML parses without error
  2. All 6 NPCs are present
  3. Every NPC satisfies is_huntable_mob() requirements (hostile=true, no
     special-reward markers)
  4. Room names match real rooms in coruscant.yaml
  5. Room names are all in the expected commercial_district set
  6. Weapon keys exist in data/weapons.yaml (skipped if no key: lines found)
  7. Era cleanness — no forbidden strings in any player-facing field
  8. Required char_sheet fields are present
  9. Schema version is 1
  10. Species diversity — at least 4 distinct species
  11. Fallback lines present on every NPC
  12. File registered in era.yaml
"""

import pytest
import yaml
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "worlds", "clone_wars")
GRIND_FILE = os.path.join(
    DATA_DIR, "npcs_drop_mob_grind_coruscant_commercial_expansion.yaml"
)
CORUSCANT_FILE = os.path.join(DATA_DIR, "planets", "coruscant.yaml")
ERA_FILE = os.path.join(DATA_DIR, "era.yaml")
WEAPONS_FILE = os.path.join(DATA_DIR, "..", "..", "weapons.yaml")

EXPECTED_NPC_COUNT = 6
EXPECTED_ROOMS = {
    "Coruscant - Mid-City Transit Hub",
    "Coruscant - Mid-Level Market Street",
    "Coruscant - Mid-Level Residential Block",
    "Coruscant - Coco Town - Residential Walk",
    "Coruscant - Coco Town - Market Arcade",
    "Coruscant - Outlander Cantina - Back Rooms",
}

# Markers that must NOT be present on huntable mob NPCs
SPECIAL_REWARD_MARKERS = [
    "is_bounty_target",
    "is_anomaly_target",
    "is_wilderness_encounter",
    "is_dsp_hunter",
    "is_intel_handler",
    "chain_enemy_template",
    "vendor",
]

ERA_FORBIDDEN = ["imperial", "empire", "rebel", "tie fighter"]


@pytest.fixture(scope="module")
def grind_data():
    with open(GRIND_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def coruscant_room_names():
    with open(CORUSCANT_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {room["name"] for room in data.get("rooms", [])}


@pytest.fixture(scope="module")
def weapon_keys():
    with open(WEAPONS_FILE, encoding="utf-8") as f:
        content = f.read()
    keys = set()
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("key:"):
            key = stripped.split(":", 1)[1].strip().strip('"').strip("'")
            if key:
                keys.add(key)
    return keys


@pytest.fixture(scope="module")
def era_data():
    with open(ERA_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_yaml_parses(grind_data):
    """YAML file loads without error."""
    assert grind_data is not None


def test_schema_version(grind_data):
    assert grind_data["schema_version"] == 1


def test_npc_count(grind_data):
    assert len(grind_data["npcs"]) == EXPECTED_NPC_COUNT


def test_all_hostile(grind_data):
    """Every NPC has ai_config.hostile = true."""
    for npc in grind_data["npcs"]:
        assert npc["ai_config"]["hostile"] is True, (
            f"{npc['name']}: hostile must be true for huntable mobs"
        )


def test_no_special_reward_markers(grind_data):
    """No NPC carries any of the is_huntable_mob() exclusion markers."""
    for npc in grind_data["npcs"]:
        for marker in SPECIAL_REWARD_MARKERS:
            assert marker not in npc, (
                f"{npc['name']}: must not carry {marker!r} for huntable mob"
            )
            assert marker not in npc.get("ai_config", {}), (
                f"{npc['name']}.ai_config: must not carry {marker!r}"
            )


def test_rooms_are_valid_coruscant_rooms(grind_data, coruscant_room_names):
    """Every NPC's room matches a real room name in coruscant.yaml."""
    for npc in grind_data["npcs"]:
        assert npc["room"] in coruscant_room_names, (
            f"{npc['name']}: room {npc['room']!r} not found in coruscant.yaml"
        )


def test_rooms_are_expected_commercial_rooms(grind_data):
    """Every NPC is placed in one of the six target commercial_district rooms."""
    for npc in grind_data["npcs"]:
        assert npc["room"] in EXPECTED_ROOMS, (
            f"{npc['name']}: room {npc['room']!r} is not a target commercial room"
        )


def test_each_expected_room_covered(grind_data):
    """All six expected rooms have at least one NPC."""
    covered = {npc["room"] for npc in grind_data["npcs"]}
    missing = EXPECTED_ROOMS - covered
    assert not missing, f"These rooms have no NPCs: {missing}"


def test_weapon_keys_exist(grind_data, weapon_keys):
    """Every weapon key resolves in data/weapons.yaml."""
    if not weapon_keys:
        pytest.skip("weapons.yaml key list empty — encoding issue")
    for npc in grind_data["npcs"]:
        weapon = npc["char_sheet"]["weapon"]
        assert weapon in weapon_keys, (
            f"{npc['name']}: weapon key {weapon!r} not in weapons.yaml"
        )


def test_required_char_sheet_fields(grind_data):
    """Every NPC has the required char_sheet fields."""
    required = {
        "attributes",
        "skills",
        "weapon",
        "move",
        "force_points",
        "character_points",
        "dark_side_points",
    }
    required_attrs = {
        "dexterity",
        "knowledge",
        "mechanical",
        "perception",
        "strength",
        "technical",
    }
    for npc in grind_data["npcs"]:
        sheet = npc["char_sheet"]
        missing = required - set(sheet.keys())
        assert not missing, f"{npc['name']}: missing char_sheet fields: {missing}"
        missing_attrs = required_attrs - set(sheet["attributes"].keys())
        assert not missing_attrs, (
            f"{npc['name']}: missing attributes: {missing_attrs}"
        )


def test_era_cleanness(grind_data):
    """No player-facing strings contain forbidden era terms."""
    import json

    raw = json.dumps(grind_data).lower()
    for term in ERA_FORBIDDEN:
        assert term not in raw, (
            f"Era violation: {term!r} found in commercial expansion mob grind data"
        )


def test_registered_in_era_yaml(era_data):
    """The new file is registered in era.yaml content_refs.npcs."""
    import json

    raw = json.dumps(era_data)
    assert "commercial_expansion" in raw, (
        "npcs_drop_mob_grind_coruscant_commercial_expansion.yaml not registered in era.yaml"
    )


def test_species_diversity(grind_data):
    """At least 4 distinct species — the batch is meant to be diverse."""
    species = {npc["species"] for npc in grind_data["npcs"]}
    assert len(species) >= 4, f"Expected ≥4 species, got {len(species)}: {species}"


def test_fallback_lines_present(grind_data):
    """Every NPC has at least 2 fallback dialogue lines."""
    for npc in grind_data["npcs"]:
        lines = npc["ai_config"].get("fallback_lines", [])
        assert len(lines) >= 2, (
            f"{npc['name']}: needs at least 2 fallback_lines, got {len(lines)}"
        )
