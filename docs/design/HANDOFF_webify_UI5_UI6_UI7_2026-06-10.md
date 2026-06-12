# HANDOFF — Webify UI-5 (bounty board) + UI-6 (objective/juice) + UI-7 (web onboarding)

**Date:** 2026-06-10 · **Project:** SW_MUSH (Star Wars D6 R&E, Clone Wars ~20 BBY)
**Supersedes for pickup:** `HANDOFF_webify_UI1_thru_UI4b_2026-06-07.md` (still the authority on UI-1→4b internals + the equipment untangle; this doc records what shipped since and what's next).

---

## 0. TL;DR

Two drops this session, one cumulative atomic rollup:

**APPLY THIS:** `SW_MUSH_webify_UI5_UI6_UI7_rollup_2026-06-10.zip`
From the Windows project root: `Expand-Archive -DestinationPath . -Force`, then `run_all_tests.bat`. Root-mirrored; **17 files** (8 modified + 9 new). The same-day `SW_MUSH_webify_UI5_UI6_rollup_2026-06-10.zip` is **superseded** — ignore it.

Shipped: **UI-5** bounty-board modal (`board_state`) · **UI-6** objective line + credit count-up + reward toast (`hud_update.objective`, `credit_event` riders) · **UI-7** web onboarding — designed AND implemented (`web_onboarding_design_v1.md` + `onboarding_state` + training panel + coach pulses + first-run tour).

Also this session: a **real bug fix** (`_hud_active_jobs` bounty branch had never fired — wrong field names) and a **phantom-delivery catch** (`web_client_vision_and_protocol_v1_4.md` was listed in the 06-07 rollup's Files but never packed; **reconstructed** with a provenance note).

**Webify state:** UI-1 → UI-7 ALL SHIPPED. Remaining: **UI-8 crafting** (gated on `T2.CRAFT.integration_design_pass`) and the **commissary fork** (`UI-4b.commissary_vendor_merge`, pending Brian).

**Brian's review action:** browser-walk a fresh character through a chain start→graduation. Copy, pacing, tour placement are best judged live; adjustments are cheap now.

---

## 1. Environment & standing disciplines (unchanged — read §1 of the 06-07 handoff)

Working tree `/home/claude/head` (does not persist); clean ref `/tmp/ref`; verify `/tmp/verify`; outputs `/mnt/user-data/outputs/`. Sandbox: `pip install pytest --break-system-packages` + `npm install --prefix /tmp jsdom` needed fresh each session; `NODE_PATH=/tmp/node_modules` for SPA tests; `aiohttp`/`aiosqlite` absent (DB/server tests fail at import — environment, not regression). Windows full suite (~7,700) is ground truth. All disciplines from the 06-07 handoff §1 enforced and unchanged: phantom-grep, extend-don't-add, atomic root-mirrored zips, AST/YAML validation, trackers same-drop, token-only CSS, real-verbs-only, B3, terse-Brian/self-direct.

**Packaging procedure** (proven again ×2 this session): delta via `diff -rq /tmp/ref head`, explicit file list, existence-check each path, zip, round-trip into `/tmp/verify`, AST + targeted tests, present.

---

## 2. What shipped (per drop)

### UI-5 — Bounty board (modal)
- **Producer:** `engine/bounty_board.py::build_board_state(posted, claimed, now=None)` — `BountyContract.to_dict()` per contract **+ server-derived `expires_in_secs`** (clamped ≥0; None if no expiry — client never trusts its clock vs `expires_at`); viewer's CLAIMED contract prepended + `claimed_id` (deduped); malformed skipped. **NPC contract board only** — Dark-Side Notoriety stays on the PC board surface.
- **Push:** `BountiesCommand` (the `bounties` verb) WS-pushes the **same chain-visibility-filtered list** the Telnet text renders (`filter_visible_bounties` — tutorial bounties never leak). Telnet unchanged.
- **Client:** `static/spa/m3_board.js` (`M3Board`; **`.stop()` drains the 1s countdown — modal close calls it**). Tier filter w/ PAY_RANGES legend; cards: tier stud, crime, reward + alive bonus, live countdown (`--warn` <30 min), DETAILS (org/id/tip), CHAIN tag, claimed pinned first + CLAIMED badge. **Real verbs:** ACCEPT → `bountyclaim <id>` (suppressed while holding a claim), TRACK → `bountytrack`; **no abandon verb exists, none offered**. Token-only tier ramp: extra `--text-dim` → average `--text` → novice `--accent` → veteran `--accent-bright` → superior `--warn`. New **JOBS** quick-action (sends real `bounties`; room-independent, unlike a shop trigger).
- Tests: `tests/test_board_state.py` (7) + `tests/spa/test_m3_board.py` (4).

### UI-6 — Objective line + juice
- **`hud_update.objective`:** module-level `server/session.py::_objective_line(jobs)` (pure, sandbox-testable) — first job wins (tutorial step → mission → bounty → smuggle → spacer quest); bounty format `Hunt <target> — N,NNN cr bounty`; 96-char ellipsis; `""` hides. `_hud_active_jobs` extended with the **tutorial-chain step FIRST** (corpus via `engine.chain_events._get_corpus`, cached).
- **⚑ BUG FIX:** the bounty branch checked `accepted_by`/`"accepted"` but `BountyContract` has **`claimed_by`/`"claimed"`** — it had matched **no contract ever**. Fixed (direct str-enum equality; `str()`-wrapping renders the member name on some Pythons).
- **Client:** boxed `#g-objective` atop the vitals card (literal `▮▮` glyphs preserved). Juice on the real `credit_event`: ~700ms cubic **count-up** on `#g-credits` animating from `credits − delta` (order-independent of `hud_update`), 2.6s **reward toast** (`+N`/`−N cr`, `--self`/`--warn`). Delta-chip preserved; producer unchanged (no `reason` field invented — ledger-tag plumbing is a separate, unscheduled change).
- Tests: `tests/test_hud_objective.py` (12 — incl. functional `_hud_active_jobs` against the real board singleton, fixture-reset; stub corpus via the `_get_corpus` seam).

### UI-7 — Web onboarding (DESIGNED + IMPLEMENTED; Brian's retention mandate)
**Contract:** `web_onboarding_design_v1.md` (repo root). **Audit finding that shaped it:** the tutorial SYSTEM was already fully live — 9 CW chains (authored `npc_intro` briefings, per-step `teaches` command lists, completion contracts, graduation rooms), **web chargen writes `tutorial_chain` at creation** (new players spawn on step 1 in the starting room), 11 F.8.c.2.b hooks fire, graduation teleports, `chain status`/`chain attempt` = Telnet parity. `get_active_step_info`'s docstring claimed "Used by web HUD" — nothing did. UI-7 fills that seam; it is **not** a new tutorial.
- **Layer A — training panel** (`#onboard-panel`, FIRST in the side stack): step rail, title, NPC line, briefing (`npc_intro` re-display), objective, **teaches chips** staging `token + ' '` (the panel **cannot invent a verb** — renders only chains.yaml content); ATTEMPT chip only on `skill_check_passed` staging real `chain attempt`; STEP COMPLETE flash + dot pop on pushed-step increase (first render + same-step re-renders quiet); one-time CHAIN COMPLETE card (DISMISS hides). Credits rewards already toast via UI-6 — zero new plumbing.
- **Producer:** `engine/chain_events.py::build_onboarding_state(char)` layered on `get_active_step_info`, which gained **ADDITIVE** fields (`chain_total_steps`/`teaches`/`npc_role`/`npc_intro`/`completed_steps`; list copies — corpus unmutable; `chain status`/`attempt` consumers green).
- **Push:** `server/session.py::_hud_sidebar_onboarding(char)` (sidebar section; needs char only, placed before the db-gated block). **Graduation memo** `self._last_chain_step` (the `_last_sent_credits` precedent): active → push every tick (idempotent); graduated → push **ONCE** on the in-session transition; **reconnect after graduation = silence**.
- **Layer B — coach pulses** on EXISTING qa anchors only: `look`→LOOK, `say`/`talk`→SAY, `+bounties`→JOBS; finite (~6 beats), unmapped tokens chip-only.
- **Layer C — first-run tour:** 4 marks (input `#cmd-bar-ground` → `#qa-row` → `#g-objective` → `#onboard-panel`); spotlight ring's spread shadow does the dimming; clamped caption card; **skips hidden anchors**; once per browser (`localStorage['m3_onboard_tour_done']`, try-wrapped, `fk_clean_mode` convention — cosmetic state only); **gated on an active chain** (veterans never see it); replay via panel-head `?` (`showOnboardTour(true)`).
- **Deferred honestly (design §5 / ledger §2):** `in_step_location` room hint (needs room-id↔slug per tick) · tutorial_v2 elective rail (parallel system, out of scope) · missions web modal (`+missions` chip stages text for now).
- Tests: `tests/test_onboarding_state.py` (8) + `tests/spa/test_m3_onboard.py` (4).

### ⚑ Phantom caught + reconstructed
`web_client_vision_and_protocol_v1_4.md` was in the 06-07 rollup's CHANGELOG Files list but **absent from Brian's HEAD** (upload script excludes no `.md`) — never packed. **Reconstructed** from the 06-07 handoff §5 with a provenance note; now pins `board_state`, `hud_update.objective`, the `credit_event` riders, and `onboarding_state` (§1.8). Logged in `TODO.json::investigation_notes` (`PHANTOM.protocol_ledger_v1_4_2026-06-07`, RESOLVED).

---

## 3. Protocol ABIs (now pinned in `web_client_vision_and_protocol_v1_4.md` — IN THE REPO)

**SHIPPED:** `region_state` · `combat_state` condition fields · `inventory_state` · `shop_state` (browse/dashboard) · **`board_state`** (§1.5) · **`hud_update.objective`** (§1.6) · `credit_event` riders (§1.7, client-side only) · **`onboarding_state`** (§1.8).
**RESERVED:** `buffs[]` on combat_state (no producer) · `shop_state mode:'vendor'` (commissary fork) · UI-8 crafting messages · UI-7 Phase 2 candidates.

---

## 4. Next steps (build order)

1. **Brian's browser review** of UI-5/6/7 — esp. a fresh chain run start→graduation (copy/pacing/tour placement; flash + graduation moments; pulse feel). Cheap to adjust now.
2. **`T2.CRAFT.integration_design_pass`** — the crafting holistic design pass Brian queued (he suspects sourcebook crafting content was never wired). **This gates UI-8.** Design-heavy: re-think, don't just implement; grep HEAD for what's actually wired before claiming gaps.
3. **UI-8 crafting panel** — after the design pass.
4. **Commissary fork** (`UI-4b.commissary_vendor_merge`) — whenever Brian decides; `mode:'vendor'` slots into `m3_shop.js`.
5. **UI-7 Phase 2 candidates** — only if Brian pulls them forward.
6. Then back to the main roadmap: Lane C remainder + Lane F, Kamino, Drop-5 farming controls, etc. (TODO.json is authoritative).

---

## 5. Key file references (delta on the 06-07 handoff's map)

- **Wireup load order** (`tests/spa/test_client_wireup_42a.py::EXPECTED_SPA_LOAD_ORDER`) now ends: `…, m3_inventory.js, m3_shop.js, m3_board.js, m3_onboard.js`. Stale "11 expected" docstring made count-agnostic (no count assertion exists).
- **client.html adds:** board modal (`board-modal*`, shares `.inv-modal`; `closeBoardModal` calls `M3Board.stop()`); onboarding panel (`onboard-panel`/`onboard-body`, head `?` → `showOnboardTour(true)`); tour overlay (`m3o-tour-*`); reward toast (`#reward-toast`); objective box (`#g-objective`); JOBS qa-btn; dispatch cases `board_state`/`onboarding_state`; CSS blocks `m3b-*`, `g-objective`, `reward-toast`, `m3o-*` after the shop rules. `handleCreditEvent` now also runs `animateCreditsTo` + `showRewardToast`.
- **session.py adds:** `_objective_line` (module-level, ~before `class Session`), `_last_chain_step` memo (next to `_last_sent_credits`), `_hud_sidebar_onboarding`, onboarding call at the top of HUD section 19, `hud["objective"]` at `_hud_active_jobs` tail, tutorial job at its head, fixed bounty branch.
- **chain_events.py adds:** additive `get_active_step_info` fields + `build_onboarding_state` (after it).
- **bounty_board.py adds:** `build_board_state` (after `format_contract_detail`, before the Drop-4b DSP section).

---

## 6. Verification status

Round-trip verified the final 17-file rollup from clean `/tmp/ref`: AST ×10, TODO valid, JS parse ×2; **186 python + 17 jsdom targeted tests green**, including the chain-consumer regression sweep (f8c2b events/phase2/attempt/prereq+skill, chains yaml — proves the producer extension is additive), bounty unit, session55 umbrellas, hygiene ×11, and all six Webify SPA suites. **Known pre-existing Windows failure (NOT this session):** `tests/spa/test_m3_substrate_hybrid.py::test_tier1abody_…` (`10 != 9` in the untouched baseline). DB/server-integration tests not runnable in-sandbox.

---

## 7. One-liner to resume in a fresh chat

> "Apply `SW_MUSH_webify_UI5_UI6_UI7_rollup_2026-06-10.zip`. Webify UI-1→UI-7 are ALL shipped (this handoff §2; protocol ledger v1_4 is now IN THE REPO). Next: Brian's browser review of 5/6/7, then the `T2.CRAFT.integration_design_pass` (gates UI-8) — re-think the design, grep HEAD for what crafting content is actually wired before claiming gaps. Commissary fork still pending Brian. Honor the 06-07 handoff §1 disciplines; package cumulative; verify from `/tmp/ref`."
