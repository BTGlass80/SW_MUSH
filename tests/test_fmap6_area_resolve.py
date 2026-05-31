# -*- coding: utf-8 -*-
"""
tests/test_fmap6_area_resolve.py — F.MAP.6 registry test surface.

Verifies the new ``AreaGeometryRegistry.resolve_area_room_ids(area_key, db)``
method behaves correctly:

  1. First call resolves every slug to its production room_id via
     ``db.get_room_by_slug``.
  2. Result is cached — second call doesn't re-query the DB.
  3. Slugs that fail to resolve (no production room exists) are
     skipped, NOT included in the result.
  4. Unknown area_key returns an empty dict.
  5. DB without ``get_room_by_slug`` (legacy stub) logs and returns
     empty dict, doesn't crash.
  6. Per-call exceptions during slug resolution are tolerated — the
     other slugs continue to resolve.
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.area_loader import (  # noqa: E402
    AreaGeometryRegistry,
)


# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeDB:
    """Minimal db stub with a synchronous-then-async get_room_by_slug."""

    def __init__(self, slug_to_id: dict, *, raise_on=None):
        self._map = dict(slug_to_id)
        self._raise_on = set(raise_on or ())
        self.calls = 0

    async def get_room_by_slug(self, slug: str):
        self.calls += 1
        if slug in self._raise_on:
            raise RuntimeError(f"simulated failure for {slug!r}")
        rid = self._map.get(slug)
        if rid is None:
            return None
        return {"id": rid, "name": "Synthetic", "properties": "{}"}


class LegacyDB:
    """A DB stub without get_room_by_slug — older builds, defensive."""
    pass


# ── Tests ──────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


class TestResolveAreaRoomIdsHappyPath(unittest.TestCase):
    """Mos Eisley is fully slug-tied (53 rooms) — confirm the method
    walks all 53 slugs and produces a 53-entry dict keyed by db
    room_id."""

    def setUp(self):
        self.reg = AreaGeometryRegistry.load_era("clone_wars")
        # Fabricate a slug→fake-id map for every slug in the area
        geom = self.reg._areas["tatooine.mos_eisley"]
        self.slug_to_id = {r.slug: r.id + 1000 for r in geom.rooms if r.slug}
        self.db = FakeDB(self.slug_to_id)

    def test_first_call_resolves_every_slug(self):
        out = _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley",
                                                  self.db))
        self.assertEqual(len(out), 53)
        # Each value is a _RoomLookupEntry with the right area + render id
        for db_id, entry in out.items():
            self.assertEqual(entry.area_key, "tatooine.mos_eisley")
            # render_room_id should equal db_id - 1000 (the synth offset)
            self.assertEqual(entry.render_room_id, db_id - 1000)

    def test_first_call_makes_53_db_calls(self):
        _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley", self.db))
        self.assertEqual(self.db.calls, 53)

    def test_second_call_is_cached(self):
        _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley", self.db))
        self.db.calls = 0  # reset
        out2 = _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley",
                                                   self.db))
        self.assertEqual(self.db.calls, 0,
                         "Second call must not re-hit the DB")
        self.assertEqual(len(out2), 53)


class TestResolveSkipsUnresolvableSlugs(unittest.TestCase):
    """Slugs that have no production room (db returns None) are skipped
    silently. Important: the Senate fixture currently has no slugs at
    all, so this exercises the partial case via Mos Eisley with some
    slugs missing from the fake DB."""

    def setUp(self):
        self.reg = AreaGeometryRegistry.load_era("clone_wars")
        # Provide rooms for only HALF the slugs
        geom = self.reg._areas["tatooine.mos_eisley"]
        slugs = [r.slug for r in geom.rooms if r.slug]
        partial = {s: i + 2000 for i, s in enumerate(slugs[:30])}
        self.db = FakeDB(partial)

    def test_unresolved_slugs_are_omitted(self):
        out = _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley",
                                                  self.db))
        self.assertEqual(len(out), 30,
                         "Should skip slugs with no production room")


class TestUnknownAreaKey(unittest.TestCase):
    def test_returns_empty_dict_for_unknown_area(self):
        reg = AreaGeometryRegistry.load_era("clone_wars")
        db = FakeDB({})
        out = _run(reg.resolve_area_room_ids("not.a.real.area", db))
        self.assertEqual(out, {})

    def test_unknown_area_doesnt_call_db(self):
        reg = AreaGeometryRegistry.load_era("clone_wars")
        db = FakeDB({})
        _run(reg.resolve_area_room_ids("not.a.real.area", db))
        self.assertEqual(db.calls, 0)


class TestLegacyDBWithoutSlugMethod(unittest.TestCase):
    """A DB without get_room_by_slug (older codebase) must log and
    return an empty dict — never crash. F.MAP.6 must be safe to deploy
    on a database that hasn't yet been backfilled with slugs."""

    def test_returns_empty_dict_caches_result(self):
        reg = AreaGeometryRegistry.load_era("clone_wars")
        db = LegacyDB()
        out = _run(reg.resolve_area_room_ids("tatooine.mos_eisley", db))
        self.assertEqual(out, {})
        # Cached — second call still returns empty without re-checking
        out2 = _run(reg.resolve_area_room_ids("tatooine.mos_eisley", db))
        self.assertEqual(out2, {})


class TestPerSlugFailureTolerated(unittest.TestCase):
    """A db.get_room_by_slug exception on ONE slug must not poison the
    rest of the resolution. Pre-launch we'd rather ship a partial
    contacts list than no contacts list."""

    def setUp(self):
        self.reg = AreaGeometryRegistry.load_era("clone_wars")
        geom = self.reg._areas["tatooine.mos_eisley"]
        slugs = [r.slug for r in geom.rooms if r.slug]
        self.slug_to_id = {s: i + 3000 for i, s in enumerate(slugs)}
        # Pick three slugs that will raise on lookup
        self.bad = set(slugs[5:8])
        self.db = FakeDB(self.slug_to_id, raise_on=self.bad)

    def test_other_slugs_resolve_when_some_raise(self):
        out = _run(self.reg.resolve_area_room_ids("tatooine.mos_eisley",
                                                  self.db))
        # 53 total, 3 raised → 50 should be in the map
        self.assertEqual(len(out), 50)


if __name__ == "__main__":
    unittest.main()
