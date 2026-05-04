# -*- coding: utf-8 -*-
"""
engine/lightsaber_construction.py — F.7.g — Path A lightsaber forge scene.

Per ``data/worlds/clone_wars/quests/jedi_village.yaml`` (the path_a
branch consequences) and design §7.1: when a Village quest player
commits to Path A (Jedi Order), Master Mace Windu leads them through
the Coruscant Temple's Apprentice Forge to construct their first
lightsaber from the Adegan crystal they earned at the Trial of
Skill.

The yaml-spec'd consequences are:

  - ``village_trial_crystal`` consumed (used at the Temple Forge)
  - ``lightsaber_basic`` granted (basic Padawan lightsaber)
  - ``craft_lightsaber`` skill floor of 4D (bumped if currently lower)

F.7.d recorded ``village_trial_lightsaber_construction_pending`` in
chargen_notes when Path A was committed but did not run the scene
(deferred — the consumer system was not yet built). F.7.g consumes
the marker, runs the scene, and clears the marker.

Integration point
=================

``engine/village_choice.py::_commit_path_a`` calls
``construct_lightsaber(session, db, char)`` between the Mace Windu
narration and the teleport to ``jedi_temple_main_gate``. The scene
is best-effort: if construction fails for any reason (missing
crystal, missing skill registry, DB write failure), the Path A
commit itself is not blocked — the player still teleports, the
Path A flags are still set, and a chargen_notes marker
(``village_trial_lightsaber_construction_failed``) is recorded so
a future drop can offer a retry path.

Skill-floor enforcement
=======================

The ``craft_lightsaber`` skill floor is a one-way bump: if the
character already has 4D+ in the skill, no change is made. If
they have less (or no entry), the skill is set to 4D+0 pips. The
floor is applied to the bonus-above-attribute representation that
is the canonical storage form for character skills (see
``engine/character.py::Character.skills``).

Idempotency
===========

The marker is the idempotency token. ``construct_lightsaber``
returns False without side effects if:
  - the character is not on Path A (defensive)
  - the marker is not set
  - the construction has already run (``village_trial_lightsaber_constructed``
    is True in chargen_notes)
"""
from __future__ import annotations

import json
import logging
from typing import Mapping, Optional

log = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# Per design §7.1 / yaml path_a consequences.
LIGHTSABER_CRAFT_SKILL_FLOOR_DICE = 4   # 4D minimum on craft_lightsaber
CRYSTAL_ITEM_KEY = "village_trial_crystal"
LIGHTSABER_ITEM_KEY = "lightsaber_basic"

# chargen_notes flags
MARKER_PENDING = "village_trial_lightsaber_construction_pending"
MARKER_DONE = "village_trial_lightsaber_constructed"
MARKER_FAILED = "village_trial_lightsaber_construction_failed"


# ─────────────────────────────────────────────────────────────────────────────
# Accessors
# ─────────────────────────────────────────────────────────────────────────────


def _read_chargen_notes(char: Mapping) -> dict:
    """Read chargen_notes JSON defensively. Returns {} on any anomaly."""
    raw = char.get("chargen_notes") or "{}"
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str):
        return {}
    try:
        loaded = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def is_construction_pending(char: Mapping) -> bool:
    """True iff the Path A commit set the pending marker but the
    construction scene has not yet run."""
    notes = _read_chargen_notes(char)
    if notes.get(MARKER_DONE):
        return False
    return bool(notes.get(MARKER_PENDING))


def is_construction_complete(char: Mapping) -> bool:
    """True iff the construction scene has run successfully."""
    return bool(_read_chargen_notes(char).get(MARKER_DONE))


def is_construction_failed(char: Mapping) -> bool:
    """True iff a previous attempt failed (missing crystal, etc.)."""
    return bool(_read_chargen_notes(char).get(MARKER_FAILED))


# ─────────────────────────────────────────────────────────────────────────────
# Skill-floor enforcement
# ─────────────────────────────────────────────────────────────────────────────


