# HANDOFF — Overnight drive 2026-07-02 → 07-03

Massive unattended/attended-hybrid session: Events milestone completed, **~5 launch blockers fixed**, two big features started, and Fable's two review rounds fully triaged. Authority order still holds — **CHANGELOG.md + TODO.json are ground truth**; this doc + `memory/overnight-qa-backlog-2026-07-02.md` are the narrative index. Everything below was HEAD-verified when written; re-grep before acting.

## Landed to `main` (verify: `git log --oneline`; HEAD was `7c9ea16` at write time, moving)

**Events milestone — COMPLETE.** All 5 Cult uprisings are now playable staged scenarios (Drowned Choir `e98253b`, Iron Veil `728d782`), 0 on the old menace-counter. Earlier blockers: anomaly-defeat-clear (INCAP not DEAD) `91b777f`, hollow-sun tuning (~6h clock + capstone) `b00bc4c`.

**Launch blockers fixed (found by live break-it QA — unit tests structurally missed them):**
- **Staged-cult reward paid ZERO** (`c2cd2fa`) — the whole rep/title/1000cr-capstone/relic system was dead on the real path (points only recorded by the redirected-away legacy strike). Fixed: `on_scenario_progress` credits `anom.resolved_by`; `_grant_capstone_item` uses `coerce_inventory` (was destroying bare-list inventories). **Root lesson (Fable §2): the tests hand-injected `contribs` — audit the signal PRODUCER on every path, not the distributor.**
- **Space-combat ghost combatant** (`9d69cbf`) — `fire`-killing an anomaly pirate paid the bounty but never ended the fight (dead code `apply_damage_to_npc`); the pirate fired forever + was un-targetable. Fixed via `destroy_combatant` + `already_rewarded` flag; also pilot-gate / atomic-anomaly-claim / mid-transit-refuse.
- **Housing data-loss** — `housing-teardown-completeness` (`a8c3e8f`: evict/foreclosure lot-leak + sell_shopfront wrong-property) + `housing-concurrency-locks` (`6cf0bf7`: per-char + per-lot locks vs double-refund/oversell). Closes the whole housing bug cluster.
- **Chain-walkthrough "flakes" retired** (`52f7a3d`) — republic_soldier/separatist_commando/smuggler were NOT RNG; they were a cold-Ollama **test poll-timeout** (`_drive_talk_to_npc` polled 6s < the 8-12s cold model load). Fixed to `NPC_DIALOGUE_TIMEOUT_S + 8`. (Fable §3 notes a cold-load can still exceed 20s → the Qwen drop adds a smoke pre-warm.)

**Feature: the 36th arc "The Phantom Tonnage"** (`16dd09b`) — Kuat bulk-liner venue + capital-ship-flavored questline; resolves `QUEST.t3_24_36th_arc`. Big-ship combat = person-scale aboard the liner (no ship-vs-ship seam existed — see the capital-ship feature below).

**Hardening/hygiene:** vendor-droid concurrency `eea3fdd`, parser-dispatch hardening `62f1482`, wilderness zone-integrity (`dune_sea.zone`) `7975cd2`, Iron Veil reward-claim accuracy `59cdd92`, F6 hygiene batch (+ the real mapgen-seed root cause) `14057b3`, F4+F2 quick-decisions `7c9ea16`. Plus OpusLoop's steady quality drops (wave-reengage, faction-payroll, experiment-fumble, ollama-model-env, …) and the parallel session's Fable-round-1 incorporation (F1 P0 chain-credit, F2/F3/F5, space FORK-1=A live combat, Guides 13/15, comlink).

## In-flight at handoff (5 lanes — autonomous, push themselves on green)
1. **Staged-questline archetype — first slice** (`staged-questline-archetype-slice1`). Brian's PRIMARY next feature. Design = a new `site_cleared` chain step-kind (arm a multi-phase scenario anomaly at a room, clear to advance); reuses the whole loop, cult runtime untouched. Brian's calls: **lightweight reuse** + **richer capstone** (suppress anomaly payout; new ~900cr "staged" reward tier + relic; sanctioned exemption from flat reward-tier parity). Spec: `docs/design/DESIGN_staged_questline_archetype_2026-07-03.md` (9 forks + rec stack 1A·2A·3A·4B·5A·6B·7A·8B·9A). Critical: its walkthrough test resolves through the REAL clear seam (the anti-cult-bug lesson).
2. **Capital-ship combat — bridge foundation** (`capital-ship-combat-bridge`). KEY FINDING: ship-vs-ship fight already works on main; only the space-kill→chain-step credit was missing. This ships the `space_combat_won` completion type + `TrafficShip.chain_enemy_ship_template` + a hook in `handle_traffic_ship_destroyed`, proven by a solo DESTROY light-capital skirmish. Spec: `docs/design/DESIGN_capital_ship_combat_2026-07-03.md`.
3. **Qwen-default hardening** (Fable 🔴, `qwen-default-hardening`) — the default flipped to `qwen3.5:9b` but only §1 of the swap spec landed. Lands §§2-5: idle_queue JSON-parse robustness (silent bark-pool starvation), provider `num_ctx`/keep_alive/sampling, bark temps→tunables, smoke pre-warm.
4. **Fable-addendum hygiene** (Fable 🟡, `fable-addendum-hygiene`) — the F6 batch's own `deepscan` alias test fails on Linux (os.walk order); deterministic sorted walk + alias-dedup + jsdom serial-mark + Phantom-Tonnage skill-uniqueness note.
5. **Chargen hardening** (3 S1 blockers, `chargen-hardening`) — illegal templates (Clone Trooper sums 53≠54 pips + skills over), **force_sensitive settable at web chargen** (hard-invariant violation — remove the web Force step + reject the field), account-orphan on name-collision (make creation transactional), + `set control/sense/alter` budget pollution.

