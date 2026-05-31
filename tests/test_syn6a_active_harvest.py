# -*- coding: utf-8 -*-
"""
tests/test_syn6a_active_harvest.py — SYN.6.a (2026-05-25).

Pins:
  * engine/harvest.py (new) — yield table lookup, skill-margin
    scaling, quality conversion, tax computation, full payout
    computation, and the DB-touching perform_harvest entry point.

Test sections
─────────────
  1. TestYieldTableLookup           — pure helper bounds
  2. TestApplySkillMargin           — band scaling, cap, fail-margin
  3. TestQualityConversion          — region quality → stack quality
  4. TestComputeTax                 — owner/non-owner split, rounding
  5. TestComputeHarvestPayout       — end-to-end deterministic
  6. TestPerformHarvestWilderness   — wilderness-only gate
  7. TestPerformHarvestSecured      — defensive secured rejection
  8. TestPerformHarvestCooldown     — cooldown gate + cooldown set
  9. TestPerformHarvestTaxRouting   — owner/non-owner tax flow
 10. TestPerformHarvestResources    — resource stacks land in inv
 11. TestPerformHarvestNoInfluence  — wilderness invariant: harvest
                                       must NOT grant org influence
 12. TestConstantsAndShape          — module-level invariants
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in (mirrors SYN.5 pattern)
# ──────────────────────────────────────────────────────────────────────

class _SyncAsyncSqlite:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        return self._conn.execute(sql, params)

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
                wilderness_region_id TEXT
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
            );
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT,
                treasury INTEGER DEFAULT 0
            );
            CREATE TABLE characters (
                id INTEGER PRIMARY KEY,
                name TEXT,
                attributes TEXT DEFAULT '{}',
                credits INTEGER DEFAULT 0,
                inventory TEXT DEFAULT '{}'
            );
            CREATE TABLE territory_influence (
                zone_id INTEGER NOT NULL,
                org_code TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_activity REAL NOT NULL DEFAULT 0,
                last_presence REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
            );
            CREATE TABLE region_ownership (
                region_slug   TEXT    NOT NULL PRIMARY KEY,
                org_code      TEXT    NOT NULL,
                zone_id       INTEGER,
                claimed_by    INTEGER NOT NULL,
                claimed_at    REAL    NOT NULL,
                maintenance   INTEGER NOT NULL DEFAULT 3000
            );
        """)
        self._db._conn.commit()

        # Treasury adjustments captured so tests can verify routing
        # without re-running SELECT queries.
        self.treasury_log: list[tuple[int, int]] = []

    # raw SQL passthroughs
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    # ORM
    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,))
        return dict(rows[0]) if rows else None

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,))
        return dict(rows[0]) if rows else None

    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,))
        return dict(rows[0]) if rows else None

    async def get_character(self, char_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM characters WHERE id = ?", (char_id,))
        return dict(rows[0]) if rows else None

    async def save_character(self, char_id, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        params = list(kwargs.values()) + [char_id]
        await self._db.execute(
            f"UPDATE characters SET {cols} WHERE id = ?", params)
        await self._db.commit()

    async def adjust_org_treasury(self, org_id, delta):
        """Mirror the production adjust_org_treasury behaviour and
        capture the (org_id, delta) for assertions."""
        self.treasury_log.append((org_id, delta))
        self._db._conn.execute(
            "UPDATE organizations SET treasury = treasury + ? WHERE id = ?",
            (delta, org_id))
        self._db._conn.commit()
        rows = self._db._conn.execute(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
        ).fetchall()
        return int(rows[0]["treasury"]) if rows else 0

    # Seeds
    def seed_org(self, *, org_id, code, treasury=0):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, code.title(), treasury))
        self._db._conn.commit()

    def seed_zone(self, *, zone_id=1, name="Tatooine", security="lawless"):
        props = json.dumps({"security": security})
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, props))
        self._db._conn.commit()

    def seed_room(self, *, room_id, zone_id=None, wilderness_region_id=None,
                   name="Room"):
        self._db._conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) "
            "VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self._db._conn.commit()

    def seed_character(self, *, char_id, credits=0, attributes=None,
                       inventory=None):
        if attributes is None:
            attributes = {}
        if inventory is None:
            inventory = {}
        self._db._conn.execute(
            "INSERT INTO characters (id, name, attributes, credits, "
            "inventory) VALUES (?, ?, ?, ?, ?)",
            (char_id, f"Char{char_id}", json.dumps(attributes), credits,
             json.dumps(inventory)))
        self._db._conn.commit()

    def seed_region_ownership(self, *, region_slug, org_code, zone_id):
        self._db._conn.execute(
            "INSERT INTO region_ownership (region_slug, org_code, zone_id, "
            "claimed_by, claimed_at) VALUES (?, ?, ?, ?, ?)",
            (region_slug, org_code, zone_id, 1, 0.0))
        self._db._conn.commit()

    def seed_influence(self, *, zone_id, org_code, score):
        self._db._conn.execute(
            "INSERT INTO territory_influence (zone_id, org_code, score) "
            "VALUES (?, ?, ?)",
            (zone_id, org_code, score))
        self._db._conn.commit()


