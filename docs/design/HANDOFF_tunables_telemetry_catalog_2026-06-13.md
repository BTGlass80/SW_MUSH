# HANDOFF — T3.19 Tunables + Telemetry Catalog (pre-build design input)

> ## ⚠️ POINT-IN-TIME — captured at commit `e58b0fc` (post-Drop-42). MAY BE SUPERSEDED.
> The session ships multiple drops/day; the values, file:lines, and "not-yet-tunable" claims
> here may already be stale by the time T3.19 builds. **Re-grep each knob against HEAD before
> externalizing it** (line numbers especially drift). The knob *names* and the *architecture*
> are durable; the specific value+location is the volatile layer. Head-start, not current truth.

CLAUDE.md flags T3.19 specifically: *"re-think the design before building; the telemetry
catalog is the named example."* This doc IS that catalog. Read-only sweep of 4 engine domains
(economy, combat/dice, crafting/harvest, progression/director/territory).

## TL;DR

- **73 tunables catalogued, ~41 HIGH-priority, ZERO currently externalized.** `server/config.py`
  has a "load from YAML" docstring that is **never implemented**; `TUN.*` keys are a
  doc/comment convention only, not runtime. The whole tunables system is aspirational — T3.19
  builds it.
- **The #1 finding is a real BUG, not a missing knob:** the Director's Claude-API cost tracking
  (the ~$20/mo circuit breaker) is broken two ways (below). Fix this first — it's cost control.
- **The config answer is EXTEND, not add:** mirror the existing
  `engine/director_config_loader.py` YAML-overrides-with-byte-equivalent-default pattern.

## 🔴 #1: Director API-cost telemetry is BROKEN (verified HEAD) — fix first

The ~$20/mo circuit breaker can't reliably do its job:
1. **In-memory only, resets on restart.** `claude_provider.py` accumulates `_month_spent_cents`
   and trips the breaker at 90% ($18) — but it's in-memory and resets to 0.0 on every server
   restart (and UTC month rollover). **A nightly restart silently re-arms the full $20 budget**;
   the breaker can't stop cross-restart overspend.
2. **The durable log is fed ZEROS.** `engine/director.py:1094-1095` hardcodes `tok_in = 0` /
   `tok_out = 0` into `log_event` (verified at HEAD), with a comment admitting exact tracking
   "would require returning from generate()". So `director_log.token_cost_*` is always 0, and
   `@director budget` reports **~$0 spent forever** regardless of real spend.

**Fix:** (a) make `ClaudeProvider.generate()` return/expose the real per-call (input_tokens,
output_tokens) — it already reads `response['usage']` — and thread them into `director.py`
`log_event` (replace the hardcoded 0/0); (b) on boot, seed `_month_spent_cents` from
`SUM(director_log)` for the current month so the breaker survives restart; (c) emit a
per-faction-turn record `{month, in_tok, out_tok, cost_cents, cumulative_month, pct_budget,
breaker_state}` so Brian watches the burn live. Also unify the duplicated Haiku $1/$5 pricing
constants (`claude_provider.py:34-35` vs `director.py:1414-1416`). **Self-contained in
director+provider — zero crafting collision.**

## The telemetry SEAMS (instrument these few, get broad coverage cheap)

The funnel-function invariants mean almost all telemetry hooks at ~4 chokepoints:

