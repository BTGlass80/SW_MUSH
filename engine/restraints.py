"""Persistent character restraint state (handcuffs / binders).

CRAFT.HOOK.restraints — a LASTING restraint condition that survives logout,
distinct from the ephemeral combat grapple (engine/combat.py Combatant.restraint,
which is contested each round and cleared when combat ends). A cuffed prisoner
stays cuffed until they break free or a captor releases them.

Design: docs/design/restraints_system_design_v1.md. PvP norm (Brian): a PC may
only cuff another PC who CONSENTS or has been DEFEATED (incapacitated) — never a
healthy unwilling PC.

State lives in the character `attributes` JSON under "restraint" (no schema
migration — mirrors engine/buffs.py consumables). Absent = not restrained, so
every existing character is unchanged.

All credit/dice movement here goes through the funnels: the escape check uses
perform_skill_check; there is no credit movement (binders are a pure item sink,
charged at the verb layer).
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# Conservative defaults (per the balance charter — retunable when T3.19 lands).
DEFAULT_ESCAPE_DIFFICULTY = 15      # Moderate; binders' fixed break-free DC
# Break the binders with raw muscle. "lifting" is the Strength-GOVERNED skill in
# the registry (so perform_skill_check rolls Strength, the WEG-faithful axis) —
# NOT the bare attribute name "strength", which _skill_to_attr mis-maps to the
# perception default (a 2D roll, ignoring the prisoner's real Strength).
ESCAPE_SKILL = "lifting"
_INCAPACITATED = 4                  # WoundLevel.INCAPACITATED — the "defeated" gate


# ── Attributes JSON helpers (mirror engine/buffs.py) ────────────────────────

def _read_attrs(char: dict) -> dict:
    """Return the character's attributes dict (tolerant of str or dict shape)."""
    attrs = char.get("attributes")
    if isinstance(attrs, str):
        try:
            attrs = json.loads(attrs or "{}")
        except (json.JSONDecodeError, TypeError):
            return {}
    return attrs if isinstance(attrs, dict) else {}


def _write_attrs(char: dict, attrs: dict) -> None:
    """Write attrs back into char['attributes'], preserving the storage shape
    (JSON string in the DB shape, dict in-memory). Callers persist via
    save_character(..., attributes=char['attributes'])."""
    was_string = isinstance(char.get("attributes"), str)
    char["attributes"] = json.dumps(attrs) if was_string else attrs


# ── State read ──────────────────────────────────────────────────────────────

def get_restraint(char: dict) -> Optional[dict]:
    """Return the restraint state dict, or None if the character is free."""
    r = _read_attrs(char).get("restraint")
    return r if isinstance(r, dict) and r else None


def is_restrained(char: dict) -> bool:
    """True if the character is currently restrained (cuffed)."""
    return get_restraint(char) is not None


def restraint_consent(char: dict) -> bool:
    """True if the character has opted in to being restrained (RP/willing
    captures) via `allow restrain`."""
    return bool(_read_attrs(char).get("restraint_consent"))


# ── The consent/defeat gate (Brian's PvP norm) ──────────────────────────────

def can_be_restrained(target: dict, *, is_npc: bool = False) -> tuple[bool, str]:
    """Whether `target` may be cuffed right now. Returns (ok, reason).

    PvP norm: a PC may be cuffed only if DEFEATED (wound_level >= INCAPACITATED)
    or CONSENTING (allow restrain). NPCs need no consent. A healthy unwilling PC
    cannot be cuffed (the grief guard)."""
    if is_restrained(target):
        return False, "They are already restrained."
    if is_npc:
        return True, ""
    try:
        wound = int(target.get("wound_level", 0) or 0)
    except (TypeError, ValueError):
        wound = 0
    if wound >= _INCAPACITATED:
        return True, ""        # defeated — subdued in combat
    if restraint_consent(target):
        return True, ""        # willing
    return (False,
            "They're not subdued or willing — you can't get the binders on them.")


# ── Apply / release ─────────────────────────────────────────────────────────

def apply_restraint(target: dict, *, applied_by: str, applied_by_id: int,
                    item_key: str = "binders",
                    escape_difficulty: int = DEFAULT_ESCAPE_DIFFICULTY) -> None:
    """Cuff `target`. Caller is responsible for the gate (can_be_restrained),
    consuming the binders item, and persisting via save_character. We stamp
    `applied_at` so display / future-timeout logic has the apply time."""
    attrs = _read_attrs(target)
    attrs["restraint"] = {
        "applied_by": applied_by,
        "applied_by_id": applied_by_id,
        "item_key": item_key,
        "escape_difficulty": int(escape_difficulty),
        "applied_at": time.time(),
    }
    _write_attrs(target, attrs)


def release_restraint(target: dict) -> bool:
    """Remove the restraint. Returns True if one was present. Caller persists."""
    attrs = _read_attrs(target)
    if "restraint" not in attrs:
        return False
    attrs.pop("restraint", None)
    _write_attrs(target, attrs)
    return True


def can_release(restraint: dict, releaser_id: int, *, is_admin: bool = False) -> bool:
    """Release authority: the captor who applied the cuffs, or an admin. A third
    party can't free a prisoner (capture stays meaningful)."""
    if is_admin:
        return True
    try:
        return int(restraint.get("applied_by_id", -1)) == int(releaser_id)
    except (TypeError, ValueError):
        return False


def set_consent(char: dict, value: bool) -> None:
    """Set the opt-in `allow restrain` consent flag. Caller persists."""
    attrs = _read_attrs(char)
    if value:
        attrs["restraint_consent"] = True
    else:
        attrs.pop("restraint_consent", None)
    _write_attrs(char, attrs)


# ── Escape ──────────────────────────────────────────────────────────────────

def attempt_escape(char: dict) -> tuple[bool, int]:
    """Try to break free with a Strength check vs the restraint's difficulty.

    Returns (escaped, difficulty). On success, the caller clears the restraint
    (release_restraint) + persists. Routes the dice through perform_skill_check
    (the out-of-combat funnel). No-op (False) if not restrained."""
    r = get_restraint(char)
    if not r:
        return False, 0
    difficulty = int(r.get("escape_difficulty", DEFAULT_ESCAPE_DIFFICULTY))
    from engine.skill_checks import perform_skill_check
    result = perform_skill_check(char, ESCAPE_SKILL, difficulty)
    return bool(result.success), difficulty
