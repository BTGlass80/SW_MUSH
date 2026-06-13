# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/commissary_loop.py — Commissary faction-gear loop smoke
(CL1-CL3).

Coverage:
  CL1: A sworn Bounty Hunters' Guild member at rank >= 1 sees tracking_fob in
       +commissary (verifies board renders without crash, faction + rank gate
       passes, item is listed).
  CL2: `+commissary buy tracking_fob` debits exactly 350 credits (the
       commissary_purchase sink fires via adjust_credits) and the item lands
       in the character's inventory blob WITH its skill_bonus dict.
  CL3: NEGATIVE — a character with faction_id="jedi_order" (no commissary)
       gets the austere refusal from +commissary; no credits are debited.

Seeding strategy (deterministic):
  CL1/CL2 — Both need a BHG member at rank 1.  seed_bhg_member() creates the
  character, sets faction_id="bounty_hunters_guild" via save_character, looks
  up the seeded BHG org row, then calls join_organization + update_membership
  to plant a rank_level=1 org_memberships row.  No full join_faction() call
  (which issues equipment and fires many hooks) — direct DB seam only.

  CL3 — Character has faction_id="jedi_order" (the order has no COMMISSARY_STOCK
  entry); the +commissary command returns the austere refusal before any credit
  movement can occur.

What each arm catches:
  CL1 — commissary command crashes / faction-rank resolution silently fails /
         tracking_fob missing from BHG stock (data regression).
  CL2 — adjust_credits not called; wrong tag; grant fails silently; inventory
         blob never written; skill_bonus not preserved in inventory item dict.
  CL3 — faction-gate bypassed; austere faction sees items or charge fires.
