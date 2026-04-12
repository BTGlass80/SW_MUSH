# -*- coding: utf-8 -*-
"""
parser/spacer_quest_commands.py — Player commands for the "From Dust to Stars"
quest chain and the Hutt debt system.

Commands:
    +quest / quest          — Show current objective and progress
    +quest log              — Show completed steps
    +quest abandon          — Abandon the chain (restart from Phase 1)
    debt                    — Show Hutt debt status
    debt pay <amount>       — Make an extra payment
    debt payoff             — Pay off entire balance
    travel <planet>         — Book passage as a quest passenger (Phase 2-3 only)
"""

import json
import logging
import time

from parser.commands import BaseCommand, CommandContext, AccessLevel
from server import ansi

log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# +quest command
# ═══════════════════════════════════════════════════════════════════════

class QuestCommand(BaseCommand):
    key = "+quest"
    aliases = ["quest", "+spacerquest", "+dusttostars"]
    help_text = "View your From Dust to Stars quest progress."
    usage = "+quest  |  +quest log  |  +quest abandon"

    async def execute(self, ctx: CommandContext):
        from engine.spacer_quest import format_quest_display, format_quest_log

        sub = ctx.args.strip().lower() if ctx.args else ""

        if sub == "log":
            text = format_quest_log(ctx.session.character)
            await ctx.session.send_line(text)
            return

        if sub == "abandon":
            await self._handle_abandon(ctx)
            return

        text = format_quest_display(ctx.session.character)
        await ctx.session.send_line(text)

    async def _handle_abandon(self, ctx: CommandContext):
        char = ctx.session.character
        raw = char.get("attributes", "{}")
        attrs = json.loads(raw) if isinstance(raw, str) else (raw or {})

        qs = attrs.get("spacer_quest")
        if not qs:
            await ctx.session.send_line(
                "  You don't have an active spacer quest to abandon.")
            return

        if qs.get("flags", {}).get("chain_complete"):
            await ctx.session.send_line(
                "  Your quest chain is already complete!")
            return

        # Require confirmation — check if they typed "+quest abandon confirm"
        if "confirm" not in ctx.args.lower():
            step = qs.get("step", 1)
            await ctx.session.send_line(
                f"  \033[1;33mWarning:\033[0m This will reset your quest "
                f"chain progress (currently on step {step}/30).")
            await ctx.session.send_line(
                f"  You will lose all step progress but keep earned "
                f"credits, titles, and items.")
            await ctx.session.send_line(
                f"  Type '\033[1;33m+quest abandon confirm\033[0m' to proceed.")
            return

        # Return borrowed ship before clearing quest state
        try:
            from engine.spacer_quest import return_borrowed_ship
            await return_borrowed_ship(ctx.db, char)
        except Exception:
            pass

        # Reset quest state
        del attrs["spacer_quest"]
        char["attributes"] = json.dumps(attrs)
        await ctx.db.save_character(char["id"],
                                     attributes=char["attributes"])
        await ctx.session.send_line(
            "  Quest chain \"From Dust to Stars\" abandoned.")
        await ctx.session.send_line(
            "  You can restart it by visiting Mos Eisley after "
            "completing the starter chain.")


# ═══════════════════════════════════════════════════════════════════════
# debt command
# ═══════════════════════════════════════════════════════════════════════

