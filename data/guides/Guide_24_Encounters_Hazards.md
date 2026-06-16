---
category: combat
order: 3
summary: "Random encounters, environmental hazards, and the dangers of wilderness and space."
tags: ["encounters", "hazards", "wilderness", "random", "dangerous"]
---

# Encounters & Hazards

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — May 2026**
**Guide Version 1.0**

---

## How to Read This Guide

This guide covers the **emergent danger layer** of the game — the things that happen *to* you when the world has decided to put pressure on. Encounters are structured choice-driven events (a patrol scans you in deep space; pirates demand a tribute; a distress beacon flashes from a derelict). Hazards are environmental — extreme heat in the desert, toxic atmosphere in the underworld, radiation near a reactor.

Both systems are **emergent rather than planned**. You don't go looking for them; they find you. Knowing how they work means knowing how to read the warning signs, decide quickly, and recover from the outcomes.

If you only have ten minutes, read **§1 What Encounters Are** and **§5 Environmental Hazards**. The rest covers depth: the specific encounter types, the recovery patterns, the long-game of being a character who routinely operates in dangerous terrain.

This is a new guide. There was no earlier version.

---

## 1. What Encounters Are

A **space encounter** is a structured event with branching choices, presented to you mid-transit (or while idle in a space zone). Examples:

- An Republic clone patrol decloaks and demands a scan.
- A pirate gang demands tribute or a fight.
- A distress signal pings — investigate or ignore.
- A mechanical fault in your ship requires repair.
- A friendly contact offers an off-book opportunity.
- A cargo opportunity surfaces in deep space.

Each encounter has 2-4 choices (typically Comply / Bluff / Run / Hide; or Pay / Negotiate / Fight / Flee), a 60-second deadline to respond, and outcomes that flow from your choice plus the skill check the engine runs.

The system runs **only in space** — encounters are a starship phenomenon. On the ground, the equivalent concept is the procedural NPC encounter (Tusken raiders in the wilderness, gang patrols in lawless zones), but those use the ground combat system directly rather than the encounter framework.

### The encounter lifecycle

1. **You're in a space zone.** Idle, transiting, doing cargo work, whatever.
2. **The engine rolls.** Periodically (and based on zone risk + cooldowns + your activity), an encounter triggers.
3. **You see the encounter description.** A boxed message with the situation and your choices.
4. **You have ~60 seconds to respond.** Type `respond <choice>` with one of the listed keys.
5. **Outcomes resolve.** Skill checks run. Damage applies. Loot appears. Or you move on to the next phase of a multi-phase encounter.

### Per-ship cooldowns

The engine caps how often any individual encounter type fires against you:

| Encounter Type | Cooldown |
|---|---|
| Patrol | 10 minutes |
| Pirate | 15 minutes |
| Hunter | 30 minutes |
| Distress | 10 minutes |
| Mechanical | 15 minutes |
| Contact | 10 minutes |
| Cargo opportunity | 15 minutes |

Plus a **global "any encounter" cooldown of 3 minutes** between any two encounters on the same ship. This prevents the system from spam-attacking you with back-to-back events.

The cooldowns are intentional: you should never feel ambushed by *too much*. The system pressures you with one encounter at a time, with breathing room between them.

### Zone caps

Each space zone has a cap on simultaneous active encounters — usually 1. So you can't be encountering a patrol while another patrol is also targeting you. The system serializes.

---

## 2. The Six Encounter Types

### Patrol — Republic / Hutt / Police Stop

**Trigger:** You're in a contested or secured space zone. The patrol's faction matches the zone's affiliation (Republic patrols in Republic space, Republic-flavor in Republic-aligned zones, etc.).

**Choices:**
- **Comply.** Submit to scan. If your cargo is clean, you're cleared. If you have contraband, a Con check determines whether you talk your way out.
- **Bluff.** Fake codes. A Con check vs. the patrol's difficulty. Easy in lawless (10), Moderate in contested (15), Hard in secured (20). On success, the patrol waves you through. On failure, you're confirmed as suspicious and they escalate (boarding or pursuit).
- **Run.** Hit the throttle. Pure piloting roll. On success, you outrun the patrol. On failure, they chase — combat-tier event with the patrol as opponent.
- **Hide.** Go dark, kill power. Sneak/Hide check. On success, the patrol moves on. On failure, they spot the power cycle and engage.

**Practical wisdom:** Comply if you're clean. Bluff if your character has good Con. Run if your ship is fast (Eta-2 Actis Interceptor, modded freighter). Hide if your Sneak is strong and you're in a debris-rich zone. Each choice's success rate depends on your specific build and the patrol's tier.

