# Space System Overhaul v3 — Design Document
## SW_MUSH · April 16, 2026 · Opus Analysis Session

**Core principle: Space is not a minigame.** It's where smugglers run
cargo, traders build empires, bounty hunters chase marks, faction
pilots fight wars, and explorers discover the unknown. Each archetype
has a primary activity loop that earns credits, CP, and reputation.
Random encounters are *seasoning* — they add texture to the journey,
not the reason for the journey. A player should log in knowing "today
I'm running spice to Kessel" or "today I'm hunting that bounty in
Nar Shaddaa space," not "today I'll fly around and see what random
events pop up."

Web-first event design; Telnet graceful degradation.

---

## Table of Contents

0. [Archetype Space Loops — The Main Course](#0-archetype-space-loops)
1. [Current State Diagnosis](#1-current-state-diagnosis)
2. [Design Principles](#2-design-principles)
3. [The Grid Question — Range Bands vs. 2D Grid](#3-the-grid-question)
4. [Space Security Zones — The CONCORD Question](#4-space-security-zones)
5. [Event Architecture Overhaul](#5-event-architecture-overhaul)
6. [Encounter Type Catalogue](#6-encounter-type-catalogue)
7. [NPC Combat AI for Space](#7-npc-combat-ai-for-space)
8. [Crew Station Engagement](#8-crew-station-engagement)
9. [Web Client Space Experience](#9-web-client-space-experience)
10. [Telnet Graceful Degradation](#10-telnet-graceful-degradation)
11. [Economy Integration](#11-economy-integration)
12. [Director AI Integration](#12-director-ai-integration)
13. [Implementation Plan](#13-implementation-plan)
14. [File Map & Architectural Changes](#14-file-map)
15. [Migration & Compatibility](#15-migration)

---

## 0. Archetype Space Loops — The Main Course

Every player archetype needs a clear answer to: **"Why am I flying
today, and how does it grow my character?"** Random encounters exist
to make the journey interesting, but the *destination* — the thing the
player chose to do — is where credits, CP, and progression come from.

### 0.1 The Smuggler

**Primary loop (EXISTS — smuggling system):**
Accept job at board → fly to destination planet → evade/bluff patrols
→ deliver cargo → earn credits (200–15,000cr depending on tier/route).

**How encounters serve the loop:** Patrol encounters ARE the smuggling
gameplay. A smuggler choosing "bluff" vs "run" vs "hide" when carrying
Tier 3 spice is the tensest moment in the game. The encounter system
doesn't interrupt the smuggler — it IS the smuggler's challenge.

**What's missing:** Nothing fundamental. The encounter redesign (Drop 2)
makes the patrol interaction richer. The smuggling system is the most
complete archetype loop in space.

**Income target:** 2,000–8,000 cr/hr (already tuned in smuggling.py).

### 0.2 The Trader

**Primary loop (EXISTS — trading system):**
Check `market` prices → buy trade goods at source planet (50% price) →
fly to demand planet → sell at 200% price → profit scales with cargo
capacity and Bargain skill.

**How encounters serve the loop:** Pirates are the trader's risk.
Patrols are a mild nuisance (traders run clean). The security zone
system (Drop 0) creates geographic trade-offs: the Corellian Trade
Spine is heavily patrolled (safe from pirates, but slower due to
inspections) while the Hutt Space corridor is lawless (fast, but
pirates). Traders pick routes based on risk tolerance.

**What's missing:** The trade goods economy is broken — static
multipliers create a "solved game" at 120x design target income
(economy_audit_v1.md). Dynamic supply pools, Bargain skill gates, and
per-planet inventory limits are needed (designed but unbuilt). Until
the economy hardening ships, trading is not a balanced loop. This is
a Priority A fix already on the roadmap, not a space overhaul item.

**Income target:** 2,000–5,000 cr/hr (after economy hardening).

### 0.3 The Bounty Hunter

**Primary loop (PARTIAL — bounty board exists, space pursuit does not):**
Claim bounty contract → track target (Streetwise/Search check) →
travel to target's location → engage target → collect bounty.

**Ground bounties work.** Space bounties don't — the bounty hunter NPC
traffic ship spawns, hails the target, then goes idle. No actual
pursuit or combat. Player-vs-player bounty hunting in space requires
the PvP consent system to work with ship combat (it does, in lawless
zones).

**How encounters serve the loop:** The bounty hunter encounter (Drop 7)
gives NPC bounty targets a space chase sequence. But the real game
for bounty hunter PCs is pursuing other PCs — encounters are the
NPC-driven version for when no PC targets are available.

**What's missing:** NPC space combat AI (Drop 3) is prerequisite for
bounty hunter NPCs to actually fight. Player bounty hunting in space
works mechanically (fire command + PvP consent in lawless zones) but
lacks pursuit mechanics — a target can just hyperspace away. Consider:
interdiction (preventing hyperspace jump), transponder scanning
(finding which zone a target is in), and pursuit across zone
transitions.

**Income target:** 500–10,000 cr per bounty (already tuned in
bounty_board.py, scales with tier).

### 0.4 The Faction Pilot

**Primary loop (PARTIAL — space missions exist but are thin):**
Accept faction mission from board → fly to mission zone → complete
objective (patrol/escort/intercept/survey) → earn credits + faction
reputation.

**Four space mission types exist:** Patrol (hold a zone for 120 ticks),
Escort (protect NPC trader), Intercept (destroy N hostiles), Survey
(resolve an anomaly). These are the right concepts but the
implementation is lightweight — patrol is "sit in a zone and wait,"
escort has no actual escort AI, intercept requires NPC combat that
doesn't exist yet.

**How encounters serve the loop:** Encounters that happen DURING a
faction mission add challenge and narrative. A patrol mission where
pirates show up is more interesting than one where you sit idle. An
escort mission where you have to fight off attackers is the core
fantasy. The encounter system provides the hostile NPCs that make
faction missions meaningful.

**What's missing:** Faction reputation system (designed in
faction_reputation_design_v1.md, unbuilt). Without reputation, faction
missions pay credits but don't advance standing. Also: escort missions
need a protected NPC ship that moves through zones and can be attacked.
Intercept missions need NPC space combat AI (Drop 3).

**Income target:** 300–2,500 cr per mission (already tuned). Reputation
is the real reward — higher faction standing unlocks gear, ships,
missions, and territorial benefits.

### 0.5 The Explorer

**Primary loop (PARTIAL — anomaly scanning exists, endpoints are stubs):**
Fly to frontier space → `deepscan` to find anomalies → resolve through
successive scans → investigate → earn salvage/components/credits.

**The scanning loop is the best-designed piece of the space system.**
Iterative sensor sweeps that narrow from vague → partial → resolved
is genuine detective work. But the payoff is thin — most anomaly
endpoints are unimplemented (pirate nests don't spawn pirates,
distress signals don't have rescue mechanics, hidden caches don't
have loot tables).

**How encounters serve the loop:** Anomaly encounters (Drop 8) complete
the exploration loop. The encounter framework provides the branching
outcomes when you arrive at an anomaly — pirate ambush, rescue
mission, salvage haul, Imperial sting. The security zone system
(Drop 0) makes exploration rewarding: lawless space has 2x anomaly
quality and +50% spawn rate, creating a genuine reason to fly
dangerous routes.

**What's missing:** Anomaly encounter completion (Drop 8), salvage loot
tables connected to the crafting pipeline, rare discovery types that
can't be found any other way (giving explorers economic value to other
players).

**Income target:** 1,000–4,000 cr/hr from salvage + rare components
(crafting value exceeds raw credit value).

### 0.6 The Casual / Multi-Role Player

Most players won't specialize — they'll do missions one day, smuggle
the next, trade when they need credits for a ship upgrade, and explore
when they feel like it. The space system needs to serve this player by
making all activities accessible without requiring mastery of any one.

**The mission board is the casual player's primary loop.** It offers
variety (14 types including 4 space types), always-available work, and
predictable income. Random encounters during mission travel add
variety without requiring the player to seek them out.

### 0.7 Encounter Frequency — Seasoning, Not the Meal

Given the loops above, random encounter frequency should be:

**During active loops (smuggling run, trade route, faction mission):**
Encounters should feel like complications in your story, not
interruptions. Target: 0-1 encounter per trip between planets. A
smuggler on a Tatooine→Kessel spice run might hit one patrol. A trader
on the Corellian Trade Spine might pass through cleanly. The zone
security system handles this naturally — secured space has more
patrols but fewer pirates; lawless space is the reverse.

**During idle/exploration:**
Encounters are slightly more frequent because the player isn't
pursuing a specific objective. Target: 1-2 encounters per 15 minutes
of active flying. But even here, encounters should feel like
*discoveries* (anomalies, distress signals, mysterious contacts) more
than *threats* (patrols, pirates). The exploration loop is about
finding things, not surviving things.

**Encounter cooldowns (revised from §5.6):**

```
Per-ship cooldowns (seconds):
  patrol:     600  (10 min) — but skipped if ship has "cleared" status
  pirate:     900  (15 min) — reduced in lawless zones
  any_type:   240  (4 min)  — hard floor between any encounters

Per-zone cap: 1 active encounter at a time
```

**Critical rule: encounters never interrupt hyperspace.** The player
chose their destination and committed. The encounter window is zone
arrival and zone loitering. Hyperspace is downtime — check your
cargo, plan your next move, chat with crew.

### 0.8 What This Reframing Changes About Implementation Priority

The encounter system (Drops 1-2) is infrastructure. It's correct to
build it. But the priority order for making space *engaging* is:

1. **Economy hardening** (Priority A, already designed) — Fix the trade
   goods "solved game." Until trading works at design-target income
   rates, the trader loop is broken.

2. **NPC space combat AI** (Drop 3) — Without this, pirate encounters,
   bounty hunter pursuits, intercept missions, and pirate nest
   anomalies all dead-end at "NPC announces attack, goes idle." This
   is the single biggest gap in the space system.

3. **Anomaly encounter completion** (Drop 8) — Finish the exploration
   endpoints. The scanning loop is good; the payoff is missing.

4. **Faction reputation system** (designed, unbuilt) — Without
   reputation, faction missions are just credit-earning. With
   reputation, they're progression.

5. **Additional encounter types** (Drops 5-7) — Distress signals,
   mechanical difficulties, bounty hunter redesign. These add texture
   but the core loops work without them.

6. **Web client encounter UI** (Drop 9) — Visual polish for encounters
   that already work mechanically.

---

## 1. Current State Diagnosis

### What's Strong (Keep)

The mechanical foundation is excellent and WEG-compliant:

- **Combat engine**: Full R&E Chapter 10 implementation — scale modifiers,
  fire arcs, ion weapons, tractor beams, shield arc management, damage
  control, evasive maneuvers with hazard table. This doesn't need
  redesigning; it needs *opponents*.

- **Crew stations**: 7 stations (Pilot, Copilot, Gunner, Engineer,
  Navigator, Commander, Sensors) with distinct capabilities. The
  architecture is sound; the problem is that events don't use most of them.

- **Zone topology**: 16 zones across 4 planets with hyperspace lanes,
  hazard zones, and docking. The galaxy structure works.

- **Ship customization**: Modifications, power allocation, captain's
  orders, quirks, transponder codes. Deep systems that reward investment.

- **Space HUD**: `build_space_state()` already sends rich JSON to the web
  client — zone info, crew, hull/shields, contacts, anomalies. The
  client already has a radar SVG with range rings and a zone map.

- **Anomaly scanning**: The `deepscan` → iterative resolution → investigate
  loop is the right design pattern. It just needs completed encounters
  at the end.

### What's Broken (Fix)

**Problem 1: Events are taxes, not gameplay.**

Every space event follows the same anti-pattern:
```
NPC spawns → timer starts → text message appears → player types response
(or doesn't) → credits deducted → NPC leaves
```

There are no meaningful choices, no skill checks the player can influence,
no branching outcomes, no rewards for engaging well. Specifically:

- **Imperial inspections**: 30-second reply timer. Any message with a
  compliance keyword = cleared. No message = boarded, credits taken.
  Clean ships get fined for "failure to respond" regardless. No skill
  check. No way to avoid, evade, or cleverly handle the situation.

- **Pirate demands**: Tail for 30s, demand 500-1500cr, player pays or
  pirate announces "open fire" — then goes idle. The ATTACKING state
  is unimplemented. Pirates are a credit tax with flavor text.

- **Bounty hunters**: Same pattern as pirates. Tail, hail, timeout,
  "lethal force authorized," go idle. No fight ever happens.

**Problem 2: NPC traffic ships can't actually fight.**

The combat engine exists. The NPC traffic ships have crew skills and
ship templates. But there is no code path where a TrafficShip enters
the SpaceGrid and exchanges fire with a player ship. The
`TrafficState.ATTACKING` enum value exists but is never used. Every
hostile encounter terminates at "announces attack" and then the NPC
reverts to IDLE.

**Problem 3: Anomaly encounters are stubs.**

The scanning loop works beautifully. But when you `course anomaly <id>`
to investigate:
- Pirate nests say "Expect 2-3 hostiles" but spawn nothing
- Distress signals mention "Perception check to detect ambush" but
  have no check
- Imperial dead drops mention "slicing check" but aren't wired
- Only derelicts (salvage) have a working endpoint

**Problem 4: Only one crew member does anything during events.**

Events address "the ship" as a unit. The pilot might steer, but the
sensors operator has nothing to do during an inspection, the engineer
has nothing to do during a pirate encounter, the commander has nothing
to do ever outside of issuing orders. Multi-crew ships should feel like
multi-crew experiences.

**Problem 5: Space has no moments.**

The current space experience is: launch → `course` to next zone → wait
→ `course` again → wait → `hyperspace` → wait → arrive → land. Anything
that interrupts this (patrol, pirate) is an annoyance, not an adventure.
Nothing in space produces the feeling of "I can't believe that just
happened" or "that was a close call."

Galaxy Guide 6: Tramp Freighters (WEG40027) literally lists the kinds
of events that should happen in space: pirates where you use cunning,
mechanical difficulties, mysterious other ships, damaged cargo, Imperial
customs with real stakes, distress signals that could be traps. The WEG
designers understood that space travel events are mini-adventures with
branching outcomes. Our implementation reduced them to timers with
credit penalties.

---

## 2. Design Principles

### 2.1 Web-First, Telnet-Functional

Features are designed for the web client's capabilities first. The web
client can display: choice panels with buttons, visual radar updates,
countdown timers, crew station action prompts, animated state transitions.

Telnet players receive the same content as numbered text menus and
typed commands. Everything *works* on Telnet, but the web client is
where the experience is designed to shine. No feature is vetoed because
Telnet can't make it pretty.

### 2.2 Choices Over Timers

Every event must present at least two meaningfully different options.
"Reply within 30 seconds or lose credits" is not a choice. "Comply
(safe), Bluff (Con check — risky but keeps contraband), or Run
(piloting chase — dangerous but no inspection)" is a choice.

### 2.3 Crew Engagement

Events that involve the whole ship should give multiple crew stations
something to do. Not every event needs all 7 stations, but any event
lasting more than one exchange should involve at least 2-3 stations.

### 2.4 Risk/Reward, Not Just Risk

Players should sometimes be *excited* to see an event trigger. A
distress signal should make them think "this could be profitable" not
just "this might cost me credits." Encounters should have upside
outcomes — salvage, reputation, information, quest hooks, rare
components — not just downside avoidance.

### 2.5 NPCs That Fight

If an NPC threatens to shoot, it must be capable of shooting. Every
hostile NPC encounter must have a code path that puts the NPC on the
SpaceGrid and runs actual combat rounds. This means the NPC space
combat AI needs to exist.

### 2.6 WEG Compliance Where It Matters

The D6 dice engine, scale modifiers, skill checks, damage tables — all
stay WEG R&E compliant. The event *structure* (branching choices,
multi-station engagement) is a game design decision, not a rules
question. WEG doesn't specify how a MUSH should present encounters;
their sourcebooks assume a human GM making real-time narrative choices.
We're building the automated equivalent.

### 2.7 Let Galaxy Guide 6 Be the Guide

GG6: Tramp Freighters is the single most relevant WEG sourcebook for
this redesign. Its "Events in Space" section describes exactly what we
should be building. Its adventure hooks are the templates for our
procedural encounters.

---

## 3. The Grid Question — Range Bands vs. 2D Grid

### What WEG R&E Actually Says

WEG D6 R&E does **not** use a grid for space combat. The core rules
(Chapter 10, "Space Travel and Combat") use **abstract range bands**:
Point Blank, Short, Medium, Long, and Extreme — with difficulty
modifiers applied to attack rolls. Movement is handled through
**opposed piloting rolls** to close range, flee, tail, or outmaneuver.
There are no hex grids, no coordinate systems, no facing angles beyond
the abstract front/rear/flank relative positioning.

The supplementary Star Warriors board game (referenced in our hazard
table) *does* use a hex grid, but WEG explicitly notes that the RPG
uses simplified range bands rather than the board game's tactical map.

The R&E rulebook's "Three-Dimensional Combat" sidebar (p.101) provides
an optional hack for measuring 3D distances with approximate geometry,
but this is for *vehicular* combat with known meter distances — not
the standard approach for starship engagements.

### What We Currently Have

Our `SpaceGrid` is already an abstract range-band system, not a grid.
It tracks:
- Pairwise range bands (Close/Short/Medium/Long/Extreme) between ships
- Relative positions (Front/Rear/Flank) for fire arc resolution
- Speed values for maneuver advantage calculations

This is faithful to WEG R&E. Maneuvers use opposed piloting rolls to
shift range bands or change relative positions. The radar SVG in the
web client already visualizes this — concentric rings labeled
Close/Short/Medium/Long with blips placed at appropriate distances.

### Should We Add a 2D Grid?

**Recommendation: No.** Here's why:

**WEG compliance**: A 2D grid would be a departure from R&E rules. The
abstract range band system *is* how WEG D6 starship combat works. A
grid would require inventing movement point costs, facing mechanics,
and hex-based fire arc calculations that don't exist in the ruleset.
This would be building a different game bolted onto WEG's dice engine.

**Gameplay pacing**: MUSH combat is asynchronous — players type commands
at their own pace, sometimes with multi-second gaps. Grid-based tactical
movement requires simultaneous action resolution and becomes tedious
when each "move one hex" requires a typed command. The abstract system
("close range on target" as a single opposed roll) is faster and more
dramatic.

**Visual experience**: The radar visualization of range bands is
actually more visually engaging than a sparse 2D grid with 2-3 dots on
it. The concentric rings with sweep animation, blip colors, and range
labels *feel* like Star Wars sensor screens. A hex grid would feel
like a board game.

**Complexity budget**: Implementing a proper 2D grid with pathfinding,
collision, movement costs, and facing would be a significant engineering
effort that doesn't make the game more fun. The range band system is
elegant precisely because it abstracts away the tedious parts of
spatial reasoning and keeps the focus on dramatic choices.

### What We Should Improve About the Current System

Rather than adding a grid, we should make the existing range band
system *more visible and tactically interesting*:

1. **Radar visualization upgrades**: Show relative positions (front/rear)
   as angular placement on the radar, not just radial distance. A ship
   on your tail should appear at the bottom of the radar; one in front,
   at the top. This gives spatial intuition without a grid.

2. **Range band tactical previews**: Before committing to a maneuver,
   show the player "If you succeed: range shifts from Long to Medium,
   giving you -5 difficulty to fire. If you fail: they get a free tail
   attempt." This makes the abstract system legible.

3. **Zone-level map with ship positions**: The zone map already exists.
   Show player ships and NPC contacts as icons within their current
   zone. This provides the "where am I in the galaxy" context that a
   local combat grid can't.

4. **Engagement clustering**: When multiple ships are in a zone, group
   them into "engagements" — local clusters of ships in combat. This
   prevents the confusion of 8 ships all at different range bands to
   each other without needing a grid to sort it out.

**Bottom line**: The abstract range band system is WEG-correct, works
well for asynchronous text gameplay, and can be made visually compelling
on the web client. A 2D grid would be a large engineering investment
that moves us away from the source material without making the game
more fun.

---

## 4. Space Security Zones — The CONCORD Question

### 4.1 What We Have Now

The ground game has a rich, Director-integrated security zone system
(engine/security.py) with three tiers: SECURED (no combat), CONTESTED
(NPC combat + consensual PvP), and LAWLESS (unrestricted PvP). This
system is deeply wired: the Director AI dynamically shifts security
based on faction influence (criminal surge downgrades a tier, Imperial
crackdown upgrades a tier), territory control lets player orgs claim
lawless rooms and upgrade them to contested for members, and bounty
hunters can bypass PvP consent in contested zones. It's one of the
best-integrated systems in the entire codebase.

Space has a vestigial mapping of this: zone *type* maps to security
level in a hardcoded 4-line function inside `FireCommand`:

```
DOCK            → secured  (no fire)
ORBIT           → contested (PvP needs consent)
HYPERSPACE_LANE → contested
DEEP_SPACE      → lawless  (unrestricted)
```

That's it. No Director integration. No faction influence overlay. No
territory claiming. No dynamic shifts. No per-planet variation. Kessel
orbit has the same security level as Corellia orbit, despite Kessel
being a lawless spice mining hellhole and Corellia being a Core World
with CorSec patrols. Every deep space zone is identically lawless
regardless of whether it's a well-patrolled shipping lane or the
uncharted void beyond the Maw.

### 4.2 The EVE Analogy — And Where We Diverge

EVE Online's security system is the single most consequential design
decision in that game. High-sec (CONCORD protection, suicide ganking is
expensive), low-sec (gate guns but no CONCORD, PvP with consequences),
and null-sec (total anarchy, player sovereignty) create radically
different gameplay experiences in different parts of the same galaxy.
The security status of a system determines encounter rates, NPC
difficulty, resource quality, patrol presence, and economic opportunity.

Our ground system already mirrors this well — SECURED/CONTESTED/LAWLESS
is high-sec/low-sec/null-sec with Star Wars flavor. But space doesn't
leverage the same principles, and it should. The key EVE insight is
that **security status isn't just a PvP toggle — it's the master knob
that tunes the entire gameplay experience of a region.**

Where we diverge from EVE: we don't need the granular 0.0-1.0 security
rating. Three tiers work well for our scale (16 zones, 4 planets). And
we don't need CONCORD-style instant NPC response — our patrol encounter
system (§7) provides a proportional response based on security level.

### 4.3 Per-Planet Space Security Profiles

Each planet should have a distinct security character that affects
encounter rates, NPC types, patrol response, economic opportunity, and
the general *feel* of flying in that space. This is the biggest
gameplay impact of this section — it transforms the galaxy from "16
identical zones with different names" into 4 genuinely different
regions to fly through.

**Corellia — Core World (High Security)**

Corellia is a Core World with CorSec patrols and CEC shipyard defense
platforms. Flying here should feel *safe* — and also heavily monitored.

```python
CORELLIA_SECURITY = {
    "corellia_dock":       SecurityLevel.SECURED,
    "corellia_orbit":      SecurityLevel.SECURED,   # CorSec + CEC defense grid
    "corellia_deep_space": SecurityLevel.CONTESTED,
    "corellian_trade_spine": SecurityLevel.CONTESTED,  # Major trade artery
}
# Effects:
#   - Patrol encounter rate: HIGH (30-40% per zone visit)
#   - Patrol profile: Imperial + CorSec (dual authority)
#   - Pirate encounter rate: VERY LOW (5%)
#   - Smuggling patrol check: +10 difficulty
#   - PvP: consent required almost everywhere
#   - NPC response to crime: fast (patrol arrives in 30 seconds)
#   - Economy: legal trade is profitable, smuggling is very risky
#   - Anomaly quality: low (picked clean by corporate surveyors)
```

**Tatooine — Outer Rim (Medium Security)**

The Outer Rim. Imperial presence exists but is thin and indifferent.
The sweet spot where legal commerce and crime coexist.

```python
TATOOINE_SECURITY = {
    "tatooine_dock":       SecurityLevel.SECURED,  # Mos Eisley port control
    "tatooine_orbit":      SecurityLevel.CONTESTED,
    "tatooine_deep_space": SecurityLevel.LAWLESS,
    "outer_rim_lane_1":    SecurityLevel.CONTESTED,
}
# Effects:
#   - Patrol rate: MODERATE (15-20%)
#   - Pirate rate: MODERATE (15-20%)
#   - Smuggling difficulty: baseline
#   - PvP: lawless in deep space, contested in orbit
#   - Economy: balanced risk/reward
#   - Anomaly quality: medium
```

**Nar Shaddaa — Hutt Space (Low Security)**

The Smuggler's Moon. Imperial authority is nominal at best. Hutt
enforcers maintain their own kind of order, which is to say: order
that benefits the Hutts and nobody else.

```python
NAR_SHADDAA_SECURITY = {
    "nar_shaddaa_dock":       SecurityLevel.CONTESTED,  # NOT secured — Hutt rules
    "nar_shaddaa_orbit":      SecurityLevel.CONTESTED,   # Hutt barges, not Imperials
    "nar_shaddaa_deep_space": SecurityLevel.LAWLESS,
    "outer_rim_lane_2":       SecurityLevel.LAWLESS,     # Hutt corridor — no law
}
# Effects:
#   - Imperial patrol rate: VERY LOW (5%)
#   - Hutt patrol rate: MODERATE (15%) — but Hutt patrols don't care
#     about contraband, only about Hutt interests
#   - Pirate rate: HIGH (25-30%)
#   - Smuggling difficulty: LOW (Hutts don't inspect for spice)
#   - PvP: lawless almost everywhere
#   - NPC response to crime: Hutt enforcers only respond if you
#     attack Hutt-flagged ships
#   - Economy: smuggling paradise, legitimate trade is dangerous
#   - Anomaly quality: high (unpatrolled space = unexplored)
```

**Kessel — Frontier (Minimal Security)**

The Maw. Spice mines. Imperial garrison exists but focuses on the
mines, not on controlling open space. The most dangerous region.

```python
KESSEL_SECURITY = {
    "kessel_dock":      SecurityLevel.CONTESTED,  # Imperial garrison present
    "kessel_orbit":     SecurityLevel.CONTESTED,   # Garrison patrols
    "kessel_approach":  SecurityLevel.LAWLESS,     # The Maw corridor
    "outer_rim_lane_3": SecurityLevel.LAWLESS,     # Wild space
}
# Effects:
#   - Imperial patrol rate: LOW (10%) — garrison stays near the mines
#   - Pirate rate: HIGH (25%)
#   - Bounty hunter rate: HIGH (20%) — criminals flee here
#   - Smuggling difficulty: baseline (they care about spice leaving,
#     not contraband arriving)
#   - PvP: lawless except docked/orbit
#   - Environment hazard: Kessel Approach has asteroid density + nav
#     modifier (already implemented)
#   - Economy: spice runs are extremely profitable but dangerous
#   - Anomaly quality: VERY HIGH (unexplored, hazardous, rewarding)
```

### 4.4 How Security Level Affects Encounters

This is the core mechanical payoff. The security level of a zone
becomes the master tuning parameter for the encounter system (§6):

**Encounter spawn rates by security level:**

| Security | Patrol Rate | Pirate Rate | Distress | Anomaly Quality | Salvage Value |
|----------|-------------|-------------|----------|-----------------|---------------|
| SECURED  | 35% | 2% | 5% | Low (common parts) | 50% base |
| CONTESTED | 15% | 15% | 15% | Medium (useful parts) | 100% base |
| LAWLESS  | 5% | 30% | 10% | High (rare components) | 200% base |

This creates the EVE-style risk/reward gradient: safe space has frequent
patrols (annoying for smugglers, protective for traders) but poor loot.
Dangerous space has pirates and PvP risk but the best anomalies, the
richest salvage, and freedom from Imperial interference.

**Patrol behavior by security level:**

- SECURED: Patrols are aggressive. Short hail timeout (45s). Bluff
  difficulty is Hard (20). Running triggers immediate pursuit + backup.
  CorSec/Imperial patrols are competent (4D+2 skill).

- CONTESTED: Patrols are present but spread thin. Standard hail timeout
  (60s). Bluff difficulty is Moderate (15). Running triggers pursuit
  but no backup. Standard patrol skill (3D+2).

- LAWLESS: Patrols are rare and cautious. Long hail timeout (90s).
  Bluff difficulty is Easy (10) — they don't want trouble either.
  Running is almost always successful — lone patrol won't pursue into
  lawless space. Low patrol skill (3D).

**PvP rules by security level (unchanged from current, but now explicit):**

- SECURED: No ship-to-ship fire allowed. Defense grid.
- CONTESTED: Fire allowed with PvP consent (challenge/accept). Bounty
  hunter override applies.
- LAWLESS: Unrestricted PvP. Fire at will.

### 4.5 Director AI Dynamic Overlays — Space Edition

The ground Director already shifts security based on faction influence.
Space should have the same capability:

**Imperial crackdown (patrol_spawn_mult effect):**
When the Director raises the alert level for a planet (already tracked
via `world_events.py`), the orbital and deep space zones around that
planet shift up one security tier:
- Deep space LAWLESS → CONTESTED (patrols extend range)
- Orbit CONTESTED → SECURED (lockdown, no combat near the planet)

**Criminal surge / pirate activity:**
When the Director detects high criminal/smuggling activity in a region,
the reverse happens:
- Orbit CONTESTED → remains CONTESTED but patrol rate drops by half
- Patrol NPC skill drops by 1D (overtaxed, demoralized)
- Pirate spawn rate increases by 50%

**Faction territory in space (future — Phase 2):**
If/when faction territory control extends to space, an org that
controls a planet's docking facilities could claim orbital zones,
providing security upgrades for faction members (parallel to ground
territory claiming where lawless → contested for org members). This
is a natural extension of the existing territory system and would
give orgs a reason to invest in space infrastructure. Not in scope
for this overhaul but the security architecture should support it.

### 4.6 Implementation Notes

**Minimal new code required.** The ground `engine/security.py` already
has the full framework: `SecurityLevel` enum, `get_effective_security()`
with Director overlays, transient overrides, claim upgrades. Space
security currently bypasses all of this with a 4-line zone-type check.

The fix is to:

1. Assign base security levels to each space zone in the `ZONES` dict
   (add a `security` field to the `Zone` dataclass), using the
   per-planet profiles from §4.3.

2. Replace the hardcoded `_check_space_security()` in `FireCommand`
   with a call to a new `get_space_security(zone_id)` that reads
   the zone's base security + applies Director overlay.

3. Wire encounter spawn rates to use the zone's effective security
   level as the tuning parameter (§4.4 table).

4. Pipe planet-level Director alerts into space security overlays.

This is a **Drop 0** — it should be implemented before any encounter
redesign because the encounter spawn rates depend on it. Estimated
effort: small (200-300 lines). Most of the work is data (assigning
security levels to zones) rather than new logic.

### 4.7 What This Changes for Players

Before: every deep space zone feels identical. Tatooine deep space
and Kessel approach are mechanically the same. Corellia orbit is as
lawless as Nar Shaddaa orbit. The galaxy has no geographic personality.

After: flying to Nar Shaddaa feels different from flying to Corellia.
Nar Shaddaa approach is dangerous — pirates, no patrols, great loot if
you survive. Corellia approach is safe — heavy patrols, no pirates,
but also no opportunity for a quick score and your smuggling cargo is
at maximum risk. Kessel is the wild frontier — environmental hazards
AND pirates AND rare resources. Tatooine is the middle ground where
new players learn the ropes.

Players develop preferences. Smugglers prefer the Nar Shaddaa corridor.
Traders stick to the Corellian Trade Spine. Combat pilots hunt pirates
in Kessel deep space. Each planet becomes a *destination with character*,
not just a different set of room descriptions on the ground.

### 4.8 Ship Class and Encounter Eligibility

Ships are classified by size/type, which determines which encounter
types can target them. This prevents absurdities like boarding a
TIE Fighter or a cargo emergency in an X-Wing.

**Ship classes** (derived from template data — crew count, passengers,
cargo capacity, scale):

| Class | Template Examples | Boardable? | Cargo Events? | Interior Encounters? |
|-------|-------------------|------------|---------------|----------------------|
| `fighter` | X-Wing, TIE, A-Wing, Z-95 | No | No | No |
| `patrol_craft` | Firespray | No | Limited | No |
| `light_freighter` | YT-1300, Ghtroc, YT-2400 | Yes | Yes | Yes |
| `shuttle` | Lambda, Sentinel | Yes | Yes | Yes |
| `capital` | Corvette, Nebulon-B, ISD | Yes | Yes | Yes |

Classification logic (added to ShipTemplate):
- `passengers == 0 and cargo <= 10` → fighter
- `passengers > 0 and cargo <= 50 and crew == 1` → patrol_craft
- `scale == "capital"` → capital
- `passengers >= 20` → shuttle
- else → light_freighter

Encounter eligibility by ship class:
- **Imperial boarding**: light_freighter, shuttle, capital only
- **Pirate boarding threat**: same (fighters get "pirate demands credits
  via comms" but no physical boarding)
- **Cargo emergency**: light_freighter, shuttle, capital only
- **Mynock colony**: all classes (mynocks cling to hull — external,
  not interior encounter; fighters get hull damage, freighters get
  the "investigate or vent" choice)
- **Stowaway**: light_freighter, shuttle, capital only
- **Mechanical difficulty**: all classes

**Future: multi-room interiors.** Currently all ships are single-room
(bridge only). The architecture supports multi-room layouts (rooms +
exits), and light freighters and larger ships should eventually have
bridge, cargo hold, engine room, crew quarters, and turret gunwells as
separate rooms. This requires auto-generating rooms on ship creation,
managing inter-room exits, routing station assignments to specific
rooms, and an intercom/comlink system for crew communication across
rooms. This is a separate design effort that builds on top of the
encounter system — the encounter framework should be designed so that
multi-room interiors are a natural extension, not a rewrite.

---

### 5.1 The SpaceEncounter Framework

Replace the current "timer → text → credit deduction" pattern with a
structured encounter system that supports branching choices, multi-station
engagement, and actual combat escalation.

```python
@dataclass
class SpaceEncounter:
    """A structured space event with branching outcomes."""
    id: str                          # unique encounter ID
    encounter_type: str              # "patrol", "pirate", "distress", etc.
    zone_id: str                     # zone where this is happening
    phase: int = 0                   # current phase of the encounter
    state: str = "pending"           # pending/active/resolved/expired
    npc_ship_id: Optional[int] = None  # traffic ship driving this encounter
    target_ship_id: Optional[int] = None  # player ship involved
    choices_presented: bool = False
    choice_deadline: float = 0.0     # timestamp, 0 = no deadline
    crew_actions: dict = field(default_factory=dict)
    # {station: {action: str, result: dict}} — tracks what each station did
    outcome: str = ""                # final outcome key
    rewards: dict = field(default_factory=dict)
    penalties: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)

    def time_remaining(self) -> float:
        if self.choice_deadline <= 0:
            return 0
        return max(0, self.choice_deadline - time.time())
```

### 5.2 Choice Presentation

When an encounter reaches a decision point, it sends a `space_choices`
WebSocket message to the relevant sessions:

```python
# WebSocket payload for a choice panel
{
    "type": "space_choices",
    "encounter_id": "enc-abc123",
    "prompt": "Imperial patrol is hailing you. How do you respond?",
    "station": "commander",  # which station should decide (or "any")
    "deadline_secs": 60,     # 0 = no time pressure
    "choices": [
        {
            "key": "comply",
            "label": "Comply",
            "description": "Transmit identification codes and submit to inspection.",
            "risk": "none",
            "icon": "shield-check",
            "station_hint": null
        },
        {
            "key": "bluff",
            "label": "Bluff",
            "description": "Fake your codes. Requires Con check (Moderate).",
            "risk": "medium",
            "icon": "mask",
            "station_hint": "commander"
        },
        {
            "key": "run",
            "label": "Run for It",
            "description": "Hit the throttle. Requires Piloting check to escape. They will pursue.",
            "risk": "high",
            "icon": "rocket",
            "station_hint": "pilot"
        },
        {
            "key": "hide",
            "label": "Go Dark",
            "description": "Kill power and hope they pass. Requires sensors offline + Sneak (Difficult).",
            "risk": "high",
            "icon": "eye-off",
            "station_hint": "engineer"
        }
    ]
}
```

**Telnet equivalent:**

```
  [IMPERIAL PATROL] An Imperial patrol cruiser is hailing you.
  "Attention freighter — transmit identification codes immediately."

  How do you respond?
    1) Comply — transmit codes, submit to inspection (safe)
    2) Bluff — fake codes (Con check, Moderate difficulty)
    3) Run   — hit the throttle (Piloting chase, they will pursue)
    4) Hide  — go dark, kill power (Sneak, Difficult)

  Type: respond 1, respond 2, respond 3, or respond 4
  You have 60 seconds before they board by force.
```

### 5.3 The `respond` Command

New command: `respond <number or key>`. Selects a choice for the active
encounter. Can also be triggered by web client button clicks (which send
the command string via WebSocket).

```
respond 2          — select choice #2 (Bluff)
respond comply     — select choice by key
respond bluff      — same
```

If the encounter specifies a `station_hint` and a different station is
occupied, the response is processed by that station's character (using
their skills). If the hinted station is empty, the responding player's
skills are used (solo ships work fine).

### 5.4 Encounter Phases

Complex encounters have multiple phases. Each phase can present new
choices or require different crew stations to act.

Example — Imperial Patrol (full encounter):

```
Phase 0: HAIL
  → Patrol enters zone, hails player ship
  → Choice panel: Comply / Bluff / Run / Hide
  → 60-second deadline (doubled from current 30s)

Phase 1a: COMPLY
  → Patrol "boards" — inspection begins
  → If clean ship: cleared, -15 min patrol risk in this zone
  → If smuggling cargo: Con check (Moderate) to hide contraband
    → Success: cleared + contraband safe
    → Failure: cargo confiscated, fine based on WEG40141 class
  → If false transponder: automatic Class 2 infraction

Phase 1b: BLUFF (Commander/anyone — Con skill check)
  → Roll Con vs. Moderate (15) difficulty
  → Success: patrol accepts fake codes, departs. +CP for creativity.
  → Failure: patrol suspicious, demands boarding → Phase 2
  → Critical success: patrol apologizes, warns you about pirates
    in the next zone (intel reward)

Phase 1c: RUN (Pilot — chase sequence)
  → Patrol enters SpaceGrid at Short range, pursuing
  → Player must flee to Extreme range to escape
  → Patrol NPC fights back — fires, attempts to close range
  → If player escapes: patrol logs transponder, +20% risk for 1 hour
  → If player is disabled: forced boarding at Class 3+ infraction
  → Either way: actual space combat with the NPC

Phase 1d: HIDE (Engineer — Stealth sequence)
  → Ship enters silent running automatically
  → Sneak check (Difficult, 20) — OR Sensors check to find a
    masking asteroid/debris field
  → Success: patrol passes through, never detects you. Clean escape.
  → Failure: patrol detects power-down anomaly, investigates →
    forced boarding at +5 difficulty (suspicious behavior)
  → Critical success: you discover an anomaly while hiding
    (reward for choosing the risky option)

Phase 2: FORCED BOARDING (if bluff failed or timeout)
  → Same as current inspection but with skill check for concealment
  → Engineer can attempt to hide contraband (Repair/Technical check)
  → Sensors operator can attempt to scramble the manifest (Computer
    Programming/Security check)
  → Multiple crew members can contribute, each reducing the
    inspection's effective difficulty
```

### 5.5 Encounter Deadlines and Defaults

Deadlines still exist — events can't wait forever. But they're longer
(60-90 seconds instead of 30), and the *default outcome* on timeout is
no longer always the worst case:

- Patrol timeout: boarding (current behavior, but now with skill checks)
- Pirate timeout: combat begins (NPC enters grid and fights)
- Distress signal timeout: signal fades (opportunity lost, no penalty)
- Anomaly encounter timeout: anomaly drifts away (neutral)

The key change: timeout is never the *only* bad outcome. Players who
engage with the choice system always have a path that's better than
timeout, and sometimes timeout is neutral rather than punishing.

### 5.6 Encounter Cooldowns and Frequency

Encounters should feel like events, not spam. New tuning constants:

```python
# Per-ship encounter cooldowns (seconds)
ENCOUNTER_COOLDOWN_PATROL = 600    # 10 minutes between patrol events
ENCOUNTER_COOLDOWN_PIRATE = 900    # 15 minutes between pirate events
ENCOUNTER_COOLDOWN_ANY    = 180    # 3 minutes between ANY events

# Per-zone caps
MAX_ACTIVE_ENCOUNTERS_PER_ZONE = 1  # only one encounter active at a time per zone

# Zone-based spawn rates (replaces current flat timer)
ENCOUNTER_RATES = {
    "dock":            {"patrol": 0.15, "pirate": 0.00, "trader": 0.20},
    "orbit":           {"patrol": 0.20, "pirate": 0.05, "trader": 0.15},
    "deep_space":      {"patrol": 0.05, "pirate": 0.20, "trader": 0.10},
    "hyperspace_lane": {"patrol": 0.10, "pirate": 0.15, "trader": 0.10},
}
```

---

## 6. Encounter Type Catalogue

Each encounter type below includes: trigger conditions, choice tree,
crew station involvement, possible outcomes, and economy impact.

### 6.1 Imperial Patrol

**Source**: WEG Galaxy Guide 6, p.62 — "Imperial Ship" event

**Trigger**: Patrol NPC enters player's zone. Probability modified by
zone type, Director alert level, and player's recent infraction history.

**Choice tree**: See §5.4 above for the full 4-choice branching structure.

**Crew involvement**:
- Commander: decides response strategy, bluff attempts
- Pilot: chase sequence if running
- Engineer: hide contraband, go dark, silent running
- Sensors: scan for patrol backup, scramble manifest
- Navigator: emergency hyperspace jump (risky — hasty entry penalty)

**Outcomes**:
- Clean compliance: cleared status (-15 min patrol risk)
- Successful bluff: no inspection + CP reward
- Successful chase: escaped but flagged (+20% risk for 1 hour)
- Successful hide: clean escape, possible anomaly discovery
- Failed bluff → inspection: cargo checked, WEG40141 fines
- Failed chase → disabled: forced boarding + higher fines
- Failed hide → suspicious boarding: +5 difficulty on concealment

**Economy**: Fines scale with infraction class (100-10,000cr). Successful
bluffs preserve smuggling cargo value. Chase sequences consume fuel.
Cleared status reduces future encounter rates (economic benefit of
compliance).

### 6.2 Pirate Attack

**Source**: WEG GG6, p.62 — "Pirates" event

**Trigger**: Pirate NPC spots player in deep space or hyperspace lane.
Higher probability in Outer Rim zones, near Nar Shaddaa, and the
Kessel Approach. Director "pirate_activity" flag increases spawn rate.

**Choice tree**:

```
Phase 0: DETECTION
  Sensors operator gets "[SENSORS] Contact — unregistered fighter
  adjusting course toward you. Hostile intent probable."
  → 15-second warning before pirate hails

Phase 1: DEMAND
  Pirate hails with credit demand (500-3,000cr based on ship value)
  Choices:
    1) Pay — transfer credits, pirate leaves (safe but expensive)
    2) Negotiate — Bargain check to reduce demand by 25-75%
    3) Fight — weapons hot, pirate enters SpaceGrid
    4) Flee — piloting chase, pirate pursues

Phase 2a: NEGOTIATE (Commander/anyone — Bargain check)
  → Roll Bargain vs. pirate's Willpower
  → Success: demand reduced (margins: 25%/50%/75% based on roll)
  → Failure: pirate offended, attacks immediately (no more talking)
  → Critical: pirate respects you, offers information about a
    hidden cache or upcoming convoy

Phase 2b: FIGHT (all combat stations)
  → Pirate NPC enters SpaceGrid at Short range
  → Full space combat using existing engine
  → Pirate has flee threshold (30% hull)
  → On pirate destruction: salvage wreck + credit bounty (500-1500cr)
  → On pirate flee: pursuit optional (pilot choice)
  → If player is disabled: pirate takes cargo + credits (not kill)

Phase 2c: FLEE (Pilot — chase sequence)
  → Pirate enters SpaceGrid at Short range, closing
  → Player must reach Extreme range OR jump to hyperspace
  → Copilot can assist piloting roll
  → Engineer can divert power to engines (+speed)
  → Navigator can calculate emergency jump (hasty, +10 difficulty)
  → Success: escaped, pirate gives up at Extreme range
  → Failure: pirate closes to Close range, forces combat
```

**Crew involvement**:
- Pilot: flee or combat maneuvering
- Gunner: combat
- Copilot: assist piloting
- Engineer: power management, damage control
- Navigator: emergency jump calculation
- Sensors: detect pirate backup, target lock assistance
- Commander: negotiate, issue tactical orders

**Outcomes**:
- Pay: safe but expensive (credit loss)
- Negotiate success: reduced payment + possible intel
- Fight and win: credit bounty + salvage + CP
- Fight and lose: cargo/credits taken (not killed — pirates want profit)
- Flee success: no cost
- Flee failure: forced into combat

**Economy**: Pirate bounties are a credit faucet (500-1,500cr). Salvage
feeds crafting pipeline. Negotiation preserves capital. The player has
genuine risk/reward calculus: fighting is profitable if you win, paying
is safe, fleeing costs nothing but risks forced combat.

### 6.3 Distress Signal

**Source**: WEG GG6, p.62 — "Distress Signal" event; also anomaly type

**Trigger**: Spawned in deep space and hyperspace lane zones. Always
voluntary — player chooses to investigate or ignore.

**Choice tree**:

```
Phase 0: DETECTION
  "[SENSORS] Distress beacon detected — emergency frequency.
  Origin: 2 zones spinward. Signal is repeating."
  
  Choices:
    1) Investigate — course to the signal source
    2) Scan first — deep scan to learn more before committing
    3) Ignore — continue on your way (no penalty, no reward)
    4) Report — hail nearest patrol with the coordinates (reputation)

Phase 1a: INVESTIGATE (arrive at signal)
  → Perception/Sensors check to assess the scene
  → Possible scenarios (weighted random):
    a) Genuine distress (50%): damaged freighter, crew needs rescue
       → Medical skill to treat wounded, Repair to patch ship
       → Reward: credits, reputation, cargo as thanks, quest hook
    b) Pirate trap (25%): ambush by 2 hostiles
       → Combat at Close range (disadvantageous)
       → Sensors critical success on arrival detects the trap,
         player can choose to withdraw before springing it
    c) Imperial trap (10%): ISB sting operation
       → If carrying contraband: automatic confiscation
       → If clean: embarrassing but no penalty
    d) Derelict with salvage (15%): crew dead, ship intact
       → Salvage components, possible rare find
       → Dark side moral choice: take cargo meant for others?

Phase 1b: SCAN FIRST (Sensors station)
  → Deep scan roll against Moderate (15)
  → Success: reveals whether signal is genuine, trap, or derelict
    (player can then choose to investigate or ignore with info)
  → Failure: inconclusive, must decide blind
  → Critical: full intel including enemy count and loot estimate
```

**Crew involvement**:
- Sensors: deep scan to assess before committing
- Pilot: navigate to signal source
- Commander: decide to investigate or report
- Engineer/Medical: rescue operations on arrival
- Gunner: combat if it's a trap

**Outcomes**:
- Rescue: credits + reputation + potential recurring contact
- Trap survived: combat loot + CP for surviving ambush
- Trap avoided (scanned first): intel + avoided danger
- Derelict salvage: components + moral choice
- Reported: small reputation boost with Imperial/local authority
- Ignored: nothing (no penalty, this is important — not every event
  should demand engagement)

### 6.4 Mechanical Difficulty

**Source**: WEG GG6, p.62 — "Mechanical Difficulties" event

**Trigger**: Random tick event, higher probability for ships with
existing damage, old hyperdrive multipliers, or the "hyperdrive_stutter"
quirk. Can also be triggered by Director as a plot complication.

**Choice tree**:

```
Phase 0: MALFUNCTION
  "[ENGINEERING] Warning: [system] malfunction detected.
  [Flavor text based on system — e.g., 'Hyperdrive motivator
  temperature rising rapidly. Overheat in 3 minutes.']"

  System affected (weighted random):
    - Hyperdrive (30%): can't jump until repaired
    - Engines (25%): speed reduced by half
    - Shields (20%): shields offline
    - Sensors (15%): blind — no scan, no deep scan
    - Weapons (10%): can't fire

  This is NOT a choice event — it's a crew problem-solving event.
  The encounter resolves through crew action, not menu selection.

Phase 1: REPAIR SEQUENCE
  → Engineer uses damcon to repair (existing system)
  → BUT: add a twist — the malfunction has a CAUSE:
    a) Wear and tear (60%): standard repair, standard difficulty
    b) Mynock infestation (20%): must clear mynocks first (Easy
       piloting check to shake them off, or ground combat if boarded)
    c) Sabotage (10%): someone tampered with the ship. Investigate
       later for plot hook. Repair difficulty +5.
    d) Power surge (10%): cascading failure. Fix the primary system
       within 2 minutes or a secondary system also fails.

  → Other crew can assist:
    - Copilot: assist the repair roll (+1D)
    - Sensors: diagnose the fault first (Technical check reduces
      repair difficulty by 5 on success)
    - Commander: Coordinate (+1D to engineer's next roll)
```

**Crew involvement**:
- Engineer: primary repair role
- Copilot: assist
- Sensors: diagnostic
- Commander: coordinate
- Pilot: shake off mynocks, or navigate to a safe repair location

**Outcomes**:
- Quick repair: minimal disruption, CP for engineer
- Slow repair: system offline for duration, vulnerability window
- Cascading failure: two systems damaged (real danger)
- Sabotage discovered: plot hook for ground investigation later

### 6.5 Mysterious Contact

**Source**: WEG GG6, p.62 — "Other Ship" event

**Trigger**: Another ship appears on sensors. Not hostile (initially),
not a standard trader. Something interesting.

**Scenarios** (one selected on spawn):

- **Adrift freighter**: Power signature but no comms response. Board
  to find unconscious crew (medical opportunity), hidden cargo,
  or Imperial prisoners in the hold.

- **Racing smuggler**: A ship blasts through your zone at maximum speed,
  pursued by two TIE fighters. Do you help (combat), ignore, or hail
  the Imperials to curry favor?

- **Luxury yacht**: A wealthy passenger liner drifts through with a
  broken nav computer. They'll pay handsomely for an astrogation
  assist (Navigator skill check + credits reward).

- **Probe droid carrier**: An Imperial probe droid deployment ship.
  If you can destroy the probes before they report, a Rebel contact
  will pay well. If you attack and fail, you've just picked a fight
  with the Empire.

- **Ghost ship**: Transponder reads as a ship that was reported
  destroyed years ago. Investigating reveals it's been jury-rigged
  by survivors (rescue mission) or it's actually a slaver ship using
  the dead transponder as cover.

These are Director-hookable — the Director AI can inject specific
scenarios based on current world state, faction tensions, or player
narrative arcs.

### 6.6 Cargo Emergency

**Source**: WEG GG6, p.62 — "Damaged Cargo" event

**Trigger**: Random during transit, especially for ships carrying cargo
or active smuggling jobs.

```
Phase 0: ALERT
  "[CARGO] Warning: cargo bay pressure anomaly. Something in the
  hold is [leaking/shifting/overheating/making noise]."

  Choices:
    1) Investigate (go to cargo hold — ground encounter)
    2) Vent the bay (safe but destroys cargo)
    3) Ignore (risk of escalation)

Phase 1a: INVESTIGATE
  → Crew member goes to cargo hold (interior ship room)
  → Possible finds:
    - Damaged container: repair to save cargo value
    - Stowaway: NPC hiding in your hold (social encounter)
    - Creature: space vermin got into the shipment (combat)
    - Hidden contraband: someone hid spice in your legitimate cargo
      (moral/legal dilemma)

Phase 1b: VENT
  → Cargo destroyed. If smuggling job active: job fails.
  → But if the cargo was actually dangerous (creature, bomb), you
    saved the ship. Outcome revealed after the fact.
```

### 6.7 Bounty Hunter Pursuit (Redesigned)

**Trigger**: Player has an active bounty. Hunter spawns as event-driven
NPC (existing system). But now the encounter actually plays out.

```
Phase 0: DETECTION
  Sensors: "Pursuit vessel dropping out of hyperspace. They're
  scanning for your transponder."

  If player has false transponder active:
    → Stealth check — hunter might not identify you immediately
    → Gives player 30 extra seconds to prepare or flee

Phase 1: CONFRONTATION
  Hunter hails with demand to surrender.
  Choices:
    1) Surrender — bounty collected, player loses credits/items
       (but is NOT killed — this is a MUSH, permadeath is off)
    2) Fight — hunter enters SpaceGrid, full combat
    3) Flee — chase sequence with a skilled pursuer
    4) Negotiate — offer to pay off the bounty yourself (Bargain
       check at Very Difficult)

Phase 2: COMBAT (if fight or failed flee)
  → Hunter uses NPC Space Combat AI (see §7)
  → Hunter is 5D skill, aggressive profile
  → Hunter flees at 25% hull (existing threshold)
  → On hunter destruction: bounty reduced, respawn in 5 min
  → On player disabled: bounty collected (credits taken, not killed)
```

---

## 7. NPC Combat AI for Space

### 7.1 The Gap

The ground NPC AI has 5 combat profiles (aggressive, defensive,
sniper, support, berserker). Space NPCs have *no* combat AI — they
announce attacks but never enter the SpaceGrid or fire weapons.

### 7.2 NPC Space Combat AI Design

New file: `engine/npc_space_combat_ai.py`

An NPC space combatant is a TrafficShip that has been promoted to
active combat status. It has:
- A ship template (from `starships.yaml`) with weapons and stats
- A crew skill level (the captain's dice pool for all stations)
- A combat profile determining tactical decisions
- A flee threshold (hull % at which it disengages)

**Combat profiles**:

```python
class SpaceCombatProfile(Enum):
    AGGRESSIVE = "aggressive"   # Close range, maximum firepower
    CAUTIOUS = "cautious"       # Medium range, flee when hurt
    PURSUIT = "pursuit"         # Close and tail, block escape
    AMBUSH = "ambush"           # Wait at close, alpha strike, then flee
    PATROL = "patrol"           # Disable (ion weapons), don't destroy

# Profile → behavior mapping
SPACE_AI_BEHAVIORS = {
    "aggressive": {
        "preferred_range": SpaceRange.SHORT,
        "action_priority": ["fire", "close", "fire"],
        "flee_threshold": 0.30,
        "uses_lockon": False,
        "preferred_weapons": "highest_damage",
    },
    "cautious": {
        "preferred_range": SpaceRange.MEDIUM,
        "action_priority": ["fire", "evade", "fire"],
        "flee_threshold": 0.50,
        "uses_lockon": True,
        "preferred_weapons": "highest_fire_control",
    },
    "pursuit": {
        "preferred_range": SpaceRange.CLOSE,
        "action_priority": ["tail", "close", "fire"],
        "flee_threshold": 0.25,
        "uses_lockon": False,
        "preferred_weapons": "any",
    },
    "patrol": {
        "preferred_range": SpaceRange.SHORT,
        "action_priority": ["fire_ion", "close", "fire_ion"],
        "flee_threshold": 0.40,
        "uses_lockon": True,
        "preferred_weapons": "ion_preferred",
    },
    "ambush": {
        "preferred_range": SpaceRange.CLOSE,
        "action_priority": ["fire", "fire", "flee"],
        "flee_threshold": 0.60,
        "uses_lockon": False,
        "preferred_weapons": "highest_damage",
    },
}
```

**Archetype → profile mapping**:
- Pirate: aggressive (standard), ambush (in pirate nest)
- Bounty hunter: pursuit
- Imperial patrol: patrol (uses ion if available, aims to disable)
- Imperial interceptor (chase escalation): aggressive

### 7.3 NPC Combat Tick

Each tick (1 second), active NPC combatants evaluate their situation
and take one action. The action cycle mirrors what a player would do:

```python
async def npc_space_combat_tick(npc_ship, player_ship, db, session_mgr):
    """One tick of NPC space combat AI."""
    profile = get_combat_profile(npc_ship)
    grid = get_space_grid()
    current_range = grid.get_range(npc_ship.id, player_ship.id)

    # Check flee condition
    if should_flee(npc_ship, profile):
        await execute_flee(npc_ship, player_ship, grid, db, session_mgr)
        return

    # Determine action based on profile priority and current situation
    action = select_action(profile, current_range, npc_ship, player_ship)

    if action == "fire":
        await execute_fire(npc_ship, player_ship, grid, db, session_mgr)
    elif action == "close":
        await execute_close_range(npc_ship, player_ship, grid, db, session_mgr)
    elif action == "tail":
        await execute_tail(npc_ship, player_ship, grid, db, session_mgr)
    elif action == "fire_ion":
        await execute_fire_ion(npc_ship, player_ship, grid, db, session_mgr)
    elif action == "evade":
        await execute_evade(npc_ship, grid, db, session_mgr)
    elif action == "flee":
        await execute_flee(npc_ship, player_ship, grid, db, session_mgr)
```

**Action pacing**: NPC fires every 3-5 seconds (not every tick). This
gives players time to react and issue commands. Configurable per profile.

### 7.4 Promoting TrafficShip to Combatant

When an encounter escalates to combat:

1. TrafficShip enters `TrafficState.ATTACKING`
2. NPC ship is added to the SpaceGrid at the appropriate starting range
3. A `SpaceNpcCombatant` wrapper is created with the ship's stats
4. The NPC combat tick begins running each tick
5. Combat messages broadcast to the bridge room as normal

When combat ends (NPC destroyed, NPC flees, player flees, player disabled):

1. NPC is removed from SpaceGrid
2. If destroyed: wreck anomaly spawned, rewards distributed
3. If fled: NPC enters FLEEING state and despawns normally
4. TrafficShip's encounter is marked resolved

---

## 8. Crew Station Engagement

### 8.1 Station Action Prompts

During multi-station encounters, the web client shows per-station
action prompts. Each crew member sees what *their* station can
contribute.

```python
# WebSocket payload for station-specific action prompts
{
    "type": "station_prompt",
    "encounter_id": "enc-abc123",
    "station": "engineer",
    "prompt": "Imperial boarding team approaching. You can:",
    "actions": [
        {
            "key": "hide_cargo",
            "label": "Hide Contraband",
            "skill": "Con or Repair",
            "difficulty": "Moderate (15)",
            "description": "Stash the cargo in a hidden compartment."
        },
        {
            "key": "scramble_manifest",
            "label": "Scramble Manifest",
            "skill": "Computer Programming",
            "difficulty": "Difficult (20)",
            "description": "Falsify the cargo manifest before they check."
        },
        {
            "key": "nothing",
            "label": "Do Nothing",
            "description": "Let the inspection proceed normally."
        }
    ]
}
```

Telnet equivalent:
```
  [ENGINEERING] Imperial boarding team approaching.
  You can:
    1) Hide Contraband (Con or Repair, Moderate)
    2) Scramble Manifest (Computer Programming, Difficult)
    3) Do Nothing

  Type: stationact 1, stationact 2, or stationact 3
```

### 8.2 Station Contributions During Combat

During active space combat (NPC on the grid, exchanging fire), crew
stations have ongoing roles:

- **Pilot**: `close`, `flee`, `tail`, `outmaneuver`, `evade` (existing)
- **Copilot**: `assist` pilot roll (existing, +1D)
- **Gunner**: `fire`, `lockon` (existing)
- **Engineer**: `damcon` repairs, `shields` redistribution, `power`
  allocation (existing)
- **Sensors**: `scan` to reveal NPC stats, `deepscan` for tactical
  intel (new: reveals NPC's flee threshold and weapon loadout)
- **Navigator**: `hyperspace` emergency jump (existing, but now explicitly
  available during combat as an escape option)
- **Commander**: `order` tactical orders (existing), `coordinate` crew
  bonus (existing), **new: `hail` to attempt cease-fire negotiation**

### 8.3 Commander Cease-Fire

New mechanic: during active combat, the Commander can attempt to
negotiate a cease-fire. This uses Bargain or Command skill vs. the
NPC's Willpower.

- Against pirates: offer credits to stop fighting
- Against bounty hunters: offer to pay off the bounty
- Against Imperial patrol: claim a misunderstanding (Con check)

Success stops the combat. Failure wastes the Commander's action that
round. Can only be attempted once per encounter.

---

## 9. Web Client Space Experience

### 9.1 Choice Panel UI

The web client renders `space_choices` messages as a floating panel
over the space HUD area — similar to how the combat panel works but
themed for space encounters.

**Visual design**:
- Dark translucent panel with a cyan/amber border
- Encounter type icon and title at top
- Timer bar (if deadline exists) — shrinking bar from full to zero
- Choice buttons styled by risk level:
  - Safe choices: green/neutral border
  - Medium risk: amber border
  - High risk: red border
- Each button shows the relevant skill and difficulty
- Station icon on buttons that hint at a specific station

### 9.2 Radar Enhancements

The existing radar SVG needs upgrades to support combat encounters:

**Current**: Blips positioned by range band (distance from center),
  random angular placement.

**New**:
- Blips positioned angularly by relative position (front = top,
  rear = bottom, flank = sides)
- Hostile contacts pulse red
- Friendly/neutral contacts are blue/green
- Range band labels highlight current engagement range
- When NPC is on the grid and fighting, show a "COMBAT" badge
- Weapon fire arcs drawn as faint cone overlays from player ship
  (shows which weapons can reach which targets)

### 9.3 Encounter Narrative Feed

During encounters, a dedicated narrative feed appears in the space panel
(below the radar). This shows:
- NPC hail messages
- Encounter phase transitions
- Skill check results
- Combat damage reports
- Crew station action results

This is separate from the main chat scroll so it doesn't get buried
in other output.

### 9.4 Station Action Sidebar

During multi-station encounters, each crew member's web client shows
their available actions in the quick-button area (already station-aware).
New encounter-specific buttons appear temporarily:
- "Hide Cargo" (engineer during inspection)
- "Diagnose Fault" (sensors during malfunction)
- "Emergency Jump" (navigator during pursuit)
- "Negotiate" (commander during combat)

These buttons send the appropriate `stationact` or `respond` commands.

---

## 10. Telnet Graceful Degradation

### 10.1 Design Philosophy

Every feature works on Telnet. The experience is *simpler*, not
*broken*. Specific approach:

- Choice panels → numbered text menus with `respond N` command
- Station prompts → text prompts with `stationact N` command
- Radar enhancements → existing `scan` command text output (unchanged)
- Narrative feed → same text, same line, in the main output stream
- Timer bars → text countdown warnings at 50%, 25%, 10%
- Quick buttons → not applicable (Telnet users type commands)

### 10.2 Telnet-Specific Considerations

- All encounter text is ANSI-formatted for readability
- Numbered choice lists are clear and unambiguous
- Commands are short and memorable (`respond`, `stationact`)
- Help text explains available commands during encounters
- No feature is web-only except visual enhancements (radar angles,
  timer bars, button styling)

---

## 11. Economy Integration

### 11.1 New Faucets

- **Pirate bounties**: 500-1,500cr on destruction (existing, but now
  actually wired to combat)
- **Distress signal rewards**: 500-3,000cr for successful rescue
- **Salvage from combat**: components feed crafting pipeline
- **Encounter CP rewards**: CP ticks for creative solutions (bluffing
  patrols, negotiating with pirates)
- **Intel rewards**: Information about upcoming convoys, hidden caches,
  or quest hooks — indirect economic value

### 11.2 New Sinks

- **Pirate payments**: 500-3,000cr (existing, retuned)
- **Imperial fines**: 100-10,000cr (existing, now with skill check mitigation)
- **Chase fuel costs**: emergency maneuvers consume extra fuel/consumables
- **Repair costs**: combat damage requires repair (existing damcon +
  docked repair at shipyard)

### 11.3 Economy Audit Alignment

Per `economy_audit_v1.md`, the space system should generate income
comparable to ground activities (2,000-5,000cr/hour for active play).
Current space income is near zero because pirate bounties are the only
faucet and pirate combat doesn't work.

Target income rates for space gameplay:
- Casual transit (occasional encounter): 1,000-2,000cr/hour
- Active space play (seeking encounters): 3,000-6,000cr/hour
- Smuggling runs (existing): 2,000-8,000cr/hour (already tuned)
- Pirate hunting (deliberate): 4,000-8,000cr/hour (high risk)

---

## 12. Director AI Integration

### 12.1 Director-Driven Encounters

The Director AI can inject specific encounter types based on world state:

- **High faction tension**: more Imperial patrols in contested zones
- **Pirate activity surge**: more pirate encounters, higher demands
- **Distress signal events**: Director can spawn a distress signal
  tied to a specific narrative (rebel cell in trouble, VIP stranded)
- **Mysterious contact**: Director can spawn a "plot ship" with
  specific scenario attached to current world narrative
- **Bounty escalation**: Director can spawn additional bounty hunters
  when a player's bounty is high

### 12.2 Director Encounter Hooks

```python
# Director can request specific encounter types
await encounter_manager.inject_encounter(
    zone_id="tatooine_deep_space",
    encounter_type="distress_signal",
    scenario="rebel_ambush",  # specific scenario override
    target_ship_id=None,       # None = any ship in zone
    narrative_context="The Rebel cell on Tatooine is compromised.",
)
```

### 12.3 Digest Integration

Encounter outcomes feed the Director's digest:
- "Player ship bluffed through an Imperial inspection"
- "Pirate destroyed in Kessel Approach — salvage recovered"
- "Distress signal in deep space was a trap — player survived ambush"
- "Player surrendered to bounty hunter — bounty collected"

This gives the Director data to adjust future encounter rates and
narrative direction.

---

## 13. Implementation Plan

### Drop 0: Space Security Zone Infrastructure
**Effort**: Small (200-300 lines)
**Prerequisite for**: All subsequent drops (encounter rates depend on this)

- Add `security` field to `Zone` dataclass in `npc_space_traffic.py`
- Assign per-planet security profiles to all 16 zones (§4.3)
- New `get_space_security(zone_id)` function with Director overlay support
- Replace hardcoded `_check_space_security()` in `FireCommand` with
  new function
- Wire patrol/pirate/anomaly spawn rates to zone security level (§4.4)
- Pipe world event alert levels into space security overlays
- Add security level to `build_space_state()` WebSocket payload
- Web client zone map: color-code zones by security level

### Drop 1: SpaceEncounter Framework + `respond` Command
**Effort**: Medium (400-500 lines)

- `SpaceEncounter` dataclass and `EncounterManager` singleton
- `respond` command (parser) and `stationact` command
- WebSocket `space_choices` message type
- Telnet numbered menu rendering
- Encounter cooldown tracking
- No specific encounters yet — just the framework

### Drop 2: Imperial Patrol Redesign
**Effort**: Medium (400-500 lines)

- 4-choice branching patrol encounter (Comply/Bluff/Run/Hide)
- Each branch with skill checks and outcomes
- Replaces current `_send_patrol_hail` / `_tick_hailing` / 
  `_run_boarding_inspection` flow
- Web client choice panel rendering (if not yet in client)
- Telnet menu rendering

### Drop 3: NPC Space Combat AI
**Effort**: Large (600-800 lines)

- `engine/npc_space_combat_ai.py` — new file
- 5 combat profiles (aggressive, cautious, pursuit, ambush, patrol)
- TrafficShip → SpaceGrid promotion flow
- NPC combat tick (action selection, fire, maneuver, flee)
- Action pacing (3-5 second intervals)
- Combat resolution (NPC destruction, NPC flee, player disabled)
- Wreck anomaly on NPC destruction

### Drop 4: Pirate Encounter Redesign
**Effort**: Medium (400-500 lines)

- 4-choice branching pirate encounter (Pay/Negotiate/Fight/Flee)
- Negotiation with Bargain skill check
- Fight path uses Drop 3 NPC combat AI
- Flee path as chase sequence
- Credit bounty and salvage rewards on destruction

### Drop 5: Distress Signal + Mysterious Contact
**Effort**: Medium-Large (500-600 lines)

- Distress signal with 4 scenarios (genuine/pirate trap/ISB sting/derelict)
- Scan-first option for pre-assessment
- Mysterious contact with 5 scenario variants
- Director hookable scenario injection

### Drop 6: Mechanical Difficulty + Cargo Emergency
**Effort**: Medium (400-500 lines)

- Malfunction event with system-specific effects
- Cause variants (wear/mynock/sabotage/cascade)
- Cargo emergency with investigate/vent/ignore choices
- Stowaway NPC encounter

### Drop 7: Bounty Hunter Redesign
**Effort**: Small-Medium (300-400 lines)

- False transponder stealth check on detection
- 4-choice encounter (Surrender/Fight/Flee/Negotiate)
- Uses Drop 3 NPC combat AI (pursuit profile)
- Bounty payment negotiation

### Drop 8: Anomaly Encounter Completion
**Effort**: Medium (400-500 lines)

- Pirate nest: spawn 2-3 hostile NPCs on arrival (uses Drop 3 AI)
- Distress signal anomaly: connects to §6.3 distress encounter
- Imperial dead drop: slicing check, patrol trigger on failure
- Hidden cache: piloting + security bypass skill checks
- Mynock colony: ground combat mini-encounter in ship interior

### Drop 9: Web Client Encounter UI
**Effort**: Medium-Large (500-700 lines, client-side)

- Choice panel component with risk-styled buttons
- Timer bar component
- Station action sidebar integration
- Encounter narrative feed (separate from main chat)
- Radar angular positioning for relative position
- Combat engagement badge

### Drop 10: Crew Station Prompts + Commander Cease-Fire
**Effort**: Small-Medium (300-400 lines)

- `station_prompt` WebSocket message type
- Per-station action buttons during encounters
- Commander cease-fire negotiation mechanic
- Multi-crew encounter resolution (aggregate station contributions)

### Drop 11: Balance, Tuning, and Polish
**Effort**: Small-Medium

- Encounter frequency tuning based on playtesting
- Economy rate validation (cr/hour targets)
- Director AI encounter injection testing
- Radar visual polish
- Help text updates for all new commands/mechanics

**Total estimated new code**: ~4,700-6,300 lines across 12 drops.

**Dependency chain**: Drop 0 is prerequisite for all others (encounter
rates depend on security levels). Drop 1 is prerequisite for Drops 2+.
Drop 3 is prerequisite for Drops 4, 7, and 8. All other drops are
independent after Drop 1.

**Revised delivery order (archetype-loops-first, per §0.8):**

```
DONE:  0 (security zones) → 1 (encounter framework) → 2 (patrol redesign)

NEXT:  3 (NPC space combat AI) ← highest impact; unblocks pirate/hunter/intercept
       4 (pirate encounter)    ← first encounter where NPCs actually fight
       8 (anomaly completion)  ← finishes the exploration loop

THEN:  5 (distress + contact)  ← texture encounters
       6 (mechanical + cargo)  ← texture encounters
       7 (bounty hunter)       ← uses Drop 3 AI
       9 (web client UI)       ← visual polish
      10 (crew station prompts) ← multi-crew depth
      11 (tuning + polish)

PARALLEL (separate from this doc):
       Economy Hardening (Priority A) ← fixes the trader loop
       Faction Reputation ← fixes the faction pilot loop
```

The key change: Drop 3 (NPC combat AI) moves to immediate next because
it unblocks the most archetype loops. Without it, pirates, bounty
hunters, and intercept missions all dead-end. With it, three archetype
loops become complete.

---

## 14. File Map & Architectural Changes

### New Files

| File | Purpose | Est. Lines |
|------|---------|-----------|
| `engine/space_encounters.py` | SpaceEncounter framework, EncounterManager | ~500 |
| `engine/npc_space_combat_ai.py` | NPC space combat AI, combat profiles | ~600 |
| `parser/encounter_commands.py` | `respond`, `stationact` commands | ~200 |

### Modified Files

| File | Changes |
|------|---------|
| `engine/npc_space_traffic.py` | Zone dataclass gains `security` field; per-planet security profiles; TrafficShip gains encounter_id field; patrol/pirate/hunter hail logic replaced with encounter spawning; `_tick_hailing` delegates to EncounterManager; new `promote_to_combat()` method; encounter spawn rates keyed to zone security level |
| `engine/security.py` | New `get_space_security(zone_id)` function with Director overlay support; space zone security caching |
| `engine/starships.py` | No changes to combat engine (it already works) |
| `parser/space_commands.py` | Replace `_check_space_security()` with `get_space_security()` call; register new commands; `build_space_state()` gains encounter data + security level; fire/flee/etc. gain NPC combat interaction hooks |
| `server/tick_handlers_ships.py` | New `encounter_tick()` handler for encounter deadlines and NPC combat pacing |
| `static/client.html` | Choice panel UI, station prompt UI, radar enhancements, encounter narrative feed, zone map security color-coding |
| `engine/space_anomalies.py` | Anomaly quality/spawn rates keyed to zone security; arrive-at hooks delegate to encounter types from §6 |
| `server/tick_scheduler.py` | Register encounter_tick handler |

### Architectural Invariants (preserved)

- All dice rolls → `engine/dice.py`
- All out-of-combat skill checks → `engine/skill_checks.py::perform_skill_check()`
- All space combat → `engine/starships.py::resolve_space_attack()`
- All influence changes → `adjust_territory_influence()`
- All credit changes → DB save with logging
- Every `except Exception` → `log.warning`
- Complete file replacements for heavily-modified files; surgical patches
  for targeted changes

---

## 15. Migration & Compatibility

### 15.1 Backward Compatibility

- All existing space commands continue to work unchanged
- Ships in flight during server update are unaffected
- NPC traffic ships that exist when the update deploys will continue
  their current routes; new encounters only spawn for new traffic
- The `respond` and `stationact` commands are purely additive
- If a player ignores the choice panel and just types `comms <patrol>
  <message>`, the old behavior still works (encounter resolves via
  compliance keyword detection as fallback)

### 15.2 Feature Flags

```python
# server/config.py
SPACE_ENCOUNTERS_V3 = True    # False = legacy hail/timeout behavior
NPC_SPACE_COMBAT_AI = True    # False = NPCs announce but don't fight (current)
ENCOUNTER_CHOICE_UI = True    # False = no choice panels, just text menus
```

These flags allow rolling back to legacy behavior per-feature if issues
arise during deployment.

### 15.3 Data Migration

No schema changes required. Encounter state is transient (in-memory,
like SpaceGrid and anomalies). NPC combat state lives on the
TrafficShip dataclass. Encounter history can optionally log to
`director_log` for Director AI consumption.

---

## Appendix A: WEG Source Material References

- **R&E Core Rulebook (WEG40120)**: Chapter 10 (Space Combat), Chapter 7
  (Space Travel)
- **Galaxy Guide 6: Tramp Freighters (WEG40027)**: "Events in Space"
  section (p.62) — pirates, mechanical difficulties, other ships,
  damaged cargo, Imperial customs, distress signals
- **Galaxy Guide 7: Mos Eisley (WEG40069)**: Docking bay encounters,
  customs procedures
- **WEG40141 (Imperial Sourcebook)**: Infraction classes and fine
  schedules (already implemented in `_run_boarding_inspection`)
- **Star Warriors board game**: Hazard table (already implemented),
  hex-based combat (explicitly NOT adopted — see §3)
- **Platt's Smugglers Guide**: Ship quirks (already implemented in
  Drop 19)

## Appendix B: Comparator Reference

- **EVE Online**: Probe scanning loop (implemented in anomaly system),
  NPC AI combat profiles, engagement timer concept. **Security status
  system** (high-sec/low-sec/null-sec) as the master tuning parameter
  for encounter rates, NPC difficulty, resource quality, PvP rules, and
  economic opportunity per region — adapted as per-planet security
  profiles in §4.
- **SWG: Jump to Lightspeed**: Duty missions, component salvage from
  combat, multi-system engagement zones
- **Star Wars Galaxies pre-NGE**: Space combat pacing (action intervals,
  not real-time twitch), patrol encounter frequency
- **FTL: Faster Than Light**: Event-driven encounters with branching
  choices — the closest single-player analogue to what we're building.
  Every jump is a mini-adventure with risk/reward decisions. This is
  the *feel* we're targeting.

## Appendix C: Event Frequency Model

Target: a player flying between planets should encounter 1-2 events per
10-minute play session. Not every zone transit triggers an event. Long
hyperspace jumps (60-120 seconds) are quiet by design — the event
windows are zone arrivals and deep space loitering.

```
Expected events per hour of active space play:
  - Imperial patrols: 1-2 (higher near Core, lower in Outer Rim)
  - Pirate encounters: 1-2 (higher in deep space, near Nar Shaddaa)
  - Distress signals: 0-1 (always voluntary)
  - Mechanical difficulties: 0-1 (based on ship condition)
  - Mysterious contacts: 0-1 (Director-driven weight)
  - Cargo emergencies: 0-1 (only if carrying cargo)
  - Bounty hunters: event-driven only (not random)

Total: 3-6 events per hour of active space play
```

This is roughly one event every 10-20 minutes — enough to keep space
interesting without making transit feel like running a gauntlet.
