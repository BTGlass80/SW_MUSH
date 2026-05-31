# -*- coding: utf-8 -*-
"""
tests/test_cities_phase1.py — Player Cities Phase 1 (May 22 2026).

Per ``player_cities_design_v1_2.md`` §13 Phase 1 and the May 22
design calls (locked in HEAD_AUDIT_MAY22_EVENING.md + this drop's
handoff):
  - Hard-block eligibility predicate (only declared contested/lawless)
  - Founding costs 25K / 75K / 200K (design-doc numbers)
  - Drop label: ``cities_phase1``

Test sections
=============

  1. TestSchema                         — ensure_schema creates tables idempotently
  2. TestValidateName                   — pure validate_city_name
  3. TestReadHelpersEmpty               — get_city_* on empty DB
  4. TestFoundCityNameValidation        — name rejection paths
  5. TestFoundCityIndependentChar       — non-faction characters rejected
  6. TestFoundCityNonexistentOrg        — orphan faction_id rejected
  7. TestFoundCityNonLeader             — rank < 5 rejected
  8. TestFoundCityNoHQ                  — org without tier-5 HQ rejected
  9. TestFoundCityUnknownHqType         — bad storage_max rejected
 10. TestFoundCityZoneNotEligible       — secured zone rejected
 11. TestFoundCityZoneNotDeclared       — unknown security rejected (hard-block)
 12. TestFoundCityLowInfluence          — < 50 influence rejected
 13. TestFoundCityInsufficientTreasury  — treasury < cost rejected
 14. TestFoundCityHappyPathOutpost      — outpost: 25K debit + rows created
 15. TestFoundCityHappyPathChapter      — chapter_house: 75K debit
 16. TestFoundCityHappyPathFortress     — fortress: 200K debit
 17. TestFoundCityHqRoomsAnchored       — HQ rooms in player_city_rooms with is_center=1
 18. TestFoundCityMayorIsFounder        — mayor_id == founder_id on creation
 19. TestFoundCityDuplicateName         — name uniqueness
 20. TestFoundCityAlreadyHasOne         — one active city per org
 21. TestDissolveCityNotFound           — unknown name rejected
 22. TestDissolveCityWrongOrg           — non-member rejected
 23. TestDissolveCityNonLeader          — rank < 5 rejected
 24. TestDissolveCityHappyPath          — refund 50% + state='dissolved'
 25. TestDissolveCityRefundsPerTier     — refund amount tracks hq_tier
 26. TestDissolveCityRemovesRooms       — player_city_rooms cleared
 27. TestDissolveCityNotVisibleAfter    — get_city_by_name returns None
 28. TestDissolveCityReleasesNameSlot   — name can be reused after dissolution
 29. TestGetCityForRoomHqRoom           — read path resolves HQ rooms
 30. TestParserRegistration             — +city in registry
 31. TestParserBareHelp                 — `+city` (no args) shows phase guide
 32. TestParserPhasePlaceholders        — Phase 2/3/4/5 echo placeholders
 33. TestParserFoundDispatch            — +city found wires to engine
 34. TestParserDissolveDispatch         — +city dissolve wires to engine
 35. TestParserAccessDenied             — not-in-game rejected
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


# ─── shared fixtures ──────────────────────────────────────────────────────

async def _fresh_db():
    """In-memory DB with core schema + housing + territory + player_cities."""
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


async def _seed_room(db, zone_id: int, name: str = "HQ Entry") -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
        "VALUES (?, ?, '', '')",
        (name, zone_id),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_zone(db, name: str, security: str | None) -> int:
    """Create a zone with optional properties.security declaration.

    security=None → no properties row (the 'unknown' case for the
    hard-block predicate test).
    """
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


async def _seed_char(db, name: str, faction_id: str = "") -> dict:
    await _seed_account(db)
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(account_id, name, species, room_id, credits, faction_id) "
        "VALUES (1, ?, 'Human', 1, 100000, ?)",
        (name, faction_id),
    )
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


async def _seed_org(
    db, code: str, name: str, treasury: int = 0,
) -> dict:
    cur = await db._db.execute(
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
    """Create a player_housing row with housing_type='org_hq'.

    storage_max selects subtype: 100 outpost / 200 chapter_house / 400 fortress.
    """
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
    """Insert a territory_influence row."""
    await db._db.execute(
        "INSERT INTO territory_influence "
        "(zone_id, org_code, score, last_activity, last_presence) "
        "VALUES (?, ?, ?, ?, ?)",
        (zone_id, org_code, score, time.time(), time.time()),
    )
    await db._db.commit()


async def _full_setup(
    db, *,
    faction_code: str = "veiled_hand",
    treasury: int = 100_000,
    rank_level: int = 5,
    zone_security: str | None = "contested",
    influence: int = 75,
    storage_max: int = 100,
    hq_room_count: int = 4,
):
    """Build a complete founding-ready scenario.

    Returns (char, org_row, hq_id, zone_id, hq_room_ids) for the test
    body to mutate or read.
    """
    await _seed_account(db)
    zone_id = await _seed_zone(db, "Test Zone", zone_security)
    # HQ entry room + N HQ rooms (all in the same zone)
    entry_room_id = await _seed_room(db, zone_id, "HQ Entry")
    hq_room_ids = []
    for i in range(hq_room_count):
        rid = await _seed_room(db, zone_id, f"HQ Room {i}")
        hq_room_ids.append(rid)
    org = await _seed_org(db, faction_code, "Test Org",
                          treasury=treasury)
    # Name founder per faction so multi-org tests don't collide on
    # characters.name UNIQUE.
    char = await _seed_char(
        db, f"Founder_{faction_code}", faction_id=faction_code)
    await _seed_membership(db, char["id"], org["id"], rank_level)
    hq_id = await _seed_hq(db, faction_code, entry_room_id,
                           hq_room_ids, storage_max=storage_max)
    if influence > 0:
        await _seed_influence(db, faction_code, zone_id, influence)
    return char, org, hq_id, zone_id, hq_room_ids


# ─── 1. Schema ────────────────────────────────────────────────────────────

class TestSchema(unittest.TestCase):
    def test_ensure_schema_creates_tables(self):
        async def _t():
            db = await _fresh_db()
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name LIKE 'player_city%' "
                "OR name='player_cities'"
            )
            names = {r["name"] for r in rows}
            self.assertIn("player_cities", names)
            self.assertIn("player_city_rooms", names)
            self.assertIn("player_city_banishments", names)
            self.assertIn("player_city_guests", names)
        _run(_t())

    def test_ensure_schema_idempotent(self):
        async def _t():
            from engine.player_cities import ensure_schema
            db = await _fresh_db()
            # Run a second time — should not error
            await ensure_schema(db)
            await ensure_schema(db)
        _run(_t())

    def test_ensure_schema_creates_indexes(self):
        async def _t():
            db = await _fresh_db()
            rows = await db.fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND name LIKE 'idx_city%'"
            )
            names = {r["name"] for r in rows}
            self.assertIn("idx_city_rooms_room", names)
            self.assertIn("idx_city_org", names)
            self.assertIn("idx_city_state", names)
        _run(_t())


# ─── 2. validate_city_name (pure) ─────────────────────────────────────────

class TestValidateName(unittest.TestCase):
    def test_empty_rejected(self):
        from engine.player_cities import validate_city_name
        ok, _ = validate_city_name("")
        self.assertFalse(ok)

    def test_too_short_rejected(self):
        from engine.player_cities import validate_city_name
        ok, msg = validate_city_name("ab")
        self.assertFalse(ok)
        self.assertIn("at least", msg.lower())

    def test_too_long_rejected(self):
        from engine.player_cities import validate_city_name
        ok, msg = validate_city_name("x" * 40)
        self.assertFalse(ok)
        self.assertIn("at most", msg.lower())

    def test_invalid_chars_rejected(self):
        from engine.player_cities import validate_city_name
        for bad in ["My@City", "City#1", "[bracket]", 'a"b"c']:
            ok, _ = validate_city_name(bad)
            self.assertFalse(ok, f"expected reject for {bad!r}")

    def test_valid_chars_accepted(self):
        from engine.player_cities import validate_city_name
        for good in ["Veiled Hand Compound", "Ord's Reach",
                     "Anchorhead-East", "Outpost 7"]:
            ok, msg = validate_city_name(good)
            self.assertTrue(ok, f"expected accept for {good!r}: {msg}")
            self.assertEqual(msg, good)

    def test_reserved_name_rejected(self):
        from engine.player_cities import validate_city_name
        for reserved in ["Mos Eisley", "Coruscant", "Theed",
                         "Jedi Temple"]:
            ok, msg = validate_city_name(reserved)
            self.assertFalse(ok, f"expected reject for {reserved!r}")
            self.assertIn("reserved", msg.lower())

    def test_reserved_case_insensitive(self):
        from engine.player_cities import validate_city_name
        ok, _ = validate_city_name("mOs eIsLeY")
        self.assertFalse(ok)

    def test_whitespace_trimmed(self):
        from engine.player_cities import validate_city_name
        ok, msg = validate_city_name("   Coronet East   ")
        self.assertTrue(ok)
        self.assertEqual(msg, "Coronet East")

    def test_non_string_rejected(self):
        from engine.player_cities import validate_city_name
        for bad in [None, 42, [], {}]:
            ok, _ = validate_city_name(bad)
            self.assertFalse(ok)


# ─── 3. Read helpers (empty DB) ───────────────────────────────────────────

class TestReadHelpersEmpty(unittest.TestCase):
    def test_get_city_by_name_miss(self):
        async def _t():
            from engine.player_cities import get_city_by_name
            db = await _fresh_db()
            self.assertIsNone(await get_city_by_name(db, "nope"))
        _run(_t())

    def test_get_city_by_org_miss(self):
        async def _t():
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            self.assertIsNone(await get_city_by_org(db, 999))
        _run(_t())

    def test_get_city_for_room_miss(self):
        async def _t():
            from engine.player_cities import get_city_for_room
            db = await _fresh_db()
            self.assertIsNone(await get_city_for_room(db, 999))
        _run(_t())


# ─── 4-13. found_city — validation branches ───────────────────────────────

class TestFoundCityNameValidation(unittest.TestCase):
    def test_invalid_name_rejected_before_db_work(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            # No setup needed — name validation short-circuits.
            char = {"id": 1, "faction_id": "republic"}
            ok, msg = await found_city(db, char, "@")
            self.assertFalse(ok)
        _run(_t())


class TestFoundCityIndependentChar(unittest.TestCase):
    def test_independent_char_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char = {"id": 1, "faction_id": "independent"}
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("organization", msg.lower())
        _run(_t())

    def test_no_faction_field_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char = {"id": 1}  # no faction_id at all
            ok, _ = await found_city(db, char, "Test City")
            self.assertFalse(ok)
        _run(_t())


class TestFoundCityNonexistentOrg(unittest.TestCase):
    def test_faction_id_with_no_org_row_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char = {"id": 1, "faction_id": "ghost_org"}
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("could not be found", msg.lower())
        _run(_t())


class TestFoundCityNonLeader(unittest.TestCase):
    def test_rank_4_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(db, rank_level=4)
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("leader", msg.lower())
        _run(_t())


class TestFoundCityAlreadyHasCity(unittest.TestCase):
    def test_second_founding_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(db)
            ok1, _ = await found_city(db, char, "First City")
            self.assertTrue(ok1)
            ok2, msg = await found_city(db, char, "Second City")
            self.assertFalse(ok2)
            self.assertIn("already", msg.lower())
        _run(_t())


class TestFoundCityNoHQ(unittest.TestCase):
    def test_org_without_hq_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            await _seed_account(db)
            org = await _seed_org(db, "test_org", "Test", treasury=100000)
            char = await _seed_char(db, "Founder", faction_id="test_org")
            await _seed_membership(db, char["id"], org["id"], 5)
            # No HQ seeded
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("hq", msg.lower())
        _run(_t())


class TestFoundCityUnknownHqType(unittest.TestCase):
    def test_bogus_storage_max_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, storage_max=333)
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("hq type", msg.lower())
        _run(_t())


class TestFoundCityZoneNotEligible(unittest.TestCase):
    def test_secured_zone_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(
                db, zone_security="secured")
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("contested", msg.lower())
        _run(_t())

    def test_contested_accepted(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(
                db, zone_security="contested")
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
        _run(_t())

    def test_lawless_accepted(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(
                db, zone_security="lawless")
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
        _run(_t())


class TestFoundCityZoneNotDeclared(unittest.TestCase):
    def test_undeclared_security_rejected(self):
        """Hard-block: zone with no properties.security must reject."""
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, zone_security=None)
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            # The error should mention contested/lawless
            self.assertIn("contested", msg.lower())
        _run(_t())


class TestFoundCityLowInfluence(unittest.TestCase):
    def test_below_threshold_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, influence=20)
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("influence", msg.lower())
        _run(_t())

    def test_zero_influence_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, influence=0)
            ok, _ = await found_city(db, char, "Test City")
            self.assertFalse(ok)
        _run(_t())

    def test_threshold_exactly_50_accepted(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, influence=50)
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
        _run(_t())


class TestFoundCityInsufficientTreasury(unittest.TestCase):
    def test_below_cost_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db, treasury=10_000)
            ok, msg = await found_city(db, char, "Test City")
            self.assertFalse(ok)
            self.assertIn("treasury", msg.lower())
        _run(_t())

    def test_chapter_house_needs_75k(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(
                db, treasury=50_000, storage_max=200)
            ok, _ = await found_city(db, char, "Test City")
            self.assertFalse(ok)
        _run(_t())


# ─── 14-20. found_city — happy paths ──────────────────────────────────────

class TestFoundCityHappyPathOutpost(unittest.TestCase):
    def test_outpost_debits_25k(self):
        async def _t():
            from engine.player_cities import found_city, FOUNDING_COSTS
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(
                db, treasury=100_000, storage_max=100)
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
            org_post = await db.get_organization(org["code"])
            self.assertEqual(
                org_post["treasury"],
                100_000 - FOUNDING_COSTS["outpost"],
            )
        _run(_t())


class TestFoundCityHappyPathChapter(unittest.TestCase):
    def test_chapter_house_debits_75k(self):
        async def _t():
            from engine.player_cities import found_city, FOUNDING_COSTS
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(
                db, treasury=200_000, storage_max=200)
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
            org_post = await db.get_organization(org["code"])
            self.assertEqual(
                org_post["treasury"],
                200_000 - FOUNDING_COSTS["chapter_house"],
            )
        _run(_t())


class TestFoundCityHappyPathFortress(unittest.TestCase):
    def test_fortress_debits_200k(self):
        async def _t():
            from engine.player_cities import found_city, FOUNDING_COSTS
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(
                db, treasury=500_000, storage_max=400)
            ok, _ = await found_city(db, char, "Test City")
            self.assertTrue(ok)
            org_post = await db.get_organization(org["code"])
            self.assertEqual(
                org_post["treasury"],
                500_000 - FOUNDING_COSTS["fortress"],
            )
        _run(_t())


class TestFoundCityHqRoomsAnchored(unittest.TestCase):
    def test_hq_rooms_inserted_as_center(self):
        async def _t():
            from engine.player_cities import (
                found_city, get_city_by_name,
            )
            db = await _fresh_db()
            char, _, _, _, hq_room_ids = await _full_setup(
                db, hq_room_count=4)
            await found_city(db, char, "Test City")
            city = await get_city_by_name(db, "Test City")
            rows = await db.fetchall(
                "SELECT room_id, is_center FROM player_city_rooms "
                "WHERE city_id = ?",
                (city["id"],),
            )
            anchored = {r["room_id"] for r in rows}
            self.assertEqual(anchored, set(hq_room_ids))
            for r in rows:
                self.assertEqual(r["is_center"], 1)
        _run(_t())


class TestFoundCityMayorIsFounder(unittest.TestCase):
    def test_mayor_equals_founder_on_create(self):
        async def _t():
            from engine.player_cities import (
                found_city, get_city_by_name,
            )
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            await found_city(db, char, "Test City")
            city = await get_city_by_name(db, "Test City")
            self.assertEqual(city["founder_id"], char["id"])
            self.assertEqual(city["mayor_id"], char["id"])
        _run(_t())


class TestFoundCityDuplicateName(unittest.TestCase):
    def test_duplicate_name_across_orgs_rejected(self):
        async def _t():
            from engine.player_cities import found_city
            db = await _fresh_db()
            # First org founds "Capitol"
            char1, _, _, _, _ = await _full_setup(
                db, faction_code="org_a")
            ok1, _ = await found_city(db, char1, "Capitol")
            self.assertTrue(ok1)
            # Second org tries the same name (case-insensitively)
            char2, _, _, _, _ = await _full_setup(
                db, faction_code="org_b")
            ok2, msg = await found_city(db, char2, "capitol")
            self.assertFalse(ok2)
            self.assertIn("exist", msg.lower())
        _run(_t())


# ─── 21-28. dissolve_city ─────────────────────────────────────────────────

class TestDissolveCityNotFound(unittest.TestCase):
    def test_unknown_name_rejected(self):
        async def _t():
            from engine.player_cities import dissolve_city
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            ok, msg = await dissolve_city(db, char, "Ghost City")
            self.assertFalse(ok)
            self.assertIn("no active", msg.lower())
        _run(_t())


class TestDissolveCityWrongOrg(unittest.TestCase):
    def test_other_org_member_rejected(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
            )
            db = await _fresh_db()
            char1, _, _, _, _ = await _full_setup(
                db, faction_code="org_a")
            await found_city(db, char1, "City Alpha")
            char2, _, _, _, _ = await _full_setup(
                db, faction_code="org_b")
            ok, msg = await dissolve_city(db, char2, "City Alpha")
            self.assertFalse(ok)
            self.assertIn("not a member", msg.lower())
        _run(_t())


class TestDissolveCityNonLeader(unittest.TestCase):
    def test_non_leader_member_rejected(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
            )
            db = await _fresh_db()
            char_leader, org, _, _, _ = await _full_setup(db)
            await found_city(db, char_leader, "Test City")

            # Add a rank-2 member from the same org
            member = await _seed_char(
                db, "Member", faction_id=org["code"])
            await _seed_membership(db, member["id"], org["id"], 2)
            ok, msg = await dissolve_city(db, member, "Test City")
            self.assertFalse(ok)
            self.assertIn("leader", msg.lower())
        _run(_t())


class TestDissolveCityHappyPath(unittest.TestCase):
    def test_dissolution_refund_and_state_flip(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city, FOUNDING_COSTS,
                DISSOLUTION_REFUND_PCT,
            )
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(
                db, treasury=100_000, storage_max=100)
            await found_city(db, char, "Test City")
            # Treasury after founding: 100_000 - 25_000 = 75_000
            org_mid = await db.get_organization(org["code"])
            self.assertEqual(org_mid["treasury"], 75_000)

            ok, _ = await dissolve_city(db, char, "Test City")
            self.assertTrue(ok)
            # Refund 50% of 25_000 = 12_500
            expected_refund = (
                FOUNDING_COSTS["outpost"] * DISSOLUTION_REFUND_PCT
            ) // 100
            org_post = await db.get_organization(org["code"])
            self.assertEqual(
                org_post["treasury"], 75_000 + expected_refund,
            )
            # State flipped
            rows = await db.fetchall(
                "SELECT state FROM player_cities "
                "WHERE name = 'Test City'"
            )
            self.assertEqual(rows[0]["state"], "dissolved")
        _run(_t())


class TestDissolveCityRefundsPerTier(unittest.TestCase):
    def test_fortress_refund_100k(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
            )
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(
                db, treasury=500_000, storage_max=400)
            await found_city(db, char, "Test Fortress")
            # 500_000 - 200_000 = 300_000
            await dissolve_city(db, char, "Test Fortress")
            # Refund 100_000
            org_post = await db.get_organization(org["code"])
            self.assertEqual(org_post["treasury"], 300_000 + 100_000)
        _run(_t())


class TestDissolveCityRemovesRooms(unittest.TestCase):
    def test_city_rooms_cleared(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
            )
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            await found_city(db, char, "Test City")
            await dissolve_city(db, char, "Test City")
            rows = await db.fetchall(
                "SELECT * FROM player_city_rooms"
            )
            self.assertEqual(len(rows), 0)
        _run(_t())


class TestDissolveCityNotVisibleAfter(unittest.TestCase):
    def test_dissolved_city_invisible_to_readers(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
                get_city_by_name, get_city_by_org,
            )
            db = await _fresh_db()
            char, org, _, _, _ = await _full_setup(db)
            await found_city(db, char, "Test City")
            await dissolve_city(db, char, "Test City")
            self.assertIsNone(await get_city_by_name(db, "Test City"))
            self.assertIsNone(await get_city_by_org(db, org["id"]))
        _run(_t())


class TestDissolveCityReleasesNameSlot(unittest.TestCase):
    def test_name_reusable_after_dissolve(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, found_city,
            )
            db = await _fresh_db()
            char1, _, _, _, _ = await _full_setup(
                db, faction_code="org_a")
            await found_city(db, char1, "Recycled Name")
            await dissolve_city(db, char1, "Recycled Name")
            # Another org takes the freed name
            char2, _, _, _, _ = await _full_setup(
                db, faction_code="org_b")
            ok, _ = await found_city(db, char2, "Recycled Name")
            self.assertTrue(ok)
        _run(_t())


# ─── 29. get_city_for_room (post-found) ───────────────────────────────────

class TestGetCityForRoomHqRoom(unittest.TestCase):
    def test_hq_room_resolves_to_city(self):
        async def _t():
            from engine.player_cities import (
                found_city, get_city_for_room,
            )
            db = await _fresh_db()
            char, _, _, _, hq_room_ids = await _full_setup(db)
            await found_city(db, char, "Test City")
            city = await get_city_for_room(db, hq_room_ids[0])
            self.assertIsNotNone(city)
            self.assertEqual(city["name"], "Test City")
        _run(_t())

    def test_non_city_room_returns_none(self):
        async def _t():
            from engine.player_cities import (
                found_city, get_city_for_room,
            )
            db = await _fresh_db()
            char, _, _, zone_id, _ = await _full_setup(db)
            await found_city(db, char, "Test City")
            # Create an orphan room in the same zone
            orphan = await _seed_room(db, zone_id, "Orphan")
            self.assertIsNone(await get_city_for_room(db, orphan))
        _run(_t())


# ─── 30-35. Parser layer ──────────────────────────────────────────────────

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


class TestParserRegistration(unittest.TestCase):
    def test_city_registered(self):
        from parser.city_commands import register_city_commands
        from parser.commands import CommandRegistry

        reg = CommandRegistry()
        register_city_commands(reg)
        cmd = reg.get("+city")
        self.assertIsNotNone(cmd)
        self.assertEqual(cmd.key, "+city")


class TestParserBareHelp(unittest.TestCase):
    def test_bare_city_shows_phase_guide(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Phase", text)
            self.assertIn("found", text.lower())
        _run(_t())


class TestParserPhasePlaceholders(unittest.TestCase):
    def test_claim_subcommand_shipped_in_phase_2(self):
        """Phase 2 (cities_phase2 drop, May 22 2026) moved
        +city claim out of the placeholder list. This test was
        originally written against Phase 1's placeholder echo;
        re-purposed to assert the bare-help advertises claim as
        live."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city claim", text)
        _run(_t())

    def test_info_subcommand_shipped_in_phase_3(self):
        """Phase 3 (cities_phase3 drop, May 22 2026) moved +city info
        out of the placeholder list. This test was originally written
        against Phase 1's placeholder echo asserting 'Phase 3' would
        appear in the output; re-purposed to assert the bare-help
        advertises info as live, mirroring the May 22 Phase 2
        re-purpose discipline (pinned-keyset on umbrella surfaces is
        the canonical signal that the public contract changed)."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city info", text)
        _run(_t())

    def test_tax_subcommand_shipped_in_phase_4(self):
        """Phase 4 (cities_phase4 drop, May 22 2026) moved +city tax
        out of the placeholder list. This test was originally
        written against Phase 3's placeholder echo expecting
        'Phase 4' to appear in the output; re-purposed to assert
        the bare-help advertises tax as live, mirroring the May 22
        Phase 2 and Phase 3 re-purpose discipline (pinned-keyset on
        umbrella surfaces is the canonical signal that the public
        contract changed)."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city tax", text)
        _run(_t())


