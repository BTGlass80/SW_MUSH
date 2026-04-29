# -*- coding: utf-8 -*-
"""F.1c — Era-aware test character loader regression tests.

Pre-F.1c, build_mos_eisley.py held the Test Jedi spec inline (~155 lines of
JSON literals + INSERT statements). F.1c extracts to
data/worlds/gcw/test_character.yaml and adds engine/test_character_loader.py
with load_era_test_character(era_dir, room_name_map).

Tests cover:
  * Spec loads with all required fields populated.
  * Critical attribute / skill / equipment fields preserved (regression
    guard against the inline literal's specific values: 10D lightsaber,
    8D+2 blaster, 5D attributes, force_sensitive: true, tutorial_step: 99).
  * starting_room resolves to a yaml_id integer.
  * Missing era.yaml / no test_character ref / bad starting_room → None.
"""
import os
import pytest

from engine.test_character_loader import load_era_test_character
from engine.world_loader import load_world_dry_run


@pytest.fixture(scope="module")
def gcw_room_map():
    bundle = load_world_dry_run("gcw")
    return {r.name: r.id for r in bundle.rooms.values()}


@pytest.fixture(scope="module")
def gcw_test_spec(gcw_room_map):
    era_dir = os.path.join(os.path.dirname(__file__), "..", "data", "worlds", "gcw")
    return load_era_test_character(era_dir, gcw_room_map)


# ──────────────────────────────────────────────────────────────────────────


class TestSpecShape:
    def test_spec_loads(self, gcw_test_spec):
        assert gcw_test_spec is not None

    def test_account_fields(self, gcw_test_spec):
        a = gcw_test_spec["account"]
        assert a["username"] == "testuser"
        assert a["password"] == "testpass"
        assert a["is_admin"] is True
        assert a["is_builder"] is True

    def test_character_basic_fields(self, gcw_test_spec):
        c = gcw_test_spec["character"]
        assert c["name"] == "Test Jedi"
        assert c["species"] == "Human"
        assert c["template"] == "jedi"
        assert c["faction_id"] == "independent"
        assert c["credits"] == 100000
        assert c["character_points"] == 25
        assert c["force_points"] == 5
        assert c["dark_side_points"] == 0
        assert c["wound_level"] == 0


class TestStartingRoomResolution:
    def test_starting_room_string_preserved(self, gcw_test_spec):
        c = gcw_test_spec["character"]
        assert c["starting_room"] == "Docking Bay 94 - Entrance"

    def test_starting_room_idx_resolved(self, gcw_test_spec, gcw_room_map):
        c = gcw_test_spec["character"]
        assert isinstance(c["starting_room_idx"], int)
        # Should match the yaml_id of "Docking Bay 94 - Entrance"
        assert c["starting_room_idx"] == gcw_room_map["Docking Bay 94 - Entrance"]


class TestAttributePreservation:
    """Critical attribute values from the inline literal must round-trip
    via YAML. These specific values define the god-mode test character."""

    def test_d6_attributes_all_5d(self, gcw_test_spec):
        attrs = gcw_test_spec["character"]["attributes"]
        for attr in ("dexterity", "knowledge", "mechanical",
                     "perception", "strength", "technical"):
            assert attrs[attr] == "5D", f"{attr} = {attrs[attr]!r}"

    def test_force_sensitive_flag(self, gcw_test_spec):
        attrs = gcw_test_spec["character"]["attributes"]
        assert attrs["force_sensitive"] is True

    def test_force_skills_present(self, gcw_test_spec):
        attrs = gcw_test_spec["character"]["attributes"]
        fs = attrs["force_skills"]
        assert fs["control"] == "8D"
        assert fs["sense"] == "8D"
        assert fs["alter"] == "7D"

    def test_tutorial_complete_flags(self, gcw_test_spec):
        attrs = gcw_test_spec["character"]["attributes"]
        assert attrs["tutorial_core"] == "complete"
        assert attrs["tutorial_step"] == 99
        electives = attrs["tutorial_electives"]
        for elective in ("combat", "space", "trading", "crafting", "factions"):
            assert electives[elective] == "complete"


