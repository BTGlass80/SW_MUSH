# -*- coding: utf-8 -*-
"""
engine/vendor_droids.py — Player Shop / Vendor Droid System for SW_MUSH.

Vendor droids are player-owned objects (type='vendor_droid') placed in
public rooms. Owners stock items; buyers browse and purchase.

All droid state lives in the objects.data JSON blob:
{
  "tier": 1,                  # 1=GN-4, 2=GN-7, 3=GN-12
  "shop_name": "Voss Arms",   # Display name
  "shop_desc": "...",         # Tagline
  "inventory": [              # Stocked item slots
    {
      "slot": 0,
      "item_key": "blaster_pistol",
      "item_name": "BlasTech DL-18",
      "quality": 78,
      "quantity": 3,
      "price": 450,
      "crafter": "Kaylee Voss",  # optional
    }, ...
  ],
  "escrow_credits": 0,        # Accumulated sale revenue (not yet collected)
  "buy_orders": [],           # Tier 3 only
  "last_sale_ts": 0.0,        # Unix timestamp of last sale
  "last_owner_ts": 0.0,       # Unix timestamp of last owner interaction
  "total_sales": 0,
}

Drops delivered:
  Drop 1  Core lifecycle (create/place/recall), browse
  Drop 2  Stock/unstock/price/collect/sales + buy-from-droid
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

import yaml

log = logging.getLogger(__name__)

# ── Tier definitions ──────────────────────────────────────────────────────────

_TIERS: dict = {}

def _load_tiers() -> dict:
    global _TIERS
    if _TIERS:
        return _TIERS
    try:
        yaml_path = Path(__file__).parent.parent / "data" / "vendor_droids.yaml"
        with open(yaml_path, "r", encoding="utf-8") as f:
            _TIERS = yaml.safe_load(f) or {}
    except Exception as e:
        log.warning("[shops] Could not load vendor_droids.yaml: %s", e)
        # Inline fallback
        _TIERS = {
            "gn4":  {"name": "GN-4 Vendor Droid",    "tier": 1, "cost": 2000,
                     "slots": 10, "listing_fee_pct": 2.0, "bargain_dice": 0,
                     "bargain_pips": 0, "buy_orders": False},
            "gn7":  {"name": "GN-7 Merchant Droid",   "tier": 2, "cost": 5000,
                     "slots": 25, "listing_fee_pct": 1.5, "bargain_dice": 2,
                     "bargain_pips": 0, "buy_orders": False},
            "gn12": {"name": "GN-12 Commerce Droid",  "tier": 3, "cost": 12000,
                     "slots": 50, "listing_fee_pct": 1.0, "bargain_dice": 3,
                     "bargain_pips": 1, "buy_orders": True},
        }
    return _TIERS


def get_tier(tier_key: str) -> Optional[dict]:
    tiers = _load_tiers()
    return tiers.get(tier_key.lower())


def get_tier_by_number(tier_num: int) -> Optional[tuple[str, dict]]:
    for key, t in _load_tiers().items():
        if t.get("tier") == tier_num:
            return key, t
    return None


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_data(obj: dict) -> dict:
    raw = obj.get("data", "{}")
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            log.warning("_load_data: unhandled exception", exc_info=True)
            return {}
    return raw or {}


def _dump_data(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False)


# ── Placement rules ───────────────────────────────────────────────────────────

MAX_DROIDS_PER_ROOM = 2
MAX_DROIDS_PER_OWNER = 3
PRICE_FLOOR_PCT = 0.5     # Cannot list below 50% of NPC buy-back value

FORBIDDEN_ROOM_TYPES = frozenset({
    "ship_interior", "tutorial", "wilderness", "space",
})


async def check_placement_allowed(room_id: int, owner_id: int, db) -> tuple[bool, str]:
    """Return (ok, error_msg). Check room and owner limits."""
    # Shopfront rooms bypass the per-room cap (the room IS the shop)
    # and have their own droid_slots limit stored in room properties.
    _is_shopfront = False
    _shopfront_slots = MAX_DROIDS_PER_ROOM
    try:
        _room = await db.get_room(room_id)
        if _room:
            from engine.housing import is_shopfront_room_props
            _props_raw = _room.get("properties", "{}")
            _is_shopfront = is_shopfront_room_props(_props_raw)
            if _is_shopfront:
                import json as _j
                _props = _j.loads(_props_raw) if isinstance(_props_raw, str) else (_props_raw or {})
                _shopfront_slots = _props.get("droid_slots", MAX_DROIDS_PER_ROOM)
    except Exception:
        log.warning("check_placement_allowed: unhandled exception", exc_info=True)
        pass

    # Room droid count — shopfront uses its own slot count
    existing = await db.get_objects_in_room(room_id, "vendor_droid")
    _room_limit = _shopfront_slots if _is_shopfront else MAX_DROIDS_PER_ROOM
    if len(existing) >= _room_limit:
        return False, f"This room already has {_room_limit} vendor droids (maximum)."

    # Room type check
    room = await db.get_room(room_id)
    if room:
        zone_id = room.get("zone_id")
        if zone_id:
            try:
                zone = await db.get_zone(zone_id)
                if zone:
                    props = zone.get("properties", "{}")
                    if isinstance(props, str):
                        props = json.loads(props) if props else {}
                    rtype = props.get("type", "")
                    if rtype in FORBIDDEN_ROOM_TYPES:
                        return False, "Vendor droids cannot be placed in this area."
                    if props.get("no_commerce"):
                        return False, "Commerce is not permitted in this area."
            except Exception:
                log.warning("check_placement_allowed: unhandled exception", exc_info=True)
                pass

    # Owner limit — use effective cap (base + 1 per shopfront owned)
    owner_droids = await db.get_objects_owned_by(owner_id, "vendor_droid")
    placed = [d for d in owner_droids if d.get("room_id")]
    try:
        from engine.housing import get_effective_droid_cap
        sf_rows = await db.fetchall(
            "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 4",
            (owner_id,),
        )
        sf_count = sf_rows[0]["cnt"] if sf_rows else 0
        # get_effective_droid_cap needs a char dict; build minimal one
        _eff_cap = get_effective_droid_cap({"id": owner_id}, sf_count)
    except Exception:
        _eff_cap = MAX_DROIDS_PER_OWNER
    if len(placed) >= _eff_cap:
        return False, (
            f"You already have {_eff_cap} placed vendor droids (maximum). "
            f"Own a shopfront to increase this limit."
        )

    return True, ""


# ── Lifecycle: purchase ───────────────────────────────────────────────────────

async def purchase_droid(char: dict, tier_key: str, db) -> tuple[bool, str]:
    """
    Buy a vendor droid and add it to owner's inventory (room_id=NULL).
    Deducts purchase cost from character credits.
    """
    tier = get_tier(tier_key)
    if not tier:
        return False, f"Unknown droid tier '{tier_key}'. Valid: gn4, gn7, gn12."

    cost = tier["cost"]
    if char.get("credits", 0) < cost:
        return False, (
            f"Insufficient credits. A {tier['name']} costs {cost:,} credits "
            f"(you have {char.get('credits', 0):,})."
        )

    # Check owner limit (including unplaced) — effective cap includes shopfront bonus
    all_droids = await db.get_objects_owned_by(char["id"], "vendor_droid")
    try:
        from engine.housing import get_effective_droid_cap
        sf_rows = await db.fetchall(
            "SELECT COUNT(*) as cnt FROM player_housing WHERE char_id = ? AND tier = 4",
            (char["id"],),
        )
        sf_count = sf_rows[0]["cnt"] if sf_rows else 0
        _eff_cap = get_effective_droid_cap(char, sf_count)
    except Exception:
        _eff_cap = MAX_DROIDS_PER_OWNER
    if len(all_droids) >= _eff_cap:
        return False, (
            f"You already own {_eff_cap} vendor droids (maximum). "
            f"Own a shopfront to increase this limit."
        )

    # Deduct credits
    new_credits = char["credits"] - cost
    char["credits"] = new_credits
    await db.save_character(char["id"], credits=new_credits)

    # Create droid object (room_id=None = in inventory)
    initial_data = {
        "tier":           tier["tier"],
        "tier_key":       tier_key,
        "shop_name":      f"{char['name']}'s Shop",
        "shop_desc":      "",
        "inventory":      [],
        "escrow_credits": 0,
        "buy_orders":     [],
        "last_sale_ts":   0.0,
        "last_owner_ts":  time.time(),
        "total_sales":    0,
    }
    droid_id = await db.create_object(
        type="vendor_droid",
        name=tier["name"],
        owner_id=char["id"],
        room_id=None,
        description=tier.get("description", ""),
        data=_dump_data(initial_data),
    )

    return True, (
        f"You purchase a {tier['name']} for {cost:,} credits. "
        f"(Balance: {new_credits:,} cr)\n"
        f"  Use \033[1;33mshop place\033[0m to deploy it in the current room.\n"
        f"  Use \033[1;33mshop name <text>\033[0m to give it a shop name."
    )


# ── Lifecycle: place / recall ─────────────────────────────────────────────────

async def place_droid(char: dict, droid_id: int, room_id: int,
                       db) -> tuple[bool, str]:
    """Move droid from inventory to the current room."""
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."
    if obj["room_id"]:
        return False, "That droid is already placed. Recall it first."

    ok, err = await check_placement_allowed(room_id, char["id"], db)
    if not ok:
        return False, err

    # Touch last_owner_ts
    data = _load_data(obj)
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, room_id=room_id, data=_dump_data(data))

    data_name = data.get("shop_name", obj["name"])
    return True, (
        f"You deploy \033[1;37m{data_name}\033[0m here. "
        f"Customers can now browse with \033[1;33mbrowse\033[0m."
    )


async def recall_droid(char: dict, droid_id: int, db) -> tuple[bool, str]:
    """Move droid from room back to owner inventory (room_id=NULL)."""
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."
    if not obj["room_id"]:
        return False, "That droid is not currently placed."

    data = _load_data(obj)
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, room_id=None, data=_dump_data(data))

    shop_name = data.get("shop_name", obj["name"])
    return True, f"\033[1;37m{shop_name}\033[0m has been recalled to your inventory."


# ── Shop configuration ────────────────────────────────────────────────────────

async def set_shop_name(char: dict, droid_id: int, name: str,
                         db) -> tuple[bool, str]:
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."
    name = name.strip()[:50]
    if not name:
        return False, "Shop name cannot be empty."
    data = _load_data(obj)
    data["shop_name"] = name
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))
    return True, f"Shop name set to: \033[1;37m{name}\033[0m"


async def set_shop_desc(char: dict, droid_id: int, desc: str,
                         db) -> tuple[bool, str]:
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."
    desc = desc.strip()[:120]
    data = _load_data(obj)
    data["shop_desc"] = desc
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))
    return True, "Shop description updated."


# ── Drop 2: Inventory management ─────────────────────────────────────────────

async def stock_droid(char: dict, droid_id: int,
                       item_key: str, item_name: str, quality: int,
                       price: int, quantity: int, crafter: str,
                       db, source_type: str = "item") -> tuple[bool, str]:
    """
    Move item(s) from character inventory into droid stock.
    source_type: "equipment", "resource", or "item" — controls how
    the item is removed from the character.
    Faction-issued items are blocked.
    """
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."

    data   = _load_data(obj)
    tier   = get_tier(data.get("tier_key", "gn4")) or {}
    slots  = tier.get("slots", 10)
    inv    = data.get("inventory", [])

    if price < 1:
        return False, "Price must be at least 1 credit."
    if quantity < 1:
        return False, "Quantity must be at least 1."

    # Faction-issued items blocked
    if _is_faction_issued(char, item_key):
        return False, "Faction-issued equipment cannot be sold in player shops."

    # ── Remove the item from character BEFORE adding to droid ──
    try:
        if source_type == "equipment":
            # Unequip the weapon
            char["equipment"] = "{}"
            await db.save_character(char["id"], equipment="{}")
            # Equipment is always qty 1
            quantity = 1
        elif source_type == "resource":
            # Decrement resource stack in inventory JSON
            char_inv = char.get("inventory", "{}")
            if isinstance(char_inv, str):
                char_inv = json.loads(char_inv) if char_inv else {}
            resources = char_inv.get("resources", [])
            stack = next((r for r in resources if r.get("type") == item_key), None)
            if not stack:
                return False, f"'{item_name}' no longer in your inventory."
            have = int(stack.get("quantity", 1))
            if quantity > have:
                quantity = have  # Cap at what they actually have
            stack["quantity"] = have - quantity
            if stack["quantity"] <= 0:
                char_inv["resources"] = [r for r in resources if r is not stack]
            char["inventory"] = json.dumps(char_inv)
            await db.save_character(char["id"], inventory=char["inventory"])
        else:  # "item"
            # Remove from items list in inventory JSON
            char_inv = char.get("inventory", "{}")
            if isinstance(char_inv, str):
                char_inv = json.loads(char_inv) if char_inv else {}
            items = char_inv.get("items", [])
            found = False
            new_items = []
            for it in items:
                if not found and it.get("key", it.get("name", "")) == item_key:
                    found = True
                    continue  # Remove this one
                new_items.append(it)
            if not found:
                return False, f"'{item_name}' no longer in your inventory."
            char_inv["items"] = new_items
            char["inventory"] = json.dumps(char_inv)
            await db.save_character(char["id"], inventory=char["inventory"])
            quantity = 1  # General items are 1-at-a-time
    except Exception as e:
        log.warning("[shops] Failed to remove item from char inventory: %s", e)
        return False, "Failed to remove item from your inventory."

    # Check slot limit — try to merge into existing slot first
    for slot in inv:
        if (slot["item_key"] == item_key and
                abs(slot.get("quality", 0) - quality) <= 5 and
                slot["price"] == price):
            slot["quantity"] += quantity
            data["inventory"] = inv
            data["last_owner_ts"] = time.time()
            await db.update_object(droid_id, data=_dump_data(data))
            return True, (
                f"Added {quantity}x {item_name} to existing slot "
                f"(now {slot['quantity']}x at {price:,}cr each)."
            )

    # New slot
    if len(inv) >= slots:
        return False, (
            f"Droid inventory full ({slots} slots). "
            f"Unstock something first or upgrade to a higher tier."
        )

    new_slot = {
        "slot":      len(inv),
        "item_key":  item_key,
        "item_name": item_name,
        "quality":   quality,
        "quantity":  quantity,
        "price":     price,
        "crafter":   crafter,
    }
    inv.append(new_slot)
    # Re-number slots
    for i, s in enumerate(inv):
        s["slot"] = i + 1

    data["inventory"] = inv
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))
    return True, (
        f"Stocked {quantity}x \033[1;37m{item_name}\033[0m "
        f"(quality {quality}) at \033[1;33m{price:,}cr\033[0m each."
    )


async def unstock_droid(char: dict, droid_id: int,
                         slot_num: int, quantity: int,
                         db) -> tuple[bool, str]:
    """Remove item(s) from a droid slot back to owner's inventory."""
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."

    data = _load_data(obj)
    inv  = data.get("inventory", [])

    slot = next((s for s in inv if s.get("slot") == slot_num), None)
    if not slot:
        return False, f"No item in slot {slot_num}."

    qty_to_remove = min(quantity, slot["quantity"])
    item_key  = slot.get("item_key", "")
    item_name = slot.get("item_name", item_key)
    quality   = slot.get("quality", 50)
    crafter   = slot.get("crafter", "")

    # ── Return item(s) to character inventory ──
    try:
        char_inv = char.get("inventory", "{}")
        if isinstance(char_inv, str):
            char_inv = json.loads(char_inv) if char_inv else {}
        if not isinstance(char_inv, dict):
            char_inv = {}

        # Determine if this is a resource (check crafting RESOURCE_TYPES)
        is_resource = False
        try:
            from engine.crafting import RESOURCE_TYPES
            if hasattr(RESOURCE_TYPES, "keys"):
                is_resource = item_key in RESOURCE_TYPES
            elif isinstance(RESOURCE_TYPES, (set, frozenset, list)):
                is_resource = item_key in RESOURCE_TYPES
        except Exception:
            log.warning("unstock_droid: unhandled exception", exc_info=True)
            pass

        if is_resource:
            resources = char_inv.get("resources", [])
            # Try to merge into existing stack
            existing = next((r for r in resources if r.get("type") == item_key), None)
            if existing:
                existing["quantity"] = int(existing.get("quantity", 0)) + qty_to_remove
            else:
                resources.append({
                    "type": item_key,
                    "quality": quality,
                    "quantity": qty_to_remove,
                })
            char_inv["resources"] = resources
        else:
            items = char_inv.get("items", [])
            for _ in range(qty_to_remove):
                items.append({
                    "key":     item_key,
                    "name":    item_name,
                    "quality": quality,
                    "crafter": crafter,
                })
            char_inv["items"] = items

        char["inventory"] = json.dumps(char_inv)
        await db.save_character(char["id"], inventory=char["inventory"])
    except Exception as e:
        log.warning("[shops] Failed to return item to char inventory: %s", e)
        return False, "Failed to return item to your inventory."

    # ── Update droid inventory ──
    slot["quantity"] -= qty_to_remove
    if slot["quantity"] <= 0:
        inv = [s for s in inv if s.get("slot") != slot_num]
        for i, s in enumerate(inv):
            s["slot"] = i + 1

    data["inventory"] = inv
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))
    return True, (
        f"Removed {qty_to_remove}x {item_name} from slot {slot_num}. "
        f"Items returned to your inventory."
    )


