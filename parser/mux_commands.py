# -*- coding: utf-8 -*-
"""
MU* Compatibility Layer — Phase 1 commands.

Provides TinyMUX-familiar commands for builders and admins,
plus RP infrastructure (page, +finger, +where).

Commands implemented:
  @name        Rename a room, exit, or object
  @wall        Broadcast to all connected players
  @pemit       Send message to a specific player (anywhere)
  @force       Force a player/NPC to execute a command (admin)
  @newpassword Admin password reset
  @shutdown    Graceful server shutdown
  @decompile   Dump object as recreatable commands
  @clone       Duplicate an object
  page         Cross-game private messaging
  +finger      Player info card
  +where       Who's where (findable players)
"""
import asyncio
import logging
import json
import time

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ── Page system state ─────────────────────────────────────────────────────────
_last_paged: dict[int, list[str]] = {}


# ═══════════════════════════════════════════════════════════════════════════════
#  @name — Rename rooms, exits, objects
# ═══════════════════════════════════════════════════════════════════════════════

class NameCommand(BaseCommand):
    key = "@name"
    aliases = ["@rename"]
    access_level = AccessLevel.BUILDER
    help_text = "Rename a room, exit, or object.\n\nUSAGE:\n  @name here = New Room Name\n  @name <exit_dir> = New Exit Label\n  @name #<room_id> = New Name"
    usage = "@name <target> = <new name>"

    async def execute(self, ctx: CommandContext):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: @name <target> = <new name>")
            return
        target, new_name = ctx.args.split("=", 1)
        target = target.strip().lower()
        new_name = new_name.strip()
        if not new_name:
            await ctx.session.send_line("  You must specify a new name.")
            return
        char = ctx.session.character
        room_id = char["room_id"]

        if target in ("here", "room"):
            await ctx.db.update_room(room_id, name=new_name)
            await ctx.session.send_line(ansi.success(f"  Room renamed to '{new_name}'."))
            return
        if target.startswith("#"):
            try:
                rid = int(target[1:])
            except ValueError:
                await ctx.session.send_line(f"  Invalid room ID: {target}")
                return
            room = await ctx.db.get_room(rid)
            if not room:
                await ctx.session.send_line(f"  Room {target} not found.")
                return
            await ctx.db.update_room(rid, name=new_name)
            await ctx.session.send_line(ansi.success(f"  Room #{rid} renamed to '{new_name}'."))
            return
        # Try exit direction match
        exits = await ctx.db.get_exits(room_id)
        matched = None
        for e in exits:
            if e["direction"].lower() == target or e["direction"].lower().startswith(target):
                matched = e
                break
        if matched:
            await ctx.db.update_exit(matched["id"], name=new_name)
            await ctx.session.send_line(ansi.success(f"  Exit '{matched['direction']}' labeled '{new_name}'."))
            return
        await ctx.session.send_line(f"  Could not find target '{target}'. Use 'here', '#<room_id>', or an exit direction.")


class WallCommand(BaseCommand):
    key = "@wall"
    aliases = ["@broadcast"]
    access_level = AccessLevel.ADMIN
    help_text = "Broadcast a message to all connected players."
    usage = "@wall <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("  Usage: @wall <message>")
            return
        sender = ctx.session.character["name"] if ctx.session.character else "System"
        msg = f"\n  \033[1;33m[BROADCAST from {sender}]\033[0m {ctx.args}\n"
        count = 0
        for s in ctx.session_mgr.all:
            try:
                await s.send_line(msg)
                count += 1
            except Exception as _e:
                log.debug("silent except in parser/mux_commands.py:109: %s", _e, exc_info=True)
        await ctx.session.send_line(f"  Broadcast sent to {count} connection(s).")


