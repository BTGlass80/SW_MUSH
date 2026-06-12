# SW_MUSH — PC Narrative Memory & Personalized Quest System
## Design Document v1.0
### April 2026 · BTGlass80 · WEG D6 R&E

---

## 1. Design Philosophy

The Director AI already moves the macro pieces — faction influence, narrative events, atmospheric text. But it treats all PCs the same. A smuggler who just ran three Kessel spice hauls sees the same world as a bounty hunter who just collected on a Veteran target. That's a missed opportunity.

This system gives the Director **memory** — a compact, two-tier record of who each PC is and what they've done. With that memory, the Director can:

- Weave personalized quest hooks into faction turns ("A contact on Nar Shaddaa heard about your last run...")
- Generate custom missions tailored to a PC's skills, history, and relationships
- Have NPCs reference past events naturally via Mistral ("Didn't you used to work for the Hutts?")
- Create emergent storylines where PC actions have long-term narrative consequences

**The golden rule still holds**: the Director sets the stage; players perform on it. This system never tells a player what they feel or forces them into a scene. It creates *personalized opportunities* — a bounty that targets someone the PC has dealt with before, a smuggling job on a route they know, a rumor about something they did last week.

---

## 2. Two-Tier Record Architecture

Each PC maintains two narrative records, sized for the AI model that consumes them.

### 2.1 Short Record (Mistral Briefing Card)

| Field | Value |
|-------|-------|
| **Target model** | Mistral 7B (local, RTX 3070) |
| **Max length** | 150 words (~200 tokens) |
| **Storage** | `pc_narrative` table, `short_record` column |
| **Update frequency** | Every long record update (derived by Haiku) |
| **Consumers** | `npc_brain.py` (NPC dialogue), ambient event personalization |

**Purpose**: A tight "briefing card" that Mistral can ingest without blowing its context budget. Contains only what an NPC who's been around Mos Eisley would plausibly know: reputation, recent visible actions, general demeanor, known associates.

**Example**:
```
Kael Voss. Human male, mid-30s. Freelance pilot operating out of Docking Bay 94.
Known smuggler — runs gray market cargo between Tatooine and Nar Shaddaa. Recently
got into a cantina brawl with a Trandoshan bounty hunter; walked away but took a
beating. Owes Venn Kator 2,000cr for hull repairs. Has been seen talking to Rebel
sympathizers in the market district. Carries a modified DL-44. Reputation: reliable
but reckless.
```

### 2.2 Long Record (Director Context)

| Field | Value |
|-------|-------|
| **Target model** | Claude Haiku 4.5 (API) |
| **Max length** | 800 words (~1,000 tokens) |
| **Storage** | `pc_narrative` table, `long_record` column |
| **Update frequency** | Nightly batch + on-demand triggers |
| **Consumers** | `engine/director.py` (faction turn PC digest), quest generation |

**Purpose**: Rich narrative context that Haiku uses for Director decisions and quest personalization. Includes motivations, relationship web, faction standing arc, skill progression trajectory, and a rolling "recent events" log.

**Example**:
```
## Kael Voss — Narrative Record

BACKGROUND: Former Imperial supply clerk (Lothal depot) who deserted 18 months ago
after witnessing civilian cargo seizures. Stole a YT-1300 (the "Dusty Mynock") and
fled to the Outer Rim. Motivated by survival, not ideology — but has a soft spot for
underdogs. Player-written: "Kael doesn't trust the Rebellion any more than the Empire,
but he'll take their money."

RELATIONSHIPS:
- Venn Kator (Shipwright, DB94): Owes 2,000cr for hull repairs. Cordial but transactional.
- Greeta (Rodian fixer, Cantina): Primary job contact. 3 successful runs together.
- Trandoshan bounty hunter (unnamed): Hostile. Cantina brawl 2 days ago. Unresolved.

RECENT EVENTS (last 14 days):
- Completed 2 gray-market smuggling runs (Tatooine→Nar Shaddaa). No incidents.
- Failed 1 spice run — dumped cargo to avoid Imperial patrol. Lost 3,000cr in goods.
- Won cantina brawl vs Trandoshan, took Wounded result, healed at medical bay.
- Purchased sensor upgrade for Dusty Mynock.
- Spent time in market district talking to known Rebel contacts (flagged by Director).

FACTION ARC: Imperial standing declining (deserted). Criminal neutral (does jobs, pays
debts). Rebel curious — not committed. Could tip either way.

SKILL TRAJECTORY: Piloting 5D+1, improving. Blaster 4D. Streetwise 3D+2 (rising from
smuggling checks). Technical weak — relies on Venn Kator for repairs.

QUEST HOOKS (Director notes):
- Trandoshan encounter is unresolved — potential bounty or revenge arc.
- Rebel contacts could offer a recruitment mission if standing improves.
- Imperial desertion backstory could trigger an Imperial Intelligence subplot.
- Debt to Venn Kator creates economic pressure toward riskier jobs.
```

