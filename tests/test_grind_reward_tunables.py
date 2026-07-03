# -*- coding: utf-8 -*-
"""tests/test_grind_reward_tunables.py — T3.19 config breadth for the mob-grind
reward trickle (engine/hunting_rewards.py).

The grind faucet's three economy levers — BASE_REWARD / DAILY_SOFT_CAP /
OVER_CAP_FLOOR — were hardcoded module constants: an operator could OBSERVE the
grind economy via the ``@balance grind`` telemetry board (the grind_kill funnel)
but could not TUNE it without a code edit + redeploy. This drop externalizes the
three to data/tunables.yaml under ``grind.*`` and reads them at the USE SITE
through live accessors, closing the observe→tune loop the grind_kill telemetry
opened.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override takes effect through the reward decision +
the at/over-cap flags + the +hunting view, a fat-fingered negative clamps to 0
(can never invert the faucet into a credit SINK on a kill), a present-but-null
key falls back to the default, and the shipped data/tunables.yaml carries the
three keys at their in-code defaults (a drift pin).

Run: python -m pytest tests/test_grind_reward_tunables.py
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

from engine import hunting_rewards as hr  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT
DAY = "2026-06-28"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _FakeDB:
    """Serves adjust_credits + save_character (mirrors test_hunting_rewards)."""

    def __init__(self, credits=1000):
        self._credits = credits
        self.saved = {}

    async def get_character(self, cid):
        # F12: on_huntable_kill reads the pre-award balance via this same
        # handle immediately before adjust_credits — must reflect live state.
        return {"id": cid, "credits": self._credits}

    async def adjust_credits(self, cid, delta, tag, *, allow_negative=True):
        self._credits += delta
        return self._credits

    async def save_character(self, cid, **fields):
        self.saved.update(fields)


def _npc(hostile=True, name="Swoop Thug"):
    return {"id": 99, "name": name, "species": "Weequay",
            "ai_config_json": json.dumps({"hostile": hostile,
                                          "faction": "hutt_cartel"})}


def _killer(credits=1000, attrs=None):
    return {"id": 5, "name": "Hunter", "credits": credits, "room_id": 4207,
            "vanity_titles": "[]", "attributes": json.dumps(attrs or {})}


class GrindRewardTunableAccessors(unittest.TestCase):
    """The use-site accessors: default fallback, override, negative clamp, null."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        self.assertEqual(hr._base_reward(), hr.BASE_REWARD)
        self.assertEqual(hr._daily_soft_cap(), hr.DAILY_SOFT_CAP)
        self.assertEqual(hr._over_cap_floor(), hr.OVER_CAP_FLOOR)

    def test_override_takes_effect(self):
        tunables._TUNABLES.update({
            "grind.base_reward": 50,
            "grind.daily_soft_cap": 1200,
            "grind.over_cap_floor": 7,
        })
        self.assertEqual(hr._base_reward(), 50)
        self.assertEqual(hr._daily_soft_cap(), 1200)
        self.assertEqual(hr._over_cap_floor(), 7)

    def test_negative_clamps_to_zero(self):
        # A fat-fingered negative base_reward must NOT become a debit-on-kill.
        tunables._TUNABLES["grind.base_reward"] = -25
        tunables._TUNABLES["grind.over_cap_floor"] = -1
        tunables._TUNABLES["grind.daily_soft_cap"] = -5
        self.assertEqual(hr._base_reward(), 0)
        self.assertEqual(hr._over_cap_floor(), 0)
        self.assertEqual(hr._daily_soft_cap(), 0)

    def test_present_but_null_falls_back_to_default(self):
        # get_tunable coerces a None (operator typo: `grind.base_reward:`) → default.
        tunables._TUNABLES["grind.base_reward"] = None
        self.assertEqual(hr._base_reward(), hr.BASE_REWARD)

    def test_bad_value_falls_back_to_default(self):
        # A non-numeric YAML value can't crash the reward path — _safe_int default.
        tunables._TUNABLES["grind.base_reward"] = "lots"
        self.assertEqual(hr._base_reward(), hr.BASE_REWARD)

    def test_float_value_truncates_to_int(self):
        tunables._TUNABLES["grind.base_reward"] = 20.9
        self.assertEqual(hr._base_reward(), 20)


