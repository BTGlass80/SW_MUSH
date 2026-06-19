"""Guard: Guide_25 Spacer Quest ("From Dust to Stars") matches engine HEAD.

The Opus-owned guides quality pass.  Guide_25 is the onboarding path for new
spacer characters, and it had drifted from ``engine/spacer_quest.py`` in many
test-INVISIBLE ways (the curated suite never reads guide prose):

* **Wrong command.**  The guide taught ``+quest`` throughout, but the
  spacer-quest command is keyed ``+spacerquest`` (aliases ``quest`` / ``+fdts`` /
  ``+dusttostars``); plain ``+quest`` is the *narrative* quest umbrella
  (``parser.narrative_commands.QuestCommand``) — a different system.

* **Wrong phase names / boundaries.**  Phase 2 is "The Wider Galaxy" (steps
  8-14, seven steps) not "Wider Horizons" (8-13); Phase 3 is "Off-World"
  (steps 15-20, six steps) not "Becoming a Spacer" (14-20).  "Making Contacts"
  is the Phase-2 gate (step 14), not a Phase-3 step.

* **Wrong reward numbers.**  Nearly every per-step credit value and every
  per-phase total was off (e.g. the guide's ~11,300 cr total vs the real
  ~10,950 cr; step 20 Grand Tour pays 500 cr + a title, not 1,000 cr).

* **Wrong Phase-5 geography.**  The 06-01 era migration removed Kessel and
  Corellia from the Clone Wars graph; Lira Shan is a **Kuat Drive Yards** broker
  on **Kuat**, not a "CEC officer at Coronet Starport on Corellia".

* **Phantom mechanics.**  Missed-debt-payment consequences are escalating Grek
  comlinks only (no enforcer spawn / patrol scrutiny / rep loss — the enforcer
  is an unimplemented TODO); paying off the debt earns the (Debt Free) title
  the guide never mentioned; the loaner ship becomes the OWNED ship (it does
  not "revert to its owner at Phase 3 end").

This test cross-checks the guide against the live ``QUEST_STEPS`` /
``PHASE_NAMES`` data and the engine's reward arithmetic, so a future retune that
desyncs the guide fails loudly here.  ``engine.spacer_quest`` is pure-stdlib, so
the import is cheap and import-order-safe.
"""
import os

import pytest

from engine import spacer_quest as sq

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_25_Spacer_Quest.md")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


# ── Engine-derived ground truth ──────────────────────────────────────────

def _phase_steps(phase):
    return [s for s in sq.QUEST_STEPS if s["phase"] == phase]


def _phase_total(phase):
    return sum(s.get("reward_credits", 0) for s in _phase_steps(phase))


GRAND_TOTAL = sum(s.get("reward_credits", 0) for s in sq.QUEST_STEPS)


# ── Structure ────────────────────────────────────────────────────────────

def test_guide_exists():
    assert os.path.exists(GUIDE_PATH)


def test_thirty_steps_five_phases():
    assert len(sq.QUEST_STEPS) == 30
    assert set(s["step_id"] for s in sq.QUEST_STEPS) == set(range(1, 31))
    assert set(sq.PHASE_NAMES) == {1, 2, 3, 4, 5}


def test_phase_names_present_and_correct(guide_text):
    # The canonical phase names the +spacerquest header prints must appear.
    for phase, name in sq.PHASE_NAMES.items():
        assert name in guide_text, f"Phase {phase} name {name!r} missing from guide"


def test_phase_boundaries_match_engine(guide_text):
    # Phase 2 = steps 8-14 (seven); Phase 3 = steps 15-20 (six).
    assert [s["step_id"] for s in _phase_steps(1)] == list(range(1, 8))
    assert [s["step_id"] for s in _phase_steps(2)] == list(range(8, 15))
    assert [s["step_id"] for s in _phase_steps(3)] == list(range(15, 21))
    assert [s["step_id"] for s in _phase_steps(4)] == list(range(21, 27))
    assert [s["step_id"] for s in _phase_steps(5)] == list(range(27, 31))
    # The guide must state the corrected ranges.
    assert "Steps 8-14" in guide_text
    assert "Steps 15-20" in guide_text


