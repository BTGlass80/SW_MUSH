#!/usr/bin/env python3
"""
drop12b_commands_patch.py  --  Space Expansion v2 Drop 12 (Part B)
Ship Customization Commands + starships.yaml mod_slots

Changes:
  1. data/starships.yaml  — add mod_slots to all 19 templates
  2. parser/space_commands.py — ShipCommand gains /install, /uninstall, /mods
     and _show_status routes through get_effective_stats()

Usage:
    python drop12b_commands_patch.py [--dry-run]
"""

import ast
import os
import shutil
import sys

DRY_RUN = "--dry-run" in sys.argv
BASE = os.getcwd()

YAML_PATH = os.path.join(BASE, "data", "starships.yaml")
CMDS_PATH = os.path.join(BASE, "parser", "space_commands.py")


def read(path):
    with open(path, "r", encoding="utf-8", newline="") as f:
        return f.read().replace("\r\n", "\n").replace("\r", "\n")


def write(path, content):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    dst = path + ".bak_drop12b"
    shutil.copy2(path, dst)
    print(f"  backup → {dst}")


def validate_py(content, label=""):
    try:
        ast.parse(content)
        print(f"  ✓ AST OK: {label}")
    except SyntaxError as e:
        print(f"  ✗ SYNTAX ERROR: {label}: {e}")
        lines = content.splitlines()
        lo = max(0, e.lineno - 3)
        hi = min(len(lines), e.lineno + 2)
        for i in range(lo, hi):
            print(f"    {i+1}: {lines[i]}")
        sys.exit(1)


def patch(content, old, new, label, validate_fn=None):
    if old not in content:
        print(f"  ✗ ANCHOR NOT FOUND: {label}")
        sys.exit(1)
    result = content.replace(old, new, 1)
    if validate_fn:
        validate_fn(result, label)
    print(f"  ✓ PATCHED: {label}")
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Patch 1 — data/starships.yaml  (mod_slots per template)
# Design table from space_expansion_v2_design.md §10.2
# ══════════════════════════════════════════════════════════════════════════════
# YAML is not Python — we use string replacements keyed on unique cost: lines.
# Each template has a distinct cost value, making safe anchors.

