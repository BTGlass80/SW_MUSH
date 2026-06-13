# -*- coding: utf-8 -*-
"""
Built-in commands for Phase 1: navigation, communication, info, and admin.
"""
import logging
import textwrap
from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


def _opposite_direction(direction: str) -> str:
    """Return the human-readable opposite of a movement direction.

    Used to phrase wilderness arrival broadcasts: "X arrives from the south"
    when X moved north into the tile.
    """
    opposites = {
        "north": "south",      "south": "north",
        "east": "west",        "west": "east",
        "northeast": "southwest", "southwest": "northeast",
        "northwest": "southeast", "southeast": "northwest",
        "n": "south", "s": "north", "e": "west", "w": "east",
        "ne": "southwest", "sw": "northeast",
        "nw": "southeast", "se": "northwest",
    }
    return opposites.get((direction or "").lower(), direction)


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
    # W.2.4: _get_or_create_combat now takes a char (not room_id) so
    # wilderness combats are keyed by (sentinel_room_id, wx, wy).
    cover_max = await ctx.db.get_room_property(room_id, "cover_max", 0)
    combat = _get_or_create_combat(char, cover_max=cover_max)
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
        source_char=char,  # W.2.3.1: wilderness co-location filter
    )

    # Roll initiative
    if new_combat:
        events = combat.roll_initiative()
        await _broadcast_events(events, ctx.session_mgr, room_id,
                                source_char=combat.broadcast_source())

    # Auto-declare NPC actions
    await _auto_declare_npc_actions(combat, ctx)

    # Prompt the player
    await ctx.session.send_line(
        ansi.combat_msg("You're under attack! Declare: attack/dodge/aim/flee")
    )


