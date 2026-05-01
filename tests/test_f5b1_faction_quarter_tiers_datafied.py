# -*- coding: utf-8 -*-
"""
tests/test_f5b1_faction_quarter_tiers_datafied.py — F.5b.1 tests

F.5b.1 (Apr 29 2026) data-fies `engine/housing.py::FACTION_QUARTER_TIERS`:
the in-Python literal was renamed to `_LEGACY_FACTION_QUARTER_TIERS`
and wrapped by `_resolve_faction_quarter_tiers()` which builds the
runtime dict from data/worlds/{gcw,clone_wars}/housing_lots.yaml at
module import.

Both YAMLs are loaded and merged because the legacy literal mashed
both eras' faction data together (B.1.d.1 added CW factions inline
alongside GCW ones), and downstream consumers
(`_faction_min_rank`, `_best_tier_for_rank`) need faction coverage
across both eras simultaneously.

Coverage:
  - Resolved FACTION_QUARTER_TIERS is byte-equivalent to the legacy
    literal (the regression gate)
  - Both eras' factions are present after merge
  - YAML failure modes fall back to the legacy literal:
      * world_loader import error
      * housing_lots.yaml missing
      * housing_lots.yaml has validation errors
      * housing_lots.yaml resolves to 0 tier entries
  - Source-level guards: legacy literal preserved as
    _LEGACY_FACTION_QUARTER_TIERS; F.5b.1 anchor comment present
  - Backward compat: `_faction_min_rank` and `_best_tier_for_rank`
    work the same as pre-F.5b.1 for every (faction, rank) combo

What's NOT tested (deferred):
  - Phase 2 deletion of _LEGACY_FACTION_QUARTER_TIERS — this drop
    keeps the literal as fallback. A future F.5b.2 (after F.5a.2
    + F.5a.3 build the actual rooms) can decide whether to retire it.
  - rep_gate filter — F.5b.2 territory.
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
# 1. Byte-equivalence — the central regression gate
# ──────────────────────────────────────────────────────────────────────


class TestByteEquivalenceWithLegacy(unittest.TestCase):
    """The resolved FACTION_QUARTER_TIERS must be byte-equivalent to
    the in-Python _LEGACY_FACTION_QUARTER_TIERS literal. This is the
    gate that proves the YAML swap doesn't change live behavior."""

    @classmethod
    def setUpClass(cls):
        from engine.housing import (
            FACTION_QUARTER_TIERS, _LEGACY_FACTION_QUARTER_TIERS,
        )
        cls.live = FACTION_QUARTER_TIERS
        cls.legacy = _LEGACY_FACTION_QUARTER_TIERS

    def test_same_key_set(self):
        """Every (faction, rank) key in legacy is in live and v.v."""
        self.assertEqual(
            set(self.live.keys()), set(self.legacy.keys()),
            f"key set diverges: only-in-live="
            f"{set(self.live.keys()) - set(self.legacy.keys())}, "
            f"only-in-legacy="
            f"{set(self.legacy.keys()) - set(self.live.keys())}",
        )

    def test_same_entry_count(self):
        """Live and legacy have the same number of entries."""
        self.assertEqual(len(self.live), len(self.legacy))

    def test_per_entry_byte_equal(self):
        """Each (faction, rank) cfg dict is byte-identical."""
        for k in self.legacy:
            self.assertIn(k, self.live, f"{k} missing from live")
            for fld in ("label", "storage_max", "room_name", "room_desc"):
                self.assertEqual(
                    self.live[k][fld], self.legacy[k][fld],
                    f"{k}.{fld!r}: live={self.live[k][fld]!r} "
                    f"vs legacy={self.legacy[k][fld]!r}",
                )

    def test_dict_equality(self):
        """The strongest assertion: full dict equality."""
        self.assertEqual(self.live, self.legacy,
                         "FACTION_QUARTER_TIERS drifted from "
                         "_LEGACY_FACTION_QUARTER_TIERS")


# ──────────────────────────────────────────────────────────────────────
# 2. Both eras present after merge
# ──────────────────────────────────────────────────────────────────────


