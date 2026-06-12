"""
test_poi_feed.py — dynamic POI feed (bounty/boss entities on the map).

The map's L_Entities layer renders ``dynamic.poi`` glyphs (vendor/mission/
bounty/objective/anomaly_t1..t3). Until now ``dynamic.poi`` was fed ONLY from
static authored landmarks; runtime entities (bounty targets) never reached it.
This wires a live feed:
  · server/session.py _build_area_pois maps posted bounty contracts whose
    target_room_id is in the player's covered area to {kind:"bounty", x, y}
    render coords (same resolve_area_room_ids bridge as contacts), and stamps
    hud["pois"]. Failure-tolerant.
  · static/spa/m3_adapter.js appends server geom.pois (Y-flipped) to the
    landmark-derived POIs.
  · static/client.html stores data.pois → _sw_areaGeom.pois on both paths.

The server method runs against fakes; the adapter merge runs the REAL extracted
_buildDynamic under node.
"""
from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SESSION_PY = REPO_ROOT / "server" / "session.py"
ADAPTER_JS = REPO_ROOT / "static" / "spa" / "m3_adapter.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

import sys
sys.path.insert(0, str(REPO_ROOT))


class _FakeEntry:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class _FakeRegistry:
    def __init__(self, m):
        self._m = m

    async def resolve_area_room_ids(self, area_key, db):
        return self._m


def _make_session():
    from server.session import Session
    return Session.__new__(Session)  # bare instance; we only call the method


def test_build_area_pois_maps_covered_bounties(monkeypatch):
    import engine.bounty_board as bb
    sess = _make_session()
    room_map = {101: _FakeEntry(10, 20), 102: _FakeEntry(30, 40)}

    # Use the monkeypatch fixture (auto-restored after the test) so this fake
    # board never leaks into later tests in the session -- e.g.
    # test_singleton_bindings, which asserts GameServer.bounty_board is the
    # SAME object the real get_bounty_board() returns.
    monkeypatch.setattr(bb, "get_bounty_board", lambda: type("B", (), {
        "posted_contracts": lambda self: [
            type("C", (), {"target_room_id": 101})(),   # covered
            type("C", (), {"target_room_id": 999})(),   # not in area
            type("C", (), {"target_room_id": None})(),  # no room
        ],
    })())

    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="tatooine.mos_eisley"))
    assert pois == [{"kind": "bounty", "x": 10, "y": 20}], pois


def test_build_area_pois_empty_room_map():
    sess = _make_session()
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry({}), area_key="x"))
    assert pois == []


def test_build_area_pois_swallows_board_errors(monkeypatch):
    import engine.bounty_board as bb
    sess = _make_session()

    def boom():
        raise RuntimeError("boom")
    # monkeypatch fixture auto-restores get_bounty_board after the test, so the
    # raise-getter cannot leak into later tests (test_singleton_bindings would
    # otherwise call this boom()).
    monkeypatch.setattr(bb, "get_bounty_board", boom)
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry({1: _FakeEntry(0, 0)}), area_key="x"))
    assert pois == []  # error swallowed, not raised into the HUD


def test_server_stamps_pois_on_hud():
    src = SESSION_PY.read_text(encoding="utf-8")
    assert "async def _build_area_pois" in src
    assert re.search(r'hud\["pois"\]\s*=\s*pois', src), "augmentation must stamp hud['pois']"
    # v1 source is bounties via the board
    body = src[src.index("async def _build_area_pois"):][:2500]
    assert "from engine.bounty_board import get_bounty_board" in body
    assert '"kind": "bounty"' in body
    assert "target_room_id" in body


def test_client_stores_pois():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    assert html.count("window._sw_areaGeom.pois = data.pois") == 2, (
        "both client paths (area-transition + per-tick) must store data.pois"
    )


def test_adapter_merges_server_pois():
    js = ADAPTER_JS.read_text(encoding="utf-8")

    def ext(name):
        i = js.index("function " + name + "(")
        d = 0
        st = False
        for k in range(i, len(js)):
            c = js[k]
            if c == "{":
                d += 1
                st = True
            elif c == "}":
                d -= 1
                if st and d == 0:
                    return js[i:k + 1]
        raise AssertionError("brace match failed: " + name)

    body = ext("_buildDynamic")
    assert "geom.pois" in body, "_buildDynamic must read server geom.pois"
    assert "flipY(sp.y)" in body, "server POIs must be Y-flipped to match landmarks"


