# -*- coding: utf-8 -*-
"""
tests/test_f5b3c_legacy_constants_deleted.py — F.5b.3.c tests.

F.5b.3.c (Apr 30 2026) is the destructive cleanup that retires the
legacy in-Python `HOUSING_LOTS_*` constants from `engine/housing.py`.
Pre-F.5b.3.c those constants were:
  - The pre-F.5b.3.b runtime source for GCW lot inventory
  - The post-F.5b.3.b transitional soft-fallback when YAML loading
    failed
  - Imported by `parser/housing_commands.py::_cmd_shopfront` for an
    incorrect-keyspace planet lookup (latent bug — `_lt[0]` is room_id,
    `lot_id` is housing_lots.id; F.5b.3.c also fixes that)

Post-F.5b.3.c:
  - Constants don't exist in `engine/housing.py` at all
  - `engine/housing_lots_provider.py::_resolve_corpus_for_era` no
    longer imports them; soft-fallback is replaced with a fail-loud
    ERROR log + empty result dict
  - `parser/housing_commands.py::_cmd_shopfront` uses `get_lot()`
    for the planet lookup (matching `_cmd_buy`'s pattern)
  - `tests/_legacy_housing_lots_snapshot.py` carries the frozen
    values for byte-equivalence regression testing

Test contract
-------------
1. The four constant names cannot be imported from `engine.housing`.
2. The provider source has no reference to `_housing.HOUSING_LOTS_*`
   names.
3. The parser source has no `HOUSING_LOTS_TIER4` import or iteration.
4. The provider's fail-loud path produces an empty result dict and
   logs ERROR (verified via mock).
5. The frozen snapshot module loads and contains the expected
   cardinalities.
"""
from __future__ import annotations

import logging
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ──────────────────────────────────────────────────────────────────────
# Section 1: legacy constants no longer exist in engine.housing
# ──────────────────────────────────────────────────────────────────────


class TestLegacyConstantsDeleted(unittest.TestCase):
    """The four `HOUSING_LOTS_*` constants must not be importable from
    `engine.housing` after F.5b.3.c."""

    def test_HOUSING_LOTS_DROP1_not_importable(self):
        with self.assertRaises(ImportError):
            from engine.housing import HOUSING_LOTS_DROP1  # noqa: F401

    def test_HOUSING_LOTS_TIER3_not_importable(self):
        with self.assertRaises(ImportError):
            from engine.housing import HOUSING_LOTS_TIER3  # noqa: F401

    def test_HOUSING_LOTS_TIER4_not_importable(self):
        with self.assertRaises(ImportError):
            from engine.housing import HOUSING_LOTS_TIER4  # noqa: F401

    def test_HOUSING_LOTS_TIER5_not_importable(self):
        with self.assertRaises(ImportError):
            from engine.housing import HOUSING_LOTS_TIER5  # noqa: F401

    def test_engine_housing_imports_cleanly(self):
        """The deletion must not break engine.housing's own imports.
        This catches a regression where the deletion accidentally
        removed something that other in-module code referenced."""
        import importlib
        import engine.housing
        # Force a reimport to surface any module-level issues
        importlib.reload(engine.housing)
        # The presence of these other public functions confirms the
        # module loaded successfully.
        self.assertTrue(hasattr(engine.housing, "purchase_home"))
        self.assertTrue(hasattr(engine.housing, "purchase_shopfront"))
        self.assertTrue(hasattr(engine.housing, "seed_lots"))
        self.assertTrue(hasattr(engine.housing, "ensure_schema"))


# ──────────────────────────────────────────────────────────────────────
# Section 2: source-level guards on the provider and parser
# ──────────────────────────────────────────────────────────────────────


