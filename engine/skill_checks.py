# -*- coding: utf-8 -*-
"""
engine/skill_checks.py  --  Out-of-combat skill check helpers
SW_MUSH  |  Economy Phase 2  |  v22 dice-unified

Centralised helpers for non-combat skill checks used across
the mission, bounty, and smuggling systems.

Design principles:
  - Every check uses the character's actual skill pool (attribute + bonus)
  - Untrained use is allowed — you roll the raw attribute
  - Results produce: success/fail, margin, narrative flavour
  - Partial success possible on a near-miss (margin >= -4)
  - Wild Die applies (exploding 6, complication on 1)
  - ALL rolls delegate to engine.dice.roll_d6_pool — ONE dice engine

Difficulty scale (WEG D6 R&E p82 — canonical ladder):
  Very Easy    5
  Easy        10
  Moderate    15
  Difficult   20
  Very Diff   25
  Heroic      30+

Note: mission_difficulty() uses intermediate values (8, 11, 14, etc.)
for game-specific reward scaling. These are deliberate tuning, not a
divergent ladder.
"""
import json
import logging
from dataclasses import dataclass
from typing import Optional

from engine.dice import DicePool, roll_d6_pool

log = logging.getLogger(__name__)


# ── Dice-string parser (canonical home) ───────────────────────────────────────
# QA HIGH (phantom-import family, 2026-06-19): four call sites
# (sabacc_commands, builtin_commands ×2, space_commands) all did
# `from engine.skill_checks import _parse_dice_str` to read an NPC's
# bargain/gambling dice off its char_sheet_json — but the function lived
# ONLY in engine.lightsaber_construction, so every import raised
# ImportError, was swallowed by the surrounding `except Exception`, and
# the NPC pool silently fell back to a flat default. The callers were
# right; the function just wasn't here. This is its canonical home
# (lightsaber_construction now imports it from here — one source of truth).
# Unlike DicePool.parse(), this is total: it returns (0, 0) on any
# anomaly instead of raising, which is exactly what the swallow-prone
# call sites expect.
def _parse_dice_str(val) -> tuple:
    """Parse a skill-bonus string like '3D', '3D+1', '3D+2' into
    (dice, pips). Returns (0, 0) on any anomaly (None, empty, garbage)."""
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


def _pool_to_str(dice: int, pips: int) -> str:
    """Format a (dice, pips) pool as a WEG D6 string: '4D', '4D+2'.

    Inverse of _parse_dice_str. Canonical home is skill_checks so callers
    can import both from one place without a circular dependency.
    """
    if pips == 0:
        return f"{dice}D"
    return f"{dice}D+{pips}"


# ── Module-level SkillRegistry singleton ──────────────────────────────────────
# Loaded once on first use, not per call.  Eliminates S1 from the audit.

_default_registry = None


def _get_default_registry():
    global _default_registry
    if _default_registry is None:
        try:
            import os as _os
            from engine.character import SkillRegistry
            _default_registry = SkillRegistry()
            _here = _os.path.dirname(_os.path.abspath(__file__))
            _root = _os.path.dirname(_here)
            _path = _os.path.join(_root, "data", "skills.yaml")
            _default_registry.load_file(_path)
        except Exception:
            log.warning("Failed to load default SkillRegistry", exc_info=True)
            _default_registry = None
    return _default_registry


# ── Result dataclass ─────────────────────────────────────────────────────────

@dataclass
class SkillCheckResult:
    roll: int           # Raw total including Wild Die
    difficulty: int
    success: bool       # roll >= difficulty
    margin: int         # roll - difficulty (negative = failure margin)
    critical_success: bool  # Wild Die exploded at least once AND succeeded
    fumble: bool        # Wild Die came up 1 (complication)
    skill_used: str
    pool_str: str       # e.g. "4D+2"
    # Gundark Drop F (2026-06-12): carried-tool bonus surface. Both
    # default-valued — additive-safe for every existing constructor and
    # consumer. tool_name is set when a tool contributed, for UIs that
    # want to credit it ("Code Slicer +1D").
    tool_pips: int = 0
    tool_name: "Optional[str]" = None


# ── Core skill check ─────────────────────────────────────────────────────────

