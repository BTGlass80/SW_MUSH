# -*- coding: utf-8 -*-
"""
engine/creature_library.py — Sourcebook Enrichment Lane A, **Phase B** core.

PURE module (no DB, no IO). It loads the faithful WEG creature stat blocks from
``data/npcs_creatures.yaml`` and turns them into the shapes the spawn bridge +
combat engine consume:

  * load_creature_library()        — cached {id: creature_dict}
  * get_creature(creature_id)      — one creature or None
  * resolve_natural_attack(...)    — the faithful melee damage for a creature
  * build_creature_char_sheet(...) — a char_sheet_json-ready dict (incl. the
                                     ``natural_attack`` marker the combat engine
                                     now honors via Character/_get_npc_weapon)
  * build_creature_ai_config(...)  — an ai_config_json-ready dict (hostile flag,
                                     fallback lines, encounter/creature ids)

THE DAMAGE PROBLEM THIS SOLVES
------------------------------
Phase A recorded each creature's ``natural_attack.damage`` as human-readable
WEG prose: "STR+1D", "STR+2D+2", "STR+2", absolute "1D", and specials like
"Poison 5D", "opposed (brawling vs..)", "+3D/round once it has the head".
The combat engine (engine/npc_combat_ai.py::_get_npc_weapon) only knows
registry-weapon damage or *bare STR* for unarmed NPCs — and **13/14** library
creatures have a natural attack that is stronger than bare STR. Spawning them
without resolving the attack would make every creature roughly half as
dangerous as the source intends.

``resolve_natural_attack`` parses the clean "STR(+ND)(+N)" / absolute "ND(+N)"
forms (≈11/14) into a concrete dice string using the creature's STR, and
**falls back to bare STR** for the prose/special forms (poison, grapple,
multi-round) while flagging ``special`` so the spawn flavor can still mention
it. Full poison/grapple *mechanics* are a documented follow-up; this ships the
faithful base damage now.
"""
from __future__ import annotations

import os
import random
import re
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Resolved lazily; cached after first load.
_LIBRARY_CACHE: Optional[dict] = None

_CREATURES_PATH = os.path.join("data", "npcs_creatures.yaml")

# Words that mark a special attack rider even when a base damage parses
# (so the spawn flavor can note it; full mechanics are a follow-up).
_SPECIAL_MARKERS = re.compile(
    r"poison|opposed|grasp|grapple|constrict|/round|swallow|drain|web", re.I
)


# ──────────────────────────────────────────────────────────────────────────
# Loader
# ──────────────────────────────────────────────────────────────────────────
def load_creature_library(path: str = _CREATURES_PATH,
                          force_reload: bool = False) -> dict:
    """Load ``npcs_creatures.yaml`` → ``{creature_id: creature_dict}`` (cached).

    Failure-tolerant: a missing/garbled file yields an empty library rather
    than raising, so a bad data drop never aborts a move or a spawn.
    """
    global _LIBRARY_CACHE
    if _LIBRARY_CACHE is not None and not force_reload:
        return _LIBRARY_CACHE
    lib: dict = {}
    try:
        import yaml
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        for c in (data.get("npcs") or []):
            cid = c.get("id")
            if cid:
                lib[str(cid)] = c
    except FileNotFoundError:
        log.warning("[creature_library] %s not found; empty library", path)
    except Exception:
        log.warning("[creature_library] failed to load %s", path, exc_info=True)
    _LIBRARY_CACHE = lib
    return lib


def get_creature(creature_id: str, path: str = _CREATURES_PATH) -> Optional[dict]:
    """Return one creature dict by id, or None."""
    if not creature_id:
        return None
    return load_creature_library(path).get(str(creature_id))


# ──────────────────────────────────────────────────────────────────────────
# Faithful natural-attack damage
# ──────────────────────────────────────────────────────────────────────────
def _str_pool(creature: dict):
    """Return the creature's STR as a DicePool (defaults to 1D)."""
    from engine.character import DicePool
    raw = (((creature.get("char_sheet") or {}).get("attributes") or {})
           .get("strength"))
    try:
        return DicePool.parse(str(raw)) if raw is not None else DicePool(1, 0)
    except Exception:
        return DicePool(1, 0)


# "STR" optionally followed by "+ND" and/or "+N"
_STR_FORM = re.compile(r"^\s*STR\b\s*(?:\+\s*(\d+)\s*D\b)?\s*(?:\+\s*(\d+))?",
                       re.IGNORECASE)
# Absolute "ND" optionally "+N"
_ABS_FORM = re.compile(r"^\s*(\d+)\s*D\b\s*(?:\+\s*(\d+))?\s*$", re.IGNORECASE)


def resolve_natural_attack(creature: dict) -> dict:
    """Resolve a creature's natural attack to concrete combat fields.

    Returns ``{"skill", "damage", "special", "raw"}`` where:
      * skill   — to-hit skill (default "brawling")
      * damage  — a concrete dice string the combat engine can roll
      * special — True if the source carries a rider (poison/grapple/…) or the
                  damage form wasn't cleanly parseable (then damage == bare STR)
      * raw     — the original source string (for flavor)
    """
    from engine.character import DicePool

    na = creature.get("natural_attack") or {}
    skill = str(na.get("to_hit_skill") or na.get("skill") or "brawling").strip() \
        or "brawling"
    raw = str(na.get("damage") or "").strip()
    str_pool = _str_pool(creature)

    special = bool(_SPECIAL_MARKERS.search(raw)) if raw else False

    if not raw:
        return {"skill": skill, "damage": str(str_pool),
                "special": special, "raw": raw}

    m = _STR_FORM.match(raw)
    if m:
        bonus_dice = int(m.group(1)) if m.group(1) else 0
        bonus_pips = int(m.group(2)) if m.group(2) else 0
        dmg = str(DicePool(str_pool.dice + bonus_dice,
                           str_pool.pips + bonus_pips))
        return {"skill": skill, "damage": dmg, "special": special, "raw": raw}

    m = _ABS_FORM.match(raw)
    if m:
        dice = int(m.group(1))
        pips = int(m.group(2)) if m.group(2) else 0
        dmg = str(DicePool(dice, pips))
        return {"skill": skill, "damage": dmg, "special": special, "raw": raw}

    # Prose / special-only form (e.g. "Poison 5D", "opposed (..)", "+3D/round"):
    # fall back to bare STR for the base contact, flag special for flavor.
    return {"skill": skill, "damage": str(str_pool),
            "special": True, "raw": raw}