class PemitCommand(BaseCommand):
    key = "@pemit"
    aliases = ["@emit/player"]
    access_level = AccessLevel.BUILDER
    help_text = "Send a message directly to a player anywhere on the game."
    usage = "@pemit <player> = <message>"

    async def execute(self, ctx: CommandContext):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: @pemit <player> = <message>")
            return
        target_name, message = ctx.args.split("=", 1)
        target_name = target_name.strip()
        message = message.strip()
        if not target_name or not message:
            await ctx.session.send_line("  Usage: @pemit <player> = <message>")
            return
        target_sess = _find_player_session(ctx.session_mgr, target_name)
        if not target_sess:
            await ctx.session.send_line(f"  Player '{target_name}' not found online.")
            return
        await target_sess.send_line(message)
        await ctx.session.send_line(f"  Message sent to {target_sess.character['name']}.")


class ForceCommand(BaseCommand):
    key = "@force"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Force a player to execute a command as if they typed it. Admin only."
    usage = "@force <player> = <command>"

    async def execute(self, ctx: CommandContext):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: @force <player> = <command>")
            return
        target_name, command = ctx.args.split("=", 1)
        target_name = target_name.strip()
        command = command.strip()
        if not target_name or not command:
            await ctx.session.send_line("  Usage: @force <player> = <command>")
            return
        target_sess = _find_player_session(ctx.session_mgr, target_name)
        if not target_sess:
            await ctx.session.send_line(f"  Player '{target_name}' not found online.")
            return
        admin_name = ctx.session.character["name"] if ctx.session.character else "Admin"
        log.info("@force: %s forcing %s to execute: %s", admin_name, target_sess.character["name"], command)
        target_sess.feed_input(command)
        await ctx.session.send_line(f"  Forced {target_sess.character['name']} to execute: {command}")


class NewPasswordCommand(BaseCommand):
    key = "@newpassword"
    aliases = ["@passwd"]
    access_level = AccessLevel.ADMIN
    help_text = "Reset a player's password. Admin only."
    usage = "@newpassword <player> = <new_password>"

    async def execute(self, ctx: CommandContext):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: @newpassword <player> = <new_password>")
            return
        target_name, new_pass = ctx.args.split("=", 1)
        target_name = target_name.strip()
        new_pass = new_pass.strip()
        if not target_name or not new_pass:
            await ctx.session.send_line("  Usage: @newpassword <player> = <new_password>")
            return
        if len(new_pass) < 4:
            await ctx.session.send_line("  Password must be at least 4 characters.")
            return
        rows = await ctx.db.fetchall(
            "SELECT a.id, a.username FROM accounts a "
            "JOIN characters c ON c.account_id = a.id "
            "WHERE LOWER(c.name) = LOWER(?)", (target_name,))
        if not rows:
            await ctx.session.send_line(f"  No character named '{target_name}' found.")
            return
        row = rows[0]
        import hashlib
        hashed = hashlib.sha256(new_pass.encode()).hexdigest()
        await ctx.db.execute("UPDATE accounts SET password_hash = ? WHERE id = ?", (hashed, row["id"]))
        await ctx.db.commit()
        admin_name = ctx.session.character["name"] if ctx.session.character else "Admin"
        log.info("@newpassword: %s reset password for account %s (%s)", admin_name, row["username"], target_name)
        await ctx.session.send_line(ansi.success(f"  Password reset for {target_name} (account: {row['username']})."))


class ShutdownCommand(BaseCommand):
    key = "@shutdown"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Gracefully shut down the game server. All players are saved and notified."
    usage = "@shutdown [<reason>]"

    async def execute(self, ctx: CommandContext):
        reason = ctx.args.strip() if ctx.args else "Server shutting down."
        admin_name = ctx.session.character["name"] if ctx.session.character else "Admin"
        log.info("@shutdown initiated by %s: %s", admin_name, reason)
        msg = f"\n  \033[1;31m[SERVER SHUTDOWN]\033[0m {reason}\n  \033[2mInitiated by {admin_name}. Disconnecting all players...\033[0m\n"
        for s in ctx.session_mgr.all:
            try:
                await s.send_line(msg)
            except Exception as _e:
                log.debug("silent except in parser/mux_commands.py:218: %s", _e, exc_info=True)
        for s in ctx.session_mgr.all:
            if s.is_in_game and s.character:
                try:
                    await ctx.db.save_character(s.character["id"], room_id=s.character.get("room_id"))
                except Exception:
                    log.warning("@shutdown: failed to save %s", s.character.get("name"))
        await ctx.session.send_line("  All players saved. Shutting down...")
        async def _do_shutdown():
            await asyncio.sleep(2)
            import os, signal
            os.kill(os.getpid(), signal.SIGTERM)
        asyncio.create_task(_do_shutdown())


