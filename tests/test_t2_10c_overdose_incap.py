# -*- coding: utf-8 -*-
"""
tests/test_t2_10c_overdose_incap.py

T2.10.c — the stim force/overdose path (design §3.6 next-iteration) plus
Brian's decision (2026-06-05): a *failed* overdose incapacitates the
target. Incapacitated is a recoverable wound level, not death.

Surface
-------
1. TestOverdoseConsequence — _execute_stim_roll with offer overdose=True:
   - failed overdose -> wound becomes INCAPACITATED (4)
   - fumbled overdose -> wound floored at INCAPACITATED
   - successful overdose -> buff applied, no incapacitation
   - +5 difficulty applied to the roll on overdose
2. TestNonOverdoseRegression — a plain failed stimpack does NOT
   incapacitate (the headline consequence is overdose-gated).
3. TestForceSwitchParsing — StimCommand.execute:
   - force switch over an active stim proceeds and stages overdose=True
   - no force over an active stim still refuses (the §3.6 block holds)

The skill roll is deterministically controlled by patching
engine.skill_checks.perform_skill_check (imported lazily inside
_execute_stim_roll, so patching the source module is what takes effect).
"""
from __future__ import annotations

import asyncio
import json
import types
import unittest
from unittest.mock import MagicMock, patch

import parser.medical_commands as mc

_WL_INCAPACITATED = 4


def _run(coro):
    return asyncio.run(coro)


# ─── Fixtures (mirror tests/test_srb1b_stim_consumable_wiring.py) ────────────

class _FakeDB:
    def __init__(self):
        self.writes = []
        self.chars = {}

    def add_char(self, char):
        self.chars[char["id"]] = char

    async def save_character(self, char_id, **kwargs):
        self.writes.append((char_id, kwargs))
        if char_id in self.chars:
            for k, v in kwargs.items():
                self.chars[char_id][k] = v

    def wound_writes(self):
        return [kw["wound_level"] for _, kw in self.writes if "wound_level" in kw]


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, msg):
        self.sent.append(msg)

    def text(self):
        return "\n".join(self.sent)


class _FakeSessionMgr:
    def __init__(self, sessions):
        self.sessions = list(sessions)

    def sessions_in_room(self, room_id, *, source_char=None):
        for s in self.sessions:
            if s.character and s.character.get("room_id") == room_id:
                yield s


def _make_char(*, char_id, name, room_id=1, skills=None,
               attributes=None, consumables=None, wound_level=0):
    attrs = dict(attributes or {})
    if consumables is not None:
        merged = dict(attrs.get("consumables", {}))
        merged.update(consumables)
        attrs["consumables"] = merged
    return {
        "id": char_id,
        "name": name,
        "room_id": room_id,
        "skills": json.dumps(skills or {}),
        "attributes": json.dumps(attrs),
        "wound_level": wound_level,
        "credits": 5000,
    }


def _make_ctx(db, session, args="", *, session_mgr=None, switches=None):
    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.session_mgr = session_mgr
    ctx.args = args
    ctx.switches = switches or []
    return ctx


def _result(*, success, fumble=False, margin=0):
    return types.SimpleNamespace(success=success, fumble=fumble, margin=margin)


def _offer(*, medic_session, overdose, consumable="stimpack", is_self=False):
    return {
        "medic_id": medic_session.character["id"],
        "medic_session": medic_session,
        "medic_name": medic_session.character["name"],
        "consumable_key": consumable,
        "is_self": is_self,
        "overdose": overdose,
        "offered_at": 0.0,
    }


def _clear_pending():
    mc._pending_stims.clear()


# ═══════════════════════════════════════════════════════════════════════════
# 1. Overdose consequence
# ═══════════════════════════════════════════════════════════════════════════

