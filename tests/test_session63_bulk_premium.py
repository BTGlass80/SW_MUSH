# -*- coding: utf-8 -*-
"""
tests/test_session63_bulk_premium.py — P3 §3.2.D Bulk-Purchase Premium

Closes economy_audit_v1.md §3.2.D ("Volume price scaling. Buying 1 ton
gets posted price. Buying 50 tons increases the effective price per
unit (bulk premium).").

Tests the pure function `engine.trading.volume_premium()` plus the
integration math used by `parser/space_commands.py::_handle_buy_cargo`.

We deliberately do NOT exercise the full `_handle_buy_cargo` flow via
the harness — that would require ship setup, docked planet, supply
pool seeding, and Bargain skill mocking. The pure-function contract
plus the pricing math integration tests cover the behavior; the
existing harness tests for the buy-cargo command will catch any
regression in the surrounding flow.
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. volume_premium() pure-function tests
# ══════════════════════════════════════════════════════════════════════════════

class TestVolumePremiumPureFunction(unittest.TestCase):
    """Verify the linear ramp from 20% supply usage to 100% supply usage."""

    def test_floor_no_premium_at_or_below_20pct(self):
        """Orders consuming ≤20% of supply pay no premium."""
        from engine.trading import volume_premium
        # 1 of 50 = 2%
        self.assertEqual(volume_premium(1, 50), 0.0)
        # 5 of 50 = 10%
        self.assertEqual(volume_premium(5, 50), 0.0)
        # 10 of 50 = 20% (floor edge — still no premium)
        self.assertEqual(volume_premium(10, 50), 0.0)

    def test_ceiling_max_premium_at_or_above_100pct(self):
        """Orders consuming ≥100% of supply pay the max premium (+40%)."""
        from engine.trading import volume_premium, VOLUME_PREMIUM_MAX
        self.assertEqual(volume_premium(50, 50), VOLUME_PREMIUM_MAX)
        # Over-clamped (caller's supply check should reject this — defense
        # in depth: the function never returns >MAX no matter the input).
        self.assertEqual(volume_premium(100, 50), VOLUME_PREMIUM_MAX)
        self.assertEqual(volume_premium(10000, 50), VOLUME_PREMIUM_MAX)

    def test_midpoint_50pct_supply_usage(self):
        """50% supply usage = midway through the ramp = 15% premium."""
        from engine.trading import volume_premium
        # fraction = 0.50; ramp = 0.40 * (0.50 - 0.20) / 0.80 = 0.15
        self.assertAlmostEqual(volume_premium(25, 50), 0.15, places=6)

    def test_ramp_is_linear(self):
        """Premium scales linearly between 20% and 100% supply usage."""
        from engine.trading import volume_premium
        # Sample points along the ramp; verify linearity.
        # fraction = 0.40 → premium = 0.40 * (0.40-0.20)/0.80 = 0.10
        # fraction = 0.60 → premium = 0.40 * (0.60-0.20)/0.80 = 0.20
        # fraction = 0.80 → premium = 0.40 * (0.80-0.20)/0.80 = 0.30
        self.assertAlmostEqual(volume_premium(20, 50), 0.10, places=6)
        self.assertAlmostEqual(volume_premium(30, 50), 0.20, places=6)
        self.assertAlmostEqual(volume_premium(40, 50), 0.30, places=6)

    def test_just_over_floor_smallest_premium(self):
        """Order at 21% of supply gets a tiny but non-zero premium."""
        from engine.trading import volume_premium
        # fraction = 0.21 → premium = 0.40 * 0.01 / 0.80 = 0.005
        result = volume_premium(21, 100)
        self.assertGreater(result, 0.0)
        self.assertLess(result, 0.01)

    def test_zero_quantity_no_premium(self):
        """Zero or negative quantity returns 0 (defensive)."""
        from engine.trading import volume_premium
        self.assertEqual(volume_premium(0, 50), 0.0)
        self.assertEqual(volume_premium(-5, 50), 0.0)

    def test_zero_supply_no_premium(self):
        """Empty market returns 0 (caller should have rejected the order)."""
        from engine.trading import volume_premium
        self.assertEqual(volume_premium(10, 0), 0.0)
        self.assertEqual(volume_premium(10, -1), 0.0)

    def test_return_type_is_float(self):
        """Premium must be a float so per-ton math doesn't truncate to 0."""
        from engine.trading import volume_premium
        self.assertIsInstance(volume_premium(25, 50), float)
        self.assertIsInstance(volume_premium(10, 50), float)  # floor case
        self.assertIsInstance(volume_premium(50, 50), float)  # ceiling case

    def test_premium_never_exceeds_max(self):
        """Invariant: the function never returns > VOLUME_PREMIUM_MAX."""
        from engine.trading import volume_premium, VOLUME_PREMIUM_MAX
        # Sweep a wide range of (q, s) inputs and assert the bound holds.
        for q in (1, 5, 10, 25, 50, 100, 500, 1000):
            for s in (1, 5, 10, 25, 50, 100):
                p = volume_premium(q, s)
                self.assertLessEqual(p, VOLUME_PREMIUM_MAX,
                    f"q={q} s={s} premium={p} exceeds MAX")
                self.assertGreaterEqual(p, 0.0,
                    f"q={q} s={s} premium={p} is negative")


# ══════════════════════════════════════════════════════════════════════════════
# 2. Module-level constants
# ══════════════════════════════════════════════════════════════════════════════

