# -*- coding: utf-8 -*-
"""
tests/test_cities_phase6_admin.py — Player Cities Phase 6 admin tools
(May 23 2026).

Per ``player_cities_design_v1_2.md`` §11.5 (admin command surface)
and §13 Phase 6 ("admin tools" line of Phase 6 polish). Ships the
six admin subcommands of ``@city`` (AccessLevel.ADMIN):

  @city list
  @city inspect <name>
  @city void-banish <city> = <player>
  @city set-rate-cap <city> = <pct>
  @city dissolve <name>
  @city rename <old> = <new>

Fixture discipline (per v47 §4.20): uses the `_FakeDB` with
mutation log pattern. The fake records every write call as a
tuple in `self.writes`; tests assert on **what was written**, not
just that a write happened (cheap insurance against
"row got modified even though the command rejected" bugs).

Test sections
=============

Engine helpers (sections 1–14):
  1.  TestListAllCitiesActiveOnly        — default excludes dissolved
  2.  TestListAllCitiesIncludeDissolved  — flag includes dissolved
  3.  TestListAllCitiesOrdering          — oldest first

  4.  TestAdminDissolveHappyPath         — write + cascade-clean
  5.  TestAdminDissolveNoRefund          — treasury untouched
  6.  TestAdminDissolveUnknownCity       — error, no writes
  7.  TestAdminDissolveBadName           — invalid name rejected
  8.  TestAdminDissolveAlreadyDissolved  — error (not 'active')

  9.  TestAdminUnbanishHappyPath         — single banishment lifted
 10.  TestAdminUnbanishUnknownCity       — error, no writes
 11.  TestAdminUnbanishUnknownTarget     — error, no writes
 12.  TestAdminUnbanishNotBanished       — error, no writes (idempotent)

 13.  TestAdminSetRateCapHappyPath       — write + correct value
 14.  TestAdminSetRateCapClamps          — current rate above cap → clamped
 15.  TestAdminSetRateCapBelowMin        — error, no writes
 16.  TestAdminSetRateCapAboveMax        — error, no writes
 17.  TestAdminSetRateCapBadValue        — non-numeric → error
 18.  TestAdminSetRateCapUnknownCity     — error, no writes

 19.  TestAdminRenameHappyPath           — write + name + name_lower
 20.  TestAdminRenameUnknownCity         — error, no writes
 21.  TestAdminRenameSameName            — error (no-op rename)
 22.  TestAdminRenameCollision           — active-name conflict → error
 23.  TestAdminRenameInvalidNew          — bad name → error

 24.  TestFormatInspectBasics            — name/id/state/tier rendered
 25.  TestFormatInspectTaxation          — tax + cap + revenue lines
 26.  TestFormatInspectRooms             — room counts (HQ + expansion + citizen_only)
 27.  TestFormatInspectBanishments       — list shown, count line accurate

Parser (AdminCityCommand) (sections 28–...):
 28.  TestCommandSurface                 — class attrs, registration
 29.  TestParsePctHelper                 — _parse_pct lenient + invalid
 30.  TestSplitOnEqualsHelper            — _split_on_equals

 31.  TestParserUsageOnEmpty             — bare @city → usage
 32.  TestParserUnknownSubcommand        — bad first token → error
 33.  TestParserListHappy                — @city list → renders
 34.  TestParserListEmpty                — no cities → no-cities line
 35.  TestParserListIncludeDissolved     — @city list all → includes dissolved

 36.  TestParserInspectHappy             — @city inspect <name> → renders
 37.  TestParserInspectMissingName       — error, no writes
 38.  TestParserInspectUnknown           — error, no writes

 39.  TestParserVoidBanishHappy          — write + success msg
 40.  TestParserVoidBanishMissingEquals  — error, no writes
 41.  TestParserVoidBanishMissingParts   — error, no writes

 42.  TestParserSetRateCapHappy          — write + correct value
 43.  TestParserSetRateCapPercentForms   — 5, 5%, 0.05 all parse to 0.05
 44.  TestParserSetRateCapBadValue       — error, no writes
 45.  TestParserSetRateCapMissingParts   — error, no writes

 46.  TestParserDissolveHappy            — write + success msg
 47.  TestParserDissolveMissingName      — error, no writes

 48.  TestParserRenameHappy              — write + success msg
 49.  TestParserRenameMissingParts       — error, no writes

 50.  TestParserAdminNameResolution      — _admin_name char/account fallbacks
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ═════════════════════════════════════════════════════════════════════
# _FakeDB — mutation-log pattern per v47 §4.20.
#
# Implements only the methods Phase 6 helpers actually call:
#   - fetchall(sql, params=())          (engine list/inspect reads)
#   - execute(sql, params=())           (engine writes)
#   - commit()                          (no-op; mutation log is what matters)
#   - get_character(char_id)            (inspect, void-banish lookups)
#   - get_character_by_name(name)       (void-banish target lookup)
#   - get_organization(code)            (not used directly by Phase 6;
#                                        included for safety against
#                                        future inspect-org integration)
#
# The fake stores the in-memory state needed for the assertions
# (cities, banishments, guests, rooms, characters) and records every
# write as a tuple in self.writes for "what was written" assertions.
# ═════════════════════════════════════════════════════════════════════


class _FakeDB:
    """Minimal DB fake for Phase 6 admin engine + parser tests.

    Only the methods Phase 6 helpers actually call are implemented;
    any other attribute access succeeds quietly (intentionally:
    `format_city_inspect`'s try/except blocks need to be exercisable
    without a full DB shape). Mutation log is the assertion anchor.
    """

    def __init__(self):
        # Cities keyed by id; row is a dict matching player_cities columns
        self.cities = {}
        self.city_name_index = {}  # lowercase name → id (active only)
        # Banishments keyed by (city_id, char_id) → row dict
        self.banishments = {}
        # Guests keyed by (city_id, char_id) → row dict
        self.guests = {}
        # City rooms keyed by (city_id, room_id) → row dict
        self.city_rooms = {}
        # Characters keyed by id; also a name index (lowercase → id)
        self.characters = {}
        self.char_name_index = {}
        # Mutation log: list of (op, sql_or_action, params)
        self.writes = []

    # ── Seeders ──────────────────────────────────────────────────────

    def add_city(self, city_id, name, *, org_id=1, state="active",
                 hq_tier="outpost", tax_rate=0.0, rate_cap=0.10,
                 revenue_total=0, revenue_week=0,
                 founded_at=None, founder_id=10, mayor_id=10,
                 hq_id=1, zone_id=1, motd="",
                 week_start_ts=None):
        now = time.time()
        row = {
            "id": city_id,
            "name": name,
            "name_lower": name.lower(),
            "org_id": org_id,
            "hq_id": hq_id,
            "zone_id": zone_id,
            "is_wilderness": 0,
            "wilderness_region_id": None,
            "wilderness_x": None,
            "wilderness_y": None,
            "is_hidden": 0,
            "search_difficulty": 20,
            "visibility_factions": "[]",
            "founded_at": founded_at if founded_at is not None else now,
            "founder_id": founder_id,
            "mayor_id": mayor_id,
            "tax_rate": tax_rate,
            "rate_cap": rate_cap,
            "motd": motd,
            "state": state,
            "grace_started_at": 0,
            "revenue_total": revenue_total,
            "revenue_week": revenue_week,
            "week_start_ts": week_start_ts if week_start_ts is not None else now,
            "hq_tier": hq_tier,
        }
        self.cities[city_id] = row
        if state != "dissolved":
            self.city_name_index[name.lower()] = city_id
        return row

    def add_char(self, char_id, name, **extra):
        row = {"id": char_id, "name": name}
        row.update(extra)
        self.characters[char_id] = row
        self.char_name_index[name.lower()] = char_id
        return row

    def add_banishment(self, city_id, char_id, *, until=None,
                       issued_by=10, issued_at=None):
        now = time.time()
        row = {
            "city_id": city_id, "char_id": char_id,
            "until": until if until is not None else now + 86400,
            "issued_by": issued_by,
            "issued_at": issued_at if issued_at is not None else now,
        }
        self.banishments[(city_id, char_id)] = row
        return row

    def add_city_room(self, city_id, room_id, *, is_center=0,
                      citizen_only=0, claimed_at=None):
        row = {
            "city_id": city_id, "room_id": room_id,
            "is_center": is_center, "citizen_only": citizen_only,
            "claimed_at": claimed_at if claimed_at is not None else time.time(),
        }
        self.city_rooms[(city_id, room_id)] = row
        return row

    # ── Read methods ────────────────────────────────────────────────

    async def fetchall(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # player_cities reads
        if s.startswith("SELECT * FROM player_cities WHERE state != 'dissolved' ORDER BY founded_at ASC"):
            rows = [r for r in self.cities.values() if r["state"] != "dissolved"]
            rows.sort(key=lambda r: r["founded_at"])
            return [dict(r) for r in rows]
        if s.startswith("SELECT * FROM player_cities ORDER BY founded_at ASC"):
            rows = list(self.cities.values())
            rows.sort(key=lambda r: r["founded_at"])
            return [dict(r) for r in rows]
        if s.startswith("SELECT * FROM player_cities WHERE state != 'dissolved' AND zone_id = ? ORDER BY founded_at ASC"):
            zone_id = params[0]
            rows = [r for r in self.cities.values()
                    if r["state"] != "dissolved" and r["zone_id"] == zone_id]
            rows.sort(key=lambda r: r["founded_at"])
            return [dict(r) for r in rows]
        # get_city_by_name uses a different SELECT (LOWER on name_lower);
        # we route those via the named accessor below.
        if "FROM player_cities WHERE LOWER(name_lower)" in s or \
           ("FROM player_cities WHERE name_lower" in s):
            target = (params[0] or "").lower() if params else ""
            for r in self.cities.values():
                if r["name_lower"] == target and r["state"] != "dissolved":
                    return [dict(r)]
            return []
        # Banishment read (admin_unbanish presence check)
        if "FROM player_city_banishments WHERE city_id = ? AND char_id = ?" in s:
            cid, charid = params
            row = self.banishments.get((cid, charid))
            return [dict(row)] if row else []
        # Active banishments (list_active_banishments)
        if "FROM player_city_banishments WHERE city_id = ? AND until > ?" in s:
            cid, _now = params
            now = time.time()
            rows = [r for k, r in self.banishments.items()
                    if k[0] == cid and r["until"] > now]
            rows.sort(key=lambda r: r["issued_at"], reverse=True)
            return [dict(r) for r in rows]
        # Citizen-only room ids (list_citizen_room_ids)
        if "FROM player_city_rooms WHERE city_id = ? AND citizen_only = 1" in s:
            cid = params[0]
            rows = [r for k, r in self.city_rooms.items()
                    if k[0] == cid and r["citizen_only"] == 1]
            return [{"room_id": r["room_id"]} for r in rows]
        # All city rooms (list_city_room_ids)
        if "FROM player_city_rooms WHERE city_id = ?" in s and "ORDER BY is_center DESC" in s:
            cid = params[0]
            rows = [r for k, r in self.city_rooms.items() if k[0] == cid]
            rows.sort(key=lambda r: (-r["is_center"], r["claimed_at"]))
            return [{"room_id": r["room_id"]} for r in rows]
        # Center-count (used by format_city_inspect)
        if "COUNT(*) AS n FROM player_city_rooms WHERE city_id = ? AND is_center = 1" in s:
            cid = params[0]
            n = sum(1 for k, r in self.city_rooms.items()
                    if k[0] == cid and r["is_center"] == 1)
            return [{"n": n}]
        # Guests (list_guests)
        if "FROM player_city_guests WHERE city_id = ?" in s and "ORDER BY added_at" in s:
            cid = params[0]
            rows = [r for k, r in self.guests.items() if k[0] == cid]
            rows.sort(key=lambda r: r.get("added_at", 0))
            return [{"char_id": r["char_id"]} for r in rows]
        # Any other fetchall: empty (fail-soft for unmodeled paths)
        return []

    async def execute(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # ── Writes for admin_dissolve_city ──
        if s.startswith("DELETE FROM player_city_rooms WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.city_rooms if k[0] == cid]
            for k in removed:
                del self.city_rooms[k]
            self.writes.append(("delete_city_rooms", cid, len(removed)))
            return MagicMock()
        if s.startswith("DELETE FROM player_city_banishments WHERE city_id = ? AND char_id = ?"):
            cid, charid = params
            existed = (cid, charid) in self.banishments
            self.banishments.pop((cid, charid), None)
            self.writes.append(("delete_banishment", cid, charid, existed))
            return MagicMock()
        if s.startswith("DELETE FROM player_city_banishments WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.banishments if k[0] == cid]
            for k in removed:
                del self.banishments[k]
            self.writes.append(("delete_city_banishments", cid, len(removed)))
            return MagicMock()
        if s.startswith("DELETE FROM player_city_guests WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.guests if k[0] == cid]
            for k in removed:
                del self.guests[k]
            self.writes.append(("delete_city_guests", cid, len(removed)))
            return MagicMock()
        if s.startswith("UPDATE player_cities SET state = 'dissolved' WHERE id = ?"):
            (cid,) = params
            if cid in self.cities:
                old_name = self.cities[cid]["name_lower"]
                self.cities[cid]["state"] = "dissolved"
                # Drop from active-name index
                if self.city_name_index.get(old_name) == cid:
                    del self.city_name_index[old_name]
            self.writes.append(("update_state_dissolved", cid))
            return MagicMock()
        # ── Writes for admin_set_rate_cap ──
        if s.startswith("UPDATE player_cities SET tax_rate = ?, rate_cap = ? WHERE id = ?"):
            rate, cap, cid = params
            if cid in self.cities:
                self.cities[cid]["tax_rate"] = rate
                self.cities[cid]["rate_cap"] = cap
            self.writes.append(("update_rate_and_cap", cid, rate, cap))
            return MagicMock()
        if s.startswith("UPDATE player_cities SET rate_cap = ? WHERE id = ?"):
            cap, cid = params
            if cid in self.cities:
                self.cities[cid]["rate_cap"] = cap
            self.writes.append(("update_rate_cap", cid, cap))
            return MagicMock()
        # ── Writes for admin_rename_city ──
        if s.startswith("UPDATE player_cities SET name = ?, name_lower = ? WHERE id = ?"):
            new_name, new_name_lower, cid = params
            if cid in self.cities:
                old_lower = self.cities[cid]["name_lower"]
                self.cities[cid]["name"] = new_name
                self.cities[cid]["name_lower"] = new_name_lower
                # Update index
                if old_lower in self.city_name_index:
                    del self.city_name_index[old_lower]
                if self.cities[cid]["state"] != "dissolved":
                    self.city_name_index[new_name_lower] = cid
            self.writes.append(("update_name", cid, new_name, new_name_lower))
            return MagicMock()
        # Any other execute: record and no-op
        self.writes.append(("unhandled_execute", s, params))
        return MagicMock()

    async def commit(self):
        # No-op; mutation log is what matters.
        return None

    async def get_character(self, char_id):
        return self.characters.get(int(char_id))

    async def get_character_by_name(self, name):
        if not name:
            return None
        cid = self.char_name_index.get(name.lower())
        return self.characters.get(cid) if cid else None

    async def adjust_org_treasury(self, org_id, amount):
        # Not used by admin_dissolve (no refund), but called by player
        # dissolve_city which we DON'T test here. Including for safety.
        self.writes.append(("adjust_org_treasury", org_id, amount))


# ═════════════════════════════════════════════════════════════════════
# get_city_by_name shim: the engine helper uses LOWER() in its real
# SQL, but our _FakeDB.fetchall is matched on a different SQL template.
# We monkey-patch get_city_by_name in the engine module to use a path
# the fake handles. This keeps the fake simple and isolates engine
# tests from the get_city_by_name SQL form.
# ═════════════════════════════════════════════════════════════════════


def _install_fake_get_city_by_name(fake_db):
    """Override engine.player_cities.get_city_by_name so tests use the
    fake's name index without needing real SQL matching.

    Returns the original function for restoration.
    """
    from engine import player_cities as pc

    original = pc.get_city_by_name

    async def fake_get_city_by_name(db, name):
        if db is not fake_db:
            return await original(db, name)
        if not name:
            return None
        cid = fake_db.city_name_index.get(name.lower())
        if cid:
            return dict(fake_db.cities[cid])
        return None

    pc.get_city_by_name = fake_get_city_by_name
    return original


def _restore_get_city_by_name(original):
    from engine import player_cities as pc
    pc.get_city_by_name = original


class _PCNamedDBMixin:
    """Mixin that wires _install/_restore around setUp/tearDown."""

    def setUp(self):
        self.db = _FakeDB()
        self._orig_gcbn = _install_fake_get_city_by_name(self.db)

    def tearDown(self):
        _restore_get_city_by_name(self._orig_gcbn)


# ═════════════════════════════════════════════════════════════════════
# 1. TestListAllCitiesActiveOnly
# ═════════════════════════════════════════════════════════════════════

class TestListAllCitiesActiveOnly(_PCNamedDBMixin, unittest.TestCase):
    def test_excludes_dissolved_by_default(self):
        from engine.player_cities import list_all_cities
        self.db.add_city(1, "Bright", state="active",
                         founded_at=100.0)
        self.db.add_city(2, "Dead", state="dissolved",
                         founded_at=200.0)
        rows = _run(list_all_cities(self.db))
        names = [r["name"] for r in rows]
        self.assertEqual(names, ["Bright"])
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 2. TestListAllCitiesIncludeDissolved
# ═════════════════════════════════════════════════════════════════════

class TestListAllCitiesIncludeDissolved(_PCNamedDBMixin, unittest.TestCase):
    def test_include_dissolved_returns_all(self):
        from engine.player_cities import list_all_cities
        self.db.add_city(1, "Bright", state="active",
                         founded_at=100.0)
        self.db.add_city(2, "Dead", state="dissolved",
                         founded_at=50.0)
        rows = _run(list_all_cities(self.db, include_dissolved=True))
        names = [r["name"] for r in rows]
        # Oldest first → Dead (50) before Bright (100)
        self.assertEqual(names, ["Dead", "Bright"])


# ═════════════════════════════════════════════════════════════════════
# 3. TestListAllCitiesOrdering
# ═════════════════════════════════════════════════════════════════════

class TestListAllCitiesOrdering(_PCNamedDBMixin, unittest.TestCase):
    def test_oldest_first(self):
        from engine.player_cities import list_all_cities
        self.db.add_city(1, "B", state="active", founded_at=300.0)
        self.db.add_city(2, "A", state="active", founded_at=100.0)
        self.db.add_city(3, "C", state="active", founded_at=200.0)
        rows = _run(list_all_cities(self.db))
        self.assertEqual([r["name"] for r in rows], ["A", "C", "B"])


# ═════════════════════════════════════════════════════════════════════
# 4. TestAdminDissolveHappyPath
# ═════════════════════════════════════════════════════════════════════

class TestAdminDissolveHappyPath(_PCNamedDBMixin, unittest.TestCase):
    def test_dissolve_cascades_and_marks(self):
        from engine.player_cities import admin_dissolve_city
        self.db.add_city(1, "Foo", state="active")
        self.db.add_city_room(1, 100, is_center=1)
        self.db.add_city_room(1, 101)
        self.db.add_banishment(1, 50)
        self.db.add_banishment(1, 51)
        self.db.add_char(50, "Targ50")

        ok, msg = _run(admin_dissolve_city(self.db, "Foo",
                                            admin_name="GM"))
        self.assertTrue(ok)
        self.assertIn("force-dissolved", msg.lower())
        # All four writes happened, in order
        ops = [w[0] for w in self.db.writes]
        self.assertEqual(ops, [
            "delete_city_rooms",
            "delete_city_banishments",
            "delete_city_guests",
            "update_state_dissolved",
        ])
        # State on row is now 'dissolved'
        self.assertEqual(self.db.cities[1]["state"], "dissolved")
        # All city rooms / banishments cleaned
        self.assertEqual(len(self.db.city_rooms), 0)
        self.assertEqual(len(self.db.banishments), 0)


# ═════════════════════════════════════════════════════════════════════
# 5. TestAdminDissolveNoRefund
# ═════════════════════════════════════════════════════════════════════

class TestAdminDissolveNoRefund(_PCNamedDBMixin, unittest.TestCase):
    def test_no_treasury_adjustment(self):
        from engine.player_cities import admin_dissolve_city
        self.db.add_city(1, "Foo", state="active")
        _run(admin_dissolve_city(self.db, "Foo"))
        # adjust_org_treasury must NOT appear in writes — admin
        # moderation does not refund
        treasury_writes = [w for w in self.db.writes
                           if w[0] == "adjust_org_treasury"]
        self.assertEqual(treasury_writes, [])


# ═════════════════════════════════════════════════════════════════════
# 6. TestAdminDissolveUnknownCity
# ═════════════════════════════════════════════════════════════════════

class TestAdminDissolveUnknownCity(_PCNamedDBMixin, unittest.TestCase):
    def test_no_such_city_no_writes(self):
        from engine.player_cities import admin_dissolve_city
        ok, msg = _run(admin_dissolve_city(self.db, "Nope"))
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 7. TestAdminDissolveBadName
# ═════════════════════════════════════════════════════════════════════

class TestAdminDissolveBadName(_PCNamedDBMixin, unittest.TestCase):
    def test_too_short_rejected(self):
        from engine.player_cities import admin_dissolve_city
        ok, msg = _run(admin_dissolve_city(self.db, "ab"))
        self.assertFalse(ok)
        # name validation error
        self.assertEqual(self.db.writes, [])

    def test_empty_rejected(self):
        from engine.player_cities import admin_dissolve_city
        ok, msg = _run(admin_dissolve_city(self.db, ""))
        self.assertFalse(ok)
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 8. TestAdminDissolveAlreadyDissolved
# ═════════════════════════════════════════════════════════════════════

class TestAdminDissolveAlreadyDissolved(_PCNamedDBMixin, unittest.TestCase):
    def test_dissolved_city_not_found(self):
        """An already-dissolved city isn't in the active-name index,
        so the helper returns 'no active city named X' — clear no-op
        signal for the admin."""
        from engine.player_cities import admin_dissolve_city
        self.db.add_city(1, "Foo", state="dissolved")
        ok, msg = _run(admin_dissolve_city(self.db, "Foo"))
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 9. TestAdminUnbanishHappyPath
# ═════════════════════════════════════════════════════════════════════

class TestAdminUnbanishHappyPath(_PCNamedDBMixin, unittest.TestCase):
    def test_single_banishment_lifted(self):
        from engine.player_cities import admin_unbanish
        self.db.add_city(1, "Foo", state="active")
        self.db.add_char(50, "Banned")
        self.db.add_banishment(1, 50)

        ok, msg = _run(admin_unbanish(self.db, "Foo", "Banned",
                                       admin_name="GM"))
        self.assertTrue(ok)
        self.assertIn("admin lifted", msg.lower())
        # Single write: the delete
        del_writes = [w for w in self.db.writes
                      if w[0] == "delete_banishment"]
        self.assertEqual(len(del_writes), 1)
        cid, charid, existed = del_writes[0][1:]
        self.assertEqual((cid, charid), (1, 50))
        self.assertTrue(existed)
        # Row is gone
        self.assertNotIn((1, 50), self.db.banishments)


# ═════════════════════════════════════════════════════════════════════
# 10. TestAdminUnbanishUnknownCity
# ═════════════════════════════════════════════════════════════════════

class TestAdminUnbanishUnknownCity(_PCNamedDBMixin, unittest.TestCase):
    def test_unknown_city_no_writes(self):
        from engine.player_cities import admin_unbanish
        self.db.add_char(50, "Banned")
        ok, msg = _run(admin_unbanish(self.db, "Nope", "Banned"))
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 11. TestAdminUnbanishUnknownTarget
# ═════════════════════════════════════════════════════════════════════

class TestAdminUnbanishUnknownTarget(_PCNamedDBMixin, unittest.TestCase):
    def test_unknown_target_no_writes(self):
        from engine.player_cities import admin_unbanish
        self.db.add_city(1, "Foo", state="active")
        ok, msg = _run(admin_unbanish(self.db, "Foo", "Ghost"))
        self.assertFalse(ok)
        self.assertIn("no character", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 12. TestAdminUnbanishNotBanished
# ═════════════════════════════════════════════════════════════════════

class TestAdminUnbanishNotBanished(_PCNamedDBMixin, unittest.TestCase):
    def test_not_banished_no_writes(self):
        from engine.player_cities import admin_unbanish
        self.db.add_city(1, "Foo", state="active")
        self.db.add_char(50, "Free")
        # No banishment on record
        ok, msg = _run(admin_unbanish(self.db, "Foo", "Free"))
        self.assertFalse(ok)
        self.assertIn("is not banished", msg.lower())
        # No delete write
        del_writes = [w for w in self.db.writes
                      if w[0] == "delete_banishment"]
        self.assertEqual(del_writes, [])


# ═════════════════════════════════════════════════════════════════════
# 13. TestAdminSetRateCapHappyPath
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapHappyPath(_PCNamedDBMixin, unittest.TestCase):
    def test_writes_cap_no_clamp(self):
        from engine.player_cities import admin_set_rate_cap
        self.db.add_city(1, "Foo", tax_rate=0.02, rate_cap=0.05)
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo", 0.08,
                                           admin_name="GM"))
        self.assertTrue(ok)
        self.assertIn("8.0%", msg)
        # Just rate_cap updated (rate was below new cap)
        cap_writes = [w for w in self.db.writes
                      if w[0] == "update_rate_cap"]
        self.assertEqual(len(cap_writes), 1)
        self.assertEqual(cap_writes[0][1], 1)   # city_id
        self.assertAlmostEqual(cap_writes[0][2], 0.08)
        # rate_and_cap path NOT taken
        clamp_writes = [w for w in self.db.writes
                        if w[0] == "update_rate_and_cap"]
        self.assertEqual(clamp_writes, [])


# ═════════════════════════════════════════════════════════════════════
# 14. TestAdminSetRateCapClamps
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapClamps(_PCNamedDBMixin, unittest.TestCase):
    def test_rate_above_new_cap_clamped(self):
        from engine.player_cities import admin_set_rate_cap
        self.db.add_city(1, "Foo", tax_rate=0.08, rate_cap=0.10)
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo", 0.05))
        self.assertTrue(ok)
        self.assertIn("clamped", msg.lower())
        # rate_and_cap write path
        clamp = [w for w in self.db.writes
                 if w[0] == "update_rate_and_cap"]
        self.assertEqual(len(clamp), 1)
        _, cid, rate, cap = clamp[0]
        self.assertEqual(cid, 1)
        self.assertAlmostEqual(rate, 0.05)
        self.assertAlmostEqual(cap, 0.05)


# ═════════════════════════════════════════════════════════════════════
# 15. TestAdminSetRateCapBelowMin
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapBelowMin(_PCNamedDBMixin, unittest.TestCase):
    def test_negative_rejected(self):
        from engine.player_cities import admin_set_rate_cap
        self.db.add_city(1, "Foo")
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo", -0.01))
        self.assertFalse(ok)
        # No update writes
        update_writes = [w for w in self.db.writes
                         if w[0].startswith("update_")]
        self.assertEqual(update_writes, [])


# ═════════════════════════════════════════════════════════════════════
# 16. TestAdminSetRateCapAboveMax
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapAboveMax(_PCNamedDBMixin, unittest.TestCase):
    def test_above_ceiling_rejected(self):
        from engine.player_cities import admin_set_rate_cap, MAX_TAX_RATE
        self.db.add_city(1, "Foo")
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo",
                                           MAX_TAX_RATE + 0.01))
        self.assertFalse(ok)
        self.assertIn("exceeds", msg.lower())
        update_writes = [w for w in self.db.writes
                         if w[0].startswith("update_")]
        self.assertEqual(update_writes, [])

    def test_exactly_at_ceiling_ok(self):
        from engine.player_cities import admin_set_rate_cap, MAX_TAX_RATE
        self.db.add_city(1, "Foo")
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo", MAX_TAX_RATE))
        self.assertTrue(ok)


# ═════════════════════════════════════════════════════════════════════
# 17. TestAdminSetRateCapBadValue
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapBadValue(_PCNamedDBMixin, unittest.TestCase):
    def test_non_numeric(self):
        from engine.player_cities import admin_set_rate_cap
        self.db.add_city(1, "Foo")
        ok, msg = _run(admin_set_rate_cap(self.db, "Foo", "abc"))
        self.assertFalse(ok)
        self.assertEqual([w for w in self.db.writes
                          if w[0].startswith("update_")], [])


# ═════════════════════════════════════════════════════════════════════
# 18. TestAdminSetRateCapUnknownCity
# ═════════════════════════════════════════════════════════════════════

class TestAdminSetRateCapUnknownCity(_PCNamedDBMixin, unittest.TestCase):
    def test_unknown_city(self):
        from engine.player_cities import admin_set_rate_cap
        ok, msg = _run(admin_set_rate_cap(self.db, "Nope", 0.05))
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 19. TestAdminRenameHappyPath
# ═════════════════════════════════════════════════════════════════════

class TestAdminRenameHappyPath(_PCNamedDBMixin, unittest.TestCase):
    def test_rename_writes_both_columns(self):
        from engine.player_cities import admin_rename_city
        self.db.add_city(1, "OldName", state="active")
        ok, msg = _run(admin_rename_city(self.db, "OldName",
                                           "NewName"))
        self.assertTrue(ok)
        self.assertIn("NewName", msg)
        # Single write: update name + name_lower
        renames = [w for w in self.db.writes if w[0] == "update_name"]
        self.assertEqual(len(renames), 1)
        _, cid, name, name_lower = renames[0]
        self.assertEqual((cid, name, name_lower),
                         (1, "NewName", "newname"))
        # Row updated; index updated
        self.assertEqual(self.db.cities[1]["name"], "NewName")
        self.assertEqual(self.db.cities[1]["name_lower"], "newname")
        self.assertIn("newname", self.db.city_name_index)
        self.assertNotIn("oldname", self.db.city_name_index)


# ═════════════════════════════════════════════════════════════════════
# 20. TestAdminRenameUnknownCity
# ═════════════════════════════════════════════════════════════════════

class TestAdminRenameUnknownCity(_PCNamedDBMixin, unittest.TestCase):
    def test_unknown_no_writes(self):
        from engine.player_cities import admin_rename_city
        ok, msg = _run(admin_rename_city(self.db, "Nope", "Yes"))
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 21. TestAdminRenameSameName
# ═════════════════════════════════════════════════════════════════════

class TestAdminRenameSameName(_PCNamedDBMixin, unittest.TestCase):
    def test_same_name_rejected(self):
        from engine.player_cities import admin_rename_city
        self.db.add_city(1, "Foo", state="active")
        ok, msg = _run(admin_rename_city(self.db, "Foo", "FOO"))
        self.assertFalse(ok)
        self.assertIn("already named", msg.lower())
        # No write
        self.assertEqual([w for w in self.db.writes
                          if w[0] == "update_name"], [])


# ═════════════════════════════════════════════════════════════════════
# 22. TestAdminRenameCollision
# ═════════════════════════════════════════════════════════════════════

class TestAdminRenameCollision(_PCNamedDBMixin, unittest.TestCase):
    def test_active_collision_rejected(self):
        from engine.player_cities import admin_rename_city
        self.db.add_city(1, "Foo", state="active")
        self.db.add_city(2, "Bar", state="active")
        ok, msg = _run(admin_rename_city(self.db, "Foo", "Bar"))
        self.assertFalse(ok)
        self.assertIn("already named", msg.lower())
        # No write
        self.assertEqual([w for w in self.db.writes
                          if w[0] == "update_name"], [])


# ═════════════════════════════════════════════════════════════════════
# 23. TestAdminRenameInvalidNew
# ═════════════════════════════════════════════════════════════════════

class TestAdminRenameInvalidNew(_PCNamedDBMixin, unittest.TestCase):
    def test_too_short(self):
        from engine.player_cities import admin_rename_city
        self.db.add_city(1, "Foo", state="active")
        ok, msg = _run(admin_rename_city(self.db, "Foo", "ab"))
        self.assertFalse(ok)
        self.assertEqual([w for w in self.db.writes
                          if w[0] == "update_name"], [])


# ═════════════════════════════════════════════════════════════════════
# 24. TestFormatInspectBasics
# ═════════════════════════════════════════════════════════════════════

class TestFormatInspectBasics(_PCNamedDBMixin, unittest.TestCase):
    def test_renders_name_id_state_tier(self):
        from engine.player_cities import format_city_inspect
        self.db.add_city(1, "Foo", state="active", hq_tier="fortress",
                         org_id=7, founder_id=10, mayor_id=11)
        self.db.add_char(10, "Alice")
        self.db.add_char(11, "Bob")
        lines = _run(format_city_inspect(
            self.db, dict(self.db.cities[1])))
        joined = "\n".join(lines)
        self.assertIn("Foo", joined)
        self.assertIn("id=1", joined)
        self.assertIn("state=active", joined)
        self.assertIn("fortress", joined)
        self.assertIn("Alice", joined)
        self.assertIn("Bob", joined)


# ═════════════════════════════════════════════════════════════════════
# 25. TestFormatInspectTaxation
# ═════════════════════════════════════════════════════════════════════

class TestFormatInspectTaxation(_PCNamedDBMixin, unittest.TestCase):
    def test_tax_cap_revenue_lines(self):
        from engine.player_cities import format_city_inspect
        self.db.add_city(1, "Foo", tax_rate=0.05, rate_cap=0.10,
                         revenue_total=12345, revenue_week=678)
        lines = _run(format_city_inspect(
            self.db, dict(self.db.cities[1])))
        joined = "\n".join(lines)
        self.assertIn("5.0%", joined)
        self.assertIn("10.0%", joined)
        self.assertIn("12,345", joined)
        self.assertIn("678", joined)


# ═════════════════════════════════════════════════════════════════════
# 26. TestFormatInspectRooms
# ═════════════════════════════════════════════════════════════════════

class TestFormatInspectRooms(_PCNamedDBMixin, unittest.TestCase):
    def test_room_counts_accurate(self):
        from engine.player_cities import format_city_inspect
        self.db.add_city(1, "Foo")
        # 2 HQ rooms, 3 expansion rooms, 1 citizen_only (an HQ)
        self.db.add_city_room(1, 100, is_center=1, citizen_only=1)
        self.db.add_city_room(1, 101, is_center=1)
        self.db.add_city_room(1, 200)
        self.db.add_city_room(1, 201)
        self.db.add_city_room(1, 202)
        lines = _run(format_city_inspect(
            self.db, dict(self.db.cities[1])))
        joined = "\n".join(lines)
        self.assertIn("5 total", joined)
        self.assertIn("2 HQ", joined)
        self.assertIn("3 expansion", joined)
        self.assertIn("1 citizen-only", joined)


# ═════════════════════════════════════════════════════════════════════
# 27. TestFormatInspectBanishments
# ═════════════════════════════════════════════════════════════════════

class TestFormatInspectBanishments(_PCNamedDBMixin, unittest.TestCase):
    def test_banishments_listed(self):
        from engine.player_cities import format_city_inspect
        now = time.time()
        self.db.add_city(1, "Foo")
        self.db.add_char(50, "Targ1")
        self.db.add_char(51, "Targ2")
        self.db.add_banishment(1, 50, until=now + 3600,
                                issued_at=now - 100)
        self.db.add_banishment(1, 51, until=now + 7200,
                                issued_at=now - 50)
        lines = _run(format_city_inspect(
            self.db, dict(self.db.cities[1])))
        joined = "\n".join(lines)
        self.assertIn("active banishments: 2", joined)
        self.assertIn("Targ1", joined)
        self.assertIn("Targ2", joined)

    def test_zero_banishments(self):
        from engine.player_cities import format_city_inspect
        self.db.add_city(1, "Foo")
        lines = _run(format_city_inspect(
            self.db, dict(self.db.cities[1])))
        joined = "\n".join(lines)
        self.assertIn("active banishments: 0", joined)


# ═════════════════════════════════════════════════════════════════════
# Parser fixture
# ═════════════════════════════════════════════════════════════════════


class _FakeSession:
    def __init__(self):
        self.sent = []
        self.is_in_game = True
        self.character = None
        self.account = None

    async def send_line(self, line):
        self.sent.append(line)


def _make_ctx(db, args, *, session=None):
    sess = session or _FakeSession()
    ctx = MagicMock()
    ctx.session = sess
    ctx.db = db
    ctx.args = args
    ctx.args_list = args.split() if args else []
    return ctx


# ═════════════════════════════════════════════════════════════════════
# 28. TestCommandSurface
# ═════════════════════════════════════════════════════════════════════

class TestCommandSurface(unittest.TestCase):
    def test_class_attrs(self):
        from parser.admin_city_commands import AdminCityCommand
        from parser.commands import AccessLevel
        self.assertEqual(AdminCityCommand.key, "@city")
        self.assertEqual(AdminCityCommand.access_level,
                         AccessLevel.ADMIN)
        self.assertTrue(AdminCityCommand.help_text)
        self.assertTrue(AdminCityCommand.usage)

    def test_register(self):
        from parser.admin_city_commands import (
            register_admin_city_commands, AdminCityCommand,
        )
        registered = []

        class FakeRegistry:
            def register(self, cmd):
                registered.append(cmd)

        register_admin_city_commands(FakeRegistry())
        self.assertEqual(len(registered), 1)
        self.assertIsInstance(registered[0], AdminCityCommand)


# ═════════════════════════════════════════════════════════════════════
# 29. TestParsePctHelper
# ═════════════════════════════════════════════════════════════════════

class TestParsePctHelper(unittest.TestCase):
    def test_percent_suffix(self):
        from parser.admin_city_commands import _parse_pct
        self.assertAlmostEqual(_parse_pct("5%"), 0.05)
        self.assertAlmostEqual(_parse_pct("10%"), 0.10)
        self.assertAlmostEqual(_parse_pct("0.5%"), 0.005)

    def test_integer_treated_as_percent(self):
        from parser.admin_city_commands import _parse_pct
        self.assertAlmostEqual(_parse_pct("5"), 0.05)
        self.assertAlmostEqual(_parse_pct("10"), 0.10)

    def test_fraction_form(self):
        from parser.admin_city_commands import _parse_pct
        self.assertAlmostEqual(_parse_pct("0.05"), 0.05)
        self.assertAlmostEqual(_parse_pct("0.10"), 0.10)
        self.assertAlmostEqual(_parse_pct("0"), 0.0)

    def test_invalid_returns_none(self):
        from parser.admin_city_commands import _parse_pct
        self.assertIsNone(_parse_pct("abc"))
        self.assertIsNone(_parse_pct(""))
        self.assertIsNone(_parse_pct("   "))
        self.assertIsNone(_parse_pct("-1"))
        self.assertIsNone(_parse_pct(None))

    def test_whitespace_tolerant(self):
        from parser.admin_city_commands import _parse_pct
        self.assertAlmostEqual(_parse_pct("  5%  "), 0.05)


# ═════════════════════════════════════════════════════════════════════
# 30. TestSplitOnEqualsHelper
# ═════════════════════════════════════════════════════════════════════

class TestSplitOnEqualsHelper(unittest.TestCase):
    def test_basic(self):
        from parser.admin_city_commands import _split_on_equals
        self.assertEqual(_split_on_equals("a = b"), ("a", "b"))
        self.assertEqual(_split_on_equals("a=b"), ("a", "b"))

    def test_no_equals(self):
        from parser.admin_city_commands import _split_on_equals
        self.assertEqual(_split_on_equals("foo"), ("foo", None))

    def test_first_equals_wins(self):
        from parser.admin_city_commands import _split_on_equals
        self.assertEqual(_split_on_equals("a = b = c"), ("a", "b = c"))

    def test_whitespace_stripped(self):
        from parser.admin_city_commands import _split_on_equals
        self.assertEqual(_split_on_equals("  foo  =  bar  "),
                         ("foo", "bar"))


# ═════════════════════════════════════════════════════════════════════
# 31. TestParserUsageOnEmpty
# ═════════════════════════════════════════════════════════════════════

class TestParserUsageOnEmpty(_PCNamedDBMixin, unittest.TestCase):
    def test_empty_args_prints_help(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        # Help mentions all six subcommands
        for sub in ("list", "inspect", "void-banish",
                    "set-rate-cap", "dissolve", "rename"):
            self.assertIn(sub, joined)
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 32. TestParserUnknownSubcommand
# ═════════════════════════════════════════════════════════════════════

class TestParserUnknownSubcommand(_PCNamedDBMixin, unittest.TestCase):
    def test_bad_first_token_error(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "explode all")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("unknown", joined.lower())
        self.assertIn("explode", joined)
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 33. TestParserListHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserListHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_list_renders_cities(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Alpha", state="active", founded_at=100.0)
        self.db.add_city(2, "Beta", state="active", founded_at=200.0)
        self.db.add_city(3, "Gone", state="dissolved", founded_at=50.0)
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "list")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        # Active cities only
        self.assertIn("Alpha", joined)
        self.assertIn("Beta", joined)
        # Dissolved excluded
        self.assertNotIn("Gone", joined)
        # Count line
        self.assertIn("2", joined)
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 34. TestParserListEmpty
# ═════════════════════════════════════════════════════════════════════

class TestParserListEmpty(_PCNamedDBMixin, unittest.TestCase):
    def test_empty_database_clean_message(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "list")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("no active cities", joined.lower())


# ═════════════════════════════════════════════════════════════════════
# 35. TestParserListIncludeDissolved
# ═════════════════════════════════════════════════════════════════════

class TestParserListIncludeDissolved(_PCNamedDBMixin, unittest.TestCase):
    def test_list_all_includes_dissolved(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Alive", state="active", founded_at=200.0)
        self.db.add_city(2, "Dead", state="dissolved", founded_at=100.0)
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "list all")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("Alive", joined)
        self.assertIn("Dead", joined)


# ═════════════════════════════════════════════════════════════════════
# 36. TestParserInspectHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserInspectHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_inspect_renders(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Foo", state="active", hq_tier="fortress",
                         tax_rate=0.05)
        self.db.add_char(10, "Founder")
        self.db.add_char(11, "Mayor")
        self.db.cities[1]["founder_id"] = 10
        self.db.cities[1]["mayor_id"] = 11
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "inspect Foo")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("Foo", joined)
        self.assertIn("fortress", joined)
        self.assertIn("5.0%", joined)
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 37. TestParserInspectMissingName
# ═════════════════════════════════════════════════════════════════════

class TestParserInspectMissingName(_PCNamedDBMixin, unittest.TestCase):
    def test_no_name_error(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "inspect")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("missing city name", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 38. TestParserInspectUnknown
# ═════════════════════════════════════════════════════════════════════

class TestParserInspectUnknown(_PCNamedDBMixin, unittest.TestCase):
    def test_unknown_city_error(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "inspect Nope")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("no active city", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 39. TestParserVoidBanishHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserVoidBanishHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_void_banish_lifts_and_acks(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Foo", state="active")
        self.db.add_char(50, "Banned")
        self.db.add_banishment(1, 50)
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "void-banish Foo = Banned")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        # Some success message
        self.assertIn("Banned", joined)
        self.assertIn("Foo", joined)
        # Banishment gone
        self.assertNotIn((1, 50), self.db.banishments)
        # Mutation log records the delete
        del_writes = [w for w in self.db.writes
                      if w[0] == "delete_banishment"]
        self.assertEqual(len(del_writes), 1)


# ═════════════════════════════════════════════════════════════════════
# 40. TestParserVoidBanishMissingEquals
# ═════════════════════════════════════════════════════════════════════

class TestParserVoidBanishMissingEquals(_PCNamedDBMixin, unittest.TestCase):
    def test_no_equals_error(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "void-banish Foo Bar")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 41. TestParserVoidBanishMissingParts
# ═════════════════════════════════════════════════════════════════════

class TestParserVoidBanishMissingParts(_PCNamedDBMixin, unittest.TestCase):
    def test_empty_left(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "void-banish = Bar")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])

    def test_empty_right(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "void-banish Foo =")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 42. TestParserSetRateCapHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserSetRateCapHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_writes_cap(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Foo", tax_rate=0.02, rate_cap=0.05)
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "set-rate-cap Foo = 8%")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("8.0%", joined)
        # Updated to 0.08 (no clamp; tax was 0.02)
        cap_writes = [w for w in self.db.writes
                      if w[0] == "update_rate_cap"]
        self.assertEqual(len(cap_writes), 1)
        self.assertAlmostEqual(cap_writes[0][2], 0.08)


# ═════════════════════════════════════════════════════════════════════
# 43. TestParserSetRateCapPercentForms
# ═════════════════════════════════════════════════════════════════════

class TestParserSetRateCapPercentForms(_PCNamedDBMixin, unittest.TestCase):
    def test_5_5pct_005_all_same(self):
        from parser.admin_city_commands import AdminCityCommand
        for form in ("5", "5%", "0.05"):
            self.db = _FakeDB()
            self._orig_gcbn_inner = _install_fake_get_city_by_name(self.db)
            try:
                self.db.add_city(1, "Foo", tax_rate=0.0, rate_cap=0.10)
                cmd = AdminCityCommand()
                ctx = _make_ctx(self.db, f"set-rate-cap Foo = {form}")
                _run(cmd.execute(ctx))
                cap_writes = [w for w in self.db.writes
                              if w[0] == "update_rate_cap"]
                self.assertEqual(
                    len(cap_writes), 1,
                    f"form={form!r}: expected exactly one cap write")
                self.assertAlmostEqual(
                    cap_writes[0][2], 0.05,
                    msg=f"form={form!r} → expected 0.05")
            finally:
                _restore_get_city_by_name(self._orig_gcbn_inner)


# ═════════════════════════════════════════════════════════════════════
# 44. TestParserSetRateCapBadValue
# ═════════════════════════════════════════════════════════════════════

class TestParserSetRateCapBadValue(_PCNamedDBMixin, unittest.TestCase):
    def test_garbage_pct_no_write(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Foo")
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "set-rate-cap Foo = abc")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("invalid percentage", joined.lower())
        # No write
        self.assertEqual([w for w in self.db.writes
                          if w[0].startswith("update_")], [])


# ═════════════════════════════════════════════════════════════════════
# 45. TestParserSetRateCapMissingParts
# ═════════════════════════════════════════════════════════════════════

class TestParserSetRateCapMissingParts(_PCNamedDBMixin, unittest.TestCase):
    def test_no_equals(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "set-rate-cap Foo")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 46. TestParserDissolveHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserDissolveHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_dissolve_writes_cascade(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "Foo", state="active")
        self.db.add_city_room(1, 100, is_center=1)
        self.db.add_banishment(1, 50)
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "dissolve Foo")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("force-dissolved", joined.lower())
        # All four ops happened
        ops = [w[0] for w in self.db.writes]
        self.assertIn("delete_city_rooms", ops)
        self.assertIn("delete_city_banishments", ops)
        self.assertIn("delete_city_guests", ops)
        self.assertIn("update_state_dissolved", ops)
        # No refund
        treasury = [w for w in self.db.writes
                    if w[0] == "adjust_org_treasury"]
        self.assertEqual(treasury, [])


# ═════════════════════════════════════════════════════════════════════
# 47. TestParserDissolveMissingName
# ═════════════════════════════════════════════════════════════════════

class TestParserDissolveMissingName(_PCNamedDBMixin, unittest.TestCase):
    def test_no_name(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "dissolve")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("missing city name", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 48. TestParserRenameHappy
# ═════════════════════════════════════════════════════════════════════

class TestParserRenameHappy(_PCNamedDBMixin, unittest.TestCase):
    def test_rename_writes(self):
        from parser.admin_city_commands import AdminCityCommand
        self.db.add_city(1, "OldName", state="active")
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "rename OldName = NewName")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("NewName", joined)
        # Row updated
        self.assertEqual(self.db.cities[1]["name"], "NewName")
        # Single update_name write
        renames = [w for w in self.db.writes if w[0] == "update_name"]
        self.assertEqual(len(renames), 1)


# ═════════════════════════════════════════════════════════════════════
# 49. TestParserRenameMissingParts
# ═════════════════════════════════════════════════════════════════════

class TestParserRenameMissingParts(_PCNamedDBMixin, unittest.TestCase):
    def test_no_equals(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "rename Foo")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])

    def test_empty_left(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        ctx = _make_ctx(self.db, "rename = NewName")
        _run(cmd.execute(ctx))
        joined = "\n".join(ctx.session.sent)
        self.assertIn("usage", joined.lower())
        self.assertEqual(self.db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 50. TestParserAdminNameResolution
# ═════════════════════════════════════════════════════════════════════

class TestParserAdminNameResolution(_PCNamedDBMixin, unittest.TestCase):
    def test_char_name_preferred(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        sess = _FakeSession()
        sess.character = {"id": 99, "name": "GMAlice"}
        ctx = _make_ctx(self.db, "", session=sess)
        # Use the private resolver
        name = cmd._admin_name(ctx)
        self.assertEqual(name, "GMAlice")

    def test_account_fallback(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        sess = _FakeSession()
        acct = MagicMock()
        acct.name = "admin_acct"
        sess.account = acct
        sess.character = None
        ctx = _make_ctx(self.db, "", session=sess)
        name = cmd._admin_name(ctx)
        self.assertEqual(name, "admin_acct")

    def test_default_admin(self):
        from parser.admin_city_commands import AdminCityCommand
        cmd = AdminCityCommand()
        sess = _FakeSession()  # no char, no account
        ctx = _make_ctx(self.db, "", session=sess)
        name = cmd._admin_name(ctx)
        self.assertEqual(name, "admin")


if __name__ == "__main__":
    unittest.main()
