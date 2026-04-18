# -*- coding: utf-8 -*-
"""
Places System — Virtual sub-locations within rooms.

Ported from the TinyMUX/SGP Places system. Allows builders to create
tables, booths, seats, alcoves etc. inside a room. Players can join/
depart from places, and use table-talk (tt) for semi-private speech.

Commands:
  places               List places in the current room
  join <#|name>        Sit at a place
  depart / stand       Leave your current place
  tt <message>         Table-talk: speak only to your place
  ttooc <message>      OOC table-talk

Builder commands:
  @places <count>      Configure N places in this room
  @places/clear        Remove all places from this room
  @place <#>/<field> = <value>   Set place properties
    Fields: name, max, desc, prefix

Also adds exit messages:
  @osucc <dir> = <msg>   Others-success message (seen by departure room)
  @ofail <dir> = <msg>   Others-fail message (seen by room on lock failure)
  @odrop <dir> = <msg>   Others-arrive message (seen by destination room)
"""
import json
import logging
import random

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
#  Places Engine — data stored in room properties JSON
# ═══════════════════════════════════════════════════════════════════════════════
#
#  Room properties["places"] = {
#      "max": 4,                    # number of configured places
#      "spots": {
#          "1": {
#              "name": "Corner Booth",
#              "max": 4,
#              "desc": "A dimly lit booth in the corner.",
#              "prefix": "At the booth",
#              "occupants": [12, 45]    # character IDs
#          },
#          "2": { ... }
#      }
#  }

async def _get_places(db, room_id: int) -> dict:
    """Load places data for a room. Returns empty dict if no places."""
    props = await db.get_all_room_properties(room_id)
    return props.get("places", {})


async def _save_places(db, room_id: int, places_data: dict):
    """Save places data back to room properties JSON."""
    room = await db.get_room(room_id)
    if not room:
        return
    try:
        props = json.loads(room.get("properties", "{}") or "{}")
    except Exception:
        props = {}
    props["places"] = places_data
    await db.update_room(room_id, properties=json.dumps(props))


def _which_place(places_data: dict, char_id: int) -> str:
    """Return the place number (as string) a character is at, or '' if none."""
    spots = places_data.get("spots", {})
    for num, spot in spots.items():
        if char_id in spot.get("occupants", []):
            return num
    return ""


def _get_spot(places_data: dict, num: str) -> dict:
    """Get a specific place spot by number string."""
    return places_data.get("spots", {}).get(num, {})


async def _clean_disconnected(db, room_id: int, places_data: dict, session_mgr) -> bool:
    """Remove disconnected players from places. Returns True if modified."""
    modified = False
    connected_ids = set()
    for s in session_mgr.sessions_in_room(room_id):
        if s.character:
            connected_ids.add(s.character["id"])
    
    for num, spot in places_data.get("spots", {}).items():
        occs = spot.get("occupants", [])
        new_occs = [cid for cid in occs if cid in connected_ids]
        if len(new_occs) != len(occs):
            spot["occupants"] = new_occs
            modified = True
    return modified


# ═══════════════════════════════════════════════════════════════════════════════
#  places — List places in the room
# ═══════════════════════════════════════════════════════════════════════════════

class PlacesCommand(BaseCommand):
    key = "places"
    aliases = ["place"]
    help_text = (
        "List all places (tables, booths, seats) in the current room.\n"
        "Use 'join <#>' to sit at one."
    )
    usage = "places"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        if not places or not places.get("spots"):
            await ctx.session.send_line("  There are no special places here.")
            return

        # Clean disconnected players
        if await _clean_disconnected(ctx.db, room_id, places, ctx.session_mgr):
            await _save_places(ctx.db, room_id, places)

        await ctx.session.send_line("")
        await ctx.session.send_line(ansi.header("=== Places ==="))
        
        spots = places.get("spots", {})
        for num in sorted(spots.keys(), key=int):
            spot = spots[num]
            name = spot.get("name", f"Place #{num}")
            max_occ = spot.get("max", 4)
            occs = spot.get("occupants", [])
            empty = max_occ - len(occs)
            desc = spot.get("desc", "")

            empty_str = f"{empty} empty place{'s' if empty != 1 else ''}"
            await ctx.session.send_line(
                f"  \033[1m#{num}\033[0m {name} — {empty_str}"
            )
            if desc:
                await ctx.session.send_line(f"      \033[2m{desc}\033[0m")
            if occs:
                # Resolve names
                names = []
                for cid in occs:
                    for s in ctx.session_mgr.sessions_in_room(room_id):
                        if s.character and s.character["id"] == cid:
                            names.append(ansi.player_name(s.character["name"]))
                            break
                    else:
                        names.append(f"#{cid}")
                await ctx.session.send_line(
                    f"      Present: {', '.join(names)}"
                )
        
        my_place = _which_place(places, char["id"])
        if my_place:
            spot = _get_spot(places, my_place)
            await ctx.session.send_line(
                f"\n  You are at: \033[1m{spot.get('name', f'Place #{my_place}')}\033[0m"
            )
        await ctx.session.send_line("")