class TestVolumePremiumConstants(unittest.TestCase):
    """The three module constants form the pricing contract; lock them."""

    def test_floor_pct_is_20(self):
        """Below 20% supply usage, premium is zero."""
        from engine.trading import VOLUME_PREMIUM_FLOOR_PCT
        self.assertEqual(VOLUME_PREMIUM_FLOOR_PCT, 0.20)

    def test_ceil_pct_is_100(self):
        """At 100% supply usage, premium reaches its max."""
        from engine.trading import VOLUME_PREMIUM_CEIL_PCT
        self.assertEqual(VOLUME_PREMIUM_CEIL_PCT, 1.00)

    def test_max_premium_is_40_pct(self):
        """Maximum bulk premium is +40% per ton."""
        from engine.trading import VOLUME_PREMIUM_MAX
        self.assertEqual(VOLUME_PREMIUM_MAX, 0.40)


# ══════════════════════════════════════════════════════════════════════════════
# 3. Pricing math integration — what _handle_buy_cargo computes
# ══════════════════════════════════════════════════════════════════════════════

class TestPricingMathIntegration(unittest.TestCase):
    """
    Verify the per-ton pricing math used in _handle_buy_cargo.

    The formula is:
        premium_pct       = volume_premium(quantity, avail) if planet else 0.0
        effective_per_ton = max(1, round(base_price * (1.0 + premium_pct)))

    This block is sandboxed here so any future change to the pricing
    formula has to also update these tests.
    """

    @staticmethod
    def _effective_per_ton(base_price: int, quantity: int,
                           supply_available: int) -> int:
        """Mirror of _handle_buy_cargo's pricing math."""
        from engine.trading import volume_premium
        premium_pct = volume_premium(quantity, supply_available)
        return max(1, int(round(base_price * (1.0 + premium_pct))))

    def test_small_order_gets_posted_price(self):
        """5t order on 50t supply (10%): posted price applies."""
        # raw_ore at Tatooine source = 50 cr/t (live constants)
        per_ton = self._effective_per_ton(base_price=50, quantity=5,
                                           supply_available=50)
        self.assertEqual(per_ton, 50)

    def test_floor_edge_order_no_premium(self):
        """10t order on 50t supply (20% — floor edge): posted price."""
        per_ton = self._effective_per_ton(base_price=100, quantity=10,
                                           supply_available=50)
        self.assertEqual(per_ton, 100)

    def test_midpoint_order_15pct_premium(self):
        """25t on 50t (50%): +15% premium → 100 cr/t becomes 115 cr/t."""
        per_ton = self._effective_per_ton(base_price=100, quantity=25,
                                           supply_available=50)
        self.assertEqual(per_ton, 115)

    def test_full_supply_order_max_premium(self):
        """50t on 50t (100%): +40% premium → 100 cr/t becomes 140 cr/t."""
        per_ton = self._effective_per_ton(base_price=100, quantity=50,
                                           supply_available=50)
        self.assertEqual(per_ton, 140)

    def test_premium_floored_at_1cr_per_ton(self):
        """Edge case: tiny base price doesn't round to zero."""
        # base=1 cr/t with no premium would yield 1; with max premium 1.4 → 1.
        # The max(1, ...) guard ensures we never sell at 0 cr/ton.
        per_ton_no_premium = self._effective_per_ton(1, 5, 50)
        per_ton_full_premium = self._effective_per_ton(1, 50, 50)
        self.assertGreaterEqual(per_ton_no_premium, 1)
        self.assertGreaterEqual(per_ton_full_premium, 1)

    def test_total_price_computation(self):
        """Total price = effective_per_ton * quantity (before bargain)."""
        # luxury_goods at Corellia source = 200 cr/t (400 base * 0.50)
        # Order 30t of 50t available → fraction 0.60 → premium = 0.20
        # effective = 200 * 1.20 = 240 cr/t
        # total = 240 * 30 = 7,200 cr (before bargain)
        per_ton = self._effective_per_ton(base_price=200, quantity=30,
                                           supply_available=50)
        self.assertEqual(per_ton, 240)
        self.assertEqual(per_ton * 30, 7200)


# ══════════════════════════════════════════════════════════════════════════════
# 4. Wire-in regression — _handle_buy_cargo imports volume_premium
# ══════════════════════════════════════════════════════════════════════════════

class TestWireInRegression(unittest.TestCase):
    """
    Catch the regression where the function exists in `engine.trading` but
    `_handle_buy_cargo` forgot to import it. Without this test, a future
    refactor that drops the import line would silently revert the fix.
    """

    def test_handle_buy_cargo_imports_volume_premium(self):
        """The handler must import volume_premium from engine.trading."""
        import inspect
        from parser import space_commands
        src = inspect.getsource(space_commands._handle_buy_cargo)
        self.assertIn("volume_premium", src,
            "_handle_buy_cargo must import volume_premium from engine.trading")

    def test_handle_buy_cargo_applies_premium_to_per_ton_price(self):
        """The handler must use effective_per_ton in the bargain call."""
        import inspect
        from parser import space_commands
        src = inspect.getsource(space_commands._handle_buy_cargo)
        # The premium must be applied BEFORE the bargain check, not after.
        # This regression test guards against a future refactor that calls
        # bargain on raw base_price * quantity.
        self.assertIn("effective_per_ton", src,
            "_handle_buy_cargo must compute effective_per_ton with premium")
        self.assertIn("effective_per_ton * quantity", src,
            "Bargain check must operate on effective_per_ton * quantity, "
            "not base_price * quantity")


if __name__ == "__main__":
    unittest.main()
