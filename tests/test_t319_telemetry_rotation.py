# -*- coding: utf-8 -*-
"""tests/test_t319_telemetry_rotation.py — T3.19 sink on-disk rotation cap.

The in-memory buffer was already bounded, but the append-only JSON-line FILE
was not: a default-on, broad-capture sink grows without bound over a launch and
can eventually exhaust the disk. ``TelemetrySink`` now rotates the file when it
reaches ``max_file_bytes`` (keeping ``backup_count`` backups), bounding on-disk
telemetry at roughly ``(backup_count + 1) * max_file_bytes``.

Contract under test:
  * rotation fires only once the EXISTING file is at/over the cap, then the new
    batch lands in a fresh file;
  * backups shift ``.1 -> .2 -> … -> .<backup_count>`` and the oldest is dropped;
  * ``backup_count == 0`` discards history (caps size, keeps no backups);
  * ``max_file_bytes == 0`` disables rotation (legacy unbounded behaviour);
  * the real default cap never fires on small writes (existing flush tests keep
    their behaviour);
  * rotation is fail-open — a rotation error never loses the write nor raises;
  * ``configure`` carries the rotation policy forward; env overrides apply;
  * the read side still parses/summarises after a rotation.
"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


class TestRotation(unittest.TestCase):
    def _sink(self, tmp, **kw):
        from engine.telemetry import TelemetrySink
        kw.setdefault("enabled", True)
        return TelemetrySink(path=os.path.join(tmp, "events.jsonl"), **kw)

    def _read(self, path):
        with open(path, encoding="utf-8") as fh:
            return fh.read()

    def test_rotation_creates_backup_when_cap_exceeded(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=10, backup_count=3)
            s.emit("e", {"i": 0}); s.flush()          # file created, no rotation
            self.assertTrue(os.path.exists(s.path))
            self.assertFalse(os.path.exists(s.path + ".1"))
            self.assertEqual(s.stats()["rotations"], 0)
            s.emit("e", {"i": 1}); s.flush()          # file > cap → rotate, write
            self.assertTrue(os.path.exists(s.path + ".1"))
            self.assertEqual(s.stats()["rotations"], 1)
            self.assertIn('"i":0', self._read(s.path + ".1"))   # old batch rolled
            self.assertIn('"i":1', self._read(s.path))          # new batch current

    def test_backups_shift_and_oldest_dropped(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=10, backup_count=2)
            for i in range(4):
                s.emit("e", {"i": i}); s.flush()
            # flush0 write; flush1/2/3 each rotate then write → 3 rotations.
            self.assertEqual(s.stats()["rotations"], 3)
            self.assertTrue(os.path.exists(s.path))            # current = i3
            self.assertTrue(os.path.exists(s.path + ".1"))     # i2
            self.assertTrue(os.path.exists(s.path + ".2"))     # i1
            self.assertFalse(os.path.exists(s.path + ".3"))    # cap=2 → never .3
            self.assertIn('"i":3', self._read(s.path))
            self.assertIn('"i":2', self._read(s.path + ".1"))
            self.assertIn('"i":1', self._read(s.path + ".2"))  # i0 dropped

    def test_backup_count_zero_discards(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=10, backup_count=0)
            s.emit("e", {"i": 0}); s.flush()
            s.emit("e", {"i": 1}); s.flush()          # cap hit, no backups → discard
            self.assertFalse(os.path.exists(s.path + ".1"))
            self.assertEqual(s.stats()["rotations"], 1)
            cur = self._read(s.path)
            self.assertIn('"i":1', cur)
            self.assertNotIn('"i":0', cur)

    def test_rotation_disabled_when_cap_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=0, backup_count=3)
            for i in range(5):
                s.emit("e", {"i": i}); s.flush()
            self.assertEqual(s.stats()["rotations"], 0)
            self.assertFalse(os.path.exists(s.path + ".1"))
            rows = [json.loads(ln) for ln in self._read(s.path).splitlines()
                    if ln.strip()]
            self.assertEqual([r["i"] for r in rows], [0, 1, 2, 3, 4])  # all kept

    def test_default_cap_does_not_rotate_small_writes(self):
        # Guards the existing flush tests: the real default cap won't fire on
        # the handful of tiny events a unit test writes.
        from engine.telemetry import _DEFAULT_MAX_FILE_BYTES
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=_DEFAULT_MAX_FILE_BYTES)
            for i in range(10):
                s.emit("e", {"i": i}); s.flush()
            self.assertEqual(s.stats()["rotations"], 0)
            self.assertFalse(os.path.exists(s.path + ".1"))

    def test_stats_reports_rotation_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=123, backup_count=2)
            st = s.stats()
            for k in ("max_file_bytes", "backup_count", "rotations"):
                self.assertIn(k, st)
            self.assertEqual(st["max_file_bytes"], 123)
            self.assertEqual(st["backup_count"], 2)
            self.assertEqual(st["rotations"], 0)

    def test_rotation_is_failopen(self):
        # A rotation that errors must neither lose the write nor raise.
        import os as _os
        with tempfile.TemporaryDirectory() as tmp:
            s = self._sink(tmp, max_file_bytes=10, backup_count=2)
            s.emit("e", {"i": 0}); s.flush()
            orig = _os.replace

            def boom(*a, **k):
                raise OSError("rotate boom")

            _os.replace = boom
            try:
                s.emit("e", {"i": 1})
                n = s.flush()             # rotation fails internally; write proceeds
            finally:
                _os.replace = orig
            self.assertEqual(n, 1)        # the append still succeeded
            vals = [json.loads(ln)["i"] for ln in self._read(s.path).splitlines()
                    if ln.strip()]
            self.assertIn(1, vals)        # event 1 persisted despite failed roll

    def test_configure_carries_rotation_forward(self):
        from engine import telemetry
        with tempfile.TemporaryDirectory() as tmp:
            telemetry.reset()
            telemetry.configure(path=os.path.join(tmp, "e.jsonl"), enabled=True,
                                max_file_bytes=999, backup_count=5)
            self.assertEqual(telemetry.get_sink().max_file_bytes, 999)
            self.assertEqual(telemetry.get_sink().backup_count, 5)
            telemetry.configure(enabled=True)          # omit rotation → keep it
            self.assertEqual(telemetry.get_sink().max_file_bytes, 999)
            self.assertEqual(telemetry.get_sink().backup_count, 5)
            telemetry.reset()

    def test_env_override(self):
        import engine.telemetry as tele
        saved = {k: os.environ.get(k) for k in
                 ("SWMUSH_TELEMETRY_MAX_BYTES", "SWMUSH_TELEMETRY_BACKUPS")}
        os.environ["SWMUSH_TELEMETRY_MAX_BYTES"] = "4096"
        os.environ["SWMUSH_TELEMETRY_BACKUPS"] = "7"
        try:
            s = tele.TelemetrySink(path="x.jsonl", enabled=True)
            self.assertEqual(s.max_file_bytes, 4096)
            self.assertEqual(s.backup_count, 7)
            os.environ["SWMUSH_TELEMETRY_MAX_BYTES"] = "notanint"   # bad → default
            s2 = tele.TelemetrySink(path="x.jsonl", enabled=True)
            self.assertEqual(s2.max_file_bytes, tele._DEFAULT_MAX_FILE_BYTES)
        finally:
            for k, v in saved.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_read_side_works_after_rotation(self):
        from engine import telemetry
        with tempfile.TemporaryDirectory() as tmp:
            telemetry.reset()
            telemetry.configure(path=os.path.join(tmp, "e.jsonl"), enabled=True,
                                max_file_bytes=10, backup_count=2)
            s = telemetry.get_sink()
            s.emit("grind_kill", {"reward": 5, "char_id": 1, "npc_name": "x"})
            s.flush()
            s.emit("grind_kill", {"reward": 7, "char_id": 1, "npc_name": "y"})
            s.flush()                                  # triggers a rotation
            self.assertGreaterEqual(s.stats()["rotations"], 1)
            recs = telemetry.read_recent(include_buffer=True)
            self.assertTrue(any(r.get("ev") == "grind_kill" for r in recs))
            summ = telemetry.summarize(recs)           # pure rollup must not raise
            self.assertIn("grind", summ)
            telemetry.reset()


if __name__ == "__main__":
    unittest.main()
