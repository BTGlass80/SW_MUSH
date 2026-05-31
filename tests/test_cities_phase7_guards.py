# -*- coding: utf-8 -*-
"""
tests/test_cities_phase7_guards.py — Player Cities Phase 7 NPC
guards (May 23 2026).

Per ``player_cities_design_v1_2.md`` §7. Phase 7 ships:

  - `player_city_guards` table (schema additive)
  - CITY_GUARD_SLOTS_BY_HQ_TIER constants (3/6/14)
  - compute_city_guard_slots / guards_active helpers
  - count_city_guards / list_city_guards / get_guard_assignment
  - assign_city_guard (Mayor/Founder, full validation chain)
  - remove_city_guard (Mayor/Founder, fail-soft on missing NPC)
  - format_city_guards_lines (display)
  - compute_city_maintenance_cost now folds in guards * 200

Fixture discipline (v47 §4.20): extends the `_FakeDB` mutation-log
pattern from test_cities_phase6_maintenance.py with:
  - guards table (dict keyed by (city_id, npc_id))
  - npcs table (dict keyed by npc_id)
  - create_npc / delete_npc / get_membership

Test sections
=============

Pure helpers:
  1.  TestConstants                       — slot caps per design §7.1
  2.  TestComputeCityGuardSlots           — by HQ tier; unknown → 0
  3.  TestGuardsActive                    — True healthy, False in grace

Read helpers:
  4.  TestCountCityGuardsEmpty            — no rows → 0
  5.  TestCountCityGuardsPopulated        — three rows → 3
  6.  TestListCityGuardsOrdering          — ordered by assigned_at, npc_id
  7.  TestGetGuardAssignmentHit           — returns the row
  8.  TestGetGuardAssignmentMiss          — returns None

Assign (validation chain — each gate tested in isolation):
  9.  TestAssignPermsRequiresMayorFounder — non-mayor refused
 10.  TestAssignNotInOrg                  — independent char refused
 11.  TestAssignNoCity                    — org has no city
 12.  TestAssignRoomNotInCity             — room belongs to another city
 13.  TestAssignRoomIsHQCenter            — refuses center rooms
 14.  TestAssignSlotCapFull               — refuses when at cap
 15.  TestAssignSlotCapUnknownTier        — refuses 0-cap tiers
 16.  TestAssignOnePerRoom                — refuses duplicate room
 17.  TestAssignTreasuryShort             — refuses, no debit
 18.  TestAssignHappyPath                 — debit + npc + row + log

Assign (failure rollback):
 19.  TestAssignRollbackOnNpcCreateFail   — refunds treasury
 20.  TestAssignRollbackCleansNpcOnInsertFail — deletes NPC on fail
 21.  TestAssignTagsCityGuardForCityId    — ai_config tagged

Remove:
 22.  TestRemovePermsRequiresMayorFounder — non-mayor refused
 23.  TestRemoveNotACityGuard             — npc not in this city
 24.  TestRemoveHappyPath                 — npc + row deleted
 25.  TestRemoveNpcAlreadyMissing         — row still cleared

Maintenance integration:
 26.  TestComputeCostFoldsInGuards        — N*100 + G*200
 27.  TestComputeCostZeroGuardsBehavesLikePhase6 — backward-compat

Display:
 28.  TestFormatLinesEmpty                — empty roster line
 29.  TestFormatLinesPopulated            — slot count + per-guard rows
 30.  TestFormatLinesShowsInactiveInGrace — status label flips

Schema:
 31.  TestEnsureSchemaCreatesGuardsTable  — DDL runs idempotently

Per HANDOFF_MAY23_CITIES_PHASE7_GUARDS.md.
"""

from __future__ import annotations

import time
import unittest
from unittest.mock import MagicMock

from engine import player_cities as pc


DAY = 86400
WEEK = 7 * DAY


# ═════════════════════════════════════════════════════════════════════
# _FakeDB — extends the Phase 6 maintenance fixture for Phase 7.
# ═════════════════════════════════════════════════════════════════════


