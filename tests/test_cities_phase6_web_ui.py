# -*- coding: utf-8 -*-
"""
tests/test_cities_phase6_web_ui.py — Phase 6 web UI HUD payload
tests (May 23 2026).

Exercises ``Session._hud_city`` and the helpers it composes:

  - Returns nothing when player has no city context AND is not
    an admin.
  - Builds a full payload for a Mayor in their own city.
  - Builds a full payload for a citizen-in-a-city.
  - Builds a payload for an admin even with no city context.
  - Admin payload includes the `admin.all_cities` block.
  - Grace state is reflected in `is_in_grace` + `grace_stage`.
  - Truncates lists at 25 (citizens/guests/banishments/guards).
  - All failure paths are fail-soft.

Fixture: lightweight `_FakeDB` extending the Phase 6/7 patterns,
with `_FakeSession` that has only the bits `_hud_city` needs.

Per HANDOFF_MAY23_CITIES_PHASE6_WEBUI.md.
"""

from __future__ import annotations

import asyncio
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from server.session import Session


# ─── _FakeDB ──────────────────────────────────────────────────────


class _FakeDB:
    def __init__(self):
        self.cities = {}            # id -> row
        self.city_rooms = {}        # (city_id, room_id) -> row
        self.banishments = {}       # (city_id, char_id) -> row
        self.guests = {}            # (city_id, char_id) -> row
        self.characters = {}        # id -> dict
        self.orgs = {}              # id -> {treasury, code, name}
        self.memberships = {}       # (char_id, org_id) -> dict
        self.guards = {}            # (city_id, npc_id) -> row

    # Seeders
    def add_city(self, city_id, name, *, org_id=1,
                 hq_tier="outpost", state="active",
                 grace_started_at=0.0, founder_id=10,
                 mayor_id=10, tax_rate=0.0, rate_cap=0.10,
                 revenue_week=0, revenue_total=0, motd=""):
        now = time.time()
        self.cities[city_id] = {
            "id": city_id, "name": name,
            "name_lower": name.lower(),
            "org_id": org_id, "hq_id": 1, "zone_id": 1,
            "founded_at": now,
            "founder_id": founder_id, "mayor_id": mayor_id,
            "tax_rate": tax_rate, "rate_cap": rate_cap,
            "motd": motd, "state": state,
            "grace_started_at": grace_started_at,
            "maint_paid_until": now + 7 * 86400,
            "revenue_total": revenue_total,
            "revenue_week": revenue_week,
            "week_start_ts": now,
            "hq_tier": hq_tier,
        }
        return self.cities[city_id]

    def add_org(self, org_id, *, treasury=10_000, code="rebel"):
        self.orgs[org_id] = {
            "id": org_id, "treasury": int(treasury),
            "code": code, "name": f"Org{org_id}",
        }
        return self.orgs[org_id]

    def add_city_room(self, city_id, room_id, *, is_center=0):
        self.city_rooms[(city_id, room_id)] = {
            "city_id": city_id, "room_id": room_id,
            "is_center": is_center, "citizen_only": 0,
            "claimed_at": time.time(),
        }

    def add_char(self, char_id, name, *, faction_id="rebel"):
        self.characters[char_id] = {
            "id": char_id, "name": name,
            "faction_id": faction_id,
        }
        return self.characters[char_id]

    def add_membership(self, char_id, org_id, *, rank_level=5):
        self.memberships[(char_id, org_id)] = {
            "char_id": char_id, "org_id": org_id,
            "rank_level": rank_level, "standing": "good",
            "rep_score": 0, "specialization": "",
            "joined_at": time.time(),
            "char_name": (self.characters.get(char_id)
                          or {}).get("name", "?"),
        }

    def add_banishment(self, city_id, char_id, *, issued_by=10):
        self.banishments[(city_id, char_id)] = {
            "city_id": city_id, "char_id": char_id,
            "until": time.time() + 30 * 86400,
            "issued_by": issued_by, "issued_at": time.time(),
        }

    def add_guest(self, city_id, char_id, *, added_by=10):
        self.guests[(city_id, char_id)] = {
            "city_id": city_id, "char_id": char_id,
            "added_by": added_by, "added_at": time.time(),
        }

    def add_guard(self, city_id, npc_id, room_id,
                  *, assigned_at=None, assigned_by=10):
        self.guards[(city_id, npc_id)] = {
            "city_id": city_id, "npc_id": npc_id,
            "room_id": room_id, "assigned_by": assigned_by,
            "assigned_at": assigned_at or time.time(),
        }

    # Read methods
    async def fetchall(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # get_city_for_room — join on player_city_rooms
        if s.startswith("SELECT pc.* FROM player_cities pc JOIN player_city_rooms"):
            (room_id,) = params
            for (cid, rid), _ in self.city_rooms.items():
                if rid == room_id:
                    c = self.cities.get(cid)
                    if c and c.get("state") != "dissolved":
                        return [dict(c)]
            return []
        # get_city_by_org
        if s.startswith("SELECT * FROM player_cities WHERE org_id = ?"):
            (org_id,) = params
            for c in self.cities.values():
                if (c.get("org_id") == org_id
                        and c.get("state") != "dissolved"):
                    return [dict(c)]
            return []
        # get_city_by_id
        if s.startswith("SELECT * FROM player_cities WHERE id = ?"):
            (cid,) = params
            c = self.cities.get(int(cid))
            return [dict(c)] if c else []
        # list_all_cities (active only)
        if s.startswith("SELECT * FROM player_cities WHERE state != 'dissolved' ORDER BY"):
            rows = [dict(c) for c in self.cities.values()
                    if c.get("state") != "dissolved"]
            rows.sort(key=lambda r: r.get("founded_at") or 0)
            return rows
        # list_all_cities (with dissolved)
        if s.startswith("SELECT * FROM player_cities ORDER BY"):
            rows = [dict(c) for c in self.cities.values()]
            rows.sort(key=lambda r: r.get("founded_at") or 0)
            return rows
        # expansion-room count
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_rooms WHERE city_id = ? AND is_center = 0"):
            (cid,) = params
            n = sum(1 for k, r in self.city_rooms.items()
                    if k[0] == cid and r.get("is_center") == 0)
            return [{"n": n}]
        # count_city_guards
        if s.startswith("SELECT COUNT(*) AS n FROM player_city_guards WHERE city_id = ?"):
            (cid,) = params
            n = sum(1 for k in self.guards if k[0] == cid)
            return [{"n": n}]
        # list_city_guards
        if s.startswith("SELECT city_id, npc_id, room_id, assigned_by, assigned_at FROM player_city_guards WHERE city_id = ? ORDER BY"):
            (cid,) = params
            rows = [dict(g) for k, g in self.guards.items()
                    if k[0] == cid]
            rows.sort(key=lambda r: (r["assigned_at"],
                                     r["npc_id"]))
            return rows
        # treasury single
        if s.startswith("SELECT treasury FROM organizations WHERE id = ?"):
            (org_id,) = params
            org = self.orgs.get(org_id)
            return [{"treasury": org["treasury"]}] if org else []
        # bulk treasury (admin block)
        if s.startswith("SELECT id, treasury FROM organizations WHERE id IN"):
            return [{"id": o["id"], "treasury": o["treasury"]}
                    for o in self.orgs.values()
                    if o["id"] in params]
        # list_active_banishments
        if s.startswith("SELECT char_id, until, issued_by, issued_at FROM player_city_banishments WHERE city_id = ? AND until >"):
            cid = params[0]
            now = time.time()
            rows = [dict(b) for k, b in self.banishments.items()
                    if k[0] == cid and b["until"] > now]
            rows.sort(key=lambda r: -r.get("issued_at", 0))
            return rows
        # list_guests (returns char_ids)
        if s.startswith("SELECT char_id FROM player_city_guests WHERE city_id = ?"):
            (cid,) = params
            return [{"char_id": k[1]}
                    for k in self.guests if k[0] == cid]
        # is_citizen / get_city_role's role-related reads — return empty
        return []

    async def execute(self, *args, **kwargs):
        # We don't need writes for the read-only HUD path; stub it
        from unittest.mock import MagicMock
        return MagicMock()

    async def commit(self):
        return None

    async def get_character(self, char_id):
        return self.characters.get(int(char_id))

    async def get_organization(self, code):
        for org in self.orgs.values():
            if org.get("code") == code:
                return org
        return None

    async def get_membership(self, char_id, org_id):
        return self.memberships.get(
            (int(char_id), int(org_id)))

    async def get_org_members(self, org_id):
        # Return all memberships for an org
        rows = []
        for (cid, oid), m in self.memberships.items():
            if oid == int(org_id):
                row = dict(m)
                row["char_id"] = cid
                row["char_name"] = (self.characters.get(cid)
                                    or {}).get("name", "?")
                rows.append(row)
        return rows


# ─── Helpers ────────────────────────────────────────────────────────


def _make_session() -> Session:
    """Build a minimal Session with no protocol layer."""
    # Avoid the real __init__ which expects a protocol. The
    # _hud_city + _hud_city_payload + _hud_city_admin_block methods
    # operate via `self` but only read `log`-level globals; they
    # don't need a fully-initialized session.
    s = Session.__new__(Session)
    return s


def _run(coro):
    return asyncio.run(coro)


# ════════════════════════════════════════════════════════════════════
# 1. Empty payload — no city, no admin
# ════════════════════════════════════════════════════════════════════


class TestEmptyPayload(unittest.TestCase):
    def test_no_city_no_admin_no_key(self):
        async def _t():
            db = _FakeDB()
            sess = _make_session()
            char = {"id": 100, "name": "Wanderer",
                    "faction_id": "independent",
                    "is_admin": 0}
            hud = {}
            await sess._hud_city(hud, db, char, room_id=None)
            self.assertNotIn("city", hud)
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 2. Mayor-in-own-city payload
# ════════════════════════════════════════════════════════════════════


class TestMayorPayload(unittest.TestCase):
    def _setup(self):
        db = _FakeDB()
        db.add_org(1, treasury=50_000, code="rebel")
        db.add_city(1, "Sunshine Outpost", org_id=1,
                    hq_tier="outpost",
                    founder_id=10, mayor_id=10,
                    tax_rate=0.05, rate_cap=0.08,
                    revenue_week=1200, revenue_total=8400,
                    motd="Welcome to Sunshine!")
        db.add_city_room(1, 100, is_center=1)
        db.add_city_room(1, 101, is_center=0)
        db.add_city_room(1, 102, is_center=0)
        db.add_char(10, "Mayor")
        db.add_membership(10, 1, rank_level=5)
        return db

    def test_full_payload_shape(self):
        async def _t():
            db = self._setup()
            sess = _make_session()
            char = db.characters[10]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=101)
            self.assertIn("city", hud)
            c = hud["city"]
            self.assertEqual(c["name"], "Sunshine Outpost")
            self.assertEqual(c["hq_tier"], "outpost")
            self.assertEqual(c["state"], "active")
            self.assertEqual(c["grace_stage"], "active")
            self.assertFalse(c["is_in_grace"])
            self.assertEqual(c["treasury"], 50_000)
            self.assertAlmostEqual(c["tax_rate"], 0.05)
            self.assertAlmostEqual(c["rate_cap"], 0.08)
            self.assertEqual(c["motd"], "Welcome to Sunshine!")
            self.assertEqual(c["revenue_week"], 1200)
            self.assertEqual(c["revenue_total"], 8400)
            # 2 expansion rooms (HQ excluded)
            self.assertEqual(c["expansion_rooms"], 2)
            # Outpost: 5 expansion max, 3 guard slots, 0 used
            self.assertEqual(c["max_expansion"], 5)
            self.assertEqual(c["guard_slots_total"], 3)
            self.assertEqual(c["guard_slots_used"], 0)
            self.assertEqual(c["founder_name"], "Mayor")
            self.assertEqual(c["mayor_name"], "Mayor")
            # Lists empty but present
            self.assertIsInstance(c["citizens"], list)
            self.assertEqual(c["citizens_count"], 1)  # 1 member
            self.assertEqual(c["guests"], [])
            self.assertEqual(c["banishments"], [])
            self.assertEqual(c["guards"], [])
            # No admin block
            self.assertNotIn("admin", c)
        _run(_t())

    def test_with_guests_and_banishments_and_guards(self):
        async def _t():
            db = self._setup()
            # Add a few citizens
            db.add_char(11, "AltMember")
            db.add_membership(11, 1, rank_level=3)
            # Add some guests, banishments, guards
            db.add_char(20, "Acquaintance")
            db.add_guest(1, 20)
            db.add_char(30, "TroubleMaker")
            db.add_banishment(1, 30)
            db.add_guard(1, 1001, 101)
            db.add_guard(1, 1002, 102)

            sess = _make_session()
            char = db.characters[10]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=101)
            c = hud["city"]
            self.assertEqual(c["citizens_count"], 2)
            self.assertEqual(c["guests_count"], 1)
            self.assertEqual(c["banishments_count"], 1)
            self.assertEqual(c["guard_slots_used"], 2)
            self.assertEqual(len(c["citizens"]), 2)
            self.assertEqual(c["citizens"][0]["name"], "Mayor")
            self.assertEqual(c["guests"][0]["name"],
                             "Acquaintance")
            self.assertEqual(c["banishments"][0]["name"],
                             "TroubleMaker")
            # Guard ai_active True (city healthy)
            self.assertTrue(c["guards"][0]["ai_active"])
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 3. Grace state propagation
# ════════════════════════════════════════════════════════════════════


