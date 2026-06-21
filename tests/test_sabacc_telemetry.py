"""tests/test_sabacc_telemetry.py — T3.19 telemetry for the gambling chokepoint.

Sabacc was Brian's named economy-depth gap. The credit movement already rides
``credit_flow`` (``db.log_credit`` tagged ``"sabacc"`` / ``"sabacc_rake"``) and
the gambling roll rides ``skill_check``, but neither stream can reconstruct the
WIN/CRITICAL/TIE/LOSS/FUMBLE distribution, the bet size, or the rake breakdown
(house / city tax / cartel-den) — the direct tuning signal for ``HOUSE_CUT``,
the win/loss cooldowns, and the bet bounds. A loss and a tie and a fumble all
log the SAME ``-bet`` credit delta, so the outcome split is invisible without a
dedicated emit.

This suite drives the real ``SabaccCommand.execute`` with the dice forced
deterministically and proves ONE ``gamble`` event fires per resolved hand at the
post-mutation seam, carries the outcome + bet + rake breakdown that matches the
credit ledger, honours the ``telemetry.gamble_sample`` tunable, fires on every
outcome branch, and — the load-bearing contract — NEVER disturbs the hand when
telemetry breaks. Early-return paths (zone gate / insufficient credits /
cooldown) emit nothing.

Run: python -m pytest tests/test_sabacc_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import unittest
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import sabacc_commands as sc  # noqa: E402
from parser.commands import CommandContext  # noqa: E402


def _events(ev_type="gamble"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeResult:
    """Stand-in for SkillCheckResult — only the fields execute() reads."""

    def __init__(self, roll, *, fumble=False, critical=False, pool="3D"):
        self.roll = roll
        self.pool_str = pool
        self.fumble = fumble
        self.critical_success = critical


class _FakeSession:
    def __init__(self, character):
        self.id = 1
        self.character = character
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeSessionMgr:
    async def broadcast_to_room(self, *a, **kw):
        pass


class _FakeDB:
    """Records the credit ledger writes execute() performs."""

    def __init__(self):
        self.credit_calls: list = []
        self.org_treasury_calls: list = []
        self.saves: list = []

    async def adjust_credits(self, char_id, delta, tag):
        self.credit_calls.append((char_id, delta, tag))

    async def adjust_org_treasury(self, org_id, amount):
        self.org_treasury_calls.append((org_id, amount))

    async def save_character(self, char_id, **fields):
        self.saves.append((char_id, fields))


def _char(credits=1000, attrs=None):
    return {
        "id": 7,
        "name": "Tester",
        "credits": credits,
        "room_id": 100,
        "attributes": json.dumps(attrs or {}),
    }


class SabaccTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── core driver: patch the dice + zone + economy hooks deterministically ──
    def _run(self, *, char=None, args="", player_roll=20, dealer_roll=5,
             fumble=False, critical=False, zone="chalmun's cantina",
             city_tax=(0, 0, ""), den=None):
        char = char if char is not None else _char()
        db = _FakeDB()
        ctx = CommandContext(
            session=_FakeSession(char),
            raw_input="sabacc",
            command="sabacc",
            args=args,
            args_list=[],
            switches=[],
            db=db,
            session_mgr=_FakeSessionMgr(),
        )

        async def _zone(_ctx):
            return zone

        async def _dealer(_ctx, _char):
            return (3, 0)

        async def _city_tax(_db, _room, _rake):
            return city_tax

        async def _room_den(_db, _room):
            return den

        with mock.patch.object(sc, "_get_zone_name", _zone), \
             mock.patch.object(sc, "_get_dealer_pool", _dealer), \
             mock.patch.object(sc, "_roll_flat", lambda d, p: dealer_roll), \
             mock.patch.object(
                 sc, "perform_skill_check",
                 lambda c, s, d: _FakeResult(player_roll, fumble=fumble,
                                             critical=critical)), \
             mock.patch("engine.player_cities.apply_city_tax", _city_tax), \
             mock.patch("engine.dens.get_room_den", _room_den):
            asyncio.run(sc.SabaccCommand().execute(ctx))
        return db

    # ── one event per outcome branch, envelope mirrors the ledger ─────────────
    def test_win_emits_gamble_event(self):
        db = self._run(player_roll=25, dealer_roll=5)
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["game"], "sabacc")
        self.assertEqual(e["outcome"], "win")
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["bet"], 100)            # BET_DEFAULT
        self.assertEqual(e["rake"], 10)            # max(5, 100*0.10)
        self.assertEqual(e["net"], 90)             # bet - rake
        self.assertEqual(e["city_take"], 0)
        self.assertEqual(e["den_rake"], 0)
        self.assertFalse(e["critical"])
        self.assertFalse(e["fumble"])
        self.assertEqual(e["margin"], 20)
        # The emitted net matches the credit ledger delta exactly.
        sabacc_ledger = [c for c in db.credit_calls if c[2] == "sabacc"]
        self.assertEqual(sabacc_ledger[0][1], 90)

    def test_loss_emits_gamble_event(self):
        db = self._run(player_roll=3, dealer_roll=20)
        e = _events()[0]
        self.assertEqual(e["outcome"], "loss")
        self.assertEqual(e["net"], -100)
        self.assertEqual(e["rake"], 0)             # house takes no rake on a loss
        self.assertEqual(e["den_rake"], 0)
        sabacc_ledger = [c for c in db.credit_calls if c[2] == "sabacc"]
        self.assertEqual(sabacc_ledger[0][1], -100)

    def test_critical_outcome_recorded(self):
        e = self._run(player_roll=25, dealer_roll=5, critical=True)
        evs = _events()
        self.assertEqual(evs[0]["outcome"], "critical")
        self.assertTrue(evs[0]["critical"])
        self.assertEqual(evs[0]["net"], 90)        # crit pays same as win (no jackpot)

    def test_fumble_outcome_recorded(self):
        self._run(player_roll=25, dealer_roll=5, fumble=True)
        e = _events()[0]
        self.assertEqual(e["outcome"], "fumble")   # fumble loses regardless of rolls
        self.assertTrue(e["fumble"])
        self.assertEqual(e["net"], -100)

    def test_tie_is_house_win(self):
        e = self._run(player_roll=12, dealer_roll=12)
        ev = _events()[0]
        self.assertEqual(ev["outcome"], "tie")
        self.assertEqual(ev["net"], -100)          # house wins ties
        self.assertEqual(ev["margin"], 0)

    # ── rake breakdown: city tax + cartel-den routing are captured ────────────
    def test_city_take_recorded(self):
        self._run(player_roll=25, dealer_roll=5, city_tax=(3, 7, "Mos Eisley"))
        e = _events()[0]
        self.assertEqual(e["city_take"], 3)

    def test_den_rake_recorded(self):
        db = self._run(player_roll=25, dealer_roll=5,
                       den={"org_id": 4, "org_code": "HUTT"})
        e = _events()[0]
        # rake_to_org = house_rake (10) - city_take (0) = 10
        self.assertEqual(e["den_rake"], 10)
        # and it really routed to the org treasury + system rake ledger
        self.assertEqual(db.org_treasury_calls, [(4, 10)])
        rake_ledger = [c for c in db.credit_calls if c[2] == "sabacc_rake"]
        self.assertEqual(rake_ledger[0][1], 10)

    # ── sampling honours the tunable ──────────────────────────────────────────
    def test_sample_zero_suppresses_event_not_the_hand(self):
        tunables._TUNABLES["telemetry.gamble_sample"] = 0.0
        db = self._run(player_roll=25, dealer_roll=5)
        self.assertEqual(len(_events()), 0)
        # The hand still resolved — credits moved despite no telemetry.
        self.assertEqual([c for c in db.credit_calls if c[2] == "sabacc"][0][1], 90)

    def test_sample_default_captures(self):
        self._run(player_roll=25, dealer_roll=5)   # no tunable loaded → 1.0
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the hand ───────────────────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            db = self._run(player_roll=25, dealer_roll=5)
        # No crash; the hand resolved and the credit ledger was written.
        self.assertEqual([c for c in db.credit_calls if c[2] == "sabacc"][0][1], 90)

    # ── early-return paths emit nothing (and touch no credits) ────────────────
    def test_non_cantina_zone_no_emit(self):
        db = self._run(zone="the dusty spaceport", player_roll=25, dealer_roll=5)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.credit_calls, [])

    def test_insufficient_credits_no_emit(self):
        db = self._run(char=_char(credits=10), args="500",
                       player_roll=25, dealer_roll=5)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.credit_calls, [])

    def test_cooldown_blocks_no_emit(self):
        recent = {"last_sabacc": time.time()}   # just played → still on cooldown
        db = self._run(char=_char(attrs=recent), player_roll=25, dealer_roll=5)
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.credit_calls, [])


if __name__ == "__main__":
    unittest.main()
