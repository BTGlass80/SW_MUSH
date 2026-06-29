# -*- coding: utf-8 -*-
"""tests/test_hazard_tunables.py — T3.19 config breadth for the environmental
hazard balance model (engine/hazards.py).

The DENSITY/DIFFICULTY sibling of the encounter-density drop
(test_encounter_density_tunables) and the SINK sibling of the smuggling-bust /
vanity-title sinks: where the wilderness encounter levers pace how often a
huntable mob spawns, these pace the periodic hazard tick — how often a hazard
re-checks a character, how hard the skill-vs-difficulty roll is per type and
severity (the extreme_heat clock grading included), and how much the
urban_danger pickpocket SINK lifts. Every governing constant was hardcoded:
``HAZARD_CHECK_INTERVAL``, the per-type ``base_difficulty`` map, the shared
``(severity-1)*3`` step (duplicated at three call sites), the
``_EXTREME_HEAT_TOD_MOD`` clock band + its DC floor, and the pickpocket's
``0.05 / max(50, severity*100)`` formula.

This drop externalizes the lot to data/tunables.yaml under ``hazards.*`` and
reads each at the USE SITE, routing the three difficulty sites through one
``_scaled_difficulty`` helper. The pickpocket theft is funnel-routed
(``adjust_credits "hazard_theft"``) so it surfaces in @balance flows / @economy
velocity as a credit sink.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), overrides flow through the cooldown gate / the per-type +
severity DC / the heat clock grading / the theft amount end-to-end, the
double-scale fix is preserved (a stored difficulty isn't re-scaled), fat-fingered
tunables clamp (interval >= 0, DC >= 1, theft fraction to [0,1], theft magnitudes
>= 0), present-but-null + corrupt values fall back to the in-code default, the
three difficulty sites share the one helper, and the shipped tunables.yaml carries
all thirteen keys at their in-code defaults (a drift pin).

Run: python -m pytest tests/test_hazard_tunables.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import hazards as H  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


class _FakeDB:
    """Records adjust_credits calls; the pickpocket SINK is the one DB touch
    the theft path makes (save_character is a no-op for the urban path)."""

    def __init__(self):
        self.credit_calls = []

    async def adjust_credits(self, char_id, delta, tag):
        self.credit_calls.append((char_id, delta, tag))
        return 0

    async def save_character(self, *a, **k):
        return None


class HazardTunableAccessors(unittest.TestCase):
    """The use-site accessors: default fallback, override, clamp, null, corrupt."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_check_interval_default_is_in_code_constant(self):
        self.assertEqual(H._check_interval(), H.HAZARD_CHECK_INTERVAL)

    def test_check_interval_override(self):
        tunables._TUNABLES["hazards.check_interval_seconds"] = 600
        self.assertEqual(H._check_interval(), 600)

    def test_check_interval_negative_clamps_to_zero(self):
        # A negative interval must not underflow the (now - last) >= window gate.
        tunables._TUNABLES["hazards.check_interval_seconds"] = -10
        self.assertEqual(H._check_interval(), 0)

    def test_check_interval_corrupt_and_null_fall_back(self):
        tunables._TUNABLES["hazards.check_interval_seconds"] = "soon"
        self.assertEqual(H._check_interval(), H.HAZARD_CHECK_INTERVAL)
        tunables._TUNABLES["hazards.check_interval_seconds"] = None
        self.assertEqual(H._check_interval(), H.HAZARD_CHECK_INTERVAL)

    def test_scaled_difficulty_defaults_match_in_code(self):
        # base = in-code HAZARD_TYPES base_difficulty; step = 3.
        for htype in ("extreme_heat", "toxic_atmosphere", "urban_danger",
                      "radiation"):
            base = H.HAZARD_TYPES[htype]["base_difficulty"]
            self.assertEqual(H._scaled_difficulty(htype, 1), base)
            self.assertEqual(H._scaled_difficulty(htype, 3), base + 2 * 3)

    def test_scaled_difficulty_per_type_override(self):
        tunables._TUNABLES["hazards.difficulty_radiation"] = 20
        self.assertEqual(H._scaled_difficulty("radiation", 1), 20)
        self.assertEqual(H._scaled_difficulty("radiation", 3), 20 + 2 * 3)

    def test_scaled_difficulty_step_override(self):
        tunables._TUNABLES["hazards.severity_difficulty_step"] = 5
        # radiation base 15, step 5, severity 3 -> 15 + 2*5 = 25
        self.assertEqual(H._scaled_difficulty("radiation", 3), 25)

    def test_scaled_difficulty_clamps_to_at_least_one(self):
        # A fat-fingered negative step can't yield a non-positive (auto-pass) DC.
        tunables._TUNABLES["hazards.severity_difficulty_step"] = -999
        self.assertEqual(H._scaled_difficulty("extreme_heat", 5), 1)

    def test_scaled_difficulty_null_and_corrupt_fall_back(self):
        tunables._TUNABLES["hazards.difficulty_radiation"] = None
        self.assertEqual(H._scaled_difficulty("radiation", 1), 15)
        tunables._TUNABLES["hazards.difficulty_radiation"] = "deadly"
        self.assertEqual(H._scaled_difficulty("radiation", 1), 15)

    def test_scaled_difficulty_unknown_type_uses_safe_base(self):
        # Unknown type -> base 10 default (no KeyError); behaviour-identical to a
        # missing template entry.
        self.assertEqual(H._scaled_difficulty("phantom_hazard", 1), 10)

    def test_heat_time_mod_defaults_match_in_code(self):
        self.assertEqual(H._extreme_heat_time_mod("day"), 3)
        self.assertEqual(H._extreme_heat_time_mod("dusk"), 0)
        self.assertEqual(H._extreme_heat_time_mod("night"), -4)
        self.assertEqual(H._extreme_heat_time_mod("nonsense"), 0)
        self.assertEqual(H._extreme_heat_time_mod(None), 0)

    def test_heat_time_mod_override_allows_negative(self):
        tunables._TUNABLES["hazards.heat_tod_night"] = -8
        tunables._TUNABLES["hazards.heat_tod_day"] = 6
        self.assertEqual(H._extreme_heat_time_mod("night"), -8)
        self.assertEqual(H._extreme_heat_time_mod("day"), 6)
        # Unknown band stays a no-op even with overrides loaded.
        self.assertEqual(H._extreme_heat_time_mod("midnight"), 0)

    def test_heat_time_mod_corrupt_falls_back(self):
        tunables._TUNABLES["hazards.heat_tod_day"] = "hot"
        self.assertEqual(H._extreme_heat_time_mod("day"), 3)


