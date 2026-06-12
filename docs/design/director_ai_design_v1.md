# SW_MUSH — Director AI System
## Design Document v1.0
### April 2026 · BTGlass80 · WEG D6 R&E

---

## 1. Design Philosophy

SW_MUSH doesn't need an AI to narrate combat results or write player poses. MUSH culture has a golden rule: never step on a player's agency. The AI should never tell a player what they feel, what they do, or how their character reacts. Players pose for themselves.

What SW_MUSH *does* need is a **Director** — an invisible hand that watches the macro state of the galaxy and moves the unseen pieces on the board. The Director sets the stage. Players perform on it. This is the difference between a GM who tells you "you feel afraid" (bad) and a GM who says "the lights go out and you hear boots on the deck above" (good).

The Director operates at three levels, each with a different cadence and purpose:

| Level | Cadence | What It Does | Who Sees It |
|-------|---------|-------------|-------------|
| **Faction Turn** | Every 30 min | Evaluates world state, adjusts faction influence, sets zone alert levels | System-level; effects propagate to all players |
| **Narrative Events** | Threshold-triggered | Spawns narrative arcs (crackdowns, surges, auctions) when influence thresholds trip | Global news broadcast + zone-specific effects |
| **Atmospheric Layer** | Continuous | Dynamic ambient text pool that reflects current world state | Players in occupied rooms |

The Director never generates text that players must react to mechanically. It never forces a player into a scene. It creates *conditions* — a crackdown, a price shift, a rumor, a surge — and players choose whether and how to engage.

---

## 2. Why Not Just Use Timers?

The existing P6 Procedural World Events spec (arch doc v10 §14.6) uses random timers: "Imperial Checkpoint fires 1/2hr avg." That works, but it produces a world that feels random rather than reactive. An Imperial crackdown that fires because a dice roll hit is atmospheric. An Imperial crackdown that fires *because players spent the last 3 hours killing patrols* is storytelling.

The Director's core value proposition is **causality**. Player actions have visible, systemic consequences that other players can observe, discuss, and respond to. This is the "did you see what happened last night?" factor that drives MUSH social currency.

The timer-based events from P6 still exist as a fallback. If the API is unavailable or the budget circuit breaker trips, the game falls back to deterministic timer events. The Director *enhances* the timer system; it doesn't replace it.

---

## 3. Faction Influence Model

### 3.1 Zone Influence Scores

Each zone tracks influence scores for four factions. These are integers that shift based on player actions and Director decisions.

| Faction | Starting Influence (Mos Eisley) |
|---------|-------------------------------|
| Imperial | 60 |
| Rebel | 10 |
| Criminal | 50 |
| Independent | 30 |

Scores range 0–100 per faction per zone. They are *not* zero-sum — multiple factions can have high influence simultaneously (the Empire and the Hutts both have a strong grip on Mos Eisley in canon). The *relative* balance matters more than absolute values.

### 3.2 Player Actions That Shift Influence

| Action | Faction Effect | Amount |
|--------|---------------|--------|
| Kill Imperial NPC | Imperial −3, Rebel +1 | Per kill |
| Kill Criminal NPC | Criminal −2, Imperial +1 | Per kill |
| Complete Imperial mission | Imperial +2 | Per mission |
| Complete Rebel mission | Rebel +2, Imperial −1 | Per mission |
| Complete smuggling mission | Criminal +2, Imperial −1 | Per mission |
| Complete bounty (any) | Bounty Hunter Guild reputation; no zone influence | — |
| Sell contraband | Criminal +1 | Per transaction |
| Talk to faction NPC (Trusted+) | Faction +1 | Capped 3/day |

These deltas are small by design. A single player shouldn't flip a zone in one session. But a week of sustained anti-Imperial activity by 3–4 players should produce a visible shift.

### 3.3 Zone Alert Levels

Each zone has a derived alert level based on faction influence ratios. These are simple thresholds computed locally (no API call needed):

