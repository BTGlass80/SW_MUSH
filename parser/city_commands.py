"""
parser/city_commands.py — Player Cities (Phases 1 + 2 + 3 + 4 + 5) command surface.

Phase 1 ships: +city found <name>, +city dissolve <name>
Phase 2 ships: +city claim <direction|room_id>, +city release [room_id]
Phase 3 ships: +city info, +city map, +city citizens, +city list,
               +city motd, +city mayor (founder-only), +city guards,
               +city guest add/remove, +city banish, +city unbanish,
               +city citizenroom on/off
Phase 4 ships: +city tax view, +city tax set <pct>,
               +city tax ratecap <pct> (founder-only)
Phase 5 ships: +city home (citizen teleport to HQ entry, 1-hour
               cooldown, same-zone, not in combat/space)

Phase 6 admin tools (`@city` verb, AccessLevel.ADMIN) live in
parser/admin_city_commands.py — a separate registration to keep
player-facing and admin-facing permission gates cleanly isolated.

This module's `+city` umbrella is player-facing only; no admin
subcommands need a placeholder here because the @city verb is
its own keyword.

Per design v1.2 §11 + §5 + §6. Phase 5 drop label: ``cities_phase5``;
Phase 6 drop label: ``cities_phase6_admin``.
"""

from __future__ import annotations

import logging

from parser.commands import AccessLevel, BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# Phase advertisement strings (DRY for the placeholder branches).
_PHASE_MSGS = {
    2: "(coming in Phase 2: expansion)",
    3: "(coming in Phase 3: governance + look integration)",
    4: "(coming in Phase 4: taxation)",
    5: "(coming in Phase 5: citizen benefits)",
}


