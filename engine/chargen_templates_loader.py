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
2. In-Python legacy fallback `_LEGACY_TEMPLATES_GCW` defined in this
   module. Only used during Phase 1 — F.7.b removes this branch.

Architecture note
-----------------
The legacy fallback lives in this module (NOT in engine/creation.py)
to avoid a circular import: engine/creation.py reads from this seam
at module-import time, so this seam cannot depend on engine/creation.py
for its fallback. F.7.b Phase 2 deletes _LEGACY_TEMPLATES_GCW from
this module entirely.

The legacy-fallback branch logs INFO when taken (not ERROR — Phase 1
expects this to fire for any era without a chargen_templates.yaml ref
yet authored). Once F.7.b retires the fallback, missing/broken YAMLs
log ERROR and return an empty dict.

Tested by tests/test_f7_chargen_templates_loader.py.
"""
from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)


# ── Phase 1 (F.7) — Legacy fallback ──────────────────────────────────────
# `_LEGACY_TEMPLATES_GCW` is the byte-equivalent in-Python copy of the
# 7 GCW archetypes authored at data/worlds/gcw/chargen_templates.yaml.
# Phase 2 (F.7.b) deletes this constant; the seam will then return an
# empty dict on YAML failure, matching F.6a.3 / F.6a.7 Phase 2
# conventions.
#
# The values below match the pre-F.7 in-Python TEMPLATES literal at
# engine/creation.py L42–L101 byte-for-byte. Tests in
# tests/test_f7_chargen_templates_loader.py prove byte-equivalence
# against the GCW YAML; the F.7 byte-equivalence guards keep this
# constant and the YAML in lockstep until Phase 2 retires the
# constant.

_LEGACY_TEMPLATES_GCW: dict = {
    "smuggler": {
        "label": "Smuggler",
        "species": "Human",
        "attributes": {"dexterity": "3D+1", "knowledge": "2D+1", "mechanical": "4D",
                        "perception": "3D+1", "strength": "2D+2", "technical": "2D+1"},
        "skills": {"blaster": "1D+1", "dodge": "1D", "space transports": "1D+2",
                    "starship gunnery": "1D", "streetwise": "1D", "bargain": "1D"},
    },
    "bounty_hunter": {
        "label": "Bounty Hunter",
        "species": "Human",
        "attributes": {"dexterity": "3D+2", "knowledge": "2D+1", "mechanical": "2D+2",
                        "perception": "3D+1", "strength": "3D+1", "technical": "2D+2"},
        "skills": {"blaster": "2D", "dodge": "1D", "brawling": "1D",
                    "search": "1D", "sneak": "1D", "security": "1D"},
    },
    "rebel_pilot": {
        "label": "Rebel Pilot",
        "species": "Human",
        "attributes": {"dexterity": "3D", "knowledge": "2D+2", "mechanical": "4D+1",
                        "perception": "2D+2", "strength": "2D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D", "starfighter piloting": "2D",
                    "starship gunnery": "1D", "astrogation": "1D", "sensors": "1D",
                    "starfighter repair": "1D"},
    },
    "scoundrel": {
        "label": "Scoundrel",
        "species": "Human",
        "attributes": {"dexterity": "3D", "knowledge": "3D", "mechanical": "2D+2",
                        "perception": "4D", "strength": "2D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D", "dodge": "1D", "con": "1D+2",
                    "persuasion": "1D", "gambling": "1D", "sneak": "1D+1"},
    },
    "technician": {
        "label": "Technician",
        "species": "Human",
        "attributes": {"dexterity": "2D+1", "knowledge": "3D", "mechanical": "2D+2",
                        "perception": "2D+2", "strength": "2D+2", "technical": "4D+2"},
        "skills": {"computer programming/repair": "1D+2", "droid repair": "1D",
                    "first aid": "1D", "security": "1D", "blaster repair": "1D",
                    "space transport repair": "1D+1"},
    },
    "jedi_apprentice": {
        "label": "Jedi Apprentice",
        "species": "Human",
        "attributes": {"dexterity": "3D+1", "knowledge": "3D", "mechanical": "2D+1",
                        "perception": "3D+2", "strength": "3D", "technical": "2D+2"},
        "skills": {"lightsaber": "1D+2", "dodge": "1D", "scholar": "1D",
                    "willpower": "1D", "sneak": "1D", "climbing/jumping": "1D+1"},
    },
    "soldier": {
        "label": "Soldier",
        "species": "Human",
        "attributes": {"dexterity": "3D+2", "knowledge": "2D+2", "mechanical": "2D+2",
                        "perception": "2D+2", "strength": "3D+2", "technical": "2D+2"},
        "skills": {"blaster": "1D+2", "dodge": "1D", "brawling": "1D",
                    "grenade": "1D", "tactics": "1D", "stamina": "1D+1"},
    },
}


def _legacy_templates_dict() -> dict:
    """Return a deep copy of the legacy in-Python templates dict.

    Used as Phase 1 fallback when the era's chargen_templates.yaml is
    not present (or the era manifest doesn't declare the ref). The
    deep copy is per-call so callers cannot mutate the legacy literal
    by accident.

    Phase 2 (F.7.b) deletes `_LEGACY_TEMPLATES_GCW` and this helper
    along with it. The seam will then return an empty dict on YAML
    failure.
    """
    return copy.deepcopy(_LEGACY_TEMPLATES_GCW)


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
    1. era=None → engine.era_state.get_active_era() (defaults to "gcw")
    2. Try data/worlds/<era>/chargen_templates.yaml via
       engine.world_loader.{load_era_manifest, load_chargen_templates}
    3. On any failure, fall back to _LEGACY_TEMPLATES_GCW (the
       in-Python legacy literal). Logs INFO when this happens.
    """
    if era is None:
        try:
            from engine.era_state import get_active_era
            era = get_active_era()
        except Exception as e:
            log.warning(
                "[chargen_templates_loader] era_state import failed (%s); "
                "defaulting to 'gcw'.", e,
            )
            era = "gcw"

    try:
        from engine.world_loader import (
            load_era_manifest, load_chargen_templates as _load_ct,
        )
    except Exception as e:
        log.error(
            "[chargen_templates_loader] world_loader import failed (%s); "
            "falling back to legacy templates literal.", e,
        )
        return _legacy_templates_dict()

    root = worlds_root or (Path("data") / "worlds")
    era_dir = Path(root) / era
    try:
        manifest = load_era_manifest(era_dir)
    except Exception as e:
        log.info(
            "[chargen_templates_loader] Era %r manifest unavailable "
            "(%s); falling back to legacy templates literal.", era, e,
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
            "failed (%s); falling back to legacy templates literal.",
            era, e,
        )
        return _legacy_templates_dict()

    if corpus is None:
        # load_chargen_templates returns None when the manifest path
        # is None, but we already short-circuited that branch above.
        # If we got here it's a defensive fall-through.
        log.info(
            "[chargen_templates_loader] Era %r chargen_templates returned "
            "None unexpectedly; falling back to legacy templates literal.",
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
