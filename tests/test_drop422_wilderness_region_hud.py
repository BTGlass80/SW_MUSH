# -*- coding: utf-8 -*-
"""
tests/test_drop422_wilderness_region_hud.py — Drop 4.22.

Verifies that ``Session._hud_area_map`` stamps the player's live wilderness
region slug onto the HUD so the SPA's ⊕ Tier-1b region map can paint the
correct painted wilderness substrate (Drop 4.21) for a live player.

The load-bearing contract:

  * ``rooms.wilderness_region_id`` is a top-level column — NULL for
    hand-built city/interior rooms, ``== region.slug`` for wilderness
    landmarks (set by ``engine/wilderness_writer.py``).
  * Wilderness regions are NOT covered by any ``AreaGeometry`` (their
    overview YAMLs carry ``landmarks:`` but no ``rooms:``), so the F.MAP.2
    path that emits ``player_position`` never fires for them. The region
    slug must therefore ride the ALWAYS-PRESENT hud path, emitted whether
    or not a registry is attached and whether or not the room is covered.
  * City/interior HUDs must be byte-identical to before (field absent).

Tests use a FakeDB (no real SQLite) and call ``_hud_area_map`` directly,
matching the harness style of ``tests/test_fmap2_session_hud.py``.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.session import Protocol, Session  # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────────


class FakeDB:
    """Minimal stub satisfying the surface ``_hud_area_map`` touches.

    ``rooms`` maps room_id → (slug, wilderness_region_id|None). ``slug`` is
    placed in ``properties`` (the F.MAP.2 registry path keys off it);
    ``wilderness_region_id`` is the top-level column the real schema carries.
    """

    def __init__(self, rooms: dict, raise_on_get_room: bool = False):
        self._rooms = rooms
        self._raise = raise_on_get_room

    async def get_room(self, room_id):
        if self._raise:
            raise RuntimeError("simulated DB failure")
        info = self._rooms.get(room_id)
        if info is None:
            return None
        slug, wregion = info
        row = {
            "id": room_id,
            "name": f"Test Room {room_id}",
            "zone_id": 1,
            "desc_short": "",
            "desc_long": "",
            "properties": json.dumps({"slug": slug}),
        }
        if wregion is not None:
            row["wilderness_region_id"] = wregion
        return row

    async def get_exits(self, room_id):
        return []  # legacy build_area_map terminates BFS immediately

    async def get_npcs_in_room(self, room_id):
        return []

    async def get_zone(self, zone_id):
        return None


class _StubEntry:
    """A registry room-lookup entry (only the fields _hud_area_map reads)."""

    def __init__(self, area_key, render_room_id, x, y):
        self.area_key = area_key
        self.render_room_id = render_room_id
        self.x = x
        self.y = y


class _StubRegistry:
    """Minimal AreaGeometry registry: covers the given slugs.

    Used only to exercise the (future-proofing) registry-gated branch — i.e.
    a hypothetical wilderness room that IS covered — without depending on the
    production registry, which today covers no wilderness area.
    """

    def __init__(self, slug_to_entry):
        self._m = slug_to_entry

    def lookup(self, slug):
        return self._m.get(slug)

    def get_payload(self, area_key):
        return {"area_key": area_key, "rooms": []}

    async def resolve_area_room_ids(self, area_key, db):
        return {}


class _SessionMgr:
    def __init__(self, registry=None):
        self._area_registry = registry


def _make_session():
    s = Session.__new__(Session)
    s.protocol = Protocol.WEBSOCKET
    s.character = {"id": 1, "name": "Tester", "room_id": 1}
    s.id = 9001
    s._last_sent_area_key = None
    return s


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Section 1 — Always-present path (the load-bearing behavior) ──────────────


class TestAlwaysPresentWildernessRegion(unittest.TestCase):
    """The region slug rides the always-present hud path: emitted with NO
    registry attached (the common case for wilderness rooms, which are never
    registry-covered) and only when the room actually carries the field."""

    def test_wilderness_room_no_registry_emits_region(self):
        # No registry → the F.MAP.2 augmentation returns early; the region
        # slug must still be present, proving it does NOT depend on coverage.
        sess = _make_session()
        db = FakeDB({1: ("forgotten_jedi_shrine", "coruscant_underworld")})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=_SessionMgr(None)))
        self.assertEqual(hud.get("wilderness_region_id"), "coruscant_underworld")
        # No registry → no F.MAP.2 augmentation.
        self.assertNotIn("area_geometry", hud)
        self.assertNotIn("player_position", hud)

    def test_dune_sea_room_no_registry_emits_region(self):
        sess = _make_session()
        db = FakeDB({5: ("dune_sea_anchor_stones", "tatooine_dune_sea")})
        hud = {}
        _run(sess._hud_area_map(hud, db, 5, session_mgr=None))
        self.assertEqual(hud.get("wilderness_region_id"), "tatooine_dune_sea")

    def test_city_room_omits_region(self):
        # City/interior room: NULL wilderness_region_id → key absent.
        sess = _make_session()
        db = FakeDB({1: ("docking_bay_94_pit", None)})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=None))
        self.assertNotIn("wilderness_region_id", hud)

    def test_empty_region_value_omitted(self):
        # Defensive: an empty-string region id is falsy → key absent.
        sess = _make_session()
        db = FakeDB({1: ("some_room", "")})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=None))
        self.assertNotIn("wilderness_region_id", hud)

    def test_always_present_companions_intact(self):
        # The region field rides the SAME best-effort block as environment /
        # legacy area_map; adding it must not displace them.
        sess = _make_session()
        db = FakeDB({1: ("forgotten_jedi_shrine", "coruscant_underworld")})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=None))
        self.assertIn("area_map", hud)        # legacy minimap always emitted
        self.assertIn("environment", hud)     # phase-1 environment scalars
        self.assertEqual(hud["wilderness_region_id"], "coruscant_underworld")


# ── Section 2 — Registry-gated consistency (future-proofing branch) ──────────


class TestRegistryGatedConsistency(unittest.TestCase):
    """If a wilderness room ever becomes registry-covered, player_position
    carries the same slug — so M3Adapter.regionKeyForArea stays correct
    whether it reads the top-level hud field or the player_position payload.
    City rooms (no region id) leave player_position byte-identical."""

    def test_covered_wilderness_room_stamps_both(self):
        sess = _make_session()
        registry = _StubRegistry({
            "forgotten_jedi_shrine": _StubEntry("coruscant_underworld", 3, 12.0, 38.0),
        })
        db = FakeDB({1: ("forgotten_jedi_shrine", "coruscant_underworld")})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=_SessionMgr(registry)))
        # Always-present field present...
        self.assertEqual(hud.get("wilderness_region_id"), "coruscant_underworld")
        # ...AND mirrored onto the (now-emitted) player_position.
        self.assertIn("player_position", hud)
        self.assertEqual(
            hud["player_position"].get("wilderness_region_id"),
            "coruscant_underworld",
        )

    def test_covered_city_room_player_position_unchanged(self):
        sess = _make_session()
        registry = _StubRegistry({
            "docking_bay_94_pit": _StubEntry("tatooine.mos_eisley", 1, 4.38, 0.0),
        })
        db = FakeDB({1: ("docking_bay_94_pit", None)})
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=_SessionMgr(registry)))
        self.assertNotIn("wilderness_region_id", hud)
        self.assertIn("player_position", hud)
        # The four canonical fields + bearing, no wilderness key.
        pp = hud["player_position"]
        self.assertEqual(pp["render_room_id"], 1)
        self.assertNotIn("wilderness_region_id", pp)


# ── Section 3 — Failure tolerance (HUD push must never crash) ────────────────


class TestFailureTolerance(unittest.TestCase):

    def test_get_room_failure_degrades_to_legacy(self):
        # If the room read fails, _hud_area_map returns after the legacy
        # area_map — no crash, and no wilderness field (it has no row).
        sess = _make_session()
        db = FakeDB({1: ("x", "coruscant_underworld")}, raise_on_get_room=True)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1, session_mgr=None))
        self.assertIn("area_map", hud)
        self.assertNotIn("wilderness_region_id", hud)


if __name__ == "__main__":
    unittest.main(verbosity=2)