def _parse_dice_str(val) -> tuple:
    """Parse a skill-bonus string like '3D', '3D+1', '3D+2' into
    (dice, pips). Returns (0, 0) on any anomaly."""
    if not val:
        return (0, 0)
    s = str(val).strip().upper()
    if not s:
        return (0, 0)
    # Strip a leading '+' if present (some sheets store '+2D')
    s = s.lstrip("+")
    try:
        if "D" in s:
            d_part, _, p_part = s.partition("D")
            dice = int(d_part) if d_part else 0
            pips = 0
            if p_part:
                p_part = p_part.strip().lstrip("+")
                if p_part:
                    pips = int(p_part)
            return (dice, pips)
        # Bare integer — treat as dice
        return (int(s), 0)
    except (TypeError, ValueError):
        return (0, 0)


def _format_dice(dice: int, pips: int) -> str:
    """Format (dice, pips) back to canonical 'ND' or 'ND+P'."""
    if pips == 0:
        return f"{dice}D"
    return f"{dice}D+{pips}"


def ensure_skill_floor(char: dict, skill_key: str, floor_dice: int) -> bool:
    """One-way bump: if character's skill is below ``floor_dice``,
    set it to ``floor_dice``D (0 pips). If at or above, no change.

    Mutates ``char['skills']`` (the JSON string) in place. Returns
    True iff a bump was applied (caller decides whether to persist).
    """
    raw_skills = char.get("skills") or "{}"
    if isinstance(raw_skills, str):
        try:
            skills = json.loads(raw_skills)
        except (json.JSONDecodeError, TypeError):
            skills = {}
    elif isinstance(raw_skills, dict):
        skills = dict(raw_skills)
    else:
        skills = {}

    if not isinstance(skills, dict):
        skills = {}

    current = skills.get(skill_key, "")
    cur_dice, cur_pips = _parse_dice_str(current)

    # Compare in pip-equivalents (1D = 3 pips). If equal or higher, no-op.
    cur_total_pips = cur_dice * 3 + cur_pips
    floor_total_pips = floor_dice * 3
    if cur_total_pips >= floor_total_pips:
        return False

    skills[skill_key] = _format_dice(floor_dice, 0)
    char["skills"] = json.dumps(skills)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Scene runtime
# ─────────────────────────────────────────────────────────────────────────────


async def _set_chargen_flags(db, char: dict, **flags) -> None:
    """Update chargen_notes JSON with the given flags and persist."""
    notes = _read_chargen_notes(char)
    notes.update(flags)
    serialized = json.dumps(notes)
    char["chargen_notes"] = serialized
    await db.save_character(char["id"], chargen_notes=serialized)


async def _emit_construction_scene(session) -> None:
    """Render the Apprentice Forge narration. Pure presentation —
    no state changes. Splitting this out from the side-effect code
    keeps the scene easy to re-render if a future drop wants to
    replay it on demand (lore-collection, etc.)."""
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*The Apprentice Forge sits one level below the "
        "main floor of the Temple. Master Windu leads you down. The "
        "chamber is small, circular, and lit only by the slow blue "
        "burn of a focusing array.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Place the crystal on the bench. Show me your "
        "hands.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*You set the Adegan crystal — the same one you "
        "scored at Daro's anvil weeks ago — onto the bench. Master "
        "Windu watches without speaking. After a moment he gestures, "
        "and a small machined cylinder rises from the bench's centre "
        "well. It is unfinished. Empty. Waiting.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m\"The first one is always the hardest. The "
        "Order will not give you a finished blade; the Order will "
        "give you the parts. Connect them. The crystal will tell you "
        "where it wants to sit. Listen.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*Hours pass. The crystal does, in fact, tell you "
        "where it wants to sit. The cylinder closes around it. The "
        "emitter clicks into place — too tight at first, then exactly "
        "right. You hold the unactivated hilt for a long moment "
        "before pressing the switch.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[2m*The blade ignites. It is blue.*\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;33m*Master Windu nods, once.*\033[0m"
    )
    await session.send_line(
        "  \033[1;33m\"Adequate. Practise the form-zero stances "
        "before you sleep. The blade goes where the body goes; the "
        "body does not yet know where it is going.\"\033[0m"
    )
    await session.send_line("")
    await session.send_line(
        "  \033[1;32m* Lightsaber constructed. *\033[0m"
    )
    await session.send_line(
        "  \033[2mThe Adegan crystal is consumed. craft_lightsaber "
        "set to 4D minimum.\033[0m"
    )
    await session.send_line("")