class DecompileCommand(BaseCommand):
    key = "@decompile"
    aliases = ["@decomp"]
    access_level = AccessLevel.BUILDER
    help_text = "Dump a room as a series of commands that would recreate it."
    usage = "@decompile [here | #<room_id>]"

    async def execute(self, ctx: CommandContext):
        target = (ctx.args or "").strip().lower()
        char = ctx.session.character
        if not target or target == "here":
            room_id = char["room_id"]
        elif target.startswith("#"):
            try:
                room_id = int(target[1:])
            except ValueError:
                await ctx.session.send_line(f"  Invalid ID: {target}")
                return
        else:
            await ctx.session.send_line("  Usage: @decompile [here | #<room_id>]")
            return
        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line(f"  Room #{room_id} not found.")
            return

        lines = [
            f"@@ Decompile of room #{room_id}: {room['name']}",
            f"@@ Generated {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            f"@dig {room['name']}",
            f"@@ Room ID would be #{room_id}",
        ]
        desc = room.get("desc_long") or room.get("desc_short") or ""
        if desc:
            lines.append(f"@describe here = {desc}")
        try:
            props = json.loads(room.get("properties", "{}") or "{}")
            for k, v in sorted(props.items()):
                if k == "room_details":
                    continue
                lines.append(f"@set {k} = {v}")
        except Exception as _e:
            log.debug("silent except in parser/mux_commands.py:276: %s", _e, exc_info=True)
        zone = room.get("zone_id")
        if zone:
            try:
                zone_rows = await ctx.db.fetchall("SELECT name FROM zones WHERE id = ?", (zone,))
                if zone_rows:
                    lines.append(f"@zone here = {zone_rows[0]['name']}")
            except Exception:
                lines.append(f"@@ zone_id = {zone}")
        exits = await ctx.db.get_exits(room_id)
        for e in exits:
            dest_room = await ctx.db.get_room(e["to_room_id"])
            dest_name = dest_room["name"] if dest_room else f"#{e['to_room_id']}"
            label = (e.get("name") or "").strip()
            lock = e.get("lock_data", "")
            lines.append(f"@open {e['direction']} = #{e['to_room_id']}  @@ {dest_name}")
            if label:
                lines.append(f"@name {e['direction']} = {label}")
            if lock and lock not in ("{}", "", "open"):
                lines.append(f"@lock {e['direction']} = {lock}")
            succ = e.get("success_msg", "")
            fail = e.get("fail_msg", "")
            if succ:
                lines.append(f"@success {e['direction']} = {succ}")
            if fail:
                lines.append(f"@fail {e['direction']} = {fail}")
        npcs = await ctx.db.get_npcs_in_room(room_id)
        if npcs:
            lines.append("")
            lines.append(f"@@ NPCs in room ({len(npcs)}):")
            for npc in npcs:
                lines.append(f"@@   {npc['name']} (#{npc['id']})")
        lines.append("")
        lines.append(f"@@ End decompile of #{room_id}")
        await ctx.session.send_line("")
        for line in lines:
            await ctx.session.send_line(f"  {line}")
        await ctx.session.send_line("")


class CloneCommand(BaseCommand):
    key = "@clone"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create a copy of an object in the current room."
    usage = "@clone <object name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("  Usage: @clone <object name>")
            return
        char = ctx.session.character
        room_id = char["room_id"]
        search = ctx.args.strip().lower()
        objects = await ctx.db.get_objects_in_room(room_id)
        target = None
        for obj in objects:
            if obj["name"].lower() == search or obj["name"].lower().startswith(search):
                target = obj
                break
        if not target:
            await ctx.session.send_line(f"  No object '{ctx.args}' found in this room.")
            return
        new_name = f"{target['name']} (copy)"
        cursor = await ctx.db.execute(
            "INSERT INTO objects (type, name, description, room_id, owner_id, data) VALUES (?, ?, ?, ?, ?, ?)",
            (target.get("type", "item"), new_name, target.get("description", ""), room_id, char.get("id"), target.get("data", "{}")))
        await ctx.db.commit()
        await ctx.session.send_line(ansi.success(f"  Cloned '{target['name']}' as '{new_name}' (#{cursor.lastrowid})."))


