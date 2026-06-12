# HANDOFF — E3: red-board remediation (full-suite test health)

**Date:** 2026-06-04
**Drop:** E3 (standalone test-health drop; post-Drop 3 / post-E2)
**Trigger:** Windows ground-truth full run = **23 failed / 7701 passed / 428 skipped** (656s).
**Result:** **18 of 23 fixed and verified green** in the Linux sandbox (changed-module runs).
4 are environmental (Windows-node), 1 (f7c1) is a tripwire left RED for your call.
One *additional* seedless flake surfaced during verification (not in the 23) — flagged, untouched.

> **Production behaviour is unchanged** except two silent-except→`log.debug` lint fixes and the
> removal of one already-orphaned module. Everything else is test code or tooling. This greens the
> board so **Drop 4a builds on a clean baseline**.

---

## What you need to do

1. **Delete the orphaned module by hand:** `del parser\admin_fp_commands.py`
   *(A zip overlay can't delete files. If you skip this, `test_wow3c::test_admin_fp_module_removed` stays RED — the zip simply doesn't ship that file.)*
2. `pip install -r requirements.txt`  ← pulls in **pytest-timeout** (now required by the new `run_all_tests.bat`).
3. Run `run_all_tests.bat`. It now writes `tests_output.log` even on Ctrl+C and kills any hanging test (see "Tooling" below).
4. Confirm the **18** fixes are green on your box (ground truth).
5. **Three things need a decision from you** — see "Open for Brian" at the bottom.

---

## The 23, classified

### FIXED + verified green in sandbox (18)

