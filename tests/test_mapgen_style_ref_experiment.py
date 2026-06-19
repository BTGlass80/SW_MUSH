"""Offline proof for the STYLE-REFERENCE experiment harness
(tools/mapgen/style_ref_experiment.py).

Pins the three things the harness must get right without spending a cent:
  1. It runs end-to-end in --mock mode and produces N candidates.
  2. It is NON-DESTRUCTIVE: the git-tracked seed / keymap / live brief are
     restored byte-identical after the run (it only overwrites them transiently).
  3. The error paths (missing style brief; live-requested-but-no-key) fail
     loudly to None rather than silently mocking.

Fully isolated: paths.SEEDS_DIR / BATCHES_DIR / MAPS_DIR are redirected into a
tempdir so the test never touches static/maps or the real seeds.

Run: python -m pytest tests/test_mapgen_style_ref_experiment.py -x
"""
import asyncio
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import tools.mapgen.paths as P  # noqa: E402
from tools.mapgen import style_ref_experiment as SRE  # noqa: E402
from tools.mapgen.nano_client import _PLACEHOLDER_PNG  # noqa: E402

AREA = "mos_eisley"
ERA = "clone_wars"
# The real seeds dir + world map the harness regenerates the desert seed FROM.
_REAL_SEEDS = Path(__file__).resolve().parents[1] / "static" / "tools" / "seeds"


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestStyleRefExperimentOffline(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="sre_"))
        self._orig = (P.SEEDS_DIR, P.BATCHES_DIR, P.MAPS_DIR)
        P.SEEDS_DIR = self.tmp / "seeds"
        P.BATCHES_DIR = self.tmp / "batches"
        P.MAPS_DIR = self.tmp / "maps"
        for d in (P.SEEDS_DIR, P.BATCHES_DIR, P.MAPS_DIR):
            d.mkdir(parents=True, exist_ok=True)
        # Seed the isolated dir with the small text briefs + a stand-in seed/keymap
        # (regenerate_desert_seed will overwrite the seed/keymap, then restore).
        for name in (f"{AREA}_paint_brief.md", f"{AREA}_paint_brief.styleref.md"):
            shutil.copy2(_REAL_SEEDS / name, P.SEEDS_DIR / name)
        for name in (f"{AREA}_tight_seed.png", f"{AREA}_tight_keymap.png"):
            (P.SEEDS_DIR / name).write_bytes(_PLACEHOLDER_PNG)
        # A stand-in hand-made plate to use as the style anchor.
        (P.MAPS_DIR / f"{AREA}_substrate.png").write_bytes(_PLACEHOLDER_PNG)

    def tearDown(self):
        P.SEEDS_DIR, P.BATCHES_DIR, P.MAPS_DIR = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _snapshot(self):
        return {n: (P.SEEDS_DIR / n).read_bytes() for n in (
            f"{AREA}_paint_brief.md", f"{AREA}_paint_brief.styleref.md",
            f"{AREA}_tight_seed.png", f"{AREA}_tight_keymap.png")}

    def test_runs_and_is_non_destructive(self):
        before = self._snapshot()
        result = _run(SRE.run_experiment(
            AREA, timestamp="t1", n_candidates=2, era=ERA,
            style_plate=P.MAPS_DIR / f"{AREA}_substrate.png",
            long_edge=256, use_mock=True, use_screen=False))

        self.assertIsNotNone(result, "mock run should produce a BatchResult")
        self.assertEqual(len(result.candidates), 2)
        cand_dir = P.BATCHES_DIR / AREA / "t1" / "candidates"
        self.assertEqual(len(list(cand_dir.glob("*.png"))), 2,
                         "two candidate PNGs written into the isolated batch dir")

        after = self._snapshot()
        for name, b in before.items():
            self.assertEqual(after[name], b,
                             f"{name} must be restored byte-identical (non-destructive)")

    def test_missing_style_brief_fails_to_none(self):
        (P.SEEDS_DIR / f"{AREA}_paint_brief.styleref.md").unlink()
        result = _run(SRE.run_experiment(
            AREA, timestamp="t2", n_candidates=1, era=ERA,
            style_plate=None, long_edge=256, use_mock=True, use_screen=False))
        self.assertIsNone(result, "absent style brief must fail loudly, not mock")

    def test_live_requested_without_key_fails_to_none(self):
        saved = {k: os.environ.pop(k, None) for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY")}
        try:
            result = _run(SRE.run_experiment(
                AREA, timestamp="t3", n_candidates=1, era=ERA, style_plate=None,
                long_edge=256, use_mock=False, use_screen=False))
            self.assertIsNone(result, "live-without-key must error to None, not "
                                      "silently fall back to placeholder images")
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


class TestDesertSeedOverride(unittest.TestCase):
    """The warm-desert palette must contain NO cool/blue hue (index 0 was the
    slate-blue Gemini painted as water) — a pure-data invariant."""

    def test_palette_is_all_warm(self):
        self.assertEqual(len(SRE.WARM_DESERT_HUES), 7)
        for (r, g, b) in SRE.WARM_DESERT_HUES:
            self.assertGreater(r, b, f"hue ({r},{g},{b}) must be warm (R>B), not blue")
            self.assertGreaterEqual(r, g, f"hue ({r},{g},{b}) should be sand-warm")

    def test_markers_are_warm(self):
        for (r, g, b) in (SRE.WARM_LM_DIST, SRE.WARM_LM_GEN):
            self.assertGreater(r, b, "muted landmark markers must not read cool/blue")

    def test_regenerate_writes_seed_with_no_water_blue_district(self):
        # Render a tiny seed into an isolated dir and confirm the warm override
        # left NO strongly-blue region — that slate-blue district (default index
        # 0) is exactly what Gemini painted as WATER. The dark neutral canvas
        # (BG_SEED) is fine; we only flag genuinely blue fills (b well above r).
        tmp = Path(tempfile.mkdtemp(prefix="sre_seed_"))
        orig = P.SEEDS_DIR
        P.SEEDS_DIR = tmp
        try:
            SRE.regenerate_desert_seed(AREA, era=ERA, long_edge=256)
            seed = tmp / f"{AREA}_tight_seed.png"
            self.assertTrue(seed.exists(), "warm seed written")
            from PIL import Image
            img = Image.open(seed).convert("RGB")
            px = list(img.getdata())
            blue = sum(1 for (r, g, b) in px if b > r + 15)
            self.assertLess(blue / len(px), 0.02,
                            "the warm-desert seed must have ~no slate-blue (water) region")
        finally:
            P.SEEDS_DIR = orig
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
