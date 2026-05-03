# -*- coding: utf-8 -*-
"""
tests/test_pg3b_gates.py — Progression Gates Phase 3, sub-drop b.

Tests the second half of PG.3:

  1. Force-sign trigger seam (engine/force_signs.py) — covers
     eligibility filtering (pre-gate, already-invited), probability
     scaling by predisposition, atomic increment, and threshold
     detection.

  2. Village quest cooldown helpers (engine/jedi_gating.py) — covers
     the 7-day Act 1→2 cooldown, the 14-day inter-trial cooldown,
     the 24-hour Trial of Courage retry cooldown, and the
     format_remaining helper.

  3. Force-sign emission tick handler — verifies the per-minute
     handler against fake sessions, including pre-gate / idle /
     not-in-game filtering and the threshold-hit logging.

  4. STEP_FORCE removal from chargen — verifies the chargen step
     ladders no longer include STEP_FORCE, that skills flows
     directly to background, and that force_sensitive defaults
     to False on new characters.

Test sections:
  1. TestForceSignProbability       — _effective_probability math
  2. TestGetForceSignState          — read-only state summary
  3. TestMaybeEmitForceSign         — DB-level trigger seam
  4. TestActCooldowns               — Act 1→2 cooldown helpers
  5. TestTrialCooldowns             — 14-day inter-trial cooldown
  6. TestCourageRetryCooldown       — 24-hour Courage retry
  7. TestFormatRemaining            — duration formatter
  8. TestForceSignTick              — tick handler integration
  9. TestStepForceRemoval           — chargen ladder no longer has FS
 10. TestModuleSelfDocs             — source-level marker
"""
from __future__ import annotations

import asyncio
import os
import random
import sys
import time
import unittest
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_char(db, name="Tester", play_time=0, predisposition=0.0,
                     signs=0):
    """Insert a minimal account + character with PG.1 columns set."""
    await db._db.execute(
        "INSERT INTO accounts(username, password_hash) VALUES(?, 'x')",
        (name.lower(),),
    )
    await db._db.execute(
        "INSERT INTO characters(account_id, name, play_time_seconds, "
        "force_predisposition, force_signs_accumulated) "
        "VALUES(1, ?, ?, ?, ?)",
        (name, play_time, predisposition, signs),
    )
    await db._db.commit()
    rows = await db._db.execute_fetchall(
        "SELECT id FROM characters WHERE name=?", (name,),
    )
    return rows[0]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Probability math
# ─────────────────────────────────────────────────────────────────────────────