# ════════════════════════════════════════════════════════════════════════════
# Anomaly POI sweep — wilderness anomalies (anomaly_t1/t2/t3, incl. the Tier-3
# world boss) anchored to landmark rooms in the player's covered area. The
# render path (MK_AnomalyT1/2/3, L_Entities poiMap, adapter merge) already
# exists; this exercises the new server-side enumeration. Anomalies are keyed
# by region, so the sweep derives the covered regions from each room entry's
# region_slug (captured for free in resolve_area_room_ids) — no per-tick DB.
# ════════════════════════════════════════════════════════════════════════════

import types  # noqa: E402

from engine.area_loader import (  # noqa: E402
    AreaGeometryRegistry,
    _RoomLookupEntry,
)

AREA_LOADER_PY = REPO_ROOT / "engine" / "area_loader.py"
COMPOSITION_JS = REPO_ROOT / "static" / "spa" / "m3_composition_engine.js"


class _FakeEntryR:
    """Like _FakeEntry, but also carries a region_slug — as the real
    _RoomLookupEntry now does — so the anomaly sweep can group by region."""
    def __init__(self, x, y, region_slug=None):
        self.x = x
        self.y = y
        self.region_slug = region_slug


def _anomaly(anchor_room_id, tier=1):
    return types.SimpleNamespace(anchor_room_id=anchor_room_id, tier=tier)


def _quiet_bounties(monkeypatch):
    """Force an empty bounty board so anomaly assertions are isolated from
    whatever the previous test left on engine.bounty_board (the existing
    error test assigns a raising board without restoring it)."""
    import engine.bounty_board as bb
    monkeypatch.setattr(
        bb, "get_bounty_board",
        lambda: types.SimpleNamespace(posted_contracts=lambda: []),
    )


def test_build_area_pois_maps_covered_anomalies(monkeypatch):
    import engine.wilderness_anomalies as wa
    _quiet_bounties(monkeypatch)
    sess = _make_session()
    room_map = {
        201: _FakeEntryR(10, 20, region_slug="dune_sea"),
        202: _FakeEntryR(30, 40, region_slug="dune_sea"),
    }
    monkeypatch.setattr(wa, "get_anomalies_for_region", lambda region, **kw: (
        [_anomaly(201, tier=1), _anomaly(202, tier=3)]
        if region == "dune_sea" else []
    ))
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map),
        area_key="tatooine.dune_sea"))
    assert {"kind": "anomaly_t1", "x": 10, "y": 20} in pois
    assert {"kind": "anomaly_t3", "x": 30, "y": 40} in pois
    assert len(pois) == 2, pois


def test_build_area_pois_anomaly_outside_view_skipped(monkeypatch):
    import engine.wilderness_anomalies as wa
    _quiet_bounties(monkeypatch)
    sess = _make_session()
    room_map = {201: _FakeEntryR(10, 20, region_slug="dune_sea")}
    # Anchored on room 999 — not part of this area's covered rooms.
    monkeypatch.setattr(wa, "get_anomalies_for_region",
                        lambda region, **kw: [_anomaly(999, tier=2)])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_anomaly_tier_clamped(monkeypatch):
    import engine.wilderness_anomalies as wa
    _quiet_bounties(monkeypatch)
    sess = _make_session()
    room_map = {
        1: _FakeEntryR(0, 0, region_slug="r"),
        2: _FakeEntryR(5, 5, region_slug="r"),
    }
    # Out-of-range tiers clamp into the renderable 1..3 band.
    monkeypatch.setattr(wa, "get_anomalies_for_region", lambda region, **kw: [
        _anomaly(1, tier=0), _anomaly(2, tier=7)])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert sorted(p["kind"] for p in pois) == ["anomaly_t1", "anomaly_t3"], pois


