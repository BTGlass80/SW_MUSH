# -*- coding: utf-8 -*-
"""
tests/test_f6a1_director_lore_loaders.py — Drop F.6a.1 tests

Exercises the three new loaders added to engine/world_loader.py for the
Director / Lore Pivot:

    load_lore(manifest)              -> Optional[LoreCorpus]
    load_director_config(manifest)   -> Optional[DirectorConfig]
    load_ambient_pools(manifest)     -> Optional[AmbientPools]

Coverage map (per clone_wars_director_lore_pivot_design_v1.md §5.1):

  Real-data smoke (sanity that authored YAML parses cleanly):
    - test_clone_wars_lore_loads_clean
    - test_clone_wars_director_config_loads_clean
    - test_clone_wars_ambient_pools_loads_clean
    - test_gcw_lore_loads_clean
    - test_gcw_director_config_loads_clean
    - test_gcw_ambient_pools_loads_clean

  Optional-ref behavior (era can omit any of the three):
    - test_loaders_return_none_when_ref_absent

  Lore validator coverage:
    - test_lore_missing_title_is_error
    - test_lore_empty_content_is_error
    - test_lore_invalid_zone_scope_type_is_error
    - test_lore_priority_out_of_range_is_warning
    - test_lore_open_category_vocabulary
    - test_lore_duplicate_title_is_warning

  Director config validator coverage:
    - test_director_config_missing_valid_factions_raises
    - test_director_config_missing_zone_baselines_raises
    - test_director_config_missing_system_prompt_raises
    - test_director_config_zone_mentions_unknown_faction_is_warning
    - test_director_config_influence_min_must_be_less_than_max
    - test_director_config_milestone_only_id_and_trigger_required
    - test_director_config_milestone_preserves_raw_for_either_shape
    - test_director_config_influence_out_of_range_is_warning

  Ambient pools validator coverage:
    - test_ambient_string_lines_coerce_to_default_weight
    - test_ambient_negative_weight_is_warning
    - test_ambient_missing_text_is_error
    - test_ambient_top_level_must_be_mapping_raises

  CW-specific sanity (per design §5.3):
    - test_cw_baselines_temple_high_jedi_score
    - test_cw_baselines_geonosis_high_cis_score
    - test_cw_system_prompt_mentions_jedi_temple
    - test_cw_holonet_pool_present_and_nonempty
    - test_cw_rewicker_factions_translate_imperial_to_republic
"""
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.world_loader import (  # noqa: E402
    load_era_manifest,
    load_lore,
    load_director_config,
    load_ambient_pools,
    LoreCorpus,
    LoreEntry,
    DirectorConfig,
    MilestoneEvent,
    AmbientPools,
    AmbientLine,
    WorldLoadError,
)


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════


def _write(path: Path, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(body).lstrip("\n"), encoding="utf-8")


def _make_minimal_era(
    root: Path,
    era: str = "test_era",
    *,
    with_lore: str = None,
    with_director: str = None,
    with_ambient: str = None,
) -> Path:
    """Create a minimal era directory under `root`/`era`.

    `with_*` parameters, if provided, are relative paths inserted into
    content_refs and matching files written with placeholder bodies.
    Pass empty string to register the ref but write empty file.
    """
    era_dir = root / era

    refs = {
        "zones": "zones.yaml",
    }
    if with_lore is not None:
        refs["lore"] = "lore.yaml"
    if with_director is not None:
        refs["director_config"] = "director_config.yaml"
    if with_ambient is not None:
        refs["ambient_events"] = "ambient_events.yaml"

    refs_block = "\n".join(f"          {k}: {v}" for k, v in refs.items())

    _write(era_dir / "era.yaml", f"""
        schema_version: 1
        era:
          code: {era}
          name: "Test Era"
        content_refs:
{refs_block}
          planets: []
          wilderness: []
    """)
    _write(era_dir / "zones.yaml", """
        zones:
          test_zone:
            name_match: "test"
    """)

    if with_lore:
        _write(era_dir / "lore.yaml", with_lore)
    if with_director:
        _write(era_dir / "director_config.yaml", with_director)
    if with_ambient:
        _write(era_dir / "ambient_events.yaml", with_ambient)

    return era_dir


