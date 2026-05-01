# -*- coding: utf-8 -*-
"""
tests/test_f6a3_director_config_loader.py — Drop F.6a.3 (seam-only) tests
+ F.6a.7 Phase 2 updates (legacy literals deleted; era=None now defaults
to GCW YAML).

Exercises engine/director_config_loader.py:
    get_director_runtime_config(era=None)        -> defaults to "gcw" YAML
    get_director_runtime_config(era="gcw")       -> GCW YAML
    get_director_runtime_config(era="clone_wars") -> CW YAML
    get_director_runtime_config(era="bogus")     -> empty config + ERROR log
    apply_rewicker(cfg, "imperial")              -> "republic" on CW
    apply_zone_rewicker(cfg, "spaceport")        -> CW zone

Pre-F.6a.7 Phase 2, era=None returned hardcoded in-Python literals
(_LEGACY_VALID_FACTIONS / _LEGACY_DEFAULT_INFLUENCE / _LEGACY_SYSTEM_PROMPT).
Phase 2 deleted those literals; the era=None path now defaults to "gcw"
and loads from data/worlds/gcw/director_config.yaml. Test names that
referenced "legacy_path" still exist for git-blame continuity but their
assertions now describe yaml-gcw behavior.
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
)


# ══════════════════════════════════════════════════════════════════════════════
# era=None default path (post-F.6a.7 Phase 2: defaults to GCW YAML)
# ══════════════════════════════════════════════════════════════════════════════


class TestLegacyPath(unittest.TestCase):
    """Pre-F.6a.7 Phase 2 these were the 'legacy hardcoded constants'
    tests; Phase 2 deleted the constants. era=None now defaults to
    'gcw' and sources data from data/worlds/gcw/director_config.yaml.
    Assertions updated to match the new contract.

    Class name kept as TestLegacyPath for git-blame continuity. The
    'legacy' label in test names refers to the era=None API call shape,
    not to in-Python data."""

    def setUp(self):
        # The data/worlds/gcw/director_config.yaml file is required for
        # the post-Phase-2 era=None path to return useful data.
        gcw_dir = Path(PROJECT_ROOT) / "data" / "worlds" / "gcw"
        if not (gcw_dir / "director_config.yaml").is_file():
            self.skipTest("data/worlds/gcw/director_config.yaml not present")

    def test_legacy_path_returns_hardcoded_constants(self):
        """era=None now resolves via the YAML path with era='gcw' default."""
        cfg = get_director_runtime_config(None)
        self.assertEqual(cfg.source, "yaml-gcw")
        self.assertIsInstance(cfg.valid_factions, frozenset)
        # GCW YAML has the canonical 4 director-axis factions
        self.assertEqual(cfg.valid_factions,
                         frozenset({"imperial", "rebel", "criminal", "independent"}))
        # YAML-sourced GCW config has empty rewicker maps (no translation needed)
        self.assertEqual(cfg.rewicker_factions, {})
        self.assertEqual(cfg.rewicker_zones, {})

    def test_legacy_path_valid_factions_match_director_constants(self):
        """The seam's era=None default must match engine/director.py's
        VALID_FACTIONS frozenset exactly. Drift between them would
        cause Director behavior to silently change between import-time
        and runtime config resolution.
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
        """Post-F.6a.7 Phase 2: source label is now 'yaml-gcw' for the
        era=None default path (was 'legacy' pre-Phase-2)."""
        self.assertEqual(get_director_runtime_config(None).source, "yaml-gcw")


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
        """Pre-F.6a.7 Phase 2 this asserted the GCW YAML matched the
        in-Python _LEGACY_VALID_FACTIONS literal. Phase 2 deleted the
        literal; the assertion now fixes the canonical 4-faction shape
        directly. Same gate, different anchor.
        """
        cfg = get_director_runtime_config("gcw")
        self.assertEqual(
            cfg.valid_factions,
            frozenset({"imperial", "rebel", "criminal", "independent"}),
        )

    def test_gcw_zone_baselines_match_legacy_byte_equivalence(self):
        """The GCW YAML's zone_baselines must contain the canonical 6
        Mos Eisley zones with the historically-fixed influence numbers.
        Pre-F.6a.7 Phase 2 this compared against _LEGACY_DEFAULT_INFLUENCE;
        post-Phase-2 the expected shape is inlined."""
        expected = {
            "spaceport":  {"imperial": 65, "rebel": 8,  "criminal": 45, "independent": 25},
            "streets":    {"imperial": 55, "rebel": 12, "criminal": 50, "independent": 35},
            "cantina":    {"imperial": 40, "rebel": 15, "criminal": 65, "independent": 40},
            "shops":      {"imperial": 50, "rebel": 10, "criminal": 55, "independent": 40},
            "jabba":      {"imperial": 20, "rebel": 5,  "criminal": 85, "independent": 10},
            "government": {"imperial": 80, "rebel": 5,  "criminal": 20, "independent": 20},
        }
        cfg = get_director_runtime_config("gcw")
        self.assertEqual(set(cfg.zone_baselines), set(expected))
        for zk in expected:
            self.assertEqual(cfg.zone_baselines[zk], expected[zk])


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
    """Pre-F.6a.7 Phase 2: an unknown era fell back to the in-Python
    legacy constants. Post-Phase-2: an unknown era logs an ERROR and
    returns an _empty_config() with a descriptive source label.

    The contract changed deliberately: a missing/broken YAML for a
    real era is a real boot misconfiguration that should fail loud,
    not silently mask itself with stale data."""

    def test_unknown_era_falls_back_to_legacy(self):
        """Test name preserved for git-blame; assertion describes new contract."""
        cfg = get_director_runtime_config("nonexistent_era_xyz")
        # Source label is now descriptive of the failure mode (no in-Python data)
        self.assertTrue(
            cfg.source.startswith("yaml-nonexistent_era_xyz"),
            f"unexpected source label for unknown era: {cfg.source!r}",
        )
        # Valid_factions is empty (no in-Python literals to fall back to)
        self.assertEqual(cfg.valid_factions, frozenset())
        # Zone baselines empty too
        self.assertEqual(cfg.zone_baselines, {})

    def test_unknown_era_source_label_is_descriptive(self):
        """The empty-config source label should describe the failure
        mode so operators can diagnose."""
        cfg = get_director_runtime_config("nonexistent_era_xyz")
        # Should be one of: yaml-<era>-load-failed / -no-content / -validation-failed
        self.assertIn(
            cfg.source,
            {
                "yaml-nonexistent_era_xyz-load-failed",
                "yaml-nonexistent_era_xyz-no-content",
                "yaml-nonexistent_era_xyz-validation-failed",
            },
        )