| Seam | file:line | State | Win |
|---|---|---|---|
| `adjust_credits` | `db/database.py:2611` | **ALREADY instrumented** (`credit_log`) — `@economy` + velocity read it | analytics on existing data; no new emit needed |
| `perform_skill_check` | `engine/skill_checks.py:142` | emits NOTHING | **biggest single win** — one emit `{skill, difficulty, total, margin, success}` = balance telemetry for crafting/harvest/repair/social across the whole game. SYNC → fire-and-forget/buffered, not await |
| `_resolve_attack` | `engine/combat.py:1047/1068` | emits nothing | one emit `{pool, defense, roll, soak, margin, wound}` = entire TTK/lethality dataset |
| Director tick | `engine/director.py:1794/772` | partial | the per-faction-turn cost record (see #1) |

## TOP HIGH-priority knobs (the post-launch balance dials Brian touches first)

| knob | file:line | value | controls |
|---|---|---|---|
| `trade.price_demand_multiplier` | `trading.py:114` | 1.40 | THE trade-loop profit dial (narrowed from 2.0 to kill the 4:1 exploit — most exploit-sensitive number) |
| `trade.price_source_multiplier` | `trading.py:112` | 0.70 | buy price; sets the route margin (currently 2:1) |
| `trade.supply_max_luxury_goods` | `trading.py:191` | 6 | throttle bounding credits/hour from grinding trade |
| `trade.max_depression` | `trading.py:297` | 0.30 | anti-farming ceiling |
| `mission.reward_smuggling_max` | `missions.py:134` | 5000 | highest single mission payout server-wide |
| `bounty.reward_superior_max` | `bounty_board.py:66` | 10000 | largest board faucet (whale-income knob) |
| `p2p_trade.tax_pct` | `builtin_commands.py:5543` | 5 | the only P2P sink — anti-laundering dial |
| `commissary.sellback_rate` | `commissary.py:268` | 0.50 | refund rate — laundering-faucet risk if too high |
| `insurance.percentage_of_bounty` | `death.py:494` | 10 | PvP death-economy drain |

(Full 73-knob list — bounty/mission reward bands, refresh intervals, harvest yields, threat-band
multipliers, territory thresholds, CP costs — in workflow task `wgc5pzgqe.output`.)

## Config architecture (EXTEND, don't add)

One `data/tunables.yaml`, namespaced by the SAME dotted `TUN.*` paths already in comments
(`trade.*`, `bounty.*`, `mission.*`, `harvest.*`, `wound_margin.*`) — so the existing doc
convention becomes the live key schema (zero new vocabulary). Add `load_tunables()` to
`server/config.py` reading the YAML once at boot, with the **current hardcoded literals as
in-code defaults** so a missing/empty YAML is byte-identical to today. **Mirror
`engine/director_config_loader.py`** — it already does this exact YAML-override-with-legacy-
default seam. One flat namespaced file (not per-domain — over-engineering at 73 knobs).

## Externalization plan (ordered, collision-aware)

| Phase | Scope | Crafting collision? |
|---|---|---|
| **0** | `load_tunables()` foundation + empty-YAML-equals-today test | None (config only) |
| **1** | HIGH economy knobs: trade.* cluster + mission/bounty reward maxes + p2p_tax + commissary + insurance | None (not crafting files) |
| **2** | Fix Director cost telemetry (#1) | None (director+provider) |
| **3** | Instrument `perform_skill_check` (biggest telemetry win) | **HOLD** — `skill_checks.py` is the funnel harvest+crafting call; wait for crafting lane to settle |
| **4** | Combat telemetry seam + combat knobs | None (combat.py disjoint from crafting) |
| **5** | harvest.* externalization | **HOLD** — `harvest.py` is in the session's hot lane |

## Collision note

Catalog is read-only; the BUILD edits balance code. Phases **0, 1, 2, 4 share no files with the
session's crafting lane — safe to build in parallel.** Phases **3 and 5 land in the crafting/
harvest hot files (`skill_checks.py`, `harvest.py`) — HOLD until the crafting lane merges, then
rebase the instrumentation onto settled code.** `adjust_credits` is already instrumented, so
that seam needs no edit (removing one collision entirely).

## Catalog gaps (honest completeness)

Thin on: combat/dice *telemetry* points (it got combat tunables but few combat emit seams),
progression/XP knobs, and director/territory tunables beyond cost. A follow-up pass should
deepen those before the build closes T3.19.

*Full 73-tunable + telemetry inventory: workflow task `wgc5pzgqe.output`.*
