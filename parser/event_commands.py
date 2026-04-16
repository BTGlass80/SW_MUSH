# -*- coding: utf-8 -*-
"""
parser/event_commands.py — Event Calendar Commands for SW_MUSH.

  +events                                List upcoming events
  +event <id>                            View event details
  +event/create <title>=<description>    Create a new event
  +event/time <id>=<time>                Set event time
  +event/location <id>=<location>        Set event location
  +event/signup <id>                     Sign up for an event
  +event/unsignup <id>                   Remove your signup
  +event/cancel <id>                     Cancel your event (creator only)
"""

import logging
from parser.commands import BaseCommand, CommandContext

log = logging.getLogger(__name__)


class EventsCommand(BaseCommand):
    """List upcoming events."""
    key = "+events"
    aliases = ["+event/list", "+calendar"]
    help_category = "Social"
    help_text = "List upcoming events. Shows title, time, location, signup count."

    async def execute(self, ctx: CommandContext):
        from engine.events import get_upcoming_events, get_signup_count, format_event_time
        events = await get_upcoming_events(ctx.db, limit=20)
        if not events:
            await ctx.session.send_line("No upcoming events scheduled.")
            await ctx.session.send_line("Use +event/create <title>=<description> to schedule one!")
            return

        lines = ["\x1b[33m═══ UPCOMING EVENTS ═══\x1b[0m"]
        for ev in events:
            count = await get_signup_count(ctx.db, ev["id"])
            time_str = format_event_time(ev["scheduled_at"])
            loc = f" @ {ev['location']}" if ev.get("location") else ""
            status_tag = ""
            if ev["status"] == "active":
                status_tag = " \x1b[92m[ACTIVE]\x1b[0m"
            lines.append(
                f"  \x1b[96m#{ev['id']}\x1b[0m {ev['title']}{status_tag}"
            )
            lines.append(
                f"      \x1b[2m{time_str}{loc} · {count} signed up · by {ev['creator_name']}\x1b[0m"
            )
        lines.append("")
        lines.append("\x1b[2mUse +event <id> for details. +event/signup <id> to sign up.\x1b[0m")
        await ctx.session.send_line("\r\n".join(lines))


class EventDetailCommand(BaseCommand):
    """View event details."""
    key = "+event"
    help_category = "Social"
    help_text = "View event details: +event <id>"

    async def execute(self, ctx: CommandContext):
        # Dispatch sub-commands via switches
        if ctx.switches:
            sub = ctx.switches[0]
            if sub == "create":
                return await _cmd_event_create(ctx)
            elif sub == "time":
                return await _cmd_event_time(ctx)
            elif sub == "location":
                return await _cmd_event_location(ctx)
            elif sub == "signup" or sub == "join":
                return await _cmd_event_signup(ctx)
            elif sub == "unsignup" or sub == "leave":
                return await _cmd_event_unsignup(ctx)
            elif sub == "cancel":
                return await _cmd_event_cancel(ctx)
            else:
                await ctx.session.send_line(
                    f"Unknown switch: /{sub}. "
                    f"Valid: /create, /time, /location, /signup, /unsignup, /cancel")
                return

        if not ctx.args or not ctx.args.strip():
            await ctx.session.send_line("Usage: +event <id>")
            return

        try:
            event_id = int(ctx.args.strip().lstrip("#"))
        except ValueError:
            await ctx.session.send_line("Usage: +event <number>")
            return

        from engine.events import get_event, get_signups, format_event_time
        ev = await get_event(ctx.db, event_id)
        if not ev:
            await ctx.session.send_line(f"Event #{event_id} not found.")
            return

        signups = await get_signups(ctx.db, event_id)
        time_str = format_event_time(ev["scheduled_at"])

        lines = [f"\x1b[33m═══ EVENT #{ev['id']}: {ev['title']} ═══\x1b[0m"]
        lines.append(f"  \x1b[96mStatus:\x1b[0m  {ev['status'].title()}")
        lines.append(f"  \x1b[96mTime:\x1b[0m    {time_str}")
        if ev.get("location"):
            lines.append(f"  \x1b[96mLocation:\x1b[0m {ev['location']}")
        lines.append(f"  \x1b[96mCreator:\x1b[0m {ev['creator_name']}")
        if ev.get("description"):
            lines.append(f"  \x1b[96mDetails:\x1b[0m")
            for line in ev["description"].split("\n"):
                lines.append(f"    {line}")

        if signups:
            lines.append(f"  \x1b[96mSignups ({len(signups)}):\x1b[0m")
            for s in signups:
                lines.append(f"    - {s['char_name']}")
        else:
            lines.append(f"  \x1b[2mNo signups yet.\x1b[0m")

        lines.append("")
        char_id = ctx.session.character["id"]
        is_signed = any(s["char_id"] == char_id for s in signups)
        if is_signed:
            lines.append("\x1b[2mYou are signed up. +event/unsignup %d to remove.\x1b[0m" % event_id)
        else:
            lines.append("\x1b[2m+event/signup %d to sign up.\x1b[0m" % event_id)

        await ctx.session.send_line("\r\n".join(lines))


# ── Sub-command handlers ───────────────────────────────────────────────────────