| Condition | Alert Level | Effects |
|-----------|-------------|---------|
| Imperial ≥ 70 | **Lockdown** | +50% docking fees, extra patrol spawns, smuggling pay +50% (risk premium) |
| Imperial 50–69 | **High Alert** | Normal patrols, occasional checkpoints |
| Imperial 30–49 | **Standard** | Normal operations |
| Imperial < 30 | **Lax** | −25% docking fees, reduced patrols, Criminal NPC density +25% |
| Criminal ≥ 70 | **Underworld** | Black market access, Hutt job board unlocks, Imperial bounties on players |
| Rebel ≥ 40 | **Unrest** | Rebel missions appear on board, propaganda ambient text |

Alert levels are recomputed every tick (1s) from the influence scores. No API call. The Director's job is to adjust the *scores*; the effects cascade automatically.

### 3.4 DB Schema Addition

```sql
CREATE TABLE IF NOT EXISTS zone_influence (
    zone_id TEXT NOT NULL,
    faction TEXT NOT NULL,     -- 'imperial', 'rebel', 'criminal', 'independent'
    score INTEGER DEFAULT 0,
    last_updated TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (zone_id, faction)
);

CREATE TABLE IF NOT EXISTS director_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    event_type TEXT NOT NULL,   -- 'faction_turn', 'narrative_event', 'atmosphere_refresh'
    summary TEXT,               -- Human-readable summary for news board / admin review
    details_json TEXT,          -- Full JSON payload from API response
    token_cost_input INTEGER DEFAULT 0,
    token_cost_output INTEGER DEFAULT 0
);
```

The `director_log` table serves triple duty: budget tracking, admin audit trail, and source data for the `news` command. The world events board reads the most recent `director_log` entries with `event_type = 'narrative_event'`.

---

## 4. The Faction Turn

### 4.1 Cadence

Every 30 minutes, triggered from the tick loop. A counter increments each tick; at 1800 ticks (30 min), the Director fires. If an API call is in-flight, skip until next cycle.

### 4.2 The Digest

The Director compiles a world-state digest from live data. This is the *only* data the API sees — a compressed JSON payload, not raw game state.

```json
{
  "time_period": "last_30_minutes",
  "zone_influence": {
    "cantina": {"imperial": 55, "rebel": 12, "criminal": 60, "independent": 30},
    "spaceport": {"imperial": 65, "rebel": 8, "criminal": 45, "independent": 25}
  },
  "player_actions": [
    {"type": "kill", "target_faction": "imperial", "zone": "spaceport", "count": 3},
    {"type": "mission_complete", "mission_type": "smuggling", "zone": "docking", "count": 2},
    {"type": "bounty_claimed", "tier": 3, "zone": "outskirts", "count": 1}
  ],
  "active_events": ["imperial_crackdown_spaceport"],
  "player_count": 4,
  "recent_news": ["Pirate Viper destroyed in grid 7-3", "Bounty on Vexx claimed"]
}
```

Target payload size: 300–500 input tokens. Lean and structured.

### 4.3 The System Prompt

The Director's system prompt is static (cacheable) and defines its role, personality, and output constraints:

```
You are the Director AI for a Star Wars MUSH set in Mos Eisley, Tatooine.
Your role is to evaluate the current state of the galaxy and decide what
happens next at the MACRO level. You never narrate player actions or
describe what individual characters do. You move the unseen pieces:
faction responses, economic shifts, atmospheric changes, and emerging
threats.

You are guided by these principles:
- The Empire reacts to resistance with escalation, not retreat.
- The criminal underworld fills any vacuum the Empire leaves.
- The Rebel Alliance operates in shadows; their influence is felt
  through sabotage and propaganda, not open warfare on Tatooine.
- Tatooine is a backwater. The Empire cares about order, not ideology.
  The Hutts care about profit. Neither wants open war here.
- Events should create OPPORTUNITIES for players, never OBLIGATIONS.
- Consequences should feel proportional and narratively logical.

Respond with ONLY a JSON object in this exact format:
{
  "influence_adjustments": [
    {"zone": "...", "faction": "...", "delta": <int>}
  ],
  "narrative_event": {
    "type": "...",
    "headline": "...",
    "duration_minutes": <int>,
    "zones_affected": ["..."],
    "mechanical_effects": {"...": "..."}
  } OR null,
  "ambient_pool": ["line1", "line2", "line3"] OR null,
  "news_headline": "One-sentence summary for the world events board."
}
```

