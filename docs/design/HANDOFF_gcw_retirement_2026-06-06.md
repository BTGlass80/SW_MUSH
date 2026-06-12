# HANDOFF — GCW Retirement (T2.CW.gcw_retirement)

**Date:** 2026-06-06
**Drop zip:** `SW_MUSH_gcw_retirement_drop_20260606.zip`
**Work item closed:** `T2.CW.gcw_retirement` (+ `T2.CW.spec_config_cleanup`, folded in)
**Scope decision:** **NARROW** (Brian: "A")
**Architecture doc:** NOT touched — stale, held for the v52 reconciliation per the standing CHANGELOG note. CHANGELOG.md + TODO.json are the authoritative record for this drop.

---

## 1. What this drop did

Retired the deprecated Galactic-Civil-War content so the Clone Wars is the production era end-to-end. Unblocks the empire→CW chargen pivot and advances B3 era-cleanliness. Deleted the GCW data tree + the named config tables, repurposed the byte-equivalence tests, and **left** the dead, test-pinned, now-unreachable GCW faction config in the other ~13 modules.

---

## 2. The scope fork (read this before any follow-up B3 work)

A HEAD-wide AST scan during this drop found **151 GCW production-strings across 14 modules** — ~10× the `if_retire_scope` target. Reading the actual B3 tests resolved what they are:

- **Sanctioned (do NOT touch):** `engine/village_trials.py` dark-future-self prophecy (`test_e3` docstring says so); the **director-axis model codes** `imperial`/`rebel` (zone-tone keys, NOT org codes) in director.py / territory.py `ORG_TO_AXIS` / vendor_droids / director_commands / npc_commands / space_commands.
- **Dead GCW faction config, reachable only via `--era gcw`:** the bulk. `test_laneb_era_cleanness` states this config "is owned by the separate `T2.CW.gcw_retirement` work item" and that the B3 regime is "deliberately surgical, not a blanket scan." These entries are **pinned byte-identical by the `b1c`/`b1d`/`b1e`/`b1f` era-aware tests** and become **unreachable** once the gcw tree is deleted.

**Why narrow was correct:** a full 14-module B3-strip would break the `b1c`/`b1d`/`b1e`/`b1f` byte-equivalence pins and is a large, invasive cross-module change. The principled clean-vs-leave rule used: **clean only the modules whose pinning test is in `if_retire_scope`'s repurpose list** — organizations (`b1b1`/`b1b2`), housing (`b1d1`/`b1d2`), espionage (`b1f`). Everything else stays as unreachable test-pinned dead code.

**`contest.py` was edited then REVERTED** to honor this rule (its pinning test `test_syn3b` is NOT in the repurpose list).

---

## 3. Three judgment calls (all recorded in TODO `design_calls_resolved_recent`)

