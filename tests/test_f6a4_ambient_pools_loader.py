# -*- coding: utf-8 -*-
"""
tests/test_f6a4_ambient_pools_loader.py — Drop F.6a.4 (seam-only) tests

Exercises engine/ambient_pools_loader.py:
    get_ambient_pools(None)            -> legacy-only
    get_ambient_pools("gcw")           -> yaml-gcw+legacy
    get_ambient_pools("clone_wars")    -> yaml-clone_wars+legacy
    get_ambient_pools("bogus")         -> legacy-only (era layer skipped)
    pick_pool_for_zone(merged, key)    -> resolves with default fallback
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

from engine.ambient_pools_loader import (  # noqa: E402
    get_ambient_pools,
    pick_pool_for_zone,
    AmbientLineTuple,
    MergedAmbientPools,
)


class TestLegacyOnlyPath(unittest.TestCase):
    def test_legacy_only_returns_real_pool_when_present(self):
        legacy = Path(PROJECT_ROOT) / "data" / "ambient_events.yaml"
        if not legacy.is_file():
            self.skipTest("data/ambient_events.yaml not present")
        m = get_ambient_pools(None)
        self.assertEqual(m.source, "legacy-only")
        self.assertGreater(len(m.pools), 0)
        # Sample zone key from the live legacy file
        self.assertTrue(
            any(zk in m.pools for zk in ("cantina", "spaceport", "default")),
            "legacy pool should contain at least one of the canonical keys"
        )

    def test_legacy_only_with_missing_file_returns_empty(self):
        with TemporaryDirectory() as td:
            fake_legacy = Path(td) / "does_not_exist.yaml"
            m = get_ambient_pools(None, legacy_path=fake_legacy)
            self.assertEqual(m.pools, {})
            self.assertEqual(m.source, "legacy-fallback")
            self.assertIsNone(m.legacy_path)


class TestGCWMergedPath(unittest.TestCase):
    def setUp(self):
        gcw = Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" / "ambient_events.yaml"
        if not gcw.is_file():
            self.skipTest("data/worlds/gcw/ambient_events.yaml not present")
        self.merged = get_ambient_pools("gcw")

    def test_gcw_source_label(self):
        # Whether we get yaml-gcw+legacy depends on whether the legacy file
        # exists; both labels are valid.
        self.assertIn(self.merged.source,
                      ("yaml-gcw+legacy", "legacy-only"))

    def test_gcw_pools_nonempty(self):
        self.assertGreater(len(self.merged.pools), 0)

    def test_gcw_merge_meta_is_present(self):
        self.assertIn("era", self.merged.raw_meta)
        self.assertEqual(self.merged.raw_meta["era"], "gcw")


class TestCloneWarsMergedPath(unittest.TestCase):
    def setUp(self):
        cw = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
              "ambient_events.yaml")
        if not cw.is_file():
            self.skipTest("data/worlds/clone_wars/ambient_events.yaml not present")
        self.merged = get_ambient_pools("clone_wars")

    def test_clone_wars_adds_new_zone_keys(self):
        # CW intentionally does NOT redefine the legacy generic keys.
        # Instead, it adds per-planet zones like coruscant_senate.
        cw_only_keys = [zk for zk in self.merged.pools
                        if zk.startswith("coruscant_") or zk.startswith("kuat_")]
        self.assertGreater(len(cw_only_keys), 0,
                           "CW should add per-planet zone keys")

    def test_clone_wars_preserves_legacy_keys(self):
        # The merge should not drop legacy keys (cantina, spaceport, etc.)
        # — CW serves them via the merged pool.
        legacy = Path(PROJECT_ROOT) / "data" / "ambient_events.yaml"
        if not legacy.is_file():
            self.skipTest("legacy ambient_events.yaml not present")
        # At least one of the canonical keys should still be there
        self.assertTrue(
            any(zk in self.merged.pools for zk in ("cantina", "spaceport")),
            "merged CW pool should preserve legacy keys not redefined by CW"
        )


class TestEraOverridesLegacyOnCollision(unittest.TestCase):
    """Synthetic test: when both layers define the same zone key, era wins."""

    def test_era_layer_wins_on_zone_key_collision(self):
        with TemporaryDirectory() as td:
            # Synthetic legacy file with one key
            legacy = Path(td) / "legacy.yaml"
            legacy.write_text(textwrap.dedent("""
                cantina:
                  - text: "LEGACY cantina line A"
                  - text: "LEGACY cantina line B"
                shops:
                  - text: "LEGACY shops line"
            """).lstrip("\n"))

            # Synthetic era directory that redefines `cantina`
            worlds_root = Path(td) / "worlds"
            era_dir = worlds_root / "synth_era"
            era_dir.mkdir(parents=True)
            (era_dir / "era.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                era:
                  code: synth_era
                  name: "Synthetic"
                content_refs:
                  zones: zones.yaml
                  ambient_events: ambient_events.yaml
                  planets: []
                  wilderness: []
            """).lstrip("\n"))
            (era_dir / "zones.yaml").write_text("zones: {}\n")
            (era_dir / "ambient_events.yaml").write_text(textwrap.dedent("""
                schema_version: 1
                ambient_events:
                  cantina:
                    - text: "ERA cantina override"
                  new_era_zone:
                    - text: "ERA-only zone"
            """).lstrip("\n"))

            merged = get_ambient_pools(
                "synth_era",
                worlds_root=worlds_root,
                legacy_path=legacy,
            )

            # Cantina: era wins (1 line, not 2)
            self.assertEqual(len(merged.pools["cantina"]), 1)
            self.assertEqual(merged.pools["cantina"][0].text,
                             "ERA cantina override")
            # Shops: legacy preserved (no era override)
            self.assertEqual(len(merged.pools["shops"]), 1)
            self.assertEqual(merged.pools["shops"][0].text,
                             "LEGACY shops line")
            # Era-only zone: present
            self.assertIn("new_era_zone", merged.pools)
            # Source label reflects the merge happened
            self.assertEqual(merged.source, "yaml-synth_era+legacy")
            # Collisions metadata
            self.assertIn("cantina", merged.raw_meta["collisions"])


