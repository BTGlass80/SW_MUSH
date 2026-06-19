"""Guard: Guide_18 The Jedi Village teaches the Trial mechanics that actually
match the engine.

The Opus-owned guides quality pass.  Guide_18 carried a dense set of
test-INVISIBLE drift on the five Trials — the green suite never sees guide prose,
and these are flagship onboarding mechanics for the entire Force/Jedi path.  This
pass corrected, against ``engine/village_trials.py`` + ``engine/force_signs.py``
+ ``engine/jedi_gating.py`` + ``engine/village_choice.py``:

* **Courage is a single 3-way choice after a recital, not a multi-turn dialogue.**
  ``trial courage 1`` ("I won't deny it.") and ``trial courage 2`` ("How did you
  know?") BOTH pass (``COURAGE_PASS_CHOICES == (1, 2)``); only ``trial courage 3``
  (walk away) fails.  The old "choose the easy answers and you fail / costly
  answers pass" framing was wrong — the test is engage-vs-walk-away.
* **Courage fail lockout is 24 hours, not "the 14-day cooldown."**
  ``COURAGE_FAIL_COOLDOWN_SECONDS == 86_400``.  The 14-day inter-Trial cooldown
  only gates the gap between *successful* Trials.
* **Flesh is a 6-hour WALL-CLOCK dwell from cave entry, not continuous presence.**
  ``FLESH_DURATION_SECONDS == 21_600``; the engine measures ``now -
  flesh_started_at`` and tells the player *"You may leave the caves; the
  discipline continues. You may log out; the discipline continues."*  The old
  "you cannot leave or the Trial fails + 14-day cooldown" was wrong.
* **Spirit is a confrontation with the player's dark-future self, count-driven.**
  Up to ``SPIRIT_MAX_TURNS == 7`` turns; pass clean at
  ``SPIRIT_REJECTIONS_TO_PASS == 4`` rejections; Path C locks at
  ``SPIRIT_DARK_PULL_TO_LOCK_C == 3`` temptation pulls; otherwise a no-cooldown
  soft-fail that resets on re-entry.  The old "Yarael presents a temptation
  scenario, refuse-or-accept" binary missed the third (ambivalent) option, the
  thresholds, and the soft-fail.

Each correction is pinned to the live engine constant so a future retune that
desyncs the guide fails loudly here instead of silently misleading players.  The
unchanged-and-verified claims (Hermit coords, sign math, path rewards/teleports,
Act/inter-Trial cooldowns) are pinned too.
"""
import os
import re

import pytest

import engine.force_signs as fs
import engine.jedi_gating as jg
import engine.village_choice as vc
import engine.village_trials as vt

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_18_Jedi_Village.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def guide_lower(guide):
    return guide.lower()


# ── Engine constants (the source of truth this guide must track) ───────────────

def test_engine_constants_unchanged():
    """If any of these trip, the engine retuned — re-verify Guide_18 prose."""
    assert fs.FORCE_SIGNS_FOR_INVITATION == 5
    assert fs.BASE_SIGN_PROBABILITY_PER_TICK == 0.0028
    assert fs.PREDISPOSITION_SCALING == 2.0
    assert jg.PLAY_TIME_GATE_SECONDS == 50 * 60 * 60          # 180,000
    assert jg.ACT_1_TO_ACT_2_COOLDOWN_SECONDS == 7 * 24 * 3600   # 604,800
    assert jg.INTER_TRIAL_COOLDOWN_SECONDS == 14 * 24 * 3600      # 1,209,600
    assert vt.SKILL_DIFFICULTIES == [8, 12, 15]
    assert vt.SKILL_RETRY_COOLDOWN_SECONDS == 60 * 60            # 1 hour
    assert vt.SKILL_TRIAL_SKILL == "craft_lightsaber"
    assert vt.COURAGE_FAIL_COOLDOWN_SECONDS == 24 * 60 * 60      # 24 hours
    assert vt.COURAGE_PASS_CHOICES == (1, 2)
    assert vt.COURAGE_CHOICE_WALK_AWAY == 3
    assert vt.FLESH_DURATION_SECONDS == 6 * 60 * 60             # 6 hours
    assert vt.SPIRIT_MAX_TURNS == 7
    assert vt.SPIRIT_REJECTIONS_TO_PASS == 4
    assert vt.SPIRIT_DARK_PULL_TO_LOCK_C == 3
    assert vc.PATH_A_DROP_SLUG == "jedi_temple_main_gate"
    assert vc.PATH_B_DROP_SLUG == "village_common_square"
    assert vc.PATH_C_DROP_SLUG == "dune_sea_anchor_stones"


