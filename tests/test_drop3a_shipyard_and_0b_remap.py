# -*- coding: utf-8 -*-
"""
tests/test_drop3a_shipyard_and_0b_remap.py — Drop 0b + ledger-completion + 3a.

One consolidated economic drop (the hard-ordering rule's faucet+measure+sink in
one delivery):

  * **0b** — ``engine/trading.py::TRADE_GOODS`` re-mapped off the deleted GCW
    worlds (Kessel/Corellia) onto the six Clone Wars launch worlds (Economy
    Audit Appendix C). Asserted: no dead planets, all six worlds reachable, the
    web is connected (every world both a source and a demand).
  * **Ledger completion (Drop 1 / F1)** — the two credit-write bypasses found at
    HEAD (``harvest.py`` faucet, ``shop_commands.py`` vendor-upgrade sink) now
    route through ``adjust_credits``. The tree-wide structural pin (mirroring
    ``test_drop1b3_ledger_migration_complete``) is re-asserted here so this drop
    cannot regress it.
  * **3a** — ``parser/shipyard_commands.py``: the Kuat civilian ship brokerage,
    the audit's load-bearing high-tier capital sink. Catalog, fuzzy hull
    matching, and the full purchase core (debit→instantiate→deliver, with all
    rejection paths and the refund-on-failure guarantee).
"""

import os
import re
import sys
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import trading                       # noqa: E402
from parser import shipyard_commands as SY        # noqa: E402

CW_WORLDS = {"coruscant", "kuat", "kamino", "geonosis", "tatooine", "nar_shaddaa"}
DEAD_WORLDS = {"kessel", "corellia"}


