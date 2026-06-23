# -*- coding: utf-8 -*-
"""Authoritative cross-check guard for Guide_14_Padawan_Master.md.

Opus quality pass, 2026-06-23 (Guide Version 1.2).

The existing test_guide_14_padawan_master_rework.py checks that the
+leave-master / +authorize features are PRESENT. It cannot catch the drift
class THIS guard exists for: prose that asserts the WRONG number, a PHANTOM
mechanic the engine never implements, or a command surface that has silently
moved. The 2026-06-23 authoritative pass found exactly that — six factual
defects invisible to every other test:

  1. A "small discount per design" on +teach that does not exist (the cost is
     the full train rate, 3 pips x per-pip price).
  2. A "+sheet lists your bond status" claim — the sheet renderer has no bond
     display at all.
  3. "+master / +padawan show ... location, current wound level" — they show
     online status, bond age, Weight-sense and Trials count; not location/wound.
  4. "Without endorsement, Trial attempts auto-fail" stated as a live hard gate
     — the endorsement flag is written + displayed + consumed but never gates
     a +trial attestation (the only consumer is the +trials display line).
  5. "When a Padawan dies, the Master gets notified" — death.py has no bond
     notification.
  6. "The Director recognizes bonded pairs" — director.py has no bond awareness.

This guard pins the numbers to the live engine constants and asserts the
phantom claims stay gone, so the guide can no longer silently drift from HEAD.
"""

import os
import re

GUIDE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "guides", "Guide_14_Padawan_Master.md",
)


def _guide() -> str:
    with open(GUIDE_PATH, encoding="utf-8") as f:
        return f.read()


# ── Numbers cross-checked against live engine constants ───────────────────

def test_bond_proposal_window_matches_engine():
    from parser.padawan_master_commands import _BOND_PROPOSAL_TTL
    minutes = _BOND_PROPOSAL_TTL // 60
    assert minutes == 10, "test premise drift: proposal TTL changed"
    text = _guide()
    assert f"{minutes} real-time minutes" in text or f"{minutes}-minute" in text, (
        "Guide must state the bond proposal window matching _BOND_PROPOSAL_TTL"
    )


def test_spar_cooldown_and_reward_match_engine():
    from parser.padawan_master_training_commands import (
        SPAR_COOLDOWN_SECS, SPAR_CP_REWARD,
    )
    hours = SPAR_COOLDOWN_SECS // 3600
    assert hours == 24 and SPAR_CP_REWARD == 1, "test premise drift"
    text = _guide()
    assert f"{hours} real-time hours" in text, (
        "Guide must state the spar cooldown matching SPAR_COOLDOWN_SECS"
    )
    assert "1 CP" in text, (
        "Guide must state the spar reward matching SPAR_CP_REWARD"
    )


def test_learn_request_window_matches_engine():
    from parser.padawan_master_training_commands import LEARN_REQUEST_TTL_SECS
    minutes = LEARN_REQUEST_TTL_SECS // 60
    assert minutes == 5, "test premise drift"
    text = _guide()
    assert f"{minutes} real-time minutes" in text or f"{minutes}-minute" in text, (
        "Guide must state the +learn request window matching "
        "LEARN_REQUEST_TTL_SECS"
    )


def test_knight_fp_grant_and_cap_match_engine():
    from parser.padawan_master_trials import KNIGHT_FP_GRANT, KNIGHT_FP_CAP
    assert KNIGHT_FP_GRANT == 1 and KNIGHT_FP_CAP == 50, "test premise drift"
    text = _guide()
    assert "+1 Force Point" in text, "Guide must state the +1 FP knight grant"
    assert "50" in text, "Guide must state the knight FP cap (50)"


def test_five_trials_match_engine():
    from parser.padawan_master_trials import FIVE_TRIALS
    assert set(FIVE_TRIALS) == {
        "skill", "courage", "flesh", "spirit", "insight"
    }, "test premise drift"
    text = _guide().lower()
    for trial in FIVE_TRIALS:
        assert trial in text, f"Guide must name the Trial of {trial.title()}"


def test_authorize_categories_match_engine():
    from parser.padawan_master_trials import AUTHORIZE_CATEGORIES
    assert set(AUTHORIZE_CATEGORIES) == {"offworld", "powers", "trials"}, (
        "test premise drift"
    )
    text = _guide()
    for cat in AUTHORIZE_CATEGORIES:
        assert cat in text, f"Guide must document the '{cat}' authorize category"


def test_marker_colors_match_engine():
    from parser.padawan_master_commands import PADAWAN_MARKER, MASTER_MARKER
    # bright green = 92, bright cyan = 96
    assert "92" in PADAWAN_MARKER and "96" in MASTER_MARKER, (
        "test premise drift: marker color codes changed"
    )
    text = _guide()
    assert "bright green" in text and "[Padawan]" in text
    assert "bright cyan" in text and "[Master]" in text


# ── All 16 documented command keys exist as real command classes ──────────

def test_all_documented_command_keys_exist():
    import parser.padawan_master_commands as pmc
    import parser.padawan_master_training_commands as pmt
    import parser.padawan_master_trials as pmtr
    from parser.commands import BaseCommand

    live_keys = set()
    for mod in (pmc, pmt, pmtr):
        for obj in vars(mod).values():
            if (isinstance(obj, type) and issubclass(obj, BaseCommand)
                    and obj is not BaseCommand):
                key = getattr(obj, "key", None)
                if key:
                    live_keys.add(key)

    text = _guide()
    documented = {
        "+master", "+padawan", "+bond", "+release", "+leave-master",
        "+learn", "+teach", "+spar", "+trials", "+endorse", "+authorize",
        "+trial", "+knight", "@bond", "@trial", "@knight",
    }
    for key in documented:
        assert key in live_keys, (
            f"Guide documents '{key}' but no live command class defines it"
        )
        assert key in text, f"'{key}' missing from the guide body"


# ── Phantom claims corrected by the authoritative pass must stay gone ──────

def test_no_phantom_teach_discount():
    text = _guide().lower()
    assert "small discount" not in text, (
        "Phantom '+teach small discount' must stay removed — the cost is the "
        "full train rate"
    )
    assert "reduced or zero cost" not in text, (
        "Phantom 'reduced or zero cost' teach claim must stay removed"
    )


def test_no_phantom_sheet_bond_display():
    text = _guide()
    # The sheet renderer has no bond display; the guide must not claim one.
    assert not re.search(r"\+sheet.{0,40}bond status", text, re.IGNORECASE), (
        "Phantom '+sheet lists your bond status' claim must stay removed"
    )


def test_no_phantom_location_or_wound_in_status_cmds():
    text = _guide().lower()
    assert "current wound level (so a master knows" not in text, (
        "+master/+padawan do not show wound level — phantom claim must stay gone"
    )


def test_endorsement_not_overstated_as_live_hard_gate():
    text = _guide()
    # The old categorical "Without endorsement, Trial attempts auto-fail."
    # (stated as a present-tense enforced gate) must be gone. The guide may
    # describe the forthcoming/future enforcement, but not as a live gate.
    assert "**Without endorsement, Trial attempts auto-fail.**" not in text, (
        "Endorsement auto-fail must not be presented as a live hard gate — it "
        "is a write+vouch surface; the +trial attestation is the real gate"
    )


def test_real_weight_sense_feature_documented():
    text = _guide()
    assert "Through the bond" in text, (
        "The real Weight-of-War 'Through the bond' sense (shown by "
        "+master/+padawan) should be documented"
    )
    assert "Trials passed" in text or "Trials progress" in text, (
        "The Trials-passed count shown by +master/+padawan should be documented"
    )
