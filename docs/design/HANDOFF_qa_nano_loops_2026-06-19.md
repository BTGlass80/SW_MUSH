# HANDOFF — QA fixes + Nano interiors + loops (2026-06-19)

Resume cold in a fresh chat. Three parallel workstreams + Brian's decisions below.
Everything is grounded in HEAD / the committed branch — re-verify any symbol at
HEAD before trusting it (hard invariant: no phantom claims).

Branch: **`drop/sidebar-contract-handoff-capture`** (pushed to origin as backup).
It now = **origin/main fully merged in** + 6 commits of Nano tooling + the QA report.
HEAD = `f5fb36a` (the merge commit). Clean **fast-forward candidate for main**.

---

## ★ STEP 1 (DO FIRST) — gate + merge to main
Brian decided: gate + merge before doing more. The branch already has origin/main
merged in (CHANGELOG/TODO conflicts were resolved as additive unions; the loops'
help/guide work + my Nano/QA work coexist; JSON validated).
1. **Brian runs `run_all_tests.bat`** (the full ~7,700-test gate, his box).
2. On green: `git branch -f main drop/sidebar-contract-handoff-capture && git push origin main`
   (fast-forward — no checkout needed; per the sole-dev model). 
3. If reds: they're almost certainly the known rotating baseline (verify tools/ paths)
   or a flake (republic_soldier walkthrough) — see memory `threaded-test-methodology`.
   The merge only added docs + tools/mapgen + the loops' help/guides; no overlap with
   engine code, so a real new red is unlikely.

**Why first:** the Opus loop (workstream C) works off main and needs the QA findings
doc ON main to take the highs; and it stops the branch drifting further from the loops.

---

## ★ Brian's decisions (2026-06-19) — fold these into the plan
1. **QA fixes:** SPLIT — the **new main (Opus) session fixes the 6 BLOCKERS**; the
   **Opus loop takes the 8 HIGHs**. (Sonnet loop stays on its existing roadmap.)
2. **Nano interiors:** **drafts + tuning ONLY** (do NOT wire into the live game);
   cover **ALL seedable interiors**; on the remaining **~$10 Gemini**.
3. **Merge:** gate + merge to main first (STEP 1).

---

## WORKSTREAM A — QA blocker fixes (NEW MAIN SESSION owns these 6)
Source of truth: **`docs/design/QA_PLAYTHROUGH_FINDINGS_2026-06-19.md`** (full repros +
fix locations) + `TODO.json` tier_1 `QA.playthrough_2026-06-19`. All 6 reproduced
in-process AND re-verified against HEAD by grep. Fix on a branch off the freshly-merged
main; full-suite gate before merge as usual.

- **B1** — `Character.from_db_row` → `from_db_dict` at **parser/cp_commands.py:157**
  and **parser/npc_commands.py:120** (skill `train` + NPC trainers fully crash). One-liner ×2.
- **B2/B3** — combat `UnboundLocalError: 'wound'` at **engine/combat.py:1853 & 1872**:
  use `wound_text` (always assigned) instead of `wound.display_name` (only assigned in
  the `damage_margin > 0` branch). Fires on soaked-hit-on-incapacitated + any stun-KO.
