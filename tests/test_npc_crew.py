"""
Tests for NPC Crew engine (npc_crew.py).
Tests the pure-logic functions: name generation, hiring board,
crew JSON helpers, role mapping, and display formatting.
"""
import sys
import os
import json

# Add project root to path (one level up from tests/)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.npc_crew import (
    generate_name, generate_hiring_board, _best_role_for_archetype,
    npc_to_character, resolve_npc_skill, get_station_skill,
    get_crew_json, set_npc_station, remove_npc_from_station,
    remove_npc_from_all_stations, get_npc_ids_on_ship,
    format_roster_entry, format_hire_entry,
    CREW_ROLES, VALID_STATIONS, TIER_WAGES, LOCATION_PROFILES,
    _weighted_choice,
)
from engine.character import Character, SkillRegistry
from engine.dice import DicePool


def test_crew_roles_complete():
    """All six crew stations are defined."""
    expected = {"pilot", "copilot", "gunner", "engineer", "navigator", "sensors"}
    assert VALID_STATIONS == expected, f"Missing stations: {expected - VALID_STATIONS}"
    for role_name, role in CREW_ROLES.items():
        assert role.skill, f"Role {role_name} has no skill"
        assert role.archetypes, f"Role {role_name} has no archetypes"
    print("  PASS: all 6 crew roles defined with skills and archetypes")


def test_tier_wages():
    """Wage table matches the design doc."""
    assert TIER_WAGES["extra"] == 30
    assert TIER_WAGES["average"] == 80
    assert TIER_WAGES["novice"] == 150
    assert TIER_WAGES["veteran"] == 400
    assert TIER_WAGES["superior"] == 1000
    print("  PASS: tier wages match design doc")


def test_name_generation():
    """Name generator produces valid names for all species."""
    seen_species = set()
    for species in ["Human", "Rodian", "Twi'lek", "Wookiee", "Trandoshan",
                    "Duros", "Sullustan", "Bothan", "Mon Calamari"]:
        name = generate_name(species)
        assert isinstance(name, str) and len(name) > 0, f"Bad name for {species}"
        seen_species.add(species)

    # Unknown species falls back to Human
    name = generate_name("Gungan")
    assert isinstance(name, str) and len(name) > 0

    print(f"  PASS: name generation works for {len(seen_species)} species + fallback")


def test_hiring_board_generation():
    """Hiring board generates valid NPCs with correct structure."""
    for profile_key in LOCATION_PROFILES:
        board = generate_hiring_board(profile_key)
        assert len(board) >= 3, f"Board too small for {profile_key}"

        for entry in board:
            assert "sheet" in entry
            assert "wage" in entry
            assert "role_hint" in entry
            assert "tier" in entry
            assert "species" in entry

            sheet = entry["sheet"]
            assert "attributes" in sheet
            assert "skills" in sheet
            assert "name" in sheet

            assert entry["wage"] == TIER_WAGES[entry["tier"]]
            assert entry["role_hint"] in VALID_STATIONS

    print(f"  PASS: hiring board generates valid NPCs for all {len(LOCATION_PROFILES)} profiles")


def test_archetype_to_role():
    """Archetypes map to sensible crew roles."""
    assert _best_role_for_archetype("pilot") == "pilot"
    assert _best_role_for_archetype("mechanic") == "engineer"
    assert _best_role_for_archetype("scout") == "pilot"
    assert _best_role_for_archetype("smuggler") == "pilot"
    assert _best_role_for_archetype("bounty_hunter") == "gunner"
    assert _best_role_for_archetype("jedi") == "gunner"
    print("  PASS: archetype-to-role mapping is sensible")


def test_npc_to_character():
    """NPC row converts to a Character with correct attributes and skills."""
    sheet = {
        "name": "Test Pilot",
        "species": "Human",
        "tier": "novice",
        "template": "Pilot",
        "attributes": {
            "dexterity": "3D", "knowledge": "2D+1", "mechanical": "4D",
            "perception": "3D", "strength": "2D+2", "technical": "3D",
        },
        "skills": {
            "space transports": "2D",
            "starship gunnery": "1D+1",
            "astrogation": "1D",
        },
    }
    npc_row = {
        "id": 1,
        "name": "Test Pilot",
        "species": "Human",
        "char_sheet_json": json.dumps(sheet),
    }

    char = npc_to_character(npc_row)
    assert char.name == "Test Pilot"
    assert char.mechanical.dice == 4
    assert "space transports" in char.skills
    assert char.skills["space transports"].dice == 2
    print("  PASS: NPC row converts to Character correctly")


def test_resolve_npc_skill():
    """Skill resolution returns attribute + skill bonus."""
    sheet = {
        "name": "Gunner Grek",
        "attributes": {
            "dexterity": "3D", "knowledge": "2D", "mechanical": "3D+2",
            "perception": "2D+1", "strength": "3D", "technical": "2D",
        },
        "skills": {
            "starship gunnery": "1D+2",
        },
    }
    npc_row = {"name": "Gunner Grek", "char_sheet_json": json.dumps(sheet)}

    sr = SkillRegistry()
    skills_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "skills.yaml",
    )
    if os.path.exists(skills_path):
        sr.load_file(skills_path)

    pool = resolve_npc_skill(npc_row, "starship gunnery", sr)
    assert pool.dice >= 4, f"Expected at least 4D, got {pool}"
    print(f"  PASS: skill resolution returns {pool} for gunnery")