async def set_slot_price(char: dict, droid_id: int,
                          slot_num: int, new_price: int,
                          db) -> tuple[bool, str]:
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."
    if new_price < 1:
        return False, "Price must be at least 1 credit."

    data = _load_data(obj)
    inv  = data.get("inventory", [])
    slot = next((s for s in inv if s.get("slot") == slot_num), None)
    if not slot:
        return False, f"No item in slot {slot_num}."

    slot["price"] = new_price
    data["inventory"] = inv
    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))
    return True, (
        f"Slot {slot_num} ({slot['item_name']}) price updated to "
        f"\033[1;33m{new_price:,}cr\033[0m."
    )


# ── Drop 2: Buying from a droid ───────────────────────────────────────────────

async def buy_from_droid(buyer: dict, droid_id: int,
                          item_arg: str, db,
                          session_mgr=None) -> tuple[bool, str]:
    """
    Buyer purchases an item from a vendor droid.

    item_arg: slot number (str) or partial item name.
    Applies Bargain check for Tier 2+ droids.
    Deducts credits, pays escrow, logs transaction.
    """
    from server import ansi

    obj = await db.get_object(droid_id)
    if not obj or not obj.get("room_id"):
        return False, "That vendor droid is not available."

    # Same-owner restriction
    if obj["owner_id"] == buyer["id"]:
        return False, "You cannot buy from your own vendor droid."

    data = _load_data(obj)
    inv  = data.get("inventory", [])
    if not inv:
        return False, "That vendor droid has no items in stock."

    # Resolve target slot
    slot = None
    if item_arg.isdigit():
        slot = next((s for s in inv if s.get("slot") == int(item_arg)), None)
    if slot is None:
        arg_lower = item_arg.lower()
        slot = next(
            (s for s in inv if arg_lower in s.get("item_name", "").lower()),
            None,
        )
    if not slot:
        return False, (
            f"No item matching '{item_arg}' in stock. "
            f"Use \033[1;33mbrowse\033[0m to see available items."
        )

    base_price = slot["price"]
    final_price = base_price

    # ── Faction shop modifier (S39) ───────────────────────────────────────
    # If the shop owner aligns with one of the canonical factions, look up
    # the buyer's reputation with that faction and apply the corresponding
    # tier modifier. Hostile rep blocks the purchase outright; friendly
    # rep gives a discount; unfriendly rep imposes a markup.
    #
    # The seller's stored faction_id is normalized through this map so a
    # vendor whose owner sits under a long-form name still resolves to a
    # canonical code. Codes (architecture v38 §6.5):
    #   GCW: "empire", "rebel", "hutt", "bh_guild"
    #   CW (B.1.a, Apr 29 2026): "republic", "cis", "jedi_order",
    #                            "hutt_cartel", "bounty_hunters_guild"
    #
    # Note: "independent" is filtered out below by the
    # `seller_faction_code != "independent"` guard, so it's not in this
    # map (no shop modifier ever applies for an independent seller).
    _FACTION_NAME_MAP = {
        # ── GCW ──
        "empire":               "empire",
        "imperial":             "empire",
        "galactic empire":      "empire",
        "rebel":                "rebel",
        "rebellion":            "rebel",
        "rebel alliance":       "rebel",
        "hutt":                 "hutt",
        "hutts":                "hutt",
        "hutt cartel":          "hutt",
        "bh_guild":             "bh_guild",
        "bounty hunters guild": "bh_guild",
        "bounty hunters":       "bh_guild",
        # ── CW (B.1.a) ──
        "republic":             "republic",
        "galactic republic":    "republic",
        "cis":                  "cis",
        "confederacy":          "cis",
        "separatist":           "cis",
        "separatists":          "cis",
        "confederacy of independent systems": "cis",
        "jedi":                 "jedi_order",
        "jedi order":           "jedi_order",
        "hutt_cartel":          "hutt_cartel",
        "bounty_hunters_guild": "bounty_hunters_guild",
        "bounty hunters' guild": "bounty_hunters_guild",
    }
    faction_msg = ""
    seller_faction_raw = ""
    try:
        seller_char_for_faction = await db.get_character(obj["owner_id"])
        if seller_char_for_faction:
            seller_faction_raw = (
                seller_char_for_faction.get("faction_id", "") or ""
            ).strip().lower()
    except Exception:
        log.debug("[shops] faction owner lookup failed", exc_info=True)

    seller_faction_code = _FACTION_NAME_MAP.get(seller_faction_raw)
    if seller_faction_code and seller_faction_code != "independent":
        try:
            from engine.organizations import get_faction_shop_modifier
            allowed, modifier, tier_name = await get_faction_shop_modifier(
                buyer, seller_faction_code, db,
            )
            if not allowed:
                # Hostile rep — vendor refuses to serve.
                return False, (
                    f"The vendor refuses to serve you. "
                    f"({tier_name} with the {seller_faction_code} faction)"
                )
            if modifier:
                final_price = max(1, int(round(base_price * (1.0 + modifier))))
                pct = int(round(modifier * 100))
                if pct < 0:
                    faction_msg = (
                        f"\n  {ansi.DIM}Faction: "
                        f"{abs(pct)}% discount ({tier_name}).{ansi.RESET}"
                    )
                elif pct > 0:
                    faction_msg = (
                        f"\n  {ansi.DIM}Faction: "
                        f"{pct}% markup ({tier_name}).{ansi.RESET}"
                    )
        except Exception:
            log.debug("[shops] faction shop modifier failed", exc_info=True)

    # Bargain check for Tier 2+
    tier_key = data.get("tier_key", "gn4")
    tier     = get_tier(tier_key) or {}
    b_dice   = tier.get("bargain_dice", 0)
    b_pips   = tier.get("bargain_pips", 0)
    bargain_msg = ""

    if b_dice > 0 or b_pips > 0:
        try:
            from engine.skill_checks import resolve_bargain_check
            haggle = resolve_bargain_check(
                buyer, final_price,
                npc_bargain_dice=b_dice, npc_bargain_pips=b_pips,
                is_buying=True,
            )
            final_price = haggle["adjusted_price"]
            pct = haggle.get("price_modifier_pct", 0)
            if pct > 0:
                bargain_msg = (
                    f"\n  {ansi.DIM}Bargain: you negotiated a "
                    f"{pct}% discount.{ansi.RESET}"
                )
        except Exception as e:
            log.debug("[shops] Bargain check failed: %s", e)

    if buyer.get("credits", 0) < final_price:
        return False, (
            f"Insufficient credits. {slot['item_name']} costs "
            f"{final_price:,} credits (you have {buyer.get('credits',0):,})."
        )

    # Listing fee
    fee_pct   = tier.get("listing_fee_pct", 2.0) / 100.0
    fee       = max(1, int(final_price * fee_pct))
    net_payout = final_price - fee

    # Deduct buyer credits
    buyer["credits"] -= final_price
    await db.save_character(buyer["id"], credits=buyer["credits"])

    # ── Add purchased item to buyer's inventory ──
    try:
        buyer_inv = buyer.get("inventory", "{}")
        if isinstance(buyer_inv, str):
            buyer_inv = json.loads(buyer_inv) if buyer_inv else {}
        if not isinstance(buyer_inv, dict):
            buyer_inv = {}
        items = buyer_inv.get("items", [])
        items.append({
            "key":     slot.get("item_key", ""),
            "name":    slot["item_name"],
            "quality": slot.get("quality", 50),
            "crafter": slot.get("crafter", ""),
        })
        buyer_inv["items"] = items
        buyer["inventory"] = json.dumps(buyer_inv)
        await db.save_character(buyer["id"], inventory=buyer["inventory"])
    except Exception as e:
        log.warning("[shops] Failed to add item to buyer inventory: %s", e)
        # Credits already deducted — log but don't fail silently.
        # The transaction log will show the purchase for admin recovery.

    # Add to droid escrow
    data["escrow_credits"] = data.get("escrow_credits", 0) + net_payout
    data["last_sale_ts"]   = time.time()
    data["total_sales"]    = data.get("total_sales", 0) + 1

    # Remove/decrement slot
    slot["quantity"] -= 1
    if slot["quantity"] <= 0:
        data["inventory"] = [s for s in inv if s.get("slot") != slot["slot"]]
        for i, s in enumerate(data["inventory"]):
            s["slot"] = i + 1
    else:
        data["inventory"] = inv

    await db.update_object(droid_id, data=_dump_data(data))

    # Log transaction
    await db.log_shop_transaction(
        droid_id=droid_id,
        seller_id=obj["owner_id"],
        buyer_id=buyer["id"],
        item_key=slot.get("item_key", ""),
        item_name=slot["item_name"],
        quality=slot.get("quality", 0),
        quantity=1,
        unit_price=final_price,
        listing_fee=fee,
    )

    # Faction rep: seller gets crafting_sale rep for vendor droid sale
    try:
        seller_char = await db.get_character(obj["owner_id"])
        if seller_char:
            seller_faction = seller_char.get("faction_id", "independent")
            if seller_faction and seller_faction != "independent":
                from engine.organizations import adjust_rep
                await adjust_rep(
                    seller_char, seller_faction, db,
                    action_key="crafting_sale",
                    reason=f"Vendor sale: {slot['item_name']}",
                )
    except Exception:
        log.warning("[shops] crafting_sale rep hook failed", exc_info=True)

    shop_name = data.get("shop_name", obj["name"])
    crafter   = slot.get("crafter", "")
    crafter_str = f" (by {crafter})" if crafter else ""

    return True, (
        f"You purchase \033[1;37m{slot['item_name']}\033[0m"
        f"{crafter_str} from \033[1;36m{shop_name}\033[0m "
        f"for \033[1;33m{final_price:,}cr\033[0m. "
        f"(Balance: {buyer['credits']:,} cr)"
        f"{bargain_msg}{faction_msg}"
    )


