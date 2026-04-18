# -*- coding: utf-8 -*-
"""
parser/housing_commands.py — Player Housing commands.  [v21 Drop 1]

Commands:
  housing / home       — show housing status or go home
  housing rent <id>   — rent a Tier 1 room
  housing checkout     — vacate rented room
  housing storage      — view storage contents
  housing store <item> — store item in home
  housing retrieve <item> — retrieve item from storage
  sethome              — set current room as home (if it's your housing)
  @housing             — admin commands

All housing state mutations go through engine/housing.py functions.
"""

from __future__ import annotations
import json
import logging

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# ── Main housing command ───────────────────────────────────────────────────────

class HousingCommand(BaseCommand):
    key = "housing"
    # S58 — `home` alias moved to the HomeUmbrellaCommand umbrella so
    # bare `home` routes via the umbrella's /view default (preserves
    # pre-S58 UX while freeing up the `+home` canonical key).
    aliases = ["myroom", "homelocation"]
    help_text = (
        "Manage your housing or go home.\n"
        "\n"
        "  housing              — show status and available locations\n"
        "  housing rent <id>    — rent a Tier 1 room at location <id>\n"
        "  housing checkout     — vacate your rented room (deposit returned)\n"
        "  housing storage      — list items in home storage\n"
        "  housing store <item> — store an item from inventory\n"
        "  housing retrieve <item> — take an item from storage\n"
        "\n"
        "Use 'home' (no args) to teleport to your home room."
    )
    usage = "housing [sub] [args]  |  home"

    async def execute(self, ctx: CommandContext):
        """Dispatch to sub-command handlers. Phase 3 C4 refactor."""
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(ansi.error("Not logged in."))
            return

        from engine.housing import (
            get_housing, get_housing_status_lines,
            rent_room, checkout_room,
            housing_store, housing_retrieve,
            _storage,
        )

        # 'home' with no args → teleport
        raw = (ctx.raw_input or "").strip().lower()
        if raw in ("home",):
            await self._go_home(ctx, char)
            return

        parts = (ctx.args or "").split(None, 1)
        sub   = parts[0].lower() if parts else ""
        rest  = parts[1].strip() if len(parts) > 1 else ""

        # ── housing (no sub) ──

        if not sub:
            return await self._cmd_status(ctx, char, rest)

        _dispatch = {
            "rent": self._cmd_rent,
            "checkout": self._cmd_checkout,
            "storage": self._cmd_storage,
            "store": self._cmd_store,
            "retrieve": self._cmd_retrieve,
            "name": self._cmd_name,
            "describe": self._cmd_describe,
            "trophy": self._cmd_trophy,
            "untrophy": self._cmd_untrophy,
            "trophies": self._cmd_trophies,
            "buy": self._cmd_buy,
            "shopfront": self._cmd_shopfront,
            "sell": self._cmd_sell,
            "guest": self._cmd_guest,
            "intrusions": self._cmd_intrusions,
            "visit": self._cmd_visit,
        }
        handler = _dispatch.get(sub)
        if handler:
            return await handler(ctx, char, rest)

        await ctx.session.send_line(f"  Unknown subcommand '{sub}'.")

    async def _cmd_status(self, ctx, char, rest):
        lines = await get_housing_status_lines(ctx.db, char)
        for line in lines:
            await ctx.session.send_line(line)
        try:
            from engine.spacer_quest import check_spacer_quest
            await check_spacer_quest(ctx.session, ctx.db, "use_command", command="housing")
        except Exception as _e:
            log.debug("silent except in parser/housing_commands.py:78: %s", _e, exc_info=True)
        return

        # ── housing rent <id> ──

    async def _cmd_rent(self, ctx, char, rest):
        if not rest.isdigit():
            await ctx.session.send_line(
                "  Usage: housing rent <location id>\n"
                "  Type 'housing' to see available locations."
            )
            return
        result = await rent_room(ctx.db, char, int(rest))
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        if result["ok"]:
            await ctx.session.send_line(
                f"  \033[2mType 'housing' to see your room details. "
                f"Go {result.get('direction', 'through the door')} to enter.\033[0m"
            )
        return

        # ── housing checkout ──

    async def _cmd_checkout(self, ctx, char, rest):
        h = await get_housing(ctx.db, char["id"])
        if not h:
            await ctx.session.send_line("  You don't have a rented room.")
            return
        storage = _storage(h)
        if storage:
            await ctx.session.send_line(
                f"  \033[1;33mYour storage has {len(storage)} item(s). "
                f"They will be returned to your inventory on checkout.\033[0m"
            )
        result = await checkout_room(ctx.db, char)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing storage ──

    async def _cmd_storage(self, ctx, char, rest):
        h = await get_housing(ctx.db, char["id"])
        if not h:
            await ctx.session.send_line("  You don't have a home with storage.")
            return
        storage = _storage(h)
        if not storage:
            await ctx.session.send_line(
                f"  Storage: empty  (0/{h['storage_max']} slots)"
            )
            return
        await ctx.session.send_line(
            f"  \033[1;37mHome Storage ({len(storage)}/{h['storage_max']} slots):\033[0m"
        )
        for i, it in enumerate(storage, 1):
            name = it.get("name") or it.get("key") or "Unknown item"
            qual = f"  Q{it['quality']}" if it.get("quality") else ""
            await ctx.session.send_line(f"    {i}. {name}{qual}")
        return

        # ── housing store <item> ──

    async def _cmd_store(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing store <item name>")
            return
        result = await housing_store(ctx.db, char, rest)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing retrieve <item> ──

    async def _cmd_retrieve(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing retrieve <item name>")
            return
        result = await housing_retrieve(ctx.db, char, rest)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing name <text> ──

    async def _cmd_name(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing name <new room name>")
            return
        h = await get_housing(ctx.db, char["id"])
        if not h:
            await ctx.session.send_line("  You don't have a home to rename.")
            return
        from engine.housing import set_room_name
        result = await set_room_name(ctx.db, char, h["id"], rest)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing describe / housing desc ──

    async def _cmd_describe(self, ctx, char, rest):
        h = await get_housing(ctx.db, char["id"])
        if not h:
            await ctx.session.send_line("  You don't have a home to describe.")
            return
        await _run_description_editor(ctx, char, h)
        return

        # ── housing trophy <item> ──

    async def _cmd_trophy(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing trophy <item name>")
            return
        from engine.housing import trophy_mount
        result = await trophy_mount(ctx.db, char, rest)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing untrophy <item> ──

    async def _cmd_untrophy(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing untrophy <item name>")
            return
        from engine.housing import trophy_unmount
        result = await trophy_unmount(ctx.db, char, rest)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing trophies ──

    async def _cmd_trophies(self, ctx, char, rest):
        from engine.housing import get_housing, _trophies
        h = await get_housing(ctx.db, char["id"])
        if not h:
            await ctx.session.send_line("  You don't have a home.")
            return
        tlist = _trophies(h)
        if not tlist:
            await ctx.session.send_line("  No trophies mounted. Use 'housing trophy <item>' to mount one.")
            return
        await ctx.session.send_line(f"  \033[1;37mTrophies ({len(tlist)}/10):\033[0m")
        for t in tlist:
            name = t.get("name") or t.get("key") or "Unknown"
            qual = f"  Q{t['quality']}" if t.get("quality") else ""
            await ctx.session.send_line(f"    ◆ {name}{qual}")
        return

        # ── housing buy <type> <lot_id> ──

    async def _cmd_buy(self, ctx, char, rest):
        buy_parts = rest.split(None, 1)
        if len(buy_parts) < 2 or not buy_parts[1].strip().isdigit():
            from engine.housing import get_tier3_listing_lines
            lines = await get_tier3_listing_lines(ctx.db, char)
            for line in lines:
                await ctx.session.send_line(line)
            return
        home_type = buy_parts[0].lower()
        lot_id = int(buy_parts[1].strip())
        from engine.housing import purchase_home
        result = await purchase_home(ctx.db, char, lot_id, home_type)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        # Enqueue AI description pre-generation on successful purchase
        if result.get("ok") and result.get("housing_id"):
            try:
                _iq = getattr(ctx.session_mgr, '_idle_queue', None)
                if _iq:
                    from engine.housing import get_lot
                    _lot = await get_lot(ctx.db, lot_id)
                    _planet = _lot["planet"] if _lot else "tatooine"
                    _lot_label = _lot["label"] if _lot else ""
                    _zone_tone = ""
                    try:
                        from engine.zone_tones import get_zone_tone
                        _zone_tone = await get_zone_tone(ctx.db, lot_id)
                    except Exception as _e:
                        log.debug("silent except in parser/housing_commands.py:266: %s", _e, exc_info=True)
                    _iq.enqueue_housing_desc(
                        housing_id=result["housing_id"],
                        room_name=f"{char.get('name', 'Unknown')}'s Residence",
                        tier_label="Private Residence",
                        planet=_planet,
                        zone_tone=_zone_tone,
                    )
            except Exception:
                pass  # Non-critical
        return

        # ── housing shopfront <type> <lot_id> ──

    async def _cmd_shopfront(self, ctx, char, rest):
        from engine.housing import (
            get_tier4_listing_lines, purchase_shopfront, HOUSING_LOTS_TIER4
        )
        sf_parts = rest.split(None, 1)
        if len(sf_parts) < 2 or not sf_parts[1].strip().isdigit():
            lines = await get_tier4_listing_lines(ctx.db, char)
            for line in lines:
                await ctx.session.send_line(line)
            return
        sf_type = sf_parts[0].lower()
        lot_id  = int(sf_parts[1].strip())
        result  = await purchase_shopfront(ctx.db, char, lot_id, sf_type)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        # Enqueue AI description pre-generation on successful purchase
        if result.get("ok") and result.get("housing_id"):
            try:
                _iq = getattr(ctx.session_mgr, '_idle_queue', None)
                if _iq:
                    _planet = "tatooine"
                    for _lt in HOUSING_LOTS_TIER4:
                        if _lt[0] == lot_id:
                            _planet = _lt[1]
                            break
                    _iq.enqueue_housing_desc(
                        housing_id=result["housing_id"],
                        room_name=f"{char.get('name', 'Unknown')}'s Shopfront",
                        tier_label="Shopfront",
                        planet=_planet,
                    )
            except Exception:
                pass  # Non-critical
        return

        # ── housing sell ──

    async def _cmd_sell(self, ctx, char, rest):
        h = await get_housing(ctx.db, char["id"])
        if not h or h.get("housing_type") not in ("private_residence", "shopfront"):
            await ctx.session.send_line(
                "  You don't own a purchased home to sell. "
                "Use 'housing checkout' for rentals."
            )
            return
        # Route shopfront sells to dedicated function
        if h.get("housing_type") == "shopfront":
            from engine.housing import sell_shopfront
            if rest.lower() != "confirm":
                price = h.get("purchase_price", 0) // 2
                await ctx.session.send_line(
                    f"  Sell your shopfront for {price:,}cr (50% of purchase price).\n"
                    "  Any vendor droids will be recalled automatically.\n"
                    "  Type \033[1;37mhousing sell confirm\033[0m to proceed."
                )
                return
            result = await sell_shopfront(ctx.db, char)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return
        # Confirmation check
        if rest.lower() != "confirm":
            price = h.get("purchase_price", 0) // 2
            await ctx.session.send_line(
                f"  \033[1;33mSelling your home will refund {price:,}cr "
                f"(50% of purchase price).\033[0m\n"
                f"  All stored items and trophies will be returned to inventory.\n"
                f"  Type \033[1;37mhousing sell confirm\033[0m to proceed."
            )
            return
        from engine.housing import sell_home
        result = await sell_home(ctx.db, char)
        await ctx.session.send_line(
            ansi.success(f"  {result['msg']}") if result["ok"]
            else ansi.error(f"  {result['msg']}")
        )
        return

        # ── housing guest add/remove/list ──

    async def _cmd_guest(self, ctx, char, rest):
        guest_parts = rest.split(None, 1)
        guest_sub = guest_parts[0].lower() if guest_parts else "list"
        guest_arg = guest_parts[1].strip() if len(guest_parts) > 1 else ""

        if guest_sub == "list" or not guest_sub:
            from engine.housing import get_guest_list_display
            lines = await get_guest_list_display(ctx.db, char)
            for line in lines:
                await ctx.session.send_line(line)
            return

        if guest_sub == "add":
            if not guest_arg:
                await ctx.session.send_line("  Usage: housing guest add <player name>")
                return
            from engine.housing import guest_add
            result = await guest_add(ctx.db, char, guest_arg)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        if guest_sub in ("remove", "revoke", "delete"):
            if not guest_arg:
                await ctx.session.send_line("  Usage: housing guest remove <player name>")
                return
            from engine.housing import guest_remove
            result = await guest_remove(ctx.db, char, guest_arg)
            await ctx.session.send_line(
                ansi.success(f"  {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        await ctx.session.send_line(
            "  Usage: housing guest add/remove/list <player>"
        )
        return

        # ── housing intrusions ──

    async def _cmd_intrusions(self, ctx, char, rest):
        from engine.housing import get_intrusion_log
        lines = await get_intrusion_log(ctx.db, char)
        for line in lines:
            await ctx.session.send_line(line)
        return

        # ── housing visit <player> — find a player's shopfront ──

    async def _cmd_visit(self, ctx, char, rest):
        if not rest:
            await ctx.session.send_line("  Usage: housing visit <player name>")
            return
        target_name = rest.strip()
        # Find the player
        rows = await ctx.db.fetchall(
            "SELECT id, name FROM characters WHERE LOWER(name) = LOWER(?)",
            (target_name,),
        )
        if not rows:
            await ctx.session.send_line(f"  No player named '{target_name}' found.")
            return
        target_id = rows[0]["id"]
        target_display = rows[0]["name"]
        # Find their shopfront
        from engine.housing import get_housing
        target_h = await get_housing(ctx.db, target_id)
        if not target_h or target_h.get("housing_type") != "shopfront":
            await ctx.session.send_line(
                f"  {target_display} doesn't have a public shopfront."
            )
            return
        entry = target_h.get("entry_room_id")
        if not entry:
            await ctx.session.send_line(f"  Could not locate {target_display}'s shop.")
            return
        room = await ctx.db.get_room(entry)
        shop_name = room["name"] if room else f"Room #{entry}"
        await ctx.session.send_line(
            f"  \033[1;36m{target_display}'s shopfront: {shop_name}\033[0m"
        )
        await ctx.session.send_line(
            f"  \033[2mRoom #{entry} — use the map or navigate there manually.\033[0m"
        )
        return

        await ctx.session.send_line(
        f"  Unknown housing command '{sub}'. Type 'housing' for help."
        )

    async def _go_home(self, ctx: CommandContext, char: dict) -> None:
        """Teleport to character's home room."""
        try:
            # Check home_room_id column
            rows = await ctx.db.fetchall(
                "SELECT home_room_id FROM characters WHERE id = ?", (char["id"],)
            )
            if rows and rows[0]["home_room_id"]:
                home_id = rows[0]["home_room_id"]
                char["room_id"] = home_id
                await ctx.db.save_character(char["id"], room_id=home_id)
                ctx.session.character["room_id"] = home_id

                room = await ctx.db.get_room(home_id)
                room_name = room["name"] if room else "your home"
                await ctx.session.send_line(
                    f"  \033[1;36mYou make your way home.\033[0m\n"
                    f"  {room_name}"
                )
                # Trigger look
                look_cmd = ctx.session_mgr._registry.get("look") if hasattr(ctx.session_mgr, '_registry') else None
                if look_cmd:
                    look_ctx = type(ctx)(
                        session=ctx.session, raw_input="look", command="look",
                        args="", args_list=[], db=ctx.db,
                        session_mgr=ctx.session_mgr,
                    )
                    await look_cmd.execute(look_ctx)
                return
        except Exception as e:
            log.warning("[housing] go_home error: %s", e)

        await ctx.session.send_line(
            "  You don't have a home set. Rent a room with 'housing rent <id>'."
        )


# ── Housing Drop 9: AI-assisted description generation ────────────────────────

_TIER_LABELS_SHORT = {
    1: "rented room", 2: "faction quarters", 3: "private residence",
    4: "shopfront", 5: "organization HQ",
}

_SUGGEST_SYSTEM = (
    "You are a Star Wars room description writer for a text-based multiplayer game "
    "set during the Galactic Civil War era. Write vivid, atmospheric room "
    "descriptions in second person present tense ('You see...', 'The room...'). "
    "Keep descriptions between 2-4 sentences, under 400 characters total. "
    "Focus on sensory details: sights, sounds, smells. Match the tone of the "
    "location and housing tier. Never mention game mechanics. "
    "Output ONLY the description text, no quotes or preamble."
)


async def _ai_suggest_description(
    ctx, char: dict, h: dict, room_name: str,
    buf: list, style_hint: str = "",
) -> None:
    """Generate an AI room description suggestion and offer it to the player."""
    CYAN = "\033[1;36m"
    DIM = "\033[2m"
    YELLOW = "\033[1;33m"
    RST = "\033[0m"

    # Check Ollama idle queue cache first (free, instant)
    if not style_hint and not buf:
        _iq = getattr(ctx.session_mgr, '_idle_queue', None) if ctx.session_mgr else None
        if _iq:
            cached = _iq.get_cached_description(h.get("id", 0))
            if cached:
                await ctx.session.send_line(CYAN + "  ── AI Suggestion (cached) ──" + RST)
                words = cached.split()
                line_buf = "  "
                for w in words:
                    if len(line_buf) + len(w) + 1 > 72:
                        await ctx.session.send_line(line_buf)
                        line_buf = "  " + w
                    else:
                        line_buf += (" " if len(line_buf) > 2 else "") + w
                if line_buf.strip():
                    await ctx.session.send_line(line_buf)
                await ctx.session.send_line(CYAN + "  ────────────────────" + RST)
                await ctx.session.send_line(
                    DIM + "  Type .accept to use this, .suggest to regenerate, "
                    "or keep typing your own." + RST
                )
                ctx.session._housing_ai_suggestion = cached
                return

    # Get AI manager from session_mgr
    ai_mgr = getattr(ctx.session_mgr, "_ai_manager", None) if ctx.session_mgr else None
    if not ai_mgr:
        await ctx.session.send_line(
            YELLOW + "  AI suggestions unavailable (no AI provider configured)." + RST
        )
        return

    # Check if claude provider is available
    try:
        claude = ai_mgr.get_provider("claude")
        if not await claude.is_available():
            raise ValueError("Claude not available")
    except Exception:
        await ctx.session.send_line(
            YELLOW + "  AI suggestions unavailable (Haiku API not configured)." + RST
        )
        return

    await ctx.session.send_line(DIM + "  Generating suggestion..." + RST)

    # Gather context
    tier = h.get("tier", 1)
    tier_label = _TIER_LABELS_SHORT.get(tier, "room")
    faction = h.get("faction_code", "")

    # Get planet from housing lot
    planet = "unknown"
    try:
        entry_room = h.get("entry_room_id")
        if entry_room:
            from engine.housing import get_lot_by_room
            lot = await get_lot_by_room(ctx.db, entry_room)
            if lot:
                planet = lot.get("planet", "unknown")
    except Exception as _e:
        log.debug("silent except in parser/housing_commands.py:578: %s", _e, exc_info=True)

    # Get zone narrative tone
    zone_tone = ""
    try:
        room_id = char.get("room_id")
        if room_id:
            from engine.zone_tones import get_zone_tone
            zone_tone = await get_zone_tone(ctx.db, room_id)
    except Exception as _e:
        log.debug("silent except in parser/housing_commands.py:588: %s", _e, exc_info=True)

    # Build prompt
    prompt_parts = [
        f"Room name: {room_name}",
        f"Housing type: {tier_label}",
        f"Planet: {planet.replace('_', ' ').title()}",
    ]
    if faction:
        prompt_parts.append(f"Faction: {faction.replace('_', ' ').title()}")
    if zone_tone:
        prompt_parts.append(f"Zone atmosphere: {zone_tone[:200]}")
    if style_hint:
        prompt_parts.append(f"Requested style/mood: {style_hint}")
    if buf:
        current = " ".join(buf)[:200]
        prompt_parts.append(f"Current draft (expand on this): {current}")

    user_msg = "\n".join(prompt_parts)

    try:
        suggestion = await claude.generate(
            system_prompt=_SUGGEST_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=300,
            temperature=0.8,
        )
        suggestion = suggestion.strip()
        if not suggestion:
            await ctx.session.send_line(
                YELLOW + "  AI returned empty response. Try again or write your own." + RST
            )
            return

        # Truncate if too long
        if len(suggestion) > 500:
            suggestion = suggestion[:497] + "..."

        await ctx.session.send_line(CYAN + "  ── AI Suggestion ──" + RST)
        # Word-wrap suggestion at ~70 chars for readability
        words = suggestion.split()
        line_buf = "  "
        for w in words:
            if len(line_buf) + len(w) + 1 > 72:
                await ctx.session.send_line(line_buf)
                line_buf = "  " + w
            else:
                line_buf += (" " if len(line_buf) > 2 else "") + w
        if line_buf.strip():
            await ctx.session.send_line(line_buf)
        await ctx.session.send_line(CYAN + "  ────────────────────" + RST)
        await ctx.session.send_line(
            DIM + "  Type .accept to use this, .suggest to regenerate, "
            "or keep typing your own." + RST
        )

        # Store suggestion for .accept
        ctx.session._housing_ai_suggestion = suggestion

    except Exception as e:
        log.warning("[housing] AI suggest failed: %s", e)
        await ctx.session.send_line(
            YELLOW + "  AI suggestion failed. Write your own description." + RST
        )


async def _run_description_editor(ctx, char: dict, h: dict) -> None:
    """
    Interactive description editor using session._input_intercept.

    Commands while editing:
      .done    — save and exit
      .clear   — wipe buffer and restart
      .show    — preview current buffer
      .cancel  — abort without saving
    Any other input is appended to the buffer.
    """
    from engine.housing import _room_ids

    room_ids = _room_ids(h)
    if not room_ids:
        await ctx.session.send_line("  No room to describe.")
        return

    room = await ctx.db.get_room(room_ids[0])
    current = (room.get("desc_long") or room.get("desc_short") or "") if room else ""
    room_name = room["name"] if room else "your room"

    CYAN = "\033[1;36m"
    DIM  = "\033[2m"
    RST  = "\033[0m"

    await ctx.session.send_line(CYAN + "  \u2554" + "\u2550" * 42 + "\u2557" + RST)
    await ctx.session.send_line(CYAN + "  \u2551  ROOM DESCRIPTION EDITOR" + " " * 18 + "\u2551" + RST)
    await ctx.session.send_line(CYAN + "  \u255a" + "\u2550" * 42 + "\u255d" + RST)
    await ctx.session.send_line(f"  Room: {room_name}")
    await ctx.session.send_line(f"  Current length: {len(current)} / 2000 chars")
    if current:
        preview = current[:120] + ("..." if len(current) > 120 else "")
        await ctx.session.send_line(DIM + f"  Current: {preview}" + RST)
    await ctx.session.send_line(DIM + "  " + "-" * 44 + RST)
    await ctx.session.send_line(DIM + "  Type lines of description." + RST)
    await ctx.session.send_line(DIM + "  .done=save  .clear=restart  .show=preview  .cancel=abort" + RST)
    await ctx.session.send_line(DIM + "  .suggest=AI suggestion  .suggest <style>=themed suggestion" + RST)

    buf: list[str] = []

    async def intercept(line: str) -> None:
        cmd = line.strip().lower()

        if cmd == ".cancel":
            ctx.session._input_intercept = None
            await ctx.session.send_line("  Description editing cancelled.")
            await ctx.session.send_prompt()
            return

        if cmd == ".clear":
            buf.clear()
            await ctx.session.send_line("  Buffer cleared. Start typing your description.")
            await ctx.session.send_prompt()
            return

        if cmd == ".show":
            preview = " ".join(buf)
            if preview:
                await ctx.session.send_line(
                    f"  Preview ({len(preview)} chars): {preview[:400]}"
                    + ("..." if len(preview) > 400 else "")
                )
            else:
                await ctx.session.send_line("  Buffer is empty.")
            await ctx.session.send_prompt()
            return

        if cmd.startswith(".suggest"):
            # Housing Drop 9: AI-generated description suggestion via Haiku
            style_hint = line.strip()[len(".suggest"):].strip()
            await _ai_suggest_description(ctx, char, h, room_name, buf, style_hint)
            await ctx.session.send_prompt()
            return

        if cmd == ".accept":
            # Accept the last AI suggestion and replace buffer
            suggestion = getattr(ctx.session, "_housing_ai_suggestion", None)
            if not suggestion:
                await ctx.session.send_line("  No AI suggestion to accept. Use .suggest first.")
            else:
                buf.clear()
                buf.append(suggestion)
                ctx.session._housing_ai_suggestion = None
                await ctx.session.send_line(
                    f"\033[1;32m  AI suggestion accepted ({len(suggestion)} chars). "
                    f"Use .done to save or keep editing.\033[0m"
                )
            await ctx.session.send_prompt()
            return

        if cmd == ".done":
            ctx.session._input_intercept = None
            final = " ".join(buf).strip()
            if not final:
                await ctx.session.send_line("  Nothing entered. Edit cancelled.")
                await ctx.session.send_prompt()
                return
            from engine.housing import set_room_description
            result = await set_room_description(ctx.db, char, h["id"], final)
            if result["ok"]:
                await ctx.session.send_line(ansi.success("  " + result["msg"]))
            else:
                await ctx.session.send_line(ansi.error("  " + result["msg"]))
            await ctx.session.send_prompt()
            return

        # Append to buffer
        stripped = line.strip()
        if stripped:
            total = len(" ".join(buf)) + len(stripped) + 1
            if total > 2000:
                await ctx.session.send_line(
                    "\033[1;33m  Character limit reached (2000). Use .done to save or .clear to restart.\033[0m"
                )
            else:
                buf.append(stripped)
        await ctx.session.send_prompt()

    ctx.session._input_intercept = intercept
    await ctx.session.send_prompt()


class SetHomeCommand(BaseCommand):
    key = "sethome"
    aliases = []
    help_text = "Set your current location as your home. Must be in your housing room."
    usage = "sethome"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            return
        room_id = char.get("room_id")

        from engine.housing import get_housing_for_room
        h = await get_housing_for_room(ctx.db, room_id)

        if not h or h["char_id"] != char["id"]:
            await ctx.session.send_line(
                "  You can only set home in a room you own or rent."
            )
            return

        try:
            await ctx.db.execute(
                "UPDATE characters SET home_room_id = ? WHERE id = ?",
                (room_id, char["id"]),
            )
            await ctx.db.commit()
        except Exception as e:
            log.warning("[housing] sethome error: %s", e)
            await ctx.session.send_line("  Error setting home.")
            return

        room = await ctx.db.get_room(room_id)
        await ctx.session.send_line(
            ansi.success(f"  Home set to: {room['name'] if room else room_id}. "
                         f"Type 'home' to return here.")
        )


# ── @housing admin command ────────────────────────────────────────────────────

class AdminHousingCommand(BaseCommand):
    key = "@housing"
    aliases = []
    help_text = (
        "Admin housing management.\n"
        "  @housing list [planet]    — list all housing records\n"
        "  @housing inspect <player> — view a player's housing\n"
        "  @housing evict <player>   — force-evict a player\n"
        "  @housing lots             — show all housing lots and occupancy"
    )
    usage = "@housing <sub> [args]"

    async def execute(self, ctx: CommandContext) -> None:
        from engine.housing import (
            get_housing, get_available_lots, checkout_room,
            _storage, _room_ids,
        )

        parts = (ctx.args or "").split(None, 1)
        sub   = parts[0].lower() if parts else "list"
        rest  = parts[1].strip() if len(parts) > 1 else ""

        if sub == "list":
            rows = await ctx.db.fetchall(
                """SELECT ph.*, c.name AS owner_name
                   FROM player_housing ph
                   JOIN characters c ON c.id = ph.char_id
                   ORDER BY ph.created_at DESC"""
            )
            if not rows:
                await ctx.session.send_line("  No housing records.")
                return
            await ctx.session.send_line(
                f"  \033[1;37mAll Housing ({len(rows)} records):\033[0m"
            )
            for r in rows:
                r = dict(r)
                storage_count = len(json.loads(r.get("storage", "[]") or "[]"))
                await ctx.session.send_line(
                    f"  [{r['id']}] {r['owner_name']:<20} "
                    f"Tier {r['tier']}  "
                    f"Room(s): {r['room_ids']}  "
                    f"Storage: {storage_count}/{r['storage_max']}  "
                    f"Overdue: {r['rent_overdue']}w"
                )
            return

        if sub == "lots":
            rows = await ctx.db.fetchall(
                "SELECT * FROM housing_lots ORDER BY planet, id"
            )
            if not rows:
                await ctx.session.send_line("  No housing lots defined.")
                return
            await ctx.session.send_line(
                f"  \033[1;37mHousing Lots:\033[0m"
            )
            for r in rows:
                r = dict(r)
                await ctx.session.send_line(
                    f"  [{r['id']}] {r['label']:<40} "
                    f"Room {r['room_id']}  "
                    f"{r['current_homes']}/{r['max_homes']} occupied  "
                    f"[{r['security'].upper()}]"
                )
            return

        if sub == "inspect":
            char_rows = await ctx.db.fetchall(
                "SELECT * FROM characters WHERE LOWER(name) = LOWER(?)", (rest,)
            )
            if not char_rows:
                await ctx.session.send_line(f"  Player '{rest}' not found.")
                return
            target = dict(char_rows[0])
            h = await get_housing(ctx.db, target["id"])
            if not h:
                await ctx.session.send_line(
                    f"  {target['name']} has no housing."
                )
                return
            storage = _storage(h)
            room_ids = _room_ids(h)
            await ctx.session.send_line(
                f"  \033[1;37m{target['name']}'s Housing:\033[0m\n"
                f"  ID: {h['id']}  Tier: {h['tier']}  Type: {h['housing_type']}\n"
                f"  Entry room: {h['entry_room_id']}  Rooms: {room_ids}\n"
                f"  Storage: {len(storage)}/{h['storage_max']}  "
                f"Overdue: {h['rent_overdue']} week(s)\n"
                f"  Rent/week: {h['weekly_rent']}cr  Deposit: {h['deposit']}cr"
            )
            return

        if sub == "evict":
            char_rows = await ctx.db.fetchall(
                "SELECT * FROM characters WHERE LOWER(name) = LOWER(?)", (rest,)
            )
            if not char_rows:
                await ctx.session.send_line(f"  Player '{rest}' not found.")
                return
            target = dict(char_rows[0])
            result = await checkout_room(ctx.db, target)
            await ctx.session.send_line(
                ansi.success(f"  Evicted {target['name']}. {result['msg']}") if result["ok"]
                else ansi.error(f"  {result['msg']}")
            )
            return

        await ctx.session.send_line(f"  Unknown @housing sub-command '{sub}'.")


# ── Registration ───────────────────────────────────────────────────────────────

def register_housing_commands(registry) -> None:
    """Register all housing commands. Called from game_server.py.

    S58 — +home umbrella registered first.
    """
    registry.register(HomeUmbrellaCommand())
    for cmd in [
        HousingCommand(),
        SetHomeCommand(),
        AdminHousingCommand(),
    ]:
        registry.register(cmd)


# ═══════════════════════════════════════════════════════════════════════════
# +home — Umbrella for housing verbs (S58)
# ═══════════════════════════════════════════════════════════════════════════

_HOME_SWITCH_IMPL: dict = {}

_HOME_ALIAS_TO_SWITCH: dict[str, str] = {
    # View — default (absorbed from HousingCommand alias list)
    "home": "view", "myroom": "view", "homelocation": "view",
    "housing": "view",
    # Set your home location
    "sethome": "sethome",
    # Admin
    "admin": "admin",
}


class HomeUmbrellaCommand(BaseCommand):
    """`+home` umbrella — housing / residence verbs.

    Canonical            Bare aliases (still work)
    -----------------    ---------------------------
    +home                home, myroom, housing (view your home — default)
    +home/view           same as default
    +home/sethome        sethome (set current room as your home)
    +home/admin <args>   @housing (admin-only)

    UNKNOWN-SWITCH FORWARDING (S58):
    HousingCommand uses positional-argument subcommands (rent,
    storage, name, trophy, buy, shopfront, guest, visit, etc.). Any
    switch NOT in the "real" umbrella switch set is forwarded to
    HousingCommand with the switch name prepended. So `+home/rent 5`
    reaches HousingCommand as `housing rent 5`.
    """

    key = "+home"
    aliases = [
        "home", "myroom", "homelocation",
        "sethome",
        # NOTE: @housing admin stays at its own key
    ]
    help_text = (
        "All housing verbs live under +home/<switch>. "
        "Bare verbs (home, myroom, sethome) still work."
    )
    usage = "+home[/switch] [args]  — see 'help +home' for all switches"
    valid_switches = [
        # Real umbrella switches
        "view", "sethome", "admin",
        # HousingCommand subcommands — forwarded
        "rent", "checkout", "storage", "store", "retrieve",
        "name", "describe",
        "trophy", "untrophy", "trophies",
        "buy", "shopfront", "sell",
        "guest", "intrusions", "visit",
    ]

    async def execute(self, ctx: CommandContext):
        switch = None
        if ctx.switches:
            switch = ctx.switches[0].lower()
        else:
            typed = (ctx.command or "").lower()
            switch = _HOME_ALIAS_TO_SWITCH.get(typed, "view")

        impl = _HOME_SWITCH_IMPL.get(switch)
        if impl is not None:
            await impl.execute(ctx)
            return

        # Forward to HousingCommand with switch prepended to args
        args_before = ctx.args or ""
        ctx.args = f"{switch} {args_before}".strip()
        ctx.switches = []
        try:
            await HousingCommand().execute(ctx)
        finally:
            ctx.args = args_before
            ctx.switches = [switch]


def _init_home_switch_impl():
    global _HOME_SWITCH_IMPL
    _HOME_SWITCH_IMPL = {
        "view":    HousingCommand(),
        "sethome": SetHomeCommand(),
        "admin":   AdminHousingCommand(),
    }


_init_home_switch_impl()