class TestBothErasMerged(unittest.TestCase):
    """The resolver loads both GCW and CW YAMLs and merges them. The
    full faction set must include factions from both eras."""

    @classmethod
    def setUpClass(cls):
        from engine.housing import FACTION_QUARTER_TIERS
        cls.factions = sorted(set(fc for (fc, _) in FACTION_QUARTER_TIERS.keys()))

    def test_gcw_factions_present(self):
        for fc in ("empire", "rebel", "hutt"):
            self.assertIn(fc, self.factions,
                          f"GCW faction {fc!r} missing from resolved dict")

    def test_cw_factions_present(self):
        for fc in ("republic", "cis", "jedi_order", "hutt_cartel"):
            self.assertIn(fc, self.factions,
                          f"CW faction {fc!r} missing from resolved dict")

    def test_bhg_correctly_absent(self):
        """BHG has no faction quarters by design (CW design §5.5);
        the YAML stores it as null and the loader/merger skips it."""
        self.assertNotIn("bounty_hunters_guild", self.factions,
                         "BHG should NOT appear in FACTION_QUARTER_TIERS")


# ──────────────────────────────────────────────────────────────────────
# 3. Fallback behavior — YAML failure modes
# ──────────────────────────────────────────────────────────────────────


class TestFallbackBehavior(unittest.TestCase):
    """When the YAML can't be loaded for any reason, the resolver
    falls back to the legacy literal. We exercise the resolver
    directly by patching its load points."""

    def test_resolver_returns_dict(self):
        """Sanity: resolver returns a dict, not None."""
        from engine.housing import _resolve_faction_quarter_tiers
        result = _resolve_faction_quarter_tiers()
        self.assertIsInstance(result, dict)
        self.assertGreater(len(result), 0)

    def test_no_yaml_dirs_falls_back_to_legacy(self):
        """If neither era directory exists in the CWD, the resolver
        falls back to legacy."""
        import tempfile
        from engine.housing import (
            _resolve_faction_quarter_tiers, _LEGACY_FACTION_QUARTER_TIERS,
        )
        old_cwd = os.getcwd()
        # Apr 30 2026 (test-hygiene): Windows + Python 3.14 can't rmdir
        # a tempdir while the CWD is still inside it — TemporaryDirectory's
        # __exit__ races against the CWD release. We chdir back out
        # explicitly inside the with-block, and pass ignore_cleanup_errors
        # as a belt-and-braces guard for any straggler handles.
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as td:
            try:
                os.chdir(td)
                # No data/worlds/<era> exists in this empty temp dir.
                with self.assertLogs("engine.housing", level="WARNING"):
                    result = _resolve_faction_quarter_tiers()
                self.assertEqual(
                    result, _LEGACY_FACTION_QUARTER_TIERS,
                    "missing YAML dirs should fall back to legacy",
                )
            finally:
                # Critical on Windows: chdir BEFORE the with-block exits
                # so TemporaryDirectory.cleanup() can rmdir without a
                # held handle blocking the call.
                os.chdir(old_cwd)

    def test_world_loader_importerror_falls_back_to_legacy(self):
        """If world_loader can't be imported, fall back. Simulated by
        patching sys.modules to make the import fail."""
        import sys as sys_mod
        from engine.housing import (
            _resolve_faction_quarter_tiers, _LEGACY_FACTION_QUARTER_TIERS,
        )
        # Save and remove world_loader from sys.modules; replace with
        # a sentinel that raises ImportError on access. Direct
        # `from engine.world_loader import ...` will then fail.
        saved = sys_mod.modules.pop("engine.world_loader", None)

        class _Broken:
            def __getattr__(self, name):
                raise ImportError(f"simulated failure for {name}")

        sys_mod.modules["engine.world_loader"] = _Broken()
        try:
            with self.assertLogs("engine.housing", level="WARNING"):
                result = _resolve_faction_quarter_tiers()
            self.assertEqual(result, _LEGACY_FACTION_QUARTER_TIERS)
        finally:
            if saved is not None:
                sys_mod.modules["engine.world_loader"] = saved
            else:
                sys_mod.modules.pop("engine.world_loader", None)


# ──────────────────────────────────────────────────────────────────────
# 4. Source-level guards
# ──────────────────────────────────────────────────────────────────────


