# -*- coding: utf-8 -*-
"""
parser/admin_fp_commands.py — WoW.3c admin command for Force-Point
awards with Weight-of-War scaling.

Per weight_of_war_design_v1.md §7.2: "Standard WEG awards Force
Points for heroic acts aligned with the light side. Weight of
War reduces the rate."

Until this drop, there was no built-in surface for "GM grants
FP for heroic RP" — staff had to use raw DB tools or piggyback
on ceremonial events (Knighting). This command provides the
canonical surface and bakes in the §7.2 multiplier so a
war-weary Jedi finds their reward genuinely diminished.

Two subforms of @fp:

    @fp <name> <delta> [for <reason>]  — grant or deduct FP
                                          (positive or negative)
    @fp <name>                          — show current FP + Weight tier
                                          and what the next grant of +1
                                          would actually award

The delta is signed. Positive deltas pass through
``engine.weight_of_war.fp_award_after_weight`` to apply the
§7.2 multiplier; negative deltas (taking FP away — e.g. mistake
recovery) are NOT modified, since the §7.2 reduction is about
*awards*, not punitive removal.

All forms require AccessLevel.ADMIN.

Substrate decisions
-------------------

1. **Single umbrella command, two subforms.** Mirrors
   parser/admin_weight_commands.py. The show form is bare
   `@fp <name>`; the grant form is `@fp <name> <delta> [for <reason>]`.

2. **Weight multiplier applies only to non-Jedi → no-op, only to
   Jedi → real multiplier.** A non-Jedi PC granted FP gets the
   raw delta. A Jedi PC at Weight 0-50 gets the raw delta. A
   Jedi PC at Weight 151-200 with a +4 grant gets +1 (25% of 4,
   floored to minimum 1 for positive base).

3. **No event-log integration.** FP changes don't go to the
   weight_of_war_events table — that table is for Weight events,
   not FP events. The admin gets a confirmation line showing the
   effective vs requested delta when they differ; the staff
   audit trail is the standard MUSH `@log` (out of scope here).

4. **No FP_CAP enforcement at this surface.** WEG has soft FP
   caps depending on house rule; this codebase's KNIGHT_FP_CAP
   is +5 above starting (per padawan_master_trials). The @fp
   admin surface is intentionally permissive — staff can grant
   beyond the soft cap for narrative reasons. If a hard cap is
   needed, it goes into ``engine.character`` not here.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# Matches "<delta> [for <reason>]" where <delta> is an integer
# (signed). The "for <reason>" tail is optional but recommended
# for audit clarity.
_GRANT_RE = re.compile(
    r"^(?P<delta>[+-]?\d+)(?:\s+for\s+(?P<reason>.+))?$",
    re.IGNORECASE,
)


class AdminFpCommand(BaseCommand):
    """The @fp umbrella admin command. See module docstring."""

    key = "@fp"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Inspect or adjust a character's Force Points, with the\n"
        "Weight-of-War §7.2 multiplier applied to positive grants\n"
        "for Jedi PCs.\n"
        "\n"
        "  @fp <name>                          — show FP + Weight tier\n"
        "  @fp <name> <delta> [for <reason>]   — grant or deduct FP\n"
        "\n"
        "<delta> is a signed integer. Positive deltas for Jedi PCs\n"
        "are scaled by their current Weight tier (75% at 51-100,\n"
        "50% at 101-150, 25% at 151-200; minimum +1 for positive\n"
        "base). Negative deltas are unmodified.\n"
        "\n"
        "EXAMPLES:\n"
        "  @fp Anakin\n"
        "  @fp Anakin +1 for heroic rescue on Geonosis\n"
        "  @fp Anakin -1 for selfish FP spend reversal"
    )
    usage = (
        "@fp <name> | @fp <name> <delta> [for <reason>]"
    )

    async def execute(self, ctx: CommandContext) -> None:
        raw = (ctx.args or "").strip()
        if not raw:
            await self._usage(ctx)
            return

        # Two tokens minimum for grant form; one token for show.
        # Robustness: a name might be multi-word. Split off the
        # last numeric (with optional sign) as the delta token.
        parts = raw.split()

        # Detect grant form: look for a signed-or-unsigned integer
        # token. The integer can be followed by 'for <reason>'.
        # We scan from left to right and find the first token
        # matching the integer pattern AND having either no more
        # tokens after OR a "for" token after.
        delta_idx: Optional[int] = None
        for i, tok in enumerate(parts):
            if re.match(r"^[+-]?\d+$", tok):
                # If there's a token after, it must be "for"
                if i + 1 < len(parts):
                    if parts[i + 1].lower() == "for":
                        delta_idx = i
                        break
                else:
                    # Last token is the delta — no reason given
                    delta_idx = i
                    break

        if delta_idx is not None:
            name = " ".join(parts[:delta_idx]).strip()
            tail = " ".join(parts[delta_idx:]).strip()
            await self._handle_grant(ctx, name, tail)
            return

        # Show form
        await self._handle_show(ctx, raw)

    async def _usage(self, ctx: CommandContext) -> None:
        await ctx.session.send_line(f"  Usage: {self.usage}")

    async def _handle_show(
        self, ctx: CommandContext, name: str,
    ) -> None:
        target = await ctx.db.get_character_by_name(name)
        if not target:
            await ctx.session.send_line(
                f"  No character named '{name}' found."
            )
            return

        from engine.weight_of_war import (
            get_weight, get_tier_for_char, is_jedi_pc,
            fp_award_after_weight,
        )
        fp = int(target.get("force_points") or 0)
        weight = get_weight(target)
        tier = get_tier_for_char(target)
        is_jedi = is_jedi_pc(target)

        await ctx.session.send_line(
            f"  {ansi.bold(target.get('name'))} — "
            f"FP: {ansi.cyan(str(fp))} | "
            f"Weight: {ansi.yellow(str(weight))} "
            f"({tier}) | "
            f"Jedi: {ansi.green('yes') if is_jedi else 'no'}"
        )

        if is_jedi and weight > 50:
            # Show what a +1 award would actually deliver after
            # the §7.2 multiplier. Useful for the admin to gauge
            # the reduction without having to compute it.
            awarded = fp_award_after_weight(1, weight)
            mult_pct = {
                "burdened": "75%",
                "strained": "50%",
                "crushed": "25%",
            }.get(tier, "100%")
            await ctx.session.send_line(
                f"  Next +1 grant would award {ansi.cyan(str(awarded))} "
                f"FP ({mult_pct} of requested at this Weight tier; "
                f"minimum 1 for positive base)."
            )

    async def _handle_grant(
        self, ctx: CommandContext, name: str, tail: str,
    ) -> None:
        if not name:
            await ctx.session.send_line(
                "  Missing character name. "
                "Usage: @fp <name> <delta> [for <reason>]"
            )
            return

        m = _GRANT_RE.match(tail)
        if not m:
            await ctx.session.send_line(
                "  Could not parse delta. "
                "Usage: @fp <name> <delta> [for <reason>]"
            )
            return

        delta_raw = int(m.group("delta"))
        reason = (m.group("reason") or "").strip()

        if delta_raw == 0:
            await ctx.session.send_line(
                "  Delta of 0 is a no-op. Use @fp <name> to inspect."
            )
            return

        target = await ctx.db.get_character_by_name(name)
        if not target:
            await ctx.session.send_line(
                f"  No character named '{name}' found."
            )
            return

        from engine.weight_of_war import (
            get_weight, is_jedi_pc, fp_award_after_weight,
        )

        current_fp = int(target.get("force_points") or 0)
        weight = get_weight(target)
        is_jedi = is_jedi_pc(target)

        # Apply §7.2 multiplier only to positive deltas for Jedi.
        if delta_raw > 0 and is_jedi:
            effective_delta = fp_award_after_weight(delta_raw, weight)
        else:
            effective_delta = delta_raw

        new_fp = current_fp + effective_delta
        # FP floor is 0 — can't go negative.
        if new_fp < 0:
            new_fp = 0
        # No upper-bound enforcement at this surface (see module
        # docstring). The KNIGHT_FP_CAP in padawan_master_trials
        # is for the ceremonial grant path; this admin surface is
        # the staff override and trusts staff to use it well.

        try:
            await ctx.db.save_character(
                target["id"], force_points=new_fp,
            )
        except Exception:
            log.exception(
                "[@fp] save_character failed for char=%s",
                target.get("id"),
            )
            await ctx.session.send_line(
                "  Something went wrong saving the FP change. "
                "Try again in a moment."
            )
            return

        # Build the confirmation line. If the multiplier reduced
        # the delta, surface that clearly so the admin sees the
        # actual result.
        if delta_raw != effective_delta:
            mod_note = (
                f" (requested {delta_raw:+d}, scaled to "
                f"{effective_delta:+d} by Weight-of-War tier)"
            )
        else:
            mod_note = ""
        line = (
            f"  {ansi.green('@fp:')} {ansi.bold(target.get('name'))} "
            f"FP: {current_fp} → {new_fp}{mod_note}"
        )
        if reason:
            line += f" — {ansi.dim(reason)}"
        await ctx.session.send_line(line)
        log.info(
            "[@fp] char=%s name=%s delta_requested=%+d "
            "delta_effective=%+d weight=%d fp_before=%d "
            "fp_after=%d reason=%r",
            target.get("id"), target.get("name"),
            delta_raw, effective_delta, weight,
            current_fp, new_fp, reason,
        )


def register_admin_fp_commands(registry) -> None:
    """Register the @fp admin command. Called from
    server/game_server.py during bootstrap."""
    registry.register(AdminFpCommand())
