# -*- coding: utf-8 -*-
"""
engine/hermit.py — Hermit NPC gate seam (Drop F.6, May 3 2026).

Per ``progression_gates_and_consequences_design_v1.md`` §2.3–§2.4 and
``jedi_village_quest_design_v1.md`` §3.2:

  - The Hermit lives at the ``Hermit's Hut`` wilderness landmark in
    Tatooine's Dune Sea region.
  - Visitors with ``force_signs_accumulated < 5`` are met with
    silence-and-tea (the Hermit is present but not interactive).
  - Visitors with ``force_signs_accumulated >= 5`` receive the
    Village invitation (the Act 1 trigger).

This module is the **gate seam** that the Village quest engine
(future drop) consults when the Hermit's talk-to handler fires.
It does not implement the dialogue runtime; it implements the
single yes/no question:

    "Should this character receive the Village invitation right now?"

Source of truth for the threshold lives in ``engine.force_signs``.
This module delegates to it, rather than duplicating the constant,
so future tuning (PG.4.polish moves the threshold to era.yaml)
ripples through one file.

What this module ships:
  - ``is_invitation_eligible(char)`` — pure boolean wrapper around
    ``force_signs.has_received_invitation``. Future dialogue runtime
    calls this to decide gate.before_lines vs gate.after_lines.
  - ``load_hermit_gate_config(yaml_path)`` — parser that pulls the
    Hermit's ``ai_config.gate`` block out of the wilderness_npcs
    YAML so tests can verify the data shape independently of the
    NPC-loader path.

What is deferred to the Village quest engine drop:
  - Wiring the talk-to handler to choose between before_lines and
    after_lines based on this module's verdict.
  - Firing the Act 1 state-machine transition when after_lines
    have been delivered for the first time.
  - Recurring-line cycling on subsequent visits.

Until that drop ships, this module is consultable but inert in
terms of player-facing effect. Talk-to falls through to the
Hermit's existing fallback_lines (the standard NPC dialogue path).
That's deliberate: F.6 is the foundation; the runtime consumer is
a future drop that uses it.

See also:
  - ``engine/force_signs.py`` for the threshold and read-helper.
  - ``data/worlds/clone_wars/wilderness_npcs.yaml`` for the Hermit
    content and gate block.
"""
from __future__ import annotations

import logging
import os
from typing import Mapping, Optional

import yaml

from engine.force_signs import (
    FORCE_SIGNS_FOR_INVITATION,
    has_received_invitation,
)

log = logging.getLogger(__name__)


# Identifier for the Hermit's gate kind. Currently the only gate kind
# the Village quest engine will recognize. If future NPCs gain
# similar gate-aware dialogue patterns, additional kinds may be added.
HERMIT_GATE_KIND: str = "force_sign_invitation"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def is_invitation_eligible(char: Mapping) -> bool:
    """True iff this character has accumulated enough Force-signs
    to receive the Village invitation from the Hermit.

    Pure wrapper around ``force_signs.has_received_invitation`` so
    that callers (the Village quest engine's Hermit talk-to handler)
    have a Hermit-named seam to call without reaching into a more
    general module. The threshold itself lives in
    ``engine.force_signs.FORCE_SIGNS_FOR_INVITATION``.

    Args:
        char: a character dict (must include
            ``force_signs_accumulated``). Missing field defaults to 0.

    Returns:
        True if signs >= FORCE_SIGNS_FOR_INVITATION, else False.
    """
    return has_received_invitation(char)


def load_hermit_gate_config(yaml_path: str) -> Optional[dict]:
    """Read the Hermit's ai_config.gate block from a wilderness_npcs YAML.

    Used by tests to verify the gate data shape directly (without
    routing through the NPC loader / DB write path). Returns None
    if no Hermit entry is present, or if the entry has no gate block.

    The Hermit is matched by name == "the Hermit" (case-sensitive,
    matches the YAML authoring). Future gated wilderness NPCs would
    need to extend this lookup.

    Args:
        yaml_path: path to a wilderness_npcs.yaml file.

    Returns:
        dict containing the gate block, or None.
        Expected keys when present: kind, threshold, before_lines,
        after_lines, recurring_lines.
    """
    if not os.path.exists(yaml_path):
        log.warning("wilderness_npcs YAML not found: %s", yaml_path)
        return None

    with open(yaml_path, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)

    if not data:
        return None

    entries = data.get("wilderness_npcs") or []
    for entry in entries:
        if (entry.get("name") or "").strip() == "the Hermit":
            ai_cfg = entry.get("ai_config") or {}
            gate = ai_cfg.get("gate")
            if gate:
                return dict(gate)   # defensive copy
            return None

    return None


def gate_threshold() -> int:
    """Return the Force-sign threshold the Hermit's gate uses.

    Single-source-of-truth accessor. Tests and admin commands should
    call this rather than reading the constant directly, so the
    eventual era.yaml-driven version (per PG.4.polish) can drop in
    without breaking call sites.
    """
    return FORCE_SIGNS_FOR_INVITATION


# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers (currently none beyond what's exported)
# ─────────────────────────────────────────────────────────────────────────────
#
# The Village quest engine drop will add:
#   - select_dialogue_lines(char, gate) -> list[str]
#       picks before_lines vs after_lines based on is_invitation_eligible
#   - record_invitation_delivered(char, db)
#       async DB write that flips the Act 1 unlock flag and triggers
#       the state-machine transition. PG.1.schema's
#       has_received_invitation column is the persistence target.
#
# Both deferred. F.6 ships data + gate seam only.
