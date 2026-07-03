"""Guard: Guide_26 §3 states the cult-rout reward in the SAME three tiers the
engine actually pays (accuracy pass, 2026-07-02).

The 2026-07-02 win-capstone tuning (`hollow-sun-tuning`, b00bc4c) made the
headline cult WIN pay real credits + a relic on top of rep/title, and updated
Guide_26 §3 to say so. But the reward paragraph then read that "everyone who did
a meaningful share of the fight also collects a credit bounty" — implying the
credit bounty reaches a *broader* set than the commemorative status flag. It does
not: in engine.communal_objective_runtime._distribute_rewards the capstone credit
is gated on `CO.earns_title(...)` — the SAME >=title_share_threshold predicate as
the status flag — so the bounty and the flag go to the identical set (the
fight-carriers), while only Republic REP is universal (everyone who scored).

This pins the corrected three-tier contract so a future engine change (making the
capstone universal) or a guide drift (re-implying a universal bounty) fails loudly
here instead of silently over-promising the reward to small contributors.
"""
import os

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_26_Director_AI.md")
RUNTIME_PATH = os.path.join(PROJECT_ROOT, "engine",
                            "communal_objective_runtime.py")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


# ── The engine actually pays the three tiers the guide describes ──────────────
class TestRewardTiersMatchEngine:
    def test_rep_is_universal_but_title_is_share_gated(self):
        """Rep pays every scorer (the show-up tier); the title/flag is gated on a
        real share of the total effort — so a tiny contributor gets rep but NOT
        the status flag."""
        from engine import communal_objective as CO

        total = 100
        big, small = 60, 5   # 60% share vs 5% share; title threshold is ~10%
        assert CO.earns_title(big, total, won=True) is True
        assert CO.earns_title(small, total, won=True) is False
        # ...but the small contributor still collects the universal rep floor.
        assert CO.reward_rep_for_share(small, total, won=True) >= CO.REP_FLOOR > 0

    def test_capstone_credit_shares_the_title_gate(self):
        """The credit bounty and the status flag go to the SAME set: the capstone
        credit block in _distribute_rewards is gated on CO.earns_title, not on
        every pts>0 contributor. This is the fact Guide_26 §3 leans on when it
        says the flag and the bounty go to 'the same people'."""
        src = _read(RUNTIME_PATH)
        idx = src.find("def _distribute_rewards")
        assert idx != -1, "reward distributor renamed — re-pin Guide_26 §3"
        body = src[idx:idx + 6000]
        # the capstone faucet fires only when the same title predicate holds
        assert "communal_win_capstone" in body
        assert "capstone > 0 and CO.earns_title(pts, total, won=True)" in body, (
            "the cult-win credit bounty is no longer gated on earns_title — it "
            "now reaches a different set than the status flag, so Guide_26 §3's "
            "'the status flag and the bounty go to the same people' is wrong"
        )


# ── The guide prose teaches that same three-tier structure ────────────────────
class TestGuideProseTeachesTiers:
    def test_prose_does_not_over_promise_the_bounty(self, guide_text):
        low = guide_text.lower()
        # the exact over-broad phrasing the accuracy pass removed
        assert "everyone who did a meaningful share" not in low, (
            "Guide_26 §3 again implies the credit bounty reaches everyone who "
            "did a meaningful share — the engine gates it on earns_title (the "
            "same set as the status flag)"
        )

    def test_prose_ties_flag_and_bounty_to_the_same_set(self, guide_text):
        low = guide_text.lower()
        assert "credit bounty" in low
        # the corrected teaching: the flag and the bounty go to the same people
        assert "same people" in low

    def test_prose_keeps_the_universal_rep_and_the_relic(self, guide_text):
        low = guide_text.lower()
        assert "republic reputation" in low
        assert "relic" in low
        # the rep band still quoted
        assert "3" in guide_text and "15" in guide_text
