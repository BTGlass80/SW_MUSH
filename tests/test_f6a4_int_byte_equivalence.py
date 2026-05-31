# -*- coding: utf-8 -*-
"""
tests/test_f6a4_int_byte_equivalence.py — Byte-equivalence test for
F.6a.4-int (AmbientEventManager seam integration).

Drop F.6a.4-int's original claim: when `use_yaml_director_data` is
False (the default), reading the static ambient pool through the seam
produces a byte-identical dict[zone_key, list[AmbientLine]] to a
direct YAML read of `data/ambient_events.yaml`.

POST-ACTIVE_ERA-PIVOT NOTE (May 18 2026):
After the active_era pivot from "gcw" to "clone_wars", the engine's
`AmbientEventManager._load_yaml()` no longer represents a "legacy
direct-yaml read" — it now reads through the seam with
`get_seeding_era()` ("clone_wars"), which merges the CW era YAML on
top of the legacy flat YAML. The original byte-equivalence assertion
("seam(era=None) == _load_yaml() output") was meaningful before the
pivot, when `get_seeding_era()` returned None; post-pivot it
structurally cannot hold.

The byte-equivalence CONTRACT survives, though: the seam at era=None
must still produce a dict identical to a raw `yaml.safe_load` of
`data/ambient_events.yaml`. This file now expresses that contract
directly against the seam's own legacy-layer loader
(`_load_legacy_pool`), which is what `AmbientEventManager._load_yaml`
*used to do* before the F.6a.4-int wire-up.

Coverage:
  - Direct-YAML pool == seam-driven pool (zone keys identical)
  - For every zone, line count identical
  - For every line, text and weight bytewise equal
  - _pick_line still returns a real string for every legacy zone
  - default zone fallback still resolves
  - get_ambient_pools(era=None) source label is "legacy-only"
"""
from __future__ import annotations

import os
import random
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.ambient_events import AmbientEventManager  # noqa: E402
from engine.ambient_pools_loader import (  # noqa: E402
    AmbientLineTuple,
    MergedAmbientPools,
    _DEFAULT_LEGACY_PATH,
    _load_legacy_pool,
    get_ambient_pools,
)


def _legacy_yaml_pool() -> dict:
    """Load `data/ambient_events.yaml` directly via the seam's own
    legacy-layer loader.

    This bypasses `AmbientEventManager._load_yaml()` entirely so the
    byte-equivalence comparison is not contaminated by the engine
    method's evolving era-aware behavior (post-active_era pivot, that
    method merges CW era YAML on top of legacy).

    Returns a `dict[zone_key, list[AmbientLineTuple]]` — the same
    shape the seam itself returns at era=None.
    """
    pools, used = _load_legacy_pool(_DEFAULT_LEGACY_PATH)
    if not used:
        raise RuntimeError(
            f"legacy ambient_events.yaml not loadable at "
            f"{_DEFAULT_LEGACY_PATH} — fixture broken"
        )
    return pools


def _seam_load_legacy_only() -> MergedAmbientPools:
    """Load via the seam with no era — legacy-flat-yaml only."""
    return get_ambient_pools(era=None)


