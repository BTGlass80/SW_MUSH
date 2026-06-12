# Web Client Vision & Wire Protocol — Design v1.2

**SW_MUSH — Star Wars D6 Revised & Expanded · Clone Wars era (~20 BBY)**
**BTGlass80 — May 24 2026**
**Status:** v1.2 — adds §3.15 (engine-canonical command discipline), §6.3.1 (`pass` button requirement), §6.13 (Force panel for Force-sensitive PCs), §10.10 (era-fidelity sanity checklist) in response to design-drop review findings. Brian sign-off pending.

**Changelog:**
- **v1.2** (May 24 2026 night) — Folds in findings from the Claude Design drop review (`design_review_may24_v1.md`). Adds §3.15 (NEVER-invent mechanics list, including `stance` is not canonical), §6.3.1 (pass-button requirement in declaration and posing phases), §6.13 (Force panel spec for Force-sensitive sheets), §10.10 (era-fidelity sanity checklist with explicit checkbox items). Tightens §6.3 (combat panel) and §6.4 (inventory) to reference engine-canonical command list. Folds the v1.1 §10.9 Claude Design re-brief recommendations into a more rigorous checklist.
- **v1.1** (May 24 2026 evening) — Adds map renderer architecture (§7.13) clarifying the separation between asset library, composition engine, and game-data layer. Adds §10.9 Claude Design redirect — the explicit re-brief for visual designers to produce asset libraries and visual language, not the map itself.
- **v1.0** (May 24 2026 afternoon) — Initial draft. Vision, protocol catalog (the ICD), panel-by-panel UI catalog, map tier deep-dive, diegetic flourishes, roadmap, Claude Design handoff appendix.

**Companion / superseded docs:** `CLAUDE_DESIGN_BRIEF.md` (map-only brief — folded into §7 below), `web_client_ux_overhaul_v1.md`, `ground_ux_overhaul_design_v1.md`, `web_ux_competitive_analysis.md`, `Map_Redesign_v2.html` (approved per-style footprint mockup).
**Architecture of record:** `sw_d6_mush_architecture_v48.md`.

---

## 0. Purpose of this document

This document has three jobs in one binding:

1. **Vision statement** for the rich web client — the "datapad of the galaxy" — describing the panels, behaviors, and atmosphere we are building toward.
2. **Wire protocol specification** (the "ICD" — interface control document) for the WebSocket and REST contracts between the SW_MUSH server and the first-party web client. This is the reference Claude (engineering sessions) consults when adding a feature, and the discipline that prevents protocol drift.
3. **Handoff package for Claude Design** — explicit enough about WEG D6 mechanics, Star Wars universe context (Clone Wars era), and SW_MUSH-specific systems that a visual designer with no prior project context can mock the UI without inventing mechanics. §3 (the Game Mechanics Primer) and §10 (the Claude Design Handoff Appendix) are written *to* a visual designer; the rest of the doc supports them.

**Reading order by audience:**

| You are… | Read in this order |
|---|---|
| Brian (owner) | §1 vision · §7 map · §9 roadmap · skim the rest |
| Engineering Claude (drop sessions) | §5 protocol · §6 panels · §3 primer as reference |
| Claude Design (visual mockups) | §3 primer · §10 handoff appendix · §7 map · §4 aesthetic · §6 panels |
| Future third-party tool author | §5 protocol · §3 primer |

**What this document does *not* do:**

- It does not specify the **server-side implementation** of any subsystem. The protocol describes the wire, not the engine. Implementation lives in the system-specific design docs cited inline.
- It does not redesign **Telnet output.** The Dual-Interface Principle (§1.3) preserves Telnet as canonical text; the web client is enrichment, not replacement.
- It does not specify **mobile** layouts beyond noting where mobile work will hook in later. Mobile is a Phase-3 deliverable per §9.
- It does not specify the **production renderer code** for the map. Map_Redesign_v2.html is an approved mockup; the production port is design-call-gated per architecture v48 §3.5.

---

## 1. Vision — the datapad of the galaxy

### 1.1 The framing

The web client is not a wrapper around a Telnet session. It is a **datapad** — a diegetic in-fiction device the player's character would plausibly be holding. Everything the character can know, sense, recall, or look up appears on this datapad. Combat math, dice rolls, faction reputation, the layout of the spaceport, the bounty board, the holocron entry on Mandalorians — all of it lives on the same surface, with the same visual grammar.

The Telnet stream is the text the character "hears" and "says." The datapad is the character's tools.

### 1.2 What we are building toward

The realized web client gives a player at any moment a glanceable answer to:

- **Who am I right now?** Wounds, attributes, Force Points, fatigue, encumbrance, faction standing.
- **Where am I?** Map at the appropriate zoom tier, security tier, who else is here, what services this place offers.
- **What's happening?** Combat state with dice transparency, conversation log, news ticker, world events.
- **What's mine?** Inventory, equipment, ship, housing, city, contracts, active jobs.
- **What can I do?** Context-aware action buttons, available skill checks, NPC interactions, exits.
- **What's the lore?** Click any noun in any text to open the holocron entry.

The first three are immediate-loop concerns. The next three are session-scope. All six should be one glance or one click away at all times.

### 1.3 The Dual-Interface Principle (preserved)

Text is canonical. Every piece of information the web client shows must also be reachable through Telnet — by typing `score`, `look`, `inventory`, `who`, `news`, etc. The web client is allowed to be *richer* (visual gauges, hover tooltips, animated transitions, drag-and-drop) but it is not allowed to be *exclusive* (hidden information, web-only commands that change game state).

The corollary: **structured JSON is supplemental to text, not a replacement for it.** Every command emits text (for Telnet, canonical) and, when relevant, also emits one or more JSON messages (for the web client to update panels without parsing text). This is the principle stated in `web_ux_competitive_analysis.md` §8 and formalized below in §5.

### 1.4 Why this matters

Three things compound from a rich, structured web client:

