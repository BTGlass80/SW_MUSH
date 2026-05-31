# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/pc_bounty.py — PG.2.bounty session 1
end-to-end (May 20 2026).

BTY-1, BTY-2, BTY-3, BTY-4: live in-process verification of the
PC bounty player surface. Unit-level coverage in
tests/test_pg2_pc_bounty_session1.py (39 tests).

Scenarios
=========

* **BTY-1** — Happy path: +pcbounty post debits credits, creates
              the bounty row, sends mail to the target.
* **BTY-2** — Stacking: second poster on the same target merges
              escrow; primary stays the original poster.
* **BTY-3** — Cancel + proportional refunds: primary cancels;
              both contributors get proportional 75% refunds.
* **BTY-4** — Cooldown blocks repost: after cancel, the same
              poster cannot re-post against the same target.
"""
from __future__ import annotations

import asyncio
import json


# ──────────────────────────────────────────────────────────────────────────
# BTY-1 — happy path post
# ──────────────────────────────────────────────────────────────────────────


async def bty_1_post_happy_path(h):
    """BTY-1 — +pcbounty post Greedo 10000 he shot first.

    Verifies: bounty row created with state='active'; poster's
    credits debited by amount + 10% fee; target receives a mail
    notification.
    """
    solo = await h.login_as(
        "BTY1Solo", room_id=1, credits=100000,
    )
    greedo = await h.login_as(
        "BTY1Greedo", room_id=1, credits=100000,
    )

    out = await h.cmd(
        solo, "+pcbounty post BTY1Greedo 10000 he shot first"
    )
    assert "traceback" not in out.lower(), (
        f"+pcbounty post raised: {out[:500]!r}"
    )
    assert "Bounty posted" in out, (
        f"+pcbounty post should confirm: {out[:400]!r}"
    )

    # Bounty exists.
    bounty = await h.db.get_active_incoming_for_target(
        greedo.character["id"]
    )
    assert bounty is not None, "Bounty row not created"
    assert bounty["amount"] == 10000, (
        f"Expected amount 10000, got {bounty['amount']}"
    )
    assert bounty["state"] == "active"

    # Poster credits debited: 10000 + 1000 fee = 11000.
    solo_reloaded = await h.db.get_character(solo.character["id"])
    assert int(solo_reloaded["credits"]) == 100000 - 11000, (
        f"Expected credits 89000, got {solo_reloaded['credits']}"
    )

    # Mail delivered.
    mail_rows = await h.db._db.execute_fetchall(
        "SELECT m.subject FROM mail m "
        "INNER JOIN mail_recipients r ON r.mail_id = m.id "
        "WHERE r.char_id = ?",
        (greedo.character["id"],),
    )
    assert len(mail_rows) >= 1, (
        f"Target should have received a mail; got {len(mail_rows)}"
    )
    subjects = [r["subject"] for r in mail_rows]
    assert any("BOUNTY" in s for s in subjects), (
        f"Mail subject should mention BOUNTY: {subjects!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# BTY-2 — stacking
# ──────────────────────────────────────────────────────────────────────────


async def bty_2_stack_merges_escrow(h):
    """BTY-2 — Two posters on the same target. First post creates
    a new bounty; second post stacks onto it. Verify the
    contributors_json sidecar has both entries and the primary
    is the original poster."""
    p1 = await h.login_as(
        "BTY2P1", room_id=1, credits=100000,
    )
    p2 = await h.login_as(
        "BTY2P2", room_id=1, credits=100000,
    )
    target = await h.login_as(
        "BTY2Target", room_id=1, credits=100000,
    )

    await h.cmd(p1, "+pcbounty post BTY2Target 5000 first")
    out2 = await h.cmd(p2, "+pcbounty post BTY2Target 3000 stacking")
    assert "traceback" not in out2.lower()
    assert "stacked" in out2.lower(), (
        f"Second post should stack: {out2[:400]!r}"
    )

    bounty = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    assert bounty["amount"] == 8000, (
        f"Stacked total should be 8000; got {bounty['amount']}"
    )
    # Primary is still P1.
    assert bounty["poster_id"] == p1.character["id"], (
        f"Primary should remain P1; got poster_id={bounty['poster_id']}"
    )
    contributors = json.loads(bounty["contributors_json"])
    assert len(contributors) == 2, (
        f"Sidecar should have 2 contributors; got {len(contributors)}"
    )


# ──────────────────────────────────────────────────────────────────────────
# BTY-3 — cancel + proportional refunds
# ──────────────────────────────────────────────────────────────────────────


async def bty_3_cancel_proportional_refunds(h):
    """BTY-3 — Primary cancels a stacked bounty. Both contributors
    get their proportional 75% refunds. The 25% cancel fee is sunk."""
    p1 = await h.login_as(
        "BTY3P1", room_id=1, credits=100000,
    )
    p2 = await h.login_as(
        "BTY3P2", room_id=1, credits=100000,
    )
    target = await h.login_as(
        "BTY3Target", room_id=1, credits=100000,
    )

    # P1 posts 10000 (pays 11000; remaining 89000)
    await h.cmd(p1, "+pcbounty post BTY3Target 10000 r1")
    # P2 stacks 5000 (pays 5500; remaining 94500)
    await h.cmd(p2, "+pcbounty post BTY3Target 5000 r2")

    p1_pre = await h.db.get_character(p1.character["id"])
    p2_pre = await h.db.get_character(p2.character["id"])
    assert int(p1_pre["credits"]) == 89000, (
        f"P1 pre-cancel: expected 89000, got {p1_pre['credits']}"
    )
    assert int(p2_pre["credits"]) == 94500, (
        f"P2 pre-cancel: expected 94500, got {p2_pre['credits']}"
    )

    # P1 cancels.
    out = await h.cmd(p1, "+pcbounty cancel")
    assert "traceback" not in out.lower(), (
        f"+pcbounty cancel raised: {out[:500]!r}"
    )

    # Refund math: total escrow 15000; refund pool 11250 (75%).
    # P1 gets 7500 (primary absorbs rounding); P2 gets 3750.
    p1_post = await h.db.get_character(p1.character["id"])
    p2_post = await h.db.get_character(p2.character["id"])
    assert int(p1_post["credits"]) == 89000 + 7500, (
        f"P1 expected 96500, got {p1_post['credits']}"
    )
    assert int(p2_post["credits"]) == 94500 + 3750, (
        f"P2 expected 98250, got {p2_post['credits']}"
    )

    # Bounty is canceled.
    bounty = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    assert bounty is None, (
        "Bounty should no longer be active after cancel"
    )


# ──────────────────────────────────────────────────────────────────────────
# BTY-4 — cooldown enforced
# ──────────────────────────────────────────────────────────────────────────


async def bty_4_cancel_sets_cooldown(h):
    """BTY-4 — After canceling a bounty, the same poster cannot
    re-post against the same target until the 30-day cooldown
    expires."""
    p = await h.login_as(
        "BTY4P", room_id=1, credits=100000,
    )
    target = await h.login_as(
        "BTY4Target", room_id=1, credits=100000,
    )

    await h.cmd(p, "+pcbounty post BTY4Target 5000 r1")
    await h.cmd(p, "+pcbounty cancel")

    # Attempt repost — should be blocked by cooldown.
    out = await h.cmd(p, "+pcbounty post BTY4Target 5000 r2")
    assert "traceback" not in out.lower()
    assert "cooldown" in out.lower(), (
        f"Repost should be blocked by cooldown: {out[:400]!r}"
    )

    # Target should not have an incoming bounty.
    bounty = await h.db.get_active_incoming_for_target(
        target.character["id"]
    )
    assert bounty is None, (
        "Cooldown-blocked repost should not create a bounty"
    )
