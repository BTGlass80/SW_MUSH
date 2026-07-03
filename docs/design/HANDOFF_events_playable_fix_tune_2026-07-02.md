# HANDOFF — Events → playable scenarios: blocker fixed + tuned; next = generalize + 36th venue (2026-07-02)

## TL;DR
- **The big discovery:** the Events → playable-scenarios feature was **already built and live** on `main` (the 2026-06-24 `_events` lane). `engine/staged_event.py` + `engine/wilderness_anomalies.py` SCENARIO_TEMPLATES + the `communal_objective_runtime` orchestrator turn **3 of 5 cults** (Hollow Sun / Ember Court / Ashen Hand) into 3-stage site scenarios (wave combat → skill gate → boss), wired into the tick + `rally` locator. The 2026-07-02 handoff's "NOT started" was stale.
- **Live validation found a real blocker** the unit tests missed → **fixed + landed.** Then **tuned** per Brian's calls.
- **This session landed 3 drops to `main`:**
  1. `b6c6065` — **housekeeping**: 441 uncommitted → 0 (committed orphaned real work, gitignored scratch).
  2. `8a8b3ac` — **anomaly-defeat fix** (the blocker): all combat anomalies / all 3 staged cults now completable.
  3. `b00bc4c` — **Hollow Sun tuning** (menace ~6h + ~1000cr capstone) — *pending final gate at time of writing; land when green.*
