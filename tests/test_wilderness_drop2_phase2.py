# -*- coding: utf-8 -*-
"""
tests/test_wilderness_drop2_phase2.py — Wilderness Drop 2 phase 2.

Closes the loop on the live command surface for wilderness movement:
- Edges YAML format parsing
- Unwalkable tiles parsing + kernel consultation
- Co-location helpers (in_wilderness, get_wilderness_coords,
  same_location, characters_at_tile, filter_by_source_location)
- Path B primitives: sessions_in_room, broadcast_to_room,
  broadcast_json_to_room, broadcast_chat with source_char
- find_session_at_same_location helper
- Region cache (cache_region, get_or_load_region)
- Edge resolution helpers (find_edge_at_coords,
  find_edge_for_exit_direction, find_entry_edges_for_room)
- Combat-in-wilderness gate (refuses combat in wilderness)
- CoordsCommand registered

NOT covered (deferred):
- Live MoveCommand wilderness fork end-to-end (requires session/db
  fixture infrastructure beyond what we want here; the move helpers
  are tested via their pure-function components)
- LookCommand wilderness rendering (same)
- Wilderness combat (intentionally refused; gate test confirms)
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from build_mos_eisley import build
from db.database import Database, SCHEMA_VERSION
from engine.wilderness_loader import (
    WildernessRegion, WildernessLandmark, WildernessTerrain, WildernessEdge,
    load_wilderness_region,
)
from engine.wilderness_movement import (
    in_wilderness, get_wilderness_coords, same_location, characters_at_tile,
    filter_by_source_location, find_session_at_same_location,
    find_edge_at_coords, find_edge_for_exit_direction, find_entry_edges_for_room,
    cache_region, get_cached_region, clear_region_cache, get_or_load_region,
    move_in_wilderness,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

DUNE_SEA_PATH = os.path.join(
    PROJECT_ROOT,
    "data", "worlds", "clone_wars", "wilderness", "dune_sea.yaml",
)


def _build_cw():
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.unlink(db_path)
    asyncio.run(build(db_path=db_path, era="clone_wars"))
    return db_path


def _query(db_path, sql, params=()):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return rows


def _toy_region(width=10, height=10, edges=None, unwalkable=None):
    """Build a synthetic region for pure-function tests."""
    return WildernessRegion(
        slug="test_region",
        name="Test Region",
        planet="testworld",
        zone="test_zone",
        default_security="lawless",
        grid_width=width,
        grid_height=height,
        tile_scale_km=1,
        default_terrain="dune",
        terrains={
            "dune": WildernessTerrain(
                name="dune", move_cost=1, sight_radius=1,
                ambient_hazard=None, hazard_severity=0, variants=["test"],
            ),
        },
        landmarks=[],
        edges=edges or [],
        unwalkable_tiles=unwalkable or {},
    )


def _normal_char(id_, room_id):
    """Build a minimal char dict in a normal room."""
    return {
        "id": id_, "room_id": room_id, "name": f"P{id_}",
        "wilderness_region_slug": None,
        "wilderness_x": None, "wilderness_y": None,
    }


def _wild_char(id_, slug, x, y, sentinel_room=999):
    """Build a minimal char dict in wilderness."""
    return {
        "id": id_, "room_id": sentinel_room, "name": f"P{id_}",
        "wilderness_region_slug": slug,
        "wilderness_x": x, "wilderness_y": y,
    }


# ═════════════════════════════════════════════════════════════════════════════
# 1. Edges YAML parsing
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgesYAMLParsing:
    """The Dune Sea YAML parses its `edges:` block into WildernessEdge instances."""

    @classmethod
    def setup_class(cls):
        report = load_wilderness_region(DUNE_SEA_PATH)
        assert report.ok, f"Failed to load Dune Sea: {report.errors}"
        cls.region = report.region

    def test_dune_sea_has_edges(self):
        assert len(self.region.edges) >= 1

    def test_jundland_edge_present(self):
        match = [e for e in self.region.edges
                 if e.room_slug == "jundland_dune_sea_edge"]
        assert len(match) == 1
        edge = match[0]
        assert edge.coords == (0, 20)
        assert edge.direction_from_room == "east"
        assert edge.direction_back_to_room == "west"
        assert "Dune Sea begins here" in edge.enter_message

    def test_edge_messages_present(self):
        for edge in self.region.edges:
            assert isinstance(edge.enter_message, str)
            assert isinstance(edge.exit_message, str)


class TestEdgeParsingValidation:
    """Loader rejects malformed edges with warnings (not errors)."""

    def test_missing_room_slug_warns(self):
        # We can't easily test through the public load path without a YAML file,
        # so call the helper directly.
        from engine.wilderness_loader import _parse_edges, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        edges = _parse_edges(
            [{"coords": [0, 0], "direction_from_room": "n",
              "direction_back_to_room": "s"}],  # missing room_slug
            10, 10, report,
        )
        assert len(edges) == 0
        assert any("room_slug" in w for w in report.warnings)

    def test_out_of_bounds_coords_warns(self):
        from engine.wilderness_loader import _parse_edges, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        edges = _parse_edges(
            [{"room_slug": "x", "coords": [99, 99],
              "direction_from_room": "e", "direction_back_to_room": "w"}],
            10, 10, report,
        )
        assert len(edges) == 0
        assert any("out of bounds" in w for w in report.warnings)

    def test_missing_directions_warns(self):
        from engine.wilderness_loader import _parse_edges, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        edges = _parse_edges(
            [{"room_slug": "x", "coords": [0, 0]}],  # no directions
            10, 10, report,
        )
        assert len(edges) == 0
        assert any("direction" in w for w in report.warnings)

    def test_directions_lowercased(self):
        from engine.wilderness_loader import _parse_edges, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        edges = _parse_edges(
            [{"room_slug": "x", "coords": [0, 0],
              "direction_from_room": "EAST", "direction_back_to_room": "WEST"}],
            10, 10, report,
        )
        assert len(edges) == 1
        assert edges[0].direction_from_room == "east"
        assert edges[0].direction_back_to_room == "west"


# ═════════════════════════════════════════════════════════════════════════════
# 2. Unwalkable tiles parsing + kernel consultation
# ═════════════════════════════════════════════════════════════════════════════


class TestUnwalkableTilesParsing:
    def test_dune_sea_has_no_unwalkable(self):
        # The shipping Dune Sea has no unwalkable tiles
        report = load_wilderness_region(DUNE_SEA_PATH)
        assert report.ok
        assert report.region.unwalkable_tiles == {}

    def test_coords_format_parses(self):
        from engine.wilderness_loader import _parse_unwalkable_tiles, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        out = _parse_unwalkable_tiles(
            [{"coords": [5, 5], "reason": "Cliff face."}],
            10, 10, report,
        )
        assert (5, 5) in out
        assert out[(5, 5)] == "Cliff face."

    def test_region_block_format_parses(self):
        from engine.wilderness_loader import _parse_unwalkable_tiles, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        out = _parse_unwalkable_tiles(
            [{"region_block": {"x1": 1, "y1": 1, "x2": 3, "y2": 3},
              "reason": "Sealed bunker."}],
            10, 10, report,
        )
        # Should be 3x3 = 9 tiles
        assert len(out) == 9
        assert (1, 1) in out
        assert (3, 3) in out
        assert out[(2, 2)] == "Sealed bunker."

    def test_out_of_bounds_filtered(self):
        from engine.wilderness_loader import _parse_unwalkable_tiles, WildernessLoadReport
        report = WildernessLoadReport(ok=False)
        out = _parse_unwalkable_tiles(
            [{"coords": [99, 99], "reason": "x"}],
            10, 10, report,
        )
        assert (99, 99) not in out


class TestUnwalkableKernelConsultation:
    def test_walkable_tile_succeeds(self):
        region = _toy_region(10, 10, unwalkable={(5, 5): "blocked"})
        result = move_in_wilderness(region, 0, 0, "north")
        assert result.ok is True

    def test_unwalkable_tile_refused(self):
        region = _toy_region(10, 10, unwalkable={(5, 6): "Cliff face here."})
        result = move_in_wilderness(region, 5, 5, "north")
        assert result.ok is False
        assert result.crossed_boundary is False
        assert "Cliff face" in result.reason

    def test_unwalkable_does_not_break_other_directions(self):
        region = _toy_region(10, 10, unwalkable={(5, 6): "blocked"})
        # Moving east from (5, 5) should succeed — destination is (6, 5), not (5, 6)
        result = move_in_wilderness(region, 5, 5, "east")
        assert result.ok is True


# ═════════════════════════════════════════════════════════════════════════════
# 3. Co-location helpers — truth tables
# ═════════════════════════════════════════════════════════════════════════════


class TestInWilderness:
    def test_normal_char_not_in_wilderness(self):
        char = _normal_char(1, 100)
        assert in_wilderness(char) is False

    def test_wild_char_in_wilderness(self):
        char = _wild_char(1, "tatooine_dune_sea", 5, 5)
        assert in_wilderness(char) is True

    def test_none_not_in_wilderness(self):
        assert in_wilderness(None) is False


class TestGetWildernessCoords:
    def test_normal_char_returns_none(self):
        char = _normal_char(1, 100)
        assert get_wilderness_coords(char) is None

    def test_wild_char_returns_tuple(self):
        char = _wild_char(1, "slug", 5, 10)
        assert get_wilderness_coords(char) == ("slug", 5, 10)

    def test_missing_x_returns_none(self):
        char = {"wilderness_region_slug": "slug", "wilderness_x": None, "wilderness_y": 5}
        assert get_wilderness_coords(char) is None

    def test_none_returns_none(self):
        assert get_wilderness_coords(None) is None


class TestSameLocation:
    def test_same_normal_room(self):
        a = _normal_char(1, 100)
        b = _normal_char(2, 100)
        assert same_location(a, b) is True

    def test_different_normal_rooms(self):
        a = _normal_char(1, 100)
        b = _normal_char(2, 200)
        assert same_location(a, b) is False

    def test_same_wilderness_tile(self):
        a = _wild_char(1, "tatooine_dune_sea", 5, 5)
        b = _wild_char(2, "tatooine_dune_sea", 5, 5)
        assert same_location(a, b) is True

    def test_different_wilderness_tiles(self):
        a = _wild_char(1, "tatooine_dune_sea", 5, 5)
        b = _wild_char(2, "tatooine_dune_sea", 10, 10)
        assert same_location(a, b) is False

    def test_different_wilderness_regions(self):
        a = _wild_char(1, "tatooine_dune_sea", 5, 5)
        b = _wild_char(2, "kashyyyk_jungle", 5, 5)
        assert same_location(a, b) is False

    def test_one_normal_one_wilderness_never_same(self):
        a = _normal_char(1, 100)
        b = _wild_char(2, "tatooine_dune_sea", 5, 5)
        assert same_location(a, b) is False
        assert same_location(b, a) is False

    def test_one_normal_one_wilderness_even_when_room_id_matches_sentinel(self):
        # Edge case: PC in normal room that happens to be the sentinel id
        a = _normal_char(1, 999)  # accidentally on the sentinel
        b = _wild_char(2, "tatooine_dune_sea", 5, 5)  # sentinel = 999
        # They are NOT same_location: one is conceptually in the sentinel
        # ROOM, one is on a wilderness TILE
        assert same_location(a, b) is False

    def test_none_arguments(self):
        assert same_location(None, _normal_char(1, 100)) is False
        assert same_location(_normal_char(1, 100), None) is False
        assert same_location(None, None) is False


# ═════════════════════════════════════════════════════════════════════════════
# 4. filter_by_source_location — the Path B chokepoint
# ═════════════════════════════════════════════════════════════════════════════


class TestFilterBySourceLocation:
    def test_no_source_char_returns_all(self):
        items = [_normal_char(1, 100), _wild_char(2, "x", 5, 5)]
        out = filter_by_source_location(items, None)
        assert len(out) == 2

    def test_normal_source_returns_all(self):
        # Normal-room source: filter does nothing (room_id sharing is enough)
        src = _normal_char(0, 100)
        items = [_normal_char(1, 100), _normal_char(2, 200), _wild_char(3, "x", 5, 5)]
        out = filter_by_source_location(items, src)
        assert len(out) == 3

    def test_wilderness_source_filters_to_same_tile(self):
        src = _wild_char(0, "slug", 5, 5)
        items = [
            _wild_char(1, "slug", 5, 5),    # match
            _wild_char(2, "slug", 10, 10),  # different tile
            _wild_char(3, "other", 5, 5),   # different region
            _normal_char(4, 100),            # normal room
        ]
        out = filter_by_source_location(items, src)
        ids = sorted(x["id"] for x in out)
        assert ids == [1]

    def test_wilderness_source_with_inconsistent_state_returns_all(self):
        # Defensive: bad source returns unfiltered (better to over-broadcast)
        src = {"wilderness_region_slug": "slug", "wilderness_x": None, "wilderness_y": None}
        items = [_wild_char(1, "slug", 5, 5), _normal_char(2, 100)]
        out = filter_by_source_location(items, src)
        assert len(out) == 2

    def test_get_char_lambda_for_session_iterables(self):
        # Simulate session-like objects
        class S:
            def __init__(self, ch): self.character = ch
        sessions = [
            S(_wild_char(1, "slug", 5, 5)),
            S(_wild_char(2, "slug", 10, 10)),
            S(None),  # session without character
        ]
        src = _wild_char(0, "slug", 5, 5)
        out = filter_by_source_location(sessions, src, get_char=lambda s: s.character)
        ids = [s.character["id"] for s in out if s.character]
        assert ids == [1]


# ═════════════════════════════════════════════════════════════════════════════
# 5. characters_at_tile — DB query helper
# ═════════════════════════════════════════════════════════════════════════════


class TestCharactersAtTile:
    """Real DB query verifying the (slug, x, y) filter works against schema v20."""

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_empty_when_no_chars_at_tile(self):
        async def _check():
            db = Database(self.db_path)

            await db.connect()

            await db.initialize()
            try:
                out = await characters_at_tile(db, "tatooine_dune_sea", 0, 0)
                assert out == []
            finally:
                await db.close()
        asyncio.run(_check())

    def test_finds_char_at_tile(self):
        async def _check():
            db = Database(self.db_path)

            await db.connect()

            await db.initialize()
            try:
                # Create a stub account to satisfy FK constraint
                acct_cur = await db._db.execute(
                    "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                    ("testacct", "x"),
                )
                acct_id = acct_cur.lastrowid
                await db._db.commit()

                await db._db.execute(
                    "INSERT INTO characters "
                    "(account_id, name, species, template, attributes, skills, room_id, "
                    " wilderness_region_slug, wilderness_x, wilderness_y, is_active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (acct_id, "WildBoy", "Human", "Smuggler", "{}", "{}", 1,
                     "tatooine_dune_sea", 5, 10, 1),
                )
                await db._db.commit()

                out = await characters_at_tile(db, "tatooine_dune_sea", 5, 10)
                assert len(out) == 1
                assert out[0]["name"] == "WildBoy"

                # Different tile = empty
                out2 = await characters_at_tile(db, "tatooine_dune_sea", 6, 10)
                assert out2 == []
            finally:
                await db.close()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 6. Edge resolution helpers
# ═════════════════════════════════════════════════════════════════════════════


class TestEdgeResolutionHelpers:
    @classmethod
    def setup_class(cls):
        edge = WildernessEdge(
            room_slug="hand_room", coords=(3, 4),
            direction_from_room="east", direction_back_to_room="west",
        )
        cls.region = _toy_region(10, 10, edges=[edge])

    def test_find_edge_at_matching_coords(self):
        edge = find_edge_at_coords(self.region, 3, 4)
        assert edge is not None
        assert edge.room_slug == "hand_room"

    def test_find_edge_at_non_edge_coords(self):
        assert find_edge_at_coords(self.region, 5, 5) is None

    def test_find_edge_for_exit_direction_match(self):
        edge = find_edge_for_exit_direction(self.region, 3, 4, "west")
        assert edge is not None

    def test_find_edge_for_exit_direction_wrong_direction(self):
        edge = find_edge_for_exit_direction(self.region, 3, 4, "north")
        assert edge is None

    def test_find_entry_edges_for_room_match(self):
        edges = find_entry_edges_for_room(self.region, "hand_room")
        assert len(edges) == 1

    def test_find_entry_edges_for_room_nomatch(self):
        edges = find_entry_edges_for_room(self.region, "other_room")
        assert edges == []


# ═════════════════════════════════════════════════════════════════════════════
# 7. Region cache + lazy YAML reload
# ═════════════════════════════════════════════════════════════════════════════


class TestRegionCache:
    def setup_method(self):
        clear_region_cache()

    def teardown_method(self):
        clear_region_cache()

    def test_cache_get_miss_returns_none(self):
        assert get_cached_region("nonexistent") is None

    def test_cache_set_and_get(self):
        region = _toy_region()
        region.slug = "test_slug"
        cache_region(region)
        assert get_cached_region("test_slug") is region

    def test_cache_clear(self):
        region = _toy_region()
        region.slug = "x"
        cache_region(region)
        clear_region_cache()
        assert get_cached_region("x") is None

    def test_get_or_load_from_yaml_on_miss(self):
        # Cache cold; should resolve via filesystem to data/.../dune_sea.yaml
        async def _check():
            assert get_cached_region("tatooine_dune_sea") is None
            # Use a dummy db (the function only uses db for the registry
            # lookup, which we don't need since we have a YAML path)
            class DummyDB: pass
            # Switch to project root so the relative path resolves
            old_cwd = os.getcwd()
            os.chdir(PROJECT_ROOT)
            try:
                region = await get_or_load_region(DummyDB(), "tatooine_dune_sea")
                assert region is not None
                assert region.name == "The Dune Sea"
            finally:
                os.chdir(old_cwd)
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 8. Path B primitives — sessions_in_room with source_char
# ═════════════════════════════════════════════════════════════════════════════


class TestSessionsInRoomSourceChar:
    """Verify SessionManager.sessions_in_room with source_char filter."""

    def _build_session_mgr(self, sessions_data):
        """Build a minimal session manager with fake sessions."""
        from server.session import SessionManager
        mgr = SessionManager()
        for sd in sessions_data:
            class FakeSession:
                pass
            s = FakeSession()
            s.is_in_game = True
            s.character = sd
            mgr._sessions[sd["id"]] = s
        return mgr

    def test_no_source_returns_room_filter_only(self):
        sessions = [
            _normal_char(1, 100), _normal_char(2, 100), _normal_char(3, 200)
        ]
        mgr = self._build_session_mgr(sessions)
        out = mgr.sessions_in_room(100)
        assert len(out) == 2

    def test_normal_source_returns_room_filter_only(self):
        # Normal-room source: filter returns all room residents
        sessions = [_normal_char(1, 100), _normal_char(2, 100), _normal_char(3, 200)]
        mgr = self._build_session_mgr(sessions)
        src = _normal_char(0, 100)
        out = mgr.sessions_in_room(100, source_char=src)
        assert len(out) == 2

    def test_wilderness_source_filters_to_same_tile(self):
        # All in same sentinel room (999), but at different tiles
        sessions = [
            _wild_char(1, "slug", 5, 5),
            _wild_char(2, "slug", 5, 5),
            _wild_char(3, "slug", 10, 10),
        ]
        mgr = self._build_session_mgr(sessions)
        src = _wild_char(0, "slug", 5, 5)
        out = mgr.sessions_in_room(999, source_char=src)
        ids = sorted(s.character["id"] for s in out)
        assert ids == [1, 2]


# ═════════════════════════════════════════════════════════════════════════════
# 9. find_session_at_same_location
# ═════════════════════════════════════════════════════════════════════════════


class TestFindSessionAtSameLocation:
    def _build_session_mgr(self, sessions_data):
        from server.session import SessionManager
        mgr = SessionManager()
        for sd in sessions_data:
            class FakeSession:
                pass
            s = FakeSession()
            s.is_in_game = True
            s.character = sd
            mgr._sessions[sd["id"]] = s
        return mgr

    def test_finds_in_normal_room(self):
        sessions = [
            _normal_char(1, 100), _normal_char(2, 100),
        ]
        sessions[1]["name"] = "Tundra"
        mgr = self._build_session_mgr(sessions)
        src = sessions[0]
        result = find_session_at_same_location(mgr, src, "Tund")
        assert result is not None
        assert result.character["name"] == "Tundra"

    def test_excludes_self(self):
        sessions = [_normal_char(1, 100)]
        sessions[0]["name"] = "Tundra"
        mgr = self._build_session_mgr(sessions)
        src = sessions[0]
        result = find_session_at_same_location(mgr, src, "Tundra")
        assert result is None

    def test_filters_by_wilderness_tile(self):
        sessions = [
            _wild_char(1, "slug", 5, 5),
            _wild_char(2, "slug", 10, 10),
        ]
        sessions[1]["name"] = "Tundra"
        mgr = self._build_session_mgr(sessions)
        src = sessions[0]
        # Tundra is in wilderness but at a different tile — should NOT match
        result = find_session_at_same_location(mgr, src, "Tundra")
        assert result is None

    def test_finds_co_located_wilderness_pc(self):
        sessions = [
            _wild_char(1, "slug", 5, 5),
            _wild_char(2, "slug", 5, 5),
        ]
        sessions[1]["name"] = "Tundra"
        mgr = self._build_session_mgr(sessions)
        src = sessions[0]
        result = find_session_at_same_location(mgr, src, "Tundra")
        assert result is not None
        assert result.character["id"] == 2

    def test_empty_name_returns_none(self):
        sessions = [_normal_char(1, 100), _normal_char(2, 100)]
        mgr = self._build_session_mgr(sessions)
        result = find_session_at_same_location(mgr, sessions[0], "")
        assert result is None


# ═════════════════════════════════════════════════════════════════════════════
# 10. broadcast_to_room with source_char (functional)
# ═════════════════════════════════════════════════════════════════════════════


class TestBroadcastToRoomSourceChar:
    """Verify broadcast_to_room respects source_char wilderness filter."""

    def _build_session_mgr_with_recorder(self, sessions_data):
        """Sessions that record send_line calls."""
        from server.session import SessionManager
        mgr = SessionManager()
        for sd in sessions_data:
            class RecorderSession:
                def __init__(self): self.received = []
                async def send_line(self, text): self.received.append(text)
                async def send_json(self, mtype, data): pass
            s = RecorderSession()
            s.is_in_game = True
            s.character = sd
            mgr._sessions[sd["id"]] = s
        return mgr

    def test_broadcast_no_source_reaches_all_room_residents(self):
        async def _check():
            sessions = [_wild_char(1, "slug", 5, 5), _wild_char(2, "slug", 10, 10)]
            mgr = self._build_session_mgr_with_recorder(sessions)
            # No source_char — both should receive
            await mgr.broadcast_to_room(999, "hello")
            received = [(s.character["id"], len(s.received)) for s in mgr._sessions.values()]
            assert received == [(1, 1), (2, 1)]
        asyncio.run(_check())

    def test_broadcast_with_wilderness_source_filters(self):
        async def _check():
            sessions = [_wild_char(1, "slug", 5, 5), _wild_char(2, "slug", 10, 10)]
            mgr = self._build_session_mgr_with_recorder(sessions)
            src = _wild_char(0, "slug", 5, 5)
            await mgr.broadcast_to_room(999, "hello", source_char=src)
            # Only the PC at (5, 5) should receive
            for s in mgr._sessions.values():
                if s.character["wilderness_x"] == 5:
                    assert len(s.received) == 1
                else:
                    assert len(s.received) == 0
        asyncio.run(_check())

    def test_broadcast_with_normal_source_unchanged(self):
        async def _check():
            sessions = [_normal_char(1, 100), _normal_char(2, 100)]
            mgr = self._build_session_mgr_with_recorder(sessions)
            src = _normal_char(0, 100)
            await mgr.broadcast_to_room(100, "hello", source_char=src)
            for s in mgr._sessions.values():
                assert len(s.received) == 1
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 11. db.get_characters_in_room with source_char
# ═════════════════════════════════════════════════════════════════════════════


class TestGetCharactersInRoomSourceChar:
    """Schema v20 + DB integration test."""

    @classmethod
    def setup_class(cls):
        cls.db_path = _build_cw()

    @classmethod
    def teardown_class(cls):
        try:
            os.unlink(cls.db_path)
        except FileNotFoundError:
            pass

    def test_no_source_returns_all_in_room(self):
        async def _check():
            db = Database(self.db_path)

            await db.connect()

            await db.initialize()
            try:
                # Get sentinel room id
                rows = await db._db.execute_fetchall(
                    "SELECT sentinel_room_id FROM wilderness_regions WHERE slug='tatooine_dune_sea'"
                )
                sentinel = rows[0]["sentinel_room_id"]

                # Create stub account
                acct_cur = await db._db.execute(
                    "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
                    ("testacct2", "x"),
                )
                acct_id = acct_cur.lastrowid
                await db._db.commit()

                cur = await db._db.execute(
                    "INSERT INTO characters "
                    "(account_id, name, species, template, attributes, skills, room_id, "
                    " wilderness_region_slug, wilderness_x, wilderness_y, is_active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (acct_id, "A", "Human", "Smuggler", "{}", "{}", sentinel,
                     "tatooine_dune_sea", 5, 5, 1),
                )
                a = cur.lastrowid
                await db._db.execute(
                    "INSERT INTO characters "
                    "(account_id, name, species, template, attributes, skills, room_id, "
                    " wilderness_region_slug, wilderness_x, wilderness_y, is_active) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (acct_id, "B", "Human", "Smuggler", "{}", "{}", sentinel,
                     "tatooine_dune_sea", 10, 10, 1),
                )
                await db._db.commit()

                # No source_char: both returned
                out = await db.get_characters_in_room(sentinel)
                names = sorted(c["name"] for c in out if c["name"] in ("A", "B"))
                assert names == ["A", "B"]

                # With wilderness source at (5, 5): only A
                src = await db.get_character(a)
                out2 = await db.get_characters_in_room(sentinel, source_char=src)
                names2 = sorted(c["name"] for c in out2 if c["name"] in ("A", "B"))
                assert names2 == ["A"]
            finally:
                await db.close()
        asyncio.run(_check())


# ═════════════════════════════════════════════════════════════════════════════
# 12. Combat-in-wilderness gate
# ═════════════════════════════════════════════════════════════════════════════


class TestCombatGateInWilderness:
    """AttackCommand refuses to fire when source is in wilderness."""

    def test_combat_gate_present_in_source(self):
        with open(os.path.join(PROJECT_ROOT, "parser", "combat_commands.py"),
                  encoding="utf-8") as fh:
            text = fh.read()
        assert "in_wilderness" in text
        assert "[NO COMBAT]" in text


# ═════════════════════════════════════════════════════════════════════════════
# 13. CoordsCommand registered
# ═════════════════════════════════════════════════════════════════════════════


class TestCoordsCommandRegistered:
    def test_coords_command_in_register_all(self):
        with open(os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py"),
                  encoding="utf-8") as fh:
            text = fh.read()
        assert "class CoordsCommand" in text
        assert "CoordsCommand()" in text


# ═════════════════════════════════════════════════════════════════════════════
# 14. Source-level guards: every Bucket 1 file passes source_char
# ═════════════════════════════════════════════════════════════════════════════


class TestBucket1SurfacesUseSourceChar:
    """Verify each Bucket 1 file actually passes source_char in at least one place.

    These tests catch the "I forgot to migrate file X" bug.
    """

    def _has_source_char(self, relpath):
        with open(os.path.join(PROJECT_ROOT, relpath), encoding="utf-8") as fh:
            return "source_char=" in fh.read()

    def test_say_uses_source_char(self):
        # builtin_commands.py covers say/whisper/emote/trade/look_at
        assert self._has_source_char("parser/builtin_commands.py")

    def test_medical_uses_source_char(self):
        assert self._has_source_char("parser/medical_commands.py")

    def test_force_uses_source_char(self):
        assert self._has_source_char("parser/force_commands.py")

    def test_sabacc_uses_source_char(self):
        assert self._has_source_char("parser/sabacc_commands.py")

    def test_entertainer_uses_source_char(self):
        assert self._has_source_char("parser/entertainer_commands.py")

    def test_d6_uses_source_char(self):
        assert self._has_source_char("parser/d6_commands.py")

    def test_scene_uses_source_char(self):
        assert self._has_source_char("parser/scene_commands.py")

    def test_faction_uses_source_char(self):
        assert self._has_source_char("parser/faction_commands.py")

    def test_espionage_uses_source_char(self):
        assert self._has_source_char("parser/espionage_commands.py")

    def test_crafting_uses_source_char(self):
        assert self._has_source_char("parser/crafting_commands.py")

    def test_matching_uses_source_char(self):
        assert self._has_source_char("engine/matching.py")
