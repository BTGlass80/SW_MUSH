# HANDOFF — Close-out + parallel-dev roadmap (2026-06-24 PM)

Pick-up doc for a **fresh, high-throughput session** (Brian upgraded Max x5 → x20 and
wants to run as many *safe* parallel lanes as possible). Authority order unchanged
(TODO.json + CHANGELOG.md first; this doc is forward-looking strategy).

Supersedes the forward-plan half of `HANDOFF_e2e_campaigns_and_ux_upgrade_2026-06-24.md`
(that doc's E2E-campaign history still stands; its "next" section is updated here).

---

## TL;DR — state at handoff

- **Economy BLOCKER fixed + on main.** The last normal-play E2E blocker (CW graduates
  stranded in a vendorless 3-room pocket) is fixed: `build_mos_eisley.py` seed-room
  linking now runs for `clone_wars` (was dead-gated on the retired `gcw` era).
  Commit `3f46c85`; regression `tests/test_seed_pocket_economy_reachable.py`.
- **origin/main merged in** (`9bb445e`) — the 19 overnight loop commits (content +
  T3.19 telemetry). Only CHANGELOG/TODO union-conflicts; zero code conflicts.
- **Loops:** the **Sonnet content loop (`SWMUSH-DurableLoop`) is PAUSED** — its
  "saturate every room with a huntable mob" mandate is wrong (see §2). The **Opus
  quality loop (`SWMUSH-OpusLoop`) is RUNNING** and should be redirected (see §3).
- **Gate gotcha discovered + fixed:** the threaded full suite HANGS under xdist
  because `tests/e2e/test_e2e_new_player.py` launches real Chromium on a worker.
  The gate command must `--ignore=tests/e2e` (the browser test is its own lane).
  See §6.
- **Two design corrections were DECIDED by Brian this session** (mob-grind
  realignment + balance-telemetry breadth) — both are new parallel lanes below.

---

## 1. What shipped this session (on the branch, ff'd to main once gate is green)

- `3f46c85` — economy seed-pocket linking fix + regression test.
- `9bb445e` — merge of origin/main (content + telemetry loop drops).
- This handoff doc.

> **GATE/PUSH STATUS:** _(fill in at close-out)_ threaded full suite (e2e-excluded)
> result = `<RESULT>`; `git branch -f main HEAD && git push origin main` = `<DONE?>`.

---

## 2. DECIDED — Mob-grind realignment (grinding belongs in the wilderness)

**Brian's call (2026-06-24):** grindable mobs respawning in Chalmun's Cantina, the
spaceport, the police station, and government offices is immersion-breaking.
Grinding belongs in the **wilderness** (and lawless/contested zones), not the
civilized core. Two read-only audits grounded this:

### The problem (audit `engine/hunting_rewards.py` `is_huntable_mob` + `engine/security.py`)
- **281 grind-mobs across ~50 `npcs_drop_mob_grind_*.yaml` files.** 162 are misplaced:
  - **131 sit in SECURED zones where the engine FORBIDS combat** (`security.py`
    `_check_security_gate` → *"Heavy security patrols this area."*). They are
    **literally unkillable — dead content** (Senate lobby, Tipoca City, Kuat
    embassy/spaceport, Dexter's Diner, the amphitheater).
  - **31 are in contested civic hubs** (police station, Kayson's Weapon Shop, the
    clinic, Chalmun's) — attackable, but there is **NO respawn for static placed
    mobs** (kill once → gone until a full world rebuild), so not a grind loop.
  - **119 are fine** (lawless/contested-dangerous: Geonosis battlefield, Nar Shaddaa
    warrens, Coruscant underworld). **These stay.**

### The wilderness already IS the grind venue (audit `engine/wilderness_*`)
The encounter→spawn→combat→loot loop is **fully built and working**:
`wilderness_encounters.roll_encounter()` (4–5%/move, 60s cooldown, threat-banded) →
`wilderness_encounter_runtime.spawn_encounter_creatures()` → starts ground combat →
`on_wild_creature_killed()` field-dresses into spoils. Self-refreshing by design (the
move-roll *is* the respawn). Backed by a **22-creature WEG-statted library**
(`data/npcs_creatures.yaml`) referenced from region encounter pools. It needs
**content breadth, not engine work**. The security model already enforces "no grinding
in the cantina."

### LANE: grind realignment (data-heavy, parallelizable, disjoint from client.html)
1. **Strip the 162 inappropriate placements.** Per the audit: **~24 wholly-inappropriate
   files** are deletable outright (all 8 Kuat + all 5 Kamino + 6 Coruscant
   [`civic_government`, `commercial_expansion`, `gilded_cage`, `midlevels`,
   `monumental`, `senate_district`] + 5 Tatooine [`cantina_market`, `commerce_services`,
   `mos_eisley`, `mos_eisley_expansion`, `spaceport`]) and **6 mixed files** need
   surgical per-NPC removal (`coruscant`, `coruscant_lower`, `final_coverage`,
   `hutt_territory`, `nar_shaddaa_criminal_hubs`, `tatooine_authority_zones`). Keep the
   ~17 wholly-defensible files. **Re-verify the classification against HEAD before
   deleting** (the audit is a snapshot; grep each file's rooms→zone→security fresh).
   Remember to un-register deleted files from `era.yaml content_refs.npcs`.
2. **Redirect the content energy to the wilderness:** more regions + richer encounter
   pools + more creatures in `npcs_creatures.yaml` (content-author agents, one per
   region). This is the *real* grind content.
3. **Optional engine knob:** add a respawn/timer for any KEPT static contested-zone
   mobs (none exists today) — itself a tunable worth instrumenting (§3).
4. **Quick-win option:** the 131 SECURED-zone mobs are dead content regardless of the
   tone debate — safe to remove first/fast.

> **Gotcha:** un-pause `SWMUSH-DurableLoop` ONLY after rewriting its mandate to
> "wilderness/lawless grind content + ambient-only in secured civic rooms." Its current
> mandate will re-pollute the cities.

---

## 3. DECIDED — Balance telemetry breadth (beyond economy)

**Brian wants tuning telemetry broader than credit-economy:** combat difficulty,
rewards, CP, mob density, respawn/encounter rate, events — "anything knobs make sense
for." T3.19 deliberately did **economy-only (10 faucet/sink seams)** because
credit-integrity was the launch-critical worry. The emitter pattern (one fail-open,
sample-tunable event at a resolution seam, buffer-only + offline-flush, surfaced on
`@economy`) **generalizes unchanged.** Stand up a **`@balance` view** beside `@economy`.

| Domain | Emit at | Payload | Knob it tunes | Status |
|---|---|---|---|---|
| **Combat difficulty** | `engine/combat.py` round/resolve seam | TTK (rounds), win/loss, wound outcome, dmg in/out, dodge/parry/fumble, fled | NPC stat baselines, difficulty, cover values | gap |
| **Rewards / grind** | `engine/hunting_rewards.on_huntable_kill` + wilderness spoils | what/where killed, difficulty, daily-cap hits, payout | 15cr/kill, 400/day soft cap, spoils tables | partial (credit leg tagged; outcome not joined) |
| **CP / advancement** | CP-award + skill-raise seam | CP earned/spent, skills raised, time-to-raise, source | CP award rates, skill-raise costs | gap |
| **Mob density / "respawn"** | `wilderness_encounters.roll_encounter` | fire rate, type mix, threat band, cooldown hits, region | `base_chance_per_move`, `ENCOUNTER_COOLDOWN_SECONDS`, pool weights | gap |
| **Events** | `engine/communal_objective_runtime` + director news | participation, completion vs expiry, menace trajectory | spawn cadence, menace thresholds, reward bands | gap |

**Recommended order (highest-leverage first):** combat difficulty → grind/rewards → CP
→ events. "Respawn timer" for the *wilderness* grind = the encounter spawn-rate/cooldown
knob (no fixed timer exists); a *static*-mob respawn is a new mechanism if we keep any.

### LANE: balance telemetry (Opus loop's natural redirect; engine seams, NOT client.html)
Touches `engine/combat.py`, `engine/hunting_rewards.py`, `engine/wilderness_encounters.py`,
the CP/advancement seam, `engine/communal_objective_runtime.py`, and `data/tunables.yaml`
— **all disjoint from the UX client bottleneck.** Same per-drop pattern as T3.19.

---

## 4. The UX upgrade (8 drops) — unchanged spec, with the conflict map

Spec docs: `docs/design/ux_engagement_roadmap_2026-06-23.md` +
`dice_animation_and_ux_polish_2026-06-22.md`. Build order: (1) clickable affordances
[+ the `get_combat` dead-hook fix in `server/session.py` `_hud_room_contents`] →
(2) combat HUD → (3) dice animation → (4) situation board → (5) scene/presence UI →
(6) goals tracker → (7) command palette → (8) polish batch.

**Bottleneck reality (audited):** `static/client.html` is touched by **7 of 8** drops;
`server/session.py` (the HUD producer queue) by **5 of 8**. These two files cannot be
edited by parallel worktrees without thrashing. `engine/combat.py` is touched by drops
2+3 (different sections, low risk). Each drop also adds a NEW `static/spa/m3_*.js`
module (no conflict) + tests (no conflict).

**Correction to the prior handoff:** the "don't touch `server/session.py` — parallel
session owns it" constraint **dissolves** now that the old QA session is closing. The
UX lane owns `session.py`, so the **LOW guide-protect fix** (`_classify_npc_role` —
protect quest-givers/guides) **folds into UX Drop 1** instead of being deferred.

---

## 5. THE PARALLEL PLAN (the point of this handoff)

Max *safe* throughput = **non-overlapping file surfaces in separate git worktrees**, plus
**intra-drop parallelism** inside the one unavoidable bottleneck lane.

### Concurrent worktree lanes (disjoint surfaces — run all at once)
| Lane | Owns (hot files) | Work | Conflict notes |
|---|---|---|---|
| **UX** (Opus main worktree → main) | `static/client.html`, `server/session.py` | The 8 UX drops, in dependency order; guide-protect folded into Drop 1 | THE bottleneck. Accelerate from *inside* (per-drop workflow below), not by forking it. |
| **GRIND** (worktree) | `data/worlds/clone_wars/npcs_drop_mob_grind_*.yaml`, `npcs_creatures.yaml`, wilderness region YAML | §2: strip civic mobs + author wilderness content | Disjoint from client.html. **Serializes on `era.yaml`** (one coordinator appends/removes refs). |
| **TELEMETRY** (worktree, or the redirected Opus loop) | `engine/combat.py`, `engine/hunting_rewards.py`, `engine/wilderness_encounters.py`, CP seam, `data/tunables.yaml` | §3: `@balance` telemetry breadth | Disjoint from client.html/session.py. Mild overlap with GRIND on wilderness files — coordinate or sequence. |
| **EVENTS** (worktree) | `engine/communal_*`, `parser/communal_commands.py`, event data | rally/communal "playable scenarios" rework | **Must land before UX Drop 4** (Situation Board consumes `communal_objective_runtime.get_active`). Disjoint from client.html. |
| **QA/HARDEN** (read-only) | none (reports only) | continue break-it + playthrough campaigns on un-swept surfaces → findings docs | Zero merge conflict. Run `tools/_fun_wf.js` AFTER UX lands. |

### Intra-drop parallelism (inside the UX lane — how each drop goes fast)
Per UX drop, run a Workflow: **parallel** {engine producer + new `m3_*.js` module +
jsdom/engine tests} → **serial** thin wiring seam (`client.html` dispatcher line +
`session.py` producer-queue entry) → **verify fan-out** (invariant-auditor +
code-reviewer + smoke + test-runner). Only the wiring seam is serialized; the bulk
parallelizes.

### Bottleneck rules (the "safely")
- **One lane owns `client.html`; one lane owns `session.py`** (both = UX lane). No other
  worktree edits them.
- **`era.yaml` is serialized** — GRIND lane's coordinator is the only writer.
- **`CHANGELOG.md` / `TODO.json`** are union-merge per drop (the in-place resolver
  pattern from this session works: keep both sides' entries; for TODO scalars pick
  current-from-branch / prev-from-mainline; **always `python -c "import json; json.load(...)"`
  after**).
- **Per-worktree git** (memory `[[parallel-session-worktrees]]`): each lane in its own
  worktree off main; ff-main races resolved by re-merge + `git branch -f main HEAD`.

---

## 6. Gotchas / operational

- **THREADED GATE COMMAND (must exclude e2e):**
  ```
  python -m pytest tests/ --ignore=tests/e2e -n auto --dist loadscope \
    -p no:cacheprovider --continue-on-collection-errors --maxfail=300 \
    --timeout=120 --timeout-method=thread -o addopts= -q
  ```
  Without `--ignore=tests/e2e`, `tests/e2e/test_e2e_new_player.py` launches Chromium on
  an xdist worker and the whole run hangs (0% CPU, no progress, timeout doesn't fire).
  Run the e2e/Playwright lane separately (`NODE_OPTIONS=--use-system-ca python
  tests/e2e/<file>.py`). If a run hangs: `TaskStop` it, then it's clean (verified — no
  orphan swarm this time, but check `[[xdist-orphan-process-swarm]]`).
- **`SWMUSH-DurableLoop` (content loop) = DISABLED.** Re-enable only after rewriting its
  mandate (§2). **`SWMUSH-OpusLoop` (quality) = RUNNING** — redirect to balance
  telemetry (§3). Earlier today both were paused 07:17→11:00 per Brian, re-armed by the
  now-self-deleted `SWMUSH-ResumeLoops-1100` task.
- **Dirty/untracked in the tree (not mine, leave or clean):** `tools/mapgen/term_boundaries.json`
  (Nano loop's working-tree write; committed HEAD is `{}`), `_probe_seed_link.py`
  (my throwaway BFS probe — deletion was permission-denied; safe to `rm`),
  `_probe_bacta*.py` / `_verify_bacta.py` (older throwaways), the `tests/e2e/_play_*`
  + `breakit_*`/`play_*` campaign artifacts (curate useful ones into committed tests).
- **`static/client.html` editing:** CRLF + literal escape chars — if `Edit` fails, use a
  Python `open(newline='')` string-replace script.
- **Known baseline-reds (NOT regressions):** 3 chain-walkthrough smokes
  (`republic_soldier`/`separatist_commando` — RNG flakes, pass solo), `test_cities_phase4b`
  cargo-tax (watch-item #7), the `term_boundaries` seed.

---

## 7. Suggested next-session kickoff (max parallel)

1. Confirm main is green + pushed (this session does it).
2. Spin up worktrees for **GRIND**, **TELEMETRY**, **EVENTS** lanes (disjoint) — they can
   all start immediately and in parallel.
3. **UX lane** starts Drop 1 (affordances + `get_combat` fix + guide-protect) in the main
   worktree, using the per-drop workflow (§5).
4. **QA/HARDEN** runs read-only campaigns continuously, feeding findings back.
5. Reconvene at each lane's drop boundary; ff-main in sequence (CHANGELOG/TODO union).
