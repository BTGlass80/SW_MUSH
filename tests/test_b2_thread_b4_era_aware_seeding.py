# -*- coding: utf-8 -*-
"""
tests/test_b2_thread_b4_era_aware_seeding.py — Byte-equivalence + era
plumbing tests for the B.2-thread + B.4 combined drop.

Two integration changes ship together:

B.2-thread — `build_mos_eisley.auto_build_if_needed` accepts an optional
`era` kwarg and, when omitted, resolves it from `engine.era_state`
(which `main.py`'s boot wires up). `server/game_server.py` passes
`era=self.config.active_era` at the call site.

B.4 — `engine.organizations.seed_organizations` accepts an optional
`era` kwarg. When omitted, resolves from `engine.era_state`. For
`era="gcw"` it reads the legacy `data/organizations.yaml` (preserving
byte-equivalence with current production). For other eras it reads
`data/worlds/<era>/organizations.yaml`.

Test contract:

  - For the GCW (default-era) case, behavior is byte-identical to the
    pre-drop production path. The CW dev-test produced GCW orgs and
    GCW Tatooine — that is what we are NOT going to do anymore when the
    flag is on, but we still must do exactly that when the flag is off.

  - For the CW (flag-on) case, `seed_organizations` reads the CW
    organizations YAML, and `auto_build_if_needed` invokes
    `build(db_path, era="clone_wars")`.

Some tests are asymmetric: they FAIL pre-wiring and PASS post-wiring.
Those are the gate.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
import types
import unittest
from unittest.mock import MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────

def _make_cfg(active_era="gcw", use_yaml_director_data=False):
    """Build a Config-shaped duck-typed object for era_state."""
    cfg = types.SimpleNamespace()
    cfg.active_era = active_era
    cfg.use_yaml_director_data = use_yaml_director_data
    return cfg


def _reset_era_state():
    """Clear the module-level ambient config between tests."""
    from engine.era_state import clear_active_config
    clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# B.2-thread — auto_build_if_needed era plumbing
# ──────────────────────────────────────────────────────────────────────

class TestAutoBuildEraPlumbing(unittest.TestCase):
    """auto_build_if_needed must thread era through to build()."""

    def setUp(self):
        _reset_era_state()

    def tearDown(self):
        _reset_era_state()

    def _patch_db_and_build(self, count_rooms_value=0):
        """Return a context manager that patches Database and build() with
        side_effect callables that produce a fresh coroutine per call.
        Avoids the 'coroutine was never awaited' issue from reusing a
        single coroutine object."""
        async def db_connect(*a, **kw): return None
        async def db_init(*a, **kw): return None
        async def db_count(*a, **kw): return count_rooms_value
        async def db_close(*a, **kw): return None
        async def fake_build(*a, **kw): return None

        mock_db_cls = MagicMock()
        mock_db = MagicMock()
        mock_db.connect = MagicMock(side_effect=db_connect)
        mock_db.initialize = MagicMock(side_effect=db_init)
        mock_db.count_rooms = MagicMock(side_effect=db_count)
        mock_db.close = MagicMock(side_effect=db_close)
        mock_db_cls.return_value = mock_db

        return mock_db_cls, fake_build

    def test_default_no_era_resolves_to_gcw(self):
        """No era arg + no registered Config -> build() called with era='gcw'."""
        from build_mos_eisley import auto_build_if_needed
        mock_db_cls, fake_build = self._patch_db_and_build(count_rooms_value=0)

        with patch("build_mos_eisley.build", side_effect=fake_build) as mock_build, \
             patch("build_mos_eisley.Database", mock_db_cls):
            asyncio.run(auto_build_if_needed("sw_mush.db"))

            # Asymmetric assertion: pre-wiring auto_build_if_needed calls
            # build(db_path) with no era kwarg. Post-wiring it must pass
            # era='gcw' (resolved from the era_state default).
            mock_build.assert_called_once()
            call_kwargs = mock_build.call_args.kwargs
            self.assertEqual(
                call_kwargs.get("era"), "gcw",
                "auto_build_if_needed must pass era='gcw' to build() when no "
                "Config is registered. Pre-wiring this test fails because "
                "auto_build_if_needed calls build(db_path) without era=."
            )

    def test_explicit_era_clone_wars(self):
        """Explicit era kwarg wins over registered Config."""
        from build_mos_eisley import auto_build_if_needed
        from engine.era_state import set_active_config
        # Register GCW config; explicit era kwarg should override.
        set_active_config(_make_cfg(active_era="gcw"))

        mock_db_cls, fake_build = self._patch_db_and_build(count_rooms_value=0)
        with patch("build_mos_eisley.build", side_effect=fake_build) as mock_build, \
             patch("build_mos_eisley.Database", mock_db_cls):
            asyncio.run(auto_build_if_needed("sw_mush.db", era="clone_wars"))

            mock_build.assert_called_once()
            self.assertEqual(mock_build.call_args.kwargs.get("era"), "clone_wars")

    def test_registered_config_clone_wars(self):
        """No explicit era kwarg + CW Config registered -> build called with CW."""
        from build_mos_eisley import auto_build_if_needed
        from engine.era_state import set_active_config
        set_active_config(_make_cfg(active_era="clone_wars",
                                    use_yaml_director_data=True))

        mock_db_cls, fake_build = self._patch_db_and_build(count_rooms_value=0)
        with patch("build_mos_eisley.build", side_effect=fake_build) as mock_build, \
             patch("build_mos_eisley.Database", mock_db_cls):
            asyncio.run(auto_build_if_needed("sw_mush.db"))

            mock_build.assert_called_once()
            self.assertEqual(mock_build.call_args.kwargs.get("era"),
                             "clone_wars")

    def test_world_already_populated_skips_build(self):
        """If count_rooms > 3, build() is not called regardless of era."""
        from build_mos_eisley import auto_build_if_needed
        mock_db_cls, fake_build = self._patch_db_and_build(count_rooms_value=50)
        with patch("build_mos_eisley.build", side_effect=fake_build) as mock_build, \
             patch("build_mos_eisley.Database", mock_db_cls):
            result = asyncio.run(auto_build_if_needed("sw_mush.db",
                                                     era="clone_wars"))
            self.assertFalse(result)
            mock_build.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# B.4 — seed_organizations era awareness
# ──────────────────────────────────────────────────────────────────────

class TestSeedOrganizationsPathResolution(unittest.TestCase):
    """seed_organizations must pick the right YAML path per era.

    These tests stub yaml.safe_load and the DB calls so we only verify
    PATH RESOLUTION — not the underlying YAML data. Path resolution is
    the contract we are adding.
    """

    def setUp(self):
        _reset_era_state()

    def tearDown(self):
        _reset_era_state()

    def _run_seed_with_path_capture(self, era=None):
        """Call seed_organizations and return the path that open() saw."""
        from engine.organizations import seed_organizations

        captured_paths = []
        original_open = open

        def capturing_open(path, *args, **kwargs):
            # Only capture organizations.yaml opens; let other reads through.
            if "organizations.yaml" in str(path):
                captured_paths.append(str(path))
            return original_open(path, *args, **kwargs)

        # Stub out DB calls — we only care about which YAML was read.
        # Use side_effect with async fns so each call gets a fresh coroutine.
        org_id_counter = [0]

        async def fake_create_org(**kw):
            org_id_counter[0] += 1
            return org_id_counter[0]

        async def fake_create_rank(**kw):
            return None

        mock_db = MagicMock()
        mock_db.create_organization = fake_create_org
        mock_db.create_org_rank = fake_create_rank

        with patch("builtins.open", side_effect=capturing_open):
            if era is None:
                asyncio.run(seed_organizations(mock_db))
            else:
                asyncio.run(seed_organizations(mock_db, era=era))

        return captured_paths

    def test_default_era_reads_legacy_path(self):
        """No era arg + no registered Config -> reads data/organizations.yaml.

        This is the byte-equivalence guarantee for production.
        """
        paths = self._run_seed_with_path_capture(era=None)
        self.assertTrue(len(paths) >= 1, "Expected at least one yaml open.")
        # The path must be the legacy top-level data/organizations.yaml,
        # NOT data/worlds/<era>/organizations.yaml.
        self.assertTrue(
            any(p.endswith(os.path.join("data", "organizations.yaml"))
                for p in paths),
            f"Expected legacy data/organizations.yaml read; got {paths}"
        )
        # And it must NOT have read from data/worlds/...
        self.assertFalse(
            any(os.path.join("worlds", "gcw") in p for p in paths),
            f"Did not expect data/worlds/gcw/ read; got {paths}"
        )

    def test_explicit_gcw_era_reads_legacy_path(self):
        """era='gcw' explicit -> reads data/organizations.yaml (legacy)."""
        paths = self._run_seed_with_path_capture(era="gcw")
        self.assertTrue(len(paths) >= 1)
        self.assertTrue(
            any(p.endswith(os.path.join("data", "organizations.yaml"))
                for p in paths),
            f"Expected legacy data/organizations.yaml; got {paths}"
        )

    def test_clone_wars_era_reads_cw_path(self):
        """era='clone_wars' -> reads data/worlds/clone_wars/organizations.yaml.

        Asymmetric gate: pre-wiring this test fails because
        seed_organizations always reads data/organizations.yaml. Post-
        wiring it passes.
        """
        paths = self._run_seed_with_path_capture(era="clone_wars")
        self.assertTrue(len(paths) >= 1)
        cw_path = os.path.join("worlds", "clone_wars", "organizations.yaml")
        self.assertTrue(
            any(cw_path in p for p in paths),
            f"Expected CW path {cw_path!r} in {paths}"
        )
        # Must NOT have read the legacy GCW path.
        self.assertFalse(
            any(p.endswith(os.path.join("data", "organizations.yaml"))
                for p in paths),
            f"Did not expect legacy GCW read for CW era; got {paths}"
        )

    def test_registered_config_clone_wars_reads_cw_path(self):
        """No explicit era + CW Config registered -> reads CW path."""
        from engine.era_state import set_active_config
        set_active_config(_make_cfg(active_era="clone_wars"))

        paths = self._run_seed_with_path_capture(era=None)
        cw_path = os.path.join("worlds", "clone_wars", "organizations.yaml")
        self.assertTrue(
            any(cw_path in p for p in paths),
            f"Expected CW path {cw_path!r} in {paths}"
        )


class TestSeedOrganizationsByteEquivalence(unittest.TestCase):
    """For era='gcw' (default), seed_organizations must produce the SAME
    DB writes as before the drop landed.

    Strategy: snapshot the sequence of (org_code, rank_count) tuples that
    seed_organizations emits when reading the legacy YAML, and assert
    the seam path produces the same sequence.
    """

    def setUp(self):
        _reset_era_state()

    def tearDown(self):
        _reset_era_state()

    def _capture_org_writes(self, era=None):
        """Run seed_organizations with mock DB and capture create_organization
        calls."""
        from engine.organizations import seed_organizations

        org_writes = []
        rank_writes = []

        async def fake_create_org(**kw):
            org_writes.append((kw["code"], kw["name"], kw["org_type"]))
            return len(org_writes)  # fake org_id

        async def fake_create_rank(**kw):
            rank_writes.append((kw["org_id"], kw["rank_level"], kw["title"]))

        mock_db = MagicMock()
        mock_db.create_organization = fake_create_org
        mock_db.create_org_rank = fake_create_rank

        if era is None:
            asyncio.run(seed_organizations(mock_db))
        else:
            asyncio.run(seed_organizations(mock_db, era=era))

        return org_writes, rank_writes

    def test_gcw_default_produces_expected_factions(self):
        """era=gcw (default) seeds the legacy GCW factions: empire, rebel,
        hutt, independent."""
        orgs, ranks = self._capture_org_writes(era=None)
        org_codes = {o[0] for o in orgs}
        for required in ("empire", "rebel", "hutt", "independent"):
            self.assertIn(required, org_codes,
                          f"GCW seed must include {required}; got {org_codes}")

    def test_clone_wars_produces_expected_factions(self):
        """era=clone_wars seeds CW factions: republic, cis, jedi_order, etc."""
        orgs, ranks = self._capture_org_writes(era="clone_wars")
        org_codes = {o[0] for o in orgs}
        # From data/worlds/clone_wars/organizations.yaml:
        # republic, cis, jedi_order, hutt_cartel, independent, bhg
        self.assertIn("republic", org_codes,
                      f"CW seed must include republic; got {org_codes}")
        self.assertIn("jedi_order", org_codes,
                      f"CW seed must include jedi_order; got {org_codes}")
        # Must NOT have the GCW empire/rebel.
        self.assertNotIn("empire", org_codes,
                         f"CW seed must NOT include empire; got {org_codes}")
        self.assertNotIn("rebel", org_codes,
                         f"CW seed must NOT include rebel; got {org_codes}")

    def test_gcw_byte_equiv_default_vs_explicit(self):
        """seed(era=None) and seed(era='gcw') produce IDENTICAL output."""
        orgs_default, ranks_default = self._capture_org_writes(era=None)
        orgs_gcw, ranks_gcw = self._capture_org_writes(era="gcw")
        self.assertEqual(orgs_default, orgs_gcw,
                         "Default-era and explicit-gcw must be byte-identical.")
        self.assertEqual(ranks_default, ranks_gcw,
                         "Default-era and explicit-gcw rank writes must match.")


class TestSeedOrganizationsMissingFile(unittest.TestCase):
    """If an era's organizations.yaml is missing, seed must log and skip
    (not crash). Mirrors current behavior for the legacy path."""

    def setUp(self):
        _reset_era_state()

    def tearDown(self):
        _reset_era_state()

    def test_missing_file_skips_gracefully(self):
        """era pointing at non-existent dir -> warning logged, no exception."""
        from engine.organizations import seed_organizations
        mock_db = MagicMock()

        # Should not raise.
        try:
            asyncio.run(seed_organizations(mock_db, era="bogus_era_xyz"))
        except Exception as e:
            self.fail(f"seed_organizations raised on missing file: {e}")

        mock_db.create_organization.assert_not_called()


# ──────────────────────────────────────────────────────────────────────
# Entry
# ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main()