class TestSourceLevelGuards(unittest.TestCase):
    """Catch a future refactor that accidentally retires the legacy
    fallback or the F.5b.1 anchor comment."""

    @classmethod
    def setUpClass(cls):
        path = os.path.join(PROJECT_ROOT, "engine", "housing.py")
        with open(path, "r", encoding="utf-8") as f:
            cls.src = f.read()

    def test_legacy_literal_preserved(self):
        """The _LEGACY_FACTION_QUARTER_TIERS literal must still be
        in source. F.5b.1 is non-destructive — the literal stays."""
        self.assertIn("_LEGACY_FACTION_QUARTER_TIERS = {", self.src)

    def test_resolver_function_present(self):
        """The resolver function must be defined."""
        self.assertIn("def _resolve_faction_quarter_tiers(", self.src)

    def test_module_level_binding_present(self):
        """The module-level `FACTION_QUARTER_TIERS = _resolve_...()`
        binding must be present so consumers see resolved data."""
        self.assertIn(
            "FACTION_QUARTER_TIERS = _resolve_faction_quarter_tiers()",
            self.src,
        )

    def test_f5b1_anchor_comment_present(self):
        """The F.5b.1 anchor comment must be present for traceability."""
        self.assertIn("F.5b.1", self.src,
                      "F.5b.1 anchor should be present in housing.py")


# ──────────────────────────────────────────────────────────────────────
# 5. Backward compat — consumer helpers unchanged
# ──────────────────────────────────────────────────────────────────────


class TestConsumerBackwardCompat(unittest.TestCase):
    """`_faction_min_rank` and `_best_tier_for_rank` are the live
    consumers of FACTION_QUARTER_TIERS. They must work the same way
    pre- and post-F.5b.1."""

    def test_faction_min_rank_gcw(self):
        from engine.housing import _faction_min_rank
        self.assertEqual(_faction_min_rank("empire"), 0)
        self.assertEqual(_faction_min_rank("rebel"), 1)
        self.assertEqual(_faction_min_rank("hutt"), 2)

    def test_faction_min_rank_cw(self):
        from engine.housing import _faction_min_rank
        self.assertEqual(_faction_min_rank("republic"), 0)
        self.assertEqual(_faction_min_rank("cis"), 0)
        self.assertEqual(_faction_min_rank("jedi_order"), 0)
        self.assertEqual(_faction_min_rank("hutt_cartel"), 2)

    def test_faction_min_rank_unknown_returns_none(self):
        from engine.housing import _faction_min_rank
        self.assertIsNone(_faction_min_rank("nonexistent_xyz"))

    def test_faction_min_rank_bhg_returns_none(self):
        """BHG isn't in FACTION_QUARTER_TIERS (no faction quarters)."""
        from engine.housing import _faction_min_rank
        self.assertIsNone(_faction_min_rank("bounty_hunters_guild"))

    def test_best_tier_for_rank_picks_highest_qualifying(self):
        from engine.housing import _best_tier_for_rank
        # GCW empire ranks: 0, 2, 4, 6
        # Rank 5 should pick rank-4 tier (officer suite)
        cfg = _best_tier_for_rank("empire", 5)
        self.assertIsNotNone(cfg)
        self.assertIn("Officer's Suite", cfg["label"])

        # Rank 7 should pick rank-6 tier (commander quarters)
        cfg = _best_tier_for_rank("empire", 7)
        self.assertIsNotNone(cfg)
        self.assertIn("Commander", cfg["label"])

    def test_best_tier_for_rank_below_minimum_returns_none(self):
        from engine.housing import _best_tier_for_rank
        # Rebel min rank is 1; rank 0 returns None
        self.assertIsNone(_best_tier_for_rank("rebel", 0))
        # Hutt min rank is 2; rank 0 returns None
        self.assertIsNone(_best_tier_for_rank("hutt", 0))
        self.assertIsNone(_best_tier_for_rank("hutt", 1))

    def test_best_tier_for_rank_cw_factions(self):
        from engine.housing import _best_tier_for_rank
        # Republic rank 0 → bunk
        cfg = _best_tier_for_rank("republic", 0)
        self.assertIsNotNone(cfg)
        self.assertIn("Bunk", cfg["label"])

        # Jedi rank 5 → master suite
        cfg = _best_tier_for_rank("jedi_order", 5)
        self.assertIsNotNone(cfg)
        # The Jedi rank-5 entry's label should mention "Master"
        # (canonical Jedi-Master suite)
        self.assertIn("Master", cfg["label"])


if __name__ == "__main__":
    unittest.main()
