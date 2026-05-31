# -*- coding: utf-8 -*-
"""
tests/test_fmap2_session_hud.py — F.MAP.2 session HUD wiring tests.

Verifies that ``Session._hud_area_map`` correctly augments the HUD
payload when an ``AreaGeometryRegistry`` is attached to session_mgr:

  1. With NO registry: legacy `area_map` only — no `area_geometry`,
     no `player_position`. Existing behavior unchanged.
  2. With registry + room IS in registry, FIRST push:
     `area_geometry` (full payload) + `player_position` both present.
  3. With registry + room IS in registry, SUBSEQUENT push (same area):
     `area_geometry` ABSENT (cached client-side), `player_position`
     present (lightweight).
  4. With registry + room transitions to DIFFERENT covered area:
     `area_geometry` re-emits.
  5. With registry + room NOT covered by any area:
     legacy `area_map` only (no augmentation).
  6. With registry + room covered, then NOT covered, then covered
     again: full `area_geometry` re-emits on re-entry.
  7. Failure tolerance: a corrupt registry never crashes
     `_hud_area_map` — it falls back silently.

Tests use a FakeDB (no real SQLite) and bypass the protocol layer
by calling `_hud_area_map` directly.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.area_loader import AreaGeometryRegistry  # noqa: E402
from server.session import Protocol, Session         # noqa: E402


# ── Helpers ─────────────────────────────────────────────────────────────────


class FakeDB:
    """Minimal stub satisfying the surface ``_hud_area_map`` touches.

    Two methods are needed:
      - ``get_room(room_id)``: return a row with ``properties`` (str
        or dict) including ``slug``.
      - ``build_area_map(...)`` is exercised via the legacy path and
        only needs ``get_exits`` to return [] so the BFS terminates
        immediately — we don't care about the legacy payload's
        contents for these tests.
    """

    def __init__(self, room_id_to_slug: dict):
        # room_id → slug
        self._slugs = room_id_to_slug

    async def get_room(self, room_id):
        slug = self._slugs.get(room_id)
        if slug is None:
            return None
        return {
            "id": room_id,
            "name": f"Test Room {room_id}",
            "zone_id": 1,
            "desc_short": "",
            "desc_long": "",
            "properties": json.dumps({"slug": slug}),
        }

    async def get_exits(self, room_id):
        return []  # legacy build_area_map terminates BFS immediately

    async def get_npcs_in_room(self, room_id):
        return []

    async def get_zone(self, zone_id):
        return None


def _make_session():
    """Construct a minimal Session object suitable for the HUD method.

    We bypass the normal __init__ since send/close callbacks aren't
    needed for these tests."""
    s = Session.__new__(Session)
    s.protocol = Protocol.WEBSOCKET
    s.character = {"id": 1, "name": "Tester", "room_id": 1}
    s.id = 9001
    s._last_sent_area_key = None
    return s


def _make_session_mgr(registry: Optional[AreaGeometryRegistry] = None):
    """Mock session_mgr with the registry attached the way GameServer
    would attach it."""
    sm = MagicMock()
    sm._area_registry = registry
    return sm


def _run(coro):
    """Convenience: run an async coroutine to completion."""
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Section 1 — No registry: legacy path only ────────────────────────────────


class TestNoRegistryLegacyPath(unittest.TestCase):
    """When session_mgr has no _area_registry attribute (or it's None),
    `_hud_area_map` MUST behave exactly as before — legacy `area_map`
    only, no F.MAP.2 fields. Existing behavior preserved."""

    def setUp(self):
        self.session = _make_session()
        # Slug exists but no registry — legacy path only
        self.db = FakeDB({1: "docking_bay_94_pit"})
        # Session_mgr without _area_registry attribute set
        self.session_mgr_none = _make_session_mgr(registry=None)
        # Session_mgr with no _area_registry attr at all
        self.session_mgr_missing = MagicMock(spec=[])

    def test_no_registry_yields_legacy_only(self):
        hud = {}
        _run(self.session._hud_area_map(hud, self.db, 1,
                                        session_mgr=self.session_mgr_none))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)
        self.assertNotIn("player_position", hud)

    def test_session_mgr_without_attr_yields_legacy_only(self):
        hud = {}
        _run(self.session._hud_area_map(hud, self.db, 1,
                                        session_mgr=self.session_mgr_missing))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)
        self.assertNotIn("player_position", hud)

    def test_session_mgr_none_yields_legacy_only(self):
        hud = {}
        _run(self.session._hud_area_map(hud, self.db, 1, session_mgr=None))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)


# ── Section 2 — Registry attached + room covered ────────────────────────────


class TestRegistryCoveredRoom(unittest.TestCase):

    def setUp(self):
        self.session = _make_session()
        self.registry = AreaGeometryRegistry.load_era("clone_wars")
        self.db = FakeDB({
            1:  "docking_bay_94_pit",     # → tatooine.mos_eisley, render id 1
            7:  "mos_eisley_spaceport_row",
            13: "chalmuans_cantina_main_bar",
        })
        self.sm = _make_session_mgr(self.registry)

    def test_first_push_includes_area_geometry_and_position(self):
        # Initial state: _last_sent_area_key is None (per Session init).
        hud = {}
        _run(self.session._hud_area_map(hud, self.db, 1, session_mgr=self.sm))
        # Legacy path still runs
        self.assertIn("area_map", hud)
        # F.MAP.2: full payload + lightweight position
        self.assertIn("area_geometry", hud)
        self.assertIn("player_position", hud)
        self.assertEqual(hud["area_geometry"]["area_key"], "tatooine.mos_eisley")
        # player_position has the four required fields
        pp = hud["player_position"]
        self.assertEqual(pp["area_key"], "tatooine.mos_eisley")
        self.assertEqual(pp["render_room_id"], 1)
        self.assertAlmostEqual(pp["x"], 4.38)
        self.assertAlmostEqual(pp["y"], 0.0)
        # Side effect: _last_sent_area_key stamped
        self.assertEqual(self.session._last_sent_area_key, "tatooine.mos_eisley")

    def test_subsequent_push_same_area_omits_geometry(self):
        # Push 1: full geometry
        hud1 = {}
        _run(self.session._hud_area_map(hud1, self.db, 1, session_mgr=self.sm))
        self.assertIn("area_geometry", hud1)
        # Push 2: same area, different room
        hud2 = {}
        _run(self.session._hud_area_map(hud2, self.db, 7, session_mgr=self.sm))
        # Geometry omitted (cached client-side)
        self.assertNotIn("area_geometry", hud2)
        # Position present and updated
        self.assertIn("player_position", hud2)
        self.assertEqual(hud2["player_position"]["render_room_id"], 7)
        self.assertAlmostEqual(hud2["player_position"]["x"], 5.39)
        self.assertAlmostEqual(hud2["player_position"]["y"], 1.43)

    def test_position_emitted_on_every_push(self):
        # 3 pushes in sequence — every one should have player_position
        for room_id in (1, 7, 13):
            hud = {}
            _run(self.session._hud_area_map(hud, self.db, room_id,
                                            session_mgr=self.sm))
            self.assertIn("player_position", hud,
                f"player_position missing on push to room {room_id}")


# ── Section 3 — Area transitions ────────────────────────────────────────────


class TestAreaTransitions(unittest.TestCase):
    """Crossing area boundaries must re-emit the full geometry. The
    test uses a synthetic temp registry with TWO areas to verify
    cross-area re-emit; production currently has only one authored
    area, so we drive this with an in-memory registry."""

    def setUp(self):
        import tempfile
        import yaml as y
        self.tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = Path(self.tmpdir_obj.name)
        # Build two minimal areas with one slug-tagged room each
        for name, key in (("alpha", "test.alpha"), ("beta", "test.beta")):
            target = self.tmpdir / "clone_wars" / "maps"
            target.mkdir(parents=True, exist_ok=True)
            geom = {
                "schema_version": 1,
                "area_key": key,
                "display_name": name.upper(),
                "planet": "TEST", "era": "test",
                "default_terrain": "sand", "palette": "tatooine",
                "bounds": {"x_min": 0.0, "y_min": 0.0,
                           "x_max": 4.0, "y_max": 4.0},
                "districts": [{
                    "id": "d1", "name": "X",
                    "polygon": [[0, 0], [4, 0], [4, 4], [0, 4]],
                    "label_anchor": [3.5, 3.5], "rotation": 0,
                }],
                "rooms": [
                    {"id": 100 if name == "alpha" else 200,
                     "slug": f"{name}_room",
                     "name": "R", "zone": "d1",
                     "x": 1, "y": 1, "w": 0.5, "h": 0.5,
                     "style": "civic", "symbol": "§"},
                    {"id": 101 if name == "alpha" else 201,
                     "slug": f"{name}_other",
                     "name": "R2", "zone": "d1",
                     "x": 3, "y": 1, "w": 0.5, "h": 0.5,
                     "style": "civic", "symbol": "§"},
                ],
                "exits": [[100 if name == "alpha" else 200,
                           101 if name == "alpha" else 201]],
                "exit_paths": {
                    f"{100 if name == 'alpha' else 200}-"
                    f"{101 if name == 'alpha' else 201}": {
                        "kind": "street",
                        "path": [[1, 1], [2, 1], [3, 1]],
                        "width": 0.30,
                    },
                },
                "labels": [], "landmarks": [],
            }
            with open(target / f"{name}.yaml", "w", encoding="utf-8") as f:
                y.safe_dump(geom, f, sort_keys=False)
        self.registry = AreaGeometryRegistry.load_era(
            "clone_wars", worlds_root=self.tmpdir)
        self.db = FakeDB({
            100: "alpha_room",
            101: "alpha_other",
            200: "beta_room",
            201: "beta_other",
        })
        self.session = _make_session()
        self.sm = _make_session_mgr(self.registry)

    def tearDown(self):
        self.tmpdir_obj.cleanup()

    def test_cross_area_re_emits_geometry(self):
        # Push 1: alpha
        hud1 = {}
        _run(self.session._hud_area_map(hud1, self.db, 100, session_mgr=self.sm))
        self.assertEqual(hud1["area_geometry"]["area_key"], "test.alpha")
        # Push 2: still alpha, geometry omitted
        hud2 = {}
        _run(self.session._hud_area_map(hud2, self.db, 101, session_mgr=self.sm))
        self.assertNotIn("area_geometry", hud2)
        # Push 3: beta — transition
        hud3 = {}
        _run(self.session._hud_area_map(hud3, self.db, 200, session_mgr=self.sm))
        self.assertIn("area_geometry", hud3)
        self.assertEqual(hud3["area_geometry"]["area_key"], "test.beta")
        # Push 4: still beta, omitted
        hud4 = {}
        _run(self.session._hud_area_map(hud4, self.db, 201, session_mgr=self.sm))
        self.assertNotIn("area_geometry", hud4)


# ── Section 4 — Room not in any area ────────────────────────────────────────


class TestUncoveredRoom(unittest.TestCase):
    """A room with a slug NOT in the registry → legacy path only.
    Critical for the partial rollout: rooms outside Mos Eisley should
    keep working with the legacy minimap."""

    def setUp(self):
        self.session = _make_session()
        self.registry = AreaGeometryRegistry.load_era("clone_wars")
        # Room 999 has a slug, but it's not in any AreaGeometry
        self.db = FakeDB({999: "kamino_cloning_chamber"})
        self.sm = _make_session_mgr(self.registry)

    def test_uncovered_room_yields_legacy_only(self):
        hud = {}
        _run(self.session._hud_area_map(hud, self.db, 999, session_mgr=self.sm))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)
        self.assertNotIn("player_position", hud)

    def test_room_with_no_slug_yields_legacy_only(self):
        # Room exists but has no slug in properties (e.g. legacy
        # rooms that predate F.8.c.1 slug-stamping).
        class NoSlugDB:
            async def get_room(self, room_id):
                return {"id": room_id, "name": "Legacy Room",
                        "properties": "{}"}  # empty props
            async def get_exits(self, room_id): return []
            async def get_npcs_in_room(self, room_id): return []
            async def get_zone(self, zone_id): return None

        hud = {}
        _run(self.session._hud_area_map(hud, NoSlugDB(), 1, session_mgr=self.sm))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)


# ── Section 5 — Re-entry into a covered area resets ──────────────────────────


class TestReEntryAfterUncovered(unittest.TestCase):
    """Player walks: covered area → uncovered → back to covered.
    The full geometry should re-emit on re-entry — the covered/
    uncovered transition resets _last_sent_area_key so the client
    gets a fresh baseline."""

    def setUp(self):
        self.session = _make_session()
        self.registry = AreaGeometryRegistry.load_era("clone_wars")
        self.db = FakeDB({
            1:   "docking_bay_94_pit",        # covered
            999: "kamino_cloning_chamber",     # NOT covered
        })
        self.sm = _make_session_mgr(self.registry)

    def test_geometry_re_emits_after_uncovered_excursion(self):
        # Push 1: covered → full geometry
        hud1 = {}
        _run(self.session._hud_area_map(hud1, self.db, 1, session_mgr=self.sm))
        self.assertIn("area_geometry", hud1)
        # Push 2: uncovered → no geometry
        hud2 = {}
        _run(self.session._hud_area_map(hud2, self.db, 999, session_mgr=self.sm))
        self.assertNotIn("area_geometry", hud2)
        # Per the implementation: _last_sent_area_key cleared to None
        self.assertIsNone(self.session._last_sent_area_key)
        # Push 3: back to covered → full geometry RE-EMITS
        hud3 = {}
        _run(self.session._hud_area_map(hud3, self.db, 1, session_mgr=self.sm))
        self.assertIn("area_geometry", hud3,
            "geometry should re-emit when re-entering a covered area "
            "after an uncovered excursion")


# ── Section 6 — Failure tolerance ───────────────────────────────────────────


class TestFailureTolerance(unittest.TestCase):
    """`_hud_area_map`'s F.MAP.2 augmentation MUST never crash the
    HUD push. Even if the registry is broken, the legacy path must
    still produce `area_map`."""

    def setUp(self):
        self.session = _make_session()

    def test_broken_registry_falls_back_to_legacy(self):
        broken_registry = MagicMock()
        broken_registry.lookup.side_effect = RuntimeError("boom")
        sm = _make_session_mgr(broken_registry)
        db = FakeDB({1: "docking_bay_94_pit"})
        hud = {}
        _run(self.session._hud_area_map(hud, db, 1, session_mgr=sm))
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)

    def test_broken_get_room_falls_back_silently(self):
        # Registry is fine, but get_room raises mid-flight.
        registry = AreaGeometryRegistry.load_era("clone_wars")
        sm = _make_session_mgr(registry)

        class BrokenDB:
            async def get_room(self, _):
                raise RuntimeError("DB exploded")
            async def get_exits(self, _): return []
            async def get_npcs_in_room(self, _): return []
            async def get_zone(self, _): return None

        hud = {}
        _run(self.session._hud_area_map(hud, BrokenDB(), 1, session_mgr=sm))
        # legacy area_map still ran since it's called BEFORE the
        # F.MAP.2 augmentation block
        self.assertIn("area_map", hud)
        self.assertNotIn("area_geometry", hud)


if __name__ == "__main__":
    unittest.main()