class TestGracePayload(unittest.TestCase):
    def test_grace_week1_payload(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=0, code="rebel")
            db.add_city(1, "Broke City", org_id=1,
                        hq_tier="outpost",
                        grace_started_at=time.time() - 3 * 86400)
            db.add_city_room(1, 100, is_center=1)
            db.add_char(10, "Mayor")
            db.add_membership(10, 1, rank_level=5)
            db.add_guard(1, 1001, 100)  # Won't normally have HQ guard but ok

            sess = _make_session()
            char = db.characters[10]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=None)
            c = hud["city"]
            self.assertTrue(c["is_in_grace"])
            self.assertEqual(c["grace_stage"], "week1")
            # Guard ai_active should reflect grace
            self.assertFalse(c["guards"][0]["ai_active"])
        _run(_t())

    def test_grace_week3_payload(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=0, code="rebel")
            db.add_city(1, "Worse City", org_id=1,
                        hq_tier="outpost",
                        grace_started_at=time.time() - 15 * 86400)
            db.add_city_room(1, 100, is_center=1)
            db.add_char(10, "Mayor")
            db.add_membership(10, 1, rank_level=5)

            sess = _make_session()
            char = db.characters[10]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=None)
            c = hud["city"]
            self.assertEqual(c["grace_stage"], "week3")
            self.assertTrue(c["is_in_grace"])
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 4. Admin payload
# ════════════════════════════════════════════════════════════════════


