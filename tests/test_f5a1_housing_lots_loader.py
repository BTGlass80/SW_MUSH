# -*- coding: utf-8 -*-
"""
tests/test_f5a1_housing_lots_loader.py — F.5a.1 housing lots loader tests

Per cw_housing_design_v1.md §11 (the housing_lots.yaml schema) and §12B.6
(F.5 sub-decomposition: F.5a.1 ships YAML authoring + GCW parity).

This drop ships:
  - data/worlds/gcw/housing_lots.yaml         (parity extraction of
                                                FACTION_QUARTER_TIERS GCW)
  - data/worlds/clone_wars/housing_lots.yaml  (CW additions: republic/cis/
                                                jedi_order/hutt_cartel +
                                                bounty_hunters_guild=null)
  - engine/world_loader.py::load_housing_lots (minimal loader)

What's tested:
  - Both YAMLs parse cleanly with zero errors/warnings
  - The loaded data is byte-equivalent to the live in-Python
    FACTION_QUARTER_TIERS for the matching factions (the regression
    gate that F.5b's data-fy refactor will rely on)
  - Schema invariants (non-negative rank_min, required fields present,
    sorted ascending)
  - BHG=null handling (CW design §5.5 — BHG explicitly has no quarters)

What's NOT tested:
  - T1/T3/T4/T5 inventory (comes in F.5a.2)
  - The data-fy refactor of FACTION_QUARTER_TIERS (comes in F.5b)
  - Live engine consumption (comes in F.5b)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. Loader basics — both YAMLs load cleanly
# ──────────────────────────────────────────────────────────────────────


class TestLoaderBasics(unittest.TestCase):
    """Both era YAMLs parse cleanly via load_housing_lots, no errors,
    no warnings."""

    def _load(self, era: str):
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(Path(PROJECT_ROOT) / "data" / "worlds" / era)
        return load_housing_lots(manifest)

    def test_gcw_loads_cleanly(self):
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "housing_lots.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/housing_lots.yaml not present")
        corpus = self._load("gcw")
        self.assertIsNotNone(corpus, "GCW housing_lots should load")
        self.assertEqual(corpus.era, "gcw")
        self.assertEqual(corpus.schema_version, 1)
        self.assertEqual(corpus.report.errors, [],
                         f"GCW load produced errors: {corpus.report.errors}")
        self.assertEqual(corpus.report.warnings, [],
                         f"GCW load produced warnings: {corpus.report.warnings}")

    def test_clone_wars_loads_cleanly(self):
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "housing_lots.yaml")
        if not cw_yaml.is_file():
            self.skipTest("data/worlds/clone_wars/housing_lots.yaml not present")
        corpus = self._load("clone_wars")
        self.assertIsNotNone(corpus, "CW housing_lots should load")
        self.assertEqual(corpus.era, "clone_wars")
        self.assertEqual(corpus.schema_version, 1)
        self.assertEqual(corpus.report.errors, [],
                         f"CW load produced errors: {corpus.report.errors}")
        self.assertEqual(corpus.report.warnings, [],
                         f"CW load produced warnings: {corpus.report.warnings}")


# ──────────────────────────────────────────────────────────────────────
# 2. GCW byte-equivalence — the regression gate for F.5b's data-fy
# ──────────────────────────────────────────────────────────────────────


class TestGCWByteEquivalence(unittest.TestCase):
    """The GCW YAML must mirror engine.housing.FACTION_QUARTER_TIERS
    byte-for-byte for the GCW factions (empire, rebel, hutt). This is
    the gate F.5b's data-fy refactor will use to prove it doesn't
    regress live behavior."""

    @classmethod
    def setUpClass(cls):
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "housing_lots.yaml")
        if not gcw_yaml.is_file():
            cls._skip = "data/worlds/gcw/housing_lots.yaml not present"
            return
        cls._skip = None
        from engine.world_loader import (
            load_era_manifest, load_housing_lots,
        )
        manifest = load_era_manifest(Path(PROJECT_ROOT) / "data" / "worlds" / "gcw")
        cls.corpus = load_housing_lots(manifest)

        from engine.housing import FACTION_QUARTER_TIERS
        cls.live = FACTION_QUARTER_TIERS

    def setUp(self):
        if self._skip:
            self.skipTest(self._skip)

    def test_gcw_factions_present(self):
        """All three GCW factions in the live data are present in the
        YAML."""
        for fc in ("empire", "rebel", "hutt"):
            self.assertIn(fc, self.corpus.tier2_faction_quarters,
                          f"GCW faction {fc!r} missing from YAML")

    def test_gcw_tier_ranks_match_live(self):
        """For each GCW faction, the rank_min set in the YAML matches
        the (faction, rank) keys in the live FACTION_QUARTER_TIERS."""
        for fc in ("empire", "rebel", "hutt"):
            yaml_ranks = sorted(
                t.rank_min
                for t in self.corpus.tier2_faction_quarters[fc].tiers
            )
            live_ranks = sorted(r for (f, r) in self.live if f == fc)
            self.assertEqual(
                yaml_ranks, live_ranks,
                f"{fc} ranks diverge: yaml={yaml_ranks} live={live_ranks}",
            )

    def test_gcw_tier_fields_match_live(self):
        """For each (faction, rank) in the live data, the YAML's
        corresponding tier has identical label/storage_max/room_name/
        room_desc."""
        for fc in ("empire", "rebel", "hutt"):
            yaml_tiers_by_rank = {
                t.rank_min: t
                for t in self.corpus.tier2_faction_quarters[fc].tiers
            }
            for (live_fc, rank), live_cfg in self.live.items():
                if live_fc != fc:
                    continue
                yaml_t = yaml_tiers_by_rank.get(rank)
                self.assertIsNotNone(
                    yaml_t,
                    f"{fc} rank={rank} present in live data but missing from YAML",
                )
                self.assertEqual(yaml_t.label, live_cfg["label"],
                                 f"{fc}/{rank} label mismatch")
                self.assertEqual(yaml_t.storage_max, live_cfg["storage_max"],
                                 f"{fc}/{rank} storage_max mismatch")
                self.assertEqual(yaml_t.room_name, live_cfg["room_name"],
                                 f"{fc}/{rank} room_name mismatch")
                self.assertEqual(yaml_t.room_desc, live_cfg["room_desc"],
                                 f"{fc}/{rank} room_desc mismatch")

    def test_gcw_yaml_does_not_include_cw_factions(self):
        """The GCW YAML is GCW-only; CW factions live in the CW YAML."""
        for cw_fc in ("republic", "cis", "jedi_order", "hutt_cartel",
                      "bounty_hunters_guild"):
            self.assertNotIn(
                cw_fc, self.corpus.tier2_faction_quarters,
                f"GCW YAML should not contain CW faction {cw_fc!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# 3. CW byte-equivalence — same gate for the CW additions
# ──────────────────────────────────────────────────────────────────────


class TestCWByteEquivalence(unittest.TestCase):
    """The CW YAML must mirror the CW additions in
    engine.housing.FACTION_QUARTER_TIERS (republic/cis/jedi_order/
    hutt_cartel) byte-for-byte. BHG is null in YAML and absent from the
    live dict."""

    @classmethod
    def setUpClass(cls):
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "housing_lots.yaml")
        if not cw_yaml.is_file():
            cls._skip = "data/worlds/clone_wars/housing_lots.yaml not present"
            return
        cls._skip = None
        from engine.world_loader import (
            load_era_manifest, load_housing_lots,
        )
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"
        )
        cls.corpus = load_housing_lots(manifest)

        from engine.housing import FACTION_QUARTER_TIERS
        cls.live = FACTION_QUARTER_TIERS

    def setUp(self):
        if self._skip:
            self.skipTest(self._skip)

    def test_cw_factions_present(self):
        """All four CW non-BHG factions plus BHG (null) are in the YAML."""
        expected = {"republic", "cis", "jedi_order", "hutt_cartel",
                    "bounty_hunters_guild"}
        actual = set(self.corpus.tier2_faction_quarters.keys())
        self.assertEqual(actual, expected,
                         f"CW factions diverge: {actual ^ expected}")

    def test_bhg_has_no_tiers(self):
        """BHG is explicitly nullable per design §5.5; loader maps null
        to FactionQuartersConfig(tiers=[])."""
        bhg = self.corpus.tier2_faction_quarters["bounty_hunters_guild"]
        self.assertEqual(bhg.tiers, [],
                         "BHG should have no tiers per design §5.5")

    def test_cw_tier_ranks_match_live(self):
        """For each CW faction in the live data, the rank_min set in
        the YAML matches."""
        for fc in ("republic", "cis", "jedi_order", "hutt_cartel"):
            yaml_ranks = sorted(
                t.rank_min
                for t in self.corpus.tier2_faction_quarters[fc].tiers
            )
            live_ranks = sorted(r for (f, r) in self.live if f == fc)
            self.assertEqual(
                yaml_ranks, live_ranks,
                f"{fc} ranks diverge: yaml={yaml_ranks} live={live_ranks}",
            )

    def test_cw_tier_fields_match_live(self):
        """For each (faction, rank) CW tier in the live data, the YAML
        tier has identical fields."""
        for fc in ("republic", "cis", "jedi_order", "hutt_cartel"):
            yaml_tiers_by_rank = {
                t.rank_min: t
                for t in self.corpus.tier2_faction_quarters[fc].tiers
            }
            for (live_fc, rank), live_cfg in self.live.items():
                if live_fc != fc:
                    continue
                yaml_t = yaml_tiers_by_rank.get(rank)
                self.assertIsNotNone(
                    yaml_t,
                    f"{fc} rank={rank} present in live but missing from YAML",
                )
                self.assertEqual(yaml_t.label, live_cfg["label"])
                self.assertEqual(yaml_t.storage_max, live_cfg["storage_max"])
                self.assertEqual(yaml_t.room_name, live_cfg["room_name"])
                self.assertEqual(yaml_t.room_desc, live_cfg["room_desc"])

    def test_cw_yaml_does_not_include_gcw_factions(self):
        """The CW YAML is CW-only; GCW factions live in the GCW YAML."""
        for gcw_fc in ("empire", "rebel", "hutt"):
            self.assertNotIn(
                gcw_fc, self.corpus.tier2_faction_quarters,
                f"CW YAML should not contain GCW faction {gcw_fc!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# 4. Schema invariants — loader rejects bad shapes
# ──────────────────────────────────────────────────────────────────────


class TestLoaderSchemaInvariants(unittest.TestCase):
    """The loader collects errors for missing required fields, bad
    types, and malformed structure — not crashes."""

    def _make_temp_manifest(self, td: Path, era_yaml: str,
                            housing_yaml: str):
        """Build a minimal era manifest pointing at the given YAML."""
        era_dir = td / "stub_era"
        era_dir.mkdir(parents=True, exist_ok=True)
        (era_dir / "era.yaml").write_text(era_yaml)
        (era_dir / "zones.yaml").write_text("zones: {}\n")
        (era_dir / "housing_lots.yaml").write_text(housing_yaml)
        from engine.world_loader import load_era_manifest
        return load_era_manifest(era_dir)

    def test_missing_required_field_logs_error(self):
        import tempfile
        import textwrap
        from engine.world_loader import load_housing_lots

        era_yaml = textwrap.dedent("""
            schema_version: 1
            era:
              code: stub
              name: "Stub"
            content_refs:
              zones: zones.yaml
              housing_lots: housing_lots.yaml
              planets: []
              wilderness: []
        """).lstrip("\n")
        bad_housing = textwrap.dedent("""
            schema_version: 1
            era: stub
            tier2_faction_quarters:
              empire:
                tiers:
                  - rank_min: 0
                    # label missing
                    storage_max: 10
                    room_name: "Bunk"
                    room_desc: "..."
        """).lstrip("\n")
        with tempfile.TemporaryDirectory() as td:
            manifest = self._make_temp_manifest(Path(td), era_yaml,
                                                bad_housing)
            corpus = load_housing_lots(manifest)
            self.assertIsNotNone(corpus)
            self.assertGreater(len(corpus.report.errors), 0,
                               "missing field should log an error")
            self.assertTrue(
                any("missing required field" in e for e in corpus.report.errors),
                f"errors do not mention missing field: {corpus.report.errors}",
            )

    def test_negative_rank_min_logs_error(self):
        import tempfile
        import textwrap
        from engine.world_loader import load_housing_lots

        era_yaml = textwrap.dedent("""
            schema_version: 1
            era: { code: stub, name: "Stub" }
            content_refs:
              zones: zones.yaml
              housing_lots: housing_lots.yaml
              planets: []
              wilderness: []
        """).lstrip("\n")
        bad_housing = textwrap.dedent("""
            schema_version: 1
            era: stub
            tier2_faction_quarters:
              empire:
                tiers:
                  - rank_min: -1
                    label: "x"
                    storage_max: 10
                    room_name: "x"
                    room_desc: "x"
        """).lstrip("\n")
        with tempfile.TemporaryDirectory() as td:
            manifest = self._make_temp_manifest(Path(td), era_yaml,
                                                bad_housing)
            corpus = load_housing_lots(manifest)
            self.assertGreater(len(corpus.report.errors), 0)
            self.assertTrue(
                any("rank_min" in e for e in corpus.report.errors),
                f"errors do not mention rank_min: {corpus.report.errors}",
            )

    def test_no_housing_lots_content_ref_returns_none(self):
        """When the manifest has no housing_lots content_ref, loader
        returns None (the design's "no housing yet" path)."""
        import tempfile
        import textwrap
        from engine.world_loader import load_era_manifest, load_housing_lots

        era_yaml = textwrap.dedent("""
            schema_version: 1
            era: { code: stub, name: "Stub" }
            content_refs:
              zones: zones.yaml
              planets: []
              wilderness: []
        """).lstrip("\n")
        with tempfile.TemporaryDirectory() as td:
            era_dir = Path(td) / "stub"
            era_dir.mkdir()
            (era_dir / "era.yaml").write_text(era_yaml)
            (era_dir / "zones.yaml").write_text("zones: {}\n")
            manifest = load_era_manifest(era_dir)
            self.assertIsNone(manifest.housing_lots_path)
            corpus = load_housing_lots(manifest)
            self.assertIsNone(corpus,
                              "load_housing_lots should return None when "
                              "no housing_lots content_ref is declared")


# ──────────────────────────────────────────────────────────────────────
# 5. Sort invariants — tiers always sorted ascending
# ──────────────────────────────────────────────────────────────────────


class TestSortInvariants(unittest.TestCase):
    """Loader guarantees tiers are sorted by rank_min ascending,
    regardless of YAML author order."""

    def test_gcw_empire_tiers_sorted(self):
        gcw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "gcw" /
                    "housing_lots.yaml")
        if not gcw_yaml.is_file():
            self.skipTest("data/worlds/gcw/housing_lots.yaml not present")
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "gcw")
        corpus = load_housing_lots(manifest)
        empire_ranks = [t.rank_min for t in
                        corpus.tier2_faction_quarters["empire"].tiers]
        self.assertEqual(empire_ranks, sorted(empire_ranks),
                         "empire tiers must be ascending")

    def test_cw_jedi_tiers_sorted(self):
        cw_yaml = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
                   "housing_lots.yaml")
        if not cw_yaml.is_file():
            self.skipTest("data/worlds/clone_wars/housing_lots.yaml not present")
        from engine.world_loader import load_era_manifest, load_housing_lots
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars")
        corpus = load_housing_lots(manifest)
        jedi_ranks = [t.rank_min for t in
                      corpus.tier2_faction_quarters["jedi_order"].tiers]
        self.assertEqual(jedi_ranks, sorted(jedi_ranks),
                         "jedi_order tiers must be ascending")


if __name__ == "__main__":
    unittest.main()
