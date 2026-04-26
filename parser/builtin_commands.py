# -*- coding: utf-8 -*-
"""
Built-in commands for Phase 1: navigation, communication, info, and admin.
"""
import logging
import textwrap
from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


def _wrap_exits(exit_parts: list, prefix: str = "  Exits: ", width: int = 120) -> str:
    """Format exits across multiple lines if needed.

    Each 'direction (Label)' pair is atomic — never split across lines.
    Continuation lines indent to align with the first exit.
    Width is measured in visible characters (ANSI codes excluded).
    """
    if not exit_parts:
        return prefix + ansi.DIM + "None" + ansi.RESET

    indent = " " * len(ansi.strip_ansi(prefix))
    lines = []
    current = prefix
    current_vis = len(ansi.strip_ansi(prefix))

    for i, part in enumerate(exit_parts):
        vis = len(ansi.strip_ansi(part))
        if i == 0:
            current += part
            current_vis += vis
        elif current_vis + 2 + vis > width:
            lines.append(current)
            current = indent + part
            current_vis = len(indent) + vis
        else:
            current += ", " + part
            current_vis += 2 + vis

    if current:
        lines.append(current)
    return "\n".join(lines)

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
    _sec = await get_effective_security(room_id, ctx.db, character=char)
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
        """Orchestrator: look at target or display room."""
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("You must be in the game to look around.")
            return

        if ctx.args:
            await self._look_at(ctx)
            return

        room = await ctx.db.get_room(char["room_id"])
        if not room:
            await session.send_line("You are in a void. Something has gone wrong.")
            return

        await self._room_header(ctx, session, char, room)
        await self._room_environment(ctx, session, char)
        await self._room_description(ctx, session, room)
        await self._room_overlays(ctx, session, char, room)
        await self._room_exits(ctx, session, char)
        await self._look_room_contents(ctx, session, char, room)
        await self._sync_space_panel(ctx, session, char)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _room_header(self, ctx, session, char, room):
        """Room name + security/housing/claim tags."""
        _sec_tag = ""
        try:
            from engine.security import get_effective_security, security_label
            _room_sec = await get_effective_security(char["room_id"], ctx.db, character=char)
            _sec_tag = " " + security_label(_room_sec)
        except Exception:
            log.warning("_room_header: security tag failed", exc_info=True)

        _housing_tag = ""
        try:
            from engine.housing import get_room_housing_display
            _hdisp = await get_room_housing_display(ctx.db, char["room_id"])
            if _hdisp:
                _housing_tag = f" \033[2m[PRIVATE — {_hdisp['owner_name']}]\033[0m"
        except Exception:
            log.warning("_room_header: housing tag failed", exc_info=True)

        _claim_tag = ""
        try:
            from engine.territory import get_claim_display_tag
            _ct = await get_claim_display_tag(ctx.db, char["room_id"])
            if _ct:
                _claim_tag = _ct
        except Exception:
            log.warning("_room_header: claim tag failed", exc_info=True)

        await session.send_line(
            ansi.room_name(room["name"]) + _sec_tag + _housing_tag + _claim_tag)

    async def _room_environment(self, ctx, session, char):
        """Environment flavor line (lighting, cover)."""
        props = await ctx.db.get_all_room_properties(char["room_id"])
        flavor_parts = []
        lighting = props.get("lighting", "")
        if lighting and lighting != "bright":
            flavor_parts.append(f"The lighting is {lighting}.")
        cover_max = props.get("cover_max", 0)
        if cover_max >= 3:
            flavor_parts.append("Heavy cover available.")
        elif cover_max == 2:
            flavor_parts.append("Moderate cover available.")
        elif cover_max == 1:
            flavor_parts.append("Minimal cover here.")

        if flavor_parts:
            await session.send_line(
                f"  {ansi.DIM}{' '.join(flavor_parts)}{ansi.RESET}")

    async def _room_description(self, ctx, session, room):
        """Room description text."""
        desc = room["desc_long"] or room["desc_short"] or "You see nothing special."
        await session.send_prose(desc, indent="  ")

    async def _room_overlays(self, ctx, session, char, room):
        """Dynamic overlays: state descriptions, trophies, territory influence."""
        # Room state overlays
        try:
            from engine.room_states import get_state_descriptions
            _state_lines = get_state_descriptions(room)
            for _sl in _state_lines:
                await session.send_line(f"\n  \033[2;3m{_sl}\033[0m")
        except Exception:
            pass  # Non-critical

        # Trophy display for player-owned rooms
        try:
            from engine.housing import get_room_housing_display
            _hd2 = await get_room_housing_display(ctx.db, char["room_id"])
            if _hd2 and _hd2["trophies"]:
                await session.send_line(
                    f"  \033[2m[Mounted on the wall]\033[0m")
                for _trophy in _hd2["trophies"]:
                    _tname = _trophy.get("name") or _trophy.get("key") or "Item"
                    _tqual = f"  (Q{_trophy['quality']})" if _trophy.get("quality") else ""
                    await session.send_line(
                        f"   \033[1;33m◆\033[0m {_tname}{_tqual}")
        except Exception:
            log.warning("_room_overlays: trophy display failed", exc_info=True)

        # Territory influence presence
        try:
            from engine.territory import get_zone_influence_line, get_room_zone_id
            _tz_id = await get_room_zone_id(ctx.db, char["room_id"])
            if _tz_id is not None:
                _tz_line = await get_zone_influence_line(ctx.db, _tz_id)
                if _tz_line:
                    await session.send_line(_tz_line)
        except Exception:
            log.warning("_room_overlays: territory influence failed", exc_info=True)

    async def _room_exits(self, ctx, session, char):
        """Display exits with locks and labels."""
        exits = await ctx.db.get_exits(char["room_id"])
        if not exits:
            return

        # Filter hidden exits
        try:
            from engine.housing import is_exit_visible
            visible_exits = []
            for e in exits:
                if await is_exit_visible(ctx.db, e, char):
                    visible_exits.append(e)
            exits = visible_exits
        except Exception:
            pass  # Graceful fallback: show all exits

        exit_parts = []
        seen_dirs = {}
        for e in exits:
            dir_key = e["direction"]
            label = (e.get("name") or "").strip()
            if not label:
                try:
                    dest = await ctx.db.get_room(e["to_room_id"])
                    if dest:
                        label = dest["name"]
                except Exception:
                    log.warning("_room_exits: dest room lookup failed", exc_info=True)
            seen_dirs.setdefault(dir_key, []).append((label, e))

        for dir_key, entries in seen_dirs.items():
            for label, e in entries:
                lock = e.get("lock_data", "")
                locked = lock and lock not in ("{}", "", "open")
                if label and label.lower() != dir_key.lower():
                    display = f"{ansi.exit_color(dir_key)} ({label})"
                else:
                    display = ansi.exit_color(dir_key)
                if locked:
                    display += f"{ansi.DIM}[locked]{ansi.RESET}"
                exit_parts.append(display)

        await session.send_line(_wrap_exits(exit_parts))

    async def _sync_space_panel(self, ctx, session, char):
        """Sync web client space panel state on every look."""
        try:
            if session.protocol.value == "websocket":
                from parser.space_commands import build_space_state, broadcast_space_state
                ship = await ctx.db.get_ship_by_bridge(char["room_id"])
                if ship and not ship.get("docked_at"):
                    payload = await build_space_state(ship, char["id"], ctx.db, ctx.session_mgr)
                    await session.send_json("space_state", payload)
                elif ship and ship.get("docked_at"):
                    await session.send_json("space_state", {
                        "active": False,
                        "ship_name": ship.get("name", ""),
                    })
                else:
                    await session.send_json("space_state", {"active": False})
                await session.send_hud_update(db=ctx.db, session_mgr=ctx.session_mgr)
        except Exception as e:
            log.warning("LookCommand space_state sync failed: %s", e)

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
            # Check room_details in room properties before giving up
            room = await ctx.db.get_room(char["room_id"])
            if room:
                try:
                    props = _json.loads(room.get("properties", "{}") or "{}")
                    details = props.get("room_details", {})
                    # Find matching detail by keyword (partial match ok)
                    search_lower = ctx.args.lower().strip()
                    found_detail = None
                    for kw, detail in details.items():
                        if search_lower == kw.lower() or kw.lower() in search_lower or search_lower in kw.lower():
                            found_detail = detail
                            break
                    if found_detail:
                        # Show the detail description
                        desc = found_detail.get("desc", "You see nothing special.")
                        await ctx.session.send_line(f"  {desc}")
                        # Grant item if present and not already granted this session
                        grants = found_detail.get("grants_item")
                        if grants:
                            if not char.get(f"_found_{grants}", False):
                                # Grant item to inventory
                                item_name = found_detail.get("item_name", grants)
                                item_slot = found_detail.get("item_slot", "misc")
                                await ctx.db.add_to_inventory(char["id"], {
                                    "key": grants,
                                    "name": item_name,
                                    "slot": item_slot,
                                })
                                await ctx.session.send_line(
                                    f"  {ansi.color(f'You pick up the {item_name}.', ansi.YELLOW)}"
                                )
                                # Mark as found so it's not granted again this session
                                char[f"_found_{grants}"] = True
                                # Tutorial hook if applicable
                                try:
                                    from engine.tutorial_v2 import check_profession_chains
                                    await check_profession_chains(
                                        ctx.session, ctx.db, "find_item",
                                        item_key=grants,
                                    )
                                except Exception as _e:
                                    log.debug("silent except in parser/builtin_commands.py:461: %s", _e, exc_info=True)
                        return
                except Exception:
                    log.warning("_look_at: room_details lookup failed", exc_info=True)
            await ctx.session.send_line(f"  You don't see '{ctx.args}' here.")
            return

        c = match.candidate
        if c.obj_type == "npc":
            # NPC description
            await ctx.session.send_line(f"  {ansi.npc_name(c.name)}")
            desc = c.data.get("description", "")
            if desc:
                await ctx.session.send_prose(desc, indent="    ")
            species = c.data.get("species", "Unknown")
            await ctx.session.send_line(f"    Species: {species}")

        elif c.obj_type == "character":
            # Character description
            await ctx.session.send_line(f"  {ansi.player_name(c.name)}")
            desc = c.data.get("description", "")
            if desc:
                await ctx.session.send_prose(desc, indent="    ")
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
                log.warning("_look_at: unhandled exception", exc_info=True)
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

    async def _look_room_contents(self, ctx, session, char, room):
        """Render characters, NPCs, and vendor droids in the room."""
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
                log.warning("execute: unhandled exception", exc_info=True)
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

        # Vendor droids in the room (player shops)
        try:
            from engine.vendor_droids import _load_data
            v_droids = await ctx.db.get_objects_in_room(char["room_id"], "vendor_droid")
            for vd in v_droids:
                vd_data  = _load_data(vd)
                shop_name = vd_data.get("shop_name", vd["name"])
                item_count = len(vd_data.get("inventory", []))
                await session.send_line(
                    f"  \033[1;36m[SHOP]\033[0m \033[1;37m{shop_name}\033[0m "
                    f"\033[2m({item_count} item{'s' if item_count != 1 else ''} — "
                    f"browse {shop_name})\033[0m"
                )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass




class MoveCommand(BaseCommand):
    key = "move"
    aliases = ["repair"]
    help_text = "Move in a direction."
    usage = "north/south/east/west/up/down (or abbreviations)"

    async def execute(self, ctx: CommandContext):
        """Orchestrator: match exit → check gates → move → auto-look → hooks."""
        session = ctx.session
        char = session.character
        if not char:
            return

        direction = ctx.args.lower().strip()
        if not direction:
            await session.send_line("Move where? Specify a direction.")
            return

        exit_data = await self._match_exit(ctx, char, direction)
        if not exit_data:
            await session.send_line(f"You can't go {direction}.")
            return

        blocked = await self._check_exit_gates(ctx, session, char, exit_data, direction)
        if blocked:
            return

        old_room_id = char["room_id"]
        new_room_id = exit_data["to_room_id"]

        # Auto-depart from places table (MUX compat)
        try:
            from parser.places_commands import auto_depart_place
            await auto_depart_place(ctx.db, char["id"], old_room_id, ctx.session_mgr)
        except Exception:
            pass  # Graceful

        lock_d = self._parse_lock_data(exit_data)

        await self._broadcast_departure(ctx, session, char, old_room_id, direction, lock_d)
        await self._fire_room_hook(ctx, session, char, old_room_id, "ALEAVE")

        char["room_id"] = new_room_id
        await ctx.db.save_character(char["id"], room_id=new_room_id)

        await self._broadcast_arrival(ctx, session, char, new_room_id, lock_d)
        await self._fire_room_hook(ctx, session, char, new_room_id, "AENTER")

        # Auto-look
        look_cmd = LookCommand()
        look_ctx = CommandContext(
            session=session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr,
        )
        await look_cmd.execute(look_ctx)

        await self._post_move_hooks(ctx, session, char, new_room_id)

    # ── Helpers ────────────────────────────────────────────────────────────

    async def _match_exit(self, ctx, char, direction):
        """Match direction input to an exit. Returns exit dict or None."""
        exits = await ctx.db.get_exits(char["room_id"])

        # Filter hidden exits
        try:
            from engine.housing import is_exit_visible
            exits = [e for e in exits if await is_exit_visible(ctx.db, e, char)]
        except Exception:
            pass  # Graceful fallback: allow all exits

        # Priority: exact → prefix → name partial → legacy direction contains
        matching = [e for e in exits if e["direction"].lower() == direction]
        if not matching:
            matching = [e for e in exits if e["direction"].lower().startswith(direction)]
        if not matching:
            matching = [
                e for e in exits
                if e.get("name") and direction in e["name"].lower()
            ]
        if not matching:
            matching = [e for e in exits if direction in e["direction"].lower()]

        return matching[0] if matching else None

    async def _check_exit_gates(self, ctx, session, char, exit_data, direction):
        """Check lock, housing, and org HQ gates. Returns True if blocked."""
        # Exit lock
        lock_str = exit_data.get("lock_data", "{}")
        if lock_str and lock_str not in ("{}", "", "open"):
            from engine.locks import eval_lock
            account = await ctx.db.get_account(char.get("account_id", 0))
            lock_ctx = {}
            if account:
                lock_ctx["is_admin"] = bool(account.get("is_admin"))
                lock_ctx["is_builder"] = bool(account.get("is_builder"))
            passed, reason = eval_lock(lock_str, char, lock_ctx)
            if not passed:
                await session.send_line(f"  The way {direction} is locked. ({reason})")
                return True

        new_room_id = exit_data["to_room_id"]

        # Housing private room gate
        try:
            from engine.housing import can_enter_housing_room
            _allowed, _reason = await can_enter_housing_room(ctx.db, char, new_room_id)
            if not _allowed:
                await session.send_line(
                    f"  [1;33m{_reason}[0m\n"
                    "  Use [1;37mlockpick[0m to attempt entry.")
                return True
        except Exception:
            pass  # Graceful fallback

        # Org HQ room gate
        try:
            from engine.housing import can_enter_hq_room
            _allowed, _reason = await can_enter_hq_room(ctx.db, char, new_room_id)
            if not _allowed:
                await session.send_line(f"  [1;33m{_reason}[0m")
                return True
        except Exception:
            pass  # Graceful fallback

        return False

    def _parse_lock_data(self, exit_data):
        """Parse exit lock_data for @osucc/@odrop messages."""
        import json as _emj
        _lock_d = {}
        try:
            _lock_raw = exit_data.get("lock_data", "{}")
            if isinstance(_lock_raw, str) and _lock_raw.strip():
                _lock_d = _emj.loads(_lock_raw)
            elif isinstance(_lock_raw, dict):
                _lock_d = _lock_raw
        except Exception:
            _lock_d = {}
        return _lock_d

    async def _broadcast_departure(self, ctx, session, char, old_room_id, direction, lock_d):
        """Broadcast departure message to the old room."""
        _osucc = (lock_d.get("osucc_msg") or "").strip()
        if _osucc:
            _osucc = _osucc.replace("%N", char["name"])
            await ctx.session_mgr.broadcast_to_room(
                old_room_id, f"  {_osucc}", exclude=session)
        else:
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"{ansi.player_name(char['name'])} leaves {direction}.",
                exclude=session)

    async def _broadcast_arrival(self, ctx, session, char, new_room_id, lock_d):
        """Broadcast arrival message to the new room."""
        _odrop = (lock_d.get("odrop_msg") or "").strip()
        if _odrop:
            _odrop = _odrop.replace("%N", char["name"])
            await ctx.session_mgr.broadcast_to_room(
                new_room_id, f"  {_odrop}", exclude=session)
        else:
            await ctx.session_mgr.broadcast_to_room(
                new_room_id,
                f"{ansi.player_name(char['name'])} arrives.",
                exclude=session)

    async def _fire_room_hook(self, ctx, session, char, room_id, hook_name):
        """Fire ALEAVE/AENTER room hook."""
        try:
            from parser.attr_commands import fire_room_hook
            await fire_room_hook(ctx.db, ctx.session_mgr, room_id, hook_name,
                                 char=char, session=session)
        except Exception as _e:
            log.debug("_fire_room_hook %s: %s", hook_name, _e, exc_info=True)


    async def _post_move_hooks(self, ctx, session, char, new_room_id):
        """Post-move effects: lawless warning, hostile NPCs, achievements, barks, tutorial."""
        # ── Lawless zone entry warning (one-time per session) ────────────
        try:
            from engine.security import get_effective_security, SecurityLevel
            _move_sec = await get_effective_security(new_room_id, ctx.db, character=char)
            if _move_sec == SecurityLevel.LAWLESS:
                if not getattr(session, "_lawless_warned", False):
                    session._lawless_warned = True
                    await session.send_line(
                        "\n  \033[1;31m*** WARNING: You are entering LAWLESS territory. ***\033[0m\n"
                        "  \033[1;31m*** Players and NPCs can attack you freely here. ***\033[0m\n"
                        "  \033[2mHigher risk, higher rewards. Watch your back.\033[0m\n"
                    )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        # Check for hostile NPCs in the new room
        await _check_hostile_npcs(ctx, new_room_id)

        # Achievement: room visit tracking
        try:
            import json as _rvj
            _attrs = char.get("attributes", "{}")
            if isinstance(_attrs, str):
                _attrs = _rvj.loads(_attrs) if _attrs else {}
            _visited = set(_attrs.get("rooms_visited", []))
            if new_room_id not in _visited:
                _visited.add(new_room_id)
                _attrs["rooms_visited"] = list(_visited)
                char["attributes"] = _rvj.dumps(_attrs)
                await ctx.db.save_character(char["id"], attributes=char["attributes"])
                if hasattr(ctx.session, "game_server"):
                    from engine.achievements import on_room_visited
                    await on_room_visited(ctx.db, char["id"],
                                          len(_visited), session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/builtin_commands.py:718: %s", _e, exc_info=True)

        # Idle queue: show ambient NPC bark on room entry
        try:
            _iq = getattr(ctx.session_mgr, '_idle_queue', None)
            if _iq:
                from engine.idle_queue import get_random_bark, needs_bark_refresh
                npcs = await ctx.db.get_npcs_in_room(new_room_id)
                for _npc in npcs:
                    _nid = _npc.get("id", 0)
                    if not _nid:
                        continue
                    _ai_cfg = _npc.get("ai_config_json", "{}")
                    if isinstance(_ai_cfg, str):
                        try:
                            import json as _bj
                            _ai_cfg = _bj.loads(_ai_cfg)
                        except Exception:
                            _ai_cfg = {}
                    if _ai_cfg.get("hostile", False):
                        continue
                    if not _ai_cfg.get("personality", ""):
                        continue
                    bark = get_random_bark(_nid, char["id"], _npc.get("name", ""))
                    if bark:
                        await session.send_json("ambient_bark", {
                            "npc_name": bark["npc_name"],
                            "bark": bark["bark"],
                            "text": bark["text"],
                        })
                        break  # Max 1 bark per room entry
                    # Queue bark generation if stale
                    if needs_bark_refresh(_nid):
                        _zone_tone = ""
                        try:
                            from engine.zone_tones import get_zone_tone
                            _zone_tone = await get_zone_tone(ctx.db, new_room_id)
                        except Exception as _e:
                            log.debug("silent except in parser/builtin_commands.py:756: %s", _e, exc_info=True)
                        _new_room = await ctx.db.get_room(new_room_id)
                        _rname = _new_room.get("name", "") if _new_room else ""
                        _iq.enqueue_bark(
                            npc_id=_nid,
                            npc_name=_npc.get("name", ""),
                            species=_npc.get("species", "alien"),
                            personality=_ai_cfg.get("personality", ""),
                            faction=_ai_cfg.get("faction", ""),
                            room_name=_rname,
                            zone_tone=_zone_tone,
                        )
        except Exception:
            pass  # Non-critical — barks are pure flavor

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
                # Spacer quest room-entry check
                try:
                    from engine.spacer_quest import check_spacer_quest
                    await check_spacer_quest(
                        session, ctx.db, "room_enter",
                        room_id=new_room_id,
                        room_name=new_room.get("name", ""),
                    )
                except Exception as _e:
                    log.debug("silent except in parser/builtin_commands.py:838: %s", _e, exc_info=True)
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

        room_id = char["room_id"]
        full_text = f'{char["name"]} says, "{ctx.args}"'
        await ctx.session.send_line(f'You say, "{ctx.args}"')
        await ctx.session_mgr.broadcast_to_room(
            room_id,
            full_text,
            exclude=ctx.session,
        )
        # Chat tag for WebSocket comms panel
        await ctx.session_mgr.broadcast_chat(
            "ic", char["name"], ctx.args,
            room_id=room_id,
        )
        # Scene logging hook
        from engine.scenes import get_active_scene_id, capture_pose
        scene_id = get_active_scene_id(room_id)
        if scene_id is not None:
            await capture_pose(ctx.db, scene_id, char["id"],
                               char["name"], full_text, pose_type="say",
                               session_mgr=ctx.session_mgr)
        # Eavesdrop relay — let listeners in adjacent rooms overhear
        try:
            from parser.espionage_commands import relay_to_eavesdroppers
            await relay_to_eavesdroppers(ctx.session_mgr, room_id, char["name"], ctx.args)
        except Exception as _e:
            log.debug("silent except in parser/builtin_commands.py:888: %s", _e, exc_info=True)
        # Achievement: pc_conversation (2+ PCs in room)
        try:
            others = [s for s in ctx.session_mgr.sessions_in_room(room_id) or []
                      if s.character and s.character.get("id") != char["id"]]
            if others:
                from engine.achievements import on_pc_conversation
                await on_pc_conversation(ctx.db, char["id"], session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/builtin_commands.py:897: %s", _e, exc_info=True)


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

        # Scene logging hook
        from engine.scenes import get_active_scene_id, capture_pose
        scene_id = get_active_scene_id(room_id)
        if scene_id is not None:
            await capture_pose(ctx.db, scene_id, char["id"],
                               char["name"], text, pose_type="pose",
                               session_mgr=ctx.session_mgr)


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
        import json as _json
        char = ctx.session.character
        if not char:
            return

        await ctx.session.send_line(ansi.header("=== Inventory ==="))

        # ── Equipped items from equipment JSON ───────────────────────────────
        eq = {}
        try:
            eq = _json.loads(char.get("equipment", "{}") or "{}")
        except Exception as _e:
            log.debug("silent except in parser/builtin_commands.py:1032: %s", _e, exc_info=True)
        weapon_key  = eq.get("weapon", "")
        armor_key   = eq.get("armor", "")

        if weapon_key or armor_key:
            await ctx.session.send_line(f"  {ansi.BOLD}Equipped:{ansi.RESET}")
            if weapon_key:
                try:
                    from engine.weapons import get_weapon_registry
                    w = get_weapon_registry().get(weapon_key)
                    wname = w.name if w else weapon_key
                    wdmg  = f"  dmg {w.damage}" if w else ""
                    await ctx.session.send_line(
                        f"    {ansi.color('⚔', ansi.YELLOW)}  {wname}{ansi.DIM}{wdmg}{ansi.RESET}"
                    )
                except Exception:
                    await ctx.session.send_line(f"    ⚔  {weapon_key}")
            if armor_key:
                try:
                    from engine.weapons import get_weapon_registry
                    a = get_weapon_registry().get(armor_key)
                    aname = a.name if a else armor_key
                    await ctx.session.send_line(
                        f"    {ansi.color('🛡', ansi.CYAN)}  {aname}{ansi.RESET}"
                    )
                except Exception:
                    await ctx.session.send_line(f"    🛡  {armor_key}")
            await ctx.session.send_line("")

        # ── Carried inventory ─────────────────────────────────────────────────
        inv = []
        try:
            inv = await ctx.db.get_inventory(char["id"])
        except Exception:
            log.warning("InventoryCommand: get_inventory failed", exc_info=True)

        if inv:
            await ctx.session.send_line(f"  {ansi.BOLD}Carried:{ansi.RESET}")
            for item in inv:
                name = item.get("name") or item.get("key") or "Unknown item"
                qty  = item.get("qty", item.get("quantity", 1))
                qty_str = f" x{qty}" if qty and int(qty) > 1 else ""
                slot = item.get("slot", "")
                slot_str = f"  [{slot}]" if slot and slot != "misc" else ""
                await ctx.session.send_line(
                    f"    {ansi.color('◆', ansi.DIM)}  {name}{qty_str}"
                    f"{ansi.DIM}{slot_str}{ansi.RESET}"
                )
        elif not weapon_key and not armor_key:
            await ctx.session.send_line("  You're not carrying anything.")

        # ── Credits ──────────────────────────────────────────────────────────
        credits = char.get("credits", 0)
        await ctx.session.send_line("")
        await ctx.session.send_line(
            f"  {ansi.BOLD}Credits:{ansi.RESET} {ansi.color(f'{credits:,} cr', ansi.YELLOW)}"
        )
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
        w = min(ctx.session.wrap_width, 100)
        if "brief" in ctx.switches:
            from engine.sheet_renderer import render_brief_sheet
            lines = render_brief_sheet(char, skill_reg, width=w)
        elif "skills" in ctx.switches:
            from engine.sheet_renderer import render_skills_sheet
            lines = render_skills_sheet(char, skill_reg, width=w)
        elif "combat" in ctx.switches:
            from engine.sheet_renderer import render_combat_sheet
            lines = render_combat_sheet(char, skill_reg, width=w)
        else:
            from engine.sheet_renderer import render_game_sheet
            lines = render_game_sheet(char, skill_reg, width=w)

        # WebSocket clients render the sheet from the structured sidebar
        # HUD payload (attributes, force_skills, wound, FP, CP, credits,
        # equipment). Dumping the rendered text into the pose log here
        # caused the visible "sheet bleed" — wound-track ASCII, weapon
        # lines, and skill rows being misclassified into the comms feed.
        # On WebSocket: trigger an immediate hud refresh and stay quiet
        # in the chat stream. Telnet still gets the full formatted text.
        from server.session import Protocol
        if ctx.session.protocol == Protocol.WEBSOCKET:
            try:
                await ctx.session.send_hud_update(
                    db=ctx.db, session_mgr=ctx.session_mgr
                )
            except Exception:
                # Fall back to text dump if HUD push fails for any reason
                for line in lines:
                    await ctx.session.send_line(line)
            # For /skills and /combat there's no sidebar equivalent yet —
            # send those text variants regardless so the user gets info.
            if "skills" in ctx.switches or "combat" in ctx.switches:
                for line in lines:
                    await ctx.session.send_line(line)
            return

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
        w = ctx.session.wrap_width
        bar = "═" * w
        await ctx.session.send_line("")
        await ctx.session.send_line(ansi.header(bar))
        await ctx.session.send_line(
            ansi.header("  STAR WARS D6 MUSH — Command Reference"))
        await ctx.session.send_line(ansi.header(bar))
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

        # S47: Summary block — only when it adds info beyond body's first line.
        # Auto-derived summaries that mirror the body opener are suppressed
        # to avoid printing the same sentence twice.
        summary = (getattr(entry, "summary", "") or "").strip()
        if summary:
            body_first_line = (entry.body or "").split("\n", 1)[0].strip()
            if not body_first_line.startswith(summary):
                await send(f"  {ansi.DIM}{summary}{ansi.RESET}")
                await send("")

        # Body text — send line by line
        for line in entry.body.split("\n"):
            await send(f"  {line}")

        # S47: Examples block — appears after body, before see-also.
        # Each example is {"cmd": "...", "description": "..."}; rows
        # missing `cmd` are silently dropped, descriptions may be empty.
        examples = getattr(entry, "examples", None) or []
        valid_examples = [ex for ex in examples
                          if isinstance(ex, dict) and (ex.get("cmd") or "").strip()]
        if valid_examples:
            await send("")
            await send(f"  {ansi.DIM}EXAMPLES:{ansi.RESET}")
            for ex in valid_examples:
                cmd = ex.get("cmd", "").strip()
                desc = (ex.get("description") or "").strip()
                if desc:
                    await send(f"    {ansi.BRIGHT_CYAN}{cmd}{ansi.RESET}"
                               f"  {ansi.DIM}—{ansi.RESET} {desc}")
                else:
                    await send(f"    {ansi.BRIGHT_CYAN}{cmd}{ansi.RESET}")

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

            # Flag as sleeping if in a non-safe room (Tier 3 Feature #16)
            if room_id:
                try:
                    from engine.sleeping import set_sleeping
                    sleeping = await set_sleeping(
                        ctx.session.character, ctx.db, room_id)
                    if sleeping:
                        await ctx.session_mgr.broadcast_to_room(
                            room_id,
                            ansi.system_msg(
                                f"{name} falls asleep here."),
                            exclude=ctx.session,
                        )
                except Exception:
                    log.warning("QuitCommand: sleeping flag failed", exc_info=True)

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

        # Scene logging hook — captured as OOC, excluded from log render
        from engine.scenes import get_active_scene_id, capture_pose
        scene_id = get_active_scene_id(room_id)
        if scene_id is not None:
            await capture_pose(ctx.db, scene_id, char["id"],
                               char["name"], f"[OOC] {name}: {ctx.args}",
                               pose_type="ooc", is_ooc=True,
                               session_mgr=ctx.session_mgr)


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

        if len(ctx.args) > 2000:
            await ctx.session.send_line("  Description too long (2000 char max).")
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


class WearCommand(BaseCommand):
    """v22: Wear armor. Armor adds to Strength for soak per R&E p83."""
    key = "wear"
    aliases = ["don"]
    help_text = "Wear armor. Use 'armor' to see available armor. Armor adds to soak in combat."
    usage = "wear <armor name>"

    async def execute(self, ctx: CommandContext):
        from engine.weapons import get_weapon_registry
        import json as _json

        if not ctx.args:
            # Show currently worn armor
            char = ctx.session.character
            try:
                equip = _json.loads(char.get("equipment", "{}")) if isinstance(
                    char.get("equipment"), str) else char.get("equipment", {})
            except Exception:
                equip = {}
            armor_key = equip.get("armor", "")
            if armor_key:
                wr = get_weapon_registry()
                a = wr.get(armor_key)
                aname = a.name if a else armor_key
                prot_e = a.protection_energy if a else "?"
                prot_p = a.protection_physical if a else "?"
                dex_pen = a.dexterity_penalty if a and a.dexterity_penalty else "none"
                await ctx.session.send_line(
                    f"  Wearing: {aname}\n"
                    f"  Energy protection: {prot_e}  |  Physical: {prot_p}\n"
                    f"  Dexterity penalty: {dex_pen}")
            else:
                await ctx.session.send_line("  No armor worn. Type 'armor' to see available armor.")
            return

        wr = get_weapon_registry()
        armor = wr.find_by_name(ctx.args.strip())
        if not armor:
            await ctx.session.send_line(f"  Unknown armor '{ctx.args}'. Type 'armor' to see options.")
            return
        if not armor.is_armor:
            await ctx.session.send_line(f"  {armor.name} is a weapon, not armor. Use 'equip' instead.")
            return

        # Update equipment JSON, preserving weapon
        char = ctx.session.character
        try:
            equip = _json.loads(char.get("equipment", "{}")) if isinstance(
                char.get("equipment"), str) else char.get("equipment", {})
        except Exception:
            equip = {}
        equip["armor"] = armor.key
        char["equipment"] = _json.dumps(equip)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])

        dex_note = ""
        if armor.dexterity_penalty:
            dex_note = f" ({armor.dexterity_penalty} Dexterity penalty)"
        await ctx.session.send_line(
            ansi.success(
                f"  You put on {armor.name}. "
                f"(Energy: {armor.protection_energy}, Physical: {armor.protection_physical})"
                f"{dex_note}"
            )
        )