### 4.4 What the Director Can Return

**influence_adjustments**: Small nudges (±1 to ±5) to zone influence scores. The Director sees the player action digest and decides how the *galaxy* responds. If players killed 3 Imperial patrols, maybe Imperial influence drops −2 in that zone but +3 in an adjacent zone (reinforcements inbound). This is where causality lives.

**narrative_event**: An optional structured event to activate. Types map to the P6 event table (imperial_crackdown, bounty_surge, merchant_arrival, sandstorm, cantina_brawl, distress_signal, krayt_sighting, hutt_auction). The Director picks the *type* and affected zones; the game engine handles spawning, mechanical effects, and duration tracking. The Director does NOT invent new event types — it selects from a fixed menu. This is the bounded context principle applied to the Director.

**ambient_pool**: 3–5 optional dynamic ambient lines reflecting the current state. These supplement (not replace) the static YAML ambient pool. If Imperial influence is high, lines about nervous patrons and stormtrooper patrols. If Criminal influence is surging, lines about shady deals and Hutt enforcers. Injected into the room's ambient rotation for the next 30-minute cycle.

**news_headline**: A one-sentence summary for the `world_events` table. Always generated. This is what players see when they type `news`.

### 4.5 Parsing and Validation

The response is parsed as JSON. Every field is validated against known enums and ranges:

- `influence_adjustments`: delta clamped to ±5, zone must be in VALID_ZONES, faction must be in VALID_FACTIONS
- `narrative_event.type`: must be in EVENT_TYPES frozenset
- `narrative_event.duration_minutes`: clamped to 15–120
- `ambient_pool`: each line max 120 chars, stripped of anything that looks like a player name or game command
- `news_headline`: max 200 chars

If JSON parsing fails, or validation rejects the payload, the turn is logged as a no-op and the timer resets. The world doesn't change. This is the graceful failure mode.

---

## 5. Narrative Events

### 5.1 Event Types (Fixed Menu)

The Director selects from this menu. It cannot invent new types. The engine knows how to run each one.

| Type | Spawns | Duration | Mechanical Effect |
|------|--------|----------|-------------------|
| `imperial_crackdown` | Extra patrols in zone | 30–60 min | Smuggling pay +50%, patrol aggro radius doubled |
| `imperial_checkpoint` | Patrol NPC in one room | 15–30 min | Contraband scan on entry, fine if caught |
| `bounty_surge` | Nothing new | 30 min | Bounty board rewards ×2 |
| `merchant_arrival` | Temp vendor NPC | 20 min | Rare/discounted items |
| `sandstorm` | Nothing | 10–20 min | Outdoor rooms: Perception −1D |
| `cantina_brawl` | Brawler NPC | 5 min | Small credit/XP reward for participation |
| `distress_signal` | NPC ship in space | 15 min | Rescue for rep/credits |
| `pirate_surge` | Extra pirates | 60–120 min | 3× pirate spawn rate |
| `hutt_auction` | Temp vendor | 30 min | Rare items, Criminal rep gate |
| `krayt_sighting` | High-tier bounty NPC | 45 min | Group content, big reward |
| `rebel_propaganda` | Nothing | 30 min | Rebel ambient text, +1 Rebel influence/tick in zone |
| `trade_boom` | Nothing | 60 min | Vendor sell prices +25% in zone |

### 5.2 Event Lifecycle