# ── Anti-drift markers (the old wrong values must NOT reappear) ───────────

def test_no_stale_phase_names(guide_text):
    assert "Wider Horizons" not in guide_text
    assert "Becoming a Spacer" not in guide_text


def test_no_corellia_or_coronet_for_lira(guide_text):
    # Kessel/Corellia were removed from the CW graph; Lira is on Kuat (KDY).
    assert "Corellia" not in guide_text
    assert "Coronet" not in guide_text
    assert "CEC" not in guide_text
    assert "Kuat Drive Yards" in guide_text


def test_uses_spacerquest_command_not_bare_plus_quest(guide_text):
    assert "+spacerquest" in guide_text
    # Plain `+quest` is the narrative umbrella, NOT the spacer chain — the guide
    # may mention it only to disambiguate, never as a command-table instruction.
    assert "`+quest log`" not in guide_text
    assert "`+quest abandon`" not in guide_text
    assert "+quest abandon confirm" not in guide_text


# ── Reward arithmetic ────────────────────────────────────────────────────

def test_per_phase_totals_present(guide_text):
    expected = {1: 2300, 2: 2450, 3: 2000, 4: 2700, 5: 1500}
    for phase, total in expected.items():
        assert _phase_total(phase) == total, (
            f"engine phase {phase} total changed to {_phase_total(phase)}")
        assert f"{total:,}" in guide_text, (
            f"phase {phase} total {total:,} missing from guide")


def test_grand_total_present(guide_text):
    assert GRAND_TOTAL == 10950, f"engine grand total changed to {GRAND_TOTAL}"
    assert "10,950" in guide_text


def test_down_payment_and_debt_numbers(guide_text):
    # Step 27 cost.
    step27 = sq.get_step(27)
    assert step27["objective_data"]["cost"] == 8000
    assert "8,000" in guide_text
    # Debt activated at step 28.
    assert "10,000" in guide_text  # principal
    assert "500" in guide_text     # weekly payment


# ── Titles ───────────────────────────────────────────────────────────────

def test_all_engine_titles_documented(guide_text):
    engine_titles = {s["reward_title"] for s in sq.QUEST_STEPS
                     if s.get("reward_title")}
    # Strip the parens for a forgiving substring check.
    for title in engine_titles:
        bare = title.strip("()")
        assert bare in guide_text, f"title {title!r} missing from guide"
    # The payoff-only (Debt Free) title lives in engine/debt.py, not QUEST_STEPS.
    assert "Debt Free" in guide_text


def test_captain_title_is_step_29_not_final(guide_text):
    assert sq.get_step(29)["reward_title"] == "(Captain)"
    assert sq.get_step(30)["reward_title"] == "(Spacer)"


# ── Key step facts ───────────────────────────────────────────────────────

def test_step_5_is_three_missions(guide_text):
    step5 = sq.get_step(5)
    assert step5["objective_type"] == "mission_count"
    assert step5["objective_data"]["target"] == 3
    assert "Complete 3 missions" in guide_text


def test_step_12_is_cpstatus_not_sheet(guide_text):
    step12 = sq.get_step(12)
    assert step12["objective_data"]["command"] == "cpstatus"
    assert "cpstatus" in guide_text


def test_lira_on_kuat(guide_text):
    step27 = sq.get_step(27)
    assert "Kuat Drive Yards" in step27["objective_data"]["room_substr"]


def test_ship_is_ghtroc_720(guide_text):
    assert "Ghtroc 720" in guide_text
    assert "Rusty Mynock" in guide_text


def test_grand_completion_awards_cp(guide_text):
    # Step 30 chain_complete flag + the +1 CP grand completion.
    assert sq.get_step(30)["reward_flags"].get("chain_complete") is True
    assert "Character Point" in guide_text
