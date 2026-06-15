# -*- coding: utf-8 -*-
"""tests/test_pm_leave_master.py — T3.13 Padawan/Master gap-close.

Tests the two additions shipped in this drop:

  1. LeaveMasterCommand (+leave-master) — Padawan-initiated voluntary
     bond dissolution (requires a reason; dissolves; notifies Master;
     logs both sides).

  2. PadawanCommand trials parity — +padawan output now includes a
     "Trials passed: N of 5" line per Padawan, mirroring MasterCommand.

Test sections
=============

  1. TestLeaveMasterHappyPath     — dissolves bond, stores reason prefix
  2. TestLeaveMasterNoBond        — no-bond message, nothing dissolved
  3. TestLeaveMasterNoReason      — empty reason blocked, bond survives
  4. TestLeaveMasterMasterNotified — online Master receives notification
  5. TestPadawanTrialsParity      — +padawan output has trials count line
  6. TestLeaveMasterRegistered    — +leave-master registers in registry
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ───── shared fixtures ─────────────────────────────────────────────────────

async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names: list) -> dict:
    """Create characters; return {name: char_dict}. All at room_id=1."""
    await db._db.execute(
        """INSERT OR IGNORE INTO accounts
           (username, password_hash, email)
           VALUES ('test', 'hash', 't@e.com')"""
    )
    out = {}
    for n in names:
        cur = await db._db.execute(
            """INSERT INTO characters
               (account_id, name, species, room_id)
               VALUES (1, ?, 'Human', 1)""",
            (n,),
        )
        out[n] = cur.lastrowid
    await db._db.commit()
    chars = {}
    for n, cid in out.items():
        chars[n] = await db.get_character(cid)
    return chars


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 1, "is_builder": 1}
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def __init__(self):
        self._by_char: dict[int, _FakeSession] = {}

    def register(self, char_id: int, session: _FakeSession) -> None:
        self._by_char[char_id] = session

    def find_by_character(self, char_id: int):
        return self._by_char.get(char_id)

    def find_by_account(self, account_id: int):
        return None

    def sessions_in_room(self, room_id: int, *, source_char=None):
        return list(self._by_char.values())


def _ctx_for(session, db, sm, command: str, args: str):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"{command} {args}".strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
        session_mgr=sm,
    )


# ═════════════════════════════════════════════════════════════════════
# 1. Happy path: bonded Padawan runs +leave-master <reason>
# ═════════════════════════════════════════════════════════════════════


class TestLeaveMasterHappyPath(unittest.TestCase):

    def test_leave_master_dissolves_bond(self):
        """Bond status becomes 'dissolved' and dissolved_reason contains
        'padawan_voluntary' prefix plus the player-supplied text."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master",
                         "path diverged")
            )

            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "dissolved",
                             f"Expected dissolved; got {bond['bond_status']}")
            dr = bond["dissolved_reason"] or ""
            self.assertIn("padawan_voluntary", dr,
                          f"dissolved_reason missing padawan_voluntary: {dr!r}")
            self.assertIn("path diverged", dr,
                          f"dissolved_reason missing player reason: {dr!r}")
        _run(_check())

    def test_leave_master_confirms_to_padawan(self):
        """Padawan receives a confirmation echo."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master",
                         "needed space")
            )
            all_output = " ".join(p_sess.sent)
            self.assertIn("Mira", all_output,
                          f"Expected Master name in echo; got: {p_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 2. No active bond → friendly message, nothing dissolved
# ═════════════════════════════════════════════════════════════════════


class TestLeaveMasterNoBond(unittest.TestCase):

    def test_no_bond_gives_friendly_message(self):
        """Padawan with no active bond gets the no-bond message."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Sela"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+leave-master", "no reason")
            )
            all_output = " ".join(sess.sent)
            self.assertIn("no active Master bond", all_output,
                          f"Expected no-bond message; got: {sess.sent}")
        _run(_check())

    def test_no_bond_dissolves_nothing(self):
        """With no bond there is nothing to dissolve (sanity check)."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Sela"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+leave-master", "a reason")
            )
            # No active bond can be fetched for this char.
            bond = await db.get_active_bond_for_padawan(chars["Sela"]["id"])
            self.assertIsNone(bond)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. No reason provided → block dissolution
# ═════════════════════════════════════════════════════════════════════


class TestLeaveMasterNoReason(unittest.TestCase):

    def test_empty_reason_is_blocked(self):
        """Supplying no reason must not dissolve the bond."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            # Empty args string — no reason.
            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master", "")
            )

            # Bond must still be active.
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "active",
                             "Bond should still be active when no reason given")
        _run(_check())

    def test_empty_reason_shows_usage(self):
        """Without a reason the command echoes usage guidance."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master", "")
            )
            all_output = " ".join(p_sess.sent).lower()
            self.assertTrue(
                "reason" in all_output or "usage" in all_output,
                f"Expected reason/usage hint; got: {p_sess.sent}",
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. Online Master is notified
# ═════════════════════════════════════════════════════════════════════


class TestLeaveMasterMasterNotified(unittest.TestCase):

    def test_online_master_receives_notification(self):
        """When the Master is online, they get a notification line."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Sela"]["id"], p_sess)
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master",
                         "felt the Force pull elsewhere")
            )

            # Master's session should have received at least one line.
            self.assertTrue(
                len(m_sess.sent) > 0,
                "Master should have been notified but received nothing",
            )
            # The notification should reference the Padawan's name.
            all_master_output = " ".join(m_sess.sent)
            self.assertIn("Sela", all_master_output,
                          f"Master notification missing Padawan name: "
                          f"{m_sess.sent}")
        _run(_check())

    def test_both_sides_have_bond_dissolved_log(self):
        """pc_action_log must record bond_dissolved on both char ids."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_commands import LeaveMasterCommand
            cmd = LeaveMasterCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+leave-master",
                         "time to walk alone")
            )

            p_actions = await db.get_recent_actions(
                chars["Sela"]["id"], limit=10
            )
            m_actions = await db.get_recent_actions(
                chars["Mira"]["id"], limit=10
            )
            self.assertTrue(
                any(a["action_type"] == "bond_dissolved"
                    for a in p_actions),
                "Padawan side: expected bond_dissolved log entry",
            )
            self.assertTrue(
                any(a["action_type"] == "bond_dissolved"
                    for a in m_actions),
                "Master side: expected bond_dissolved log entry",
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. +padawan output includes trials count per Padawan
# ═════════════════════════════════════════════════════════════════════


class TestPadawanTrialsParity(unittest.TestCase):

    def test_padawan_command_shows_trials_count_zero(self):
        """With no trials passed, +padawan shows 'Trials passed: 0 of 5'."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_commands import PadawanCommand
            cmd = PadawanCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+padawan", "")
            )

            all_output = " ".join(m_sess.sent)
            self.assertIn("Trials passed:", all_output,
                          f"Expected 'Trials passed:' in output; "
                          f"got: {m_sess.sent}")
            self.assertIn("0 of 5", all_output,
                          f"Expected '0 of 5'; got: {m_sess.sent}")
        _run(_check())

    def test_padawan_command_shows_correct_trials_count(self):
        """With 2 trials passed, +padawan shows 'Trials passed: 2 of 5'."""
        async def _check():
            import json as _json
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )
            # Manually set 2 trials on the bond row.
            await db._db.execute(
                "UPDATE master_padawan_bond SET trials_passed_json = ? "
                "WHERE id = ?",
                (_json.dumps(["Skill", "Courage"]), bond_id),
            )
            await db._db.commit()

            from parser.padawan_master_commands import PadawanCommand
            cmd = PadawanCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+padawan", "")
            )

            all_output = " ".join(m_sess.sent)
            self.assertIn("Trials passed:", all_output,
                          f"Expected 'Trials passed:'; got: {m_sess.sent}")
            self.assertIn("2 of 5", all_output,
                          f"Expected '2 of 5'; got: {m_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. Registration smoke
# ═════════════════════════════════════════════════════════════════════


class TestLeaveMasterRegistered(unittest.TestCase):

    def test_leave_master_registers_under_key(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_commands import (
            register_padawan_master_commands,
        )
        reg = CommandRegistry()
        register_padawan_master_commands(reg)
        self.assertIsNotNone(
            reg.get("+leave-master"),
            "+leave-master must be registered in the command registry",
        )

    def test_leave_master_alias_registered(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_commands import (
            register_padawan_master_commands,
        )
        reg = CommandRegistry()
        register_padawan_master_commands(reg)
        # 'leavemaster' alias should also resolve.
        self.assertIsNotNone(
            reg.get("leavemaster"),
            "leavemaster alias must be registered",
        )

    def test_all_six_commands_register_cleanly(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_commands import (
            register_padawan_master_commands,
        )
        reg = CommandRegistry()
        register_padawan_master_commands(reg)
        for key in (
            "+master", "+padawan", "+bond", "+release",
            "@bond", "+leave-master",
        ):
            self.assertIsNotNone(
                reg.get(key), f"Command '{key}' not registered"
            )


if __name__ == "__main__":
    unittest.main()
