---
category: foundations
order: 3
summary: "How D6 dice rolls, attributes, and skills work. The rules engine behind every action."
tags: ["d6", "dice", "rolls", "attributes", "skills", "wild die", "rules"]
---

# WEG D6 Core Mechanics

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. The Dice Pool System

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

---

## 2. Skills and Skill Resolution

Skills are built on top of their parent attribute. The game has **76 skills** spread across the six attributes. When you train a skill, you're adding bonus dice above your attribute's base.

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
  [4D+2] 5, 3, 2, W:4 (+2) = 16

> +roll blaster
  Blaster (DEX): [4D+1] 5, 3, 1, W:6->3 (+1) = 19
```

**`+check <skill> <difficulty>`** — Roll your skill against a target number. Unlike a raw `+roll`, this resolves a **full skill check** through the same engine funnel every system-driven roll uses, so it honors your active buffs and debuffs, a carried tool's bonus, and any environmental penalty (such as the perception penalty during a sandstorm). The pool it prints is the *effective* pool after those modifiers; it flags a *critical!* (the Wild Die exploded on a success) or a *complication!* (a Wild Die came up 1), and credits a tool that helped.
```
> +check persuasion moderate
  Persuasion vs Moderate (15): 3D+2 = 13 -> FAILURE by 2

> +check security 15
  Security vs Moderate (15): 4D = 17 (critical!) [Code Slicer] -> SUCCESS by 2
```

**`+roll <skill> <modifier>`** — Roll with a situational modifier.
```
> +roll dodge -1D
```

Other players in the room see an abbreviated result (success/fail) but not your detailed dice breakdown.

---

## 3. The Wild Die

One die in every roll is designated the **Wild Die**. It follows special rules:

**Roll a 6 → Exploding!** Keep the 6 and roll again. If that roll is also a 6, keep going — the total is theoretically unlimited. A roll of [3, 2, W:6→6→4] scores 3 + 2 + 16 = 21. This is what makes every roll exciting — even a small dice pool can produce a spectacular result.

**Roll a 1 → Complication!** The Wild Die contributes 0 to your total, AND the game removes your highest-scoring normal die. If you rolled [5, 4, 3, W:1] with 4D, the 5 is removed and the Wild Die is 0, giving you 4 + 3 + 0 = 7 instead of what could have been 12+. Something bad may also happen narratively (at the GM's/game's discretion).

**Roll 2–5 → Normal.** The Wild Die just adds its face value like any other die.

The Wild Die creates genuine tension on every roll. A 3D pool can theoretically beat a 6D pool if the Wild Die explodes hard enough. And a complication on an otherwise easy check can turn success into failure.

---

## 4. Difficulty Numbers

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

**Partial success:** Some systems award a **partial success** on a near miss — you don't fully succeed, but you don't completely fail either. The window is system-specific: a ship or equipment **repair** that misses by up to 4 stabilizes the system without fully fixing it, while a **mission** that misses by up to 2 still earns partial pay. A near miss is always better than a clean failure.

---

## 5. Opposed Rolls

When two characters act against each other — attacker vs. dodger, haggler vs. vendor, pursuer vs. quarry — both sides roll their relevant dice pools. The higher total wins. Ties go to the defender.

The **margin** (difference between the two totals) determines how decisively one side won. In combat, the attack-vs-dodge margin feeds directly into whether damage is dealt and how severe it is. In bargaining, the margin determines how much the price shifts.

---

## 6. The Scale System

Not everything in Star Wars is the same size. A blaster pistol and a turbolaser operate on completely different scales. The game uses a **scale system** to handle cross-scale engagements:

| Scale | Value | Examples |
|-------|-------|----------|
| Character | 0 | People, droids, personal weapons |
| Speeder | 2 | Landspeeders, swoops |
| Walker | 4 | AT-TE, AT-RT |
| Starfighter | 6 | ARC-170 Starfighter, Vulture Droid Starfighter |
| Corvette | 9 | Corellian Corvette, gunships |
| Capital | 12 | Venator-class Star Destroyer, Acclamator-class assault ship |
| Death Star scale | 18 | (Canonical scale-18 reference; no such weapon exists in the Clone Wars era) |

When something at a smaller scale attacks something at a larger scale, the smaller attacker gets **bonus dice to hit** equal to the scale difference (the bigger target is easier to hit) but does **reduced damage** (the target's armor is massive relative to your weapon). The reverse also applies — a turbolaser has a hard time hitting a starfighter, but if it connects, the fighter is dust.

The scale difference is always the absolute value of `defender_scale - attacker_scale`. For a character (0) attacking a starfighter (6), the difference is 6D.

---

## 7. Multiple Actions and Penalties

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

---

## 8. Character Points and Force Points

**Character Points (CP)** are your tactical resource. You can spend them mid-combat, *after* seeing your roll but before the result is applied, to add extra dice. Each CP spent adds one die to the roll — and these bonus dice **explode on 6 like the Wild Die** (but don't cause complications on 1). This lets you turn a near-miss into a hit when it really matters.

CPs are also your advancement currency (see the CP Progression guide for details).

**Force Points (FP)** are your dramatic resource. Spending a Force Point **doubles all your dice** for the entire round — attributes, skills, everything. It's the cinematic "hero moment." A character with 4D in Blaster becomes 8D for one round. You typically have only 1–2 Force Points, so each use is a major decision.

If you spend a Force Point at a dramatically appropriate moment (self-sacrifice, saving innocents, etc.), you get it back at the end of the session. Spend it selfishly or use it for the Dark Side, and it's gone — or worse, you gain a Dark Side Point.

---

## 9. The Unified Skill Check Engine

You don't need to know this as a player — the game handles it automatically. But it's worth understanding that every non-combat dice roll in the entire game goes through a single system. Whether you're completing a mission, haggling a price, repairing a ship, or slicing a computer, the same engine resolves your roll. This guarantees that the Wild Die, difficulty numbers, partial successes, and critical/fumble mechanics work identically everywhere.

---

## 10. Weapons and Damage Codes

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
| Improved Body Armor | +1D | +2D | −1D Dexterity |
| Bounty Hunter Armor | +2D | +3D | −1D Dexterity |

**Range bands** affect hit difficulty:

| Range | Difficulty |
|-------|-----------|
| Point-blank (< short min) | Very Easy (5) |
| Short | Easy (10) |
| Medium | Moderate (15) |
| Long | Difficult (20) |

---

## 11. Summary of Key Data Flows

### How a Complete Non-Combat Check Works (End to End)

A player's `+check` and an engine-driven check travel the **same path**: every out-of-combat skill roll resolves through the single `perform_skill_check` funnel. That is what lets a manual `+check` honor your buffs, tools, and the environment exactly the way a mission, harvest, or slicing check does — and what feeds the success-rate telemetry the game uses to keep difficulty numbers calibrated.

```
Player types: +check search 15

