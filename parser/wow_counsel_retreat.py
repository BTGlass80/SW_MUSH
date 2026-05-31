# -*- coding: utf-8 -*-
"""
parser/wow_counsel_retreat.py — WoW.2c: +counsel and +retreat commands.

Per weight_of_war_design_v1.md §5.2 ("Active Decay") and §10
("Commands Summary"):

    +counsel  → -10 Weight, 1x per week
                  Padawan path: bonded Master in same room
                  Knight/Master path: Council Chamber (room slug
                  'jedi_temple_council_chamber')
    +retreat  → declare extended leave; combat unavailable
    +return   → end retreat; apply -2 weight per real-time day
                elapsed since +retreat, capped at -30 per cycle.

Both commands close WoW Drop 2 alongside WoW.2a (look self + admin)
and WoW.2b (+meditate). After this drop, the WoW MVP launch
criteria for §13 commands are fully implemented; only the runtime
hooks (combat accrual, passive decay tick, DSP/FP wiring) and
+forcebond integration remain — those are WoW.3 and WoW.4.

Substrate decisions
-------------------

1. **Counsel path determined by bond, not rank.** Looking up
   "is this a Padawan" by `org_memberships.rank_level == 0 in
   jedi_order` misses Path-B Force-sensitives who aren't in the
   Order. Looking up by active padawan-bond is robust: if you
   have an active bond AS a padawan, you use the Padawan path
   (need your Master here); otherwise the Knight/Master path
   (need the Council Chamber). A Knight between Padawans
   correctly uses the Council path; a Path-B independent
   correctly uses the Council path. The path is determined by
   "who can hear your counsel" — your bonded Master if you have
   one, the Council if not.

2. **Council Chamber room slug = 'jedi_temple_council_chamber'.**
   The room exists in data/worlds/clone_wars/planets/coruscant.yaml.
   Design call: a specific Council NPC is NOT required to be in
   the room — the chamber itself is hallowed and counsels you.
   This is the "limited by Council NPC availability" line in
   design §5.2 interpreted permissively for launch (Director AI
   would add a flavor NPC at post-launch deep-integration).

3. **+counsel has no FP cost.** Design §5.2 explicitly lists 1 FP
   for +meditate; +counsel and other active-decay channels have
   no FP cost mentioned. Locking that interpretation here:
   counsel costs only time (1x/week cooldown) and venue/bond
   eligibility.

4. **At-peace short-circuit preserves the no-op preventer pattern
   from WoW.2b.** weight=0 means no-op, no cooldown set, friendly
   message. Same design call.

5. **+retreat / +return state lives in attributes JSON, not as a
   schema column.** Two attributes:
     - wow_retreat_active: bool
     - wow_retreat_started_at: float (Unix ts)
   Per the "ship the contract first" pattern: the flag is set
   but no combat-command consumer reads it yet — that wiring
   belongs in WoW.3 alongside other runtime hooks. This drop's
   contract: "retreat state is persisted and consumable by
   future consumers". The decay accumulator does NOT need a tick
   handler — it computes elapsed-days at +return time.

6. **Retreat decay cap of -30 per cycle.** Design §5.2 explicit.
   Days elapsed * 2, capped at 30. The substrate's WEIGHT_MIN
   floor (0) gives the second clamp: if you retreat at weight=5
   and return after 20 days, you get -5 (down to floor) not -30.
   Both clamps apply; the substrate's floor is the inner one.

7. **No "minimum 7 days" hard block.** Design §5.2 says "7+ in-
   game days" which reads as a recommendation, not a gate. A
   player who +retreats and +returns the next day gets -2 (per
   design's daily rate). This is intentional: forcing a 7-day
   minimum on the +return command would block the player from
   ending retreat for emergencies. Design call documented.

8. **+return outside of retreat = friendly error.** "+return"
   when there's no active retreat is a usage error, not a no-op.
   Tell the player.

9. **Re-+retreat while in retreat = friendly error.** Same logic.
   "You are already in retreat. Use +return to end it."

10. **Combat-unavailability wiring deferred to WoW.3.** The flag
    is set; this drop does NOT touch combat.py or any combat
    command to make it refuse. Documented in the +retreat
    success message: "You are now in retreat. (Combat
    refusal will activate in a future update.)" — keeps player
    expectation aligned with the substrate-only nature of this
    drop. The flag persists, so when WoW.3 ships, existing
    retreats become enforceable immediately.
"""