class RemoveArmorCommand(BaseCommand):
    """v22: Remove worn armor."""
    key = "remove"
    aliases = ["doff"]
    help_text = "Remove your worn armor."
    usage = "remove armor"

    async def execute(self, ctx: CommandContext):
        from engine.weapons import get_weapon_registry
        import json as _json

        # Only handle "remove armor" — other remove targets can be added later
        if not ctx.args or ctx.args.strip().lower() != "armor":
            await ctx.session.send_line("  Usage: remove armor")
            return

        char = ctx.session.character
        try:
            equip = _json.loads(char.get("equipment", "{}")) if isinstance(
                char.get("equipment"), str) else char.get("equipment", {})
        except Exception:
            equip = {}

        armor_key = equip.get("armor", "")
        if not armor_key:
            await ctx.session.send_line("  You're not wearing any armor.")
            return

        wr = get_weapon_registry()
        a = wr.get(armor_key)
        aname = a.name if a else armor_key

        del equip["armor"]
        char["equipment"] = _json.dumps(equip)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        await ctx.session.send_line(ansi.success(f"  You remove your {aname}."))


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
        # Route 'sell <resource> to <shop>' to vendor droid buy-order system
        if ctx.args:
            arg_lower = ctx.args.strip().lower()
            if " to " in arg_lower:
                idx = arg_lower.index(" to ")
                resource_part = ctx.args.strip()[:idx].strip()
                shop_part     = ctx.args.strip()[idx + 4:].strip()
                if shop_part:
                    return await _handle_sell_to_droid(ctx, resource_part, shop_part)
            # Route 'sell cargo' to trade handler
            if arg_lower.startswith("cargo"):
                return await _handle_sell_cargo(ctx)

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
            log.warning("execute: unhandled exception", exc_info=True)
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
            log.warning("execute: unhandled exception", exc_info=True)
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