async def _describe_inventory_item(ctx: "CommandContext", char: dict,
                                   arg: str) -> bool:
    """Try to resolve *arg* against the player's carried inventory and
    print the item's description.

    Resolution (same 3-pass shape as UseCommand):
      Pass 1 — exact ``key`` match (case-sensitive)
      Pass 2 — exact ``name`` match (case-insensitive)
      Pass 3 — unique substring on name or key (case-insensitive);
                multiple partial hits → "Which one?" and return True

    Description source priority:
      1. ``description`` or ``desc`` key in the inventory dict
      2. ``engine.organizations.EQUIPMENT_CATALOG[key]['description']``
      3. Equipped weapon/armor keys (via ``engine.items.equipment_keys``)
         resolved against EQUIPMENT_CATALOG — so ``look <equipped item>``
         also works.
      4. "You see nothing special about it."

    Returns True  when the arg was *handled* (item found, or ambiguous).
    Returns False when no inventory item matched so the caller can
    fall through to its existing room/error message.

    This is a READ-ONLY helper — no credits, no dice, no state change.
    """
    # ── fetch inventory ───────────────────────────────────────────────────
    try:
        inv = await ctx.db.get_inventory(char["id"])
    except Exception:
        log.debug("_describe_inventory_item: get_inventory failed", exc_info=True)
        return False

    inv = [item for item in (inv or []) if isinstance(item, dict)]

    # ── also expose equipped slots as pseudo-items for lookup ─────────────
    # We build a small list of {key, name, description} dicts from the
    # equipped weapon/armor keys so `look <equipped weapon>` works even
    # when the equipped item isn't separately tracked in the carried list.
    equip_items: list[dict] = []
    try:
        from engine.items import equipment_keys
        from engine.organizations import EQUIPMENT_CATALOG
        eq_keys = equipment_keys(char.get("equipment", "{}") or "{}")
        for slot_key in (eq_keys.get("weapon", ""), eq_keys.get("armor", "")):
            if not slot_key:
                continue
            # Only add if not already in inv (avoid double-match)
            already = any(i.get("key") == slot_key for i in inv)
            if not already:
                cat = EQUIPMENT_CATALOG.get(slot_key, {})
                equip_items.append({
                    "key": slot_key,
                    "name": cat.get("name", slot_key),
                    "description": cat.get("description", ""),
                    "_from_equip": True,
                })
    except Exception:
        log.debug("_describe_inventory_item: equip lookup failed", exc_info=True)

    all_items = inv + equip_items

    if not all_items:
        return False

    target = arg.strip()
    target_lower = target.lower()
    matched = None

    # Pass 1: exact key
    for item in all_items:
        if item.get("key") == target:
            matched = item
            break

    # Pass 2: exact name (case-insensitive)
    if matched is None:
        for item in all_items:
            if (item.get("name", "") or "").lower() == target_lower:
                matched = item
                break

    # Pass 3: unique substring on name or key
    if matched is None:
        partial = []
        for item in all_items:
            name = (item.get("name", "") or "").lower()
            key = (item.get("key", "") or "").lower()
            if target_lower in name or target_lower in key:
                partial.append(item)
        if len(partial) == 1:
            matched = partial[0]
        elif len(partial) > 1:
            names = [p.get("name") or p.get("key") or "?" for p in partial]
            await ctx.session.send_line(
                f"  Which one? {', '.join(names)}"
            )
            return True  # handled (ambiguous — caller must not emit "not found")

    if matched is None:
        return False  # not an inventory item — let caller handle

    # ── resolve description ───────────────────────────────────────────────
    item_key = matched.get("key", "") or ""
    item_name = matched.get("name") or item_key or "the item"

    # Priority 1: inline description/desc on the item dict
    desc = matched.get("description") or matched.get("desc") or ""

    # Priority 2: EQUIPMENT_CATALOG fallback
    if not desc and item_key:
        try:
            from engine.organizations import EQUIPMENT_CATALOG
            desc = EQUIPMENT_CATALOG.get(item_key, {}).get("description", "")
        except Exception:
            log.debug("_describe_inventory_item: EQUIPMENT_CATALOG lookup failed",
                      exc_info=True)

    # Priority 3: generic fallback
    if not desc:
        desc = "You see nothing special about it."

    await ctx.session.send_line(f"  {ansi.color(item_name, ansi.BOLD)}")
    await ctx.session.send_line(f"  {desc}")
    return True


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

        # ── W.2 phase 2: wilderness branch ──────────────────────────────
        try:
            from engine.wilderness_movement import in_wilderness
            if in_wilderness(char):
                await self._look_wilderness(ctx, char)
                return
        except Exception:
            log.warning("wilderness look fork failed", exc_info=True)

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
        """Room name + security/housing/claim/city tags."""
        _sec_tag = ""
        try:
            from engine.security import get_effective_security, security_label
            _room_sec = await get_effective_security(char["room_id"], ctx.db, character=char)
            _sec_tag = " " + security_label(_room_sec)
        except Exception:
            log.warning("_room_header: security tag failed", exc_info=True)

        # DIFF.2 (2026-06-13): threat-band tag alongside security. The
        # band is orthogonal to security — security says whether combat
        # is allowed, the band says how dangerous it is. Surfaced so
        # "players see where the tiers are" (the KNOWN lines). Settled
        # (the default mid-game band) is suppressed to keep the header
        # quiet for the common case; the off-default bands (Frontier /
        # Contested Marches / Deep Wilds) show.
        _threat_tag = ""
        try:
            from engine.threat_band import (
                get_effective_threat, threat_label, ThreatBand,
            )
            _band = await get_effective_threat(char["room_id"], ctx.db)
            if _band is not ThreatBand.SETTLED:
                _threat_tag = " " + threat_label(_band)
        except Exception:
            log.warning("_room_header: threat tag failed", exc_info=True)

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

        # Player Cities Phase 3: [CITY: <name>] bracket tag
        _city_tag = ""
        try:
            from engine.player_cities import (
                get_city_for_room, format_city_header_tag,
            )
            _city = await get_city_for_room(ctx.db, char["room_id"])
            if _city:
                _city_tag = format_city_header_tag(_city)
        except Exception:
            log.warning("_room_header: city tag failed", exc_info=True)

        await session.send_line(
            ansi.room_name(room["name"]) + _sec_tag + _threat_tag
            + _housing_tag + _claim_tag + _city_tag)

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

        # SRB.2 (May 22 2026): morale aura overlay per design §2.6.
        # Renders a single line under the room description naming the
        # active performer and the aura's effect. Suppressed if the
        # aura has expired (the row is still on disk until the tick
        # reaps it). Failure-tolerant: any DB issue silently no-ops.
        try:
            import time as _time
            from parser.entertainer_commands import _AURA_FLAVOR
            aura = await ctx.db.get_morale_aura(char["room_id"])
            if aura and float(aura.get("expires_at", 0.0)) > _time.time():
                magnitude = int(aura.get("magnitude", 0))
                flavor = _AURA_FLAVOR.get(magnitude, "A performance is in progress.")
                # Look up performer name; fall back to "Someone" if
                # the character row is gone (shouldn't happen but be safe).
                performer_name = "Someone"
                try:
                    perf = await ctx.db.get_character(aura["performer_id"])
                    if perf:
                        performer_name = perf.get("name") or performer_name
                except Exception:
                    log.debug(
                        "_room_overlays: morale aura performer "
                        "name lookup failed (best-effort)",
                        exc_info=True,
                    )
                await session.send_line(
                    f"  \033[36m\u266a {performer_name} is performing — {flavor}\033[0m"
                )
                await session.send_line(
                    "  \033[2m(Morale-related rolls are easier in this room.)\033[0m"
                )
        except Exception:
            log.warning("_room_overlays: morale aura failed", exc_info=True)

        # Player Cities Phase 3 (May 22 2026) — city motd + banishment
        # warning per design §12. Lookup the city by room (cheap; if
        # absent, all overlays no-op). Motd renders for everyone;
        # banishment warning renders only for banished viewers.
        try:
            from engine.player_cities import (
                get_city_for_room, is_banished,
            )
            _city = await get_city_for_room(ctx.db, char["room_id"])
            if _city:
                _motd = (_city.get("motd") or "").strip()
                if _motd:
                    await session.send_line(
                        f"  \033[2;3m— {_motd}\033[0m"
                    )
                if await is_banished(
                    ctx.db, int(_city["id"]), int(char["id"])
                ):
                    await session.send_line(
                        f"  \033[91m⚠ You are not welcome here. "
                        f"Move along.\033[0m"
                    )
        except Exception:
            log.warning(
                "_room_overlays: city overlay failed", exc_info=True,
            )

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
            source_char=char,  # W.2 phase 2: wilderness co-location
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
            # Try the player's own inventory before giving up entirely.
            if await _describe_inventory_item(ctx, char, ctx.args):
                return
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
                from engine.items import equipment_keys
                wkey = equipment_keys(c.data.get("equipment", "{}"))["weapon"]
                if wkey:
                    from engine.weapons import get_weapon_registry
                    w = get_weapon_registry().get(wkey)
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

            # ── WoW.2a: look self Force-connection descriptor ─────────
            # Per weight_of_war_design_v1.md §6: when a Jedi PC looks
            # at themselves, surface the narrative descriptor for the
            # current Weight-of-War tier. Conditions for display:
            #   - The looker IS the character being looked at (self).
            #   - The character is a Jedi PC (engine.weight_of_war.
            #     is_jedi_pc).
            #   - Weight > 20 (the "at peace" tier is silent — no
            #     descriptor — per design §6's table starting at
            #     "Troubled" being the first signal). This avoids a
            #     constant "you feel the Force flowing freely" message
            #     that would be just noise.
            # Other players looking at this character get no Weight
            # signal — per design §3, this is private Force state.
            try:
                from engine.weight_of_war import (
                    get_descriptor_for_char, get_weight, is_jedi_pc,
                )
                if c.data.get("id") == char.get("id"):
                    if is_jedi_pc(c.data):
                        wow_value = get_weight(c.data)
                        if wow_value > 20:
                            descriptor = get_descriptor_for_char(c.data)
                            await ctx.session.send_line(
                                f"    {ansi.color(descriptor, ansi.CYAN)}"
                            )
            except Exception:
                log.warning(
                    "_look_at: WoW descriptor render failed",
                    exc_info=True,
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
        # ── P-M.2 (May 20 2026): batched bond-role lookup ──────────────
        # Per padawan_master_system_design_v1.md §5.1 + v45 §8.12 #4:
        # show [Padawan]/[Master] marker on bonded PCs in the room
        # listing. Batched into a single SELECT to avoid N+1 queries
        # on busy rooms. The marker literals live as module constants
        # in parser/padawan_master_commands.py and are byte-grep-pinned
        # by tests + smoke (v45 §6.2 seventh phantom-pattern discipline).
        bond_roles: dict = {}
        try:
            from parser.padawan_master_commands import (
                PADAWAN_MARKER, MASTER_MARKER,
            )
            if present:
                bond_roles = await ctx.db.get_bond_roles_for_chars(
                    [p["id"] for p in present]
                )
        except Exception:
            log.warning(
                "_look_room_contents: bond-role lookup failed; "
                "markers will be omitted this turn",
                exc_info=True,
            )
            PADAWAN_MARKER = ""
            MASTER_MARKER = ""
        for other in present:
            equip_str = ""
            try:
                from engine.items import equipment_keys
                wkey = equipment_keys(other.get("equipment", "{}"))["weapon"]
                if wkey:
                    from engine.weapons import get_weapon_registry
                    w = get_weapon_registry().get(wkey)
                    if w:
                        equip_str = f", wielding a {w.name}"
            except Exception:
                log.warning("execute: unhandled exception", exc_info=True)
                pass
            # +pvp display surface (May 18 2026): show a [PvP] marker
            # after the flagged player's name so observers can see at a
            # glance who's opted in. SECURED zones still refuse PvP
            # regardless of flag state — the marker is informational, not
            # a green light.
            pvp_str = (" \033[1;31m[PvP]\033[0m"
                       if other.get("pvp_flagged") else "")
            # P-M.2 bond marker. 'both' shows both markers (rare: a
            # Knight who has not yet been formally promoted past their
            # own Master-bond but has taken a Padawan).
            role = bond_roles.get(other["id"])
            bond_str = ""
            if role == "padawan":
                bond_str = f" {PADAWAN_MARKER}"
            elif role == "master":
                bond_str = f" {MASTER_MARKER}"
            elif role == "both":
                bond_str = f" {PADAWAN_MARKER} {MASTER_MARKER}"
            # Drop 3 B3: worn vanity title, rendered as an honorific right
            # after the name (cosmetic standing; surfaces here for observers).
            from engine.titles import worn_title as _worn_title
            _wt = _worn_title(other)
            title_str = (", " + ansi.dim(_wt)) if _wt else ""
            await session.send_line(
                f"  {ansi.player_name(other['name'])}{title_str}"
                f"{pvp_str}{bond_str} is here{equip_str}."
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

        # ── PG.1.death.b (Drop 2d): corpses in the room ──
        # Any non-decayed corpses show up between the NPC list and
        # the vendor droids. Resolves owner-name from the
        # characters table; tolerant of missing rows.
        try:
            _corpses = await ctx.db.get_corpses_in_room(char["room_id"])
            for _cr in _corpses:
                try:
                    _owner = await ctx.db.get_character(_cr["char_id"])
                except Exception:
                    _owner = None
                _owner_name = (_owner or {}).get("name", "") or "an unknown person"
                # Resolve a friendly time-since-death.
                try:
                    import time as _t
                    _age = max(0.0, _t.time() - float(_cr.get("died_at", 0.0)))
                    if _age < 60:
                        _age_str = "moments ago"
                    elif _age < 3600:
                        _age_str = f"{int(_age / 60)} minutes ago"
                    else:
                        _age_str = f"{int(_age / 3600)} hours ago"
                except Exception:
                    _age_str = "recently"
                await session.send_line(
                    f"  {ansi.dim('The body of')} "
                    f"{ansi.player_name(_owner_name)}"
                    f" {ansi.dim('lies here (' + _age_str + ').')}"
                )
        except Exception:
            log.debug("look: corpse listing failed", exc_info=True)

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


    # ─────────────────────────────────────────────────────────────────────
    # W.2 phase 2: wilderness rendering branch
    # ─────────────────────────────────────────────────────────────────────

    async def _look_wilderness(self, ctx, char):
        """Render a wilderness tile.

        Pulls the WildernessRegion from the cache (or YAML on miss),
        renders tile + adjacent terrain via the engine kernel, lists
        co-located peers (Path B: characters_at_tile gives us only
        same-tile PCs).
        """
        session = ctx.session
        try:
            from engine.wilderness_movement import (
                get_or_load_region, get_wilderness_coords,
                render_tile, render_adjacent_terrain, characters_at_tile,
                find_edge_at_coords,
            )
        except Exception:
            await session.send_line("You can't see anything.")
            return

        coords = get_wilderness_coords(char)
        if coords is None:
            await session.send_line("You feel disoriented; the desert blurs.")
            return
        slug, x, y = coords

        region = await get_or_load_region(ctx.db, slug)
        if region is None:
            await session.send_line(f"You are in {slug}, but the region is unloaded.")
            return

        tile = render_tile(region, x, y)

        # Header — region name + coords
        await session.send_line("")
        await session.send_line(
            f"\033[1;33m{tile['region_name']} — Coordinates {x}, {y}\033[0m"
        )

        # Description (terrain variant + optional time overlay)
        if tile["description"]:
            await session.send_line(f"  {tile['description']}")
        if tile["time_overlay"]:
            await session.send_line(f"  {tile['time_overlay']}")

        # Status line: security tag + movement cost + hazard hint
        sec = (tile.get("security") or "").upper()
        sec_tag = ""
        if sec == "LAWLESS":
            sec_tag = "\033[1;31m[LAWLESS]\033[0m  "
        elif sec == "CONTESTED":
            sec_tag = "\033[1;33m[CONTESTED]\033[0m  "
        elif sec == "SECURED":
            sec_tag = "\033[1;32m[SECURED]\033[0m  "
        await session.send_line("")
        await session.send_line(
            f"  {sec_tag}Movement: {tile['terrain']} (cost {tile['move_cost']})"
        )
        if tile.get("ambient_hazard") and tile["ambient_hazard"] != "none":
            await session.send_line(
                f"  \033[2mAmbient hazard: {tile['ambient_hazard']} "
                f"(severity {tile['hazard_severity']})\033[0m"
            )

        # SYN.10 (May 25 2026): Region info block per design §2.6.
        # Renders ownership, influence breakdown, weekly resource
        # quality, and active contest under the security/movement
        # tags. Failure-tolerant: any error silently no-ops so the
        # wilderness look itself never breaks.
        try:
            from engine.territory_display import get_region_look_block
            viewing_org = char.get("faction_id")
            if viewing_org == "independent":
                viewing_org = None
            region_lines = await get_region_look_block(
                ctx.db, slug, viewing_org_code=viewing_org, ansi=True,
            )
            if region_lines:
                await session.send_line("")
                for rline in region_lines:
                    await session.send_line(rline)
        except Exception:
            log.warning(
                "_look_wilderness: region info block failed",
                exc_info=True,
            )

        # Adjacent terrain (compass-style)
        adj = render_adjacent_terrain(region, x, y)
        await session.send_line("")
        await session.send_line("  Terrain around you:")
        for d in ("north", "south", "east", "west"):
            t = adj.get(d)
            label = t if t else "edge of region"
            await session.send_line(f"    {d:6s} {label}")

        # Edge exit hint
        edge = find_edge_at_coords(region, x, y)
        if edge is not None:
            await session.send_line("")
            await session.send_line(
                f"  \033[1;36mYou could leave the desert here — "
                f"head {edge.direction_back_to_room}.\033[0m"
            )

        # Other PCs at this tile (co-location filtered by helper)
        others = await characters_at_tile(ctx.db, slug, x, y)
        peers = [o for o in others if o.get("id") != char.get("id")]
        if peers:
            await session.send_line("")
            for o in peers:
                await session.send_line(
                    f"  {ansi.player_name(o['name'])} is here."
                )

        await session.send_line("")




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

        # ── W.2 phase 2: wilderness fork ────────────────────────────────
        # If character is already in wilderness, branch entirely to the
        # wilderness handler — it owns in-tile movement, edge exits,
        # and all messaging.
        try:
            from engine.wilderness_movement import in_wilderness
            if in_wilderness(char):
                await self._execute_wilderness_move(ctx, char, direction)
                return
        except Exception:
            log.warning("wilderness move fork failed", exc_info=True)
            # Fall through to normal-room path

        exit_data = await self._match_exit(ctx, char, direction)
        if not exit_data:
            # ── W.2 phase 2: wilderness entry from hand-built room ─────
            # No normal exit matched; check whether the current room
            # is a wilderness edge entry point for this direction.
            try:
                if await self._try_wilderness_entry(ctx, char, direction):
                    return
            except Exception:
                log.warning("wilderness entry fork failed", exc_info=True)
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

        # SRB.2 (May 22 2026): if this character is the active performer
        # in their old room, clear the morale aura on departure per
        # design §2.1 ("until performer leaves the room"). Failure-
        # tolerant: a DB error doesn't block the movement.
        try:
            old_aura = await ctx.db.get_morale_aura(old_room_id)
            if old_aura and int(old_aura.get("performer_id", 0)) == char["id"]:
                await ctx.db.clear_morale_aura(old_room_id)
        except Exception:
            log.warning("MoveCommand: aura-clear hook failed", exc_info=True)

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

        await self._post_move_hooks(ctx, session, char, new_room_id,
                                    direction=direction, exit_data=exit_data)

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

        # Conditional room-lock gate (F.7.e):
        # If the destination room carries a `locked_until_flag` property
        # in its world-data definition, evaluate the named flag against
        # the character's quest state. Admins/builders bypass.
        try:
            from engine.room_locks import can_enter_locked_room
            _lock_ctx = {}
            account = await ctx.db.get_account(char.get("account_id", 0))
            if account:
                _lock_ctx["is_admin"] = bool(account.get("is_admin"))
                _lock_ctx["is_builder"] = bool(account.get("is_builder"))
            _allowed, _reason = await can_enter_locked_room(
                ctx.db, char, new_room_id, lock_ctx=_lock_ctx,
            )
            if not _allowed:
                await session.send_line(f"  \033[1;33m{_reason}\033[0m")
                return True
        except Exception:
            pass  # Graceful fallback — fail-open

        # Player Cities Phase 5 (May 22 2026) §6.3 gate:
        # Non-citizens (including guests) cannot enter rooms flagged
        # citizen_only. Failure-tolerant: any exception in the cities
        # layer logs and falls open per design §6.3 ("cities are
        # public spaces by default").
        try:
            from engine.player_cities import can_enter_city_room
            _allowed, _reason = await can_enter_city_room(
                ctx.db, char, new_room_id,
            )
            if not _allowed:
                await session.send_line(f"  \033[1;33m{_reason}\033[0m")
                return True
        except Exception:
            log.warning(
                "_check_exit_gates: city gate failed", exc_info=True,
            )

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
        """Broadcast departure message to the old room.

        W.2.3.1: ``source_char=char`` filters the broadcast to the old
        room's co-located peers (in wilderness, same tile). In regular
        rooms the kwarg is a no-op (no wilderness state on char).
        """
        _osucc = (lock_d.get("osucc_msg") or "").strip()
        if _osucc:
            _osucc = _osucc.replace("%N", char["name"])
            await ctx.session_mgr.broadcast_to_room(
                old_room_id, f"  {_osucc}", exclude=session,
                source_char=char,
            )
        else:
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"{ansi.player_name(char['name'])} leaves {direction}.",
                exclude=session,
                source_char=char,
            )

    async def _broadcast_arrival(self, ctx, session, char, new_room_id, lock_d):
        """Broadcast arrival message to the new room.

        W.2.3.1: ``source_char=char`` filters to the new room's
        co-located peers (in wilderness, the tile char just stepped
        onto). In regular rooms the kwarg is a no-op.
        """
        _odrop = (lock_d.get("odrop_msg") or "").strip()
        if _odrop:
            _odrop = _odrop.replace("%N", char["name"])
            await ctx.session_mgr.broadcast_to_room(
                new_room_id, f"  {_odrop}", exclude=session,
                source_char=char,
            )
        else:
            await ctx.session_mgr.broadcast_to_room(
                new_room_id,
                f"{ansi.player_name(char['name'])} arrives.",
                exclude=session,
                source_char=char,
            )

    async def _fire_room_hook(self, ctx, session, char, room_id, hook_name):
        """Fire ALEAVE/AENTER room hook."""
        try:
            from parser.attr_commands import fire_room_hook
            await fire_room_hook(ctx.db, ctx.session_mgr, room_id, hook_name,
                                 char=char, session=session)
        except Exception as _e:
            log.debug("_fire_room_hook %s: %s", hook_name, _e, exc_info=True)


    # ─────────────────────────────────────────────────────────────────────
    # W.2 phase 2: wilderness movement helpers
    # ─────────────────────────────────────────────────────────────────────

    async def _try_wilderness_entry(self, ctx, char, direction) -> bool:
        """Check whether the current room is a wilderness edge entry for direction.

        If so, transition the character into wilderness at the edge's
        coords and return True. If not, return False so the caller
        falls through to the normal "you can't go that way" message.
        """
        try:
            from engine.wilderness_movement import (
                get_or_load_region, find_entry_edges_for_room,
            )
        except Exception:
            return False

        room = await ctx.db.get_room(char["room_id"])
        if not room:
            return False

        # Pull room slug from properties
        import json as _wj
        rprops = room.get("properties", "{}")
        if isinstance(rprops, str):
            try:
                rprops = _wj.loads(rprops or "{}")
            except Exception:
                rprops = {}
        room_slug = (rprops.get("slug") or "").strip()
        if not room_slug:
            return False

        # Iterate registered regions and check each for matching edges
        rows = await ctx.db._db.execute_fetchall(
            "SELECT slug FROM wilderness_regions"
        )
        for r in rows:
            slug = r["slug"]
            region = await get_or_load_region(ctx.db, slug)
            if region is None:
                continue

            for edge in find_entry_edges_for_room(region, room_slug):
                if direction != edge.direction_from_room:
                    continue

                # Match — transition into wilderness at edge.coords.
                sentinel_rows = await ctx.db._db.execute_fetchall(
                    "SELECT sentinel_room_id FROM wilderness_regions WHERE slug = ?",
                    (slug,),
                )
                if not sentinel_rows or not sentinel_rows[0]["sentinel_room_id"]:
                    log.warning("wilderness entry: no sentinel for %r", slug)
                    return False
                sentinel_id = sentinel_rows[0]["sentinel_room_id"]

                old_room_id = char["room_id"]
                ex, ey = edge.coords

                # Departure broadcast in OLD room — no source_char filter
                # needed; caller is leaving a normal room and everyone there
                # should see them go.
                await ctx.session_mgr.broadcast_to_room(
                    old_room_id,
                    f"{char['name']} heads {direction}.",
                    exclude=ctx.session,
                )

                # Update character state
                char["room_id"] = sentinel_id
                char["wilderness_region_slug"] = slug
                char["wilderness_x"] = ex
                char["wilderness_y"] = ey
                await ctx.db.save_character(
                    char["id"],
                    room_id=sentinel_id,
                    wilderness_region_slug=slug,
                    wilderness_x=ex,
                    wilderness_y=ey,
                )

                # Self-message
                if edge.enter_message:
                    await ctx.session.send_line("")
                    await ctx.session.send_line(edge.enter_message.strip())

                # Auto-look (LookCommand will branch to wilderness path now)
                look_cmd = LookCommand()
                look_ctx = CommandContext(
                    session=ctx.session, raw_input="look", command="look",
                    args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr,
                )
                await look_cmd.execute(look_ctx)

                return True

        return False

    async def _execute_wilderness_move(self, ctx, char, direction):
        """Movement handler for characters already in wilderness.

        Two paths:
          1. Edge exit: at edge coords + direction matches direction_back_to_room
          2. In-tile move: ask move_in_wilderness, update coords on success
        """
        session = ctx.session
        try:
            from engine.wilderness_movement import (
                get_or_load_region, find_edge_for_exit_direction,
                move_in_wilderness, get_wilderness_coords,
            )
        except Exception:
            await session.send_line("Movement is unavailable here.")
            return

        coords = get_wilderness_coords(char)
        if coords is None:
            await session.send_line("You feel disoriented; the desert blurs.")
            return
        slug, x, y = coords

        region = await get_or_load_region(ctx.db, slug)
        if region is None:
            await session.send_line("You can't move — this region is unavailable.")
            return

        # 1. Edge exit?
        edge = find_edge_for_exit_direction(region, x, y, direction)
        if edge is not None:
            await self._execute_wilderness_exit(ctx, char, edge)
            return

        # 2. In-tile move
        result = move_in_wilderness(region, x, y, direction)
        if not result.ok:
            await session.send_line(result.reason or f"You can't go {direction}.")
            return

        # Departure broadcast at old tile (Path B: source_char filters)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"{char['name']} moves {direction}.",
            exclude=ctx.session,
            source_char=char,  # filtered to old-tile peers
        )

        # Update coords
        char["wilderness_x"] = result.new_x
        char["wilderness_y"] = result.new_y
        await ctx.db.save_character(
            char["id"],
            wilderness_x=result.new_x,
            wilderness_y=result.new_y,
        )

        # Arrival broadcast at new tile (source_char now points to new coords)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"{char['name']} arrives from the {_opposite_direction(direction)}.",
            exclude=ctx.session,
            source_char=char,  # filtered to new-tile peers
        )

        # ── T2.WENC encounter roll (May 24 2026) ────────────────────────
        # Per wilderness_system_design_v1.md §5: roll for a wilderness
        # encounter on the new tile. The selector enforces the
        # per-character 60s cooldown and filters the region's pool by
        # terrain + edge distance + faction gate. Regions without an
        # encounter pool no-op silently.
        #
        # This drop fires the encounter as a narrative broadcast only.
        # NPC spawn / vendor caravan / weather effects land in a
        # follow-up sub-drop (T2.WENC.b) per minimal-substrate-first
        # discipline.
        try:
            from engine.wilderness_encounters import roll_encounter
            # Gundark Drop E: carried-gear gate. One inventory read per
            # wilderness move feeds the animal-excluder aversion (and
            # any future carried-key encounter gates) — roll_encounter
            # is sync, so the async caller fetches.
            try:
                _carried = await ctx.db.get_inventory(char["id"])
                _carried_keys = {
                    d.get("key", "").lower()
                    for d in _carried if isinstance(d, dict)
                }
            except Exception:
                _carried_keys = None
            # DIFF.3 (2026-06-13): resolve the destination tile's threat
            # band so the encounter selector can gate the pool by tier
            # (Frontier tiles draw trivial fauna only; Deep Wilds unlock
            # minibosses). Failure-tolerant — a read error resolves to
            # the Settled default rating (2).
            try:
                from engine.threat_band import get_effective_threat
                _tile_band = (await get_effective_threat(
                    char["room_id"], ctx.db)).rating
            except Exception:
                _tile_band = 2
            enc_result = roll_encounter(
                region,
                new_x=result.new_x,
                new_y=result.new_y,
                terrain=result.terrain or region.default_terrain,
                char=char,
                db=ctx.db,
                carried_keys=_carried_keys,
                tile_band_rating=_tile_band,
            )
            if (not enc_result.fired
                    and enc_result.reason == "averted_by_excluder"):
                await session.send_line(
                    "  \033[2mSomething large shifts in the dark — then "
                    "your animal excluder's ultrasonic whine turns it "
                    "away.\033[0m")
            if enc_result.fired and enc_result.entry is not None:
                narrative = enc_result.entry.narrative or (
                    f"[Something stirs nearby — {enc_result.entry.id}.]"
                )
                await session.send_line("")
                await session.send_line(f"[ENCOUNTER] {narrative}")
                # Lane A Phase B (T2.WENC.b): a hostile/non_hostile encounter
                # whose payload.npc_template resolves in the creature library
                # spawns the creature(s) with faithful stats; a hostile one
                # starts combat immediately. Failure-tolerant in the bridge,
                # and guarded again by the enclosing try/except.
                _etype = getattr(enc_result.entry, "type", "")
                _pl = getattr(enc_result.entry, "payload", None) or {}
                if _etype in ("hostile", "non_hostile") and _pl.get("npc_template"):
                    from engine.wilderness_encounter_runtime import (
                        resolve_encounter_spawn,
                    )
                    await resolve_encounter_spawn(
                        ctx.db, ctx.session_mgr, enc_result.entry,
                        char["room_id"],
                    )
        except Exception as _e:
            # Encounters must never sink a move. Log and continue.
            import logging as _enc_log
            _enc_log.getLogger(__name__).warning(
                "[wilderness] encounter roll failed for char %s: %s",
                char.get("name", "?"), _e,
            )

        # Auto-look
        look_cmd = LookCommand()
        look_ctx = CommandContext(
            session=session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr,
        )
        await look_cmd.execute(look_ctx)

    async def _execute_wilderness_exit(self, ctx, char, edge):
        """Transition character out of wilderness to a hand-built room."""
        session = ctx.session

        # Resolve target room by slug. JSON1 path first; scan fallback if unavailable.
        target_id = None
        try:
            target_rows = await ctx.db._db.execute_fetchall(
                "SELECT id FROM rooms WHERE json_extract(properties, '$.slug') = ? LIMIT 1",
                (edge.room_slug,),
            )
            if target_rows:
                target_id = target_rows[0]["id"]
        except Exception:
            pass  # Falls through to scan

        if target_id is None:
            import json as _exj
            all_rows = await ctx.db._db.execute_fetchall(
                "SELECT id, properties FROM rooms"
            )
            for r in all_rows:
                try:
                    p = _exj.loads(r["properties"] or "{}")
                    if p.get("slug") == edge.room_slug:
                        target_id = r["id"]
                        break
                except Exception:
                    continue

        if target_id is None:
            await session.send_line("You can't go that way — the path is blocked.")
            return

        # Cache old wilderness state for the departure broadcast
        old_slug = char.get("wilderness_region_slug")
        old_x = char.get("wilderness_x")
        old_y = char.get("wilderness_y")

        # Departure broadcast at OLD wilderness tile (source_char still pointing
        # to wilderness coords)
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"{char['name']} departs the area.",
            exclude=ctx.session,
            source_char=char,
        )

        # Clear wilderness state
        char["room_id"] = target_id
        char["wilderness_region_slug"] = None
        char["wilderness_x"] = None
        char["wilderness_y"] = None
        await ctx.db.save_character(
            char["id"],
            room_id=target_id,
            wilderness_region_slug=None,
            wilderness_x=None,
            wilderness_y=None,
        )

        # Self-message: exit message
        if edge.exit_message:
            await session.send_line("")
            await session.send_line(edge.exit_message.strip())

        # Arrival broadcast in the new (normal) room
        await ctx.session_mgr.broadcast_to_room(
            target_id,
            f"{char['name']} arrives from the wastes.",
            exclude=ctx.session,
        )

        # Auto-look (normal room path now)
        look_cmd = LookCommand()
        look_ctx = CommandContext(
            session=session, raw_input="look", command="look",
            args="", args_list=[], db=ctx.db, session_mgr=ctx.session_mgr,
        )
        await look_cmd.execute(look_ctx)


    async def _post_move_hooks(self, ctx, session, char, new_room_id,
                                direction=None, exit_data=None):
        """Post-move effects: lawless warning, hostile NPCs, achievements, barks, tutorial."""
        # ── Zone-entry death-stakes warning (one-time per session, per
        # tier). Drop 2: make the loss explicit. LAWLESS is the hard
        # warning; CONTESTED gets a softer one-time heads-up since a corpse
        # there is also lootable by others. ────────────
        try:
            from engine.security import get_effective_security, SecurityLevel
            _move_sec = await get_effective_security(new_room_id, ctx.db, character=char)
            if _move_sec == SecurityLevel.LAWLESS:
                if not getattr(session, "_lawless_warned", False):
                    session._lawless_warned = True
                    await session.send_line(
                        "\n  \033[1;31m*** WARNING: You are entering LAWLESS territory. ***\033[0m\n"
                        "  \033[1;31m*** Players and NPCs can attack you freely here. ***\033[0m\n"
                        "  \033[1;31m*** Death here means losing everything you carry — \033[0m\n"
                        "  \033[1;31m*** your loose gear drops to a lootable corpse. ***\033[0m\n"
                        "  \033[2mYour equipped weapon stays with you. Higher risk, higher rewards.\033[0m\n"
                    )
            elif _move_sec == SecurityLevel.CONTESTED:
                if not getattr(session, "_contested_warned", False):
                    session._contested_warned = True
                    await session.send_line(
                        "\n  \033[1;33m* Entering CONTESTED territory. *\033[0m\n"
                        "  \033[2mIf you die here, your loose gear drops to a corpse others can loot. "
                        "Carry only what you can afford to lose.\033[0m\n"
                    )
        except Exception:
            log.warning("execute: unhandled exception", exc_info=True)
            pass

        # Check for hostile NPCs in the new room
        await _check_hostile_npcs(ctx, new_room_id)

        # Achievement: room visit tracking (+ Phase-1 bearing substrate:
        # record facing from the move direction so the map chevron points the
        # way the player last walked). Both ride the SAME attributes read-
        # modify-write so a move costs at most one extra DB write, not two.
        try:
            import json as _rvj
            _attrs = char.get("attributes", "{}")
            if isinstance(_attrs, str):
                _attrs = _rvj.loads(_attrs) if _attrs else {}
            _dirty = False
            # Bearing: only planar compass moves set a facing; up/down/in/out/
            # named exits leave the previous bearing intact (a turbolift ride
            # shouldn't spin the marker).
            try:
                from engine.bearing import bearing_for_direction
                _bdir = (exit_data.get("direction") if isinstance(exit_data, dict) else None) or direction
                _bearing = bearing_for_direction(_bdir)
                if _bearing is not None and _attrs.get("bearing") != _bearing:
                    _attrs["bearing"] = _bearing
                    _dirty = True
            except Exception:
                log.warning("MoveCommand: bearing update failed", exc_info=True)
            _visited = set(_attrs.get("rooms_visited", []))
            _new_visit = new_room_id not in _visited
            if _new_visit:
                _visited.add(new_room_id)
                _attrs["rooms_visited"] = list(_visited)
                _dirty = True
            if _dirty:
                char["attributes"] = _rvj.dumps(_attrs)
                await ctx.db.save_character(char["id"], attributes=char["attributes"])
            if _new_visit:
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

                # Village quest room-entry check (F.7.a). Slug-based
                # match against properties.slug (set by world_writer
                # for hand-built rooms and wilderness_writer for
                # landmarks). Step 2: arrival at village_outer_watch.
                try:
                    from engine.village_quest import check_village_quest
                    _vq_slug = ""
                    if isinstance(rprops, dict):
                        _vq_slug = rprops.get("slug", "") or ""
                    await check_village_quest(
                        session, ctx.db, "room_entered",
                        room_id=new_room_id,
                        room_slug=_vq_slug,
                    )
                except Exception as _e:
                    log.debug(
                        "silent except in parser/builtin_commands.py village_quest hook: %s",
                        _e, exc_info=True,
                    )

                # F.8.c.2.b: CW tutorial chain — room_entered completion.
                # Reuses the slug computed above for the village quest
                # hook; hand-built rooms have properties.slug set by
                # world_writer, while legacy rooms without a slug
                # silently no-op (the hook is slug-keyed).
                try:
                    from engine.chain_events import on_room_entered
                    _ce_slug = ""
                    if isinstance(rprops, dict):
                        _ce_slug = rprops.get("slug", "") or ""
                    if _ce_slug:
                        _adv = await on_room_entered(ctx.db, char, _ce_slug)
                        if _adv:
                            from engine.chain_graduation import (
                                execute_pending_teleport,
                            )
                            await execute_pending_teleport(ctx, char)
                except Exception as _e:
                    log.debug(
                        "silent except in parser/builtin_commands.py chain_events hook: %s",
                        _e, exc_info=True,
                    )
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
        # Drop B': broadcast as typed pose_event instead of plain text.
        # Telnet observers still see the formatted line via the
        # send_json("pose_event") Telnet fallback in server/session.py;
        # WebSocket observers get the typed event for handlePoseEvent.
        # Actor is excluded — they already saw the self-echo above.
        from engine.pose_events import make_pose_event, EVENT_SAY
        await ctx.session_mgr.broadcast_json_to_room(
            room_id,
            "pose_event",
            make_pose_event(
                EVENT_SAY,
                ctx.args,
                who=char["name"],
                speaker_id=char.get("id"),
                mode="says",
            ),
            exclude=ctx.session,
            source_char=char,  # W.2 phase 2: wilderness co-location
        )
        # Chat tag for WebSocket comms panel
        await ctx.session_mgr.broadcast_chat(
            "ic", char["name"], ctx.args,
            room_id=room_id,
            source_char=char,  # W.2 phase 2: wilderness co-location
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
            others = [s for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char) or []
                      if s.character and s.character.get("id") != char["id"]]
            if others:
                from engine.achievements import on_pc_conversation
                await on_pc_conversation(ctx.db, char["id"], session=ctx.session)
        except Exception as _e:
            log.debug("silent except in parser/builtin_commands.py:897: %s", _e, exc_info=True)