def test_build_area_pois_city_region_none_no_anomalies(monkeypatch):
    """City rooms have region_slug=None → no regions collected → the
    anomaly accessor is never consulted → no anomaly glyphs in a city."""
    import engine.wilderness_anomalies as wa
    _quiet_bounties(monkeypatch)
    sess = _make_session()
    room_map = {1: _FakeEntryR(0, 0, region_slug=None)}
    called = {"n": 0}

    def spy(region, **kw):
        called["n"] += 1
        return [_anomaly(1, tier=1)]

    monkeypatch.setattr(wa, "get_anomalies_for_region", spy)
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map),
        area_key="tatooine.mos_eisley"))
    assert pois == []
    assert called["n"] == 0, "no regions → anomaly accessor must not be called"


def test_build_area_pois_swallows_anomaly_errors(monkeypatch):
    """An anomaly-enumeration error must not break the HUD, and must not
    discard bounty POIs gathered before it."""
    import engine.bounty_board as bb
    import engine.wilderness_anomalies as wa
    sess = _make_session()
    room_map = {201: _FakeEntryR(10, 20, region_slug="dune_sea")}
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=201)]))

    def boom(region, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(wa, "get_anomalies_for_region", boom)
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [{"kind": "bounty", "x": 10, "y": 20}], pois


def test_build_area_pois_bounty_and_anomaly_coexist(monkeypatch):
    import engine.bounty_board as bb
    import engine.wilderness_anomalies as wa
    sess = _make_session()
    room_map = {
        201: _FakeEntryR(10, 20, region_slug="dune_sea"),
        202: _FakeEntryR(30, 40, region_slug="dune_sea"),
    }
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=201)]))
    monkeypatch.setattr(wa, "get_anomalies_for_region",
                        lambda region, **kw: [_anomaly(202, tier=2)])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert {"kind": "bounty", "x": 10, "y": 20} in pois
    assert {"kind": "anomaly_t2", "x": 30, "y": 40} in pois
    assert len(pois) == 2, pois


# ── region_slug capture (registry side) ─────────────────────────────────────

def test_resolve_area_room_ids_captures_region_slug():
    """resolve_area_room_ids records the room's wilderness_region_id on each
    _RoomLookupEntry, from the row it already fetches — no extra DB call."""
    reg = AreaGeometryRegistry()
    reg._areas["test.area"] = types.SimpleNamespace(rooms=[
        types.SimpleNamespace(id=0, x=1.0, y=2.0, slug="alpha"),
        types.SimpleNamespace(id=1, x=3.0, y=4.0, slug="beta"),
        types.SimpleNamespace(id=2, x=5.0, y=6.0, slug="gamma"),
    ])
    rows = {
        "alpha": {"id": 101, "wilderness_region_id": "dune_sea"},
        "beta":  {"id": 102, "wilderness_region_id": "dune_sea"},
        "gamma": {"id": 103, "wilderness_region_id": None},   # city room
    }

    class _DB:
        async def get_room_by_slug(self, slug):
            return rows.get(slug)

    out = asyncio.run(reg.resolve_area_room_ids("test.area", _DB()))
    assert out[101].region_slug == "dune_sea"
    assert out[102].region_slug == "dune_sea"
    assert out[103].region_slug is None


def test_room_lookup_entry_region_slug_defaults_none():
    """Back-compat: the slug-index path (no DB row) leaves region_slug None."""
    e = _RoomLookupEntry(area_key="a", render_room_id=0, x=0.0, y=0.0)
    assert e.region_slug is None


# ── Static guards: source wiring + render path the feed depends on ──────────

def test_server_wires_anomaly_sweep():
    body = SESSION_PY.read_text(encoding="utf-8")
    body = body[body.index("async def _build_area_pois"):][:3500]
    assert ("from engine.wilderness_anomalies import "
            "get_anomalies_for_region") in body
    assert "anchor_room_id" in body
    assert "anomaly_t" in body
    assert "region_slug" in body, "sweep must group by entry.region_slug"


def test_area_loader_captures_region_on_entry():
    src = AREA_LOADER_PY.read_text(encoding="utf-8")
    assert "region_slug" in src, "_RoomLookupEntry must carry region_slug"
    assert 'row.get("wilderness_region_id")' in src, (
        "resolve_area_room_ids must capture wilderness_region_id from the row")


