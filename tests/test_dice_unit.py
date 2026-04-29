# -*- coding: utf-8 -*-
"""
tests/test_dice_unit.py — Code review C6 fix tests (drop K-C6d)

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`engine/dice.py` is the canonical D6 dice engine — every roll in the
game funnels through it (combat, skill checks, bargain, repair, etc.),
so a regression here is uniquely catastrophic. This file adds
unit-test coverage of the deterministic surface and stochastic
surface (with `random.seed`), covering:

  - DicePool: pip carry/borrow normalization (5D-1 must NOT corrupt
    to 5D), parse('4D+2'), parse('5D-1'), parse('3D'), parse('0D'),
    arithmetic, stringify, total_pips.
  - WildDieResult / RollResult / CheckResult / OpposedResult shapes.
  - Difficulty.from_name and Difficulty.describe (label ladder).
  - Scale.difference (cross-scale arithmetic).
  - roll_die: range [1,6].
  - roll_wild_die: explosion on 6, complication on 1, normal on 2-5.
  - roll_d6_pool: zero-dice path, complication-removes-highest path,
    pip floor (max 1), pip-only path (0 dice).
  - difficulty_check / opposed_roll: success and tie semantics.
  - apply_multi_action_penalty: -1D per extra action.
  - apply_wound_penalty: -XD with floor.
  - apply_scale_modifier: absolute scale-difference dice.
  - roll_cp_die / roll_cp_dice: explodes on 6, NO mishap on 1.
  - apply_force_point: doubles dice AND pips.

Stochastic functions are tested by seeding `random` so the harness
is deterministic.
"""
import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.dice import (  # noqa: E402
    CheckResult,
    Difficulty,
    DicePool,
    OpposedResult,
    RollResult,
    Scale,
    WildDieResult,
    apply_force_point,
    apply_multi_action_penalty,
    apply_scale_modifier,
    apply_wound_penalty,
    difficulty_check,
    opposed_roll,
    roll_cp_dice,
    roll_cp_die,
    roll_d6_pool,
    roll_die,
    roll_pool_str,
    roll_wild_die,
)


# ══════════════════════════════════════════════════════════════════════════════
# DicePool — normalization
# ══════════════════════════════════════════════════════════════════════════════


class TestDicePoolNormalization(unittest.TestCase):
    """__post_init__ should carry overflow pips into dice and never produce
    negative pips. The 5D-1 → must-not-corrupt-to-5D case is from project
    user-memory: WEG D6 R&E negative-pip normalization is a known footgun.
    """

    def test_zero_pool(self):
        p = DicePool(0, 0)
        self.assertEqual(p.dice, 0)
        self.assertEqual(p.pips, 0)

    def test_positive_pip_carry(self):
        # 4D + 4 pips should normalize to 5D+1
        p = DicePool(4, 4)
        self.assertEqual(p.dice, 5)
        self.assertEqual(p.pips, 1)

    def test_positive_pip_carry_exact(self):
        # 4D + 6 pips should be exactly 6D+0 (two full dice carried)
        p = DicePool(4, 6)
        self.assertEqual(p.dice, 6)
        self.assertEqual(p.pips, 0)

    def test_pips_three_carries_one_die(self):
        # 4D + 3 pips => 5D+0 (one full die carried)
        p = DicePool(4, 3)
        self.assertEqual(p.dice, 5)
        self.assertEqual(p.pips, 0)

    def test_negative_pip_borrow_5d_minus_1(self):
        # 5D-1 must NOT silently become 5D — it must borrow into 4D+2.
        # This is THE canonical regression from project memory.
        p = DicePool(5, -1)
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 2)

    def test_negative_pip_borrow_5d_minus_2(self):
        p = DicePool(5, -2)
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 1)

    def test_negative_pip_underflow_clamps_at_zero(self):
        # 1D-9 cannot legally exist — should clamp to 0D, 0 pips
        p = DicePool(1, -9)
        self.assertEqual(p.dice, 0)
        # After borrowing once, pips would be -6; the loop guards on
        # dice > 0 so it stops at 0D, but the residual negative pip
        # value is then clamped to 0 by max(0, self.pips).
        self.assertEqual(p.pips, 0)

    def test_total_pips_accounting(self):
        # 5D-1 normalized = 4D+2; total_pips should be 14
        # (pre-normalization 5*3-1 = 14, post-normalization 4*3+2 = 14)
        p = DicePool(5, -1)
        self.assertEqual(p.total_pips(), 14)


