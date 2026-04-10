# -*- coding: utf-8 -*-
"""
Built-in commands for Phase 1: navigation, communication, info, and admin.
"""
import textwrap
from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi


async def _check_hostile_npcs(ctx: CommandContext, room_id: int):
    """
    Check for hostile NPCs when a player enters a room.
    If found, initiate combat with them attacking the player.
    """
    from engine.npc_combat_ai import (
        check_room_hostiles, build_npc_character, get_npc_behavior,
    )
    from parser.combat_commands import (
        _get_or_create_combat, _active_combats, _npc_behaviors,
        _broadcast_events, _auto_declare_npc_actions,
    )
    from engine.combat import CombatAction, ActionType
    from engine.character import Character

    char = ctx.session.character
    if not char:
        return

    # ── Security zone — no NPC aggro in SECURED areas ───────────────────────
    from engine.security import get_effective_security, SecurityLevel
    _sec = await get_effective_security(room_id, ctx.db)
    if _sec == SecurityLevel.SECURED:
        return
    # ── End security check ───────────────────────────────────────────────────

    hostiles = await check_room_hostiles(room_id, char["id"], ctx.db)
    if not hostiles:
        return

    # Get or create combat
    cover_max = await ctx.db.get_room_property(room_id, "cover_max", 0)
    combat = _get_or_create_combat(room_id, cover_max=cover_max)
    new_combat = combat.round_num == 0

    # Add the player
    if not combat.get_combatant(char["id"]):
        char_obj = Character.from_db_dict(char)
        combat.add_combatant(char_obj)

    # Add hostile NPCs
    added_names = []
    for npc_row in hostiles:
        npc_id = npc_row["id"]
        if combat.get_combatant(npc_id):
            continue
        npc_char = build_npc_character(npc_row)
        if not npc_char:
            continue
        combatant = combat.add_combatant(npc_char)
        combatant.is_npc = True
        _npc_behaviors[npc_id] = get_npc_behavior(npc_row)
        added_names.append(npc_row["name"])

    if not added_names:
        return

    # Announce aggro
    names = ", ".join(added_names)
    await ctx.session_mgr.broadcast_to_room(
        room_id,
        ansi.combat_msg(f"{names} {'attacks' if len(added_names) == 1 else 'attack'}!"),
    )

    # Roll initiative
    if new_combat:
        events = combat.roll_initiative()
        await _broadcast_events(events, ctx.session_mgr, room_id)

    # Auto-declare NPC actions
    await _auto_declare_npc_actions(combat, ctx)

    # Prompt the player
    await ctx.session.send_line(
        ansi.combat_msg("You're under attack! Declare: attack/dodge/aim/flee")
    )


