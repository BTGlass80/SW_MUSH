#!/usr/bin/env python3
"""
Drop A — Help System Infrastructure Patch
==========================================
1. Rewrites HelpCommand in builtin_commands.py to use HelpManager
2. Wires HelpManager initialization into game_server.py boot sequence

Requires: data/help_topics.py (delivered with this drop)
Requires: Drop 1 (parser infra — switches support for +help/search)
Requires: Drop 2 (alias sweep — + prefixed canonical names)

Run from project root:  python patches/patch_help_system.py
"""
import os
import sys
import ast
import shutil
from datetime import datetime

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

BUILTIN_PY = os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py")
GAME_SERVER = os.path.join(PROJECT_ROOT, "server", "game_server.py")
# Also check root-level game_server.py
GAME_SERVER_ALT = os.path.join(PROJECT_ROOT, "game_server.py")


def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_{ts}"
    shutil.copy2(path, bak)
    print(f"  Backup: {bak}")
    return bak


def patch_help_command():
    """Replace HelpCommand class in builtin_commands.py."""
    print("\n── Patching HelpCommand in builtin_commands.py ──")

    if not os.path.isfile(BUILTIN_PY):
        print(f"  ERROR: {BUILTIN_PY} not found")
        return False

    backup(BUILTIN_PY)
    src = open(BUILTIN_PY, "r", encoding="utf-8").read()

    # Find the HelpCommand class boundaries
    anchor_start = 'class HelpCommand(BaseCommand):'
    if anchor_start not in src:
        print("  ERROR: Could not find HelpCommand class")
        return False

    # Find the next class definition after HelpCommand to know where it ends
    start_idx = src.index(anchor_start)

    # Find the class after HelpCommand
    # Look for the next "class " at the same indent level
    rest = src[start_idx + len(anchor_start):]
    # Find next class definition (not indented, i.e., at column 0)
    import re
    match = re.search(r'\nclass \w+', rest)
    if match:
        end_idx = start_idx + len(anchor_start) + match.start()
    else:
        print("  ERROR: Could not find end of HelpCommand class")
        return False

    new_help_command = '''class HelpCommand(BaseCommand):
    key = "+help"
    aliases = ["help", "?", "commands", "+commands"]
    help_text = "Show available commands and help topics."
    usage = "+help [topic|command]  |  +help/search <keyword>"
    valid_switches = ["search"]
    access_level = AccessLevel.ANYONE

    # HelpManager is injected at boot by game_server.py
    _help_mgr = None

    CATEGORIES = {
        "Navigation": ["look", "move", "board", "disembark"],
        "Communication": ["say", "whisper", "emote", ";", "+ooc",
                          "comlink", "fcomm"],
        "Character": ["+sheet", "+inv", "equip", "unequip",
                       "+weapons", "+credits", "+repair", "sell", "@desc"],
        "D6 Dice": ["+roll", "+check", "+opposed"],
        "Combat": ["attack", "dodge", "fulldodge", "parry", "fullparry",
                    "aim", "cover", "flee", "forcepoint", "range",
                    "+combat", "resolve", "pass", "disengage", "respawn"],
        "Force": ["force", "+powers", "+forcestatus"],
        "Advancement": ["+cpstatus", "train", "+kudos", "+scenebonus"],
        "Economy": ["buy", "sell", "+credits",
                     "+missions", "accept", "+mission", "complete",
                     "abandon"],
        "Smuggling": ["+smugjobs", "smugaccept", "+smugjob",
                       "smugdeliver", "smugdump"],
        "Bounty": ["+bounties", "bountyclaim", "+mybounty",
                    "bountytrack", "bountycollect"],
        "Crafting": ["survey", "resources", "buyresource",
                      "schematics", "craft"],
        "Medical": ["heal", "healaccept", "+healrate"],
        "Space": ["+ships", "+shipinfo", "pilot", "gunner", "copilot",
                  "engineer", "navigator", "commander", "sensors",
                  "vacate", "assist", "coordinate", "+shiprepair",
                  "+myships", "launch", "land", "scan", "fire", "evade",
                  "+shipstatus", "close", "fleeship", "tail",
                  "outmaneuver", "shields", "hyperspace", "damcon"],
        "NPC Crew": ["hire", "+roster", "assign", "unassign",
                      "dismiss", "order"],
        "NPCs": ["talk", "ask"],
        "Channels": ["+channels", "comlink", "fcomm", "+faction",
                      "tune", "untune", "+freqs", "commfreq"],
        "Social": ["+party", "sabacc", "perform", "+news"],
        "Building": ["@dig", "@tunnel", "@open", "@rdesc", "@rname",
                     "@destroy", "@link", "@unlink", "@examine",
                     "@rooms", "@teleport", "@set", "@lock",
                     "@entrances", "@find", "@zone",
                     "@create", "@npc", "@spawn"],
        "Admin": ["@grant", "@ai", "@director", "@setbounty"],
        "Info": ["+who", "+help", "quit"],
    }

    # Topic keywords — these map to help_topics entries, not commands
    TOPIC_KEYWORDS = {
        "dice", "d6", "wilddie", "attributes", "skills", "difficulty",
        "combat", "ranged", "melee", "wounds", "dodge", "cover",
        "multiaction", "armor", "scale", "force", "forcepoints",
        "darkside", "lightsaber", "cp", "advancement", "space",
        "spacecombat", "crew", "hyperdrive", "sensors", "moseisley",
        "cantina", "tatooine", "trading", "smuggling", "bounty",
        "species", "rp", "newbie", "commands", "channels", "building",
    }

    async def execute(self, ctx: CommandContext):
        # Handle /search switch
        if "search" in ctx.switches:
            if not ctx.args:
                await ctx.session.send_line("  Usage: +help/search <keyword>")
                return
            await self._search_help(ctx, ctx.args.strip())
            return

        if ctx.args:
            await self._specific_help(ctx)
            return

        # Default: show category overview
        await self._show_categories(ctx)

    async def _show_categories(self, ctx):
        """Show the command category overview."""
        await ctx.session.send_line("")
        await ctx.session.send_line(
            ansi.header("═" * 70))
        await ctx.session.send_line(
            ansi.header("  STAR WARS D6 MUSH — Command Reference"))
        await ctx.session.send_line(
            ansi.header("═" * 70))
        await ctx.session.send_line("")

        for cat, cmds in self.CATEGORIES.items():
            # Skip admin categories for non-admins
            if cat in ("Building", "Admin"):
                if not (ctx.session.account
                        and ctx.session.account.get("is_admin", 0)):
                    continue
            cmd_str = ", ".join(
                f"{ansi.BRIGHT_CYAN}{c}{ansi.RESET}" for c in cmds)
            await ctx.session.send_line(
                f"  {ansi.BOLD}{cat:14s}{ansi.RESET} {cmd_str}")

        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type '+help <command>' for command details.{ansi.RESET}")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type '+help <topic>' for rules help "
            f"(combat, dice, wounds, force, space...){ansi.RESET}")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type '+help/search <keyword>' to search "
            f"all help files.{ansi.RESET}")
        await ctx.session.send_line("")

    async def _specific_help(self, ctx):
        """Show help for a specific command or topic."""
        name = ctx.args.strip().lower()
        mgr = self.__class__._help_mgr

        # Try HelpManager first (covers both topics and commands)
        if mgr:
            entry = mgr.get(name)
            if entry:
                await self._render_entry(ctx, entry)
                return

        # Fallback: check if it's a command in CATEGORIES
        all_cmds = {}
        for cat, cmd_names in self.CATEGORIES.items():
            for cn in cmd_names:
                all_cmds[cn.lower()] = cat

        if name in all_cmds:
            await ctx.session.send_line(
                f"  {ansi.BOLD}{name}{ansi.RESET} "
                f"(Category: {all_cmds[name]})")
            await ctx.session.send_line(
                f"  {ansi.DIM}No detailed help available yet.{ansi.RESET}")
            await ctx.session.send_line("")
            return

        # Try without + prefix
        if not name.startswith("+") and ("+" + name) in all_cmds:
            await ctx.session.send_line(
                f"  {ansi.BOLD}+{name}{ansi.RESET} "
                f"(Category: {all_cmds['+' + name]})")
            await ctx.session.send_line(
                f"  {ansi.DIM}No detailed help available yet.{ansi.RESET}")
            await ctx.session.send_line("")
            return

        await ctx.session.send_line(f"  No help found for '{name}'.")
        await ctx.session.send_line(
            f"  {ansi.DIM}Try '+help/search {name}' to search.{ansi.RESET}")
        await ctx.session.send_line("")

    async def _search_help(self, ctx, keyword):
        """Search all help entries by keyword."""
        mgr = self.__class__._help_mgr
        if not mgr:
            await ctx.session.send_line("  Help system not initialized.")
            return

        results = mgr.search(keyword)
        if not results:
            await ctx.session.send_line(
                f"  No help entries found matching '{keyword}'.")
            return

        await ctx.session.send_line("")
        await ctx.session.send_line(
            ansi.header(f"  Search results for '{keyword}':"))
        await ctx.session.send_line("")
        for entry in results[:15]:  # Cap at 15 results
            title = entry.title
            cat = entry.category
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}{entry.key:20s}{ansi.RESET} "
                f"{title:30s} {ansi.DIM}[{cat}]{ansi.RESET}")
        if len(results) > 15:
            await ctx.session.send_line(
                f"  {ansi.DIM}...and {len(results) - 15} more.{ansi.RESET}")
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.DIM}Type '+help <name>' for details.{ansi.RESET}")
        await ctx.session.send_line("")

    async def _render_entry(self, ctx, entry):
        """Render a single HelpEntry with ANSI formatting."""
        send = ctx.session.send_line
        w = 70  # display width

        await send("")
        await send(ansi.header("═" * w))

        # Title line with category right-aligned
        title = f"  {entry.title}"
        cat_tag = f"[{entry.category}]"
        padding = w - len(title) - len(cat_tag) - 1
        if padding < 1:
            padding = 1
        await send(ansi.header(
            f"{title}{' ' * padding}{cat_tag}"))

        await send(ansi.header("═" * w))
        await send("")

        # Body text — send line by line
        for line in entry.body.split("\\n"):
            await send(f"  {line}")

        # See also
        if entry.see_also:
            await send("")
            refs = ", ".join(
                f"{ansi.BRIGHT_CYAN}{s}{ansi.RESET}"
                for s in entry.see_also)
            await send(f"  {ansi.DIM}SEE ALSO:{ansi.RESET} {refs}")

        await send("")
        await send(ansi.header("═" * w))
        await send("")

'''

    src = src[:start_idx] + new_help_command + src[end_idx:]
    print("  Replaced HelpCommand class")

    # Validate
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR: {e}")
        return False

    with open(BUILTIN_PY, "w", encoding="utf-8") as f:
        f.write(src)
    print("  AST validated and written successfully")
    return True


