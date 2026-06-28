# -*- coding: utf-8 -*-
"""tests/test_vanity_title_cost_tunables.py — T3.19 config breadth for the
vanity-title prestige-SINK cost curve (engine/titles.py).

The ``@balance progress`` board's "Vanity titles … cr soaked" line lets an
operator OBSERVE the prestige sink (which tiers sell, how much veteran credit it
soaks), but the 8-tier cost curve it informs was a hardcoded ``VANITY_TITLES``
constant — the very lever the producer's own telemetry comment names ("the signal
for tuning the 8-tier VANITY_TITLES cost curve (2k→400k): a dead top tier is
priced past reach; everyone parked on the cheap tiers means the sink is too
shallow"). This drop externalizes the 8 costs to data/tunables.yaml under
``title.cost_<key>`` and reads them at the USE SITE (catalog_lines +
purchase_title), closing the observe→tune loop.

This suite proves: the YAML is purely additive (defaults when a key is absent,
behaviour-identical), an override flows through BOTH the catalog affordability
mark/displayed cost AND the actual buy debit, a fat-fingered negative clamps to 0
(a free tier, never a credit-paying "sink"), a float truncates to int, a
present-but-null / corrupt value can't crash a `+title` buy, and the shipped
data/tunables.yaml carries all 8 keys at their in-code defaults (a drift pin).

Run: python -m pytest tests/test_vanity_title_cost_tunables.py
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

from engine import titles  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402

REPO = PROJECT_ROOT


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _StubDB:
    """Recording stub mirroring tests/test_vanity_titles.py: captures the debit
    amount so the resolved (possibly operator-edited) cost is observable."""

    def __init__(self):
        self.credit_log = []   # (delta, source)
        self.saves = []

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        self.credit_log.append((delta, source))
        return 1_000_000 + delta

    async def save_character(self, cid, **fields):
        self.saves.append(fields)


def _char(credits=1_000_000, owned=None, worn=""):
    return {"id": 7, "credits": credits,
            "vanity_titles": json.dumps(owned or []),
            "display_title": worn}


class TitleCostTunableAccessor(unittest.TestCase):
    """The use-site accessor: default fallback, override, clamp, null, corrupt."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_defaults_when_unset(self):
        # No tunable loaded → every tier resolves to its in-code VANITY_TITLES cost.
        for t in titles.VANITY_TITLES:
            self.assertEqual(titles.title_cost(t["key"], t["cost"]), t["cost"])

    def test_override_takes_effect(self):
        tunables._TUNABLES["title.cost_wayfarer"] = 750
        self.assertEqual(titles.title_cost("wayfarer", 2_000), 750)

    def test_negative_clamps_to_zero(self):
        # A negative would PAY the buyer to take a sink — clamp to a free tier.
        tunables._TUNABLES["title.cost_luminary"] = -5
        self.assertEqual(titles.title_cost("luminary", 400_000), 0)

    def test_float_truncates_to_int(self):
        tunables._TUNABLES["title.cost_magnate"] = 59_999.9
        self.assertEqual(titles.title_cost("magnate", 60_000), 59_999)

    def test_present_but_null_falls_back_to_default(self):
        # Operator typo `title.cost_wayfarer:` (no value) → get_tunable coerces None.
        tunables._TUNABLES["title.cost_wayfarer"] = None
        self.assertEqual(titles.title_cost("wayfarer", 2_000), 2_000)

    def test_corrupt_value_falls_back_to_default(self):
        # A non-numeric YAML value can't crash the catalog render or a buy.
        tunables._TUNABLES["title.cost_socialite"] = "lots"
        self.assertEqual(titles.title_cost("socialite", 25_000), 25_000)


