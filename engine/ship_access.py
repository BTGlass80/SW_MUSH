# -*- coding: utf-8 -*-
"""
engine/ship_access.py — ship control authorization (Drop 3b.1).

Policy: **open boarding, gated control.** Anyone may ``board`` a docked ship
(stowaway / passenger / piracy-attempt RP stays alive), but only the **owner**
or an **authorized crew member** may take the pilot seat and ``launch``.

The authorized-crew allow-list lives in the ship's ``systems`` JSON under
``authorized_pilots`` (a list of character ids). It is kept separate from the
volatile ``crew`` seat dict (which records *current* seat occupancy) so that
authorizations persist across crew changes, disembarks, and reboots.

**Unowned hulls fail open.** If ``owner_id`` is NULL/0 the ship is treated as
unclaimed (derelicts, salvage, demo/seed ships, and the borrowed quest ship
before its ownership transfer) and anyone may fly it. Every production
player ship — brokerage purchase, builder spawn, quest grant — is created with
a real ``owner_id``, so the theft hole this drop closes is closed wherever it
actually matters.

These functions are intentionally pure (no DB, no I/O) so they unit-test
trivially; the commands in ``parser/space_commands.py`` and
``parser/ship_crew_commands.py`` read/write the ship row and call them.
"""

from __future__ import annotations

AUTH_KEY = "authorized_pilots"


def _as_int(x):
    """Coerce to int, or None. Char ids appear as both int and str across the
    codebase (e.g. ``crew`` seats vs. stringified ids in ShipNameCommand)."""
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def get_authorized_pilots(systems: dict) -> list:
    """Return the de-duplicated list of authorized-pilot char ids (ints)."""
    raw = (systems or {}).get(AUTH_KEY, []) or []
    out: list = []
    for v in raw:
        iv = _as_int(v)
        if iv is not None and iv not in out:
            out.append(iv)
    return out


def is_authorized_pilot(char_id, owner_id, authorized, *, is_admin: bool = False) -> bool:
    """True if ``char_id`` may take the pilot seat / launch this ship.

    Authorized = staff (admin) OR the ship is unowned OR char is the owner OR
    char is on the authorized-crew allow-list.
    """
    if is_admin:
        return True
    oid = _as_int(owner_id)
    if oid is None or oid == 0:
        # Unowned / unclaimed / derelict — anyone may fly it.
        return True
    cid = _as_int(char_id)
    if cid is None:
        return False
    if cid == oid:
        return True
    return cid in {_as_int(a) for a in (authorized or [])}


def add_authorized_pilot(systems: dict, char_id) -> bool:
    """Add ``char_id`` to the allow-list in ``systems`` (mutates in place).
    Returns True if the list changed, False if already present / invalid."""
    cid = _as_int(char_id)
    if cid is None:
        return False
    cur = get_authorized_pilots(systems)
    if cid in cur:
        return False
    cur.append(cid)
    systems[AUTH_KEY] = cur
    return True


def remove_authorized_pilot(systems: dict, char_id) -> bool:
    """Remove ``char_id`` from the allow-list in ``systems`` (mutates in place).
    Returns True if the list changed, False if it wasn't present / invalid."""
    cid = _as_int(char_id)
    if cid is None:
        return False
    cur = get_authorized_pilots(systems)
    if cid not in cur:
        return False
    systems[AUTH_KEY] = [c for c in cur if c != cid]
    return True
