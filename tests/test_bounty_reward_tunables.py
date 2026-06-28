# -*- coding: utf-8 -*-
"""tests/test_bounty_reward_tunables.py — T3.19 config breadth for the
procedurally-generated bounty-board reward model (engine/bounty_board.py).

The bounty board's reward levers — the 5-tier PAY_RANGES credit bands, the
TIER_WEIGHTS spawn-rarity weights, and the alive-bonus fraction — were hardcoded
module constants (T3.19 Phase 1 externalized ONLY the superior-tier ceiling
`bounty.reward_superior_max`). An operator could OBSERVE the bounty faucet via
the ``@balance objectives`` board (the per-kind start→complete funnel + its
`reward` column, tagged `bounty`) but could not TUNE the rest of the curve
without a code edit + redeploy. This drop externalizes the whole model to
data/tunables.yaml under ``bounty.*`` and reads it at the USE SITE through live
accessors, closing the observe→tune loop.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override flows through the REAL deciders (_scale_reward
/ _pick_tier / generate_bounty), magnitudes clamp >= 0 (a negative can never pay
a hunter a debit), the band/weight guards keep random.randint / random.choices
from ever raising on bad config, present-but-null + non-numeric values fall back
to the in-code default, and the shipped data/tunables.yaml carries every key at
its in-code default (a drift pin). The pre-existing `bounty.reward_superior_max`
Phase-1 key is preserved (it IS the superior-tier max under the new scheme).

Run: python -m pytest tests/test_bounty_reward_tunables.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import bounty_board as bb  # noqa: E402
from engine import tunables  # noqa: E402
from engine.bounty_board import BountyTier  # noqa: E402

REPO = PROJECT_ROOT


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Accessor tests (pure; no DB) ──────────────────────────────────────────


class PayRangeAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        for tier in BountyTier:
            self.assertEqual(bb._pay_range(tier), bb.PAY_RANGES[tier],
                             f"{tier} band drifted from PAY_RANGES default")

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "bounty.reward_extra_min": 250,
            "bounty.reward_extra_max": 600,
        })
        self.assertEqual(bb._pay_range(BountyTier.EXTRA), (250, 600))

    def test_superior_max_uses_the_phase1_key(self):
        # The Phase-1 key bounty.reward_superior_max IS the superior-tier max
        # under the consistent naming — no orphaned legacy key.
        tunables._TUNABLES["bounty.reward_superior_max"] = 25000
        lo, hi = bb._pay_range(BountyTier.SUPERIOR)
        self.assertEqual(hi, 25000)
        self.assertEqual(lo, bb.PAY_RANGES[BountyTier.SUPERIOR][0])  # 3000

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["bounty.reward_extra_min"] = -100
        tunables._TUNABLES["bounty.reward_extra_max"] = -50
        # both clamp to 0; hi>=lo holds → randint(0,0) is safe
        self.assertEqual(bb._pay_range(BountyTier.EXTRA), (0, 0))

    def test_hi_clamped_to_lo_when_inverted(self):
        # An operator who sets max < min must not make random.randint raise
        # "empty range" — hi is clamped up to lo.
        tunables._TUNABLES["bounty.reward_extra_min"] = 5000
        tunables._TUNABLES["bounty.reward_extra_max"] = 100
        self.assertEqual(bb._pay_range(BountyTier.EXTRA), (5000, 5000))

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["bounty.reward_extra_max"] = None
        lo, hi = bb._pay_range(BountyTier.EXTRA)
        self.assertEqual(hi, bb.PAY_RANGES[BountyTier.EXTRA][1])  # 300

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["bounty.reward_extra_min"] = "cheap"
        lo, hi = bb._pay_range(BountyTier.EXTRA)
        self.assertEqual(lo, bb.PAY_RANGES[BountyTier.EXTRA][0])  # 100

    def test_float_truncates_to_int(self):
        tunables._TUNABLES["bounty.reward_extra_min"] = 250.9
        self.assertEqual(bb._pay_range(BountyTier.EXTRA)[0], 250)


class AliveBonusAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(bb._alive_bonus_pct_range(),
                         (bb.ALIVE_BONUS_MIN_PCT, bb.ALIVE_BONUS_MAX_PCT))

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "bounty.alive_bonus_min_pct": 0.05,
            "bounty.alive_bonus_max_pct": 0.30,
        })
        self.assertEqual(bb._alive_bonus_pct_range(), (0.05, 0.30))

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["bounty.alive_bonus_min_pct"] = -0.10
        lo, hi = bb._alive_bonus_pct_range()
        self.assertEqual(lo, 0.0)

    def test_hi_clamped_to_lo_when_inverted(self):
        tunables._TUNABLES["bounty.alive_bonus_min_pct"] = 0.30
        tunables._TUNABLES["bounty.alive_bonus_max_pct"] = 0.05
        self.assertEqual(bb._alive_bonus_pct_range(), (0.30, 0.30))

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["bounty.alive_bonus_max_pct"] = "lots"
        self.assertEqual(bb._alive_bonus_pct_range()[1], bb.ALIVE_BONUS_MAX_PCT)


class TierWeightAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(bb._tier_weights(), dict(bb.TIER_WEIGHTS))

    def test_override_takes_effect(self):
        tunables._TUNABLES["bounty.tier_weight_superior"] = 50
        self.assertEqual(bb._tier_weights()[BountyTier.SUPERIOR], 50)

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["bounty.tier_weight_extra"] = -5
        self.assertEqual(bb._tier_weights()[BountyTier.EXTRA], 0)

    def test_all_zero_falls_back_to_in_code(self):
        # An operator who zeros every weight must not make random.choices raise
        # "Total of weights must be greater than zero".
        for t in bb.TIER_WEIGHTS:
            tunables._TUNABLES[f"bounty.tier_weight_{t.value}"] = 0
        self.assertEqual(bb._tier_weights(), dict(bb.TIER_WEIGHTS))

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["bounty.tier_weight_extra"] = "many"
        self.assertEqual(bb._tier_weights()[BountyTier.EXTRA],
                         bb.TIER_WEIGHTS[BountyTier.EXTRA])


# ── End-to-end through the real deciders ──────────────────────────────────


class ScaleRewardEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_override_lands_in_new_band(self):
        # Pin a tier's band to a single value → _scale_reward is deterministic.
        tunables._TUNABLES.update({
            "bounty.reward_extra_min": 5000,
            "bounty.reward_extra_max": 5000,
        })
        self.assertEqual(bb._scale_reward(BountyTier.EXTRA), 5000)

    def test_negative_band_never_debits_or_raises(self):
        tunables._TUNABLES.update({
            "bounty.reward_extra_min": -500,
            "bounty.reward_extra_max": -100,
        })
        # randint(0,0) → 0; never a negative reward, never an empty-range raise.
        self.assertEqual(bb._scale_reward(BountyTier.EXTRA), 0)

    def test_inverted_band_does_not_raise(self):
        tunables._TUNABLES.update({
            "bounty.reward_veteran_min": 3000,
            "bounty.reward_veteran_max": 100,
        })
        self.assertEqual(bb._scale_reward(BountyTier.VETERAN), 3000)

    def test_behaviour_identical_to_defaults_when_unset(self):
        for tier in BountyTier:
            lo, hi = bb.PAY_RANGES[tier]
            for _ in range(50):
                r = bb._scale_reward(tier)
                # 50cr rounding can land one step below lo / above hi
                self.assertGreaterEqual(r, lo - 50)
                self.assertLessEqual(r, hi + 50)


class PickTierEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_weight_override_forces_a_tier(self):
        # Give only SUPERIOR a non-zero weight → every draw is SUPERIOR.
        for t in bb.TIER_WEIGHTS:
            tunables._TUNABLES[f"bounty.tier_weight_{t.value}"] = 0
        tunables._TUNABLES["bounty.tier_weight_superior"] = 1
        picks = {bb._pick_tier() for _ in range(50)}
        self.assertEqual(picks, {BountyTier.SUPERIOR})

    def test_all_zero_weights_still_returns_a_valid_tier(self):
        for t in bb.TIER_WEIGHTS:
            tunables._TUNABLES[f"bounty.tier_weight_{t.value}"] = 0
        # falls back to in-code weights — no raise, valid tier
        for _ in range(20):
            self.assertIn(bb._pick_tier(), set(BountyTier))


class _FakeDB:
    """Minimal DB for generate_bounty: rooms, zones, NPC creation."""

    def __init__(self):
        self._next_npc = 1000

    async def list_rooms(self, limit=100):
        return [{"id": 4207, "name": "Cantina Back Room", "zone_id": 1}]

    async def get_all_zones(self):
        return [{"id": 1, "name": "tatooine_mos_eisley"}]

    async def create_npc(self, **kw):
        self._next_npc += 1
        return self._next_npc


class GenerateBountyEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_reward_and_alive_bonus_overrides_flow_through(self):
        # Force the tier (SUPERIOR-only weights), pin its band to a single
        # value, and pin both alive pcts to 0.5 → uniform(0.5, 0.5) == 0.5,
        # so both the reward and the derived alive-bonus are deterministic.
        for t in bb.TIER_WEIGHTS:
            tunables._TUNABLES[f"bounty.tier_weight_{t.value}"] = 0
        tunables._TUNABLES.update({
            "bounty.tier_weight_superior": 1,
            "bounty.reward_superior_min": 8000,
            "bounty.reward_superior_max": 8000,
            "bounty.alive_bonus_min_pct": 0.5,
            "bounty.alive_bonus_max_pct": 0.5,
        })
        contract = _run(bb.generate_bounty(_FakeDB()))
        self.assertIsNotNone(contract, "generate_bounty returned None")
        self.assertEqual(contract.tier, BountyTier.SUPERIOR)
        self.assertEqual(contract.reward, 8000)
        # alive_bonus = round(8000 * 0.5 / 50) * 50 == 4000
        self.assertEqual(contract.reward_alive_bonus, 4000)


# ── Shipped-YAML drift pins ───────────────────────────────────────────────


class ShippedYaml(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_every_key_at_in_code_default(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for tier in BountyTier:
            lo, hi = bb.PAY_RANGES[tier]
            self.assertEqual(
                tunables.get_tunable(f"bounty.reward_{tier.value}_min", -1), lo)
            self.assertEqual(
                tunables.get_tunable(f"bounty.reward_{tier.value}_max", -1), hi)
            self.assertEqual(
                tunables.get_tunable(f"bounty.tier_weight_{tier.value}", -1),
                bb.TIER_WEIGHTS[tier])
        self.assertEqual(
            tunables.get_tunable("bounty.alive_bonus_min_pct", -1),
            bb.ALIVE_BONUS_MIN_PCT)
        self.assertEqual(
            tunables.get_tunable("bounty.alive_bonus_max_pct", -1),
            bb.ALIVE_BONUS_MAX_PCT)

    def test_shipped_yaml_is_behaviour_identical(self):
        # With the real YAML loaded, the accessors equal the in-code defaults.
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for tier in BountyTier:
            self.assertEqual(bb._pay_range(tier), bb.PAY_RANGES[tier])
        self.assertEqual(bb._tier_weights(), dict(bb.TIER_WEIGHTS))
        self.assertEqual(bb._alive_bonus_pct_range(),
                         (bb.ALIVE_BONUS_MIN_PCT, bb.ALIVE_BONUS_MAX_PCT))

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for tier in BountyTier:
            self.assertIn(f"bounty.reward_{tier.value}_min:", ty)
            self.assertIn(f"bounty.reward_{tier.value}_max:", ty)
            self.assertIn(f"bounty.tier_weight_{tier.value}:", ty)
        self.assertIn("bounty.alive_bonus_min_pct:", ty)
        self.assertIn("bounty.alive_bonus_max_pct:", ty)

    def test_accessors_read_at_use_site(self):
        src = (REPO / "engine" / "bounty_board.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable(f"bounty.reward_{name}_min"', src)
        self.assertIn('get_tunable(f"bounty.reward_{name}_max"', src)
        self.assertIn('get_tunable("bounty.alive_bonus_min_pct"', src)
        self.assertIn('get_tunable(f"bounty.tier_weight_{t.value}"', src)
        # _scale_reward / _pick_tier route through the accessors, not the raw
        # constants — guard against a regression that re-freezes them at import.
        self.assertIn("lo, hi = _pay_range(tier)", src)
        self.assertIn("weights_map = _tier_weights()", src)


if __name__ == "__main__":
    unittest.main()