class LookCommand(BaseCommand):
    key = "look"
    aliases = ["l"]
    help_text = (
        "Look at your surroundings, an object, or a character.\n"
        "With no argument, shows the room, exits, NPCs, and players.\n"
        "\n"
        "EXAMPLES:\n"
        "  look            -- the current room\n"
        "  look bartender  -- an NPC or object\n"
        "  look Tundra     -- another player"
    )
    usage = "look [target]"

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("You must be in the game to look around.")
            return

        if ctx.args:
            await self._look_at(ctx)
            return

        # ── Look at the current room ──
        room = await ctx.db.get_room(char["room_id"])
        if not room:
            await session.send_line("You are in a void. Something has gone wrong.")
            return

        # Room name
        await session.send_line(ansi.room_name(room["name"]))

        # Environment flavor line (from inherited properties)
        props = await ctx.db.get_all_room_properties(char["room_id"])
        flavor_parts = []
        lighting = props.get("lighting", "")
        if lighting and lighting != "bright":
            flavor_parts.append(f"The lighting is {lighting}.")
        env = props.get("environment", "")
        cover_max = props.get("cover_max", 0)
        if cover_max >= 3:
            flavor_parts.append("Heavy cover available.")
        elif cover_max == 2:
            flavor_parts.append("Moderate cover available.")
        elif cover_max == 1:
            flavor_parts.append("Minimal cover here.")

        if flavor_parts:
            await session.send_line(
                f"  {ansi.DIM}{' '.join(flavor_parts)}{ansi.RESET}"
            )

        # Room description (word-wrapped)
        desc = room["desc_long"] or room["desc_short"] or "You see nothing special."
        for line in textwrap.wrap(desc, width=session.wrap_width - 2):
            await session.send_line(f"  {line}")

        # Exits (show locks)
        exits = await ctx.db.get_exits(char["room_id"])
        if exits:
            exit_parts = []
            for e in exits:
                lock = e.get("lock_data", "")
                if lock and lock not in ("{}", "", "open"):
                    exit_parts.append(
                        f"{ansi.exit_color(e['direction'])}"
                        f"{ansi.DIM}[locked]{ansi.RESET}"
                    )
                else:
                    exit_parts.append(ansi.exit_color(e["direction"]))
            await session.send_line(f"  Exits: {', '.join(exit_parts)}")

        # Other characters in the room
        others = await ctx.db.get_characters_in_room(char["room_id"])
        present = []
        for other in others:
            if other["id"] != char["id"]:
                present.append(other)
        for other in present:
            equip_str = ""
            import json as _json
            try:
                eq = _json.loads(other.get("equipment", "{}") or "{}")
                if eq.get("weapon"):
                    from engine.weapons import get_weapon_registry
                    w = get_weapon_registry().get(eq["weapon"])
                    if w:
                        equip_str = f", wielding a {w.name}"
            except Exception:
                pass
            await session.send_line(
                f"  {ansi.player_name(other['name'])} is here{equip_str}."
            )

        # NPCs in the room
        npcs = await ctx.db.get_npcs_in_room(char["room_id"])
        if npcs:
            NPC_CONDENSE_THRESHOLD = 5
            if len(npcs) >= NPC_CONDENSE_THRESHOLD:
                # Condensed: group NPC names into wrapped lines
                npc_names = [ansi.npc_name(n["name"]) for n in npcs]
                # Build a comma-separated string and wrap it
                # We need to estimate ANSI-free width for wrapping
                plain_names = [n["name"] for n in npcs]
                # Wrap the plain version, then rebuild with ANSI
                name_str = ", ".join(plain_names)
                indent = "  Also here: "
                subsequent = " " * len("  Also here: ")
                wrapped = textwrap.wrap(
                    name_str, width=session.wrap_width - 2,
                    initial_indent=indent,
                    subsequent_indent=subsequent,
                )
                # Re-inject ANSI coloring into the wrapped output
                for wline in wrapped:
                    for pn in plain_names:
                        wline = wline.replace(
                            pn, ansi.npc_name(pn), 1)
                    await session.send_line(wline)
                await session.send_line(
                    f"  {ansi.DIM}(Type 'look <name>' to examine someone.)"
                    f"{ansi.RESET}"
                )
            else:
                # Few NPCs: show full descriptions
                for npc in npcs:
                    desc = npc.get("description", "")
                    if desc and not desc.startswith("["):
                        await session.send_line(
                            f"  {ansi.npc_name(npc['name'])} is here."
                            f" {desc}"
                        )
                    else:
                        await session.send_line(
                            f"  {ansi.npc_name(npc['name'])} is here."
                        )

        await session.send_line("")

    async def _look_at(self, ctx: CommandContext):
        """Look at a specific target (character, NPC, or object)."""
        from engine.matching import match_in_room, MatchResult
        import json as _json

        char = ctx.session.character
        match = await match_in_room(
            ctx.args, char["room_id"], char["id"], ctx.db,
            session_mgr=ctx.session_mgr,
        )

        if match.result == MatchResult.AMBIGUOUS:
            await ctx.session.send_line(f"  {match.error_message(ctx.args)}")
            return

        if not match.found:
            await ctx.session.send_line(f"  You don't see '{ctx.args}' here.")
            return

        c = match.candidate
        if c.obj_type == "npc":
            # NPC description
            await ctx.session.send_line(f"  {ansi.npc_name(c.name)}")
            desc = c.data.get("description", "")
            if desc:
                for line in textwrap.wrap(desc, width=ctx.session.wrap_width - 4):
                    await ctx.session.send_line(f"    {line}")
            species = c.data.get("species", "Unknown")
            await ctx.session.send_line(f"    Species: {species}")

        elif c.obj_type == "character":
            # Character description
            await ctx.session.send_line(f"  {ansi.player_name(c.name)}")
            desc = c.data.get("description", "")
            if desc:
                for line in textwrap.wrap(desc, width=ctx.session.wrap_width - 4):
                    await ctx.session.send_line(f"    {line}")
            species = c.data.get("species", "Human")
            await ctx.session.send_line(f"    Species: {species}")
            # Show equipped weapon
            try:
                eq = _json.loads(c.data.get("equipment", "{}") or "{}")
                if eq.get("weapon"):
                    from engine.weapons import get_weapon_registry
                    w = get_weapon_registry().get(eq["weapon"])
                    if w:
                        await ctx.session.send_line(f"    Wielding: {w.name}")
            except Exception:
                pass
            # Wound status
            wl = c.data.get("wound_level", 0)
            if wl > 0:
                from engine.character import WoundLevel
                await ctx.session.send_line(
                    f"    Condition: {WoundLevel(wl).display_name}"
                )

        elif c.obj_type == "room":
            await ctx.session.send_line(f"  This is {c.name}.")

        else:
            await ctx.session.send_line(f"  You see {c.name}.")


class MoveCommand(BaseCommand):
    key = "move"
    aliases = ["repair"]
    help_text = "Move in a direction."
    usage = "north/south/east/west/up/down (or abbreviations)"

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            return

        direction = ctx.args.lower().strip()
        if not direction:
            await session.send_line("Move where? Specify a direction.")
            return

        exits = await ctx.db.get_exits(char["room_id"])
        matching = [e for e in exits if e["direction"].lower() == direction]

        if not matching:
            await session.send_line(f"You can't go {direction}.")
            return

        exit_data = matching[0]

        # Check exit lock (composable lock expressions)
        lock_str = exit_data.get("lock_data", "{}")
        if lock_str and lock_str not in ("{}", "", "open"):
            from engine.locks import eval_lock
            # Build context from account data
            account = await ctx.db.get_account(char.get("account_id", 0))
            lock_ctx = {}
            if account:
                lock_ctx["is_admin"] = bool(account.get("is_admin"))
                lock_ctx["is_builder"] = bool(account.get("is_builder"))
            passed, reason = eval_lock(lock_str, char, lock_ctx)
            if not passed:
                await session.send_line(f"  The way {direction} is locked. ({reason})")
                return

        old_room_id = char["room_id"]
        new_room_id = exit_data["to_room_id"]

        # Notify the old room
        await ctx.session_mgr.broadcast_to_room(
            old_room_id,
            f"{ansi.player_name(char['name'])} leaves {direction}.",
            exclude=session,
        )

        # Move the character
        char["room_id"] = new_room_id
        await ctx.db.save_character(char["id"], room_id=new_room_id)

        # Notify the new room
        await ctx.session_mgr.broadcast_to_room(
            new_room_id,
            f"{ansi.player_name(char['name'])} arrives.",
            exclude=session,
        )

        # Auto-look
        look_cmd = LookCommand()
        look_ctx = CommandContext(
            session=session,
            raw_input="look",
            command="look",
            args="",
            args_list=[],
            db=ctx.db,
            session_mgr=ctx.session_mgr,
        )
        await look_cmd.execute(look_ctx)

        # Check for hostile NPCs in the new room
        await _check_hostile_npcs(ctx, new_room_id)

        # Tutorial: start hint timer if in tutorial zone; check starter + discovery quests
        try:
            from engine.tutorial_v2 import (
                start_hint_timer, check_starter_quest, check_discovery_quest,
                check_core_tutorial_step, check_elective_progress,
                is_tutorial_zone, set_tutorial_core,
                start_starter_quest, get_tutorial_state
            )
            new_room = await ctx.db.get_room(new_room_id)
            if new_room:
                import json as _tj
                rprops = new_room.get("properties", "{}")
                if isinstance(rprops, str):
                    try:
                        rprops = _tj.loads(rprops)
                    except Exception:
                        rprops = {}

                ts = get_tutorial_state(char)

                if is_tutorial_zone(rprops):
                    # Player is in tutorial — mark as in_progress if not yet started
                    if ts["core"] == "not_started":
                        set_tutorial_core(char, "in_progress", step=-1)
                        await ctx.db.save_character(
                            char["id"], attributes=char.get("attributes", "{}")
                        )
                    start_hint_timer(session, new_room.get("name", ""))
                    # Advance step counter + show per-room guidance [v21]
                    await check_core_tutorial_step(
                        session, ctx.db, new_room.get("name", "")
                    )
                else:
                    # Player just left tutorial zone into the live world
                    if ts["core"] == "in_progress":
                        set_tutorial_core(char, "complete")
                        start_starter_quest(char)
                        await ctx.db.save_character(
                            char["id"], attributes=char.get("attributes", "{}")
                        )
                        await session.send_line(
                            "\n  \033[1;32m[TUTORIAL COMPLETE]\033[0m "
                            "You've arrived in Mos Eisley. "
                            "Find Kessa Dray in the cantina for your next steps.\n"
                            "  Type \033[1;33mtraining list\033[0m to track your progress "
                            "or \033[1;33mtraining\033[0m to return for advanced training.\n"
                        )

                # Starter quest room-entry check
                await check_starter_quest(
                    session, ctx.db,
                    trigger="enter",
                    room_name=new_room.get("name", ""),
                )
                # Discovery quest room-entry check
                await check_discovery_quest(session, ctx.db, new_room.get("name", ""))
                # Elective module step advancement [v25]
                await check_elective_progress(session, ctx.db, new_room.get("name", ""))
        except Exception:
            pass  # Non-critical