class WhisperCommand(BaseCommand):
    key = "whisper"
    aliases = ["wh", "tell"]
    help_text = (
        "Private message to someone in the same room (or, in "
        "wilderness, at the same co-located tile). Only you and the "
        "target see it. For cross-room private messaging use `page` "
        "(separate command in mux_commands.py).\n"
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
        speaker = ctx.session.character
        # W.2 phase 2: Path B — sessions_in_room with source_char filters
        # to co-located characters when in wilderness. The whisper target
        # must be at the same wilderness tile, not just somewhere else
        # in the desert.
        room_sessions = ctx.session_mgr.sessions_in_room(room_id, source_char=speaker)
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
        # Drop B': target receives a typed pose_event instead of plain
        # text. Telnet target sees the formatted line via the send_json
        # Telnet fallback; WebSocket target gets the typed event for
        # handlePoseEvent (renders in pose log with whisper styling).
        from engine.pose_events import make_pose_event, EVENT_WHISPER
        speaker_char = ctx.session.character
        target_char_name = target_session.character["name"]
        await target_session.send_json(
            "pose_event",
            make_pose_event(
                EVENT_WHISPER,
                message,
                who=speaker_char["name"],
                speaker_id=speaker_char.get("id"),
                mode="whispers",
                to=target_char_name,
            ),
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

        # Drop B': broadcast as typed pose_event to ALL sessions in the
        # room (including the actor — matches the legacy behavior of the
        # send_line loop, where the actor sees their own pose). Telnet
        # observers and the actor's Telnet self-view both render via the
        # send_json("pose_event") Telnet fallback as 'Tundra <action>';
        # WebSocket clients get the typed event for handlePoseEvent.
        room_id = char["room_id"]
        from engine.pose_events import make_pose_event, EVENT_POSE
        await ctx.session_mgr.broadcast_json_to_room(
            room_id,
            "pose_event",
            make_pose_event(
                EVENT_POSE,
                ctx.args,
                who=char["name"],
                speaker_id=char.get("id"),
                mode="poses",
            ),
            source_char=char,  # W.2 phase 2: wilderness co-location
        )

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
            from engine.titles import worn_title
            for s in in_game:
                name = s.character["name"]
                species = s.character.get("species", "Unknown")
                proto = s.protocol.value.upper()
                wt = worn_title(s.character)
                title_suffix = ("  " + ansi.dim("\u2014 " + wt)) if wt else ""
                await ctx.session.send_line(
                    f"  {ansi.player_name(name):30s} {species:15s} "
                    f"[{proto}]{title_suffix}"
                )
        await ctx.session.send_line(
            f"  {ansi.dim(f'{len(in_game)} player(s) online.')}"
        )
        await ctx.session.send_line("")


class UseCommand(BaseCommand):
    """`use <item>` — activate / consume an inventory item.

    F.8.c.2.b₄ (May 4 2026) closes the last wired-but-inert chain
    hook. The ``on_item_used`` chain dispatcher hook was wired in
    F.8.c.2.b₂ but had no production trigger. With this command,
    chain steps with ``completion: {type: item_used, item: <key>}``
    can advance at runtime.

    Item resolution order:
      1. Exact ``key`` match (case-sensitive)
      2. Exact ``name`` match (case-insensitive)
      3. Single-substring partial-name match (case-insensitive)

    Items may declare an optional ``consumable: true`` flag — if
    set, the item is removed from inventory after use. Items with
    an optional ``use_message`` field replace the default flavor
    line; otherwise a generic "You use the X." is sent.

    Side effect: every successful use fires the ``on_item_used``
    chain hook with the item's ``key``. The chain hook is a no-op
    for non-chain players or chain-active players whose current
    step doesn't match.

    Usage:
        use sealed_data_packet
        use packet            (matches "Sealed Data Packet" partial)
        use Sealed Data Packet
    """
    key = "use"
    aliases = []
    help_text = "Activate or consume an inventory item."
    usage = "use <item-name-or-key>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use items.")
            return

        target = (ctx.args or "").strip()
        if not target:
            await ctx.session.send_line("  Usage: use <item-name-or-key>")
            return

        # ── Fetch inventory ────────────────────────────────────────
        try:
            inv = await ctx.db.get_inventory(char["id"])
        except Exception:
            log.warning("UseCommand: get_inventory failed",
                        exc_info=True)
            await ctx.session.send_line(
                "  You can't access your inventory right now.")
            return

        if not inv:
            await ctx.session.send_line(
                "  You're not carrying anything to use.")
            return

        # ── Resolve target ────────────────────────────────────────
        target_lower = target.lower()
        matched = None

        # Pass 1: exact key match
        for item in inv:
            if not isinstance(item, dict):
                continue
            if item.get("key") == target:
                matched = item
                break

        # Pass 2: exact name match (case-insensitive)
        if matched is None:
            for item in inv:
                if not isinstance(item, dict):
                    continue
                if (item.get("name", "") or "").lower() == target_lower:
                    matched = item
                    break

        # Pass 3: partial name match (must be unique)
        if matched is None:
            partial = []
            for item in inv:
                if not isinstance(item, dict):
                    continue
                name = (item.get("name", "") or "").lower()
                key = (item.get("key", "") or "").lower()
                if target_lower in name or target_lower in key:
                    partial.append(item)
            if len(partial) == 1:
                matched = partial[0]
            elif len(partial) > 1:
                names = [
                    p.get("name") or p.get("key") or "?"
                    for p in partial
                ]
                await ctx.session.send_line(
                    f"  Multiple matches for '{target}': "
                    f"{', '.join(names)}. Be more specific.")
                return

        if matched is None:
            await ctx.session.send_line(
                f"  You don't have anything called '{target}'.")
            return

        # ── Send flavor ────────────────────────────────────────────
        item_key = matched.get("key", "") or ""
        item_name = matched.get("name") or item_key or "the item"
        flavor = matched.get("use_message") or f"You use the {item_name}."
        await ctx.session.send_line(f"  {flavor}")

        # ── Consume if marked consumable ──────────────────────────
        if matched.get("consumable") and item_key:
            try:
                removed = await ctx.db.remove_from_inventory(
                    char["id"], item_key)
                if not removed:
                    log.debug("UseCommand: consumable item %s not "
                              "removed (no matching key in inventory)",
                              item_key)
            except Exception:
                log.warning("UseCommand: remove_from_inventory failed "
                            "for %s", item_key, exc_info=True)
                # Don't fail the use itself; the flavor already sent

        # ── Fire chain hook ───────────────────────────────────────
        if item_key:
            try:
                from engine.chain_events import on_item_used
                _adv = await on_item_used(ctx.db, char, item_key)
                if _adv:
                    # F.8.c.2.c graduation finisher (consistent with
                    # the other chain-hook call sites)
                    from engine.chain_graduation import (
                        execute_pending_teleport,
                    )
                    await execute_pending_teleport(ctx, char)
            except Exception as _e:
                log.debug("UseCommand: chain_events hook error: %s",
                          _e, exc_info=True)

        # ── PG.1.death.b bacta-pack hook (Drop 2d) ─────────────────
        # The bacta_pack is a normal consumable item that *also*
        # clears wound_state. The flavor + consume already happened
        # above; here we just toggle the debuff if the player is
        # wounded. No-op for healthy chars (the pack is spent
        # anyway — single-shot, per design §3.3).
        from engine.death import BACTA_PACK_KEY as _BPK
        if item_key == _BPK:
            try:
                state = char.get("wound_state") or "healthy"
                if state == "wounded":
                    from engine.death import consume_bacta_pack
                    cleared = await consume_bacta_pack(ctx.db, char["id"])
                    if cleared:
                        char["wound_state"] = "healthy"
                        char["wound_clear_at"] = 0.0
                        await ctx.session.send_line(
                            f"  {ansi.BRIGHT_CYAN}Relief floods "
                            f"through you.{ansi.RESET} Your wounds "
                            f"close clean."
                        )
                else:
                    await ctx.session.send_line(
                        "  (You weren't wounded — the pack works "
                        "but the effect is wasted.)"
                    )
            except Exception:
                log.debug(
                    "UseCommand: bacta_pack hook failed for char %s",
                    char.get("id"), exc_info=True,
                )


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

        # ── Equipped items from equipment JSON (tolerant of all shapes) ──────
        from engine.items import equipment_keys
        _eqk = equipment_keys(char.get("equipment", "{}"))
        weapon_key = _eqk["weapon"]
        armor_key  = _eqk["armor"]

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

        # ── WebSocket clients: emit a structured inventory_state for the panel ──
        # (Webify UI-4a) The browser modal renders equipped + carried with
        # per-item condition/quality/value/stats; Telnet falls through to the
        # text dump above. Non-blocking — a push failure never breaks `inventory`.
        from server.session import Protocol
        if ctx.session.protocol == Protocol.WEBSOCKET:
            try:
                from engine.items import build_inventory_state
                payload = build_inventory_state(char.get("equipment", "{}"), inv)
                await ctx.session.send_json("inventory_state", payload)
            except Exception:
                log.debug("InventoryCommand: inventory_state push failed",
                          exc_info=True)


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

        # ── WebSocket clients: emit structured sheet_data event ──
        # The browser slide-in panel renders from this payload — no
        # ANSI parsing, no comms-feed bleed.  Telnet falls through to
        # the text dump below.  /skills, /combat, /brief switches are
        # passed through as `view` so the panel opens on the matching
        # tab; the legacy text variants are no longer sent on WS (the
        # tabs absorb them).
        from server.session import Protocol
        if ctx.session.protocol == Protocol.WEBSOCKET:
            try:
                from engine.sheet_renderer import build_sheet_payload
                # Hydrate background from pc_narrative if available so
                # the right-rail can show it without a second round-trip.
                sheet_char = dict(char)
                try:
                    char_id = sheet_char.get("id")
                    if char_id and ctx.db is not None:
                        row = await ctx.db.fetchone(
                            "SELECT background FROM pc_narrative "
                            "WHERE char_id = ?",
                            (char_id,),
                        )
                        # aiosqlite.Row supports bracket access but not
                        # .get(); guard via keys().
                        if row is not None and "background" in row.keys():
                            bg = row["background"]
                            if bg:
                                sheet_char["background"] = bg
                except Exception as _e:
                    log.debug(
                        "sheet: pc_narrative hydrate skipped: %s", _e,
                        exc_info=True,
                    )
                payload = build_sheet_payload(sheet_char, skill_reg)
                await ctx.session.send_json("sheet_data", {
                    "payload": payload,
                    "view": (
                        "skills" if "skills" in ctx.switches
                        else "combat" if "combat" in ctx.switches
                        else "brief" if "brief" in ctx.switches
                        else "full"
                    ),
                })
                # Refresh the sidebar HUD too — vitals / credits / wound
                # are mirrored there and can drift if the sheet is the
                # only thing that pulled fresh state.
                try:
                    await ctx.session.send_hud_update(
                        db=ctx.db, session_mgr=ctx.session_mgr,
                    )
                except Exception as _e:
                    log.debug(
                        "sheet: HUD refresh skipped: %s", _e, exc_info=True,
                    )
            except Exception as _e:
                # Any failure in the structured path falls back to the
                # ANSI text dump so the user still sees their sheet.
                log.warning("sheet_data emission failed: %s", _e, exc_info=True)
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
    help_text = "Return to life after death. You'll be Wounded — go to a med-droid or wait it out."
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

        # ── PG.1.death (Drop 2c, May 19 2026 evening) ──
        # Per progression_gates_and_consequences_design_v1.md §3.2:
        #   - Credits and bank UNTOUCHED.
        #   - Equipment stayed on the corpse at death-time (the
        #     on_pc_death hook in parser/combat_commands.py already
        #     ran before this command); no extra weapon-condition
        #     penalty.
        #   - wound_state='wounded' was set by on_pc_death; here
        #     we just respawn the body in the safe room.
        # Old behavior (pre-PG.1.death): 10%-of-credits penalty +
        # 20% weapon condition damage. Both removed per design.
        from engine.death import respawn_destination
        respawn_room = await respawn_destination(ctx.db, char["id"])

        old_room_id = char.get("room_id", 1)

        # ── W.2.4 Phase 5: capture pre-respawn wilderness snapshot ──
        # The broadcast to old_room_id below needs Path B
        # filtering to route the "body carried away" line to the
        # right wilderness tile. By the time we reach the
        # broadcasts, char's wilderness coords will have been
        # nulled by the respawn move. Capture the pre-respawn
        # anchor now so we can build a synthetic source_char for
        # the OLD-room broadcast that points at the right tile.
        old_source_char = {
            "room_id": old_room_id,
            "wilderness_region_slug": char.get("wilderness_region_slug"),
            "wilderness_x": char.get("wilderness_x"),
            "wilderness_y": char.get("wilderness_y"),
        }

        # ── Apply respawn ──
        # wound_level resets to HEALTHY on the WEG ladder — the
        # death-roll state is gone; you're a live body again.
        # The −1D debuff comes from wound_state, not wound_level,
        # so the in-combat ladder reset is clean.
        char["wound_level"] = 0  # WoundLevel.HEALTHY
        char["room_id"] = respawn_room
        # Clear wilderness anchor — respawn moves char to a regular room.
        char["wilderness_region_slug"] = None
        char["wilderness_x"] = None
        char["wilderness_y"] = None

        # Persist to DB. Note: credits NOT in this update — they
        # stay untouched. wound_state was already set by on_pc_death.
        await ctx.db.save_character(
            char["id"],
            wound_level=0,
            room_id=respawn_room,
            wilderness_region_slug=None,
            wilderness_x=None,
            wilderness_y=None,
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
            f"  {ansi.dim('\"Patient stable. Vitals weak. Body still recovering.\"')}"
        )
        await ctx.session.send_line("")
        # ── Status callout: Wounded + recovery hint ──
        # The −1D Wounded debuff is real — surface it visibly. Two
        # recovery paths per design §3.3:
        #   (a) wait it out: 1 hour real-time, wound_clear_at handles it
        #   (b) bacta tank at any med-droid: 500cr (PG.1.death.b ships
        #       the vendor)
        await ctx.session.send_line(
            f"  {ansi.BRIGHT_RED}Status: Wounded{ansi.RESET} "
            f"{ansi.dim('(-1D to all rolls until recovered)')}"
        )
        # Show retrieval hint if a corpse exists.
        try:
            corpses = await ctx.db.get_corpses_in_room(old_room_id)
            for cr in corpses:
                if cr.get("char_id") == char["id"]:
                    await ctx.session.send_line(
                        f"  {ansi.dim('Your body, and your gear, are still at the scene.')}"
                    )
                    break
        except Exception:
            log.debug("respawn: corpse-hint lookup failed",
                      exc_info=True)
        await ctx.session.send_line("")

        # Notify old room.
        # W.2.4 Phase 5: source_char is the PRE-RESPAWN snapshot
        # captured above, so the broadcast filters to the wilderness
        # tile char died at (not the regular respawn room).
        char_name = char["name"]
        death_msg = ansi.dim(char_name + "'s body is carried away by medical droids.")
        if old_room_id != respawn_room:
            await ctx.session_mgr.broadcast_to_room(
                old_room_id,
                f"  {death_msg}",
                exclude=ctx.session,
                source_char=old_source_char,
            )

        # Notify new room.
        # W.2.4 Phase 5: source_char is char (which has been moved to
        # the respawn room — a regular, non-wilderness room). In a
        # future world where respawn could land in wilderness, this
        # would key on char's new coords; today the respawn_room is
        # always a regular room (Mos Eisley Landing Pad), so
        # source_char=char is a no-op filter.
        revive_msg = ansi.dim(char_name + " stumbles out of a bacta tank, gasping.")
        await ctx.session_mgr.broadcast_to_room(
            respawn_room,
            f"  {revive_msg}",
            exclude=ctx.session,
            source_char=char,
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


# ─── PG.1.death.b (Drop 2d, May 19 2026 evening) ────────────────────────
#
# Three commands that close the death-penalty loop:
#   loot <name> [item]   — take from a corpse in the room
#   bacta tank           — 500cr immediate heal at a med-droid
#   use bacta_pack       — 150cr consumable, in-place heal
#
# All three honour the design's "credits-untouched" rule on death
# itself; these are explicit player credit sinks for *recovery*,
# which is exactly the economy_design §3.2 mandated credit drain.


class LootCommand(BaseCommand):
    key = "loot"
    aliases = []
    help_text = (
        "Take items from a corpse in the current room.\n"
        "\n"
        "With no item argument, takes EVERYTHING (the body's owner\n"
        "is the typical user). With an item key, takes the first\n"
        "matching item.\n"
        "\n"
        "EXAMPLES:\n"
        "  loot kessa             -- take everything from Kessa's corpse\n"
        "  loot kessa blaster     -- take just the blaster_pistol key"
    )
    usage = "loot <name> [item_key]"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game to loot.")
            return
        if not ctx.args:
            await ctx.session.send_line("  Usage: loot <name> [item_key]")
            return

        parts = ctx.args.strip().split(maxsplit=1)
        target_name = parts[0].lower()
        item_key = parts[1].lower() if len(parts) > 1 else None

        # Find a corpse in this room whose owner-name starts with the
        # target. Owners can be offline, so we look the name up from
        # the characters table rather than session_mgr.
        room_id = char.get("room_id", 0)
        corpses = await ctx.db.get_corpses_in_room(room_id)
        if not corpses:
            await ctx.session.send_line(
                "  There's nothing here to loot."
            )
            return

        # Resolve each corpse's owner name (for matching). Cache one
        # lookup per char_id to avoid hammering get_character on a
        # big pile-up.
        chosen = None
        for cr in corpses:
            try:
                owner = await ctx.db.get_character(cr["char_id"])
            except Exception:
                owner = None
            owner_name = (owner or {}).get("name", "") or ""
            if owner_name.lower().startswith(target_name):
                chosen = (cr, owner_name)
                break
        if chosen is None:
            await ctx.session.send_line(
                f"  No corpse here matching '{target_name}'."
            )
            return
        corpse_row, owner_name = chosen

        if item_key is None:
            # Bulk loot — usually the owner returning to their body.
            from engine.death import loot_all_from_corpse
            moved = await loot_all_from_corpse(
                ctx.db,
                corpse_id=corpse_row["id"],
                looter_id=char["id"],
            )
            if not moved:
                await ctx.session.send_line(
                    f"  {owner_name}'s body has nothing left to take."
                )
                return
            keys = ", ".join(
                str(i.get("key") or i.get("type") or "?")
                for i in moved
            )
            await ctx.session.send_line(
                f"  You take everything from {owner_name}'s body: "
                f"{keys}."
            )
            return

        # Single-item loot.
        from engine.death import loot_corpse_take_item
        taken = await loot_corpse_take_item(
            ctx.db,
            corpse_id=corpse_row["id"],
            looter_id=char["id"],
            item_key=item_key,
        )
        if taken is None:
            await ctx.session.send_line(
                f"  {owner_name}'s body has no '{item_key}'."
            )
            return
        await ctx.session.send_line(
            f"  You take the {item_key} from {owner_name}'s body."
        )


class BactaTankCommand(BaseCommand):
    key = "bacta"
    aliases = []
    help_text = (
        "Pay for a bacta tank treatment at a med-droid.\n"
        "Costs 500 credits and clears Wounded immediately."
    )
    usage = "bacta tank"

    async def execute(self, ctx: CommandContext):
        from engine.death import (
            apply_bacta_tank, BACTA_TANK_PRICE,
        )
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game for treatment."
            )
            return
        args = (ctx.args or "").strip().lower()
        if args not in ("", "tank"):
            await ctx.session.send_line(
                "  Usage: bacta tank   (500cr immediate heal)"
            )
            return

        # Wounded check first — don't charge if no benefit.
        state = char.get("wound_state") or "healthy"
        if state != "wounded":
            await ctx.session.send_line(
                "  You're not wounded. The med-droid politely declines "
                "your business."
            )
            return

        credits = int(char.get("credits", 0))
        if credits < BACTA_TANK_PRICE:
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_RED}Bacta tank costs "
                f"{BACTA_TANK_PRICE} credits — you have {credits:,}."
                f"{ansi.RESET}"
            )
            return

        # Deduct first, then transition. Either-order would work,
        # but charging first means a transient DB blip during
        # apply_bacta_tank doesn't leave the player healed-for-free.
        new_credits = credits - BACTA_TANK_PRICE
        char["credits"] = await ctx.db.adjust_credits(char["id"], -BACTA_TANK_PRICE, "bacta_tank")

        cleared = await apply_bacta_tank(ctx.db, char["id"])
        if cleared:
            char["wound_state"] = "healthy"
            char["wound_clear_at"] = 0.0
            await ctx.session.send_line(
                f"  {ansi.BRIGHT_CYAN}The bacta tank works its slow "
                f"magic.{ansi.RESET} Your wounds knit clean."
            )
            balance_line = (
                f"-{BACTA_TANK_PRICE} credits. "
                f"Balance: {new_credits:,}."
            )
            await ctx.session.send_line(
                f"  {ansi.dim(balance_line)}"
            )
        else:
            # Race: the wound_recovery_tick already cleared. Refund.
            char["credits"] = await ctx.db.adjust_credits(char["id"], BACTA_TANK_PRICE, "bacta_tank_refund")
            await ctx.session.send_line(
                "  The med-droid checks again — you're already healed. "
                "No charge."
            )