class TestParserFoundDispatch(unittest.TestCase):
    def test_found_happy_path_writes_to_db(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_name
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city",
                           "found Veiled Hand Compound")
            await CityCommand().execute(ctx)
            # Engine result reaches session
            text = "\n".join(session.sent)
            self.assertIn("Veiled Hand Compound", text)
            # And the city is now in the DB
            city = await get_city_by_name(db, "Veiled Hand Compound")
            self.assertIsNotNone(city)
        _run(_t())

    def test_found_no_args_shows_usage(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "found")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Usage", text)
        _run(_t())


class TestParserDissolveDispatch(unittest.TestCase):
    def test_dissolve_after_found_works(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import (
                found_city, get_city_by_name,
            )
            db = await _fresh_db()
            char, _, _, _, _ = await _full_setup(db)
            await found_city(db, char, "Doomed City")
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city",
                           "dissolve Doomed City")
            await CityCommand().execute(ctx)
            self.assertIsNone(await get_city_by_name(db, "Doomed City"))
        _run(_t())


class TestParserAccessDenied(unittest.TestCase):
    def test_no_character_rejected(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            session = _FakeSession(character=None)
            ctx = _ctx_for(session, db, "+city", "found Anything")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("must be in the game", text.lower())
        _run(_t())


if __name__ == "__main__":
    unittest.main()
