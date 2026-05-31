# -*- coding: utf-8 -*-
"""
engine/kyber_attunement.py — Kyber shard acquisition (SYN.6.c, 2026-05-25).

Per ``contestable_wilderness_design_v2.md`` §2.5.6: T5 master-crafted
lightsaber crafting requires ``kyber_shard_minor`` of quality 75+.
The design says: *"from force-resonant landmarks in any wilderness
region"*.

This module is the engine-side seam for that acquisition path. A
Force-sensitive character entering a wilderness room flagged
``force_resonant: true`` can run the ``attune`` command to perform a
Knowledge skill check against the kyber resonance. On success, they
receive 1 ``kyber_shard_minor`` resource stack at a quality scaled by
their skill margin (q75 baseline → q95 with strong margins).

Distinct from harvest mechanically:
  * Not on the harvest cooldown — has its own 24h-per-landmark
    cooldown (kyber shards are NOT a renewable resource per
    landmark; the design intends scarcity).
  * Gated by ``is_jedi_pc`` (force-sensitive only). Non-Jedi
    characters at a force-resonant landmark get a thematic "you
    sense something but cannot grasp it" response.
  * Skill: ``meditate`` if it exists, fall back to ``knowledge``
    raw attribute (WEG D6 R&E doesn't have a dedicated "Force
    detection" skill — meditation/knowledge is the closest fit).
  * Quality range: q75 (the T5 floor) to q95 (top-of-band; the q100
    bonus is reserved for the SYN.7/SYN.8 T3 anomaly kyber drops
    when those land).

This is a player surface (parser command `attune` lives in
``parser/attune_command.py``). The engine entry point is callable
without the parser for tests + future Director-AI usage.
"""
from __future__ import annotations

import json
import logging
import random
import time
from typing import Optional

log = logging.getLogger(__name__)


# ── Constants ────────────────────────────────────────────────────────────────

# Skill check difficulty — design language is "force-resonant
# landmark" → "minor kyber shard". The shard is "minor" (not the
# heart-of-a-temple kyber the Jedi spec needed). Moderate difficulty
# (11 on WEG D6 R&E ladder) is the right band — Easy would mean any
# Padawan auto-passes; Difficult would mean only Masters succeed.
ATTUNE_DIFFICULTY = 11
ATTUNE_SKILL = "knowledge"  # raw attribute fallback; see _resolve_skill

# Skill alternatives — if the character has one of these as a trained
# skill, perform_skill_check uses the trained skill pool (better than
# the raw attribute). Picked from the existing SW_MUSH skill catalogue.
ATTUNE_PREFERRED_SKILLS = ("scholar", "willpower")

# 24h per-landmark cooldown. Kyber shards are not a renewable harvest
# — once a Jedi has attuned to a specific resonant site, the
# resonance settles for a day before another shard surfaces. Design
# intent is scarcity; this also prevents farming.
ATTUNE_COOLDOWN_SECS = 24 * 60 * 60
COOLDOWN_KEY_PREFIX = "attune_"

# Output quality band. Floor matches the T5 component min_quality
# (engine.crafting.T5_MIN_QUALITY = 75). Ceiling stays below q100 to
# reserve top-of-band for the Tier-3 anomaly drops (SYN.8) which
# represent the *major* kyber finds — a Jedi pulling a perfect crystal
# off a krayt dragon's bone-bed, not surveying a resonance pillar.
QUALITY_FLOOR = 75
QUALITY_CEILING = 95

# Margin scaling: 5-pt skill margin bands give +5 quality each.
# WEG margin tradition. 0 margin → q75, +10 margin → q85, +20+ → q95.
_MARGIN_BAND_SIZE = 5
_QUALITY_BONUS_PER_BAND = 5


# ── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_skill(char: dict) -> str:
    """Pick the best available skill for the attune roll.

    Preference order: scholar → willpower → knowledge (the governing
    attribute, used as fallback). The skill_checks module already
    falls back from skill to attribute internally — but picking a
    *trained* skill here means the character gets credit for their
    training, not just their raw 3D Knowledge.
    """
    skills_raw = char.get("skills", "{}")
    if isinstance(skills_raw, str):
        try:
            skills = json.loads(skills_raw)
        except (json.JSONDecodeError, TypeError):
            skills = {}
    elif isinstance(skills_raw, dict):
        skills = skills_raw
    else:
        skills = {}
    for s in ATTUNE_PREFERRED_SKILLS:
        if skills.get(s):
            return s
    return ATTUNE_SKILL


def _room_is_force_resonant(room: dict) -> bool:
    """Return True iff ``room['properties']['force_resonant'] is True``."""
    props_raw = room.get("properties")
    if not props_raw:
        return False
    if isinstance(props_raw, str):
        try:
            props = json.loads(props_raw)
        except (json.JSONDecodeError, TypeError):
            return False
    elif isinstance(props_raw, dict):
        props = props_raw
    else:
        return False
    return props.get("force_resonant") is True


def _compute_kyber_quality(margin: int) -> float:
    """Map skill-check margin → kyber shard quality (75..95).

    A negative margin doesn't reach here — the caller short-circuits
    on failed skill check. At margin 0 (exact-DC success), the shard
    is q75 (the T5 floor). Each 5-pt margin band adds +5 quality,
    capped at q95.
    """
    if margin < 0:
        return float(QUALITY_FLOOR)  # defensive; not normally reached
    bands = margin // _MARGIN_BAND_SIZE
    quality = QUALITY_FLOOR + bands * _QUALITY_BONUS_PER_BAND
    return float(min(QUALITY_CEILING, quality))


# ── Main entry point ─────────────────────────────────────────────────────────

