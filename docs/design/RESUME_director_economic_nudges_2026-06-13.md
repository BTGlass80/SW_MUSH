# RESUME — Director economic-nudges drop (paused 2026-06-13 21:10 EDT)

> **Why this file exists.** Brian is about to run out of usage; resume target is
> **2026-06-13 ~23:15 EDT** (usage refresh + buffer). This doc is the durable
> hand-off so the work continues whether the *same* local session wakes up, a
> fresh local session opens, or a cloud agent picks it up. Everything below is
> HEAD-verified as of the pause.

## Where the work lives (CRITICAL — coordination)

- **My isolated worktree: `C:/SW_MUSH_dir`**, branch **`drop/director-economic-nudges`**,
  based on `main` = `origin/main` = `45cee83`.
- **DO NOT work in `c:\SW_MUSH`.** A *second live Claude session* is mid-drop there
  (an era-validator / Ollama-era-guard drop: `engine/era_validator.py`,
  `engine/idle_queue.py`, `tools/ingest_lore.py`, + tests). Brian confirmed: I stay
  in my own worktree, leave `c:\SW_MUSH` to that session. Their files are DISJOINT
  from mine (I only touch `engine/director.py` + my new test/CHANGELOG/TODO).
- `C:/SW_MUSH_wild` = `opus-parallel` (chain content). `C:/SW_MUSH_dev` = dormant `opus-wt`.
- **`git checkout` is DENIED** in this environment. Mechanics: rename current branch in
  place (`git -C C:/SW_MUSH_dir branch -m <new>`), fast-forward via `git merge --ff-only`,
  move main with `git branch -f main <sha>` (never `git checkout main`).

## What this drop is

**Director step-4 soft economic NUDGES** (`director_scope_and_adaptive_spend_v1.md` §4 step 4;
Brian **decision A**: the Director SEEDS opportunities players can take or ignore — caravans /
rare buyers / bounties — and NEVER pulls price/yield levers). The economy-eyes *perception*
layer (`_compile_economy_digest`) already shipped; this is the *action* layer.

Design (decided, no open fork):
- A deterministic, free (no API) seeder that runs on **every executed faction turn** in
  `_governed_turn`, gated on a populated server + a 1h cooldown.
- It reads the live economy digest and fires **one** decision-A-SAFE event:
  **`merchant_arrival`** (= `rare_vendor`, a merchant caravan: content + a credit SINK).
  Live consumer verified: `parser/space_commands.py::apply_rare_vendor_discount`.
- It NEVER fires the price/yield-LEVER events (`trade_boom` / `spice_demand` /
  `bounty_surge` / `intelligence_thaw`) as an economic intervention (decision A), and adds
  **no new faucet/sink** (reuses an event already balanced at ship).
- Two trigger conditions (pure, testable classifier `_classify_economic_seed`):
  **wealth_surge** (faucet ≥ `ECON_SURPLUS_RATIO`×sink) and **trade_boom** (≥ `ECON_BUSY_TXNS`
  txns with a commerce-flavored dominant faucet). Thresholds are first-cut/playtest-tunable.

## DONE (committed in this checkpoint)

All in `engine/director.py`:
1. Module constants block after `OVERNIGHT_CATCHUP_LOOKBACK`: `ECONOMIC_SEED_COOLDOWN_SECONDS`,
   `ECONOMIC_SEED_MIN_PLAYERS`, `ECON_BUSY_TXNS`, `ECON_SURPLUS_RATIO`, `ECON_MIN_FLOW`,
   `ECON_TRADE_SOURCE_HINTS`, `ECON_SEED_EVENT="merchant_arrival"`, `ECON_FORBIDDEN_LEVER_EVENTS`.
2. Instance state in `__init__`: `self._last_economic_seed_time = 0.0`.
3. `@staticmethod _classify_economic_seed(eco)` + `async _seed_economic_opportunities(db, session_mgr, online, now=None)`
   placed right after `_compile_economy_digest`.
