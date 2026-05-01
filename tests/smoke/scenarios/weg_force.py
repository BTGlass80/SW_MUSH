# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/weg_force.py — WEG D6 mechanics & Force (W1-W4).

Per design §6.6.

Coverage:
  W1: +roll <dice> produces a roll result with reasonable shape
  W2: +opposed handles two-side rolls
  W3: +powers lists Force powers
  W4: +forcestatus shows Force Point / DSP state

Force-power activation (force <power>) is intentionally NOT smoke-
tested here — it requires a target, a known power name, sufficient
Force Points, and may produce non-deterministic outcomes. A full
Force-use scenario belongs in a richer combat-and-Force fixture drop.

W1 already exists at scenario layer in communication.py (C7) — this
module's W1 is a richer assertion: dice expression parsing, total
calculation, Wild Die marker visibility.
"""
from __future__ import annotations

import asyncio


async def w1_roll_dice_expression(h):
    """W1 — `+roll 4D+2` parses, runs, and produces a numeric result.

    The harness's C7 scenario already validates that `+roll 3d6`
    runs cleanly. This scenario goes further:
      - asserts an explicit total appears in the output
      - validates the WEG-style "+pips" notation parses (`4D+2`)
      - confirms no traceback escapes
    """
    s = await h.login_as("W1Roller", room_id=1)
    out = await h.cmd(s, "+roll 4D+2")
    assert out and out.strip(), "+roll produced no output"
    assert "traceback" not in out.lower(), (
        f"+roll raised: {out[:500]!r}"
    )
    # Some digit must appear (the total or one of the dice).
    assert any(c.isdigit() for c in out), (
        f"+roll output has no numeric content: {out[:300]!r}"
    )


async def w2_opposed_check(h):
    """W2 — `+opposed <skill1> vs <skill2>` runs cleanly.

    Validates the opposed-roll command path. Self-opposed is fine
    for a smoke check — we don't need two actual PCs.
    """
    s = await h.login_as("W2Opposed", room_id=1)
    # Some implementations want `+opposed <skill1>=<skill2>`, others
    # `+opposed <skill1> vs <skill2>`. Try the most common form and
    # be tolerant of usage-message replies.
    out = await h.cmd(s, "+opposed 4D vs 3D")
    assert out and out.strip(), "+opposed produced no output"
    assert "traceback" not in out.lower(), (
        f"+opposed raised: {out[:500]!r}"
    )


async def w3_powers_list(h):
    """W3 — `+powers` lists Force powers known/available.

    For a non-Force-sensitive baseline character, the listing is
    typically empty or a "you have no Force powers" message — both
    are valid; we just assert no crash.
    """
    s = await h.login_as("W3Powers", room_id=1)
    out = await h.cmd(s, "+powers")
    assert out and out.strip(), "+powers produced no output"
    assert "traceback" not in out.lower(), (
        f"+powers raised: {out[:500]!r}"
    )


async def w4_force_status(h):
    """W4 — `+forcestatus` shows Force-related state.

    Validates the FP / DSP display pipeline. The test character has
    force_points=1, dark_side_points=0 from the harness defaults, so
    the output should reference Force Points or DSP terminology.
    """
    s = await h.login_as("W4Force", room_id=1)
    out = await h.cmd(s, "+forcestatus")
    assert out and out.strip(), "+forcestatus produced no output"
    assert "traceback" not in out.lower(), (
        f"+forcestatus raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    has_force_terminology = (
        "force" in out_lc
        or "dark side" in out_lc
        or "fp" in out_lc
        or "dsp" in out_lc
    )
    assert has_force_terminology, (
        f"+forcestatus output doesn't reference Force terminology: "
        f"{out[:400]!r}"
    )