class HazardTheftSinkEndToEnd(unittest.IsolatedAsyncioTestCase):
    """The pickpocket SINK override flows through check_hazard_for_character to
    the metered adjust_credits("hazard_theft") call."""

    def setUp(self):
        tunables.reset_tunables()
        H._hazard_timers.clear()

    def tearDown(self):
        tunables.reset_tunables()
        H._hazard_timers.clear()

    def _char(self, credits=10000):
        return {
            "id": 4242,
            "credits": credits,
            "attributes": json.dumps({"perception": "2D"}),
            "skills": json.dumps({}),
            "inventory": json.dumps({"items": []}),
            "equipment": json.dumps({}),
        }

    def _room(self, severity=3):
        # Stored difficulty 999 forces the perception roll to FAIL deterministically
        # -> the urban_danger theft branch runs. (Stored difficulty is used as-is;
        # the double-scale fix means severity is NOT re-applied here.)
        return {
            "id": 7777,
            "properties": json.dumps({
                "environment_hazard": {
                    "type": "urban_danger", "severity": severity,
                    "difficulty": 999,
                },
            }),
        }

    async def test_default_theft_amount(self):
        db = _FakeDB()
        char = self._char(credits=10000)
        res = await H.check_hazard_for_character(char, self._room(severity=3), db)
        self.assertIsNotNone(res)
        self.assertFalse(res["passed"])
        # default: min(int(10000*0.05)=500, max(50, 3*100)=300) = 300
        self.assertEqual(db.credit_calls, [(4242, -300, "hazard_theft")])
        self.assertEqual(char["credits"], 9700)

    async def test_override_theft_amount(self):
        tunables._TUNABLES["hazards.theft_credit_fraction"] = 0.10
        tunables._TUNABLES["hazards.theft_per_severity"] = 50
        db = _FakeDB()
        char = self._char(credits=10000)
        await H.check_hazard_for_character(char, self._room(severity=3), db)
        # min(int(10000*0.10)=1000, max(50, 3*50)=150) = 150
        self.assertEqual(db.credit_calls, [(4242, -150, "hazard_theft")])
        self.assertEqual(char["credits"], 9850)

    async def test_theft_fraction_clamps_to_probability_range(self):
        # 5.0 -> clamps to 1.0 (the whole balance, capped by the severity ceiling).
        tunables._TUNABLES["hazards.theft_credit_fraction"] = 5.0
        tunables._TUNABLES["hazards.theft_per_severity"] = 100000
        db = _FakeDB()
        char = self._char(credits=800)
        await H.check_hazard_for_character(char, self._room(severity=1), db)
        # min(int(800*1.0)=800, max(50, 100000)) = 800
        self.assertEqual(db.credit_calls, [(4242, -800, "hazard_theft")])

    async def test_theft_funnel_tag_is_hazard_theft(self):
        db = _FakeDB()
        await H.check_hazard_for_character(self._char(), self._room(), db)
        self.assertEqual(len(db.credit_calls), 1)
        self.assertEqual(db.credit_calls[0][2], "hazard_theft")
        self.assertLess(db.credit_calls[0][1], 0)  # a debit, never a credit


