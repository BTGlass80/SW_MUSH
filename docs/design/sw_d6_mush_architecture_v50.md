# SW_MUSH — Architecture (v50)
## Star Wars MUSH on Python/aiohttp/aiosqlite — May 25 2026 consolidation

> **Full consolidation, no delta.** v50 supersedes v48 (May 23) and
> v49 (May 24). It is grounded in HEAD as of the close of the
> May 25 2026 SYN-wave session (six combined drops: SYN.0 →
> SYN.5). It carries forward v49's web-client lane framing intact
> — that lane is still the largest open work surface, and remains
> the next thing the team turns to once the SYN sequence closes.
>
> If you are reading this and have v48 or v49 in hand: discard
> them. This document is the single architecture-of-record.

---

## §0. Reading guide

- **§1 Current state** — what SW_MUSH is, what's in HEAD, what's
  shipped since v49, the open work.
- **§2 Architecture by layer** — engine / parser / server / data /
  static / tests breakdown with module counts.
- **§3 Roadmap** — three-lane execution model, the SYN sequence
  status, the web-client lane status, priority ranking.
- **§4 Invariants** — the rules that don't move between
  consolidations. v50 adds three new ones (§4.25–§4.27) all from
  the SYN wave.
- **§5 Process disciplines** — how we work (drop discipline,
  phantom catalog, memory hygiene, etc.). v50 adds the
  SYN-sequence roll-up discipline at §5.9.
- **§6 Audit and verification** — the audit anchor, the seven
  phantom-patterns catalog, HEAD verification matrix.
- **§7 Design doc map** — which design doc owns which surface.
- **§8 Outstanding decisions** — open questions Brian or the
  engineer needs to resolve.
- **§9 Version history** — what each prior consolidation closed.
- **§10 Closing notes** — what v50 retires, what's newly tracked,
  the lesson of the SYN wave.

**What v50 closes vs v49:**

1. The **Contestable Wilderness pivot** — design v2 LOCKED 2026-05-24,
   SYN sequence implementation drops 0–5 SHIPPED 2026-05-25. The
   territory model has moved from per-room city-map zones to
   whole-region wilderness ownership. Influence, security, contests,
   cities, and espionage-as-influence are all retargeted.
2. **Five new engine surfaces:** `engine/contest.py` (region contest
   state machine), `engine/intel_handlers.py` (espionage-as-influence
   redemption), expanded `engine/territory.py` (region ownership +
   garrisons + contest hooks), expanded `engine/security.py`
   (wilderness-aware branch), expanded `engine/player_cities.py` (region-
   anchored founding + landmark adjacency + vitality state machine +
   one-shot dissolution migration).
3. **Drop 6D Territory contestation retired in place** — the 442-line
   city-map zone-keyed contest block was physically deleted in SYN.3
   and replaced with a 24-line retirement header pointing at
   `engine/contest.py`. No phantom; clean removal.
4. **A new architecture invariant set (§4.25–§4.27):**
   wilderness-only-influence (§4.25), region-anchored cities (§4.26),
   parallel-ship discipline for engine API retargets (§4.27).
5. **A new process discipline (§5.9):** the SYN-sequence roll-up
   pattern — combining what the design plan scoped as ~2 sessions
   into a single combined drop where dependencies allow.
6. **The web-client lane state is unchanged from v49.** No web-client
   code has shipped since v49; the bug-fix sprint Brian set as v49
   Tier 1 #3 has been deferred while the SYN wave executes. The lane
   re-opens after SYN closes (SYN.6 next; ~4 more sub-drops to
   close).

**What v50 does NOT change:**

- The engine/parser/server layer model.
- The web-client vision/protocol doc (`web_client_vision_and_protocol_v1_2.md`)
  is still authoritative for that lane.
- Invariants §4.1–§4.24 (carried forward verbatim from v49 except
  §4.13 cities is supplemented with §4.26).

---

## §1. Current state

### §1.1 What SW_MUSH is

A Star Wars MUSH built solo by Brian (GitHub: BTGlass80) in
Python 3.14, using aiohttp + aiosqlite + asyncio with a vanilla-JS
web client. Active era is **Clone Wars** (~20 BBY); GCW is
deprecated reference content. WEG D6 R&E ruleset, fidelity is a
hard constraint. Target audience: small RP-leaning playerbase.
Local Mistral 7B for NPC dialogue (RTX 3070, 8GB VRAM); Claude
Haiku for the Director AI when enabled.

Windows desktop is the ground-truth dev box (`run_all_tests.bat`);
MacBook Air M4 is the secondary. The chat sandbox is Linux/Python
3.12 — it runs targeted regression sweeps against HEAD; the full
suite executes on Windows on apply.

### §1.2 What this document is

The architecture-of-record. **v50 is a full consolidation**, not a
delta. It folds the v48 HEAD audit anchor forward (the v48 numbers
are still in §1.3 as the "pre-SYN" baseline) and re-derives counts
against the post-SYN HEAD. It folds the v49 web-client lane
framing forward verbatim — that lane is still open, just on
pause behind the SYN sequence.

### §1.3 Code-state baseline (grounded in HEAD, May 25 2026)