async def collect_escrow(char: dict, droid_id: int, db) -> tuple[bool, str]:
    """Owner collects accumulated sale revenue from the droid."""
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."

    data    = _load_data(obj)
    escrow  = data.get("escrow_credits", 0)

    if escrow <= 0:
        return False, "No revenue to collect."

    char["credits"] += escrow
    await db.save_character(char["id"], credits=char["credits"])

    data["escrow_credits"] = 0
    data["last_owner_ts"]  = time.time()
    await db.update_object(droid_id, data=_dump_data(data))

    return True, (
        f"Collected \033[1;33m{escrow:,}cr\033[0m from "
        f"\033[1;37m{data.get('shop_name', obj['name'])}\033[0m. "
        f"(Balance: {char['credits']:,} cr)"
    )


# ── Browse formatting ─────────────────────────────────────────────────────────

def format_droid_list(droids: list, room_name: str = "") -> str:
    """Format a list of vendor droids for the 'browse' command (room level)."""
    from server import ansi
    lines = [
        f"\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37mVENDOR DROIDS{' — ' + room_name if room_name else ''}\033[0m",
        f"\033[1;36m──────────────────────────────────────────\033[0m",
    ]
    for obj in droids:
        data      = _load_data(obj)
        shop_name = data.get("shop_name", obj["name"])
        shop_desc = data.get("shop_desc", "")
        item_count = len(data.get("inventory", []))
        tier_key  = data.get("tier_key", "gn4")
        tier      = get_tier(tier_key) or {}
        tier_name = tier.get("name", obj["name"])
        lines.append(
            f"  \033[1;37m{shop_name}\033[0m  "
            f"\033[2m[{tier_name}]\033[0m  "
            f"{item_count} item{'s' if item_count != 1 else ''} in stock"
        )
        if shop_desc:
            lines.append(f"    \033[2m\"{shop_desc}\"\033[0m")
    lines += [
        f"\033[1;36m──────────────────────────────────────────\033[0m",
        f"  Type \033[1;33mbrowse <shop name>\033[0m to view inventory.",
        f"\033[1;36m══════════════════════════════════════════\033[0m",
    ]
    return "\n".join(lines)


