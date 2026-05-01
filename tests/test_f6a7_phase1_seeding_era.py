# -*- coding: utf-8 -*-
"""
tests/test_f6a7_phase1_seeding_era.py — F.6a.7 Phase 1 tests.

F.6a.7 Phase 1 (Apr 29 2026) wires production boot to use the YAML
data path for both GCW and CW, instead of the `era=None` legacy code
paths. This is non-destructive: the legacy `_LEGACY_*` constants in
`engine/director_config_loader.py`, the `SEED_ENTRIES` literal in
`engine/world_lore.py`, and the `era=None` branches in `seed_lore()`
and `get_director_runtime_config()` are all kept in place. They just
stop being reached from production boot.

Phase 2 (later drop) is the destructive delete of those constants
and code paths.

Three changes verified:

  1. `engine/era_state.py::get_seeding_era()` — new helper that
     returns the active era unconditionally (mirrors get_active_era()).
     The pre-existing `resolve_era_for_seeding()` is kept as deprecated
     for backward compatibility with explicit-legacy-path test
     fixtures.

  2. `engine/director.py::_resolve_director_runtime_config` — switched
     from `resolve_era_for_seeding()` to `get_seeding_era()`. Result:
     module-level `VALID_FACTIONS` and `DEFAULT_INFLUENCE` resolve via
     the YAML path for GCW (source label is now "yaml-gcw" instead of
     "legacy"). Byte-equivalent observable values because GCW YAML is
     byte-equivalence-verified by F.6a.3 tests.

  3. `server/game_server.py:362` and `engine/ambient_events.py:152` —
     production seeding callers switched to `get_seeding_era()` so
     GCW boot routes through `data/worlds/gcw/lore.yaml` and the
     full ambient pool merge instead of the bare legacy flat file.
"""
from __future__ import annotations

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. get_seeding_era() — new helper
# ──────────────────────────────────────────────────────────────────────

class TestGetSeedingEra(unittest.TestCase):
    """get_seeding_era() returns the active era regardless of the
    use_yaml_director_data flag. This is the key behavior change for
    F.6a.7 Phase 1: production seeding callers no longer gate on the
    transitional flag."""

    def setUp(self):
        from engine import era_state
        # Snapshot and clear so each test starts from a known baseline
        self._saved = era_state._active_config
        era_state.clear_active_config()

    def tearDown(self):
        from engine import era_state
        era_state.set_active_config(self._saved)

    def test_default_returns_gcw(self):
        from engine.era_state import get_seeding_era
        self.assertEqual(get_seeding_era(), "gcw")

    def test_with_cfg_returns_cfg_era(self):
        from engine.era_state import get_seeding_era
        cfg = SimpleNamespace(
            active_era="clone_wars",
            use_yaml_director_data=True,
        )
        self.assertEqual(get_seeding_era(cfg), "clone_wars")

    def test_yaml_flag_off_still_returns_active_era(self):
        """The crucial difference vs. resolve_era_for_seeding(): the
        flag does NOT gate the result. Even with use_yaml_director_data
        off, get_seeding_era() returns the active era."""
        from engine.era_state import get_seeding_era
        cfg = SimpleNamespace(
            active_era="clone_wars",
            use_yaml_director_data=False,  # flag OFF
        )
        # get_seeding_era ignores the flag — returns the active era
        self.assertEqual(get_seeding_era(cfg), "clone_wars")

    def test_with_cfg_gcw_returns_gcw(self):
        from engine.era_state import get_seeding_era
        cfg = SimpleNamespace(
            active_era="gcw",
            use_yaml_director_data=False,
        )
        self.assertEqual(get_seeding_era(cfg), "gcw")

    def test_registered_cfg_used_when_no_explicit(self):
        from engine import era_state
        from engine.era_state import get_seeding_era, set_active_config
        cfg = SimpleNamespace(
            active_era="clone_wars",
            use_yaml_director_data=False,
        )
        set_active_config(cfg)
        try:
            self.assertEqual(get_seeding_era(), "clone_wars")
        finally:
            era_state.clear_active_config()

    def test_explicit_cfg_overrides_registered(self):
        from engine import era_state
        from engine.era_state import get_seeding_era, set_active_config
        registered = SimpleNamespace(
            active_era="gcw", use_yaml_director_data=True,
        )
        set_active_config(registered)
        try:
            explicit = SimpleNamespace(
                active_era="clone_wars", use_yaml_director_data=False,
            )
            self.assertEqual(get_seeding_era(explicit), "clone_wars")
        finally:
            era_state.clear_active_config()