class TestOverdoseConsequence(unittest.TestCase):

    def setUp(self):
        _clear_pending()
        self.db = _FakeDB()
        self.medic = _make_char(
            char_id=1, name="Medic",
            skills={"first aid": 6},
            consumables={"stimpack": 5},
        )
        self.target = _make_char(char_id=2, name="Patient", wound_level=0)
        self.db.add_char(self.medic)
        self.db.add_char(self.target)
        self.medic_sess = _FakeSession(self.medic)
        self.target_sess = _FakeSession(self.target)
        self.ctx = _make_ctx(self.db, self.medic_sess)

    @patch("engine.skill_checks.perform_skill_check")
    def test_failed_overdose_incapacitates(self, mock_roll):
        mock_roll.return_value = _result(success=False, margin=-4)
        offer = _offer(medic_session=self.medic_sess, overdose=True)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        self.assertEqual(self.target["wound_level"], _WL_INCAPACITATED)
        self.assertIn(_WL_INCAPACITATED, self.db.wound_writes())
        self.assertIn("incapacitated", self.target_sess.text().lower())

    @patch("engine.skill_checks.perform_skill_check")
    def test_fumbled_overdose_floors_at_incapacitated(self, mock_roll):
        mock_roll.return_value = _result(success=False, fumble=True, margin=-9)
        offer = _offer(medic_session=self.medic_sess, overdose=True)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        # max(0 + 2 fumble, INCAP) == INCAP
        self.assertGreaterEqual(self.target["wound_level"], _WL_INCAPACITATED)

    @patch("engine.skill_checks.perform_skill_check")
    def test_successful_overdose_does_not_incapacitate(self, mock_roll):
        mock_roll.return_value = _result(success=True, margin=3)
        offer = _offer(medic_session=self.medic_sess, overdose=True)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        self.assertEqual(self.target["wound_level"], 0)
        # buff was applied
        from engine.buffs import get_active_stim
        self.assertIsNotNone(get_active_stim(self.target))

    @patch("engine.skill_checks.perform_skill_check")
    def test_overdose_adds_five_difficulty(self, mock_roll):
        mock_roll.return_value = _result(success=True, margin=1)
        offer = _offer(medic_session=self.medic_sess, overdose=True)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        # stimpack base difficulty is 10; overdose -> 15.
        called_difficulty = mock_roll.call_args.args[2]
        self.assertEqual(called_difficulty, 15)

    @patch("engine.skill_checks.perform_skill_check")
    def test_non_overdose_difficulty_unchanged(self, mock_roll):
        mock_roll.return_value = _result(success=True, margin=1)
        offer = _offer(medic_session=self.medic_sess, overdose=False)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        self.assertEqual(mock_roll.call_args.args[2], 10)


# ═══════════════════════════════════════════════════════════════════════════
# 2. Non-overdose regression — a plain failed stim doesn't incapacitate
# ═══════════════════════════════════════════════════════════════════════════

class TestNonOverdoseRegression(unittest.TestCase):

    def setUp(self):
        _clear_pending()
        self.db = _FakeDB()
        self.medic = _make_char(
            char_id=1, name="Medic", skills={"first aid": 6},
            consumables={"stimpack": 5})
        self.target = _make_char(char_id=2, name="Patient", wound_level=0)
        self.db.add_char(self.medic)
        self.db.add_char(self.target)
        self.medic_sess = _FakeSession(self.medic)
        self.target_sess = _FakeSession(self.target)
        self.ctx = _make_ctx(self.db, self.medic_sess)

    @patch("engine.skill_checks.perform_skill_check")
    def test_plain_failed_stimpack_no_incap(self, mock_roll):
        mock_roll.return_value = _result(success=False, margin=-2)
        offer = _offer(medic_session=self.medic_sess, overdose=False)
        _run(mc._execute_stim_roll(
            self.ctx, self.target_sess, self.target, offer))
        self.assertEqual(self.target["wound_level"], 0)
        self.assertEqual(self.db.wound_writes(), [])


# ═══════════════════════════════════════════════════════════════════════════
# 3. Force-switch parsing in StimCommand.execute
# ═══════════════════════════════════════════════════════════════════════════

class TestForceSwitchParsing(unittest.TestCase):

    def setUp(self):
        _clear_pending()
        self.db = _FakeDB()
        self.medic = _make_char(
            char_id=1, name="Medic", room_id=7,
            skills={"first aid": 6}, consumables={"stimpack": 5})
        self.target = _make_char(char_id=2, name="Patient", room_id=7)
        # give the target an already-active stim
        from engine.buffs import add_buff
        add_buff(self.target, "stimpack")
        self.db.add_char(self.medic)
        self.db.add_char(self.target)
        self.medic_sess = _FakeSession(self.medic)
        self.target_sess = _FakeSession(self.target)
        self.mgr = _FakeSessionMgr([self.medic_sess, self.target_sess])

    def test_active_stim_precondition(self):
        from engine.buffs import get_active_stim
        self.assertIsNotNone(
            get_active_stim(self.target),
            "test setup: target should have an active stim")

    def test_force_over_active_stim_stages_overdose(self):
        ctx = _make_ctx(self.db, self.medic_sess, args="Patient",
                        session_mgr=self.mgr, switches=["force"])
        _run(mc.StimCommand().execute(ctx))
        # an offer was staged for the target, flagged overdose
        offer = mc._pending_stims.get(self.target["id"])
        self.assertIsNotNone(offer, "force should stage an offer, not refuse")
        self.assertTrue(offer.get("overdose"))
        # and the refuse line was NOT sent
        self.assertNotIn("wait for it to clear",
                         self.medic_sess.text().lower())

    def test_no_force_over_active_stim_refuses(self):
        ctx = _make_ctx(self.db, self.medic_sess, args="Patient",
                        session_mgr=self.mgr, switches=[])
        _run(mc.StimCommand().execute(ctx))
        self.assertIsNone(mc._pending_stims.get(self.target["id"]),
                          "without force the block should hold (no offer)")
        self.assertIn("already has an active stim",
                      self.medic_sess.text().lower())


if __name__ == "__main__":
    unittest.main()
