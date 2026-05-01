# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/missions_factions.py — Missions, bounties, factions, scenes (Q1-Q6).

Per design §6.8.

Coverage (read-only / list-mode where possible to stay portable):
  Q1: +missions lists available missions
  Q2: +bounties lists active bounties
  Q3: +faction list lists factions
  Q4: +reputation shows player reputation state
  Q5: +scenes lists active scenes
  Q6: +plots lists active plots

Q7 (encounter trigger + investigate) is deferred — it requires
ambient encounter spawning which is non-deterministic and benefits
from the same advance_ticks(n) helper SH4-B will introduce.
"""
from __future__ import annotations


async def q1_missions_list(h):
    """Q1 — `+missions` lists available missions.

    For a fresh character with no active missions, the listing is
    typically empty or a "no missions available" message. Both are
    valid; we assert no traceback.
    """
    s = await h.login_as("Q1Mission", room_id=1)
    out = await h.cmd(s, "+missions")
    assert out and out.strip(), "+missions produced no output"
    assert "traceback" not in out.lower(), (
        f"+missions raised: {out[:500]!r}"
    )


async def q2_bounties_list(h):
    """Q2 — `+bounties` lists active bounties.

    Read-only: just exercises the bounty board display.
    """
    s = await h.login_as("Q2Bounty", room_id=1)
    out = await h.cmd(s, "+bounties")
    assert out and out.strip(), "+bounties produced no output"
    assert "traceback" not in out.lower(), (
        f"+bounties raised: {out[:500]!r}"
    )


async def q3_faction_list(h):
    """Q3 — `+faction list` lists factions.

    A fresh character is not in any faction by default. The list
    output should still render (it's a global registry, not a
    per-player list).
    """
    s = await h.login_as("Q3Faction", room_id=1)
    out = await h.cmd(s, "+faction list")
    assert out and out.strip(), "+faction list produced no output"
    assert "traceback" not in out.lower(), (
        f"+faction list raised: {out[:500]!r}"
    )
    # A populated faction registry should mention at least one of the
    # well-known GCW-era factions. Be tolerant of formatting.
    out_lc = out.lower()
    has_known_faction = (
        "rebel" in out_lc
        or "imperial" in out_lc
        or "hutt" in out_lc
        or "alliance" in out_lc
        or "empire" in out_lc
        # Or just generic faction headers / count
        or "faction" in out_lc
    )
    assert has_known_faction, (
        f"+faction list output doesn't reference any expected GCW "
        f"faction or faction terminology: {out[:500]!r}"
    )


async def q4_reputation(h):
    """Q4 — `+reputation` shows the player's reputation state.

    For a fresh character, all reputation should be 0 / Neutral. We
    assert the command runs and produces output.
    """
    s = await h.login_as("Q4Rep", room_id=1)
    out = await h.cmd(s, "+reputation")
    assert out and out.strip(), "+reputation produced no output"
    assert "traceback" not in out.lower(), (
        f"+reputation raised: {out[:500]!r}"
    )


async def q5_scenes_list(h):
    """Q5 — `+scenes` lists active scenes."""
    s = await h.login_as("Q5Scene", room_id=1)
    out = await h.cmd(s, "+scenes")
    assert out and out.strip(), "+scenes produced no output"
    assert "traceback" not in out.lower(), (
        f"+scenes raised: {out[:500]!r}"
    )


async def q6_plots_list(h):
    """Q6 — `+plots` lists active plots."""
    s = await h.login_as("Q6Plot", room_id=1)
    out = await h.cmd(s, "+plots")
    assert out and out.strip(), "+plots produced no output"
    assert "traceback" not in out.lower(), (
        f"+plots raised: {out[:500]!r}"
    )
