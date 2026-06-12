# HANDOFF — Drop A: real-bug fixes from the Windows run

**Date:** 2026-06-06
**Rollup zip:** `SW_MUSH_rollup_laneB_and_dropA_20260606.zip`
**Supersedes:** `SW_MUSH_rollup_laneb_era_cleanness_20260606.zip` — this is a **session rollup**: it contains all of Lane B **plus** Drop A. Apply this one (`Expand-Archive -DestinationPath . -Force` from project root); you don't need the earlier Lane B zip.
**Schema:** unchanged at **42**.

---

## What Drop A is

The **product-bug** half of the triage of `tests_output.log` (your 7,939-pass / 13-fail Windows run). It also closes the **Lane A Phase B Windows verification gate**. The remaining 7 failures are a queued **test-hygiene rollup** (B2 + C1 + C2 — see below), which carry no product change.

The 13 failures were on a tree that predates the Lane B zip, so none were Lane B regressions.

---

## Fixes

### A1 — SellCommand city-tax / sale regression (Vendor V1 dispatch)  ·  `parser/builtin_commands.py`
Vendor V1 (2026-06-05) routed **every** `sell <arg>` to the carried-item path. But the equipped weapon lives in `char['equipment']`, not `inventory['items']` — so `sell weapon` found no carried item, said *"not carrying"*, and **never sold**: it dropped the sale, the "Sold…" success line, **and** the `apply_city_tax` hook (the Phase-4b city-revenue invariant).

**Fix:** the **generic words** `weapon` / `equipped` route to the equipped-weapon path; **specific item names** still go carried-only, so Vendor V1's sell-by-name is untouched. Bare `sell` stays the equipped default.

> Investigation note: my first cut tried carried-first-with-fallback by moving `_sell_carried_item`'s no-match messages up into `execute()` — that broke 2 Vendor V1 tests, because they call `_sell_carried_item` **directly** and assert its "not carrying" / armor-hint output. Reverted; left that method's contract intact and gated only on the generic word. Both suites pass.

### A2 — sabacc `cantina_brawl` AttributeError (latent **live** bug)  ·  `parser/sabacc_commands.py`
The code called `get_world_event_manager().is_active("cantina_brawl")`, but `WorldEventManager` has **no** `is_active` — only the `active_event_types` property. Every sabacc play raised `AttributeError` (caught + logged), so the cantina_brawl double-bet ceiling was **silently dead** in production.

**Fix:** `"cantina_brawl" in get_world_event_manager().active_event_types` (matches `director.py`'s existing usage).

### B1 — Lane A Phase B spawner test (Python 3.14 gate)  ·  `tests/test_lane_a_phase_b_spawner.py`
The `_run` helper used `asyncio.get_event_loop().run_until_complete()`, which raises `RuntimeError: no current event loop` on Python 3.12+/3.14 — **the reason the creature-bridge tests "passed in the 3.12 sandbox" but failed your 3.14 box.**

**Fix:** `asyncio.run(coro)`. This closes the Lane A Phase B Windows verification gate (the live spawn path now runs under the harness on 3.14).

---

## Verification (sandbox, Python 3.12)

| Suite | Result |
|---|---|
| `test_cities_phase4b` (the 3 SellCmd/sabacc failures) | **3/3 pass** |
| `test_vendor_sell_carried` (Vendor V1, regression check) | **20/20 pass** |
| `test_lane_a_phase_b_spawner` | **18/18 pass** |
| `test_drop_a_realbug_fixes` (new guard, +4) | **4/4 pass** |
| hygiene + encoding | pass |

All touched `.py` AST-clean.

New guard `tests/test_drop_a_realbug_fixes.py`: A2 behavioral (`active_event_types` membership clean, `is_active` absent) + source guard (sabacc no longer calls `.is_active`); A1 dispatch-contract pin (generic-word guard present); B1 source guard (`asyncio.run`, not `get_event_loop`).

---

## Files (21 in the rollup)

Lane B's 14 code/test files + 3 trackers/doc, **plus** Drop A's: `parser/builtin_commands.py` (A1 — also carried Lane B's lockpick string), `parser/sabacc_commands.py` (A2), `tests/test_lane_a_phase_b_spawner.py` (B1), `tests/test_drop_a_realbug_fixes.py` (new). `CHANGELOG.md` / `TODO.json` carry both drops; `sw_d6_mush_architecture_v51.md` carries the Lane B point-update.

---

## Also queued this session

- **`TODO.json` T3.19** — pre-launch tunables-externalization + telemetry instrumentation (lift every difficulty / economy / progression / Force / Director knob into config files + add structured telemetry so post-launch tuning can be grounded in real player data). Near-launch refactor + ongoing post-launch loop.

---

## Windows gate (Brian)

Re-run the full pytest suite to confirm **13 → 6** (Drop A clears A1+A2+B1 = 7 of the 13: 3 phase4b + 3 spawner + the sabacc-pathed one is among the 3 phase4b). Remaining = the **test-hygiene rollup**, not yet shipped:
- **B2** — SPA node-subprocess/tempfile encoding under cp1252 (`test_clickwalk_slugjoin` ×4 + `test_client_html_inline_script_parses` ×1): the harness hands non-ASCII JS to node without forcing UTF-8. Fix = `encoding="utf-8"`. Test-infra only; the JS files are fine.
- **C1** — `test_m3_tokens::test_canonical_labels_present`: the expected literal is corrupted (a replacement char where the multiplication sign should be). Product value is correct. Fix = restore the char + ensure file UTF-8.
- **C2** — `test_f7c1_village_trials` NPC-count canary 196 → 198 (2 NPCs added since the pin). Trivial re-pin.

Say the word and I'll ship the hygiene rollup (B2 + C1 + C2).
