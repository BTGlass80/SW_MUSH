# -*- coding: utf-8 -*-
"""
tests/test_pm3_trials_and_knight.py — P-M.3 Trials + Knight
promotion (May 20 2026).

P-M.3 ships the launch surface for the Trials and Knight
promotion ceremony per padawan_master_system_design_v1.md §6
and §6.4. Builds on:
  - P-M.1 (schema v28 + DB API record_trial_passed, knight_bond)
  - P-M.2 (the bond commands and look-output markers)

Commands shipped this drop:
  +trials [padawan]            view Trial progress
  +endorse trials <padawan>    Master endorses next attempt
  +trial <name> [<padawan>]    Master attests a pass
  @trial <name> = <padawan>    Staff records a pass
  +knight <padawan>            Master invokes ceremony (hard gate)
  @knight <padawan>            Staff promotes (gate override)

Test sections
=============

  1. TestCanonTrialName              — name normalization helper
  2. TestPassedTrialsFromBond        — JSON decode + canon-filter
  3. TestTrialsCommandSelfView       — Padawan +trials shows own
  4. TestTrialsCommandSingleBond     — Master +trials auto-resolves
  5. TestTrialsCommandNamedTarget    — Master +trials <padawan>
  6. TestTrialsCommandAuthorization  — outsider rejected
  7. TestEndorseSets                 — endorsement flag writes
  8. TestEndorseRequiresActiveBond   — endorsement without bond rejected
  9. TestEndorseRequiresOwnPadawan   — wrong-Master rejected
 10. TestTrialCommandHappyPath       — Master records a pass
 11. TestTrialCommandIdempotent      — re-record returns no-op msg
 12. TestTrialCommandInvalidName     — bad Trial name rejected
 13. TestTrialCommandWrongMaster     — wrong Master rejected
 14. TestTrialCommandConsumesEndorsement — endorsement cleared
 15. TestAdminTrialHappyPath         — @trial works
 16. TestKnightHardGate              — +knight refuses < 5
 17. TestKnightHappyPath             — +knight promotes
 18. TestKnightGrantsForcePoint      — Force Point +1
 19. TestKnightLogsBothSides         — pc_action_log cross-write
 20. TestAdminKnightOverridesGate    — @knight ignores Trials count
 21. TestRegistration                — all 6 commands register
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_chars(db, names: list) -> dict:
    """Create chars; return {name: dict}."""
    await db._db.execute(
        """INSERT OR IGNORE INTO accounts
           (username, password_hash, email)
           VALUES ('test', 'hash', 't@e.com')"""
    )
    out = {}
    for n in names:
        cur = await db._db.execute(
            """INSERT INTO characters
               (account_id, name, species, room_id, force_points)
               VALUES (1, ?, 'Human', 1, 1)""",
            (n,),
        )
        out[n] = cur.lastrowid
    await db._db.commit()
    chars = {}
    for n, cid in out.items():
        chars[n] = await db.get_character(cid)
    return chars


class _FakeSession:
    def __init__(self, character=None, *, admin=False):
        self.character = character
        self.is_in_game = character is not None
        self.account = {"is_admin": 1 if admin else 0,
                        "is_builder": 0}
        self.sent: list = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def __init__(self):
        self._by_char: dict = {}

    def register(self, char_id: int, session: _FakeSession) -> None:
        self._by_char[char_id] = session

    def find_by_character(self, char_id: int):
        return self._by_char.get(char_id)


def _ctx_for(session, db, sm, command: str, args: str):
    from parser.commands import CommandContext
    return CommandContext(
        session=session, raw_input=f"{command} {args}".strip(),
        command=command, args=args,
        args_list=args.split() if args else [],
        db=db, session_mgr=sm,
    )


# ═════════════════════════════════════════════════════════════════════
# 1. _canon_trial_name normalization
# ═════════════════════════════════════════════════════════════════════


class TestCanonTrialName(unittest.TestCase):

    def test_bare_lowercase(self):
        from parser.padawan_master_trials import _canon_trial_name
        for t in ("skill", "courage", "flesh", "spirit", "insight"):
            self.assertEqual(_canon_trial_name(t), t)

    def test_uppercase_normalized(self):
        from parser.padawan_master_trials import _canon_trial_name
        self.assertEqual(_canon_trial_name("SKILL"), "skill")
        self.assertEqual(_canon_trial_name("Insight"), "insight")

    def test_trial_of_prefix_stripped(self):
        from parser.padawan_master_trials import _canon_trial_name
        self.assertEqual(_canon_trial_name("Trial of Skill"), "skill")
        self.assertEqual(_canon_trial_name("trial_of_courage"), "courage")
        self.assertEqual(_canon_trial_name("Trial-of-Insight"), "insight")

    def test_unknown_returns_none(self):
        from parser.padawan_master_trials import _canon_trial_name
        self.assertIsNone(_canon_trial_name(""))
        self.assertIsNone(_canon_trial_name("kindness"))
        self.assertIsNone(_canon_trial_name("Trial of Honor"))


# ═════════════════════════════════════════════════════════════════════
# 2. _passed_trials_from_bond
# ═════════════════════════════════════════════════════════════════════


class TestPassedTrialsFromBond(unittest.TestCase):

    def test_empty_json_returns_empty(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        self.assertEqual(_passed_trials_from_bond({"trials_passed_json": "[]"}), [])

    def test_canon_names_round_trip(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        bond = {"trials_passed_json": '["skill", "courage"]'}
        self.assertEqual(
            _passed_trials_from_bond(bond), ["skill", "courage"]
        )

    def test_malformed_json_returns_empty(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        self.assertEqual(
            _passed_trials_from_bond({"trials_passed_json": "not-json"}),
            [],
        )

    def test_non_string_entries_dropped(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        bond = {"trials_passed_json": '["skill", 42, null, "spirit"]'}
        self.assertEqual(
            _passed_trials_from_bond(bond), ["skill", "spirit"]
        )

    def test_unknown_names_dropped(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        bond = {"trials_passed_json": '["skill", "honor", "courage"]'}
        self.assertEqual(
            _passed_trials_from_bond(bond), ["skill", "courage"]
        )

    def test_dedup_preserved(self):
        from parser.padawan_master_trials import (
            _passed_trials_from_bond,
        )
        bond = {"trials_passed_json": '["skill", "skill", "skill"]'}
        # First occurrence wins; duplicates dropped.
        self.assertEqual(_passed_trials_from_bond(bond), ["skill"])


# ═════════════════════════════════════════════════════════════════════
# 3. +trials — Padawan self-view
# ═════════════════════════════════════════════════════════════════════


class TestTrialsCommandSelfView(unittest.TestCase):

    def test_padawan_bare_trials_shows_own(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Mira", "Sela"])
            bond_id = await db.create_bond(
                chars["Mira"]["id"], chars["Sela"]["id"]
            )
            await db.record_trial_passed(bond_id, "skill")

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Sela"])
            sm.register(chars["Sela"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", ""))
            joined = "\n".join(sess.sent)
            # Strip ANSI for cleaner substring matching on the
            # count line ("1 of 5" — there's an ansi.bold() around
            # the digit in the renderer).
            import re as _re
            joined_plain = _re.sub(r'\x1b\[[0-9;]*m', '', joined)
            self.assertIn("Mira", joined,
                          f"Master name should appear: {sess.sent}")
            self.assertIn("Trial of Skill", joined,
                          f"Trial labels should appear: {sess.sent}")
            self.assertIn("1 of 5", joined_plain,
                          f"Count line: {sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. +trials — Master single-bond auto
# ═════════════════════════════════════════════════════════════════════


class TestTrialsCommandSingleBond(unittest.TestCase):

    def test_master_bare_trials_with_one_bond_shows_padawan(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Yoda", "Asoka"])
            await db.create_bond(
                chars["Yoda"]["id"], chars["Asoka"]["id"]
            )

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Yoda"])
            sm.register(chars["Yoda"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", ""))
            joined = "\n".join(sess.sent)
            self.assertIn("Asoka", joined,
                          f"Padawan name in master's view: {sess.sent}")
        _run(_check())

    def test_master_bare_trials_with_no_bond_says_so(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Solo"])

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Solo"])
            sm.register(chars["Solo"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", ""))
            self.assertTrue(
                any("no active bond" in l.lower() for l in sess.sent),
                f"Expected no-bond message: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. +trials — Master with named target
# ═════════════════════════════════════════════════════════════════════


class TestTrialsCommandNamedTarget(unittest.TestCase):

    def test_master_with_named_padawan(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", "P"))
            joined = "\n".join(sess.sent)
            import re as _re
            joined_plain = _re.sub(r'\x1b\[[0-9;]*m', '', joined)
            self.assertIn("P", joined)
            self.assertIn("0 of 5", joined_plain)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. +trials — outsider rejected
# ═════════════════════════════════════════════════════════════════════


class TestTrialsCommandAuthorization(unittest.TestCase):

    def test_outsider_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P", "Outsider"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Outsider"])  # not admin, not in bond
            sm.register(chars["Outsider"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", "P"))
            self.assertTrue(
                any("aren't part of that bond" in l for l in sess.sent),
                f"Expected outsider rejection: {sess.sent}"
            )
        _run(_check())

    def test_admin_can_view(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P", "Adm"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import TrialsCommand
            cmd = TrialsCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Adm"], admin=True)
            sm.register(chars["Adm"]["id"], sess)

            await cmd.execute(_ctx_for(sess, db, sm, "+trials", "P"))
            joined = "\n".join(sess.sent)
            import re as _re
            joined_plain = _re.sub(r'\x1b\[[0-9;]*m', '', joined)
            self.assertIn("0 of 5", joined_plain,
                          f"Admin should be able to view: {sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. +endorse trials writes the flag
# ═════════════════════════════════════════════════════════════════════


class TestEndorseSets(unittest.TestCase):

    def test_endorse_writes_chargen_notes_flag(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import EndorseCommand
            cmd = EndorseCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+endorse", "trials P")
            )
            reloaded = await db.get_character(chars["P"]["id"])
            notes = json.loads(reloaded.get("chargen_notes") or "{}")
            self.assertTrue(notes.get("trial_endorsement_active"))
            self.assertEqual(
                notes.get("trial_endorsement_by_master_id"),
                chars["M"]["id"],
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. +endorse trials without bond rejected
# ═════════════════════════════════════════════════════════════════════


class TestEndorseRequiresActiveBond(unittest.TestCase):

    def test_no_bond_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "Stranger"])

            from parser.padawan_master_trials import EndorseCommand
            cmd = EndorseCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+endorse", "trials Stranger")
            )
            self.assertTrue(
                any("no active Padawan-Master" in l for l in sess.sent),
                f"Expected no-bond rejection: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. +endorse from wrong Master rejected
# ═════════════════════════════════════════════════════════════════════


class TestEndorseRequiresOwnPadawan(unittest.TestCase):

    def test_other_master_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["MA", "MB", "P"])
            await db.create_bond(chars["MA"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import EndorseCommand
            cmd = EndorseCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["MB"])
            sm.register(chars["MB"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+endorse", "trials P")
            )
            self.assertTrue(
                any("not P's Master" in l or "are not" in l.lower()
                    for l in sess.sent),
                f"Expected wrong-master rejection: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 10. +trial happy path
# ═════════════════════════════════════════════════════════════════════


class TestTrialCommandHappyPath(unittest.TestCase):

    def test_master_records_trial(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "skill P")
            )
            bond = await db.get_bond(bond_id)
            passed = json.loads(bond["trials_passed_json"])
            self.assertIn("skill", passed)
            joined = "\n".join(sess.sent)
            self.assertIn("Recorded", joined)
            self.assertIn("1/5", joined)
        _run(_check())

    def test_bare_trial_with_one_bond(self):
        """+trial skill with no <padawan> uses Master's single bond."""
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "courage")
            )
            bond = await db.get_bond(bond_id)
            passed = json.loads(bond["trials_passed_json"])
            self.assertIn("courage", passed)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11. +trial idempotent