class BactaPackUseCommand(BaseCommand):
    """DEPRECATED stub — see UseCommand (Drop 2d hook).

    Drop 2d (May 19 2026 evening) initially shipped a dedicated
    ``BactaPackUseCommand`` for the 150cr Wounded → Healthy
    consumable. During the same drop we discovered the existing
    F.8.c.2.b₄ ``UseCommand`` already handles consumables generically
    via the ``consumable: true`` item flag and fires the chain hook.
    The bacta-pack hook now lives inline in ``UseCommand`` (search
    for "PG.1.death.b bacta-pack hook"), and this class is left as
    a no-op for backwards-compatibility with any code that imported
    it from this module during the drop authoring.

    The class deliberately does NOT set ``key`` so it isn't
    registered against any command keyword. Treat it as removed.
    """

    key = "__bacta_pack_legacy__"  # not a real command keyword
    aliases = []
    help_text = ""
    usage = ""

    async def execute(self, ctx: CommandContext):
        await ctx.session.send_line(
            "  (use bacta_pack now goes through `use` — try that.)"
        )


class QuitCommand(BaseCommand):
    key = "quit"
    aliases = ["@quit", "logout", "QUIT"]
    access_level = AccessLevel.ANYONE
    help_text = "Disconnect from the game."
    usage = "quit"

    async def execute(self, ctx: CommandContext):
        if ctx.session.character:
            char = ctx.session.character
            name = char["name"]
            room_id = char.get("room_id")
            await ctx.db.save_character(
                char["id"],
                room_id=room_id,
            )

            # Flag as sleeping if in a non-safe room (Tier 3 Feature #16)
            if room_id:
                try:
                    from engine.sleeping import set_sleeping
                    sleeping = await set_sleeping(
                        char, ctx.db, room_id)
                    if sleeping:
                        # W.2.3.1: source_char filters to co-located peers
                        # so a PC sleeping at wilderness (12,18) doesn't
                        # broadcast "X falls asleep" to (15,18) etc.
                        await ctx.session_mgr.broadcast_to_room(
                            room_id,
                            ansi.system_msg(
                                f"{name} falls asleep here."),
                            exclude=ctx.session,
                            source_char=char,
                        )
                except Exception:
                    log.warning("QuitCommand: sleeping flag failed", exc_info=True)

            if room_id:
                await ctx.session_mgr.broadcast_to_room(
                    room_id,
                    ansi.system_msg(f"{name} has disconnected."),
                    exclude=ctx.session,
                    source_char=char,  # W.2.3.1: co-located peers only
                )

        await ctx.session.close()


