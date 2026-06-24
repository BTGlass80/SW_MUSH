# -*- coding: utf-8 -*-
"""
Character model for the D6 system.

Ties together attributes, skills, species, wounds, and Force sensitivity
into a unified Character object. Handles skill resolution (finding the
effective dice pool for any skill check) and serialization to/from the DB.
"""
import json
import logging
import os
import time
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Optional

import yaml

from engine.dice import DicePool

log = logging.getLogger(__name__)

# ── Constants ──

ATTRIBUTE_NAMES = (
    "dexterity", "knowledge", "mechanical",
    "perception", "strength", "technical",
)


# ── Wound System ──

class WoundLevel(IntEnum):
    """D6 wound levels in ascending severity."""
    HEALTHY = 0
    STUNNED = 1
    WOUNDED = 2
    WOUNDED_TWICE = 3
    INCAPACITATED = 4
    MORTALLY_WOUNDED = 5
    DEAD = 6

    @property
    def penalty_dice(self) -> int:
        """Dice penalty from this wound level (excludes stun — tracked separately)."""
        return {
            0: 0, 1: 0, 2: 1, 3: 2, 4: 0, 5: 0, 6: 0
        }.get(self.value, 0)
        # STUNNED penalty now comes from len(stun_timers) on Character
        # Incap/mortal/dead can't act so penalty is moot

    @property
    def can_act(self) -> bool:
        return self.value <= WoundLevel.WOUNDED_TWICE

    @property
    def display_name(self) -> str:
        return self.name.replace("_", " ").title()

    @classmethod
    def from_damage_margin(cls, margin: int) -> "WoundLevel":
        """Determine wound level from damage-vs-resistance margin."""
        if margin <= 0:
            return cls.HEALTHY
        elif margin <= 3:
            return cls.STUNNED
        elif margin <= 8:
            return cls.WOUNDED
        elif margin <= 12:
            return cls.INCAPACITATED
        elif margin <= 15:
            return cls.MORTALLY_WOUNDED
        else:
            return cls.DEAD


# ── Skill Registry ──

# ── Skill-key canonicalization (2026-06-11) ──────────────────────────
# The repo carries two live key dialects for the SAME skills:
#   • space-form      — SkillRegistry keys ("blaster repair"), chargen
#     templates, train/CP writes, MISSION_SKILL_MAP, combat literals.
#   • underscore-form — data/schematics.yaml skill_required values and
#     most NPC yaml skill blocks (46× melee_combat, 43× first_aid, …).
# Until 2026-06-11 nothing translated between dialects, so every lookup
# that crossed them silently resolved as UNTRAINED — and in
# skill_checks._skill_to_attr, to the wrong governing attribute
# (default "perception"). Net effect: crafter training never counted
# for any underscore skill_required (trained Blaster Repair 3D PCs
# rolled raw 2D Perception to craft), technical-mission rolls ignored
# Space Transport Repair training (plural/singular drift), and every
# melee_combat-keyed NPC attacked and parried at raw attribute.
# canonical_skill_key() is the single translation point; both
# resolution surfaces (Character.get_skill_pool and
# skill_checks._get_skill_pool / _skill_to_attr) route through it.
_SKILL_KEY_ALIASES = {
    # data-form (lowered, post-separator-normalization) → the
    # registry-canonical name from data/skills.yaml. Keep this map
    # SMALL and sanctioned: tests/test_skill_key_resolution.py pins
    # that every schematics.yaml skill_required resolves through here
    # to a registered skill, so new data-side spellings fail loudly at
    # data-entry time instead of silently rolling untrained.
    "computer prog": "computer programming/repair",
    "computer programming": "computer programming/repair",
    "space transports repair": "space transport repair",
    "pickpocket": "pick pocket",
}


def canonical_skill_key(name: str) -> str:
    """Normalize a skill name to its registry-canonical lookup key.

    Lowercase, strip, underscores→spaces, then the sanctioned
    ``_SKILL_KEY_ALIASES`` map. Idempotent. ``canonical_skill_key("")``
    is ``""`` (never raises on None/empty).
    """
    key = (name or "").strip().lower().replace("_", " ")
    return _SKILL_KEY_ALIASES.get(key, key)


@dataclass
class SkillDef:
    """Definition of a skill from the YAML."""
    name: str
    attribute: str  # parent attribute name
    specializations: list[str] = field(default_factory=list)

    @property
    def key(self) -> str:
        """Lowercase lookup key."""
        return self.name.lower()


