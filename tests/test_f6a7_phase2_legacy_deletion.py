# -*- coding: utf-8 -*-
"""
tests/test_f6a7_phase2_legacy_deletion.py — F.6a.7 Phase 2 tests.

F.6a.7 Phase 2 (Apr 29 2026) deleted the in-Python legacy fallback
constants and code paths that Phase 1 made unreached:

  In `engine/world_lore.py`:
    - SEED_ENTRIES (61-entry list literal, ~490 lines)

  In `engine/director_config_loader.py`:
    - _LEGACY_VALID_FACTIONS (frozenset)
    - _LEGACY_DEFAULT_INFLUENCE (dict)
    - _LEGACY_SYSTEM_PROMPT (multi-line string)
    - _legacy() factory function

After deletion, `seed_lore(db, era=None)` defaults to "gcw" and loads
from data/worlds/gcw/lore.yaml; same for
`get_director_runtime_config(era=None)`. YAML load failures log ERROR
and return either 0 entries (seed_lore) or an empty config
(get_director_runtime_config) with a descriptive `source` label —
no in-Python fallback.

Tests in this file are explicitly Phase 2 deletion guards. The broader
behavioral coverage lives in:
  - tests/test_f6a2_world_lore_yaml.py (Phase 2 contract for seed_lore)
  - tests/test_f6a3_director_config_loader.py (Phase 2 contract for
    get_director_runtime_config — TestLegacyPath class was rewritten)
  - tests/test_f6a3_int_byte_equivalence.py (drift detection — the
    _LEGACY_SYSTEM_PROMPT byte-equiv test was replaced with a
    self-consistency test)
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
# 1. Deleted-symbol guards — direct attribute checks
# ──────────────────────────────────────────────────────────────────────

class TestDeletedSymbols(unittest.TestCase):
    """The deleted symbols must not exist on the modules. Future
    re-introduction of any of these would silently re-create dead
    fallbacks the Phase 2 cleanup was supposed to remove."""

    def test_seed_entries_is_gone_from_world_lore(self):
        import engine.world_lore as wl
        self.assertFalse(
            hasattr(wl, "SEED_ENTRIES"),
            "engine.world_lore.SEED_ENTRIES should be deleted (Phase 2)",
        )

    def test_legacy_valid_factions_is_gone(self):
        import engine.director_config_loader as dcl
        self.assertFalse(
            hasattr(dcl, "_LEGACY_VALID_FACTIONS"),
            "engine.director_config_loader._LEGACY_VALID_FACTIONS "
            "should be deleted (Phase 2)",
        )

    def test_legacy_default_influence_is_gone(self):
        import engine.director_config_loader as dcl
        self.assertFalse(
            hasattr(dcl, "_LEGACY_DEFAULT_INFLUENCE"),
            "engine.director_config_loader._LEGACY_DEFAULT_INFLUENCE "
            "should be deleted (Phase 2)",
        )

    def test_legacy_system_prompt_is_gone(self):
        import engine.director_config_loader as dcl
        self.assertFalse(
            hasattr(dcl, "_LEGACY_SYSTEM_PROMPT"),
            "engine.director_config_loader._LEGACY_SYSTEM_PROMPT "
            "should be deleted (Phase 2)",
        )

    def test_legacy_factory_is_gone(self):
        import engine.director_config_loader as dcl
        self.assertFalse(
            hasattr(dcl, "_legacy"),
            "engine.director_config_loader._legacy() factory "
            "should be deleted (Phase 2)",
        )


# ──────────────────────────────────────────────────────────────────────
# 2. Source-level guards — the literal text shouldn't reappear
# ──────────────────────────────────────────────────────────────────────

class TestSourceLevelDeletionGuards(unittest.TestCase):
    """Catch a future refactor that re-introduces literal data instead
    of routing through YAML."""

    def _read(self, rel_path: str) -> str:
        path = os.path.join(PROJECT_ROOT, rel_path)
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_world_lore_has_no_seed_entries_assignment(self):
        src = self._read("engine/world_lore.py")
        # Match `SEED_ENTRIES = [` at the start of a line (allowing
        # for indent — but never inside a string).
        self.assertNotIn(
            "\nSEED_ENTRIES = [", src,
            "engine/world_lore.py should not contain "
            "`SEED_ENTRIES = [` — that's the deleted literal",
        )

    def test_world_lore_has_no_seed_entries_imports(self):
        """The world_lore module body should not export SEED_ENTRIES."""
        src = self._read("engine/world_lore.py")
        # An assignment like `SEED_ENTRIES =` would be a tell-tale
        # re-introduction of the literal.
        # (Comments mentioning SEED_ENTRIES historically are fine.)
        for line in src.splitlines():
            stripped = line.lstrip()
            self.assertFalse(
                stripped.startswith("SEED_ENTRIES =") or
                stripped.startswith("SEED_ENTRIES:"),
                f"world_lore.py contains a SEED_ENTRIES assignment: {line!r}",
            )

    def test_director_config_loader_has_no_legacy_valid_factions(self):
        src = self._read("engine/director_config_loader.py")
        for line in src.splitlines():
            stripped = line.lstrip()
            self.assertFalse(
                stripped.startswith("_LEGACY_VALID_FACTIONS ="),
                f"director_config_loader.py contains a "
                f"_LEGACY_VALID_FACTIONS assignment: {line!r}",
            )

    def test_director_config_loader_has_no_legacy_default_influence(self):
        src = self._read("engine/director_config_loader.py")
        for line in src.splitlines():
            stripped = line.lstrip()
            self.assertFalse(
                stripped.startswith("_LEGACY_DEFAULT_INFLUENCE ="),
                f"director_config_loader.py contains a "
                f"_LEGACY_DEFAULT_INFLUENCE assignment: {line!r}",
            )

    def test_director_config_loader_has_no_legacy_system_prompt(self):
        src = self._read("engine/director_config_loader.py")
        for line in src.splitlines():
            stripped = line.lstrip()
            self.assertFalse(
                stripped.startswith("_LEGACY_SYSTEM_PROMPT ="),
                f"director_config_loader.py contains a "
                f"_LEGACY_SYSTEM_PROMPT assignment: {line!r}",
            )

    def test_director_config_loader_has_phase_2_anchor(self):
        """The Phase 2 anchor comment should be present for traceability."""
        src = self._read("engine/director_config_loader.py")
        self.assertIn("F.6a.7 Phase 2", src,
                      "F.6a.7 Phase 2 anchor should be present in "
                      "director_config_loader.py")

    def test_world_lore_has_phase_2_anchor(self):
        src = self._read("engine/world_lore.py")
        self.assertIn("F.6a.7 Phase 2", src,
                      "F.6a.7 Phase 2 anchor should be present in "
                      "world_lore.py")


# ──────────────────────────────────────────────────────────────────────
# 3. New behavior — era=None defaults to "gcw"
# ──────────────────────────────────────────────────────────────────────

class TestEraNoneDefaultsToGCW(unittest.TestCase):
    """Pre-Phase-2 era=None returned in-Python literals; post-Phase-2
    it must default to "gcw" (loading from
    data/worlds/gcw/director_config.yaml)."""

    def test_get_director_runtime_config_era_none_yields_yaml_gcw(self):
        from engine.director_config_loader import get_director_runtime_config
        gcw_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
        if not os.path.isfile(os.path.join(gcw_dir, "director_config.yaml")):
            self.skipTest("data/worlds/gcw/director_config.yaml not present")
        cfg = get_director_runtime_config(era=None)
        self.assertEqual(cfg.source, "yaml-gcw",
                         "era=None should default to 'gcw' and produce "
                         "source='yaml-gcw' (not 'legacy' anymore)")
        self.assertGreater(len(cfg.valid_factions), 0)
        self.assertGreater(len(cfg.zone_baselines), 0)

    def test_get_director_runtime_config_era_none_equals_era_gcw(self):
        """era=None and era='gcw' must produce identical configs."""
        from engine.director_config_loader import get_director_runtime_config
        gcw_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
        if not os.path.isfile(os.path.join(gcw_dir, "director_config.yaml")):
            self.skipTest("data/worlds/gcw/director_config.yaml not present")
        cfg_none = get_director_runtime_config(era=None)
        cfg_gcw = get_director_runtime_config(era="gcw")
        self.assertEqual(cfg_none.valid_factions, cfg_gcw.valid_factions)
        self.assertEqual(cfg_none.zone_baselines, cfg_gcw.zone_baselines)
        self.assertEqual(cfg_none.system_prompt, cfg_gcw.system_prompt)


# ──────────────────────────────────────────────────────────────────────
# 4. Fail-loud behavior — YAML load failure returns empty config
# ──────────────────────────────────────────────────────────────────────

class TestFailLoudBehavior(unittest.TestCase):
    """Pre-Phase-2 YAML load failures silently fell back to in-Python
    literals. Post-Phase-2 they return an empty config with a
    descriptive `source` label and log ERROR."""

    def test_unknown_era_returns_empty_config(self):
        from engine.director_config_loader import get_director_runtime_config
        cfg = get_director_runtime_config(era="nonexistent_xyz")
        # Empty config: no factions, no zones, empty prompt
        self.assertEqual(cfg.valid_factions, frozenset())
        self.assertEqual(cfg.zone_baselines, {})
        self.assertEqual(cfg.system_prompt, "")

    def test_unknown_era_source_label_indicates_failure(self):
        """The source label should clearly indicate the failure mode
        for diagnostic purposes."""
        from engine.director_config_loader import get_director_runtime_config
        cfg = get_director_runtime_config(era="nonexistent_xyz")
        # Source label should mention "yaml-" + era + "-...-failed"
        self.assertIn("nonexistent_xyz", cfg.source,
                      f"source label {cfg.source!r} should mention the era")
        self.assertTrue(
            "failed" in cfg.source or "no-content" in cfg.source,
            f"source label {cfg.source!r} should indicate failure mode",
        )

    def test_unknown_era_logs_error(self):
        from engine.director_config_loader import get_director_runtime_config
        with self.assertLogs("engine.director_config_loader",
                             level="ERROR"):
            get_director_runtime_config(era="nonexistent_xyz")


# ──────────────────────────────────────────────────────────────────────
# 5. LOC reduction sanity check
# ──────────────────────────────────────────────────────────────────────

class TestLocReduction(unittest.TestCase):
    """Phase 2 was supposed to remove ~600 LOC of dead literals. Sanity
    check that the modules are now in roughly the expected size range
    (catches accidental re-introduction of the deleted literals via
    a sloppy git revert)."""

    def test_world_lore_under_500_lines(self):
        path = os.path.join(PROJECT_ROOT, "engine", "world_lore.py")
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        # Pre-Phase-2 was 887 lines (with 490-line SEED_ENTRIES literal).
        # Post-Phase-2 should be ~400 lines.
        self.assertLess(
            len(lines), 500,
            f"world_lore.py is {len(lines)} lines — Phase 2 should "
            f"have reduced it to ~400. Possible re-introduction of "
            f"SEED_ENTRIES literal?",
        )

    def test_director_config_loader_under_300_lines(self):
        path = os.path.join(PROJECT_ROOT, "engine",
                            "director_config_loader.py")
        with open(path, "r", encoding="utf-8") as fh:
            lines = fh.readlines()
        # Pre-Phase-2 was 290 lines (with ~100 lines of _LEGACY_*).
        # Post-Phase-2 should be ~225 lines.
        self.assertLess(
            len(lines), 300,
            f"director_config_loader.py is {len(lines)} lines — "
            f"Phase 2 should have reduced it to ~225. Possible "
            f"re-introduction of _LEGACY_* constants?",
        )


if __name__ == "__main__":
    unittest.main()
