# -*- coding: utf-8 -*-
"""
parser/admin_security_commands.py — SECMOD.1 admin command layer.

Per security_zones_design_v1.md §9, ships the four-form @security
admin command:

    @security <zone>                       — show level for a zone
    @security <zone> = <level>             — set zone-level security
    @security override <room> = <faction>  — set a room's faction override
    @security override <room> = none       — clear a room's faction override

All four require AccessLevel.ADMIN. Changes write directly to the DB
and take effect immediately (no restart) — the resolver in
engine/security.py reads from DB on every effective-security check.

Substrate decisions
-------------------

1. **Single command, four subforms.** The design §9 names a single
   `@security` verb with parameter-driven dispatch. Following that:
   `AdminSecurityCommand` is one class that parses `args` to pick a
   handler. Matches the `@director` umbrella-command pattern in
   `parser/director_commands.py`.

2. **Zone lookup by name.** `get_zone_by_name` is the canonical
   case-insensitive exact-match lookup; aligns with `set_zone_property`
   docstring's stated SECMOD.1 contract. Partial-match search is
   intentionally NOT supported — ambiguous matches would create
   surprise mutations.

3. **Room lookup by id OR slug.** Admin tooling commonly uses room
   ids; YAML-built rooms also carry a slug. Both unambiguous. We try
   integer parse first (preferred for tooling), then slug lookup. No
   partial-name search — same rationale as zones.

4. **Faction-code validation against `organizations`.** `@security
   override <room> = empire` will reject if there is no
   `organizations.code = 'empire'`. The design's example values
   (empire/rebel/hutt) are not hardcoded — era-clean because the
   organizations table changes between Clone Wars and GCW.

5. **`none` is the canonical clear keyword.** `@security override
   <room> = none` clears via `set_room_faction_override(room_id,
   None)`. Aliases `null`, `clear`, `off` also accepted for builder
   convenience.

6. **Level parsing is lenient.** `@security tatooine = SECURED`,
   `secured`, or `Secured` all work — string is lowercased before the
   `SecurityLevel` enum lookup.

7. **Reads echo what the resolver would return.** `@security <zone>`
   shows the **base** level (from `properties.security`), NOT the
   transient Director override, claim-upgrade-modified, or
   faction-overridden value — those are dynamic and depend on the
   current character. The base is what `@security <zone> = <level>`
   sets, so showing it on read keeps the symmetry.
"""

from __future__ import annotations

import logging
from typing import Optional

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# Accepted level strings. Order = display order on error.
_LEVELS = ("secured", "contested", "lawless")

# Synonyms for "clear the override" in `@security override <room> = X`.
_CLEAR_KEYWORDS = {"none", "null", "clear", "off", "-"}


def _parse_level(token: str) -> Optional[str]:
    """Lenient parse of a security level string. Returns canonical
    lowercase value or None if invalid."""
    if not token:
        return None
    clean = token.strip().lower()
    if clean in _LEVELS:
        return clean
    return None


async def _resolve_room(db, ref: str) -> Optional[dict]:
    """Resolve a room reference — integer id first, slug second.

    Returns the room dict or None if not found. Partial-name search
    is intentionally not attempted (ambiguity hazard for admin
    mutations).
    """
    if not ref:
        return None
    clean = ref.strip()
    if not clean:
        return None
    # Try integer id first
    try:
        room_id = int(clean)
        return await db.get_room(room_id)
    except (ValueError, TypeError):
        pass
    # Fall back to slug
    return await db.get_room_by_slug(clean)


async def _is_known_faction(db, code: str) -> bool:
    """True if `code` is a known organization code."""
    try:
        org = await db.get_organization(code)
        return bool(org)
    except Exception:
        log.warning(
            "[admin_security] organization lookup failed for %r",
            code, exc_info=True,
        )
        return False