class OocCommand(BaseCommand):
    key = "+ooc"
    aliases = ["@ooc"]
    help_text = (
        "Room-local out-of-character message — visible only to "
        "people in your current room (or co-located wilderness "
        "tile). For galaxy-wide OOC chat, use the plain `ooc` "
        "channel command instead.\n"
        "\n"
        "Display tag: [Local OOC]  (global is [OOC])\n"
    )
    usage = "+ooc <message>"

    async def execute(self, ctx: CommandContext):
        if not ctx.args:
            await ctx.session.send_line("OOC what?")
            return

        char = ctx.session.character
        name = char["name"]
        # Smoke #5 fix: tag local-room OOC distinctly from global ooc.
        # Global ooc (channel_commands.OocCommand) uses `[OOC]`; we use
        # `[Local OOC]` to make scope unambiguous at the receiving end.
        text = f"{ansi.dim(f'[Local OOC] {name}: {ctx.args}')}"

        room_id = char["room_id"]
        # W.2.3.1: source_char filters OOC chatter to co-located peers.
        # In wilderness, "+ooc" should reach the tile you're at, not
        # every PC in the sentinel region.
        for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
            await s.send_line(text)

        # Scene logging hook — captured as OOC, excluded from log render
        from engine.scenes import get_active_scene_id, capture_pose
        scene_id = get_active_scene_id(room_id)
        if scene_id is not None:
            await capture_pose(ctx.db, scene_id, char["id"],
                               char["name"],
                               f"[Local OOC] {name}: {ctx.args}",
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
            from engine.items import read_equipment
            from engine.weapons import get_weapon_registry
            item = read_equipment(ctx.session.character.get("equipment", "{}"))["weapon"]
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

        # CRAFT.P0.9: equip from CARRIED INVENTORY only. The old path
        # minted a fresh vendor-grade ItemInstance straight from the
        # registry — a free, unlogged weapon faucet (no ownership check,
        # no credit cost) that also made crafted/modified instances
        # unequippable (equip conjured a pristine copy instead). Now the
        # carried instance itself moves into the slot, and any displaced
        # weapon returns to inventory — nothing minted, nothing destroyed.
        from engine.weapons import get_weapon_registry
        from engine.items import (
            read_equipment, write_equipment,
            find_carried_gear, carried_to_instance, instance_to_carried,
        )
        wr = get_weapon_registry()
        char = ctx.session.character
        carried = await ctx.db.get_inventory(char["id"])
        idx, gear_dict, weapon = find_carried_gear(
            carried, ctx.args, wr, want_armor=False)
        if weapon is None:
            # Helpful refusal: distinguish "no such weapon" from
            # "exists but you don't own one".
            known = wr.find_by_name(ctx.args.strip())
            if known and not known.is_armor:
                await ctx.session.send_line(
                    f"  You don't have a {known.name}. Buy one from a "
                    f"vendor, craft one, or loot one.")
            elif known and known.is_armor:
                await ctx.session.send_line(
                    f"  {known.name} is armor, not a weapon. Use 'wear'.")
            else:
                await ctx.session.send_line(
                    f"  You aren't carrying a weapon matching "
                    f"'{ctx.args}'. Type 'inventory' to see what you have.")
            return

        item = carried_to_instance(gear_dict)
        if item is None:
            await ctx.session.send_line(
                "  That item is damaged beyond recognition. Contact an admin.")
            return

        # Remove the carried copy, swap any displaced weapon back in.
        await ctx.db.remove_from_inventory(char["id"], item.key)
        _slots = read_equipment(char.get("equipment", "{}"))
        displaced = _slots["weapon"]
        if displaced is not None:
            d_w = wr.get(displaced.key)
            await ctx.db.add_to_inventory(
                char["id"],
                instance_to_carried(
                    displaced, name=(d_w.name if d_w else displaced.key)))
        char["equipment"] = write_equipment(weapon=item, armor=_slots["armor"])
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        crafter = f" (crafted by {item.crafter})" if item.crafter else ""
        await ctx.session.send_line(
            ansi.success(
                f"  You equip your {weapon.name}.{crafter} "
                f"({weapon.damage} damage, skill: {weapon.skill})")
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
        from engine.items import read_equipment, write_equipment
        from engine.weapons import get_weapon_registry

        _slots = read_equipment(ctx.session.character.get("equipment", "{}"))
        item = _slots["weapon"]
        if not item:
            await ctx.session.send_line("  You don't have a weapon equipped.")
            return
        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key

        char = ctx.session.character
        # CRAFT.P0.9: return the instance to carried inventory — the old
        # path cleared the slot and DESTROYED the instance (condition,
        # quality, crafter, experiment state gone).
        from engine.items import instance_to_carried
        await ctx.db.add_to_inventory(
            char["id"], instance_to_carried(item, name=wname))
        # Clear only the weapon slot — preserve worn armor. (The old
        # serialize_equipment(None) wrote "{}" and wiped armor too.)
        char["equipment"] = write_equipment(weapon=None, armor=_slots["armor"])
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
            from engine.items import equipment_keys
            armor_key = equipment_keys(char.get("equipment", "{}"))["armor"]
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

        # CRAFT.P0.9: wear from CARRIED INVENTORY only — the old path
        # minted a fresh vendor-grade instance from the registry (free
        # armor faucet, same hole as `equip`). Displaced armor returns
        # to inventory.
        wr = get_weapon_registry()
        from engine.items import (
            read_equipment, write_equipment,
            find_carried_gear, carried_to_instance, instance_to_carried,
        )
        char = ctx.session.character
        carried = await ctx.db.get_inventory(char["id"])
        idx, gear_dict, armor = find_carried_gear(
            carried, ctx.args, wr, want_armor=True)
        if armor is None:
            known = wr.find_by_name(ctx.args.strip())
            if known and known.is_armor:
                await ctx.session.send_line(
                    f"  You don't have a {known.name}. Buy one from a "
                    f"vendor, craft one, or loot one.")
            elif known:
                await ctx.session.send_line(
                    f"  {known.name} is a weapon, not armor. Use 'equip' instead.")
            else:
                await ctx.session.send_line(
                    f"  You aren't carrying armor matching '{ctx.args}'. "
                    f"Type 'inventory' to see what you have.")
            return

        item = carried_to_instance(gear_dict)
        if item is None:
            await ctx.session.send_line(
                "  That item is damaged beyond recognition. Contact an admin.")
            return

        await ctx.db.remove_from_inventory(char["id"], item.key)
        _slots = read_equipment(char.get("equipment", "{}"))
        displaced = _slots["armor"]
        if displaced is not None:
            d_a = wr.get(displaced.key)
            await ctx.db.add_to_inventory(
                char["id"],
                instance_to_carried(
                    displaced, name=(d_a.name if d_a else displaced.key),
                    gear_type="armor"))
        char["equipment"] = write_equipment(weapon=_slots["weapon"], armor=item)
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
        from engine.items import read_equipment, write_equipment
        _slots = read_equipment(char.get("equipment", "{}"))
        armor_key = _slots["armor"].key if _slots["armor"] else ""
        if not armor_key:
            await ctx.session.send_line("  You're not wearing any armor.")
            return

        wr = get_weapon_registry()
        a = wr.get(armor_key)
        aname = a.name if a else armor_key

        # CRAFT.P0.9: return the worn instance to carried inventory —
        # the old path cleared the slot and destroyed it.
        from engine.items import instance_to_carried
        await ctx.db.add_to_inventory(
            char["id"],
            instance_to_carried(_slots["armor"], name=aname,
                                gear_type="armor"))
        # Clear only the armor slot — preserve the equipped weapon.
        char["equipment"] = write_equipment(weapon=_slots["weapon"], armor=None)
        await ctx.db.save_character(char["id"], equipment=char["equipment"])
        await ctx.session.send_line(ansi.success(f"  You remove your {aname}."))


class RepairCommand(BaseCommand):
    key = "+repair"
    aliases = []
    help_text = "Repair your equipped weapon. Costs credits at NPC shops, or use Technical skill for cheaper."
    usage = "repair"

    async def execute(self, ctx: CommandContext):
        from engine.items import read_equipment, write_equipment
        from engine.weapons import get_weapon_registry

        char = ctx.session.character
        _slots = read_equipment(char.get("equipment", "{}"))
        item = _slots["weapon"]
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
        # Canonical per-slot write — preserve worn armor (the old
        # serialize_equipment(item) clobbered the armor slot).
        char["equipment"] = write_equipment(weapon=item, armor=_slots["armor"])
        # Ledger chokepoint (F1): repair cost as a logged sink.
        char["credits"] = await ctx.db.adjust_credits(char["id"], -cost, "repair")
        await ctx.db.save_character(
            char["id"], equipment=char["equipment"])
        await ctx.session.send_line(
            ansi.success(
                f"  {wname} repaired! {item.condition_bar}  "
                f"({cost:,} credits spent, {char['credits']:,} remaining)"))


# ── Vendor sale helpers (Vendor V1, 2026-06-05) ─────────────────────────────
# Shared by the equipped-weapon sale and the new carried-item sale so both
# price identically and the economy-audit §1.3 craft-refusal guard applies
# uniformly.

# Fields a non-weapon carried item may carry a sale value under. Items with a
# weapons-registry key price off that; items with none of these and no
# registry entry (quest tokens, crafting inputs) are NOT NPC-sellable — they
# go to the vendor-droid market or storage (Vendor V1 DD-1: value-bearing
# only, not a blanket floor, so quest items can't be sold by accident).
_CARRIED_VALUE_FIELDS = ("value", "cost", "base_cost")


def _npc_salvage_price(item, base_cost: int) -> int:
    """Pre-haggle NPC salvage price for an ItemInstance: condition-scaled
    base (25% broken → 50% new), the crafted-quality bonus, and the live
    sell-price world-event multiplier. Identical math to the long-standing
    equipped-weapon path (now shared)."""
    condition_factor = item.condition / max(item.max_condition, 1)
    sale_pct = 0.25 + (condition_factor * 0.25)
    price = max(10, int(base_cost * sale_pct))
    if item.quality >= 80:
        price = int(price * 1.3)
    elif item.quality >= 60:
        price = int(price * 1.15)
    try:
        from engine.world_events import get_world_event_manager
        _m = get_world_event_manager().get_effect("sell_price_mult", 1.0)
        if _m != 1.0:
            price = int(price * _m)
    except Exception:
        log.warning("_npc_salvage_price: world-event mult failed", exc_info=True)
    return price


def _find_carried_item_by_name(items: list, name: str):
    """First carried-item dict whose name (or registry key) matches *name*,
    case-insensitive — exact match first, then a prefix match. Returns the
    dict or None."""
    n = (name or "").strip().lower()
    if not n:
        return None
    for it in items:
        if isinstance(it, dict) and (
            str(it.get("name", "")).lower() == n
            or str(it.get("key", "")).lower() == n
        ):
            return it
    for it in items:
        if isinstance(it, dict) and (
            str(it.get("name", "")).lower().startswith(n)
            or str(it.get("key", "")).lower().startswith(n)
        ):
            return it
    return None


def _resolve_carried_sale(item_dict: dict, wr):
    """Resolve a carried item's NPC sale basis.

    Returns ``(item_instance, base_cost, display_name)``. If the item has no
    resolvable value (not a weapons/armor registry key and no stored value
    field), ``item_instance`` and ``base_cost`` are ``None`` — the vendor
    won't buy it."""
    from engine.items import ItemInstance
    key = str(item_dict.get("key", "") or "")
    name = str(item_dict.get("name", "") or key or "item")
    wd = wr.get(key) if key else None
    if wd is not None:
        # Weapon or armor: full ItemInstance (condition/quality/crafter if
        # present on the dict), priced off the registry cost.
        try:
            inst = ItemInstance.from_dict(item_dict)
        except Exception:
            inst = ItemInstance(key=key)
        return inst, int(getattr(wd, "cost", 0) or 0), (wd.name or name)
    # Non-registry item with an explicit stored value.
    for fld in _CARRIED_VALUE_FIELDS:
        val = item_dict.get(fld)
        if isinstance(val, (int, float)) and val > 0:
            inst = ItemInstance(key=key or name, condition=100,
                                max_condition=100, quality=50)
            return inst, int(val), name
    return None, None, name


class SellCommand(BaseCommand):
    key = "sell"
    aliases = []
    help_text = ("Sell your equipped weapon, or a carried item by name "
                 "(`sell <item>`), to an NPC vendor (25-50% of base value). "
                 "Well-made crafted items are refused — list those on a "
                 "vendor droid.")
    usage = "sell [<item name>]"

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
            # Vendor V1 (2026-06-05): 'sell <item name>' liquidates a carried
            # inventory item to an NPC vendor. The GENERIC words 'weapon' /
            # 'equipped' instead target the equipped weapon (which lives in
            # char['equipment'], NOT inventory['items'], so the carried path
            # can't find it). This keeps Vendor V1's sell-a-named-carried-item
            # semantics while restoring the pre-V1 `sell weapon` UX and the
            # city-tax-on-sale invariant the player-cities tests pin. Bare
            # `sell` (no arg) is the equipped-weapon default handled below.
            if arg_lower not in ("weapon", "equipped", "equipped weapon"):
                return await self._sell_carried_item(ctx, ctx.args.strip())
            # else: fall through to the equipped-weapon sale below.

        from engine.items import read_equipment, write_equipment
        from engine.weapons import get_weapon_registry

        char = ctx.session.character
        # Canonical per-slot read (equipment-instance untangle). The old
        # parse_equipment_json returned None under canonical storage, so
        # selling the equipped weapon always reported "Nothing equipped".
        _slots = read_equipment(char.get("equipment", "{}"))
        item = _slots["weapon"]
        if not item:
            await ctx.session.send_line("  Nothing equipped to sell.")
            return

        wr = get_weapon_registry()
        w = wr.get(item.key)
        wname = w.name if w else item.key
        base_cost = w.cost if w else 500

        # Economy audit v2 §1.3: NPC vendors must not price-support the player
        # crafted-goods market. A well-made player craft is "too good for
        # scrap" — the NPC refuses it, pushing it to the vendor-droid market
        # where it discovers its own floor. Low-quality crafts and all factory
        # items still sell here as salvage.
        from engine.items import npc_refuses_buyback
        if npc_refuses_buyback(item):
            await ctx.session.send_line(
                f"  The vendor turns the {wname} over and hands it back. "
                f"\"Too well-made for scrap — I'd just resell it at a markup. "
                f"List it on a vendor droid; that's where it'll fetch its real "
                f"value.\"")
            return

        # Sale price: condition/quality/world-event salvage (shared helper —
        # identical math now used by the carried-item sale below).
        base_sale_price = _npc_salvage_price(item, base_cost)

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

        # Clear the weapon slot, preserving worn armor. (The old
        # serialize_equipment(None) wrote "{}" and wiped armor too.)
        char["equipment"] = write_equipment(weapon=None, armor=_slots["armor"])
        # Ledger chokepoint (F1): item sale as a logged faucet.
        char["credits"] = await ctx.db.adjust_credits(
            char["id"], sale_price, "item_sale")
        await ctx.db.save_character(
            char["id"], equipment=char["equipment"])

        # ── Player Cities Phase 4b (May 22 2026): city tax ─────────────
        # NPC vendor sale: per Phase 4b design call #2, the player's
        # receipt is unchanged; the city revenue is funded "from thin
        # air" by the NPC vendor system. The transaction value is
        # sale_price (what the NPC paid).
        city_tax_msg = ""
        try:
            from engine.player_cities import apply_city_tax
            city_take, _, city_name = await apply_city_tax(
                ctx.db, char["room_id"], sale_price,
            )
            if city_take > 0:
                city_tax_msg = (
                    f"  \033[2m[{city_take:,}cr city tax to "
                    f"{city_name}]\033[0m"
                )
        except Exception:
            log.warning(
                "execute: city tax hook failed", exc_info=True,
            )

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
        if city_tax_msg:
            await ctx.session.send_line(city_tax_msg)

    async def _sell_carried_item(self, ctx, name: str):
        """Vendor V1: sell a named carried item from ``inventory['items']`` to
        an NPC vendor. Reuses the equipped-weapon salvage math, the §1.3
        craft-refusal guard, the bargain haggle, the city tax, and the ledger
        chokepoint. Items with no resolvable value (quest tokens, crafting
        inputs) are refused rather than floored."""
        import json as _json
        from engine.items import npc_refuses_buyback
        from engine.weapons import get_weapon_registry
        from engine.skill_checks import resolve_bargain_check

        char = ctx.session.character
        try:
            items = await ctx.db.get_inventory(char["id"])
        except Exception:
            log.warning("_sell_carried_item: get_inventory failed", exc_info=True)
            items = []

        item_dict = _find_carried_item_by_name(items or [], name)
        if not item_dict:
            if name.strip().lower() == "armor":
                await ctx.session.send_line(
                    "  You have no carried item by that name. To sell worn "
                    "armor, `unequip armor` first, then `sell <name>`.")
            else:
                await ctx.session.send_line(
                    f"  You're not carrying anything called \"{name}\".")
            return

        wr = get_weapon_registry()
        inst, base_cost, display_name = _resolve_carried_sale(item_dict, wr)
        if inst is None:
            await ctx.session.send_line(
                f"  The vendor has no use for the {display_name}. "
                f"\"Not something I can move — try a vendor droid.\"")
            return

        # §1.3 craft-refusal guard: well-made player crafts go to the droid market.
        if npc_refuses_buyback(inst):
            await ctx.session.send_line(
                f"  The vendor turns the {display_name} over and hands it back. "
                f"\"Too well-made for scrap — list it on a vendor droid.\"")
            return

        try:
            qty = max(1, int(item_dict.get("qty", item_dict.get("quantity", 1))))
        except (TypeError, ValueError):
            qty = 1

        unit_price = _npc_salvage_price(inst, base_cost)

        # Bargain haggle vs the room vendor (same as the equipped path).
        npc_dice, npc_pips = 3, 0
        try:
            npcs = await ctx.db.get_npcs_in_room(char["room_id"])
            for npc in npcs:
                sheet = _json.loads(npc.get("char_sheet_json", "{}"))
                bargain_str = sheet.get("skills", {}).get("bargain", "")
                if bargain_str:
                    from engine.skill_checks import _parse_dice_str
                    npc_dice, npc_pips = _parse_dice_str(bargain_str)
                    break
        except Exception:
            log.warning("_sell_carried_item: vendor bargain lookup failed",
                        exc_info=True)

        haggle = resolve_bargain_check(
            char, unit_price,
            npc_bargain_dice=npc_dice, npc_bargain_pips=npc_pips,
            is_buying=False,
        )
        sale_price = haggle["adjusted_price"] * qty

        # Remove the item (whole dict) from inventory, then credit through the
        # ledger chokepoint. (Stacks sell whole for V1; per-unit selling is a
        # documented follow-up.)
        try:
            removed = await ctx.db.remove_from_inventory(
                char["id"], str(item_dict.get("key", "")))
        except Exception:
            log.warning("_sell_carried_item: remove_from_inventory failed",
                        exc_info=True)
            removed = False
        if not removed:
            await ctx.session.send_line(
                "  Something went wrong removing that item from your pack.")
            return

        char["credits"] = await ctx.db.adjust_credits(
            char["id"], sale_price, "item_sale")

        # City tax (funded from thin air; player receipt unchanged).
        city_tax_msg = ""
        try:
            from engine.player_cities import apply_city_tax
            city_take, _, city_name = await apply_city_tax(
                ctx.db, char["room_id"], sale_price)
            if city_take > 0:
                city_tax_msg = (f"  \033[2m[{city_take:,}cr city tax to "
                                f"{city_name}]\033[0m")
        except Exception:
            log.warning("_sell_carried_item: city tax hook failed", exc_info=True)

        pct = haggle.get("price_modifier_pct", 0)
        if pct:
            direction = "bonus" if pct > 0 else "penalty"
            await ctx.session.send_line(
                f"  {ansi.DIM}Bargain {haggle['player_pool']}: "
                f"{haggle['player_roll']} vs vendor {haggle['npc_pool']}: "
                f"{haggle['npc_roll']} → {abs(pct)}% {direction}{ansi.RESET}")
        await ctx.session.send_line(haggle["message"])
        qty_str = f"{qty}x " if qty > 1 else ""
        await ctx.session.send_line(ansi.success(
            f"  Sold {qty_str}{display_name} for {sale_price:,} credits. "
            f"Balance: {char['credits']:,} credits."))
        if city_tax_msg:
            await ctx.session.send_line(city_tax_msg)


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
            # segmentation a: the cost column is the SHOP signal — only
            # vendor_stocked rows show a price; the rest read "craft"
            # (the list stays a full stats reference either way).
            if getattr(w, "vendor_stocked", False) and w.cost:
                cost_str = f"{w.cost:,}cr"
            else:
                cost_str = "craft"
            await ctx.session.send_line(
                f"  {w.name:<22s} {w.damage:>6s}  {w.skill:<14s} {ranges}  {cost_str:>8s}"
            )

        # Show currently equipped with condition (canonical per-slot read)
        from engine.items import read_equipment
        item = read_equipment(
            ctx.session.character.get("equipment", "{}"))["weapon"]
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

        # Show currently worn (canonical per-slot read; the old raw
        # equip.get("armor") returned an instance dict under canonical
        # storage, not a key)
        char = ctx.session.character
        from engine.items import equipment_keys
        armor_key = equipment_keys(char.get("equipment", "{}"))["armor"]
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
        # W.2.3.1: source_char filters semipose to co-located peers.
        for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
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
        "  Secured zone:   Impossible (heavy security seals)\n"
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
            # W.2.3.1: source_char filters to co-located peers so a
            # pickpocket fumble at wilderness (12,18) doesn't alert PCs
            # at (15,18).
            await ctx.session_mgr.broadcast_to_room(
                room_id, result["room_msg"],
                exclude=ctx.session,
                source_char=char,
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


class CoordsCommand(BaseCommand):
    """Show wilderness coordinates and region info.

    Per W.2 phase 2: small comfort command for players in wilderness.
    """
    key = "coords"
    aliases = ["coordinates"]
    help_text = (
        "Show your wilderness coordinates.\n"
        "Only meaningful while you're in a wilderness region.\n"
        "Use 'look' for full tile information including terrain and exits."
    )
    usage = "coords"

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            return
        try:
            from engine.wilderness_movement import (
                in_wilderness, get_wilderness_coords, get_or_load_region,
            )
        except Exception:
            await session.send_line("Coordinates are unavailable.")
            return

        if not in_wilderness(char):
            await session.send_line(
                "You're not in a wilderness region. Use 'look' to see your surroundings."
            )
            return

        coords = get_wilderness_coords(char)
        if coords is None:
            await session.send_line("Your wilderness state is inconsistent.")
            return
        slug, x, y = coords

        region = await get_or_load_region(ctx.db, slug)
        region_name = region.name if region else slug
        await session.send_line(
            f"  \033[1;33m{region_name}\033[0m — coordinates "
            f"\033[1;36m({x}, {y})\033[0m"
        )
        if region is not None:
            await session.send_line(
                f"  \033[2mRegion bounds: 0..{region.grid_width-1} x 0..{region.grid_height-1}\033[0m"
            )


# ── DIFF.2: +threat / threat — zoned difficulty band ────────────────────────

class ThreatCommand(BaseCommand):
    """Show the current area's threat band (zoned difficulty).

    Per difficulty_tiers_design_v1.md §8/§11. The band is orthogonal to
    security: security says whether combat/PvP is allowed here, the
    threat band says how dangerous the hostiles are. The band is also
    shown in the `look` room header (off-default bands only), so this is
    the dedicated "tell me more" surface.
    """
    key = "+threat"
    aliases = ["threat"]
    help_text = (
        "Show how dangerous the current area is — its THREAT BAND.\n\n"
        "Difficulty is separate from security: a Lawless zone can still\n"
        "be a Frontier (newbie) area, and a Secured city can be deep in\n"
        "the Deep Wilds. The band tells you how tough the hostiles are.\n\n"
        "Bands (low to high): Frontier, Settled, Contested Marches,\n"
        "Deep Wilds. The band also appears in the room header on `look`."
    )
    usage = "+threat"

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            return
        try:
            from engine.threat_band import (
                get_effective_threat, threat_name, threat_blurb,
                threat_color_code,
            )
            band = await get_effective_threat(char["room_id"], ctx.db)
        except Exception:
            await session.send_line("  Threat information is unavailable here.")
            return
        color = threat_color_code(band)
        await session.send_line(
            f"  Threat band: {color}{threat_name(band)}\033[0m "
            f"(level {band.rating}/4)")
        await session.send_line(f"  \033[2m{threat_blurb(band)}\033[0m")


# ── Lane E2b: +weather / +time ──────────────────────────────────────────────

def _storm_pips_to_dice(pips: int) -> str:
    """Render a negative pip penalty as a D6 die count, e.g. -3 -> '-1D',
    -6 -> '-2D', -9 -> '-3D'; partials as '-ND+r' / '-r pip(s)'."""
    n = -int(pips)
    d, r = divmod(n, 3)
    if d and not r:
        return f"-{d}D"
    if d and r:
        return f"-{d}D+{r}"
    return f"-{r} pip" + ("s" if r != 1 else "")


class WeatherCommand(BaseCommand):
    """Show the local time-of-day (in the planet's idiom where one exists) and
    any active weather. The clock idiom comes from the room's inherited
    `time_vocab` zone property (or the wilderness region's planet); active storms
    come from the world-event manager. Both platforms; no renderer dependency."""
    key = "+weather"
    aliases = ["+time", "weather"]
    help_text = (
        "Show the local time of day and any active weather.\n"
        "On Tatooine the clock reads in the local idiom (First Dawn, High Noon, "
        "Second Twilight, ...). Active sandstorms / gravel storms / sandwhirls are "
        "listed with their effect on Perception and ranged fire."
    )
    usage = "+weather"

    async def execute(self, ctx: CommandContext):
        session = ctx.session
        char = session.character
        if not char:
            await session.send_line("You must be in the game to check the weather.")
            return

        # Resolve the local clock idiom (planet vocab). Wilderness tiles derive it
        # from the region's planet (their sentinel room isn't in a planet zone);
        # everything else uses the room->zone `time_vocab` property zone-walk.
        vocab = None
        room_id = char.get("room_id")
        try:
            from engine.wilderness_movement import (
                in_wilderness, get_wilderness_coords, get_or_load_region,
            )
            if in_wilderness(char) and ctx.db is not None:
                coords = get_wilderness_coords(char)
                if coords:
                    region = await get_or_load_region(ctx.db, coords[0])
                    if region is not None:
                        vocab = getattr(region, "planet", None)
        except Exception:
            vocab = None
        if vocab is None and ctx.db is not None and room_id:
            try:
                vocab = await ctx.db.get_room_property(room_id, "time_vocab")
            except Exception:
                vocab = None

        from engine.world_time import resolve_period_label
        period = resolve_period_label(vocab)

        lines = [ansi.header("=== Local Conditions ===")]
        lines.append(f"  {ansi.cyan('Time:')}    {period}")

        # Active weather events (sandstorm / gravel_storm / sandwhirl).
        try:
            from engine.world_events import get_world_event_manager
            active = get_world_event_manager().get_status()
        except Exception:
            active = []
        _WEATHER = {"sandstorm", "gravel_storm", "sandwhirl", "flood"}
        storms = [e for e in active if e.get("type") in _WEATHER]
        if storms:
            for e in storms:
                eff = e.get("effects", {}) or {}
                bits = []
                if eff.get("perception_penalty"):
                    bits.append(f"Perception {_storm_pips_to_dice(eff['perception_penalty'])}")
                if eff.get("ranged_penalty"):
                    bits.append(f"ranged fire {_storm_pips_to_dice(eff['ranged_penalty'])}")
                effstr = ("  " + ansi.dim("\u2014 " + ", ".join(bits))) if bits else ""
                rem = e.get("remaining_minutes", 0)
                lines.append(
                    f"  {ansi.cyan('Weather:')} {e.get('name', e.get('type'))}{effstr}"
                    f"  {ansi.dim(f'(~{rem}m remaining)')}"
                )
        else:
            lines.append(f"  {ansi.cyan('Weather:')} Clear.")

        await session.send_line("\n".join(lines))


class GiveCommand(BaseCommand):
    """``give <item> to <player-or-NPC>`` — one-way item hand-off.

    Distinct from ``trade`` (two-party, consented, 5%-taxed exchange):
    ``give`` is an immediate, one-way ITEM transfer to a character or
    NPC in the same room.

    Credits deliberately route through ``trade`` instead. A one-way
    untaxed credit ``give`` would bypass both the trade 5% sink and the
    consent gate — a mule/laundering channel — so ``give ... credits``
    redirects the player to ``trade``.

      give <item> to <player>  → the item moves to that PC at once.
      give <item> to <npc>     → you hand the item over; the NPC
                                 accepts it (quests that watch for a
                                 hand-off, e.g. the Smuggler chain's
                                 "give crate to Dyn", advance via the
                                 standard command hook).

    Anti-dupe ordering: the item is removed from the giver FIRST; only
    then is it added to a PC recipient. If that add fails it is rolled
    back to the giver (lose-nothing), never duplicated.
    """
    key = "give"
    aliases = ["hand"]
    help_text = (
        "Give an inventory item to another player or an NPC in the "
        "room.\n"
        "\n"
        "USAGE:\n"
        "  give <item> to <player>   — hand an item to another player\n"
        "  give <item> to <npc>      — hand an item to an NPC (quests)\n"
        "\n"
        "Both of you must be in the same room. To move CREDITS, use "
        "`trade` —\n"
        "credit transfers are consented and taxed; `give` is for "
        "items only.\n"
        "\n"
        "EXAMPLES:\n"
        "  give sealed cargo crate to Dyn\n"
        "  give blaster to Tundra"
    )
    usage = "give <item> to <player or NPC>"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to give things.")
            return

        args = (ctx.args or "").strip()
        if not args:
            await ctx.session.send_line(
                "  Usage: give <item> to <player or NPC>")
            return

        # ── Parse "<item> to <target>" ──────────────────────────────
        low = args.lower()
        if " to " in low:
            idx = low.rfind(" to ")
            item_part = args[:idx].strip()
            target_part = args[idx + 4:].strip()
        else:
            # Friendly fallback: last token is the target, the rest is
            # the item. (`give crate Dyn` works; `give crate` does not.)
            toks = args.split()
            if len(toks) < 2:
                await ctx.session.send_line(
                    "  Give what to whom? "
                    "Usage: give <item> to <player or NPC>")
                return
            target_part = toks[-1]
            item_part = " ".join(toks[:-1])

        if not item_part or not target_part:
            await ctx.session.send_line(
                "  Usage: give <item> to <player or NPC>")
            return

        # ── Credits route through `trade` (consented + taxed sink) ──
        ip_tokens = item_part.lower().split()
        looks_like_credits = (
            (ip_tokens and ip_tokens[0].lstrip("+").isdigit())
            or any(t in ("credit", "credits", "cred", "creds", "cr")
                   for t in ip_tokens)
        )
        if looks_like_credits:
            await ctx.session.send_line(
                "  To transfer credits, use "
                f"{ansi.cyan('trade <player> <amount> credits')} — it's "
                "consented and taxed. `give` is for items only.")
            return

        # ── Self-give guard (own name / me / self) ──────────────────
        # match_in_room only resolves self via the "me"/"self" tokens,
        # never by the player's own name — so catch both here for a
        # clear message instead of a misleading "you don't see".
        if target_part.lower() in ("me", "self", "myself") or \
                target_part.lower() == (char.get("name") or "").lower():
            await ctx.session.send_line(
                "  You can't give something to yourself.")
            return

        # ── Resolve the target (a PC or NPC in the room) ────────────
        from engine.matching import match_in_room
        match = await match_in_room(
            target_part, char["room_id"], char["id"], ctx.db,
            session_mgr=ctx.session_mgr, source_char=char,
        )
        if not match.found:
            await ctx.session.send_line(
                f"  {match.error_message(target_part)}")
            return
        cand = match.candidate
        if cand.obj_type not in ("character", "npc"):
            await ctx.session.send_line(
                f"  You can't give things to {cand.name}.")
            return
        if cand.obj_type == "character" and cand.id == char["id"]:
            await ctx.session.send_line(
                "  You can't give something to yourself.")
            return

        # ── Resolve the item in the giver's inventory (3-pass) ──────
        try:
            inv = await ctx.db.get_inventory(char["id"])
        except Exception:
            log.warning("GiveCommand: get_inventory failed", exc_info=True)
            await ctx.session.send_line(
                "  You can't access your inventory right now.")
            return
        if not inv:
            await ctx.session.send_line(
                "  You're not carrying anything to give.")
            return

        matched = self._resolve_item(inv, item_part)
        if matched == "AMBIGUOUS":
            await ctx.session.send_line(
                f"  You're carrying more than one thing like "
                f"'{item_part}'. Be more specific.")
            return
        if matched is None:
            await ctx.session.send_line(
                f"  You don't have anything called '{item_part}'.")
            return

        item_key = matched.get("key", "") or ""
        item_name = matched.get("name") or item_key or "the item"
        if not item_key:
            # remove_from_inventory keys off `key`; a keyless item can't
            # be cleanly transferred.
            await ctx.session.send_line(
                f"  You can't give the {item_name} away.")
            return

        target_name = cand.name

        # ── Remove from the giver FIRST (lose-not-dupe ordering) ────
        try:
            removed = await ctx.db.remove_from_inventory(
                char["id"], item_key)
        except Exception:
            log.warning("GiveCommand: remove_from_inventory failed for "
                        "%s", item_key, exc_info=True)
            await ctx.session.send_line(
                "  Something went wrong handing that over.")
            return
        if not removed:
            await ctx.session.send_line(
                f"  You don't have a {item_name} to give.")
            return

        # ── NPC hand-off: the NPC accepts the item (consumed) ───────
        if cand.obj_type == "npc":
            await ctx.session.send_line(
                f"  You hand the {item_name} to {target_name}.")
            try:
                await ctx.session_mgr.broadcast_to_room(
                    char["room_id"],
                    f"{char['name']} hands something to {target_name}.",
                    exclude=[char["id"]], source_char=char,
                )
            except Exception:
                log.debug("GiveCommand: npc room broadcast failed",
                          exc_info=True)
            # The post-execute on_command_executed hook (parser/
            # commands.py) advances any chain step whose completion /
            # requires_first is `give <item> to <npc>` — nothing to do
            # here.
            return

        # ── PC recipient: add to their inventory, rollback on failure ──
        try:
            await ctx.db.add_to_inventory(cand.id, matched)
        except Exception:
            log.warning("GiveCommand: add_to_inventory to char %s "
                        "failed; rolling back to giver %s",
                        cand.id, char["id"], exc_info=True)
            try:
                # fire_chain_hook=False: a compensating re-add, not a
                # genuine acquisition — must not advance the giver's
                # chain on an item_acquired step.
                await ctx.db.add_to_inventory(
                    char["id"], matched, fire_chain_hook=False)
            except Exception:
                log.error("GiveCommand: ROLLBACK re-add failed — item "
                          "%s lost from char %s", item_key, char["id"],
                          exc_info=True)
            await ctx.session.send_line(
                f"  You couldn't give the {item_name} to {target_name}.")
            return

        await ctx.session.send_line(
            f"  You give the {item_name} to "
            f"{ansi.player_name(target_name)}.")

        # Notify the recipient if they're present in the room.
        try:
            for s in ctx.session_mgr.sessions_in_room(
                    char["room_id"], source_char=char):
                if s.character and s.character.get("id") == cand.id:
                    await s.send_line(
                        f"  {ansi.player_name(char['name'])} gives you "
                        f"the {item_name}.")
                    break
        except Exception:
            log.debug("GiveCommand: recipient notify failed",
                      exc_info=True)

        # Room broadcast (everyone but giver + recipient).
        try:
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                f"{char['name']} gives something to {target_name}.",
                exclude=[char["id"], cand.id], source_char=char,
            )
        except Exception:
            log.debug("GiveCommand: pc room broadcast failed",
                      exc_info=True)

    @staticmethod
    def _resolve_item(inv: list, target: str):
        """3-pass inventory match (mirrors UseCommand): exact key →
        exact name (ci) → unique partial. Returns the item dict, None
        (no match), or the sentinel "AMBIGUOUS"."""
        target_lower = target.lower()
        # Pass 1: exact key
        for item in inv:
            if isinstance(item, dict) and item.get("key") == target:
                return item
        # Pass 2: exact name (case-insensitive)
        for item in inv:
            if isinstance(item, dict) and \
                    (item.get("name", "") or "").lower() == target_lower:
                return item
        # Pass 3: unique partial on name or key
        partial = []
        for item in inv:
            if not isinstance(item, dict):
                continue
            name = (item.get("name", "") or "").lower()
            key = (item.get("key", "") or "").lower()
            if target_lower in name or target_lower in key:
                partial.append(item)
        if len(partial) == 1:
            return partial[0]
        if len(partial) > 1:
            return "AMBIGUOUS"
        return None


def register_all(registry):
    """Register all built-in commands with the registry."""
    commands = [
        LookCommand(),
        MoveCommand(),
        CoordsCommand(),
        PicklockCommand(),
        ForceDoorCommand(),
        StealCommand(),
        PickpocketCommand(),
        SayCommand(),
        WhisperCommand(),
        EmoteCommand(),
        WhoCommand(),
        WeatherCommand(),
        InventoryCommand(),
        UseCommand(),
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
        # ── PG.1.death.b (Drop 2d): loot + bacta tank ──
        # `use bacta_pack` flows through the existing UseCommand
        # (above) which now carries the wound_state-clearing hook;
        # no separate BactaPackUseCommand needed.
        LootCommand(),
        BactaTankCommand(),
        SemiposeCommand(),
        TradeCommand(),
        GiveCommand(),
        ThinkCommand(),
        BuffsCommand(),
        # DIFF.2 (2026-06-13): zoned-difficulty surface.
        ThreatCommand(),
    ]
    for cmd in commands:
        registry.register(cmd)

# ── Trade (player-to-player) ───────────────────────────────────────────────────

import time as _trade_time

# Pending trade offers: {(offerer_id, target_id): {offer_dict, timestamp}}
_pending_trades: dict = {}
_TRADE_TTL = 120  # 2 minutes

# ── S51 economy hardening: daily P2P transfer cap ──────────────────────────
# Caps how many credits one character may *send* via the trade command in any
# rolling 24-hour window. Tuned per the economy audit (v1) — 5,000 cr/day is
# enough for legitimate gifts and small payments while making large alt-farming
# transfers visible (and ultimately blocked). The window is rolling, not
# calendar-bound, so a player can't dodge by waiting for midnight UTC.
# Audit v2 §2.4: 1,500 cr/day — a meal-out gift, not a salary. The old 5,000
# let seven alts wire ~35,000/day to a main *through* the cap. This targets
# UNATTRIBUTED p2p flow only: vendor-droid purchases and faction-treasury
# contributions route through their own commands/ledger tags (not
# get_daily_p2p_outgoing), so they are inherently exempt and uncapped — a player
# selling to a friend lists on a vendor droid, a backer funds the faction
# treasury. Tunable in one place.
# contributions route through their own commands/ledger tags (not
# get_daily_p2p_outgoing), so they are inherently exempt and uncapped — a player
# selling to a friend lists on a vendor droid, a backer funds the faction
# treasury. Tunable in one place.
#
# ECON.p2p_cap_review = a (2026-06-11): the S51/audit-v2 HARD CAP
# (P2P_DAILY_CAP = 1,500) is REMOVED — vendor segmentation (a) makes
# crafters the supply chain, and a single quality item legitimately
# trades above the old cap. What survives: the 5% tax (p2p_tax sink),
# the p2p_transfer ledger tag, the alt-trade block, and this rolling
# window — now feeding a fail-open VELOCITY ALERT
# (engine.economy_alerts.evaluate_p2p_velocity_alert, thresholds live
# there) instead of a block. Nothing in the trade path refuses on volume.
P2P_DAILY_WINDOW_SECONDS  = 86_400  # 24 hours


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
        DEMAND_POOL, flush_market_pools,
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
    # Apply demand depression to the sell price (economy audit v2 §1.5 latent
    # fix): a saturated market pays less per ton. Previously this passed the
    # base price and the depression mechanic was inert in production despite the
    # price-list display advertising it.
    base_price = get_planet_price(good, planet, include_demand_depression=True)

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
    await ctx.db.adjust_credits(char["id"], total_revenue, "trade_goods")

    # Record the sale so demand depresses for the next seller, and persist both
    # pools (economy audit v2 §1.5). Without this, depression never accumulated
    # — the audit-praised round-trip profit ceiling was dead in production.
    if planet:
        DEMAND_POOL.record_sale(planet, good.key, quantity)
        try:
            await flush_market_pools(ctx.db)
        except Exception:
            log.debug("sell-cargo market-state flush failed", exc_info=True)

    # ── Player Cities Phase 4b (May 22 2026): city tax ──────────────────
    # Planet-market cargo sell at a spaceport. Per Phase 4b design call
    # #2, player's receipt is unchanged; city revenue funded by the
    # NPC vendor system. Mostly a no-op since spaceport rooms aren't
    # usually in player cities — but if a player city has expanded to
    # include a spaceport room, the tax fires correctly.
    city_tax_msg = ""
    try:
        from engine.player_cities import apply_city_tax
        city_take, _, city_name = await apply_city_tax(
            ctx.db, char["room_id"], total_revenue,
        )
        if city_take > 0:
            city_tax_msg = (
                f"  \033[2m[{city_take:,}cr city tax to "
                f"{city_name}]\033[0m"
            )
    except Exception:
        log.warning(
            "_handle_sell_cargo: city tax hook failed", exc_info=True,
        )

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
    if city_tax_msg:
        await ctx.session.send_line(city_tax_msg)


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
            for s in ctx.session_mgr.sessions_in_room(char["room_id"], source_char=char):
                if (s.character and
                        s.character["name"].lower().startswith(target_name.lower()) and
                        s.character["id"] != char["id"]):
                    target_sess = s
                    break

            if not target_sess:
                await ctx.session.send_line(f"  '{target_name}' isn't here.")
                return

            target = target_sess.character

            # ── Self-trade alt block (S44) — item path ────────────────────
            # Block trades between two characters on the same account.
            # Compare account_id values, guarding for None (web sessions
            # may have an unset account in tests). We deliberately
            # re-fetch both sides every time so a stale session doesn't
            # leak a free transfer between alternate characters.
            own_account = (
                ctx.session.account["id"] if ctx.session.account else None
            )
            tgt_account = (
                target_sess.account["id"] if target_sess.account else None
            )
            if own_account is not None and own_account == tgt_account:
                await ctx.session.send_line(
                    "  \033[1;31m[TRADE BLOCKED]\033[0m You cannot trade "
                    "between alternate characters on the same account. "
                    "Items must be earned, not handed off to your alts."
                )
                return

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
        for s in ctx.session_mgr.sessions_in_room(char["room_id"], source_char=char):
            if (s.character and
                    s.character["name"].lower().startswith(target_name.lower()) and
                    s.character["id"] != char["id"]):
                target_sess = s
                break

        if not target_sess:
            await ctx.session.send_line(f"  '{target_name}' isn't here.")
            return

        target = target_sess.character

        # ── Self-trade alt block (S44) — credit path ──────────────────────
        # Same guard as the item path: refuse credit transfers between
        # two characters on the same account. own_account == tgt_account
        # appears here intentionally a second time (the test count locks
        # in that the check runs on BOTH paths, not just one).
        own_account = (
            ctx.session.account["id"] if ctx.session.account else None
        )
        tgt_account = (
            target_sess.account["id"] if target_sess.account else None
        )
        if own_account is not None and own_account == tgt_account:
            await ctx.session.send_line(
                "  \033[1;31m[TRADE BLOCKED]\033[0m You cannot trade "
                "credits between alternate characters on the same account."
            )
            return

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
            # W.2.3.1: source_char filters to co-located peers. Trades
            # are mutually consensual so both parties are at the same
            # tile by construction (same room_id + same coords).
            await ctx.session_mgr.broadcast_to_room(
                char["room_id"],
                f"  {offerer['name']} hands {item_name} to {char['name']}.",
                exclude=[offerer["id"], char["id"]],
                source_char=char,
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

        offerer["credits"] = await ctx.db.adjust_credits(offerer["id"], -amount, "p2p_transfer")
        char["credits"] = await ctx.db.adjust_credits(char["id"], received, "p2p_transfer")
        await ctx.db.adjust_credits(0, -tax, "p2p_tax")

        # ── P2P velocity alert (ECON.p2p_cap_review = a, 2026-06-11) ─────
        # The old hard cap's threshold, repurposed as fail-open telemetry:
        # read the sender's rolling 24h outgoing (now including this
        # trade) and record an @economy alert on a band breach. NEVER
        # blocks — a telemetry failure must not disturb a completed trade
        # (mirrors the faucet throttle's fail-open posture).
        try:
            from engine.economy_alerts import (
                evaluate_p2p_velocity_alert, record_alert,
                format_alert_line,
            )
            rolling = await ctx.db.get_daily_p2p_outgoing(
                offerer["id"], seconds=P2P_DAILY_WINDOW_SECONDS,
            )
            alert = evaluate_p2p_velocity_alert(
                offerer["name"], offerer["id"], char["name"],
                rolling, amount=amount,
            )
            if alert:
                record_alert(alert)
                log.info("p2p velocity alert: %s", format_alert_line(alert))
        except Exception:
            log.debug("p2p velocity alert failed (trade unaffected)",
                      exc_info=True)

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
        # W.2.3.1: source_char filters to co-located peers.
        await ctx.session_mgr.broadcast_to_room(
            char["room_id"],
            f"  {offerer['name']} and {char['name']} exchange credits.",
            exclude=[offerer["id"], char["id"]],
            source_char=char,
        )

        # Credit movements (offerer debit, receiver credit, 5% tax to the
        # system sink) are recorded via adjust_credits at the transfer site.

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