1. Director returns a `narrative_event` in its Faction Turn response
2. `engine/director.py` validates the event type and parameters
3. `engine/world_events.py` activates the event (identical path to timer-triggered events)
4. Event broadcasts announcement to all online players via comlink channel
5. Event runs for its duration, applying mechanical effects
6. On expiry, event cleans up (despawns NPCs, removes modifiers)
7. Event logged to `director_log` and `world_events` tables

### 5.3 Event Constraints

- Maximum 2 concurrent narrative events globally (prevents chaos)
- Minimum 15 minutes between Director-spawned events (cooldown)
- Same event type cannot repeat within 2 hours
- Events never hard-block player progress (fines, not imprisonment)

---

## 6. Atmospheric Layer

### 6.1 Two-Pool Ambient System

The ambient events system (already specced in the handoff brief) fires flavor text every 2–5 minutes per occupied room. The Director extends this with a *dynamic pool* alongside the static YAML pool.

**Static pool** (`data/ambient_events.yaml`): Hand-authored, always available, zero API dependency. ~10 lines per zone. This is the floor — the world always breathes even if the API is down.

**Dynamic pool** (Director-generated): 3–5 lines per cycle, reflecting current world state. Rotated every 30 minutes on the Faction Turn. Stored in memory (transient, like ChannelManager). If empty, the system draws exclusively from the static pool.

When the ambient timer fires for a room:
1. 70% chance: draw from static pool for that zone
2. 30% chance: draw from dynamic pool (if non-empty), else static

This ratio keeps the dynamic text feeling like a spice, not the main flavor. Players should not notice the AI generating text — it should feel like the world naturally reacting.

### 6.2 Content Safety

Dynamic ambient lines are validated before entering the pool:

- Max 120 characters (one line of terminal text)
- No player character names (checked against online player list)
- No game commands or mechanical language ("roll", "attack", "skill check")
- No anachronisms (the system prompt handles this, but a simple keyword filter catches obvious failures)
- No quotes from copyrighted Star Wars media

Lines that fail validation are silently dropped. The static pool fills any gaps.

---

## 7. Claude API Integration

### 7.1 Model Selection

**Haiku 4.5** is the right model for this workload. The Director needs structured JSON output from a compressed data payload — this is exactly Haiku's sweet spot. It doesn't need extended thinking or deep reasoning. It needs speed, reliability, and consistent JSON formatting.

Current pricing: $1/MTok input, $5/MTok output.

### 7.2 Budget Math ($20/month)

| Call Type | Frequency | Input Tokens | Output Tokens | Cost/Call | Monthly Cost |
|-----------|-----------|-------------|---------------|-----------|-------------|
| Faction Turn | 48/day (every 30 min) | ~600 (system prompt cacheable) | ~300 | ~$0.002 | ~$2.88 |
| Prompt cache writes | 48/day | ~400 (system prompt) | — | ~$0.0005 | ~$0.72 |
| **Total Director** | | | | | **~$3.60/mo** |

With prompt caching (system prompt is static, cache hit at 10% of input cost), the effective monthly cost is approximately **$3–4/month** for the Director running 24/7.

This leaves **$16–17/month** of budget headroom for future expansions: named NPC dialogue upgrades, dynamic mission briefings, or increasing the Faction Turn frequency.

### 7.3 Provider Architecture

New file: `ai/claude_provider.py`

```python
class ClaudeProvider(AIProvider):
    """Anthropic Claude API provider with budget tracking."""

    def __init__(self, api_key, model="claude-haiku-4-5-20251001",
                 monthly_budget_cents=2000):
        self.api_key = api_key
        self.model = model
        self.monthly_budget_cents = monthly_budget_cents
        self._month_key = ""           # "2026-04"
        self._month_spent_cents = 0.0
        self._lock = asyncio.Lock()

    async def generate(self, system_prompt, messages, **kwargs):
        if self._is_over_budget():
            return ""  # Graceful fallback
        # ... aiohttp POST to api.anthropic.com/v1/messages
        # Track token usage from response headers/body
        # Update _month_spent_cents

    def _is_over_budget(self):
        current_month = datetime.now().strftime("%Y-%m")
        if current_month != self._month_key:
            self._month_key = current_month
            self._month_spent_cents = 0.0
        return self._month_spent_cents >= (self.monthly_budget_cents * 0.9)
        # 90% threshold — leaves 10% buffer for in-flight requests
```

