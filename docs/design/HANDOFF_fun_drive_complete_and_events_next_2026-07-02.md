# HANDOFF — First-fun drive COMPLETE; next focus = Events → playable scenarios (2026-07-02)

## TL;DR
- **`main` is green** (only accepted red: `test_cities_phase4b::test_dock_sell_in_city_credits_city`, a long-standing cargo-tax baseline). HEAD at handoff: **`1194bf6`**.
- **`c:\SW_MUSH` (Brian's live tree) is now synced to `main`.** It had been 173 commits behind on `drop/sidebar-contract-handoff-capture`. His 2 local edits (`docs/design/INDEX.md`, `tools/mapgen/term_boundaries.json`) are **stashed** in that repo — recover with `git -C c:/SW_MUSH stash pop`.
- **The first-fun drive is DONE and validated**: 8th fun re-run = new-player *would-keep-playing TRUE*, scores 4/4/4/3/4/4 (from 2s), "the tutorial is the best part of this game and it lands," open world reached.
- **All four of Brian's 2026-07-01 design forks are addressed** (see below).
- **NEXT MAJOR FOCUS (Brian's call this session): Events → playable scenarios — vertical-slice the Cult of the Hollow Sun.** NOT started (handoff came first).

## Operating model (READ FIRST)
- **Worktrees, not the live tree.** All work lands on `main` via per-session git worktrees. This session used **`C:/SW_MUSH_grind`** (drop worktree) and **`C:/SW_MUSH_ux`** (fun-pass re-runs). `c:\SW_MUSH` is Brian's view — keep it on `main`. Drive via `git -C <worktree>`.
- **Land pattern:** branch `drop/<name>` off `origin/main` → implement + targeted tests → **two-phase gate** → land. CHANGELOG + TODO update in the same drop.
  - **⚠ ff-pattern changed this session:** `main` is now **checked out in `c:\SW_MUSH`** (Brian's tree was synced to it), so `git branch -f main HEAD` fails (`cannot force update the branch 'main' used by worktree`). Land instead with **`git -C <worktree> push origin HEAD:main`** (re-fetch first; if BEHIND, merge `origin/main` + re-gate), then **`git -C c:/SW_MUSH pull --ff-only origin main`** to keep Brian's tree current. (Alternative: move `c:\SW_MUSH` back onto a throwaway branch to restore the old `git branch -f main` flow.)
- **Two-phase gate** (the OpusLoop reds the gate between drops — this catches it):
  - Phase 1: `python -m pytest tests/ --ignore=tests/e2e -n auto --dist loadscope -p no:cacheprovider --continue-on-collection-errors --maxfail=300 -o addopts= -m "not smoke and not smoke_slow and not slow" -q` (~2.5-4 min, ~14,180 pass).
  - Phase 2: `python -m pytest tests/smoke -m smoke -k foundation -o addopts= -p no:cacheprovider -q` (~16s).
- **OpusLoop is VERY active on `main`** (T3.24 questlines + guides + telemetry + G5, ~90m cadence). It **red-the-gate twice this session** (a field-kit false-positive regex from the g5 drop + a winnability-band test catching the Bohrus Kang vibroaxe design-call). Both fixed. The per-drop gate is the safety net — always Phase-1 before ff. Brian was FYI'd; a loop-mandate tightening is an open option he hasn't actioned.

## This session's work (all on `main`)
The **fun drive** — peeling the first-fun path layer by layer across **8 fun re-runs** (the `tools/_fun_wf_run.js` Playwright harness, 4 archetypes + audits). Each re-run's #1 kills-it, fixed:
- **fun6** `576631d` — sim combat safe-sandbox: no-KO + `_SIM_STUN_CAP=1` (stun-accumulation soft-lock in the tutorial drill).
- **fun7** `6ec438f` — graduate reward loop: ALL 8 CW chains were stranding graduates in 0-exit vendorless pockets; retargeted 7 chains to live vendor-hubs + 3 new `ai_config.vendor` outfitters (Brekka Solwynn/coco_town, Muss Farren/nar_shaddaa_promenade_main, Orvak Tesh/kuat_ring_commercial).
- **fun8** `a609e66` — bare `accept` auto-takes the tutorial mission (step-3 soft-lock: opaque hash mission-ids).
- **fun9** `2329a57` — boards location-neutral (were hardcoded "Mos Eisley" on Kamino).
- **fun10** `56d63b0` — sim auto-poses players so spamming `attack` WINS (multi-action-stacking soft-lock; `_auto_pose_sim_players` in `_start_posing_window`).
- **fun11** `2e779f1` — GOALS panel populates at graduation (the accepted mission was filtered by `is_chain_mission_visible_to` applied to an already-accepted mission).
- **fun12** `ddef084` — every in-game unknown command → the helpful recovery (not just question-like) + `go`/`walk`/`head <dir>` → MoveCommand.
- **fun13** `e0dbcfb` — `inventory`/`inv`/`i` → `+inv` back-compat aliases (Brian's call; reverses the rework's terse-canonical deletion for these reflexes).
- **fun14** `db7e1b1` — winnability band admits MELEE foils (accept the vibroaxe; judged on `melee_combat` via new `_primary_to_hit`; resolved `BAL.condemned_hull_melee_foil_band`).
- **fun15** `9a3f083`(+`4b85676`,`bc8f21c`) — `goals`/`situation`/`list` text-status commands + `presence`→`+who` (reflex words become real commands). Gate caught fun15's `goals` prefix-colliding with `go` and breaking movement — fixed (route go/walk/head before the registry prefix-match).
- **fun16** `1194bf6` — zone-keyed ambient audio system (client-only; off by default; silent until CC0 loops added).
- Also fixed a loop-red field-kit false-positive (`569246d`) and groomed the vibroaxe design-call to `resolved_recent`.

### The 4 forks Brian answered (2026-07-01)
1. **Command-vocab aliases** → build them (fun13 = inventory family; fun15 = goals/situation/list/presence). The rest of the reflex words fold into the command-syntax-rework.
2. **`BAL.condemned_hull_melee_foil_band`** → accept the vibroaxe + widen the band (fun14). RESOLVED + groomed.
3. **`UX.living_sheet_delta`** → keep per-view (no build; shipped default).
4. **`FUN.shop_verb`** → fold the `shop`→`+myshop`/`+vendor` rename into the command-syntax-rework (no standalone build).

## NEXT WORK — priority order

### 1. PRIMARY: Events → playable scenarios (vertical-slice the Hollow Sun)  ← the decided next focus
See memory `events-must-be-playable-scenarios.md`. Brian (2026-06-21, after playing Cult of the Hollow Sun): **typing `rally strike` isn't gameplay.** Events should be **go-to-a-location + cooperate + waves of enemies + varied skill objectives (e.g. slice terminals) → resolve**. Current cults are a global menace counter (MVP, "design-open").
- **Approach (Brian's standing direction): COMPOSE existing engines, reuse — don't rebuild.** Vertical-slice the Hollow Sun as the proof.
- **Reusable engines to map + compose** (recommend an Ultracode understand+design workflow FIRST — I was about to launch exactly this):
  - **Current cult/event mechanics** — `engine/world_events.py` (the menace counter, `rally strike`, event lifecycle, `active_events()` / `get_status()`; the WorldEventManager singleton `_manager` — reset to None between tests).
  - **Wilderness-anomaly multi-phase combat** — the staged waves engine (find the anomaly multi-phase encounter runner).
  - **Skill-mode / `perform_skill_check`** — for the varied-skill objectives (slice a terminal, etc.).
  - **Chain-step / questline engine** — `engine/chain_events.py` staged-step machine (go-to-location + step completion) — the scaffolding for a multi-step location scenario.
- **Design target:** an event fires → a location beacon (go there) → cooperate + WAVES (wilderness-anomaly combat) → varied SKILL objectives (skill-mode) → resolve → reward + menace reduction. Minimal new code; lean on the four engines.
- This is a MAJOR feature (multi-phase: understand → design → build → verify). Do it as its own sequence of gated drops.

### 2. 36th questline arc — add a civilian big-ship VENUE (Brian's call)
Resolves `QUEST.t3_24_36th_arc_skill_pool_exhausted` (design_calls_pending_brian). The T3.24 loop is PAUSED because every clean skill pool is exhausted (35 arcs shipped). Brian chose: **author a civilian capital-ship VENUE** to unlock the capital-ship COMBAT-arc shape (currently blocked by the civilian-big-ship-room problem). Once the venue exists, the 36th arc (a capital-ship combat questline) becomes buildable — either by the T3.24 loop or directly. Update the QUEST design-call entry (pending → resolved-with-decision) when actioned. See `inflight-t3-24-questline-expansion.md` for the per-arc history + fresh-room-sweep discipline.

### 3. Sound — awaiting Brian's CC0 files
The fun16 system is ready + silent. Brian sources CC0-licensed seamless `.ogg` loops and drops them at `static/audio/<track>.ogg` (`cantina`, `spaceport`, `market`, `deep-space`, `city` — see `static/audio/README.md`). They auto-play by zone once a player flips the `SOUND` toggle. I cannot source/download audio.

### 4. Light follow-ups (no decisions needed)
- **TODO grooming:** move the answered forks (`FUN.shop_verb`, `UX.living_sheet_delta`, and `UX.sound_atmosphere` once built) from `design_calls_pending_brian` → `design_calls_resolved_recent`. Do it with **validated text-surgery** (parse-move-write by brace-matching; NOT a json round-trip — TODO.json is loop-contended and a reformat conflicts). The grooming test `test_todo_design_calls_grooming::test_pending_has_no_resolved_entries` flags RESOLVED/EXECUTED/DEFERRED markers left in pending.
- **Command-syntax-rework pass:** the coherent review where `FUN.shop_verb` + a principled newcomer-alias/canonical policy live (fold in fun12/13/15's ad-hoc additions). Note the tension: the rework RATCHETS DOWN commands (baseline-collision guard in `test_command_syntax_drop4/drop5`), while the fun drive ADDED newcomer commands/aliases — each addition needs a guard update. Pre-req for the doc rework.

## Gotchas
- **Loop-contended files:** `CHANGELOG.md` and `TODO.json` change under you constantly (OpusLoop). Re-read before each Edit; merge with union-resolution (strip `<<<`/`===`/`>>>`, keep both entries) at ff time.
- **`force_sensitive` is derived** — never a `save_character` kwarg.
- **World-YAML edits additive-only** (zero deleted lines); chains.yaml `drop_room` retargets are fine (no coordinates / not golden-snapshot-guarded).
- **Two standing pre-existing reds** (NOT to re-investigate): Bohrus Kang vibroaxe (now RESOLVED via fun14) and a `republic_soldier`/`separatist_commando` combat-RNG walkthrough flake.
- **`_fun_wf_run.js`** (fun re-run) runs from `C:/SW_MUSH_ux` — sync it to `main` before each re-run so it tests the latest. Harness needs `NODE_OPTIONS=--use-system-ca PYTHONUTF8=1`.