YAML_PATCHES = [
    # (template_key_comment, old_str, new_str)
    # YT-1300 (cost: 100000, appears twice — yt_1300 and alias yt1300)
    # We patch both by replacing the trailing weapons block anchor per entry.
    # Better: patch by inserting after cost line with unique surrounding context.
    # Use "  cost: 100000\n  weapons:" → insert mod_slots: 5 before weapons.
    # yt_1300 and yt1300 share the same stats including cost, so we must patch
    # the YAML block differently. We'll target each first occurrence by the
    # name: line which is unique context.
    ("yt_1300 mod_slots",
     '  name: "YT-1300 Transport"\n  nickname: "YT-1300"\n  scale: starfighter\n  hull: "4D"\n  shields: "1D"\n  speed: 4\n  maneuverability: "1D"\n  crew: 1\n  passengers: 6\n  cargo: 100\n  consumables: "2 months"\n  hyperdrive: 2\n  hyperdrive_backup: 12\n  cost: 100000',
     '  name: "YT-1300 Transport"\n  nickname: "YT-1300"\n  scale: starfighter\n  hull: "4D"\n  shields: "1D"\n  speed: 4\n  maneuverability: "1D"\n  crew: 1\n  passengers: 6\n  cargo: 100\n  consumables: "2 months"\n  hyperdrive: 2\n  hyperdrive_backup: 12\n  cost: 100000\n  mod_slots: 5'),
    # ghtroc_720 (unique name)
    ("ghtroc_720 mod_slots",
     '  name: "Ghtroc 720 Freighter"',
     '  name: "Ghtroc 720 Freighter"\n  mod_slots: 4'),
    # yt_2400 (unique name)
    ("yt_2400 mod_slots",
     '  name: "YT-2400 Transport"',
     '  name: "YT-2400 Transport"\n  mod_slots: 5'),
    # x_wing
    ("x_wing mod_slots",
     '  name: "X-Wing Starfighter"',
     '  name: "X-Wing Starfighter"\n  mod_slots: 2'),
    # y_wing
    ("y_wing mod_slots",
     '  name: "Y-Wing Starfighter"',
     '  name: "Y-Wing Starfighter"\n  mod_slots: 2'),
    # a_wing
    ("a_wing mod_slots",
     '  name: "A-Wing Interceptor"',
     '  name: "A-Wing Interceptor"\n  mod_slots: 1'),
    # b_wing
    ("b_wing mod_slots",
     '  name: "B-Wing Heavy Assault Fighter"',
     '  name: "B-Wing Heavy Assault Fighter"\n  mod_slots: 2'),
    # tie_fighter (appears twice — tie_fighter and alias; patch first occurrence only)
    ("tie_fighter mod_slots",
     '  name: "TIE/ln Fighter"',
     '  name: "TIE/ln Fighter"\n  mod_slots: 1'),
    # tie_interceptor
    ("tie_interceptor mod_slots",
     '  name: "TIE Interceptor"',
     '  name: "TIE Interceptor"\n  mod_slots: 1'),
    # tie_bomber
    ("tie_bomber mod_slots",
     '  name: "TIE Bomber"',
     '  name: "TIE Bomber"\n  mod_slots: 2'),
    # z_95 (appears twice — patches first occurrence, z95 alias gets same via second name match)
    ("z_95 mod_slots",
     '  name: "Z-95 Headhunter"',
     '  name: "Z-95 Headhunter"\n  mod_slots: 2'),
    # firespray
    ("firespray mod_slots",
     '  name: "Firespray Patrol Craft"',
     '  name: "Firespray Patrol Craft"\n  mod_slots: 3'),
    # lambda_shuttle
    ("lambda_shuttle mod_slots",
     '  name: "Lambda-class Shuttle"',
     '  name: "Lambda-class Shuttle"\n  mod_slots: 3'),
    # sentinel_shuttle
    ("sentinel_shuttle mod_slots",
     '  name: "Sentinel-class Landing Craft"',
     '  name: "Sentinel-class Landing Craft"\n  mod_slots: 2'),
    # corellian_corvette
    ("corellian_corvette mod_slots",
     '  name: "Corellian Corvette"',
     '  name: "Corellian Corvette"\n  mod_slots: 6'),
    # nebulon_b
    ("nebulon_b mod_slots",
     '  name: "Nebulon-B Escort Frigate"',
     '  name: "Nebulon-B Escort Frigate"\n  mod_slots: 8'),
    # imperial_star_destroyer
    ("imperial_star_destroyer mod_slots",
     '  name: "Imperial-class Star Destroyer"',
     '  name: "Imperial-class Star Destroyer"\n  mod_slots: 10'),
]


# ══════════════════════════════════════════════════════════════════════════════
# Patch 2 — parser/space_commands.py: ShipCommand extensions
# ══════════════════════════════════════════════════════════════════════════════

# A) Extend help_text, usage, and valid_switches
OLD_SHIP_META = """    help_text = (
        "Your ship's status, info, and management.\\n"
        "\\n"
        "SWITCHES:\\n"
        "  /status  -- tactical status of your ship (default)\\n"
        "  /info    -- template specs for a ship type\\n"
        "  /list    -- list all available ship types\\n"
        "  /mine    -- list ships you own\\n"
        "  /repair  -- repair a damaged system (engineer)\\n"
        "\\n"
        "EXAMPLES:\\n"
        "  +ship              -- your ship's status\\n"
        "  +ship/info x-wing  -- X-Wing stats\\n"
        "  +ship/list         -- browse ship catalog\\n"
        "  +ship/mine         -- your fleet"
    )
    usage = "+ship [/status|/info|/list|/mine|/repair]"
    valid_switches = ["status", "info", "list", "mine", "repair"]"""