## ⚠ MERGE WATCH — archetype ↔ capital-ship overlap (READ before either lands)
The **archetype** build (worktree `agent-aa6b277f...`) and the **capital-ship bridge** build (editing `c:/SW_MUSH` directly, worktree empty) BOTH modify the completion-type seam: `engine/tutorial_chains.py` (`ALLOWED_COMPLETION_TYPES`), `engine/chain_events.py`, `data/worlds/clone_wars/tutorials/chains.yaml`, `data/achievements.yaml`, `tools/verify_tutorial_chains.py`, and the phantom-tonnage/T5 tests. Archetype adds `site_cleared`; capital-ship adds `space_combat_won`. **These are ADDITIVE and must BOTH survive** — whoever lands second gets a merge conflict; resolve KEEP-BOTH (both strings in the frozenset, both arcs in chains.yaml, both hooks in chain_events.py, both completion types in the two `verify_*` linter copies + the test enumerations). Do NOT let an auto-resolve drop one. (Capital-ship editing the live tree directly is an anomaly — its work is the uncommitted WIP in `c:/SW_MUSH`; don't disturb it while `a75b221` runs.)

### Landing updates (since the doc was first written)
LANDED after handoff: **Qwen 🔴** `6be07ad` (mostly verify-HEAD — §§2-5 were already in `0ea500b`; added the cold-Ollama smoke pre-warm), **F4+F2** `7c9ea16`, **chargen-hardening** `2f2ffb3` (3 S1 blockers). NOTE: the chargen drop pushed on targeted+smoke green only (it declined to run the full suite per its role reading) — a full gate hasn't covered `2f2ffb3` in isolation; the next lane's full gate will. Chargen follow-up: `tests/e2e/breakit_chargen.py` (Playwright) hardcodes the OLD step layout → update before the next browser QA pass. STILL LANDING: archetype first slice, capital-ship bridge, addendum-hygiene.

## ⭐ Pending Brian's decisions (nothing else blocks)
- **Capital-ship disable/board + crewed tiers** (his choice) layer ON the shipped bridge. DEFERRED — need his specifics: the ion-cripple/disable threshold; what boarding a crippled capital triggers/awards (the boarding-party integration); the crewed set-piece reward. The `gunner`/`vacate` station model exists, so the crewed tier is feasible.
- (F4 = silenced, F2 = blaster-swapped, both DONE.)

## Deferred / queued (logged in TODO + memory)
- **Signal-producer audit** (Fable §2 — the highest-value pre-launch QA pass): break-it the reward pipelines whose distributors gate on upstream accumulation — territory contest scoring, bounty split/claim, org payroll, communal title-share, chain `slot_totals`, grind daily-cap. Treat break-it as the PRIMARY gate for reward pipelines.
- `COMMUNAL.staged_concurrency_gaps` (record_strike anomaly-orphan + maybe_post multi-post — MEDIUM, guarded today).
- Bohrus Kang flavor-text: now carries a blaster but narrated as axe-wielding — tiny content polish.
- Qwen §6/§7 (era-drop telemetry + acceptance cycle) + the §2 one-curl check (needs Brian's Ollama box).
- Archetype fast-follows: Fork 8A (templates→YAML = fully-data), Fork 6A (unify cults onto the archetype), Fork 9C (end-game hard-remix).
- Wilderness per-tile coordinate grid (bigger roadmap; landmark-to-landmark works, free-roam is thin).

## Process notes / gotchas (worth keeping)
- **Break-it QA earned its keep** — it found the 3 headline blockers static review (and Fable) missed. Run it as the primary gate for reward/state pipelines, not the confirmation step.
- **Drop-implementers detach the full gate** as a background task then end their turn → the drop stalls uncommitted. Resume them with "block on your existing gate task synchronously, don't relaunch, commit+push in-turn" (worked for reward-fix + space-combat).
- **xdist zombie swarms** under heavy multi-agent load (saw 26–57 frozen `python.exe`). Reap frozen procs (CPU=0, old StartTime) with `Stop-Process -Force`; the box thrashes otherwise. See [[xdist-orphan-process-swarm]].
- Accepted baseline red is now **only** `test_cities_phase4b::test_dock_sell_in_city_credits_city` (the mapgen-seed red + the chain-walkthrough flakes were fixed tonight; the jsdom trio is being serial-marked by the addendum drop).
- Multi-actor git: re-fetch+merge before every push; CHANGELOG conflicts = keep-both; TODO conflicts = `git restore --theirs` + reapply (NOT `git checkout --theirs`, permission-denied).
