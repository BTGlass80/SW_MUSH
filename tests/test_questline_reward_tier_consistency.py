# -*- coding: utf-8 -*-
"""
tests/test_questline_reward_tier_consistency.py — economy-integrity guard
for the T3.24 questline corpus (OpusLoop quality lane, 2026-06-27).

WHAT GAP THIS CLOSES
--------------------
Each per-questline slice test (test_generalized_questline_*.py) asserts only
that its OWN arc's reward stays in a loose band — total credits <= 1000, total
faction_rep below HONORED (50) and under the tuned CEILING (22) — and the
corpus-wide test_t5_questline_content.TestChainRepEconomyCeiling enforces the
same rep ceiling across every chain. But NOTHING pins reward CONSISTENCY
*across* the questlines of a tier. A new accessible arc could ship 800cr /
20rep — inside every existing band — yet be wildly out of line with the peers
that all pay an identical 450cr / 17 Independent rep, and every existing test
would stay green. (This is not hypothetical: the loop adds a freelance arc most
fires, each authored from a sibling, so a single fat-fingered reward is the
realistic drift.) This guard makes that drift fail loudly.

THE TWO REWARD TIERS (by the canonical chain_id prefix)
-------------------------------------------------------
  * FREELANCE accessible side-jobs — every `kind: questline` whose chain_id is
    NOT prefixed `master_`. chargen_complete-gated, Independent-aligned.
    Canonical TOTAL arc reward (graduation + step rewards) = 450 credits +
    17 Independent rep, with a cp_reward-3 achievement. This is the tier that
    grows; it is also the one this guard protects most strictly.
  * t5 master-trainer trials — the `master_*` crafting-unlock arcs. Canonical
    TOTAL = 700 credits + ~17 faction rep (faction varies by trainer).

SELF-CALIBRATING BY DESIGN
--------------------------
The assertions read the canonical value FROM the tier itself and require the
rest to agree — they do NOT hard-pin 450/700. A DELIBERATE balance pass that
re-tunes a whole tier together still passes (conservative-on-balance: never
block intentional tuning); only a SINGLE arc drifting from its peers fails.
The literal numbers above are documentation, not the assertion. Absolute
magnitude stays guarded elsewhere (the rep CEILING corpus-wide; the <=1000
credit band per slice); this guard is about FAIRNESS within a tier and the
tiers staying distinct.

Pure data/test guard: no engine, parser, data, or client change.
"""
from __future__ import annotations

import sys
import unittest
from collections import defaultdict
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CHAINS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "tutorials" / "chains.yaml")

# Mirror of the tuned rep economy constants (test_t5_questline_content /
# the slice tests). Re-stated so a reader sees the band this guard sits in.
HONORED = 50
CEILING = 22


def _questlines():
    """All `kind: questline` chains from the shipped corpus file."""
    data = yaml.safe_load(open(CHAINS_PATH, encoding="utf-8"))
    return [c for c in data["chains"] if c.get("kind") == "questline"]


def _total_reward(chain):
    """TOTAL arc reward = graduation grant + every step's reward.

    Returns (credits:int, faction_rep:dict[str,int]).
    """
    credits = 0
    rep = defaultdict(int)
    grad = chain.get("graduation") or {}
    credits += int(grad.get("credits", 0) or 0)
    for fac, val in (grad.get("faction_rep") or {}).items():
        rep[fac] += int(val)
    for step in chain.get("steps") or []:
        reward = step.get("reward") or {}
        credits += int(reward.get("credits", 0) or 0)
        for fac, val in (reward.get("faction_rep") or {}).items():
            rep[fac] += int(val)
    return credits, dict(rep)


def _is_t5(chain):
    return str(chain.get("chain_id", "")).startswith("master_")