# Reusable minimal valid bodies
_VALID_LORE = """
    schema_version: 1
    entries:
      - title: "Test Entry"
        keywords: "test,sample"
        category: "concept"
        priority: 5
        content: "A test entry."
"""

_VALID_DIRECTOR = """
    schema_version: 1
    valid_factions: [alpha, beta]
    npc_only_factions: []
    influence_min: 0
    influence_max: 100
    max_delta_per_turn: 5
    zone_baselines:
      test_zone: { alpha: 50, beta: 50 }
    system_prompt: |
      You are a director. Be directorial.
"""

_VALID_AMBIENT = """
    schema_version: 1
    ambient_events:
      test_zone:
        - text: "A line."
        - text: "Another line."
          weight: 0.5
"""


# ══════════════════════════════════════════════════════════════════════════════
# Real-data smoke tests
# ══════════════════════════════════════════════════════════════════════════════


class _RealEraTestBase(unittest.TestCase):
    """Base for tests that read live data/worlds/<era>/. Skips when missing."""

    ERA: str = ""

    def setUp(self) -> None:
        era_dir = Path(PROJECT_ROOT) / "data" / "worlds" / self.ERA
        if not (era_dir / "era.yaml").is_file():
            self.skipTest(f"no era.yaml under data/worlds/{self.ERA}/")
        self.manifest = load_era_manifest(era_dir)


class TestCloneWarsRealData(_RealEraTestBase):
    ERA = "clone_wars"

    def test_clone_wars_lore_loads_clean(self):
        if self.manifest.lore_path is None:
            self.skipTest("no clone_wars/lore.yaml content_ref")
        corpus = load_lore(self.manifest)
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.report.errors, [])
        # Per design §5.1: "test_clone_wars_loads_32_entries" — accept >= 32
        # (49 at time of writing; future authoring may add more).
        self.assertGreaterEqual(len(corpus.entries), 32)

    def test_clone_wars_director_config_loads_clean(self):
        if self.manifest.director_config_path is None:
            self.skipTest("no clone_wars/director_config.yaml content_ref")
        dc = load_director_config(self.manifest)
        self.assertIsNotNone(dc)
        self.assertEqual(dc.report.errors, [])
        self.assertGreaterEqual(len(dc.valid_factions), 6)
        self.assertGreaterEqual(len(dc.zone_baselines), 30)

    def test_clone_wars_ambient_pools_loads_clean(self):
        if self.manifest.ambient_events_path is None:
            self.skipTest("no clone_wars/ambient_events.yaml content_ref")
        ap = load_ambient_pools(self.manifest)
        self.assertIsNotNone(ap)
        self.assertEqual(ap.report.errors, [])
        self.assertGreaterEqual(len(ap.pools), 10)

    # CW-specific sanity (per design §5.3)

    def test_cw_baselines_temple_high_jedi_score(self):
        dc = load_director_config(self.manifest)
        if dc is None or "coruscant_temple" not in dc.zone_baselines:
            self.skipTest("coruscant_temple not in baselines")
        self.assertGreaterEqual(
            dc.zone_baselines["coruscant_temple"].get("jedi_order", 0), 90,
            "Jedi Temple should have jedi_order >= 90"
        )

    def test_cw_baselines_geonosis_high_cis_score(self):
        dc = load_director_config(self.manifest)
        if dc is None or "geonosis_foundries" not in dc.zone_baselines:
            self.skipTest("geonosis_foundries not in baselines")
        self.assertGreaterEqual(
            dc.zone_baselines["geonosis_foundries"].get("cis", 0), 80,
            "Geonosis foundries should have cis >= 80"
        )

    def test_cw_system_prompt_mentions_jedi_temple(self):
        dc = load_director_config(self.manifest)
        self.assertIsNotNone(dc)
        self.assertIn("Jedi", dc.system_prompt,
                     "CW system_prompt must mention Jedi (atmospheric)")

    def test_cw_holonet_pool_present_and_nonempty(self):
        dc = load_director_config(self.manifest)
        self.assertIsNotNone(dc)
        self.assertGreaterEqual(len(dc.holonet_news_pool), 1,
                                "CW must author holonet_news_pool entries")

    def test_cw_rewicker_factions_translate_imperial_to_republic(self):
        dc = load_director_config(self.manifest)
        self.assertIsNotNone(dc)
        self.assertEqual(
            dc.rewicker_faction_codes.get("imperial"), "republic",
            "Rewicker must map imperial→republic for legacy code paths"
        )