class TestForceSignProbability(unittest.TestCase):

    def test_zero_predisposition_uses_base(self):
        from engine.force_signs import (
            _effective_probability, BASE_SIGN_PROBABILITY_PER_TICK,
        )
        self.assertAlmostEqual(
            _effective_probability(0.0),
            BASE_SIGN_PROBABILITY_PER_TICK,
            places=6,
        )

    def test_max_predisposition_triples_base(self):
        from engine.force_signs import (
            _effective_probability, BASE_SIGN_PROBABILITY_PER_TICK,
        )
        # multiplier = 1 + 1.0 * 2.0 = 3.0
        self.assertAlmostEqual(
            _effective_probability(1.0),
            BASE_SIGN_PROBABILITY_PER_TICK * 3.0,
            places=6,
        )

    def test_half_predisposition_doubles_base(self):
        from engine.force_signs import (
            _effective_probability, BASE_SIGN_PROBABILITY_PER_TICK,
        )
        self.assertAlmostEqual(
            _effective_probability(0.5),
            BASE_SIGN_PROBABILITY_PER_TICK * 2.0,
            places=6,
        )

    def test_negative_predisposition_clamped(self):
        from engine.force_signs import (
            _effective_probability, BASE_SIGN_PROBABILITY_PER_TICK,
        )
        self.assertAlmostEqual(
            _effective_probability(-0.5),
            BASE_SIGN_PROBABILITY_PER_TICK,
            places=6,
        )

    def test_above_one_predisposition_clamped(self):
        from engine.force_signs import (
            _effective_probability, BASE_SIGN_PROBABILITY_PER_TICK,
        )
        self.assertAlmostEqual(
            _effective_probability(2.0),
            BASE_SIGN_PROBABILITY_PER_TICK * 3.0,
            places=6,
        )

    def test_probability_in_unit_range(self):
        """Even worst-case parameters keep p in [0, 1]."""
        from engine.force_signs import _effective_probability
        for pd in (0.0, 0.25, 0.5, 0.75, 1.0):
            p = _effective_probability(pd)
            self.assertGreaterEqual(p, 0.0)
            self.assertLessEqual(p, 1.0)

    def test_design_target_invitation_pacing(self):
        """At p_d=0.0, ~30 hours expected to 5 signs.
        At p_d=1.0, ~10 hours expected. Per design §2.4."""
        from engine.force_signs import _effective_probability
        # Expected ticks per sign = 1/p. Each tick is 60s = 1 minute.
        # So expected hours per sign = (1/p) / 60.
        # For 5 signs: hours = 5 / p / 60.
        p0 = _effective_probability(0.0)
        hours_p0 = 5 / p0 / 60
        self.assertGreater(hours_p0, 20)
        self.assertLess(hours_p0, 50)
        p1 = _effective_probability(1.0)
        hours_p1 = 5 / p1 / 60
        self.assertGreater(hours_p1, 5)
        self.assertLess(hours_p1, 15)


# ─────────────────────────────────────────────────────────────────────────────
# 2. State summary
# ─────────────────────────────────────────────────────────────────────────────

class TestGetForceSignState(unittest.TestCase):

    def test_fresh_char_zero_state(self):
        from engine.force_signs import get_force_sign_state
        s = get_force_sign_state({
            "play_time_seconds": 0,
            "force_predisposition": 0.0,
            "force_signs_accumulated": 0,
        })
        self.assertEqual(s["play_time_seconds"], 0)
        self.assertEqual(s["predisposition"], 0.0)
        self.assertEqual(s["signs_accumulated"], 0)
        self.assertEqual(s["signs_required"], 5)
        self.assertFalse(s["gate_passed"])
        self.assertFalse(s["invitation_received"])

    def test_post_gate_pre_invitation(self):
        from engine.force_signs import get_force_sign_state
        s = get_force_sign_state({
            "play_time_seconds": 60 * 60 * 60,  # 60 hours
            "force_predisposition": 0.5,
            "force_signs_accumulated": 3,
        })
        self.assertTrue(s["gate_passed"])
        self.assertFalse(s["invitation_received"])

    def test_post_invitation(self):
        from engine.force_signs import get_force_sign_state
        s = get_force_sign_state({
            "play_time_seconds": 100 * 60 * 60,
            "force_predisposition": 0.7,
            "force_signs_accumulated": 5,
        })
        self.assertTrue(s["gate_passed"])
        self.assertTrue(s["invitation_received"])

    def test_missing_fields_defaults(self):
        """Empty dict shouldn't crash — all fields default to safe."""
        from engine.force_signs import get_force_sign_state
        s = get_force_sign_state({})
        self.assertEqual(s["play_time_seconds"], 0)
        self.assertFalse(s["gate_passed"])
        self.assertFalse(s["invitation_received"])

    def test_has_received_invitation_helper(self):
        from engine.force_signs import has_received_invitation
        self.assertFalse(has_received_invitation({"force_signs_accumulated": 4}))
        self.assertTrue(has_received_invitation({"force_signs_accumulated": 5}))
        self.assertTrue(has_received_invitation({"force_signs_accumulated": 10}))
        self.assertFalse(has_received_invitation({}))


# ─────────────────────────────────────────────────────────────────────────────
# 3. maybe_emit_force_sign DB-level
# ─────────────────────────────────────────────────────────────────────────────

