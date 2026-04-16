# -*- coding: utf-8 -*-
"""
Universal Attribute System — Commands.

Provides TinyMUX-style arbitrary attribute storage on any game object.
Attributes are key-value pairs stored in the object_attributes table.

Commands:
  &<attr> <target> = <value>     Set attribute (builder shorthand)
  @set <target>/<attr> = <value> Set attribute (TinyMUX style)
  @wipe <target>                 Clear all attributes on an object
  @examine extended attrs        @examine now shows user-defined attributes

Target resolution:
  "here"          → current room
  "#<id>"         → room by ID
  "<exit_dir>"    → exit by direction
  "<object_name>" → object in room
  "me"            → yourself (player attributes)
"""
import logging

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  Target resolution helper
# ═══════════════════════════════════════════════════════════════════════════════

async def _resolve_target(ctx: CommandContext, target_str: str):
    """
    Resolve a target string to (obj_type, obj_id, display_name).
    Returns (None, None, error_msg) on failure.
    """
    target = target_str.strip().lower()
    char = ctx.session.character
    room_id = char["room_id"]

    if target in ("here", "room"):
        room = await ctx.db.get_room(room_id)
        return "room", room_id, room["name"] if room else f"Room #{room_id}"

    if target == "me":
        return "character", char["id"], char["name"]

    if target.startswith("#"):
        try:
            rid = int(target[1:])
        except ValueError:
            return None, None, f"Invalid ID: {target}"
        room = await ctx.db.get_room(rid)
        if room:
            return "room", rid, room["name"]
        return None, None, f"Room {target} not found."

    # Try exit direction
    exits = await ctx.db.get_exits(room_id)
    for e in exits:
        if e["direction"].lower() == target or e["direction"].lower().startswith(target):
            return "exit", e["id"], f"Exit '{e['direction']}'"

    # Try object in room
    objects = await ctx.db.get_objects_in_room(room_id)
    for obj in objects:
        if obj["name"].lower() == target or obj["name"].lower().startswith(target):
            return "object", obj["id"], obj["name"]

    # Try player in room
    for s in ctx.session_mgr.sessions_in_room(room_id):
        if s.character and s.character["name"].lower().startswith(target):
            return "character", s.character["id"], s.character["name"]

    return None, None, f"Could not find '{target_str}' here."


# ═══════════════════════════════════════════════════════════════════════════════
#  @set with attribute support — extends existing @set
# ═══════════════════════════════════════════════════════════════════════════════

class SetAttrExtCommand(BaseCommand):
    """
    Extended @set that handles target/attr = value syntax for user attributes.
    Uses the universal attribute table.

    @set here/MY_WEATHER = A dust storm howls outside.
    @set me/RP_STATUS = Looking for RP
    @set north/CUSTOM_MSG = The door creaks ominously.
    """
    key = "@setattr"
    aliases = ["&"]
    access_level = AccessLevel.BUILDER
    help_text = (
        "Set a user-defined attribute on a game object.\n"
        "\n"
        "USAGE:\n"
        "  @setattr <target>/<attr> = <value>\n"
        "  &<attr> <target> = <value>          (shorthand)\n"
        "\n"
        "TARGETS: here, me, #<room_id>, <exit_dir>, <object_name>\n"
        "\n"
        "EXAMPLES:\n"
        "  @setattr here/WEATHER = A dust storm howls outside.\n"
        "  &RP_STATUS me = Looking for RP\n"
        "  @setattr here/WEATHER =            (blank value deletes)"
    )
    usage = "@setattr <target>/<attr> = <value>"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()

        # Parse: target/attr = value  OR  attr target = value (& shorthand)
        if "/" in args and "=" in args:
            # @setattr target/attr = value
            slash_idx = args.index("/")
            eq_idx = args.index("=", slash_idx)
            target_str = args[:slash_idx].strip()
            attr_name = args[slash_idx + 1:eq_idx].strip()
            attr_value = args[eq_idx + 1:].strip()
        elif "=" in args:
            # & attr target = value (the & prefix eats first word as attr)
            # By the time we get here, the parser has split:
            #   "&MY_ATTR object = value" → command="&", args="MY_ATTR object = value"
            parts = args.split("=", 1)
            left = parts[0].strip().split()
            attr_value = parts[1].strip()
            if len(left) < 2:
                await ctx.session.send_line("  Usage: &<attr> <target> = <value>")
                return
            attr_name = left[0]
            target_str = " ".join(left[1:])
        else:
            await ctx.session.send_line(
                "  Usage: @setattr <target>/<attr> = <value>\n"
                "         &<attr> <target> = <value>"
            )
            return

        if not attr_name:
            await ctx.session.send_line("  Attribute name cannot be empty.")
            return

        # Resolve target
        obj_type, obj_id, display = await _resolve_target(ctx, target_str)
        if obj_type is None:
            await ctx.session.send_line(f"  {display}")
            return

        attr_name = attr_name.upper()  # TinyMUX convention: uppercase attrs

        if attr_value:
            await ctx.db.set_attribute(
                obj_type, obj_id, attr_name, attr_value,
                owner_id=ctx.session.character.get("id", 0),
            )
            await ctx.session.send_line(
                ansi.success(f"  {display}/{attr_name} set to: {attr_value}")
            )
        else:
            await ctx.db.delete_attribute(obj_type, obj_id, attr_name)
            await ctx.session.send_line(
                ansi.success(f"  {display}/{attr_name} cleared.")
            )


# ═══════════════════════════════════════════════════════════════════════════════
#  @wipe — Clear all user attributes on a target
# ═══════════════════════════════════════════════════════════════════════════════