class SkillRegistry:
    """Loads skill definitions and provides lookup."""

    def __init__(self):
        self._skills: dict[str, SkillDef] = {}       # key -> SkillDef
        self._by_attribute: dict[str, list[str]] = {} # attr -> [skill keys]

    def load_file(self, path: str):
        """Load skills from a YAML file."""
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        count = 0
        for attr_name, skill_list in data.items():
            attr_name = attr_name.lower()
            self._by_attribute[attr_name] = []
            for entry in skill_list:
                sd = SkillDef(
                    name=entry["name"],
                    attribute=attr_name,
                    specializations=entry.get("specializations", []),
                )
                self._skills[sd.key] = sd
                self._by_attribute[attr_name].append(sd.key)
                count += 1

        log.info("Loaded %d skill definitions from %s", count, path)

    def get(self, name: str) -> Optional[SkillDef]:
        # 2026-06-11: canonicalize so underscore-form data keys
        # ("blaster_repair") and sanctioned aliases ("computer prog")
        # resolve to the registered SkillDef instead of None.
        return self._skills.get(canonical_skill_key(name))

    def get_attribute_for(self, skill_name: str) -> Optional[str]:
        sd = self.get(skill_name)
        return sd.attribute if sd else None

    def skills_for_attribute(self, attr: str) -> list[SkillDef]:
        keys = self._by_attribute.get(attr.lower(), [])
        return [self._skills[k] for k in keys]

    def all_skills(self) -> list[SkillDef]:
        return list(self._skills.values())

    @property
    def count(self) -> int:
        return len(self._skills)


# ── Cached default registry ───────────────────────────────────────────
#
# Many parser sites previously did:
#     sr = SkillRegistry()
#     sr.load_file("data/skills.yaml")
# inside a command handler. That re-parses the YAML synchronously on the
# asyncio event loop every time the command runs — contributing to
# "tick loop fell behind" warnings. Use get_cached_skill_registry() for
# read-only lookups; the registry is loaded once on first use.

_CACHED_SKILL_REG: Optional["SkillRegistry"] = None


def get_cached_skill_registry(
    yaml_path: Optional[str] = None,
) -> "SkillRegistry":
    """Return a process-wide cached SkillRegistry, loading on first use.

    The cache is loaded synchronously the first time it's requested.
    Subsequent calls return the same instance with no I/O. Pass a custom
    yaml_path to force-reload (used by tests); a custom path always
    rebuilds the cache.

    The returned registry should be treated as read-only by callers.
    Mutating it would affect every other caller in the process.
    """
    global _CACHED_SKILL_REG
    if _CACHED_SKILL_REG is not None and yaml_path is None:
        return _CACHED_SKILL_REG

    reg = SkillRegistry()
    if yaml_path is None:
        # Default: data/skills.yaml relative to the project root.
        _here = os.path.dirname(os.path.abspath(__file__))
        _root = os.path.dirname(_here)
        yaml_path = os.path.join(_root, "data", "skills.yaml")
    reg.load_file(yaml_path)
    _CACHED_SKILL_REG = reg
    return reg


def reset_cached_skill_registry() -> None:
    """Drop the cached registry. Tests use this to force a reload."""
    global _CACHED_SKILL_REG
    _CACHED_SKILL_REG = None


# ── Character ──