class _DeterministicRng:
    """Tiny RNG that returns scripted floats. Lets tests force a hit
    or miss without inspecting probability internals."""
    def __init__(self, scripted):
        self._values = list(scripted)
        self._pos = 0

    def random(self):
        v = self._values[self._pos]
        self._pos += 1
        return v


class TestMaybeEmitForceSign(unittest.TestCase):

    def test_pre_gate_no_roll(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            # 10 hours of playtime — well under 50.
            cid = await _make_char(db, play_time=10 * 60 * 60,
                                   predisposition=1.0)
            # Even with p_d=1.0 we should never roll pre-gate.
            outcome = await maybe_emit_force_sign(
                db, cid, rng=_DeterministicRng([0.0]),
            )
            self.assertEqual(outcome, SignOutcome.NOT_ELIGIBLE_PRE_GATE)
            # Counter unchanged
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 0)
            await db._db.close()
        _run(_check())

    def test_already_invited_no_roll(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            cid = await _make_char(
                db, play_time=100 * 60 * 60,
                predisposition=0.5, signs=5,
            )
            outcome = await maybe_emit_force_sign(
                db, cid, rng=_DeterministicRng([0.0]),
            )
            self.assertEqual(outcome, SignOutcome.ALREADY_INVITED)
            # Should NOT have incremented past 5.
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 5)
            await db._db.close()
        _run(_check())

    def test_post_gate_roll_miss(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=0.0)
            # Force a miss: r=0.99 vs base p=0.0028.
            outcome = await maybe_emit_force_sign(
                db, cid, rng=_DeterministicRng([0.99]),
            )
            self.assertEqual(outcome, SignOutcome.ROLLED_NO_SIGN)
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 0)
            await db._db.close()
        _run(_check())

    def test_post_gate_roll_hit(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=1.0)
            outcome = await maybe_emit_force_sign(
                db, cid, rng=_DeterministicRng([0.0]),
            )
            self.assertEqual(outcome, SignOutcome.SIGN_EMITTED)
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 1)
            await db._db.close()
        _run(_check())

    def test_threshold_hit_returns_invitation_sentinel(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            # Already at 4 signs; one more hits invitation.
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=1.0, signs=4)
            outcome = await maybe_emit_force_sign(
                db, cid, rng=_DeterministicRng([0.0]),
            )
            self.assertEqual(outcome, SignOutcome.SIGN_THRESHOLD_HIT)
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 5)
            await db._db.close()
        _run(_check())

    def test_unknown_char_returns_pre_gate(self):
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            outcome = await maybe_emit_force_sign(db, 99999)
            self.assertEqual(outcome, SignOutcome.NOT_ELIGIBLE_PRE_GATE)
            await db._db.close()
        _run(_check())

    def test_passed_char_dict_avoids_db_select(self):
        """Caller-supplied char dict should be used instead of fetched."""
        async def _check():
            from engine.force_signs import maybe_emit_force_sign, SignOutcome
            db = await _fresh_db()
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=1.0)
            char = {
                "play_time_seconds": 60 * 60 * 60,
                "force_predisposition": 1.0,
                "force_signs_accumulated": 0,
            }
            outcome = await maybe_emit_force_sign(
                db, cid, char=char, rng=_DeterministicRng([0.0]),
            )
            self.assertEqual(outcome, SignOutcome.SIGN_EMITTED)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 4. Act 1 → Act 2 cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestActCooldowns(unittest.TestCase):

    def test_pre_act_1_returns_infinite(self):
        from engine.jedi_gating import act_2_unlock_seconds_remaining
        # Character hasn't even been invited yet.
        self.assertEqual(
            act_2_unlock_seconds_remaining({"village_act": 0}),
            float("inf"),
        )
        self.assertFalse(
            __import__("engine.jedi_gating",
                       fromlist=["act_2_unlock_ready"])
                .act_2_unlock_ready({"village_act": 0})
        )

    def test_already_act_2_or_beyond_zero(self):
        from engine.jedi_gating import (
            act_2_unlock_seconds_remaining, act_2_unlock_ready,
        )
        for act in (2, 3):
            self.assertEqual(
                act_2_unlock_seconds_remaining({"village_act": act}),
                0.0,
            )
            self.assertTrue(act_2_unlock_ready({"village_act": act}))

    def test_act_1_just_started_full_cooldown(self):
        from engine.jedi_gating import (
            act_2_unlock_seconds_remaining,
            ACT_1_TO_ACT_2_COOLDOWN_SECONDS,
        )
        now = 1_000_000.0
        char = {
            "village_act": 1,
            "village_act_unlocked_at": now,
        }
        remaining = act_2_unlock_seconds_remaining(char, now=now)
        self.assertEqual(remaining, ACT_1_TO_ACT_2_COOLDOWN_SECONDS)

    def test_act_1_partway_through_cooldown(self):
        from engine.jedi_gating import (
            act_2_unlock_seconds_remaining,
            ACT_1_TO_ACT_2_COOLDOWN_SECONDS,
        )
        # 3 days into the 7-day cooldown
        unlocked_at = 1_000_000.0
        now = unlocked_at + (3 * 24 * 60 * 60)
        char = {
            "village_act": 1,
            "village_act_unlocked_at": unlocked_at,
        }
        remaining = act_2_unlock_seconds_remaining(char, now=now)
        self.assertEqual(
            remaining,
            ACT_1_TO_ACT_2_COOLDOWN_SECONDS - (3 * 24 * 60 * 60),
        )

    def test_act_1_cooldown_cleared(self):
        from engine.jedi_gating import (
            act_2_unlock_seconds_remaining, act_2_unlock_ready,
            ACT_1_TO_ACT_2_COOLDOWN_SECONDS,
        )
        unlocked_at = 1_000_000.0
        now = unlocked_at + ACT_1_TO_ACT_2_COOLDOWN_SECONDS + 100
        char = {
            "village_act": 1,
            "village_act_unlocked_at": unlocked_at,
        }
        self.assertEqual(act_2_unlock_seconds_remaining(char, now=now), 0.0)
        self.assertTrue(act_2_unlock_ready(char, now=now))

    def test_missing_unlocked_at_treated_as_ready(self):
        """Defensive: bad data shouldn't trap the player."""
        from engine.jedi_gating import act_2_unlock_seconds_remaining
        char = {"village_act": 1, "village_act_unlocked_at": 0}
        self.assertEqual(act_2_unlock_seconds_remaining(char, now=2e9), 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 5. 14-day inter-trial cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestTrialCooldowns(unittest.TestCase):

    def test_no_attempt_yet_zero(self):
        from engine.jedi_gating import (
            trial_cooldown_seconds_remaining, trial_cooldown_ready,
        )
        char = {"village_trial_last_attempt": 0}
        self.assertEqual(trial_cooldown_seconds_remaining(char), 0.0)
        self.assertTrue(trial_cooldown_ready(char))

    def test_just_attempted_full_cooldown(self):
        from engine.jedi_gating import (
            trial_cooldown_seconds_remaining,
            INTER_TRIAL_COOLDOWN_SECONDS,
        )
        now = 1_000_000.0
        char = {"village_trial_last_attempt": now}
        self.assertEqual(
            trial_cooldown_seconds_remaining(char, now=now),
            INTER_TRIAL_COOLDOWN_SECONDS,
        )

    def test_partway_through_cooldown(self):
        from engine.jedi_gating import (
            trial_cooldown_seconds_remaining,
            INTER_TRIAL_COOLDOWN_SECONDS,
        )
        # 7 days into the 14-day cooldown
        last = 1_000_000.0
        now = last + (7 * 24 * 60 * 60)
        char = {"village_trial_last_attempt": last}
        self.assertEqual(
            trial_cooldown_seconds_remaining(char, now=now),
            INTER_TRIAL_COOLDOWN_SECONDS - (7 * 24 * 60 * 60),
        )

    def test_cooldown_cleared(self):
        from engine.jedi_gating import (
            trial_cooldown_ready, INTER_TRIAL_COOLDOWN_SECONDS,
        )
        last = 1_000_000.0
        now = last + INTER_TRIAL_COOLDOWN_SECONDS + 100
        char = {"village_trial_last_attempt": last}
        self.assertTrue(trial_cooldown_ready(char, now=now))


# ─────────────────────────────────────────────────────────────────────────────
# 6. 24-hour Trial of Courage retry cooldown
# ─────────────────────────────────────────────────────────────────────────────

class TestCourageRetryCooldown(unittest.TestCase):

    def test_no_attempt_yet_zero(self):
        from engine.jedi_gating import courage_retry_cooldown_ready
        self.assertTrue(courage_retry_cooldown_ready({
            "village_trial_last_attempt": 0,
        }))

    def test_just_attempted_full_24h(self):
        from engine.jedi_gating import (
            courage_retry_cooldown_seconds_remaining,
            TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS,
        )
        now = 1_000_000.0
        char = {"village_trial_last_attempt": now}
        self.assertEqual(
            courage_retry_cooldown_seconds_remaining(char, now=now),
            TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS,
        )

    def test_after_24h_cleared(self):
        from engine.jedi_gating import (
            courage_retry_cooldown_ready,
            TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS,
        )
        last = 1_000_000.0
        now = last + TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS + 1
        char = {"village_trial_last_attempt": last}
        self.assertTrue(courage_retry_cooldown_ready(char, now=now))


# ─────────────────────────────────────────────────────────────────────────────
# 7. Format remaining duration
# ─────────────────────────────────────────────────────────────────────────────

class TestFormatRemaining(unittest.TestCase):

    def test_zero_now(self):
        from engine.jedi_gating import format_remaining
        self.assertEqual(format_remaining(0), "Now")
        self.assertEqual(format_remaining(-5), "Now")

    def test_infinity_dash(self):
        from engine.jedi_gating import format_remaining
        self.assertEqual(format_remaining(float("inf")), "—")

    def test_minutes_only(self):
        from engine.jedi_gating import format_remaining
        self.assertEqual(format_remaining(5 * 60), "5m")
        self.assertEqual(format_remaining(45 * 60), "45m")

    def test_hours_and_minutes(self):
        from engine.jedi_gating import format_remaining
        self.assertEqual(format_remaining(72 * 60), "1h 12m")

    def test_days_hours_minutes(self):
        from engine.jedi_gating import format_remaining
        # 6 days, 23 hours, 45 minutes
        s = (6 * 86400) + (23 * 3600) + (45 * 60)
        self.assertEqual(format_remaining(s), "6d 23h 45m")

    def test_exact_day(self):
        from engine.jedi_gating import format_remaining
        # 7 days exactly should drop the trailing 0h 0m
        self.assertEqual(format_remaining(7 * 86400), "7d")


# ─────────────────────────────────────────────────────────────────────────────
# 8. force_sign_emit_tick handler
# ─────────────────────────────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, char_id, in_game=True, idle_for_seconds=0,
                 play_time=0, predisposition=0.0, signs=0):
        self.id = char_id
        self.character = {
            "id": char_id,
            "play_time_seconds": play_time,
            "force_predisposition": predisposition,
            "force_signs_accumulated": signs,
        }
        self._idle_for = idle_for_seconds
        self._in_game = in_game
        self.last_activity = time.time() - idle_for_seconds

    @property
    def is_in_game(self):
        return self._in_game

    def is_idle_for(self, threshold):
        return self._idle_for > threshold


