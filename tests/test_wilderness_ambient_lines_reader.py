"""
TD.WILDERNESS_AMBIENT_LINES_DEAD_WRITE — consumer added.

wilderness_writer writes `wilderness_ambient_lines` to room properties for
force-resonant + underworld landmarks. Before this fix, no runtime path ever
read that property. Now AmbientEventManager._get_room_ambient_lines reads it
and _pick_line merges room lines into the static pool.
"""
import json
import pytest

from engine.ambient_events import AmbientEventManager, AmbientLine


# ── helpers ──────────────────────────────────────────────────────────────────

class _FakeDB:
    def __init__(self, rooms):
        self._rooms = rooms  # {room_id: room_dict}

    async def get_room(self, room_id):
        return self._rooms.get(room_id)


def _mgr():
    m = AmbientEventManager()
    m._loaded = True  # skip YAML load
    return m


def _room_with_lines(room_id, lines):
    props = json.dumps({"wilderness_ambient_lines": lines})
    return {"id": room_id, "properties": props, "zone_id": None}


def _room_no_lines(room_id):
    return {"id": room_id, "properties": "{}", "zone_id": None}


# ── _get_room_ambient_lines ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_returns_ambient_lines_from_room_props():
    mgr = _mgr()
    db = _FakeDB({1: _room_with_lines(1, ["The air moves strangely.", "A hum settles behind your ears."])})
    result = await mgr._get_room_ambient_lines(1, db)
    assert len(result) == 2
    assert all(isinstance(x, AmbientLine) for x in result)
    assert result[0].text == "The air moves strangely."
    assert result[1].text == "A hum settles behind your ears."


@pytest.mark.asyncio
async def test_returns_empty_for_room_with_no_lines():
    mgr = _mgr()
    db = _FakeDB({1: _room_no_lines(1)})
    result = await mgr._get_room_ambient_lines(1, db)
    assert result == []


@pytest.mark.asyncio
async def test_returns_empty_for_missing_room():
    mgr = _mgr()
    db = _FakeDB({})
    result = await mgr._get_room_ambient_lines(99, db)
    assert result == []


@pytest.mark.asyncio
async def test_caches_result_skips_second_db_call():
    calls = []

    class _TrackingDB:
        async def get_room(self, room_id):
            calls.append(room_id)
            return _room_with_lines(room_id, ["A shadow falls."])

    mgr = _mgr()
    db = _TrackingDB()
    await mgr._get_room_ambient_lines(5, db)
    await mgr._get_room_ambient_lines(5, db)
    assert len(calls) == 1  # cached after first call


@pytest.mark.asyncio
async def test_empty_strings_skipped():
    mgr = _mgr()
    db = _FakeDB({1: _room_with_lines(1, ["", "  ", "Valid line.", ""])})
    result = await mgr._get_room_ambient_lines(1, db)
    assert len(result) == 1
    assert result[0].text == "Valid line."


@pytest.mark.asyncio
async def test_empty_list_cached():
    mgr = _mgr()
    db = _FakeDB({1: _room_no_lines(1)})
    r1 = await mgr._get_room_ambient_lines(1, db)
    r2 = await mgr._get_room_ambient_lines(1, db)
    assert r1 is r2  # same list object (cache hit)


# ── _pick_line with room_lines ────────────────────────────────────────────────

def test_pick_line_includes_room_lines_in_static_pool():
    mgr = _mgr()
    mgr._static_pool["default"] = [AmbientLine(text="zone line")]
    room_lines = [AmbientLine(text="landmark line A"), AmbientLine(text="landmark line B")]
    seen = set()
    for _ in range(200):
        seen.add(mgr._pick_line("default", room_lines=room_lines))
    assert "zone line" in seen
    assert "landmark line A" in seen or "landmark line B" in seen


def test_pick_line_room_lines_only_when_no_static():
    mgr = _mgr()
    # no static pool for this zone; room provides the only content
    room_lines = [AmbientLine(text="only room line")]
    result = mgr._pick_line("wilderness_zone", room_lines=room_lines)
    assert result == "only room line"


def test_pick_line_no_room_lines_unchanged():
    mgr = _mgr()
    mgr._static_pool["streets"] = [AmbientLine(text="street scene")]
    result = mgr._pick_line("streets")
    assert result == "street scene"


def test_pick_line_room_lines_none_unchanged():
    mgr = _mgr()
    mgr._static_pool["default"] = [AmbientLine(text="default line")]
    result = mgr._pick_line("missing_zone", room_lines=None)
    assert result == "default line"


def test_pick_line_empty_room_lines_falls_through_to_zone():
    mgr = _mgr()
    mgr._static_pool["default"] = [AmbientLine(text="fallback")]
    result = mgr._pick_line("nozone", room_lines=[])
    assert result == "fallback"


def test_pick_line_no_pool_and_no_room_lines_returns_none():
    mgr = _mgr()
    result = mgr._pick_line("empty_zone", room_lines=None)
    assert result is None