# ═══════════════════════════════════════════════════════════════════════════════
#  join — Sit at a place
# ═══════════════════════════════════════════════════════════════════════════════

class JoinPlaceCommand(BaseCommand):
    key = "join"
    aliases = ["sit"]
    help_text = "Join a place (table, booth, etc.) in the current room."
    usage = "join <#>  |  join <name>  |  join with <player>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        if not places or not places.get("spots"):
            await ctx.session.send_line("  There are no special places here.")
            return

        if not ctx.args:
            await ctx.session.send_line("  Usage: join <#>  |  join <name>  |  join with <player>")
            return

        # Check if already seated
        current = _which_place(places, char["id"])
        if current:
            spot = _get_spot(places, current)
            await ctx.session.send_line(
                f"  You're already at {spot.get('name', f'Place #{current}')}. "
                f"Type 'depart' first."
            )
            return

        arg = ctx.args.strip()
        spots = places.get("spots", {})
        target_num = None

        # Try direct number
        if arg.lstrip("#").isdigit():
            num = arg.lstrip("#")
            if num in spots:
                target_num = num

        # Try name match
        if not target_num:
            arg_lower = arg.lower()
            for num, spot in spots.items():
                if spot.get("name", "").lower().startswith(arg_lower):
                    target_num = num
                    break

        # Try "with <player>" — find which place they're at
        if not target_num and arg.lower().startswith("with "):
            player_name = arg[5:].strip()
            for s in ctx.session_mgr.sessions_in_room(room_id):
                if s.character and s.character["name"].lower().startswith(player_name.lower()):
                    p = _which_place(places, s.character["id"])
                    if p:
                        target_num = p
                    break

        if not target_num:
            await ctx.session.send_line(f"  No place matching '{arg}'. Type 'places' to see options.")
            return

        spot = spots[target_num]
        max_occ = spot.get("max", 4)
        occs = spot.get("occupants", [])
        if len(occs) >= max_occ:
            await ctx.session.send_line(f"  {spot.get('name', f'Place #{target_num}')} is full.")
            return

        # Join
        occs.append(char["id"])
        spot["occupants"] = occs
        await _save_places(ctx.db, room_id, places)

        name = spot.get("name", f"Place #{target_num}")
        await ctx.session.send_line(f"  You sit down at {name}.")

        # Notify others at the place
        for cid in occs:
            if cid == char["id"]:
                continue
            for s in ctx.session_mgr.sessions_in_room(room_id):
                if s.character and s.character["id"] == cid:
                    await s.send_line(f"  {ansi.player_name(char['name'])} joins you at {name}.")
                    break

        # Notify room
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"  {ansi.player_name(char['name'])} sits down at {name}.",
            exclude=ctx.session,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  depart / stand — Leave a place
# ═══════════════════════════════════════════════════════════════════════════════

class DepartPlaceCommand(BaseCommand):
    key = "depart"
    aliases = ["stand"]
    help_text = "Leave your current place (table, booth, etc.)."
    usage = "depart"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        current = _which_place(places, char["id"])
        if not current:
            await ctx.session.send_line("  You aren't placed anywhere.")
            return

        spot = _get_spot(places, current)
        name = spot.get("name", f"Place #{current}")
        
        # Remove from occupants
        spot["occupants"] = [c for c in spot.get("occupants", []) if c != char["id"]]
        await _save_places(ctx.db, room_id, places)

        await ctx.session.send_line(f"  You stand and leave {name}.")

        # Notify remaining occupants
        for cid in spot.get("occupants", []):
            for s in ctx.session_mgr.sessions_in_room(room_id):
                if s.character and s.character["id"] == cid:
                    await s.send_line(f"  {ansi.player_name(char['name'])} has departed {name}.")
                    break

        # Notify room
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            f"  {ansi.player_name(char['name'])} stands and leaves {name}.",
            exclude=ctx.session,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  tt — Table-talk (speak to your place only)
