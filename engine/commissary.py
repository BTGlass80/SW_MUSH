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
         "desc": "Short-range biometric tracker. +1D to Search for targets."},
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
        await db.add_to_inventory(char["id"], {
            "key":            item["key"],
            "name":           item["name"],
            "slot":           item["slot"],
            "description":    item.get("desc", ""),
            "faction_issued": True,
            "faction_code":   str(faction_code).strip().lower(),
            "commissary":     True,
        })
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
