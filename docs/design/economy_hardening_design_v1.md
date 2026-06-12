# SW_MUSH — Economy Hardening Drop
## Design Document v1 — Session 17
### April 13, 2026

---

## Executive Summary

This drop implements the remaining 4 items from the Economy Hardening priority (Priority A in the v22 architecture doc), plus the CP Progression Rebalance (Priority D). Two of the original 6 Economy Hardening items were already delivered in earlier sessions (mission skill checks and trade goods supply limits + Bargain gate).

---

## What's Already Done (Verified in Codebase)

1. **Mission completion skill checks** — `resolve_mission_completion()` in `engine/skill_checks.py`, wired into `CompleteMissionCommand` in `parser/mission_commands.py`. 10 mission types mapped, difficulty scales with reward, partial pay on near-miss.

2. **Trade goods supply limits + Bargain gate** — `SupplyPool` class in `engine/trading.py` (45-min refresh, per-good caps, 2x carryover). `resolve_bargain_check()` wired into `_handle_buy_cargo()` and `_handle_sell_cargo()` in `parser/space_commands.py`.

---

## What This Drop Delivers

### 1. Transaction Tax on P2P Credit Transfers (5%)

**File:** `parser/builtin_commands.py` — `TradeCommand._accept()`

The `trade <player> <amount> credits` → `trade accept` flow currently transfers credits 1:1. Add a 5% tax deducted from the transferred amount (recipient gets 95%, 5% is destroyed as a sink).

- Tax shown to both parties in the completion message
- Minimum 1 credit tax (floor)
- Tax is a pure sink — credits are destroyed, not transferred anywhere

### 2. Recurring Daily Docking Fees (25 cr/day/ship)

**Files:** `server/tick_handlers_economy.py` (new handler), `server/game_server.py` (registration), `db/database.py` (query helper)

Every 86400 ticks (~1 day), iterate all player-owned ships with `docked_at IS NOT NULL`. Deduct 25 cr from the owner's balance. If insufficient credits, log a warning but don't impound (yet — impound is a Phase 3 feature).

- Only player-owned ships (owner_id IS NOT NULL, not traffic/NPC ships)
- Only docked ships (docked_at IS NOT NULL)
- 25 cr base fee
- Ships in space (docked_at IS NULL) pay nothing
- Notify player if online when fee is deducted

### 3. Credit Transaction Log (`credit_log` table)

**Files:** `db/database.py` (schema v12 migration, `log_credit()` method, query helpers), `parser/director_commands.py` (`@economy` enhancements)

New `credit_log` table tracks every credit mutation:
- `char_id`, `delta` (+/-), `source` (string tag), `balance` (after), `created_at`
- Indexed on `(created_at)` and `(source, created_at)`

`db.log_credit()` method called from all major credit flows. Source tags:
- `mission`, `bounty`, `smuggling`, `trade_goods`, `entertainer`, `medical`
- `p2p_transfer`, `p2p_tax`, `docking_fee`, `fuel`, `repair`, `ship_purchase`
- `vendor_buy`, `vendor_sell`, `faction_payroll`, `housing_rent`, `crew_wages`
- `sabacc_win`, `sabacc_loss`, `sabacc_rake`

`@economy velocity` subcommand: shows credit flow over 1h/24h/7d windows, top faucets, top sinks, net flow, per-player averages.

### 4. NPC Resource Vendors (Crafting Price Floor)

**Files:** `parser/craftin_commands.py` or `parser/builtin_commands.py` (new `buy resources` command), `engine/crafting.py` (resource vendor data)

NPC vendors sell basic crafting resources at fixed prices, establishing a floor:
- Metal Ore: 15 cr/unit
- Chemical Compound: 20 cr/unit
- Electronic Component: 25 cr/unit
- Organic Material: 10 cr/unit
- Polymer Resin: 18 cr/unit

Available in rooms with a "mechanic" NPC (already detected by the room services system). `buy resources <type> <qty>` command. Fixed quality of 50 (middling — survey can produce better quality for free, but at time cost).

### 5. CP Progression Rebalance (Priority D)

**File:** `engine/cp_engine.py` — constants only

- `TICKS_PER_CP`: 300 → 200
- `WEEKLY_CAP_TICKS`: 300 → 400
- `PASSIVE_TICKS_PER_DAY`: 5 → 10

Target: 1 CP per ~7 days for active players (was 10-12 days).

### 6. Kudos Same-Room Requirement Removal

**File:** `parser/cp_commands.py`

Change kudos target lookup from same-room only to any online player. Small population sizes make same-room a bottleneck.

---

## Files Modified

| File | Change |
|------|--------|
| `db/database.py` | Schema v12 (credit_log table), `log_credit()`, `get_credit_velocity()`, `get_docked_player_ships()` |
| `parser/builtin_commands.py` | Trade command 5% tax, `buy resources` command |
| `parser/director_commands.py` | `@economy velocity` subcommand |
| `server/tick_handlers_economy.py` | `docking_fee_tick` handler |
| `server/game_server.py` | Register docking_fee_tick handler, import |
| `engine/cp_engine.py` | 3 constant changes |
| `parser/cp_commands.py` | Remove same-room requirement for kudos |

---

*End of design document.*