@dataclass
class Character:
    """
    A player or NPC character with full D6 stats.

    Attributes are stored as DicePool objects.
    Skills are stored as bonus dice ABOVE the parent attribute.
    The effective skill pool = attribute + skill bonus.
    """
    id: int = 0
    account_id: int = 0
    name: str = ""
    species_name: str = "Human"
    template: str = ""

    # Core attributes
    dexterity: DicePool = field(default_factory=lambda: DicePool(3, 0))
    knowledge: DicePool = field(default_factory=lambda: DicePool(3, 0))
    mechanical: DicePool = field(default_factory=lambda: DicePool(3, 0))
    perception: DicePool = field(default_factory=lambda: DicePool(3, 0))
    strength: DicePool = field(default_factory=lambda: DicePool(3, 0))
    technical: DicePool = field(default_factory=lambda: DicePool(3, 0))

    # Skills: {skill_name_lower: DicePool bonus above attribute}
    skills: dict[str, DicePool] = field(default_factory=dict)

    # Specializations: {spec_key: DicePool bonus above skill}
    specializations: dict[str, DicePool] = field(default_factory=dict)

    # Status
    wound_level: WoundLevel = WoundLevel.HEALTHY
    # v22 audit #13/#21: per-stun expiry timers.
    # Each entry is the number of rounds remaining for that stun.
    # The stun penalty = -len(active_stuns)D.
    # Stun knockout threshold: len(active_stuns) >= STR dice → unconscious.
    stun_timers: list = field(default_factory=list)  # list[int] — rounds remaining per stun
    mortally_wounded_rounds: int = 0  # Rounds spent mortally wounded (for death roll)
    # ── PG.1.death wound_state (Drop 2c, May 19 2026 evening) ──
    # Post-respawn debuff per progression_gates_and_consequences §3.3.
    # Distinct from wound_level (the WEG R&E in-combat ladder).
    #   wound_state: 'healthy' | 'wounded'  (DB column wound_state)
    #   wound_clear_at: unix-epoch seconds; 0 means no active clock.
    # Contributes +1 to total_penalty_dice when 'wounded' so every
    # existing dice-pool call site picks up the −1D automatically.
    wound_state: str = "healthy"
    wound_clear_at: float = 0.0
    # ── Drop D Phase 3: STRICT R&E stun-KO (May 28 2026) ──
    # Wall-clock unconscious gate from R&E p83 stun ruling:
    # "Weapons set for stun roll damage normally, but treat any result
    #  more serious than 'stunned' as 'unconscious for 2D minutes.'"
    # The 2D roll happens when the KO triggers in combat.py; this field
    # holds the unix-epoch-seconds deadline. 0.0 means no active KO.
    # Process-state only — NOT persisted to DB. A server restart wakes
    # everyone up, which is the R&E-friendlier outcome vs. leaving
    # players KO'd through a deploy.
    #
    # Unit decision: SECONDS (float), matching wound_clear_at and the
    # rest of the codebase's wall-clock convention. The original
    # design memo named the field `unconscious_until_ms` (ms-suffixed)
    # but the in-codebase convention is seconds; using ms here would
    # be inconsistent with every other timer. See handoff §1.3.
    unconscious_until: float = 0.0
    character_points: int = 5
    force_points: int = 1
    dark_side_points: int = 0
    credits: int = 1000        # Starting credits
    force_sensitive: bool = False

    # Force attributes (0D if not force-sensitive)
    control: DicePool = field(default_factory=lambda: DicePool(0, 0))
    sense: DicePool = field(default_factory=lambda: DicePool(0, 0))
    alter: DicePool = field(default_factory=lambda: DicePool(0, 0))

    # Location & inventory
    room_id: int = 1
    description: str = ""
    equipped_weapon: str = ""  # weapon key from weapons.yaml (e.g. "blaster_pistol")
    worn_armor: str = ""       # v22: armor key from weapons.yaml (e.g. "blast_vest")
    # Crafted-armor soak quality, folded into the combat soak roll
    # (CRAFT.armor_soak_quality). The Character holds only the bare worn_armor
    # KEY (the instance quality is discarded by from_db_dict), so the soak-pip
    # is computed ONCE at load — where the equipment JSON is still in hand —
    # and cached here as a primitive, mirroring the Drop-19 weapon-pip isolation
    # (combat never re-reads equipment). 0 = vendor baseline / no crafted armor.
    armor_soak_pips: int = 0
    # Load-time snapshot of the per-slot equipment ItemInstances
    # (TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES Stage 1). from_db_dict
    # already calls read_equipment to derive the bare keys; we keep the parsed
    # instances here too, so a consumer that needs condition/quality/crafter/mods
    # can read them off the Character WITHOUT re-parsing the equipment JSON. The
    # bare-key fields above stay canonical for registry lookups (the 56 key-only
    # consumers are untouched). Exposed via the equipped_weapon_inst /
    # worn_armor_inst properties below. NOT live — like armor_soak_pips this is a
    # one-shot-at-load snapshot; equip/wear/craft mutate char['equipment'] on the
    # session dict, so MUTATION sites must read_equipment(char['equipment'])
    # directly, never trust this cache for post-load mods.
    _equipment_slots: dict = field(
        default_factory=lambda: {"weapon": None, "armor": None})
    # Lane A Phase B: a creature's faithful natural attack (skill + concrete
    # dice), set from the char_sheet's `natural_attack` marker. Empty for
    # ordinary characters. Honored first by npc_combat_ai._get_npc_weapon so
    # creatures fight with their source damage instead of bare-STR brawling.
    natural_attack_skill: str = ""
    natural_attack_damage: str = ""

    # Lane A tail (2026-06-06): a creature's WEG special-attack riders, parsed
    # from the char_sheet's `special_attack` block at spawn. Empty dicts for
    # ordinary characters. Read by combat._resolve_melee_attack on a landed
    # natural-attack hit to inject the matching in-combat condition (poison
    # DoT / grapple-constriction restraint). NOT persisted — creature-template
    # state, set fresh each spawn (mirrors natural_attack_*).
    special_attack_poison: dict = field(default_factory=dict)
    special_attack_restraint: dict = field(default_factory=dict)

    # Movement
    move: int = 10

    # Player-supplied chargen rationale ("why I built this character
    # this way"). Captured during creation, surfaces in the GUI sheet
    # right-rail, editable via +chargen_notes <text>. Distinct from
    # description (in-character look-at) and pc_narrative.background
    # (in-character biography).
    chargen_notes: str = ""

    @property
    def active_stun_count(self) -> int:
        """Number of currently active stuns (each gives -1D)."""
        return len(self.stun_timers)

    @property
    def total_penalty_dice(self) -> int:
        """Total dice penalty from wounds + active stuns + PG.1.death
        respawn-Wounded debuff.

        Drop 2c (May 19 2026 evening): wound_state='wounded' adds +1
        to the penalty (i.e. −1D to all rolls). The penalty lifts when
        the wound_state recovery clock expires (engine.death.
        tick_wound_recovery) or a med-droid clears it (PG.1.death.b).
        """
        respawn_debuff = 1 if self.wound_state == "wounded" else 0
        return (self.wound_level.penalty_dice + self.active_stun_count
                + respawn_debuff)

    # ── Drop D Phase 3: STRICT R&E stun-KO gate ───────────────────────
    def is_stun_unconscious(self, now: Optional[float] = None) -> bool:
        """True while a stun-KO wall-clock is active (R&E p83).

        ``now`` defaults to ``time.time()``; tests pass a fixed value
        for determinism. The KO clears the moment ``now`` reaches
        ``unconscious_until`` (strict ``<``); a single-call equality
        check at the deadline reports awake, matching the existing
        ``wound_clear_at`` convention in engine.death.
        """
        if self.unconscious_until <= 0.0:
            return False
        if now is None:
            now = time.time()
        return now < self.unconscious_until

    def can_act_now(self, now: Optional[float] = None) -> bool:
        """True iff the character may declare/resolve combat actions
        this round. Combines the WEG wound ladder
        (``wound_level.can_act``) with the Drop-D-Phase-3 stun-KO
        gate (``is_stun_unconscious``).

        Call sites in combat.py that currently use
        ``char.wound_level.can_act`` should migrate to this so a
        stun-KO'd character cannot act even when their wound_level
        is only STUNNED (the KO branch leaves wound_level at STUNNED
        per R&E and uses ``unconscious_until`` as the independent
        gate)."""
        if not self.wound_level.can_act:
            return False
        if self.is_stun_unconscious(now):
            return False
        return True

    def clear_stun_unconscious(self) -> None:
        """Wake the character from a stun-KO. Idempotent — safe to call
        even when no KO is active. Used by the combat tick loop when
        the wall-clock deadline passes, and exposed for tests + admin
        revive commands."""
        self.unconscious_until = 0.0

    def get_attribute(self, name: str) -> DicePool:
        """Get an attribute pool by name."""
        name = name.lower()
        if name in ATTRIBUTE_NAMES:
            return getattr(self, name)
        if name in ("control", "sense", "alter"):
            return getattr(self, name)
        return DicePool(0, 0)

    def set_attribute(self, name: str, pool: DicePool):
        """Set an attribute pool by name."""
        name = name.lower()
        if name in ATTRIBUTE_NAMES or name in ("control", "sense", "alter"):
            setattr(self, name, pool)

    def get_skill_pool(self, skill_name: str, skill_registry: SkillRegistry) -> DicePool:
        """
        Get the effective dice pool for a skill check.

        If the character has dice in the skill, pool = attribute + skill bonus.
        If not, they roll the raw attribute (untrained use).
        """
        key = canonical_skill_key(skill_name)
        skill_def = skill_registry.get(key)
        if skill_def is None:
            return DicePool(0, 0)

        attr_pool = self.get_attribute(skill_def.attribute)
        bonus = self.skills.get(key)
        if not bonus:
            # 2026-06-11: tolerate non-canonical STORED keys. Most NPC
            # yaml skill blocks are underscore-form ("melee_combat:
            # 5D"), while combat queries space-form ("melee combat") —
            # before this scan every such NPC attacked and parried at
            # raw attribute. O(n) over a small dict, miss path only.
            for k, v in self.skills.items():
                if canonical_skill_key(k) == key:
                    bonus = v
                    break
        if bonus:
            return attr_pool + bonus
        return attr_pool

    def get_effective_pool(
        self, skill_name: str, skill_registry: SkillRegistry,
        num_actions: int = 1
    ) -> DicePool:
        """
        Get effective pool after applying wound and multi-action penalties.
        """
        from engine.dice import apply_multi_action_penalty, apply_wound_penalty
        pool = self.get_skill_pool(skill_name, skill_registry)
        pool = apply_wound_penalty(pool, self.wound_level.penalty_dice)
        pool = apply_multi_action_penalty(pool, num_actions)
        return pool

    def add_skill(self, skill_name: str, bonus: DicePool):
        """Set a skill bonus (dice above the parent attribute)."""
        self.skills[skill_name.lower()] = bonus

    def get_armor_protection(self, energy: bool = True) -> DicePool:
        """
        Get the worn armor's protection dice pool.

        v22: Armor adds to Strength for soak per R&E p83.
        Energy weapons (blasters) use protection_energy.
        Physical attacks (melee/brawling) use protection_physical.

        Returns DicePool(0,0) if no armor worn.
        """
        if not self.worn_armor:
            return DicePool(0, 0)
        try:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            armor = wr.get(self.worn_armor)
            if not armor or not armor.is_armor:
                return DicePool(0, 0)
            prot_str = armor.protection_energy if energy else armor.protection_physical
            if prot_str:
                return DicePool.parse(prot_str)
        except Exception as _e:
            log.debug("silent except in engine/character.py:278: %s", _e, exc_info=True)
        return DicePool(0, 0)

    def get_armor_dex_penalty(self) -> DicePool:
        """
        Get the worn armor's Dexterity penalty.

        Returns DicePool(0,0) if no armor or no penalty.
        """
        if not self.worn_armor:
            return DicePool(0, 0)
        try:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            armor = wr.get(self.worn_armor)
            if not armor or not armor.is_armor or not armor.dexterity_penalty:
                return DicePool(0, 0)
            # 2026-06-11 (Gundark Drop C): data stores penalties SIGNED
            # per the book ("-1D"), but DicePool is unsigned —
            # DicePool.parse("-1D") silently returned (0,0), so every
            # armor dex penalty has been a no-op since v22 (Bounty
            # Hunter Armor included). All three combat consumers
            # subtract the returned pool's magnitude
            # (apply_wound_penalty(pool, pen.dice)), so the producer
            # returns the MAGNITUDE here.
            pen_str = armor.dexterity_penalty.strip().lstrip("-")
            return DicePool.parse(pen_str)
        except Exception as _e:
            log.debug("silent except in engine/character.py:297: %s", _e, exc_info=True)
        return DicePool(0, 0)

    def has_skill_dice(self, skill_name: str) -> bool:
        """True if the character has any nonzero dice TRAINED in a skill.

        Tolerates both stored key dialects (space-form / underscore-form) via the
        canonical key, mirroring get_skill_pool's fallback scan, and treats a
        zero-valued entry (DicePool(0,0)) as UNTRAINED — DicePool has no __bool__,
        so a bare ``self.skills.get(key)`` truthiness test would wrongly count a
        0D entry as trained."""
        key = canonical_skill_key(skill_name)
        v = self.skills.get(key)
        if v is None:
            for k, vv in self.skills.items():
                if canonical_skill_key(k) == key:
                    v = vv
                    break
        # Defensive: char.skills should hold DicePools, but guard a non-DicePool
        # value (the from_db_dict skills loop now skips malformed entries, but a
        # synthetic Character could still carry junk) — treat it as untrained
        # rather than raise AttributeError on .is_zero().
        return isinstance(v, DicePool) and not v.is_zero()

    def get_powersuit_strength_bonus(self) -> DicePool:
        """The servo-assisted Strength bonus a worn POWERED suit grants, gated by
        Powersuit Operation proficiency and HARD-CAPPED at +1D (no power creep).

        CRAFT.powered_suit_design. Returns DicePool(0,0) unless the worn armor is
        a POWERED suit (powersuit_skill flag + a strength_bonus). A wearer with NO
        Powersuit Operation skill dice fights the servos — they get only HALF the
        (capped) bonus, rounded down (untrained-use penalty). v1 applies this to
        the combat SOAK roll only (powered armor = tankier); Strength-based melee
        is a future increment.
        """
        if not self.worn_armor:
            return DicePool(0, 0)
        try:
            from engine.weapons import get_weapon_registry
            wr = get_weapon_registry()
            armor = wr.get(self.worn_armor)
            # The powersuit_skill flag MARKS an armor row as a powered suit — only
            # flagged suits grant the servo bonus + carry the training penalty.
            if (not armor or not armor.is_armor or not armor.powersuit_skill
                    or not armor.strength_bonus):
                return DicePool(0, 0)
            bonus = DicePool.parse(armor.strength_bonus)
            # Hard cap at +1D (3 pips) so a powered suit is BETTER but not
            # game-warping vs the strongest unpowered armor's soak.
            bonus_pips = min(bonus.dice * 3 + bonus.pips, 3)
            # Untrained-use penalty: no trained Powersuit Operation dice → half.
            if not self.has_skill_dice("powersuit operation"):
                bonus_pips = bonus_pips // 2
            if bonus_pips <= 0:
                return DicePool(0, 0)
            return DicePool(bonus_pips // 3, bonus_pips % 3)
        except Exception as _e:
            log.debug("silent except in get_powersuit_strength_bonus: %s",
                      _e, exc_info=True)
        return DicePool(0, 0)

    @property
    def equipped_weapon_inst(self):
        """The equipped-weapon ItemInstance (condition/quality/crafter/mods), or
        None. Load-time snapshot — see the _equipment_slots field note. Bare-key
        registry lookups should still use self.equipped_weapon; this is for
        consumers that need the richer per-instance state without re-parsing the
        equipment JSON (TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES Stage 1)."""
        return self._equipment_slots.get("weapon")

    @property
    def worn_armor_inst(self):
        """The worn-armor ItemInstance (condition/quality/crafter/mods), or None.
        Load-time snapshot — see the _equipment_slots field note. Bare-key
        registry lookups should still use self.worn_armor."""
        return self._equipment_slots.get("armor")

    def advance_skill(self, skill_name: str, skill_registry: SkillRegistry) -> int:
        """
        Advance a skill by 1 pip. Returns CP cost.
        Cost = current total dice in the skill (attribute + bonus).
        """
        # 2026-06-11: store registry-canonical keys only — prevents the
        # split-key write ("blaster repair" from chargen + "blaster_repair"
        # from a train alias) now that SkillRegistry.get accepts both forms.
        key = canonical_skill_key(skill_name)
        skill_def = skill_registry.get(key)
        if not skill_def:
            return 0

        current_bonus = self.skills.get(key, DicePool(0, 0))
        attr_pool = self.get_attribute(skill_def.attribute)
        total_pool = attr_pool + current_bonus

        cost = total_pool.dice

        # Advance by 1 pip
        new_bonus = DicePool(current_bonus.dice, current_bonus.pips + 1)
        self.skills[key] = new_bonus

        return cost

    def apply_wound(self, margin: int) -> WoundLevel:
        """
        Apply damage from a combat hit per R&E 2nd Edition rules.

        R&E wound stacking:
          Stunned: -1D rest of round + next round. If stun_count equals
            STR dice, character is knocked unconscious 20 minutes.
          Wounded: fall prone, no actions rest of round. -1D until healed.
            Second wound -> Incapacitated.
          Incapacitated: unconscious 100 minutes. Another wound -> MW.
          Mortally Wounded: unconscious, dying. Each round roll 2D;
            if roll < rounds_MW, character dies. Another wound -> Dead.
          Dead: Dead.

        Returns the new wound level.
        """
        incoming = WoundLevel.from_damage_margin(margin)
        if incoming == WoundLevel.HEALTHY:
            return self.wound_level

        if incoming == WoundLevel.STUNNED:
            # v22 audit #13: each stun has its own 2-round timer
            self.stun_timers.append(2)  # Rest of current round + next round

            # Check stun knockout: active stuns >= STR dice = unconscious (R&E p83)
            str_dice = self.strength.dice
            if str_dice > 0 and len(self.stun_timers) >= str_dice:
                self.wound_level = max(self.wound_level, WoundLevel.INCAPACITATED)
                return self.wound_level

            if self.wound_level < WoundLevel.STUNNED:
                self.wound_level = WoundLevel.STUNNED
            return self.wound_level

        if incoming == WoundLevel.WOUNDED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                # Any further damage to mortally wounded = dead
                self.wound_level = WoundLevel.DEAD
            elif self.wound_level >= WoundLevel.INCAPACITATED:
                # Incap + wound -> mortally wounded (R&E p59)
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
            elif self.wound_level >= WoundLevel.WOUNDED:
                # Second wound -> incapacitated (R&E p59)
                self.wound_level = WoundLevel.INCAPACITATED
            else:
                self.wound_level = WoundLevel.WOUNDED
            return self.wound_level

        if incoming == WoundLevel.INCAPACITATED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                # MW + incap -> dead (R&E p59)
                self.wound_level = WoundLevel.DEAD
            elif self.wound_level >= WoundLevel.INCAPACITATED:
                # Incap + incap -> mortally wounded
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
            else:
                self.wound_level = WoundLevel.INCAPACITATED
            return self.wound_level

        if incoming == WoundLevel.MORTALLY_WOUNDED:
            if self.wound_level >= WoundLevel.MORTALLY_WOUNDED:
                self.wound_level = WoundLevel.DEAD
            else:
                self.wound_level = WoundLevel.MORTALLY_WOUNDED
                self.mortally_wounded_rounds = 0
            return self.wound_level

        if incoming == WoundLevel.DEAD:
            self.wound_level = WoundLevel.DEAD
            return self.wound_level

        # Fallback: take the worse level
        if incoming.value > self.wound_level.value:
            self.wound_level = incoming
        return self.wound_level

    # ── Serialization ──

    def to_db_dict(self) -> dict:
        """Serialize to a dict matching the DB schema."""
        attrs = {a: str(self.get_attribute(a)) for a in ATTRIBUTE_NAMES}
        if self.force_sensitive:
            attrs["control"] = str(self.control)
            attrs["sense"] = str(self.sense)
            attrs["alter"] = str(self.alter)

        skills = {k: str(v) for k, v in self.skills.items()}

        # HAZARD (TD.EQUIPMENT_CHARACTER_HOLDS_KEYS_NOT_INSTANCES): this writes
        # the equipment column as BARE KEYS, dropping the instance condition/
        # quality/crafter that _equipment_slots holds. to_db_dict is NOT an
        # equipment-persistence path — durable equipment writes go through
        # save_character(equipment=write_equipment(...)) at the verb layer, which
        # preserves the instance. Do not route an equipped-gear save through
        # to_db_dict or it silently downgrades the slot to vendor defaults.
        equipment = {}
        if self.equipped_weapon:
            equipment["weapon"] = self.equipped_weapon
        if self.worn_armor:
            equipment["armor"] = self.worn_armor

        return {
            "name": self.name,
            "species": self.species_name,
            "template": self.template,
            "attributes": json.dumps(attrs),
            "skills": json.dumps(skills),
            "wound_level": self.wound_level.value,
            "character_points": self.character_points,
            "force_points": self.force_points,
            "dark_side_points": self.dark_side_points,
            "credits": self.credits,
            "room_id": self.room_id,
            "description": self.description,
            "equipment": json.dumps(equipment),
            "chargen_notes": self.chargen_notes,
        }

    @classmethod
    def from_npc_sheet(cls, npc_id: int, sheet: dict) -> "Character":
        """
        Build a Character from an NPC char_sheet_json dict.

        The sheet format matches generate_npc() output:
          {
            "name": "...",
            "species": "Human",
            "attributes": {"dexterity": "3D+1", ...},
            "skills": {"blaster": "2D", ...},  # bonus above attribute
            "force_points": 1,
            "character_points": 5,
            "move": 10,
            "weapon": "blaster_pistol",  # optional weapon key
            "force_sensitive": false,
            "force_skills": {"control": "2D", ...},  # optional
            ...
          }
        """
        char = cls()
        char.id = npc_id
        char.account_id = 0  # NPCs have no account
        char.name = sheet.get("name", f"NPC #{npc_id}")
        char.species_name = sheet.get("species", "Human")
        char.template = sheet.get("template", "")
        char.character_points = sheet.get("character_points", 0)
        char.force_points = sheet.get("force_points", 0)
        char.dark_side_points = sheet.get("dark_side_points", 0)
        char.credits = sheet.get("credits", 0)
        char.move = sheet.get("move", 10)
        char.wound_level = WoundLevel(sheet.get("wound_level", 0))

        # Attributes
        attrs = sheet.get("attributes", {})
        for attr_name in ATTRIBUTE_NAMES:
            if attr_name in attrs:
                char.set_attribute(attr_name, DicePool.parse(attrs[attr_name]))

        # Skills (bonus above attribute)
        skills = sheet.get("skills", {})
        for skill_name, pool_str in skills.items():
            char.skills[skill_name.lower()] = DicePool.parse(str(pool_str))

        # Force
        char.force_sensitive = sheet.get("force_sensitive", False)
        force_skills = sheet.get("force_skills", {})
        for fa in ("control", "sense", "alter"):
            if fa in force_skills:
                char.set_attribute(fa, DicePool.parse(force_skills[fa]))
                char.force_sensitive = True
            elif fa in attrs:
                char.set_attribute(fa, DicePool.parse(attrs[fa]))
                char.force_sensitive = True

        # Weapon
        char.equipped_weapon = sheet.get("weapon", "")
        # Keep the instance snapshot consistent with the bare key (sheet NPCs are
        # vendor-grade, so a default ItemInstance is correct) so equipped_weapon_inst
        # doesn't return None for an armed NPC. worn_armor isn't set from the
        # sheet here, so the armor slot stays None.
        if char.equipped_weapon:
            from engine.items import ItemInstance
            char._equipment_slots = {
                "weapon": ItemInstance(key=char.equipped_weapon),
                "armor": None,
            }

        # Lane A Phase B: faithful creature natural attack (skill + dice).
        _na = sheet.get("natural_attack") or {}
        char.natural_attack_skill = str(_na.get("skill", "") or "")
        char.natural_attack_damage = str(_na.get("damage", "") or "")

        # Lane A tail: WEG special-attack riders (poison DoT / restraint).
        _sa = sheet.get("special_attack") or {}
        char.special_attack_poison = dict(_sa.get("poison") or {})
        char.special_attack_restraint = dict(_sa.get("restraint") or {})

        return char

    @classmethod
    def from_db_dict(cls, data: dict) -> "Character":
        """Deserialize from a DB row dict."""
        char = cls()
        char.id = data.get("id", 0)
        char.account_id = data.get("account_id", 0)
        char.name = data.get("name", "")
        char.species_name = data.get("species", "Human")
        char.template = data.get("template", "")
        char.room_id = data.get("room_id", 1)
        char.description = data.get("description", "")
        char.character_points = data.get("character_points", 5)
        char.force_points = data.get("force_points", 1)
        char.dark_side_points = data.get("dark_side_points", 0)
        char.credits = data.get("credits", 1000)
        char.wound_level = WoundLevel(data.get("wound_level", 0))
        # PG.1.death (Drop 2c): the new wound_state column rides
        # alongside wound_level. Defaults match the schema migration
        # ('healthy', 0.0) so pre-migration rows or partial dicts
        # work cleanly.
        char.wound_state = data.get("wound_state") or "healthy"
        try:
            char.wound_clear_at = float(data.get("wound_clear_at") or 0.0)
        except (TypeError, ValueError):
            char.wound_clear_at = 0.0
        # chargen_notes is optional — pre-migration rows return None.
        char.chargen_notes = data.get("chargen_notes", "") or ""

        # Parse attributes
        attrs = data.get("attributes", "{}")
        if isinstance(attrs, str):
            try:
                attrs = json.loads(attrs)
            except (json.JSONDecodeError, TypeError) as _e:
                log.warning("Malformed attributes JSON for char %s: %s",
                            data.get("id", "?"), _e)
                attrs = {}
        # BLOCKER 1 (T3.20 safe-load): guard each DicePool.parse so ONE
        # corrupted attribute value (e.g. "4X+2") skips that field with a
        # warning instead of raising and aborting the whole character load —
        # which would lock the player out entirely. Mirrors the skills-loop
        # guard below (the earlier char-load hardening guarded skills but left
        # this attributes loop unguarded).
        for attr_name in ATTRIBUTE_NAMES:
            if attr_name in attrs:
                try:
                    char.set_attribute(attr_name, DicePool.parse(attrs[attr_name]))
                except (ValueError, TypeError, AttributeError) as _e:
                    log.warning("Malformed attribute %r=%r for char %s: %s — skipped",
                                attr_name, attrs.get(attr_name), data.get("id", "?"), _e)
        for force_attr in ("control", "sense", "alter"):
            if force_attr in attrs:
                try:
                    pool = DicePool.parse(attrs[force_attr])
                    char.set_attribute(force_attr, pool)
                    char.force_sensitive = True  # key presence → force-sensitive (invariant)
                except (ValueError, TypeError, AttributeError) as _e:
                    log.warning("Malformed force attribute %r=%r for char %s: %s — skipped",
                                force_attr, attrs.get(force_attr), data.get("id", "?"), _e)

        # BLOCKER 2 / FORCE.sensitivity_failsafe_to_jedi (Brian Ruling 5,
        # T3.20 blocker-2): force_sensitive is DERIVED from control/sense/alter
        # in the attributes JSON. If that blob is unreadable/corrupt (attrs fell
        # back to {} above) or predates the derivation, a path-committed Jedi
        # would silently reconstruct as force_sensitive=False — losing their
        # Force on that login. The committed path is recorded in the
        # village_chosen_path TYPED COLUMN, which survives blob corruption, so
        # FAIL SAFE TO JEDI: a committed path with no recovered Force attrs loads
        # force_sensitive=True with a LOUD warning (the Force dice then need a
        # backfill) rather than a silent downgrade. force_sensitive stays derived
        # state — never written back (save_character's allowlist already blocks
        # persisting it), so this re-asserts safely on every load.
        if not char.force_sensitive:
            _chosen_path = str(data.get("village_chosen_path") or "").strip().lower()
            if _chosen_path in ("a", "b", "c"):
                char.force_sensitive = True
                log.warning(
                    "[force-failsafe] char %s is committed to Force path %r but "
                    "parsed attributes carry no control/sense/alter — failing SAFE "
                    "to force_sensitive=True (attributes JSON corrupt or "
                    "pre-derivation; Force attributes need a backfill).",
                    data.get("id", "?"), _chosen_path)

        # Parse skills
        skills = data.get("skills", "{}")
        if isinstance(skills, str):
            try:
                skills = json.loads(skills)
            except (json.JSONDecodeError, TypeError) as _e:
                log.warning("Malformed skills JSON for char %s: %s",
                            data.get("id", "?"), _e)
                skills = {}
        for skill_name, pool_str in skills.items():
            # Tolerate a malformed individual skill value (a non-D6 string like
            # "TRAINED", or a non-str like an int) the way the JSON-decode above
            # tolerates a bad blob — skip the bad entry with a warning rather than
            # let DicePool.parse's ValueError/AttributeError abort the whole
            # character load (which leaked raw Python error text to the player).
            try:
                char.skills[skill_name.lower()] = DicePool.parse(str(pool_str))
            except (ValueError, TypeError, AttributeError) as _e:
                log.warning("Malformed skill %r=%r for char %s: %s — skipped",
                            skill_name, pool_str, data.get("id", "?"), _e)

        # Parse equipment — tolerant of all historical on-disk shapes
        # (flat key, top-level single instance, per-slot instance) via
        # engine.items.equipment_keys. The Character object holds bare keys,
        # not instances (see read_equipment notes); instance condition/quality
        # lives in the DB JSON, read directly by the inventory surfaces.
        # read_equipment recovers the full per-slot ItemInstances; we keep only
        # the bare keys on the Character (the instance condition/quality lives in
        # the DB JSON, read directly by inventory surfaces) — EXCEPT the
        # crafted-armor soak quality, which we capture here as a primitive pip
        # (CRAFT.armor_soak_quality) because the equipment JSON is discarded
        # past this point and the combat soak site holds only the Character.
        from engine.items import read_equipment, crafted_armor_soak_pips
        _slots = read_equipment(data.get("equipment", "{}"))
        char.equipped_weapon = _slots["weapon"].key if _slots["weapon"] else ""
        char.worn_armor = _slots["armor"].key if _slots["armor"] else ""
        char.armor_soak_pips = crafted_armor_soak_pips(_slots["armor"])
        # Cache the parsed instances for equipped_weapon_inst / worn_armor_inst
        # (Stage 1 of the equipment-instance untangle) — see the field note.
        char._equipment_slots = _slots

        return char

    def format_sheet(self, skill_registry: SkillRegistry, width: int = 78) -> str:
        """Render a full character sheet for display."""
        lines = []
        sep = "=" * width
        lines.append(sep)
        lines.append(f"  {self.name}  |  {self.species_name}  |  {self.template or 'No Template'}")
        lines.append(sep)

        # Wound status
        if self.wound_level > WoundLevel.HEALTHY:
            lines.append(f"  Status: {self.wound_level.display_name} (-{self.wound_level.penalty_dice}D)")
        else:
            lines.append("  Status: Healthy")

        lines.append(f"  CP: {self.character_points}  |  FP: {self.force_points}  |  DSP: {self.dark_side_points}  |  Credits: {self.credits:,}")
        lines.append(f"  Move: {self.move}")
        lines.append("")

        # Attributes and skills
        for attr_name in ATTRIBUTE_NAMES:
            attr_pool = self.get_attribute(attr_name)
            lines.append(f"  {attr_name.upper():15s} {attr_pool}")

            # Skills under this attribute
            skill_defs = skill_registry.skills_for_attribute(attr_name)
            for sd in skill_defs:
                bonus = self.skills.get(sd.key)
                if bonus:
                    total = attr_pool + bonus
                    lines.append(f"    {sd.name:25s} {total}  (+{bonus})")
            lines.append("")

        # Force attributes
        if self.force_sensitive:
            lines.append("  FORCE ATTRIBUTES:")
            lines.append(f"    Control:  {self.control}")
            lines.append(f"    Sense:    {self.sense}")
            lines.append(f"    Alter:    {self.alter}")
            lines.append("")

        lines.append(sep)
        return "\n".join(lines)
