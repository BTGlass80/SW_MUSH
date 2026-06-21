# -*- coding: utf-8 -*-
"""
engine/dens.py — Drop 3 A5: sabacc dens (the criminal-empire loop).

A Hutt-cartel org "operates" a sabacc den in a cantina room. A sufficiently-
ranked cartel member establishes one with ``+den establish`` (paying a setup-cost
sink); while a room is a den, the sabacc house rake (after the city's slice)
routes to that org's treasury — see ``parser/sabacc_commands.py``.

DESIGN CALL — why a dedicated per-room den marker (not territory/region ownership)
--------------------------------------------------------------------------------
The region-ownership model (``region_ownership``) is wilderness-only and cantina
rooms have no region/owner; extending ownership into the city was explicitly
ruled out. So dens get their own lightweight per-room marker (the ``sabacc_dens``
table, schema v40): one den per room, owned by one org, established by an actual
in-world act (the "build the empire" verb). Clean one-row lookup, no dependence
on the mid-migration territory model.

DESIGN CALL — the rake is a transfer, not conjured credits
----------------------------------------------------------
The rake routing (in sabacc) credits the winner the FULL gross win (``sabacc``)
then DEBITS the rake (``sabacc_rake``) — so the org's receipt is sourced from the
player, never net-new creation. The player's net is unchanged. This also fixes
audit F15 (the house cut was previously notional + unlogged) for *every* sabacc
game, den or not: in a public cantina the debited rake is a pure sink; in a den
it transfers to the org treasury.

This module: the setup constants, a PURE eligibility helper, and the DB-touching
den CRUD + establish/abandon mutators (mirrors engine/gear_insurance.py's shape).
"""

import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# Only the Hutt cartel runs dens (the criminal faction in the CW 5-faction model).
HUTT_ORG_CODE = "hutt_cartel"

# Minimum cartel rank to establish a den (you've earned standing to run one for
# the kajidic). Tunable.
DEN_ESTABLISH_MIN_RANK = 3

# One-time setup cost, debited from the establishing member (a sink + the
# criminal-investment fantasy). Tunable.
DEN_SETUP_COST = 10_000
DEN_SETUP_SOURCE = "sabacc_den_setup"
DEN_SETUP_REFUND_SOURCE = "sabacc_den_setup_refund"


# ── Pure eligibility ─────────────────────────────────────────────────────────
def check_den_eligibility(*, is_cantina: bool, membership: Optional[dict],
                          existing_den: Optional[dict], balance: int,
                          min_rank: int = DEN_ESTABLISH_MIN_RANK,
                          cost: int = DEN_SETUP_COST) -> dict:
    """Decide whether a den may be established here. Pure.

    Returns ``{"ok": True}`` or ``{"ok": False, "reason": <key>}`` where reason
    is one of: ``not_cantina``, ``not_member``, ``rank``, ``already_den``,
    ``insufficient``. ``membership`` is the caller's hutt_cartel membership row
    (or None); ``existing_den`` is any den already on the room (or None).
    """
    if not is_cantina:
        return {"ok": False, "reason": "not_cantina"}
    if not membership:
        return {"ok": False, "reason": "not_member"}
    try:
        rank = int(membership.get("rank_level") or 0)
    except (TypeError, ValueError):
        rank = 0
    if rank < min_rank:
        return {"ok": False, "reason": "rank", "rank": rank, "need": min_rank}
    if existing_den:
        return {"ok": False, "reason": "already_den"}
    try:
        bal = int(balance or 0)
    except (TypeError, ValueError):
        bal = 0
    if bal < cost:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - bal}
    return {"ok": True}


# ── DB helpers ───────────────────────────────────────────────────────────────
async def get_room_den(db, room_id: int) -> Optional[dict]:
    """Return the den row for a room (``{room_id, org_id, org_code, ...}``) or None."""
    try:
        rows = await db.fetchall(
            "SELECT room_id, org_id, org_code, established_by, established_at "
            "FROM sabacc_dens WHERE room_id = ?", (room_id,))
    except Exception:
        log.warning("[dens] get_room_den failed for room %s", room_id,
                    exc_info=True)
        return None
    return dict(rows[0]) if rows else None


async def get_org_dens(db, org_id: int) -> list:
    """Return all den rows owned by an org."""
    try:
        rows = await db.fetchall(
            "SELECT room_id, org_id, org_code, established_by, established_at "
            "FROM sabacc_dens WHERE org_id = ? ORDER BY established_at", (org_id,))
    except Exception:
        log.warning("[dens] get_org_dens failed for org %s", org_id,
                    exc_info=True)
        return []
    return [dict(r) for r in rows]


