# Ambient NPC Life — Design v1 (POST-LAUNCH)

**Status:** DESIGN ONLY — post-launch feature. No engine code in this doc.
**Requested by:** Brian, 2026-06-13.
**Author:** Claude Opus 4.8 (main session), grounded against HEAD.
**Build posture:** design now → land inert DB scaffolding PRE-launch (so
no risky migration on a live DB) → build the sim POST-launch.

---

## 1. The pitch (Brian's words, captured)

Make the world feel alive: NPCs have **goals**, **interact with each
other**, and **move through the environment** as background flavor.
Driven by the **Ollama idle queue** so it never competes with PC-facing
Ollama work. **No unprompted PC interaction** in v1 — NPCs are
*observable* (you walk in on a conversation, see one travel through), but
the sim never *targets* a player. As much logic in **Python** as
possible; Ollama only for flavor, invoked last. Needs a DB for goal/
activity state. Be very careful about live-game impact (it's
post-launch) — hence: design first, build the DB hooks early.

## 2. Why this is buildable as an EXTENSION (not a new system)

Verified against HEAD — the substrate already exists:

| Need | Existing seam (HEAD) | Posture |
| --- | --- | --- |
| Lowest-priority, preemptible Ollama | **`engine/idle_queue.py`** — already has per-task priority (1–4), a 5s backoff after any player request (`BACKOFF_SECONDS`), a 200-task cap, `notify_player_request()` preemption, and an `AmbientBarkTask` precedent | **EXTEND** — add an `AmbientLifeTask` at a priority *below* every existing task |
| Background scheduler | **`server/tick_scheduler.py`** — unified interval+offset registry; `npc_space_traffic_tick`, `world_events_tick`, `director_tick`, `idle_queue_tick` already registered | **EXTEND** — register one `ambient_npc_life_tick` sibling (interval ≈300, offset to avoid pile-up) |
| NPC movement pattern | **`engine/npc_space_traffic.py`** — zone-based traffic manager: NPC ships move between adjacent zones on tick timers, archetype behaviors, a singleton `tick(db, session_mgr)` | **MIRROR** — a ground analogue that transitions `npcs.room_id` between connected rooms |
| Forward-compat DB | JSON catch-all columns are idiomatic here (`characters.attributes`, `rooms.properties`, **`npcs.ai_config_json`**, `npc_memory.memory_json`, …); additive `PRAGMA user_version` migrations (`SCHEMA_VERSION` currently 43) | **REUSE** `ai_config_json` for config + **one new state table** with a JSON `extra` column |
| Macro world state | **`engine/world_events.py`** singleton (crackdowns, surges, merchant arrivals) | **SIT BESIDE** — world-events are macro/player-facing drama; ambient-life is micro/background churn. Optional future read-coupling (a trade boom nudges merchant goals). |

Nothing here is a new top-level system. That matters for the "extend,
don't add" invariant and for keeping launch risk near zero.

## 3. Architecture — three layers, Ollama last

```
┌─────────────────────────────────────────────────────────────┐
│ LAYER 3 — FLAVOR (Ollama, idle queue, lowest priority)        │
│   Generate a LINE for an interaction the sim already decided.  │
│   Fully preemptible. If Ollama is busy → no line, NPCs still   │
│   move + act silently. Never blocks a PC.                      │
├─────────────────────────────────────────────────────────────┤
│ LAYER 2 — SIM (pure Python, deterministic, on the tick)       │
│   Goal selection, scheduling, movement, NPC-NPC interaction    │
│   resolution. Testable without Ollama. THIS is most of the     │
│   code (Brian's "Python before Ollama" requirement).          │
├─────────────────────────────────────────────────────────────┤
│ LAYER 1 — STATE (DB)                                           │
│   Persistent goals, schedules, current activity, relationships.│
│   Survives restart so the world is consistent + resumable.     │
└─────────────────────────────────────────────────────────────┘
```

