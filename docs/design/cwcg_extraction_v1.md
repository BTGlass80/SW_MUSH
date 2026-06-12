# Clone Wars Campaign Guide — SW_MUSH Extraction (v1)

**Source:** *The Clone Wars Campaign Guide* (Wizards of the Coast, Star Wars Saga Edition, January 2009; ISBN 978-0786949991, 224 pages; Rodney Thompson, Patrick Stutzman, J.D. Wiker, Gary Astleford, T. Rob Brown).
**Generated:** April 26, 2026
**Scope:** Lore, structural patterns, and one additive ruleset (mass combat). All Saga Edition character/equipment/Force/vehicle/starship rules are deliberately omitted — SW_MUSH is built on **WEG D6 Revised & Expanded** and adding parallel d20 mechanics to ground combat, space combat, character creation, or equipment would dilute that core ruleset.

---

## Reading rules — WEG-focus discipline

This file is split into two kinds of content:

- **🧱 ADDITIVE — gap-filling for SW_MUSH.** Material here covers ground that WEG D6 R&E does not address. It is safe to lift mechanics directly because there's no WEG equivalent to compete with. Currently exactly one section: **Mass Combat (§2)**.
- **📖 LORE & STRUCTURE — never rules.** Everything else: faction lore, Jedi Order structure, atmospheric campaign themes, Force-using traditions, planet entries. Use as content/atmosphere/world-building reference only. **Do not lift Saga numbers or mechanics from these sections** — the source provides Saga stats, but SW_MUSH should generate its own D6 stats from WEG sources (`WEG40120.pdf`, `Star_Wars_Sourcebook_2nd_Edition_*`, the Galaxy Guides) when stat blocks are needed.

**Excluded from this extract** (and should stay excluded):
- Saga character classes, talents, feats, prestige classes (`Heroes of the Clone Wars`, `Prestige Classes` chapters) — would compete with WEG character creation.
- New weapons and equipment (`Equipment and Droids` chapter) — would compete with WEG equipment lists.
- Saga Force powers, talents, secrets, techniques (`The Force` chapter — except the three Force-using **traditions**, which are pure lore — see §4) — would dilute WEG Force Powers system in `Guide_08`.
- Starship and vehicle stat blocks (`Starships` chapter, plus vehicles/starships sections of Republic/CIS/Jedi chapters) — would compete with WEG ship stats and the `space_overhaul_v3_design`/`Guide_05_Space_Systems`.
- Saga species traits (`Species` chapter) — would compete with WEG species mechanics.
- Followers system **as a rule mechanic** (`Heroic Traits` chapter) — uses Saga's CL/talent structure that doesn't translate to D6. The **design patterns** behind the system are summarized in §1 as inspiration for `padawan_master_system_design_v1.md`, but the numbers and feat-gates are not.

---

## §1. Followers / Mentor-Companion Patterns 📖
**Maps to:** `padawan_master_system_design_v1.md`, `weight_of_war_design_v1.md` (squad leadership feel)

The Saga book's Followers system is a Talent-gated way for a hero to acquire a small group of NPC allies who travel and fight alongside them. The mechanics are tied to Saga's CL and feat economy and don't port to WEG, but the **design patterns** are useful reference for the Padawan-Master system and any future companion/crew mechanic.

### Useful design patterns (pattern, not rule)

1. **Acquisition is character-driven, not loot-driven.** A hero doesn't *find* followers; the hero takes a deliberate character-development step (in Saga, a Talent) that opens up follower acquisition. The follower is then created with the hero's input on role and personality. → Implication for `padawan_master_system`: a Master taking on a Padawan should be a deliberate character milestone, not a quest reward.

2. **Three follower archetypes** ground the system in clear roles:
   - **Aggressive** — focused on dealing damage; bonuses to Strength/Constitution; trained in Endurance; weapon-proficiency feat.
   - **Defensive** — focused on holding ground, taking suppression; bonuses to Dexterity/Wisdom; armor-proficiency feat.
   - **Utility** — broad skills, multiple proficiencies; bonuses to Int/Cha; weapon OR armor proficiency.
   These map onto a "what is this companion *for*" question players answer at acquisition. → Implication: Padawans (and any other companion type) benefit from a small, sharply-distinguished archetype set rather than full character-builder breadth.

3. **Followers gain advancement passively, not by independent XP.** Follower stats are derived from the hero's level. → Implication: Padawan progression should be tied to a clear function of the Master's progression, not an independent CP track. This avoids the bookkeeping nightmare of independent NPC PCs.

4. **Sharing actions across hero + follower has a hard daily/round budget.** A hero can let a follower take *one* of several specific actions per round (attack, aid, draw weapon, manipulate item, move with you, fight defensively, use special ability). The hero cannot give followers a full duplicate action economy. The book is explicit that this is to prevent a hero who takes follower talents from out-pacing other party members. → Implication for `padawan_master`: any "Master commands Padawan" mechanic must have a round-budget that prevents the Master from effectively doubling their own actions. The Saga book recommends each follower-granting talent grant *at least* one feature that lets only-the-hero act — same principle as preserving Master-character distinctness.

5. **Follower death penalty is graceful.** When a follower dies, the hero loses *no* benefits of the Talent — they can recruit a replacement after a recruitment period (typically 8 hours of in-game searching). → Implication: Padawan death shouldn't permadeath the Master's "I have a Padawan" status; there should be a recruitment downtime cost only.

6. **Dark Side responsibility flows up.** A good leader is responsible for the actions of those who follow him. If a Master commands a Padawan to do something that would normally raise the Master's Dark Side score, it raises the Master's Dark Side score. If a Padawan's DSP equals their Wisdom, they fall — they become an NPC under GM control, and the hero may recruit a replacement *as though the Padawan had died*. → Implication: in SW_MUSH, a Padawan who falls to the Dark Side leaves the player's control; the Master takes a one-time DSP gain reflecting their failure, then can take on a new Padawan after a cooldown.

