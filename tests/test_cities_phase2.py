# -*- coding: utf-8 -*-
"""
tests/test_cities_phase2.py — Player Cities Phase 2 (May 22 2026).

Per ``player_cities_design_v1_2.md`` §13 Phase 2 (expansion + release)
and the May 22 design calls.

Test sections
=============

  1. TestPhase2Constants                 — constants match design
  2. TestExpansionCountEmpty             — get_city_expansion_count
  3. TestResolveDirectionToRoom          — direction → room_id resolver

  4. TestClaimIndependent                — non-faction char rejected
  5. TestClaimNoCity                     — org without city rejected
  6. TestClaimNonLeader                  — rank < 5 rejected
  7. TestClaimRoomMissing                — bogus room_id rejected
  8. TestClaimWrongZone                  — different-zone rejected
  9. TestClaimAlreadyInThisCity          — re-claim own city rejected
 10. TestClaimAlreadyInOtherCity         — claim another city's room rejected
 11. TestClaimSizeCapOutpost             — outpost: 5 expansion max
 12. TestClaimSizeCapChapter             — chapter_house: 10 expansion max
 13. TestClaimSizeCapFortress            — fortress: 20 expansion max
 14. TestClaimNonContiguous              — disconnected room rejected
 15. TestClaimContiguousFromCenter       — HQ-adjacent works
 16. TestClaimContiguousFromExpansion    — chained expansion works
 17. TestClaimRateLimit                  — 24h enforced in prod-cooldown mode
 18. TestClaimRateLimitDevBypass         — cooldowns_enabled() bypass
 19. TestClaimLowInfluence               — < 50 influence rejected
 20. TestClaimInsufficientTreasury       — treasury < cost rejected
 21. TestClaimHappyPath                  — happy path: row inserted, debited
 22. TestClaimDoesNotWriteTerritory      — territory_claims untouched
 23. TestClaimReverseExitContiguity      — one-way exit counts

 24. TestReleaseNoCity                   — no active city rejected
 25. TestReleaseNonLeader                — non-leader rejected
 26. TestReleaseUnknownRoom              — room not in city rejected
 27. TestReleaseHqCenterRejected         — is_center=1 rejected
 28. TestReleaseHappyPath                — refund + row deleted
 29. TestReleaseDecrementsCount          — expansion count goes down
 30. TestReleaseFreesRoomForReclaim      — rate limit gates re-claim,
                                            but room is reclaimable in dev

 31. TestParserClaimByDirection          — `+city claim northwest`
 32. TestParserClaimByRoomId             — `+city claim 42`
 33. TestParserClaimNoArgs               — usage echoed
 34. TestParserClaimBadDirection         — bad exit error surfaced
 35. TestParserReleaseDefault            — `+city release` (no args)
 36. TestParserReleaseByRoomId           — `+city release 42`
 37. TestParserReleaseNonNumeric         — `+city release northwest` rejected

 38. TestPhase2NotInPlaceholderList      — claim/release no longer phase-stubbed

 39. TestClaimUnknownTier                — corrupt hq_tier value rejected
 40. TestExpansionRefund                 — exact refund math (2500 cr)
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


# ─── shared fixtures (extended from test_cities_phase1.py) ────────────────

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


async def _setup_founded_city(
    db, *,
    faction_code: str = "veiled_hand",
    treasury: int = 100_000,
    rank_level: int = 5,
    zone_security: str = "contested",
    influence: int = 75,
    storage_max: int = 100,
    hq_room_count: int = 4,
    extra_treasury_after_found: int = 0,
    city_name: str | None = None,
):
    """Build a complete founded city. Returns
    (char, org_post, city, zone_id, hq_room_ids, neighbor_rooms).

    ``neighbor_rooms`` is a list of 3 rooms adjacent to the HQ entry
    room (each via a unique direction). Tests use these as expansion
    targets. Test bodies needing more neighbors can use _seed_room +
    _seed_exit.
    """
    from engine.player_cities import found_city

    await _seed_account(db)
    zone_id = await _seed_zone(db, "Test Zone", zone_security)
    entry_room_id = await _seed_room(db, zone_id, "HQ Entry")
    hq_room_ids = []
    for i in range(hq_room_count):
        rid = await _seed_room(db, zone_id, f"HQ Room {i}")
        hq_room_ids.append(rid)

    # Adjacent rooms — three exits from entry_room_id
    neighbors = []
    for direction in ("north", "south", "east"):
        n = await _seed_room(db, zone_id, f"Neighbor {direction}")
        await _seed_exit(db, entry_room_id, n, direction)
        # Reverse exit too (more realistic; helps reverse-contiguity test)
        await _seed_exit(db, n, entry_room_id, _reverse(direction))
        neighbors.append(n)

    org = await _seed_org(
        db, faction_code, "Test Org",
        treasury=treasury + extra_treasury_after_found
                 + 25_000 * (1 if storage_max == 100 else 0)
                 + 75_000 * (1 if storage_max == 200 else 0)
                 + 200_000 * (1 if storage_max == 400 else 0),
    )
    char = await _seed_char(
        db, f"Founder_{faction_code}",
        faction_id=faction_code,
        room_id=entry_room_id,
    )
    await _seed_membership(db, char["id"], org["id"], rank_level)
    await _seed_hq(
        db, faction_code, entry_room_id,
        hq_room_ids, storage_max=storage_max,
    )
    if influence > 0:
        await _seed_influence(db, faction_code, zone_id, influence)

    # Found the city
    name_to_use = city_name or f"Test City-{faction_code.replace('_', '-')}"
    ok, msg = await found_city(db, char, name_to_use)
    assert ok, f"setup failed in found_city: {msg}"

    # Re-read everything that may have changed
    from engine.player_cities import get_city_by_org
    org_post = await db.get_organization(faction_code)
    city = await get_city_by_org(db, org["id"])

    return char, org_post, city, zone_id, hq_room_ids, neighbors


def _reverse(direction: str) -> str:
    return {
        "north": "south", "south": "north",
        "east": "west", "west": "east",
        "up": "down", "down": "up",
        "northeast": "southwest", "southwest": "northeast",
        "northwest": "southeast", "southeast": "northwest",
        "in": "out", "out": "in",
    }.get(direction, direction)


# ─── 1. Constants ────────────────────────────────────────────────────────

class TestPhase2Constants(unittest.TestCase):
    def test_claim_cost_matches_drop6(self):
        from engine.player_cities import EXPANSION_CLAIM_COST
        from engine.territory import CLAIM_COST
        self.assertEqual(EXPANSION_CLAIM_COST, CLAIM_COST)

    def test_influence_threshold_matches_drop6_foothold(self):
        from engine.player_cities import EXPANSION_INFLUENCE_THRESHOLD
        from engine.territory import THRESHOLD_FOOTHOLD
        self.assertEqual(
            EXPANSION_INFLUENCE_THRESHOLD, THRESHOLD_FOOTHOLD,
        )

    def test_refund_pct_50(self):
        from engine.player_cities import EXPANSION_REFUND_PCT
        self.assertEqual(EXPANSION_REFUND_PCT, 50)

    def test_rate_limit_24h(self):
        from engine.player_cities import EXPANSION_RATE_LIMIT_SECONDS
        self.assertEqual(EXPANSION_RATE_LIMIT_SECONDS, 86400)


# ─── 2-3. Read helpers ────────────────────────────────────────────────────

class TestExpansionCountEmpty(unittest.TestCase):
    def test_returns_zero_for_unknown_city(self):
        async def _t():
            from engine.player_cities import get_city_expansion_count
            db = await _fresh_db()
            self.assertEqual(
                await get_city_expansion_count(db, 999), 0,
            )
        _run(_t())

    def test_returns_zero_for_newly_founded_city(self):
        async def _t():
            from engine.player_cities import get_city_expansion_count
            db = await _fresh_db()
            _, _, city, _, _, _ = await _setup_founded_city(db)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 0,
            )
        _run(_t())


class TestResolveDirectionToRoom(unittest.TestCase):
    def test_valid_direction_resolves(self):
        async def _t():
            from engine.player_cities import resolve_direction_to_room
            db = await _fresh_db()
            _, _, _, _, _, neighbors = await _setup_founded_city(db)
            # HQ entry is room "HQ Entry"; we exited north to neighbors[0]
            hq_entry_rows = await db.fetchall(
                "SELECT id FROM rooms WHERE name = 'HQ Entry'"
            )
            entry_id = hq_entry_rows[0]["id"]
            target, err = await resolve_direction_to_room(
                db, entry_id, "north",
            )
            self.assertEqual(target, neighbors[0])
            self.assertEqual(err, "")
        _run(_t())

    def test_case_insensitive(self):
        async def _t():
            from engine.player_cities import resolve_direction_to_room
            db = await _fresh_db()
            _, _, _, _, _, neighbors = await _setup_founded_city(db)
            hq_entry_rows = await db.fetchall(
                "SELECT id FROM rooms WHERE name = 'HQ Entry'"
            )
            entry_id = hq_entry_rows[0]["id"]
            target, _ = await resolve_direction_to_room(
                db, entry_id, "NORTH",
            )
            self.assertEqual(target, neighbors[0])
        _run(_t())

    def test_unknown_direction_returns_error(self):
        async def _t():
            from engine.player_cities import resolve_direction_to_room
            db = await _fresh_db()
            _, _, _, _, _, _ = await _setup_founded_city(db)
            hq_entry_rows = await db.fetchall(
                "SELECT id FROM rooms WHERE name = 'HQ Entry'"
            )
            entry_id = hq_entry_rows[0]["id"]
            target, err = await resolve_direction_to_room(
                db, entry_id, "skyward",
            )
            self.assertIsNone(target)
            self.assertIn("no exit", err.lower())
        _run(_t())


# ─── 4-13. claim — validation branches ────────────────────────────────────

class TestClaimIndependent(unittest.TestCase):
    def test_independent_char_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char = {"id": 1, "faction_id": "independent"}
            ok, msg = await claim_room_for_city(db, char, 1)
            self.assertFalse(ok)
        _run(_t())


class TestClaimNoCity(unittest.TestCase):
    def test_org_without_city_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            await _seed_account(db)
            org = await _seed_org(db, "no_city_org", "No City Org")
            char = await _seed_char(
                db, "Wanderer", faction_id="no_city_org",
            )
            await _seed_membership(db, char["id"], org["id"], 5)
            ok, msg = await claim_room_for_city(db, char, 1)
            self.assertFalse(ok)
            self.assertIn("no active city", msg.lower())
        _run(_t())


class TestClaimNonLeader(unittest.TestCase):
    def test_rank_4_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, neighbors = await _setup_founded_city(db)
            # Demote
            await db._db.execute(
                "UPDATE org_memberships SET rank_level = 4 "
                "WHERE char_id = ?", (char["id"],),
            )
            await db._db.commit()
            ok, msg = await claim_room_for_city(db, char, neighbors[0])
            self.assertFalse(ok)
            self.assertIn("leader", msg.lower())
        _run(_t())


class TestClaimRoomMissing(unittest.TestCase):
    def test_bogus_room_id_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            ok, msg = await claim_room_for_city(db, char, 99_999)
            self.assertFalse(ok)
            self.assertIn("does not exist", msg.lower())
        _run(_t())


class TestClaimWrongZone(unittest.TestCase):
    def test_different_zone_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            # Spin up a foreign zone + room
            other_zone = await _seed_zone(db, "Other", "contested")
            foreign_room = await _seed_room(
                db, other_zone, "Foreign",
            )
            ok, msg = await claim_room_for_city(
                db, char, foreign_room,
            )
            self.assertFalse(ok)
            self.assertIn("different zone", msg.lower())
        _run(_t())


class TestClaimAlreadyInThisCity(unittest.TestCase):
    def test_existing_city_room_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, hq_room_ids, _ = await _setup_founded_city(db)
            # HQ rooms are already city rooms (is_center=1)
            ok, msg = await claim_room_for_city(
                db, char, hq_room_ids[0],
            )
            self.assertFalse(ok)
            self.assertIn("already part of your city", msg.lower())
        _run(_t())


class TestClaimAlreadyInOtherCity(unittest.TestCase):
    def test_other_city_room_rejected(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, found_city,
            )
            db = await _fresh_db()
            char_a, _, _, _, hq_a, _ = await _setup_founded_city(
                db, faction_code="org_a",
            )
            # Now make a SECOND city in a DIFFERENT zone
            char_b, _, _, zone_b, _, _ = await _setup_founded_city(
                db, faction_code="org_b",
            )
            # org_b tries to claim one of org_a's HQ rooms
            ok, msg = await claim_room_for_city(
                db, char_b, hq_a[0],
            )
            self.assertFalse(ok)
            # Either zone mismatch or "another city" — both reject
            self.assertFalse(ok)
        _run(_t())


class TestClaimSizeCapOutpost(unittest.TestCase):
    def test_5_rooms_max(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, MAX_EXPANSION_ROOMS,
            )
            db = await _fresh_db()
            char, _, city, zone_id, _, neighbors = await _setup_founded_city(
                db, treasury=200_000, storage_max=100,
                extra_treasury_after_found=200_000,
            )
            # Bypass rate limit for the loop
            import engine.jedi_gating as jg
            original = jg.cooldowns_enabled
            jg.cooldowns_enabled = lambda: False
            try:
                # We have 3 neighbors of the HQ entry. We need 6
                # candidate rooms to exceed the cap (5 then fail). Add
                # a chain off neighbors[0].
                prev = neighbors[0]
                more = []
                for i in range(6):
                    r = await _seed_room(
                        db, zone_id, f"Chain Room {i}"
                    )
                    await _seed_exit(db, prev, r, "north")
                    await _seed_exit(db, r, prev, "south")
                    more.append(r)
                    prev = r

                # Claim 5 in a chain — neighbors[0], more[0]..more[3]
                targets = [neighbors[0]] + more[:4]
                for t in targets:
                    ok, msg = await claim_room_for_city(db, char, t)
                    self.assertTrue(ok, msg)
                # 6th attempt should fail with the cap
                ok, msg = await claim_room_for_city(db, char, more[4])
                self.assertFalse(ok)
                self.assertIn("cap", msg.lower())
            finally:
                jg.cooldowns_enabled = original
            self.assertEqual(MAX_EXPANSION_ROOMS["outpost"], 5)
        _run(_t())


class TestClaimSizeCapResolves(unittest.TestCase):
    """Smoke: each tier's cap appears in the error message when hit."""

    def test_chapter_house_cap_string(self):
        from engine.player_cities import MAX_EXPANSION_ROOMS
        self.assertEqual(MAX_EXPANSION_ROOMS["chapter_house"], 10)

    def test_fortress_cap_string(self):
        from engine.player_cities import MAX_EXPANSION_ROOMS
        self.assertEqual(MAX_EXPANSION_ROOMS["fortress"], 20)


