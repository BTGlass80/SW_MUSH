# SW_MUSH Gameplay and Senior Game Design Audit

## Verdict

SW_MUSH is no longer “just a MUSH.” It is a hybrid sandbox RPG with tabletop-rule fidelity, a web client, AI-assisted living-world features, faction economy, crafting, contraband, threat bands, questlines, social roleplay, and space/ground systems.

That is exciting. It is also dangerous.

The core design risk is not lack of systems. The risk is that the systems are individually interesting but collectively overwhelming. The project needs a sharper player-facing structure: clear first-session goals, repeatable profession loops, visible local opportunities, and social reasons to use the systems together.

In short: **the systems are coherent from a developer/auditor perspective; they still need to be made coherent from a player moment-to-moment perspective.**

## What is already strong

### 1. The fantasy is distinctive.

A Clone Wars-era WEG D6 MUSH/web hybrid is a strong niche. It can offer something that neither modern MMOs nor Discord RP servers usually provide: crunchy tabletop-like persistence with live multiplayer social play.

### 2. The system palette supports multiple playstyles.

The game appears to support:

- combat characters,
- crafters,
- scouts/explorers,
- Force-sensitive/Jedi paths,
- bounty hunters,
- smugglers/contraband runners,
- social/RP characters,
- faction operatives,
- space pilots,
- city/housing/community builders.

That breadth is a real strength if players can understand where they fit.

### 3. Threat bands are a good readability axis.

Separating difficulty from security is the right design. “This place is dangerous” and “this place is lawful/lawless” are different player questions. The four-band structure gives you a way to steer players into appropriate risk.

### 4. Communal objectives are a good social anchor.

The communal objective system is exactly the kind of feature a small multiplayer game needs. It gives players a shared topic, a reason to gather, and a way for non-identical builds to contribute.

### 5. Contraband and black-market systems create meaningful risk.

Contraband is fun because it asks: Do I want power, money, access, or safety? That is a better choice than “buy the highest DPS item.”

## Primary gameplay risks

### GAME-1 — P1: The new-player question is probably still unanswered: “What should I do now?”

The game has many commands and systems, but a new player needs a small number of obvious next actions. Tutorials and command help are not enough. The player needs a goal stack.

**Recommendation:** every player should always have 1–3 suggested actions visible:

- “Finish your starter chain.”
- “Talk to Sela Tarn about armor work.”
- “Take a courier contract from the local board.”
- “A communal threat is active: rally from any settlement.”
- “Your faction contact has a low-risk job nearby.”

These should not be hard rails. They are playable invitations.

### GAME-2 — P1: Roles may not be equally fun in the moment.

A combat character's loop is obvious: find danger, fight, loot, recover. A crafter, medic, slicer, scout, diplomat, or quartermaster needs equally visible moment-to-moment value.

**Recommendation:** build profession contracts and local calls-to-action:

| Role | Repeatable fun loop |
|---|---|
| Crafter | Work orders, repairs, commissions, field modifications, quality contests. |
| Medic | Injury calls, evac contracts, battlefield triage, clinic reputation. |
| Slicer | Locked intel, route discovery, market tips, security bypass jobs. |
| Scout | Survey routes, locate rare spawns/materials, mark danger. |
| Diplomat | De-escalate events, negotiate access, rep conversion. |
| Bounty hunter | Track, prepare, capture/kill, collect, deal with reprisal. |
| Smuggler | Source illegal goods, choose route, evade scan, sell into demand. |
| Pilot | Transport, escort, intercept, salvage, emergency extraction. |

The UI and Director should surface these as actual opportunities.

### GAME-3 — P1: Crafting needs emotional payoff, not only economic correctness.

The Gundark lane is structurally impressive. But crafting becomes fun when players feel identity and pride:

- “I made this.”
- “This is better because of my choices.”
- “Other players know me for this.”
- “This object has a story.”

**Recommendation:** add item provenance and visible identity:

- maker name,
- quality band title,
- notable experiment trait,
- first owner / famous use / battle scar,
- repair history,
- illegal modifications,
- faction markings,
- public “crafted by” inspection.

Even small flavor metadata can make crafting much stickier.

### GAME-4 — P1: Combat needs readable choices and consequences.

WEG fidelity is a constraint, but players still need to understand tactical options without reading a sourcebook. A player should know:

- Why did I miss?
- Why did that hurt?
- What can I do next round?
- Am I outmatched?
- Should I retreat?
- Did my gear matter?
- Did my wound level matter?

**Recommendation:** combat output should include compact explanation lines:

```text
Result: Hit by 7. Damage 5D+1 vs soak 3D+2. You are Wounded.
Why: armor helped (+1 pip), range hurt attacker (-1D), your dodge failed by 2.
Next: fire, dodge, retreat, use medpac, call for help.
```

Avoid dumping full math every time, but make the reasons discoverable.

### GAME-5 — P1: Content density can become a dead-zone problem.

A 40×40×3 Coruscant Underworld sounds impressive, but large maps are dangerous in text games. If players wander through many rooms with nothing actionable, the world feels empty even if the data count is high.

**Recommendation:** use “event magnets” rather than uniform room density:

- noise/rumor pull lines,
- local opportunity markers,
- known safe paths,
- danger gradients,
- NPC clusters,
- boards/contacts/vendors/trainers,
- “you sense activity nearby” hints,
- minimap pins for role-relevant points.