class SayCommand(BaseCommand):
    key = "say"
    aliases = ["'", '"']
    help_text = (
        "Say something aloud. Everyone in the room hears it.\n"
        "Shortcut: type a single-quote then your message.\n"
        "\n"
        "EXAMPLE: say Nice ship. She yours?\n"
        "Output:  You say, \"Nice ship. She yours?\""
    )
    usage = "say <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Say what?")
            return

        char = ctx.session.character
        name = ansi.player_name(char["name"])

        await ctx.session.send_line(f'You say, "{ctx.args}"')
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f'{name} says, "{ctx.args}"',
            exclude=ctx.session,
        )
        # Chat tag for WebSocket comms panel
        await ctx.session_mgr.broadcast_chat(
            "ic", char["name"], ctx.args,
            room_id=char["room_id"],
        )


class WhisperCommand(BaseCommand):
    key = "whisper"
    aliases = ["wh", "page", "tell"]
    help_text = (
        "Private message to someone in the same room.\n"
        "Only you and the target see it.\n"
        "\n"
        "EXAMPLE: whisper Tundra = Meet me at bay 94."
    )
    usage = "whisper <player> = <message>"

    async def execute(self, ctx: CommandContext):
        if "=" not in ctx.args:
            await ctx.session.send_line("Usage: whisper <player> = <message>")
            return

        target_name, message = ctx.args.split("=", 1)
        target_name = target_name.strip()
        message = message.strip()

        if not target_name or not message:
            await ctx.session.send_line("Usage: whisper <player> = <message>")
            return

        # Find target in room
        room_id = ctx.session.character["room_id"]
        room_sessions = ctx.session_mgr.sessions_in_room(room_id)
        target_session = None
        for s in room_sessions:
            if s.character and s.character["name"].lower() == target_name.lower():
                target_session = s
                break

        if not target_session:
            await ctx.session.send_line(f"You don't see '{target_name}' here.")
            return

        char_name = ansi.player_name(ctx.session.character["name"])
        await ctx.session.send_line(
            f'You whisper to {ansi.player_name(target_name)}, "{message}"'
        )
        await target_session.send_line(
            f'{char_name} whispers to you, "{message}"'
        )


class EmoteCommand(BaseCommand):
    key = "emote"
    aliases = [":", "pose", "em"]
    help_text = (
        "Describe an action your character performs.\n"
        "Shows as your name followed by the text.\n"
        "\n"
        "SHORTCUTS:\n"
        "  :draws a blaster  -- Tundra draws a blaster\n"
        "  ;'s hand shakes   -- Tundra's hand shakes (semipose)\n"
        "\n"
        "Write in third person present tense."
    )
    usage = "emote <action>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("Emote what?")
            return

        char = ctx.session.character
        name = ansi.player_name(char["name"])
        text = f"{name} {ctx.args}"

        # Send to everyone in the room including the actor
        room_id = char["room_id"]
        for s in ctx.session_mgr.sessions_in_room(room_id):
            await s.send_line(text)


class WhoCommand(BaseCommand):
    key = "+who"
    aliases = ["who", "online", "+online"]
    help_text = "See who is online."
    usage = "who"

    async def execute(self, ctx: CommandContext):
        in_game = [
            s for s in ctx.session_mgr.all
            if s.is_in_game and s.character
        ]

        await ctx.session.send_line(ansi.header("=== Who's Online ==="))
        if not in_game:
            await ctx.session.send_line("  No one is currently in the game.")
        else:
            for s in in_game:
                name = s.character["name"]
                species = s.character.get("species", "Unknown")
                proto = s.protocol.value.upper()
                await ctx.session.send_line(
                    f"  {ansi.player_name(name):30s} {species:15s} [{proto}]"
                )
        await ctx.session.send_line(
            f"  {ansi.dim(f'{len(in_game)} player(s) online.')}"
        )
        await ctx.session.send_line("")