# ══════════════════════════════════════════════════════════════════════════════
# DicePool — parse / stringify / arithmetic
# ══════════════════════════════════════════════════════════════════════════════


class TestDicePoolParse(unittest.TestCase):
    def test_parse_simple(self):
        p = DicePool.parse("4D")
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 0)

    def test_parse_with_plus_pips(self):
        p = DicePool.parse("4D+2")
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 2)

    def test_parse_with_minus_pips_normalizes(self):
        p = DicePool.parse("5D-1")
        # parse calls __post_init__ which borrows
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 2)

    def test_parse_lowercase(self):
        p = DicePool.parse("3d+1")
        self.assertEqual(p.dice, 3)
        self.assertEqual(p.pips, 1)

    def test_parse_with_spaces(self):
        p = DicePool.parse("  4D + 2  ")
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 2)

    def test_parse_empty_string(self):
        p = DicePool.parse("")
        self.assertEqual(p.dice, 0)
        self.assertEqual(p.pips, 0)

    def test_parse_pips_only(self):
        # Bare '2' (no D) is treated as 2 pips, no dice. After normalization
        # this stays 0D + 2 pips since no dice to carry.
        p = DicePool.parse("2")
        self.assertEqual(p.dice, 0)
        self.assertEqual(p.pips, 2)


class TestDicePoolStringify(unittest.TestCase):
    def test_str_no_pips(self):
        self.assertEqual(str(DicePool(4, 0)), "4D")

    def test_str_positive_pips(self):
        self.assertEqual(str(DicePool(4, 2)), "4D+2")

    def test_str_zero_dice(self):
        self.assertEqual(str(DicePool(0, 0)), "0D")

    def test_repr_includes_class_name(self):
        self.assertEqual(repr(DicePool(4, 2)), "DicePool(4, 2)")


class TestDicePoolArithmetic(unittest.TestCase):
    def test_add_two_pools(self):
        p = DicePool(3, 1) + DicePool(2, 0)
        self.assertEqual(p.dice, 5)
        self.assertEqual(p.pips, 1)

    def test_add_two_pools_with_pip_carry(self):
        # 3D+2 + 2D+2 = 5D+4 -> normalize 6D+1
        p = DicePool(3, 2) + DicePool(2, 2)
        self.assertEqual(p.dice, 6)
        self.assertEqual(p.pips, 1)

    def test_add_int_treats_as_pips(self):
        p = DicePool(3, 0) + 2
        self.assertEqual(p.dice, 3)
        self.assertEqual(p.pips, 2)

    def test_sub_pool(self):
        # 5D - 1D = 4D
        p = DicePool(5, 0) - DicePool(1, 0)
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 0)

    def test_sub_int_treats_as_pips(self):
        # 5D - 1 (pip) -> normalized to 4D+2
        p = DicePool(5, 0) - 1
        self.assertEqual(p.dice, 4)
        self.assertEqual(p.pips, 2)

    def test_add_unsupported_returns_notimplemented(self):
        # Returning NotImplemented should make Python raise TypeError
        with self.assertRaises(TypeError):
            DicePool(3, 0) + "garbage"

    def test_is_zero(self):
        self.assertTrue(DicePool(0, 0).is_zero())
        self.assertFalse(DicePool(0, 1).is_zero())
        self.assertFalse(DicePool(1, 0).is_zero())


# ══════════════════════════════════════════════════════════════════════════════
# Difficulty enum
# ══════════════════════════════════════════════════════════════════════════════


