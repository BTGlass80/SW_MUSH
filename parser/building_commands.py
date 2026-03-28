"""
Tier 1 building commands for world construction.

Requires Builder or Admin access level.
"""
from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

# Reverse directions for automatic return exits
REVERSE_DIR = {
    "north": "south", "south": "north",
    "east": "west", "west": "east",
    "up": "down", "down": "up",
    "northeast": "southwest", "southwest": "northeast",
    "northwest": "southeast", "southeast": "northwest",
    "in": "out", "out": "in",
}

# Short aliases for directions
DIR_ALIASES = {
    "n": "north", "s": "south", "e": "east", "w": "west",
    "u": "up", "d": "down", "ne": "northeast", "nw": "northwest",
    "se": "southeast", "sw": "southwest",
}


def _resolve_dir(text):
    """Normalize a direction string."""
    text = text.lower().strip()
    return DIR_ALIASES.get(text, text)


class DigCommand(BaseCommand):
    key = "@dig"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create a new room, optionally linked to your current room."
    usage = "@dig <room name> [= <exit_there>[,<exit_back>]]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @dig <room name> [= <exit>[,<return_exit>]]")
            await ctx.session.send_line("  @dig Cantina Back Room")
            await ctx.session.send_line("  @dig Cantina Back Room = north,south")
            return

        # Parse: name = exit_to[,exit_back]
        if "=" in ctx.args:
            room_name, exit_part = ctx.args.split("=", 1)
            room_name = room_name.strip()
            exit_part = exit_part.strip()
        else:
            room_name = ctx.args.strip()
            exit_part = ""

        if not room_name:
            await ctx.session.send_line("  You must specify a room name.")
            return

        # Create the room
        room_id = await ctx.db.create_room(room_name)
        await ctx.session.send_line(
            ansi.success(f"  Room '{room_name}' created as #{room_id}.")
        )

        # Create exits if specified
        if exit_part:
            here = ctx.session.character["room_id"]
            parts = exit_part.split(",")
            exit_to = _resolve_dir(parts[0].strip()) if parts[0].strip() else ""
            exit_back = _resolve_dir(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else ""

            if exit_to:
                eid = await ctx.db.create_exit(here, room_id, exit_to)
                await ctx.session.send_line(
                    f"  Exit '{ansi.exit_color(exit_to)}' created from here to #{room_id}. (exit #{eid})"
                )

            if exit_back:
                eid = await ctx.db.create_exit(room_id, here, exit_back)
                await ctx.session.send_line(
                    f"  Return exit '{ansi.exit_color(exit_back)}' created from #{room_id} to here. (exit #{eid})"
                )


class TunnelCommand(BaseCommand):
    key = "@tunnel"
    aliases = ["@tun"]
    access_level = AccessLevel.BUILDER
    help_text = "Quick-dig a room in a compass direction with auto return exit."
    usage = "@tunnel <direction> [= <room name>]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @tunnel <direction> [= <room name>]")
            await ctx.session.send_line("  @tunnel north = Cantina Storage")
            await ctx.session.send_line("  @tunnel sw = Desert Trail")
            await ctx.session.send_line("  Directions: n/s/e/w/ne/nw/se/sw/u/d")
            return

        if "=" in ctx.args:
            dir_part, name_part = ctx.args.split("=", 1)
            direction = _resolve_dir(dir_part.strip())
            room_name = name_part.strip()
        else:
            direction = _resolve_dir(ctx.args.strip())
            room_name = ""

        if direction not in REVERSE_DIR:
            await ctx.session.send_line(f"  Unknown direction: '{direction}'")
            return

        reverse = REVERSE_DIR[direction]
        here = ctx.session.character["room_id"]

        # Check if exit already exists in that direction
        existing = await ctx.db.find_exit_by_dir(here, direction)
        if existing:
            await ctx.session.send_line(
                f"  An exit '{direction}' already exists here (leads to #{existing['to_room_id']})."
            )
            return

        if not room_name:
            room_name = f"Room {direction.capitalize()} of #{here}"

        # Create room + both exits
        room_id = await ctx.db.create_room(room_name)
        await ctx.db.create_exit(here, room_id, direction)
        await ctx.db.create_exit(room_id, here, reverse)

        await ctx.session.send_line(
            ansi.success(
                f"  Tunneled {ansi.exit_color(direction)} to '{room_name}' (#{room_id}). "
                f"Return exit: {ansi.exit_color(reverse)}."
            )
        )