class InventoryCommand(BaseCommand):
    key = "+inv"
    aliases = ["inventory", "inv", "i", "+inventory"]
    help_text = "View your inventory."
    usage = "inventory"

    async def execute(self, ctx: CommandContext):
        await ctx.session.send_line(ansi.header("=== Inventory ==="))
        await ctx.session.send_line("  Your inventory is empty.")
        await ctx.session.send_line("  (Inventory system coming in Phase 3+)")
        await ctx.session.send_line("")


class SheetCommand(BaseCommand):
    key = "+sheet"
    aliases = ["sheet", "score", "stats", "+score", "+stats", "sc"]
    help_text = "View your character sheet."
    usage = "+sheet [/brief|/skills|/combat]"
    valid_switches = ["brief", "skills", "combat"]

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        import os
        from engine.character import SkillRegistry
        skill_reg = SkillRegistry()
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        skills_path = os.path.join(data_dir, "skills.yaml")
        if os.path.exists(skills_path):
            skill_reg.load_file(skills_path)

        # Dispatch by switch
        if "brief" in ctx.switches:
            from engine.sheet_renderer import render_brief_sheet
            lines = render_brief_sheet(char, skill_reg)
        elif "skills" in ctx.switches:
            from engine.sheet_renderer import render_skills_sheet
            lines = render_skills_sheet(char, skill_reg)
        elif "combat" in ctx.switches:
            from engine.sheet_renderer import render_combat_sheet
            lines = render_combat_sheet(char, skill_reg)
        else:
            from engine.sheet_renderer import render_game_sheet
            lines = render_game_sheet(char, skill_reg)

        for line in lines:
            await ctx.session.send_line(line)


class HelpCommand(BaseCommand):
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
        "Space": ["+ship", "pilot", "gunner", "copilot",
                  "engineer", "navigator", "commander", "sensors",
                  "vacate", "assist", "coordinate",
                  "launch", "land", "scan", "fire", "evade",
                  "close", "fleeship", "tail", "resist",
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
            # Word-wrap the command list at terminal width
            plain_str = ", ".join(cmds)
            label = f"  {cat:14s} "
            indent = " " * 17  # align continuation under first cmd
            wrapped = textwrap.wrap(
                plain_str, width=ctx.session.wrap_width - 2,
                initial_indent=label,
                subsequent_indent=indent,
            )
            for i, wline in enumerate(wrapped):
                # Re-inject ANSI coloring on command names
                for c in cmds:
                    wline = wline.replace(
                        c, f"{ansi.BRIGHT_CYAN}{c}{ansi.RESET}", 1)
                # Bold the category label on first line
                if i == 0:
                    wline = wline.replace(
                        label, f"  {ansi.BOLD}{cat:14s}{ansi.RESET} ", 1)
                await ctx.session.send_line(wline)

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
        for line in entry.body.split("\n"):
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


class RespawnCommand(BaseCommand):
    key = "respawn"
    aliases = ["revive"]
    help_text = "Return to life after death. Costs credits and weapon condition."
    usage = "respawn"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game to respawn.")
            return

        wound_level = char.get("wound_level", 0)
        if wound_level < 6:  # WoundLevel.DEAD = 6
            await ctx.session.send_line("  You're not dead!")
            return

        # ── Calculate penalties ──
        credits = char.get("credits", 0)
        credit_penalty = max(100, int(credits * 0.10))  # 10% or min 100
        new_credits = max(0, credits - credit_penalty)

        # Starting room (could be expanded to nearest medical facility)
        respawn_room = 1  # Landing Pad - Mos Eisley
        # Try to find a medical room property in the future
        # For now, use config starting room

        old_room_id = char.get("room_id", 1)

        # ── Apply respawn ──
        char["wound_level"] = 2  # WoundLevel.WOUNDED (need medical treatment)
        char["credits"] = new_credits
        char["room_id"] = respawn_room

        # Persist to DB
        await ctx.db.save_character(
            char["id"],
            wound_level=2,
            credits=new_credits,
            room_id=respawn_room,
        )

        # Weapon condition penalty
        import json as _json
        equip_data = char.get("equipment", "{}")
        if isinstance(equip_data, str):
            try:
                equip_data = _json.loads(equip_data)
            except Exception:
                equip_data = {}
        if equip_data and equip_data.get("weapon"):
            from engine.items import parse_equipment_json, serialize_equipment
            item = parse_equipment_json(char.get("equipment", "{}"))
            if item:
                item.condition = max(0, item.condition - 20)
                char["equipment"] = serialize_equipment(item)
                await ctx.db.save_character(
                    char["id"], equipment=char["equipment"]
                )

        # ── Bacta tank narration ──
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}+======================================+{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}|{ansi.RESET}     "
            f"{ansi.BOLD}B A C T A   T A N K{ansi.RESET}          "
            f"{ansi.BRIGHT_CYAN}|{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_CYAN}+======================================+{ansi.RESET}"
        )
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.dim('Darkness... then the burn of bacta fluid in your lungs.')}"
        )
        await ctx.session.send_line(
            f"  {ansi.dim('Consciousness floods back. A medical droid chirps.')}"
        )
        await ctx.session.send_line(
            f"  {ansi.dim('\"Patient revived. Vital signs stabilizing.\"')}"
        )
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_YELLOW}Medical charges: {credit_penalty:,} credits deducted.{ansi.RESET}"
        )
        await ctx.session.send_line(
            f"  {ansi.dim(f'Credits remaining: {new_credits:,}')}"
        )
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}Status: Wounded{ansi.RESET} "
            f"{ansi.dim('(seek medical treatment to fully heal)')}"
        )
        await ctx.session.send_line("")

        # Notify old room
        char_name = char["name"]
        death_msg = ansi.dim(char_name + "'s body is carried away by medical droids.")
        if old_room_id != respawn_room:
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"  {death_msg}",
                exclude=ctx.session,
            )

        # Notify new room
        revive_msg = ansi.dim(char_name + " stumbles out of a bacta tank, gasping.")
        await ctx.session_mgr.broadcast_to_room(
            respawn_room,
            f"  {revive_msg}",
            exclude=ctx.session,
        )

        # Auto-look at new room
        look_cmd = LookCommand()
        look_ctx = CommandContext(
            session=ctx.session,
            raw_input="look",
            command="look",
            args="",
            args_list=[],
            db=ctx.db,
            session_mgr=ctx.session_mgr,
        )
        await look_cmd.execute(look_ctx)