"""
from __future__ import annotations

import json as _json

# ── Constants ─────────────────────────────────────────────────────────────────

_FOB_KEY  = "tracking_fob"
_FOB_COST = 350         # commissary.py:71
_FOB_SKILL_BONUS = {"skill": "search", "bonus": "+1D"}

_BHG_CODE = "bounty_hunters_guild"
_JEDI_CODE = "jedi_order"


# ── Shared seeding helper ─────────────────────────────────────────────────────

async def _seed_bhg_member(h, name: str, credits: int) -> tuple:
    """Return (client_session, char_id) for a BHG member at rank 1.

    Sequence:
      1. login_as() — creates character row + session.
      2. save_character(..., faction_id=_BHG_CODE) — sets faction column.
      3. get_organization(_BHG_CODE) — resolves the seeded org id.
      4. join_organization(char_id, org_id) — plants org_memberships row
         with rank_level=0 (default).
      5. update_membership(char_id, org_id, rank_level=1) — promotes to
         rank 1, which is the min_rank required for tracking_fob.
      6. Refresh s.character so the live session sees faction_id.
    """
    s = await h.login_as(name, room_id=1, credits=credits)
    char_id = s.character["id"]

    # Set faction_id on the DB row.
    await h.db.save_character(char_id, faction_id=_BHG_CODE)

    # Resolve the BHG org row (seeded by seed_organizations at boot).
    org = await h.db.get_organization(_BHG_CODE)
    assert org is not None, (
        f"bounty_hunters_guild org row not found in DB — "
        f"seed_organizations may have failed during harness boot."
    )
    org_id = org["id"]

    # Plant membership at rank 0, then promote to rank 1.
    await h.db.join_organization(char_id, org_id)
    await h.db.update_membership(char_id, org_id, rank_level=1)

    # Refresh session character so +commissary reads faction_id correctly.
    s.character = await h.get_char(char_id)

    return s, char_id


# ── CL1 — BHG member sees tracking_fob on +commissary ────────────────────────

async def cl1_bhg_member_sees_tracking_fob(h):
    """CL1 — A sworn BHG member at rank 1 sees tracking_fob on +commissary.

    Wiring regressions caught:
    - commissary command raises on rank resolution (_resolve_faction_rank
      exception silently caught → rank=0 → tracking_fob hidden as rank-locked)
    - BHG org row missing from DB (seed_organizations didn't run)
    - tracking_fob missing from bounty_hunters_guild COMMISSARY_STOCK (data
      regression in engine/commissary.py)
    - commissary_status_lines returns "does not maintain a commissary" for BHG
      (faction check broken)
    """
    s, char_id = await _seed_bhg_member(h, "CL1BHGMember", credits=1000)

    out = await h.cmd(s, "+commissary")
    low = out.lower()

    assert out and out.strip(), "+commissary produced no output"
    assert "traceback" not in low, f"CL1: traceback in output: {out[:600]!r}"
    assert "error occurred" not in low, f"CL1: error in output: {out[:600]!r}"

    # Must render the commissary header (not the "no commissary" / "not in a
    # faction" refusal).
    assert "faction commissary" in low or "requisition" in low, (
        f"CL1: +commissary header not found. Output: {out[:500]!r}"
    )

    # tracking_fob must appear (rank 1 unlocks it).
    assert _FOB_KEY in out or "tracking fob" in low, (
        f"CL1: tracking_fob not visible for rank-1 BHG member. "
        f"Output: {out[:600]!r}"
    )

    # Must NOT see the austere refusal.
    assert "does not maintain a commissary" not in low, (
        f"CL1: got austere refusal for BHG — faction gate broken. "
        f"Output: {out[:400]!r}"
    )


# ── CL2 — buy tracking_fob debits 350 cr + inventory blob has skill_bonus ────

async def cl2_buy_tracking_fob_debits_and_grants(h):
    """CL2 — `+commissary buy tracking_fob` debits exactly 350 credits via the
    commissary_purchase sink and lands the item in the inventory blob with its
    skill_bonus dict intact.

    Wiring regressions caught:
    - adjust_credits not called (credits unchanged after buy)
    - adjust_credits called with wrong tag (funnel invariant, no assert
      on tag text — the debit amount is the observable)
    - grant path fails silently (inventory blob not written / item absent)
    - skill_bonus not preserved in inv_item construction
      (engine/commissary.py purchase_commissary's inv_item build)
    - refund path fires erroneously (credits back to pre-buy level)
    """
    s, char_id = await _seed_bhg_member(h, "CL2BHGBuyer", credits=1000)

    credits_before = await h.get_credits(char_id)
    assert credits_before == 1000, (
        f"CL2: pre-condition credits mismatch: {credits_before}"
    )

    out = await h.cmd(s, f"+commissary buy {_FOB_KEY}")
    low = out.lower()

    assert "traceback" not in low, f"CL2: traceback in output: {out[:600]!r}"
    assert "error occurred" not in low, f"CL2: error in output: {out[:600]!r}"

    # Success message from _buy → send_line("Requisitioned … for … credits.")
    assert "requisitioned" in low or "tracking fob" in low, (
        f"CL2: expected requisition success message; got: {out[:500]!r}"
    )

    # Credit delta: exactly 350 debited.
    credits_after = await h.get_credits(char_id)
    assert credits_after == credits_before - _FOB_COST, (
        f"CL2: expected credits {credits_before - _FOB_COST}, "
        f"got {credits_after}. before={credits_before}. "
        f"Output: {out[:500]!r}"
    )

    # Inventory: tracking_fob must be present AND carry skill_bonus.
    fresh = await h.get_char(char_id)
    raw_inv = fresh.get("inventory") or "{}"
    try:
        inv_data = _json.loads(raw_inv)
    except Exception:
        inv_data = {}

    # Normalise legacy list vs. dict format.
    if isinstance(inv_data, list):
        items = inv_data
    elif isinstance(inv_data, dict):
        items = inv_data.get("items", [])
    else:
        items = []

    fob_items = [it for it in items if it.get("key") == _FOB_KEY]
    assert fob_items, (
        f"CL2: tracking_fob not found in inventory after purchase. "
        f"items={[it.get('key') for it in items]!r}. "
        f"Command output: {out[:500]!r}"
    )

    # skill_bonus must survive the inv_item build (engine/commissary.py:230-237).
    fob = fob_items[0]
    assert "skill_bonus" in fob, (
        f"CL2: skill_bonus missing from tracking_fob inventory entry. "
        f"fob={fob!r}"
    )
    assert fob["skill_bonus"] == _FOB_SKILL_BONUS, (
        f"CL2: skill_bonus value wrong. "
        f"expected={_FOB_SKILL_BONUS!r} got={fob['skill_bonus']!r}"
    )


# ── CL3 — jedi_order (no commissary) gets austere refusal, no debit ──────────

async def cl3_no_commissary_faction_refused(h):
    """CL3 — A character with faction_id="jedi_order" gets the austere refusal
    from +commissary and no credits are debited.

    The Jedi Order has no COMMISSARY_STOCK entry (design invariant from
    engine/commissary.py header: "The Jedi Order has no commissary"). The
    commissary_status_lines() path returns "does not maintain a commissary".

    Wiring regressions caught:
    - faction_has_commissary gate bypassed (jedi_order sees items)
    - "not in a faction" early-return fires instead of the proper
      "does not maintain" path (faction_id set but gate wrong)
    - credits debited even on a refused buy
    """
    # Seed a jedi_order character. We do NOT need an org_memberships row —
    # _resolve_faction_rank gracefully returns rank=0 when no row exists, and
    # the commissary gate fires before any rank check for factions without stock.
    s = await h.login_as("CL3JediRefused", room_id=1, credits=500)
    char_id = s.character["id"]

    await h.db.save_character(char_id, faction_id=_JEDI_CODE)
    s.character = await h.get_char(char_id)

    credits_before = await h.get_credits(char_id)

    # Test both: the listing command and the buy command.
    out_list = await h.cmd(s, "+commissary")
    low_list = out_list.lower()

    assert "traceback" not in low_list, (
        f"CL3: traceback on +commissary list: {out_list[:600]!r}"
    )
    assert "error occurred" not in low_list, (
        f"CL3: error on +commissary list: {out_list[:600]!r}"
    )
    # The commissary_status_lines path returns this exact string for
    # factions not in COMMISSARY_STOCK.
    assert "does not maintain a commissary" in low_list, (
        f"CL3: expected austere refusal 'does not maintain a commissary'; "
        f"got: {out_list[:500]!r}"
    )

    # Buy command — must also refuse without debit.
    out_buy = await h.cmd(s, f"+commissary buy {_FOB_KEY}")
    low_buy = out_buy.lower()

    assert "traceback" not in low_buy, (
        f"CL3: traceback on +commissary buy: {out_buy[:600]!r}"
    )
    assert "error occurred" not in low_buy, (
        f"CL3: error on +commissary buy: {out_buy[:600]!r}"
    )
    assert "does not maintain a commissary" in low_buy, (
        f"CL3: buy should refuse with austere message; got: {out_buy[:500]!r}"
    )

    # Credits must be unchanged across both refused commands.
    credits_after = await h.get_credits(char_id)
    assert credits_after == credits_before, (
        f"CL3: credits changed after refused +commissary on jedi_order! "
        f"before={credits_before} after={credits_after}"
    )
