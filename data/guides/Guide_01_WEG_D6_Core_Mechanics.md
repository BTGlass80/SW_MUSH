# SW_MUSH Detailed Systems Guide #1
# WEG D6 Core Mechanics

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide is split into two tracks. **Player Rules** sections explain how the system works from a player's perspective — what you type, what you see, and what the numbers mean. **Developer Internals** sections (marked with 🔧) explain how the code implements each mechanic, including file paths, function signatures, data structures, and edge cases. Skip whichever track doesn't apply to you.

---

## 1. The Dice Pool System

### Player Rules

Every ability in the game — from shooting a blaster to haggling a price to piloting a starship — is expressed as a **dice pool**. A dice pool looks like this:

```
4D+2
```

That means "roll four six-sided dice and add 2 to the total." The number before the D is how many dice you roll. The number after the + is your **pips** — a small bonus on top of the dice.

Pips range from 0 to 2. When you accumulate 3 pips, they automatically roll up into another die: 3D+3 becomes 4D. This is how advancement works — you improve in small increments (pips) that eventually become full dice.

Your character has six **attributes**, each expressed as a dice pool:

| Attribute | Governs |
|-----------|---------|
| **Dexterity** | Shooting, dodging, melee combat, throwing, running, sneaking |
| **Knowledge** | Alien species, streetwise, survival, languages, tactics, willpower |
| **Mechanical** | Piloting, astrogation, sensors, gunnery, vehicle operation |
| **Perception** | Persuasion, bargain, con, search, command, gambling, hiding |
| **Strength** | Brawling, lifting, stamina, climbing, swimming |
| **Technical** | Repair, first aid, computer slicing, demolitions, medicine |

A starting Human character distributes **18D** across these six attributes, with each attribute between 2D and 4D. Other species have different ranges — a Wookiee's Strength ranges from 3D to 6D, but their Knowledge caps at 2D+1.

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

---

## 2. Skills and Skill Resolution

### Player Rules

Skills are built on top of their parent attribute. The game has **75 skills** spread across the six attributes. When you train a skill, you're adding bonus dice above your attribute's base.

**Example:** Your Dexterity is 3D+1. You train 1D in Blaster. Your effective Blaster skill is 4D+1 (the attribute plus the skill bonus). If you haven't trained Blaster at all, you just roll your raw Dexterity — 3D+1.

Here's a sampling of skills by attribute:

**Dexterity:** Blaster, Dodge, Melee Combat, Brawling Parry, Grenade, Lightsaber, Pick Pocket, Running
**Knowledge:** Streetwise, Survival, Languages, Intimidation, Tactics, Willpower, Alien Species, Bureaucracy
**Mechanical:** Space Transports, Starfighter Piloting, Astrogation, Sensors, Starship Gunnery, Capital Ship Piloting
**Perception:** Bargain, Command, Con, Persuasion, Search, Sneak, Hide, Gambling, Investigation
**Strength:** Brawling, Climbing/Jumping, Lifting, Stamina, Swimming
**Technical:** First Aid, Computer Programming/Repair, Space Transport Repair, Security, Demolitions, Medicine

Some skills have **specializations** — narrower versions that are cheaper to advance. Blaster has specializations for Heavy Blaster Pistol, Blaster Rifle, and Hold-Out Blaster. Specializations are tracked separately and add on top of the base skill.

### Using Skills In-Game

Three commands let you roll dice directly:

**`+roll <dice or skill>`** — Roll a dice pool or your skill, with Wild Die.
```
> +roll 4D+2
  [4D+2] 3, 5, 2, W:4 (+2) = 16

> +roll blaster
  Blaster (DEX): [4D+1] 5, 3, 1, W:6->3 (+1) = 19
```

**`+check <skill> <difficulty>`** — Roll your skill against a target number.
```
> +check persuasion moderate
  Persuasion vs Moderate (15): [3D+2] 4, 2, W:5 (+2) = 13 -> FAILURE by 2
```

**`+roll <skill> <modifier>`** — Roll with a situational modifier.
```
> +roll dodge -1D
```

Other players in the room see an abbreviated result (success/fail) but not your detailed dice breakdown.

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

---

## 3. The Wild Die

### Player Rules

One die in every roll is designated the **Wild Die**. It follows special rules:

**Roll a 6 → Exploding!** Keep the 6 and roll again. If that roll is also a 6, keep going — the total is theoretically unlimited. A roll of [3, 2, W:6→6→4] scores 3 + 2 + 16 = 21. This is what makes every roll exciting — even a small dice pool can produce a spectacular result.

**Roll a 1 → Complication!** The Wild Die contributes 0 to your total, AND the game removes your highest-scoring normal die. If you rolled [5, 4, 3, W:1] with 4D, the 5 is removed and the Wild Die is 0, giving you 4 + 3 + 0 = 7 instead of what could have been 12+. Something bad may also happen narratively (at the GM's/game's discretion).