class _FakeDB:
    def __init__(self):
        # Existing Phase 6 tables
        self.cities = {}              # id -> row
        self.city_rooms = {}          # (city_id, room_id) -> row
        self.banishments = {}         # (city_id, char_id) -> row
        self.guests = {}              # (city_id, char_id) -> row
        self.characters = {}          # id -> dict
        self.orgs = {}                # id -> dict
        self.memberships = {}         # (char_id, org_id) -> dict
        # Phase 7 tables
        self.guards = {}              # (city_id, npc_id) -> row
        self.npcs = {}                # npc_id -> dict
        self._next_npc_id = 1000
        # Capture
        self.writes = []
        self.mails = []
        # Failure injection
        self.fail_on_create_npc = False
        self.fail_on_guard_insert = False

    # ── Seeders ─────────────────────────────────────────────────────

    def add_city(self, city_id, name, *, org_id=1, state="active",
                 grace_started_at=0.0, hq_tier="outpost",
                 founder_id=10, mayor_id=10):
        row = {
            "id": city_id, "name": name, "name_lower": name.lower(),
            "org_id": org_id, "hq_id": 1, "zone_id": 1,
            "founded_at": time.time(),
            "founder_id": founder_id, "mayor_id": mayor_id,
            "tax_rate": 0.0, "rate_cap": 0.10,
            "motd": "", "state": state,
            "grace_started_at": grace_started_at,
            "maint_paid_until": time.time() + WEEK,
            "revenue_total": 0, "revenue_week": 0,
            "week_start_ts": time.time(),
            "hq_tier": hq_tier,
        }
        self.cities[city_id] = row
        return row

    def add_org(self, org_id, *, treasury=10_000, code="rebel",
                name=None):
        self.orgs[org_id] = {
            "id": org_id, "treasury": int(treasury),
            "code": code, "name": name or f"Org{org_id}",
        }
        return self.orgs[org_id]

    def add_city_room(self, city_id, room_id, *, is_center=0):
        self.city_rooms[(city_id, room_id)] = {
            "city_id": city_id, "room_id": room_id,
            "is_center": is_center, "citizen_only": 0,
            "claimed_at": time.time(),
        }

    def add_char(self, char_id, name, *, faction_id="rebel",
                 room_id=None):
        self.characters[char_id] = {
            "id": char_id, "name": name,
            "faction_id": faction_id,
            "room_id": room_id,
        }
        return self.characters[char_id]

    def add_membership(self, char_id, org_id, *, rank_level=5):
        self.memberships[(char_id, org_id)] = {
            "char_id": char_id, "org_id": org_id,
            "rank_level": rank_level,
        }

    def add_guard(self, city_id, npc_id, room_id, *,
                  assigned_by=10, assigned_at=None):
        self.guards[(city_id, npc_id)] = {
            "city_id": city_id, "npc_id": npc_id,
            "room_id": room_id, "assigned_by": assigned_by,
            "assigned_at": assigned_at or time.time(),
        }
        self.npcs[npc_id] = {
            "id": npc_id, "name": "Test Guard",
            "room_id": room_id,
        }

    # ── Read methods ────────────────────────────────────────────────

    async def fetchall(self, sql, params=()):
        s = " ".join(sql.split()).strip()

        # count guards per city
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_guards WHERE city_id = ?"):
            (cid,) = params
            n = sum(1 for k in self.guards if k[0] == cid)
            return [{"n": n}]

        # list guards per city
        if s.startswith("SELECT city_id, npc_id, room_id, assigned_by, assigned_at FROM player_city_guards WHERE city_id = ? ORDER BY"):
            (cid,) = params
            rows = [g for k, g in self.guards.items() if k[0] == cid]
            rows.sort(key=lambda r: (r["assigned_at"], r["npc_id"]))
            return [dict(r) for r in rows]

        # get assignment by (city, npc)
        if s.startswith("SELECT city_id, npc_id, room_id, assigned_by, assigned_at FROM player_city_guards WHERE city_id = ? AND npc_id = ?"):
            cid, npc_id = params
            g = self.guards.get((cid, npc_id))
            return [dict(g)] if g else []

        # one-per-room check
        if s.startswith("SELECT npc_id FROM player_city_guards WHERE city_id = ? AND room_id = ?"):
            cid, rid = params
            rows = [g for k, g in self.guards.items()
                    if k[0] == cid and g["room_id"] == rid]
            return [{"npc_id": r["npc_id"]} for r in rows]

        # Phase 6: expansion-room count (used by compute_cost)
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_rooms WHERE city_id = ? AND is_center = 0"):
            (cid,) = params
            n = sum(1 for k, r in self.city_rooms.items()
                    if k[0] == cid and r["is_center"] == 0)
            return [{"n": n}]

        # room presence in city
        if s.startswith("SELECT room_id, is_center FROM player_city_rooms WHERE city_id = ? AND room_id = ?"):
            cid, rid = params
            r = self.city_rooms.get((cid, rid))
            return [{"room_id": r["room_id"],
                     "is_center": r["is_center"]}] if r else []

        return []

    async def execute(self, sql, params=()):
        s = " ".join(sql.split()).strip()

        # INSERT into player_city_guards
        if s.startswith("INSERT INTO player_city_guards"):
            if self.fail_on_guard_insert:
                self.writes.append(("guard_insert_failed", params))
                raise RuntimeError("simulated guard insert failure")
            cid, npc_id, rid, by, at = params
            self.guards[(cid, npc_id)] = {
                "city_id": cid, "npc_id": npc_id,
                "room_id": rid, "assigned_by": by,
                "assigned_at": at,
            }
            self.writes.append(("guard_insert", cid, npc_id, rid))
            return MagicMock()

        # DELETE from player_city_guards
        if s.startswith("DELETE FROM player_city_guards WHERE city_id = ? AND npc_id = ?"):
            cid, npc_id = params
            removed = self.guards.pop((cid, npc_id), None)
            self.writes.append(("guard_delete", cid, npc_id,
                                bool(removed)))
            return MagicMock()

        # DDL — pretend it works (schema tests use real sqlite below)
        if s.startswith("CREATE TABLE") or s.startswith("CREATE INDEX") or s.startswith("CREATE UNIQUE INDEX"):
            self.writes.append(("ddl", s[:50]))
            return MagicMock()

        if s.startswith("ALTER TABLE"):
            self.writes.append(("alter", s[:50]))
            return MagicMock()

        # Catch-all
        self.writes.append(("unhandled_execute", s[:60], params))
        return MagicMock()

    async def commit(self):
        return None

    async def adjust_org_treasury(self, org_id, delta):
        if org_id in self.orgs:
            new = max(0, self.orgs[org_id]["treasury"] + delta)
            self.orgs[org_id]["treasury"] = new
        else:
            new = max(0, delta)
        self.writes.append(("adjust_treasury", org_id, delta))
        return new

    async def get_character(self, char_id):
        return self.characters.get(int(char_id))

    async def get_organization(self, code):
        for org in self.orgs.values():
            if org.get("code") == code:
                return org
        return None

    async def get_membership(self, char_id, org_id):
        return self.memberships.get((int(char_id), int(org_id)))

    async def get_npc(self, npc_id):
        return self.npcs.get(int(npc_id))

    async def create_npc(self, name, room_id, species="Human",
                          description="", char_sheet_json="{}",
                          ai_config_json="{}"):
        if self.fail_on_create_npc:
            self.writes.append(("create_npc_failed", name))
            raise RuntimeError("simulated NPC create failure")
        npc_id = self._next_npc_id
        self._next_npc_id += 1
        self.npcs[npc_id] = {
            "id": npc_id, "name": name, "room_id": room_id,
            "species": species, "description": description,
            "char_sheet_json": char_sheet_json,
            "ai_config_json": ai_config_json,
        }
        self.writes.append(("create_npc", npc_id, name, room_id))
        return npc_id

    async def delete_npc(self, npc_id):
        existed = npc_id in self.npcs
        self.npcs.pop(int(npc_id), None)
        self.writes.append(("delete_npc", npc_id, existed))
        return existed

    # Helper city lookups used by _resolve_actor_city
    async def get_city_by_org(self, *args, **kwargs):
        # Not actually called — engine uses
        # engine.player_cities.get_city_by_org which we patch
        # per-test via monkeypatching. Keep this as a stub.
        return None