def _run(coro):
    """Run a coroutine on a fresh event loop (no deprecation churn)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# 0b — trade re-map
# ─────────────────────────────────────────────────────────────────────────────
class TestTradeRemap0b(unittest.TestCase):
    def test_no_dead_worlds_in_trade_goods(self):
        for key, good in trading.TRADE_GOODS.items():
            for p in list(good.source) + list(good.demand):
                self.assertNotIn(
                    p, DEAD_WORLDS,
                    f"{key} still references deleted world {p!r}")

    def test_all_planets_are_cw_worlds(self):
        for key, good in trading.TRADE_GOODS.items():
            for p in list(good.source) + list(good.demand):
                self.assertIn(
                    p, CW_WORLDS,
                    f"{key} references non-CW world {p!r}")

    def test_web_is_connected(self):
        """Every CW world must be both a source and a demand of *something* —
        otherwise the cargo economy funnels onto a thin route again."""
        src = {w: [] for w in CW_WORLDS}
        dem = {w: [] for w in CW_WORLDS}
        for key, good in trading.TRADE_GOODS.items():
            for p in good.source:
                src[p].append(key)
            for p in good.demand:
                dem[p].append(key)
        for w in CW_WORLDS:
            self.assertTrue(src[w], f"{w} is a source of nothing")
            self.assertTrue(dem[w], f"{w} is a demand of nothing")

    def test_appendix_c_spot_checks(self):
        g = trading.TRADE_GOODS
        self.assertEqual(set(g["raw_ore"].source), {"tatooine", "geonosis"})
        self.assertEqual(set(g["raw_ore"].demand), {"kuat", "coruscant"})
        self.assertEqual(set(g["manufactured_parts"].source), {"kuat"})
        self.assertEqual(set(g["medical_supplies"].source), {"kamino"})
        self.assertEqual(set(g["spice_legal"].source), {"nar_shaddaa"})
        self.assertEqual(set(g["spice_legal"].demand), {"coruscant"})

    def test_pricing_spread_unchanged(self):
        # 0b is a map change only; the 70/140 spread must be intact.
        self.assertAlmostEqual(trading.PRICE_SOURCE, 0.70)
        self.assertAlmostEqual(trading.PRICE_DEMAND, 1.40)


# ─────────────────────────────────────────────────────────────────────────────
# Ledger completion (Drop 1 / F1) — structural pin re-assert
# ─────────────────────────────────────────────────────────────────────────────
class TestLedgerBypassesClosed(unittest.TestCase):
    _CREDIT_SAVE_RE = re.compile(r"save_character\([^)]*credits")

    def _iter_py(self, rel_dir):
        base = os.path.join(PROJECT_ROOT, rel_dir)
        for root, _dirs, files in os.walk(base):
            if "__pycache__" in root:
                continue
            for fn in files:
                if fn.endswith(".py"):
                    yield os.path.join(root, fn)

    def test_no_credit_writing_save_character_anywhere(self):
        """Tree-wide: every credit movement goes through adjust_credits."""
        offenders = []
        for rel_dir in ("engine", "parser"):
            for path in self._iter_py(rel_dir):
                with open(path, "r", encoding="utf-8") as f:
                    for i, line in enumerate(f, 1):
                        if self._CREDIT_SAVE_RE.search(line) and "`" not in line:
                            offenders.append(
                                f"{os.path.relpath(path, PROJECT_ROOT)}:{i}: {line.strip()}")
        self.assertEqual(offenders, [], "save_character(credits=...) bypass(es) found:\n  "
                         + "\n  ".join(offenders))

    def test_harvest_routes_through_ledger(self):
        src = open(os.path.join(PROJECT_ROOT, "engine", "harvest.py"),
                   encoding="utf-8").read()
        self.assertIn('adjust_credits(', src)
        self.assertIn('"harvest"', src)

    def test_vendor_upgrade_routes_through_ledger(self):
        src = open(os.path.join(PROJECT_ROOT, "parser", "shop_commands.py"),
                   encoding="utf-8").read()
        self.assertIn('"vendor_droid_upgrade"', src)


# ─────────────────────────────────────────────────────────────────────────────
# 3a — Kuat ship brokerage
# ─────────────────────────────────────────────────────────────────────────────
_FORBIDDEN_HULL_TOKENS = ("x_wing", "y_wing", "a_wing", "b_wing", "tie",
                          "nebulon", "star_destroyer", "imperial")


class TestShipyardCatalog(unittest.TestCase):
    def test_catalog_shape_and_order(self):
        cat = SY.build_catalog()
        keys = [c["key"] for c in cat]
        self.assertEqual(
            keys,
            ["z_95", "ghtroc_720", "yt_1300", "firespray", "yt_2400",
             "consular_cruiser"])
        # Ordered cheap → whale, all priced.
        costs = [c["cost"] for c in cat]
        self.assertTrue(all(x > 0 for x in costs))
        self.assertEqual(costs, sorted(costs))
        self.assertEqual(cat[-1]["key"], "consular_cruiser")
        self.assertEqual(cat[-1]["cost"], 1_500_000)

    def test_catalog_is_era_clean(self):
        for c in SY.build_catalog():
            blob = (c["key"] + " " + c["name"]).lower()
            for bad in _FORBIDDEN_HULL_TOKENS:
                self.assertNotIn(bad, blob,
                                 f"off-era hull {c['key']!r} on the civilian market")

    def test_prices_single_sourced_from_registry(self):
        from engine.starships import get_ship_registry
        reg = get_ship_registry()
        for c in SY.build_catalog():
            self.assertEqual(c["cost"], int(reg.get(c["key"]).cost))

    def test_match_hull(self):
        cat = SY.build_catalog()
        cases = {
            "yt1300": "yt_1300", "YT-1300": "yt_1300",
            "ghtroc": "ghtroc_720", "consular": "consular_cruiser",
            "z95": "z_95", "firespray": "firespray",
            "stardestroyer": None, "": None,
        }
        for tok, exp in cases.items():
            m = SY._match_hull(tok, cat)
            self.assertEqual(m["key"] if m else None, exp, f"match({tok!r})")


class _StubDB:
    """Minimal async DB stub exercising purchase_ship's call surface."""
    BROKER = {"kuat_deporin_shipyards": 1, "kuat_ileu_shipyards": 2,
              "kuat_ring_commercial": 3}
    DOCK = {"kuat_city_landing_pad": 50, "kuat_shuttle_bay": 51,
            "kuat_arrivals": 52}

    def __init__(self, bal=200000, owned=0, fail_ship=False, dock=True):
        self.bal = bal
        self.log = []          # (delta, source)
        self.ships = []        # (template, name, owner, bridge, dock)
        self.owned = owned
        self.fail_ship = fail_ship
        self.dock = dock
        self._rid = 1000
        self._sid = 0

    async def get_room_by_slug(self, slug):
        if slug in self.BROKER:
            return {"id": self.BROKER[slug]}
        if self.dock and slug in self.DOCK:
            return {"id": self.DOCK[slug]}
        return None

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        if not allow_negative and self.bal + delta < 0:
            return None
        self.bal += delta
        self.log.append((delta, source))
        return self.bal

    async def get_ships_owned_by(self, oid):
        return [{}] * self.owned

    async def create_room(self, *a):
        self._rid += 1
        return self._rid

    async def create_ship(self, template, name, owner, bridge, dock):
        if self.fail_ship:
            raise RuntimeError("boom")
        self._sid += 1
        self.ships.append((template, name, owner, bridge, dock))
        return self._sid

    async def get_ship(self, sid):
        return {"systems": "{}"}

    async def update_ship(self, sid, **kw):
        pass

    async def create_exit(self, *a, **k):
        pass

    async def get_room(self, rid):
        return {"name": "Kuat City - Landing Pad"}

    async def execute(self, *a):
        pass

    async def commit(self):
        pass


