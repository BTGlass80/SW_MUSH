# -*- coding: utf-8 -*-
"""
engine/commissary.py — Drop 3 A4 (commissary): the faction requisition sink.

The Republic/CIS officer (and the Hutt runner, the Guild journeyman) "serve the
war" — and the *spending* side of that loop is **requisition**: a sworn member
buys rank-appropriate gear from their faction commissary for credits, at a
requisition rate below the open market. It is the `commissary_purchase` sink the
economy audit (report A4) calls for, sitting on the existing org-membership +
rank machinery — no new schema.

Design:
  - Stock is per-faction and rank-gated (an item carries a ``min_rank``). The
    catalog is the CW factions' own rank-0 / rank-1 issue gear, so it is
    **era-clean by construction** (keys match ``EQUIPMENT_CATALOG`` so a bought
    item behaves identically to an issued one).
  - The **Jedi Order has no commissary** — the Order is austere and issues, it
    does not sell. (Faithful to the report's Jedi-austerity thesis.)
  - Access opens to sworn members (rank >= ``COMMISSARY_MIN_RANK``); fresh
    recruits (rank 0) get their issue gear free on join and requisition later.
  - A purchase debits the cost through the ledger chokepoint as
    ``commissary_purchase`` (a sink), then grants the item to inventory.
    Refund-safe: the cost is taken before the grant, and a
    ``commissary_purchase_refund`` fires if the grant fails.

There is **no schema change**: the commissary reads org membership (existing),
debits credits (existing ledger), and grants to inventory (existing).
"""

import logging

from engine.tunables import get_tunable

log = logging.getLogger(__name__)

# Per-faction commissary stock. Era-clean CW gear only; keys match
# EQUIPMENT_CATALOG (engine/organizations.py) so a bought item is identical to
# an issued one. Jedi Order intentionally absent (austere — issues, never
# sells). Costs are first-cut requisition rates (a discount vs open market is
# implicit); tunable against live @economy data.
COMMISSARY_STOCK = {
    "republic": [
        {"key": "republic_uniform",     "name": "Republic Service Uniform", "slot": "armor",  "cost":  150, "min_rank": 0,
         "desc": "Off-white Republic-issue tunic and trousers."},
        {"key": "dc17_pistol",          "name": "DC-17 Hand Blaster",       "slot": "weapon", "cost":  500, "min_rank": 0,
         "desc": "Republic sidearm. 4D damage."},
        {"key": "dc15_blaster_rifle",   "name": "DC-15A Blaster Rifle",     "slot": "weapon", "cost": 1200, "min_rank": 1,
         "desc": "Standard clone trooper rifle. 5D damage."},
        {"key": "republic_light_armor", "name": "Republic Combat Plate",    "slot": "armor",  "cost":  900, "min_rank": 1,
         "desc": "Clone trooper armor segments. +1D+2 physical soak."},
    ],
    "cis": [
        {"key": "encrypted_comlink",    "name": "Encrypted Comlink",        "slot": "misc",   "cost":  150, "min_rank": 0,
         "desc": "Coded comlink. Secure channel access."},
        {"key": "blaster_pistol",       "name": "DH-17 Blaster Pistol",     "slot": "weapon", "cost":  450, "min_rank": 1,
         "desc": "Reliable sidearm. 4D damage."},
        {"key": "civilian_gear",        "name": "Civilian Operative Kit",   "slot": "misc",   "cost":  200, "min_rank": 1,
         "desc": "Plain clothes, forged ID chip, comm earpiece."},
    ],
    "hutt_cartel": [
        {"key": "blaster_pistol",       "name": "DH-17 Blaster Pistol",     "slot": "weapon", "cost":  450, "min_rank": 0,
         "desc": "Reliable sidearm. 4D damage."},
        {"key": "heavy_blaster_pistol", "name": "Heavy Blaster Pistol",     "slot": "weapon", "cost":  700, "min_rank": 1,
         "desc": "Compact stopping power. 5D damage."},
        {"key": "smuggler_vest",        "name": "Smuggler's Vest",          "slot": "armor",  "cost":  600, "min_rank": 1,
         "desc": "Concealed plating. +1D physical soak; +2 storage."},
    ],
    "bounty_hunters_guild": [
        {"key": "binder_cuffs",         "name": "Binder Cuffs",             "slot": "misc",   "cost":  200, "min_rank": 0,
         "desc": "Durasteel restraints. Required for live capture."},
        {"key": "guild_license",        "name": "Guild License",            "slot": "misc",   "cost":  100, "min_rank": 0,
         "desc": "Official Bounty Hunters' Guild authorization."},
        {"key": "tracking_fob",         "name": "Tracking Fob",             "slot": "misc",   "cost":  350, "min_rank": 1,
         "desc": "Short-range biometric tracker. +1D to Search for targets.",
         "skill_bonus": {"skill": "search", "bonus": "+1D"}},
    ],
}


# ── Pure helpers ─────────────────────────────────────────────────────────────
def faction_has_commissary(faction_code) -> bool:
    """True if `faction_code` maintains a commissary (has stock)."""
    return bool(COMMISSARY_STOCK.get(str(faction_code or "").strip().lower()))


