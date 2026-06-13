# -*- coding: utf-8 -*-
"""
tests/test_worldevent_flag_consumers.py — WORLDEVENT.flag_effect_consumers.

Wires thin consumers for world-event FLAG effects that were fired but
never read, mirroring the contraband_scan precedent (read the flag at one
existing seam → modulate a deterministic, separately-unit-testable
outcome). Built one flag per increment:

  * Consumer 1 — `rare_vendor` (MERCHANT_ARRIVAL): the buy command
    discounts the pre-haggle base price via
    engine.world_events.apply_rare_vendor_discount.
  * Consumer 2 — `krayt_bounty` (KRAYT_SIGHTING): generate_bounty bumps a
    newly-posted contract one tier toward SUPERIOR via
    engine.bounty_board.krayt_upgrade_tier.

Remaining (own future increments): brawl_active (CANTINA_BRAWL),
distress_active (DISTRESS_SIGNAL), hutt_auction (HUTT_AUCTION).

Each consumer: a pure modulator (tested without the manager) + the
manager-driven flag path (activate the event, assert the flag drives the
modulation). World-events singleton reset (engine.world_events._manager =
None) per the CLAUDE.md test-isolation rule.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _WorldEventBase(unittest.TestCase):
    def setUp(self):
        import engine.world_events as we
        we._manager = None

    def tearDown(self):
        import engine.world_events as we
        we._manager = None


class TestRareVendorModulator(_WorldEventBase):
    """The pure function — no manager needed."""

    def test_discount_applied_when_active(self):
        from engine.world_events import (
            apply_rare_vendor_discount, RARE_VENDOR_DISCOUNT,
        )
        base = 1000
        out = apply_rare_vendor_discount(base, True)
        self.assertEqual(out, int(round(base * (1.0 - RARE_VENDOR_DISCOUNT))))
        self.assertLess(out, base)

    def test_no_change_when_inactive(self):
        from engine.world_events import apply_rare_vendor_discount
        self.assertEqual(apply_rare_vendor_discount(1000, False), 1000)

    def test_floors_at_one(self):
        from engine.world_events import apply_rare_vendor_discount
        # A 1-credit item discounted still costs at least 1.
        self.assertGreaterEqual(apply_rare_vendor_discount(1, True), 1)

    def test_zero_or_negative_base_unchanged(self):
        from engine.world_events import apply_rare_vendor_discount
        self.assertEqual(apply_rare_vendor_discount(0, True), 0)
        self.assertEqual(apply_rare_vendor_discount(-5, True), -5)


class TestRareVendorFlagPath(_WorldEventBase):
    """The manager-driven path the buy command uses."""

    def test_flag_false_with_no_event(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        self.assertFalse(mgr.get_effect("rare_vendor", False))

    def test_merchant_arrival_sets_rare_vendor_flag(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        ev = mgr.activate_event("merchant_arrival")
        self.assertIsNotNone(ev, "merchant_arrival should be a valid event")
        self.assertTrue(mgr.get_effect("rare_vendor", False))

    def test_end_to_end_flag_drives_discount(self):
        from engine.world_events import (
            get_world_event_manager, apply_rare_vendor_discount,
        )
        mgr = get_world_event_manager()
        # No event: full price.
        base = 800
        active = bool(mgr.get_effect("rare_vendor", False))
        self.assertEqual(apply_rare_vendor_discount(base, active), base)
        # Activate: discounted.
        mgr.activate_event("merchant_arrival")
        active = bool(mgr.get_effect("rare_vendor", False))
        self.assertLess(apply_rare_vendor_discount(base, active), base)


# ─────────────────────────────────────────────────────────────────────
# Consumer 2 of 5: krayt_bounty (KRAYT_SIGHTING) — bounty tier upgrade
# ─────────────────────────────────────────────────────────────────────


class TestKraytBountyModulator(_WorldEventBase):
    """The pure tier-upgrade function."""

    def test_upgrade_bumps_one_tier_when_active(self):
        from engine.bounty_board import krayt_upgrade_tier, BountyTier
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.EXTRA, True), BountyTier.AVERAGE)
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.VETERAN, True), BountyTier.SUPERIOR)

    def test_no_change_when_inactive(self):
        from engine.bounty_board import krayt_upgrade_tier, BountyTier
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.EXTRA, False), BountyTier.EXTRA)

    def test_superior_stays_superior(self):
        from engine.bounty_board import krayt_upgrade_tier, BountyTier
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.SUPERIOR, True), BountyTier.SUPERIOR)


class TestKraytBountyFlagPath(_WorldEventBase):
    """The manager-driven path generate_bounty uses."""

    def test_krayt_sighting_sets_flag(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        ev = mgr.activate_event("krayt_sighting")
        self.assertIsNotNone(ev, "krayt_sighting should be a valid event")
        self.assertTrue(mgr.get_effect("krayt_bounty", False))

    def test_end_to_end_flag_drives_upgrade(self):
        from engine.world_events import get_world_event_manager
        from engine.bounty_board import krayt_upgrade_tier, BountyTier
        mgr = get_world_event_manager()
        # No event: tier unchanged.
        active = bool(mgr.get_effect("krayt_bounty", False))
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.NOVICE, active), BountyTier.NOVICE)
        # Activate: tier bumped.
        mgr.activate_event("krayt_sighting")
        active = bool(mgr.get_effect("krayt_bounty", False))
        self.assertEqual(
            krayt_upgrade_tier(BountyTier.NOVICE, active), BountyTier.VETERAN)


# ─────────────────────────────────────────────────────────────────────
# Consumer 3 of 5: distress_active (DISTRESS_SIGNAL) — mission injection
# ─────────────────────────────────────────────────────────────────────


class TestDistressModulator(_WorldEventBase):
    def test_bonus_applied_when_active(self):
        from engine.missions import (
            distress_mission_bonus, DISTRESS_REWARD_BONUS,
        )
        base = 500
        out = distress_mission_bonus(base, True)
        self.assertGreater(out, base)
        self.assertEqual(out, int(round(base * (1.0 + DISTRESS_REWARD_BONUS) / 50) * 50))

    def test_no_change_when_inactive(self):
        from engine.missions import distress_mission_bonus
        self.assertEqual(distress_mission_bonus(500, False), 500)

    def test_zero_reward_unchanged(self):
        from engine.missions import distress_mission_bonus
        self.assertEqual(distress_mission_bonus(0, True), 0)


class TestDistressFlagPath(_WorldEventBase):
    def test_distress_signal_sets_flag(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        ev = mgr.activate_event("distress_signal")
        self.assertIsNotNone(ev)
        self.assertTrue(mgr.get_effect("distress_active", False))

    def test_generate_mission_forces_medical_when_active(self):
        from engine.world_events import get_world_event_manager
        from engine.missions import generate_mission, MissionType
        mgr = get_world_event_manager()
        mgr.activate_event("distress_signal")
        # With the flag live, generated missions are MEDICAL/distress.
        for _ in range(5):
            m = generate_mission()
            self.assertEqual(m.mission_type, MissionType.MEDICAL)
            self.assertTrue(m.title.startswith("DISTRESS:"))


# ─────────────────────────────────────────────────────────────────────
# Consumer 4 of 5: hutt_auction (HUTT_AUCTION) — rep-gated rare purchase
# ─────────────────────────────────────────────────────────────────────


class TestHuttAuctionModulator(_WorldEventBase):
    def test_gate_requires_active_and_rep(self):
        from engine.world_events import hutt_auction_purchase_allowed
        # inactive -> never allowed
        self.assertFalse(hutt_auction_purchase_allowed(99, False, 30))
        # active but rep below gate -> denied
        self.assertFalse(hutt_auction_purchase_allowed(29, True, 30))
        # active + rep at/above gate -> allowed
        self.assertTrue(hutt_auction_purchase_allowed(30, True, 30))
        self.assertTrue(hutt_auction_purchase_allowed(80, True, 30))

    def test_markup_applied_when_active(self):
        from engine.world_events import (
            apply_hutt_auction_markup, HUTT_AUCTION_MARKUP,
        )
        base = 1000
        out = apply_hutt_auction_markup(base, True)
        self.assertGreater(out, base)
        self.assertEqual(out, int(round(base * (1.0 + HUTT_AUCTION_MARKUP))))

    def test_markup_noop_when_inactive(self):
        from engine.world_events import apply_hutt_auction_markup
        self.assertEqual(apply_hutt_auction_markup(1000, False), 1000)

    def test_bad_rep_value_fails_closed(self):
        from engine.world_events import hutt_auction_purchase_allowed
        self.assertFalse(hutt_auction_purchase_allowed(None, True, 30))


class TestHuttAuctionFlagPath(_WorldEventBase):
    def test_hutt_auction_sets_flag_and_gate(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        ev = mgr.activate_event("hutt_auction")
        self.assertIsNotNone(ev)
        self.assertTrue(mgr.get_effect("hutt_auction", False))
        self.assertEqual(mgr.get_effect("criminal_rep_gate", 0), 30)


# ─────────────────────────────────────────────────────────────────────
# Consumer 5 of 5: brawl_active (CANTINA_BRAWL) — forced brawl beat
# ─────────────────────────────────────────────────────────────────────


class TestBrawlModulator(_WorldEventBase):
    def test_forces_brawl_code_when_active(self):
        from engine.cantina_encounters import (
            roll_cantina_encounter, BRAWL_CODE, CANTINA_ENCOUNTERS,
        )
        code, text = roll_cantina_encounter(brawl_active=True)
        self.assertEqual(code, BRAWL_CODE)
        self.assertEqual(text, CANTINA_ENCOUNTERS[BRAWL_CODE])

    def test_random_when_inactive(self):
        # Seeded RNG -> deterministic non-forced roll (proves the flag,
        # not the RNG, drives the brawl).
        import random
        from engine.cantina_encounters import roll_cantina_encounter
        rng = random.Random(1)
        code, _ = roll_cantina_encounter(rng=rng, brawl_active=False)
        self.assertIn(code, range(11, 67))


class TestBrawlFlagPath(_WorldEventBase):
    def test_cantina_brawl_sets_flag(self):
        from engine.world_events import get_world_event_manager
        mgr = get_world_event_manager()
        ev = mgr.activate_event("cantina_brawl")
        self.assertIsNotNone(ev)
        self.assertTrue(mgr.get_effect("brawl_active", False))

    def test_end_to_end_flag_forces_brawl(self):
        from engine.world_events import get_world_event_manager
        from engine.cantina_encounters import roll_cantina_encounter, BRAWL_CODE
        mgr = get_world_event_manager()
        mgr.activate_event("cantina_brawl")
        active = bool(mgr.get_effect("brawl_active", False))
        code, _ = roll_cantina_encounter(brawl_active=active)
        self.assertEqual(code, BRAWL_CODE)


if __name__ == "__main__":
    unittest.main()