# E2: skills affected by the SANDSTORM world event's perception_penalty. Limited
# to the observation/visual family so the penalty never touches the many social
# skills (con/persuasion/bargain/intimidation/command) that merely fall back to
# the PERCEPTION attribute. Tunable.
_ENV_PERCEPTION_SKILLS = frozenset({"perception", "search"})


def _best_tool_bonus(char: dict, skill_name: str) -> tuple[int, "Optional[str]"]:
    """Gundark Drop F (2026-06-12): carried-tool skill bonus.

    Scan the character's carried items for gear dicts bearing a
    ``skill_bonus`` mapping ({"skill": <key>, "bonus": "+1D"}) whose
    skill canonicalizes to this check's skill, and return the single
    BEST one as (pips, item_name). Tools never stack — the best one
    applies (carrying two medscanners is one medscanner that beeps
    twice). Inventory source + shape tolerance mirror
    engine.hazards._has_mitigation. Fail-open: a malformed item must
    never break a roll.

    Lives at the chokepoint for the same reason SRB.3's lead bonus
    does — every out-of-combat caller benefits without knowing the
    mechanic exists. Combat is structurally untouched: engine/combat
    builds its pools directly and never calls perform_skill_check.
    """
    best_pips = 0
    best_name = None
    try:
        inv = char.get("inventory", "[]")
        if isinstance(inv, str):
            inv = json.loads(inv) if inv else {}
        items = inv.get("items", []) if isinstance(inv, dict) else (
            inv if isinstance(inv, list) else [])
        if not items:
            return 0, None
        from engine.character import canonical_skill_key
        from engine.dice import DicePool
        for item in items:
            if not isinstance(item, dict):
                continue
            sb = item.get("skill_bonus")
            if not isinstance(sb, dict):
                continue
            if canonical_skill_key(str(sb.get("skill", ""))) != skill_name:
                continue
            try:
                p = DicePool.parse(str(sb.get("bonus", "")).lstrip("+"))
                pips = p.dice * 3 + p.pips
            except Exception:
                continue
            if pips > best_pips:
                best_pips = pips
                best_name = item.get("name", item.get("key", "tool"))
    except Exception:
        log.debug("tool-bonus scan failed (roll unaffected)", exc_info=True)
        return 0, None
    return best_pips, best_name