class WipeCommand(BaseCommand):
    key = "@wipe"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Clear all user-defined attributes on a game object."
    usage = "@wipe <target>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("  Usage: @wipe <target>  (here, me, #id, exit_dir, object)")
            return

        obj_type, obj_id, display = await _resolve_target(ctx, ctx.args)
        if obj_type is None:
            await ctx.session.send_line(f"  {display}")
            return

        count = await ctx.db.wipe_attributes(obj_type, obj_id)
        await ctx.session.send_line(
            ansi.success(f"  Wiped {count} attribute(s) from {display}.")
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  @getattr — Read a single attribute (for non-builders too)
# ═══════════════════════════════════════════════════════════════════════════════

class GetAttrUCommand(BaseCommand):
    key = "@getattr"
    aliases = []
    help_text = "Read a user-defined attribute from a game object."
    usage = "@getattr <target>/<attr>"

    async def execute(self, ctx: CommandContext):
        args = (ctx.args or "").strip()
        if "/" not in args:
            await ctx.session.send_line("  Usage: @getattr <target>/<attr>")
            return

        target_str, attr_name = args.split("/", 1)
        obj_type, obj_id, display = await _resolve_target(ctx, target_str)
        if obj_type is None:
            await ctx.session.send_line(f"  {display}")
            return

        value = await ctx.db.get_attribute(obj_type, obj_id, attr_name.upper())
        if value is not None:
            await ctx.session.send_line(f"  {display}/{attr_name.upper()}: {value}")
        else:
            await ctx.session.send_line(f"  {display}/{attr_name.upper()}: (not set)")


# ═══════════════════════════════════════════════════════════════════════════════
#  @lattr — List all attributes on a target
# ═══════════════════════════════════════════════════════════════════════════════

class LattrCommand(BaseCommand):
    key = "@lattr"
    aliases = ["@listattr"]
    access_level = AccessLevel.BUILDER
    help_text = "List all user-defined attributes on a game object."
    usage = "@lattr <target>"

    async def execute(self, ctx: CommandContext):
        target = (ctx.args or "").strip()
        if not target:
            target = "here"

        obj_type, obj_id, display = await _resolve_target(ctx, target)
        if obj_type is None:
            await ctx.session.send_line(f"  {display}")
            return

        attrs = await ctx.db.list_attributes(obj_type, obj_id)
        if not attrs:
            await ctx.session.send_line(f"  {display}: no user attributes set.")
            return

        await ctx.session.send_line(f"\n  \033[1mAttributes on {display}:\033[0m")
        for a in attrs:
            val_preview = a["value"][:60] + ("..." if len(a["value"]) > 60 else "")
            await ctx.session.send_line(
                f"    \033[1;36m{a['name']:20s}\033[0m {val_preview}"
            )
        await ctx.session.send_line(f"  \033[2m{len(attrs)} attribute(s) total.\033[0m\n")


# ═══════════════════════════════════════════════════════════════════════════════
#  Event hooks — @hook system for builder-defined room behaviors
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Hooks are stored as attributes with special names:
#    AENTER  — fired when a player enters the room
#    ALEAVE  — fired when a player leaves the room  
#    ADESC   — fired when someone looks at the room
#
#  Hook values are simple action strings:
#    @setattr here/AENTER = emit The door creaks shut behind %N.
#    @setattr here/ALEAVE = emit %N slips away into the shadows.
#
#  Actions supported:
#    emit <text>         — emit text to the room
#    pemit <player> <text> — send text to a specific player
#
#  Substitutions:
#    %N — character name
#    %S — subject pronoun (he/she/they)
#    %O — object pronoun (him/her/them)
#    %P — possessive pronoun (his/her/their)

async def fire_room_hook(db, session_mgr, room_id: int, hook_name: str,
                         char: dict = None):
    """Fire a room-level attribute hook if set."""
    try:
        value = await db.get_attribute("room", room_id, hook_name.upper())
        if not value:
            return

        # Apply substitutions
        if char:
            name = char.get("name", "Someone")
            sex = (char.get("sex") or char.get("gender") or "").lower()
            if sex.startswith("m"):
                subj, obj, poss = "he", "him", "his"
            elif sex.startswith("f"):
                subj, obj, poss = "she", "her", "her"
            else:
                subj, obj, poss = "they", "them", "their"

            value = (value
                     .replace("%N", name).replace("%n", name)
                     .replace("%S", subj).replace("%s", subj)
                     .replace("%O", obj).replace("%o", obj)
                     .replace("%P", poss).replace("%p", poss))

        # Parse action
        if value.lower().startswith("emit "):
            text = value[5:]
            await session_mgr.broadcast_to_room(room_id, f"  {text}")
        elif value.lower().startswith("pemit "):
            parts = value[6:].split(None, 1)
            if len(parts) == 2:
                target_name, text = parts
                for s in session_mgr.sessions_in_room(room_id):
                    if s.character and s.character["name"].lower().startswith(
                            target_name.lower()):
                        await s.send_line(f"  {text}")
                        break
        # else: unknown action, silently ignore

    except Exception as e:
        log.warning("fire_room_hook %s failed on room %d: %s",
                    hook_name, room_id, e)


# ═══════════════════════════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════════════════════════

def register_attr_commands(registry):
    """Register attribute system commands."""
    for cmd in [
        SetAttrExtCommand(),
        WipeCommand(),
        GetAttrUCommand(),
        LattrCommand(),
    ]:
        registry.register(cmd)
