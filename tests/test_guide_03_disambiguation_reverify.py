"""Guide_03 re-verify: the §3 "Picking a target when names collide" subsection
must stay reconciled with the live actionable-disambiguation behaviour shipped
in `7225337` (engine/matching.py `Match.error_message`).

Why this guard exists
---------------------
The 4th fun re-run's #1 "kills-it" finding was a stranded newcomer: in the
combat sim, ``attack droid`` matches *both* B1 Sim Droid Alpha and Bravo, and
the old prompt — ``Which one? (matches: B1 Sim Droid Alpha, B1 Sim Droid
Bravo)`` — listed names without telling the player HOW to choose.  The fix made
the prompt *actionable*: it now echoes the shortest unique token the parser
accepts (``try: 'Alpha', 'Bravo'.``).  Guide_03 §3 — where a player learns
``attack <target>`` — taught the command (its own example is literally
``attack droid``) but said nothing about the ambiguity case, so a newcomer who
hit the prompt had no guide to fall back on.

This test pins, all against HEAD so an engine revert/retune fails loudly here:

1. the live engine produces the NEW actionable message (distinguishing tokens +
   "Be more specific — try:" phrasing), and NOT the old listing-only format;
2. the documented full-name fallback (names fully overlap) actually fires;
3. the combat command genuinely surfaces ``error_message`` on AMBIGUOUS
   (producer -> consumer), so the guide's "the game tells you" claim is real;
4. the combat sim still seeds the two B1 Sim Droids the prose names, so the
   worked example is not a phantom;
5. the guide prose teaches the recovery (token-to-type, fallback, "not a dead
   end") and quotes the live message verbatim.
"""
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_03_Ground_Combat.md")
COMBAT_CMD_PATH = os.path.join(PROJECT_ROOT, "parser", "combat_commands.py")
SIM_DROID_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars",
    "npcs_drop_f8c2b2_combat_templates.yaml")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


# ── 1. The live engine produces the actionable, token-echoing message ─────────
class TestEngineProducesActionableMessage:
    def test_ambiguous_attack_echoes_distinguishing_tokens(self):
        """`attack droid` vs the two sim droids -> the new token-echo message."""
        from engine.matching import MatchCandidate, MatchResult, match_one

        cands = [
            MatchCandidate(id=1, name="B1 Sim Droid Alpha", obj_type="npc"),
            MatchCandidate(id=2, name="B1 Sim Droid Bravo", obj_type="npc"),
        ]
        match = match_one("droid", cands)
        assert match.result == MatchResult.AMBIGUOUS, (
            "`droid` should match both sim droids ambiguously"
        )
        msg = match.error_message("droid")
        # The actionable phrasing the guide quotes.
        assert "Be more specific" in msg
        assert "try:" in msg
        # The distinguishing tokens, quoted, are what the player types.
        assert "'Alpha'" in msg and "'Bravo'" in msg
        # And it must NOT have regressed to the old listing-only format.
        assert "(matches:" not in msg

    def test_full_overlap_falls_back_to_full_name(self):
        """When names share every word, the token is the full name (documented
        fallback) — never an empty quote."""
        from engine.matching import MatchCandidate, match_one

        cands = [
            MatchCandidate(id=1, name="B1 Sim Droid", obj_type="npc"),
            MatchCandidate(id=2, name="B1 Sim Droid", obj_type="npc"),
        ]
        msg = match_one("droid", cands).error_message("droid")
        assert "B1 Sim Droid" in msg
        assert "''" not in msg, "fallback must not yield an empty token"


# ── 2. Producer -> consumer: combat actually surfaces error_message ───────────
def test_combat_command_surfaces_error_message_on_ambiguous():
    """parser/combat_commands.py must hand `error_message` to the player when an
    attack target is ambiguous — the guide claims 'the game tells you'."""
    src = _read(COMBAT_CMD_PATH)
    assert "MatchResult.AMBIGUOUS" in src
    assert "match.error_message(" in src, (
        "combat must call Match.error_message so the actionable prompt reaches "
        "the player; if this seam moved, re-verify Guide_03 §3"
    )


# ── 3. The worked example is grounded — the two sim droids exist ──────────────
def test_combat_sim_seeds_the_two_named_droids():
    src = _read(SIM_DROID_YAML)
    assert "B1 Sim Droid Alpha" in src
    assert "B1 Sim Droid Bravo" in src


# ── 4. The guide prose teaches the recovery and quotes the live message ───────
class TestGuideTeachesDisambiguation:
    def test_subsection_present(self, guide_text):
        assert "Picking a target when names collide" in guide_text

    def test_quotes_the_live_message_verbatim(self, guide_text):
        # The fenced example must match what the engine emits today.
        assert "Which one? Be more specific — try: 'Alpha', 'Bravo'." in guide_text

    def test_teaches_the_token_to_type(self, guide_text):
        # The player must learn that the quoted word is what they type.
        assert "`attack alpha`" in guide_text
        assert "shortest unique token" in guide_text

    def test_teaches_the_fallback(self, guide_text):
        # The full-name fallback for fully-overlapping names is documented.
        assert "share *every* word" in guide_text

    def test_reassures_not_a_dead_end(self, guide_text):
        # The fun-pass lesson: the prompt is a hand-up, not a wall.
        assert "not a dead end" in guide_text

    def test_no_stale_listing_only_phrasing(self, guide_text):
        # The guide must not present the retired listing-only message as THE
        # prompt (it would teach the player nothing about how to choose).
        assert not re.search(r"Which one\? \(matches:", guide_text)