class PageCommand(BaseCommand):
    key = "page"
    aliases = ["p"]
    help_text = (
        "Send a private message to a player anywhere on the game.\n\n"
        "USAGE:\n  page <player> = <message>\n  page <message>  (re-pages last target)\n\n"
        "EXAMPLES:\n  page Tundra = Meet me at bay 94.\n  page Hey, are you still there?"
    )
    usage = "page <player> = <message>  |  page <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game to page.")
            return
        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line("  Usage: page <player> = <message>\n         page <message>  (re-pages last target)")
            return
        if "=" in args:
            target_part, message = args.split("=", 1)
            target_names = [t.strip() for t in target_part.split() if t.strip()]
            message = message.strip()
        else:
            last = _last_paged.get(char["id"])
            if not last:
                await ctx.session.send_line("  No previous page target. Usage: page <player> = <message>")
                return
            target_names = last
            message = args
        if not message:
            await ctx.session.send_line("  Page what?")
            return
        resolved = []
        not_found = []
        for tname in target_names:
            found = _find_player_session(ctx.session_mgr, tname, exclude_id=char["id"])
            if found:
                resolved.append(found)
            else:
                not_found.append(tname)
        if not_found:
            await ctx.session.send_line(f"  Could not find: {', '.join(not_found)}")
        if not resolved:
            return
        _last_paged[char["id"]] = [s.character["name"] for s in resolved]
        sender_name = char["name"]
        target_list = ", ".join(s.character["name"] for s in resolved)
        if message.startswith(":"):
            pose_text = message[1:].lstrip()
            display_to = f"From afar, {sender_name} {pose_text}"
            display_from = f"Long distance to {target_list}: {sender_name} {pose_text}"
        elif message.startswith(";"):
            semi_text = message[1:]
            display_to = f"From afar, {sender_name}{semi_text}"
            display_from = f"Long distance to {target_list}: {sender_name}{semi_text}"
        else:
            display_to = f"{ansi.player_name(sender_name)} pages: {message}"
            display_from = f"You paged {target_list} with '{message}'"
        for s in resolved:
            await s.send_line(f"  {display_to}")
            idle_secs = time.time() - s.last_activity
            if idle_secs > 300:
                await ctx.session.send_line(f"  \033[2m{s.character['name']} is idle ({int(idle_secs/60)}m).\033[0m")
        await ctx.session.send_line(f"  {display_from}")