class ArmorListCommand(BaseCommand):
    """v22: List available armor."""
    key = "+armor"
    aliases = ["armor", "armorlist"]
    help_text = "List all armor in the game. Use 'wear <name>' to put armor on."
    usage = "armor"

    async def execute(self, ctx: CommandContext):
        from engine.weapons import get_weapon_registry
        import json as _json
        wr = get_weapon_registry()

        await ctx.session.send_line(
            f"  {'Armor':<28s} {'Energy':>8s} {'Physical':>10s} {'DEX Pen':>8s} {'Cost':>8s}")
        await ctx.session.send_line(
            f"  {'-'*28} {'-'*8} {'-'*10} {'-'*8} {'-'*8}")
        for a in wr.all_armor():
            dex = a.dexterity_penalty if a.dexterity_penalty else "--"
            cost_str = f"{a.cost:,}cr" if a.cost else "--"
            await ctx.session.send_line(
                f"  {a.name:<28s} {a.protection_energy:>8s} "
                f"{a.protection_physical:>10s} {dex:>8s} {cost_str:>8s}")

        # Show currently worn
        char = ctx.session.character
        try:
            equip = _json.loads(char.get("equipment", "{}")) if isinstance(
                char.get("equipment"), str) else char.get("equipment", {})
        except Exception:
            equip = {}
        armor_key = equip.get("armor", "")
        if armor_key:
            a = wr.get(armor_key)
            aname = a.name if a else armor_key
            await ctx.session.send_line(
                f"\n  Wearing: {ansi.BRIGHT_WHITE}{aname}{ansi.RESET}")


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