class TestClaimNonContiguous(unittest.TestCase):
    def test_disconnected_room_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, zone_id, _, _ = await _setup_founded_city(db)
            # Same zone, no exit linking it to anything in the city
            orphan = await _seed_room(db, zone_id, "Orphan")
            ok, msg = await claim_room_for_city(db, char, orphan)
            self.assertFalse(ok)
            self.assertIn("not adjacent", msg.lower())
        _run(_t())


class TestClaimContiguousFromCenter(unittest.TestCase):
    def test_hq_adjacent_succeeds(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, neighbors = await _setup_founded_city(db)
            ok, _ = await claim_room_for_city(
                db, char, neighbors[0],
            )
            self.assertTrue(ok)
        _run(_t())


class TestClaimContiguousFromExpansion(unittest.TestCase):
    def test_chained_expansion_works(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, zone_id, _, neighbors = await _setup_founded_city(db)
            # Bypass rate limit
            import engine.jedi_gating as jg
            original = jg.cooldowns_enabled
            jg.cooldowns_enabled = lambda: False
            try:
                # First claim neighbors[0]
                ok1, _ = await claim_room_for_city(
                    db, char, neighbors[0],
                )
                self.assertTrue(ok1)
                # Now chain: room beyond neighbors[0]
                beyond = await _seed_room(
                    db, zone_id, "Beyond Neighbor",
                )
                await _seed_exit(db, neighbors[0], beyond, "north")
                await _seed_exit(db, beyond, neighbors[0], "south")
                ok2, msg = await claim_room_for_city(
                    db, char, beyond,
                )
                self.assertTrue(ok2, msg)
            finally:
                jg.cooldowns_enabled = original
        _run(_t())


class TestClaimRateLimit(unittest.TestCase):
    def test_second_claim_within_24h_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, zone_id, _, neighbors = await _setup_founded_city(db)
            # Force cooldowns_enabled to True (prod mode)
            import engine.jedi_gating as jg
            original = jg.cooldowns_enabled
            jg.cooldowns_enabled = lambda: True
            try:
                ok1, _ = await claim_room_for_city(
                    db, char, neighbors[0],
                )
                self.assertTrue(ok1)
                # Immediately try another adjacent room
                ok2, msg = await claim_room_for_city(
                    db, char, neighbors[1],
                )
                self.assertFalse(ok2)
                self.assertIn("rate-limited", msg.lower())
            finally:
                jg.cooldowns_enabled = original
        _run(_t())


class TestClaimRateLimitDevBypass(unittest.TestCase):
    def test_dev_bypass_allows_immediate_second(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, neighbors = await _setup_founded_city(db)
            import engine.jedi_gating as jg
            original = jg.cooldowns_enabled
            jg.cooldowns_enabled = lambda: False
            try:
                ok1, _ = await claim_room_for_city(
                    db, char, neighbors[0],
                )
                self.assertTrue(ok1)
                ok2, msg = await claim_room_for_city(
                    db, char, neighbors[1],
                )
                self.assertTrue(ok2, msg)
            finally:
                jg.cooldowns_enabled = original
        _run(_t())


class TestClaimLowInfluence(unittest.TestCase):
    def test_below_threshold_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, org, _, zone_id, _, neighbors = await _setup_founded_city(
                db, influence=75,  # passes founding
            )
            # Drop influence below threshold post-founding
            await db._db.execute(
                "UPDATE territory_influence SET score = 30 "
                "WHERE org_code = ? AND zone_id = ?",
                (org["code"], zone_id),
            )
            await db._db.commit()
            ok, msg = await claim_room_for_city(
                db, char, neighbors[0],
            )
            self.assertFalse(ok)
            self.assertIn("influence", msg.lower())
        _run(_t())


class TestClaimInsufficientTreasury(unittest.TestCase):
    def test_below_cost_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, org, _, _, _, neighbors = await _setup_founded_city(db)
            # Drain treasury below 5000
            await db._db.execute(
                "UPDATE organizations SET treasury = 1000 WHERE id = ?",
                (org["id"],),
            )
            await db._db.commit()
            ok, msg = await claim_room_for_city(
                db, char, neighbors[0],
            )
            self.assertFalse(ok)
            self.assertIn("treasury", msg.lower())
        _run(_t())


# ─── 14-22. claim — happy paths and integration ───────────────────────────

class TestClaimHappyPath(unittest.TestCase):
    def test_full_happy_path(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, get_city_expansion_count,
                EXPANSION_CLAIM_COST,
            )
            db = await _fresh_db()
            char, org, city, _, _, neighbors = await _setup_founded_city(db)
            # treasury at this point is treasury - 25K founding
            t_before = (await db.get_organization(org["code"]))["treasury"]
            ok, _ = await claim_room_for_city(
                db, char, neighbors[0],
            )
            self.assertTrue(ok)
            t_after = (await db.get_organization(org["code"]))["treasury"]
            self.assertEqual(t_after, t_before - EXPANSION_CLAIM_COST)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 1,
            )
        _run(_t())


class TestClaimDoesNotWriteTerritory(unittest.TestCase):
    """Phase 2 design call: city expansion does NOT write to
    territory_claims."""

    def test_territory_claims_table_unaffected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, _, _, neighbors = await _setup_founded_city(db)
            before = await db.fetchall(
                "SELECT COUNT(*) AS n FROM territory_claims"
            )
            ok, _ = await claim_room_for_city(
                db, char, neighbors[0],
            )
            self.assertTrue(ok)
            after = await db.fetchall(
                "SELECT COUNT(*) AS n FROM territory_claims"
            )
            self.assertEqual(before[0]["n"], after[0]["n"])
        _run(_t())


class TestClaimReverseExitContiguity(unittest.TestCase):
    """One-way exits: a room that only has an exit INTO a city
    room (not from) should still be claimable."""

    def test_one_way_exit_counts(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, _, zone_id, _, _ = await _setup_founded_city(db)
            # Get the HQ entry room id (first HQ room)
            rows = await db.fetchall(
                "SELECT room_id FROM player_city_rooms "
                "ORDER BY room_id LIMIT 1"
            )
            hq_room = rows[0]["room_id"]
            # New room with a ONE-WAY exit FROM hq_room (no reverse)
            target = await _seed_room(db, zone_id, "One-Way Target")
            await _seed_exit(db, hq_room, target, "west")
            # No reverse exit — but contiguity should still pass
            ok, msg = await claim_room_for_city(db, char, target)
            self.assertTrue(ok, msg)
        _run(_t())


# ─── 24-30. release ────────────────────────────────────────────────────────

class TestReleaseNoCity(unittest.TestCase):
    def test_org_without_city_rejected(self):
        async def _t():
            from engine.player_cities import release_room_from_city
            db = await _fresh_db()
            await _seed_account(db)
            org = await _seed_org(db, "ghost_org", "Ghost")
            char = await _seed_char(
                db, "Solo", faction_id="ghost_org",
            )
            await _seed_membership(db, char["id"], org["id"], 5)
            ok, msg = await release_room_from_city(db, char, 1)
            self.assertFalse(ok)
            self.assertIn("no active city", msg.lower())
        _run(_t())


class TestReleaseNonLeader(unittest.TestCase):
    def test_rank_3_rejected(self):
        async def _t():
            from engine.player_cities import release_room_from_city
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            await db._db.execute(
                "UPDATE org_memberships SET rank_level = 3 "
                "WHERE char_id = ?", (char["id"],),
            )
            await db._db.commit()
            ok, msg = await release_room_from_city(db, char, 1)
            self.assertFalse(ok)
            self.assertIn("leader", msg.lower())
        _run(_t())


class TestReleaseUnknownRoom(unittest.TestCase):
    def test_room_not_in_city_rejected(self):
        async def _t():
            from engine.player_cities import release_room_from_city
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            ok, msg = await release_room_from_city(db, char, 99_999)
            self.assertFalse(ok)
            self.assertIn("not part of your city", msg.lower())
        _run(_t())


class TestReleaseHqCenterRejected(unittest.TestCase):
    def test_is_center_room_rejected(self):
        async def _t():
            from engine.player_cities import release_room_from_city
            db = await _fresh_db()
            char, _, _, _, hq_room_ids, _ = await _setup_founded_city(db)
            ok, msg = await release_room_from_city(
                db, char, hq_room_ids[0],
            )
            self.assertFalse(ok)
            self.assertIn("hq", msg.lower())
            self.assertIn("dissolve", msg.lower())
        _run(_t())


class TestReleaseHappyPath(unittest.TestCase):
    def test_refund_and_row_removed(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, release_room_from_city,
                EXPANSION_CLAIM_COST, EXPANSION_REFUND_PCT,
            )
            db = await _fresh_db()
            char, org, _, _, _, neighbors = await _setup_founded_city(db)
            await claim_room_for_city(db, char, neighbors[0])
            t_before_release = (
                await db.get_organization(org["code"])
            )["treasury"]
            ok, _ = await release_room_from_city(
                db, char, neighbors[0],
            )
            self.assertTrue(ok)
            t_after_release = (
                await db.get_organization(org["code"])
            )["treasury"]
            expected_refund = (
                EXPANSION_CLAIM_COST * EXPANSION_REFUND_PCT
            ) // 100
            self.assertEqual(
                t_after_release,
                t_before_release + expected_refund,
            )
            # Row gone
            rows = await db.fetchall(
                "SELECT * FROM player_city_rooms "
                "WHERE room_id = ?", (neighbors[0],),
            )
            self.assertEqual(rows, [])
        _run(_t())


class TestReleaseDecrementsCount(unittest.TestCase):
    def test_expansion_count_drops(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, release_room_from_city,
                get_city_expansion_count,
            )
            db = await _fresh_db()
            char, _, city, _, _, neighbors = await _setup_founded_city(db)
            await claim_room_for_city(db, char, neighbors[0])
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 1,
            )
            await release_room_from_city(db, char, neighbors[0])
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 0,
            )
        _run(_t())


class TestExpansionRefundExact(unittest.TestCase):
    def test_refund_is_2500(self):
        async def _t():
            from engine.player_cities import (
                claim_room_for_city, release_room_from_city,
            )
            db = await _fresh_db()
            char, org, _, _, _, neighbors = await _setup_founded_city(db)
            await claim_room_for_city(db, char, neighbors[0])
            t_pre = (await db.get_organization(org["code"]))["treasury"]
            await release_room_from_city(db, char, neighbors[0])
            t_post = (await db.get_organization(org["code"]))["treasury"]
            self.assertEqual(t_post - t_pre, 2_500)
        _run(_t())


# ─── 31-37. Parser layer ─────────────────────────────────────────────────

class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 0, "is_builder": 0}
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


