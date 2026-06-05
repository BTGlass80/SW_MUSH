# -*- coding: utf-8 -*-
"""
engine/gear_insurance.py — Drop 3 B4: gear insurance (loadout protection, willing sink).

A one-shot policy a player buys with ``+insure buy``. It debits a flat premium
through the ledger chokepoint as ``gear_insurance_premium`` (a pure sink) and
sets the character's ``gear_insured`` flag. On the holder's next
lawless/contested death, the death flow (``engine/death.py``) keeps their loose
loadout on them instead of dropping it to a lootable corpse, and consumes the
policy.

DESIGN CALL — why there is NO payout
------------------------------------
This game's death model does NOT destroy gear: it sends a dead PC's loose
inventory to a *re-lootable* corpse (Drop 2 already preserves *equipped* gear
on the character). So a credit indemnity (the obvious ``gear_insurance_payout``)
would be a **suicide-faucet**: a player could die on demand, re-loot their own
gear off the corpse, AND pocket the payout. Protecting the *loadout* with no
payout is the only exploit-safe shape — the premium is the sole credit movement
(a sink), so there is nothing to farm. Uninsured deaths still drop loose gear,
so the consensual gear-loss sink the lawless/contested zones rest on survives.

Storage: the ``characters.gear_insured`` flag (0/1) added by main schema
migration v39. ``purchase_gear_insurance`` / ``cancel_gear_insurance`` write it
through the allowlisted ``save_character`` proxy; the death flow consumes it
(flips it to 0) in ``engine/death.py::_consume_gear_insurance_if_active``.

This module mirrors ``engine/titles.py``: small pure helpers plus the two
async, ledger-routed, refund-safe mutators the command renders.
"""

import logging

log = logging.getLogger(__name__)

# Flat premium for a one-shot policy (tunable for v1; ratify against live
# @economy data). If *everyone* insures — eroding the gear-loss sink the
# consensual-loss model rests on — raise this or scale it by assessed loadout
# value. Valuation would only affect premium *fairness*, never exploit-safety,
# since there is no payout.
GEAR_INSURANCE_PREMIUM = 500

# Ledger source tags (stable; grouped on the @economy dashboard). Reuse these
# rather than inventing near-duplicates.
PREMIUM_SOURCE = "gear_insurance_premium"
PREMIUM_REFUND_SOURCE = "gear_insurance_premium_refund"


# ── Pure helpers ─────────────────────────────────────────────────────────────
def premium_amount() -> int:
    """The flat premium for a one-shot gear-insurance policy."""
    return GEAR_INSURANCE_PREMIUM


def is_insured(char) -> bool:
    """True iff the character currently holds an active gear policy."""
    try:
        return bool(int(char.get("gear_insured") or 0))
    except (TypeError, ValueError, AttributeError):
        return False


def insure_status_lines(char) -> list:
    """Player-facing ``+insure`` status lines (no credit movement)."""
    lines = []
    if is_insured(char):
        lines.append("  Coverage: ACTIVE - a one-shot policy.")
        lines.append("    Your loose loadout is protected on your next death")
        lines.append("    in a lawless or contested zone (the policy is then")
        lines.append("    spent). Equipped gear is always kept regardless.")
        lines.append("    There is no cash payout - only the loadout is kept.")
        lines.append("  +insure cancel  - drop coverage (no refund).")
    else:
        lines.append("  Coverage: none.")
        lines.append("    In a lawless or contested zone, the loose gear you")
        lines.append("    carry drops to your corpse when you die (anyone can")
        lines.append("    loot it). A policy keeps that loadout on you once.")
        lines.append("    Equipped gear is always kept, insured or not.")
        lines.append("  +insure buy     - buy coverage for {:,} credits.".format(
            GEAR_INSURANCE_PREMIUM))
    return lines


# ── The sink: buy / cancel a policy ──────────────────────────────────────────
async def purchase_gear_insurance(db, char: dict) -> dict:
    """Buy a one-shot gear-insurance policy for ``char``.

    Debits the flat premium through the ledger chokepoint as
    ``gear_insurance_premium`` (a pure sink) and sets ``gear_insured``.
    Refund-safe: the premium is taken before the flag is persisted, and a
    ``gear_insurance_premium_refund`` fires if the persist fails. Returns a
    result dict the command renders.
    """
    if is_insured(char):
        return {"ok": False, "reason": "already"}

    cost = GEAR_INSURANCE_PREMIUM
    try:
        balance = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        balance = 0
    if balance < cost:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - balance}

    # Debit FIRST (the sink), then persist; refund on failure so a failed buy
    # never eats credits.
    try:
        char["credits"] = await db.adjust_credits(char["id"], -cost, PREMIUM_SOURCE)
    except Exception:
        log.warning("[gear_insurance] premium debit failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "charge_failed"}

    try:
        await db.save_character(char["id"], gear_insured=1)
        char["gear_insured"] = 1
    except Exception:
        log.warning("[gear_insurance] persist failed for char %s; refunding",
                    char.get("id"), exc_info=True)
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], cost, PREMIUM_REFUND_SOURCE)
        except Exception:
            log.error("[gear_insurance] premium REFUND FAILED for char %s",
                      char.get("id"), exc_info=True)
        return {"ok": False, "reason": "persist_failed"}

    return {"ok": True, "cost": cost}


async def cancel_gear_insurance(db, char: dict) -> dict:
    """Cancel an active policy.

    No refund - the premium bought an *option*; forfeiting unused coverage
    keeps the premium a pure sink (no buy/cancel wash to farm). Returns a
    result dict the command renders.
    """
    if not is_insured(char):
        return {"ok": False, "reason": "none"}
    try:
        await db.save_character(char["id"], gear_insured=0)
        char["gear_insured"] = 0
    except Exception:
        log.warning("[gear_insurance] cancel persist failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "persist_failed"}
    return {"ok": True}
