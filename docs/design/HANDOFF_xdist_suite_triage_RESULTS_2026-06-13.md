# HANDOFF — xdist full-suite triage RESULTS (2026-06-13)

**Follows:** `HANDOFF_xdist_suite_triage_2026-06-13.md` (the charter).
**Session job:** run the full pytest suite under pytest-xdist, triage each
failure **real-bug vs bad-test**, fix what's in lane, escalate what isn't.

---

## TL;DR

Full suite run under `-n auto` (12 workers, ~8,800 items). **4 distinct
failures**, all triaged and resolved within lane except one cross-session
residual (flagged to Brian, who chose "flag, don't touch"):

| # | Test | Verdict | Fix |
|---|------|---------|-----|
| F1 | `test_drop_f8c2a_chain_anchors::test_every_chain_npc_is_authored` | **STALE TEST** | broaden coverage to all era-wired NPC rosters |
| F2 | `spa/test_map_label_lod::test_zoom_reveals_more_rooms` | **TEST BUG** | snapshot far-zoom labels before the idempotency re-run clobbers them |
| F3 | `spa/test_m3_substrate_hybrid::...skips_procedural` | **STALE PIN** | count 9→10 (predated the `L_SubstrateRooms` layer); + added real coverage for it |
| F4 | `test_session38::test_no_silent_except_pass_in_production` | **1 REAL + 2 not-in-lane** | fixed the real production site (commissary ×3); flagged the 2 untracked guide-tool strays |

**No engine logic was wrong.** Three of four were tests that drifted from
correct, intended engine behavior. The single real defect (F4 commissary)
was a bare `except: pass` swallowing a best-effort web push with no logging
— now `log.debug(..., exc_info=True)` per the codebase idiom.

---

## Process note (why the first runs looked stuck)

On pickup the box had **two competing `-n auto` masters + ~20 hung 0%-CPU
execnet worker zombies** from prior reaped background runs — the exact
contention trap the charter warned about (the live run was crawling
~18 bytes/8s). Swept them (`taskkill //T //F` the masters; the two
dev-session harness one-liners from the night before were also hung at 0%
and got swept — they were read-only PRAGMA/SELECT probes, no durable
state lost). Then launched **exactly one** clean run. Recorded the pattern
in memory (`xdist-orphan-process-swarm`).

**Also discovered:** `pytest.ini addopts` carries `-x`, so the first run
**stopped at 3 failures** and hid F4. Re-ran with `-o addopts="" --maxfail=200`
to get the complete set. *Any* triage run must strip `-x` or it under-reports.

**Why these spa/map tests surfaced now:** they were **dormant (skipped, no
jsdom)** until drop 26 (today) made `_resolve_node_modules` prefer the
repo-local `node_modules` (installed by the VSCode extension's npm). With
jsdom now resolvable, F2 and F3 run for the first time — they were never
regressions, just never-executed.

---

## Per-failure detail

### F1 — chain-npc-coverage (STALE TEST)
`test_every_chain_npc_is_authored` checked chain NPC refs against a **single**
roster file (`npcs_drop_f8c2a_chain_anchors.yaml`). The T5-questline arc
(drops 34–35, this branch) legitimately added 5 master-trainer NPCs
(Master Vehn Tasaal, Vossk the Armorer, Lieutenant Corso Venn, Chief Dax
Orrin, Sabra the Smith) in a **second** roster (`npcs_drop_b_t5_trainers.yaml`)
— authored, era-wired (`era.yaml::content_refs.npcs`), and consumed by the
runtime talk_to_npc lookup, which is roster-agnostic. Producer + manifest +
consumer all present → **not a phantom**, just a stale single-file assumption.
**Fix:** new `_all_authored_npc_names()` helper unions NPC names across every
roster in `era.yaml::content_refs.npcs`; `test_every_chain_npc_is_authored`
now checks against that union. `test_no_extra_npcs` stayed file-scoped (it's a
correct per-file identity check). 26/26 in the file green.

### F2 — map zoom LOD (TEST BUG)
The production `_labelRoomsForNavigation` is correct (verified by running the
brace-matched function directly under node+jsdom: far-zoom → all 6 rooms ✓).
The test read `far: labelled(s3)` **after** re-running the label fn on the same
`s3` at zoom:1 (the idempotency check), which collapsed the set back to the
fit-3. So `far` captured the post-collapse state and the assert for all-6
failed. **Fix:** snapshot `farLabels = labelled(s3)` immediately after the
zoom-2.5 call, before the idempotency re-run. Author's intent preserved
(`reidempotent` still reads `s3` post-collapse). 3/3 green.

### F3 — substrate child count (STALE PIN)
Substrate mode emits 10 children, test pinned 9. The 10th is
`L_SubstrateRooms` — the intended tier≤1 tactical click-target layer that
replaces the skipped procedural `L_Buildings` so click-to-walk works under a
painting (`data-room-id` cells). Engine + the stale `9` landed in the **same**
squash commit (`catchup_01`) but were never run together (no jsdom → always
skipped), so the inconsistency hid until today. **Fix:** count 9→10 with full
attribution; added positive assertions for the `substrate-rooms` layer and its
2 non-street click targets (the layer had **zero** prior coverage). 8/8 green.

### F4 — silent except/pass (1 REAL, 2 not-in-lane)
Whole-tree scanner. Flagged:
- **`parser/commissary_commands.py:197`** — REAL. Bare `except: pass` on a
  best-effort `shop_state` web push after a confirmed sale. Also found two
  **comment-masked siblings** the scanner missed (`:117`, `:146` — `pass  # …`
  defeats its `stripped == "pass"` check). **Fixed all three** to
  `log.debug("[commissary] <list|buy|sell> shop_state push failed", exc_info=True)`,
  matching the bounty/inventory/crafting best-effort idiom.
- **`tools/guide_lint.py:39`, `tools/split_guide_dev_track.py:35`** — UNTRACKED
  files from the parallel **guides-rework** session; benign
  `sys.std*.reconfigure(encoding="utf-8")` console-bootstrap idiom. **Not this
  session's lane.** Brian's call: **flag, don't touch.** Logged as
  `OBS.silent_except_invariant_reconfigure_carveout` in
  `design_calls_pending_brian` (recommendation: the guides session gives both a
  real `log.debug`, keeping the invariant carve-out-free).

---

## Residual state (honest)

- **My lane is clean.** All 37 tests across the 4 affected files green
  single-threaded except the 2 untracked guide-tool strays in F4.
- **The full suite still carries exactly 2 reds** — both
  `test_no_silent_except_pass_in_production` hits on the guides session's
  uncommitted `tools/*.py`. They are not mine to edit/commit and will clear
  when that session resolves `OBS.silent_except_invariant_reconfigure_carveout`.
- **The canonical gate** (`run_all_tests.bat`, single-threaded) will show the
  same 2 reds for the same reason until then.

## Files touched (this session — scoped, uncommitted)

- `tests/test_drop_f8c2a_chain_anchors.py` (F1)
- `tests/spa/test_map_label_lod.py` (F2)
- `tests/spa/test_m3_substrate_hybrid.py` (F3)
- `parser/commissary_commands.py` (F4 — the one real production fix)
- `TODO.json` (appended `OBS.silent_except_invariant_reconfigure_carveout`)
- `CHANGELOG.md` (this session's entry)
- `docs/design/HANDOFF_xdist_suite_triage_RESULTS_2026-06-13.md` (this doc)

**Not committed** — TODO/CHANGELOG are shared, high-churn, and dirty from
concurrent sessions; Brian commits.