class OpenCommand(BaseCommand):
    key = "@open"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create an exit from here to a room."
    usage = "@open <direction> = <room #id> [,<return_direction>]"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @open <direction> = <room #id> [,<return_dir>]")
            await ctx.session.send_line("  @open north = #5")
            await ctx.session.send_line("  @open north = #5,south")
            return

        dir_part, dest_part = ctx.args.split("=", 1)
        direction = _resolve_dir(dir_part.strip())
        dest_part = dest_part.strip()

        # Parse destination and optional return direction
        if "," in dest_part:
            dest_str, return_dir = dest_part.split(",", 1)
            dest_str = dest_str.strip()
            return_dir = _resolve_dir(return_dir.strip())
        else:
            dest_str = dest_part.strip()
            return_dir = ""

        # Parse room ID
        dest_id = dest_str.lstrip("#")
        try:
            dest_id = int(dest_id)
        except ValueError:
            await ctx.session.send_line(f"  Invalid room ID: '{dest_str}'. Use a number like #5.")
            return

        dest_room = await ctx.db.get_room(dest_id)
        if not dest_room:
            await ctx.session.send_line(f"  Room #{dest_id} does not exist.")
            return

        here = ctx.session.character["room_id"]

        # Check for duplicate
        existing = await ctx.db.find_exit_by_dir(here, direction)
        if existing:
            await ctx.session.send_line(
                f"  Exit '{direction}' already exists here. Use @unlink first."
            )
            return

        eid = await ctx.db.create_exit(here, dest_id, direction)
        await ctx.session.send_line(
            f"  Exit '{ansi.exit_color(direction)}' opened to '{dest_room['name']}' (#{dest_id}). Exit #{eid}."
        )

        if return_dir:
            eid2 = await ctx.db.create_exit(dest_id, here, return_dir)
            here_room = await ctx.db.get_room(here)
            await ctx.session.send_line(
                f"  Return exit '{ansi.exit_color(return_dir)}' from #{dest_id} to "
                f"'{here_room['name']}'. Exit #{eid2}."
            )


class RoomDescCommand(BaseCommand):
    key = "@rdesc"
    aliases = ["@roomdesc"]
    access_level = AccessLevel.BUILDER
    help_text = "Set the current room's description."
    usage = "@rdesc <description>"

    async def execute(self, ctx: CommandContext):
        room_id = ctx.session.character["room_id"]
        room = await ctx.db.get_room(room_id)

        if not ctx.args:
            await ctx.session.send_line(f"  Room #{room_id}: {room['name']}")
            await ctx.session.send_line(f"  Current desc: {room.get('desc_long', '(none)')}")
            await ctx.session.send_line("  Usage: @rdesc <new description>")
            return

        await ctx.db.update_room(room_id, desc_long=ctx.args, desc_short=ctx.args[:80])
        await ctx.session.send_line(ansi.success(f"  Description set for '{room['name']}'."))


class RoomNameCommand(BaseCommand):
    key = "@rname"
    aliases = ["@roomname"]
    access_level = AccessLevel.BUILDER
    help_text = "Rename the current room."
    usage = "@rname <new name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            room = await ctx.db.get_room(ctx.session.character["room_id"])
            await ctx.session.send_line(f"  Current name: {room['name']}")
            await ctx.session.send_line("  Usage: @rname <new name>")
            return

        room_id = ctx.session.character["room_id"]
        old = await ctx.db.get_room(room_id)
        await ctx.db.update_room(room_id, name=ctx.args.strip())
        await ctx.session.send_line(
            ansi.success(f"  Room renamed: '{old['name']}' -> '{ctx.args.strip()}'")
        )


