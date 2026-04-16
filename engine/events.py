# -*- coding: utf-8 -*-
"""
engine/events.py — Event Calendar for SW_MUSH.

Inspired by AresMUSH Events plugin (see hspace_ares_integration_design_v1.md §5.1).

Players create in-game events (RP nights, PvP tournaments, plot sessions,
social gatherings) with time, location, and description. Other players
sign up. Events appear on the web portal.

Commands (parser/event_commands.py):
  +event/create <title>=<description>   Create a new event
  +event/time <id>=<time>               Set event time (natural format)
  +event/location <id>=<room>           Set event location
  +event/signup <id>                    Sign up for an event
  +event/unsignup <id>                  Remove yourself from event
  +event/cancel <id>                    Cancel your event
  +events                               List upcoming events
  +event <id>                            View event details

Schema (v15 migration):
  game_events         — event records
  game_event_signups  — player signups

Note: Table is named `game_events` to avoid SQL reserved word conflicts.
"""

import logging
import time
from datetime import datetime, timedelta, timezone

log = logging.getLogger(__name__)

# ── Event status constants ─────────────────────────────────────────────────────
STATUS_UPCOMING = "upcoming"
STATUS_ACTIVE = "active"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"


async def create_event(db, creator_id: int, creator_name: str, title: str,
                       description: str = "", location: str = "",
                       scheduled_at: float = None) -> dict:
    """Create a new event. Returns the event dict."""
    now = time.time()
    if scheduled_at is None:
        scheduled_at = now + 86400  # Default: 24 hours from now

    await db.execute(
        """INSERT INTO game_events
           (title, description, location, creator_id, creator_name, status,
            scheduled_at, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (title, description, location, creator_id, creator_name,
         STATUS_UPCOMING, scheduled_at, now)
    )
    await db.commit()
    rows = await db.fetchall(
        "SELECT * FROM game_events WHERE creator_id=? ORDER BY id DESC LIMIT 1",
        (creator_id,)
    )
    row = rows[0] if rows else None
    log.info("Event #%d created by %s: %s", row["id"], creator_name, title)
    return dict(row)


async def get_event(db, event_id: int) -> dict:
    """Get event by ID. Returns dict or None."""
    rows = await db.fetchall(
        "SELECT * FROM game_events WHERE id=?", (event_id,)
    )
    return dict(rows[0]) if rows else None


async def get_upcoming_events(db, limit: int = 20) -> list:
    """Get upcoming events, ordered by scheduled time."""
    rows = await db.fetchall(
        """SELECT * FROM game_events
           WHERE status IN (?, ?)
           ORDER BY scheduled_at ASC
           LIMIT ?""",
        (STATUS_UPCOMING, STATUS_ACTIVE, limit)
    )
    return [dict(r) for r in rows]


async def get_all_events(db, limit: int = 50, include_past: bool = False) -> list:
    """Get all events for portal display."""
    if include_past:
        rows = await db.fetchall(
            "SELECT * FROM game_events ORDER BY scheduled_at DESC LIMIT ?",
            (limit,)
        )
    else:
        rows = await db.fetchall(
            """SELECT * FROM game_events
               WHERE status IN (?, ?)
               ORDER BY scheduled_at ASC LIMIT ?""",
            (STATUS_UPCOMING, STATUS_ACTIVE, limit)
        )
    return [dict(r) for r in rows]


async def update_event(db, event_id: int, **kwargs) -> bool:
    """Update event fields. Returns True if updated."""
    allowed = {"title", "description", "location", "scheduled_at", "status"}
    updates = {k: v for k, v in kwargs.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [event_id]
    await db.execute(
        f"UPDATE game_events SET {set_clause} WHERE id=?", tuple(values)
    )
    await db.commit()
    return True


async def cancel_event(db, event_id: int) -> bool:
    """Cancel an event."""
    await db.execute(
        "UPDATE game_events SET status=? WHERE id=?",
        (STATUS_CANCELLED, event_id)
    )
    await db.commit()
    log.info("Event #%d cancelled", event_id)
    return True


async def signup_event(db, event_id: int, char_id: int, char_name: str) -> bool:
    """Sign up for an event. Returns False if already signed up."""
    existing = await db.fetchall(
        "SELECT 1 FROM game_event_signups WHERE event_id=? AND char_id=?",
        (event_id, char_id)
    )
    if existing:
        return False
    await db.execute(
        "INSERT INTO game_event_signups (event_id, char_id, char_name, signed_up_at) VALUES (?, ?, ?, ?)",
        (event_id, char_id, char_name, time.time())
    )
    await db.commit()
    return True


async def unsignup_event(db, event_id: int, char_id: int) -> bool:
    """Remove signup. Returns False if not signed up."""
    existing = await db.fetchall(
        "SELECT 1 FROM game_event_signups WHERE event_id=? AND char_id=?",
        (event_id, char_id)
    )
    if not existing:
        return False
    await db.execute(
        "DELETE FROM game_event_signups WHERE event_id=? AND char_id=?",
        (event_id, char_id)
    )
    await db.commit()
    return True


async def get_signups(db, event_id: int) -> list:
    """Get all signups for an event."""
    rows = await db.fetchall(
        "SELECT char_id, char_name, signed_up_at FROM game_event_signups WHERE event_id=? ORDER BY signed_up_at",
        (event_id,)
    )
    return [dict(r) for r in rows]


async def get_signup_count(db, event_id: int) -> int:
    """Get signup count for an event."""
    rows = await db.fetchall(
        "SELECT COUNT(*) as cnt FROM game_event_signups WHERE event_id=?",
        (event_id,)
    )
    return rows[0]["cnt"] if rows else 0


def parse_event_time(text: str) -> float:
    """Parse a natural time string into a Unix timestamp.

    Supported formats:
      - "tomorrow 8pm"  / "tomorrow 20:00"
      - "2026-04-20 19:00"
      - "+2h" / "+3d" / "+1w"  (relative)
      - "friday 7pm"
      - ISO 8601

    Returns Unix timestamp, raises ValueError on failure.
    """
    text = text.strip().lower()
    now = datetime.now(timezone.utc)

    # Relative: +Nh, +Nd, +Nw
    if text.startswith("+"):
        rest = text[1:].strip()
        if rest.endswith("h"):
            hours = float(rest[:-1])
            return (now + timedelta(hours=hours)).timestamp()
        elif rest.endswith("d"):
            days = float(rest[:-1])
            return (now + timedelta(days=days)).timestamp()
        elif rest.endswith("w"):
            weeks = float(rest[:-1])
            return (now + timedelta(weeks=weeks)).timestamp()
        raise ValueError(f"Unknown relative format: {text}")

    # "tomorrow" prefix
    if text.startswith("tomorrow"):
        target = now + timedelta(days=1)
        time_part = text.replace("tomorrow", "").strip()
        if time_part:
            target = _apply_time_of_day(target, time_part)
        return target.timestamp()

    # Day name: "friday 7pm"
    day_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, day in enumerate(day_names):
        if text.startswith(day):
            days_ahead = (i - now.weekday()) % 7
            if days_ahead == 0:
                days_ahead = 7  # Next occurrence
            target = now + timedelta(days=days_ahead)
            time_part = text.replace(day, "").strip()
            if time_part:
                target = _apply_time_of_day(target, time_part)
            return target.timestamp()

    # ISO / standard datetime: "2026-04-20 19:00"
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M",
                "%Y-%m-%dT%H:%M:%S", "%m/%d/%Y %H:%M", "%m/%d %H:%M"):
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return dt.timestamp()
        except ValueError:
            continue

    raise ValueError(f"Could not parse time: '{text}'. Try formats like 'tomorrow 8pm', '+2d', 'friday 7pm', or '2026-04-20 19:00'.")


def _apply_time_of_day(dt: datetime, time_str: str) -> datetime:
    """Apply a time-of-day string like '8pm', '20:00', '7:30pm' to a date."""
    time_str = time_str.strip()

    # Handle am/pm: "8pm", "7:30pm"
    is_pm = time_str.endswith("pm")
    is_am = time_str.endswith("am")
    if is_pm or is_am:
        time_str = time_str[:-2].strip()

    if ":" in time_str:
        parts = time_str.split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
    else:
        hour = int(time_str)
        minute = 0

    if is_pm and hour < 12:
        hour += 12
    elif is_am and hour == 12:
        hour = 0

    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def format_event_time(timestamp: float) -> str:
    """Format a Unix timestamp as a human-readable string."""
    dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    now = datetime.now(timezone.utc)
    diff = timestamp - now.timestamp()

    time_str = dt.strftime("%a %b %d, %Y %H:%M UTC")

    if diff < 0:
        return f"{time_str} (past)"
    elif diff < 3600:
        return f"{time_str} (in {int(diff/60)}min)"
    elif diff < 86400:
        return f"{time_str} (in {int(diff/3600)}h)"
    elif diff < 604800:
        return f"{time_str} (in {int(diff/86400)}d)"
    else:
        return time_str