7. **Equipping followers shares the hero's credits but limits arsenal.** Followers carry equipment but are limited by their (small) number of weapon and armor proficiencies, which prevents them from becoming walking arsenals. → Implication: Padawan equipment should be limited to their training, not the Master's wealth.

The above are **patterns**, not numbers. Concrete D6 rules for `padawan_master_system` should derive from WEG sources.

---

## §2. Mass Combat 🧱 ADDITIVE
**Maps to:** `weight_of_war_design_v1.md` (Priority H)
**Status:** Gap-filling. WEG D6 R&E does not include a mass-combat subsystem at this scale. This entire section is safe to translate to D6 because there is no WEG equivalent to compete with. **Translation rules at end of section.**

### 2.1 Concept

Mass Combat is a system for resolving battles involving thousands of combatants without rolling individually for every soldier. It scales the standard combat encounter by treating large groups of low-CL identical creatures as a single composite **unit**, which acts and is targeted as one entity.

The core abstraction: a unit's stats are derived from the stats of one *representative* creature (e.g., a single B1 battle droid or a single clone trooper) by applying a multiplier transformation. The unit then takes actions, occupies battlefield space, and resolves attacks like a single creature — but its hit points, damage threshold, and presence on the battlefield reflect the dozens to hundreds of soldiers it contains.

Mass Combat is designed to operate alongside character-scale play. Heroes (and important NPCs) act as individual combatants on the same battlefield, capable of joining units, commanding them, dueling other unit-leaders, or pursuing independent objectives while the mass battle plays out around them. **A unit cannot target an individual character directly via attacks. A unit's attacks target other units or vehicles.**

### 2.2 Scale

Mass combat takes place at **starship scale** (1 square = 1 starship-scale square). Character-scale movement, weapon ranges, and area effects are converted to starship scale via the standard conversion table. This means the battlefield is much wider than a normal encounter — appropriate for representing a battle spread across kilometers.

Combat round length is also abstracted at this scale.

### 2.3 Creating a Unit

To make a unit out of a base creature, apply the following transformations to the creature's stat block:

| Stat | Transform |
|---|---|
| **Size** | Increase one category, ending at Colossal (Ingame). Units do not exceed Colossal. |
| **Initiative & Senses** | Unchanged from base creature. |
| **Defenses** | Unchanged from base creature. |
| **Hit Points** | × 4 |
| **Damage Reduction (DR/SR)** | Use the SR of the base creature, gain DR 15. |
| **Damage Threshold** | Replace the base creature's size bonus to damage threshold; if any, with a +50 size bonus. So: `Threshold = Fortitude Defense + 50` |
| **Attrition** | All units have attrition numbers. Three attrition steps below the unit's hit point total (each one step lower than the prior on the condition track). When the unit drops below an attrition step, it moves -1 persistent step on the condition track. The persistent condition cannot be removed from the unit. (See 2.4) |
| **Speed** | For most ground units, the unit's speed at starship scale is 1 square. Some creatures with high base speed can move faster (use "Speed conversions" table at end). The unit does not retain the base creature's full movement modes. |
| **Melee Attacks** | Convert base melee attacks to unit melee attacks. Attack bonuses remain the same, but all attacks (without a damage multiplier) gain a ×2 damage multiplier. |
| **Ranged Attacks** | Convert base ranged attacks to unit ranged attacks. Attack bonuses remain the same, but all attacks (without a damage multiplier) gain a ×2 damage multiplier. |
| **Fighting Space** | All units have a fighting space of 1 square at starship scale. |
| **Base Attack & Grapple** | Retain the base creature's base attack and grapple scores. |
| **Ability Scores** | Retain the base creature's ability scores. |
| **Talents and Feats** | Units have no talents or feats. Exception: talents/feats that *alter attack rolls with numerical modifiers* (e.g., Power Attack, Rapid Shot, Burst Fire) — these attack options can be converted to unit attacks. Talents/feats that rely on other conditions or situations to activate (most other talents) do not carry over. |
| **Skills** | Retain the skill modifiers of the base creature. |
| **Possessions** | Retain only possessions relevant to the unit's attacks and defenses. |

### 2.4 Attrition

A unit has three attrition steps below its hit point total (one step down the condition track per step). Use the example unit below: when a clone trooper battalion drops below 62 hit points, it moves −1 persistent step. Attrition steps cannot be removed from the unit. The unit's normal condition track works on top of attrition.

To determine attrition numbers: divide the unit's total hit points by 4 (rounding down), then subtract that number from the total hit points 3 times, each time marking the result on the attrition track.

### 2.5 Sample Unit: Clone Trooper Battalion

```
Clone Trooper Battalion                                      CL 8
Colossal ground unit (Human nonheroic 6)
Init +9; Senses Perception +9
Defenses Ref 17 (flat-footed 16), Fort 13, Will 9
hp 82; DR 15; Threshold 63; Attrition 62 / 42 / 22
Speed 1 square (starship scale)
Ranged blaster rifle +5 (see below)
Fighting Space 1 square (starship scale)
Base Atk +4; Grp +5
Abilities Str 12, Dex 13, Con 12, Int 10, Wis 9, Cha 8
Special Qualities half damage from nonarea attacks
Skills Initiative +9, Perception +9
Possessions clone trooper armor, blaster rifle

Blaster Rifle:  Atk +5 (+0 autofire); Dmg (3d8+3) ×2
```

### 2.6 Sample Unit: B1 Battle Droid Squad

```
B1-Series Battle Droid Squad                                 CL 3
Large droid 14th-degree squad nonheroic 3
Init +0; Senses Perception +0
Languages Basic, Binary
Defenses Ref 9 (flat-footed 8), Fort 11, Will 12
hp 23; Threshold 21; Immune droid traits
Speed 6 squares (walking)
Melee unarmed +2 (1d4+1)
Ranged blaster carbine +3 (3d8, 1-square splash)
Fighting Space 2×2; Reach 1 square
Base Atk +2; Grp +3
Abilities Str 13, Dex 9, Con —, Int 9, Wis 10, Cha 10
Special Qualities droid traits, squad traits
Feats: Toughness, Weapon Proficiency (pistols, rifles, simple weapons)
Skills Perception +0
Systems walking locomotion, remote receiver, 2 hand appendages,
  internal comlink, vocabulator
Possessions blaster carbine
Squad Traits — The melee attack of a squad is an area attack that affects
  all squares within reach. The ranged attacks of a squad are considered
  to have a 1-square splash. Area attacks deal an extra 2 dice of damage
  against a squad. A squad cannot be grabbed or grappled.
```

