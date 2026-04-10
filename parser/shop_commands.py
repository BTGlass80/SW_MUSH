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
            item_key, actual_name, quality, crafter = _find_in_inventory(
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
                ctx.db,
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

        await ctx.session.send_line(
            f"  Unknown shop command '{sub}'.\n"
            f"  Try: buy, place, recall, name, desc, stock, unstock, price, "
            f"collect, sales, order, cancel"
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
    Returns (item_key, item_name, quality, crafter) or (None, None, 0, "").

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
                )
    except Exception:
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
                )
    except Exception:
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
                )
    except Exception:
        pass

    return None, None, 0, ""


def register_shop_commands(registry):
    registry.register(ShopCommand())
    registry.register(BrowseCommand())
    registry.register(AdminShopCommand())
