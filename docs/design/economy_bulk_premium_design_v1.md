# SW_MUSH — Bulk Premium Pricing Design

**Version:** 1.0
**Generated:** April 24, 2026
**Source spec:** `economy_audit_v1.md` §3.2.D
**Architecture doc target:** v32 §3 Economy / §25 Design Documents Reference
**Implementation status:** Designed — implementation in flight (parallel Sonnet session)

---

## 1. Summary

Buying trade-good cargo currently pays the posted per-ton price regardless of order size. This is the last unimplemented item from the Economy Audit's Section 3.2 ("Trade Goods: A Solved Game"). Items A–C (dynamic price volatility / supply pools, Bargain skill gate) landed in earlier drops; D — bulk premium — did not.

This design adds a **`volume_premium(quantity, available) → float`** function in `engine/trading.py` and wires it into the buy-cargo handler so that large orders pay a per-ton premium proportional to the fraction of available supply they consume. Curve: quadratic, capped at +50% when an order buys out the planet's stock.

The premium is applied to the base asking price **before** the Bargain check, so a high-Bargain trader can shave the inflated price down — but not erase it. Bargain matters more in bulk because the underlying spread is bigger.

The premium applies to **buying only**. Selling is unchanged for now (a sell-side equivalent is a discrete future increment, not in this design).

---

## 2. Design Rationale

### 2.1 Why bulk impact is realistic

Real commodity markets have measurable price impact above ~1% of daily volume. EVE Online's market simulation, SWG's resource markets, and Torn's bazaar all model some form of order-size impact. The audit's §3.2.D framing ("Buying 1 ton gets posted price, buying 50 tons increases the effective price per unit (bulk premium). This is how commodity markets work — large orders move the price.") is the standard industry model.

### 2.2 Why scale against supply, not against absolute quantity

The audit's "50 tons" reference predates the supply pool work that landed as part of audit items A and B. Current supply caps per good per 45-minute refresh cycle:

| Good            | Cap / refresh | Carryover ceiling |
|-----------------|---------------|-------------------|
| Luxury goods    | 10            | 20                |
| Spice (legal)   | 10            | 20                |
| Weapons         | 10            | 20                |
| Manufactured    | 15 (default)  | 30                |
| Raw ore         | 25            | 50                |
| Medical         | 20            | 40                |
| Foodstuffs      | 30            | 60                |

Most goods cap below the audit's 50-ton reference. Scaling against an absolute "50t" threshold would apply zero premium to 99% of legal orders. **Scaling against fraction-of-supply** is the right primitive: it self-tunes to whatever the supply numbers are, scales correctly when supply caps change in future tuning, and matches the underlying economic intuition (consuming half the market moves the price more than consuming a tenth, regardless of absolute magnitude).

### 2.3 Why quadratic, not linear or logarithmic

- **Linear** is too punitive at small fractions. Buying 10% of supply shouldn't cost 5% more — it should cost almost nothing more.
- **Logarithmic** is too gentle at large fractions. Buying 90% of supply should hurt; log curves don't bite at the top.
- **Quadratic** gives the right shape: invisible below ~25% of supply (under 3% premium), noticeable around 50% (12.5%), and bites hard at the top end (50% at 100%).

### 2.4 Why 1.5x is the right ceiling

Bargain caps modifier swings at ±10%. A premium ceiling of +50% means a maxed-out bargain trader can bring a full-stock buyout from 1.5x → 1.35x. Lower ceilings (e.g., 1.25x) get fully erased by a great Bargain roll — which makes the mechanic feel pointless. Higher ceilings (e.g., 2.0x) feel arbitrary and overshadow the underlying tier multipliers (SOURCE 0.5x, NORMAL 1.0x, DEMAND 2.0x).

50% pairs cleanly with the existing tier system without distorting it.

---

## 3. Specification

### 3.1 New constant and function

Add to `engine/trading.py`, immediately after `get_planet_tier()`:

```python
VOLUME_PREMIUM_MAX_PCT = 0.50  # multiplier cap is 1.0 + this


def volume_premium(quantity: int, available: int) -> float:
    """Return the per-ton price multiplier for a bulk purchase.

    Args:
        quantity:  Tons being purchased. Values <= 0 yield 1.0.
        available: Tons currently in the planet's supply pool. Values
                   <= 0 yield 1.0 (no pool → no premium model applies,
                   e.g. legacy off-planet calls or test paths).

    Returns:
        Multiplier in [1.0, 1.0 + VOLUME_PREMIUM_MAX_PCT]. Apply as
        `effective_base = base_price * volume_premium(qty, avail)`.
    """
    if quantity <= 0 or available <= 0:
        return 1.0
    fraction = min(1.0, quantity / available)
    return 1.0 + VOLUME_PREMIUM_MAX_PCT * (fraction ** 2)
```

