# -*- coding: utf-8 -*-
"""tests/test_communal_objective_tunables.py — T3.19 config breadth for the
dark-side cult communal objective (engine/communal_objective.py +
engine/communal_objective_runtime.py).

The cult-uprising difficulty + prestige-reward levers — MENACE_START /
MENACE_PER_MINUTE / DEADLINE_HOURS / STRIKE_COOLDOWN_S (difficulty) and
REP_FLOOR / REP_MAX / TITLE_SHARE_THRESHOLD (reward) — were hardcoded module
constants: an operator could OBSERVE the cult economy via the ``@balance
communal`` board (menace-tick + tier-escalation count, strike count + success
rate) but could not TUNE it without a code edit + redeploy. The producer's own
emit-site comments already name MENACE_PER_MINUTE / DEADLINE_HOURS / strike
balance as the tuning targets — so the observe→tune loop was half-open exactly as
grind's / craft's / cp's were. This drop externalizes the seven to
data/tunables.yaml under ``communal.*`` and reads them at the USE SITE through
live accessors, closing that loop.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override takes effect through the real deciders
(advance_menace escalation, reward_rep_for_share, earns_title, the strike-
cooldown view), a fat-fingered negative clamps safe (a negative escalation can't
self-route the cult into a guaranteed win; a negative rep can't DEBIT a winner;
deadline_hours floors at 1 so an objective is never posted instantly-LOST), a
present-but-null / bad-typed key falls back to the default, the shipped
data/tunables.yaml carries the seven keys at their in-code defaults (a drift
pin), and the engine + runtime use sites read via the accessors (no import-time
freeze, no revert to the raw constant).

Run: python -m pytest tests/test_communal_objective_tunables.py
"""
from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import communal_objective as CO  # noqa: E402
from engine import communal_objective_runtime as CORT  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT

# The frozen legacy magnitudes — the behaviour-identical numbers this drop must
# reproduce when the YAML is absent (hard-coded here, NOT read from the module,
# so a constant edit can't silently move the goalposts).
LEGACY = {
    "menace_start": 35.0,
    "menace_per_minute": 0.35,
    "deadline_hours": 48,
    "strike_cooldown_s": 600,
    "rep_floor": 3,
    "rep_max": 15,
    "title_share_threshold": 0.10,
}


