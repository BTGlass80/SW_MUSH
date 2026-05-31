# -*- coding: utf-8 -*-
"""
tests/test_cities_phase4.py — Player Cities Phase 4 (May 22 2026).

Per ``player_cities_design_v1_2.md`` §5 (taxation) and §13 Phase 4,
plus the two May 22 design calls captured in the engine module
docstring (tax carved out of existing sinks, sabacc + NPC vendor
deferred to Phase 4b).

Test sections
=============

  1.  TestPhase4Constants                  — MIN_TAX_RATE, rollover seconds
  2.  TestSetTaxRateAuth                   — outsider/citizen rejected
  3.  TestSetTaxRateBounds                 — 0-cap range enforced
  4.  TestSetTaxRateRateCapCeiling         — cap-exceeded rejected
  5.  TestSetTaxRateAbsoluteCeiling        — > MAX_TAX_RATE rejected even on corrupt cap
  6.  TestSetTaxRateHappyPath              — DB row updated
  7.  TestSetTaxRateInvalidShape           — non-numeric rejected

  8.  TestSetRateCapFounderOnly            — Mayor (non-Founder) rejected
  9.  TestSetRateCapBounds                 — > MAX_TAX_RATE rejected
 10.  TestSetRateCapHappyPath              — cap stored
 11.  TestSetRateCapClampsCurrentRate      — rate > new cap → clamped
 12.  TestSetRateCapDoesNotClampIfBelow    — rate < new cap → no change

 13.  TestApplyCityTaxNoRoom               — invalid room_id → (0, None, None)
 14.  TestApplyCityTaxNoCity               — outside-city room → (0, None, None)
 15.  TestApplyCityTaxZeroRate             — 0% rate → (0, city_id, name)
 16.  TestApplyCityTaxMath                 — 5% of 1000 = 50
 17.  TestApplyCityTaxRoundsDown           — 5% of 19 = 0 (no negative-floor)
 18.  TestApplyCityTaxCreditsTreasury      — org treasury increments by exact take
 19.  TestApplyCityTaxIncrementsRevenue    — revenue_total/_week both += take
 20.  TestApplyCityTaxZeroGross            — non-positive gross → (0, None, None)

 21.  TestTickRevenueRolloverElapsed       — old week_start → revenue_week reset
 22.  TestTickRevenueRolloverFresh         — fresh week_start → unchanged
 23.  TestTickRevenueRolloverDissolvedSkipped  — dissolved cities skipped
 24.  TestTickRevenueRolloverTotalUnchanged    — revenue_total never resets

 25.  TestFormatCityTaxViewBasic           — view contains rate, cap, totals
 26.  TestFormatCityTaxViewEmptyState      — fresh city renders 0s cleanly

 27.  TestVendorDroidIntegrationTaxed      — sale in city → escrow reduced by tax
 28.  TestVendorDroidIntegrationUntaxed    — sale outside city → escrow unchanged
 29.  TestVendorDroidIntegrationTaxMessage — success message names city

 30.  TestBountyPostIntegrationTaxed       — post in city → city take credited
 31.  TestBountyPostIntegrationUntaxed     — post outside city → no take

 32.  TestParserTaxViewInCity              — view echoes rate + revenue
 33.  TestParserTaxSetHappyPath            — set 5% → DB updated
 34.  TestParserTaxSetAcceptsPercent       — "5%" parses correctly
 35.  TestParserTaxSetAcceptsDecimal       — "0.05" parses correctly
 36.  TestParserTaxSetNoArgs               — usage echoed
 37.  TestParserTaxSetBadInput             — non-numeric rejected
 38.  TestParserTaxRatecapHappyPath        — Founder sets cap
 39.  TestParserTaxRatecapFounderOnly      — non-Founder rejected
 40.  TestParserTaxUnknownAction           — bad subcommand surfaced

 41.  TestPhase4NotInPlaceholderList       — tax view live, no Phase 4 echo
 42.  TestPhase5HomeStillPlaceholder       — home still Phase 5
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


# ─── shared fixtures (parallel to Phase 1/2/3) ───────────────────────────


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
    credits: int = 100_000,
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


async def _setup_taxable_city(
    db, *,
    faction_code: str = "veiled_hand",
    treasury: int = 100_000,
    storage_max: int = 100,
    tax_rate: float = 0.0,
    rate_cap: float = 0.10,
):
    """Build a complete founded city with tax controls.

    Returns dict with keys: founder, citizen, outsider, org, city,
    zone_id, hq_room_ids, hq_entry_id.
    """
    from engine.player_cities import found_city, get_city_by_org

    await _seed_account(db)
    zone_id = await _seed_zone(db, "Test Zone", "contested")
    entry_room_id = await _seed_room(db, zone_id, "HQ Entry")
    hq_room_ids = []
    for i in range(4):
        rid = await _seed_room(db, zone_id, f"HQ Room {i}")
        hq_room_ids.append(rid)

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
        faction_id=faction_code, room_id=entry_room_id,
    )
    await _seed_membership(db, founder["id"], org["id"], 5)
    await _seed_hq(
        db, faction_code, entry_room_id,
        hq_room_ids, storage_max=storage_max,
    )
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

    ok, msg = await found_city(
        db, founder, f"City-{faction_code.replace('_', '-')}",
    )
    assert ok, f"setup failed in found_city: {msg}"

    city = await get_city_by_org(db, org["id"])
    org = await db.get_organization(faction_code)

    # Apply non-default tax_rate / rate_cap if requested
    if tax_rate != 0.0 or rate_cap != 0.10:
        await db.execute(
            "UPDATE player_cities SET tax_rate = ?, rate_cap = ? "
            "WHERE id = ?",
            (tax_rate, rate_cap, int(city["id"])),
        )
        await db.commit()
        city = await get_city_by_org(db, org["id"])

    return {
        "founder": founder,
        "citizen": citizen,
        "outsider": outsider,
        "org": org,
        "city": city,
        "zone_id": zone_id,
        "hq_room_ids": hq_room_ids,
        "hq_entry_id": entry_room_id,
    }


# ─── 1. Constants ────────────────────────────────────────────────────────


class TestPhase4Constants(unittest.TestCase):
    def test_min_tax_rate_zero(self):
        from engine.player_cities import MIN_TAX_RATE
        self.assertEqual(MIN_TAX_RATE, 0.0)

    def test_rollover_seconds_one_week(self):
        from engine.player_cities import CITY_REVENUE_ROLLOVER_SECONDS
        self.assertEqual(CITY_REVENUE_ROLLOVER_SECONDS,
                         7 * 24 * 60 * 60)


# ─── 2-7. set_city_tax_rate ──────────────────────────────────────────────


class TestSetTaxRateAuth(unittest.TestCase):
    def test_outsider_rejected(self):
        async def _t():
            from engine.player_cities import set_city_tax_rate
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_tax_rate(
                db, ctx["outsider"], 0.05,
            )
            self.assertFalse(ok)
            self.assertIn("not a member", msg)
        _run(_t())

    def test_citizen_rejected(self):
        async def _t():
            from engine.player_cities import set_city_tax_rate
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_tax_rate(
                db, ctx["citizen"], 0.05,
            )
            self.assertFalse(ok)
            self.assertIn("Mayor or Founder", msg)
        _run(_t())


class TestSetTaxRateBounds(unittest.TestCase):
    def test_negative_rejected(self):
        async def _t():
            from engine.player_cities import set_city_tax_rate
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_tax_rate(
                db, ctx["founder"], -0.01,
            )
            self.assertFalse(ok)
            self.assertIn("at least", msg.lower())
        _run(_t())


class TestSetTaxRateRateCapCeiling(unittest.TestCase):
    def test_above_cap_rejected(self):
        async def _t():
            from engine.player_cities import set_city_tax_rate
            db = await _fresh_db()
            # Cap = 5%
            ctx = await _setup_taxable_city(db, rate_cap=0.05)
            ok, msg = await set_city_tax_rate(
                db, ctx["founder"], 0.08,
            )
            self.assertFalse(ok)
            self.assertIn("cap", msg.lower())
        _run(_t())


class TestSetTaxRateAbsoluteCeiling(unittest.TestCase):
    def test_above_max_rejected_even_if_cap_corrupt(self):
        """Defense in depth: even if rate_cap got corrupted above
        MAX_TAX_RATE, the absolute ceiling check still blocks."""
        async def _t():
            from engine.player_cities import (
                set_city_tax_rate, MAX_TAX_RATE,
            )
            db = await _fresh_db()
            # Force-corrupt the cap to 50% directly in the DB
            ctx = await _setup_taxable_city(db)
            await db.execute(
                "UPDATE player_cities SET rate_cap = 0.50 WHERE id = ?",
                (int(ctx["city"]["id"]),),
            )
            await db.commit()
            ok, msg = await set_city_tax_rate(
                db, ctx["founder"], 0.20,
            )
            self.assertFalse(ok)
            self.assertIn("ceiling", msg.lower())
        _run(_t())


class TestSetTaxRateHappyPath(unittest.TestCase):
    def test_rate_stored(self):
        async def _t():
            from engine.player_cities import (
                set_city_tax_rate, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_tax_rate(
                db, ctx["founder"], 0.05,
            )
            self.assertTrue(ok, msg)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.05, places=6,
            )
        _run(_t())


class TestSetTaxRateInvalidShape(unittest.TestCase):
    def test_non_numeric_rejected(self):
        async def _t():
            from engine.player_cities import set_city_tax_rate
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_tax_rate(
                db, ctx["founder"], "not-a-number",
            )
            self.assertFalse(ok)
            self.assertIn("invalid", msg.lower())
        _run(_t())


# ─── 8-12. set_city_rate_cap ─────────────────────────────────────────────


class TestSetRateCapFounderOnly(unittest.TestCase):
    def test_mayor_non_founder_rejected(self):
        """Reassign Mayor to citizen, then have the new Mayor try to
        set the cap. Founder-only check must reject."""
        async def _t():
            from engine.player_cities import (
                assign_mayor, set_city_rate_cap,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, _ = await assign_mayor(
                db, ctx["founder"], ctx["citizen"]["id"],
            )
            self.assertTrue(ok)
            ok2, msg = await set_city_rate_cap(
                db, ctx["citizen"], 0.05,
            )
            self.assertFalse(ok2)
            self.assertIn("Founder", msg)
        _run(_t())


class TestSetRateCapBounds(unittest.TestCase):
    def test_above_max_rejected(self):
        async def _t():
            from engine.player_cities import set_city_rate_cap
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_rate_cap(
                db, ctx["founder"], 0.20,
            )
            self.assertFalse(ok)
            self.assertIn("ceiling", msg.lower())
        _run(_t())

    def test_negative_rejected(self):
        async def _t():
            from engine.player_cities import set_city_rate_cap
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, msg = await set_city_rate_cap(
                db, ctx["founder"], -0.01,
            )
            self.assertFalse(ok)
            self.assertIn("at least", msg.lower())
        _run(_t())


class TestSetRateCapHappyPath(unittest.TestCase):
    def test_cap_stored(self):
        async def _t():
            from engine.player_cities import (
                set_city_rate_cap, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            ok, _ = await set_city_rate_cap(
                db, ctx["founder"], 0.07,
            )
            self.assertTrue(ok)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["rate_cap"]), 0.07, places=6,
            )
        _run(_t())


class TestSetRateCapClampsCurrentRate(unittest.TestCase):
    def test_cap_below_rate_clamps_rate(self):
        async def _t():
            from engine.player_cities import (
                set_city_rate_cap, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(
                db, tax_rate=0.08, rate_cap=0.10,
            )
            ok, msg = await set_city_rate_cap(
                db, ctx["founder"], 0.05,
            )
            self.assertTrue(ok)
            self.assertIn("clamp", msg.lower())
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.05, places=6,
            )
            self.assertAlmostEqual(
                float(city2["rate_cap"]), 0.05, places=6,
            )
        _run(_t())


class TestSetRateCapDoesNotClampIfBelow(unittest.TestCase):
    def test_cap_above_rate_no_clamp(self):
        async def _t():
            from engine.player_cities import (
                set_city_rate_cap, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(
                db, tax_rate=0.03, rate_cap=0.10,
            )
            ok, msg = await set_city_rate_cap(
                db, ctx["founder"], 0.05,
            )
            self.assertTrue(ok)
            self.assertNotIn("clamp", msg.lower())
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            # Rate untouched at 3%, cap is now 5%
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.03, places=6,
            )
            self.assertAlmostEqual(
                float(city2["rate_cap"]), 0.05, places=6,
            )
        _run(_t())


# ─── 13-20. apply_city_tax ───────────────────────────────────────────────


class TestApplyCityTaxNoRoom(unittest.TestCase):
    def test_invalid_room_returns_zero(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            take, cid, cname = await apply_city_tax(db, 999_999, 1000)
            self.assertEqual(take, 0)
            self.assertIsNone(cid)
            self.assertIsNone(cname)
        _run(_t())


class TestApplyCityTaxNoCity(unittest.TestCase):
    def test_room_outside_city(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            # Seed a room not in any city
            await _seed_account(db)
            zid = await _seed_zone(db, "Z", "contested")
            rid = await _seed_room(db, zid, "Lonely Room")
            take, cid, cname = await apply_city_tax(db, rid, 1000)
            self.assertEqual(take, 0)
            self.assertIsNone(cid)
            self.assertIsNone(cname)
        _run(_t())


class TestApplyCityTaxZeroRate(unittest.TestCase):
    def test_zero_rate_returns_zero_with_city_attribution(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.0)
            take, cid, cname = await apply_city_tax(
                db, ctx["hq_room_ids"][0], 1000,
            )
            self.assertEqual(take, 0)
            self.assertEqual(cid, ctx["city"]["id"])
            self.assertEqual(cname, ctx["city"]["name"])
        _run(_t())


class TestApplyCityTaxMath(unittest.TestCase):
    def test_five_percent_of_thousand(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            take, _, _ = await apply_city_tax(
                db, ctx["hq_room_ids"][0], 1000,
            )
            self.assertEqual(take, 50)
        _run(_t())


class TestApplyCityTaxRoundsDown(unittest.TestCase):
    def test_tiny_gross_floors_to_zero(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            take, _, _ = await apply_city_tax(
                db, ctx["hq_room_ids"][0], 19,
            )
            self.assertEqual(take, 0)  # int(0.95) == 0
        _run(_t())


class TestApplyCityTaxCreditsTreasury(unittest.TestCase):
    def test_treasury_increments_by_exact_take(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            org_before = await db.get_organization(
                ctx["org"]["code"],
            )
            treasury_before = int(org_before["treasury"])
            take, _, _ = await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            self.assertEqual(take, 500)
            org_after = await db.get_organization(
                ctx["org"]["code"],
            )
            self.assertEqual(
                int(org_after["treasury"]) - treasury_before, 500,
            )
        _run(_t())


class TestApplyCityTaxIncrementsRevenue(unittest.TestCase):
    def test_revenue_total_and_week_both_increment(self):
        async def _t():
            from engine.player_cities import (
                apply_city_tax, get_city_by_org,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            await apply_city_tax(
                db, ctx["hq_room_ids"][1], 5_000,
            )
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(int(city2["revenue_total"]), 500 + 250)
            self.assertEqual(int(city2["revenue_week"]), 500 + 250)
        _run(_t())


class TestApplyCityTaxZeroGross(unittest.TestCase):
    def test_zero_gross_returns_zero(self):
        async def _t():
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            take, cid, cname = await apply_city_tax(
                db, ctx["hq_room_ids"][0], 0,
            )
            self.assertEqual(take, 0)
            self.assertIsNone(cid)
            self.assertIsNone(cname)
        _run(_t())


# ─── 21-24. tick_city_revenue_rollover ───────────────────────────────────


class TestTickRevenueRolloverElapsed(unittest.TestCase):
    def test_elapsed_week_resets_revenue_week(self):
        async def _t():
            from engine.player_cities import (
                apply_city_tax, get_city_by_org,
                tick_city_revenue_rollover,
                CITY_REVENUE_ROLLOVER_SECONDS,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            # Force-elapse the week
            old_start = time.time() - CITY_REVENUE_ROLLOVER_SECONDS - 1
            await db.execute(
                "UPDATE player_cities SET week_start_ts = ? "
                "WHERE id = ?",
                (old_start, int(ctx["city"]["id"])),
            )
            await db.commit()
            await tick_city_revenue_rollover(db)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(int(city2["revenue_week"]), 0)
            # week_start_ts advanced
            self.assertGreater(
                float(city2["week_start_ts"]), old_start,
            )
        _run(_t())


class TestTickRevenueRolloverFresh(unittest.TestCase):
    def test_fresh_week_unchanged(self):
        async def _t():
            from engine.player_cities import (
                apply_city_tax, get_city_by_org,
                tick_city_revenue_rollover,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            # week_start_ts from found_city is "now" — not elapsed.
            await tick_city_revenue_rollover(db)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertEqual(int(city2["revenue_week"]), 500)
        _run(_t())


class TestTickRevenueRolloverDissolvedSkipped(unittest.TestCase):
    def test_dissolved_cities_not_processed(self):
        async def _t():
            from engine.player_cities import (
                dissolve_city, tick_city_revenue_rollover,
                CITY_REVENUE_ROLLOVER_SECONDS,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            city_id = int(ctx["city"]["id"])
            # Dissolve the city
            ok, _ = await dissolve_city(
                db, ctx["founder"], ctx["city"]["name"],
            )
            self.assertTrue(ok)
            # Force the dissolved city's week_start to elapsed
            old_start = time.time() - CITY_REVENUE_ROLLOVER_SECONDS - 1
            await db.execute(
                "UPDATE player_cities SET week_start_ts = ?, "
                "revenue_week = 999 WHERE id = ?",
                (old_start, city_id),
            )
            await db.commit()
            await tick_city_revenue_rollover(db)
            # Dissolved row stays as we set it (rollover skipped)
            rows = await db.fetchall(
                "SELECT revenue_week, week_start_ts FROM player_cities "
                "WHERE id = ?",
                (city_id,),
            )
            self.assertEqual(int(rows[0]["revenue_week"]), 999)
            self.assertAlmostEqual(
                float(rows[0]["week_start_ts"]), old_start, places=2,
            )
        _run(_t())


class TestTickRevenueRolloverTotalUnchanged(unittest.TestCase):
    def test_revenue_total_never_resets(self):
        async def _t():
            from engine.player_cities import (
                apply_city_tax, get_city_by_org,
                tick_city_revenue_rollover,
                CITY_REVENUE_ROLLOVER_SECONDS,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            old_start = time.time() - CITY_REVENUE_ROLLOVER_SECONDS - 1
            await db.execute(
                "UPDATE player_cities SET week_start_ts = ? "
                "WHERE id = ?",
                (old_start, int(ctx["city"]["id"])),
            )
            await db.commit()
            await tick_city_revenue_rollover(db)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            # week reset, total preserved
            self.assertEqual(int(city2["revenue_week"]), 0)
            self.assertEqual(int(city2["revenue_total"]), 500)
        _run(_t())


# ─── 25-26. format_city_tax_view ─────────────────────────────────────────


class TestFormatCityTaxViewBasic(unittest.TestCase):
    def test_contains_rate_cap_and_revenue(self):
        async def _t():
            from engine.player_cities import (
                apply_city_tax, get_city_by_org, format_city_tax_view,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(
                db, tax_rate=0.05, rate_cap=0.08,
            )
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            lines = format_city_tax_view(city2)
            joined = "\n".join(lines)
            self.assertIn("5.0%", joined)
            self.assertIn("8.0%", joined)
            self.assertIn("500", joined)
        _run(_t())


class TestFormatCityTaxViewEmptyState(unittest.TestCase):
    def test_zero_revenue_renders_cleanly(self):
        async def _t():
            from engine.player_cities import (
                get_city_by_org, format_city_tax_view,
            )
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)  # tax_rate=0 default
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            lines = format_city_tax_view(city2)
            joined = "\n".join(lines)
            self.assertIn("0.0%", joined)
            self.assertIn("0 cr", joined)
        _run(_t())


# ─── 27-29. Vendor droid integration ─────────────────────────────────────


async def _create_droid_in_room(db, owner: dict, room_id: int):
    """Create a Tier-1 droid in a room, stocked with one item.

    Returns the droid_id.
    """
    from engine.vendor_droids import _dump_data

    droid_data = {
        "tier": "tier_1",
        "shop_name": "Test Shop",
        "shop_desc": "A test vendor droid.",
        "inventory": [
            {
                "slot": 1,
                "item_key": "test_item",
                "item_name": "Test Item",
                "quality": 50,
                "price": 1000,
                "quantity": 5,
                "crafter": "",
            },
        ],
        "escrow_credits": 0,
        "auto_recall_at": time.time() + 86400 * 30,
    }
    droid_id = await db.create_object(
        type="vendor_droid",
        name="Test Droid",
        owner_id=owner["id"],
        room_id=room_id,
        description="A test vendor droid.",
        data=_dump_data(droid_data),
    )
    return droid_id


class TestVendorDroidIntegrationTaxed(unittest.TestCase):
    def test_sale_in_city_reduces_escrow_by_tax(self):
        """In-city sale at 5%: buyer pays 1000, droid escrow gets
        net_payout minus the city tax.

        Tier 1 listing fee is 2% per data/vendor_droids.yaml default.
        Net payout pre-tax: 1000 - 20 = 980.
        City tax 5% of 980 = 49.
        Final escrow: 980 - 49 = 931.
        """
        async def _t():
            from engine.vendor_droids import buy_from_droid, _load_data
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            droid_id = await _create_droid_in_room(
                db, ctx["founder"], ctx["hq_room_ids"][0],
            )
            # Buyer = outsider (doesn't own droid)
            ok, msg = await buy_from_droid(
                ctx["outsider"], droid_id, "1", db,
            )
            self.assertTrue(ok, msg)
            obj = await db.get_object(droid_id)
            data = _load_data(obj)
            escrow = int(data.get("escrow_credits", 0))
            # net_payout = 1000 - 20 (2% fee) = 980, city take = 49
            self.assertEqual(escrow, 980 - 49)
        _run(_t())


class TestVendorDroidIntegrationUntaxed(unittest.TestCase):
    def test_sale_outside_city_full_escrow(self):
        """Sale in a room not in any city: full net_payout reaches escrow."""
        async def _t():
            from engine.vendor_droids import buy_from_droid, _load_data
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            # Make a non-city room in a different zone
            other_zone = await _seed_zone(db, "Other Zone", "contested")
            outside_room = await _seed_room(db, other_zone, "Outside")
            # Move buyer there
            await db.save_character(
                ctx["outsider"]["id"], room_id=outside_room,
            )
            outsider2 = await db.get_character(ctx["outsider"]["id"])
            droid_id = await _create_droid_in_room(
                db, ctx["founder"], outside_room,
            )
            ok, msg = await buy_from_droid(
                outsider2, droid_id, "1", db,
            )
            self.assertTrue(ok, msg)
            obj = await db.get_object(droid_id)
            data = _load_data(obj)
            escrow = int(data.get("escrow_credits", 0))
            # No tax: 1000 - 20 = 980
            self.assertEqual(escrow, 980)
        _run(_t())


class TestVendorDroidIntegrationTaxMessage(unittest.TestCase):
    def test_message_names_city(self):
        async def _t():
            from engine.vendor_droids import buy_from_droid
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            droid_id = await _create_droid_in_room(
                db, ctx["founder"], ctx["hq_room_ids"][0],
            )
            ok, msg = await buy_from_droid(
                ctx["outsider"], droid_id, "1", db,
            )
            self.assertTrue(ok, msg)
            self.assertIn(ctx["city"]["name"], msg)
            self.assertIn("city tax", msg.lower())
        _run(_t())


# ─── 30-31. Bounty post integration ──────────────────────────────────────


class TestBountyPostIntegrationTaxed(unittest.TestCase):
    def test_post_in_city_credits_treasury(self):
        """Posting a 10K bounty (10% fee = 1000) in a 5%-tax city
        adds 5% of 1000 = 50 to the city's treasury, without
        changing the poster's debit (still 10000 + 1000 = 11000).

        Note: the HQ entry_room is the "doorstep" and is NOT in
        player_city_rooms (Phase 2 invariant from the contiguity
        bug — see HANDOFF_MAY22_CITIES_PHASE2.md). The poster has
        to be physically inside an HQ room (one of hq_room_ids) for
        the city to be detected. Real player flow: walk in the door,
        then post."""
        async def _t():
            from parser.pc_bounty_commands import BountyCommand
            from parser.commands import CommandContext
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            # Move founder into a city room (HQ proper, not the doorstep)
            await db.save_character(
                ctx["founder"]["id"], room_id=ctx["hq_room_ids"][0],
            )
            poster = await db.get_character(ctx["founder"]["id"])
            target = ctx["outsider"]
            poster_credits_before = int(poster["credits"])
            org_treasury_before = int(ctx["org"]["treasury"])

            # Build session + ctx
            class _S:
                def __init__(self, c):
                    self.character = c
                    self.is_in_game = True
                    self.account = {"is_admin": 0, "is_builder": 0}
                    self.sent = []
                async def send_line(self, line):
                    self.sent.append(line)
            class _SM:
                def find_by_character(self, _):
                    return None
                async def deliver_mail_notification(self, *a, **kw):
                    return None
            session = _S(poster)
            cmd_ctx = CommandContext(
                session=session,
                raw_input=f"+pcbounty post {target['name']} 10000 testreason",
                command="+pcbounty",
                args=f"post {target['name']} 10000 testreason",
                args_list=["post", target["name"], "10000", "testreason"],
                db=db, session_mgr=_SM(),
            )
            await BountyCommand().execute(cmd_ctx)
            text = "\n".join(session.sent)
            self.assertIn("Bounty posted", text)
            # Refresh poster
            poster2 = await db.get_character(poster["id"])
            self.assertEqual(
                poster_credits_before - int(poster2["credits"]),
                11000,
            )
            # Org treasury should have +50 (5% of 1000 fee)
            org2 = await db.get_organization(ctx["org"]["code"])
            self.assertEqual(
                int(org2["treasury"]) - org_treasury_before, 50,
            )
        _run(_t())


class TestBountyPostIntegrationUntaxed(unittest.TestCase):
    def test_post_outside_city_no_treasury_change(self):
        async def _t():
            from parser.pc_bounty_commands import BountyCommand
            from parser.commands import CommandContext
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            # Move poster to a room outside any city
            other_zone = await _seed_zone(db, "Other Zone", "contested")
            outside_room = await _seed_room(db, other_zone, "Outside")
            await db.save_character(
                ctx["founder"]["id"], room_id=outside_room,
            )
            poster = await db.get_character(ctx["founder"]["id"])
            target = ctx["outsider"]
            org_treasury_before = int(ctx["org"]["treasury"])

            class _S:
                def __init__(self, c):
                    self.character = c
                    self.is_in_game = True
                    self.account = {"is_admin": 0, "is_builder": 0}
                    self.sent = []
                async def send_line(self, line):
                    self.sent.append(line)
            class _SM:
                def find_by_character(self, _):
                    return None
                async def deliver_mail_notification(self, *a, **kw):
                    return None
            session = _S(poster)
            cmd_ctx = CommandContext(
                session=session,
                raw_input=f"+pcbounty post {target['name']} 10000 testreason",
                command="+pcbounty",
                args=f"post {target['name']} 10000 testreason",
                args_list=["post", target["name"], "10000", "testreason"],
                db=db, session_mgr=_SM(),
            )
            await BountyCommand().execute(cmd_ctx)
            text = "\n".join(session.sent)
            self.assertIn("Bounty posted", text)
            # Treasury unchanged
            org2 = await db.get_organization(ctx["org"]["code"])
            self.assertEqual(
                int(org2["treasury"]), org_treasury_before,
            )
        _run(_t())


# ─── 32-40. Parser tests ─────────────────────────────────────────────────


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


class TestParserTaxViewInCity(unittest.TestCase):
    def test_view_shows_rate_and_revenue(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import apply_city_tax
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db, tax_rate=0.05)
            await apply_city_tax(
                db, ctx["hq_room_ids"][0], 10_000,
            )
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax view")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Tax for", text)
            self.assertIn("5.0%", text)
            self.assertIn("500", text)
        _run(_t())


class TestParserTaxSetHappyPath(unittest.TestCase):
    def test_set_via_parser(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax set 5%")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.05, places=6,
            )
        _run(_t())


class TestParserTaxSetAcceptsPercent(unittest.TestCase):
    def test_percent_sign_parsed(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax set 7%")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.07, places=6,
            )
        _run(_t())


class TestParserTaxSetAcceptsDecimal(unittest.TestCase):
    def test_decimal_parsed(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax set 0.03")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["tax_rate"]), 0.03, places=6,
            )
        _run(_t())


class TestParserTaxSetNoArgs(unittest.TestCase):
    def test_usage_echoed(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax set")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Usage:", text)
        _run(_t())


class TestParserTaxSetBadInput(unittest.TestCase):
    def test_non_numeric_surfaced(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax set wat")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("parse", text.lower())
        _run(_t())


class TestParserTaxRatecapHappyPath(unittest.TestCase):
    def test_founder_sets_cap(self):
        async def _t():
            from parser.city_commands import CityCommand
            from engine.player_cities import get_city_by_org
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax ratecap 7%")
            await CityCommand().execute(cctx)
            city2 = await get_city_by_org(db, ctx["org"]["id"])
            self.assertAlmostEqual(
                float(city2["rate_cap"]), 0.07, places=6,
            )
        _run(_t())


class TestParserTaxRatecapFounderOnly(unittest.TestCase):
    def test_citizen_rejected(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["citizen"])
            cctx = _ctx_for(session, db, "+city", "tax ratecap 5%")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            # Citizen is in org but not founder → Founder-only check
            self.assertIn("Founder", text)
        _run(_t())


class TestParserTaxUnknownAction(unittest.TestCase):
    def test_unknown_subcommand(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax frobnicate")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Unknown tax action", text)
        _run(_t())


# ─── 41-42. Phase membership ─────────────────────────────────────────────


class TestPhase4NotInPlaceholderList(unittest.TestCase):
    def test_tax_view_does_not_echo_placeholder(self):
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "tax view")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertNotIn("coming in Phase 4", text)
        _run(_t())


class TestPhase5HomeStillPlaceholder(unittest.TestCase):
    def test_home_subcommand_shipped_in_phase_5(self):
        """Phase 5 (cities_phase5 drop, May 22 2026) moved +city home
        out of the placeholder list. This test was originally
        written against Phase 4's placeholder echo expecting
        'Phase 5' to appear in the output; re-purposed to assert
        the bare-help advertises home as live, mirroring the May 22
        Phase 2/3/4 re-purpose discipline (pinned-keyset on
        umbrella surfaces is the canonical signal that the public
        contract changed)."""
        async def _t():
            from parser.city_commands import CityCommand
            db = await _fresh_db()
            ctx = await _setup_taxable_city(db)
            session = _FakeSession(character=ctx["founder"])
            cctx = _ctx_for(session, db, "+city", "")
            await CityCommand().execute(cctx)
            text = "\n".join(session.sent)
            self.assertIn("Available now:", text)
            self.assertIn("+city home", text)
        _run(_t())


if __name__ == "__main__":
    unittest.main()