class PicklockCommand(BaseCommand):
    """
    lockpick  — Attempt to pick the lock on a private housing door.
    Uses Security skill. Difficulty varies by zone security level.
    Drop 7: Housing Security & Intrusion.
    """
    key = "lockpick"
    aliases = ["pick"]
    help_text = (
        "Attempt to pick the lock on a private housing room door.\n"
        "\n"
        "USAGE:\n"
        "  lockpick  — attempt to pick the lock on the door you just tried to enter\n"
        "\n"
        "Difficulties:\n"
        "  Contested zone: Very Difficult (25)\n"
        "  Lawless zone:   Difficult (20)\n"
        "  Secured zone:   Impossible (Imperial security seals)\n"
        "\n"
        "Failed attempts may alert the owner. A critical failure jams the lock."
    )
    usage = "lockpick"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            return
        # Target: the private housing room reachable from current room
        room_id = char.get("room_id")
        exits = await ctx.db.get_exits(room_id)
        # Find the first adjacent private housing room
        target_room_id = None
        for e in exits:
            from engine.housing import get_housing_for_private_room
            h_check = await get_housing_for_private_room(ctx.db, e["to_room_id"])
            if h_check:
                target_room_id = e["to_room_id"]
                break

        if not target_room_id:
            await ctx.session.send_line(
                "  There's no locked housing door here to pick."
            )
            return

        from engine.housing import attempt_lockpick, can_enter_housing_room
        result = await attempt_lockpick(
            ctx.db, char, target_room_id, ctx.session_mgr
        )
        await ctx.session.send_line(result["msg"])

        if result.get("entered"):
            # Move the character into the room
            old_room_id = char["room_id"]
            char["room_id"] = target_room_id
            await ctx.db.save_character(char["id"], room_id=target_room_id)
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"  {char['name']} slips through a door.",
                exclude=ctx.session,
            )
            await ctx.session_mgr.broadcast_to_room(
                target_room_id,
                f"  {char['name']} enters.",
                exclude=ctx.session,
            )
            # Auto-look
            look_cmd = LookCommand()
            look_ctx = CommandContext(
                session=ctx.session, raw_input="look",
                command="look", args="",
                db=ctx.db, session_mgr=ctx.session_mgr,
            )
            await look_cmd.execute(look_ctx)


