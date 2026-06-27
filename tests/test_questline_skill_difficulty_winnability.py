# -*- coding: utf-8 -*-
"""
tests/test_questline_skill_difficulty_winnability.py — balance-integrity guard
for the T3.24 freelance-questline SKILL CHECKS (OpusLoop quality lane, 2026-06-27).

WHAT GAP THIS CLOSES
--------------------
This is the third leg of the questline winnability/integrity trilogy. Its
siblings pin the other two axes a freelance arc can silently break:
  * test_questline_reward_tier_consistency  — economy (every arc pays the same).
  * test_questline_foil_winnability_band     — COMBAT step (the foil is beatable).
This file pins the SKILL-CHECK step.

Every freelance accessible questline (`kind: questline`, chain_id NOT prefixed
`master_`, gated only on `chargen_complete`) advances through one or more
`skill_check_passed` steps. Each carries an authored `skill:` and an integer
`difficulty:`, rolled at `chain attempt` time via
engine.skill_checks.perform_skill_check(char, skill, difficulty). Two things
about that difficulty are load-bearing for a fresh player and NOTHING pins them:

  1. MAGNITUDE. The arcs are open to a brand-new character with no rep gate, so
     their difficulties were authored inside a tight Easy→Moderate band (shipped
     range 9..14, all <= WEG Moderate=15). A fat-fingered Difficult/Heroic value
     (e.g. `difficulty: 25`) on a `chargen_complete`-only arc is a practical
     SOFT-LOCK: retries are cooldown-throttled and a starting character cannot
     roll 25 on a 2D–3D attribute pool in any reasonable number of attempts.
     This is the exact open-world soft-lock class the tutorial combat-sim drive
     spent days fixing — but on the skill axis, and invisible to the unit suite
     because the per-arc slice harness force-passes skill checks (no dice rolled).
  2. RETRYABILITY. Every freelance skill check ships `on_fail: retry_allowed` —
     the guarantee that one bad roll never strands the player. An arc authored
     with a terminal no-retry on_fail (e.g. `abort_step_no_retry`) on an
     open-world step would soft-lock a player who fails once with no other path.

(Skill NAME validity — that `skill:` resolves to a real registered skill — is
already guarded by test_chain_corpus_reachability_invariant CLASS 4 via
canonical_skill_key against data/skills.yaml. This file does NOT re-cover that;
it covers difficulty magnitude + retryability, which that invariant never reads.)

THE WINNABILITY CONTRACT
------------------------
Difficulty bands are taken from the game's OWN resolver ladder
(engine.dice.Difficulty: VERY_EASY=5, EASY=10, MODERATE=15, DIFFICULT=20, …),
so this guard tracks the engine if those bands are ever re-tuned — no phantom
constant. WEG40120 (the mechanics authority) is gitignored/local-only and absent
in this worktree, so the band ladder is sourced from the engine enum it backs,
not invented here.

  * FREELANCE ceiling  = Difficulty.MODERATE (15). An accessible arc must never
    exceed Moderate. Shipped max is 14 → +1 headroom; a Difficult+ value trips it.
  * FREELANCE floor    = above Difficulty.VERY_EASY (>= 6, i.e. Easy or harder).
    Shipped min is 9. Anti-vacuous — a `skill_check_passed` beat meant to serve a
    build should be a real check, not a Very-Easy rubber-stamp.
  * on_fail            = "retry_allowed" for every freelance skill check.
  * difficulty         = present and an int (else `chain attempt` shows the
    "misconfigured" staff message instead of rolling — itself a soft-lock).
  * CORPUS backstop    = Difficulty.DIFFICULT (20) for BOTH tiers — even an
    end-game t5 trainer trial should never be Heroic (t5 shipped max is 11).

ASYMMETRY VS THE REWARD GUARD (intentional, same as the foil guard)
-------------------------------------------------------------------
The reward guard is fully self-calibrating (a whole-tier rebalance passes). A
difficulty ceiling is a WINNABILITY CLIFF, so the magnitude ceilings here are
hard absolutes tied to the band enum: a deliberate galaxy-wide difficulty
rebalance SHOULD trip this and force a conscious one-line edit — that sign-off is
the point. The intra-arc ramp check IS self-calibrating (reads each arc's own
sequence), the softer companion that surfaces a likely ordering fat-finger.

Pure data/test guard: no engine, parser, data, or client change.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.dice import Difficulty  # noqa: E402  (path set above)

CHAINS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "tutorials" / "chains.yaml")

# --- the winnability contract, tied to the engine's own band ladder -------
FREELANCE_CEIL = int(Difficulty.MODERATE)        # 15 — accessible arc ceiling
FREELANCE_FLOOR = int(Difficulty.VERY_EASY) + 1  # 6  — >= Easy, anti-vacuous
CORPUS_BACKSTOP_CEIL = int(Difficulty.DIFFICULT)  # 20 — both tiers, never Heroic
WINNABLE_ON_FAIL = "retry_allowed"


# --- shared predicates (single-sourced so the negative checks exercise the
#     exact logic the corpus tests use) ----------------------------------
def _over_freelance_ceiling(d) -> bool:
    return isinstance(d, int) and d > FREELANCE_CEIL


def _under_freelance_floor(d) -> bool:
    return isinstance(d, int) and d < FREELANCE_FLOOR


def _bad_on_fail(of) -> bool:
    return of != WINNABLE_ON_FAIL


def _bad_difficulty_type(d) -> bool:
    # engine/chain_commands._handle_attempt requires isinstance(difficulty, int)
    # (bool is an int subclass but is never a valid difficulty here).
    return not isinstance(d, int) or isinstance(d, bool)


# --- corpus loading (mirrors test_questline_reward_tier_consistency) -------
def _questlines():
    data = yaml.safe_load(open(CHAINS_PATH, encoding="utf-8"))
    return [c for c in data["chains"] if c.get("kind") == "questline"]


def _is_t5(chain) -> bool:
    return str(chain.get("chain_id", "")).startswith("master_")


def _skill_checks(chain):
    """Every `skill_check_passed` completion in an arc, in step order.

    Returns a list of (step_no, skill, difficulty, on_fail) tuples.
    """
    out = []
    for step in chain.get("steps") or []:
        comp = step.get("completion") or {}
        if comp.get("type") == "skill_check_passed":
            out.append((step.get("step"), comp.get("skill"),
                        comp.get("difficulty"), comp.get("on_fail")))
    return out


class _Corpus(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.all = _questlines()
        cls.freelance = [c for c in cls.all if not _is_t5(c)]
        cls.t5 = [c for c in cls.all if _is_t5(c)]


class TestCorpusIsReal(_Corpus):

    def test_freelance_tier_non_vacuous(self):
        # Guard against the partition or the kind: questline marker silently
        # collapsing to nothing (which would make every assertion vacuous).
        self.assertGreaterEqual(
            len(self.freelance), 8,
            "expected a substantial freelance questline tier; the chain_id "
            "partition or the kind:questline marker may have drifted")

    def test_freelance_arcs_actually_have_skill_checks(self):
        # The whole point of these arcs is a build-serving skill spread; if a
        # glob/key change meant we found zero skill checks the guard is hollow.
        total = sum(len(_skill_checks(c)) for c in self.freelance)
        self.assertGreaterEqual(
            total, 12,
            f"found only {total} freelance skill checks; expected ~2 per arc — "
            "the completion-type key may have drifted from skill_check_passed")

    def test_every_questline_is_classified(self):
        self.assertEqual(len(self.all), len(self.freelance) + len(self.t5))


class TestFreelanceWinnability(_Corpus):
    """Absolute 'a fresh character can clear this' guards — the real protection."""

    def test_difficulty_present_and_int(self):
        for c in self.freelance:
            for step, skill, diff, _of in _skill_checks(c):
                self.assertFalse(
                    _bad_difficulty_type(diff),
                    f"{c['chain_id']} step {step} ({skill!r}) difficulty "
                    f"{diff!r} is not an int — `chain attempt` would show the "
                    "'misconfigured' staff message instead of rolling, "
                    "soft-locking the step")

    def test_difficulty_under_moderate_ceiling(self):
        for c in self.freelance:
            for step, skill, diff, _of in _skill_checks(c):
                self.assertFalse(
                    _over_freelance_ceiling(diff),
                    f"{c['chain_id']} step {step} ({skill!r}) difficulty {diff} "
                    f"exceeds the freelance ceiling {FREELANCE_CEIL} "
                    f"(Difficulty.MODERATE) — a fresh chargen_complete character "
                    "cannot clear a Difficult/Heroic roll even with retries "
                    "(soft-lock). If this is a deliberate galaxy-wide difficulty "
                    "rebalance, raise FREELANCE_CEIL consciously.")

    def test_difficulty_above_vacuous_floor(self):
        for c in self.freelance:
            for step, skill, diff, _of in _skill_checks(c):
                self.assertFalse(
                    _under_freelance_floor(diff),
                    f"{c['chain_id']} step {step} ({skill!r}) difficulty {diff} "
                    f"is below the anti-vacuous floor {FREELANCE_FLOOR} (Easy) — "
                    "a build-serving skill beat should be a real check, not a "
                    "Very-Easy rubber-stamp")

    def test_on_fail_is_retry_allowed(self):
        for c in self.freelance:
            for step, skill, _diff, of in _skill_checks(c):
                self.assertFalse(
                    _bad_on_fail(of),
                    f"{c['chain_id']} step {step} ({skill!r}) on_fail is {of!r}, "
                    f"not {WINNABLE_ON_FAIL!r} — an open-world freelance arc must "
                    "let a player who fails the roll retry, or a single bad roll "
                    "soft-locks the arc with no other path")


class TestIntraArcRamp(_Corpus):
    """Self-calibrating: difficulty should not DROP across an arc's steps."""

    def test_difficulty_non_decreasing_within_arc(self):
        for c in self.freelance:
            diffs = [d for _s, _sk, d, _of in _skill_checks(c)
                     if isinstance(d, int)]
            self.assertEqual(
                diffs, sorted(diffs),
                f"{c['chain_id']} skill-check difficulties {diffs} are not "
                "non-decreasing across the arc — a later step easier than an "
                "earlier one is the signature of a difficulty/order fat-finger "
                "(escalating challenge is the authored design intent)")