---

## 3. Data Sources

The narrative records are built from multiple input streams:

### 3.1 Player-Written Background (`+background` command)

Players write their own origin story. This is the **seed** for the long record and the only part that's purely player-authored. Stored separately so it's never overwritten by AI summarization.

| Field | Value |
|-------|-------|
| **Command** | `+background <text>` (set/replace), `+background` (view) |
| **Max length** | 500 words |
| **Storage** | `pc_narrative` table, `player_background` column |
| **Editable** | Anytime by the player |

### 3.2 Automated Action Log

The system silently logs narratively significant PC actions. These feed into the summarization pipeline.

| Event Type | Source Hook | Data Captured |
|------------|------------|---------------|
| Combat outcome | `combat_commands.py` kill/wound hooks | Opponent, result, location |
| Mission complete | `mission_commands.py` completion | Type, pay, skill used, pass/fail |
| Bounty collected | `bounty_commands.py` collection | Target tier, method |
| Smuggling run | `smuggling_commands.py` deliver/dump | Tier, success/failure, cargo dumped? |
| Crafting | `crafting.py` assembly complete | Item type, quality, experimentation result |
| Purchase/sale | `buy`/`sell` commands | Significant transactions (>500cr) |
| Planet travel | `LandCommand` arrival | Destination planet |
| NPC interaction | `npc_brain.py` talk/ask | NPC name, topic (brief) |
| Faction rep change | Future faction system | Faction, old→new standing |
| Force power use | `force_powers.py` | Power used, DSP earned |
| Skill training | `train` command | Skill, old→new level |

**Storage**: `pc_action_log` table. Append-only. Pruned after summarization (archive rows older than 30 days).

### 3.3 Director Annotations

The Director can append "quest hook" notes to a PC's long record during faction turns. These are internal — never shown to the player — and guide future quest generation.

---

## 4. Summarization Pipeline

### 4.1 Nightly Batch Job

Runs once per day (configurable, default 03:00 server time). Uses the **Batch API** for 50% cost reduction.

**Pipeline**:
1. For each PC with new action log entries since last summarization:
   a. Load: player background + current long record + new action log entries
   b. Send to Haiku with summarization prompt (see §4.3)
   c. Haiku returns: updated long record + distilled short record
   d. Validate lengths (long ≤1000 tokens, short ≤200 tokens)
   e. Write to `pc_narrative` table
   f. Mark action log entries as summarized

**Batch size**: All PCs with new entries batched into a single Batch API call.

### 4.2 On-Demand Triggers

Some events are significant enough to trigger an immediate (non-batch) summarization:

- PC dies and respawns (major narrative beat)
- PC changes planet for the first time
- PC completes a Director-generated personal quest
- Admin command: `@narrative update <player>`

These use standard API calls (not batch), but should be rare — a few per day at most.

### 4.3 Summarization Prompt Template

```
You are a Star Wars campaign journal keeper for a tabletop RPG set during the
Galactic Civil War. Your job is to maintain two narrative records for a player
character based on their background and recent actions.

CHARACTER BACKGROUND (player-written, preserve tone and intent):
{player_background}

CURRENT LONG RECORD (your previous summary, may be empty for new characters):
{current_long_record}

NEW ACTIONS SINCE LAST UPDATE:
{action_log_entries}

CURRENT GAME STATE:
- Location: {current_planet}, {current_room}
- Credits: {credits}
- Active faction standings: {faction_standings}
- Days since character creation: {age_days}

Produce two outputs:

LONG_RECORD: (max 800 words)
Update the narrative record. Preserve the player's background faithfully.
Integrate new actions into the RECENT EVENTS section (keep last 14 days,
summarize older events into the character arc). Update RELATIONSHIPS if any
NPC interactions occurred. Update SKILL TRAJECTORY if training happened.
Add or update QUEST HOOKS — note unresolved threads, emerging patterns, or
narrative opportunities the Director could act on. Write in concise,
third-person campaign-journal style.

SHORT_RECORD: (max 150 words)
Distill the long record into a briefing card — what a well-connected NPC
in a cantina would know about this person. Focus on: name, species, visible
occupation, reputation, recent notable actions (last 3-5 days only), known
associates, any outstanding debts or conflicts. Do NOT include internal
motivations or quest hooks. Write as a dossier, not a story.

Respond in JSON:
{
  "long_record": "...",
  "short_record": "..."
}
```