def _stock(faction_code):
    return COMMISSARY_STOCK.get(str(faction_code or "").strip().lower(), [])


def commissary_item(faction_code, key):
    """Return the stock entry for `key` in `faction_code`'s commissary, or None."""
    k = str(key or "").strip().lower()
    for it in _stock(faction_code):
        if it["key"] == k:
            return it
    return None


def commissary_stock_for(faction_code, rank_level):
    """Rank-appropriate stock for a member: items with ``min_rank <= rank_level``."""
    try:
        rl = int(rank_level or 0)
    except (TypeError, ValueError):
        rl = 0
    return [it for it in _stock(faction_code) if it["min_rank"] <= rl]


def commissary_vendor_payload(faction_code, rank_level, balance=0) -> dict:
    """Web panel payload for the shop_state mode:'vendor' push.

    Returns a dict that ``send_json("shop_state", ...)`` can emit directly.
    Reuses ``commissary_status_lines`` / ``_stock`` for the item+mark
    derivation — no mark logic is duplicated here. Header strings from
    ``commissary_status_lines`` are stripped; only the item dicts are kept.

    Shape::

        {
            "mode": "vendor",
            "vendor_kind": "commissary",
            "faction_code": <str, normalised lower>,
            "rank_level": <int>,
            "balance": <int>,
            "items": [
                {"key", "name", "slot", "cost", "min_rank", "desc", "mark"},
                ...
            ]
        }

    If the faction has no commissary, ``items`` is an empty list so the panel
    can show a "no commissary" state without extra branches on the caller.
    """
    fc = str(faction_code or "").strip().lower()
    try:
        rl = int(rank_level or 0)
    except (TypeError, ValueError):
        rl = 0
    try:
        bal = int(balance or 0)
    except (TypeError, ValueError):
        bal = 0
    rows = commissary_status_lines(fc, rl, bal)
    items = [r for r in rows if not isinstance(r, str)]
    return {
        "mode": "vendor",
        "vendor_kind": "commissary",
        "faction_code": fc,
        "rank_level": rl,
        "balance": bal,
        "items": items,
    }


def commissary_status_lines(faction_code, rank_level, balance=0):
    """Plain-text status block for the +commissary command (the command styles)."""
    lines = []
    if not faction_has_commissary(faction_code):
        lines.append("  Your faction does not maintain a commissary.")
        return lines
    try:
        rl = int(rank_level or 0)
    except (TypeError, ValueError):
        rl = 0
    try:
        bal = int(balance or 0)
    except (TypeError, ValueError):
        bal = 0
    lines.append("  Requisition  (+commissary buy <key>):")
    for it in _stock(faction_code):
        if it["min_rank"] > rl:
            mark = "rank"
        elif bal >= it["cost"]:
            mark = "buy"
        else:
            mark = "short"
        lines.append({"key": it["key"], "name": it["name"], "cost": it["cost"],
                      "slot": it["slot"], "desc": it.get("desc", ""),
                      "min_rank": it["min_rank"], "mark": mark})
    return lines


# ── The sink: requisition an item ────────────────────────────────────────────
async def purchase_commissary(db, char: dict, faction_code, rank_level, key) -> dict:
    """Requisition the commissary item `key` for `char`.

    Debits the cost through the ledger chokepoint as ``commissary_purchase`` (a
    sink), then grants the item to inventory. Refund-safe: the cost is taken
    before the grant, and a ``commissary_purchase_refund`` fires if the grant
    fails. Returns a result dict the command renders.
    """
    if not faction_has_commissary(faction_code):
        return {"ok": False, "reason": "no_commissary"}
    try:
        rl = int(rank_level or 0)
    except (TypeError, ValueError):
        rl = 0

    item = commissary_item(faction_code, key)
    if item is None:
        return {"ok": False, "reason": "unknown"}
    if item["min_rank"] > rl:
        return {"ok": False, "reason": "rank_locked",
                "min_rank": item["min_rank"], "name": item["name"]}

    cost = int(item["cost"])
    try:
        balance = int(char.get("credits") or 0)
    except (TypeError, ValueError):
        balance = 0
    if balance < cost:
        return {"ok": False, "reason": "insufficient", "cost": cost,
                "short": cost - balance, "name": item["name"]}

    # Debit FIRST (the sink), then grant; refund on failure so a failed
    # requisition never eats credits.
    try:
        char["credits"] = await db.adjust_credits(
            char["id"], -cost, "commissary_purchase")
    except Exception:
        log.warning("[commissary] debit failed for char %s", char.get("id"),
                    exc_info=True)
        return {"ok": False, "reason": "charge_failed"}

    try:
        # H1 fix (2026-06-17): prefer registry name/slot for weapon/armor
        # keys so find_carried_gear can match by display name after purchase.
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()
        reg_entry = wr.get(item["key"])
        if reg_entry is not None:
            resolved_name = reg_entry.name
            resolved_slot = "armor" if reg_entry.is_armor else "weapon"
        else:
            resolved_name = item["name"]
            resolved_slot = item["slot"]

        # Build the inventory payload; conditionally pass skill_bonus
        # when the stock entry carries one (generic passthrough —
        # future tools need only the data field, not code changes).
        inv_item = {
            "key":            item["key"],
            "name":           resolved_name,
            "slot":           resolved_slot,
            "description":    item.get("desc", ""),
            "faction_issued": True,
            "faction_code":   str(faction_code).strip().lower(),
            "commissary":     True,
            # ECON.commissary_sellback (2026-06-13): the item carries its
            # own requisition cost so the sellback refund (<=50%) is
            # computable from the instance, robust to later stock-price
            # changes (same idea as crafted items carrying `quality`).
            "requisition_cost": cost,
        }
        sb = item.get("skill_bonus")
        if isinstance(sb, dict):
            inv_item["skill_bonus"] = dict(sb)
        await db.add_to_inventory(char["id"], inv_item)
    except Exception:
        log.warning("[commissary] grant failed for char %s; refunding",
                    char.get("id"), exc_info=True)
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], cost, "commissary_purchase_refund")
        except Exception:
            log.error("[commissary] REFUND FAILED for char %s", char.get("id"),
                      exc_info=True)
        return {"ok": False, "reason": "grant_failed"}

    return {"ok": True, "key": item["key"], "name": item["name"], "cost": cost}