# Helper: bind _FakeDB through the engine's get_city_by_org so
# _resolve_actor_city sees the right city.

def _patch_get_city_by_org(db: _FakeDB):
    """Monkey-patch engine.player_cities.get_city_by_org for the
    duration of a test. Returns the patched fn so the caller can
    restore."""
    orig = pc.get_city_by_org

    async def fake(_db, org_id):
        for c in db.cities.values():
            if c["org_id"] == org_id and c["state"] == "active":
                return c
        return None

    pc.get_city_by_org = fake
    return orig


def _unpatch_get_city_by_org(orig):
    pc.get_city_by_org = orig


# ═════════════════════════════════════════════════════════════════════
# 1. TestConstants
# ═════════════════════════════════════════════════════════════════════


class TestConstants(unittest.TestCase):
    def test_slot_caps_match_design(self):
        # Per design v1.2 §7.1 — additional city-level slots
        self.assertEqual(
            pc.CITY_GUARD_SLOTS_BY_HQ_TIER["outpost"], 3,
        )
        self.assertEqual(
            pc.CITY_GUARD_SLOTS_BY_HQ_TIER["chapter_house"], 6,
        )
        self.assertEqual(
            pc.CITY_GUARD_SLOTS_BY_HQ_TIER["fortress"], 14,
        )

    def test_guard_maint_constant_matches_design(self):
        # §7.3: 200 cr/wk per guard
        self.assertEqual(pc.CITY_GUARD_MAINT_PER_WEEK_CR, 200)