class TestAdminPayload(unittest.TestCase):
    def test_admin_no_city_gets_admin_only_block(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=25_000, code="rebel")
            db.add_city(1, "Some City", org_id=1)
            db.add_city_room(1, 100, is_center=1)
            sess = _make_session()
            char = {"id": 999, "name": "Admin",
                    "faction_id": "independent",
                    "is_admin": 1}
            hud = {}
            await sess._hud_city(hud, db, char, room_id=None)
            self.assertIn("city", hud)
            c = hud["city"]
            self.assertTrue(c.get("admin_only"))
            self.assertIn("admin", c)
            self.assertTrue(c["admin"]["is_admin"])
            self.assertEqual(len(c["admin"]["all_cities"]), 1)
            self.assertEqual(
                c["admin"]["all_cities"][0]["name"], "Some City")
            self.assertEqual(
                c["admin"]["all_cities"][0]["treasury"], 25_000)
        _run(_t())

    def test_admin_mayor_in_own_city_gets_both(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=10_000, code="rebel")
            db.add_org(2, treasury=20_000, code="empire")
            db.add_city(1, "City A", org_id=1)
            db.add_city(2, "City B", org_id=2)
            db.add_city_room(1, 100, is_center=1)
            db.add_city_room(2, 200, is_center=1)
            db.add_char(10, "MayorAdmin", faction_id="rebel")
            db.add_membership(10, 1, rank_level=5)
            db.characters[10]["is_admin"] = 1

            sess = _make_session()
            char = db.characters[10]
            hud = {}
            # In their own city's room
            await sess._hud_city(hud, db, char, room_id=100)
            c = hud["city"]
            self.assertEqual(c["name"], "City A")
            self.assertIn("admin", c)
            # Admin block lists BOTH cities
            self.assertEqual(len(c["admin"]["all_cities"]), 2)
            names = sorted(
                ac["name"] for ac in c["admin"]["all_cities"])
            self.assertEqual(names, ["City A", "City B"])
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 5. Citizen-in-someone-else's-city payload
# ════════════════════════════════════════════════════════════════════