from __future__ import annotations

import json
import logging
import time as _time
from typing import Optional

from parser.commands import BaseCommand, CommandContext
from server import ansi

log = logging.getLogger(__name__)


# Per design §5.2: "once per in-game week". 7 real-time days.
_COUNSEL_COOLDOWN_SECONDS = 7 * 86400
_COUNSEL_COOLDOWN_KEY = "counsel"
_COUNSEL_WEIGHT_DECAY = 10

# Per design §5.2: "cap of -30 per retreat"
_RETREAT_MAX_DECAY = 30
_RETREAT_DAILY_DECAY = 2
_RETREAT_ATTR_ACTIVE = "wow_retreat_active"
_RETREAT_ATTR_STARTED_AT = "wow_retreat_started_at"

# Council Chamber room slug — set in WoW.2c module docstring
# decision #2. The substrate looks the character's current room
# up by slug from `properties.slug` JSON, which is how
# data/worlds/clone_wars/planets/coruscant.yaml ships room slugs.
_COUNCIL_CHAMBER_SLUG = "jedi_temple_council_chamber"


# ─────────────────────────────────────────────────────────────────────
# +counsel
# ─────────────────────────────────────────────────────────────────────

class CounselCommand(BaseCommand):
    """The +counsel command. Jedi-only, 1x per week. Padawan path
    requires bonded Master in same room; Knight/Master path
    requires Council Chamber."""

    key = "+counsel"
    aliases = ["counsel"]
    help_text = (
        "Seek counsel to ease the Weight of War.\n"
        "\n"
        "  -10 Weight, once per week. No Force Point cost.\n"
        "\n"
        "  As a Padawan with a bonded Master: your Master must be\n"
        "    in the same room.\n"
        "  As a Knight or Master: you must be at the Council\n"
        "    Chamber in the Jedi Temple.\n"
        "\n"
        "EXAMPLES:\n"
        "  +counsel"
    )
    usage = "+counsel"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to seek counsel."
            )
            return

        # Identity gate
        from engine.weight_of_war import is_jedi_pc
        if not is_jedi_pc(char):
            await ctx.session.send_line(
                "  Only Jedi may seek counsel for the Weight of War."
            )
            return

        # Cooldown gate
        from engine.cooldowns import (
            check_cooldown, format_remaining, remaining_cooldown,
            set_cooldown,
        )
        if not check_cooldown(char, _COUNSEL_COOLDOWN_KEY):
            rem = remaining_cooldown(char, _COUNSEL_COOLDOWN_KEY)
            await ctx.session.send_line(
                f"  You have sought counsel recently. "
                f"(next available in {format_remaining(rem)})"
            )
            return

        # Path resolution — bond first, then venue
        bond = await ctx.db.get_active_bond_for_padawan(char["id"])
        if bond:
            ok, reason = await self._padawan_path_check(ctx, char, bond)
        else:
            ok, reason = await self._council_path_check(ctx, char)
        if not ok:
            await ctx.session.send_line(f"  {reason}")
            return

        # At-peace short-circuit
        from engine.weight_of_war import (
            decay_weight, get_descriptor_for_char, get_tier_for_char,
            get_weight,
        )
        current_weight = get_weight(char)
        if current_weight <= 0:
            await ctx.session.send_line(
                "  You are already at peace; counsel finds no "
                "burden to ease. (Weekly availability preserved.)"
            )
            return

        # Success path
        try:
            actual_decay = await decay_weight(
                ctx.db, char["id"], _COUNSEL_WEIGHT_DECAY,
                "counsel", self._counsel_event_description(bond),
            )
        except Exception:
            log.exception("CounselCommand: decay_weight failed")
            await ctx.session.send_line(
                "  The counsel falters. Try again."
            )
            return

        char["weight_of_war"] = current_weight - actual_decay

        # Persist cooldown
        char = set_cooldown(
            char, _COUNSEL_COOLDOWN_KEY, _COUNSEL_COOLDOWN_SECONDS,
        )
        try:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}"),
            )
        except Exception:
            log.exception(
                "CounselCommand: cooldown persist failed; weight "
                "already applied",
            )

        # Render
        new_weight = char["weight_of_war"]
        if bond:
            await ctx.session.send_line(
                f"  {ansi.color('You sit with your Master. Words give way to silence; the burden eases.', ansi.CYAN)}"
            )
        else:
            await ctx.session.send_line(
                f"  {ansi.color('In the Council Chamber, you find perspective. The weight settles into bearable shape.', ansi.CYAN)}"
            )
        await ctx.session.send_line(
            f"  Weight of War: {current_weight} → {new_weight} "
            f"(-{actual_decay}). Tier: {get_tier_for_char(char)}."
        )
        if new_weight > 20:
            await ctx.session.send_line(
                f"    {ansi.color(get_descriptor_for_char(char), ansi.CYAN)}"
            )

    # ── Path checks ─────────────────────────────────────────────────

    async def _padawan_path_check(
        self, ctx: CommandContext, char: dict, bond: dict,
    ) -> tuple[bool, str]:
        """Verify the Padawan's bonded Master is in the same room."""
        master_id = bond.get("master_char_id")
        if not master_id:
            return False, (
                "Your bond record is malformed; please contact "
                "staff."
            )
        master = await ctx.db.get_character(master_id)
        if not master:
            return False, (
                "Your Master cannot be found. Have they been "
                "removed from the game?"
            )
        if master.get("room_id") != char.get("room_id"):
            return False, (
                f"Your Master {master['name']} is not here. Counsel "
                "requires you to be in the same room."
            )
        return True, ""

    async def _council_path_check(
        self, ctx: CommandContext, char: dict,
    ) -> tuple[bool, str]:
        """Verify Knight/Master is at the Council Chamber."""
        room = await ctx.db.get_room(char.get("room_id") or 0)
        if not room:
            return False, (
                "You are nowhere; counsel is impossible."
            )
        slug = self._room_slug(room)
        if slug != _COUNCIL_CHAMBER_SLUG:
            return False, (
                "Counsel for Knights and Masters is held in the "
                "Council Chamber at the Jedi Temple. You are not "
                "there."
            )
        return True, ""

    def _room_slug(self, room: dict) -> str:
        """Pull room slug out of properties JSON. Returns '' if not
        a string slug."""
        props_raw = room.get("properties") or "{}"
        if isinstance(props_raw, str):
            try:
                props = json.loads(props_raw)
            except (json.JSONDecodeError, ValueError):
                return ""
        elif isinstance(props_raw, dict):
            props = props_raw
        else:
            return ""
        slug = props.get("slug")
        return slug if isinstance(slug, str) else ""

    def _counsel_event_description(self, bond: Optional[dict]) -> str:
        if bond:
            return "Counsel with bonded Master"
        return "Counsel at the Council Chamber"


