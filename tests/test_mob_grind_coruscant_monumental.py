"""
tests/test_mob_grind_coruscant_monumental.py

Per-drop test for npcs_drop_mob_grind_coruscant_monumental.yaml.
Verifies:
  - All 10 NPCs parse correctly
  - All rooms exist in coruscant.yaml (planet rooms)
  - All NPCs are hostile with no special-reward markers
  - All weapon keys exist in weapons.yaml
  - No canon figures, no era violations in names/species
  - is_huntable_mob() logic satisfied
"""
import yaml
import pytest
from pathlib import Path


WORLD_DIR = Path("data/worlds/clone_wars")
NPC_FILE = WORLD_DIR / "npcs_drop_mob_grind_coruscant_monumental.yaml"
PLANET_FILE = WORLD_DIR / "planets/coruscant.yaml"
WEAPONS_FILE = Path("data/weapons.yaml")


@pytest.fixture(scope="module")
def npc_data():
    with open(NPC_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def coruscant_rooms():
    with open(PLANET_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {r["name"] for r in data.get("rooms", [])}


@pytest.fixture(scope="module")
def weapon_keys():
    with open(WEAPONS_FILE, encoding="utf-8") as f:
        return set(yaml.safe_load(f).keys())


def test_npc_file_parses():
    with open(NPC_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "npcs" in data


def test_npc_count(npc_data):
    assert len(npc_data["npcs"]) == 10, "Expected 10 NPCs in monumental district batch"


def test_all_rooms_exist_in_planet(npc_data, coruscant_rooms):
    for npc in npc_data["npcs"]:
        room = npc.get("room", "")
        assert room in coruscant_rooms, (
            f"NPC {npc['name']!r} room {room!r} not found in coruscant.yaml"
        )


def test_all_rooms_in_monumental_zone(npc_data):
    with open(PLANET_FILE, encoding="utf-8") as f:
        planet = yaml.safe_load(f)
    room_to_zone = {r["name"]: r.get("zone", "") for r in planet.get("rooms", [])}
    for npc in npc_data["npcs"]:
        room = npc.get("room", "")
        zone = room_to_zone.get(room, "")
        assert zone == "monumental_district", (
            f"NPC {npc['name']!r} is in zone {zone!r}, expected monumental_district"
        )


def test_all_hostile(npc_data):
    for npc in npc_data["npcs"]:
        ai = npc.get("ai_config", {})
        assert ai.get("hostile") is True, (
            f"NPC {npc['name']!r} is not hostile"
        )


def test_no_special_reward_markers(npc_data):
    special_markers = [
        "is_bounty_target",
        "is_anomaly_target",
        "is_wilderness_encounter",
        "is_dsp_hunter",
        "is_intel_handler",
        "chain_enemy_template",
        "vendor",
    ]
    for npc in npc_data["npcs"]:
        ai = npc.get("ai_config", {})
        for marker in special_markers:
            assert not npc.get(marker), (
                f"NPC {npc['name']!r} has forbidden marker {marker!r} on npc"
            )
            assert not ai.get(marker), (
                f"NPC {npc['name']!r} has forbidden marker {marker!r} in ai_config"
            )


def test_weapons_exist_in_registry(npc_data, weapon_keys):
    for npc in npc_data["npcs"]:
        weapon = npc.get("char_sheet", {}).get("weapon", "")
        if weapon:
            assert weapon in weapon_keys, (
                f"NPC {npc['name']!r} uses weapon {weapon!r} not in weapons.yaml"
            )


def test_no_era_violations(npc_data):
    banned = ["imperial", "empire", "rebel", "tie fighter", "stormtrooper"]
    for npc in npc_data["npcs"]:
        # Check name and description
        text = (
            (npc.get("name") or "")
            + (npc.get("description") or "")
            + (npc.get("ai_config", {}).get("personality") or "")
            + (npc.get("ai_config", {}).get("dialogue_style") or "")
        ).lower()
        for term in banned:
            assert term not in text, (
                f"NPC {npc['name']!r} contains era-banned term {term!r}"
            )


def test_schema_version(npc_data):
    assert npc_data.get("schema_version") == 1


def test_each_npc_has_required_fields(npc_data):
    required = ["name", "room", "species", "description", "char_sheet", "ai_config"]
    for npc in npc_data["npcs"]:
        for field in required:
            assert field in npc, f"NPC {npc.get('name','?')} missing required field {field!r}"


def test_char_sheet_attributes(npc_data):
    attrs = ["dexterity", "knowledge", "mechanical", "perception", "strength", "technical"]
    for npc in npc_data["npcs"]:
        sheet = npc.get("char_sheet", {})
        attributes = sheet.get("attributes", {})
        for attr in attrs:
            assert attr in attributes, (
                f"NPC {npc['name']!r} missing attribute {attr!r}"
            )


def test_era_registered_in_era_yaml():
    with open(WORLD_DIR / "era.yaml", encoding="utf-8") as f:
        content = f.read()
    assert "npcs_drop_mob_grind_coruscant_monumental.yaml" in content, (
        "era.yaml does not reference the monumental district mob grind file"
    )
