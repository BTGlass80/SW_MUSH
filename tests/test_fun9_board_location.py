# -*- coding: utf-8 -*-
"""
tests/test_fun9_board_location.py — FUN9 board location label.

6th fun re-run (major-drag): on KAMINO, the Mission Board, Bounty Board, and the
GNN news fallback all printed "-- Mos Eisley", contradicting the player's actual
location on their first screen. The boards are global (galaxy-wide content), so
the headers are now location-neutral and the GNN zone-less fallback reads
"the galaxy".
"""
from __future__ import annotations

import re


def _strip_ansi(s: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def test_mission_board_header_is_location_neutral():
    from engine.missions import format_board
    out = "\n".join(_strip_ansi(x) for x in format_board([]))
    assert "MISSION BOARD" in out
    assert "Mos Eisley" not in out, "mission board header still hardcodes Mos Eisley"


def test_bounty_board_header_is_location_neutral():
    from engine.bounty_board import format_bounty_board
    out = "\n".join(_strip_ansi(x) for x in format_bounty_board([]))
    assert "BOUNTY BOARD" in out
    assert "Mos Eisley" not in out, "bounty board header still hardcodes Mos Eisley"


def test_gnn_zoneless_fallback_not_mos_eisley():
    import engine.world_events as we
    import inspect
    src = inspect.getsource(we)
    assert 'else "Mos Eisley"' not in src, (
        "GNN zone-less location fallback still defaults to Mos Eisley")
