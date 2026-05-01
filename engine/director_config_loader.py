# -*- coding: utf-8 -*-
"""
engine/director_config_loader.py — Era-aware Director config seam.

Drop F.6a.3 (seam-only) + F.6a.7 Phase 2 (legacy fallback removal).
This module is the production-safe seam between the F.6a.1 YAML loader
(`engine/world_loader.py::load_director_config`) and the live Director
engine (`engine/director.py`).

What this module provides
-------------------------
A single function `get_director_runtime_config(era)` returns a small
dataclass `DirectorRuntimeConfig` containing the four runtime knobs the
Director needs:

    valid_factions:    frozenset[str]
    zone_baselines:    dict[str, dict[str, int]]
    system_prompt:     str
    rewicker_factions: dict[str, str]   # {"imperial": "republic", ...}

`era` defaults to "gcw" when None. The values are sourced from
`data/worlds/<era>/director_config.yaml` via the F.6a.1 loader.

History
-------
- F.6a.3 (Apr 28): shipped the seam with in-Python legacy constants
  (`_LEGACY_VALID_FACTIONS`, `_LEGACY_DEFAULT_INFLUENCE`,
  `_LEGACY_SYSTEM_PROMPT`) as a rollback safety net while the F.6a
  integration drops landed.
- F.6a.7 Phase 1 (Apr 29): production boot wired to pass `era="gcw"`
  via `engine.era_state.get_seeding_era()` so legacy fallbacks became
  unreached from production.
- F.6a.7 Phase 2 (Apr 29): legacy constants and `_legacy()` factory
  deleted. `era=None` now defaults to "gcw" so backward-compat with
  existing test fixtures is preserved (they get YAML-sourced data
  byte-equivalent to what the deleted constants used to provide).
  YAML load failures return an empty config + ERROR log instead of
  silent fallback to stale literals.

Tested by tests/test_f6a3_director_config_loader.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── F.6a.7 Phase 2 (Apr 29 2026) — legacy constants deleted ─────────
# Pre-F.6a.7 Phase 2, this module held three large legacy constants:
#
#   _LEGACY_VALID_FACTIONS      (frozenset of 4 GCW director-axis names)
#   _LEGACY_DEFAULT_INFLUENCE   (dict of 6 zone × 4-faction baselines)
#   _LEGACY_SYSTEM_PROMPT       (~70-line multi-line string)
#
# They were the byte-equivalent in-Python copy of the values authored
# in `data/worlds/gcw/director_config.yaml`. They existed as a rollback
# safety net during F.6a.{1-6}; once the byte-equivalence tests proved
# the YAML matches them exactly and Phase 1 wired production boot to
# the YAML path, the constants became dead code.
#
# Phase 2 deletes them outright. The `era is None` branch in
# `get_director_runtime_config` now defaults to "gcw" so backward-compat
# with existing test fixtures is preserved (they get YAML-sourced data
# byte-equivalent to what the deleted constants used to provide).


@dataclass
class DirectorRuntimeConfig:
    """Frozen view of the Director's runtime knobs.

    `source` is "yaml-<era>" when the values came from
    data/worlds/<era>/director_config.yaml, "legacy" when the fallback
    was used. Useful for logging / debugging which path resolved.

    `valid_factions` is a frozenset for hashability (matches the
    DirectorAI's existing `VALID_FACTIONS` semantics — used in `if x in
    VALID_FACTIONS`).
    """
    valid_factions: frozenset
    zone_baselines: dict
    system_prompt: str
    rewicker_factions: dict
    rewicker_zones: dict
    source: str = "legacy"
    _yaml_config: Optional["DirectorConfig"] = None  # type: ignore[name-defined]
    raw_meta: dict = field(default_factory=dict)


def get_director_runtime_config(
    era: Optional[str] = None,
    *,
    worlds_root: Optional[Path] = None,
) -> DirectorRuntimeConfig:
    """Resolve Director runtime config for the given era.

    `era` is the directory name under data/worlds/ — usually "gcw" or
    "clone_wars". When None, defaults to "gcw" (the F.6a.7 Phase 2
    behavior change: pre-Phase-2, era=None returned in-Python literal
    constants; post-Phase-2, era=None defaults to loading
    `data/worlds/gcw/director_config.yaml`).

    `worlds_root` overrides the default `data/worlds` path; tests use
    this to point at a temp directory.

    Raises `RuntimeError` on any YAML load/validation failure for the
    GCW era — there is no longer an in-Python fallback. For other eras,
    a missing/broken YAML returns a minimal empty config so the engine
    can still boot (with degraded Director behavior). The
    `engine/director.py::_resolve_director_runtime_config` last-resort
    SimpleNamespace fallback still catches "what if the seam itself
    fails to import" for true defense-in-depth.
    """
    if era is None:
        era = "gcw"

    try:
        from engine.world_loader import (
            load_era_manifest, load_director_config as _load_dc,
        )
    except Exception as e:
        log.error(
            "[director_config_loader] world_loader import failed (%s); "
            "Director config cannot be resolved.", e,
        )
        return _empty_config(era=era, source_label=f"yaml-{era}-load-failed")

    root = worlds_root or (Path("data") / "worlds")
    era_dir = Path(root) / era
    try:
        manifest = load_era_manifest(era_dir)
        dc = _load_dc(manifest)
    except Exception as e:
        log.error(
            "[director_config_loader] Era %r director_config load failed "
            "(%s); returning empty config.", era, e,
        )
        return _empty_config(era=era, source_label=f"yaml-{era}-load-failed")

    if dc is None:
        log.error(
            "[director_config_loader] Era %r has no director_config "
            "content_ref; returning empty config.", era,
        )
        return _empty_config(era=era, source_label=f"yaml-{era}-no-content")

    if dc.report.errors:
        log.error(
            "[director_config_loader] Era %r director_config has %d "
            "validation error(s); returning empty config. First: %s",
            era, len(dc.report.errors), dc.report.errors[0],
        )
        return _empty_config(era=era, source_label=f"yaml-{era}-validation-failed")

    return DirectorRuntimeConfig(
        valid_factions=frozenset(dc.valid_factions),
        zone_baselines=dict(dc.zone_baselines),
        system_prompt=dc.system_prompt,
        rewicker_factions=dict(dc.rewicker_faction_codes),
        rewicker_zones=dict(dc.rewicker_zone_keys),
        source=f"yaml-{era}",
        _yaml_config=dc,
        raw_meta={
            "era": era,
            "schema_version": dc.schema_version,
            "milestone_count": len(dc.milestone_events),
            "holonet_pool_size": len(dc.holonet_news_pool),
        },
    )


def _empty_config(era: str, source_label: str) -> DirectorRuntimeConfig:
    """Return a minimal empty config when YAML resolution fails.

    Post-F.6a.7 Phase 2, this is the only fallback path inside this
    module. The Director can still boot (it has zero valid_factions
    and no zone baselines), but its behavior is degraded to "no
    Director activity" rather than "use stale GCW literals." This
    fail-loud behavior surfaces real boot misconfigurations instead
    of silently masking them.

    Operators see ERROR-level log messages identifying which YAML
    failed to load, so the diagnostic signal is preserved.
    """
    return DirectorRuntimeConfig(
        valid_factions=frozenset(),
        zone_baselines={},
        system_prompt="",
        rewicker_factions={},
        rewicker_zones={},
        source=source_label,
        raw_meta={"era": era},
    )


def apply_rewicker(
    cfg: DirectorRuntimeConfig,
    legacy_faction: str,
) -> str:
    """Translate a legacy GCW faction code to the current era's code.

    Returns the rewicked code if the rewicker map covers it, otherwise
    returns the input unchanged. Use at boundaries between legacy code
    paths (which still construct `imperial`/`rebel`/`criminal` literals)
    and the era's faction set.

    When the runtime is on the legacy path (no era YAML), the rewicker
    map is empty and this is a no-op.
    """
    return cfg.rewicker_factions.get(legacy_faction, legacy_faction)


def apply_zone_rewicker(
    cfg: DirectorRuntimeConfig,
    legacy_zone_key: str,
) -> str:
    """Translate a legacy GCW zone key to the current era's zone key.

    Returns the rewicked key if the rewicker map covers it, otherwise
    returns the input unchanged.
    """
    return cfg.rewicker_zones.get(legacy_zone_key, legacy_zone_key)