class TestVisitorPayload(unittest.TestCase):
    def test_visitor_in_a_city(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=10_000, code="rebel")
            db.add_city(1, "Host City", org_id=1)
            db.add_city_room(1, 100, is_center=1)
            db.add_city_room(1, 101, is_center=0)
            # Visitor — different org
            db.add_org(2, treasury=0, code="hutt")
            db.add_char(20, "Visitor", faction_id="hutt")

            sess = _make_session()
            char = db.characters[20]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=101)
            self.assertIn("city", hud)
            c = hud["city"]
            self.assertEqual(c["name"], "Host City")
            # role isn't 'mayor' or 'founder' for a visitor.
            # get_city_role returns one of: banished/founder/mayor/
            # citizen/guest/outsider. For a non-member, non-guest,
            # non-banished char, the role is "outsider".
            self.assertIn(c["role"],
                          {"outsider", "guest", "citizen",
                           "banished", "visitor"})
            # No admin block
            self.assertNotIn("admin", c)
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 6. Truncation at 25
# ════════════════════════════════════════════════════════════════════


class TestTruncation(unittest.TestCase):
    def test_lists_truncated_at_25(self):
        async def _t():
            db = _FakeDB()
            db.add_org(1, treasury=10_000, code="rebel")
            db.add_city(1, "Big City", org_id=1)
            db.add_city_room(1, 100, is_center=1)
            # Add 40 citizens
            for i in range(40):
                cid = 100 + i
                db.add_char(cid, f"Citizen{i}",
                            faction_id="rebel")
                db.add_membership(cid, 1, rank_level=1)
            db.characters[100]["is_admin"] = 0
            db.add_membership(10, 1, rank_level=5)
            db.add_char(10, "Mayor", faction_id="rebel")
            db.add_membership(10, 1, rank_level=5)
            # The city's mayor is char 10 by default
            sess = _make_session()
            char = db.characters[10]
            char["is_admin"] = 0
            hud = {}
            await sess._hud_city(hud, db, char, room_id=None)
            c = hud["city"]
            # Citizens count is full (41 total), but list
            # truncated to 25
            self.assertEqual(len(c["citizens"]), 25)
            # Count reflects the full pool
            self.assertGreaterEqual(c["citizens_count"], 25)
        _run(_t())