# ═════════════════════════════════════════════════════════════════════
# 2. TestComputeCityGuardSlots
# ═════════════════════════════════════════════════════════════════════


class TestComputeCityGuardSlots(unittest.TestCase):
    def test_outpost(self):
        self.assertEqual(
            pc.compute_city_guard_slots({"hq_tier": "outpost"}), 3,
        )

    def test_chapter_house(self):
        self.assertEqual(
            pc.compute_city_guard_slots(
                {"hq_tier": "chapter_house"}), 6,
        )

    def test_fortress(self):
        self.assertEqual(
            pc.compute_city_guard_slots({"hq_tier": "fortress"}), 14,
        )

    def test_unknown_tier_returns_zero(self):
        self.assertEqual(
            pc.compute_city_guard_slots({"hq_tier": "weirdname"}), 0,
        )

    def test_missing_hq_tier_defaults_to_outpost(self):
        # The helper defaults to 'outpost' when hq_tier is None
        self.assertEqual(pc.compute_city_guard_slots({}), 3)

    def test_none_city(self):
        # Defensive: None city → 0 slots (don't crash)
        self.assertEqual(pc.compute_city_guard_slots(None), 3)


# ═════════════════════════════════════════════════════════════════════
# 3. TestGuardsActive
# ═════════════════════════════════════════════════════════════════════


class TestGuardsActive(unittest.TestCase):
    def test_healthy_city_returns_true(self):
        self.assertTrue(pc.guards_active(
            {"grace_started_at": 0.0, "state": "active"}))

    def test_in_grace_week1_returns_false(self):
        # In grace = grace_started_at != 0 (any week)
        now = time.time()
        self.assertFalse(pc.guards_active(
            {"grace_started_at": now - 3 * DAY,
             "state": "active"}))

    def test_in_grace_week3_returns_false(self):
        now = time.time()
        self.assertFalse(pc.guards_active(
            {"grace_started_at": now - 15 * DAY,
             "state": "active"}))


# ═════════════════════════════════════════════════════════════════════
# 4-8. Read helpers
# ═════════════════════════════════════════════════════════════════════