# Standard character template that satisfies perform_skill_check
# requirements (attributes blob with skill values).
def _make_char(*, char_id=1, faction_id="independent", room_id=10,
                credits=0, survival_dice="3D", attributes=None,
                skills=None, inventory=None):
    """Build an in-memory character dict for harvest tests.

    perform_skill_check reads:
      * char['attributes']     — JSON string of attribute → dice
      * char['skills']         — JSON string of skill_name → dice bonus
    These are TWO separate top-level fields on the char dict
    (see engine/skill_checks.py::_get_skill_pool).

    The survival skill is keyed off the 'knowledge' attribute by
    default (see _skill_to_attr fallback). We give knowledge=3D
    baseline, and the survival_dice param is the additional skill
    bonus on top of that. 12D survival means knowledge 3D + survival
    bonus 9D → effective 12D pool — minimum roll 12, always passes
    DC 6.
    """
    if attributes is None:
        attributes = {"knowledge": "3D"}
    if skills is None:
        skills = {"survival": survival_dice}
    if inventory is None:
        inventory = {}
    return {
        "id": char_id,
        "name": f"Char{char_id}",
        "faction_id": faction_id,
        "room_id": room_id,
        "credits": credits,
        "attributes": json.dumps(attributes),
        "skills": json.dumps(skills),
        "inventory": json.dumps(inventory),
    }


# ──────────────────────────────────────────────────────────────────────
# 1. TestYieldTableLookup
# ──────────────────────────────────────────────────────────────────────