def format_droid_inventory(obj: dict, viewer_id: int = None) -> str:
    """Format a single droid's inventory for 'browse <shop>'."""
    from server import ansi
    data      = _load_data(obj)
    shop_name = data.get("shop_name", obj["name"])
    shop_desc = data.get("shop_desc", "")
    inv       = data.get("inventory", [])
    tier_key  = data.get("tier_key", "gn4")
    tier      = get_tier(tier_key) or {}

    lines = [
        f"\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37m{shop_name}\033[0m",
    ]
    if shop_desc:
        lines.append(f"  \033[2m\"{shop_desc}\"\033[0m")
    lines.append(f"\033[1;36m──────────────────────────────────────────\033[0m")

    if not inv:
        lines.append("  \033[2mNo items currently in stock.\033[0m")
    else:
        for s in sorted(inv, key=lambda x: x.get("slot", 0)):
            q_bar   = _quality_color(s.get("quality", 0))
            crafter = f"  by {s['crafter']}" if s.get("crafter") else ""
            lines.append(
                f"  \033[1;37m[{s['slot']:2d}]\033[0m "
                f"{s['item_name']:<28} "
                f"{q_bar}  "
                f"\033[1;33m{s['price']:>6,}cr\033[0m  "
                f"x{s.get('quantity', 1)}"
                f"{crafter}"
            )
        if tier.get("bargain_dice", 0) > 0:
            lines.append(
                f"  \033[2m(Bargain skill active — you may negotiate a discount)\033[0m"
            )

    # Buy orders section (Tier 3)
    buy_order_lines = format_buy_orders(data.get("buy_orders", []))
    lines.extend(buy_order_lines)

    lines += [
        f"\033[1;36m──────────────────────────────────────────\033[0m",
        f"  \033[1;33mbuy <slot#> from {shop_name}\033[0m to purchase.",
    ]
    if any(o.get("active") for o in data.get("buy_orders", [])):
        lines.append(
            f"  \033[1;33msell <resource> to {shop_name}\033[0m to fill a buy order."
        )
    lines.append(f"\033[1;36m══════════════════════════════════════════\033[0m")
    return "\n".join(lines)