class TestShipyardPurchase(unittest.TestCase):
    def test_happy_path_sinks_credits_and_creates_ship(self):
        db = _StubDB(bal=200000)
        char = {"id": 7, "credits": 200000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "yt1300"))
        self.assertTrue(res["ok"], res["message"])
        # Exact price sunk, tagged ship_purchase, balance updated.
        self.assertEqual(db.log, [(-100000, "ship_purchase")])
        self.assertEqual(char["credits"], 100000)
        # Ship created: right template, owner, delivered to the landing pad.
        self.assertEqual(len(db.ships), 1)
        tmpl, name, owner, bridge, dock = db.ships[0]
        self.assertEqual(tmpl, "yt_1300")
        self.assertEqual(owner, 7)
        self.assertEqual(dock, 50)

    def test_custom_name(self):
        db = _StubDB(bal=200000)
        char = {"id": 7, "credits": 200000, "room_id": 2}
        res = _run(SY.purchase_ship(db, char, 2, "ghtroc", "Lucky Strike"))
        self.assertTrue(res["ok"])
        self.assertEqual(db.ships[0][1], "Lucky Strike")

    def test_rejected_when_not_at_broker(self):
        db = _StubDB()
        char = {"id": 7, "credits": 200000, "room_id": 99}
        res = _run(SY.purchase_ship(db, char, 99, "yt1300"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.log, [], "must not charge when not at a broker")
        self.assertEqual(db.ships, [])

    def test_rejected_insufficient_credits(self):
        db = _StubDB(bal=5000)
        char = {"id": 7, "credits": 5000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "consular"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.log, [])

    def test_rejected_unknown_hull(self):
        db = _StubDB()
        char = {"id": 7, "credits": 200000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "stardestroyer"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.log, [])

    def test_ownership_cap_enforced(self):
        db = _StubDB(owned=SY.MAX_OWNED_SHIPS)
        char = {"id": 7, "credits": 2_000_000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "consular"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.log, [])

    def test_refund_on_ship_insert_failure(self):
        db = _StubDB(bal=200000, fail_ship=True)
        char = {"id": 7, "credits": 200000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "yt1300"))
        self.assertFalse(res["ok"])
        # Debited then fully refunded — net zero, no orphaned charge.
        self.assertEqual(
            db.log,
            [(-100000, "ship_purchase"), (100000, "ship_purchase_refund")])
        self.assertEqual(char["credits"], 200000)

    def test_no_delivery_dock_refunds(self):
        # If no Kuat pad exists, we must not charge.
        db = _StubDB(bal=200000, dock=False)
        char = {"id": 7, "credits": 200000, "room_id": 1}
        res = _run(SY.purchase_ship(db, char, 1, "yt1300"))
        self.assertFalse(res["ok"])
        self.assertEqual(db.log, [], "no dock → no charge")


if __name__ == "__main__":
    unittest.main()