class TestYieldTableLookup(unittest.TestCase):
    """Pure helper: every (security, tier) pair returns a yield row."""

    def test_contested_foothold(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("contested", "foothold")
        self.assertEqual((cr_min, cr_max), (100, 200))
        self.assertEqual(res, {"metal": 1})

    def test_contested_dominant(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("contested", "dominant")
        self.assertEqual((cr_min, cr_max), (150, 300))
        self.assertEqual(res, {"metal": 2, "organic": 1})

    def test_contested_control_has_t5_chance(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("contested", "control")
        self.assertEqual((cr_min, cr_max), (200, 400))
        self.assertIn("_t5_rare_chance", res)
        self.assertEqual(res["metal"], 2)
        self.assertEqual(res["organic"], 1)

    def test_lawless_foothold(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("lawless", "foothold")
        self.assertEqual((cr_min, cr_max), (150, 300))
        self.assertEqual(res, {"metal": 2, "chemical": 1})

    def test_lawless_dominant(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("lawless", "dominant")
        self.assertEqual((cr_min, cr_max), (250, 500))
        self.assertEqual(res, {"metal": 3, "chemical": 2, "rare": 1})

    def test_lawless_control(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("lawless", "control")
        self.assertEqual((cr_min, cr_max), (400, 800))
        self.assertEqual(res["metal"], 4)
        self.assertEqual(res["chemical"], 3)
        self.assertEqual(res["rare"], 2)
        self.assertIn("_t5_rare_chance", res)

    def test_unknown_tier_falls_back_to_foothold(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("lawless", "garbage")
        # Falls back to ("lawless", "foothold")
        self.assertEqual((cr_min, cr_max), (150, 300))

    def test_unknown_security_falls_back_to_lawless(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("nonsense", "foothold")
        self.assertEqual((cr_min, cr_max), (150, 300))

    def test_none_security_treated_as_lawless(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup(None, "foothold")
        self.assertEqual((cr_min, cr_max), (150, 300))

    def test_none_tier_falls_back_to_foothold(self):
        from engine.harvest import _yield_table_lookup
        cr_min, cr_max, res = _yield_table_lookup("lawless", None)
        self.assertEqual((cr_min, cr_max), (150, 300))


# ──────────────────────────────────────────────────────────────────────
# 2. TestApplySkillMargin
# ──────────────────────────────────────────────────────────────────────

class TestApplySkillMargin(unittest.TestCase):
    """5-point margin bands give +20% credits + 10Q each, capped at 50Q."""

    def test_failure_margin_returns_empty(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, -1)
        self.assertEqual(band, (0, 0))
        self.assertEqual(qbonus, 0)

    def test_far_failure_margin_returns_empty(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, -10)
        self.assertEqual(band, (0, 0))
        self.assertEqual(qbonus, 0)

    def test_zero_margin_base_band_no_bonus(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 0)
        self.assertEqual(band, (100, 200))
        self.assertEqual(qbonus, 0)

    def test_4_margin_still_base_band(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 4)
        self.assertEqual(band, (100, 200))
        self.assertEqual(qbonus, 0)

    def test_5_margin_one_band(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 5)
        self.assertEqual(band, (120, 240))  # +20%
        self.assertEqual(qbonus, 10)

    def test_10_margin_two_bands(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 10)
        self.assertEqual(band, (140, 280))  # +40%
        self.assertEqual(qbonus, 20)

    def test_25_margin_five_bands_caps_quality_at_50(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 25)
        self.assertEqual(band, (200, 400))  # +100%
        self.assertEqual(qbonus, 50)  # capped

    def test_50_margin_credit_keeps_scaling_quality_stays_capped(self):
        from engine.harvest import _apply_skill_margin
        band, qbonus = _apply_skill_margin(100, 200, 50)
        # 10 bands → +200% on credits
        self.assertEqual(band, (300, 600))
        # quality cap still 50
        self.assertEqual(qbonus, 50)


# ──────────────────────────────────────────────────────────────────────
# 3. TestQualityConversion
# ──────────────────────────────────────────────────────────────────────

class TestQualityConversion(unittest.TestCase):
    """Region quality multiplier × margin bonus → 1..100 stack quality."""

    def test_baseline_quality_50(self):
        from engine.harvest import _quality_to_resource_quality
        self.assertEqual(_quality_to_resource_quality(1.0, 0), 50.0)

    def test_high_region_with_margin_bonus(self):
        from engine.harvest import _quality_to_resource_quality
        # 1.3× × 50 = 65, +20 margin bonus = 85
        self.assertEqual(_quality_to_resource_quality(1.3, 20), 85.0)

    def test_low_region_clamped_at_one(self):
        from engine.harvest import _quality_to_resource_quality
        # 0.01 × 50 = 0.5, clamped to 1.0
        self.assertEqual(_quality_to_resource_quality(0.01, 0), 1.0)

    def test_high_clamped_at_100(self):
        from engine.harvest import _quality_to_resource_quality
        # 1.5× × 50 = 75, +50 = 125, clamped to 100
        self.assertEqual(_quality_to_resource_quality(1.5, 50), 100.0)

    def test_zero_region_quality_clamps_low(self):
        from engine.harvest import _quality_to_resource_quality
        self.assertEqual(_quality_to_resource_quality(0.0, 0), 1.0)


# ──────────────────────────────────────────────────────────────────────
# 4. TestComputeTax
# ──────────────────────────────────────────────────────────────────────

class TestComputeTax(unittest.TestCase):
    """Owner-member keeps 100%; non-member pays 15%; sums conserve."""

    def test_owner_keeps_all(self):
        from engine.harvest import _compute_tax
        kept, tax = _compute_tax(1000, is_owner_member=True)
        self.assertEqual((kept, tax), (1000, 0))

    def test_nonmember_pays_15pct(self):
        from engine.harvest import _compute_tax
        kept, tax = _compute_tax(1000, is_owner_member=False)
        self.assertEqual(kept + tax, 1000)
        self.assertEqual(tax, 150)
        self.assertEqual(kept, 850)

    def test_zero_credits_no_tax(self):
        from engine.harvest import _compute_tax
        kept, tax = _compute_tax(0, is_owner_member=False)
        self.assertEqual((kept, tax), (0, 0))

    def test_small_amount_rounds_consistently(self):
        from engine.harvest import _compute_tax
        # 7 cr × 0.15 = 1.05 → rounds to 1 tax, 6 kept
        kept, tax = _compute_tax(7, is_owner_member=False)
        self.assertEqual(kept + tax, 7)
        # Tax is non-negative, bounded by credits
        self.assertGreaterEqual(tax, 0)
        self.assertLessEqual(tax, 7)

    def test_one_credit_edge(self):
        from engine.harvest import _compute_tax
        kept, tax = _compute_tax(1, is_owner_member=False)
        # 1 × 0.15 = 0.15 → rounds to 0; kept=1, tax=0
        self.assertEqual(kept + tax, 1)

    def test_unowned_region_keeps_everything(self):
        """When the region has no owner, non-member status is moot —
        harvester keeps 100% and the 15% would otherwise vanish."""
        from engine.harvest import _compute_tax
        kept, tax = _compute_tax(
            1000, is_owner_member=False, owner_exists=False,
        )
        self.assertEqual((kept, tax), (1000, 0))


# ──────────────────────────────────────────────────────────────────────
# 5. TestComputeHarvestPayout (deterministic end-to-end on the pure path)
# ──────────────────────────────────────────────────────────────────────

class TestComputeHarvestPayout(unittest.TestCase):
    """compute_harvest_payout pulls together band/quality/tax/stacks."""

    def test_failure_margin_zero_payout(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless", influence_tier="foothold",
            margin=-1, quality=1.0, is_owner_member=True,
            rng=random.Random(42),
        )
        self.assertEqual(out["credits_gross"], 0)
        self.assertEqual(out["credits_kept"], 0)
        self.assertEqual(out["credits_tax"], 0)
        self.assertEqual(out["resource_stacks"], [])
        self.assertFalse(out["t5_rare"])

    def test_owner_member_zero_tax(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless", influence_tier="dominant",
            margin=0, quality=1.0, is_owner_member=True,
            rng=random.Random(1),
        )
        self.assertEqual(out["credits_tax"], 0)
        self.assertEqual(out["credits_kept"], out["credits_gross"])

    def test_nonmember_tax_routed(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless", influence_tier="dominant",
            margin=0, quality=1.0, is_owner_member=False,
            rng=random.Random(1),
        )
        # Sum conserves
        self.assertEqual(
            out["credits_kept"] + out["credits_tax"],
            out["credits_gross"],
        )
        # Tax is approximately 15% (within rounding)
        if out["credits_gross"] > 0:
            ratio = out["credits_tax"] / out["credits_gross"]
            self.assertAlmostEqual(ratio, 0.15, delta=0.02)

    def test_resource_stacks_carry_quality(self):
        from engine.harvest import compute_harvest_payout
        out = compute_harvest_payout(
            security="lawless", influence_tier="dominant",
            margin=0, quality=1.0, is_owner_member=True,
            rng=random.Random(7),
        )
        # 3 metal + 2 chemical + 1 rare
        self.assertEqual(len(out["resource_stacks"]), 3)
        types = {s["type"] for s in out["resource_stacks"]}
        self.assertEqual(types, {"metal", "chemical", "rare"})
        # All at baseline quality 50
        for s in out["resource_stacks"]:
            self.assertEqual(s["quality"], 50.0)

    def test_t5_rare_grants_q100_rare_when_rolled(self):
        from engine.harvest import compute_harvest_payout
        # Force the t5_rare roll by patching rng so .random() returns 0.0
        class _AlwaysHitRng:
            def randint(self, a, b): return (a + b) // 2
            def random(self): return 0.0  # always hits
        out = compute_harvest_payout(
            security="lawless", influence_tier="control",
            margin=0, quality=1.0, is_owner_member=True,
            rng=_AlwaysHitRng(),
        )
        self.assertTrue(out["t5_rare"])
        # The base "rare" stack is at q50, the T5 bonus is at q100
        rare_stacks = [s for s in out["resource_stacks"]
                        if s["type"] == "rare"]
        self.assertEqual(len(rare_stacks), 2)
        qs = sorted(s["quality"] for s in rare_stacks)
        self.assertEqual(qs, [50.0, 100.0])

    def test_t5_rare_not_rolled_no_q100(self):
        from engine.harvest import compute_harvest_payout
        class _NeverHitRng:
            def randint(self, a, b): return (a + b) // 2
            def random(self): return 0.99  # never hits
        out = compute_harvest_payout(
            security="lawless", influence_tier="control",
            margin=0, quality=1.0, is_owner_member=True,
            rng=_NeverHitRng(),
        )
        self.assertFalse(out["t5_rare"])
        rare_stacks = [s for s in out["resource_stacks"]
                        if s["type"] == "rare"]
        self.assertEqual(len(rare_stacks), 1)
        self.assertEqual(rare_stacks[0]["quality"], 50.0)

    def test_margin_scales_credits_up(self):
        from engine.harvest import compute_harvest_payout
        rng = random.Random(0)
        low = compute_harvest_payout(
            security="lawless", influence_tier="foothold",
            margin=0, quality=1.0, is_owner_member=True,
            rng=rng,
        )
        rng = random.Random(0)  # same seed
        high = compute_harvest_payout(
            security="lawless", influence_tier="foothold",
            margin=20, quality=1.0, is_owner_member=True,
            rng=rng,
        )
        # +20 margin = 4 bands = +80%; sampled credit should be ~1.8x
        # the same-seed low-margin sample
        self.assertGreater(high["credits_gross"], low["credits_gross"])

    def test_quality_multiplier_scales_stack_quality(self):
        from engine.harvest import compute_harvest_payout
        out_low = compute_harvest_payout(
            security="lawless", influence_tier="foothold",
            margin=0, quality=0.7, is_owner_member=True,
            rng=random.Random(0),
        )
        out_high = compute_harvest_payout(
            security="lawless", influence_tier="foothold",
            margin=0, quality=1.3, is_owner_member=True,
            rng=random.Random(0),
        )
        # 0.7 × 50 = 35, 1.3 × 50 = 65
        self.assertEqual(out_low["stack_quality"], 35.0)
        self.assertEqual(out_high["stack_quality"], 65.0)


# ──────────────────────────────────────────────────────────────────────
# Shared helpers for DB-touching tests
# ──────────────────────────────────────────────────────────────────────

def _setup_basic_world(*, security="lawless", owner_code=None,
                        owner_score=0):
    """Build a MiniDB with a wilderness room, optional owner."""
    mdb = _MiniDB()
    mdb.seed_zone(zone_id=1, name="Tatooine", security=security)
    mdb.seed_room(room_id=10, zone_id=1,
                   wilderness_region_id="tatooine_dune_sea")
    if owner_code is not None:
        mdb.seed_org(org_id=100, code=owner_code, treasury=0)
        mdb.seed_region_ownership(
            region_slug="tatooine_dune_sea", org_code=owner_code, zone_id=1,
        )
        if owner_score > 0:
            mdb.seed_influence(zone_id=1, org_code=owner_code,
                                score=owner_score)
    return mdb


# ──────────────────────────────────────────────────────────────────────
# 6. TestPerformHarvestWilderness — wilderness-only gate
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestWilderness(unittest.TestCase):
    """Active harvest must short-circuit on non-wilderness rooms."""

    def test_city_room_rejected(self):
        from engine.harvest import perform_harvest
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1, name="Mos Eisley", security="contested")
        # City room: wilderness_region_id is NULL
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id=None)
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10)

        result = _run(perform_harvest(mdb, char, 10))

        self.assertFalse(result["ok"])
        self.assertIn("harvest node", result["msg"].lower())

    def test_missing_room_rejected(self):
        from engine.harvest import perform_harvest
        mdb = _MiniDB()
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=999)

        result = _run(perform_harvest(mdb, char, 999))

        self.assertFalse(result["ok"])
        self.assertIn("harvest node", result["msg"].lower())


# ──────────────────────────────────────────────────────────────────────
# 7. TestPerformHarvestSecured — secured wilderness defensive reject
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestSecured(unittest.TestCase):
    """Defensive: secured wilderness is impossible by design but a
    misconfigured zone shouldn't farm errors — reject cleanly."""

    def test_secured_wilderness_rejected(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(security="secured")
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10)

        result = _run(perform_harvest(mdb, char, 10))

        self.assertFalse(result["ok"])
        self.assertIn("policed", result["msg"].lower())


# ──────────────────────────────────────────────────────────────────────
# 8. TestPerformHarvestCooldown
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestCooldown(unittest.TestCase):
    """First harvest succeeds, second is gated by cooldown."""

    def test_cooldown_set_on_first_harvest(self):
        from engine.harvest import (
            perform_harvest, COOLDOWN_KEY_PREFIX, HARVEST_COOLDOWN_SECS,
        )
        from engine.cooldowns import remaining_cooldown
        mdb = _setup_basic_world()
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10, survival_dice="6D")

        result = _run(perform_harvest(mdb, char, 10))

        # ok regardless of skill outcome — cooldown set either way
        self.assertTrue(result["ok"])
        cd_key = f"{COOLDOWN_KEY_PREFIX}tatooine_dune_sea"
        # Cooldown remaining should be close to the full duration
        rem = remaining_cooldown(char, cd_key)
        self.assertGreater(rem, HARVEST_COOLDOWN_SECS - 10)

    def test_cooldown_blocks_second_harvest(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world()
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10, survival_dice="6D")

        _run(perform_harvest(mdb, char, 10))
        result2 = _run(perform_harvest(mdb, char, 10))

        self.assertFalse(result2["ok"])
        self.assertIn("wait", result2["msg"].lower())

    def test_cooldown_is_per_region(self):
        """A second region's cooldown does not block harvest in the
        first. Tests the namespacing of COOLDOWN_KEY_PREFIX."""
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world()
        # Add a second wilderness region in the same zone.
        mdb.seed_room(room_id=20, zone_id=1,
                       wilderness_region_id="tatooine_jundland")
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10, survival_dice="6D")

        r1 = _run(perform_harvest(mdb, char, 10))
        self.assertTrue(r1["ok"])
        # Same character moves to the other region — different cd key
        r2 = _run(perform_harvest(mdb, char, 20))
        self.assertTrue(r2["ok"])  # not blocked
        self.assertNotIn("wait", r2["msg"].lower())


# ──────────────────────────────────────────────────────────────────────
# 9. TestPerformHarvestTaxRouting
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestTaxRouting(unittest.TestCase):
    """Non-member harvesters pay 15% to owner treasury; members don't."""

    def test_member_pays_no_tax(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code="hutts", owner_score=1000)
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10,
                           faction_id="hutts",
                           survival_dice="6D")

        result = _run(perform_harvest(mdb, char, 10))

        self.assertTrue(result["ok"])
        self.assertEqual(result["credits_tax"], 0)
        # Owner treasury unchanged
        self.assertEqual(mdb.treasury_log, [])

    def test_nonmember_pays_15pct_to_owner(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code="hutts", owner_score=1000)
        mdb.seed_character(char_id=1)
        # 12D survival — minimum roll is 12, always ≥ DC 6.
        # Deterministic without seeding the global RNG.
        char = _make_char(char_id=1, room_id=10,
                           faction_id="cis",
                           survival_dice="12D")

        result = _run(perform_harvest(mdb, char, 10))

        self.assertGreater(result.get("credits_kept", 0), 0)
        self.assertGreater(result["credits_tax"], 0)
        self.assertEqual(len(mdb.treasury_log), 1)
        log_org_id, log_delta = mdb.treasury_log[0]
        self.assertEqual(log_org_id, 100)
        self.assertEqual(log_delta, result["credits_tax"])

    def test_unowned_region_no_tax(self):
        """No owner → no tax, no treasury_log entry."""
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code=None)
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10,
                           faction_id="independent",
                           survival_dice="6D")

        result = _run(perform_harvest(mdb, char, 10))

        self.assertTrue(result["ok"])
        self.assertEqual(result["credits_tax"], 0)
        self.assertEqual(mdb.treasury_log, [])

    def test_independent_harvester_pays_tax(self):
        """An 'independent' (faction-less) PC is NOT a member of any
        org — should still pay tax in owned regions."""
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code="hutts", owner_score=1000)
        mdb.seed_character(char_id=1)
        # 12D survival → deterministic success (min roll 12 ≥ DC 6).
        char = _make_char(char_id=1, room_id=10,
                           faction_id="independent",
                           survival_dice="12D")

        result = _run(perform_harvest(mdb, char, 10))

        self.assertGreater(result.get("credits_kept", 0), 0)
        self.assertGreater(result["credits_tax"], 0)


