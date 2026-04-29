# -*- coding: utf-8 -*-
"""F.1b — Era-aware ship loader regression tests.

Pre-F.1b, build_mos_eisley.py held SHIPS as a 7-entry Python tuple-list.
F.1b extracts to data/worlds/gcw/ships.yaml and adds engine/ship_loader.py
with load_era_ships(era_dir, room_name_map).

Tests cover:
  * Count parity (7 entries).
  * Per-entry round-trip of template_key, name, bay_room resolution.
  * Missing-room graceful skip.
  * Missing era.yaml / ships file → empty list, no crash.
"""
import os
import pytest

from engine.ship_loader import load_era_ships
from engine.world_loader import load_world_dry_run


@pytest.fixture(scope="module")
def gcw_room_map():
    bundle = load_world_dry_run("gcw")
    return {r.name: r.id for r in bundle.rooms.values()}


@pytest.fixture(scope="module")
def gcw_ships(gcw_room_map):
    era_dir = os.path.join(os.path.dirname(__file__), "..", "data", "worlds", "gcw")
    return load_era_ships(era_dir, gcw_room_map)


# ──────────────────────────────────────────────────────────────────────────


class TestCountAndShape:
    def test_seven_ships_loaded(self, gcw_ships):
        # 4 Tatooine + 1 Nar Shaddaa + 1 Kessel + 1 Corellia = 7
        assert len(gcw_ships) == 7

    def test_each_entry_has_required_fields(self, gcw_ships):
        for entry in gcw_ships:
            assert "template_key" in entry
            assert "name" in entry
            assert "bay_room" in entry
            assert "bay_room_idx" in entry
            assert "bridge_desc" in entry
            assert isinstance(entry["bay_room_idx"], int)


class TestEntryParity:
    """Spot-check several entries against the SHIPS literal that was deleted
    in F.1b. The 7 entries are stable and version-controlled, so checking a
    subset by name is sufficient regression coverage."""

    def test_rusty_mynock(self, gcw_ships):
        m = next(s for s in gcw_ships if s["name"] == "Rusty Mynock")
        assert m["template_key"] == "yt_1300"
        assert m["bay_room"] == "Docking Bay 94 - Pit Floor"
        assert "YT-1300" in m["bridge_desc"]

    def test_imperial_surplus_seven(self, gcw_ships):
        m = next(s for s in gcw_ships if s["name"] == "Imperial Surplus 7")
        assert m["template_key"] == "lambda_shuttle"
        assert m["bay_room"] == "Docking Bay 92"

    def test_corellian_dawn(self, gcw_ships):
        m = next(s for s in gcw_ships if s["name"] == "Corellian Dawn")
        assert m["template_key"] == "yt_1300"
        assert m["bay_room"] == "Coronet City - Starport Docking Bay"

    def test_one_z95_present(self, gcw_ships):
        z95s = [s for s in gcw_ships if s["template_key"] == "z_95"]
        assert len(z95s) == 1
        assert z95s[0]["name"] == "Dusty Hawk"


class TestEdgeCases:
    def test_missing_era_yaml_returns_empty(self, tmp_path, gcw_room_map):
        ships = load_era_ships(str(tmp_path), gcw_room_map)
        assert ships == []

    def test_no_ships_ref_returns_empty(self, tmp_path, gcw_room_map):
        # era.yaml exists but has no content_refs.ships
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\nera:\n  code: test\ncontent_refs:\n  zones: zones.yaml\n"
        )
        ships = load_era_ships(str(tmp_path), gcw_room_map)
        assert ships == []

    def test_unresolvable_bay_room_skipped(self, tmp_path, gcw_room_map):
        # ships.yaml refers to a nonexistent bay
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  ships: ships.yaml\n"
        )
        (tmp_path / "ships.yaml").write_text(
            "schema_version: 1\n"
            "ships:\n"
            "  - template_key: yt_1300\n"
            "    name: 'Phantom Ship'\n"
            "    bay_room: 'Nonexistent Bay'\n"
            "    bridge_desc: 'Nowhere.'\n"
            "  - template_key: yt_1300\n"
            "    name: 'Real Ship'\n"
            "    bay_room: 'Docking Bay 86'\n"
            "    bridge_desc: 'A real bay.'\n"
        )
        ships = load_era_ships(str(tmp_path), gcw_room_map)
        # Phantom Ship skipped, Real Ship loaded
        assert len(ships) == 1
        assert ships[0]["name"] == "Real Ship"

    def test_required_fields_validated(self, tmp_path, gcw_room_map):
        (tmp_path / "era.yaml").write_text(
            "schema_version: 1\ncontent_refs:\n  ships: ships.yaml\n"
        )
        (tmp_path / "ships.yaml").write_text(
            "schema_version: 1\n"
            "ships:\n"
            "  - template_key: yt_1300\n"
            "    bay_room: 'Docking Bay 86'\n"  # name missing
            "    bridge_desc: 'No name.'\n"
        )
        ships = load_era_ships(str(tmp_path), gcw_room_map)
        assert ships == []