class TitleCostCatalogEndToEnd(unittest.TestCase):
    """The override flows through catalog_lines: affordability mark + shown cost."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def _row(self, rows, key):
        return next(r for r in rows if r["key"] == key)

    def test_default_catalog_shows_in_code_costs(self):
        rows = titles.catalog_lines(_char(credits=3_000))
        self.assertEqual(self._row(rows, "wayfarer")["cost"], 2_000)
        self.assertEqual(self._row(rows, "wayfarer")["mark"], "buy")        # 3000 >= 2000
        self.assertEqual(self._row(rows, "dealmaker")["mark"], "locked")    # 3000 < 5000

    def test_repriced_tier_changes_displayed_cost_and_affordability(self):
        # Drop the Dealmaker to 1000 → a 3000-credit char can now afford it,
        # and the catalog renders the repriced figure (not the stale 5000).
        tunables._TUNABLES["title.cost_dealmaker"] = 1_000
        rows = titles.catalog_lines(_char(credits=3_000))
        self.assertEqual(self._row(rows, "dealmaker")["cost"], 1_000)
        self.assertEqual(self._row(rows, "dealmaker")["mark"], "buy")

    def test_priced_out_of_reach_locks_a_formerly_affordable_tier(self):
        tunables._TUNABLES["title.cost_wayfarer"] = 9_999
        rows = titles.catalog_lines(_char(credits=3_000))
        self.assertEqual(self._row(rows, "wayfarer")["cost"], 9_999)
        self.assertEqual(self._row(rows, "wayfarer")["mark"], "locked")


class TitleCostBuyEndToEnd(unittest.TestCase):
    """The override flows through the actual purchase_title debit — the sink leg."""

    def setUp(self):
        tunables.reset_tunables()
        telemetry.reset()

    def tearDown(self):
        tunables.reset_tunables()
        telemetry.reset()

    def test_default_buy_debits_in_code_cost(self):
        db = _StubDB()
        res = _run(titles.purchase_title(db, _char(), "wayfarer"))
        self.assertTrue(res["ok"])
        self.assertEqual(db.credit_log, [(-2_000, "vanity_title")])

    def test_repriced_buy_debits_the_tunable_amount(self):
        tunables._TUNABLES["title.cost_wayfarer"] = 750
        db = _StubDB()
        res = _run(titles.purchase_title(db, _char(), "wayfarer"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["cost"], 750)
        self.assertEqual(db.credit_log, [(-750, "vanity_title")])

    def test_priced_out_blocks_the_buy_with_resolved_short(self):
        # Raise the Wayfarer above the buyer's balance → insufficient, no debit.
        tunables._TUNABLES["title.cost_wayfarer"] = 5_000
        db = _StubDB()
        res = _run(titles.purchase_title(db, _char(credits=1_000), "wayfarer"))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "insufficient")
        self.assertEqual(res["cost"], 5_000)
        self.assertEqual(res["short"], 4_000)
        self.assertEqual(db.credit_log, [])   # no credits moved on a blocked buy


class TitleCostTunableShipped(unittest.TestCase):
    """Drift pins: the shipped YAML carries all 8 keys at in-code defaults."""

    def setUp(self):
        tunables.reset_tunables()

    def tearDown(self):
        tunables.reset_tunables()

    def test_yaml_ships_every_tier_at_its_in_code_cost(self):
        tunables.load_tunables(str(REPO / "data" / "tunables.yaml"))
        for t in titles.VANITY_TITLES:
            self.assertEqual(
                tunables.get_tunable(f"title.cost_{t['key']}", -1), t["cost"],
                f"tunables.yaml title.cost_{t['key']} drifted from VANITY_TITLES",
            )

    def test_every_tier_key_documented_in_yaml(self):
        ty = (REPO / "data" / "tunables.yaml").read_text(encoding="utf-8")
        for t in titles.VANITY_TITLES:
            self.assertIn(f"title.cost_{t['key']}:", ty)

    def test_accessor_reads_at_use_site(self):
        # Guard the use-site contract: both consumers route through title_cost
        # (read via get_tunable on reload), not the frozen-at-import literal.
        src = (REPO / "engine" / "titles.py").read_text(encoding="utf-8")
        self.assertIn('get_tunable(f"title.cost_{key}"', src)
        # catalog_lines + purchase_title both resolve through the accessor.
        self.assertEqual(src.count('title_cost(t["key"], t["cost"])'), 2)


if __name__ == "__main__":
    unittest.main()