### 4.4 Cost Estimate

| Component | Tokens In | Tokens Out | Cost/Call | Frequency | Monthly Cost |
|-----------|-----------|------------|-----------|-----------|-------------|
| Nightly batch (per PC) | ~1,500 | ~1,200 | $0.0075 | Daily | $0.225/PC |
| Batch API discount | — | — | 50% off | — | **$0.1125/PC** |
| Prompt caching (system prompt) | ~300 cached | — | 90% off input | — | Further savings |
| On-demand trigger | ~1,500 | ~1,200 | $0.0075 | ~2/day total | $0.45/month |

**Total for 20 active PCs**: ~$2.25 + $0.45 = **~$2.70/month**

---

## 5. Personalized Quest Generation

### 5.1 Integration with Director Faction Turn

The Director's faction turn prompt (§4 of director_ai_design_v1.md) is extended with an optional PC digest. When a PC is online, their short record is included in the digest. The Director can then reference PCs in its response.

**Extended faction turn JSON response**:
```json
{
  "influence_adjustments": [...],
  "narrative_event": {...} | null,
  "ambient_pool": [...] | null,
  "news_headline": "...",
  "pc_hooks": [
    {
      "char_id": 42,
      "hook_type": "personal_quest" | "rumor" | "encounter" | "opportunity",
      "content": "A Trandoshan matching the description of your cantina opponent was seen asking about you at the docking bays.",
      "delivery": "npc_whisper" | "comlink_message" | "news_item" | "ambient"
    }
  ] | null
}
```

**Constraint**: Max 2 `pc_hooks` per faction turn. The Director doesn't spam.

### 5.2 Quest Template System

Instead of letting Haiku write entire quest narratives (expensive, unpredictable), quests are generated as **structured templates** that the engine fills in.

**Quest template fields**:
```json
{
  "quest_id": "auto-generated",
  "title": "Unfinished Business",
  "type": "personal",
  "source_hook": "Trandoshan cantina brawl unresolved",
  "objective_type": "combat" | "delivery" | "investigation" | "social" | "escape",
  "objective_summary": "Confront or evade the Trandoshan bounty hunter",
  "target_npc": "generated or named",
  "location_zone": "docking_bays",
  "reward_credits": 800,
  "reward_reputation": {"faction": "criminal", "delta": 5},
  "difficulty_tier": "novice",
  "expiry_hours": 48,
  "prerequisites": {
    "min_skill": null,
    "required_item": null,
    "required_location": "tatooine"
  }
}
```

**Haiku generates the template**; the engine handles spawning, tracking, and completion — identical to the existing mission board pipeline. This keeps output tokens small and behavior predictable.

### 5.3 Quest Delivery Methods

| Method | Description | When |
|--------|-------------|------|
| `npc_whisper` | A known NPC approaches the PC with a whispered message | PC is in a room with the relevant NPC |
| `comlink_message` | Message arrives on PC's comlink channel | PC is online, any location |
| `news_item` | Appears in `news` feed with PC-relevant angle | Passive discovery |
| `ambient` | Room ambient text references something PC-specific | PC is in relevant zone |

**Delivery respects presence**: `npc_whisper` only fires if the PC is actually in the room with that NPC. If not, it downgrades to `comlink_message`.

### 5.4 Personal Quest Budget

Personal quests are generated via a **separate, lower-frequency call** — not every faction turn.

| Trigger | Frequency | Cost |
|---------|-----------|------|
| PC logs in with stale quest hooks (>24hr since last check) | Max 1/PC/day | ~$0.005/call |
| Director faction turn flags a PC hook | Max 2/faction turn | Included in faction turn call |
| PC completes a personal quest (generate follow-up) | Event-driven | ~$0.005/call |

**Monthly estimate for 20 active PCs**: ~$3.00/month (on top of the $2.70 for summarization).

---

## 6. Cost Mitigation Architecture

### 6.1 Strategy Summary

| Strategy | Savings | How |
|----------|---------|-----|
| **Batch API** for nightly summarization | 50% | Queue all PC summaries into one batch call |
| **Prompt caching** on system prompts | 90% on cached tokens | Summarization and quest prompts share a stable system prompt |
| **Template-driven quests** | ~70% output reduction | Haiku fills structured JSON, not freeform narrative |
| **Tiered triggers** | ~80% call reduction | Don't evaluate every PC every faction turn |
| **Mistral as gatekeeper** | Variable | Local model filters "is this interesting?" before API calls |
| **Cooldowns** | Prevents runaway | Max 1 summary + 1 quest check per PC per day (batch) |
| **Budget circuit breaker** | Hard cap | Existing Director budget tracker ($20/month cap) applies to all Haiku calls including narrative |