1. **Kept the org-axis legacy rewicker** (`apply_org_rewicker` / `get_org_rewicker_map`) as a permanent migration safety net (state-preservation directive). Map lives in `clone_wars/organizations.yaml::legacy_rewicker` (empire→republic, rebel→cis, hutt→hutt_cartel, bh_guild→bounty_hunters_guild, independent→independent). `era="gcw"` now returns `{}` via graceful fallthrough, preserving `test_b5` no-op behavior.
2. **Flipped `build_mos_eisley.build()` DEFAULT era `gcw`→`clone_wars`** — a real production fix the engine/parser/server sweep missed (it's a root-level file), surfaced by `test_build_pass_a`.
3. **Narrow scope** on the 151-hit surface (see §2).

---

## 4. Files in the zip (26)

### Production (13)
- `engine/organizations.py` — removed empire/rebel/hutt/bh_guild from STIPEND_TABLE / RANK_0_EQUIPMENT / RANK_1_EQUIPMENT / CROSS_FACTION_PENALTIES; deleted 10 GCW-only EQUIPMENT_CATALOG items + re-skinned 3 CW-reused descs (officers_sidearm / encrypted_comlink / blaster_pistol) + fixed dc15_blaster_rifle "E-11" leak; deleted `IMPERIAL_SPEC_EQUIPMENT` + empire entries in `SPEC_EQUIPMENT_BY_FACTION` / `_SPEC_CONFIG_BY_FACTION` + `prompt_imperial_specialization` / `complete_imperial_specialization` shims; dropped `era=="gcw"` branches from `seed_organizations` + `get_org_rewicker_map`. **Rewicker kept.**
- `engine/housing.py` — removed all 7 GCW clusters: `_LEGACY_FACTION_QUARTER_TIERS` GCW block, `FACTION_QUARTER_LOTS` / `FACTION_HOME_PLANET` empire/rebel/hutt, kessel/corellia tier descs + `_planet_view`, `_TIER5_ROOM_DESCS` GCW block; `INSURGENT_FACTIONS` → `{"cis"}`; resolver loop → `("clone_wars",)`.
- `engine/espionage.py` — removed empire/rebel/hutt from `_FACTION_FINDINGS` (**B3-dirty; was missing from the original surface inventory — caught by a comprehensive B3 re-scan**).
- `data/weapons.yaml` — deleted `stormtrooper_armor`; de-Imperialized `force_pike` note.
- `era="gcw"`→`clone_wars` fallback flips: `engine/world_lore.py`, `engine/chargen_templates_loader.py` (**deleted `_LEGACY_TEMPLATES_GCW` per planned F.7.b — fallback now returns `{}`**; removed unused `import copy`), `engine/npc_space_traffic.py` (+2 Kessel/Corellia desc re-skins), `engine/starships.py`, `engine/director_config_loader.py` (docstring), `engine/ship_loader.py` (docstring), `parser/tutorial_commands.py` (rewrote `training skip` CW-only; trimmed 4 now-unused imports), `main.py` (--era help/comment), `build_mos_eisley.py` (**default era flipped**).

### Tests (12)
- **New guard:** `tests/test_gcw_retirement_guard.py` (16 tests).
- **Repurposed wholesale → CW-contract:** `test_b1b1`(20), `test_b1b2`(17), `test_b1d1`(12), `test_b1d2`(5).
- **Repurposed surgically:** `test_b1f`(23) (dropped GCW byte-equiv class; empire-spec + empire-claim methods repurposed), `test_f6a7_phase1_seeding_era`(19), `test_f6a3_int_byte_equivalence`(7) (dropped GCW system-prompt byte-equiv class), `test_cw_ships`(19), `test_q1_2_extended_sweep`(16), `test_b2_thread_b4_era_aware_seeding`(12), `test_f6_hermit`(22) (dropped `TestGcwHasNoHermit`).

### Docs (2)
`CHANGELOG.md`, `TODO.json`.

### NOT in the zip
`engine/contest.py` (reverted to byte-identical original).

---

## 5. Deletions (zip can't delete — run manually, from project root, PowerShell)

```
Remove-Item -Recurse -Force data\worlds\gcw
Remove-Item -Force data\organizations.yaml
Remove-Item -Force tests\test_f1a_npc_loader.py
Remove-Item -Force tests\test_f1b_ship_loader.py
Remove-Item -Force tests\test_f1c_test_character_loader.py
Remove-Item -Force tests\test_f5b3a_gcw_housing_host_rooms.py
Remove-Item -Force tests\test_build_pass_a.py
```

**Deleted tests, why:** `test_f1a/f1b/f1c` = pure-gcw NPC/ship/test-character loader parity (gcw world gone). `test_f5b3a` = gcw housing host rooms. `test_build_pass_a` = gcw-**world** build-cutover; asserts gcw room names + coords + counts, and **Corellia/Coronet City is not among CW's six launch worlds**, so it can't be cleanly repurposed. The writer-based build it verified is now exercised by the live CW build. *(A CW build-pass test could be authored later — out of scope; would need CW-world ground truth.)*

---

## 6. Tests that pass-or-skip UNCHANGED (no edit needed)

The F-series migration tests were written defensively with `skipTest("…gcw…not present")` guards, so they **skip** rather than fail after the tree is gone:
`test_b5_org_rewicker`(20, rewicker kept), `test_f5a1`, `test_f5a2`, `test_f6a2`, `test_f6a3`, `test_f6a4`, `test_f6a6`, `test_f6a7_phase2`, `test_e3`, `test_f8`, `test_t2def`.

Re-verified green to confirm the leave-as-dead-code decision: **`test_syn3b`(53)** (confirms the contest.py revert), **`test_b1c`(26)** / **`test_b1e`(17)** (confirms leaving territory/missions dead config is correct).

---

## 7. Validation done in sandbox

- All touched `.py` compile; **pyflakes-clean on changed lines** (the pyflakes warnings that remain are all pre-existing — unused imports / f-strings / undefined names on lines this drop did not touch, unrelated to gcw).
- **All touched modules B3-clean** (AST string-literal scan).
- **clone_wars dry-run:** era resolves clone_wars; chargen templates load with **no `rebel_pilot`** (clone_trooper / republic_officer / etc. present); housing resolves CW factions only; rewicker map intact; chargen empty-fallback returns `{}`.
- Full affected test-set green (deps `aiosqlite`/`pytest`/`bcrypt` installed in sandbox for the run; present on Brian's box).

---

## 8. PENDING — Brian's Windows box (ground truth)

1. **Full ~7,700 pytest suite** (`run_all_tests.bat`).
2. **clone_wars boot smoke:**
   - chargen template list has **no `rebel_pilot`**.
   - a **SECURED city / customs** reads era-clean (no "Imperial").
   - `@spawn` of a retired GCW org_code is **graceful** (no crash, no faction finding).

---

## 9. Deliberately LEFT (future optional full-B3-strip)

Unreachable, test-pinned dead GCW faction config remains in ~13 modules: `territory.py`, `director.py`, `tutorial_v2.py`, `bounty_board.py`, `vendor_droids.py`, `npc_generator.py`, `npc_combat_ai.py`, `security.py`, `space_anomalies.py`, `contest.py`. Plus `build_mos_eisley.py`'s dead `if era == "gcw"` branches.

A future full-B3-strip would remove these **and** retire the `b1c` / `b1e` (+ the dead `b1b`/`b1d` GCW pins) test families. The **sanctioned** director-axis model codes and the `village_trials` dark-future prophecy stay regardless.

---

## 10. Pre-flight reminders for the next session

- This was executed under the standing **phantom-delivery** discipline: symbol-level HEAD grep before claiming delivered. The espionage `_FACTION_FINDINGS` miss in the original surface inventory is exactly why a **comprehensive B3 re-scan** is run, not trust in handoff docs.
- The B3 cleanness regime is **surgical, not a blanket file scan** — don't "fix" the 151 hits by grep-and-replace; most are sanctioned or test-pinned dead config.
- `force_sensitive` is derived state; the rewicker is the standing legacy-migration seam (any future grudge/nemesis or migration work extends it, doesn't duplicate).
