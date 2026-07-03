# HANDOFF — Decisions + Comlink + Space-Anomaly Rework + Guide Accuracy (2026-07-02)

Unattended session. Branch **`drop/decisions-comlink-hazard-anomaly-2026-07-02`** (worktree `C:/SW_MUSH_fix`), 4 commits on top of `b0485b0`. Everything below is committed, verified, and **integration-ready** — but NOT merged to main (main moved to `8a8b3ac` under the parallel session and is checked out in the primary worktree; see §Integration).

## What landed (4 commits)

| Commit | Drop | Verification |
|---|---|---|
| `c834356` | **A** — Comlink planet-scoped + 4 design calls resolved | invariant CLEAN · code-review (3 minor, all addressed) · smoke boots clean · 49 green |
| `dec09fe` | A review fixes (guarded recipient lookup + accurate feedback) | — |
| `598c53f` | **B** — Richer space-anomaly engagement + untrained-roll fix | invariant CLEAN · code-review 0 findings · smoke boots clean (223) · 31 green |
| `90dee88` | **C** — Guide accuracy pass (7 guides, grounded + test-locked) | 177 targeted green · era-clean · test-flips sound |

### Drop A — Comlink is planet-scoped
`server/channels.py::broadcast_comlink` now takes `db`/`sender_planet` and filters recipients to the sender's planet (sender always echoes; off-planet sender reaches only self; `db=None` = legacy unfiltered for harnesses). `parser/channel_commands.py` derives the planet via `engine.housing._planet_for_room`. Fixed a **latent bug in that shared helper**: 6 non-prefixed Coruscant districts + Kuat's `kdy_orbital_ring` resolved to `None` (lumped with deep space) → added `_NONPREFIXED_ZONE_PLANET` (sourced from each planet YAML's `planet:`); additive, also fixes housing's "rent from here". Guide_21 reverted to planet-wide framing; 2 guards inverted; new `tests/test_fork_comlink_planet_scoped_2026_07_02.py`.

### Drop B — Richer space-anomaly engagement (`course anomaly <id>`)
Every non-derelict type resolved with one flat roll, and — a **real bug** — cache/mynock/pirates passed a governing-ATTRIBUTE name where a skill SLUG was expected → silent untrained dice. Now per-type (all funnel-honored, fail-closed):
- **distress** = Perception ambush read (`search`, Easy 10)
- **cache** = two-step approach (`space transports`, 10) + bypass (`security`, 15), both must pass (solo rolls both; crewed pilot+engineer can split)
- **mynock** = piloting detach (`space transports`, 8); **failure damages a working ship system** (`_damage_random_system`; repair via `+ship/repair`/spacedock)
- **imperial** = slicing decode (`computer programming/repair`, Difficult 20)
- **pirates** = a `starship gunnery` skirmish (Moderate 15) whose victory **drops a salvageable wreck** (reward = the salvage, so pirates no longer pays a flat faucet)

Guide_24 §4 gained an "Engaging an anomaly" subsection + command-table row; phantom-guard flipped. New `tests/test_space_anomaly_richer_resolution_2026_07_02.py` + tightened fork test.

### Drop C — Guide accuracy pass (7 guides)
Grounded drift fixes from the audit (§Guides below), **no** hyperlink/prose/style changes: Guide_05 `flee`→`fleeship`/`breakaway`; Guide_08 Sense Deception shows `sense_lie`; Guide_18 drops deleted `listen fragment` alias; Guide_14 xref #3→#19; Guide_23 Cantina Brawl 30-60min→~5min (+ §6/Scenario 4 rescope); Guide_21 header 1.1→1.2; Guide_24 hazard "no cure" → real `drink`/`hydrate` + ~20-min decay. Two authoritative guard tests flipped in lockstep.

---

## Decisions logged (TODO.json)

**Resolved** (moved pending→resolved_recent; pending 11→7 then +1 fork = 8):
- `COMM.comlink_not_planet_scoped` → **A, planet-scoped** (built, Drop A).
- `EVENT.communal_rework_staged_scenarios` → **PRE-LAUNCH** (implementation lane = the parallel main session; its declared next-focus).
- `ENV.hazard_debuff_no_cure_path` → verified **ALREADY CURED 2026-06-23** (drink verb + 1200s decay + double-scale fix); stale-OPEN closed; guide corrected in Drop C.
- `SPACE.anomaly_engagement_mostly_unwired` → verified **ALREADY BUILT 2026-06-23** (`a49f3e0`); ratified + richer-flavor follow-up shipped in Drop B.

### ⭐ AWAITING BRIAN — new fork logged
**`SPACE.anomaly_combat_live_tick_vs_skirmish`** (pending). Brian asked to make anomaly combat "more engaging." I shipped an honest **interim** (pirates = corrected-skill skirmish + salvageable wreck; imperial-failure = narrated patrol-withdrawal) and **deferred the REAL combat** because it touches a dormant subsystem and combat *feel* is your call:
- **(A)** Register the dormant `NpcSpaceCombatManager.tick()` (~5-line adapter in `server/game_server.py`) → full interactive cockpit combat (fire/evade/flee) for anomaly pirates + a real era-clean patrol spawn on imperial-failure. Also shifts pirate rewards to kill-bounty + salvage. *Recommended (most-complete); reversible; low blast radius — nothing else calls `promote_to_combat`.*
- **(B)** Self-contained resolved multi-round skirmish (real rolls + hull stakes, no dormant-subsystem flip).
- **(C)** Hybrid.

Both need the shared `NpcSpaceTrafficManager.spawn_for_encounter(zone_id, archetype)` helper (also resolves a live `spawn_pirate_for_encounter` phantom + the zone-ignoring `_spawn`). Design pass verified all seams; era-clean patrol identity ("Sector Customs Patrol" etc.) is worked out in the design notes.

---

## Integration (I could NOT merge — coordinate)

`main` advanced `b0485b0`→`8a8b3ac` while I worked and is **checked out + actively moving** in the primary worktree under the parallel session (telemetry rollups, Guide_16 re-verifies, hollow-sun-tuning). I can't force-update a branch checked out elsewhere, and shouldn't race it.

**Overlap with the advanced main = ONLY `CHANGELOG.md` + `TODO.json`** (both union-resolvable). **No code or guide-file conflicts** — the parallel session touched Guide_16, `combat_commands.py`, e2e tests, and a `test_anomaly_defeat_clears_on_incap` test; I touched none of those. (Note: their anomaly/combat work is a *different concern* — combat-defeat cleanup — from my engagement rework; they compose.)

**To land:**
1. Merge `drop/decisions-comlink-hazard-anomaly-2026-07-02` into current main.
2. Resolve the two conflicts by **union**: CHANGELOG.md — keep both sides' entries newest-first; TODO.json — keep my 4 resolved-recent additions + the `SPACE.anomaly_combat_live_tick_vs_skirmish` pending entry + their changes. **Validate JSON after** (`python -c "import json;json.load(open('TODO.json'))"`) — do NOT auto-union-strip (corrupts object/scalar conflicts).
3. Run `run_all_tests.bat` (the full gate).

---

## Guides — audit done; edit-pass DEFERRED (parallel-safe reasons)

A read-only audit of all 25 guides ran. **Hyperlinkability confirmed**: slugs are kebab-case of the filename title (`server/web_portal.py:205-212`), zero dead existing links, and **~77 plain-text "Guide #N" refs** could become `[text](#/guide/<slug>)` links (worst: Guide_19 ~11, Guide_21 10, Guide_05/24 ~8). The full mechanical conversion + style normalization + prose polish was **deferred** — it's an all-files edit that would race the active guide loop (esp. Guide_16). Best link/structure exemplars: Guide_10, Guide_26.

**Deferred items needing Brian or coordination:**
- **CONTENT DECISION:** Guide #13 (Housing) and #15 (Wilderness) are referenced ~7×, but **the files don't exist**. Publish them, or reword the refs (e.g. to `@housing` help / inline). Guide_18's #15 refs also point at a wilderness-landmark roster that isn't in Guide_24 either (content gap).
- **Guide_16** — actively edited by the parallel session; its 4 link conversions + a "Scoundrel is not a chain" fix (L146) need coordination.
- **Hyperlink conversion** (~77 refs) + **"See also" footers** (missing on 01,02,05,06,07,08,09,18-22) + **version/byline blocks** (missing on 03,04,10,12,26) + **"ten-minutes" openers** (missing on 01,02,05,06,07,08,09,11) — safe mechanical, batchable when the guide loop is idle.
- **Prose polish** (driest: Guide_05, 01, 07, 11, 21; match the voice of Guide_03 / 25 / 18).
- Minor: Guide_19/20 headers say "Version 1.1" but bodies say "new guide"; Guide_24 header still "May 2026 / v1.1" despite the 2026-07-02 content updates (bump when convenient).

---

## Follow-ups noted (non-blocking)
- **Drop B integration test** (code-review coverage note, not a defect): no end-to-end test drives `_engage_anomaly` with a mocked `perform_skill_check`; helpers + spec + wiring are unit/trace-verified. Optional hardening.
- Known standing reds (unchanged): `test_smoke_telnet::test_t2_telnet_movement` (combat-state bleed) + `republic_soldier`/`republic_intelligence`/`separatist_commando` chain-walkthrough combat-RNG flakes — all reproduce clean in isolation.