### 6.2 Mistral as First Filter

Before escalating to Haiku for quest generation, Mistral 7B performs a lightweight local check:

```
Given this PC's recent actions, is there a narratively interesting
unresolved thread? Answer YES or NO with a one-sentence reason.

Actions: {last_5_action_log_entries}
```

- If YES → escalate to Haiku for quest template generation
- If NO → skip this cycle, check again tomorrow

This keeps Haiku calls to only the PCs with genuinely interesting story threads. Mistral runs locally — zero API cost.

### 6.3 Budget Allocation

The existing Director budget is $20/month. Current Director usage is ~$6-8/month (48 calls/day × 30 days). The narrative memory system adds:

| Component | Monthly Cost |
|-----------|-------------|
| Nightly summarization (20 PCs, batch) | $2.25 |
| On-demand triggers | $0.45 |
| Personal quest generation | $3.00 |
| **Narrative system total** | **~$5.70** |
| **Existing Director usage** | **~$7.00** |
| **Combined total** | **~$12.70** |

Leaves ~$7.30 headroom under the $20 cap. Comfortable.

---

## 7. NPC Integration

### 7.1 NPC Dialogue (Mistral)

When a PC talks to an NPC via `talk`/`ask`, `npc_brain.py` already constructs a prompt with the NPC's personality. The short record is appended:

```
[Existing NPC personality prompt]

THE PERSON TALKING TO YOU:
{pc_short_record}

Respond in character. You may reference what you know about this person
if it's relevant, but don't force it. Not every conversation needs to
reference their history.
```

This costs zero additional API calls — Mistral is local. The short record adds ~200 tokens to the NPC prompt, well within budget.

### 7.2 Named NPC Memory

Future enhancement (post-v1): named NPCs (Wuher, Venn Kator, etc.) could maintain their own short memory of interactions with specific PCs. A `npc_pc_memory` table with 1-2 sentence entries per NPC-PC pair. Populated by Mistral after each conversation. This creates continuity — Wuher remembers you broke a glass last week.

---

## 8. DB Schema

```sql
-- Core narrative records
CREATE TABLE IF NOT EXISTS pc_narrative (
    char_id           INTEGER PRIMARY KEY REFERENCES characters(id),
    player_background TEXT    DEFAULT '',           -- Player-written, max 500 words
    long_record       TEXT    DEFAULT '',           -- Haiku-maintained, max 800 words
    short_record      TEXT    DEFAULT '',           -- Haiku-distilled, max 150 words
    last_summary_ts   REAL    DEFAULT 0,            -- Timestamp of last summarization
    last_quest_ts     REAL    DEFAULT 0,            -- Timestamp of last quest check
    created_at        REAL    NOT NULL
);

-- Append-only action log (input to summarization)
CREATE TABLE IF NOT EXISTS pc_action_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL REFERENCES characters(id),
    event_type      TEXT    NOT NULL,               -- combat, mission, smuggling, etc.
    event_summary   TEXT    NOT NULL,               -- One-line description
    event_data      TEXT    DEFAULT '{}',           -- JSON details
    summarized      INTEGER DEFAULT 0,             -- 0=pending, 1=included in summary
    created_at      REAL    NOT NULL
);

-- Personal quest tracking
CREATE TABLE IF NOT EXISTS personal_quests (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL REFERENCES characters(id),
    quest_data      TEXT    NOT NULL,               -- JSON quest template
    status          TEXT    DEFAULT 'offered',      -- offered, accepted, completed, expired, abandoned
    source_hook     TEXT    DEFAULT '',             -- What triggered this quest
    offered_at      REAL    NOT NULL,
    accepted_at     REAL,
    completed_at    REAL,
    expires_at      REAL
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_action_log_char ON pc_action_log(char_id, summarized);
CREATE INDEX IF NOT EXISTS idx_action_log_ts ON pc_action_log(created_at);
CREATE INDEX IF NOT EXISTS idx_personal_quests_char ON personal_quests(char_id, status);
```

---

## 9. Command Interface

### 9.1 Player Commands

