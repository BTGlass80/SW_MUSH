# HANDOFF — xdist full-suite triage session (2026-06-13)

**For:** a dedicated parallel session whose job is to run the full pytest
suite under **pytest-xdist** (`-n auto`), then fix what it surfaces — with
the discipline of judging each failure **"real bug vs bad test"** before
touching anything.

**State at handoff:** `main` is at `07fbd70` (drops 24–43 merged + pushed
to origin). `pytest-xdist 3.8.0` + `execnet 2.1.2` are installed in the
venv. The agent that merged ran a 565-test **targeted** regression green +
reconciled the 2 known count-pin canaries, but **never completed a full
single-threaded run** in its harness (background runs got reaped; repeated
launches contended). That's exactly why this session exists.

---

## Run it

```
python -m pytest tests/ -n auto -p no:cacheprovider --continue-on-collection-errors -q
```

- `-n auto` → 12 workers on this box (~8,800 tests, expect ~2–4 min vs
  ~12 min single-threaded).
- The canonical gate `run_all_tests.bat` is **single-threaded** — keep it
  as the source of truth; xdist is the fast triage lens.
- Write to a log you can poll live: `... 2>&1 | tee /tmp/xdist.log`.

## ⚠️ The core discipline — real bug vs bad test (per Brian)

xdist runs tests **in parallel across processes**, which surfaces failures
a serial run hides. This codebase has KNOWN test-isolation hazards, so
**expect false positives** and triage each:

**Likely-BAD-TEST (parallel-isolation false positive) — fix the test, not the engine:**
- **`engine.world_events._manager` singleton** — CLAUDE.md flags it:
  "reset to `None` between tests or event state leaks." A test that sets a
  world event and another that asserts none-active, on different workers,
  will collide. Fix = proper setUp/tearDown reset, not engine change.
- **aiosqlite / in-memory DB fixtures** — `Database(":memory:")` fixtures
  are loop-bound and per-connection; module-scoped DB fixtures shared
  across xdist workers can race. Many tests use `event_loop_for_tests`
  module fixtures (see `test_world_writer.py`) — these are fine within a
  worker but suspect if a failure only appears under `-n`.
- **Module-level / global state** — corpus caches (`chain_events._CORPUS_CACHE`,
  reset via `_reset_corpus_cache()`), era config (`set_active_config` /
  `clear_active_config`), the bounty/mission singletons. A test that
  forgets to reset one taints the next on the same worker.
- **Shared on-disk artifacts** — anything writing a real file/db path
  (not `:memory:`) that two workers touch at once.
- **Order-dependent tests** — a test that only passes if a prior test ran
  first (xdist's `--dist loadscope` keeps a class on one worker; bare
  `loadfile`/`load` may split them).

**Likely-REAL-BUG — fix the engine (or escalate):**
- A failure that ALSO reproduces single-threaded (`python -m pytest <that test> -q`)
  → real. **Always confirm a suspected real bug reproduces serially**
  before fixing engine code — that's the cleanest real-vs-bad-test test.
- Logic/assertion failures unrelated to shared state (dice math, a
  None-deref, a wrong value) → real.
- A genuine count-pin drift where the COUNT is wrong because content was
  added wrong (vs a stale pin — see below).

**The count-pin canary class (you'll hit these — judge each):**
Several tests hardcode whole-table totals (NPC count, landmark count,
chain count) and drift on every content drop. Examples already reconciled
this session: `test_f7c1_village_trials` NPC count (201→211, the 10
t5-trainer NPCs), the chain-count pins (onboarding=9 vs questline-kind).
**Rule:** if the new content is legitimate and the by-name/structural
checks pass, the PIN is stale → update the number with an attribution
comment. If content was added WRONG (a dupe, a phantom), it's a real bug.
The prior full run flagged 2 such canaries; both are now resolved
(village-trials fixed; coruscant-landmark already clean).

## Triage workflow (suggested)

1. Run `-n auto`, collect the FAILED list.
2. For each failure: re-run it **single-threaded** (`pytest <nodeid> -q`).
   - Passes serial, fails parallel → **bad test / isolation** → fix the
     fixture (reset the singleton, scope the fixture, isolate the file).
   - Fails serial too → **real** → confirm, fix engine, add/adjust a test.
3. Re-run `-n auto` until clean.
4. Then run the canonical **`run_all_tests.bat`** (single-threaded) as the
   final gate — that's the authoritative green.

## Watch out for (cross-session)

- **Multiple parallel sessions are live** (guides rework, map/command
  specs, this one). Stay in your lane: don't edit CHANGELOG.md / TODO.json
  beyond your own append; don't commit other sessions' uncommitted strays
  (guides, architecture_v52, command/map specs). The merge agent kept its
  commits strictly scoped — do the same.
- **The harness reaps long background runs** — the working approach was a
  single `run_in_background` pytest with a `tee` log, then poll the log
  with a bounded loop (don't launch competing runs; they contend and crawl
  — that bit the merge agent: 7 concurrent full-suite runs dragged it to
  8% in 10 min).

## If xdist itself causes trouble
If `-n auto` produces unfixable isolation noise, fall back to
`-n 4 --dist loadscope` (keeps each test class on one worker — much
gentler on class-level shared state) or just run the canonical
single-threaded `run_all_tests.bat` and triage its (smaller) failure set.