- **B4** — **server/session.py:566** `force_sensitive` read off the raw DB dict (it's
  DERIVED state). Use `char_obj.force_sensitive` (char_obj already fetched at :550).
  **Do the whole force_sensitive SWEEP here** (it's one coherent theme — see below).
- **B5** — **engine/housing_lots_provider.py:178** `room_id = host.id` uses the YAML id,
  not the DB AUTOINCREMENT id → 37/40 lots wrong, 4 dropped. Resolve host slug → DB id
  (pass `WriteResult.yaml_to_db`, or look up by slug at seed time). CW-era only.
- **B6** — **parser/medical_commands.py:274** affordability check reads the stale session
  cache; `:324` `adjust_credits(-rate)` runs with default `allow_negative=True`. Read
  fresh DB credits and/or pass `allow_negative=False` + abort on `None`.

### File-lane split (avoid main-session ↔ Opus-loop collisions)
Some files carry BOTH a blocker and a high. To prevent two owners editing one file,
**the main session owns the WHOLE of any file that has a blocker**, including its highs:
- **main session also takes:** H8 combat CP double-spend (combat.py:966/1407/1542 — same
  file as B2/B3); H11 mail sidebar (server/session.py:1867 — same file as B4); H12
  `training force` + the rest of the **force_sensitive family** (server/session.py:566 [B4],
  parser/tutorial_commands.py:156 [H12], parser/force_commands.py:168 [M], engine/locks.py:73)
  — fix all in one sweep; *note* the `server/api.py` force_sensitive reads are the
  web-submission path where the key is legitimately present — verify before touching.

## WORKSTREAM C — loops (Sonnet roadmap + Opus takes the QA highs)
Both loops are armed (Task Scheduler: `SWMUSH-OpusLoop` C:/SW_MUSH_opus opus,
`SWMUSH-DurableLoop` C:/SW_MUSH_loop sonnet; on the Max subscription). They self-heal
across compute gaps (StartWhenAvailable).
- **Sonnet loop:** continue the existing roadmap (it's been doing help-corpus + guide
  quality passes — see CHANGELOG). No change needed.
- **Opus loop → the 8 HIGHs**, in files the main session is NOT touching (disjoint, no
  collision): **H7** chargen cap (engine/creation.py:_cmd_skill ~262 + _validate ~467);
  **H9** buy-order any-resource (engine/vendor_droids.py:1071 → `list(RESOURCE_TYPES)`);
  **H10** BountyTrack flat-2D + funnel bypass (parser/bounty_commands.py:278/291);
  **H13** raw-`str(e)` leak (parser/commands.py:508 — sanitize player msg, log detail);
  plus the **funnel-bypass family** (engine/communal_objective.py:223 `int("3D")`,
  engine/force_powers.py:381/397/620/800) and **phantom imports** (`_parse_dice_str` @
  sabacc_commands:132 / builtin_commands:3790,3916 / space_commands:4181). H14 is test-only
  (tests/harness.py:923). **Setup task (after STEP 1 merge):** point the Opus loop at these
  by updating its resume prompt (`~/.claude/durable_loop/SWMUSH-OpusLoop/prompt.txt`) and/or
  `OPUS_CLAIM.md` to "fix the QA HIGHs in QA_PLAYTHROUGH_FINDINGS_2026-06-19.md §HIGHs,
  files [list above], one drop each, full-suite gate, don't touch the blocker files the
  main session owns." Re-arm with `python tools/durable_loop.py arm --in 30 ... --prompt-file ...`
  or edit the prompt.txt in place (the launcher reads it each fire).

### QA coverage GAP to close
The **onboarding_chains** lane did NOT run (session/compute limit) — re-run that lane
(re-invoke the QA workflow scoped to it, or a break-it-tester agent). The movement lane
partially covered tutorial-chain rooms and REFUTED the "0-exit stranding" claim
(working-as-designed). After the blocker fixes land, **re-run the whole QA campaign** to
catch regressions + the missed lane (script at the workflow path in this session's log).

---

## WORKSTREAM B — Nano interiors (drafts + tuning, ALL seedable, ~$10)
The pipeline is PROVEN (Jedi Temple, 2026-06-18→19). Goal per Brian: **initial drafts +
a tuning pass for every seedable interior, into the review folder, for his judgment —
do NOT wire anything into the live game.**

### The proven recipe (no new tooling needed)
A building interior is a small AreaGeometry zone-map (like `data/worlds/clone_wars/maps/
senate_district.yaml`). Per building:
1. **Author a per-building zone-map YAML at a TEST root** (`static/tools/_interior_test/
   clone_wars/maps/<building>.yaml`) — projecting the zone's real rooms' `map_x`/`map_y`
   from the planet file into bounds + room footprints + exit-graph corridors + landmarks
   (entrance hub + distinctive chambers). Pattern: `static/tools/_interior_test/clone_wars/
   maps/jedi_temple.yaml` (this session's example). Keeping it OUTSIDE `data/worlds/`
   sidesteps the additive guard + avoids a phantom unconsumed file.
2. **Generate the muted seed:** `import tools.make_substrate_seed as mss` + set the muted
   globals from `tools.mapgen.overnight_runner` (`MUTED_STREET/CASING/LM_DIST/LM_GEN`,
   `DISTRICT_HUES=[_warm_neutral(h) ...]`) + `mss.render("<building>", root="static/tools/
   _interior_test", out="static/tools/seeds", tight=True)`.
3. **Author a nameless interior brief** at `static/tools/seeds/<building>_paint_brief.md`
   (pattern: `jedi_temple_paint_brief.md` — "TWO images: image1=floorplan layout,
   image2=style; interior cutaway, warm stone, NO TEXT/water"). Describe chambers by
   type+position.
4. **Paint:** `BatchOrchestrator("<building>", nano_client=NanoClient(key), screener_provider=None,
   boundaries_path=<gitignored>).run_batch(n_candidates=4, timestamp="<id>", style_reference_image=<plate>)`.
   STYLE ANCHOR: there's no hand-made interior plate; use ONE consistent painterly plate
   across all interiors for set cohesion — the Coruscant **senate** plate worked for the
   Jedi Temple. (The brief carries the content; the anchor is style-only.)
5. **Tune** if artifacts appear (same muted recipe already applied; iterate the brief).
6. Build a review montage into `static/tools/batches/_review/`. **NEVER `select`** (never
   overwrite a real substrate) — drafts only.

### First task: ENUMERATE the seedable interiors
Grep the planet YAMLs for multi-room interior **zones** whose rooms carry `map_x`/`map_y`
+ in/out/up/down exit graphs (the feasibility named **Jedi Temple** [done] + **Senate
building** [done as the senate_district city-map]; look for cantina/hangar/cellblock/
cantina-back-room/garrison interiors across all 6 planets). Then drafts+tune each, spreading
the ~$10 (real ~3–4¢/image → ~250 images; budget ~n=4 draft + ~n=4 tune per interior).

### State / artifacts (this session)
- Jedi Temple test: `static/tools/_interior_test/clone_wars/maps/jedi_temple.yaml` +
  `static/tools/seeds/jedi_temple_paint_brief.md` + seed + `static/tools/batches/jedi_temple/
  jt1/` candidates + `_review/jedi_temple_test.png`. All **uncommitted** (test scaffolding).
- All 8 CITY maps have good tuned/generic versions: `_review/best_overview.png`, `_review/
  best/`, per-city `_review/<city>_sheet.png`. Tuned candidates in `<city>/tn1_*|tn2_*/`.
- Feasibility (outer tiers data-blocked): `docs/design/nano_tier_depth_feasibility_2026-06-19.md`.

---

## Budget / key / guardrails
- **Gemini ~$10 left** (Brian refilled $13; ~$2.6 spent on the 3 city tunes + Jedi Temple).
  Real ~3–4¢/image. **Stretch it across all interiors.** Key is in the **Windows USER env**
  (`GEMINI_API_KEY`) so headless/scheduled runs authenticate; pass inline for attended runs;
  **never commit it**. Remove when fully done: `[Environment]::SetEnvironmentVariable('GEMINI_API_KEY',$null,'User')`.
- **Anthropic key = timers + Director ONLY** (memory `anthropic-key-budget-guardrail`). Do
  Nano visual QA yourself (Opus session, Max sub) — NOT the mapgen Haiku screener. The dev
  loops run on the Max subscription (their launchers clear ANTHROPIC_API_KEY).
- **SWMUSH-NanoLoop is disarmed** (the city sweep is done). Interiors run attended/in-session.
- Memories: `inflight-nano-overnight-campaign-2026-06-18` (full Nano state),
  `anthropic-key-budget-guardrail`, `maps-quality-automation-future`,
  `threaded-test-methodology`, `sole-developer-deconflict-with-self`, `durable-loop-scheduler`.

## Launch read (for context)
Feature backlog is largely delivered; the remaining gate is this **QA campaign's fixes**
(6 blockers + 8 highs) + the hardening cluster (T3.19/20/21) the loops keep chewing +
**hosting** (home-box internet reachability, unstarted) + Brian's calls. None of the QA
findings block *booting*; they break core player loops. Est. to live ≈ a few days, gated by
QA-fix throughput + hosting, not features. Maps are non-blocking polish (hand-made ship fine).
