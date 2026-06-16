# Session close-out + handoff — 2026-06-15

*For the NEW interactive dev chat. Read `CLAUDE.md` + `MEMORY.md` +
`memory/inflight-main-march-2026-06-14-pm.md` first, then this.*

## Where things are
- **`origin/main` = `adbfc99`.** Worktree for the **interactive dev chat = `C:/SW_MUSH_live`** (clean). The autonomous loop has its OWN worktree now — see below.
- Recent shipped (this multi-session arc): T3.17/T3.18 (client parity, a11y, smart-buttons, sheet content), kyber/decision-3, T3.13 +leave-master + +authorize (approval pre-auth), Cities client-polish + dissolve-confirm + refund-fix, and **T3.16 Space Wildspace Drops 1a / 2 / 2b / 3 / 4** (cache framework, Sieges + Hutt Frontier theaters, faction caches + rep, equipment mods).

## SCOPE (current — Brian 2026-06-15)
- **T3.13 Padawan/Master → POST-LAUNCH.** Core (bond + trials + +teach/+spar/+leave-master/+authorize) is shipped and stays. **Do NOT build the expansion** (council / lineage / re-assignment) pre-launch.
- **T3.14 Cities → POST-LAUNCH + OPTIONAL.** Core (founding/expansion/taxation/governance) is shipped but the world must not outgrow the player count → **likely gate `+city found` OFF at launch via a feature flag** (enable post-launch only if population warrants). Don't build multi-city/discovery pre-launch. *(Open task: add the launch feature-flag to disable city-founding — small.)*
- **T3.16 Wildspace stays PRE-LAUNCH.** Nearly done — only **Drop 5 (web cache panel)** + the **refinery-rtype follow-up** (`T3.16.D4.REFINE_RTYPE_DEFERRED`) remain.

### Pre-launch priority order (what to build next)
1. Finish **T3.16** (Drop 5 web panel; refinery-rtype decision + conversion).
2. **T3.19** tunables externalization + telemetry.
3. **T3.21** optimization + **security** pass.
4. **T3.22** ambient NPC life, **T3.23** party skill challenges.
5. **tier-2 pre-launch tail:** command-syntax rework, help/Codex rework, web-landing.
6. Final hardening: full-suite-green, doc/arch reconcile.
(T3.24 = explicitly post-launch.)

## The autonomous loop (now actually viable)
- **Cost fix:** the durable loop billed **~$31/day metered Opus on the API key, which also hit $0 balance → it produced NOTHING all day (13 hourly no-op "credit balance too low" fires).** Fixed: the launcher now **clears `ANTHROPIC_API_KEY` → runs on the flat-rate Max subscription**, at **`--model sonnet`** (it can escalate to Opus subagents for genuine planning/judgment). No more per-token fees.
- **Own worktree:** the loop runs in **`C:/SW_MUSH_loop`** (branch `loop/auto`), separate from `C:/SW_MUSH_live`. **So the loop + this dev chat run concurrently with NO worktree collision** (both ff `main` + push; only CHANGELOG/TODO merge-conflict, resolved by union). You do NOT need to disarm the loop while you work here.
- **Schedule:** recurring `--every 60` (self-healing — a killed fire can't break the chain). Its brain: `C:/Users/btgla/.claude/projects/c--SW-MUSH/loop_resume_main_march.md` (has the scope banner + the recover-stranded-WIP-first rule + single-process-gate rule).
- **Verify it's working:** check `C:/Users/btgla/.claude/durable_loop/SWMUSH-DurableLoop/logs/run_*.log` — a healthy fire shows real work; "Credit balance is too low" would mean it's back on the API key (it shouldn't be). Disarm: `python C:/SW_MUSH_loop/tools/durable_loop.py disarm`.

## Open decisions / flags for Brian
1. **Cities gate-off-at-launch** — confirm: add a feature flag disabling `+city found` at launch? (Implied by "optional, world-size".)
2. **`T3.16.D4.REFINE_RTYPE_DEFERRED`** (in `design_calls_pending_brian`) — refined-resource rtypes + 3× sell-anchor + recipes (refinery conversion is stubbed pending this).
3. **`CITY.dissolution_refund_formula`** = resolved+shipped; **`PM.approval_pending_store`** = resolved (pre-auth-only, shipped as +authorize).
4. **Live Director at launch** needs the paid API funded/reachable (the standing `anthropic-api-box-blockers`: $0 credits + corporate-TLS-proxy). The dev loop now sidesteps it via subscription, but the *runtime* Director still needs it — launch dependency.

## Launch estimate (updated for the descope)
With T3.13 + T3.14 expansions OUT of pre-launch, remaining pre-launch is: finish T3.16 (small), T3.19 + T3.21 hardening, T3.22/T3.23, the tier-2 tail, final hardening — roughly **~15–30 drops**. With the loop now able to run autonomously (subscription, no $/fire) + interactive sessions: **~1.5–3 weeks to launch-ready**, gated mainly on the hardening tail (full-suite-green + security) and the live-Director API dependency (#4).

## Avoid-lanes (parallel engine session)
`engine/harvest.py`, `engine/combat.py` (+ `death.py`/`npc_combat_ai.py`), `engine/director.py`. Era-clean, funnels, no-phantom, single-process test gates (xdist OSErrors/orphan-swarms on this box).