def _zone_current_security(zone: dict) -> str:
    """Pull `properties.security` from a zone dict, returning the
    canonical level string or 'contested' as default per
    `security_zones_design_v1.md` §4.1."""
    import json as _json
    props_raw = zone.get("properties") or "{}"
    if isinstance(props_raw, str):
        try:
            props = _json.loads(props_raw)
        except (ValueError, TypeError):
            return "contested"
    elif isinstance(props_raw, dict):
        props = props_raw
    else:
        return "contested"
    val = props.get("security")
    if isinstance(val, str) and val.lower() in _LEVELS:
        return val.lower()
    return "contested"


class AdminSecurityCommand(BaseCommand):
    """The @security umbrella admin command. See module docstring."""

    key = "@security"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Manage zone security and room faction overrides.\n"
        "  @security <zone>                       — show level for a zone\n"
        "  @security <zone> = <level>             — set zone-level security\n"
        "  @security override <room> = <faction>  — set room faction override\n"
        "  @security override <room> = none       — clear faction override\n"
        "\n"
        "<level> is one of: secured, contested, lawless.\n"
        "<room> can be a room id or slug. <faction> is an organization code.\n"
        "Changes take effect immediately — no restart needed."
    )
    usage = "@security <zone> [= <level>] | @security override <room> = <faction|none>"

    async def execute(self, ctx: CommandContext) -> None:
        raw = (ctx.args or "").strip()
        if not raw:
            await self._usage(ctx)
            return

        # Subdispatch on the first token. "override" goes to the
        # override path; anything else is treated as a zone reference.
        first_token = raw.split(None, 1)[0].lower()
        if first_token == "override":
            await self._handle_override(ctx, raw)
        else:
            await self._handle_zone(ctx, raw)

    # ── @security <zone> [= <level>] ────────────────────────────────

    async def _handle_zone(self, ctx: CommandContext, raw: str) -> None:
        if "=" in raw:
            await self._handle_zone_set(ctx, raw)
        else:
            await self._handle_zone_show(ctx, raw)

    async def _handle_zone_show(self, ctx: CommandContext, raw: str) -> None:
        zone_name = raw.strip()
        try:
            zone = await ctx.db.get_zone_by_name(zone_name)
        except Exception:
            log.warning(
                "[admin_security] get_zone_by_name failed for %r",
                zone_name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                f"  Failed to look up zone '{zone_name}' "
                "(see server logs)."
            ))
            return
        if not zone:
            await ctx.session.send_line(ansi.error(
                f"  No zone named '{zone_name}'. "
                "Names are case-insensitive."
            ))
            return
        level = _zone_current_security(zone)
        await ctx.session.send_line(
            f"  Zone '{zone['name']}' (id={zone['id']}): "
            f"security = \033[1;33m{level}\033[0m"
        )

    async def _handle_zone_set(self, ctx: CommandContext, raw: str) -> None:
        left, _, right = raw.partition("=")
        zone_name = left.strip()
        level_token = right.strip()
        if not zone_name:
            await ctx.session.send_line(ansi.error(
                "  Missing zone name. "
                "Usage: @security <zone> = <level>"
            ))
            return
        level = _parse_level(level_token)
        if not level:
            await ctx.session.send_line(ansi.error(
                f"  Invalid level '{level_token}'. "
                f"Must be one of: {', '.join(_LEVELS)}."
            ))
            return
        try:
            zone = await ctx.db.get_zone_by_name(zone_name)
        except Exception:
            log.warning(
                "[admin_security] get_zone_by_name failed for %r",
                zone_name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                f"  Failed to look up zone '{zone_name}'."
            ))
            return
        if not zone:
            await ctx.session.send_line(ansi.error(
                f"  No zone named '{zone_name}'."
            ))
            return
        ok = await ctx.db.set_zone_property(zone["id"], "security", level)
        if not ok:
            await ctx.session.send_line(ansi.error(
                f"  Failed to set security on zone '{zone['name']}' "
                "(zone disappeared between lookup and write)."
            ))
            return
        log.info(
            "[admin_security] @security %s = %s (by char_id=%s)",
            zone["name"], level,
            getattr(ctx.session, "char_id", None),
        )
        await ctx.session.send_line(
            f"  Zone '{zone['name']}' security set to "
            f"\033[1;33m{level}\033[0m. Change is live immediately."
        )

    # ── @security override <room> = <faction|none> ──────────────────

    async def _handle_override(self, ctx: CommandContext, raw: str) -> None:
        # Strip the leading "override" keyword and dispatch.
        rest = raw[len("override"):].strip()
        if not rest:
            await ctx.session.send_line(ansi.error(
                "  Usage: @security override <room> = <faction|none>"
            ))
            return
        if "=" not in rest:
            await ctx.session.send_line(ansi.error(
                "  Missing '='. "
                "Usage: @security override <room> = <faction|none>"
            ))
            return
        left, _, right = rest.partition("=")
        room_ref = left.strip()
        faction_token = right.strip().lower()
        if not room_ref:
            await ctx.session.send_line(ansi.error(
                "  Missing room. "
                "Usage: @security override <room> = <faction|none>"
            ))
            return
        if not faction_token:
            await ctx.session.send_line(ansi.error(
                "  Missing faction (or 'none' to clear). "
                "Usage: @security override <room> = <faction|none>"
            ))
            return

        try:
            room = await _resolve_room(ctx.db, room_ref)
        except Exception:
            log.warning(
                "[admin_security] _resolve_room failed for %r",
                room_ref, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                f"  Failed to look up room '{room_ref}'."
            ))
            return
        if not room:
            await ctx.session.send_line(ansi.error(
                f"  No room found for '{room_ref}' "
                "(pass a room id or slug)."
            ))
            return

        # Clear path
        if faction_token in _CLEAR_KEYWORDS:
            ok = await ctx.db.set_room_faction_override(room["id"], None)
            if not ok:
                await ctx.session.send_line(ansi.error(
                    f"  Failed to clear override on room "
                    f"{room['id']} ('{room.get('name', '?')}')."
                ))
                return
            log.info(
                "[admin_security] @security override room=%s cleared "
                "(by char_id=%s)",
                room["id"],
                getattr(ctx.session, "char_id", None),
            )
            await ctx.session.send_line(
                f"  Faction override on room {room['id']} "
                f"('{room.get('name', '?')}') cleared."
            )
            return

        # Set path
        if not await _is_known_faction(ctx.db, faction_token):
            await ctx.session.send_line(ansi.error(
                f"  Unknown faction code '{faction_token}'. "
                "See 'faction list' for valid codes, or use "
                "'none' to clear."
            ))
            return
        ok = await ctx.db.set_room_faction_override(
            room["id"], faction_token,
        )
        if not ok:
            await ctx.session.send_line(ansi.error(
                f"  Failed to set override on room {room['id']}."
            ))
            return
        log.info(
            "[admin_security] @security override room=%s = %s "
            "(by char_id=%s)",
            room["id"], faction_token,
            getattr(ctx.session, "char_id", None),
        )
        await ctx.session.send_line(
            f"  Faction override on room {room['id']} "
            f"('{room.get('name', '?')}') set to "
            f"\033[1;33m{faction_token}\033[0m. "
            "Hostile/Unfriendly PCs of that faction will now see "
            "this room as LAWLESS instead of SECURED."
        )

    # ── Usage helper ────────────────────────────────────────────────

    async def _usage(self, ctx: CommandContext) -> None:
        for line in self.help_text.splitlines():
            await ctx.session.send_line("  " + line if line else "")


# ── Registration ────────────────────────────────────────────────────


def register_admin_security_commands(registry) -> None:
    """Register the @security admin command. Called from
    server/game_server.py during bootstrap."""
    registry.register(AdminSecurityCommand())