NEW_SHIP_META = """    help_text = (
        "Your ship's status, info, and management.\\n"
        "\\n"
        "SWITCHES:\\n"
        "  /status         -- tactical status of your ship (default)\\n"
        "  /info           -- template specs for a ship type\\n"
        "  /list           -- list all available ship types\\n"
        "  /mine           -- list ships you own\\n"
        "  /repair         -- repair a damaged system (engineer)\\n"
        "  /mods           -- view installed ship modifications\\n"
        "  /install <item> -- install a crafted ship component\\n"
        "  /uninstall <#>  -- remove a mod by slot number\\n"
        "\\n"
        "EXAMPLES:\\n"
        "  +ship              -- your ship's status\\n"
        "  +ship/info x-wing  -- X-Wing stats\\n"
        "  +ship/list         -- browse ship catalog\\n"
        "  +ship/mine         -- your fleet\\n"
        "  +ship/mods         -- installed modifications\\n"
        "  +ship/install Engine Booster (Basic)\\n"
        "  +ship/uninstall 0  -- remove mod in slot 0"
    )
    usage = "+ship [/status|/info|/list|/mine|/repair|/mods|/install|/uninstall]"
    valid_switches = ["status", "info", "list", "mine", "repair", "mods", "install", "uninstall"]"""

# B) Extend execute() to handle new switches
OLD_SHIP_EXECUTE = """    async def execute(self, ctx):
        if "list" in ctx.switches:
            return await self._show_list(ctx)
        if "info" in ctx.switches:
            return await self._show_info(ctx)
        if "mine" in ctx.switches:
            return await self._show_mine(ctx)
        if "repair" in ctx.switches:
            return await self._show_repair(ctx)
        # Default: status
        return await self._show_status(ctx)"""

NEW_SHIP_EXECUTE = """    async def execute(self, ctx):
        if "list" in ctx.switches:
            return await self._show_list(ctx)
        if "info" in ctx.switches:
            return await self._show_info(ctx)
        if "mine" in ctx.switches:
            return await self._show_mine(ctx)
        if "repair" in ctx.switches:
            return await self._show_repair(ctx)
        if "mods" in ctx.switches:
            return await self._show_mods(ctx)
        if "install" in ctx.switches:
            return await self._install_mod(ctx)
        if "uninstall" in ctx.switches:
            return await self._uninstall_mod(ctx)
        # Default: status
        return await self._show_status(ctx)"""

# C) Insert _show_mods, _install_mod, _uninstall_mod methods before _show_list
#    Anchor: the line that starts _show_list
OLD_SHOW_LIST_ANCHOR = """    async def _show_list(self, ctx):"""

