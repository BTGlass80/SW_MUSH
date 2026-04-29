# -*- coding: utf-8 -*-
"""
engine/era_state.py — Active era resolution.

Drop F.6a.5b (active-era scaffolding). Companion to F.6a.{3,4} seams.

Provides `get_active_era()` and `use_yaml_director_data()` — the two
runtime queries the F.6a.{2,3,4}-int integrations need to decide which
data path to take.

Design
------
Both functions accept an optional Config; if not passed, they fall back
to a module-level "ambient" config that the server boot sequence sets
once via `set_active_config(cfg)`. Tests can call `set_active_config`
with a synthetic Config, or override per-call via the `cfg` kwarg.

Why this module exists
----------------------
The F.6a.{2,3,4} loaders and seams already work without it — they
accept `era` as a parameter directly. But the eventual integration
sites in `engine/world_lore.py::seed_lore`, `engine/director.py`'s
boot path, and `engine/ambient_events.py::AmbientEventManager._load_yaml`
will need a SINGLE place to resolve "what era are we in" without
plumbing the Config object through every call. This module is that
place.

Default behavior is conservative: returns "gcw" and use_yaml=False
when no Config has been registered, so importing this module from
test code with no setup gives the legacy production behavior.

Tested by tests/test_f6a5b_era_state.py.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Module-level holder. Set once at boot via `set_active_config`.
# Tests may overwrite this directly via `_active_config = ...` or use
# the public set_active_config / clear_active_config helpers.
_active_config: Optional[object] = None


# Conservative defaults — what this module returns when no Config has
# been registered. Mirrors the current production behavior so importing
# era_state from a test file with no setup never accidentally flips the
# era YAML path.
_DEFAULT_ERA = "gcw"
_DEFAULT_USE_YAML = False


def set_active_config(cfg: Optional[object]) -> None:
    """Register a Config-shaped object as the ambient era source.

    The object must have `active_era: str` and `use_yaml_director_data: bool`
    attributes; duck-typed (no isinstance check) so tests can pass any
    object with the right attributes.

    Pass `None` to clear; subsequent reads return the module defaults.
    """
    global _active_config
    _active_config = cfg


def clear_active_config() -> None:
    """Equivalent to `set_active_config(None)`."""
    set_active_config(None)


def get_active_era(cfg: Optional[object] = None) -> str:
    """Return the active era code (e.g. "gcw", "clone_wars").

    Resolution order:
      1. `cfg.active_era` if `cfg` is provided
      2. `_active_config.active_era` if registered
      3. `_DEFAULT_ERA` ("gcw")

    Never raises. Logs a warning and returns the default if either
    source has the attribute set to a non-string.
    """
    src = cfg if cfg is not None else _active_config
    if src is None:
        return _DEFAULT_ERA
    val = getattr(src, "active_era", _DEFAULT_ERA)
    if not isinstance(val, str) or not val:
        log.warning(
            "[era_state] active_era is %r (expected non-empty str); "
            "falling back to %r.", val, _DEFAULT_ERA,
        )
        return _DEFAULT_ERA
    return val


def use_yaml_director_data(cfg: Optional[object] = None) -> bool:
    """Return True iff the engine should read Director/lore data from YAML.

    Resolution mirrors get_active_era(): explicit cfg → registered cfg →
    _DEFAULT_USE_YAML (False).

    Callers in F.6a.*-int will use this to decide between:
      - True  → call era-aware loader (e.g. seed_lore(db, era=get_active_era()))
      - False → call legacy path (e.g. seed_lore(db) — uses SEED_ENTRIES)

    Defaults to False so the flag stays off until the integration drops
    are validated against your live DB.
    """
    src = cfg if cfg is not None else _active_config
    if src is None:
        return _DEFAULT_USE_YAML
    val = getattr(src, "use_yaml_director_data", _DEFAULT_USE_YAML)
    if not isinstance(val, bool):
        log.warning(
            "[era_state] use_yaml_director_data is %r (expected bool); "
            "falling back to %r.", val, _DEFAULT_USE_YAML,
        )
        return _DEFAULT_USE_YAML
    return val


def resolve_era_for_seeding(cfg: Optional[object] = None) -> Optional[str]:
    """Convenience: return the era code IF use_yaml_director_data is on,
    else None.

    This is the exact value that should be passed as the `era=` kwarg to
    `seed_lore(db, era=...)` and similar era-aware seeding functions.
    Returns None when the flag is off, which makes the seeding function
    take its legacy path. Callers that want the era code regardless
    should use `get_active_era()` directly.
    """
    if not use_yaml_director_data(cfg):
        return None
    return get_active_era(cfg)
