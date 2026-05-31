# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/padawan_master_trials.py — P-M.3 end-to-end
(May 20 2026).

PM3-1, PM3-2, PM3-3, PM3-4: live in-process verification of the
Trials + Knight promotion surface. Unit-level coverage is in
tests/test_pm3_trials_and_knight.py (33 tests). These scenarios
exercise the same code through the live harness to catch wiring
regressions.

Scenarios
=========

* **PM3-1** — Happy path. Bond via +bond/accept, record all 5
              Trials via +trial, +knight promotes. Padawan gets
              the Force-Point grant + narrative cue.
* **PM3-2** — Hard gate. With only 4 Trials recorded, +knight
              refuses with a listing of the missing Trial.
* **PM3-3** — Staff override. @knight promotes a Padawan with
              zero Trials recorded (Council fiat path).
* **PM3-4** — Endorsement write surface. +endorse trials writes
              the chargen_notes flag; +trial consumes it.
"""
from __future__ import annotations

import asyncio
import json


# ──────────────────────────────────────────────────────────────────────────
# PM3-1 — bond → all 5 Trials → knight (happy path)
# ──────────────────────────────────────────────────────────────────────────


async def pm3_1_full_promotion_happy_path(h):
    """PM3-1 — End-to-end: bond via player flow, Master records all 5
    Trials via +trial, then +knight promotes. Verify:
      (a) bond.bond_status flips to 'knighted'
      (b) Padawan gets +1 Force Point
      (c) Padawan sees the ceremony line in their session
    """
    master = await h.login_as("PM31Master", room_id=1)
    padawan = await h.login_as("PM31Padawan", room_id=1)

    # Capture starting FP for the Padawan so the post-knight
    # check is robust to whatever test_character.yaml seeds.
    p_pre = await h.db.get_character(padawan.character["id"])
    fp_pre = int(p_pre.get("force_points") or 0)

    # Bond via player flow.
    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(padawan, f"+bond accept {master.character['name']}")

    bond = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    assert bond is not None, "PM3-1 setup: bond not established"
    bond_id = bond["id"]

    # Record all 5 trials.
    for trial in ("skill", "courage", "flesh", "spirit", "insight"):
        out = await h.cmd(
            master, f"+trial {trial} {padawan.character['name']}"
        )
        assert "traceback" not in out.lower(), (
            f"+trial {trial} raised: {out[:300]!r}"
        )

    bond_pre = await h.db.get_bond(bond_id)
    passed = json.loads(bond_pre["trials_passed_json"])
    assert len(passed) == 5, (
        f"PM3-1: expected 5 Trials, got {len(passed)}: {passed!r}"
    )

    # Drain Padawan so we can see the ceremony notification cleanly.
    padawan.drain_text()

    # Promote.
    out = await h.cmd(
        master, f"+knight {padawan.character['name']}"
    )
    assert "traceback" not in out.lower(), (
        f"+knight raised: {out[:500]!r}"
    )
    assert "Knight PM31Padawan" in out, (
        f"+knight should render 'Knight <name>': {out[:400]!r}"
    )

    bond_post = await h.db.get_bond(bond_id)
    assert bond_post["bond_status"] == "knighted", (
        f"bond_status should be 'knighted'; got "
        f"{bond_post['bond_status']!r}"
    )
    assert bond_post.get("knight_promotion_at"), (
        "knight_promotion_at should be set"
    )

    # Padawan Force Point grant (+1).
    p_reloaded = await h.db.get_character(padawan.character["id"])
    fp_post = int(p_reloaded.get("force_points") or 0)
    assert fp_post == fp_pre + 1, (
        f"Padawan should have +1 Force Point after knighting; "
        f"pre={fp_pre} post={fp_post}"
    )

    # Padawan-side notification.
    await asyncio.sleep(0.1)
    padawan_buf = padawan.drain_text()
    assert "Rise, Knight" in padawan_buf, (
        f"Padawan should have received ceremony line; "
        f"buffer: {padawan_buf[:500]!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PM3-2 — hard gate: 4 trials, +knight refused
# ──────────────────────────────────────────────────────────────────────────


async def pm3_2_knight_hard_gate(h):
    """PM3-2 — With only 4 Trials recorded, +knight refuses
    and names the missing Trial."""
    master = await h.login_as("PM32Master", room_id=1)
    padawan = await h.login_as("PM32Padawan", room_id=1)

    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(padawan, f"+bond accept {master.character['name']}")

    # Record 4 of 5.
    for trial in ("skill", "courage", "flesh", "spirit"):
        await h.cmd(
            master, f"+trial {trial} {padawan.character['name']}"
        )

    out = await h.cmd(
        master, f"+knight {padawan.character['name']}"
    )
    assert "traceback" not in out.lower()
    assert "4/5" in out, (
        f"+knight should show count 4/5: {out[:400]!r}"
    )
    assert "Insight" in out, (
        f"+knight should name missing Trial: {out[:400]!r}"
    )

    # Bond NOT promoted.
    bond = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    assert bond is not None and bond["bond_status"] == "active", (
        f"Bond should still be active; got "
        f"{bond and bond['bond_status']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PM3-3 — @knight override
# ──────────────────────────────────────────────────────────────────────────


async def pm3_3_admin_knight_override(h):
    """PM3-3 — Staff @knight promotes with zero Trials recorded
    (Council-fiat path)."""
    master = await h.login_as("PM33Master", room_id=1)
    padawan = await h.login_as("PM33Padawan", room_id=1)
    staff = await h.login_as("PM33Staff", room_id=1, is_admin=True)

    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(padawan, f"+bond accept {master.character['name']}")

    bond = await h.db.get_active_bond_for_padawan(
        padawan.character["id"]
    )
    bond_id = bond["id"]
    # NO trials recorded.

    out = await h.cmd(
        staff, f"@knight {padawan.character['name']}"
    )
    assert "traceback" not in out.lower(), (
        f"@knight raised: {out[:500]!r}"
    )
    bond_post = await h.db.get_bond(bond_id)
    assert bond_post["bond_status"] == "knighted", (
        f"@knight should override gate and promote; "
        f"status={bond_post['bond_status']!r}"
    )


# ──────────────────────────────────────────────────────────────────────────
# PM3-4 — endorsement flag round-trip
# ──────────────────────────────────────────────────────────────────────────


async def pm3_4_endorsement_consumed_on_trial_record(h):
    """PM3-4 — +endorse trials sets the flag; +trial consumes it.

    Verifies the endorsement seam is wired correctly. Per design
    §6.3, Master endorsement is required for Trial attempts;
    the runtime gate (where the Padawan's attempt reads this
    flag) is content/future-drop concern, but the write surface
    must work today.
    """
    master = await h.login_as("PM34Master", room_id=1)
    padawan = await h.login_as("PM34Padawan", room_id=1)

    await h.cmd(master, f"+bond {padawan.character['name']}")
    await asyncio.sleep(0.1)
    await h.cmd(padawan, f"+bond accept {master.character['name']}")

    # Endorse.
    out = await h.cmd(
        master, f"+endorse trials {padawan.character['name']}"
    )
    assert "traceback" not in out.lower()
    p_after_endorse = await h.db.get_character(padawan.character["id"])
    notes = json.loads(p_after_endorse.get("chargen_notes") or "{}")
    assert notes.get("trial_endorsement_active"), (
        f"Endorsement flag should be set: {notes!r}"
    )

    # Record a Trial — endorsement should be consumed.
    await h.cmd(master, f"+trial skill {padawan.character['name']}")
    p_after_trial = await h.db.get_character(padawan.character["id"])
    notes_after = json.loads(
        p_after_trial.get("chargen_notes") or "{}"
    )
    assert not notes_after.get("trial_endorsement_active"), (
        f"Endorsement should be consumed; notes after: {notes_after!r}"
    )
