"""tests/test_t319_cp_spend_telemetry.py — T3.19 telemetry for the CP SINK
(character advancement via ``train``, parser/cp_commands.py).

The CP economy already telemeters its FAUCET (``telemetry.emit_cp_income`` — every
Character-Point income source, wired in ``engine/cp_engine.py``) but had NO sink
emitter: ``train`` spends CP to raise a skill pip — the dominant deliberate CP
sink — and nothing recorded the spend, so the income half could not be rejoined
offline against the spend half. This drop adds ONE fail-open, sample-tunable
``cp_spend`` event at the resolution seam of ``TrainCommand.execute``, AFTER the
advance is saved.

This suite drives the REAL ``TrainCommand.execute`` (a fixture character loaded
through ``Character.from_db_dict`` + faked sessions/db, with the guild-discount
multiplier + narrative log patched) and proves: exactly one event per successful
train with the right envelope (source/skill/cost/dice/cp_remaining/pool
transition); the ``dice`` cost basis tracks the pool size; the guild-discount flag
is recorded; every refusal (insufficient CP / unknown skill / Force skill / empty
arg / not logged in) emits nothing; the ``telemetry.cp_spend_sample`` tunable is
honoured; and — the load-bearing contract — a broken sink NEVER disturbs the
completed advancement.

Run: python -m pytest tests/test_t319_cp_spend_telemetry.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser import cp_commands as cpc  # noqa: E402
from parser.commands import CommandContext  # noqa: E402

REPO = Path(PROJECT_ROOT)


def _events(ev_type="cp_spend"):
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r["ev"] == ev_type]


class _FakeSession:
    def __init__(self, character):
        self.id = (character or {}).get("id") if character else None
        self.character = character
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)


class _FakeDB:
    """Serves the fixture character row + records the advancement save."""

    def __init__(self, char_row):
        self._char_row = char_row
        self.saved: list = []

    async def get_character(self, char_id):
        return dict(self._char_row) if self._char_row else None

    async def save_character(self, char_id, **kwargs):
        self.saved.append((char_id, kwargs))
        return True


class CpSpendTelemetryTests(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    # ── core driver: a fixture char + the real TrainCommand.execute ───────────
    def _run_train(self, *, skill_arg="blaster", cp=10, dex="3D",
                   skills=None, multiplier=1.0):
        if skills is None:
            skills = {"blaster": "1D"}
        char_session_dict = {"id": 7, "name": "Bob", "character_points": cp}
        char_row = {
            "id": 7, "name": "Bob", "character_points": cp,
            "credits": 1000, "room_id": 100,
            "attributes": json.dumps({"dexterity": dex}),
            "skills": json.dumps(skills),
        }
        sess = _FakeSession(char_session_dict)
        db = _FakeDB(char_row)
        ctx = CommandContext(
            session=sess, raw_input=f"train {skill_arg}",
            command="train", args=skill_arg, args_list=skill_arg.split(),
            switches=[], db=db, session_mgr=None,
        )
        with mock.patch("engine.organizations.get_guild_cp_multiplier",
                        new=mock.AsyncMock(return_value=multiplier)), \
                mock.patch("engine.narrative.log_action",
                           new=mock.AsyncMock(return_value=None)):
            asyncio.run(cpc.TrainCommand().execute(ctx))
        return db, sess

    # ── success: one event, envelope matches the advance + CP spend ───────────
    def test_train_emits_one_cp_spend_event(self):
        db, _ = self._run_train()  # dex 3D + blaster 1D = 4D pool → cost 4
        evs = _events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["source"], "train")
        self.assertEqual(e["char_id"], 7)
        self.assertEqual(e["skill"], "blaster")
        self.assertEqual(e["attribute"], "dexterity")
        self.assertEqual(e["cost"], 4)
        self.assertEqual(e["dice"], 4)          # WEG total-dice cost basis
        self.assertEqual(e["cp_remaining"], 6)  # 10 - 4
        self.assertEqual(e["old_pool"], "4D")
        self.assertEqual(e["new_pool"], "4D+1")
        self.assertFalse(e["guild_discount"])
        # The advance committed: CP debited + skills persisted.
        self.assertEqual(len(db.saved), 1)
        cid, kwargs = db.saved[0]
        self.assertEqual(cid, 7)
        self.assertEqual(kwargs["character_points"], 6)

    def test_dice_reflects_pool_size(self):
        # dex 4D + blaster 2D = 6D pool → cost 6, dice 6, new pool 6D+1.
        db, _ = self._run_train(dex="4D", skills={"blaster": "2D"}, cp=10)
        e = _events()[0]
        self.assertEqual(e["dice"], 6)
        self.assertEqual(e["cost"], 6)
        self.assertEqual(e["new_pool"], "6D+1")
        self.assertEqual(e["cp_remaining"], 4)

    # ── guild discount: cost reduced, flag set, dice basis unchanged ──────────
    def test_guild_discount_flagged(self):
        db, _ = self._run_train(multiplier=0.8)  # max(1,int(4*0.8)) = 3
        e = _events()[0]
        self.assertEqual(e["dice"], 4)             # pre-discount cost basis
        self.assertEqual(e["cost"], 3)             # what was actually paid
        self.assertTrue(e["guild_discount"])
        self.assertEqual(e["cp_remaining"], 7)     # 10 - 3
        self.assertEqual(db.saved[0][1]["character_points"], 7)

    # ── refusals emit nothing (no committed advance) ──────────────────────────
    def test_insufficient_cp_no_emit(self):
        db, _ = self._run_train(cp=2)  # cost 4 > 2 CP
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.saved, [])

    def test_unknown_skill_no_emit(self):
        db, _ = self._run_train(skill_arg="notaskill")
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.saved, [])

    def test_force_skill_no_emit(self):
        db, _ = self._run_train(skill_arg="control")
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.saved, [])

    def test_empty_arg_no_emit(self):
        db, _ = self._run_train(skill_arg="")
        self.assertEqual(len(_events()), 0)
        self.assertEqual(db.saved, [])

    def test_not_logged_in_no_emit(self):
        sess = _FakeSession(None)
        ctx = CommandContext(
            session=sess, raw_input="train blaster", command="train",
            args="blaster", args_list=["blaster"], switches=[],
            db=_FakeDB(None), session_mgr=None,
        )
        asyncio.run(cpc.TrainCommand().execute(ctx))
        self.assertEqual(len(_events()), 0)

    # ── sampling honours the tunable, the advance still lands ─────────────────
    def test_sample_zero_suppresses_event_not_the_train(self):
        tunables._TUNABLES["telemetry.cp_spend_sample"] = 0.0
        db, _ = self._run_train()
        self.assertEqual(len(_events()), 0)
        # The skill was still trained + CP still spent.
        self.assertEqual(db.saved[0][1]["character_points"], 6)

    def test_sample_default_captures(self):
        self._run_train()  # no tunable set → defaults to 1.0
        self.assertEqual(len(_events()), 1)

    # ── load-bearing: a broken sink never disturbs the completed advance ──────
    def test_fail_open_when_emit_raises(self):
        def _boom(*a, **kw):
            raise RuntimeError("telemetry down")

        with mock.patch.object(telemetry, "emit", _boom):
            db, _ = self._run_train()
        # No crash; the advance committed (CP debited + skills saved).
        self.assertEqual(db.saved[0][1]["character_points"], 6)

    # ── helper unit: field schema + coercion + None-extra drop ────────────────
    def test_helper_schema(self):
        cpc._emit_cp_spend(
            42, "bargain", 5, attribute="knowledge", dice=5,
            cp_remaining=12, old_pool="5D", new_pool="5D+1",
            guild_discount=False)
        e = _events()[0]
        self.assertEqual(e["ev"], "cp_spend")
        self.assertEqual(e["source"], "train")
        self.assertEqual(e["char_id"], 42)
        self.assertEqual(e["skill"], "bargain")
        self.assertEqual(e["cost"], 5)
        self.assertEqual(e["attribute"], "knowledge")
        self.assertEqual(e["cp_remaining"], 12)

    def test_helper_coerces_str_id(self):
        cpc._emit_cp_spend("7", "blaster", 4)
        self.assertEqual(_events()[0]["char_id"], 7)

    def test_helper_drops_none_extra(self):
        cpc._emit_cp_spend(7, "blaster", 4, attribute=None, dice=4)
        e = _events()[0]
        self.assertNotIn("attribute", e)
        self.assertEqual(e["dice"], 4)

    # ── seam wired + tunable registered (drift pins) ──────────────────────────
    def test_seam_calls_helper(self):
        src = (REPO / "parser" / "cp_commands.py").read_text(encoding="utf-8")
        self.assertIn("_emit_cp_spend(", src)
        self.assertIn("telemetry.cp_spend_sample", src)

    def test_tunable_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        self.assertIn("telemetry.cp_spend_sample:", ty)


if __name__ == "__main__":
    unittest.main()