def perform_skill_check(
    char: dict,
    skill_name: str,
    difficulty: int,
    skill_registry=None,
    *,
    lead_bonus: Optional[int] = None,
    auto_consume_lead: bool = True,
) -> SkillCheckResult:
    """
    Perform a skill check for a character dict.

    Args:
        char: Character dict from session (has 'attributes', 'skills' keys).
        skill_name: Lowercase skill name e.g. "con", "search", "blaster".
        difficulty: Target number.
        skill_registry: SkillRegistry instance (uses module singleton if None).
        lead_bonus: SRB.3 — explicit bonus in pips to add (1D = 3 pips). If
            None and ``auto_consume_lead`` is True, the function will look
            up any active combined-action offer the character is a member
            of and consume it, applying its bonus_pips to this roll. Pass
            ``0`` explicitly to suppress the auto-consume.
        auto_consume_lead: SRB.3 — when True (default), do the
            combined-action lookup if ``lead_bonus`` is None. When False,
            the helper never touches the in-memory offers (use for test
            isolation or for code paths that need to roll independently
            of any active lead).

    Returns:
        SkillCheckResult
    """
    if skill_registry is None:
        skill_registry = _get_default_registry()

    # 2026-06-11 skill-key unification: canonicalize ONCE at the
    # chokepoint ingress so every downstream consumer (_get_skill_pool,
    # _skill_to_attr, the env-perception gate) sees one dialect.
    # schematics.yaml passes underscore-form ("blaster_repair"),
    # MISSION_SKILL_MAP passes space-form ("space transports repair") —
    # before this, underscore callers resolved as UNTRAINED **and**
    # mapped to the wrong governing attribute (the "perception"
    # default): a Blaster Repair 3D / Technical 3D crafter rolled raw
    # 2D Perception. See engine.character.canonical_skill_key.
    from engine.character import canonical_skill_key
    skill_name = canonical_skill_key(skill_name)

    # SRB.3 (May 22 2026): resolve a combined-action bonus if applicable.
    # Per support_role_buffs_design_v1.md §4, a leader who passes their
    # Command roll stages a pending bonus; the next skill roll from any
    # member of the lead consumes it. We do the lookup HERE so that
    # every consumer of perform_skill_check automatically benefits from
    # an active lead without each call site needing to know about it.
    effective_lead_pips = 0
    if lead_bonus is not None:
        effective_lead_pips = int(lead_bonus)
    elif auto_consume_lead:
        try:
            from engine.combined_actions import consume_lead_bonus
            char_id = char.get("id")
            if char_id is not None:
                effective_lead_pips = consume_lead_bonus(int(char_id))
        except Exception:
            log.warning("perform_skill_check: lead-bonus lookup failed",
                        exc_info=True)
            effective_lead_pips = 0

    # Parse character's skill pool
    dice, pips = _get_skill_pool(char, skill_name, skill_registry)

    # E2: environmental observation penalty (SANDSTORM world event). Applies a
    # flat pip modifier to observation checks (the perception/search family)
    # while a sandstorm is active. Guarded to those skills (see
    # _ENV_PERCEPTION_SKILLS) and a no-op (default 0) when no event is active —
    # transparent to the test suite and to every non-observation check, and the
    # only path here that touches the world-event singleton.
    env_pips = 0
    if skill_name in _ENV_PERCEPTION_SKILLS:
        try:
            from engine.world_events import get_world_event_manager
            env_pips = int(get_world_event_manager().get_effect("perception_penalty", 0) or 0)
        except Exception:
            env_pips = 0

    # Gundark Drop F: carried-tool bonus (best single tool, no stacking).
    tool_pips, tool_name = _best_tool_bonus(char, skill_name)

    # Apply buff/debuff modifiers (in pips) AND any SRB.3 lead bonus
    try:
        from engine.buffs import get_buff_modifier
        attr_name = _skill_to_attr(skill_name, skill_registry)
        buff_pips = get_buff_modifier(char, attr_name)
        total_buff_pips = buff_pips + effective_lead_pips + env_pips + tool_pips
        if total_buff_pips:
            total_pips = dice * 3 + pips + total_buff_pips
            total_pips = max(3, total_pips)  # Floor: 1D minimum
            dice = total_pips // 3
            pips = total_pips % 3
    except Exception:
        # Even if buff system errors out, apply the lead bonus + environmental
        # penalty alone if present — they're independent mechanics.
        _fallback_pips = effective_lead_pips + env_pips + tool_pips
        if _fallback_pips:
            total_pips = dice * 3 + pips + _fallback_pips
            total_pips = max(3, total_pips)
            dice = total_pips // 3
            pips = total_pips % 3

    pool = DicePool(dice, pips)
    pool_str = str(pool)

    # Roll through the ONE canonical dice engine
    roll = roll_d6_pool(pool)

    success = roll.total >= difficulty
    margin = roll.total - difficulty

    # T3.19 telemetry: this is the single funnel for ALL out-of-combat dice,
    # so one emit captures skill-check success rates by skill + difficulty band
    # (catalog D — are DCs calibrated). Fail-open + buffer-only (non-blocking).
    # Skill checks are the highest-frequency of the instrumented chokepoints,
    # so the keep-rate is a tunable (read at use-site per the T3.19 contract):
    # 1.0 = capture everything at launch's small population; dial down later.
    try:
        from engine.telemetry import emit as _tele_emit
        from engine.tunables import get_tunable
        _tele_emit("skill_check", {
            "char_id": char.get("id"),
            "skill": skill_name,
            "difficulty": difficulty,
            "roll": roll.total,
            "success": success,
            "margin": margin,
            "crit": roll.exploded and success,
            "fumble": roll.complication,
        }, sample=float(get_tunable("telemetry.skill_check_sample", 1.0)))
    except Exception as _e:
        log.debug("skill_check telemetry emit failed: %s", _e)

    return SkillCheckResult(
        roll=roll.total,
        difficulty=difficulty,
        success=success,
        margin=margin,
        critical_success=roll.exploded and success,
        fumble=roll.complication,
        skill_used=skill_name,
        pool_str=pool_str,
        tool_pips=tool_pips,
        tool_name=tool_name if tool_pips else None,
    )