A sparse map with excellent wayfinding feels bigger than a huge map with weak affordances.

### GAME-6 — P1: The Director AI should create playable situations, not just atmosphere.

Atmosphere is useful, but the Director's highest value is generating opportunities that players can act on.

**Recommendation:** classify Director output into tiers:

1. **Flavor only** — ambient text, no mechanical impact.
2. **Hint** — points toward existing content.
3. **Opportunity** — creates a limited-time job/event/contact.
4. **State change** — modifies world event, faction, market, or danger state.

For launch, bias toward tiers 2 and 3. They are easier to make fun and safer than broad state changes.

### GAME-7 — P2: Force/Jedi progression should be aspirational without dominating the game.

The Force path is a strong fantasy, but it can distort a multiplayer game if it becomes the only “real” endgame.

**Recommendation:** keep Jedi rare and meaningful, but make non-Jedi mastery equally prestigious:

- master armorer,
- legendary scout,
- feared bounty hunter,
- trusted medic,
- ace pilot,
- faction fixer,
- underworld broker,
- city founder.

Every archetype needs a “I made it” milestone.

### GAME-8 — P2: Communal objectives should be used as onboarding/social glue.

Because communal losses do not penalize players, they are ideal for inclusive participation.

**Recommendation:** make communal objectives visible to new players with low-risk contribution paths:

- investigate rumors,
- deliver supplies,
- rally morale,
- treat wounded,
- scout activity,
- slice communications,
- fight cultists if combat-ready.

Do not make the default contribution path “go fight something scary.”

### GAME-9 — P2: Space and ground may be two separate games fighting for attention.

The space system appears deep. That is good for pilots but risky for everyone else. A player should understand when they are playing the ground game, when they are playing the space game, and why crossing modes matters.

**Recommendation:** define transition verbs and reasons:

- ground job requires space transport,
- space salvage yields crafting material,
- faction war creates escort/intercept jobs,
- contraband route crosses space and ground enforcement,
- player cities create demand for shipped goods.

Do not let space become a parallel silo.

## Fun upgrades with high return

### 1. Galactic briefing

On login, show a short actionable briefing:

```text
GALACTIC BRIEFING
1. Your tutorial chain can continue at Kayson's Workshop.
2. A contested-marches bounty near Anchorhead pays 1.4x today.
3. The communal cult threat needs scouts, medics, and fighters.
```

This should be personalized by profession, faction, location, and threat readiness.

### 2. Profession contract board

Instead of a generic mission board, let each profession see suitable tasks:

- novice-safe,
- local,
- group recommended,
- high risk/high reward,
- faction-specific,
- crafting order,
- social/RP prompt.

### 3. “Why can't I?” failure messages

Every refusal should include:

1. what failed,
2. why,
3. what to do next.

Example:

```text
You cannot buy that here.
Reason: this vendor only stocks common legal weapons.
Try: craft it, find a specialist, or ask underworld contacts on Nar Shaddaa.
```

### 4. Milestone journals

Players need persistent memory of progress:

- completed chains,
- faction favors,
- important NPCs met,
- crafted notable items,
- first kill/capture/sale,
- communal wins,
- legal infractions,
- training unlocked.

This helps RP and retention.

### 5. Group finder / crew call

Small multiplayer games need help forming groups. Add a lightweight “crew call” surface:

- “Need medic for underworld run.”
- “Crafter taking armor commissions.”
- “Pilot offering transport.”
- “Bounty hunter seeking spotter.”

## Playtest rubric

Use 5 players who do not know the codebase. Give no coaching beyond the UI.

### First 10 minutes

- Can they create a character?
- Can they explain their role fantasy?
- Do they know where they are?
- Do they know what to do next?
- Do they use buttons, typed commands, or freeze?
- Do they understand when a command is staged vs sent?

### First hour

- Do they complete a tutorial or starter contract?
- Do they earn a meaningful reward?
- Do they spend something?
- Do they meet an NPC they remember?
- Do they see another player or social opportunity?
- Do they know how to recover from injury/failure?

### First three sessions

- Do they have a self-directed goal?
- Do they understand faction reputation?
- Do they understand gear quality?
- Do they care about money?
- Did they encounter a communal or world event?
- Did they ask “what do I do now?” less often over time?

## Specific Claude prompts

### Prompt: first-session design audit

> Audit SW_MUSH from the perspective of a new player who has never used a MUSH and does not know WEG D6. Trace the first 10 minutes, first hour, and first three sessions for each starting archetype. Identify every point where the player may not know what to do next. Do not add new systems first; propose the smallest UI/help/briefing/contracts changes that make the existing systems legible.

### Prompt: role-loop parity audit

> Build a table of all supported player archetypes in SW_MUSH: combat, crafter, medic, slicer, scout, pilot, smuggler, bounty hunter, faction operative, social/RP, Force-sensitive. For each, identify the repeatable 5-minute loop, 30-minute loop, session goal, reward, risk, and social dependency. Flag roles that have advancement but weak moment-to-moment gameplay.

### Prompt: content-density audit

> Audit the current world/content layout for dead zones. For each major region, count actionable rooms, NPCs, vendors, trainers, boards, hazards, quest hooks, faction hooks, crafting hooks, and travel links. Then propose wayfinding/event-magnet changes that improve perceived density without adding hundreds of rooms.