| Command | Aliases | Description |
|---------|---------|-------------|
| `+background <text>` | `bg`, `+bg`, `setbg` | Set/replace player background (max 500 words) |
| `+background` | `bg`, `+bg` | View your current background |
| `+recap` | `recap`, `myhistory`, `+myhistory` | View your short record (what NPCs know about you) |
| `+quests` | `quests`, `pq`, `+pq`, `personalquests` | List active/available personal quests |
| `+quest <id>` | `quest` | View details of a specific personal quest |
| `questaccept <id>` | `acceptquest`, `pqaccept` | Accept a personal quest |
| `questcomplete` | `finishquest`, `pqcomplete` | Complete active personal quest (if objectives met) |
| `questabandon` | `abandonquest`, `pqdrop` | Abandon active personal quest |

### 9.2 Admin Commands

| Command | Description |
|---------|-------------|
| `@narrative status` | Show narrative system stats (PCs with records, log size, last batch) |
| `@narrative view <player>` | View a PC's full narrative records (background + long + short) |
| `@narrative update <player>` | Force immediate summarization for a PC |
| `@narrative reset <player>` | Clear a PC's narrative records (keeps background) |
| `@narrative log <player>` | View raw action log entries for a PC |
| `@narrative quest <player>` | Force quest generation check for a PC |

---

## 10. Implementation Drops

### Drop 1: Schema + Background Command
- `pc_narrative` table creation in DB init
- `pc_action_log` table creation
- `+background` command (set/view)
- `+recap` command (placeholder — shows background until summarization exists)

### Drop 2: Action Logging Hooks
- Wire action log inserts into: combat outcome, mission complete, bounty collect, smuggling deliver/dump, crafting complete, significant purchase, planet travel, skill training
- Each hook writes one row to `pc_action_log` with a concise `event_summary`
- No AI calls yet — just data collection

### Drop 3: Summarization Pipeline
- Nightly batch job in `engine/narrative.py`
- Haiku summarization call (system prompt + per-PC context)
- Short record + long record generation and storage
- `+recap` command now shows AI-generated short record
- Batch API integration

### Drop 4: Director Integration
- Extend faction turn digest with online PC short records
- Parse `pc_hooks` from Director response
- Deliver hooks via npc_whisper / comlink / ambient / news
- Mistral gatekeeper filter for quest escalation

### Drop 5: Personal Quest System
- `personal_quests` table
- Quest template generation via Haiku
- Quest commands: `+quests`, `+quest`, `questaccept`, `questcomplete`, `questabandon`
- Quest expiry and cleanup
- Integration with existing mission completion skill check engine

### Drop 6: NPC Short Record Injection
- Wire `pc_short_record` into `npc_brain.py` prompt construction
- Named NPC memory table (future prep, not fully wired)

---

## 11. Invariants

1. **Player background is sacred**: AI never overwrites `player_background`. It can summarize and reference it, but the original text is preserved verbatim.
2. **Short record = public knowledge**: Nothing in the short record should contain information an NPC couldn't plausibly know. No internal motivations, no quest hooks, no meta-game information.
3. **Director golden rule applies**: Personal quests create opportunities, never obligations. A PC can ignore every quest hook forever with no penalty.
4. **Budget cap is shared**: Narrative system calls count against the same $20/month Director budget. Circuit breaker applies.
5. **Graceful degradation**: If the API is down or budget is exhausted, NPCs simply don't reference PC history. The game works fine without it — it's a layer of polish, not a dependency.
6. **No mechanical advantage**: Personal quests reward the same credit/rep ranges as mission board jobs. They're *narratively* richer, not mechanically superior.
7. **Telnet parity**: All commands work identically on Telnet and WebSocket. Quest delivery via ambient/whisper uses standard broadcast — no web-only features.

---

## 12. Architecture Doc Changes (for v17)

**New section: §14B PC Narrative Memory System**
- Subsections: Two-Tier Records, Action Logging, Summarization Pipeline, Personal Quests
- References this design doc for full specification

**Modified: §13A Director AI System**
- Add: PC digest in faction turn prompt (online PCs' short records)
- Add: `pc_hooks` response field
- Note: Budget allocation now includes narrative system (~$5.70/month)

**Modified: §16 Completed Features** (when implemented)
- Add each drop as completed

**Modified: §17 Key Architecture Invariants**
- Add: "PC narrative records: two-tier (short for Mistral, long for Haiku). Player background never overwritten by AI."
- Modify AI budget line: "$20/month cap covers Director + Narrative Memory system"

---

*End of PC Narrative Memory & Personalized Quest System Design Document — Version 1.0*
*Reference: director_ai_design_v1.md, economy_design_v02-1.md, sw_d6_mush_architecture_v16.md*
