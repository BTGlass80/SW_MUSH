"""
tests/test_mob_grind_geonosis_foundry_density.py

Static invariant tests for the Geonosis Foundries second-mob density expansion
(data/worlds/clone_wars/npcs_drop_mob_grind_geonosis_foundry_density.yaml).

Adds a SECOND hostile mob to 6 geonosis_foundries rooms that previously had
exactly one:
  Geonosis - Droid Foundry - Main Floor
  Geonosis - B2 Super Battle Droid Assembly
  Geonosis - Foundry Control Center
  Geonosis - CIS Engineering Bay
  Geonosis - Foundry Power Generator
  Geonosis - Secondary Foundry (Deep Level)

Verifies:
  1. YAML parses without error
  2. Schema version is 1
  3. All 6 NPCs are present
  4. Every NPC satisfies is_huntable_mob() requirements (hostile=true, no exclusion markers)
  5. Room names match real rooms in geonosis.yaml
  6. All rooms are in the expected target set
  7. Each expected room has at least one NPC
  8. Weapon keys exist in data/weapons.yaml
  9. Required char_sheet fields present
  10. Era cleanness — no forbidden strings
  11. Species diversity — all 6 distinct species
  12. Fallback lines present on every NPC (>= 2)
  13. File registered in era.yaml
"""

import pytest
import yaml
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "worlds", "clone_wars")
GRIND_FILE = os.path.join(DATA_DIR, "npcs_drop_mob_grind_geonosis_foundry_density.yaml")
GEONOSIS_FILE = os.path.join(DATA_DIR, "planets", "geonosis.yaml")
ERA_FILE = os.path.join(DATA_DIR, "era.yaml")
WEAPONS_FILE = os.path.join(DATA_DIR, "..", "..", "weapons.yaml")

EXPECTED_NPC_COUNT = 6
EXPECTED_ROOMS = {
    "Geonosis - Droid Foundry - Main Floor",
    "Geonosis - B2 Super Battle Droid Assembly",
    "Geonosis - Foundry Control Center",
    "Geonosis - CIS Engineering Bay",
    "Geonosis - Foundry Power Generator",
    "Geonosis - Secondary Foundry (Deep Level)",
}

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
def geonosis_room_names():
    with open(GEONOSIS_FILE, encoding="utf-8") as f:
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
    for line in content.splitlines():
        if line and not line.startswith(" ") and not line.startswith("#") and line.endswith(":"):
            keys.add(line[:-1].strip())
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


def test_rooms_are_valid_geonosis_rooms(grind_data, geonosis_room_names):
    """Every NPC's room matches a real room in geonosis.yaml."""
    for npc in grind_data["npcs"]:
        assert npc["room"] in geonosis_room_names, (
            f"{npc['name']}: room {npc['room']!r} not found in geonosis.yaml"
        )


def test_rooms_are_expected_target_rooms(grind_data):
    """Every NPC is placed in one of the six target foundry rooms."""
    for npc in grind_data["npcs"]:
        assert npc["room"] in EXPECTED_ROOMS, (
            f"{npc['name']}: room {npc['room']!r} is not a target foundry room"
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
        if weapon == "":
            continue  # empty = brawling fallback, valid
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
            f"Era violation: {term!r} found in Geonosis foundry density mob grind data"
        )


def test_registered_in_era_yaml(era_data):
    """The new file is registered in era.yaml content_refs.npcs."""
    import json
    raw = json.dumps(era_data)
    assert "foundry_density" in raw, (
        "npcs_drop_mob_grind_geonosis_foundry_density.yaml not registered in era.yaml"
    )


def test_species_diversity(grind_data):
    """All 6 NPCs are different species."""
    species = {npc["species"] for npc in grind_data["npcs"]}
    assert len(species) == EXPECTED_NPC_COUNT, (
        f"Expected {EXPECTED_NPC_COUNT} distinct species, got {len(species)}: {species}"
    )


def test_fallback_lines_present(grind_data):
    """Every NPC has at least 2 fallback dialogue lines."""
    for npc in grind_data["npcs"]:
        lines = npc["ai_config"].get("fallback_lines", [])
        assert len(lines) >= 2, (
            f"{npc['name']}: needs at least 2 fallback_lines, got {len(lines)}"
        )