# ─────────────────────────────────────────────────────────────────────
# +retreat / +return
# ─────────────────────────────────────────────────────────────────────

class RetreatCommand(BaseCommand):
    """The +retreat command. Declares extended leave of absence;
    accumulates weight decay until +return."""

    key = "+retreat"
    aliases = ["retreat"]
    help_text = (
        "Declare an extended leave of absence from the war.\n"
        "\n"
        "  -2 Weight per real-time day, capped at -30 per retreat.\n"
        "  Use +return to end your retreat and apply accumulated\n"
        "  decay.\n"
        "\n"
        "  While in retreat, you will be combat-unavailable in a\n"
        "  future update; currently this is a state flag only.\n"
        "\n"
        "EXAMPLES:\n"
        "  +retreat"
    )
    usage = "+retreat"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to declare retreat."
            )
            return

        from engine.weight_of_war import is_jedi_pc
        if not is_jedi_pc(char):
            await ctx.session.send_line(
                "  Only Jedi may declare retreat from the war."
            )
            return

        attrs = _parse_attrs(char)
        if attrs.get(_RETREAT_ATTR_ACTIVE):
            started_at = attrs.get(_RETREAT_ATTR_STARTED_AT) or 0
            days = _days_since(started_at)
            await ctx.session.send_line(
                f"  You are already in retreat (started "
                f"~{days} day(s) ago). Use +return to end it."
            )
            return

        # Declare retreat
        attrs[_RETREAT_ATTR_ACTIVE] = True
        attrs[_RETREAT_ATTR_STARTED_AT] = _time.time()
        _write_attrs(char, attrs)
        try:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}"),
            )
        except Exception:
            log.exception("RetreatCommand: persist failed")
            await ctx.session.send_line(
                "  Something went wrong. Try again in a moment."
            )
            return

        await ctx.session.send_line(
            f"  {ansi.color('You withdraw from active duty. The galaxy will turn without you for a time.', ansi.CYAN)}"
        )
        await ctx.session.send_line(
            "  You are now in retreat. Use +return to end your "
            "retreat and apply accumulated decay (-2/day, cap -30)."
        )
        await ctx.session.send_line(
            f"  {ansi.color('(Combat refusal will activate in a future update.)', ansi.DIM)}"
        )