# ═══════════════════════════════════════════════════════════════════════════════

class TableTalkCommand(BaseCommand):
    key = "tt"
    aliases = ["tabletalk"]
    help_text = (
        "Speak only to the people at your current place (table, booth).\n"
        "Others in the room see a muffled/partial version.\n"
        "\n"
        "Supports poses:  tt :leans forward  →  At the booth, Han leans forward"
    )
    usage = "tt <message>  |  tt :<pose>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        if not ctx.args:
            await ctx.session.send_line("  tt what?")
            return

        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        current = _which_place(places, char["id"])
        if not current:
            await ctx.session.send_line("  You need to join a place first. Type 'places' to see options.")
            return

        spot = _get_spot(places, current)
        prefix = spot.get("prefix", spot.get("name", f"Place #{current}"))
        name = char["name"]
        msg = ctx.args

        # Format the message
        if msg.startswith(":"):
            pose_text = msg[1:].lstrip()
            full_msg = f"  \033[1;36m[{prefix}]\033[0m {ansi.player_name(name)} {pose_text}"
        elif msg.startswith(";"):
            semi_text = msg[1:]
            full_msg = f"  \033[1;36m[{prefix}]\033[0m {ansi.player_name(name)}{semi_text}"
        else:
            full_msg = f"  \033[1;36m[{prefix}]\033[0m {ansi.player_name(name)} says, \"{msg}\""

        # Send full message to place occupants
        for cid in spot.get("occupants", []):
            for s in ctx.session_mgr.sessions_in_room(room_id):
                if s.character and s.character["id"] == cid:
                    await s.send_line(full_msg)
                    break

        # Send muffled version to rest of room
        muffled = _muffle_text(msg)
        if msg.startswith(":") or msg.startswith(";"):
            muffled_msg = f"  \033[2m{name} mutters something at {prefix}.\033[0m"
        else:
            muffled_msg = f"  \033[2m{name} says something at {prefix}: \"{muffled}\"\033[0m"
        
        occ_ids = set(spot.get("occupants", []))
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["id"] not in occ_ids:
                await s.send_line(muffled_msg)


class TableTalkOocCommand(BaseCommand):
    key = "ttooc"
    aliases = []
    help_text = "OOC table-talk. Same as tt but marked as OOC."
    usage = "ttooc <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        if not ctx.args:
            await ctx.session.send_line("  ttooc what?")
            return

        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        current = _which_place(places, char["id"])
        if not current:
            await ctx.session.send_line("  You need to join a place first.")
            return

        spot = _get_spot(places, current)
        prefix = spot.get("prefix", spot.get("name", f"Place #{current}"))
        name = char["name"]

        full_msg = f"  \033[1;36m[{prefix}]\033[0m \033[2m<OOC> {name}: {ctx.args}\033[0m"

        for cid in spot.get("occupants", []):
            for s in ctx.session_mgr.sessions_in_room(room_id):
                if s.character and s.character["id"] == cid:
                    await s.send_line(full_msg)
                    break


# ═══════════════════════════════════════════════════════════════════════════════
#  @places — Configure places (builder)
# ═══════════════════════════════════════════════════════════════════════════════

