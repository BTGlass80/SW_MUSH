# -*- coding: utf-8 -*-
"""
tests/test_force_powers_unit.py — Code review C6 fix tests

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`force_powers.py` was the #1 priority target for testing — complex dice
mechanics and dark-side tracking with no coverage. This file adds
unit-test coverage of the pure / deterministic surface:

  - POWERS dict completeness + invariants
  - get_power lookup with key normalization
  - _has_force_skill predicate against constructed Character fixtures
  - list_powers_for_char filtering by skill availability
  - _dsp_warning text bands
  - format_power_list display rendering
  - Difficulty constants ordering (R&E p113)
  - DSP_FALL_THRESHOLD value

Stochastic / Character-mutating surface (`resolve_force_power`,
`_resolve_*` per-power functions, `_resolve_fall_check`) is left to
integration tests with a real RNG seed and skill registry. That's a
follow-up drop and requires the live SkillRegistry which is built at
boot from the species YAML — out of scope for unit tests.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.dice import DicePool  # noqa: E402
from engine.force_powers import (  # noqa: E402
    POWERS,
    ForcePower,
    ForcePowerResult,
    get_power,
    list_powers_for_char,
    _has_force_skill,
    _dsp_warning,
    format_power_list,
    VERY_EASY, EASY, MODERATE, DIFFICULT, VERY_DIFF, HEROIC,
    DSP_FALL_THRESHOLD,
)


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════


class _CharFixture:
    """Minimal Character-shaped stand-in. We only need get_attribute() to
    return a DicePool for the force skills the test cares about.

    Per engine.force_powers._has_force_skill, the predicate is
    `pool.dice > 0 or pool.pips > 0`. So a non-zero DicePool reports
    "has skill"; a zero-zero pool reports "no skill."
    """

    def __init__(self, **skills):
        # skills like control=DicePool(2), sense=DicePool(0)
        self._skills = skills
        self.dark_side_points = 0
        self.name = "Test Char"

    def get_attribute(self, name):
        return self._skills.get(name, DicePool(0, 0))


# ══════════════════════════════════════════════════════════════════════════════
# Difficulty constants
# ══════════════════════════════════════════════════════════════════════════════


class TestDifficultyConstants(unittest.TestCase):
    def test_difficulty_constants_ordered_ascending(self):
        # Per R&E p113, difficulty bands must be monotonically increasing.
        self.assertLess(VERY_EASY, EASY)
        self.assertLess(EASY, MODERATE)
        self.assertLess(MODERATE, DIFFICULT)
        self.assertLess(DIFFICULT, VERY_DIFF)
        self.assertLess(VERY_DIFF, HEROIC)

    def test_difficulty_constant_values_match_weg_re_table(self):
        # These specific values are the WEG R&E canonical difficulty bands.
        # If any of these change, the player-facing difficulty descriptions
        # in commands and help text need to update too.
        self.assertEqual(VERY_EASY, 5)
        self.assertEqual(EASY, 10)
        self.assertEqual(MODERATE, 15)
        self.assertEqual(DIFFICULT, 20)
        self.assertEqual(VERY_DIFF, 25)
        self.assertEqual(HEROIC, 30)

    def test_dsp_fall_threshold_is_six_per_re_p118(self):
        self.assertEqual(DSP_FALL_THRESHOLD, 6)


# ══════════════════════════════════════════════════════════════════════════════
# POWERS dict invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestPowersDict(unittest.TestCase):
    def test_eight_powers_defined(self):
        # Per the module docstring: 3 Control + 2 Sense + 1 Alter +
        # 1 combination + 1 dark-side Alter = 8 powers.
        self.assertEqual(len(POWERS), 8)

    def test_each_power_key_matches_its_key_field(self):
        for k, p in POWERS.items():
            self.assertEqual(k, p.key, f"dict key {k!r} != ForcePower.key {p.key!r}")

    def test_each_power_has_at_least_one_skill(self):
        for k, p in POWERS.items():
            self.assertGreater(len(p.skills), 0,
                               f"{k} has empty skills list")

    def test_each_power_uses_only_canonical_force_skills(self):
        canonical = {"control", "sense", "alter"}
        for k, p in POWERS.items():
            for s in p.skills:
                self.assertIn(s, canonical,
                              f"{k} references non-canonical skill {s!r}")

    def test_each_power_difficulty_is_known_band(self):
        bands = {VERY_EASY, EASY, MODERATE, DIFFICULT, VERY_DIFF, HEROIC}
        for k, p in POWERS.items():
            self.assertIn(p.base_diff, bands,
                          f"{k}.base_diff={p.base_diff} not a known WEG band")

    def test_each_power_has_target_field(self):
        valid_targets = {"self", "room", "target"}
        for k, p in POWERS.items():
            self.assertIn(p.target, valid_targets,
                          f"{k}.target={p.target!r} not in {valid_targets}")

    def test_each_power_has_nonempty_description(self):
        for k, p in POWERS.items():
            self.assertIsInstance(p.description, str)
            self.assertGreater(len(p.description), 20,
                               f"{k} description too short to be useful")

    def test_dark_side_powers_explicitly_marked(self):
        # Per the module docstring: only injure_kill and affect_mind
        # award DSP. If a future power gets added with dark_side=True
        # that should be deliberate; this test catches accidental
        # additions.
        dark = {k for k, p in POWERS.items() if p.dark_side}
        self.assertEqual(dark, {"injure_kill", "affect_mind"})

    def test_dark_side_powers_warn_in_description(self):
        # All dark_side=True powers should mention DSP in their
        # description so a player reading +help <power> understands the
        # cost before activating.
        for k, p in POWERS.items():
            if p.dark_side:
                self.assertTrue(
                    "DARK SIDE" in p.description or "Dark Side" in p.description,
                    f"{k} is dark_side=True but description doesn't warn"
                )


# ══════════════════════════════════════════════════════════════════════════════
# get_power lookup
# ══════════════════════════════════════════════════════════════════════════════


class TestGetPower(unittest.TestCase):
    def test_exact_key_lookup(self):
        p = get_power("life_sense")
        self.assertIsNotNone(p)
        self.assertEqual(p.key, "life_sense")

    def test_uppercase_normalized(self):
        self.assertIsNotNone(get_power("LIFE_SENSE"))
        self.assertIsNotNone(get_power("Life_Sense"))

    def test_space_normalized_to_underscore(self):
        self.assertIsNotNone(get_power("life sense"))
        self.assertEqual(get_power("life sense").key, "life_sense")

    def test_dash_normalized_to_underscore(self):
        self.assertIsNotNone(get_power("life-sense"))
        self.assertEqual(get_power("life-sense").key, "life_sense")

    def test_mixed_separators_normalized(self):
        self.assertIsNotNone(get_power("LIFE-SENSE"))
        self.assertIsNotNone(get_power("Life Sense"))

    def test_unknown_key_returns_none(self):
        self.assertIsNone(get_power("nonexistent_power"))
        self.assertIsNone(get_power(""))

    def test_each_canonical_key_resolvable(self):
        for k in POWERS.keys():
            self.assertIsNotNone(get_power(k),
                                 f"canonical key {k!r} should resolve")


# ══════════════════════════════════════════════════════════════════════════════
# _has_force_skill predicate
# ══════════════════════════════════════════════════════════════════════════════


class TestHasForceSkill(unittest.TestCase):
    def test_dice_only_pool_counts_as_having_skill(self):
        char = _CharFixture(control=DicePool(2, 0))
        self.assertTrue(_has_force_skill(char, "control"))

    def test_pips_only_pool_counts_as_having_skill(self):
        char = _CharFixture(control=DicePool(0, 2))
        self.assertTrue(_has_force_skill(char, "control"))

    def test_zero_pool_means_no_skill(self):
        char = _CharFixture(control=DicePool(0, 0))
        self.assertFalse(_has_force_skill(char, "control"))

    def test_missing_attribute_means_no_skill(self):
        # Char with no control attribute at all (most non-Force PCs)
        char = _CharFixture()
        self.assertFalse(_has_force_skill(char, "control"))


# ══════════════════════════════════════════════════════════════════════════════
# list_powers_for_char
# ══════════════════════════════════════════════════════════════════════════════


class TestListPowersForChar(unittest.TestCase):
    def test_no_force_skills_returns_empty(self):
        char = _CharFixture()
        self.assertEqual(list_powers_for_char(char), [])

    def test_control_only_returns_control_powers(self):
        char = _CharFixture(control=DicePool(1, 0))
        powers = list_powers_for_char(char)
        keys = {p.key for p in powers}
        # Should include all control-only powers
        self.assertIn("accelerate_healing", keys)
        self.assertIn("control_pain", keys)
        self.assertIn("remain_conscious", keys)
        # Should NOT include sense or alter powers
        self.assertNotIn("life_sense", keys)
        self.assertNotIn("telekinesis", keys)
        self.assertNotIn("injure_kill", keys)
        # Should NOT include affect_mind (needs all three)
        self.assertNotIn("affect_mind", keys)

    def test_all_three_skills_returns_all_powers(self):
        char = _CharFixture(
            control=DicePool(1, 0),
            sense=DicePool(1, 0),
            alter=DicePool(1, 0),
        )
        powers = list_powers_for_char(char)
        keys = {p.key for p in powers}
        self.assertEqual(keys, set(POWERS.keys()))

    def test_combination_power_requires_all_three(self):
        # Two of three is not enough for affect_mind
        char = _CharFixture(
            control=DicePool(1, 0),
            sense=DicePool(1, 0),
        )
        keys = {p.key for p in list_powers_for_char(char)}
        self.assertNotIn("affect_mind", keys)


# ══════════════════════════════════════════════════════════════════════════════
# _dsp_warning bands
# ══════════════════════════════════════════════════════════════════════════════


class TestDspWarning(unittest.TestCase):
    def test_low_dsp_uses_first_band(self):
        for n in (1, 2, 3):
            warn = _dsp_warning(n)
            self.assertIn("[DARK SIDE]", warn)
            self.assertIn(str(n), warn)
            self.assertIn("gain 1 Dark Side Point", warn)

    def test_medium_dsp_uses_grows_within_band(self):
        for n in (4, 5):
            warn = _dsp_warning(n)
            self.assertIn(str(n), warn)
            self.assertIn("grows within", warn)

    def test_high_dsp_uses_consuming_band(self):
        for n in (DSP_FALL_THRESHOLD, DSP_FALL_THRESHOLD + 5, 20):
            warn = _dsp_warning(n)
            self.assertIn(str(n), warn)
            self.assertIn("consuming", warn)

    def test_threshold_is_inclusive(self):
        # Exactly at the threshold should use the high-DSP message
        # (the function uses >=).
        warn = _dsp_warning(DSP_FALL_THRESHOLD)
        self.assertIn("consuming", warn)


# ══════════════════════════════════════════════════════════════════════════════
# format_power_list
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatPowerList(unittest.TestCase):
    def test_empty_list_renders_empty(self):
        self.assertEqual(format_power_list([]), [])

    def test_each_power_produces_two_lines(self):
        powers = list(POWERS.values())
        lines = format_power_list(powers)
        self.assertEqual(len(lines), 2 * len(powers),
                         "each power should produce a header + description line")

    def test_dark_side_powers_show_tag(self):
        dark_powers = [p for p in POWERS.values() if p.dark_side]
        lines = format_power_list(dark_powers)
        text = "\n".join(lines)
        # Each dark-side power's header line should have the [DARK SIDE] tag
        for p in dark_powers:
            self.assertIn("[DARK SIDE]", text,
                          f"{p.key} not tagged in formatted output")

    def test_skill_combinations_rendered(self):
        # accept_mind requires Control + Sense + Alter
        affect_mind = POWERS["affect_mind"]
        lines = format_power_list([affect_mind])
        text = " ".join(lines)
        # Title-cased skill names joined by " + "
        self.assertIn("Control + Sense + Alter", text)

    def test_difficulty_shown_in_header(self):
        for k, p in POWERS.items():
            lines = format_power_list([p])
            # The header line is lines[0]
            self.assertIn(f"Diff {p.base_diff}", lines[0],
                          f"{k} header doesn't show difficulty")


# ══════════════════════════════════════════════════════════════════════════════
# ForcePowerResult dataclass defaults
# ══════════════════════════════════════════════════════════════════════════════


class TestForcePowerResultDefaults(unittest.TestCase):
    def test_minimum_construction(self):
        # Only required fields
        r = ForcePowerResult(
            power=POWERS["life_sense"],
            success=True,
            roll=15,
            difficulty=10,
            margin=5,
            narrative="Sensed three life forms.",
        )
        # Defaults
        self.assertEqual(r.dsp_gained, 0)
        self.assertFalse(r.fall_check)
        self.assertFalse(r.fall_failed)
        self.assertEqual(r.heal_amount, 0)
        self.assertFalse(r.pain_suppressed)
        self.assertEqual(r.targets_felt, [])
        self.assertEqual(r.damage_dealt, 0)

    def test_targets_felt_defaults_independent_per_instance(self):
        # Catch the classic mutable-default bug — if targets_felt were
        # shared across instances, mutating one would affect another.
        r1 = ForcePowerResult(
            power=POWERS["life_sense"], success=True,
            roll=10, difficulty=10, margin=0, narrative="",
        )
        r2 = ForcePowerResult(
            power=POWERS["life_sense"], success=True,
            roll=10, difficulty=10, margin=0, narrative="",
        )
        r1.targets_felt.append("ghost")
        self.assertEqual(r2.targets_felt, [])


if __name__ == "__main__":
    unittest.main()
