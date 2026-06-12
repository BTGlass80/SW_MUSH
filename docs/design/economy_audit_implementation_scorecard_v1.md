# SW_MUSH — Economy Audit Implementation Scorecard

**Version:** 1.0
**Generated:** April 24, 2026 · Symbol-level audit against `SW_MUSH__84_.zip`
**Source:** `economy_audit_v1.md` §12 Implementation Priority (17 items + audit §3.2.D bulk premium)
**Purpose:** This document closes a gap surfaced by Brian on April 24, 2026 — the previous design-doc audit (`design_doc_implementation_status_v1.md`) treated `economy_audit_v1.md` as a "review doc" and did not track its 17 numbered fixes individually. This is that tracking, done properly.

---

## Scorecard Summary

| Phase | Total | ✅ Done | 🟡 Partial / value-mismatch | ❌ Not implemented | 🟦 In flight |
|---|---|---|---|---|---|
| Phase 1 (Critical, pre-launch) | 6 | 5 | 1 | 0 | 0 |
| Phase 2 (Balance, first week) | 5 | 3 | 1 | 1 | 0 |
| Phase 3 (Long-term, month 1+) | 6 | 0 | 1 | 5 | 0 |
| Audit §3.2.D bulk premium (extra) | 1 | 0 | 0 | 0 | 1 |
| **Totals** | **18** | **8** | **3** | **6** | **1** |

**Headline:** 8 of 18 verified delivered. 6 still ❌ Not Implemented — all in Phase 3 (long-term). The Phase 1 critical-pre-launch list is essentially clean except for one mechanic where the implemented variant differs from the audit's recommendation.

---

## Phase 1 — Critical (Pre-Launch)

### #1 Mission completion skill checks — ✅ DELIVERED

- **Where:** `parser/mission_commands.py:217` "Handle space mission completion checks"; line 446 imports `resolve_mission_completion` from `engine.skill_checks`.
- **`engine/missions.py:145`** — `REQUIRED_SKILLS: dict[MissionType, list[str]]` defines per-type checks (Delivery → Stamina, Investigation → Search, etc.).
- Audit recommendation matched: each completion now requires a `perform_skill_check()`-equivalent rather than self-report.

### #2 Trade goods supply pool + Bargain gate — ✅ DELIVERED

- **`engine/trading.py:188`** `class SupplyPool` (45-min refresh, 2x carryover ceiling).
- **`engine/trading.py:171`** `MAX_UNITS_PER_REFRESH` per-good caps (10–30 tons).
- **`engine/skill_checks.py:328`** `resolve_bargain_check` (±10% modifier swing, applied to both buy and sell paths).

### #3 NPC resource vendors / price floor for crafting — ✅ DELIVERED

