# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/economy_progression.py — Economy & progression (E1-E6).

Per design §6.7.

Coverage:
  E1: +shop (or shop list) renders without crashing
  E2: market list (commodities)
  E3: +cpstatus displays CP balance
  E4: +kudos awards CP
  E5: +scenebonus path
  E6: survey runs (already covered indirectly by test_economy_validation;
      added here for end-to-end smoke pairing)

E7 (full crafting roll loop) and E8 (experiment success/fail paths)
are deferred — they have rich state and depend on resource nodes that
require harness extensions (advance_ticks for cooldowns, resource
seeding for nodes).
"""
from __future__ import annotations

import asyncio


async def e1_shop_lists(h):
    """E1 — `+shop list` (or `shop`) shows shop-related output.

    The shop command's exact behavior depends on the player's
    location: in a shop room, lists wares; outside, lists nearby
    shops or shows an error. We assert non-error output.
    """
    s = await h.login_as("E1Shopper", room_id=1)
    # Try the most common forms — first one that produces output wins.
    for cmd in ("+shop list", "+shop", "shop"):
        out = await h.cmd(s, cmd)
        if out and out.strip():
            assert "traceback" not in out.lower(), (
                f"`{cmd}` raised: {out[:500]!r}"
            )
            return
    assert False, "No form of shop command produced output"


async def e2_market_lists(h):
    """E2 — `market` (or `market list`) shows commodity data.

    The market command lists available commodities at the current
    location's market or a default. Lightweight: just exercises the
    read path.
    """
    s = await h.login_as("E2Trader", room_id=1)
    out = await h.cmd(s, "market")
    assert out and out.strip(), "market produced no output"
    assert "traceback" not in out.lower(), (
        f"market raised: {out[:500]!r}"
    )


async def e3_cpstatus(h):
    """E3 — `+cpstatus` shows the character's CP balance.

    Validates the CP status display pipeline. Test characters have
    character_points=5 from the harness defaults.
    """
    s = await h.login_as("E3CPSee", room_id=1)
    out = await h.cmd(s, "+cpstatus")
    assert out and out.strip(), "+cpstatus produced no output"
    assert "traceback" not in out.lower(), (
        f"+cpstatus raised: {out[:500]!r}"
    )
    out_lc = out.lower()
    # The display should mention CP or character points.
    assert "cp" in out_lc or "character point" in out_lc, (
        f"+cpstatus output doesn't reference CP: {out[:400]!r}"
    )


async def e4_kudos_awards_cp(h):
    """E4 — `+kudos <player>` awards CP to another PC.

    Two PCs in the same room — Alice gives Bob a kudos. We don't
    assert exact CP delta because the kudos amount may vary by
    config; we assert the command runs and produces some output.
    """
    s_alice = await h.login_as("E4Giver", room_id=1)
    s_bob = await h.login_as("E4Receiver", room_id=1)
    out = await h.cmd(s_alice, "+kudos E4Receiver thank you for the great roleplay")
    assert "traceback" not in out.lower(), (
        f"+kudos raised: {out[:500]!r}"
    )
    # Some output should be present (success or rate-limit message).
    assert out and out.strip(), "+kudos produced no output"


async def e5_scenebonus_runs(h):
    """E5 — `+scenebonus` (admin/director command) runs without crash.

    For non-admin characters this typically refuses with a permissions
    message. We give an admin character so the path can run, but only
    assert that no traceback occurs — actual award semantics depend
    on scene-tracker state.
    """
    s = await h.login_as("E5Admin", room_id=1, is_admin=True)
    out = await h.cmd(s, "+scenebonus")
    assert "traceback" not in out.lower(), (
        f"+scenebonus raised: {out[:500]!r}"
    )
    assert out and out.strip(), "+scenebonus produced no output"


async def e6_survey_runs_with_skill(h):
    """E6 — `survey` runs without raising for a character with the
    search skill set.

    The harness's economy_validation.py already exercises survey for
    cooldown semantics (and surfaced the soft warning). This scenario
    just smokes the read path on a fresh character.

    Survey requires being in a wilderness/resource room; in spawn
    (Landing Pad) it may refuse with a "no resources here" message.
    Both refusal and success are acceptable — we just assert no
    traceback.
    """
    s = await h.login_as(
        "E6Surveyor", room_id=1,
        skills={"search": "3D"},
    )
    out = await h.cmd(s, "survey")
    assert "traceback" not in out.lower(), (
        f"survey raised: {out[:500]!r}"
    )
    # Some output: success, refusal, or "no resources here" — all fine.
    assert out and out.strip(), "survey produced no output"