# ──────────────────────────────────────────────────────────────────────────
# Spawn-ready builders
# ──────────────────────────────────────────────────────────────────────────
def build_creature_char_sheet(creature: dict) -> dict:
    """Build a ``char_sheet_json``-ready dict for ``db.create_npc``.

    Passes the faithful attributes/skills/move through and injects the resolved
    ``natural_attack`` marker (``{skill, damage}``) that
    ``Character.from_npc_sheet`` reads and ``_get_npc_weapon`` honors — so the
    spawned creature fights with its source damage, not bare STR.
    """
    cs = creature.get("char_sheet") or {}
    atk = resolve_natural_attack(creature)
    from engine.creature_special_attacks import parse_special_attacks
    sheet = {
        "name": creature.get("name", creature.get("id", "Creature")),
        "attributes": dict(cs.get("attributes") or {}),
        "skills": dict(cs.get("skills") or {}),
        "move": cs.get("move", 10),
        "force_points": cs.get("force_points", 0),
        "character_points": cs.get("character_points", 0),
        "dark_side_points": cs.get("dark_side_points", 0),
        "weapon": "",  # creatures have no registry weapon
        "natural_attack": {"skill": atk["skill"], "damage": atk["damage"]},
    }
    # Lane A tail: carry the parsed WEG special-attack riders (poison/restraint)
    # so the spawned creature's venom/grab is mechanically live, not just flavor.
    _sa = parse_special_attacks(creature)
    if _sa:
        sheet["special_attack"] = _sa
    return sheet


def build_creature_ai_config(creature: dict, encounter_id: str = "",
                             hostile: bool = True) -> dict:
    """Build an ``ai_config_json``-ready dict for a spawned creature."""
    name = creature.get("name", "creature")
    atk = resolve_natural_attack(creature)
    cfg = {
        "personality": "",
        "hostile": bool(hostile),
        "combat_behavior": "aggressive" if hostile else "skittish",
        "fallback_lines": [
            f"The {name.lower()} bares itself, wary and tense.",
            f"The {name.lower()} shifts, tracking your movement.",
            f"The {name.lower()} makes a low, animal sound.",
        ],
        "is_wilderness_encounter": True,
        "encounter_id": encounter_id,
        "creature_id": creature.get("id", ""),
        # Redundant carry so the combat path can honor faithful damage even if
        # something rebuilds the Character from ai_config alone.
        "natural_attack_damage": atk["damage"],
        "natural_attack_skill": atk["skill"],
    }
    if atk.get("special"):
        cfg["natural_attack_note"] = atk.get("raw", "")
    return cfg


def _roll_low_biased(lo: int, hi: int) -> int:
    """Roll an int in the inclusive range ``[lo, hi]`` with a deliberate LOW bias.

    Takes the ``min`` of two uniform rolls, so the mean sits ~a third of the way
    up the range (e.g. ``[4,6]`` -> mean ~4.56, vs uniform 5.0, vs the old
    always-4). This honors an encounter's authored spawn spread without the
    galaxy-wide difficulty spike a uniform roll would cause, while still often
    spawning the minimum (Brian ruling on TD.ENCOUNTER_COUNT_RANGE_IGNORED:
    "ship, bias low").
    """
    if hi <= lo:
        return lo
    return min(random.randint(lo, hi), random.randint(lo, hi))


def creature_spawn_count(creature: dict, payload: Optional[dict] = None) -> int:
    """Resolve how many to spawn: explicit payload.count wins, else pack low.

    ``payload["count"]`` may be a scalar (``3``) or an authored ``[lo, hi]``
    range (``[4, 6]`` — the live region YAMLs author ranges). A range is now
    rolled LOW-biased via :func:`_roll_low_biased`. Previously ``int([4, 6])``
    raised ``TypeError``, was swallowed, and EVERY ranged encounter silently
    fell back to the creature ``pack_count`` minimum
    (TD.ENCOUNTER_COUNT_RANGE_IGNORED).
    """
    payload = payload or {}
    count = payload.get("count")
    if count is not None:
        if isinstance(count, (list, tuple)):
            try:
                vals = [int(x) for x in count]
            except (TypeError, ValueError):
                vals = []
            if len(vals) == 1:
                return max(1, vals[0])
            if len(vals) >= 2:
                return max(1, _roll_low_biased(min(vals), max(vals)))
            # malformed/empty list -> fall through to pack logic below
        else:
            try:
                return max(1, int(count))
            except (TypeError, ValueError):
                pass
    pc = creature.get("pack_count")
    if isinstance(pc, (list, tuple)) and pc:
        try:
            return max(1, int(pc[0]))
        except (TypeError, ValueError):
            pass
    return 1
