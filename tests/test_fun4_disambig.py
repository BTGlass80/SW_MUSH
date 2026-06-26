"""
test_fun4_disambig.py — FUN tier-4 actionable disambiguation.

Typing the obvious "attack droid" against two B1 Sim Droids returned
"Which one? (matches: B1 Sim Droid Alpha, B1 Sim Droid Bravo)" with no hint on
HOW to choose — stranding newcomers one step from the combat payoff. The
disambiguation message now echoes the distinguishing TOKEN the parser accepts
('alpha' / 'bravo').
"""
from __future__ import annotations

from engine.matching import Match, MatchResult, MatchCandidate


def _ambig(*names):
    return Match(
        result=MatchResult.AMBIGUOUS,
        ambiguous_options=[MatchCandidate(id=i + 1, name=n)
                           for i, n in enumerate(names)],
    )


def test_message_shows_distinguishing_tokens():
    m = _ambig("B1 Sim Droid Alpha", "B1 Sim Droid Bravo")
    msg = m.error_message("droid")
    assert "Alpha" in msg and "Bravo" in msg
    assert "be more specific" in msg.lower()
    # the actionable tokens are quoted so the player knows what to type
    assert "'Alpha'" in msg and "'Bravo'" in msg
    # the old non-actionable phrasing is gone
    assert "(matches:" not in msg


def test_distinguishing_token_picks_unique_word():
    opts = [MatchCandidate(id=1, name="B1 Sim Droid Alpha"),
            MatchCandidate(id=2, name="B1 Sim Droid Bravo")]
    assert Match._distinguishing_token(opts[0], opts) == "Alpha"
    assert Match._distinguishing_token(opts[1], opts) == "Bravo"


def test_fully_overlapping_names_fall_back_to_full_name():
    opts = [MatchCandidate(id=1, name="Clone Trooper"),
            MatchCandidate(id=2, name="Clone Trooper")]
    # no unique word → fall back to the full name (still better than nothing)
    assert Match._distinguishing_token(opts[0], opts) == "Clone Trooper"


def test_not_found_message_unchanged():
    m = Match(result=MatchResult.NOT_FOUND)
    assert m.error_message("xyzzy") == "You don't see 'xyzzy' here."