class GrindRewardTunableEndToEnd(unittest.TestCase):
    """The override flows through on_huntable_kill + hunting_log_view."""

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def test_base_reward_override_credits_the_killer(self):
        tunables._TUNABLES["grind.base_reward"] = 50
        db, char = _FakeDB(1000), _killer(1000)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY))
        self.assertEqual(out["reward"], 50)
        self.assertEqual(char["credits"], 1050)

    def test_soft_cap_override_moves_the_floor_boundary(self):
        # Tighten the cap to 30: a kill seeded at 30 cr today is already over cap
        # and pays the floor (default behaviour would pay BASE under the 400 cap).
        tunables._TUNABLES["grind.daily_soft_cap"] = 30
        seed = {hr.HUNT_LOG_KEY: {"kills": 3, "daily_credits": 30, "day": DAY}}
        out = _run(hr.on_huntable_kill(_FakeDB(), _killer(attrs=seed),
                                       _npc(), day_stamp=DAY))
        self.assertEqual(out["reward"], hr.OVER_CAP_FLOOR)
        self.assertTrue(out["at_cap"])

    def test_over_cap_floor_override_pays_the_new_floor(self):
        tunables._TUNABLES["grind.over_cap_floor"] = 9
        seed = {hr.HUNT_LOG_KEY: {"kills": 3,
                                  "daily_credits": hr.DAILY_SOFT_CAP, "day": DAY}}
        out = _run(hr.on_huntable_kill(_FakeDB(), _killer(attrs=seed),
                                       _npc(), day_stamp=DAY))
        self.assertEqual(out["reward"], 9)

    def test_negative_base_reward_never_debits(self):
        tunables._TUNABLES["grind.base_reward"] = -100
        db, char = _FakeDB(1000), _killer(1000)
        out = _run(hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY))
        self.assertEqual(out["reward"], 0)
        self.assertEqual(char["credits"], 1000)   # not 900

    def test_hunting_view_reflects_cap_override(self):
        tunables._TUNABLES["grind.daily_soft_cap"] = 999
        view = hr.hunting_log_view(_killer(), day_stamp=DAY)
        self.assertEqual(view["daily_cap"], 999)

    def test_behaviour_identical_to_defaults_when_unset(self):
        # No tunables loaded → exact legacy numbers.
        out = _run(hr.on_huntable_kill(_FakeDB(), _killer(), _npc(),
                                       day_stamp=DAY))
        self.assertEqual(out["reward"], hr.BASE_REWARD)   # 15
        self.assertEqual(out["daily_credits"], hr.BASE_REWARD)
        self.assertFalse(out["at_cap"])


class GrindRewardTunableShipped(unittest.TestCase):
    """Drift pins: the shipped YAML carries the three keys at in-code defaults."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_keys_at_in_code_defaults(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        # Behaviour-identical: each shipped value EQUALS the module constant.
        self.assertEqual(tunables.get_tunable("grind.base_reward", -1),
                         hr.BASE_REWARD)
        self.assertEqual(tunables.get_tunable("grind.daily_soft_cap", -1),
                         hr.DAILY_SOFT_CAP)
        self.assertEqual(tunables.get_tunable("grind.over_cap_floor", -1),
                         hr.OVER_CAP_FLOOR)

    def test_keys_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("grind.base_reward:", ty)
        self.assertIn("grind.daily_soft_cap:", ty)
        self.assertIn("grind.over_cap_floor:", ty)

    def test_accessors_read_at_use_site(self):
        # Guard the use-site contract: the constants are read through get_tunable,
        # not frozen at import (so an operator edit takes effect on reload).
        src = (REPO / "engine" / "hunting_rewards.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable("grind.base_reward"', src)
        self.assertIn('get_tunable("grind.daily_soft_cap"', src)
        self.assertIn('get_tunable("grind.over_cap_floor"', src)


if __name__ == "__main__":
    unittest.main()
