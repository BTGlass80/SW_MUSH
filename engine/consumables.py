"""
engine/consumables.py — consumable identity registry.

CRAFT.P2 / Gundark Drop A (2026-06-10). Loads data/consumables.yaml —
the migrated home of what used to be the parser-local
``_CONSUMABLE_STATS`` dict in parser/crafting_commands.py
(crafting_integration_design_pass_v1.md §3.3: "consumable stats out of
the parser, so Gundark stim/med families are data drops, not parser
edits").

Identity only (name / description / category). Use-time MECHANICS live
in ``parser/medical_commands.py::_STIM_CATALOG`` — see the division-of-
responsibility note at the top of data/consumables.yaml. The two are
pinned against each other by tests (every catalog key must have an
identity row, and vice versa).

Mirrors the weapons-registry pattern: module-level cache, lazy load,
dict-backed lookups, tolerant of a missing/malformed file (empty
registry, never a raise).
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

log = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "consumables.yaml"

_cache: dict | None = None


def _load() -> dict:
    global _cache
    if _cache is not None:
        return _cache
    try:
        raw = yaml.safe_load(_DATA_PATH.read_text(encoding="utf-8")) or {}
        entries = raw.get("consumables", {})
        _cache = entries if isinstance(entries, dict) else {}
    except Exception:
        log.warning("consumables registry load failed", exc_info=True)
        _cache = {}
    return _cache


def get_consumable(key: str) -> dict | None:
    """Identity row for one consumable output_key, or None."""
    row = _load().get(key)
    return dict(row) if isinstance(row, dict) else None


def get_all_consumables() -> dict:
    """Full {key: row} mapping (copies — callers can't poison the cache)."""
    return {k: dict(v) for k, v in _load().items() if isinstance(v, dict)}


def consumable_display_name(key: str) -> str:
    """Display name for a consumable key, falling back to the key itself."""
    row = _load().get(key)
    if isinstance(row, dict):
        return str(row.get("name", key))
    return key
