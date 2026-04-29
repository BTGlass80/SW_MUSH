# -*- coding: utf-8 -*-
"""
tests/test_f6a3_director_config_loader.py — Drop F.6a.3 (seam-only) tests

Exercises engine/director_config_loader.py:
    get_director_runtime_config(era=None)        -> legacy fallback
    get_director_runtime_config(era="gcw")       -> YAML
    get_director_runtime_config(era="clone_wars") -> YAML
    get_director_runtime_config(era="bogus")     -> legacy fallback (logged)
    apply_rewicker(cfg, "imperial")              -> "republic" on CW
    apply_zone_rewicker(cfg, "spaceport")        -> CW zone

Covers:
  - test_legacy_path_returns_hardcoded_constants
  - test_legacy_path_valid_factions_match_director_constants
  - test_legacy_path_zone_baselines_match_director_constants
  - test_gcw_yaml_path_returns_yaml_values
  - test_gcw_valid_factions_match_legacy_byte_equivalence
  - test_clone_wars_returns_six_factions
  - test_clone_wars_returns_thirty_plus_zones
  - test_clone_wars_rewicker_translates_imperial_to_republic
  - test_clone_wars_rewicker_zone_keys_translate
  - test_unknown_era_falls_back_to_legacy
  - test_apply_rewicker_passthrough_on_unknown
  - test_apply_rewicker_translates_when_present
  - test_apply_zone_rewicker_passthrough_on_unknown
  - test_legacy_source_label_is_legacy
  - test_yaml_source_label_includes_era
  - test_runtime_config_is_safe_to_mutate
"""
import os
import sys
import unittest
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.director_config_loader import (  # noqa: E402
    get_director_runtime_config,
    apply_rewicker,
    apply_zone_rewicker,
    DirectorRuntimeConfig,
    _LEGACY_VALID_FACTIONS,
    _LEGACY_DEFAULT_INFLUENCE,
)


# ══════════════════════════════════════════════════════════════════════════════
# Legacy path
# ══════════════════════════════════════════════════════════════════════════════


class TestLegacyPath(unittest.TestCase):
    def test_legacy_path_returns_hardcoded_constants(self):
        cfg = get_director_runtime_config(None)
        self.assertEqual(cfg.source, "legacy")
        self.assertIsInstance(cfg.valid_factions, frozenset)
        self.assertEqual(cfg.valid_factions, _LEGACY_VALID_FACTIONS)
        self.assertEqual(cfg.rewicker_factions, {})
        self.assertEqual(cfg.rewicker_zones, {})

    def test_legacy_path_valid_factions_match_director_constants(self):
        """The seam's legacy fallback must mirror engine/director.py's
        VALID_FACTIONS frozenset exactly. Drift between these two
        constants would cause the integration PR to silently change
        Director behavior.
        """
        from engine.director import VALID_FACTIONS as DIRECTOR_VF
        cfg = get_director_runtime_config(None)
        self.assertEqual(cfg.valid_factions, DIRECTOR_VF)

    def test_legacy_path_zone_baselines_match_director_constants(self):
        from engine.director import DEFAULT_INFLUENCE as DIRECTOR_DI
        cfg = get_director_runtime_config(None)
        # cfg.zone_baselines is a deep copy; compare values
        self.assertEqual(set(cfg.zone_baselines), set(DIRECTOR_DI))
        for zk in DIRECTOR_DI:
            self.assertEqual(cfg.zone_baselines[zk], DIRECTOR_DI[zk])

    def test_legacy_source_label_is_legacy(self):
        self.assertEqual(get_director_runtime_config(None).source, "legacy")


# ══════════════════════════════════════════════════════════════════════════════
# YAML path — GCW
# ══════════════════════════════════════════════════════════════════════════════


class TestGCWYamlPath(unittest.TestCase):
    def setUp(self):
        gcw_dir = Path(PROJECT_ROOT) / "data" / "worlds" / "gcw"
        if not (gcw_dir / "director_config.yaml").is_file():
            self.skipTest("data/worlds/gcw/director_config.yaml not present")

    def test_gcw_yaml_path_returns_yaml_values(self):
        cfg = get_director_runtime_config("gcw")
        self.assertEqual(cfg.source, "yaml-gcw")
        self.assertGreater(len(cfg.valid_factions), 0)
        self.assertGreater(len(cfg.zone_baselines), 0)

    def test_gcw_valid_factions_match_legacy_byte_equivalence(self):
        """The 6a.5 GCW counterpart YAML was authored to be byte-equivalent
        to the legacy hardcoded constants. This test gates the eventual
        flag-flip from legacy → YAML for the GCW era.
        """
        cfg = get_director_runtime_config("gcw")
        self.assertEqual(cfg.valid_factions, _LEGACY_VALID_FACTIONS)

    def test_gcw_zone_baselines_match_legacy_byte_equivalence(self):
        cfg = get_director_runtime_config("gcw")
        self.assertEqual(set(cfg.zone_baselines), set(_LEGACY_DEFAULT_INFLUENCE))
        for zk in _LEGACY_DEFAULT_INFLUENCE:
            self.assertEqual(cfg.zone_baselines[zk], _LEGACY_DEFAULT_INFLUENCE[zk])


