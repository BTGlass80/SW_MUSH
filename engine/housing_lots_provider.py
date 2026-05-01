# -*- coding: utf-8 -*-
"""
engine/housing_lots_provider.py — Era-aware housing lot resolver (F.5b.2 → F.5b.3.c).

Bridges the F.5a YAML lot corpus to the legacy tuple shape that
engine/housing.py's runtime call sites have used since Drop 1. Lets the
runtime read era-specific YAML records without rewriting six call sites.

Design
------
After F.5b.3.c (Apr 30 2026) the in-Python `HOUSING_LOTS_*` constants
in engine/housing.py have been deleted. YAML is the only source of
truth.

The provider returns lists of `(room_id, planet, label, security,
max_homes)` tuples — the same shape that pre-F.5b.2 call sites expected.

Six call sites switched from:
    for room_id, planet, label, security, max_homes in HOUSING_LOTS_TIER3:
to:
    for room_id, planet, label, security, max_homes in get_tier3_lots():

— a one-token change that preserved tuple shape and iteration semantics.

The T3 path adds rep_gate filtering as a separate function:
    get_tier3_lots_filtered(char) — applies the `rep_gate` field to
    hide lots from low-rep characters per cw_housing_design_v1.md §7.1.

Caching
-------
The provider caches the resolved corpus per-era (clone_wars / gcw) at
first call. Cache invalidation is via `clear_lots_cache()`, called by
the era-switch path and by tests.

Tested by tests/test_f5b2_housing_lots_provider.py,
tests/test_f5b3b_provider_yaml_swap.py, tests/test_f5b3c_legacy_constants_deleted.py.
"""
from __future__ import annotations

import logging
from typing import Optional

log = logging.getLogger(__name__)

# Per-era cache. Key: era code; value: dict with t1/t3/t4/t5 lists of tuples.
_lots_cache: dict[str, dict] = {}


# ── Zone → security mapping (derived from cw_housing_design_v1.md §4) ──────
# When the YAML lot record's host_room zone is in this mapping, we use the
# specified security tier. Default is "contested" for unmapped zones — this
# is the design's "permissive default" for new content not yet classified.
_ZONE_SECURITY = {
    # Coruscant
    "coruscant_senate": "secured",
    "coruscant_temple": "secured",
    "coruscant_upper": "secured",
    "coruscant_midlevels": "contested",
    "coruscant_lower": "lawless",
    "coruscant_underworld": "lawless",
    "coruscant_works": "contested",
    "coruscant_gilded_cage": "contested",
    # Kuat
    "kuat_main_spaceport": "secured",
    "kuat_city_embassy": "secured",
    "kdy_orbital_ring": "secured",
    # Kamino
    "kamino_tipoca_city": "secured",
    "kamino_cloning_halls": "secured",
    "kamino_ocean_platform": "contested",
    # Geonosis
    "geonosis_surface": "lawless",
    "geonosis_petranaki": "contested",
    "geonosis_deep_hive": "lawless",
    "geonosis_foundries": "lawless",
    # Tatooine
    "tatooine_spaceport": "secured",
    "tatooine_mos_eisley": "secured",
    "tatooine_market": "contested",
    "tatooine_civic": "secured",
    "tatooine_cantina": "contested",
    "tatooine_outskirts": "contested",
    "tatooine_jundland": "lawless",
    "tatooine_dune_sea": "lawless",
    # Nar Shaddaa
    "nar_shaddaa_landing": "contested",
    "nar_shaddaa_promenade": "contested",
    "nar_shaddaa_undercity": "lawless",
    "nar_shaddaa_warrens": "lawless",
}


def _resolve_security(zone: str) -> str:
    """Map a zone slug to its security tier. Defaults to 'contested'."""
    return _ZONE_SECURITY.get(zone, "contested")


def _build_label(lot, host_room) -> str:
    """Build a display label for a lot.

    The legacy tuples have hand-authored labels like "Spaceport Hotel"
    or "Market Row Stalls". The YAML lot records have an `id` (slug-shaped)
    and a `description_theme` (tag), but no display label per se. We
    derive one from the host_room's `name` field when available, falling
    back to a humanized version of the lot id.
    """
    if host_room is not None and host_room.name:
        # Strip "Coruscant - " / "Kuat - " etc. prefixes for compactness
        name = host_room.name
        for prefix in ("Coruscant - ", "Kuat - ", "Kuat City - ",
                       "Kamino - ", "Geonosis - ", "Tatooine - ",
                       "Nar Shaddaa - "):
            if name.startswith(prefix):
                name = name[len(prefix):]
                break
        return name
    # Fallback: humanize the lot id
    return lot.id.replace("_", " ").title()


