# -*- coding: utf-8 -*-
"""
tests/test_encounter_skillcheck_funnel.py — regression guard for the space
encounter skill-check funnel bypass (drop encounter-skillcheck-funnel).

`engine/encounter_{anomaly,hunter,patrol,pirate,texture}.py::_skill_check`
called the skill-check funnel as `await perform_skill_check(char_id=..., db=...)`.
But `engine.skill_checks.perform_skill_check` is SYNCHRONOUS and takes the char
DICT positionally with no `char_id`/`db` parameters — so the call ALWAYS raised
and every space-encounter check silently fell back to skill-ignoring **raw 3D**
(and reported roll 0 via the wrong result-field names). The fix loads the char
via `db.get_character` and calls `perform_skill_check(char, skill, difficulty)`.

The discriminating assertion: a high-skill character vs a high difficulty must
now SUCCEED with a real roll **> 18** — raw 3D caps at 18 and could never reach
it, so this proves the real skill pool is used (not the old fallback).
"""
import asyncio
import json
import random
import unittest


def _run(coro):
    return asyncio.run(coro)


def _char(skill_name, code, char_id=1):
    return {
        "id": char_id, "name": "Ace", "room_id": 1,
        "attributes": json.dumps({"perception": "3D", "mechanical": "3D",
                                  "knowledge": "3D", "dexterity": "3D",
                                  "technical": "3D", "strength": "3D"}),
        "skills": json.dumps({skill_name: code}),
    }


class _FakeDB:
    def __init__(self, char):
        self._char = char

    async def get_character(self, char_id):
        return self._char


# All five share the same helper logic (patrol's also carries a "fumble" key).
import engine.encounter_anomaly as anomaly
import engine.encounter_hunter as hunter
import engine.encounter_pirate as pirate
import engine.encounter_texture as texture
import engine.encounter_patrol as patrol

_MODULES = [anomaly, hunter, pirate, texture, patrol]


class TestEncounterSkillCheckFunnel(unittest.TestCase):
    def test_high_skill_beats_high_difficulty_via_real_pool(self):
        # 12D perception vs difficulty 22: real skill ~always succeeds with a
        # roll far above 18; raw 3D (max 18) could NEVER reach 22.
        random.seed(2024)
        for mod in _MODULES:
            db = _FakeDB(_char("perception", "12D"))
            res = _run(mod._skill_check(1, "perception", 22, db))
            self.assertTrue(res["success"],
                            f"{mod.__name__}: high skill should beat diff 22")
            self.assertGreater(res["roll"], 18,
                               f"{mod.__name__}: roll {res['roll']} <= 18 means raw-3D "
                               "fallback (real skill pool not used)")

    def test_low_skill_fails_high_difficulty(self):
        random.seed(7)
        for mod in _MODULES:
            db = _FakeDB(_char("perception", "1D"))
            res = _run(mod._skill_check(1, "perception", 28, db))
            self.assertFalse(res["success"],
                             f"{mod.__name__}: 1D should not beat diff 28")

    def test_missing_char_falls_back_without_raising(self):
        # get_character returns None -> the loud raw-3D fallback runs (no crash).
        class _NoneDB:
            async def get_character(self, char_id):
                return None
        random.seed(1)
        for mod in _MODULES:
            res = _run(mod._skill_check(999, "perception", 10, mod and _NoneDB()))
            self.assertIn("success", res)
            self.assertIn("roll", res)
            self.assertLessEqual(res["roll"], 18)  # raw 3D fallback range

    def test_patrol_keeps_fumble_key(self):
        random.seed(3)
        db = _FakeDB(_char("con", "5D"))
        res = _run(patrol._skill_check(1, "con", 10, db))
        self.assertIn("fumble", res)
        self.assertIsInstance(res["fumble"], bool)


if __name__ == "__main__":
    unittest.main()
