# -*- coding: utf-8 -*-
"""
engine/ambient_pools_loader.py — Era-aware ambient-pool seam.

Drop F.6a.4 (seam-only). Same pattern as F.6a.3:
  - Production-safe wrapper over F.6a.1's load_ambient_pools
  - Returns a frozen view of merged ambient pools
  - Falls back to the legacy flat data/ambient_events.yaml when no era
    is supplied, or when era-specific YAML is absent / has errors
  - Does NOT modify engine/ambient_events.py — that integration is a
    later targeted PR

What this module provides
-------------------------
A single function `get_ambient_pools(era)` returns a `MergedAmbientPools`
dataclass mapping zone-key → list[(text, weight)] tuples. The merge
order is:

  1. Legacy flat data/ambient_events.yaml (always loaded if present)
  2. Era-specific data/worlds/<era>/ambient_events.yaml (overrides #1
     for any colliding zone keys; additive for new zone keys)

Per design doc §3.3 + the CW ambient_events.yaml header: era-specific
keys are wrapped under `ambient_events:` (e.g. coruscant_senate); legacy
keys are at the top level (cantina, spaceport, etc.). The CW file
intentionally does NOT redefine the legacy generic keys — those continue
to be served by the legacy file in both eras. The merge logic just
unions the two key spaces; era-specific zone keys win when they exist.

Why a seam, not a refactor
--------------------------
Same logic as F.6a.3. AmbientEventManager._load_yaml() is called once at
boot; touching it directly risks the live ambient flavor system. The
seam ships the loader contract; the integration ("AmbientEventManager
reads from the seam") happens later in a single targeted PR.

Tested by tests/test_f6a4_ambient_pools_loader.py.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class AmbientLineTuple:
    """Lightweight (text, weight) pair. Distinct from
    engine.ambient_events.AmbientLine to keep the seam decoupled from
    the live engine module — integration PR maps between them.
    """
    text: str
    weight: float = 1.0


@dataclass
class MergedAmbientPools:
    """Result of get_ambient_pools.

    `pools` maps zone_key → list[AmbientLineTuple]. Keys are a union of
    legacy and era-specific keys; era-specific keys win on collision.

    `source` is one of: "legacy-only", "yaml-<era>+legacy", "legacy-fallback".
    `legacy_path` and `era_path` are the resolved paths used for each layer.
    """
    pools: dict
    source: str = "legacy-only"
    legacy_path: Optional[Path] = None
    era_path: Optional[Path] = None
    raw_meta: dict = field(default_factory=dict)


# Default location of the legacy flat ambient pool. Tests can override
# by passing `legacy_path=` to get_ambient_pools.
_DEFAULT_LEGACY_PATH = Path(__file__).parent.parent / "data" / "ambient_events.yaml"


def get_ambient_pools(
    era: Optional[str] = None,
    *,
    worlds_root: Optional[Path] = None,
    legacy_path: Optional[Path] = None,
) -> MergedAmbientPools:
    """Resolve merged ambient pools for the given era.

    `era` is the directory name under data/worlds/. When None, returns
    only the legacy flat pool. When set, era-specific pools are merged
    on top of legacy.

    Never raises. On any per-layer failure, that layer is skipped and
    the other layer's data still loads. If both layers fail, returns
    an empty pools dict with source="legacy-fallback".
    """
    legacy_p = legacy_path or _DEFAULT_LEGACY_PATH

    # ── Layer 1: legacy flat YAML ───────────────────────────────────────
    legacy_pools, legacy_used = _load_legacy_pool(legacy_p)

    if era is None:
        return MergedAmbientPools(
            pools=legacy_pools,
            source="legacy-only" if legacy_used else "legacy-fallback",
            legacy_path=legacy_p if legacy_used else None,
            raw_meta={
                "legacy_zone_count": len(legacy_pools),
                "era": None,
            },
        )

    # ── Layer 2: era-specific YAML ──────────────────────────────────────
    era_pools, era_path = _load_era_pool(era, worlds_root=worlds_root)

    if not era_pools:
        # Era requested but era YAML unavailable → legacy only
        return MergedAmbientPools(
            pools=legacy_pools,
            source="legacy-only" if legacy_used else "legacy-fallback",
            legacy_path=legacy_p if legacy_used else None,
            era_path=None,
            raw_meta={
                "legacy_zone_count": len(legacy_pools),
                "era_zone_count": 0,
                "era": era,
            },
        )

    # Merge: start from legacy, era keys win on collision.
    merged = dict(legacy_pools)
    for zk, lines in era_pools.items():
        merged[zk] = list(lines)

    return MergedAmbientPools(
        pools=merged,
        source=f"yaml-{era}+legacy",
        legacy_path=legacy_p if legacy_used else None,
        era_path=era_path,
        raw_meta={
            "legacy_zone_count": len(legacy_pools),
            "era_zone_count": len(era_pools),
            "merged_zone_count": len(merged),
            "era": era,
            "collisions": sorted(set(legacy_pools) & set(era_pools)),
        },
    )


def _load_legacy_pool(path: Path) -> tuple[dict, bool]:
    """Load legacy flat data/ambient_events.yaml. Returns (pools, used).

    Schema: top-level dict where each key is a zone_key and the value
    is a list of strings or {text, weight} mappings. This is the schema
    AmbientEventManager._load_yaml() in engine/ambient_events.py reads.
    """
    if not path.is_file():
        log.info("[ambient_pools_loader] No legacy pool at %s", path)
        return {}, False

    try:
        import yaml
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except Exception as e:
        log.warning("[ambient_pools_loader] Failed to parse %s: %s", path, e)
        return {}, False

    if not isinstance(raw, dict):
        log.warning(
            "[ambient_pools_loader] %s top-level is not a mapping; "
            "skipping legacy layer.", path,
        )
        return {}, False

    pools: dict[str, list[AmbientLineTuple]] = {}
    for zk, entries in raw.items():
        if not isinstance(entries, list):
            continue
        lines: list[AmbientLineTuple] = []
        for entry in entries:
            if isinstance(entry, str):
                lines.append(AmbientLineTuple(text=entry, weight=1.0))
            elif isinstance(entry, dict) and "text" in entry:
                try:
                    w = float(entry.get("weight", 1.0))
                except (TypeError, ValueError):
                    w = 1.0
                lines.append(AmbientLineTuple(text=str(entry["text"]), weight=w))
        if lines:
            pools[zk] = lines
    return pools, True


def _load_era_pool(
    era: str,
    *,
    worlds_root: Optional[Path] = None,
) -> tuple[dict, Optional[Path]]:
    """Load era-specific ambient_events.yaml via F.6a.1's loader.

    Returns (pools, path_used). On any failure, returns ({}, None).
    """
    try:
        from engine.world_loader import (
            load_era_manifest, load_ambient_pools as _load_ap,
        )
    except Exception as e:
        log.warning(
            "[ambient_pools_loader] world_loader import failed (%s); "
            "skipping era layer.", e,
        )
        return {}, None

    root = worlds_root or (Path("data") / "worlds")
    era_dir = Path(root) / era
    try:
        manifest = load_era_manifest(era_dir)
        ap = _load_ap(manifest)
    except Exception as e:
        log.warning(
            "[ambient_pools_loader] Era %r ambient_events load failed "
            "(%s); skipping era layer.", era, e,
        )
        return {}, None

    if ap is None:
        log.info(
            "[ambient_pools_loader] Era %r has no ambient_events "
            "content_ref; skipping era layer.", era,
        )
        return {}, None

    if ap.report.errors:
        log.warning(
            "[ambient_pools_loader] Era %r ambient_events has %d "
            "validation error(s); skipping era layer. First: %s",
            era, len(ap.report.errors), ap.report.errors[0],
        )
        return {}, None

    pools: dict[str, list[AmbientLineTuple]] = {}
    for zk, lines in ap.pools.items():
        pools[zk] = [
            AmbientLineTuple(text=ln.text, weight=ln.weight) for ln in lines
        ]
    return pools, manifest.ambient_events_path


def pick_pool_for_zone(
    merged: MergedAmbientPools,
    zone_key: str,
    fallback_zone_key: str = "default",
) -> list:
    """Helper: get the line list for `zone_key`, falling back when absent.

    Returns the empty list if neither key resolves. AmbientEventManager
    will eventually call this from its tick path; for now it documents
    the resolution rule for the integration PR.
    """
    if zone_key in merged.pools:
        return merged.pools[zone_key]
    if fallback_zone_key in merged.pools:
        return merged.pools[fallback_zone_key]
    return []