async def construct_lightsaber(session, db, char: dict) -> bool:
    """Run the Path A lightsaber-construction scene.

    Idempotency:
      - Returns False without side effects if construction is already
        complete or marker is not pending.

    Side effects (when running successfully):
      - Removes ``village_trial_crystal`` from inventory.
      - Adds ``lightsaber_basic`` to inventory.
      - Bumps ``craft_lightsaber`` to 4D if currently lower.
      - Clears ``village_trial_lightsaber_construction_pending``.
      - Sets ``village_trial_lightsaber_constructed`` = True.
      - Emits the Apprentice Forge narration.

    Failure handling:
      - If crystal removal fails (item missing, etc.), records
        ``village_trial_lightsaber_construction_failed`` flag and
        returns False *without* emitting narration. The Path A
        commit will still complete.

    Returns True iff the scene ran end-to-end with side effects.
    """
    if is_construction_complete(char):
        return False
    if not is_construction_pending(char):
        return False

    # ── Consume the crystal ─────────────────────────────────────────
    try:
        removed = await db.remove_from_inventory(
            char["id"], CRYSTAL_ITEM_KEY,
        )
    except Exception:
        log.warning("construct_lightsaber: remove_from_inventory raised "
                    "for char_id=%s", char.get("id"), exc_info=True)
        removed = False

    if not removed:
        # No crystal in inventory. This shouldn't happen normally
        # (Trial of Skill grants the crystal; nothing else removes
        # it before Path A) but defend anyway.
        log.warning(
            "construct_lightsaber: no village_trial_crystal in "
            "inventory for char_id=%s; skipping scene", char.get("id"),
        )
        try:
            await _set_chargen_flags(
                db, char, **{MARKER_FAILED: True},
            )
        except Exception:
            log.warning("construct_lightsaber: failed to record "
                        "failure marker", exc_info=True)
        return False

    # ── Grant the basic lightsaber ──────────────────────────────────
    try:
        await db.add_to_inventory(char["id"], {
            "key": LIGHTSABER_ITEM_KEY,
            "name": "Padawan lightsaber, blue",
            "slot": "weapon_primary",
            "description": (
                "A basic lightsaber, constructed by your own hands at "
                "the Apprentice Forge of the Coruscant Jedi Temple. "
                "The blade is blue. It is not yet a master's weapon, "
                "but it is yours."
            ),
            "modifiers": {
                "damage": "5D",
                "weapon_skill": "lightsaber",
            },
        })
    except Exception:
        log.warning("construct_lightsaber: add_to_inventory failed "
                    "for char_id=%s", char.get("id"), exc_info=True)
        # The crystal is already consumed at this point. Continue —
        # the player gets the marker and the skill floor; they don't
        # get the item but we don't roll back the crystal removal.

    # ── Skill-floor: craft_lightsaber → 4D minimum ──────────────────
    try:
        bumped = ensure_skill_floor(
            char, "craft_lightsaber",
            LIGHTSABER_CRAFT_SKILL_FLOOR_DICE,
        )
        if bumped:
            await db.save_character(char["id"], skills=char["skills"])
    except Exception:
        log.warning("construct_lightsaber: skill-floor bump failed "
                    "for char_id=%s", char.get("id"), exc_info=True)

    # ── Update markers ──────────────────────────────────────────────
    try:
        notes = _read_chargen_notes(char)
        # Clear pending; set done. (Don't carry MARKER_FAILED if it
        # was set on a prior attempt — the scene now succeeded.)
        notes[MARKER_DONE] = True
        notes.pop(MARKER_PENDING, None)
        notes.pop(MARKER_FAILED, None)
        char["chargen_notes"] = json.dumps(notes)
        await db.save_character(
            char["id"], chargen_notes=char["chargen_notes"],
        )
    except Exception:
        log.warning("construct_lightsaber: marker update failed "
                    "for char_id=%s", char.get("id"), exc_info=True)

    # ── Emit narration ──────────────────────────────────────────────
    await _emit_construction_scene(session)

    return True