class DestroyCommand(BaseCommand):
    key = "@destroy"
    aliases = ["@delete"]
    access_level = AccessLevel.BUILDER
    help_text = "Destroy a room or exit. Requires confirmation."
    usage = "@destroy room <#id>  |  @destroy exit <direction>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @destroy room <#id>  |  @destroy exit <direction>")
            await ctx.session.send_line("  @destroy room #15")
            await ctx.session.send_line("  @destroy exit north")
            await ctx.session.send_line("  Add 'confirm' at end to skip prompt: @destroy room #15 confirm")
            return

        parts = ctx.args.split()
        obj_type = parts[0].lower()
        skip_confirm = parts[-1].lower() == "confirm"

        if obj_type == "room":
            await self._destroy_room(ctx, parts, skip_confirm)
        elif obj_type == "exit":
            await self._destroy_exit(ctx, parts, skip_confirm)
        else:
            await ctx.session.send_line(f"  Unknown type: '{obj_type}'. Use 'room' or 'exit'.")

    async def _destroy_room(self, ctx, parts, skip_confirm):
        if len(parts) < 2:
            await ctx.session.send_line("  Usage: @destroy room <#id>")
            return

        room_str = parts[1].lstrip("#")
        try:
            room_id = int(room_str)
        except ValueError:
            await ctx.session.send_line(f"  Invalid room ID: '{parts[1]}'")
            return

        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line(f"  Room #{room_id} not found.")
            return

        # Prevent destroying the room you're standing in
        if room_id == ctx.session.character["room_id"]:
            await ctx.session.send_line("  You can't destroy the room you're in!")
            return

        # Check for characters in the room
        chars = await ctx.db.get_characters_in_room(room_id)
        if chars:
            names = ", ".join(c["name"] for c in chars)
            await ctx.session.send_line(
                f"  Room #{room_id} has characters in it: {names}. "
                f"They must leave first."
            )
            return

        if not skip_confirm:
            await ctx.session.send_line(
                f"  About to destroy '{room['name']}' (#{room_id}) and all its exits."
            )
            await ctx.session.send_line(
                "  Type '@destroy room #" + str(room_id) + " confirm' to proceed."
            )
            return

        ok = await ctx.db.delete_room(room_id)
        if ok:
            await ctx.session.send_line(
                ansi.success(f"  Room '{room['name']}' (#{room_id}) destroyed.")
            )
        else:
            await ctx.session.send_line(f"  Failed to destroy room #{room_id}.")

    async def _destroy_exit(self, ctx, parts, skip_confirm):
        if len(parts) < 2:
            await ctx.session.send_line("  Usage: @destroy exit <direction>")
            return

        direction = _resolve_dir(parts[1])
        here = ctx.session.character["room_id"]
        exit_data = await ctx.db.find_exit_by_dir(here, direction)

        if not exit_data:
            await ctx.session.send_line(f"  No exit '{direction}' found here.")
            return

        if not skip_confirm:
            dest = await ctx.db.get_room(exit_data["to_room_id"])
            dest_name = dest["name"] if dest else "???"
            await ctx.session.send_line(
                f"  About to destroy exit '{direction}' (to '{dest_name}' #{exit_data['to_room_id']})."
            )
            await ctx.session.send_line(
                f"  Type '@destroy exit {direction} confirm' to proceed."
            )
            return

        ok = await ctx.db.delete_exit(exit_data["id"])
        if ok:
            await ctx.session.send_line(
                ansi.success(f"  Exit '{direction}' destroyed.")
            )


class TeleportCommand(BaseCommand):
    key = "@teleport"
    aliases = ["@tel"]
    access_level = AccessLevel.BUILDER
    help_text = "Teleport to a room by ID."
    usage = "@teleport <#room_id>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @teleport <#room_id>")
            return

        room_str = ctx.args.strip().lstrip("#")
        try:
            room_id = int(room_str)
        except ValueError:
            await ctx.session.send_line(f"  Invalid room ID: '{ctx.args}'")
            return

        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line(f"  Room #{room_id} not found.")
            return

        char = ctx.session.character
        old_room = char["room_id"]

        # Announce departure
        await ctx.session_mgr.broadcast_to_room(
            old_room,
            f"  {ansi.player_name(char['name'])} vanishes in a flash of light.",
            exclude=ctx.session,
        )

        # Move
        char["room_id"] = room_id
        await ctx.db.save_character(char["id"], room_id=room_id)

        # Announce arrival
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"  {ansi.player_name(char['name'])} appears in a flash of light.",
            exclude=ctx.session,
        )

        await ctx.session.send_line(ansi.system_msg(f"Teleported to #{room_id}."))

        # Auto-look
        from parser.commands import CommandContext as CC
        look_cmd = ctx.session_mgr  # placeholder, we'll get it from registry
        # Just re-use the look command
        from parser.builtin_commands import LookCommand
        look = LookCommand()
        look_ctx = CC(
            session=ctx.session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr,
        )
        await look.execute(look_ctx)


class LinkCommand(BaseCommand):
    key = "@link"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Redirect an existing exit to a different room."
    usage = "@link <direction> = <#room_id>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @link <direction> = <#room_id>")
            return

        dir_part, dest_part = ctx.args.split("=", 1)
        direction = _resolve_dir(dir_part.strip())
        dest_str = dest_part.strip().lstrip("#")

        try:
            dest_id = int(dest_str)
        except ValueError:
            await ctx.session.send_line(f"  Invalid room ID: '{dest_part.strip()}'")
            return

        dest_room = await ctx.db.get_room(dest_id)
        if not dest_room:
            await ctx.session.send_line(f"  Room #{dest_id} not found.")
            return

        here = ctx.session.character["room_id"]
        exit_data = await ctx.db.find_exit_by_dir(here, direction)
        if not exit_data:
            await ctx.session.send_line(f"  No exit '{direction}' found here. Use @open to create one.")
            return

        await ctx.db.update_exit(exit_data["id"], to_room_id=dest_id)
        await ctx.session.send_line(
            ansi.success(f"  Exit '{direction}' now leads to '{dest_room['name']}' (#{dest_id}).")
        )