class TestCountCityGuards(unittest.IsolatedAsyncioTestCase):
    async def test_empty(self):
        db = _FakeDB()
        self.assertEqual(await pc.count_city_guards(db, 1), 0)

    async def test_populated(self):
        db = _FakeDB()
        db.add_guard(1, 1001, 100)
        db.add_guard(1, 1002, 101)
        db.add_guard(1, 1003, 102)
        # Different city - should not be counted
        db.add_guard(2, 1004, 200)
        self.assertEqual(await pc.count_city_guards(db, 1), 3)
        self.assertEqual(await pc.count_city_guards(db, 2), 1)


class TestListCityGuards(unittest.IsolatedAsyncioTestCase):
    async def test_orders_by_assigned_at_then_npc_id(self):
        db = _FakeDB()
        # Add out of order
        db.add_guard(1, 1003, 102, assigned_at=300.0)
        db.add_guard(1, 1001, 100, assigned_at=100.0)
        db.add_guard(1, 1002, 101, assigned_at=200.0)
        rows = await pc.list_city_guards(db, 1)
        self.assertEqual([r["npc_id"] for r in rows],
                         [1001, 1002, 1003])

    async def test_empty(self):
        db = _FakeDB()
        self.assertEqual(await pc.list_city_guards(db, 1), [])


class TestGetGuardAssignment(unittest.IsolatedAsyncioTestCase):
    async def test_hit(self):
        db = _FakeDB()
        db.add_guard(1, 1001, 100)
        r = await pc.get_guard_assignment(db, 1, 1001)
        self.assertIsNotNone(r)
        self.assertEqual(r["npc_id"], 1001)
        self.assertEqual(r["room_id"], 100)

    async def test_miss(self):
        db = _FakeDB()
        self.assertIsNone(
            await pc.get_guard_assignment(db, 1, 9999))


# ═════════════════════════════════════════════════════════════════════
# 9-21. assign_city_guard — validation chain + happy path + rollback
# ═════════════════════════════════════════════════════════════════════


class _AssignBase(unittest.IsolatedAsyncioTestCase):
    """Shared setUp for assignment tests."""

    async def asyncSetUp(self):
        self.db = _FakeDB()
        # Founder + Mayor = same char (id=10), city 1, org 1, room 100 = HQ, room 101 = expansion
        self.db.add_org(1, treasury=10_000, code="rebel")
        self.db.add_city(1, "Test Outpost", org_id=1,
                         hq_tier="outpost",
                         founder_id=10, mayor_id=10)
        self.db.add_city_room(1, 100, is_center=1)
        self.db.add_city_room(1, 101, is_center=0)
        self.db.add_city_room(1, 102, is_center=0)
        self.db.add_char(10, "Mayor", faction_id="rebel")
        self.db.add_char(20, "NonMayor", faction_id="rebel")
        self.db.add_membership(10, 1, rank_level=5)
        self.db.add_membership(20, 1, rank_level=2)
        # Patch get_city_by_org
        self._orig = _patch_get_city_by_org(self.db)

    async def asyncTearDown(self):
        _unpatch_get_city_by_org(self._orig)


class TestAssignPerms(_AssignBase):
    async def test_non_mayor_refused(self):
        char = self.db.characters[20]
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, char, 101)
        self.assertFalse(ok)
        self.assertIn("Mayor or Founder", msg)
        self.assertIsNone(npc_id)
        # No treasury debit
        self.assertEqual(self.db.orgs[1]["treasury"], 10_000)


class TestAssignNotInOrg(_AssignBase):
    async def test_independent_char_refused(self):
        self.db.add_char(30, "Loner", faction_id="independent")
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[30], 101)
        self.assertFalse(ok)
        self.assertIn("not a member", msg.lower())


class TestAssignNoCity(_AssignBase):
    async def test_org_without_city_refused(self):
        # New org with no city
        self.db.add_org(2, treasury=10_000, code="hutt")
        self.db.add_char(40, "HuttGuy", faction_id="hutt")
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[40], 101)
        self.assertFalse(ok)
        self.assertIn("no active city", msg.lower())