1. parser/d6_commands.py::CheckCommand.execute()
   ├── Parses "search" and "15" from args
   ├── Looks up "search" in SkillRegistry → SkillDef(name="Search", attribute="perception")
   └── Calls perform_skill_check(char, "Search", 15, skill_reg)   ← the one funnel

2. engine/skill_checks.py::perform_skill_check()
   ├── _get_skill_pool(char, "Search", registry)
   │   ├── Looks up parent attribute → "perception"
   │   ├── Parses char["attributes"] JSON → Perception pool
   │   ├── Parses char["skills"] JSON → Search bonus (if any)
   │   └── Returns (dice, pips)
   ├── Applies the modifier stack (all in pips, floored at 1D):
   │   ├── environment — sandstorm perception penalty (observation skills only)
   │   ├── carried tool — best single tool bonus (no stacking)
   │   ├── buffs / debuffs — active effects on the parent attribute
   │   └── combined-action lead — staged support bonus
   ├── Builds the effective DicePool, calls roll_d6_pool()
   │   ├── Rolls (pool.dice - 1) normal d6s + the Wild Die (roll_wild_die())
   │   ├── On a Wild Die 1: removes the highest normal die (complication)
   │   └── Returns RollResult
   ├── Emits the `skill_check` telemetry event (T3.19, fail-open + sampled)
   └── Returns SkillCheckResult(success, margin, critical_success,
                                fumble, pool_str, tool_name, …)

3. Back in CheckCommand:
   ├── Formats with ANSI colors (green=success, red=fail), tagging a
   │   critical!/complication! and a [tool] credit when one contributed
   ├── Sends the detailed breakdown to the player
   └── Broadcasts the abbreviated result to the room
```

Combat, communal-objective, and Force-power rolls take a parallel resolver, `engine/dice.py::difficulty_check` — a raw pool-vs-target roll *without* the out-of-combat funnel's buff/tool/environment stack. (`+roll` and `+opposed` are not difficulty checks, so neither passes through `perform_skill_check`.)

---

