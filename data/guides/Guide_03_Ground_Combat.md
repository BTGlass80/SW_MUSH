---
category: combat
order: 1
summary: "Turn order, attack and damage rolls, cover and range, blasters, melee, and grenades."
tags: ["combat", "fighting", "attack", "damage", "blasters", "melee", "initiative"]
---

# Ground Combat

**Parsec — WEG D6 Revised & Expanded**

---

## How to Read This Guide

Combat is the densest system in the game. It's also the system you'll touch the most often, so it's worth taking the time to understand. This guide covers the full round structure, every action you can declare, how to-hit and damage work, the cover and range systems, melee, grenades, fleeing, posing, NPC AI, the death sequence, and the web client's combat panel.

If you only have ten minutes, read **§1 The Round**, **§3 Actions**, and **§5 Damage**. That's enough to play a competent first fight. The rest is what makes you good — when to full-dodge versus when to aim, how to position for cover, when to spend Character Points versus when to bank them, what NPC behaviors to expect from B1 droids versus Geonosian warriors versus Hutt enforcers.

This is the foundational combat-rules layer. It assumes you've already read the [Core Mechanics](#/guide/weg-d6-core-mechanics) guide — dice pools, the Wild Die, difficulty numbers. If those phrases don't mean anything to you yet, start there. Combat is gated by zones (see [Security Zones](#/guide/security-zones)) and feeds directly into the wound and death system (see [Medical & Death](#/guide/medical-death)). Force-sensitive characters layer Force powers on top of everything below (see [Force Powers](#/guide/force-powers)). The Clone Wars setting also means you'll be fighting a specific range of opponents: B1 and B2 battle droids on Geonosis, Hutt enforcers in Mos Eisley and Nar Shaddaa, Trandoshan thugs in the Coruscant Underworld, Republic clones in rare PvE-vs-Republic scenarios. Each archetype fights differently — knowing the patterns saves your life.

---

## 1. The Round

Combat is turn-based, organized into rounds. Each round has four phases that always run in the same order:

**Phase 1 — Initiative.** Everyone in combat rolls Perception. Highest goes first. The game displays the turn order.

**Phase 2 — Declaration.** Starting from lowest initiative and going up, each combatant declares what they'll do this round: attack a target, dodge, parry, aim, take cover, flee, use a Force power. You can declare multiple actions in one round, but every extra action imposes a **−1D penalty to all of your rolls** that round. You can also commit your entire round to defense — see "full dodge" and "full parry" below.

**Phase 3 — Resolution.** Actions resolve in initiative order (highest first). The game rolls all the dice, applies damage, and narrates results. Each action produces a two-line output: a **bold story line** ("▸ Kaelin fires at the B1 droid — HIT! Wounded!") and a **dim mechanics line** showing the exact rolls and math behind it. You can see the underlying dice without them cluttering the narrative.

**Phase 4 — Cleanup.** Stun timers tick down. Mortally wounded characters make their death rolls. Fled or dead combatants leave the fight. If only one side remains, combat ends. Otherwise a new round begins at Phase 1.

The round structure is consistent. Once you know the four phases, you know the rhythm of every fight — including big multi-combatant battles. The phases just take longer when there's more going on. A two-character cantina duel in Mos Eisley resolves a round in seconds; a five-on-five clone-vs-droid engagement on the Geonosis surface can take several minutes per round once everyone has declared. The web client shows you exactly where in the phase cycle the fight is, so you don't have to guess whether you should be declaring or waiting.

### What gets carried across rounds

Some state persists between rounds and some doesn't:

| State | Persists? | Notes |
|---|---|---|
| Wound level | Yes | Healthy → Stunned → Wounded → ... stays unless healed |
| Stun timers | Yes (until they tick out) | Each stun has a 2-round countdown |
| Cover level | Yes (until you attack or move) | Attacking degrades cover to 1/4 |
| Aim bonus | Yes (resets after you fire) | Stacks to +3D over multiple rounds |
| Force Point active | No | One round per spend |
| PvP consent timer | Yes | 10 minutes from accept |
| Declared actions | No | Cleared at the start of each declaration phase |

The persistence model is what makes longer fights tactical rather than chaotic. If you full-dodge in round 2, then attack in round 3, you didn't waste your effort — you survived round 2's incoming shots, and you go into round 3 with a clean slate to attack. Cover stays put until you give it up. Aim stacks across rounds.

---

## 2. Initiative

At the start of every round, every combatant rolls **Perception** (with wound penalties applied). The results sort the turn order — highest acts first during resolution. Ties are broken by sort order, so the same character always wins identical ties to themselves.

You don't type anything for initiative. The game rolls it automatically and shows you the order:

```
Turn order: Kaelin (18) → Tarn (15) → B1 Battle Droid (12) → Hutt Enforcer (9)
```

Initiative matters more than people expect. The first character to act in resolution gets to apply their wound (or kill) before the target gets to fire back. A character at low Perception in a fast fight may never get to act before being incapacitated. Investing in Perception isn't just about social skills — it's a combat stat. In a Clone Wars context this is particularly relevant against Republic Commandos, who have Perception 3D+2 and routinely outroll player characters in opening initiative.

### Tactical tip: re-rolling initiative

Some Force powers (Sense-tree powers like Combat Sense) can boost your Perception for the round in which you activate them. If you suspect you're in a fight where initiative matters and you have a Force-sensitive in the party, that's the kind of round to spend a Force Point on — being first in resolution often decides who walks away.

---

## 3. Declaring Actions

When the declaration phase opens, the game waits for every combatant to declare at least one action. The available actions:

| Command | Action | Notes |
|---|---|---|
| `attack <target>` | Attack a specific target | Optional: `attack droid with melee combat` |
| `dodge` | Normal dodge | Counts as an action; multi-action penalty applies |
| `fulldodge` | Full dodge | Entire round on defense; no other actions allowed |
| `parry` | Normal melee parry | Counts as an action |
| `fullparry` | Full melee parry | Entire round on defense; no other actions allowed |
| `aim` | Aim at next target | +1D to your next attack, stackable to +3D |
| `cover` | Take cover | Uses the room's available cover (see §7) |
| `flee` | Attempt to escape | Opposed Running roll vs. fastest opponent |
| `pass` | Do nothing | Generates a generic auto-pose |

**Multi-action declarations.** You can declare more than one action in a single round — attack and dodge in the same turn, for instance. Every extra action imposes **−1D on every roll you make that round**, including the first one. A character with 4D in Blaster declaring "attack + dodge" rolls both at 3D. Three actions is 2D for everything. The penalty doesn't favor the original action; it spreads evenly.

This is the central tradeoff of every combat round. More actions means more things you can do but more chances to whiff. Skilled combat is largely about knowing when to commit to one action with full dice and when to spread thin. Against B1 Battle Droids (low individual stats but they come in numbers), single-attack rounds are usually correct — your full-dice attack one-shots them. Against a Republic Commando or a Trandoshan brute with 6D Brawling, the calculation changes — you may need to dodge AND attack to survive, even at the dice penalty.

**Full defense.** `fulldodge` and `fullparry` must be your *only* action. You can't full-dodge and also attack. In exchange, the defense roll behaves very differently:

- A normal dodge roll **replaces** the base difficulty for incoming ranged attacks. If you roll high, you're safer than the base difficulty would have made you. If you roll low, you might actually be *easier* to hit than if you hadn't dodged at all.
- A full dodge roll **adds to** the base difficulty. Whatever your dodge roll comes out to is added on top of the range difficulty. Even a low full-dodge roll is still net-positive defense; a high one makes you nearly untouchable.

The same distinction applies to `parry` versus `fullparry` for melee. Full defense is the right call when you're outnumbered or wounded and just need to survive the round. It's also a strong call in the first round of a fight you didn't expect — if a Mos Eisley cantina brawl breaks out and you weren't ready, full-dodging round 1 buys you a round to assess before you commit.

**Character Points on attacks.** `attack droid cp 3` spends 3 Character Points on the attack roll. The CP dice are rolled *after* your normal attack dice — you see your initial result, then decide whether to spend CP to push it over the edge. CP dice explode on 6s (like the Wild Die) but have no complication on 1s, so they're always purely beneficial. The R&E rule is that CP and Force Points can't be used in the same round; the game enforces this.

When to spend CP: when the roll is close to the difficulty and the consequences of missing matter. Killing the last B1 in a patrol so it can't sound an alarm is worth 2 CP. Landing a hit on a fleeing bounty target before they round the corner is worth 3 CP. Pushing a marginal dodge over the threshold to survive a Republic Commando's headshot is worth as much as you've got. Don't burn CP on rolls that succeed or fail by wide margins — only on the close ones.

**Soak CP.** `soak 2` pre-declares 2 CP to add to your Strength resistance roll *if* you get hit. Max 5 per the R&E rule. The CP is only spent if damage actually lands, so it's a smart precaution rather than a guaranteed cost. Pre-declaring soak before a round where you expect to take fire — say, you've drawn the aggro of a Droideka and you're going to be in its line of sight — is one of the highest-value uses of CP in the game.

---

## 4. Ranged Attacks

When you fire a blaster, bowcaster, or any other ranged weapon, your attack works like this:

**1. The range band sets the base difficulty.** Every shot starts with a target number based on how far you are from your target:

| Range | Difficulty |
|---|---|
| Point-blank | Very Easy (5) |
| Short | Easy (10) |
| Medium | Moderate (15) |
| Long | Difficult (20) |

Range is determined by the room geometry and the `range` command. Most cantina interiors are short-range throughout. Mos Eisley street fights can stretch to medium. Open terrain like the Jundland Wastes or the Geonosis surface routinely sees long-range fire — that's why sniping with `aim` matters so much in those zones.

**2. The target's dodge modifies the difficulty.** If they declared a normal dodge, their dodge roll **replaces** the base difficulty — which can backfire if they rolled low. If they declared a full dodge, their roll **adds to** the base. Dodge is rolled once per round and cached, so the same value applies to every incoming ranged attack on them that round.

**3. Cover adds more difficulty.** If they're behind cover, the game rolls extra dice and adds the total to the difficulty: +1D for quarter cover, +2D for half, +3D for three-quarters. Full cover blocks the shot entirely.

**4. You roll your weapon skill.** Your Blaster pool (or Bowcaster, or whatever) with all relevant modifiers applied: wound penalty, multi-action penalty, armor's Dexterity penalty (heavy armor makes you a worse shot), aim bonus from previous rounds, Force Point doubling if you spent one, plus any CP dice you spent on this roll.

**5. If your roll is greater than or equal to the total difficulty, you hit.** Then damage is rolled — see §5.

A hit looks like this in play:

```
  ▸ Kaelin fires at B1 Battle Droid with blaster — HIT — Wounded!
    (Roll: 18 vs Diff: Short(10) + Cover(1/2) 6 = 16 · Damage 14 vs Soak 9 → Wounded)
```

A miss is dimmer and less dramatic:

```
  Kaelin shoots at B1 Battle Droid with blaster — barely misses!
    (Roll: 12 vs Diff: Short(10) + FullDodge 8 = 18)
```

The first line is always the narrative. The dim parenthetical is the math. Both are shown so you understand exactly why the result came out as it did — no hidden modifiers.

### Worked example: Mos Eisley cantina brawl

You're a Human smuggler at 3D+2 Blaster, carrying a DL-44 Heavy Blaster Pistol (5D damage). A Trandoshan tough across the cantina decides he doesn't like your face and pulls a blaster pistol. Initiative comes out: him 14, you 11. He fires first.

His attack: 3D Blaster, short range (cantinas are mostly short). Diff is 10 + your cached dodge (you declared a normal dodge, rolled 9 — *replaces* the base, so total diff is 9). He rolls 13. Hit. Damage 4D = 12 vs your Strength 3D + Blast Vest 1D energy = 4D, you roll 11. Margin 1 — Stunned for 2 rounds. Bad start, but you're still up.

Your turn. You're at −1D from the stun (1 active timer × −1D), so effective Blaster is 2D+2. You attack, Diff is 10 + his cached dodge (he declared a normal dodge, rolled 7 — so diff is 7 because dodge replaces). You roll 12, including a Wild Die that exploded. Margin 5 — Hit. Damage 5D from the DL-44 vs his 3D Strength + 1D Blast Vest = 4D, you roll 16. Margin 6 — Wounded. He's at −1D for the rest of the fight.

Round 2 starts. You stun-timer ticks once (one round left). You're still at −1D. He's at −1D from wounded. You both declare attacks at reduced dice. Etc.

The fight runs another two rounds — you spend 2 CP on round 3 to push him to Incapacitated, he tries to flee in round 4 and fails the opposed Running roll, you put him down on round 5. Three minutes of real time, four to five rounds of fiction, a full cantina sequence. Welcome to Mos Eisley.

---

## 5. Damage and Wounds

When an attack hits, the game rolls the weapon's damage dice against the target's **resistance** (Strength + armor protection). The margin between damage and resistance determines what kind of wound the target takes:

| Damage Margin | Result |
|---|---|
| ≤ 0 | No Damage |
| 1–3 | Stunned (−1D, wears off after 2 rounds) |
| 4–8 | Wounded (−1D, persists until healed) |
| 9–12 | Incapacitated (out of the fight, unconscious) |
| 13–15 | Mortally Wounded (death roll each round) |
| 16+ | Dead |

A ranged attack rolls the weapon's flat damage code (a blaster pistol is 4D, a blaster rifle is 5D, a Wookiee bowcaster is 4D, and so on). A melee attack rolls **Strength + weapon bonus** — a 3D-Strength character swinging a Vibroblade (STR+3D) rolls 6D damage.

**Force Point interaction.** Spending a Force Point doubles your dice for the round. For melee damage, it doubles your **Strength** but *not* the weapon bonus. So that 3D-STR + 3D-Vibroblade character with a Force Point active rolls 6D STR + 3D weapon = 9D damage, not 12D. This is the R&E p52 rule and the game enforces it specifically.

**Armor.** Armor adds dice to your Strength when resisting damage. Clone trooper armor gives +2D energy / +1D physical (deliberately tuned the opposite of stormtrooper armor — clone phase-1 armor is better against energy weapons than against melee). A 3D-Strength clone resists a blaster bolt with 5D total but resists a vibroblade strike with only 4D. Most armors also impose a Dexterity penalty for wearing them, which reduces your effectiveness at shooting and dodging — so armor is a tradeoff, not a free upgrade.

Some specific armor profiles you'll see in CW play:

| Armor | Energy | Physical | Dex Penalty | Notes |
|---|---|---|---|---|
| Plain Clothes | +0 | +0 | None | Default for civilians and smugglers |
| Blast Vest | +1D | +1D | None | The everyman option |
| Padded Flight Suit | +1D | +1D | None | Spacer-typical |
| Clone Phase 1 Armor | +2D | +1D | −1D Dexterity | Republic standard issue |
| Mandalorian Beskar'gam | +2D | +3D | −1D Dexterity | Bounty hunter, very expensive |
| ARC Trooper Recon Armor | +1D+2 | +1D+1 | None | Lighter, faster, elite-only |
| Geonosian Chitin | +1D | +2D | None | Native species natural armor |

**Stun mode.** Blaster pistols (and many other blasters) have a stun setting. A blaster set to stun rolls damage normally, but any result more severe than Stunned is capped at "Stunned — Unconscious." You cannot kill someone with a stun blast, no matter how good your damage roll. This is what most arrest scenarios use — Coruscant Security Force shoots first and asks questions later, but they shoot on stun.

**Soak CP, again.** If you pre-declared `soak 2`, those 2 CP get rolled and added to your resistance total when you actually get hit. Up to 5 CP can be soaked per round. The decision is asymmetric — you spend CP only if hit, so soak-declaring is much cheaper than attack-CP-spending.

For what happens *after* you take serious damage — wound recovery, bacta tanks (rare in CW; field medics with bacta-patches are more common), the death sequence — see [Medical & Death](#/guide/medical-death).

---

## 6. Melee

Melee combat (fists, vibroblades, lightsabers) uses **opposed rolls** instead of a fixed difficulty. Your attack skill vs. their parry skill. Highest total wins.

The defense skill the game uses depends on what you're attacking with:

- **Brawling attacks** → defended by Brawling Parry
- **Melee weapon attacks** → defended by Melee Parry (or Lightsaber if the defender has it trained higher)
- **Lightsaber attacks** → defended by Lightsaber or Melee Parry (whichever is higher for the defender)

The R&E rules add two flat bonuses for equipment mismatches:

- An **unarmed defender** fighting an **armed attacker** gives the attacker **+10 to their roll total**. Trying to parry a vibroblade barehanded is a bad idea.
- An **armed defender** parrying an **unarmed attacker** gets **+5 to the parry roll**. Lightsabers and vibroaxes don't have trouble swatting away a punch.

If no defense is declared at all, the attacker rolls against the weapon's **listed melee difficulty** (Easy, Moderate, or Difficult, set per weapon). This lets you stab someone who's not paying attention without the game requiring them to defend — useful for sneak attacks and surprise rounds.

After a melee hit, damage resolves exactly as in §5 — STR + weapon bonus vs. STR + armor.

### Lightsabers are special

Lightsabers do **flat 5D** damage regardless of your Strength, and they **bypass most armor** (the blade cuts through Phase 1 clone armor as easily as through plain clothes; beskar is one of the few materials that can resist a lightsaber strike, and even then only briefly).

If you're a Padawan or fully-trained Jedi facing a non-lightsaber opponent, you have an extreme melee advantage. The reverse is also true — facing a lightsaber opponent without one of your own is essentially a death sentence unless you can stay at range. This is part of why Padawans get sent into messy ground engagements and why Hutt enforcers facing Jedi tend to fire from cover rather than close to melee.

### Worked example: a Geonosian arena duel

You're a Padawan with 3D Lightsaber. A Geonosian Warrior on the arena floor closes with a sonic pike (STR+2D damage, defended by Melee Parry). Initiative: you 14, Geo 12. You attack.

Your roll: 3D Lightsaber, opposed by their Melee Parry 2D+1. You roll 11. They roll 8. Margin 3, you hit. Damage 5D (lightsaber flat) vs their Strength 3D + Geonosian Chitin 1D = 4D, you roll 17. Margin 12 — Incapacitated in one swing. The lightsaber bypassed most of their chitin protection; even rolling decently on the soak side, they're done.

Round 2 starts but the fight is over. The arena crowd reacts. You disengage. Welcome to Geonosis.

---

## 7. Cover

Many rooms have **cover available** — crates, low walls, doorways, terrain, the rusted hulks of battle-droid wreckage. Use the `cover` command to take advantage of it:

| Cover Level | Bonus to Attacker's Difficulty | Feels Like |
|---|---|---|
| None | +0 | Standing in the open |
| 1/4 Cover | +1D | Peeking around a corner |
| 1/2 Cover | +2D | Behind a crate or wall section |
| 3/4 Cover | +3D | Barely exposed |
| Full Cover | Cannot be targeted | Hidden — but you can't shoot either |

The key rules to remember:

- **Cover level is room-capped.** Each room has a maximum cover level set by the builder. The Mos Eisley docking bays have plenty of cargo crates (cover_max = 3). The Coruscant Senate plaza has columns but they're spaced thin (cover_max = 2). The open Jundland Wastes mid-canyon have almost nothing (cover_max = 1, maybe 0). The room's `look` description usually tells you what's available.
- **Attacking from cover degrades your cover to 1/4.** You have to peek out to take the shot. So an aggressive shooter behind half-cover effectively loses most of their protection when they fire. Sniping with `aim` and rare shots is more cover-friendly than spraying every round.
- **Cover persists across rounds** until you attack or move out of the cover position. You don't have to re-declare it every turn.
- **Cover only protects against ranged attacks.** Hiding behind a crate doesn't help against a vibroblade. The melee combatant just walks around the crate. (This is why Jedi and Sith are so dangerous against blaster-only opponents — they close to melee and your cover stops mattering.)

### Tactical: when to take cover

- Round 1 of any unexpected fight, if cover is available — buys you assessment time.
- Whenever you're at 4D or less in your active combat skill and facing multiple shooters — the difficulty boost on incoming fire matters more than your action economy.
- Before declaring `aim` rounds — a sniper in 3/4 cover aiming for three rounds is the safest possible offensive setup.

When NOT to take cover:

- When your only viable target is also in cover and you need to close — cover doesn't help you advance.
- In melee-only encounters — wastes an action for zero benefit.
- When fleeing — `flee` is the better single-action choice; cover doesn't help you exit the room.

---

## 8. Fleeing

Type `flee` to attempt to escape combat. The game makes an **opposed Running roll** — your Running skill against the highest-initiative opponent's Running skill. Both rolls include wound and multi-action penalties.

Win the roll and you flee successfully — you're removed from combat during cleanup. Lose and you're stuck in the fight for at least another round. If no enemies remain by the time you declare, you flee automatically.

Fleeing is a legitimate tactical choice, not a failure state. A wounded character down to 2D in everything fleeing to find a medic is often the right move. A character at full health bailing on a fight just because they're outnumbered is also valid. The game doesn't shame you for running.

### Running in the Clone Wars

A few specific scenarios where fleeing is the correct read:

- **Republic Commando squad ambush.** Four ARC-tier troopers with 4D+ skills and military discipline. If you're solo and they've gotten the drop on you, run. Fight back later from cover with friends.
- **Droideka deployment.** Once a droideka unfolds its shield and starts firing, you cannot outshoot it — its shield negates most damage and its twin blasters out-DPS most player loadouts. Run, regroup, find an EMP grenade.
- **Mandalorian bounty hunter pursuit.** If a beskar-armored hunter has identified you specifically, you cannot win that fight head-on with a starting character. Run, lose them in the Coruscant Underworld levels, change your appearance, fight another day.
- **Geonosian swarm encounter.** Ten Geonosian Warriors in their home arena. Even with Force-sensitivity, the dice math just doesn't work. Run.

---

## 9. Aim

Type `aim` to spend your action carefully aiming. You gain **+1D to your next attack**, stackable up to **+3D** over multiple rounds. The bonus resets to 0 once you actually fire.

Aim is the bedrock of sniper play. Three rounds of `aim` followed by a single shot is a 4D-Blaster character firing at 7D — that's the difference between a probable miss and a probable kill on a difficult target.

It also works as a soft delay tactic. If your initiative is high but you're not ready to commit, `aim` lets you stack a bonus while waiting for a better tactical picture.

The classic Tatooine setup: a player with a sporting blaster and 5D Blaster, perched on a rocky outcropping at long range to a Bantha caravan in the Jundland flatlands. Three rounds of aim (+3D), one shot at 8D against long-range difficulty 20 plus whatever cover the target has. That's the math that puts food on a moisture farmer's table.

---

## 10. PvP Consent and Security Zones

Combat is gated by security level — this is critical to understand. Players are not legally targets just because they're hostile to your character.

| Zone | PvE | PvP |
|---|---|---|
| Secured | Blocked | Blocked |
| Contested | Allowed | Requires challenge/accept |
| Lawless | Unrestricted | Unrestricted |

In contested zones, you must `challenge <player>` and they must `accept` before PvP can begin. Challenges expire after 10 minutes. Once accepted, PvP is open between you for ten minutes.

In secured zones — the Senate District, the Jedi Temple, Kuat Drive Yards — you cannot attack other players at all. The `attack` command will refuse.

In lawless zones — the Jundland Wastes, the Coruscant Underworld below level 50, the Nar Shaddaa Warrens, anywhere on Geonosis that isn't a Republic position — no consent is needed. Anyone can attack anyone.

**Bounty Hunter override:** Guild members with an active claimed contract can bypass PvP consent in contested zones for their target. The bounty is the consent. See [Security Zones](#/guide/security-zones) §4 for the full rules.

For the complete security model — Director-driven crackdowns, faction influence, territory claims, space security — see [Security Zones](#/guide/security-zones).

---

## 11. NPC Combat AI

NPCs in combat use one of five **behavioral profiles** that determine how they pick targets, when they take cover, when they dodge, and when they flee. Knowing which profile you're up against tells you a lot about how to fight them.

| Profile | Attack Style | Defense | Flees At | Targeting |
|---|---|---|---|---|
| **Aggressive** | Attacks best target | Dodges when wounded | Mortally Wounded | Most wounded (easiest kill) |
| **Defensive** | Attacks opportunistically | Prefers dodge/cover | Incapacitated | Random |
| **Cowardly** | Only fights if cornered | Takes cover first | Wounded | Most wounded (safest target) |
| **Berserk** | Always attacks | Never dodges | Never | Strongest (biggest threat) |
| **Sniper** | Aims, then attacks | Uses cover | Wounded | Most wounded (easiest kill) |

The default profile by NPC type in the Clone Wars era:

- **Clone Troopers** are **Aggressive** — they fight as a disciplined unit, will dodge when wounded, will retreat if Mortally Wounded but not before. They pick the highest-value target (the most wounded ally of the player party) and focus fire.
- **B1 Battle Droids** are **Berserk** — they don't dodge, don't take cover, just attack until destroyed. Individually weak (2D Blaster), but they come in numbers and they don't flinch. The first round of a B1 swarm fight is usually the worst because they all act and they all fire.
- **B2 Super Battle Droids** are **Aggressive** with extra durability — they have the protocol to dodge and back off, but their heavy plating means they often don't bother.
- **Droidekas** are **Sniper** — they deploy, aim, fire from cover. The shield is a special-state flag that adds significant resistance to incoming damage.
- **Republic Commandos** are **Defensive** — disciplined, professional, will dodge and take cover, will only flee if the squad is reduced to one survivor. The hardest non-Force opponent in the player-accessible PvE pool.
- **Geonosian Warriors** are **Berserk** in their home arena, **Defensive** outside it. Cultural — they fight to defend the hive, not to win as individuals.
- **Hutt Enforcers** are **Aggressive** — they're paid, they're professional, they fight competently but they don't have suicide-pact loyalty. They'll flee if the contract isn't going their way.
- **Trandoshan thugs** are **Berserk** — religious motivation, jagannath points, they don't flee even when they should.
- **Twi'lek pickpockets / Coruscant Underworld lowlifes** are **Cowardly** — they'll only fight if cornered, will take cover first, will run as soon as wounded.
- **Bounty hunter NPCs** (Cad Bane archetype, Aurra Sing archetype) are **Sniper** — they aim, they take cover, they fight from advantage. Avoid open ground.

**What this means in practice.** A Berserk B1 swarm will pick the strongest character in your party and just hit them every round until they go down. You can mitigate this by full-dodging on the threatened character, or by spreading the threat across multiple PCs. A Cowardly Twi'lek in a back alley will take cover the moment combat starts; if you let them, they'll run — fine if you don't need them dead, bad if you wanted to interrogate them and they escaped. A Sniper Droideka will aim for a round or two before firing — that's your window to close distance, throw an EMP, or flank the cover.

---

## 12. Rewards for Defeating NPCs

Not every NPC you kill is a posted contract or a field-dressable creature. The galaxy is full of ordinary **roaming hostiles** — street thugs, swoop-gang muscle, pirate scavengers, rogue droids — seeded across populated and contested zones. Put one down and you collect a small, automatic reward: a **credit trickle** plus **prestige** toward earned hunter titles. There's no board to check and no contract to claim — land the killing blow and the reward fires on its own.

**What counts.** Any generic hostile that doesn't already carry its own reward hook: *not* a bounty target, *not* a space/wilderness anomaly spawn, *not* a field-dressable creature, *not* a Dark-Side-Point hunter's quarry, *not* a tutorial/questline chain enemy, *not* a vendor. Ordinary guards, gangers, and street pirates standing in the world are the typical quarry. Anything that pays through its own system (a [bounty contract](#/guide/economy), a creature's spoils) never double-dips with this trickle.

**The credits are deliberately tiny**, and that's the point. A small flat reward per kill, a daily soft cap, and a token tail once you pass the cap. Here's why it's so small: combat costs money. Any non-trivial fight burns bacta (medical) and degrades your weapon (repair), and for a real mob those costs exceed the per-kill reward — so grinding runs **break-even to slightly negative**. The tougher the quarry, the more you spend healing relative to the trickle. Think of it as a **solo-play income floor** — what you do when no one else is on and you just want to put down NPCs and zone out — not a road to wealth. Missions, bounties, and smuggling (see [Economy](#/guide/economy)) are where the real money lives.

**It pays zero Character Points.** Advancement is roleplay- and time-gated (the weekly CP cap; see [CP Progression](#/guide/cp-progression)). Grinding mobs can *never* buy skill growth — it pays credits and prestige only, and structurally cannot touch your character's progression. Don't grind expecting to "level up." Grind because the fight was fun and the prestige is yours.

**Prestige is the real reward.** Your lifetime kill tally lives in a per-character hunting log, and crossing a milestone earns a permanent, wearable hunter title — *the Hunter*, then *the Seasoned Hunter*, *the Master Hunter*, and finally *the Apex Hunter*. Earned titles show on `+finger` and `+sheet`; wear one with `+title wear <key>`.

Check your standing any time with **`+hunting`** — it shows your lifetime kill tally, today's take against the daily cap, and how many more kills to your next title:

```
─────────────  HUNTING LOG  ─────────────
  Quarry felled (lifetime): 38
  Today's take: 210 / 400 cr
  Next milestone: 62 more to reach 100 felled.
```

The exact per-kill reward, the daily cap, and the full title thresholds live in [Economy](#/guide/economy) — this is the combat-side summary; that's the ledger-side detail.

---

## 13. Combat Narrative and Flavor

Combat output uses a deliberate two-line format for every action:

**Line 1 (Story):** Bold text with narrative verb variety and wound color escalation.
**Line 2 (Mechanics):** Dim text showing exact rolls, difficulties, damage, and soak.

The narrative line varies by weapon and outcome. A blaster attack might "fire," "shoot," "snap off a shot," or "lay down covering fire." A vibroblade attack might "slash," "thrust," "carve," or "strike." A Force-power attack might "channel," "gather," or "release." The variety is built from a flavor matrix that picks verbs based on the weapon's skill and the margin of success.

Miss margin affects the flavor. A narrow miss says "barely misses!" or "grazes the air past your ear!" A wide miss says "misses wildly!" or "the shot sails well past the target!" The dimmer the description, the worse the roll.

Severe wounds get drama beats. A Wounded Twice result reads "staggers, struggling to stay on their feet." An Incapacitated result reads "collapses, unable to continue." Mortally Wounded reads "falls and lies still, life draining away." These dramatic lines exist specifically because in a play-by-text game, the difference between "wounded twice" and "incapacitated" needs to *feel* different at a glance — players scanning the action log shouldn't have to parse the mechanics line to know what happened.

**Color coding.** Wound results escalate visually:

- No damage: dim white
- Stunned: yellow
- Wounded: bright yellow
- Wounded Twice: orange-yellow
- Incapacitated: bright red
- Mortally Wounded: bold red
- Dead: bold red + skull marker

You can scan a combat log purely by color and know who's in trouble.

**The "◆ YOU" marker.** When you take a hit, the target line shows your name with a bright red diamond marker — "◆ YOU" — so you immediately notice you've been wounded. Other players in the same combat see your name normally; the marker is yours alone. This prevents the "I didn't realize I'd been shot" failure mode in fast multi-combatant fights.

---

## 14. The Posing System

After resolution, there's a short **pose window** before the next round begins. During this window, type **`cpose <text>`** to write a custom narrative description of what your character did:

```
> cpose Kaelin ducks behind the cargo crate, snapping off two quick shots at the B1. The first goes wide but the second catches it in the optical sensor.
```

The combat-pose command is **`cpose`** (not the bare `pose`/`:` emote — that broadcasts an ordinary room emote and will *not* register as your round's pose, leaving you with the auto-pose instead).

If you don't write a pose within the grace period, the system generates an **auto-pose** from a flavor matrix — verb variety based on your weapon skill, miss/graze/solid/devastating tier based on the damage margin, color-coded based on the wound result. The auto-pose is competent prose, not a placeholder.

Type `pass` to skip the pose window explicitly and accept the auto-generated text.

Poses are delivered in initiative order, so the action log reads chronologically: highest-initiative action first, then lower, then lower. This makes it possible to read a round back and follow the sequence cleanly. In a five-on-five fight, the log for one round might be five lines of action followed by five poses, all in initiative order — readable, dramatic, and complete.

The pose window is short on purpose. It's a beat for the narrative to land, not a creative-writing exercise. If you can't think of something in the time given, the auto-pose is more than adequate. Save your best prose for the dramatic rounds — the kill shot on a major villain, the heroic sacrifice that saves your Padawan, the moment your character finally connects with their lightsaber on the Sith they've been chasing for six sessions.

### Practical posing tips

- **Don't restate the mechanics.** The mechanics line already showed the roll. Your pose should be the *fiction* of the result, not a description of it.
- **Acknowledge environment.** "Kaelin ducks behind the cargo crate" reads better than "Kaelin shoots." Use the room.
- **Keep it short.** Three sentences max. The pose window is for one beat per round, not a paragraph.
- **Match the tone.** A wide-miss pose shouldn't be dramatic. A killing-blow pose should be.

---

## 15. Death, Mortal Wounds, and Recovery

**Mortal wound death roll.** Each round you're Mortally Wounded, the game rolls 2D. If the result is less than the number of rounds you've been mortally wounded, you die. Round 1: need to roll ≥ 1 (impossible to die). Round 4: need ≥ 4 (likely fine). Round 7: need ≥ 7 (50/50). The longer you go without medical attention, the worse your odds.

Someone — a fellow PC, an NPC medic, a passing clone with a bacta-patch — can stabilize you and stop the death roll. See [Medical & Death](#/guide/medical-death) for the full healing flow.

**Stun recovery.** Each stun hit has a 2-round timer. When all stun timers expire, you recover to Healthy (if no other wounds). Multiple stuns stack their −1D penalties, and if total active stuns ≥ your Strength dice, you're knocked unconscious. A 3D-Strength character with three concurrent stun timers is at −3D on everything AND unconscious. Wakes up when the timers tick out, with no permanent damage.

**Death and respawn.** When killed, your character respawns at a safe location — usually a nearby Republic medical facility, the Jedi Temple infirmary if you're a Padawan or Jedi, or the Mos Eisley clinic if you died in the Outer Rim. There is no permadeath. Equipment you had equipped is preserved; loose inventory may be lootable from your corpse before it decays. You take a temporary **−1D to all rolls for 30 game-minutes post-respawn** to represent the recovery period — this is the cost of dying, not a permanent setback.

For the corpse system, looting, bacta tank protocols, the −1D debuff details, and the full death loop, see [Medical & Death](#/guide/medical-death).

---

## 16. The Web Client Combat Panel

If you're playing through the web client (which most players are), combat gets a dedicated panel that updates in real time:

- **Wound pips** — color-coded health indicators for every combatant in the fight
- **Initiative order** — who acts when, top to bottom
- **Declared actions** — what each combatant has locked in for this round
- **★ Viewer marker** — your own character highlighted distinctly
- **Phase labels and round badge** — current phase and round number, top of panel
- **Cover and aim indicators** — small visual flags showing tactical state
- **Pose deadline countdown** — how long you have left in the pose window

The panel is meant to replace the cognitive load of tracking everything in text. You don't need to remember whether the B1 is at half cover or whether you have an aim stack — the panel shows you. Telnet players still get the text-based status via `combat` and `combat rolls`, but the web client is significantly more readable for anything beyond a simple two-combatant fight.

A particularly important affordance: the panel shows you, in real time, which combatants have declared and which haven't. In a five-character fight you can see at a glance who's still typing their declaration, so you know whether to keep waiting or whether the game is just slow to resolve.

---

## 17. Command Quick Reference

| Command | Syntax | Description |
|---|---|---|
| `attack` | `attack <target> [with <skill>] [cp <n>]` | Attack a target |
| `dodge` | `dodge` | Normal dodge (counts as an action) |
| `fulldodge` | `fulldodge` | Full dodge (only action this round) |
| `parry` | `parry` | Normal melee parry |
| `fullparry` | `fullparry` | Full melee parry |
| `aim` | `aim` | +1D to next attack (max +3D) |
| `cover` | `cover [quarter\|half\|3/4\|full]` | Take cover (defaults to half) |
| `flee` | `flee` | Attempt to escape combat |
| `pass` | `pass` | Skip posing, use auto-pose |
| `cpose` | `cpose <text>` | Submit your narrative pose this round |
| `combat` | `combat` | Show combat status |
| `crolls` | `crolls` (or `combat rolls`) | Show detailed dice for this round |
| `range` | `range <target>` | Check range to a target |
| `challenge` | `challenge <player>` | Request PvP in a contested zone |
| `accept` | `accept` | Accept a PvP challenge |
| `decline` | `decline` | Decline a PvP challenge |
| `soak` | `soak <n>` | Pre-declare CP for damage resistance |
| `forcepoint` | `forcepoint` (or `fp`) | Activate Force Point (Force-sensitives only) |
| `disengage` | `disengage` | Leave combat once it's over |
| `+hunting` | `+hunting` | Your mob-hunting log: kill tally, today's take, next title |

---

*This guide is part of the Parsec Game Guides. See also: [Core Mechanics](#/guide/weg-d6-core-mechanics), [Security Zones](#/guide/security-zones), [Medical & Death](#/guide/medical-death), [Force Powers](#/guide/force-powers), [Encounters & Hazards](#/guide/encounters-hazards), [Economy](#/guide/economy).*
