# HANDOFF — Lane E2 + E3 rollup (recovery + consolidation)

**Date:** 2026-06-07
**Architecture-of-record:** `sw_d6_mush_architecture_v51.md` — **STALE, do not trust the §4.x invariant block.** CHANGELOG.md + TODO.json are the authoritative record until the v52 reconciliation (see "Carry-forward" below).
**Builds on:** the 2026-06-06 Lane E small-wins trio + the Director-dispatch bugfix.
**Apply:** `Expand-Archive -Path .\SW_MUSH_lane_e2_e3_rollup_20260607.zip -DestinationPath . -Force` from the project root. Root-mirrored. Additive only — **no deletions, no Remove-Item**.
**Deliverable:** `SW_MUSH_lane_e2_e3_rollup_20260607.zip`

---

## TL;DR

This session was a **recovery + consolidation**, not a new feature drop. A `rm -rf head`
in the sandbox cleared the working copy; it was immediately rebuilt from your uploaded
zip, which already contained the full recent chain — so **nothing was lost**. I verified
that against the disk (symbol-level greps of each drop's marquee feature, not just
CHANGELOG claims), ran the four new suites green (**39/39**), and re-packaged the entire
Lane E2→E3 chain as a single idempotent rollup so the tree can be brought current in one
`Expand-Archive`.

**Lane E is now COMPLETE** (E1 + E2a + E2b + E3). The two latent bugs flagged during E2a
are **resolved** in HEAD.

---

## A. What's in the rollup (all verified present in code + green in sandbox)

Four 2026-06-06 drops, consolidated:

1. **Lane E2a — graded sand-weather.** `world_events.py` gains `GRAVEL_STORM` +
   `SANDWHIRL` as graded siblings above the live `SANDSTORM` (×1/×2/×3 the −1D base on
   the only two effects with a live consumer: `perception_penalty`, `ranged_penalty`).
   SANDSTORM re-tuned to add `ranged_penalty` (SoT: sandstorms cripple ranged fire).
   New `ranged_penalty` consumer in `combat._resolve_ranged_attack` (ranged-only;
   surfaces as `+ Storm N` in the difficulty). Storms fire via the working timer path.
2. **Lane E2b — Tatooine clock + heat + `+weather`** (completes Lane E2).
   `world_time.resolve_period_label` + `PLANET_PERIOD_LABELS["tatooine"]` (First Dawn /
   Second Dawn / High Noon / First Twilight / Second Twilight) nested inside the existing
   day/dusk/night cycle — **no renderer change**. New `+weather`/`+time` command (both
   platforms) is the consumer. `hazards.extreme_heat` graded by time-of-day (noon harder,
   night eased). `build_mos_eisley.py --era` default fixed gcw→clone_wars.
3. **Director world-event dispatch fix.** Repaired both broken `activate_event` call
   sites in `director.py` (was awaiting a 6-arg async form that doesn't exist → guaranteed
   TypeError; ALL Director-fired narrative events were dead). Added `effect_text` field to
   `EventDef` so the web-client structured `effects` payload sends. This makes the
   sandwhirl's Director-narrated beat — and every LLM-driven narrative event — actually
   fire.
4. **Lane E3 — d66 cantina table.** `engine/cantina_encounters.py` (NEW): the 36-entry
   Wretched Hive §2C table, era-translated + reworded, rolled as a **true WEG d66**
   (tens/ones, not summed). BUILDER-gated `+cantina` GM tool in `scene_commands.py` poses
   the beat to the room. The atmospheric subset enriches the live legacy `cantina` ambient
   pool; disruptive plot-hooks stay out of the passive pool (GM-fired only).

**Files (17):** `engine/world_events.py`, `engine/combat.py`, `engine/director.py`,
`engine/world_time.py`, `engine/hazards.py`, `engine/cantina_encounters.py` (NEW),
`parser/builtin_commands.py`, `parser/scene_commands.py`,
`data/worlds/clone_wars/zones.yaml`, `data/ambient_events.yaml`, `build_mos_eisley.py`,
4 new test files, `CHANGELOG.md`, `TODO.json`.

---

## B. Verification status

- **Sandbox (this session):** the four new suites run green —
  `test_lane_e2_storms` **16**, `test_lane_e2b_clock` **11**,
  `test_director_event_dispatch` **5**, `test_lane_e3_cantina` **7** = **39/39**.
  All touched `.py` AST-clean; both touched YAML files parse.
- **Anti-phantom:** each drop's marquee symbol grep-confirmed in code
  (GRAVEL_STORM/SANDWHIRL, `get_effect("ranged_penalty"`, `resolve_period_label`,
  `PLANET_PERIOD_LABELS`, `effect_text`, `roll_cantina_encounter`, `+cantina`).
