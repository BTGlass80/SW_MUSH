# HANDOFF — UX engagement roadmap: Drops 6+7 landed; Drop 8 + fun-QA remain (2026-06-25)

Clean-chat takeover doc. `main` is green and pushed. Two UX roadmap drops
remain plus the fun QA pass. Everything below is verified against HEAD.

## Current state of the world

- **`main` @ `f3ac288`** (pushed to origin). The full UX engagement roadmap is
  **7 of 8 drops landed**:
  - Drops 1–5 + EVENTS (Hollow Sun vertical slice + Ember Court/Ashen Hand) +
    GRIND realignment + wilderness balance + T3.22 ambient Phase 1 + the
    frozen-gate fix — landed by the prior session(s).
  - **Drop 6 — consolidated GOALS / objectives tracker** — `48f9ae3`.
    `_hud_sidebar_goals` on the HUD tick (questline + accepted mission +
    claimed bounty, all from the live board singletons `_hud_active_jobs`
    reads), `static/spa/m3_goals.js`, chips that *stage* the authored verb.
    Fixed a MEDIUM phantom-verb bug (bounty chip staged `JOBS`, which aliases
    `+missions` → now `bounties`).
  - **Drop 7 — Ctrl/Cmd+K command palette** — `f3ac288`.
    `static/spa/m3_command_palette.js` (fuzzy autocomplete over the existing
    access-gated `/api/portal/reference` index, prefetch+cache, top-10, stages-
    not-fires). Fixed a MEDIUM phantom-verb leak (`BactaPackUseCommand`
    sentinel key `__bacta_pack_legacy__` was registered in the help corpus →
    set `key=""` + filter dunder keys in `handle_reference_index`), a MAJOR
    null-guard ordering bug, and 2 minors.

- **Worktree:** this session drove **`C:/SW_MUSH_ux`**, currently on branch
  `drop/ux-drop7-palette` (== `main` == `f3ac288`), tree clean. Do **NOT** edit
  `c:/SW_MUSH` — that is the other (live-engine) session's tree. Per-session
  worktree model (see memory `parallel-session-worktrees`).

- **The Opus content/quality loop pushes to `main` concurrently** (T3.19
  telemetry drops landed during this session). Always re-fetch + re-merge
  before an ff (see the race check below).

## What's left — the next driver's queue

### 1. UX Drop 8 — living character sheet polish (+ optional sound atmosphere)
- TODO ids: **`UX.living_character_sheet`** (TODO.json ~L415) and the optional
  **`UX.sound_atmosphere`** (~L425). Both `status: "DESIGNED (doc), queued"`.
- **Living sheet** (web-client only, NO engine change — all data already flows
  via `sheet_data`): snapshot `sheetPanelData` on each `+sheet` open, diff vs
  the previous open, add a `.sheet-val-changed` highlight to changed
  values/rows; a `sheet-deltas` localStorage toggle; Force-blue / dark-side-red
  accents on the existing FORCE tab + DSP pips, gated on `payload.force` (the
  existing guard) behind a `sheet-force-theme` toggle. **Guardrails:** values
  render immediately + fully; highlight is a decoration layer applied AFTER
  (never gates pace/info); honor `prefers-reduced-motion` (static marker, no
  strobe); `force_sensitive` stays DERIVED — read `payload.force`, never
  recompute. All work in `static/client.html` + a new jsdom test
  `tests/spa/test_living_sheet_deltas.py`. Full spec is in the TODO item.
- **Sound atmosphere** is optional/lower priority — opt-in, off by default,
  per the design doc. Treat as a stretch within Drop 8 or a fast-follow.

### 2. FUN QA PASS — once the UI/UX is fully updated (i.e. after Drop 8)
- Brian's standing ask: run the **fun-focused** playthrough campaign
  (`tools/_fun_wf.js`, already armed) now that the engagement UI is complete.
  This is the "is it actually *fun* to play" pass, distinct from the break-it /
  correctness campaigns. See memory `inflight-e2e-campaigns-2026-06-24`.

## How to land a drop (the pipeline this session used, proven across Drops 6+7)

1. **Branch** off `main` in `C:/SW_MUSH_ux`:
   `git checkout -b drop/ux-drop8-living-sheet`.
2. **Build** via the `drop-implementer` agent (Sonnet) when the spec is settled
   and mechanical — give it the verified seams + the hard guardrails + "don't
   commit, don't touch CHANGELOG/TODO, stop on any real fork." (Drop 8's spec
   is settled — no design fork flagged.)
