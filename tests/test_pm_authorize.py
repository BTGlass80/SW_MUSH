# -*- coding: utf-8 -*-
"""tests/test_pm_authorize.py — T3.13 Padawan/Master gap-close: the
Master pre-authorization surface (`+authorize`).

Resolved design fork PM.approval_pending_store = OPTION C
(pre-authorization only at launch). This drop ships the STORE + display
surface for the §5.3 Master approval-weight, skipping the per-action
+approve/+deny block-and-wait flow (deferred post-launch).

Test sections
=============

  1. TestAuthorizeGrant        — grant writes chargen_notes; idempotent
  2. TestAuthorizeSoleBond     — sole-bond shorthand `+authorize <cat>`
  3. TestAuthorizeRevoke       — `... off` removes the grant
  4. TestAuthorizeValidation   — bad category / no bond / not-the-master
  5. TestAuthorizeList         — master + padawan list views
  6. TestAuthorizeNotify       — padawan notified on grant
  7. TestTrialsEndorsementLine — +trials consumes the standing grant
  8. TestAuthorizeRegistered   — +authorize registers
"""
from __future__ import annotations

import asyncio
import json
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
    def __init__(self, character=None, *, is_admin=1):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": is_admin, "is_builder": is_admin}
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


async def _read_auths(db, char_id: int) -> list:
    """Read the stored master_authorizations list off a character."""
    char = await db.get_character(char_id)
    raw = char.get("chargen_notes") or "{}"
    try:
        notes = json.loads(raw)
    except (ValueError, TypeError):
        return []
    val = notes.get("master_authorizations")
    return val if isinstance(val, list) else []


