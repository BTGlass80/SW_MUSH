# -*- coding: utf-8 -*-
"""
tests/test_tier2_tuning_batch.py — economy audit v2 Tier-2 tuning batch.

Four tuning items, one drop:
  * **#4 (§1.4)** smuggling EV — high-risk tiers' fine drops 0.50 → 0.25 so the
    smuggler archetype is no longer EV-dominated by bounty hunting.
  * **#5 (§2.1)** mission partial-pay — fractions 0.50/0.75 → 0.40 and the
    partial window tightens -4 → -2, so over-reaching no longer out-earns lane.
  * **#7 (§2.4)** P2P cap 5,000 → 1,500 (vendor/faction flows inherently exempt).
  * **#8 (§2.7)** vendor listing TTL — a recurring relist fee on listings older
    than the TTL turns the one-time listing fee into a recurring cost.
"""

import os
import re
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# #4 — smuggling fine fractions
# ─────────────────────────────────────────────────────────────────────────────
class TestSmugglingFine(unittest.TestCase):
    def test_high_risk_tiers_pay_quarter_fine(self):
        from engine.smuggling import _fine_fraction, CargoTier
        self.assertEqual(_fine_fraction(CargoTier.CONTRABAND), 0.25)
        self.assertEqual(_fine_fraction(CargoTier.SPICE), 0.25)

    def test_low_tiers_unchanged(self):
        from engine.smuggling import _fine_fraction, CargoTier, FINE_FRACTION
        self.assertEqual(_fine_fraction(CargoTier.GREY_MARKET), FINE_FRACTION)
        self.assertEqual(_fine_fraction(CargoTier.BLACK_MARKET), FINE_FRACTION)
        self.assertEqual(FINE_FRACTION, 0.50)

    def test_unknown_tier_falls_back_to_flat(self):
        from engine.smuggling import _fine_fraction, FINE_FRACTION
        self.assertEqual(_fine_fraction("???"), FINE_FRACTION)

    def test_high_tier_fine_is_half_the_old_flat(self):
        """The EV fix: a busted Spice/Core run keeps twice as much as before."""
        from engine.smuggling import _fine_fraction, CargoTier, FINE_FRACTION
        self.assertLess(_fine_fraction(CargoTier.SPICE), FINE_FRACTION)

    def test_bust_site_uses_tier_aware_fine(self):
        with open(os.path.join(PROJECT_ROOT, "engine", "smuggling.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("_fine_fraction(tier)", src,
                      "the bust fine must be tier-aware, not the flat FINE_FRACTION")


# ─────────────────────────────────────────────────────────────────────────────
# #5 — mission partial-pay
# ─────────────────────────────────────────────────────────────────────────────
class TestMissionPartialPay(unittest.TestCase):
    def test_partial_fractions_lowered(self):
        from engine.skill_checks import MISSION_SKILL_MAP
        for mtype, (skill, frac) in MISSION_SKILL_MAP.items():
            if mtype == "delivery":
                self.assertEqual(frac, 1.00, "delivery stays full-pay (easy tier)")
            else:
                self.assertLessEqual(frac, 0.40,
                                     f"{mtype} partial-pay should be <= 0.40")
                self.assertGreaterEqual(frac, 0.25,
                                        f"{mtype} partial-pay should be in 25-40%")

    def test_partial_window_tightened_to_minus_two(self):
        """The mission resolver pays partial only on a near-miss (margin >= -2);
        the repair resolver's -4 window is unrelated and must stay."""
        with open(os.path.join(PROJECT_ROOT, "engine", "skill_checks.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        # the mission credit branch + the 'partial' flag both use >= -2
        i = src.index("def resolve_mission_completion")
        j = src.index("\ndef ", i + 10)
        mission_src = src[i:j]
        self.assertIn("result.margin >= -2", mission_src)
        self.assertNotIn("result.margin >= -4", mission_src,
                         "no -4 window should remain in the mission resolver")

    def test_repair_resolver_window_unchanged(self):
        """Guard: the change must not have touched the repair resolver's -4."""
        from engine import skill_checks
        src = open(skill_checks.__file__, encoding="utf-8").read()
        self.assertIn("result.margin >= -4", src,
                      "the repair resolver's -4 partial window should remain")


# ─────────────────────────────────────────────────────────────────────────────
# #7 — P2P cap → velocity alert (ECON.p2p_cap_review = a, 2026-06-11)
# ─────────────────────────────────────────────────────────────────────────────
class TestP2PCap(unittest.TestCase):
    def test_hard_cap_constant_removed(self):
        # The S51/audit-v2 hard cap is reversed by explicit sign-off:
        # decision a removes the block; the threshold lives on as the
        # alert band in engine.economy_alerts.
        import parser.builtin_commands as bc
        self.assertFalse(hasattr(bc, "P2P_DAILY_CAP"),
                         "P2P_DAILY_CAP must not exist — decision a")

    def test_alert_threshold_keeps_old_value(self):
        from engine.economy_alerts import P2P_VELOCITY_CAUTION_24H
        self.assertEqual(P2P_VELOCITY_CAUTION_24H, 1_500)

    def test_alert_keyed_on_p2p_outgoing_only(self):
        """Vendor/faction flows stay exempt from the ALERT for the same
        reason they were exempt from the cap: the read is
        get_daily_p2p_outgoing, which they don't increment."""
        with open(os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("get_daily_p2p_outgoing", src)


# ─────────────────────────────────────────────────────────────────────────────
# #8 — vendor listing TTL / recurring relist fee
# ─────────────────────────────────────────────────────────────────────────────
class TestStaleListingFee(unittest.TestCase):
    def setUp(self):
        from engine.vendor_droids import (
            _stale_listing_fee, _LISTING_TTL_DAYS, _RELIST_FEE_PCT, _RELIST_FEE_MIN,
        )
        self.fee = _stale_listing_fee
        self.TTL = _LISTING_TTL_DAYS
        self.PCT = _RELIST_FEE_PCT
        self.MIN = _RELIST_FEE_MIN

    def test_fresh_listing_is_free(self):
        import time
        slot = {"price": 1000, "quantity": 5, "listed_at": time.time()}
        self.assertEqual(self.fee(slot, time.time()), 0)

    def test_missing_clock_is_free(self):
        import time
        self.assertEqual(self.fee({"price": 1000, "quantity": 5}, time.time()), 0)

    def test_stale_listing_charges_pct_of_value(self):
        import time
        now = time.time()
        old = now - (self.TTL + 1) * 86400
        slot = {"price": 1000, "quantity": 5, "listed_at": old}  # value 5000
        self.assertEqual(self.fee(slot, now), int(5000 * self.PCT))

    def test_stale_cheap_listing_floors(self):
        import time
        now = time.time()
        old = now - (self.TTL + 1) * 86400
        slot = {"price": 1, "quantity": 1, "listed_at": old}  # value 1
        self.assertEqual(self.fee(slot, now), self.MIN)

    def test_does_not_mutate(self):
        import time
        now = time.time()
        slot = {"price": 1000, "quantity": 5, "listed_at": now - (self.TTL + 1) * 86400}
        before = dict(slot)
        self.fee(slot, now)
        self.assertEqual(slot, before)


class _FeeStubDB:
    """Records adjust_credits + update_object; serves vendor-droid rows."""

    def __init__(self, droids, broke=False):
        self._droids = droids  # list of obj dicts (with 'data' JSON)
        self.broke = broke
        self.credit_log = []
        self.updates = []

    async def fetchall(self, sql, params=None):
        return list(self._droids)

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        # Mirrors db.adjust_credits keyword-only allow_negative (QA re-run added
        # allow_negative=False at the relist-fee site). A broke owner raises (the
        # caller treats that as "not charged"); a funded owner is charged.
        if self.broke:
            raise RuntimeError("insufficient funds")
        self.credit_log.append((cid, delta, source))
        return 0

    async def update_object(self, oid, **fields):
        self.updates.append((oid, fields))


def _droid(inv, owner_id=1, oid=10):
    return {"id": oid, "owner_id": owner_id, "room_id": 500,
            "name": "Droid", "data": json.dumps({"inventory": inv, "shop_name": "Shop"})}


class TestListingFeeTick(unittest.TestCase):
    def setUp(self):
        from engine.vendor_droids import tick_listing_fees, _LISTING_TTL_DAYS
        self.tick = tick_listing_fees
        self.TTL = _LISTING_TTL_DAYS

    def _old(self):
        import time
        return time.time() - (self.TTL + 1) * 86400

    def test_stale_slot_charges_owner_via_relist_tag(self):
        slot = {"item_key": "x", "price": 1000, "quantity": 5, "listed_at": self._old()}
        db = _FeeStubDB([_droid([slot])])
        _run(self.tick(db, None))
        self.assertEqual(len(db.credit_log), 1)
        cid, delta, source = db.credit_log[0]
        self.assertEqual(cid, 1)
        self.assertLess(delta, 0)
        self.assertEqual(source, "vendor_relist_fee")
        self.assertTrue(db.updates, "listed_at refresh must persist")

    def test_fresh_slot_is_not_charged(self):
        import time
        slot = {"item_key": "x", "price": 1000, "quantity": 5, "listed_at": time.time()}
        db = _FeeStubDB([_droid([slot])])
        _run(self.tick(db, None))
        self.assertEqual(db.credit_log, [])

    def test_legacy_slot_is_stamped_not_charged(self):
        slot = {"item_key": "x", "price": 1000, "quantity": 5}  # no listed_at
        db = _FeeStubDB([_droid([slot])])
        _run(self.tick(db, None))
        self.assertEqual(db.credit_log, [])          # not billed this cycle
        self.assertTrue(db.updates, "legacy slot should be stamped with a clock")

    def test_broke_owner_does_not_crash_or_lose_listing(self):
        slot = {"item_key": "x", "price": 1000, "quantity": 5, "listed_at": self._old()}
        db = _FeeStubDB([_droid([slot])], broke=True)
        _run(self.tick(db, None))  # adjust_credits raises; must be swallowed
        self.assertEqual(db.credit_log, [])
        # the slot's clock is still refreshed (data persisted), listing intact
        self.assertTrue(db.updates)


if __name__ == "__main__":
    unittest.main(verbosity=2)