# ══════════════════════════════════════════════════════════════════════════════
# YAML path — Clone Wars
# ══════════════════════════════════════════════════════════════════════════════


class TestCloneWarsYamlPath(unittest.TestCase):
    def setUp(self):
        cw_dir = Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"
        if not (cw_dir / "director_config.yaml").is_file():
            self.skipTest("data/worlds/clone_wars/director_config.yaml not present")
        self.cfg = get_director_runtime_config("clone_wars")

    def test_yaml_source_label_includes_era(self):
        self.assertEqual(self.cfg.source, "yaml-clone_wars")

    def test_clone_wars_returns_six_factions(self):
        self.assertEqual(len(self.cfg.valid_factions), 6,
                         f"CW should have 6 factions, got {self.cfg.valid_factions}")

    def test_clone_wars_returns_thirty_plus_zones(self):
        self.assertGreaterEqual(len(self.cfg.zone_baselines), 30)

    def test_clone_wars_rewicker_translates_imperial_to_republic(self):
        self.assertEqual(self.cfg.rewicker_factions.get("imperial"), "republic")
        self.assertEqual(apply_rewicker(self.cfg, "imperial"), "republic")
        self.assertEqual(apply_rewicker(self.cfg, "rebel"), "cis")

    def test_clone_wars_rewicker_zone_keys_translate(self):
        self.assertIn("spaceport", self.cfg.rewicker_zones)
        self.assertEqual(apply_zone_rewicker(self.cfg, "spaceport"),
                         self.cfg.rewicker_zones["spaceport"])


# ══════════════════════════════════════════════════════════════════════════════
# Fallback behavior — never raises
# ══════════════════════════════════════════════════════════════════════════════


class TestFallbackBehavior(unittest.TestCase):
    def test_unknown_era_falls_back_to_legacy(self):
        cfg = get_director_runtime_config("nonexistent_era_xyz")
        self.assertEqual(cfg.source, "legacy")
        self.assertEqual(cfg.valid_factions, _LEGACY_VALID_FACTIONS)


# ══════════════════════════════════════════════════════════════════════════════
# Rewicker helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestRewickerHelpers(unittest.TestCase):
    def test_apply_rewicker_passthrough_on_unknown(self):
        cfg = get_director_runtime_config(None)  # legacy → empty rewicker
        self.assertEqual(apply_rewicker(cfg, "anything"), "anything")

    def test_apply_rewicker_translates_when_present(self):
        # Use a synthetic config to avoid requiring CW data on this test
        cfg = DirectorRuntimeConfig(
            valid_factions=frozenset({"a", "b"}),
            zone_baselines={},
            system_prompt="...",
            rewicker_factions={"old": "new"},
            rewicker_zones={"oldzone": "newzone"},
        )
        self.assertEqual(apply_rewicker(cfg, "old"), "new")
        self.assertEqual(apply_rewicker(cfg, "other"), "other")

    def test_apply_zone_rewicker_passthrough_on_unknown(self):
        cfg = get_director_runtime_config(None)
        self.assertEqual(apply_zone_rewicker(cfg, "spaceport"), "spaceport")


# ══════════════════════════════════════════════════════════════════════════════
# Mutability — caller mustn't be able to corrupt cached state
# ══════════════════════════════════════════════════════════════════════════════


class TestMutability(unittest.TestCase):
    def test_runtime_config_is_safe_to_mutate(self):
        """Two successive calls produce independent zone_baselines dicts.

        If a caller mutates one returned config's zone_baselines, the
        next call should NOT see the mutation.
        """
        a = get_director_runtime_config(None)
        a.zone_baselines["spaceport"]["imperial"] = -999
        b = get_director_runtime_config(None)
        # The legacy module-level constant must not have been corrupted
        self.assertEqual(b.zone_baselines["spaceport"]["imperial"], 65,
                         "legacy DEFAULT_INFLUENCE was mutated by caller — "
                         "the seam needs to deep-copy")


if __name__ == "__main__":
    unittest.main()