class TestDifficulty(unittest.TestCase):
    def test_canonical_ladder_values(self):
        # WEG D6 R&E p82 ladder
        self.assertEqual(int(Difficulty.VERY_EASY), 5)
        self.assertEqual(int(Difficulty.EASY), 10)
        self.assertEqual(int(Difficulty.MODERATE), 15)
        self.assertEqual(int(Difficulty.DIFFICULT), 20)
        self.assertEqual(int(Difficulty.VERY_DIFFICULT), 25)
        self.assertEqual(int(Difficulty.HEROIC), 30)

    def test_from_name_basic(self):
        self.assertEqual(Difficulty.from_name("Easy"), Difficulty.EASY)

    def test_from_name_with_space(self):
        self.assertEqual(
            Difficulty.from_name("Very Easy"), Difficulty.VERY_EASY
        )

    def test_from_name_with_hyphen(self):
        self.assertEqual(
            Difficulty.from_name("very-difficult"), Difficulty.VERY_DIFFICULT
        )

    def test_describe_below_very_easy_is_trivial(self):
        self.assertEqual(Difficulty.describe(3), "Trivial")

    def test_describe_picks_highest_band_at_or_below(self):
        self.assertEqual(Difficulty.describe(5), "Very Easy")
        self.assertEqual(Difficulty.describe(7), "Very Easy")
        self.assertEqual(Difficulty.describe(10), "Easy")
        self.assertEqual(Difficulty.describe(15), "Moderate")
        self.assertEqual(Difficulty.describe(30), "Heroic")
        self.assertEqual(Difficulty.describe(99), "Heroic")


# ══════════════════════════════════════════════════════════════════════════════
# Scale enum
# ══════════════════════════════════════════════════════════════════════════════


class TestScale(unittest.TestCase):
    def test_canonical_values(self):
        self.assertEqual(int(Scale.CHARACTER), 0)
        self.assertEqual(int(Scale.STARFIGHTER), 6)
        self.assertEqual(int(Scale.CAPITAL), 12)
        self.assertEqual(int(Scale.DEATH_STAR), 18)

    def test_from_name(self):
        self.assertEqual(Scale.from_name("starfighter"), Scale.STARFIGHTER)
        self.assertEqual(Scale.from_name("DEATH STAR"), Scale.DEATH_STAR)

    def test_difference_is_defender_minus_attacker(self):
        # Speeder attacking starfighter: defender bigger by +4
        diff = Scale.difference(Scale.SPEEDER, Scale.STARFIGHTER)
        self.assertEqual(diff, 4)
        # Starfighter attacking speeder: defender smaller by -4
        diff = Scale.difference(Scale.STARFIGHTER, Scale.SPEEDER)
        self.assertEqual(diff, -4)

    def test_difference_same_scale_is_zero(self):
        self.assertEqual(
            Scale.difference(Scale.CHARACTER, Scale.CHARACTER), 0
        )


# ══════════════════════════════════════════════════════════════════════════════
# roll_die, roll_wild_die — stochastic with seeding
# ══════════════════════════════════════════════════════════════════════════════


class TestRollDie(unittest.TestCase):
    def test_returns_int_in_range(self):
        for _ in range(200):
            r = roll_die()
            self.assertIsInstance(r, int)
            self.assertGreaterEqual(r, 1)
            self.assertLessEqual(r, 6)


class TestRollWildDieDeterministic(unittest.TestCase):
    """Use random.seed + monkey-patch on randint to force exact rolls."""

    def _force_rolls(self, sequence):
        """Return a closure that pops from `sequence` on each call."""
        seq = list(sequence)
        seq_iter = iter(seq)

        def fake_randint(_lo, _hi):
            return next(seq_iter)

        return fake_randint

    def test_complication_on_one(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=self._force_rolls([1])):
            r = roll_wild_die()
        self.assertTrue(r.complication)
        self.assertFalse(r.exploded)
        self.assertEqual(r.total, 0)
        self.assertEqual(r.first_roll, 1)
        self.assertEqual(r.rolls, [1])

    def test_normal_roll_no_explosion(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=self._force_rolls([4])):
            r = roll_wild_die()
        self.assertFalse(r.complication)
        self.assertFalse(r.exploded)
        self.assertEqual(r.total, 4)
        self.assertEqual(r.rolls, [4])

    def test_explosion_chain(self):
        from unittest.mock import patch
        # Roll a 6, explode to 6, explode to 3 — total 6+6+3 = 15
        with patch("engine.dice.random.randint", side_effect=self._force_rolls([6, 6, 3])):
            r = roll_wild_die()
        self.assertTrue(r.exploded)
        self.assertFalse(r.complication)
        self.assertEqual(r.total, 15)
        self.assertEqual(r.rolls, [6, 6, 3])

    def test_first_roll_property_empty_safe(self):
        # If rolls is empty (degenerate constructed case), first_roll=0
        wd = WildDieResult()
        self.assertEqual(wd.first_roll, 0)


