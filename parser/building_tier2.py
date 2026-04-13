"""
Tier 2 building commands - quality of life tools.

@set       - Set properties on rooms/exits (environment, cover, gravity, etc.)
@lock      - Lock an exit (skill check, key item, faction, admin-only)
@entrances - Show all exits leading to the current room
@find      - Search for rooms or objects by name
@zone      - Create and assign zones
@create    - Create in-game objects (items, weapons, datapads)
@success   - Set custom success message on an exit
@fail      - Set custom failure message on a locked exit
@emit      - Make the room emit ambient text
@grant     - Grant builder/admin status to a player (admin only)
"""
import json
from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi


class SetCommand(BaseCommand):
    key = "@set"
    aliases = ["@succ"]
    access_level = AccessLevel.BUILDER
    help_text = "Set a property on the current room or an exit."
    usage = "@set <property> = <value>  |  @set [here] to show all"

    async def execute(self, ctx: CommandContext):
        room_id = ctx.session.character["room_id"]
        room = await ctx.db.get_room(room_id)

        if not ctx.args or ctx.args.strip().lower() in ("here", "show"):
            # Show current properties
            props = json.loads(room.get("properties", "{}"))
            await ctx.session.send_line(ansi.header(f"=== Properties: {room['name']} ==="))
            if not props:
                await ctx.session.send_line("  (no properties set)")
            else:
                for k, v in sorted(props.items()):
                    await ctx.session.send_line(f"  {ansi.cyan(k):25s} = {v}")
            await ctx.session.send_line("")
            await ctx.session.send_line("  Common properties: environment (indoor/outdoor/space),")
            await ctx.session.send_line("  gravity (normal/low/zero), atmosphere (breathable/vacuum/toxic),")
            await ctx.session.send_line("  cover (none/light/heavy), lighting (bright/dim/dark)")
            return

        if "=" not in ctx.args:
            await ctx.session.send_line("Usage: @set <property> = <value>")
            await ctx.session.send_line("  @set environment = indoor")
            await ctx.session.send_line("  @set cover = heavy")
            await ctx.session.send_line("  @set <property> =     (blank value removes it)")
            return

        key, val = ctx.args.split("=", 1)
        key = key.strip().lower()
        val = val.strip()

        props = json.loads(room.get("properties", "{}"))

        if not val:
            # Remove property
            if key in props:
                del props[key]
                await ctx.db.update_room(room_id, properties=json.dumps(props))
                await ctx.session.send_line(ansi.success(f"  Property '{key}' removed."))
            else:
                await ctx.session.send_line(f"  Property '{key}' not set.")
        else:
            props[key] = val
            await ctx.db.update_room(room_id, properties=json.dumps(props))
            await ctx.session.send_line(ansi.success(f"  {key} = {val}"))


class LockCommand(BaseCommand):
    key = "@lock"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Lock an exit with a composable expression."
    usage = "@lock <direction> = <expression>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @lock <direction> = <expression>")
            await ctx.session.send_line("  Atoms:")
            await ctx.session.send_line("    admin, builder         - require flag")
            await ctx.session.send_line("    species:<name>         - require species")
            await ctx.session.send_line("    skill:<name>:<ND>      - require minimum skill")
            await ctx.session.send_line("    has:<object>           - require carrying item")
            await ctx.session.send_line("    wounded                - requires wounded status")
            await ctx.session.send_line("    force_sensitive        - requires Force sensitivity")
            await ctx.session.send_line("    open / none            - remove lock")
            await ctx.session.send_line("  Operators: & (AND), | (OR), ! (NOT), ( )")
            await ctx.session.send_line("  Examples:")
            await ctx.session.send_line("    @lock east = has:keycard")
            await ctx.session.send_line("    @lock north = admin | builder")
            await ctx.session.send_line("    @lock south = species:wookiee & !wounded")
            return

        if "=" not in ctx.args:
            await ctx.session.send_line("Usage: @lock <direction> = <expression>")
            return

        dir_part, lock_part = ctx.args.split("=", 1)
        direction = dir_part.strip().lower()
        lock_str = lock_part.strip()

        here = ctx.session.character["room_id"]
        exit_data = await ctx.db.find_exit_by_dir(here, direction)
        if not exit_data:
            await ctx.session.send_line(f"  No exit '{direction}' found here.")
            return

        if lock_str.lower() in ("none", "open", ""):
            await ctx.db.update_exit(exit_data["id"], lock_data="")
            await ctx.session.send_line(ansi.success(f"  Lock removed from '{direction}'."))
            return

        # Validate by parsing
        from engine.locks import parse_lock, describe_lock
        try:
            parse_lock(lock_str)
        except Exception as e:
            await ctx.session.send_line(f"  Invalid lock expression: {e}")
            return

        await ctx.db.update_exit(exit_data["id"], lock_data=lock_str)
        await ctx.session.send_line(
            ansi.success(f"  Exit '{direction}' locked: {describe_lock(lock_str)}")
        )


