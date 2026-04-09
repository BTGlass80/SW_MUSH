#!/usr/bin/env python3
"""
Patch: Structured HUD protocol for WebSocket clients.

Changes:
  1. parser/commands.py — after every command dispatch, send a
     hud_update JSON message to WebSocket sessions with current
     character state (name, wound, credits, room, exits).
  2. server/session.py — add send_hud_update() helper method.

The web client will listen for {"type": "hud_update", ...} messages
and update the sidebar directly — no more regex parsing.
"""
import os
import sys
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SESSION_PATH = os.path.join(ROOT, "server", "session.py")
COMMANDS_PATH = os.path.join(ROOT, "parser", "commands.py")

DRY_RUN = "--dry-run" in sys.argv


def read(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write(path, content):
    if DRY_RUN:
        print(f"  [DRY RUN] Would write {len(content)} chars to {path}")
        return
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def backup(path):
    bak = path + ".pre_hud_bak"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"  Backup: {bak}")


def patch_session():
    """Add send_hud_update() method to Session."""
    src = read(SESSION_PATH)
    backup(SESSION_PATH)

    if "send_hud_update" in src:
        print("  [SKIP] send_hud_update already exists")
        return

    # Insert the method after send_json
    anchor = '''    async def send_json(self, msg_type: str, data: dict):
        """Send a typed JSON message (primarily for WebSocket clients)."""
        if self.protocol == Protocol.WEBSOCKET:
            try:
                await self._send(json.dumps({"type": msg_type, **data}))
            except Exception as e:
                log.warning("JSON send failed on %s: %s", self, e)
        else:
            # Telnet fallback: render as text
            if msg_type == "room_description":
                await self.send_line(data.get("text", ""))
            elif msg_type == "combat_log":
                await self.send_line(data.get("text", ""))
            else:
                await self.send_line(str(data))'''

    new_block = anchor + '''

    async def send_hud_update(self, db=None):
        """
        Send structured HUD data to WebSocket clients.

        Reads current character state from self.character dict and
        optionally fetches exits from DB. Telnet clients ignore this.
        """
        if self.protocol != Protocol.WEBSOCKET:
            return
        if not self.character:
            return

        char = self.character
        room_id = char.get("room_id")

        # Build HUD payload
        hud = {
            "name": char.get("name", ""),
            "wound_level": char.get("wound_level", 0),
            "wound_name": _wound_name(char.get("wound_level", 0)),
            "credits": char.get("credits", 0),
            "room_name": char.get("_room_name", ""),
            "room_id": room_id,
            "force_points": char.get("force_points", 0),
            "character_points": char.get("character_points", 0),
            "dark_side_points": char.get("dark_side_points", 0),
            "force_sensitive": bool(char.get("force_sensitive", False)),
            "exits": [],
        }

        # Fetch exits if we have a DB handle
        if db and room_id:
            try:
                exits = await db.get_exits(room_id)
                hud["exits"] = [e["direction"] for e in exits]
                # Also grab room name from DB if not cached
                if not hud["room_name"]:
                    room = await db.get_room(room_id)
                    if room:
                        hud["room_name"] = room.get("name", "")
            except Exception:
                pass  # Non-critical — HUD just won't show exits

        try:
            await self._send(json.dumps({"type": "hud_update", **hud}))
        except Exception as e:
            log.warning("HUD update failed on %s: %s", self, e)'''

    if anchor in src:
        src = src.replace(anchor, new_block, 1)
        print("  [1] Added send_hud_update() method to Session")
    else:
        print("  [1] FAIL — anchor not found in session.py")
        return

    # Add the helper function for wound names (before the class definition)
    wound_helper = '''

def _wound_name(level: int) -> str:
    """Convert wound_level int to display name."""
    names = {
        0: "Healthy",
        1: "Stunned",
        2: "Wounded",
        3: "Wounded Twice",
        4: "Incapacitated",
        5: "Mortally Wounded",
        6: "Dead",
    }
    return names.get(level, "Healthy")

'''

    # Insert before the Session class
    class_anchor = "\nclass Session:"
    if "_wound_name" not in src:
        src = src.replace(class_anchor, wound_helper + "class Session:", 1)
        print("  [2] Added _wound_name() helper")

    write(SESSION_PATH, src)
    print("  ✓ session.py patched")