class _FakeSessionMgr:
    def __init__(self, sessions):
        self._sessions = list(sessions)

    @property
    def all(self):
        return list(self._sessions)


class TestForceSignTick(unittest.TestCase):

    def _ctx(self, db, sessions):
        from server.tick_scheduler import TickContext
        return TickContext(
            server=MagicMock(),
            db=db,
            session_mgr=_FakeSessionMgr(sessions),
            tick_count=60,
            ships_in_space=[],
        )

    def test_pre_gate_session_skipped(self):
        async def _check():
            from server.tick_handlers_progression import (
                force_sign_emit_tick,
            )
            db = await _fresh_db()
            cid = await _make_char(db, play_time=10 * 60 * 60,
                                   predisposition=1.0)
            sess = _FakeSession(cid, in_game=True, idle_for_seconds=5,
                                play_time=10 * 60 * 60, predisposition=1.0)
            ctx = self._ctx(db, [sess])
            # Should not raise; pre-gate filter inside maybe_emit
            await force_sign_emit_tick(ctx)
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 0)
            await db._db.close()
        _run(_check())

    def test_idle_session_skipped(self):
        async def _check():
            from server.tick_handlers_progression import (
                force_sign_emit_tick, IDLE_THRESHOLD_SECONDS,
            )
            db = await _fresh_db()
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=1.0)
            sess = _FakeSession(
                cid, in_game=True,
                idle_for_seconds=IDLE_THRESHOLD_SECONDS + 1,
                play_time=60 * 60 * 60, predisposition=1.0,
            )
            ctx = self._ctx(db, [sess])
            await force_sign_emit_tick(ctx)
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["force_signs_accumulated"], 0)
            await db._db.close()
        _run(_check())

    def test_empty_session_list_safe(self):
        async def _check():
            from server.tick_handlers_progression import force_sign_emit_tick
            db = await _fresh_db()
            ctx = self._ctx(db, [])
            await force_sign_emit_tick(ctx)
            await db._db.close()
        _run(_check())

    def test_handler_registered_in_game_server(self):
        path = os.path.join(PROJECT_ROOT, "server", "game_server.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            'register("force_sign_emit"', src,
            "force_sign_emit tick handler should be registered",
        )
        self.assertIn(
            "force_sign_emit_tick", src,
            "force_sign_emit_tick should be imported in game_server.py",
        )

    def test_post_gate_session_can_get_sign(self):
        """Statistical test: with predisposition=1.0 and 100 ticks,
        a post-gate active session should see at least one sign."""
        async def _check():
            from server.tick_handlers_progression import force_sign_emit_tick
            db = await _fresh_db()
            cid = await _make_char(db, play_time=60 * 60 * 60,
                                   predisposition=1.0)
            # Run many ticks; expected ~1 sign per ~120 ticks at p_d=1.0.
            # At 1000 ticks we should reliably see >= 1 sign.
            random.seed(42)
            for _ in range(1000):
                sess = _FakeSession(
                    cid, in_game=True, idle_for_seconds=5,
                    play_time=60 * 60 * 60, predisposition=1.0,
                )
                ctx = self._ctx(db, [sess])
                await force_sign_emit_tick(ctx)
                # Re-read the persisted sign count so the caller sees
                # the cached value progress.
                rows = await db._db.execute_fetchall(
                    "SELECT force_signs_accumulated FROM characters "
                    "WHERE id=?", (cid,),
                )
                if rows[0]["force_signs_accumulated"] >= 1:
                    break
            rows = await db._db.execute_fetchall(
                "SELECT force_signs_accumulated FROM characters WHERE id=?",
                (cid,),
            )
            self.assertGreaterEqual(rows[0]["force_signs_accumulated"], 1)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 9. STEP_FORCE removal from chargen
