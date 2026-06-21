# -*- coding: utf-8 -*-
"""tests/test_t319_influence_telemetry.py — T3.19 telemetry breadth.

Instruments ``engine.territory.adjust_territory_influence`` — one of the three
mandatory funnel functions and the SINGLE chokepoint for all territory-control
movement. One ``influence`` telemetry event is emitted here per real change
(``delta != 0``), the influence analog of how ``credit_flow`` rides
``db.log_credit``. The offline funnel can then answer the post-launch balance
question Brian wants: who is contesting/holding which zones, and what drives it.

The contract under test (Brian, telemetry_purpose_clarified): the emit is
buffer-only (non-blocking), fail-open (NEVER disturbs the influence path it
observes), and the keep-rate is a use-site tunable (``telemetry.influence_sample``).
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── minimal Database-API surface (territory_influence only) ────────────────
class _MiniDB:
    """Just enough of the Database API for adjust_territory_influence:
    fetchall / execute / commit over an in-memory territory_influence table."""

    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE territory_influence (
                zone_id       INTEGER NOT NULL,
                org_code      TEXT    NOT NULL,
                score         INTEGER NOT NULL DEFAULT 0,
                last_activity REAL    NOT NULL DEFAULT 0,
                last_presence REAL    NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
            );
            """
        )
        self._conn.commit()

    async def fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)

    async def commit(self):
        self._conn.commit()

    def seed_influence(self, *, zone_id, org_code, score):
        now = time.time()
        self._conn.execute(
            "INSERT INTO territory_influence "
            "(zone_id, org_code, score, last_activity, last_presence) "
            "VALUES (?, ?, ?, ?, ?)",
            (zone_id, org_code, score, now, now),
        )
        self._conn.commit()

    def read_score(self, *, zone_id, org_code):
        cur = self._conn.execute(
            "SELECT score FROM territory_influence "
            "WHERE zone_id = ? AND org_code = ?",
            (zone_id, org_code),
        )
        row = cur.fetchone()
        return row["score"] if row else 0


class _InfluenceTelemetryCase(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        self._tmp = tempfile.TemporaryDirectory()
        telemetry.reset()
        telemetry.configure(path=os.path.join(self._tmp.name, "e.jsonl"),
                            enabled=True)
        self.db = _MiniDB()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()
        self._tmp.cleanup()

    def _influence_events(self):
        from engine import telemetry
        recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
        return [r for r in recs if r["ev"] == "influence"]

    def _adjust(self, **kw):
        from engine.territory import adjust_territory_influence
        return _run(adjust_territory_influence(self.db, **kw))

    # ── core: one event per real change ───────────────────────────────────
    def test_positive_delta_emits_one_event_with_full_payload(self):
        new = self._adjust(org_code="republic", zone_id=5, delta=10,
                           reason="mission_complete")
        self.assertEqual(new, 10)
        evs = self._influence_events()
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["org"], "republic")
        self.assertEqual(e["zone_id"], 5)
        self.assertEqual(e["delta"], 10)
        self.assertEqual(e["score"], 10)
        self.assertEqual(e["prev"], 0)
        self.assertFalse(e["clamped"])
        self.assertEqual(e["reason"], "mission_complete")
        self.assertEqual(e["region"], "")

    def test_negative_delta_emits_and_reports_prev(self):
        self.db.seed_influence(zone_id=5, org_code="cis", score=40)
        new = self._adjust(org_code="cis", zone_id=5, delta=-15,
                           reason="espionage")
        self.assertEqual(new, 25)
        evs = self._influence_events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["delta"], -15)
        self.assertEqual(evs[0]["prev"], 40)
        self.assertEqual(evs[0]["score"], 25)
        self.assertFalse(evs[0]["clamped"])

    def test_zero_delta_emits_nothing(self):
        # A no-op influence call must not pollute the funnel.
        new = self._adjust(org_code="republic", zone_id=5, delta=0,
                           reason="touch")
        self.assertEqual(new, 0)
        self.assertEqual(self._influence_events(), [])

    # ── clamp flag: floor + ceiling ───────────────────────────────────────
    def test_clamp_at_cap_flagged(self):
        from engine.territory import INFLUENCE_CAP
        self.db.seed_influence(zone_id=5, org_code="republic",
                               score=INFLUENCE_CAP - 5)
        new = self._adjust(org_code="republic", zone_id=5, delta=20,
                           reason="harvest")
        self.assertEqual(new, INFLUENCE_CAP)
        evs = self._influence_events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["clamped"])
        self.assertEqual(evs[0]["score"], INFLUENCE_CAP)

    def test_clamp_at_floor_flagged(self):
        self.db.seed_influence(zone_id=5, org_code="cis", score=5)
        new = self._adjust(org_code="cis", zone_id=5, delta=-20,
                           reason="raid")
        self.assertEqual(new, 0)
        evs = self._influence_events()
        self.assertEqual(len(evs), 1)
        self.assertTrue(evs[0]["clamped"])
        self.assertEqual(evs[0]["score"], 0)

    # ── region passthrough (negative delta avoids contest auto-trigger) ────
    def test_region_slug_passthrough(self):
        self.db.seed_influence(zone_id=5, org_code="republic", score=30)
        # delta<0 with region_slug exercises the `region` field WITHOUT
        # firing the delta>0-only contest-multiplier / auto-trigger machinery.
        self._adjust(org_code="republic", zone_id=5, delta=-3,
                     reason="contested", region_slug="dune_sea")
        evs = self._influence_events()
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["region"], "dune_sea")

    # ── keep-rate is wired to the telemetry.influence_sample tunable ───────
    def test_sample_zero_suppresses_emit(self):
        with mock.patch("engine.tunables.get_tunable", return_value=0.0):
            new = self._adjust(org_code="republic", zone_id=5, delta=10,
                               reason="mission")
        # Mutation still happened; telemetry was sampled out.
        self.assertEqual(new, 10)
        self.assertEqual(self.db.read_score(zone_id=5, org_code="republic"), 10)
        self.assertEqual(self._influence_events(), [])

    def test_sample_one_keeps_emit(self):
        with mock.patch("engine.tunables.get_tunable", return_value=1.0):
            self._adjust(org_code="republic", zone_id=5, delta=10,
                         reason="mission")
        self.assertEqual(len(self._influence_events()), 1)

    # ── fail-open: a broken telemetry sink never breaks the influence path ─
    def test_emit_failure_does_not_disturb_influence(self):
        self.db.seed_influence(zone_id=5, org_code="cis", score=10)
        with mock.patch("engine.telemetry.emit",
                        side_effect=RuntimeError("sink exploded")):
            new = self._adjust(org_code="cis", zone_id=5, delta=7,
                               reason="mission")
        # The credit-move-equivalent (influence mutation) MUST still succeed
        # and return the correct score even though the emitter raised.
        self.assertEqual(new, 17)
        self.assertEqual(self.db.read_score(zone_id=5, org_code="cis"), 17)


if __name__ == "__main__":
    unittest.main()
