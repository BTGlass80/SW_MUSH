# HANDOFF — Unattended session 2026-06-25 (UI finish + fun pass + audit)

Pick-up doc for Brian's return. Authority order unchanged (TODO.json + CHANGELOG.md first; this is the session narrative). Everything below landed on `main` and is gate-green (two-phase gate; sole red = the accepted `test_cities_phase4b` cargo-tax baseline).

## What I was asked to do
Run unattended: make as much roadmap progress as possible; **finish the UI**, then do the **fun pass**, make obvious fixes from it, **stage decisions** for your return, and **keep working**. Mid-session you asked to **parallelize harder** on the Max x20 capacity.

## Drops landed to `main` this session (5)
1. **UX Drop 8 — living character sheet** (`188f19a`) — delta-highlight (changed-since-last-view) + Force/dark-side identity + two default-on toggles. **Completes the 8-drop UX engagement roadmap core slice.** Pure web-client. 17 tests.
2. **Audit-fix + content batch** (`fb41176`, one ff of 3 commits):
   - **era-clean-chargen** — ~25 GCW-string leaks (Empire/Imperial/Rebel/TIE/AT-AT/X-Wing) re-flavored to CW canon on the chargen wizard + character sheet (the most-visible new-player surface). New regression test.
   - **crew-wage-ledger** — the recurring crew-wage SINK bypassed `adjust_credits` (invisible to the ledger / `@economy`); now routed through the funnel + the two blind-spotted guard tests closed.
   - **wilderness-grind-breadth** — 5 WEG-D6 creatures + 14 huntable encounter pool entries across 4 wilderness regions (the grind-realignment follow-up). 21 tests.
