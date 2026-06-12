# Tutorial System — Design Document
## SW_MUSH · April 2026 · Opus Design Session

---

## 1. Philosophy

The worst tutorial teaches every system before the player cares about any of them. The best tutorial makes the player *do a thing*, feel the reward, and then say "what else can I do?"

SW_MUSH currently has 195+ commands across 21 modules, 50+ space commands, a crafting pipeline, a smuggling system, bounty hunting, Force powers, NPC crews, missions, and a Director AI shaping the galaxy. Dumping all of this on a new player is overwhelming. Not teaching any of it means they log in, look around Mos Eisley, don't know what to do, and leave.

The design: a short mandatory **core tutorial** (10–15 minutes) that gets you moving, talking, fighting, and earning your first credits. Then a set of **elective modules** — self-contained training scenarios you can enter at any time, covering space, combat, economy, crafting, and the Force. Each elective is accessed from a persistent hub that stays available after the core is done. Players return when they're ready to learn something new.

Think of it like a flight school with a main campus. Everyone goes through orientation. Then you pick which simulators to train in.

---

## 2. Structure Overview

```
CHARACTER CREATION
        │
        ▼
┌─────────────────────┐
│   CORE TUTORIAL     │  Mandatory. 10-15 minutes.
│   (The Arrival)     │  Movement, look, talk, +sheet,
│                     │  basic combat, first mission,
│                     │  credits, gear purchase.
│                     │  Ends at Mos Eisley gates.
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  MOS EISLEY          │  The real game world.
│  (Live world)        │  Player is free.
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│  TRAINING GROUNDS   │  Persistent hub. Accessible
│  (Elective Hub)     │  anytime via 'training' command
│                     │  or by walking to it.
│  ┌───────────────┐  │
│  │ Space Academy │  │  Flight, navigation, combat
│  │ Combat Arena  │  │  Advanced ground combat
│  │ Trader's Hall │  │  Economy, missions, smuggling
│  │ Crafter's Shop│  │  Survey, gather, craft
│  │ Jedi Enclave  │  │  Force powers (Force-sensitive only)
│  │ Bounty Office │  │  Bounty hunting, tracking
│  │ Crew Quarters │  │  NPC hiring, ship crewing
│  └───────────────┘  │
└─────────────────────┘
```

---

## 3. Core Tutorial — "The Arrival"

### 3.1 Narrative Frame

You've just arrived on Tatooine. Your transport dropped you at a dusty outpost on the outskirts of Mos Eisley. A contact is waiting for you inside the city — but first you need to get there, and the desert between here and the spaceport isn't entirely safe.

This is the universal Star Wars opening: the nobody arriving on a backwater planet with nothing but their wits. Luke arriving in Mos Eisley. The Mandalorian walking into a cantina. Every player starts the same way regardless of species, archetype, or background.

### 3.2 Room Layout (separate zone, 8–10 rooms)

```
[Landing Pad] → [Desert Trail] → [Rocky Pass] → [Ambush Point]
                                                       │
                                               [Mos Eisley Gate]
                                                       │
                                              [LIVE WORLD START]
```

The tutorial zone is a one-way path. No getting lost, no confusion about where to go. Each room teaches one concept. Once you reach Mos Eisley Gate, you're done and the exit is one-way into the live world (you can't walk back).

### 3.3 Room-by-Room Walkthrough

**Room 1: Landing Pad**
*What it teaches:* `look`, movement, reading room descriptions, exits.

> The dusty landing pad of Outpost Aurek stretches before you. A battered shuttle idles behind you, engines cooling. A weathered Twi'lek in a pilot's jacket leans against a cargo crate, watching you.
>
> Exits: [east] Desert Trail