def _quality_color(quality: int) -> str:
    """Color-coded quality indicator."""
    from server import ansi
    if quality >= 85:
        return f"\033[1;32mQ:{quality:3d}\033[0m"
    if quality >= 65:
        return f"\033[1;33mQ:{quality:3d}\033[0m"
    if quality >= 40:
        return f"\033[33mQ:{quality:3d}\033[0m"
    return f"\033[2mQ:{quality:3d}\033[0m"


def format_shop_status(droids: list) -> str:
    """Format +shop owner dashboard."""
    from server import ansi
    if not droids:
        return (
            "  You don't own any vendor droids.\n"
            "  Visit a droid dealer and use \033[1;33mshop buy droid <tier>\033[0m."
        )
    lines = [
        f"\033[1;36m══════════════════════════════════════════\033[0m",
        f"  \033[1;37mYOUR VENDOR DROIDS\033[0m",
        f"\033[1;36m──────────────────────────────────────────\033[0m",
    ]
    for obj in droids:
        data      = _load_data(obj)
        shop_name = data.get("shop_name", obj["name"])
        escrow    = data.get("escrow_credits", 0)
        items     = len(data.get("inventory", []))
        placed    = "Placed" if obj.get("room_id") else "In inventory"
        sales     = data.get("total_sales", 0)
        lines += [
            f"  \033[1;37m{shop_name}\033[0m  [ID: {obj['id']}]",
            f"    Status: {placed}  Items: {items}  Sales: {sales}",
            f"    Revenue pending: \033[1;33m{escrow:,}cr\033[0m",
        ]
        if escrow > 0:
            lines.append(
                f"    → \033[1;33mshop collect {obj['id']}\033[0m to withdraw."
            )
    lines.append(f"\033[1;36m══════════════════════════════════════════\033[0m")
    return "\n".join(lines)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_faction_issued(char: dict, item_key: str) -> bool:
    """Return True if the item is faction-issued (cannot be sold)."""
    try:
        import json as _j
        inv = char.get("inventory", "{}")
        if isinstance(inv, str):
            inv = _j.loads(inv) if inv else {}
        items = inv.get("items", [])
        for item in items:
            if item.get("key") == item_key and item.get("faction_issued"):
                return True
    except Exception:
        log.warning("_is_faction_issued: unhandled exception", exc_info=True)
        pass
    return False


