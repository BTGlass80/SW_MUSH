# -*- coding: utf-8 -*-
"""
parser/admin_weight_commands.py — WoW staff admin command.

Per weight_of_war_design_v1.md §10 ("Commands Summary"): "Admin
command to manually adjust Weight (for staff story purposes)."
Per §7.2 + §14: "Staff can manually adjust Weight for narrative
purposes" combined with Weight-aware FP grants.

Single umbrella command `@weight` with four subforms — staff
WoW management lives at one entry point, not scattered across
multiple admin commands:

    @weight <name>                          — show weight + tier
                                               + FP + last 5 events
    @weight <name> = <value> for <note>     — set weight to <value>
    @weight <name> history [<n>]            — show last <n> events
    @weight <name> fp <delta> [for <reason>] — grant/deduct Force
                                               Points with §7.2
                                               multiplier applied
                                               to positive grants

All four require AccessLevel.ADMIN.

Substrate decisions
-------------------

1. **Single umbrella command, four subforms.** Mirrors
   parser/admin_security_commands.py — one BaseCommand subclass
   that parses ``args`` to dispatch. The fp/history/set forms
   are identified by keyword (``fp``, ``history``) or by ``=``
   presence; bare ``@weight <name>`` is the show form.

2. **Character lookup by name only.** ``db.get_character_by_name``
   is the canonical lookup. Case-insensitive per the column
   collation. No id-based lookup at this drop — staff find a player
   by typing their name, not their internal id. (If a future audit
   need wants id-based addressing, it's a tiny add.)

3. **The ``for <note>`` requirement is enforced parser-side too.**
   ``engine.weight_of_war.set_weight_admin`` raises ValueError if
   admin_note is empty or whitespace. We mirror that at the parser
   layer with a friendlier message so the admin doesn't see a
   stack trace — instead they see "you must include 'for <reason>'
   when setting weight."

4. **Non-Jedi targets accepted but warned.** ``@weight`` is a
   debug/recovery tool, not a play surface. If staff want to inspect
   a non-Jedi character (or set their weight for some unusual
   narrative reason), the command allows it but prints a warning
   line. The substrate's weight column exists on every character
   row (default 0); the design §3 "Jedi only" rule is a play-side
   gate (look-self descriptor, accrual triggers), not a substrate
   gate.

5. **History defaults to 20, caps at 100.** Mirrors the @bounty
   history pattern (read enough to be useful for an audit, capped
   so a wide query can't flood the session).

6. **No batched dispatch.** Each @weight invocation handles exactly
   one character. Multi-character form (``@weight all jedi``) is
   intentionally not in this drop — design §13 lists "admin command"
   singular and "Staff can manually adjust Weight" suggests
   one-at-a-time intent. Future scope if a need emerges.

7. **FP subform applies §7.2 multiplier only to positive deltas
   on Jedi PCs.** Negative deltas (taking FP away — mistake
   recovery, selfish-spend reversal) and non-Jedi targets are
   unmodified. The §7.2 reduction is about awards, not punishment.
"""

from __future__ import annotations

import logging
from typing import Optional

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)


# Default and cap for `@weight <name> history [<n>]`.
_HISTORY_DEFAULT = 20
_HISTORY_CAP = 100