**Roll 2–5 → Normal.** The Wild Die just adds its face value like any other die.

The Wild Die creates genuine tension on every roll. A 3D pool can theoretically beat a 6D pool if the Wild Die explodes hard enough. And a complication on an otherwise easy check can turn success into failure.

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

---

## 4. Difficulty Numbers

### Player Rules

When you attempt something, the game sets a target number based on how hard it is:

| Difficulty | Target Number | Example |
|-----------|---------------|---------|
| Very Easy | 5 | Climbing a ladder, noticing something obvious |
| Easy | 10 | Picking a simple lock, basic first aid |
| Moderate | 15 | Tracking someone through a crowd, decent piloting |
| Difficult | 20 | Hotshot combat maneuver, repairing under fire |
| Very Difficult | 25 | Threading an asteroid field, cracking military encryption |
| Heroic | 30+ | Something that should be impossible |

You roll your dice pool and compare the total to the target. Meet or beat it and you succeed. Miss it and you fail. How much you succeed or fail by (the **margin**) matters — a huge margin means a spectacular result, while barely scraping by is a narrow success.

**Partial success:** In many systems (missions, repairs, bounties), missing the target by 4 or fewer points gives a **partial success** — you don't fully succeed, but you don't completely fail either. You might earn partial pay on a mission or stabilize a damaged ship system without fully repairing it.

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

---

## 5. Opposed Rolls

### Player Rules

When two characters act against each other — attacker vs. dodger, haggler vs. vendor, pursuer vs. quarry — both sides roll their relevant dice pools. The higher total wins. Ties go to the defender.

The **margin** (difference between the two totals) determines how decisively one side won. In combat, the attack-vs-dodge margin feeds directly into whether damage is dealt and how severe it is. In bargaining, the margin determines how much the price shifts.

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

---

## 6. The Scale System

### Player Rules

Not everything in Star Wars is the same size. A blaster pistol and a turbolaser operate on completely different scales. The game uses a **scale system** to handle cross-scale engagements:

| Scale | Value | Examples |
|-------|-------|----------|
| Character | 0 | People, droids, personal weapons |
| Speeder | 2 | Landspeeders, swoops |
| Walker | 4 | AT-ST, AT-AT |
| Starfighter | 6 | X-Wing, TIE Fighter |
| Corvette | 9 | Corellian Corvette, gunships |
| Capital | 12 | Star Destroyer, Mon Calamari cruiser |
| Death Star | 18 | The Death Star |