def find_droid_by_name(droids: list, name_arg: str) -> Optional[dict]:
    """Find a droid from a list by partial name match on shop_name."""
    name_lower = name_arg.lower()
    # Exact id match first
    if name_arg.isdigit():
        droid_id = int(name_arg)
        for d in droids:
            if d["id"] == droid_id:
                return d
    # Shop name prefix match
    for d in droids:
        data = _load_data(d)
        shop_name = data.get("shop_name", d["name"])
        if shop_name.lower().startswith(name_lower):
            return d
    # Partial match
    for d in droids:
        data = _load_data(d)
        shop_name = data.get("shop_name", d["name"])
        if name_lower in shop_name.lower():
            return d
    return None


# ── Drop 3: Buy orders (Tier 3 only) ─────────────────────────────────────────

_ORDER_ID_KEY = "_next_order_id"


def _next_order_id(data: dict) -> int:
    nid = data.get(_ORDER_ID_KEY, 1)
    data[_ORDER_ID_KEY] = nid + 1
    return nid


async def post_buy_order(
    char: dict, droid_id: int,
    resource_type: str, min_quality: int,
    qty_wanted: int, price_per: int,
    db,
) -> tuple[bool, str]:
    """
    Owner posts a buy order for a crafting resource (Tier 3 only).
    Escrow = qty_wanted × price_per is deducted from owner's credits immediately.
    """
    from engine.crafting import RESOURCE_TYPES

    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."

    data     = _load_data(obj)
    tier_key = data.get("tier_key", "gn4")
    tier     = get_tier(tier_key) or {}
    if not tier.get("buy_orders"):
        return False, (
            "Buy orders are only available on Tier 3 (GN-12 Commerce Droids). "
            "Upgrade your droid first."
        )

    # Validate resource type
    valid_types = list(RESOURCE_TYPES.keys()) if hasattr(RESOURCE_TYPES, "keys") else []
    if resource_type not in valid_types and valid_types:
        return False, (
            f"Unknown resource type '{resource_type}'. "
            f"Valid: {', '.join(list(valid_types)[:8])}"
        )

    if min_quality < 1 or min_quality > 100:
        return False, "Minimum quality must be between 1 and 100."
    if qty_wanted < 1:
        return False, "Quantity must be at least 1."
    if price_per < 1:
        return False, "Price per unit must be at least 1 credit."

    escrow_needed = qty_wanted * price_per
    if char.get("credits", 0) < escrow_needed:
        return False, (
            f"Insufficient credits. Escrow required: {escrow_needed:,} cr "
            f"({qty_wanted} × {price_per:,} cr)."
        )

    # Deduct escrow from owner
    char["credits"] -= escrow_needed
    await db.save_character(char["id"], credits=char["credits"])

    # Add order to droid data
    orders = data.get("buy_orders", [])
    order_id = _next_order_id(data)
    orders.append({
        "id":               order_id,
        "resource_type":    resource_type,
        "min_quality":      min_quality,
        "qty_wanted":       qty_wanted,
        "qty_filled":       0,
        "price_per":        price_per,
        "escrow_deposited": escrow_needed,
        "active":           True,
    })
    data["buy_orders"]     = orders
    data["last_owner_ts"]  = time.time()
    await db.update_object(droid_id, data=_dump_data(data))

    shop_name = data.get("shop_name", obj["name"])
    return True, (
        f"Buy order #{order_id} posted on \033[1;37m{shop_name}\033[0m:\n"
        f"  Wanted: {qty_wanted}x {resource_type.replace('_', ' ').title()} "
        f"(quality {min_quality}+) at {price_per:,} cr each\n"
        f"  Escrow deposited: {escrow_needed:,} cr "
        f"(Balance: {char['credits']:,} cr)\n"
        f"  Sellers can fill this with: "
        f"\033[1;33msell {resource_type} to {shop_name}\033[0m"
    )


