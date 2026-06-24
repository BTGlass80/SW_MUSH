"""tests/test_t319_medical_telemetry.py — T3.19 telemetry for the player-healer
medical-services economy (parser/medical_commands.py).

A SUCCESSFUL ``healaccept`` moves credits through the ``credit_flow`` chokepoint
(two ``medical``-tagged ``adjust_credits`` rows: the patient debit + the healer
credit), but those two ledger rows can't be rejoined offline into a single
healer→patient service transaction — and the **partial / failed** treatments
move NO credits at all, so ``credit_flow`` never sees them. So the heal-for-hire
market is mostly dark: the healer success rate, the rate-vs-wound-severity
distribution, and the partial/fail share are all unreconstructable. This drop
adds ONE fail-open, sample-tunable ``medical_treatment`` event at the resolution
seam of ``HealAcceptCommand.execute``.

This suite drives the REAL ``HealAcceptCommand.execute`` (a populated
``_pending_heals`` offer + faked sessions/db + a controlled skill result) and
proves: exactly one event per resolved treatment for every outcome
(critical/success/partial/fail/fumble); the envelope matches the wound move +
the ledger legs; the partial/fail events are the ONLY record of a flow
``credit_flow`` can't see; the insufficient-credits abort emits nothing; the
``telemetry.medical_sample`` tunable is honoured; and — the load-bearing
contract — a broken sink NEVER disturbs the completed treatment.

Run: python -m pytest tests/test_t319_medical_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import medical_commands as mc  # noqa: E402
from parser.commands import CommandContext  # noqa: E402

REPO = Path(PROJECT_ROOT)


def _events(ev_type="medical_treatment"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeResult:
    """Stand-in for engine.skill_checks.SkillCheckResult."""

    def __init__(self, *, success=True, critical_success=False, fumble=False,
                 margin=0, roll=15, pool_str="4D"):
        self.success = success
        self.critical_success = critical_success
        self.fumble = fumble
        self.margin = margin
        self.roll = roll
        self.pool_str = pool_str


class _FakeSession:
    def __init__(self, character):
        self.id = character["id"]
        self.character = character
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeSessionMgr:
    async def broadcast_to_room(self, *a, **kw):
        pass


class _FakeDB:
    """Records the treatment's ledger + wound writes."""

    def __init__(self, *, debit_returns_none=False):
        self.credit_calls: list = []
        self.saved: list = []
        self._debit_returns_none = debit_returns_none
        self._balances = {3: 0, 7: 10_000}

    async def adjust_credits(self, char_id, delta, tag, allow_negative=True):
        self.credit_calls.append((char_id, delta, tag))
        # The atomic patient-debit guard returns None when it would go
        # negative; the real path then aborts before paying the healer.
        if (self._debit_returns_none and tag == "medical"
                and delta < 0 and allow_negative is False):
            return None
        self._balances[char_id] = self._balances.get(char_id, 0) + delta
        return self._balances[char_id]

    async def save_character(self, char_id, **kwargs):
        self.saved.append((char_id, kwargs))
        return True


class MedicalTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        mc._pending_heals.clear()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()
        mc._pending_heals.clear()

    # ── core driver: a populated offer + the real execute ─────────────────────
    def _run_accept(self, *, result, patient_wound=2, rate=200,
                    patient_credits=10_000, room=100, skill="first aid",
                    debit_returns_none=False, same_room=True):
        # `char` = the patient (calls "healaccept"); healer = the giver.
        patient = {"id": 7, "name": "Bob", "credits": patient_credits,
                   "room_id": room, "wound_level": patient_wound}
        healer = {"id": 3, "name": "Vera",
                  "room_id": room if same_room else (room + 1)}
        patient_sess = _FakeSession(patient)
        healer_sess = _FakeSession(healer)
        db = _FakeDB(debit_returns_none=debit_returns_none)
        ctx = CommandContext(
            session=patient_sess, raw_input="healaccept",
            command="healaccept", args="", args_list=[],
            switches=[], db=db, session_mgr=_FakeSessionMgr(),
        )
        mc._pending_heals[7] = {
            "healer_session": healer_sess,
            "rate": rate,
            "skill_name": skill,
            "difficulty": 11,
            "timestamp": time.time(),
        }
        with mock.patch("engine.skill_checks.perform_skill_check",
                        return_value=result):
            asyncio.run(mc.HealAcceptCommand().execute(ctx))
        return db

    # ── success: one event, envelope matches the wound + ledger move ──────────
    def test_success_emits_one_event(self):
        db = self._run_accept(result=_FakeResult(success=True, roll=14))
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["outcome"], "success")
        self.assertEqual(e["healer_char"], 3)
        self.assertEqual(e["patient_char"], 7)
        self.assertEqual(e["room_id"], 100)
        self.assertEqual(e["skill"], "first aid")
        self.assertEqual(e["difficulty"], 11)     # _HEAL_DIFFICULTY[2]
        self.assertEqual(e["roll"], 14)
        self.assertEqual(e["wound_before"], 2)
        self.assertEqual(e["wound_after"], 1)     # one step healed
        self.assertEqual(e["rate"], 200)
        self.assertEqual(e["paid"], 200)
        # The ledger legs the event re-links: patient debit + healer credit.
        self.assertIn((7, -200, "medical"), db.credit_calls)
        self.assertIn((3, 200, "medical"), db.credit_calls)
        self.assertEqual(db.saved, [(7, {"wound_level": 1})])

    def test_critical_heals_two_steps(self):
        e = (self._run_accept(
            result=_FakeResult(success=True, critical_success=True, roll=20))
            and _events()[0])
        self.assertEqual(e["outcome"], "critical")
        self.assertEqual(e["wound_before"], 2)
        self.assertEqual(e["wound_after"], 0)     # two steps → Healthy
        self.assertEqual(e["paid"], 200)

    # ── partial / fail: the ONLY record of a credit_flow-invisible flow ───────
    def test_partial_emits_event_and_is_dark_to_credit_flow(self):
        db = self._run_accept(
            result=_FakeResult(success=False, margin=-2, roll=9))
        e = _events()[0]
        self.assertEqual(e["outcome"], "partial")
        self.assertEqual(e["paid"], 0)
        self.assertEqual(e["wound_after"], 2)     # unchanged
        # No credits moved → credit_flow would record NOTHING; this is the sole
        # signal that the (paid-for-nothing) treatment was even attempted.
        self.assertEqual(db.credit_calls, [])
        self.assertEqual(db.saved, [])

    def test_failure_emits_event_no_payment(self):
        db = self._run_accept(
            result=_FakeResult(success=False, margin=-10, roll=4))
        e = _events()[0]
        self.assertEqual(e["outcome"], "fail")
        self.assertEqual(e["paid"], 0)
        self.assertEqual(db.credit_calls, [])

    def test_fumble_outcome_tagged(self):
        e = (self._run_accept(
            result=_FakeResult(success=False, margin=-12, fumble=True))
            and _events()[0])
        self.assertEqual(e["outcome"], "fumble")
        self.assertEqual(e["paid"], 0)

    # ── insufficient-credits abort: no completed treatment, no event ──────────
    def test_debit_abort_no_emit(self):
        # Passes the session-cache check (10k >= rate) but the atomic DB debit
        # guard returns None → abort before paying the healer → no event.
        db = self._run_accept(result=_FakeResult(success=True),
                              debit_returns_none=True)
        self.assertEqual(len(_events()), 0)
        # The healer was never paid.
        self.assertNotIn((3, 200, "medical"), db.credit_calls)

    # ── non-completing paths emit nothing ─────────────────────────────────────
    def test_no_pending_offer_no_emit(self):
        patient = {"id": 7, "name": "Bob", "credits": 5_000,
                   "room_id": 100, "wound_level": 2}
        ctx = CommandContext(
            session=_FakeSession(patient), raw_input="healaccept",
            command="healaccept", args="", args_list=[], switches=[],
            db=_FakeDB(), session_mgr=_FakeSessionMgr(),
        )
        asyncio.run(mc.HealAcceptCommand().execute(ctx))
        self.assertEqual(len(_events()), 0)

    def test_healer_left_room_no_emit(self):
        self._run_accept(result=_FakeResult(success=True), same_room=False)
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable, the treatment still lands ───────────────
    def test_sample_zero_suppresses_event_not_the_heal(self):
        tunables._TUNABLES["telemetry.medical_sample"] = 0.0
        db = self._run_accept(result=_FakeResult(success=True))
        self.assertEqual(len(_events()), 0)
        # The wound was still healed + the healer still paid.
        self.assertEqual(db.saved, [(7, {"wound_level": 1})])
        self.assertIn((3, 200, "medical"), db.credit_calls)

    def test_sample_default_captures(self):
        self._run_accept(result=_FakeResult(success=True))  # no tunable → 1.0
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the completed treatment ────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            db = self._run_accept(result=_FakeResult(success=True))
        # No crash; the heal resolved and the ledger + wound were written.
        self.assertEqual(db.saved, [(7, {"wound_level": 1})])
        self.assertIn((3, 200, "medical"), db.credit_calls)

    # ── helper unit: field schema + fail-open coercion ────────────────────────
    def test_helper_schema(self):
        mc._emit_medical_telemetry(
            healer_id=3, patient_id=7, room_id=42, skill="medicine",
            difficulty=16, roll=18, outcome="success", wound_before=4,
            wound_after=3, rate=500, paid=500)
        e = _events()[0]
        self.assertEqual(e["healer_char"], 3)
        self.assertEqual(e["patient_char"], 7)
        self.assertEqual(e["skill"], "medicine")
        self.assertEqual(e["wound_after"], 3)
        self.assertEqual(e["paid"], 500)

    def test_helper_coerces_none_ids(self):
        mc._emit_medical_telemetry(
            healer_id=None, patient_id=None, room_id=None, skill="first aid",
            difficulty=11, roll=10, outcome="fail", wound_before=2,
            wound_after=2, rate=0, paid=0)
        e = _events()[0]
        self.assertEqual(e["healer_char"], 0)
        self.assertEqual(e["patient_char"], 0)

    # ── seam wired + tunable registered (source pins) ─────────────────────────
    def test_seam_calls_helper(self):
        src = (REPO / "parser" / "medical_commands.py").read_text(
            encoding="utf-8")
        self.assertIn("_emit_medical_telemetry(", src)
        self.assertIn("telemetry.medical_sample", src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.medical_sample:", ty)


if __name__ == "__main__":
    unittest.main()
