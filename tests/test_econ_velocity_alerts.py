"""Economy audit #17 / R1 — proactive credit-velocity alerts.

Covers the pure band evaluator (engine.economy_alerts) — including the
*deflation* direction that economy_audit_v2 flagged as a blind spot — the
recent-alert ring buffer, and structural pins that the hourly tick is wired
(handler present, registered in GameServer) and surfaced (`@economy alerts`).

The tick handler itself does live DB/session I/O against the aiohttp server
stack, so it's verified by source-structure here and by the full suite on the
dev box; the band logic that decides whether to page is fully unit-tested.
"""

import unittest
from pathlib import Path

from engine.economy_alerts import (
    evaluate_velocity_alert, format_alert_line,
    record_alert, recent_alerts, clear_alerts,
    VELOCITY_CAUTION_NET_1H, VELOCITY_CRITICAL_NET_1H,
)


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "server" / "game_server.py").exists():
            return parent
    raise RuntimeError("could not locate repo root from test file")


ROOT = _find_root()


def _v(net, **extra):
    """Build a minimal velocity dict with a given net."""
    d = {"net": net, "faucet_total": max(net, 0), "sink_total": min(net, 0),
         "txn_count": 1, "top_faucets": [], "top_sinks": []}
    d.update(extra)
    return d


class TestVelocityBands(unittest.TestCase):
    def test_below_caution_is_no_alert(self):
        self.assertIsNone(evaluate_velocity_alert(_v(VELOCITY_CAUTION_NET_1H - 1)))
        self.assertIsNone(evaluate_velocity_alert(_v(-(VELOCITY_CAUTION_NET_1H - 1))))

    def test_caution_inflation(self):
        a = evaluate_velocity_alert(_v(VELOCITY_CAUTION_NET_1H))
        self.assertIsNotNone(a)
        self.assertEqual(a["severity"], "caution")
        self.assertEqual(a["direction"], "inflation")

    def test_critical_inflation(self):
        a = evaluate_velocity_alert(_v(VELOCITY_CRITICAL_NET_1H + 10_000))
        self.assertEqual(a["severity"], "critical")
        self.assertEqual(a["direction"], "inflation")

    def test_caution_deflation(self):
        # The economy_audit_v2 blind spot: a net-negative (contracting) economy
        # must trip an alert, not pass silently.
        a = evaluate_velocity_alert(_v(-VELOCITY_CAUTION_NET_1H))
        self.assertIsNotNone(a)
        self.assertEqual(a["severity"], "caution")
        self.assertEqual(a["direction"], "deflation")

    def test_critical_deflation(self):
        a = evaluate_velocity_alert(_v(-(VELOCITY_CRITICAL_NET_1H + 5_000)))
        self.assertEqual(a["severity"], "critical")
        self.assertEqual(a["direction"], "deflation")

    def test_custom_thresholds_respected(self):
        a = evaluate_velocity_alert(_v(1_000), caution=500, critical=2_000)
        self.assertEqual(a["severity"], "caution")
        b = evaluate_velocity_alert(_v(3_000), caution=500, critical=2_000)
        self.assertEqual(b["severity"], "critical")

    def test_24h_context_and_drivers_carried(self):
        a = evaluate_velocity_alert(
            _v(VELOCITY_CRITICAL_NET_1H + 1, top_faucets=[("mission_reward", 120_000)]),
            _v(800_000),
        )
        self.assertEqual(a["net_24h"], 800_000)
        self.assertEqual(a["drivers"], [("mission_reward", 120_000)])

    def test_deflation_uses_sink_drivers(self):
        a = evaluate_velocity_alert(
            _v(-(VELOCITY_CAUTION_NET_1H + 1), top_sinks=[("crew_wages", -90_000)]))
        self.assertEqual(a["drivers"], [("crew_wages", -90_000)])


class TestMalformedInput(unittest.TestCase):
    def test_non_dict_is_none(self):
        self.assertIsNone(evaluate_velocity_alert("nope"))
        self.assertIsNone(evaluate_velocity_alert(None))

    def test_bad_net_is_none(self):
        self.assertIsNone(evaluate_velocity_alert({"net": "x"}))

    def test_empty_dict_is_none(self):
        self.assertIsNone(evaluate_velocity_alert({}))


class TestRingBuffer(unittest.TestCase):
    def setUp(self):
        clear_alerts()

    def test_record_and_recent_newest_first(self):
        a = evaluate_velocity_alert(_v(VELOCITY_CRITICAL_NET_1H + 1))
        b = evaluate_velocity_alert(_v(-(VELOCITY_CAUTION_NET_1H + 1)))
        record_alert(a)
        record_alert(b)
        got = recent_alerts()
        self.assertEqual([x["direction"] for x in got], ["deflation", "inflation"])

    def test_clear(self):
        record_alert(evaluate_velocity_alert(_v(VELOCITY_CRITICAL_NET_1H + 1)))
        clear_alerts()
        self.assertEqual(recent_alerts(), [])

    def test_cap_enforced(self):
        from engine.economy_alerts import _ALERT_BUFFER_MAX
        for i in range(_ALERT_BUFFER_MAX + 25):
            record_alert({"ts": i, "severity": "caution", "direction": "inflation",
                          "net_1h": 60_000})
        self.assertLessEqual(len(recent_alerts(10_000)), _ALERT_BUFFER_MAX)

    def test_recent_limit_zero(self):
        record_alert(evaluate_velocity_alert(_v(VELOCITY_CRITICAL_NET_1H + 1)))
        self.assertEqual(recent_alerts(0), [])


class TestFormatLine(unittest.TestCase):
    def test_line_has_severity_direction_net(self):
        a = evaluate_velocity_alert(_v(VELOCITY_CRITICAL_NET_1H + 1))
        line = format_alert_line(a)
        self.assertIn("CRITICAL", line)
        self.assertIn("inflation", line)
        self.assertIn("cr/hr", line)


class TestStructuralWiring(unittest.TestCase):
    def test_tick_handler_defined(self):
        src = (ROOT / "server" / "tick_handlers_economy.py").read_text(encoding="utf-8")
        self.assertIn("async def credit_velocity_alert_tick(", src)
        self.assertIn("get_credit_velocity(3600)", src)
        self.assertIn("evaluate_velocity_alert", src)

    def test_tick_registered_in_game_server(self):
        src = (ROOT / "server" / "game_server.py").read_text(encoding="utf-8")
        self.assertIn("credit_velocity_alert_tick", src,
                      "tick must be imported in game_server")
        self.assertIn('register("credit_velocity_alert"', src,
                      "tick must be registered with the scheduler")

    def test_readout_surfaces_recent_alerts(self):
        src = (ROOT / "parser" / "director_commands.py").read_text(encoding="utf-8")
        self.assertIn("recent_alerts", src,
                      "@economy alerts must surface the recent-alert buffer")


if __name__ == "__main__":
    unittest.main(verbosity=2)