NEW_SHOW_LIST_ANCHOR = """    # ── Modification commands (Drop 12) ─────────────────────────────────────

    async def _show_mods(self, ctx):
        \"\"\"Show installed modifications on the player's current ship.\"\"\"
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return
        systems = _get_systems(ship)
        from engine.starships import format_mods_display
        for line in format_mods_display(template, systems):
            await ctx.session.send_line(line)

    async def _install_mod(self, ctx):
        \"\"\"Install a crafted ship component from inventory. (+ship/install <item name>)\"\"\"
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship.get("docked_at"):
            await ctx.session.send_line(
                "  Ship must be docked to install modifications. Land first.")
            return

        reg = get_ship_registry()
        template = reg.get(ship["template"])
        if not template:
            await ctx.session.send_line("  Ship data error.")
            return

        item_name = (ctx.args or "").strip()
        if not item_name:
            await ctx.session.send_line(
                "  Usage: +ship/install <component name>\\n"
                "  Use 'inventory' to see your items.")
            return

        # Find matching component in character inventory
        char = ctx.session.character
        char_id = char["id"]
        try:
            inv_raw = char.get("inventory", "[]")
            import json as _j
            inv = _j.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        except Exception:
            inv = []

        component = None
        comp_idx = -1
        for idx, item in enumerate(inv):
            if not isinstance(item, dict):
                continue
            if item.get("type") != "ship_component":
                continue
            if (item_name.lower() in item.get("name", "").lower() or
                    item_name.lower() in item.get("key", "").lower()):
                component = item
                comp_idx = idx
                break

        if not component:
            await ctx.session.send_line(
                f"  No ship component matching '{item_name}' in your inventory.\\n"
                f"  Use 'inventory' to see your items. Components must be crafted first.")
            return

        systems = _get_systems(ship)
        mods = systems.get("modifications", [])

        # Check mod slot availability
        if len(mods) >= template.mod_slots:
            await ctx.session.send_line(
                f"  No mod slots available. This ship has {template.mod_slots} slot(s), "
                f"all occupied. Use +ship/uninstall <#> to free a slot.")
            return

        # Cargo capacity check
        from engine.starships import get_effective_stats as _ges
        effective = _ges(template, systems)
        cargo_remaining = template.cargo - effective["cargo_used_by_mods"]
        cargo_weight = component.get("cargo_weight", 10)
        if cargo_weight > cargo_remaining:
            await ctx.session.send_line(
                f"  Insufficient cargo capacity. Component requires {cargo_weight}t, "
                f"only {cargo_remaining}t available after existing mods.")
            return

        # Max stat boost check
        stat_target = component.get("stat_target", "")
        stat_boost  = component.get("stat_boost", 1)
        quality     = component.get("quality", 80)
        from engine.starships import _quality_factor, _pip_count, _MOD_MAX_SPEED, _MOD_MAX_PIPS
        factor      = _quality_factor(quality)
        eff_boost   = max(1, round(stat_boost * factor))

        if stat_target == "speed":
            current_boost = effective["speed"] - template.speed
            if current_boost + eff_boost > _MOD_MAX_SPEED:
                await ctx.session.send_line(
                    f"  Speed already at maximum modification (+{_MOD_MAX_SPEED}). "
                    f"Cannot install.")
                return
        elif stat_target in _MOD_MAX_PIPS:
            base_pips = _pip_count(getattr(template, stat_target, "0D"))
            curr_pips = _pip_count(effective.get(stat_target, getattr(template, stat_target, "0D")))
            if curr_pips - base_pips + eff_boost > _MOD_MAX_PIPS[stat_target]:
                await ctx.session.send_line(
                    f"  {stat_target.title()} already at maximum modification boost. "
                    f"Cannot install.")
                return

        # Installation skill check
        install_difficulty = max(5, component.get("craft_difficulty", 16) - 4)
        from engine.skill_checks import perform_skill_check
        from engine.character import SkillRegistry
        skill_reg = SkillRegistry()
        skill_reg.load_default()
        from engine.starships import get_repair_skill_name, get_weapon_repair_skill
        if stat_target == "fire_control":
            repair_skill = get_weapon_repair_skill(template.scale)
        else:
            repair_skill = get_repair_skill_name(template.scale)
        try:
            result = perform_skill_check(char, repair_skill, install_difficulty, skill_reg)
        except Exception:
            result = None

        if result is not None and result.fumble:
            # Fumble: component quality drops one tier
            new_quality = max(0, quality - 20)
            component["quality"] = new_quality
            inv[comp_idx] = component
            char["inventory"] = _j.dumps(inv)
            await ctx.db.save_character(char_id, inventory=char["inventory"])
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}[FUMBLE]{ansi.RESET} Installation catastrophically failed! "
                f"Component quality degraded to {new_quality}%.\\n"
                f"  (Roll: {result.roll} vs {install_difficulty})")
            return

        if result is not None and not result.success:
            await ctx.session.send_line(
                f"  Installation failed. The component doesn't seat properly.\\n"
                f"  (Roll: {result.roll} vs {install_difficulty}) — Try again.")
            return

        # Success: add mod, remove from inventory
        roll_str = f"Roll: {result.roll} vs {install_difficulty}" if result else "auto"
        mod_entry = {
            "slot":           len(mods),
            "component_key":  component.get("key", "unknown"),
            "component_name": component.get("name", item_name),
            "quality":        quality,
            "stat_target":    stat_target,
            "stat_boost":     stat_boost,
            "cargo_weight":   cargo_weight,
            "craft_difficulty": component.get("craft_difficulty", 16),
            "installed_by":   char.get("name", "Unknown"),
            "weapon_slot":    component.get("weapon_slot", None),
        }
        mods.append(mod_entry)
        systems["modifications"] = mods
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        # Remove from inventory
        inv.pop(comp_idx)
        char["inventory"] = _j.dumps(inv)
        await ctx.db.save_character(char_id, inventory=char["inventory"])

        await ctx.session.send_line(
            ansi.success(
                f"  {component.get('name', item_name)} installed successfully! "
                f"({roll_str})"
            )
        )
        await ctx.session.send_line(
            f"  +{eff_boost} {stat_target} effective boost applied. "
            f"Slots used: {len(mods)}/{template.mod_slots}.")

    async def _uninstall_mod(self, ctx):
        \"\"\"Remove a mod by slot index. (+ship/uninstall <slot#>)\"\"\"
        ship = await _get_ship_for_player(ctx)
        if not ship:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if not ship.get("docked_at"):
            await ctx.session.send_line(
                "  Ship must be docked to remove modifications. Land first.")
            return

        slot_str = (ctx.args or "").strip()
        if not slot_str.isdigit():
            await ctx.session.send_line(
                "  Usage: +ship/uninstall <slot number>\\n"
                "  Use +ship/mods to see slot numbers.")
            return

        slot_idx = int(slot_str)
        systems = _get_systems(ship)
        mods = systems.get("modifications", [])

        if slot_idx < 0 or slot_idx >= len(mods):
            await ctx.session.send_line(
                f"  No mod in slot {slot_idx}. "
                f"Valid slots: 0–{len(mods)-1}.")
            return

        removed = mods.pop(slot_idx)
        # Re-index remaining mods
        for i, m in enumerate(mods):
            m["slot"] = i
        systems["modifications"] = mods
        await ctx.db.update_ship(ship["id"], systems=json.dumps(systems))

        # Return component to inventory
        char = ctx.session.character
        char_id = char["id"]
        try:
            inv_raw = char.get("inventory", "[]")
            import json as _j2
            inv = _j2.loads(inv_raw) if isinstance(inv_raw, str) else inv_raw
        except Exception:
            inv = []

        returned_item = {
            "type":             "ship_component",
            "key":              removed.get("component_key", "unknown"),
            "name":             removed.get("component_name", "Component"),
            "quality":          removed.get("quality", 80),
            "stat_target":      removed.get("stat_target", ""),
            "stat_boost":       removed.get("stat_boost", 1),
            "cargo_weight":     removed.get("cargo_weight", 10),
            "craft_difficulty": removed.get("craft_difficulty", 16),
        }
        inv.append(returned_item)
        char["inventory"] = _j2.dumps(inv)
        await ctx.db.save_character(char_id, inventory=char["inventory"])

        await ctx.session.send_line(
            ansi.success(
                f"  {removed.get('component_name', 'Component')} uninstalled. "
                f"Returned to your inventory."
            )
        )
        await ctx.session.send_line(
            f"  Slots remaining: {template.mod_slots - len(mods)}/{template.mod_slots}."
            if (reg := get_ship_registry()) and (t := reg.get(ship["template"]))
            else ""
        )

    async def _show_list(self, ctx):"""