# ══════════════════════════════════════════════════════════════════════════════
# roll_d6_pool — pool-level rolling
# ══════════════════════════════════════════════════════════════════════════════


class TestRollD6Pool(unittest.TestCase):
    def test_zero_dice_pool_returns_pips_only(self):
        # 0D+2 should just yield 2 with no rolls
        result = roll_d6_pool(DicePool(0, 2))
        self.assertEqual(result.total, 2)
        self.assertEqual(result.normal_dice, [])
        self.assertIsNone(result.wild_die)
        self.assertEqual(result.pips, 2)

    def test_zero_dice_zero_pips_total_is_zero(self):
        result = roll_d6_pool(DicePool(0, 0))
        self.assertEqual(result.total, 0)

    def test_zero_dice_negative_implicit_pips(self):
        # 0D pool with 0 pips total clamps to 0
        result = roll_d6_pool(DicePool(0, 0))
        self.assertGreaterEqual(result.total, 0)

    def test_one_die_pool_rolls_only_wild_die(self):
        # 1D pool: dice-1=0 normals, just wild die
        random.seed(42)
        result = roll_d6_pool(DicePool(1, 0))
        self.assertEqual(result.normal_dice, [])
        self.assertIsNotNone(result.wild_die)
        # Total is at least 1 (engine clamps to 1 minimum)
        self.assertGreaterEqual(result.total, 1)

    def test_complication_removes_highest_normal_die(self):
        from unittest.mock import patch
        # Force: 3 normal dice = 5, 4, 2 (will be sorted desc to 5,4,2)
        # then wild die = 1 (complication)
        # After complication: normal_total = 5+4+2 = 11, then -5 (highest) = 6
        # Wild die contributes 0; pips 0; total = max(1, 6+0+0) = 6
        forced = [5, 4, 2, 1]
        forced_iter = iter(forced)

        def fake_randint(_lo, _hi):
            return next(forced_iter)

        with patch("engine.dice.random.randint", side_effect=fake_randint):
            result = roll_d6_pool(DicePool(4, 0))

        self.assertTrue(result.complication)
        self.assertFalse(result.exploded)
        self.assertEqual(result.removed_die, 5)
        self.assertEqual(result.normal_dice, [5, 4, 2])
        self.assertEqual(result.total, 6)

    def test_explosion_no_complication(self):
        from unittest.mock import patch
        # 4D: normals 3, 4, 5 (sorted 5,4,3) + wild=6,2 (explodes once total=8)
        forced = [3, 4, 5, 6, 2]
        forced_iter = iter(forced)

        def fake_randint(_lo, _hi):
            return next(forced_iter)

        with patch("engine.dice.random.randint", side_effect=fake_randint):
            result = roll_d6_pool(DicePool(4, 0))

        self.assertTrue(result.exploded)
        self.assertFalse(result.complication)
        # normal sum = 3+4+5 = 12; wild = 6+2 = 8; total = 20
        self.assertEqual(result.total, 20)

    def test_pip_floor_clamps_to_one(self):
        from unittest.mock import patch
        # 1D pool: 0 normals + wild=1 (complication, contributes 0)
        # No normal die to remove. Total would be max(1, 0+0+0) = 1.
        with patch("engine.dice.random.randint", side_effect=[1]):
            result = roll_d6_pool(DicePool(1, 0))
        self.assertEqual(result.total, 1)
        self.assertTrue(result.complication)
        # No normal dice exist to remove
        self.assertIsNone(result.removed_die)

    def test_pool_str_convenience(self):
        # roll_pool_str just delegates — pick a small deterministic pool
        random.seed(123)
        result = roll_pool_str("2D+1")
        self.assertEqual(result.pool.dice, 2)
        self.assertEqual(result.pool.pips, 1)


# ══════════════════════════════════════════════════════════════════════════════
# Check / opposed roll structures
# ══════════════════════════════════════════════════════════════════════════════


