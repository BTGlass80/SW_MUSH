# -*- coding: utf-8 -*-
"""
parser/admin_city_commands.py — Player Cities Phase 6 admin command layer.

Per player_cities_design_v1_2.md §11.5 and §13 Phase 6 ("admin tools"
line of Phase 6 polish). Ships the six-form @city admin command:

    @city list                              — active cities, all planets
    @city inspect <name>                    — detailed status dump
    @city void-banish <city> = <player>     — lift a banishment
    @city set-rate-cap <city> = <pct>       — override the founder rate cap
    @city dissolve <name>                   — force-dissolve (moderation)
    @city rename <old> = <new>              — admin rename

All six require AccessLevel.ADMIN. Mirrors the design pattern of
`parser/admin_security_commands.py` (SECMOD.1) — single class, one
keyword, parameter-driven dispatch.

Substrate decisions
-------------------

1. **Single command, six subforms.** Following the §9 SECMOD.1 pattern,
   `AdminCityCommand` is one class that parses `args` to pick a
   handler. Player-facing `+city` (parser/city_commands.py) stays
   separate to keep player and admin permission gates cleanly
   isolated at the registration layer.

2. **City lookup by name.** Phase 1-5 engine helpers expose
   `get_city_by_name` (case-insensitive exact match). Partial-match
   search is intentionally NOT supported — ambiguous matches would
   create surprise moderation actions on the wrong city.

3. **Character lookup by name.** `db.get_character_by_name` is the
   canonical lookup. Same anti-ambiguity rationale as #2.

4. **`set-rate-cap` accepts percentage shorthand.** `0.05`, `5`, and
   `5%` all parse to 0.05 (5%). Per design §5.4 the absolute ceiling
   is 10% (`MAX_TAX_RATE` constant in engine/player_cities.py); the
   engine helper enforces this so the parser doesn't duplicate the
   check.

5. **`dissolve` does NOT refund the treasury.** Admin moderation is
   not a voluntary winding-down — that's the `+city dissolve` player
   path which goes through `engine.player_cities.dissolve_city` and
   issues a 50% refund. The admin path goes through
   `admin_dissolve_city` which intentionally does not refund.

6. **Equals-sign for two-arg subforms.** `@city void-banish Tatooine = Bob`
   uses `=` to disambiguate city name from player name in cases where
   either could contain spaces. Same convention as `@security <zone>
   = <level>`. Subforms with a single arg (`inspect`, `dissolve`,
   `list`) accept the arg as a plain trailing token.
"""

from __future__ import annotations

import logging
from typing import Optional

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

from engine import player_cities as pc_engine

log = logging.getLogger(__name__)


# Subcommand keywords (dispatch map).
_SUBCOMMANDS = (
    "list", "inspect", "void-banish", "set-rate-cap",
    "dissolve", "rename",
)


def _parse_pct(token: str) -> Optional[float]:
    """Lenient parse of a percentage token. Returns a fraction
    in [0, 1] or None if invalid.

    Accepts:
      - "5"     -> 0.05
      - "5%"    -> 0.05
      - "0.05"  -> 0.05
      - "10%"   -> 0.10
      - "0.10"  -> 0.10

    Heuristic: if the value parses to >= 1.0, treat as a percentage
    (divide by 100). Below 1.0 it's already a fraction. The "%"
    suffix is stripped first and always triggers percentage parsing.
    """
    if token is None:
        return None
    s = token.strip()
    if not s:
        return None
    has_percent = s.endswith("%")
    if has_percent:
        s = s[:-1].strip()
    try:
        v = float(s)
    except ValueError:
        return None
    if has_percent or v >= 1.0:
        v = v / 100.0
    if v < 0:
        return None
    return v


def _split_on_equals(raw: str) -> tuple[str, Optional[str]]:
    """Split `LEFT = RIGHT` on the first `=`. Returns (left, right)
    with whitespace stripped. If no `=` present, returns (raw, None).
    """
    if "=" not in raw:
        return raw.strip(), None
    left, _, right = raw.partition("=")
    return left.strip(), right.strip()