class TestUnknownEraFallback(unittest.TestCase):
    def test_unknown_era_falls_back_to_legacy_layer(self):
        m = get_ambient_pools("nonexistent_era_xyz")
        # Legacy layer still loads; era layer is skipped
        self.assertIn(m.source, ("legacy-only", "legacy-fallback"))
        self.assertIsNone(m.era_path)


class TestBrokenLegacyPath(unittest.TestCase):
    def test_malformed_legacy_yaml_skips_legacy_layer_gracefully(self):
        with TemporaryDirectory() as td:
            broken = Path(td) / "broken.yaml"
            broken.write_text("this: is: not: valid: yaml: at: all:\n")
            m = get_ambient_pools(None, legacy_path=broken)
            # Returns empty pools, doesn't raise
            self.assertEqual(m.pools, {})

    def test_legacy_top_level_list_not_mapping_skips_layer(self):
        with TemporaryDirectory() as td:
            bad = Path(td) / "bad.yaml"
            bad.write_text("- just a list\n- not a mapping\n")
            m = get_ambient_pools(None, legacy_path=bad)
            self.assertEqual(m.pools, {})


class TestPickPoolForZone(unittest.TestCase):
    def test_pick_returns_zone_lines_when_present(self):
        m = MergedAmbientPools(pools={
            "cantina": [AmbientLineTuple("a"), AmbientLineTuple("b")],
            "default": [AmbientLineTuple("d")],
        })
        lines = pick_pool_for_zone(m, "cantina")
        self.assertEqual(len(lines), 2)

    def test_pick_falls_back_to_default_when_zone_missing(self):
        m = MergedAmbientPools(pools={
            "default": [AmbientLineTuple("d1"), AmbientLineTuple("d2")],
        })
        lines = pick_pool_for_zone(m, "missing_zone")
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0].text, "d1")

    def test_pick_returns_empty_when_neither_present(self):
        m = MergedAmbientPools(pools={"shops": [AmbientLineTuple("s")]})
        lines = pick_pool_for_zone(m, "missing_zone")
        self.assertEqual(lines, [])

    def test_pick_with_custom_fallback_key(self):
        m = MergedAmbientPools(pools={
            "fallback_zone": [AmbientLineTuple("f")],
        })
        lines = pick_pool_for_zone(m, "missing", fallback_zone_key="fallback_zone")
        self.assertEqual(len(lines), 1)


class TestWeightPreservation(unittest.TestCase):
    def test_weighted_lines_round_trip_through_merge(self):
        with TemporaryDirectory() as td:
            legacy = Path(td) / "legacy.yaml"
            legacy.write_text(textwrap.dedent("""
                cantina:
                  - text: "rare line"
                    weight: 0.2
                  - text: "common line"
            """).lstrip("\n"))
            m = get_ambient_pools(None, legacy_path=legacy)
            self.assertEqual(len(m.pools["cantina"]), 2)
            rare = m.pools["cantina"][0]
            self.assertAlmostEqual(rare.weight, 0.2)
            common = m.pools["cantina"][1]
            self.assertAlmostEqual(common.weight, 1.0)


if __name__ == "__main__":
    unittest.main()
