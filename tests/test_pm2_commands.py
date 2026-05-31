# -*- coding: utf-8 -*-
"""tests/test_pm2_commands.py — P-M.2 Padawan-Master command layer
(May 20, 2026).

P-M.2 ships the launch command surface on top of P-M.1's DB API:

  +master              — Padawan: see bonded Master's status
  +padawan             — Master: see bonded Padawan(s) status
  +bond <padawan>      — Master: propose bond (player-flow path)
  +bond accept <m>     — Padawan: accept pending proposal
  +bond decline <m>    — Padawan: decline pending proposal
  +release [padawan]   — Master: voluntary dissolve (narrative event)
  @bond <m> = <p>      — Admin: direct establishment

Design calls locked (per v45 §8.12):

  1. +bond auth:        BOTH admin + player flow
  2. +release:          Voluntary + Padawan-side narrative event
                        (pc_action_log cross-write seam)
  3. Master-cap:        DB-driven via v29 characters.master_cap column
  4. look markers:      Padawan = bright green, Master = bright cyan

Test sections
=============

  1. TestSchemaV29Migration            — master_cap column ships at v29
  2. TestMasterCapWritable             — _CHARACTER_WRITABLE_COLUMNS includes it
  3. TestBondRolesBatchLookup          — db.get_bond_roles_for_chars
  4. TestProposalStoreTTL              — _pending_bond_proposals + pruning
  5. TestBondCommandProposeHappyPath   — +bond <padawan> in same room
  6. TestBondCommandProposeMasterCap   — cap-enforce gate
  7. TestBondCommandAcceptHappyPath    — +bond accept creates bond
  8. TestBondCommandAcceptStaleState   — Padawan-already-bonded race
  9. TestBondCommandDecline            — +bond decline removes proposal
 10. TestReleaseCommandHappyPath       — dissolves + logs both sides
 11. TestReleaseCommandSingleBondAuto  — convenience: no arg w/ 1 bond
 12. TestReleaseCommandLogCrossWrite   — pc_action_log on both sides
 13. TestAdminBondHappyPath            — @bond <m> = <p> direct path
 14. TestAdminBondCapEnforced          — @bond also gates on master_cap
 15. TestMarkerLiterals                — byte-grep on marker constants
 16. TestMarkerLiteralsInLookCode      — markers used in builtin_commands
 17. TestRegistration                  — all 5 commands register cleanly
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


DATABASE_PY = PROJECT_ROOT / "db" / "database.py"
PADAWAN_MASTER_PY = PROJECT_ROOT / "parser" / "padawan_master_commands.py"
BUILTIN_PY = PROJECT_ROOT / "parser" / "builtin_commands.py"


# ───── shared fixtures ─────────────────────────────────────────────────────

async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names: list) -> dict:
    """Create the given characters; return {name: char_dict}.

    All chars are at room_id=1 by default. Tests that need
    co-location vs. separation can move them via direct UPDATE.
    """
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
    """Minimal Session stand-in for command execution tests."""

    def __init__(self, character: dict | None = None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 1, "is_builder": 1}
        self.sent: list[str] = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    """Minimal SessionManager stand-in.

    Holds a dict of character_id -> _FakeSession so commands can
    find_by_character() and push notifications. Tests that don't
    care about cross-session delivery can leave it empty.
    """

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
    """Build a CommandContext analog for tests."""
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
# 1. Schema v29 migration
# ═════════════════════════════════════════════════════════════════════


class TestSchemaV29Migration(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(DATABASE_PY)

    def test_schema_version_at_least_29(self):
        m = re.search(r'^\s*SCHEMA_VERSION\s*=\s*(\d+)',
                      self.src, re.MULTILINE)
        self.assertIsNotNone(m)
        self.assertGreaterEqual(int(m.group(1)), 29)

    def test_migration_29_present(self):
        from db.database import MIGRATIONS
        self.assertIn(29, MIGRATIONS)
        stmts = MIGRATIONS[29]
        joined = " ".join(stmts)
        self.assertIn("master_cap", joined)
        self.assertIn("ALTER TABLE characters", joined)

    def test_master_cap_default_is_one(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Kira"])
            self.assertEqual(int(chars["Kira"].get("master_cap") or 0), 1)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 2. _CHARACTER_WRITABLE_COLUMNS includes master_cap
# ═════════════════════════════════════════════════════════════════════


class TestMasterCapWritable(unittest.TestCase):

    def test_master_cap_in_writable_allowlist(self):
        from db.database import Database
        db = Database(":memory:")
        self.assertIn("master_cap", db._CHARACTER_WRITABLE_COLUMNS)

    def test_save_character_accepts_master_cap(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Yoda"])
            await db.save_character(chars["Yoda"]["id"], master_cap=3)
            reloaded = await db.get_character(chars["Yoda"]["id"])
            self.assertEqual(int(reloaded["master_cap"]), 3)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. Batched bond-role lookup
# ═════════════════════════════════════════════════════════════════════


class TestBondRolesBatchLookup(unittest.TestCase):

    def test_empty_input_returns_empty_dict(self):
        async def _check():
            db = await _fresh_db()
            roles = await db.get_bond_roles_for_chars([])
            self.assertEqual(roles, {})
        _run(_check())

    def test_unbonded_chars_return_none(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["A", "B"])
            roles = await db.get_bond_roles_for_chars(
                [chars["A"]["id"], chars["B"]["id"]]
            )
            self.assertIsNone(roles[chars["A"]["id"]])
            self.assertIsNone(roles[chars["B"]["id"]])
        _run(_check())

    def test_bonded_pair_classified_correctly(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(chars["Mira"]["id"], chars["Sela"]["id"])
            roles = await db.get_bond_roles_for_chars(
                [chars["Mira"]["id"], chars["Sela"]["id"]]
            )
            self.assertEqual(roles[chars["Mira"]["id"]], "master")
            self.assertEqual(roles[chars["Sela"]["id"]], "padawan")
        _run(_check())

    def test_single_select_batched(self):
        """Confirm the batched lookup returns correct roles for
        a mixed input (some bonded, some not) in one call."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M1", "P1", "Other"])
            await db.create_bond(chars["M1"]["id"], chars["P1"]["id"])
            ids = [chars["M1"]["id"], chars["P1"]["id"],
                   chars["Other"]["id"]]
            roles = await db.get_bond_roles_for_chars(ids)
            self.assertEqual(roles[chars["M1"]["id"]], "master")
            self.assertEqual(roles[chars["P1"]["id"]], "padawan")
            self.assertIsNone(roles[chars["Other"]["id"]])
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. Pending-proposal TTL
# ═════════════════════════════════════════════════════════════════════