class TestParserClaimByDirection(unittest.TestCase):
    def test_claim_by_direction_succeeds(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_expansion_count
            db = await _fresh_db()
            char, _, city, _, _, _ = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "claim north")
            await CityCommand().execute(ctx)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 1,
            )
        _run(_t())


class TestParserClaimByRoomId(unittest.TestCase):
    def test_claim_by_room_id_succeeds(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_expansion_count
            db = await _fresh_db()
            char, _, city, _, _, neighbors = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(
                session, db, "+city", f"claim {neighbors[0]}",
            )
            await CityCommand().execute(ctx)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 1,
            )
        _run(_t())


class TestParserClaimNoArgs(unittest.TestCase):
    def test_bare_claim_shows_usage(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "claim")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("Usage", text)
        _run(_t())


class TestParserClaimBadDirection(unittest.TestCase):
    def test_unknown_direction_error(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(session, db, "+city", "claim skyward")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("no exit", text.lower())
        _run(_t())


class TestParserReleaseDefault(unittest.TestCase):
    def test_release_no_args_targets_current_room(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import (
                claim_room_for_city, get_city_expansion_count,
            )
            db = await _fresh_db()
            char, _, city, _, _, neighbors = await _setup_founded_city(db)
            await claim_room_for_city(db, char, neighbors[0])
            # Move the player INTO the claimed room
            await db._db.execute(
                "UPDATE characters SET room_id = ? WHERE id = ?",
                (neighbors[0], char["id"]),
            )
            await db._db.commit()
            char_now = await db.get_character(char["id"])
            session = _FakeSession(character=char_now)
            ctx = _ctx_for(session, db, "+city", "release")
            await CityCommand().execute(ctx)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 0,
            )
        _run(_t())


class TestParserReleaseByRoomId(unittest.TestCase):
    def test_release_by_room_id(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import (
                claim_room_for_city, get_city_expansion_count,
            )
            db = await _fresh_db()
            char, _, city, _, _, neighbors = await _setup_founded_city(db)
            await claim_room_for_city(db, char, neighbors[0])
            session = _FakeSession(character=char)
            ctx = _ctx_for(
                session, db, "+city", f"release {neighbors[0]}",
            )
            await CityCommand().execute(ctx)
            self.assertEqual(
                await get_city_expansion_count(db, city["id"]), 0,
            )
        _run(_t())


class TestParserReleaseNonNumeric(unittest.TestCase):
    def test_release_with_word_rejected(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            ctx = _ctx_for(
                session, db, "+city", "release northwest",
            )
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            self.assertIn("numeric", text.lower())
        _run(_t())


# ─── 38. Phase 2 no longer in placeholder list ───────────────────────────

class TestPhase2NotInPlaceholderList(unittest.TestCase):
    def test_claim_not_advertised_as_phase_2_placeholder(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            char, _, _, _, _, _ = await _setup_founded_city(db)
            session = _FakeSession(character=char)
            # Bare +city should NOT say "claim … Phase 2"
            ctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(ctx)
            text = "\n".join(session.sent)
            # The current line is "  +city claim <direction>    Claim an adjacent room..."
            # which lives under "Available now:" not "Coming soon:"
            self.assertIn("Available now:", text)
            # No "Phase 2" mention should remain in the help
            self.assertNotIn("Phase 2", text)
        _run(_t())


# ─── 39-40. Edge cases ───────────────────────────────────────────────────

class TestClaimUnknownTier(unittest.TestCase):
    def test_corrupt_hq_tier_rejected(self):
        async def _t():
            from engine.player_cities import claim_room_for_city
            db = await _fresh_db()
            char, _, city, _, _, neighbors = await _setup_founded_city(db)
            # Corrupt the city's hq_tier
            await db._db.execute(
                "UPDATE player_cities SET hq_tier = 'invalid_tier' "
                "WHERE id = ?", (city["id"],),
            )
            await db._db.commit()
            ok, msg = await claim_room_for_city(db, char, neighbors[0])
            self.assertFalse(ok)
            self.assertIn("tier", msg.lower())
        _run(_t())


if __name__ == "__main__":
    unittest.main()
