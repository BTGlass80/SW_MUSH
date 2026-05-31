# -*- coding: utf-8 -*-
"""
tests/test_cities_phase3.py — Player Cities Phase 3 (May 22 2026).

Per ``player_cities_design_v1_2.md`` §13 Phase 3 (governance +
look-output) and the two May 22 design calls captured in the engine
module docstring (banishment anti-griefing rule, view-only guards).

Test sections
=============

  1.  TestPhase3Constants                  — banishment/motd/list constants
  2.  TestIsBanishedHelper                 — is_banished read path
  3.  TestIsGuestHelper                    — is_guest read path
  4.  TestGetCityRole                      — role resolution (6 outcomes)
  5.  TestListActiveCities                 — list_active_cities filter/sort
  6.  TestListCityRoomIds                  — list_city_room_ids ordering
  7.  TestListGuests                       — list_guests ordering
  8.  TestListActiveBanishments            — expired banishments excluded

  9.  TestAssignMayorFounderOnly           — non-founder rejected
 10.  TestAssignMayorTargetExists          — bogus char id rejected
 11.  TestAssignMayorTargetIsOrgMember     — non-member rejected
 12.  TestAssignMayorIdempotent            — re-assign same mayor no-op
 13.  TestAssignMayorHappyPath             — DB row updated

 14.  TestSetMotdMayorOrFounder            — outsider rejected
 15.  TestSetMotdLength                    — over-max rejected
 16.  TestSetMotdHappyPath                 — DB row updated
 17.  TestSetMotdClear                     — empty arg clears motd
 18.  TestSetMotdFounderAlso               — founder can set motd

 19.  TestAddGuestMayorOrFounder           — non-officer rejected
 20.  TestAddGuestTargetExists             — bogus char id rejected
 21.  TestAddGuestCitizenRejected          — citizen-as-guest rejected
 22.  TestAddGuestIdempotent               — duplicate add no-op
 23.  TestAddGuestHappyPath                — DB row inserted
 24.  TestRemoveGuestNotPresent            — not-on-list rejected
 25.  TestRemoveGuestHappyPath             — DB row deleted

 26.  TestBanishMayorOrFounder             — outsider rejected
 27.  TestBanishTargetExists               — bogus char id rejected
 28.  TestBanishSelfRejected               — banishing self rejected
 29.  TestBanishFounderRejected            — banishing the founder rejected
 30.  TestBanishRivalLeaderRejected        — rank-5 in another org rejected
 31.  TestBanishHappyPath                  — DB row inserted with until
 32.  TestBanishDropsFromGuestList         — banishment drops guest entry
 33.  TestBanishExtendsExisting            — re-banish replaces expiry
 34.  TestBanishZeroDurationRejected       — negative/zero duration rejected
 35.  TestUnbanishNotPresent               — no banishment rejected
 36.  TestUnbanishHappyPath                — DB row deleted

 37.  TestSetRoomCitizenOnlyAuth           — non-officer rejected
 38.  TestSetRoomCitizenOnlyRoomMembership — non-city-room rejected
 39.  TestSetRoomCitizenOnlyHappyOn        — flag set to 1
 40.  TestSetRoomCitizenOnlyHappyOff       — flag set back to 0

 41.  TestFormatCityHeaderTag              — bracket tag format
 42.  TestFormatCityInfoOutsider           — outsider view (count only)
 43.  TestFormatCityInfoCitizen            — citizen view (names list)
 44.  TestFormatCityInfoBanished           — banished view (short-circuit)

 45.  TestParserInfoNoCity                 — no-city path
 46.  TestParserInfoInCity                 — in-city happy path
 47.  TestParserMapInCity                  — map renders rooms
 48.  TestParserCitizensInCity             — citizens lists members + guests
 49.  TestParserList                       — list command echoes city name
 50.  TestParserMotdHappyPath              — engine reached
 51.  TestParserMotdNoArgs                 — empty arg clears motd (engine path)
 52.  TestParserMayorNoArgs                — usage echoed
 53.  TestParserMayorBadName               — not-found echoed
 54.  TestParserGuardsInCity               — guards renders empty stub
 55.  TestParserGuestAddHappyPath          — guest added by parser
 56.  TestParserGuestRemoveHappyPath       — guest removed by parser
 57.  TestParserGuestBadAction             — invalid action surfaced
 58.  TestParserBanishHappyPath            — banishment via parser
 59.  TestParserUnbanishHappyPath          — unbanishment via parser
 60.  TestParserCitizenroomOnHappyPath     — flag set via parser
 61.  TestParserCitizenroomBadFlag         — bad flag token rejected

 62.  TestPhase3NotInPlaceholderList       — info/motd/etc. live in dispatch
 63.  TestPhase4TaxStillPlaceholder        — tax/home still placeholders
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures (parallel to Phase 1/2) ─────────────────────────────


async def _fresh_db():
    from db.database import Database
    from engine.housing import ensure_schema as _hs_schema
    from engine.territory import ensure_territory_schema
    from engine.player_cities import ensure_schema as _pc_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _hs_schema(db)
    await ensure_territory_schema(db)
    await _pc_schema(db)
    return db


async def _seed_account(db):
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(username, password_hash, email) "
        "VALUES ('test', 'hash', 't@e.com')"
    )
    await db._db.commit()


async def _seed_room(db, zone_id: int, name: str = "Room") -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
        "VALUES (?, ?, '', '')",
        (name, zone_id),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_exit(
    db, from_room: int, to_room: int, direction: str = "north",
) -> int:
    cur = await db._db.execute(
        "INSERT INTO exits (from_room_id, to_room_id, direction, name) "
        "VALUES (?, ?, ?, ?)",
        (from_room, to_room, direction, direction.title()),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_zone(db, name: str, security: str | None) -> int:
    if security is None:
        props = "{}"
    else:
        props = json.dumps({"security": security})
    cur = await db._db.execute(
        "INSERT INTO zones (name, properties) VALUES (?, ?)",
        (name, props),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_char(
    db, name: str, faction_id: str = "", room_id: int | None = None,
) -> dict:
    await _seed_account(db)
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(account_id, name, species, room_id, credits, faction_id) "
        "VALUES (1, ?, 'Human', ?, 100000, ?)",
        (name, room_id or 1, faction_id),
    )
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


async def _seed_org(
    db, code: str, name: str, treasury: int = 0,
) -> dict:
    await db._db.execute(
        "INSERT INTO organizations "
        "(code, name, org_type, director_managed, leader_id, "
        " hq_room_id, treasury, properties) "
        "VALUES (?, ?, 'faction', 0, NULL, NULL, ?, '{}')",
        (code, name, treasury),
    )
    await db._db.commit()
    return await db.get_organization(code)


async def _seed_membership(
    db, char_id: int, org_id: int, rank_level: int,
) -> None:
    await db._db.execute(
        "INSERT INTO org_memberships "
        "(char_id, org_id, rank_level, standing, rep_score, "
        " specialization, joined_at) "
        "VALUES (?, ?, ?, 'member', 0, '', ?)",
        (char_id, org_id, rank_level, str(time.time())),
    )
    await db._db.commit()


async def _seed_hq(
    db, org_code: str, entry_room_id: int, room_ids: list[int],
    *, storage_max: int = 100,
) -> int:
    now = time.time()
    cur = await db._db.execute(
        "INSERT INTO player_housing "
        "(char_id, tier, housing_type, entry_room_id, room_ids, "
        " storage, storage_max, weekly_rent, deposit, "
        " purchase_price, rent_paid_until, door_direction, "
        " faction_code, created_at, last_activity) "
        "VALUES (?, 5, 'org_hq', ?, ?, '[]', ?, 500, 0, 50000, ?, "
        " 'in', ?, ?, ?)",
        (1, entry_room_id, json.dumps(room_ids), storage_max,
         now + 86400, org_code, now, now),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_influence(
    db, org_code: str, zone_id: int, score: int,
) -> None:
    await db._db.execute(
        "INSERT INTO territory_influence "
        "(zone_id, org_code, score, last_activity, last_presence) "
        "VALUES (?, ?, ?, ?, ?)",
        (zone_id, org_code, score, time.time(), time.time()),
    )
    await db._db.commit()


async def _setup_governed_city(
    db, *,
    faction_code: str = "veiled_hand",
    treasury: int = 100_000,
    storage_max: int = 100,
    influence: int = 75,
    city_name: str | None = None,
):
    """Build a complete founded city + extra characters for governance.

    Returns dict with keys: founder, org, city, zone_id, hq_room_ids,
    neighbors, citizen, outsider, other_org_leader.

    - founder: rank-5 in the owning org. Also the city's founder_id
      and (initially) mayor_id.
    - citizen: rank-2 member of the owning org (used as guest/banish
      targets and the assign-mayor target).
    - outsider: not a member of the owning org. Used as guest target,
      anti-griefing-safe banish target.
    - other_org_leader: rank-5 in a different org. Used as the
      anti-griefing-rejected banish target.
    """
    from engine.player_cities import found_city

    await _seed_account(db)
    zone_id = await _seed_zone(db, "Test Zone", "contested")
    entry_room_id = await _seed_room(db, zone_id, "HQ Entry")
    hq_room_ids = []
    for i in range(4):
        rid = await _seed_room(db, zone_id, f"HQ Room {i}")
        hq_room_ids.append(rid)

    # 3 neighbors (for room-membership tests around the city)
    neighbors = []
    for direction in ("north", "south", "east"):
        n = await _seed_room(db, zone_id, f"Neighbor {direction}")
        await _seed_exit(db, entry_room_id, n, direction)
        neighbors.append(n)

    # Owning org + founder
    org_treasury = (
        treasury
        + 25_000 * (1 if storage_max == 100 else 0)
        + 75_000 * (1 if storage_max == 200 else 0)
        + 200_000 * (1 if storage_max == 400 else 0)
    )
    org = await _seed_org(
        db, faction_code, "Test Org", treasury=org_treasury,
    )
    founder = await _seed_char(
        db, f"Founder_{faction_code}",
        faction_id=faction_code,
        room_id=entry_room_id,
    )
    await _seed_membership(db, founder["id"], org["id"], 5)
    await _seed_hq(
        db, faction_code, entry_room_id,
        hq_room_ids, storage_max=storage_max,
    )
    if influence > 0:
        await _seed_influence(db, faction_code, zone_id, influence)

    # Extra characters
    citizen = await _seed_char(
        db, f"Citizen_{faction_code}",
        faction_id=faction_code,
        room_id=entry_room_id,
    )
    await _seed_membership(db, citizen["id"], org["id"], 2)

    outsider = await _seed_char(
        db, f"Outsider_{faction_code}", faction_id="",
        room_id=entry_room_id,
    )

    # Other-org leader for anti-griefing test
    other_code = f"rival_{faction_code}"
    other_org = await _seed_org(
        db, other_code, "Rival Org", treasury=0,
    )
    other_org_leader = await _seed_char(
        db, f"RivalLeader_{faction_code}",
        faction_id=other_code,
        room_id=entry_room_id,
    )
    await _seed_membership(
        db, other_org_leader["id"], other_org["id"], 5,
    )

    # Found the city
    name_to_use = city_name or f"City-{faction_code.replace('_', '-')}"
    ok, msg = await found_city(db, founder, name_to_use)
    assert ok, f"setup failed in found_city: {msg}"

    from engine.player_cities import get_city_by_org
    city = await get_city_by_org(db, org["id"])
    org = await db.get_organization(faction_code)

    return {
        "founder": founder,
        "org": org,
        "city": city,
        "zone_id": zone_id,
        "hq_room_ids": hq_room_ids,
        "entry_room_id": entry_room_id,
        "neighbors": neighbors,
        "citizen": citizen,
        "outsider": outsider,
        "other_org": other_org,
        "other_org_leader": other_org_leader,
    }


# ─── 1. Constants ────────────────────────────────────────────────────────


class TestPhase3Constants(unittest.TestCase):
    def test_banishment_duration_thirty_days(self):
        from engine.player_cities import BANISHMENT_DEFAULT_SECONDS
        self.assertEqual(BANISHMENT_DEFAULT_SECONDS, 30 * 24 * 60 * 60)

    def test_motd_max_len_positive(self):
        from engine.player_cities import MOTD_MAX_LEN
        self.assertGreater(MOTD_MAX_LEN, 0)
        self.assertLessEqual(MOTD_MAX_LEN, 1024)

    def test_list_page_size_positive(self):
        from engine.player_cities import CITY_LIST_PAGE_SIZE
        self.assertGreater(CITY_LIST_PAGE_SIZE, 0)

    def test_max_tax_rate_within_design(self):
        from engine.player_cities import MAX_TAX_RATE
        # Design §5.4: 10% absolute ceiling
        self.assertEqual(MAX_TAX_RATE, 0.10)


# ─── 2. is_banished read path ────────────────────────────────────────────


class TestIsBanishedHelper(unittest.TestCase):
    def test_no_banishment_returns_false(self):
        async def _t():
            from engine.player_cities import is_banished
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            self.assertFalse(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())

    def test_active_banishment_returns_true(self):
        async def _t():
            from engine.player_cities import is_banished
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            await db.execute(
                "INSERT INTO player_city_banishments "
                "(city_id, char_id, until, issued_by, issued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["outsider"]["id"],
                 now + 3600, ctx["founder"]["id"], now),
            )
            await db.commit()
            self.assertTrue(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())

    def test_expired_banishment_returns_false(self):
        async def _t():
            from engine.player_cities import is_banished
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            await db.execute(
                "INSERT INTO player_city_banishments "
                "(city_id, char_id, until, issued_by, issued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["outsider"]["id"],
                 now - 3600, ctx["founder"]["id"], now - 7200),
            )
            await db.commit()
            self.assertFalse(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


# ─── 3. is_guest read path ───────────────────────────────────────────────


class TestIsGuestHelper(unittest.TestCase):
    def test_no_guest_returns_false(self):
        async def _t():
            from engine.player_cities import is_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            self.assertFalse(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())

    def test_guest_row_returns_true(self):
        async def _t():
            from engine.player_cities import is_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            await db.execute(
                "INSERT INTO player_city_guests "
                "(city_id, char_id, added_by, added_at) "
                "VALUES (?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["outsider"]["id"],
                 ctx["founder"]["id"], now),
            )
            await db.commit()
            self.assertTrue(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


# ─── 4. get_city_role (6 outcomes) ───────────────────────────────────────


class TestGetCityRole(unittest.TestCase):
    def test_founder_role(self):
        async def _t():
            from engine.player_cities import get_city_role
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            role = await get_city_role(db, ctx["city"], ctx["founder"])
            self.assertEqual(role, "founder")
        _run(_t())

    def test_citizen_role(self):
        async def _t():
            from engine.player_cities import get_city_role
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            role = await get_city_role(db, ctx["city"], ctx["citizen"])
            self.assertEqual(role, "citizen")
        _run(_t())

    def test_outsider_role(self):
        async def _t():
            from engine.player_cities import get_city_role
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            role = await get_city_role(db, ctx["city"], ctx["outsider"])
            self.assertEqual(role, "outsider")
        _run(_t())

    def test_guest_role(self):
        async def _t():
            from engine.player_cities import get_city_role
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            await db.execute(
                "INSERT INTO player_city_guests "
                "(city_id, char_id, added_by, added_at) "
                "VALUES (?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["outsider"]["id"],
                 ctx["founder"]["id"], now),
            )
            await db.commit()
            role = await get_city_role(db, ctx["city"], ctx["outsider"])
            self.assertEqual(role, "guest")
        _run(_t())

    def test_banished_role_overrides_citizen(self):
        """Banishment supersedes citizen status."""
        async def _t():
            from engine.player_cities import get_city_role
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            await db.execute(
                "INSERT INTO player_city_banishments "
                "(city_id, char_id, until, issued_by, issued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["citizen"]["id"],
                 now + 3600, ctx["founder"]["id"], now),
            )
            await db.commit()
            role = await get_city_role(db, ctx["city"], ctx["citizen"])
            self.assertEqual(role, "banished")
        _run(_t())

    def test_mayor_role_after_reassignment(self):
        """After reassigning Mayor away from Founder, the new Mayor
        gets the 'mayor' role and the original Founder retains
        'founder' (founder is immutable)."""
        async def _t():
            from engine.player_cities import (
                assign_mayor, get_city_role, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await assign_mayor(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            role = await get_city_role(db, city2, ctx["citizen"])
            self.assertEqual(role, "mayor")
            # Founder stays founder
            role2 = await get_city_role(db, city2, ctx["founder"])
            self.assertEqual(role2, "founder")
        _run(_t())


# ─── 5. list_active_cities ───────────────────────────────────────────────


class TestListActiveCities(unittest.TestCase):
    def test_returns_active_only(self):
        async def _t():
            from engine.player_cities import list_active_cities
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            cities = await list_active_cities(db)
            self.assertEqual(len(cities), 1)
            self.assertEqual(cities[0]["id"], ctx["city"]["id"])
        _run(_t())

    def test_zone_filter(self):
        async def _t():
            from engine.player_cities import list_active_cities
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # Wrong zone → empty list
            other_zone_id = await _seed_zone(db, "Other Zone", "contested")
            cities = await list_active_cities(db, zone_id=other_zone_id)
            self.assertEqual(cities, [])
            # Right zone → list one
            cities = await list_active_cities(db, zone_id=ctx["zone_id"])
            self.assertEqual(len(cities), 1)
        _run(_t())


# ─── 6. list_city_room_ids ───────────────────────────────────────────────


class TestListCityRoomIds(unittest.TestCase):
    def test_returns_center_then_expansion(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, list_city_room_ids,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # Add an expansion room
            ok, _ = await claim_room_for_city(
                db, ctx["founder"], ctx["neighbors"][0],
            )
            self.assertTrue(ok)
            ids = await list_city_room_ids(db, ctx["city"]["id"])
            # 4 HQ rooms + 1 expansion = 5
            self.assertEqual(len(ids), 5)
            self.assertIn(ctx["neighbors"][0], ids)
            # Center rows come first (is_center DESC). Verify the
            # expansion is somewhere in the tail.
            last_id = ids[-1]
            row = await db.fetchall(
                "SELECT is_center FROM player_city_rooms "
                "WHERE city_id = ? AND room_id = ?",
                (ctx["city"]["id"], last_id),
            )
            self.assertEqual(int(row[0]["is_center"]), 0)
        _run(_t())


# ─── 7. list_guests ──────────────────────────────────────────────────────


class TestListGuests(unittest.TestCase):
    def test_empty(self):
        async def _t():
            from engine.player_cities import list_guests
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            self.assertEqual(
                await list_guests(db, ctx["city"]["id"]),
                [],
            )
        _run(_t())

    def test_returns_added_guest(self):
        async def _t():
            from engine.player_cities import add_guest, list_guests
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertIn(
                ctx["outsider"]["id"],
                await list_guests(db, ctx["city"]["id"]),
            )
        _run(_t())


# ─── 8. list_active_banishments ──────────────────────────────────────────


class TestListActiveBanishments(unittest.TestCase):
    def test_expired_banishment_excluded(self):
        async def _t():
            from engine.player_cities import list_active_banishments
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            now = time.time()
            # Expired
            await db.execute(
                "INSERT INTO player_city_banishments "
                "(city_id, char_id, until, issued_by, issued_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (ctx["city"]["id"], ctx["outsider"]["id"],
                 now - 3600, ctx["founder"]["id"], now - 7200),
            )
            await db.commit()
            self.assertEqual(
                await list_active_banishments(db, ctx["city"]["id"]),
                [],
            )
        _run(_t())

    def test_active_banishment_listed(self):
        async def _t():
            from engine.player_cities import (
                banish_player, list_active_banishments,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            rows = await list_active_banishments(db, ctx["city"]["id"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(
                int(rows[0]["char_id"]), ctx["outsider"]["id"],
            )
        _run(_t())


# ─── 9-13. assign_mayor ──────────────────────────────────────────────────


class TestAssignMayorFounderOnly(unittest.TestCase):
    def test_non_founder_rejected(self):
        async def _t():
            from engine.player_cities import assign_mayor
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # citizen is a member of the org but not founder
            ok, msg = await assign_mayor(
                db, ctx["citizen"], ctx["citizen"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("Founder", msg)
        _run(_t())


class TestAssignMayorTargetExists(unittest.TestCase):
    def test_bogus_id_rejected(self):
        async def _t():
            from engine.player_cities import assign_mayor
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await assign_mayor(
                db, ctx["founder"], 999_999,
            )
            self.assertFalse(ok)
            self.assertIn("does not exist", msg)
        _run(_t())


class TestAssignMayorTargetIsOrgMember(unittest.TestCase):
    def test_non_member_rejected(self):
        async def _t():
            from engine.player_cities import assign_mayor
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await assign_mayor(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("not a member", msg)
        _run(_t())


class TestAssignMayorIdempotent(unittest.TestCase):
    def test_assigning_existing_mayor_no_op(self):
        async def _t():
            from engine.player_cities import assign_mayor
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # Founder is also the initial Mayor; assigning founder
            # to Mayor again is a no-op success.
            ok, msg = await assign_mayor(
                db, ctx["founder"], ctx["founder"]["id"],
            )
            self.assertTrue(ok)
            self.assertIn("already", msg.lower())
        _run(_t())


class TestAssignMayorHappyPath(unittest.TestCase):
    def test_mayor_id_updated(self):
        async def _t():
            from engine.player_cities import (
                assign_mayor, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await assign_mayor(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok, msg)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(
                int(city2["mayor_id"]), ctx["citizen"]["id"],
            )
            # Founder unchanged
            self.assertEqual(
                int(city2["founder_id"]), ctx["founder"]["id"],
            )
        _run(_t())


# ─── 14-18. set_city_motd ────────────────────────────────────────────────


class TestSetMotdMayorOrFounder(unittest.TestCase):
    def test_outsider_rejected(self):
        async def _t():
            from engine.player_cities import set_city_motd
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await set_city_motd(
                db, ctx["outsider"], "Welcome",
            )
            self.assertFalse(ok)
            # Outsider has no faction → "not a member"
            self.assertIn("not a member", msg)
        _run(_t())

    def test_citizen_rejected(self):
        """Plain citizen (not Mayor, not Founder) cannot set motd."""
        async def _t():
            from engine.player_cities import set_city_motd
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await set_city_motd(
                db, ctx["citizen"], "Welcome",
            )
            self.assertFalse(ok)
            self.assertIn("Mayor or Founder", msg)
        _run(_t())


class TestSetMotdLength(unittest.TestCase):
    def test_over_max_rejected(self):
        async def _t():
            from engine.player_cities import set_city_motd, MOTD_MAX_LEN
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await set_city_motd(
                db, ctx["founder"], "x" * (MOTD_MAX_LEN + 1),
            )
            self.assertFalse(ok)
            self.assertIn("too long", msg)
        _run(_t())


class TestSetMotdHappyPath(unittest.TestCase):
    def test_motd_set(self):
        async def _t():
            from engine.player_cities import (
                set_city_motd, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await set_city_motd(
                db, ctx["founder"], "Welcome, traveler.",
            )
            self.assertTrue(ok)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(city2["motd"], "Welcome, traveler.")
        _run(_t())


class TestSetMotdClear(unittest.TestCase):
    def test_empty_clears_motd(self):
        async def _t():
            from engine.player_cities import (
                set_city_motd, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await set_city_motd(db, ctx["founder"], "First.")
            ok, msg = await set_city_motd(db, ctx["founder"], "")
            self.assertTrue(ok)
            self.assertIn("cleared", msg.lower())
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(city2["motd"], "")
        _run(_t())


class TestSetMotdFounderAlso(unittest.TestCase):
    def test_after_reassign_founder_still_can_set(self):
        """After reassigning Mayor to citizen, the Founder retains
        motd-set permission (Mayor-or-Founder)."""
        async def _t():
            from engine.player_cities import (
                assign_mayor, set_city_motd, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await assign_mayor(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok)
            ok2, _ = await set_city_motd(
                db, ctx["founder"], "Founder still.",
            )
            self.assertTrue(ok2)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(city2["motd"], "Founder still.")
        _run(_t())


# ─── 19-25. guest commands ───────────────────────────────────────────────


class TestAddGuestMayorOrFounder(unittest.TestCase):
    def test_non_officer_rejected(self):
        async def _t():
            from engine.player_cities import add_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await add_guest(
                db, ctx["citizen"], ctx["outsider"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("Mayor or Founder", msg)
        _run(_t())


class TestAddGuestTargetExists(unittest.TestCase):
    def test_bogus_id_rejected(self):
        async def _t():
            from engine.player_cities import add_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await add_guest(db, ctx["founder"], 999_999)
            self.assertFalse(ok)
            self.assertIn("does not exist", msg)
        _run(_t())


class TestAddGuestCitizenRejected(unittest.TestCase):
    def test_org_member_as_guest_rejected(self):
        async def _t():
            from engine.player_cities import add_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await add_guest(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("already a citizen", msg)
        _run(_t())


class TestAddGuestIdempotent(unittest.TestCase):
    def test_duplicate_add_noop(self):
        async def _t():
            from engine.player_cities import add_guest, list_guests
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok1, _ = await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            ok2, msg = await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok1)
            self.assertTrue(ok2)
            self.assertIn("already", msg.lower())
            # Only one row
            guests = await list_guests(db, ctx["city"]["id"])
            self.assertEqual(len(guests), 1)
        _run(_t())


class TestAddGuestHappyPath(unittest.TestCase):
    def test_guest_inserted(self):
        async def _t():
            from engine.player_cities import add_guest, is_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertTrue(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestRemoveGuestNotPresent(unittest.TestCase):
    def test_not_on_list_rejected(self):
        async def _t():
            from engine.player_cities import remove_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await remove_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("not on the guest list", msg)
        _run(_t())


class TestRemoveGuestHappyPath(unittest.TestCase):
    def test_guest_removed(self):
        async def _t():
            from engine.player_cities import (
                add_guest, remove_guest, is_guest,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            ok, _ = await remove_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertFalse(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


# ─── 26-36. banish / unbanish ────────────────────────────────────────────


class TestBanishMayorOrFounder(unittest.TestCase):
    def test_citizen_cannot_banish(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await banish_player(
                db, ctx["citizen"], ctx["outsider"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("Mayor or Founder", msg)
        _run(_t())


class TestBanishTargetExists(unittest.TestCase):
    def test_bogus_id_rejected(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await banish_player(db, ctx["founder"], 999_999)
            self.assertFalse(ok)
            self.assertIn("does not exist", msg)
        _run(_t())


class TestBanishSelfRejected(unittest.TestCase):
    def test_cannot_banish_self(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await banish_player(
                db, ctx["founder"], ctx["founder"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("yourself", msg.lower())
        _run(_t())


class TestBanishFounderRejected(unittest.TestCase):
    """If a non-founder Mayor tries to banish the Founder, refused."""

    def test_mayor_cannot_banish_founder(self):
        async def _t():
            from engine.player_cities import (
                assign_mayor, banish_player,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # Reassign Mayor to citizen
            ok, _ = await assign_mayor(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok)
            # New Mayor tries to banish the Founder
            ok2, msg = await banish_player(
                db, ctx["citizen"], ctx["founder"]["id"],
            )
            self.assertFalse(ok2)
            self.assertIn("Founder", msg)
        _run(_t())


class TestBanishRivalLeaderRejected(unittest.TestCase):
    def test_other_org_leader_rejected(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await banish_player(
                db, ctx["founder"], ctx["other_org_leader"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("anti-griefing", msg.lower())
        _run(_t())


class TestBanishHappyPath(unittest.TestCase):
    def test_banishment_row_inserted(self):
        async def _t():
            from engine.player_cities import banish_player, is_banished
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertTrue(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())

    def test_until_thirty_days_default(self):
        async def _t():
            from engine.player_cities import (
                banish_player, BANISHMENT_DEFAULT_SECONDS,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            t_before = time.time()
            ok, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            rows = await db.fetchall(
                "SELECT until FROM player_city_banishments "
                "WHERE city_id = ? AND char_id = ?",
                (ctx["city"]["id"], ctx["outsider"]["id"]),
            )
            until = float(rows[0]["until"])
            # Should be approximately t_before + 30 days
            self.assertGreaterEqual(
                until, t_before + BANISHMENT_DEFAULT_SECONDS - 2,
            )
            self.assertLessEqual(
                until, time.time() + BANISHMENT_DEFAULT_SECONDS + 2,
            )
        _run(_t())


class TestBanishDropsFromGuestList(unittest.TestCase):
    def test_banish_removes_guest_entry(self):
        async def _t():
            from engine.player_cities import (
                add_guest, banish_player, is_guest, is_banished,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            ok, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertFalse(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
            self.assertTrue(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestBanishExtendsExisting(unittest.TestCase):
    def test_re_banish_replaces_until(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok1, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
                duration_seconds=60,
            )
            self.assertTrue(ok1)
            ok2, _ = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
                duration_seconds=3600,
            )
            self.assertTrue(ok2)
            rows = await db.fetchall(
                "SELECT COUNT(*) AS n FROM player_city_banishments "
                "WHERE city_id = ? AND char_id = ?",
                (ctx["city"]["id"], ctx["outsider"]["id"]),
            )
            # Exactly one row (replaced, not appended)
            self.assertEqual(int(rows[0]["n"]), 1)
        _run(_t())


class TestBanishZeroDurationRejected(unittest.TestCase):
    def test_zero_duration_rejected(self):
        async def _t():
            from engine.player_cities import banish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
                duration_seconds=0,
            )
            self.assertFalse(ok)
            self.assertIn("positive", msg.lower())
        _run(_t())


class TestUnbanishNotPresent(unittest.TestCase):
    def test_no_banishment_rejected(self):
        async def _t():
            from engine.player_cities import unbanish_player
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await unbanish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertFalse(ok)
            self.assertIn("not banished", msg.lower())
        _run(_t())


class TestUnbanishHappyPath(unittest.TestCase):
    def test_banishment_removed(self):
        async def _t():
            from engine.player_cities import (
                banish_player, unbanish_player, is_banished,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            ok, _ = await unbanish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            self.assertTrue(ok)
            self.assertFalse(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


# ─── 37-40. set_room_citizen_only ────────────────────────────────────────


class TestSetRoomCitizenOnlyAuth(unittest.TestCase):
    def test_citizen_cannot_flag(self):
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, msg = await set_room_citizen_only(
                db, ctx["citizen"], ctx["hq_room_ids"][0], True,
            )
            self.assertFalse(ok)
            self.assertIn("Mayor or Founder", msg)
        _run(_t())


class TestSetRoomCitizenOnlyRoomMembership(unittest.TestCase):
    def test_non_city_room_rejected(self):
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # A neighbor room is not part of the city
            ok, msg = await set_room_citizen_only(
                db, ctx["founder"], ctx["neighbors"][0], True,
            )
            self.assertFalse(ok)
            self.assertIn("not part of your city", msg)
        _run(_t())


class TestSetRoomCitizenOnlyHappyOn(unittest.TestCase):
    def test_flag_set_to_one(self):
        async def _t():
            from engine.player_cities import (
                set_room_citizen_only, list_citizen_room_ids,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            ok, _ = await set_room_citizen_only(
                db, ctx["founder"], ctx["hq_room_ids"][0], True,
            )
            self.assertTrue(ok)
            citizen_rooms = await list_citizen_room_ids(
                db, ctx["city"]["id"],
            )
            self.assertIn(ctx["hq_room_ids"][0], citizen_rooms)
        _run(_t())


class TestSetRoomCitizenOnlyHappyOff(unittest.TestCase):
    def test_flag_cleared(self):
        async def _t():
            from engine.player_cities import (
                set_room_citizen_only, list_citizen_room_ids,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await set_room_citizen_only(
                db, ctx["founder"], ctx["hq_room_ids"][0], True,
            )
            ok, _ = await set_room_citizen_only(
                db, ctx["founder"], ctx["hq_room_ids"][0], False,
            )
            self.assertTrue(ok)
            citizen_rooms = await list_citizen_room_ids(
                db, ctx["city"]["id"],
            )
            self.assertNotIn(ctx["hq_room_ids"][0], citizen_rooms)
        _run(_t())


# ─── 41-44. format helpers ───────────────────────────────────────────────


class TestFormatCityHeaderTag(unittest.TestCase):
    def test_format_returns_bracketed_name(self):
        from engine.player_cities import format_city_header_tag
        tag = format_city_header_tag({"name": "Veiled Hand"})
        self.assertIn("[CITY:", tag)
        self.assertIn("Veiled Hand", tag)
        self.assertTrue(tag.startswith(" "))  # leading space for chain

    def test_format_empty_on_none(self):
        from engine.player_cities import format_city_header_tag
        self.assertEqual(format_city_header_tag(None), "")
        self.assertEqual(format_city_header_tag({}), "")


class TestFormatCityInfoOutsider(unittest.TestCase):
    def test_outsider_sees_count_only(self):
        async def _t():
            from engine.player_cities import format_city_info
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            lines = await format_city_info(
                db, ctx["city"], viewer=ctx["outsider"],
            )
            joined = "\n".join(lines)
            # Should NOT show individual citizen names (just a count)
            self.assertNotIn(ctx["citizen"]["name"], joined)
            self.assertIn("Citizens:", joined)
        _run(_t())


class TestFormatCityInfoCitizen(unittest.TestCase):
    def test_citizen_sees_names(self):
        async def _t():
            from engine.player_cities import format_city_info
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            lines = await format_city_info(
                db, ctx["city"], viewer=ctx["citizen"],
            )
            joined = "\n".join(lines)
            self.assertIn(ctx["citizen"]["name"], joined)
            self.assertIn(ctx["founder"]["name"], joined)
        _run(_t())


class TestFormatCityInfoBanished(unittest.TestCase):
    def test_banished_short_circuits(self):
        async def _t():
            from engine.player_cities import (
                banish_player, format_city_info,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            lines = await format_city_info(
                db, ctx["city"], viewer=ctx["outsider"],
            )
            self.assertEqual(len(lines), 1)
            self.assertIn("banished", lines[0].lower())
        _run(_t())


# ─── 45-61. parser tests ─────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None, is_admin=False):
        self.character = character
        self.is_in_game = character is not None
        self.account = {
            "is_admin": 1 if is_admin else 0,
            "is_builder": 0,
        }
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None


def _ctx_for(session, db, command: str, args: str):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"{command} {args}".strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
        session_mgr=_FakeSessionManager(),
    )


class TestParserInfoNoCity(unittest.TestCase):
    def test_no_city_path(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            # An outsider not in any city
            await _seed_account(db)
            zone_id = await _seed_zone(db, "Z", "contested")
            room_id = await _seed_room(db, zone_id, "Empty")
            char = await _seed_char(
                db, "Lone", faction_id="", room_id=room_id,
            )
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "info")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("not in a city", text.lower())
        _run(_t())


class TestParserInfoInCity(unittest.TestCase):
    def test_in_city_shows_name(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            # Founder is standing in HQ entry — which is a city room
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "info")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn(ctx["city"]["name"], text)
        _run(_t())


class TestParserMapInCity(unittest.TestCase):
    def test_map_lists_rooms(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "map")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Map of", text)
            self.assertIn(ctx["city"]["name"], text)
            # The 4 HQ rooms should each appear by id
            for rid in ctx["hq_room_ids"]:
                self.assertIn(f"[{rid}]", text)
        _run(_t())


class TestParserCitizensInCity(unittest.TestCase):
    def test_citizens_lists_members_and_guests(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import add_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "citizens")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn(ctx["founder"]["name"], text)
            self.assertIn(ctx["citizen"]["name"], text)
            self.assertIn("Guests:", text)
            self.assertIn(ctx["outsider"]["name"], text)
        _run(_t())


class TestParserList(unittest.TestCase):
    def test_list_echoes_city(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "list")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Active Player Cities", text)
            self.assertIn(ctx["city"]["name"], text)
        _run(_t())


class TestParserMotdHappyPath(unittest.TestCase):
    def test_motd_set_via_parser(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city",
                            "motd Welcome to the city")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(city2["motd"], "Welcome to the city")
        _run(_t())


class TestParserMotdNoArgs(unittest.TestCase):
    def test_motd_clear_with_no_args(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import (
                set_city_motd, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await set_city_motd(
                db, ctx["founder"], "Existing motd",
            )
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "motd")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(city2["motd"], "")
        _run(_t())


class TestParserMayorNoArgs(unittest.TestCase):
    def test_usage_echoed(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "mayor")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Usage:", text)
            self.assertIn("+city mayor", text)
        _run(_t())


class TestParserMayorBadName(unittest.TestCase):
    def test_not_found_echoed(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "mayor NoSuchPerson")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("No character named", text)
        _run(_t())


class TestParserGuardsInCity(unittest.TestCase):
    def test_guards_renders_empty_roster(self):
        """Phase 7 (May 23 2026): the bare `+city guards` view
        no longer carries the Phase 6/7-coming stub language.
        It now renders the real roster header (slot count +
        status) and an empty-roster line.

        Pre-Phase-7 assertion was `assertIn("Phase 6/7", text)`;
        that text was removed when assign/remove shipped.
        """
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "guards")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Guards of", text)
            # New Phase 7 shape: slot count + status line
            self.assertIn("Slots:", text)
            # Empty-roster line
            self.assertIn("No NPC guards stationed", text)
        _run(_t())


class TestParserGuestAddHappyPath(unittest.TestCase):
    def test_guest_added(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import is_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city",
                f"guest add {ctx['outsider']['name']}",
            )
            await CityCommand().execute(cctx)
            self.assertTrue(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestParserGuestRemoveHappyPath(unittest.TestCase):
    def test_guest_removed(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import add_guest, is_guest
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await add_guest(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city",
                f"guest remove {ctx['outsider']['name']}",
            )
            await CityCommand().execute(cctx)
            self.assertFalse(
                await is_guest(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestParserGuestBadAction(unittest.TestCase):
    def test_invalid_action(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city", "guest poke Outsider",
            )
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Unknown guest action", text)
        _run(_t())


class TestParserBanishHappyPath(unittest.TestCase):
    def test_banishment_via_parser(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import is_banished
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city",
                f"banish {ctx['outsider']['name']}",
            )
            await CityCommand().execute(cctx)
            self.assertTrue(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestParserUnbanishHappyPath(unittest.TestCase):
    def test_unbanish_via_parser(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import (
                banish_player, is_banished,
            )
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            await banish_player(
                db, ctx["founder"], ctx["outsider"]["id"],
            )
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city",
                f"unbanish {ctx['outsider']['name']}",
            )
            await CityCommand().execute(cctx)
            self.assertFalse(
                await is_banished(
                    db, ctx["city"]["id"], ctx["outsider"]["id"],
                )
            )
        _run(_t())


class TestParserCitizenroomOnHappyPath(unittest.TestCase):
    def test_flag_set_via_parser(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import list_citizen_room_ids
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            # Use explicit room_id (founder.room_id is the HQ entry,
            # which is NOT a center row because Phase 1 anchors
            # room_ids only — entry_room is the doorstep, not in city)
            cctx = _ctx_for(
                session, db, "+city",
                f"citizenroom on {ctx['hq_room_ids'][0]}",
            )
            await CityCommand().execute(cctx)
            rooms = await list_citizen_room_ids(db, ctx["city"]["id"])
            self.assertIn(ctx["hq_room_ids"][0], rooms)
        _run(_t())


class TestParserCitizenroomBadFlag(unittest.TestCase):
    def test_bad_flag_rejected(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city", "citizenroom maybe 42",
            )
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("on", text)
            self.assertIn("off", text)
        _run(_t())


# ─── 62-63. Phase membership ─────────────────────────────────────────────


class TestPhase3NotInPlaceholderList(unittest.TestCase):
    def test_info_is_live(self):
        """+city info no longer renders the Phase-3 placeholder."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "info")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            # Phase 3 placeholder string is "(coming in Phase 3:..."
            self.assertNotIn("coming in Phase 3", text)
        _run(_t())

    def test_motd_is_live(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "motd Hello")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertNotIn("coming in Phase 3", text)
        _run(_t())

    def test_banish_is_live(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(
                session, db, "+city",
                f"banish {ctx['outsider']['name']}",
            )
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertNotIn("coming in Phase 3", text)
        _run(_t())


class TestPhase4TaxStillPlaceholder(unittest.TestCase):
    def test_tax_subcommand_shipped_in_phase_4(self):
        """Phase 4 (cities_phase4 drop, May 22 2026) moved +city tax
        out of the placeholder list. This test was originally
        written against Phase 3's placeholder echo asserting
        'Phase 4' would appear in the output; re-purposed to assert
        the bare-help advertises tax as live, mirroring the May 22
        Phase 2 and Phase 3 re-purpose discipline (pinned-keyset on
        umbrella surfaces is the canonical signal that the public
        contract changed)."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city tax", text)
        _run(_t())

    def test_home_subcommand_shipped_in_phase_5(self):
        """Phase 5 (cities_phase5 drop, May 22 2026) moved +city home
        out of the placeholder list. This test was originally
        written against Phase 3's placeholder echo expecting
        'Phase 5' to appear in the output; re-purposed to assert
        the bare-help advertises home as live. Same pinned-keyset
        discipline as the Phase 2 (claim/release), Phase 3 (motd,
        banish), Phase 4 (tax), and Phase 4b/5 tests use — the
        umbrella's "Available now:" list is the canonical signal
        that the public contract changed."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_governed_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city home", text)
        _run(_t())


if __name__ == "__main__":
    unittest.main()
