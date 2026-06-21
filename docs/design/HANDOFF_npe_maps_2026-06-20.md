# HANDOFF — NPE polish + Nano maps (2026-06-20 evening)

Self-contained pickup for a fresh chat. **Order: finish the NPE pass, then the maps.**

---

## 0. Git / branch state — READ FIRST

- Working branch **`drop/sidebar-contract-handoff-capture`** == **`origin/main`** == **`ce02900`**. Everything below is already merged + pushed. **No gate/merge needed at startup** — just keep working on the branch and ff `main` to it as you land drops.
- **Loops are ENABLED** (`SWMUSH-DurableLoop` = Sonnet content; `SWMUSH-OpusLoop` = Opus quality). They push to `origin/main` during work, so the loop-merge dance below applies on every drop.

### Drops merged this session (newest first)
| commit | drop | what |
|---|---|---|
| `ce02900` | npe-tour-per-character | interface tour keyed per-character + GUIDES coach-mark |
| `f50646a` | in-game-guide-browser | GUIDES button + `help`/`+guide` opens an in-game guide overlay |
| `fa6e618` | nano-align-jedi-temple | garden pin swap + `tools/_grid_probe.py` |
| `f2aed9f`/`f128e26` | npe-live-playtest | combat JSON leak, BH stun-capture stranding, crafting-trials-in-chargen, skill tooltips |
| `2da975d`/`e2b361d` | chargen-csp-frame-ancestors | **launch blocker**: CSP `frame-ancestors 'none'` broke the chargen iframe |
| `5f9759c`/`771b7a6` | qa-rerun-findings | FP-dup, vendor credit-integrity, smoke-harness blind-spots |

**What works now (after a server restart — client.html changed):** chargen loads; combat doesn't dump JSON; BH tutorial `attack <t> stun` advances the capture step; chargen shows no crafting-trial chains and all 76 skills have tooltips; in-game **GUIDES** button + `help`/`+guide`; the interface tour fires once per new character.

---

## 1. NPE — remaining (DO FIRST)

Brian (2026-06-20): chose a **TARGETED** pre-launch NPE pass (not a full rebuild). First-10-min retention is the launch-critical window. Headline items (in-game help + interface tour) are DONE. Remaining:

- **NPE-A — tutorial hand-off clarity.** Once a player lands in their tutorial chain it "got a lot less clear." Make the first 1-3 commands obvious; crisper step `objective`/`next_hint`. Lives in `data/worlds/clone_wars/tutorials/chains.yaml` (step `objective`/`npc_intro`/`next_hint` fields) + how `build_onboarding_state(char)` (`server/session.py::_hud_sidebar_onboarding`) feeds the training panel (rendered by `static/spa/m3_onboard.js`). Mostly data; verify the panel surfaces the exact command to type.
- **NPE-C2 — contextual help hooks.** Surface a relevant guide/nudge the first time a player hits a system (combat / shop / craft / travel). The in-game guide browser already exists (`openGuideBrowser()` in `client.html`; guides keyed by slug via `/api/portal/guide/{slug}`) — a contextual nudge can deep-link to a guide. New server-side first-time hooks (a `sys-event` pose + a "type help" pointer), gated by a per-character "seen this hint" attribute.
- **DEFERRED — post-combat "huge text".** A defeated NPC re-poses its FULL physical description in the brighter/larger **pose** style (vs the dimmer desc style; the `.pose-body` 13.5px vs `.desc-text` 13px delta is minor, so the real fix is stopping the full re-pose, not CSS). **Could not find the server emitter** — needs Brian to re-trigger and paste the exact sequence / browser console. Likely in `engine/pose_events.py`, a chain reveal, or a combat-end NPC re-display.

---

## 2. Maps — Nano (AFTER NPE)

Brian: *"use your reasoning to take a hard look at where you're placing things and make sure they make sense"* + *"regenerate maps for the worst offenders is okay"*. **Gemini key provided** (see §4).