# ──────────────────────────────────────────────────────────────────────
# 10. TestPerformHarvestResources — stacks land in inventory.resources
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestResources(unittest.TestCase):
    """Resource stacks must use engine.crafting (inventory.resources)."""

    def test_stacks_land_in_inventory_resources(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code="hutts", owner_score=1000)
        mdb.seed_character(char_id=1)
        # 12D → deterministic skill check success
        char = _make_char(char_id=1, room_id=10,
                           faction_id="hutts",
                           survival_dice="12D")

        result = _run(perform_harvest(mdb, char, 10))

        self.assertTrue(result.get("ok"))
        self.assertGreater(len(result.get("resource_stacks", [])), 0)

        # Inventory is mutated in place by add_resource as a JSON string
        inv_raw = char["inventory"]
        self.assertIsInstance(inv_raw, str)
        inv = json.loads(inv_raw)
        self.assertIn("resources", inv)
        self.assertGreater(len(inv["resources"]), 0)
        # Each stack has the SWG schema
        for stack in inv["resources"]:
            self.assertIn("type", stack)
            self.assertIn("quantity", stack)
            self.assertIn("quality", stack)

    def test_resource_types_in_crafting_set(self):
        """All harvested resource types must be in HARVESTABLE_RESOURCE_TYPES.

        SYN.6.c (May 25 2026): tightened from the broader RESOURCE_TYPES to
        the narrower HARVESTABLE_RESOURCE_TYPES subset. T5 mats
        (kyber_shard_minor, weapons_capacitor_core, etc.) are drop-only
        and must NOT appear in the harvest yield table — they have their
        own acquisition paths (force-resonant landmarks, T2/T3 anomalies,
        special harvests)."""
        from engine.harvest import YIELD_TABLE
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES
        for (sec, tier), (cmin, cmax, res) in YIELD_TABLE.items():
            for key in res:
                if key.startswith("_"):
                    continue
                self.assertIn(
                    key, HARVESTABLE_RESOURCE_TYPES,
                    f"yield table row ({sec},{tier}) has type {key!r} "
                    f"which is not in HARVESTABLE_RESOURCE_TYPES "
                    f"(T5 mats must not appear in ordinary harvest yields)",
                )