class TestDifficultyCheck(unittest.TestCase):
    def test_success_when_total_meets_target(self):
        from unittest.mock import patch
        # 1D pool, force wild=5 → total max(1, 0+5+0) = 5; target=5 → success
        with patch("engine.dice.random.randint", side_effect=[5]):
            result = difficulty_check(DicePool(1, 0), 5)
        self.assertTrue(result.success)
        self.assertEqual(result.margin, 0)

    def test_failure_when_under_target(self):
        from unittest.mock import patch
        # 1D pool, force wild=2 → total 2; target=10 → fail
        with patch("engine.dice.random.randint", side_effect=[2]):
            result = difficulty_check(DicePool(1, 0), 10)
        self.assertFalse(result.success)
        self.assertEqual(result.margin, -8)

    def test_check_result_display_formats(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[3]):
            result = difficulty_check(DicePool(1, 0), 5)
        # Just sanity: display should contain SUCCESS or FAILURE token
        text = result.display()
        self.assertTrue("SUCCESS" in text or "FAILURE" in text)


class TestOpposedRoll(unittest.TestCase):
    def test_attacker_wins_when_higher(self):
        from unittest.mock import patch
        # Attacker 1D rolls 5; defender 1D rolls 2
        with patch("engine.dice.random.randint", side_effect=[5, 2]):
            result = opposed_roll(DicePool(1, 0), DicePool(1, 0))
        self.assertTrue(result.attacker_wins)
        self.assertEqual(result.margin, 3)

    def test_tie_goes_to_defender(self):
        from unittest.mock import patch
        # Both roll wild=4 only (1D pools). Margin = 0. Defender wins on tie.
        with patch("engine.dice.random.randint", side_effect=[4, 4]):
            result = opposed_roll(DicePool(1, 0), DicePool(1, 0))
        self.assertFalse(result.attacker_wins)
        self.assertEqual(result.margin, 0)

    def test_defender_wins_when_higher(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[2, 5]):
            result = opposed_roll(DicePool(1, 0), DicePool(1, 0))
        self.assertFalse(result.attacker_wins)
        self.assertEqual(result.margin, -3)


# ══════════════════════════════════════════════════════════════════════════════
# Modifier helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestMultiActionPenalty(unittest.TestCase):
    def test_one_action_no_penalty(self):
        result = apply_multi_action_penalty(DicePool(4, 2), 1)
        self.assertEqual(result.dice, 4)
        self.assertEqual(result.pips, 2)

    def test_two_actions_minus_one_die(self):
        result = apply_multi_action_penalty(DicePool(4, 2), 2)
        self.assertEqual(result.dice, 3)
        # Pips preserved when dice > 0
        self.assertEqual(result.pips, 2)

    def test_three_actions_minus_two_dice(self):
        result = apply_multi_action_penalty(DicePool(4, 2), 3)
        self.assertEqual(result.dice, 2)

    def test_penalty_floors_at_zero_dice(self):
        result = apply_multi_action_penalty(DicePool(2, 2), 5)
        # 2 - 4 (penalty) = floored at 0
        self.assertEqual(result.dice, 0)
        # When dice == 0, pips MUST be zero (engine convention)
        self.assertEqual(result.pips, 0)

    def test_zero_actions_treated_as_no_penalty(self):
        # max(0, 0-1) = 0, so no penalty applied
        result = apply_multi_action_penalty(DicePool(3, 1), 0)
        self.assertEqual(result.dice, 3)
        self.assertEqual(result.pips, 1)


class TestWoundPenalty(unittest.TestCase):
    def test_no_wounds_no_change(self):
        result = apply_wound_penalty(DicePool(5, 1), 0)
        self.assertEqual(result.dice, 5)
        self.assertEqual(result.pips, 1)

    def test_one_wound_minus_one_die(self):
        result = apply_wound_penalty(DicePool(5, 1), 1)
        self.assertEqual(result.dice, 4)
        self.assertEqual(result.pips, 1)

    def test_more_wounds_than_dice_floors_at_zero(self):
        result = apply_wound_penalty(DicePool(2, 1), 5)
        self.assertEqual(result.dice, 0)
        self.assertEqual(result.pips, 0)