Integrates into the existing `AIManager` as a new provider alongside `OllamaProvider` and `MockProvider`. The Director calls `ai_manager.generate(provider="claude")` explicitly — it never routes through the default Ollama path.

### 7.4 Circuit Breaker

The budget circuit breaker is non-negotiable. When the monthly spend hits 90% of budget:

1. All Director API calls return empty (no-op)
2. Faction Turn falls back to deterministic timer-based events (P6 spec)
3. Dynamic ambient pool freezes (last generated set persists until manual reset or month rollover)
4. Admin alert broadcasts: `[SYSTEM] Director AI budget threshold reached. Falling back to timer events.`
5. `@ai status` command shows current month spend and remaining budget

The budget resets on the 1st of each month (UTC). No carry-over.

### 7.5 Configuration

All Director settings in a config block (environment variables or config file):

```python
@dataclass
class DirectorConfig:
    enabled: bool = False              # Off by default until API key configured
    api_key: str = ""                  # ANTHROPIC_API_KEY
    model: str = "claude-haiku-4-5-20251001"
    monthly_budget_cents: int = 2000   # $20.00
    faction_turn_interval: int = 1800  # seconds (30 min)
    max_concurrent_events: int = 2
    event_cooldown: int = 900          # seconds (15 min) between Director events
    fallback_to_timers: bool = True    # Use P6 timer events when API unavailable
    dynamic_ambient_ratio: float = 0.3 # 30% dynamic, 70% static ambient
```

---

## 8. Interaction with Existing Systems

### 8.1 Systems the Director Reads (Input)

| System | Data Used | How |
|--------|-----------|-----|
| `world_events` table | Recent player actions | Query last 30 min of events |
| `zone_influence` table | Current faction scores | Direct read |
| `missions` table | Completed missions by type | Count by type/zone |
| `bounties` table | Claimed bounties | Count by tier |
| Kill hook (`combat_commands.py`) | NPC kills by faction | Increment counter in memory |
| `session_mgr` | Online player count | `len(sessions)` |

### 8.2 Systems the Director Writes (Output)

| System | What Changes | How |
|--------|-------------|-----|
| `zone_influence` table | Faction scores | Direct DB update |
| `world_events` / `engine/world_events.py` | Narrative events | Activate event by type |
| Ambient pool (`engine/ambient_events.py`) | Dynamic ambient lines | Replace in-memory dynamic pool |
| `director_log` table | Audit trail + news source | Insert row |
| `news` command | Player-visible world events | Reads `director_log` |
| NPC space traffic (`npc_space_traffic.py`) | Spawn rate modifiers | Zone alert level affects spawn weights |
| Mission board (`missions.py`) | Type weighting | Zone alert level biases mission type selection |
| Economy (vendor prices) | Docking fees, sell prices | Zone alert level applies multiplier |

### 8.3 Systems the Director Never Touches

- **Player poses or actions**: Never
- **Combat resolution**: Never
- **Dice rolls**: Never
- **Individual NPC dialogue**: Never (that's Ollama's job via `npc_brain.py`)
- **Character sheets or inventory**: Never
- **Room descriptions**: Never (but dynamic ambient *supplements* them)

---

## 9. The `news` Command

The world events board is a direct consumer of Director output. It already existed in the engagement doc spec as a lightweight feature; the Director gives it meaningful content.

