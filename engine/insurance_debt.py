# -*- coding: utf-8 -*-
"""
engine/insurance_debt.py — BH Guild insurance-debt service gate.

Per progression_gates_and_consequences_design_v1.md §4.4 ("Insurance
hit (the death-bounty bridge)"):

    Until paid, target cannot:
      - Use Guild services (post bounties, etc.)
      - Receive faction stipends (intercepted by Guild claim)
      - Some BH-tier vendors refuse service

This module provides the single gate point for *blocking* services
(items 1 and 3). Faction stipends are handled separately by
engine/organizations.py's stipend payout loop, which intercepts toward
the debt rather than refusing — it consults db.get_insurance_debt
directly and does NOT call check_debt_gate for that path. The
FACTION_STIPEND constant below is exported for symmetry and for
future call sites that may want to refuse rather than intercept.

Substrate decisions
-------------------

1. **All-or-nothing gate.** Per design §4.4, the bullet is "until
   paid". There is no threshold curve, no partial-allowance band.
   Any outstanding debt > 0 blocks. This is a design call: a
   threshold would be a soft policy that lets griefable behavior leak
   through. Hard gate matches the design's anti-griefing math (§4.6).

2. **Service constants are strings.** Not an enum — strings render
   directly in logs and refusal messages, and downstream code (mostly
   logging) compares them as labels. The constants are also used as
   keys into the SERVICE_LABELS dict that formats refusals.

3. **Async signature.** `check_debt_gate` is async because
   `db.get_insurance_debt` is async; the caller (e.g.
   `pc_bounty_commands._handle_post`) is already in an async context.

4. **Fail-soft on DB errors.** If `db.get_insurance_debt` raises, the
   gate returns `(True, None)` — allow the action. The alternative is
   to deny on lookup error, which would silently break unrelated
   features whenever the bh_insurance_debt table had a problem. Soft
   policy matches the stipend interceptor's behavior in
   `engine/organizations.py` (which also falls through on lookup
   failure).

Consumers (HEAD as of May 21 2026)
----------------------------------

- `parser/pc_bounty_commands.py::_handle_post`
    imports `check_debt_gate` and `BOUNTY_POST`. Crashes without
    this module — this is the original consumer that motivated the
    rebuild.

- `engine/organizations.py` references `FACTION_STIPEND` in a comment
    but does NOT call the gate (it does its own inline accounting per
    the intercept-not-refuse policy).

- `BH_TIER_VENDOR` has no current consumer; reserved for future
    BH-tier vendor refusal hooks per design §4.4.
"""
from __future__ import annotations

import logging
from typing import Optional, Tuple

log = logging.getLogger(__name__)


# ── Service identifiers ─────────────────────────────────────────────────
# Used as the `service` argument to check_debt_gate.
# Values are stable strings; they appear in logs and refusal text.

BOUNTY_POST = "bounty_post"
FACTION_STIPEND = "faction_stipend"
BH_TIER_VENDOR = "bh_tier_vendor"

ALL_SERVICES = (BOUNTY_POST, FACTION_STIPEND, BH_TIER_VENDOR)


# ── Refusal message templates ──────────────────────────────────────────
# Map service → (action label) used in the refusal sentence.
# The full refusal is rendered by _format_refusal() below.

SERVICE_LABELS = {
    BOUNTY_POST:     "post a bounty",
    FACTION_STIPEND: "receive a faction stipend",
    BH_TIER_VENDOR:  "purchase from this vendor",
}


def _format_refusal(service: str, debt: int) -> str:
    """
    Format a refusal message for a blocked service.

    The refusal is printed verbatim by the caller (no leading
    indentation here — the caller adds its own "  " prefix). The
    text mirrors the in-fiction framing of design §4.4: the BH Guild
    has a claim on the character until the debt is cleared.

    Example output:
        You cannot post a bounty until your BH Guild insurance debt
        (3,400 cr) is paid. See +bounty debt / +bounty pay.
    """
    action = SERVICE_LABELS.get(service, "use this service")
    return (
        f"You cannot {action} until your BH Guild insurance debt "
        f"({debt:,} cr) is paid. See +bounty debt / +bounty pay."
    )


# ── The gate ────────────────────────────────────────────────────────────

async def check_debt_gate(
    db,
    char_id: int,
    service: str,
) -> Tuple[bool, Optional[str]]:
    """
    Check whether a character may use the named BH Guild service.

    Returns (allowed, refusal):
        allowed=True,  refusal=None       — proceed
        allowed=False, refusal="..."      — block; print refusal to user

    Policy: any outstanding insurance debt > 0 blocks every gated
    service. There is no partial-allowance band (see module docstring,
    substrate decision #1).

    Fail-soft: if the debt lookup raises, returns (True, None) and
    logs the error. The alternative would silently disable every
    gated service on DB hiccups, which is worse than letting the
    occasional debt slip through.

    Args:
        db: Database instance (must expose `get_insurance_debt`).
        char_id: Character to check.
        service: One of the module-level service constants
            (BOUNTY_POST, FACTION_STIPEND, BH_TIER_VENDOR).
            Unknown services log a warning and are treated as
            BOUNTY_POST for refusal-text purposes.

    Returns:
        (allowed, refusal_text)
    """
    if service not in SERVICE_LABELS:
        log.warning(
            "[insurance_debt] check_debt_gate called with unknown "
            "service=%r for char_id=%s — treating as bounty_post",
            service, char_id,
        )

    try:
        debt = await db.get_insurance_debt(char_id)
    except Exception:
        log.warning(
            "[insurance_debt] get_insurance_debt failed for "
            "char_id=%s service=%s — failing open (allow)",
            char_id, service, exc_info=True,
        )
        return True, None

    # Treat None / missing row as zero debt.
    debt_int = int(debt) if debt else 0
    if debt_int <= 0:
        return True, None

    refusal = _format_refusal(service, debt_int)
    log.info(
        "[insurance_debt] gate BLOCKED char_id=%s service=%s debt=%s",
        char_id, service, debt_int,
    )
    return False, refusal


# ── Introspection helpers (not used by consumers; useful in tests) ─────

async def get_debt(db, char_id: int) -> int:
    """Read the current debt, treating None/missing as 0. Never raises."""
    try:
        debt = await db.get_insurance_debt(char_id)
        return int(debt) if debt else 0
    except Exception:
        log.warning(
            "[insurance_debt] get_debt: lookup failed for char_id=%s",
            char_id, exc_info=True,
        )
        return 0


async def has_debt(db, char_id: int) -> bool:
    """True if the character has any outstanding insurance debt."""
    return (await get_debt(db, char_id)) > 0