# ═════════════════════════════════════════════════════════════════════


class TestTrialCommandIdempotent(unittest.TestCase):

    def test_re_record_says_already(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            await db.record_trial_passed(bond_id, "skill")

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "skill P")
            )
            self.assertTrue(
                any("Already recorded" in l for l in sess.sent),
                f"Expected idempotent message: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 12. +trial invalid name rejected
# ═════════════════════════════════════════════════════════════════════


class TestTrialCommandInvalidName(unittest.TestCase):

    def test_bad_trial_name_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "kindness P")
            )
            self.assertTrue(
                any("isn't one of the five Trials" in l
                    for l in sess.sent),
                f"Expected bad-trial rejection: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 13. +trial — wrong Master
# ═════════════════════════════════════════════════════════════════════


class TestTrialCommandWrongMaster(unittest.TestCase):

    def test_other_master_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["MA", "MB", "P"])
            await db.create_bond(chars["MA"]["id"], chars["P"]["id"])

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["MB"])
            sm.register(chars["MB"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "skill P")
            )
            self.assertTrue(
                any("not P's Master" in l or "are not" in l.lower()
                    for l in sess.sent),
                f"Expected wrong-master rejection: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 14. +trial consumes endorsement
# ═════════════════════════════════════════════════════════════════════


class TestTrialCommandConsumesEndorsement(unittest.TestCase):

    def test_endorsement_cleared_on_record(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            await db.create_bond(chars["M"]["id"], chars["P"]["id"])
            # Pre-set endorsement flag.
            notes = {"trial_endorsement_active": True,
                     "trial_endorsement_by_master_id": chars["M"]["id"]}
            await db.save_character(
                chars["P"]["id"],
                chargen_notes=json.dumps(notes),
            )

            from parser.padawan_master_trials import TrialCommand
            cmd = TrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+trial", "skill P")
            )
            reloaded = await db.get_character(chars["P"]["id"])
            notes_after = json.loads(
                reloaded.get("chargen_notes") or "{}"
            )
            self.assertNotIn("trial_endorsement_active", notes_after,
                             f"Endorsement should be consumed: "
                             f"{notes_after}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 15. @trial happy path
# ═════════════════════════════════════════════════════════════════════


class TestAdminTrialHappyPath(unittest.TestCase):

    def test_admin_records_with_equals_syntax(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["Yoda", "Asoka", "Staff"])
            bond_id = await db.create_bond(
                chars["Yoda"]["id"], chars["Asoka"]["id"]
            )

            from parser.padawan_master_trials import AdminTrialCommand
            cmd = AdminTrialCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Staff"], admin=True)
            sm.register(chars["Staff"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "@trial", "skill = Asoka")
            )
            bond = await db.get_bond(bond_id)
            passed = json.loads(bond["trials_passed_json"])
            self.assertIn("skill", passed)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 16. +knight hard gate
# ═════════════════════════════════════════════════════════════════════


class TestKnightHardGate(unittest.TestCase):

    def test_knight_with_zero_trials_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )

            from parser.padawan_master_trials import KnightCommand
            cmd = KnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+knight", "P")
            )
            joined = "\n".join(sess.sent)
            self.assertIn("0/5", joined)
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "active",
                             "Knight should not have promoted")
        _run(_check())

    def test_knight_with_4_trials_rejected(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            for t in ("skill", "courage", "flesh", "spirit"):
                await db.record_trial_passed(bond_id, t)

            from parser.padawan_master_trials import KnightCommand
            cmd = KnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+knight", "P")
            )
            joined = "\n".join(sess.sent)
            self.assertIn("4/5", joined)
            self.assertIn("Insight", joined,
                          f"Should list missing Trial: {sess.sent}")
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "active")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 17. +knight happy path
# ═════════════════════════════════════════════════════════════════════


