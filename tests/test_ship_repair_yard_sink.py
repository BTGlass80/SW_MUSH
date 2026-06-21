# -*- coding: utf-8 -*-
"""
tests/test_ship_repair_yard_sink.py — the spacedock yard-repair sink (F2).

Closes the single largest gap in the sink architecture
(``SW_MUSH_Economy_Audit_FINAL.md`` F2/R2/B5; ``economy_audit_v2.md`` §1.3
priority #3): ship repair was free, so the rich had no high-tier drain. The new
``+spacedock repair`` does what ``damcon`` cannot — restore DESTROYED systems —
and fully restores hull, for a fee that is a fraction of hull value routed
through the ledger as ``ship_repair``.

Covers:
  * the pure pricing model (``quote_yard_repair``) and the restore step
    (``apply_yard_repair``) — math, boundaries, design invariants;
  * the ``SpacedockCommand`` behaviour end-to-end against a recording stub DB
    (docked gate, quote, debit==quote, restore, insufficient funds, refund);
  * structural pins: the ``ship_repair`` tag, debit-precedes-write ordering,
    a refund path, and the protected invariant that **damcon stays free**.
"""

import os
import re
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.ship_repair import (                                    # noqa: E402
    quote_yard_repair, apply_yard_repair, SYSTEM_KEYS,
    YARD_DESTROYED_PCT, YARD_DAMAGED_PCT, YARD_HULL_PCT, YARD_MIN_FEE,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure pricing model
# ─────────────────────────────────────────────────────────────────────────────
class TestQuotePricing(unittest.TestCase):
    COST = 100_000  # round hull value so percentages read cleanly

    def test_pristine_costs_nothing(self):
        q = quote_yard_repair(self.COST, {}, hull_damage=0, hull_max=12)
        self.assertFalse(q["needs_repair"])
        self.assertEqual(q["cost"], 0)
        self.assertEqual(q["destroyed"], [])
        self.assertEqual(q["damaged"], [])

    def test_destroyed_system_is_the_dominant_fee(self):
        q = quote_yard_repair(self.COST, {"engines": "destroyed"},
                              hull_damage=0, hull_max=12)
        self.assertEqual(q["destroyed"], ["engines"])
        self.assertEqual(q["cost"], int(self.COST * YARD_DESTROYED_PCT))  # 6,000

    def test_damaged_system_is_modest(self):
        q = quote_yard_repair(self.COST, {"shields": "damaged"},
                              hull_damage=0, hull_max=12)
        self.assertEqual(q["damaged"], ["shields"])
        self.assertEqual(q["cost"], int(self.COST * YARD_DAMAGED_PCT))    # 1,000

    def test_hull_fee_scales_with_damage_fraction(self):
        # Half-wrecked hull → 3% × 0.5 = 1.5% = 1,500
        q = quote_yard_repair(self.COST, {}, hull_damage=6, hull_max=12)
        self.assertEqual(q["cost"], int(round(self.COST * YARD_HULL_PCT * 0.5)))

    def test_fees_compose_additively(self):
        systems = {"engines": "destroyed", "shields": "damaged"}
        q = quote_yard_repair(self.COST, systems, hull_damage=6, hull_max=12)
        expected = int(round(
            (YARD_DESTROYED_PCT + YARD_DAMAGED_PCT + YARD_HULL_PCT * 0.5) * self.COST
        ))
        self.assertEqual(q["cost"], expected)

    def test_destroyed_costs_more_than_damaged(self):
        """Design invariant: the yard's value is fixing what damcon can't."""
        d = quote_yard_repair(self.COST, {"engines": "destroyed"}, 0, 12)["cost"]
        m = quote_yard_repair(self.COST, {"engines": "damaged"}, 0, 12)["cost"]
        self.assertGreater(d, m)

    def test_min_fee_floor(self):
        # Tiny job on a cheap hull floors at YARD_MIN_FEE.
        q = quote_yard_repair(1_000, {"shields": "damaged"}, 0, 12)  # raw = 10
        self.assertEqual(q["cost"], YARD_MIN_FEE)

    def test_needs_repair_with_zero_value_hull_still_floors(self):
        q = quote_yard_repair(0, {"engines": "destroyed"}, 0, 12)
        self.assertTrue(q["needs_repair"])
        self.assertEqual(q["cost"], YARD_MIN_FEE)

    def test_hull_overdamage_fraction_capped(self):
        """A 'destroyed' hull (damage > max) must not bill past full hull %."""
        capped = quote_yard_repair(self.COST, {}, hull_damage=999, hull_max=12)["cost"]
        full = quote_yard_repair(self.COST, {}, hull_damage=12, hull_max=12)["cost"]
        self.assertEqual(capped, full)
        self.assertEqual(full, int(round(self.COST * YARD_HULL_PCT)))

    def test_zero_hull_max_is_safe(self):
        q = quote_yard_repair(self.COST, {}, hull_damage=5, hull_max=0)
        self.assertTrue(q["needs_repair"])      # hull_damage>0 still flags it
        self.assertEqual(q["cost"], YARD_MIN_FEE)  # floors (never a free patch)

    def test_whale_class_repair_actually_bites(self):
        """The audit's whole point: a 1.5M cruiser's destroyed system must drain
        a meaningful sum, not a rounding error."""
        q = quote_yard_repair(1_500_000, {"hyperdrive": "destroyed"}, 0, 12)
        self.assertEqual(q["cost"], 90_000)  # 6% of 1.5M

    def test_hull_is_not_a_per_system_fee(self):
        """'hull' must not appear in SYSTEM_KEYS — it is billed via the fraction,
        not as a destroyed/damaged system (it lives in a separate column)."""
        self.assertNotIn("hull", SYSTEM_KEYS)


class TestApplyRepair(unittest.TestCase):
    def test_restores_every_nonhull_system(self):
        systems = {"engines": "destroyed", "shields": "damaged",
                   "sensors": True, "weapons": False}
        new = apply_yard_repair(systems)
        for s in ("engines", "shields", "sensors", "weapons"):
            self.assertTrue(new[s] is True or new[s] == "working",
                            f"{s} not restored")

    def test_does_not_mutate_input(self):
        systems = {"engines": "destroyed"}
        _ = apply_yard_repair(systems)
        self.assertEqual(systems, {"engines": "destroyed"},
                         "apply_yard_repair must not mutate its argument")

    def test_does_not_invent_a_hull_key(self):
        new = apply_yard_repair({"engines": "destroyed"})
        self.assertNotIn("hull", new)


# ─────────────────────────────────────────────────────────────────────────────
# SpacedockCommand integration (recording stub DB + minimal ctx)
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    """Records adjust_credits/update_ship; serves one ship by bridge room."""

    def __init__(self, ship, bal=500_000, fail_update=False):
        self._ship = ship
        self.bal = bal
        self.fail_update = fail_update
        self.credit_log = []   # (delta, source)
        self.ship_updates = []  # dict of fields

    async def get_ship_by_bridge(self, room_id):
        return self._ship if room_id == self._ship.get("bridge_room_id") else None

    async def adjust_credits(self, cid, delta, source, *, allow_negative=True):
        if not allow_negative and self.bal + delta < 0:
            return None
        self.bal += delta
        self.credit_log.append((delta, source))
        return self.bal

    async def update_ship(self, sid, **fields):
        if self.fail_update:
            raise RuntimeError("yard write boom")
        self.ship_updates.append(fields)


class _StubSession:
    def __init__(self, character):
        self.character = character
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)