### 3.2 Calibration table

| Order vs. supply | Fraction | Multiplier | Premium % | Visible? |
|---|---|---|---|---|
| 1t / 50t | 0.02 | 1.0002 | 0.02% | No (under 5% surface threshold) |
| 5t / 30t | 0.17 | 1.014 | 1.4% | No |
| 10t / 30t | 0.33 | 1.056 | 5.6% | **Yes** |
| 15t / 30t | 0.50 | 1.125 | 12.5% | Yes |
| 20t / 30t | 0.67 | 1.222 | 22.2% | Yes |
| 25t / 30t | 0.83 | 1.347 | 34.7% | Yes |
| 30t / 30t | 1.00 | 1.500 | 50.0% | Yes |
| 50t / 30t (capped) | 1.00 | 1.500 | 50.0% | Yes |

### 3.3 Integration in `_handle_buy_cargo`

Located in `parser/space_commands.py:5184`. Three changes:

**Change 1 — Imports.** Add `volume_premium` to the trading-module import:

```python
from engine.trading import (
    TRADE_GOODS, get_planet_price, get_ship_cargo,
    cargo_free, add_cargo, SUPPLY_POOL, volume_premium,
)
```

**Change 2 — Hoist `avail`.** The current code defines `avail` inside `if planet:` so it isn't visible to the premium calculation. Lift it to outer scope:

```python
# Supply pool cap (review fix v1) — prevents the unlimited-trade
# exploit that let a YT-1300 loop generate ~240,000 cr/hr.
avail = 0
if planet:
    avail = SUPPLY_POOL.available(planet, good.key)
    # ... existing cleared-out / overage messages unchanged ...
```

**Change 3 — Apply premium between supply check and Bargain.** Insert immediately before the `resolve_bargain_check` call:

```python
# Bulk-premium pricing (audit §3.2.D) — large orders move the price.
# Quadratic in (qty / available); 0% at 1 ton, up to +50% buying out
# the planet's stock. Applied BEFORE bargain so a high-Bargain trader
# can shave the inflated asking price down.
premium = volume_premium(quantity, avail)
effective_base = max(1, int(round(base_price * premium)))

# Bargain check
char = ctx.session.character
haggle = resolve_bargain_check(
    char, effective_base * quantity,    # <-- was: base_price * quantity
    npc_bargain_dice=3, npc_bargain_pips=0,
    is_buying=True,
)
total_price = haggle["adjusted_price"]
per_ton = max(1, total_price // quantity)

# Surface the bulk premium when it would be visible to the player
# (>=5% — below that it's effectively rounding noise).
if premium >= 1.05:
    premium_pct = int(round((premium - 1.0) * 100))
    await ctx.session.send_line(
        f"  {ansi.DIM}Bulk premium: +{premium_pct}% "
        f"(buying {quantity}t of {avail}t available){ansi.RESET}"
    )
```

The existing Bargain narration line is unchanged. From the player's perspective they see two dim lines: `Bulk premium: +N% (buying Xt of Yt available)` and the existing `Bargain: M% bonus/penalty`. They can read the additive arithmetic.

### 3.4 Sell-side: explicitly out of scope

The audit §3.2.D specifies buying only. A symmetric "you flood the market when selling 100 tons" is realistic, but:

- It would require a sell-side supply concept the supply pool doesn't model (sell pool is currently absent — sells go straight to the destination planet without inventory consequence).
- It doubles the design surface for marginal additional realism.
- The asymmetry (premium on buy, not on sell) actually matches real markets where buyers chasing scarce supply move price more than sellers dumping into deep demand.

If desired later, the sell-side premium would slot into `_handle_sell_cargo` in `parser/builtin_commands.py:2479` with a separate `volume_discount(quantity, market_appetite)` function and its own design pass.

---

## 4. Test Plan

Target: **14 tests** in `tests/test_volume_premium.py`. Two categories:

### 4.1 Pure function tests (8 tests, no harness needed)

