#!/usr/bin/env python3
"""
Drop 1 — Parser Infrastructure Patch
=====================================
Patches parser/commands.py to add:
  1. Glued prefix extraction (' " : ;) — fixes broken single-char aliases
  2. Switch parsing (command/switch syntax)
  3. CommandContext.switches field
  4. BaseCommand.valid_switches field
  5. Switch validation in _execute()
  6. Updated DEAD_ALLOWED set with + prefixed forms

Also patches parser/builtin_commands.py to add:
  1. SemiposeCommand (;)
  2. '"' alias for SayCommand
  3. 'pose'/'em' aliases for EmoteCommand

Run from project root:  python patches/patch_parser_infra.py
"""
import os
import sys
import ast
import shutil
from datetime import datetime

# ── Resolve project root ──
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)
sys.path.insert(0, PROJECT_ROOT)

COMMANDS_PY = os.path.join(PROJECT_ROOT, "parser", "commands.py")
BUILTIN_PY = os.path.join(PROJECT_ROOT, "parser", "builtin_commands.py")

def backup(path):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = f"{path}.bak_{ts}"
    shutil.copy2(path, bak)
    print(f"  Backup: {bak}")
    return bak

def patch_commands_py():
    """Patch parser/commands.py with prefix extraction, switches, etc."""
    print("\n── Patching parser/commands.py ──")

    if not os.path.isfile(COMMANDS_PY):
        print(f"  ERROR: {COMMANDS_PY} not found")
        return False

    backup(COMMANDS_PY)
    src = open(COMMANDS_PY, "r", encoding="utf-8").read()

    # ── 1. Add switches to CommandContext ──
    anchor1 = '    args_list: list[str]     # Args split by whitespace\n    db: object = None        # Database reference'
    replacement1 = ('    args_list: list[str]     # Args split by whitespace\n'
                    '    switches: list[str] = field(default_factory=list)  # /switch flags\n'
                    '    db: object = None        # Database reference')
    if anchor1 not in src:
        lines = src.split('\n')
        inserted = False
        for i, line in enumerate(lines):
            if 'args_list: list[str]' in line and '# Args split by whitespace' in line:
                lines.insert(i + 1, '    switches: list[str] = field(default_factory=list)  # /switch flags')
                src = '\n'.join(lines)
                inserted = True
                print("  [1/6] Added switches field to CommandContext (alt anchor)")
                break
        if not inserted:
            print("  ERROR: Could not find CommandContext.args_list anchor")
            return False
    else:
        src = src.replace(anchor1, replacement1, 1)
        print("  [1/6] Added switches field to CommandContext")

    # ── 2. Add valid_switches to BaseCommand ──
    anchor2 = '    usage: str = ""                  # Usage string (e.g., "look [target]")'
    replacement2 = ('    usage: str = ""                  # Usage string (e.g., "look [target]")\n'
                    '    valid_switches: list[str] = []   # Accepted /switch names (empty = no validation)')
    if anchor2 not in src:
        print("  ERROR: Could not find BaseCommand.usage anchor")
        return False
    src = src.replace(anchor2, replacement2, 1)
    print("  [2/6] Added valid_switches field to BaseCommand")

    # ── 3. Replace parse_and_dispatch() ──
    anchor3_start = '    async def parse_and_dispatch(self, session: Session, raw_input: str):'
    anchor3_end = '        await self._execute(cmd, ctx)'
    if anchor3_start not in src:
        print("  ERROR: Could not find parse_and_dispatch start anchor")
        return False
    if anchor3_end not in src:
        print("  ERROR: Could not find parse_and_dispatch end anchor")
        return False

    start_idx = src.index(anchor3_start)
    end_idx = src.index(anchor3_end, start_idx)
    end_idx = end_idx + len(anchor3_end)

    new_parse_and_dispatch = '''    async def parse_and_dispatch(self, session: Session, raw_input: str):
        """Parse a line of input and execute the matching command."""
        raw_input = raw_input.strip()
        if not raw_input:
            await session.send_prompt()
            return

        # Rate limit check
        if not self._check_rate_limit(session):
            await session.send_line("  Slow down! Too many commands.")
            return

        # ── Prefix extraction ──────────────────────────────────────────
        # Single-char prefixes that glue to their arguments with no space:
        #   'hello  →  command "'", args "hello"
        #   :waves  →  command ":", args "waves"
        #   ;'s     →  command ";", args "'s"
        # The + and @ prefixes are part of the command word and need no
        # special extraction — "+sheet" splits normally on whitespace.
        GLUED_PREFIXES = {"'", '"', ":", ";"}
        first_char = raw_input[0]

        if first_char in GLUED_PREFIXES:
            cmd_name = first_char
            args_str = raw_input[1:].strip()
        else:
            # Expand direction aliases before splitting
            first_word = raw_input.split()[0].lower()
            if first_word in DIRECTION_ALIASES:
                raw_input = (DIRECTION_ALIASES[first_word]
                             + raw_input[len(first_word):])

            # Split into command and arguments
            parts = raw_input.split(None, 1)
            cmd_name = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

        # ── Switch extraction ──────────────────────────────────────────
        # "+sheet/brief"  →  cmd_name="+sheet", switches=["brief"]
        # "+help/search"  →  cmd_name="+help",  switches=["search"]
        # Glued prefixes never have switches (no such thing as ":/foo").
        switches = []
        if "/" in cmd_name and first_char not in GLUED_PREFIXES:
            switch_parts = cmd_name.split("/")
            cmd_name = switch_parts[0]
            switches = [s.lower() for s in switch_parts[1:] if s]

        # ── Build context ──────────────────────────────────────────────
        ctx = CommandContext(
            session=session,
            raw_input=raw_input,
            command=cmd_name,
            args=args_str,
            args_list=args_str.split() if args_str else [],
            switches=switches,
            db=self.db,
            session_mgr=self.session_mgr,
        )

        # ── Look up command ────────────────────────────────────────────
        cmd = self.registry.get(cmd_name)

        if cmd is None:
            # Try treating it as a direction (movement command)
            if cmd_name in (
                "north", "south", "east", "west", "up", "down",
                "northeast", "northwest", "southeast", "southwest",
                "enter", "leave",
            ):
                move_cmd = self.registry.get("move")
                if move_cmd:
                    ctx.args = cmd_name
                    ctx.args_list = [cmd_name]
                    await self._execute(move_cmd, ctx)
                    return

            # ── Natural Language Combat Intercept ──────────────────────
            # If the player is in active combat and types something that
            # isn't a registered command, try the IntentParser before
            # giving up.
            if session.character:
                from parser.combat_commands import try_nl_combat_action
                handled = await try_nl_combat_action(ctx, raw_input)
                if handled:
                    return

            await session.send_line(f"Huh? Unknown command: '{cmd_name}'")
            await session.send_prompt()
            return

        await self._execute(cmd, ctx)'''

    src = src[:start_idx] + new_parse_and_dispatch + src[end_idx:]
    print("  [3/6] Replaced parse_and_dispatch() with prefix/switch support")

    # ── 4. Update DEAD_ALLOWED set ──
    anchor4 = '    DEAD_ALLOWED = {"respawn", "look", "l", "help", "?", "commands", "who", "quit"}'
    replacement4 = ('    DEAD_ALLOWED = {\n'
                    '        "respawn", "look", "l",\n'
                    '        "help", "+help", "?", "commands", "+commands",\n'
                    '        "who", "+who", "quit", "@quit", "logout",\n'
                    '    }')
    if anchor4 not in src:
        print("  WARNING: Could not find DEAD_ALLOWED anchor — skipping")
    else:
        src = src.replace(anchor4, replacement4, 1)
        print("  [4/6] Updated DEAD_ALLOWED set with + prefixed forms")

    # ── 5. Add switch validation to _execute() ──
    anchor5 = '''        if not await cmd.check_access(ctx):
            await ctx.session.send_line("You don't have permission to do that.")
            await ctx.session.send_prompt()
            return'''
    replacement5 = '''        if not await cmd.check_access(ctx):
            await ctx.session.send_line("You don't have permission to do that.")
            await ctx.session.send_prompt()
            return

        # ── Switch validation ──
        if cmd.valid_switches and ctx.switches:
            bad = [s for s in ctx.switches if s not in cmd.valid_switches]
            if bad:
                valid_str = ", ".join("/" + s for s in cmd.valid_switches)
                await ctx.session.send_line(
                    f"  Unknown switch: /{bad[0]}. Valid: {valid_str}"
                )
                await ctx.session.send_prompt()
                return'''
    if anchor5 not in src:
        print("  WARNING: Could not find check_access anchor for switch validation")
    else:
        src = src.replace(anchor5, replacement5, 1)
        print("  [5/6] Added switch validation to _execute()")

    # ── 6. Validate and write ──
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR: {e}")
        print("  Aborting — file not written. Backup is safe.")
        return False

    with open(COMMANDS_PY, "w", encoding="utf-8") as f:
        f.write(src)
    print("  [6/6] AST validated and written successfully")
    return True


