"""ECON.p2p_cap_removal_impl — decision a, 2026-06-11 (same-day drop 5).

The S51/audit-v2 hard P2P cap (1,500 cr per rolling 24h per sender) is
REMOVED by explicit sign-off (reverses audit v2 §2.4): under vendor
segmentation (a), crafters are the supply chain and a single quality
item legitimately trades above the old cap. What survives:

  • the 5% transaction tax (p2p_tax sink) and p2p_transfer ledger tag
  • the alt-account trade block ([TRADE BLOCKED], both item + credit paths)
  • the rolling-window read (get_daily_p2p_outgoing) — now feeding a
    FAIL-OPEN velocity alert (engine.economy_alerts) instead of a block:
    caution at the old 1,500, critical at 7,500. Telemetry must never
    disturb a trade.

Companion updates in the same drop: test_tier2_tuning_batch.TestP2PCap,
test_session51_economy_hardening.TestP2PDailyCapConstants, and the EE8
smoke scenario all pinned the reversed policy and were rewritten WITH
this change, not skipped.
"""
import inspect
import re
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _stripped(src: str) -> str:
    """Source with full-line comments removed, so pins can't match the
    explanatory comments that describe the OLD policy."""
    return "\n".join(ln for ln in src.splitlines()
                     if not ln.lstrip().startswith("#"))


class TestCapRemovedFromTradePath(unittest.TestCase):
    def setUp(self):
        self.src = (REPO / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8")
        self.code = _stripped(self.src)

    def test_no_cap_constant(self):
        import parser.builtin_commands as bc
        self.assertFalse(hasattr(bc, "P2P_DAILY_CAP"))
        self.assertNotIn("P2P_DAILY_CAP", self.code)

    def test_no_volume_block_remains(self):
        # No code path may refuse a trade on volume: the old blocks
        # compared against the cap and messaged "Daily transfer cap".
        self.assertNotIn("Daily transfer cap", self.code)
        self.assertNotIn("daily transfer cap", self.code.lower())

    def test_alt_block_survives(self):
        # The [TRADE BLOCKED] alt-account prohibition is a different
        # policy and stays — both the item path and the credit path.
        self.assertGreaterEqual(self.code.count("TRADE BLOCKED"), 2)
        self.assertIn("alternate characters", self.code)

    def test_tax_survives(self):
        # T3.19 externalized the tax rate as a tunable (p2p.tax_pct, default 5).
        # The expression amount*pct//100 with pct=5 is integer-identical to the
        # prior amount//20; the old literal no longer exists.
        self.assertIn("p2p.tax_pct", self.code)
        self.assertIn('tax = max(1, amount * tax_pct // 100)', self.code)
        self.assertIn('"p2p_tax"', self.code)
        self.assertIn('"p2p_transfer"', self.code)

    def test_alert_hook_present_and_fail_open(self):
        self.assertIn("evaluate_p2p_velocity_alert", self.code)
        self.assertIn("record_alert", self.code)
        # The hook sits inside a try with a swallow-and-log except —
        # locate the hook and confirm an except follows before any
        # further await on the session (fail-open posture).
        hook = self.code.index("evaluate_p2p_velocity_alert")
        tail = self.code[hook:hook + 1200]
        self.assertIn("except Exception", tail)

    def test_window_constant_survives(self):
        from parser.builtin_commands import P2P_DAILY_WINDOW_SECONDS
        self.assertEqual(P2P_DAILY_WINDOW_SECONDS, 86_400)


class TestVelocityEvaluator(unittest.TestCase):
    def _eval(self, total, amount=0):
        from engine.economy_alerts import evaluate_p2p_velocity_alert
        return evaluate_p2p_velocity_alert(
            "Alice", 7, "Bob", total, amount=amount)

    def test_below_threshold_is_none(self):
        self.assertIsNone(self._eval(1_499))
        self.assertIsNone(self._eval(0))

    def test_caution_band(self):
        a = self._eval(1_500, amount=600)
        self.assertIsNotNone(a)
        self.assertEqual(a["severity"], "caution")
        self.assertEqual(a["kind"], "p2p_velocity")
        self.assertEqual(a["sender"], "Alice")
        self.assertEqual(a["recipient"], "Bob")
        self.assertEqual(a["rolling_24h"], 1_500)
        self.assertEqual(a["amount"], 600)

    def test_critical_band(self):
        a = self._eval(7_500)
        self.assertEqual(a["severity"], "critical")

    def test_fails_safe_on_garbage(self):
        # Telemetry must never raise into the trade path.
        from engine.economy_alerts import evaluate_p2p_velocity_alert
        self.assertIsNone(evaluate_p2p_velocity_alert(
            "A", 1, "B", "not-a-number"))
        self.assertIsNone(evaluate_p2p_velocity_alert(
            None, None, None, None))

    def test_generic_readout_compatibility(self):
        # The @economy display reads severity/direction/net_1h with
        # .get defaults — the p2p dict must satisfy that shape.
        a = self._eval(2_000)
        for field in ("ts", "severity", "direction", "net_1h", "drivers"):
            self.assertIn(field, a)

    def test_format_line_p2p_branch(self):
        from engine.economy_alerts import format_alert_line
        line = format_alert_line(self._eval(2_000, amount=2_000))
        self.assertIn("p2p-volume", line)
        self.assertIn("Alice", line)
        self.assertIn("Bob", line)
        self.assertIn("2,000", line)

    def test_ring_buffer_round_trip(self):
        from engine.economy_alerts import (
            record_alert, recent_alerts, clear_alerts)
        clear_alerts()
        try:
            record_alert(self._eval(9_000))
            got = recent_alerts(5)
            self.assertEqual(len(got), 1)
            self.assertEqual(got[0]["kind"], "p2p_velocity")
            self.assertEqual(got[0]["severity"], "critical")
        finally:
            clear_alerts()


class TestReversedPinsUpdatedWithDrop(unittest.TestCase):
    """The three old-policy pin sites must carry the new policy — this
    guards against a future 'fix the test by restoring the cap'."""

    def test_tier2_pin_flipped(self):
        src = (REPO / "tests" / "test_tier2_tuning_batch.py").read_text(
            encoding="utf-8")
        self.assertIn("test_hard_cap_constant_removed", src)

    def test_s51_pin_flipped(self):
        src = (REPO / "tests" /
               "test_session51_economy_hardening.py").read_text(
            encoding="utf-8")
        self.assertIn("test_cap_constant_removed", src)

    def test_smoke_scenario_flipped(self):
        src = (REPO / "tests" / "smoke" / "scenarios" /
               "economy_extended.py").read_text(encoding="utf-8")
        self.assertIn("ee8_p2p_large_trade_flows_and_alerts", src)
        self.assertNotIn("ee8_p2p_cap_blocks_over_limit", src)


if __name__ == "__main__":
    unittest.main()
