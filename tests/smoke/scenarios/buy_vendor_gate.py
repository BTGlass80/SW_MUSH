# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/buy_vendor_gate.py — Open-market buy gate (BVG1–BVG3).

Drops 10-11 "market segmentation" + "vendor-presence" gate:

  BVG1 — REFUSAL arm: bare `buy <vendor_stocked weapon>` in a room with
          NO vendor NPC returns the "No merchant here sells weapons. Find
          a shop." refusal and credits are UNCHANGED.

  BVG2 — SUCCESS arm: with a flagged vendor NPC (ai_config vendor:true)
          seeded into the room, `buy blaster pistol` succeeds, credits
          DECREASE by at most the weapon's book cost (haggle can only
          reduce, not increase for a buyer without Bargain skill), and
          the success message "Purchased and equipped" appears in output.

  BVG3 — STOCK GATE arm: with the vendor NPC still present, `buy
          disruptor pistol` (no vendor_stocked flag) returns the
          not-stocked redirect ("No open vendor stocks") and credits are
          UNCHANGED.

Scenario ordering within the class-scoped harness matters:
  BVG1 → no NPC in room 100 yet (asserts refusal)
  BVG2 → seeds vendor NPC into room 100, then buys (asserts success)
  BVG3 → vendor NPC still in room 100, buys contraband (asserts refusal)

Room 100 is used as an isolated test room.  The harness world-build
always seeds at least rooms 1-20; we insert the NPC row directly and
the buy command reads npcs by room_id, so the room row itself need not
pre-exist for the NPC scan (the scan is a pure DB fetch on npcs.room_id).

Weapon constants (data/weapons.yaml):
  blaster_pistol   — vendor_stocked: true,  cost: 500   (Avail-1 common)
  disruptor_pistol — no vendor_stocked flag, cost: 3000  (contraband band)