### 2.7 Unit Type Modifiers (Advantaged / Disadvantaged Units)

A unit can be **Advantaged** (better trained, equipped, or staffed than a standard unit). Advantaged units take a special quality and the unit's CL increases by 1. Multiple special qualities can be selected; CL increases by 1 each time. Available special qualities include:

- **All-Terrain Unit** — ignores difficult terrain.
- **Antiair Unit** — +2 competence bonus on attack rolls and +1 die of damage against airspeeders and starfighters.
- **Antiarmor Unit** — +2 competence bonus on attack rolls and +1 die of damage against nonflying units and nonflying vehicles.
- **Dedicated Officer** — unit can take extra actions as though the unit had a hero in one of the unit roles. Choose one of the unit roles (Commander, First Officer, Attack Leader, Communications Officer, Medic).
- **Mobile Unit** — when using hard march or all-out movement, the unit moves 5 times its base speed instead of 4.
- **Reinforcements** — when this unit disbands and reforms with another unit, the new unit starts at full hit points regardless of the actual hit points of either unit.
- **Superior Formation** — +2 competence bonus to Reflex Defense.
- **Superior Training** — +5 competence bonus on all unit checks.
- **Superior Weapons** — +1 die of damage with all attacks made with weapons.
- **Vehicle Contingent** — unit also has a small contingent of vehicles. Choose a vehicle whose CL is no more than 2 points higher than the unit's CL; the unit gains an attack with that vehicle's weapon.

A **Disadvantaged Unit** has inferior numbers, equipment, or morale. Apply the inverse: hit points × 3 (instead of × 4); CL decreases by 2.

### 2.8 Attacks and Damage

- A **unit** can make melee and ranged attacks if it possesses appropriate weapons.
- Units use Table 7-1 (Character Weapon Ranges) to determine character-scale weapon ranges at starship scale. Heavy weapons reach further; pistols are point-blank only. (Range table summarized: heavy = point-blank/short/medium/long all valid at starship scale; rifles = no point-blank but short/medium/long; single weapons = point-blank only; thrown = point-blank only.)
- A unit takes **half damage from non-area attacks** at character scale. Area attacks deal full damage to a unit.
- An **area attack against a unit** targets one square within weapon range. The attacker rolls; if both ground units and flying units occupy that square, the attacker chooses which units are hit, but not both.
- Critical hits: a natural 20 against a unit causes the unit to *automatically* take full damage from the attack (instead of the normal half) but only on a non-character-scale weapon — for character-scale weapons, the damage stays the same.
- A natural 1 attack roll against a unit is always a miss.
- Vehicle weapons deal full damage at unit scale.

### 2.9 Hit Points & Damage Threshold

Units have hit points like normal, but represent the unit's combat capacity rather than literal individual losses. When the unit drops to 0 hit points, it disbands. If the attack that reduced it to 0 also exceeded its damage threshold, every hero in the unit's square *also* takes that 22 damage. (For unit attacks, hero damage is taken after unit damage.)

`Damage Threshold = Fortitude Defense + 50 (size modifier)`

### 2.10 Speed

Units have a single speed in squares (starship scale). A commander can move a unit at up to 4 times its speed via the **Hard March** action, but at the cost of becoming flat-footed until the start of the commander's next turn.

### 2.11 Occupying the Same Square

Mass combat allows a unit to move into a square with other units. A square can hold up to two ground units and two flying units at a time. There are no direct consequences for moving past, into, or out of a square already occupied by a unit (though occupying the same square might allow the enemy to target you with area attacks).

### 2.12 Reducing a Unit to 0 Hit Points

When a unit is reduced to 0 hit points, it disbands immediately. Any heroes in the unit's square take that unit's damage equal to the lowest attrition number. (Thus, if the attack that reduces a clone trooper battalion to 0 hp also exceeds its damage threshold, each hero in that unit takes 22 damage.)

### 2.13 Characters in Units (Roles)

Characters can fill one of several specific roles within a unit. Each unit can have only one of each role at a time. Characters within units cannot be specifically targeted by effects or attacks, just as one cannot target sacrifice vehicle systems in most circumstances.

- **Commander** — central authority and leader. Issues most of the orders. Controls movement, can fill any other role not currently filled. One commander at a time.
- **First Officer** — second-in-command. Helps ensure all orders are carried out properly. Can perform all the same actions as the Commander, but only if the Commander hasn't performed that same action since the end of the First Officer's last turn. One at a time.
- **Attack Leader** — coordinates all the unit's attacks. An attack leader can order attacks and use special tactics. One at a time.
- **Communications Officer** — responsible for coordinating all the orders within the unit and with other units. One at a time.
- **Medic** — responsible for keeping the unit a healthy fighting force. The medic coordinates a team of combat physicians who oversee the general welfare of the unit. One at a time.

### 2.14 Using Talents, Feats, and Special Abilities (Characters in Units)

Characters filling roles in a unit might have talents, feats, Force powers, and special abilities they can use in mass combat. As a general rule, special abilities that function in character combat have too narrow an effect to be noticeable in mass combat. Some abilities, especially those used by officers and medics, can give units a big advantage through superior leadership. Specific filters that determine whether an ability translates:

- **All Targets Who Can See, Hear, and Understand You** — abilities that require your targets to be able to see, hear, and understand you function only for targets within your same square in mass combat.
- **All Targets in Line of Sight** — abilities that affect comrades, allies, or targets in line-of-sight function in mass combat. They affect all targets of the appropriate type within your same square.
- **Single Target, Limited Number of Targets, or Nearby Targets** — abilities that affect a single target, a limited number of targets, or targets within a certain number of squares of you have no effect during mass combat.

