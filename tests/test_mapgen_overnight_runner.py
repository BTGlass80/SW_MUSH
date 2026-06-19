"""Offline proof for the overnight Nano sweep runner
(tools/mapgen/overnight_runner.py).

The highest-risk part is the AREA_PLATE slug map (seed slug -> hand-made plate
filename is NOT uniform), so those checks run against the REAL static/maps to
catch a mis-paired anchor. The rest (ledger budget cap, lock, one-round mock
sweep) runs fully isolated in a tempdir.

Run: python -m pytest tests/test_mapgen_overnight_runner.py -x
"""
import asyncio
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.mapgen.paths as P  # noqa: E402
from tools.mapgen import overnight_runner as OR  # noqa: E402
from tools.mapgen.nano_client import MockNanoClient, _PLACEHOLDER_PNG  # noqa: E402

_REAL_SEEDS = Path(__file__).resolve().parents[1] / "static" / "tools" / "seeds"
_REAL_MAPS = Path(__file__).resolve().parents[1] / "static" / "maps"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestAreaPlateMap(unittest.TestCase):
    def test_sweep_order_all_have_a_plate(self):
        for area in OR.SWEEP_ORDER:
            self.assertIn(area, OR.AREA_PLATE, f"{area} has no style-anchor plate")

    def test_every_plate_file_exists_on_disk(self):
        # The slug map must match real files — a wrong slug = no/incorrect anchor.
        for area, plate in OR.AREA_PLATE.items():
            self.assertTrue((_REAL_MAPS / plate).exists(),
                            f"{area} -> {plate} not found in static/maps")

    def test_every_area_has_a_seed_and_brief(self):
        for area in OR.SWEEP_ORDER:
            self.assertTrue((_REAL_SEEDS / f"{area}_tight_seed.png").exists(),
                            f"{area} has no tight seed")
            self.assertTrue((_REAL_SEEDS / f"{area}_paint_brief.md").exists(),
                            f"{area} has no paint brief")


class TestLockAndLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="or_"))
        self._orig = (P.BATCHES_DIR, P.SEEDS_DIR, P.MAPS_DIR,
                      OR.LEDGER, OR.LOCKFILE, OR.SWEEP_ORDER, OR.BUDGET_CENTS)
        P.BATCHES_DIR = self.tmp / "batches"
        P.SEEDS_DIR = self.tmp / "seeds"
        P.MAPS_DIR = self.tmp / "maps"
        OR.LEDGER = P.BATCHES_DIR / "_overnight" / "ledger.json"
        OR.LOCKFILE = P.BATCHES_DIR / "_overnight" / "lock"
        for d in (P.SEEDS_DIR, P.MAPS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        # one isolated city for the mock sweep
        OR.SWEEP_ORDER = ["mos_eisley"]
        shutil.copy2(_REAL_SEEDS / "mos_eisley_tight_seed.png",
                     P.SEEDS_DIR / "mos_eisley_tight_seed.png")
        shutil.copy2(_REAL_SEEDS / "mos_eisley_paint_brief.md",
                     P.SEEDS_DIR / "mos_eisley_paint_brief.md")
        (P.MAPS_DIR / "mos_eisley_substrate.png").write_bytes(_PLACEHOLDER_PNG)

    def tearDown(self):
        (P.BATCHES_DIR, P.SEEDS_DIR, P.MAPS_DIR,
         OR.LEDGER, OR.LOCKFILE, OR.SWEEP_ORDER, OR.BUDGET_CENTS) = self._orig

    def test_lock_acquire_then_blocks(self):
        self.assertTrue(OR._acquire_lock(), "first acquire should succeed")
        self.assertFalse(OR._acquire_lock(), "a fresh lock blocks a second sweep")
        OR._release_lock()
        self.assertTrue(OR._acquire_lock(), "after release the lock is free again")
        OR._release_lock()

    def test_mock_sweep_updates_ledger_and_restores_brief(self):
        brief = P.SEEDS_DIR / "mos_eisley_paint_brief.md"
        before = brief.read_bytes()
        rc = _run(OR._sweep(use_mock=True, n=2, loop=False))
        self.assertEqual(rc, 0)
        led = OR._load_ledger()
        self.assertEqual(led["images"], 2)
        self.assertGreater(led["cents_spent"], 0)
        # the wrapped brief must be restored byte-identical (non-destructive)
        self.assertEqual(brief.read_bytes(), before,
                         "the style-preamble wrap must be reverted after the sweep")
        # candidate PNGs landed in the isolated batch dir
        cand = P.BATCHES_DIR / "mos_eisley" / "on_r0" / "candidates"
        self.assertEqual(len(list(cand.glob("*.png"))), 2)

    def test_budget_cap_sets_done(self):
        OR.BUDGET_CENTS = 4.0  # below one image at 4¢/img -> first round trips done
        led = {"cents_spent": 0.0, "images": 0, "round": 0, "done": False,
               "budget_cents": OR.BUDGET_CENTS, "per_image_cents": 4.0, "history": []}
        OR._save_ledger(led)
        _run(OR._sweep(use_mock=True, n=2, loop=True))  # loop must still terminate
        self.assertTrue(OR._load_ledger()["done"], "budget cap must set DONE")


if __name__ == "__main__":
    unittest.main()