async def _is_cantina_room(db, room_id: int) -> bool:
    """True if the room's zone name contains 'cantina' (where sabacc is played)."""
    try:
        room = await db.get_room(room_id)
        if not room or not room.get("zone_id"):
            return False
        zone = await db.get_zone(room["zone_id"])
        return "cantina" in ((zone.get("name") or "").lower() if zone else "")
    except Exception:
        log.warning("[dens] _is_cantina_room failed for room %s", room_id,
                    exc_info=True)
        return False


async def establish_den(db, char: dict, *,
                        min_rank: int = DEN_ESTABLISH_MIN_RANK,
                        cost: int = DEN_SETUP_COST) -> dict:
    """Establish a Hutt-cartel den in the character's current room.

    Gating (via ``check_den_eligibility``): the room is a cantina, the character
    is a hutt_cartel member of rank >= ``min_rank``, the room isn't already a den,
    and they can afford the setup cost. On success the cost is debited through the
    ledger as ``sabacc_den_setup`` (a sink), then the den row is written; a refund
    fires if the write fails. Returns a result dict the command renders.
    """
    room_id = char.get("room_id")
    is_cantina = await _is_cantina_room(db, room_id)

    org = await db.get_organization(HUTT_ORG_CODE)
    membership = None
    if org:
        membership = await db.get_membership(char["id"], org["id"])

    existing = await get_room_den(db, room_id)

    try:
        balance = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        balance = 0

    elig = check_den_eligibility(
        is_cantina=is_cantina, membership=membership, existing_den=existing,
        balance=balance, min_rank=min_rank, cost=cost)
    if not elig.get("ok"):
        return elig

    # Debit the setup cost (sink) FIRST, then write the den; refund on failure.
    # allow_negative=False refuses a concurrent overdraw atomically; None return
    # means insufficient funds — treat identically to the balance pre-check above.
    try:
        new_balance = await db.adjust_credits(
            char["id"], -cost, DEN_SETUP_SOURCE, allow_negative=False)
    except Exception:
        log.warning("[dens] setup debit failed for char %s", char.get("id"),
                    exc_info=True)
        return {"ok": False, "reason": "charge_failed"}
    if new_balance is None:
        return {"ok": False, "reason": "insufficient"}
    char["credits"] = new_balance

    try:
        await db._db.execute(  # noqa: SLF001
            "INSERT OR REPLACE INTO sabacc_dens "
            "(room_id, org_id, org_code, established_by, established_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (room_id, org["id"], org["code"], char["id"], time.time()))
        await db._db.commit()  # noqa: SLF001
    except Exception:
        log.warning("[dens] den write failed for room %s; refunding", room_id,
                    exc_info=True)
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], cost, DEN_SETUP_REFUND_SOURCE)
        except Exception:
            log.error("[dens] setup REFUND FAILED for char %s", char.get("id"),
                      exc_info=True)
        return {"ok": False, "reason": "write_failed"}

    return {"ok": True, "cost": cost, "org_name": org.get("name", "the cartel")}


async def abandon_den(db, char: dict) -> dict:
    """Abandon the Hutt-cartel den in the character's current room.

    Gating: the room is a den owned by the character's hutt_cartel org, and the
    character is a member of rank >= ``DEN_ESTABLISH_MIN_RANK``. No refund of the
    setup cost. Returns a result dict.
    """
    room_id = char.get("room_id")
    den = await get_room_den(db, room_id)
    if not den:
        return {"ok": False, "reason": "no_den"}

    org = await db.get_organization(HUTT_ORG_CODE)
    membership = await db.get_membership(char["id"], org["id"]) if org else None
    if not membership or int(membership.get("rank_level") or 0) < DEN_ESTABLISH_MIN_RANK:
        return {"ok": False, "reason": "rank"}
    if not org or den.get("org_id") != org["id"]:
        return {"ok": False, "reason": "not_yours"}

    try:
        await db._db.execute(  # noqa: SLF001
            "DELETE FROM sabacc_dens WHERE room_id = ?", (room_id,))
        await db._db.commit()  # noqa: SLF001
    except Exception:
        log.warning("[dens] abandon failed for room %s", room_id, exc_info=True)
        return {"ok": False, "reason": "write_failed"}
    return {"ok": True}
