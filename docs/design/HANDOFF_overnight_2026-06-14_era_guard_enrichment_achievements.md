# HANDOFF — Overnight session 2026-06-14 — era-guard + free-LLM enrichment + achievement hooks

> Session D (the free-LLM enrichment lane, claimed in `COORDINATION_live_lanes_2026-06-13.md`).
> Acted as the integrating/main session for this shift (owned commit/merge/push).
> All 7 drops below are **on `origin/main`** and passed the full suite at least
> once (9338 passed at the last gate). Grounded in HEAD; verify before acting.

## What shipped (7 drops, one coherent arc)

| Commit | Drop | One-line |
|--------|------|----------|
| (1b1beb3→e564a2e) | `ollama-era-guard` | new `engine/era_validator.py` single-source era canon + runtime guard, wired into the 4 idle-queue tasks; migrated the era test + `tools/ingest_lore.py` onto the shared tuple |
| `f2bd145` | `idle-queue-rewrite-broadcast-guard` | fixed a latent EventRewrite broadcast-without-persist bug (TD.IDLE_QUEUE_EVENT_REWRITE_BROADCAST_WITHOUT_PERSIST, resolved) |
| `b95b834` | `ambient-dynamic-pool-era-guard` | era-filter the Director's LLM `ambient_pool` lines at `set_dynamic_pool`; logged `TD.AMBIENT_INJECT_ONCE_PHANTOM` |
| `a14df14` | `npc-dialogue-era-guard` | era-guard the primary `talk <npc>` path (highest-traffic LLM→player surface) + fixed a latent double-random-`_get_fallback()` mismatch |
| `b7f684e`→`5ad559c` | `ambient-flavor-feeder` | Ollama-generated ambient room flavor (the idle GPU enriches rooms) — first enrichment on the era-guard substrate |
| `5ddf58b` | `org-rank-achievement-hook` | wire `on_org_rank_reached` in `organizations.py::promote` → unblock `faction_loyalist` (was unwinnable) |
| `3e7a8ae` | `scene-achievement-hook` | wire `on_scene_completed` in `scenes.py::stop_scene` → unblock `storyteller` (was unwinnable) |

**Arc:** (a) closed **every live LLM→player era hole** — the runtime era-guard the
`free_llm_enrichment_roadmap_v1.md` named as its load-bearing STEP-0 prerequisite;
(b) shipped the **first enrichment** on that substrate (Ollama ambient flavor —
valuable precisely because the paid Director path is credit-gated on Brian's box);
(c) opportunistically fixed **2 engine-side defect-hunt findings** (unwinnable
achievements) found via the parallel session's `HANDOFF_defect_hunt_findings_2026-06-14.md`.

## The era-guard substrate — `engine/era_validator.py` (NEW, pure stdlib)

Single source of truth for Clone Wars era cleanness. Exports:
- `BANNED_ERA_TOKENS` / `CANONICAL_FIGURES` — the canon (lifted from the two former
  divergent copies in the era test + `ingest_lore.py`; both now `import` it; a
  `tests/test_era_validator.py` identity assert prevents re-drift).
- `era_violations(text)` / `is_era_clean(text)` — runtime drop-gate (case-insensitive
  substring; errs toward dropping — a false-drop costs one pool entry, a false-accept
  leaks off-era text to players).
- `ERA_PROMPT_HINT` — CW prompt-hardening prepended to every LLM generation prompt.

**Guarded surfaces (all live LLM→player output now passes through it):**
`engine/idle_queue.py` (AmbientBark/SceneSummary/EventRewrite/HousingDesc tasks) +
`engine/ambient_events.py::set_dynamic_pool` (Director ambient) + `set_idle_pool`
(Ollama ambient) + `ai/npc_brain.py::dialogue` (NPC `talk`).

## Enrichment — `ambient-flavor-feeder` architecture (reuse this pattern)

`engine/idle_queue.py::AmbientFlavorTask` (Ollama) → `AmbientEventManager.set_idle_pool`
(era-guard + length/count cap via a shared `_validate_lines` helper) → a **NEW
`_idle_pool` kept SEPARATE from the Director's `_dynamic_pool`** (the Director
`.clear()`s its pool each Faction Turn — two LLM writers must not share a pool) →
`_pick_line` draws its 30% "live" line from **both pools combined**. Seeded by
piggybacking `seed_barks_for_populated_rooms` (one task per occupied zone, refresh-gated).
Fail-safe end to end (guarded idle task + guarded seed block + drop-on-bad-JSON).