| Surface | v48 (pre-SYN, May 23) | v50 (post-SYN.5, May 25) | Δ |
|---|---:|---:|---|
| Engine modules (`engine/*.py`) | 109 | **114** | +5 (`contest`, `intel_handlers`, `wilderness_encounters`, `wilderness_loader`, `wilderness_writer` — wilderness trio existed pre-SYN but was undercounted; `contest` + `intel_handlers` are new in SYN.3 / SYN.5) |
| Parser modules (`parser/*.py`) | 51 | **55** | +4 (parser surfaces gained during the SYN wave and adjacent T2.WENC work — all small surfaces) |
| Server modules (`server/*.py`) | 16 | **16** | 0 (no new server modules; `tick_handlers_economy.py` gained the `city_vitality_tick` wrapper in SYN.4) |
| DB modules (`db/*.py`) | 2 | 2 | 0 |
| Schema version | 34 | **35** | +1 (SYN.1.b: `territory_claims.wilderness_region_slug`; SYN.3: `region_contests`, `region_contest_cooldowns`; SYN.4: `player_cities.vitality_state` + `vitality_below_since`) |
| Test files (`tests/test_*.py`) | 201 | **253** | +52 across the SYN wave and adjacent T2.WENC work |
| SYN test methods (the new suites) | — | **299** | +299 (SYN.1.a 43 + SYN.2 24 + SYN.3.a 65 + SYN.3.b 53 + SYN.4a 30 + SYN.4b 37 + SYN.5 47) |
| Cities tests (legacy, parallel-ship preserved) | 553 | **520** | −33 (some tests retired during the May 23 wave's stabilization; the 520 figure is what regressed cleanly across SYN.4) |
| Test methods (sandbox-collectible, default deselect) | ~5,796 | **~4,854 expected on Windows** | reconciled per the userMemories anchor; the gap is sandbox-divergence on smoke scenarios |

**On the test-count gap.** v48 reported ~5,796 sandbox-collectible.
userMemories' running count of 4,854 across ~156 files reflects
the Windows full-suite anchor, which excludes some smoke
collections that only register in sandbox. The two numbers
disagree because they're not the same anchor; they have been
disagreeing since v47 and v50 makes no attempt to reconcile them
further. **The audit anchor is HEAD verified by import-load
against the sandbox.** Windows full-suite totals are Brian's
ground truth and run via `run_all_tests.bat`.

**SYN wave regression results.** Across the SYN family + adjacent:

| Sweep | Tests | Status |
|---|---:|---|
| SYN.1.a (region ownership) | 43 | green |
| SYN.2 (wilderness-aware security) | 24 | green |
| SYN.3.a (region contest state machine) | 65 | green |
| SYN.3.b (Anchor kill + multipliers) | 53 | green |
| SYN.4a (city region anchor) | 30 | green |
| SYN.4b (vitality + migration) | 37 | green |
| SYN.5 (espionage-as-influence) | 47 | green |
| **SYN total** | **299** | **green** |
| Cities phase 1–7c + help + web UI | 520 | green (unchanged by SYN — parallel-ship pattern) |
| Adjacent: secmod1, B1c, T2.WENC, wilderness_drop2/phase2, hygiene | 200 | green |
| Adjacent: combat/faction (drop_h, w_2_4, session49, B6, B1b1, B1d3) | 191 | green |
| Adjacent: broader cities/PvP/chain_events | 220 | green |
| **Cumulative across SYN + adjacent sweep** | **1,430** | **green** |

All seven SYN drops were verified at HEAD by AST validation +
targeted regression. The 1,430-test sweep covers everything that
could plausibly regress from the SYN wave.

**Pre-existing baseline failures carried forward** (unchanged by
v50, all pre-SYN):

- `test_cw_era_neutral_carryovers_match_gcw` — technician
  template strength drift GCW↔CW, Brian design call.
- `test_cw_no_test_character` in `test_f1d_era_switch.py`.
- `test_wow3c_dsp_fp_wiring.py::TestNoLeftoverAdminFpModule::test_admin_fp_module_removed`
  — WoW.4 housekeeping debt; `parser/admin_fp_commands.py` should
  have been deleted but wasn't. Unrelated to SYN; will close in
  a small follow-up drop.

### §1.4 What landed since v49 (the May 25 SYN wave)

v49 closed the May 24 design phase. v50 closes the May 25
implementation wave for the Contestable Wilderness pivot.

**One design-lock event:**

- `contestable_wilderness_design_v2.md` **LOCKED 2026-05-24** —
  the full Contestable Wilderness pivot design. Region-keyed
  ownership, region contest state machine (7-day timer +
  4-hour culminating fight + Anchor NPC), wilderness-aware
  security, region-anchored cities + vitality, espionage-as-
  influence, mission/bounty/PvP influence hooks retargeted to
  wilderness-only, active harvest + region resource quality
  (SYN.6 ahead), wilderness anomalies Tier 1/2 + 3 (SYN.7/8
  ahead), building construction (SYN.9 ahead), display
  integration (SYN.10 ahead). The doc is the source of truth
  for the entire SYN sequence.

**Six implementation drops (May 25, in one session, sequential):**

| Drop | Files | New tests | What it shipped |
|---|---|---:|---|
| **SYN.0** | (pre-flight + migration plan, no code) | — | Audited HEAD; wrote `tools/syn_migration.py` plan for the territory_claims wipe and city dissolution. |
| **SYN.1.a** | `engine/territory.py` (region-ownership engine + new constants + 4 surfaces), schema v34→v35 | 43 | Region ownership schema (`region_ownership`, `region_garrison`), `claim_region` / `unclaim_region` / `get_region_owner` / `_get_region_landmarks` / `tick_region_maintenance` / `tick_region_passive_yield`. YAML `resource_signature` schema. Garrison spawn helpers. |
| **SYN.1.b** | `engine/territory.py` (legacy caller retargets), `engine/security.py` (`_apply_claim_upgrade` deleted), `tools/syn_migration.py` (territory_claims wipe) | (regressed within SYN.1.a's 43) | Drop 6D territory_claims surfaces retargeted onto region ownership; `_apply_claim_upgrade` retired (per design v2 §2.3); migration script runs idempotent via `syn_migration_state` marker. |
| **SYN.2** | `engine/security.py` (wilderness-aware step 4) | 24 | Security model: rooms with `wilderness_region_id` resolve declared security from the region; rooms without one keep the legacy zone-keyed path. The "cities cannot be founded in secured zones" rule retired in favor of the wilderness-aware branch. |
| **SYN.3** (combined a+b) | `engine/contest.py` (new, ~1700 LOC), `engine/territory.py` (Drop 6D contest block deletion + retirement header), 5 caller retargets (`server/session.py`, `parser/combat_commands.py`, `parser/faction_commands.py`, `server/tick_handlers_economy.py`) | 118 | Region contest state machine (7-day timer, 4-hour culminating window, Anchor NPC HP/tier scaling, outnumbered-defender 1.5×, contest influence multipliers 2×, `on_npc_killed_in_combat` kill detection). 9 faction Anchor templates + `_default`. Drop 6D's 442-line city-map contest block physically deleted in `engine/territory.py`. |
| **SYN.4** (combined a+b) | `engine/player_cities.py` (+720 LOC SYN.4 section), `parser/city_commands.py` (founding + claim routing), `server/tick_handlers_economy.py` (`city_vitality_tick` wrapper), `server/game_server.py` (scheduler register) | 67 | Region-anchored city founding (`found_city_in_region`), landmark-adjacency expansion (`claim_landmark_for_city`), vitality state machine (active citizen counts → reduced/dormant), one-shot dissolution migration with 75% refund (idempotent via `syn_migration_state`). Parallel-ship: legacy `found_city` + `claim_room_for_city` stay operational for the 520 cities tests. |
| **SYN.5** | `engine/intel_handlers.py` (new, ~520 LOC), `engine/territory.py` (3 influence hooks retargeted + helper), `parser/espionage_commands.py` (`+intel handover` subcommand) | 47 | Espionage-as-influence: `+intel handover [<id>]` redemption surface with quality-classification heuristic stub (T3.15 swap point), faction handler NPC resolution via `ai_config_json` tag, quality tier rates from design §2.7. `on_npc_kill` / `on_mission_complete` / `on_pvp_kill` retargeted to gate on `wilderness_region_id` — city-map activity = rep/credits/CP only; wilderness activity adds the design-table influence delta routed through SYN.3 `region_slug=` so contest multipliers fire automatically. |

Cumulative SYN wave: **299 new tests**, all green. The 1,430-test
sweep across SYN + adjacent verified no regressions.

The userMemories anchor of **~4,854 tests across ~156 files**
remains the Windows ground truth pre-SYN. Post-SYN.5, the
Windows total is expected to land near **5,150–5,170** (4,854 +
299 SYN). v50 does not attempt to re-anchor against Windows;
that's `run_all_tests.bat`'s job on apply.

### §1.5 What's still open

**Engine — launch-critical:**

- **SYN.6** (~1.5 sess) — Active harvest + region resource quality.
  `engine/harvest.py` new; `harvest` player command with skill
  check + cooldown + 15% non-owner tax routing; weekly region
  quality variance roll on Monday midnight tick; Director
  resource-outlook digest. **Next drop in the SYN sequence.**
- **SYN.7** (~2 sess) — Wilderness anomalies Tier 1-2.
  `engine/wilderness_anomalies.py` new (~600 LOC); ~12 type
  templates; spawn cadence engine; Imperial corvette boarding
  adapted from `engine/encounter_boarding.py`; reward
  distribution.
- **SYN.8** (~2 sess) — Wilderness anomalies Tier 3 (world bosses).
  Krayt Dragon, Maze Predator Apex, Crashed Separatist Capital
  Ship, Republic Lost Patrol templates; multi-phase combat with
  relocation; participation-scaled loot; during-contest 2× cadence
  wiring; trophy generation.
- **SYN.9** (~2 sess) — Building construction. `engine/buildings.py`
  new; `buildings` table; `+building` command suite; 24-hour
  construction timer; ownership transfer rules; category effects
  (residence storage, crafting station, commerce stall, garrison
  annex, cultural hall).
- **SYN.10** (~1 sess) — Display integration + launch polish.
  Region look block; faction influence dashboard rewrite;
  `faction contest` and `faction resource_outlook` commands; news
  digest expansions.

**Engine — Tier 2 launch-flexible:**

- **Weight of War mechanic** — MVP_COMPLETE per TODO (Brian
  ticked off May 24). Full implementation pending; currently
  the seam ships and exposes the MVP shape.
- **PG.2.bounty post-launch follow-ups** — BH-tier vendor
  `check_debt_gate` integration (no consumer yet).
- **PG.3 Act 3 trial implementation** — predisposition +
  play-time + Act 1/2 + cooldowns shipped; Act 3 formal Knighting
  trial named but not landed.
- **Padawan-Master expansion** — Master-takes-Padawan,
  Padawan-linked-Master, Master-approves-Trials, training events
  all shipped. Council politics, formal lineage trees, Padawan
  re-assignment are post-launch.

**Web client — full lane:**

- **Tier 1 #3 (carried from v49)** — Bug-fix sprint against the
  Claude Design v3 JSX. Engineering Claude applies fixes per
  `design_review_may24_v1.md` to the v3 drop before any production
  port begins. **The bridge between "design drop produced" and
  "production port begins."** Deferred while the SYN wave executes;
  re-opens after SYN closes.
- **Phase 0–1** (protocol substrate, launch-blocking enabling work).
- **Phase 2** (rich panels, mostly post-launch).
- **Phase 3** (map renderer + asset library + landmark
  illustrations, ships incrementally).
- **Phases 4–5** (diegetic polish, mobile — post-launch).
- See `web_client_vision_and_protocol_v1_2.md` §9 for the phase
  breakdown. The lane has not advanced since v49.

**Design calls (Brian, all carried forward unchanged):**

- *Eavesdrop `target_char` model* — open since v45.
- *`skill_check_passed` trigger-site decision* — open since v45.
- *SRB.1 §3.6 "failed overdose auto-incapacitates"* — block-and-
  warn shipped; auto-incap is a post-launch follow-up if behavior
  demands it.
- *SRB.2 Force-fall-check aura integration* — sync→async
  conversion + db threading work; post-launch.
- *Security Model v1 Coruscant naming reconciliation* — live YAML
  is tier-based, catalog wants function-based.

**Content — launch-flexible:**

- **Coruscant Underworld wilderness build** — landmarks YAML
  shipped May 22; the 40×40×3 grid body still needs authoring
  OR confirmation that the landmarks-as-anchors approach is
  sufficient. Design call.
- **Intel handler NPC seeding** (SYN.5 follow-up) — engine
  treats any NPC with `ai_config_json::is_intel_handler: true` as
  a handler. Need to spawn handlers at the 9 faction HQs with
  this tag. Single small content drop.

### §1.6 What's been steady for a while

- WEG D6 R&E core mechanics — stable since v40.
- Dual WebSocket/Telnet networking — stable since v35 era.
- The web-first design directive — locked since v40.
- The `replaces:` protocol for era-keyed YAML content — locked.
- The phantom-catalog discipline — patterns 1–7 carried forward
  from v48; v50 does not add a new pattern (the SYN wave caught
  three of the existing patterns in flight, all repaired before
  ship; see §5.9 for the SYN-sequence roll-up discipline that
  emerged from the wave).
- The `_FakeDB`-with-mutation-log test fixture pattern (§4.20) —
  used by every SYN test file.
- Boot ordering, era flag (CW), drop-zip packaging discipline —
  all carried forward from v48/v49.
- The Drop 6D contest block deletion is **closed** in SYN.3 — it
  was a parallel-ship retirement pattern (legacy surface deleted
  in same drop the new surface ships). No phantom risk because the
  deletion is HEAD-physical.

---

## §2. Architecture by layer

(Mostly unchanged from v48/v49. The engine/parser/server/data/test
layer shape is what it was. The SYN wave added five engine surfaces
and two parser surfaces; nothing moved between layers. The §2.x
subsections below note the new surfaces only.)

### §2.1 Persistence — `db/`

Unchanged from v48. Schema **v35** (up from v34): SYN.1.b added the
`territory_claims.wilderness_region_slug` column via migration; SYN.3
added `region_contests` + `region_contest_cooldowns` tables; SYN.4
added `player_cities.vitality_state` + `vitality_below_since` columns
via additive `ALTER TABLE` (idempotent — wrapped in try/except since
SQLite < 3.35 lacks `ADD COLUMN IF NOT EXISTS`).

### §2.2 Game engine — `engine/`

**114 modules.** New since v48:

- **`engine/contest.py`** (NEW SYN.3, ~1,700 LOC) — region contest
  state machine. Schema (`region_contests`, `region_contest_
  cooldowns`), 7-day timer, accumulation/culminating-fight phase
  split (`_CULMINATING_SECS = 4h`), Anchor NPC HP-tier scaling
  (`_anchor_hp_tier` → WEG D6 stat dice buckets), 9 faction Anchor
  templates + `_default`. `compute_anchor_hp`, `compute_anchor_
  reinforcements`, `compute_outnumbered_defender_multiplier`,
  `apply_contest_influence_multipliers` (2× both sides + 1.5×
  outnumbered defender on top). Two-phase tick (Phase A: spawn
  Anchor at `accumulation_ends_at`; Phase B: defender-win-by-default
  at `ends_at`). `on_npc_killed_in_combat` kill-detection hook.
  `_resolve_challenger_win` ownership transfer with
  `claimed_by=-contest_id` sentinel.
- **`engine/intel_handlers.py`** (NEW SYN.5, ~520 LOC) — espionage-
  as-influence redemption. Quality tier constants
  (`INTEL_QUALITY_LOW/MEDIUM/HIGH`), heuristic stub
  `evaluate_intel_quality` (T3.15 will replace with real LLM call),
  `sample_intel_reward`, `_is_handler_npc` + `find_handler_in_room`
  (ai_config_json marker `is_intel_handler` + faction match),
  `handover_intel` 5-step validation entry point.
- **`engine/wilderness_encounters.py`** (carried from T2.WENC partial,
  pre-SYN — counted here for first time in v50; v48 undercounted).
- **`engine/wilderness_loader.py`** + **`engine/wilderness_writer.py`**
  (pre-SYN, undercounted in v48).

Substantially expanded since v48:

- **`engine/territory.py`** — gained: `region_ownership` +
  `region_garrison` schemas; `claim_region` / `unclaim_region` /
  `get_region_owner` / `get_org_regions` / `is_region_owned_by` /
  `_get_region_landmarks` / `_get_region_zone` / `spawn_region_
  garrison` / `dismiss_region_garrison` / `tick_region_maintenance`
  / `tick_region_passive_yield` (SYN.1.a). `adjust_territory_
  influence` gained `region_slug=` kwarg routing through SYN.3
  contest multipliers. Drop 6D's 442-line city-map zone-keyed
  contest block **physically deleted** in SYN.3 and replaced with
  a 24-line retirement header pointing at `engine/contest.py`.
  `on_npc_kill` / `on_mission_complete` / `on_pvp_kill` retargeted
  in SYN.5 to gate on `wilderness_region_id` and pass `region_slug=`
  down. New `_resolve_room_region` helper.
- **`engine/security.py`** — gained the wilderness-aware step-4
  branch (SYN.2): rooms with `wilderness_region_id` resolve declared
  security from the region; rooms without one keep the legacy
  zone-keyed path. `_apply_claim_upgrade` retired in SYN.1.b.
- **`engine/player_cities.py`** — gained the +720 LOC SYN.4 section:
  `found_city_in_region` + `claim_landmark_for_city` (parallel-ship
  alongside legacy `found_city` + `claim_room_for_city`),
  `count_active_citizens` + `compute_vitality_threshold` +
  `compute_vitality_state` + `tick_city_vitality` +
  `effective_tax_rate_cap` (vitality state machine),
  `syn4_migrate_dissolve_city_map_cities` (one-shot migration with
  75% refund, idempotent via `syn_migration_state` row).

### §2.3 Parser — `parser/`

**55 modules.** Substantially modified surfaces since v48:

- **`parser/city_commands.py`** — `_handle_found` accepts new
  `+city found <name> in <region_slug>` form (SYN.4); `_handle_claim`
  routes to `claim_landmark_for_city` when the active org's city is
  region-anchored (`wilderness_region_id` set), else falls through
  to legacy.
- **`parser/espionage_commands.py`** — `IntelCommand` gains
  `+intel handover [<id>]` subcommand (SYN.5).
- **`parser/combat_commands.py`** — PvP gate retargeted; NPC death
  hook added per SYN.3.
- **`parser/faction_commands.py`** — `_cmd_seize` deleted (SYN.3
  retired the per-room seize surface; replaced by region-keyed
  challenge flow in `engine/contest.py`, parser command for it not
  yet wired — see §1.5 follow-ups).

### §2.4 Server — `server/`

**16 modules** (unchanged). Modified:

- `server/tick_handlers_economy.py` — gained `city_vitality_tick`
  wrapper (SYN.4).
- `server/game_server.py` — registers `city_vitality` tick at
  `interval=3600, offset=1900` (SYN.4); registers
  `region_maintenance` + `region_passive_yield` (SYN.1.a) and
  `region_contest_tick` (SYN.3).
- `server/session.py` — HUD payload gained contest-status field
  (SYN.3 retarget).

### §2.5 Static client — `static/`

Unchanged from v48. The web-client lane has not advanced.

### §2.6 World data — `data/worlds/`

Unchanged from v48 structurally. Two CW zones gained `resource_
signature` YAML blocks during SYN.1.a (per design v2 §3.11). The
Drop 6D-vintage territory_claims data is wiped via the SYN.1.b
migration when applied; the wipe is idempotent.

### §2.7 Tests — `tests/`

**253 test files** (up from 201 in v48). The SYN wave added 7 new
test files (one per drop) totaling **299 tests**:

- `test_syn1a_region_ownership.py` (43)
- `test_syn2_wilderness_aware_security.py` (24)
- `test_syn3a_region_contest_state_machine.py` (65)
- `test_syn3b_anchor_kill_and_multipliers.py` (53)
- `test_syn4a_city_region_anchor.py` (30)
- `test_syn4b_vitality_and_migration.py` (37)
- `test_syn5_espionage_as_influence.py` (47)

The legacy 520 cities tests are **unchanged** by the SYN wave —
this is the parallel-ship pattern's payoff. Retargeting them to
wilderness fixtures is its own ~2-session refactor that will land
after the SYN.4 migration runs in production and confirms no
orphan legacy cities remain.

### §2.8 Skills directory — `data/skills/` (CP / WEG)

Unchanged from v48.

---

## §3. Roadmap

### §3.1 Three-lane execution model (UNCHANGED from v49)

Three lanes:

- **Engine lane** — **closed for launch EXCEPT for the open SYN
  sequence (SYN.6 → SYN.10).** When SYN closes, engine reverts to
  the post-launch follow-up state v48 described. Tier 2 follow-ups
  remain: PG.2.bounty post-launch (#9), SRB.1 post-launch (#10),
  SRB.2 post-launch (#11), PG.3 Act 3 (#12). Brian-design calls
  carried over.
- **Content lane** — Tier 2 #3 (Coruscant Underworld) remains the
  main open content item. Intel-handler NPC seeding is a small
  SYN.5 follow-up content drop.
- **Web client lane** — **paused since v49.** Tier 1 #3 (the
  Claude Design bug-fix sprint) is on hold while the SYN sequence
  executes. Re-opens after SYN.10 closes, OR if Brian wants to
  interleave web work between SYN sub-drops (which the parallel-
  ship discipline §4.27 makes safe).

### §3.2 Priority ranking (UPDATED v50)

**Tier 1 — Top priority (active focus)**

| # | Item | Lane | Effort | Why |
|---|---|---|---|---|
| **1** | Eavesdrop `target_char` design call | design | Small (~0.5 sess) | Open since v45. Brian-design call. |
| **2** | `skill_check_passed` trigger-site decision | design | Small (~0.5 sess) | Open since v45. Brian-design call. |
| **3** | Claude Design drop bug-fix sprint (Path B) | web-client | Small–Medium (~1 sess) | Carried from v49 unchanged. Engineering Claude applies fixes per `design_review_may24_v1.md` to the v3 JSX before production port. **Currently paused behind the SYN sequence.** |
| **4** | **SYN.6 — Active harvest + region resource quality** | engine | Medium (~1.5 sess) | **NEW v50.** `engine/harvest.py` new module; `harvest` command with skill check + cooldown + 15% non-owner tax routing; weekly region quality variance roll on Monday midnight tick; Director resource-outlook digest. **Next drop after v50 consolidates.** |

**Tier 2 — Important, queued**

| # | Item | Lane | Effort | Why deferred |
|---|---|---|---|---|
| **5** | **SYN.7 — Wilderness anomalies Tier 1-2** | engine | Medium (~2 sess) | `engine/wilderness_anomalies.py` new (~600 LOC); ~12 anomaly type templates; spawn cadence engine; Imperial corvette boarding adapter; reward distribution. |
| **6** | **SYN.8 — Wilderness anomalies Tier 3 (world bosses)** | engine | Medium (~2 sess) | Krayt Dragon, Maze Predator Apex, Crashed Separatist Capital Ship, Republic Lost Patrol; multi-phase combat with relocation; participation-scaled loot. |
| **7** | **SYN.9 — Building construction** | engine + parser | Medium (~2 sess) | `engine/buildings.py` new; `buildings` table; `+building construct/demolish` suite; 24-hour construction timer; ownership transfer; category effects (residence, crafting station, commerce stall, garrison annex, cultural hall). |
| **8** | **SYN.10 — Display integration + launch polish** | engine + parser | Small (~1 sess) | Region look block; faction influence dashboard rewrite; `faction contest` + `faction resource_outlook` commands; news digest expansions. **Final SYN drop.** |
| **9** | **Coruscant Underworld wilderness build** | content + design | Medium (~1–2 sess) | Landmarks YAML shipped May 22; the grid body needs authoring OR confirmation. Design call. **Likely interleavable with the SYN sequence depending on Brian's call.** |
| **10** | Security Model v1 content reconciliation | data + design | Small (~0.5 sess + call) | Blocked on Coruscant naming-scheme design call. |
| **11** | PG.2.bounty post-launch follow-ups | engine | Small per-drop | BH-tier vendor `check_debt_gate` integration. |
| **12** | SRB.1 follow-ups | engine + data | Small per-drop | Stim crafting schematics, inventory wiring, design §3.6 auto-incap call. |
| **13** | SRB.2 follow-ups | engine | Small per-drop | Force-fall-check aura integration. |
| **14** | PG.3 Act 3 trial implementation | engine | Small (~1 sess) | Manual fallback (`+knight` via Padawan-Master) exists. |

**Tier 3 — Polish / post-launch**

| # | Item | Why deferred |
|---|---|---|
| **15** | Padawan-Master post-launch expansion (council, lineage trees, re-assignment) | Design names these as post-launch. |
| **16** | Cities post-launch expansion (multi-city-per-org, paged list sub-modals, P2P discovery) | All named as post-launch per `player_cities_design_v1_2.md`. |
| **17** | Director AI Clone-Wars tuning (T3.15) | Will replace SYN.5 intel-quality heuristic stub with real LLM call. |
| **18** | Space Wildspace expansion | `space_wildspace_design_v1.md` exists. Post-launch. |
| **19** | Web client Phase 4 (diegetic polish) | Vision Phase 4. |
| **20** | Web client Phase 5 (mobile) | Vision Phase 5. |
| **21** | Legacy cities tests retargeted to wilderness fixtures + legacy `found_city` / `claim_room_for_city` removal | After SYN.4 migration runs in production. ~2 sess. |

### §3.3 Closed since v49

**The May 25 SYN wave closes SYN.0 through SYN.5** — six drops in
one session (combined drops for SYN.3 and SYN.4 per the roll-up
discipline; see §5.9):

- **SYN.0** — Pre-flight + migration plan. No code.
- **SYN.1.a** — Region ownership engine. 43 tests.
- **SYN.1.b** — Legacy caller retargets; migration script;
  `_apply_claim_upgrade` retired. Regression-tested within SYN.1.a's
  suite.
- **SYN.2** — Wilderness-aware security branch; "cities not in
  secured zones" rule retired. 24 tests.
- **SYN.3** (combined a+b) — Region contest state machine; Drop 6D
  contest block deleted. 118 tests.
- **SYN.4** (combined a+b) — Region-anchored cities + landmark
  expansion + vitality + 75%-refund migration. 67 tests.
- **SYN.5** — Espionage-as-influence + mission/bounty/PvP hooks
  retargeted to wilderness-only. 47 tests.

Cumulative: **6 drops in 1 session, 299 new tests, 1,430-test
sweep across SYN + adjacent all green.**

**Other items closed since v49:**

- *(None.)* The SYN wave was the only engine activity. The
  web-client lane has not advanced.

### §3.4 Why this ranking

**The SYN sequence dominates the engine lane.** Five more drops
(SYN.6 → SYN.10) close the Contestable Wilderness pivot
end-to-end. Each drop is ~1–2 sessions of scope; the
SYN-sequence roll-up discipline (§5.9) may compress some pairs
into single drops where dependencies allow.

**The web-client lane is the next thing after SYN.** Per the
userMemories on-the-horizon framing: "Map redesign production
implementation: v2 mockup approved; production port pending." When
SYN.10 closes, the engine lane reverts to small follow-ups and
the team turns to the web-client lane. Brian's stated preference
("UI which will be the goal as soon as we finish this SYN pivot")
makes this explicit.

**Tier 1 design calls #1 and #2** remain open across v45–v50.
They are small implementations; both require Brian to commit on a
design call. Both can ship after the SYN sequence closes if Brian
prefers to keep them deferred.

**Coruscant Underworld** is interleavable. The SYN wave's
parallel-ship discipline (§4.27) means content drops can land
between SYN sub-drops without engine interference. If Brian wants
to break up the SYN cadence with a content drop, the
Coruscant Underworld build is the obvious candidate.

### §3.5 Web client lane reference (UNCHANGED from v49)

Carried forward verbatim from v49 §3.5. The authoritative
reference for all web client work is **`web_client_vision_and_protocol_v1_2.md`**.

That document subsumes:
- `CLAUDE_DESIGN_BRIEF.md` (folded into vision §7)
- `MAP_REDESIGN_HANDOFF.md` (superseded by vision §7.13)
- `web_client_ux_overhaul_v1.md` (folded into vision §6)
- `ground_ux_overhaul_design_v1.md` (folded into vision §6 / §10.4)
- `web_ux_competitive_analysis.md` (folded into vision §5)

`Map_Redesign_v2.html` remains a valid reference asset (the
per-style room footprint mockup, the fallback layer in the asset
library per vision §7.13.1).

### §3.6 What ships at launch (current reading)

**Launch scope (updated for the SYN sequence):**

- WEG D6 R&E core + chargen.
- Combat (ground + space).
- Economy + trade + crafting + Sabacc + Entertainer aura + lead.
- **Wilderness movement, all wilderness regions including
  Coruscant Underworld once content lands.**
- Tutorial chains (F.8 + F.8.c).
- All security zones + faction-override SECMOD.1, **plus the
  wilderness-aware security branch from SYN.2**.
- All progression gates (PG.1 death, PG.2 bounty, PG.3 Force).
- Padawan-Master (Masters take Padawans, Padawans linked, Masters
  approve Trials, `+teach`/`+learn`/`+spar`).
- Player Cities v1.2 (full) **+ region-anchored cities from SYN.4
  + vitality state machine + 75%-refund migration of legacy cities**.
- Mail, channels, news, places, plots, scenes, espionage, spacer
  quest.
- **Contestable Wilderness end-to-end (SYN.0 → SYN.10): region
  ownership + region contests with Anchor NPCs + region-anchored
  cities + espionage-as-influence + active harvest + wilderness
  anomalies Tier 1/2/3 + building construction + display
  integration.**
- Director AI (Clone Wars era, with intel-quality stub awaiting
  T3.15).
- Web client UX (chargen, modal panels, city panels, HUD —
  post-bug-fix-sprint + production port; v3 JSX → `static/client.html`).

**Post-launch (intentionally deferred):**

- Cities multi-city-per-org, P2P city discovery.
- Padawan-Master council politics, formal lineage trees.
- Space Wildspace expansion.
- Director AI CW prompt tuning (T3.15 — will replace SYN.5
  intel-quality heuristic stub).
- Web client Phase 4 (diegetic polish) and Phase 5 (mobile).
- PG.3 Act 3 formal Knighting trial (Padawan-Master `+knight` is
  the manual fallback).
- Legacy cities tests retargeted to wilderness fixtures + legacy
  founding surfaces removed.

### §3.7 Forward session plan (UPDATED v50)

**Next session:** SYN.6 (active harvest + region resource quality)
unless Brian elects to interleave Coruscant Underworld or the
Claude Design bug-fix sprint.

**Subsequent sessions** (in order, unless Brian re-prioritizes):

1. SYN.7 — Wilderness anomalies Tier 1-2.
2. SYN.8 — Wilderness anomalies Tier 3 / world bosses.
3. SYN.9 — Building construction.
4. SYN.10 — Display integration + launch polish.
5. **Web client lane re-opens.** Tier 1 #3 — Claude Design bug-fix
   sprint (engineering Claude applies the `design_review_may24_v1.md`
   fixes to the v3 JSX). Pre-implementation checkpoint with Brian
   after the fixes land.
6. Production port of v3-fixed → `static/client.html`.
7. Web client Phase 0–1 (protocol substrate). Launch-blocking
   enabling work.
8. Coruscant Underworld build (if not already interleaved).
9. The two design calls (Tier 1 #1, #2).

**Brian's stated preference:** "Update the architecture doc … 49
focuses on the UI which will be the goal as soon as we finish this
SYN pivot." v50 honors that — the SYN sequence is the active focus
through SYN.10, then the team turns to the web-client lane.

---

## §4. Architecture invariants

(All v48/v49 invariants §4.1–§4.24 carry forward unchanged unless
noted. Three new invariants added at §4.25, §4.26, §4.27. The
§4.13 cities invariants are supplemented by §4.26 region-anchored
cities; both are operative.)

### §4.1 Web-first directive

(unchanged.) Features are designed for the web client first.
Graceful Telnet degradation is a nice-to-have, not a veto.
Features requiring the web client show "requires web client" on
Telnet. Telnet port stays alive for admin debugging and purists.

### §4.2 WEG-fidelity invariant (carried forward from v49 strengthening)

Mechanics follow WEG D6 R&E. Departures are explicit design calls,
documented in the relevant design doc. Strengthened in v49 to UI
surfaces: UI controls must represent state the engine canonically
tracks AND send parser commands that canonically exist. See §4.23
for the enforcement discipline.

### §4.3 Audit discipline (unchanged)

Grep HEAD before marking delivered. Every drop's pre-flight audit
grepped HEAD for the prior drop's claims before writing new code.
The SYN wave validated this discipline across 6 sequential drops.

### §4.4 Boot ordering for era flag (unchanged)

Active era is **Clone Wars** (`server/config.py` and
`engine/era_state.py` flipped to `clone_wars`; `use_yaml_director_
data` True). GCW is deprecated reference content.

### §4.5 Seam vs. integration discipline (unchanged)

Ship the contract first with no consumer; wire later. Fail-loud
on seam failures (not silent fallback). The SYN wave used this
extensively: SYN.1.a shipped the `region_slug=` seam on
`adjust_territory_influence` with no consumer; SYN.5 then wired
the consumer at three call sites.

### §4.6 `replaces:` protocol for era-keyed content (unchanged)

### §4.7 Smoke-test discipline (unchanged)

### §4.8 Test ground-truth split (unchanged)

Brian runs full pytest on the Windows dev box. In-sandbox Claude
runs only targeted checks: AST validation of modified files + tests
for the changed module + regression sweep of adjacent surfaces.
**Do NOT run full suite in sandbox** — timeout exceeds 600s.

### §4.9 Chunked delivery (unchanged)

### §4.10 Single-source-of-truth state transitions (unchanged)

The SYN wave reinforces this: the region-contest state machine in
`engine/contest.py` is the single source of truth for contest
state transitions; the Drop 6D zone-keyed contest block was
deleted in SYN.3 specifically because two truth sources would have
diverged.

### §4.11 Security model invariants (UPDATED v50)

Carried forward from v48 with the SYN.2 wilderness-aware branch
added:

- Rooms with `wilderness_region_id` resolve declared security
  from the region (the region's `properties.security` or the
  region default).
- Rooms without `wilderness_region_id` keep the legacy zone-keyed
  path.
- The "cities cannot be founded in secured zones" rule is
  **retired** in SYN.4 — wilderness regions are CONTESTED by
  default, and the city-founding eligibility rule moved to
  region ownership / Foothold influence (50+) per §4.26.

### §4.12 Support role buffs invariants (unchanged)

### §4.13 Player cities invariants (UPDATED v50)

(Carried forward from v48 with the SYN.4 retarget added; see also
the new §4.26.)

- City state is org-anchored. `get_city_by_org(db, org_id)` is the
  canonical lookup.
- Roles: `founder` / `mayor` / `citizen` / `guest` / `outsider` /
  `banished`. Banished is highest priority.
- Grace state machine for maintenance: 1 week flags-off, 2 tax-off,
  3 final warning, 4 dissolve. `grace_started_at` is the single
  source of truth. `guards_active(city)` False in any grace stage.
- Citizen-only rooms subject to a 33% cap; enforcement in
  `set_room_citizen_only`.
- NPC guards (Phase 7+): slot counts per HQ tier (outpost 3 /
  chapter_house 6 / fortress 14), engagement triggers from
  citizen-only intrusion / banished entry / bountied entry /
  attacked-a-citizen-in-this-combat-session. The ATTEMPT counts,
  not the HIT. Citizen-on-citizen still triggers.
- **NEW v50 (SYN.4):** Cities can be region-anchored
  (`wilderness_region_id` set) or legacy city-map (NULL). The
  vitality state machine applies per-tier active-citizen
  thresholds (outpost 1, chapter house 3, fortress 5); below
  threshold → `reduced` immediately, `dormant` after 14d under
  threshold. Recovery is single-tick. Reduced/dormant halves the
  tax cap (via `effective_tax_rate_cap` — seam in place; consumer
  wiring is a follow-up) and blocks expansion. See §4.26.
- **NEW v50 (SYN.4):** Parallel-ship: legacy `found_city` and
  `claim_room_for_city` remain operational for the 520 cities
  tests. The new region-anchored API (`found_city_in_region`,
  `claim_landmark_for_city`) ships alongside. Parser routes by
  active-org-city's `wilderness_region_id`.
- Web UI (Phase 6 web UI): HUD payload `hud["city"]` is the
  transport. Action buttons send the same text the player would
  type. 6 destructive actions go through 5-second two-stage
  confirm.

### §4.14 Wilderness co-location invariant (unchanged)

### §4.15 Map renderer invariants (carried forward from v49)

The map renderer is a three-layer separation: asset library
(hand-authored SVG illustrations), composition engine (runtime
renderer), game data (geometry + state). One renderer for all
viewports; no parallel implementations. Production code must NOT
bypass the asset library by inlining schematic SVGs in panels.
Rooms may declare a `landmark_slug` field; renderer uses
named-landmark illustration when set, falls back to style
primitive otherwise.

### §4.16 Q1 canonical-character policy (unchanged)

Canonical Star Wars characters = EXTREMELY RESTRICTED.
Absence-framing or original-NPC substitution required. Q1 test
family is the standing quality regime — has caught real slips
multiple times (most recently a Tarkin reference during SYN.4
chain-anchor NPC validation).

### §4.17 +pvp opt-in flag invariants (unchanged)

### §4.18 PG.1.death invariants (unchanged)

### §4.19 PG.2.bounty invariants (unchanged)

### §4.20 Test-fixture patterns (unchanged)

The `_MiniDB` + `_FakeDB` patterns continue to be the default for
SYN-wave tests. SYN.4 test fixtures specifically needed to validate
against `Database._CHARACTER_WRITABLE_COLUMNS` allowlist behavior.

### §4.21 Cities web-UI safety pattern (unchanged)

The two-stage confirm pattern is still the canonical destructive-
action UI safety pattern. Future destructive surfaces (housing
dissolve, ship scrap) should reuse `_cityMakeDangerBtn`.

### §4.22 Combat-trigger state (unchanged)

`CombatInstance.attacks_made` is the in-memory record of every
attempted attack. Consumers include
`evaluate_combat_round_triggers` and (SYN.3) `on_npc_killed_in_combat`
for region-contest kill detection. The ATTEMPT counts, not the HIT.

### §4.23 Engine-canonical command discipline (carried forward from v49)

Before merging UI code that sends a parser command, the engineer
must verify the command exists. Before displaying a value, the
engineer must verify the engine field exists. Canonical command
list lives in `web_client_vision_and_protocol_v1_2.md` §3.15.
Things that are NOT canonical: `stance`, "Mode <combat|exploration|
social>", hit-point bars/percentage health, mana/energy pools,
armor durability.

### §4.24 Web wire protocol discipline (carried forward from v49)

Every server→client message carries a `schema_version` field.
Server supports last N versions (start with N=2). Client states
preferred version on connect. Schema-discovery endpoint at
`GET /api/protocol/schema`. The §5.10 maintenance rule from the
vision doc applies.

### §4.25 Wilderness-only influence invariant (NEW v50)

**Per design v2 §2.7, the two-tier reward rule for faction
power projection is:**

- **City-map activity (rooms with `wilderness_region_id` NULL):**
  rep + credits + CP only. NO influence delta. The mission/bounty
  awards live in the caller and still fire — only the influence
  hook gates out.
- **Wilderness activity (rooms with `wilderness_region_id` set):**
  rep + credits + CP + influence delta routed through
  `adjust_territory_influence(..., region_slug=<slug>)` so SYN.3
  contest multipliers apply automatically.

The three engine hooks (`on_npc_kill`, `on_mission_complete`,
`on_pvp_kill`) all gate on `wilderness_region_id`. The constants
match design verbatim: `INFLUENCE_NPC_KILL=2`, `INFLUENCE_MISSION=5`,
`INFLUENCE_PVP_WIN=15`. PvP loser pays -5 (also gated on
wilderness; loser penalty short-circuits multipliers via
`apply_contest_influence_multipliers`'s `delta <= 0` early-return).

**Why this is an invariant, not just a behavior:** future reward
hooks (e.g. `on_harvest_success`, `on_anomaly_kill`,
`on_intel_handover`) MUST also gate on `wilderness_region_id` and
route through `region_slug=`. Any new influence-granting code path
that doesn't do this is a regression of the design rule.

The espionage handover (SYN.5) is the first non-combat consumer
of this invariant: `handover_intel` evaluates which region the
intel describes (via `_extract_mentioned_regions`); if no known
wilderness region is named, the credits pay out but influence is
zero. The handler-NPC sits at a faction HQ (city-map room) but
the influence lands in the *region the intel describes*, not where
the handover happens.

### §4.26 Region-anchored cities invariant (NEW v50)

**Per design v2 §2.9, cities anchor on wilderness regions.** Five
city benefits (identity, tax, citizen security upgrade, +city home,
mayor governance) survive unchanged from city-map cities. What
retargets:

- **HQ anchor:** city HQ anchors on a wilderness landmark room
  within the chosen region.
- **Expansion:** claim adjacent landmarks within the same region
  using the existing landmark adjacency graph.
- **Founding requirement:** "org owns the region OR has Foothold
  (50+ influence in parent zone)." Founding in un-owned region
  is allowed (stakes a claim with infrastructure); rival-owned
  region requires contesting via SYN.3 first.
- **Retired rule:** "Cities cannot be founded in secured zones."
  Wilderness regions are CONTESTED by default per SYN.2.

**Vitality:** per HQ tier (outpost 1, chapter house 3, fortress 5)
active citizens within 7-day window. Below threshold → `reduced`
immediately. 14 days below → `dormant`. Recovery is single-tick.
Effects: tax cap halved (seam in place), expansion blocked.

**Parallel-ship pattern:** legacy `found_city` and
`claim_room_for_city` remain operational. The 520 cities tests
stay green without retargeting. New surfaces ship alongside; parser
routes by active-org-city's `wilderness_region_id`. Retirement
depends on the SYN.4 dissolution migration having run in
production.

### §4.27 Parallel-ship discipline for engine API retargets (NEW v50)

When retargeting an engine API to a new model (e.g. zone-keyed →
region-keyed, city-map → wilderness-anchored), **the new surface
ships alongside the old, not in place of it.** The retirement of
the old surface depends on:

1. The migration that translates old data to new having run in
   production.
2. The runtime confirming no orphan legacy state remains.
3. Tests for the old surface having been retargeted to the new
   fixtures.

The retirement is then a separate drop — small, focused on
deletion and cleanup, with a clean audit trail.

**Why this is an invariant:** the alternative (big-bang retarget in
one drop) packages the new surface, the migration, the tests, and
the legacy cleanup all together. That's a higher-risk drop and
typically a longer one. The SYN wave used parallel-ship for SYN.1
(region-keyed alongside zone-keyed influence), SYN.3 (one of the
two non-parallel cases — Drop 6D zone-keyed contest deleted because
runtime data was already pre-wiped), SYN.4 (region-anchored
alongside city-map), and SYN.5 (gates added to existing hooks, no
retirement needed). The pattern compresses to its limit on SYN.3
where the deletion is HEAD-physical because the data migration is
also part of the same wave; everywhere else, deletion is a future
small drop.

**Process implication:** the SYN sequence's "retire legacy
surfaces" follow-up is **after SYN.10 closes** (or whenever the
production-side SYN.4 migration completes, whichever comes later).
~2 sessions: retargets the 520 legacy cities tests to wilderness
fixtures + physically removes `found_city` / `claim_room_for_city`
/ adjacent Drop 6D surfaces.

---

## §5. Process disciplines

### §5.1 Architecture rev cadence

Consolidations: every 4–6 weeks or after 8+ drops since the
last full consolidation. **v50 is consolidating early** because
the SYN wave delivered 6 drops in a single session and Brian
asked for a full consolidation rather than a delta. The next
expected consolidation is v51 after SYN.6–SYN.10 close (or a
delta if no SYN milestone has been hit).

Deltas remain acceptable between consolidations but every delta
should be paired with a backup of its parent consolidation.

### §5.2 Project knowledge tier discipline (unchanged)

Design docs are Tier 1 (must persist). Handoff docs are Tier 2
(persist until consolidated). Working notes are Tier 3.

### §5.3 Sourcebook PDF handling (unchanged)

WEG sourcebook PDFs live in project knowledge. Extraction docs
(`WEG40120_extraction_v1.md` etc.) are the live references.

### §5.4 Memory hygiene (unchanged)

UserMemories edits should be made in the same session as the
delivery they describe. userMemories should never be the source
of truth for "what shipped" — always verify against HEAD with
import-load.

### §5.5 Wookieepedia scraping (unchanged)

### §5.6 Drop-zip packaging discipline (unchanged)

Every drop zip is built project-root-mirrored from the actual
sandbox HEAD; Windows-applied via `Expand-Archive -Force`; first
action of every new session is a pre-flight audit with import-load
on items the prior session's handoff claimed shipped.

### §5.7 Long-wave drop discipline (unchanged from v48)

The May 23 cities wave validated 7 sequential drops in one
session. The May 25 SYN wave validated 6 more (some combined,
per §5.9). Pattern requirements: dependencies one-way; each
drop independently complete and testable; session can summarize
and compact mid-wave without losing audit trail; single
architecture consolidation closes the wave.

### §5.8 Design-drop review discipline (carried forward from v49)

Large external design drops (e.g. Claude Design's UI/UX work) get
a structured review against the mechanical/era constraints before
production port begins. Issues are catalogued by severity (blocker
/ high / medium / low). Path B (engineering Claude applies fixes
to the design drop before production port) is the default for
asset-heavy drops where most of the material is salvageable.

### §5.9 SYN-sequence roll-up discipline (NEW v50)

The design doc may scope a drop as N sessions; the engineer may
deliver it as a single combined drop when dependencies allow.
This was Brian's standing call going into the SYN wave: "roll up
multi-half drops into single combined deliveries."

The pattern that worked across the SYN wave:

1. **Original design scoping** estimates effort in sessions
   (e.g. SYN.3 "~1.5 sess", SYN.4 "~2 sess"). This is the
   honest first-cut estimate.
2. **In the implementation session, the engineer checks for
   sub-drop boundaries** — are the sub-drops independently
   shippable, or does sub-drop B require sub-drop A's
   surfaces to even be testable?
3. **If sub-drops are tightly coupled** (e.g. SYN.3.b's
   "Anchor kill + multipliers" tests can't exist without
   SYN.3.a's contest state machine), combine into one drop.
4. **If sub-drops are loosely coupled** (e.g. SYN.4 region
   anchor and SYN.4 vitality could in principle ship
   separately), still combine if the combined size is
   manageable (~720 LOC was the SYN.4 ceiling that worked).
5. **Document the combination** in the handoff so the
   architecture-of-record carries the actual shape, not the
   originally-scoped shape.

**Limits:**

- Don't combine across deletion boundaries. SYN.3's Drop 6D
  block deletion was its own scope; SYN.4's legacy cleanup is
  explicitly a separate future drop because it depends on a
  production-side migration.
- Don't combine across consumer/seam boundaries. If sub-drop B
  exists to wire a consumer that sub-drop A's seam exposes, ship
  the seam first and the consumer second — even if both
  technically fit in one session.
- Don't combine if total size exceeds ~1,500 LOC of changed
  source per drop. The combined drop becomes too risky to
  audit at HEAD.

The May 25 wave demonstrated the discipline works: SYN.3 and
SYN.4 both shipped as combined drops; SYN.1 shipped as a/b split
because the b half was specifically the legacy-caller retargets
that depended on the a half's new surfaces; SYN.5 shipped as a
single drop because it was naturally single-scoped.

### §5.10 Memory anchor refresh (NEW v50)

Per Brian's preference, userMemories should be refreshed at the
end of significant waves to reflect the post-wave state. The May
25 wave is one such wave. The architecture doc (v50) is the
durable anchor; userMemories carries a recent-bias snapshot.

When userMemories disagrees with the architecture doc, the
architecture doc wins. The architecture doc is sandbox-verified;
userMemories is text Brian wrote.

---

## §6. Audit and verification

### §6.1 The audit anchor

The audit anchor is **HEAD verified by import-load**, not any
handoff document or memory note. The SYN wave reinforces this:
every SYN drop's pre-flight grepped HEAD for the prior drop's
claims before writing new code; every SYN drop's tests verify
their own surfaces by import-loading the new symbols.

### §6.2 The phantom-pattern catalog (UNCHANGED from v48)

Seven patterns. v50 adds no new patterns. The May 25 wave caught
three of the existing patterns in flight, all repaired before ship:

1. **Phantom-delivered** — handoff says X shipped, HEAD says no.
2. **Phantom-undelivered** — handoff says X is pending, HEAD says
   shipped. *(Caught in SYN.3: the userMemories' "Drop 6D contest
   block deletion" was scoped as upcoming, but a HEAD grep showed
   the deletion had not happened yet at the start of the session
   — userMemories was the wrong way around. The actual deletion
   shipped in SYN.3.)*
3. **Dual-source drift** — content scrubbed in one location but
   a mirroring literal not scrubbed.
4. **Stale-test-fixture drift** — test fixture mirrors live state;
   state changes but fixture doesn't.
5. **Inverted-narrative phantom** — userMemories records X as open
   when X is delivered at HEAD, or vice-versa.
6. **Sandbox-divergence phantom** — chat sandbox contains files or
   symbols that get reported as "shipped" but never reach Windows.
7. **Import-load syntax phantom** — import-load verification
   statement is syntactically wrong even though the underlying
   symbol exists.

The SYN.3 case is documented as a phantom-undelivered catch.

### §6.3 Smoke as wiring-verification (unchanged)

### §6.4 Verification matrix — post-SYN.5 HEAD (May 25 2026)

| Surface | Verified by | Status |
|---|---|---|
| `engine.contest.compute_anchor_hp` (SYN.3) | `from engine.contest import compute_anchor_hp; assert callable(compute_anchor_hp)` | ✓ green |
| `engine.contest.apply_contest_influence_multipliers` (SYN.3) | import-load | ✓ green |
| `engine.contest.on_npc_killed_in_combat` (SYN.3) | import-load | ✓ green |
| `engine.territory.adjust_territory_influence(region_slug=)` (SYN.1.a + SYN.3) | signature inspection + integration test | ✓ green |
| `engine.territory.claim_region` / `unclaim_region` (SYN.1.a) | import-load + test sweep | ✓ green |
| `engine.territory._get_region_landmarks` (SYN.1.a) | import-load | ✓ green |
| `engine.territory.on_npc_kill / on_mission_complete / on_pvp_kill` wilderness gate (SYN.5) | TestInfluenceHooksRetarget (9 tests) | ✓ green |
| `engine.security` wilderness-aware step 4 (SYN.2) | test_syn2 24 tests | ✓ green |
| `engine.player_cities.found_city_in_region` (SYN.4) | test_syn4a 30 tests | ✓ green |
| `engine.player_cities.claim_landmark_for_city` (SYN.4) | test_syn4a | ✓ green |
| `engine.player_cities.tick_city_vitality` (SYN.4) | test_syn4b 37 tests | ✓ green |
| `engine.player_cities.syn4_migrate_dissolve_city_map_cities` (SYN.4) | test_syn4b migration sections | ✓ green |
| `engine.intel_handlers.handover_intel` (SYN.5) | test_syn5 47 tests | ✓ green |
| `engine.intel_handlers.evaluate_intel_quality` (SYN.5) | TestEvaluateIntelQuality 7 tests | ✓ green |
| `parser.espionage_commands.IntelCommand.execute` handover branch (SYN.5) | manual code review (no parser-test infrastructure for the handover path yet) | ✓ wired |
| `parser.city_commands._handle_found` region form (SYN.4) | manual code review + downstream test | ✓ wired |
| `parser.city_commands._handle_claim` route-by-region (SYN.4) | manual code review + downstream test | ✓ wired |
| `server.tick_handlers_economy.city_vitality_tick` (SYN.4) | scheduler registration check | ✓ green |
| `server.game_server` city_vitality registration (SYN.4) | grep at HEAD | ✓ green |
| Schema v35 columns (SYN.1.b + SYN.3 + SYN.4) | `PRAGMA table_info` against sandbox DB after `ensure_schema` | ✓ green |
| Drop 6D contest block deletion (SYN.3) | `grep -n` confirms absence + retirement header present | ✓ green |
| `_apply_claim_upgrade` retirement (SYN.1.b) | grep at HEAD confirms absence | ✓ green |
| Legacy `found_city` + `claim_room_for_city` still operational (parallel-ship) | 520 cities tests green | ✓ green |
| `engine.cooldowns_enabled` (lives in `engine.jedi_gating`, NOT `engine.cooldowns`) | sandbox verification | ✓ corrected during SYN.4 |

All 299 SYN tests pass at HEAD. 1,430-test SYN-and-adjacent sweep
green.

### §6.5 Smoke-flagged design issues (unchanged)

None outstanding from the May 25 wave.

### §6.6 Import-load discipline (unchanged from v48)

Import-load verification statements MUST target module-level
symbols. For method-on-class wiring, the verification statement is
`from <module> import <ClassName>` plus
`assert callable(getattr(<ClassName>, '<method>'))`.

### §6.7 Post-SYN HEAD state (REGENERATED v50)

Engine modules (114): all import-loadable. The new `engine/contest.py`
and `engine/intel_handlers.py` are AST-clean and pass their
respective test sweeps. The expanded `engine/territory.py` retains
all its pre-SYN surfaces (parallel-ship); the new surfaces are
import-load verified per §6.4.

Parser modules (55): all import-loadable. The two retargeted
modules (`parser/city_commands.py` for SYN.4 routing,
`parser/espionage_commands.py` for SYN.5 handover) pass downstream
tests.

Server modules (16): unchanged structurally; `server/game_server.py`
and `server/tick_handlers_economy.py` have new tick registrations
(SYN.1.a, SYN.3, SYN.4).

Schema v35: SYN.1.b column add + SYN.3 two-table add + SYN.4
two-column add. All idempotent via additive ALTER + IF NOT EXISTS
on CREATE.

---

## §7. Design doc map

(Updated for the SYN wave. Other rows carried forward from v48/v49
unchanged.)

| Surface | Design doc | Status |
|---|---|---|
| Contestable Wilderness pivot (all SYN drops) | `contestable_wilderness_design_v2.md` | **LOCKED 2026-05-24; SYN.0–5 SHIPPED** |
| Web client lane (all phases) | `web_client_vision_and_protocol_v1_2.md` | v1.2 LOCKED; bug-fix sprint pending |
| Map renderer reference | `Map_Redesign_v2.html` | Approved mockup; renderer port pending (subsumed under web client Phase 3) |
| Player Cities v1.2 | `player_cities_design_v1_2.md` | Feature-complete pre-SYN; SYN.4 retargets the founding/expansion model |
| Player Cities v1.2 SYN supplements | `contestable_wilderness_design_v2.md` §2.9 | LOCKED |
| Territory contestation | `contestable_wilderness_design_v2.md` §2.4, §3.3 | SYN.3 implementation SHIPPED |
| Espionage-as-influence | `contestable_wilderness_design_v2.md` §2.7, §3.5 | SYN.5 implementation SHIPPED |
| Active harvest | `contestable_wilderness_design_v2.md` §2.5, §3.6 | SYN.6 pending |
| Wilderness anomalies | `contestable_wilderness_design_v2.md` §2.8, §3.7/§3.8 | SYN.7/8 pending |
| Building construction | `contestable_wilderness_design_v2.md` §2.9.3, §3.9 | SYN.9 pending |
| Display integration | `contestable_wilderness_design_v2.md` §2.6, §3.12 | SYN.10 pending |
| Security Model v1 | `security_model_design_v1.md` | live (with SYN.2 wilderness-aware branch added) |
| Progression Gates (PG.1/2/3) | `progression_gates_and_consequences_design_v1.md` | PG.1 + PG.2 + PG.3 Acts 1/2 SHIPPED |
| Padawan-Master | `padawan_master_system_design_v1.md` | launch-scope SHIPPED; council/lineage post-launch |
| Director AI | `director_ai_design_v1.md` | base SHIPPED; T3.15 CW-tuning post-launch |
| Director AI ↔ SYN.5 intel handover | `director_ai_design_v1.md` + `contestable_wilderness_design_v2.md` §2.10 | heuristic stub SHIPPED at SYN.5; T3.15 will swap |
| Weight of War | `weight_of_war_design_v1.md` | MVP_COMPLETE 2026-05-24 (Brian-confirmed) |
| Combat Posing | `combat_posing_narrative_design.md` | SHIPPED |
| Espionage (base) | `competitive_analysis_feature_designs_v1.md` §F | SHIPPED |
| Player Housing | `player_housing_design_v1.md` | SHIPPED |
| Faction Reputation | `faction_reputation_design_v1.md` | SHIPPED |
| Organizations | `organizations_factions_design_v1.md` | SHIPPED |
| Player Shops | `player_shops_design_v1.md` | SHIPPED |
| Wilderness movement | `wilderness_system_design_v1.md` + supplements | SHIPPED |
| Tutorials | `cw_tutorial_chains_design_v1.md` | SHIPPED |
| Coruscant Underworld build | `cw_content_gap_design_v1.md`, `coruscant_underworld.md` | content pending |
| Force-resonant landmarks | `force_resonant_landmarks_design_v1.md` | SHIPPED |
| Jedi Village | `jedi_village_quest_design_v1.md` | SHIPPED |
| Economy (Phase 1) | `economy_design_v02-1.md` + `economy_hardening_design_v1.md` + `economy_bulk_premium_design_v1.md` | SHIPPED |
| Spacer quest | `from_dust_to_stars_design_v2_clone_wars.md` | SHIPPED |
| Sabacc | (Galaxy Guide extraction + parser/sabacc_commands.py) | SHIPPED |
| Hyperspace | `space_overhaul_v3_design.md` + `npc_space_traffic_design_v2.pdf` | base SHIPPED; Wildspace post-launch |
| Encounters/Hazards | `competitive_analysis_feature_mining_v1.md` + supplements | base SHIPPED |
| Spaceflight (cargo/customs/sabacc-on-ship) | `gg6_tramp_freighters_extraction_v1.md` + extractions | SHIPPED |
| Codex (in-game help guides 01–26) | each `Guide_XX_*.md` | SHIPPED |

---

## §8. Outstanding decisions

(Most carried forward from v48/v49. The SYN wave closed a few
items; some new ones are added.)

### §8.1 CW pivot tactical questions

Carried forward from v48 unchanged.

### §8.2 Progression Gates open questions

Carried forward from v48.

### §8.3 Smoke-flagged design issues

None outstanding.

### §8.4 Smoke harness open questions

Carried forward.

### §8.5 Security Model open questions

- Coruscant naming reconciliation (Tier 2 #10).
- Overdose-difficulty bump for cross-type stim attempts: not in
  scope for SECMOD.1; tracked under SRB.1 follow-ups instead.

### §8.6 Support Role Buffs open questions

Carried forward from v48.

### §8.7 Player Cities open questions (UPDATED v50)

(Was v48 "design-locked, feature-complete"; v50 adds the SYN.4
items.)

- **SYN.4 `effective_tax_rate_cap` consumer wiring.** Seam in
  place; the consumer at `set_city_tax_rate` is unwired. Players
  can still set tax up to the base cap regardless of vitality
  state. Small follow-up.
- **SYN.4 dissolution migration application timing.** The
  migration is an explicit admin invocation (`await
  syn4_migrate_dissolve_city_map_cities(db)`), not a server-boot
  tick. When does Brian want to run it in production? The
  idempotency marker makes re-running safe; the question is
  whether to run it before or after the next launch checkpoint.
- **Legacy cities tests retargeting.** 520 tests still use legacy
  fixtures. Retargeting them to wilderness fixtures is ~2 sess
  and depends on the migration having run. Post-launch.

### §8.8 Jedi Village build open questions

CLOSED.

### §8.9 Wilderness Co-location remediation open questions

CLOSED (May 17 wave's W.2.4).

### §8.10 Map redesign open questions

(Carried forward from v49.) Superseded by the web-client lane;
the production port is Tier 1 #3 (bug-fix sprint) + subsequent
production-port drop.

### §8.11 +pvp opt-in tuning

Carried forward from v48. No griefing patterns observed.

### §8.12 Sandbox-divergence phantom prevention

(Carried forward from v48 as Pragmatic discipline with quarterly
Conservative sweep.)

### §8.13 Coruscant Underworld scope (UNCHANGED from v48)

Design call needed: author standalone 40×40×3 region file OR use
landmarks as anchors in implicit grid.

### §8.14 Long-wave drop discipline lessons (UNCHANGED from v48)

Validated again by the May 25 SYN wave.

### §8.15 Web client implementation path (UNCHANGED from v49)

Path B chosen. Engineering Claude fixes design drop before
production port. Currently on pause behind SYN sequence.

### §8.16 Web client launch-scope cutoff (UNCHANGED from v49)

Open question: where does the launch-scope cut between web-client
phases land? Vision Phase 0–1 is launch-blocking; Phase 2 is
mostly post-launch; Phase 3 ships incrementally. The cut point
within Phase 2/3 is Brian's call.

### §8.17 SYN sequence interleave question (NEW v50)

The SYN sequence is currently planned as five more sequential drops
(SYN.6 → SYN.10). At any point Brian may choose to interleave:

- **Web-client work** — Tier 1 #3 bug-fix sprint can land between
  SYN sub-drops without engine interference (per §4.27
  parallel-ship discipline).
- **Coruscant Underworld content** — likewise interleavable.
- **The two Brian design calls** — both are small implementations
  Brian could resolve any session.

The default assumption (v50 §3.7) is that SYN runs to completion
first, then web. Brian's stated preference for "UI as the goal as
soon as we finish this SYN pivot" supports this — but the door is
open.

### §8.18 Intel handler NPC seeding follow-up (NEW v50)

SYN.5 ships the engine; the content drop to spawn handler NPCs at
the 9 faction HQs is pending. Without that content drop, `+intel
handover` returns the clean "No intel handler for your faction is
here" message everywhere. Single small YAML or admin-spawn pass.

---

## §9. Version history

- **v50 (May 25 2026)** — full consolidation, the May 25 SYN wave.
  Contestable Wilderness pivot SHIPPED through SYN.5; SYN.6–10
  queued. Three new invariants (§4.25 wilderness-only influence,
  §4.26 region-anchored cities, §4.27 parallel-ship discipline).
  New process discipline (§5.9 SYN-sequence roll-up). Web client
  lane unchanged from v49 (on pause behind SYN).
- **v49 (May 24 2026)** — delta against v48. Web-client lane
  opened as first-class third lane. Vision/protocol doc v1.0 →
  v1.2 + Claude Design drop review folded in. Tier 1 #3 added
  (bug-fix sprint).
- **v48 (May 23 2026)** — full consolidation post-Player-Cities
  v1.2. Closes v47 Tier 1 #3 (HEAD re-audit). Adds invariants
  §4.21 (cities web-UI safety pattern) and §4.22 (combat-trigger
  state). Adds phantom pattern 7 (import-load syntax phantom).
- **v47 (May 21 2026)** — full consolidation post-rebuild wave.
  Recovers v44/v45 structural material from v46 + handoffs. Adds
  phantom pattern 6 (sandbox-divergence) and §6.6 import-load
  discipline.
- **v46 (May 22 2026)** — delta against v45 (lost). Superseded by
  v47.
- **v45 (presumed mid-May 2026)** — NOT IN PROJECT FILES.
  Referenced by v46 but absent.
- **v44 (presumed mid-May 2026)** — NOT IN PROJECT FILES. Material
  recovered into v47.
- **v43 (May 18 2026)** — full consolidation post-May-18 wave.
  Adds inverted-narrative phantom to catalog.
- **v40 (~mid-April 2026)** — earliest reference in current docs
  for the "web-first directive locked since" anchor.

---

## §10. Closing notes

### §10.1 What v50 retires from v49

- v49 Tier 1 #3 was the next-session item (bug-fix sprint).
  **v50 retains it as Tier 1 #3 but explicitly notes it's
  paused behind the SYN sequence.** When SYN.10 closes, this is
  the immediate next item.
- v48 Tier 2 #5–#8 (Security Model + F.MAP.4/5/7) — already
  retired by v49 (subsumed under web-client lane). v50 carries
  v49's retirement.
- v48 Tier 3 #17 #18 (sheet redesign, ground UX overhaul) —
  already retired by v49 (subsumed under web-client Phase 2).
  v50 carries forward.
- The Drop 6D zone-keyed territory contest block — **physically
  deleted in SYN.3**, replaced with a 24-line retirement header
  in `engine/territory.py` pointing at `engine/contest.py`. This
  is the cleanest retirement v50 records: no phantom, no
  parallel-ship period — the deletion shipped in the same drop
  the replacement shipped, because data migration (SYN.1.b)
  preceded it.
- `engine/security.py::_apply_claim_upgrade` — retired in SYN.1.b.

### §10.2 What v50 newly tracks

- The SYN sequence as Tier 1 #4 + Tier 2 #5–#8 (SYN.6 through
  SYN.10).
- Three new invariants: §4.25 (wilderness-only influence), §4.26
  (region-anchored cities), §4.27 (parallel-ship discipline).
- One new process discipline: §5.9 (SYN-sequence roll-up).
- One new audit anchor item: §6.4 verification matrix updated for
  all 299 SYN-wave symbols.
- Two new open questions: §8.17 (SYN sequence interleave with
  web), §8.18 (intel handler NPC seeding content drop).

### §10.3 What v50 keeps unchanged from v48/v49

- The engine/parser/server/data/static/test layer model.
- The phantom-pattern catalog (7 patterns; no new pattern from
  the SYN wave).
- The web-client lane phasing (Phase 0–5 per the vision doc).
- The drop-zip packaging discipline, the import-load verification
  discipline, the memory-hygiene discipline.
- The launch-scope reading (with SYN sequence additions inline).

### §10.4 The lesson of the May 25 SYN wave

**Six drops in one session.** All shipped clean, all green at
HEAD. The combined-drop discipline (§5.9) worked: SYN.3 packaged
the contest state machine + the Drop 6D deletion in one drop
because the data migration preceded the deletion; SYN.4 packaged
region-anchored founding + landmark expansion + vitality + the
75%-refund migration in one drop because they shared the same DB
schema delta. SYN.5 stayed single-scope because it was naturally
one drop's worth.

The parallel-ship discipline (§4.27) was the safety net. SYN.1's
new region-keyed surfaces shipped alongside the existing
zone-keyed ones; SYN.4's new region-anchored founding shipped
alongside the legacy city-map founding. The 520 cities tests
didn't move during the wave — they validated their legacy
surfaces, which the wave didn't touch. The new SYN tests validated
the new surfaces. No fixture retargeting, no test churn.

The wave caught one phantom-undelivered (the Drop 6D deletion was
scheduled in userMemories as upcoming but had not happened) and
one import-source error (`cooldowns_enabled` lives in
`engine.jedi_gating`, not `engine.cooldowns`). Both repaired in
flight. The phantom-pattern catalog from v47/v48 is doing its
job — patterns get named, then they get caught faster the next
time.

**The web-client lane is the next thing.** Per Brian's preference,
v50 documents the SYN sequence and the web-client lane as the two
remaining large work surfaces. SYN closes first; then the web
client takes the focus. The lane has not moved since v49 and v50
is intentionally faithful to that — there is no progress to
document, only patient parking.

### §10.5 What v50 explicitly does NOT trust

- **userMemories** still references some v45-vintage state. v50
  is grounded in HEAD (verified by AST + import-load + the 1,430-
  test SYN-and-adjacent sweep) and supplements with the May 25
  handoff docs (`HANDOFF_MAY25_SYN3.md`, `HANDOFF_MAY25_SYN4.md`,
  `HANDOFF_MAY25_SYN5.md`). userMemories should be refreshed at
  Brian's discretion to reflect SYN.0–5 closed.
- Older Contestable Wilderness design iterations (v1 if any exist
  in archive). `contestable_wilderness_design_v2.md` LOCKED
  2026-05-24 is the single source of truth.
- v48 and v49 as authoritative. v50 supersedes both.

### §10.6 The path to launch (current reading)

1. **SYN.6 → SYN.10** close the Contestable Wilderness pivot
   (~7–9 sessions).
2. **Web-client Tier 1 #3** (bug-fix sprint) — engineering Claude
   applies the May 24 design-review fixes to the v3 JSX.
3. **Production port** of v3-fixed → `static/client.html`.
4. **Web-client Phase 0–1** (protocol substrate, launch-blocking
   enabling work).
5. **Coruscant Underworld build** (if not already interleaved).
6. **Brian's two open design calls** (eavesdrop, skill_check_
   passed).
7. **Launch.**

Post-launch:
- Web-client Phase 2 (rich panels, the bulk).
- Web-client Phase 3 (map renderer + asset library + landmark
  illustrations, ships incrementally).
- Cities multi-city-per-org, P2P city discovery.
- Padawan-Master council politics, formal lineage trees.
- Space Wildspace expansion.
- Director AI CW prompt tuning (T3.15).
- PG.3 Act 3 formal Knighting trial.
- Legacy cities tests retargeted to wilderness fixtures + legacy
  founding surfaces removed.
- Web-client Phase 4 (diegetic polish) and Phase 5 (mobile).

---

*v50 consolidates the May 25 SYN wave. Contestable Wilderness
pivot is half-shipped (SYN.0–5 done; SYN.6–10 queued). The
parallel-ship discipline kept the legacy surfaces honest while
the new ones shipped. The web-client lane stays paused behind
SYN per Brian's preference. The path to launch is again
well-defined; what's left is execution.*