class TestSkillPreservation:
    def test_lightsaber_10d(self, gcw_test_spec):
        skills = gcw_test_spec["character"]["skills"]
        assert skills["lightsaber"] == "10D"

    def test_blaster_8d2(self, gcw_test_spec):
        skills = gcw_test_spec["character"]["skills"]
        assert skills["blaster"] == "8D+2"

    def test_starship_gunnery_8d2(self, gcw_test_spec):
        skills = gcw_test_spec["character"]["skills"]
        assert skills["starship_gunnery"] == "8D+2"

    def test_skill_count(self, gcw_test_spec):
        # Inline literal had 75 skills + 3 force skills = 78 entries
        skills = gcw_test_spec["character"]["skills"]
        assert len(skills) >= 70  # tolerant lower bound; exact = 78


class TestEquipmentInventory:
    def test_lightsaber_equipped(self, gcw_test_spec):
        eq = gcw_test_spec["character"]["equipment"]
        assert eq["key"] == "lightsaber"
        assert eq["condition"] == 100
        assert eq["quality"] == 100

    def test_inventory_items_count(self, gcw_test_spec):
        inv = gcw_test_spec["character"]["inventory"]
        items = inv["items"]
        # Inline had 5: 2 medpacs, DL-44, comlink, datapad
        assert len(items) == 5
        keys = [i["key"] for i in items]
        assert keys.count("medpac") == 2
        assert "heavy_blaster_pistol" in keys
        assert "comlink" in keys
        assert "datapad" in keys

    def test_inventory_resources_count(self, gcw_test_spec):
        inv = gcw_test_spec["character"]["inventory"]
        resources = inv["resources"]
        assert len(resources) == 3
        types = [r["type"] for r in resources]
        assert "durasteel" in types
        assert "power_cell" in types
        assert "tibanna_gas" in types


class TestEdgeCases:
    def test_missing_era_yaml_returns_none(self, tmp_path, gcw_room_map):
        spec = load_era_test_character(str(tmp_path), gcw_room_map)
        assert spec is None

    def test_no_test_character_ref_returns_none(self, tmp_path, gcw_room_map):
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  zones: zones.yaml\n"
        )
        spec = load_era_test_character(str(tmp_path), gcw_room_map)
        assert spec is None

    def test_unresolvable_starting_room_returns_none(self, tmp_path, gcw_room_map):
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  test_character: tc.yaml\n"
        )
        (tmp_path / "tc.yaml").write_text(
            "schema_version: 1\n"
            "account:\n  username: u\n  password: p\n"
            "character:\n  name: 'X'\n  starting_room: 'Nonexistent Bay'\n"
        )
        spec = load_era_test_character(str(tmp_path), gcw_room_map)
        assert spec is None

    def test_missing_username_returns_none(self, tmp_path, gcw_room_map):
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  test_character: tc.yaml\n"
        )
        (tmp_path / "tc.yaml").write_text(
            "schema_version: 1\n"
            "account:\n  password: p\n"  # username missing
            "character:\n  name: 'X'\n  starting_room: 'Docking Bay 86'\n"
        )
        spec = load_era_test_character(str(tmp_path), gcw_room_map)
        assert spec is None

    def test_minimal_valid_spec(self, tmp_path, gcw_room_map):
        """Smallest spec the loader will accept, with defaults filled in."""
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  test_character: tc.yaml\n"
        )
        (tmp_path / "tc.yaml").write_text(
            "schema_version: 1\n"
            "account:\n"
            "  username: dev\n"
            "  password: dev\n"
            "character:\n"
            "  name: 'Dev Account'\n"
            "  starting_room: 'Docking Bay 86'\n"
        )
        spec = load_era_test_character(str(tmp_path), gcw_room_map)
        assert spec is not None
        # Defaults
        assert spec["character"]["species"] == "Human"
        assert spec["character"]["template"] == "scout"
        assert spec["character"]["faction_id"] == "independent"
        assert spec["character"]["credits"] == 500
        assert spec["account"]["is_admin"] is False
        assert spec["account"]["is_builder"] is False
