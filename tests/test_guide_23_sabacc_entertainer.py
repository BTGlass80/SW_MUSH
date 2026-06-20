"""Guard: Guide_23 Sabacc & Entertainer teaches commands that actually RESOLVE
against the live registry, and its numbers match the engine.

The Opus-owned guides quality pass.  Guide_23 carried a dense set of mechanical
claims the green suite never saw (the convention invariant guards the registry,
not guide prose).  This pass corrected — and this test pins — the following:

* **Sabacc criticals pay NO cash bonus.**  The guide claimed a crit pays
  "Bet x 2, no house cut".  In code (``parser.sabacc_commands``) the ``win`` and
  ``critical`` outcomes share ONE payout branch (``if outcome in
  ("win", "critical")``): both net ``Bet x 0.9``.  A crit is recognition +
  flavor + the achievement, not a jackpot.
* **The Cantina Brawl does NOT double sabacc payouts** — only the bet *ceiling*
  doubles (``bet_max = BET_MAX_DEFAULT * 2``).  Only ``perform`` payouts double
  (``brawl_mult = 2.0`` in ``parser.entertainer_commands``).  The old "All
  payouts x 2" / "Sabacc payouts double" claims were wrong.
* **The dealer pool is auto-detected** from the dealer NPC's Gambling skill
  (default 3D), rolled flat — not a hard "3D Gambling".
* **The morale aura is now WIRED.**  ``perform_morale_aware_check`` (the function
  that subtracts the aura magnitude from a difficulty) had zero live callers —
  the entertainer's headline buff was inert.  The talk-to-NPC persuasion check
  (``parser.npc_commands.TalkCommand._run_persuasion_check``) now routes through
  it, so the aura genuinely lowers in-room morale-flavored difficulties.
* **Auras do NOT stack** — highest magnitude wins (overwrite-if->=).
* The **audience bonus** (+15%/head, cap 4 heads = +60%) and the per-perform
  **fatigue** (+3 difficulty) were undocumented and are now in the guide.
* The **Entertainers' Guild** discount is 20% off *all* skill training, not a
  Persuasion-specific discount.

Each correction is pinned against the live engine so a future retune that
desyncs the guide fails loudly here instead of silently misleading players.
"""
import importlib.util
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_23_Sabacc_Entertainer.md")
SABACC_SRC = os.path.join(PROJECT_ROOT, "parser", "sabacc_commands.py")
ENTERTAINER_SRC = os.path.join(PROJECT_ROOT, "parser", "entertainer_commands.py")
NPC_SRC = os.path.join(PROJECT_ROOT, "parser", "npc_commands.py")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def reg():
    spec = importlib.util.spec_from_file_location(
        "_sabaccreg_for_guide",
        os.path.join(PROJECT_ROOT, "tests",
                     "test_t321_admin_command_access_invariant.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod._build_full_registry()


# ── Every command Guide_23 teaches must resolve against HEAD ──────────────────
class TestGuideCommandsResolve:
    @pytest.mark.parametrize("form", ["sabacc", "perform"])
    def test_form_resolves(self, reg, form):
        assert reg.get(form) is not None, (
            f"Guide_23 teaches {form!r} but it no longer resolves against the "
            f"live registry"
        )


# ── Sabacc numbers must match parser.sabacc_commands constants ────────────────
class TestSabaccNumbers:
    def test_constants_match_guide(self, guide_text):
        from parser import sabacc_commands as sc

        assert sc.BET_MIN == 50
        assert sc.BET_MAX_DEFAULT == 2000
        assert sc.BET_DEFAULT == 100
        assert sc.HOUSE_CUT == 0.10
        assert sc.WIN_COOLDOWN_S == 300       # 5 min
        assert sc.LOSS_COOLDOWN_S == 120      # 2 min
        assert sc.DEALER_DICE == 3            # *default* dealer pool
        # Guide prose carries these numbers verbatim.
        assert "50-2,000 cr" in guide_text
        assert "100 cr" in guide_text
        assert "5-minute cooldown" in guide_text or "5 minutes" in guide_text
        assert "2-minute cooldown" in guide_text or "2 minutes" in guide_text

    def test_crit_pays_same_as_win_in_code(self):
        """Win and Critical share ONE payout branch — a crit is no jackpot."""
        src = _read(SABACC_SRC)
        assert 'outcome in ("win", "critical")' in src, (
            "Sabacc crit/win payout branches diverged — re-verify Guide_23's "
            "claim that a crit pays the same credits as a win"
        )
        # There must be no dedicated crit-payout multiplier constant.
        assert not re.search(r"CRIT.*=.*2\b", src), (
            "A crit-payout multiplier appeared in sabacc — Guide_23 says a crit "
            "carries no cash bonus"
        )

    def test_guide_drops_the_crit_double_phantom(self, guide_text):
        for bad in ("Bet × 2, no house cut", "Bet x 2 (no house cut)",
                    "pays you 200 cr", "doubles to 400 cr"):
            assert bad not in guide_text, (
                f"Guide_23 must not claim the {bad!r} crit jackpot — a sabacc "
                f"crit pays the same credits as a win"
            )

    def test_guide_states_crit_is_recognition_only(self, guide_text):
        assert "same credits as a win" in guide_text or \
               "same as a win" in guide_text, (
            "Guide_23 should state a sabacc crit pays the same as a win"
        )


# ── Cantina Brawl scope: sabacc bet-ceiling only; perform payout x2 ───────────
class TestBrawlScope:
    def test_sabacc_only_doubles_bet_ceiling(self):
        src = _read(SABACC_SRC)
        assert "BET_MAX_DEFAULT * 2" in src, (
            "Sabacc brawl handling changed — Guide_23 says the brawl doubles the "
            "bet ceiling"
        )

    def test_perform_doubles_payout(self):
        src = _read(ENTERTAINER_SRC)
        assert "brawl_mult = 2.0" in src, (
            "Perform brawl multiplier changed — Guide_23 says brawl doubles "
            "perform payouts"
        )

    def test_guide_drops_the_all_payouts_double_phantom(self, guide_text):
        for bad in ("Sabacc payouts double", "All payouts × 2", "All payouts x 2"):
            assert bad not in guide_text, (
                f"Guide_23 must not claim {bad!r} — only the sabacc bet ceiling "
                f"and perform payouts double in a brawl"
            )


# ── Perform numbers must match parser.entertainer_commands constants ──────────
class TestPerformNumbers:
    def test_constants_match_guide(self, guide_text):
        from parser import entertainer_commands as ec

        assert ec._BASE_PAY_MIN == 50
        assert ec._BASE_PAY_MAX == 200
        assert ec._CRIT_PAY_MIN == 250
        assert ec._CRIT_PAY_MAX == 500
        assert ec._PARTIAL_PAY == 25
        assert ec._PERFORM_DIFFICULTY == 10
        assert ec._SUCCESS_COOLDOWN == 600    # 10 min
        assert ec._FAILURE_COOLDOWN == 300    # 5 min
        assert ec._FATIGUE_WINDOW_SECONDS == 8 * 3600
        assert ec._FATIGUE_PENALTY_PIPS == 3
        assert ec._AURA_DURATION_SECONDS == 1800
        assert ec._AUDIENCE_BONUS_PER == 0.15
        assert ec._AUDIENCE_CAP == 4
        # Guide prose carries the headline numbers.
        assert "50-200 cr" in guide_text
        assert "250-500" in guide_text
        assert "25 cr" in guide_text
        assert "10 (Easy)" in guide_text or "Easy (10)" in guide_text

    def test_audience_multiplier_cap(self):
        from parser.entertainer_commands import audience_multiplier, _AUDIENCE_CAP

        assert audience_multiplier(0) == 1.0
        assert audience_multiplier(1) == pytest.approx(1.15)
        # capped at 4 heads => +60%
        assert audience_multiplier(_AUDIENCE_CAP) == pytest.approx(1.6)
        assert audience_multiplier(99) == pytest.approx(1.6)

    def test_guide_documents_audience_bonus(self, guide_text):
        assert "+15%" in guide_text and ("+60%" in guide_text), (
            "Guide_23 must document the audience bonus (+15%/head, cap +60%)"
        )


# ── Morale aura: WIRED consumer + correct semantics ──────────────────────────
class TestMoraleAura:
    def test_aura_consumer_is_wired_into_talk_persuasion(self):
        """The completed feature: the talk-to-NPC persuasion check routes through
        the aura-aware helper.  If this regresses, the entertainer's headline buff
        goes inert again."""
        src = _read(NPC_SRC)
        assert "perform_morale_aware_check" in src, (
            "TalkCommand no longer routes its persuasion check through "
            "perform_morale_aware_check — the morale aura buff is inert again"
        )

    def test_aura_magnitudes_and_skillset(self, guide_text):
        from parser.entertainer_commands import (
            _aura_magnitude_for_margin, _AURA_DURATION_SECONDS)
        from engine.skill_checks import MORALE_FLAVORED_SKILLS

        # Magnitude bands per design §2.2 (note: 4 is intentionally skipped).
        assert _aura_magnitude_for_margin(0) == 0
        assert _aura_magnitude_for_margin(1) == 1
        assert _aura_magnitude_for_margin(5) == 2
        assert _aura_magnitude_for_margin(10) == 3
        assert _aura_magnitude_for_margin(15) == 5
        assert _AURA_DURATION_SECONDS == 1800
        # The guide names the affected skill set.
        for skill in ("Persuasion", "Command", "Con", "Bargain",
                      "Willpower", "Gambling"):
            assert skill in guide_text, (
                f"Guide_23 should list {skill} among the aura-affected skills"
            )
        # And those skills really are the morale-flavored set.
        for skill in ("persuasion", "command", "con", "bargain",
                      "willpower", "gambling"):
            assert skill in MORALE_FLAVORED_SKILLS

    def test_guide_says_no_stacking(self, guide_text):
        assert "do not stack" in guide_text or "does not stack" in guide_text, (
            "Guide_23 must state auras do not stack (highest magnitude wins)"
        )
        assert "can stack" not in guide_text, (
            "Guide_23 must not claim auras can stack — code keeps the strongest"
        )


# ── Entertainers' Guild discount is all-skill, not Persuasion-specific ─────────
class TestGuildDiscount:
    def test_guild_discount_is_twenty_percent_all_skills(self, guide_text):
        from engine.organizations import GUILD_CP_DISCOUNT

        assert GUILD_CP_DISCOUNT == 0.20
        assert "20% CP discount on all skill training" in guide_text or \
               "20% CP discount on all skill" in guide_text, (
            "Guide_23 should describe the guild discount as 20% off ALL skill "
            "training, not Persuasion-specific"
        )
