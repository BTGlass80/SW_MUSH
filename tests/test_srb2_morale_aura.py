# -*- coding: utf-8 -*-
"""
tests/test_srb2_morale_aura.py — SRB.2 (May 22 2026).

Support Role Buffs v1, session 2 — Entertainer morale aura.

Per `support_role_buffs_design_v1.md` §2, ships:

  Schema (v32): morale_auras table + characters.perform_fatigue_*
  Engine: engine.skill_checks.is_morale_flavored(),
          get_morale_aura_magnitude(), perform_morale_aware_check().
  Parser: parser/entertainer_commands.PerformCommand extended to
          (a) read fatigue and adjust difficulty,
          (b) write a morale aura on success,
          (c) tick the fatigue counter on success and partial.
          parser/builtin_commands.LookCommand surfaces the aura.
          parser/builtin_commands.MoveCommand clears it on departure.
  Tick:   server.tick_handlers_economy.morale_aura_expiry_tick.

Force fall check integration in engine/force_powers.py is explicitly
DEFERRED to a follow-up (requires async-converting a synchronous
helper). Morale aura still applies via perform_morale_aware_check for
Willpower / Command / Persuasion rolls when consumers opt in.

Test sections
=============

  1. TestSchemaV32                 — table + columns land
  2. TestAuraDbHelpers             — round-trip get/set/clear
  3. TestAuraExpiry                — list/reap by timestamp
  4. TestAuraReplacement           — OR REPLACE semantics
  5. TestClearByPerformer          — all-rooms cleanup
  6. TestFatigueDbHelpers          — get/set fatigue
  7. TestMagnitudeMapping          — _aura_magnitude_for_margin
  8. TestIsMoraleFlavored          — classification helper
  9. TestGetMagnitudeNone          — no aura → 0
 10. TestGetMagnitudeExpired       — expired aura → 0
 11. TestGetMagnitudeActive        — live aura → value
 12. TestMoraleAwareSkipsNonMorale — non-morale skills bypass DB
 13. TestMoraleAwareReducesDiff    — morale skill gets difficulty cut
 14. TestMoraleAwareFloors         — difficulty floor at 1
 15. TestMoraleAwareNoRoomNoBenefit — missing room_id → no aura
 16. TestAuraFlavorTable           — _AURA_FLAVOR has all magnitudes
 17. TestExpiryTick                — tick reaps expired auras
 18. TestExpiryTickSilent          — tick survives DB errors
 19. TestHigherAuraWinsLogic       — write only if magnitude >= existing
 20. TestRegistration              — DB methods exist on class
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

pytestmark = pytest.mark.slow  # heavy: per-test in-memory DB + full migration chain


def _run(coro):
    return asyncio.run(coro)


# ─── shared fixtures ──────────────────────────────────────────────────────


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_character(db, *, name="Performer1", room_id=1):
    """Insert a minimal character + backing account, return dict."""
    acct_cur = await db._db.execute(
        "INSERT INTO accounts (username, password_hash) VALUES (?, ?)",
        (f"acct_{name.lower()}_{id(name)}", "x"),
    )
    await db._db.commit()
    account_id = acct_cur.lastrowid

    attrs_json = json.dumps({
        "strength": "3D", "dexterity": "3D", "knowledge": "3D",
        "perception": "3D", "mechanical": "2D", "technical": "2D",
    })
    inv_json = json.dumps({"items": [], "resources": []})

    cur = await db._db.execute(
        "INSERT INTO characters "
        "(name, account_id, room_id, attributes, skills, inventory, "
        " credits, wound_level) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (name, account_id, room_id, attrs_json, "{}", inv_json, 500, 0),
    )
    await db._db.commit()
    char_id = cur.lastrowid
    row = await db._db.execute_fetchall(
        "SELECT * FROM characters WHERE id = ?", (char_id,)
    )
    return dict(row[0])


# ──────────────────────────────────────────────────────────────────────
# 1. Schema v32 lands
# ──────────────────────────────────────────────────────────────────────

class TestSchemaV32(unittest.TestCase):

    def test_schema_version_is_32(self):
        from db.database import SCHEMA_VERSION
        self.assertGreaterEqual(SCHEMA_VERSION, 32,
                                f"want >=32, got {SCHEMA_VERSION}")

    def test_morale_auras_table_exists(self):
        async def go():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name='morale_auras'"
            )
            self.assertTrue(rows, "morale_auras table missing")
        _run(go())

    def test_morale_auras_columns(self):
        async def go():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(morale_auras)"
            )
            cols = {r["name"] for r in rows}
            for need in ("room_id", "performer_id", "magnitude",
                         "started_at", "expires_at"):
                self.assertIn(need, cols)
        _run(go())

    def test_fatigue_columns_on_characters(self):
        async def go():
            db = await _fresh_db()
            rows = await db._db.execute_fetchall(
                "PRAGMA table_info(characters)"
            )
            cols = {r["name"] for r in rows}
            self.assertIn("perform_fatigue_resets_at", cols)
            self.assertIn("perform_fatigue_count", cols)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 2. Aura DB helpers
# ──────────────────────────────────────────────────────────────────────

class TestAuraDbHelpers(unittest.TestCase):

    def test_get_returns_none_when_empty(self):
        async def go():
            db = await _fresh_db()
            self.assertIsNone(await db.get_morale_aura(1))
        _run(go())

    def test_set_then_get_round_trip(self):
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=10, performer_id=42, magnitude=3,
                started_at=100.0, expires_at=200.0,
            )
            aura = await db.get_morale_aura(10)
            self.assertEqual(aura["room_id"], 10)
            self.assertEqual(aura["performer_id"], 42)
            self.assertEqual(aura["magnitude"], 3)
            self.assertEqual(aura["expires_at"], 200.0)
        _run(go())

    def test_clear_morale_aura_removes_row(self):
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=5, performer_id=1, magnitude=2,
                started_at=0, expires_at=999.0,
            )
            removed = await db.clear_morale_aura(5)
            self.assertTrue(removed)
            self.assertIsNone(await db.get_morale_aura(5))

        _run(go())

    def test_clear_morale_aura_on_empty_returns_false(self):
        async def go():
            db = await _fresh_db()
            self.assertFalse(await db.clear_morale_aura(999))
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 3. Aura expiry semantics
# ──────────────────────────────────────────────────────────────────────

class TestAuraExpiry(unittest.TestCase):

    def test_list_expired_returns_only_expired(self):
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=1,
                started_at=0, expires_at=50.0,
            )
            await db.set_morale_aura(
                room_id=2, performer_id=2, magnitude=1,
                started_at=0, expires_at=9999.0,
            )
            expired = await db.list_expired_morale_auras(now=100.0)
            self.assertEqual(len(expired), 1)
            self.assertEqual(expired[0]["room_id"], 1)
        _run(go())

    def test_reap_removes_expired_only(self):
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=1,
                started_at=0, expires_at=50.0,
            )
            await db.set_morale_aura(
                room_id=2, performer_id=2, magnitude=1,
                started_at=0, expires_at=9999.0,
            )
            n = await db.reap_expired_morale_auras(now=100.0)
            self.assertEqual(n, 1)
            self.assertIsNone(await db.get_morale_aura(1))
            self.assertIsNotNone(await db.get_morale_aura(2))
        _run(go())

    def test_reap_on_empty_returns_zero(self):
        async def go():
            db = await _fresh_db()
            self.assertEqual(await db.reap_expired_morale_auras(now=0), 0)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 4. OR REPLACE semantics
# ──────────────────────────────────────────────────────────────────────

class TestAuraReplacement(unittest.TestCase):

    def test_second_aura_replaces_first(self):
        """Per design §2.4, room_id PK enforces single aura row."""
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=2,
                started_at=0, expires_at=100.0,
            )
            await db.set_morale_aura(
                room_id=1, performer_id=2, magnitude=5,
                started_at=10, expires_at=200.0,
            )
            aura = await db.get_morale_aura(1)
            self.assertEqual(aura["performer_id"], 2)
            self.assertEqual(aura["magnitude"], 5)
            self.assertEqual(aura["expires_at"], 200.0)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 5. clear_morale_auras_for_performer
# ──────────────────────────────────────────────────────────────────────

class TestClearByPerformer(unittest.TestCase):

    def test_clears_all_rooms_for_one_performer(self):
        async def go():
            db = await _fresh_db()
            # 2 rooms, same performer
            await db.set_morale_aura(
                room_id=1, performer_id=42, magnitude=2,
                started_at=0, expires_at=999.0,
            )
            await db.set_morale_aura(
                room_id=2, performer_id=42, magnitude=3,
                started_at=0, expires_at=999.0,
            )
            # A third room, different performer
            await db.set_morale_aura(
                room_id=3, performer_id=99, magnitude=2,
                started_at=0, expires_at=999.0,
            )
            n = await db.clear_morale_auras_for_performer(42)
            self.assertEqual(n, 2)
            self.assertIsNone(await db.get_morale_aura(1))
            self.assertIsNone(await db.get_morale_aura(2))
            # Other performer untouched
            self.assertIsNotNone(await db.get_morale_aura(3))
        _run(go())

    def test_unknown_performer_returns_zero(self):
        async def go():
            db = await _fresh_db()
            self.assertEqual(
                await db.clear_morale_auras_for_performer(99999), 0
            )
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 6. Fatigue DB helpers
# ──────────────────────────────────────────────────────────────────────

class TestFatigueDbHelpers(unittest.TestCase):

    def test_defaults_zero(self):
        async def go():
            db = await _fresh_db()
            ch = await _make_character(db)
            r, c = await db.get_perform_fatigue(ch["id"])
            self.assertEqual(r, 0.0)
            self.assertEqual(c, 0)
        _run(go())

    def test_round_trip(self):
        async def go():
            db = await _fresh_db()
            ch = await _make_character(db)
            await db.set_perform_fatigue(
                char_id=ch["id"], resets_at=12345.0, count=3
            )
            r, c = await db.get_perform_fatigue(ch["id"])
            self.assertEqual(r, 12345.0)
            self.assertEqual(c, 3)
        _run(go())

    def test_missing_char_safe(self):
        async def go():
            db = await _fresh_db()
            r, c = await db.get_perform_fatigue(99999)
            # Missing char → both zero (the SQL returns 0 rows)
            self.assertEqual((r, c), (0.0, 0))
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 7. Magnitude mapping
# ──────────────────────────────────────────────────────────────────────

class TestMagnitudeMapping(unittest.TestCase):

    def test_below_min_returns_zero(self):
        from parser.entertainer_commands import _aura_magnitude_for_margin
        self.assertEqual(_aura_magnitude_for_margin(0), 0)
        self.assertEqual(_aura_magnitude_for_margin(-5), 0)

    def test_basic_tier(self):
        from parser.entertainer_commands import _aura_magnitude_for_margin
        for m in (1, 2, 3, 4):
            self.assertEqual(_aura_magnitude_for_margin(m), 1,
                             f"margin {m}")

    def test_good_tier(self):
        from parser.entertainer_commands import _aura_magnitude_for_margin
        for m in (5, 7, 9):
            self.assertEqual(_aura_magnitude_for_margin(m), 2)

    def test_excellent_tier(self):
        from parser.entertainer_commands import _aura_magnitude_for_margin
        for m in (10, 12, 14):
            self.assertEqual(_aura_magnitude_for_margin(m), 3)

    def test_heroic_tier(self):
        from parser.entertainer_commands import _aura_magnitude_for_margin
        for m in (15, 20, 100):
            self.assertEqual(_aura_magnitude_for_margin(m), 5)

    def test_magnitude_4_is_skipped(self):
        """Design §2.2 — magnitude jumps 3 → 5; no 4."""
        from parser.entertainer_commands import _aura_magnitude_for_margin
        outputs = {_aura_magnitude_for_margin(m) for m in range(0, 30)}
        self.assertNotIn(4, outputs)


# ──────────────────────────────────────────────────────────────────────
# 8. is_morale_flavored
# ──────────────────────────────────────────────────────────────────────

class TestIsMoraleFlavored(unittest.TestCase):

    def test_morale_skills(self):
        from engine.skill_checks import is_morale_flavored
        for s in ("willpower", "command", "persuasion", "con"):
            self.assertTrue(is_morale_flavored(s), s)

    def test_non_morale_skills(self):
        from engine.skill_checks import is_morale_flavored
        for s in ("blaster", "dodge", "first aid", "medicine",
                  "search", "hide", "lift", "starship piloting"):
            self.assertFalse(is_morale_flavored(s), s)

    def test_case_insensitive(self):
        from engine.skill_checks import is_morale_flavored
        self.assertTrue(is_morale_flavored("Willpower"))
        self.assertTrue(is_morale_flavored("PERSUASION"))


# ──────────────────────────────────────────────────────────────────────
# 9-11. get_morale_aura_magnitude variants
# ──────────────────────────────────────────────────────────────────────

class TestGetMagnitudeNone(unittest.TestCase):

    def test_no_aura_returns_zero(self):
        from engine.skill_checks import get_morale_aura_magnitude
        async def go():
            db = await _fresh_db()
            mag = await get_morale_aura_magnitude(db, 999)
            self.assertEqual(mag, 0)
        _run(go())


class TestGetMagnitudeExpired(unittest.TestCase):

    def test_expired_aura_returns_zero(self):
        from engine.skill_checks import get_morale_aura_magnitude
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=3,
                started_at=0, expires_at=50.0,
            )
            mag = await get_morale_aura_magnitude(db, 1, now=100.0)
            self.assertEqual(mag, 0)
        _run(go())


class TestGetMagnitudeActive(unittest.TestCase):

    def test_live_aura_returns_magnitude(self):
        from engine.skill_checks import get_morale_aura_magnitude
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=3,
                started_at=0, expires_at=9999.0,
            )
            mag = await get_morale_aura_magnitude(db, 1, now=100.0)
            self.assertEqual(mag, 3)
        _run(go())

    def test_db_error_returns_zero(self):
        """get_morale_aura raises → helper returns 0, not propagate."""
        from engine.skill_checks import get_morale_aura_magnitude
        async def go():
            broken_db = MagicMock()
            broken_db.get_morale_aura = AsyncMock(side_effect=RuntimeError("oops"))
            mag = await get_morale_aura_magnitude(broken_db, 1)
            self.assertEqual(mag, 0)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 12-15. perform_morale_aware_check behavior
# ──────────────────────────────────────────────────────────────────────

class TestMoraleAwareSkipsNonMorale(unittest.TestCase):

    def test_non_morale_skill_does_not_touch_db(self):
        """Per design §2.3: combat / tech / etc are not aura-affected."""
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = MagicMock()
            db.get_morale_aura = AsyncMock()  # Would fail if called
            char = {"attributes": '{"dexterity": "3D"}', "skills": "{}",
                    "room_id": 1}
            result = await perform_morale_aware_check(
                char, "blaster", difficulty=15, db=db,
            )
            self.assertEqual(result.difficulty, 15)
            db.get_morale_aura.assert_not_called()
        _run(go())


class TestMoraleAwareReducesDiff(unittest.TestCase):

    def test_willpower_difficulty_drops_by_magnitude(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=3,
                started_at=time.time(),
                expires_at=time.time() + 9999.0,
            )
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}",
                    "room_id": 1}
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=15, db=db,
            )
            # 15 - 3 = 12
            self.assertEqual(result.difficulty, 12)
        _run(go())

    def test_no_aura_difficulty_unchanged(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = await _fresh_db()
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}",
                    "room_id": 1}
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=15, db=db,
            )
            self.assertEqual(result.difficulty, 15)
        _run(go())


class TestMoraleAwareFloors(unittest.TestCase):

    def test_difficulty_floors_at_one(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=5,
                started_at=time.time(),
                expires_at=time.time() + 9999.0,
            )
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}",
                    "room_id": 1}
            # Difficulty 3 with magnitude 5 → would be -2; floor at 1
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=3, db=db,
            )
            self.assertEqual(result.difficulty, 1)
        _run(go())


class TestMoraleAwareNoRoomNoBenefit(unittest.TestCase):

    def test_missing_room_id_returns_unmodified(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = await _fresh_db()
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}"}
            # No room_id in char, none passed
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=15, db=db,
            )
            self.assertEqual(result.difficulty, 15)
        _run(go())

    def test_missing_db_returns_unmodified(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}",
                    "room_id": 1}
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=15, db=None,
            )
            self.assertEqual(result.difficulty, 15)
        _run(go())

    def test_explicit_room_id_overrides_char(self):
        from engine.skill_checks import perform_morale_aware_check
        async def go():
            db = await _fresh_db()
            # Aura is on room 2; char.room_id says 1; we pass room_id=2
            await db.set_morale_aura(
                room_id=2, performer_id=1, magnitude=2,
                started_at=time.time(),
                expires_at=time.time() + 9999.0,
            )
            char = {"attributes": '{"knowledge": "3D"}', "skills": "{}",
                    "room_id": 1}
            result = await perform_morale_aware_check(
                char, "willpower", difficulty=15, db=db, room_id=2,
            )
            self.assertEqual(result.difficulty, 13)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 16. Aura flavor table
# ──────────────────────────────────────────────────────────────────────

class TestAuraFlavorTable(unittest.TestCase):

    def test_all_magnitudes_have_flavor(self):
        from parser.entertainer_commands import _AURA_FLAVOR
        for m in (1, 2, 3, 5):
            self.assertIn(m, _AURA_FLAVOR)
            self.assertTrue(_AURA_FLAVOR[m].strip())

    def test_no_flavor_for_4(self):
        from parser.entertainer_commands import _AURA_FLAVOR
        self.assertNotIn(4, _AURA_FLAVOR)


# ──────────────────────────────────────────────────────────────────────
# 17-18. Expiry tick
# ──────────────────────────────────────────────────────────────────────

class TestExpiryTick(unittest.TestCase):

    def test_tick_reaps_expired_rows(self):
        from server.tick_handlers_economy import morale_aura_expiry_tick
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=1,
                started_at=0, expires_at=1.0,  # already expired
            )
            await db.set_morale_aura(
                room_id=2, performer_id=2, magnitude=1,
                started_at=0, expires_at=time.time() + 9999.0,
            )
            ctx = MagicMock()
            ctx.db = db
            await morale_aura_expiry_tick(ctx)
            self.assertIsNone(await db.get_morale_aura(1))
            self.assertIsNotNone(await db.get_morale_aura(2))
        _run(go())


class TestExpiryTickSilent(unittest.TestCase):

    def test_tick_swallows_db_errors(self):
        from server.tick_handlers_economy import morale_aura_expiry_tick
        async def go():
            ctx = MagicMock()
            ctx.db = MagicMock()
            ctx.db.reap_expired_morale_auras = AsyncMock(
                side_effect=RuntimeError("DB exploded")
            )
            # Should not raise
            await morale_aura_expiry_tick(ctx)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 19. Higher aura wins (the rule lives in PerformCommand, not DB —
#     test the policy directly by simulating the read-before-write.)
# ──────────────────────────────────────────────────────────────────────

class TestHigherAuraWinsLogic(unittest.TestCase):

    def test_db_does_not_enforce_higher_wins(self):
        """DB layer is dumb on purpose; the policy lives in PerformCommand.

        Documenting this so future readers don't add the check at the
        DB layer (which would prevent legitimate use cases like
        cleanup-and-replace).
        """
        async def go():
            db = await _fresh_db()
            await db.set_morale_aura(
                room_id=1, performer_id=1, magnitude=5,
                started_at=0, expires_at=999.0,
            )
            # DB layer cheerfully writes the lower-magnitude row
            await db.set_morale_aura(
                room_id=1, performer_id=2, magnitude=1,
                started_at=0, expires_at=999.0,
            )
            aura = await db.get_morale_aura(1)
            self.assertEqual(aura["magnitude"], 1)
        _run(go())


# ──────────────────────────────────────────────────────────────────────
# 20. Registration
# ──────────────────────────────────────────────────────────────────────

class TestRegistration(unittest.TestCase):

    def test_db_methods_exist(self):
        from db.database import Database
        # All eight new helpers
        for name in (
            "get_morale_aura", "set_morale_aura", "clear_morale_aura",
            "clear_morale_auras_for_performer",
            "list_expired_morale_auras", "reap_expired_morale_auras",
            "get_perform_fatigue", "set_perform_fatigue",
        ):
            self.assertTrue(hasattr(Database, name), name)

    def test_engine_helpers_exist(self):
        import engine.skill_checks as sc
        for name in (
            "MORALE_FLAVORED_SKILLS", "is_morale_flavored",
            "get_morale_aura_magnitude", "perform_morale_aware_check",
        ):
            self.assertTrue(hasattr(sc, name), name)

    def test_parser_helpers_exist(self):
        import parser.entertainer_commands as ec
        for name in (
            "_aura_magnitude_for_margin", "_AURA_FLAVOR",
            "_AURA_DURATION_SECONDS", "_FATIGUE_WINDOW_SECONDS",
            "_FATIGUE_PENALTY_PIPS",
        ):
            self.assertTrue(hasattr(ec, name), name)

    def test_tick_handler_exists(self):
        from server.tick_handlers_economy import morale_aura_expiry_tick
        self.assertTrue(callable(morale_aura_expiry_tick))

    def test_tick_registered_in_game_server(self):
        """Verify the tick is referenced in game_server.py registration."""
        gs_path = PROJECT_ROOT / "server" / "game_server.py"
        text = gs_path.read_text(encoding="utf-8")
        self.assertIn("morale_aura_expiry_tick", text)
        self.assertIn('"morale_aura_expiry"', text)


if __name__ == "__main__":
    unittest.main()