class ReturnCommand(BaseCommand):
    """The +return command. Ends a retreat; applies accumulated
    Weight decay."""

    key = "+return"
    aliases = []
    help_text = (
        "End your retreat and resume active duty.\n"
        "\n"
        "  Applies -2 Weight per real-time day spent in retreat,\n"
        "  capped at -30 per retreat.\n"
        "\n"
        "EXAMPLES:\n"
        "  +return"
    )
    usage = "+return"

    async def execute(self, ctx: CommandContext) -> None:
        char = ctx.session.character
        if not char:
            await ctx.session.send_line(
                "  You must be in the game to return from retreat."
            )
            return

        attrs = _parse_attrs(char)
        if not attrs.get(_RETREAT_ATTR_ACTIVE):
            await ctx.session.send_line(
                "  You are not currently in retreat."
            )
            return

        started_at = attrs.get(_RETREAT_ATTR_STARTED_AT) or 0
        days = _days_since(started_at)
        intended_decay = min(
            days * _RETREAT_DAILY_DECAY, _RETREAT_MAX_DECAY,
        )

        from engine.weight_of_war import (
            decay_weight, get_descriptor_for_char, get_tier_for_char,
            get_weight,
        )
        current_weight = get_weight(char)

        if intended_decay <= 0:
            # Retreat lasted less than a day — no decay applies but
            # we still let them return cleanly.
            actual_decay = 0
        else:
            try:
                actual_decay = await decay_weight(
                    ctx.db, char["id"], intended_decay,
                    "retreat",
                    f"Retreat ended after ~{days} day(s)",
                )
            except Exception:
                log.exception("ReturnCommand: decay_weight failed")
                await ctx.session.send_line(
                    "  The return ritual falters. Try again."
                )
                return

        # Clear retreat flags
        attrs[_RETREAT_ATTR_ACTIVE] = False
        attrs.pop(_RETREAT_ATTR_STARTED_AT, None)
        _write_attrs(char, attrs)
        char["weight_of_war"] = current_weight - actual_decay
        try:
            await ctx.db.save_character(
                char["id"], attributes=char.get("attributes", "{}"),
            )
        except Exception:
            log.exception(
                "ReturnCommand: attribute clear persist failed",
            )

        # Render
        new_weight = char["weight_of_war"]
        await ctx.session.send_line(
            f"  {ansi.color('You return to active duty.', ansi.CYAN)}"
        )
        if actual_decay > 0:
            await ctx.session.send_line(
                f"  Weight of War: {current_weight} → {new_weight} "
                f"(-{actual_decay} over ~{days} day(s)). "
                f"Tier: {get_tier_for_char(char)}."
            )
        else:
            await ctx.session.send_line(
                "  You return before a full day has passed; "
                "no decay applies."
            )
        if new_weight > 20:
            await ctx.session.send_line(
                f"    {ansi.color(get_descriptor_for_char(char), ansi.CYAN)}"
            )


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _parse_attrs(char: dict) -> dict:
    """Parse attributes JSON defensively."""
    raw = char.get("attributes") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    if not isinstance(loaded, dict):
        return {}
    return loaded


def _write_attrs(char: dict, attrs: dict) -> None:
    char["attributes"] = json.dumps(attrs)


def _days_since(ts: float) -> int:
    """Whole real-time days since the given Unix timestamp.
    Returns 0 if ts is in the future or invalid."""
    try:
        ts_f = float(ts)
    except (TypeError, ValueError):
        return 0
    delta = _time.time() - ts_f
    if delta <= 0:
        return 0
    return int(delta // 86400)


def register_wow_counsel_retreat_commands(registry) -> None:
    """Register +counsel, +retreat, +return. Called from
    server/game_server.py during bootstrap."""
    registry.register(CounselCommand())
    registry.register(RetreatCommand())
    registry.register(ReturnCommand())
