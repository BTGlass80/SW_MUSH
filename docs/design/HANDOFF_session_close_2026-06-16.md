# Session close-out + handoff — 2026-06-16

*For the NEW interactive dev chat. Read `CLAUDE.md` + `MEMORY.md` +
`memory/inflight-overnight-2026-06-15-solo.md` + `OPUS_CLAIM.md` first, then this.
**Trust `git log origin/main` + `CHANGELOG.md` + `TODO.json` over any doc** — main moves
fast (two durable loops + interactive sessions all push to it).*

## 0. ⚠️ READ FIRST — API COST + the ANTHROPIC_API_KEY in env (Brian's standing concern)

Brian funded the Anthropic API with **$30** (2026-06-16) for the **live Director at launch**, and
was emphatic: *"go easy on it. We MUST not blow through it."* The earlier $45 was blown FAST by the
durable dev loop running on the **metered key billing Opus** (~$31/day). That failure mode is now
structurally closed — keep it that way:

- **The durable loops run on the flat-rate Max SUBSCRIPTION, never the metered key.** Both launchers
  (`SWMUSH-DurableLoop`, `SWMUSH-OpusLoop`) do `set "ANTHROPIC_API_KEY="`. **NEVER point a loop —
  especially an Opus loop — at the metered key.** With $30 in the account now, a stray metered fire
  would *succeed* and burn it (before, the $0 balance fail-safed it).
- **The ONLY thing that should spend the $30 is the live Director** — `ai/claude_provider.py`
  `ClaudeProvider`, model `claude-haiku-4-5` (cheap), **hard-capped by an in-code circuit breaker at
  $20/mo (fires at 90% = $18)**, graceful "" fallback, monthly reset. It cannot blow $30 fast. At
  that cap $30 lasts ~1.5+ months. To tighten: lower `make_claude_provider(monthly_budget_cents=…)`
  in `ai/providers.py` (could be made an env var — offered, not yet built).
- **`ANTHROPIC_API_KEY` IS set user-scope** → it will be present in THIS fresh chat's env too. That
  is *required* for the live Director (`make_claude_provider` reads it). The interactive session
  itself runs on the **subscription** (it worked while the key was at $0 — a metered session would
  have failed), so your normal Opus work is NOT billing the $30. **Stay frugal with Opus
  subagents/workflows anyway.** *(If the key-in-every-shell makes you uneasy: it can be removed from
  user-scope and injected only at game-server/Director launch — a config change to Brian's
  environment, not done here.)*
- #1 (live Director) was **verified live 2026-06-16** with a single Haiku probe — cost $0.0000004.
- Full detail + the standing rule: `memory/anthropic-api-box-blockers.md`.

## 1. Where things are
- **`origin/main` HEAD = `518bf65`** (T3.21 read-only connection pool). **48 commits** shipped since
  the 2026-06-15 handoff (`76f9b65`) — see `git log 76f9b65..origin/main`.
- **Worktrees / drivers (each its OWN git worktree → no file collisions; only CHANGELOG/TODO
  union-merge):**
  - Interactive dev chat → **`c:/SW_MUSH`** (this is where the fresh chat runs).
  - **Sonnet content loop** → `SWMUSH-DurableLoop`, worktree `C:/SW_MUSH_loop`, hourly, prompt
    `loop_resume_solo_2026-06-15.md`.
  - **Opus quality loop** → `SWMUSH-OpusLoop`, worktree `C:/SW_MUSH_opus`, every 90m, prompt
    `loop_resume_opus_quality_2026-06-15.md`.
  - Both armed + healthy (LastResult=0). Disarm: `python C:/SW_MUSH_loop/tools/durable_loop.py
    disarm` and `… disarm --name SWMUSH-OpusLoop`.
- **Coordination file both loops read each fire: `C:/Users/btgla/.claude/projects/c--SW-MUSH/OPUS_CLAIM.md`**
  — the lane partition + Brian's decisions + what's shipped. Keep it current if you change lanes.
- **Branches with preserved WIP:** `drop/cmd-syntax-drop0` (tip `c60e04a` = command-syntax Drop-0 WIP:
  `register()` collision-recording + the frozen `tests/data/command_convention_baseline.json` of 135
  collisions — UNTESTED, needs the summary-warn + the convention test before merge); `design/command-syntax-rework`
  (the v1 design doc). The design docs (v1 + v2) are already on `main`.

## 2. Brian's launch decisions (2026-06-16) + status
1. **Director LIVE at launch** (API funded $30) → ✅ **DONE** (TLS fix already in place, verified live).
2. **T3.16 refinery (`REFINE_RTYPE_DEFERRED`)** → **DEFER post-launch** (do not build).
3. **Read-only SELECT connection pool** → ✅ **DONE** (`518bf65`; `db/database.py` read pool, mode=ro,
   9 tests, code-review-hardened).