class UnlinkCommand(BaseCommand):
    key = "@unlink"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Remove an exit from the current room."
    usage = "@unlink <direction>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @unlink <direction>")
            return

        direction = _resolve_dir(ctx.args.strip())
        here = ctx.session.character["room_id"]

        ok = await ctx.db.delete_exit_by_dir(here, direction)
        if ok:
            await ctx.session.send_line(ansi.success(f"  Exit '{direction}' removed."))
        else:
            await ctx.session.send_line(f"  No exit '{direction}' found here.")


class ExamineCommand(BaseCommand):
    key = "@examine"
    aliases = ["@exam", "@ex"]
    access_level = AccessLevel.BUILDER
    help_text = "Show detailed info about the current room or a room by ID."
    usage = "@examine [#room_id | here]"

    async def execute(self, ctx: CommandContext):
        if ctx.args and ctx.args.strip().lower() != "here":
            room_str = ctx.args.strip().lstrip("#")
            try:
                room_id = int(room_str)
            except ValueError:
                await ctx.session.send_line(f"  Invalid room ID: '{ctx.args}'")
                return
        else:
            room_id = ctx.session.character["room_id"]

        room = await ctx.db.get_room(room_id)
        if not room:
            await ctx.session.send_line(f"  Room #{room_id} not found.")
            return

        await ctx.session.send_line(ansi.header(f"=== Room #{room_id}: {room['name']} ==="))
        await ctx.session.send_line(f"  Zone: {room.get('zone_id', 'None')}")
        await ctx.session.send_line(f"  Properties: {room.get('properties', '{}')}")
        await ctx.session.send_line(f"  Short desc: {room.get('desc_short', '(none)')}")
        await ctx.session.send_line(f"  Long desc: {room.get('desc_long', '(none)')}")

        # Exits from this room
        exits = await ctx.db.get_exits(room_id)
        if exits:
            await ctx.session.send_line("")
            await ctx.session.send_line(f"  {ansi.bold('Exits from here:')}")
            for e in exits:
                dest = await ctx.db.get_room(e["to_room_id"])
                dest_name = dest["name"] if dest else "???"
                await ctx.session.send_line(
                    f"    #{e['id']} {ansi.exit_color(e['direction']):20s} -> "
                    f"'{dest_name}' (#{e['to_room_id']})"
                )

        # Exits to this room
        entrances = await ctx.db.get_entrances(room_id)
        if entrances:
            await ctx.session.send_line("")
            await ctx.session.send_line(f"  {ansi.bold('Entrances to here:')}")
            for e in entrances:
                await ctx.session.send_line(
                    f"    #{e['id']} from '{e['from_room_name']}' (#{e['from_room_id']}) "
                    f"via {ansi.exit_color(e['direction'])}"
                )

        # Characters
        chars = await ctx.db.get_characters_in_room(room_id)
        if chars:
            await ctx.session.send_line("")
            await ctx.session.send_line(f"  {ansi.bold('Characters here:')}")
            for c in chars:
                await ctx.session.send_line(f"    {c['name']} (#{c['id']})")

        await ctx.session.send_line("")


class RoomsCommand(BaseCommand):
    key = "@rooms"
    aliases = ["@roomlist"]
    access_level = AccessLevel.BUILDER
    help_text = "List all rooms or search by name."
    usage = "@rooms [search term]"

    async def execute(self, ctx: CommandContext):
        if ctx.args:
            rooms = await ctx.db.find_rooms(ctx.args.strip())
            label = f"matching '{ctx.args.strip()}'"
        else:
            rooms = await ctx.db.list_rooms(limit=100)
            total = await ctx.db.count_rooms()
            label = f"(showing up to 100 of {total})"

        await ctx.session.send_line(ansi.header(f"=== Rooms {label} ==="))
        if not rooms:
            await ctx.session.send_line("  No rooms found.")
        else:
            for r in rooms:
                zone = f" [zone {r['zone_id']}]" if r.get("zone_id") else ""
                await ctx.session.send_line(
                    f"  #{r['id']:5d}  {r['name']}{zone}"
                )
        await ctx.session.send_line("")


def register_building_commands(registry):
    """Register all Tier 1 building commands."""
    cmds = [
        DigCommand(), TunnelCommand(), OpenCommand(),
        RoomDescCommand(), RoomNameCommand(),
        DestroyCommand(), TeleportCommand(),
        LinkCommand(), UnlinkCommand(),
        ExamineCommand(), RoomsCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)
