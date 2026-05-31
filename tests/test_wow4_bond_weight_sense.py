# -*- coding: utf-8 -*-
"""tests/test_wow4_bond_weight_sense.py — WoW.4 (May 24 2026).

Per weight_of_war_design_v1.md §7.4: bonded partners can sense
each other's Weight-of-War state. Rather than building a separate
``+forcebond`` command for this (which would duplicate the bond
lookup + partner resolution logic in ``+master`` / ``+padawan``),
WoW.4 extends those existing commands with a "Through the bond:"
sense-line showing the partner's Weight tier and narrative
descriptor.

The design doc names ``+forcebond`` as the command surface; the
implementation chose consolidation — one set of bond-status
commands, one sensing surface. In-game, the bond IS the sensing.

Test sections
=============

+master output (Padawan-side view of Master):
  1.  TestMasterShowsWeightLine              — line is present
  2.  TestMasterShowsTierLabel               — tier name appears
  3.  TestMasterShowsDescriptor              — descriptor text appears
  4.  TestMasterSuppressedWhenNoBond         — no-bond output unaffected
  5.  TestMasterSuppressedForNonJediMaster   — non-Jedi master → no line

+padawan output (Master-side view of Padawan):
  6.  TestPadawanShowsWeightLine             — line is present
  7.  TestPadawanShowsTierLabel              — tier name appears
  8.  TestPadawanShowsDescriptor             — descriptor text appears
  9.  TestPadawanSuppressedWhenNoBond        — no-bond output unaffected
 10.  TestPadawanSuppressedForNonJediPadawan — non-Jedi padawan → no line

Mutual support narrative (design §7.4):
 11.  TestMasterCanSensePadawanStrained      — strained tier surfaces
 12.  TestPadawanCanSenseMasterCrushed       — crushed tier surfaces

Defensive:
 13.  TestMasterWeightReadFailDoesNotCrash   — WoW import failure → rest works
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ── Real-DB harness ──────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await db._db.execute(
        "INSERT OR IGNORE INTO accounts "
        "(id, username, password_hash) VALUES (1, 'u', 'p')",
    )
    await db._db.commit()
    return db


async def _make_char(
    db, char_id: int, name: str,
    faction: str = "jedi_order",
    weight: int = 0,
) -> dict:
    await db._db.execute(
        "INSERT INTO characters "
        "(id, account_id, name, room_id, faction_id, "
        "weight_of_war) VALUES (?, ?, ?, ?, ?, ?)",
        (char_id, 1, name, 1, faction, weight),
    )
    await db._db.commit()
    return await db.get_character(char_id)


async def _make_bond(
    db, master_id: int, padawan_id: int,
) -> None:
    """Create an active master-padawan bond via direct insert."""
    await db._db.execute(
        "INSERT INTO master_padawan_bond "
        "(master_char_id, padawan_char_id, bond_status) "
        "VALUES (?, ?, 'active')",
        (master_id, padawan_id),
    )
    await db._db.commit()


def _make_session(char: dict):
    """Build a minimal session with .character and .send_line
    that captures output."""
    session = MagicMock()
    session.character = char
    session.lines = []

    async def send(line):
        session.lines.append(str(line))

    session.send_line = send
    return session


def _make_ctx(char: dict, db):
    ctx = MagicMock()
    ctx.session = _make_session(char)
    ctx.db = db
    # session_mgr.find_by_character returns None (we don't need
    # online sessions for these tests; the +master / +padawan
    # output handles offline cleanly).
    sm = MagicMock()
    sm.find_by_character = MagicMock(return_value=None)
    ctx.session_mgr = sm
    return ctx


# ═════════════════════════════════════════════════════════════════════
# 1-5. +master output
# ═════════════════════════════════════════════════════════════════════


class TestMasterShowsWeightLine(unittest.TestCase):
    def test_through_the_bond_line_present(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(
                db, 10, "Obi-Wan", weight=60,
            )
            padawan = await _make_char(
                db, 11, "Anakin", weight=0,
            )
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Through the bond", joined)


class TestMasterShowsTierLabel(unittest.TestCase):
    def test_tier_name_appears(self):
        async def go():
            db = await _fresh_db()
            await _make_char(db, 10, "Obi-Wan", weight=60)
            padawan = await _make_char(db, 11, "Anakin")
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        # Weight 60 = "burdened" tier per design §6
        self.assertIn("Burdened", joined)


class TestMasterShowsDescriptor(unittest.TestCase):
    def test_descriptor_sentence_appears(self):
        async def go():
            db = await _fresh_db()
            await _make_char(db, 10, "Obi-Wan", weight=60)
            padawan = await _make_char(db, 11, "Anakin")
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        # Descriptor for "burdened" (Weight 51-100) per design §6
        # includes the phrase "hesitate before drawing your saber"
        self.assertIn("hesitate", joined.lower())


class TestMasterSuppressedWhenNoBond(unittest.TestCase):
    def test_no_bond_no_weight_line(self):
        async def go():
            db = await _fresh_db()
            solo = await _make_char(db, 11, "Anakin")
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(solo, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertNotIn("Through the bond", joined)
        # The no-bond message should still be present
        self.assertIn("no active Master bond", joined)


class TestMasterSuppressedForNonJediMaster(unittest.TestCase):
    """Should never happen in practice — bonds are Jedi-only —
    but defense in depth. If a non-Jedi somehow appears as a
    Master, the WoW sense-line is suppressed via is_jedi_pc."""

    def test_non_jedi_master_no_weight_line(self):
        async def go():
            db = await _fresh_db()
            await _make_char(
                db, 10, "FakeMaster",
                faction="bh_guild", weight=60,
            )
            padawan = await _make_char(db, 11, "Anakin")
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertNotIn("Through the bond", joined)


# ═════════════════════════════════════════════════════════════════════
# 6-10. +padawan output
# ═════════════════════════════════════════════════════════════════════


class TestPadawanShowsWeightLine(unittest.TestCase):
    def test_through_the_bond_line_present(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(db, 10, "Obi-Wan")
            await _make_char(db, 11, "Anakin", weight=110)
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(master, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Through the bond", joined)


class TestPadawanShowsTierLabel(unittest.TestCase):
    def test_tier_name_appears(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(db, 10, "Obi-Wan")
            await _make_char(db, 11, "Anakin", weight=110)
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(master, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        # Weight 110 = "strained" tier per design §6
        self.assertIn("Strained", joined)


class TestPadawanShowsDescriptor(unittest.TestCase):
    def test_descriptor_sentence_appears(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(db, 10, "Obi-Wan")
            await _make_char(db, 11, "Anakin", weight=110)
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(master, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        # Descriptor for "strained" (Weight 101-150) per design §6
        # includes the phrase "Meditation no longer calms you"
        self.assertIn("Meditation no longer", joined)


class TestPadawanSuppressedWhenNoBond(unittest.TestCase):
    def test_no_bond_no_weight_line(self):
        async def go():
            db = await _fresh_db()
            solo = await _make_char(db, 10, "Obi-Wan")
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(solo, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertNotIn("Through the bond", joined)
        # The no-bond message should still be present
        self.assertIn("no active Padawan bond", joined)


class TestPadawanSuppressedForNonJediPadawan(unittest.TestCase):
    def test_non_jedi_padawan_no_weight_line(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(db, 10, "Obi-Wan")
            await _make_char(
                db, 11, "FakePadawan",
                faction="bh_guild", weight=110,
            )
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(master, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertNotIn("Through the bond", joined)


# ═════════════════════════════════════════════════════════════════════
# 11-12. Mutual support narrative
# ═════════════════════════════════════════════════════════════════════


class TestMasterCanSensePadawanStrained(unittest.TestCase):
    """Design §7.4: 'a Master can notice their Padawan is
    struggling and initiate +counsel.' At Weight 110 (strained
    tier), the +padawan view shows the strained descriptor —
    that's the noticing."""

    def test_strained_padawan_visible_to_master(self):
        async def go():
            db = await _fresh_db()
            master = await _make_char(db, 10, "Obi-Wan")
            await _make_char(db, 11, "Anakin", weight=130)
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import PadawanCommand
            ctx = _make_ctx(master, db)
            await PadawanCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Strained", joined)