### Pirate — Ransom or Fight

**Trigger:** You're in a contested or lawless space zone. Pirates spawn opportunistically when traffic is light and you're alone.

**Choices:**
- **Pay.** They demand 500-3,000 cr tribute. You hand it over; they let you go. Reputation hit with the relevant criminal faction (you're paying tribute, you're being marked).
- **Negotiate.** A Con or Bargain roll vs. Moderate (15). On success, they accept reduced tribute (often 1/3 the demand). On failure, they take the original demand or escalate to combat.
- **Fight.** Combat begins. The pirate ship engages you with NPC combat AI. Outcome depends on your ship + skills vs. theirs.
- **Flee.** Pilot roll to outrun. Same dynamics as Patrol's Run.

**Practical wisdom:** Paying is cheap if you can afford it. Fighting is the right answer when you're well-armed and they're a low-tier pirate (small fighter, weak loadout). Fleeing works if your ship is fast. Negotiate cleverly when you have a strong Con character — it's the "save credits without combat" win condition.

### Hunter — Targeted (Event-Driven)

**Trigger:** Someone has marked you. This isn't random — Hunter encounters fire when you've drawn attention (a PC bounty on your head, an organized faction's vendetta, an active manhunt). The hunter is specifically pursuing you.

**Choices:** Same shape as Pirate but stakes higher. The hunter is better-equipped, more determined, and the rewards/consequences are larger. Hunter encounters carry the 30-minute cooldown precisely because they're consequential.

### Distress — Investigation Opportunity

**Trigger:** You're in deep space. A distress signal pings on your sensors.

**Choices:**
- **Investigate.** Follow the signal. The arc plays out — maybe a stranded freighter needs supplies (rewards on help), maybe it's a trap (combat ambush), maybe it's salvage (anomaly system kicks in). The branching is rich.
- **Ignore.** Continue your business. No reward, no risk. Some reputational nuance with the Hutts or Republic depending on whether you should have helped.
- **Comms.** Hail them. Get more information without commiting. Sometimes this is enough to discern trap vs. real distress.

**Practical wisdom:** Investigate if you have spare time and decent combat capability. Ignore if you're carrying valuable cargo and can't afford a delay. Comms is the cautious middle ground — costs nothing, gives intel.

### Mechanical — Random Ship Issue

**Trigger:** Periodic. Heavier on older, less-maintained ships.

**Choices:** Usually a repair-skill check or a "do you ignore and accept performance loss" choice. A jammed weapon, a fluctuating shield, an iffy hyperdrive coupling. The Engineer station (or your Technical: Space Transports Repair) resolves it.

On success: ship continues normally. On failure: a small stat penalty for the rest of the session, or a component takes hidden damage. On critical fumble: a system breakdown mid-flight that requires a real repair stop.

### Contact — Friendly Encounter

**Trigger:** You're in a zone where your faction has presence. A friendly contact hails you with information, an opportunity, or a request.

**Choices:** Typically a "yes, take the opportunity" or "no, decline." The opportunity might be a mission lead, an off-book trade, intel about an enemy. Decline costs nothing; accept may earn faction reputation or unique rewards.

### Cargo — Trade Opportunity

**Trigger:** Deep space; rare. A small NPC trader offers an off-the-books trade.

**Choices:** Buy, sell, or pass. The trader may offer goods you can't get from regular ports, or accept goods at premium prices. Sometimes legitimate; sometimes a scam (the goods are stolen and tracked by patrol scanners).

---

## 3. The `respond` Command

When an encounter activates, the system displays the situation and choices. You respond:

```
respond <choice>
```

Where `<choice>` is the key listed in the choice description — `comply`, `bluff`, `run`, `hide`, `pay`, `fight`, `flee`, `negotiate`, `investigate`, `ignore`, `comms`, etc.

The engine matches your response to the encounter's expected choices, runs the relevant skill check, and resolves. Outcomes are presented as a follow-up message — sometimes immediate ("you bluff cleanly — they wave you through"), sometimes multi-phase ("they pursue! Combat begins...").

### Timing matters

The 60-second deadline is real. If you don't respond in time:

- **Patrol**: typically advances to a "they board you" outcome.
- **Pirate**: typically advances to combat (they got tired of waiting).
- **Distress**: typically resolves as "ignore" (the signal fades).
- **Mechanical**: usually persists; you'll be reminded.
- **Contact**: typically ignored, opportunity lost.

The pressure is intentional. You should be deciding quickly under uncertainty, not careful analysis. Encounter content rewards instinct over computation.

### Crew-station coordination

Some encounters explicitly invite specific crew stations to handle the response:

```
stationact <action>
```

A Sensors crew member can `stationact scan` to gather more intel before responding. An Engineer can `stationact repair` to address mechanical issues. The Commander can `stationact rally` for a Command roll bonus on the next station-action. Crewed ships have more options than solo pilots in encounters; the system rewards multi-player crew play here.

---

## 4. Anomalies

Distinct from encounters, **anomalies** are persistent space-zone features that you can choose to engage with. Where encounters are *forced* events with deadlines, anomalies are *opt-in* opportunities you can investigate when you want.

### Types of anomalies

| Type | What It Is |
|---|---|
| **Derelict** | An abandoned ship or station. Salvageable. (Resolved via `salvage` command.) |
| **Distress** | A stranded ship needing help. (Investigation pays out or reveals a trap.) |
| **Cache** | A hidden cache of cargo or credits. Find and recover. |
| **Pirates** | A pirate base hidden in a zone — attack and loot. |
| **Mineral Vein** | A deep-space resource node for mining. |
| **Republic Dead Drop** | An encrypted intelligence cache. Slicing check (Difficult); failure triggers a Republic patrol. |
| **Mynock** | A swarm of mynocks attached to a wreck or asteroid. (Combat-ish encounter.) |

### Discovery

You discover anomalies by scanning:

```
scan                       — Basic scan of the zone
deepscan                   — Detailed scan; identifies anomalies and threats
```

Scanning reveals anomalies present in the zone. The deepscan provides specific identification (vs. just "an anomaly is here"). You can ignore them; you can investigate them.

### Investigation

```
investigate <anomaly_id>
```

Begins the anomaly's branching sequence. Each anomaly type has its own flow — derelicts go through `salvage`; distress signals lead to NPC scenes; caches require skill checks to find and access. Outcomes vary from "you found 5,000 credits" to "the trap activates; combat begins."

### When to investigate

Anomalies are **risk-and-reward**. Most pay out something — credits, salvage, resources, intel. Some carry real risk (the Republic Dead Drop can trigger a patrol if slicing fails). Investigation takes real-time minutes; if you're rushed, skip the anomalies and continue.

For dedicated spacers, anomaly investigation is a regular income stream. Spending 10-15 minutes investigating two or three anomalies in a transit zone is often worth 1,000-3,000 cr plus interesting loot.

---

## 5. Environmental Hazards

On the ground, certain rooms carry **environmental hazards** that periodically tick against characters present. Unlike combat encounters, hazards are **environmental conditions** — they affect everyone in the room, including NPCs, simply by being there.

### The four hazard types

**Extreme Heat.**
- **Tested by:** Stamina vs. base difficulty 10 (scales with severity).
- **Mitigation items:** Water canteen, cooling unit (in your inventory).
- **Debuff applied:** **Dehydration** — −1D Strength, stacks up to 3x. Persistent until you drink water or leave the heat.
- **Environments:** Desert wilderness, barren zones, desert fringe.
- **Found in:** Tatooine Dune Sea, Jundland Wastes, certain desert outposts.

**Toxic Atmosphere.**
- **Tested by:** Stamina vs. base difficulty 12.
- **Mitigation items:** Breath mask.
- **Debuff applied:** **Toxic Exposure** — −1D Strength. Persistent until you equip a breath mask or leave the area.
- **Environments:** Deep underground zones.
- **Found in:** Coruscant underworld levels, certain industrial zones, the deep Kessel mines.

**Urban Danger.**
- **Tested by:** Perception vs. base difficulty 10.
- **Mitigation items:** None — it's a perception test.
- **Effect:** **Credit theft** — On failure, you lose some credits (10-50 cr) to a pickpocket. Repeated failures escalate.
- **Environments:** Lawless urban zones.
- **Found in:** Nar Shaddaa undercity rough rooms, certain Coruscant lower-level alleys.

**Radiation.**
- **Tested by:** Stamina vs. base difficulty (varies by source).
- **Mitigation items:** Radiation suit.
- **Debuff applied:** **Radiation Sickness** — varies; can include long-term effects.
- **Environments:** Manually tagged rooms only (e.g., reactor cores, irradiated wreckage, certain Kessel areas).

### How hazards work

**Hazards tick every 5 minutes.** When the timer fires:

1. The engine identifies all characters in hazard-tagged rooms.
2. For each character, it checks: do they have the mitigation item (canteen, breath mask, etc.) in their inventory or equipped?
3. If they have mitigation: the check is bypassed. No roll. No debuff.
4. If they don't: a skill check is rolled. Pass = no debuff. Fail = the relevant debuff applies (or stacks).

The 5-minute cadence means hazards are **slow attrition**, not instant damage. You can spend 5-10 minutes in extreme heat without consequence if your Stamina rolls hot. Stay 30+ minutes without water, and the dehydration stacks add up.

### Reading hazard signals

When you enter a hazard zone, you see the warning text. Examples:

- **Extreme heat**: *"The twin suns beat down mercilessly. Your mouth is parched, your skin burning. Without water, you won't last much longer."*
- **Toxic atmosphere**: *"The air burns your lungs with every breath. Chemical particulates sting your eyes. You need a breath mask."*
- **Urban danger**: *"You feel eyes on you from the shadows. This neighborhood has a reputation for a reason."*

These are your first indication that a hazard applies. Watch for them; carry mitigation items when planning extended visits.

### Mitigation items

All four mitigation items are craftable (Guide #7) and stockable at vendor droids (Guide #17):

| Hazard | Mitigation Item | Crafted By |
|---|---|---|
| Extreme heat | Water canteen | Vek Nurren (or any crafter with the schematic) |
| Extreme heat | Cooling unit | Venn Kator |
| Toxic atmosphere | Breath mask | Vek Nurren |
| Radiation | Radiation suit | Vek Nurren |
| Urban danger | (none — Perception is the test) | — |

A spacer or wilderness traveler typically carries a water canteen and a breath mask at minimum. The cost is small (a few hundred cr each) and the protection is essentially free across many hours of play. The mitigation items are inventory-light — they don't consume on use.

---

## 6. Long-Game Survival

For characters who routinely operate in dangerous zones, the hazards and encounters layer become **background management**:

**Pre-trip checklist.**
- Mitigation items in inventory (canteen + breath mask, minimum).
- Stimpacks and bacta packs (Guide #19).
- Working comlink (for hailing patrols or contacting allies).
- A buddy if possible — encounters are often easier with a Sensors-equipped partner.

**During the trip.**
- Watch for hazard warnings on room entry; carry mitigation when warning appears.
- Watch for encounter triggers in space; respond quickly.
- Use scanning aggressively in deep space — find anomalies before they find you.

**Post-trip cleanup.**
- Bacta-tank if you took the wound-state debuff.
- Restock mitigation items if they got consumed.
- Restock medical consumables based on what you used.

This rhythm is the spacer's and wilderness-fighter's daily ritual. After a few weeks, it's reflex. The mitigation items, the medical loadout, the encounter-response patterns become muscle memory.

---

## 7. The Five Worked Scenarios

Five concrete pictures.

**Scenario 1 — Patrol in deep space.** You're transiting Tatooine Deep Space carrying legitimate cargo. A Republic patrol decloaks. You see the encounter: "Republic Patrol Inspection — choose: comply, bluff, run, hide." You `respond comply`. The scan finds nothing. You're cleared. The encounter ends. Total time: 60 seconds. No cost.

**Scenario 2 — Pirate ambush in Nar Shaddaa orbit.** You're a Twi'lek smuggler approaching Nar Shaddaa with glitterstim. Three pirate ships block your approach: "Pirate Demand — pay 1,500 cr or fight." Your ship has decent guns. You `respond fight`. Combat begins; you use your YT-1300's turret and fire control. The pirates withdraw after one of their ships takes serious damage. You finish the approach with damaged shields but cargo intact.

**Scenario 3 — Distress signal investigation.** You're in deep space. Sensors ping: "Distress signal, unknown source." You `respond investigate`. You arrive at the signal — a damaged freighter, captain pleading for help with supplies. You give him 200 cr worth of medpacs. He thanks you, gives you a contact name in Coronet. Two weeks later that contact pays out a 5,000 cr smuggling job. The investigation paid off in indirect ways.

**Scenario 4 — Wilderness heat death.** You're tracking bandits through the Dune Sea. No canteen. After 30 minutes of real-time, you've failed three Stamina checks at 5-minute intervals — Dehydration is now 3-stacked, you're at −3D Strength. Your soak rolls have collapsed. The next bandit fight goes badly; you're Wounded Twice and barely escape. The hazard nearly killed you. Lesson: carry the canteen.

**Scenario 5 — Hunter encounter.** A PC bounty was posted on your character (you're worth 25,000 cr to the right hunter). You're transiting Kessel Approach. The encounter fires: "Bounty Hunter — Boba Vinn intercepts your ship." You see the choices. You `respond fight`. The hunter is a Veteran-tier — better-equipped than a pirate. You take significant damage but survive; the hunter's ship is destroyed. The bounty doesn't pay (you didn't kill the hunter cleanly), but you're alive. Lesson: PC bounty Hunter encounters carry real stakes. Travel armed.

---

## 8. Common Pitfalls

**1. Slow to respond.** A 60-second deadline feels generous until you're parsing a four-option encounter description. If you delay, the default outcome triggers — usually combat. Have a fast read.

**2. Carrying no mitigation items into hazard zones.** Walking into the Dune Sea without a canteen is the most common rookie mistake. The hazard ticks accumulate fast.

**3. Trying to bluff Republic clone patrol with low Con.** The bluff difficulty in secured zones is 20. If your Con is 3D, you'll fail more than you succeed. Comply instead.

**4. Ignoring distress signals when you should help.** They're not always traps. Some are genuine, and ignoring them costs you reputation in the relevant faction. Read the situation.

**5. Engaging Hunter encounters without preparation.** Hunters are upgraded pirates — better gear, more aggressive. They'll go through an under-prepared spacer. If a Hunter encounter fires, consider fleeing first; engage only if you have the tools.

---

## 9. Player Commands Quick Reference

| Command | What it does |
|---|---|
| `respond <choice>` | Respond to an active encounter |
| `stationact <action>` | Crew-station-specific encounter action |
| `encounter` | View current active encounter status |
| `scan` | Basic sensor scan of current zone |
| `deepscan` | Detailed scan — identifies anomalies and threats |
| `investigate <anomaly_id>` | Begin investigation of a discovered anomaly |
| `salvage` | Search for salvage in current deep-space zone |

---

## 10. Numbers At A Glance

| Quantity | Value |
|---|---|
| Default encounter choice deadline | 60 seconds |
| Per-ship encounter cooldown — any | 3 minutes (180 seconds) |
| Patrol cooldown per ship | 10 minutes |
| Pirate cooldown per ship | 15 minutes |
| Hunter cooldown per ship | 30 minutes |
| Max active encounters per zone | 1 |
| Hazard check interval | 5 minutes (300 seconds) |
| Extreme heat difficulty | Stamina vs. 10 (scales with severity) |
| Toxic atmosphere difficulty | Stamina vs. 12 |
| Urban danger difficulty | Perception vs. 10 |
| Radiation difficulty | Stamina vs. 10+ |
| Bluff difficulty — secured zone patrol | Difficult (20) |
| Bluff difficulty — contested zone patrol | Moderate (15) |
| Bluff difficulty — lawless zone patrol | Easy (10) |
| Pirate demand range | 500-3,000 cr |
| Pirate negotiate difficulty | Moderate (15) |
| Anomaly types | 7 (derelict, distress, cache, pirates, mineral vein, republic dead drop, mynock) |
| Dehydration stack cap | 3x |

---

## 11. A Final Word

The Encounters and Hazards systems exist to make the world feel **dynamic and contingent**. Without them, traveling between locations would be a transit-time wait. With them, the world is sometimes friendly, sometimes hostile, sometimes opportunity-rich, and you have to be alert.

Most encounters are **manageable**. Most hazards are **survivable with preparation**. The system doesn't aim to wipe characters; it aims to require active engagement. A spacer who carries mitigation items, responds to encounters quickly, and reads the warning signs correctly will travel the galaxy without much trouble. A spacer who plays carelessly will accumulate small setbacks until they compound into a real loss.

The deeper system goal is **emergent narrative**. The pirates who shake you down for 1,500 cr today might come back next week. The friendly contact you helped during a distress signal might lead you to a long-arc mission. The hunter who pursued you means someone, somewhere, has marked you — and the next encounter might reveal who. The encounters layer is where the world meets you halfway: you're not just running missions, you're living in a galaxy that has its own life.

For players who treat these systems mechanically — read the encounter, pick the optimal choice, move on — they're a small layer of additional complexity. For players who pose through them and let them shape their character's experience, they're some of the richest content in the game. Pose your character's reaction to the Republic clone patrol. RP the negotiation with the pirate captain. Take notes on which factions favor you. The system rewards both modes.

---

*End of Guide #24 — Encounters & Hazards*