class TestGCWRealData(_RealEraTestBase):
    ERA = "gcw"

    def test_gcw_lore_loads_clean(self):
        if self.manifest.lore_path is None:
            self.skipTest("no gcw/lore.yaml content_ref")
        corpus = load_lore(self.manifest)
        self.assertIsNotNone(corpus)
        self.assertEqual(corpus.report.errors, [])
        self.assertGreater(len(corpus.entries), 0)

    def test_gcw_director_config_loads_clean(self):
        if self.manifest.director_config_path is None:
            self.skipTest("no gcw/director_config.yaml content_ref")
        dc = load_director_config(self.manifest)
        self.assertIsNotNone(dc)
        self.assertEqual(dc.report.errors, [])
        # GCW uses a different milestone shape — assert that the
        # permissive parser preserved the GCW fields rather than
        # silently dropping them.
        if dc.milestone_events:
            self.assertTrue(
                any(m.headline is not None for m in dc.milestone_events),
                "GCW milestones should populate the `headline` field"
            )

    def test_gcw_ambient_pools_loads_clean(self):
        if self.manifest.ambient_events_path is None:
            self.skipTest("no gcw/ambient_events.yaml content_ref")
        ap = load_ambient_pools(self.manifest)
        self.assertIsNotNone(ap)
        self.assertEqual(ap.report.errors, [])
        self.assertGreater(len(ap.pools), 0)


# ══════════════════════════════════════════════════════════════════════════════
# Optional-ref behavior
# ══════════════════════════════════════════════════════════════════════════════


class TestOptionalRefs(unittest.TestCase):
    def test_loaders_return_none_when_ref_absent(self):
        """An era that omits all three refs gets None from each loader."""
        with TemporaryDirectory() as td:
            era_dir = _make_minimal_era(Path(td), "minimal_era")
            m = load_era_manifest(era_dir)
            self.assertIsNone(m.lore_path)
            self.assertIsNone(m.director_config_path)
            self.assertIsNone(m.ambient_events_path)
            self.assertIsNone(load_lore(m))
            self.assertIsNone(load_director_config(m))
            self.assertIsNone(load_ambient_pools(m))