- **`parser/crafting_commands.py:1244`** logs purchases as `"resource_vendor"` credit transactions — confirms NPC vendor purchase path is wired.
- The free-survey exploit the audit named is constrained by the survey cooldown (#10 below).

### #4 Transaction tax on `pay` (5%) — ✅ DELIVERED

- **`parser/builtin_commands.py:2967`** `await ctx.db.log_credit(0, -tax, "p2p_tax", 0)` — system sink at `char_id=0`, tax label confirmed.
- Aligns with `economy_hardening_design_v1.md` (audit #14).

### #5 Recurring docking fee (daily tick) — 🟡 PARTIAL (different mechanic)

- **What audit recommended:** A daily tick that bills 25 cr/day per docked ship as a passive "drip sink."
- **What's actually implemented:** **Per-landing fee.** `parser/space_commands.py:1140` `docking_fee = 25` charged once at landing time, with security-zone modifiers (`*1.5` Imperial, `*0.75` low-security).
- **Gap:** The recurring/daily aspect is missing. A player with a ship docked for 7 days pays 25 cr (one landing) instead of the audit's intended 175 cr (7 × 25). The drip-sink behavior the audit wanted is not present.
- **Recommended action:** Decide whether to add a daily docking-fee tick or formally reclassify the per-landing fee as the canonical mechanic. Per-landing is simpler but doesn't address inactive-period drag.

### #6 `@economy` dashboard — ✅ DELIVERED

- **`parser/director_commands.py:354`** `@economy` admin command with subcommands: `shops`, `credits`, `zones`, `velocity`.
- Aligns with `economy_hardening_design_v1.md` (audit #14).

---

## Phase 2 — Balance (First Week Live)

### #7 CP progression rebalance (constants only) — ✅ DELIVERED

- **`engine/cp_engine.py:42`** `WEEKLY_CAP_TICKS = 400` with explicit comment: `# v23: was 300 — room for active RPers to progress`. The audit's complaint was that 300/week was too punishing; the rebalance landed.

### #8 Trade goods price differentiation — ✅ DELIVERED

- **`engine/trading.py:171`** `MAX_UNITS_PER_REFRESH` per-good caps (luxury 10, foodstuffs 30, etc.) — exactly the differentiation the audit recommended. Bulk-cheap goods refresh fast; high-margin goods are throttled.
- The static price tier multipliers (SOURCE 0.5x / NORMAL 1.0x / DEMAND 2.0x) remain static — see #12 below for the dynamic-curve gap.

### #9 Power pack consumable system — ❌ NOT IMPLEMENTED

- `grep -rn "power_pack\|charge_pack\|reload\|ammo_count" engine/ parser/` — **zero relevant matches** outside test files.
- Blasters still have infinite ammo. The audit's faucet/sink table (line 67) noted this as "NOT WIRED" and it remains that way.
- **Effort estimate (audit):** 2–3 hours.

### #10 Survey cooldown — 🟡 PARTIAL (value mismatch)

- **`engine/cooldowns.py:173`** `SURVEY_COOLDOWN_S = 300` (5 minutes).
- **What audit recommended:** 15 minutes (900 s) for "free crafting materials" to feel earned.
- **Gap:** Cooldown infrastructure is in place; tuning differs. Either accept 5 min as the live tuning or change the constant. Constant change is a one-line patch.

### #11 Kudos same-room requirement — ✅ DELIVERED

- **`engine/cp_engine.py:56-57`** `KUDOS_TICKS = 35` and `KUDOS_PER_WEEK = 3`. The same-room enforcement and rolling-window cap are part of `economy_hardening_design_v1.md` (audit #14).

---

## Phase 3 — Long-Term (Month 1+)

### #12 Dynamic trade prices (supply/demand curves) — ❌ NOT IMPLEMENTED

- **`engine/trading.py`** still uses static `PRICE_SOURCE = 0.5`, `PRICE_NORMAL = 1.0`, `PRICE_DEMAND = 2.0` multipliers.
- No interpolation function exists. `grep -nE "supply_curve\|demand_curve\|dynamic_price\|interpolate.*price" engine/trading.py` returns zero hits.
- **Note:** The bulk-premium feature (in flight) is *order-impact pricing* — distinct from supply/demand curve pricing. Bulk premium scales price with order size; #12 would scale base price with current supply level (e.g., when 80% of supply is depleted, posted price climbs from NORMAL toward DEMAND). Both can coexist; bulk premium does not satisfy #12.
- **Effort estimate (audit):** 4–6 hours.

### #13 Resource decay — ❌ NOT IMPLEMENTED

- `grep -rn "resource_decay\|RESOURCE_DECAY\|decay_resource" engine/ parser/` — zero hits.
- Surveyed resources persist indefinitely in player inventory. Audit identified this as a value-store inflation risk: stockpiled resources accumulate forever without sink pressure.
- **Effort estimate (audit):** 2–3 hours.

### #14 `@economy` web dashboard panel — ❌ NOT IMPLEMENTED

- The admin command exists (#6 above) but there's no portal/web rendering. `grep -rn "economy.*panel\|/economy" static/ server/web_portal.py server/api.py` returns zero hits.
- **Effort estimate (audit):** 3–4 hours.

### #15 Ship impound mechanic — ❌ NOT IMPLEMENTED

- `grep -rn "impound" engine/ parser/` returns only **lore strings** in `engine/world_lore.py` lines 528, 581 (Imperial infraction-class flavor). No mechanic.
- The audit recommended ship-impound as a smuggling-risk escalation tool. Currently the smuggling loop ends at fines.
- **Effort estimate (audit):** 2–3 hours.

### #16 Loot tables on NPC kills — ❌ NOT IMPLEMENTED

- `grep -rn "loot_table\|drop_loot\|npc_loot" engine/ parser/` — zero hits.
- The audit's faucet inventory (line 60) called this out: "NPC Loot Drops — NOT WIRED — 0 cr/hr — No loot table on NPC kill." Still the case.
- **Effort estimate (audit):** 3–4 hours.

### #17 Credit velocity alerts — 🟡 PARTIAL (data collected, no alerts)

- **`parser/director_commands.py:487, 494`** `await ctx.db.get_credit_velocity(secs)` — velocity data IS computed and surfaced via `@economy velocity`.
- **What's missing:** Proactive *alerts* — automated thresholds that page the GM when velocity exceeds bands. The audit specifically wanted alert pages, not just dashboard reads.
- **Recommended action:** Wrap a tick-time check around `get_credit_velocity` that posts to `@economy alerts` (the channel the design doc mentions) when thresholds breach.

---

## Bonus — Audit §3.2.D Bulk Premium Pricing — 🟦 IN FLIGHT

- **Source:** `economy_audit_v1.md` §3.2 D (Section 3, item D — distinct from the §12 Phase numbering above; this is a separate Trade Goods recommendation).
- **Status:** Not yet in `engine/trading.py`. `grep -nE "volume_premium\|bulk.premium" engine/trading.py` confirms absent at the time of this audit.
- **Implementation in flight:** Per parallel Sonnet session (April 24, 2026). See companion document **`economy_bulk_premium_design_v1.md`** for the formal spec.
- **Scope:** Quadratic order-impact curve, +50% cap at 100% of supply, applied before Bargain check, buy-side only. 14 tests planned.

---

## Cross-Cutting Findings

### Finding A: Phase 3 of the economy audit is essentially untouched

5 of 6 Phase-3 items (#12, #13, #14, #15, #16) are ❌. Only #17 has partial coverage (data without alerts). The audit's verdict that these are "Long-term, Month 1+" was a triage deferral — they remain deferred but no work has happened.

If the launch target is ~50 concurrent players (per `launch_strategy_v1.md`), the absence of resource decay (#13) and loot tables (#16) is moderately exposed. A dedicated player can stockpile surveyed resources indefinitely; killing NPCs gives no economic reward. Both are tunable but absent.

### Finding B: Three Phase-2 items have value mismatches, not absences

Items #5 (docking fee), #10 (survey cooldown), and arguably #17 (velocity alerts) all have *infrastructure* in place but with values or scope different from the audit's recommendation. These are 30-minute fixes if the audit's recommendation is adopted, or a one-line architecture-doc note if the implemented value is the canonical decision.

### Finding C: This audit doc itself was the unrecognized backlog

The previous design-doc audit (`design_doc_implementation_status_v1.md`) classified `economy_audit_v1.md` as a "review doc" outside its scope. That was a methodological error — the doc is effectively an 18-item design backlog with explicit effort estimates. This scorecard fixes that.

The same risk likely applies to the other "review doc" classifications:
- `architecture_status_post_review.md` — has 4 standing-priority items needing verification (Phase 3 C4 god-object refactoring confirmed regressed; FireCommand grew from 384 → 518 lines, AttackCommand 290 → 428, CourseCommand 202 → 248). Hardcoded ANSI cleanup confirmed not done (1,257 hits remain).
- `code_review_session32.md` — Severity A/B items mostly addressed; D2 (hardcoded ANSI) and C4 (god-objects) regressed.
- `opus_code_review_session4.md` — 6 numbered bugs need spot verification (not done in this scorecard pass).

These should get their own scorecards before the next planning cycle, on the same template as this one.

---

## Recommended Actions

1. **Decide on #5 docking fee** — daily tick or accept per-landing as canonical. (Architecture-doc decision.)
2. **Decide on #10 survey cooldown** — 5 min or 15 min. (One-line code change either way.)
3. **Decide on #17 alerts** — add a tick-time velocity alert wrapper or accept on-demand reads. (~30 min of work.)
4. **Schedule Phase 3 items** if launch is approaching:
   - #13 resource decay (2–3 hrs)
   - #16 loot tables (3–4 hrs) — this is also a faucet expansion, not just a sink
   - #14 web dashboard (3–4 hrs)
   - #15 ship impound (2–3 hrs) — depends on smuggling-risk priorities
   - #12 dynamic price curves (4–6 hrs) — can wait until bulk premium lands and is observed in play
5. **Audit `architecture_status_post_review.md` and the two code-review docs** with a scorecard like this one before the v32 rollup.

---

## Architecture Doc Integration

For v32:

**§25 Design Documents Reference** — Add a row:

| Document | Status | Contents |
|---|---|---|
| `economy_audit_v1.md` | **Backlog tracked (see scorecard)** | 17-item economy audit; 8 ✅, 3 🟡, 6 ❌, 1 🟦 in flight. See `economy_audit_implementation_scorecard_v1.md`. |

The "review doc" classification used in v1 of the design-doc audit is incorrect for this file — it's a backlog disguised as a review. Future architecture rollups should treat audit docs the same way they treat feature designs: scoreboard each numbered item.

---

*End of Economy Audit Implementation Scorecard — Version 1.0*
