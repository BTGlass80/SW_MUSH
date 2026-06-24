# -*- coding: utf-8 -*-
"""
engine/debt.py — Hutt Cartel debt system for "From Dust to Stars" quest chain.

Weekly tick handler that auto-deducts 500cr from players with active
hutt_debt in their attributes. Missed payments trigger warnings and
eventually hostile NPC spawns.

Integration: Called from tick_handlers_economy.py on the weekly cycle.
"""

import json
import logging
import time

log = logging.getLogger(__name__)

DEBT_WEEKLY_PAYMENT = 500
DEBT_WARNING_THRESHOLD = 2     # missed payments before threatening comlink
DEBT_ENFORCER_THRESHOLD = 3    # missed payments before enforcer spawn

_COMLINK = "\033[1;35m[COMLINK]\033[0m"


# ── T3.19 telemetry ───────────────────────────────────────────────────────────
def _emit_debt(action: str, char_id, amount: int, **extra) -> None:
    """T3.19 telemetry: one fail-open ``debt`` event per Hutt-debt-lifecycle
    transition.

    The weekly payment debit already rides ``credit_flow`` under the
    ``debt_payment`` tag, but those isolated per-tick rows can't be rejoined
    offline into the debt *lifecycle*: how many debtors pay on schedule vs miss,
    the miss → enforcer-escalation rate, and the time-to-payoff distribution.
    That lifecycle is the direct signal for tuning this module's levers
    (``DEBT_WEEKLY_PAYMENT`` = 500cr and the warning/enforcer miss thresholds):
    if nobody ever misses the 500cr debit is painless dead weight (raise it or
    shorten the schedule); if most debtors escalate straight to the enforcer the
    pressure is punitive (lower the weekly bite or widen the warning window).

      action : the lifecycle transition — ``"payment"`` (a partial weekly
               payment), ``"payoff"`` (the final payment that cleared the
               principal), or ``"missed"`` (insufficient credits at the due
               date; the ``escalation`` field tags warning/enforcer).
      char_id: the acting character (coerced to int when it parses so a str-id
               and int-id system join on the same player).
      amount : signed credit delta — negative for the payment sink, 0 for a
               missed payment (no credits move).
      extra  : action-specific fields (principal_remaining, total_paid,
               payments_missed, escalation, …); ``None`` values are dropped so
               the record stays clean.

    Sampling honours ``telemetry.debt_sample`` (default 1.0 — a debt event fires
    at most once per debtor per weekly tick, so it is low-frequency + high-value
    and warrants full capture). Buffer-only + offline-flushed → can NEVER disturb
    the payment path it observes.
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
            sample = float(get_tunable("telemetry.debt_sample", 1.0))
        except Exception:
            sample = 1.0
        _tele_emit("debt", fields, sample=sample)
    except Exception:
        log.debug("debt telemetry emit failed", exc_info=True)


async def process_all_debts(db, session_mgr):
    """
    Called once per weekly tick cycle.
    Iterates all characters with active hutt_debt and processes payments.
    """
    try:
        # Get all active characters
        rows = await db.fetchall(
            "SELECT id, credits, attributes FROM characters WHERE is_active = 1"
        )
    except Exception:
        log.warning("process_all_debts: failed to query characters",
                    exc_info=True)
        return

    now = int(time.time())
    processed = 0

    for row in rows:
        try:
            char_id = row[0] if isinstance(row, (list, tuple)) else row["id"]
            credits = row[1] if isinstance(row, (list, tuple)) else row["credits"]
            attrs_raw = row[2] if isinstance(row, (list, tuple)) else row["attributes"]

            if not attrs_raw:
                continue

            attrs = json.loads(attrs_raw) if isinstance(attrs_raw, str) else attrs_raw
            debt = attrs.get("hutt_debt")
            if not debt or debt.get("principal", 0) <= 0:
                continue

            # Check if payment is due
            next_due = debt.get("next_payment_due", 0)
            if now < next_due:
                continue

            # Find the player's session (for comlink messages)
            sess = None
            if session_mgr:
                for s in session_mgr.all:
                    if (s.is_in_game and s.character
                            and s.character.get("id") == char_id):
                        sess = s
                        break

            # Try to collect payment
            payment = min(DEBT_WEEKLY_PAYMENT, debt["principal"])

            if credits >= payment:
                # Successful payment
                new_credits = credits - payment
                debt["principal"] -= payment
                debt["total_paid"] = debt.get("total_paid", 0) + payment
                debt["payments_missed"] = 0
                debt["next_payment_due"] = now + 604800  # 7 days

                attrs["hutt_debt"] = debt
                await db.save_character(
                    char_id,
                    attributes=json.dumps(attrs),
                )
                # Ledger chokepoint (F1): debt payment as a logged sink.
                await db.adjust_credits(char_id, -payment, "debt_payment")

                remaining = debt["principal"]
                # Lifecycle telemetry: AFTER the sink + attr persist both
                # succeed — a partial weekly payment vs the final payoff. Fires
                # regardless of whether the debtor has a live session.
                _emit_debt(
                    "payoff" if remaining <= 0 else "payment",
                    char_id, -payment,
                    principal_remaining=remaining,
                    total_paid=debt.get("total_paid", 0),
                )

                if sess:
                    if remaining <= 0:
                        # Debt paid off!
                        await sess.send_line(
                            f"\n  {_COMLINK} Grek: \"Final payment received. "
                            f"Your account with Drago the Hutt is closed. "
                            f"Pleasure doing business, Captain.\"")
                        # Award title
                        titles = attrs.get("tutorial_titles", [])
                        if "(Debt Free)" not in titles:
                            titles.append("(Debt Free)")
                            attrs["tutorial_titles"] = titles
                            await db.save_character(
                                char_id,
                                attributes=json.dumps(attrs),
                            )
                            await sess.send_line(
                                f"  \033[1;36mTitle earned: (Debt Free)\033[0m")
                    else:
                        await sess.send_line(
                            f"\n  {_COMLINK} Grek: \"Payment received. "
                            f"Balance: {remaining:,} credits remaining.\"")

                processed += 1

            else:
                # Missed payment
                debt["payments_missed"] = debt.get("payments_missed", 0) + 1
                debt["next_payment_due"] = now + 604800  # still advances
                missed = debt["payments_missed"]

                attrs["hutt_debt"] = debt
                await db.save_character(
                    char_id,
                    attributes=json.dumps(attrs),
                )

                if sess:
                    if missed >= DEBT_ENFORCER_THRESHOLD:
                        await sess.send_line(
                            f"\n  {_COMLINK} Grek: \"Three missed payments, "
                            f"Captain. Drago is very disappointed. He's "
                            f"sending someone to... discuss your financial "
                            f"planning. I'd suggest having the credits ready "
                            f"next time.\"")
                        # TODO: Spawn hostile Hutt Enforcer NPC near player
                        # For now, just the threatening message.
                        # Reset missed to 0 after enforcer threat
                        debt["payments_missed"] = 0
                        attrs["hutt_debt"] = debt
                        await db.save_character(
                            char_id,
                            attributes=json.dumps(attrs),
                        )
                    elif missed >= DEBT_WARNING_THRESHOLD:
                        await sess.send_line(
                            f"\n  {_COMLINK} Grek: \"You missed another "
                            f"payment. Drago doesn't like waiting. Get the "
                            f"credits together — 500 is all we ask. Don't "
                            f"make me send someone.\"")

                # Lifecycle telemetry: emitted outside the session gate so a
                # missed payment is recorded even for an offline debtor, using
                # the pre-reset ``missed`` count. The escalation tag is derived
                # from the count (independent of whether the threat was shown),
                # so the debt's true missed-payment state is captured.
                _emit_debt(
                    "missed", char_id, 0,
                    payments_missed=missed,
                    principal_remaining=debt["principal"],
                    escalation=(
                        "enforcer" if missed >= DEBT_ENFORCER_THRESHOLD
                        else "warning" if missed >= DEBT_WARNING_THRESHOLD
                        else None
                    ),
                )

                processed += 1

        except Exception:
            log.warning("process_all_debts: error processing char %s",
                        row, exc_info=True)
            continue

    if processed > 0:
        log.info("[debt] Processed %d debt payments", processed)
