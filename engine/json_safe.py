# -*- coding: utf-8 -*-
"""
engine/json_safe.py — Defensive JSON-from-DB helpers.

Drop K-D5b. Companion to the area_map.py / buffs.py narrowing in the
prior K-D5 drop. Per code_review_session32.md Severity D5, the codebase
has 25 unguarded `json.loads()` call sites that crash on corrupt data.
Most follow this exact pattern:

    sd = json.loads(dict(ship).get("systems") or "{}")

The `or "{}"` only protects against `None` / empty string. A
half-written or hand-edited DB row produces malformed JSON that crashes
the function and (in space tick paths) the entire tick handler.

This module ships two helpers:

    safe_json_loads(s, default)        — generic; returns default on error
    load_ship_systems(ship)            — domain-specific for the dominant
                                         ship-systems pattern

Both log a warning on parse failure so corruption is observable.

The helpers are NOT wired into the live engine in this drop — they
ship as a stable API, ready for individual targeted PRs to swap call
sites in. Bulk editing 25 sites unattended is too risky (some live in
hot space-tick paths). With the helper in place, each follow-up PR
becomes a 1-line replacement.

Tested by tests/test_json_safe.py.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

log = logging.getLogger(__name__)


def safe_json_loads(
    raw: Any,
    default: Any = None,
    *,
    context: Optional[str] = None,
) -> Any:
    """Parse `raw` as JSON, returning `default` on any failure.

    Behavior:
      - If `raw` is None or empty string, returns `default` silently
        (no log — this is the routine "field not set" case).
      - If `raw` is already a dict/list/etc, returns it unchanged
        (no log — this is the "already parsed by aiosqlite row factory"
        case).
      - If `raw` is a string and json.loads succeeds, returns the parsed
        value.
      - If json.loads raises, logs a warning and returns `default`.

    `context` is included in the warning message to help diagnose the
    source of corruption (e.g. context="ship 42 systems"). When None,
    the warning omits a source identifier.

    The default for `default` is None, but callers should pass an
    explicit value matching the expected schema — typically `{}` for
    object-shaped fields and `[]` for array-shaped fields. Returning
    `None` instead of the right empty-shape often causes downstream
    `'NoneType' object has no attribute 'get'` errors, defeating the
    point of the guard.
    """
    if raw is None:
        return default
    if isinstance(raw, str):
        if not raw:
            return default
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError) as e:
            if context:
                log.warning(
                    "[json_safe] Parse failed for %s: %s", context, e,
                )
            else:
                log.warning("[json_safe] Parse failed: %s", e)
            return default
    # Already-parsed (dict/list/etc) — pass through
    return raw


def load_ship_systems(ship: dict) -> dict:
    """Domain helper for the dominant pattern across the space subsystem:

        sd = json.loads(dict(ship).get("systems") or "{}")

    Becomes:

        sd = load_ship_systems(ship)

    Returns a dict in all cases (never None). Logs context including
    the ship id (when available) on parse failure for traceability.
    """
    raw = ship.get("systems") if hasattr(ship, "get") else None
    ship_id = ship.get("id") if hasattr(ship, "get") else None
    ctx = f"ship {ship_id} systems" if ship_id is not None else "ship systems"
    result = safe_json_loads(raw, default={}, context=ctx)
    # If the field was a non-dict JSON value (e.g. a list or a string),
    # coerce to dict — every consumer expects dict-shaped systems.
    if not isinstance(result, dict):
        log.warning(
            "[json_safe] Ship %s systems is not a dict (%s); coercing to {}",
            ship_id, type(result).__name__,
        )
        return {}
    return result


def load_json_field(
    row: dict,
    field: str,
    default: Any = None,
    *,
    row_id_key: str = "id",
) -> Any:
    """Generic row-field JSON loader for cases beyond ship systems.

    Use when reading a JSON-typed column from a DB row dict:

        equip = load_json_field(char_row, "equipment", default=[])
        attrs = load_json_field(char_row, "attributes", default={})

    `row_id_key` controls which row field to log as the source identifier.
    Default "id" works for most engine row dicts; pass e.g. "char_id"
    or "ship_id" for tables with non-standard PK column names.
    """
    raw = row.get(field) if hasattr(row, "get") else None
    row_id = row.get(row_id_key) if hasattr(row, "get") else None
    if row_id is not None:
        ctx = f"{field} for {row_id_key}={row_id}"
    else:
        ctx = field
    return safe_json_loads(raw, default=default, context=ctx)