class AdminCityCommand(BaseCommand):
    """The @city umbrella admin command. See module docstring."""

    key = "@city"
    aliases: list[str] = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Manage player cities as an admin.\n"
        "  @city list                                "
        "— list all active cities\n"
        "  @city inspect <name>                      "
        "— detailed city status\n"
        "  @city void-banish <city> = <player>       "
        "— lift a banishment\n"
        "  @city set-rate-cap <city> = <pct>         "
        "— override the founder rate cap (max 10%)\n"
        "  @city dissolve <name>                     "
        "— force-dissolve a city (NO refund)\n"
        "  @city rename <old> = <new>                "
        "— rename an active city\n"
        "\n"
        "Pct accepts 5, 5%, or 0.05.\n"
        "Changes take effect immediately — no restart needed."
    )
    usage = (
        "@city <list|inspect|void-banish|set-rate-cap|"
        "dissolve|rename> [...]"
    )

    async def execute(self, ctx: CommandContext) -> None:
        raw = (ctx.args or "").strip()
        if not raw:
            await self._usage(ctx)
            return

        # First token = subcommand keyword.
        parts = raw.split(None, 1)
        sub = parts[0].lower()
        rest = parts[1] if len(parts) > 1 else ""

        if sub == "list":
            await self._handle_list(ctx, rest)
        elif sub == "inspect":
            await self._handle_inspect(ctx, rest)
        elif sub == "void-banish":
            await self._handle_void_banish(ctx, rest)
        elif sub == "set-rate-cap":
            await self._handle_set_rate_cap(ctx, rest)
        elif sub == "dissolve":
            await self._handle_dissolve(ctx, rest)
        elif sub == "rename":
            await self._handle_rename(ctx, rest)
        else:
            await ctx.session.send_line(ansi.error(
                f"  Unknown @city subcommand '{sub}'. "
                f"Try: {', '.join(_SUBCOMMANDS)}."
            ))

    # ── @city list ──────────────────────────────────────────────────

    async def _handle_list(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        # Optional `all` token includes dissolved cities for audit.
        include_dissolved = rest.strip().lower() in ("all", "*", "dissolved")
        try:
            cities = await pc_engine.list_all_cities(
                ctx.db, include_dissolved=include_dissolved,
            )
        except Exception:
            log.warning(
                "[admin_city] list_all_cities failed", exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                "  Failed to list cities (see server logs)."
            ))
            return

        if not cities:
            scope = "any" if include_dissolved else "active"
            await ctx.session.send_line(
                f"  No {scope} cities on record."
            )
            return

        scope_label = "all cities" if include_dissolved else "active cities"
        await ctx.session.send_line(
            f"  == {scope_label} ({len(cities)}) =="
        )
        for c in cities:
            state = c.get("state", "active")
            hq = c.get("hq_tier", "?")
            rate = float(c.get("tax_rate") or 0.0)
            rooms_n = c.get("revenue_total")  # placeholder for column dump
            name = c.get("name") or "?"
            cid = c.get("id")
            org_id = c.get("org_id")
            line = (
                f"  [{cid:>3}] {name:<28}  "
                f"state={state:<10} tier={hq:<13} "
                f"tax={rate*100:>4.1f}%  org_id={org_id}"
            )
            await ctx.session.send_line(line)

    # ── @city inspect <name> ────────────────────────────────────────

    async def _handle_inspect(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        name = rest.strip()
        if not name:
            await ctx.session.send_line(ansi.error(
                "  Missing city name. Usage: @city inspect <name>"
            ))
            return
        try:
            city = await pc_engine.get_city_by_name(ctx.db, name)
        except Exception:
            log.warning(
                "[admin_city] inspect lookup failed for %r",
                name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                f"  Failed to look up city '{name}' (see server logs)."
            ))
            return
        if not city:
            await ctx.session.send_line(ansi.error(
                f"  No active city named '{name}'."
            ))
            return

        try:
            lines = await pc_engine.format_city_inspect(ctx.db, city)
        except Exception:
            log.warning(
                "[admin_city] format_city_inspect failed for %r",
                name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                f"  Failed to render inspect for '{name}' "
                "(see server logs)."
            ))
            return

        for ln in lines:
            await ctx.session.send_line(ln)

    # ── @city void-banish <city> = <player> ─────────────────────────

    async def _handle_void_banish(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        city_name, target_name = _split_on_equals(rest)
        if not city_name or not target_name:
            await ctx.session.send_line(ansi.error(
                "  Usage: @city void-banish <city> = <player>"
            ))
            return

        admin_name = self._admin_name(ctx)
        try:
            ok, msg = await pc_engine.admin_unbanish(
                ctx.db, city_name, target_name,
                admin_name=admin_name,
            )
        except Exception:
            log.warning(
                "[admin_city] admin_unbanish failed: city=%r target=%r",
                city_name, target_name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                "  Void-banish failed (see server logs)."
            ))
            return

        await ctx.session.send_line(
            f"  {ansi.success(msg)}" if ok else f"  {ansi.error(msg)}"
        )

    # ── @city set-rate-cap <city> = <pct> ───────────────────────────

    async def _handle_set_rate_cap(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        city_name, pct_token = _split_on_equals(rest)
        if not city_name or pct_token is None or pct_token == "":
            await ctx.session.send_line(ansi.error(
                "  Usage: @city set-rate-cap <city> = <pct> "
                "(e.g. 5, 5%, or 0.05)"
            ))
            return

        cap = _parse_pct(pct_token)
        if cap is None:
            await ctx.session.send_line(ansi.error(
                f"  Invalid percentage '{pct_token}'. "
                f"Use a non-negative number like 5, 5%, or 0.05."
            ))
            return

        admin_name = self._admin_name(ctx)
        try:
            ok, msg = await pc_engine.admin_set_rate_cap(
                ctx.db, city_name, cap, admin_name=admin_name,
            )
        except Exception:
            log.warning(
                "[admin_city] admin_set_rate_cap failed: city=%r cap=%r",
                city_name, cap, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                "  Set-rate-cap failed (see server logs)."
            ))
            return

        await ctx.session.send_line(
            f"  {ansi.success(msg)}" if ok else f"  {ansi.error(msg)}"
        )

    # ── @city dissolve <name> ───────────────────────────────────────

    async def _handle_dissolve(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        name = rest.strip()
        if not name:
            await ctx.session.send_line(ansi.error(
                "  Missing city name. Usage: @city dissolve <name>"
            ))
            return

        admin_name = self._admin_name(ctx)
        try:
            ok, msg = await pc_engine.admin_dissolve_city(
                ctx.db, name, admin_name=admin_name,
            )
        except Exception:
            log.warning(
                "[admin_city] admin_dissolve_city failed for %r",
                name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                "  Dissolve failed (see server logs)."
            ))
            return

        await ctx.session.send_line(
            f"  {ansi.success(msg)}" if ok else f"  {ansi.error(msg)}"
        )

    # ── @city rename <old> = <new> ──────────────────────────────────

    async def _handle_rename(
        self, ctx: CommandContext, rest: str,
    ) -> None:
        old_name, new_name = _split_on_equals(rest)
        if not old_name or not new_name:
            await ctx.session.send_line(ansi.error(
                "  Usage: @city rename <old> = <new>"
            ))
            return

        admin_name = self._admin_name(ctx)
        try:
            ok, msg = await pc_engine.admin_rename_city(
                ctx.db, old_name, new_name,
                admin_name=admin_name,
            )
        except Exception:
            log.warning(
                "[admin_city] admin_rename_city failed: %r -> %r",
                old_name, new_name, exc_info=True,
            )
            await ctx.session.send_line(ansi.error(
                "  Rename failed (see server logs)."
            ))
            return

        await ctx.session.send_line(
            f"  {ansi.success(msg)}" if ok else f"  {ansi.error(msg)}"
        )

    # ── Helpers ─────────────────────────────────────────────────────

    def _admin_name(self, ctx: CommandContext) -> str:
        """Resolve a human-readable admin name for audit logs.

        Prefers the character name if the admin is in-game; falls
        back to the account name; defaults to 'admin' if neither
        resolvable (the engine helper signature has a default too).
        """
        sess = ctx.session
        char = getattr(sess, "character", None)
        if char and isinstance(char, dict) and char.get("name"):
            return char["name"]
        acct = getattr(sess, "account", None)
        if acct:
            name = getattr(acct, "name", None) or getattr(acct, "username", None)
            if name:
                return name
        return "admin"

    async def _usage(self, ctx: CommandContext) -> None:
        for line in self.help_text.splitlines():
            await ctx.session.send_line("  " + line if line else "")


# ── Registration ────────────────────────────────────────────────────


def register_admin_city_commands(registry) -> None:
    """Register the @city admin command. Called from
    server/game_server.py during bootstrap."""
    registry.register(AdminCityCommand())
