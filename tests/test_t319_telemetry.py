# -*- coding: utf-8 -*-
"""tests/test_t319_telemetry.py — T3.19 telemetry sink + chokepoint emitters.

Covers the second half of T3.19 (the telemetry instrumentation): an
append-only JSON-line sink (``engine/telemetry.py``) plus emitters wired at
three principled chokepoints so one site each captures an entire metric
category:

  * ``db.log_credit``              → ``credit_flow``  (every faucet + sink, by tag)
  * ``db.cp_add_character_points`` → ``cp_award``     (every CP earn + spend)
  * ``engine.skill_checks.perform_skill_check`` → ``skill_check`` (every OOC roll)

The contract under test (Brian, telemetry_purpose_clarified): emit is
non-blocking (buffer only), fail-open (never disturbs gameplay), bounded
(can't leak memory), and writes happen only on the periodic flush. Tests that
exercise an emitter therefore just fill the buffer — nothing is written to
disk unless the test drives a flush.
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest

import aiosqlite  # noqa: F401  (proves the DB harness deps are present)

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _fresh_db(start_credits: int = 1000, start_cp: int = 10,
                    char_id: int = 1):
    """Real Database on :memory: with the columns the emitters touch."""
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db._db.execute(
        "CREATE TABLE characters (id INTEGER PRIMARY KEY, "
        "credits INTEGER DEFAULT 1000, character_points INTEGER DEFAULT 0)"
    )
    await db._db.execute(
        """CREATE TABLE credit_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            char_id     INTEGER NOT NULL,
            delta       INTEGER NOT NULL,
            source      TEXT NOT NULL,
            balance     INTEGER NOT NULL,
            created_at  REAL NOT NULL
        )"""
    )
    await db._db.execute(
        "INSERT INTO characters (id, credits, character_points) VALUES (?, ?, ?)",
        (char_id, start_credits, start_cp),
    )
    await db._db.commit()
    return db


def _char(attrs=None, char_id=42):
    return {
        "id": char_id,
        "inventory": json.dumps({"items": [], "resources": []}),
        "attributes": json.dumps(attrs or {"perception": "3D"}),
        "skills": "{}",
        "equipment": "{}",
    }


# ══════════════════════════════════════════════════════════════════════════
# 1. The sink (pure, direct instantiation — no singleton)
# ══════════════════════════════════════════════════════════════════════════
class TestTelemetrySink(unittest.TestCase):
    def _sink(self, tmp, **kw):
        from engine.telemetry import TelemetrySink
        kw.setdefault("enabled", True)
        return TelemetrySink(path=os.path.join(tmp, "events.jsonl"), **kw)

    def test_emit_buffers_envelope(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            s.emit("test_event", {"a": 1, "b": "x"})
            lines = s.drain()
            self.assertEqual(len(lines), 1)
            rec = json.loads(lines[0])
            self.assertEqual(rec["ev"], "test_event")
            self.assertIn("ts", rec)
            self.assertEqual(rec["seq"], 1)
            self.assertEqual(rec["a"], 1)
            self.assertEqual(rec["b"], "x")

    def test_envelope_keys_protected(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            s.emit("e", {"ev": "HACK", "seq": 999, "ts": 0, "real": 5})
            rec = json.loads(s.drain()[0])
            self.assertEqual(rec["ev"], "e")        # not overridden
            self.assertEqual(rec["seq"], 1)         # not overridden
            self.assertEqual(rec["real"], 5)

    def test_drain_clears(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            s.emit("e", {})
            self.assertEqual(len(s.drain()), 1)
            self.assertEqual(len(s.drain()), 0)

    def test_flush_writes_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            for i in range(3):
                s.emit("e", {"i": i})
            n = s.flush()
            self.assertEqual(n, 3)
            with open(s.path, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            self.assertEqual([r["i"] for r in rows], [0, 1, 2])
            self.assertEqual(len(s.drain()), 0)  # flush drained the buffer

    def test_flush_appends(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            s.emit("e", {"i": 0}); s.flush()
            s.emit("e", {"i": 1}); s.flush()
            with open(s.path, encoding="utf-8") as fh:
                rows = [json.loads(ln) for ln in fh if ln.strip()]
            self.assertEqual(len(rows), 2)

    def test_flush_empty_is_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            self.assertEqual(s.flush(), 0)
            self.assertFalse(os.path.exists(s.path))

    def test_disabled_buffers_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, enabled=False)
            s.emit("e", {"a": 1})
            self.assertEqual(len(s.drain()), 0)
            self.assertEqual(s.stats()["emitted"], 0)

    def test_empty_event_type_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            s.emit("", {"a": 1})
            self.assertEqual(len(s.drain()), 0)

    def test_sample_zero_drops(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            for _ in range(50):
                s.emit("e", {}, sample=0.0)
            self.assertEqual(len(s.drain()), 0)
            self.assertEqual(s.stats()["sampled_out"], 50)
            self.assertEqual(s.stats()["emitted"], 0)

    def test_sample_one_keeps_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            for _ in range(20):
                s.emit("e", {}, sample=1.0)
            self.assertEqual(len(s.drain()), 20)

    def test_bounded_overflow_drops_oldest(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_buffer=3)
            for _ in range(5):
                s.emit("e", {})
            lines = s.drain()
            self.assertEqual(len(lines), 3)              # capped
            seqs = [json.loads(ln)["seq"] for ln in lines]
            self.assertEqual(seqs, [3, 4, 5])            # oldest (1,2) dropped
            self.assertEqual(s.stats()["dropped_overflow"], 2)

    def test_emit_never_raises_on_bad_field(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            # A non-JSON-serializable value must degrade (default=str), not drop.
            s.emit("e", {"obj": object()})
            lines = s.drain()
            self.assertEqual(len(lines), 1)
            self.assertIn("obj", json.loads(lines[0]))

    def test_write_error_is_failopen(self):
        from engine.telemetry import TelemetrySink
        # An unwritable path must not raise out of flush.
        s = TelemetrySink(path=os.path.join("\x00bad", "x.jsonl"), enabled=True)
        s.emit("e", {})
        self.assertEqual(s.flush(), 0)
        self.assertGreaterEqual(s.stats()["write_errors"], 1)

    def test_stats_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp)
            for k in ("enabled", "path", "buffered", "emitted", "sampled_out",
                      "dropped_overflow", "flushed", "write_errors"):
                self.assertIn(k, s.stats())


class TestFlushAsync(unittest.TestCase):
    def test_flush_async_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            from engine.telemetry import TelemetrySink
            s = TelemetrySink(path=os.path.join(tmp, "e.jsonl"), enabled=True)
            s.emit("e", {"i": 1})
            n = _run(s.flush_async())
            self.assertEqual(n, 1)
            with open(s.path, encoding="utf-8") as fh:
                self.assertEqual(len([1 for ln in fh if ln.strip()]), 1)

    def test_flush_async_empty_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            from engine.telemetry import TelemetrySink
            s = TelemetrySink(path=os.path.join(tmp, "e.jsonl"), enabled=True)
            self.assertEqual(_run(s.flush_async()), 0)


# ══════════════════════════════════════════════════════════════════════════
# 2. Module singleton API
# ══════════════════════════════════════════════════════════════════════════
class TestModuleAPI(unittest.TestCase):
    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_module_emit_through_singleton(self):
        from engine import telemetry
        with tempfile.TemporaryDirectory() as tmp:
            telemetry.reset()
            telemetry.configure(path=os.path.join(tmp, "e.jsonl"), enabled=True)
            telemetry.emit("hello", {"x": 1})
            lines = telemetry.get_sink().drain()
            self.assertEqual(len(lines), 1)
            self.assertEqual(json.loads(lines[0])["ev"], "hello")

    def test_reset_rebuilds_singleton(self):
        from engine import telemetry
        telemetry.reset()
        a = telemetry.get_sink()
        telemetry.reset()
        b = telemetry.get_sink()
        self.assertIsNot(a, b)


# ── shared fixture for the emitter integration tests ──────────────────────
class _EmitterCase(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        self._tmp = tempfile.TemporaryDirectory()
        telemetry.reset()
        telemetry.configure(path=os.path.join(self._tmp.name, "e.jsonl"),
                            enabled=True)

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()
        self._tmp.cleanup()

    def _events(self, ev_type=None):
        from engine import telemetry
        recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
        if ev_type is not None:
            recs = [r for r in recs if r["ev"] == ev_type]
        return recs


# ══════════════════════════════════════════════════════════════════════════
# 3. credit_flow emitter (db.log_credit chokepoint)
# ══════════════════════════════════════════════════════════════════════════
class TestCreditFlowEmitter(_EmitterCase):
    def test_faucet_emits_credit_flow(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            await db.adjust_credits(1, 500, "mission")
        _run(go())
        evs = self._events("credit_flow")
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["char_id"], 1)
        self.assertEqual(e["delta"], 500)
        self.assertEqual(e["tag"], "mission")
        self.assertEqual(e["balance"], 1500)

    def test_sink_emits_negative_delta(self):
        async def go():
            db = await _fresh_db(start_credits=1000)
            await db.adjust_credits(1, -200, "docking_fee")
        _run(go())
        e = self._events("credit_flow")[0]
        self.assertEqual(e["delta"], -200)
        self.assertEqual(e["tag"], "docking_fee")
        self.assertEqual(e["balance"], 800)

    def test_system_path_emits(self):
        async def go():
            db = await _fresh_db()
            await db.adjust_credits(0, -1000, "treasury_sink")
        _run(go())
        e = self._events("credit_flow")[0]
        self.assertEqual(e["char_id"], 0)
        self.assertEqual(e["tag"], "treasury_sink")
        self.assertEqual(e["balance"], 0)


# ══════════════════════════════════════════════════════════════════════════
# 4. cp_award emitter (db.cp_add_character_points chokepoint)
# ══════════════════════════════════════════════════════════════════════════
class TestCPAwardEmitter(_EmitterCase):
    def test_cp_earn_emits(self):
        async def go():
            db = await _fresh_db(start_cp=0)
            await db.cp_add_character_points(1, 5)
        _run(go())
        evs = self._events("cp_award")
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["char_id"], 1)
        self.assertEqual(evs[0]["amount"], 5)

    def test_cp_spend_emits_negative(self):
        async def go():
            db = await _fresh_db(start_cp=20)
            await db.cp_add_character_points(1, -9)
        _run(go())
        self.assertEqual(self._events("cp_award")[0]["amount"], -9)


# ══════════════════════════════════════════════════════════════════════════
# 5. skill_check emitter (perform_skill_check chokepoint)
# ══════════════════════════════════════════════════════════════════════════
class TestSkillCheckEmitter(_EmitterCase):
    def test_perform_skill_check_emits(self):
        from engine.skill_checks import perform_skill_check
        r = perform_skill_check(_char(), "search", 10, auto_consume_lead=False)
        evs = self._events("skill_check")
        self.assertEqual(len(evs), 1)
        e = evs[0]
        self.assertEqual(e["char_id"], 42)
        self.assertEqual(e["skill"], "search")
        self.assertEqual(e["difficulty"], 10)
        self.assertEqual(e["roll"], r.roll)
        self.assertEqual(e["success"], r.success)
        self.assertEqual(e["margin"], r.margin)
        self.assertIn("crit", e)
        self.assertIn("fumble", e)

    def test_sample_tunable_respected(self):
        # telemetry.skill_check_sample = 0 → no skill_check events emitted.
        import engine.tunables as tun
        orig = tun.get_tunable
        tun.get_tunable = lambda k, d=None: (0.0 if k == "telemetry.skill_check_sample" else orig(k, d))
        try:
            from engine.skill_checks import perform_skill_check
            for _ in range(30):
                perform_skill_check(_char(), "search", 10, auto_consume_lead=False)
            self.assertEqual(len(self._events("skill_check")), 0)
        finally:
            tun.get_tunable = orig


# ══════════════════════════════════════════════════════════════════════════
# 6. fail-open invariant — a broken telemetry layer never breaks gameplay
# ══════════════════════════════════════════════════════════════════════════
class TestFailOpen(unittest.TestCase):
    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_skill_check_survives_broken_emit(self):
        import engine.telemetry as telemetry

        def boom(*a, **k):
            raise RuntimeError("telemetry exploded")

        orig = telemetry.emit
        telemetry.emit = boom
        try:
            from engine.skill_checks import perform_skill_check
            r = perform_skill_check(_char(), "search", 10,
                                    auto_consume_lead=False)
            self.assertIsNotNone(r)          # roll still produced
            self.assertEqual(r.difficulty, 10)
        finally:
            telemetry.emit = orig

    def test_adjust_credits_survives_broken_emit(self):
        import engine.telemetry as telemetry

        def boom(*a, **k):
            raise RuntimeError("telemetry exploded")

        orig = telemetry.emit
        telemetry.emit = boom
        try:
            async def go():
                db = await _fresh_db(start_credits=1000)
                return await db.adjust_credits(1, 250, "mission")
            bal = _run(go())
            self.assertEqual(bal, 1250)       # credit move still committed
        finally:
            telemetry.emit = orig


# ══════════════════════════════════════════════════════════════════════════
# 7. flush tick handler
# ══════════════════════════════════════════════════════════════════════════
class TestFlushTick(_EmitterCase):
    def test_flush_tick_drains_to_disk(self):
        from engine import telemetry
        from server.tick_handlers_telemetry import flush_telemetry_tick
        telemetry.emit("tick_test", {"n": 1})
        _run(flush_telemetry_tick(None))   # handler ignores ctx
        self.assertEqual(len(telemetry.get_sink().drain()), 0)  # buffer drained
        with open(telemetry.get_sink().path, encoding="utf-8") as fh:
            rows = [json.loads(ln) for ln in fh if ln.strip()]
        self.assertEqual(rows[0]["ev"], "tick_test")


# ══════════════════════════════════════════════════════════════════════════
# 8. structural drift pins — the chokepoint wiring can't silently vanish
# ══════════════════════════════════════════════════════════════════════════
class TestWiringPins(unittest.TestCase):
    def _src(self, rel):
        with open(os.path.join(PROJECT_ROOT, rel), encoding="utf-8") as fh:
            return fh.read()

    def test_credit_and_cp_emitters_present(self):
        src = self._src("db/database.py")
        self.assertIn('_tele_emit("credit_flow"', src)
        self.assertIn('_tele_emit("cp_award"', src)

    def test_skill_check_emitter_present(self):
        self.assertIn('_tele_emit("skill_check"',
                      self._src("engine/skill_checks.py"))

    def test_flush_tick_registered(self):
        src = self._src("server/game_server.py")
        self.assertIn("flush_telemetry_tick", src)
        self.assertIn('"telemetry_flush"', src)


if __name__ == "__main__":
    unittest.main()