class FingerCommand(BaseCommand):
    key = "+finger"
    aliases = ["finger"]
    help_text = (
        "View a player's info card, or set your own info.\n\n"
        "USAGE:\n  +finger <player>\n  +finger/set <field> = <value>\n\n"
        "FIELDS: fullname, position, rp-prefs, quote, alts, theme-song, plan, timezone"
    )
    usage = "+finger [player]  |  +finger/set <field> = <value>"
    valid_switches = ["set"]
    FIELDS = ["fullname", "position", "rp-prefs", "quote", "alts", "theme-song", "plan", "timezone"]

    async def execute(self, ctx: CommandContext):
        if "set" in ctx.switches:
            await self._set_field(ctx)
            return
        char = ctx.session.character
        if not char:
            return
        if ctx.args:
            target_name = ctx.args.strip()
            target_sess = _find_player_session(ctx.session_mgr, target_name)
            target = target_sess.character if target_sess else await ctx.db.get_character_by_name(target_name)
            if not target:
                await ctx.session.send_line(f"  No player named '{target_name}' found.")
                return
        else:
            target = char
        await self._display_finger(ctx, target)

    async def _display_finger(self, ctx, target):
        name = target["name"]
        species = target.get("species", "Human")
        w = min(ctx.session.wrap_width, 78)
        bar = "═" * w
        finger_data = {}
        try:
            attrs = target.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
            finger_data = attrs.get("finger", {})
        except Exception as _e:
            log.debug("silent except in parser/mux_commands.py:456: %s", _e, exc_info=True)
        online_sess = _find_player_session_by_id(ctx.session_mgr, target["id"])
        await ctx.session.send_line("")
        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line(f"  \033[1;37m  {name}\033[0m")
        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line(f"  \033[1mSpecies:\033[0m    {species}")
        for field_key, label in [("fullname", "Full Name"), ("position", "Position")]:
            val = finger_data.get(field_key, "")
            if val:
                pad = max(1, 12 - len(label))
                await ctx.session.send_line(f"  \033[1m{label}:\033[0m{' '*pad}{val}")
        faction = target.get("faction", "")
        if faction:
            await ctx.session.send_line(f"  \033[1mFaction:\033[0m    {faction}")
        desc = target.get("description", "")
        if desc:
            short = desc[:80] + ("..." if len(desc) > 80 else "")
            await ctx.session.send_line(f"  \033[1mDesc:\033[0m       {short}")
        if online_sess:
            idle_str = _format_duration(int(time.time() - online_sess.last_activity))
            on_str = _format_duration(int(time.time() - online_sess.connected_at))
            await ctx.session.send_line(f"  \033[1mStatus:\033[0m     \033[1;32mOnline\033[0m  On for: {on_str}  Idle: {idle_str}")
        else:
            await ctx.session.send_line("  \033[1mStatus:\033[0m     \033[2mOffline\033[0m")
        for field in self.FIELDS:
            if field in ("fullname", "position"):
                continue
            val = finger_data.get(field, "")
            if val:
                label = field.replace("-", " ").title()
                pad = max(1, 12 - len(label))
                await ctx.session.send_line(f"  \033[1m{label}:\033[0m{' '*pad}{val}")

        # RP Preferences (structured display from rpprefs)
        rpprefs = {}
        try:
            rpprefs = attrs.get("rpprefs", {})
        except Exception as _e:
            log.debug("silent except in parser/mux_commands.py:495: %s", _e, exc_info=True)
        if rpprefs:
            await ctx.session.send_line(f"  \033[1;36m{'─' * w}\033[0m")
            await ctx.session.send_line("  \033[1mRP PREFERENCES:\033[0m")
            _val_colors = {
                "yes": "\033[1;32mYES\033[0m",
                "no": "\033[1;31mNO\033[0m",
                "maybe": "\033[1;33mMAYBE\033[0m",
            }
            _row_items = []
            for pk, plabel in _RPPREFS_KEYS:
                pval = rpprefs.get(pk, "")
                if pval and pk != "notes":
                    display = _val_colors.get(pval.lower(), pval)
                    entry = f"    {plabel} {'.' * max(1, 18 - len(plabel))} {display}"
                    _row_items.append(entry)
            # Print in two columns if we have enough items
            for ri in range(0, len(_row_items), 2):
                left = _row_items[ri] if ri < len(_row_items) else ""
                right = _row_items[ri + 1] if ri + 1 < len(_row_items) else ""
                if right:
                    # Pad left to 40 chars visible
                    left_vis = len(ansi.strip_ansi(left))
                    pad_amt = max(1, 42 - left_vis)
                    await ctx.session.send_line(left + " " * pad_amt + right.strip())
                else:
                    await ctx.session.send_line(left)
            notes = rpprefs.get("notes", "")
            if notes:
                await ctx.session.send_line(f"    \033[2mNotes: \"{notes[:80]}\"\033[0m")

        await ctx.session.send_line(f"  \033[1;36m{bar}\033[0m")
        await ctx.session.send_line("")

    async def _set_field(self, ctx):
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line(f"  Usage: +finger/set <field> = <value>\n  Fields: {', '.join(self.FIELDS)}")
            return
        field, value = ctx.args.split("=", 1)
        field = field.strip().lower().replace(" ", "-")
        value = value.strip()
        if field not in self.FIELDS:
            await ctx.session.send_line(f"  Unknown field '{field}'.\n  Valid fields: {', '.join(self.FIELDS)}")
            return
        char = ctx.session.character
        try:
            attrs = char.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
        except Exception:
            attrs = {}
        if "finger" not in attrs:
            attrs["finger"] = {}
        if value:
            attrs["finger"][field] = value
        else:
            attrs["finger"].pop(field, None)
        char["attributes"] = json.dumps(attrs)
        await ctx.db.save_character(char["id"], attributes=char["attributes"])
        if value:
            await ctx.session.send_line(ansi.success(f"  Finger field '{field}' set to: {value}"))
        else:
            await ctx.session.send_line(ansi.success(f"  Finger field '{field}' cleared."))


