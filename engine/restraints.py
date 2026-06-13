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


# ── Async orchestration (the verb-layer back ends, mirror engine/breaching) ──

BINDERS_KEY = "binders"


async def attempt_cuff(db, char: dict, target_name: str, *,
                       session_mgr=None) -> dict:
    """Resolve `target_name` in the room, apply the consent/defeat gate, consume
    one binders item, and cuff them. Returns {ok, msg, target_name?}.

    The actor must hold a binders consumable. The target must be DEFEATED or
    CONSENTING (PC) — NPCs are exempt. Mirrors engine/breaching.attempt_breach:
    the engine does the work; the parser is a thin front end."""
    from engine.matching import match_in_room
    from engine.buffs import has_consumable, consume_consumable

    target_name = (target_name or "").strip()
    if not target_name:
        return {"ok": False, "msg": "  Cuff whom?"}

    if not has_consumable(char, BINDERS_KEY):
        return {"ok": False,
                "msg": "  You don't have any binders to cuff someone with."}

    match = await match_in_room(
        target_name, char.get("room_id"), char["id"], db,
        session_mgr=session_mgr, source_char=char)
    if not match.found:
        return {"ok": False, "msg": f"  {match.error_message(target_name)}"}

    target = match.candidate.data
    is_npc = match.candidate.obj_type == "npc"
    if not is_npc and match.candidate.id == char["id"]:
        return {"ok": False, "msg": "  You can't cuff yourself."}

    # v1 cuffs PCs only. NPC capture needs the restraint state to live in the
    # NPC's char_sheet_json (NPCs have no `attributes` column) — a future
    # increment; the consent/defeat gate is fundamentally a PvP feature anyway.
    if is_npc:
        return {"ok": False,
                "msg": "  You can't get binders on a creature like that "
                       "(restraining NPCs isn't supported yet)."}

    ok, reason = can_be_restrained(target, is_npc=is_npc)
    if not ok:
        return {"ok": False, "msg": f"  {reason}"}

    # Apply, then consume the binders (a successful cuff spends them).
    apply_restraint(target, applied_by=char.get("name", "someone"),
                    applied_by_id=char["id"], item_key=BINDERS_KEY)
    consume_consumable(char, BINDERS_KEY)
    try:
        await db.save_character(char["id"], attributes=char.get("attributes"))
        await db.save_character(target["id"],
                                attributes=target.get("attributes"))
    except Exception:
        log.warning("[restraints] cuff persist failed", exc_info=True)

    tname = match.candidate.name
    return {"ok": True, "target_name": tname, "target_id": target["id"],
            "msg": f"  You snap the binders onto {tname}. They're restrained."}


async def attempt_uncuff(db, char: dict, target_name: str, *,
                         session_mgr=None, is_admin: bool = False) -> dict:
    """Release `target_name`'s restraint, if the actor is the captor or an admin.
    Returns {ok, msg}."""
    from engine.matching import match_in_room

    target_name = (target_name or "").strip()
    if not target_name:
        return {"ok": False, "msg": "  Uncuff whom?"}

    match = await match_in_room(
        target_name, char.get("room_id"), char["id"], db,
        session_mgr=session_mgr, source_char=char)
    if not match.found:
        return {"ok": False, "msg": f"  {match.error_message(target_name)}"}

    target = match.candidate.data
    r = get_restraint(target)
    if not r:
        return {"ok": False, "msg": f"  {match.candidate.name} isn't restrained."}

    if not can_release(r, char["id"], is_admin=is_admin):
        return {"ok": False,
                "msg": "  Only the one who cuffed them (or an admin) can "
                       "release them."}

    release_restraint(target)
    try:
        await db.save_character(target["id"],
                                attributes=target.get("attributes"))
    except Exception:
        log.warning("[restraints] uncuff persist failed", exc_info=True)

    return {"ok": True, "target_name": match.candidate.name,
            "msg": f"  You release {match.candidate.name} from their binders."}


async def attempt_escape_action(db, char: dict) -> dict:
    """The `escape` verb back end: try to break free, persist on success.
    Returns {ok, escaped, msg}."""
    if not is_restrained(char):
        return {"ok": False, "escaped": False,
                "msg": "  You aren't restrained."}
    escaped, difficulty = attempt_escape(char)
    if escaped:
        release_restraint(char)
        try:
            await db.save_character(char["id"],
                                    attributes=char.get("attributes"))
        except Exception:
            log.warning("[restraints] escape persist failed", exc_info=True)
        return {"ok": True, "escaped": True,
                "msg": "  With a surge of effort you wrench free of the "
                       "binders!"}
    return {"ok": True, "escaped": False,
            "msg": "  You strain against the binders but can't break free."}


async def set_consent_action(db, char: dict, value: bool) -> dict:
    """The `allow restrain` toggle: opt in/out of being restrained. Persists."""
    set_consent(char, value)
    try:
        await db.save_character(char["id"], attributes=char.get("attributes"))
    except Exception:
        log.warning("[restraints] consent persist failed", exc_info=True)
    if value:
        return {"ok": True, "msg": "  You signal that you'll allow yourself to "
                                   "be restrained (for willing captures / RP)."}
    return {"ok": True, "msg": "  You will no longer allow being restrained "
                              "unless subdued."}