# ══════════════════════════════════════════════════════════════════════════════
# Rewicker helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestRewickerHelpers(unittest.TestCase):
    def test_apply_rewicker_passthrough_on_unknown(self):
        # era=None defaults to GCW, which has empty rewicker maps
        cfg = get_director_runtime_config(None)
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
        # era=None defaults to GCW, which has empty rewicker maps
        cfg = get_director_runtime_config(None)
        self.assertEqual(apply_zone_rewicker(cfg, "spaceport"), "spaceport")


# ══════════════════════════════════════════════════════════════════════════════
# Mutability — caller mustn't be able to corrupt cached state
# ══════════════════════════════════════════════════════════════════════════════


class TestMutability(unittest.TestCase):
    def test_runtime_config_is_safe_to_mutate(self):
        """Two successive calls produce independent zone_baselines dicts.

        If a caller mutates one returned config's zone_baselines, the
        next call should NOT see the mutation. Post-F.6a.7 Phase 2,
        each call freshly loads from YAML so mutation isolation is
        intrinsic; pre-Phase-2 the seam had to deep-copy from the
        in-Python _LEGACY_DEFAULT_INFLUENCE dict.
        """
        gcw_dir = Path(PROJECT_ROOT) / "data" / "worlds" / "gcw"
        if not (gcw_dir / "director_config.yaml").is_file():
            self.skipTest("data/worlds/gcw/director_config.yaml not present")
        a = get_director_runtime_config(None)
        a.zone_baselines["spaceport"]["imperial"] = -999
        b = get_director_runtime_config(None)
        self.assertEqual(b.zone_baselines["spaceport"]["imperial"], 65,
                         "GCW YAML data was corrupted by caller mutation — "
                         "the seam should not share state across calls")


if __name__ == "__main__":
    unittest.main()