class WhereCommand(BaseCommand):
    key = "+where"
    aliases = ["where"]
    help_text = "Show connected players and their locations."
    usage = "+where"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        in_game = [s for s in ctx.session_mgr.all if s.is_in_game and s.character]
        if not in_game:
            await ctx.session.send_line("  No players online.")
            return
        by_room: dict[int, list] = {}
        for s in in_game:
            by_room.setdefault(s.character["room_id"], []).append(s)
        await ctx.session.send_line("")
        await ctx.session.send_line(ansi.header("=== Where Is Everyone? ==="))
        await ctx.session.send_line(f"  {'Location':<30s} {'Player':<20s} {'Idle':>6s}")
        await ctx.session.send_line(f"  {'─'*30} {'─'*20} {'─'*6}")
        for rid, sessions in sorted(by_room.items()):
            room = await ctx.db.get_room(rid)
            room_name = room["name"] if room else f"Room #{rid}"
            if len(room_name) > 28:
                room_name = room_name[:27] + "…"
            for i, s in enumerate(sessions):
                idle_str = _format_duration(int(time.time() - s.last_activity))
                loc = room_name if i == 0 else ""
                await ctx.session.send_line(f"  {loc:<30s} {ansi.player_name(s.character['name']):<20s} {idle_str:>6s}")
        await ctx.session.send_line("")
        await ctx.session.send_line(f"  \033[2m{len(in_game)} player(s) online.\033[0m")
        await ctx.session.send_line("")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _find_player_session(session_mgr, name: str, exclude_id: int = None):
    name_lower = name.lower()
    for s in session_mgr.all:
        if (s.is_in_game and s.character and s.character["name"].lower() == name_lower
                and (exclude_id is None or s.character["id"] != exclude_id)):
            return s
    for s in session_mgr.all:
        if (s.is_in_game and s.character and s.character["name"].lower().startswith(name_lower)
                and (exclude_id is None or s.character["id"] != exclude_id)):
            return s
    return None

def _find_player_session_by_id(session_mgr, char_id: int):
    for s in session_mgr.all:
        if s.is_in_game and s.character and s.character["id"] == char_id:
            return s
    return None

def _format_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m"
    elif seconds < 86400:
        return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"
    else:
        return f"{seconds // 86400}d"


# ── RP Preferences ────────────────────────────────────────────────────────────

_RPPREFS_KEYS = [
    ("adventure", "Adventure"),
    ("intrigue", "Intrigue"),
    ("romance", "Romance"),
    ("horror", "Dark Themes"),
    ("comedy", "Comedy"),
    ("permadeath", "Permadeath"),
    ("pvp", "PvP Combat"),
    ("long_scenes", "Long Scenes"),
    ("scheduled", "Scheduled RP"),
    ("notes", "Notes"),
]

_RPPREFS_VALID_VALUES = {"yes", "no", "maybe"}