4. **G4 combat-events feed + G13 Director zone-feed** → **PRE-LAUNCH, ATTENDED-Opus, STILL TODO.**
   Both avoid-lane (`combat.py` / `director.py`) — surgical careful passes. **This is the only attended
   item left.**
5. **T3.19 telemetry = sink + broad emitters** → Opus loop (non-director parts).
6. **CORS = same-origin no-op** → Opus loop (document + assert).
7. **Cities `+city found` launch feature-flag (gated OFF)** → Opus loop.

(Earlier resolved forks: `SEC.player_online_activity_visibility` = PUBLIC by design;
`PM.approval_pending_store`, `CITY.dissolution_refund_formula`, `ERA…` all shipped.)

## 3. Two execution buckets (this is the operating model)
- **🤖 UNATTENDED LOOPS** (already running, no babysitting): command-syntax rework Drops 0–5 (Opus
  loop, per `docs/design/command_syntax_rework_design_v2.md`), guides authoritative quality pass (Opus
  loop — guides are Opus-owned now), telemetry sink+emitters (#5), T3.21 LOW/MED tail, CORS (#6),
  Cities flag (#7), help-corpus tail (Sonnet loop).
- **👤 ATTENDED Opus** (needs a present/careful session — do NOT hand to the unattended loop):
  **#4 G4/G13** is the only one left. (#1 live-Director and #3 connection-pool are DONE.)

## 4. Command-syntax rework — RATIFIED, build assigned to the Opus loop
Brian ratified (2026-06-16): **A1 prefixes** (bare=IC / `+`=OOC/meta / `@`=staff), **switches PRIMARY**
(`cmd/switch`, MUSH idiom — `ctx.switches` already parses them), **CLEAN — delete redundant forms, NO
back-compat aliases** (nobody's playing yet), **do ALL** ~128 multi-prefix stems + 11 run-ons + 6
`@`-exceptions; `@desc`/`@mail` kept. **MUSH/MUX is the reference feel.** Plan + the 135-collision
finding: `docs/design/command_syntax_rework_design_v2.md`. Enforcement guard (Brian's "make future
commands conform") = Drop 0. The Opus loop owns Drops 0–5; it gates the doc rework, so it's the loop's
top priority. The Sonnet loop must NEVER touch command keys. **This rework collides with parser work —
keep it one focused branch; don't interleave.**

## 5. Launch estimate: ~1.5–2 weeks of dev
The overnight + today surge closed T3.16, T3.15, T3.21 (security), T3.22, T3.23, T3.19 Phase 1, the
DB pool, and most of the help/guide corpus. Remaining is mostly: command-syntax rework (Opus loop),
final hardening (full-suite-green on this box's flaky xdist + arch/doc v52 reconcile + the
SCHEMA_VERSION-now-46 catch-up), T3.19 telemetry, the T3.21 LOW/MED tail, #4, and the guide quality
pass. **The binding constraint is now your decisions + the hardening tail, not raw throughput.** Live
Director is no longer a blocker (funded + verified).

## 6. Operating mechanics (this box)
- **Gate = SINGLE-PROCESS targeted + `tests/smoke/test_smoke_foundation.py`**:
  `python -m pytest <touched tests> tests/test_todo_and_changelog_hygiene.py tests/smoke/test_smoke_foundation.py -o addopts= -p no:cacheprovider --timeout=120 -q`.
  **NEVER `-n auto`** (xdist orphan-swarms / hangs on this box). `run_all_tests.bat` (xdist full) is
  the pre-merge ground truth, not the inner loop. `C:/SW_MUSH/venv/Scripts/python.exe` has deps;
  pytest 9.0.2.
- **git:** `git checkout <branch>` is DENIED → use `git switch -c/-C` + `git push origin HEAD:main`
  for fast-forward merges; `git worktree add -b` works. Fetch + race-check before every push.
- **CHANGELOG.md / TODO.json** are high-churn (loops edit them): union-resolve CHANGELOG (keep all
  entries); **edit `TODO.json` by TEXT-SPLICING the `last_updated_note` value, NEVER a json
  round-trip** (it normalizes `\u` escapes across the whole file and conflicts).
- **AVOID-LANES** (unless explicitly lane-excepted like #4): `engine/harvest.py`,
  `engine/combat.py`/`death.py`/`npc_combat_ai.py`, `engine/director.py`.
- **Untracked in `c:/SW_MUSH` (preserve):** `.agents/`, `.codex/`, `AGENTS.md` (local Codex config).

## 7. Suggested first move for the fresh chat
Either: (a) take **#4** (G4/G13) — the last attended item — as a careful surgical pass; or (b) just
confirm the loops are healthy and let them grind the unattended bucket while you watch the API spend
(`@director budget` in-game, or `ClaudeProvider.get_budget_stats`). Nothing is blocked.