# ═════════════════════════════════════════════════════════════════════
# 1. Grant happy path
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeGrant(unittest.TestCase):

    def test_grant_writes_authorization(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))

            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertIn("trials", auths,
                          f"Expected 'trials' stored; got {auths}")
        _run(_check())

    def test_grant_alias_normalizes(self):
        """`force` is an alias for the canonical `powers` category."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela force"))

            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertIn("powers", auths,
                          f"Alias 'force' should store 'powers'; got {auths}")
        _run(_check())

    def test_grant_twice_is_idempotent(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))
            m_sess.sent.clear()
            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))

            out = " ".join(m_sess.sent).lower()
            self.assertIn("already", out,
                          f"Second grant should report already-set; "
                          f"got {m_sess.sent}")
            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertEqual(auths.count("trials"), 1,
                             f"trials should appear once; got {auths}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 2. Sole-bond shorthand
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeSoleBond(unittest.TestCase):

    def test_sole_bond_category_shorthand(self):
        """A Master with one Padawan can `+authorize <category>`."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "offworld"))

            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertIn("offworld", auths,
                          f"Shorthand grant failed; got {auths}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. Revoke
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeRevoke(unittest.TestCase):

    def test_revoke_removes_grant(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))
            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials off"))

            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertNotIn("trials", auths,
                             f"trials should be revoked; got {auths}")
        _run(_check())

    def test_revoke_when_absent_is_noop(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials off"))

            out = " ".join(m_sess.sent).lower()
            self.assertIn("nothing to revoke", out,
                          f"Expected nothing-to-revoke; got {m_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. Validation
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeValidation(unittest.TestCase):

    def test_invalid_category_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela banana"))

            out = " ".join(m_sess.sent).lower()
            self.assertIn("category", out,
                          f"Expected category error; got {m_sess.sent}")
            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertEqual(auths, [],
                             f"Nothing should be stored; got {auths}")
        _run(_check())

    def test_no_bond_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            # No bond between them.

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))

            out = " ".join(m_sess.sent).lower()
            self.assertIn("no active", out,
                          f"Expected no-bond message; got {m_sess.sent}")
        _run(_check())

    def test_non_master_rejected(self):
        """A non-admin third party cannot authorize another's Padawan."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela", "Dax"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            # Dax is not Sela's Master and not admin.
            d_sess = _FakeSession(chars["Dax"], is_admin=0)
            sm.register(chars["Dax"]["id"], d_sess)

            await cmd.execute(
                _ctx_for(d_sess, db, sm, "+authorize", "Sela trials"))

            out = " ".join(d_sess.sent).lower()
            self.assertIn("not", out,
                          f"Expected not-the-master rejection; "
                          f"got {d_sess.sent}")
            auths = await _read_auths(db, chars["Sela"]["id"])
            self.assertEqual(auths, [],
                             f"Nothing should be stored; got {auths}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. List views
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeList(unittest.TestCase):

    def test_master_list_shows_states(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))
            m_sess.sent.clear()
            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela"))

            out = " ".join(m_sess.sent)
            self.assertIn("trials", out,
                          f"List should mention trials; got {m_sess.sent}")
            self.assertIn("CLEARED", out,
                          f"Granted category should show CLEARED; "
                          f"got {m_sess.sent}")
            self.assertIn("offworld", out,
                          f"List should enumerate all categories; "
                          f"got {m_sess.sent}")
        _run(_check())

    def test_padawan_bare_list(self):
        """A Padawan running bare +authorize sees their own clearances."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela powers"))
            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+authorize", ""))

            out = " ".join(p_sess.sent)
            self.assertIn("pre-authorized", out.lower(),
                          f"Padawan view header missing; got {p_sess.sent}")
            self.assertIn("powers", out,
                          f"Padawan should see 'powers'; got {p_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. Notification
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeNotify(unittest.TestCase):

    def test_padawan_notified_on_grant(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])

            from parser.padawan_master_trials import AuthorizeCommand
            cmd = AuthorizeCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))

            self.assertTrue(len(p_sess.sent) > 0,
                            "Padawan should have been notified")
            out = " ".join(p_sess.sent)
            self.assertIn("Mira", out,
                          f"Notification should name the Master; "
                          f"got {p_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. +trials consumes the standing grant (real consumer)
# ═════════════════════════════════════════════════════════════════════


class TestTrialsEndorsementLine(unittest.TestCase):

    async def _setup_bond(self, db, names=("Mira", "Sela")):
        chars = await _make_chars(db, list(names))
        await db.create_bond(chars[names[0]]["id"], chars[names[1]]["id"])
        return chars

    def test_standing_when_trials_authorized(self):
        async def _check():
            db = await _fresh_db()
            chars = await self._setup_bond(db)

            from parser.padawan_master_trials import (
                AuthorizeCommand, TrialsCommand,
            )
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            await AuthorizeCommand().execute(
                _ctx_for(m_sess, db, sm, "+authorize", "Sela trials"))
            await TrialsCommand().execute(
                _ctx_for(p_sess, db, sm, "+trials", ""))

            out = " ".join(p_sess.sent)
            self.assertIn("Endorsement:", out,
                          f"+trials must show endorsement line; "
                          f"got {p_sess.sent}")
            self.assertIn("standing", out,
                          f"Authorized trials → standing; got {p_sess.sent}")
        _run(_check())

    def test_none_when_unendorsed(self):
        async def _check():
            db = await _fresh_db()
            chars = await self._setup_bond(db)

            from parser.padawan_master_trials import TrialsCommand
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await TrialsCommand().execute(
                _ctx_for(p_sess, db, sm, "+trials", ""))

            out = " ".join(p_sess.sent)
            self.assertIn("Endorsement:", out,
                          f"Expected endorsement line; got {p_sess.sent}")
            self.assertIn("none", out,
                          f"Unendorsed → none; got {p_sess.sent}")
        _run(_check())

    def test_ready_when_oneshot_endorsed(self):
        async def _check():
            db = await _fresh_db()
            chars = await self._setup_bond(db)
            # Plant a one-shot +endorse flag on the Padawan.
            await db.save_character(
                chars["Sela"]["id"],
                chargen_notes=json.dumps(
                    {"trial_endorsement_active": True}),
            )

            from parser.padawan_master_trials import TrialsCommand
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await TrialsCommand().execute(
                _ctx_for(p_sess, db, sm, "+trials", ""))

            out = " ".join(p_sess.sent)
            self.assertIn("ready", out,
                          f"One-shot endorse → ready; got {p_sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. Registration smoke
# ═════════════════════════════════════════════════════════════════════


class TestAuthorizeRegistered(unittest.TestCase):

    def test_authorize_registers(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_trials import (
            register_padawan_master_trials,
        )
        reg = CommandRegistry()
        register_padawan_master_trials(reg)
        self.assertIsNotNone(
            reg.get("+authorize"),
            "+authorize must be registered in the command registry",
        )


if __name__ == "__main__":
    unittest.main()
