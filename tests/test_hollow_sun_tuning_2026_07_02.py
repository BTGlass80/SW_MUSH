# -*- coding: utf-8 -*-
"""tests/test_hollow_sun_tuning_2026_07_02.py

Pins the two Hollow-Sun playable-scenario tuning decisions Brian made after the
live break-it validation (2026-07-02):

  * MENACE ~6h window for STAGED cults — the staged menace is a one-way failure
    clock (strikes don't push it down), and at the legacy 0.35/min it auto-lost
    in ~3.1h while the 48h deadline never bound. Brian: a "one session" ~6h
    window -> staged_menace_per_minute() = 0.18. Legacy strike-path cults keep
    0.35 (advance_menace's default).
  * WIN CAPSTONE — the headline rout used to pay 0 credits (rep + title only) and
    each stage's loot ran LOWER than a standalone anomaly. Brian: a "bigger"
    ~1000cr capstone + a named relic. Credits to every title-earning contributor;
    the relic to the single top contributor.

Run: python -m pytest tests/test_hollow_sun_tuning_2026_07_02.py
"""
from __future__ import annotations

import asyncio
import json
import unittest

import engine.communal_objective as CO
import engine.communal_objective_runtime as COR


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _DB:
    """Tiny aiosqlite-shaped stub — enough for _distribute_rewards' capstone path
    (get/save character + the metered adjust_credits faucet)."""
    def __init__(self):
        self.chars: dict[int, dict] = {}

    async def get_character(self, cid):
        return self.chars.get(int(cid))

    async def save_character(self, cid, **kw):
        self.chars.setdefault(int(cid), {"id": int(cid)}).update(kw)

    async def adjust_credits(self, cid, delta, tag):
        c = self.chars.setdefault(int(cid), {"id": int(cid), "credits": 0})
        c["credits"] = int(c.get("credits", 0)) + int(delta)
        return c["credits"]


class TestStagedMenaceWindow(unittest.TestCase):

    def test_staged_rate_is_slower_than_legacy(self):
        self.assertLess(CO.staged_menace_per_minute(), CO.menace_per_minute())
        self.assertAlmostEqual(CO.staged_menace_per_minute(), 0.18, places=3)

    def test_staged_window_is_about_six_hours(self):
        rate = CO.staged_menace_per_minute()
        # still ACTIVE at ~3h (would have auto-lost at the legacy pace)
        self.assertLess(
            CO.advance_menace(CO.MENACE_START, 180, per_minute=rate),
            CO.MENACE_MAX)
        # reaches auto-loss by ~6.1h
        self.assertGreaterEqual(
            CO.advance_menace(CO.MENACE_START, 366, per_minute=rate),
            CO.MENACE_MAX)

    def test_legacy_default_rate_unchanged(self):
        # no per_minute arg -> legacy 0.35/min: 35 + 0.35*60 = 56
        self.assertAlmostEqual(CO.advance_menace(35, 60), 56.0, places=1)

    def test_advance_menace_still_clamps(self):
        self.assertEqual(CO.advance_menace(95, 999, per_minute=0.18), CO.MENACE_MAX)

    def test_negative_rate_cannot_self_route(self):
        # a hostile tunable can't turn escalation into a self-win
        self.assertGreaterEqual(CO.advance_menace(50, 60, per_minute=-5.0), 50.0)


class TestWinCapstone(unittest.TestCase):

    def test_capstone_amount_default(self):
        self.assertEqual(CO.win_capstone_credits(), 1000)

    def test_win_pays_capstone_to_title_earners_and_relic_to_top(self):
        async def go():
            db = _DB()
            for cid in (1, 2, 3):
                db.chars[cid] = {"id": cid, "credits": 0,
                                 "attributes": "{}", "inventory": "{}"}
            cult = CO.CULT_BY_KEY["hollow_sun"]
            # shares of 105: 57% / 38% / 4.8% -> #1,#2 earn a title (>=10%), #3 not
            contribs = {"1": {"points": 60}, "2": {"points": 40}, "3": {"points": 5}}
            await COR._distribute_rewards(db, None, cult, contribs)

            cap = CO.win_capstone_credits()
            # title-earning contributors each get the capstone bounty
            self.assertEqual(db.chars[1]["credits"], cap)
            self.assertEqual(db.chars[2]["credits"], cap)
            # a below-threshold contributor gets NO capstone
            self.assertEqual(db.chars[3]["credits"], 0)

            # the single top contributor gets the one-off cult relic...
            inv1 = json.loads(db.chars[1]["inventory"])
            relics1 = [i for i in inv1.get("items", []) if i.get("is_capstone_loot")]
            self.assertEqual(len(relics1), 1)
            self.assertEqual(relics1[0]["key"], "hollow_sun_reliquary")
            # ...and no one else does
            inv2 = json.loads(db.chars[2]["inventory"])
            self.assertEqual(
                [i for i in inv2.get("items", []) if i.get("is_capstone_loot")], [])
        _run(go())

    def test_zero_capstone_pays_no_credits(self):
        """A tunable of 0 disables the capstone credits (relic still drops)."""
        import engine.tunables as _T
        orig = _T.get_tunable

        def _patched(key, default=None):
            if key == "communal.win_capstone_credits":
                return 0
            return orig(key, default)

        _T.get_tunable = _patched
        try:
            async def go():
                db = _DB()
                db.chars[1] = {"id": 1, "credits": 0,
                               "attributes": "{}", "inventory": "{}"}
                cult = CO.CULT_BY_KEY["hollow_sun"]
                await COR._distribute_rewards(db, None, cult, {"1": {"points": 100}})
                self.assertEqual(db.chars[1]["credits"], 0)  # no capstone credits
                inv = json.loads(db.chars[1]["inventory"])
                self.assertEqual(
                    len([i for i in inv.get("items", []) if i.get("is_capstone_loot")]),
                    1)  # relic still drops
            _run(go())
        finally:
            _T.get_tunable = orig


if __name__ == "__main__":
    unittest.main()
