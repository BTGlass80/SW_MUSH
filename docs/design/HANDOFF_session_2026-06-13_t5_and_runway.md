# HANDOFF — Session 2026-06-13 (t5-trainer arc + runway)

**Branch:** `drop/t5-questline-engine` (built on `roadmap`, which carries
the overnight drops 25–32). **NOT merged to main or roadmap** — your
`run_all_tests.bat` gate.
**Author:** Claude Opus 4.8 (1M), attended session with Brian.

---

## TL;DR

Shipped the **T5 master-trainer questline arc end-to-end** (3 drops: the
engine + all 5 questlines + gates), wrote the **ambient-NPC-life
post-launch design** you asked for, logged the **parallel tooling
session's** CHANGELOG/TODO, and started the **world-event flag-consumer**
runway (2 of 5 done). Every drop verified (targeted unit + reachability
invariant + content walkthrough + 227-test smoke + the read-only verify
fan-out). All on the feature branch; nothing merged.

---

## Commits this session (on `drop/t5-questline-engine`, oldest→newest)

| Commit | Drop | What |
| --- | --- | --- |
| `e811ab5` | 33 | T5-questline arc A — multi-slot chain engine + `mastery` verb |
| `ec79109` | 34 | T5-questline arc B slice 1 — "The Hermit's Trial" (Jedi/lightsaber) + the schematic gate + per-step reward consumer + rep tuning |
| `c6931ff` | 35 | T5-questline arc B slices 2–5 — the other 4 master trainers + tooling-session CHANGELOG/TODO log |
| *(uncommitted at write time)* | 36 | World-event flag consumers 2 of 5 (rare_vendor + krayt_bounty) — committing on the green smoke |

---

## What landed, by area

### T5 master-trainer questlines (the roadmap item `T2.DEF.t5_trainer_storyline` — DONE)

Design: `docs/design/t5_trainer_questlines_design_v1.md`. Your four
resolved forks: gated questline EACH, RICH (combat+travel+NPC web),
faction rep ≥ 50 + Contested/Wilds placement, generalize-the-chain-engine
architecture.

- **Engine (Drop 33):** the single-slot chargen-only chain engine now
  supports a 2nd mid-game **questline slot** (`active_questline`) — every
  state helper took a `state_key` param (onboarding behavior byte-neutral,
  298 legacy chain tests green), a `kind: questline` chain field (chargen
  picker skips them), a slot-aware dispatcher (`_try_advance_all_slots`),
  slot-aware teleport/pending-flag (review caught + fixed a slot-corruption
  blocker here), and the **`mastery [start|status|abandon]`** command +
  an NPC-offer-on-talk hook. Verb is `mastery` because quest/quests/+quests/
  train/training/trial were all already taken.
- **Content (Drops 34–35):** 5 rich 5-step questlines (meet → flavor
  command → skill check → themed combat → certify), each unlocking ONE t5
  schematic, each in a Contested/Wilds zone with an original CW-era trainer
  + a themed enemy:
  - Jedi Master **Vehn Tasaal** (Jundland) → lightsaber
  - Trandoshan **Vossk the Armorer** (Nar Shaddaa pits) → blaster rifle
  - Lt. **Corso Venn** (Geonosis) → hyperdrive surge converter
  - Chief **Dax Orrin** (Geonosis) → ion engine core
  - Zabrak **Sabra the Smith** (Nar Shaddaa Warrens) → master-grade armor
- **The gate:** `trainer_curriculum` is async + gate-aware; a t5 schematic
  carrying `gated_by_questline`/`gated_faction`/`gated_min_rep` is hidden
  until the player GRADUATED the questline AND holds rep ≥ 50 — enforced in
  both the `talk`/teach flow AND `learn` (review BLOCKER), and gated recipes
  always cost tuition (review MAJOR).
- **Verification:** a DATA-DRIVEN content walkthrough test walks EVERY
  questline start→graduation through the production dispatcher; an
  all-5-t5-gated invariant; the static reachability invariant (every slug/
  command/skill resolves) extended to the questline kind.

