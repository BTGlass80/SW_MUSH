# -*- coding: utf-8 -*-
"""
tests/test_breaching.py — breaching charges (CRAFT.mines_breaching_split,
breaching half — 2026-06-13).

`breach <target>` blows open a sealed obstacle (a `breachable` room
object carrying data.breach_difficulty) with a single-use breaching
charge (a crafted consumable in attributes.consumables) and a Demolitions
check. Safe by design (no blast-on-players); placed mines deferred.

Covers: find_breachable matching, the charge gate (must carry one),
charge-consumed-on-attempt (success AND failure), the demolitions check
driving success/failure, obstacle deletion on success, and the
no-obstacle / no-charge / ambiguous paths.
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


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _StubDB:
    """Minimal DB surface attempt_breach uses."""
    def __init__(self, objects):
        self._objects = list(objects)
        self.deleted = []
        self.saved = []

    async def get_objects_in_room(self, room_id, obj_type=None):
        objs = self._objects
        if obj_type:
            objs = [o for o in objs if o.get("type") == obj_type]
        return [dict(o) for o in objs]

    async def delete_object(self, object_id):
        self.deleted.append(object_id)
        self._objects = [o for o in self._objects if o.get("id") != object_id]

    async def save_character(self, char_id, **fields):
        self.saved.append((char_id, fields))


def _obstacle(oid=1, name="Sealed Blast Door", difficulty=20):
    return {
        "id": oid, "type": "breachable", "name": name, "room_id": 100,
        "data": json.dumps({
            "breach_difficulty": difficulty,
            "reveal": "The blast door hangs open, edges glowing.",
        }),
    }


def _char(charges=1, demolitions="12D"):
    # 12D demolitions ~ always beats difficulty 20; 0D ~ always fails.
    attrs = {"consumables": {"breaching_charge": charges} if charges else {}}
    return {
        "id": 7, "name": "Sapper", "room_id": 100,
        "attributes": json.dumps(attrs),
        "skills": json.dumps({"demolitions": demolitions}),
    }


# ── find_breachable ──────────────────────────────────────────────────


class TestFindBreachable(unittest.TestCase):
    def test_sole_obstacle_no_target(self):
        from engine.breaching import find_breachable
        objs = [_obstacle()]
        self.assertIsNotNone(find_breachable(objs, ""))

    def test_substring_match(self):
        from engine.breaching import find_breachable
        objs = [_obstacle(name="Sealed Blast Door"),
                _obstacle(oid=2, name="Iron Gate")]
        self.assertEqual(find_breachable(objs, "gate")["id"], 2)

    def test_ambiguous_no_target_returns_none(self):
        from engine.breaching import find_breachable
        objs = [_obstacle(oid=1), _obstacle(oid=2, name="Iron Gate")]
        self.assertIsNone(find_breachable(objs, ""))

    def test_ignores_non_breachable_objects(self):
        from engine.breaching import find_breachable
        objs = [{"id": 9, "type": "corpse", "name": "a corpse"}]
        self.assertIsNone(find_breachable(objs, ""))


# ── attempt_breach ───────────────────────────────────────────────────


class TestAttemptBreach(unittest.TestCase):
    def test_no_obstacle(self):
        from engine.breaching import attempt_breach
        db = _StubDB([])
        res = _run(attempt_breach(db, _char(), ""))
        self.assertFalse(res["ok"])
        self.assertIn("nothing here to breach", res["msg"].lower())

    def test_no_charge_blocks_and_keeps_obstacle(self):
        from engine.breaching import attempt_breach
        db = _StubDB([_obstacle()])
        res = _run(attempt_breach(db, _char(charges=0), ""))
        self.assertFalse(res["ok"])
        self.assertIn("breaching charge", res["msg"].lower())
        self.assertEqual(db.deleted, [])  # obstacle intact

    def test_success_consumes_charge_and_deletes_obstacle(self):
        from engine.breaching import attempt_breach
        from engine.buffs import get_consumable_count
        db = _StubDB([_obstacle(difficulty=10)])
        char = _char(charges=1, demolitions="12D")
        res = _run(attempt_breach(db, char, ""))
        self.assertTrue(res["ok"])
        self.assertTrue(res["breached"])
        self.assertEqual(db.deleted, [1])               # obstacle removed
        self.assertEqual(get_consumable_count(char, "breaching_charge"), 0)
        self.assertTrue(db.saved)                        # attrs persisted

    def test_failure_consumes_charge_but_keeps_obstacle(self):
        from engine.breaching import attempt_breach
        from engine.buffs import get_consumable_count
        # 0D demolitions vs difficulty 30 -> reliable failure.
        db = _StubDB([_obstacle(difficulty=30)])
        char = _char(charges=1, demolitions="1D")
        res = _run(attempt_breach(db, char, ""))
        self.assertTrue(res["ok"])           # the attempt resolved...
        self.assertFalse(res["breached"])    # ...but the breach failed
        self.assertEqual(db.deleted, [])     # obstacle intact
        # The charge is still spent (shaped charge blown).
        self.assertEqual(get_consumable_count(char, "breaching_charge"), 0)

    def test_target_mismatch(self):
        from engine.breaching import attempt_breach
        db = _StubDB([_obstacle(name="Blast Door")])
        res = _run(attempt_breach(db, _char(), "nonexistent"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.deleted, [])

    def test_delete_failure_reports_honest_failure_not_false_success(self):
        # Regression (defect-hunt): a passing demolitions check followed by a
        # delete_object that RAISES must NOT tell the player the breach opened.
        from engine.breaching import attempt_breach

        class _DeleteRaisesDB(_StubDB):
            async def delete_object(self, object_id):
                raise RuntimeError("simulated DB failure")

        db = _DeleteRaisesDB([_obstacle(difficulty=10)])
        char = _char(charges=1, demolitions="12D")  # skill check passes
        res = _run(attempt_breach(db, char, ""))
        # The obstacle is still there -> the breach did NOT succeed.
        self.assertFalse(res["breached"],
                         "delete failure must not report a successful breach")
        self.assertNotIn("blows", res["msg"].lower())   # no false success line
        self.assertIn("still blocked", res["msg"].lower())


if __name__ == "__main__":
    unittest.main()