class ConfigPlacesCommand(BaseCommand):
    key = "@places"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = (
        "Configure places (tables, booths, seats) in the current room.\n"
        "\n"
        "USAGE:\n"
        "  @places <count>              — set up N places\n"
        "  @places/clear                — remove all places\n"
        "\n"
        "Then customize each with:\n"
        "  @place <#>/name = Corner Booth\n"
        "  @place <#>/max = 6\n"
        "  @place <#>/desc = A dimly lit booth.\n"
        "  @place <#>/prefix = At the booth"
    )
    usage = "@places <count>  |  @places/clear"
    valid_switches = ["clear"]

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        room_id = char["room_id"]

        if "clear" in ctx.switches:
            await _save_places(ctx.db, room_id, {})
            await ctx.session.send_line(ansi.success("  All places removed from this room."))
            return

        if not ctx.args or not ctx.args.strip().isdigit():
            await ctx.session.send_line("  Usage: @places <count>  |  @places/clear")
            return

        count = int(ctx.args.strip())
        if count < 1 or count > 20:
            await ctx.session.send_line("  Place count must be between 1 and 20.")
            return

        spots = {}
        for i in range(1, count + 1):
            spots[str(i)] = {
                "name": f"Table {i}",
                "max": 4,
                "desc": "",
                "prefix": f"At Table {i}",
                "occupants": [],
            }

        places_data = {"max": count, "spots": spots}
        await _save_places(ctx.db, room_id, places_data)
        await ctx.session.send_line(
            ansi.success(f"  {count} places configured. Use '@place <#>/name = ...' to customize.")
        )