class TestCommunalTunableAccessors(unittest.TestCase):
    """The seven accessors: default / override / clamp / null / bad-value."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_equal_in_code_constants(self):
        self.assertEqual(CO.menace_start(), float(CO.MENACE_START))
        self.assertEqual(CO.menace_per_minute(), float(CO.MENACE_PER_MINUTE))
        self.assertEqual(CO.deadline_hours(), CO.DEADLINE_HOURS)
        self.assertEqual(CO.strike_cooldown_s(), CO.STRIKE_COOLDOWN_S)
        self.assertEqual(CO.rep_floor(), CO.REP_FLOOR)
        self.assertEqual(CO.rep_max(), CO.REP_MAX)
        self.assertEqual(CO.title_share_threshold(), CO.TITLE_SHARE_THRESHOLD)

    def test_defaults_match_frozen_legacy(self):
        # A second, independent pin against the literal launch values.
        self.assertEqual(CO.menace_start(), LEGACY["menace_start"])
        self.assertEqual(CO.menace_per_minute(), LEGACY["menace_per_minute"])
        self.assertEqual(CO.deadline_hours(), LEGACY["deadline_hours"])
        self.assertEqual(CO.strike_cooldown_s(), LEGACY["strike_cooldown_s"])
        self.assertEqual(CO.rep_floor(), LEGACY["rep_floor"])
        self.assertEqual(CO.rep_max(), LEGACY["rep_max"])
        self.assertEqual(CO.title_share_threshold(), LEGACY["title_share_threshold"])

    def test_overrides_take_effect(self):
        tunables._TUNABLES.update({
            "communal.menace_start": 50,
            "communal.menace_per_minute": 0.8,
            "communal.deadline_hours": 72,
            "communal.strike_cooldown_s": 300,
            "communal.rep_floor": 5,
            "communal.rep_max": 25,
            "communal.title_share_threshold": 0.2,
        })
        self.assertEqual(CO.menace_start(), 50.0)
        self.assertEqual(CO.menace_per_minute(), 0.8)
        self.assertEqual(CO.deadline_hours(), 72)
        self.assertEqual(CO.strike_cooldown_s(), 300)
        self.assertEqual(CO.rep_floor(), 5)
        self.assertEqual(CO.rep_max(), 25)
        self.assertEqual(CO.title_share_threshold(), 0.2)

    def test_negative_magnitudes_clamp_to_zero(self):
        tunables._TUNABLES.update({
            "communal.menace_start": -10,
            "communal.menace_per_minute": -0.5,
            "communal.strike_cooldown_s": -100,
            "communal.rep_floor": -5,
            "communal.rep_max": -9,
            "communal.title_share_threshold": -0.3,
        })
        self.assertEqual(CO.menace_start(), 0.0)
        self.assertEqual(CO.menace_per_minute(), 0.0)
        self.assertEqual(CO.strike_cooldown_s(), 0)
        self.assertEqual(CO.rep_floor(), 0)
        self.assertEqual(CO.rep_max(), 0)
        self.assertEqual(CO.title_share_threshold(), 0.0)

    def test_deadline_hours_floors_at_one_not_zero(self):
        # deadline_hours is the win-window — a 0/negative window would post every
        # objective already past its deadline (instantly LOST = unwinnable), so
        # it floors at 1 rather than 0 (the analog of cp.ticks_per_cp's divisor
        # floor). The other magnitudes floor at 0.
        for bad in (0, -1, -48):
            tunables._TUNABLES["communal.deadline_hours"] = bad
            self.assertEqual(CO.deadline_hours(), 1)

    def test_present_but_null_falls_back(self):
        for key in (
            "communal.menace_start", "communal.menace_per_minute",
            "communal.deadline_hours", "communal.strike_cooldown_s",
            "communal.rep_floor", "communal.rep_max",
            "communal.title_share_threshold",
        ):
            tunables._TUNABLES[key] = None
        self.assertEqual(CO.menace_start(), float(CO.MENACE_START))
        self.assertEqual(CO.menace_per_minute(), float(CO.MENACE_PER_MINUTE))
        self.assertEqual(CO.deadline_hours(), CO.DEADLINE_HOURS)
        self.assertEqual(CO.strike_cooldown_s(), CO.STRIKE_COOLDOWN_S)
        self.assertEqual(CO.rep_floor(), CO.REP_FLOOR)
        self.assertEqual(CO.rep_max(), CO.REP_MAX)
        self.assertEqual(CO.title_share_threshold(), CO.TITLE_SHARE_THRESHOLD)

    def test_bad_typed_value_falls_back(self):
        tunables._TUNABLES.update({
            "communal.menace_per_minute": "fast",
            "communal.deadline_hours": "soon",
            "communal.rep_max": "lots",
            "communal.title_share_threshold": "most",
        })
        self.assertEqual(CO.menace_per_minute(), float(CO.MENACE_PER_MINUTE))
        self.assertEqual(CO.deadline_hours(), CO.DEADLINE_HOURS)
        self.assertEqual(CO.rep_max(), CO.REP_MAX)
        self.assertEqual(CO.title_share_threshold(), CO.TITLE_SHARE_THRESHOLD)

    def test_numeric_coercion(self):
        # float lever fed an int -> float; int lever fed a float -> truncated int.
        tunables._TUNABLES["communal.menace_per_minute"] = 1   # int
        tunables._TUNABLES["communal.deadline_hours"] = 36.9    # float
        tunables._TUNABLES["communal.strike_cooldown_s"] = 90.5
        self.assertEqual(CO.menace_per_minute(), 1.0)
        self.assertEqual(CO.deadline_hours(), 36)
        self.assertEqual(CO.strike_cooldown_s(), 90)


class TestCommunalTunableEndToEnd(unittest.TestCase):
    """An override flows through the REAL deciders, not just the accessors."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_escalation_uses_menace_per_minute(self):
        # advance_menace escalates by menace_per_minute() per minute.
        base = CO.advance_menace(20.0, 10.0)        # 20 + 0.35*10 = 23.5
        self.assertAlmostEqual(base, 23.5)
        tunables._TUNABLES["communal.menace_per_minute"] = 1.0
        hot = CO.advance_menace(20.0, 10.0)         # 20 + 1.0*10 = 30
        self.assertAlmostEqual(hot, 30.0)

    def test_negative_escalation_cannot_self_route(self):
        # A negative escalation clamps to 0, so menace never DROPS on its own
        # (which would invert the objective into a guaranteed community win).
        tunables._TUNABLES["communal.menace_per_minute"] = -2.0
        self.assertEqual(CO.advance_menace(50.0, 60.0), 50.0)

    def test_reward_uses_rep_floor_and_max(self):
        # Largest contributor (full share) earns rep_max; raising both lifts it.
        self.assertEqual(CO.reward_rep_for_share(10, 10, True), 15)
        tunables._TUNABLES.update({
            "communal.rep_floor": 10, "communal.rep_max": 40})
        self.assertEqual(CO.reward_rep_for_share(10, 10, True), 40)   # full share -> max
        self.assertEqual(CO.reward_rep_for_share(0, 10, True), 0)     # no effort -> nothing

    def test_negative_rep_never_debits_a_winner(self):
        # Opportunities-never-penalties: a negative rep lever clamps to 0, so a
        # community WIN can never pay a NEGATIVE (a rep debit) to a contributor.
        tunables._TUNABLES.update({
            "communal.rep_floor": -100, "communal.rep_max": -100})
        for pts in (1, 5, 10):
            self.assertGreaterEqual(CO.reward_rep_for_share(pts, 10, True), 0)

    def test_title_eligibility_uses_threshold(self):
        # 0.2 share qualifies at the 0.10 default; raise the bar past it -> no.
        self.assertTrue(CO.earns_title(2, 10, True))
        tunables._TUNABLES["communal.title_share_threshold"] = 0.5
        self.assertFalse(CO.earns_title(2, 10, True))
        tunables._TUNABLES["communal.title_share_threshold"] = 0.05
        self.assertTrue(CO.earns_title(1, 15, True))   # 0.066 share clears 0.05

    def test_strike_cooldown_view_uses_lever(self):
        # The rally board's "Next strike" line reads strike_cooldown_s(): a
        # contributor who struck 60s ago is on cooldown at the 600s default but
        # ready once the cooldown is dropped below 60s.
        now = 1_000_000_000
        contribs = {"7": {"points": 4, "last_strike_at": now - 60_000}}
        on_cd = CO.viewer_contribution_line(contribs, 7, now)
        self.assertNotIn("Next strike: ready", _strip(on_cd))  # still cooling at 600s
        self.assertIn("~9m", _strip(on_cd))                    # 540s left -> ~9m
        tunables._TUNABLES["communal.strike_cooldown_s"] = 30
        ready = CO.viewer_contribution_line(contribs, 7, now)
        self.assertIn("Next strike: ready", _strip(ready))     # 60s > 30s cooldown


