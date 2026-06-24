"""
tests/test_ambient_coruscant_culture_venues.py

Per-drop test for npcs_drop_ambient_coruscant_culture_venues.yaml.
Verifies:
  - All 4 NPCs parse correctly
  - All rooms exist in coruscant.yaml (planet rooms)
  - All NPCs are ambient (hostile: false) with no special-reward markers
  - No era violations in names/descriptions
  - Required fields present on all NPCs
  - File registered in era.yaml
"""
import yaml
import pytest
from pathlib import Path


WORLD_DIR = Path("data/worlds/clone_wars")
NPC_FILE = WORLD_DIR / "npcs_drop_ambient_coruscant_culture_venues.yaml"
PLANET_FILE = WORLD_DIR / "planets/coruscant.yaml"


@pytest.fixture(scope="module")
def npc_data():
    with open(NPC_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def coruscant_rooms():
    with open(PLANET_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {r["name"] for r in data.get("rooms", [])}


def test_npc_file_parses():
    with open(NPC_FILE, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    assert data is not None
    assert "npcs" in data


def test_npc_count(npc_data):
    assert len(npc_data["npcs"]) == 4, (
        f"Expected 4 ambient NPCs, got {len(npc_data['npcs'])}"
    )


def test_all_rooms_exist_in_planet(npc_data, coruscant_rooms):
    for npc in npc_data["npcs"]:
        room = npc.get("room", "")
        assert room in coruscant_rooms, (
            f"NPC {npc['name']!r} room {room!r} not found in coruscant.yaml"
        )


def test_all_rooms_in_monumental_district(npc_data):
    with open(PLANET_FILE, encoding="utf-8") as f:
        planet = yaml.safe_load(f)
    room_to_zone = {r["name"]: r.get("zone", "") for r in planet.get("rooms", [])}
    for npc in npc_data["npcs"]:
        room = npc.get("room", "")
        zone = room_to_zone.get(room, "")
        assert zone == "monumental_district", (
            f"NPC {npc['name']!r} is in zone {zone!r}, expected monumental_district"
        )


def test_all_npcs_non_hostile(npc_data):
    for npc in npc_data["npcs"]:
        ai = npc.get("ai_config", {})
        assert ai.get("hostile") is False, (
            f"NPC {npc['name']!r} is hostile (expected ambient/flavor NPC)"
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


def test_no_era_violations(npc_data):
    banned = ["imperial", "empire", "rebel", "tie fighter", "stormtrooper"]
    for npc in npc_data["npcs"]:
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
            assert field in npc, (
                f"NPC {npc.get('name', '?')} missing required field {field!r}"
            )


def test_char_sheet_attributes(npc_data):
    attrs = ["dexterity", "knowledge", "mechanical", "perception", "strength", "technical"]
    for npc in npc_data["npcs"]:
        sheet = npc.get("char_sheet", {})
        attributes = sheet.get("attributes", {})
        for attr in attrs:
            assert attr in attributes, (
                f"NPC {npc['name']!r} missing attribute {attr!r}"
            )


def test_distinct_rooms(npc_data):
    rooms = [npc.get("room") for npc in npc_data["npcs"]]
    assert len(rooms) == len(set(rooms)), (
        f"Duplicate room assignments found: {rooms}"
    )


def test_era_registered_in_era_yaml():
    with open(WORLD_DIR / "era.yaml", encoding="utf-8") as f:
        content = f.read()
    assert "npcs_drop_ambient_coruscant_culture_venues.yaml" in content, (
        "era.yaml does not reference the culture venues ambient NPC file"
    )