### 2.15 Standard Actions Available to Units

- **Aid Another** — add the attack roll of another unit (if line of sight). Suppress fire. (See full original for details.)
- **Attack with Melee Weapons (Attack Leader Only)** — A ground unit can make melee weapon attacks against another ground unit if it shares the same space as an enemy unit or vehicle. Can make a single melee attack against that target as a standard action. Individual characters cannot make melee attacks against units.
- **Attack with Ranged Weapons (Attack Leader Only)** — Units can make attacks using their ranged weapons. A unit can target a unit or vehicle within its range and attack with its ranged weapon as a standard action. Individual characters cannot make ranged attacks against units.
- **Attack with Vehicle Weapons (Attack Leader Only)** — Vehicle units can attack with each weapon that has its own gunner. Vehicle weapons attacks follow the same rules as in vehicle combat (see Saga p.187 — but for SW_MUSH purposes, this maps to standard WEG vehicle weapon rules).
- **Charge (Commander Only)** — The commander can order the unit to charge: moving up to its speed and making a melee attack in one action. Charging unit gains +2 to attack but takes -2 penalty to Reflex Defense until the start of its next turn.
- **Fight Defensively (Attack Leader Only)** — Order the unit to fight defensively as a standard action, hunkering down to resist incoming attacks. The unit cannot make attacks until the beginning of the Attack Leader's next turn but gains +5 bonus to Reflex Defense.
- **Provide Medical Assistance (Medic Only)** — By spending three swift actions, the medic can administer basic first aid to the unit. After spending the third swift action, make a DC 20 Treat Injury check. If successful, the unit heals 5 hit points. The unit's hit points cannot exceed the next highest attrition number.
- **Use Tactical Knowledge (Commander Only)** — By spending three swift actions, the commander can give the unit a tactical advantage. After spending the third swift action, make a DC 30 Knowledge (tactics) check. If successful, the commander can grant a single extra standard action to any other character filling a role in the unit. If the commander is the only character filling a role in the unit, the action has no effect.

### 2.16 Move / Swift / Full-Round / Reactions

- **Move (Commander Only)** — The commander can move the unit up to its speed as a move action.
- **Disband Unit (Commander Only / swift)** — The commander can disband the unit as a swift action.
- **Hard March (Commander Only / full-round)** — Move the unit up to 4 times its speed. The unit is flat-footed until the beginning of the commander's next turn. An Attack Leader cannot order the unit to make attacks until the end of the commander's next turn.
- **Disband and Reform Unit (Commander Only / reaction)** — When a unit disbands, as a reaction, the commander of an adjacent unit can order that unit to disband also and reform with the other unit as a new unit. Any heroes or models/characters must rejoin the unit as a move action on their next turn (except for the commander, who automatically transfers).

### 2.17 Special Mass Combat Rules

- **Cover and Concealment** — Units can gain cover and concealment just as characters do. Determine cover or concealment as normal for an attacker targeting a unit in a particular square.
- **Falling Vehicles** — When a flying vehicle or vehicle unit is disabled (but not destroyed) in mass combat, the vehicle falls to the ground and might damage ground units. At the beginning of a disabled or uncontrolled flying vehicle's turn, that vehicle crashes into the ground in the square it occupies. All nonflying units in that square take damage equal to collision damage for a vehicle of that size.
- **Orbital Bombardment** — Combatants in a ground battle can be devastated by capital ships in orbit above the planet. As a standard action, the commander of a capital ship can order a single weapons system to aim at a single square on a mass combat battlefield. The square is considered to be at long range for the capital ship, and the ship must make an attack roll against a Reflex Defense of 10 to hit the target square. If successful, all units in that square take normal weapon damage for that weapon system, or half damage on a miss. That ship cannot make any other attacks until the beginning of the commander's next turn. **Orbital bombardment should be used by the GM only as a means of making a mass combat encounter more dangerous.** A single shot from a capital ship weapon is usually more than enough to destroy a unit, so orbital bombardment should not be used lightly. Orbital bombardment should occur only if the needs of the adventure require it rather than as a means for resolving combats.
- **Weapon Emplacements** — Treated as vehicles for statistical purposes, but immobile and gunner-controlled. Examples include sonic antipersonnel cannons, antivehicle cannons.

### 2.18 Combining Mass Combat with Battlefield Encounters

The book emphasizes that combining mass combat with individual battlefield encounters can lead to exciting scenes mirroring those of the Star Wars saga. Three integration patterns are documented:

1. **Battlefield encounters trigger smaller encounters** — heroes in a mass combat unit move adjacent to or into the same square as an opposing force; they begin a battlefield encounter. If they emerge victorious, they gain favorable circumstances on their unit's next attack roll.
2. **Heroes leave the unit for a side mission** — heroes might be charged with completing several battlefield encounters while the mass battle takes place around them. Heroes are not part of any unit, but each time they complete an objective, it triggers a special effect on the battlefield.
3. **Simultaneous battles** — heroes control two encounters (one as hero/NPC, one as part of a unit). For example, the heroes might be part of a unit but also take control of a Republic Commando squad with a special mission to disable a shield generator. Initiative is rolled for both battles; mass combat encounter and battlefield encounter progress concurrently.

### 2.19 Translation Rules: Saga → WEG D6

For SW_MUSH implementation in `weight_of_war_design_v1.md`, these are the structural transforms to bridge the Saga abstractions to D6:

