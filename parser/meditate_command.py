# -*- coding: utf-8 -*-
"""
parser/meditate_command.py — WoW.2b: the +meditate command.

Per weight_of_war_design_v1.md §5.2 ("Active Decay") and §10
("Commands Summary"):

    +meditate at Temple: Spend 1 Force Point, -5 Weight
                         (once per in-game day)

This is the first player-side write command in the Weight of War
track. It exercises the substrate's `decay_weight` helper, the
existing `engine/cooldowns.py` infra, and the `is_jedi_pc`
predicate shipped in WoW.2a.

Substrate decisions
-------------------

1. **"In-game day" = 24h real-time.** Design §5.2 says "once per
   day". The cooldown module tracks real-time seconds. There is
   no separate game-time clock. Documenting the mapping here so a
   future design refinement (e.g. a faster "campaign day" loop)
   knows where to look.

2. **"At Temple" = zone name == 'jedi_temple'.** Resolved
   via room → zone_id → zones.name. The Jedi Temple has 11 rooms
   under the `jedi_temple` zone per data/worlds/clone_wars/
   planets/coruscant.yaml. Any room within that zone qualifies —
   the Council Chamber, the Archives, the meditation chamber, the
   main gate. Design call: this is intentional. A Jedi who walks
   into the gates and sits down to meditate is meditating "at
   the Temple"; the system should not insist on a single meditation-
   only room.

3. **Failure ordering: identity → location → cooldown → fuel →
   no-op.** Friendlier than the raw "you have no FP" first-fail
   pattern: tell the player WHY they can't, in order of how easy
   each problem is to fix.

4. **Weight=0 short-circuits without spending FP or starting the
   cooldown.** Design §5.2 implies a meaningful decay; spending
   an FP and a daily cooldown to drop weight from 0 to 0 is a
   trap. We surface a soft "you are already at peace" message
   and exit — the player keeps their FP and can try again later
   when they actually have weight to shed.

5. **No partial decay.** If weight is 3, meditation still applies
   the full -5 (substrate clamps to floor=0). The player gets the
   FP cost. Design §4.4 wording ("active decay halves in Force
   Point cost") implies the decay-amount and FP-cost are coupled,
   not the floor — so a near-zero player still spends 1 FP.
   This matches the substrate's behavior since `decay_weight(5)`
   on weight=3 returns actual_decay=3 (not 5), but the substrate
   logs the full event and we treat the action as completed.

6. **Cooldown set AFTER the decay write.** If the decay fails for
   any reason (DB error), no cooldown is set — the player can
   retry. The FP refund on DB failure is harder and is not
   attempted; design call: the cooldowns-before-spend pattern
   would be the wrong order because failed cooldown-write
   shouldn't refund FP either. Decay is the canonical "did this
   work" gate.
"""

from __future__ import annotations

import logging

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# Per design §5.2: "once per in-game day". Mapping to 24h real-time.
# If a future design adds a faster game-clock, this constant moves to
# a config seam.
_MEDITATE_COOLDOWN_SECONDS = 86400  # 24h
_MEDITATE_COOLDOWN_KEY = "meditate"

# Per design §5.2: "Spend 1 Force Point, gain -5 Weight"
_MEDITATE_FP_COST = 1
_MEDITATE_WEIGHT_DECAY = 5

# Per data/worlds/clone_wars/planets/coruscant.yaml: 11-room temple
# under zone name 'jedi_temple'.
_TEMPLE_ZONE_NAME = "jedi_temple"


