# -*- coding: utf-8 -*-
"""
tests/test_f6a5b_era_state.py — Drop F.6a.5b (era-state scaffolding) tests

Exercises engine/era_state.py + the two new fields on server/config.py
(active_era, use_yaml_director_data).

Coverage:
  - test_default_era_when_no_config_is_gcw
  - test_default_use_yaml_when_no_config_is_false
  - test_default_resolve_for_seeding_is_none
  - test_set_active_config_changes_resolution
  - test_clear_active_config_restores_defaults
  - test_explicit_cfg_overrides_registered
  - test_resolve_for_seeding_returns_era_when_flag_on
  - test_resolve_for_seeding_returns_none_when_flag_off
  - test_real_config_defaults_match_module_defaults
  - test_invalid_era_type_falls_back_to_default
  - test_invalid_use_yaml_type_falls_back_to_default
  - test_empty_string_era_falls_back_to_default
  - test_get_active_era_with_missing_attribute_returns_default
"""
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.era_state import (  # noqa: E402
    get_active_era,
    use_yaml_director_data,
    resolve_era_for_seeding,
    set_active_config,
    clear_active_config,
    _DEFAULT_ERA,
    _DEFAULT_USE_YAML,
)


class _CfgStub:
    """Duck-typed stand-in for server.config.Config. Only the two fields
    era_state cares about exist."""

    def __init__(self, era="gcw", use_yaml=False):
        self.active_era = era
        self.use_yaml_director_data = use_yaml


class _EraStateTestBase(unittest.TestCase):
    """Reset the module-level active config before & after each test
    so test order doesn't leak state."""

    def setUp(self):
        clear_active_config()

    def tearDown(self):
        clear_active_config()


class TestDefaults(_EraStateTestBase):
    def test_default_era_when_no_config_is_gcw(self):
        self.assertEqual(get_active_era(), "gcw")
        self.assertEqual(get_active_era(), _DEFAULT_ERA)

    def test_default_use_yaml_when_no_config_is_false(self):
        self.assertFalse(use_yaml_director_data())
        self.assertEqual(use_yaml_director_data(), _DEFAULT_USE_YAML)

    def test_default_resolve_for_seeding_is_none(self):
        self.assertIsNone(resolve_era_for_seeding())


class TestRegisteredConfig(_EraStateTestBase):
    def test_set_active_config_changes_resolution(self):
        cfg = _CfgStub(era="clone_wars", use_yaml=True)
        set_active_config(cfg)
        self.assertEqual(get_active_era(), "clone_wars")
        self.assertTrue(use_yaml_director_data())

    def test_clear_active_config_restores_defaults(self):
        set_active_config(_CfgStub(era="clone_wars", use_yaml=True))
        clear_active_config()
        self.assertEqual(get_active_era(), _DEFAULT_ERA)
        self.assertFalse(use_yaml_director_data())

    def test_set_active_config_to_none_is_clear(self):
        set_active_config(_CfgStub(era="clone_wars", use_yaml=True))
        set_active_config(None)
        self.assertEqual(get_active_era(), _DEFAULT_ERA)


class TestExplicitCfgOverride(_EraStateTestBase):
    def test_explicit_cfg_overrides_registered(self):
        registered = _CfgStub(era="gcw", use_yaml=False)
        set_active_config(registered)
        explicit = _CfgStub(era="clone_wars", use_yaml=True)
        # Explicit cfg argument wins
        self.assertEqual(get_active_era(explicit), "clone_wars")
        self.assertTrue(use_yaml_director_data(explicit))
        # Registered config is unchanged
        self.assertEqual(get_active_era(), "gcw")
        self.assertFalse(use_yaml_director_data())


class TestResolveForSeeding(_EraStateTestBase):
    def test_resolve_for_seeding_returns_era_when_flag_on(self):
        set_active_config(_CfgStub(era="clone_wars", use_yaml=True))
        self.assertEqual(resolve_era_for_seeding(), "clone_wars")

    def test_resolve_for_seeding_returns_none_when_flag_off(self):
        set_active_config(_CfgStub(era="clone_wars", use_yaml=False))
        self.assertIsNone(resolve_era_for_seeding())

    def test_resolve_for_seeding_with_explicit_cfg(self):
        # Registered = flag off, explicit = flag on → explicit wins
        set_active_config(_CfgStub(era="gcw", use_yaml=False))
        explicit = _CfgStub(era="clone_wars", use_yaml=True)
        self.assertEqual(resolve_era_for_seeding(explicit), "clone_wars")


class TestRealConfigIntegration(_EraStateTestBase):
    def test_real_config_defaults_match_module_defaults(self):
        """The real Config dataclass must default to the same era-state
        the module defaults to. Drift between these would cause a silent
        production regression on first boot after config load.
        """
        from server.config import Config
        cfg = Config()
        self.assertEqual(cfg.active_era, _DEFAULT_ERA)
        self.assertEqual(cfg.use_yaml_director_data, _DEFAULT_USE_YAML)
        # Round-trip through era_state
        self.assertEqual(get_active_era(cfg), _DEFAULT_ERA)
        self.assertEqual(use_yaml_director_data(cfg), _DEFAULT_USE_YAML)
        self.assertIsNone(resolve_era_for_seeding(cfg))

    def test_real_config_can_be_registered(self):
        from server.config import Config
        cfg = Config()
        cfg.active_era = "clone_wars"
        cfg.use_yaml_director_data = True
        set_active_config(cfg)
        self.assertEqual(get_active_era(), "clone_wars")
        self.assertTrue(use_yaml_director_data())


class TestDefensiveTypeChecks(_EraStateTestBase):
    def test_invalid_era_type_falls_back_to_default(self):
        bad = _CfgStub(era=42, use_yaml=False)  # int, not str
        self.assertEqual(get_active_era(bad), _DEFAULT_ERA)

    def test_invalid_use_yaml_type_falls_back_to_default(self):
        bad = _CfgStub(era="gcw", use_yaml="yes")  # str, not bool
        self.assertEqual(use_yaml_director_data(bad), _DEFAULT_USE_YAML)

    def test_empty_string_era_falls_back_to_default(self):
        bad = _CfgStub(era="", use_yaml=False)
        self.assertEqual(get_active_era(bad), _DEFAULT_ERA)

    def test_get_active_era_with_missing_attribute_returns_default(self):
        class NoAttrs:
            pass
        self.assertEqual(get_active_era(NoAttrs()), _DEFAULT_ERA)
        self.assertFalse(use_yaml_director_data(NoAttrs()))


if __name__ == "__main__":
    unittest.main()