def patch_builtin_py():
    """Patch parser/builtin_commands.py to add SemiposeCommand and fix aliases."""
    print("\n── Patching parser/builtin_commands.py ──")

    if not os.path.isfile(BUILTIN_PY):
        print(f"  ERROR: {BUILTIN_PY} not found")
        return False

    backup(BUILTIN_PY)
    src = open(BUILTIN_PY, "r", encoding="utf-8").read()

    # ── 1. Fix SayCommand aliases — add '"' ──
    anchor1 = '''class SayCommand(BaseCommand):
    key = "say"
    aliases = ["'"]'''
    replacement1 = '''class SayCommand(BaseCommand):
    key = "say"
    aliases = ["'", '"']'''
    if anchor1 not in src:
        print('  WARNING: Could not find SayCommand alias anchor')
    else:
        src = src.replace(anchor1, replacement1, 1)
        print('  [1/4] Added \'"\' alias to SayCommand')

    # ── 2. Add more aliases to EmoteCommand ──
    anchor2 = '''class EmoteCommand(BaseCommand):
    key = "emote"
    aliases = [":"]'''
    replacement2 = '''class EmoteCommand(BaseCommand):
    key = "emote"
    aliases = [":", "pose", "em"]'''
    if anchor2 not in src:
        print("  WARNING: Could not find EmoteCommand alias anchor")
    else:
        src = src.replace(anchor2, replacement2, 1)
        print("  [2/4] Added pose/em aliases to EmoteCommand")

    # ── 3. Add SemiposeCommand before register_all ──
    semipose_class = '''

class SemiposeCommand(BaseCommand):
    key = ";"
    aliases = ["semipose"]
    help_text = "Emote with your name glued to the text (no space)."
    usage = ";'s lightsaber hums.  →  Tundra's lightsaber hums."

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Semipose what?")
            return
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("You must be in the game to do that.")
            return
        name = ansi.player_name(char["name"])
        # No space between name and args — that's the whole point
        text = f"{name}{ctx.args}"
        room_id = char["room_id"]
        for s in ctx.session_mgr.sessions_in_room(room_id):
            await s.send_line(text)


'''

    anchor3 = 'def register_all(registry):'
    if anchor3 not in src:
        print("  ERROR: Could not find register_all anchor")
        return False
    src = src.replace(anchor3, semipose_class + anchor3, 1)
    print("  [3/4] Added SemiposeCommand class")

    # ── 4. Register SemiposeCommand in register_all ──
    anchor4 = '        RespawnCommand(),'
    replacement4 = '        RespawnCommand(),\n        SemiposeCommand(),'
    if anchor4 not in src:
        anchor4_alt = '        WeaponsListCommand(),\n        RespawnCommand(),'
        if anchor4_alt in src:
            replacement4_alt = '        WeaponsListCommand(),\n        RespawnCommand(),\n        SemiposeCommand(),'
            src = src.replace(anchor4_alt, replacement4_alt, 1)
            print("  [4/4] Registered SemiposeCommand (alt anchor)")
        else:
            print("  WARNING: Could not find RespawnCommand registration anchor")
    else:
        src = src.replace(anchor4, replacement4, 1)
        print("  [4/4] Registered SemiposeCommand")

    # ── Validate and write ──
    try:
        ast.parse(src)
    except SyntaxError as e:
        print(f"  SYNTAX ERROR: {e}")
        print("  Aborting — file not written. Backup is safe.")
        return False

    with open(BUILTIN_PY, "w", encoding="utf-8") as f:
        f.write(src)
    print("  AST validated and written successfully")
    return True


def main():
    print("=" * 60)
    print("  Drop 1 — Parser Infrastructure Patch")
    print("  Prefix extraction, switch parsing, semipose")
    print("=" * 60)

    ok1 = patch_commands_py()
    ok2 = patch_builtin_py()

    print("\n" + "=" * 60)
    if ok1 and ok2:
        print("  All patches applied successfully.")
        print("  Run the server and test:")
        print("    'hello          →  say hello")
        print("    :waves          →  emote waves")
        print("    ;'s blaster     →  Tundra's blaster")
        print('    "greetings      →  say greetings')
        print("    +help/search    →  help with search switch")
    else:
        print("  Some patches failed. Check output above.")
        print("  Backups were created — restore if needed.")
    print("=" * 60)


if __name__ == "__main__":
    main()