3. **first-session-unblock** (`d3e1d3d`) — **the two kills-it findings from the fun pass.** (a) NAMED exits were unwalkable (exit-chip/dir-buttons sent the bare dir; parser fallback only routed compass words) → now send `move <dir>` AND the dispatcher routes a typed bare exit-name to MoveCommand; (b) the first-run tour overlay ate all input → `pointer-events:none` + Escape-close + auto-dismiss-on-type. **This un-gates the whole game.** 8 tests, all root causes live-verified via the Playwright harness.
4. **fun-followups** (`cfc3477`) — `talk <multi-word NPC>` now opens dialogue (was saying the 2nd word — the tutorial's literal first action `talk Major Tarrn`); ambient-bark consecutive-duplicate suppression (server re-emits buried player output). 5 tests.

> The **Opus quality loop** (SWMUSH-OpusLoop, RUNNING) pushed concurrently throughout — T3.24 questlines ("The Crooked Wheel", "The Lost Courier") + T3.19 telemetry. `main` moved under me several times; every land re-fetched + re-merged (CHANGELOG union). Drop 8 + all my drops are intact in the history.

## The FUN pass (the headline)
Ran `tools/_fun_wf_run.js` — 7 lenses (4 archetypes + onboarding/systems/world), each a real Chromium playthrough + a synthesis. **Verdict: 3/10 "not fun yet — but almost no one got far enough to find out."** The master finding: **6 of 7 lenses never escaped the spawn room** because of the movement + tour-overlay bugs — **both now FIXED** (drop 3). The synthesis was emphatic that the bones are good (production values, the living sheet, the command palette, the writing all scored well) and that "fixing the door probably jumps the score several points." Re-run the fun pass after these fixes for a fresh read — the flagship Drop 4-8 surfaces (GOALS/SITUATION/SCENE/combat HUD/dice) went mostly unseen because they live past the door that was locked.

## The launch-readiness AUDIT
Ran `tools/_audit_wf.js` (read-only, adversarially-verified) — **0 blockers, 4 majors + 2 minors confirmed.** The 4 majors are FIXED (the era leaks → era-clean-chargen drop; the crew-wage ledger bypass → crew-wage-ledger drop). The phantom-verb majors (BOOST switch, command-palette topics) are STAGED (below). Correctness verdict: launch-shippable; the era leaks were the visible-surface debt and are cleared.

## DECISIONS STAGED FOR YOU — `TODO.json design_calls_pending_brian` (7 new)
1. **FUN.combat_zero_cp_reward_loop** — combat pays 0 CP by design; no kill→progress loop for the action/min-maxer archetype. Keep RP-first economy, or add an early-game combat-progress tick?
2. **FUN.chargen_template_chain_identity_collision** — template (Smuggler) + chain (Republic Soldier) force-join + clone-reskin you while your sheet says smuggler. Couple / warn / allow?
3. **FUN.shop_verb_and_natural_verb_surface** — "shop" = manage-your-vendor (not browse); natural verbs error out. Alias pass + rename (folds into the planned command-syntax-rework) or leave? (The exit-name half is already fixed.)
4. **AUDIT.boost_switch_phantom_verb** — cockpit BOOST stages a non-existent `speed +1`. Recommend: remove the dead switch (I can do it on your OK); or build a throttle verb.
5. **AUDIT.command_palette_surfaces_help_topics** — the Drop-7 palette stages non-typeable help-topics → dead-end. Recommend: add `is_command` to HelpEntry + filter (I can implement on OK).
6. **UX.sound_atmosphere_asset_sourcing** — the sound drop is code-ready but BLOCKED on a CC0/licensed-audio + embed-vs-CDN decision. Default: defer.
7. **UX.living_sheet_delta_semantic** — Drop 8 ships per-view deltas; want session-cumulative instead? Low priority.

## READY obvious-fix backlog (not forks — queued, low-risk, I can batch next)
From the audit + fun pass, clear fixes I did NOT land (to wrap at a clean state):
- **Dead consumers**: `auth_status` message handler with no producer; `rank_up` toast reads `data.benefits` never emitted (static/client.html) — pure dead-code removal.
- **Async task-reference hygiene** (minor GC-hazard): Director paid-turn task, telnet read-loop task, ws reader task spawned without a held reference (engine/director.py, server/game_server.py).
- **`+check` funnel**: `parser/d6_commands.py` resolves OOC dice inline via `difficulty_check` instead of `perform_skill_check` (no buffs/telemetry) — minor funnel-compliance.
- **Onboarding copy**: separatist_agent step 3 says "cannot be retried" but the engine allows retry; smuggler step 4 fallback hint is unreachable (parser/chain_commands.py) — soften copy.
- **Help see_also**: already done in era-clean drop.

## State / ops
- `main` HEAD at handoff: **`cfc3477`** + any later Opus-loop pushes (always `git fetch` + re-merge before an ff — the loop is live).
- **Worktrees used**: `C:/SW_MUSH_ux` (UX lane — Drop 8, first-session-unblock, fun-followups, this handoff), `C:/SW_MUSH_events`/`_ambient`/`_wildc` (the audit-fix + content drops). All disjoint surfaces.
- **Two-phase gate** (frozen-gate-safe) unchanged — see `HANDOFF_ux_engagement_drops_6_7_2026-06-25.md`. Auto-ff only if the sole phase-1 red is the cargo-tax baseline.
- **Workflow scripts** (uncommitted, in `tools/`): `_fun_wf_run.js` (fun pass, re-runnable), `_audit_wf.js` (launch-readiness audit), `_wildcontent_wf.js` (content proposer). Re-run via the Workflow tool with `scriptPath`.
- **Throwaway probe artifacts** in `tests/e2e/` (`_move_probe.py`, `_unblock_probe.py`, `_chip_probe.py`, `_tut_probe.py`, `_talk_probe.py`, `_fun_preflight.py`, the `_fun_*/` screenshot dirs, the workflow `fun_*.py`) — safe to delete; gate-excluded (tests/e2e conftest ignores unless RUN_E2E=1).

## Suggested next session
1. **Re-run the fun pass** (`tools/_fun_wf_run.js`) now the door is open — get the real fun read with the Drop 4-8 surfaces reachable.
2. Knock out the **ready obvious-fix backlog** (above) as one QA-cleanup drop.
3. Resolve the **7 staged forks** — several (BOOST, command-palette) are ready-to-implement on your one-word OK.
4. The **tutorial determinism** finding (step-2 sim-room) — re-probe post-unblock to confirm what (if anything) still strands; much was downstream of the movement/tour block.