# ── Act 1 — sign math (verified clean; pinned) ─────────────────────────────────

def test_act1_sign_math(guide):
    assert "0.0028" in guide
    assert re.search(r"five\s+signs|5\s+signs", guide, re.I)
    # 50-hour gate, both the hours and the raw seconds the guide quotes.
    assert "50 real-time hours" in guide
    assert "180,000" in guide


def test_hermit_coords_match_world_yaml(guide):
    # The Hermit's Hut sits at (33, 16) in the Dune Sea, west of the Anchor
    # Stones — verified against data/worlds/clone_wars/wilderness/dune_sea.yaml.
    assert "(33, 16)" in guide
    dune = _read(os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                              "wilderness", "dune_sea.yaml"))
    assert "[33, 16]" in dune


# ── Trial of Skill (verified clean; pinned) ────────────────────────────────────

def test_skill_trial(guide):
    assert "8, 12, 15" in guide
    assert "craft_lightsaber" in guide
    assert "kyber crystal" in guide.lower() or "kyber crystal" in guide


# ── Trial of Courage (corrected) ───────────────────────────────────────────────

def test_courage_is_single_three_way_choice(guide):
    # Both engaged responses pass; only walking away fails.
    assert "I won't deny it." in guide
    assert "How did you know?" in guide
    assert "trial courage 1" in guide and "trial courage 3" in guide


def test_courage_fail_lockout_is_24h_not_14_day(guide, guide_lower):
    assert "24 real-time hours" in guide or "24-hour" in guide_lower
    # Regression: the Courage section must NOT teach a 14-day fail-retry wait.
    assert "reattempt after the 14-day cooldown" not in guide


def test_courage_easy_costly_framing_removed(guide):
    # The wrong "easy answers fail / costly answers pass" model is gone.
    assert "Players who choose the easy answers fail" not in guide


# ── Trial of Flesh (corrected) ─────────────────────────────────────────────────

def test_flesh_is_six_hour_wallclock(guide, guide_lower):
    assert "six-hour" in guide_lower or "six hours" in guide_lower
    assert "wall-clock" in guide_lower
    # The defining correction: you MAY leave; the timer keeps running.
    assert "may leave the caves" in guide_lower
    assert "the discipline continues" in guide_lower


def test_flesh_no_fail_on_leave(guide):
    # Regression: the old "leave the room -> Trial fails + 14-day cooldown" is gone.
    assert "if you leave the room, the Trial fails" not in guide


# ── Trial of Spirit (corrected) ────────────────────────────────────────────────

def test_spirit_is_dark_future_self(guide_lower):
    assert "dark-future self" in guide_lower
    assert "trial spirit" in guide_lower


def test_spirit_thresholds(guide, guide_lower):
    # 7 turns; 4 rejections to pass; 3 pulls to lock Path C.
    assert "seven turns" in guide_lower or "up to seven" in guide_lower
    assert "four rejections" in guide_lower
    assert "three times" in guide_lower
    # The three response options exist (reject / waver / lean in).
    assert "trial spirit 1" in guide and "trial spirit 3" in guide


def test_spirit_soft_fail_no_cooldown(guide_lower):
    assert "soft fail" in guide_lower or "soft-fail" in guide_lower
    assert "no real-time cooldown" in guide_lower or "no cooldown" in guide_lower


def test_spirit_flags(guide):
    assert "village_trial_spirit_done" in guide
    assert "village_trial_spirit_path_c_locked" in guide


# ── Cooldowns table (corrected to be complete) ─────────────────────────────────

def test_cooldowns_table(guide):
    assert re.search(r"7\s+real-time\s+days|seven\s+real-time\s+days", guide, re.I)
    assert re.search(r"14\s+real-time\s+days|14-day", guide, re.I)
    # The previously-missing rows are now present.
    assert "Courage Trial fail lockout" in guide
    assert "Flesh Trial dwell" in guide


# ── Path A/B/C rewards & teleports (verified clean; pinned) ────────────────────

def test_path_rewards(guide, guide_lower):
    assert "Tova Resh" in guide                       # Path A intake NPC
    assert "Jedi Temple Main Gate" in guide           # Path A teleport
    assert "Village Common Square" in guide           # Path B teleport
    assert "Dune Sea Anchor Stones" in guide          # Path C teleport
    assert re.search(r"\+50 rep|\+50 reputation", guide)   # Path B Independent
    assert "dark_path_unlocked" in guide
    assert "dark_contact_freq" in guide


# ── Insight commands (corrected to precise arg form) ───────────────────────────

def test_insight_commands(guide):
    assert "accuse fragment_" in guide
    assert "examine fragment_" in guide