class ForceDoorCommand(BaseCommand):
    """
    forcedoor  — Attempt to force a housing door open with brute Strength.
    Only works in lawless zones. Loud — always alerts owner.
    Drop 7: Housing Security & Intrusion.
    """
    key = "forcedoor"
    aliases = ["breakin", "force door"]
    help_text = (
        "Force a housing door open with brute strength.\n"
        "Only possible in lawless zones. Always alerts the owner.\n"
        "Difficulty: Moderate Strength (15)."
    )
    usage = "forcedoor"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            return
        room_id = char.get("room_id")
        exits = await ctx.db.get_exits(room_id)
        target_room_id = None
        for e in exits:
            from engine.housing import get_housing_for_private_room
            h_check = await get_housing_for_private_room(ctx.db, e["to_room_id"])
            if h_check:
                target_room_id = e["to_room_id"]
                break

        if not target_room_id:
            await ctx.session.send_line("  There's no housing door here to force.")
            return

        from engine.housing import attempt_force_door
        result = await attempt_force_door(
            ctx.db, char, target_room_id, ctx.session_mgr
        )
        await ctx.session.send_line(result["msg"])

        if result.get("entered"):
            old_room_id = char["room_id"]
            char["room_id"] = target_room_id
            await ctx.db.save_character(char["id"], room_id=target_room_id)
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"  [1;31m{char['name']} smashes through a door![0m",
                exclude=ctx.session,
            )
            await ctx.session_mgr.broadcast_to_room(
                target_room_id,
                f"  [1;31m{char['name']} breaks in![0m",
                exclude=ctx.session,
            )
            look_cmd = LookCommand()
            look_ctx = CommandContext(
                session=ctx.session, raw_input="look",
                command="look", args="",
                db=ctx.db, session_mgr=ctx.session_mgr,
            )
            await look_cmd.execute(look_ctx)


class StealCommand(BaseCommand):
    """
    steal <item>  — Attempt to steal a displayed item from a housing room.
    Requires being inside the housing room first (via lockpick or invite).
    Drop 7: Housing Security & Intrusion.
    """
    key = "steal"
    aliases = ["pilfer", "swipe"]
    help_text = (
        "Attempt to steal a displayed trophy item from a housing room.\n"
        "\n"
        "USAGE:\n"
        "  steal <item name>\n"
        "\n"
        "You must already be inside the housing room.\n"
        "Difficulties vary by zone: contested needs Sneak+Security (30),\n"
        "lawless needs Sneak only (15). Secured zones: impossible."
    )
    usage = "steal <item name>"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            return
        item_name = (ctx.args or "").strip()
        if not item_name:
            await ctx.session.send_line("  Steal what? Usage: steal <item name>")
            return

        room_id = char.get("room_id")
        from engine.housing import attempt_theft
        result = await attempt_theft(
            ctx.db, char, room_id, item_name, ctx.session_mgr
        )
        await ctx.session.send_line(result["msg"])


class PickpocketCommand(BaseCommand):
    """
    pickpocket <player> — Attempt to steal credits from a sleeping character.
    Tier 3 Feature #16: Sleeping Character Vulnerability.

    Only works on characters who disconnected in non-secured rooms.
    Pickpocket (Dexterity) check vs. sleeper's Perception at -2D.
    Success: steal 5-25% of their credits. Fumble: you're exposed.
    """
    key = "pickpocket"
    aliases = ["pp"]
    help_text = (
        "Attempt to steal credits from a sleeping character.\n"
        "\n"
        "USAGE:\n"
        "  pickpocket <player name>\n"
        "\n"
        "Only works on characters who disconnected in non-secured rooms.\n"
        "Success steals 5-25% of their credits. Fumble alerts the room.\n"
        "Cannot be used in SECURED zones. 10-minute cooldown per target."
    )
    usage = "pickpocket <player name>"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            return
        target_name = (ctx.args or "").strip()
        if not target_name:
            await ctx.session.send_line(
                "  Pickpocket whom? Usage: pickpocket <player name>")
            return

        # Find the target character in the room (must be sleeping)
        room_id = char.get("room_id")
        if not room_id:
            await ctx.session.send_line("  You need to be in a room.")
            return

        # Look for sleeping characters in this room
        # Sleeping chars are NOT in session_mgr (they're disconnected)
        # so we need to query the DB for characters with this room_id
        try:
            rows = await ctx.db.fetchall(
                """SELECT id, name, credits, attributes, faction_id
                   FROM characters
                   WHERE room_id = ? AND LOWER(name) LIKE LOWER(?)""",
                (room_id, f"%{target_name}%"),
            )
        except Exception:
            log.warning("PickpocketCommand: DB query failed", exc_info=True)
            await ctx.session.send_line("  Something went wrong.")
            return

        if not rows:
            await ctx.session.send_line(
                f"  No one named '{target_name}' is here.")
            return

        # Filter to sleeping characters (not online)
        target = None
        for r in rows:
            r = dict(r)
            # Check they're not currently online
            online = ctx.session_mgr.find_by_character(r["id"])
            if online:
                await ctx.session.send_line(
                    f"  {r['name']} is awake. You can't pickpocket an alert target.")
                return
            # Check sleeping flag
            from engine.sleeping import is_sleeping
            if is_sleeping(r):
                target = r
                break

        if not target:
            await ctx.session.send_line(
                f"  {rows[0]['name'] if rows else target_name} is not asleep here.")
            return

        # Can't pickpocket yourself
        if target["id"] == char["id"]:
            await ctx.session.send_line("  You can't pickpocket yourself.")
            return

        from engine.sleeping import attempt_pickpocket
        result = await attempt_pickpocket(char, target, ctx.db, ctx.session_mgr)

        await ctx.session.send_line(result["msg"])

        # Broadcast fumble alert to room if present
        if result.get("room_msg"):
            await ctx.session_mgr.broadcast_to_room(
                room_id, result["room_msg"],
                exclude=ctx.session,
            )


