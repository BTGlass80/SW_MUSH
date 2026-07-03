# Ambient NPC Life — Design v2 (POST-LAUNCH)

**Status:** DESIGN ONLY — post-launch feature (backlog **T3.22**). No engine
code in this doc.
**Supersedes:** `ambient_npc_life_design_v1.md` (2026-06-13). v1 stays on
disk as the detailed reference for the parts v2 carries forward unchanged
(the 3-layer rationale, the pre-launch DB-scaffolding plan, the `extra`-JSON
"blanks" policy). Per the authority order, **v2 beats v1**.
**Requested by:** Brian, 2026-06-24 — *"use the Ollama idle queue to make NPCs
more alive: interacting with each other, moving around, working toward goals…
come up with more ways… is that achievable? design it."*
**Author:** Claude Opus 4.8 (parallel design session), grounded against HEAD
via a 12-agent recon (8 subsystem maps + 3 independent architectures + 1
feasibility critic). Every seam cited below was symbol-verified against the
working tree.

---

## 0. TL;DR

- **Is it achievable? Yes — *achievable with one caveat*.** The codebase is
  practically built for this: the Phase-0 substrate already shipped (the
  `npc_ambient_state` / `npc_ambient_relationship` tables + accessors landed
  inert at schema v44), and the movement, broadcast, clock, and idle-LLM seams
  all exist and are verified present.
- **The one caveat (load-bearing):** *Ollama is a garnish, not a brain.* A
  single local Mistral 7B drains at most **~1 idle task / 30 s** and also serves
  live player dialogue. So **Python decides and moves NPCs; Ollama only supplies
  words** — and even then, the right pattern is to **pre-generate rotating line
  pools during idle windows and serve them from cache** (the proven bark model),
  *not* generate per-event in real time. Anyone expecting per-NPC live LLM
  cognition will be disappointed; that is explicitly not the design.