def test_get_station_skill():
    """Station names map to correct skills."""
    assert get_station_skill("pilot") == "space transports"
    assert get_station_skill("gunner") == "starship gunnery"
    assert get_station_skill("engineer") == "space transports repair"
    assert get_station_skill("navigator") == "astrogation"
    assert get_station_skill("sensors") == "sensors"
    assert get_station_skill("copilot") == "space transports"
    assert get_station_skill("nonexistent") == ""
    print("  PASS: station -> skill mapping correct")


def test_crew_json_helpers():
    """Crew JSON manipulation: set, remove, get IDs."""
    crew = {"pilot": 42, "gunners": [100]}

    crew = set_npc_station(crew, "pilot", 7)
    assert crew["npc_pilot"] == 7

    crew = set_npc_station(crew, "gunner", 12)
    assert 12 in crew["npc_gunners"]

    crew = set_npc_station(crew, "gunner", 13)
    assert crew["npc_gunners"] == [12, 13]

    crew = set_npc_station(crew, "engineer", 15)
    assert crew["npc_engineer"] == 15

    ids = get_npc_ids_on_ship(crew)
    assert 7 in ids
    assert 12 in ids
    assert 13 in ids
    assert 15 in ids
    assert 42 not in ids
    assert 100 not in ids

    crew = remove_npc_from_station(crew, "gunner", 12)
    assert 12 not in crew["npc_gunners"]
    assert 13 in crew["npc_gunners"]

    crew = remove_npc_from_station(crew, "pilot", 7)
    assert crew["npc_pilot"] is None

    crew = set_npc_station(crew, "pilot", 15)
    crew = remove_npc_from_all_stations(crew, 15)
    assert crew.get("npc_pilot") is None
    assert crew.get("npc_engineer") is None

    print("  PASS: crew JSON helpers -- set/remove/getIDs all work")


def test_crew_json_parse():
    """get_crew_json handles string, dict, and None."""
    assert get_crew_json({"crew": '{"pilot": 1}'})["pilot"] == 1
    assert get_crew_json({"crew": {"pilot": 2}})["pilot"] == 2
    assert get_crew_json({"crew": None}) == {}
    assert get_crew_json({"crew": "invalid json{"}) == {}
    assert get_crew_json({}) == {}
    print("  PASS: crew JSON parsing handles all edge cases")


def test_player_slots_untouched():
    """NPC station operations never touch player crew slots."""
    crew = {"pilot": 42, "gunners": [100, 101], "copilot": 43}

    crew = set_npc_station(crew, "pilot", 7)
    crew = set_npc_station(crew, "gunner", 12)

    assert crew["pilot"] == 42
    assert crew["gunners"] == [100, 101]
    assert crew["copilot"] == 43
    assert crew["npc_pilot"] == 7
    assert crew["npc_gunners"] == [12]

    print("  PASS: player crew slots completely untouched by NPC operations")


def test_format_functions():
    """Display formatters produce non-empty strings."""
    npc_row = {
        "name": "Kael Voss",
        "char_sheet_json": json.dumps({
            "tier": "novice", "template": "Pilot",
            "attributes": {"mechanical": "4D"},
            "skills": {"space transports": "2D"},
        }),
        "assigned_station": "pilot",
        "hire_wage": 150,
    }
    line = format_roster_entry(npc_row)
    assert "Kael Voss" in line
    assert "PILOT" in line
    assert "150" in line

    entry = {
        "sheet": {
            "name": "Mira Tann",
            "attributes": {"mechanical": "3D+1"},
            "skills": {"space transports repair": "1D+2"},
        },
        "wage": 80,
        "role_hint": "engineer",
        "tier": "average",
        "species": "Human",
    }
    line = format_hire_entry(entry, 1)
    assert "Mira Tann" in line
    assert "80" in line

    print("  PASS: format functions produce readable output")


def test_weighted_choice():
    """Weighted choice produces valid keys."""
    weights = {"a": 0.9, "b": 0.1}
    results = [_weighted_choice(weights) for _ in range(100)]
    assert "a" in results
    assert all(r in ("a", "b") for r in results)
    print("  PASS: weighted choice produces valid results")


def test_duplicate_npc_gunner_prevention():
    """Adding the same NPC gunner twice should not create duplicates."""
    crew = {}
    crew = set_npc_station(crew, "gunner", 12)
    crew = set_npc_station(crew, "gunner", 12)
    assert crew["npc_gunners"].count(12) == 1
    print("  PASS: duplicate NPC gunner prevention works")


def main():
    print("Testing NPC Crew Engine (npc_crew.py)")
    print("=" * 55)
    test_crew_roles_complete()
    test_tier_wages()
    test_name_generation()
    test_hiring_board_generation()
    test_archetype_to_role()
    test_npc_to_character()
    test_resolve_npc_skill()
    test_get_station_skill()
    test_crew_json_helpers()
    test_crew_json_parse()
    test_player_slots_untouched()
    test_format_functions()
    test_weighted_choice()
    test_duplicate_npc_gunner_prevention()
    print("=" * 55)
    print("All tests passed.")


if __name__ == "__main__":
    main()
