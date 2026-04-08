#!/usr/bin/env python3
"""
Drop 3 — Bargain Skill Integration for buy/sell commands.
Patches:
  1. parser/space_commands.py  BuyCommand  → Bargain check adjusts purchase price
  2. parser/builtin_commands.py SellCommand → Bargain check adjusts sell price

Run from project root:
    python patches/patch_bargain_integration.py

Requires Drop 1 (engine/skill_checks.py with resolve_bargain_check).
"""
import os
import sys
import shutil
import ast

TARGETS = [
    ("parser/space_commands.py",   "space_buy"),
    ("parser/builtin_commands.py", "builtin_sell"),
]


def read_file(path):
    for enc in ("utf-8", "utf-8-sig"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def safe_replace(source, old, new, label):
    """Try LF version first, then CRLF."""
    if old in source:
        result = source.replace(old, new, 1)
        print(f"  [OK] {label}")
        return result
    old_crlf = old.replace("\n", "\r\n")
    if old_crlf in source:
        new_crlf = new.replace("\n", "\r\n")
        result = source.replace(old_crlf, new_crlf, 1)
        print(f"  [OK] {label} (CRLF)")
        return result
    print(f"  [FAIL] {label} — anchor not found!")
    return None


def patch_buy(source):
    """Patch BuyCommand to include Bargain haggle."""

    OLD = '''\
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: buy <weapon name>")
            await ctx.session.send_line("  Type 'weapons' to see available weapons and prices.")
            return
        from engine.weapons import get_weapon_registry
        from engine.items import ItemInstance, serialize_equipment
        wr = get_weapon_registry()
        weapon = wr.find_by_name(ctx.args.strip())
        if not weapon:
            await ctx.session.send_line(f"  Unknown item: '{ctx.args}'. Type 'weapons' to see the list.")
            return
        if weapon.is_armor:
            await ctx.session.send_line("  Armor purchases coming soon.")
            return
        price = weapon.cost
        if price <= 0:
            price = 500
        char = ctx.session.character
        current_credits = char.get("credits", 1000)
        if current_credits < price:
            await ctx.session.send_line(
                f"  Not enough credits! {weapon.name} costs {price:,} credits, "
                f"you have {current_credits:,}.")
            return
        new_credits = current_credits - price
        item = ItemInstance.new_from_vendor(weapon.key)
        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], credits=new_credits, equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(
                f"  Purchased and equipped {weapon.name} for {price:,} credits. "
                f"({new_credits:,} remaining)")
        )
        await ctx.session.send_line(f"  Condition: {item.condition_bar}")'''

    NEW = '''\
    async def execute(self, ctx):
        if not ctx.args:
            await ctx.session.send_line("Usage: buy <weapon name>")
            await ctx.session.send_line("  Type 'weapons' to see available weapons and prices.")
            return
        from engine.weapons import get_weapon_registry
        from engine.items import ItemInstance, serialize_equipment
        wr = get_weapon_registry()
        weapon = wr.find_by_name(ctx.args.strip())
        if not weapon:
            await ctx.session.send_line(f"  Unknown item: '{ctx.args}'. Type 'weapons' to see the list.")
            return
        if weapon.is_armor:
            await ctx.session.send_line("  Armor purchases coming soon.")
            return
        base_price = weapon.cost
        if base_price <= 0:
            base_price = 500
        char = ctx.session.character

        # ── Bargain haggle: player vs vendor ──
        npc_dice, npc_pips = 3, 0  # Default generic vendor: 3D Bargain
        try:
            import json as _json
            npcs = await ctx.db.get_npcs_in_room(char["room_id"])
            for npc in npcs:
                sheet = _json.loads(npc.get("char_sheet_json", "{}"))
                npc_skills = sheet.get("skills", {})
                bargain_str = npc_skills.get("bargain", "")
                if bargain_str:
                    from engine.skill_checks import _parse_dice_str
                    npc_dice, npc_pips = _parse_dice_str(bargain_str)
                    break  # Use first vendor NPC with Bargain skill
        except Exception:
            pass

        from engine.skill_checks import resolve_bargain_check
        haggle = resolve_bargain_check(
            char, base_price,
            npc_bargain_dice=npc_dice, npc_bargain_pips=npc_pips,
            is_buying=True,
        )
        price = haggle["adjusted_price"]

        current_credits = char.get("credits", 1000)
        if current_credits < price:
            await ctx.session.send_line(
                f"  Not enough credits! {weapon.name} costs {price:,} credits "
                f"(base {base_price:,}), you have {current_credits:,}.")
            return
        new_credits = current_credits - price
        item = ItemInstance.new_from_vendor(weapon.key)
        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], credits=new_credits, equipment=char["equipment"])

        # Show haggle result
        pct = haggle["price_modifier_pct"]
        if pct != 0:
            direction = "discount" if pct < 0 else "markup"
            await ctx.session.send_line(
                f"  {ansi.DIM}Bargain {haggle['player_pool']}:"
                f" {haggle['player_roll']} vs vendor {haggle['npc_pool']}:"
                f" {haggle['npc_roll']}"
                f" → {abs(pct)}% {direction}{ansi.RESET}")
        await ctx.session.send_line(haggle["message"])
        await ctx.session.send_line(
            ansi.success(
                f"  Purchased and equipped {weapon.name} for {price:,} credits. "
                f"({new_credits:,} remaining)")
        )
        await ctx.session.send_line(f"  Condition: {item.condition_bar}")'''

    return safe_replace(source, OLD, NEW, "BuyCommand → Bargain haggle")


def patch_sell(source):
    """Patch SellCommand to include Bargain haggle on sell price."""

    OLD = '''\
    async def execute(self, ctx: CommandContext):
        from engine.items import parse_equipment_json, serialize_equipment
        from engine.weapons import get_weapon_registry

        char = ctx.session.character
        item = parse_equipment_json(char.get("equipment", "{}"))
        if not item:
            await ctx.session.send_line("  Nothing equipped to sell.")
            return

        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key
        base_cost = w.cost if w else 500

        # Sale price: 25-50% based on condition
        condition_factor = item.condition / max(item.max_condition, 1)
        sale_pct = 0.25 + (condition_factor * 0.25)  # 25% at broken, 50% at new
        sale_price = max(10, int(base_cost * sale_pct))

        # Quality bonus for crafted items
        if item.quality >= 80:
            sale_price = int(sale_price * 1.3)
        elif item.quality >= 60:
            sale_price = int(sale_price * 1.15)

        # World event sell price multiplier (e.g. trade_boom: +25%)
        try:
            from engine.world_events import get_world_event_manager
            _smult = get_world_event_manager().get_effect('sell_price_mult', 1.0)
            if _smult != 1.0:
                sale_price = int(sale_price * _smult)
        except Exception:
            pass

        credits = char.get("credits", 0)
        new_credits = credits + sale_price

        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(None)
        await ctx.db.save_character(
            char["id"], credits=new_credits, equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(
                f"  Sold {wname} ({item.condition_label}) for {sale_price:,} credits. "
                f"Balance: {new_credits:,} credits."))'''

    NEW = '''\
    async def execute(self, ctx: CommandContext):
        from engine.items import parse_equipment_json, serialize_equipment
        from engine.weapons import get_weapon_registry

        char = ctx.session.character
        item = parse_equipment_json(char.get("equipment", "{}"))
        if not item:
            await ctx.session.send_line("  Nothing equipped to sell.")
            return

        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key
        base_cost = w.cost if w else 500

        # Sale price: 25-50% based on condition
        condition_factor = item.condition / max(item.max_condition, 1)
        sale_pct = 0.25 + (condition_factor * 0.25)  # 25% at broken, 50% at new
        base_sale_price = max(10, int(base_cost * sale_pct))

        # Quality bonus for crafted items
        if item.quality >= 80:
            base_sale_price = int(base_sale_price * 1.3)
        elif item.quality >= 60:
            base_sale_price = int(base_sale_price * 1.15)

        # World event sell price multiplier (e.g. trade_boom: +25%)
        try:
            from engine.world_events import get_world_event_manager
            _smult = get_world_event_manager().get_effect('sell_price_mult', 1.0)
            if _smult != 1.0:
                base_sale_price = int(base_sale_price * _smult)
        except Exception:
            pass

        # ── Bargain haggle: player vs vendor ──
        npc_dice, npc_pips = 3, 0  # Default generic vendor: 3D Bargain
        try:
            import json as _json
            npcs = await ctx.db.get_npcs_in_room(char["room_id"])
            for npc in npcs:
                sheet = _json.loads(npc.get("char_sheet_json", "{}"))
                npc_skills = sheet.get("skills", {})
                bargain_str = npc_skills.get("bargain", "")
                if bargain_str:
                    from engine.skill_checks import _parse_dice_str
                    npc_dice, npc_pips = _parse_dice_str(bargain_str)
                    break  # Use first vendor NPC with Bargain skill
        except Exception:
            pass

        from engine.skill_checks import resolve_bargain_check
        haggle = resolve_bargain_check(
            char, base_sale_price,
            npc_bargain_dice=npc_dice, npc_bargain_pips=npc_pips,
            is_buying=False,
        )
        sale_price = haggle["adjusted_price"]

        credits = char.get("credits", 0)
        new_credits = credits + sale_price

        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(None)
        await ctx.db.save_character(
            char["id"], credits=new_credits, equipment=char["equipment"])

        # Show haggle result
        pct = haggle["price_modifier_pct"]
        if pct != 0:
            direction = "bonus" if pct > 0 else "penalty"
            await ctx.session.send_line(
                f"  {ansi.DIM}Bargain {haggle['player_pool']}:"
                f" {haggle['player_roll']} vs vendor {haggle['npc_pool']}:"
                f" {haggle['npc_roll']}"
                f" → {abs(pct)}% {direction}{ansi.RESET}")
        await ctx.session.send_line(haggle["message"])
        await ctx.session.send_line(
            ansi.success(
                f"  Sold {wname} ({item.condition_label}) for {sale_price:,} credits. "
                f"Balance: {new_credits:,} credits."))'''

    return safe_replace(source, OLD, NEW, "SellCommand → Bargain haggle")


def main():
    for target, patch_id in TARGETS:
        if not os.path.exists(target):
            print(f"ERROR: {target} not found. Run from project root.")
            sys.exit(1)

    # ── Patch BuyCommand in space_commands.py ──
    target = "parser/space_commands.py"
    backup = target + ".pre_bargain_bak"
    source = read_file(target)
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")

    patched = patch_buy(source)
    if patched is None:
        print("ABORT: Could not patch BuyCommand.")
        sys.exit(1)

    try:
        ast.parse(patched)
        print("  [OK] space_commands.py ast.parse passed")
    except SyntaxError as e:
        print(f"  [FAIL] SyntaxError in space_commands.py: {e}")
        sys.exit(1)

    with open(target, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"  Written: {target}")

    # ── Patch SellCommand in builtin_commands.py ──
    target = "parser/builtin_commands.py"
    backup = target + ".pre_bargain_bak"
    source = read_file(target)
    if not os.path.exists(backup):
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")

    patched = patch_sell(source)
    if patched is None:
        print("ABORT: Could not patch SellCommand.")
        sys.exit(1)

    try:
        ast.parse(patched)
        print("  [OK] builtin_commands.py ast.parse passed")
    except SyntaxError as e:
        print(f"  [FAIL] SyntaxError in builtin_commands.py: {e}")
        sys.exit(1)

    with open(target, "w", encoding="utf-8") as f:
        f.write(patched)
    print(f"  Written: {target}")

    print("\nDone. Bargain skill wired into buy and sell.")
    print("  - BuyCommand: opposed Bargain roll adjusts purchase price ±2-10%")
    print("  - SellCommand: opposed Bargain roll adjusts sell price ±2-10%")
    print("  - NPC vendor Bargain pool auto-detected from room NPCs")
    print("  - Falls back to 3D generic vendor if no NPC found")


if __name__ == "__main__":
    main()