class RpPrefsCommand(BaseCommand):
    key = "+rpprefs"
    aliases = ["rpprefs"]
    help_text = (
        "Manage your RP preferences (visible on +finger).\n"
        "\n"
        "  +rpprefs                     — view your preferences\n"
        "  +rpprefs/set <pref> = <val>  — set a preference (yes/no/maybe)\n"
        "  +rpprefs/set notes = <text>  — set freeform notes\n"
        "  +rpprefs/clear               — clear all preferences\n"
    )
    usage = "+rpprefs  |  +rpprefs/set <pref> = <value>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        try:
            attrs = char.get("attributes", "{}")
            if isinstance(attrs, str):
                attrs = json.loads(attrs)
        except Exception:
            attrs = {}

        rpprefs = attrs.get("rpprefs", {})
        args = (ctx.args or "").strip()

        # +rpprefs/set
        if args.lower().startswith("set ") or args.lower().startswith("set="):
            rest = args[4:].strip() if args.lower().startswith("set ") else args[3:].strip()
            if "=" not in rest:
                await ctx.session.send_line(
                    "  Usage: +rpprefs/set <pref> = <value>\n"
                    "  Prefs: " + ", ".join(k for k, _ in _RPPREFS_KEYS) + "\n"
                    "  Values: yes, no, maybe (or freeform text for notes)"
                )
                return
            key, val = rest.split("=", 1)
            key = key.strip().lower().replace(" ", "_").replace("-", "_")
            val = val.strip()
            valid_keys = {k for k, _ in _RPPREFS_KEYS}
            if key not in valid_keys:
                await ctx.session.send_line(
                    f"  Unknown preference '{key}'.\n"
                    "  Valid: " + ", ".join(k for k, _ in _RPPREFS_KEYS)
                )
                return
            if key != "notes" and val.lower() not in _RPPREFS_VALID_VALUES:
                await ctx.session.send_line(
                    f"  Value must be yes, no, or maybe (got '{val}')."
                )
                return
            if key == "notes" and len(val) > 120:
                await ctx.session.send_line("  Notes must be 120 characters or fewer.")
                return

            rpprefs[key] = val.lower() if key != "notes" else val
            attrs["rpprefs"] = rpprefs
            char["attributes"] = json.dumps(attrs)
            await ctx.db.save_character(char["id"], attributes=char["attributes"])
            label = dict(_RPPREFS_KEYS).get(key, key)
            await ctx.session.send_line(ansi.success(f"  RP preference '{label}' set to: {val}"))
            return

        # +rpprefs/clear
        if args.lower() == "clear":
            attrs.pop("rpprefs", None)
            char["attributes"] = json.dumps(attrs)
            await ctx.db.save_character(char["id"], attributes=char["attributes"])
            await ctx.session.send_line(ansi.success("  All RP preferences cleared."))
            return

        # Display current prefs
        w = min(ctx.session.wrap_width, 60)
        await ctx.session.send_line(f"\n  \033[1;36m{'═' * w}\033[0m")
        await ctx.session.send_line("  \033[1;37m  RP Preferences\033[0m")
        await ctx.session.send_line(f"  \033[1;36m{'─' * w}\033[0m")
        if not rpprefs:
            await ctx.session.send_line("  \033[2mNo preferences set.\033[0m")
            await ctx.session.send_line(
                "  \033[2mUse +rpprefs/set <pref> = yes/no/maybe\033[0m"
            )
        else:
            _vc = {
                "yes": "\033[1;32mYES\033[0m",
                "no": "\033[1;31mNO\033[0m",
                "maybe": "\033[1;33mMAYBE\033[0m",
            }
            for pk, plabel in _RPPREFS_KEYS:
                pval = rpprefs.get(pk, "")
                if pk == "notes":
                    if pval:
                        await ctx.session.send_line(f"  Notes: \033[2m\"{pval}\"\033[0m")
                elif pval:
                    display = _vc.get(pval.lower(), pval)
                    dots = "." * max(1, 20 - len(plabel))
                    await ctx.session.send_line(f"    {plabel} {dots} {display}")
        await ctx.session.send_line(f"  \033[1;36m{'═' * w}\033[0m\n")


# ── Registration ──────────────────────────────────────────────────────────────

def register_mux_commands(registry):
    """Register all MU* compatibility commands."""
    for cmd in [NameCommand(), WallCommand(), PemitCommand(), ForceCommand(),
                NewPasswordCommand(), ShutdownCommand(), DecompileCommand(),
                CloneCommand(), PageCommand(), FingerCommand(), WhereCommand(),
                RpPrefsCommand()]:
        registry.register(cmd)