**The load-bearing rule (Brian's): Layer 2 decides; Layer 3 only
decorates.** Example — a barter interaction: Layer 2 (Python) picks two
co-located NPCs with compatible goals, rolls the outcome, updates state.
ONLY THEN does Layer 2 enqueue a Layer-3 task to generate the spoken
line. If that task never runs (Ollama saturated by players), the trade
still happened; observers just don't see dialogue. The world stays
consistent regardless of Ollama load.

### 3.1 Preemption guarantee (the "never impact PC-facing Ollama" promise)

`AmbientLifeTask` is enqueued at a priority **strictly below** every
current idle task (barks, scene summaries, event rewrites, housing). The
idle queue already backs off 5s after any player request and processes
≤1 task/tick. So ambient flavor only generates in genuine idle gaps, and
PC `talk` (which bypasses the queue entirely and calls the provider
directly) is never behind ambient work. **The sim tick (Layer 2) does
NOT call Ollama** — it only enqueues optional Layer-3 tasks — so the
world-simulation cadence is independent of Ollama availability.

## 4. The sim (Layer 2) — what NPCs actually do in v1

Deliberately small for v1, all deterministic Python:

- **Goals:** each ambient-enabled NPC carries a small goal set
  (`work`, `socialize`, `patrol`, `rest`, `trade`) with a time-of-day
  schedule (reuse the existing day/night tick). A goal resolves to a
  *destination room* + an *activity*.
- **Movement:** mirror `npc_space_traffic`'s timer model on the ground —
  an NPC with a destination transitions `room_id` along connected rooms
  over a move-duration. Movement is announced to the *rooms involved*
  (departure/arrival lines), never to a targeted player.
- **NPC-NPC interaction:** when two ambient NPCs share a room and their
  goals are compatible (two `socialize`, a `trade` + a merchant), Layer 2
  rolls a short interaction (a chat, a haggle), updates any relationship
  state, and enqueues an optional Layer-3 line.
- **Observability, not targeting:** a PC in the room sees the ambient
  output (the two NPCs talking, an NPC passing through). The sim never
  reads "is a specific PC here and what do they want" — PCs are scenery
  to the sim, exactly inverting the normal NPC-serves-PC relationship.
  This is the v1 safety boundary.

**Explicitly OUT of v1** (future increments, flagged so scope is clear):
NPCs initiating contact with PCs; combat/economy *effects* from ambient
acts (an ambient trade must NOT move real market prices in v1 — flavor
only); cross-zone travel; faction-politics simulation.

## 5. DB design (Layer 1) — with the pre-launch scaffolding plan

Per Brian: **land the schema PRE-launch (inert), build the sim
post-launch** — so we never migrate a live DB with players in it. And
per Brian's future-proofing instinct, every new table carries a JSON
`extra` column from day one (the SQLite-idiomatic "blank" — new fields
go into JSON with zero migration, exactly like `characters.attributes`).

### 5.1 Config — reuse `npcs.ai_config_json` (no schema change)

Ambient config rides the existing JSON column (forward-compat already):

```jsonc
// npcs.ai_config_json (additive keys; absent = NPC is not ambient)
{
  "personality": "...", "faction": "...",   // existing
  "ambient_enabled": true,                    // opt-in (default false)
  "ambient_home_room": "mos_eisley_cantina",  // anchor it returns to
  "ambient_routine": "merchant_dayshift",     // named schedule template
  "ambient_goals": ["work", "socialize"]      // allowed goal set
}
```

Defaulting `ambient_enabled` absent/false means **every existing NPC is
unchanged** until explicitly opted in — a critical live-safety property.

### 5.2 Runtime state — ONE new table (the pre-launch migration)

```sql
-- Migration vNN (land PRE-launch, inert until the sim ships).
CREATE TABLE IF NOT EXISTS npc_ambient_state (
    npc_id          INTEGER PRIMARY KEY REFERENCES npcs(id),
    current_goal    TEXT DEFAULT '',          -- e.g. "socialize"
    current_room_id INTEGER REFERENCES rooms(id),
    dest_room_id    INTEGER REFERENCES rooms(id),  -- null = not moving
    move_started_at REAL,                      -- unix epoch
    move_duration   REAL,                      -- seconds
    last_tick_at    REAL,                       -- last sim evaluation
    activity        TEXT DEFAULT '',           -- current verb (display)
    extra           TEXT DEFAULT '{}'          -- JSON future-proof blank
);
CREATE INDEX IF NOT EXISTS idx_npc_ambient_room
    ON npc_ambient_state(current_room_id);

-- Relationships (NPC-NPC affinity that interactions nudge). Optional in
-- v1; can ship empty + populated lazily. Carries its own JSON blank.
CREATE TABLE IF NOT EXISTS npc_ambient_relationship (
    npc_id_a   INTEGER NOT NULL REFERENCES npcs(id),
    npc_id_b   INTEGER NOT NULL REFERENCES npcs(id),
    affinity   INTEGER DEFAULT 0,              -- -100..100
    extra      TEXT DEFAULT '{}',              -- JSON future-proof blank
    PRIMARY KEY (npc_id_a, npc_id_b)
);
```

**Why this is live-safe to land pre-launch:** both tables are NEW (no
ALTER on a hot table), empty, and read by NOTHING until the sim ships.
A `CREATE TABLE IF NOT EXISTS` migration on an empty-of-this-table DB is
the lowest-risk migration class there is. Post-launch, the sim is pure
feature code against an already-present schema — no migration races a
live player.

### 5.3 On Brian's "blanks" question — the right pattern

Brian's telemetry-style future-proofing instinct is correct; the
SQLite-idiomatic form is the **JSON `extra` column**, NOT reserved empty
typed columns (`spare_int_1`, …). Reasons:
- New fields go into `extra` JSON with **zero migration** — that IS the
  "blank space," and it's unlimited + self-describing.
- SQLite `ALTER TABLE ADD COLUMN` is cheap if a field ever genuinely
  needs to be a real indexed column — so reserved typed blanks buy
  nothing and add untyped clutter.
- It matches the codebase's own convention (`characters.attributes`,
  `rooms.properties`, `npcs.ai_config_json`, `missions.data`, …).