## Open follow-ups (well-scoped for the next session)

### 1. Variant-pool generator — the roadmap keystone (HIGH value, my lane, deferred)
`free_llm_enrichment_roadmap_v1.md` step 1: generalize the bespoke caches into one
generic keyed variant-pool pre-generator (`VariantPoolTask(surface_key, ctx, n)` +
`_variant_pools[key]` + `get_variant(key, fallback_fn)` with the era-guard + grounding
baked in). There are now **THREE** Ollama caches to migrate for parity: `_bark_cache`,
`_housing_desc_cache`, and the new `_idle_pool` (ambient). All in `engine/idle_queue.py`
+ `engine/ambient_events.py` (my files — zero collision). **Why deferred:** it's a
refactor of *working* code whose payoff (the ~35 new surfaces) is mostly **blocked**
— those surfaces live in `parser/` (Session B's command-syntax lane) or are
mechanics-coupled (space/wilderness anomalies carry dice/verb text). Do it when the
parser lane clears, OR when a 2nd clean engine-side surface justifies the substrate.

### 2. Remaining defect-hunt A1 achievement hooks (still unwinnable)
2 of 8 fixed this session (both had **engine-side** seams the defect-hunt mapped to
parser). The rest seam into `parser/` (Session B) or contested files:
- `on_item_crafted`, `on_experiment_success` → crafting success (parser/`crafting_commands.py`; engine/`crafting.py` *might* have a completion point — check)
- `on_trade_goods_sold` → trade/commerce sell (parser)
- `on_ship_launch` → launch (parser/`space_commands.py`; check engine/space for a launch fn)
- `on_anomaly_salvaged` → `engine/space_anomalies.py::remove_anomaly` is engine, but the salvage **loot-grant** (the real completion) is in `parser/space_commands.py`
- `on_dark_side_atoned` → atonement (parser/`force_commands.py`; engine/`dsp_hunter.py`?)
Pattern: one `try/except`-wrapped `await on_X(...)` at the seam (copy
`organizations.py::promote` or `scenes.py::stop_scene` from this session). Verify the
achievement event exists in `data/achievements.yaml` first (no phantom emit).
Also A2 (intercept arg-order, parser) and A3 (sabacc rake faucet/sink, parser, economy).

### 3. Logged tech-debt
- `TD.AMBIENT_INJECT_ONCE_PHANTOM` (open) — `director.py:1490` calls a non-existent
  `AmbientEventManager.inject_once` → the Director ambient-delivery path is dead
  (always comlink-fallback). Fix needs `director.py`-side zone/session targeting
  (the comlink fallback actually targets the right PC; a naive engine impl would
  mis-target) — coordinate with the director lane.
- 2 minor era-guard follow-ups (by-design, in `TD.IDLE_QUEUE_EVENT_REWRITE...` notes):
  ingest `validate()` case-sensitivity; `era_violations` "mauled"/"rebellion" over-drop.

## Memory / posture updates made this session
- `anthropic-api-box-blockers` — **TLS blocker is RESOLVED, not latent**:
  `ai/claude_provider.py::_build_ssl_context()` already uses `truststore` (Windows
  cert store) — verified in code. Only the $0-credits half remained (and that's now
  $45 per the memory). Don't re-investigate the Director SSL path as broken.
- `overnight-autonomy-posture` — sharpened: in unattended mode, don't use
  AskUserQuestion for choices I can default (Brian: "I wasn't expecting those").

## Coordination notes (shared-branch reality)
All "parallel sessions" share ONE working tree on branch `drop/t3-20-safe-load` and
commit onto it (local HEAD advances when another session commits). `origin/main`
moved on nearly every push tonight (5+ active sessions). Working model that held up:
(1) re-read CHANGELOG/TODO immediately before editing; (2) for the high-churn
CHANGELOG/TODO, **atomic Python splice + immediate commit** beats the Edit tool's
read-then-write race (which kept hitting "modified since read"); (3) stage only my
own files explicitly (never `git add -A` — the tree carries other sessions' WIP +
scratch like `_defect_findings.md`); (4) push = `git fetch` → if behind, `git merge
origin/main` (conflicts were ALWAYS only CHANGELOG/TODO, both additive — keep both),
re-verify, `git branch -f main HEAD` (checkout is denied), `git push origin main`.
The xdist orphan/contention check (`tasklist | grep python.exe`) distinguished real
parallel `-n auto` suites (workers with high CPU-seconds) from zombies — don't kill
a live parallel suite; don't launch a concurrent `-n auto` (thrash).