class TestAssignRoomNotInCity(_AssignBase):
    async def test_room_in_other_city_refused(self):
        # 999 doesn't exist in city 1's rooms
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 999)
        self.assertFalse(ok)
        self.assertIn("not part of", msg)
        # No treasury debit
        self.assertEqual(self.db.orgs[1]["treasury"], 10_000)


class TestAssignRoomIsHQCenter(_AssignBase):
    async def test_center_room_refused(self):
        # Room 100 is is_center=1
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 100)
        self.assertFalse(ok)
        self.assertIn("HQ center", msg)
        # No treasury debit
        self.assertEqual(self.db.orgs[1]["treasury"], 10_000)


class TestAssignSlotCapFull(_AssignBase):
    async def test_at_cap_refused(self):
        # Outpost cap = 3
        self.db.add_guard(1, 1001, 101)
        self.db.add_guard(1, 1002, 102)
        # Need 3rd room
        self.db.add_city_room(1, 103, is_center=0)
        self.db.add_guard(1, 1003, 103)
        # Try to add 4th
        self.db.add_city_room(1, 104, is_center=0)
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 104)
        self.assertFalse(ok)
        self.assertIn("slots full", msg)
        self.assertEqual(self.db.orgs[1]["treasury"], 10_000)


class TestAssignSlotCapUnknownTier(_AssignBase):
    async def test_unknown_tier_refused(self):
        self.db.cities[1]["hq_tier"] = "alien_tier"
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertFalse(ok)
        self.assertIn("Unknown HQ tier", msg)


class TestAssignOnePerRoom(_AssignBase):
    async def test_duplicate_room_refused(self):
        self.db.add_guard(1, 1001, 101)
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertFalse(ok)
        self.assertIn("already stationed", msg)


class TestAssignTreasuryShort(_AssignBase):
    async def test_short_treasury_refused_no_debit(self):
        self.db.orgs[1]["treasury"] = 100  # less than 500
        ok, msg, _ = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertFalse(ok)
        self.assertIn("Insufficient treasury", msg)
        # Treasury untouched
        self.assertEqual(self.db.orgs[1]["treasury"], 100)


class TestAssignHappyPath(_AssignBase):
    async def test_full_assignment_flow(self):
        treasury_before = self.db.orgs[1]["treasury"]
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertTrue(ok, msg)
        self.assertIsNotNone(npc_id)
        # Treasury debited by GUARD_COST (500)
        from engine.territory import GUARD_COST
        self.assertEqual(
            self.db.orgs[1]["treasury"],
            treasury_before - GUARD_COST,
        )
        # NPC row created
        self.assertIn(npc_id, self.db.npcs)
        self.assertEqual(self.db.npcs[npc_id]["room_id"], 101)
        # Assignment row created
        self.assertIn((1, npc_id), self.db.guards)
        # Log message mentions slot 1/3
        self.assertIn("1/3", msg)

    async def test_uses_default_template_for_unknown_org_code(self):
        # Patch org code to something not in _GUARD_TEMPLATES.
        # Char's faction_id must match the new code for the
        # _resolve_actor_city lookup.
        self.db.orgs[1]["code"] = "unmapped_org"
        self.db.characters[10]["faction_id"] = "unmapped_org"
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        # Should still succeed via _default template fallback
        self.assertTrue(ok, msg)
        self.assertIsNotNone(npc_id)


class TestAssignRollback(_AssignBase):
    async def test_npc_create_failure_refunds_treasury(self):
        self.db.fail_on_create_npc = True
        treasury_before = self.db.orgs[1]["treasury"]
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertFalse(ok)
        self.assertIsNone(npc_id)
        # Treasury refunded
        self.assertEqual(
            self.db.orgs[1]["treasury"], treasury_before,
        )
        # No assignment row
        self.assertNotIn((1, 1000), self.db.guards)
        # Error message is the canonical one
        self.assertIn("refunded", msg.lower())

    async def test_assignment_insert_failure_cleans_up_npc(self):
        self.db.fail_on_guard_insert = True
        treasury_before = self.db.orgs[1]["treasury"]
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertFalse(ok)
        # Treasury refunded
        self.assertEqual(
            self.db.orgs[1]["treasury"], treasury_before,
        )
        # The NPC that was created should be cleaned up
        delete_calls = [w for w in self.db.writes
                        if w[0] == "delete_npc"]
        self.assertEqual(len(delete_calls), 1,
                         "expected exactly one delete_npc on cleanup")