# ── SRB.2 morale-aware skill check ────────────────────────────────────────
#
# Per support_role_buffs_design_v1.md §2.1–§2.3: a successful `perform`
# in a cantina room creates a morale aura on the room. The aura reduces
# the difficulty of morale-flavored rolls for everyone in the room.
#
# Affected skills (design §2.3):
#   - Willpower (any check; resisting fear / persuasion / intimidation)
#   - Command   (when leading a combined action)
#   - Persuasion / con   (interpersonal / social)
#   - Dark Side fall check (the high-difficulty Willpower roll)
#
# NOT affected: combat skills (blaster/dodge/melee/brawling), technical,
# mechanical, knowledge, Force-power rolls themselves, damage rolls.
#
# Implementation note: `perform_skill_check` is synchronous; the aura
# lookup requires DB. We expose a separate async wrapper
# `perform_morale_aware_check` so consumers that want aura-aware checks
# can opt in without forcing all callers to async. The Fall check is
# the canonical first consumer.

MORALE_FLAVORED_SKILLS = frozenset({
    "willpower",
    "command",
    "persuasion",
    "con",         # alias used in some chargen content
    # T2.11.b (2026-06-05): broadened beyond v1 to the cantina-social core.
    # A performance lifts the mood, so deals, the sabacc table, and working
    # the room all get easier. Intimidation is deliberately EXCLUDED — the
    # aura uplifts, while intimidation instills fear; a warm, lively room
    # makes it harder, not easier. Combat/technical/mechanical/knowledge/
    # Force-power rolls remain unaffected.
    "bargain",     # haggling buoyed by good cheer
    "gambling",    # confidence at the sabacc table (the cantina's heart)
    "streetwise",  # working a lively room for information / connections
})


def is_morale_flavored(skill_name: str) -> bool:
    """True if a skill is in the aura-affected set per design §2.3.

    Used by both `perform_morale_aware_check` and any consumer that
    wants to know whether a roll would benefit from a morale aura
    before doing the DB lookup.
    """
    return skill_name.lower() in MORALE_FLAVORED_SKILLS


async def get_morale_aura_magnitude(db, room_id: int,
                                     now: float | None = None) -> int:
    """Return the active aura magnitude for a room, or 0 if none.

    `now` defaults to the current wall clock. Filters expired auras
    inline (matches the look-renderer's behavior); the periodic tick
    reaps the actual rows.
    """
    import time as _time
    if now is None:
        now = _time.time()
    try:
        aura = await db.get_morale_aura(room_id)
    except Exception:
        log.warning("get_morale_aura_magnitude: DB error", exc_info=True)
        return 0
    if not aura:
        return 0
    try:
        if float(aura.get("expires_at", 0.0)) <= now:
            return 0
        return int(aura.get("magnitude", 0))
    except (TypeError, ValueError):
        return 0


async def perform_morale_aware_check(
    char: dict,
    skill_name: str,
    difficulty: int,
    *,
    db,
    room_id: int | None = None,
    skill_registry=None,
) -> SkillCheckResult:
    """Skill check variant that consults the room morale aura.

    For morale-flavored skills (§2.3), the active aura magnitude is
    subtracted from the difficulty before the underlying
    `perform_skill_check` is called. Difficulty has a floor of 1
    (a 0-or-negative difficulty would auto-succeed even on a fumble,
    which is undesirable — even a heroic perform doesn't make
    Willpower trivial).

    For non-morale-flavored skills, this delegates to
    `perform_skill_check` unchanged (the aura is ignored).

    `room_id` defaults to `char["room_id"]` if not supplied. If
    neither is available, the aura is treated as 0.
    """
    if not is_morale_flavored(skill_name):
        return perform_skill_check(char, skill_name, difficulty,
                                    skill_registry=skill_registry)

    effective_room = room_id
    if effective_room is None:
        effective_room = char.get("room_id")
    if effective_room is None or db is None:
        return perform_skill_check(char, skill_name, difficulty,
                                    skill_registry=skill_registry)

    magnitude = await get_morale_aura_magnitude(db, effective_room)
    adjusted = max(1, difficulty - magnitude)
    return perform_skill_check(char, skill_name, adjusted,
                                skill_registry=skill_registry)


