# -*- coding: utf-8 -*-
"""
tests/test_wow2b_meditate.py — WoW.2b: +meditate command.

Per weight_of_war_design_v1.md §5.2 ("Active Decay") and §10
("Commands Summary"). Exercises MeditateCommand end-to-end
against a real Database (Pattern 8 discipline: every parser
command that does DB writes needs production-schema integration
coverage).

Test sections
=============

Command shape:
  1.  TestMeditateCommandKeyAndAliases
  2.  TestMeditateCommandRegistered
  3.  TestMeditateNoAccessLevelGate   — player command, no admin gate

Identity gate (Failure 1: not a Jedi):
  4.  TestRejectsNonJediBHGuild
  5.  TestRejectsIndependentNoChargen
  6.  TestAcceptsJediByFaction
  7.  TestAcceptsJediByChargenFlag

Location gate (Failure 2: not at Temple):
  8.  TestRejectsAwayFromTemple
  9.  TestAcceptsAtTempleMainGate
 10.  TestAcceptsAnyRoomInTempleZone
 11.  TestRejectsRoomWithoutZone
 12.  TestRejectsMissingRoom

Cooldown gate (Failure 3: already meditated):
 13.  TestRejectsWhileOnCooldown
 14.  TestSuccessSetsCooldown
 15.  TestCooldownMessageIncludesTimeRemaining

Force Point gate (Failure 4: insufficient FP):
 16.  TestRejectsWithZeroFP
 17.  TestRejectsWithNegativeFP
 18.  TestRejectsWithNonIntegerFP   — defensive
 19.  TestSuccessWithExactlyOneFP

Soft fail (Failure 5: already at peace):
 20.  TestAtPeaceShortCircuitsNoSpend
 21.  TestAtPeaceDoesNotSetCooldown
 22.  TestAtPeaceMessageMentionsPreserved

Success path:
 23.  TestSuccessDecrementsFP
 24.  TestSuccessDecaysWeight
 25.  TestSuccessLogsEvent
 26.  TestSuccessRendersDescriptorAboveTwenty
 27.  TestSuccessSilentOnDescriptorBelowTwenty
 28.  TestSuccessIdempotentReadback   — char dict and DB agree

Edge cases:
 29.  TestNoCharOnSession              — defensive
 30.  TestPartialDecayNearFloor        — weight=3, -5 → 0 (not -8)
 31.  TestDecayEventTriggerType        — "meditate" tag in log

Phantom-prevention (Pattern 8):
 32.  TestProductionSchemaEndToEnd     — full real-DB invocation
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import MagicMock

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

pytestmark = pytest.mark.slow  # heavy: per-test in-memory DB + full migration chain


def _run(coro):
    return asyncio.run(coro)


# ── Test fixture helpers ─────────────────────────────────────────────


class _Harness:
    """Build a real Database with a Temple zone, a Temple room, a
    non-Temple zone+room, and a seeded Jedi PC. Returns ids and the
    PC dict via .reload()."""

    def __init__(self):
        self.db = None
        self.temple_room_id = 0
        self.lower_room_id = 0
        self.char_id = 10

    async def setup(self, weight: int = 50, fp: int = 2,
                    faction: str = "jedi_order",
                    chargen_flags: dict | None = None) -> None:
        from db.database import Database
        self.db = Database(":memory:")
        await self.db.connect()
        await self.db.initialize()

        await self.db._db.execute(
            "INSERT INTO accounts (id, username, password_hash) "
            "VALUES (1, 'u', 'p')"
        )
        cur = await self.db._db.execute(
            "INSERT INTO zones (name, properties) VALUES (?, ?)",
            ("jedi_temple", "{}"),
        )
        temple_zone_id = cur.lastrowid
        cur = await self.db._db.execute(
            "INSERT INTO zones (name, properties) VALUES (?, ?)",
            ("southern_underground", "{}"),
        )
        lower_zone_id = cur.lastrowid
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, zone_id, properties) "
            "VALUES (?, ?, ?)",
            ("Temple Hall", temple_zone_id, "{}"),
        )
        self.temple_room_id = cur.lastrowid
        cur = await self.db._db.execute(
            "INSERT INTO rooms (name, zone_id, properties) "
            "VALUES (?, ?, ?)",
            ("Lower City", lower_zone_id, "{}"),
        )
        self.lower_room_id = cur.lastrowid

        notes = json.dumps(chargen_flags) if chargen_flags else ""
        await self.db._db.execute(
            "INSERT INTO characters "
            "(id, account_id, name, room_id, faction_id, "
            "force_points, weight_of_war, chargen_notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (self.char_id, 1, "Anakin", self.temple_room_id, faction,
             fp, weight, notes),
        )
        await self.db._db.commit()

    async def reload(self) -> dict:
        return await self.db.get_character(self.char_id)


def _make_ctx(char: dict, db, args: str = ""):
    session = MagicMock()
    session.lines = []

    async def send(s):
        session.lines.append(str(s))

    session.send_line = send
    session.character = char

    ctx = MagicMock()
    ctx.session = session
    ctx.db = db
    ctx.args = args
    return ctx


def _session_contains(ctx, needle: str) -> bool:
    return any(needle in line for line in ctx.session.lines)


# ═════════════════════════════════════════════════════════════════════
# Command shape
# ═════════════════════════════════════════════════════════════════════

class TestMeditateCommandKeyAndAliases(unittest.TestCase):
    def test_key_and_aliases(self):
        from parser.meditate_command import MeditateCommand
        cmd = MeditateCommand()
        self.assertEqual(cmd.key, "+meditate")
        self.assertIn("meditate", cmd.aliases)


class TestMeditateCommandRegistered(unittest.TestCase):
    def test_register_function(self):
        from parser.meditate_command import (
            register_meditate_command, MeditateCommand,
        )
        registry = MagicMock()
        register_meditate_command(registry)
        registry.register.assert_called_once()
        cmd = registry.register.call_args[0][0]
        self.assertIsInstance(cmd, MeditateCommand)


class TestMeditateNoAccessLevelGate(unittest.TestCase):
    def test_no_admin_gate(self):
        """+meditate is a player command — no access_level override."""
        from parser.meditate_command import MeditateCommand
        cmd = MeditateCommand()
        # If a subclass declares access_level, BaseCommand has a
        # default. Just verify it's not ADMIN.
        from parser.commands import AccessLevel
        self.assertNotEqual(
            getattr(cmd, "access_level", None), AccessLevel.ADMIN,
        )


# ═════════════════════════════════════════════════════════════════════
# Identity gate
# ═════════════════════════════════════════════════════════════════════

class TestRejectsNonJediBHGuild(unittest.TestCase):
    def test_bh_guild_rejected(self):
        async def go():
            h = _Harness()
            await h.setup(faction="bh_guild")
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Only Jedi"))
            # No state change
            after = await h.reload()
            self.assertEqual(after["force_points"], 2)
            self.assertEqual(after["weight_of_war"], 50)
        _run(go())


class TestRejectsIndependentNoChargen(unittest.TestCase):
    def test_independent_without_chargen_flag_rejected(self):
        async def go():
            h = _Harness()
            await h.setup(faction="independent", chargen_flags=None)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Only Jedi"))
        _run(go())


class TestAcceptsJediByFaction(unittest.TestCase):
    def test_jedi_order_passes_identity_gate(self):
        async def go():
            h = _Harness()
            await h.setup(faction="jedi_order")
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertFalse(_session_contains(ctx, "Only Jedi"))
        _run(go())


class TestAcceptsJediByChargenFlag(unittest.TestCase):
    def test_path_b_jedi_passes_identity_gate(self):
        async def go():
            h = _Harness()
            await h.setup(
                faction="independent",
                chargen_flags={"jedi_path_unlocked": True},
            )
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertFalse(_session_contains(ctx, "Only Jedi"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Location gate
# ═════════════════════════════════════════════════════════════════════

class TestRejectsAwayFromTemple(unittest.TestCase):
    def test_lower_city_rejected(self):
        async def go():
            h = _Harness()
            await h.setup()
            await h.db.save_character(h.char_id, room_id=h.lower_room_id)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Coruscant Temple"))
            after = await h.reload()
            self.assertEqual(after["force_points"], 2)
        _run(go())


class TestAcceptsAtTempleMainGate(unittest.TestCase):
    def test_temple_room_passes_location_gate(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # Successful path — no "Temple" rejection message
            self.assertFalse(
                _session_contains(ctx, "must be at the Jedi Temple"),
            )
        _run(go())


class TestAcceptsAnyRoomInTempleZone(unittest.TestCase):
    def test_archives_also_qualifies(self):
        async def go():
            h = _Harness()
            await h.setup()
            # Add another room in the same Temple zone
            temple_room = await h.db.get_room(h.temple_room_id)
            cur = await h.db._db.execute(
                "INSERT INTO rooms (name, zone_id, properties) "
                "VALUES (?, ?, ?)",
                ("Archives", temple_room["zone_id"], "{}"),
            )
            archives_id = cur.lastrowid
            await h.db._db.commit()
            await h.db.save_character(h.char_id, room_id=archives_id)

            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # Success path means weight decreased
            after = await h.reload()
            self.assertEqual(after["weight_of_war"], 45)
        _run(go())


class TestRejectsRoomWithoutZone(unittest.TestCase):
    def test_zoneless_room_rejected(self):
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
            await h.db.save_character(h.char_id, room_id=void_id)

            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Coruscant Temple"))
        _run(go())


class TestRejectsMissingRoom(unittest.TestCase):
    def test_invalid_room_id_rejected_cleanly(self):
        async def go():
            h = _Harness()
            await h.setup()
            # Force a bad room_id
            char = await h.reload()
            char = dict(char)
            char["room_id"] = 99999
            from parser.meditate_command import MeditateCommand
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Coruscant Temple"))
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Cooldown gate
# ═════════════════════════════════════════════════════════════════════

class TestRejectsWhileOnCooldown(unittest.TestCase):
    def test_second_meditate_blocked(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx1 = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx1)
            # Reload to pick up cooldown attribute
            char2 = await h.reload()
            ctx2 = _make_ctx(char2, h.db)
            await MeditateCommand().execute(ctx2)
            self.assertTrue(
                _session_contains(ctx2, "meditated recently"),
            )
            # FP unchanged from the second attempt
            after = await h.reload()
            self.assertEqual(after["force_points"], 1)  # 2-1 from first
        _run(go())


class TestSuccessSetsCooldown(unittest.TestCase):
    def test_cooldown_persisted(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # Verify cooldown is in attributes
            after = await h.reload()
            attrs = json.loads(after.get("attributes") or "{}")
            self.assertIn("cooldowns", attrs)
            self.assertIn("meditate", attrs["cooldowns"])
            # Expiry should be ~86400s from now
            import time
            expiry = attrs["cooldowns"]["meditate"]
            self.assertGreater(expiry, time.time() + 86000)
            self.assertLess(expiry, time.time() + 87000)
        _run(go())


class TestCooldownMessageIncludesTimeRemaining(unittest.TestCase):
    def test_cooldown_message_shows_time(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            char2 = await h.reload()
            ctx2 = _make_ctx(char2, h.db)
            await MeditateCommand().execute(ctx2)
            # Should show e.g. "23h 59m" or similar
            joined = " ".join(ctx2.session.lines)
            self.assertTrue("h " in joined or "h\n" in joined,
                            f"expected hours marker. Got: {joined!r}")
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Force Point gate
# ═════════════════════════════════════════════════════════════════════

class TestRejectsWithZeroFP(unittest.TestCase):
    def test_zero_fp_rejected(self):
        async def go():
            h = _Harness()
            await h.setup(fp=0)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Force Point"))
            after = await h.reload()
            self.assertEqual(after["weight_of_war"], 50)  # no decay
        _run(go())


class TestRejectsWithNegativeFP(unittest.TestCase):
    def test_negative_fp_treated_as_zero(self):
        async def go():
            h = _Harness()
            await h.setup(fp=-1)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Force Point"))
        _run(go())


class TestRejectsWithNonIntegerFP(unittest.TestCase):
    def test_garbage_fp_defensive(self):
        async def go():
            h = _Harness()
            await h.setup()
            char = await h.reload()
            char = dict(char)
            char["force_points"] = "garbage"
            from parser.meditate_command import MeditateCommand
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "Force Point"))
        _run(go())


class TestSuccessWithExactlyOneFP(unittest.TestCase):
    def test_one_fp_succeeds(self):
        async def go():
            h = _Harness()
            await h.setup(fp=1)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            after = await h.reload()
            self.assertEqual(after["force_points"], 0)
            self.assertEqual(after["weight_of_war"], 45)
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# At-peace soft-fail
# ═════════════════════════════════════════════════════════════════════

class TestAtPeaceShortCircuitsNoSpend(unittest.TestCase):
    def test_weight_zero_does_not_spend_fp(self):
        async def go():
            h = _Harness()
            await h.setup(weight=0, fp=3)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            after = await h.reload()
            self.assertEqual(after["force_points"], 3)
            self.assertEqual(after["weight_of_war"], 0)
        _run(go())


class TestAtPeaceDoesNotSetCooldown(unittest.TestCase):
    def test_no_cooldown_set_when_at_peace(self):
        async def go():
            h = _Harness()
            await h.setup(weight=0, fp=3)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            after = await h.reload()
            attrs = json.loads(after.get("attributes") or "{}")
            cooldowns = attrs.get("cooldowns", {})
            self.assertNotIn("meditate", cooldowns)
        _run(go())


class TestAtPeaceMessageMentionsPreserved(unittest.TestCase):
    def test_message_explains_no_spend(self):
        async def go():
            h = _Harness()
            await h.setup(weight=0)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            joined = " ".join(ctx.session.lines)
            self.assertIn("preserved", joined.lower())
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Success path
# ═════════════════════════════════════════════════════════════════════

class TestSuccessDecrementsFP(unittest.TestCase):
    def test_fp_decremented_by_one(self):
        async def go():
            h = _Harness()
            await h.setup(fp=5)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            after = await h.reload()
            self.assertEqual(after["force_points"], 4)
        _run(go())


class TestSuccessDecaysWeight(unittest.TestCase):
    def test_weight_decreased_by_five(self):
        async def go():
            h = _Harness()
            await h.setup(weight=75)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            after = await h.reload()
            self.assertEqual(after["weight_of_war"], 70)
        _run(go())


class TestSuccessLogsEvent(unittest.TestCase):
    def test_decay_event_recorded(self):
        async def go():
            h = _Harness()
            await h.setup(weight=50)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            from engine.weight_of_war import get_events
            events = await get_events(h.db, h.char_id, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["trigger_type"], "meditate")
            self.assertLess(events[0]["delta"], 0)
        _run(go())


class TestSuccessRendersDescriptorAboveTwenty(unittest.TestCase):
    def test_descriptor_in_output_when_weight_above_20(self):
        async def go():
            h = _Harness()
            await h.setup(weight=50)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # After: weight=45, still > 20 → descriptor renders
            joined = " ".join(ctx.session.lines)
            # Troubled tier (21-50) descriptor
            self.assertIn("Force feels clouded", joined)
        _run(go())


class TestSuccessSilentOnDescriptorBelowTwenty(unittest.TestCase):
    def test_descriptor_silent_when_weight_drops_to_or_below_20(self):
        async def go():
            h = _Harness()
            await h.setup(weight=25)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # After: weight=20, NOT > 20, no descriptor
            joined = " ".join(ctx.session.lines)
            self.assertNotIn("Force feels clouded", joined)
            self.assertNotIn("haunted", joined)
        _run(go())


class TestSuccessIdempotentReadback(unittest.TestCase):
    def test_session_char_and_db_match(self):
        async def go():
            h = _Harness()
            await h.setup(weight=50, fp=2)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            ctx = _make_ctx(char, h.db)
            await MeditateCommand().execute(ctx)
            # The session char dict should match what's in DB
            db_char = await h.reload()
            self.assertEqual(
                ctx.session.character["force_points"],
                db_char["force_points"],
            )
            self.assertEqual(
                ctx.session.character["weight_of_war"],
                db_char["weight_of_war"],
            )
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Edge cases
# ═════════════════════════════════════════════════════════════════════

class TestNoCharOnSession(unittest.TestCase):
    def test_disconnected_session_handled(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            ctx = _make_ctx(None, h.db)
            ctx.session.character = None
            await MeditateCommand().execute(ctx)
            self.assertTrue(_session_contains(ctx, "in the game"))
        _run(go())


class TestPartialDecayNearFloor(unittest.TestCase):
    def test_weight_3_decays_to_0_not_negative(self):
        async def go():
            h = _Harness()
            await h.setup(weight=3)
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            after = await h.reload()
            self.assertEqual(after["weight_of_war"], 0)
            # FP still spent — design call locked in module docstring
            self.assertEqual(after["force_points"], 1)
        _run(go())


class TestDecayEventTriggerType(unittest.TestCase):
    def test_trigger_type_is_meditate(self):
        async def go():
            h = _Harness()
            await h.setup()
            from parser.meditate_command import MeditateCommand
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            from engine.weight_of_war import get_events
            events = await get_events(h.db, h.char_id, limit=1)
            self.assertEqual(events[0]["trigger_type"], "meditate")
        _run(go())


# ═════════════════════════════════════════════════════════════════════
# Production-schema integration (Pattern 8)
# ═════════════════════════════════════════════════════════════════════

class TestProductionSchemaEndToEnd(unittest.TestCase):
    """Run +meditate twice on the same char and confirm full
    state evolution: FP, weight, event log, cooldown — all
    against the real Database."""

    def test_full_flow(self):
        async def go():
            h = _Harness()
            await h.setup(weight=60, fp=3)
            from parser.meditate_command import MeditateCommand

            # 1. First meditation
            char = await h.reload()
            await MeditateCommand().execute(_make_ctx(char, h.db))
            after = await h.reload()
            self.assertEqual(after["force_points"], 2)
            self.assertEqual(after["weight_of_war"], 55)
            attrs = json.loads(after.get("attributes") or "{}")
            self.assertIn(
                "meditate", attrs.get("cooldowns", {}),
            )

            # 2. Second attempt blocked by cooldown
            ctx2 = _make_ctx(after, h.db)
            await MeditateCommand().execute(ctx2)
            self.assertTrue(
                _session_contains(ctx2, "meditated recently"),
            )
            after2 = await h.reload()
            # FP/weight unchanged
            self.assertEqual(after2["force_points"], 2)
            self.assertEqual(after2["weight_of_war"], 55)

            # 3. Event log
            from engine.weight_of_war import get_events
            events = await get_events(h.db, h.char_id, limit=5)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["delta"], -5)
            self.assertEqual(events[0]["trigger_type"], "meditate")
        _run(go())


if __name__ == "__main__":
    unittest.main()