class SetPlaceCommand(BaseCommand):
    key = "@place"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Set properties on a specific place.\n\nFields: name, max, desc, prefix"
    usage = "@place <#>/<field> = <value>"

    async def execute(self, ctx: CommandContext):
        if "/" not in (ctx.args or "") or "=" not in (ctx.args or ""):
            await ctx.session.send_line(
                "  Usage: @place <#>/<field> = <value>\n"
                "  Fields: name, max, desc, prefix\n"
                "  Example: @place 1/name = Corner Booth"
            )
            return

        target, value = ctx.args.split("=", 1)
        value = value.strip()
        num_part, field = target.split("/", 1)
        num = num_part.strip().lstrip("#")
        field = field.strip().lower()

        if field not in ("name", "max", "desc", "prefix"):
            await ctx.session.send_line(f"  Unknown field '{field}'. Valid: name, max, desc, prefix")
            return

        char = ctx.session.character
        room_id = char["room_id"]
        places = await _get_places(ctx.db, room_id)
        spots = places.get("spots", {})

        if num not in spots:
            await ctx.session.send_line(f"  Place #{num} does not exist. Use '@places <count>' first.")
            return

        if field == "max":
            try:
                value = int(value)
            except ValueError:
                await ctx.session.send_line("  Max must be a number.")
                return

        spots[num][field] = value
        await _save_places(ctx.db, room_id, places)
        await ctx.session.send_line(
            ansi.success(f"  Place #{num} {field} set to: {value}")
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Exit messages: @osucc, @ofail, @odrop
# ═══════════════════════════════════════════════════════════════════════════════

class OsuccCommand(BaseCommand):
    key = "@osucc"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = (
        "Set the others-success message on an exit.\n"
        "Shown to the room the player is LEAVING when they traverse the exit.\n"
        "Use %N for the player's name.\n\n"
        "Example: @osucc north = %N pushes through the cantina doors."
    )
    usage = "@osucc <direction> = <message>"

    async def execute(self, ctx: CommandContext):
        await _set_exit_msg(ctx, "osucc_msg")


class OfailCommand(BaseCommand):
    key = "@ofail"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = (
        "Set the others-fail message on an exit.\n"
        "Shown to the room when someone fails to pass through a locked exit.\n"
        "Use %N for the player's name.\n\n"
        "Example: @ofail east = %N tugs at the blast door but it won't budge."
    )
    usage = "@ofail <direction> = <message>"

    async def execute(self, ctx: CommandContext):
        await _set_exit_msg(ctx, "ofail_msg")


class OdropCommand(BaseCommand):
    key = "@odrop"
    aliases = ["@oarrive"]
    access_level = AccessLevel.BUILDER
    help_text = (
        "Set the others-arrive message on an exit.\n"
        "Shown to the DESTINATION room when someone arrives.\n"
        "Use %N for the player's name.\n\n"
        "Example: @odrop north = %N enters from the south, dust on their boots."
    )
    usage = "@odrop <direction> = <message>"

    async def execute(self, ctx: CommandContext):
        await _set_exit_msg(ctx, "odrop_msg")


async def _set_exit_msg(ctx: CommandContext, msg_key: str):
    """Set a custom message field on an exit's lock_data JSON."""
    if "=" not in (ctx.args or ""):
        cmd = msg_key.replace("_msg", "").upper()
        await ctx.session.send_line(f"  Usage: @{cmd.lower()} <direction> = <message>")
        return

    direction, message = ctx.args.split("=", 1)
    direction = direction.strip().lower()
    message = message.strip()

    room_id = ctx.session.character["room_id"]
    exit_data = await ctx.db.find_exit_by_dir(room_id, direction)
    if not exit_data:
        await ctx.session.send_line(f"  No exit '{direction}' found here.")
        return

    try:
        lock = json.loads(exit_data.get("lock_data", "{}") or "{}")
    except Exception:
        lock = {}

    if message:
        lock[msg_key] = message
    else:
        lock.pop(msg_key, None)

    await ctx.db.update_exit(exit_data["id"], lock_data=json.dumps(lock))
    label = msg_key.replace("_msg", "").upper()
    if message:
        await ctx.session.send_line(ansi.success(f"  {label} on '{direction}' set to: {message}"))
    else:
        await ctx.session.send_line(ansi.success(f"  {label} on '{direction}' cleared."))


# ═══════════════════════════════════════════════════════════════════════════════
#  Mutter — partial overheard speech
# ═══════════════════════════════════════════════════════════════════════════════

class MutterCommand(BaseCommand):
    key = "mutter"
    aliases = ["mu"]
    help_text = (
        "Mutter to someone — they hear the full message, but others in\n"
        "the room only hear fragments. Put key words in \"quotes\" to\n"
        "control what leaks through.\n\n"
        "EXAMPLES:\n"
        "  mutter Han = Meet me at \"bay 94\" at midnight.\n"
        "  Others see: Tundra mutters to Han, \"... bay 94 ...\""
    )
    usage = "mutter <player> = <message>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        if "=" not in (ctx.args or ""):
            await ctx.session.send_line("  Usage: mutter <player> = <message>")
            return

        target_name, message = ctx.args.split("=", 1)
        target_name = target_name.strip()
        message = message.strip()
        if not target_name or not message:
            await ctx.session.send_line("  Usage: mutter <player> = <message>")
            return

        room_id = char["room_id"]
        target_sess = None
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s.character and s.character["name"].lower().startswith(target_name.lower()):
                target_sess = s
                break

        if not target_sess:
            await ctx.session.send_line(f"  You don't see '{target_name}' here.")
            return

        tname = target_sess.character["name"]
        cname = char["name"]

        # Full message to target
        await target_sess.send_line(
            f"  {ansi.player_name(cname)} mutters to you, \"{message}\""
        )
        # Full message to sender
        await ctx.session.send_line(
            f"  You mutter to {ansi.player_name(tname)}, \"{message}\""
        )

        # Muffled version to rest of room
        muffled = _muffle_text(message)
        muffled_msg = (
            f"  \033[2m{cname} mutters to {tname}, \"{muffled}\"\033[0m"
        )
        for s in ctx.session_mgr.sessions_in_room(room_id):
            if s is ctx.session or s is target_sess:
                continue
            await s.send_line(muffled_msg)


# ═══════════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _muffle_text(text: str) -> str:
    """
    Replace parts of a message with '...' to simulate overheard speech.
    Words inside "double quotes" are preserved (the quoted parts leak through).
    Other words have a 30% chance of being heard.
    """
    import re
    
    # Extract quoted segments
    parts = re.split(r'(".*?")', text)
    result = []
    for part in parts:
        if part.startswith('"') and part.endswith('"'):
            # Quoted text leaks through
            result.append(part[1:-1])  # strip quotes
        else:
            # Non-quoted: randomly replace words with ...
            words = part.split()
            muffled_words = []
            for w in words:
                if random.random() < 0.3:
                    muffled_words.append(w)
                else:
                    muffled_words.append("...")
            result.append(" ".join(muffled_words))
    
    return " ".join(result).strip()


# ═══════════════════════════════════════════════════════════════════════════════
#  Auto-depart on room change (hook for MoveCommand)
# ═══════════════════════════════════════════════════════════════════════════════

async def auto_depart_place(db, char_id: int, room_id: int, session_mgr):
    """Remove a character from any place when they leave the room.
    Called from MoveCommand before the actual move."""
    places = await _get_places(db, room_id)
    if not places:
        return
    current = _which_place(places, char_id)
    if not current:
        return
    spot = _get_spot(places, current)
    spot["occupants"] = [c for c in spot.get("occupants", []) if c != char_id]
    await _save_places(db, room_id, places)


# ═══════════════════════════════════════════════════════════════════════════════
#  Registration
# ═══════════════════════════════════════════════════════════════════════════════

def register_places_commands(registry):
    """Register all places/mutter/exit-message commands.

    S58 — +place umbrella registered first; per-verb classes remain
    registered at their bare keys for backward compatibility. `tt`,
    `ttooc`, and `mutter` stay bare (natural RP shortcuts, per the
    S54 rename policy).
    """
    # Umbrella first so its alias list claims bare-word routing
    registry.register(PlaceUmbrellaCommand())
    for cmd in [
        PlacesCommand(), JoinPlaceCommand(), DepartPlaceCommand(),
        TableTalkCommand(), TableTalkOocCommand(),
        ConfigPlacesCommand(), SetPlaceCommand(),
        OsuccCommand(), OfailCommand(), OdropCommand(),
        MutterCommand(),
    ]:
        registry.register(cmd)


# ═══════════════════════════════════════════════════════════════════════════
# +place — Umbrella for places verbs (S58)
# ═══════════════════════════════════════════════════════════════════════════

_PLACE_SWITCH_IMPL: dict = {}

_PLACE_ALIAS_TO_SWITCH: dict[str, str] = {
    # View default
    "places": "view", "place": "view",
    # Seating
    "join": "join", "sit": "join",
    "depart": "depart", "stand": "depart",
    # NOTE: admin commands (@places, @place, @osucc, @ofail, @odrop)
    # stay at their @-prefix keys per S58 design. Folding them into
    # +place/config etc. would clobber their native ctx.switches
    # handling (e.g., @places/clear reads "clear" from ctx.switches,
    # but +place/config clear would set ctx.switches=["config"]
    # and lose the /clear signal).
    # NOTE: tt, ttooc, mutter, mu stay BARE per S54 policy
    # (natural RP shortcuts). Not routed through this umbrella.
}


class PlaceUmbrellaCommand(BaseCommand):
    """`+place` umbrella — places / seating / exit-messages.

    Canonical              Bare aliases (still work)
    --------------------   ---------------------------
    +place                 places, place (view places in this room — default)
    +place/view            places (same as default)
    +place/join <name>     join, sit
    +place/depart          depart, stand
    +place/config          @places (admin: configure places in this room)
    +place/set <args>      @place (admin: set a specific place)
    +place/osucc <msg>     @osucc (admin: exit success message)
    +place/ofail <msg>     @ofail (admin: exit failure message)
    +place/odrop <msg>     @odrop (admin: exit drop-off message)

    `+place` with no switch lists places in this room (the legacy
    PlacesCommand behavior). Seating verbs (join/depart) are
    canonical under +place; bare RP shortcuts (tt, ttooc, mutter)
    remain bare per the S54 rename policy — those are natural RP
    actions players type without role context.
    """

    key = "+place"
    aliases = [
        # View
        "places", "place",
        # Seating
        "join", "sit",
        "depart", "stand",
        # NOTE: admin @-prefix aliases stay on their per-verb classes;
        # the umbrella only provides canonical +place/<switch> forms.
    ]
    help_text = (
        "All places verbs live under +place/<switch>. "
        "Bare verbs (places, join, depart) still work. "
        "RP shortcuts (tt, ttooc, mutter) stay bare."
    )
    usage = "+place[/switch] [args]  — see 'help +place' for all switches"
    valid_switches = [
        "view", "join", "depart",
    ]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _PLACE_ALIAS_TO_SWITCH.get(typed, "view")

        impl = _PLACE_SWITCH_IMPL.get(switch)
        if impl is None:
            await ctx.session.send_line(
                f"  Unknown place switch: /{switch}. "
                f"Type 'help +place' for the full list."
            )
            return
        await impl.execute(ctx)


def _init_place_switch_impl():
    global _PLACE_SWITCH_IMPL
    _PLACE_SWITCH_IMPL = {
        "view":   PlacesCommand(),
        "join":   JoinPlaceCommand(),
        "depart": DepartPlaceCommand(),
        # NOTE: admin commands (@places, @place, @osucc, @ofail, @odrop)
        # stay at their @-prefix keys per S58 design. Folding them
        # here would clobber their native ctx.switches handling.
    }


_init_place_switch_impl()
