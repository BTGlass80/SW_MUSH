# -*- coding: utf-8 -*-
"""
tests/test_wow2c_counsel_retreat.py — WoW.2c command tests.

Per weight_of_war_design_v1.md §5.2 + §10. Tests +counsel,
+retreat, and +return end-to-end against real Database
(Pattern 8 discipline).

Test sections
=============

+counsel command shape:
  1.  TestCounselKey                       — '+counsel', alias 'counsel'
  2.  TestCounselNotAdmin                  — player-level

+counsel identity gate:
  3.  TestCounselRejectsNonJedi
  4.  TestCounselAcceptsJediByFaction

+counsel Padawan path:
  5.  TestCounselPadawanWithMasterInRoom   — happy path
  6.  TestCounselPadawanMasterWrongRoom    — rejection message
  7.  TestCounselPadawanNoMasterRecord     — defensive: master id missing

+counsel Knight/Master path:
  8.  TestCounselNoBondAtCouncilChamber    — happy path
  9.  TestCounselNoBondWrongRoom           — rejection (not Council Chamber)
 10.  TestCounselNoBondZonelessRoom        — defensive

+counsel cooldown:
 11.  TestCounselCooldownAfterSuccess
 12.  TestCounselCooldownMessage

+counsel at-peace short-circuit:
 13.  TestCounselAtPeaceNoChange
 14.  TestCounselAtPeaceNoCooldown

+counsel event log:
 15.  TestCounselLogsEventWithPadawanDescription
 16.  TestCounselLogsEventWithCouncilDescription

+retreat:
 17.  TestRetreatRejectsNonJedi
 18.  TestRetreatHappy                     — sets flag + timestamp
 19.  TestRetreatRejectsWhileAlreadyInRetreat
 20.  TestRetreatPersistsState

+return:
 21.  TestReturnRejectsIfNotInRetreat
 22.  TestReturnSameDayNoDecay
 23.  TestReturnAppliesProRatedDecay       — 20 days → -30 cap
 24.  TestReturnClearsRetreatFlag
 25.  TestReturnLogsEvent
 26.  TestReturnDecayClampsToFloor         — start at weight 5, 20 days → weight 0 not negative

Phantom-prevention (Pattern 8):
 27.  TestCounselProductionSchemaEndToEnd
 28.  TestRetreatReturnCycleProductionSchema
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time as _time
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ── Harness ───────────────────────────────────────────────────────────


class _Harness:
    """Real-Database fixture with Temple zone, Council Chamber +
    Training Hall rooms, a Knight (id 10), a Padawan (id 11), and
    a Master (id 12) bonded to the Padawan.

    Weights: Knight=60, Padawan=40 by default."""

    def __init__(self):
        self.db = None
        self.council_room = 0
        self.training_room = 0
        self.knight_id = 10
        self.padawan_id = 11
        self.master_id = 12

    async def setup(self,
                    knight_weight: int = 60,
                    padawan_weight: int = 40) -> None:
        from db.database import Database
        self.db = Database(":memory:")
        await self.db.connect()
        await self.db.initialize()

        await self.db._db.execute(
            "INSERT INTO accounts (id, username, password_hash) "
            "VALUES (1, 'u', 'p')",
        )
        cur = await self.db._db.execute(
            "INSERT INTO zones (name, properties) VALUES (?, ?)",
            ("coruscant_temple", "{}"),
        )
        temple_zone = cur.lastrowid
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, zone_id, properties) "
            "VALUES (?, ?, ?)",
            ("Council Chamber", temple_zone,
             json.dumps({"slug": "jedi_temple_council_chamber"})),
        )
        self.council_room = cur.lastrowid
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, zone_id, properties) "
            "VALUES (?, ?, ?)",
            ("Training Hall", temple_zone,
             json.dumps({"slug": "jedi_temple_training_hall"})),
        )
        self.training_room = cur.lastrowid

        # Knight (no bond)
        await self.db._db.execute(
            "INSERT INTO characters "
            "(id, account_id, name, room_id, faction_id, "
            "weight_of_war) VALUES (?, ?, ?, ?, ?, ?)",
            (self.knight_id, 1, "Obi-Wan", self.council_room,
             "jedi_order", knight_weight),
        )
        # Padawan (with bond)
        await self.db._db.execute(
            "INSERT INTO characters "
            "(id, account_id, name, room_id, faction_id, "
            "weight_of_war) VALUES (?, ?, ?, ?, ?, ?)",
            (self.padawan_id, 1, "Ahsoka", self.training_room,
             "jedi_order", padawan_weight),
        )
        # Padawan's Master (in council room by default)
        await self.db._db.execute(
            "INSERT INTO characters "
            "(id, account_id, name, room_id, faction_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (self.master_id, 1, "Anakin", self.council_room,
             "jedi_order"),
        )
        await self.db._db.execute(
            "INSERT INTO master_padawan_bond "
            "(master_char_id, padawan_char_id, bond_status) "
            "VALUES (?, ?, ?)",
            (self.master_id, self.padawan_id, "active"),
        )
        await self.db._db.commit()


def _make_ctx(char: dict, db):
    session = MagicMock()
    session.lines = []

    async def send(s):
        session.lines.append(str(s))

    session.send_line = send
    session.character = char
    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.args = ""
    return ctx


def _contains(ctx, needle):
    return any(needle in line for line in ctx.session.lines)


# ═════════════════════════════════════════════════════════════════════
# +counsel command shape
# ═════════════════════════════════════════════════════════════════════

class TestCounselKey(unittest.TestCase):
    def test_key_and_alias(self):
        from parser.wow_counsel_retreat import CounselCommand
        cmd = CounselCommand()
        self.assertEqual(cmd.key, "+counsel")
        self.assertIn("counsel", cmd.aliases)


class TestCounselNotAdmin(unittest.TestCase):
    def test_no_admin_gate(self):
        from parser.wow_counsel_retreat import CounselCommand
        from parser.commands import AccessLevel
        self.assertNotEqual(
            getattr(CounselCommand(), "access_level", None),
            AccessLevel.ADMIN,
        )


# ═════════════════════════════════════════════════════════════════════
# Identity gate
# ═════════════════════════════════════════════════════════════════════

class TestCounselRejectsNonJedi(unittest.TestCase):
    def test_bh_guild_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            await h.db.save_character(
                h.knight_id, faction_id="bh_guild",
            )
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "Only Jedi"))
        _run(go())


class TestCounselAcceptsJediByFaction(unittest.TestCase):
    def test_jedi_order_passes(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertFalse(_contains(ctx, "Only Jedi"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Padawan path
# ═════════════════════════════════════════════════════════════════════

class TestCounselPadawanWithMasterInRoom(unittest.TestCase):
    def test_happy_path(self):
        async def go():
            h = _Harness()
            await h.setup()
            # Move master into Padawan's room
            await h.db.save_character(
                h.master_id, room_id=h.training_room,
            )
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.padawan_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            after = await h.db.get_character(h.padawan_id)
            self.assertEqual(after["weight_of_war"], 30)
            self.assertTrue(_contains(ctx, "sit with your Master"))
        _run(go())


class TestCounselPadawanMasterWrongRoom(unittest.TestCase):
    def test_master_in_council_chamber_padawan_in_training(self):
        async def go():
            h = _Harness()
            await h.setup()
            # Master in council_room (default), Padawan in training
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.padawan_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "is not here"))
            after = await h.db.get_character(h.padawan_id)
            self.assertEqual(after["weight_of_war"], 40)
        _run(go())


class TestCounselPadawanNoMasterRecord(unittest.TestCase):
    def test_bond_with_missing_master(self):
        """Defensive: if the bond points to a master_char_id whose
        characters row was force-removed (FK cascade should normally
        prevent this, but admin tools bypassing FK could leave a
        bond orphaned), the command should produce a friendly
        'cannot be found' message rather than crash."""
        async def go():
            h = _Harness()
            await h.setup()
            # Repoint the bond at a nonexistent master id, then
            # disable FK enforcement so the orphaned bond persists.
            await h.db._db.execute("PRAGMA foreign_keys = OFF")
            await h.db._db.execute(
                "UPDATE master_padawan_bond "
                "SET master_char_id = ? WHERE padawan_char_id = ?",
                (99999, h.padawan_id),
            )
            await h.db._db.commit()
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.padawan_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "cannot be found"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Knight/Master path
# ═════════════════════════════════════════════════════════════════════

class TestCounselNoBondAtCouncilChamber(unittest.TestCase):
    def test_knight_at_chamber_happy(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            after = await h.db.get_character(h.knight_id)
            self.assertEqual(after["weight_of_war"], 50)
            self.assertTrue(
                _contains(ctx, "Council Chamber, you find"),
            )
        _run(go())


class TestCounselNoBondWrongRoom(unittest.TestCase):
    def test_knight_in_wrong_room_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            await h.db.save_character(
                h.knight_id, room_id=h.training_room,
            )
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "Council Chamber"))
            after = await h.db.get_character(h.knight_id)
            self.assertEqual(after["weight_of_war"], 60)
        _run(go())


class TestCounselNoBondZonelessRoom(unittest.TestCase):
    def test_invalid_room_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            cur = await h.db._db.execute(
                "INSERT INTO rooms (name, zone_id, properties) "
                "VALUES (?, ?, ?)",
                ("Void", None, "{}"),
            )
            void_id = cur.lastrowid
            await h.db._db.commit()
            await h.db.save_character(h.knight_id, room_id=void_id)
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "Council Chamber"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Cooldown
# ═════════════════════════════════════════════════════════════════════

class TestCounselCooldownAfterSuccess(unittest.TestCase):
    def test_second_attempt_blocked(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            char2 = await h.db.get_character(h.knight_id)
            ctx2 = _make_ctx(char2, h.db)
            await CounselCommand().execute(ctx2)
            self.assertTrue(_contains(ctx2, "sought counsel recently"))
        _run(go())


class TestCounselCooldownMessage(unittest.TestCase):
    def test_includes_time_remaining(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            char2 = await h.db.get_character(h.knight_id)
            ctx2 = _make_ctx(char2, h.db)
            await CounselCommand().execute(ctx2)
            joined = " ".join(ctx2.session.lines)
            # 7-day cooldown → "167h NNm" range
            self.assertTrue("h " in joined or "h\n" in joined)
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# At-peace short-circuit
# ═════════════════════════════════════════════════════════════════════

class TestCounselAtPeaceNoChange(unittest.TestCase):
    def test_at_peace_no_change(self):
        async def go():
            h = _Harness()
            await h.setup(knight_weight=0)
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await CounselCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "already at peace"))
            after = await h.db.get_character(h.knight_id)
            self.assertEqual(after["weight_of_war"], 0)
        _run(go())


class TestCounselAtPeaceNoCooldown(unittest.TestCase):
    def test_at_peace_does_not_set_cooldown(self):
        async def go():
            h = _Harness()
            await h.setup(knight_weight=0)
            from parser.wow_counsel_retreat import CounselCommand
            char = await h.db.get_character(h.knight_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            after = await h.db.get_character(h.knight_id)
            attrs = json.loads(after.get("attributes") or "{}")
            self.assertNotIn("counsel", attrs.get("cooldowns", {}))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Event log
# ═════════════════════════════════════════════════════════════════════

class TestCounselLogsEventWithPadawanDescription(unittest.TestCase):
    def test_padawan_description(self):
        async def go():
            h = _Harness()
            await h.setup()
            await h.db.save_character(
                h.master_id, room_id=h.training_room,
            )
            from parser.wow_counsel_retreat import CounselCommand
            from engine.weight_of_war import get_events
            char = await h.db.get_character(h.padawan_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            events = await get_events(h.db, h.padawan_id, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["trigger_type"], "counsel")
            self.assertIn("Master", events[0]["description"])
        _run(go())


class TestCounselLogsEventWithCouncilDescription(unittest.TestCase):
    def test_council_description(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            from engine.weight_of_war import get_events
            char = await h.db.get_character(h.knight_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            events = await get_events(h.db, h.knight_id, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["trigger_type"], "counsel")
            self.assertIn("Council", events[0]["description"])
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# +retreat
# ═════════════════════════════════════════════════════════════════════

class TestRetreatRejectsNonJedi(unittest.TestCase):
    def test_bh_guild_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            await h.db.save_character(
                h.knight_id, faction_id="bh_guild",
            )
            from parser.wow_counsel_retreat import RetreatCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await RetreatCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "Only Jedi"))
        _run(go())


class TestRetreatHappy(unittest.TestCase):
    def test_sets_flag_and_timestamp(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import RetreatCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await RetreatCommand().execute(ctx)
            after = await h.db.get_character(h.knight_id)
            attrs = json.loads(after.get("attributes") or "{}")
            self.assertTrue(attrs.get("wow_retreat_active"))
            self.assertGreater(
                attrs.get("wow_retreat_started_at") or 0, 0,
            )
            self.assertTrue(_contains(ctx, "withdraw from active"))
        _run(go())


class TestRetreatRejectsWhileAlreadyInRetreat(unittest.TestCase):
    def test_double_retreat_blocked(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import RetreatCommand
            char = await h.db.get_character(h.knight_id)
            await RetreatCommand().execute(_make_ctx(char, h.db))
            char2 = await h.db.get_character(h.knight_id)
            ctx2 = _make_ctx(char2, h.db)
            await RetreatCommand().execute(ctx2)
            self.assertTrue(_contains(ctx2, "already in retreat"))
        _run(go())


class TestRetreatPersistsState(unittest.TestCase):
    def test_state_survives_reload(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import RetreatCommand
            char = await h.db.get_character(h.knight_id)
            await RetreatCommand().execute(_make_ctx(char, h.db))
            # Fresh fetch from DB
            reloaded = await h.db.get_character(h.knight_id)
            attrs = json.loads(reloaded.get("attributes") or "{}")
            self.assertTrue(attrs.get("wow_retreat_active"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# +return
# ═════════════════════════════════════════════════════════════════════

class TestReturnRejectsIfNotInRetreat(unittest.TestCase):
    def test_no_retreat_state_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import ReturnCommand
            char = await h.db.get_character(h.knight_id)
            ctx = _make_ctx(char, h.db)
            await ReturnCommand().execute(ctx)
            self.assertTrue(_contains(ctx, "not currently in retreat"))
        _run(go())


class TestReturnSameDayNoDecay(unittest.TestCase):
    def test_same_day_zero_decay(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import (
                RetreatCommand, ReturnCommand,
            )
            char = await h.db.get_character(h.knight_id)
            await RetreatCommand().execute(_make_ctx(char, h.db))
            char2 = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char2, h.db))
            after = await h.db.get_character(h.knight_id)
            self.assertEqual(after["weight_of_war"], 60)  # unchanged
        _run(go())


class TestReturnAppliesProRatedDecay(unittest.TestCase):
    def test_twenty_days_caps_at_thirty(self):
        async def go():
            h = _Harness()
            await h.setup(knight_weight=60)
            # Backdate retreat by 20 days
            attrs = {
                "wow_retreat_active": True,
                "wow_retreat_started_at": _time.time() - 20 * 86400,
            }
            await h.db.save_character(
                h.knight_id, attributes=json.dumps(attrs),
            )
            from parser.wow_counsel_retreat import ReturnCommand
            char = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char, h.db))
            after = await h.db.get_character(h.knight_id)
            # 20 days * 2 = 40 desired, but cap is 30. So 60 - 30 = 30
            self.assertEqual(after["weight_of_war"], 30)
        _run(go())


class TestReturnClearsRetreatFlag(unittest.TestCase):
    def test_flag_cleared_after_return(self):
        async def go():
            h = _Harness()
            await h.setup()
            attrs = {
                "wow_retreat_active": True,
                "wow_retreat_started_at": _time.time() - 5 * 86400,
            }
            await h.db.save_character(
                h.knight_id, attributes=json.dumps(attrs),
            )
            from parser.wow_counsel_retreat import ReturnCommand
            char = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char, h.db))
            after = await h.db.get_character(h.knight_id)
            new_attrs = json.loads(after.get("attributes") or "{}")
            self.assertFalse(
                new_attrs.get("wow_retreat_active"),
            )
            self.assertNotIn("wow_retreat_started_at", new_attrs)
        _run(go())


class TestReturnLogsEvent(unittest.TestCase):
    def test_retreat_event_logged(self):
        async def go():
            h = _Harness()
            await h.setup()
            attrs = {
                "wow_retreat_active": True,
                "wow_retreat_started_at": _time.time() - 3 * 86400,
            }
            await h.db.save_character(
                h.knight_id, attributes=json.dumps(attrs),
            )
            from parser.wow_counsel_retreat import ReturnCommand
            from engine.weight_of_war import get_events
            char = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char, h.db))
            events = await get_events(h.db, h.knight_id, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["trigger_type"], "retreat")
            self.assertEqual(events[0]["delta"], -6)  # 3 days * 2
        _run(go())


class TestReturnDecayClampsToFloor(unittest.TestCase):
    def test_decay_clamps_to_zero(self):
        async def go():
            h = _Harness()
            await h.setup(knight_weight=5)
            attrs = {
                "wow_retreat_active": True,
                "wow_retreat_started_at": _time.time() - 20 * 86400,
            }
            await h.db.save_character(
                h.knight_id, attributes=json.dumps(attrs),
            )
            from parser.wow_counsel_retreat import ReturnCommand
            char = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char, h.db))
            after = await h.db.get_character(h.knight_id)
            # Substrate floor at 0
            self.assertEqual(after["weight_of_war"], 0)
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Production-schema integration (Pattern 8)
# ═════════════════════════════════════════════════════════════════════

class TestCounselProductionSchemaEndToEnd(unittest.TestCase):
    """Full +counsel flow against real Database — Pattern 8."""

    def test_counsel_complete_flow(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import CounselCommand
            from engine.weight_of_war import (
                get_events, get_weight_db,
            )

            # 1. Knight counsels at Council Chamber
            char = await h.db.get_character(h.knight_id)
            await CounselCommand().execute(_make_ctx(char, h.db))
            self.assertEqual(
                await get_weight_db(h.db, h.knight_id), 50,
            )

            # 2. Cooldown blocks second attempt
            char2 = await h.db.get_character(h.knight_id)
            ctx2 = _make_ctx(char2, h.db)
            await CounselCommand().execute(ctx2)
            self.assertTrue(
                _contains(ctx2, "sought counsel recently"),
            )

            # 3. Event log
            events = await get_events(h.db, h.knight_id, limit=5)
            self.assertEqual(len(events), 1)
        _run(go())


class TestRetreatReturnCycleProductionSchema(unittest.TestCase):
    """Full +retreat → +return cycle against real Database."""

    def test_retreat_return_full_cycle(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.wow_counsel_retreat import (
                RetreatCommand, ReturnCommand,
            )

            # 1. Declare retreat
            char = await h.db.get_character(h.knight_id)
            await RetreatCommand().execute(_make_ctx(char, h.db))
            mid = await h.db.get_character(h.knight_id)
            attrs = json.loads(mid.get("attributes") or "{}")
            self.assertTrue(attrs.get("wow_retreat_active"))

            # 2. Backdate so we have decay to apply
            attrs["wow_retreat_started_at"] = (
                _time.time() - 4 * 86400
            )
            await h.db.save_character(
                h.knight_id, attributes=json.dumps(attrs),
            )

            # 3. Return
            char2 = await h.db.get_character(h.knight_id)
            await ReturnCommand().execute(_make_ctx(char2, h.db))
            after = await h.db.get_character(h.knight_id)
            self.assertEqual(after["weight_of_war"], 52)  # 60-8
            final_attrs = json.loads(after.get("attributes") or "{}")
            self.assertFalse(final_attrs.get("wow_retreat_active"))
        _run(go())


if __name__ == "__main__":
    unittest.main()
