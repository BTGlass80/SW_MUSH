# -*- coding: utf-8 -*-
"""
engine/room_locks.py — Room-level conditional locks (F.7.e).

Some rooms in world data carry a ``properties.locked_until_flag``
value that names a condition gating entry. A trial example is the
Sealed Sanctum on Tatooine, which carries
``locked_until_flag: spirit_trial_in_progress`` so it stays sealed
until the player is eligible to undertake the Trial of Spirit
(audience + skill + courage + flesh done) and remains open after
they have done the trial (per ``post_quest_open: true``).

Until F.7.e (this drop), no engine consumer read the flag — the
property was world-data-only. F.7.e adds:

  - ``can_enter_locked_room(db, char, room_id) -> (bool, str)`` —
    the gate function. Returns ``(True, "")`` if entry is allowed,
    or ``(False, reason)`` to block.
  - A flag-handler registry mapping flag-name strings to functions
    that take a character dict and return ``(allowed, reason)``.
    Currently registered:
      ``spirit_trial_in_progress`` — open iff Spirit is unlocked
        OR completed.
  - A wired call from ``MoveCommand._check_exit_gates`` so the gate
    actually fires on movement (in
    ``parser/builtin_commands.py``).

Design notes
============

**Why room-level rather than exit-level?**
Exits already carry a ``lock_data`` field handled by
``engine/locks.py``. Adding the same expression-based gate again
on the destination room would double the surface and force every
inbound exit (the Sanctum has only one, but the model should
generalise) to repeat the lock. Reading the flag from the
*destination* room's properties — once — keeps the world data
small and the engine surface minimal.

**Why a flag registry rather than expression evaluation?**
The current flag set is small (one entry today, one or two in the
foreseeable future per the village design). An expression DSL would
be over-engineered. Each flag is a named, vetted, engine-coupled
predicate; the registry pattern keeps the audit trail explicit.
Future drops that need broader flexibility (e.g. arbitrary
chargen-notes flag checks) can layer that on top without disturbing
the registry pattern.

**Admin/builder bypass.**
Admins and builders pass the gate unconditionally. The check uses
the same context shape (``is_admin`` / ``is_builder``) that
``engine/locks.py`` and the housing gate already respect.

**Graceful failure.**
If room properties are missing, malformed, or carry an unknown
flag name, the gate **allows entry** (logs at WARNING for unknown
flags). The runtime cost of failing-open on a misconfigured world
is "the door wasn't locked"; the cost of failing-closed is "the
player can't reach this room at all," which is a much worse
outcome on launch day. The same fail-open posture is used by
``engine/housing.py``'s gates.
"""
from __future__ import annotations

import json
import logging
from typing import Mapping, Optional, Tuple

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Flag handlers
# ─────────────────────────────────────────────────────────────────────────────


def _flag_spirit_trial_in_progress(char: Mapping) -> Tuple[bool, str]:
    """``locked_until_flag: spirit_trial_in_progress``.

    Open iff:
      - the character has cleared the prerequisites for the Trial of
        Spirit (audience + skill + courage + flesh), OR
      - the character has already completed the Trial of Spirit (Path
        C lock-in counts as completion per F.7.c.4 and design §7.3).

    The hook in ``engine/village_trials.py::maybe_handle_yarael_spirit_trial``
    further gates on flesh_done, so this room-level lock and the
    NPC-level lock are belt-and-suspenders.
    """
    # Late import to avoid circulars during engine boot.
    from engine.village_trials import (
        is_spirit_unlocked, is_spirit_trial_done,
    )
    if is_spirit_trial_done(char):
        return (True, "")
    if is_spirit_unlocked(char):
        return (True, "")
    return (
        False,
        "The door is sealed. Master Yarael will lead you in when "
        "you are ready.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────
#
# Mapping flag-name → handler. Handlers take (char) and return
# (allowed: bool, reason: str). When `allowed` is True, `reason` is
# expected to be empty (and is ignored anyway).
#
# Use ``register_flag_handler`` rather than mutating this dict
# directly so we can add validation (e.g. duplicate-name rejection)
# in a future drop without touching the call sites.

_FLAG_HANDLERS = {
    "spirit_trial_in_progress": _flag_spirit_trial_in_progress,
}


def register_flag_handler(flag_name: str, handler) -> None:
    """Register a new room-lock flag handler. Idempotent — re-registering
    the same name with the same handler is a no-op; re-registering with
    a different handler raises ValueError.
    """
    existing = _FLAG_HANDLERS.get(flag_name)
    if existing is not None and existing is not handler:
        raise ValueError(
            f"register_flag_handler: '{flag_name}' is already registered "
            f"with a different handler."
        )
    _FLAG_HANDLERS[flag_name] = handler


def get_registered_flags() -> tuple:
    """Return the registered flag names (for diagnostics / tests)."""
    return tuple(sorted(_FLAG_HANDLERS.keys()))


# ─────────────────────────────────────────────────────────────────────────────
# Property reading
# ─────────────────────────────────────────────────────────────────────────────


def _read_room_properties(room: Optional[Mapping]) -> dict:
    """Return room.properties as a dict.

    The properties column is stored as a JSON string. This helper
    is defensive against missing keys, missing rooms, or malformed
    JSON — all return an empty dict (which means 'no flag', i.e.
    'no lock', i.e. 'allow entry').
    """
    if not room:
        return {}
    raw = room.get("properties") if hasattr(room, "get") else None
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str):
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def get_locked_until_flag(room: Optional[Mapping]) -> str:
    """Return the room's ``locked_until_flag`` property, or '' if absent."""
    props = _read_room_properties(room)
    val = props.get("locked_until_flag")
    if not isinstance(val, str):
        return ""
    return val.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Public gate function
# ─────────────────────────────────────────────────────────────────────────────


async def can_enter_locked_room(
    db, char: Mapping, room_id: int,
    *, lock_ctx: Optional[Mapping] = None,
) -> Tuple[bool, str]:
    """Evaluate the room-level conditional lock for ``room_id``.

    Returns ``(True, "")`` if entry is allowed, ``(False, reason)`` to
    block. Admins and builders pass unconditionally — pass an
    ``lock_ctx`` dict containing ``is_admin`` / ``is_builder`` keys
    (the same shape ``engine.locks.eval_lock`` uses).

    The function is fail-open: if the room has no properties, no
    ``locked_until_flag``, an unknown flag, or any other anomaly,
    entry is allowed. See module docstring for rationale.
    """
    if lock_ctx:
        if lock_ctx.get("is_admin") or lock_ctx.get("is_builder"):
            return (True, "")

    try:
        room = await db.get_room(room_id)
    except Exception:
        log.warning("can_enter_locked_room: get_room raised for "
                    "room_id=%s; allowing entry", room_id, exc_info=True)
        return (True, "")

    flag = get_locked_until_flag(room)
    if not flag:
        return (True, "")

    handler = _FLAG_HANDLERS.get(flag)
    if handler is None:
        log.warning(
            "can_enter_locked_room: unknown locked_until_flag '%s' on "
            "room_id=%s; allowing entry (fail-open)", flag, room_id,
        )
        return (True, "")

    try:
        return handler(char)
    except Exception:
        log.warning(
            "can_enter_locked_room: handler for '%s' raised; allowing "
            "entry (fail-open)", flag, exc_info=True,
        )
        return (True, "")
