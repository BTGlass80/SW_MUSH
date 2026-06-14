# -*- coding: utf-8 -*-
"""
tests/test_wow3b_passive_decay_and_duels.py — WoW.3b runtime hooks.

Three things ship in this drop, all per WoW design §5.1 (passive
decay) and the May 23 handoff scope:

1. **`last_event_at`** substrate helper — returns max of
   `weight_last_accrual_at` and `weight_last_decay_at`, or None
   if no events have ever fired.

2. **`run_passive_decay_tick`** — engine-side worker that scans
   all Jedi PCs and applies -1 Weight to anyone with no events
   in 7+ real-time days. Skips retreat-active characters.

3. **`refuse_if_in_retreat`** wired into `ChallengeCommand` and
   `AcceptCommand` — extending the WoW.3a AttackCommand gate to
   the other two combat-initiation surfaces.

Test sections
=============

last_event_at (engine/weight_of_war.py):
  1.  TestLastEventAtNoCharacter            — missing char_id → None
  2.  TestLastEventAtBothNull               — fresh char, no events → None
  3.  TestLastEventAtOnlyAccrual            — only accrual ts → returns it
  4.  TestLastEventAtOnlyDecay              — only decay ts → returns it
  5.  TestLastEventAtBothSet                — both ts → returns max

run_passive_decay_tick (engine/weight_of_war.py):
  6.  TestPassiveDecayNoCharacters          — empty DB → no-op summary
  7.  TestPassiveDecayDecaysStale           — Jedi with no events in 8d → -1
  8.  TestPassiveDecaySkipsRecent           — Jedi with event 1d ago → skipped
  9.  TestPassiveDecaySkipsWeightZero       — Jedi at weight=0 → skipped at SQL
 10.  TestPassiveDecaySkipsNonJedi          — non-Jedi PC → skipped
 11.  TestPassiveDecaySkipsRetreat          — Jedi in retreat → skipped
 12.  TestPassiveDecaySummaryShape          — summary keys + counts correct
 13.  TestPassiveDecayMultipleJedi          — mixed eligibility batch processed
 14.  TestPassiveDecayFiresEventLog         — event row written with
                                              trigger_type='passive_decay'

Tick handler (server/tick_handlers_progression.py):
 15.  TestTickHandlerImportable             — wow_passive_decay_tick on module
 16.  TestTickHandlerDelegatesToEngine      — calls run_passive_decay_tick

Duel-gate wiring (parser/combat_commands.py):
 17.  TestChallengeRetreatGate              — Jedi-in-retreat refused
 18.  TestChallengeActiveJediProceeds       — Jedi NOT in retreat passes
 19.  TestAcceptRetreatGate                 — Jedi-in-retreat refused
 20.  TestAcceptActiveJediProceeds          — Jedi NOT in retreat passes

Phantom prevention:
 21.  TestSubstrateSurfaceImportable        — last_event_at + constants
 22.  TestSharedRefusalMessageConsistent    — all gates use same text
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time as _time
import unittest
from unittest.mock import AsyncMock, MagicMock

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

pytestmark = pytest.mark.slow  # heavy: per-test in-memory DB + full migration chain


def _run(coro):
    return asyncio.run(coro)


# ── Real-DB harness (Pattern 8) ───────────────────────────────────────


async def _make_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await db._db.execute(
        "INSERT INTO accounts (id, username, password_hash) "
        "VALUES (1, 'u', 'p')",
    )
    await db._db.commit()
    return db


async def _insert_jedi(
    db, char_id: int, name: str,
    weight: int = 50,
    last_accrual_at=None,
    last_decay_at=None,
    attributes_json: str = "{}",
    faction: str = "jedi_order",
):
    """Insert a Jedi PC with the given Weight + timestamp state.
    Returns nothing — caller can read back via get_weight_db etc."""
    await db._db.execute(
        "INSERT INTO characters "
        "(id, account_id, name, faction_id, weight_of_war, "
        "weight_last_accrual_at, weight_last_decay_at, "
        "attributes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (char_id, 1, name, faction, weight,
         last_accrual_at, last_decay_at, attributes_json),
    )
    await db._db.commit()


# ═════════════════════════════════════════════════════════════════════
# 1-5. last_event_at substrate
# ═════════════════════════════════════════════════════════════════════


class TestLastEventAtNoCharacter(unittest.TestCase):
    def test_missing_char_returns_none(self):
        from engine.weight_of_war import last_event_at

        async def go():
            db = await _make_db()
            return await last_event_at(db, 9999)

        self.assertIsNone(_run(go()))


class TestLastEventAtBothNull(unittest.TestCase):
    def test_fresh_char_returns_none(self):
        from engine.weight_of_war import last_event_at

        async def go():
            db = await _make_db()
            await _insert_jedi(db, 10, "Mace", weight=0)
            return await last_event_at(db, 10)

        self.assertIsNone(_run(go()))


class TestLastEventAtOnlyAccrual(unittest.TestCase):
    def test_returns_accrual_ts(self):
        from engine.weight_of_war import last_event_at

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Mace", weight=20,
                last_accrual_at=1_700_000_000.0,
            )
            return await last_event_at(db, 10)

        self.assertEqual(_run(go()), 1_700_000_000.0)


class TestLastEventAtOnlyDecay(unittest.TestCase):
    def test_returns_decay_ts(self):
        from engine.weight_of_war import last_event_at

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Mace", weight=20,
                last_decay_at=1_700_000_500.0,
            )
            return await last_event_at(db, 10)

        self.assertEqual(_run(go()), 1_700_000_500.0)


class TestLastEventAtBothSet(unittest.TestCase):
    def test_returns_max(self):
        from engine.weight_of_war import last_event_at

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Mace", weight=20,
                last_accrual_at=1_700_000_000.0,
                last_decay_at=1_700_000_500.0,
            )
            return await last_event_at(db, 10)

        # max(accrual=1.7e9, decay=1.7e9+500) = 1.7e9+500
        self.assertEqual(_run(go()), 1_700_000_500.0)


# ═════════════════════════════════════════════════════════════════════
# 6-14. run_passive_decay_tick
# ═════════════════════════════════════════════════════════════════════


_NOW = 2_000_000_000.0  # Fixed "now" for deterministic age math
_EIGHT_DAYS = 8 * 86400  # > 7 days = eligible for decay
_ONE_DAY = 86400        # < 7 days = NOT eligible


class TestPassiveDecayNoCharacters(unittest.TestCase):
    def test_empty_db_noop(self):
        from engine.weight_of_war import run_passive_decay_tick

        async def go():
            db = await _make_db()
            return await run_passive_decay_tick(db, now=_NOW)

        summary = _run(go())
        self.assertEqual(summary["scanned"], 0)
        self.assertEqual(summary["decayed"], 0)


class TestPassiveDecayDecaysStale(unittest.TestCase):
    def test_stale_jedi_decayed_by_one(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_weight_db,
        )

        async def go():
            db = await _make_db()
            # Jedi with last accrual 8 days ago → eligible
            await _insert_jedi(
                db, 10, "Anakin", weight=50,
                last_accrual_at=_NOW - _EIGHT_DAYS,
            )
            summary = await run_passive_decay_tick(db, now=_NOW)
            new_w = await get_weight_db(db, 10)
            return summary, new_w

        summary, new_w = _run(go())
        self.assertEqual(summary["decayed"], 1)
        self.assertEqual(new_w, 49)


class TestPassiveDecaySkipsRecent(unittest.TestCase):
    def test_recent_event_not_decayed(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_weight_db,
        )

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Anakin", weight=50,
                last_accrual_at=_NOW - _ONE_DAY,
            )
            summary = await run_passive_decay_tick(db, now=_NOW)
            new_w = await get_weight_db(db, 10)
            return summary, new_w

        summary, new_w = _run(go())
        self.assertEqual(summary["decayed"], 0)
        self.assertEqual(summary["skipped_recent"], 1)
        self.assertEqual(new_w, 50)


class TestPassiveDecaySkipsWeightZero(unittest.TestCase):
    def test_weight_zero_skipped(self):
        """SQL-level filter — weight=0 chars are never scanned."""
        from engine.weight_of_war import run_passive_decay_tick

        async def go():
            db = await _make_db()
            # Eligible by age but weight=0
            await _insert_jedi(
                db, 10, "Anakin", weight=0,
                last_accrual_at=_NOW - _EIGHT_DAYS,
            )
            return await run_passive_decay_tick(db, now=_NOW)

        summary = _run(go())
        self.assertEqual(summary["scanned"], 0,
                         "weight=0 chars must not appear in scan")
        self.assertEqual(summary["decayed"], 0)


class TestPassiveDecaySkipsNonJedi(unittest.TestCase):
    def test_non_jedi_not_decayed(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_weight_db,
        )

        async def go():
            db = await _make_db()
            # Non-Jedi PC with high weight (data anomaly — could
            # happen via admin override on a non-Jedi)
            await _insert_jedi(
                db, 10, "Han", weight=50,
                faction="independent",
                last_accrual_at=_NOW - _EIGHT_DAYS,
            )
            summary = await run_passive_decay_tick(db, now=_NOW)
            new_w = await get_weight_db(db, 10)
            return summary, new_w

        summary, new_w = _run(go())
        # SQL filter (faction='jedi_order' OR chargen_notes LIKE
        # '%jedi_path_unlocked%') excludes him at the read stage.
        self.assertEqual(summary["scanned"], 0)
        self.assertEqual(new_w, 50)


class TestPassiveDecaySkipsRetreat(unittest.TestCase):
    def test_retreat_active_jedi_not_decayed(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_weight_db,
        )

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Anakin", weight=50,
                last_accrual_at=_NOW - _EIGHT_DAYS,
                attributes_json=json.dumps({
                    "wow_retreat_active": True,
                    "wow_retreat_started_at":
                        _NOW - _EIGHT_DAYS,
                }),
            )
            summary = await run_passive_decay_tick(db, now=_NOW)
            new_w = await get_weight_db(db, 10)
            return summary, new_w

        summary, new_w = _run(go())
        self.assertEqual(summary["decayed"], 0)
        self.assertEqual(summary["skipped_retreat"], 1)
        self.assertEqual(new_w, 50)


class TestPassiveDecaySummaryShape(unittest.TestCase):
    def test_summary_dict_has_expected_keys(self):
        from engine.weight_of_war import run_passive_decay_tick

        async def go():
            db = await _make_db()
            return await run_passive_decay_tick(db, now=_NOW)

        summary = _run(go())
        for k in ("scanned", "decayed", "skipped_recent",
                  "skipped_retreat", "skipped_floor", "errors"):
            self.assertIn(k, summary)


class TestPassiveDecayMultipleJedi(unittest.TestCase):
    def test_batch_handles_mixed_eligibility(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_weight_db,
        )

        async def go():
            db = await _make_db()
            # Eligible (stale, no retreat)
            await _insert_jedi(
                db, 10, "Anakin", weight=50,
                last_accrual_at=_NOW - _EIGHT_DAYS,
            )
            # Recent — skipped
            await _insert_jedi(
                db, 11, "Obi-Wan", weight=30,
                last_accrual_at=_NOW - _ONE_DAY,
            )
            # In retreat — skipped
            await _insert_jedi(
                db, 12, "Yoda", weight=20,
                last_accrual_at=_NOW - _EIGHT_DAYS,
                attributes_json=json.dumps({
                    "wow_retreat_active": True}),
            )
            # Eligible (stale, no retreat)
            await _insert_jedi(
                db, 13, "Mace", weight=100,
                last_decay_at=_NOW - _EIGHT_DAYS,
            )
            summary = await run_passive_decay_tick(db, now=_NOW)
            weights = {
                cid: await get_weight_db(db, cid)
                for cid in (10, 11, 12, 13)
            }
            return summary, weights

        summary, weights = _run(go())
        self.assertEqual(summary["scanned"], 4)
        self.assertEqual(summary["decayed"], 2)
        self.assertEqual(summary["skipped_recent"], 1)
        self.assertEqual(summary["skipped_retreat"], 1)
        self.assertEqual(weights[10], 49)  # decayed
        self.assertEqual(weights[11], 30)  # unchanged
        self.assertEqual(weights[12], 20)  # unchanged
        self.assertEqual(weights[13], 99)  # decayed


class TestPassiveDecayFiresEventLog(unittest.TestCase):
    def test_event_row_written(self):
        from engine.weight_of_war import (
            run_passive_decay_tick, get_events,
            PASSIVE_DECAY_TRIGGER_TYPE,
        )

        async def go():
            db = await _make_db()
            await _insert_jedi(
                db, 10, "Anakin", weight=50,
                last_accrual_at=_NOW - _EIGHT_DAYS,
            )
            await run_passive_decay_tick(db, now=_NOW)
            return await get_events(db, 10, limit=5)

        events = _run(go())
        self.assertEqual(len(events), 1)
        self.assertEqual(
            events[0]["trigger_type"],
            PASSIVE_DECAY_TRIGGER_TYPE,
        )
        # Decay events log NEGATIVE delta per the substrate
        self.assertEqual(events[0]["delta"], -1)


# ═════════════════════════════════════════════════════════════════════
# 15-16. Tick handler
# ═════════════════════════════════════════════════════════════════════


class TestTickHandlerImportable(unittest.TestCase):
    def test_handler_on_module(self):
        from server import tick_handlers_progression as thp
        self.assertTrue(
            hasattr(thp, "wow_passive_decay_tick"),
            "wow_passive_decay_tick missing from progression "
            "tick handlers module",
        )


class TestTickHandlerDelegatesToEngine(unittest.TestCase):
    def test_handler_calls_engine_function(self):
        """The handler is the scheduler-side thin wrapper. It
        should delegate to engine.weight_of_war.run_passive_decay_tick
        per architecture v45 §4.5 seam discipline."""
        from server.tick_handlers_progression import (
            wow_passive_decay_tick,
        )
        from unittest.mock import patch

        called = []

        async def fake_run(db, **k):
            called.append(db)
            return {
                "scanned": 0, "decayed": 0,
                "skipped_recent": 0, "skipped_retreat": 0,
                "skipped_floor": 0, "errors": 0,
            }

        with patch(
            "engine.weight_of_war.run_passive_decay_tick",
            new=fake_run,
        ):
            ctx = MagicMock()
            ctx.db = MagicMock()
            ctx.tick_count = 100
            _run(wow_passive_decay_tick(ctx))
        self.assertEqual(len(called), 1)
        self.assertIs(called[0], ctx.db)


# ═════════════════════════════════════════════════════════════════════
# 17-20. Duel-gate wiring
# ═════════════════════════════════════════════════════════════════════


class _DuelGateTestBase(unittest.TestCase):
    """Build a minimal context for testing Challenge/Accept
    gates. The commands will fail at later stages (no real
    session_mgr, no real db) — we just want to confirm the
    retreat gate fires (or doesn't) at the very top."""

    def _make_ctx(self, char: dict, target_name: str = "rival"):
        session = MagicMock()
        session.character = char
        session.lines = []

        async def send(s):
            session.lines.append(str(s))

        session.send_line = send
        ctx = MagicMock()
        ctx.session = session
        ctx.args = target_name
        return ctx

    def _contains(self, ctx, *needles) -> bool:
        for line in ctx.session.lines:
            for n in needles:
                if n in line:
                    return True
        return False


class TestChallengeRetreatGate(_DuelGateTestBase):
    def test_jedi_in_retreat_cannot_challenge(self):
        from parser.combat_commands import ChallengeCommand
        char = {
            "id": 1, "room_id": 200, "name": "Anakin",
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": True}),
        }
        ctx = self._make_ctx(char)
        cmd = ChallengeCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass
        self.assertTrue(
            self._contains(
                ctx, "withdrawn from active duty", "+return"),
            f"Expected retreat-refusal; got: {ctx.session.lines}",
        )


class TestChallengeActiveJediProceeds(_DuelGateTestBase):
    def test_active_jedi_passes_challenge_gate(self):
        from parser.combat_commands import ChallengeCommand
        char = {
            "id": 1, "room_id": 200, "name": "Anakin",
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": False}),
        }
        ctx = self._make_ctx(char)
        cmd = ChallengeCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass
        self.assertFalse(
            self._contains(ctx, "withdrawn from active duty"),
            "Active Jedi should pass the challenge gate",
        )


class TestAcceptRetreatGate(_DuelGateTestBase):
    def test_jedi_in_retreat_cannot_accept(self):
        from parser.combat_commands import AcceptCommand
        char = {
            "id": 1, "room_id": 200, "name": "Anakin",
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": True}),
        }
        ctx = self._make_ctx(char, target_name="challenger")
        cmd = AcceptCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass
        self.assertTrue(
            self._contains(
                ctx, "withdrawn from active duty", "+return"),
            f"Expected retreat-refusal; got: {ctx.session.lines}",
        )


class TestAcceptActiveJediProceeds(_DuelGateTestBase):
    def test_active_jedi_passes_accept_gate(self):
        from parser.combat_commands import AcceptCommand
        char = {
            "id": 1, "room_id": 200, "name": "Anakin",
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": False}),
        }
        ctx = self._make_ctx(char, target_name="challenger")
        cmd = AcceptCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass
        self.assertFalse(
            self._contains(ctx, "withdrawn from active duty"),
            "Active Jedi should pass the accept gate",
        )


# ═════════════════════════════════════════════════════════════════════
# 21-22. Phantom prevention
# ═════════════════════════════════════════════════════════════════════


class TestSubstrateSurfaceImportable(unittest.TestCase):
    """Pattern 1+8 protection: every documented WoW.3b surface
    symbol must be importable. If any of these disappears, the
    tick handler or test would silently route through
    ImportError-then-AttributeError."""

    def test_surface(self):
        import engine.weight_of_war as wow
        for name in (
            "run_passive_decay_tick", "last_event_at",
            "PASSIVE_DECAY_INTERVAL_SECONDS",
            "PASSIVE_DECAY_AMOUNT",
            "PASSIVE_DECAY_TRIGGER_TYPE",
        ):
            self.assertTrue(
                hasattr(wow, name),
                f"engine.weight_of_war missing {name}",
            )

        import engine.wow_combat_hooks as wch
        for name in ("refuse_if_in_retreat",
                     "RETREAT_REFUSAL_MESSAGE"):
            self.assertTrue(
                hasattr(wch, name),
                f"engine.wow_combat_hooks missing {name}",
            )


class TestSharedRefusalMessageConsistent(unittest.TestCase):
    """All three gated commands send the SAME refusal text.
    Pattern check: a UI-string fork (one command saying
    'withdrawn', another saying 'in retreat') would be a
    silent contract drift; this test pins the shared message."""

    def test_message_is_centralized(self):
        from engine.wow_combat_hooks import RETREAT_REFUSAL_MESSAGE

        # All gated commands route through refuse_if_in_retreat
        # which uses the constant. We assert the constant is
        # non-empty and references the +return command (the
        # contract for "how do I get out of this").
        self.assertIn("+return", RETREAT_REFUSAL_MESSAGE)
        self.assertIn("withdrawn", RETREAT_REFUSAL_MESSAGE.lower())


if __name__ == "__main__":
    unittest.main()