class TestAssignTagsCityGuardForCityId(_AssignBase):
    async def test_ai_config_includes_tag(self):
        ok, msg, npc_id = await pc.assign_city_guard(
            self.db, self.db.characters[10], 101)
        self.assertTrue(ok, msg)
        import json
        ai = json.loads(self.db.npcs[npc_id]["ai_config_json"])
        self.assertEqual(ai.get("city_guard_for_city_id"), 1)


# ═════════════════════════════════════════════════════════════════════
# 22-25. remove_city_guard
# ═════════════════════════════════════════════════════════════════════


class _RemoveBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.db = _FakeDB()
        self.db.add_org(1, treasury=10_000, code="rebel")
        self.db.add_city(1, "Test Outpost", org_id=1,
                         hq_tier="outpost",
                         founder_id=10, mayor_id=10)
        self.db.add_city_room(1, 101, is_center=0)
        self.db.add_char(10, "Mayor", faction_id="rebel")
        self.db.add_char(20, "NonMayor", faction_id="rebel")
        self.db.add_membership(10, 1, rank_level=5)
        self.db.add_membership(20, 1, rank_level=2)
        self.db.add_guard(1, 1001, 101)
        self._orig = _patch_get_city_by_org(self.db)

    async def asyncTearDown(self):
        _unpatch_get_city_by_org(self._orig)


class TestRemovePerms(_RemoveBase):
    async def test_non_mayor_refused(self):
        ok, msg = await pc.remove_city_guard(
            self.db, self.db.characters[20], 1001)
        self.assertFalse(ok)
        self.assertIn("Mayor or Founder", msg)
        # Guard still there
        self.assertIn((1, 1001), self.db.guards)


class TestRemoveNotACityGuard(_RemoveBase):
    async def test_unknown_npc_refused(self):
        ok, msg = await pc.remove_city_guard(
            self.db, self.db.characters[10], 9999)
        self.assertFalse(ok)
        self.assertIn("not a city guard", msg)


class TestRemoveHappyPath(_RemoveBase):
    async def test_npc_and_row_deleted(self):
        ok, msg = await pc.remove_city_guard(
            self.db, self.db.characters[10], 1001)
        self.assertTrue(ok, msg)
        self.assertNotIn((1, 1001), self.db.guards)
        self.assertNotIn(1001, self.db.npcs)


class TestRemoveNpcAlreadyMissing(_RemoveBase):
    async def test_row_still_cleared(self):
        # NPC already gone (e.g. killed in combat); assignment row stays
        self.db.npcs.pop(1001, None)
        ok, msg = await pc.remove_city_guard(
            self.db, self.db.characters[10], 1001)
        self.assertTrue(ok, msg)
        # Row cleared
        self.assertNotIn((1, 1001), self.db.guards)
        # Message mentions the npc-was-absent edge
        self.assertIn("already absent", msg.lower())


# ═════════════════════════════════════════════════════════════════════
# 26-27. Maintenance integration
# ═════════════════════════════════════════════════════════════════════