# ── Think (internal monologue) ────────────────────────────────────────────────

class ThinkCommand(BaseCommand):
    """
    think <text>
    Record an internal thought visible only to you and the AI systems.
    Thoughts feed into the PC Narrative Memory pipeline — NPCs and the
    Director AI can pick up on behavioral patterns over time, but they
    never see the exact words.
    """
    key = "think"
    aliases = []
    help_text = (
        "Record an internal thought.\n\n"
        "USAGE:\n"
        "  think <text>\n\n"
        "Your thoughts are private — no one else in the room sees them.\n"
        "The AI narrative system uses them to inform NPC behavior and\n"
        "Director quest hooks over time.\n\n"
        "EXAMPLES:\n"
        "  think I don't trust this Rodian.\n"
        "  think Something about this deal feels wrong..."
    )
    usage = "think <text>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return

        text = (ctx.args or "").strip()
        if not text:
            await ctx.session.send_line(
                "  What are you thinking?  Usage: think <text>"
            )
            return

        # Cap at 500 characters
        if len(text) > 500:
            text = text[:500]

        # Display to the thinker only (italic/dim styling)
        await ctx.session.send_line(
            f"  \033[2;3mYou think: {text}\033[0m"
        )

        # Log to pc_action_log for narrative memory pipeline
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(
                ctx.db, char["id"], NT.THOUGHT,
                text[:120],  # summary capped for log readability
                {"full_text": text},
            )
        except Exception:
            log.warning("ThinkCommand: log_action failed", exc_info=True)


class BuffsCommand(BaseCommand):
    """Display active buffs and debuffs."""
    key = "+buffs"
    aliases = ["buffs", "+effects"]
    help_text = "Show your active buffs and debuffs with remaining durations."
    usage = "+buffs"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            return
        from engine.buffs import format_buffs_display
        lines = format_buffs_display(char)
        for line in lines:
            await ctx.session.send_line(line)


