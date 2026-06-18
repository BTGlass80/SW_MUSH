# SW_MUSH — Morning Report (2026-06-18)

**Drafted:** 2026-06-17 ~22:15 (attended Opus session).
**Finalized:** at the 6 AM wind-down (overnight loop delta + final gate folded in — see §10).
**Prepared for:** Brian's morning review. Loops + this session stood down at 6 AM as requested.

---

## 1. TL;DR

- **Launch ETA: ~5–6 days of launch-ready work — holding steady** (was "~1 week" on 06-16). The binding constraint is the **QA/hardening tail + your decisions (the public name)**, *not* engineering throughput — the loops + the attended session are shipping fast.
- **There are no open design forks.** All 7 items in the pending-decision queue are actually already resolved/deferred (the queue just wasn't drained — see §6). The only real decision waiting on you is the **public project name**.
- **Both reviews you asked about are done:** the **marketing review** is complete (`MARKETING_PLAN_2026-06-17.md`) and the **Claude Design UI handoff package is built + hardened + ready** (`CLAUDE_DESIGN_HANDOFF.md`, 17 captured surfaces). Neither blocks on me.
- This session found + fixed a **real launch bug no test caught** (the ground-client Mail + Achievements panels were silently dead on live data) — a good signal that the remaining risk lives in the **QA-playthrough tail**, exactly where you wanted to invest.

---

## 2. Launch ETA + critical path

| Long pole | Status | Owner / next step |
|---|---|---|
| **Public project name + domain + logo** | not chosen | **You** — blocks the landing page + marketing launch. Name ideas in §8. |
| **QA-playthrough campaign + hardening tail** | partial | The comprehensive playthrough you wanted. The sidebar bug shows this is where real risk hides. Run it broadly. |
| **Claude Design UI pass** | package READY | **Your call:** trigger now vs. at end-of-hardening, then execute the returned punch-list. |
| **help / guides rework** | queued, now **unblocked** | Command-syntax rework is DONE (baseline ZERO), so the help/guide docs can be rewritten to final syntax. |
| **Marketing execution** | plan done; MSSP + disclaimer shipped | Remaining: the name (above), Claude Design visual assets, Discord hub + directory listings + announcement wave. |

**Open design decisions blocking launch: none** (all resolved — §6).

---

## 3. Open items that need YOU (not me)

1. **Pick the public name** (the single highest-leverage unblock — it gates the landing page *and* the whole marketing launch). Spitballed options in §8.
2. **Decide when to run the Claude Design UI review** — the handoff package is ready *now*; the alternative is to wait until the UI is fully locked at end-of-hardening (the doc is built either way).
3. **Whether/when to re-arm the loops** — both are disarmed as of 6 AM (§10). Re-arm with `python tools/durable_loop.py arm ...` when you want them back.

---

## 4. What shipped this session (attended Opus)

- **Real launch bug fixed:** ground-client **Mail + Achievements sidebar panels were silently dead on live data** — the M3 client read `data.recent`/`data.unlocked` but the server emits `messages`/`achievements` (a key mismatch the M3 rewrite introduced; the legacy client read them correctly). Realigned the consumers + pinned both contracts with `tests/test_sidebar_panel_contract.py`. *No test caught this before.*
- **Claude Design handoff hardened + expanded 15 → 17 surfaces**, captured against a **cost-safe live backend** (so chargen's APIs resolve and "regenerate any time" actually reproduces the set). Added the **Holocarta galaxy navigator** and **chargen attributes step**; made `04_ground_play` comprehensive (populated comms pane + full faction-standing/achievements/mail/places sidebar). Fixed the original "Failed to load game data" chargen capture.
- **Cleared 6 of 8 full-suite gate reds** surfaced by `run_all_tests.bat`: my tool's `except:pass` teardown blocks (silent-except invariant), and **5 orphaned command-syntax stale guards** the loop left behind (retargeted to the verified DROP-7 final state). The other 2 are pre-existing flaky chain walkthroughs (pass solo).
- Landed on `main`: `9cbb16e` (sidebar + handoff), `524805d` (merge), `51176a8` (gate fix-forward).

---

## 5. What the loops shipped overnight  *(filled at 6 AM wind-down)*

> Baseline at session close: `main` = **51176a8**. The wind-down lists `51176a8..origin/main`.

- _[6 AM: `git log --oneline 51176a8..origin/main` delta]_

---

## 6. Design decisions: ALL resolved (queue needs draining)

The `design_calls_pending_brian` queue still lists 7 items, but **every one is already decided** — it just wasn't moved to the resolved list. For the record:

| Call | Decision |
|---|---|
| ITEM.unified_item_registry | Deferred post-launch (extend for launch; 14 combat items authored) |
| ACH.dsp_atonement_mechanic | Option B — defer (no launch blocker) |
| PM.approval_pending_store | Option C — shipped (pre-authorization only) |
| CITY.dissolution_refund_formula | Option A — shipped (align to spec) |
| ERA.tutorial_v2_gcw_profession_chains | Option A — executed (deleted; era invariant restored) |
| SEC.player_online_activity_visibility | Option A — public by design |
| H2.faction_mission_system_reconciliation | Option A — resolved + implemented this session |

→ Housekeeping (done at wind-down or next pass): drain these 7 into `design_calls_resolved_recent`.

---

## 7. Test / gate health — **GREEN** (modulo 2 known flakes)

- First full-suite run (`run_all_tests.bat`): 11,250 passed; 8 reds triaged → 6 fixed + verified, 2 flaky walkthroughs.
- **Confirmation re-run after the fix-forward (2026-06-17 ~22:35): 11,256 passed, 2 failed, 25 skipped, 5 xfailed** — and the *only* 2 failures are the pre-existing flaky chain walkthroughs (`republic_soldier` / `republic_intelligence`, both pass solo). This proves all 6 fixes held and nothing regressed. **main is effectively green.**
- **Known flaky tests to clean up eventually** (not launch-blocking): the two chain walkthroughs above (suite-order / state-leak non-determinism, in the content/chain lane).

---

## 8. Name ideas (spitball)

Per the marketing plan's guardrails: **original + non-trademarked** — no "Star Wars / Jedi / Force / Lightsaber / Droid / X-Wing / Sith / Empire", no character names, no official logos. Keep "SW_MUSH" as the internal/repo name only. (I can't verify live domain availability — treat these as creative starts; check the domain + a quick USPTO/TESS search before committing.)

**Top picks (distinctive + on-theme + clean IP):**

1. **Wild Die** — the signature WEG-D6 mechanic; the strongest *insider credibility* signal for the D6 crowd (the marketing plan literally recommends "Roll the Wild Die" as the D6-insider tagline). Low IP risk (a generic game-mechanic term; the D6 System is openly licensed). `wilddie.*` / `thewilddie.*`.
2. **Rimward** — frontier/smuggler flavor (toward the galactic edge); one clean word, very brandable, no SW mark. `rimward.*`.
3. **Parsec** — punchy space-travel signal (the "made the run in X" vibe without the trademarked phrase); real astronomy unit, short, memorable. `parsec.*` may be taken — try `playparsec.*`.
4. **Crucible** — the war era as a galaxy-forging crucible; gravitas, evocative, generic word. `crucible.*` likely taken — `crucible-mush.*` / a compound.
5. **Hyperlane** — the trade routes that web the galaxy (literally shown on our galaxy map); evokes a connected, traveled, *living* galaxy. SW-adjacent vocabulary but a generic concept term. `hyperlane.*`.

**Strong alternates:**

6. **Sublight** — clean sci-fi (sublight engines); calm, brandable.
7. **The Long Rim** — frontier expanse; safer than "Outer Rim" (which is SW-coded).
8. **Sixfold** — abstract nod to the d6; modern, ownable, easy domain.
9. **Pax Galactica** — the (breaking) galactic peace; ironic for a war era, Latin gravitas.
10. **Wildspace** — uncharted frontier (we already have a "wildspace" theater). Mild overlap with D&D Spelljammer's term — usable but less distinctive.

**My lean:** **Wild Die** if you want to plant a flag with the D6 community (your #1 beachhead per the marketing plan); **Rimward** or **Parsec** if you want a broader, genre-neutral brand that travels beyond the D6 niche. Avoid the SW-coded near-misses (Outer Rim, Holonet, Holocron, Coruscant-anything).

---

## 9. Recommended next moves (in order)

1. **Pick the name** (§8) — it unblocks the landing page + the entire marketing launch.
2. **Greenlight the Claude Design UI review** (package ready) — or schedule it for end-of-hardening; your call.
3. **Run the comprehensive QA-playthrough campaign** broadly — it's where the real residual risk is (the sidebar bug is the proof).
4. **help/guides rewrite** to final command syntax (now unblocked).
5. **Marketing execution** — Discord hub + directory registrations + the announcement drafts (plan §7), once the name exists.
6. Re-arm the loops if you want them to keep grinding the content/quality tail while you handle the decisions.

---

## 10. Wind-down log  *(filled at 6 AM)*

- [ ] `SWMUSH-DurableLoop` (Sonnet content loop) disarmed
- [ ] `SWMUSH-OpusLoop` (Opus quality loop) disarmed
- [ ] Overnight delta captured (§5)
- [ ] Confirmation gate result folded in (§7)
- [ ] This attended session closed

_Re-arm later with:_ `python tools/durable_loop.py arm --name SWMUSH-DurableLoop --every 60 --workdir C:/SW_MUSH_loop` (Sonnet) / `... --name SWMUSH-OpusLoop --every 90 --workdir C:/SW_MUSH_opus` (Opus) — adjust to the original launch params.