class TestProviderSourceCleanup(unittest.TestCase):
    """The provider must no longer reference the deleted constants."""

    @classmethod
    def setUpClass(cls):
        cls.provider_src = (
            PROJECT_ROOT / "engine" / "housing_lots_provider.py"
        ).read_text(encoding="utf-8")

    def test_no_legacy_constant_reference(self):
        for name in ("HOUSING_LOTS_DROP1", "HOUSING_LOTS_TIER3",
                     "HOUSING_LOTS_TIER4", "HOUSING_LOTS_TIER5"):
            self.assertNotIn(
                f"_housing.{name}", self.provider_src,
                f"Provider must not reference deleted {name}",
            )

    def test_no_legacy_import(self):
        self.assertNotIn(
            "from engine import housing as _housing",
            self.provider_src,
            "Provider must not import the deleted constants",
        )

    def test_fail_loud_log_present(self):
        """The fail-loud path uses log.error, not log.warning, per
        F.5b.3.c §18.19 seam-vs-integration discipline."""
        self.assertIn(
            "log.error", self.provider_src,
            "Provider must use log.error on YAML load failure (fail-loud)",
        )


class TestParserSourceCleanup(unittest.TestCase):
    """The parser shopfront command must use get_lot() instead of
    iterating the deleted HOUSING_LOTS_TIER4 constant."""

    @classmethod
    def setUpClass(cls):
        cls.parser_src = (
            PROJECT_ROOT / "parser" / "housing_commands.py"
        ).read_text(encoding="utf-8")

    def test_no_legacy_constant_import(self):
        """The parser must not import or iterate HOUSING_LOTS_TIER4.

        We strip comments before checking, because the F.5b.3.c bug-fix
        commentary intentionally names HOUSING_LOTS_TIER4 (to document
        what was removed and why). A bare-string scan would false-match
        the comment.
        """
        import re
        # Strip full-line comments (leading whitespace + #)
        # and inline comments (# to end-of-line, but preserving strings).
        # Crude but adequate: drop everything from `#` to end-of-line on
        # each line. This will also drop `#` characters inside strings,
        # which is acceptable here since we're only scanning for an
        # identifier name and the source has no `#` inside strings.
        lines = self.parser_src.splitlines()
        code_only = "\n".join(
            re.sub(r"#.*$", "", line) for line in lines
        )
        self.assertNotIn(
            "HOUSING_LOTS_TIER4", code_only,
            "parser/housing_commands.py must not import or reference the "
            "deleted HOUSING_LOTS_TIER4 constant in code (comments are OK).",
        )

    def test_get_lot_used_in_shopfront(self):
        """The shopfront purchase path must use get_lot() to resolve
        the planet (mirroring _cmd_buy's pattern)."""
        # Find the _cmd_shopfront block specifically
        idx = self.parser_src.find("async def _cmd_shopfront")
        self.assertGreater(idx, 0, "_cmd_shopfront must exist")
        # Look for get_lot usage within ~2000 chars after
        block = self.parser_src[idx:idx + 2500]
        self.assertIn(
            "get_lot(ctx.db, lot_id)", block,
            "_cmd_shopfront must use get_lot(ctx.db, lot_id) for "
            "planet lookup (F.5b.3.c bug fix)",
        )


# ──────────────────────────────────────────────────────────────────────
# Section 3: fail-loud behavior on YAML unavailability
# ──────────────────────────────────────────────────────────────────────