def test_composition_engine_renders_anomaly_kinds():
    """The feed emits anomaly_t1/t2/t3; L_Entities' poiMap must map all
    three to markers or the glyphs silently vanish."""
    ce = COMPOSITION_JS.read_text(encoding="utf-8")
    for k in ("anomaly_t1", "anomaly_t2", "anomaly_t3"):
        assert k in ce, "L_Entities poiMap missing " + k


# ════════════════════════════════════════════════════════════════════════════
# Objective POI sweep — the player's accepted-mission destination(s).
#
# Unlike the bounty/anomaly sweeps (area-state: everything huntable/anomalous in
# view, for everyone), an objective is PERSONAL — it's where THIS character's
# accepted mission says to go. The sweep reads self.character, finds that
# character's ACCEPTED missions on the board, and places the green-star
# "objective" glyph (MK_Objective) on each destination room that's in view.
#
# Data side: a mission's destination_room_id is populated by the board generator
# from a real DB room (stored as a string). Missions without one — space
# missions (zone targets, not ground rooms) and any generated with no room list
# — carry None and are skipped. The render path (MK_Objective + L_Entities
# poiMap "objective" + adapter pass-through) already exists; this exercises the
# new server-side enumeration only.
# ════════════════════════════════════════════════════════════════════════════

from engine.missions import (  # noqa: E402
    MissionStatus,
    MissionBoard,
    BOARD_MAX,
)

MISSIONS_PY = REPO_ROOT / "engine" / "missions.py"


def _mission(accepted_by, status, destination_room_id):
    """A minimal stand-in for engine.missions.Mission with just the fields the
    objective sweep touches. destination_room_id is a *string* in production
    (str(room["id"])), so tests pass strings to exercise the str→int bridge."""
    return types.SimpleNamespace(
        accepted_by=accepted_by,
        status=status,
        destination_room_id=destination_room_id,
    )


def _mission_board(missions):
    return types.SimpleNamespace(
        _missions={i: m for i, m in enumerate(missions)})


def _patch_board(monkeypatch, missions):
    import engine.missions as mm
    monkeypatch.setattr(mm, "get_mission_board",
                        lambda: _mission_board(missions))


def _session_for_char(char_id):
    sess = _make_session()
    sess.character = {"id": char_id}
    return sess


def test_build_area_pois_maps_accepted_mission_objective(monkeypatch):
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(42)
    # _FakeEntry carries no region_slug → no regions → anomaly accessor never
    # consulted, so this isolates the objective sweep without touching anomalies.
    room_map = {201: _FakeEntry(10, 20), 202: _FakeEntry(30, 40)}
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.ACCEPTED, "201"),   # mine, in view
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [{"kind": "objective", "x": 10, "y": 20}], pois


def test_build_area_pois_unaccepted_mission_no_objective(monkeypatch):
    """An AVAILABLE (un-accepted) mission is not the player's objective — no
    star, even though its destination is in view."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(42)
    room_map = {201: _FakeEntry(10, 20)}
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.AVAILABLE, "201"),
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_other_chars_mission_skipped(monkeypatch):
    """A mission accepted by a DIFFERENT character is not mine → skipped."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(42)
    room_map = {201: _FakeEntry(10, 20)}
    _patch_board(monkeypatch, [
        _mission("99", MissionStatus.ACCEPTED, "201"),   # someone else's
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_objective_outside_view_skipped(monkeypatch):
    """My accepted mission's destination isn't in this area's covered rooms."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(42)
    room_map = {201: _FakeEntry(10, 20)}
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.ACCEPTED, "999"),   # not in room_map
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_mission_without_destination_room_skipped(monkeypatch):
    """A space mission (or any mission generated with no room list) carries
    destination_room_id=None and is skipped — degrades to no marker, no error."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(42)
    room_map = {201: _FakeEntry(10, 20)}
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.ACCEPTED, None),
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_objective_no_character_skipped(monkeypatch):
    """A bare session with no .character must not crash and emits no objective
    (the sweep is guarded by getattr(self, 'character', None))."""
    _quiet_bounties(monkeypatch)
    sess = _make_session()  # NB: no .character set
    room_map = {201: _FakeEntry(10, 20)}
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.ACCEPTED, "201"),
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_swallows_mission_errors(monkeypatch):
    """A mission-board error must not break the HUD, and must not discard the
    bounty POIs gathered before it."""
    import engine.bounty_board as bb
    import engine.missions as mm
    sess = _session_for_char(42)
    room_map = {201: _FakeEntry(10, 20)}
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=201)]))

    def boom():
        raise RuntimeError("mission board down")
    monkeypatch.setattr(mm, "get_mission_board", boom)
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [{"kind": "bounty", "x": 10, "y": 20}], pois


