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


async def process_all_debts(db, session_mgr):
    """
    Called once per weekly tick cycle.
    Iterates all characters with active hutt_debt and processes payments.
    """
    try:
        # Get all active characters
        rows = await db._db.execute_fetchall(
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
                for s in session_mgr.sessions:
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
                    credits=new_credits,
                    attributes=json.dumps(attrs),
                )

                if sess:
                    remaining = debt["principal"]
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

                processed += 1

        except Exception:
            log.warning("process_all_debts: error processing char %s",
                        row, exc_info=True)
            continue

    if processed > 0:
        log.info("[debt] Processed %d debt payments", processed)