- **Next lane (Brian's call): check the other session's resolved calls, then GENERALIZE (Drowned Choir + Iron Veil) + the 36th-arc civilian big-ship VENUE** — teed up below, deliberately NOT built unattended (higher-risk content; wants review).

## Git / operating state
- `main` = `8a8b3ac` (housekeeping + anomaly fix). The tuning drop `drop/hollow-sun-tuning` (worktree `C:/SW_MUSH_hsfix`) is committed at `b00bc4c`, gated, **land with `git -C C:/SW_MUSH_hsfix push origin HEAD:main`** (re-fetch first) → then `git -C c:/SW_MUSH pull --ff-only origin main`.
- Land pattern (main is checked out in `c:\SW_MUSH`): implement in a worktree → gate → `push origin HEAD:main` → ff-pull `c:\SW_MUSH`. `git branch -f main` fails (main is a worktree checkout).
- **Accepted baseline red** (NOT ours): `test_cities_phase4b::test_dock_sell_in_city_credits_city` (long-standing cargo-tax). The full Phase-1 gate is "green modulo this one".
- OpusLoop is live on `opus/auto` (T3.24 questlines + guides); it pushes to `main` on ~90m cadence — re-fetch before every push, merge `origin/main` if behind.

## Brian's 4 decisions this session (all actioned)
1. **Validate live first** → done: break-it agent drove the Hollow Sun scenario in-process, found the blocker.
2. **Menace clock** → **~6h "one session"** window. Implemented: `STAGED_MENACE_PER_MINUTE = 0.18` (tunable `communal.staged_menace_per_minute`), staged-only, in `advance_and_resolve`. Legacy strike-path cults keep 0.35.
3. **Win reward** → **bigger ~1000cr capstone + named loot**. Implemented: `WIN_CAPSTONE_CREDITS = 1000` (tunable) to each title-earning contributor via `adjust_credits`, + a one-off per-cult relic (`_CAPSTONE_LOOT`) to the top contributor. Updated the "rep-only/no-credits" contract in Guide_26 §3 + its guard tests.
4. **Boss difficulty** → **group finale as-is** (no change).

## The blocker fix (drop `anomaly-defeat-clear`, landed `8a8b3ac`)
- **Symptom:** combat stages (Hollow Sun / Ember Court / Ashen Hand + every combat wilderness anomaly) could not be completed via the normal `attack` loop — the stage stuck at 0/N forever.
- **Root cause:** combat ends at **incapacitation** (`CombatInstance.is_over` → `active_combatants` → `can_act_now`, `>= INCAPACITATED(4)`) and `_cleanup`/room-cleanup vanish the downed NPC there, but the anomaly kill-hook (`parser/combat_commands.py::_apply_combat_wear`, line ~1212) fired the clear only at `>= DEAD(6)`. You rarely one-shot to DEAD, so the last hostile was incapacitated, removed, never "killed" → anomaly never resolved.
- **Fix:** one-line gate change — anomaly clear now fires at `>= INCAPACITATED` (defeat = can't-act), aligning with the game's own victory model (bounty *capture* + achievements already treat incap as a win). Bounty / WoW.3a hooks stay DEAD-gated by design.
- **Test:** `tests/test_anomaly_defeat_clears_on_incap_2026_07_02.py` drives the REAL `_apply_combat_wear` parser loop (the seam the tier-2 tests never hit — they call `award_combat_anomaly_reward` directly).

## Deferred quick follow-ups (small, well-scoped)
1. **Persuasion/con cistern fallback.** The `hollow_sun_cistern_slice` (+ ember/ashen skill stages) *advertise* a "turn the farmers" persuasion/con/bargain path in `staged_event.py` skills[] and the objective text, but the anomaly template only rolls `security`/`computer_programming` (`_resolve_anomaly_skill` uses `_pick_better_skill(char, primary, secondary)` — 2 skills). **Fix:** add an `alt_skills` field to the 3 cult skill templates + extend the resolver to pick the best across primary+secondary+alt. Additive, opt-in per template, backward-compatible.
2. **Wave→wave re-engage polish.** When you clear a combat wave, combat ends and you `attack` again to engage the next wave (a stutter). `_advance_to_next_phase` spawns the next wave into the room but not into the active `CombatInstance`. Optional: chain waves into one fight (needs the combat ref threaded to the advance).

## NEXT LANE — generalize + 36th venue (Brian: "check the other session's work first, then this")
**The convergence:** the last 2 cults (**Drowned Choir**/Nar Shaddaa, **Iron Veil**/Kuat) are still on the legacy menace-counter path, held back because their worlds have **no wilderness substrate to anchor a scenario site** (`staged_event.STAGED_CULT_REGION` maps only the 3 staged cults; `is_staged()` gates the scenario path). This is the **same "anchor a venue in a non-wilderness world" problem** as the **36th-arc civilian big-ship venue** (`QUEST.t3_24_36th_arc_skill_pool_exhausted`, resolved-with-decision: author a civilian capital-ship venue to unlock the capital-ship COMBAT questline). **Solve the anchor-venue once → unlock BOTH.**

**Plan (design-first, then reviewed build):**
1. Decide the anchor-venue approach for a non-wilderness world. Precedent: `kuat_arrivals` is a clean *civilian* big-ship berth (the war-coded KDY rooms stayed OFF); the design-call #4 in `events_playable_scenarios_design_v1.md` §6 offers "bespoke authored shrine room vs. random landmark". For Drowned Choir/Iron Veil, either (a) anchor at an existing civilian room in their zone, or (b) author a small venue.
2. Author the 3-stage descriptors + SCENARIO_TEMPLATES for Drowned Choir + Iron Veil, mirroring the Hollow Sun exactly (combat wave → resolution:"skill" middle → boss), flip `is_staged` via `STAGED_CULTS`/`STAGED_CULT_REGION`. **No engine work** — the orchestrator is roster-agnostic.
3. Author the civilian big-ship VENUE (additive world-YAML, coordinate-guard-safe) that hosts the capital-ship combat arc → the 36th questline becomes buildable (capital-ship gunnery/piloting/shields skills already exist).
- See `docs/design/events_playable_scenarios_design_v1.md` §4 (generalization) + §6 (open calls), the wf_269ed484 understand→design workflow (engine maps + a 36th-arc venue scout), and `inflight-t3-24-questline-expansion.md`.

## Gotchas
- **TODO.json** is huge (38k tokens) + loop-contended; the hygiene test is **structural only** (parses + keys + dated CHANGELOG entry) — it does NOT require a per-drop TODO edit, so a tuning/fix drop needs only a CHANGELOG entry. Don't round-trip TODO.json (union-strip corrupts it).
- **CHANGELOG.md** is loop-contended — re-read before editing; merge origin/main before push.
- The capstone is a **bounded, Brian-sanctioned reward faucet** (one uprising per ~6h; general-economy sink) — consistent with the anomaly/questline reward faucets; the invariant-auditor may flag it, the rationale is in the CHANGELOG + code comment.
- `_LiveHarness` (`tests/harness.py`) drives the real parser in-process; `COR.force_post(db, session_mgr, cult_key=...)` posts + arms a staged scenario for a walkthrough.