| Saga Concept | D6 Mapping |
|---|---|
| **Hit points × 4** | Use unit's structural strength as the wound stock; in D6, multiply the base creature's wound capacity by 4 (or use Vehicle scale wound stock if base creature has none). |
| **DR 15** | Apply as a flat damage reducer to the unit, similar to vehicle armor in D6. |
| **Damage threshold = Fort + 50** | In D6, replace with a "stagger threshold" pegged to the unit's Strength roll + a fixed scaling number. |
| **Attrition (3 steps below hp total)** | Use directly — track as a wound condition track. Each attrition step crossed = persistent −1D to all unit rolls. |
| **CL** | Replace with a unit power rating derived from base creature's skill dice + numeric modifiers for size and equipment. |
| **Starship-scale squares** | Use SW_MUSH's existing zone abstraction (per architecture v33). |
| **Defenses (Reflex / Fortitude / Will)** | Replace with WEG difficulty numbers for each unit. Reflex → "to hit" difficulty; Fortitude → resilience for bombardment; Will → morale/fear difficulty. |
| **Roles (Commander / First Officer / Attack Leader / Comms / Medic)** | Carry over verbatim — these are role abstractions, not Saga mechanics. PCs filling roles get +1D bonus to relevant unit actions. |
| **Talents / Feats** | Skip entirely — D6 character abilities use skills/specializations, which map differently. |
| **Standard Actions framework** | Carry over the *list* of available standard actions (Aid Another, Charge, Fight Defensively, Tactical Knowledge, Provide Medical Assistance, Hard March, Disband, Disband and Reform). Resolve each via WEG skill checks instead of d20 rolls. |
| **Orbital Bombardment** | Carry over the rule that capital ships can target unit squares; use existing WEG capital-ship damage rules. Keep the GM-restraint guidance verbatim. |

These are mappings, not a full design. A complete D6 mass-combat ruleset is the deliverable of `weight_of_war_design_v1.md`; this section provides the patterns to build on.

---

## §3. Decline of the Jedi & Campaign Themes 📖
**Maps to:** `clone_wars_director_lore_pivot_design_v1.md`, `cw_tutorial_chains_design_v1.md`, atmospheric tone for the era pivot generally.

These are GM-facing campaign themes — narrative and atmospheric, no rules. Useful for Director AI lore handling and tutorial chain content.

### 3.1 Decline of the Jedi

The Clone Wars dwindle the Jedi Order nearly to the point of extinction. The decline begins slowly before the war but accelerates sharply at Geonosis (the opening battle), where dozens of Jedi die. As the war progresses, more Jedi are killed than are raised to knighthood. By the time of Order 66, the Jedi are significantly fewer than at the start of the war.

**Two specific campaign techniques** the book recommends for showing this decline:

1. **The Dwindling Jedi Campaign** — Early adventures feature heroes regularly receiving missions from Jedi Masters, encountering Jedi Knights on the battlefield, helping Padawans escape trouble. As the campaign progresses, the GM gradually reduces the number of Jedi shown up in the campaign. Major NPC Jedi die; remaining Jedi are sent away to distant systems beyond the heroes' reach. By the time the heroes reach the highest levels, only a small number of Jedi — at most — are actively visible in the campaign.

   The contrast between the campaign's start (Jedi everywhere) and its end (Jedi a dying breed) becomes thematic on a regular basis.

2. **The Masterless Padawan** — Jedi heroes in a Clone Wars game lose their Jedi Master. Either the Master dies on the battlefield, is presumed dead, or otherwise is taken from them. A Clone Wars campaign that starts at low level can begin with Jedi heroes as Padawans whose Masters have died or been otherwise separated. Left to find their own way, Padawan heroes are confronted immediately by the fortunes of the Jedi: if that Padawan then makes contact with the Jedi Council, the Council might assign that Padawan to the company of other heroes (such as a Republic soldier or well-known Jedi Knight) until such time when another Jedi Master can continue the Padawan's training. Alternately, a Padawan might be entrusted to the care of a more Jedi Knight — as Ahsoka Tano is entrusted to Anakin Skywalker just a short time after his Knighting ceremony. This places the hero under the tutelage of a Jedi who is not yet ready to truly train the Padawan.

3. **Order 66** — "The Order given by Supreme Chancellor Palpatine to wipe out the Jedi" can be tricky because it represents a major setting shift. When Palpatine issues Order 66, the Clone Wars suddenly come to an end, and within a brief time the Empire rises and the Dark Times begin. However, using Order 66 in a campaign gives the GM a chance to build up to a single climactic event that is prominent in *Revenge of the Sith*. For campaigns taking place during the Clone Wars, Order 66 should probably be one of the last major events in the campaign. Jedi heroes in the company of clone troops during Order 66 must deal with sudden betrayal (which can surprise players if they do not know it coming). The scenario can also be obscured if any of the heroes have clone trooper followers, as formerly loyal allies that have only known them through the war might suddenly turn on them. Gamemasters planning to use Order 66 should be careful: over the course of the Clone Wars campaign, GMs should be mindful of how much information as to how close, or how far away, Order 66 is. Additionally, after the Order 66 event Jedi become outlaws, and Jedi heroes quickly find themselves hunted and cut off from the resources they have come to rely on from the Republic, radically altering the feel of the campaign. **Order 66 represents the final blow in the collapse of the Jedi Order, and it should be treated as either a major shift in the campaign's tone or as one of the final events leading to the climax of the campaign.**

### 3.2 Rampant Corruption

By the time the Clone Wars begin to tear the galaxy apart, the Republic has already been steeped in massive corruption for decades, even centuries. In fact, corruption in the Republic allowed Palpatine to maneuver his way into becoming Supreme Chancellor — a climate before the outbreak of the Clone Wars. Similar corruption allowed him — in the guise of Darth Sidious — to manipulate the Separatists into engaging the Republic in an open war. In a Clone Wars campaign, the heroes are likely to encounter corruption at every turn, and those in positions of power can never be truly trusted, for they might have their allegiances bought by enemy factions. Politicians sell their votes; corporate leaders disregard the basic rights of their employees; and security forces turn a blind eye to crime and violence all out of greed, that permeates the Republic during this time.

**Heroes are likely to encounter (or even be put in conflict with):**
- corrupt individual politicians, military officers, or security officers
- military officers selling substandard weapons
- military officers endangering not only the war effort but also the soldiers on the front lines
- corrupt officers blackmailing or bribing the heroes for personal gain
- corrupt Senate or planetary government officials
- corruption *within* the Confederacy as well — even Separatist leaders can be bribed by Republic agents or Sith