class TestFailLoudOnYAMLFailure(unittest.TestCase):
    """When `_load_yaml_corpus` returns None, the provider must:
      1. Log at ERROR severity (not WARNING)
      2. Return an empty result dict (no fallback to constants)
      3. Cache the empty result so subsequent calls don't re-fail
    """

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def tearDown(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_empty_result_on_yaml_failure(self):
        from engine.housing_lots_provider import _resolve_corpus_for_era
        with patch(
            "engine.housing_lots_provider._load_yaml_corpus",
            return_value=None,
        ):
            result = _resolve_corpus_for_era("nonexistent_era")
        self.assertEqual(result["t1"], [])
        self.assertEqual(result["t3"], [])
        self.assertEqual(result["t4"], [])
        self.assertEqual(result["t5"], [])
        self.assertEqual(result["rep_gates"], {})

    def test_error_log_on_yaml_failure(self):
        from engine.housing_lots_provider import _resolve_corpus_for_era
        with patch(
            "engine.housing_lots_provider._load_yaml_corpus",
            return_value=None,
        ):
            with self.assertLogs(
                "engine.housing_lots_provider", level=logging.ERROR
            ) as cm:
                _resolve_corpus_for_era("nonexistent_era_2")
        # At least one ERROR-level record
        self.assertTrue(
            any(rec.levelno == logging.ERROR for rec in cm.records),
            f"Expected an ERROR log; got: {[r.levelname for r in cm.records]}",
        )


# ──────────────────────────────────────────────────────────────────────
# Section 4: the snapshot module
# ──────────────────────────────────────────────────────────────────────


class TestSnapshotModule(unittest.TestCase):
    """The snapshot module carries the frozen pre-F.5b.3.c values."""

    def test_snapshot_module_loads(self):
        from tests._legacy_housing_lots_snapshot import (
            LEGACY_HOUSING_LOTS_DROP1, LEGACY_HOUSING_LOTS_TIER3,
            LEGACY_HOUSING_LOTS_TIER4, LEGACY_HOUSING_LOTS_TIER5,
        )
        # Cardinalities locked at pre-F.5b.3.c values.
        self.assertEqual(len(LEGACY_HOUSING_LOTS_DROP1), 5)
        self.assertEqual(len(LEGACY_HOUSING_LOTS_TIER3), 7)
        self.assertEqual(len(LEGACY_HOUSING_LOTS_TIER4), 6)
        self.assertEqual(len(LEGACY_HOUSING_LOTS_TIER5), 6)

    def test_snapshot_tuple_shape(self):
        """Each snapshot entry is a 5-tuple
        (room_id, planet, label, security, max_homes)."""
        from tests._legacy_housing_lots_snapshot import (
            LEGACY_HOUSING_LOTS_DROP1, LEGACY_HOUSING_LOTS_TIER3,
            LEGACY_HOUSING_LOTS_TIER4, LEGACY_HOUSING_LOTS_TIER5,
        )
        for name, snap in (
            ("DROP1", LEGACY_HOUSING_LOTS_DROP1),
            ("TIER3", LEGACY_HOUSING_LOTS_TIER3),
            ("TIER4", LEGACY_HOUSING_LOTS_TIER4),
            ("TIER5", LEGACY_HOUSING_LOTS_TIER5),
        ):
            for i, entry in enumerate(snap):
                self.assertEqual(
                    len(entry), 5,
                    f"{name}[{i}] must be a 5-tuple, got {len(entry)}",
                )
                rid, p, label, sec, mh = entry
                self.assertIsInstance(rid, int, f"{name}[{i}] room_id")
                self.assertIsInstance(p, str, f"{name}[{i}] planet")
                self.assertIsInstance(label, str, f"{name}[{i}] label")
                self.assertIn(
                    sec, ("secured", "contested", "lawless"),
                    f"{name}[{i}] security",
                )
                self.assertIsInstance(mh, int, f"{name}[{i}] max_homes")


# ──────────────────────────────────────────────────────────────────────
# Section 5: end-to-end — boot path produces correct lot inventory
# ──────────────────────────────────────────────────────────────────────


class TestEndToEndPostDeletion(unittest.TestCase):
    """The `housing tier3` listing path (the user-facing surface
    most likely to break) must still produce correct output post-
    F.5b.3.c. Cardinality and at-least-one-known-label checks.
    """

    def setUp(self):
        from engine.housing_lots_provider import clear_lots_cache
        clear_lots_cache()

    def test_gcw_t3_produces_seven_lots_post_deletion(self):
        from engine.housing_lots_provider import get_tier3_lots
        t3 = get_tier3_lots("gcw")
        self.assertEqual(
            len(t3), 7,
            "GCW T3 must produce 7 lots from YAML (matches legacy "
            "TIER3 cardinality)",
        )

    def test_gcw_t3_includes_known_label(self):
        from engine.housing_lots_provider import get_tier3_lots
        t3 = get_tier3_lots("gcw")
        labels = [lot[2] for lot in t3]
        self.assertIn("South End Residences", labels)

    def test_gcw_all_tiers_total_24(self):
        """All four GCW tiers combined produce 24 lots
        (5+7+6+6 = the F.5b.3.a YAML inventory cardinality)."""
        from engine.housing_lots_provider import (
            get_tier1_lots, get_tier3_lots, get_tier4_lots, get_tier5_lots,
        )
        total = (
            len(get_tier1_lots("gcw")) + len(get_tier3_lots("gcw"))
            + len(get_tier4_lots("gcw")) + len(get_tier5_lots("gcw"))
        )
        self.assertEqual(total, 24)


if __name__ == "__main__":
    unittest.main()