- **Retention.** Reviews of competing MUDs and browser RPGs (Iron Realms' Nexus, Torn) consistently flag rich web UIs as a top driver of player stickiness. New players who would bounce off a Telnet screen stay when the interface looks like a game.
- **Onboarding.** The 133+ command surface (current count) is unsearchable in Telnet. Tooltipped action buttons, a holocron, and contextual help let new players discover the game by clicking rather than memorizing.
- **Director AI surface.** The Director AI generates ambient events, news, faction movements, and personal quests. Those are far more impactful as a live newsfeed and map overlay than as text lines that scroll off-screen.

### 1.5 Aesthetic anchors (one paragraph here, full treatment in §4)

The visual language is **terminal-meets-datapad.** Dark backgrounds. IBM Plex Mono and Plex Sans. Amber and cyan accents. Faint scan-flicker. Per-planet palette overlays — sand-bleached for Tatooine, neon for Nar Shaddaa, blue-white clinical for Kamino. The hand-drawn WEG sourcebook maps (Mos Eisley overview, Chalmun's Cantina floor plan, Imperial garrison sections) are the spiritual reference point — iconographic, alive, drawn rather than diagrammed.

---

## 2. Reading-order check for the visual designer

If you are Claude Design and this is the first SW_MUSH document you have seen, the rest of the document will use terminology that needs grounding. Read §3 next. Do not invent mechanics; if §3 does not cover a term you encounter, ask before sketching.

If you are engineering Claude and your task is "add a wire message for X," jump to §5 to see whether the message type already exists and what its schema is; only sketch a new message type if §5 confirms none exists.

If you are Brian, you can read in any order; the map deep-dive is §7.

---

## 3. Game mechanics primer (for visual designers)

This section is the explicit primer that prevents the most common designer-confusion failure mode: drawing UI elements for systems that work differently than they appear. Every term used in panel mockups should be defined here. If it is not, raise it.

### 3.1 The WEG D6 dice system — the most important thing to get right

The whole game runs on a dice notation that looks like `3D+2`. **This does not mean "three six-sided dice plus 2."** It means:

- **3D** = three six-sided dice, rolled and summed.
- **+2** = two **pips**. A pip is `+1` to the rolled total. Three pips equal one die: `3D+3` is exactly equivalent to `4D`. The notation never exceeds `+2` for this reason; the next step up is `4D`.

So `3D+2` rolls three dice, adds them up, then adds 2.

**The Wild Die.** One of the dice rolled is the **Wild Die**, traditionally rendered in a different color (we render it green). The Wild Die has two special rules:

- If it rolls a **6**, you re-roll it and add the result (and if it rolls 6 again, repeat — this is "exploding").
- If it rolls a **1**, on most actions this signals a complication (the rules vary; the GM, here the server, decides what bad thing happens).

When mocking dice in UI, **always render one die distinctly as the Wild Die.** Never show four identical dice for `4D`.

**Dice pool examples:**

- `2D` = 2–12, average 7. (A toddler. Untrained.)
- `3D+2` = 5–20, average 12. (Trained adult.)
- `4D` = 4–24, average 14. (Skilled professional.)
- `5D+2` = 7–32, average 19. (Veteran.)
- `7D` = 7–42, average 24. (Master.)
- `10D+` = legendary.

### 3.2 The six attributes

Every character has exactly six attributes, always in this order:

| Attribute | Abbrev. | Governs |
|---|---|---|
| Dexterity | DEX | Aiming, dodging, melee, reflexes |
| Knowledge | KNO | Education, languages, lore, scholarship |
| Mechanical | MEC | Piloting, gunnery, vehicle ops, sensors |
| Perception | PER | Spotting, persuasion, con, awareness |
| Strength | STR | Hand-to-hand damage, lifting, soak |
| Technical | TEC | Repair, computer use, medicine, demolitions |

Each attribute has a dice rating like `3D` or `3D+1`. Most player characters start in the `2D–4D+2` range depending on species (Wookiees are `4D+2` Strength but only `1D` Mechanical, etc.).

**Designer note:** there are **exactly six**, always in that order. Do not add a seventh ("Charisma," "Willpower," "Luck"). Do not reorder them. The hex/wheel chart, if you make one, has six wedges.

### 3.3 Skills

Every skill is **owned by exactly one attribute** and starts at the attribute's rating. Improving a skill adds dice or pips beyond that.

Examples (the full list runs to ~80 skills across all six attributes; partial list shown):

- **Dexterity skills:** Blaster, Dodge, Lightsaber, Melee Combat, Brawling Parry, Thrown Weapons
- **Knowledge skills:** Alien Species, Bureaucracy, Cultures, Languages, Planetary Systems, Streetwise, Survival, Tactics, Value
- **Mechanical skills:** Astrogation, Beast Riding, Capital Ship Piloting, Communications, Repulsorlift Operation, Sensors, Space Transports, Starfighter Piloting, Starship Gunnery, Starship Shields
- **Perception skills:** Bargain, Command, Con, Forgery, Gambling, Hide, Investigation, Persuasion, Search, Sneak
- **Strength skills:** Brawling, Climbing/Jumping, Lifting, Stamina, Swimming
- **Technical skills:** Blaster Repair, Computer Programming/Repair, Demolitions, First Aid, Medicine, Security, Space Transports Repair, Starfighter Repair, Starship Weapon Repair

**Specializations.** A skill can have one or more *specializations* (narrower applications that benefit from extra dice). Example: a character with `Blaster: 5D+2` and a specialization in `Heavy Blaster Pistol: 6D+2` rolls 6D+2 when using a heavy blaster pistol specifically and 5D+2 with any other blaster.

**UI implication:** the character sheet panel needs a tree shape — Attribute → Skill → Specialization — not a flat list.

### 3.4 The difficulty ladder

When a character attempts something with uncertain outcome, the server rolls their relevant dice pool against a **difficulty number**:

| Label | Number range | Example |
|---|---|---|
| Very Easy | 1–5 | Hitting the side of a barn |
| Easy | 6–10 | Hitting a stationary target at short range |
| Moderate | 11–15 | Hitting a person in cover |
| Difficult | 16–20 | Hitting at long range in poor light |
| Very Difficult | 21–30 | Trick shot through a window |
| Heroic | 31+ | The Death Star exhaust port |

The difficulty number is built from a base plus modifiers (range, cover, darkness, smoke, target movement, called shot, etc.). When showing the difficulty in the combat UI, it should show **the breakdown** — `15 (base 10 + cover 3 + medium range 2)` — not just the final number.

### 3.5 The wound ladder

Damage in WEG D6 is not a hit-point bar. There are exactly **six wound states**, in this order:

1. **Healthy** (no marker)
2. **Stunned** — temporary; goes away after the scene. Penalty to actions.
3. **Wounded** — penalty to actions; visible bandage state.
4. **Wounded Twice** — heavy penalty; character is hurting.
5. **Incapacitated** — character is out of the fight, unconscious or nearly so.
6. **Mortally Wounded** — character will die unless stabilized within rounds.
7. **Killed** — permadeath in our system (see §3.10 below for nuance).

**UI implication:** wound state is a **discrete ladder**, not a continuous bar. Mocking it as a percentage HP bar is wrong. The visual we use in `combat_mechanics_display_design_v1.1.md` is a stylized humanoid figure outline where injury markers light up at each tier, plus the tier's label as a chip. There is no "73% HP."

### 3.6 Soak — damage reduction

When a character is hit, the **damage roll** (the weapon's damage code, e.g. `5D`) is opposed by the **soak roll** (the defender's Strength + armor bonus). The difference moves the wound state up the ladder by one tier per category of margin won by the attacker.

Strength soaks naked damage; armor adds dice to the soak roll. So a Wookiee in heavy armor might roll `6D` (Strength) + `2D` (armor) = `8D` against the damage.

**UI implication:** there is no concept of "armor durability" or "armor breaking." Armor either gives its soak bonus or it doesn't (it's broken / unequipped). The equipment panel should show soak total as `Strength soak: 4D · Armor soak: +2D · Total: 6D`.

### 3.7 Force Points, Dark Side Points, Character Points

These are **integer counters**, not bars or percentages.

- **Force Points (FP).** Spent (by player declaration) to double *all* your dice on one critical action. Earned for heroic, selfless deeds. A starting character typically has 1–3. **They are precious.** Spending one is dramatic. UI: a small constellation of icons, one per point, with a "spend FP" action button when conditions allow.
- **Dark Side Points (DSP).** Accumulated by using the Force for selfish or harmful ends, or by murderous PC actions. Each one increases the chance of falling to the dark side. Mostly irreversible. UI: same constellation pattern, but red/tarnished. Most characters have 0; non-zero is a serious narrative state.
- **Character Points (CP).** The XP-equivalent. Earned at session end. Spent to improve skills, or to add 1D to a dice roll on the fly (the "burn a CP for a die" mechanic). A starting character has ~5; an experienced one might have 50+.

These three are NOT interchangeable. Do not collapse them into a single "soul meter" or "karma bar."

### 3.8 Range bands

Ranged combat does not use precise meter measurements. It uses **four bands**:

- **Point-Blank** (essentially touching)
- **Short** (close enough)
- **Medium** (mid-range)
- **Long** (about as far as the weapon reaches)

Every weapon has its own range thresholds. A hold-out blaster's "Long" is much shorter than a sniper rifle's "Long." The difficulty modifier shifts: Short is easiest, Long is hardest.

**UI implication:** the combat panel should show a **horizontal strip** with the four bands, the attacker at one end, the target highlighted in the band they're currently in, and the difficulty modifier next to each band. This is the visualization in `combat_mechanics_display_design_v1.1.md`.

### 3.9 The combat round

A round in WEG combat is structured in three phases. The web UI should make these phases visible:

1. **Declaration phase.** Every combatant declares their intended action(s) for the round. Multi-actioning incurs a die penalty per extra action. Once declared, intent is locked.
2. **Resolution phase.** Initiative is rolled (Perception-based). Combatants act in initiative order. Each action: roll dice, compare to difficulty / opposed roll, narrate outcome.
3. **End-of-round bookkeeping.** Wound states update, stun fades, Force Points if spent are consumed, the next round begins.

The web combat panel should show **initiative order as a timeline**, **declared actions per combatant**, **rolls as they happen**, and a **damage feed** (a per-event log). All three are specified in `combat_mechanics_display_design_v1.1.md`.

### 3.10 Permadeath (SW_MUSH-specific)

The base WEG D6 rules treat death as permanent. SW_MUSH softens this slightly via the **`PG.1.death` system** (see `progression_gates_and_consequences_design_v1.md`):

- On death, the character becomes a **corpse** in the room. Other players can `loot` it.
- A `bacta tank` or `bacta pack` can revive within a time window.
- If un-revived, the character respawns with a **−1D penalty** for a recovery period (the "post-respawn debuff").
- True permadeath is opt-in but available.

This is a SW_MUSH design call, not WEG canon.

### 3.11 Force-sensitivity, Jedi, and Force powers (Clone Wars era specifics)

The current era is the **Clone Wars (~20 BBY)**, two-to-three years into the war. Important context:

- **The Jedi Order is intact and at war.** Jedi serve as generals leading clone troopers against CIS forces. They are not yet hunted.
- **Order 66 has not happened.** Anakin Skywalker is alive, a Knight, not yet Vader.
- **Padawans are common.** A young Force-sensitive PC can plausibly be a Padawan; the Padawan-Master system is designed in `padawan_master_system_design_v1.md`.
- **Force-sensitivity is rare.** Random NPCs are not Force-sensitive. PC Force-sensitivity is gated through chargen and tutorial choices (`F.7.j/k/l/m` — the Jedi Village path on Dantooine).
- **The Sith exist but are hidden.** Dooku and Sidious operate from the shadows. PC Sith are extraordinarily rare.

**Force powers** are skills under their own subsystem (Control, Sense, Alter). Force powers are not "spells" with mana cost; they are skill checks with a Force Point optional boost. Designer note: do not draw mana bars for Jedi PCs. Force-related UI is FP counter + power-check log.

### 3.12 The faction landscape (Clone Wars era)

Major factions a UI must accommodate (in roughly descending visibility):

- **Galactic Republic.** The good guys (mostly). Led by Chancellor Palpatine (secretly Sith — the player doesn't know). Clone troopers, Jedi generals. Color: blue/white/red Republic insignia.
- **Confederacy of Independent Systems (CIS).** The separatists. Droid armies (B1 battle droids, B2 super battle droids, droidekas), Trade Federation backing, Count Dooku at the head. Color: dark steel, hex insignia.
- **The Jedi Order.** Allied with the Republic but distinct. Robes, lightsabers, no faction insignia per se but a recognizable visual identity.
- **The Hutt Cartel.** Crime lords. Officially neutral, profiting from the war. Hutt sigil (the curling glyph).
- **Mandalorian factions.** Death Watch, the New Mandalorian government, mercenary clans. Beskar armor, T-visor helmets.
- **Bounty Hunters' Guild.** Cross-faction.
- **The Black Sun.** Galactic crime syndicate.
- **The Falleen Syndicate.** Smaller crime org — replaces a deferred GCW reference (Q1 design call).
- **Local planetary governments.** Tatooine has none meaningful; Coruscant has the Republic Senate; Naboo has the queen; etc.

**Designer note:** this is **NOT the Galactic Civil War.** No Empire. No Rebel Alliance. No stormtroopers (clones instead). No TIE fighters (Republic gunships and CIS vulture droids). The aesthetic is *Phantom Menace / Attack of the Clones / Revenge of the Sith era*, not *A New Hope*.

If you find yourself referencing Vader, Luke, Leia, Han, the Death Star, the Emperor, or stormtroopers (in their OT form), **stop** — that is the wrong era. The right reference points are Anakin (as Knight), Obi-Wan, Yoda, Mace Windu, Ahsoka, Padmé, Dooku, Grievous, Ventress, Kit Fisto.

### 3.13 Security tiers (SW_MUSH-specific)

Every game location has one of three security tiers, displayed as a badge:

| Tier | Badge | Meaning |
|---|---|---|
| **Secured** | green | PvE blocked, PvP blocked. Safe. Authority enforces. |
| **Contested** | yellow | PvE allowed, PvP by mutual consent or bounty. |
| **Lawless** | red | PvE unrestricted, PvP unrestricted. Frontier rules. |

Per the locked `security_model_design_v1.md` and `contestable_wilderness_design_v2.md`: hand-built city rooms are **secured**, a curated set of zones is **contested**, and **wilderness regions** carry the bulk of contested and lawless. The web client should show the badge prominently in the room context panel and subtly tint the terminal frame (green/yellow/red) to give peripheral awareness.

### 3.14 Wilderness — the contestable frontier

Wilderness regions (per `wilderness_system_design_v1.md` and the May 24 lock of `contestable_wilderness_design_v2.md`) are tile-gridded open spaces — the Dune Sea on Tatooine, the Jundland Wastes, etc. Each region:

- Is a grid (typically 40×40) of terrain tiles (dune, canyon, oasis, rocky outcrop, vaporator field, etc.).
- Has hand-placed **landmarks** (Tusken camps, abandoned mines, moisture farms, anomalies).
- Hosts random encounters (Tusken war parties, krayt dragons, jawa sandcrawlers, Republic patrols, sandstorms).
- Has stamina/hazard mechanics — the desert hurts you over time.
- Is **contestable** — one faction can own it, contests run on a 7-day timer culminating in a "Region Anchor" boss fight, and faction influence accumulates from missions/bounties/harvest/anomalies.
- Hosts **player cities** — citadels-in-the-frontier.
- Hosts **anomalies** — temporary spawned events from "Imperial corvette down" to "krayt dragon emerged" world bosses.

The wilderness map view (Tier 1 wilderness, parallel to the Tier 1 city district view) needs to render all of this — terrain, landmarks, anomalies, contest state, influence overlays, the player's position as a dot, faction-owned territory borders.

### 3.15 Engine-canonical commands — the never-invent list

The single most expensive failure mode in UI design for SW_MUSH is **inventing a mechanic that looks plausible but doesn't exist in WEG D6 R&E or in the engine**. The May 2026 review of the v2 design drop found one such invention (a "stance" cycle with persistent ±1D modifiers) that would have shipped a command the parser rejects and a mechanic that doesn't match WEG R&E. This section is the explicit list of what *does* exist so designers and engineers can pattern-match against it.

**Canonical phase-1 (declaration) actions a player can declare in combat:**

| Action | Parser command | Mechanics |
|---|---|---|
| **Attack** | `attack <target>` (ground), `fire <target>` (space) | Roll skill vs difficulty; damage on hit |
| **Dodge** | `dodge` | Reactive — raises incoming attack difficulty; can still act |
| **Full Dodge** | `fulldodge` | Entire round dodging; no other actions; opposed roll on every incoming |
| **Parry** | `parry` | Melee reactive defense — reactive opposed roll |
| **Brawling Parry** | (covered by parry with brawling skill) | Same reactive pattern, brawling skill |
| **Cover** | `cover` | Move to / behind cover; raises difficulty for attacks against you |
| **Move** | `move <direction or distance>` | Close or open range bands |
| **Aim** | `aim` | Spend round aiming; +1D next attack (up to +3D after 3 rounds, capped) |
| **Evade** | `evade` | Space-combat specific — evasive maneuvers, +1D defense, can still act |
| **Flee** | `flee` | Attempt to disengage from combat |
| **Spend FP** | `spend fp` | Double all dice for one critical action this round |
| **Pass** | `pass` | Hold action this round; OR accept auto-generated default pose in posing phase |

**Canonical pose-phase actions:**

| Action | Parser command | Effect |
|---|---|---|
| **Custom pose** | `cpose <text>` | Submit your pose for the combat round |
| **Plain pose** | `pose <text>` or `:` (in-room shorthand) | Emote in the room; does NOT register the combat round pose |
| **Accept auto-pose** | `pass` | Use the engine-generated default pose; advances to next round |

**Canonical non-combat commands relevant to UI:**

- `say <text>`, `whisper <target> <text>`, `page <target>=<text>` (speech variants)
- `+ooc <text>`, `+chan <channel> <text>` (out-of-band)
- `look`, `look <target>`, `examine <target>` (perception)
- `sheet`, `+sheet/skills`, `score`, `inventory` (character state)
- `get <item>`, `drop <item>`, `wear <item>`, `wield <item>` (item manipulation)
- `news`, `+news <number>` (holonet)
- `who`, `+who/faction` (player roster)

**Things that are NOT canonical and must NOT be designed around:**

- **`stance`** — no such command. No persistent stance state in R&E.
- **`mode <combat|exploration|social>`** — game does not have modes.
- **`cooldown`** as a command (cooldowns exist as game state but are not toggled by player command).
- **Hit-point bars / percentage health.** Wound state is a discrete 7-rung ladder.
- **Mana / energy pools.** Force Points are integer counters, not regenerating pools.
- **Armor durability.** Armor is binary equipped/not equipped; soak bonus is fixed.
- **Action points per turn.** Combat uses declared actions with MAP (multi-action penalty), not action points.
- **Levels / classes.** Characters have skills with dice ratings; no levels.
- **Critical hit / critical fail percentages on a percentile.** Critical events come from the Wild Die rolling a 6 (explode) or a 1 (complication).
- **Combat "tactics" / "stances" / "modes."** R&E does not have these as game systems.

**Discipline rule:** before designing any UI affordance, the designer should be able to point to (a) the parser command it sends, or (b) the engine state field it reflects. If neither exists, the affordance is inventing a mechanic.

---

## 4. Aesthetic anchors

### 4.1 Visual language

The web client visual language is **terminal-meets-holographic-datapad.** Specifically:

- **Dark backgrounds.** The terminal pane is near-black with subtle gradient. Side panels are dark slate. No pure white.
- **Two typefaces.** IBM Plex Mono for data (numbers, labels, code-like values) and short ALL-CAPS section headers. IBM Plex Sans for room descriptions, pose text, NPC dialogue, lore text. Display sizes use Orbitron for HUD chrome (the Star Wars feel) — already in place via `--font-display` per `ground_ux_overhaul_design_v1.md` §5.1.
- **Three accent colors** carry the entire palette: amber `#ffa640` (warm — neutral, active, "self"), cyan `#6ee8ff` (cool — informational, allied, "other"), red `#ff5a4a` (alert — hostile, damaged, contested). A green `#8fff8f` accent appears only for confirmed-secured states and successful checks.
- **Subtle motion.** A slow CRT scan-flicker on the chrome bezel. Pulse animations on active elements (player marker, your turn in combat, unread comms tab). No constant motion in the main reading area.
- **No filters in hot paths.** No `backdrop-filter`, no per-frame `filter: blur()`, no heavy shadows. CSS `transform`, `opacity`, and `color` only for animations. Per `CLAUDE_DESIGN_BRIEF.md` performance budget.

### 4.2 Planet-specific palette overlays

Each planet gets a palette overlay applied on top of the base. The overlays mostly affect map substrate, room frame tinting, and ambient mood — not core HUD chrome.

| Planet | Overlay character | Hex anchor |
|---|---|---|
| Tatooine | Sand-bleached, low-contrast amber, twin-suns glare | `#d4a574` warm tan |
| Coruscant (upper) | Clean blue-white, glass-and-chrome | `#c5d8e8` cool ice |
| Coruscant Underworld | Smudged red-orange, neon haze, perpetual twilight | `#c46a3a` smog amber |
| Nar Shaddaa | Magenta-and-cyan neon, wet streets, vapor | `#ff5fb3` neon pink |
| Kamino | Cool teal-silver, storm-grey, rain | `#7eb8c4` storm teal |
| Geonosis | Rust-oxide red, dust, hex-rock | `#a0533a` oxide |
| Dantooine | Soft green-gold, savanna, low horizon | `#a8c47a` grass |
| Naboo | Lakes-and-stone, soft blues and creams | `#9dbcc4` lake |
| Kashyyyk | Deep forest green, dappled gold | `#3d6e3a` canopy |
| Mandalore | Steel and cobalt, hard-edge angularity | `#5a6b8f` steel |
| Geonosian wilderness | Dust storms and oxide | (extension of Geonosis) |

Designer task in the appendix: produce a swatch sheet with the full per-planet palette derived from these anchors. Two planets minimum at mockup time (Tatooine + one of Coruscant Underworld / Nar Shaddaa for maximum aesthetic contrast).

### 4.3 The WEG sourcebook reference target

The hand-drawn maps in the *Star Wars Sourcebook (2nd ed.)*, *Galaxy Guide 7: Mos Eisley*, and the *Imperial Sourcebook* (the latter for visual sensibility, not lore — that's GCW-era) are the **spiritual reference** for our map. Specifically:

- **Mos Eisley overview map** (GG7 p. 13): the Dune Sea / Jundland Wastes / Mos Eisley regional spread with arrowed routes. This is the Tier-3 Tatooine planet view target.
- **Chalmun's Cantina floor plan** (GG7 p. 53): individually-drawn tables and booths around the iconic bar curve, with numbered points of interest. This is the Tier-0 site view target — far beyond abstract footprints.
- **Imperial garrison cross-sections** (Imperial Sourcebook): isometric levels with labeled rooms and turbolifts. Reference for ship interiors and underground bases.
- **Tierfon Rebel Outpost** (multi-page spread): how a hand-drawn floor plan can carry both information and atmosphere.

We are NOT directly copying these (copyright, era mismatch). We are matching their **drafting sensibility** — iconography over abstraction, atmosphere over schematic. Per-style room footprints (already in `Map_Redesign_v2.html`) are the floor; named-landmark *illustrations* (Chalmun-the-cantina drawn as the iconic dome with the band stage protrusion, not a generic rect with a "C" glyph) are the ceiling.

### 4.4 Diegetic framing

The client should feel like the character's tool, not the player's dashboard. Specific moves:

- **The terminal pane is "the comm/datapad screen."** Beveled chrome frame, faint scanline.
- **The right sidebar is "the heads-up overlay."** Status data the character would have at a glance.
- **News feed is "the holonet ticker."**
- **The map is the character's "holocarta" / "holomap."** Branded as such in flavor text.
- **The holocron is the character's "datacron archive."** In-fiction naming.
- **The character sheet is the character's "identity chip / dossier."**
- **The "datapad mode" hotkey** (toggle) reframes the right panel as if the character is physically looking at a tablet — slight tilt, edge-glare, the data presented as if displayed on a held device. Same data, different framing. Optional flourish, not a requirement.

This isn't gimmickry; it's a unification trick. When everything is framed as something the character would have, the player stops feeling like they are "operating a UI" and starts feeling like they are "checking their datapad."

---

## 5. Protocol architecture (the ICD)

This section is the **wire protocol specification.** It defines the exact contracts between the SW_MUSH server and the first-party web client. Engineering sessions consult this section before adding a message type or REST endpoint. The discipline rule is in §5.10.

### 5.1 Transports

The web client uses **two transports** in parallel:

- **WebSocket** (port 4001 today, served from same aiohttp app as HTTP). Persistent, bidirectional, low-latency. Used for game commands, server push events, and any state that updates during play.
- **REST** over HTTP (port 8080). Stateless reads. Used for character creation, reference content (skills, species, lore), bootstrap snapshots, and any data the client would otherwise have to ask for repeatedly.

The principle: **WebSocket carries living state; REST carries reference and bootstrap.** A change to the player's wound state goes over WebSocket. The blast radius diagram for thermal detonators goes over REST.

### 5.2 The push/pull contract

The web client never polls game state. The server pushes:

- A **`hud_update` message** after every command, containing the deltas the HUD cares about.
- A **system-specific event message** for major state changes (combat, space, pose, news, faction, city, mail, etc.).
- An **ambient broadcast message** for zone-wide events (sandstorms, faction movements, world bosses).

The client may *request* a refresh via specific commands (`look`, `score`, `inventory`) — but those are user-initiated, not poll loops. There is no `setInterval(fetchHUD, 5000)` anywhere.

### 5.3 Bootstrap then diff

On WebSocket connect (after auth handshake), the server sends a **`session_bootstrap` message** containing the full state snapshot the client needs to render every panel:

- Full character sheet (sheet payload identical to the REST `/api/sheet` response).
- Current room context (description, exits, contents, security tier, services).
- Active combat state (if in combat).
- Active space state (if in space / piloting).
- Active jobs / contracts.
- Faction reputation map.
- Comms scrollback (last N entries per channel, configurable).
- Active anomalies and contests visible to the player.
- Inventory and equipment.

After bootstrap, the server sends **diffs** — partial updates indicating what changed. `hud_update` carries only the fields whose values differ from last push. The client merges into its in-memory state.

A `resync` message is available for the client to request a full re-bootstrap if it suspects it has drifted (e.g. after a reconnect or a long idle).

### 5.4 Subscription model

The client tells the server which streams it cares about right now. On WebSocket connect, the client sends a `subscribe` message with a list of stream keys:

```json
{
  "type": "subscribe",
  "streams": ["hud", "combat", "comms", "news", "space", "map", "faction"]
}
```

Server only emits messages whose stream key the client subscribes to. The client can unsubscribe (e.g. close the map panel → `unsubscribe: ["map"]` → server stops sending map deltas).

This serves two purposes:

- **Bandwidth control** for mobile / slower connections.
- **Future capability negotiation** — if a client doesn't speak a new message type yet, it doesn't subscribe to that stream.

Default subscription on connect (the "everything" set) is all current streams. Subscription is sticky per session; clients re-state it on reconnect.

### 5.5 Versioning

Every server→client message carries a `schema_version` field. The discipline rules:

- **Increment on breaking change.** Adding a new optional field is not a breaking change. Removing a field, renaming a field, or changing a field's type *is*.
- **Server supports last N versions** (we'll start with N=2 — current and previous). Old clients still work during a transition window.
- **Client states preferred version** on connect (`"protocol_version": 3`). Server downgrades responses if necessary.
- **Versions are per-message-type**, not global. `combat_state` v3 and `hud_update` v5 coexist.

### 5.6 Schema discovery (capability handshake)

The server exposes a REST endpoint that returns the live message-type catalog:

`GET /api/protocol/schema` → returns the full list of supported message types, their current schema versions, and the streams they belong to.

```json
{
  "protocol_version": 1,
  "streams": ["hud", "combat", "comms", "news", "space", "map", "faction", "city", "mail", "anomaly"],
  "messages": {
    "hud_update": { "version": 5, "stream": "hud", "schema": { /* JSON schema */ } },
    "combat_state": { "version": 3, "stream": "combat", "schema": { /* ... */ } },
    "pose_event": { "version": 2, "stream": "comms", "schema": { /* ... */ } },
    // ...
  }
}
```

This makes the client self-documenting and enables future-proofing — if we ever open the protocol to third-party tools, they consume this endpoint to know what they can subscribe to. **For now (first-party only), this endpoint exists for developer/Claude-Design inspection during build, not as a public ecosystem hook.**

### 5.7 Server→client message catalog

**Status legend:**

- **Shipped** — exists in the codebase at HEAD, payload may be partial.
- **Partial** — exists but missing fields the rich UI vision requires; needs extension.
- **Designed** — specified in a design doc but not yet wired.
- **Horizon** — required by the vision in §6 / §7, not yet specified.

| Message type | Stream | Status | Source of truth |
|---|---|---|---|
| `session_bootstrap` | (init) | **Horizon** | this doc §5.3 |
| `hud_update` | hud | **Partial** | extended by §6.1; today covers stats/exits/room/contacts; needs section-by-section extension per §6 |
| `combat_state` | combat | **Partial** | `web_client_ux_overhaul_v1.md`; needs timeline + per-event damage feed extensions |
| `combat_resolution_event` | combat | **Designed** | `combat_mechanics_display_design_v1.1.md` §4 (full TypeScript schema) |
| `pose_event` | comms | **Shipped** | `field_kit_audit_and_remediation_v1.md` §4 (canonical schema) |
| `space_state` | space | **Shipped** | `space_overhaul_v3_design.md` |
| `space_event` | space | **Partial** | needs per-event push (sensor contact change, shield hit, sublight throttle) — see §6.3 |
| `news_event` | news | **Shipped** | `director_ai_design_v1.md` |
| `chat_message` | comms | **Designed** | `web_ux_competitive_analysis.md` §5 (channel-tagged) |
| `inventory_change` | hud | **Horizon** | this doc §6.4 |
| `equipment_change` | hud | **Horizon** | this doc §6.4 |
| `skill_check` | hud | **Horizon** | this doc §6.7 (dice transparency for non-combat checks) |
| `force_event` | hud | **Horizon** | FP spend / DSP gain / power use |
| `cooldown_update` | hud | **Horizon** | wheel UI for cooldowns (heal, mission, harvest, etc.) |
| `map_geometry` | map | **Horizon** | per-area geometry payload — see §7 |
| `map_position` | map | **Horizon** | per-move position delta — see §7 |
| `wilderness_state` | map | **Horizon** | terrain tile under player, visible landmarks, hazards — see §7.4 |
| `anomaly_event` | anomaly | **Horizon** | wilderness anomaly spawn / phase / despawn — see `contestable_wilderness_design_v2.md` §2.8 |
| `contest_state` | faction | **Horizon** | region contest accumulation, anchor spawn — see `contestable_wilderness_design_v2.md` §2.6 |
| `faction_state` | faction | **Horizon** | reputation deltas, payroll countdown, faction news |
| `city_state` | city | **Horizon** | player-city status, vitality, treasury, guard alerts |
| `mail_event` | mail | **Designed** | `engine/mail` substrate — needs notification push |
| `quest_state` | hud | **Horizon** | tutorial chain progress, active mission tracker, training events |
| `holocron_link` | (none) | **Horizon** | lore cross-reference click target — see §6.8 |

Each entry's full payload schema lives in the system-specific design doc cited or, for **Horizon** items, will be specified before the message type is implemented. The implementation discipline (§5.10) requires that schema-first.

### 5.8 Client→server message catalog

| Message type | Status | Purpose |
|---|---|---|
| `command` | **Shipped** | Raw command line (the same string Telnet would receive) |
| `resize` | **Shipped** | Terminal width in characters, on connect + on resize |
| `token_auth` | **Shipped** | Auto-login from chargen handoff |
| `subscribe` / `unsubscribe` | **Horizon** | Stream subscription per §5.4 |
| `resync` | **Horizon** | Request a fresh `session_bootstrap` |
| `map_request` | **Horizon** | Request geometry for a specific area at a specific tier |
| `holocron_query` | **Horizon** | Request lore entry by slug or noun |
| `tooltip_request` | **Horizon** | Lazy-load tooltip detail for a referenced entity |

### 5.9 REST endpoint catalog

| Path | Status | Purpose |
|---|---|---|
| `GET /chargen` | **Shipped** | Serves chargen.html |
| `GET /api/chargen/species` | **Shipped** | Species catalog with attribute ranges |
| `GET /api/chargen/skills` | **Shipped** | Skill catalog grouped by attribute |
| `GET /api/chargen/templates` | **Shipped** | Starter template presets |
| `GET /api/chargen/chains` | **Shipped** | Tutorial chain catalog (CW era) |
| `POST /api/chargen/validate` | **Shipped** | Validate build without saving |
| `POST /api/chargen/create-character` | **Shipped** | Atomic account+character creation |
| `POST /api/auth/login` | **Shipped** | Token-based auth |
| `GET /api/auth/check` | **Shipped** | Verify token |
| `GET /api/protocol/schema` | **Horizon** | Live message-type catalog per §5.6 |
| `GET /api/sheet/{character_id}` | **Horizon** | Full character sheet snapshot |
| `GET /api/inventory/{character_id}` | **Horizon** | Inventory snapshot |
| `GET /api/lore/{topic_slug}` | **Horizon** | Holocron entry (species, planet, faction, weapon, NPC, etc.) — feeds tooltips and the holocron browser |
| `GET /api/lore/index` | **Horizon** | Holocron index for search/browse |
| `GET /api/map/area/{area_slug}` | **Horizon** | Static area geometry (rooms, polygons, labels, landmarks) |
| `GET /api/map/wilderness/{region_slug}` | **Horizon** | Wilderness region map data — tiles, landmarks, edges |
| `GET /api/map/planet/{planet_slug}` | **Horizon** | Planet-tier map data |
| `GET /api/map/galaxy` | **Horizon** | Galaxy-tier map data (sectors, hyperlanes, faction shading) |
| `GET /api/reference/skills` | **Horizon** | Skill details (descriptions, difficulty examples, etc.) |
| `GET /api/reference/weapons` | **Horizon** | Weapon stat blocks |
| `GET /api/reference/factions` | **Horizon** | Faction summaries with current era state |

REST endpoints can be cached aggressively by the client (with `Cache-Control` headers from the server). Reference data rarely changes mid-session.

### 5.10 Discipline — the maintenance rule

This is the rule that prevents the doc from drifting from reality (which is the standing failure mode per architecture v48 §6.2):

**Before merging code that sends a new server→client message or adds a new REST endpoint, an engineering session must:**

1. Confirm the message type or endpoint exists in §5.7 / §5.8 / §5.9 above.
2. If it doesn't, add it (status: Designed) with its schema, *in the same drop* that wires it.
3. If extending an existing message type's payload, bump `schema_version` if breaking; add the field to the schema in this doc otherwise.
4. Update the entry's status from Designed → Shipped when the wiring is verified by tests.

The pre-flight audit pattern (architecture v48 §6.2) extends to this doc: when consolidating, grep HEAD for message-type strings and compare against the catalog. Drift becomes a phantom, gets fixed.

### 5.11 Telnet parity check

For every message type whose information could affect a player's decisions, there must be a Telnet command that surfaces the same information in text form. The web is allowed to be *richer* (a wound-figure diagram vs the words "Wounded Twice"), not *exclusive* (a critical alert that only appears on the web). The parity check is:

- For each Horizon message in §5.7, name the Telnet command that surfaces the same info. If no such command exists today, propose one before shipping the web feature.

This is the Dual-Interface Principle (§1.3) operationalized.

---

## 6. Panel catalog — what the rich web client shows

This section is the spec for every panel in the rich client. Each subsection is structured the same way:

- **What it shows** — the player-facing content.
- **Why it matters** — the player-experience rationale.
- **Wire data** — which message types feed it.
- **Mockup brief** — guidance for Claude Design.

The layout target (per `web_client_ux_overhaul_v1.md` and `ground_ux_overhaul_design_v1.md`) keeps the existing two-column grid (terminal pane + right context panel) but expands the right panel substantially and adds expandable "expand-on-click" panels for the holocron, full sheet, and full map. Tabbed comms pane sits at the bottom of the terminal pane.

### 6.1 The persistent character HUD

**What it shows.** The "you-at-a-glance" cluster, always visible in the top of the right context panel:

- **Name** (small) and **species** glyph.
- **Wound state** as a stylized humanoid figure outline. The figure has discrete tier indicators that light up at Stunned / Wounded / Wounded Twice / Incapacitated / Mortally Wounded. Tooltip on hover shows the dice penalty.
- **Force Points** as a small constellation of light-points (one per FP). Click → "spend FP" action button (only enabled when conditions permit).
- **Dark Side Points** as a parallel constellation, tarnished red. Hidden if zero.
- **Character Points** as a numeric counter. Click → spend-CP modal.
- **Fatigue** chip (when present): hours-awake counter or stamina bar in wilderness.
- **Encumbrance** chip: green/amber/red status based on carried weight vs Strength.
- **Status auras** (small chips that appear when active): Stunned, Dodging, In Cover, Aim Held, Force-Focused, Intoxicated, Drugged, On Fire, Drowning, Bleeding (PG.1.death state), etc. Each has a tooltip with the mechanical effect.
- **Active morale aura** chip if the player is benefitting from an Entertainer's morale aura (per SRB.2).
- **Current security tier badge** (echoed from §6.2 for at-a-glance access).

**Why it matters.** This is the single most-looked-at panel. A player should always know their state without typing `score`. Wound state, FP, and status auras drive every immediate decision.

**Wire data.**
- `hud_update` (extended): wound_state, fp_total, dsp_total, cp_total, fatigue, encumbrance, status_auras, morale_aura.
- `force_event` (new): on FP spend or DSP gain.
- REST `/api/sheet/{id}` for full detail on demand.

**Mockup brief.** A stylized humanoid figure (genderless silhouette is fine — Star Wars has many species and the figure represents "your body") with five wound-tier markers that progressively light up. Avoid HP-bar treatment. The figure can use a glow at the head when Force-Focused (Jedi). Six small attribute chips below (D K M P S T) showing current dice ratings with subtle modifier indicators if buffed/penalized. The FP/DSP constellations are 1–5 small glyph slots; lit and dim. Iconography for status auras: 8 to 12 distinct glyphs for the most common states. Show three example mockups: healthy, mid-combat (Wounded once, dodging, in cover), critical (Wounded Twice, FP spent, Mortally Wounded). Keep it dense — this is the single most-rendered panel.

### 6.2 Room context panel

**What it shows.** Persistent below the HUD. Reflects the player's current location:

- **Room name** with security tier badge (green/yellow/red).
- **Room description** (the canonical text from `look`), persistent so players can reference it during combat.
- **Faction presence indicator** if the Director AI has zone faction state.
- **Territory ownership tag** if the wilderness region is claimed.
- **Services row** (icons): vendor, trainer, cantina, medical, docking bay, crafting bench, mission board, mail terminal. Click to interact.
- **Mini area map** — small SVG inset, 2-hop BFS from current room, clickable to move. Expands to the full map view on click.
- **Exits row** — labeled buttons (north (Pit Floor), south (Market), etc.). Click to move.
- **Other PCs in room** — clickable, opens a contact dossier with what you know about them (mediated by `pc_narrative_memory_design_v1.md`).
- **NPCs in room** — clickable, opens NPC interaction menu (talk, examine, attack if hostile, trade if vendor, etc.).
- **Items in room** — clickable, opens get/examine menu.

**Why it matters.** Room is the orientation anchor. Players check it dozens of times per minute in active scenes. Currently the description scrolls away after `look`; making it persistent is the highest-impact micro-improvement.

**Wire data.**
- `hud_update.room_description`, `room_services`, `room_contents.pcs`, `room_contents.npcs`, `room_contents.items`, `exits`, `security_tier`, `area_map`.

**Mockup brief.** Card-style layout. Top: room name with security badge inline. Body: description text in Plex Sans, two-thirds width. Service icons in a row. The 2-hop area map sits in a small SVG inset, ~200×200px, using the Map_Redesign_v2.html iconography (per-style room footprints). Exits as labeled chip buttons below. PC/NPC/Item rows are collapsible sections with one-click interaction menus on each entry.

### 6.3 Combat console (the dice-transparency panel)

**What it shows.** When `combat_state.active == true`, this section expands inline below the HUD:

- **Round number** and **phase indicator** (Declaration / Resolution / End).
- **Initiative timeline** — a vertical strip showing every combatant in initiative order, with their portrait (or species glyph), name, wound state pips, and current declared action. Your character is marked with a star.
- **Range strip** — the four-band horizontal strip per §3.8, showing each combatant's current band relative to you, with difficulty modifiers per band.
- **Action prompt** — when it's your turn, context-aware buttons (Attack, Dodge, Aim, Run, Use Force Point, Move, Take Cover, Surrender).
- **Live dice readout** — when a roll resolves, the panel shows the dice that were rolled with their face values. The Wild Die is visually distinct (green, exploding animation on a 6). Modifiers laid out: `5D+2 (skill) + 1D (aim) − 2D (Wounded Twice) = effective 4D+2`. Difficulty shown with breakdown: `15 (base 10 + cover 3 + medium range 2)`. Result: `19 → hit by margin 4`. Damage roll shown similarly.
- **Damage feed** — a scrolling log of recent hits/misses/effects in the round.
- **End-of-combat summary** — when combat resolves, a debrief panel: who hit what, how many CPs you earned, any wound state recovery, FP spent, lessons (skills that improved).

**Why it matters.** The dice math is the heart of WEG D6. Today it's hidden server-side and the player sees only the narrative result. Surfacing the math is *teaching*, *transparency*, and *theater*. New players learn the system by watching it work. Veterans appreciate the rolls. Both audiences forgive bad rolls more easily when they can see they were honest.

**Wire data.**
- `combat_state` (existing, extended): combatants array with positions, phase, round.
- `combat_resolution_event` (designed, per `combat_mechanics_display_design_v1.1.md`): full TypeScript schema in that doc — actor, target, action, attacker_pool, defender_pool/difficulty, damage_pool, soak.

**Mockup brief.** This is the most dice-heavy panel; get the dice right. Each die rendered as a six-sided cube face (or a clean numeric chip — designer's call), but the Wild Die must be visually distinct (green tint, slightly larger, animation on explode). Show three example mockups: (a) blaster shot at medium range against a B1 battle droid in cover, (b) lightsaber duel — two PCs, opposed roll, both with multiple modifiers, (c) Force power use — Knight rolling Control + Sense, FP spent (all dice doubled). The combat panel needs to feel **alive and dramatic**, not like a spreadsheet. A subtle red left-border accent when combat is active is already approved per `ground_ux_overhaul_design_v1.md` §5.3.

#### 6.3.1 The `pass` button — required in two places

A specific UX requirement that the May 24 design-drop review surfaced: the `pass` command must appear as a **first-class action button** with equal visual weight to other action buttons in **both** of these phases:

1. **Declaration phase.** Alongside ATTACK / DODGE / AIM / COVER / MOVE / SPEND FP / FLEE, the `pass` button is the canonical "hold action this round" choice. Useful for reactive play, conserving multi-action penalty, watching the scene develop, or simply not committing to anything. Must be visible with the other buttons — not buried in a tooltip or text link.

2. **Posing phase.** During the 180-second pose window, the engine generates an **auto-pose** that will be used if the player doesn't submit one. The `pass` button accepts that auto-pose immediately, advancing the round without waiting out the timer. Visual treatment: a prominent button labeled something like "▸ ACCEPT AUTO-POSE" with a tooltip noting "sends `pass` — uses the engine-generated default pose visible above." Three minutes is a long time when you're not feeling creative or when the moment doesn't warrant a custom pose. Burying `pass` as a tiny text link (the failure mode in the v2 design drop) forces players to type the command manually or wait out the timer — both bad UX.

The auto-pose text should be shown in the posing panel (it already is in current designs) so the player can read what they're accepting before clicking pass. A keyboard shortcut (e.g. `Ctrl+Enter` to submit custom pose, `Ctrl+P` for pass) makes both actions usable at speed.

**This is a hard requirement, not a recommendation.** The current designs that omit or de-emphasize `pass` would make players type the command manually every time the engine offers an auto-pose — friction the web client exists to eliminate.

### 6.4 Inventory and equipment (the paper doll)

**What it shows.**

- **Paper doll** — humanoid silhouette with equipment slots: head, eyes, chest, back, weapon (main hand), weapon (off-hand), belt, gloves, legs, boots, comlink. Visual representation of what's equipped where.
- **Soak readout** below the paper doll: `Strength soak 4D · Armor soak +2D · Total 6D`.
- **Carried inventory** as a grid of item cards. Each card shows a glyph + name + key stat (damage code for weapons, range bands, ammo count, weight, value). Hover for tooltip with full stats.
- **Encumbrance bar** — green/amber/red.
- **Quick equip** drag-and-drop or click-to-equip from inventory to paper doll slots.
- **Container drill-down** — clicking a pack/bag opens its contents.
- **Filter chips**: All / Weapons / Armor / Consumables / Quest / Misc.

**Why it matters.** Inventory in Telnet is a flat list. The web should make it visual. Equipment context (what's in which slot) drives combat math and is currently surfaced only by `score`.

**Wire data.**
- REST `/api/inventory/{id}` for full snapshot on first open.
- `inventory_change` (new) for deltas.
- `equipment_change` (new) for slot changes.

**Mockup brief.** The paper doll silhouette is genderless/species-neutral; equipment slots are highlighted rectangles around it. Item cards in the grid are ~80×100px, glyph-forward. Tooltip on hover shows full stats. Weapons specifically: damage code (`5D`), range bands with thresholds (`PB 3-5 · S 6-10 · M 11-25 · L 26-50` in meters), ammo state (`12/12 power cells`), special properties (`stun mode available`, `requires both hands`). Show example mockups for: a smuggler's loadout (blaster pistol, vibroknife, comlink, light armor), a Jedi Knight (lightsaber, robes, datapad, no armor), a Mandalorian (full beskar, blaster rifle, vambraces, jetpack).

### 6.5 Comms — tabbed channels

**What it shows.** A dedicated comms pane (per the approved direction in `web_client_ux_overhaul_v1.md`), positioned at the bottom of the terminal pane (~30% height):

- **Tab bar**: All · IC · OOC · System · Comlink · Faction · Holonet. Unread badge on inactive tabs.
- **Per-tab scrollback** — last N messages per channel, server-persisted within the session.
- **Channel-tagged messages** in standardized JSON per `chat_message` schema.
- **Inline reply** — clicking a player's name pre-populates `page <name>` in the input.
- **Holocron tooltips** — hovering any noun in a pose triggers a holocron preview tooltip after 500ms (per §6.8).

**Why it matters.** In active multiplayer sessions, social messages get buried in combat output. The single biggest complaint about MUD web clients is "I missed what they said because combat scrolled it off." A dedicated, tabbed, persistent comms pane fixes this.

**Wire data.**
- `chat_message` (new): `{ channel, from, to, text, timestamp, channel_subtype }`
- `pose_event` (existing, canonical schema in `field_kit_audit_and_remediation_v1.md` §4).

**Mockup brief.** Tabbed UI similar to a chat client. Tab labels short, badges for unread. Messages are timestamped (small, dim, right-aligned). System messages distinguished by color tint. IC vs OOC distinguished by font (Plex Sans vs Plex Mono). The pane should be resizable vertically by drag-handle. Filter chips above the tabs for "only this room" / "only PCs" / "only NPCs" / "search". Show three example states: quiet zone (mostly atmosphere), active scene (multiple PCs talking, NPC responses), combat (declarations, system messages, the occasional OOC).

### 6.6 Map — the holocarta

The map deserves its own deep-dive section. See **§7**.

### 6.7 The skill-check ribbon

**What it shows.** Whenever the player makes a non-combat skill check (Search, Persuasion, Streetwise, etc.), a small ribbon appears briefly at the bottom of the HUD:

- **Skill name** and **dice pool**.
- **Dice rolled** with face values (Wild Die distinct).
- **Difficulty** with breakdown.
- **Margin** (positive = success, negative = fail).
- **Result chip**: Success / Failure / Critical Success / Complication.

**Why it matters.** Same transparency rationale as combat. Players currently see "You search the rubble and find a credit chip" without knowing whether they rolled well or got lucky. The ribbon teaches the system and rewards skill investment visibly.

**Wire data.** `skill_check` (new): `{ skill, dice_pool, dice_rolled, difficulty, breakdown, result, margin, narrative_text }`.

**Mockup brief.** Slim ribbon, animates in, displays for ~4 seconds, animates out. Doesn't displace other UI. Dice rendered same way as combat (Wild Die distinct). Subtle sound cue on critical success / complication is a future flourish (audio is out-of-scope for the first design pass).

### 6.8 The holocron — clickable lore

**What it shows.** A panel that opens (right-side overlay or modal — designer's call) when:

- The player clicks any noun in any text (room description, pose, news, NPC dialogue).
- The player explicitly opens it via `help <topic>` or a sidebar button.
- A tooltip hover persists past 500ms (preview).

Contents per entry:

- **Title** and **type** (Species / Planet / Faction / Weapon / Vehicle / Person / Skill / Concept).
- **Era-aware content** — Clone Wars context, not GCW.
- **Body** — markdown-rendered prose, ~150–500 words per entry.
- **Cross-references** — clickable links to related entries (Mos Eisley → links to Tatooine, Jundland Wastes, Hutts, smugglers).
- **Player knowledge gating** — entries the player's character "knows" (based on Knowledge skill specializations, faction membership, places visited) are highlighted; entries they don't know show as "limited info — your character has not encountered this" with a teaser.

**Why it matters.** SW_MUSH has deep canon. New players don't know the difference between a Mandalorian and a Jedi. The holocron makes lore discoverable in-line with play, no Wookieepedia tab required. It also serves the Director AI's narrative output — when the AI generates a news event involving the Falleen Syndicate, the player can click "Falleen Syndicate" in the news ticker and learn what that is.

**Wire data.**
- REST `/api/lore/{slug}` for entry content.
- REST `/api/lore/index` for the searchable index.
- `holocron_link` (new) wire metadata — the server can emit "this text contains lore links at offsets X, Y, Z to slugs A, B, C" so the client renders them as clickable.

**Mockup brief.** Two visual treatments to consider:
1. **Modal overlay** — center-screen, dimmed background, single entry with cross-ref sidebar. Like a wiki page.
2. **Right-side drawer** — slides in from the right, occupies ~40% width, doesn't dim the rest. Player can keep the holocron open while continuing to play.

The drawer pattern is recommended (less disruptive). Treat it as a diegetic holocron (the round Jedi crystal) — opening it should feel like the character pulled out a reference device. Cross-references are styled as cyan underlined inline-links. Player-knowledge-gating: gated entries get a faded treatment with a "your character knows of the [Falleen Syndicate] but has not learned details" stub. Show three example entries: a species (Wookiee), a planet (Tatooine), a faction (Hutt Cartel).

### 6.9 Quest / progression tracker

**What it shows.**

- **Active jobs** — bounties, smuggling runs, mission board contracts, training assignments. Each shows progress (steps completed, deadline if any).
- **Tutorial chain progress** for new characters — the F.8.c chain step pills, lit up to current step.
- **Padawan-Master relationship** (for Force-sensitive characters) — current master, training streak, last lesson.
- **Faction payroll countdown** — when does the next payroll tick fire?
- **Cooldown wheels** — visual countdown for cooldown-gated actions (heal, harvest, mission accept, perform, sabacc hand, etc.). Wheels drain over time. Tooltip shows exact remaining.

**Why it matters.** Forgetting an active job or missing a payroll because you didn't notice the deadline is a feel-bad. Visual progression is also intrinsically rewarding (the dopamine hit of a progress bar filling).

**Wire data.**
- `quest_state` (new): array of active jobs with progress.
- `cooldown_update` (new): per-cooldown remaining-time and total-time.
- `faction_state.payroll_in_seconds`.

**Mockup brief.** Cooldown wheels are circular, drain over time, color-coded (healing = green, mission accept = amber, etc.). Active jobs are card-style with progress bars or step-checkboxes. Tutorial chain step pills already designed for chargen — extend that visual language. Padawan-Master block is a small two-portrait card with relationship status text.

### 6.10 News / Director AI / world state

**What it shows.**

- **Holonet news ticker** at top of screen — current breaking events from the Director AI, faction movements, anomaly spawns.
- **Expanded news pane** (click-to-expand): full recent news, filterable by faction / region / topic.
- **Faction state summary** — for each major faction (Republic, CIS, Hutt Cartel, Jedi, etc.), a small status block showing current narrative state, recent moves, and where they are pressing.
- **World event banners** — for major events (Region Anchor spawn, krayt dragon emergence, planetary upheaval), a transient banner across the top.

**Why it matters.** The Director AI is a key differentiator. Its output is currently text-in-the-stream that scrolls away. A dedicated news surface makes the AI's storytelling visible and persistent.

**Wire data.** `news_event` (existing), `anomaly_event` (new — see `contestable_wilderness_design_v2.md`), `faction_state` (new).

**Mockup brief.** Ticker is a horizontal scrolling strip at the very top, ~32px tall, terminal aesthetic. Expanded news pane is a sidebar overlay or modal with timeline. Faction state blocks are small cards, one per major faction, showing a sigil, current narrative one-liner, and a pressure-direction indicator (where they're advancing). World event banners take the full width when active and require a dismiss click.

### 6.11 Faction reputation

**What it shows.** A radial chart or hexagonal radar showing the player's standing with each major faction. Each wedge is a faction; the radial distance shows current reputation level. Hover for history.

Reputation tiers (per `faction_reputation_design_v1.md`):

- Hated / Hostile / Unfriendly / Neutral / Friendly / Honored / Exalted

Each tier unlocks faction-specific content (missions, vendors, training, housing).

**Why it matters.** Faction rep is a major progression vector and the current Telnet representation (`+rep` command) is just a list. The radial view makes the strategic shape visible — "I'm Friendly with the Republic, Unfriendly with the Hutts, Neutral with everyone else" reads instantly.

**Wire data.** `faction_state.reputation` (per-faction integer + tier label).

**Mockup brief.** Radial chart with ~8 wedges. Each wedge labeled with the faction sigil. The radial axis shows tiers (7 rings). The player's current standing is the polygon connecting their tier on each axis. Color the polygon amber. Hover over a wedge to highlight that faction and show numeric rep + tier. Click to see history.

### 6.12 The "datapad mode" toggle

**What it shows.** A hotkey (`Ctrl+D` or similar) toggles the right panel from "flat HUD overlay" mode to "diegetic datapad" mode. In datapad mode, the panel is rendered as if the character is holding a tablet device:

- Slight isometric tilt.
- Edge bezel with subtle holographic shimmer.
- Glare/reflection overlay (gentle).
- The data is exactly the same — only the framing changes.

**Why it matters.** This is a fun mode-switch that lets RPers screenshot a "your character is checking their datapad" moment for scene immersion, without being on by default (it slightly reduces information density).

**Wire data.** None — pure client-side visual treatment.

**Mockup brief.** Style reference: holographic Jedi datapads from the films. Subtle, not gimmicky. Same readability as flat mode.

### 6.13 Force panel — required for Force-sensitive PCs

For characters with `force_sensitive: true`, the sheet must render a dedicated Force panel. Audit issue F10 (April 2026) flagged the omission of this panel as a Medium-severity gap; the May 24 design drop review confirms it remains unaddressed in all sheet variants.

**What it shows.**

- **Three Force-skill dice ratings** — Control (Force-related actions on self), Sense (Force-related perception), Alter (Force-related effects on others). Each shown as a dice pool like other skills (e.g. `Control 4D+1`).
- **Powers known** — a list of individual Force powers the character has learned (e.g. Heal Self, Telekinesis, Lightsaber Combat, Affect Mind, Battle Meditation, Force Push, Concentrate, Receptive Telepathy). Each power tagged with which of Control/Sense/Alter skills it requires (single-skill powers tag one; combination powers tag two or three).
- **Force Points and Dark Side Points** — already in HUD; cross-reference them here. Don't duplicate the spend-FP affordance; just show the totals as a reminder.
- **Recent Force activity** (optional) — last few Force power uses with their rolls, like a mini-skill-check log.

**Visual style.**

The Force panel uses the cyan accent (`#6ee8ff`) more heavily than the rest of the sheet, with a subtle radial glow around the panel border to evoke the Force. The skill dice are rendered identically to other skills but in a separate section. Force powers list uses small SVG glyphs per power (eight to twelve glyphs covering the most common powers).

For dark-side characters (DSP > 0), the panel subtly tints toward red — the more DSP, the redder. At DSP ≥ 3, a "FALLING" warning appears.

**Wire data.**

The sheet payload schema (per `sheet_redesign_design_v1.md`) already includes a `force` block:
```python
"force": { control, sense, alter, powers: [...] } | None
```
When `force == None`, the panel is not rendered. When present, render per above.

**Mockup brief.**

Add a fourth example sheet mockup to the design priority list (§10.4): a Force-sensitive Padawan (Clone Wars era) with Control 4D, Sense 4D+2, Alter 3D+1, two powers learned (Lightsaber Combat, Concentrate), 3 FP, 0 DSP. The Force panel renders prominently between the attributes section and the equipment section.

### 6.14 FP rendering — no hard cap

A specific call-out (folded from audit F9): Force Points are not capped in WEG R&E. A character earns FP through heroic acts and accumulates them without an engine-enforced ceiling.

**Implications for UI.**

- Do NOT render FP with a fixed `fp_max` denominator (e.g. `2/3`). This implies a cap that doesn't exist.
- DO render FP as a **growing constellation of glyphs** — current count visible as filled icons. The "empty" slot count grows dynamically based on the character's recent earn pattern (or is unlimited — let the row wrap).
- Alternative: simple integer counter ("FP: 4") with no slot visualization. Less evocative but mechanically honest.

The current v2 sheet designs hardcode `fp_max = 3`. Fix during implementation.

---

## 7. Map system — the deep dive

The map is the keystone of the player experience. The existing `CLAUDE_DESIGN_BRIEF.md` (May 3 2026) covers the map alone; this section supersedes it and extends the brief substantially based on the May 24 lock of `contestable_wilderness_design_v2.md` (wilderness contestability) and Brian's direction (May 24 2026) to push past schematic "shapes" toward stylized geography.

### 7.1 What "actual view of the city" means

The currently-approved `Map_Redesign_v2.html` mockup already establishes per-style room footprints — docks have notched bay doors, cantinas read as pills, civic structures have pediments, gates have chevrons, Hutt structures have doubled borders, landmarks are hexagons. Layered substrate (dune undulation, grit, debris) sells "this is desert, not noise." Street ribbons have shoulder gradient + core surface + lighter centerline. This is past abstract.

But Brian's direction is to push further. **The reference target is the hand-drawn maps in *Galaxy Guide 7: Mos Eisley***: Chalmun's Cantina drawn with individually-rendered tables, the curved bar, the bandstand, the back hallway. The Mos Eisley regional map with the Dune Sea, the Jundland Wastes, named arrowed routes ("To Fort Tusken," "To Jabba's Palace"). The Imperial garrison cross-sections with labeled rooms.

We are not directly copying these (copyright, era). We are **matching the drafting sensibility**. Specifically:

- **Named landmarks have unique illustrations**, not generic glyphs. Chalmun's Cantina is drawn as the iconic dome shape with the band stage protrusion. Docking Bay 94 is drawn as the circular bay with a docked ship silhouette. Jabba's Palace is drawn as the iconic mass with the entrance arch. The Lucky Despot is the wrecked star cruiser silhouette. Each is hand-authored as an SVG asset, ~5–15 KB per landmark.
- **Building density and street furniture** are visible. Speeder-bike racks, vaporator clusters, market awnings, scrap piles. Small SVG glyphs scattered to make the city *populated*.
- **Atmospheric overlays** sell the planet. Tatooine has twin shadow casts from buildings (two suns), a sand-haze gradient over the ground, scattered dune mark patterns. Coruscant Underworld has neon glow halos around vendor stalls, smog drifts, perpetual amber twilight. Nar Shaddaa has rain streaks, neon reflections in wet streets, vapor plumes from industrial vents.
- **Time-of-day** is visible on the map. Day / dusk / night / dawn cycles shift the palette and shadow direction. Lit windows at night.
- **Weather** appears as overlay effects when active. Sandstorms partially obscure the Tatooine map. Coruscant Underworld has occasional industrial smog events. Kamino has perpetual rain.
- **Verticality is hinted via drop shadows** even though the rendering is top-down. Taller buildings cast longer shadows.

The result should feel like a *drawn* map — atmospheric, alive, full of detail you discover on a second look — not a *diagrammed* map.

### 7.2 The five zoom tiers (carried forward from CLAUDE_DESIGN_BRIEF.md)

Same five-tier structure as the prior brief, with one nuance: **Tier 1 has two variants — Tier 1a (city district) and Tier 1b (wilderness region).** They are visually distinct because the underlying data structure is different (room graph vs tile grid).

| Tier | Scope | Primary use |
|---|---|---|
| **0** | Site / interior cluster (~5 rooms or one building's floor plan) | Looking at a cantina interior, a ship interior, a building |
| **1a** | City district (one zone, ~10–25 rooms) | Active play in a city — most-used view |
| **1b** | Wilderness region (one region, 40×40 tile grid) | Active play in wilderness — moving tile-to-tile |
| **2** | Whole city (~50–100 rooms across multiple zones) | Strategic orientation in a settled area |
| **3** | Planet (top-down or stylized) | Travel between cities + wilderness regions |
| **4a** | Star system | Space travel within a system |
| **4b** | Sector | Strategic space, hyperlanes |
| **4c** | Galaxy | Faction shading, hyperlane network, where am I |

Smooth zoom transitions between tiers. The breadcrumb in the corner reads: `GALAXY ▸ OUTER RIM ▸ TATOOINE ▸ MOS EISLEY ▸ SPACEPORT ▸ Docking Bay 94`.

### 7.3 Tier 1a — city district (the everyday view)

This is the most-used view. Reference: the approved `Map_Redesign_v2.html` Tier-1 District mockup, extended with the §7.1 enrichments. Specifically:

- Building footprints with **per-style silhouettes** (already in v2 mockup).
- **Named-landmark illustrations** overriding the generic style footprint for iconic locations.
- **Streets as actual drawn paths** — not point-to-point lines. Bending, varying width, with shoulder/center/wear treatment.
- **Street furniture and ambient detail** scattered between buildings.
- **District labels** at low opacity overhead.
- **Security tier overlays** — subtle green/yellow/red tint over the polygon containing each room.
- **Player marker** prominent (cyan chevron with pulse).
- **Other PC markers** smaller (cyan dot).
- **NPC markers** distinguished by attitude (amber friendly, red hostile, grey neutral) — per existing radar legend.
- **Faction territory borders** if the district has been claimed (rare in cities — usually wilderness).
- **Time-of-day** applied as a palette shift and shadow direction.

### 7.4 Tier 1b — wilderness region (the new beast)

Per `wilderness_system_design_v1.md` and `contestable_wilderness_design_v2.md`, a wilderness region is a 40×40 tile grid. Each tile has a terrain type (dune, canyon, oasis, rocky outcrop, vaporator field, etc.). Players move tile-to-tile. The map view needs to render:

- **Terrain tiles** — each rendered with the terrain's visual signature. Dunes show wind-rippled sand patterns; canyons show sandstone walls; oases show the unlikely-water-and-scrub motif; vaporator fields show vaporator spires. Tiles bleed into each other (no hard grid lines — the grid is a logical structure, visually painterly).
- **Landmarks** — hand-placed, hand-illustrated. The Tusken camp has tents and a bonfire glyph. The abandoned mine has the entrance tunnel mouth. Moisture farms are vaporator clusters around a domed homestead.
- **Faction-owned territory** — when a faction owns the region, a subtle border/shading shows their influence. Influence falloff at the edges where contests happen.
- **Active contest** — when a contest is running, a dramatic overlay: a glowing band along the contested edge, a countdown timer, current accumulation scores.
- **Anomaly markers** — when a wilderness anomaly is active (krayt dragon, downed corvette, Imperial patrol intrusion, world boss), a distinctive icon appears at its location with a glow. Tier 3 anomalies (world bosses) are visually dramatic — pulsing, large, mythic.
- **Player position** as the chevron marker, fixed-size regardless of zoom.
- **Other PC positions** — when in shared sight radius (per region rules).
- **Sight radius / fog-of-war** — tiles beyond the player's terrain-specific sight radius are dimmed.
- **Travel routes** — when the player uses the `travel` command toward a known landmark, the path is rendered.
- **Hazard overlays** — when a sandstorm or other weather event is active, the relevant tiles get the overlay.
- **Resource quality indicators** — per `contestable_wilderness_design_v2.md`, regions have weekly resource quality variance for harvesting. A subtle indicator (a "Metal 1.3×" tag, for example) appears on tiles that host harvestable resources during high-quality weeks.

This is the most ambitious view, because it has the most layers. It is also the most differentiated from any other MUD client we've reviewed — most don't have wilderness rendering at all.

### 7.5 Tier 2 — city view

Per CLAUDE_DESIGN_BRIEF.md: districts as filled colored polygons with strong borders. Major streets as wider lines. Room interiors collapsed to small dots or building markers (no labels). District names large. Major landmarks visible as pins. Tile substrate (sand/duracrete) prominent.

Extension for the rich vision: even at Tier 2, **named landmarks retain their distinctive icon** (a small simplified version of the Tier 1a illustration). The player should be able to see "Jabba's Palace" as the iconic mass even when zoomed out to whole-city scope.

### 7.6 Tier 3 — planet view

Per CLAUDE_DESIGN_BRIEF.md: top-down or stylized-abstract planet body. Cities as labeled pins. Wilderness regions as colored polygons. Hyperspace beacon at one position. Atmosphere overlay/glow for flavor.

Extension: **wilderness regions get terrain-themed fill** (the Dune Sea is sand-tan with a hint of dune pattern; the Jundland Wastes are rocky and red). Cities get a small skyline silhouette next to their pin. Major landmarks across the planet (the Sarlacc, Jabba's Palace, Mos Eisley) are individually illustrated even at this tier.

### 7.7 Tier 4abc — system, sector, galaxy

Per CLAUDE_DESIGN_BRIEF.md, unchanged. The galaxy tier specifically gets era-aware faction shading — Republic core blue, CIS-controlled rust-red, Hutt space green, Outer Rim dim — calibrated for **Clone Wars**, not GCW.

### 7.8 What's drawn at each tier — the layer system

In z-order, bottom to top (carried from CLAUDE_DESIGN_BRIEF.md with extensions):

1. **Atmosphere / sky** — planet-specific gradient (Tier 3+) or zone-specific (Tier 1–2).
2. **Tile substrate** — palette-quantized PNG or SVG-tile, the painted base (sand, duracrete, water, void). Tiers 0–2.
3. **District fills + borders** — colored polygons (Tiers 1a–2).
4. **Faction territory overlay** — semi-transparent influence shading (Tiers 1b–4c).
5. **Security tier tinting** — subtle green/yellow/red wash over rooms/regions.
6. **Exit paths / streets** — polylines with shoulder + center + wear styling.
7. **Building footprints / room polygons** — per-style silhouettes or named-landmark illustrations.
8. **Landmark icons** — point markers at landmark positions (Tiers 1b–4).
9. **Street furniture / ambient detail** — small scattered SVG glyphs (Tier 1a).
10. **Weather overlay** — sandstorm, rain, smog effects when active.
11. **Anomaly / contest overlays** — dramatic markers for active events (Tier 1b).
12. **Labels** — street names, district names, landmark names, with min-zoom/max-zoom visibility.
13. **NPC markers** — small distinct shapes per attitude.
14. **Other-PC markers** — cyan dots.
15. **Player marker** — chevron with pulse, fixed-size on-screen, always on top.
16. **HUD chrome / breadcrumb** — outside the map content, on the bezel.

### 7.9 Marker system (designed in detail)

Player marker, the most-rendered element:

- **Shape:** cyan chevron pointing in the direction of last movement.
- **Pulse:** outer ring fades in and out at ~1 Hz, very subtle.
- **Animation:** lerp between positions on room change, ~150ms ease-out. Never teleports.
- **Fixed size on-screen** at all zoom levels. Map content scales; marker doesn't.

Other markers:

| Entity | Shape | Color | Size |
|---|---|---|---|
| Other PC (allied / unknown) | small chevron | cyan | 60% of player |
| NPC friendly | dot | amber | small |
| NPC hostile | triangle | red | small |
| NPC neutral / unknown | dot | grey | small |
| Vendor / merchant | dot with awning glyph | amber | small |
| Mission giver | dot with exclamation | amber | small |
| Bounty target | crosshair | red | medium |
| Quest objective | star | green | medium |
| Anomaly Tier 1 | pulsing circle | amber | medium |
| Anomaly Tier 2 | pulsing hex | red-orange | medium-large |
| Anomaly Tier 3 (world boss) | mythic glyph (large, dramatic) | gold-orange | large |
| Region Anchor (culminating fight) | dramatic skull-or-crown glyph | gold | large |

### 7.10 Transitions

- **Zoom in/out:** smooth animation, ~400ms ease-in-out. Cross-fade layer visibility (district fills fade out as room interiors fade in).
- **Player crosses room boundary:** marker lerps 150ms; map stays still (camera tracks marker if needed).
- **Player crosses area boundary (Mos Eisley → Dune Sea):** transitional sequence — Mos Eisley fades out, new area loads via `map_geometry` push, fades in. ~600ms total. Breadcrumb updates.
- **Tier transition (Tier 1a → Tier 2):** camera zooms out smoothly; layers cross-fade.

### 7.11 Wire data for the map

The map uses both REST and WebSocket:

- **REST `GET /api/map/area/{slug}`** — static geometry for a settled area (rooms, polygons, streets, labels, landmark illustrations). Cached aggressively (changes only when builders edit the area in YAML).
- **REST `GET /api/map/wilderness/{slug}`** — static geometry for a wilderness region (tiles, landmarks, terrain types). Cached.
- **REST `GET /api/map/planet/{slug}`** — planet view data.
- **REST `GET /api/map/galaxy`** — galaxy view data, with current-era faction shading.
- **WebSocket `map_position`** — pushed on every move: `{ x, y, room_id, area_slug, tier_hint }`.
- **WebSocket `map_overlay`** — pushed when overlay state changes: contest state, anomaly spawns, weather events.
- **WebSocket `wilderness_state`** — pushed when in a wilderness region: current tile, sight radius, visible landmarks, visible PCs.

The geometry-once + position-deltas pattern (per CLAUDE_DESIGN_BRIEF.md §6.4) is preserved. The client loads area geometry on area entry, then only consumes position deltas during play in that area.

### 7.12 Mobile note

Mobile work is Phase 3 (per §9). The map's mobile variant is a full-screen takeover with finger-friendly zoom/pan. The protocol stays the same; only the layout adapts.

### 7.13 The map renderer — architecture

The single most important clarification in v1.1: **the map is not a mockup. It is a composition engine that runs in the browser, consuming hand-authored illustration assets and live game state at runtime.** This is qualitatively different from every other panel in §6 — those are designed as static layouts that bind to live data. The map is a *system* that draws differently every frame depending on where the player is, what they can see, who else is around, and what's happening in the world.

This section specifies that system.

#### 7.13.1 The three-layer separation

The renderer architecture is three layers, kept strictly separate:

| Layer | What it is | Who authors it |
|---|---|---|
| **Asset library** | Hand-authored SVG illustrations, style primitives, marker shapes, iconography, palette swatches | Visual designer (Claude Design) — once, evergreen |
| **Composition engine** | The runtime renderer — takes geometry + state + assets + palette, emits SVG, handles zoom/transition/animation | Engineering Claude — once, then maintained |
| **Game data** | Room geometries, landmark positions, terrain tiles, dynamic state (player, NPCs, contests, anomalies, weather) | Builders (YAML) + server engine (live state) |

The renderer's job is to be the **conductor** of these three sources. It does not draw any content of its own. It does not invent illustrations. It does not generate geometry. It assembles.

**Why this matters:** the "looks like block shapes" problem is not a renderer problem; it is an **empty asset library** problem. With no hand-authored illustrations, the renderer falls back to generic style primitives (the `Map_Redesign_v2.html` per-style footprints), which read as schematic shapes. With a rich asset library, the same renderer composes those illustrations onto the same data and produces the WEG-sourcebook-style result.

#### 7.13.2 The asset library

The asset library is the **visual deliverable**. It is what Claude Design produces. It consists of:

**A. Named-landmark illustrations.** Hand-authored SVG illustrations for specific, iconic locations. Each has a stable slug bound to a room or landmark in the world data.

Examples:

```
assets/landmarks/
  cantina_chalmuns.svg          # Chalmun's Cantina — iconic dome + bandstand protrusion
  dock_bay_94.svg               # Docking Bay 94 — circular bay + ship silhouette
  palace_jabba.svg              # Jabba's Palace — iconic mass + entrance arch
  plaza_kerner.svg              # Kerner Plaza
  wreck_lucky_despot.svg        # The Lucky Despot — wrecked star cruiser silhouette
  wreck_dowager_queen.svg       # The Dowager Queen
  station_westport.svg          # The Westport
  pit_sarlacc.svg               # The Sarlacc — Great Pit of Carkoon
  outpost_anchorhead.svg        # Anchorhead settlement
  station_tosche.svg            # Tosche Station
```

Each illustration is **small** (5–15 KB SVG), uses only the CSS variable palette, and is authored for composition at a known cell size (e.g., the building footprint cell on the map).

**B. Style primitives.** The fallback layer. When a room doesn't have a bespoke illustration, the renderer uses one of these per the room's `style` field (already in the schema, already exercised by `Map_Redesign_v2.html`):

```
assets/style/
  style_dock.svg                # Notched bay door (generic)
  style_cantina.svg             # Pill with peaked overhang
  style_civic.svg               # Rounded rect with pediment
  style_gate.svg                # Chevron
  style_hutt.svg                # Doubled border rect
  style_vendor.svg              # Awning rect
  style_market.svg              # Awning row
  style_landmark.svg            # Hexagon (generic landmark)
  style_residential.svg         # Plain rounded rect
  style_industrial.svg          # Sharp-edged rect with vent glyphs
  style_warehouse.svg           # Long rect with bay doors
  style_default.svg             # Plain rect (true fallback)
```

The style primitive library is **finite and bounded** — maybe 15–25 styles total. The named-landmark library grows over time as builders author more iconic locations.

**C. Marker shapes.** Per §7.9 — player chevron, PC dot, NPC variants by attitude, anomaly markers by tier, region anchor glyph, vendor/mission/quest icons.

```
assets/markers/
  marker_player.svg
  marker_pc.svg
  marker_npc_friendly.svg
  marker_npc_hostile.svg
  marker_npc_neutral.svg
  marker_vendor.svg
  marker_mission.svg
  marker_bounty.svg
  marker_objective.svg
  marker_anomaly_t1.svg
  marker_anomaly_t2.svg
  marker_anomaly_t3.svg
  marker_region_anchor.svg
```

**D. Iconography.** Service icons, status auras, attribute glyphs, faction sigils. Used across the map *and* across other panels (the HUD, the holocron, the comms pane).

```
assets/icons/
  service_vendor.svg
  service_trainer.svg
  service_cantina.svg
  service_medical.svg
  service_dock.svg
  service_crafting.svg
  service_mission_board.svg
  service_mail.svg
  status_stunned.svg
  status_wounded.svg
  status_in_cover.svg
  status_aim_held.svg
  status_force_focused.svg
  attr_dex.svg
  attr_kno.svg
  ...
  faction_republic.svg
  faction_cis.svg
  faction_hutt.svg
  faction_jedi.svg
  faction_bounty_guild.svg
  faction_mandalorian.svg
  faction_falleen.svg
  faction_black_sun.svg
```

**E. Palette swatches.** Per-planet JSON/CSS files declaring the full palette derived from the anchors in §4.2. The renderer reads the active planet's palette on area entry and substitutes CSS variables before draw.

```
assets/palettes/
  palette_tatooine.css
  palette_coruscant_upper.css
  palette_coruscant_underworld.css
  palette_nar_shaddaa.css
  palette_kamino.css
  palette_geonosis.css
  palette_dantooine.css
  palette_naboo.css
  palette_kashyyyk.css
  palette_mandalore.css
```

**F. Atmospheric overlay assets.** Reusable overlay SVGs/CSS patterns for weather, time-of-day, faction territory shading.

```
assets/overlays/
  overlay_sandstorm.svg
  overlay_rain.svg
  overlay_smog.svg
  overlay_night.svg
  overlay_dusk.svg
  overlay_faction_republic.css
  overlay_faction_cis.css
  overlay_faction_hutt.css
  overlay_contest_active.svg
```

#### 7.13.3 LOD strategy — three variants per named landmark

A named-landmark illustration is **three files**, not one, corresponding to zoom tier visibility:

| Variant | Used at tier | Size | Detail |
|---|---|---|---|
| **Detailed** | Tier 0 (site/interior), Tier 1a (district), Tier 1b (wilderness) | ~10–15 KB | Full hand-drawn illustration with internal detail |
| **Simplified** | Tier 2 (whole city) | ~3–5 KB | Recognizable silhouette, no internal detail |
| **Icon** | Tier 3 (planet) | ~1–2 KB | Minimal glyph, identifiable shape only |

```
assets/landmarks/cantina_chalmuns/
  detailed.svg                  # Tier 0/1: full domed cantina with bandstand protrusion, doors, table-row hint
  simplified.svg                # Tier 2: dome silhouette with one protrusion, no doors
  icon.svg                      # Tier 3: single dome glyph
```

The renderer picks the right variant based on current tier. This is the same idea as map-tile zoom levels in Google Maps, but applied to hand-authored SVG illustrations.

**Why three:** at Tier 0 you can see Chalmun's Cantina filling a screen, so the detail matters; at Tier 2 it's one of dozens of buildings and detail becomes noise; at Tier 3 it's a pin on a planet and only the *silhouette identity* survives. Authoring three variants is more work than one but produces a coherent zoom experience.

#### 7.13.4 The composition engine — what the renderer does

In pseudocode, the renderer's per-frame logic:

```
function render(area_geometry, dynamic_state, tier, palette):
    apply_palette(palette)  # substitute CSS variables for the active planet
    
    layers = []
    
    if tier <= 2:
        layers.append(atmosphere_layer(planet))
        layers.append(tile_substrate(area_geometry.terrain))
    
    if tier in (1a, 2):
        layers.append(district_fills(area_geometry.districts))
        layers.append(security_tint(area_geometry.rooms))
    
    if tier == 1b:
        layers.append(terrain_tiles(area_geometry.tiles))
    
    if tier in (1a, 1b, 2):
        layers.append(faction_territory(dynamic_state.factions))
    
    if tier in (0, 1a):
        layers.append(street_paths(area_geometry.streets))
    
    if tier in (0, 1a, 2):
        layers.append(building_footprints(area_geometry.rooms, lod=lod_for(tier)))
        # ↑ This is the key step. For each room:
        #   - If room.landmark_slug is set → use named-landmark illustration at the LOD for this tier
        #   - Else → use style primitive for room.style
        #   - Else → use generic rect (style_default)
    
    if tier == 1a:
        layers.append(street_furniture(area_geometry.ambient_glyphs))
    
    if tier in (1a, 1b):
        layers.append(weather_overlay(dynamic_state.weather))
    
    if tier == 1b:
        layers.append(anomaly_markers(dynamic_state.anomalies))
        layers.append(contest_overlay(dynamic_state.contest))
    
    if tier <= 2:
        layers.append(landmark_pins(area_geometry.landmarks, lod=icon))
        layers.append(labels(area_geometry.labels, visibility_for(tier)))
    
    layers.append(npc_markers(dynamic_state.npcs))
    layers.append(pc_markers(dynamic_state.other_pcs))
    layers.append(player_marker(dynamic_state.player))  # always on top
    
    return compose_svg(layers)
```

This runs on a state change (server pushes a `map_position` or `map_overlay` message) or a tier change (user zooms). Not on a per-frame timer.

#### 7.13.5 Dynamic overlay system

Overlays are dynamic layers driven by live game state, applied on top of the static geometry. Each overlay has its own activation rule:

| Overlay | Trigger | Tier visibility |
|---|---|---|
| Atmosphere | Always (planet-keyed) | 0–4c |
| Time of day | Server clock + planet rotation | 0–3 |
| Weather (sandstorm, rain, smog) | Active weather event | 1a, 1b |
| Faction territory | Region ownership state | 1b, 3, 4c |
| Security tint | Room/region security tier | 0, 1a, 2 |
| Contest banner | Active wilderness contest | 1b |
| Anomaly markers | Live anomalies | 1b |
| Region Anchor pulse | Culminating-fight window | 1b |
| Fog of war | Wilderness sight radius | 1b |
| Travel route | Player using `travel` command | 1b |
| World event banner | Director AI major event | All (chrome) |

Overlays are added or removed as state changes — the renderer recomposes when `dynamic_state` changes. Most overlays are lightweight (a CSS pattern, a single SVG element, or a subtle filter). The world event banner lives outside the map content area, in the chrome.

#### 7.13.6 Transitions and animation

All animation is CSS `transform`, `opacity`, or `color` only — no per-frame JS loops, no `filter:` in hot paths.

| Transition | Mechanism | Duration |
|---|---|---|
| Player marker move | CSS transform lerp | 150 ms ease-out |
| Tier zoom (in or out) | CSS scale + cross-fade of layer visibility | 400 ms ease-in-out |
| Area boundary cross | Fade out, geometry load via REST, fade in | 600 ms total |
| Marker pulse (active player, anomaly) | CSS keyframe animation | infinite, low frequency |
| Anomaly spawn alert | CSS scale + opacity from 0 to 1 with bounce | 800 ms |
| Region Anchor spawn (dramatic) | Larger reveal animation, screen-flash | 1200 ms one-shot |
| Contest accumulation tick | Number scrub animation | 300 ms |
| Weather transition (clear → sandstorm) | Cross-fade overlay opacity | 2000 ms |

Performance budget per frame is 16ms (60fps target per CLAUDE_DESIGN_BRIEF.md). Layer count caps:

- Tier 0: ≤ 50 SVG elements visible.
- Tier 1a: ≤ 200 SVG elements.
- Tier 1b: ≤ 400 (wilderness has more tiles).
- Tier 2: ≤ 300.
- Tier 3+: ≤ 100 (mostly simplified shapes).

If a tier's element count exceeds the cap, the renderer drops layers — labels first, then street furniture, then non-essential overlays. The player marker is never dropped.

#### 7.13.7 Asset binding — how illustrations attach to game data

Every room in the world data has a `style` field today (per `Map_Redesign_v2.html`). v1.1 of this doc proposes one new optional field on rooms: `landmark_slug`. When set, the renderer uses the named-landmark illustration at that slug instead of the style primitive.

```yaml
# In data/worlds/clone_wars/cities/mos_eisley.yaml
rooms:
  - slug: cantina_chalmuns_main_floor
    name: "Chalmun's Cantina — Main Floor"
    map_x: 6
    map_y: 8
    style: cantina            # fallback if landmark_slug unset
    landmark_slug: cantina_chalmuns   # NEW — binds to assets/landmarks/cantina_chalmuns/
    
  - slug: dock_bay_94
    name: "Docking Bay 94"
    map_x: 4
    map_y: 12
    style: dock
    landmark_slug: dock_bay_94
    
  - slug: market_stall_jawa
    name: "Jawa Trinket Stall"
    map_x: 7
    map_y: 7
    style: vendor             # no landmark_slug — renders as style primitive
```

This means the *world data* (which builders maintain) declares "this room is Chalmun's Cantina" by binding to a slug, and the *asset library* (which the designer maintains) provides the illustration at that slug. The two are decoupled — builders can author rooms before illustrations exist (graceful degradation to style primitive), and designers can author illustrations before rooms exist (the slug is just unused).

#### 7.13.8 Wilderness rendering specifics

Tier 1b (wilderness region) uses a different composition pipeline than Tier 1a (city district), because the underlying data is a tile grid not a room graph. Specifics:

- **Tile painter.** Each terrain type (dune, canyon, oasis, rocky outcrop, vaporator field) has a *painterly tile asset* — not a single SVG per tile, but a small library of variants. The renderer picks variants pseudo-randomly per tile coordinate (deterministic from `(x, y, region_seed)` so the same tile always looks the same) to avoid visible repetition. ~3–5 variants per terrain type is enough.
- **Tile bleeds.** Adjacent tiles of the same terrain visually bleed into each other; transitions between terrains use a soft alpha gradient or a hand-authored transition tile (canyon-to-dune, oasis-to-dune, etc.). Eliminates the "grid lines" look.
- **Landmark layer.** Wilderness landmarks (Tusken camps, abandoned mines, moisture farms, oases with homesteads) have their own bespoke illustrations, same LOD system as city landmarks.
- **Fog of war.** Tiles beyond the player's terrain-specific sight radius are dimmed (~40% opacity); never fully hidden — the player can still see the *shape* of the region.
- **Anomaly placement.** Anomaly markers are placed at their (x, y) coords and pulse. The Tier 3 (world boss) anomaly gets a dramatic full-screen flash animation on spawn.
- **Contest overlay.** When a contest is active, a band of glowing color follows the contested landmark, with the countdown timer floating above it. During the 4-hour culminating-fight window, the Region Anchor's location pulses dramatically.

#### 7.13.9 Implementation phasing within Phase 3

Phase 3 of the roadmap (§9) breaks into renderer-focused sub-drops:

- **Drop 3.0 — Renderer scaffolding.** Build the composition engine skeleton. No assets yet; renders the existing `Map_Redesign_v2.html` style-primitive output through the new pipeline as proof. Validates that the engine can swap palette, switch tiers, and load geometry on area entry. Visually identical to today; architecturally different.
- **Drop 3.1 — Landmark binding + first 5 illustrations.** Add the `landmark_slug` field to room schema. Wire renderer to prefer named-landmark assets. Ship with 5 hand-authored Mos Eisley landmarks (Chalmun's Cantina, Docking Bay 94, Jabba's Palace, Kerner Plaza, the Lucky Despot). Mos Eisley already looks dramatically better than v2 mockup at this drop.
- **Drop 3.2 — Tier 0 site/interior + Chalmun's interior asset.** Renders inside-the-cantina view with hand-authored interior plan.
- **Drop 3.3 — Tier 2 whole-city + LOD simplified variants.** Adds the simplified-LOD assets for each Tier 1a landmark and the Tier 2 composition rules.
- **Drop 3.4 — Wilderness Tier 1b.** Tile painter, terrain variants, fog of war. Dune Sea as first authored region.
- **Drop 3.5 — Tier 3 planet view + icon-LOD assets.**
- **Drop 3.6 — Dynamic overlay system.** Weather, faction territory, security tinting, contest banners.
- **Drop 3.7 — Anomaly markers + Region Anchor + world boss spawn dramatics.**
- **Drop 3.8 — Tier 4abc system/sector/galaxy.**
- **Drop 3.9 — Tier transitions + smooth zoom + area-boundary cross-fade.**
- **Drop 3.10 — Builder tooling.** A web-based geometry editor for builders to position rooms, draw streets, place landmarks. (Per CLAUDE_DESIGN_BRIEF.md, this is post-pilot work — could slip to Phase 5.)

The asset library grows continuously, parallel to engineering work. Brian (or Claude Design) can author landmark illustrations whenever — they slot into the renderer the moment a builder binds a `landmark_slug` to a room.

#### 7.13.10 The economic argument for the asset-library approach

A blunt accounting of why this architecture is worth the up-front structure:

- **Hand-authoring every map view** as a static mockup means re-authoring whenever a room is added, a contest fires, an anomaly spawns, or weather changes. The map has thousands of distinct possible states. No designer can keep up.
- **Hand-authoring a single mockup** that "represents" the map (the current approach Claude Design seems to be defaulting to) produces one frame and zero ability to extend. The block-shapes outcome is the natural result of asking "produce the map" when what's wanted is "produce the assets that compose into the map."
- **Hand-authoring an asset library** of ~30–60 named-landmark illustrations + ~15–25 style primitives + ~30 markers/icons + ~10 palettes is a bounded one-time effort. The library grows organically as builders add iconic locations. The renderer composes those assets into infinitely many map states automatically.

This is the same architecture as a tile-based 2D game engine (think classic isometric RPGs) — the artist makes the tiles, the engine composes them. Brian's instinct that "the renderer should do more than Design is created to display" is exactly right: the renderer is the system; Design supplies its source material.

---

## 8. Diegetic flourishes — atmosphere without breaking immersion

These are the touches that elevate the client from "functional UI" to "Star Wars game." None are required for functionality; all are recommended for polish. Designer can choose which to elaborate.

- **Force Point spend animation.** When the player spends an FP, the entire HUD gets a brief mystic shimmer — a soft cyan-to-white pulse, ~600ms, no functional disruption.
- **Wound state ambient effect.** At Wounded Twice or worse, the screen edges get a subtle red vignette. At Mortally Wounded, the vignette pulses with the character's "heartbeat."
- **Security zone framing.** The terminal pane's outer border subtly tints with the current room's security tier — soft green in SECURED, amber in CONTESTED, red in LAWLESS.
- **Dark Side ambient.** A character with DSP > 0 gets a slight chromatic shift in their portrait, deepening per DSP point.
- **Holocron crystal idle.** The holocron sidebar button (when closed) has a slow rotation/glow animation, like a Jedi holocron sitting on a desk.
- **Companion droid icon.** A small protocol-droid or astromech icon in a corner; clicking it triggers a contextual hint (powered by Director AI). Cosmetic, not required.
- **Twin sun position indicator on Tatooine.** When on Tatooine, a small twin-sun indicator shows the current in-game time of day — both suns rising, both at zenith (oppressive heat indicator), one setting, etc. Per-planet equivalents on other planets.
- **News ticker chrome.** The Holonet ticker has a subtle TV-static effect on transitions, faint scanlines, occasional static crackle on big stories.
- **Skill check "tick."** When a skill check resolves, a single subtle tick sound (or visual flash) for successes; a softer thud for failures. Optional audio is future-scope.
- **Datapad mode** (per §6.12) — the toggleable diegetic framing.
- **Loading states framed as in-fiction.** When the holocron is loading an entry, show "ACCESSING ARCHIVE…" with progress glyphs, not a generic spinner. When the map is loading geometry on area change, show "PLOTTING COORDINATES…".
- **Ambient mood theming** (already designed in `ground_ux_overhaul_design_v1.md` §5.4) — zone-keyed CSS custom properties shift the palette subtly based on the room's mood key (cantina = warm amber-orange, spaceport = cool grey-blue, market = bright variegated, wilderness = harsh).

---

## 9. Implementation roadmap

This is a multi-phase buildout, sequenced to deliver value incrementally without committing to the full vision before validating each piece.

### Phase 0 — Protocol audit and consolidation (~1 session)

Goal: ground truth at HEAD.

- Audit every message type and REST endpoint currently in the codebase.
- Update §5.7, §5.8, §5.9 above with verified current state.
- Document each shipped message's payload schema in this doc (or link to the system-specific doc that owns it).
- Identify drift between this doc and HEAD; flag for fixing.

No code ships. The doc becomes authoritative.

### Phase 1 — Foundation drops (~3–4 sessions)

Goal: protocol substrate for the rich client.

- **Drop 1.1** — `session_bootstrap` message (full snapshot on connect).
- **Drop 1.2** — Subscription model (`subscribe` / `unsubscribe`).
- **Drop 1.3** — Versioning (`schema_version` on every message; server supports last N versions).
- **Drop 1.4** — `/api/protocol/schema` endpoint.
- **Drop 1.5** — Telnet parity check against §5.7 horizon items; backfill any missing Telnet commands.

These enable everything that follows. Low player-visible value individually; high enabling value.

### Phase 2 — Panel build-out (~6–10 sessions, parallelizable)

Goal: rich panels per §6, served from the protocol foundation.

- **Drop 2.1** — Persistent character HUD (§6.1) wired to extended `hud_update`.
- **Drop 2.2** — Room context panel (§6.2) with persistent description, services, mini-map.
- **Drop 2.3** — Combat console with dice transparency (§6.3) wired to `combat_resolution_event`.
- **Drop 2.4** — Inventory paper doll (§6.4) wired to `inventory_change` + `equipment_change`.
- **Drop 2.5** — Tabbed comms (§6.5).
- **Drop 2.6** — Skill-check ribbon (§6.7).
- **Drop 2.7** — Quest / progression tracker (§6.9) with cooldown wheels.
- **Drop 2.8** — Faction reputation radial (§6.11).
- **Drop 2.9** — News / Director AI panel (§6.10).
- **Drop 2.10** — Holocron (§6.8) — biggest single drop; new content pipeline.

Each is independent and can ship in any order after Phase 1.

### Phase 3 — Map system (~8–12 sessions)

Goal: the holocarta per §7.

- **Drop 3.1** — Tier 1a city district renderer (extension of `Map_Redesign_v2.html` mockup to production).
- **Drop 3.2** — Tier 0 site / interior renderer.
- **Drop 3.3** — Tier 2 whole-city renderer.
- **Drop 3.4** — Tier 1b wilderness region renderer (new — biggest visual variant).
- **Drop 3.5** — Tier 3 planet renderer.
- **Drop 3.6** — Tier 4a/b/c system / sector / galaxy renderers.
- **Drop 3.7** — Named-landmark illustration pipeline (asset authoring tooling + per-landmark SVG library).
- **Drop 3.8** — Map overlay system (contests, anomalies, weather, territory).
- **Drop 3.9** — Tier transitions and smooth zoom.
- **Drop 3.10** — Wilderness `wilderness_state` push (terrain tile, sight radius, visible entities).

### Phase 4 — Diegetic polish (~2–3 sessions)

Goal: §8 flourishes. Low priority but high impact on feel.

### Phase 5 — Mobile (~3–5 sessions)

Goal: responsive layout for tablet and phone.

- CSS breakpoints for narrow viewports.
- Map full-screen takeover with finger gestures.
- Mobile-specific tab bar for switching between panels.
- Touch-optimized interaction targets.

**Phasing principle:** Phase 0 and Phase 1 are sequenced and gate everything. Phase 2 drops are independent and can ship in any order, prioritized by player-visible impact. Phase 3 is the largest investment and can run in parallel with Phase 2 (different files, different sessions). Phase 4 is opportunistic polish. Phase 5 is the mobile expansion gate.

---

## 10. Claude Design handoff appendix

This appendix is the **standalone packet you can hand to Claude Design** to mock the rich web client. It pre-empts the "Claude Design gets confused about game mechanics" failure mode by being explicit about what is and is not the case in this game.

### 10.1 Read this first (the irreducible primer)

If you are Claude Design and have not read the rest of this document, read this list before sketching anything:

1. **The game is SW_MUSH.** It is a Star Wars MUD (multi-user text adventure) with a web client. The web client we are designing is a rich enrichment layer on top of the text game. **Text is canonical.** The web cannot show information the text doesn't show; it can only *show it better*.
2. **The era is the Clone Wars (~20 BBY).** This is the prequel-trilogy era. Republic vs. CIS. Anakin is a Knight. Jedi are not yet hunted. Order 66 has not happened. **NO Empire, NO Rebellion, NO stormtroopers (in their OT form), NO Vader, NO Death Star.** If you find yourself referencing any of those, you are referencing the wrong era — stop and re-orient.
3. **The dice system is WEG D6.** Read §3.1 before drawing any dice. Specifically: notation like `3D+2` means three six-sided dice plus 2 pips (where a pip = +1, three pips = +1D). One die per roll is the Wild Die, visually distinct (green), which explodes on a 6 and can complicate on a 1. **Never draw four identical dice for `4D` — one must be the Wild Die.**
4. **There are exactly six attributes** in the order Dexterity, Knowledge, Mechanical, Perception, Strength, Technical. Six. In that order. No seventh attribute. No reordering.
5. **Wound state is a discrete ladder, not an HP bar.** Six tiers (Healthy → Stunned → Wounded → Wounded Twice → Incapacitated → Mortally Wounded → Killed). The visual is a humanoid figure with tier indicators. **No percentage HP bar.**
6. **Force Points, Dark Side Points, and Character Points are integer counters, not bars.** Force Points are precious (1–5 typical). Dark Side Points are usually 0; non-zero is significant. Character Points are XP-like (5–50+ range).
7. **Range bands are four discrete bands** (Point-Blank / Short / Medium / Long), per-weapon thresholds. Show as a horizontal strip, not a slider.
8. **Security tiers are three: secured (green) / contested (yellow) / lawless (red).** These are explicit game states with mechanical effects, not just flavor.
9. **The visual language is terminal-meets-datapad.** Dark backgrounds, IBM Plex Mono / Plex Sans / Orbitron, amber + cyan + red accents. Per-planet palette overlays. Subtle CRT-flicker and scan-lines acceptable on chrome bezel only; not on reading surfaces.
10. **The reference for "rich" maps is the hand-drawn WEG sourcebook material.** Iconographic, atmospheric, drawn-not-diagrammed. See `Map_Redesign_v2.html` for the current approved direction; push past it toward named-landmark illustrations.

### 10.2 Glossary of in-game terms you will encounter

Alphabetical. If you encounter a term not on this list while reading, ask before sketching.

- **Astrogation** — Mechanical skill for plotting hyperspace jumps.
- **Attack of the Clones, Revenge of the Sith** — the prequel films; the right era reference.
- **B1 / B2 battle droid** — CIS infantry. B1 is thin, blocky-headed. B2 is bulkier "super battle droid."
- **Bacta** — healing fluid. Bacta tanks and bacta patches restore wound state.
- **Beskar** — Mandalorian armor material.
- **Blaster** — energy pistol/rifle. The standard Star Wars firearm.
- **CIS** — Confederacy of Independent Systems. The separatists. The "other side" of the Clone Wars.
- **Character Point (CP)** — XP-equivalent. See §3.7.
- **Clone trooper** — Republic infantry. Successor to the Republic militia, predecessor to the Imperial stormtrooper. White armor with phase-specific styling.
- **Comlink** — communicator. Wrist or handheld.
- **Coruscant** — galactic capital. Skyscraper city-planet. Senate sits here.
- **Coruscant Underworld** — the lower levels of Coruscant. Dim, dangerous, crowded.
- **Credits** — currency. Universal.
- **Dantooine** — agricultural planet. Hosts the Jedi Village in our content.
- **Dark Side Point (DSP)** — see §3.7.
- **Datapad** — handheld computing device. Tablet-equivalent.
- **Difficulty** — number the player must beat with their dice roll. See §3.4.
- **Director AI** — our in-game GM AI. Generates events, faction movements, ambient flavor.
- **Dodge** — Dexterity skill, opposed roll against incoming attacks.
- **Force Point (FP)** — see §3.7.
- **Force-sensitive** — capable of using the Force. Rare. Most PCs are not.
- **Geonosis** — desert planet. CIS-aligned in our era. Rust-red oxide aesthetic.
- **Holocron** — Jedi data crystal. Our lore browser is themed as one.
- **Holonet** — galactic news network. Our news ticker is themed as it.
- **Hutt Cartel** — crime syndicate led by Hutts. Officially neutral in the war.
- **Hyperdrive** — FTL drive. Different ratings (Class 1 fast, Class 12 slow).
- **Hyperlane** — established hyperspace route. Visible on galaxy tier of map.
- **Jedi** — Force-using order, allied with Republic. Wear robes. Wield lightsabers.
- **Kamino** — water/storm planet. Cloning facilities. Cool teal palette.
- **Knight (Jedi Knight)** — Jedi rank between Padawan and Master. Anakin's rank in this era.
- **Krayt dragon** — giant Tatooine predator. World boss in wilderness.
- **Lightsaber** — Jedi/Sith weapon. Plasma blade.
- **Mandalore / Mandalorian** — warrior culture. Beskar armor. T-visor helmets.
- **Mos Eisley** — Tatooine spaceport. Our pilot city.
- **Nar Shaddaa** — "Smuggler's Moon." Hutt-controlled. Neon-and-rust aesthetic.
- **Naboo** — beautiful planet, lakes and stone architecture. Padmé's homeworld.
- **NPC** — non-player character. Server-controlled.
- **Order 66** — the future event where clones turn on Jedi. **Has not happened yet** in our era.
- **PC** — player character. Player-controlled.
- **Padawan** — Jedi apprentice. Wears a braid.
- **Pip** — `+1` to a dice roll. Three pips = +1D. See §3.1.
- **Republic (Galactic Republic)** — the "good guys" side of the Clone Wars. Pre-Empire.
- **Sabacc** — card game. Implemented in-game with full rules.
- **Sarlacc** — pit-monster on Tatooine. World boss landmark.
- **Sith** — dark-side counterpart to Jedi. Hidden in this era (Dooku and Sidious).
- **Soak** — damage reduction (Strength + armor). See §3.6.
- **Specialization** — narrower skill within a skill, with bonus dice. See §3.3.
- **Stormtrooper** — does NOT exist yet in this era. Clones are the Republic infantry. Do not draw white-shell GCW stormtroopers.
- **Tatooine** — desert world. Twin suns. Mos Eisley is here. Sand-bleached amber aesthetic.
- **Telnet** — the text-only client. Canonical.
- **TIE fighter** — does NOT exist yet in this era. Republic uses gunships and ARC-170 fighters; CIS uses vulture droids (variable-wing droid starfighters) and tri-fighters.
- **Vibroblade / vibroknife** — melee weapon with vibrating edge.
- **WEG D6** — West End Games D6 system. Our ruleset. See §3.
- **Wild Die** — the special die in every roll. Green. Explodes on 6, complicates on 1.
- **Wookiee** — large furry humanoid species. Strong, loyal, native to Kashyyyk.
- **Yoda, Mace Windu, Obi-Wan, Anakin, Ahsoka, Dooku, Grievous, Ventress** — major canonical figures of the era. Reference them, don't quote them, don't render their exact likeness.

### 10.3 Sample data for mockups

When mocking, use this realistic sample data instead of inventing values. Designer mockups that show realistic data are easier to evaluate.

**Sample character — "Tey Voss" (smuggler PC):**

- Species: Human
- Era: Clone Wars
- Faction reputation: Hutts Friendly, Republic Neutral, CIS Unfriendly, Bounty Guild Friendly
- Attributes: DEX 3D+2, KNO 3D, MEC 4D+1, PER 3D+1, STR 2D+2, TEC 3D
- Skills (selected): Blaster 5D+2 (Heavy Blaster Pistol 6D+1), Dodge 4D+2, Astrogation 5D, Space Transports 5D+2, Bargain 4D+2, Streetwise 5D
- Wound state: Wounded
- Force Points: 2
- Dark Side Points: 0
- Character Points: 18
- Credits: 4,250
- Currently at: Docking Bay 94, Mos Eisley, Tatooine
- Equipped: Heavy blaster pistol (5D damage, PB 3-5/S 6-10/M 11-25/L 26-50m), padded armor (+1D physical, +1D energy soak), comlink, datapad
- Active status: In Cover, Aim Held
- Active jobs: Smuggling run to Nar Shaddaa (2/4 stops complete), Hutt Cartel bounty on Vex Drago (3 days remaining)

**Sample combat round mockup data:**

- Round 3, Declaration phase complete, Resolution phase active
- Combatants: Tey Voss (PC, init 14, declared "Aim then shoot at B1 #1"), Marek Tan (PC, init 11, "Take cover, shoot at B1 #2"), B1 battle droid #1 (NPC hostile, init 9, "Shoot at Tey"), B1 battle droid #2 (NPC hostile, init 8, "Shoot at Marek")
- Range strip: Tey & Marek at Short range, B1s at Medium range
- Tey's roll resolving: Heavy Blaster Pistol skill 6D+1, +1D from Aim, −1D from Wounded = effective 6D+1. Wild Die rolled (green): 6 → explode → 4. Other dice: 4, 3, 5, 5, 2. Total: 6+4+4+3+5+5+2 = 29. (+1 pip = 30.)
- Difficulty: 12 (base 10 Easy, +2 Medium range). Beaten by margin 18 — "spectacular hit."
- Damage: 5D damage roll, 4+3+3+5+(WD 6 → explode → 2) = 23. Soak: B1 has 2D+1 soak, rolls 3+5+1+1pip = 10. Margin 13 → "Severely Wounded" (combat droids don't follow PC wound ladder; they have 4 hit states: Damaged / Heavily Damaged / Disabled / Destroyed). B1 #1 now Disabled.

**Sample inventory:**

```
Equipped:
  Main hand: Heavy Blaster Pistol [5D, PB 3-5/S 6-10/M 11-25/L 26-50m, 50 charges]
  Belt: Vibroknife [STR+1D damage], 2× Stim packs
  Chest: Padded Armor [+1D physical, +1D energy]
  Comlink: Standard
  Wrist: Datapad

Carried (pack):
  Med-kit (3 uses)
  Hydration pouch (75% full)
  Restraining bolt (1)
  Hyperspace fuel canister (full)
  Credit chits (4,250 cr)
  Sealed Imperial dispatch (quest item)
  Spare power pack × 3
  Glow-rod
  Survival rations (4 days)
```

**Sample news ticker:**

```
HOLONET ▸ BREAKING: Republic gunship squadron arrives in Tatooine system, declares "anti-piracy operation"...
HOLONET ▸ Hutt Cartel statement: "Coronet Vintner's Guild contract dispute resolved peacefully"...
HOLONET ▸ Jedi General Plo Koon confirmed wounded in action at Anaxes...
HOLONET ▸ CIS sympathizers stage protest at Bestine spaceport — Imperial Authority responds...
[ANOMALY DETECTED] ▸ Krayt dragon emergence in Western Dune Sea sector 7, hunters dispatched...
```

**Sample holocron entry — "Hutt Cartel":**

```
HUTT CARTEL
Faction · Criminal Organization · Active (Clone Wars era)

The Hutt Cartel is the loose alliance of Hutt crime lords that dominates the Outer Rim
underworld. Operating from Nal Hutta and its moon Nar Shaddaa, the Cartel controls
spice trafficking, slave trading, bounty issuance, gambling syndicates, and protection
rackets across hundreds of worlds.

In the Clone Wars era, the Cartel maintains a public posture of neutrality between the
Republic and the CIS, while privately profiting from arms-running to both sides. The
Hutt clan known as the Desilijic — currently led by Jabba — controls the most lucrative
operations.

Player characters may earn standing with the Cartel through smuggling missions, bounty
contracts, and protection deals. Cartel-friendly PCs gain access to Hutt-only vendors,
the bounty board on Nar Shaddaa, and discount rates with Hutt-aligned ship outfitters.

Your character knows: [Tatooine operations · Mos Eisley contacts · standard Hutt protocol]
Your character has not learned: [Nal Hutta internal politics · Desilijic family tree]

Related: Tatooine · Nar Shaddaa · Jabba the Hutt · Spice · Bounty Hunters' Guild
```

### 10.4 What to mock — priority order

If Claude Design has limited time, mock these first:

**Priority 1 (must have for first review):**
1. The persistent character HUD (§6.1) in three states: healthy, mid-combat, critical.
2. The combat console (§6.3) with full dice transparency for one realistic roll.
3. The room context panel (§6.2) for Mos Eisley Docking Bay 94.
4. The Tier 1a city district map for Mos Eisley spaceport, extending `Map_Redesign_v2.html` with named-landmark illustrations.

**Priority 2 (second pass):**
5. The Tier 1b wilderness region map for the Dune Sea.
6. The inventory paper doll (§6.4) for the smuggler sample PC.
7. The tabbed comms pane (§6.5) in active-scene state.
8. The holocron entry view (§6.8) for the "Hutt Cartel" sample.

**Priority 3 (third pass):**
9. The Tier 3 Tatooine planet view.
10. The faction reputation radial (§6.11).
11. The quest tracker with cooldown wheels (§6.9).
12. The news ticker and expanded news pane (§6.10).
13. Datapad-mode treatment (§6.12) for the right panel.

**Priority 4 (final pass, polish):**
14. Tier 2 whole-city view.
15. Tier 0 site/interior view (Chalmun's Cantina interior).
16. Tier 4abc system/sector/galaxy views.
17. Diegetic flourish reference sheet (§8).

### 10.5 Hard constraints recap

These are not negotiable:

- **Tech:** SVG + CSS transforms. No WebGL. No Canvas-as-renderer except optional tile substrate PNG.
- **Performance:** ≤16ms per frame (60fps target). ≤50KB per area asset (tile raster ≤30KB on top).
- **Animation:** opacity, transform, color only. No `filter:` in hot paths, no `backdrop-filter`.
- **Typography:** IBM Plex Mono (data), IBM Plex Sans (prose), Orbitron (display headers).
- **Palette:** amber `#ffa640`, cyan `#6ee8ff`, red `#ff5a4a`, green `#8fff8f` (for confirmed-secured/success only). Per-planet overlays per §4.2.
- **Y-axis convention:** north = +y in world coords (Y-up). Render layer flips via `scale(1, -1)` on the world group.
- **Mobile is out of scope for this design pass** but should not be precluded by layout choices.

### 10.6 What to NOT design

- The tactical space combat radar (already exists, keep as-is — see existing `static/client.html` space HUD).
- Era-specific Imperial / Rebel UI elements (wrong era).
- Stormtroopers, TIE fighters, Star Destroyers, Vader, etc. (wrong era).
- Site interiors of every building (just enough variety to show the Tier 0 pattern — Chalmun's Cantina is the canonical example).
- Mobile layouts (Phase 5).
- Audio / sound effects (future scope).
- The web-based geometry editor (separate tool, after pilot).

### 10.7 Deliverables expected from Claude Design

1. **Panel mockups** at Priority 1 fidelity (PNG or SVG, treat as final-quality target).
2. **Map mockups** for the five tiers of Mos Eisley + Dune Sea wilderness region.
3. **Marker system sheet** — all marker types from §7.9.
4. **Iconography sheet** — service icons (vendor, trainer, etc.), status aura glyphs (Stunned, In Cover, etc.), faction sigils, attribute glyphs (D K M P S T).
5. **Named-landmark illustration set** — at least 10 iconic Mos Eisley landmarks (Chalmun's Cantina, Docking Bay 94, Jabba's Palace, Kerner Plaza, the Lucky Despot, the Dowager Queen, the Westport, plus 3 of your choice). Reusable across Tier 1a/2/3.
6. **Per-planet palette swatch sheet** — full palettes derived from the anchors in §4.2 for at least Tatooine and one of Coruscant Underworld or Nar Shaddaa.
7. **Transition storyboard** — short visual sequence describing zoom-in tier transition, area-boundary crossing, and contest-anchor spawn alert.
8. **Component spec document** — for the developer handoff, list SVG asset specs, color hex values, font sizes/weights, animation timings, CSS transform conventions.
9. **Datapad-mode reference** — sketch of the diegetic framing.

### 10.8 If you have questions

Refer to this document's sections first:

- Game mechanics questions: §3 (the primer).
- Aesthetic / palette questions: §4 (aesthetic anchors) and §10.5 (constraints).
- Map / geometry / tier questions: §7 (map deep dive), especially §7.13 (renderer architecture and asset-library framing).
- Specific panel questions: §6 (panel catalog).
- "What does X mean?" — §10.2 (glossary).

If a question hinges on a system not covered here, refer to the cited system-specific design doc. If a question still isn't answered, raise it before sketching.

### 10.9 The Claude Design re-brief (read this if v1.0 mockups looked like block shapes)

If your first-pass map mockups read as schematic — block shapes, generic markers, "looks like what's there now" — the cause is almost certainly a framing problem, not a skill problem. The map is not a mockup you produce; it is a runtime composition engine that consumes assets *you* produce. This section is the explicit re-brief.

**What you are producing — the asset library, NOT the map itself.**

Read §7.13 (Map renderer architecture) in full before continuing. The short version: the map renderer (built by engineering Claude in Phase 3) takes hand-authored illustration assets, generic style primitives, marker shapes, iconography, palette swatches, and atmospheric overlays — and composes them dynamically onto live game state. Your job is to author those assets. The map, in production, is the renderer composing your library onto the player's current situation. Each individual frame of the map is dynamic; the *library* is static.

This means:

- You do **not** produce "the map of Mos Eisley" as a single artwork. Mos Eisley has dozens of distinct possible map states (player at the spaceport vs the cantina vs the outskirts; day vs night; sandstorm active vs clear; Republic patrol present vs absent; contest active in the connected Dune Sea region vs not).
- You **do** produce: (a) the named-landmark illustrations Mos Eisley contains, (b) the marker types the renderer will draw, (c) the iconography it will use, (d) the palette swatches, (e) one or two example frame mockups showing what the renderer's output looks like when composing your library on real data.
- The example frame mockups are *target images*, not the system. They illustrate "if you fed the renderer this player position with these landmarks visible at this tier in this weather, this is what it should look like." A small number of well-composed example frames (~3) is more useful than dozens of variant mockups.

**The visual sensibility target — drawn, not diagrammed.**

The reference target is the hand-drawn cartography in the WEG sourcebooks already in the project. Two specific pages to study before authoring any illustration:

- ***Galaxy Guide 7: Mos Eisley*, page 13** — the Tatooine regional map. Dune Sea, Jundland Wastes, named arrowed routes ("To Fort Tusken," "To Jabba's Palace"). Hand-drawn, atmospheric, alive. This is the Tier 3 (planet) reference.
- ***Galaxy Guide 7: Mos Eisley*, page 53** — Chalmun's Cantina floor plan. Individually drawn tables, the curved bar, the bandstand, the back hallway, numbered points of interest. This is the Tier 0 (interior) reference, *and* the benchmark for what "named-landmark illustration" means at any tier.

The Imperial Sourcebook's cross-section spreads (the Tierfon Rebel Outpost multi-page spread, the Imperial garrison Levels 1–7) demonstrate the same drafting sensibility for interiors — labeled, iconographic, drawn.

If your output looks like the WEG sourcebook art *adapted to our terminal-datapad palette* (amber/cyan/red on dark backgrounds, IBM Plex typography, subtle scan-lines), we're winning. If it looks like Google Maps, Apple Maps, a schematic node graph, a flat-design illustration, or a generic top-down game UI, we're losing.

**The asset library — concrete deliverables.**

For the Mos Eisley + Dune Sea pilot, the asset library you produce:

| Category | Count | Notes |
|---|---|---|
| Named-landmark illustrations (city) | ~10–15 | Each at three LOD variants (detailed / simplified / icon) — so ~30–45 SVG files total. Mos Eisley list in §10.4 Priority 4. |
| Named-landmark illustrations (wilderness) | ~5–8 | Dune Sea landmarks: Tusken camps, the abandoned Krayt Skeleton, Anchorhead approach, Jabba's Palace approach, the Pit of Carkoon, etc. |
| Style primitives | ~15–25 | Per §7.13.2.B. Many already implied by `Map_Redesign_v2.html` per-style footprints — refine those, add residential/industrial/warehouse. |
| Wilderness terrain tile painters | ~3–5 variants × ~6 terrains = ~20 files | Painterly small tiles for dune, canyon, oasis, rocky outcrop, vaporator field, etc. |
| Marker shapes | ~13 | Per §7.9 table. |
| Iconography | ~30–40 | Services, status auras, attribute glyphs, faction sigils per §7.13.2.D. |
| Palette swatch files | 2 minimum | Tatooine + one contrast planet (recommend Coruscant Underworld or Nar Shaddaa). |
| Atmospheric overlay assets | ~8 | Sandstorm, rain, smog, night, dusk, faction territory shadings, contest active. |
| Example frame mockups | 3 | (1) Mos Eisley Tier 1a district view by day, (2) Dune Sea Tier 1b wilderness with an active anomaly (krayt dragon), (3) Tatooine Tier 3 planet view. These are illustrative *targets*, showing the renderer output you're aiming for. |
| Component spec sheet | 1 | Hex values, font sizes/weights, animation timings, asset sizing conventions, SVG export specs. |

Total file count: ~120–150 SVG/CSS/PNG files. This is more than a typical mockup engagement and reflects the asset-library nature of the work. The benefit: every file authored is permanent; the library does not get re-authored when the game adds a feature, only extended.

**What is in scope vs. out of scope for the *visual* design pass.**

In scope:
- Asset library as enumerated above.
- The visual language of each panel from §6 (the rich web client UI) — one mockup per panel, treated as the visual target the implementation will match. These are panel mockups, plural — distinct from the map.
- Marker system sheet, iconography sheet, palette swatch sheet.
- Diegetic flourish reference (§8) — sketches of the FP-spend shimmer, wound-state vignette, datapad-mode framing.

Out of scope (engineering, not visual):
- The map renderer itself (composition engine code).
- The wire protocol implementation.
- Builder tooling (the geometry editor).
- Dynamic state simulation.
- Server-side everything.

The right test: if Claude Design's output is consumed once and never re-authored, it's an asset; if it would have to be re-authored every time the game adds a feature, it's something engineering should build dynamically. Anything in the second category is out of scope.

**The "show me what the renderer's output should look like" deliverable.**

The three example frame mockups (the last row of the asset table above) are the *visualization* of what we're building toward. They are mockups in the traditional sense — single frames showing the assembled output. But they are not the map; they are *examples of the map at one specific moment*. Their purpose:

1. To validate that the asset library composes into the intended look. If a mockup using only the produced assets at a real scenario looks right, the library is correct.
2. To give engineering a reference image to match when implementing the renderer's composition logic.
3. To give Brian (and any future stakeholder) a "this is what we're aiming for" image.

Specifically, the three recommended frames:

- **Frame A: Mos Eisley Tier 1a district view, daytime, clear weather.** Player in the spaceport. Show ~12 visible rooms, of which Chalmun's Cantina, Docking Bay 94, and Kerner Plaza are named-landmark illustrations; the rest are style primitives. Streets drawn as actual paths with shoulder/center/wear. Player marker (cyan chevron, pulsing) at Docking Bay 94. Two NPC dots (amber friendly, grey neutral). Service icons visible on relevant rooms. Security tier tinting (mostly green — secured). Twin-sun shadows from buildings. Sand-bleached amber palette.
- **Frame B: Dune Sea Tier 1b wilderness, dusk, active krayt dragon anomaly.** Player marker mid-tile in a canyon terrain. ~6 visible tiles in sight radius, fog-of-war on the rest. The Tusken Camp landmark visible to the northeast. The krayt dragon anomaly marker pulsing dramatically to the southeast, ~4 tiles away. Faction territory border (Hutt Cartel) visible at the south edge. Dusk overlay shifting the palette. A travel-route line from the player toward the Tusken Camp.
- **Frame C: Tatooine Tier 3 planet view.** Stylized top-down planet body. Mos Eisley pinned with its icon-LOD silhouette. Jabba's Palace, Anchorhead, Bestine, Tosche Station as additional pins. Dune Sea and Jundland Wastes as terrain-themed polygons. Hyperspace beacon at one position. Faction shading: Hutt Cartel influence yellow-tinted, Republic minor presence blue dots at Bestine. Atmosphere glow at the planet edge. Twin suns visible.

Each frame is one image, ~1920×1080 or larger, lossless. They are the singular reference Brian shows engineering and says "make the renderer do this."

**The summary you can paste to Claude Design.**

> The map you're producing is wrong because the framing is wrong. The map in production is a **runtime composition engine** consuming hand-authored illustration assets. Your job is to produce the asset library, not the map.
>
> Specifically: ~10–15 named-landmark illustrations for Mos Eisley (each in three LOD variants — detailed/simplified/icon), ~5–8 wilderness landmarks for the Dune Sea, ~15–25 generic style primitives as fallback, ~20 painterly wilderness terrain tile variants, the marker system sheet, an iconography sheet (~30–40 glyphs), two per-planet palette swatch sheets, ~8 atmospheric overlay assets, and *three* example frame mockups showing what the assembled output looks like at specific game moments.
>
> The visual sensibility target is the hand-drawn cartography in WEG's *Galaxy Guide 7: Mos Eisley* — specifically page 13 (Tatooine regional map) and page 53 (Chalmun's Cantina floor plan). The PDF is at `/mnt/project/WEG40069.pdf`. Study those pages before authoring anything. Drawn, atmospheric, iconographic — not schematic.
>
> Read §7.13 and §10.9 of `web_client_vision_and_protocol_v1.1.md` in full. Those sections are written specifically to redirect this engagement.

### 10.10 Era-fidelity sanity checklist

The May 24 design drop review found that even after §10.2's glossary and §10.9's directive ("NO Empire, NO Rebellion, NO stormtroopers"), the design drop still contained "Imperial Patrol" as a wilderness anomaly, "Sealed Imperial Dispatch" as an active mission, an Imperial Security Bureau quote attribution in the Hutt Cartel holocron, and TIE fighters / X-wings in the space combat demo. The era pivot warnings need to be a literal checklist a designer can walk before submitting any deliverable.

**Before submitting ANY deliverable, verify:**

- [ ] No instance of "Empire" or "Imperial" in any content text (mission names, item names, NPC dialogue, holocron entries, news ticker, sample personality notes, character tags, comments in code that ship as text).
- [ ] No instance of "Rebel" or "Rebellion" as a faction reference. (Insurgent activity exists in CW era but is not "the Rebellion.")
- [ ] No "stormtroopers" in OT armor form. CW infantry is **clone troopers** (Phase 1 armor in earlier-CW era, Phase 2 in later-CW era; both white-and-color with phase-specific styling).
- [ ] No "TIE fighter" or "TIE/ln" or "TIE bomber." CIS fighters are **vulture droids** (variable-wing droid starfighters), **tri-fighters** (three-armed combat droids), and **Geonosian starfighters**.
- [ ] No "X-wing" or "Y-wing" used as a Rebel craft. (Y-wings actually existed in CW era as Republic bombers — but as Republic, not Rebel. ARC-170 starfighter is the more CW-iconic fighter.)
- [ ] No "Death Star," "Star Destroyer" (Imperial-class), or any post-Empire-construction-era ship name.
- [ ] No reference to Vader, Luke, Leia, Han, Chewbacca-as-Han's-copilot, Boba Fett-as-adult, the Emperor (as galactic ruler), Palpatine-as-Emperor.
- [ ] No "Imperial Security Bureau (ISB)" — does not exist in CW. Closest CW equivalent: **Senate Bureau of Intelligence (SBI)** or **Republic Intelligence**.
- [ ] No "Imperial-style" architecture in landmark/style names — call it "civic" or "Republic" or "local government" as appropriate.
- [ ] Character tags use CW-era factions: `REPUBLIC`, `JEDI`, `PADAWAN`, `KNIGHT`, `MASTER`, `CIS`, `SEPARATIST`, `HUTT`, `MERCENARY`, `BOUNTY HUNTER`, `MANDALORIAN`, `SMUGGLER`, `OUTLAW`, etc. — never `REBEL` or `IMPERIAL`.
- [ ] Random ambient NPC events in cities reference CW factions/groups (Republic patrols, Trade Federation reps, Hutt enforcers, Jedi attachés, clone troopers passing through) — never Imperial inspections or Rebel cell activity.
- [ ] Iconic CW personalities allowed and encouraged in news/holocron content: Anakin (Knight), Obi-Wan, Yoda, Mace Windu, Ahsoka, Padmé Amidala, Bail Organa, Dooku, Grievous, Ventress, Kit Fisto, Plo Koon, Aayla Secura, Kenobi.
- [ ] Era-plausible OT-canonical figures (Greedo as an adult bounty hunter, Wuher as the cantina bartender, Jabba Desilijic Tiure as the Tatooine Hutt boss) are fine to include — but cross-check the WEG sourcebook material or *The Clone Wars* TV series for accuracy on their CW-era activities.
- [ ] Equipment references era-appropriate models: blasters fine (DL-44 existed in CW but heavily Han-coded — consider alternatives), YT-1300 freighters fine, droidekas/B1/B2/B3 droids canon, lightsabers obviously canon, the Mandalorian Death Watch as a faction is canon, etc.

**When in doubt, ask Brian** rather than guess. A two-line "is X CW-era?" exchange takes thirty seconds; rebuilding a deliverable after era contamination is found takes much longer.

**Engineering Claude's discipline:** when reviewing any design drop, grep the deliverable for `Imperial`, `Empire`, `Rebel`, `Rebellion`, `Stormtrooper`, `TIE`, `X-wing`, `Vader`, `Death Star`, `ISB` (case-insensitive, word-boundary). Hits are flagged as B3-class issues per the review document.

---

## 11. Reference list

System design docs referenced by this document:

- `sw_d6_mush_architecture_v48.md` — current architecture of record
- `web_ux_competitive_analysis.md` — structured JSON principle
- `web_client_ux_overhaul_v1.md` — layout direction, width negotiation
- `ground_ux_overhaul_design_v1.md` — ground UX, mood theming, design language
- `web_chargen_design_v1.md` — REST chargen flow
- `CLAUDE_DESIGN_BRIEF.md` — original map design brief (superseded by §7)
- `Map_Redesign_v2.html` — approved per-style footprint mockup
- `combat_mechanics_display_design_v1.1.md` — combat_resolution_event schema (canonical)
- `field_kit_audit_and_remediation_v1.md` — pose_event schema (canonical)
- `security_zones_design_v1.md` — three-tier security model
- `security_model_design_v1.md` — locked CW-era security assignments
- `wilderness_system_design_v1.md` — tile grid wilderness mechanics
- `contestable_wilderness_design_v2.md` — wilderness contestability (locked May 24)
- `clone_wars_era_design_v3.md` — era pivot decisions
- `director_ai_design_v1.md` — Director AI architecture
- `padawan_master_system_design_v1.md` — Padawan-Master training
- `faction_reputation_design_v1.md` — reputation tiers
- `pc_narrative_memory_design_v1.md` — PC narrative memory / dossier
- `progression_gates_and_consequences_design_v1.md` — death system (PG.1)
- `player_cities_design_v1_2.md` — player cities
- `space_overhaul_v3_design.md` — space subsystem

WEG sourcebook references (aesthetic only — content references era-mismatched):

- *Star Wars Sourcebook* (2nd ed., WEG40093) — visual sensibility
- *Galaxy Guide 7: Mos Eisley* (WEG40069) — pilot city reference
- *Imperial Sourcebook* (WEG40092) — interior cross-section style (era-mismatched for content)

---

*End of design document v1.2. Sign-off pending.*