class TestKnightHappyPath(unittest.TestCase):

    def test_knight_with_all_5_promotes(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            for t in ("skill", "courage", "flesh", "spirit", "insight"):
                await db.record_trial_passed(bond_id, t)

            from parser.padawan_master_trials import KnightCommand
            cmd = KnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+knight", "P")
            )
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "knighted")
            self.assertIsNotNone(bond.get("knight_promotion_at"))
            joined = "\n".join(sess.sent)
            self.assertIn("Knight P", joined)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 18. +knight grants Force Point
# ═════════════════════════════════════════════════════════════════════


class TestKnightGrantsForcePoint(unittest.TestCase):

    def test_fp_increments_by_one(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            await db.save_character(chars["P"]["id"], force_points=2)
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            for t in ("skill", "courage", "flesh", "spirit", "insight"):
                await db.record_trial_passed(bond_id, t)

            from parser.padawan_master_trials import KnightCommand
            cmd = KnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+knight", "P")
            )
            reloaded = await db.get_character(chars["P"]["id"])
            self.assertEqual(int(reloaded["force_points"]), 3)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 19. +knight logs both sides
# ═════════════════════════════════════════════════════════════════════


class TestKnightLogsBothSides(unittest.TestCase):

    def test_knight_writes_action_log_for_both(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            for t in ("skill", "courage", "flesh", "spirit", "insight"):
                await db.record_trial_passed(bond_id, t)

            from parser.padawan_master_trials import KnightCommand
            cmd = KnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["M"])
            sm.register(chars["M"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "+knight", "P")
            )
            m_actions = await db.get_recent_actions(
                chars["M"]["id"], limit=10
            )
            p_actions = await db.get_recent_actions(
                chars["P"]["id"], limit=10
            )
            self.assertTrue(
                any(a["action_type"] == "knight_promotion"
                    for a in m_actions)
            )
            self.assertTrue(
                any(a["action_type"] == "knight_promotion"
                    for a in p_actions)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 20. @knight overrides the gate
# ═════════════════════════════════════════════════════════════════════


class TestAdminKnightOverridesGate(unittest.TestCase):

    def test_admin_knight_promotes_with_zero_trials(self):
        async def _check():
            db = await _fresh_db()
            chars = await _make_chars(db, ["M", "P", "Staff"])
            bond_id = await db.create_bond(
                chars["M"]["id"], chars["P"]["id"]
            )
            # NO trials recorded.

            from parser.padawan_master_trials import AdminKnightCommand
            cmd = AdminKnightCommand()
            sm = _FakeSessionManager()
            sess = _FakeSession(chars["Staff"], admin=True)
            sm.register(chars["Staff"]["id"], sess)

            await cmd.execute(
                _ctx_for(sess, db, sm, "@knight", "P")
            )
            bond = await db.get_bond(bond_id)
            self.assertEqual(bond["bond_status"], "knighted",
                             f"@knight should promote without "
                             f"Trials gate: {sess.sent}")
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 21. Registration
# ═════════════════════════════════════════════════════════════════════


class TestRegistration(unittest.TestCase):

    def test_all_six_commands_register(self):
        from parser.commands import CommandRegistry
        from parser.padawan_master_trials import (
            register_padawan_master_trials,
        )
        reg = CommandRegistry()
        register_padawan_master_trials(reg)
        for key in ("+trials", "+endorse", "+trial", "@trial",
                    "+knight", "@knight"):
            self.assertIsNotNone(reg.get(key),
                                 f"Command {key!r} not registered")


if __name__ == "__main__":
    unittest.main()