async def cancel_buy_order(
    char: dict, droid_id: int, order_id: int, db
) -> tuple[bool, str]:
    """Cancel a buy order and refund remaining escrow to owner."""
    obj = await db.get_object(droid_id)
    if not obj or obj["owner_id"] != char["id"]:
        return False, "You don't own that vendor droid."

    data   = _load_data(obj)
    orders = data.get("buy_orders", [])
    order  = next((o for o in orders if o["id"] == order_id), None)

    if not order:
        return False, f"No buy order #{order_id} found."
    if not order.get("active"):
        return False, f"Buy order #{order_id} is already inactive."

    # Calculate refund: escrow minus what's already been paid out
    filled        = order.get("qty_filled", 0)
    price_per     = order["price_per"]
    paid_out      = filled * price_per
    deposited     = order.get("escrow_deposited", 0)
    refund        = max(0, deposited - paid_out)

    order["active"] = False
    data["buy_orders"] = orders

    if refund > 0:
        char["credits"] += refund
        await db.save_character(char["id"], credits=char["credits"])

    data["last_owner_ts"] = time.time()
    await db.update_object(droid_id, data=_dump_data(data))

    msg = f"Buy order #{order_id} cancelled."
    if refund > 0:
        msg += f" Refunded {refund:,} cr (Balance: {char['credits']:,} cr)."
    return True, msg


async def sell_to_droid(
    seller: dict, droid_id: int, resource_type: str, qty: int, db
) -> tuple[bool, str]:
    """
    Seller fills a buy order at a vendor droid.
    Transfers resources from seller inventory → droid, pays credits from escrow.
    """
    obj = await db.get_object(droid_id)
    if not obj or not obj.get("room_id"):
        return False, "That vendor droid is not available."
    if obj["owner_id"] == seller["id"]:
        return False, "You cannot fill your own buy orders."

    data   = _load_data(obj)
    orders = data.get("buy_orders", [])

    # Find a matching active order
    order = next(
        (o for o in orders
         if o.get("active")
         and o["resource_type"] == resource_type
         and (o["qty_wanted"] - o.get("qty_filled", 0)) > 0),
        None,
    )
    if not order:
        shop_name = data.get("shop_name", obj["name"])
        return False, (
            f"\033[1;37m{shop_name}\033[0m has no active buy order "
            f"for '{resource_type.replace('_', ' ')}'. "
            f"Use \033[1;33mbrowse {shop_name}\033[0m to see current orders."
        )

    # Check seller has the resource
    try:
        import json as _j
        inv = seller.get("inventory", "{}")
        if isinstance(inv, str):
            inv = _j.loads(inv) if inv else {}
        resources = inv.get("resources", [])
        stack = next(
            (r for r in resources
             if r.get("type") == resource_type
             and float(r.get("quality", 0)) >= order["min_quality"]),
            None,
        )
        if not stack:
            return False, (
                f"You don't have {resource_type.replace('_', ' ')} "
                f"with quality {order['min_quality']}+ in your inventory."
            )
    except Exception as e:
        log.warning("[shops] sell_to_droid inventory check failed: %s", e)
        return False, "Inventory check failed."

    # Calculate how many we can fill
    have_qty   = int(stack.get("quantity", 1))
    needed_qty = order["qty_wanted"] - order.get("qty_filled", 0)
    sell_qty   = min(qty, have_qty, needed_qty)
    if sell_qty < 1:
        return False, "Nothing to sell."

    # Check escrow is sufficient
    escrow_remaining = (
        order.get("escrow_deposited", 0)
        - order.get("qty_filled", 0) * order["price_per"]
    )
    max_can_pay = escrow_remaining // order["price_per"]
    sell_qty = min(sell_qty, max_can_pay)
    if sell_qty < 1:
        return False, "Buy order has insufficient escrow to pay for more units."

    payout = sell_qty * order["price_per"]

    # Deduct from seller inventory
    stack["quantity"] -= sell_qty
    if stack["quantity"] <= 0:
        resources = [r for r in resources if r is not stack]
    inv["resources"] = resources
    seller["inventory"] = _j.dumps(inv)
    seller["credits"]  += payout
    await db.save_character(
        seller["id"], credits=seller["credits"], inventory=seller["inventory"]
    )

    # Update order
    order["qty_filled"] = order.get("qty_filled", 0) + sell_qty
    if order["qty_filled"] >= order["qty_wanted"]:
        order["active"] = False

    data["buy_orders"]    = orders
    data["last_sale_ts"]  = time.time()
    data["total_sales"]   = data.get("total_sales", 0) + 1
    await db.update_object(droid_id, data=_dump_data(data))

    # Log transaction
    await db.log_shop_transaction(
        droid_id=droid_id,
        seller_id=obj["owner_id"],
        buyer_id=seller["id"],
        item_key=resource_type,
        item_name=resource_type.replace("_", " ").title(),
        quality=int(float(stack.get("quality", 0))),
        quantity=sell_qty,
        unit_price=order["price_per"],
        listing_fee=0,
        txn_type="buy_order_fill",
    )

    shop_name = data.get("shop_name", obj["name"])
    remaining = order["qty_wanted"] - order["qty_filled"]
    filled_msg = " (order complete!)" if not order["active"] else f" ({remaining} still needed)"
    return True, (
        f"Sold {sell_qty}x {resource_type.replace('_', ' ').title()} "
        f"to \033[1;37m{shop_name}\033[0m "
        f"for \033[1;33m{payout:,} cr\033[0m.{filled_msg}\n"
        f"  Balance: {seller['credits']:,} cr"
    )


