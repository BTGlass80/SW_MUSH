# -*- coding: utf-8 -*-
"""
tests/test_syn2_wilderness_aware_security.py — SYN.2 (May 24 2026).

Pins the new wilderness-aware security branch in
``engine/security.py::get_effective_security`` per
``contestable_wilderness_design_v2.md`` §2.3 + §3.2.

Test sections
─────────────
  1. TestApplyWildernessOwnership      — pure citadel-upgrade rule
  2. TestGetWildernessRegionState      — registry + ownership DB reads
  3. TestStep4WildernessBranch         — full integration into
                                          get_effective_security
  4. TestClaimUpgradeRetired           — _apply_claim_upgrade gone;
                                          _finalize no longer calls it
  5. TestCityMapUnaffected             — city-map resolution path
                                          identical to pre-SYN.2
  6. TestDirectorOverlayRunsFirst      — Director steps 1-3 still
                                          short-circuit wilderness step 4
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    """Run a coroutine in a fresh event loop (BugFix5 Py3.14 pattern)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in
# ──────────────────────────────────────────────────────────────────────
#
# Mirrors the SYN.1.a test pattern. The new branch reads from:
#   - rooms.wilderness_region_id  (set by wilderness writer)
#   - wilderness_regions.default_security  (registry)
#   - region_ownership.org_code  (SYN.1.a table)
# Plus the standard get_room / get_zone / get_room_property surfaces
# the existing branches use.