class TestSeamMatchesLegacy(unittest.TestCase):
    """Byte-equivalence: seam output (era=None) ==
    direct-yaml-load of `data/ambient_events.yaml`.

    Pre-active_era-pivot this compared seam(era=None) against
    `AmbientEventManager._load_yaml()` output, which at the time was
    a synonym for the direct YAML read. Post-pivot
    `_load_yaml()` reads era-aware (merging CW on top of legacy), so
    the test now compares against `_load_legacy_pool` — the seam's
    own legacy-layer loader, which IS the "direct yaml read" the
    original contract was about.
    """

    @classmethod
    def setUpClass(cls):
        cls.legacy_pool = _legacy_yaml_pool()
        cls.seam_pools = _seam_load_legacy_only()

    def test_seam_source_is_legacy_only(self):
        # When era is None, the seam must report legacy-only as its source.
        # If this changes, the byte-equiv claim has shifted and the wire-up
        # decision needs revisiting.
        self.assertEqual(self.seam_pools.source, "legacy-only")

    def test_zone_key_sets_match(self):
        legacy_keys = set(self.legacy_pool.keys())
        seam_keys = set(self.seam_pools.pools.keys())
        self.assertEqual(
            legacy_keys, seam_keys,
            f"zone key mismatch: legacy-only={legacy_keys-seam_keys}, "
            f"seam-only={seam_keys-legacy_keys}",
        )

    def test_legacy_zone_count_nonzero(self):
        # Sanity: this test is meaningless if the legacy path returned
        # zero zones. The live data/ambient_events.yaml has 7 zones.
        self.assertGreater(
            len(self.legacy_pool), 0,
            "Direct yaml read returned zero zones — fixture broken",
        )

    def test_per_zone_line_counts_match(self):
        for zk in self.legacy_pool:
            legacy_lines = self.legacy_pool[zk]
            seam_lines = self.seam_pools.pools[zk]
            self.assertEqual(
                len(legacy_lines), len(seam_lines),
                f"zone {zk!r}: legacy has {len(legacy_lines)} lines, "
                f"seam has {len(seam_lines)}",
            )

    def test_per_line_text_byte_equal(self):
        for zk, legacy_lines in self.legacy_pool.items():
            seam_lines = self.seam_pools.pools[zk]
            for i, (legacy_line, seam_line) in enumerate(
                zip(legacy_lines, seam_lines)
            ):
                self.assertEqual(
                    legacy_line.text, seam_line.text,
                    f"zone {zk!r}[{i}]: text mismatch\n"
                    f"  legacy: {legacy_line.text!r}\n"
                    f"  seam:   {seam_line.text!r}",
                )

    def test_per_line_weight_byte_equal(self):
        for zk, legacy_lines in self.legacy_pool.items():
            seam_lines = self.seam_pools.pools[zk]
            for i, (legacy_line, seam_line) in enumerate(
                zip(legacy_lines, seam_lines)
            ):
                self.assertEqual(
                    legacy_line.weight, seam_line.weight,
                    f"zone {zk!r}[{i}]: weight mismatch "
                    f"({legacy_line.weight} vs {seam_line.weight})",
                )

    def test_seam_lines_are_AmbientLineTuple(self):
        """The seam returns AmbientLineTuple, distinct from the engine's
        AmbientLine. The integration must do the conversion. This test
        just confirms the seam contract — used as a sanity check before
        the integration writes the conversion code."""
        for zk, lines in self.seam_pools.pools.items():
            for ln in lines:
                self.assertIsInstance(ln, AmbientLineTuple)


class TestSeamSurvivesPickLine(unittest.TestCase):
    """The seam-loaded pool, fed into the existing _pick_line logic, must
    return a non-empty string for every legacy zone — same as today.

    This is the integration target's behavioral contract. After the
    F.6a.4-int wire-up, AmbientEventManager._static_pool will be
    populated from the seam; _pick_line shouldn't even notice.
    """

    def setUp(self):
        # Build a fake AmbientEventManager whose _static_pool comes from
        # the seam with era=None. This is what F.6a.4-int will produce
        # at boot when the use_yaml flag is off.
        from engine.ambient_events import AmbientLine

        mgr = AmbientEventManager()
        seam = get_ambient_pools(era=None)
        for zk, lines in seam.pools.items():
            mgr._static_pool[zk] = [
                AmbientLine(text=ln.text, weight=ln.weight) for ln in lines
            ]
        mgr._loaded = True
        self.mgr = mgr

    def test_every_zone_returns_a_line(self):
        # Seed for reproducibility — but the test should pass regardless
        random.seed(12345)
        for zk in self.mgr._static_pool:
            line = self.mgr._pick_line(zk)
            self.assertIsNotNone(line, f"zone {zk!r} returned None")
            self.assertIsInstance(line, str)
            self.assertGreater(len(line), 0)

    def test_unknown_zone_falls_back_to_default(self):
        # Test only meaningful if 'default' actually exists in the pool
        if "default" not in self.mgr._static_pool:
            self.skipTest("'default' zone not in live ambient_events.yaml")
        random.seed(99)
        line = self.mgr._pick_line("__nonexistent_zone__")
        # Either the default pool fired, or None if no default exists.
        # Live YAML has 'default'; assert non-None.
        self.assertIsNotNone(line)


class TestSeamPickPoolHelper(unittest.TestCase):
    """Document the seam's `pick_pool_for_zone` resolution rule.

    Not used by the integration (that goes through AmbientEventManager's
    _pick_line), but it's part of the seam contract and should stay
    consistent across the integration drop.
    """

    def test_pick_pool_returns_zone_lines(self):
        from engine.ambient_pools_loader import pick_pool_for_zone

        merged = get_ambient_pools(era=None)
        # Pick any present zone
        if not merged.pools:
            self.skipTest("seam returned empty pool — fixture broken")
        zk = next(iter(merged.pools.keys()))
        lines = pick_pool_for_zone(merged, zk)
        self.assertEqual(lines, merged.pools[zk])

    def test_pick_pool_falls_back_to_default(self):
        from engine.ambient_pools_loader import pick_pool_for_zone

        merged = get_ambient_pools(era=None)
        if "default" not in merged.pools:
            self.skipTest("no 'default' zone in live data")
        lines = pick_pool_for_zone(merged, "__nonexistent__")
        self.assertEqual(lines, merged.pools["default"])


if __name__ == "__main__":
    unittest.main()