async def attune_to_landmark(
    db, char: dict, room_id: int,
    *,
    rng: Optional[random.Random] = None,
    now: Optional[float] = None,
) -> dict:
    """Attempt to attune to a force-resonant landmark and acquire a
    ``kyber_shard_minor`` resource stack.

    Returns a result dict:

      ``{
          "ok":            bool,
          "msg":           str,
          "quality":       float | None,  # awarded shard quality
          "skill_used":    str,
          "skill_roll":    int,
          "margin":        int,
          "cooldown_set":  bool,
      }``

    Failure conditions (in order):
      1. Room not found → "you are nowhere"
      2. Room not flagged ``force_resonant`` → "no resonance here"
      3. Character not force-sensitive → "you sense, but cannot grasp"
      4. Cooldown active (24h per landmark) → "the resonance is silent"
      5. Skill check failed → "you cannot find the shard's pattern"

    Success:
      * Roll Knowledge (or trained scholar/willpower) vs DC 11.
      * Quality = q75 + (margin // 5) × 5, capped at q95.
      * Grant 1 kyber_shard_minor stack via engine.crafting.add_resource.
      * Set per-landmark cooldown.
    """
    if now is None:
        now = time.time()
    if rng is None:
        rng = random.Random()

    # ── Step 1: room resolution ─────────────────────────────────────────────
    try:
        room = await db.get_room(room_id)
    except Exception:
        log.warning("[attune] get_room failed for %s", room_id, exc_info=True)
        room = None
    if not room:
        return {
            "ok": False,
            "msg": "You are nowhere a kyber resonance could be felt.",
            "quality": None,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }

    # ── Step 2: force_resonant gate ─────────────────────────────────────────
    if not _room_is_force_resonant(room):
        return {
            "ok": False,
            "msg": ("This place has no force resonance. Kyber shards "
                    "surface only at landmarks where the Force runs "
                    "near the surface."),
            "quality": None,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }

    # ── Step 3: force-sensitivity gate ──────────────────────────────────────
    try:
        from engine.weight_of_war import is_jedi_pc
    except Exception:
        log.warning("[attune] is_jedi_pc import failed", exc_info=True)
        # Fail closed — without the predicate, refuse rather than
        # opening the seam to non-Jedi.
        return {
            "ok": False,
            "msg": "The Force is silent to you here.",
            "quality": None,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }
    if not is_jedi_pc(char):
        return {
            "ok": False,
            "msg": ("You sense something resonant here, but cannot "
                    "grasp its pattern. Only those attuned to the "
                    "Force can draw a kyber shard from this place."),
            "quality": None,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }

    # ── Step 4: cooldown check (per-landmark) ───────────────────────────────
    from engine.cooldowns import (
        check_cooldown, remaining_cooldown, set_cooldown, format_remaining,
    )
    cd_key = f"{COOLDOWN_KEY_PREFIX}{room_id}"
    if not check_cooldown(char, cd_key):
        rem = remaining_cooldown(char, cd_key)
        return {
            "ok": False,
            "msg": (f"The resonance here is silent — you've drawn from "
                    f"this place too recently. ({format_remaining(rem)} "
                    f"remaining.)"),
            "quality": None,
            "skill_used": "",
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }

    # ── Step 5: skill check ─────────────────────────────────────────────────
    skill = _resolve_skill(char)
    from engine.skill_checks import perform_skill_check
    try:
        sc = perform_skill_check(char, skill, ATTUNE_DIFFICULTY)
    except Exception:
        log.warning("[attune] perform_skill_check raised", exc_info=True)
        # Don't burn the cooldown on engine errors — character can retry.
        return {
            "ok": False,
            "msg": "Your concentration fractures. Try again.",
            "quality": None,
            "skill_used": skill,
            "skill_roll": 0,
            "margin": 0,
            "cooldown_set": False,
        }

    # ── Step 6: set cooldown (even on failed check) ─────────────────────────
    # A failed attune still consumes the cooldown — otherwise a Jedi
    # could spam-roll for Wild Die explosions. Design intent is
    # measured engagement: meditation, not slot-machine.
    set_cooldown(char, cd_key, ATTUNE_COOLDOWN_SECS)
    try:
        await db.save_character(char["id"], attributes=char["attributes"])
    except Exception:
        log.warning("[attune] cooldown save failed", exc_info=True)

    # ── Step 7: handle failed-check exit ────────────────────────────────────
    if not sc.success:
        return {
            "ok": True,  # call succeeded, payout empty
            "msg": ("You reach for the resonance but cannot find the "
                    "shard's pattern. Return tomorrow."),
            "quality": None,
            "skill_used": skill,
            "skill_roll": sc.roll,
            "margin": sc.margin,
            "cooldown_set": True,
        }

    # ── Step 8: compute quality + grant resource ────────────────────────────
    quality = _compute_kyber_quality(sc.margin)
    try:
        from engine.crafting import add_resource
        add_resource(char, "kyber_shard_minor", 1, quality)
        await db.save_character(char["id"], inventory=char["inventory"])
    except Exception:
        log.warning("[attune] resource grant failed", exc_info=True)
        return {
            "ok": False,
            "msg": ("The shard surfaces but slips from your grasp. "
                    "Something is wrong — try again."),
            "quality": None,
            "skill_used": skill,
            "skill_roll": sc.roll,
            "margin": sc.margin,
            "cooldown_set": True,
        }

    log.info(
        "[attune] %s acquired kyber_shard_minor q%.0f at room %s "
        "(margin +%d)",
        char.get("name", "?"), quality, room_id, sc.margin,
    )

    return {
        "ok": True,
        "msg": (f"The resonance crystallises. You hold a minor kyber "
                f"shard, its facets faint but unmistakable. "
                f"(quality {quality:.0f}/100)"),
        "quality": quality,
        "skill_used": skill,
        "skill_roll": sc.roll,
        "margin": sc.margin,
        "cooldown_set": True,
    }