- **What v2 adds over v1:** (a) a **much larger catalog of liveliness
  behaviors** (Brian's "more ways" — §3), (b) the **pool-cache Layer-3
  refinement** that makes spoken texture work within the Ollama ceiling (§2.1),
  (c) **decisions on all four of v1's open design calls** (§4), and (d) a
  **verified landmine list** the v1 doc didn't have (§6) — including two
  must-fix-first traps that would silently sink the feature.

---

## 1. Is this achievable? — the honest feasibility read

**Verdict: achievable-with-caveats.** Every load-bearing seam is verified at
HEAD:

| Capability the feature needs | Verified seam (HEAD) | Status |
| --- | --- | --- |
| Lowest-priority, preemptible Ollama that never blocks players | `engine/idle_queue.py` — per-task priority, 5 s `BACKOFF_SECONDS` after any player request, 200-task cap, `notify_player_request()`, `try_process_one()` drains ≤1/tick, every task pins `provider="ollama"` | **EXTEND** |
| A heartbeat to hang the sim on | `server/tick_scheduler.py` `register(name, fn, interval, offset)`; siblings `director_tick`, `ambient_events_tick`, `dsp_hunter_tick`, `communal_objective_tick`, `idle_queue_tick` already registered in `server/game_server.py` | **EXTEND** (one sibling) |
| A ground mover pattern | `engine/npc_space_traffic.py` — singleton `tick(db, session_mgr)`, `TrafficShip` transit-timer state machine, `enter_state(duration)`, route/BFS | **MIRROR** (zones→`room_id`) |
| Persistent per-NPC goal/movement/mood state | `npc_ambient_state` + `ambient_state_get/ensure_row/update/in_room` (db/database.py:3832+) — **shipped, INERT** | **REUSE** (be its first reader) |
| Opt-in config, zero migration | `npcs.ai_config_json` (additive keys) | **REUSE** |
| Actually relocate an NPC | `db.update_npc(npc_id, room_id=…)` (allowlisted) + `get_npcs_in_room` | **REUSE** |
| Room adjacency | `db.get_exits(room_id)` (filter hidden/locked); BFS idiom in `area_map.build_area_map` | **REUSE** |
| Announce to a room (web + telnet) | `SessionManager.broadcast_json_to_room(room_id,"pose_event",ev)` + `broadcast_to_room` + `broadcast_chat` | **REUSE** |
| Attributed NPC output payloads | `engine/pose_events.py` `make_npc_say` / `make_npc_pose` (**zero prod callers — ready**) / `make_ambient_event` | **REUSE** |
| A world clock for routines | `engine/world_time.py` `global_time_of_day()` + `_CYCLE_BANDS` (`DAY_LENGTH_SECONDS = 2h`, continuous fraction) | **REUSE** |
| NPC↔NPC affinity | `npc_ambient_relationship` (**shipped, INERT, no accessors yet**) | **REUSE** + add accessor trio (Phase 2) |
| Player recall | `npc_memory` (already written by dialogue) | **REUSE** |
| Mood-colored dialogue | `NPCBrain._build_system_prompt` + the `_npc_brains` cache (existing edit-invalidation pattern) | **EXTEND** |
| Macro context to react to | `engine/director.py` zone alert + `engine/world_events.py` effects (**read-only**) | **READ-COUPLE** |

Nothing here is a new top-level system, which keeps the "extend, don't add"
invariant satisfied and launch risk near zero.

### 1.1 The capacity arithmetic (why the caveat matters)

`idle_queue_tick` runs at `interval=30` and drains ≤1 task/tick → a **~120
tasks/hr ceiling**, and only when Ollama is up, `_busy` is clear, and no player
has talked to an NPC in the last 5 s. `AmbientLifeTask` sits at the **lowest
priority**, draining *after* scene summaries, barks, ambient-flavor, event
rewrites, and housing descriptions. Under active play the realistic throughput
is **single-digit generated lines per hour per hub**. Each `generate()` is one
serialized GPU call (up to 60 s timeout).

**Consequence for the design:** the felt-aliveness ceiling *from Ollama alone*
is low; the ceiling *from deterministic Python movement + a large
pre-generated, era-guarded, rotating string pool* is high. So:

> **Python is the brain. Ollama refills pools in the background. The tick deals
> lines from cache. Templated strings are the floor.**

This is the single most important refinement v2 makes to v1.

---

## 2. Architecture (carried from v1) + the pool-cache refinement

Three layers, Ollama last (unchanged from v1 §3):

```
LAYER 3 — FLAVOR (Ollama, idle queue, lowest priority)
   Pre-generates ROTATING LINE POOLS for (archetype × goal/mood × beat).
   Fully preemptible. If Ollama is down, pools just don't refill;
   NPCs still move + act on templated strings. Never blocks a PC.
LAYER 2 — SIM (pure Python, deterministic, on a ~300 s tick)
   Goal/routine selection, movement, NPC-NPC interaction, mood drift,
   reactions. DECIDES every act. SERVES a cached pool line if present,
   else the templated string. THE bulk of the code; testable Ollama-off.
LAYER 1 — STATE (DB, already shipped inert)
   npc_ambient_state (goal/movement/activity + JSON `extra` for mood/
   rumor/sightings), npc_ambient_relationship (affinity), npcs.ai_config_json
   (opt-in config), npc_memory (player recall). Survives restart.
```

**The load-bearing rule (Brian's):** Layer 2 decides; Layer 3 only decorates.
Layer 2 **never calls Ollama on the tick path** — it only *enqueues* pool-refill
tasks and *reads from cache*. World cadence is therefore fully decoupled from
Ollama load.

### 2.1 The refinement: rotating pools, not per-event generation

v1 implied "after the sim decides an interaction, enqueue a task to generate the
line." At ≤1 task/30 s that starves: most events would never get a line.

Instead, mirror what `AmbientBarkTask` and `AmbientFlavorTask` already do —
**pre-generate a small POOL of variant lines keyed by *category*, not by
event**, and serve instantly:

- **Key:** `(archetype, goal_or_mood, beat_type)` — e.g.
  `(merchant, content, arrival)`, `(dockworker, uneasy, idle_business)`,
  `(patron, irritable, npc_chat)`.
- **Refill:** a new lowest-priority `AmbientLifeTask` generates ~5–8 era-guarded
  variants per key during idle windows, exactly like the bark generator, stored
  in a module-level cache (`_ambient_line_pool[key] = {lines, generated_at}`)
  with a staleness TTL.
- **Serve:** on the tick, Layer 2 picks a cached variant for the beat it just
  decided (`random.choice`), with a per-(NPC,beat) cooldown like
  `_bark_cooldowns`. **Empty/stale pool → deterministic template string.**

This converts the Ollama ceiling from "lines per event" (impossible) to "pools
per category refreshed every few hours" (trivially within budget), and gives
**variety without real-time latency**. It also means a busy server degrades
gracefully: pools just go stale and the templated floor shows — never a stall,
never a blank.

---

## 3. The liveliness catalog — "more ways to make NPCs feel alive"

This is the heart of Brian's ask. v1 had three behaviors (move, goals,
NPC-NPC). v2 specifies **thirteen**, organized into tiers by felt-aliveness ÷
risk (the critic's must-haves are **Tier A**). Each is tagged
**[D]** deterministic-Python or **[D+O]** deterministic decision with optional
Ollama-pooled words, with its verified seam and target phase.

### Tier A — Core motion (Phase 1; pure Python; zero Ollama dependency)

1. **Room-to-room movement toward a goal** **[D]** — *the single
   highest-leverage primitive.* An NPC with a `dest_room_id` transitions
   `room_id` along `get_exits` over a `move_duration` (mirror
   `npc_space_traffic`'s transit timer); on arrival flip
   `npc_ambient_state.current_room_id` **and** `db.update_npc(room_id=)` so
   `look`/`talk`/combat agree. Two-call announce shape copied from
   `MoveCommand._broadcast_departure/_arrival`.
   *Player sees:* `Greeda heads off toward the market.` in your room, then
   `Greeda arrives from the south.` in the next — a `pose_event` via
   `broadcast_json_to_room(make_npc_pose)`.

2. **Daily routines keyed to the world clock** **[D]** — band
   `world_time.global_time_of_day()` (the existing continuous fraction, banded
   by `_CYCLE_BANDS`) into the NPC's `ambient_routine` slots; each slot →
   goal → destination + activity. `rest` returns it to `ambient_home_room`.
   Uses an idempotence anchor (`last_tick_at`) so routines advance on
   *band change*, not raw tick offset → restart-safe.
   *Player sees:* the market bustles at midday, the same faces have drifted to
   the cantina by dusk, and gone home by night — a district with a rhythm.

3. **Idle "business" activity verbs when stationary** **[D+O]** — at-goal and
   not moving, cycle a per-archetype verb into `npc_ambient_state.activity`,
   surfaced on `look`/entry and as an occasional `make_npc_pose` (its first
   production use).
   *Player sees:* `Greeda is here, recounting credits behind the stall.` and
   the bartender wiping a glass, eyeing the door — people, not props.

### Tier B — Social fabric (Phase 2; observable NPC↔NPC)

4. **NPC-to-NPC conversation / haggle** **[D+O]** — after movement resolves,
   `ambient_state_in_room()` finds co-located goal-compatible NPCs (vendor +
   patron, two laborers); Layer 2 rolls a short scripted 2–4 line exchange via
   alternating `make_npc_say`, nudges affinity. *(No credits/goods move —
   faucet/sink-neutral.)*
   *Player sees:* you walk into the cantina and catch two locals mid-argument
   about docking fees.

5. **Group formation & cliques** **[D]** — a `socialize`/`gather` goal biases
   its destination toward the room with the most co-socializing NPCs
   (deterministic flocking, per-room capped); affinity above a threshold makes a
   pair co-schedule, below it makes them avoid each other.
   *Player sees:* a knot of regulars forms at the cantina in the evening and
   breaks up at closing; a feuding pair never share a room.

6. **NPC chatter recorded into player scenes** **[D]** — route all NPC speech
   through one shared `npc_say()` helper that calls `get_active_scene_id()` +
   `capture_pose(char_id=None)` (already Optional). Closes the "world feels
   unrecorded" gap; **also requires fixing the confirmed scene-stop column bug**
   (§6).
   *Player sees:* ambient NPC banter shows up in the scene log and summary,
   not just the live feed.

### Tier C — Reactivity (Phase 3; read-only coupling to existing macro state)

7. **React to Director headlines / world events** **[D+O]** — Layer 2 reads
   (read-only) the Director's zone alert level + active `world_events` for the
   NPC's zone and biases goal weights + mood. *Never* writes `zone_influence`
   or the paid path.
   *Player sees:* after a "checkpoints tightened" headline, patrol-type NPCs
   thicken and vendors look nervous — the macro story reaches street level.

8. **React to combat in the room** **[D]** — hook the existing combat
   round-end / `on_pc_death` path to write a `recent_combat` marker + fear-delta
   into nearby non-combatant NPCs' `extra`. Next tick: a timid NPC's goal flips
   to flee-home; a hardened one posts a wary comment. *(No mechanical combat
   effect.)*
   *Player sees:* bystanders scatter when a firefight breaks out instead of
   standing inert.

9. **React to economy / territory shifts (flavor only)** **[D+O]** — read the
   same read-only economy/territory signals the HUD already exposes; pick a
   matching grumble/cheer mood + line. **Zero mechanical effect** (no
   `adjust_credits`, no market write).
   *Player sees:* `A trader complains ration prices have gone mad lately.`
   shortly after a price spike — the world acknowledges its own state.

### Tier D — Inner life & continuity (Phase 3–4)

10. **Emotional state (mood) drift** **[D+O]** — a mood scalar/label in
    `extra` drifts deterministically toward a personality baseline, perturbed by
    interaction outcomes, nearby combat, and zone tension. Mood biases goal
    selection **and** is injected into `NPCBrain._build_system_prompt` (pop the
    `_npc_brains` cache on band change) so even *player-initiated* talk reflects
    it.
    *Player sees:* the same NPC sounds tense during a crackdown and upbeat on a
    good market day — continuity you can feel. Never shown as a raw stat.

11. **Gossip / rumor propagation** **[D+O]** — a bounded rumor *token* (from a
    recent Director headline or a notable nearby beat) lives in `extra`; on a
    co-located interaction it propagates to the partner with a TTL/decay.
    Bounded vocabulary (no free-text growth). Ollama only renders the phrasing.
    *Player sees:* the same event surfaces from different NPCs in different
    rooms over hours, phrased differently — emergent word-of-mouth.

12. **Remember & reference players** **[D]** — *boundary-safe:* the tick records
    co-located PC ids into `extra.last_seen_pcs` (capped, TTL'd) as
    **observation only**, never as a goal input or target. The existing
    `npc_memory` table + `_build_system_prompt` already let a *later
    player-initiated* talk reference history.
    *Player sees:* `Back again, are you?` — and other NPCs having heard of you
    secondhand — without the sim ever breaking the PCs-are-scenery rule.

13. **Multi-step agendas** **[D]** — model an errand as an explicit step list in
    `extra` and advance it with `engine/tutorial_chains.advance_step` (the
    dict-agnostic linear step machine — reuse, don't rebuild). Each step is a
    `(goal, dest, activity)`.
    *Player sees:* a courier you saw at the docks turns up at a warehouse, then
    heads home — a person with an errand, not a wanderer.

> **All thirteen respect the v1 safety boundaries:** observable-not-targeting
> (no unprompted NPC→PC), no mechanical effects in v1 (faucet/sink-neutral),
> era-clean on both layers, opt-in (`ambient_enabled` default false).

---

## 4. Resolved open design calls (v1 §8)

Per Brian's standing preferences (*decide+build+log*, *best/most-complete*,
*conservative only on balance numbers*), I'm **deciding** these rather than
parking them. Each is overridable — flag any you'd reverse.

1. **Movement scope → INTRA-ZONE wander for v1.** An NPC moves among the rooms
   of its building/district (BFS over `get_exits` bounded to its `zone_id`).
   Cross-zone travel is deferred: it adds pathing depth, restart-resume edge
   cases, and "where did everyone go" emptiness with no proportional payoff.
   Intra-zone already reads as alive. *(Critic + all three architects concur.)*

2. **Population cap → START TINY, widen on telemetry** (this is a balance
   number → conservative). A **global per-tick cap** (≈5–10 NPCs processed/tick,
   round-robin, the `npc_space_traffic` `MAX_TRAFFIC_SHIPS=8` discipline) **and**
   a **per-room cap** so a hub can't swarm. Opt in a handful of Mos Eisley hub
   NPCs first; widen with tick-time + queue-depth telemetry. Hard rule: the tick
   **self-gates on occupied rooms** (the `ambient_events` idiom) — an empty
   galaxy costs ~zero CPU.

3. **Observability surface → ROOM CHANNEL, rate-limited, with a player
   suppress-pref.** Ambient lines flow through the same `pose_event` path as
   player speech (dimmed/attributed), rate-limited per room, and silenceable via
   a per-player preference (so RP scenes aren't drowned). No separate channel
   (fragments attention); no look-only (invisible = not alive).

4. **PC-interaction boundary → OUT for v1, confirmed.** NPCs are *observable*,
   never *targeting*. The sim treats PCs as scenery. Any PC-facing ambient
   interaction is a post-v1 design call (grief/spam surface, couples to per-PC
   state the sim deliberately doesn't read).

---

## 5. Build-from seam map (symbol-verified at HEAD)

| Concern | Symbol(s) | File |
| --- | --- | --- |
| Idle task base + queue | `IdleTask`, `IdleQueue.enqueue/try_process_one`, `_bark_cache`/`_bark_cooldowns` (cache+cooldown precedent) | `engine/idle_queue.py` |
| New flavor task | add `AmbientLifeTask(IdleTask, priority=5)` + `enqueue_ambient_life()` (de-dup scan like `enqueue_bark`); pin `provider="ollama"`; `is_era_clean`/`era_violations` drop-guard | `engine/idle_queue.py` |
| Tick registration | `TickScheduler.register("ambient_npc_life", fn, interval=300, offset=<unique, e.g. 135>)` (dodge the 15/75/90 cluster) | `server/tick_scheduler.py`, `server/game_server.py` |
| Sim home (NEW) | `engine/ambient_life.py` — `AmbientLifeManager` singleton + `get_ambient_life_manager()` + module `_manager` (reset in test teardown) | new |
| State | `ambient_state_get/ensure_row/update/in_room`, `_NPC_AMBIENT_STATE_WRITABLE` | `db/database.py:3832+` |
| Affinity (Phase 2) | add `rel_get/rel_update` accessor trio (table shipped without accessors) | `db/database.py` |
| Move | `update_npc(room_id=)` (`_NPC_WRITABLE_COLUMNS`), `get_npcs_in_room`, `get_exits` | `db/database.py:3526/3538/2191` |
| Mover pattern (MIRROR) | `NpcSpaceTrafficManager.tick`, `TrafficShip`, `enter_state` | `engine/npc_space_traffic.py` |
| Broadcast | `broadcast_json_to_room` (2344), `broadcast_to_room` (2307), `broadcast_chat`, `sessions_in_room` (2271) | `server/session.py` |
| Payloads | `make_npc_say`/`make_npc_pose`/`make_ambient_event` | `engine/pose_events.py` |
| Clock | `global_time_of_day`, `_CYCLE_BANDS`, `resolve_period_label` | `engine/world_time.py` |
| Config pass-through | `_build_ai_config` (**add `ambient_*` keys here** — see §6) | `engine/npc_loader.py:274` |
| Mood-in-dialogue | `NPCBrain._build_system_prompt`, `_npc_brains` cache | `ai/npc_brain.py`, `parser/npc_commands.py` |
| Shared speech (NEW) | `engine/npc_speech.py::npc_say(session_mgr, db, npc, room_id, text)` — visibility + COMMS + scene-capture in one | new |
| Scene capture | `capture_pose(char_id=None)`, `get_active_scene_id` | `engine/scenes.py` |
| Player recall | `npc_memory` | `db/database.py`, `ai/npc_brain.py` |
| Agenda engine (REUSE) | `advance_step` | `engine/tutorial_chains.py` |

---

## 6. Landmines & guardrails (verified — v1 didn't capture these)

**Two MUST-FIX-FIRST traps (a drop that ignores either silently does nothing):**

1. **The Inertness guard flips on first read.**
   `tests/test_t3_22_ambient_life_phase0.py::TestInertness` asserts that **no**
   engine/parser/server file references the ambient tables/accessors. The first
   sim file fails it. This is the *intended* Phase-1 trigger — **update the test
   in the same drop** (assert the sanctioned single consumer, not zero), with a
   CHANGELOG/TODO note so the green-suite gate isn't misread as a regression.

2. **The `ai_config` silent-drop trap.** `_build_ai_config`
   (`engine/npc_loader.py:274`) has a **fixed 10-key schema** plus explicit
   pass-throughs for `skills`/`trainer`/`gate`/`is_intel_handler`. Any new
   `ambient_enabled`/`ambient_home_room`/`ambient_routine`/`ambient_goals` key
   **not added there** is dropped at the YAML→DB write seam — the exact class
   that previously killed `skills`/`vendor`/`is_intel`. **Add each key as a
   pass-through, read flags via `safe_json_loads` on the raw row (never via
   `NPCConfig.to_dict`, which round-trips only the typed keys), and add a
   round-trip test** proving an authored ambient NPC survives build→reload.

**Other verified hazards:**

3. **Scene-stop column bug (pre-existing).** `parser/scene_commands.py:317`
   selects `character_name, content … ORDER BY posed_at` — wrong columns (real:
   `char_name`/`pose_text`/`created_at`), swallowed by a bare `except` — so
   `SceneSummaryTask` **never enqueues from scene-stop today**. Fix the 3-column
   rename when wiring behavior #6 (otherwise NPC banter won't be summarized).

4. **`make_npc_pose` has zero production callers.** Its web-render + telnet
   fallback path is untested in the wild — **smoke-verify it on both transports**
   before relying on it for movement/idle-business narration.

5. **"Mute but moving" post-restart window.** Sim state is DB-backed and
   resumes; but the line *pools* (`_bark_cache` and the new
   `_ambient_line_pool`) are in-memory and lost on restart, re-seeding on the
   ~4 h bark cadence. NPCs will move on templated strings until pools refill —
   acceptable, but seed the pools on startup (extend `seed_barks_for_populated_rooms`).

6. **Naming drift.** The v1 doc said `AmbientLifeTask`, but the **shipped** class
   is `AmbientFlavorTask` (the zone-pool feeder, priority 2). The new task is
   genuinely new at **priority 5** — don't shadow/collide with the feeder.

7. **DB write amplification on aiosqlite (single writer).** Every move writes
   `npc_ambient_state` (+ `update_npc`). Bound per-tick writes, keep reads on the
   `idx_npc_ambient_room` index, and round-robin — a large population thrashing
   room state competes with player writes.

8. **Era-guard BOTH layers.** Run `is_era_clean`/`era_violations` on every Ollama
   line (drop on violation, like all existing tasks) **and** hand-author every
   templated Python string era-clean (Tier-A strings ship even when Ollama is
   down). Add a hygiene test scanning the templated pool for banned tokens.
   Mistral invents Empire/TIE/Stormtrooper/canon figures even when prompted CW.

9. **Faucet/sink lockdown.** Assert in review that **no ambient path** calls
   `adjust_credits` / market mutation / `adjust_territory_influence` /
   `perform_skill_check`-for-reward in v1. Ambient acts are mechanically inert.
   *(When effects are ever wanted, they ship through the funnels with their sink
   in the same drop — a post-v1 increment.)*

10. **Singleton test-isolation.** Add `engine.ambient_life._manager = None` to
    test teardown (the documented `world_events._manager` leak gotcha).

11. **Don't route movement through `entity_actor.py`.** It's combat-only (no
    `MOVE` action, idle-reaped at 60 s) — not a generic mover.

---

## 7. Revised phased build plan

Each phase is a shippable vertical slice; Phase 1 alone delivers visibly-moving
NPCs with the LLM entirely offline.

- **Phase 0 — PRE-LAUNCH (DONE).** The two `CREATE TABLE` migrations + the
  `npc_ambient_state` accessor trio shipped inert at schema v44 (drop 46).
  *No further pre-launch DB work.*
- **Phase 1 — Sim core, Python-only, silent (Tier A).** `engine/ambient_life.py`
  (`AmbientLifeManager` mirroring `npc_space_traffic`) + `ambient_npc_life_tick`
  (interval 300, self-gated on occupied rooms, bounded N/tick) + `ai_config`
  pass-throughs (trap #2) + first reader of the ambient accessors (flip
  Inertness, trap #1). Behaviors 1–3, all templated strings. Opt-in a few
  Mos Eisley hub NPCs, tiny cap. Proves movement is consistent + restart-safe.
- **Phase 2 — Social fabric (Tier B, still Python).** `npc_ambient_relationship`
  accessors; co-located goal-compatible exchanges + affinity; group
  formation/cliques; the shared `engine/npc_speech.npc_say` helper +
  scene-capture wiring + the scene-stop bug fix (trap #3, #4). Behaviors 4–6.
- **Phase 3 — Ollama flavor + reactivity (Tiers C + inner-life start).**
  `AmbientLifeTask` (priority 5, `provider="ollama"`, era-guarded) +
  `enqueue_ambient_life` + the **rotating pool cache** (§2.1) seeded on startup;
  mood drift + `_build_system_prompt` injection; read-only Director/world-event
  reactions; combat & economy reactions. Behaviors 7–10. Verify budget-untouched
  (provider routing) + Ollama-down graceful degradation.
- **Phase 4 — Networked world & continuity (Tier D finish).** Gossip/rumor
  propagation; boundary-safe player-sighting memory; multi-step agendas via
  `advance_step`. Behaviors 11–13. Tune caps/observability on telemetry.
- **Phase 5+ (deferred, design-later).** Cross-zone travel; the carefully-gated
  question of any PC-facing ambient interaction; ambient acts with mechanical
  effects (full funnel + sink coverage) — all explicitly out of v1.

---

## 8. Live-safety checklist

Carried from v1 §7, plus v2 additions:

- `ambient_enabled` defaults absent/false → zero change to existing NPCs.
- The sim tick **never** calls Ollama; Ollama is optional Layer-3 pool refill
  only. World cadence independent of Ollama.
- `AmbientLifeTask` priority below all existing idle tasks; PC `talk` bypasses
  the queue entirely → ambient work can never delay a player.
- **No mechanical effects in v1** (faucet/sink-neutral). Read-only coupling to
  Director/economy/world-events only.
- DB scaffolding already landed pre-launch → the post-launch build never
  migrates a live, populated DB.
- Per-tick work bounded (N NPCs/tick); self-gate on occupied rooms.
- Both layers era-guarded; both layers fail safe to templated strings.
- Singleton `_manager=None` test reset; round-trip config test; faucet/sink
  review assertion.

---

## 9. What "done and alive" looks like (acceptance feel)

A player walks into the Mos Eisley cantina at dusk. Two regulars are already
mid-argument about docking fees (you caught them, you didn't summon them). A
vendor you saw at the market an hour ago shuffles in, mutters that ration prices
have gone mad, and settles at the bar wiping it down. When you `talk` to her she
sounds tired — there was a firefight two rooms over earlier and the street's
been tense since the checkpoint headline. None of it cost a credit, none of it
touched the Director's budget, and if the GPU were pegged it'd all still happen —
just with fewer custom lines. That's the bar.

---

## 10. Open questions genuinely for Brian

The four v1 calls are **decided** in §4 (override any you'd reverse). Two
genuine forks remain, both deferrable to when this comes off the shelf:

- **Suppress-pref default (§4.3):** ambient chatter ON by default with an
  opt-out, or OFF with an opt-in? Rec: **ON, opt-out** (invisible = not alive),
  but it touches the RP-scene experience, so it's your call.
- **First opt-in roster:** which hub + which ~6 NPCs get `ambient_enabled` first
  for the Phase-1 telemetry bake? Rec: Mos Eisley cantina + spaceport. Pure
  content choice.