### Two decisions you made mid-session (both implemented + pinned)

1. **Per-step chain rewards → ship for all chains.** `apply_step_rewards`
   was items-only; per-step `credits`/`faction_rep` were authored across
   ALL chains but silently dropped. Now delivered (metered
   `chain_step_reward` faucet + `adjust_rep` funnel).
2. **Faction rep → "tune lower."** After ratcheting twice on your
   feedback: every onboarding chain now leaves a player at **recognized
   (~8–13**, ≈10% of max); the t5 questline at **18**. NO chain reaches
   honored (50) — the t5 rep-50 gate is earned through post-questline play.
   Pinned by `TestChainRepEconomyCeiling` (hard ceiling 22).

### Ambient NPC life (your post-launch feature request)

`docs/design/ambient_npc_life_design_v1.md` + TODO **T3.22**. Idle-Ollama
background world sim: NPCs with goals that move + interact with each other,
Python-first / Ollama-last-and-preemptible, **no unprompted PC interaction
v1**. Verified the codebase is ready (idle_queue.py already has the
priority/backoff/preemption model; tick scheduler; space-traffic movement
pattern to mirror). **DB scaffolding lands pre-launch** (empty CREATE TABLE
+ JSON `extra` future-proof columns — your "blanks" instinct, done the
SQLite-idiomatic way) so the post-launch build never migrates a live DB.

### Parallel tooling session (logged per your request)

`CHANGELOG` + TODO (`TOOL.tooling_additions` done, `TOOL.settings_apply`
pending you). That session shipped 2 agents (break-it-tester, handoff-
writer), 4 slash commands (/verify-drop, /break-it, /log-design-call,
/handoff), and the upload-zip slimming. The deferred `.claude/settings.json`
allow/deny changes are captured with exact lines + the `python main.py`
caveat — apply after the parallel session commits its settings.json edits.

### World-event flag consumers (runway item 1 — 2 of 5)

Drop 36: `rare_vendor` (MERCHANT_ARRIVAL → buy-command pre-haggle 15%
discount) + `krayt_bounty` (KRAYT_SIGHTING → bounty tier-bump toward
SUPERIOR). Thin consumers over existing seams, mirroring contraband_scan;
each a pure modulator + manager-driven flag-path test. **Remaining 3**
(brawl_active, distress_active, hutt_auction) each want their own small
drop (combat-spawn / mission-injection / rep-gated-purchase seams).

---

## State of the suite

- Every drop's targeted tests green. The full chain/questline/crafting/
  rewards/achievements regression (~430 tests) green. The **227-test smoke
  suite green** after drops 33–35 (drop 36's smoke run is the gate on its
  commit). Reachability invariant green for all 5 questlines.
- **I did NOT run `run_all_tests.bat`** (the full ~7,700 Windows suite) —
  that's your merge gate. I expect green; the authoritative run is yours.

## Suggested next session

1. Run `run_all_tests.bat`. If green, merge `drop/t5-questline-engine`
   (drops 33–36) — and separately decide on merging `roadmap` (25–32).
2. Apply `TOOL.settings_apply` (the deferred settings.json allow/deny)
   after the parallel session's settings.json edits land.
3. Continue the runway (all greenlit by you, in order): the **3 remaining
   world-event flags** → **commissary sellback** → **breaching charges** →
   **Director CW faction mapping**.
4. Pre-launch: schedule the ambient-life **Phase 0** DB scaffolding (T3.22)
   — the only pre-launch piece of that feature.

## Untracked strays (NOT mine — parallel sessions)

`data/guides/*` + `Guide_27` + `tools/guide_lint.py` + `docs/dev/` (the
guides-rework session); `sw_d6_mush_architecture_v52.md` +
`HANDOFF_readiness_sequencing_review_2026-06-13.md` (the readiness session);
`.claude/settings.json`/`.gitignore`/`make_upload_zip.ps1`/`.claude/agents`/
`.claude/commands`/`package*.json`/`node_modules` (the tooling session).
I left all of these untouched and out of my commits.