class _Corpus(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.all = _questlines()
        cls.freelance = [c for c in cls.all if not _is_t5(c)]
        cls.t5 = [c for c in cls.all if _is_t5(c)]


class TestTierPartition(_Corpus):

    def test_both_tiers_are_non_trivially_populated(self):
        # Guards against a vacuous pass if the chain_id convention ever
        # changes and the partition silently collapses to one bucket.
        self.assertGreaterEqual(
            len(self.freelance), 8,
            "expected a substantial freelance questline tier; the partition "
            "may have broken (chain_id naming convention changed?)")
        self.assertGreaterEqual(
            len(self.t5), 5,
            "expected the five master-trainer t5 trials")

    def test_every_questline_is_classified(self):
        self.assertEqual(len(self.all), len(self.freelance) + len(self.t5))


class TestFreelanceTierConsistency(_Corpus):
    """The growing tier: every accessible side-job pays the same."""

    def test_all_freelance_credits_identical(self):
        totals = {c["chain_id"]: _total_reward(c)[0] for c in self.freelance}
        distinct = set(totals.values())
        self.assertEqual(
            len(distinct), 1,
            "freelance questlines must all pay the same TOTAL credits "
            f"(self-calibrating); found {sorted(distinct)} across {totals}")

    def test_all_freelance_rep_identical(self):
        reps = {c["chain_id"]: frozenset(_total_reward(c)[1].items())
                for c in self.freelance}
        distinct = set(reps.values())
        self.assertEqual(
            len(distinct), 1,
            "freelance questlines must all grant the same faction_rep "
            f"(faction + magnitude); found {sorted(map(dict, distinct))}")

    def test_freelance_rep_is_independent_only(self):
        # A neutral favor pays Independent standing, never faction-coded rep —
        # that is what keeps them open to anyone regardless of allegiance.
        for c in self.freelance:
            rep = _total_reward(c)[1]
            self.assertEqual(
                set(rep), {"independent"},
                f"{c['chain_id']} grants non-Independent rep {set(rep)}; "
                "freelance side-jobs must stay allegiance-neutral")

    def test_freelance_rep_under_tuned_ceiling(self):
        for c in self.freelance:
            for fac, total in _total_reward(c)[1].items():
                self.assertLess(total, HONORED,
                                f"{c['chain_id']} {fac} {total} >= honored")
                self.assertLessEqual(total, CEILING,
                                     f"{c['chain_id']} {fac} {total} > ceiling")

    def test_freelance_achievements_share_cp_reward(self):
        import engine.achievements as A
        A.load_achievements()
        cp = {}
        for c in self.freelance:
            for key in (c.get("graduation") or {}).get("achievements") or []:
                ach = A.get_achievement(key)
                self.assertIsNotNone(
                    ach, f"{c['chain_id']} achievement {key} not registered")
                cp[key] = ach.get("cp_reward")
        self.assertTrue(cp, "no freelance achievements found")
        distinct = set(cp.values())
        self.assertEqual(
            len(distinct), 1,
            f"freelance achievements must share one cp_reward; found {cp}")


class TestT5TierConsistency(_Corpus):

    def test_all_t5_credits_identical(self):
        totals = {c["chain_id"]: _total_reward(c)[0] for c in self.t5}
        self.assertEqual(
            len(set(totals.values())), 1,
            f"t5 trainer trials must all pay the same TOTAL credits; {totals}")

    def test_all_t5_rep_under_ceiling(self):
        for c in self.t5:
            for fac, total in _total_reward(c)[1].items():
                self.assertLess(total, HONORED,
                                f"{c['chain_id']} {fac} {total} >= honored")
                self.assertLessEqual(total, CEILING,
                                     f"{c['chain_id']} {fac} {total} > ceiling")


class TestTiersAreDistinct(_Corpus):

    def test_freelance_pays_less_than_t5(self):
        # The tiering must be real: an accessible side-job is a lighter faucet
        # than an end-game crafting-unlock trial.
        free_cr = _total_reward(self.freelance[0])[0]
        t5_cr = _total_reward(self.t5[0])[0]
        self.assertLess(
            free_cr, t5_cr,
            f"freelance total {free_cr} should be < t5 total {t5_cr}; the "
            "two reward tiers have collapsed into one")


if __name__ == "__main__":
    unittest.main()
