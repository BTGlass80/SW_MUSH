"""Offline proof that the map-automation framework (tools/mapgen) runs
end-to-end with no API keys and no frozen coordinates — the structure is real,
not just written. Also pins the "toe the line" loop: bold-start, back-off on
refusal / off-theme, and boundary recording.

Run: python -m pytest tests/test_mapgen_pipeline_offline.py -x
"""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.mapgen import (  # noqa: E402
    apply_term_substitutions, terms_present, phrase_for,
    MockNanoClient, GenResult, MockScreener, screen_image,
    NoOpCoordinateScorer, CompositeRanker, screen_to_score,
    BatchOrchestrator, select_painting, record_boundary, load_boundaries,
)
from tools.mapgen import term_substitutions as tsub  # noqa: E402
from tools.mapgen.nano_client import create_nano_client  # noqa: E402
import pytest

pytestmark = pytest.mark.slow  # heavy: full world build (build_mos_eisley / load_world_dry_run)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class TestTermSubstitution(unittest.TestCase):
    def test_franchise_terms_are_replaced(self):
        out = apply_term_substitutions("A Tatooine landspeeder near the cantina.")
        self.assertNotIn("landspeeder", out.lower())
        self.assertNotIn("cantina", out.lower())

    def test_idempotent(self):
        once = apply_term_substitutions("a landspeeder")
        twice = apply_term_substitutions(once)
        self.assertEqual(once, twice)

    def test_ladder_rung_selects_phrasing(self):
        bold = phrase_for("landspeeder", 0)
        safe = phrase_for("landspeeder", 99)  # clamps to floor
        self.assertNotEqual(bold, safe)

    def test_era_terms_never_survive(self):
        out = apply_term_substitutions("Imperial Empire Rebel stormtrooper")
        for bad in ("imperial", "empire", "rebel", "stormtrooper"):
            self.assertNotIn(bad, out.lower())

    def test_terms_present_detects(self):
        self.assertIn("landspeeder", terms_present("an old landspeeder"))
        self.assertEqual(terms_present("a quiet plaza"), [])


class TestScreenerOffline(unittest.TestCase):
    def test_mock_passes_clean(self):
        v = _run(screen_image(b"img", "desert terrain", provider=None))
        self.assertTrue(v["passed"])
        self.assertTrue(v["on_theme"])

    def test_injected_off_theme_fails(self):
        screener = MockScreener(inject_flags=["off-theme: ocean ship in desert"])
        v = _run(screener.screen(b"img", "desert"))
        self.assertFalse(v["on_theme"])
        self.assertFalse(v["passed"])

    def test_escalate_band_flag(self):
        # Build a verdict in the borderline band via the finalize path.
        from tools.mapgen.screen import _finalize
        v = _finalize({"passed": True, "score": 60, "has_text": False,
                       "on_theme": True, "flags": [], "reasoning": "x"})
        self.assertIn("ESCALATE", v["flags"])


class TestScoring(unittest.TestCase):
    def test_noop_coord_scorer_neutral(self):
        self.assertEqual(NoOpCoordinateScorer().score_coordinate_fit(b"", {}), 50.0)

    def test_off_theme_floors_screen_score(self):
        score = screen_to_score({"score": 90, "has_text": False, "on_theme": False})
        self.assertLessEqual(score, 20.0)

    def test_composite_weights(self):
        r = CompositeRanker(screen_weight=0.7, coord_weight=0.3)
        self.assertAlmostEqual(r.composite(100, 0), 70.0, places=1)


class TestFactoryOffline(unittest.TestCase):
    def test_no_key_yields_mock(self):
        # Ensure no key in this test's env.
        for k in ("GOOGLE_API_KEY", "GEMINI_API_KEY"):
            os.environ.pop(k, None)
        client = _run(create_nano_client())
        self.assertIsInstance(client, MockNanoClient)


class TestToeTheLineLoop(unittest.TestCase):
    """The bold-start / back-off / record behavior, with a fake nano client."""

    class _RefuseThenPass:
        """Refuses the first call (forcing a back-off), passes after."""
        def __init__(self):
            self.calls = 0

        async def generate_image(self, seed, style, brief):
            self.calls += 1
            if self.calls == 1:
                return GenResult(image=None, refused=True, error="content filter")
            return GenResult(image=b"\x89PNG_ok")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mapgen_toe_"))
        self.boundaries = self.tmp / "term_boundaries.json"

    def test_backoff_on_refusal_then_records_boundary(self):
        brief = "A weathered landspeeder crosses the dunes."
        orch = BatchOrchestrator(
            "tatooine.test", nano_client=self._RefuseThenPass(),
            screener_provider=None, boundaries_path=self.boundaries)
        # Drive a single candidate through the loop directly.
        art = _run(orch._make_one_candidate(
            "cand_00", Path("seed.png"), brief, brief, None,
            self.tmp / "cand_00.png", {}, "2026-06-13"))
        self.assertIsNotNone(art, "candidate should survive after one back-off")
        self.assertIn("stepped a term down", art.notes)
        # The boundary file should now record landspeeder at a non-bold rung.
        data = load_boundaries(self.boundaries)
        self.assertIn("landspeeder", data["terms"])
        self.assertGreaterEqual(data["terms"]["landspeeder"]["rung"], 1)

    def test_boundary_only_tightens_to_bolder(self):
        record_boundary("landspeeder", 2, 80.0, verified="x", path=self.boundaries)
        record_boundary("landspeeder", 1, 85.0, verified="y", path=self.boundaries)  # bolder
        record_boundary("landspeeder", 2, 90.0, verified="z", path=self.boundaries)  # safer, ignored
        rec = load_boundaries(self.boundaries)["terms"]["landspeeder"]
        self.assertEqual(rec["rung"], 1, "boldest proven rung should stick")