Greed can be exploited as a tool — heroes might use the corruption of the enemy to their advantage, paying their trade-while-draining-credits-from-corrupt-officials-on-both-sides.

> *"Greed can be a powerful ally."* — Qui-Gon Jinn

### 3.3 Villains

Major Clone Wars villains: Count Dooku, General Grievous, Durge, Asajj Ventress, General Loathsom, and others. The book's design notes for villains:

- **Dehumanization** — most Clone Wars villains are distinctly dehumanized. Villain physical appearance is often a thinly-veiled metaphor: General Grievous (cyborg, unnatural movement), Asajj Ventress (twin Sith lightsabers, frenzied appearance), Durge (cybernetic body, layers of humanity stripped away). High-profile villains use more than just frightening stat blocks; their appearance signals the villain's degradation from humanity.
- **Powerful Personality** — strong personality reveals/reasserts itself throughout the campaign. Count Dooku is iconic as a villain who sees Sith legacy; Asajj Ventress is more than just a pair of lightsabers. Players should encounter villains whose strong personalities reverberate in the campaign.

### 3.4 Militarization

The onset of the Clone Wars necessitates that various planets shift their peaceful, prosperous, and civilized ways behind and embrace militarization to survive. Worlds that have not seen major conflicts for thousands of years become central to the war, and more than just infrastructure must change if those worlds want to survive. A Clone Wars campaign brings with it an aspect of growing military importance. Few worlds are exempt from this: GMs have several options for highlighting militarization in their campaigns:

- Throw the heroes directly into a battle between the Republic and the Confederacy.
- Place the heroes more subtle: have them witness the launch of a Republic flotilla from a staging point on an Outer Rim world.
- Convert civilian assets into military assets — research hospitals retrofitted into weapons fabricators, droid starfighters being used to manufacture AT-TEs, refining computers for droid starfighters.
- Civilian rescues — heroes rescue former Republic citizens trapped behind enemy lines.

> *"Greed can be a powerful ally."* — Qui-Gon Jinn (italics in original)

---

## §4. Force-Using Traditions 📖
**Maps to:** `force_resonant_landmarks_design_v1.md`, `clone_wars_director_lore_pivot_design_v1.md` (lore-only)

The Jedi are not the only Force-using tradition in the galaxy during the Clone Wars. Three named traditions are detailed here as **lore reference**. These are NOT alternative Force Powers systems for SW_MUSH — `Guide_08_Force_Powers` is canonical. These are atmospheric/world-building entries for use in landmarks, NPCs, and quest content.

### 4.1 The Bando Gora

A **dark-side cult** that drifted away in the Inner Rim, tucked away on the moon Kohlma near the Hyssano River system. Originally a peaceful Kessrina-located religious sect, the Bando Gora's presence in the galaxy would have gone unnoticed for the most part if not for the emergence of a band of ruthless, zealots-turned-killers calling themselves the Bando Gora.

**Origin:** Shortly after the Battle of Sulafassan, the Bando Gora gained the attention of the Galactic Republic, which swiftly requested Jedi intervention against the criminal faction. Even the mighty Jedi Order underestimated the sect's power and lost nearly every member they sent against the Bando Gora. The only known survivor is Komari Vosa, who abandoned her teachings and succumbed to the dark side of the Force. To escape her bonds, eventually becoming the new leader of the Bando Gora.

**Operations:** The Bando Gora's reach extends into many worlds and organizations, subsuming members and devouring countless people. Those that do not surrender to Bando Gora rule are killed or captured and brutally tortured. Companies that refuse to follow the cult's lead find their leaders assassinated.

**Tactics:** The Bando Gora supplements its ranks through the recruitment and abduction of skilled warriors and enduring companies; uses a highly potent system of death stick that is sometimes used as a brainwashing agent. The opioid cells all across the galaxy and is particularly popular with those who have ties to the underworld.

**Initiation Ritual:** After joining the cult, members of the Bando Gora must undergo a ritual that transforms their appearance, scarring them and making their flesh skin pale and glowing eyes. Leaders of the organization are known to don frightening masks and carry staffs that shoot green balls of fire.

**Membership rule:** Anyone with the Force Sensitivity feat and a Dark Side Score of 1 or higher can become a member of the Bando Gora.

### 4.2 The Believers

Rising to prominence shortly after the Battle of Naboo, the Believers, based in the Cularin system, are a cult of Force-sensitive beings whose members devote their energies to studying and embracing the dark side of the Force, with the intent of following the destinies and customs of the ancient Sith that existed before Darth Bane. Rejecting Bane's Rule of Two, the Believers seek to expand their numbers to eventually challenge the Jedi Order.

**Origins:** During the Clone Wars, Jedi stumbled upon the cult's existence and slowly began to whittle down their numbers. As their numbers swell, the Believers retreat into a hidden cult-state somewhere on the same planet known as the Mortuum (the home of the dark side cult and increasing in size). At the cult's height, the Believers attack the Sith Temple of Almas and go underground for a short time.

**Operations:** The Believers return later, when the Ossiform (a Sith artifact) attempts to project itself from a group of agents that discover its connection. The shadow turns out to be Lord Vamuk of the Cularin system, who beats the Jedi on the run, but is stopped by a captain incident and turned to stone. With their plans foiled, the Believers abandon the Sith Temple at Almas and go underground for a short time. The Believers return later, when the Ossiform, a Sith artifact, attempts to project itself from a group of agents that discover its connection. To protect itself from a group of agents that discover its connection.

**Membership rule:** Anyone with the Force Sensitivity feat and a Dark Side Score of 1 or higher can become a member of the Believers, by being accepted as an apprentice by a Force adept or Force-disciple member of the cult.

### 4.3 The Korunnai

The Korunnai are a nomadic tribe of Humans from the Galactic Rim. The home planet, Haruun Kal, the only planet of the Al'Har system. Not so much a formal Force-tradition like the Jedi, the Korunnai live in the harsh jungles that grow above the layers of lethal gases that fill the planet's lowlands. They maintain their existence by following herd animals called grazers, which provide them with sustenance and the materials they need to survive. In addition to their keen survival skills, members of the Korunnai have a strong connection to the Force.