4. Call site in `_governed_turn` after `_safe_faction_turn` (fail-open try/except).
- `director.py` passes `ast.parse` (verified).

## REMAINING (the resume task — do these in order)

1. **Write `tests/test_director_economic_nudges.py`** (per-drop test file is mandatory).
   Cover, at minimum:
   - `_classify_economic_seed`: None on empty / sub-`ECON_MIN_FLOW`; `wealth_surge` when
     faucet≫sink; `trade_boom` when busy + commerce-flavored dominant faucet; None when busy
     but dominant faucet is NOT commerce (e.g. `"admin_grant"`); wealth_surge beats trade_boom.
   - `_seed_economic_opportunities`: returns None when `online < ECONOMIC_SEED_MIN_PLAYERS`;
     returns None within cooldown; FIRES on a qualifying eco (stub `db.fetchall` to feed
     `_compile_economy_digest`; reset the world-events singleton `engine.world_events._manager = None`
     per the CLAUDE.md isolation gotcha; stub `session_mgr` with async `broadcast` + `all=[]`);
     when `activate_event` is declined (e.g. same-type cooldown) the seed cooldown is NOT burned.
   - **Invariant guard test**: `ECON_SEED_EVENT not in ECON_FORBIDDEN_LEVER_EVENTS` and the
     forbidden set names the four price/yield levers (documents decision A in code).
   - stub `db` needs async `fetchall` (for `_compile_economy_digest`) + async `execute` (for `log_event`).
2. **Run targeted tests** (FOREGROUND, Windows box):
   `python -m pytest tests/test_director_economic_nudges.py tests/test_director_economy_eyes.py tests/test_director_adaptive_spend.py tests/test_director_living_galaxy.py -x -q`
   (cwd `C:/SW_MUSH_dir`). Fix until green.
3. **CHANGELOG.md** — prepend a dated entry (drop `director-economic-nudges`), grounded in the
   real symbols above. **TODO.json** — mark the handoff next-up item #1 (Director step-4 economic
   nudges) done; note the follow-ups (pc_hook personalization for decision-B per-player wealth
   magnets; prompt-tuning in `director_config.yaml` to let the LLM leverage `digest["economy"]`).
4. **Verify fan-out** (`/verify-drop` or manual): invariant-auditor + code-reviewer +
   smoke-verifier + test-runner. Adjudicate.
5. **Commit** the test + CHANGELOG + TODO (+ this RESUME doc can be deleted on merge).
6. **Integrate**: re-check `main`/`origin/main` (they move — other sessions merge). Merge main
   into my branch (`git -C C:/SW_MUSH_dir merge --ff-only main` or a real merge), run the full
   suite (Rule 1: FOREGROUND `pytest -n auto --dist loadscope -p no:cacheprovider
   --continue-on-collection-errors -o addopts="" --maxfail=200 -q`, timeout 540000), then
   `git branch -f main <my-head>` + push on green. Coordinate with the live `c:\SW_MUSH` session
   (its era-validator drop may land on main first — merge it forward, don't clobber).

## Follow-ups noted (NOT this drop)

- Decision-B per-player wealth/power → content magnet via targeted `pc_hooks` (needs a per-player
  wealth signal; the macro digest is aggregate).
- Prompt-tuning so the paid LLM turn also leverages `digest["economy"]` (lives in `director_config.yaml`).
- Bigger remaining pre-launch picture (HEAD-verified this session): features ~95% done; the bulk is
  the hardening cluster **T3.19 (tunables externalization) → T3.20 (state-preservation; safe-load
  shipped, migration-harness + Force-attr backfill runner remain) → T3.21 (optimization+security)**,
  explicitly last+sequential; plus Director tuning (T3.15 pulled pre-launch), scaffolding seams
  (T3.13/14/16), near-end polish, and free Ollama enrichment (in progress in `c:\SW_MUSH`).
  Equipment-instance migration is NO LONGER the blocker the day-old handoffs framed — drop 47's
  accessor shipped and its consumers (powered-suit drop 50, restraints drops 48-49) already landed.
