# -*- coding: utf-8 -*-
"""
parser/shop_commands.py — Player shop / vendor droid commands for SW_MUSH.

Owner commands (via 'shop <sub>'):
  shop buy droid <tier>    — purchase a vendor droid (gn4/gn7/gn12)
  shop place [id]          — deploy droid in current room
  shop recall [id]         — recall droid to inventory
  shop name <text>         — set shop name
  shop desc <text>         — set shop description
  shop stock <item> <price> [qty] — stock item from inventory
  shop unstock <slot> [qty]       — remove item from stock
  shop price <slot> <price>       — update slot price
  shop collect [id]               — collect sales revenue
  shop sales [id]                 — view recent sales log
  +shop                           — view all your droids (dashboard)

Buyer commands:
  browse                   — list vendor droids in current room
  browse <name>            — view a specific droid's inventory
  buy <item> from <shop>   — purchase from a vendor droid (Drops 2+)

Admin commands:
  @shop list               — list all active droids
  @shop inspect <player>   — view a player's droids
  @shop remove <id>        — force-remove a droid
"""
import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

log = logging.getLogger(__name__)


class ShopCommand(BaseCommand):
    key = "shop"
    aliases = ["+shop", "shopinfo"]
    help_text = (
        "Manage your vendor droid player shop.\n"
        "\n"
        "PURCHASE & SETUP:\n"
        "  shop buy droid <tier>    — buy a droid (tiers: gn4, gn7, gn12)\n"
        "  shop place [id]          — deploy droid in this room\n"
        "  shop recall [id]         — recall droid to inventory\n"
        "  shop name <text>         — set shop display name\n"
        "  shop desc <text>         — set shop tagline\n"
        "\n"
        "INVENTORY:\n"
        "  shop stock <item> <price> [qty] — add item to shop\n"
        "  shop unstock <slot#> [qty]      — remove item from shop\n"
        "  shop price <slot#> <price>      — update price\n"
        "\n"
        "REVENUE:\n"
        "  shop collect [id]    — collect accumulated revenue\n"
        "  shop sales [id]      — view recent sales\n"
        "\n"
        "UPGRADE:\n"
        "  shop upgrade [tier]  — upgrade droid tier (must be recalled)\n"
        "\n"
        "  +shop                — view your droid status dashboard\n"
        "\n"
        "Tiers: gn4 (2,000cr/10 slots), gn7 (5,000cr/25 slots), "
        "gn12 (12,000cr/50 slots)"
    )
    usage = "shop <sub-command> [args]"

    async def execute(self, ctx: CommandContext):
        from engine.vendor_droids import (
            purchase_droid, place_droid, recall_droid,
            set_shop_name, set_shop_desc,
            stock_droid, unstock_droid, set_slot_price,
            collect_escrow, format_shop_status,
            find_droid_by_name, _load_data,
        )
        from server import ansi

        char  = ctx.session.character
        args  = (ctx.args or "").strip()
        parts = args.split(None, 1)
        sub   = parts[0].lower() if parts else ""
        rest  = parts[1].strip() if len(parts) > 1 else ""

        # ── +shop / no args → dashboard ──
        if not sub or sub in ("+shop", "shopinfo", "info", "status"):
            droids = await ctx.db.get_objects_owned_by(char["id"], "vendor_droid")
            await ctx.session.send_line(format_shop_status(droids))
            # Emit structured shop_state for web dashboard
            await _send_shop_dashboard(ctx.session, droids, char, ctx.db)
            return

        # ── shop buy droid <tier> ──
        if sub == "buy":
            bparts = rest.split(None, 1)
            if not bparts or bparts[0].lower() != "droid":
                await ctx.session.send_line(
                    "  Usage: shop buy droid <tier>  (tiers: gn4, gn7, gn12)\n"
                    "  Visit a droid dealer NPC to purchase, or use this command."
                )
                return
            tier_arg = bparts[1].strip().lower() if len(bparts) > 1 else ""
            if not tier_arg:
                await ctx.session.send_line(
                    "  Specify a tier: gn4 (2,000cr), gn7 (5,000cr), gn12 (12,000cr)"
                )
                return
            ok, msg = await purchase_droid(char, tier_arg, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop place [id] ──
        if sub in ("place", "deploy"):
            droid = await _get_owner_droid(ctx, rest, unplaced_only=True)
            if droid is None:
                return
            ok, msg = await place_droid(char, droid["id"], char["room_id"], ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop recall [id] ──
        if sub in ("recall", "pickup"):
            droid = await _get_owner_droid(ctx, rest, placed_only=True)
            if droid is None:
                return
            ok, msg = await recall_droid(char, droid["id"], ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop name <text> ──
        if sub == "name":
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            ok, msg = await set_shop_name(char, droid["id"], rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop desc <text> ──
        if sub == "desc":
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            ok, msg = await set_shop_desc(char, droid["id"], rest, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop stock <item_name> <price> [qty] ──
        if sub in ("stock", "add"):
            # Parse: last token is qty (optional), second-to-last is price
            rparts = rest.rsplit(None, 2)
            if len(rparts) < 2:
                await ctx.session.send_line(
                    "  Usage: shop stock <item name> <price> [quantity]"
                )
                return
            # Detect if last token is a qty or price
            qty = 1
            if len(rparts) == 3 and rparts[2].isdigit():
                qty = int(rparts[2])
                price_str = rparts[1]
                item_name = rparts[0]
            else:
                price_str = rparts[-1]
                item_name = " ".join(rparts[:-1])

            if not price_str.isdigit():
                await ctx.session.send_line(
                    "  Usage: shop stock <item name> <price> [quantity]"
                )
                return

            price = int(price_str)
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return

            # Find item in character inventory (equipment or resources)
            item_key, actual_name, quality, crafter, source_type = _find_in_inventory(
                char, item_name
            )
            if not item_key:
                await ctx.session.send_line(
                    f"  '{item_name}' not found in your inventory.\n"
                    f"  Use 'inventory' to see your items."
                )
                return

            ok, msg = await stock_droid(
                char, droid["id"],
                item_key, actual_name, quality, price, qty, crafter,
                ctx.db, source_type=source_type,
            )
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop unstock <slot> [qty] ──
        if sub in ("unstock", "remove"):
            uparts = rest.split()
            if not uparts or not uparts[0].isdigit():
                await ctx.session.send_line("  Usage: shop unstock <slot#> [quantity]")
                return
            slot_num = int(uparts[0])
            qty      = int(uparts[1]) if len(uparts) > 1 and uparts[1].isdigit() else 999
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            ok, msg = await unstock_droid(char, droid["id"], slot_num, qty, ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop price <slot> <price> ──
        if sub == "price":
            pparts = rest.split()
            if len(pparts) < 2 or not pparts[0].isdigit() or not pparts[1].isdigit():
                await ctx.session.send_line("  Usage: shop price <slot#> <new_price>")
                return
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            ok, msg = await set_slot_price(
                char, droid["id"], int(pparts[0]), int(pparts[1]), ctx.db
            )
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop collect [id] ──
        if sub in ("collect", "withdraw"):
            droid = await _get_owner_droid(ctx, rest)
            if droid is None:
                return
            ok, msg = await collect_escrow(char, droid["id"], ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop sales [id] ──
        if sub in ("sales", "log"):
            droids = await ctx.db.get_objects_owned_by(char["id"], "vendor_droid")
            if not droids:
                await ctx.session.send_line("  You don't own any vendor droids.")
                return
            droid_id = None
            if rest.isdigit():
                droid_id = int(rest)
            txns = await ctx.db.get_shop_transactions(
                char["id"], droid_id=droid_id, limit=20
            )
            if not txns:
                await ctx.session.send_line("  No sales recorded yet.")
                return
            lines = [
                "\033[1;36m══════════════════════════════════════════\033[0m",
                "  \033[1;37mRECENT SALES\033[0m",
                "\033[1;36m──────────────────────────────────────────\033[0m",
            ]
            for t in txns:
                import datetime
                ts = datetime.datetime.fromtimestamp(
                    float(t.get("created_at", 0))
                ).strftime("%m/%d %H:%M")
                net = t["total_price"] - t.get("listing_fee", 0)
                lines.append(
                    f"  \033[2m{ts}\033[0m  {t['item_name']:<24} "
                    f"x{t.get('quantity',1)}  "
                    f"\033[1;33m{net:,}cr net\033[0m  "
                    f"\033[2m→ {t.get('buyer_name','?')}\033[0m"
                )
            lines.append("\033[1;36m══════════════════════════════════════════\033[0m")
            await ctx.session.send_line("\n".join(lines))
            return

        # ── shop order <resource> <min_quality> <qty> <price> (Tier 3) ──
        if sub == "order":
            oparts = rest.split()
            if len(oparts) < 4:
                await ctx.session.send_line(
                    "  Usage: shop order <resource> <min_quality> <qty> <price_per>\n"
                    "  Example: shop order durasteel 60 10 80\n"
                    "  (Tier 3 GN-12 Commerce Droids only)"
                )
                return
            resource_type = oparts[0].lower()
            if not all(p.isdigit() for p in oparts[1:4]):
                await ctx.session.send_line(
                    "  Usage: shop order <resource> <min_quality> <qty> <price_per>"
                )
                return
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            from engine.vendor_droids import post_buy_order
            ok, msg = await post_buy_order(
                char, droid["id"], resource_type,
                int(oparts[1]), int(oparts[2]), int(oparts[3]),
                ctx.db,
            )
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop cancel <order_id> ──
        if sub == "cancel":
            if not rest.isdigit():
                await ctx.session.send_line("  Usage: shop cancel <order_id>")
                return
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return
            from engine.vendor_droids import cancel_buy_order
            ok, msg = await cancel_buy_order(char, droid["id"], int(rest), ctx.db)
            await ctx.session.send_line(f"  {msg}")
            return

        # ── shop upgrade <tier> ──
        if sub == "upgrade":
            from engine.vendor_droids import (
                get_tier, get_tier_by_number, _load_data, _dump_data,
            )
            droid = await _get_owner_droid(ctx, "")
            if droid is None:
                return

            obj = await ctx.db.get_object(droid["id"])
            if not obj:
                await ctx.session.send_line("  Droid data error.")
                return

            data = _load_data(obj)
            current_tier_key = data.get("tier_key", "gn4")
            current_tier = get_tier(current_tier_key) or {}
            current_num = current_tier.get("tier", 1)

            if current_num >= 3:
                await ctx.session.send_line(
                    "  Your droid is already at maximum tier (GN-12)."
                )
                return

            # Must be recalled (not placed)
            if obj.get("room_id"):
                await ctx.session.send_line(
                    "  Your droid must be recalled before upgrading.\n"
                    "  Use \033[1;33mshop recall\033[0m first."
                )
                return

            # Determine target tier
            target_num = current_num + 1
            if rest:
                # Allow explicit tier: "shop upgrade gn7" or "shop upgrade 2"
                if rest.lower().startswith("gn"):
                    target = get_tier(rest.lower())
                    if target:
                        target_num = target["tier"]
                elif rest.isdigit():
                    target_num = int(rest)

            target_result = get_tier_by_number(target_num)
            if not target_result:
                await ctx.session.send_line(
                    f"  Unknown tier '{rest}'. Valid tiers: gn4 (1), gn7 (2), gn12 (3)."
                )
                return

            target_key, target_tier = target_result

            if target_num <= current_num:
                await ctx.session.send_line(
                    f"  Your droid is already tier {current_num}. "
                    f"Can only upgrade to a higher tier."
                )
                return

            # Upgrade cost: difference between tier costs
            upgrade_cost = target_tier["cost"] - current_tier.get("cost", 0)
            if upgrade_cost < 1000:
                upgrade_cost = 1000  # Minimum floor

            # Pricing from NPC dealer personality text:
            # gn4->gn7 = 3,000cr, gn7->gn12 = 7,000cr
            UPGRADE_PRICES = {
                (1, 2): 3000,   # gn4 -> gn7
                (1, 3): 10000,  # gn4 -> gn12 (skip tier)
                (2, 3): 7000,   # gn7 -> gn12
            }
            upgrade_cost = UPGRADE_PRICES.get(
                (current_num, target_num), upgrade_cost
            )

            if char.get("credits", 0) < upgrade_cost:
                await ctx.session.send_line(
                    f"  Insufficient credits. Upgrade to {target_tier['name']} "
                    f"costs {upgrade_cost:,} cr "
                    f"(you have {char.get('credits', 0):,})."
                )
                return

            # Deduct credits
            char["credits"] -= upgrade_cost
            await ctx.db.save_character(char["id"], credits=char["credits"])

            # Update droid tier (inventory carries over)
            data["tier"] = target_num
            data["tier_key"] = target_key
            import time as _time
            data["last_owner_ts"] = _time.time()
            await ctx.db.update_object(
                droid["id"],
                name=target_tier["name"],
                data=_dump_data(data),
            )

            old_slots = current_tier.get("slots", 10)
            new_slots = target_tier.get("slots", 25)
            await ctx.session.send_line(
                f"  \033[1;32mUpgrade complete!\033[0m "
                f"{current_tier.get('name', current_tier_key)} → "
                f"\033[1;37m{target_tier['name']}\033[0m\n"
                f"  Cost: {upgrade_cost:,} cr "
                f"(Balance: {char['credits']:,} cr)\n"
                f"  Inventory slots: {old_slots} → {new_slots}\n"
                f"  All stocked items have been preserved."
            )
            if target_tier.get("buy_orders"):
                await ctx.session.send_line(
                    f"  \033[1;33mBuy orders now available!\033[0m "
                    f"Use \033[1;33mshop order\033[0m to post wanted listings."
                )
            return

        await ctx.session.send_line(
            f"  Unknown shop command '{sub}'.\n"
            f"  Try: buy, place, recall, name, desc, stock, unstock, price, "
            f"collect, sales, order, cancel, upgrade"
        )


# ── Browse command ─────────────────────────────────────────────────────────────

class BrowseCommand(BaseCommand):
    key = "browse"
    aliases = ["shops", "shoplist"]
    help_text = (
        "Browse vendor droids in your current location.\n"
        "\n"
        "USAGE:\n"
        "  browse              — list all vendor droids here\n"
        "  browse <shop name>  — view a specific droid's inventory\n"
        "\n"
        "To buy: buy <slot#> from <shop name>"
    )
    usage = "browse [shop name]"

    async def execute(self, ctx: CommandContext):
        from engine.vendor_droids import (
            format_droid_list, format_droid_inventory, find_droid_by_name
        )

        char   = ctx.session.character
        room   = await ctx.db.get_room(char["room_id"])
        droids = await ctx.db.get_objects_in_room(char["room_id"], "vendor_droid")

        if not droids:
            await ctx.session.send_line(
                "  No vendor droids in this area.\n"
                "  Explore the market districts on each planet to find player shops."
            )
            return

        arg = (ctx.args or "").strip()

        if not arg:
            room_name = room["name"] if room else ""
            await ctx.session.send_line(format_droid_list(droids, room_name))
            # Emit shop_state so web panel shows room droids
            await _send_shop_browse(ctx.session, droids, focused_id=None)
            return

        droid = find_droid_by_name(droids, arg)
        if not droid:
            await ctx.session.send_line(
                f"  No vendor droid named '{arg}' here. "
                f"Use 'browse' to list available shops."
            )
            return

        await ctx.session.send_line(
            format_droid_inventory(droid, viewer_id=char["id"])
        )
        # Emit shop_state for web browse panel
        await _send_shop_browse(ctx.session, droids, focused_id=droid["id"])


# ── Admin @shop command ────────────────────────────────────────────────────────

class AdminShopCommand(BaseCommand):
    key = "@shop"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Admin vendor droid management.\n"
        "  @shop list            — list all active vendor droids\n"
        "  @shop inspect <name>  — view a player's droids\n"
        "  @shop remove <id>     — force-remove a droid"
    )
    usage = "@shop <sub> [args]"

    async def execute(self, ctx: CommandContext):
        from engine.vendor_droids import _load_data

        parts = (ctx.args or "").split(None, 1)
        sub   = parts[0].lower() if parts else "list"
        rest  = parts[1].strip() if len(parts) > 1 else ""

        if sub == "list":
            # List all placed droids
            rows = await ctx.db._db.execute_fetchall(
                """SELECT o.*, c.name AS owner_name
                   FROM objects o
                   JOIN characters c ON c.id = o.owner_id
                   WHERE o.type = 'vendor_droid' AND o.room_id IS NOT NULL
                   ORDER BY c.name, o.id"""
            )
            if not rows:
                await ctx.session.send_line("  No vendor droids currently placed.")
                return
            lines = ["  \033[1;37mAll Placed Vendor Droids:\033[0m"]
            for r in rows:
                d = _load_data(dict(r))
                lines.append(
                    f"  [{r['id']}] {d.get('shop_name', r['name']):<30} "
                    f"Owner: {r['owner_name']}  "
                    f"Room: {r['room_id']}"
                )
            await ctx.session.send_line("\n".join(lines))
            return

        if sub == "inspect":
            rows = await ctx.db._db.execute_fetchall(
                "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
                (rest,),
            )
            if not rows:
                await ctx.session.send_line(f"  Player '{rest}' not found.")
                return
            owner_id = rows[0]["id"]
            droids   = await ctx.db.get_objects_owned_by(owner_id, "vendor_droid")
            from engine.vendor_droids import format_shop_status
            await ctx.session.send_line(format_shop_status(droids))
            return

        if sub == "remove":
            if not rest.isdigit():
                await ctx.session.send_line("  Usage: @shop remove <droid_id>")
                return
            await ctx.db.delete_object(int(rest))
            await ctx.session.send_line(f"  Vendor droid #{rest} removed.")
            return

        await ctx.session.send_line(f"  Unknown @shop sub-command '{sub}'.")


# ── Helpers ────────────────────────────────────────────────────────────────────

async def _get_owner_droid(ctx: CommandContext, id_or_name: str,
                            placed_only: bool = False,
                            unplaced_only: bool = False):
    """
    Return the owner's droid matching id_or_name (or their only droid).
    Sends an error and returns None on failure.
    """
    from engine.vendor_droids import find_droid_by_name, _load_data

    char   = ctx.session.character
    droids = await ctx.db.get_objects_owned_by(char["id"], "vendor_droid")

    if not droids:
        await ctx.session.send_line(
            "  You don't own any vendor droids.\n"
            "  Use \033[1;33mshop buy droid <tier>\033[0m to purchase one."
        )
        return None

    if placed_only:
        droids = [d for d in droids if d.get("room_id")]
        if not droids:
            await ctx.session.send_line("  You have no placed vendor droids.")
            return None

    if unplaced_only:
        droids = [d for d in droids if not d.get("room_id")]
        if not droids:
            await ctx.session.send_line(
                "  All your droids are already placed. "
                "Use \033[1;33mshop recall\033[0m first."
            )
            return None

    if not id_or_name or len(droids) == 1:
        return droids[0]

    droid = find_droid_by_name(droids, id_or_name)
    if not droid:
        await ctx.session.send_line(
            f"  No vendor droid matching '{id_or_name}'. "
            f"Use \033[1;33m+shop\033[0m to see your droids."
        )
        return None
    return droid


def _find_in_inventory(char: dict, name_arg: str):
    """
    Search character inventory for an item matching name_arg.
    Returns (item_key, item_name, quality, crafter, source_type) or
    (None, None, 0, "", None).

    source_type is one of: "equipment", "resource", "item"

    Checks:
      1. Equipped weapon (engine/items.py ItemInstance)
      2. Crafting resources (engine/crafting.py resource list)
      3. General inventory items (list under 'items' key)
    """
    import json as _j
    name_lower = name_arg.lower()

    # Check equipped weapon
    try:
        from engine.items import parse_equipment_json
        from engine.weapons import get_weapon_registry
        item = parse_equipment_json(char.get("equipment", "{}"))
        if item and not item.is_broken:
            wr = get_weapon_registry()
            w  = wr.get(item.key)
            wname = w.name if w else item.key
            if name_lower in wname.lower() or name_lower in item.key.lower():
                return (
                    item.key, wname, item.quality,
                    getattr(item, "crafter", "") or "",
                    "equipment",
                )
    except Exception:
        log.warning("_find_in_inventory: unhandled exception", exc_info=True)
        pass

    # Check crafting resources
    try:
        inv = char.get("inventory", "{}")
        if isinstance(inv, str):
            inv = _j.loads(inv) if inv else {}
        resources = inv.get("resources", [])
        for stack in resources:
            rtype = stack.get("type", "")
            if name_lower in rtype.lower():
                return (
                    rtype,
                    rtype.replace("_", " ").title(),
                    int(stack.get("quality", 0)),
                    "",
                    "resource",
                )
    except Exception:
        log.warning("_find_in_inventory: unhandled exception", exc_info=True)
        pass

    # Check general inventory items
    try:
        inv = char.get("inventory", "{}")
        if isinstance(inv, str):
            inv = _j.loads(inv) if inv else {}
        items = inv.get("items", [])
        for it in items:
            iname = it.get("name", it.get("key", ""))
            if name_lower in iname.lower():
                if it.get("faction_issued"):
                    continue  # Skip faction gear
                return (
                    it.get("key", iname),
                    iname,
                    it.get("quality", 50),
                    it.get("crafter", "") or "",
                    "item",
                )
    except Exception:
        log.warning("_find_in_inventory: unhandled exception", exc_info=True)
        pass

    return None, None, 0, "", None


# ── Web JSON helpers ───────────────────────────────────────────────────────────

def _droid_to_dict(droid: dict) -> dict:
    """Serialize a vendor droid object to a JSON-safe dict for shop_state."""
    from engine.vendor_droids import _load_data
    data = _load_data(droid)
    inventory = data.get("inventory", [])
    return {
        "id": droid["id"],
        "name": data.get("shop_name") or droid.get("name", "Vendor Droid"),
        "desc": data.get("shop_desc", ""),
        "tier": data.get("tier_key", "gn4"),
        "placed": bool(droid.get("room_id")),
        "escrow": data.get("escrow_credits", 0),
        "item_count": len([s for s in inventory if s.get("quantity", 0) > 0]),
        "inventory": [
            {
                "slot": i + 1,
                "name": slot.get("item_name", "Unknown"),
                "price": slot.get("price", 0),
                "qty": slot.get("quantity", 1),
                "quality": slot.get("quality", 0),
                "crafter": slot.get("crafter", ""),
            }
            for i, slot in enumerate(inventory)
            if slot.get("quantity", 0) > 0
        ],
    }


async def _get_sales_summary(db, owner_id: int, droid_id: int) -> list:
    """Fetch recent sales for the dashboard (last 10 per droid)."""
    try:
        txns = await db.get_shop_transactions(owner_id, droid_id=droid_id, limit=10)
        import datetime as _dt
        result = []
        for t in txns:
            ts = _dt.datetime.fromtimestamp(
                float(t.get("created_at", 0))
            ).strftime("%m/%d %H:%M")
            net = t["total_price"] - t.get("listing_fee", 0)
            result.append({
                "ts": ts,
                "item": t["item_name"],
                "qty": t.get("quantity", 1),
                "net": net,
                "buyer": t.get("buyer_name", "?"),
            })
        return result
    except Exception:
        log.warning("_get_sales_summary: unhandled exception", exc_info=True)
        return []


async def _send_shop_dashboard(session, droids: list, char: dict, db) -> None:
    """
    Send a shop_state JSON message for the +shop owner dashboard.
    WebSocket only — Telnet clients ignore it.
    """
    try:
        from server.session import Protocol
        if session.protocol != Protocol.WEBSOCKET:
            return

        droid_list = []
        total_escrow = 0
        for d in droids:
            entry = _droid_to_dict(d)
            entry["sales"] = await _get_sales_summary(db, char["id"], d["id"])
            total_escrow += entry["escrow"]
            droid_list.append(entry)

        await session.send_json("shop_state", {
            "mode": "dashboard",
            "owner_name": char.get("name", ""),
            "total_escrow": total_escrow,
            "droids": droid_list,
        })
    except Exception:
        pass  # Non-critical — text output already sent


async def _send_shop_browse(session, droids: list, focused_id=None) -> None:
    """
    Send a shop_state JSON message for the buyer browse panel.
    WebSocket only — Telnet clients ignore it.
    """
    try:
        from server.session import Protocol
        if session.protocol != Protocol.WEBSOCKET:
            return

        droid_list = [_droid_to_dict(d) for d in droids]

        await session.send_json("shop_state", {
            "mode": "browse",
            "focused_id": focused_id,
            "droids": droid_list,
        })
    except Exception:
        pass  # Non-critical — text output already sent


def register_shop_commands(registry):
    registry.register(ShopCommand())
    registry.register(BrowseCommand())
    registry.register(AdminShopCommand())
    registry.register(MarketSearchCommand())


class MarketSearchCommand(BaseCommand):
    """
    market search [planet]  — Search the planet-wide shopfront directory.
    Lists all vendor droids in player-owned shopfront residences.
    Drop 5: Housing Shopfronts.
    """
    key = "market"
    aliases = ["mkt"]
    help_text = (
        "Search the planetary market directory for player-run shops.\n"
        "\n"
        "USAGE:\n"
        "  market search           — list all shopfronts on the current planet\n"
        "  market search <planet>  — list shopfronts on a specific planet\n"
        "  market search all       — list all shopfronts across all planets\n"
        "\n"
        "Only vendor droids placed in player-owned shopfront residences appear here.\n"
        "Use 'browse <shop name>' to browse a specific shop's inventory."
    )
    usage = "market search [planet | all]"

    async def execute(self, ctx: CommandContext) -> None:
        from engine.housing import get_market_directory

        char    = ctx.session.character
        args    = (ctx.args or "").strip().lower()
        parts   = args.split(None, 1)
        sub     = parts[0] if parts else ""
        planet  = parts[1].strip() if len(parts) > 1 else None

        if sub not in ("search", ""):
            await ctx.session.send_line(
                "  Usage: market search [planet | all]\n"
                "  Example: market search tatooine"
            )
            return

        # Determine planet filter: default to current room's planet
        if not planet or planet == "all":
            filter_planet = None
            if not planet:
                # Infer from current room's zone
                try:
                    room_id = char.get("room_id")
                    if room_id:
                        room = await ctx.db.get_room(room_id)
                        if room and room.get("zone_id"):
                            zone = await ctx.db.get_zone(room["zone_id"])
                            if zone:
                                props = zone.get("properties", "{}")
                                import json as _j
                                if isinstance(props, str):
                                    props = _j.loads(props)
                                filter_planet = props.get("planet", "").lower() or None
                except Exception:
                    log.warning("execute: unhandled exception", exc_info=True)
                    pass
        else:
            filter_planet = planet

        shops = await get_market_directory(ctx.db, filter_planet)

        planet_label = filter_planet.title() if filter_planet else "All Planets"
        lines = [
            f"\033[1;37m── Market Directory — {planet_label} ──\033[0m",
        ]

        if not shops:
            lines.append(
                f"  No player shopfronts found"
                + (f" on {planet_label}" if filter_planet else "") + "."
            )
            lines.append(
                "  Players can open shopfronts with: \033[1;37mhousing shopfront\033[0m"
            )
            for line in lines:
                await ctx.session.send_line(line)
            return

        # Group by planet
        by_planet: dict[str, list] = {}
        for s in shops:
            by_planet.setdefault(s["planet"], []).append(s)

        tier_labels = {"gn4": "GN-4", "gn7": "GN-7", "gn12": "GN-12"}
        TIER_COLORS = {
            "gn4":  "\033[2m",
            "gn7":  "\033[1;36m",
            "gn12": "\033[1;33m",
        }

        for p_name, p_shops in sorted(by_planet.items()):
            lines.append(f"")
            lines.append(f"  \033[1;36m{p_name.title()}\033[0m")
            lines.append(f"  {'Shop Name':<28} {'Owner':<18} {'Items':>5}  {'Tier':<8}  Location")
            lines.append("  " + "─" * 74)
            for s in sorted(p_shops, key=lambda x: x["shop_name"].lower()):
                tier_color = TIER_COLORS.get(s["tier_key"], "")
                tier_str   = tier_labels.get(s["tier_key"], s["tier_key"])
                items_str  = str(s["item_count"]) if s["item_count"] > 0 else "—"
                lines.append(
                    f"  \033[1;37m{s['shop_name']:<28}\033[0m "
                    f"\033[2m{s['owner_name']:<18}\033[0m "
                    f"{items_str:>5}  "
                    f"{tier_color}{tier_str:<8}\033[0m  "
                    f"\033[2m{s['room_name']}\033[0m"
                )
                if s.get("shop_desc"):
                    lines.append(f"    \033[2m{s['shop_desc'][:70]}\033[0m")

        lines += [
            "",
            "  Use \033[1;37mbrowse <shop name>\033[0m to see a shop's inventory.",
            "  Use \033[1;37mhousing shopfront\033[0m to open your own shop.",
        ]

        for line in lines:
            await ctx.session.send_line(line)