def patch_commands():
    """Add HUD update after every command dispatch."""
    src = read(COMMANDS_PATH)
    backup(COMMANDS_PATH)

    if "send_hud_update" in src:
        print("  [SKIP] HUD hook already in commands.py")
        return

    # Hook after command execution, right before send_prompt
    old_tail = '''        except Exception as e:
            log.exception("Command error (%s): %s", ctx.command, e)
            await ctx.session.send_line(
                f"An error occurred processing your command. ({e})"
            )
        await ctx.session.send_prompt()'''

    new_tail = '''        except Exception as e:
            log.exception("Command error (%s): %s", ctx.command, e)
            await ctx.session.send_line(
                f"An error occurred processing your command. ({e})"
            )

        # ── HUD update for WebSocket clients ──
        # Send structured state after every command so the browser
        # sidebar stays current without regex-parsing output text.
        if ctx.session.is_in_game:
            # Refresh character data from DB to catch any mutations
            if ctx.session.character:
                try:
                    fresh = await ctx.db.get_character(
                        ctx.session.character["id"]
                    )
                    if fresh:
                        # Preserve room_name cache
                        rn = ctx.session.character.get("_room_name", "")
                        ctx.session.character.update(fresh)
                        if rn:
                            ctx.session.character["_room_name"] = rn
                except Exception:
                    pass  # Non-critical
            await ctx.session.send_hud_update(db=ctx.db)

        await ctx.session.send_prompt()'''

    if old_tail in src:
        src = src.replace(old_tail, new_tail, 1)
        print("  [1] Added post-command HUD update hook")
    else:
        print("  [1] FAIL — anchor not found in commands.py")
        return

    write(COMMANDS_PATH, src)
    print("  ✓ commands.py patched")


def patch_look_room_cache():
    """Cache room name in session.character when look fires."""
    builtin_path = os.path.join(ROOT, "parser", "builtin_commands.py")
    src = read(builtin_path)
    backup(builtin_path)

    if "_room_name" in src:
        print("  [SKIP] Room name caching already in builtin_commands.py")
        return

    # After the room name is displayed in look, cache it on session.character
    # Find the line that sends room name and add caching after
    anchor = '''        await session.send_line(
            ansi.room_name(room["name"])
        )'''

    replacement = '''        await session.send_line(
            ansi.room_name(room["name"])
        )

        # Cache room name for HUD updates
        if session.character:
            session.character["_room_name"] = room["name"]'''

    if anchor in src:
        src = src.replace(anchor, replacement, 1)
        write(builtin_path, src)
        print("  [1] Added room name caching to look command")
        print("  ✓ builtin_commands.py patched")
    else:
        print("  [1] SKIP — look anchor not found (may have different formatting)")


def validate():
    """AST-parse all patched files."""
    import ast
    ok = True
    for path in [SESSION_PATH, COMMANDS_PATH,
                 os.path.join(ROOT, "parser", "builtin_commands.py")]:
        try:
            ast.parse(read(path))
            print(f"  AST OK: {os.path.basename(path)}")
        except SyntaxError as e:
            print(f"  AST FAIL: {os.path.basename(path)} — {e}")
            ok = False
    return ok


if __name__ == "__main__":
    print("=" * 60)
    print("Patch: Structured HUD Protocol")
    print("=" * 60)
    print()

    print("[session.py]")
    patch_session()
    print()

    print("[commands.py]")
    patch_commands()
    print()

    print("[builtin_commands.py]")
    patch_look_room_cache()
    print()

    print("[Validation]")
    if validate():
        print()
        print("All patches applied and validated successfully.")
    else:
        print()
        print("VALIDATION FAILED — check output above.")
        sys.exit(1)