class TestCorpusBackstop(_Corpus):
    """Both tiers: even an end-game t5 trial should never be Heroic."""

    def test_every_questline_under_difficult_ceiling(self):
        for c in self.all:
            for step, skill, diff, _of in _skill_checks(c):
                if not isinstance(diff, int):
                    continue  # type guarded for the freelance tier elsewhere
                self.assertLessEqual(
                    diff, CORPUS_BACKSTOP_CEIL,
                    f"{c['chain_id']} step {step} ({skill!r}) difficulty {diff} "
                    f"exceeds the corpus backstop {CORPUS_BACKSTOP_CEIL} "
                    "(Difficulty.DIFFICULT) — no questline skill check, even a "
                    "t5 trainer trial, should sit at Very Difficult/Heroic")


class TestContractSanity(unittest.TestCase):
    """The contract must sit above the shipped band (no false pass) AND the
    predicates must actually reject a planted outlier (no false sense of cover).
    """

    def setUp(self):
        self.free = [c for c in _questlines() if not _is_t5(c)]
        self.t5 = [c for c in _questlines() if _is_t5(c)]

    def _free_diffs(self):
        return [d for c in self.free for _s, _sk, d, _of in _skill_checks(c)
                if isinstance(d, int)]

    def test_ceiling_clears_shipped_freelance_max_with_headroom(self):
        mx = max(self._free_diffs())
        self.assertLess(
            mx, FREELANCE_CEIL,
            f"shipped freelance max difficulty {mx} is not below the ceiling "
            f"{FREELANCE_CEIL} — the guard would have no headroom (re-tune one)")

    def test_floor_below_shipped_freelance_min(self):
        mn = min(self._free_diffs())
        self.assertGreaterEqual(
            mn, FREELANCE_FLOOR,
            f"shipped freelance min difficulty {mn} is below the floor "
            f"{FREELANCE_FLOOR} — shipped data would fail the anti-vacuous guard")

    def test_tiers_and_backstop_are_ordered(self):
        # Moderate ceiling < Difficult backstop, so the freelance tier is
        # genuinely stricter than the corpus-wide floor-of-sanity.
        self.assertLess(FREELANCE_CEIL, CORPUS_BACKSTOP_CEIL)
        t5_diffs = [d for c in self.t5 for _s, _sk, d, _of in _skill_checks(c)
                    if isinstance(d, int)]
        self.assertLessEqual(max(t5_diffs), CORPUS_BACKSTOP_CEIL)

    # --- negative checks: a planted outlier must trip each predicate --------
    def test_planted_heroic_difficulty_is_caught(self):
        self.assertTrue(_over_freelance_ceiling(25))      # Very Difficult
        self.assertTrue(_over_freelance_ceiling(FREELANCE_CEIL + 1))
        self.assertFalse(_over_freelance_ceiling(14))     # shipped max passes

    def test_planted_very_easy_difficulty_is_caught(self):
        self.assertTrue(_under_freelance_floor(3))        # Very Easy
        self.assertFalse(_under_freelance_floor(9))       # shipped min passes

    def test_planted_no_retry_on_fail_is_caught(self):
        self.assertTrue(_bad_on_fail("abort_step_no_retry"))
        self.assertTrue(_bad_on_fail(None))
        self.assertFalse(_bad_on_fail("retry_allowed"))   # shipped value passes

    def test_planted_non_int_difficulty_is_caught(self):
        self.assertTrue(_bad_difficulty_type("9"))        # string
        self.assertTrue(_bad_difficulty_type(None))
        self.assertTrue(_bad_difficulty_type(True))       # bool is not a diff
        self.assertFalse(_bad_difficulty_type(11))        # shipped form passes

    def test_planted_descending_ramp_is_caught(self):
        # Mirrors TestIntraArcRamp's logic against a synthetic arc.
        diffs = [13, 11]
        self.assertNotEqual(diffs, sorted(diffs))


if __name__ == "__main__":
    unittest.main()
