# -*- coding: utf-8 -*-
"""
tests/test_cities_phase5.py — Player Cities Phase 5 (May 22 2026).

Per ``player_cities_design_v1_2.md`` §6 (citizen benefits) and the
four May 22 Phase 5 design calls captured in the engine module
docstring:
  1. "Same planet" → "same zone" (zones don't have planet attr yet)
  2. 30%-cap on citizen_only counts only non-HQ rooms
  3. +city home cooldown durable across logout (attributes JSON)
  4. Rest bonus MECHANIC not shipped (only the read seam)

Test sections
=============

  1.  TestPhase5Constants                  — CITY_HOME_COOLDOWN_SECONDS, etc.

  2.  TestIsCitizen                        — role matrix → bool
  3.  TestIsRestBonusRoom                  — citizen-in-city True, others False

  4.  TestCanEnterCityRoom                 — non-citizen-only room → open
  5.  TestCanEnterCityRoomCitizenOnly      — citizen-only + citizen → open
  6.  TestCanEnterCityRoomBlocksOutsider   — citizen-only + outsider → blocked
  7.  TestCanEnterCityRoomBlocksGuest      — citizen-only + guest → blocked
  8.  TestCanEnterCityRoomBlocksBanished   — citizen-only + banished → blocked

  9.  TestApplyCityUpgradeContestedSecured  — citizen in contested → SECURED
 10.  TestApplyCityUpgradeLawlessContested  — citizen in lawless → CONTESTED
 11.  TestApplyCityUpgradeNonCitizen        — outsider → no upgrade
 12.  TestApplyCityUpgradeSecuredStays      — already SECURED → SECURED
 13.  TestGetEffectiveSecurityEndToEnd      — full chain: citizen in contested
                                              city room → SECURED via
                                              get_effective_security

 14.  TestSetRoomCitizenOnlyCap            — 30%-cap enforced on non-HQ rooms
 15.  TestSetRoomCitizenOnlyHQExempt       — HQ rooms always allowed (cap-exempt)
 16.  TestSetRoomCitizenOnlySmallCityMin   — min-1 allowed even at small N
 17.  TestSetRoomCitizenOnlyClearAlwaysOK  — clearing the flag is always OK

 18.  TestCanUseCityHomeIndependent        — char with no faction → blocked
 19.  TestCanUseCityHomeNoCity             — org has no city → blocked
 20.  TestCanUseCityHomeNotCitizen         — banished citizen → blocked
 21.  TestCanUseCityHomeInCombat           — in_combat attribute → blocked
 22.  TestCanUseCityHomeInSpace            — no zone (ship) → blocked
 23.  TestCanUseCityHomeDifferentZone      — different zone → blocked
 24.  TestCanUseCityHomeCooldown           — recent use → blocked with time
 25.  TestCanUseCityHomeHappyPath          — citizen, same zone, no cooldown → ok

 26.  TestRecordCityHomeUse                — stamps attributes JSON

 27.  TestParserCityHomeHappyPath          — full parser flow: teleport + look
 28.  TestParserCityHomeCooldownSurface    — cooldown rejection surfaces
 29.  TestParserCityHomeInSpace            — space rejection surfaces

 30.  TestPhase5LivePlaceholder            — bare-help advertises +city home
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


# ─── Shared fixtures (parallel to Phase 4) ───────────────────────────────


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


async def _seed_zone(
    db, name: str, security: str | None = "contested",
) -> int:
    props = "{}" if security is None else json.dumps({"security": security})
    cur = await db._db.execute(
        "INSERT INTO zones (name, properties) VALUES (?, ?)",
        (name, props),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_room(db, zone_id: int, name: str = "Room") -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
        "VALUES (?, ?, '', '')",
        (name, zone_id),
    )
    await db._db.commit()
    return cur.lastrowid


async def _seed_char(
    db, name: str, faction_id: str = "",
    room_id: int | None = None, credits: int = 100_000,
) -> dict:
    await _seed_account(db)
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(account_id, name, species, room_id, credits, faction_id) "
        "VALUES (1, ?, 'Human', ?, ?, ?)",
        (name, room_id or 1, credits, faction_id),
    )
    await db._db.commit()
    return await db.get_character(cur.lastrowid)


async def _seed_org(
    db, code: str, name: str, treasury: int = 100_000,
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
) -> int:
    now = time.time()
    cur = await db._db.execute(
        "INSERT INTO player_housing "
        "(char_id, tier, housing_type, entry_room_id, room_ids, "
        " storage, storage_max, weekly_rent, deposit, "
        " purchase_price, rent_paid_until, door_direction, "
        " faction_code, created_at, last_activity) "
        "VALUES (?, 5, 'org_hq', ?, ?, '[]', 100, 500, 0, 50000, ?, "
        " 'in', ?, ?, ?)",
        (1, entry_room_id, json.dumps(room_ids),
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
    zone_security: str = "contested",
):
    """Build a founded city with founder, citizen, outsider, guest,
    and a separate outside_room in a different zone. Returns a
    dict with all the handles tests need."""
    from engine.player_cities import found_city, get_city_by_org

    await _seed_account(db)
    zone_id = await _seed_zone(db, "Test Zone", zone_security)
    entry_room_id = await _seed_room(db, zone_id, "HQ Entry")
    hq_room_ids = []
    for i in range(4):
        rid = await _seed_room(db, zone_id, f"HQ Room {i}")
        hq_room_ids.append(rid)

    # Outside-zone room for cross-zone tests
    outside_zone = await _seed_zone(
        db, "Other Zone", "contested",
    )
    outside_room = await _seed_room(db, outside_zone, "Outside")

    org = await _seed_org(db, faction_code, "Test Org",
                           treasury=125_000)
    founder = await _seed_char(
        db, f"Founder_{faction_code}",
        faction_id=faction_code, room_id=entry_room_id,
    )
    await _seed_membership(db, founder["id"], org["id"], 5)
    await _seed_hq(db, faction_code, entry_room_id, hq_room_ids)
    await _seed_influence(db, faction_code, zone_id, 75)

    citizen = await _seed_char(
        db, f"Citizen_{faction_code}",
        faction_id=faction_code, room_id=entry_room_id,
    )
    await _seed_membership(db, citizen["id"], org["id"], 2)

    outsider = await _seed_char(
        db, f"Outsider_{faction_code}",
        faction_id="", room_id=entry_room_id,
    )

    guest = await _seed_char(
        db, f"Guest_{faction_code}",
        faction_id="", room_id=entry_room_id,
    )

    ok, msg = await found_city(
        db, founder, f"City-{faction_code.replace('_', '-')}",
    )
    assert ok, f"setup failed in found_city: {msg}"

    city = await get_city_by_org(db, org["id"])
    org = await db.get_organization(faction_code)

    return {
        "founder": founder,
        "citizen": citizen,
        "outsider": outsider,
        "guest": guest,
        "org": org,
        "city": city,
        "zone_id": zone_id,
        "outside_zone": outside_zone,
        "hq_room_ids": hq_room_ids,
        "hq_entry_id": entry_room_id,
        "outside_room": outside_room,
    }


async def _add_expansion_rooms(db, ctx, count: int) -> list[int]:
    """Add `count` expansion rooms to the city (non-HQ, is_center=0).

    Uses direct INSERT into player_city_rooms to skip the
    claim_room_for_city validation pipeline (we already have a
    founded city). Returns the new room ids.
    """
    new_ids = []
    for i in range(count):
        rid = await _seed_room(
            db, ctx["zone_id"], f"Expansion {i}",
        )
        await db._db.execute(
            "INSERT INTO player_city_rooms "
            "(city_id, room_id, is_center, citizen_only, "
            " claimed_at) "
            "VALUES (?, ?, 0, 0, ?)",
            (int(ctx["city"]["id"]), rid, time.time()),
        )
        new_ids.append(rid)
    await db._db.commit()
    return new_ids


# ─── 1. Constants ────────────────────────────────────────────────────────


class TestPhase5Constants(unittest.TestCase):
    def test_cooldown_one_hour(self):
        from engine.player_cities import CITY_HOME_COOLDOWN_SECONDS
        self.assertEqual(CITY_HOME_COOLDOWN_SECONDS, 60 * 60)

    def test_citizen_only_max_fraction(self):
        from engine.player_cities import CITIZEN_ONLY_MAX_FRACTION
        self.assertEqual(CITIZEN_ONLY_MAX_FRACTION, 0.30)


# ─── 2. is_citizen ───────────────────────────────────────────────────────


class TestIsCitizen(unittest.TestCase):
    def test_role_matrix(self):
        async def _t():
            from engine.player_cities import is_citizen, banish_player
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            city = ctx["city"]

            self.assertTrue(
                await is_citizen(db, ctx["founder"], city),
            )
            self.assertTrue(
                await is_citizen(db, ctx["citizen"], city),
            )
            self.assertFalse(
                await is_citizen(db, ctx["outsider"], city),
            )

            # Banish the citizen → no longer is_citizen
            ok, _ = await banish_player(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok)
            citizen2 = await db.get_character(ctx["citizen"]["id"])
            self.assertFalse(
                await is_citizen(db, citizen2, city),
            )
        _run(_t())


# ─── 3. is_rest_bonus_room ───────────────────────────────────────────────


class TestIsRestBonusRoom(unittest.TestCase):
    def test_citizen_in_city_room_true(self):
        async def _t():
            from engine.player_cities import is_rest_bonus_room
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Founder is a citizen; one of the HQ rooms IS a city room
            self.assertTrue(
                await is_rest_bonus_room(
                    db, ctx["founder"], ctx["hq_room_ids"][0],
                ),
            )
        _run(_t())

    def test_non_citizen_in_city_room_false(self):
        async def _t():
            from engine.player_cities import is_rest_bonus_room
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            self.assertFalse(
                await is_rest_bonus_room(
                    db, ctx["outsider"], ctx["hq_room_ids"][0],
                ),
            )
        _run(_t())

    def test_citizen_outside_any_city_false(self):
        async def _t():
            from engine.player_cities import is_rest_bonus_room
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            self.assertFalse(
                await is_rest_bonus_room(
                    db, ctx["founder"], ctx["outside_room"],
                ),
            )
        _run(_t())


# ─── 4-8. can_enter_city_room ────────────────────────────────────────────


class TestCanEnterCityRoom(unittest.TestCase):
    def test_non_citizen_only_room_open(self):
        async def _t():
            from engine.player_cities import can_enter_city_room
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # HQ rooms are NOT citizen_only by default (Phase 3
            # `citizenroom on/off` is what sets the flag).
            ok, _ = await can_enter_city_room(
                db, ctx["outsider"], ctx["hq_room_ids"][0],
            )
            self.assertTrue(ok)
        _run(_t())


class TestCanEnterCityRoomCitizenOnly(unittest.TestCase):
    def test_citizen_allowed(self):
        async def _t():
            from engine.player_cities import (
                can_enter_city_room, set_room_citizen_only,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            target_room = ctx["hq_room_ids"][0]
            # Flag the HQ room as citizen_only
            ok, _ = await set_room_citizen_only(
                db, ctx["founder"], target_room, True,
            )
            self.assertTrue(ok)
            ok2, _ = await can_enter_city_room(
                db, ctx["founder"], target_room,
            )
            self.assertTrue(ok2)
        _run(_t())


class TestCanEnterCityRoomBlocksOutsider(unittest.TestCase):
    def test_outsider_blocked(self):
        async def _t():
            from engine.player_cities import (
                can_enter_city_room, set_room_citizen_only,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            target = ctx["hq_room_ids"][0]
            await set_room_citizen_only(
                db, ctx["founder"], target, True,
            )
            ok, reason = await can_enter_city_room(
                db, ctx["outsider"], target,
            )
            self.assertFalse(ok)
            self.assertIn("citizens", reason.lower())
        _run(_t())


class TestCanEnterCityRoomBlocksGuest(unittest.TestCase):
    def test_guest_blocked(self):
        """Per design §6.3: guests are NOT citizens for the citizen-
        only room check. They get safety/movement but not access
        to private rooms."""
        async def _t():
            from engine.player_cities import (
                can_enter_city_room, set_room_citizen_only,
                add_guest,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            target = ctx["hq_room_ids"][0]
            await set_room_citizen_only(
                db, ctx["founder"], target, True,
            )
            # Add guest
            await add_guest(
                db, ctx["founder"], ctx["guest"]["id"],
            )
            ok, reason = await can_enter_city_room(
                db, ctx["guest"], target,
            )
            self.assertFalse(ok)
            self.assertIn("citizens", reason.lower())
        _run(_t())


class TestCanEnterCityRoomBlocksBanished(unittest.TestCase):
    def test_banished_blocked(self):
        async def _t():
            from engine.player_cities import (
                can_enter_city_room, set_room_citizen_only,
                banish_player,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            target = ctx["hq_room_ids"][0]
            await set_room_citizen_only(
                db, ctx["founder"], target, True,
            )
            # Banish the citizen
            await banish_player(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            citizen2 = await db.get_character(ctx["citizen"]["id"])
            ok, _ = await can_enter_city_room(
                db, citizen2, target,
            )
            self.assertFalse(ok)
        _run(_t())


# ─── 9-13. _apply_city_upgrade (security) ────────────────────────────────


class TestApplyCityUpgradeContestedSecured(unittest.TestCase):
    def test_contested_citizen_secured(self):
        async def _t():
            from engine.security import (
                _apply_city_upgrade, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            result = await _apply_city_upgrade(
                SecurityLevel.CONTESTED,
                ctx["hq_room_ids"][0],
                ctx["founder"], db,
            )
            self.assertEqual(result, SecurityLevel.SECURED)
        _run(_t())


class TestApplyCityUpgradeLawlessContested(unittest.TestCase):
    def test_lawless_citizen_contested(self):
        async def _t():
            from engine.security import (
                _apply_city_upgrade, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db, zone_security="lawless")
            result = await _apply_city_upgrade(
                SecurityLevel.LAWLESS,
                ctx["hq_room_ids"][0],
                ctx["founder"], db,
            )
            self.assertEqual(result, SecurityLevel.CONTESTED)
        _run(_t())


class TestApplyCityUpgradeNonCitizen(unittest.TestCase):
    def test_outsider_no_upgrade(self):
        async def _t():
            from engine.security import (
                _apply_city_upgrade, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            result = await _apply_city_upgrade(
                SecurityLevel.CONTESTED,
                ctx["hq_room_ids"][0],
                ctx["outsider"], db,
            )
            self.assertEqual(result, SecurityLevel.CONTESTED)
        _run(_t())


class TestApplyCityUpgradeSecuredStays(unittest.TestCase):
    def test_already_secured_unchanged(self):
        async def _t():
            from engine.security import (
                _apply_city_upgrade, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            result = await _apply_city_upgrade(
                SecurityLevel.SECURED,
                ctx["hq_room_ids"][0],
                ctx["founder"], db,
            )
            self.assertEqual(result, SecurityLevel.SECURED)
        _run(_t())


class TestGetEffectiveSecurityEndToEnd(unittest.TestCase):
    def test_citizen_in_contested_city_gets_secured(self):
        """Full chain test: citizen calls get_effective_security on
        an HQ room in a contested zone → SECURED."""
        async def _t():
            from engine.security import (
                get_effective_security, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db, zone_security="contested")
            result = await get_effective_security(
                ctx["hq_room_ids"][0], db, ctx["founder"],
            )
            self.assertEqual(result, SecurityLevel.SECURED)
        _run(_t())

    def test_outsider_in_contested_city_stays_contested(self):
        async def _t():
            from engine.security import (
                get_effective_security, SecurityLevel,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db, zone_security="contested")
            result = await get_effective_security(
                ctx["hq_room_ids"][0], db, ctx["outsider"],
            )
            self.assertEqual(result, SecurityLevel.CONTESTED)
        _run(_t())


# ─── 14-17. set_room_citizen_only 30%-cap ────────────────────────────────


class TestSetRoomCitizenOnlyCap(unittest.TestCase):
    def test_cap_enforced_on_non_hq(self):
        """Add 10 expansion rooms (so the cap is max(1, 3) = 3),
        then flag 3 OK + 4th rejected."""
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            exp = await _add_expansion_rooms(db, ctx, 10)
            # 30% of 10 = 3
            for i in range(3):
                ok, msg = await set_room_citizen_only(
                    db, ctx["founder"], exp[i], True,
                )
                self.assertTrue(ok, msg)
            # 4th should be rejected
            ok, msg = await set_room_citizen_only(
                db, ctx["founder"], exp[3], True,
            )
            self.assertFalse(ok)
            self.assertIn("30%", msg)
        _run(_t())


class TestSetRoomCitizenOnlyHQExempt(unittest.TestCase):
    def test_all_4_hq_rooms_can_flag(self):
        """All 4 HQ rooms can be flagged citizen_only without
        consuming the 30% non-HQ cap (HQ rooms are exempt)."""
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            for rid in ctx["hq_room_ids"]:
                ok, msg = await set_room_citizen_only(
                    db, ctx["founder"], rid, True,
                )
                self.assertTrue(ok, msg)
        _run(_t())


class TestSetRoomCitizenOnlySmallCityMin(unittest.TestCase):
    def test_min_one_allowed_even_at_two_rooms(self):
        """With 2 expansion rooms, 30% = 0 rounded; min-1 should
        still allow flagging exactly one."""
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            exp = await _add_expansion_rooms(db, ctx, 2)
            # max(1, int(0.3 * 2)) = max(1, 0) = 1
            ok, msg = await set_room_citizen_only(
                db, ctx["founder"], exp[0], True,
            )
            self.assertTrue(ok, msg)
            # 2nd rejected
            ok2, _ = await set_room_citizen_only(
                db, ctx["founder"], exp[1], True,
            )
            self.assertFalse(ok2)
        _run(_t())


class TestSetRoomCitizenOnlyClearAlwaysOK(unittest.TestCase):
    def test_clear_flag_always_succeeds(self):
        """Clearing the flag never triggers the cap check."""
        async def _t():
            from engine.player_cities import set_room_citizen_only
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            exp = await _add_expansion_rooms(db, ctx, 10)
            # Cap at max(1, 3) = 3
            for i in range(3):
                await set_room_citizen_only(
                    db, ctx["founder"], exp[i], True,
                )
            # Clear one — always allowed
            ok, msg = await set_room_citizen_only(
                db, ctx["founder"], exp[0], False,
            )
            self.assertTrue(ok, msg)
        _run(_t())


# ─── 18-25. can_use_city_home ────────────────────────────────────────────


class TestCanUseCityHomeIndependent(unittest.TestCase):
    def test_no_faction_rejected(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            ok, dest, reason = await can_use_city_home(
                db, ctx["outsider"],
            )
            self.assertFalse(ok)
            self.assertIn("member", reason.lower())
        _run(_t())


class TestCanUseCityHomeNoCity(unittest.TestCase):
    def test_org_without_city_rejected(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            # Org without a city
            await _seed_account(db)
            zone_id = await _seed_zone(db, "Z", "contested")
            room_id = await _seed_room(db, zone_id, "R")
            org = await _seed_org(db, "no_city_org", "No City Org")
            char = await _seed_char(
                db, "NoCityChar", faction_id="no_city_org",
                room_id=room_id,
            )
            await _seed_membership(db, char["id"], org["id"], 3)
            ok, _, reason = await can_use_city_home(db, char)
            self.assertFalse(ok)
            self.assertIn("no active city", reason.lower())
        _run(_t())


class TestCanUseCityHomeNotCitizen(unittest.TestCase):
    def test_banished_rejected(self):
        async def _t():
            from engine.player_cities import (
                can_use_city_home, banish_player,
            )
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Banish the citizen — banishment supersedes membership
            await banish_player(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            citizen2 = await db.get_character(ctx["citizen"]["id"])
            ok, _, reason = await can_use_city_home(db, citizen2)
            self.assertFalse(ok)
            self.assertIn("not a citizen", reason.lower())
        _run(_t())


class TestCanUseCityHomeInCombat(unittest.TestCase):
    def test_in_combat_attr_blocks(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Set in_combat attribute on the founder
            await db.execute(
                "UPDATE characters SET attributes = ? "
                "WHERE id = ?",
                (json.dumps({"in_combat": True}),
                 ctx["founder"]["id"]),
            )
            await db.commit()
            char = await db.get_character(ctx["founder"]["id"])
            ok, _, reason = await can_use_city_home(db, char)
            self.assertFalse(ok)
            self.assertIn("combat", reason.lower())
        _run(_t())


class TestCanUseCityHomeInSpace(unittest.TestCase):
    def test_no_zone_room_blocks(self):
        """A character in a room without a zone_id is treated as
        being on a ship/in space."""
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Create a zoneless room (NULL zone_id)
            cur = await db._db.execute(
                "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
                "VALUES ('Ship Bridge', NULL, '', '')"
            )
            await db._db.commit()
            space_room = cur.lastrowid
            await db.save_character(
                ctx["founder"]["id"], room_id=space_room,
            )
            char = await db.get_character(ctx["founder"]["id"])
            ok, _, reason = await can_use_city_home(db, char)
            self.assertFalse(ok)
            self.assertIn("ship", reason.lower())
        _run(_t())


class TestCanUseCityHomeDifferentZone(unittest.TestCase):
    def test_other_zone_blocks(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Move founder to the outside zone
            await db.save_character(
                ctx["founder"]["id"], room_id=ctx["outside_room"],
            )
            char = await db.get_character(ctx["founder"]["id"])
            ok, _, reason = await can_use_city_home(db, char)
            self.assertFalse(ok)
            self.assertIn("same zone", reason.lower())
        _run(_t())


class TestCanUseCityHomeCooldown(unittest.TestCase):
    def test_recent_use_blocks(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Stamp last_city_home to 5 minutes ago
            five_min_ago = time.time() - 300
            await db.execute(
                "UPDATE characters SET attributes = ? "
                "WHERE id = ?",
                (json.dumps({"last_city_home": five_min_ago}),
                 ctx["founder"]["id"]),
            )
            await db.commit()
            char = await db.get_character(ctx["founder"]["id"])
            ok, _, reason = await can_use_city_home(db, char)
            self.assertFalse(ok)
            self.assertIn("recent", reason.lower())
        _run(_t())


class TestCanUseCityHomeHappyPath(unittest.TestCase):
    def test_citizen_same_zone_no_cooldown_ok(self):
        async def _t():
            from engine.player_cities import can_use_city_home
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Founder is already in the entry room, same zone
            char = ctx["founder"]
            ok, dest, _ = await can_use_city_home(db, char)
            self.assertTrue(ok)
            self.assertEqual(dest, ctx["hq_entry_id"])
        _run(_t())


# ─── 26. record_city_home_use ────────────────────────────────────────────


class TestRecordCityHomeUse(unittest.TestCase):
    def test_stamps_attributes_json(self):
        async def _t():
            from engine.player_cities import record_city_home_use
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            char = ctx["founder"]
            await record_city_home_use(db, char)
            char2 = await db.get_character(char["id"])
            attrs = json.loads(char2.get("attributes") or "{}")
            self.assertIn("last_city_home", attrs)
            self.assertGreater(
                float(attrs["last_city_home"]),
                time.time() - 5,
            )
        _run(_t())


# ─── 27-29. Parser +city home ────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 0, "is_builder": 0}
        self.sent: list[str] = []
    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def __init__(self):
        self._registry = None
    def find_by_character(self, char_id):
        return None
    async def broadcast_to_room(self, *_, **__):
        pass


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


class TestParserCityHomeHappyPath(unittest.TestCase):
    def test_teleport_succeeds(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Move founder to an HQ room (not the doorstep — we
            # want a "different" starting room from dest so we can
            # confirm the teleport moved them)
            await db.save_character(
                ctx["founder"]["id"], room_id=ctx["hq_room_ids"][2],
            )
            char = await db.get_character(ctx["founder"]["id"])
            session = _FakeSession(character=char)
            cctx = _ctx_for(session, db, "+city", "home")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            # Should say "make your way" (or contain entry room name)
            self.assertIn("make your way", text.lower())
            # Char's room should now be the entry room
            char2 = await db.get_character(char["id"])
            self.assertEqual(
                int(char2["room_id"]), int(ctx["hq_entry_id"]),
            )
            # last_city_home stamped
            attrs = json.loads(char2.get("attributes") or "{}")
            self.assertIn("last_city_home", attrs)
        _run(_t())


class TestParserCityHomeCooldownSurface(unittest.TestCase):
    def test_cooldown_surfaces_to_player(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Stamp cooldown
            await db.execute(
                "UPDATE characters SET attributes = ? "
                "WHERE id = ?",
                (json.dumps({"last_city_home": time.time() - 60}),
                 ctx["founder"]["id"]),
            )
            await db.commit()
            char = await db.get_character(ctx["founder"]["id"])
            session = _FakeSession(character=char)
            cctx = _ctx_for(session, db, "+city", "home")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("recent", text.lower())
        _run(_t())


class TestParserCityHomeInSpace(unittest.TestCase):
    def test_in_space_surfaces_to_player(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            # Move founder to a zoneless room (simulates ship)
            cur = await db._db.execute(
                "INSERT INTO rooms (name, zone_id, desc_short, desc_long) "
                "VALUES ('Bridge', NULL, '', '')"
            )
            await db._db.commit()
            await db.save_character(
                ctx["founder"]["id"], room_id=cur.lastrowid,
            )
            char = await db.get_character(ctx["founder"]["id"])
            session = _FakeSession(character=char)
            cctx = _ctx_for(session, db, "+city", "home")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("ship", text.lower())
        _run(_t())


# ─── 30. Phase membership ────────────────────────────────────────────────


class TestPhase5LivePlaceholder(unittest.TestCase):
    def test_home_subcommand_shipped_in_phase_5(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_founded_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city home", text)
        _run(_t())


if __name__ == "__main__":
    unittest.main()
