# -*- coding: utf-8 -*-
"""
tests/test_pm3_training_events.py — P-M.3 (May 22 2026).

Padawan-Master training events per design §5.2.

Ships:

  Schema (v34): training_log table.
  DB helpers: insert_training_log, get_last_spar_for_bond,
              get_training_log_for_bond, count_teach_events_for_bond.
  Commands: +teach (Master), +learn (Padawan), +spar (Either),
            via parser/padawan_master_training_commands.py.
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(db, *, name="Test", attrs=None, skills=None,
                       cp=10, room_id=1):
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid
    if attrs is None:
        attrs = {"strength": "3D", "dexterity": "3D",
                 "knowledge": "3D", "perception": "3D",
                 "mechanical": "3D", "technical": "3D"}
    if skills is None:
        skills = {}
    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, character_points, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, room_id,
         json.dumps(attrs), json.dumps(skills), '{"items":[]}',
         0, cp, 0),
    )
    await db._db.commit()
    row = await db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (cur.lastrowid,)
    )
    return dict(row[0])


async def _create_active_bond(db, *, master_id: int, padawan_id: int):
    cur = await db._db.execute(
        """INSERT INTO master_padawan_bond
           (master_char_id, padawan_char_id, bond_status)
           VALUES (?, ?, 'active')""",
        (master_id, padawan_id),
    )
    await db._db.commit()
    return int(cur.lastrowid)


def _reset_state():
    from parser.padawan_master_training_commands import _reset_for_test
    _reset_for_test()


# ──────────────────────────────────────────────────────
# Schema v34
# ──────────────────────────────────────────────────────

class TestSchemaV34(unittest.TestCase):

    def test_schema_version_at_least_34(self):
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 34)

    def test_training_log_table_exists(self):
        async def go():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='training_log'"
            )
            self.assertTrue(rows)
        _run(go())

    def test_training_log_columns(self):
        async def go():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(training_log)"
            )
            cols = {r["name"] for r in rows}
            for need in ("bond_id", "master_id", "padawan_id",
                          "event_type", "payload_json", "created_at"):
                self.assertIn(need, cols)
        _run(go())


# ──────────────────────────────────────────────────────
# DB helpers
# ──────────────────────────────────────────────────────

class TestInsertTrainingLog(unittest.TestCase):

    def test_basic_insert(self):
        async def go():
            db = await _fresh_db()
            new_id = await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach",
                payload={"power_key": "telekinesis"},
            )
            self.assertGreater(new_id, 0)
            rows = await db._db.execute_fetchall(
                "SELECT * FROM training_log WHERE id = ?", (new_id,)
            )
            self.assertEqual(len(rows), 1)
            r = rows[0]
            self.assertEqual(int(r["bond_id"]), 1)
            self.assertEqual(r["event_type"], "teach")
            payload = json.loads(r["payload_json"])
            self.assertEqual(payload["power_key"], "telekinesis")
        _run(go())

    def test_payload_defaults_to_empty(self):
        async def go():
            db = await _fresh_db()
            new_id = await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="spar",
            )
            rows = await db._db.execute_fetchall(
                "SELECT payload_json FROM training_log WHERE id = ?",
                (new_id,),
            )
            self.assertEqual(json.loads(rows[0]["payload_json"]), {})
        _run(go())


class TestGetLastSpar(unittest.TestCase):

    def test_no_spars_returns_none(self):
        async def go():
            db = await _fresh_db()
            self.assertIsNone(await db.get_last_spar_for_bond(1))
        _run(go())

    def test_most_recent_returned(self):
        async def go():
            db = await _fresh_db()
            now = time.time()
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="spar", created_at=now - 100,
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="spar", created_at=now,
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", created_at=now + 50,
                payload={"power_key": "x"},
            )
            r = await db.get_last_spar_for_bond(1)
            self.assertIsNotNone(r)
            self.assertEqual(r["event_type"], "spar")
            self.assertAlmostEqual(float(r["created_at"]), now, delta=1)
        _run(go())

    def test_filter_by_bond(self):
        async def go():
            db = await _fresh_db()
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="spar",
            )
            await db.insert_training_log(
                bond_id=2, master_id=4, padawan_id=5,
                event_type="spar",
            )
            r1 = await db.get_last_spar_for_bond(1)
            r2 = await db.get_last_spar_for_bond(2)
            self.assertEqual(int(r1["bond_id"]), 1)
            self.assertEqual(int(r2["bond_id"]), 2)
        _run(go())


class TestCountTeach(unittest.TestCase):

    def test_count_all(self):
        async def go():
            db = await _fresh_db()
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", payload={"power_key": "a"},
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", payload={"power_key": "b"},
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="spar",
            )
            n = await db.count_teach_events_for_bond(1)
            self.assertEqual(n, 2)
        _run(go())

    def test_count_by_power_key(self):
        async def go():
            db = await _fresh_db()
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", payload={"power_key": "telekinesis"},
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", payload={"power_key": "telekinesis"},
            )
            await db.insert_training_log(
                bond_id=1, master_id=2, padawan_id=3,
                event_type="teach", payload={"power_key": "control_pain"},
            )
            n = await db.count_teach_events_for_bond(
                1, power_key="telekinesis"
            )
            self.assertEqual(n, 2)
        _run(go())


# ──────────────────────────────────────────────────────
# In-memory state
# ──────────────────────────────────────────────────────

class TestLearnRequestExpiry(unittest.TestCase):

    def test_expired_after_ttl(self):
        from parser.padawan_master_training_commands import (
            _LearnRequest, LEARN_REQUEST_TTL_SECS,
        )
        r = _LearnRequest(
            padawan_id=1, master_id=2, power_key="x",
            created_at=100.0,
        )
        self.assertFalse(r.is_expired(now=100.0 + LEARN_REQUEST_TTL_SECS - 1))
        self.assertTrue(r.is_expired(now=100.0 + LEARN_REQUEST_TTL_SECS))

    def test_reset_clears_state(self):
        from parser.padawan_master_training_commands import (
            _LEARN_REQUESTS, _LearnRequest, _reset_for_test,
        )
        _LEARN_REQUESTS[1] = _LearnRequest(
            padawan_id=1, master_id=2, power_key="x",
        )
        _reset_for_test()
        self.assertEqual(len(_LEARN_REQUESTS), 0)


class TestPendingLearnLookup(unittest.TestCase):

    def test_no_request_returns_none(self):
        from parser.padawan_master_training_commands import (
            _get_pending_learn,
        )
        _reset_state()
        self.assertIsNone(_get_pending_learn(1, 2, "x"))

    def test_match_returns_request(self):
        from parser.padawan_master_training_commands import (
            _LEARN_REQUESTS, _LearnRequest, _get_pending_learn,
        )
        _reset_state()
        _LEARN_REQUESTS[1] = _LearnRequest(
            padawan_id=1, master_id=2, power_key="telekinesis",
        )
        r = _get_pending_learn(1, 2, "telekinesis")
        self.assertIsNotNone(r)

    def test_wrong_master_returns_none(self):
        from parser.padawan_master_training_commands import (
            _LEARN_REQUESTS, _LearnRequest, _get_pending_learn,
        )
        _reset_state()
        _LEARN_REQUESTS[1] = _LearnRequest(
            padawan_id=1, master_id=2, power_key="x",
        )
        self.assertIsNone(_get_pending_learn(1, 99, "x"))

    def test_wrong_power_returns_none(self):
        from parser.padawan_master_training_commands import (
            _LEARN_REQUESTS, _LearnRequest, _get_pending_learn,
        )
        _reset_state()
        _LEARN_REQUESTS[1] = _LearnRequest(
            padawan_id=1, master_id=2, power_key="x",
        )
        self.assertIsNone(_get_pending_learn(1, 2, "different_power"))

    def test_expired_request_returns_none_and_cleans(self):
        from parser.padawan_master_training_commands import (
            _LEARN_REQUESTS, _LearnRequest, _get_pending_learn,
        )
        _reset_state()
        _LEARN_REQUESTS[1] = _LearnRequest(
            padawan_id=1, master_id=2, power_key="x",
            created_at=0,  # 0 → very old
        )
        self.assertIsNone(_get_pending_learn(1, 2, "x"))
        # Cleaned up
        self.assertNotIn(1, _LEARN_REQUESTS)


# ──────────────────────────────────────────────────────
# Power lookup
# ──────────────────────────────────────────────────────

class TestPowerLookup(unittest.TestCase):

    def test_normalize_lowercases_and_underscores(self):
        from parser.padawan_master_training_commands import (
            _normalize_power_key,
        )
        self.assertEqual(_normalize_power_key("Telekinesis"), "telekinesis")
        self.assertEqual(_normalize_power_key("Control Pain"),
                          "control_pain")
        self.assertEqual(_normalize_power_key("  CONTROL_PAIN  "),
                          "control_pain")

    def test_lookup_known_power(self):
        from parser.padawan_master_training_commands import _lookup_power
        p = _lookup_power("control_pain")
        self.assertIsNotNone(p)
        self.assertEqual(p.key, "control_pain")

    def test_lookup_unknown_returns_none(self):
        from parser.padawan_master_training_commands import _lookup_power
        self.assertIsNone(_lookup_power("not_a_power"))

    def test_lookup_with_spaces(self):
        from parser.padawan_master_training_commands import _lookup_power
        p = _lookup_power("Control Pain")
        self.assertIsNotNone(p)


# ──────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────

class TestHasOneDie(unittest.TestCase):

    def test_one_die_strings(self):
        from parser.padawan_master_training_commands import _has_one_die
        for s in ("1D", "2D", "3D+1", "4D", "10D"):
            self.assertTrue(_has_one_die(s), s)

    def test_no_die_strings(self):
        from parser.padawan_master_training_commands import _has_one_die
        for s in (None, "", "0D", "0D+1", "2"):
            self.assertFalse(_has_one_die(s), s)


class TestDiceCountFromStr(unittest.TestCase):

    def test_parses(self):
        from parser.padawan_master_training_commands import (
            _dice_count_from_str,
        )
        self.assertEqual(_dice_count_from_str("3D"), 3)
        self.assertEqual(_dice_count_from_str("3D+2"), 3)
        self.assertEqual(_dice_count_from_str("0D"), 0)
        self.assertEqual(_dice_count_from_str(None), 0)
        self.assertEqual(_dice_count_from_str("garbage"), 0)


# ──────────────────────────────────────────────────────
# Command execution — +learn
# ──────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None):
        self.is_in_game = True
        self.account = {"username": "P", "is_admin": 0}
        self.character = character
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)

    def text(self) -> str:
        return "\n".join(self.sent)


class _FakeSessionMgr:
    def __init__(self):
        self.broadcasts: list[tuple[int, str]] = []
        self._by_char: dict[int, _FakeSession] = {}

    async def broadcast_to_room(self, room_id, msg, exclude=None,
                                  source_char=None):
        self.broadcasts.append((room_id, msg))

    def find_by_character(self, char_id):
        return self._by_char.get(char_id)

    def sessions_in_room(self, room_id, source_char=None):
        return [s for s in self._by_char.values()
                if s.character and s.character.get("room_id") == room_id]


def _make_ctx(*, db, session, session_mgr, command, args="",
                switches=None):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=command + " " + args,
        command=command,
        args=args,
        args_list=args.split(),
        switches=switches or [],
        db=db,
        session_mgr=session_mgr,
    )


class TestLearnCommandHappy(unittest.TestCase):

    def test_creates_pending_request(self):
        from parser.padawan_master_training_commands import (
            LearnCommand, _LEARN_REQUESTS,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="Yoda",
                                         attrs={"strength":"3D","dexterity":"3D","knowledge":"4D","perception":"4D","mechanical":"3D","technical":"3D","control":"3D","sense":"3D","alter":"3D"})
            padawan = await _make_char(db, name="Luke")
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            mgr._by_char[master["id"]] = _FakeSession(character=master)
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+learn",
                              args="control_pain from Yoda")
            await LearnCommand().execute(ctx)
            self.assertIn(padawan["id"], _LEARN_REQUESTS)
            req = _LEARN_REQUESTS[padawan["id"]]
            self.assertEqual(req.master_id, master["id"])
            self.assertEqual(req.power_key, "control_pain")
        _run(go())


class TestLearnUnknownPower(unittest.TestCase):

    def test_rejects(self):
        from parser.padawan_master_training_commands import LearnCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterX")
            padawan = await _make_char(db, name="PadawanX")
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+learn",
                              args="banthapoodoo from MasterX")
            await LearnCommand().execute(ctx)
            self.assertIn("not a recognized", sess.text().lower())
        _run(go())


class TestLearnNoBond(unittest.TestCase):

    def test_rejects_without_bond(self):
        from parser.padawan_master_training_commands import LearnCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            padawan = await _make_char(db, name="Unbonded")
            master = await _make_char(db, name="MasterY")
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+learn",
                              args="control_pain from MasterY")
            await LearnCommand().execute(ctx)
            self.assertIn("don't have an active padawan bond",
                            sess.text().lower())
        _run(go())


class TestLearnWrongMaster(unittest.TestCase):

    def test_rejects_when_specified_master_not_yours(self):
        from parser.padawan_master_training_commands import LearnCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            real_master = await _make_char(db, name="RealMaster")
            other_master = await _make_char(db, name="OtherMaster")
            padawan = await _make_char(db, name="Pad")
            await _create_active_bond(
                db, master_id=real_master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+learn",
                              args="control_pain from OtherMaster")
            await LearnCommand().execute(ctx)
            self.assertIn("not your master", sess.text().lower())
        _run(go())


# ──────────────────────────────────────────────────────
# Command execution — +teach
# ──────────────────────────────────────────────────────

class TestTeachCommandSuccess(unittest.TestCase):

    def test_master_teaches_padawan(self):
        from parser.padawan_master_training_commands import (
            TeachPowerCommand,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            # Master has control skill (1D+), Padawan has none.
            master = await _make_char(
                db, name="MasterT",
                skills={"control": "3D"},
                room_id=1,
            )
            padawan = await _make_char(
                db, name="PadT",
                skills={},
                room_id=1, cp=50,
            )
            bond_id = await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=master)
            mgr = _FakeSessionMgr()
            mgr._by_char[padawan["id"]] = _FakeSession(character=padawan)
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+teach",
                              args="control_pain")
            await TeachPowerCommand().execute(ctx)
            # Should succeed, Padawan now has control at 1D
            updated = await db.get_character(padawan["id"])
            # Force skills live in the ATTRIBUTES blob (force_sensitive derives
            # from control/sense/alter there); +teach writes them to attributes.
            attrs = json.loads(updated["attributes"])
            self.assertEqual(attrs.get("control"), "1D")
            # CP deducted: cost = 2D attr default * 3 pips = 6
            self.assertEqual(int(updated["character_points"]), 44)
            # training_log entry created
            log_rows = await db.get_training_log_for_bond(bond_id)
            self.assertEqual(len(log_rows), 1)
            self.assertEqual(log_rows[0]["event_type"], "teach")
        _run(go())


class TestTeachMasterCannotAttempt(unittest.TestCase):

    def test_master_without_required_skill_rejected(self):
        from parser.padawan_master_training_commands import (
            TeachPowerCommand,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            # Master has NO control skill
            master = await _make_char(db, name="MasterU", skills={})
            padawan = await _make_char(db, name="PadU", room_id=1, cp=50)
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=master)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+teach",
                              args="control_pain")
            await TeachPowerCommand().execute(ctx)
            self.assertIn("don't know", sess.text().lower())
        _run(go())


class TestTeachInsufficientCp(unittest.TestCase):

    def test_padawan_with_low_cp_rejected(self):
        from parser.padawan_master_training_commands import (
            TeachPowerCommand,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterV",
                                          skills={"control": "3D"})
            # Padawan has only 2 CP — not enough for 6 (default 2D attr × 3)
            padawan = await _make_char(db, name="PadV", room_id=1, cp=2)
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=master)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+teach",
                              args="control_pain")
            await TeachPowerCommand().execute(ctx)
            self.assertIn("needs", sess.text().lower())
        _run(go())


class TestTeachDifferentRoom(unittest.TestCase):

    def test_padawan_in_different_room_rejected(self):
        from parser.padawan_master_training_commands import (
            TeachPowerCommand,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterW",
                                          skills={"control": "3D"},
                                          room_id=1)
            padawan = await _make_char(db, name="PadW", room_id=99, cp=50)
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=master)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+teach",
                              args="control_pain")
            await TeachPowerCommand().execute(ctx)
            self.assertIn("not in this room", sess.text().lower())
        _run(go())


class TestTeachConsumesLearnRequest(unittest.TestCase):

    def test_pending_request_consumed_on_match(self):
        from parser.padawan_master_training_commands import (
            TeachPowerCommand, _LEARN_REQUESTS, _LearnRequest,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterC",
                                          skills={"control": "3D"})
            padawan = await _make_char(db, name="PadC", room_id=1, cp=50)
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            # Pre-stage learn request
            _LEARN_REQUESTS[padawan["id"]] = _LearnRequest(
                padawan_id=padawan["id"],
                master_id=master["id"],
                power_key="control_pain",
            )
            sess = _FakeSession(character=master)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+teach",
                              args="control_pain")
            await TeachPowerCommand().execute(ctx)
            # Request consumed
            self.assertNotIn(padawan["id"], _LEARN_REQUESTS)
        _run(go())


# ──────────────────────────────────────────────────────
# Command execution — +spar
# ──────────────────────────────────────────────────────

class TestSparHappy(unittest.TestCase):

    def test_both_pcs_gain_cp(self):
        from parser.padawan_master_training_commands import (
            SparCommand, SPAR_CP_REWARD,
        )
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterS", cp=10, room_id=1)
            padawan = await _make_char(db, name="PadS", cp=10, room_id=1)
            bond_id = await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            mgr._by_char[master["id"]] = _FakeSession(character=master)
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+spar", args="")
            await SparCommand().execute(ctx)
            # Both gained CP
            updated_master = await db.get_character(master["id"])
            updated_padawan = await db.get_character(padawan["id"])
            self.assertEqual(int(updated_master["character_points"]),
                              10 + SPAR_CP_REWARD)
            self.assertEqual(int(updated_padawan["character_points"]),
                              10 + SPAR_CP_REWARD)
            # Training log
            rows = await db.get_training_log_for_bond(bond_id)
            spar_rows = [r for r in rows if r["event_type"] == "spar"]
            self.assertEqual(len(spar_rows), 1)
        _run(go())


class TestSparCooldown(unittest.TestCase):

    def test_back_to_back_spar_rejected(self):
        from parser.padawan_master_training_commands import SparCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterCD", cp=10, room_id=1)
            padawan = await _make_char(db, name="PadCD", cp=10, room_id=1)
            bond_id = await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            # Pre-log a recent spar (within cooldown)
            await db.insert_training_log(
                bond_id=bond_id, master_id=master["id"],
                padawan_id=padawan["id"], event_type="spar",
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+spar", args="")
            await SparCommand().execute(ctx)
            self.assertIn("too recently", sess.text().lower())
            # No CP change
            updated = await db.get_character(padawan["id"])
            self.assertEqual(int(updated["character_points"]), 10)
        _run(go())


class TestSparNoBond(unittest.TestCase):

    def test_rejects_unbonded(self):
        from parser.padawan_master_training_commands import SparCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            ch = await _make_char(db, name="Solo")
            sess = _FakeSession(character=ch)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+spar", args="")
            await SparCommand().execute(ctx)
            self.assertIn("not in an active", sess.text().lower())
        _run(go())


class TestSparDifferentRoom(unittest.TestCase):

    def test_rejects(self):
        from parser.padawan_master_training_commands import SparCommand
        async def go():
            _reset_state()
            db = await _fresh_db()
            master = await _make_char(db, name="MasterDr", room_id=1)
            padawan = await _make_char(db, name="PadDr", room_id=99)
            await _create_active_bond(
                db, master_id=master["id"], padawan_id=padawan["id"],
            )
            sess = _FakeSession(character=padawan)
            mgr = _FakeSessionMgr()
            ctx = _make_ctx(db=db, session=sess, session_mgr=mgr,
                              command="+spar", args="")
            await SparCommand().execute(ctx)
            self.assertIn("not in this room", sess.text().lower())
        _run(go())


# ──────────────────────────────────────────────────────
# Registration
# ──────────────────────────────────────────────────────

class TestRegistration(unittest.TestCase):

    def test_register_wires_three_commands(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_training_commands import (
            register_padawan_master_training_commands,
        )
        reg = CommandRegistry()
        register_padawan_master_training_commands(reg)
        self.assertIsNotNone(reg.get("+teach"))
        self.assertIsNotNone(reg.get("+learn"))
        self.assertIsNotNone(reg.get("+spar"))

    def test_registered_in_game_server(self):
        gs_path = PROJECT_ROOT / "server" / "game_server.py"
        text = gs_path.read_text(encoding="utf-8")
        self.assertIn(
            "register_padawan_master_training_commands", text
        )


if __name__ == "__main__":
    unittest.main()