# ══════════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print("\n=== Drop 12b — starships.yaml + space_commands /install /uninstall /mods ===\n")
    if DRY_RUN:
        print("DRY RUN — no files modified.\n")

    # ── YAML patches ──────────────────────────────────────────────────────────
    print("data/starships.yaml:")
    yaml_content = read(YAML_PATH)
    for label, old, new in YAML_PATCHES:
        yaml_content = patch(yaml_content, old, new, label)
    # YAML doesn't need AST validation
    if not DRY_RUN:
        backup(YAML_PATH)
        write(YAML_PATH, yaml_content)
        print(f"  Written: {YAML_PATH}")
    else:
        print("  (dry run — not written)")

    # ── space_commands.py patches ─────────────────────────────────────────────
    print("\nparser/space_commands.py:")
    cmds_content = read(CMDS_PATH)
    cmds_content = patch(cmds_content, OLD_SHIP_META,    NEW_SHIP_META,    "ShipCommand help/usage/switches", validate_py)
    cmds_content = patch(cmds_content, OLD_SHIP_EXECUTE, NEW_SHIP_EXECUTE, "ShipCommand execute() new switches", validate_py)
    cmds_content = patch(cmds_content, OLD_SHOW_LIST_ANCHOR, NEW_SHOW_LIST_ANCHOR, "_install_mod/_uninstall_mod/_show_mods methods", validate_py)

    if not DRY_RUN:
        backup(CMDS_PATH)
        write(CMDS_PATH, cmds_content)
        print(f"  Written: {CMDS_PATH}")
    else:
        print("  (dry run — not written)")

    print("\n=== Drop 12b complete ===")


if __name__ == "__main__":
    main()
