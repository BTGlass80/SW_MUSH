"""tests/test_guide_09_timeline_accuracy.py — Guide_09 advancement-timeline accuracy.

Companion to test_guide_09_cp_progression_rework.py (which guards the headline
tick/cap/passive numbers in the *served* guide). This drop closes QA findings:

  M7 — the served guide (data/guides/Guide_09_CP_Progression.md) kept the v23
       headline numbers but its DERIVED timeline narrative ("~1 CP per 10-12
       days", "~7 months" for 3D->5D, "57 CP" for 3D->7D) was still the pre-v23
       (300-tick / 1-CP-week) rate -> internally self-contradictory.
  L5 — the design-corpus copy (docs/design/Guide_09_CP_Progression.md, a richer
       superset with Developer Internals) was fully pre-v23 (300/300/5, 1 CP/wk,
       "Both players must be in the same room") and unguarded -> drifts, misleads
       the next author.

Both files are guarded here, and the timeline arithmetic + the max CP/week rate
are cross-checked against the LIVE engine (cp_engine constants + the advance_skill
"cost = current whole-dice value" rule) so a future retune that updates the engine
but not the guide trips this test.
"""

import pathlib

import pytest

from engine.cp_engine import TICKS_PER_CP, WEEKLY_CAP_TICKS

SERVED_PATH = pathlib.Path("data/guides/Guide_09_CP_Progression.md")
CORPUS_PATH = pathlib.Path("docs/design/Guide_09_CP_Progression.md")


# --------------------------------------------------------------------------
# Engine-truth: the WEG R&E advance_skill rule (engine/character.py):
#   cost to raise a skill by 1 pip = the current TOTAL whole-dice value.
#   3 pips roll up to +1 die. Flat per pip (no doubling — QA L3 confirmed
#   the "cost doubled above attribute" branch is dead).
# --------------------------------------------------------------------------
def _cp_cost(start, end):
    """CP to advance a pool from (dice, pips) `start` to `end`."""
    cost = 0
    d, p = start
    while (d, p) < end:
        cost += d  # current whole-dice value, paid before the pip lands
        p += 1
        if p == 3:
            d, p = d + 1, 0
    return cost


def test_engine_cost_rule_matches_guide_milestones():
    """The CP totals the guide quotes are exactly what the engine rule yields."""
    assert _cp_cost((3, 0), (5, 0)) == 21      # Two dice  3D -> 5D
    assert _cp_cost((3, 0), (6, 0)) == 36      # Three dice 3D -> 6D
    assert _cp_cost((3, 0), (7, 0)) == 54      # Specialist 3D -> 7D (NOT 57)
    assert _cp_cost((4, 1), (6, 0)) == 23      # worked example 4D+1 -> 6D


def test_max_cp_per_week_matches_engine():
    """400 cap / 200 per CP = 2 CP/week is the live ceiling."""
    assert WEEKLY_CAP_TICKS // TICKS_PER_CP == 2


@pytest.mark.parametrize("path", [SERVED_PATH, CORPUS_PATH])
def test_guide_exists(path):
    assert path.exists(), f"{path} not found"


@pytest.mark.parametrize("path", [SERVED_PATH, CORPUS_PATH])
def test_no_stale_prev23_rate_markers(path):
    text = path.read_text(encoding="utf-8")
    stale = [
        "10–12 days",          # "~1 CP per 10-12 days" (old rate)
        "10-12 days",
        "roughly 7 months",        # 3D->5D at the old rate
        "7–9 months",          # 4D+1->6D at the old rate
        "every 8.5 weeks",         # passive-floor line at the old 300/5 rate
        "57 CP",                   # arithmetic error: 3D->7D is 54, not 57
        "300 ticks",
        "300-tick",
        "max 1 CP/week",
        "Both players must be in the same room",  # v23 removed same-room req
    ]
    for marker in stale:
        assert marker not in text, f"{path.name} still contains stale marker {marker!r}"


@pytest.mark.parametrize("path", [SERVED_PATH, CORPUS_PATH])
def test_v23_timeline_present(path):
    text = path.read_text(encoding="utf-8")
    # Corrected derived timeline, consistent with ~1 CP/week (2 CP/week cap).
    assert "1 CP/week" in text or "1 CP per week" in text
    assert "2 CP/week" in text
    assert "54 CP" in text                       # 3D -> 7D, engine-correct
    assert "Players do not need to be in the same room" in text


def test_corpus_developer_constants_are_v23():
    """The Developer Internals constants block must mirror the live engine."""
    text = CORPUS_PATH.read_text(encoding="utf-8")
    assert f"TICKS_PER_CP = {TICKS_PER_CP}" in text
    assert f"WEEKLY_CAP_TICKS = {WEEKLY_CAP_TICKS}" in text
    assert "PASSIVE_TICKS_PER_DAY = 10" in text