```
> news

=== Mos Eisley Galactic News Network ===

  [2 hours ago]  Imperial reinforcements deployed to the Spaceport
                 district following a wave of attacks on patrol units.
  [4 hours ago]  A rare weapons merchant was spotted in Docking Bay 87.
                 The merchant departed after 20 minutes.
  [Yesterday]    Bounty on Vexx the Devaronian was collected by Kira Senn.
  [Yesterday]    Criminal activity in the Market District reached a
                 three-month high according to Imperial sources.
  [2 days ago]   A sandstorm swept through the Outskirts, grounding
                 all surface traffic for 15 minutes.
```

The `news_headline` from each Faction Turn is inserted into `director_log`. The `news` command queries the 10 most recent entries. Player-action events (kills, bounty claims, mission completions) are also inserted directly by their respective hooks, independent of the Director.

---

## 10. Admin Commands

```
@director status     — Show Director state: enabled, budget, last turn, 
                       active events, zone influence summary
@director enable     — Enable Director (requires API key in config)
@director disable    — Disable Director, fall back to timer events
@director trigger    — Force an immediate Faction Turn (debug/testing)
@director budget     — Show monthly spend, remaining budget, call count
@director influence  — Show full zone influence table
@director log [n]    — Show last N director_log entries (default 5)
@director reset      — Reset all zone influence to starting values
```

---

## 11. Implementation Plan

### Files to Create

| File | Contents |
|------|----------|
| `ai/claude_provider.py` | ClaudeProvider class with budget tracking |
| `engine/director.py` | DirectorAI singleton, Faction Turn logic, digest compiler |
| `engine/world_events.py` | WorldEventManager, event lifecycle, timer fallback |
| `engine/ambient_events.py` | AmbientEventManager, static + dynamic pool |
| `data/ambient_events.yaml` | Static ambient lines (~10 per zone, 7 zones) |
| `parser/director_commands.py` | Admin commands for Director management |
| `parser/news_commands.py` | `news` command |

### Files to Modify (via patch)

| File | Changes |
|------|---------|
| `ai/providers.py` | Add ClaudeProvider to AIManager provider registry |
| `db/database.py` | Add zone_influence + director_log table DDL and CRUD methods |
| `server/game_server.py` | Wire Director tick, ambient tick, news command registration |
| `engine/npc_space_traffic.py` | Read zone alert level for spawn weight modifiers |
| `engine/missions.py` | Read zone alert level for mission type bias |
| `parser/combat_commands.py` | Add faction kill counter increment to kill hook |

### Delivery Sequence

1. **Drop 1**: `data/ambient_events.yaml` + `engine/ambient_events.py` + wire patch — delivers the static ambient system immediately (zero API dependency, instant atmosphere)
2. **Drop 2**: `engine/world_events.py` + wire patch — timer-based P6 events (deterministic fallback, no API)
3. **Drop 3**: DB schema additions (zone_influence, director_log) + `engine/director.py` (digest compiler, influence model, local alert level computation) — all local logic, no API yet
4. **Drop 4**: `ai/claude_provider.py` + Director API integration + `parser/director_commands.py` + `parser/news_commands.py` — the full Director goes live
5. **Drop 5**: System integration patches (space traffic, missions, economy modifiers reading alert levels)

Each drop is independently useful. Drop 1 alone is the "highest atmosphere-per-engineering-hour" item from the engagement doc. Drops 1–3 work without any API key. Drop 4 lights up the intelligence layer.

---

## 12. Future Expansion (Post-Director v1)

These are explicitly out of scope for v1 but designed to plug into the Director architecture:

**Named NPC Dialogue Upgrade**: Route Tier 2/3 NPC `talk`/`ask` commands through ClaudeProvider instead of Ollama. The Director's zone influence and alert level feed into the NPC system prompt, so named NPCs react to the political climate. Budget impact: ~$2–5/month additional depending on player interaction volume.

**Dynamic Mission Briefings**: When `engine/missions.py` generates a new mission, pass the zone state to Claude for a one-paragraph narrative briefing instead of a template string. Budget impact: ~$1–2/month.