# ── Sellback (ECON.commissary_sellback, 2026-06-13) ──────────────────
#
# Faction-issued / commissary gear cannot be sold to ordinary vendors
# (npc_refuses_buyback now refuses faction_issued — closes the buy-at-
# discount / resell-on-open-market laundering loop). It sells back ONLY
# here, to the issuing faction's commissary, as a PARTIAL refund at
# COMMISSARY_SELLBACK_RATE of the item's requisition cost. The refund is
# BY CONSTRUCTION smaller than the commissary_purchase sink that created
# the item, so the buy->sellback round trip is a NET LOSS — no laundering.

COMMISSARY_SELLBACK_RATE = 0.50  # refund fraction of requisition cost


def _refund_amount(item: dict, faction_code) -> int:
    """The sellback refund for a commissary item: COMMISSARY_SELLBACK_RATE
    of its requisition cost. Prefer the cost stamped on the item at
    purchase; fall back to the current stock price for legacy items that
    predate the stamped field. Returns 0 if neither is available."""
    cost = item.get("requisition_cost")
    if cost is None:
        stock = commissary_item(faction_code, item.get("key"))
        cost = stock["cost"] if stock else 0
    try:
        rate = get_tunable("commissary.sellback_rate", COMMISSARY_SELLBACK_RATE)
        return max(0, int(int(cost) * rate))
    except (TypeError, ValueError):
        return 0


async def sell_commissary(db, char: dict, faction_code, key) -> dict:
    """Sell a faction-issued commissary item back to the issuing
    commissary for a partial refund. Returns a result dict the command
    renders.

    Validation: the item must be in inventory, be faction_issued, and
    belong to THIS faction's channel (you sell Republic gear to the
    Republic commissary, not the Hutts'). Refund-safe: the item is
    removed FIRST, then the refund credited — so a credit can never be
    paid for an item the player keeps."""
    fc = str(faction_code or "").strip().lower()
    if not faction_has_commissary(fc):
        return {"ok": False, "reason": "no_commissary"}

    # Find the matching faction-issued item in inventory.
    try:
        inv = await db.get_inventory(char["id"])
    except Exception:
        log.warning("[commissary] sell: get_inventory failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "lookup_failed"}

    match = None
    for it in (inv or []):
        if not isinstance(it, dict):
            continue
        if it.get("key") == key and it.get("faction_issued"):
            match = it
            break
    if match is None:
        return {"ok": False, "reason": "not_owned"}

    # Channel-bound: only the issuing faction buys it back.
    item_fac = str(match.get("faction_code") or "").strip().lower()
    if item_fac and item_fac != fc:
        return {"ok": False, "reason": "wrong_channel",
                "item_faction": item_fac, "name": match.get("name", key)}

    refund = _refund_amount(match, fc)

    # Remove FIRST (refund-safe), then credit.
    try:
        removed = await db.remove_from_inventory(char["id"], key)
    except Exception:
        log.warning("[commissary] sell: remove failed for char %s",
                    char.get("id"), exc_info=True)
        return {"ok": False, "reason": "remove_failed"}
    if not removed:
        return {"ok": False, "reason": "not_owned"}

    if refund > 0:
        try:
            char["credits"] = await db.adjust_credits(
                char["id"], refund, "commissary_sellback")
        except Exception:
            # Credit failed AFTER removing the item — restore it so the
            # player isn't out both item and refund.
            log.error("[commissary] sellback credit failed for char %s; "
                      "restoring item", char.get("id"), exc_info=True)
            try:
                await db.add_to_inventory(char["id"], match)
            except Exception:
                log.error("[commissary] RESTORE FAILED for char %s",
                          char.get("id"), exc_info=True)
            return {"ok": False, "reason": "credit_failed"}

    return {"ok": True, "key": key, "name": match.get("name", key),
            "refund": refund}
