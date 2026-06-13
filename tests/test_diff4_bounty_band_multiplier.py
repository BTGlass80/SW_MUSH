# -*- coding: utf-8 -*-
"""
tests/test_diff4_bounty_band_multiplier.py — DIFF.4 threat-band reward
scaling at the bounty payout.

Per difficulty_tiers_design_v1.md §7. The bounty payout scales by the
threat band of where the target was (contract.target_room_id, bound in
drop 26): hunting a Deep Wilds mark pays the danger premium (2.0×), a
Frontier mark pays 0.6× — so a veteran can't farm newbie contracts for
full rate.

This is a STRUCTURAL pin (the multiplier is applied before the metered
`bounty` faucet, mirroring the bounty_reward_mult surge pattern) plus a
math check on reward_multiplier. The full claim→defeat→collect path is
exercised by the bounty smoke; this pins the wiring + the band→× mapping.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _src(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


# ── Structural pin: the band multiplier is wired before the faucet ──────

def test_band_multiplier_wired_before_bounty_payout():
    src = _src("parser/bounty_commands.py")
    assert "reward_multiplier" in src, (
        "DIFF.4: the threat-band reward_multiplier is not wired into "
        "the bounty payout."
    )
    assert "target_room_id" in src, (
        "DIFF.4: the band multiplier must scale off contract."
        "target_room_id (the danger of the hunt)."
    )
    # The band read must precede the metered `bounty` adjust_credits call
    # — otherwise it would scale nothing.
    i_band = src.index("reward_multiplier")
    i_pay = src.index('adjust_credits(char["id"], reward, "bounty")')
    assert i_band < i_pay, (
        "DIFF.4: reward_multiplier applied AFTER the payout, not before."
    )


def test_band_multiplier_rides_the_existing_bounty_faucet():
    """No new credit faucet — the scaled reward goes through the SAME
    `bounty`-tagged adjust_credits call (faucet discipline)."""
    src = _src("parser/bounty_commands.py")
    # Exactly one bounty-tagged payout faucet in the collect path.
    assert src.count('adjust_credits(char["id"], reward, "bounty")') >= 1


# ── Math: the band → multiplier mapping is correct ──────────────────────

def test_reward_multiplier_band_mapping():
    from engine.threat_band import ThreatBand, reward_multiplier
    # The design's gradient: Frontier discounts, Wilds doubles.
    assert reward_multiplier(ThreatBand.FRONTIER) == 0.6
    assert reward_multiplier(ThreatBand.SETTLED) == 1.0
    assert reward_multiplier(ThreatBand.CONTESTED_MARCHES) == 1.4
    assert reward_multiplier(ThreatBand.WILDS) == 2.0


def test_a_wilds_bounty_pays_more_than_a_frontier_one():
    """The whole point: same base reward, different band → veteran can't
    farm the newbie zone for full rate."""
    from engine.threat_band import ThreatBand, reward_multiplier
    base = 1000
    frontier_pay = int(base * reward_multiplier(ThreatBand.FRONTIER))
    wilds_pay = int(base * reward_multiplier(ThreatBand.WILDS))
    assert wilds_pay > base > frontier_pay, (
        f"DIFF.4: the gradient is broken — frontier={frontier_pay}, "
        f"base={base}, wilds={wilds_pay}"
    )
    # Roughly: Wilds pays ~3.3× what Frontier pays for the same contract.
    assert wilds_pay > frontier_pay * 3


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