class CityCommand(BaseCommand):
    """``+city`` — player city governance entry point.

    Phase 1 ships only ``+city found`` and ``+city dissolve``; the
    other subcommands echo their target phase number.
    """

    key = "+city"
    aliases: list[str] = []
    access_level = AccessLevel.PLAYER

    usage = (
        "+city <found|dissolve|info|map|citizens|tax|home|list|"
        "claim|release|motd|mayor|guards|guest|banish|unbanish|"
        "citizenroom> [...]"
    )

    help_text = (
        "Player city system. Phases 1-5 ship founding, expansion, "
        "governance, look-output, taxation, and citizen benefits. "
        "Admin tools (Phase 6) ship as a separate `@city` keyword.\n"
    )

    async def execute(self, ctx: CommandContext) -> None:
        char = getattr(ctx.session, "character", None)
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to use +city."
            )
            return

        args = (ctx.args or "").strip()
        if not args:
            await self._show_help(ctx)
            return

        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "found":
            await self._handle_found(ctx, char, rest)
            return
        if sub == "dissolve":
            await self._handle_dissolve(ctx, char, rest)
            return
        if sub == "claim":
            await self._handle_claim(ctx, char, rest)
            return
        if sub == "release":
            await self._handle_release(ctx, char, rest)
            return

        # ── Phase 3 subcommands ────────────────────────────────────────
        if sub == "info":
            await self._handle_info(ctx, char, rest)
            return
        if sub == "map":
            await self._handle_map(ctx, char, rest)
            return
        if sub == "citizens":
            await self._handle_citizens(ctx, char, rest)
            return
        if sub == "list":
            await self._handle_list(ctx, char, rest)
            return
        if sub == "motd":
            await self._handle_motd(ctx, char, rest)
            return
        if sub == "mayor":
            await self._handle_mayor(ctx, char, rest)
            return
        if sub == "guards":
            await self._handle_guards(ctx, char, rest)
            return
        if sub == "guest":
            await self._handle_guest(ctx, char, rest)
            return
        if sub == "banish":
            await self._handle_banish(ctx, char, rest)
            return
        if sub == "unbanish":
            await self._handle_unbanish(ctx, char, rest)
            return
        if sub == "citizenroom":
            await self._handle_citizenroom(ctx, char, rest)
            return

        # ── Phase 4 subcommands ────────────────────────────────────────
        if sub == "tax":
            await self._handle_tax(ctx, char, rest)
            return

        # ── Phase 5 subcommands ────────────────────────────────────────
        if sub == "home":
            await self._handle_home(ctx, char, rest)
            return

        await ctx.session.send_line(
            f"  Unknown +city subcommand: {sub!r}"
        )
        await ctx.session.send_line(f"  Usage: {self.usage}")

    # ── Help (bare `+city`) ──────────────────────────────────────────────

    async def _show_help(self, ctx: CommandContext) -> None:
        lines = [
            "Player cities — phased rollout in progress.",
            "",
            "Available now:",
            "  +city found <name>         Found a city (org leader, "
            "tier-5 HQ, 50 influence, treasury).",
            "  +city dissolve <name>      Dissolve a city (org "
            "leader only; refunds 50% of founding cost).",
            "  +city claim <direction>    Claim an adjacent room as "
            "expansion (org leader).",
            "  +city claim <room_id>      Claim by explicit room id "
            "(if you know it).",
            "  +city release [room_id]    Release an expansion room "
            "(default: room you're standing in).",
            "  +city info                 Show details for the city "
            "you're in.",
            "  +city map                  ASCII map of the current "
            "city.",
            "  +city citizens             List members + guests of "
            "the current city.",
            "  +city list                 List all active cities.",
            "  +city motd <text>          Set the city's motd "
            "(Mayor/Founder).",
            "  +city mayor <player>       Reassign Mayor "
            "(Founder only).",
            "  +city guards               View NPC guards stationed "
            "in this city.",
            "  +city guards assign <room>   Station a guard in a "
            "city room (Mayor/Founder).",
            "  +city guards remove <npc>    Remove a guard "
            "(Mayor/Founder).",
            "  +city guest add <player>   Add a guest (Mayor/"
            "Founder).",
            "  +city guest remove <p>     Remove a guest (Mayor/"
            "Founder).",
            "  +city banish <player>      Banish a player from the "
            "city for 30 days (Mayor/Founder).",
            "  +city unbanish <player>    Lift a banishment "
            "(Mayor/Founder).",
            "  +city citizenroom on|off [room_id]   Mark current or "
            "named room as citizen-only (Mayor/Founder).",
            "  +city tax view             View tax rate + revenue.",
            "  +city tax set <pct>        Set tax rate, 0-10% "
            "(Mayor/Founder, within cap).",
            "  +city tax ratecap <pct>    Set rate cap, 0-10% "
            "(Founder only).",
            "  +city home                 Teleport to city HQ entry "
            "(citizen only; 1-hour cooldown).",
            "",
            "Coming soon:",
            "  (Phase 6 admin tools)",
        ]
        for line in lines:
            await ctx.session.send_line(line)

    # ── +city found ─────────────────────────────────────────────────────

    async def _handle_found(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Dispatch `+city found <name>` or `+city found <name> in <region>`.

        SYN.4 (2026-05-25): added the region-anchored form. If the args
        contain `' in '` (with surrounding spaces), the trailing token is
        treated as the wilderness region slug and the new
        ``found_city_in_region`` flow is invoked. Otherwise the legacy
        ``found_city`` flow runs. Per design v2 §2.9.1, post-migration
        only the region-anchored form will yield viable cities — but
        the legacy syntax is preserved so the 520 existing cities tests
        and any cached-fixture admin flows keep working.
        """
        if not args:
            await ctx.session.send_line(
                "  Usage: +city found <name>\n"
                "         +city found <name> in <region_slug>   "
                "(SYN.4)"
            )
            return

        # Detect ` in <slug>` suffix (case-insensitive on ' in ').
        # Split only on the LAST ' in ' so multi-word names that
        # contain "in" as a substring don't false-positive.
        region_slug = None
        name_part = args
        lower = args.lower()
        in_idx = lower.rfind(" in ")
        if in_idx > 0:
            candidate = args[in_idx + 4:].strip()
            # Slug shape: lowercase identifier chars only. If the
            # candidate has spaces it's almost certainly part of the
            # name, not a slug.
            if candidate and " " not in candidate:
                region_slug = candidate
                name_part = args[:in_idx].strip()

        try:
            if region_slug:
                from engine.player_cities import found_city_in_region
                ok, message = await found_city_in_region(
                    ctx.db, char, name_part, region_slug,
                )
            else:
                from engine.player_cities import found_city
                ok, message = await found_city(ctx.db, char, name_part)
        except Exception as e:
            log.exception("[city.found] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The founding was not "
                "completed."
            )
            return

        if ok:
            await ctx.session.send_line(f"  {ansi.GREEN}{message}{ansi.RESET}")
        else:
            await ctx.session.send_line(f"  {message}")

    # ── +city dissolve ──────────────────────────────────────────────────

    async def _handle_dissolve(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        if not args:
            await ctx.session.send_line(
                "  Usage: +city dissolve <name>"
            )
            return

        from engine.player_cities import dissolve_city

        try:
            ok, message = await dissolve_city(ctx.db, char, args)
        except Exception as e:
            log.exception("[city.dissolve] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The dissolution was "
                "not completed."
            )
            return

        if ok:
            await ctx.session.send_line(f"  {ansi.YELLOW}{message}{ansi.RESET}")
        else:
            await ctx.session.send_line(f"  {message}")

    # ── +city claim ─────────────────────────────────────────────────────

    async def _handle_claim(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Dispatch `+city claim <direction-or-room-id>`.

        The argument is treated as:
          1. A room id if it parses as int
          2. A direction (e.g. 'northwest', 'up') otherwise — resolved
             via the exits table from the player's current room.

        Phase 2 design call: direction-from-current-room is the
        primary UX per design §11.4 example. The numeric-id fallback
        lets admins or scripted clients claim by id directly when
        the direction-walk isn't convenient.
        """
        if not args:
            await ctx.session.send_line(
                "  Usage: +city claim <direction|room_id>"
            )
            return

        from engine.player_cities import resolve_direction_to_room

        # Disambiguate: pure-integer = room_id; else direction.
        target_room_id = None
        if args.isdigit():
            target_room_id = int(args)
        else:
            # Need the player's current room to resolve direction.
            current_room_id = char.get("room_id")
            if not current_room_id:
                await ctx.session.send_line(
                    "  You must be in a room to claim by direction."
                )
                return
            target_room_id, err = await resolve_direction_to_room(
                ctx.db, current_room_id, args,
            )
            if target_room_id is None:
                await ctx.session.send_line(f"  {err}")
                return

        try:
            # SYN.4 (May 25 2026): route region-anchored cities through
            # the landmark-adjacency API. Look up the player's org city;
            # if it has wilderness_region_id set, the new path applies.
            # Otherwise fall through to the legacy claim_room_for_city.
            faction_code = char.get("faction_id") or "independent"
            city_for_org = None
            if faction_code != "independent":
                try:
                    from engine.player_cities import get_city_by_org
                    org = await ctx.db.get_organization(faction_code)
                    if org:
                        city_for_org = await get_city_by_org(
                            ctx.db, org["id"]
                        )
                except Exception:
                    log.warning(
                        "[city.claim] city-lookup failed for SYN.4 route",
                        exc_info=True,
                    )

            if city_for_org and city_for_org.get("wilderness_region_id"):
                from engine.player_cities import claim_landmark_for_city
                ok, message = await claim_landmark_for_city(
                    ctx.db, char, target_room_id,
                )
            else:
                from engine.player_cities import claim_room_for_city
                ok, message = await claim_room_for_city(
                    ctx.db, char, target_room_id,
                )
        except Exception as e:
            log.exception("[city.claim] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The claim was not "
                "completed."
            )
            return

        if ok:
            await ctx.session.send_line(f"  {ansi.GREEN}{message}{ansi.RESET}")
        else:
            await ctx.session.send_line(f"  {message}")

    # ── +city release ───────────────────────────────────────────────────

    async def _handle_release(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Dispatch `+city release [room_id]`.

        With no args, release the room the player is standing in.
        With a room id, release that specific room. Cannot release
        the City Center (HQ rooms) — the engine enforces this and
        returns an actionable error.
        """
        from engine.player_cities import release_room_from_city

        target_room_id = None
        if args:
            if args.isdigit():
                target_room_id = int(args)
            else:
                await ctx.session.send_line(
                    "  +city release takes a numeric room id. "
                    "With no argument, releases the room you're "
                    "standing in."
                )
                return
        else:
            target_room_id = char.get("room_id")
            if not target_room_id:
                await ctx.session.send_line(
                    "  You are not in a room. "
                    "Usage: +city release <room_id>"
                )
                return

        try:
            ok, message = await release_room_from_city(
                ctx.db, char, target_room_id,
            )
        except Exception as e:
            log.exception("[city.release] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The release was not "
                "completed."
            )
            return

        if ok:
            await ctx.session.send_line(f"  {ansi.YELLOW}{message}{ansi.RESET}")
        else:
            await ctx.session.send_line(f"  {message}")

    # ── Phase 3 handlers ────────────────────────────────────────────────

    async def _resolve_target_by_name(self, ctx, name: str):
        """Resolve a player name to a character row, or return None
        and send a not-found message to the player.
        """
        target = await ctx.db.get_character_by_name(name)
        if not target:
            await ctx.session.send_line(
                f"  No character named {name!r} was found."
            )
            return None
        return target

    async def _send_engine_result(
        self, ctx: CommandContext, ok: bool, message: str,
        *, success_color: str = ansi.GREEN,
    ) -> None:
        """Render an engine (ok, message) tuple."""
        if ok:
            await ctx.session.send_line(
                f"  {success_color}{message}{ansi.RESET}"
            )
        else:
            await ctx.session.send_line(f"  {message}")

    async def _handle_info(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Show info for the city in the player's current room.

        If the player is not standing in a city room, falls back to
        their org's active city (if any). If neither, errors out
        with an actionable usage hint.
        """
        from engine.player_cities import (
            format_city_info, get_city_by_org, get_city_for_room,
        )

        room_id = char.get("room_id")
        city = None
        if room_id:
            try:
                city = await get_city_for_room(ctx.db, int(room_id))
            except Exception as e:
                log.exception("[city.info] room lookup failed: %s", e)

        if not city:
            # Fallback: org's active city
            faction = char.get("faction_id") or "independent"
            if faction != "independent":
                org = await ctx.db.get_organization(faction)
                if org:
                    city = await get_city_by_org(ctx.db, int(org["id"]))

        if not city:
            await ctx.session.send_line(
                "  You are not in a city and your organization has "
                "no active city. Use '+city list' to see all cities."
            )
            return

        try:
            lines = await format_city_info(ctx.db, city, viewer=char)
        except Exception as e:
            log.exception("[city.info] format failed: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred while reading city info."
            )
            return

        for line in lines:
            await ctx.session.send_line(f"  {line}")

    async def _handle_map(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Minimal city map for Phase 3.

        Renders a simple list of city rooms (center first, then
        expansion in claim order). A graphical / ASCII map is a
        Phase 6 polish item per design §13.
        """
        from engine.player_cities import (
            get_city_for_room, get_city_by_org, list_city_room_ids,
        )

        room_id = char.get("room_id")
        city = None
        if room_id:
            try:
                city = await get_city_for_room(ctx.db, int(room_id))
            except Exception as e:
                log.exception("[city.map] room lookup failed: %s", e)
        if not city:
            faction = char.get("faction_id") or "independent"
            if faction != "independent":
                org = await ctx.db.get_organization(faction)
                if org:
                    city = await get_city_by_org(ctx.db, int(org["id"]))

        if not city:
            await ctx.session.send_line(
                "  You are not in a city and your organization has "
                "no active city."
            )
            return

        room_ids = await list_city_room_ids(ctx.db, int(city["id"]))
        await ctx.session.send_line(
            f"  === Map of {city['name']} ==="
        )
        await ctx.session.send_line(
            f"  ({len(room_ids)} rooms total — center + expansion)"
        )
        for rid in room_ids:
            room = await ctx.db.get_room(int(rid))
            if not room:
                continue
            await ctx.session.send_line(
                f"   • [{rid}] {room.get('name', '<unnamed>')}"
            )
        await ctx.session.send_line(
            "  (A graphical map is planned for Phase 6.)"
        )

    async def _handle_citizens(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """List org members (citizens) and guests of the current city."""
        from engine.player_cities import (
            get_city_for_room, get_city_by_org, list_guests,
        )

        room_id = char.get("room_id")
        city = None
        if room_id:
            try:
                city = await get_city_for_room(ctx.db, int(room_id))
            except Exception as e:
                log.exception("[city.citizens] room lookup failed: %s", e)
        if not city:
            faction = char.get("faction_id") or "independent"
            if faction != "independent":
                org = await ctx.db.get_organization(faction)
                if org:
                    city = await get_city_by_org(ctx.db, int(org["id"]))

        if not city:
            await ctx.session.send_line(
                "  You are not in a city and your organization has "
                "no active city."
            )
            return

        # Citizens = org members
        member_rows = await ctx.db.fetchall(
            "SELECT c.id, c.name, m.rank_level FROM org_memberships m "
            "JOIN characters c ON c.id = m.char_id "
            "WHERE m.org_id = ? "
            "ORDER BY m.rank_level DESC, c.name ASC",
            (int(city.get("org_id") or 0),),
        )
        await ctx.session.send_line(
            f"  === Citizens of {city['name']} ==="
        )
        if not member_rows:
            await ctx.session.send_line(
                "  (No citizens — this should not happen.)"
            )
        for r in member_rows:
            await ctx.session.send_line(
                f"   • {r['name']} (rank {r['rank_level']})"
            )

        # Guests
        guest_char_ids = await list_guests(ctx.db, int(city["id"]))
        if guest_char_ids:
            await ctx.session.send_line("  Guests:")
            for gcid in guest_char_ids:
                g = await ctx.db.get_character(int(gcid))
                if g:
                    await ctx.session.send_line(
                        f"   - {g['name']}"
                    )

    async def _handle_list(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """List all active cities. Phase 3 lists globally; per-planet
        filtering deferred to Phase 6 when planet context is firmer.
        """
        from engine.player_cities import (
            list_active_cities, CITY_LIST_PAGE_SIZE,
        )

        cities = await list_active_cities(ctx.db)
        if not cities:
            await ctx.session.send_line(
                "  No active player cities."
            )
            return

        await ctx.session.send_line(
            f"  === Active Player Cities ({len(cities)} total) ==="
        )
        shown = cities[:CITY_LIST_PAGE_SIZE]
        for c in shown:
            org_rows = await ctx.db.fetchall(
                "SELECT name FROM organizations WHERE id = ?",
                (int(c.get("org_id") or 0),),
            )
            org_name = (
                dict(org_rows[0])["name"] if org_rows else "<unknown>"
            )
            await ctx.session.send_line(
                f"   • {c['name']} — {org_name} "
                f"(zone {c.get('zone_id') or '?'})"
            )
        if len(cities) > CITY_LIST_PAGE_SIZE:
            await ctx.session.send_line(
                f"   ... and {len(cities) - CITY_LIST_PAGE_SIZE} more."
            )

    async def _handle_motd(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """Set the city's motd. Mayor/Founder only.

        `+city motd` (no args) clears the motd. The motd may contain
        whitespace; the entire `rest` is taken verbatim.
        """
        from engine.player_cities import set_city_motd

        try:
            ok, message = await set_city_motd(ctx.db, char, args)
        except Exception as e:
            log.exception("[city.motd] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The motd was not set."
            )
            return

        await self._send_engine_result(
            ctx, ok, message, success_color=ansi.YELLOW,
        )

    async def _handle_mayor(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city mayor <player>` — Founder-only reassignment."""
        from engine.player_cities import assign_mayor

        name = (args or "").strip()
        if not name:
            await ctx.session.send_line(
                "  Usage: +city mayor <player>"
            )
            return

        target = await self._resolve_target_by_name(ctx, name)
        if not target:
            return

        try:
            ok, message = await assign_mayor(
                ctx.db, char, int(target["id"]),
            )
        except Exception as e:
            log.exception("[city.mayor] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The Mayor was not "
                "reassigned."
            )
            return

        await self._send_engine_result(ctx, ok, message)

    async def _handle_guards(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city guards [assign <room_id>|remove <npc_id>]`.

        Phase 7 (May 23 2026): the view-only stub becomes a real
        Mayor/Founder management surface.

          +city guards                    — list assigned guards
          +city guards assign <room_id>   — station a guard
          +city guards remove <npc_id>    — remove a guard

        Assignment + removal require Mayor or Founder (enforced
        by the engine helpers); listing is open to anyone in
        the city (matches +city info etc.).
        """
        from engine.player_cities import (
            get_city_for_room, get_city_by_org,
            assign_city_guard, remove_city_guard,
            format_city_guards_lines,
        )

        # Resolve city: prefer the room the player is in, fall
        # back to their org's city. Same lookup pattern as the
        # prior Phase 3 stub.
        room_id = char.get("room_id")
        city = None
        if room_id:
            try:
                city = await get_city_for_room(ctx.db, int(room_id))
            except Exception as e:
                log.exception(
                    "[city.guards] room lookup failed: %s", e,
                )
        if not city:
            faction = char.get("faction_id") or "independent"
            if faction != "independent":
                org = await ctx.db.get_organization(faction)
                if org:
                    city = await get_city_by_org(
                        ctx.db, int(org["id"]),
                    )

        if not city:
            await ctx.session.send_line(
                "  You are not in a city and your organization "
                "has no active city."
            )
            return

        args = (args or "").strip()
        if not args:
            # Bare list — open to all
            lines = await format_city_guards_lines(ctx.db, city)
            for line in lines:
                await ctx.session.send_line(f"  {line}")
            return

        parts = args.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "assign":
            if not rest:
                await ctx.session.send_line(
                    "  Usage: +city guards assign <room_id>"
                )
                return
            try:
                room_id_target = int(rest)
            except ValueError:
                await ctx.session.send_line(
                    f"  Invalid room id: {rest!r}. Must be a "
                    f"number."
                )
                return
            ok, msg, _npc_id = await assign_city_guard(
                ctx.db, char, room_id_target,
            )
            await ctx.session.send_line(f"  {msg}")
            return

        if sub == "remove":
            if not rest:
                await ctx.session.send_line(
                    "  Usage: +city guards remove <npc_id>"
                )
                return
            try:
                npc_id_target = int(rest)
            except ValueError:
                await ctx.session.send_line(
                    f"  Invalid npc id: {rest!r}. Must be a "
                    f"number."
                )
                return
            ok, msg = await remove_city_guard(
                ctx.db, char, npc_id_target,
            )
            await ctx.session.send_line(f"  {msg}")
            return

        await ctx.session.send_line(
            f"  Unknown +city guards action: {sub!r}. "
            f"Use 'assign' or 'remove', or bare '+city guards' "
            f"to list."
        )

    async def _handle_guest(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city guest add|remove <player>`."""
        from engine.player_cities import add_guest, remove_guest

        parts = args.strip().split(None, 1)
        if len(parts) < 2:
            await ctx.session.send_line(
                "  Usage: +city guest add <player>"
            )
            await ctx.session.send_line(
                "         +city guest remove <player>"
            )
            return

        action = parts[0].lower()
        name = parts[1].strip()
        if action not in ("add", "remove"):
            await ctx.session.send_line(
                f"  Unknown guest action: {action!r}. "
                f"Use 'add' or 'remove'."
            )
            return

        target = await self._resolve_target_by_name(ctx, name)
        if not target:
            return

        fn = add_guest if action == "add" else remove_guest
        try:
            ok, message = await fn(ctx.db, char, int(target["id"]))
        except Exception as e:
            log.exception("[city.guest] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The guest list was "
                "not updated."
            )
            return

        await self._send_engine_result(ctx, ok, message)

    async def _handle_banish(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city banish <player>` — Mayor/Founder, 30-day default."""
        from engine.player_cities import banish_player

        name = (args or "").strip()
        if not name:
            await ctx.session.send_line(
                "  Usage: +city banish <player>"
            )
            return

        target = await self._resolve_target_by_name(ctx, name)
        if not target:
            return

        try:
            ok, message = await banish_player(
                ctx.db, char, int(target["id"]),
            )
        except Exception as e:
            log.exception("[city.banish] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The banishment was "
                "not applied."
            )
            return

        await self._send_engine_result(
            ctx, ok, message, success_color=ansi.YELLOW,
        )

    async def _handle_unbanish(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city unbanish <player>` — Mayor/Founder, lift banishment."""
        from engine.player_cities import unbanish_player

        name = (args or "").strip()
        if not name:
            await ctx.session.send_line(
                "  Usage: +city unbanish <player>"
            )
            return

        target = await self._resolve_target_by_name(ctx, name)
        if not target:
            return

        try:
            ok, message = await unbanish_player(
                ctx.db, char, int(target["id"]),
            )
        except Exception as e:
            log.exception("[city.unbanish] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The banishment was "
                "not lifted."
            )
            return

        await self._send_engine_result(ctx, ok, message)

    async def _handle_citizenroom(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city citizenroom on|off [room_id]` — Mayor/Founder.

        With no room_id, operates on the player's current room.
        """
        from engine.player_cities import set_room_citizen_only

        parts = args.strip().split()
        if not parts:
            await ctx.session.send_line(
                "  Usage: +city citizenroom on|off [room_id]"
            )
            return

        flag_token = parts[0].lower()
        if flag_token not in ("on", "off"):
            await ctx.session.send_line(
                f"  Expected 'on' or 'off'; got {flag_token!r}."
            )
            return
        flag = flag_token == "on"

        room_id: int | None = None
        if len(parts) >= 2:
            if not parts[1].isdigit():
                await ctx.session.send_line(
                    "  Room id must be numeric. Omit to use your "
                    "current room."
                )
                return
            room_id = int(parts[1])
        else:
            cur = char.get("room_id")
            if not cur:
                await ctx.session.send_line(
                    "  You are not in a room. Provide a room id."
                )
                return
            room_id = int(cur)

        try:
            ok, message = await set_room_citizen_only(
                ctx.db, char, room_id, flag,
            )
        except Exception as e:
            log.exception("[city.citizenroom] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The room flag was "
                "not changed."
            )
            return

        await self._send_engine_result(ctx, ok, message)

    # ── +city tax (Phase 4) ─────────────────────────────────────────────

    async def _handle_tax(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city tax view | set <pct> | ratecap <pct>`.

        view     — anyone in the city can view
        set      — Mayor or Founder (within rate_cap)
        ratecap  — Founder only (sets the cap, up to 10% absolute)

        Percentages are accepted as either decimals (0.05) or
        percentage points (5 or 5%) — design ergonomics. The engine
        internal representation is always a decimal (0.0-0.10).
        """
        parts = args.strip().split(None, 1)
        sub = (parts[0].lower() if parts else "view")
        rest = parts[1].strip() if len(parts) > 1 else ""

        if sub == "view":
            await self._handle_tax_view(ctx, char)
            return
        if sub == "set":
            await self._handle_tax_set(ctx, char, rest)
            return
        if sub == "ratecap":
            await self._handle_tax_ratecap(ctx, char, rest)
            return

        await ctx.session.send_line(
            f"  Unknown tax action: {sub!r}. "
            f"Use 'view', 'set', or 'ratecap'."
        )

    async def _handle_tax_view(
        self, ctx: CommandContext, char: dict,
    ) -> None:
        """`+city tax view` — render tax dashboard for the active city."""
        from engine.player_cities import (
            format_city_tax_view, get_city_by_org, get_city_for_room,
        )

        # Same lookup pattern as info/map/citizens (current room
        # first, then fall back to the org's active city)
        city = None
        room_id = char.get("room_id")
        if room_id:
            try:
                city = await get_city_for_room(ctx.db, int(room_id))
            except Exception as e:
                log.exception("[city.tax.view] room lookup: %s", e)
        if not city:
            faction = char.get("faction_id") or "independent"
            if faction != "independent":
                org = await ctx.db.get_organization(faction)
                if org:
                    city = await get_city_by_org(ctx.db, int(org["id"]))

        if not city:
            await ctx.session.send_line(
                "  You are not in a city and your organization has "
                "no active city."
            )
            return

        for line in format_city_tax_view(city):
            await ctx.session.send_line(f"  {line}")

    def _parse_pct(self, raw: str) -> tuple[bool, float, str]:
        """Parse a percentage argument as either decimal (0.05) or
        percent (5 or 5%). Returns (ok, decimal_value, err_msg).

        Range-checking is the engine's job — this is shape parsing
        only. Accepted inputs:
            "0"     → 0.0
            "0.05"  → 0.05
            "5"     → 0.05    (5%)
            "5%"    → 0.05
            "10%"   → 0.10
            "0.1"   → 0.1
            "1"     → 0.01    (1% — values >= 1 with no '%' are still
                                treated as percent if the decimal
                                interpretation would exceed 1.0; here
                                "1" is ambiguous, we treat as percent
                                for safety: 1 → 1% → 0.01)
        """
        s = (raw or "").strip()
        if not s:
            return False, 0.0, "No percentage provided."

        had_pct = s.endswith("%")
        if had_pct:
            s = s[:-1].strip()
        if not s:
            return False, 0.0, "No percentage provided."

        try:
            val = float(s)
        except ValueError:
            return False, 0.0, f"Could not parse {raw!r} as a number."

        # If explicit "%", always treat as percent.
        # If no "%" and value > 1, also treat as percent (5 → 0.05).
        # If no "%" and value <= 1, treat as decimal (0.05 stays 0.05).
        # Ambiguous 1 is treated as 1% for safety (caps protect us).
        if had_pct or val > 1.0 or (val == 1.0):
            return True, val / 100.0, ""
        return True, val, ""

    async def _handle_tax_set(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city tax set <pct>` — Mayor or Founder."""
        from engine.player_cities import set_city_tax_rate

        if not args.strip():
            await ctx.session.send_line(
                "  Usage: +city tax set <pct>  (e.g. '5', '5%', or '0.05')"
            )
            return

        ok_parse, rate, err = self._parse_pct(args)
        if not ok_parse:
            await ctx.session.send_line(f"  {err}")
            return

        try:
            ok, message = await set_city_tax_rate(ctx.db, char, rate)
        except Exception as e:
            log.exception("[city.tax.set] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The tax rate was not set."
            )
            return

        await self._send_engine_result(
            ctx, ok, message, success_color=ansi.YELLOW,
        )

    async def _handle_tax_ratecap(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city tax ratecap <pct>` — Founder only."""
        from engine.player_cities import set_city_rate_cap

        if not args.strip():
            await ctx.session.send_line(
                "  Usage: +city tax ratecap <pct>  "
                "(e.g. '10', '10%', or '0.10')"
            )
            return

        ok_parse, cap, err = self._parse_pct(args)
        if not ok_parse:
            await ctx.session.send_line(f"  {err}")
            return

        try:
            ok, message = await set_city_rate_cap(ctx.db, char, cap)
        except Exception as e:
            log.exception("[city.tax.ratecap] error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The rate cap was not set."
            )
            return

        await self._send_engine_result(
            ctx, ok, message, success_color=ansi.YELLOW,
        )

    # ── +city home (Phase 5) ────────────────────────────────────────────

    async def _handle_home(
        self, ctx: CommandContext, char: dict, args: str,
    ) -> None:
        """`+city home` — teleport to the city's HQ entry room.

        Per design §6.4: 1-hour cooldown, same-zone, blocked in
        combat or in space. Citizenship required (founder, mayor,
        or citizen — guests and banished users rejected).

        Engine gate is engine.player_cities.can_use_city_home;
        cooldown stamp is engine.player_cities.record_city_home_use.
        """
        from engine.player_cities import (
            can_use_city_home, record_city_home_use,
        )

        try:
            ok, dest_room_id, reason = await can_use_city_home(
                ctx.db, char,
            )
        except Exception as e:
            log.exception("[city.home] gate error: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred. The teleport "
                "was not performed."
            )
            return

        if not ok:
            await ctx.session.send_line(f"  {reason}")
            return

        # Perform the teleport. Parallel structure to
        # parser/housing_commands.py::_go_home (the personal home).
        try:
            char["room_id"] = int(dest_room_id)
            await ctx.db.save_character(
                char["id"], room_id=int(dest_room_id),
            )
            ctx.session.character["room_id"] = int(dest_room_id)

            # Stamp the cooldown only AFTER the move actually
            # commits; otherwise a save failure would burn the
            # cooldown for free.
            await record_city_home_use(ctx.db, char)

            room = await ctx.db.get_room(int(dest_room_id))
            room_name = room.get("name") if room else "the city"
            await ctx.session.send_line(
                f"  \033[1;36mYou make your way to "
                f"{room_name}.\033[0m"
            )

            # Trigger look (parallel to _go_home)
            registry = getattr(
                ctx.session_mgr, "_registry", None,
            )
            look_cmd = (
                registry.get("look") if registry else None
            )
            if look_cmd:
                from parser.commands import CommandContext as _CC
                look_ctx = _CC(
                    session=ctx.session, raw_input="look",
                    command="look", args="", args_list=[],
                    db=ctx.db, session_mgr=ctx.session_mgr,
                )
                await look_cmd.execute(look_ctx)
        except Exception as e:
            log.exception("[city.home] teleport commit failed: %s", e)
            await ctx.session.send_line(
                "  An internal error occurred mid-teleport. "
                "Please notify staff."
            )

    # ── Phase placeholders ──────────────────────────────────────────────

    async def _phase_placeholder(
        self, ctx: CommandContext, sub: str, phase: int,
    ) -> None:
        msg = _PHASE_MSGS.get(phase, "(coming soon)")
        await ctx.session.send_line(
            f"  +city {sub} is not yet available {msg}."
        )


def register_city_commands(registry) -> None:
    """Register Player Cities Phase 1 commands with the registry.

    Called from server.game_server during command-table init.
    """
    registry.register(CityCommand())