# ──────────────────────────────────────────────────────────────────────
# 11. TestPerformHarvestNoInfluence — wilderness-only invariant
# ──────────────────────────────────────────────────────────────────────

class TestPerformHarvestNoInfluence(unittest.TestCase):
    """Per design §2.7 + arch §4.25: active harvest does NOT grant
    org influence. Only kills/missions/pvp/intel-handover do."""

    def test_harvest_does_not_touch_territory_influence(self):
        from engine.harvest import perform_harvest
        mdb = _setup_basic_world(owner_code="hutts", owner_score=300)
        mdb.seed_character(char_id=1)
        char = _make_char(char_id=1, room_id=10,
                           faction_id="cis", survival_dice="6D")

        # Capture pre-harvest influence
        before = mdb._db._conn.execute(
            "SELECT zone_id, org_code, score FROM territory_influence"
        ).fetchall()
        before_rows = [tuple(r) for r in before]

        _run(perform_harvest(mdb, char, 10))

        after = mdb._db._conn.execute(
            "SELECT zone_id, org_code, score FROM territory_influence"
        ).fetchall()
        after_rows = [tuple(r) for r in after]

        # Influence table is byte-identical before/after — harvest
        # touches treasury and credits only.
        self.assertEqual(before_rows, after_rows)


# ──────────────────────────────────────────────────────────────────────
# 12. TestConstantsAndShape
# ──────────────────────────────────────────────────────────────────────