def test_build_area_pois_objective_coexists_with_bounty_and_anomaly(monkeypatch):
    """All three runtime kinds land together: bounty + anomaly + objective."""
    import engine.bounty_board as bb
    import engine.wilderness_anomalies as wa
    sess = _session_for_char(42)
    room_map = {
        201: _FakeEntryR(10, 20, region_slug="dune_sea"),   # bounty here
        202: _FakeEntryR(30, 40, region_slug="dune_sea"),   # anomaly here
        203: _FakeEntryR(50, 60, region_slug="dune_sea"),   # objective here
    }
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=201)]))
    monkeypatch.setattr(wa, "get_anomalies_for_region",
                        lambda region, **kw: [_anomaly(202, tier=2)])
    _patch_board(monkeypatch, [
        _mission("42", MissionStatus.ACCEPTED, "203"),
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=None, registry=_FakeRegistry(room_map), area_key="x"))
    assert {"kind": "bounty", "x": 10, "y": 20} in pois
    assert {"kind": "anomaly_t2", "x": 30, "y": 40} in pois
    assert {"kind": "objective", "x": 50, "y": 60} in pois
    assert len(pois) == 3, pois


# ── Static guards: source wiring + render path the objective glyph needs ─────

def test_server_wires_objective_sweep():
    src = SESSION_PY.read_text(encoding="utf-8")
    start = src.index("async def _build_area_pois")
    body = src[start:src.index("async def _hud_nearby_services", start)]
    assert "from engine.missions import get_mission_board" in body
    assert "MissionStatus.ACCEPTED" in body
    assert "destination_room_id" in body
    assert '"kind": "objective"' in body
    assert 'getattr(self, "character"' in body, (
        "objective sweep must be player-specific (read self.character)")


def test_composition_engine_renders_objective_kind():
    """The feed emits the 'objective' kind; L_Entities' poiMap must map it to a
    marker or the green star silently vanishes."""
    ce = COMPOSITION_JS.read_text(encoding="utf-8")
    assert "objective" in ce, "L_Entities poiMap missing 'objective'"


# ── Enabling data-side change: MissionBoard.refresh lazy-fetches the room list
# so tick-spawned missions (ensure_loaded(db) with no rooms) still get a
# destination_room_id and can therefore show an objective marker. The fetch is
# gated on actually filling the board, so idle ticks pay no DB cost. ──────────

class _FakeDBRooms:
    def __init__(self, rooms):
        self._rooms = rooms
        self.get_all_rooms_calls = 0
        self.created = 0

    async def get_all_rooms(self):
        self.get_all_rooms_calls += 1
        return self._rooms

    async def create_mission(self, **kw):
        self.created += 1


def test_refresh_lazily_fetches_rooms_when_filling():
    """No rooms passed + an empty board → refresh fetches rooms itself and the
    generated missions get real destination_room_ids."""
    board = MissionBoard()
    board._missions = {}
    board._last_refresh = 0.0
    db = _FakeDBRooms([{"id": 101, "name": "Cantina"},
                       {"id": 102, "name": "Docking Bay"}])
    asyncio.run(board.refresh(db))                 # NB: no rooms arg
    assert db.get_all_rooms_calls == 1, "refresh must lazily fetch the room list"
    assert len(board._missions) == BOARD_MAX
    assert any(getattr(m, "destination_room_id", None) is not None
               for m in board._missions.values()), (
        "with a room list supplied, ground missions must carry a destination "
        "room id (so their objective can be mapped)")