```python
from engine.trading import volume_premium, VOLUME_PREMIUM_MAX_PCT


def test_volume_premium_zero_quantity_returns_one():
    assert volume_premium(0, 30) == 1.0

def test_volume_premium_zero_available_returns_one():
    assert volume_premium(10, 0) == 1.0

def test_volume_premium_negative_inputs_return_one():
    assert volume_premium(-5, 30) == 1.0
    assert volume_premium(10, -30) == 1.0

def test_volume_premium_tiny_fraction_near_one():
    # 1t out of 50t supply: ~0.02% premium
    assert 1.0 < volume_premium(1, 50) < 1.001

def test_volume_premium_half_supply_is_quarter_max():
    # fraction 0.5 -> 0.25 of max premium -> 1.125x
    result = volume_premium(15, 30)
    assert abs(result - 1.125) < 0.001

def test_volume_premium_full_supply_hits_cap():
    assert abs(volume_premium(30, 30) - 1.5) < 0.001

def test_volume_premium_overage_clamped_at_cap():
    # quantity > available: still capped at 1.5
    assert abs(volume_premium(100, 30) - 1.5) < 0.001

def test_volume_premium_monotonically_increasing():
    prev = 1.0
    for q in range(1, 31):
        cur = volume_premium(q, 30)
        assert cur >= prev
        prev = cur
```

### 4.2 Integration tests (6 tests, harness needed)

Pattern after `tests/test_economy.py` `TestShops` class. Each uses `harness.login_as` with a docked ship, sufficient credits, and a known-quantity supply pool.

```python
class TestBulkPremiumIntegration:
    async def test_small_buy_no_premium_message(self, harness):
        """Buying 1 ton: no 'Bulk premium' line in output."""

    async def test_large_buy_shows_premium_message(self, harness):
        """Buying >=10t/30t supply: output includes 'Bulk premium: +N%'."""

    async def test_full_supply_buy_pays_50pct_premium_before_bargain(self, harness):
        """Buy out all supply: total price reflects +50% before bargain ±10%."""

    async def test_premium_uses_inflated_credits_check(self, harness):
        """Player with credits between base and premium price gets 'not enough'."""

    async def test_offplanet_no_supply_means_no_premium(self, harness):
        """Edge case: no zone/planet → premium=1.0, posted price applies."""

    async def test_premium_does_not_apply_to_sell_cargo(self, harness):
        """Selling 30 tons: revenue uses bargain only, no premium-style discount."""
```

Total: **14 tests** matching the user-memory target count.

---

## 5. Acceptance Criteria

The implementation is complete when:

1. ✅ `engine/trading.py` exports `volume_premium` and `VOLUME_PREMIUM_MAX_PCT` (verifiable by `grep -n 'def volume_premium\|VOLUME_PREMIUM_MAX_PCT' engine/trading.py`).
2. ✅ `_handle_buy_cargo` calls `volume_premium(quantity, avail)` and feeds the result into `resolve_bargain_check` via `effective_base * quantity` (not `base_price * quantity`).
3. ✅ Buying 100% of supply pool produces a price that is ~1.35–1.65× base price after bargain (1.5× before, ±10% bargain swing).
4. ✅ Buying 1t of any good produces price within ±15% of `base_price` (bargain swing only; premium negligible).
5. ✅ When premium ≥ 5% the player sees a `Bulk premium: +N%` UI line.
6. ✅ All 14 tests in `tests/test_volume_premium.py` pass.
7. ✅ No regression in existing `tests/test_economy.py` (especially `TestTradeGoods` and any cargo tests).
8. ✅ AST-validates: `python -c "import ast; ast.parse(open('engine/trading.py').read())"` and same for `parser/space_commands.py`.

---

## 6. Architecture Doc Integration

When v32 rolls up:

**§3 Economy** — Add a paragraph under the existing trade-goods discussion documenting that bulk premium pricing closes audit §3.2.D. Reference `volume_premium` as the primary symbol.

**§25 Design Documents Reference** — Add a row:

| Document | Status | Contents |
|---|---|---|
| `economy_bulk_premium_design_v1.md` | ✅ Delivered | Order-impact pricing curve; quadratic, +50% cap. Closes economy audit §3.2.D. |

**§19 Priority list** — No change. This was scoped as a small in-flight item, not a roadmap priority.

**Memory edits** — User-memory edit #3 (the "P3 NEVER landed" note) should be replaced with: *"P3 bulk-premium pricing (audit §3.2.D) implemented April 2026 — `volume_premium()` in `engine/trading.py`, wired into `_handle_buy_cargo`. Quadratic curve, +50% cap at 100% of supply, applied before Bargain check. 14 passing tests in `tests/test_volume_premium.py`."*

---

*End of Bulk Premium Pricing Design — Version 1.0*
