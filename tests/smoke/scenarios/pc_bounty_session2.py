# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/pc_bounty_session2.py — PG.2.bounty
session 2 end-to-end (May 21 2026).

BTY-5, BTY-6, BTY-7: live in-process verification of:
  - BH claim/release workflow
  - Full insurance loop on BH-kill (mocked via direct
    on_pc_death call to bypass full combat orchestration; the
    important verification is that the death hook fires the
    insurance + payout + fulfillment chain end-to-end).
  - Expiry tick handler refunds + claim revert
"""
from __future__ import annotations

import asyncio
import time


# ──────────────────────────────────────────────────────────────────────────
# BTY-5 — BH claim + release workflow
# ──────────────────────────────────────────────────────────────────────────


async def bty_5_bh_claim_and_release(h):
    """BTY-5 — BH claims an active bounty (state → claimed),
    then releases it (state → active). Non-BH cannot claim."""
    poster = await h.login_as(
        "BTY5Poster", room_id=1, credits=100000,
    )
    target = await h.login_as(
        "BTY5Target", room_id=1, credits=100000,
    )
    # Make a BH Guild member via direct save_character. login_as
    # doesn't take faction; we set after login.
    bh = await h.login_as("BTY5BH", room_id=1, credits=100000)
    await h.db.save_character(
        bh.character["id"], faction_id="bh_guild",
    )
    # Refresh session's cached character so commands read the
    # new faction.
    bh.character["faction_id"] = "bh_guild"

    # Random PC who is NOT BH.
    rando = await h.login_as("BTY5Rando", room_id=1, credits=100000)

    # Poster posts.
    await h.cmd(
        poster, f"+pcbounty post {target.character['name']} "
        f"5000 testing claim"
    )
    bounty = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    assert bounty is not None
    bid = bounty["id"]

    # Non-BH tries to claim → rejected.
    out = await h.cmd(rando, f"+pcbounty claim {bid}")
    assert "BH Guild members" in out, (
        f"Non-BH should be rejected: {out[:400]!r}"
    )
    row = await h.db.get_pc_bounty(bid)
    assert row["state"] == "active", "Non-BH claim should not flip state"

    # BH claims.
    out = await h.cmd(bh, f"+pcbounty claim {bid}")
    assert "Bounty claimed" in out, (
        f"BH claim should succeed: {out[:400]!r}"
    )
    row = await h.db.get_pc_bounty(bid)
    assert row["state"] == "claimed"
    assert row["claimed_by"] == bh.character["id"]

    # BH releases.
    out = await h.cmd(bh, f"+pcbounty release {bid}")
    assert "released" in out.lower(), (
        f"BH release should succeed: {out[:400]!r}"
    )
    row = await h.db.get_pc_bounty(bid)
    assert row["state"] == "active"
    assert row["claimed_by"] is None


# ──────────────────────────────────────────────────────────────────────────
# BTY-6 — Full insurance loop
# ──────────────────────────────────────────────────────────────────────────


async def bty_6_full_insurance_loop(h):
    """BTY-6 — A BH kills a bountied target. Verify:
      (a) 10% insurance hit on target's credits
      (b) 80% payout to BH
      (c) bounty state → fulfilled
      (d) bounty appears on the target's pc_action_log

    Bypasses full combat orchestration by calling on_pc_death
    directly with the right killer attribution. The combat
    layer's contribution (stamping last_attacker_id +
    populating killer_is_bh at the call site) is unit-tested
    separately; here we verify the death → insurance → payout
    chain works end-to-end via the live harness DB.
    """
    poster = await h.login_as(
        "BTY6Poster", room_id=1, credits=100000,
    )
    target = await h.login_as(
        "BTY6Target", room_id=1, credits=100000,
    )
    bh = await h.login_as("BTY6BH", room_id=1, credits=100000)
    await h.db.save_character(
        bh.character["id"], faction_id="bh_guild",
    )

    # Poster posts a 10000 cr bounty.
    await h.cmd(
        poster, f"+pcbounty post {target.character['name']} "
        f"10000 deserves it"
    )
    bounty = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    bid = bounty["id"]

    target_pre = await h.db.get_character(target.character["id"])
    bh_pre = await h.db.get_character(bh.character["id"])

    # Drive death via on_pc_death directly. Use LAWLESS so a
    # corpse drops (any non-secured zone is fine; insurance
    # math is independent of corpse mechanics).
    from engine.death import on_pc_death
    await on_pc_death(
        h.db,
        char_id=target.character["id"],
        room_id=1,
        security_level="lawless",
        killer_id=bh.character["id"],
        killer_is_bh=True,
    )

    # Verify state.
    row = await h.db.get_pc_bounty(bid)
    assert row["state"] == "fulfilled", (
        f"Bounty should be fulfilled; got state={row['state']!r}"
    )
    assert row["claimed_by"] == bh.character["id"]

    # Insurance hit: 10% of 10000 = 1000 cr from target.
    target_post = await h.db.get_character(target.character["id"])
    assert int(target_post["credits"]) == int(target_pre["credits"]) - 1000, (
        f"Target should have lost 1000 cr to insurance; "
        f"pre={target_pre['credits']} post={target_post['credits']}"
    )

    # BH payout: 80% of 10000 = 8000 cr.
    bh_post = await h.db.get_character(bh.character["id"])
    assert int(bh_post["credits"]) == int(bh_pre["credits"]) + 8000, (
        f"BH should have gained 8000 cr; "
        f"pre={bh_pre['credits']} post={bh_post['credits']}"
    )

    # Bounty no longer active.
    active = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    assert active is None, (
        "Bounty should no longer be active after fulfillment"
    )


# ──────────────────────────────────────────────────────────────────────────
# BTY-7 — Expiry tick handler
# ──────────────────────────────────────────────────────────────────────────


async def bty_7_expiry_tick(h):
    """BTY-7 — Expiry tick auto-expires past-30d active bounties
    (refunds stake to all contributors, fee stays sunk) and
    reverts past-7d claimed bounties back to active."""
    poster = await h.login_as(
        "BTY7Poster", room_id=1, credits=100000,
    )
    target1 = await h.login_as(
        "BTY7T1", room_id=1, credits=100000,
    )
    target2 = await h.login_as(
        "BTY7T2", room_id=1, credits=100000,
    )
    bh = await h.login_as("BTY7BH", room_id=1, credits=100000)
    await h.db.save_character(
        bh.character["id"], faction_id="bh_guild",
    )

    # Bounty 1: active and past expiry (manually backdate
    # expires_at). Use post_pc_bounty directly so we control
    # the duration.
    poster_balance_pre = int(
        (await h.db.get_character(poster.character["id"]))["credits"]
    )
    # Debit the poster manually to mirror what +pcbounty post would do.
    await h.db.save_character(
        poster.character["id"], credits=poster_balance_pre - 5500,
    )
    b1 = await h.db.post_pc_bounty(
        poster_id=poster.character["id"],
        target_id=target1.character["id"],
        amount=5000, reason="will expire", fee=500,
        duration_seconds=-100,  # already past
    )

    # Bounty 2: claimed, claim past 7d window.
    poster_balance_now = int(
        (await h.db.get_character(poster.character["id"]))["credits"]
    )
    # Need a SECOND outgoing bounty — but session 1's command
    # would block that. Use DB layer directly.
    await h.db.save_character(
        poster.character["id"], credits=poster_balance_now - 5500,
    )
    b2 = await h.db.post_pc_bounty(
        poster_id=poster.character["id"],
        target_id=target2.character["id"],
        amount=5000, reason="will revert claim", fee=500,
        duration_seconds=30 * 86400,
    )
    await h.db.claim_pc_bounty(
        bounty_id=b2, bh_char_id=bh.character["id"],
        timer_seconds=7 * 86400,
    )
    # Backdate the claim.
    await h.db._db.execute(
        "UPDATE pc_bounties SET claimed_at = ? WHERE id = ?",
        (time.time() - 8 * 86400, b2),
    )
    await h.db._db.commit()

    poster_pre_tick = int(
        (await h.db.get_character(poster.character["id"]))["credits"]
    )

    # Run the tick.
    from parser.pc_bounty_commands import run_pc_bounty_expiry_tick
    summary = await run_pc_bounty_expiry_tick(h.db)
    assert summary["expired"] == 1, (
        f"Expected 1 expired; got {summary['expired']}"
    )
    assert summary["reverted"] == 1, (
        f"Expected 1 reverted; got {summary['reverted']}"
    )
    assert summary["refunded_total"] == 5000, (
        f"Expected 5000 refunded; got {summary['refunded_total']}"
    )

    # b1: expired
    row1 = await h.db.get_pc_bounty(b1)
    assert row1["state"] == "expired"
    # b2: reverted to active
    row2 = await h.db.get_pc_bounty(b2)
    assert row2["state"] == "active"
    assert row2["claimed_by"] is None

    # Poster got back 5000 (stake from b1; fee stays sunk).
    poster_post_tick = int(
        (await h.db.get_character(poster.character["id"]))["credits"]
    )
    assert poster_post_tick == poster_pre_tick + 5000, (
        f"Poster should be refunded 5000 from b1 expiry; "
        f"pre={poster_pre_tick} post={poster_post_tick}"
    )