class QuitCommand(BaseCommand):
    key = "quit"
    aliases = ["@quit", "logout", "QUIT"]
    access_level = AccessLevel.ANYONE
    help_text = "Disconnect from the game."
    usage = "quit"

    async def execute(self, ctx: CommandContext):
        if ctx.session.character:
            name = ctx.session.character["name"]
            room_id = ctx.session.character.get("room_id")
            await ctx.db.save_character(
                ctx.session.character["id"],
                room_id=room_id,
            )
            if room_id:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    ansi.system_msg(f"{name} has disconnected."),
                    exclude=ctx.session,
                )

        await ctx.session.close()


class OocCommand(BaseCommand):
    key = "+ooc"
    aliases = ["ooc", "@ooc"]
    help_text = "Send an out-of-character message to the room."
    usage = "@ooc <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("OOC what?")
            return

        char = ctx.session.character
        name = char["name"]
        text = f"{ansi.dim(f'[OOC] {name}: {ctx.args}')}"

        room_id = char["room_id"]
        for s in ctx.session_mgr.sessions_in_room(room_id):
            await s.send_line(text)


class DescCommand(BaseCommand):
    key = "@desc"
    aliases = ["@describe"]
    help_text = "Set your character's description."
    usage = "@desc <description>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            current = ctx.session.character.get("description", "")
            if current:
                await ctx.session.send_line(f"Current description: {current}")
            else:
                await ctx.session.send_line("You have no description set.")
            await ctx.session.send_line("Usage: @desc <description>")
            return

        ctx.session.character["description"] = ctx.args
        await ctx.db.save_character(
            ctx.session.character["id"], description=ctx.args
        )
        await ctx.session.send_line(ansi.success("Description set."))


class EquipCommand(BaseCommand):
    key = "equip"
    aliases = ["wield", "draw"]
    help_text = "Equip a weapon by name. Use 'weapons' to see available weapons."
    usage = "equip <weapon name>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            # Show currently equipped weapon with condition
            from engine.items import parse_equipment_json
            from engine.weapons import get_weapon_registry
            item = parse_equipment_json(ctx.session.character.get("equipment", "{}"))
            if item and not item.is_broken:
                wr = get_weapon_registry()
                w = wr.get(item.key)
                wname = w.name if w else item.key
                crafter = f" (crafted by {item.crafter})" if item.crafter else ""
                await ctx.session.send_line(
                    f"  Equipped: {wname} -- {item.condition_bar}{crafter}")
            elif item and item.is_broken:
                await ctx.session.send_line(
                    f"  Equipped: {item.key} -- BROKEN. Type 'repair' to fix it.")
            else:
                await ctx.session.send_line("  Nothing equipped. Type 'weapons' to see options.")
            return

        from engine.weapons import get_weapon_registry
        from engine.items import ItemInstance, serialize_equipment
        wr = get_weapon_registry()
        weapon = wr.find_by_name(ctx.args.strip())
        if not weapon:
            await ctx.session.send_line(f"  Unknown weapon '{ctx.args}'. Type 'weapons' to see the list.")
            return
        if weapon.is_armor:
            await ctx.session.send_line(f"  {weapon.name} is armor, not a weapon.")
            return

        item = ItemInstance.new_from_vendor(weapon.key)
        char = ctx.session.character
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(f"  You equip your {weapon.name}. ({weapon.damage} damage, skill: {weapon.skill})")
        )
        await ctx.session.send_line(f"  Condition: {item.condition_bar}")


class UnequipCommand(BaseCommand):
    key = "unequip"
    aliases = ["holster", "sheathe"]
    help_text = "Put away your equipped weapon."
    usage = "unequip"

    async def execute(self, ctx: CommandContext):
        # Route cargo sales to trade handler
        if ctx.args and ctx.args.strip().lower().startswith("cargo"):
            return await _handle_sell_cargo(ctx)
        from engine.items import parse_equipment_json, serialize_equipment
        from engine.weapons import get_weapon_registry

        item = parse_equipment_json(ctx.session.character.get("equipment", "{}"))
        if not item:
            await ctx.session.send_line("  You don't have a weapon equipped.")
            return
        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key

        char = ctx.session.character
        char["equipment"] = serialize_equipment(None)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        await ctx.session.send_line(ansi.success(f"  You put away your {wname}."))


class RepairCommand(BaseCommand):
    key = "+repair"
    aliases = []
    help_text = "Repair your equipped weapon. Costs credits at NPC shops, or use Technical skill for cheaper."
    usage = "repair"

    async def execute(self, ctx: CommandContext):
        from engine.items import parse_equipment_json, serialize_equipment
        from engine.weapons import get_weapon_registry

        char = ctx.session.character
        item = parse_equipment_json(char.get("equipment", "{}"))
        if not item:
            await ctx.session.send_line("  Nothing equipped to repair.")
            return

        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key
        base_cost = w.cost if w else 500

        if item.condition >= item.max_condition:
            await ctx.session.send_line(f"  Your {wname} is in perfect condition.")
            return

        if item.max_condition <= 5:
            await ctx.session.send_line(
                f"  Your {wname} is too degraded to repair further. "
                f"It's worn out -- time for a replacement.")
            return

        cost = item.repair_cost(base_cost)
        credits = char.get("credits", 0)

        await ctx.session.send_line(f"  {wname}: {item.condition_bar}")
        await ctx.session.send_line(
            f"  Repair cost: {cost:,} credits (max condition drops "
            f"{item.max_condition} -> {item.max_condition - 5})")
        await ctx.session.send_line(f"  Your credits: {credits:,}")

        if credits < cost:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}Not enough credits!{ansi.RESET}")
            return

        # Apply repair
        item.repair()
        new_credits = credits - cost
        char["credits"] = new_credits
        char["equipment"] = serialize_equipment(item)
        await ctx.db.save_character(
            char["id"], credits=new_credits, equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(
                f"  {wname} repaired! {item.condition_bar}  "
                f"({cost:,} credits spent, {new_credits:,} remaining)"))


