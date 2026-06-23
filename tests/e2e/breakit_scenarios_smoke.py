# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_scenarios_smoke.py — harness self-test + the SCENARIO TEMPLATE.

Doubles as (1) proof the break-it harness boots a server+browser, makes a player,
and captures browser-layer defects, and (2) the copy-me pattern for the break-it
Workflow agents: each writes `def s_<name>(sess): ...` driving `sess.page` /
`sess.send(...)` adversarially, then `run_scenarios("<surface>", [...])`.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_scenarios_smoke.py
Exit 0 = no browser-layer defect captured across the scenarios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


def s_new_player_baseline(sess):
    """Baseline: the happy path itself must produce ZERO browser-layer defects.
    If this records anything, the harness or the SPA's clean path is broken."""
    sess.new_player()
    sess.send("look")


def s_adversarial_command_input(sess):
    """Throw malformed / oversized / injection-shaped input at the command box.
    None of it should produce an uncaught JS exception, a console.error, or a 5xx."""
    sess.new_player()
    for junk in (
        "x" * 6000,                       # oversized
        ";;;@@@###|||",                   # punctuation soup
        "look \t\x07\x1b[31m",            # tab + bell + ANSI escape (control chars)
        "<script>alert(1)</script>",      # XSS-shaped
        "'; DROP TABLE characters;--",    # SQLi-shaped
        "say " + "\U0001f600" * 200,      # emoji flood
        "   ",                            # whitespace only
        "MOVE NORTHHHH",                  # bogus direction
    ):
        sess.send(junk, settle_ms=350)


def s_rapid_fire_commands(sess):
    """Fire commands with no settle to provoke client-side races / dropped frames
    / double-submit handlers."""
    sess.new_player()
    for _ in range(15):
        sess.send("look", settle_ms=0)
    sess.page.wait_for_timeout(1500)


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "harness-selftest",
        [s_new_player_baseline, s_adversarial_command_input, s_rapid_fire_commands],
    ))
