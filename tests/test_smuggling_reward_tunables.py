# -*- coding: utf-8 -*-
"""tests/test_smuggling_reward_tunables.py — T3.19 config breadth for the
procedurally-generated smuggling reward model (engine/smuggling.py).

The smuggling board's reward levers — the per-tier TIER_PAY_RANGE credit bands,
the multi-planet ROUTE_TIERS pay overrides, the ROUTE_SPAWN_WEIGHTS spawn-rarity
weights, and the FINE_FRACTION bust SINK — were hardcoded module constants. An
operator could OBSERVE the smuggling faucet via the ``@balance objectives`` board
(the per-kind start→complete funnel + its `reward` column, tagged `smuggling` —
the third leg of that board's reward triad after mission + bounty) but could not
TUNE the model without a code edit + redeploy. This drop externalizes the whole
PAY model to data/tunables.yaml under ``smuggling.*`` and reads it at the USE SITE
through live accessors, closing the observe→tune loop.

Smuggling has TWO pay paths — a direct per-tier job and a multi-planet ROUTE job
(the live board uses both: a guaranteed grey-market tier job + weighted-random
routes) — so the route bands are SEPARATE levers from the tier bands; both are
covered here so neither lever is a phantom. The patrol-chance / scrutiny
difficulty levers are a distinct (encounters) board and stay hardcoded for now.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), overrides flow through the REAL decider (generate_job),
pay magnitudes clamp >= 0 with hi >= lo (random.randint can never get an empty
range), a zeroed route-weight set falls back so random.choices can't raise, the
fine fraction clamps to [0, 1] (a bad value can neither pay the smuggler on a
bust nor confiscate more than the reward), present-but-null + non-numeric values
fall back to the in-code default, and the shipped data/tunables.yaml carries
every key at its in-code default (a drift pin).

Run: python -m pytest tests/test_smuggling_reward_tunables.py
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import smuggling as sm  # noqa: E402
from engine import tunables  # noqa: E402
from engine.smuggling import CargoTier  # noqa: E402

REPO = PROJECT_ROOT


# ── Per-tier pay band accessor ────────────────────────────────────────────


class TierPayRangeAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        for tier in CargoTier:
            self.assertEqual(sm._tier_pay_range(tier), sm.TIER_PAY_RANGE[tier],
                             f"{tier} band drifted from TIER_PAY_RANGE default")

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "smuggling.pay_grey_market_min": 250,
            "smuggling.pay_grey_market_max": 700,
        })
        self.assertEqual(sm._tier_pay_range(CargoTier.GREY_MARKET), (250, 700))

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["smuggling.pay_grey_market_min"] = -100
        tunables._TUNABLES["smuggling.pay_grey_market_max"] = -50
        self.assertEqual(sm._tier_pay_range(CargoTier.GREY_MARKET), (0, 0))

    def test_hi_clamped_to_lo_when_inverted(self):
        # An inverted band (max < min) would make random.randint(lo, hi) raise.
        tunables._TUNABLES["smuggling.pay_spice_min"] = 9000
        tunables._TUNABLES["smuggling.pay_spice_max"] = 100
        lo, hi = sm._tier_pay_range(CargoTier.SPICE)
        self.assertEqual((lo, hi), (9000, 9000))

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["smuggling.pay_grey_market_max"] = None
        self.assertEqual(sm._tier_pay_range(CargoTier.GREY_MARKET),
                         sm.TIER_PAY_RANGE[CargoTier.GREY_MARKET])

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["smuggling.pay_grey_market_min"] = "cheap"
        lo, _ = sm._tier_pay_range(CargoTier.GREY_MARKET)
        self.assertEqual(lo, sm.TIER_PAY_RANGE[CargoTier.GREY_MARKET][0])

    def test_float_truncates_to_int(self):
        tunables._TUNABLES["smuggling.pay_grey_market_min"] = 250.9
        lo, _ = sm._tier_pay_range(CargoTier.GREY_MARKET)
        self.assertEqual(lo, 250)


# ── Multi-planet route pay band accessor ──────────────────────────────────


class RoutePayRangeAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        for key, (_t, _planet, (lo, hi), _patrol) in sm.ROUTE_TIERS.items():
            self.assertEqual(sm._route_pay_range(key, lo, hi), (lo, hi),
                             f"route {key} band drifted from ROUTE_TIERS default")

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "smuggling.route_spicerun_pay_min": 4000,
            "smuggling.route_spicerun_pay_max": 9000,
        })
        self.assertEqual(sm._route_pay_range("spicerun", 3000, 6000), (4000, 9000))

    def test_negative_clamps_and_inversion_guarded(self):
        tunables._TUNABLES["smuggling.route_corerun_pay_min"] = 8000
        tunables._TUNABLES["smuggling.route_corerun_pay_max"] = -5
        lo, hi = sm._route_pay_range("corerun", 4000, 8000)
        self.assertEqual((lo, hi), (8000, 8000))  # max clamps to 0 then hi=max(lo,0)=lo


# ── Route spawn-weight accessor ───────────────────────────────────────────


class RouteWeightsAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        keys, weights = sm._route_weights()
        self.assertEqual(keys, list(sm.ROUTE_TIERS.keys()))
        self.assertEqual(weights, [sm.ROUTE_SPAWN_WEIGHTS[k] for k in keys])

    def test_override_takes_effect(self):
        tunables._TUNABLES["smuggling.route_weight_corerun"] = 99
        keys, weights = sm._route_weights()
        self.assertEqual(weights[keys.index("corerun")], 99)

    def test_zeroed_set_falls_back_to_in_code(self):
        for k in sm.ROUTE_TIERS:
            tunables._TUNABLES[f"smuggling.route_weight_{k}"] = 0
        keys, weights = sm._route_weights()
        # all-zero would make random.choices raise — accessor restores in-code weights
        self.assertEqual(weights, [sm.ROUTE_SPAWN_WEIGHTS[k] for k in keys])
        self.assertGreater(sum(weights), 0)

    def test_negative_weight_clamps_to_zero(self):
        tunables._TUNABLES["smuggling.route_weight_local"] = -40
        keys, weights = sm._route_weights()
        self.assertEqual(weights[keys.index("local")], 0)

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["smuggling.route_weight_local"] = "many"
        keys, weights = sm._route_weights()
        self.assertEqual(weights[keys.index("local")], sm.ROUTE_SPAWN_WEIGHTS["local"])


# ── Fine-fraction (bust SINK) accessor ────────────────────────────────────


class FineFractionAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(sm._fine_fraction(CargoTier.GREY_MARKET), sm.FINE_FRACTION)
        self.assertEqual(sm._fine_fraction(CargoTier.BLACK_MARKET), sm.FINE_FRACTION)
        self.assertEqual(sm._fine_fraction(CargoTier.CONTRABAND), 0.25)
        self.assertEqual(sm._fine_fraction(CargoTier.SPICE), 0.25)

    def test_apex_tier_keeps_more_than_default(self):
        # The economy-audit invariant the old test_tier2_tuning_batch pins.
        self.assertLess(sm._fine_fraction(CargoTier.SPICE), sm.FINE_FRACTION)

    def test_unknown_tier_uses_default_key(self):
        self.assertEqual(sm._fine_fraction("???"), sm.FINE_FRACTION)
        tunables._TUNABLES["smuggling.fine_fraction_default"] = 0.40
        self.assertEqual(sm._fine_fraction("???"), 0.40)

    def test_override_takes_effect(self):
        tunables._TUNABLES["smuggling.fine_fraction_spice"] = 0.10
        self.assertEqual(sm._fine_fraction(CargoTier.SPICE), 0.10)

    def test_clamps_to_unit_interval(self):
        tunables._TUNABLES["smuggling.fine_fraction_grey_market"] = -0.5
        self.assertEqual(sm._fine_fraction(CargoTier.GREY_MARKET), 0.0)
        tunables._TUNABLES["smuggling.fine_fraction_grey_market"] = 2.0
        self.assertEqual(sm._fine_fraction(CargoTier.GREY_MARKET), 1.0)

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["smuggling.fine_fraction_contraband"] = None
        self.assertEqual(sm._fine_fraction(CargoTier.CONTRABAND), 0.25)

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["smuggling.fine_fraction_spice"] = "half"
        self.assertEqual(sm._fine_fraction(CargoTier.SPICE), 0.25)


# ── End-to-end: overrides flow through the live decider ───────────────────


class EndToEndGenerateJob(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        random.seed(7)

    def tearDown(self):
        tunables.reset_tunables()

    def test_tier_pay_override_flows_into_reward(self):
        tunables._TUNABLES.update({
            "smuggling.pay_grey_market_min": 1000,
            "smuggling.pay_grey_market_max": 1000,
        })
        job = sm.generate_job(CargoTier.GREY_MARKET)
        self.assertEqual(job.reward, 1000)  # band collapsed to a point; rounds to 50

    def test_route_pay_override_flows_into_reward(self):
        tunables._TUNABLES.update({
            "smuggling.route_spicerun_pay_min": 7000,
            "smuggling.route_spicerun_pay_max": 7000,
        })
        job = sm.generate_job(route_key="spicerun")
        self.assertEqual(job.reward, 7000)
        self.assertEqual(job.tier, CargoTier.CONTRABAND)  # tier unchanged by pay lever

    def test_fine_override_flows_into_fine(self):
        tunables._TUNABLES.update({
            "smuggling.pay_grey_market_min": 1000,
            "smuggling.pay_grey_market_max": 1000,
            "smuggling.fine_fraction_grey_market": 0.10,
        })
        job = sm.generate_job(CargoTier.GREY_MARKET)
        self.assertEqual(job.fine, 100)  # 0.10 * 1000

    def test_behaviour_identical_to_legacy_when_unset(self):
        # Frozen against the pre-externalization numbers: a grey-market job pays
        # in [200,500] (rounded to 50) with a 50% fine.
        for _ in range(40):
            job = sm.generate_job(CargoTier.GREY_MARKET)
            self.assertTrue(200 <= job.reward <= 500)
            self.assertEqual(job.reward % 50, 0)
            self.assertEqual(job.fine, int(job.reward * 0.50))

    def test_zeroed_route_weights_still_generate_a_board(self):
        for k in sm.ROUTE_TIERS:
            tunables._TUNABLES[f"smuggling.route_weight_{k}"] = 0
        board = sm.generate_board()  # must not raise on random.choices
        self.assertTrue(len(board) >= sm.BOARD_MIN)
        self.assertTrue(all(j.reward > 0 for j in board))


# ── Shipped-YAML drift pin ────────────────────────────────────────────────


class ShippedYamlDriftPin(unittest.TestCase):
    """Every smuggling.* key in the shipped tunables.yaml must equal its in-code
    default — so the YAML stays behaviour-identical (purely additive) and a future
    constant edit that forgets the YAML (or vice-versa) fails loudly here."""

    def setUp(self):
        tunables.reset_tunables()
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))

    def tearDown(self):
        tunables.reset_tunables()

    def _expected(self) -> dict:
        exp: dict[str, float] = {}
        for tier in CargoTier:
            name = tier.name.lower()
            lo, hi = sm.TIER_PAY_RANGE[tier]
            exp[f"smuggling.pay_{name}_min"] = lo
            exp[f"smuggling.pay_{name}_max"] = hi
        for key, (_t, _planet, (lo, hi), _patrol) in sm.ROUTE_TIERS.items():
            exp[f"smuggling.route_{key}_pay_min"] = lo
            exp[f"smuggling.route_{key}_pay_max"] = hi
        for key, w in sm.ROUTE_SPAWN_WEIGHTS.items():
            exp[f"smuggling.route_weight_{key}"] = w
        for tier, frac in sm.FINE_FRACTION_BY_TIER.items():
            exp[f"smuggling.fine_fraction_{tier.name.lower()}"] = frac
        exp["smuggling.fine_fraction_default"] = sm.FINE_FRACTION
        return exp

    def test_every_key_matches_in_code_default(self):
        for key, val in self._expected().items():
            self.assertEqual(tunables.get_tunable(key, "MISSING"), val,
                             f"{key} drifted between tunables.yaml and the constant")

    def test_no_stray_smuggling_keys(self):
        shipped = {k for k in tunables._TUNABLES if k.startswith("smuggling.")}
        expected = set(self._expected())
        self.assertEqual(shipped, expected,
                         f"unexpected/missing smuggling.* keys: {shipped ^ expected}")

    def test_accessors_match_shipped_yaml(self):
        # With the file loaded, the live accessors equal the in-code model.
        for tier in CargoTier:
            self.assertEqual(sm._tier_pay_range(tier), sm.TIER_PAY_RANGE[tier])
            self.assertEqual(sm._fine_fraction(tier),
                             sm.FINE_FRACTION_BY_TIER.get(tier, sm.FINE_FRACTION))
        keys, weights = sm._route_weights()
        self.assertEqual(weights, [sm.ROUTE_SPAWN_WEIGHTS[k] for k in keys])


# ── Source-scope guard ────────────────────────────────────────────────────


class SourceScopeGuard(unittest.TestCase):
    def test_smuggling_reads_get_tunable(self):
        src = (REPO / "engine" / "smuggling.py").read_text(encoding="utf-8")
        self.assertIn("from engine.tunables import get_tunable", src)
        for name in ("_tier_pay_range", "_route_pay_range", "_route_weights"):
            self.assertIn(f"def {name}", src)
        # the patrol-difficulty levers are deliberately left hardcoded this drop
        self.assertIn("CHECKPOINT_DIFFICULTY_BOOST", src)


if __name__ == "__main__":
    unittest.main()
