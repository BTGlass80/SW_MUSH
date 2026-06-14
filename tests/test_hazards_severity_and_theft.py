# -*- coding: utf-8 -*-
"""
tests/test_hazards_severity_and_theft.py

Per-drop guard for the 2026-06-14 hazards.py drop (from the engine defect-hunt —
docs/design/HANDOFF_engine_defect_hunt_2026-06-14.md):

  * severity_difficulty_double_scaled (HIGH): the hazard config's stored
    "difficulty" is ALREADY severity-scaled by its producers (set_room_hazard /
    the wilderness synthesizer store base_difficulty + (severity-1)*3), but
    check_hazard_for_character read that and then added (severity-1)*3 AGAIN, so
    every stored hazard resolved harder than intended (severity-2 extreme_heat
    rolled difficulty 16 instead of 13). Fix: adopt the stored difficulty as-is;
    apply the scaling only on the (difficulty-less) fallback.

  * theft_credit_dict_desync (MEDIUM): the urban_danger pickpocket pre-mutated
    char["credits"] with a local guess, DISCARDED adjust_credits' authoritative
    return, and narrated "You lost N credits" even when the ledger write failed.
    Fix: char["credits"] = await adjust_credits(...) (adopt the ledger balance),
    narrate only after the credits actually moved.

Both assertions fail against the unfixed code.
"""

import asyncio
import json
import os
import sys
import types
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


def _char():
    return {"id": 1, "name": "T", "credits": 1000,
            "attributes": "{}", "inventory": "{}", "equipment": "{}"}


def _room(hazard: dict):
    return {"id": 1, "properties": json.dumps({"environment_hazard": hazard})}


class _FakeDB:
    def __init__(self, ret=888, raises=False):
        self.ret = ret
        self.raises = raises
        self.calls = []

    async def adjust_credits(self, char_id, delta, tag):
        self.calls.append((char_id, delta, tag))
        if self.raises:
            raise RuntimeError("ledger write failed")
        return self.ret

    async def save_character(self, *a, **k):
        return None


class _FakeSession:
    def __init__(self):
        self.events = []

    async def send_json(self, etype, payload):
        self.events.append((etype, payload))

    async def send_line(self, line):
        return None

    def fired_pickpocket(self):
        return any("pickpocket" in json.dumps(p, default=str)
                   for _, p in self.events)


def _clear_timers():
    from engine import hazards
    hazards._hazard_timers.clear()


class TestSeverityDoubleScaling(unittest.TestCase):
    def _captured_difficulty(self, hazard):
        captured = {}

        def _capture(char, skill, difficulty):
            captured["difficulty"] = difficulty
            return types.SimpleNamespace(success=True)  # pass → no effect path

        async def _t():
            from engine.hazards import check_hazard_for_character
            _clear_timers()
            with mock.patch("engine.skill_checks.perform_skill_check", _capture), \
                 mock.patch("engine.hazards._extreme_heat_time_mod", lambda tod: 0):
                await check_hazard_for_character(_char(), _room(hazard), db=None)
            return captured.get("difficulty")
        return _run(_t())

    def test_stored_difficulty_not_double_scaled(self):
        # severity-2 extreme_heat: producers store base(10)+(2-1)*3 = 13.
        diff = self._captured_difficulty(
            {"type": "extreme_heat", "severity": 2, "difficulty": 13})
        self.assertEqual(diff, 13,
                         "stored hazard difficulty must not be re-scaled "
                         "(double-scaling gave 16)")

    def test_fallback_difficulty_is_scaled(self):
        # A config with severity but no pre-computed difficulty: the fallback
        # must scale it (base 10 + (2-1)*3 = 13).
        diff = self._captured_difficulty(
            {"type": "extreme_heat", "severity": 2})
        self.assertEqual(diff, 13,
                         "the difficulty-less fallback must apply severity scaling")

    def test_severity_one_is_base(self):
        diff = self._captured_difficulty(
            {"type": "extreme_heat", "severity": 1, "difficulty": 10})
        self.assertEqual(diff, 10)


class TestUrbanTheftFunnel(unittest.TestCase):
    def test_theft_adopts_ledger_balance_and_narrates(self):
        async def _t():
            from engine.hazards import check_hazard_for_character
            _clear_timers()
            db = _FakeDB(ret=888)         # ledger-authoritative balance != local guess
            sess = _FakeSession()
            char = _char()                # credits 1000; stolen = 50 → local guess 950
            with mock.patch("engine.skill_checks.perform_skill_check",
                            lambda c, s, d: types.SimpleNamespace(success=False)):
                await check_hazard_for_character(
                    char, _room({"type": "urban_danger", "severity": 2}),
                    db=db, session=sess)
            # adopts the ledger return (888), NOT the local 1000-50=950 guess
            self.assertEqual(char["credits"], 888)
            self.assertEqual(db.calls, [(1, -50, "hazard_theft")])
            self.assertTrue(sess.fired_pickpocket())
        _run(_t())

    def test_theft_write_failure_no_loss_no_narrative(self):
        async def _t():
            from engine.hazards import check_hazard_for_character
            _clear_timers()
            db = _FakeDB(raises=True)
            sess = _FakeSession()
            char = _char()
            with mock.patch("engine.skill_checks.perform_skill_check",
                            lambda c, s, d: types.SimpleNamespace(success=False)):
                await check_hazard_for_character(
                    char, _room({"type": "urban_danger", "severity": 2}),
                    db=db, session=sess)
            # ledger write failed → credits unchanged, and NO false "you lost" pose
            self.assertEqual(char["credits"], 1000)
            self.assertFalse(sess.fired_pickpocket())
        _run(_t())


if __name__ == "__main__":
    unittest.main()