def format_buy_orders(orders: list) -> list[str]:
    """Return formatted lines for buy orders section of browse display."""
    active = [o for o in orders if o.get("active") and
              (o["qty_wanted"] - o.get("qty_filled", 0)) > 0]
    if not active:
        return []
    lines = [
        "\033[1;36m──────────────────────────────────────────\033[0m",
        "  \033[1;33m[WANTED]\033[0m",
    ]
    for o in active:
        remaining = o["qty_wanted"] - o.get("qty_filled", 0)
        rname = o["resource_type"].replace("_", " ").title()
        lines.append(
            f"  \033[1;33mW{o['id']}\033[0m  {rname:<22} "
            f"quality {o['min_quality']}+  "
            f"{remaining} needed  "
            f"\033[1;33m{o['price_per']:,} cr/unit\033[0m"
        )
    return lines


# ── Auto-recall tick ──────────────────────────────────────────────────────────

_WARN_DAYS   = 30   # Notify owner after this many days of inactivity
_RECALL_DAYS = 60   # Auto-recall after this many days

async def tick_auto_recall(db, session_mgr) -> None:
    """
    Daily maintenance tick for vendor droids.

    - Placed droids idle > 30 days with no owner interaction → warn owner once.
    - Placed droids idle > 60 days → auto-recall to owner inventory + notify.

    "Idle" = max(last_owner_ts, last_sale_ts) is older than the threshold.
    A sale resets the clock, so active shops are never recalled.
    """
    import time as _time
    now = _time.time()
    warn_cutoff   = now - (_WARN_DAYS   * 86400)
    recall_cutoff = now - (_RECALL_DAYS * 86400)

    try:
        # Fetch all placed droids
        rows = await db.fetchall(
            "SELECT * FROM objects WHERE type = 'vendor_droid' AND room_id IS NOT NULL"
        )
    except Exception:
        log.warning("tick_auto_recall: unhandled exception", exc_info=True)
        return

    for row in (rows or []):
        droid = dict(row)
        data  = _load_data(droid)

        last_active = max(
            float(data.get("last_owner_ts", 0) or 0),
            float(data.get("last_sale_ts",  0) or 0),
        )
        if last_active <= 0:
            # No timestamp set — treat as just placed
            continue

        owner_id   = droid.get("owner_id")
        shop_name  = data.get("shop_name") or droid.get("name", "Vendor Droid")

        # ── Auto-recall (60 days) ──────────────────────────────────────────
        if last_active < recall_cutoff and droid.get("room_id"):
            try:
                # Pull owner character to do a proper recall
                owner_rows = await db.fetchall(
                    "SELECT * FROM characters WHERE id = ? AND is_active = 1",
                    (owner_id,),
                )
                if owner_rows:
                    owner = dict(owner_rows[0])
                    await recall_droid(owner, droid["id"], db)
                else:
                    # Owner deleted or inactive — just clear room_id
                    await db.update_object(droid["id"], room_id=None)
                # Notify owner if online
                if owner_id and session_mgr:
                    sess = session_mgr.find_by_character(owner_id)
                    if sess:
                        await sess.send_line(
                            f"  \033[1;33m[SHOP]\033[0m \033[1;37m{shop_name}\033[0m "
                            f"has been \033[1;31mauto-recalled\033[0m — "
                            f"inactive for {_RECALL_DAYS}+ days."
                        )
                import logging as _log
                _log.getLogger(__name__).info(
                    "[shops] Auto-recalled droid %d (%s) — idle >%d days",
                    droid["id"], shop_name, _RECALL_DAYS,
                )
            except Exception:
                log.warning("tick_auto_recall: unhandled exception", exc_info=True)
                pass
            continue  # Skip warn check for recalled droids

        # ── Idle warning (30 days, send once) ─────────────────────────────
        if last_active < warn_cutoff and not data.get("idle_warned"):
            try:
                data["idle_warned"] = True
                await db.update_object(droid["id"], data=_dump_data(data))
                if owner_id and session_mgr:
                    sess = session_mgr.find_by_character(owner_id)
                    if sess:
                        await sess.send_line(
                            f"  \033[1;33m[SHOP]\033[0m \033[1;37m{shop_name}\033[0m "
                            f"has had no activity for {_WARN_DAYS} days. "
                            f"It will be auto-recalled in "
                            f"{_RECALL_DAYS - _WARN_DAYS} more days if idle."
                        )
            except Exception:
                log.warning("tick_auto_recall: unhandled exception", exc_info=True)
                pass
        elif last_active >= warn_cutoff and data.get("idle_warned"):
            # Activity reset the clock — clear the warning flag
            try:
                data["idle_warned"] = False
                await db.update_object(droid["id"], data=_dump_data(data))
            except Exception:
                log.warning("tick_auto_recall: unhandled exception", exc_info=True)
                pass
