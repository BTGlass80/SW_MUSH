# -*- coding: utf-8 -*-
"""
tests/test_hunting_rewards_faucet_throttle_cap.py — signal-producer audit F12
(MAJOR): the mob-grind daily-cap counter must track what was actually PAID,
not the nominal pre-throttle reward.

Bug (engine/hunting_rewards.py, pre-fix): ``on_huntable_kill`` incremented
``hunting_log.daily_credits`` — the ONLY signal the soft-cap gate reads — by
the nominal ``reward`` constant, while ``db.adjust_credits`` scales a positive
faucet delta by the live ``@economy`` throttle (``db/database.py``:
``delta = (delta * pct) // 100``). Under a throttle < 100%, the cap meter
raced ahead of the player's real income; under a full (0%) suppression, the
cap could trip on kills that paid the player NOTHING.

Fix: book ``applied = new_balance - credits_before`` (a live before/after
diff on the SAME db handle, read immediately around the ``adjust_credits``
call) into ``daily_credits`` instead of the nominal ``reward``.

This suite drives the REAL path — a real ``on_huntable_kill`` call against a
real, fully-initialized in-memory ``db.database.Database`` (not a hand-rolled
fake), with the real ``@economy`` faucet throttle set via
``set_faucet_throttle_pct`` — so both the throttle math and the cap-meter
bookkeeping are exercised end to end, then re-verified by reading the
persisted character row back out of the DB.

Run: python -m pytest tests/test_hunting_rewards_faucet_throttle_cap.py
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine import hunting_rewards as hr  # noqa: E402

DAY = "2026-07-03"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db():
    """A real, fully-initialized in-memory Database — the actual
    ``adjust_credits`` faucet-throttle code path, not a stand-in."""
    from db.database import Database
    from engine.titles import ensure_schema as _title_schema

    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    await _title_schema(db)  # vanity_titles / display_title columns
    return db


async def _make_killer(db, *, credits=1000, name="Hunter"):
    account_id = await db.create_account(f"test_{name.lower()}", "smoketestpass")
    char_id = await db.create_character(account_id, {
        "name": name, "species": "Human", "template": "scout",
        "attributes": "{}", "skills": "{}",
    })
    # create_character's INSERT doesn't set credits (schema default 1000);
    # apply the requested starting balance through the canonical proxy.
    await db.save_character(char_id, credits=credits)
    return await db.get_character(char_id)


def _npc(name="Swoop Thug"):
    return {"id": 99, "name": name,
            "ai_config_json": json.dumps({"hostile": True})}


class TestAppliedNotNominal(unittest.TestCase):
    """daily_credits must increment by the APPLIED (post-throttle) amount."""

    def test_fractional_throttle_books_applied_not_nominal(self):
        async def go():
            db = await _fresh_db()
            await db.set_faucet_throttle_pct(50)
            char = await _make_killer(db, credits=1000)
            out = await hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY)

            self.assertIsNotNone(out)
            # Nominal reward is untouched (still the knob value; telemetry
            # and the reward-decision math key off it).
            self.assertEqual(out["reward"], hr.BASE_REWARD)
            # But the amount actually paid — and what the cap meter must
            # book — is halved by the throttle.
            expected_applied = (hr.BASE_REWARD * 50) // 100
            self.assertNotEqual(expected_applied, hr.BASE_REWARD,
                                "fixture is only meaningful if throttle "
                                "actually changes the paid amount")
            self.assertEqual(out["applied"], expected_applied)
            self.assertEqual(out["daily_credits"], expected_applied)
            self.assertEqual(out["new_balance"], 1000 + expected_applied)

            # Re-read from the DB — the persisted ledger must agree with
            # what the function returned (no in-memory-only drift).
            row = await db.get_character(char["id"])
            self.assertEqual(row["credits"], 1000 + expected_applied)
            attrs = json.loads(row["attributes"])
            self.assertEqual(
                attrs[hr.HUNT_LOG_KEY]["daily_credits"], expected_applied)
        _run(go())

    def test_full_suppression_books_zero_not_nominal(self):
        async def go():
            db = await _fresh_db()
            await db.set_faucet_throttle_pct(0)
            char = await _make_killer(db, credits=1000)
            out = await hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY)

            self.assertIsNotNone(out)
            self.assertEqual(out["reward"], hr.BASE_REWARD)  # nominal, unchanged
            self.assertEqual(out["applied"], 0)               # nothing was paid
            self.assertEqual(out["daily_credits"], 0)
            self.assertEqual(out["new_balance"], 1000)         # balance untouched

            row = await db.get_character(char["id"])
            self.assertEqual(row["credits"], 1000)
            attrs = json.loads(row["attributes"])
            self.assertEqual(attrs[hr.HUNT_LOG_KEY]["daily_credits"], 0)
            # Prestige (kill count) is NOT gated by the faucet — it's not
            # credits, so it advances even at full throttle suppression.
            self.assertEqual(attrs[hr.HUNT_LOG_KEY]["kills"], 1)
        _run(go())


class TestCapEngagesOnRealTotal(unittest.TestCase):
    """The soft cap must gate on real (applied) income, never nominal."""

    def test_full_suppression_never_trips_the_cap_though_nominal_would(self):
        # 30 kills * BASE_REWARD nominal comfortably clears DAILY_SOFT_CAP
        # (400) under the OLD nominal-booking bug -- but at 0% throttle no
        # real credit ever lands, so the cap must never engage.
        self.assertGreater(30 * hr.BASE_REWARD, hr.DAILY_SOFT_CAP,
                            "fixture needs nominal-would-have-capped headroom")

        async def go():
            db = await _fresh_db()
            await db.set_faucet_throttle_pct(0)
            char = await _make_killer(db, credits=1000)

            last = None
            for _ in range(30):
                last = await hr.on_huntable_kill(db, char, _npc(),
                                                  day_stamp=DAY)
                char = await db.get_character(char["id"])

            self.assertIsNotNone(last)
            self.assertEqual(last["daily_credits"], 0)
            self.assertFalse(last["at_cap"])
            self.assertEqual(char["credits"], 1000)  # zero real income, ever
            attrs = json.loads(char["attributes"])
            self.assertEqual(attrs[hr.HUNT_LOG_KEY]["kills"], 30)
            self.assertEqual(attrs[hr.HUNT_LOG_KEY]["daily_credits"], 0)
        _run(go())

    def test_cap_engages_exactly_at_the_real_credited_total(self):
        # Seed the log at 50%-throttle real income one kill short of the
        # cap boundary (achieved via applied, not nominal, accounting).
        applied_per_kill = (hr.BASE_REWARD * 50) // 100
        seed_daily = hr.DAILY_SOFT_CAP - applied_per_kill  # one kill shy

        async def go():
            db = await _fresh_db()
            await db.set_faucet_throttle_pct(50)
            char = await _make_killer(db, credits=1000)
            attrs = {hr.HUNT_LOG_KEY: {"kills": 10,
                                       "daily_credits": seed_daily,
                                       "day": DAY}}
            await db.save_character(char["id"], attributes=json.dumps(attrs))
            char = await db.get_character(char["id"])

            # Not yet at cap.
            self.assertLess(seed_daily, hr.DAILY_SOFT_CAP)

            out = await hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY)
            self.assertEqual(out["daily_credits"],
                             seed_daily + applied_per_kill)
            self.assertGreaterEqual(out["daily_credits"], hr.DAILY_SOFT_CAP)
            self.assertTrue(out["at_cap"])
        _run(go())


class TestBeforeAfterInvariant(unittest.TestCase):
    """applied always equals the real balance delta the kill produced."""

    def test_applied_equals_balance_delta_at_100_pct(self):
        async def go():
            db = await _fresh_db()
            # Default throttle (100%) is the behaviour-identical no-op case.
            char = await _make_killer(db, credits=500)
            out = await hr.on_huntable_kill(db, char, _npc(), day_stamp=DAY)
            self.assertEqual(out["applied"], hr.BASE_REWARD)
            self.assertEqual(out["reward"], out["applied"])
            self.assertEqual(out["new_balance"], 500 + hr.BASE_REWARD)
        _run(go())


if __name__ == "__main__":
    unittest.main()