# ── Skill pool extraction ────────────────────────────────────────────────────

def _get_skill_pool(char: dict, skill_name: str, skill_registry) -> tuple[int, int]:
    """
    Extract (dice, pips) for a character's effective skill pool.
    Falls back to raw attribute if skill not trained.
    """
    import json as _json
    from engine.character import canonical_skill_key
    # 2026-06-11: canonical key — direct callers of this helper (the
    # haggle path, tests) may bypass perform_skill_check's ingress.
    key = canonical_skill_key(skill_name)

    # Look up attribute for this skill
    attr_name = _skill_to_attr(key, skill_registry)

    # Parse attributes JSON
    try:
        attrs = _json.loads(char.get("attributes", "{}"))
    except Exception:
        attrs = {}

    attr_pool = DicePool.parse(attrs.get(attr_name, "2D"))
    attr_dice, attr_pips = attr_pool.dice, attr_pool.pips

    # Parse skills JSON for bonus
    try:
        skills = _json.loads(char.get("skills", "{}"))
    except Exception:
        skills = {}

    bonus_str = skills.get(key)
    if not bonus_str:
        # 2026-06-11: tolerate non-canonical STORED keys — NPC yaml
        # skill blocks are predominantly underscore-form ("first_aid:
        # 4D"), PC chargen writes space-form. Scan is O(n) over a
        # small dict and only on the primary-key miss path.
        for k, v in skills.items():
            if canonical_skill_key(k) == key:
                bonus_str = v
                break
    if not bonus_str:
        # Untrained: roll raw attribute
        return attr_dice, attr_pips

    bonus_pool = DicePool.parse(bonus_str)
    total_pips = (attr_dice * 3 + attr_pips) + (bonus_pool.dice * 3 + bonus_pool.pips)
    return total_pips // 3, total_pips % 3


def _skill_to_attr(skill_name: str, skill_registry) -> str:
    """Get the governing attribute for a skill."""
    from engine.character import canonical_skill_key
    # 2026-06-11: canonical key — registry keys and the fallback map
    # below are space-form; underscore data-form callers previously
    # missed BOTH and landed on the "perception" default.
    skill_name = canonical_skill_key(skill_name)
    if skill_registry:
        try:
            skill_def = skill_registry.get(skill_name)
            if skill_def:
                return skill_def.attribute.lower()
        except Exception:
            log.warning("_skill_to_attr: unhandled exception", exc_info=True)

    # Hardcoded fallback for common skills
    _FALLBACK = {
        "blaster": "dexterity", "dodge": "dexterity", "melee combat": "dexterity",
        "brawling": "dexterity", "grenade": "dexterity", "melee parry": "dexterity",
        "con": "perception", "persuasion": "perception", "bargain": "perception",
        "search": "perception", "sneak": "dexterity", "hide": "dexterity",
        "streetwise": "knowledge", "survival": "knowledge", "languages": "knowledge",
        "first aid": "technical", "medicine": "technical",
        "computer programming/repair": "technical", "security": "technical",
        "blaster repair": "technical", "space transports repair": "technical",
        "space transports": "mechanical", "starship piloting": "mechanical",
        "astrogation": "mechanical", "repulsorlift operation": "mechanical",
        "stamina": "strength", "lifting": "strength", "brawling parry": "dexterity",
        "intimidation": "perception", "command": "perception",
        "willpower": "knowledge", "scholar": "knowledge",
        "starfighter repair": "technical", "capital ship repair": "technical",
        "starship weapon repair": "technical",
        "musical instrument": "perception",
        # 2026-06-11: sanctioned non-registry craft skill — the T5
        # master-lightsaber schematic's skill_required. Not in
        # data/skills.yaml (nothing trains it); rolls raw Technical.
        # Exempted by name in tests/test_skill_key_resolution.py's
        # whole-catalog pin.
        "craft lightsaber": "technical",
    }
    return _FALLBACK.get(skill_name, "perception")


# ── Mission completion skill check ────────────────────────────────────────────