class AdminWeightCommand(BaseCommand):
    """The @weight umbrella admin command. See module docstring."""

    key = "@weight"
    aliases = []
    access_level = AccessLevel.ADMIN
    help_text = (
        "Inspect or adjust a character's Weight of War + Force Points.\n"
        "  @weight <name>                          — show weight + tier "
        "+ FP + last 5 events\n"
        "  @weight <name> = <value> for <note>     — set weight to "
        "<value> (audit-logged; <note> is required)\n"
        "  @weight <name> history [<n>]            — show last <n> "
        "events (default 20, max 100)\n"
        "  @weight <name> fp <delta> [for <reason>] — grant/deduct FP "
        "(positive grants scaled by §7.2 tier)\n"
        "\n"
        "<value> is clamped to [0, 200]. <name> is a character name "
        "(case-insensitive). <delta> is a signed integer.\n"
        "Non-Jedi targets are accepted but flagged with a warning.\n"
        "FP positive grants on Jedi PCs are scaled by Weight tier "
        "(75% / 50% / 25% at 51-100 / 101-150 / 151-200, floored at +1).\n"
        "FP negative deltas (taking FP away) are unmodified."
    )
    usage = (
        "@weight <name> | @weight <name> = <value> for <note> | "
        "@weight <name> history [<n>] | "
        "@weight <name> fp <delta> [for <reason>]"
    )

    async def execute(self, ctx: CommandContext) -> None:
        raw = (ctx.args or "").strip()
        if not raw:
            await self._usage(ctx)
            return

        # Detect set form: `<name> = <value> for <note>`
        if "=" in raw:
            await self._handle_set(ctx, raw)
            return

        # Detect history form: `<name> history [<n>]` and
        # fp form: `<name> fp <delta> [for <reason>]`.
        # Find the keyword position to be robust against names
        # containing the words (rare but possible).
        tokens = raw.split()
        history_idx: Optional[int] = None
        fp_idx: Optional[int] = None
        for i, tok in enumerate(tokens):
            lo = tok.lower()
            if history_idx is None and lo == "history":
                history_idx = i
            if fp_idx is None and lo == "fp":
                fp_idx = i
        if history_idx is not None and history_idx > 0:
            await self._handle_history(ctx, tokens, history_idx)
            return
        if fp_idx is not None and fp_idx > 0:
            await self._handle_fp(ctx, tokens, fp_idx)
            return

        # Otherwise: show form
        await self._handle_show(ctx, raw)

    # ── @weight <name> ──────────────────────────────────────────────

    async def _handle_show(self, ctx: CommandContext, name: str) -> None:
        target = await self._lookup_char(ctx, name)
        if target is None:
            return
        await self._render_show(ctx, target)

    async def _render_show(self, ctx, target: dict) -> None:
        from engine.weight_of_war import (
            get_descriptor_for_char, get_events, get_tier_for_char,
            get_weight, is_jedi_pc, fp_award_after_weight,
        )
        w = get_weight(target)
        tier = get_tier_for_char(target)
        descriptor = get_descriptor_for_char(target)
        fp = int(target.get("force_points") or 0)
        is_jedi = is_jedi_pc(target)

        jedi_note = (
            "" if is_jedi
            else f"  {ansi.color('[non-Jedi PC — Weight not surfaced player-side]', ansi.YELLOW)}\n"
        )

        await ctx.session.send_line(
            f"  {ansi.player_name(target['name'])} — Weight of War"
        )
        await ctx.session.send_line(f"    Weight:      {w} / 200")
        await ctx.session.send_line(f"    Tier:        {tier}")
        await ctx.session.send_line(f"    Descriptor:  {descriptor}")
        await ctx.session.send_line(f"    Force Points: {fp}")
        # If this is a Jedi past the 50-Weight reduction threshold,
        # surface what a +1 FP grant would actually deliver — useful
        # for staff gauging the §7.2 multiplier without computing it.
        if is_jedi and w > 50:
            awarded = fp_award_after_weight(1, w)
            mult_pct = {
                "burdened": "75%",
                "strained": "50%",
                "crushed":  "25%",
            }.get(tier, "100%")
            await ctx.session.send_line(
                f"    (Next +1 FP grant → {awarded} "
                f"[{mult_pct} of requested at this tier; min +1 "
                f"for positive base])"
            )
        if jedi_note:
            await ctx.session.send_line(jedi_note.rstrip("\n"))

        # Last 5 events
        events = await get_events(ctx.db, target["id"], limit=5)
        if events:
            await ctx.session.send_line("    Recent events:")
            for ev in events:
                await ctx.session.send_line(
                    f"      {self._format_event(ev)}"
                )
        else:
            await ctx.session.send_line("    Recent events: (none)")

    # ── @weight <name> = <value> for <note> ─────────────────────────

    async def _handle_set(self, ctx: CommandContext, raw: str) -> None:
        # Parse: <name> = <value> for <note>
        try:
            left, right = raw.split("=", 1)
        except ValueError:
            await self._usage(ctx)
            return

        name = left.strip()
        if not name:
            await ctx.session.send_line(
                "  Missing character name. "
                "Usage: @weight <name> = <value> for <note>"
            )
            return

        right = right.strip()
        # Detect the empty-value case first: if `right` starts with
        # "for " (no value before the keyword), the user typed
        # something like `Anakin = for note` — the value is missing
        # rather than the keyword.
        lower = right.lower()
        if lower.startswith("for ") or lower == "for":
            await ctx.session.send_line(
                "  Missing value. Usage: @weight <name> = <value> "
                "for <note>"
            )
            return
        # Find "for" separator. Use the first occurrence — admins
        # who include "for" in earlier tokens are unusual and the
        # value is normally a bare integer.
        if " for " not in lower:
            await ctx.session.send_line(
                "  You must include 'for <reason>' when setting "
                "weight. Example: @weight Anakin = 100 for "
                "Mortis arc."
            )
            return

        # Split on the first occurrence of " for " (case-insensitive)
        idx = lower.find(" for ")
        value_str = right[:idx].strip()
        note = right[idx + 5:].strip()  # skip " for "

        if not value_str:
            await ctx.session.send_line(
                "  Missing value. Usage: @weight <name> = <value> "
                "for <note>"
            )
            return
        if not note:
            await ctx.session.send_line(
                "  Missing audit reason after 'for'. Required for "
                "the event log."
            )
            return

        try:
            value = int(value_str)
        except ValueError:
            await ctx.session.send_line(
                f"  Weight value must be an integer, got "
                f"{value_str!r}."
            )
            return

        # The substrate clamps to [0, 200], but warn early so the
        # admin knows their requested value won't land exactly.
        if value < 0 or value > 200:
            await ctx.session.send_line(
                f"  Weight value {value} will be clamped to "
                f"[0, 200]."
            )

        target = await self._lookup_char(ctx, name)
        if target is None:
            return

        from engine.weight_of_war import (
            get_weight, set_weight_admin, is_jedi_pc,
        )
        before = get_weight(target)
        try:
            after = await set_weight_admin(
                ctx.db, target["id"], value, note,
            )
        except ValueError as e:
            # Defensive: substrate's own validation (e.g. empty note
            # that slipped through our parser-side check).
            await ctx.session.send_line(f"  Rejected: {e}")
            return

        delta = after - before
        sign = "+" if delta >= 0 else ""
        await ctx.session.send_line(
            f"  {ansi.player_name(target['name'])}: Weight "
            f"{before} → {after} ({sign}{delta}). "
            f"Reason logged: {note!r}"
        )
        if not is_jedi_pc(target):
            await ctx.session.send_line(
                f"  {ansi.color('Note: target is not a Jedi PC. '
                                 'Weight is set but no player-side '
                                 'surface (look self, descriptor) '
                                 'will display it.', ansi.YELLOW)}"
            )

    # ── @weight <name> history [<n>] ────────────────────────────────

    async def _handle_history(
        self, ctx: CommandContext, tokens: list, history_idx: int,
    ) -> None:
        # Name is everything before the `history` token.
        name = " ".join(tokens[:history_idx]).strip()
        if not name:
            await ctx.session.send_line(
                "  Missing character name. "
                "Usage: @weight <name> history [<n>]"
            )
            return

        # Optional limit after `history`.
        limit = _HISTORY_DEFAULT
        if len(tokens) > history_idx + 1:
            try:
                limit = int(tokens[history_idx + 1])
            except ValueError:
                await ctx.session.send_line(
                    f"  history limit must be an integer, got "
                    f"{tokens[history_idx + 1]!r}."
                )
                return
            if limit < 1:
                limit = 1
            if limit > _HISTORY_CAP:
                await ctx.session.send_line(
                    f"  history limit {limit} capped at "
                    f"{_HISTORY_CAP}."
                )
                limit = _HISTORY_CAP

        target = await self._lookup_char(ctx, name)
        if target is None:
            return

        from engine.weight_of_war import get_events, get_weight
        w = get_weight(target)
        events = await get_events(ctx.db, target["id"], limit=limit)
        await ctx.session.send_line(
            f"  {ansi.player_name(target['name'])} — Weight history "
            f"(current: {w}/200, last {len(events)} events):"
        )
        if not events:
            await ctx.session.send_line("    (no events on record)")
            return
        for ev in events:
            await ctx.session.send_line(
                f"    {self._format_event(ev)}"
            )

    # ── @weight <name> fp <delta> [for <reason>] ────────────────────

    async def _handle_fp(
        self, ctx: CommandContext, tokens: list, fp_idx: int,
    ) -> None:
        """Grant or deduct Force Points with §7.2 multiplier
        applied to positive grants on Jedi PCs.

        Parses ``<name>`` from tokens before the ``fp`` keyword,
        and ``<delta> [for <reason>]`` from tokens after.
        """
        import re

        name = " ".join(tokens[:fp_idx]).strip()
        if not name:
            await ctx.session.send_line(
                "  Missing character name. "
                "Usage: @weight <name> fp <delta> [for <reason>]"
            )
            return

        tail = " ".join(tokens[fp_idx + 1:]).strip()
        if not tail:
            await ctx.session.send_line(
                "  Missing delta. "
                "Usage: @weight <name> fp <delta> [for <reason>]"
            )
            return

        m = re.match(
            r"^(?P<delta>[+-]?\d+)(?:\s+for\s+(?P<reason>.+))?$",
            tail, re.IGNORECASE,
        )
        if not m:
            await ctx.session.send_line(
                "  Could not parse delta. "
                "Usage: @weight <name> fp <delta> [for <reason>]"
            )
            return
        delta_raw = int(m.group("delta"))
        reason = (m.group("reason") or "").strip()

        if delta_raw == 0:
            await ctx.session.send_line(
                "  Delta of 0 is a no-op. "
                "Use @weight <name> to inspect."
            )
            return

        target = await self._lookup_char(ctx, name)
        if target is None:
            return

        from engine.weight_of_war import (
            get_weight, is_jedi_pc, fp_award_after_weight,
        )

        current_fp = int(target.get("force_points") or 0)
        weight = get_weight(target)
        is_jedi = is_jedi_pc(target)

        # §7.2 multiplier: positive deltas on Jedi only. Negative
        # deltas (punishment / mistake recovery) and non-Jedi
        # targets are unmodified.
        if delta_raw > 0 and is_jedi:
            effective_delta = fp_award_after_weight(delta_raw, weight)
        else:
            effective_delta = delta_raw

        new_fp = current_fp + effective_delta
        if new_fp < 0:
            new_fp = 0
        # No upper-bound enforcement at this surface; staff override
        # is intentionally permissive. KNIGHT_FP_CAP applies only to
        # the ceremonial grant path in padawan_master_trials.

        try:
            await ctx.db.save_character(
                target["id"], force_points=new_fp,
            )
        except Exception:
            log.exception(
                "[@weight fp] save_character failed for char=%s",
                target.get("id"),
            )
            await ctx.session.send_line(
                "  Something went wrong saving the FP change. "
                "Try again in a moment."
            )
            return

        if delta_raw != effective_delta:
            mod_note = (
                f" (requested {delta_raw:+d}, scaled to "
                f"{effective_delta:+d} by Weight-of-War tier)"
            )
        else:
            mod_note = ""
        line = (
            f"  {ansi.color('@weight fp:', ansi.GREEN)} "
            f"{ansi.player_name(target['name'])} "
            f"FP: {current_fp} → {new_fp}{mod_note}"
        )
        if reason:
            line += f" — {reason}"
        await ctx.session.send_line(line)
        log.info(
            "[@weight fp] char=%s name=%s delta_requested=%+d "
            "delta_effective=%+d weight=%d fp_before=%d "
            "fp_after=%d reason=%r",
            target.get("id"), target.get("name"),
            delta_raw, effective_delta, weight,
            current_fp, new_fp, reason,
        )

    # ── Helpers ─────────────────────────────────────────────────────

    async def _lookup_char(
        self, ctx: CommandContext, name: str,
    ) -> Optional[dict]:
        """Look up a character by name. Sends the not-found message
        and returns None if no match."""
        target = await ctx.db.get_character_by_name(name)
        if target is None:
            await ctx.session.send_line(
                f"  No character named {name!r}."
            )
            return None
        return target

    def _format_event(self, event: dict) -> str:
        """Render one event-log row for display."""
        import time as _time
        delta = event["delta"]
        sign = "+" if delta >= 0 else ""
        # event_at is a Unix REAL; format as ISO-ish UTC short.
        try:
            ts = _time.strftime(
                "%Y-%m-%d %H:%M",
                _time.gmtime(float(event["event_at"])),
            )
        except Exception:
            ts = "?"
        desc = event.get("description") or ""
        desc_tail = f" — {desc}" if desc else ""
        return (
            f"{ts}  {sign}{delta:+4d}  "
            f"{event['trigger_type']!s:<24s}{desc_tail}"
        )

    async def _usage(self, ctx: CommandContext) -> None:
        await ctx.session.send_line(f"  Usage: {self.usage}")


def register_admin_weight_commands(registry) -> None:
    """Register the @weight admin command. Called from
    server/game_server.py during bootstrap."""
    registry.register(AdminWeightCommand())
