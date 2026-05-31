# -*- coding: utf-8 -*-
"""
tests/test_cities_phase6_maintenance.py — Player Cities Phase 6
weekly maintenance tick + 4-week grace state machine
(May 23 2026).

Per ``player_cities_design_v1_2.md`` §8.1 (maintenance costs) and
§8.2 (treasury depletion behavior). Implements the weekly tick
that:

  - Charges expansion-room maintenance (100 cr/room) from org
    treasury
  - Enters 4-week grace on shortfall (`grace_started_at` set)
  - Advances through stages: week1 (guards off — Phase 7),
    week2 (citizen-only flags cleared + locked), week3 (tax
    collection ceases), week4 (final warning), expired (auto
    dissolve)
  - Mails the Mayor + Founder on each grace transition
  - Recovers (clears grace, resumes paying) when treasury covers

Fixture discipline (per v47 §4.20): uses the `_FakeDB` with
mutation log pattern. The fake records every write call as a
tuple in `self.writes`.

Test sections
=============

Pure helpers (no DB):
  1.  TestConstants                       — thresholds match design §8.2
  2.  TestIsInGrace                       — derived from grace_started_at
  3.  TestGraceStageActive                — grace_started_at=0 → 'active'
  4.  TestGraceStageWeek1                 — t < 7d → 'week1'
  5.  TestGraceStageWeek2                 — 7d ≤ t < 14d → 'week2'
  6.  TestGraceStageWeek3                 — 14d ≤ t < 21d → 'week3'
  7.  TestGraceStageWeek4                 — 21d ≤ t < 28d → 'week4'
  8.  TestGraceStageExpired               — t ≥ 28d → 'expired'
  9.  TestGraceStageDissolved             — state='dissolved' overrides
 10.  TestIsTaxCollectionDisabled         — week3+ → True
 11.  TestIsCitizenFlaggingDisabled       — week2+ → True

Cost computation:
 12.  TestComputeCostNoExpansion          — only HQ rooms → 0
 13.  TestComputeCostOneExpansion         — 1 expansion → 100
 14.  TestComputeCostManyExpansion        — N expansion → N*100
 15.  TestComputeCostExcludesCenter       — HQ rooms not counted

Maintenance tick (happy paths):
 16.  TestTickPaysHealthyCity             — treasury covers → pay + bump
 17.  TestTickPaysClearsGraceFromPrior    — recovered: clear grace
 18.  TestTickSkipsNotDueYet              — maint_paid_until > now
 19.  TestTickSkipsDissolved              — state='dissolved'
 20.  TestTickZeroCostStillBumps          — 0-expansion city, no debit
                                            but bump still happens

Maintenance tick (entering grace):
 21.  TestTickEntersGraceOnShortfall      — treasury<cost → grace_started_at=now
 22.  TestTickEntryNoTreasuryDebit        — no debit when entering grace
 23.  TestTickEntryNoBump                 — maint_paid_until NOT bumped
                                            (so next tick re-checks)
 24.  TestTickEntryMailsMayorFounder      — both get mail

Maintenance tick (advancing grace):
 25.  TestTickAdvancesWeek1ToWeek2        — clears citizen flags + mails
 26.  TestTickAdvancesWeek2ToWeek3        — mails (no other side effect)
 27.  TestTickAdvancesWeek3ToWeek4        — mails (final warning)
 28.  TestTickSameStageNoMail             — second pass in week2, no mail
 29.  TestTickAdvancesExpired             — dissolves

Maintenance tick (dissolution from grace):
 30.  TestTickDissolutionCascades         — rooms/banishments/guests cleared
 31.  TestTickDissolutionMarksState       — state='dissolved' set
 32.  TestTickDissolutionMails            — mayor/founder notified
 33.  TestTickDissolutionDifferentDispatch — uses MAINT dissolve, not admin

Recovery:
 34.  TestTickRecoverySendsMail           — exit-grace mail
 35.  TestTickRecoveryResetsGraceStarted  — grace_started_at = 0
 36.  TestTickRecoveryAfterWeek2          — still recovers from late stages

Bulk clear:
 37.  TestBulkClearCitizenFlags           — flagged → cleared
 38.  TestBulkClearIdempotent             — zero flags → 0 cleared
 39.  TestBulkClearLeavesHQRooms          — is_center=1 not touched

Gating integration:
 40.  TestApplyCityTaxGatedInGraceWeek3   — short-circuits
 41.  TestApplyCityTaxNotGatedWeek1Week2  — still collects
 42.  TestSetCitizenOnlyGatedWeek2        — refuses to set flag
 43.  TestSetCitizenOnlyClearAllowedInGrace — clear path still works

Founding:
 44.  TestFoundCitySetsMaintPaidUntil     — new city gets +1 week

Summary counters:
 45.  TestTickSummaryAllCategories        — one tick can advance multiple
                                            cities through different paths

Mail helper:
 46.  TestNotifySingleRecipientWhenSame   — mayor==founder → 1 mail
 47.  TestNotifyMailFailureNonBlocking    — mail exception ignored
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# Constants we use everywhere
DAY = 86400
WEEK = 7 * DAY


# ═════════════════════════════════════════════════════════════════════
# _FakeDB — mutation-log pattern per v47 §4.20.
# Reused shape from test_cities_phase6_admin.py with extensions
# for the maintenance flow: org treasury reads, mail capture,
# city-rooms expansion count.
# ═════════════════════════════════════════════════════════════════════


class _FakeDB:
    def __init__(self):
        self.cities = {}                # id -> dict
        self.city_name_index = {}       # name_lower -> id (active)
        self.city_rooms = {}            # (city_id, room_id) -> row
        self.banishments = {}           # (city_id, char_id) -> row
        self.guests = {}                # (city_id, char_id) -> row
        self.characters = {}            # id -> dict
        self.orgs = {}                  # id -> dict {treasury: int}
        self.mails = []                 # captured (recipient_id, subject, body)
        self.writes = []
        self.raise_on_mail = False

    # ── Seeders ─────────────────────────────────────────────────────

    def add_city(self, city_id, name, *, org_id=1, state="active",
                 grace_started_at=0.0, maint_paid_until=0.0,
                 founded_at=None, hq_tier="outpost", tax_rate=0.0,
                 rate_cap=0.10, revenue_total=0, revenue_week=0,
                 founder_id=10, mayor_id=10, hq_id=1, zone_id=1,
                 motd="", week_start_ts=None):
        now = time.time()
        row = {
            "id": city_id, "name": name, "name_lower": name.lower(),
            "org_id": org_id, "hq_id": hq_id, "zone_id": zone_id,
            "is_wilderness": 0, "wilderness_region_id": None,
            "wilderness_x": None, "wilderness_y": None,
            "is_hidden": 0, "search_difficulty": 20,
            "visibility_factions": "[]",
            "founded_at": founded_at if founded_at is not None else now,
            "founder_id": founder_id, "mayor_id": mayor_id,
            "tax_rate": tax_rate, "rate_cap": rate_cap,
            "motd": motd, "state": state,
            "grace_started_at": grace_started_at,
            "maint_paid_until": maint_paid_until,
            "revenue_total": revenue_total,
            "revenue_week": revenue_week,
            "week_start_ts": week_start_ts if week_start_ts is not None else now,
            "hq_tier": hq_tier,
        }
        self.cities[city_id] = row
        if state != "dissolved":
            self.city_name_index[name.lower()] = city_id
        return row

    def add_org(self, org_id, *, treasury=0, code=None, name=None):
        self.orgs[org_id] = {
            "id": org_id, "treasury": int(treasury),
            "code": code or f"org_{org_id}",
            "name": name or f"Org{org_id}",
        }
        return self.orgs[org_id]

    def add_city_room(self, city_id, room_id, *, is_center=0,
                      citizen_only=0):
        self.city_rooms[(city_id, room_id)] = {
            "city_id": city_id, "room_id": room_id,
            "is_center": is_center, "citizen_only": citizen_only,
            "claimed_at": time.time(),
        }

    def add_char(self, char_id, name):
        self.characters[char_id] = {"id": char_id, "name": name}

    def add_banishment(self, city_id, char_id):
        self.banishments[(city_id, char_id)] = {
            "city_id": city_id, "char_id": char_id,
            "until": time.time() + 86400,
            "issued_by": 10, "issued_at": time.time(),
        }

    def add_guest(self, city_id, char_id):
        self.guests[(city_id, char_id)] = {
            "city_id": city_id, "char_id": char_id,
            "added_by": 10, "added_at": time.time(),
        }

    # ── Read methods ────────────────────────────────────────────────

    async def fetchall(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # Maintenance tick's main query
        if s.startswith("SELECT * FROM player_cities WHERE state != 'dissolved' AND maint_paid_until <= ?"):
            now = params[0]
            rows = [r for r in self.cities.values()
                    if r["state"] != "dissolved"
                    and r["maint_paid_until"] <= now]
            return [dict(r) for r in rows]
        # compute_city_maintenance_cost / cap query (non-HQ count)
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_rooms WHERE city_id = ? AND is_center = 0"):
            cid = params[0]
            n = sum(1 for k, r in self.city_rooms.items()
                    if k[0] == cid and r["is_center"] == 0)
            return [{"n": n}]
        # bulk_clear flag count (with citizen_only condition)
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_rooms WHERE city_id = ? AND citizen_only = 1 AND is_center = 0"):
            cid = params[0]
            n = sum(1 for k, r in self.city_rooms.items()
                    if k[0] == cid and r["citizen_only"] == 1
                    and r["is_center"] == 0)
            return [{"n": n}]
        # set_room_citizen_only's room-presence read
        if s.startswith("SELECT room_id, is_center FROM player_city_rooms WHERE city_id = ? AND room_id = ?"):
            cid, rid = params
            r = self.city_rooms.get((cid, rid))
            if r:
                return [{"room_id": r["room_id"], "is_center": r["is_center"]}]
            return []
        # _get_org_treasury
        if s.startswith("SELECT treasury FROM organizations WHERE id = ?"):
            (org_id,) = params
            org = self.orgs.get(org_id)
            return [{"treasury": org["treasury"]}] if org else []
        # Catch-all empty
        return []

    async def execute(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # tick: bump paid + clear grace
        if s.startswith("UPDATE player_cities SET maint_paid_until = ?, grace_started_at = 0 WHERE id = ?"):
            paid, cid = params
            if cid in self.cities:
                self.cities[cid]["maint_paid_until"] = paid
                self.cities[cid]["grace_started_at"] = 0
            self.writes.append(("paid_and_clear_grace", cid, paid))
            return MagicMock()
        # tick: enter grace (combined: grace_started + maint_paid bump)
        if s.startswith("UPDATE player_cities SET grace_started_at = ?, maint_paid_until = ? WHERE id = ?"):
            started, paid, cid = params
            if cid in self.cities:
                self.cities[cid]["grace_started_at"] = started
                self.cities[cid]["maint_paid_until"] = paid
            self.writes.append(("enter_grace_and_bump", cid, started, paid))
            return MagicMock()
        # tick: bump-only (advancing within grace)
        if s.startswith("UPDATE player_cities SET maint_paid_until = ? WHERE id = ?"):
            paid, cid = params
            if cid in self.cities:
                self.cities[cid]["maint_paid_until"] = paid
            self.writes.append(("bump_paid_only", cid, paid))
            return MagicMock()
        # tick: enter grace (legacy single-column path; kept for safety)
        if s.startswith("UPDATE player_cities SET grace_started_at = ? WHERE id = ?"):
            started, cid = params
            if cid in self.cities:
                self.cities[cid]["grace_started_at"] = started
            self.writes.append(("enter_grace", cid, started))
            return MagicMock()
        # tick: dissolve
        if s.startswith("UPDATE player_cities SET state = 'dissolved' WHERE id = ?"):
            (cid,) = params
            if cid in self.cities:
                old_lower = self.cities[cid]["name_lower"]
                self.cities[cid]["state"] = "dissolved"
                if self.city_name_index.get(old_lower) == cid:
                    del self.city_name_index[old_lower]
            self.writes.append(("dissolve", cid))
            return MagicMock()
        # delete_city_rooms
        if s.startswith("DELETE FROM player_city_rooms WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.city_rooms if k[0] == cid]
            for k in removed:
                del self.city_rooms[k]
            self.writes.append(("delete_city_rooms", cid, len(removed)))
            return MagicMock()
        # delete banishments
        if s.startswith("DELETE FROM player_city_banishments WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.banishments if k[0] == cid]
            for k in removed:
                del self.banishments[k]
            self.writes.append(("delete_banishments", cid, len(removed)))
            return MagicMock()
        # delete guests
        if s.startswith("DELETE FROM player_city_guests WHERE city_id = ?"):
            (cid,) = params
            removed = [k for k in self.guests if k[0] == cid]
            for k in removed:
                del self.guests[k]
            self.writes.append(("delete_guests", cid, len(removed)))
            return MagicMock()
        # bulk-clear citizen flags
        if s.startswith("UPDATE player_city_rooms SET citizen_only = 0 WHERE city_id = ? AND is_center = 0"):
            (cid,) = params
            cleared = 0
            for k, r in self.city_rooms.items():
                if k[0] == cid and r["is_center"] == 0 and r["citizen_only"] == 1:
                    r["citizen_only"] = 0
                    cleared += 1
            self.writes.append(("bulk_clear_flags", cid, cleared))
            return MagicMock()
        # single-room citizen_only update (from set_room_citizen_only)
        if s.startswith("UPDATE player_city_rooms SET citizen_only = ? WHERE city_id = ? AND room_id = ?"):
            flag_int, cid, rid = params
            if (cid, rid) in self.city_rooms:
                self.city_rooms[(cid, rid)]["citizen_only"] = flag_int
            self.writes.append(("set_citizen_only", cid, rid, flag_int))
            return MagicMock()
        # mail inserts
        if s.startswith("INSERT INTO mail "):
            sender_id, subject, body, sent_at = params
            # the send_system_mail flow does INSERT mail then INSERT mail_recipients
            self._pending_mail = (sender_id, subject, body)
            cursor = MagicMock()
            cursor.lastrowid = len(self.mails) + 1
            return cursor
        if s.startswith("INSERT INTO mail_recipients"):
            # SQL: VALUES (?, ?, 0, 0) — only mail_id + char_id are bound
            mail_id, char_id = params
            if hasattr(self, '_pending_mail'):
                sender_id, subject, body = self._pending_mail
                self.mails.append({
                    "recipient_id": char_id,
                    "subject": subject,
                    "body": body,
                    "sender_id": sender_id,
                })
                del self._pending_mail
            return MagicMock()
        # Catch-all
        self.writes.append(("unhandled_execute", s, params))
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


# ═════════════════════════════════════════════════════════════════════
# 1. TestConstants
# ═════════════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):
    def test_thresholds(self):
        from engine.player_cities import (
            CITY_GRACE_FLAGS_OFF_AT_SECONDS,
            CITY_GRACE_TAX_OFF_AT_SECONDS,
            CITY_GRACE_FINAL_WARNING_AT_SECONDS,
            CITY_GRACE_DISSOLVE_AT_SECONDS,
            CITY_EXPANSION_MAINT_PER_WEEK_CR,
            CITY_GUARD_MAINT_PER_WEEK_CR,
            ONE_WEEK_SECONDS,
            CITY_MAINTENANCE_TICK_INTERVAL_SECONDS,
        )
        self.assertEqual(CITY_GRACE_FLAGS_OFF_AT_SECONDS, 7 * 86400)
        self.assertEqual(CITY_GRACE_TAX_OFF_AT_SECONDS, 14 * 86400)
        self.assertEqual(CITY_GRACE_FINAL_WARNING_AT_SECONDS, 21 * 86400)
        self.assertEqual(CITY_GRACE_DISSOLVE_AT_SECONDS, 28 * 86400)
        # Design §8.1 numbers
        self.assertEqual(CITY_EXPANSION_MAINT_PER_WEEK_CR, 100)
        self.assertEqual(CITY_GUARD_MAINT_PER_WEEK_CR, 200)
        # Tick cadence
        self.assertEqual(ONE_WEEK_SECONDS, 7 * 86400)
        self.assertEqual(CITY_MAINTENANCE_TICK_INTERVAL_SECONDS,
                         7 * 86400)


# ═════════════════════════════════════════════════════════════════════
# 2. TestIsInGrace
# ═════════════════════════════════════════════════════════════════════

class TestIsInGrace(unittest.TestCase):
    def test_active_zero_started(self):
        from engine.player_cities import is_in_grace
        self.assertFalse(is_in_grace(
            {"state": "active", "grace_started_at": 0}))

    def test_active_with_started(self):
        from engine.player_cities import is_in_grace
        self.assertTrue(is_in_grace(
            {"state": "active", "grace_started_at": 1000.0}))

    def test_dissolved_never_in_grace(self):
        from engine.player_cities import is_in_grace
        self.assertFalse(is_in_grace(
            {"state": "dissolved", "grace_started_at": 1000.0}))

    def test_none_safely_false(self):
        from engine.player_cities import is_in_grace
        self.assertFalse(is_in_grace(None))
        self.assertFalse(is_in_grace({}))


# ═════════════════════════════════════════════════════════════════════
# 3-9. TestGraceStage*
# ═════════════════════════════════════════════════════════════════════

class TestGraceStageActive(unittest.TestCase):
    def test_no_grace_returns_active(self):
        from engine.player_cities import grace_stage
        c = {"state": "active", "grace_started_at": 0}
        self.assertEqual(grace_stage(c), "active")


class TestGraceStageWeek1(unittest.TestCase):
    def test_t_zero(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW), "week1")

    def test_just_before_week2_boundary(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 7 * DAY - 1), "week1")


class TestGraceStageWeek2(unittest.TestCase):
    def test_exactly_at_week2(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 7 * DAY), "week2")

    def test_mid_week2(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 10 * DAY), "week2")


class TestGraceStageWeek3(unittest.TestCase):
    def test_exactly_at_week3(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 14 * DAY), "week3")


class TestGraceStageWeek4(unittest.TestCase):
    def test_exactly_at_week4(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 21 * DAY), "week4")


class TestGraceStageExpired(unittest.TestCase):
    def test_at_28_days(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 28 * DAY), "expired")

    def test_well_past(self):
        from engine.player_cities import grace_stage
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertEqual(grace_stage(c, NOW + 100 * DAY), "expired")


class TestGraceStageDissolved(unittest.TestCase):
    def test_dissolved_overrides(self):
        from engine.player_cities import grace_stage
        c = {"state": "dissolved", "grace_started_at": 1000.0}
        self.assertEqual(grace_stage(c, 1_000_000.0), "dissolved")


# ═════════════════════════════════════════════════════════════════════
# 10. TestIsTaxCollectionDisabled
# ═════════════════════════════════════════════════════════════════════

class TestIsTaxCollectionDisabled(unittest.TestCase):
    def test_active_false(self):
        from engine.player_cities import is_tax_collection_disabled
        self.assertFalse(is_tax_collection_disabled(
            {"state": "active", "grace_started_at": 0}))

    def test_week1_2_false(self):
        from engine.player_cities import is_tax_collection_disabled
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertFalse(is_tax_collection_disabled(c, NOW))
        self.assertFalse(is_tax_collection_disabled(c, NOW + 7 * DAY))

    def test_week3_and_later_true(self):
        from engine.player_cities import is_tax_collection_disabled
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertTrue(is_tax_collection_disabled(c, NOW + 14 * DAY))
        self.assertTrue(is_tax_collection_disabled(c, NOW + 21 * DAY))
        self.assertTrue(is_tax_collection_disabled(c, NOW + 30 * DAY))


# ═════════════════════════════════════════════════════════════════════
# 11. TestIsCitizenFlaggingDisabled
# ═════════════════════════════════════════════════════════════════════

class TestIsCitizenFlaggingDisabled(unittest.TestCase):
    def test_active_false(self):
        from engine.player_cities import is_citizen_flagging_disabled
        self.assertFalse(is_citizen_flagging_disabled(
            {"state": "active", "grace_started_at": 0}))

    def test_week1_false(self):
        from engine.player_cities import is_citizen_flagging_disabled
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertFalse(is_citizen_flagging_disabled(c, NOW))

    def test_week2_and_later_true(self):
        from engine.player_cities import is_citizen_flagging_disabled
        NOW = 1_000_000.0
        c = {"state": "active", "grace_started_at": NOW}
        self.assertTrue(is_citizen_flagging_disabled(c, NOW + 7 * DAY))
        self.assertTrue(is_citizen_flagging_disabled(c, NOW + 14 * DAY))
        self.assertTrue(is_citizen_flagging_disabled(c, NOW + 30 * DAY))


# ═════════════════════════════════════════════════════════════════════
# 12-15. TestComputeCost
# ═════════════════════════════════════════════════════════════════════

class TestComputeCostNoExpansion(unittest.TestCase):
    def test_zero(self):
        from engine.player_cities import compute_city_maintenance_cost
        db = _FakeDB()
        cost = _run(compute_city_maintenance_cost(db, 1))
        self.assertEqual(cost, 0)


class TestComputeCostOneExpansion(unittest.TestCase):
    def test_100(self):
        from engine.player_cities import compute_city_maintenance_cost
        db = _FakeDB()
        db.add_city_room(1, 200, is_center=0)
        cost = _run(compute_city_maintenance_cost(db, 1))
        self.assertEqual(cost, 100)


class TestComputeCostManyExpansion(unittest.TestCase):
    def test_scales(self):
        from engine.player_cities import compute_city_maintenance_cost
        db = _FakeDB()
        for rid in range(200, 210):
            db.add_city_room(1, rid, is_center=0)
        cost = _run(compute_city_maintenance_cost(db, 1))
        self.assertEqual(cost, 1000)


class TestComputeCostExcludesCenter(unittest.TestCase):
    def test_hq_rooms_not_charged(self):
        from engine.player_cities import compute_city_maintenance_cost
        db = _FakeDB()
        # 4 HQ rooms (free), 3 expansion (300 cr)
        for rid in range(100, 104):
            db.add_city_room(1, rid, is_center=1)
        for rid in range(200, 203):
            db.add_city_room(1, rid, is_center=0)
        cost = _run(compute_city_maintenance_cost(db, 1))
        self.assertEqual(cost, 300)


# ═════════════════════════════════════════════════════════════════════
# 16. TestTickPaysHealthyCity
# ═════════════════════════════════════════════════════════════════════

class TestTickPaysHealthyCity(unittest.TestCase):
    def test_treasury_covers_so_pay(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=10_000)
        db.add_city(1, "Foo", org_id=1,
                    maint_paid_until=NOW - 100)
        for rid in range(200, 205):  # 5 expansion → 500 cr
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["paid"], 1)
        self.assertEqual(summary["entered_grace"], 0)
        # Treasury debited 500
        self.assertEqual(db.orgs[1]["treasury"], 9500)
        # adjust_treasury and paid_and_clear_grace both recorded
        ops = [w[0] for w in db.writes]
        self.assertIn("adjust_treasury", ops)
        self.assertIn("paid_and_clear_grace", ops)


# ═════════════════════════════════════════════════════════════════════
# 17. TestTickPaysClearsGraceFromPrior
# ═════════════════════════════════════════════════════════════════════

class TestTickPaysClearsGraceFromPrior(unittest.TestCase):
    def test_recovered_city_clears_grace_and_mails(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=10_000)
        # City was in grace stage week2 (entered 7 days ago)
        db.add_city(1, "Foo", org_id=1,
                    maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 7 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 203):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["paid"], 1)
        self.assertEqual(summary["recovered"], 1)
        # Grace cleared on the row
        self.assertEqual(db.cities[1]["grace_started_at"], 0)
        # Recovery mail sent to both mayor and founder
        self.assertEqual(len(db.mails), 2)
        recipients = {m["recipient_id"] for m in db.mails}
        self.assertEqual(recipients, {10, 11})
        for m in db.mails:
            self.assertIn("restored", m["subject"].lower())


# ═════════════════════════════════════════════════════════════════════
# 18. TestTickSkipsNotDueYet
# ═════════════════════════════════════════════════════════════════════

class TestTickSkipsNotDueYet(unittest.TestCase):
    def test_skip(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=10_000)
        # City's paid-until is in the future → skip
        db.add_city(1, "Foo", org_id=1,
                    maint_paid_until=NOW + 1000)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["checked"], 0)
        # No writes
        self.assertEqual(db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 19. TestTickSkipsDissolved
# ═════════════════════════════════════════════════════════════════════

class TestTickSkipsDissolved(unittest.TestCase):
    def test_dissolved_excluded(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=10_000)
        db.add_city(1, "Dead", state="dissolved", org_id=1,
                    maint_paid_until=NOW - 100)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["checked"], 0)
        self.assertEqual(db.writes, [])


# ═════════════════════════════════════════════════════════════════════
# 20. TestTickZeroCostStillBumps
# ═════════════════════════════════════════════════════════════════════

class TestTickZeroCostStillBumps(unittest.TestCase):
    def test_zero_expansion_no_debit_but_bump(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)  # zero treasury, but cost is 0 too
        db.add_city(1, "Foo", org_id=1,
                    maint_paid_until=NOW - 100)
        # No rooms → cost 0
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["paid"], 1)
        self.assertEqual(summary["entered_grace"], 0)
        # No debit happened
        self.assertEqual([w for w in db.writes
                          if w[0] == "adjust_treasury"], [])
        # But the paid bump did happen
        paid_writes = [w for w in db.writes
                       if w[0] == "paid_and_clear_grace"]
        self.assertEqual(len(paid_writes), 1)


# ═════════════════════════════════════════════════════════════════════
# 21. TestTickEntersGraceOnShortfall
# ═════════════════════════════════════════════════════════════════════

class TestTickEntersGraceOnShortfall(unittest.TestCase):
    def test_grace_started_at_set(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=50)  # < 500 cost
        db.add_city(1, "Foo", org_id=1,
                    maint_paid_until=NOW - 100,
                    grace_started_at=0)  # healthy → about to enter
        for rid in range(200, 205):  # 500 cr
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["entered_grace"], 1)
        self.assertEqual(summary["paid"], 0)
        # grace_started_at written ≈ now
        self.assertGreater(db.cities[1]["grace_started_at"], 0)


# ═════════════════════════════════════════════════════════════════════
# 22. TestTickEntryNoTreasuryDebit
# ═════════════════════════════════════════════════════════════════════

class TestTickEntryNoTreasuryDebit(unittest.TestCase):
    def test_no_debit_when_entering(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=50)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        # No adjust_treasury — the treasury can't cover, so we don't
        # debit (treasury is left as-is for the org to consume
        # elsewhere or refill)
        self.assertEqual([w for w in db.writes
                          if w[0] == "adjust_treasury"], [])
        self.assertEqual(db.orgs[1]["treasury"], 50)


# ═════════════════════════════════════════════════════════════════════
# 23. TestTickEntryBumpsMaintPaid
# ═════════════════════════════════════════════════════════════════════

class TestTickEntryBumpsMaintPaid(unittest.TestCase):
    def test_maint_paid_until_bumped_on_entry_for_idempotence(self):
        """Per the May 23 idempotence design: when a city enters
        grace, maint_paid_until is bumped by ONE_WEEK_SECONDS so
        that a duplicate tick within the week skips the city.
        The grace timer (grace_started_at) is independent of this
        bump."""
        from engine.player_cities import (
            tick_city_maintenance, ONE_WEEK_SECONDS,
        )
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=50)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        # The combined "enter_grace_and_bump" write fires (not the
        # legacy single-column path)
        ops = [w[0] for w in db.writes]
        self.assertIn("enter_grace_and_bump", ops)
        self.assertNotIn("paid_and_clear_grace", ops)
        # maint_paid_until bumped exactly one week from prior value
        expected = NOW - 100 + ONE_WEEK_SECONDS
        self.assertAlmostEqual(
            db.cities[1]["maint_paid_until"], expected, places=2,
        )

    def test_duplicate_tick_within_week_is_idempotent(self):
        """Running the tick twice without time advancing should
        NOT enter grace twice / send mail twice."""
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=50)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    mayor_id=10)
        db.add_char(10, "Mayor")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        # First tick → enters grace, sends 1 shortfall mail
        _run(tick_city_maintenance(db))
        self.assertEqual(len(db.mails), 1)
        # Second tick at same NOW → city's maint_paid_until is now
        # in the future → not selected by the main query → no work.
        _run(tick_city_maintenance(db))
        self.assertEqual(len(db.mails), 1)  # still just 1


# ═════════════════════════════════════════════════════════════════════
# 24. TestTickEntryMailsMayorFounder
# ═════════════════════════════════════════════════════════════════════

class TestTickEntryMailsMayorFounder(unittest.TestCase):
    def test_both_get_shortfall_mail(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=50)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        self.assertEqual(len(db.mails), 2)
        for m in db.mails:
            self.assertIn("shortfall", m["subject"].lower())
            self.assertIn("grace period", m["body"].lower())


# ═════════════════════════════════════════════════════════════════════
# 25. TestTickAdvancesWeek1ToWeek2
# ═════════════════════════════════════════════════════════════════════

class TestTickAdvancesWeek1ToWeek2(unittest.TestCase):
    def test_clears_flags_and_mails(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        # City in grace 7+ days now (week 2 boundary)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 8 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 205):
            db.add_city_room(1, rid, citizen_only=1)
        for rid in range(300, 302):
            db.add_city_room(1, rid, citizen_only=0)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["advanced_in_grace"], 1)
        # All 5 citizen flags cleared
        clear_writes = [w for w in db.writes
                        if w[0] == "bulk_clear_flags"]
        self.assertEqual(len(clear_writes), 1)
        # Mail sent with "week2" in subject or body
        self.assertEqual(len(db.mails), 2)
        for m in db.mails:
            self.assertIn("week2", m["subject"].lower())


# ═════════════════════════════════════════════════════════════════════
# 26. TestTickAdvancesWeek2ToWeek3
# ═════════════════════════════════════════════════════════════════════

class TestTickAdvancesWeek2ToWeek3(unittest.TestCase):
    def test_mails_only(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 15 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["advanced_in_grace"], 1)
        # No bulk clear (week2 transition already happened on prior tick)
        clear_writes = [w for w in db.writes
                        if w[0] == "bulk_clear_flags"]
        self.assertEqual(clear_writes, [])
        # Mail mentions week3 stage
        self.assertEqual(len(db.mails), 2)
        for m in db.mails:
            self.assertIn("week3", m["subject"].lower())


# ═════════════════════════════════════════════════════════════════════
# 27. TestTickAdvancesWeek3ToWeek4
# ═════════════════════════════════════════════════════════════════════

class TestTickAdvancesWeek3ToWeek4(unittest.TestCase):
    def test_final_warning(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 22 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["advanced_in_grace"], 1)
        # FINAL WARNING in body
        joined_bodies = "\n".join(m["body"] for m in db.mails)
        self.assertIn("FINAL", joined_bodies)


# ═════════════════════════════════════════════════════════════════════
# 28. TestTickSameStageNoMail
# ═════════════════════════════════════════════════════════════════════

class TestTickSameStageNoMail(unittest.TestCase):
    def test_duplicate_tick_skips_advanced_city(self):
        """When a tick advances a city through a stage, the city's
        maint_paid_until is bumped by one week so duplicate ticks
        within the week don't re-fire the advance. (The mechanism
        is the main query filter `maint_paid_until <= now`, not a
        per-stage notification flag.)"""
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        # Grace started 10 days ago → first tick sees prev=week1
        # (3d ago), cur=week2 (10d now) → advances.
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 10 * DAY,
                    mayor_id=10)
        db.add_char(10, "Mayor")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        # First tick advances (fires mail + bulk-clears flags)
        summary1 = _run(tick_city_maintenance(db))
        self.assertEqual(summary1["advanced_in_grace"], 1)
        first_mail_count = len(db.mails)
        self.assertGreater(first_mail_count, 0)
        # Second tick at same NOW: city's maint_paid_until is now
        # in the future → main query skips it → no work.
        summary2 = _run(tick_city_maintenance(db))
        self.assertEqual(summary2["checked"], 0)
        self.assertEqual(summary2["advanced_in_grace"], 0)
        # No new mail
        self.assertEqual(len(db.mails), first_mail_count)


# ═════════════════════════════════════════════════════════════════════
# 29. TestTickAdvancesExpired
# ═════════════════════════════════════════════════════════════════════

class TestTickAdvancesExpired(unittest.TestCase):
    def test_expired_dissolves(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 29 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["dissolved"], 1)
        self.assertEqual(db.cities[1]["state"], "dissolved")


# ═════════════════════════════════════════════════════════════════════
# 30. TestTickDissolutionCascades
# ═════════════════════════════════════════════════════════════════════

class TestTickDissolutionCascades(unittest.TestCase):
    def test_all_aux_tables_cleared(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 29 * DAY)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        db.add_banishment(1, 50)
        db.add_banishment(1, 51)
        db.add_guest(1, 52)
        _run(tick_city_maintenance(db))
        # All cleared
        self.assertEqual(len(db.city_rooms), 0)
        self.assertEqual(len(db.banishments), 0)
        self.assertEqual(len(db.guests), 0)


# ═════════════════════════════════════════════════════════════════════
# 31. TestTickDissolutionMarksState
# ═════════════════════════════════════════════════════════════════════

class TestTickDissolutionMarksState(unittest.TestCase):
    def test_state_dissolved(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 30 * DAY)
        # Need expansion rooms so cost > 0 (otherwise treasury=0 covers
        # cost=0 and the city would "pay" / recover instead of dissolve)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        self.assertEqual(db.cities[1]["state"], "dissolved")


# ═════════════════════════════════════════════════════════════════════
# 32. TestTickDissolutionMails
# ═════════════════════════════════════════════════════════════════════

class TestTickDissolutionMails(unittest.TestCase):
    def test_dissolution_notifies(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 30 * DAY,
                    mayor_id=10, founder_id=11)
        db.add_char(10, "Mayor")
        db.add_char(11, "Founder")
        # Cost > 0 to force the dissolve path
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        self.assertEqual(len(db.mails), 2)
        for m in db.mails:
            self.assertIn("dissolved", m["subject"].lower())


# ═════════════════════════════════════════════════════════════════════
# 33. TestTickDissolutionDifferentDispatch
# ═════════════════════════════════════════════════════════════════════

class TestTickDissolutionDifferentDispatch(unittest.TestCase):
    def test_no_treasury_refund(self):
        """Maintenance-driven dissolution does NOT refund (same as
        admin dissolve). The only treasury writes should be from
        the maintenance-payment path, which we're NOT taking here
        because treasury is 0."""
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=0)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 30 * DAY)
        # Cost > 0 → forced into shortfall + expired-dissolve path
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        treasury_writes = [w for w in db.writes
                           if w[0] == "adjust_treasury"]
        self.assertEqual(treasury_writes, [])


# ═════════════════════════════════════════════════════════════════════
# 34-36. Recovery
# ═════════════════════════════════════════════════════════════════════

class TestTickRecoverySendsMail(unittest.TestCase):
    def test_recovery_mail(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=5000)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 3 * DAY,
                    mayor_id=10)
        db.add_char(10, "Mayor")
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        self.assertEqual(len(db.mails), 1)
        self.assertIn("restored", db.mails[0]["subject"].lower())


class TestTickRecoveryResetsGraceStarted(unittest.TestCase):
    def test_grace_zeroed(self):
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=5000)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 5 * DAY)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        _run(tick_city_maintenance(db))
        self.assertEqual(db.cities[1]["grace_started_at"], 0)


class TestTickRecoveryAfterWeek2(unittest.TestCase):
    def test_recovers_from_week3(self):
        """Even at week3 (tax-off stage), a treasury refill still
        recovers the city."""
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        db.add_org(1, treasury=5000)
        db.add_city(1, "Foo", org_id=1, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 16 * DAY)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["recovered"], 1)
        self.assertEqual(db.cities[1]["grace_started_at"], 0)


# ═════════════════════════════════════════════════════════════════════
# 37-39. Bulk-clear citizen flags
# ═════════════════════════════════════════════════════════════════════

class TestBulkClearCitizenFlags(unittest.TestCase):
    def test_flagged_rooms_cleared(self):
        from engine.player_cities import _bulk_clear_citizen_flags
        db = _FakeDB()
        for rid in range(200, 205):
            db.add_city_room(1, rid, citizen_only=1)
        cleared = _run(_bulk_clear_citizen_flags(db, 1))
        self.assertEqual(cleared, 5)
        for k, r in db.city_rooms.items():
            self.assertEqual(r["citizen_only"], 0)


class TestBulkClearIdempotent(unittest.TestCase):
    def test_no_flags_zero_cleared(self):
        from engine.player_cities import _bulk_clear_citizen_flags
        db = _FakeDB()
        for rid in range(200, 205):
            db.add_city_room(1, rid, citizen_only=0)
        cleared = _run(_bulk_clear_citizen_flags(db, 1))
        self.assertEqual(cleared, 0)
        # No bulk-clear write (the COUNT(*)=0 short-circuits)
        clear_writes = [w for w in db.writes
                        if w[0] == "bulk_clear_flags"]
        self.assertEqual(clear_writes, [])


class TestBulkClearLeavesHQRooms(unittest.TestCase):
    def test_hq_centers_not_touched(self):
        from engine.player_cities import _bulk_clear_citizen_flags
        db = _FakeDB()
        # HQ rooms flagged (shouldn't be in real data, but defensive)
        for rid in range(100, 104):
            db.add_city_room(1, rid, is_center=1, citizen_only=1)
        # Expansion flagged
        for rid in range(200, 205):
            db.add_city_room(1, rid, is_center=0, citizen_only=1)
        cleared = _run(_bulk_clear_citizen_flags(db, 1))
        # Only expansion cleared
        self.assertEqual(cleared, 5)
        for rid in range(100, 104):
            self.assertEqual(db.city_rooms[(1, rid)]["citizen_only"], 1)
        for rid in range(200, 205):
            self.assertEqual(db.city_rooms[(1, rid)]["citizen_only"], 0)


# ═════════════════════════════════════════════════════════════════════
# 40-43. Gating integration
# ═════════════════════════════════════════════════════════════════════

class TestApplyCityTaxGatedInGraceWeek3(unittest.TestCase):
    def test_zero_take_when_gated(self):
        """When a city is in grace stage week3+, apply_city_tax
        short-circuits and returns 0 take."""
        from engine import player_cities as pc

        NOW = time.time()
        db = _FakeDB()
        db.add_org(1, treasury=10_000)
        city = db.add_city(1, "Foo", org_id=1, tax_rate=0.05,
                           grace_started_at=NOW - 15 * DAY)
        # Stub get_city_for_room to return this city
        async def fake_get_city_for_room(_db, _rid):
            return dict(city)
        original = pc.get_city_for_room
        pc.get_city_for_room = fake_get_city_for_room
        try:
            take, cid, name = _run(pc.apply_city_tax(db, 100, 1000))
            self.assertEqual(take, 0)
            # City attribution still preserved
            self.assertEqual(cid, 1)
            self.assertEqual(name, "Foo")
            # No treasury or revenue write
            self.assertEqual([w for w in db.writes
                              if w[0] == "adjust_treasury"], [])
        finally:
            pc.get_city_for_room = original


class TestApplyCityTaxNotGatedWeek1Week2(unittest.TestCase):
    def test_still_collects_in_week1(self):
        from engine import player_cities as pc

        NOW = time.time()
        db = _FakeDB()
        db.add_org(1, treasury=10_000)
        city = db.add_city(1, "Foo", org_id=1, tax_rate=0.05,
                           grace_started_at=NOW - 1 * DAY)  # week1
        async def fake_get_city_for_room(_db, _rid):
            return dict(city)
        original = pc.get_city_for_room
        pc.get_city_for_room = fake_get_city_for_room
        try:
            take, _, _ = _run(pc.apply_city_tax(db, 100, 1000))
            self.assertEqual(take, 50)  # 5% of 1000
        finally:
            pc.get_city_for_room = original

    def test_still_collects_in_week2(self):
        from engine import player_cities as pc

        NOW = time.time()
        db = _FakeDB()
        db.add_org(1, treasury=10_000)
        city = db.add_city(1, "Foo", org_id=1, tax_rate=0.05,
                           grace_started_at=NOW - 8 * DAY)  # week2
        async def fake_get_city_for_room(_db, _rid):
            return dict(city)
        original = pc.get_city_for_room
        pc.get_city_for_room = fake_get_city_for_room
        try:
            take, _, _ = _run(pc.apply_city_tax(db, 100, 1000))
            self.assertEqual(take, 50)  # still collects
        finally:
            pc.get_city_for_room = original


class TestSetCitizenOnlyGatedWeek2(unittest.TestCase):
    def test_set_flag_refused_in_week2(self):
        """In grace stage week2+, set_room_citizen_only(flag=True)
        is refused."""
        from engine import player_cities as pc

        NOW = time.time()
        db = _FakeDB()
        # Set up the actor-resolver path. Easier: stub _resolve_actor_city
        # to return our own org+city.
        city = db.add_city(1, "Foo", org_id=1,
                           grace_started_at=NOW - 8 * DAY,
                           mayor_id=10)
        char = {"id": 10, "name": "Mayor"}
        async def fake_resolve(_db, _char):
            return (
                {"id": 1, "name": "Org1"},  # org
                dict(city),                  # city (in week2 grace)
                None,                        # err
            )
        def fake_is_mof(*_a, **_k):
            return True
        original_resolve = pc._resolve_actor_city
        original_mof = pc._is_mayor_or_founder
        pc._resolve_actor_city = fake_resolve
        pc._is_mayor_or_founder = fake_is_mof
        # Seed the city-rooms read path
        db.add_city_room(1, 200, is_center=0)
        try:
            ok, msg = _run(pc.set_room_citizen_only(db, char, 200, True))
            self.assertFalse(ok)
            self.assertIn("grace", msg.lower())
        finally:
            pc._resolve_actor_city = original_resolve
            pc._is_mayor_or_founder = original_mof


class TestSetCitizenOnlyClearAllowedInGrace(unittest.TestCase):
    def test_clear_flag_works_in_grace(self):
        """Clearing the flag (flag=False) is always allowed, even
        in late grace stages."""
        from engine import player_cities as pc

        NOW = time.time()
        db = _FakeDB()
        city = db.add_city(1, "Foo", org_id=1,
                           grace_started_at=NOW - 8 * DAY)
        char = {"id": 10, "name": "Mayor"}
        async def fake_resolve(_db, _char):
            return (
                {"id": 1, "name": "Org1"}, dict(city), None,
            )
        def fake_is_mof(*_a, **_k):
            return True
        original_resolve = pc._resolve_actor_city
        original_mof = pc._is_mayor_or_founder
        pc._resolve_actor_city = fake_resolve
        pc._is_mayor_or_founder = fake_is_mof
        db.add_city_room(1, 200, is_center=0, citizen_only=1)
        try:
            ok, msg = _run(pc.set_room_citizen_only(db, char, 200, False))
            self.assertTrue(ok)
        finally:
            pc._resolve_actor_city = original_resolve
            pc._is_mayor_or_founder = original_mof


# ═════════════════════════════════════════════════════════════════════
# 44. TestFoundCitySetsMaintPaidUntil
# ═════════════════════════════════════════════════════════════════════

class TestFoundCitySetsMaintPaidUntil(unittest.TestCase):
    def test_via_sql_inspection(self):
        """Source-level check that the found_city INSERT mentions
        maint_paid_until. (Real end-to-end found_city covered by
        Phase 1 tests; this just guards against the additive
        column being dropped accidentally.)"""
        from pathlib import Path
        source = Path(PROJECT_ROOT, "engine", "player_cities.py").read_text(
            encoding="utf-8"
        )
        # The INSERT in found_city should include maint_paid_until
        # and pass now + ONE_WEEK_SECONDS
        # We look for the literal column name in the INSERT, plus
        # an inline reference to ONE_WEEK_SECONDS near the values.
        assert "maint_paid_until" in source
        assert "now + ONE_WEEK_SECONDS" in source


# ═════════════════════════════════════════════════════════════════════
# 45. TestTickSummaryAllCategories
# ═════════════════════════════════════════════════════════════════════

class TestTickSummaryAllCategories(unittest.TestCase):
    def test_multiple_paths_in_one_tick(self):
        """One tick pass can advance multiple cities through
        different code paths. Sanity: the summary counters
        accumulate correctly."""
        from engine.player_cities import tick_city_maintenance
        db = _FakeDB()
        NOW = time.time()
        # City 1: healthy, treasury covers → pay
        db.add_org(1, treasury=10_000)
        db.add_city(1, "Healthy", org_id=1, maint_paid_until=NOW - 100)
        for rid in range(200, 205):
            db.add_city_room(1, rid)
        # City 2: shortfall → enter grace
        db.add_org(2, treasury=50)
        db.add_city(2, "ShortNew", org_id=2, maint_paid_until=NOW - 100,
                    mayor_id=20)
        db.add_char(20, "M2")
        for rid in range(300, 305):
            db.add_city_room(2, rid)
        # City 3: in grace already, treasury refilled → recover
        db.add_org(3, treasury=5_000)
        db.add_city(3, "Recovered", org_id=3, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 3 * DAY, mayor_id=30)
        db.add_char(30, "M3")
        for rid in range(400, 405):
            db.add_city_room(3, rid)
        # City 4: in grace week3, treasury still empty → advance
        db.add_org(4, treasury=0)
        db.add_city(4, "Advancing", org_id=4, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 15 * DAY, mayor_id=40)
        db.add_char(40, "M4")
        for rid in range(500, 505):
            db.add_city_room(4, rid)
        # City 5: expired → dissolve
        db.add_org(5, treasury=0)
        db.add_city(5, "Dead", org_id=5, maint_paid_until=NOW - 100,
                    grace_started_at=NOW - 30 * DAY, mayor_id=50)
        db.add_char(50, "M5")
        for rid in range(600, 605):
            db.add_city_room(5, rid)

        summary = _run(tick_city_maintenance(db))
        self.assertEqual(summary["checked"], 5)
        self.assertEqual(summary["paid"], 2)         # Healthy + Recovered
        self.assertEqual(summary["entered_grace"], 1)  # ShortNew
        self.assertEqual(summary["advanced_in_grace"], 1)  # Advancing
        self.assertEqual(summary["recovered"], 1)    # Recovered
        self.assertEqual(summary["dissolved"], 1)    # Dead


# ═════════════════════════════════════════════════════════════════════
# 46. TestNotifySingleRecipientWhenSame
# ═════════════════════════════════════════════════════════════════════

class TestNotifySingleRecipientWhenSame(unittest.TestCase):
    def test_dedupe_when_mayor_is_founder(self):
        from engine.player_cities import _notify_mayor_and_founder
        db = _FakeDB()
        db.add_char(10, "Solo")
        city = {"id": 1, "name": "Foo", "mayor_id": 10, "founder_id": 10}
        _run(_notify_mayor_and_founder(
            db, city, subject="Test", body="Body",
        ))
        self.assertEqual(len(db.mails), 1)
        self.assertEqual(db.mails[0]["recipient_id"], 10)


# ═════════════════════════════════════════════════════════════════════
# 47. TestNotifyMailFailureNonBlocking
# ═════════════════════════════════════════════════════════════════════

class TestNotifyMailFailureNonBlocking(unittest.TestCase):
    def test_mail_exception_does_not_propagate(self):
        """If send_system_mail throws, _notify_mayor_and_founder
        must swallow it. Verified by monkey-patching mail_utils."""
        from engine import player_cities as pc
        from engine import mail_utils

        db = _FakeDB()
        async def boom(*_a, **_k):
            raise RuntimeError("mail server down")
        original = mail_utils.send_system_mail
        mail_utils.send_system_mail = boom
        try:
            city = {"id": 1, "name": "Foo",
                    "mayor_id": 10, "founder_id": 11}
            # Should not raise
            _run(pc._notify_mayor_and_founder(
                db, city, subject="x", body="y",
            ))
        finally:
            mail_utils.send_system_mail = original


if __name__ == "__main__":
    unittest.main()