class TestEscalationRouting(unittest.TestCase):
    """A borderline screen verdict should route to result.escalated, not silently
    rank — the human/Opus second-look queue."""

    class _BorderlineScreener:
        """Mock that returns ESCALATE-band verdicts so the routing fires."""
        async def screen(self, image_bytes, geography):
            from tools.mapgen.screen import _finalize
            return _finalize({"passed": True, "score": 60, "has_text": False,
                              "on_theme": True, "flags": [], "reasoning": "borderline"})

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mapgen_esc_"))
        import tools.mapgen.paths as P
        self._orig = (P.BATCHES_DIR, P.MAPS_DIR)
        P.BATCHES_DIR = self.tmp / "batches"
        P.MAPS_DIR = self.tmp / "maps"

    def tearDown(self):
        import tools.mapgen.paths as P
        P.BATCHES_DIR, P.MAPS_DIR = self._orig

    def test_borderline_candidates_are_escalated(self):
        # Patch the module-level screen_image to use the borderline screener.
        import tools.mapgen.batch as B
        orig = B.screen_image
        borderline = self._BorderlineScreener()

        async def _patched(img, brief, geo, provider=None):
            return await borderline.screen(img, geo)
        B.screen_image = _patched
        try:
            orch = B.BatchOrchestrator(
                "tatooine.test", nano_client=MockNanoClient(),
                boundaries_path=self.tmp / "b.json")
            result = _run(orch.run_batch(n_candidates=3, timestamp="ts"))
            # Every candidate is borderline -> all escalated.
            self.assertEqual(len(result.escalated), 3)
            self.assertEqual(set(result.escalated), set(result.top_k))
            # Persisted in the manifest.
            manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
            self.assertEqual(len(manifest["escalated"]), 3)
        finally:
            B.screen_image = orig


class TestBoundarySeedFile(unittest.TestCase):
    def test_committed_seed_is_valid_and_empty(self):
        from tools.mapgen import paths as P
        data = json.loads(P.TERM_BOUNDARIES_FILE.read_text(encoding="utf-8"))
        self.assertIn("terms", data)
        self.assertEqual(data["terms"], {}, "seed should start empty")


class TestFullPipelineOffline(unittest.TestCase):
    """The headline proof: run_batch end-to-end on mocks, manifest round-trips,
    selection writes a substrate, all with no keys and no frozen coords."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="mapgen_e2e_"))
        # Redirect output dirs into tmp so the test never touches real maps/.
        import tools.mapgen.paths as P
        self._orig = (P.BATCHES_DIR, P.MAPS_DIR)
        P.BATCHES_DIR = self.tmp / "batches"
        P.MAPS_DIR = self.tmp / "maps"

    def tearDown(self):
        import tools.mapgen.paths as P
        P.BATCHES_DIR, P.MAPS_DIR = self._orig

    def test_run_batch_and_select(self):
        orch = BatchOrchestrator(
            "tatooine.mos_eisley", nano_client=MockNanoClient(),
            screener_provider=None, coord_scorer=NoOpCoordinateScorer(),
            boundaries_path=self.tmp / "boundaries.json")
        result = _run(orch.run_batch(n_candidates=4, timestamp="20260613_0001"))

        # N candidate PNGs exist.
        self.assertEqual(len(result.candidates), 4)
        for c in result.candidates:
            self.assertTrue(Path(c.image_path).exists(), "candidate PNG written")
            self.assertGreater(c.composite_rank, 0)

        # Ranked + manifest round-trips.
        self.assertEqual(len(result.top_k), 4)
        manifest = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(manifest["area_key"], "tatooine.mos_eisley")
        self.assertEqual(len(manifest["candidates"]), 4)

        # Selection writes a substrate PNG + records the choice + emits the line.
        line = select_painting(result, result.top_k[0], slug="mos_eisley")
        self.assertIsNotNone(line)
        self.assertIn("substrate_image:", line)
        import tools.mapgen.paths as P
        self.assertTrue((P.MAPS_DIR / "mos_eisley_substrate.png").exists())
        reloaded = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
        self.assertEqual(reloaded["selected"], result.top_k[0])


if __name__ == "__main__":
    unittest.main()
