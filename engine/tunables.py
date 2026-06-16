# -*- coding: utf-8 -*-
"""
engine/tunables.py — Game balance tunables loaded from data/tunables.yaml.

T3.19 Phase 0: foundation.  Call ``load_tunables()`` once at boot; then
``get_tunable(key, default)`` at every hardcoded balance value that should
be operator-adjustable post-launch.

The YAML is a flat namespace of dotted keys::

    trade.price_demand_multiplier: 1.40
    bounty.reward_superior_max: 10000

A missing or empty file is byte-equivalent to using hardcoded defaults:
any key absent from the YAML causes ``get_tunable`` to return the caller's
``default`` argument unchanged — identical to the pre-T3.19 behaviour.

Mirrored after ``engine/director_config_loader.py``: YAML-overrides-with-
in-code-default, fail-open (warnings/errors logged; no crash).

Tested by tests/test_t3_19_tunables_foundation.py.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

# Module-level singleton populated by load_tunables().
_TUNABLES: dict[str, Any] = {}


def load_tunables(path: str = "data/tunables.yaml") -> None:
    """Read game balance tunables from a flat YAML file.

    Populates the module-level ``_TUNABLES`` dict.  Safe to call multiple
    times (later call wins); idempotent when the file has not changed.

    Missing file → no-op (INFO log).
    Top-level non-mapping → ERROR log, _TUNABLES cleared.
    Parse error → ERROR log, _TUNABLES cleared.
    All failure paths leave the tunables at their hardcoded defaults.
    """
    global _TUNABLES
    p = Path(path)
    if not p.exists():
        log.info("[tunables] %s not found; using hardcoded defaults", path)
        _TUNABLES = {}
        return
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except Exception as exc:
        log.error("[tunables] failed to parse %s: %s; using hardcoded defaults", path, exc)
        _TUNABLES = {}
        return

    if data is None:
        # Empty file — treat as empty dict (valid "use all defaults" case)
        _TUNABLES = {}
        log.info("[tunables] %s is empty; using hardcoded defaults", path)
        return

    if not isinstance(data, dict):
        log.error(
            "[tunables] %s top-level must be a mapping (got %s); using hardcoded defaults",
            path, type(data).__name__,
        )
        _TUNABLES = {}
        return

    _TUNABLES = {str(k): v for k, v in data.items()}
    log.info("[tunables] loaded %d knob(s) from %s", len(_TUNABLES), path)


def get_tunable(key: str, default: Any = None) -> Any:
    """Return a tunable by dotted key, or *default* if not set in YAML.

    The caller supplies the hardcoded literal as *default* so the YAML is
    purely additive — omitting a key from the YAML is always safe.

    Example::

        PRICE_DEMAND = get_tunable("trade.price_demand_multiplier", 1.40)
    """
    return _TUNABLES.get(key, default)


def reset_tunables() -> None:
    """Clear all loaded tunables (test helper only)."""
    global _TUNABLES
    _TUNABLES = {}
