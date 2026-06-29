# -*- coding: utf-8 -*-
"""tests/test_mission_reward_tunables.py — T3.19 config breadth for the
procedurally-generated mission-board reward model (engine/missions.py).

The mission board's reward levers — the 14-type PAY_RANGES credit bands, the
SPAWN_WEIGHTS spawn-rarity weights (ground types), and the DISTRESS_REWARD_BONUS
emergency premium — were hardcoded module constants (T3.19 Phase 1 externalized
ONLY the smuggling-tier ceiling `mission.reward_smuggling_max`). An operator
could OBSERVE the mission faucet via the ``@balance objectives`` board (the
per-kind start→complete funnel + its `reward` column, the `mission` rows) but
could not TUNE the rest of the curve without a code edit + redeploy. This drop
externalizes the whole model to data/tunables.yaml under ``mission.*`` and reads
it at the USE SITE through live accessors, closing the observe→tune loop.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override flows through the REAL deciders (_scale_reward
/ _pick_type / distress_mission_bonus / generate_board), magnitudes clamp >= 0
(a negative can never pay a debit), the band/weight guards keep random.randint /
random.choices from ever raising on bad config, present-but-null + non-numeric
values fall back to the in-code default, and the shipped data/tunables.yaml
carries every key at its in-code default (a drift pin). The pre-existing
`mission.reward_smuggling_max` Phase-1 key is preserved (it IS the smuggling-type
max under the new scheme — no orphaned legacy key).

Run: python -m pytest tests/test_mission_reward_tunables.py
"""
from __future__ import annotations

import random
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import missions as ms  # noqa: E402
from engine import tunables  # noqa: E402
from engine.missions import MissionType  # noqa: E402

REPO = PROJECT_ROOT


# ── Accessor tests (pure; no DB) ──────────────────────────────────────────


class PayRangeAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        for mt in MissionType:
            self.assertEqual(ms._pay_range(mt), ms.PAY_RANGES[mt],
                             f"{mt} band drifted from PAY_RANGES default")

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "mission.reward_combat_min": 700,
            "mission.reward_combat_max": 1800,
        })
        self.assertEqual(ms._pay_range(MissionType.COMBAT), (700, 1800))

    def test_smuggling_max_uses_the_phase1_key(self):
        # The Phase-1 key mission.reward_smuggling_max IS the smuggling-type max
        # under the consistent naming — no orphaned legacy key.
        tunables._TUNABLES["mission.reward_smuggling_max"] = 12000
        lo, hi = ms._pay_range(MissionType.SMUGGLING)
        self.assertEqual(hi, 12000)
        self.assertEqual(lo, ms.PAY_RANGES[MissionType.SMUGGLING][0])  # 500

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["mission.reward_combat_min"] = -100
        tunables._TUNABLES["mission.reward_combat_max"] = -50
        self.assertEqual(ms._pay_range(MissionType.COMBAT), (0, 0))

    def test_hi_clamped_to_lo_when_inverted(self):
        tunables._TUNABLES["mission.reward_combat_min"] = 5000
        tunables._TUNABLES["mission.reward_combat_max"] = 100
        self.assertEqual(ms._pay_range(MissionType.COMBAT), (5000, 5000))

    def test_present_but_null_falls_back(self):
        tunables._TUNABLES["mission.reward_combat_max"] = None
        lo, hi = ms._pay_range(MissionType.COMBAT)
        self.assertEqual(hi, ms.PAY_RANGES[MissionType.COMBAT][1])  # 1000

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["mission.reward_combat_min"] = "cheap"
        lo, hi = ms._pay_range(MissionType.COMBAT)
        self.assertEqual(lo, ms.PAY_RANGES[MissionType.COMBAT][0])  # 300

    def test_float_truncates_to_int(self):
        tunables._TUNABLES["mission.reward_combat_min"] = 350.9
        self.assertEqual(ms._pay_range(MissionType.COMBAT)[0], 350)


class SpawnWeightAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(ms._spawn_weights(), dict(ms.SPAWN_WEIGHTS))

    def test_override_takes_effect(self):
        tunables._TUNABLES["mission.spawn_weight_social"] = 40
        self.assertEqual(ms._spawn_weights()[MissionType.SOCIAL], 40)

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["mission.spawn_weight_social"] = -5
        self.assertEqual(ms._spawn_weights()[MissionType.SOCIAL], 0)

    def test_all_zero_falls_back_to_in_code(self):
        # An operator who zeros every weight must not make random.choices raise
        # "Total of weights must be greater than zero".
        for t in ms.SPAWN_WEIGHTS:
            tunables._TUNABLES[f"mission.spawn_weight_{t.value}"] = 0
        self.assertEqual(ms._spawn_weights(), dict(ms.SPAWN_WEIGHTS))

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["mission.spawn_weight_social"] = "many"
        self.assertEqual(ms._spawn_weights()[MissionType.SOCIAL],
                         ms.SPAWN_WEIGHTS[MissionType.SOCIAL])


class DistressBonusAccessor(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_default_when_unset(self):
        self.assertEqual(ms._distress_bonus_pct(), ms.DISTRESS_REWARD_BONUS)

    def test_override_takes_effect(self):
        tunables._TUNABLES["mission.distress_reward_bonus_pct"] = 0.75
        self.assertEqual(ms._distress_bonus_pct(), 0.75)

    def test_negative_clamps_to_zero(self):
        tunables._TUNABLES["mission.distress_reward_bonus_pct"] = -0.5
        self.assertEqual(ms._distress_bonus_pct(), 0.0)

    def test_bad_value_falls_back(self):
        tunables._TUNABLES["mission.distress_reward_bonus_pct"] = "lots"
        self.assertEqual(ms._distress_bonus_pct(), ms.DISTRESS_REWARD_BONUS)

    def test_flows_through_distress_mission_bonus(self):
        # +100% premium → a 1000cr mission pays 2000 (rounded to 50cr).
        tunables._TUNABLES["mission.distress_reward_bonus_pct"] = 1.0
        self.assertEqual(ms.distress_mission_bonus(1000, True), 2000)
        # negative clamps → no premium, base reward unchanged.
        tunables._TUNABLES["mission.distress_reward_bonus_pct"] = -1.0
        self.assertEqual(ms.distress_mission_bonus(1000, True), 1000)


# ── End-to-end through the real deciders ──────────────────────────────────


class ScaleRewardEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_override_lands_in_new_band(self):
        # Pin a type's band to a single value → _scale_reward is deterministic.
        tunables._TUNABLES.update({
            "mission.reward_combat_min": 4000,
            "mission.reward_combat_max": 4000,
        })
        for sl in (1, 3, 6):
            random.seed(sl)
            self.assertEqual(ms._scale_reward(MissionType.COMBAT, sl), 4000)

    def test_smuggling_phase1_key_still_collapses_band(self):
        # Regression mirror of the Phase-1 behaviour: setting only the max to lo
        # collapses the band deterministically (min defaults to 500).
        tunables._TUNABLES["mission.reward_smuggling_max"] = 500
        for sl in (1, 3, 6):
            random.seed(sl)
            self.assertEqual(ms._scale_reward(MissionType.SMUGGLING, sl), 500)

    def test_negative_band_never_debits_or_raises(self):
        tunables._TUNABLES.update({
            "mission.reward_combat_min": -500,
            "mission.reward_combat_max": -100,
        })
        for sl in (1, 3, 6):
            random.seed(sl)
            self.assertEqual(ms._scale_reward(MissionType.COMBAT, sl), 0)

    def test_inverted_band_does_not_raise(self):
        tunables._TUNABLES.update({
            "mission.reward_combat_min": 3000,
            "mission.reward_combat_max": 100,
        })
        random.seed(0)
        self.assertEqual(ms._scale_reward(MissionType.COMBAT, 3), 3000)

    def test_behaviour_identical_to_defaults_when_unset(self):
        for mt in MissionType:
            lo, hi = ms.PAY_RANGES[mt]
            for _ in range(40):
                r = ms._scale_reward(mt)
                # 50cr rounding can land one step below lo / above hi
                self.assertGreaterEqual(r, lo - 50)
                self.assertLessEqual(r, hi + 50)


class PickTypeEndToEnd(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()
        # Null the Director singleton so _pick_type's alert-bias path sees an
        # empty-zone director (no bias fires) — bulletproof determinism even if
        # a prior full-suite test populated the singleton's zones.
        from engine import director
        director._director = None

    def tearDown(self):
        tunables.reset_tunables()
        from engine import director
        director._director = None

    def test_weight_override_forces_a_type(self):
        # Give only SLICING a non-zero weight → every draw is SLICING.
        # (Director bias can ADD to smuggling/bounty/combat, so pick a type the
        # alert-bias code never touches to keep the assertion deterministic.)
        for t in ms.SPAWN_WEIGHTS:
            tunables._TUNABLES[f"mission.spawn_weight_{t.value}"] = 0
        tunables._TUNABLES["mission.spawn_weight_slicing"] = 1
        picks = {ms._pick_type() for _ in range(50)}
        self.assertEqual(picks, {MissionType.SLICING})

    def test_all_zero_weights_still_returns_a_valid_type(self):
        for t in ms.SPAWN_WEIGHTS:
            tunables._TUNABLES[f"mission.spawn_weight_{t.value}"] = 0
        for _ in range(20):
            self.assertIn(ms._pick_type(), set(MissionType))


class GenerateBoardGuard(unittest.TestCase):
    """The guaranteed-delivery slot rolls randint(lo, hi//2); a collapsed
    delivery band (hi//2 < lo) must not make randint raise."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_collapsed_delivery_band_does_not_raise(self):
        tunables._TUNABLES.update({
            "mission.reward_delivery_min": 100,
            "mission.reward_delivery_max": 100,  # hi//2 == 50 < lo == 100
        })
        board = ms.generate_board(count=ms.BOARD_MIN)
        self.assertTrue(board)
        delivery = next(m for m in board
                        if m.mission_type == MissionType.DELIVERY)
        self.assertEqual(delivery.reward, 100)


# ── Shipped-YAML drift pins ───────────────────────────────────────────────


class ShippedYaml(unittest.TestCase):
    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_every_key_at_in_code_default(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for mt in MissionType:
            lo, hi = ms.PAY_RANGES[mt]
            self.assertEqual(
                tunables.get_tunable(f"mission.reward_{mt.value}_min", -1), lo,
                f"{mt} min drifted")
            self.assertEqual(
                tunables.get_tunable(f"mission.reward_{mt.value}_max", -1), hi,
                f"{mt} max drifted")
        for t, w in ms.SPAWN_WEIGHTS.items():
            self.assertEqual(
                tunables.get_tunable(f"mission.spawn_weight_{t.value}", -1), w,
                f"{t} weight drifted")
        self.assertEqual(
            tunables.get_tunable("mission.distress_reward_bonus_pct", -1),
            ms.DISTRESS_REWARD_BONUS)

    def test_back_compat_smuggling_max_preserved(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        # The Phase-1 key is still shipped at its original value.
        self.assertEqual(
            tunables.get_tunable("mission.reward_smuggling_max", -1), 5000)

    def test_shipped_yaml_is_behaviour_identical(self):
        # With the real YAML loaded, the accessors equal the in-code defaults.
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for mt in MissionType:
            self.assertEqual(ms._pay_range(mt), ms.PAY_RANGES[mt])
        self.assertEqual(ms._spawn_weights(), dict(ms.SPAWN_WEIGHTS))
        self.assertEqual(ms._distress_bonus_pct(), ms.DISTRESS_REWARD_BONUS)

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for mt in MissionType:
            self.assertIn(f"mission.reward_{mt.value}_min:", ty)
            self.assertIn(f"mission.reward_{mt.value}_max:", ty)
        for t in ms.SPAWN_WEIGHTS:
            self.assertIn(f"mission.spawn_weight_{t.value}:", ty)
        self.assertIn("mission.distress_reward_bonus_pct:", ty)

    def test_accessors_read_at_use_site(self):
        src = (REPO / "engine" / "missions.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable(f"mission.reward_{name}_min"', src)
        self.assertIn('get_tunable(f"mission.reward_{name}_max"', src)
        self.assertIn('get_tunable(f"mission.spawn_weight_{t.value}"', src)
        self.assertIn('get_tunable("mission.distress_reward_bonus_pct"', src)
        # the deciders route through the accessors, not the raw constants —
        # guard against a regression that re-freezes them at import.
        self.assertIn("lo, hi = _pay_range(mission_type)", src)
        self.assertIn("weights = _spawn_weights()", src)
        self.assertIn("_distress_bonus_pct()", src)


if __name__ == "__main__":
    unittest.main()
