# -*- coding: utf-8 -*-
"""NPE (2026-06-20): the first-run interface tour fires PER CHARACTER, not
once-per-browser, and points at the in-game GUIDES button.

Brian's playtest: "we had a more robust onboarding that walked the player
through the UI — I didn't see it this time." The tour existed but was gated by a
single global localStorage flag (m3_onboard_tour_done), so a returning player
(or a dev cycling test characters) never saw it again. Fixed: the gate is now
keyed by character id (each new character gets the tour once), and a new
coach-mark teaches the GUIDES button (the in-game help browser).
"""
from __future__ import annotations

import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT = os.path.join(REPO, "static", "client.html")


def _src() -> str:
    with open(CLIENT, encoding="utf-8") as f:
        return f.read()


def test_tour_gate_is_keyed_per_character():
    s = _src()
    assert "function _tourKey()" in s, "tour must key its seen-flag per character"
    assert "lastHud.character_id" in s, "the tour key must derive from the character id"
    # The end-of-tour write must use the per-character key, not the bare global.
    assert "localStorage.setItem(_tourKey(), '1')" in s, (
        "endOnboardTour must persist the per-character key"
    )
    assert "localStorage.setItem(ONBOARD_TOUR_KEY, '1')" not in s, (
        "the once-per-browser global write must be gone"
    )


def test_tour_teaches_the_in_game_guides_button():
    s = _src()
    assert "'.guide-qa-btn'" in s, (
        "the tour must include a coach-mark for the in-game GUIDES button"
    )