# Maps mission type -> (skill_name, partial_pay_fraction)
# partial_pay: fraction of reward on a partial success (a NEAR-miss, margin >= -2).
# Audit v2 §2.1: dropped from 0.50-0.75 to 0.40 and the partial window tightened
# from -4 to -2 — over-reaching by two tiers no longer out-earns staying in lane.
# 'delivery' stays full-pay: it is the deliberately-easy low-reward tier, not an
# over-reach exploit.
MISSION_SKILL_MAP = {
    "combat":        ("blaster",                    0.40),
    "smuggling":     ("con",                        0.40),
    "investigation": ("search",                     0.40),
    "social":        ("persuasion",                 0.40),
    "technical":     ("space transports repair",    0.40),
    "medical":       ("first aid",                  0.40),
    "slicing":       ("computer programming/repair",0.40),
    "salvage":       ("search",                     0.40),
    "bounty":        ("streetwise",                 0.40),
    "delivery":      ("stamina",                    1.00),  # easy, always full pay
}

# Difficulty scaling: reward band -> difficulty
# These are game-tuning intermediate values, not the R&E canonical ladder.
def mission_difficulty(reward: int) -> int:
    """Scale difficulty by reward amount."""
    if reward < 300:
        return 8    # Easy-
    if reward < 600:
        return 11   # Moderate-
    if reward < 1200:
        return 14   # Moderate+
    if reward < 2500:
        return 16   # Difficult-
    if reward < 5000:
        return 19   # Very Difficult-
    return 21       # Very Difficult


def resolve_mission_completion(
    char: dict,
    mission_type: str,
    reward: int,
    skill_registry=None,
) -> dict:
    """
    Resolve a mission completion skill check.

    Returns:
        {
          "success": bool,
          "partial": bool,      # True if partial pay on near-miss
          "credits_earned": int,
          "roll": int,
          "difficulty": int,
          "skill": str,
          "pool": str,
          "fumble": bool,
          "message": str,       # narrative result line
        }
    """
    skill_name, partial_frac = MISSION_SKILL_MAP.get(
        mission_type.lower(), ("perception", 0.75)
    )
    difficulty = mission_difficulty(reward)

    result = perform_skill_check(char, skill_name, difficulty, skill_registry)

    if result.success:
        credits = reward
        if result.critical_success:
            # Exceptional success: +20% bonus
            credits = int(reward * 1.20)
            msg = (
                f"  Exceptional work. The client is impressed. "
                f"Bonus pay included."
            )
        else:
            msg = f"  Job well done. Payment received."
    elif result.margin >= -2:
        # Partial success: some pay, but not full (near-miss only, audit v2 §2.1)
        credits = int(reward * partial_frac)
        msg = (
            f"  Close, but not quite. "
            f"Partial payment for the effort."
        )
    else:
        credits = 0
        if result.fumble:
            msg = (
                f"  Things went wrong. The client is not pleased. "
                f"No payment."
            )
        else:
            msg = (
                f"  The job fell through. "
                f"No payment this time."
            )

    return {
        "success": result.success,
        "partial": (not result.success and result.margin >= -2),
        "credits_earned": credits,
        "roll": result.roll,
        "difficulty": difficulty,
        "skill": skill_name,
        "pool": result.pool_str,
        "fumble": result.fumble,
        "critical": result.critical_success,
        "message": msg,
    }


# ── Bargain / Haggle check ───────────────────────────────────────────────────
#
# WEG D6 R&E Bargain Table (Galaxy Guide 6, p77):
# Player and NPC each roll Bargain.  The difference in rolls maps to a
# price modifier.  Simplified for MUSH: each 4 points of margin = ±2%,
# capped at ±10%.  A critical doubles the modifier.  A fumble inverts it.
#
# v22: NPC now rolls through roll_d6_pool (gets Wild Die per audit #3).
#
# Usage:
#   from engine.skill_checks import resolve_bargain_check
#   result = resolve_bargain_check(char, npc_bargain_dice=3, npc_bargain_pips=0,
#                                  base_price=500)
#   final_price = result["adjusted_price"]
# ─────────────────────────────────────────────────────────────────────────────