Life is not so simple for the Korunnai as they also fight a bloody war against the planet's other sapient inhabitants, the Balawai. Originally off-worlders, the Balawai invade the jungles the Korunnai call home and harvest the natural resources to sell in the galaxy's markets for profit, including spices and exotic woods. Their unsympathetic behavior quickly creates enmity between the two peoples that erupts into war just as well into the Clone Wars. When the Separatists back the Balawai by providing them with updated weapons and technology to protect the planet's only spaceport, the Republic has too few troops to help in the conflict and sends in a single Jedi — Lord Bilbous — to back the Korunnai. The conflict between the Korunnai and Balawai escalates to such an extent that the Jedi Master is mentally scarred from the experience.

**Cosmology:** The Korunnai refer to the Force as *pelekotan*, interacting with what they believe to be the "jungle mind" as a way to survive the war is to use their hostile world. They see *pelekotan* as a dark force that rules the darkness of the jungles and challenges those that tap into its energy. Sometimes, *pelekotan* presents its challenges in ways that cause physical ailments to its users, and at other times, those challenges can cause mental impairments. Jedi believe that users of *pelekotan* equally use both the light side and the dark side of the Force, but the Korunnai merely believe that they are all part of the same entity. Some Jedi feel that *pelekotan* is just another name for the Living Force.

**Membership rule:** Anyone with the Force Sensitivity feat can become a member of the Korunnai.

---

## §5. Jedi Order Structure 📖
**Maps to:** `padawan_master_system_design_v1.md`, `jedi_village_quest_design_v1.md`, `jedi_village_dialogue_authoring_design_v1.md`

Pure lore/structure content for Jedi Order modeling. NPC stats and lightsaber forms are not extracted (Saga numbers; out of scope per WEG-focus).

### 5.1 Order rank progression

```
Youngling (Initiate)
  ↓ at appropriate age, two paths split:
  ├─→ selected by a Jedi Master → Padawan
  │    ↓ pass the Trials
  │    Jedi Knight
  │      ↓ expanded knowledge & understanding of the Force
  │      Jedi Master
  │        ↓ distinguished service
  │        Council seat (one of several councils)
  │
  └─→ not selected → Jedi Service Corps (lifelong service)
```

Younglings undergo formal education in the Coruscant Temple. At the appropriate age, they are either selected by a Jedi Master to become a Padawan, or assigned to one of four branches of the Jedi Service Corps. Padawans continue their education under the direct tutelage of their Jedi Masters until they pass the trials to become a Jedi Knight. Jedi who expand their knowledge and understanding of the Force might reach Jedi Master, and those who serve the Order with distinction might be offered a seat on one of the councils that oversee the actions and activities of their fellow Jedi Knights and Jedi Masters.

### 5.2 The Jedi Service Corps

Younglings who pass the age to begin training as a Padawan without being chosen by a Jedi Master are sent to the Jedi Service Corps. The Service Corps has **four separate branches**, each serving the Republic and the Jedi Order according to its designated purpose:

1. **Agricultural Corps (AgriCorps)** — supports the Republic's agricultural administration. Members serve at farms and tend to crops/livestock. The primary goal is to support the Republic's Agricultural Administration, which oversees the production and processing of foodstuffs throughout the Republic. Most members serve on or near Coruscant; some are sent to other worlds. Use of the Force is restricted to tending the crops and livestock under their care, primarily because they have not learned anything beyond these basic skills at this point.

2. **Educational Corps (EduCorps)** — provides instruction to the disadvantaged on countless worlds. Armed with the philosophy that knowledge of the universe and those who dwell in it increases one's understanding of life in the galaxy, EduCorps scholars strive to learn all they can within the first few years of membership to prepare themselves to teach that knowledge to their future students. EduCorps members also study the worlds and cultures they visit, recording their experiences in the libraries located within the Jedi Temple on Coruscant.

3. **Exploration Corps (ExplorCorps)** — primarily travels on missions to explore the Unknown Regions of the galaxy, charting new star systems and discovering new civilizations and races. The ExplorCorps also works in conjunction with like-minded organizations, such as the Intergalactic Zoological Society. ExplorCorps takes its students from other branches of the Jedi Service Corps. Not surprisingly, the young Jedi who are assigned to the ExplorCorps are considered by their peers to be "the lucky ones." The primary purpose of the ExplorCorps, however, is to seek out new worlds and civilizations in the galaxy. Knowledge of their discoveries is catalogued in the Jedi Archives for all to learn.

4. **Medical Corps (MedCorps)** — tends to the medical needs of Republic citizens throughout the galaxy. Members are responsible for maintaining the infirmary located in the Jedi Temple on Coruscant, which is connected to the expansive Galactic City Medical Center via a dedicated underground transport tube. MedCorps members can also be found at medical facilities throughout the galaxy, bestowing relief in times of crisis or instructing non-Force-using personnel in new methods to care for their patients.

While Service Corps members usually live the rest of their lives in service there, Padawans continue their education under the direct tutelage of their Jedi Masters until they pass the trials to become a Jedi Knight.

### 5.3 Specialized Jedi Knight roles

Jedi who achieve knighthood and have a natural talent in certain areas might choose to serve the Jedi Order in ways that allow them to use such talents to the best of their ability. Many areas are available, and the ones listed in the chapter are a sample:

- **Jedi Archivist** — Jedi who prize knowledge over other things. They study many areas of knowledge so others might learn. Most archivists remain close to the temple archives on Coruscant or Ossus, others travel to gain more information about the galaxy, its inhabitants, and its cultures, continually increasing their common pool of knowledge. Archivists also work with ExplorCorps, searching for lost civilizations or exploring and studying newly discovered star systems. During the latter days of the Republic and into the Clone Wars, Jedi archivists become fewer in number. Older Jedi believe that the younger members of the Jedi Order do not have the patience to take on the role of an archivist, choosing other roles deemed more important to the Jedi Order at that time.
- **Jedi Healer** — like many religions and Force-using traditions in the galaxy, the Jedi Order values life and its preservation, and life in turn creates the Force. To that end, the ability to channel the Force to heal is one of the most prized powers a Jedi can possess. Although many Jedi learn to treat wounds to some extent, few Jedi devote their lives to the healing arts. Those that specialize in this area find that their understanding of the Force increases when they heal the sick and tend to the wounded. Jedi healers are experts in the field of medicine. They spend a majority of their time tending to patients and expanding their understanding of the Force by studying its connection with all living things. Since anger and aggression hamper their healing abilities, Jedi healers are less likely to be tempted by the dark side of the Force.