class SellCommand(BaseCommand):
    key = "sell"
    aliases = []
    help_text = "Sell your equipped weapon to an NPC vendor (25-50% of base value)."
    usage = "sell"

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
                f"Balance: {new_credits:,} credits."))


class WeaponsListCommand(BaseCommand):
    key = "+weapons"
    aliases = ["weapons", "weaponlist", "armory", "+armory"]
    help_text = "List all known weapons in the game."
    usage = "weapons"

    async def execute(self, ctx: CommandContext):
        from engine.weapons import get_weapon_registry
        wr = get_weapon_registry()

        await ctx.session.send_line(f"  {'Weapon':<24s} {'Damage':>8s}  {'Skill':<16s} {'Short':>5s} {'Med':>5s} {'Long':>5s}")
        await ctx.session.send_line(f"  {'-'*24} {'-'*8}  {'-'*16} {'-'*5} {'-'*5} {'-'*5}")
        for w in wr.all_weapons():
            if w.is_ranged:
                ranges = f"{w.ranges[1]:>5d} {w.ranges[2]:>5d} {w.ranges[3]:>5d}"
            else:
                ranges = "Melee"
            cost_str = f"{w.cost:,}cr" if w.cost else "--"
            await ctx.session.send_line(
                f"  {w.name:<22s} {w.damage:>6s}  {w.skill:<14s} {ranges}  {cost_str:>8s}"
            )

        # Show currently equipped with condition
        from engine.items import parse_equipment_json
        item = parse_equipment_json(ctx.session.character.get("equipment", "{}"))
        if item:
            w = wr.get(item.key)
            wname = w.name if w else item.key
            await ctx.session.send_line(
                f"\n  Equipped: {ansi.BRIGHT_WHITE}{wname}{ansi.RESET} "
                f"{item.condition_bar}")




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


def register_all(registry):
    """Register all built-in commands with the registry."""
    commands = [
        LookCommand(),
        MoveCommand(),
        SayCommand(),
        WhisperCommand(),
        EmoteCommand(),
        WhoCommand(),
        InventoryCommand(),
        SheetCommand(),
        HelpCommand(),
        QuitCommand(),
        OocCommand(),
        DescCommand(),
        EquipCommand(),
        UnequipCommand(),
        RepairCommand(),
        SellCommand(),
        WeaponsListCommand(),
        RespawnCommand(),
        SemiposeCommand(),
        TradeCommand(),
    ]
    for cmd in commands:
        registry.register(cmd)

# ── Trade (player-to-player) ───────────────────────────────────────────────────

import time as _trade_time

# Pending trade offers: {(offerer_id, target_id): {offer_dict, timestamp}}
_pending_trades: dict = {}
_TRADE_TTL = 120  # 2 minutes


def _purge_trade_offers():
    now = _trade_time.time()
    stale = [k for k, v in _pending_trades.items() if now - v["ts"] > _TRADE_TTL]
    for k in stale:
        _pending_trades.pop(k, None)