def resolve_bargain_check(
    char: dict,
    base_price: int,
    npc_bargain_dice: int = 3,
    npc_bargain_pips: int = 0,
    is_buying: bool = True,
    skill_registry=None,
) -> dict:
    """
    Resolve a Bargain opposed roll for buy/sell transactions.

    The player rolls Bargain (or raw Perception if untrained).
    The NPC rolls a Bargain pool (now with Wild Die per audit #3).
    Margin maps to price shift: ±2% per 4 points, capped ±10%.
    Critical success: modifier is doubled (up to ±10% cap).
    Fumble: modifier is inverted (player gets worse deal).

    Args:
        char: Player character dict.
        base_price: The base sticker price before haggling.
        npc_bargain_dice: NPC's Bargain skill dice.
        npc_bargain_pips: NPC's Bargain skill pips.
        is_buying: True if player is buying (lower = better for player).
                   False if player is selling (higher = better for player).
        skill_registry: Optional SkillRegistry.

    Returns:
        {
          "adjusted_price": int,
          "price_modifier_pct": int,   # e.g. -4 means 4% cheaper
          "player_roll": int,
          "npc_roll": int,
          "player_pool": str,
          "npc_pool": str,
          "margin": int,               # player_roll - npc_roll
          "critical": bool,
          "fumble": bool,
          "message": str,              # narrative line
        }
    """
    # Player roll — through the canonical dice engine
    if skill_registry is None:
        skill_registry = _get_default_registry()

    player_dice, player_pips = _get_skill_pool(char, "bargain", skill_registry)
    player_pool = DicePool(player_dice, player_pips)
    player_pool_str = str(player_pool)

    player_roll = roll_d6_pool(player_pool)
    player_total = player_roll.total
    player_crit = player_roll.exploded and not player_roll.complication
    player_fumble = player_roll.complication

    # NPC roll — also through roll_d6_pool now (audit fix #3: NPCs get Wild Die)
    npc_pool = DicePool(max(1, npc_bargain_dice), npc_bargain_pips)
    npc_pool_str = str(npc_pool)
    npc_roll = roll_d6_pool(npc_pool)
    npc_total = npc_roll.total

    # Margin: positive = player wins the haggle
    margin = player_total - npc_total

    # Map margin to price modifier: ±2% per 4 points, capped ±10%
    raw_pct = (margin // 4) * 2  # e.g. margin 8 → +4%, margin -4 → -2%
    raw_pct = max(-10, min(10, raw_pct))

    # Critical doubles the modifier (still capped)
    if player_crit and margin > 0:
        raw_pct = max(-10, min(10, raw_pct * 2))

    # Fumble inverts the modifier (player gets worse deal)
    if player_fumble:
        raw_pct = -abs(raw_pct) if raw_pct >= 0 else abs(raw_pct)
        # Fumble always hurts: minimum -2% swing against player
        if is_buying and raw_pct <= 0:
            raw_pct = 2
        elif not is_buying and raw_pct >= 0:
            raw_pct = -2

    # Apply modifier: for buying, negative % = cheaper (good for player)
    # For selling, positive % = higher sell price (good for player)
    if is_buying:
        modifier = -raw_pct
    else:
        modifier = raw_pct

    adjusted = max(1, int(base_price * (1 + modifier / 100)))

    # Build narrative
    if modifier < 0:
        if is_buying:
            msg = f"  The vendor holds firm. You pay a bit extra."
        else:
            msg = f"  The vendor low-balls you. Not your best deal."
    elif modifier > 0:
        if is_buying:
            msg = f"  You haggle the price down. Nice deal."
        else:
            msg = f"  You talk the vendor up. Good negotiating."
    else:
        msg = f"  Standard price. No advantage either way."

    if player_crit and margin > 0:
        msg = f"  Masterful negotiation! The vendor is impressed."
    if player_fumble:
        msg = f"  Your haggling backfires. The vendor smirks."

    return {
        "adjusted_price": adjusted,
        "price_modifier_pct": modifier,
        "player_roll": player_total,
        "npc_roll": npc_total,
        "player_pool": player_pool_str,
        "npc_pool": npc_pool_str,
        "margin": margin,
        "critical": player_crit,
        "fumble": player_fumble,
        "message": msg,
    }


# ── Ship repair skill check ──────────────────────────────────────────────────

def resolve_repair_check(
    char: dict,
    skill_name: str,
    difficulty: int,
    is_hull: bool = False,
    skill_registry=None,
) -> dict:
    """
    Resolve a ship repair skill check via perform_skill_check.

    Args:
        char: Player character dict.
        skill_name: e.g. "space transports repair", "starfighter repair"
        difficulty: Target number (from REPAIR_DIFFICULTIES + combat penalty).
        is_hull: If True, success restores hull points scaled by margin.
        skill_registry: Optional SkillRegistry.

    Returns:
        {
          "success": bool,
          "partial": bool,          # margin >= -4, system stabilised but not fixed
          "catastrophic": bool,     # fumble or margin <= -9, system destroyed
          "hull_repaired": int,     # 0 for non-hull, 1 normal, 2 on crit
          "roll": int,
          "difficulty": int,
          "margin": int,
          "skill": str,
          "pool": str,
          "critical": bool,
          "fumble": bool,
          "message": str,
        }
    """
    result = perform_skill_check(char, skill_name, difficulty, skill_registry)

    hull_repaired = 0
    catastrophic = False
    partial = False

    if result.success:
        if is_hull:
            hull_repaired = 2 if result.critical_success else 1
            if result.critical_success:
                msg = (
                    f"  Outstanding work! Two hull breaches patched. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
            else:
                msg = (
                    f"  Repair successful. Hull breach sealed. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
        else:
            if result.critical_success:
                msg = (
                    f"  Expert repair! System restored and running clean. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
            else:
                msg = (
                    f"  Repair successful. System back online. "
                    f"({result.pool_str}: {result.roll} vs {difficulty})"
                )
    elif result.fumble or result.margin <= -9:
        catastrophic = True
        msg = (
            f"  Catastrophic failure! Components fused together — "
            f"needs a spacedock. "
            f"({result.pool_str}: {result.roll} vs {difficulty}, "
            f"margin: {result.margin})"
        )
    elif result.margin >= -4:
        partial = True
        msg = (
            f"  Almost had it — system stabilised but still offline. "
            f"({result.pool_str}: {result.roll} vs {difficulty})"
        )
    else:
        msg = (
            f"  Repair failed. System remains offline. "
            f"({result.pool_str}: {result.roll} vs {difficulty})"
        )

    return {
        "success": result.success,
        "partial": partial,
        "catastrophic": catastrophic,
        "hull_repaired": hull_repaired,
        "roll": result.roll,
        "difficulty": difficulty,
        "margin": result.margin,
        "skill": skill_name,
        "pool": result.pool_str,
        "critical": result.critical_success,
        "fumble": result.fumble,
        "message": msg,
    }


# ── Coordinate (Command skill) check ────────────────────────────────────────

def resolve_coordinate_check(
    char: dict,
    difficulty: int = 12,
    skill_registry=None,
) -> dict:
    """
    Resolve a Command skill check for crew coordination.

    Returns:
        {
          "success": bool,
          "critical": bool,     # crit = +2 bonus to crew instead of +1
          "fumble": bool,       # fumble = -1 penalty to crew
          "roll": int,
          "difficulty": int,
          "pool": str,
          "message": str,
        }
    """
    result = perform_skill_check(char, "command", difficulty, skill_registry)

    if result.success:
        if result.critical_success:
            msg = (
                f"Brilliant coordination! The crew acts as one. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"+2 to all crew rolls this round."
            )
        else:
            msg = (
                f"The crew rallies! "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"+1 to all crew rolls this round."
            )
    else:
        if result.fumble:
            msg = (
                f"Confusing orders! The crew hesitates. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty}) "
                f"-1 to crew rolls this round."
            )
        else:
            msg = (
                f"The coordination attempt falls flat. "
                f"(Command {result.pool_str}: {result.roll} vs {difficulty})"
            )

    return {
        "success": result.success,
        "critical": result.critical_success,
        "fumble": result.fumble,
        "roll": result.roll,
        "difficulty": difficulty,
        "pool": result.pool_str,
        "message": msg,
    }