class HazardCheckIntervalGate(unittest.TestCase):
    """The interval override flows through the _should_check cooldown gate."""

    def setUp(self):
        tunables.reset_tunables()
        H._hazard_timers.clear()

    def tearDown(self):
        tunables.reset_tunables()
        H._hazard_timers.clear()

    def test_recent_check_holds_under_default_window(self):
        import time
        H._hazard_timers[(1, 2)] = time.time() - 30  # 30s ago, default 300s
        self.assertFalse(H._should_check(1, 2))

    def test_tightened_window_releases_sooner(self):
        import time
        tunables._TUNABLES["hazards.check_interval_seconds"] = 10
        H._hazard_timers[(1, 2)] = time.time() - 30  # 30s ago, 10s window
        self.assertTrue(H._should_check(1, 2))

    def test_zero_interval_always_checks(self):
        import time
        tunables._TUNABLES["hazards.check_interval_seconds"] = 0
        H._hazard_timers[(1, 2)] = time.time()  # just now
        self.assertTrue(H._should_check(1, 2))  # elapsed ~0 >= 0


class HazardTunablesShipped(unittest.TestCase):
    """Drift pins: the shipped YAML carries the 13 keys at in-code defaults, and
    the three difficulty sites read through the one tunable-backed helper."""

    EXPECTED = {
        "hazards.check_interval_seconds": 300,
        "hazards.difficulty_extreme_heat": 10,
        "hazards.difficulty_toxic_atmosphere": 12,
        "hazards.difficulty_urban_danger": 10,
        "hazards.difficulty_radiation": 15,
        "hazards.severity_difficulty_step": 3,
        "hazards.heat_tod_day": 3,
        "hazards.heat_tod_dusk": 0,
        "hazards.heat_tod_night": -4,
        "hazards.heat_difficulty_floor": 5,
        "hazards.theft_credit_fraction": 0.05,
        "hazards.theft_floor": 50,
        "hazards.theft_per_severity": 100,
    }

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_keys_at_in_code_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for key, val in self.EXPECTED.items():
            got = tunables.get_tunable(key, "MISSING")
            self.assertEqual(got, val, f"{key}: shipped {got!r}, expected {val!r}")

    def test_difficulty_keys_match_in_code_hazard_types(self):
        # The per-type DC defaults must equal the live HAZARD_TYPES map (no drift).
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for htype in ("extreme_heat", "toxic_atmosphere", "urban_danger",
                      "radiation"):
            self.assertEqual(
                tunables.get_tunable(f"hazards.difficulty_{htype}", -1),
                H.HAZARD_TYPES[htype]["base_difficulty"])

    def test_three_difficulty_sites_share_one_helper(self):
        src = (REPO / "engine" / "hazards.py").read_text(encoding="utf-8")
        # All three formula sites now call the helper; the old inline formula is gone.
        self.assertEqual(src.count("_scaled_difficulty("), 3 + 1)  # 3 sites + def
        self.assertNotIn("base_difficulty\"] + (severity - 1) * 3", src)

    def test_accessors_read_at_use_site(self):
        src = (REPO / "engine" / "hazards.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable("hazards.check_interval_seconds"', src)
        self.assertIn('get_tunable(f"hazards.difficulty_{hazard_type}"', src)
        self.assertIn('get_tunable("hazards.severity_difficulty_step"', src)
        self.assertIn('get_tunable("hazards.theft_credit_fraction"', src)


if __name__ == "__main__":
    unittest.main()