def test_refresh_no_room_fetch_when_board_full():
    """Board already at BOARD_MAX → needed<=0 → no fill → no room fetch (idle
    ticks must not hit the DB just to be told there's nothing to do)."""
    board = MissionBoard()
    board._missions = {i: types.SimpleNamespace(expires_at=None)
                       for i in range(BOARD_MAX)}
    board._last_refresh = 0.0
    db = _FakeDBRooms([{"id": 101, "name": "Cantina"}])
    asyncio.run(board.refresh(db))
    assert db.get_all_rooms_calls == 0, "a full board must not fetch rooms"


def test_refresh_explicit_rooms_not_overfetched():
    """When the caller DOES pass rooms (the +missions board path), refresh must
    use them and not also hit get_all_rooms."""
    board = MissionBoard()
    board._missions = {}
    board._last_refresh = 0.0
    db = _FakeDBRooms([{"id": 999, "name": "ShouldNotBeUsed"}])
    asyncio.run(board.refresh(db, rooms=[{"id": 101, "name": "Cantina"}]))
    assert db.get_all_rooms_calls == 0, (
        "explicit rooms must be used as-is; no redundant get_all_rooms")
    assert len(board._missions) == BOARD_MAX


# ════════════════════════════════════════════════════════════════════════════
# Vendor POI sweep — placed vendor droids (player shopfronts) on the map.
#
# Area-state, like bounty/anomaly (every shopfront in view, for everyone) —
# NOT personal like the objective sweep. Vendor droids are player-owned objects
# (type='vendor_droid') anchored to a room when deployed via `shop place`;
# unplaced droids sit in inventory (room_id=NULL) and the room_id IN-filter
# excludes them. The sweep uses one batched SQL keyed on the covered room ids —
# the same no-storm IN-query the contacts NPC sweep uses — so it adds a single
# indexed query per push, not one-per-room. Render path (MK_Vendor + L_Entities
# poiMap "vendor" + adapter pass-through) already exists; this exercises the new
# server-side enumeration only.
# ════════════════════════════════════════════════════════════════════════════

class _FakeInnerDB:
    """Stands in for db._db — the only method the vendor sweep touches is
    execute_fetchall. Captures the query + params so tests can assert the
    IN-filter shape (single batched query, type-gated)."""
    def __init__(self, rows):
        self._rows = rows
        self.calls = []

    async def execute_fetchall(self, sql, params=()):
        self.calls.append((sql, params))
        # Emulate the WHERE type='vendor_droid' AND room_id IN (...) filter:
        # return only stub rows whose room_id is in the supplied params.
        wanted = set(params)
        return [r for r in self._rows if r.get("room_id") in wanted]


class _FakeDBWithObjects:
    """A db whose ._db is a _FakeInnerDB. resolve_area_room_ids is provided by
    _FakeRegistry, so this object only needs the ._db handle."""
    def __init__(self, rows):
        self._db = _FakeInnerDB(rows)


def _vendor_rows(*room_ids):
    return [{"room_id": rid} for rid in room_ids]


def test_build_area_pois_maps_placed_vendor_droids(monkeypatch):
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(7)
    _patch_board(monkeypatch, [])  # no missions → isolate the vendor sweep
    room_map = {301: _FakeEntry(11, 22), 302: _FakeEntry(33, 44)}
    db = _FakeDBWithObjects(_vendor_rows(301, 302))
    pois = asyncio.run(sess._build_area_pois(
        db=db, registry=_FakeRegistry(room_map), area_key="x"))
    assert {"kind": "vendor", "x": 11, "y": 22} in pois
    assert {"kind": "vendor", "x": 33, "y": 44} in pois
    assert len(pois) == 2, pois