class _StubMgr:
    async def broadcast_to_room(self, *a, **k):
        pass


class _Ctx:
    def __init__(self, db, session, args=""):
        self.db = db
        self.session = session
        self.session_mgr = _StubMgr()
        self.args = args


def _make_ship(template_key="yt_1300", *, systems=None, hull_damage=0, docked=True):
    return {
        "id": 7,
        "template": template_key,
        "bridge_room_id": 999,
        "name": "Test Hull",
        "systems": json.dumps(systems or {}),
        "hull_damage": hull_damage,
        "docked_at": 500 if docked else None,
    }


def _expected_quote(ship):
    """Recompute the quote exactly as the command will, so assertions track the
    real hull's cost/dice and survive tuning-constant changes."""
    from engine.starships import get_ship_registry, get_effective_stats
    from engine.dice import DicePool
    reg = get_ship_registry()
    tmpl = reg.get(ship["template"])
    systems = json.loads(ship["systems"])
    eff = get_effective_stats(tmpl, systems)
    hull_pool = DicePool.parse(eff["hull"]) if eff else DicePool.parse(tmpl.hull)
    hull_max = hull_pool.total_pips()
    return quote_yard_repair(tmpl.cost, systems, ship["hull_damage"], hull_max)


class TestSpacedockCommand(unittest.TestCase):
    def setUp(self):
        from parser.space_commands import SpacedockCommand
        self.cmd = SpacedockCommand()

    def _ctx(self, ship, *, args="", bal=500_000, fail_update=False):
        db = _StubDB(ship, bal=bal, fail_update=fail_update)
        char = {"id": 1, "room_id": ship["bridge_room_id"], "credits": bal}
        sess = _StubSession(char)
        return _Ctx(db, sess, args=args), db, char, sess

    def test_in_flight_refuses_and_does_not_charge(self):
        ship = _make_ship(systems={"engines": "destroyed"}, docked=False)
        ctx, db, char, sess = self._ctx(ship)
        _run(self.cmd.execute(ctx))
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.ship_updates, [])
        self.assertTrue(any("docked" in l.lower() for l in sess.lines))

    def test_quote_only_does_not_charge(self):
        ship = _make_ship(systems={"engines": "destroyed"}, hull_damage=4)
        ctx, db, char, sess = self._ctx(ship, args="")  # no sub-command
        _run(self.cmd.execute(ctx))
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.ship_updates, [])
        q = _expected_quote(ship)
        self.assertTrue(any(f"{q['cost']:,}" in l for l in sess.lines),
                        "quote should display the full-restoration cost")

    def test_repair_debits_exactly_the_quote_via_ship_repair(self):
        ship = _make_ship(systems={"engines": "destroyed", "shields": "damaged"},
                          hull_damage=4)
        q = _expected_quote(ship)
        ctx, db, char, sess = self._ctx(ship, args="repair")
        _run(self.cmd.execute(ctx))
        # exactly one debit, tagged ship_repair, equal to the quoted cost
        self.assertEqual(len(db.credit_log), 1)
        delta, source = db.credit_log[0]
        self.assertEqual(source, "ship_repair")
        self.assertEqual(delta, -q["cost"])

    def test_repair_restores_systems_and_hull(self):
        ship = _make_ship(systems={"engines": "destroyed", "shields": "damaged"},
                          hull_damage=4)
        ctx, db, char, sess = self._ctx(ship, args="repair")
        _run(self.cmd.execute(ctx))
        self.assertEqual(len(db.ship_updates), 1)
        fields = db.ship_updates[0]
        self.assertEqual(fields["hull_damage"], 0)
        restored = json.loads(fields["systems"])
        self.assertTrue(restored["engines"] is True)
        self.assertTrue(restored["shields"] is True)

    def test_insufficient_funds_does_not_charge_or_repair(self):
        ship = _make_ship(systems={"hyperdrive": "destroyed"}, hull_damage=2)
        q = _expected_quote(ship)
        ctx, db, char, sess = self._ctx(ship, args="repair", bal=q["cost"] - 1)
        _run(self.cmd.execute(ctx))
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.ship_updates, [])
        self.assertTrue(any("short" in l.lower() for l in sess.lines))

    def test_nothing_to_repair_does_not_charge(self):
        ship = _make_ship(systems={"engines": True}, hull_damage=0)
        ctx, db, char, sess = self._ctx(ship, args="repair")
        _run(self.cmd.execute(ctx))
        self.assertEqual(db.credit_log, [])
        self.assertEqual(db.ship_updates, [])

    def test_failed_yard_write_refunds_net_zero(self):
        ship = _make_ship(systems={"engines": "destroyed"}, hull_damage=4)
        ctx, db, char, sess = self._ctx(ship, args="repair", fail_update=True)
        start = db.bal
        _run(self.cmd.execute(ctx))
        # a debit then a refund — net zero balance, ship untouched
        self.assertEqual(db.bal, start)
        sources = [s for _, s in db.credit_log]
        self.assertIn("ship_repair", sources)
        self.assertIn("ship_repair_refund", sources)
        self.assertEqual(db.ship_updates, [])  # never persisted