class TestScaleModifier(unittest.TestCase):
    def test_same_scale_no_dice_added(self):
        result = apply_scale_modifier(
            DicePool(4, 0), Scale.CHARACTER, Scale.CHARACTER
        )
        self.assertEqual(result.dice, 4)
        self.assertEqual(result.pips, 0)

    def test_cross_scale_adds_absolute_difference(self):
        # Speeder vs starfighter: scale diff = 4. Pool gets +4D.
        result = apply_scale_modifier(
            DicePool(4, 0), Scale.SPEEDER, Scale.STARFIGHTER
        )
        self.assertEqual(result.dice, 8)
        self.assertEqual(result.pips, 0)

    def test_cross_scale_uses_absolute_value(self):
        # Same difference whether attacker is bigger or smaller
        result_a = apply_scale_modifier(
            DicePool(2, 0), Scale.STARFIGHTER, Scale.SPEEDER
        )
        result_b = apply_scale_modifier(
            DicePool(2, 0), Scale.SPEEDER, Scale.STARFIGHTER
        )
        self.assertEqual(result_a.dice, result_b.dice)


# ══════════════════════════════════════════════════════════════════════════════
# CP dice — explodes on 6, NO mishap on 1 (R&E p55)
# ══════════════════════════════════════════════════════════════════════════════


class TestCPDice(unittest.TestCase):
    def test_cp_die_no_mishap_on_one(self):
        from unittest.mock import patch
        # CP die on 1 should return exactly 1 (NOT zero — that's the Wild Die rule)
        with patch("engine.dice.random.randint", side_effect=[1]):
            self.assertEqual(roll_cp_die(), 1)

    def test_cp_die_explodes_on_six(self):
        from unittest.mock import patch
        # 6, then 4 → total 10
        with patch("engine.dice.random.randint", side_effect=[6, 4]):
            self.assertEqual(roll_cp_die(), 10)

    def test_cp_die_double_explosion(self):
        from unittest.mock import patch
        # 6, 6, 3 → total 15
        with patch("engine.dice.random.randint", side_effect=[6, 6, 3]):
            self.assertEqual(roll_cp_die(), 15)

    def test_cp_die_normal_roll(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[4]):
            self.assertEqual(roll_cp_die(), 4)

    def test_cp_dice_returns_total_and_per_die(self):
        from unittest.mock import patch
        # roll 3 CP dice: 4, 6+2=8, 1 → total=13, rolls=[4, 8, 1]
        with patch("engine.dice.random.randint", side_effect=[4, 6, 2, 1]):
            total, rolls = roll_cp_dice(3)
        self.assertEqual(total, 13)
        self.assertEqual(rolls, [4, 8, 1])

    def test_cp_dice_zero_count(self):
        total, rolls = roll_cp_dice(0)
        self.assertEqual(total, 0)
        self.assertEqual(rolls, [])


# ══════════════════════════════════════════════════════════════════════════════
# Force Point — doubles dice AND pips (R&E p52)
# ══════════════════════════════════════════════════════════════════════════════


class TestForcePoint(unittest.TestCase):
    def test_doubles_dice_and_pips(self):
        # 3D+2 -> 6D+4 -> normalize to 7D+1
        result = apply_force_point(DicePool(3, 2))
        # dice doubled = 6, pips doubled = 4 → 7D+1 after carry
        self.assertEqual(result.dice, 7)
        self.assertEqual(result.pips, 1)

    def test_doubles_zero_pips(self):
        result = apply_force_point(DicePool(4, 0))
        self.assertEqual(result.dice, 8)
        self.assertEqual(result.pips, 0)

    def test_doubles_zero_dice(self):
        # 0D+1 -> 0D+2 (no dice to double)
        result = apply_force_point(DicePool(0, 1))
        self.assertEqual(result.dice, 0)
        self.assertEqual(result.pips, 2)


# ══════════════════════════════════════════════════════════════════════════════
# Result dataclasses — display invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestResultDisplay(unittest.TestCase):
    def test_roll_result_display_includes_pool(self):
        # Use a forced 1D roll to make display deterministic
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[3]):
            result = roll_d6_pool(DicePool(1, 0))
        self.assertIn("[1D]", result.display())
        self.assertIn(" = ", result.display())

    def test_check_result_display_shows_target(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[3]):
            result = difficulty_check(DicePool(1, 0), 10)
        self.assertIn("vs 10", result.display())

    def test_opposed_result_display_includes_winner(self):
        from unittest.mock import patch
        with patch("engine.dice.random.randint", side_effect=[5, 2]):
            result = opposed_roll(DicePool(1, 0), DicePool(1, 0))
        text = result.display()
        self.assertIn("ATTACKER", text)


if __name__ == "__main__":
    unittest.main()