class MeditateCommand(BaseCommand):
    """The +meditate command. Jedi-only, Temple-only, daily,
    spends 1 FP for -5 Weight."""

    key = "+meditate"
    aliases = ["meditate"]
    help_text = (
        "Meditate at the Jedi Temple to ease the Weight of War.\n"
        "\n"
        "  Spends 1 Force Point and reduces your Weight by 5.\n"
        "  Once per day. Must be at the Coruscant Temple.\n"
        "  Jedi only.\n"
        "\n"
        "EXAMPLES:\n"
        "  +meditate"
    )
    usage = "+meditate"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to meditate."
            )
            return

        # ── Failure 1: not a Jedi ─────────────────────────────────────
        from engine.weight_of_war import is_jedi_pc
        if not is_jedi_pc(char):
            await ctx.session.send_line(
                "  Only Jedi may meditate to ease the Weight of War."
            )
            return

        # ── Failure 2: not at the Temple ──────────────────────────────
        if not await self._is_at_temple(ctx.db, char):
            await ctx.session.send_line(
                "  You must be at the Jedi Temple to meditate. "
                "Find your way to the Coruscant Temple."
            )
            return

        # ── Failure 3: cooldown ───────────────────────────────────────
        from engine.cooldowns import (
            check_cooldown, format_remaining, remaining_cooldown,
            set_cooldown,
        )
        if not check_cooldown(char, _MEDITATE_COOLDOWN_KEY):
            rem = remaining_cooldown(char, _MEDITATE_COOLDOWN_KEY)
            await ctx.session.send_line(
                f"  You have meditated recently. "
                f"(next available in {format_remaining(rem)})"
            )
            return

        # ── Failure 4: insufficient Force Points ──────────────────────
        fp = char.get("force_points") or 0
        try:
            fp = int(fp)
        except (TypeError, ValueError):
            fp = 0
        if fp < _MEDITATE_FP_COST:
            await ctx.session.send_line(
                f"  Meditation requires a Force Point. You have none "
                f"to spend."
            )
            return

        # ── Failure 5 (soft): already at peace ────────────────────────
        from engine.weight_of_war import (
            decay_weight, get_descriptor_for_char, get_tier_for_char,
            get_weight,
        )
        current_weight = get_weight(char)
        if current_weight <= 0:
            await ctx.session.send_line(
                f"  You are already at peace; meditation brings "
                f"only quiet. (Force Point preserved.)"
            )
            return

        # ── Success path ──────────────────────────────────────────────
        # Spend FP first (via DB write), then decay, then cooldown.
        # Order: FP-spend and decay are the two "did this cost
        # something" gates. The cooldown is bookkeeping that follows.
        new_fp = fp - _MEDITATE_FP_COST
        try:
            await ctx.db.save_character(char["id"], force_points=new_fp)
        except Exception:
            log.exception("MeditateCommand: FP save failed")
            await ctx.session.send_line(
                "  Something went wrong. Try again in a moment."
            )
            return
        char["force_points"] = new_fp

        try:
            actual_decay = await decay_weight(
                ctx.db, char["id"], _MEDITATE_WEIGHT_DECAY,
                "meditate", "Temple meditation",
            )
        except Exception:
            log.exception("MeditateCommand: decay_weight failed")
            # FP already spent; do not refund (would require a
            # second DB write that could itself fail). The
            # cooldown is NOT set, so the player can retry — the
            # substrate is idempotent and a second meditation
            # would just decay further if it succeeds.
            await ctx.session.send_line(
                "  Your meditation falters. Try again."
            )
            return

        # Update local char dict so subsequent reads in this turn
        # see fresh values.
        char["weight_of_war"] = current_weight - actual_decay

        # Set cooldown. We also persist the updated attributes
        # back to DB so the cooldown survives session loss.
        char = set_cooldown(char, _MEDITATE_COOLDOWN_KEY,
                            _MEDITATE_COOLDOWN_SECONDS)
        try:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}"),
            )
        except Exception:
            log.exception(
                "MeditateCommand: cooldown persist failed (FP and "
                "weight already applied; cooldown will not survive "
                "session loss)",
            )
            # Don't fail user-visibly — the action succeeded; only
            # the cooldown bookkeeping is at risk.

        # ── Render success ────────────────────────────────────────────
        new_weight = char["weight_of_war"]
        new_tier = get_tier_for_char(char)
        await ctx.session.send_line(
            f"  {ansi.color('You settle into meditation. The Force '
                            'steadies you.', ansi.CYAN)}"
        )
        await ctx.session.send_line(
            f"  Weight of War: {current_weight} → {new_weight} "
            f"(-{actual_decay}). Tier: {new_tier}."
        )
        if new_weight > 20:
            await ctx.session.send_line(
                f"    {ansi.color(get_descriptor_for_char(char), ansi.CYAN)}"
            )

    # ── Helpers ─────────────────────────────────────────────────────

    async def _is_at_temple(self, db, char: dict) -> bool:
        """Return True iff the character's current room is inside the
        Coruscant Temple zone."""
        try:
            room = await db.get_room(char["room_id"])
            if not room:
                return False
            zone_id = room.get("zone_id")
            if not zone_id:
                return False
            zone = await db.get_zone(zone_id)
            if not zone:
                return False
            return zone.get("name") == _TEMPLE_ZONE_NAME
        except Exception:
            log.warning(
                "MeditateCommand._is_at_temple: lookup failed; "
                "treating as not-at-Temple",
                exc_info=True,
            )
            return False


def register_meditate_command(registry) -> None:
    """Register the +meditate command. Called from
    server/game_server.py during bootstrap."""
    registry.register(MeditateCommand())
