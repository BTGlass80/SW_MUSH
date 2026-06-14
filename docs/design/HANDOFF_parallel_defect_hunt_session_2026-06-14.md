# HANDOFF — Parallel defect-hunt session — 2026-06-14

> For the NEXT session continuing the parallel content/defect-hunt lane.
> Written from a clean stopping point: **all of this session's work is already on
> `origin/main`** (carried up by the shared-branch integrator). Everything below
> is verified against HEAD `9318b5b` at write time.

## TL;DR

Overnight defect-hunt + remediation. A 10-cell adversarial defect-hunt workflow
(Explore finders → adversarial verifiers) confirmed **30 real defects**; this
session shipped **4 fix drops** (all on `origin/main`), raised **1 design call**
(needs Brian), and wrote a **cross-session findings doc** so the rest aren't lost.
The other parallel session (era-guard/enrichment/achievements lane) is sharing
the same branch and has already started fixing the parser-domain findings I
flagged (it wired `on_scene_completed` + `on_org_rank_reached`).

`origin/main` @ **`9318b5b`** at handoff. Local `c:\SW_MUSH` (drop/t3-20-safe-load)
is synced to it, working tree clean.

## Shipped this session (all on origin/main)

| Drop | What | Files |
|------|------|-------|
| `encounter-count-range` | `TD.ENCOUNTER_COUNT_RANGE_IGNORED` fixed (Brian ruling: **ship, bias low**). `creature_library.creature_spawn_count` couldn't parse a `[lo,hi]` range (`int([4,6])` raised → always fell back to pack minimum); new `_roll_low_biased` (min of two uniform rolls) honors the range with a low bias. | `engine/creature_library.py`, `tests/test_encounter_count_range.py` |
| `tutorial-v2-era-remediation` | **Live B3 era-cleanness BLOCKER**: `tutorial_v2.py` REBEL_CELL + IMPERIAL_SERVICE (GCW Rebel/Imperial onboarding chains) were reachable in CW via `check_profession_chains` (gated only on `missions_complete>=2`, no era check). Gated dormant behind `_GCW_PROFESSION_CHAINS_ENABLED=False` + reworded 5 scattered off-era barks. | `engine/tutorial_v2.py`, `tests/test_tutorial_v2_era_cleanness.py` |
| `breaching-delete-failsafe` | `attempt_breach` swallowed a `delete_object` exception on the success path and still told the player the breach opened. Now returns honest `breached=False`. | `engine/breaching.py`, `tests/test_breaching.py` |
| `encounter-skillcheck-funnel` | **Always-on funnel bug**: `encounter_{anomaly,hunter,patrol,pirate,texture}._skill_check` called the *sync* `perform_skill_check` as `await …(char_id=…, db=…)` → always raised → every space-encounter check silently used skill-ignoring **raw 3D**. Fixed all 5 to load the char + call correctly; raw-3D fallback retained but made loud. | 5× `engine/encounter_*.py`, `tests/test_encounter_skillcheck_funnel.py` |

Plus `docs/design/HANDOFF_defect_hunt_findings_2026-06-14.md` — the full
cross-session findings ledger (the 30 confirmed defects, with ownership).

## NEEDS BRIAN — design call (TODO.json `design_calls_pending_brian`)

**`ERA.tutorial_v2_gcw_profession_chains`** — the two GCW chains are now *dormant*
(unreachable) but their off-era source strings still live in `tutorial_v2.py`.
Permanent disposition is a fork: **(A) delete**, **(B) keep dormant**, or
**(C) CW-rewrite** them into era-appropriate chains. Recommendation: B now (done),
C post-launch IF the legacy `tutorial_v2` profession-chain system is being kept —
**A (delete) if that system is being deprecated in favor of the `chains.yaml`
questline engine.** Needs Brian's call on whether the legacy system stays.

## Deferred findings — see `HANDOFF_defect_hunt_findings_2026-06-14.md`

Confirmed defects this session did NOT fix (fix lands in another session's
avoid-set, or it's low ROI). Highlights:
- **PARSER-domain (Session B):** 8 achievement hooks defined-but-never-called
  (item_crafted/experiment/trade/scene/ship_launch/anomaly_salvaged/org_rank/
  dark_side_atoned). **Note: the other session already wired `on_scene_completed`
  + `on_org_rank_reached`** — re-check which remain before acting. Also: `intercept`
  achievement wrong-arg-order + undefined; sabacc rake ledger bugs (rake logged as
  faucet not sink; missing from ledger; silent routing-failure income loss).
- **MISSIONS-domain (Session A):** `chain_missions.py` `destination_slug` written
  but never read → fragile fuzzy mission-completion matching.
- **Low-ROI engine cleanups (parallel-safe, left undone):** `contest.py` phantom
  `anchor_*` writes; `hazards.py:429` dead `char['credits']` mutation;
  `espionage.py:275` unused `faction` field; `achievements.py` dead
  `notify_room_achievement`.

## NOT DONE — remaining parallel-safe lanes (for the next session)

1. **Wilderness content depth (thin Coruscant sub-regions).** The 4 sub-regions
   (`ne_smuggler`, `nw_overflow`, `se_mazefringe`, `sw_deepwarren`) are
   `landmark_includes` into `coruscant_underworld.yaml` with **zero** encounters;
   the encounter pool is **region-level**. Add band/terrain-gated entries to
   `coruscant_underworld.yaml`'s `encounter_pool` (schema: `id`/`type`/`weight`/
   `terrains`/`min_band`/`payload`). **Reuse existing creatures** (`underworld_thug`,
   `maze_predator`, gang creatures) to avoid new stat blocks — the resolution guard
   `tests/test_wilderness_encounter_template_resolution.py` will catch any dangling
   `npc_template`. Any NEW creature needs a faithful WEG D6 block in
   `data/npcs_creatures.yaml` (use the `stat-d6` skill).