class TestProposalStoreTTL(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()
        self.pmc = pmc

    def test_proposal_pruned_after_ttl(self):
        from parser.padawan_master_commands import (
            _pending_bond_proposals, _prune_expired_proposals,
            _BOND_PROPOSAL_TTL,
        )
        now = time.time()
        _pending_bond_proposals[(1, 2)] = now - _BOND_PROPOSAL_TTL - 1
        _pending_bond_proposals[(3, 4)] = now
        _prune_expired_proposals(now=now)
        self.assertNotIn((1, 2), _pending_bond_proposals)
        self.assertIn((3, 4), _pending_bond_proposals)


# ═════════════════════════════════════════════════════════════════════
# 5. +bond <padawan> propose — happy path
# ═════════════════════════════════════════════════════════════════════


class TestBondCommandProposeHappyPath(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()

    def test_propose_records_pending_proposal(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["MasterKira", "PadawanSela"])
            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["MasterKira"])
            p_sess = _FakeSession(chars["PadawanSela"])
            sm.register(chars["MasterKira"]["id"], m_sess)
            sm.register(chars["PadawanSela"]["id"], p_sess)

            ctx = _ctx_for(m_sess, db, sm, "+bond", "PadawanSela")
            await cmd.execute(ctx)

            key = (chars["MasterKira"]["id"], chars["PadawanSela"]["id"])
            self.assertIn(key, _pending_bond_proposals)
            # Padawan was notified
            self.assertTrue(
                any("offers to take you" in line
                    for line in p_sess.sent)
            )
        _run(_check())

    def test_propose_target_not_in_room_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mk", "Ps"])
            # Move Padawan to a different room.
            await db._db.execute(
                "UPDATE characters SET room_id = 99 WHERE id = ?",
                (chars["Ps"]["id"],),
            )
            await db._db.commit()
            chars["Mk"] = await db.get_character(chars["Mk"]["id"])

            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mk"])
            sm.register(chars["Mk"]["id"], m_sess)

            ctx = _ctx_for(m_sess, db, sm, "+bond", "Ps")
            await cmd.execute(ctx)

            self.assertEqual(_pending_bond_proposals, {})
            self.assertTrue(
                any("No player named" in line for line in m_sess.sent)
            )
        _run(_check())

    def test_propose_self_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo"])
            from parser.padawan_master_commands import BondCommand
            cmd = BondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Solo"])
            sm.register(chars["Solo"]["id"], sess)

            ctx = _ctx_for(sess, db, sm, "+bond", "Solo")
            await cmd.execute(ctx)
            self.assertTrue(
                any("cannot bond with yourself" in line
                    for line in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. Master-cap gate
# ═════════════════════════════════════════════════════════════════════


class TestBondCommandProposeMasterCap(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()

    def test_propose_rejected_when_at_cap(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(
                db, ["M", "ExistingP", "WantedP"]
            )
            # Already have one active bond (matches default cap=1).
            await db.create_bond(chars["M"]["id"],
                                 chars["ExistingP"]["id"])
            chars["M"] = await db.get_character(chars["M"]["id"])

            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            ctx = _ctx_for(sess, db, sm, "+bond", "WantedP")
            await cmd.execute(ctx)

            self.assertEqual(_pending_bond_proposals, {})
            self.assertTrue(
                any("master_cap" in line for line in sess.sent),
                f"Expected cap-rejection; got: {sess.sent}",
            )
        _run(_check())

    def test_propose_allowed_when_cap_raised(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(
                db, ["Yoda", "Padawan1", "Padawan2"]
            )
            # Raise Yoda's cap to 2.
            await db.save_character(chars["Yoda"]["id"], master_cap=2)
            await db.create_bond(chars["Yoda"]["id"],
                                 chars["Padawan1"]["id"])
            chars["Yoda"] = await db.get_character(chars["Yoda"]["id"])

            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Yoda"])
            p2_sess = _FakeSession(chars["Padawan2"])
            sm.register(chars["Yoda"]["id"], sess)
            sm.register(chars["Padawan2"]["id"], p2_sess)

            ctx = _ctx_for(sess, db, sm, "+bond", "Padawan2")
            await cmd.execute(ctx)

            key = (chars["Yoda"]["id"], chars["Padawan2"]["id"])
            self.assertIn(key, _pending_bond_proposals)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. +bond accept — happy path
# ═════════════════════════════════════════════════════════════════════


class TestBondCommandAcceptHappyPath(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()

    def test_accept_creates_active_bond(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])

            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            # Master proposes
            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+bond", "Sela")
            )
            self.assertIn(
                (chars["Mira"]["id"], chars["Sela"]["id"]),
                _pending_bond_proposals,
            )

            # Padawan accepts
            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+bond", "accept Mira")
            )

            bond = await db.get_active_bond_for_padawan(
                chars["Sela"]["id"]
            )
            self.assertIsNotNone(bond)
            self.assertEqual(bond["master_char_id"], chars["Mira"]["id"])
            # Proposal cleaned up
            self.assertNotIn(
                (chars["Mira"]["id"], chars["Sela"]["id"]),
                _pending_bond_proposals,
            )
        _run(_check())

    def test_accept_with_no_pending_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Phantom", "Sela"])
            from parser.padawan_master_commands import BondCommand
            cmd = BondCommand()
            sm = _FakeSessionManager()
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+bond", "accept Phantom")
            )
            bond = await db.get_active_bond_for_padawan(
                chars["Sela"]["id"]
            )
            self.assertIsNone(bond)
            self.assertTrue(
                any("No pending bond proposal" in line
                    for line in p_sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. +bond accept — Padawan-already-bonded race
# ═════════════════════════════════════════════════════════════════════


class TestBondCommandAcceptStaleState(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()

    def test_accept_voids_proposal_if_padawan_already_bonded(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(
                db, ["MasterA", "MasterB", "Sela"]
            )

            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            ma_sess = _FakeSession(chars["MasterA"])
            mb_sess = _FakeSession(chars["MasterB"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["MasterA"]["id"], ma_sess)
            sm.register(chars["MasterB"]["id"], mb_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            # MasterA proposes, Sela accepts.
            await cmd.execute(
                _ctx_for(ma_sess, db, sm, "+bond", "Sela")
            )
            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+bond", "accept MasterA")
            )
            # Now MasterB proposes (DB-level Padawan check skipped
            # at propose because Sela isn't bonded YET in MasterB's
            # head). Actually we DO check — so this propose itself
            # is rejected. Exercise the accept-time stale check by
            # manually injecting a proposal as if it raced.
            _pending_bond_proposals[
                (chars["MasterB"]["id"], chars["Sela"]["id"])
            ] = time.time()

            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+bond", "accept MasterB")
            )
            # Sela's active bond is still MasterA.
            bond = await db.get_active_bond_for_padawan(
                chars["Sela"]["id"]
            )
            self.assertEqual(bond["master_char_id"],
                             chars["MasterA"]["id"])
            # Stale proposal cleaned up.
            self.assertNotIn(
                (chars["MasterB"]["id"], chars["Sela"]["id"]),
                _pending_bond_proposals,
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. +bond decline
# ═════════════════════════════════════════════════════════════════════


class TestBondCommandDecline(unittest.TestCase):

    def setUp(self):
        from parser import padawan_master_commands as pmc
        pmc._pending_bond_proposals.clear()

    def test_decline_removes_proposal(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            from parser.padawan_master_commands import (
                BondCommand, _pending_bond_proposals,
            )
            cmd = BondCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+bond", "Sela")
            )
            await cmd.execute(
                _ctx_for(p_sess, db, sm, "+bond", "decline Mira")
            )
            self.assertNotIn(
                (chars["Mira"]["id"], chars["Sela"]["id"]),
                _pending_bond_proposals,
            )
            # No bond created
            bond = await db.get_active_bond_for_padawan(
                chars["Sela"]["id"]
            )
            self.assertIsNone(bond)
            # Master was notified of decline
            self.assertTrue(
                any("declined" in line.lower() for line in m_sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 10. +release — happy path
# ═════════════════════════════════════════════════════════════════════


class TestReleaseCommandHappyPath(unittest.TestCase):

    def test_release_dissolves_active_bond(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )

            from parser.padawan_master_commands import ReleaseCommand
            cmd = ReleaseCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            p_sess = _FakeSession(chars["Sela"])
            sm.register(chars["Mira"]["id"], m_sess)
            sm.register(chars["Sela"]["id"], p_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+release",
                         "Sela = guidance complete")
            )
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "dissolved")
            self.assertEqual(bond["dissolved_reason"],
                             "guidance complete")
            # Padawan was notified
            self.assertTrue(
                any("go quiet" in line for line in p_sess.sent),
                f"Expected Padawan-side narrative line; got "
                f"{p_sess.sent}",
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11. +release — single-bond convenience
# ═════════════════════════════════════════════════════════════════════


class TestReleaseCommandSingleBondAuto(unittest.TestCase):

    def test_no_arg_with_single_bond_releases_it(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )

            from parser.padawan_master_commands import ReleaseCommand
            cmd = ReleaseCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+release", "")
            )
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "dissolved")
        _run(_check())

    def test_no_arg_with_no_bonds_says_nothing_to_release(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira"])
            from parser.padawan_master_commands import ReleaseCommand
            cmd = ReleaseCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+release", ""))
            self.assertTrue(
                any("no active padawan bonds" in line.lower()
                    for line in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 12. +release writes narrative log on BOTH sides
# ═════════════════════════════════════════════════════════════════════


class TestReleaseCommandLogCrossWrite(unittest.TestCase):

    def test_release_logs_action_on_both_chars(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )

            from parser.padawan_master_commands import ReleaseCommand
            cmd = ReleaseCommand()
            sm = _FakeSessionManager()
            m_sess = _FakeSession(chars["Mira"])
            sm.register(chars["Mira"]["id"], m_sess)

            await cmd.execute(
                _ctx_for(m_sess, db, sm, "+release",
                         "Sela = path diverges")
            )

            # Both sides have action log entries.
            m_actions = await db.get_recent_actions(
                chars["Mira"]["id"], limit=10
            )
            p_actions = await db.get_recent_actions(
                chars["Sela"]["id"], limit=10
            )
            self.assertTrue(
                any(a["action_type"] == "bond_dissolved"
                    for a in m_actions)
            )
            self.assertTrue(
                any(a["action_type"] == "bond_dissolved"
                    for a in p_actions)
            )
            # Padawan's log records the Master's name.
            p_summary = next(
                a["summary"] for a in p_actions
                if a["action_type"] == "bond_dissolved"
            )
            self.assertIn("Mira", p_summary)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 13. @bond admin — direct establishment
# ═════════════════════════════════════════════════════════════════════


class TestAdminBondHappyPath(unittest.TestCase):

    def test_admin_bond_creates_active_bond(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["YodaM", "AsokaP"])

            from parser.padawan_master_commands import AdminBondCommand
            cmd = AdminBondCommand()
            sm = _FakeSessionManager()
            admin_sess = _FakeSession(chars["YodaM"])  # admin flag set
            sm.register(chars["YodaM"]["id"], admin_sess)

            await cmd.execute(
                _ctx_for(admin_sess, db, sm, "@bond",
                         "YodaM = AsokaP")
            )
            bond = await db.get_active_bond_for_padawan(
                chars["AsokaP"]["id"]
            )
            self.assertIsNotNone(bond)
            self.assertEqual(bond["master_char_id"],
                             chars["YodaM"]["id"])
        _run(_check())

    def test_admin_bond_missing_equals_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["A", "B"])
            from parser.padawan_master_commands import AdminBondCommand
            cmd = AdminBondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["A"])
            sm.register(chars["A"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "@bond", "A B")  # no '='
            )
            self.assertTrue(
                any("Usage" in line for line in sess.sent)
            )
        _run(_check())

    def test_admin_bond_unknown_master_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Real"])
            from parser.padawan_master_commands import AdminBondCommand
            cmd = AdminBondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Real"])
            sm.register(chars["Real"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "@bond", "Ghost = Real")
            )
            self.assertTrue(
                any("'Ghost'" in line for line in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 14. @bond also enforces master_cap
# ═════════════════════════════════════════════════════════════════════


class TestAdminBondCapEnforced(unittest.TestCase):

    def test_admin_bond_rejected_at_cap(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P1", "P2"])
            await db.create_bond(chars["M"]["id"], chars["P1"]["id"])

            from parser.padawan_master_commands import AdminBondCommand
            cmd = AdminBondCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "@bond", "M = P2")
            )
            bond = await db.get_active_bond_for_padawan(
                chars["P2"]["id"]
            )
            self.assertIsNone(bond)
            self.assertTrue(
                any("master_cap" in line for line in sess.sent),
                f"Expected cap-rejection; got: {sess.sent}",
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 15. Marker literals (byte-grep pin)
# ═════════════════════════════════════════════════════════════════════


class TestMarkerLiterals(unittest.TestCase):
    """Per v45 §6.2 seventh phantom-pattern: byte-grep + smoke pin
    the marker literals so a refactor that moves them into a dead
    branch is caught at both layers (unit catches symbol drift;
    smoke catches runtime delivery).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(PADAWAN_MASTER_PY)

    def test_padawan_marker_constant_present(self):
        # green = 92, bright variant.
        self.assertIn('PADAWAN_MARKER', self.src)
        self.assertIn('\\033[1;92m[Padawan]\\033[0m', self.src)

    def test_master_marker_constant_present(self):
        # cyan = 96, bright variant.
        self.assertIn('MASTER_MARKER', self.src)
        self.assertIn('\\033[1;96m[Master]\\033[0m', self.src)

    def test_markers_importable(self):
        from parser.padawan_master_commands import (
            PADAWAN_MARKER, MASTER_MARKER,
        )
        self.assertIn("[Padawan]", PADAWAN_MARKER)
        self.assertIn("[Master]", MASTER_MARKER)


# ═════════════════════════════════════════════════════════════════════
# 16. Markers wired into LookCommand
# ═════════════════════════════════════════════════════════════════════


class TestMarkerLiteralsInLookCode(unittest.TestCase):
    """Byte-grep that builtin_commands.LookCommand actually consumes
    PADAWAN_MARKER / MASTER_MARKER. Distinct from the constants
    test above (which only proves the source file has the literals).
    """

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(BUILTIN_PY)

    def test_look_imports_padawan_marker(self):
        self.assertIn("PADAWAN_MARKER", self.src)

    def test_look_imports_master_marker(self):
        self.assertIn("MASTER_MARKER", self.src)

    def test_look_calls_get_bond_roles(self):
        self.assertIn("get_bond_roles_for_chars", self.src)


# ═════════════════════════════════════════════════════════════════════
# 17. Registration smoke
# ═════════════════════════════════════════════════════════════════════


class TestRegistration(unittest.TestCase):

    def test_all_five_commands_register_cleanly(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_commands import (
            register_padawan_master_commands,
        )
        reg = CommandRegistry()
        register_padawan_master_commands(reg)
        for key in ("+master", "+padawan", "+bond", "+release", "@bond"):
            self.assertIsNotNone(reg.get(key),
                                 f"Command '{key}' not registered")


if __name__ == "__main__":
    unittest.main()
