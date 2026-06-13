# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/threat_band.py — DIFF.2 runtime UI (drop 29).

Live-harness verification that the threat band surfaces in the `look`
room header (off-default bands only) and via the `+threat` / `threat`
command, resolving through the real zone-inheritance chain.
"""
from __future__ import annotations


async def tb_1_look_header_shows_frontier(h):
    """TB-1 — `look` in a Frontier zone (tipoca briefing room) shows the
    [FRONTIER] tag in the room header."""
    try:
        rid = await h.room_id_by_slug("tipoca_briefing_room")
    except LookupError:
        return  # not this world/era
    s = await h.login_as("TB1Look", room_id=rid)
    out = await h.cmd(s, "look")
    assert "traceback" not in out.lower(), f"look raised: {out[:300]!r}"
    assert "FRONTIER" in out, (
        f"TB-1: look header did not show the [FRONTIER] threat tag in a "
        f"Frontier zone. Output: {out[:400]!r}"
    )


async def tb_2_look_header_suppresses_settled(h):
    """TB-2 — `look` in a Settled zone (the default band) does NOT show a
    threat tag (the common case is kept quiet)."""
    try:
        rid = await h.room_id_by_slug("nar_shaddaa_bhg_chapter_house")
    except LookupError:
        return
    s = await h.login_as("TB2Look", room_id=rid)
    out = await h.cmd(s, "look")
    assert "[SETTLED]" not in out.upper(), (
        f"TB-2: look header should suppress the Settled (default) band "
        f"tag. Output: {out[:400]!r}"
    )


async def tb_3_threat_command_renders_band(h):
    """TB-3 — `+threat` (and the `threat` alias) renders the current
    band name + level + blurb without crashing."""
    try:
        rid = await h.room_id_by_slug("tipoca_briefing_room")
    except LookupError:
        return
    s = await h.login_as("TB3Threat", room_id=rid)
    out = await h.cmd(s, "+threat")
    out_lc = out.lower()
    assert "traceback" not in out_lc, f"+threat raised: {out[:300]!r}"
    assert "threat band" in out_lc, (
        f"TB-3: +threat did not render the band. Output: {out[:300]!r}"
    )
    assert "frontier" in out_lc, (
        f"TB-3: +threat did not name the Frontier band. Output: "
        f"{out[:300]!r}"
    )
    # The bare `threat` alias must work too.
    out2 = await h.cmd(s, "threat")
    assert "threat band" in out2.lower(), (
        f"TB-3: `threat` alias did not render. Output: {out2[:300]!r}"
    )