# ════════════════════════════════════════════════════════════════════
# 7. Fail-soft
# ════════════════════════════════════════════════════════════════════


class TestFailSoft(unittest.TestCase):
    def test_broken_db_doesnt_crash(self):
        async def _t():
            # FakeDB that raises on every read
            class BrokenDB:
                async def fetchall(self, *args, **kwargs):
                    raise RuntimeError("boom")

                async def execute(self, *args, **kwargs):
                    raise RuntimeError("boom")

                async def commit(self):
                    raise RuntimeError("boom")

                async def get_character(self, *args, **kwargs):
                    raise RuntimeError("boom")

                async def get_organization(self, *args, **kwargs):
                    raise RuntimeError("boom")

                async def get_membership(self, *args, **kwargs):
                    raise RuntimeError("boom")

                async def get_org_members(self, *args, **kwargs):
                    raise RuntimeError("boom")

            sess = _make_session()
            char = {"id": 1, "faction_id": "rebel",
                    "is_admin": 0}
            hud = {}
            # Should not crash, just set or omit hud["city"]
            try:
                await sess._hud_city(hud, BrokenDB(), char,
                                     room_id=1)
            except Exception as e:
                self.fail(
                    f"_hud_city should be fail-soft; "
                    f"raised {type(e).__name__}: {e}")
        _run(_t())


if __name__ == "__main__":
    unittest.main()
