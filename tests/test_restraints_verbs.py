# -*- coding: utf-8 -*-
"""tests/test_restraints_verbs.py — restraint verb layer (CRAFT.HOOK.restraints
slice 2): the async orchestration helpers attempt_cuff / attempt_uncuff /
attempt_escape_action / set_consent_action over engine/restraints.py.

Drives the helpers with a stub DB + session_mgr (the surface match_in_room
needs), asserting the consent/defeat PvP gate, the binders sink, release
authority, escape, and persistence. The move/attack/equip command GATES are a
thin `is_restrained` check covered by the engine test's is_restrained.
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

import engine.restraints as R


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


class _StubSession:
    def __init__(self, char):
        self.character = char


class _StubSessionMgr:
    """Returns the given target sessions for any room."""
    def __init__(self, sessions):
        self._sessions = sessions

    def sessions_in_room(self, room_id, source_char=None):
        return self._sessions


class _StubDB:
    """Minimal DB surface the restraint helpers + match_in_room use."""
    def __init__(self, npcs=None):
        self._npcs = list(npcs or [])
        self.saved = []

    async def get_npcs_in_room(self, room_id):
        return [dict(n) for n in self._npcs]

    async def get_character(self, cid):
        return None

    async def get_room(self, rid):
        return None

    async def save_character(self, char_id, **fields):
        self.saved.append((char_id, fields))


def _pc(cid, name, *, wound=0, binders=0, attrs=None):
    a = dict(attrs or {})
    if binders:
        a.setdefault("consumables", {})["binders"] = binders
    return {
        "id": cid, "name": name, "room_id": 100,
        "wound_level": wound, "attributes": json.dumps(a),
        "skills": "{}",
    }


def _cuffer(binders=1):
    return _pc(1, "Captor", binders=binders)


# ── attempt_cuff: the consent/defeat gate ───────────────────────────────────

class TestCuffGate(unittest.TestCase):

    def _cuff(self, target, cuffer=None):
        cuffer = cuffer or _cuffer()
        db = _StubDB()
        sm = _StubSessionMgr([_StubSession(target)])
        return _run(R.attempt_cuff(db, cuffer, target["name"], session_mgr=sm)), cuffer, target

    def test_defeated_pc_cuffed(self):
        res, cuffer, target = self._cuff(_pc(2, "Victim", wound=4))
        self.assertTrue(res["ok"])
        self.assertTrue(R.is_restrained(target))
        # binders consumed by the successful cuff
        from engine.buffs import get_consumable_count
        self.assertEqual(get_consumable_count(cuffer, "binders"), 0)

    def test_healthy_unwilling_pc_rejected(self):
        res, _c, target = self._cuff(_pc(2, "Victim", wound=0))
        self.assertFalse(res["ok"])
        self.assertFalse(R.is_restrained(target))

    def test_consenting_pc_cuffed(self):
        target = _pc(2, "Willing", wound=0, attrs={"restraint_consent": True})
        res, _c, target2 = self._cuff(target)
        self.assertTrue(res["ok"])

    def test_no_binders_rejected(self):
        res, _c, target = self._cuff(_pc(2, "Victim", wound=4), cuffer=_cuffer(binders=0))
        self.assertFalse(res["ok"])
        self.assertIn("binders", res["msg"].lower())
        self.assertFalse(R.is_restrained(target))

    def test_binders_not_consumed_on_failed_gate(self):
        # A rejected cuff (healthy target) must NOT spend the binders.
        cuffer = _cuffer(binders=1)
        db = _StubDB()
        target = _pc(2, "Victim", wound=0)
        sm = _StubSessionMgr([_StubSession(target)])
        res = _run(R.attempt_cuff(db, cuffer, "Victim", session_mgr=sm))
        self.assertFalse(res["ok"])
        from engine.buffs import get_consumable_count
        self.assertEqual(get_consumable_count(cuffer, "binders"), 1)  # kept

    def test_self_cuff_rejected(self):
        cuffer = _cuffer()
        db = _StubDB()
        sm = _StubSessionMgr([_StubSession(cuffer)])
        # match resolves to self (same id) — but sessions_in_room excludes the
        # searcher; emulate by having the only session be the cuffer, then the
        # candidate list is empty → not found. So instead test the explicit
        # self guard via an NPC-free direct path is N/A; assert not-found msg.
        res = _run(R.attempt_cuff(db, cuffer, "Captor", session_mgr=sm))
        self.assertFalse(res["ok"])

    def test_npc_rejected_v1(self):
        # v1 cuffs PCs only.
        cuffer = _cuffer()
        db = _StubDB(npcs=[{"id": 9, "name": "Thug", "room_id": 100,
                            "attributes": "{}"}])
        sm = _StubSessionMgr([])
        res = _run(R.attempt_cuff(db, cuffer, "Thug", session_mgr=sm))
        self.assertFalse(res["ok"])
        self.assertIn("isn't supported", res["msg"].lower())

    def test_target_not_found(self):
        cuffer = _cuffer()
        db = _StubDB()
        sm = _StubSessionMgr([])
        res = _run(R.attempt_cuff(db, cuffer, "Nobody", session_mgr=sm))
        self.assertFalse(res["ok"])

    def test_empty_target(self):
        res = _run(R.attempt_cuff(_StubDB(), _cuffer(), "", session_mgr=_StubSessionMgr([])))
        self.assertFalse(res["ok"])


# ── attempt_uncuff: release authority ────────────────────────────────────────

class TestUncuff(unittest.TestCase):

    def _restrained_target(self, captor_id=1):
        t = _pc(2, "Prisoner", wound=4)
        R.apply_restraint(t, applied_by="Captor", applied_by_id=captor_id)
        return t

    def _uncuff(self, releaser, target, is_admin=False):
        db = _StubDB()
        sm = _StubSessionMgr([_StubSession(target)])
        return _run(R.attempt_uncuff(db, releaser, target["name"],
                                     session_mgr=sm, is_admin=is_admin))

    def test_captor_releases(self):
        target = self._restrained_target(captor_id=1)
        res = self._uncuff(_pc(1, "Captor"), target)
        self.assertTrue(res["ok"])
        self.assertFalse(R.is_restrained(target))

    def test_third_party_cannot_release(self):
        target = self._restrained_target(captor_id=1)
        res = self._uncuff(_pc(3, "Stranger"), target)
        self.assertFalse(res["ok"])
        self.assertTrue(R.is_restrained(target))  # still bound

    def test_admin_releases_anyone(self):
        target = self._restrained_target(captor_id=1)
        res = self._uncuff(_pc(3, "Admin"), target, is_admin=True)
        self.assertTrue(res["ok"])
        self.assertFalse(R.is_restrained(target))

    def test_uncuff_unrestrained_target(self):
        target = _pc(2, "Free", wound=0)
        res = self._uncuff(_pc(1, "Captor"), target)
        self.assertFalse(res["ok"])


# ── escape + consent actions ─────────────────────────────────────────────────

class TestEscapeAction(unittest.TestCase):

    def test_strong_pc_escapes_and_persists(self):
        c = _pc(1, "Strongman", attrs={"strength": "12D"})
        R.apply_restraint(c, applied_by="X", applied_by_id=9)
        db = _StubDB()
        res = _run(R.attempt_escape_action(db, c))
        self.assertTrue(res["ok"])
        self.assertTrue(res["escaped"])
        self.assertFalse(R.is_restrained(c))
        self.assertTrue(db.saved)  # persisted the freedom

    def test_escape_when_free_noop(self):
        res = _run(R.attempt_escape_action(_StubDB(), _pc(1, "Free")))
        self.assertFalse(res["ok"])
        self.assertFalse(res["escaped"])


class TestConsentAction(unittest.TestCase):

    def test_set_and_clear_consent_persists(self):
        c = _pc(1, "Willing")
        db = _StubDB()
        res = _run(R.set_consent_action(db, c, True))
        self.assertTrue(res["ok"])
        self.assertTrue(R.restraint_consent(c))
        self.assertTrue(db.saved)
        _run(R.set_consent_action(db, c, False))
        self.assertFalse(R.restraint_consent(c))


if __name__ == "__main__":
    unittest.main()