When something at a smaller scale attacks something at a larger scale, the smaller attacker gets **bonus dice to hit** equal to the scale difference (the bigger target is easier to hit) but does **reduced damage** (the target's armor is massive relative to your weapon). The reverse also applies — a turbolaser has a hard time hitting a starfighter, but if it connects, the fighter is dust.

The scale difference is always the absolute value of `defender_scale - attacker_scale`. For a character (0) attacking a starfighter (6), the difference is 6D.

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

---

## 7. Multiple Actions and Penalties

### Player Rules

In a combat round, you can attempt multiple actions — shoot and dodge, pilot and fire, etc. But there's a cost: **each action beyond the first reduces ALL your rolls that round by 1D.**

- 1 action: No penalty
- 2 actions: −1D to both
- 3 actions: −2D to all three
- 4 actions: −3D to all four

This makes multi-action rounds a genuine tradeoff. A character with 4D in Blaster who declares two actions (shoot + dodge) rolls both at 3D. Three actions drops everything to 2D. You're spreading yourself thin.

### Wound Penalties

Injuries also reduce your dice pools:

| Wound Level | Penalty | Can Still Act? |
|-------------|---------|----------------|
| Healthy | None | Yes |
| Stunned | −1D per active stun | Yes |
| Wounded | −1D | Yes |
| Wounded Twice | −2D | Yes |
| Incapacitated | Cannot act | No |
| Mortally Wounded | Cannot act (death roll each round) | No |
| Dead | — | No |

Wound penalties and multi-action penalties **stack**. A Wounded character (−1D) who declares two actions (−1D) is rolling at −2D to everything.

**Stun stacking:** Each stun hit applies its own −1D penalty. If you take three stun hits, that's −3D. If your total active stun count reaches or exceeds your Strength dice, you're knocked unconscious. Stuns expire after a set number of rounds.

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

---

## 8. Character Points and Force Points

### Player Rules

**Character Points (CP)** are your tactical resource. You can spend them mid-combat, *after* seeing your roll but before the result is applied, to add extra dice. Each CP spent adds one die to the roll — and these bonus dice **explode on 6 like the Wild Die** (but don't cause complications on 1). This lets you turn a near-miss into a hit when it really matters.

CPs are also your advancement currency (see the CP Progression guide for details).

**Force Points (FP)** are your dramatic resource. Spending a Force Point **doubles all your dice** for the entire round — attributes, skills, everything. It's the cinematic "hero moment." A character with 4D in Blaster becomes 8D for one round. You typically have only 1–2 Force Points, so each use is a major decision.

If you spend a Force Point at a dramatically appropriate moment (self-sacrifice, saving innocents, etc.), you get it back at the end of the session. Spend it selfishly or use it for the Dark Side, and it's gone — or worse, you gain a Dark Side Point.

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

---

## 9. The Unified Skill Check Engine

### Player Rules

You don't need to know this as a player — the game handles it automatically. But it's worth understanding that every non-combat dice roll in the entire game goes through a single system. Whether you're completing a mission, haggling a price, repairing a ship, or slicing a computer, the same engine resolves your roll. This guarantees that the Wild Die, difficulty numbers, partial successes, and critical/fumble mechanics work identically everywhere.

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

---

## 10. Weapons and Damage Codes

### Player Rules

Weapons have a **damage code** — another dice pool. When you hit a target, you roll the weapon's damage dice against the target's **resistance** (Strength for characters, hull for ships). The margin between damage and resistance determines the wound level inflicted.

**Ranged weapons** (blasters) have flat damage codes:

| Weapon | Damage | Cost | Notes |
|--------|--------|------|-------|
| Hold-Out Blaster | 3D+1 | 275 cr | Easily concealed |
| Blaster Pistol | 4D | 500 cr | Standard sidearm |
| Heavy Blaster Pistol | 5D | 750 cr | Powerful, short range |
| Blaster Rifle | 5D | 1,000 cr | Standard military |
| Sporting Blaster | 3D+1 | 300 cr | Light civilian |
| Light Repeating Blaster | 6D | 2,000 cr | No stun setting |
| Bowcaster | 4D | 900 cr | Requires STR 4D to cock |

**Melee weapons** add to your Strength:

| Weapon | Damage | Cost |
|--------|--------|------|
| Knife | STR+1D | 25 cr |
| Vibroblade | STR+3D | 250 cr |
| Vibroaxe | STR+3D+1 | 500 cr |
| Force Pike | STR+2D | 500 cr |
| Lightsaber | 5D (flat) | — |

**Armor** adds to your Strength for damage resistance:

| Armor | Energy Protection | Physical Protection | Penalty |
|-------|-------------------|---------------------|---------|
| Blast Vest | +1D | +1D | None |
| Blast Helmet | +1D | +1D | None |
| Stormtrooper Armor | +1D | +2D | −1D Dexterity |
| Bounty Hunter Armor | +2D | +3D | −1D Dexterity |

**Range bands** affect hit difficulty:

| Range | Difficulty |
|-------|-----------|
| Point-blank (< short min) | Very Easy (5) |
| Short | Easy (10) |
| Medium | Moderate (15) |
| Long | Difficult (20) |

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

---

## 11. Summary of Key Data Flows

### How a Complete Non-Combat Check Works (End to End)

```
Player types: +check search 15

1. parser/d6_commands.py::CheckCommand.execute()
   ├── Parses "search" and "15" from args
   ├── Looks up "search" in SkillRegistry → SkillDef(name="Search", attribute="perception")
   ├── Builds Character from DB dict
   └── Calls dice.difficulty_check(pool, 15)

2. engine/dice.py::difficulty_check()
   ├── Calls roll_d6_pool(pool)
   │   ├── Rolls (pool.dice - 1) normal d6s
   │   ├── Rolls Wild Die (roll_wild_die())
   │   ├── On complication: removes highest normal die
   │   └── Returns RollResult
   └── Returns CheckResult(success, margin)

3. Back in CheckCommand:
   ├── Formats result with ANSI colors (green=success, red=fail)
   ├── Sends detailed breakdown to the player
   └── Broadcasts abbreviated result to room
```

### How a Skill Check Through perform_skill_check Works

```
Engine code calls: perform_skill_check(char_dict, "bargain", 15)

1. engine/skill_checks.py::perform_skill_check()
   ├── Gets SkillRegistry (module-level singleton, lazy-loaded)
   ├── _get_skill_pool(char, "bargain", registry)
   │   ├── Looks up parent attribute → "perception"
   │   ├── Parses char["attributes"] JSON → gets Perception pool
   │   ├── Parses char["skills"] JSON → gets Bargain bonus (if any)
   │   └── Returns (total_dice, total_pips)
   ├── Builds DicePool, calls roll_d6_pool()
   └── Returns SkillCheckResult with all metadata
```

---

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