async def _cmd_event_create(ctx: CommandContext):
    """Create a new event: +event/create <title>=<description>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +event/create <title>=<description>")
        await ctx.session.send_line("Then use +event/time <id>=<time> and +event/location <id>=<room>")
        return

    title, _, desc = ctx.args.partition("=")
    title = title.strip()
    desc = desc.strip()

    if not title:
        await ctx.session.send_line("Event title required.")
        return
    if len(title) > 80:
        await ctx.session.send_line("Title too long (80 char max).")
        return

    from engine.events import create_event
    ev = await create_event(
        ctx.db,
        creator_id=ctx.session.character["id"],
        creator_name=ctx.session.character["name"],
        title=title,
        description=desc,
    )

    await ctx.session.send_line(f"\x1b[92mEvent #{ev['id']} created: {title}\x1b[0m")
    await ctx.session.send_line(f"Set the time: +event/time {ev['id']}=<time>")
    await ctx.session.send_line(f"Set location: +event/location {ev['id']}=<place>")
    await ctx.session.send_line(f"\x1b[2mTime formats: 'tomorrow 8pm', '+2d', 'friday 7pm', '2026-04-20 19:00'\x1b[0m")

    # Send web client event
    try:
        await ctx.session.send_json({
            "type": "event_created",
            "event_id": ev["id"],
            "title": title,
        })
    except Exception as _e:
        log.debug("silent except in parser/event_commands.py:172: %s", _e, exc_info=True)


async def _cmd_event_time(ctx: CommandContext):
    """Set event time: +event/time <id>=<time>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +event/time <id>=<time>")
        await ctx.session.send_line("Formats: 'tomorrow 8pm', '+2d', 'friday 7pm', '2026-04-20 19:00'")
        return

    id_str, _, time_str = ctx.args.partition("=")
    try:
        event_id = int(id_str.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +event/time <id>=<time>")
        return

    from engine.events import get_event, update_event, parse_event_time, format_event_time
    ev = await get_event(ctx.db, event_id)
    if not ev:
        await ctx.session.send_line(f"Event #{event_id} not found.")
        return
    if ev["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the event creator can change the time.")
        return

    try:
        ts = parse_event_time(time_str.strip())
    except ValueError as e:
        await ctx.session.send_line(str(e))
        return

    await update_event(ctx.db, event_id, scheduled_at=ts)
    await ctx.session.send_line(f"\x1b[92mEvent #{event_id} scheduled for {format_event_time(ts)}\x1b[0m")


async def _cmd_event_location(ctx: CommandContext):
    """Set event location: +event/location <id>=<location>"""
    if not ctx.args or "=" not in ctx.args:
        await ctx.session.send_line("Usage: +event/location <id>=<location text>")
        return

    id_str, _, loc = ctx.args.partition("=")
    try:
        event_id = int(id_str.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +event/location <id>=<location text>")
        return

    from engine.events import get_event, update_event
    ev = await get_event(ctx.db, event_id)
    if not ev:
        await ctx.session.send_line(f"Event #{event_id} not found.")
        return
    if ev["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the event creator can change the location.")
        return

    await update_event(ctx.db, event_id, location=loc.strip())
    await ctx.session.send_line(f"\x1b[92mEvent #{event_id} location set to: {loc.strip()}\x1b[0m")


async def _cmd_event_signup(ctx: CommandContext):
    """Sign up for an event: +event/signup <id>"""
    if not ctx.args:
        await ctx.session.send_line("Usage: +event/signup <id>")
        return

    try:
        event_id = int(ctx.args.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +event/signup <id>")
        return

    from engine.events import get_event, signup_event
    ev = await get_event(ctx.db, event_id)
    if not ev:
        await ctx.session.send_line(f"Event #{event_id} not found.")
        return
    if ev["status"] in ("cancelled", "completed"):
        await ctx.session.send_line(f"Event #{event_id} is {ev['status']} — cannot sign up.")
        return

    ok = await signup_event(
        ctx.db, event_id,
        ctx.session.character["id"],
        ctx.session.character["name"]
    )
    if ok:
        await ctx.session.send_line(f"\x1b[92mSigned up for '{ev['title']}'!\x1b[0m")
    else:
        await ctx.session.send_line("You're already signed up for that event.")


async def _cmd_event_unsignup(ctx: CommandContext):
    """Remove signup from an event: +event/unsignup <id>"""
    if not ctx.args:
        await ctx.session.send_line("Usage: +event/unsignup <id>")
        return

    try:
        event_id = int(ctx.args.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +event/unsignup <id>")
        return

    from engine.events import get_event, unsignup_event
    ev = await get_event(ctx.db, event_id)
    if not ev:
        await ctx.session.send_line(f"Event #{event_id} not found.")
        return

    ok = await unsignup_event(ctx.db, event_id, ctx.session.character["id"])
    if ok:
        await ctx.session.send_line(f"Removed from '{ev['title']}'.")
    else:
        await ctx.session.send_line("You're not signed up for that event.")


async def _cmd_event_cancel(ctx: CommandContext):
    """Cancel an event (creator only): +event/cancel <id>"""
    if not ctx.args:
        await ctx.session.send_line("Usage: +event/cancel <id>")
        return

    try:
        event_id = int(ctx.args.strip().lstrip("#"))
    except ValueError:
        await ctx.session.send_line("Usage: +event/cancel <id>")
        return

    from engine.events import get_event, cancel_event
    ev = await get_event(ctx.db, event_id)
    if not ev:
        await ctx.session.send_line(f"Event #{event_id} not found.")
        return
    if ev["creator_id"] != ctx.session.character["id"]:
        await ctx.session.send_line("Only the event creator can cancel it.")
        return
    if ev["status"] == "cancelled":
        await ctx.session.send_line("Event is already cancelled.")
        return

    await cancel_event(ctx.db, event_id)
    await ctx.session.send_line(f"\x1b[91mEvent #{event_id} '{ev['title']}' has been cancelled.\x1b[0m")


def register_event_commands(registry):
    """Register all event calendar commands."""
    registry.register(EventsCommand())
    registry.register(EventDetailCommand())