class DebtCommand(BaseCommand):
    key = "debt"
    aliases = ["+debt"]
    help_text = "View and manage your Hutt Cartel debt."
    usage = "debt  |  debt pay <amount>  |  debt payoff"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        raw = char.get("attributes", "{}")
        attrs = json.loads(raw) if isinstance(raw, str) else (raw or {})
        debt = attrs.get("hutt_debt")

        if not debt or debt.get("principal", 0) <= 0:
            await ctx.session.send_line(
                "  You don't owe anyone anything. Enjoy your freedom.")
            return

        sub = ctx.args.strip().lower() if ctx.args else ""

        if sub.startswith("pay "):
            await self._handle_pay(ctx, char, attrs, debt, sub)
            return

        if sub == "payoff":
            await self._handle_payoff(ctx, char, attrs, debt)
            return

        # Default: show status
        principal = debt.get("principal", 0)
        weekly = debt.get("weekly_payment", 500)
        next_due = debt.get("next_payment_due", 0)
        missed = debt.get("payments_missed", 0)
        paid = debt.get("total_paid", 0)
        payments_remaining = max(1, (principal + weekly - 1) // weekly)

        # Time until next payment
        now = int(time.time())
        seconds_left = max(0, next_due - now)
        days_left = seconds_left // 86400
        hours_left = (seconds_left % 86400) // 3600

        missed_str = ""
        if missed > 0:
            missed_str = f"  \033[1;31mPayments missed: {missed}\033[0m\n"

        display = (
            f"{'='*63}\n"
            f"  \033[1;33mHUTT CARTEL DEBT\033[0m — Drago the Hutt via Grek\n"
            f"{'='*63}\n"
            f"  Principal remaining: {principal:,} credits\n"
            f"  Weekly payment:      {weekly:,} credits (auto-deducted)\n"
            f"  Next payment due:    {days_left}d {hours_left}h\n"
            f"  Payments remaining:  ~{payments_remaining}\n"
            f"  Total paid:          {paid:,} credits\n"
            f"{missed_str}"
            f"  {'─'*44}\n"
            f"  Pay extra: \033[1;33mdebt pay <amount>\033[0m\n"
            f"  Pay off:   \033[1;33mdebt payoff\033[0m\n"
            f"{'='*63}"
        )
        await ctx.session.send_line(display)

    async def _handle_pay(self, ctx, char, attrs, debt, sub):
        """Handle 'debt pay <amount>'."""
        try:
            amount = int(sub.split()[1])
        except (IndexError, ValueError):
            await ctx.session.send_line("  Usage: debt pay <amount>")
            return

        if amount <= 0:
            await ctx.session.send_line("  Nice try. Pay a positive amount.")
            return

        credits = char.get("credits", 0)
        principal = debt.get("principal", 0)
        amount = min(amount, principal, credits)

        if amount <= 0:
            if credits <= 0:
                await ctx.session.send_line(
                    "  You don't have any credits to pay with.")
            else:
                await ctx.session.send_line("  No debt to pay.")
            return

        # Deduct
        debt["principal"] -= amount
        debt["total_paid"] = debt.get("total_paid", 0) + amount
        char["credits"] = credits - amount
        attrs["hutt_debt"] = debt
        char["attributes"] = json.dumps(attrs)
        await ctx.db.save_character(char["id"],
                                     credits=char["credits"],
                                     attributes=char["attributes"])

        await ctx.session.send_line(
            f"  \033[1;32mPaid {amount:,} credits toward your debt.\033[0m")
        await ctx.session.send_line(
            f"  Remaining: {debt['principal']:,} credits")

        if debt["principal"] <= 0:
            await self._debt_cleared(ctx, char, attrs)

    async def _handle_payoff(self, ctx, char, attrs, debt):
        """Handle 'debt payoff' — pay entire balance."""
        principal = debt.get("principal", 0)
        credits = char.get("credits", 0)

        if credits < principal:
            await ctx.session.send_line(
                f"  You need {principal:,} credits to pay off the debt. "
                f"You have {credits:,}.")
            return

        debt["principal"] = 0
        debt["total_paid"] = debt.get("total_paid", 0) + principal
        char["credits"] = credits - principal
        attrs["hutt_debt"] = debt
        char["attributes"] = json.dumps(attrs)
        await ctx.db.save_character(char["id"],
                                     credits=char["credits"],
                                     attributes=char["attributes"])

        await ctx.session.send_line(
            f"  \033[1;32mPaid {principal:,} credits. Debt cleared!\033[0m")
        await self._debt_cleared(ctx, char, attrs)

    async def _debt_cleared(self, ctx, char, attrs):
        """Handle debt fully paid off."""
        await ctx.session.send_line(
            f"\n  \033[1;35m[COMLINK]\033[0m Grek: \"Last payment received. "
            f"Your account with Drago the Hutt is closed. Pleasure doing "
            f"business, Captain. Drago says if you ever need capital "
            f"again, his door is open. Better terms for returning "
            f"customers.\"")

        # Award title
        titles = attrs.get("tutorial_titles", [])
        title = "(Debt Free)"
        if title not in titles:
            titles.append(title)
            attrs["tutorial_titles"] = titles
            char["attributes"] = json.dumps(attrs)
            await ctx.db.save_character(char["id"],
                                         attributes=char["attributes"])
            await ctx.session.send_line(
                f"  \033[1;36mTitle earned: {title}\033[0m")


# ═══════════════════════════════════════════════════════════════════════
# travel command (passenger travel for Phase 2-3)
# ═══════════════════════════════════════════════════════════════════════

# Name fragments to identify docking/landing rooms per planet (avoids hardcoded IDs)
_DOCKING_NAME_FRAGMENTS = {
    "tatooine":    "Docking Bay 94",
    "nar_shaddaa": "Nar Shaddaa - Docking Bay",
    "kessel":      "Kessel - Spaceport",
    "corellia":    "Coronet City - Starport Docking",
}

_LANDING_NAME_FRAGMENTS = {
    "tatooine":    "Docking Bay 94 - Pit Floor",
    "narshaddaa":  "Nar Shaddaa - Landing Platform",
    "nar_shaddaa": "Nar Shaddaa - Landing Platform",
    "kessel":      "Kessel - Spaceport Landing",
    "corellia":    "Coronet City - Starport Docking Bay",
}

async def _find_room_id_by_name(db, name_fragment: str):
    """Return the first room ID whose name contains name_fragment."""
    try:
        rooms = await db.find_rooms(name_fragment)
        if rooms:
            return rooms[0]["id"]
    except Exception:
        pass
    return None

async def _player_in_docking_area(db, char, planet: str) -> bool:
    """Return True if char is in any docking room for the given planet."""
    fragment = _DOCKING_NAME_FRAGMENTS.get(planet, "Docking Bay")
    try:
        docking_rooms = await db.find_rooms(fragment)
        docking_ids = {r["id"] for r in docking_rooms}
        return char.get("room_id") in docking_ids
    except Exception:
        return True  # fail open so quest doesn't get stuck


class TravelCommand(BaseCommand):
    key = "travel"
    aliases = ["passage", "bookpassage"]
    help_text = "Book passage to another planet (quest passengers only)."
    usage = "travel <planet>  — tatooine, narshaddaa, kessel, corellia"

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        raw = char.get("attributes", "{}")
        attrs = json.loads(raw) if isinstance(raw, str) else (raw or {})
        qs = attrs.get("spacer_quest")

        # Only works during Phase 2-3 (before player has own ship)
        if not qs:
            await ctx.session.send_line(
                "  You don't have passage booked. "
                "This command is for quest passengers.")
            return

        phase = qs.get("phase", 1)
        if phase < 2 or phase > 3:
            if phase >= 4:
                await ctx.session.send_line(
                    "  You have your own ship now — use 'launch' and "
                    "'hyperspace' instead!")
            else:
                await ctx.session.send_line(
                    "  You're not ready for off-world travel yet. "
                    "Keep working through your quest objectives.")
            return

        dest = ctx.args.strip().lower() if ctx.args else ""
        if not dest:
            await ctx.session.send_line(
                "  Usage: travel <planet>")
            await ctx.session.send_line(
                "  Destinations: tatooine, narshaddaa, kessel, corellia")
            return

        landing_room = await _find_room_id_by_name(
            ctx.db, _LANDING_NAME_FRAGMENTS.get(dest, "Docking Bay")
        )
        if landing_room is None:
            await ctx.session.send_line(
                f"  Unknown destination: {dest}")
            await ctx.session.send_line(
                "  Destinations: tatooine, narshaddaa, kessel, corellia")
            return

        # Check player is in a docking area
        current_room = char.get("room_id", 0)
        in_dock = any([
            await _player_in_docking_area(ctx.db, char, p)
            for p in _DOCKING_NAME_FRAGMENTS
        ])

        if not in_dock:
            await ctx.session.send_line(
                "  You need to be at a docking bay or landing pad "
                "to book passage.")
            return

        # Check not already at destination
        if current_room == landing_room:
            await ctx.session.send_line(
                "  You're already there!")
            return

        # Move the player
        await ctx.session.send_line(
            f"\n  \033[2mYou board a battered freighter bound for "
            f"{dest.replace('_', ' ').title()}. After a day in "
            f"hyperspace watching stars streak past the viewport, "
            f"the ship drops out of lightspeed and docks.\033[0m\n")

        char["room_id"] = landing_room
        await ctx.db.save_character(char["id"], room_id=landing_room)

        # Show the new room
        room = await ctx.db.get_room(landing_room)
        if room:
            await ctx.session.send_line(
                f"  \033[1;37m{room['name']}\033[0m")
            desc = room.get("desc_long") or room.get("desc_short", "")
            if desc:
                await ctx.session.send_line(f"  {desc}")

        # Trigger room_enter for quest checks
        from engine.spacer_quest import check_spacer_quest
        await check_spacer_quest(ctx.session, ctx.db, "room_enter",
                                  room_id=landing_room,
                                  room_name=room.get("name", "") if room else "")


# ═══════════════════════════════════════════════════════════════════════
# Registration
# ═══════════════════════════════════════════════════════════════════════

def register_spacer_quest_commands(registry):
    """Register all spacer quest commands."""
    registry.register(QuestCommand())
    registry.register(DebtCommand())
    registry.register(TravelCommand())