A guide NPC (the Twi'lek) greets you automatically on entry:

> "Hey, fresh off the shuttle? Welcome to Tatooine. I'm Kessa. You'll want to head east toward Mos Eisley — that's where the work is. Type **look** to get your bearings, then head **east** when you're ready."

The system sends a private hint if the player idles for 30 seconds without typing anything:

> [TUTORIAL] Try typing: look
> [TUTORIAL] Then type: east (to move to the next area)

**Room 2: Desert Trail**
*What it teaches:* `+sheet`, `talk`, NPC interaction.

An old hermit NPC sits by the trail. The room description mentions him. The system prompts:

> [TUTORIAL] See that old hermit? Try talking to him: talk hermit
> [TUTORIAL] You can also check your character stats: +sheet

When the player talks to the hermit, the NPC gives a brief speech about the dangers of the Wastes and mentions that the player should check their equipment before going further. This naturally leads to:

> [TUTORIAL] Check what you're carrying: +inv
> [TUTORIAL] Equip your weapon: equip

**Room 3: Supply Cache**
*What it teaches:* `+inv`, `equip`, `+credits`, item interaction.

A crate of emergency supplies. The system walks them through picking up an item and equipping it. If they have starting credits, they see their balance.

> [TUTORIAL] Pick up the medpac: get medpac
> [TUTORIAL] Check your credits: +credits

**Room 4: Rocky Pass**
*What it teaches:* `emote`, `say`, communication basics.

Kessa (the guide NPC) catches up via a shortcut. She asks the player to practice communicating — say something, emote an action. This feels natural because she's "testing" if you can handle yourself before the rough part of the trail.

> [TUTORIAL] Say something in-character: say I'm ready for whatever's out there.
> [TUTORIAL] Describe an action: emote checks their blaster nervously.

Kessa responds to whatever they say via the AI brain, keeping it brief and encouraging.

**Room 5: Ambush Point**
*What it teaches:* Basic combat — `attack`, `dodge`, wound system, death/respawn.

Two Tusken Raiders attack. This is a scripted encounter with weakened NPCs (2D blaster, 2D Strength) designed to be winnable by any starting character. The system walks through combat step by step:

> [COMBAT] Tusken Raiders attack!
> [TUTORIAL] Fight back: attack tusken
> [TUTORIAL] After each round, you can also: dodge (to avoid attacks)

The combat resolves normally through the existing combat engine. If the player wins (expected), they get a congratulatory message and loot (50 credits, a gaderffii stick). If they somehow lose, the respawn system handles it and places them back at the Rocky Pass with a message from Kessa about patching them up.

**Room 6: Mos Eisley Gate — The Mission**
*What it teaches:* `+missions`, `accept`, `complete`, earning credits.

Kessa is waiting. She points the player to a job board on the gate wall — a single delivery mission (bring a datapad to a contact inside the cantina). This is a tutorial-specific mission that always spawns here.

> [TUTORIAL] Check the job board: +missions
> [TUTORIAL] Accept the delivery job: accept 1
> [TUTORIAL] Head into Mos Eisley through the gate to deliver it!

The player walks through the gate into the live Mos Eisley world. The mission completes automatically when they reach the cantina and type `complete`. Payout: 200 credits — enough to feel rewarding but not economy-breaking.

**Post-Gate: Welcome Message**

On entering Mos Eisley for the first time, the player gets a one-time welcome:

> ══════════════════════════════════════════════════════
>  Welcome to Mos Eisley! The core tutorial is complete.
>
>  You earned 250 credits and some basic gear.
>  The galaxy is yours to explore.
>
>  WHAT NEXT?
>   • Explore Mos Eisley — the cantina, market, and
>     docking bays are all worth visiting.
>   • Check +missions for paying work.
>   • Visit the Training Grounds anytime for advanced
>     lessons: type 'training' from anywhere in Mos Eisley.
>
>  Type +help newbie for a quick reference.
> ══════════════════════════════════════════════════════

### 3.4 Tracking

A `tutorial_state` key in the character's `attributes` JSON tracks progress:

```json
{
    "tutorial_core": "complete",
    "tutorial_electives": {
        "space": "not_started",
        "combat": "not_started",
        "economy": "not_started",
        "crafting": "not_started",
        "force": "not_started",
        "bounty": "not_started",
        "crew": "not_started"
    }
}
```

The core tutorial sets `tutorial_core` to `"complete"` when the player exits through the gate. This flag is checked by the `training` command to unlock electives.

### 3.5 Skipping

Veteran players can skip the core tutorial during character creation:

> You've arrived on Tatooine. Would you like to:
>   1. Follow the guided arrival (recommended for new players)
>   2. Skip to Mos Eisley (for experienced MUSHers)

Option 2 drops them directly into Mos Eisley with the same starting credits/gear, `tutorial_core` set to `"skipped"`, and all electives unlocked.

---

## 4. The Training Grounds — Elective Hub

### 4.1 Concept

A persistent area accessible from Mos Eisley — physically it's a room near the Transport Depot or Docking Bay, narratively it's a "Spacer's Guild Training Center" or similar. The player can also teleport there with the `training` command from anywhere in Mos Eisley.

```
training                    — teleport to the Training Grounds hub
training space              — go directly to Space Academy
training combat             — go directly to Combat Arena
training list               — show available modules and completion status
```

The hub room has exits to each elective module. Each module is a self-contained zone of 4–8 rooms with its own narrative, NPCs, and practice scenarios. Completing a module grants a small reward (credits, a cosmetic title, or a useful item) and sets the `tutorial_electives.<module>` flag to `"complete"`.

Players can leave any elective mid-progress and return later. Progress within a module is tracked per step, so you resume where you left off.

### 4.2 Hub Room

> **Spacer's Guild — Training Center**
> A clean, well-lit facility on the edge of the Docking Bay district. Holoprojectors line the walls showing recruitment notices for various guilds and factions. A protocol droid stands at a reception desk, ready to direct newcomers.
>
> Several doors lead to specialized training areas. A sign reads:
>   "All training programs are voluntary and self-paced.
>    Complete any program to receive your Guild certification."
>
> Exits:
>   [space]    Space Academy — Flight and Navigation
>   [combat]   Combat Arena — Advanced Fighting
>   [economy]  Trader's Hall — Money and Missions
>   [crafting] Crafter's Workshop — Building Things
>   [force]    Jedi Enclave — The Force (Force-sensitive only)
>   [bounty]   Bounty Office — Tracking and Hunting
>   [crew]     Crew Quarters — Hiring and Managing NPCs
>   [out]      Back to Mos Eisley

The protocol droid NPC answers questions about each module and can check your completion status.

---

## 5. Elective Modules

### 5.1 Space Academy (6 rooms)

**Narrative:** An old Rebel flight instructor named Commander Dex runs a simulator bay. He walks you through the basics of spaceflight in a safe environment before sending you up in a real ship.

**Room 1: Briefing Room**
Dex explains the basics — ships, crew stations, zones. The player reads a holoprojector display (essentially a condensed version of the Spacer's Handbook intro). Teaches: `+ships`, `+ship/info`.

**Room 2: Simulator — Boarding**
A simulated docking bay with a training ship. Teaches: `board`, `pilot`, `launch`. The training ship is a special instance that can't be destroyed and doesn't cost fuel.

**Room 3: Simulator — Navigation**
Now in space (a tutorial-only zone). Teaches: `course`, `scan`, zone movement. Dex talks them through navigating from dock to orbit to deep space and back.

**Room 4: Simulator — Hyperspace**
Teaches: `hyperspace`, astrogation rolls, travel time. A short jump to a tutorial hyperspace zone and back. Explains the misjump risk.

**Room 5: Simulator — Combat**
A scripted encounter with a weak pirate NPC. Teaches: `fire`, `evade`, `lockon`, `shields`, `damcon`. The pirate is designed to be beatable but lands a few hits so the player sees damage and repair.

**Room 6: Graduation**
Dex congratulates them. Reward: 500 credits and the title "(Certified Pilot)" visible on `+sheet`. The player is told where to buy their first ship (Docking Bay) and pointed toward the smuggling board for their first real space job.

**Completion flag:** `tutorial_electives.space = "complete"`

### 5.2 Combat Arena (4 rooms)

**Narrative:** A Mandalorian veteran runs a training ring behind the cantina. No blasters — this is about fundamentals.

**Room 1: Basics Refresher**
Quick recap of combat commands for players who skipped or forgot the core. Teaches: `attack`, `dodge`, `fulldodge`, `aim`, `flee`.

**Room 2: Multi-Action Training**
A sparring partner NPC demonstrates multi-action penalties. Teaches: attacking + dodging in the same round, when it's worth it vs. when to commit.

**Room 3: Ranged vs. Melee**
Two encounters — one ranged (blaster), one melee (vibroblade). Teaches: cover, range bands, melee parry, weapon switching.

**Room 4: Boss Fight**
A tougher NPC opponent (Novice-tier bounty hunter stats). Winning requires using what was taught. Reward: 300 credits, a decent blaster pistol (quality 60).

**Completion flag:** `tutorial_electives.combat = "complete"`

### 5.3 Trader's Hall (5 rooms)

**Narrative:** A Rodian merchant guild operator introduces the economic systems.

**Room 1: Credits and Commerce**
Teaches: `+credits`, `buy`, `sell`, `+weapons`, Bargain skill. The player haggles with an NPC vendor for practice.

**Room 2: The Mission Board**
Teaches: `+missions`, `accept`, `complete`, `abandon`. A tutorial-specific mission spawns (Easy delivery, guaranteed success).

**Room 3: Smuggling 101**
Teaches: `+smugjobs`, `smugaccept`, `smugdeliver`, `smugdump`. Explains risk tiers, patrol checks, the Con/Sneak roll. A safe practice run with no real patrol risk (tutorial flag disables the patrol check).

**Room 4: Bounty Basics**
Teaches: `+bounties`, `bountyclaim`, `bountytrack`, `bountycollect`. A tutorial NPC bounty target is placed in the next room for the player to track and collect on.

**Room 5: Putting It Together**
A summary room. The Rodian explains how smuggling, missions, and bounties fit together as income lanes. Points toward the relevant `+help` topics. Reward: 400 credits.

**Completion flag:** `tutorial_electives.economy = "complete"`

### 5.4 Crafter's Workshop (4 rooms)

**Narrative:** A grizzled Duros engineer demonstrates the crafting pipeline.

**Room 1: Resource Survey**
Teaches: `survey`, resource types, quality. The room has a rich resource node (tutorial-only, guaranteed high-quality find).

**Room 2: Gathering**
Teaches: gathering resources from survey results. Player collects enough materials for one craft.

**Room 3: Assembly**
Teaches: `+schematics`, `craft`. The player is granted a basic blaster schematic (if they don't have one) and walks through assembly. Explains quality, experimentation, failure modes.

**Room 4: Experimentation & Graduation**
Teaches: experimentation rolls on a completed item. Reward: the item they crafted (theirs to keep), 200 credits, and the schematic is permanently learned.

**Completion flag:** `tutorial_electives.crafting = "complete"`

### 5.5 Jedi Enclave (4 rooms, Force-sensitive only)

**Gating:** The exit from the hub to this module checks `force_sensitive` on the character sheet. Non-Force-sensitive characters get: "The door doesn't respond to your touch. You sense nothing within." This is thematic — the Enclave only reveals itself to those who can feel it.

**Narrative:** A quiet meditation chamber beneath the Training Center. A holocron provides guidance (avoiding the need for a live Jedi NPC, which would be lore-problematic during the GCW era).

**Room 1: Sensing the Force**
Teaches: `+forcestatus`, `+powers`, how Force skills work. The holocron explains Control, Sense, and Alter.

**Room 2: Using Powers**
Teaches: `force <power>`. The player uses their starting Force power on a target (a training remote, a locked box, etc.). Explains skill rolls, multi-skill powers.

**Room 3: The Dark Side**
Teaches: DSP, the temptation mechanic, Force Points. The holocron presents a moral dilemma — use the Force aggressively for quick success (gain a DSP) or solve the problem the hard way. This is the single most important lesson for a Force-sensitive character.

**Room 4: Meditation**
A brief cooldown room. The holocron summarizes the path ahead. Reward: +1 Force Point (significant and thematic). No credits — Jedi don't get paid.

**Completion flag:** `tutorial_electives.force = "complete"`

### 5.6 Bounty Office (4 rooms)

**Narrative:** A Trandoshan Guild representative explains the profession.

**Room 1: The Profession**
Explains the bounty hunter income lane — the board, threat tiers, tracking vs. pure combat, alive vs. dead payouts.

**Room 2: Tracking**
A practice tracking exercise. An NPC target is hidden somewhere in a small 3-room area. The player uses `bountytrack` (Investigation/Search rolls) to narrow down the location. Teaches the cooldown, the result tiers, and the Sneak/Hide opposition.

**Room 3: The Takedown**
The player finds and fights the NPC target. Teaches: `bountycollect`, the difference between alive and dead capture, the payout modifier.

**Room 4: Going Pro**
Explains Guild reputation (once faction rep is live), how player bounties work (once that system ships), and NPC bounty hunter traffic. Reward: 300 credits, a pair of binder cuffs (flavor item). Points to `+help bounty` and `+help playerbounty`.

**Completion flag:** `tutorial_electives.bounty = "complete"`

### 5.7 Crew Quarters (3 rooms)

**Narrative:** A retired freighter captain explains NPC crew management.

**Room 1: Hiring**
Teaches: `hire`, the hiring board, wage tiers, skill assessment. A tutorial hiring board with a few sample NPCs. The player hires one (free for the tutorial, no wage during training).

**Room 2: Assignment**
Teaches: `assign`, `+roster`, station roles. The player assigns their hired NPC to a station on a training ship and sees the auto-action system in action during a brief simulated combat.

**Room 3: Management**
Teaches: `order`, `unassign`, `dismiss`, wage costs. Explains the tradeoffs between NPC and player crew. Reward: the NPC they hired is theirs to keep (first 24 hours wage-free).

**Completion flag:** `tutorial_electives.crew = "complete"`

---

## 6. Tutorial NPCs

Each module has 1–2 guide NPCs. These are special tutorial-only NPCs with the following properties:

- **AI-enhanced dialogue:** Connected to the NPC brain (Ollama/Mistral) with tutorial-specific context. They can answer freeform questions about their module's topic.
- **Cannot be attacked:** Tutorial NPCs are flagged non-hostile and combat-immune.
- **Persuasion bypass:** The persuasion gate is disabled for tutorial NPCs — they're here to teach, not gatekeep.
- **Per-module personality:** Each NPC has a distinct voice. Commander Dex is gruff but encouraging. The Rodian merchant is eager and chatty. The Mandalorian combat instructor is laconic.

| Module | NPC | Species | Personality |
|--------|-----|---------|-------------|
| Core | Kessa | Twi'lek | Friendly, street-smart, encouraging |
| Space | Commander Dex | Human | Gruff old pilot, no-nonsense |
| Combat | Ordo | Mandalorian | Laconic, demonstrates by example |
| Economy | Greelo | Rodian | Fast-talking, enthusiastic about credits |
| Crafting | Vek Nurren | Duros | Patient engineer, loves explaining |
| Force | Holocron | (artifact) | Calm, ancient, occasionally cryptic |
| Bounty | Ssk'rath | Trandoshan | Professional, pragmatic, respects skill |
| Crew | Captain Mora | Human | Retired captain, fond of stories |

---

## 7. Return-to-Training System

### 7.1 The `training` Command

Available anywhere in Mos Eisley (or any planet's main city, when those are built). Teleports the player to the Training Grounds hub. On return, they're placed back where they left.

```
training                    — go to the Training Grounds hub
training <module>           — go directly to a specific module
training list               — show module status
training return             — go back to where you were
```

The `training return` stashes and restores the player's location in `attributes` JSON under `"training_return_room"`.

### 7.2 Status Display

```
+training
  ══════════════════════════════════════════
   TRAINING GROUNDS — Your Progress
  ══════════════════════════════════════════
   Core Tutorial ........... ✓ Complete
   Space Academy ........... ✓ Complete
   Combat Arena ............ ○ Not started
   Trader's Hall ........... ◐ In progress (step 3/5)
   Crafter's Workshop ...... ○ Not started
   Jedi Enclave ............ ○ Not started (Force-sensitive only)
   Bounty Office ........... ○ Not started
   Crew Quarters ........... ○ Not started
  ──────────────────────────────────────────
   Type 'training <module>' to begin or resume.
  ══════════════════════════════════════════
```

### 7.3 Rewards Summary

| Module | Credits | Item / Perk |
|--------|---------|-------------|
| Core Tutorial | 250 | Starting gear |
| Space Academy | 500 | "(Certified Pilot)" title |
| Combat Arena | 300 | Quality-60 blaster pistol |
| Trader's Hall | 400 | — |
| Crafter's Workshop | 200 | Crafted item + learned schematic |
| Jedi Enclave | 0 | +1 Force Point |
| Bounty Office | 300 | Binder cuffs (flavor item) |
| Crew Quarters | 0 | Free NPC hire (24h wage-free) |
| **All Complete** | **500 bonus** | **"(Guild Certified)" title** |

Completing all seven electives (Force excluded for non-sensitives) grants a bonus 500 credits and the "(Guild Certified)" title — a visible badge of completion. Total tutorial credits if you do everything: 2,450. See Section 13 for the complete reward table including starter quests and planetary discovery.

---

## 8. Technical Architecture

### 8.1 Tutorial Zone

Tutorial rooms live in a dedicated zone (`tutorial_core`, `tutorial_space`, `tutorial_combat`, etc.) built by `build_mos_eisley.py` or a separate `build_tutorial.py` script. Rooms have a `tutorial_zone: true` flag that:

- Disables ambient events (no random Director-driven interruptions)
- Disables world events (no Imperial Crackdown during your first fight)
- Disables NPC traffic spawning
- Disables CP tick accrual (no advancement during training)

### 8.2 Tutorial State Machine

Each module has a step counter in `attributes` JSON:

```json
{
    "tutorial_electives": {
        "space": "complete",
        "combat": "not_started",
        "economy": {"step": 3, "started_at": 1712700000}
    }
}
```

When a player enters a module room, the system checks their step counter and gates entry accordingly. Moving to the next room advances the step. This is simple — no complex event scripting, just room-gated progression.

### 8.3 Tutorial Hints

A lightweight hint system for the core tutorial. On room entry, if the player is in a tutorial zone and idles for 30 seconds without input, send a context-appropriate hint. Hints are defined per-room in the room's properties (or in a `data/tutorial_hints.yaml` file).

```yaml
tutorial_hints:
  landing_pad:
    delay: 30
    hints:
      - "[TUTORIAL] Try typing: look"
      - "[TUTORIAL] Move east to continue: east"
    repeat: 60
  desert_trail:
    delay: 30
    hints:
      - "[TUTORIAL] Talk to the hermit: talk hermit"
      - "[TUTORIAL] Check your stats: +sheet"
    repeat: 60
```

Hints stop once the player takes the prompted action (tracked by a transient flag in session state).

### 8.4 Tutorial NPCs

Tutorial NPCs are created by the build script with special flags:

```python
{
    "tutorial_npc": True,       # Cannot be attacked, no persuasion gate
    "tutorial_module": "core",  # Which module this NPC belongs to
    "tutorial_role": "guide",   # guide, opponent, vendor, target
}
```

Guide NPCs have pre-seeded NPC memory with context about their module, so the AI brain gives relevant answers when players ask questions.

### 8.5 Simulated Systems

Space and combat electives use the real game engines (combat.py, starships.py) but with tutorial-specific modifications:

- **Tutorial ships** can't be permanently destroyed. Hull resets on dock.
- **Tutorial combat** NPCs respawn instantly if killed (so the player can retry).
- **Tutorial zones** are isolated from the live space grid (no NPC traffic interference).
- **No fuel cost**, no docking fees, no durability loss during tutorials.

This means the player experiences the *real* game mechanics — actual dice rolls, real skill checks, genuine combat resolution — in a consequence-free environment.

### 8.6 DB Requirements

No schema migration. All state in existing `attributes` JSON. Tutorial rooms and NPCs created by the build script. Tutorial zones flagged in the `zones` table.

### 8.7 New Files

| File | Purpose |
|------|---------|
| `build_tutorial.py` | Build script for all tutorial rooms, exits, NPCs, and items |
| `data/tutorial_hints.yaml` | Per-room hint text and timing |
| `engine/tutorial.py` | Tutorial state machine, step tracking, hint timer, reward grants |
| `parser/tutorial_commands.py` | `training` command (teleport, list, return) |

---

## 9. Implementation Plan

| Drop | Content | Size | Dependencies |
|------|---------|------|--------------|
| 1 | Tutorial engine (`engine/tutorial.py`), state tracking, hint system, `training` command | Medium | None |
| 2 | Core tutorial rooms + Kessa NPC + scripted combat encounter | Medium | Drop 1 |
| 3 | Starter quest chain (8 steps, all in existing Mos Eisley rooms/NPCs) | Small | Drop 2 |
| 4 | Training Grounds hub + Space Academy (6 rooms + Commander Dex) | Large | Drop 1 |
| 5 | Combat Arena (4 rooms + Ordo) + Trader's Hall (5 rooms + Greelo) | Large | Drop 1 |
| 6 | Crafter's Workshop (4 rooms + Vek Nurren) + Crew Quarters (3 rooms + Mora) | Medium | Drop 1 |
| 7 | Jedi Enclave (4 rooms + Holocron) + Bounty Office (4 rooms + Ssk'rath) | Medium | Drop 1 |
| 8 | Planetary discovery quests (Nar Shaddaa, Kessel, Corellia) | Small | Planet ground rooms exist |
| 9 | Completion rewards, all titles, Grand Tour bonus, +1 CP | Small | Drops 2–8 |

Drops 4–7 are independent of each other. Drop 3 (starter chain) is the highest-value item after the core — it requires zero new rooms and makes the existing city feel alive. Drop 8 (planetary discovery) ships whenever the planetary ground rooms are built.

---

## 10. Design Decisions & Rationale

**Why separate rooms instead of an in-place overlay?**
Tutorial rooms give you full control over the environment. No other players walking through your training fight. No ambient events interrupting the lesson. No Director AI throwing an Imperial Crackdown during your first smuggling run. Isolation is a feature.

**Why not force all tutorials?**
Experienced MUSH players don't need to learn what `look` does. Forcing them through 45 minutes of tutorials they already understand is disrespectful of their time. The core tutorial is short enough (10–15 minutes) that even veterans can tolerate it, and the skip option exists for those who can't.

**Why give rewards?**
Rewards solve two problems: motivation to complete electives, and making sure new players have enough gear/credits to be functional. The credits are calibrated to not distort the economy — the total (2,450 if you do everything) is roughly equivalent to 2–3 hours of normal play. The items are useful but not best-in-class.

**Why a teleport command?**
Walking to the Training Grounds requires knowing where it is, which new players don't. The `training` command is discoverable (mentioned in the welcome message) and removes navigation friction. The return-to-origin feature means you don't lose your place in the world.

**Why use real game engines instead of scripted sequences?**
Players need to learn the real game, not a simplified version that doesn't match. If the tutorial teaches a dice roll that works differently from the live game, you've trained the player wrong. Using the actual combat engine, actual skill checks, and actual ship systems means the skills transfer directly.

**Why is the Force module gated?**
Only Force-sensitive characters can use Force powers. Showing non-sensitive characters a Force tutorial is confusing and misleading. The gate is thematic (the Enclave only reveals itself to those who can sense it) and prevents false expectations.

---

## 11. Starter Quest Chain — "Getting to Know Mos Eisley"

### 11.1 Concept

After the core tutorial deposits the player at the Mos Eisley gate, they know `look`, `talk`, `attack`, and `+missions`. But Mos Eisley has 47 rooms, 50 NPCs, and half a dozen systems they've never seen. Dropping them in with "explore!" and nothing else is a recipe for aimless wandering.

The **starter quest chain** is a series of 6–8 short errands that walk the player through the city district by district, introducing key locations and NPCs by *sending them there with a purpose*. It's not a tutorial — there are no hint popups, no training wheels. It's a sequence of favors and odd jobs given by Kessa (their guide from the core tutorial) that happen to take them past every important location in town.

Kessa stays in the cantina after the core tutorial. When the player finds her (or when the chain auto-starts after the core), she gives them the first errand. Each errand completes when the player reaches the destination and performs a simple action (talk to an NPC, buy an item, look at something). Rewards are small but useful — credits, a piece of gear, a tip about a game system.

### 11.2 The Chain

The chain is tracked in `attributes` JSON under `"starter_quest"` with a step counter. Each step gives a comlink message from Kessa when completed, pointing to the next step. The player can do them at their own pace — there's no timer and no penalty for wandering off.

**Step 1: "Drinks on Me"**
*Kessa:* "Hey, you made it! Come find me in the cantina — I owe you a drink for surviving that mess on the trail."
*Task:* Go to Chalmun's Cantina. Talk to Kessa.
*Teaches:* Where the cantina is (the social hub). Introduces Wuher (bartender), the band, the sabacc tables. Kessa mentions you can `perform` here or play `sabacc` for credits.
*Reward:* 50 credits, Kessa mentions the weapon shop.

**Step 2: "Arm Yourself"**
*Kessa (comlink):* "You're going to need a better blaster if you plan on staying alive out here. Kayson at the Weapon Shop in the market district can sort you out. Tell him I sent you."
*Task:* Go to the Weapon Shop. Talk to Kayson. Buy any weapon (or just browse with `+weapons`).
*Teaches:* Where the market is, how `buy` works, the Bargain skill, weapon stats. Kayson also teaches blaster schematics if you `talk` to him — introduces crafting organically.
*Reward:* 100 credits (Kessa's "referral bonus").

**Step 3: "Patch Yourself Up"**
*Kessa (comlink):* "One more thing — if you get shot, and you will, Heist at the Clinic knows her way around a medpac. Worth introducing yourself."
*Task:* Go to the Clinic. Talk to Heist.
*Teaches:* Where medical services are, healing costs, the `heal` command flow. Heist offers to teach consumable schematics.
*Reward:* 1 free medpac.

**Step 4: "Stash Your Credits"**
*Kessa (comlink):* "Getting some credits together? Smart. Zygian at the bank can hold onto them for you — and I hear she offers... favorable exchange rates to new customers."
*Task:* Go to the Bank. Talk to Zygian Teller.
*Teaches:* Where the bank is, `+credits`, how credits work. Zygian mentions docking fees, fuel costs — the economic basics.
*Reward:* 50 credits ("welcome bonus" from the bank).

**Step 5: "Check the Boards"**
*Kessa (comlink):* "You're getting settled. If you need real work, check the mission board at the Transport Depot. Dispatch keeps it updated. And if you're feeling... adventurous... there might be some less official work available too."
*Task:* Go to the Transport Depot. Use `+missions` and `+smugjobs`.
*Teaches:* Mission board location, smuggling board, Dispatch NPC. This is where the player discovers the main PvE income loops.
*Reward:* 100 credits. Kessa mentions the docking bay.

**Step 6: "Meet Your Ship"**
*Kessa (comlink):* "Last thing. If you're ever going to leave this dustball, you'll need a ship. Head to the Docking Bay and take a look at what's available. The De Maals run a decent operation — just don't let them overcharge you."
*Task:* Go to the Docking Bay. Use `+ships` to browse ships. Optionally use `+ship/info yt_1300` to look at specs.
*Teaches:* Where ships are bought, the `+ship` command family, ship prices. If they can't afford one yet, they now know where to come back when they can.
*Reward:* 200 credits.

**Step 7: "The Outskirts" (optional — combat oriented)**
*Kessa (comlink):* "One more thing. The Jundland Wastes outside town can be dangerous, but they're good hunting ground. Sergeant Kreel at the Police Station might have some... pest control work if you're looking to earn combat pay."
*Task:* Go to the Police Station. Talk to Sergeant Kreel. Accept a combat mission from `+missions`.
*Teaches:* Where combat-focused content is, the outskirts/wastes zone, how to find hostile NPCs. Introduces the idea that different areas of the city connect to different types of gameplay.
*Reward:* 100 credits from Kreel + whatever the mission pays.

**Step 8: "Welcome to Mos Eisley" (chain complete)**
*Kessa (comlink):* "That's everything I can teach you, kid. You know the city, you know the people, you know where the work is. The rest is up to you. Oh — and if you ever want to come back for advanced training, just type 'training'. Good luck out there."
*Final reward:* 200 credits + "(Mos Eisley Local)" title.

### 11.3 Chain Properties

- **Total credits from chain:** 800. Combined with the 250 from the core tutorial, a player who does everything has 1,050cr — enough to buy basic gear but nowhere near a ship. This is intentional: it creates the goal of "save up for a ship" naturally.
- **No handholding:** The chain gives destinations, not directions. "Go to the Weapon Shop" doesn't tell you which exit to take. The player has to `look` at exits and figure out navigation. This is the soft training for spatial awareness.
- **Skippable:** The chain can be abandoned at any point. The remaining steps just won't fire. No penalty.
- **One-time only:** Each step completes once. Revisiting the NPC doesn't re-trigger the quest.
- **Comlink delivery:** After step 1 (finding Kessa in person), all subsequent quest prompts arrive via comlink message. This teaches the comlink system implicitly.

### 11.4 Implementation

Minimal. Each step is a conditional check: "Is the player in room X with starter_quest step N?" If yes, trigger the completion: grant reward, advance step, send next comlink message. This hooks into the room-entry event (already exists for ambient events) or the `talk` command handler.

No new rooms. No new NPCs. Every location and NPC in the chain already exists. The quest chain is pure data — a YAML or dict defining the step sequence, target rooms, and rewards.

```python
STARTER_QUEST_STEPS = [
    {"step": 1, "target_room": "Chalmun's Cantina", "action": "talk kessa",
     "reward_credits": 50, "next_hint": "Kessa suggests visiting Kayson at the Weapon Shop."},
    {"step": 2, "target_room": "Weapon Shop", "action": "talk kayson",
     "reward_credits": 100, "next_hint": "Kessa comlinks about the Clinic."},
    # ... etc
]
```

---

## 12. Planetary Discovery Quests

### 12.1 Concept

Once a player has a ship and travels to another planet, they've graduated far past needing tutorials. They know how to move, fight, trade, and fly. What they *don't* know is what's on this new planet — the local NPCs, the vibe, the opportunities, the dangers.

**Planetary discovery quests** are lightweight exploration rewards, not tutorials. When a player lands on a new planet for the first time, a local NPC contacts them via comlink with a brief welcome and a few optional tasks. Completing them earns credits and a planet-specific title. There are no hint popups, no training rooms, no hand-holding — just "here are some things worth seeing" with a reward for looking.

### 12.2 Trigger

On `land`, if the character has never landed on this planet before (checked via `attributes` JSON `"planets_visited"` list), the system:

1. Adds the planet to `"planets_visited"`
2. Sends a first-arrival comlink message from a local contact NPC
3. Unlocks the planet's discovery quest chain

```json
{
    "planets_visited": ["tatooine", "nar_shaddaa"],
    "discovery_quests": {
        "nar_shaddaa": {"step": 2, "started_at": 1712700000},
        "kessel": "complete",
        "corellia": "not_started"
    }
}
```

### 12.3 Planet Chains

Each planet has 3–5 discovery steps. All optional, all reward-bearing. No tutorials — just exploration incentives.

**Nar Shaddaa — "The Smuggler's Moon"**

Contact NPC: Mira Vel (a Twi'lek fixer at the Nar Shaddaa landing pad)

> *"Fresh off the shuttle? Welcome to Nar Shaddaa, spacer. The Hutts run everything here, but there's plenty of opportunity if you know where to look. Let me point you in the right direction."*

| Step | Task | Reward |
|------|------|--------|
| 1 | Visit the Undercity Market | 100cr + "The Hutts control the market here, but independent traders survive in the cracks." |
| 2 | Talk to the local smuggling contact | 150cr + unlocks Nar Shaddaa smuggling routes on `+smugjobs` |
| 3 | Visit the fighting pits (if built) or cantina equivalent | 100cr + "Entertainment is... rougher here than Mos Eisley." |
| 4 | Find Renna Dox, the shipwright | 150cr + ship mod schematic hint |
| **Complete** | — | **500cr bonus + "(Nar Shaddaa Veteran)" title** |

**Kessel — "The Spice Mines"**

Contact NPC: Foreman Crix (a gruff human at the Kessel docking facility)

> *"You actually landed here on purpose? Brave or stupid. Either way, watch your step — the mines don't care which you are."*

| Step | Task | Reward |
|------|------|--------|
| 1 | Visit the mines observation deck | 100cr + lore about spice and the Kessel Run |
| 2 | Survey for resources in the mining zone | 200cr + guaranteed rare mineral find |
| 3 | Survive the Kessel Approach asteroid field (fly through it) | 300cr + "You made the Kessel Run. Well, part of it." |
| **Complete** | — | **500cr bonus + "(Kessel Survivor)" title** |

**Corellia / Coronet City — "The Shipyards"**

Contact NPC: Dockmaster Vaan (a Corellian bureaucrat at the Coronet spaceport)

> *"Welcome to Corellia, the heart of the galaxy's shipbuilding industry. Coronet City has everything you need — if you can afford it."*

| Step | Task | Reward |
|------|------|--------|
| 1 | Visit the Corellian Engineering Corporation showroom | 100cr + detailed ship comparison info |
| 2 | Talk to the local Traders' Guild representative | 150cr + unlocks Corellia trade goods on `market` |
| 3 | Visit Treasure Ship Row (the famous Corellian market street) | 100cr + lore flavor |
| 4 | Talk to Venn Kator, the shipwright (if on Corellia) | 150cr + ship mod schematic hint |
| **Complete** | — | **500cr bonus + "(Corellian Spacer)" title** |

### 12.4 Design Properties

- **No teaching, just rewarding.** The player already knows how to `talk`, `survey`, `+smugjobs`, and `course`. Discovery quests just give them a reason to explore the new planet and show them what's unique about it.
- **Titles are the real reward.** Credits are nice but the planet-specific titles are what players actually want — visible markers of where they've been. Combined with the Ship's Log system (planned Drop 19), these create a "passport stamps" collectible layer.
- **Future planets get their own chains.** When Kashyyyk, Coruscant, or Hoth are added, they each get a 3–5 step discovery chain. The system is generic — just data, not code.
- **First-arrival message is automatic.** No command needed. Land on a new planet → get a comlink. This ensures every player discovers the feature without searching for it.
- **Interplay with the Ship's Log.** The Ship's Log (Drop 19 of the space expansion) tracks zones visited, ships scanned, and anomalies resolved, with milestone CP tick rewards. Planetary discovery quests complement this — the Log rewards *going there*, the discovery quests reward *looking around once you arrive*.

### 12.5 Realistic Timeline

Correcting the earlier estimate: a focused player can complete the core tutorial in 15 minutes, the starter quest chain in 30–60 minutes, and reach the cantina with over 1,000 credits by the end of their first session. Buying a ship (cheapest: Z-95 at 40,000cr or a used Ghtroc at 23,000cr) takes 1–3 days of active mission running. Reaching all four planets is achievable within the first week.

The elective training modules are 15–30 minutes each and can be done any time. The full Grand Tour (all planets + all electives) is comfortably completable in the first two weeks for a player putting in a few hours a day. The system is designed so that no individual piece feels like a grind — each step is a few minutes, each reward is immediate.

---

## 13. Profession Quest Chains

### 13.1 Concept

After a player has settled in (completed the starter chain, done a few missions), they start gravitating toward a playstyle. The smuggler runs cargo. The bounty hunter takes contracts. The crafter tinkers. Profession quest chains acknowledge this specialization and deepen it with a multi-step storyline that teaches advanced techniques, introduces profession-specific NPCs, and rewards commitment with unique gear and titles.

These are **not tutorials**. The player already knows the commands. Profession chains are narrative content — short storylines with skill checks, branching outcomes, and profession-specific rewards. They're closer to WEG published adventures than to training exercises.

Each chain is 5–8 steps, takes 2–4 play sessions to complete, and is gated by a simple entry requirement (own a ship, have a certain skill at 4D, etc.). Chains are tracked in `attributes` JSON under `"profession_quests"`.

### 13.2 The Smuggler's Run

*Entry requirement:* Own a ship. Completed at least one smuggling delivery.

*Contact NPC:* Kessa (she's a smuggler herself — this is her world)

*Narrative:* Kessa has a friend in trouble. A Twi'lek pilot named Dash owes money to the wrong people and needs help running a series of increasingly risky cargo jobs to pay off the debt. Each step escalates the danger and teaches an advanced smuggling technique.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Run a Grey Market delivery Tatooine → Nar Shaddaa | Multi-planet smuggling routes | 500cr |
| 2 | Deliver contraband while evading a patrol (Con/Sneak check) | Patrol evasion mechanics in depth | 800cr |
| 3 | Meet Dash on Nar Shaddaa — he's being tailed | NPC dialogue, Perception check to spot the tail | 300cr + lore |
| 4 | Run a Spice Run (Kessel → Nar Shaddaa, high patrol risk) | Kessel Approach asteroid navigation | 2,000cr |
| 5 | Dash's creditors catch up — space combat encounter | Combat while carrying cargo (can't dump it) | 1,500cr |
| 6 | Deliver the final payment to the Hutt representative | Bargain check for reduced "processing fee" | 1,000cr |
| **Complete** | — | — | **"(Veteran Smuggler)" title, +Hutt Cartel rep** |

### 13.3 The Hunter's Mark

*Entry requirement:* Completed at least 3 NPC bounties from the bounty board.

*Contact NPC:* Ssk'rath (the Trandoshan from the Bounty Office training module, or a Guild board posting if the player skipped that elective)

*Narrative:* The Bounty Hunters' Guild has a special contract — a target who's been evading capture for weeks across multiple planets. The chain follows a single multi-step hunt with escalating tracking difficulty.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Accept the Guild contract, receive the dossier | Introduction to multi-stage tracking | 200cr retainer |
| 2 | Track the target to Nar Shaddaa (Investigation check) | Cross-planet tracking | 500cr |
| 3 | Target flees — trail leads to Kessel | Chase mechanics, false leads | 300cr |
| 4 | Find the target's ship in a Kessel anomaly (deepscan) | Space scanning as part of bounty hunting | 800cr |
| 5 | Confront the target — they offer to pay you off | Moral choice: take the bribe or stay loyal to the contract |  |
| 5a | (Take bribe) | +3,000cr, −Guild rep, +Criminal rep | 3,000cr |
| 5b | (Complete contract) | +1,500cr, +Guild rep | 1,500cr |
| **Complete** | — | — | **"(Guild Hunter)" title** |

The branching at step 5 is the key moment — it tests whether the player values credits or reputation. Both paths complete the chain but with different consequences. This is the Star Wars moral choice pattern.

### 13.4 The Artisan's Forge

*Entry requirement:* Know at least 2 schematics. Crafted at least 3 items.

*Contact NPC:* Vek Nurren (the Duros engineer from the Crafter's Workshop, now in the live world at a workshop room)

*Narrative:* Vek has been commissioned to build a custom ship component for a wealthy Corellian merchant, but he needs help sourcing rare materials. The chain follows the full crafting pipeline at a higher level — rare resources, difficult assembly, and a demanding client.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Survey for rare minerals in the Jundland Wastes | High-difficulty survey (diff 16) | Rare resource cache |
| 2 | Fly to Kessel and salvage a derelict for energy cells | Space salvage integration | Quality-80+ energy cells |
| 3 | Assemble the component (Difficult craft check) | High-stakes crafting | The component (quality 85+) |
| 4 | Deliver to the Corellian client on Corellia | Bargain check for bonus payment | 2,000cr |
| 5 | Client is so impressed they commission a second job | Teaches experimentation on the second build | 1,500cr + rare schematic |
| **Complete** | — | — | **"(Master Artisan)" title, +Traders' Guild rep** |

### 13.5 The Rebel Cell

*Entry requirement:* Completed at least 2 Rebel-flagged missions, or Imperial zone influence below 40 in any zone the player has visited.

*Contact NPC:* An anonymous comlink contact ("Fulcrum") who reaches out after the player's anti-Imperial actions are noticed.

*Narrative:* The Rebel Alliance has noticed the player's work and wants to recruit them for a covert operation. This chain is the political on-ramp — it introduces the Rebel faction, sets up recurring contacts, and gives the player a stake in the galactic conflict.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Meet the contact in a private back room of the cantina | Stealth (Sneak check to arrive unnoticed) | 200cr + Rebel contact |
| 2 | Deliver a datapad to Nar Shaddaa without being scanned | Smuggling mechanics for the cause, not for credits | 500cr + Rebel rep |
| 3 | Gather intel on Imperial patrol patterns (scan 3 patrols in space) | Space scanning, observation | 800cr + Rebel rep |
| 4 | Sabotage an Imperial supply drop (combat encounter in the Wastes) | Ground combat with Imperial NPCs | 1,000cr + Rebel rep |
| 5 | Extract a Rebel operative from Kessel | Multi-phase: fly to Kessel, land, ground encounter, escape to orbit | 1,500cr + Rebel rep |
| **Complete** | — | — | **"(Rebel Sympathizer)" title, Rebel standing → Friendly** |

### 13.6 The Imperial Service

*Entry requirement:* Completed at least 2 Imperial-flagged missions, or talked to Sergeant Kreel and expressed interest.

*Contact NPC:* Sergeant Kreel (already in the Police Station)

*Narrative:* The local Imperial garrison is short-handed and willing to use freelancers for tasks they don't want official records of. This is the Imperial on-ramp — morally grey work that pays well and earns Imperial favor.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Report to Sergeant Kreel for a "consulting" assignment | Introduction to Imperial missions | 300cr |
| 2 | Track down a suspected smuggler in Mos Eisley (Investigation) | Streetwise/Search in the live city | 800cr + Imperial rep |
| 3 | Escort an Imperial convoy through space (NPC escort mission) | Space escort mechanics | 1,200cr + Imperial rep |
| 4 | "Persuade" an uncooperative merchant to pay taxes (Intimidation or Persuasion) | Social skill check with moral weight | 1,000cr + Imperial rep |
| 5 | Intercept a Rebel supply ship at the Outer Rim Lane (space combat) | Combat against Rebel-flagged NPC ship | 2,000cr + Imperial rep |
| **Complete** | — | — | **"(Imperial Associate)" title, Imperial standing → Friendly** |

### 13.7 The Underworld

*Entry requirement:* Completed at least 3 smuggling deliveries, or Criminal zone influence ≥ 50 in any zone.

*Contact NPC:* Gep (the info broker at the Grill, already in the game)

*Narrative:* Gep has connections deeper than he lets on. If the player has proven they can handle dirty work, he opens the door to the Hutt Cartel's inner circle — higher-paying jobs with higher stakes.

| Step | Task | Teaches / Tests | Reward |
|------|------|----------------|--------|
| 1 | Meet Gep's contact at Jabba's Townhouse | Introduction to the Hutt power structure | 300cr |
| 2 | Collect a debt from a delinquent spice dealer (Intimidation or combat) | Enforcement work | 1,000cr + Criminal rep |
| 3 | Fence stolen goods through a contact on Nar Shaddaa | Multi-planet black market chain | 1,500cr + Criminal rep |
| 4 | Hijack an NPC trader ship's cargo in space | Piracy mechanics (hail, threaten, board) | 2,000cr + Criminal rep |
| 5 | Deliver a "message" to a rival crime boss on Corellia | Climactic confrontation (combat or Con) | 2,500cr + Criminal rep |
| **Complete** | — | — | **"(Made Man)" title, Hutt Cartel standing → Friendly** |

### 13.8 Design Notes on Profession Chains

**These are mutually exclusive in tone, not in access.** A player can do the Rebel Cell AND the Imperial Service chain — the game doesn't prevent it. But faction reputation consequences mean doing both pushes your standing in opposite directions. This is intentional: the player is living the galactic conflict, not being locked into a menu choice.

**Branching moments matter.** Each chain has at least one moral decision point. The Hunter's Mark bribe choice, the Imperial Service tax collection (Intimidation vs. Persuasion), the Underworld piracy step — these define who the character is becoming. The Director AI logs all of these for narrative hooks.

**Entry requirements are soft gates, not walls.** "Completed 3 bounties" isn't hard to achieve — it's just enough to confirm the player is actually interested in bounty hunting before offering them a 6-step storyline about it.

**Faction reputation rewards are the long game.** Each chain pushes the player toward Friendly standing with one faction. From the economy design, Friendly means 10% vendor discount and access to faction-specific missions. This is the bridge between the quest chain system and the faction reputation system — chains are how you *start* a faction relationship, and the rep system (Priority B) is how you *maintain* it.

---

## 14. Faction Status — What Exists Now

For clarity on what's live vs. planned:

**Live (Director AI, v12–v13):**
- `zone_influence` table: 4 factions (Imperial, Rebel, Criminal, Independent) with 0–100 scores per zone
- Player actions shift zone influence (kill Imperial NPC → Imperial −3, Rebel +1; complete smuggling → Criminal +2, etc.)
- Alert levels derived automatically (Lockdown, Lax, Underworld, Unrest) with mechanical effects on docking fees, patrol rates, mission board bias
- Director AI adjusts influence every 30 minutes based on digest of player activity
- `+news` shows GNN bulletins about factional shifts

**Designed, not built (Priority B — Faction Reputation System):**
- Per-character reputation with 6 factions: Rebel Alliance, Galactic Empire, Hutt Cartel, Bounty Hunters' Guild, Traders' Guild, Underworld
- Standing tiers: Hostile → Unfriendly → Neutral → Friendly → Trusted → Allied
- Economic effects: vendor discounts (10%–30%), faction mission access, faction stipends at Allied
- Axis conflicts: Rebel↔Empire (political), Traders↔Underworld (economic), Hutts and BH Guild neutral
- Storage: character `attributes` JSON under `"faction"` key

**What this means for quest chains:** The profession chains are designed to grant faction reputation on completion ("+Rebel rep", "+Hutt rep"), but this requires the faction reputation system to exist. Until Priority B ships, the chains can still be implemented with their narrative content and credit/title rewards — the faction rep lines simply become no-ops that activate once the system is wired. The quest tracking infrastructure doesn't depend on faction rep at all.

---

## 15. Complete Reward Table

| Activity | Credits | Other |
|----------|---------|-------|
| **Onboarding** | | |
| Core Tutorial | 250 | Starting gear |
| Starter Quest Chain (8 steps) | 800 | "(Mos Eisley Local)" title |
| **Training Electives** | | |
| Space Academy | 500 | "(Certified Pilot)" title |
| Combat Arena | 300 | Quality-60 blaster |
| Trader's Hall | 400 | — |
| Crafter's Workshop | 200 | Crafted item + schematic |
| Jedi Enclave | 0 | +1 Force Point |
| Bounty Office | 300 | Binder cuffs |
| Crew Quarters | 0 | Free NPC hire (24h) |
| All Electives Complete | 500 | "(Guild Certified)" title |
| **Planetary Discovery** | | |
| Nar Shaddaa Discovery | 1,000 | "(Nar Shaddaa Veteran)" title |
| Kessel Discovery | 1,100 | "(Kessel Survivor)" title |
| Corellia Discovery | 1,000 | "(Corellian Spacer)" title |
| All Planets Complete | 1,000 | "(Galaxy Traveler)" title, +1 CP |
| **Profession Chains** | | |
| Smuggler's Run (6 steps) | 6,100 | "(Veteran Smuggler)" title, +Hutt rep |
| Hunter's Mark (5 steps) | 2,800–4,300 | "(Guild Hunter)" title, +/−Guild rep |
| Artisan's Forge (5 steps) | 3,500 | "(Master Artisan)" title, +Traders rep, rare schematic |
| Rebel Cell (5 steps) | 4,000 | "(Rebel Sympathizer)" title, Rebel → Friendly |
| Imperial Service (5 steps) | 5,300 | "(Imperial Associate)" title, Imperial → Friendly |
| Underworld (5 steps) | 7,300 | "(Made Man)" title, Hutt → Friendly |
| **Grand Total (all completable)** | **~36,350** | 12+ titles, gear, FP, CP, schematics, faction standing |

The profession chains are substantially more rewarding than the onboarding content because they represent real gameplay investment (2–4 sessions each, skill gates, multi-planet travel). The Underworld chain pays the most because it carries the most risk and moral weight — the dark side economics principle from the economy design.

---

## 16. Implementation Plan (Revised)

| Drop | Content | Size | Dependencies |
|------|---------|------|--------------|
| 1 | Tutorial engine, state tracking, hint system, `training` command | Medium | None |
| 2 | Core tutorial rooms + Kessa NPC + scripted combat | Medium | Drop 1 |
| 3 | Starter quest chain (8 steps, existing rooms/NPCs) | Small | Drop 2 |
| 4 | Training Grounds hub + Space Academy | Large | Drop 1 |
| 5 | Combat Arena + Trader's Hall | Large | Drop 1 |
| 6 | Crafter's Workshop + Crew Quarters | Medium | Drop 1 |
| 7 | Jedi Enclave + Bounty Office | Medium | Drop 1 |
| 8 | Planetary discovery quests (3 planets) | Small | Planet ground rooms |
| 9 | Smuggler's Run + Hunter's Mark chains | Medium | Multi-planet travel works |
| 10 | Artisan's Forge + Underworld chains | Medium | Crafting + smuggling live |
| 11 | Rebel Cell + Imperial Service chains | Medium | Zone influence live (it is) |
| 12 | All completion rewards, Grand Tour, titles | Small | Drops 2–11 |

Drops 4–7 are independent. Drops 9–11 are independent of each other. Drop 3 (starter chain) remains the highest-value item after the core — zero new rooms, massive impact on new player retention.

**Priority ordering for maximum impact:**
1. Drop 1–3 first (engine + core + starter chain). This is the minimum viable tutorial.
2. Drop 4 (Space Academy) next — space is the deepest system and most needs guided introduction.
3. Drop 8 (planetary discovery) whenever planet ground rooms exist.
4. Drops 9–11 (profession chains) are endgame content and can roll out over time.

---

*"Your eyes can deceive you. Don't trust them." — Obi-Wan Kenobi*

*The best tutorial teaches you to trust your instincts, not your tutorial.*

*End of design document.*