# ─────────────────────────────────────────────────────────────────────────────

class TestStepForceRemoval(unittest.TestCase):

    def test_step_force_constant_still_exists(self):
        """The constant is preserved as orphaned dead code so external
        imports don't break, but it must not appear in the step ladders."""
        from engine.creation_wizard import STEP_FORCE
        self.assertEqual(STEP_FORCE, "force")

    def test_step_force_not_in_scratch_legacy(self):
        from engine.creation_wizard import (
            STEP_FORCE, SCRATCH_STEPS_LEGACY,
        )
        self.assertNotIn(STEP_FORCE, SCRATCH_STEPS_LEGACY)

    def test_step_force_not_in_scratch_cw(self):
        from engine.creation_wizard import (
            STEP_FORCE, SCRATCH_STEPS_CW,
        )
        self.assertNotIn(STEP_FORCE, SCRATCH_STEPS_CW)

    def test_step_force_not_in_template_legacy(self):
        from engine.creation_wizard import (
            STEP_FORCE, TEMPLATE_STEPS_LEGACY,
        )
        self.assertNotIn(STEP_FORCE, TEMPLATE_STEPS_LEGACY)

    def test_step_force_not_in_template_cw(self):
        from engine.creation_wizard import (
            STEP_FORCE, TEMPLATE_STEPS_CW,
        )
        self.assertNotIn(STEP_FORCE, TEMPLATE_STEPS_CW)

    def test_skills_flows_to_background(self):
        """After PG.3.gates.b, finishing skills routes to background,
        not to force. Source-level guard."""
        path = os.path.join(PROJECT_ROOT, "engine", "creation_wizard.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        # The old line 'self.step = STEP_FORCE' should be gone from
        # _handle_skills (the comment trail still mentions it).
        # Confirm by looking for the key substring inside the _handle_skills
        # block: look for the new routing.
        self.assertIn("self.step = STEP_BACKGROUND", src)

    def test_force_sensitive_defaults_false_at_chargen(self):
        """Even if the wizard's _force_sensitive flag exists, fresh
        wizards initialize it to False — no chargen step can flip it."""
        from engine.creation_wizard import CreationWizard

        class _MockReg:
            def get(self, *a, **kw): return None
            def __getattr__(self, name): return lambda *a, **kw: None
            def skills_for_attribute(self, *a, **kw): return []

        w = CreationWizard(_MockReg(), _MockReg(), width=80)
        self.assertFalse(w._force_sensitive)
        attrs = w._chargen_attrs_for_chain_check()
        self.assertFalse(attrs.get("force_sensitive"))

    def test_legacy_force_sensitive_setter_still_works(self):
        """The flag can still be set programmatically (e.g. by future
        Village-quest-completion code). PG.3.gates.b removes the
        chargen UI for it, not the flag itself."""
        from engine.creation_wizard import CreationWizard

        class _MockReg:
            def get(self, *a, **kw): return None
            def __getattr__(self, name): return lambda *a, **kw: None
            def skills_for_attribute(self, *a, **kw): return []

        w = CreationWizard(_MockReg(), _MockReg(), width=80)
        w._force_sensitive = True
        attrs = w._chargen_attrs_for_chain_check()
        self.assertTrue(attrs.get("force_sensitive"))


# ─────────────────────────────────────────────────────────────────────────────
# 10. Source-level marker for the drop
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleSelfDocs(unittest.TestCase):

    def test_force_signs_module_references_design(self):
        path = os.path.join(PROJECT_ROOT, "engine", "force_signs.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("PG.3.gates.b", src)
        self.assertIn(
            "progression_gates_and_consequences_design_v1.md", src,
        )

    def test_jedi_gating_has_cooldown_constants(self):
        from engine.jedi_gating import (
            ACT_1_TO_ACT_2_COOLDOWN_SECONDS,
            INTER_TRIAL_COOLDOWN_SECONDS,
            TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS,
        )
        self.assertEqual(ACT_1_TO_ACT_2_COOLDOWN_SECONDS, 7 * 86400)
        self.assertEqual(INTER_TRIAL_COOLDOWN_SECONDS, 14 * 86400)
        self.assertEqual(TRIAL_COURAGE_RETRY_COOLDOWN_SECONDS, 86400)

    def test_creation_wizard_documents_step_force_removal(self):
        path = os.path.join(PROJECT_ROOT, "engine", "creation_wizard.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("PG.3.gates.b", src)
        self.assertIn("Force Sensitivity step removed", src)


if __name__ == "__main__":
    unittest.main()