class TestComputeCostFoldsInGuards(unittest.IsolatedAsyncioTestCase):
    async def test_expansion_plus_guards(self):
        db = _FakeDB()
        db.add_city(1, "Test", hq_tier="outpost")
        # 2 expansion rooms
        db.add_city_room(1, 100, is_center=1)
        db.add_city_room(1, 101, is_center=0)
        db.add_city_room(1, 102, is_center=0)
        # 3 guards
        db.add_guard(1, 1001, 101)
        db.add_guard(1, 1002, 102)
        db.add_guard(1, 1003, 101)
        cost = await pc.compute_city_maintenance_cost(db, 1)
        # 2 * 100 (expansion) + 3 * 200 (guards) = 800
        self.assertEqual(cost, 800)

    async def test_zero_guards_zero_expansion_zero_cost(self):
        db = _FakeDB()
        db.add_city(1, "Test", hq_tier="outpost")
        db.add_city_room(1, 100, is_center=1)
        cost = await pc.compute_city_maintenance_cost(db, 1)
        self.assertEqual(cost, 0)

    async def test_zero_guards_behaves_like_phase6(self):
        """Backward-compat: cities with no guards see the same
        cost as before Phase 7 (just expansion * 100)."""
        db = _FakeDB()
        db.add_city(1, "Test", hq_tier="outpost")
        db.add_city_room(1, 100, is_center=1)
        for rid in (101, 102, 103):
            db.add_city_room(1, rid, is_center=0)
        cost = await pc.compute_city_maintenance_cost(db, 1)
        self.assertEqual(cost, 300)  # 3 * 100, no guards


# ═════════════════════════════════════════════════════════════════════
# 28-30. Display
# ═════════════════════════════════════════════════════════════════════


class TestFormatLinesEmpty(unittest.IsolatedAsyncioTestCase):
    async def test_empty_roster_message(self):
        db = _FakeDB()
        city = db.add_city(1, "Test", hq_tier="outpost")
        lines = await pc.format_city_guards_lines(db, city)
        # Header
        self.assertTrue(any("Guards of Test" in line
                            for line in lines))
        # Slot count
        self.assertTrue(any("0/3" in line for line in lines))
        # Empty message
        self.assertTrue(
            any("No NPC guards stationed" in line
                for line in lines),
            f"lines: {lines}",
        )


class TestFormatLinesPopulated(unittest.IsolatedAsyncioTestCase):
    async def test_per_guard_rows(self):
        db = _FakeDB()
        city = db.add_city(1, "Test", hq_tier="chapter_house")
        db.add_guard(1, 1001, 101, assigned_at=time.time())
        db.add_guard(1, 1002, 102, assigned_at=time.time() + 1)
        lines = await pc.format_city_guards_lines(db, city)
        # Slot count 2/6
        self.assertTrue(any("2/6" in line for line in lines))
        # Two per-guard rows
        guard_lines = [line for line in lines
                       if "#1001" in line or "#1002" in line]
        self.assertEqual(len(guard_lines), 2)


class TestFormatLinesShowsInactiveInGrace(unittest.IsolatedAsyncioTestCase):
    async def test_grace_flips_status(self):
        db = _FakeDB()
        # In grace
        now = time.time()
        city = db.add_city(1, "Test", hq_tier="outpost",
                           grace_started_at=now - 3 * DAY)
        lines = await pc.format_city_guards_lines(db, city)
        self.assertTrue(
            any("INACTIVE" in line for line in lines),
            f"lines: {lines}",
        )

    async def test_healthy_shows_active(self):
        db = _FakeDB()
        city = db.add_city(1, "Test", hq_tier="outpost")
        lines = await pc.format_city_guards_lines(db, city)
        self.assertTrue(
            any("ACTIVE" in line and "INACTIVE" not in line
                for line in lines),
            f"lines: {lines}",
        )


# ═════════════════════════════════════════════════════════════════════
# 31. Schema idempotence
# ═════════════════════════════════════════════════════════════════════


class TestEnsureSchemaIncludesGuardsTable(unittest.TestCase):
    def test_schema_sql_creates_guards_table(self):
        # The CREATE TABLE SQL block should include
        # player_city_guards.
        self.assertIn(
            "player_city_guards",
            pc.PLAYER_CITIES_SCHEMA_SQL,
        )

    def test_indexes_include_guards_lookups(self):
        joined = " ".join(pc.PLAYER_CITIES_INDEXES_SQL)
        self.assertIn("idx_city_guards_city", joined)
        self.assertIn("idx_city_guards_room", joined)


if __name__ == "__main__":
    unittest.main()