2. **New questlines (`chains.yaml`).** Verified-additive seam
   (`quest_expansion_postlaunch_path_v1.md`): pure-YAML `kind: questline` over the
   11 already-emitted event types + existing reward funnels. **Caveat:** the 7
   existing questlines are all **T5 master-trainer schematic-unlock arcs** (need a
   schematic + trainer NPC + rep gate). A new one of that type is high-effort; a
   simpler self-contained faction-flavor questline (credits/rep/title rewards) is
   lower-risk. Either way the reachability guard
   `tests/test_chain_corpus_reachability_invariant.py` enforces real rooms /
   registered commands / canonical skills / `combat_won` enemy_templates tagged on
   real NPCs (Class 1–5). Faction/zone GAPS with no questline: **bhg**, **cis**,
   Coruscant, Kamino.
3. **break-it state machines.** Engine-side (fixes parallel-safe): `harvest.py`,
   `housing.py`, `espionage.py`, gambling (`dens.py`/`cantina_encounters.py`). The
   defect-hunt already swept these statically; a break-it *runtime* pass (malformed/
   out-of-order inputs) would find different bugs. Lower marginal value than #1/#2
   given the existing unfixed backlog.

## Operating reality — git / multi-session (READ THIS)

- **`c:\SW_MUSH` is a SHARED worktree on `drop/t3-20-safe-load`.** Multiple Claude
  sessions commit here sequentially (this session's defect drops interleaved with
  the other session's era-guard/enrichment drops). Single-file atomic
  `git add <my files> && git commit` is safe; **multi-step ops (merge/rebase) in
  this shared tree are NOT** — another session can `git commit` against the shared
  index mid-operation and corrupt it.
- **Integration to main is handled by a shared-branch integrator** — it merges
  `origin/main` into `drop/t3-20-safe-local` and pushes, carrying everyone's
  commits up. **You usually do NOT need to push to main yourself**; commit on the
  branch and the integrator carries it (all 4 of this session's drops reached main
  this way after a direct push of drop 1 + integrator pulls of drops 2-4).
- If you DO need an isolated merge/integration, use a **temporary linked worktree**
  (`git worktree add --detach <dir> origin/main`), merge there (separate index),
  resolve CHANGELOG/TODO by **union**, push, remove. `git checkout` in the shared
  tree is denied. Always `git fetch` first; origin/main moves every few minutes.
- **Only edit your own files**; never `git add -A` in the shared tree (you'd
  capture another session's uncommitted work — always `git add <explicit paths>`).

## Gate / test notes

- Full suite: `cd /c/SW_MUSH && python -m pytest -n auto --dist loadscope -o addopts="" --maxfail=300 --timeout=120 --timeout-method=thread -q` in the FOREGROUND or harness-background (the `--timeout` flags prevent the 99%-hang). ~6–8 min under shared-box contention.
- **Known rotating flakes (pass solo, fail under parallel load — NOT regressions):**
  `tests/smoke/test_smoke_chain_walkthrough.py::…[republic_soldier]` (and sometimes
  `[separatist_commando]`/`[smuggler]`); `tests/test_lane_e2_storms.py::test_ranged_no_storm_baseline`
  (world-events singleton leak). Re-run any red solo before treating it as real.
- **Box hygiene (left for Brian):** the crashed merge-gate left **~52 orphan
  `python.exe` processes** (the xdist zombie swarm — see memory
  `xdist-orphan-process-swarm`) and an orphaned **`C:\SW_MUSH_integ`** directory
  (git worktree already de-registered; dir delete hit permission-denied, likely an
  orphan worker lock). Safe to `rm -rf C:\SW_MUSH_integ` once the python orphans
  are reaped. Did NOT blanket-kill python (other live sessions own the box too).

## Method that worked (repeat it)
Defect-hunt **Workflow**: fan-out Explore finders per (surface, defect-class) cell
→ adversarial verifier per finding (default-refute) → re-triage survivors against
the TRUE avoid-set (the finder's `parallel_safe` flag was unreliable **both ways**)
→ fix the genuinely parallel-safe ones → targeted + full-suite gate → commit. The
recurring root cause (era + reachability) is the **partial-coverage test blind
spot**: surgical curated-list tests miss whole files. Candidate systemic follow-up:
a broad allow-listed AST era scan over `engine/*.py` player-facing strings.