# ══════════════════════════════════════════════════════════════════════════════
# Lore validator coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestLoreValidator(unittest.TestCase):
    def _load(self, body: str) -> LoreCorpus:
        with TemporaryDirectory() as td:
            era_dir = _make_minimal_era(Path(td), with_lore=body)
            m = load_era_manifest(era_dir)
            return load_lore(m)

    def test_lore_missing_title_is_error(self):
        corpus = self._load("""
            schema_version: 1
            entries:
              - keywords: "no,title"
                category: "concept"
                content: "no title here"
        """)
        self.assertEqual(len(corpus.entries), 0)
        self.assertTrue(any("title" in e for e in corpus.report.errors))

    def test_lore_empty_content_is_error(self):
        corpus = self._load("""
            schema_version: 1
            entries:
              - title: "Empty"
                keywords: "k"
                category: "concept"
                content: ""
        """)
        self.assertEqual(len(corpus.entries), 0)
        self.assertTrue(any("content" in e for e in corpus.report.errors))

    def test_lore_invalid_zone_scope_type_is_error(self):
        corpus = self._load("""
            schema_version: 1
            entries:
              - title: "Bad Zone"
                keywords: "k"
                category: "concept"
                content: "ok"
                zone_scope: [list, not, string]
        """)
        self.assertEqual(len(corpus.entries), 0)
        self.assertTrue(any("zone_scope" in e for e in corpus.report.errors))

    def test_lore_priority_out_of_range_is_warning(self):
        corpus = self._load("""
            schema_version: 1
            entries:
              - title: "Out of Range"
                keywords: "k"
                category: "concept"
                content: "ok"
                priority: 99
        """)
        self.assertEqual(len(corpus.entries), 1)
        self.assertEqual(corpus.report.errors, [])
        self.assertTrue(any("priority" in w for w in corpus.report.warnings))

    def test_lore_open_category_vocabulary(self):
        """Categories outside the documented set should be accepted (no warning).

        The GCW corpus uses 'history', 'item', 'npc' — the loader must
        treat category as an open vocabulary, not a fixed enum.
        """
        corpus = self._load("""
            schema_version: 1
            entries:
              - title: "Open Vocab Entry"
                keywords: "k"
                category: "history"
                content: "ok"
        """)
        self.assertEqual(len(corpus.entries), 1)
        self.assertEqual(corpus.entries[0].category, "history")
        self.assertEqual(corpus.report.errors, [])
        self.assertEqual(corpus.report.warnings, [])

    def test_lore_duplicate_title_is_warning(self):
        corpus = self._load("""
            schema_version: 1
            entries:
              - title: "Same"
                keywords: "k"
                category: "concept"
                content: "first"
              - title: "Same"
                keywords: "k"
                category: "concept"
                content: "second"
        """)
        self.assertEqual(len(corpus.entries), 2)
        self.assertTrue(any("duplicate" in w for w in corpus.report.warnings))