class TestResolveEraForSeedingDeprecatedButPreserved(unittest.TestCase):
    """resolve_era_for_seeding() is kept for backward compatibility
    with F.6a.{2,3}-int test fixtures that exercise the era=None
    legacy branch explicitly. Behavior must be identical to pre-drop."""

    def setUp(self):
        from engine import era_state
        self._saved = era_state._active_config
        era_state.clear_active_config()

    def tearDown(self):
        from engine import era_state
        era_state.set_active_config(self._saved)

    def test_flag_off_returns_none(self):
        from engine.era_state import resolve_era_for_seeding
        cfg = SimpleNamespace(
            active_era="gcw", use_yaml_director_data=False,
        )
        self.assertIsNone(resolve_era_for_seeding(cfg))

    def test_flag_on_returns_active_era(self):
        from engine.era_state import resolve_era_for_seeding
        cfg = SimpleNamespace(
            active_era="clone_wars", use_yaml_director_data=True,
        )
        self.assertEqual(resolve_era_for_seeding(cfg), "clone_wars")

    def test_default_returns_none(self):
        from engine.era_state import resolve_era_for_seeding
        # No registered config; default flag is False
        self.assertIsNone(resolve_era_for_seeding())


# ──────────────────────────────────────────────────────────────────────
# 2. director.py source wiring — uses get_seeding_era
# ──────────────────────────────────────────────────────────────────────

class TestDirectorRuntimeConfigUsesSeedingEra(unittest.TestCase):
    """Source-level inspection that director.py's _resolve_director_runtime_config
    calls get_seeding_era() instead of resolve_era_for_seeding()."""

    def _read_director_source(self):
        import engine.director as d
        with open(d.__file__, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_uses_get_seeding_era(self):
        src = self._read_director_source()
        self.assertIn("get_seeding_era", src,
                      "director.py should import/use get_seeding_era")

    def test_does_not_use_resolve_era_for_seeding_in_runtime_config(self):
        """The _resolve_director_runtime_config function should NOT
        call resolve_era_for_seeding anymore in its executable code.
        (Docstring mentions for historical context are fine; only
        actual code references count.)"""
        src = self._read_director_source()
        # The function body — find the function and check its slice
        marker = "def _resolve_director_runtime_config():"
        idx = src.find(marker)
        self.assertGreater(idx, 0, "marker not found in director.py")
        # Look at the next ~2500 chars (function body + safety buffer)
        slice_ = src[idx:idx + 2500]
        # Strip the docstring before checking — historical-context
        # mentions in the docstring are fine, only executable code
        # should not reference the deprecated helper.
        # The docstring runs from the first triple-quote after the def
        # to the next triple-quote.
        ds_start = slice_.find('"""')
        ds_end = slice_.find('"""', ds_start + 3)
        if ds_start >= 0 and ds_end > ds_start:
            code_only = slice_[:ds_start] + slice_[ds_end + 3:]
        else:
            code_only = slice_
        self.assertNotIn(
            "resolve_era_for_seeding", code_only,
            "_resolve_director_runtime_config should not import or call "
            "the deprecated helper (docstring mentions are fine)",
        )

    def test_f6a7_anchor_present(self):
        src = self._read_director_source()
        self.assertIn("F.6a.7", src,
                      "F.6a.7 anchor comment should be present")


# ──────────────────────────────────────────────────────────────────────
# 3. director.py runtime config — sources from yaml-gcw, not legacy
# ──────────────────────────────────────────────────────────────────────

class TestDirectorRuntimeConfigSourceLabel(unittest.TestCase):
    """When the production boot path resolves the runtime config under
    the GCW default, the source label should be 'yaml-gcw' (post-F.6a.7
    Phase 1) instead of 'legacy' (pre-drop). This is the most direct
    evidence that GCW is now booting through the YAML path.
    """

    def setUp(self):
        from engine import era_state
        self._saved = era_state._active_config
        # Mirror production: no cfg registered → defaults to GCW + YAML off
        era_state.clear_active_config()

    def tearDown(self):
        from engine import era_state
        era_state.set_active_config(self._saved)

    def test_default_resolution_uses_yaml_gcw(self):
        # Re-resolve fresh
        from engine import director
        from importlib import reload
        # Capture the freshly-resolved config via the seam directly
        # (since module-level VALID_FACTIONS is import-time).
        from engine.director_config_loader import get_director_runtime_config
        from engine.era_state import get_seeding_era
        cfg = get_director_runtime_config(era=get_seeding_era())
        # GCW YAML must be present for this assertion to be meaningful
        gcw_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
        if not os.path.isfile(os.path.join(gcw_dir, "director_config.yaml")):
            self.skipTest("data/worlds/gcw/director_config.yaml not present")
        self.assertEqual(cfg.source, "yaml-gcw",
                         "Default GCW boot should now resolve via YAML, "
                         "not legacy fallback")

    def test_default_factions_match_canonical_gcw_set(self):
        """The YAML path's resolved factions for GCW must equal the
        canonical 4-axis-name GCW set. Pre-F.6a.7 Phase 2 this asserted
        against `_LEGACY_VALID_FACTIONS` directly; Phase 2 deleted that
        constant, so we hardcode the expected set here as the test's
        ground truth."""
        from engine.director_config_loader import get_director_runtime_config
        from engine.era_state import get_seeding_era
        gcw_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "gcw")
        if not os.path.isfile(os.path.join(gcw_dir, "director_config.yaml")):
            self.skipTest("data/worlds/gcw/director_config.yaml not present")
        cfg = get_director_runtime_config(era=get_seeding_era())
        # The canonical GCW axis-name factions, formerly captured in
        # `_LEGACY_VALID_FACTIONS`. Pinned here as the test's ground
        # truth post-F.6a.7-Phase-2.
        canonical_gcw = frozenset({
            "imperial", "rebel", "criminal", "independent",
        })
        self.assertEqual(cfg.valid_factions, canonical_gcw)