"""
from __future__ import annotations

import json

# ── constants ────────────────────────────────────────────────────────────────

_VENDOR_ROOM = 100          # isolated room; no other scenario uses it
_VENDOR_NAME = "BVG Smoke Arms Dealer"
_STOCKED_WEAPON_CMD = "blaster pistol"   # matches find_by_name prefix search
_STOCKED_WEAPON_COST = 500               # book cost; haggle may reduce
_CONTRABAND_WEAPON_CMD = "disruptor pistol"


# ── helper ───────────────────────────────────────────────────────────────────

async def _seed_vendor_npc(h) -> int:
    """Insert a vendor-flagged NPC into _VENDOR_ROOM. Returns NPC id.

    Uses the idempotent create_npc (returns existing id if name+room
    already exists) so repeated calls within one harness session are safe.
    """
    npc_id = await h.db.create_npc(
        name=_VENDOR_NAME,
        room_id=_VENDOR_ROOM,
        species="Human",
        description="A licensed arms dealer for smoke-test purposes.",
        char_sheet_json=json.dumps({"skills": {"bargain": "3D"}}),
        ai_config_json=json.dumps({"vendor": True}),
    )
    return npc_id


# ── scenarios ────────────────────────────────────────────────────────────────

async def bvg1_refusal_no_vendor(h):
    """BVG1 — `buy <vendor_stocked weapon>` refuses when no vendor is present.

    Asserts:
      - Output contains the "No merchant here sells weapons. Find a shop."
        refusal string (case-insensitive).
      - Credits are unchanged after the refused buy.
      - No traceback / error-occurred in output.
    """
    # Confirm no vendor NPC in _VENDOR_ROOM at start of this scenario.
    # (Relies on BVG1 running before BVG2 seeds the NPC — pytest runs
    # class methods in definition order.)
    existing = await h.db.fetchall(
        "SELECT id FROM npcs WHERE room_id = ? AND name = ?",
        (_VENDOR_ROOM, _VENDOR_NAME),
    )
    assert not existing, (
        "BVG1 pre-condition: vendor NPC must NOT be in room yet; "
        f"found {existing!r}. If scenarios ran out of order, check test class ordering."
    )

    credits_start = 2000
    s = await h.login_as(
        "BVG1NoVendor",
        room_id=_VENDOR_ROOM,
        credits=credits_start,
    )
    char_id = s.character["id"]

    out = await h.cmd(s, f"buy {_STOCKED_WEAPON_CMD}")
    low = out.lower()

    # No crash.
    assert "traceback" not in low, f"BVG1: traceback in output: {out[:600]!r}"
    assert "error occurred" not in low, f"BVG1: error in output: {out[:600]!r}"

    # The specific refusal message from space_commands.py BuyCommand.execute().
    assert "no merchant" in low or "find a shop" in low, (
        f"BVG1: expected 'no merchant'/'find a shop' refusal; got: {out[:400]!r}"
    )

    # Credits must be unchanged — the refused buy must not deduct anything.
    credits_after = await h.get_credits(char_id)
    assert credits_after == credits_start, (
        f"BVG1: credits changed on refused buy! "
        f"before={credits_start}, after={credits_after}"
    )


async def bvg2_success_with_vendor(h):
    """BVG2 — `buy blaster pistol` succeeds when a vendor NPC is present.

    Seeds a vendor NPC (ai_config vendor:true) into _VENDOR_ROOM, then
    buys a blaster pistol.

    Asserts:
      - Output contains "Purchased and equipped" (the BuyCommand success
        message from space_commands.py line ~4222).
      - Credits DECREASED by at least 1 cr (haggle can give a discount
        but never makes the weapon free when the player has no Bargain).
      - Credits DECREASED by at most _STOCKED_WEAPON_COST (book price;
        a no-skill player can't negotiate a worse price than book under
        the resolve_bargain_check implementation).
      - No traceback / error-occurred in output.
    """
    await _seed_vendor_npc(h)

    credits_start = 5000
    s = await h.login_as(
        "BVG2Buyer",
        room_id=_VENDOR_ROOM,
        credits=credits_start,
    )
    char_id = s.character["id"]

    out = await h.cmd(s, f"buy {_STOCKED_WEAPON_CMD}")
    low = out.lower()

    # No crash.
    assert "traceback" not in low, f"BVG2: traceback in output: {out[:600]!r}"
    assert "error occurred" not in low, f"BVG2: error in output: {out[:600]!r}"

    # Success message.
    assert "purchased and equipped" in low, (
        f"BVG2: expected 'purchased and equipped' in output; got: {out[:400]!r}"
    )

    # Credits decreased.
    credits_after = await h.get_credits(char_id)
    assert credits_after < credits_start, (
        f"BVG2: credits did NOT decrease after successful buy! "
        f"before={credits_start}, after={credits_after}"
    )
    deducted = credits_start - credits_after
    assert 1 <= deducted <= _STOCKED_WEAPON_COST, (
        f"BVG2: deducted={deducted} outside expected range "
        f"[1, {_STOCKED_WEAPON_COST}]; full output: {out[:400]!r}"
    )


async def bvg3_stock_gate_contraband(h):
    """BVG3 — `buy <non-vendor_stocked weapon>` refuses even with vendor present.

    Relies on BVG2 having seeded the vendor NPC in _VENDOR_ROOM so the
    vendor-presence gate passes, leaving only the vendor_stocked gate to
    fire.

    Asserts:
      - Output contains "no open vendor stocks" (the market-segmentation
        refusal from space_commands.py line ~4052).
      - Credits are unchanged.
      - No traceback / error-occurred.
    """
    # Confirm vendor NPC is present (BVG2 must have run first).
    existing = await h.db.fetchall(
        "SELECT id FROM npcs WHERE room_id = ? AND name = ?",
        (_VENDOR_ROOM, _VENDOR_NAME),
    )
    assert existing, (
        "BVG3 pre-condition: vendor NPC must be in room (BVG2 must run first). "
        f"Found: {existing!r}"
    )

    credits_start = 5000
    s = await h.login_as(
        "BVG3StockGate",
        room_id=_VENDOR_ROOM,
        credits=credits_start,
    )
    char_id = s.character["id"]

    out = await h.cmd(s, f"buy {_CONTRABAND_WEAPON_CMD}")
    low = out.lower()

    # No crash.
    assert "traceback" not in low, f"BVG3: traceback in output: {out[:600]!r}"
    assert "error occurred" not in low, f"BVG3: error in output: {out[:600]!r}"

    # The market-segmentation refusal (vendor_stocked gate).
    assert "no open vendor stocks" in low, (
        f"BVG3: expected 'no open vendor stocks' refusal; got: {out[:400]!r}"
    )

    # Credits unchanged — refused purchase must not deduct anything.
    credits_after = await h.get_credits(char_id)
    assert credits_after == credits_start, (
        f"BVG3: credits changed on refused contraband buy! "
        f"before={credits_start}, after={credits_after}"
    )