Other specialized roles named in the book (not extracted in detail): **Jedi Investigator, Jedi Sentinel, Jedi Watchman, Jedi Battlemaster, Jedi Shadow, Jedi Diplomat**. Wookieepedia covers each in depth.

### 5.4 The Jedi Council(s)

Jedi who serve the Order with distinction might be offered a seat on one of **several councils** that oversee the actions and activities of fellow Jedi Knights and Jedi Masters. The book confirms multiple councils exist (not just the High Council), but specific council names and remit are detailed elsewhere — Wookieepedia lists at least: **High Council, Council of First Knowledge, Council of Reconciliation, Council of Reassignment**.

---

## §6. Galactic Gazetteer (Planet Index) 📖
**Maps to:** `from_dust_to_stars_design_v2_clone_wars.md`, `world_data_extraction_design_v1.md`

The book includes a Galactic Gazetteer of 18 Clone Wars-relevant planets plus a "Planetary Updates" section. **Per WEG-focus discipline, individual planet entries are not transcribed here — they're available via Wookieepedia at higher quality and currency.** This section serves as an **index** of which CW-era worlds the Saga book covers, so future content authors know where to look:

| Planet | Notable for |
|---|---|
| **Cato Neimoidia** | Trade Federation/CIS-aligned bridge cities; iconic Clone Wars battlefield |
| **Christophsis** | Crystalline-architecture world; major Republic battle |
| **Geonosis** | CIS war-industry homeworld; opening battle of the Clone Wars |
| **Glee Anselm** | Watery world, Nautolan homeworld (Kit Fisto) |
| **Iktotch** | Iktotchi homeworld; mountainous, harsh weather |
| **Kalee** | Kaleesh homeworld (Grievous's species); martial culture |
| **Kamino** | Cloning facility; clone trooper homeworld; off-galactic-grid |
| **Kerkoidia** | Kerkoiden homeworld; aligned ambiguously |
| **Malastare** | Dug homeworld; Pod-racing; CIS-leaning |
| **Mustafar** | Volcanic; Techno Union mining; future Vader retreat |
| **Muunilinst** | InterGalactic Banking Clan HQ; finance; CIS funder |
| **Nelvaan** | Snow-covered world with isolated Nelvaanian natives (Techno Union research site) |
| **Polis Massa** | Asteroid medical/research base (canon-significant for Padmé's death) |
| **Sembla** | (Rare/lesser-known) |
| **Skako** | Techno Union homeworld |
| **Teth** | Cliff-monastery world; *Clone Wars* film setting |
| **Toydaria** | Toydarian homeworld (Watto's species); neutrality-leaning |
| **Utapau** | Sinkhole-cities; Pau'an + Utai species; Grievous's last stand |

The "Planetary Updates" section (book pages 115–119) provides Clone Wars-era updates for **Tatooine** and other previously-detailed worlds — relevant for any retained Mos Eisley content if SW_MUSH keeps the Tatooine zones during the era pivot.

**Recommended workflow for planet content:** When `from_dust_to_stars_design_v2_clone_wars.md` or `world_data_extraction_design_v1.md` needs detail on a specific Clone Wars planet, pull the corresponding Wookieepedia article rather than transcribing this book's entry — the wiki is more comprehensive, regularly updated, and better-formatted for markdown extraction.

---

## §7. What's deliberately NOT here

If a future Claude session looks at this extract and thinks "I should add the Saga rules for X to SW_MUSH," **the answer is no, by Brian's standing directive**. The following Saga content is in the source PDF but has been deliberately excluded from this extraction to preserve WEG focus:

- **Species Chapter** (Dugs, Gen'Dai, Iktotchi, Kaleesh, Kaminoans, Kerkoidens, Nautolans, Nelvaanians, Vurks) — Saga species traits don't translate; use WEG GG12 (Aliens) or Wookieepedia for D6-compatible alien stats.
- **Heroic Traits Chapter** (Jedi/Nobles/Scoundrels/Scouts/Soldiers tracks, Skills, Feats, Followers as full mechanics) — competes with WEG character creation.
- **Prestige Classes** (Droid Commander, Military Engineer, Vanguard) — Saga-specific.
- **The Force Chapter** (Force Powers, Talents, Techniques, Secrets — *except* the three Force-Using Traditions, which are pure lore in §4) — would dilute `Guide_08_Force_Powers`.
- **Equipment and Droids Chapter** (melee weapons, ranged weapons, armor, equipment, droids stat blocks) — competes with WEG equipment.
- **Starships Chapter** (Space Transports, Starfighters, the Phoenix Hawk, etc.) — competes with WEG ships and `Guide_05_Space_Systems`.
- **Influential Figures stat blocks** in Chapters IX (Jedi), X (Republic), XI (Confederacy), XII (Fringe Factions) — names and roles are useful, but the stat blocks are Saga-numbers. For NPCs the project actually needs in code, generate D6 stats from WEG sources.
- **Republic / CIS / Jedi Vehicles and Starships** subsections — competes with WEG vehicles.
- **Beasts** (Chapter XII: Fringe Factions) — competes with WEG creature stats.

---

## Source disposition

Once this extraction is uploaded to project knowledge, the source PDF (`SW_Saga_Clone_Wars_Campaign_Guide_compressed.pdf`, ~15 MB) does **not** need to live in the project. Everything from this book that's relevant to SW_MUSH within the WEG-focus discipline is captured above.

*End of extraction v1.*