def _load_yaml_corpus(era: str):
    """Load the YAML housing-lot corpus for an era. Returns None on
    failure (logs a warning); the caller should fall back to legacy."""
    try:
        from engine.world_loader import (
            load_era_manifest, load_housing_lots, load_world_dry_run,
        )
        from pathlib import Path
        era_dir = Path("data") / "worlds" / era
        if not era_dir.is_dir():
            log.warning(
                "[housing_lots_provider] data/worlds/%s/ not present; "
                "cannot load YAML corpus.", era,
            )
            return None
        manifest = load_era_manifest(era_dir)
        corpus = load_housing_lots(manifest)
        if corpus is None or corpus.report.errors:
            log.warning(
                "[housing_lots_provider] %s housing_lots.yaml had load "
                "errors (%d); falling back to legacy.",
                era,
                0 if corpus is None else len(corpus.report.errors),
            )
            return None
        # Need the world too so we can resolve slugs to room IDs
        world = load_world_dry_run(era)
        return (corpus, world)
    except Exception as e:
        log.warning(
            "[housing_lots_provider] %s YAML corpus load failed (%s); "
            "falling back to legacy.", era, e,
        )
        return None


def _build_tier_tuples_from_yaml(lots: list, world, t1: bool = False) -> list:
    """Convert YAML lot records to legacy 5-tuple shape.

    Returns list of (room_id, planet, label, security, max_homes) tuples.
    Entries whose host_room slug doesn't resolve are dropped with a
    warning — the F.5a.2.x.1 regression guard catches these at YAML-load
    time, but a defensive resolve here protects against runtime drift.

    For T1: max_homes maps to the lot's `slots` field. For T3/T4/T5:
    max_homes maps to the lot's `max_homes` field directly.

    F.5b.3.b (Apr 30 2026): honors `display_label` and
    `security_override` when set on the lot record. These overrides
    let the YAML preserve hand-authored labels and securities from
    the legacy GCW constants (which the auto-derived label/security
    couldn't reproduce). When unset, falls back to derived defaults
    (preserving CW behavior, where authors don't specify these).
    """
    rooms_by_slug = {r.slug: r for r in world.rooms.values()}
    out: list = []
    for lot in lots:
        host = rooms_by_slug.get(lot.host_room)
        if host is None:
            log.warning(
                "[housing_lots_provider] lot %r host_room %r not found "
                "in world; skipping.", lot.id, lot.host_room,
            )
            continue
        room_id = host.id
        planet = lot.planet

        # F.5b.3.b: prefer explicit override; fall back to derivation.
        label_override = getattr(lot, "display_label", None)
        if label_override:
            label = label_override
        else:
            label = _build_label(lot, host)

        sec_override = getattr(lot, "security_override", None)
        if sec_override:
            security = sec_override
        else:
            security = _resolve_security(host.zone)

        if t1:
            max_h = lot.slots
        else:
            max_h = lot.max_homes
        out.append((room_id, planet, label, security, max_h))
    return out


def _resolve_corpus_for_era(era: str) -> dict:
    """Return the resolved per-tier tuple lists for an era, with caching.

    Returns a dict with keys 't1', 't3', 't4', 't5', 'rep_gates' where:
      - t1/t3/t4/t5 are lists of legacy 5-tuples
      - rep_gates is a dict {lot_room_id: rep_gate_dict} for T3 lots
        with rep_gate set

    F.5b.3.b (Apr 30 2026): GCW now flows through the YAML path, same
    as CW.

    F.5b.3.c (Apr 30 2026): the legacy in-Python `HOUSING_LOTS_*`
    constants in engine/housing.py have been deleted. The soft-fallback
    branch that returned them on YAML load failure is gone — fail-loud
    per §18.19 (seam-vs-integration discipline). A YAML load failure
    now produces an ERROR log and an empty result dict; `seed_lots`
    will then insert zero rows and `housing tier3` listings will show
    nothing. The fail-loud surface is intentional: a missing
    housing_lots.yaml is a content-debt bug, not a runtime fallback.

    The YAML path is also *more correct* than the legacy constants
    were: the legacy room IDs had drifted (e.g. legacy "Spaceport
    Hotel" claimed room 29; the actual Spaceport Hotel is room 25 —
    legacy 29 was Jawa Traders). Slug-based YAML resolution
    auto-corrects this drift.
    """
    if era in _lots_cache:
        return _lots_cache[era]

    result = {"t1": [], "t3": [], "t4": [], "t5": [], "rep_gates": {}}

    # F.5b.3.c: unified YAML path for both GCW and CW. Fail-loud on
    # YAML unavailability — no in-Python fallback exists anymore.
    loaded = _load_yaml_corpus(era)
    if loaded is None:
        log.error(
            "[housing_lots_provider] %s YAML corpus unavailable; "
            "housing inventory will be empty for this era. Check "
            "data/worlds/%s/housing_lots.yaml exists and parses cleanly.",
            era, era,
        )
        _lots_cache[era] = result
        return result

    corpus, world = loaded
    rooms_by_slug = {r.slug: r for r in world.rooms.values()}

    result["t1"] = _build_tier_tuples_from_yaml(
        corpus.tier1_rentals, world, t1=True,
    )
    result["t3"] = _build_tier_tuples_from_yaml(
        corpus.tier3_lots, world,
    )
    result["t4"] = _build_tier_tuples_from_yaml(
        corpus.tier4_lots, world,
    )
    result["t5"] = _build_tier_tuples_from_yaml(
        corpus.tier5_lots, world,
    )

    # Build rep_gate lookup keyed by room_id (the runtime works in
    # room_ids; YAML works in slugs). Only T3 supports rep_gate per
    # cw_housing_design_v1.md §7.1.
    for lot in corpus.tier3_lots:
        if lot.rep_gate:
            host = rooms_by_slug.get(lot.host_room)
            if host is not None:
                result["rep_gates"][host.id] = dict(lot.rep_gate)

    _lots_cache[era] = result
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Public API
# ══════════════════════════════════════════════════════════════════════════════