def test_build_area_pois_vendor_query_is_single_and_type_gated(monkeypatch):
    """One batched query (no per-room storm) and it filters on the vendor_droid
    type — the two properties that keep this cheap and correct."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(7)
    _patch_board(monkeypatch, [])
    room_map = {301: _FakeEntry(11, 22), 302: _FakeEntry(33, 44),
                303: _FakeEntry(55, 66)}
    db = _FakeDBWithObjects(_vendor_rows(301))
    asyncio.run(sess._build_area_pois(
        db=db, registry=_FakeRegistry(room_map), area_key="x"))
    vendor_calls = [c for c in db._db.calls if "vendor_droid" in c[0]]
    assert len(vendor_calls) == 1, "vendor sweep must be a single batched query"
    sql, params = vendor_calls[0]
    assert "type = 'vendor_droid'" in sql
    assert "room_id IN" in sql
    # Params are exactly the covered room ids — bounded by authored rooms.
    assert set(params) == {301, 302, 303}, params


def test_build_area_pois_vendor_outside_view_skipped(monkeypatch):
    """A vendor droid in a room not covered by this area never comes back from
    the IN-filtered query (and the post-filter guard would drop it anyway)."""
    _quiet_bounties(monkeypatch)
    sess = _session_for_char(7)
    _patch_board(monkeypatch, [])
    room_map = {301: _FakeEntry(11, 22)}
    db = _FakeDBWithObjects(_vendor_rows(999))   # droid in an uncovered room
    pois = asyncio.run(sess._build_area_pois(
        db=db, registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [], pois


def test_build_area_pois_swallows_vendor_errors(monkeypatch):
    """A vendor-query error must not break the HUD and must not discard the
    bounty POIs gathered before it."""
    import engine.bounty_board as bb
    sess = _session_for_char(7)
    _patch_board(monkeypatch, [])
    room_map = {301: _FakeEntry(11, 22)}
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=301)]))

    class _BoomDB:
        class _Inner:
            async def execute_fetchall(self, sql, params=()):
                raise RuntimeError("objects table locked")
        def __init__(self):
            self._db = self._Inner()

    pois = asyncio.run(sess._build_area_pois(
        db=_BoomDB(), registry=_FakeRegistry(room_map), area_key="x"))
    assert pois == [{"kind": "bounty", "x": 11, "y": 22}], pois


def test_build_area_pois_all_four_kinds_coexist(monkeypatch):
    """The full runtime POI feed: bounty + anomaly + vendor + objective land
    together in one sweep."""
    import engine.bounty_board as bb
    import engine.wilderness_anomalies as wa
    sess = _session_for_char(7)
    room_map = {
        301: _FakeEntryR(11, 22, region_slug="dune_sea"),   # bounty
        302: _FakeEntryR(33, 44, region_slug="dune_sea"),   # anomaly
        303: _FakeEntryR(55, 66, region_slug="dune_sea"),   # vendor
        304: _FakeEntryR(77, 88, region_slug="dune_sea"),   # objective
    }
    monkeypatch.setattr(bb, "get_bounty_board", lambda: types.SimpleNamespace(
        posted_contracts=lambda: [types.SimpleNamespace(target_room_id=301)]))
    monkeypatch.setattr(wa, "get_anomalies_for_region",
                        lambda region, **kw: [_anomaly(302, tier=2)])
    db = _FakeDBWithObjects(_vendor_rows(303))
    _patch_board(monkeypatch, [
        _mission("7", MissionStatus.ACCEPTED, "304"),
    ])
    pois = asyncio.run(sess._build_area_pois(
        db=db, registry=_FakeRegistry(room_map), area_key="x"))
    assert {"kind": "bounty", "x": 11, "y": 22} in pois
    assert {"kind": "anomaly_t2", "x": 33, "y": 44} in pois
    assert {"kind": "vendor", "x": 55, "y": 66} in pois
    assert {"kind": "objective", "x": 77, "y": 88} in pois
    assert len(pois) == 4, pois


# ── Static guards: source wiring + render path the vendor glyph needs ────────

def test_server_wires_vendor_sweep():
    src = SESSION_PY.read_text(encoding="utf-8")
    start = src.index("async def _build_area_pois")
    body = src[start:src.index("async def _hud_nearby_services", start)]
    assert "type = 'vendor_droid'" in body, "vendor sweep must type-gate"
    assert "room_id IN" in body, "vendor sweep must use a batched IN-query"
    assert '"kind": "vendor"' in body


def test_composition_engine_renders_vendor_kind():
    """The feed emits the 'vendor' kind; L_Entities' poiMap must map it to a
    marker or the amber awning silently vanishes."""
    ce = COMPOSITION_JS.read_text(encoding="utf-8")
    assert "vendor" in ce, "L_Entities poiMap missing 'vendor'"
