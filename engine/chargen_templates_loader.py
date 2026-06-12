# -*- coding: utf-8 -*-
"""
engine/chargen_templates_loader.py — Era-aware chargen templates seam.

Drop F.7 (Apr 30 2026) — Phase 1: ships the seam with a legacy
in-Python fallback as a rollback safety net. Phase 2 (F.7.b, future
drop) retires the legacy fallback once byte-equivalence is proven
in production.

What this module provides
-------------------------
A single function `get_chargen_templates(era)` returns a dict shaped
exactly like the legacy `engine.creation.TEMPLATES` literal:

    {
        "smuggler": {
            "label": "Smuggler",
            "species": "Human",
            "attributes": {"dexterity": "3D+1", ...},
            "skills":     {"blaster": "1D+1", ...},
        },
        ...
    }

`era` defaults to the active era (per `engine.era_state.get_active_era()`)
when None. The dict is a fresh copy — callers may mutate it without
side-effects on the seam's internal cache.

Source preference order
-----------------------
1. YAML at `data/worlds/<era>/chargen_templates.yaml` (per F.7.1)
2. Empty-fallback seam (the GCW in-Python literal was retired with the
   GCW era). Returns an empty dict on YAML failure.

Architecture note
-----------------
The empty-fallback seam lives in this module (NOT in engine/creation.py)
to avoid a circular import: engine/creation.py reads from this seam
at module-import time, so this seam cannot depend on engine/creation.py.

A missing/broken YAML logs an ERROR/INFO and returns an empty dict.

Tested by tests/test_f7_chargen_templates_loader.py.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── Empty-fallback seam ───────────────────────────────────────────────────
# The in-Python GCW template literal (_LEGACY_TEMPLATES_GCW) was retired
# with the GCW era. Chargen templates are now sourced exclusively from
# data/worlds/<era>/chargen_templates.yaml. On YAML failure this seam
# returns an empty dict (a broken-but-survivable state — the chargen
# wizard handles an empty template list), matching the F.6a.3 / F.6a.7
# Phase 2 conventions.


def _legacy_templates_dict() -> dict:
    """Return the empty-fallback template dict.

    Used when the era's chargen_templates.yaml is not present (or the
    era manifest doesn't declare the ref). The GCW in-Python literal
    that this once returned was retired with the GCW era; the seam now
    returns an empty dict on YAML failure.
    """
    return {}


def get_chargen_templates(
    era: Optional[str] = None,
    *,
    worlds_root: Optional[Path] = None,
) -> dict:
    """Resolve chargen templates for the given era.

    Parameters
    ----------
    era : str or None
        Era code under data/worlds/. When None, defers to
        engine.era_state.get_active_era().
    worlds_root : Path or None
        Override the default `data/worlds` path; tests use this to
        point at a temp directory.

    Returns
    -------
    dict
        Mapping of template_key -> {label, species, attributes, skills}.
        Empty dict if both the YAML AND the legacy fallback fail (a
        broken state that should never happen in production but is
        survivable — chargen wizard handles an empty template list).

    Resolution order
    ----------------
    1. era=None → engine.era_state.get_active_era() (defaults to the
       production era, clone_wars)
    2. Try data/worlds/<era>/chargen_templates.yaml via
       engine.world_loader.{load_era_manifest, load_chargen_templates}
    3. On any failure, return an empty dict (the GCW in-Python literal
       was retired with the GCW era). Logs INFO/ERROR when this happens.
    """
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception as e:
            log.warning(
                "[chargen_templates_loader] era_state import failed (%s); "
                "defaulting to 'clone_wars'.", e,
            )
            era = "clone_wars"

    try:
        from engine.world_loader import (
            load_era_manifest, load_chargen_templates as _load_ct,
        )
    except Exception as e:
        log.error(
            "[chargen_templates_loader] world_loader import failed (%s); "
            "returning empty template set (GCW literal retired).", e,
        )
        return _legacy_templates_dict()

    root = worlds_root or (Path("data") / "worlds")
    era_dir = Path(root) / era
    try:
        manifest = load_era_manifest(era_dir)
    except Exception as e:
        log.info(
            "[chargen_templates_loader] Era %r manifest unavailable "
            "(%s); returning empty template set (GCW literal retired).", era, e,
        )
        return _legacy_templates_dict()

    if manifest.chargen_templates_path is None:
        log.info(
            "[chargen_templates_loader] Era %r manifest has no "
            "chargen_templates ref; falling back to legacy templates "
            "literal. (Author data/worlds/%s/chargen_templates.yaml "
            "and add a chargen_templates: entry under content_refs: "
            "to retire this fallback for the era.)",
            era, era,
        )
        return _legacy_templates_dict()

    try:
        corpus = _load_ct(manifest)
    except Exception as e:
        log.error(
            "[chargen_templates_loader] Era %r chargen_templates load "
            "failed (%s); returning empty template set (GCW literal retired).",
            era, e,
        )
        return _legacy_templates_dict()

    if corpus is None:
        # load_chargen_templates returns None when the manifest path
        # is None, but we already short-circuited that branch above.
        # If we got here it's a defensive fall-through.
        log.info(
            "[chargen_templates_loader] Era %r chargen_templates returned "
            "None unexpectedly; returning empty template set (GCW literal retired).",
            era,
        )
        return _legacy_templates_dict()

    if corpus.report.errors:
        log.error(
            "[chargen_templates_loader] Era %r chargen_templates has "
            "%d validation error(s); using whatever templates loaded "
            "cleanly. First: %s",
            era, len(corpus.report.errors), corpus.report.errors[0],
        )

    # Project the dataclass corpus back into the legacy dict shape so
    # consumers (engine/creation.py CreationEngine, parser/chargen) get
    # exactly what they got pre-F.7. The legacy shape is:
    #   {key: {"label": str, "species": str,
    #          "attributes": dict, "skills": dict}}
    out: dict = {}
    for tmpl in corpus.templates:
        out[tmpl.key] = {
            "label": tmpl.label,
            "species": tmpl.species,
            "attributes": dict(tmpl.attributes),
            "skills": dict(tmpl.skills),
        }
    return out