**Stale assertions** (code moved to its intended Drop-2 / Audit-v2 balance; the test just hadn't caught up — these are *not* masking):
- `test_skill_checks_unit::test_partial_success_pays_fraction` — Audit v2 §2.1: partial window tightened to `margin ≥ -2`, fraction `0.40`. Dice `[3,3,2]→[3,4,2]`, expected `375→200`. *(Already noted as a known stale test in the E2 CHANGELOG entry.)*
- `tests/smoke/scenarios/pc_bounty_session2.py` (BTY-6) — Drop 2 rescaled death insurance to **flat + %** (`engine/death.py`: `INSURANCE_FLAT=250`, `INSURANCE_PCT=10`). A 10 000-cr bounty now costs the target **1 250** (250 + 1 000), not 1 000. Assertion + comment updated; the 8 000-cr BH-payout assertion left intact.
- `test_market_state_persistence` (`== "SCHEMA_VERSION = 38"` → robust parse + `>= 38`).
- `test_wow1_substrate` (`SCHEMA_VERSION == 35` → `>= 35`). *(Schema is at v40.)*
- `test_session58_cleanup_umbrellas` — Drop 3 added `prestige`; `_HOME_SWITCH_IMPL` now `{view, sethome, admin, prestige}`.

**Test-harness / fake-DB gaps** (Drop 1 ledger migration moved real call sites to the metered `adjust_credits`, but these fakes never grew the method):
- `adjust_credits` shim added to `test_syn5_espionage_as_influence`, `test_syn7a_wilderness_anomalies`, `test_syn7b_wilderness_anomalies_tier2` (sqlite-backed `_MiniDB`; `char_id==0 → 0`) and `test_cities_phase6_maintenance` `_FakeDB` (dict-backed; `city_tax` routes through `adjust_credits(0, -take, "city_tax")`).
- `test_syn7a` also never seeded its char row → added `INSERT INTO characters` so the migrated `UPDATE characters` path has a row.
- `tests/harness.py` — smoke harness inited housing/territory/world-lore but **not** `player_cities` → `no such table: player_cities`. Added `engine.player_cities.ensure_schema(srv.db)`. **This was breaking BTY-6's setup.**

**Real test-ordering bug** (not stale):
- `test_poi_feed` had **two** raw `engine.bounty_board.get_bounty_board = …` monkeypatches with no restore. The fake lambda leaked, so `test_singleton_bindings[bounty_board]` failed whenever poi_feed ran first. Converted both to the auto-restoring `monkeypatch` fixture. **Note:** a first pass that wrapped only the *second* site in try/finally was insufficient — it captured the lambda the *first* site had already leaked; the fix had to touch the upstream site. Verified: `poi_feed` + `singleton_bindings[bounty_board]` together = 38 passed.

**Production lint** (the only production-code touch):
- `engine/titles.py` and `parser/bounty_commands.py` — `except Exception: … pass` → `log.debug(..., exc_info=True)` (flagged by `test_session38::test_no_silent_except_pass_in_production`).

**Module deletion:**
- `parser/admin_fp_commands.py` removed (tree-wide orphan from the WoW.4 `@fp`→`@weight fp` consolidation; only refs were the file + the test asserting its removal).

**Optional-dependency guard:**
- `test_wilderness_substrate_seed`, `test_wilderness_overview_faithful` — errored `ModuleNotFoundError: PIL` on your box (no Pillow). Added `pytest.importorskip("PIL", …)` inside `_load_tool`, gated to the substrate tool: **skips** without Pillow, **runs** with it (sandbox: 28 passed). *Install Pillow (`pip install pillow`) if you want those map-render tests to actually execute instead of skip.*

**Fragile-window test:**
- `test_bearing_wireup::test_move_command_records_bearing` — sliced `src[start:start+3000]`; the move hook grew past 3 000 chars so the slice missed the present, correct wiring. Replaced with a slice bounded by the next `def`/`async def`; the single `save_character(..., attributes=…)` keeps the `count == 1` assertion exact.

### Environmental — REPORTED, no code change (4)
- `tests/spa/test_clickwalk_slugjoin.py` ×4 — **pass in the Linux sandbox** (node v22.22.2: 6 passed, 1 skipped) and already skip when node is absent. Your Windows box has node but produces a different result. **Need `proc.stderr` from your box** (the test shells out to node) — likely a node-version or Windows subprocess/newline/temp-file quirk.

### Tripwire — FLAGGED, left RED (1)
- `test_f7c1_village_trials::test_total_npc_count_includes_all_seven_village` — asserts `COUNT(*) FROM npcs == 177`; actual is **196** (+19 from recent drops: Senator Iolanthe Kress, Independent Trader Sela Dorne, Kabe, …). This is a *conscious-review canary* — **not** auto-bumped. **Your call** (see below).

---

## Surfaced during verification (NOT in the 23)

- `test_session38::TestTextureEncounterTick::test_security_scaling` — **seedless statistical** test (5 000 iters, real `random`, conftest doesn't seed). Passed in your full run; coin-flipped in the isolated sandbox run (lawless=24 vs secured=32). Both ≈0.5% suggests the secured/lawless multiplier isn't separating in an isolated run (the zone→security lookup likely needs world/registry data the full suite has loaded). **Zero causal link to E3 — left untouched.** Recommend hardening later (mock `random` like the sibling `test_trigger_during_hyperspace` does, or seed + assert on probability *after* confirming the two zone rates differ in isolation). Logged in `TODO.json` `tech_debt`.

---

## Tooling fix (`run_all_tests.bat`)

Your symptom: bat hangs, Ctrl+C needed, no log written. Causes + fixes:
- Old script piped through PowerShell `Tee-Object`, which buffered output and **lost the log on Ctrl+C** → rewrote to plain `> tests_output.log 2>&1` (survives Ctrl+C).
- A hanging test stalled the run forever → added `--timeout=120 --timeout-method=thread` (kills any single test after 120 s so the run finishes and the log writes). Requires **pytest-timeout**, now added to `requirements.txt`.
- Also `--continue-on-collection-errors --maxfail=999 -o addopts= -q` so one broken import can't abort the whole run.

---

## Verification (sandbox, changed-module only — never the full suite here)

- Group A (market, wow1, session58, skill_checks, bearing, wow3c): **210 passed**
- Group B (syn5, syn7a, syn7b, cities_phase6): **216 passed**
- session38 silent-except invariant: **31 passed** (the *other* session38 failure is the unrelated flake above)
- poi_feed + singleton_bindings[bounty_board]: **38 passed** (leak fix proven)
- wilderness substrate + overview: **28 passed** (skip-safe without PIL)
- BTY smoke session2: **3 passed**
- clickwalk: **6 passed / 1 skipped**
- All 16 touched `.py` files: **AST-clean**. No JS touched.

---

## Files in this drop

Production: `engine/titles.py`, `parser/bounty_commands.py`, *(deleted)* `parser/admin_fp_commands.py`
Tests: `tests/test_syn5_espionage_as_influence.py`, `tests/test_syn7a_wilderness_anomalies.py`, `tests/test_syn7b_wilderness_anomalies_tier2.py`, `tests/test_cities_phase6_maintenance.py`, `tests/test_market_state_persistence.py`, `tests/test_wow1_substrate.py`, `tests/test_session58_cleanup_umbrellas.py`, `tests/test_wilderness_substrate_seed.py`, `tests/test_wilderness_overview_faithful.py`, `tests/test_poi_feed.py`, `tests/test_skill_checks_unit.py`, `tests/test_bearing_wireup.py`, `tests/harness.py`, `tests/smoke/scenarios/pc_bounty_session2.py`
Tooling: `requirements.txt`, `run_all_tests.bat`
Bookkeeping: `CHANGELOG.md`, `TODO.json`

---

## Open for Brian (decisions)

1. **f7c1 NPC count (177 → 196):** confirm the 19 added NPCs are intended (no dupes / no Q1 named-figure violations), then say the word and I'll either bump the constant **or** refactor the test to assert the seven village NPCs by name (more robust). Left RED on purpose.
2. **clickwalk ×4:** paste the **node `proc.stderr`** from your Windows run so I can diagnose the env mismatch. (Passes here, so it's not the test logic.)
3. **TextureEncounterTick flake:** want me to harden it (mock/seed)? It's seedless and can flip on you.

---

## Next session — Drop 4a (gated)

`TODO.json` now carries the **Part V / Drop 4 locked decisions** (`design_calls_resolved_recent`, 2026-06-04) and a forward item **T1.3 — Drop 4a** (`tier_1_active`, status `ready_pending_e3_green`).

**Do not start Drop 4a until you've confirmed this E3 board is green on the Windows full run.** Drop 4a = mechanical teeth on the currently narrative-only social/sense Force powers + the mind-trick split + the offered-effect consent path; force_sensitive stays a derived state; all rolls via `perform_skill_check`.
