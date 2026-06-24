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


# ── T3.19 telemetry ───────────────────────────────────────────────────────────
def _emit_gear_insurance(action: str, char_id, amount: int, **extra) -> None:
    """T3.19 telemetry: one fail-open ``gear_insurance`` event per
    policy-lifecycle transition.

    The premium debit already rides ``credit_flow`` per-tag
    (``gear_insurance_premium`` / ``gear_insurance_premium_refund``), but those
    isolated ``credit_flow`` rows can't be rejoined offline into the policy
    *lifecycle* — the buy → cancel voluntary-churn rate, or the premium-sink
    volume against take-up. That lifecycle is the direct signal for tuning the
    one lever this module has (``GEAR_INSURANCE_PREMIUM``): if *everyone* insures
    the consensual gear-loss sink erodes (raise it); if nobody does it is dead
    weight (lower it or scale by loadout value). The death-consume leg moves no
    credits and lives in ``engine/death.py`` (an avoid-lane), so it is
    deliberately NOT emitted here — this emitter covers the buy/cancel side.

      action : the lifecycle transition — ``"purchase"`` / ``"cancel"``.
      char_id: the acting character (coerced to int when it parses so a str-id
               and int-id system join on the same player).
      amount : signed credit delta — negative for the premium sink (purchase),
               0 for a cancel (no refund — the premium is a pure sink).
      extra  : action-specific fields (premium, …); ``None`` values are dropped
               so the record stays clean.

    Sampling honours ``telemetry.gear_insurance_sample`` (default 1.0 — buying a
    policy is a deliberate, low-frequency act, so full capture by default).
    Buffer-only + offline-flushed → can NEVER disturb the buy/cancel it observes.
    """
    try:
        try:
            cid = int(char_id)
        except (TypeError, ValueError):
            cid = char_id
        fields = {"action": action, "char_id": cid, "amount": int(amount)}
        for k, v in extra.items():
            if v is not None and k not in fields:
                fields[k] = v
        from engine.telemetry import emit as _tele_emit
        try:
            from engine.tunables import get_tunable
            sample = float(get_tunable("telemetry.gear_insurance_sample", 1.0))
        except Exception:
            sample = 1.0
        _tele_emit("gear_insurance", fields, sample=sample)
    except Exception:
        log.debug("gear_insurance telemetry emit failed", exc_info=True)


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
    # allow_negative=False refuses a concurrent overdraw atomically; None return
    # means insufficient funds — treat identically to the balance pre-check above.
    try:
        new_balance = await db.adjust_credits(
            char["id"], -cost, PREMIUM_SOURCE, allow_negative=False)
    except Exception:
        log.warning("[gear_insurance] premium debit failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "charge_failed"}
    if new_balance is None:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - int(char.get("credits") or 0)}
    char["credits"] = new_balance

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

    # Lifecycle telemetry: one fail-open event AFTER the premium sink + flag
    # persist both succeed, so a refused/refunded buy emits nothing.
    _emit_gear_insurance("purchase", char["id"], -cost, premium=cost)
    return {"ok": True, "cost": cost}


async def cancel_gear_insurance(db, char: dict) -> dict:
    """Cancel an active policy.

    No refund - the premium bought an *option*; forfeiting unused coverage
    keeps the premium a pure sink (no buy/cancel wash to farm). Returns a
    result dict the command renders.

    Guards against a stale session-cache "still insured" state: after a death
    the DB consumer (_consume_gear_insurance_if_active in engine/death.py)
    flips gear_insured→0 in the DB but does NOT update the session-cache
    char dict (no session_mgr is available at that call site).  A player who
    types ``+insure cancel`` immediately after dying would see the cache as
    gear_insured=1, pass the is_insured(char) guard, and get a spurious
    "coverage dropped" success.  The DB re-read below catches this: if the
    live DB row says 0 we return not_insured immediately rather than writing
    another (no-op) UPDATE.
    """
    if not is_insured(char):
        return {"ok": False, "reason": "not_insured"}

    # Authoritative DB check: the session-cache may be stale if the policy
    # was consumed by an on_pc_death call since the last reload.
    try:
        rows = await db._db.execute_fetchall(  # noqa: SLF001
            "SELECT gear_insured FROM characters WHERE id = ?",
            (char["id"],),
        )
        if not rows or not bool(rows[0]["gear_insured"]):
            # DB already shows 0 (policy was consumed by a death).
            # Sync the local cache so future callers don't hit this again.
            char["gear_insured"] = 0
            return {"ok": False, "reason": "not_insured"}
    except Exception:
        # DB read failed; fall through to the save attempt, which will
        # catch any real persistence problem on its own.
        log.debug("[gear_insurance] cancel DB pre-read failed for char %s; "
                  "proceeding with save attempt", char.get("id"),
                  exc_info=True)

    try:
        await db.save_character(char["id"], gear_insured=0)
        char["gear_insured"] = 0
    except Exception:
        log.warning("[gear_insurance] cancel persist failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "persist_failed"}
    # Lifecycle telemetry: a voluntary checkout — no credits move (no refund).
    # Wired after the flag-clear persist, so a refused/stale-cache/failed cancel
    # emits nothing.
    _emit_gear_insurance("cancel", char["id"], 0)
    return {"ok": True}