async def _handle_sell_cargo(ctx) -> None:
    """Handle 'sell cargo <good> <tons>'."""
    from engine.trading import (
        TRADE_GOODS, get_planet_price, get_ship_cargo,
        cargo_quantity, remove_cargo, get_cargo_tons,
    )
    from engine.starships import get_ship_registry
    from engine.skill_checks import resolve_bargain_check
    from parser.space_commands import _get_ship_for_player, _get_systems

    # Parse args: "cargo <good> <tons>"  or  "cargo <good>" for all
    raw = (ctx.args or "").strip()
    parts = raw[len("cargo"):].strip().lower().split()
    if not parts:
        await ctx.session.send_line(
            "  Usage: sell cargo <good key> <tons>\n"
            "  Example: sell cargo raw_ore 20\n"
            "  Type 'market' to see goods in your hold."
        )
        return

    # Last token is quantity if numeric
    if len(parts) > 1 and parts[-1].isdigit():
        quantity = int(parts[-1])
        good_query = " ".join(parts[:-1]).replace(" ", "_")
    else:
        quantity = None  # sell all
        good_query = " ".join(parts).replace(" ", "_")

    good = TRADE_GOODS.get(good_query)
    if not good:
        good = next(
            (g for g in TRADE_GOODS.values()
             if good_query in g.name.lower().replace(" ", "_")),
            None,
        )
    if not good:
        await ctx.session.send_line(
            f"  Unknown trade good '{good_query}'. Type 'market' to see your hold."
        )
        return

    ship = await _get_ship_for_player(ctx)
    if not ship or not ship.get("docked_at"):
        await ctx.session.send_line("  You must be docked to sell cargo.")
        return

    import json as _j
    cargo = get_ship_cargo(ship)
    held = cargo_quantity(cargo, good.key)
    if held == 0:
        await ctx.session.send_line(
            f"  You have no {good.name} in the cargo hold."
        )
        return

    if quantity is None:
        quantity = held
    elif quantity > held:
        await ctx.session.send_line(
            f"  Only {held}t of {good.name} in hold. "
            f"Use 'sell cargo {good.key}' to sell all."
        )
        return

    # Planet price
    systems = _get_systems(ship)
    zone_id = systems.get("current_zone", "")
    from engine.npc_space_traffic import ZONES
    zone_obj = ZONES.get(zone_id)
    planet = zone_obj.planet if zone_obj else ""
    base_price = get_planet_price(good, planet)

    # Bargain check
    char = ctx.session.character
    haggle = resolve_bargain_check(
        char, base_price * quantity,
        npc_bargain_dice=3, npc_bargain_pips=0,
        is_buying=False,
    )
    total_revenue = haggle["adjusted_price"]
    per_ton = max(1, total_revenue // quantity)

    # Remove cargo and compute profit
    new_cargo, avg_cost = remove_cargo(cargo, good.key, quantity)
    profit_per_ton = per_ton - avg_cost
    total_profit = profit_per_ton * quantity

    await ctx.db.update_ship(ship["id"], cargo=_j.dumps(new_cargo))

    new_credits = char.get("credits", 0) + total_revenue
    char["credits"] = new_credits
    await ctx.db.save_character(char["id"], credits=new_credits)

    pct = haggle["price_modifier_pct"]
    if pct != 0:
        direction = "bonus" if pct > 0 else "penalty"
        await ctx.session.send_line(
            f"  {ansi.DIM}Bargain: {abs(pct)}% {direction}{ansi.RESET}"
        )

    # Ship's log: trade run if profitable (Drop 19)
    if total_profit >= 0:
        try:
            from engine.ships_log import log_event as _tlog
            await _tlog(ctx.db, char, "trade_runs")
        except Exception:
            pass

    profit_color = ansi.BRIGHT_GREEN if total_profit >= 0 else ansi.BRIGHT_RED
    profit_sign  = "+" if total_profit >= 0 else ""
    await ctx.session.send_line(
        ansi.success(
            f"  Sold {quantity}t of {good.name} for {total_revenue:,}cr "
            f"({per_ton:,}cr/t)."
        )
    )
    await ctx.session.send_line(
        f"  {profit_color}Profit: {profit_sign}{total_profit:,}cr "
        f"(paid {avg_cost:,}/t, sold {per_ton:,}/t){ansi.RESET}"
        f"  Balance: {new_credits:,}cr"
    )


class TradeCommand(BaseCommand):
    key = "trade"
    aliases = ["offer", "+trade"]
    help_text = (
        "Trade credits or items with another player in the same room.\n"
        "\n"
        "USAGE:\n"
        "  trade <player> <amount> credits    — offer credits\n"
        "  trade accept <player>              — accept a pending offer\n"
        "  trade decline <player>             — decline a pending offer\n"
        "  trade cancel                       — cancel your outgoing offer\n"
        "  trade list                         — show pending offers\n"
        "\n"
        "Both parties must be in the same room. The target must 'trade accept'\n"
        "within 2 minutes or the offer expires.\n"
        "\n"
        "EXAMPLES:\n"
        "  trade Tundra 500 credits\n"
        "  trade accept Jex"
    )
    usage = "trade <player> <amount> credits  |  trade accept|decline|cancel|list"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        args = (ctx.args or "").strip()
        parts = args.split()

        if not parts:
            await ctx.session.send_line(
                "  Usage: trade <player> <amount> credits\n"
                "         trade accept|decline|cancel|list"
            )
            return

        sub = parts[0].lower()

        if sub == "list":
            await self._list(ctx, char)
        elif sub == "cancel":
            await self._cancel(ctx, char)
        elif sub == "accept":
            target_name = parts[1] if len(parts) > 1 else ""
            await self._accept(ctx, char, target_name)
        elif sub == "decline":
            target_name = parts[1] if len(parts) > 1 else ""
            await self._decline(ctx, char, target_name)
        else:
            # trade <player> <amount> credits
            await self._offer(ctx, char, parts)

    async def _offer(self, ctx, char, parts):
        _purge_trade_offers()
        # Expect: <player_name> <amount> credits
        if len(parts) < 3:
            await ctx.session.send_line(
                "  Usage: trade <player> <amount> credits\n"
                "  Example: trade Tundra 500 credits"
            )
            return

        target_name = parts[0]
        amount_str = parts[1]
        kind = parts[2].lower() if len(parts) > 2 else ""

        if kind != "credits":
            await ctx.session.send_line(
                "  Only credit trades are supported right now.\n"
                "  Usage: trade <player> <amount> credits"
            )
            return

        try:
            amount = int(amount_str.replace(",", ""))
        except ValueError:
            await ctx.session.send_line(f"  '{amount_str}' isn't a valid amount.")
            return

        if amount <= 0:
            await ctx.session.send_line("  Amount must be positive.")
            return

        if char.get("credits", 0) < amount:
            await ctx.session.send_line(
                f"  You don't have enough credits. "
                f"(You have {char.get('credits', 0):,} cr)"
            )
            return

        # Find target in same room
        target_sess = None
        for s in ctx.session_mgr.sessions_in_room(char["room_id"]):
            if (s.character and
                    s.character["name"].lower().startswith(target_name.lower()) and
                    s.character["id"] != char["id"]):
                target_sess = s
                break

        if not target_sess:
            await ctx.session.send_line(f"  '{target_name}' isn't here.")
            return

        target = target_sess.character
        offer_key = (char["id"], target["id"])

        _pending_trades[offer_key] = {
            "offerer_id":   char["id"],
            "offerer_name": char["name"],
            "target_id":    target["id"],
            "target_name":  target["name"],
            "amount":       amount,
            "kind":         "credits",
            "ts":           _trade_time.time(),
        }

        await ctx.session.send_line(
            f"  \033[1;33mTrade offer sent:\033[0m {amount:,} credits → {target['name']}.\n"
            f"  Waiting for them to 'trade accept {char['name']}'."
        )
        await target_sess.send_line(
            f"\n  \033[1;33m[TRADE OFFER]\033[0m {char['name']} offers you "
            f"\033[1;32m{amount:,} credits\033[0m.\n"
            f"  Type '\033[1;37mtrade accept {char['name']}\033[0m' to accept "
            f"or '\033[1;37mtrade decline {char['name']}\033[0m' to decline. "
            f"(Expires in 2 minutes.)\n"
        )

    async def _accept(self, ctx, char, offerer_name):
        _purge_trade_offers()
        if not offerer_name:
            await ctx.session.send_line("  Usage: trade accept <player name>")
            return

        # Find matching offer
        offer = None
        offer_key = None
        for k, v in _pending_trades.items():
            if (v["target_id"] == char["id"] and
                    v["offerer_name"].lower().startswith(offerer_name.lower())):
                offer = v
                offer_key = k
                break

        if not offer:
            await ctx.session.send_line(
                f"  No pending trade offer from '{offerer_name}'."
            )
            return

        # Find offerer session
        offerer_sess = ctx.session_mgr.find_by_character(offer["offerer_id"])
        if not offerer_sess or not offerer_sess.character:
            _pending_trades.pop(offer_key, None)
            await ctx.session.send_line("  The other player has gone offline. Trade cancelled.")
            return

        # Verify same room
        if offerer_sess.character["room_id"] != char["room_id"]:
            _pending_trades.pop(offer_key, None)
            await ctx.session.send_line(
                "  They've left the room. Trade cancelled."
            )
            return

        offerer = offerer_sess.character
        amount = offer["amount"]

        # Check offerer still has the credits
        if offerer.get("credits", 0) < amount:
            _pending_trades.pop(offer_key, None)
            await ctx.session.send_line(
                f"  {offerer['name']} no longer has enough credits. Trade cancelled."
            )
            await offerer_sess.send_line(
                f"  Trade with {char['name']} cancelled — insufficient credits."
            )
            return

        # Execute transfer
        offerer["credits"] = offerer.get("credits", 0) - amount
        char["credits"] = char.get("credits", 0) + amount

        await ctx.db.save_character(offerer["id"], credits=offerer["credits"])
        await ctx.db.save_character(char["id"], credits=char["credits"])

        _pending_trades.pop(offer_key, None)

        await ctx.session.send_line(
            f"  \033[1;32m[TRADE COMPLETE]\033[0m Received {amount:,} credits "
            f"from {offerer['name']}. Balance: {char['credits']:,} cr."
        )
        await offerer_sess.send_line(
            f"  \033[1;32m[TRADE COMPLETE]\033[0m {char['name']} accepted. "
            f"-{amount:,} credits. Balance: {offerer['credits']:,} cr."
        )

        # Broadcast to room (brief)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {offerer['name']} and {char['name']} exchange credits.",
            exclude=[offerer["id"], char["id"]],
        )

        # Narrative log
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.PURCHASE,
                             f"Received {amount:,} credits from {offerer['name']} via trade",
                             {"amount": amount, "counterpart": offerer["name"]})
            await log_action(ctx.db, offerer["id"], NT.PURCHASE,
                             f"Paid {amount:,} credits to {char['name']} via trade",
                             {"amount": -amount, "counterpart": char["name"]})
        except Exception:
            pass

    async def _decline(self, ctx, char, offerer_name):
        _purge_trade_offers()
        if not offerer_name:
            await ctx.session.send_line("  Usage: trade decline <player name>")
            return

        offer = None
        offer_key = None
        for k, v in _pending_trades.items():
            if (v["target_id"] == char["id"] and
                    v["offerer_name"].lower().startswith(offerer_name.lower())):
                offer = v
                offer_key = k
                break

        if not offer:
            await ctx.session.send_line(f"  No pending offer from '{offerer_name}'.")
            return

        _pending_trades.pop(offer_key, None)
        await ctx.session.send_line(f"  You decline {offer['offerer_name']}'s offer.")

        offerer_sess = ctx.session_mgr.find_by_character(offer["offerer_id"])
        if offerer_sess:
            await offerer_sess.send_line(
                f"  {char['name']} declined your trade offer."
            )

    async def _cancel(self, ctx, char):
        _purge_trade_offers()
        cancelled = []
        for k in list(_pending_trades.keys()):
            if _pending_trades[k]["offerer_id"] == char["id"]:
                target_name = _pending_trades[k]["target_name"]
                target_id = _pending_trades[k]["target_id"]
                cancelled.append((k, target_name, target_id))

        if not cancelled:
            await ctx.session.send_line("  You have no pending trade offers.")
            return

        for k, tname, tid in cancelled:
            _pending_trades.pop(k, None)
            target_sess = ctx.session_mgr.find_by_character(tid)
            if target_sess:
                await target_sess.send_line(
                    f"  {char['name']} cancelled their trade offer to you."
                )

        await ctx.session.send_line(
            f"  Cancelled {len(cancelled)} trade offer(s)."
        )

    async def _list(self, ctx, char):
        _purge_trade_offers()
        incoming = [v for v in _pending_trades.values() if v["target_id"] == char["id"]]
        outgoing = [v for v in _pending_trades.values() if v["offerer_id"] == char["id"]]

        if not incoming and not outgoing:
            await ctx.session.send_line("  No pending trade offers.")
            return

        lines = ["\033[1;36m── Pending Trades ──────────────────\033[0m"]
        for v in incoming:
            age = int(_trade_time.time() - v["ts"])
            lines.append(
                f"  \033[1;33mINBOUND\033[0m  {v['offerer_name']} offers "
                f"{v['amount']:,} credits  \033[2m({age}s ago)\033[0m"
            )
            lines.append(f"           → 'trade accept {v['offerer_name']}'")
        for v in outgoing:
            age = int(_trade_time.time() - v["ts"])
            lines.append(
                f"  \033[2mOUTBOUND\033[0m → {v['target_name']}:  "
                f"{v['amount']:,} credits  \033[2m({age}s ago)\033[0m"
            )
        lines.append("\033[1;36m────────────────────────────────────\033[0m")
        await ctx.session.send_line("\n".join(lines))