**Faction Mail**: When a player crosses a reputation threshold, the Director generates a personalized async mail from a faction leader. Budget impact: negligible (< $0.50/month).

**Multi-Planet Expansion**: When the game adds a second planet, the Director's zone_influence model extends naturally — new zone IDs, same schema. The system prompt gains a paragraph about the new planet's political dynamics.

**Escalation Arcs**: Multi-day narrative arcs where the Director tracks a "tension" counter that builds across Faction Turns. At threshold, a major event fires (Star Destroyer arrives, Hutt war erupts). This is the "Fronts" concept from Gemini's suggestion, but constrained to the fixed event menu.

---

## 13. What I Changed from Gemini's Suggestions

For transparency, here's where this design diverges from the Gemini conversation:

| Gemini Suggested | This Design | Why |
|-----------------|-------------|-----|
| AI narrates skill check results | Explicitly excluded | MUSH culture: players pose for themselves |
| "Scene Pacing" — AI monitors party chat and drops complications | Excluded | Steps on player agency; Director operates at macro level only |
| `look` command override with AI-generated descriptions | Excluded | Players expect `look` to return canonical room desc; dynamic ambient supplements it instead |
| Store AI-generated strings in ambient_events.yaml | Dynamic pool in memory | Don't mix AI output with hand-authored YAML; keep separation of concerns |
| Claude 3.5 Haiku pricing ($0.25/$1.25) | Claude Haiku 4.5 ($1/$5) | Gemini used outdated pricing. Corrected budget math still works within $20/month. Haiku 3 retires April 19, 2026. |
| 50,000–75,000 API calls/month on $20 | ~1,440 calls/month (48/day) | Director is low-frequency, high-value. Quality over quantity. Budget headroom preserved for future features. |
| Hourly Faction Turn | Every 30 minutes | 30 min is responsive enough for a 5–50 player population without being wasteful. Configurable. |
| Free-form AI event generation | Fixed event type menu | Bounded context principle: Director selects from known types, engine handles mechanics. Prevents hallucinated game mechanics. |
| No circuit breaker detail | Full budget tracking with 90% threshold + graceful fallback | Non-negotiable for a hobby project with a real-dollar budget |

---

## 14. Architecture Doc v12 Changes

The following sections should be added/modified in the architecture document for v12:

**New section: §15 Director AI System**
- Subsections: Faction Influence Model, Faction Turn, Narrative Events, Atmospheric Layer, Claude API Integration
- References this design doc for full specification

**Modified: §3 AI Intent Pipeline / Provider Abstraction**
- Add ClaudeProvider to the provider table
- Note: Director uses claude provider explicitly; NPC dialogue remains on Ollama

**Modified: §12 Economy System**
- Add zone alert level modifiers to docking fees and vendor prices
- Note: Director-driven economic effects are temporary and zone-scoped

**Modified: §14.6 Procedural World Events**
- Status change: TODO → IN PROGRESS
- Note: Timer-based events serve as deterministic fallback; Director provides intelligent event selection when API is available

**Modified: §16 Roadmap**
- New priority: P10 Director AI System
- Dependencies: ambient events (P6 partial), world events board, zone_influence schema

**Modified: §17 Key Architecture Invariants**
- Add: "AI model (Director): Claude Haiku 4.5 via API. $20/month budget cap. Graceful fallback to timer events."
- Add: "Zone influence: DB-backed (zone_influence table). Persists across restarts."
- Modify AI model line: "AI model (NPC): Mistral 7B only. RTX 3070 8GB VRAM. No 24B." (clarify scope)

**New: §18 Data Files update**
- Add `data/ambient_events.yaml` to the data files table

---

*End of Director AI Design Document — Version 1.0*
*Reference: sw_d6_mush_architecture_v11.md, sw_mush_engagement.docx, economy_design_v02-1.md*