class EntrancesCommand(BaseCommand):
    key = "@entrances"
    aliases = ["@ent"]
    access_level = AccessLevel.BUILDER
    help_text = "Show all exits leading to the current room."
    usage = "@entrances"

    async def execute(self, ctx: CommandContext):
        room_id = ctx.session.character["room_id"]
        room = await ctx.db.get_room(room_id)
        entrances = await ctx.db.get_entrances(room_id)

        await ctx.session.send_line(
            ansi.header(f"=== Entrances to: {room['name']} (#{room_id}) ===")
        )
        if not entrances:
            await ctx.session.send_line("  No exits lead here.")
        else:
            for e in entrances:
                lock = e.get("lock_data", "{}")
                lock_str = ""
                if lock and lock != "{}":
                    lock_info = json.loads(lock) if isinstance(lock, str) else lock
                    if lock_info:
                        lock_str = f"  {ansi.red('[LOCKED]')}"
                await ctx.session.send_line(
                    f"  #{e['id']}  from '{e['from_room_name']}' (#{e['from_room_id']}) "
                    f"via {ansi.exit_color(e['direction'])}{lock_str}"
                )
        await ctx.session.send_line("")


class FindCommand(BaseCommand):
    key = "@find"
    aliases = ["@search"]
    access_level = AccessLevel.BUILDER
    help_text = "Search for rooms by name."
    usage = "@find <search term>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @find <search term>")
            return

        rooms = await ctx.db.find_rooms(ctx.args.strip())
        await ctx.session.send_line(
            ansi.header(f"=== Rooms matching '{ctx.args.strip()}' ===")
        )
        if not rooms:
            await ctx.session.send_line("  No rooms found.")
        else:
            for r in rooms:
                zone = f" [zone {r['zone_id']}]" if r.get("zone_id") else ""
                await ctx.session.send_line(f"  #{r['id']:5d}  {r['name']}{zone}")
        await ctx.session.send_line(f"  {ansi.dim(f'{len(rooms)} result(s)')}")
        await ctx.session.send_line("")


class ZoneCommand(BaseCommand):
    key = "@zone"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create, assign, or list zones."
    usage = "@zone list  |  @zone create <name>  |  @zone set <#id>  |  @zone here"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage:")
            await ctx.session.send_line("  @zone list              - List all zones")
            await ctx.session.send_line("  @zone create <name>     - Create a new zone")
            await ctx.session.send_line("  @zone set <#zone_id>    - Assign current room to a zone")
            await ctx.session.send_line("  @zone clear             - Remove current room from its zone")
            await ctx.session.send_line("  @zone here              - Show current room's zone")
            return

        parts = ctx.args.split(None, 1)
        subcmd = parts[0].lower()
        subargs = parts[1].strip() if len(parts) > 1 else ""

        if subcmd == "list":
            await self._list_zones(ctx)
        elif subcmd == "create":
            await self._create_zone(ctx, subargs)
        elif subcmd == "set":
            await self._set_zone(ctx, subargs)
        elif subcmd == "clear":
            await self._clear_zone(ctx)
        elif subcmd == "here":
            await self._show_zone(ctx)
        else:
            await ctx.session.send_line(f"  Unknown subcommand: '{subcmd}'")

    async def _list_zones(self, ctx):
        rows = await ctx.db._db.execute_fetchall(
            "SELECT z.id, z.name, z.parent_id, COUNT(r.id) as room_count "
            "FROM zones z LEFT JOIN rooms r ON r.zone_id = z.id "
            "GROUP BY z.id ORDER BY z.id"
        )
        await ctx.session.send_line(ansi.header("=== Zones ==="))
        if not rows:
            await ctx.session.send_line("  No zones created yet.")
        else:
            for z in rows:
                z = dict(z)
                parent = f" (parent: #{z['parent_id']})" if z.get("parent_id") else ""
                await ctx.session.send_line(
                    f"  #{z['id']:4d}  {z['name']:30s}  "
                    f"{z['room_count']} room(s){parent}"
                )
        await ctx.session.send_line("")

    async def _create_zone(self, ctx, name):
        if not name:
            await ctx.session.send_line("  Usage: @zone create <name>")
            return
        cursor = await ctx.db._db.execute(
            "INSERT INTO zones (name) VALUES (?)", (name,)
        )
        await ctx.db._db.commit()
        await ctx.session.send_line(
            ansi.success(f"  Zone '{name}' created as #{cursor.lastrowid}.")
        )

    async def _set_zone(self, ctx, zone_str):
        if not zone_str:
            await ctx.session.send_line("  Usage: @zone set <#zone_id>")
            return
        zone_id = zone_str.lstrip("#")
        try:
            zone_id = int(zone_id)
        except ValueError:
            await ctx.session.send_line(f"  Invalid zone ID: '{zone_str}'")
            return

        rows = await ctx.db._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        if not rows:
            await ctx.session.send_line(f"  Zone #{zone_id} not found.")
            return

        room_id = ctx.session.character["room_id"]
        await ctx.db.update_room(room_id, zone_id=zone_id)
        zone = dict(rows[0])
        await ctx.session.send_line(
            ansi.success(f"  Room assigned to zone '{zone['name']}' (#{zone_id}).")
        )

    async def _clear_zone(self, ctx):
        room_id = ctx.session.character["room_id"]
        await ctx.db.update_room(room_id, zone_id=None)
        await ctx.session.send_line(ansi.success("  Room removed from its zone."))

    async def _show_zone(self, ctx):
        room = await ctx.db.get_room(ctx.session.character["room_id"])
        zone_id = room.get("zone_id")
        if not zone_id:
            await ctx.session.send_line("  This room is not assigned to a zone.")
            return
        rows = await ctx.db._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        if rows:
            zone = dict(rows[0])
            await ctx.session.send_line(f"  Zone: '{zone['name']}' (#{zone['id']})")
        else:
            await ctx.session.send_line(f"  Zone #{zone_id} (missing from DB)")


