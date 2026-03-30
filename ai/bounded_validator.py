# -*- coding: utf-8 -*-
"""
BoundedContextValidator — hallucination defense for intent parsing.

After the LLM produces a structured ActionRequest, this validator
checks every entity ID and action verb against the live SceneContext.
Any ID or verb not present in the manifest raises a ValueError so the
caller can reject the result rather than silently acting on wrong data.

Usage:
    validator = BoundedContextValidator()
    validated = validator.validate(raw_action_dict, scene_ctx)
    # raises ValueError if anything is invalid
    # returns cleaned ActionRequest dict on success
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ai.scene_context import SceneContext

log = logging.getLogger(__name__)

# Valid action verbs the LLM is allowed to produce
VALID_ACTION_VERBS = frozenset({
    "attack",
    "dodge",
    "fulldodge",
    "full_dodge",
    "parry",
    "fullparry",
    "full_parry",
    "aim",
    "cover",
    "flee",
    "pass",
})

# Normalise LLM aliases to canonical command names
_VERB_NORMALISE = {
    "full_dodge": "fulldodge",
    "full dodge": "fulldodge",
    "full_parry": "fullparry",
    "full parry": "fullparry",
    "shoot": "attack",
    "fire": "attack",
    "strike": "attack",
    "hit": "attack",
    "run": "flee",
    "escape": "flee",
    "evade": "dodge",
    "block": "parry",
    "defend": "dodge",
    "wait": "pass",
    "nothing": "pass",
    "hide": "cover",
    "take cover": "cover",
}


class ValidationError(ValueError):
    """Raised when the LLM output fails bounded-context validation."""
    pass


class BoundedContextValidator:
    """
    Validates an ActionRequest dict against a SceneContext.

    The contract:
    - action verb must be in VALID_ACTION_VERBS (after normalisation)
    - target_id (if present) must be in scene_ctx.entities
    - target_name (if present) must loosely match an entity in scene_ctx
    - skill (if present) must be a plausible D6 skill string (non-empty, no injection)

    Returns a cleaned dict with canonical keys on success.
    Raises ValidationError on any violation.
    """

    def validate(self, raw: dict, scene_ctx: "SceneContext") -> dict:
        """
        Validate and normalise a raw LLM action dict.

        Expected raw keys (all optional except 'action'):
            action      str   — "attack", "dodge", etc.
            target_id   int   — entity ID to act on
            target_name str   — entity name (used if target_id missing/invalid)
            skill       str   — D6 skill to use
            damage      str   — damage dice string e.g. "4D+2"
            cp          int   — Character Points to spend

        Returns cleaned dict with resolved target_id (or 0 if no target needed).
        Raises ValidationError on any violation.
        """
        if not isinstance(raw, dict):
            raise ValidationError(f"Expected dict from LLM, got {type(raw).__name__}")

        # ── Action verb ────────────────────────────────────────────────────
        action_raw = str(raw.get("action", "")).lower().strip()
        if not action_raw:
            raise ValidationError("LLM returned empty 'action' field")

        action = _VERB_NORMALISE.get(action_raw, action_raw)

        if action not in VALID_ACTION_VERBS:
            raise ValidationError(
                f"LLM action '{action_raw}' (→'{action}') is not a valid combat verb. "
                f"Valid verbs: {sorted(VALID_ACTION_VERBS)}"
            )

        result: dict = {"action": action}

        # ── Target resolution ──────────────────────────────────────────────
        needs_target = action in {"attack"}
        target_id_raw = raw.get("target_id")
        target_name_raw = str(raw.get("target_name", "")).strip()

        resolved_id: int = 0

        if target_id_raw is not None:
            try:
                tid = int(target_id_raw)
            except (TypeError, ValueError):
                raise ValidationError(
                    f"LLM target_id '{target_id_raw}' is not an integer"
                )

            if tid not in scene_ctx.entities:
                # Hallucinated ID — try to rescue via name match
                log.warning(
                    "BCV: LLM hallucinated target_id=%d (not in scene). "
                    "Attempting name rescue from target_name='%s'",
                    tid, target_name_raw,
                )
                rescued = _match_by_name(target_name_raw, scene_ctx)
                if rescued is None:
                    raise ValidationError(
                        f"LLM target_id={tid} not found in scene "
                        f"(entities: {list(scene_ctx.entities.keys())})"
                    )
                resolved_id = rescued
                log.info("BCV: rescued target_id=%d via name match", resolved_id)
            else:
                resolved_id = tid

        elif target_name_raw:
            rescued = _match_by_name(target_name_raw, scene_ctx)
            if rescued is None and needs_target:
                raise ValidationError(
                    f"LLM target_name='{target_name_raw}' matched no entity in scene"
                )
            resolved_id = rescued or 0

        elif needs_target:
            # Auto-target: pick the first hostile entity
            hostile = [e for e in scene_ctx.entities.values() if e.is_hostile]
            if hostile:
                resolved_id = hostile[0].id
                log.debug("BCV: auto-targeted hostile entity id=%d", resolved_id)
            elif scene_ctx.entities:
                resolved_id = next(iter(scene_ctx.entities))
                log.debug("BCV: auto-targeted first entity id=%d", resolved_id)
            else:
                raise ValidationError("'attack' action needs a target but no entities in scene")

        if resolved_id:
            result["target_id"] = resolved_id

        # ── Skill ──────────────────────────────────────────────────────────
        skill_raw = str(raw.get("skill", "")).strip()
        if skill_raw:
            skill = _sanitise_skill(skill_raw)
            if skill:
                result["skill"] = skill

        # ── Damage ────────────────────────────────────────────────────────
        damage_raw = str(raw.get("damage", "")).strip()
        if damage_raw:
            damage = _sanitise_dice(damage_raw)
            if damage:
                result["damage"] = damage

        # ── CP spend ──────────────────────────────────────────────────────
        cp_raw = raw.get("cp", 0)
        try:
            cp = max(0, int(cp_raw))
        except (TypeError, ValueError):
            cp = 0
        if cp:
            result["cp"] = cp

        return result


# ── Helpers ────────────────────────────────────────────────────────────────────

def _match_by_name(name: str, scene_ctx: "SceneContext") -> Optional[int]:
    """Try to match an entity by name (case-insensitive prefix match)."""
    if not name:
        return None
    name_lower = name.lower().strip()
    # Exact match first
    for eid, entity in scene_ctx.entities.items():
        if entity.name.lower() == name_lower:
            return eid
    # Prefix match
    for eid, entity in scene_ctx.entities.items():
        if entity.name.lower().startswith(name_lower):
            return eid
    # Substring match
    for eid, entity in scene_ctx.entities.items():
        if name_lower in entity.name.lower():
            return eid
    return None


def _sanitise_skill(skill: str) -> str:
    """
    Sanitise a skill string from the LLM.
    Returns empty string if the value looks dangerous or nonsensical.
    """
    import re
    # Allow only alphanumeric + space + underscore + hyphen, max 40 chars
    cleaned = re.sub(r"[^a-zA-Z0-9 _\-]", "", skill).strip()[:40]
    if not cleaned:
        return ""
    # Reject anything that looks like injection
    lower = cleaned.lower()
    bad_words = {"select", "insert", "update", "delete", "drop", "exec", "eval"}
    if any(b in lower for b in bad_words):
        return ""
    return cleaned.lower()


def _sanitise_dice(dice: str) -> str:
    """
    Sanitise a WEG D6 dice string from the LLM.
    Valid forms: 3D, 3D+2, STR+1D, 4D+1, etc.
    Returns empty string on failure.
    """
    import re
    cleaned = dice.strip().upper()[:20]
    # Pattern: optional prefix (STR/DEX), number + D, optional +/- pip
    if re.match(r'^([A-Z]{2,4}\+)?(\d+D)(\+\d+)?$', cleaned):
        return cleaned
    # Also allow plain e.g. "4D+1", "STR+2D"
    if re.match(r'^\d+D(\+\d+|-\d+)?$', cleaned):
        return cleaned
    return ""