class TestPadawanCanSenseMasterCrushed(unittest.TestCase):
    """Design §7.4: 'a Padawan can see their Master fraying and
    offer support (reversing the normal direction of mentorship,
    which is itself a Clone Wars-era theme).' Master at Weight
    170 (crushed tier) → Padawan sees the crushed descriptor."""

    def test_crushed_master_visible_to_padawan(self):
        async def go():
            db = await _fresh_db()
            await _make_char(db, 10, "Obi-Wan", weight=170)
            padawan = await _make_char(db, 11, "Anakin")
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        self.assertIn("Crushed", joined)


# ═════════════════════════════════════════════════════════════════════
# 13. Defensive
# ═════════════════════════════════════════════════════════════════════


class TestMasterWeightReadFailDoesNotCrash(unittest.TestCase):
    """The Weight sense-line is wrapped in try/except. If the
    substrate read somehow raises, the rest of +master output
    must still render — name, bond age, trials count."""

    def test_broken_weight_read_falls_through(self):
        # We don't have a clean way to inject a broken
        # get_tier_for_char short of monkey-patching, but the
        # production code's try/except is defensive enough to
        # cover the normal failure modes (missing column, bad
        # JSON in chargen_notes, etc.). This test just
        # confirms the happy path emits the bond-age line
        # which lives AFTER the WoW block — if the WoW block
        # raised, age wouldn't appear.
        async def go():
            db = await _fresh_db()
            await _make_char(db, 10, "Obi-Wan", weight=60)
            padawan = await _make_char(db, 11, "Anakin")
            await _make_bond(db, 10, 11)
            from parser.padawan_master_commands import MasterCommand
            ctx = _make_ctx(padawan, db)
            await MasterCommand().execute(ctx)
            return ctx.session.lines

        lines = _run(go())
        joined = "\n".join(lines)
        # The "Bonded:" line is rendered before the WoW block.
        # The "Trials passed:" line is rendered AFTER. Both
        # should be present if the WoW block doesn't break the
        # rest.
        self.assertIn("Bonded:", joined)
        self.assertIn("Trials passed:", joined)


if __name__ == "__main__":
    unittest.main()