# ──────────────────────────────────────────────────────────────────────
# 4. game_server.py source wiring
# ──────────────────────────────────────────────────────────────────────

class TestGameServerSeedLoreUsesSeedingEra(unittest.TestCase):
    """Source-level inspection that game_server.py passes era to
    seed_lore()."""

    def _read_game_server_source(self):
        # Read source directly without importing — the module has
        # heavy import-time dependencies (aiohttp etc.) that aren't
        # required to inspect its source text.
        path = os.path.join(PROJECT_ROOT, "server", "game_server.py")
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_seed_lore_called_with_era(self):
        src = self._read_game_server_source()
        self.assertIn("seed_lore(self.db, era=get_seeding_era())", src,
                      "seed_lore should be called with era=get_seeding_era()")

    def test_no_bare_seed_lore_call_remains(self):
        """The bare `seed_lore(self.db)` call should be gone."""
        src = self._read_game_server_source()
        # The whole-line bare call (allowing for indentation)
        bare = "await seed_lore(self.db)"
        idx = src.find(bare)
        if idx >= 0:
            # Make sure it's not inside a comment or different context;
            # check the next few chars to confirm it's not part of a
            # different signature like seed_lore(self.db, ...)
            after = src[idx + len(bare):idx + len(bare) + 5]
            # If after is empty, newline, or whitespace-only, it's a true bare call
            self.assertFalse(
                after == "" or after[0] in "\n)",
                f"Bare `await seed_lore(self.db)` call should be removed: "
                f"context after: {after!r}",
            )


# ──────────────────────────────────────────────────────────────────────
# 5. ambient_events.py source wiring
# ──────────────────────────────────────────────────────────────────────

class TestAmbientEventsUsesSeedingEra(unittest.TestCase):
    """Source-level inspection that ambient_events.py uses
    get_seeding_era()."""

    def _read_ambient_source(self):
        import engine.ambient_events as ae
        with open(ae.__file__, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_uses_get_seeding_era(self):
        src = self._read_ambient_source()
        self.assertIn("get_seeding_era", src,
                      "ambient_events.py should use get_seeding_era")

    def test_f6a7_anchor_present(self):
        src = self._read_ambient_source()
        self.assertIn("F.6a.7", src,
                      "F.6a.7 anchor comment should be present in ambient_events.py")


# ──────────────────────────────────────────────────────────────────────
# 6. Behavioral integration — get_director_runtime_config under
#    different cfg shapes still returns sane configs
# ──────────────────────────────────────────────────────────────────────

class TestRuntimeConfigBehavioralIntegration(unittest.TestCase):
    """Belt-and-suspenders: even with various cfg shapes, the runtime
    config resolution path still returns a valid config object with
    the expected structural fields."""

    def setUp(self):
        from engine import era_state
        self._saved = era_state._active_config

    def tearDown(self):
        from engine import era_state
        era_state.set_active_config(self._saved)

    def test_resolution_for_gcw_returns_4_factions(self):
        from engine import era_state
        era_state.clear_active_config()
        from engine.director_config_loader import get_director_runtime_config
        from engine.era_state import get_seeding_era
        cfg = get_director_runtime_config(era=get_seeding_era())
        self.assertEqual(len(cfg.valid_factions), 4,
                         f"GCW expects 4 factions, got {cfg.valid_factions}")

    def test_resolution_for_clone_wars_returns_6_factions(self):
        from engine import era_state
        from engine.director_config_loader import get_director_runtime_config
        from engine.era_state import get_seeding_era
        cw_dir = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
        if not os.path.isfile(os.path.join(cw_dir, "director_config.yaml")):
            self.skipTest("data/worlds/clone_wars/director_config.yaml not present")
        # Register a CW config
        era_state.set_active_config(SimpleNamespace(
            active_era="clone_wars",
            use_yaml_director_data=True,
        ))
        try:
            cfg = get_director_runtime_config(era=get_seeding_era())
            self.assertEqual(len(cfg.valid_factions), 6,
                             f"CW expects 6 factions, got {cfg.valid_factions}")
            self.assertEqual(cfg.source, "yaml-clone_wars")
        finally:
            era_state.clear_active_config()


if __name__ == "__main__":
    unittest.main()