class TestConstantsAndShape(unittest.TestCase):
    """Module invariants."""

    def test_tax_rate_15pct(self):
        from engine.harvest import NON_OWNER_TAX_RATE
        self.assertEqual(NON_OWNER_TAX_RATE, 0.15)

    def test_cooldown_30_minutes(self):
        from engine.harvest import HARVEST_COOLDOWN_SECS
        self.assertEqual(HARVEST_COOLDOWN_SECS, 1800)

    def test_difficulty_is_easy(self):
        from engine.harvest import HARVEST_DIFFICULTY
        # WEG D6 R&E "Easy" is 6
        self.assertEqual(HARVEST_DIFFICULTY, 6)

    def test_skill_is_survival(self):
        from engine.harvest import HARVEST_SKILL
        self.assertEqual(HARVEST_SKILL, "survival")

    def test_yield_table_has_six_rows(self):
        from engine.harvest import YIELD_TABLE
        self.assertEqual(len(YIELD_TABLE), 6)
        # Two security levels × three influence tiers
        secs = {k[0] for k in YIELD_TABLE}
        tiers = {k[1] for k in YIELD_TABLE}
        self.assertEqual(secs, {"contested", "lawless"})
        self.assertEqual(tiers, {"foothold", "dominant", "control"})

    def test_region_quality_seam_returns_baseline(self):
        """SYN.6.b updated this seam: ``_get_region_quality`` now
        returns a per-resource-type dict (was a float 1.0 in SYN.6.a).
        Without the region_quality table populated (or in this test
        fixture's case, absent entirely), it returns the all-baseline
        dict — every resource type at 1.0×.

        ``compute_harvest_payout`` accepts both forms (float or dict)
        for back-compat, so the existing SYN.6.a unit tests below
        that pass ``quality=1.0`` still work."""
        from engine.harvest import _get_region_quality
        mdb = _MiniDB()
        q = _run(_get_region_quality(mdb, "anything"))
        # SYN.6.b contract: dict keyed by resource type, all baseline.
        self.assertIsInstance(q, dict)
        # Every value is the baseline multiplier
        self.assertTrue(all(v == 1.0 for v in q.values()))
        # And the dict covers crafting's HARVESTABLE_RESOURCE_TYPES
        # (SYN.6.c: T5 mats are drop-only, not in the weekly variance roll)
        from engine.crafting import HARVESTABLE_RESOURCE_TYPES
        self.assertEqual(set(q.keys()), set(HARVESTABLE_RESOURCE_TYPES))

    def test_cooldown_key_prefix_namespaces_by_region(self):
        """Region slug appended to prefix gives the cooldown key
        (verified by inspecting the prefix shape)."""
        from engine.harvest import COOLDOWN_KEY_PREFIX
        self.assertTrue(COOLDOWN_KEY_PREFIX.endswith("_"))


if __name__ == "__main__":
    unittest.main()