def find_game_server():
    """Find game_server.py — could be in root or server/."""
    for path in [GAME_SERVER_ALT, GAME_SERVER]:
        if os.path.isfile(path):
            return path
    return None


def patch_game_server():
    """Wire HelpManager initialization into game_server.py boot."""
    print("\n── Wiring HelpManager into game_server.py ──")

    gs_path = find_game_server()
    if not gs_path:
        print("  WARNING: game_server.py not found — manual wiring needed.")
        print("  Add after command registration in __init__:")
        print("    from data.help_topics import HelpManager")
        print("    help_mgr = HelpManager()")
        print("    help_mgr.auto_register_commands(self.registry)")
        print("    help_mgr.register_topics()")
        print("    from parser.builtin_commands import HelpCommand")
        print("    HelpCommand._help_mgr = help_mgr")
        return True

    src = open(gs_path, "r", encoding="utf-8").read()

    # Check if already wired
    if "HelpManager" in src:
        print("  Help system already wired — skipping")
        return True

    backup(gs_path)

    # Anchor: insert after the last register call block
    anchor = '        register_sabacc_commands(self.registry)\n\n        # AI system'
    if anchor not in src:
        # Try alternate anchors
        anchor = '        register_cp_commands(self.registry)\n\n        # AI system'
    if anchor not in src:
        print("  WARNING: Could not find injection anchor.")
        print("  Manual wiring needed (see above)")
        return True

    inject = '''        register_sabacc_commands(self.registry)

        # ── Help System Init ──
        from data.help_topics import HelpManager
        help_mgr = HelpManager()
        help_mgr.auto_register_commands(self.registry)
        help_mgr.register_topics()
        from parser.builtin_commands import HelpCommand
        HelpCommand._help_mgr = help_mgr
        log.info("Help system initialized: %d entries",
                 len(help_mgr._entries))

        # AI system'''

    src = src.replace(anchor, inject, 1)

    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR: {e}")
        print("  Manual wiring needed")
        return True

    with open(gs_path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"  Wired HelpManager into {os.path.basename(gs_path)}")
    return True


def main():
    print("=" * 60)
    print("  Drop A — Help System Infrastructure")
    print("  HelpManager, topic help, rewritten +help command")
    print("=" * 60)

    ok1 = patch_help_command()
    ok2 = patch_game_server()

    print("\n" + "=" * 60)
    if ok1:
        print("  HelpCommand rewritten successfully.")
        print("  data/help_topics.py provides 30+ topic help entries.")
        print("")
        print("  Test commands:")
        print("    +help              Category overview")
        print("    +help combat       Combat rules topic")
        print("    +help dice         D6 dice system topic")
        print("    +help wounds       Wound levels topic")
        print("    +help newbie       New player guide")
        print("    +help/search force Search all entries")
    else:
        print("  Some patches failed. Check output above.")
    print("=" * 60)


if __name__ == "__main__":
    main()
