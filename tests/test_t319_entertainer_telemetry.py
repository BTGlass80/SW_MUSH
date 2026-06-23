# -*- coding: utf-8 -*-
"""tests/test_t319_entertainer_telemetry.py — T3.19 telemetry for the
entertainer (cantina) credit faucet.

The `perform` payout already rides the credit ledger (``adjust_credits`` tagged
``"entertainer"``) and the Persuasion / Musical-Instrument roll rides
``skill_check``, but neither stream can reconstruct the outcome split
(critical / success / partial / fail), the fatigue-bumped difficulty +
``fatigue_count`` (diminishing returns), the live-audience hub bonus, or the
cantina-brawl 2x flag — the direct tuning signal for the pay bounds, the
audience cap, the fatigue penalty, and the perform cooldowns. A partial-pay
perform and a flat-pay perform can log the SAME ``entertainer`` delta, so the
outcome split is invisible without a dedicated emit.

This suite drives the real ``PerformCommand.execute`` with the roll forced
deterministically and proves ONE ``entertainer_perform`` event fires per
resolved performance at the post-dispatch seam, carries the outcome + payout
that matches the credit ledger, records the audience / fatigue / brawl depth,
honours the ``telemetry.entertainer_sample`` tunable, fires on every outcome
branch, and — the load-bearing contract — NEVER disturbs the performance when
telemetry breaks. Early-return paths (zone gate / cooldown) emit nothing.

Run: python -m pytest tests/test_t319_entertainer_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from unittest import mock

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import skill_checks  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import entertainer_commands as ec  # noqa: E402
from parser.commands import CommandContext  # noqa: E402


def _events(ev_type="entertainer_perform"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeResult:
    """Stand-in for SkillCheckResult — only the fields execute() reads."""

    def __init__(self, *, success, margin, roll=15, critical=False,
                 fumble=False, pool="3D"):
        self.success = success
        self.critical_success = critical
        self.margin = margin
        self.roll = roll
        self.pool_str = pool
        self.fumble = fumble


class _FakeSession:
    def __init__(self, character):
        self.id = 1
        self.character = character
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeSessionMgr:
    """sessions_in_room is SYNC (the real one is); broadcast is async."""

    def __init__(self, audience_ids=None):
        # ids of OTHER players present (the performer is added by the test);
        # _count_audience excludes the performer by id.
        self._audience_ids = list(audience_ids or [])

    def sessions_in_room(self, room_id, *, source_char=None):
        sessions = [_FakeSession({"id": 7})]  # the performer
        for cid in self._audience_ids:
            sessions.append(_FakeSession({"id": cid}))
        return sessions

    async def broadcast_to_room(self, *a, **kw):
        pass


class _FakeDB:
    """Records the credit ledger writes execute() performs."""

    def __init__(self, fatigue=(0, 0)):
        self.credit_calls: list = []
        self.saves: list = []
        self._fatigue = fatigue

    async def get_perform_fatigue(self, char_id):
        return self._fatigue

    async def set_perform_fatigue(self, **kw):
        pass

    async def adjust_credits(self, char_id, delta, tag):
        self.credit_calls.append((char_id, delta, tag))
        return 1000 + delta  # new balance

    async def save_character(self, char_id, **fields):
        self.saves.append((char_id, fields))

    async def get_morale_aura(self, room_id):
        return None

    async def set_morale_aura(self, **kw):
        pass


def _char(credits=1000, attrs=None, skills=None):
    return {
        "id": 7,
        "name": "Tester",
        "credits": credits,
        "room_id": 100,
        "attributes": json.dumps(attrs or {}),
        "skills": json.dumps(skills or {}),
    }


class _FakeWEM:
    def __init__(self, brawl=False):
        self._brawl = brawl

    def get_status(self):
        return [{"type": "cantina_brawl"}] if self._brawl else []


class EntertainerTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── core driver: patch the roll + zone + brawl deterministically ──────────
    def _run(self, *, char=None, success=True, margin=5, critical=False,
             fumble=False, zone="chalmun's cantina", db=None, brawl=False,
             audience_ids=None):
        char = char if char is not None else _char()
        db = db if db is not None else _FakeDB()
        ctx = CommandContext(
            session=_FakeSession(char),
            raw_input="perform",
            command="perform",
            args="",
            args_list=[],
            switches=[],
            db=db,
            session_mgr=_FakeSessionMgr(audience_ids=audience_ids),
        )

        async def _zone(_ctx):
            return zone

        result = _FakeResult(success=success, margin=margin,
                             critical=critical, fumble=fumble)

        with mock.patch.object(ec, "_get_room_zone_name", _zone), \
             mock.patch.object(skill_checks, "perform_skill_check",
                               lambda c, s, d: result), \
             mock.patch("engine.world_events.get_world_event_manager",
                        lambda: _FakeWEM(brawl=brawl)):
            asyncio.run(ec.PerformCommand().execute(ctx))
        return db

    def _ent_ledger(self, db):
        return [c for c in db.credit_calls if c[2] == "entertainer"]

    # ── one event per outcome branch, payout mirrors the ledger ───────────────
    def test_success_emits_event(self):
        db = self._run(success=True, margin=5)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["outcome"], "success")
        self.assertEqual(e["char_id"], 7)
        self.assertGreater(e["payout"], 0)
        self.assertEqual(e["skill"], "persuasion")
        self.assertEqual(e["margin"], 5)
        self.assertEqual(e["difficulty"], 10)       # no fatigue → base
        self.assertEqual(e["fatigue_count"], 0)
        self.assertEqual(e["audience"], 0)
        self.assertFalse(e["brawl"])
        self.assertFalse(e["fumble"])
        # emitted payout matches the entertainer ledger delta exactly
        self.assertEqual(self._ent_ledger(db)[0][1], e["payout"])

    def test_critical_emits_event(self):
        db = self._run(success=True, critical=True, margin=12)
        e = _events()[0]
        self.assertEqual(e["outcome"], "critical")
        # crit pay band is 250..500 (before audience/brawl)
        self.assertGreaterEqual(e["payout"], ec._CRIT_PAY_MIN)
        self.assertLessEqual(e["payout"], ec._CRIT_PAY_MAX)
        self.assertEqual(self._ent_ledger(db)[0][1], e["payout"])

    def test_partial_emits_event(self):
        db = self._run(success=False, margin=-2)   # >= -4 → partial
        e = _events()[0]
        self.assertEqual(e["outcome"], "partial")
        self.assertEqual(e["payout"], ec._PARTIAL_PAY)
        self.assertEqual(self._ent_ledger(db)[0][1], ec._PARTIAL_PAY)

    def test_fail_emits_zero_payout_event(self):
        db = self._run(success=False, margin=-8)    # < -4 → fail
        e = _events()[0]
        self.assertEqual(e["outcome"], "fail")
        self.assertEqual(e["payout"], 0)
        self.assertFalse(e["fumble"])
        # a failed perform pays nothing — no entertainer ledger write
        self.assertEqual(self._ent_ledger(db), [])

    def test_fumble_recorded_on_fail(self):
        self._run(success=False, margin=-8, fumble=True)
        e = _events()[0]
        self.assertEqual(e["outcome"], "fail")
        self.assertTrue(e["fumble"])

    # ── depth the ledger can't rejoin ─────────────────────────────────────────
    def test_audience_recorded_and_lifts_payout(self):
        # base normal-success payout with margin 5 (no audience) for comparison
        base = self._run(success=True, margin=5)
        base_pay = _events()[0]["payout"]
        telemetry.reset()
        # 3 other players present → audience 3 → +45% take, recorded
        db = self._run(success=True, margin=5, audience_ids=[2, 3, 4])
        e = _events()[0]
        self.assertEqual(e["audience"], 3)
        self.assertEqual(e["payout"], int(base_pay * ec.audience_multiplier(3)))
        self.assertEqual(self._ent_ledger(db)[0][1], e["payout"])

    def test_brawl_flag_recorded_and_doubles_payout(self):
        base = self._run(success=True, margin=5)
        base_pay = _events()[0]["payout"]
        telemetry.reset()
        e = self._run(success=True, margin=5, brawl=True)
        ev = _events()[0]
        self.assertTrue(ev["brawl"])
        self.assertEqual(ev["payout"], base_pay * 2)

    def test_fatigue_recorded_in_difficulty(self):
        # two prior performs in-window → +6 difficulty (3 pips each)
        future = time.time() + 10_000
        db = _FakeDB(fatigue=(future, 2))
        self._run(success=True, margin=5, db=db)
        e = _events()[0]
        self.assertEqual(e["fatigue_count"], 2)
        self.assertEqual(e["difficulty"],
                         ec._PERFORM_DIFFICULTY + 2 * ec._FATIGUE_PENALTY_PIPS)

    def test_skill_musical_instrument_recorded(self):
        char = _char(skills={"musical instrument": "4D"})
        self._run(success=True, margin=5, char=char)
        self.assertEqual(_events()[0]["skill"], "musical instrument")

    # ── sampling honours the tunable ──────────────────────────────────────────
    def test_sample_zero_suppresses_event_not_the_payout(self):
        tunables._TUNABLES["telemetry.entertainer_sample"] = 0.0
        db = self._run(success=True, margin=5)
        self.assertEqual(len(_events()), 0)
        # the performance still resolved — credits moved despite no telemetry
        self.assertGreater(self._ent_ledger(db)[0][1], 0)

    def test_sample_default_captures(self):
        self._run(success=True, margin=5)   # no tunable loaded → 1.0
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the performance ────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            db = self._run(success=True, margin=5)
        # no crash; the perform resolved and the credit ledger was written
        self.assertGreater(self._ent_ledger(db)[0][1], 0)

    # ── early-return paths emit nothing (and touch no credits) ────────────────
    def test_non_cantina_zone_no_emit(self):
        db = self._run(zone="the dusty spaceport", success=True, margin=5)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.credit_calls, [])

    def test_cooldown_blocks_no_emit(self):
        recent = {"last_perform": time.time()}   # just performed → on cooldown
        db = self._run(char=_char(attrs=recent), success=True, margin=5)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.credit_calls, [])

    # ── exactly one event per resolved performance ────────────────────────────
    def test_single_event_per_perform(self):
        self._run(success=True, margin=5)
        self.assertEqual(len(_events()), 1)


if __name__ == "__main__":
    unittest.main()