- **Tool:** `tools/_grid_probe.py <map.yaml> <substrate.png> <out.png>` renders the room coordinate grid + labels over a painted substrate so placement is checked **by eye**, not guessed. This is how the Jedi Temple fix was found/verified.
- **Pins are anchored to room coords; the AI painting is NOT** — so labels can land on the wrong painted space. That's the whole problem.
- **DONE:** Jedi Temple (Meditation Garden ↔ Medical Bay swap; garden pin now on the painted greenhouse). Coruscant Works + Gladiator Barracks probe-checked = **already coherent** (reactor=Power Grid, weapon-racks=Armory, etc.). So all 3 *wired* interiors are good.
- **WORST OFFENDERS = city maps** (`tipoca_city` [Kamino — Brian's "strategic cmd in growth chambers" example], `mos_eisley`, `smugglers_moon`, `stalgasin_hive`): uniform-dome **exterior** cityscapes with no per-room interior art → **NOT hand-alignable**. Fix = a NEW per-city tight keymap + a Gemini regen so painted features land in coded cells, then probe-verify. (Or accept them as labeled overviews — the label tells the player what each building is.)
- **6 unwired interior drafts** (have tight seeds in `static/tools/seeds/*_tight_seed.png`): `chalmuns_cantina, cloning_halls, deep_hive, droid_foundry, petranaki_arena, tipoca_admin`. To wire ("wire more" — Brian's choice): re-key for **slug collisions** (their room slugs already live in a city map → "second wins" nondeterminism), align via the probe, then wire as tier-1a AreaGeometries (the `senate_district` pattern: drop `data/worlds/clone_wars/maps/<b>.yaml` + `static/maps/<b>_substrate.png`; the registry binds at boot).
- **Nano pipeline:** `tools/mapgen/batch.py` (`BatchOrchestrator.run_batch(n_candidates, timestamp, style_reference_image)`), `tools/mapgen/nano_client.py` (`NanoClient(api_key)`); muted-seed recipe per `tools/mapgen/overnight_runner.py`. Review candidates under `static/tools/batches/_review/`. **Never auto-`select`** — show Brian candidate sheets to choose. ~$10 Gemini budget.

---

## 3. Operating mechanics — IMPORTANT

- **Git ownership:** you own commit/merge/push. `git checkout` is **denied** by policy → land via `git branch -f main <branch-HEAD>` then `git push origin main` (fast-forward only).
- **Loop-merge dance (every drop):** `Disable-ScheduledTask SWMUSH-DurableLoop, SWMUSH-OpusLoop` → `git fetch origin main` → if advanced, `git merge origin/main --no-edit` and **union-resolve CHANGELOG.md** (keep BOTH entries; TODO.json auto-merges; validate JSON) → commit code → `git branch -f main HEAD` → `git push origin main` → `Enable-ScheduledTask` both.
- **GATE FLAKINESS (this box):** the full xdist gate `pytest tests/ -n auto --dist loadscope` **HANGS** — xdist `execnet` worker zombies accumulate (they run as `python -c "import execnet…"`, NOT `python -m pytest`), causing 99% hangs or `[gwN] node down` crashes. Two rules: (1) if you clear addopts with `-o addopts=` you MUST re-add `--timeout=120 --timeout-method=thread` or a slow/hanging test stalls forever; (2) **prefer SINGLE-PROCESS targeted gates** (no `-n`, `--timeout=120`, scoped to touched modules + `tests/smoke/`) — fast and crash-free. When the full suite *does* run it reaches 99% with **zero** failures. To reap a hung run: `TaskStop` the background task, then PowerShell `Get-CimInstance Win32_Process -Filter "Name='python.exe'"` → `Stop-Process` those whose `CommandLine` matches `execnet` or `pytest` **but NOT `main.py`** (Brian has **2 live `main.py` servers** running — never kill them).
- **Client.html edits:** it's one ~13k-line file with a single huge inline `<script>`. After editing, ALWAYS validate: extract the inline script and `node --check` (a JS syntax error breaks the entire client). Inline-onclick handlers must be exported on `window`.
- **Known baseline reds (not yours):** `republic_soldier` walkthrough (suite-order flake, passes solo), era-scrub "storm"≈Stormtrooper, `test_cities_found` bare-`open()` hygiene, laneb fragment-prune, `tools/mapgen/term_boundaries.json` (working-tree artifact; committed version is empty — never stage it; it's the Nano loop's local learned state).

---

## 4. Secrets / cost

- **Gemini key** (for map regens): Brian provides it in chat — store it as the `GEMINI_API_KEY` env var for the batch run and **remove it when done**. NEVER commit the literal key (GitHub secret-scanning push protection will reject the push, as it did when this key was first pasted here).
- **Anthropic key = timers + Director only** — don't spend the metered key on tooling; loops run on the Max subscription.

---

## 5. Launch context

- Go-live runbook drafted: `docs/ops/GO_LIVE_RUNBOOK.md` (Cloudflare Tunnel + NSSM supervision + domain).
- QA campaign (`QA.playthrough_2026-06-19`) **CLOSED**. Features ~complete. Binding launch constraints now: **NPE polish (in progress) → hosting/go-live (unstarted) → Brian's marketing tail.**
- Authority order unchanged: `TODO.json` + `CHANGELOG.md` are ground truth (see `tier_1_active`: `NPE.targeted_polish_pass_2026-06-20`, `NANO.map_alignment_2026-06-20`).