def get_tier1_lots(era: Optional[str] = None) -> list:
    """Return T1 lots as legacy 5-tuples for the given (or active) era.

    Each tuple: (room_id, planet, label, security, slots).

    If `era` is None, the active era from era_state is used.
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    return list(_resolve_corpus_for_era(era)["t1"])


def get_tier3_lots(era: Optional[str] = None) -> list:
    """Return T3 lots as legacy 5-tuples for the given (or active) era.

    Each tuple: (room_id, planet, label, security, max_homes).
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    return list(_resolve_corpus_for_era(era)["t3"])


def get_tier4_lots(era: Optional[str] = None) -> list:
    """Return T4 lots as legacy 5-tuples for the given (or active) era."""
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    return list(_resolve_corpus_for_era(era)["t4"])


def get_tier5_lots(era: Optional[str] = None) -> list:
    """Return T5 lots as legacy 5-tuples for the given (or active) era."""
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    return list(_resolve_corpus_for_era(era)["t5"])


def get_tier3_rep_gates(era: Optional[str] = None) -> dict:
    """Return the T3 rep_gate map for the given (or active) era.

    Returns dict {room_id: {"faction": str, "min_value": int}}.

    Only T3 lots from the YAML corpus contribute; legacy hardcoded
    T3 entries (GCW) have no rep_gate concept and are NOT in the dict.
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    return dict(_resolve_corpus_for_era(era)["rep_gates"])


def is_lot_rep_visible(lot_room_id: int, char_rep: dict,
                       era: Optional[str] = None) -> bool:
    """Return True iff the character can SEE this lot.

    A lot with no rep_gate is always visible. A lot with a rep_gate
    is visible only if `char_rep[faction] >= min_value`.

    `char_rep` is a dict mapping faction codes to integer reputation
    values, as produced by engine/factions.get_character_reputation().

    Per cw_housing_design_v1.md §7.1, rep-gated lots disappear from
    market-search and from `housing tier3` listings entirely (rather
    than appearing as locked) — the rationale is that an unaligned
    PC shouldn't even know about the Kuat-side properties unless they've
    earned the clearance to be told.
    """
    gates = get_tier3_rep_gates(era)
    gate = gates.get(lot_room_id)
    if not gate:
        return True
    faction = gate.get("faction", "")
    min_value = int(gate.get("min_value", 0))
    cur = int(char_rep.get(faction, 0))
    return cur >= min_value


def get_tier3_lots_filtered(char_rep: dict,
                            era: Optional[str] = None) -> list:
    """Return T3 lots visible to a character with the given reputation.

    Equivalent to `get_tier3_lots()` filtered by `is_lot_rep_visible()`.
    Use this in market-search and `housing tier3` listing code paths
    so rep-gated lots are hidden from low-rep characters.
    """
    if era is None:
        from engine.era_state import get_active_era
        era = get_active_era()
    all_t3 = get_tier3_lots(era)
    return [
        t for t in all_t3
        if is_lot_rep_visible(t[0], char_rep, era=era)
    ]


def clear_lots_cache() -> None:
    """Clear the per-era resolved-corpus cache.

    Call after switching active era, or in test setup/teardown to ensure
    a fresh resolution.
    """
    _lots_cache.clear()