class _SyncAsyncSqlite:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:

    def __init__(self):
        self._db = _SyncAsyncSqlite()
        cur = self._db._conn
        cur.executescript("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                name TEXT,
                zone_id INTEGER,
                wilderness_region_id TEXT,
                properties TEXT DEFAULT '{}'
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{}'
            );
            CREATE TABLE wilderness_regions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                planet TEXT NOT NULL,
                zone_slug TEXT NOT NULL,
                width INTEGER NOT NULL,
                height INTEGER NOT NULL,
                tile_scale_km INTEGER NOT NULL DEFAULT 1,
                default_terrain TEXT NOT NULL,
                default_security TEXT NOT NULL,
                sentinel_room_id INTEGER,
                config_json TEXT DEFAULT '{}',
                created_at REAL DEFAULT 0
            );
            CREATE TABLE region_ownership (
                region_slug TEXT NOT NULL PRIMARY KEY,
                org_code TEXT NOT NULL,
                zone_id INTEGER,
                claimed_by INTEGER NOT NULL,
                claimed_at REAL NOT NULL,
                maintenance INTEGER NOT NULL DEFAULT 3000
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                faction_id TEXT
            );
        """)
        self._db._conn.commit()

    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_room_property(self, room_id, key):
        """Return room.properties[key] or zone.properties[key] fallback.

        Mirrors the actual db.database.Database.get_room_property
        semantics (room props override zone props).
        """
        rows = await self._db.execute_fetchall(
            "SELECT properties, zone_id FROM rooms WHERE id = ?", (room_id,)
        )
        if not rows:
            return None
        row = rows[0]
        props_raw = row.get("properties") or "{}"
        try:
            props = json.loads(props_raw) if isinstance(props_raw, str) else props_raw
        except Exception:
            props = {}
        if key in props:
            return props[key]
        zone_id = row.get("zone_id")
        if zone_id is None:
            return None
        zrows = await self._db.execute_fetchall(
            "SELECT properties FROM zones WHERE id = ?", (zone_id,)
        )
        if not zrows:
            return None
        zprops_raw = zrows[0].get("properties") or "{}"
        try:
            zprops = json.loads(zprops_raw) if isinstance(zprops_raw, str) else zprops_raw
        except Exception:
            zprops = {}
        return zprops.get(key)

    # ── Seed helpers ───────────────────────────────────────────────
    def seed_zone(self, *, zone_id, name, security="lawless", environment=""):
        props = {"security": security}
        if environment:
            props["environment"] = environment
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, json.dumps(props)),
        )
        self._db._conn.commit()

    def seed_room(self, *, room_id, name, zone_id=None,
                  wilderness_region_id=None, properties=None):
        props = properties if properties is not None else {}
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id, "
            "properties) VALUES (?, ?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id, json.dumps(props)),
        )
        self._db._conn.commit()

    def seed_wilderness_region(self, *, slug, default_security="lawless"):
        self._db._conn.execute(
            "INSERT INTO wilderness_regions ("
            " slug, name, planet, zone_slug, width, height, tile_scale_km,"
            " default_terrain, default_security"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, slug, "tatooine", "jundland_wastes",
             40, 40, 2, "dune", default_security),
        )
        self._db._conn.commit()

    def seed_region_ownership(self, *, slug, org_code, claimed_by=1):
        self._db._conn.execute(
            "INSERT INTO region_ownership "
            "(region_slug, org_code, zone_id, claimed_by, claimed_at, maintenance) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (slug, org_code, None, claimed_by, 0.0, 3000),
        )
        self._db._conn.commit()


def _char(*, faction_id=None, char_id=1):
    return {"id": char_id, "faction_id": faction_id} if faction_id else {"id": char_id}


# ──────────────────────────────────────────────────────────────────────
# 1. _apply_wilderness_ownership — pure rule unit tests
# ──────────────────────────────────────────────────────────────────────

class TestApplyWildernessOwnership(unittest.TestCase):
    """The citadel-upgrade rule is a pure function. Test it in
    isolation without DB setup."""

    def _state(self, owner=None, default=None):
        from engine.security import SecurityLevel
        return {
            "slug": "tatooine_dune_sea",
            "default_security": default or SecurityLevel.LAWLESS,
            "owner_org": owner,
        }

    def test_unowned_lawless_stays_lawless(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, _char(faction_id="hutt_cartel"),
            self._state(owner=None),
        )
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_owned_by_own_org_lawless_upgrades_to_contested(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, _char(faction_id="hutt_cartel"),
            self._state(owner="hutt_cartel"),
        )
        self.assertEqual(result, SecurityLevel.CONTESTED)

    def test_owned_by_rival_org_lawless_stays_lawless(self):
        """Hostile territory: outsiders take the frontier risk."""
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, _char(faction_id="rebel"),
            self._state(owner="hutt_cartel"),
        )
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_owned_contested_stays_contested_no_double_promotion(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.CONTESTED, _char(faction_id="hutt_cartel"),
            self._state(owner="hutt_cartel", default=SecurityLevel.CONTESTED),
        )
        # No further promotion — CONTESTED stays CONTESTED, never SECURED
        self.assertEqual(result, SecurityLevel.CONTESTED)

    def test_no_character_context_returns_base(self):
        """NPC observers / system queries get base regardless of owner."""
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, None,
            self._state(owner="hutt_cartel"),
        )
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_independent_pc_gets_no_upgrade(self):
        """Independent / no-faction PCs don't get citadel upgrades
        even from an owned region."""
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, _char(faction_id="independent"),
            self._state(owner="hutt_cartel"),
        )
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_no_faction_id_at_all_gets_no_upgrade(self):
        from engine.security import _apply_wilderness_ownership, SecurityLevel
        result = _apply_wilderness_ownership(
            SecurityLevel.LAWLESS, _char(), self._state(owner="hutt_cartel"),
        )
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ──────────────────────────────────────────────────────────────────────
# 2. _get_wilderness_region_state — DB reads
# ──────────────────────────────────────────────────────────────────────

class TestGetWildernessRegionState(unittest.TestCase):

    def test_unregistered_region_returns_none(self):
        from engine.security import _get_wilderness_region_state
        db = _MiniDB()
        # Room references a region that doesn't exist in registry
        db.seed_room(room_id=1, name="ghost",
                     wilderness_region_id="phantom_region")
        room = _run(db.get_room(1))
        result = _run(_get_wilderness_region_state(room, db))
        self.assertIsNone(result)

    def test_no_wilderness_region_id_returns_none(self):
        from engine.security import _get_wilderness_region_state
        db = _MiniDB()
        db.seed_room(room_id=1, name="city_room", zone_id=10)
        room = _run(db.get_room(1))
        result = _run(_get_wilderness_region_state(room, db))
        self.assertIsNone(result)

    def test_registered_unowned_region_returns_state(self):
        from engine.security import _get_wilderness_region_state, SecurityLevel
        db = _MiniDB()
        db.seed_wilderness_region(slug="tatooine_dune_sea", default_security="lawless")
        db.seed_room(room_id=1, name="dune", wilderness_region_id="tatooine_dune_sea")
        room = _run(db.get_room(1))
        state = _run(_get_wilderness_region_state(room, db))
        self.assertIsNotNone(state)
        self.assertEqual(state["slug"], "tatooine_dune_sea")
        self.assertEqual(state["default_security"], SecurityLevel.LAWLESS)
        self.assertIsNone(state["owner_org"])

    def test_owned_region_returns_owner(self):
        from engine.security import _get_wilderness_region_state
        db = _MiniDB()
        db.seed_wilderness_region(slug="tatooine_dune_sea", default_security="lawless")
        db.seed_region_ownership(slug="tatooine_dune_sea", org_code="hutt_cartel")
        db.seed_room(room_id=1, name="dune", wilderness_region_id="tatooine_dune_sea")
        room = _run(db.get_room(1))
        state = _run(_get_wilderness_region_state(room, db))
        self.assertEqual(state["owner_org"], "hutt_cartel")

    def test_contested_default_security_carried_through(self):
        from engine.security import _get_wilderness_region_state, SecurityLevel
        db = _MiniDB()
        db.seed_wilderness_region(slug="contested_zone", default_security="contested")
        db.seed_room(room_id=1, name="alley", wilderness_region_id="contested_zone")
        room = _run(db.get_room(1))
        state = _run(_get_wilderness_region_state(room, db))
        self.assertEqual(state["default_security"], SecurityLevel.CONTESTED)

    def test_unknown_default_security_falls_back_to_lawless(self):
        from engine.security import _get_wilderness_region_state, SecurityLevel
        db = _MiniDB()
        db.seed_wilderness_region(slug="weird", default_security="xenosec")
        db.seed_room(room_id=1, name="weird_lm", wilderness_region_id="weird")
        room = _run(db.get_room(1))
        state = _run(_get_wilderness_region_state(room, db))
        self.assertEqual(state["default_security"], SecurityLevel.LAWLESS)


# ──────────────────────────────────────────────────────────────────────
# 3. get_effective_security — step 4 integration
# ──────────────────────────────────────────────────────────────────────

def _make_wilderness_db(*, owner=None, default_security="lawless"):
    """Seed a stocked DB for integration tests.

    Region 'tatooine_dune_sea' in zone 50 (jundland_wastes, lawless).
    Room 100 is a landmark in the region.
    """
    db = _MiniDB()
    db.seed_zone(zone_id=50, name="Jundland Wastes",
                 security="lawless")
    db.seed_wilderness_region(
        slug="tatooine_dune_sea", default_security=default_security,
    )
    db.seed_room(
        room_id=100, name="anchor_stones", zone_id=50,
        wilderness_region_id="tatooine_dune_sea",
        properties={"security": default_security},
    )
    if owner:
        db.seed_region_ownership(slug="tatooine_dune_sea", org_code=owner)
    return db


class TestStep4WildernessBranch(unittest.TestCase):
    """Integration: wilderness room → step 4 wins."""

    def setUp(self):
        from engine.security import clear_all_overrides
        clear_all_overrides()

    def test_unowned_lawless_wilderness_lawless_for_pc(self):
        from engine.security import get_effective_security, SecurityLevel
        db = _make_wilderness_db(owner=None, default_security="lawless")
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="hutt_cartel"),
        ))
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_owned_lawless_wilderness_owner_pc_gets_contested(self):
        from engine.security import get_effective_security, SecurityLevel
        db = _make_wilderness_db(owner="hutt_cartel", default_security="lawless")
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="hutt_cartel"),
        ))
        self.assertEqual(result, SecurityLevel.CONTESTED)

    def test_owned_lawless_wilderness_rival_pc_stays_lawless(self):
        from engine.security import get_effective_security, SecurityLevel
        db = _make_wilderness_db(owner="hutt_cartel", default_security="lawless")
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="rebel"),
        ))
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_no_character_in_wilderness_returns_base(self):
        from engine.security import get_effective_security, SecurityLevel
        db = _make_wilderness_db(owner="hutt_cartel", default_security="lawless")
        result = _run(get_effective_security(100, db))  # no character
        self.assertEqual(result, SecurityLevel.LAWLESS)

    def test_contested_wilderness_owner_stays_contested(self):
        from engine.security import get_effective_security, SecurityLevel
        db = _make_wilderness_db(owner="hutt_cartel", default_security="contested")
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="hutt_cartel"),
        ))
        self.assertEqual(result, SecurityLevel.CONTESTED)

    def test_unregistered_region_falls_through_to_property(self):
        """Room has wilderness_region_id pointing at a region the
        registry doesn't know about. The branch returns None →
        falls through to step 5 (room property → 'lawless'). The
        room property is 'lawless' from our fixture."""
        from engine.security import get_effective_security, SecurityLevel
        db = _MiniDB()
        db.seed_zone(zone_id=50, name="Jundland", security="lawless")
        db.seed_room(
            room_id=100, name="phantom", zone_id=50,
            wilderness_region_id="not_in_registry",
            properties={"security": "lawless"},
        )
        # No region registered. No ownership row.
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="hutt_cartel"),
        ))
        self.assertEqual(result, SecurityLevel.LAWLESS)


# ──────────────────────────────────────────────────────────────────────
# 4. _apply_claim_upgrade retired
# ──────────────────────────────────────────────────────────────────────

class TestClaimUpgradeRetired(unittest.TestCase):
    """SYN.1.b stubbed _apply_claim_upgrade; SYN.2 deletes it entirely
    and removes the call from _finalize. Confirm both happened."""

    def test_apply_claim_upgrade_symbol_gone(self):
        import engine.security as sec
        self.assertFalse(
            hasattr(sec, "_apply_claim_upgrade"),
            "_apply_claim_upgrade should be deleted in SYN.2",
        )

    def test_finalize_does_not_reference_claim_upgrade(self):
        """Sanity-check the source: _finalize should no longer call
        the retired function. The docstring may mention it as part of
        the retirement explanation; we check for a real call pattern
        (``await _apply_claim_upgrade(``)."""
        import inspect
        from engine.security import _finalize
        src = inspect.getsource(_finalize)
        self.assertNotIn("await _apply_claim_upgrade(", src,
                         "_finalize should not invoke _apply_claim_upgrade")


# ──────────────────────────────────────────────────────────────────────
# 5. City-map resolution unaffected
# ──────────────────────────────────────────────────────────────────────

class TestCityMapUnaffected(unittest.TestCase):
    """The wilderness branch must NOT affect city-map rooms (those
    without wilderness_region_id). Verifies isolation per design
    §2.3 ('City-map zone security is completely unaffected')."""

    def setUp(self):
        from engine.security import clear_all_overrides
        clear_all_overrides()

    def test_city_map_room_resolves_via_property(self):
        """A city-map room with security=secured should resolve to
        SECURED via step 5, untouched by step 4."""
        from engine.security import get_effective_security, SecurityLevel
        db = _MiniDB()
        db.seed_zone(zone_id=10, name="Mos Eisley Core",
                     security="secured")
        db.seed_room(
            room_id=200, name="Mos Eisley Bank", zone_id=10,
            wilderness_region_id=None,
            properties={"security": "secured"},
        )
        result = _run(get_effective_security(
            200, db, character=_char(faction_id="hutt_cartel"),
        ))
        self.assertEqual(result, SecurityLevel.SECURED)

    def test_city_map_owned_org_has_no_effect(self):
        """Even if the character's org happens to own a wilderness
        region, that ownership shouldn't bleed into a city-map
        room's resolution."""
        from engine.security import get_effective_security, SecurityLevel
        db = _MiniDB()
        db.seed_zone(zone_id=10, name="Mos Eisley", security="contested")
        db.seed_room(
            room_id=200, name="cantina", zone_id=10,
            wilderness_region_id=None,
            properties={"security": "contested"},
        )
        # Hutts also own a wilderness region somewhere else
        db.seed_wilderness_region(slug="tatooine_dune_sea",
                                   default_security="lawless")
        db.seed_region_ownership(slug="tatooine_dune_sea",
                                  org_code="hutt_cartel")
        result = _run(get_effective_security(
            200, db, character=_char(faction_id="hutt_cartel"),
        ))
        # City-map cantina stays CONTESTED — no citadel upgrade leak
        self.assertEqual(result, SecurityLevel.CONTESTED)


# ──────────────────────────────────────────────────────────────────────
# 6. Director overlays still short-circuit
# ──────────────────────────────────────────────────────────────────────

class TestDirectorOverlayRunsFirst(unittest.TestCase):
    """Steps 1-3 (Director overrides) run before step 4 and short-
    circuit it. A wilderness room with an active admin override
    should yield the override level, not the wilderness-branch
    resolution."""

    def setUp(self):
        from engine.security import clear_all_overrides
        clear_all_overrides()

    def tearDown(self):
        from engine.security import clear_all_overrides
        clear_all_overrides()

    def test_admin_override_wins_over_wilderness_branch(self):
        from engine.security import (
            get_effective_security, set_security_override, SecurityLevel,
        )
        db = _make_wilderness_db(owner="hutt_cartel", default_security="lawless")
        # Step 1 admin override: force SECURED on zone 50
        set_security_override(50, SecurityLevel.SECURED)
        # A Hutt in their own owned region — wilderness branch would
        # give CONTESTED. But step 1 SECURED should win.
        result = _run(get_effective_security(
            100, db, character=_char(faction_id="hutt_cartel"),
        ))
        # _finalize's _apply_faction_override doesn't fire (no override
        # tag on room); _apply_city_upgrade doesn't fire (not a citizen).
        # So SECURED stands.
        self.assertEqual(result, SecurityLevel.SECURED)


if __name__ == "__main__":
    unittest.main()