class CreateObjCommand(BaseCommand):
    key = "@create"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Create an in-game object in your inventory."
    usage = "@create <type> <name>  (types: item, weapon, armor, datapad)"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @create <type> <name>")
            await ctx.session.send_line("  Types: item, weapon, armor, datapad, container")
            await ctx.session.send_line("  Example: @create weapon DL-44 Heavy Blaster Pistol")
            return

        parts = ctx.args.split(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line("  Need both a type and a name.")
            return

        obj_type = parts[0].lower()
        obj_name = parts[1].strip()

        valid_types = ("item", "weapon", "armor", "datapad", "container", "key", "consumable")
        if obj_type not in valid_types:
            await ctx.session.send_line(
                f"  Unknown type: '{obj_type}'. Valid: {', '.join(valid_types)}"
            )
            return

        char_id = ctx.session.character["id"]
        cursor = await ctx.db._db.execute(
            """INSERT INTO objects (type, name, owner_id, data)
               VALUES (?, ?, ?, '{}')""",
            (obj_type, obj_name, char_id),
        )
        await ctx.db._db.commit()
        await ctx.session.send_line(
            ansi.success(f"  {obj_type.capitalize()} '{obj_name}' created as object #{cursor.lastrowid}.")
        )


class SuccessCommand(BaseCommand):
    key = "@success"
    aliases = ["@succ"]
    access_level = AccessLevel.BUILDER
    help_text = "Set a custom message shown when someone uses an exit."
    usage = "@success <direction> = <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @success <direction> = <message>")
            await ctx.session.send_line("  @success north = You push through the cantina doors.")
            return

        dir_part, msg = ctx.args.split("=", 1)
        direction = dir_part.strip().lower()
        msg = msg.strip()
        here = ctx.session.character["room_id"]

        exit_data = await ctx.db.find_exit_by_dir(here, direction)
        if not exit_data:
            await ctx.session.send_line(f"  No exit '{direction}' found here.")
            return

        # Store in lock_data JSON (extend it)
        lock = json.loads(exit_data.get("lock_data", "{}"))
        lock["success_msg"] = msg
        await ctx.db.update_exit(exit_data["id"], lock_data=json.dumps(lock))
        await ctx.session.send_line(ansi.success(f"  Success message set on '{direction}'."))


class FailCommand(BaseCommand):
    key = "@fail"
    aliases = []
    access_level = AccessLevel.BUILDER
    help_text = "Set a message shown when someone fails to use a locked exit."
    usage = "@fail <direction> = <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @fail <direction> = <message>")
            await ctx.session.send_line("  @fail east = The blast door is sealed shut.")
            return

        dir_part, msg = ctx.args.split("=", 1)
        direction = dir_part.strip().lower()
        msg = msg.strip()
        here = ctx.session.character["room_id"]

        exit_data = await ctx.db.find_exit_by_dir(here, direction)
        if not exit_data:
            await ctx.session.send_line(f"  No exit '{direction}' found here.")
            return

        lock = json.loads(exit_data.get("lock_data", "{}"))
        lock["fail_msg"] = msg
        await ctx.db.update_exit(exit_data["id"], lock_data=json.dumps(lock))
        await ctx.session.send_line(ansi.success(f"  Failure message set on '{direction}'."))