# ─────────────────────────────────────────────────────────────────────────────
# Structural pins (source-level) — mirror the npc_buyback discipline
# ─────────────────────────────────────────────────────────────────────────────
class TestStructuralPins(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(PROJECT_ROOT, "parser", "space_commands.py"),
                  encoding="utf-8") as fh:
            cls.src = fh.read()
        # isolate the two commands
        sd = cls.src.index("class SpacedockCommand")
        nxt = cls.src.index("class PayCommand", sd)
        cls.spacedock_src = cls.src[sd:nxt]
        dc = cls.src.index("class DamConCommand")
        dc_end = cls.src.index("class SpacedockCommand", dc)
        cls.damcon_src = cls.src[dc:dc_end]

    def test_spacedock_uses_ship_repair_tag(self):
        self.assertIn('"ship_repair"', self.spacedock_src)

    def test_debit_precedes_ship_write(self):
        # QA 2026-06-21: the debit now carries allow_negative=False (multi-line);
        # pin the guarded form and that it still precedes the ship write.
        debit = self.spacedock_src.index('-cost, "ship_repair", allow_negative=False')
        write = self.spacedock_src.index("update_ship(")
        self.assertLess(debit, write,
                        "the ledger debit must precede the ship write (refund-safe order)")

    def test_refund_path_exists(self):
        self.assertIn("ship_repair_refund", self.spacedock_src)

    def test_command_is_registered(self):
        # appears in the top-level registry list and the bridge-switch dict
        self.assertGreaterEqual(self.src.count("SpacedockCommand()"), 2)

    def test_damcon_stays_free(self):
        """Protected invariant (Integrated report B5 / v2 §1.3): the in-combat
        field-repair must NOT charge credits — only the spacedock does."""
        self.assertNotIn("adjust_credits", self.damcon_src,
                         "damcon must remain a free skill check — no credit cost")


if __name__ == "__main__":
    unittest.main(verbosity=2)