3. **Adjudicate** in parallel: `invariant-auditor` + `code-reviewer` on
   `git -C C:/SW_MUSH_ux diff HEAD` + an independent targeted re-run + foundation
   smoke. The Opus main session adjudicates findings.
4. **Fix** findings yourself (the main session keeps the judgment endpoints).
5. **CHANGELOG.md** entry (above the most-recent UX entry) + **TODO.json**
   status flip (surgical Edit — see gotcha) in the SAME commit as code.
6. **Commit** (message ends with the `Co-Authored-By: Claude Opus 4.8 (1M
   context)` trailer).
7. **Merge** the latest `origin/main`, **gate**, **ff** (below).

## The two-phase gate — frozen-gate-safe (CRITICAL — do not deviate)

Run **foreground**, timeout-guarded, in two phases. Phase 1 EXCLUDES smoke/slow;
phase 2 runs foundation smoke serially.

```bash
# Phase 1 — unit/integration (xdist, ~2:15 on this box)
cd C:/SW_MUSH_ux && timeout 560 python -m pytest tests/ --ignore=tests/e2e \
  -n auto --dist loadscope -p no:cacheprovider --continue-on-collection-errors \
  --maxfail=300 -o addopts= -m "not smoke and not smoke_slow and not slow" -q

# Phase 2 — foundation smoke (serial, ~15s)
cd C:/SW_MUSH_ux && python -m pytest tests/smoke -m smoke -k foundation \
  -o addopts= -p no:cacheprovider -q
```

- **Auto-ff ONLY if the sole phase-1 `^FAILED` is
  `test_cities_phase4b.py::TestCargoSellInCityTaxed::test_dock_sell_in_city_credits_city`**
  — the accepted cargo-tax baseline red (a long-standing watch-item, not a
  regression). Any OTHER failure → stop and investigate.
- **NEVER** run the all-in-one xdist gate with `-o addopts=` that *includes*
  smoke/slow markers — the smoke/slow tests deadlock the xdist workers and the
  gate hangs at ~99% (the "frozen gate" — we killed 52 hung python procs over
  this once). The two-phase split above is the permanent fix.

## ff-main (checkout of `main` is denied in this model → `git branch -f`)

```bash
cd C:/SW_MUSH_ux && git fetch -q origin
BEHIND=$(git rev-list --count HEAD..origin/main)
# if BEHIND != 0: git merge origin/main --no-edit  (then re-gate)
git branch -f main HEAD && git push origin main
```

The Opus loop pushes to `main` concurrently, so the `BEHIND` check is not
optional. CHANGELOG conflicts → union; TODO.json conflicts → keep-mine.

## Gotchas (learned this session)

- **TODO.json: do NOT json round-trip it.** `json.dump(...)` reformats the
  WHOLE file (a 727-line diff, even with `ensure_ascii=True` — the original
  serializer differs from Python's). Use surgical `Edit` on the one `status`
  field instead. (This is the documented "TODO.json round-trip corrupts"
  gotcha — validate JSON after every edit.)
- **client.html CRLF:** the file is CRLF. If `Edit` fails on a match, edit via
  Python `open(path, newline='')` string-replace, then `node --check` the
  inline-script region.
- **jsdom test harness (`tests/spa/spa_dom_harness`) evals a function SUBSET** —
  do NOT reference a top-level helper from inside an event handler in an
  `m3_*.js` module; inline nested helpers instead (the `_evSig is not defined`
  ReferenceError pattern from Drop 2; Drops 6+7 followed this).
- **Phantom-verb risk on any "stage a command" UI:** verify the staged string
  is a REAL typeable parser verb. Drop 6 staged `JOBS` (wrong board); Drop 7
  surfaced a sentinel `__bacta_pack_legacy__`. The `invariant-auditor` catches
  these — always run it on staging UIs.
- **AskUserQuestion was not working for Brian this session** — present design
  forks in prose with a recommended default and proceed; don't block on the
  tool.

## Standing constraints (unchanged)

Web-first; "best/most-complete, no corners" (conservative only on balance
numbers); surface only genuine forks; decide+build+log, stop only for
irreversible. Hard invariants: extend-don't-add, funnel functions, era-clean
(no Imperial/Empire/Rebel/TIE in production strings), WEG R&E D6 only,
world-YAML additive-only, no phantom producers/consumers, faucets+sinks land
together, `force_sensitive` derived. Per-session worktrees; don't edit other
sessions' trees.