class EmitCommand(BaseCommand):
    key = "@emit"
    aliases = ["@remit"]
    access_level = AccessLevel.BUILDER
    help_text = "Emit text to the room as if the room itself said it."
    usage = "@emit <text>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Usage: @emit <text>")
            await ctx.session.send_line("  Text appears to everyone in the room with no attribution.")
            return

        room_id = ctx.session.character["room_id"]
        for s in ctx.session_mgr.sessions_in_room(room_id):
            await s.send_line(ctx.args)


class GrantCommand(BaseCommand):
    key = "@grant"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = "Grant builder or admin status to a player."
    usage = "@grant <player> = <builder|admin>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @grant <player> = <builder|admin>")
            return

        name_part, role_part = ctx.args.split("=", 1)
        target_name = name_part.strip()
        role = role_part.strip().lower()

        if role not in ("builder", "admin"):
            await ctx.session.send_line("  Role must be 'builder' or 'admin'.")
            return

        # Find the target player's account
        rows = await ctx.db._db.execute_fetchall(
            "SELECT a.* FROM accounts a JOIN characters c ON c.account_id = a.id "
            "WHERE c.name = ? COLLATE NOCASE",
            (target_name,),
        )
        if not rows:
            await ctx.session.send_line(f"  Player '{target_name}' not found.")
            return

        account = dict(rows[0])
        field = "is_builder" if role == "builder" else "is_admin"
        await ctx.db._db.execute(
            f"UPDATE accounts SET {field} = 1 WHERE id = ?",
            (account["id"],),
        )
        await ctx.db._db.commit()

        await ctx.session.send_line(
            ansi.success(f"  {target_name} granted {role} status.")
        )

        # Update the target's live session if online
        target_session = ctx.session_mgr.find_by_account(account["id"])
        if target_session and target_session.account:
            target_session.account[field] = 1
            await target_session.send_line(
                ansi.system_msg(f"You have been granted {role} status!")
            )


def register_building_tier2(registry):
    """Register Tier 2 building commands."""
    cmds = [
        SetCommand(), LockCommand(), EntrancesCommand(),
        FindCommand(), ZoneCommand(), CreateObjCommand(),
        SuccessCommand(), FailCommand(), EmitCommand(),
        GrantCommand(), SetAttrCommand(), GetAttrCommand(),
    ]
    for cmd in cmds:
        registry.register(cmd)


class GetAttrCommand(BaseCommand):
    """@getattr — show character attribute JSON keys (admin)."""
    key = "@getattr"
    aliases = ["@ga"]
    access_level = AccessLevel.ADMIN
    help_text = "Show character attributes. Usage: @getattr [key]"
    usage = "@getattr [key]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        a = json.loads(char.get("attributes", "{}") or "{}")
        key = ctx.args.strip() if ctx.args else None
        if key:
            val = a.get(key, "<not set>")
            await ctx.session.send_line(
                f"  {key} = {json.dumps(val, indent=2)}"
            )
        else:
            await ctx.session.send_line("  Attribute keys:")
            for k, v in sorted(a.items()):
                snippet = str(v)[:60]
                await ctx.session.send_line(f"    {k}: {snippet}")


class SetAttrCommand(BaseCommand):
    """@setattr — set a character attribute value (admin, for testing)."""
    key = "@setattr"
    aliases = ["@sa"]
    access_level = AccessLevel.ADMIN
    help_text = "Set a character attribute. Usage: @setattr <key> = <json_value>"
    usage = "@setattr <key> = <value>"

    async def execute(self, ctx: CommandContext):
        import json as _json
        if not ctx.args or "=" not in ctx.args:
            await ctx.session.send_line("Usage: @setattr <key> = <json_value>")
            await ctx.session.send_line("  e.g. @setattr starter_quest = 10")
            await ctx.session.send_line("  e.g. @setattr spacer_quest = null")
            return

        key, raw = ctx.args.split("=", 1)
        key = key.strip()
        raw = raw.strip()

        try:
            val = _json.loads(raw)
        except _json.JSONDecodeError:
            # Treat as bare string if not valid JSON
            val = raw

        char = ctx.session.character
        a = _json.loads(char.get("attributes", "{}") or "{}")

        if val is None:
            a.pop(key, None)
            await ctx.session.send_line(f"  Removed attribute: {key}")
        else:
            a[key] = val
            await ctx.session.send_line(
                f"  Set {key} = {_json.dumps(val)[:80]}"
            )

        char["attributes"] = _json.dumps(a)
        await ctx.db.save_character(char["id"], attributes=char["attributes"])
        await ctx.session.send_line(ansi.success("  Saved."))
