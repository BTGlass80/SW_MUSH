# -*- coding: utf-8 -*-
"""
engine/cooldowns.py — Centralized Cooldown Handler for SW_MUSH.

Stores per-character cooldown expiry timestamps in the character's
attributes JSON under a "cooldowns" key.  Each cooldown is identified
by a string key (e.g. "survey", "faction_switch", "trade") and stores
a Unix timestamp of when it expires.

Usage:
    from engine.cooldowns import check_cooldown, set_cooldown, remaining_cooldown

    rem = remaining_cooldown(char, "survey")
    if rem > 0:
        await session.send_line(f"Survey on cooldown for {int(rem)}s.")
        return

    # ... do the action ...
    char = set_cooldown(char, "survey", 300)  # 5 minutes
    await db.save_character(char_id, attributes=char["attributes"])

Design note: This module does NOT persist to DB itself — it modifies
the in-memory char dict's "attributes" JSON string.  The caller is
responsible for saving via db.save_character().  This keeps the handler
pure and avoids hidden DB calls.

Sabacc uses a legacy cooldown pattern (last_sabacc timestamp with
win/loss offset trick) that is intentionally left alone.  New cooldowns
should use this module.
"""

import json
import logging
import time

log = logging.getLogger(__name__)


def _parse_attrs(char: dict) -> dict:
    """Parse the attributes JSON from a character dict."""
    raw = char.get("attributes", "{}") or "{}"
    try:
        return json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        log.warning("[cooldowns] Failed to parse attributes for char %s",
                    char.get("id", "?"))
        return {}


def _write_attrs(char: dict, attrs: dict) -> None:
    """Write attributes dict back to the character dict as JSON string."""
    char["attributes"] = json.dumps(attrs)


def remaining_cooldown(char: dict, cooldown_key: str) -> float:
    """Return seconds remaining on a cooldown, or 0.0 if ready.

    Args:
        char: Character dict (must have "attributes" key).
        cooldown_key: Identifier for the cooldown (e.g. "survey").

    Returns:
        Seconds remaining (float).  0.0 means ready.
    """
    attrs = _parse_attrs(char)
    cooldowns = attrs.get("cooldowns", {})
    expiry = cooldowns.get(cooldown_key, 0.0)
    try:
        expiry = float(expiry)
    except (ValueError, TypeError):
        return 0.0
    rem = expiry - time.time()
    return max(0.0, rem)


def check_cooldown(char: dict, cooldown_key: str) -> bool:
    """Return True if the cooldown has expired (action is ready).

    Args:
        char: Character dict.
        cooldown_key: Identifier for the cooldown.

    Returns:
        True if ready, False if still on cooldown.
    """
    return remaining_cooldown(char, cooldown_key) <= 0.0


def set_cooldown(char: dict, cooldown_key: str,
                 duration_seconds: float) -> dict:
    """Start a cooldown.  Mutates char["attributes"] in place.

    Args:
        char: Character dict.
        cooldown_key: Identifier for the cooldown.
        duration_seconds: How long the cooldown lasts.

    Returns:
        The same char dict (for chaining convenience).
    """
    attrs = _parse_attrs(char)
    if "cooldowns" not in attrs:
        attrs["cooldowns"] = {}
    attrs["cooldowns"][cooldown_key] = time.time() + duration_seconds
    _write_attrs(char, attrs)
    return char


def clear_cooldown(char: dict, cooldown_key: str) -> dict:
    """Force-clear a cooldown.  Mutates char["attributes"] in place.

    Args:
        char: Character dict.
        cooldown_key: Identifier for the cooldown.

    Returns:
        The same char dict (for chaining convenience).
    """
    attrs = _parse_attrs(char)
    cooldowns = attrs.get("cooldowns", {})
    cooldowns.pop(cooldown_key, None)
    if cooldowns:
        attrs["cooldowns"] = cooldowns
    else:
        attrs.pop("cooldowns", None)
    _write_attrs(char, attrs)
    return char


def clear_all_cooldowns(char: dict) -> dict:
    """Clear all cooldowns for a character (admin use).

    Returns:
        The same char dict (for chaining convenience).
    """
    attrs = _parse_attrs(char)
    attrs.pop("cooldowns", None)
    _write_attrs(char, attrs)
    return char


def format_remaining(seconds: float) -> str:
    """Format a cooldown remainder as a human-readable string.

    Examples:
        format_remaining(125)  → "2m 05s"
        format_remaining(3661) → "1h 01m"
        format_remaining(45)   → "45s"
        format_remaining(0)    → "ready"
    """
    if seconds <= 0:
        return "ready"
    s = int(seconds)
    if s >= 3600:
        h = s // 3600
        m = (s % 3600) // 60
        return f"{h}h {m:02d}m"
    if s >= 60:
        m = s // 60
        sec = s % 60
        return f"{m}m {sec:02d}s"
    return f"{s}s"


# ── Cooldown key constants ────────────────────────────────────────────────────
# Using constants avoids typo bugs across modules.

CD_SURVEY         = "survey"
CD_FACTION_SWITCH = "faction_switch"
CD_TRADE          = "trade"

# Durations (seconds)
SURVEY_COOLDOWN_S         = 300   # 5 minutes
FACTION_SWITCH_COOLDOWN_S = 604800  # 7 days
TRADE_COOLDOWN_S          = 30    # 30 seconds between trades