- **Policy recommendation (general, not just this feature):** every new
  table gets a nullable `extra TEXT DEFAULT '{}'` JSON column at
  creation. Cheap insurance, no downside.

## 6. Phased build plan

- **Phase 0 — PRE-LAUNCH (small, own drop, Brian sign-off):** land the
  two `CREATE TABLE` migrations (§5.2) + the `npc_ambient_state` accessor
  stubs in `db/database.py`. Inert: no tick handler, no reader. A test
  asserts the tables exist + the schema version bumped. **This is the
  only thing that touches the live DB, and it does so while it's safe.**
- **Phase 1 — POST-LAUNCH, sim core (Python only, no Ollama):** the
  Layer-2 sim — goals, schedules, ground movement (mirror
  `npc_space_traffic`), the `ambient_npc_life_tick` handler. NPCs move +
  act silently (departure/arrival/activity lines are templated Python
  strings, not Ollama). Fully testable offline. Opt-in via
  `ambient_enabled` on a handful of NPCs first.
- **Phase 2 — POST-LAUNCH, NPC-NPC interaction (Python):** co-located
  goal-compatible NPCs run short interactions; relationship state.
  Still templated strings.
- **Phase 3 — POST-LAUNCH, Ollama flavor (Layer 3):** add
  `AmbientLifeTask` to the idle queue; the sim enqueues optional
  line-generation for interactions/arrivals. Preemptible; degrades to
  Phase-2 templated strings when Ollama is busy.
- **Phase 4+ (deferred, design later):** world-event coupling; richer
  schedules; the (carefully gated, opt-in) question of any PC-facing
  ambient interaction — out of scope until v1 proves safe and fun.

## 7. Live-safety checklist (because it's post-launch)

- `ambient_enabled` defaults false → zero behavior change for existing
  NPCs until explicitly opted in.
- The sim NEVER calls Ollama on the tick path; Ollama is optional Layer-3
  decoration only. World cadence independent of Ollama load.
- `AmbientLifeTask` priority below all existing idle tasks; PC `talk`
  bypasses the queue → ambient flavor can never delay a player.
- Ambient acts produce NO mechanical effects in v1 (no market/combat/
  faction state changes) — pure flavor. (Faucet/sink discipline: an
  ambient "trade" mints/sinks nothing.)
- DB scaffolding lands pre-launch (empty `CREATE TABLE`), so the
  post-launch build never migrates a live, populated DB.
- world-events singleton reset-between-tests discipline applies to any
  ambient-life singleton too (test isolation).
- Per-tick work is bounded (process N NPCs/tick, not all) so a large NPC
  population can't spike a tick.

## 8. Open design calls for Brian (when this comes off the shelf)

1. **Movement scope:** intra-zone only (NPC wanders its building/
   district) vs. cross-zone travel. Rec: intra-zone for v1 (simpler,
   safer, still feels alive).
2. **Population cap:** how many NPCs are ambient-enabled at once
   (per-room + global caps for tick budget). Rec: start tiny (a few
   per hub) and widen with telemetry.
3. **Observability surface:** do ambient lines go to the room channel,
   a dedicated ambient channel, or only on `look`? Rec: room channel,
   rate-limited, suppressible by a player pref.
4. **The PC-interaction boundary:** confirmed OUT for v1; revisit only
   after v1.
