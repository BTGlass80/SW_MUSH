# -*- coding: utf-8 -*-
"""
tests/test_era_additions_loader.py — TD.AMBIENT_ERA_ADDITIONS_DEAD fix

Covers the _load_era_additions() helper and the era_additions APPEND
integration inside get_ambient_pools().

The 29 CW cantina/spaceport/streets/shops/jabba/government war-flavored
lines in data/worlds/clone_wars/ambient_events.yaml era_additions: section
were authored but never fired (the loader only read ambient_events:).
_load_era_additions() reads that section and get_ambient_pools() APPENDs
the lines to the merged pool instead of replacing them.
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
    _load_era_additions,
    AmbientLineTuple,
)

# The CW ambient file is at this path on disk.
_CW_AMBIENT = (
    Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" / "ambient_events.yaml"
)
# Generic pool keys carried by era_additions in the live CW file.
_CW_ADDITION_KEYS = {"cantina", "spaceport", "streets", "shops", "jabba", "government"}


class TestLoadEraAdditionsHelper(unittest.TestCase):
    def test_returns_empty_for_none_path(self):
        self.assertEqual(_load_era_additions(None), {})

    def test_returns_empty_for_missing_file(self):
        self.assertEqual(_load_era_additions(Path("/nonexistent/path.yaml")), {})

    def test_returns_empty_when_no_era_additions_key(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "no_additions.yaml"
            p.write_text("ambient_events:\n  cantina:\n    - text: 'hi'\n")
            self.assertEqual(_load_era_additions(p), {})

    def test_returns_empty_when_era_additions_not_a_mapping(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "bad.yaml"
            p.write_text("era_additions:\n  - just a list\n")
            self.assertEqual(_load_era_additions(p), {})

    def test_parses_string_entries(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "additions.yaml"
            p.write_text(textwrap.dedent("""
                era_additions:
                  cantina:
                    - text: "Clone trooper on leave"
                    - text: "War news on muted holovid"
            """).lstrip())
            result = _load_era_additions(p)
            self.assertIn("cantina", result)
            self.assertEqual(len(result["cantina"]), 2)
            self.assertEqual(result["cantina"][0].text, "Clone trooper on leave")
            self.assertAlmostEqual(result["cantina"][0].weight, 1.0)

    def test_parses_weighted_entries(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "weighted.yaml"
            p.write_text(textwrap.dedent("""
                era_additions:
                  spaceport:
                    - text: "Republic transport lands"
                      weight: 0.6
                    - text: "Droids check manifests"
            """).lstrip())
            result = _load_era_additions(p)
            self.assertIn("spaceport", result)
            self.assertAlmostEqual(result["spaceport"][0].weight, 0.6)
            self.assertAlmostEqual(result["spaceport"][1].weight, 1.0)

    def test_skips_entry_missing_text_key(self):
        with TemporaryDirectory() as td:
            p = Path(td) / "bad_entry.yaml"
            p.write_text(textwrap.dedent("""
                era_additions:
                  streets:
                    - weight: 0.5
                    - text: "Valid line"
            """).lstrip())
            result = _load_era_additions(p)
            self.assertEqual(len(result["streets"]), 1)
            self.assertEqual(result["streets"][0].text, "Valid line")

    def test_live_cw_file_has_expected_addition_keys(self):
        if not _CW_AMBIENT.is_file():
            self.skipTest("live CW ambient file not present")
        result = _load_era_additions(_CW_AMBIENT)
        self.assertTrue(
            result,
            "CW ambient file should have a non-empty era_additions section",
        )
        missing = _CW_ADDITION_KEYS - set(result.keys())
        self.assertFalse(
            missing,
            f"era_additions missing expected keys: {missing}",
        )

    def test_live_cw_cantina_additions_count(self):
        if not _CW_AMBIENT.is_file():
            self.skipTest("live CW ambient file not present")
        result = _load_era_additions(_CW_AMBIENT)
        self.assertGreaterEqual(
            len(result.get("cantina", [])), 5,
            "CW cantina era_additions should have at least 5 authored lines",
        )


class TestGetAmbientPoolsEraAdditionsIntegration(unittest.TestCase):
    """get_ambient_pools() APPENDS era_additions to the merged pool."""

    def _make_worlds_root(self, td, era_yaml_content, legacy_yaml_content=""):
        """Create a synthetic worlds_root with a single era and optional legacy."""
        worlds_root = Path(td) / "worlds"
        era_dir = worlds_root / "test_era"
        era_dir.mkdir(parents=True)
        # era YAML
        (era_dir / "ambient_events.yaml").write_text(era_yaml_content)
        # era.yaml + minimal zones.yaml so load_era_manifest validates
        (era_dir / "zones.yaml").write_text("zones: []\n")
        era_text = textwrap.dedent("""
            schema_version: 1
            era:
              code: test_era
              name: Test Era
              tagline: ''
              description: ''
            content_refs:
              zones: zones.yaml
              ambient_events: ambient_events.yaml
        """).lstrip()
        (era_dir / "era.yaml").write_text(era_text)
        # optional legacy
        if legacy_yaml_content:
            legacy_path = Path(td) / "legacy.yaml"
            legacy_path.write_text(legacy_yaml_content)
        else:
            legacy_path = Path(td) / "legacy_absent.yaml"  # does not exist
        return worlds_root, legacy_path

    def test_era_additions_appended_not_replacing(self):
        """Legacy cantina lines survive; era_additions are appended after them."""
        with TemporaryDirectory() as td:
            worlds_root, legacy_path = self._make_worlds_root(
                td,
                era_yaml_content=textwrap.dedent("""
                    schema_version: 1
                    ambient_events:
                      senate_district:
                        - text: "CW-only zone line"
                    era_additions:
                      cantina:
                        - text: "CW cantina addition"
                """).lstrip(),
                legacy_yaml_content=textwrap.dedent("""
                    cantina:
                      - text: "Legacy cantina line A"
                      - text: "Legacy cantina line B"
                """).lstrip(),
            )
            merged = get_ambient_pools(
                "test_era",
                worlds_root=worlds_root,
                legacy_path=legacy_path,
            )
            cantina = merged.pools.get("cantina", [])
            texts = [ln.text for ln in cantina]
            self.assertIn("Legacy cantina line A", texts, "legacy line must survive")
            self.assertIn("Legacy cantina line B", texts, "legacy line must survive")
            self.assertIn("CW cantina addition", texts, "era_addition must be appended")
            # Append: addition comes AFTER legacy lines
            legacy_idx = max(i for i, t in enumerate(texts) if "Legacy" in t)
            addition_idx = texts.index("CW cantina addition")
            self.assertGreater(addition_idx, legacy_idx,
                               "era_addition should appear after legacy lines")

    def test_era_additions_key_not_in_legacy_creates_new_entry(self):
        with TemporaryDirectory() as td:
            worlds_root, legacy_path = self._make_worlds_root(
                td,
                era_yaml_content=textwrap.dedent("""
                    schema_version: 1
                    ambient_events:
                      some_cw_zone:
                        - text: "CW zone line"
                    era_additions:
                      newkey:
                        - text: "Addition for new key"
                """).lstrip(),
                legacy_yaml_content="shops:\n  - text: 'shops line'\n",
            )
            merged = get_ambient_pools(
                "test_era",
                worlds_root=worlds_root,
                legacy_path=legacy_path,
            )
            self.assertIn("newkey", merged.pools)
            self.assertEqual(merged.pools["newkey"][0].text, "Addition for new key")

    def test_era_additions_absent_leaves_legacy_unchanged(self):
        with TemporaryDirectory() as td:
            worlds_root, legacy_path = self._make_worlds_root(
                td,
                era_yaml_content=textwrap.dedent("""
                    schema_version: 1
                    ambient_events:
                      some_zone:
                        - text: "era zone line"
                """).lstrip(),
                legacy_yaml_content="cantina:\n  - text: 'legacy only'\n",
            )
            merged = get_ambient_pools(
                "test_era",
                worlds_root=worlds_root,
                legacy_path=legacy_path,
            )
            cantina = merged.pools.get("cantina", [])
            self.assertEqual(len(cantina), 1)
            self.assertEqual(cantina[0].text, "legacy only")

    def test_era_additions_count_in_meta(self):
        with TemporaryDirectory() as td:
            worlds_root, legacy_path = self._make_worlds_root(
                td,
                era_yaml_content=textwrap.dedent("""
                    schema_version: 1
                    ambient_events:
                      zone_a:
                        - text: "era zone"
                    era_additions:
                      cantina:
                        - text: "addition 1"
                        - text: "addition 2"
                      spaceport:
                        - text: "spaceport addition"
                """).lstrip(),
            )
            merged = get_ambient_pools(
                "test_era",
                worlds_root=worlds_root,
                legacy_path=legacy_path,
            )
            self.assertEqual(merged.raw_meta.get("era_additions_count"), 3)
            self.assertIn("cantina", merged.raw_meta.get("era_additions_keys", []))
            self.assertIn("spaceport", merged.raw_meta.get("era_additions_keys", []))

    def test_live_cw_cantina_grows_with_era_additions(self):
        """Live CW merge: cantina pool is larger than legacy-only cantina pool."""
        if not _CW_AMBIENT.is_file():
            self.skipTest("live CW ambient file not present")
        legacy_path = Path(PROJECT_ROOT) / "data" / "ambient_events.yaml"
        if not legacy_path.is_file():
            self.skipTest("data/ambient_events.yaml not present")

        legacy_only = get_ambient_pools(None, legacy_path=legacy_path)
        cw_merged = get_ambient_pools("clone_wars")

        legacy_cantina_count = len(legacy_only.pools.get("cantina", []))
        cw_cantina_count = len(cw_merged.pools.get("cantina", []))
        self.assertGreater(
            cw_cantina_count,
            legacy_cantina_count,
            "CW merge should add era_additions cantina lines on top of legacy",
        )

    def test_live_cw_era_additions_meta(self):
        """Live CW merge: raw_meta tracks era_additions_count > 0."""
        if not _CW_AMBIENT.is_file():
            self.skipTest("live CW ambient file not present")
        merged = get_ambient_pools("clone_wars")
        self.assertGreater(
            merged.raw_meta.get("era_additions_count", 0),
            0,
            "CW merged pool should report >0 era_additions lines in meta",
        )


if __name__ == "__main__":
    unittest.main()
