# Developer Internals — Guide_01_WEG_D6_Core_Mechanics.md

Extracted from `data/guides/Guide_01_WEG_D6_Core_Mechanics.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

### 🔧 Developer Internals

**File:** `engine/dice.py` — The `DicePool` dataclass (lines 20–92)

```python
@dataclass
class DicePool:
    dice: int = 0
    pips: int = 0

    def __post_init__(self):
        # Auto-normalize: 3 pips = 1 die
        if self.pips >= 3:
            self.dice += self.pips // 3
            self.pips = self.pips % 3
        # Handle negative pips by borrowing dice
        while self.pips < 0 and self.dice > 0:
            self.dice -= 1
            self.pips += 3
        self.dice = max(0, self.dice)
        self.pips = max(0, self.pips)
```

Key behaviors:
- `DicePool.parse("4D+2")` handles uppercase/lowercase, spaces, and negative pips (`"5D-1"`)
- Arithmetic is supported: `DicePool(3,1) + DicePool(1,0)` → `DicePool(4,1)`
- `total_pips()` converts to a flat integer for comparison (1D = 3 pips), used in advancement cost calculations
- `is_zero()` returns True when dice ≤ 0 and pips ≤ 0

**File:** `engine/character.py` — `ATTRIBUTE_NAMES` tuple (line 24) defines the canonical six attributes. The `Character` dataclass stores each as a `DicePool` field with default `3D`.

**File:** `data/species/*.yaml` — Each species YAML defines `min`/`max` ranges per attribute plus `attribute_dice` (total to distribute, always "18D") and `skill_dice` (bonus skill dice at creation, always "7D").

### 🔧 Developer Internals

**File:** `data/skills.yaml` — Canonical skill definitions. YAML structure is `attribute_name: [list of {name, specializations}]`. Loaded by `SkillRegistry.load_file()`.

**File:** `engine/character.py` — `SkillRegistry` class (lines 78–135):
- `_skills: dict[str, SkillDef]` — lowercase key → definition
- `_by_attribute: dict[str, list[str]]` — attribute → list of skill keys
- `get(name)` → `SkillDef` or `None`
- `get_attribute_for(skill_name)` → parent attribute string
- `skills_for_attribute(attr)` → list of `SkillDef` (used by sheet renderer)

**File:** `engine/character.py` — `Character.get_skill_pool()` (line 222):
- Looks up the skill bonus in `self.skills` dict
- Adds it to the parent attribute's `DicePool`
- Returns the effective pool for rolling
- If skill not trained, returns raw attribute pool (untrained use)

**File:** `engine/skill_checks.py` — `_get_skill_pool()` (lines 118–151):
- Used for out-of-combat checks where the character is a dict (DB row), not a `Character` object
- Parses `attributes` and `skills` JSON from the character dict
- Falls back to a hardcoded `_FALLBACK` mapping if the `SkillRegistry` can't resolve the attribute (line 165–183)
- Returns `(dice, pips)` tuple

**File:** `parser/d6_commands.py` — Player-facing roll commands:
- `RollCommand` (+roll): Tries parsing as `DicePool` first, falls back to skill name lookup with partial matching
- `CheckCommand` (+check): Accepts difficulty as a number or name ("moderate", "difficult", etc.)
- `OpposedCommand` (+opposed): Rolls player skill vs. a specified opposing dice pool
- All three broadcast abbreviated results to the room via `broadcast_to_room()`

**Skill Registry singleton pattern:** `skill_checks.py` uses a module-level `_default_registry` that lazily loads on first access (lines 40–53). This avoids re-loading the YAML on every skill check.

### 🔧 Developer Internals

**File:** `engine/dice.py` — `roll_wild_die()` (lines 218–244):

```python
def roll_wild_die() -> WildDieResult:
    result = WildDieResult()
    first = roll_die()
    result.rolls.append(first)

    if first == 1:
        result.complication = True
        result.total = 0      # Wild Die contributes nothing
        return result

    if first == 6:
        result.exploded = True
        total = 6
        while True:
            reroll = roll_die()
            result.rolls.append(reroll)
            if reroll == 6:
                total += 6     # Keep chaining
            else:
                total += reroll
                break          # Stop on non-6
        result.total = total
        return result

    result.total = first       # Normal: just the face value
    return result
```

**File:** `engine/dice.py` — `roll_d6_pool()` (lines 247–277):
- Rolls `pool.dice - 1` normal dice plus one Wild Die
- On complication: removes the highest normal die (`normal_dice[0]` since they're sorted descending)
- Floor of 1 on the total: `max(1, normal_total + wild.total + pool.pips)`
- A pool of 0D or fewer returns just the pips (minimum 0)

**`WildDieResult` dataclass** tracks: `rolls` (list of all Wild Die rolls for display), `total`, `exploded` (bool), `complication` (bool).

**`RollResult` dataclass** captures the complete roll: `pool`, `normal_dice`, `wild_die`, `pips`, `total`, `complication`, `exploded`, `removed_die`. The `display()` method formats it as `[4D+2] 3, 5, 2, W:6->4 (+2) = 22`.

**Verification note:** The Wild Die explosion logic and complication-drops-highest-die behavior have been verified against R&E p82. The audit confirmed this is correctly implemented (see `AUDIT_HANDOFF.md`, Appendix A).

### 🔧 Developer Internals

**File:** `engine/dice.py` — `Difficulty` IntEnum (lines 170–188):

```python
class Difficulty(IntEnum):
    VERY_EASY = 5
    EASY = 10
    MODERATE = 15
    DIFFICULT = 20
    VERY_DIFFICULT = 25
    HEROIC = 30
```

- `from_name("moderate")` → `Difficulty.MODERATE` (handles underscores and hyphens)
- `describe(target)` → human-readable name for any target number (finds the nearest bracket)

**Note on intermediate values:** `skill_checks.py::mission_difficulty()` (lines 205–217) uses non-canonical intermediate values (8, 11, 14, 16, 19, 21) for game-tuning purposes. These are deliberately between the R&E ladder values to provide finer reward scaling. They are not a bug.

**File:** `engine/dice.py` — `difficulty_check()` (lines 287–291):
```python
def difficulty_check(pool, target):
    roll = roll_d6_pool(pool)
    margin = roll.total - target
    return CheckResult(roll=roll, target=target, success=margin >= 0, margin=margin)
```

**File:** `engine/skill_checks.py` — `SkillCheckResult` dataclass (lines 58–67):
Returns `roll`, `difficulty`, `success`, `margin`, `critical_success` (Wild Die exploded AND succeeded), `fumble` (Wild Die = 1), `skill_used`, `pool_str`.

### 🔧 Developer Internals

**File:** `engine/dice.py` — `opposed_roll()` (lines 294–305):

```python
def opposed_roll(attacker_pool, defender_pool):
    att_roll = roll_d6_pool(attacker_pool)
    def_roll = roll_d6_pool(defender_pool)
    margin = att_roll.total - def_roll.total
    return OpposedResult(
        attacker_roll=att_roll, defender_roll=def_roll,
        attacker_wins=margin > 0,   # Ties go to defender
        margin=margin,
    )
```

**Usage in combat:** `engine/combat.py` does NOT use `opposed_roll()` directly for attack resolution — it rolls attacker and defender separately because combat involves additional modifiers (cover, range, multi-action penalty, wound penalties) applied between the pool construction and the roll. The opposed roll function is used for simpler contests.

**Usage in bargaining:** `skill_checks.py::resolve_bargain_check()` (lines 330–428) rolls both the player's Bargain skill and the NPC's bargain dice through `roll_d6_pool()` independently, then computes the margin to determine price adjustment (±2% per 4 points of margin, capped at ±10%).

### 🔧 Developer Internals

**File:** `engine/dice.py` — `Scale` IntEnum (lines 193–209):

```python
class Scale(IntEnum):
    CHARACTER = 0
    SPEEDER = 2
    WALKER = 4
    STARFIGHTER = 6
    CORVETTE = 9
    CAPITAL = 12
    DEATH_STAR = 18
```

- `Scale.difference(attacker_scale, defender_scale)` returns `defender - attacker` (signed)
- `apply_scale_modifier(base_pool, attacker_scale, defender_scale)` adds `abs(difference)` dice to the pool

**Usage pattern:** Scale modifiers are applied to to-hit rolls in space combat (`engine/starships.py`). The `_get_effective_for_ship()` helper computes effective stats including scale. All new space combat code must use this helper per standing architecture rules.

**File:** `data/starships.yaml` — Each ship template defines its `scale` field (e.g., `scale: starfighter` or `scale: capital`). The `data/weapons.yaml` file also tags each weapon with a `scale` field.

### 🔧 Developer Internals

**File:** `engine/dice.py` — `apply_multi_action_penalty()` (lines 309–313):
```python
def apply_multi_action_penalty(base_pool, num_actions):
    penalty = max(0, num_actions - 1)
    new_dice = max(0, base_pool.dice - penalty)
    return DicePool(new_dice, base_pool.pips if new_dice > 0 else 0)
```
Note: pips are zeroed out if dice drop to 0.

**File:** `engine/dice.py` — `apply_wound_penalty()` (lines 316–319):
```python
def apply_wound_penalty(base_pool, wound_dice):
    new_dice = max(0, base_pool.dice - wound_dice)
    return DicePool(new_dice, base_pool.pips if new_dice > 0 else 0)
```

**File:** `engine/character.py` — Wound and stun tracking:
- `WoundLevel` IntEnum (lines 32–73): HEALTHY(0) through DEAD(6)
- `penalty_dice` property: Returns 0 for Stunned (tracked separately), 1 for Wounded, 2 for Wounded Twice, 0 for Incap/Mortal/Dead (moot — can't act)
- `stun_timers: list[int]` — Each entry is a countdown in rounds. Stun penalty = `len(stun_timers)`
- `total_penalty_dice` property: `wound_level.penalty_dice + active_stun_count`
- Stun knockout threshold: `active_stun_count >= Strength dice` → unconscious

**File:** `engine/character.py` — `WoundLevel.from_damage_margin()` (lines 60–73):
```python
if margin <= 0:   return HEALTHY       # No effect
elif margin <= 3: return STUNNED       # Glancing hit
elif margin <= 8: return WOUNDED       # Solid hit
elif margin <= 12: return INCAPACITATED # Devastating
elif margin <= 15: return MORTALLY_WOUNDED
else:             return DEAD          # margin 16+
```
This maps directly to the R&E damage chart on p83. Verified correct per audit.

**Wound escalation** (`Character.apply_wound()`, lines 340–401): Implements the R&E cumulative wound rules:
- Wounded + Wounded → Incapacitated
- Incapacitated + any wound → Mortally Wounded
- Mortally Wounded + any wound → Dead
- Stun on already-Wounded character → Wounded Twice (not just another stun)

### 🔧 Developer Internals

**File:** `engine/dice.py` — CP dice (lines 332–365):
```python
def roll_cp_die() -> int:
    """Per R&E p55: explodes on 6, NO mishap on 1."""
    total = 0
    while True:
        r = roll_die()
        total += r
        if r != 6:
            break
    return total
```
- `roll_cp_dice(count)` rolls multiple CP dice, returns `(total_bonus, individual_rolls)`
- Key difference from Wild Die: **no complication on 1** — CP dice are always beneficial

**File:** `engine/dice.py` — Force Point doubling (lines 370–381):
```python
def apply_force_point(pool):
    """Double a dice pool. R&E p52."""
    return DicePool(pool.dice * 2, pool.pips * 2)
```
- Note for melee damage: doubles Strength but NOT the weapon bonus (R&E p52 vibroaxe example). This is enforced in `engine/combat.py` lines 1024–1037.

**CP spending in combat:** `engine/combat.py` lines 967–974 implement the R&E "spend after roll, before resolution" rule. The player sees their roll, decides how many CP to spend, the CP dice are rolled and added, then resolution proceeds.

### 🔧 Developer Internals

**File:** `engine/skill_checks.py` — `perform_skill_check()` (lines 72–113):

This is the **mandatory single entry point** for all out-of-combat dice rolls. It is an architecture invariant that no command file ever rolls dice directly for non-combat checks. Every roll goes through this function.

```python
def perform_skill_check(char, skill_name, difficulty, skill_registry=None):
    if skill_registry is None:
        skill_registry = _get_default_registry()

    dice, pips = _get_skill_pool(char, skill_name, skill_registry)
    pool = DicePool(dice, pips)
    roll = roll_d6_pool(pool)   # ONE canonical dice engine

    return SkillCheckResult(
        roll=roll.total,
        difficulty=difficulty,
        success=roll.total >= difficulty,
        margin=roll.total - difficulty,
        critical_success=roll.exploded and roll.total >= difficulty,
        fumble=roll.complication,
        skill_used=skill_name,
        pool_str=str(pool),
    )
```

**Higher-level resolvers** built on `perform_skill_check()`:

| Function | File | Purpose |
|----------|------|---------|
| `resolve_mission_completion()` | `skill_checks.py:220` | Mission skill check with partial pay on near-miss |
| `resolve_bargain_check()` | `skill_checks.py:297` | Opposed Bargain roll for buy/sell price adjustment |
| `resolve_repair_check()` | `skill_checks.py:433` | Ship repair with partial/catastrophic failure tiers |
| `resolve_coordinate_check()` | `skill_checks.py:534` | Command skill check for crew coordination bonus |

**Mission skill mapping** (`MISSION_SKILL_MAP`, lines 190–201):

| Mission Type | Skill Rolled | Partial Pay % |
|-------------|-------------|---------------|
| combat | blaster | 50% |
| smuggling | con | 50% |
| investigation | search | 75% |
| social | persuasion | 75% |
| technical | space transports repair | 50% |
| medical | first aid | 75% |
| slicing | computer programming/repair | 50% |
| salvage | search | 75% |
| bounty | streetwise | 50% |
| delivery | stamina | 100% (always full pay) |

**Bargain check mechanics** (lines 330–428):
- Player rolls Bargain skill, NPC rolls their bargain dice (both through `roll_d6_pool()`)
- Margin maps to price modifier: ±2% per 4 points, capped at ±10%
- Critical success doubles the modifier (still capped)
- Fumble inverts the modifier and guarantees at least a 2% swing against the player
- Result dict includes `adjusted_price`, `price_modifier_pct`, `margin`, `critical`, `fumble`, and narrative `message`

### 🔧 Developer Internals

**File:** `data/weapons.yaml` — Complete weapon and armor definitions. Each entry includes:
- `name`, `type` (blaster/melee/grenade/lightsaber/armor), `skill`, `damage`, `cost`, `scale`
- Ranged weapons: `ranges: [short_min, short_max, medium_max, long_max]`
- Grenades: `blast_radius` and `blast_damage` arrays (damage by distance band)
- Armor: `protection_energy`, `protection_physical`, `covers` list, optional `dexterity_penalty`
- Melee: `difficulty` for the weapon (Easy/Moderate/Difficult)

**File:** `engine/weapons.py` — Weapon loading and lookup utilities. Loads `data/weapons.yaml` at startup.

**Damage resolution flow** (in `engine/combat.py`):
1. Attacker rolls weapon skill vs. defender's dodge/parry (or range difficulty)
2. If hit: roll weapon damage dice
3. Defender rolls Strength + armor protection for resistance
4. Margin = damage total − resistance total
5. `WoundLevel.from_damage_margin(margin)` determines wound inflicted
6. `Character.apply_wound()` handles wound escalation

## 12. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/dice.py` | ~381 | DicePool, Wild Die, rolling, difficulty/opposed checks, CP dice, Force Point doubling, Scale system |
| `engine/character.py` | ~588 | Character dataclass, WoundLevel, SkillRegistry, skill resolution, wound escalation, serialization |
| `engine/skill_checks.py` | ~590 | Central skill check engine, mission/bargain/repair/coordinate resolvers |
| `parser/d6_commands.py` | ~287 | Player-facing +roll, +check, +opposed commands |
| `data/skills.yaml` | ~89 | 75 skill definitions across 6 attributes with specializations |
| `data/skill_descriptions.yaml` | ~50K | Detailed descriptions of every skill (for help system) |
| `data/weapons.yaml` | ~279 | 22 weapon/armor definitions with damage, ranges, costs |
| `data/species/*.yaml` | 9 files | Species attribute ranges, special abilities, story factors |

---

*End of Guide #1 — WEG D6 Core Mechanics*
*Next: Guide #2 — Character Creation*