# ══════════════════════════════════════════════════════════════════════════════
# Director config validator coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestDirectorConfigValidator(unittest.TestCase):
    def _load(self, body: str) -> DirectorConfig:
        with TemporaryDirectory() as td:
            era_dir = _make_minimal_era(Path(td), with_director=body)
            m = load_era_manifest(era_dir)
            return load_director_config(m)

    def test_director_config_missing_valid_factions_raises(self):
        with self.assertRaises(WorldLoadError) as ctx:
            self._load("""
                schema_version: 1
                zone_baselines: {}
                system_prompt: "anything"
            """)
        self.assertIn("valid_factions", str(ctx.exception))

    def test_director_config_missing_zone_baselines_raises(self):
        with self.assertRaises(WorldLoadError) as ctx:
            self._load("""
                schema_version: 1
                valid_factions: [a, b]
                system_prompt: "anything"
            """)
        self.assertIn("zone_baselines", str(ctx.exception))

    def test_director_config_missing_system_prompt_raises(self):
        with self.assertRaises(WorldLoadError) as ctx:
            self._load("""
                schema_version: 1
                valid_factions: [a, b]
                zone_baselines: {}
            """)
        self.assertIn("system_prompt", str(ctx.exception))

    def test_director_config_zone_mentions_unknown_faction_is_warning(self):
        dc = self._load("""
            schema_version: 1
            valid_factions: [alpha, beta]
            zone_baselines:
              test_zone: { alpha: 50, gamma: 25 }
            system_prompt: "..."
        """)
        self.assertTrue(
            any("gamma" in w for w in dc.report.warnings),
            f"expected warning about unknown faction; warnings={dc.report.warnings}"
        )

    def test_director_config_influence_min_must_be_less_than_max(self):
        with self.assertRaises(WorldLoadError):
            self._load("""
                schema_version: 1
                valid_factions: [a]
                influence_min: 50
                influence_max: 50
                zone_baselines: {}
                system_prompt: "..."
            """)

    def test_director_config_milestone_only_id_and_trigger_required(self):
        """Both CW and GCW shapes parse cleanly under permissive contract."""
        dc = self._load("""
            schema_version: 1
            valid_factions: [a]
            zone_baselines: {}
            system_prompt: "..."
            milestone_events:
              - id: cw_shape
                trigger: { type: foo, threshold: 5 }
                cooldown_hours: 24
                narrative_priority: high
                output_type: ambient_holonet
                flavor_template: "CW flavor"
              - id: gcw_shape
                trigger: { type: bar }
                headline: "GCW headline"
                fires_once: true
                narrative_event_type: imperial_crackdown
                duration_minutes: 60
        """)
        self.assertEqual(dc.report.errors, [])
        self.assertEqual(len(dc.milestone_events), 2)

    def test_director_config_milestone_preserves_raw_for_either_shape(self):
        dc = self._load("""
            schema_version: 1
            valid_factions: [a]
            zone_baselines: {}
            system_prompt: "..."
            milestone_events:
              - id: cw_one
                trigger: {}
                cooldown_hours: 12
                output_type: holonet_news
                flavor_template: "x"
              - id: gcw_one
                trigger: {}
                headline: "y"
                fires_once: false
                duration_minutes: 30
        """)
        cw, gcw = dc.milestone_events
        self.assertEqual(cw.cooldown_hours, 12)
        self.assertEqual(cw.output_type, "holonet_news")
        self.assertIsNone(cw.headline)
        self.assertIsNone(gcw.cooldown_hours)
        self.assertIsNone(gcw.output_type)
        self.assertEqual(gcw.headline, "y")
        self.assertEqual(gcw.fires_once, False)
        self.assertEqual(gcw.duration_minutes, 30)
        # raw dict preserves everything regardless of shape
        self.assertIn("headline", gcw.raw)
        self.assertIn("output_type", cw.raw)

    def test_director_config_influence_out_of_range_is_warning(self):
        dc = self._load("""
            schema_version: 1
            valid_factions: [a]
            influence_min: 0
            influence_max: 100
            zone_baselines:
              test: { a: 150 }
            system_prompt: "..."
        """)
        self.assertTrue(
            any("150" in w or "outside" in w for w in dc.report.warnings)
        )


# ══════════════════════════════════════════════════════════════════════════════
# Ambient pools validator coverage
# ══════════════════════════════════════════════════════════════════════════════


class TestAmbientPoolsValidator(unittest.TestCase):
    def _load(self, body: str) -> AmbientPools:
        with TemporaryDirectory() as td:
            era_dir = _make_minimal_era(Path(td), with_ambient=body)
            m = load_era_manifest(era_dir)
            return load_ambient_pools(m)

    def test_ambient_string_lines_coerce_to_default_weight(self):
        ap = self._load("""
            schema_version: 1
            ambient_events:
              cantina:
                - "A bare string line."
        """)
        self.assertEqual(ap.report.errors, [])
        self.assertEqual(len(ap.pools["cantina"]), 1)
        self.assertEqual(ap.pools["cantina"][0].text, "A bare string line.")
        self.assertEqual(ap.pools["cantina"][0].weight, 1.0)

    def test_ambient_negative_weight_is_warning(self):
        ap = self._load("""
            schema_version: 1
            ambient_events:
              cantina:
                - text: "Will never trigger."
                  weight: -1.0
        """)
        self.assertEqual(ap.report.errors, [])
        self.assertTrue(
            any("never trigger" in w for w in ap.report.warnings),
            f"expected weight warning; warnings={ap.report.warnings}"
        )

    def test_ambient_missing_text_is_error(self):
        ap = self._load("""
            schema_version: 1
            ambient_events:
              cantina:
                - weight: 1.0
        """)
        self.assertTrue(any("text" in e for e in ap.report.errors))

    def test_ambient_top_level_must_be_mapping_raises(self):
        with self.assertRaises(WorldLoadError):
            self._load("""
                schema_version: 1
                ambient_events:
                  - just_a_list
            """)


if __name__ == "__main__":
    unittest.main()