- **PENDING — your Windows box (ground truth):** full ~7,700-test suite
  (`run_all_tests.bat`). The Director Faction Turn is integration-tested there too (the
  sandbox can't run the AI-provider/DB harness).

### Smoke (live)
- **Storms:** admin-activate `sandstorm` → fire a blaster at LONG range → see `+ Storm 3`
  while a search/perception check drops 1D. `gravel_storm` → `+ Storm 6` / −2D.
  `sandwhirl` → `+ Storm 9` / −3D (short-lived).
- **Clock:** `+weather` in a Mos Eisley room shows `Time: High Noon` + any active storm's
  effect; off Tatooine shows the generic band; desert heat-check harder at the day peak,
  eased after dark.
- **Director:** with the Director enabled, a narrative event activates, announces, and
  shows in `+events`; web client receives the `effects` string.
- **Cantina:** `+cantina` (BUILDER) rolls the table and poses the beat; `+cantina <code>`
  poses a specific entry.
- **Build:** `python build_mos_eisley.py` (no `--era`) builds clone_wars.

---

## C. What's next

**Sourcebook enrichment roadmap — Lane E is done. Remaining lanes:**

- **Lane D (Geonosis/Kamino faction-tension wiring).** The recorded recommendation
  (TODO `tier_2_queued[42].claude_recommendation`) is **EXTEND don't add**: ride the
  existing `engine/contest.py` SYN.3 faction-intent/contest machinery and the
  security-zone + wilderness models rather than building parallel infrastructure. This is
  also where Lane E1's `violence_index` finally gets consumed — driving territory-contest
  aggression math and the Director's turf-dispute narration. `violence_descriptor` /
  `get_org_violence_index` are the primitives waiting for that wiring.
- **Lane C (Gundark's gear/crafting expansion).** Gate resolved as **SPLIT by
  faucet/sink** (`design_calls_resolved_recent[43]`): purchasable/vendor gear families may
  ship now, wave-by-wave, as credit sinks; **craftable/lootable families stay gated behind
  Drop-5 farming controls** (faucet). Honor the hard ordering rule — no faucet without a
  matching sink.
- **Lane F — remaining.**

**Then the pre-launch hardening cluster (near T3.19):** externalize tunables + structured
JSON-line telemetry (re-review/expand the telemetry catalog at implementation time — the
economy bucket is too thin as drafted); state-preservation/safe-migration robustness
(T3.20 — also folds in the F.7.n `force_sensitive` reload-round-trip verify-or-close);
optimization + security pass (T3.21).

**Other queued:** Drop-5 farming controls (unblocks the gated half of Lane C); the web-UI
expansion package for Claude Design (mechanical surfaces → structured web, RP stays text);
difficulty tiers / zoned progression; the F.8.c tutorial-graduation work.

---

## D. Open tech-debt (carried, NOT regressions)

- **TD.WORLD_EVENT_ZONE_MODEL** (tech_debt[18]) — `get_effect()` is **global**: any active
  storm applies its penalty everywhere, including indoors. Same coarseness as the
  pre-existing perception penalty. A larger zone-scoping fix; out of scope for the storms
  work.
- **TD.AMBIENT_ERA_ADDITIONS_DEAD** (tech_debt[0]) —
  `data/worlds/clone_wars/ambient_events.yaml` has an `era_additions:` section **no loader
  reads** (`world_loader.load_ambient_pools` reads only `ambient_events:`), so the authored
  CW cantina/spaceport flavor there is dead. E3 deliberately routed its enrichment through
  the live legacy `cantina` pool instead. Touches the loader; flagged, not fixed.
- **Lane E3 venue front/true-owner split — DEFERRED** (anti-phantom). HEAD has no
  investigation/territory consumer for a hidden venue owner, so the `front_owner`/
  `true_owner` flag-pair would be schema-ahead-of-consumer. The §2A 7-field card and §2B
  10-step framework are captured in `wretched_hive_extraction_v1.md` for a future venue
  generator; the flag-pair ships with the mechanic that reads it (future Lane F / territory
  drop).

**Resolved this chain (for the record):** TD.DIRECTOR_ACTIVATE_EVENT_SIGNATURE_MISMATCH
(tech_debt[16]) and TD.WORLD_EVENT_EFFECT_TEXT_MISSING (tech_debt[17]) — both fixed by the
Director-dispatch drop in this rollup.

---

## E. Carry-forward for the next session

- **Architecture doc is stale.** `sw_d6_mush_architecture_v51.md` lost the Jun-5 invariants
  in a lossy round-trip and is **no longer shipped in drop zips**. It needs a dedicated
  **v52 reconciliation**: rebuild the §4.x invariant block from CHANGELOG truth and
  renumber the cult invariant to §4.33 (the creature special-attack invariant folds in as
  §4.34). Until then, **CHANGELOG.md + TODO.json are authoritative.**
- **Phantom-delivery is still the chronic failure mode.** This session is the case in
  point — always grep HEAD at the symbol level before trusting any "delivered"/"absent"
  claim, including claims in handoffs and this document. The uploaded zip is ground truth;
  the sandbox tree does not persist between sessions.
- **Disciplines unchanged:** extend don't add; never declare a mechanical effect field
  without a live consumer; faucets and sinks land together; atomic root-mirrored zips;
  CHANGELOG + TODO updated every drop; sandbox runs targeted unittest/pytest only, the
  Windows ~7,700 suite is the gate.