class TestCommunalTunableBehaviourIdentical(unittest.TestCase):
    """With the YAML absent, every decider reproduces the frozen launch numbers."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_legacy_escalation(self):
        # 35 start + 0.35/min for 30 min = 45.5 (matches the pre-config formula).
        self.assertAlmostEqual(CO.advance_menace(LEGACY["menace_start"], 30.0), 45.5)

    def test_legacy_reward_curve(self):
        floor, top = LEGACY["rep_floor"], LEGACY["rep_max"]
        for pts, total in ((10, 10), (5, 10), (1, 100), (0, 10)):
            share = min(1.0, pts / max(1, total)) if pts > 0 else 0.0
            expected = int(round(floor + (top - floor) * share)) if pts > 0 else 0
            self.assertEqual(CO.reward_rep_for_share(pts, total, True), expected)

    def test_legacy_title_threshold(self):
        # 0.10 share boundary: 1/10 qualifies, 9/100 does not.
        self.assertTrue(CO.earns_title(1, 10, True))
        self.assertFalse(CO.earns_title(9, 100, True))

    def test_loss_pays_nothing_regardless_of_config(self):
        tunables._TUNABLES.update({
            "communal.rep_floor": 99, "communal.rep_max": 99})
        self.assertEqual(CO.reward_rep_for_share(10, 10, False), 0)
        self.assertFalse(CO.earns_title(10, 10, False))


class TestCommunalTunableShippedYaml(unittest.TestCase):
    """Drift + source-scope guards: the shipped YAML and the use sites."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_shipped_yaml_carries_the_seven_keys_at_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        self.assertEqual(tunables.get_tunable("communal.menace_start", -1),
                         CO.MENACE_START)
        self.assertEqual(tunables.get_tunable("communal.menace_per_minute", -1),
                         CO.MENACE_PER_MINUTE)
        self.assertEqual(tunables.get_tunable("communal.deadline_hours", -1),
                         CO.DEADLINE_HOURS)
        self.assertEqual(tunables.get_tunable("communal.strike_cooldown_s", -1),
                         CO.STRIKE_COOLDOWN_S)
        self.assertEqual(tunables.get_tunable("communal.rep_floor", -1),
                         CO.REP_FLOOR)
        self.assertEqual(tunables.get_tunable("communal.rep_max", -1),
                         CO.REP_MAX)
        self.assertEqual(tunables.get_tunable("communal.title_share_threshold", -1),
                         CO.TITLE_SHARE_THRESHOLD)

    def test_yaml_text_declares_the_keys(self):
        text = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for key in (
            "communal.menace_start", "communal.menace_per_minute",
            "communal.deadline_hours", "communal.strike_cooldown_s",
            "communal.rep_floor", "communal.rep_max",
            "communal.title_share_threshold",
        ):
            self.assertIn(key, text)

    def test_accessors_read_via_get_tunable_no_import_freeze(self):
        # Each accessor must call get_tunable with its own key (so an edit takes
        # effect on the next load) — a regression that froze the value at import
        # would drop the get_tunable call and fail here.
        checks = {
            CO.menace_start: 'get_tunable("communal.menace_start"',
            CO.menace_per_minute: 'get_tunable("communal.menace_per_minute"',
            CO.deadline_hours: 'get_tunable("communal.deadline_hours"',
            CO.strike_cooldown_s: 'get_tunable("communal.strike_cooldown_s"',
            CO.rep_floor: 'get_tunable("communal.rep_floor"',
            CO.rep_max: 'get_tunable("communal.rep_max"',
            CO.title_share_threshold: 'get_tunable("communal.title_share_threshold"',
        }
        for fn, needle in checks.items():
            self.assertIn(needle, inspect.getsource(fn),
                          f"{fn.__name__} must read {needle})")

    def test_pure_deciders_call_accessors_not_raw_constants(self):
        adv = inspect.getsource(CO.advance_menace)
        self.assertIn("menace_per_minute()", adv)
        self.assertNotIn("MENACE_PER_MINUTE", adv)

        rep = inspect.getsource(CO.reward_rep_for_share)
        self.assertIn("rep_floor()", rep)
        self.assertIn("rep_max()", rep)
        self.assertNotIn("REP_FLOOR", rep)
        self.assertNotIn("REP_MAX", rep)

        title = inspect.getsource(CO.earns_title)
        self.assertIn("title_share_threshold()", title)
        self.assertNotIn("TITLE_SHARE_THRESHOLD", title)

        view = inspect.getsource(CO.viewer_contribution_line)
        self.assertIn("strike_cooldown_s()", view)
        self.assertNotIn("STRIKE_COOLDOWN_S", view)

    def test_runtime_use_sites_call_accessors_not_raw_constants(self):
        # The DB-touching runtime posts objectives + checks the strike cooldown;
        # those sites must read the live accessors, never the frozen constant.
        src = inspect.getsource(CORT)
        self.assertIn("CO.menace_start()", src)
        self.assertIn("CO.deadline_hours()", src)
        self.assertIn("CO.strike_cooldown_s()", src)
        self.assertNotIn("CO.MENACE_START", src)
        self.assertNotIn("CO.DEADLINE_HOURS", src)
        self.assertNotIn("CO.STRIKE_COOLDOWN_S", src)


def _strip(s: str) -> str:
    """Drop ANSI escapes so assertions match on the visible text."""
    import re
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


if __name__ == "__main__":
    unittest.main()