def register_all(registry):
    """Register all built-in commands with the registry."""
    commands = [
        LookCommand(),
        MoveCommand(),
        PicklockCommand(),
        ForceDoorCommand(),
        StealCommand(),
        PickpocketCommand(),
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
        WearCommand(),
        RemoveArmorCommand(),
        ArmorListCommand(),
        RepairCommand(),
        SellCommand(),
        WeaponsListCommand(),
        RespawnCommand(),
        SemiposeCommand(),
        TradeCommand(),
        ThinkCommand(),
        BuffsCommand(),
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


async def _handle_sell_to_droid(ctx, resource_arg: str, shop_arg: str) -> None:
    """Handle 'sell <resource> to <shop name>' — routes to vendor droid buy-order fill."""
    from engine.vendor_droids import sell_to_droid, find_droid_by_name

    char   = ctx.session.character
    droids = await ctx.db.get_objects_in_room(char["room_id"], "vendor_droid")

    if not droids:
        await ctx.session.send_line(
            "  No vendor droids in this area. "
            "Use 'sell' to sell your equipped weapon to an NPC vendor."
        )
        return

    droid = find_droid_by_name(droids, shop_arg)
    if not droid:
        await ctx.session.send_line(
            f"  No vendor droid named '{shop_arg}' here. "
            f"Use 'browse' to see available shops."
        )
        return

    # Ask quantity if not specified in resource_arg
    resource_type = resource_arg.lower().replace(" ", "_")
    ok, msg = await sell_to_droid(char, droid["id"], resource_type, 999, ctx.db)
    await ctx.session.send_line(f"  {msg}")


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
    try:
        await ctx.db.log_credit(char["id"], total_revenue, "trade_goods",
                                 new_credits)
    except Exception as _e:
        log.debug("silent except in parser/builtin_commands.py:2555: %s", _e, exc_info=True)

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
            log.warning("_handle_sell_cargo: unhandled exception", exc_info=True)
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
        "  trade <player> item <item name>    — offer an inventory item\n"
        "  trade accept <player>              — accept a pending offer\n"
        "  trade decline <player>             — decline a pending offer\n"
        "  trade cancel                       — cancel your outgoing offer\n"
        "  trade list                         — show pending offers\n"
        "\n"
        "Both parties must be in the same room. The target must 'trade accept'\n"
        "within 2 minutes or the offer expires.\n"
        "A 5% tax applies to credit trades (economy sink).\n"
        "\n"
        "EXAMPLES:\n"
        "  trade Tundra 500 credits\n"
        "  trade Tundra item Heavy Blaster Pistol\n"
        "  trade accept Jex"
    )
    usage = "trade <player> <amount> credits | trade <player> item <name> | trade accept|decline|cancel|list"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        args = (ctx.args or "").strip()
        parts = args.split()

        if not parts:
            await ctx.session.send_line(
                "  Usage: trade <player> <amount> credits\n"
                "         trade <player> item <item name>\n"
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
            # trade <player> <amount> credits  OR  trade <player> item <name>
            await self._offer(ctx, char, parts)

    async def _offer(self, ctx, char, parts):
        _purge_trade_offers()
        if len(parts) < 3:
            await ctx.session.send_line(
                "  Usage: trade <player> <amount> credits\n"
                "         trade <player> item <item name>\n"
                "  Example: trade Tundra 500 credits\n"
                "  Example: trade Tundra item Heavy Blaster Pistol"
            )
            return

        target_name = parts[0]
        kind_hint = parts[1].lower()

        # ── Item trade ────────────────────────────────────────────────────
        if kind_hint == "item":
            item_name = " ".join(parts[2:])
            if not item_name:
                await ctx.session.send_line("  Specify an item name: trade <player> item <name>")
                return

            # Find item in inventory
            import json as _tj
            inv = await ctx.db.get_inventory(char["id"])
            matched_item = None
            item_name_lower = item_name.lower()
            for it in inv:
                it_name = it.get("name", it.get("key", ""))
                if it_name.lower() == item_name_lower or it_name.lower().startswith(item_name_lower):
                    matched_item = it
                    break

            if not matched_item:
                await ctx.session.send_line(
                    f"  You don't have '{item_name}' in your inventory.\n"
                    f"  Use 'inventory' to see your items."
                )
                return

            display_name = matched_item.get("name", matched_item.get("key", "Unknown"))

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
                "amount":       0,
                "kind":         "item",
                "item":         matched_item,
                "item_name":    display_name,
                "item_key":     matched_item.get("key", ""),
                "ts":           _trade_time.time(),
            }

            await ctx.session.send_line(
                f"  \033[1;33mTrade offer sent:\033[0m {display_name} → {target['name']}.\n"
                f"  Waiting for them to 'trade accept {char['name']}'."
            )
            await target_sess.send_line(
                f"\n  \033[1;33m[TRADE OFFER]\033[0m {char['name']} offers you "
                f"\033[1;37m{display_name}\033[0m.\n"
                f"  Type '\033[1;37mtrade accept {char['name']}\033[0m' to accept "
                f"or '\033[1;37mtrade decline {char['name']}\033[0m' to decline. "
                f"(Expires in 2 minutes.)\n"
            )
            return

        # ── Credit trade (original path) ──────────────────────────────────
        amount_str = parts[1]
        kind = parts[2].lower() if len(parts) > 2 else ""

        if kind != "credits":
            await ctx.session.send_line(
                "  Usage: trade <player> <amount> credits\n"
                "         trade <player> item <item name>"
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
        trade_kind = offer.get("kind", "credits")

        # ── Item trade execution ──────────────────────────────────────────
        if trade_kind == "item":
            item_key = offer.get("item_key", "")
            item_name = offer.get("item_name", "Unknown")
            item_data = offer.get("item", {})

            # Verify offerer still has the item
            import json as _atj
            offerer_inv = await ctx.db.get_inventory(offerer["id"])
            has_item = any(
                it.get("key") == item_key or it.get("name", "").lower() == item_name.lower()
                for it in offerer_inv
            )
            if not has_item:
                _pending_trades.pop(offer_key, None)
                await ctx.session.send_line(
                    f"  {offerer['name']} no longer has {item_name}. Trade cancelled."
                )
                await offerer_sess.send_line(
                    f"  Trade with {char['name']} cancelled — you no longer have {item_name}."
                )
                return

            # Execute item transfer atomically
            removed = await ctx.db.remove_from_inventory(offerer["id"], item_key)
            if not removed:
                _pending_trades.pop(offer_key, None)
                await ctx.session.send_line("  Item transfer failed. Trade cancelled.")
                return

            await ctx.db.add_to_inventory(char["id"], item_data)
            _pending_trades.pop(offer_key, None)

            await ctx.session.send_line(
                f"  \033[1;32m[TRADE COMPLETE]\033[0m Received "
                f"\033[1;37m{item_name}\033[0m from {offerer['name']}."
            )
            await offerer_sess.send_line(
                f"  \033[1;32m[TRADE COMPLETE]\033[0m {char['name']} accepted. "
                f"Gave \033[1;37m{item_name}\033[0m."
            )

            # Broadcast to room
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                f"  {offerer['name']} hands {item_name} to {char['name']}.",
                exclude=[offerer["id"], char["id"]],
            )

            # Narrative log
            try:
                from engine.narrative import log_action, ActionType as NT
                await log_action(ctx.db, char["id"], NT.PURCHASE,
                                 f"Received {item_name} from {offerer['name']} via trade",
                                 {"item": item_name, "counterpart": offerer["name"]})
                await log_action(ctx.db, offerer["id"], NT.PURCHASE,
                                 f"Gave {item_name} to {char['name']} via trade",
                                 {"item": item_name, "counterpart": char["name"]})
            except Exception:
                log.warning("_accept: item trade narrative log failed", exc_info=True)

            return

        # ── Credit trade execution (original path) ───────────────────────
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

        # Execute transfer with 5% transaction tax (economy hardening v23)
        tax = max(1, amount // 20)  # 5% floor of 1 credit
        received = amount - tax

        offerer["credits"] = offerer.get("credits", 0) - amount
        char["credits"] = char.get("credits", 0) + received

        await ctx.db.save_character(offerer["id"], credits=offerer["credits"])
        await ctx.db.save_character(char["id"], credits=char["credits"])

        _pending_trades.pop(offer_key, None)

        await ctx.session.send_line(
            f"  \033[1;32m[TRADE COMPLETE]\033[0m Received {received:,} credits "
            f"from {offerer['name']}. "
            f"\033[2m(5% tax: {tax:,} cr)\033[0m  "
            f"Balance: {char['credits']:,} cr."
        )
        await offerer_sess.send_line(
            f"  \033[1;32m[TRADE COMPLETE]\033[0m {char['name']} accepted. "
            f"-{amount:,} credits. "
            f"\033[2m(5% tax: {tax:,} cr)\033[0m  "
            f"Balance: {offerer['credits']:,} cr."
        )

        # Broadcast to room (brief)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {offerer['name']} and {char['name']} exchange credits.",
            exclude=[offerer["id"], char["id"]],
        )

        # Credit log (economy hardening v23)
        try:
            await ctx.db.log_credit(offerer["id"], -amount, "p2p_transfer",
                                     offerer["credits"])
            await ctx.db.log_credit(char["id"], received, "p2p_transfer",
                                     char["credits"])
            await ctx.db.log_credit(0, -tax, "p2p_tax", 0)  # char_id=0 = system sink
        except Exception:
            log.warning("_accept: credit log failed", exc_info=True)

        # Narrative log
        try:
            from engine.narrative import log_action, ActionType as NT
            await log_action(ctx.db, char["id"], NT.PURCHASE,
                             f"Received {received:,} credits from {offerer['name']} via trade (tax: {tax:,})",
                             {"amount": received, "tax": tax, "counterpart": offerer["name"]})
            await log_action(ctx.db, offerer["id"], NT.PURCHASE,
                             f"Paid {amount:,} credits to {char['name']} via trade (tax: {tax:,})",
                             {"amount": -amount, "tax": tax, "counterpart": char["name"]})
        except Exception:
            log.warning("_accept: unhandled exception", exc_info=True)

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

        def _offer_desc(v):
            if v.get("kind") == "item":
                return f"\033[1;37m{v.get('item_name', 'Unknown Item')}\033[0m"
            return f"{v['amount']:,} credits"

        lines = ["\033[1;36m── Pending Trades ──────────────────\033[0m"]
        for v in incoming:
            age = int(_trade_time.time() - v["ts"])
            lines.append(
                f"  \033[1;33mINBOUND\033[0m  {v['offerer_name']} offers "
                f"{_offer_desc(v)}  \033[2m({age}s ago)\033[0m"
            )
            lines.append(f"           → 'trade accept {v['offerer_name']}'")
        for v in outgoing:
            age = int(_trade_time.time() - v["ts"])
            lines.append(
                f"  \033[2mOUTBOUND\033[0m → {v['target_name']}:  "
                f"{_offer_desc(v)}  \033[2m({age}s ago)\033[0m"
            )
        lines.append("\033[1;36m────────────────────────────────────\033[0m")
        await ctx.session.send_line("\n".join(lines))
