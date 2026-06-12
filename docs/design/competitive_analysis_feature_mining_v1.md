# SW_MUSH — Competitive Analysis & Feature Mining
## Design Document v1.0
### April 13, 2026 · Opus Session

---

## 1. Executive Summary

After surveying six online games/platforms — **Sindome** (MOO), **Armageddon MUD** (RPI), **AI Dungeon / NovelAI** (AI narrative), **Evennia** (Python MU\* engine), **AresMUSH** (Ruby MU\* platform), and **Legends of the Jedi** (Star Wars MUD) — plus cross-referencing our own architecture doc (v23) and economy audit, this document identifies **23 concrete, actionable feature ideas** organized by priority and implementation effort.

The thesis: SW_MUSH already leads the field in AI-driven narrative (Director system), economy depth, and web client UX. Where we can draw the most value is in **player interdependence mechanics** (Sindome), **environmental survival pressure** (Armageddon), **keyword-triggered contextual lore injection** (NovelAI's Lorebook pattern), **achievement/progression visibility** (Evennia contribs), **automated scene logging for the web** (AresMUSH), and **player-driven crafting economies where engineers are kingmakers** (Legends of the Jedi).

None of these require architectural changes. Every recommendation maps to existing engine files and DB tables.

---

## 2. Source-by-Source Analysis

### 2.1 Sindome (MOO) — Player Interdependence & Living City

**What they do well:**

Sindome's core design philosophy is that no character should be self-sufficient. Combat characters need doctors. Doctors need supplies from fixers. Fixers need information from deckers. This creates a web of dependencies that forces organic RP interaction — nobody can grind solo to the top.

Their key systems worth studying:

**A. SIC Chip (Subdermal Identification Chip) — Universal Comms Layer.** Every character has an implanted communication device that serves as ID, city-wide chat, and encrypted private messaging. This is brilliant because it's both a gameplay system and a narrative device — it can be jammed, intercepted, or hacked. It creates emergent espionage gameplay without a dedicated "espionage system."

**Relevance to SW_MUSH:** We already have comlink channels, but they're functionally just chat. A "comlink intercept" system where Espionage-skilled characters can eavesdrop on channels in adjacent rooms — gated by a Perception vs. Security contested roll — would create an entirely new profession chain. The infrastructure is already there in `engine/skill_checks.py` and the channel system.

**B. Persistent Character Vulnerability.** When you log out in Sindome, your character falls asleep in place. Your stuff can be stolen, you can be attacked. This means housing (apartments with locks) isn't a luxury — it's survival. Rent is an essential credit sink, not an optional vanity purchase.

**Relevance to SW_MUSH:** We already have a housing system with locks and guest lists. We could add a lightweight "sleeping character" flag where characters who disconnect in non-secured rooms are flagged as vulnerable to pickpocketing (Pickpocket skill check vs. the sleeper's Perception, with the sleeper rolling at disadvantage). This makes apartments in secured zones a genuine survival need, not just cosmetic. The implementation is trivial — a flag on disconnect, a check in the `steal` command.

**C. Layered Equipment & Body Part Descriptions.** Sindome lets players set descriptions for individual body parts. Clothing covers specific body parts, and what's visible changes dynamically based on what you're wearing. Cybernetics alter your body description.

**Relevance to SW_MUSH:** Our `@describe` is a single text block. A layered system where armor covers specific body locations (already tracked for combat hit locations) and modifies what `look` shows would add enormous texture. Implementation: store per-location description snippets in character attributes JSON, compose `look` output dynamically. Moderate effort (8-12 hours) but high immersion payoff.

**D. Economy as Survival, Not Accumulation.** Sindome's economy thread reveals that even basic apartments are expensive relative to entry-level income. New players struggle to afford rent AND cloning (their respawn insurance). This creates genuine tension — every credit matters.

**Relevance to SW_MUSH:** Our economy audit identified that trade goods are a "solved game" generating ~240K cr/hr vs. a 2K cr/hr design target. Sindome validates the principle: if basic survival is cheap, the economy loses all tension. Our economy hardening plan already addresses this, but Sindome proves the principle works — players who struggle to make rent are more engaged than players who can buy everything by week 4.

---

### 2.2 Armageddon MUD (RPI) — Environmental Pressure & Permadeath Tension

**What they do well:**

Armageddon's world of Zalanthas is defined by scarcity. Water is a consumable resource. Travel through the desert is genuinely dangerous. Every expedition outside city walls could be your last. The `think` command lets you write internal monologue that staff can read, creating a window into character motivation.

**Note:** Armageddon closed in 2024 and is being rebuilt as "Tales of Zalanthas" on the Evennia engine. The design lessons remain valid even though the original codebase is defunct.

**A. Environmental Hazards as Gameplay.** Armageddon's desert has thirst mechanics, sandstorm events, and hostile wildlife in wilderness rooms. These aren't just flavor — they're mechanical threats that drain resources and force preparation. Going into the wasteland without water and supplies is suicide.

**Relevance to SW_MUSH:** Our planets lack environmental pressure. Tatooine should punish players who venture into the Dune Sea without preparation. A lightweight hazard system: rooms tagged with `environment_hazard` in their properties fire a periodic check (every 5 minutes while a PC is present). Tatooine desert = dehydration (Stamina drain). Kessel mines = toxic atmosphere (Strength check or take wound). Nar Shaddaa lower levels = random mugging (NPC pickpocket attempts). These are Director AI ambient events with mechanical teeth. Implementation: add a `hazard_type` field to room properties, a periodic task in `game_server.py`, and hook into existing wound/condition systems. 4-6 hours.

**B. The `think` Command — Internal Monologue.** Armageddon's `think` command writes text visible only to the character and staff. It creates a private narrative log that GMs use to understand character motivation and tailor plots.

**Relevance to SW_MUSH:** This is a natural fit for our PC Narrative Memory system (design doc v1). If `think` output is logged to `pc_action_log` with `event_type = 'thought'`, and the nightly Haiku summarization pipeline includes it, NPCs could respond to a character's *demeanor* without the character explicitly telling them anything. "You seem troubled" from a bartender NPC who read the thought log is emergent, private, and immersive. Implementation: one new command, one `pc_action_log` insert. 1-2 hours, plus tuning the summarization prompt.

**C. Crafting Tied to Survival, Not Vanity.** In Armageddon, crafting was tied to survival needs — making waterskins, tents, basic tools from scavenged materials. The desert *demanded* these items.

**Relevance to SW_MUSH:** Our crafting system produces weapons and armor, but nothing the environment *demands*. If environmental hazards exist (per 2.2A above), crafting survival gear (breath masks for Kessel, cooling units for Tatooine, anti-mugging alarms for Nar Shaddaa) creates a new crafting lane that isn't competing with NPC vendor gear. It's crafting things NPCs *don't* sell.

**D. Permadeath's Emotional Weight.** Armageddon's permadeath creates extraordinary tension. Every combat encounter has stakes. Players write their characters' stories knowing they could end at any moment.

**Relevance to SW_MUSH:** We don't want permadeath — it's incompatible with our MMO-informed design and casual player retention goals. But we can borrow the *emotional structure* without the mechanical finality. A "near-death experience" system: when a character drops to 0 wounds (Incapacitated), they gain a permanent `scar` entry in their character record, visible on `+sheet` and injected into their PC narrative short record. "Kael Voss — survived a blaster wound to the chest on Nar Shaddaa" becomes part of their identity. NPCs can reference it. It creates permanent consequences without permanent death. Implementation: one INSERT on incapacitation, template updates to `+sheet` and narrative prompts. 2-3 hours.

---

### 2.3 AI Dungeon / NovelAI — Memory Architecture for AI Narrative

**What they do well:**

These platforms have spent years solving the core problem our Director AI also faces: how to maintain narrative coherence across a context window that can only hold a fraction of the world state.

**A. NovelAI's Lorebook Pattern — Keyword-Triggered Context Injection.** NovelAI's Lorebook is their most sophisticated feature. It works like this: you create entries for characters, locations, factions, and items. Each entry has activation keywords. When those keywords appear in the recent narrative context, the entry is injected into the AI's prompt. The key insight: the AI doesn't carry the entire world state at all times. It loads relevant context *on demand* based on what's currently happening.

**Relevance to SW_MUSH:** This is directly applicable to our Director AI and NPC dialogue systems. Right now, the Director's faction turn prompt gets a fixed set of faction data. A Lorebook-style system would maintain a `world_lore` table of entries (locations, faction relationships, notable NPCs, recent events) with keyword triggers. When the Director constructs its prompt, it scans the current game state (which zones are active, which factions have players online, what recent events fired) and dynamically injects only the relevant lore entries. This compresses the prompt while increasing relevance.

Similarly, `npc_brain.py` could keyword-match against the player's recent dialogue to pull in relevant lore. If a player asks an NPC about "the Empire" in a Rebel-held territory, the NPC's prompt would get the Rebel faction entry and the local political situation injected — without carrying every faction's lore at all times.

**Implementation sketch:**
```sql
CREATE TABLE world_lore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    keywords    TEXT NOT NULL,    -- comma-separated activation keywords
    content     TEXT NOT NULL,    -- the lore text to inject (max 200 tokens)
    category    TEXT NOT NULL,    -- 'faction', 'location', 'npc', 'event', 'item'
    zone_scope  TEXT,            -- optional: only activate in specific zones
    priority    INTEGER DEFAULT 5,
    created_at  REAL NOT NULL
);
```

This is 4-6 hours of implementation but would dramatically improve both Director coherence and NPC dialogue quality. High-value addition to the PC Narrative Memory design doc.

**B. Memory vs. Lorebook Distinction — Two-Tier Context.** NovelAI separates "Memory" (always-present context about the current story) from "Lorebook" (on-demand context triggered by keywords). This maps almost exactly to our existing two-tier PC narrative design: short record (always available to Mistral) and long record (available to Haiku on demand).

**Relevance to SW_MUSH:** Validates our existing design. The PC Narrative Memory doc already got this right. The addition is the world-level Lorebook system described above, which is the *third* tier — world context that neither the short nor long record covers.

**C. Author's Note — Steering Narrative Tone.** NovelAI's "Author's Note" is a persistent instruction injected near the end of the context that guides the AI's tone and style without being part of the story itself. Users write things like "The mood is tense and paranoid" and the AI adjusts its output accordingly.

**Relevance to SW_MUSH:** The Director AI's system prompt already does this at a macro level. But we could add a per-zone "narrative tone" field to the Director's configuration:

```yaml
zones:
  mos_eisley:
    narrative_tone: "Dangerous, lawless, everyone is looking over their shoulder. Deals happen in whispered conversations. Trust is currency."
  imperial_garrison:
    narrative_tone: "Oppressive, militaristic, tightly controlled. Everyone watches what they say. Stormtroopers patrol in pairs."
```

This tone string gets injected into both the Director's faction turn prompt (when generating events for that zone) and into `npc_brain.py` (when NPCs in that zone generate dialogue). Small addition to config YAML, large impact on narrative consistency. 1-2 hours.

---

### 2.4 Evennia — Python Architecture & Contrib Systems

**What they do well:**

Evennia is the closest architectural cousin to SW_MUSH — both are Python, both use asyncio-compatible patterns, both target the MU\* audience with modern tooling. After reviewing the full codebase, the most valuable patterns are:

**A. Achievement System.** Evennia's achievement contrib provides tracked, persistent achievements defined as Python dicts with progress tracking, categories, and tiered completion. The system tracks partial progress ("Kill 10 NPCs: 3/10") and fires callbacks on completion.

**Relevance to SW_MUSH:** We have no achievement system. This is a significant retention gap for the 2026 audience. Achievements serve as both progression markers and tutorial breadcrumbs. A SW_MUSH achievement system could track milestones across every system: "First Blood" (win your first combat), "Kessel Run" (complete a smuggling run), "Force Awakening" (discover Force sensitivity), "Empire's Most Wanted" (reach Bounty Level 3), "Landlord" (purchase a residence), "Territory Baron" (claim 5 rooms).

Achievements would integrate with the web client as a panel (similar to territory and housing panels), and could award CP bonuses on first completion — providing guided progression for new players without requiring the tutorial's rigid structure.

Implementation: new `achievements` table, a `check_achievement()` hook called from existing systems (combat, missions, crafting, etc.), web client panel. 8-12 hours total, but modular — each system's achievement hooks can be added incrementally.

**B. Buff/Debuff Handler.** Evennia's buff contrib provides timed status effects with stacking, expiration, and stat modification. Buffs are persistent across server restarts and can be paused when a character goes offline.

**Relevance to SW_MUSH:** We have wound states and Force power effects, but no generalized buff/debuff system. Environmental hazards (2.2A), combat stims, food/drink effects, and Force power durations would all benefit from a unified `BuffHandler` class. Currently these are all ad-hoc implementations. A unified handler would be:

```python
class BuffHandler:
    """Manages timed status effects on a character."""
    async def add_buff(self, char_id: int, buff_type: str, 
                       duration_seconds: int, modifier: dict):
        """Add or stack a buff. Modifier: {'stat': 'dexterity', 'bonus_pips': 1}"""
    async def check_buffs(self, char_id: int) -> list[Buff]:
        """Return all active buffs, pruning expired ones."""
    async def get_stat_modifier(self, char_id: int, stat: str) -> int:
        """Sum all active buff modifiers for a given stat."""
```

This enables: combat stims (+1D Dexterity for 5 minutes), Tatooine heat exhaustion (-1 pip Stamina until you drink water), bacta treatment (+2D healing for 1 hour), Dark Side corruption effects, cantina drinks (minor buffs with roleplay flavor). 6-8 hours for the core handler, then individual buff sources are 1-2 hours each.

**C. Extended Room — State-Based Descriptions.** Evennia's ExtendedRoom allows room descriptions to change based on time of day, season, and arbitrary state flags. A room can be "on fire" or "flooded" and its description changes accordingly. It also supports "details" — sub-objects you can `look` at without creating database objects.

**Relevance to SW_MUSH:** Our rooms have static descriptions. The Director AI generates ambient text, but the room `look` output never changes. State-based descriptions would let the Director's narrative events actually modify the world players see:

- Director fires a "Imperial Crackdown" event → rooms in the affected zone gain a `crackdown` state → their descriptions append "Stormtrooper patrols are more frequent than usual. Citizens hurry past with their eyes down."
- A territory control room that's been claimed by an organization → description reflects the faction's presence: "Rebel Alliance banners hang from the rafters. A sentry watches the entrance."

Implementation: add a `room_states` JSON field to room properties, modify the `look` command to compose descriptions dynamically. The Director event handler already modifies game state — it just needs to write room state flags. 4-6 hours.

**D. Wilderness/Procedural Grid — Efficient Map Generation.** Evennia's wilderness contrib creates vast explorable areas without individual room database entries. As you move, the room recycles but its description changes based on coordinates. This allows huge desert or space areas with minimal DB overhead.

**Relevance to SW_MUSH:** Less immediately relevant since our planets use hand-crafted rooms. However, this pattern could enable future wilderness zones (Tatooine Dune Sea, Kashyyyk forests, Dagobah swamps) as procedurally generated exploration areas for gathering resources, encountering wildlife, and finding hidden locations. This is a "future roadmap" item, not a near-term priority. Would require a separate design doc.

**E. Barter System — Structured Player Trading.** Evennia's barter contrib implements a safe trading protocol where both players add items to a trade window, both approve, and items swap atomically. No risk of one player running off with goods.

**Relevance to SW_MUSH:** Our `pay` command transfers credits, but there's no safe item-for-item or item-for-credits trading. A `trade` command would formalize player commerce and provide a hook for the transaction tax (already in the economy audit). Implementation: 3-4 hours.

**F. Cooldown Handler — Centralized Rate Limiting.** Evennia's cooldown contrib provides a clean API for checking "has enough time passed since X?" without scattered `time.time()` comparisons throughout the codebase.

**Relevance to SW_MUSH:** We use ad-hoc cooldown checks in multiple systems (crafting, smuggling, survey, sabacc). A centralized cooldown handler stored in character attributes would clean up the codebase and make it trivial to add cooldowns to new systems. Low effort (2-3 hours), high code quality improvement.

---

### 2.5 AresMUSH — Web Portal & RP Social Features

**What they do well:**

AresMUSH's killer feature is the web portal, particularly its scene logging and RP management tools. The Ares philosophy is that the web should be a first-class citizen for RP, not just a convenience layer.

**A. Automated Scene Logging.** Ares captures scene logs automatically, strips OOC chatter, formats rolls and combat results, and publishes them to the web portal. Players can browse, search, and filter past scenes. Scene pages generate icons from character profile images.

**Relevance to SW_MUSH:** This is a significant gap. Our web client shows real-time gameplay but has no scene archive. An automated scene logging system would:
1. Track when a room has 2+ PCs present for more than 5 minutes (scene detection)
2. Capture all IC text (emotes, says, poses), combat results, and skill checks
3. Strip OOC chatter (`ooc`, `+ooc`, page messages)
4. Store as a scene record in a `scene_logs` table
5. Display on the web client as a searchable scene archive

This is enormously valuable for several reasons: RP communities *love* reading scene logs, it creates a public record of the game's evolving story, it helps absent players catch up, and it gives the Director AI a rich source of recent events to reference.

Implementation: scene detection logic in `game_server.py`, a `scene_logs` table, text filtering, a web client panel. 10-15 hours, but a high-impact feature for community building.

**B. Web-Based Character Creation.** Ares lets players create characters entirely through the web portal with fill-in forms, dropdown menus, and validation. No need to learn commands first.

**Relevance to SW_MUSH:** Our character creation is command-based (the tutorial system handles it). A web-based chargen would dramatically lower the barrier for non-MU\* players — our target expansion audience. This is a substantial project (20-30 hours) but would be the single highest-impact feature for player acquisition from the web audience. Should be a dedicated design doc and implementation sprint.

**C. RP Preferences Plugin.** Ares's `ares-prefs-plugin` lets players declare RP preferences (Adventure: Yes, Romance: Maybe, Horror: No) that show on their profile and are searchable. Players can find others with compatible preferences.

**Relevance to SW_MUSH:** A lightweight implementation: add an `rp_preferences` JSON field to character attributes, a `+rpprefs` command to set them, display on `+finger`. The Director AI could even use RP preferences when generating personal quest hooks — don't send horror-themed quests to players who've flagged "Horror: No." 2-3 hours.

**D. Places System.** Ares's places system (tables/booths in a room) is already implemented in our MU\* compatibility layer (Phase 2, `parser/places_commands.py`). We got this one right. The table-talk muffling mechanics from our implementation actually exceed what Ares offers.

---

### 2.6 Legends of the Jedi — Star Wars MUD Competitor Analysis

**What they do well:**

LOTJ is our most direct competitor — a Star Wars text game with space combat, crafting, and faction warfare. It's been running since 1999 and consistently ranks as the top Star Wars MUD. Understanding what they offer (and what we can do better) is critical.

**A. Player-Driven Crafting Economy — Engineers as Kingmakers.** In LOTJ, engineers don't just craft generic items from recipes. They design custom weapons, armor, and ships with variable stats based on their skill level and component choices. Every piece of equipment in the game's economy was built by a player engineer. NPCs don't sell competitive gear.

**Relevance to SW_MUSH:** Our crafting system uses fixed schematics with skill-based quality rolls. LOTJ's model goes further — the *design* of the schematic is itself a player skill. An "experimentation" system where engineers can adjust parameters (damage vs. accuracy, armor vs. mobility) during crafting would create differentiated products and a more dynamic player market. This maps to our existing `engine/crafting.py` experimentation framework — the hooks exist, they just need parameter ranges defined per schematic category. 6-8 hours.

**B. Information as Currency — The Spy Class.** LOTJ has a spy class where information brokering is a core gameplay loop. Spies gather intelligence (troop movements, faction plans, character locations) and sell it. Information has explicit economic value.

**Relevance to SW_MUSH:** Our Espionage profession chain exists but lacks mechanical depth. Specific ideas:
- `scan <player>` command (Perception vs. target's Con) reveals their credits, wounds, and equipped weapons
- `eavesdrop` command (Perception check) lets you listen to conversations in adjacent rooms
- `investigate <location>` (Search check) reveals hidden exits, stashed items, or security vulnerabilities
- A `+intel` command that packages gathered intelligence into a tradeable data item (like a datapad) that can be sold to faction leaders for credits and reputation

These commands route through `perform_skill_check()` per our invariant and create genuine gameplay for the Intelligence-focused character. 8-12 hours across all four commands.

**C. Timeline/Era System.** LOTJ runs on 2-year real-time "timelines" that cycle through Star Wars eras. When a timeline ends, the galaxy resets. This creates a built-in content lifecycle.

**Relevance to SW_MUSH:** We're set in the Galactic Civil War era permanently — no timeline resets. But the *concept* of era progression could work: as the Director AI accumulates enough faction influence shifts, the galaxy's political state could visibly evolve. If the Rebel Alliance faction accumulates dominant influence across multiple zones, the Director could fire a "The Empire Strikes Back" escalation event (Star Destroyer deployment, increased patrols). If the Empire dominates, a "Rebel in Retreat" state could trigger hidden rebel cells and guerilla mechanics. This is already within the Director's design capabilities — it just needs defined threshold triggers. 4-6 hours to define thresholds and wire events.

**D. Multi-Level Skill System.** LOTJ uses a level-based system where you can multi-class (150 engineering + 40 piloting). This creates hybrid characters with interesting capability combinations.

**Relevance to SW_MUSH:** WEG D6 already handles this natively through its dice-pool skill system — characters naturally specialize through CP allocation. No changes needed; our system is already superior to LOTJ's level-based approach for character differentiation.

---

## 3. Cross-Cutting Themes

Several patterns emerged across multiple sources:

### 3.1 Player Interdependence is the Key to Retention

Sindome, Armageddon, and LOTJ all demonstrate that forcing players to depend on each other creates stronger communities than any amount of solo content. SW_MUSH should ensure that no single character build can self-sufficiently handle combat, crafting, piloting, AND diplomacy at high levels. The CP progression system already creates this pressure — reinforce it by ensuring high-end content requires team composition.

### 3.2 Environmental Pressure Creates Engagement

Both Sindome (rent as survival) and Armageddon (water, heat, predators) show that passive environmental threats create more engaging gameplay than purely opt-in challenges. Our planets currently lack environmental identity beyond flavor text.

### 3.3 AI Context Management is a Solved Problem (Sort Of)

NovelAI's Lorebook, AI Dungeon's memory anchors, and our own PC Narrative Memory system are all solving the same problem from different angles. The consensus approach is: tiered context (always-on memory + keyword-triggered lore + recent history), structured data over freeform, and aggressive compression. Our Director system is already well-designed; the Lorebook pattern is the main enhancement.

### 3.4 The Web is the Front Door

AresMUSH and Evennia both recognize that the web client/portal is the primary acquisition channel. Our web client is already strong; web-based chargen is the missing piece for converting web visitors into players.

---

## 4. Prioritized Feature List

### Tier 1: High Impact, Low Effort (Do During Economy Hardening Sprint)

| # | Feature | Source | Effort | Files Affected |
|---|---------|--------|--------|----------------|
| 1 | `think` command → PC action log | Armageddon | 1-2 hrs | New command, `pc_action_log` |
| 2 | Narrative tone per zone (YAML config) | NovelAI Author's Note | 1-2 hrs | `data/zones.yaml`, `engine/director.py`, `npc_brain.py` |
| 3 | Centralized cooldown handler | Evennia | 2-3 hrs | New `engine/cooldowns.py`, refactor existing checks |
| 4 | RP preferences on `+finger` | AresMUSH | 2-3 hrs | `parser/mux_commands.py`, character attributes |
| 5 | Scar system (permanent wound record) | Armageddon | 2-3 hrs | `engine/combat.py`, `+sheet`, narrative prompts |
| 6 | `trade` command (safe item exchange) | Evennia barter | 3-4 hrs | New `parser/trade_commands.py` |

**Total Tier 1: ~12-17 hours**

### Tier 2: High Impact, Medium Effort (First Month Post-Launch)

| # | Feature | Source | Effort | Files Affected |
|---|---------|--------|--------|----------------|
| 7 | World Lore table + keyword injection | NovelAI Lorebook | 4-6 hrs | New `world_lore` table, `engine/director.py`, `npc_brain.py` |
| 8 | Environmental hazards (room-based) | Armageddon | 4-6 hrs | Room properties, `game_server.py`, new periodic task |
| 9 | Room state descriptions | Evennia ExtendedRoom | 4-6 hrs | Room properties, `look` command, Director events |
| 10 | Espionage commands (`scan`, `eavesdrop`, `investigate`, `+intel`) | LOTJ Spy class, Sindome | 8-12 hrs | New commands in `parser/`, `engine/skill_checks.py` |
| 11 | Achievement system (core + web panel) | Evennia | 8-12 hrs | New `achievements` table, hooks across systems, web panel |
| 12 | Crafting experimentation (parameter tuning) | LOTJ engineering | 6-8 hrs | `engine/crafting.py`, `data/schematics.yaml` |
| 13 | Buff/debuff handler | Evennia buffs | 6-8 hrs | New `engine/buffs.py`, integration points |

**Total Tier 2: ~41-58 hours**

### Tier 3: High Impact, High Effort (Roadmap Items)

| # | Feature | Source | Effort | Files Affected |
|---|---------|--------|--------|----------------|
| 14 | Automated scene logging + web archive | AresMUSH | 10-15 hrs | `game_server.py`, new `scene_logs` table, web panel |
| 15 | Director era-progression thresholds | LOTJ timelines | 4-6 hrs | `engine/director.py`, event definitions |
| 16 | Sleeping character vulnerability | Sindome | 4-6 hrs | Disconnect handler, `steal` command |
| 17 | Layered equipment descriptions | Sindome | 8-12 hrs | `look` command, character attributes, equipment system |
| 18 | Survival crafting lane (environment-specific gear) | Armageddon | 6-8 hrs | `data/schematics.yaml`, `engine/crafting.py` |
| 19 | Comlink intercept system | Sindome SIC | 6-8 hrs | Channel system, `engine/skill_checks.py` |
| 20 | Web-based character creation | AresMUSH | 20-30 hrs | `static/client.html`, new API endpoints, chargen logic |

**Total Tier 3: ~59-85 hours**

### Tier 4: Future Consideration (Needs Design Doc)

| # | Feature | Source | Notes |
|---|---------|--------|-------|
| 21 | Procedural wilderness zones | Evennia wilderness | Large architectural addition for exploration content |
| 22 | Hacking/slicing minigame | Sindome Grid | Cyberpunk Matrix → Star Wars computer slicing |
| 23 | Player-run government/senate | LOTJ Galactic Senate | Org system extension for political gameplay |

---

## 5. What NOT to Adopt

Several observed patterns are explicitly bad fits for SW_MUSH:

**Permadeath** (Armageddon). Incompatible with casual player retention and MMO-informed design goals. Our "scar system" captures the emotional weight without the player loss.

**Opaque mechanics** (Sindome, Armageddon). Both games deliberately hide mechanical details from players. Our design philosophy (per the Gemini critique response doc and Tales of Zalanthas's explicit rejection of this) is transparency. Players should know how skill checks work, what their odds are, and why they failed.

**Karma/trust gating** (Armageddon). Locking races and classes behind account trust scores creates insider/outsider dynamics that poison communities. All SW_MUSH content should be accessible through gameplay, not OOC reputation.

**Full softcode** (TinyMUX, Evennia). Our TinyMUX comparison doc already settled this — SW_MUSH provides builder tools without requiring players to learn a programming language.

**AI-generated room descriptions on `look`** (explicitly rejected in Director AI design doc §13). Room descriptions are canonical. AI supplements via ambient text, never replaces the authored room.

**DIKU-style level grinding** (LOTJ, d20MUD). WEG D6's skill-based progression is mechanically superior. Levels create artificial gates; dice pools create organic specialization.

---

## 6. Implementation Roadmap Integration

### Pre-Launch (Economy Hardening Sprint)
Add Tier 1 items alongside economy fixes. These are all small, independent additions that don't complicate the economy work.

### Month 1 Post-Launch
Prioritize items 7 (Lorebook), 11 (Achievements), and 10 (Espionage commands). These create the most visible new gameplay for early adopters.

### Month 2-3 Post-Launch
Scene logging (14), buff system (13), and environmental hazards (8) add depth for retained players. Crafting experimentation (12) and room states (9) enrich the living world.

### Quarter 2+
Web chargen (20), wilderness zones (21), and layered descriptions (17) are the long-tail features that mature the platform.

---

## 7. Architecture Doc Changes (for v24)

**New section: §18A Competitive Analysis Features**
- Subsections: World Lore System, Achievement System, Buff Handler, Environmental Hazards, Scene Logging
- References this design doc for full specification

**Modified: §13A Director AI System**
- Add: World Lore table as third context tier
- Add: Per-zone narrative tone configuration
- Add: Era-progression threshold triggers

**Modified: §14B PC Narrative Memory System**
- Add: `think` command as action log source
- Add: World Lore keyword injection in NPC dialogue prompts

**Modified: §12 Economy System**
- Add: Crafting experimentation parameters
- Add: Survival crafting lane
- Add: Safe trade command

**Modified: §17 MU\* Compatibility Layer**
- Add: RP preferences to `+finger`

---

*End of Competitive Analysis & Feature Mining Design Document — Version 1.0*
*Reference: sw_d6_mush_architecture_v23.md, economy_audit_v1.md, director_ai_design_v1.md, pc_narrative_memory_design_v1.md, tinymux_comparison_design_v1.md*
