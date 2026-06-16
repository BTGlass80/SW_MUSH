# -*- coding: utf-8 -*-
"""
tests/test_t3_19_tunables_foundation.py — T3.19 Phase 0: tunables foundation.

Tests:
  1. TestLoadTunables  — empty YAML, missing file, valid knobs, bad YAML,
                         non-mapping top-level all behave correctly.
  2. TestGetTunable    — key present, key absent (default), type preservation.
  3. TestBootWiring    — game_server.py imports engine.tunables.load_tunables.
"""
from __future__ import annotations

import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.tunables import load_tunables, get_tunable, reset_tunables


class TestLoadTunables(unittest.TestCase):

    def setUp(self):
        reset_tunables()

    def tearDown(self):
        reset_tunables()

    def test_empty_yaml_loads_cleanly(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write("{}\n")
            path = f.name
        load_tunables(path)
        self.assertIsNone(get_tunable("any.key"))

    def test_none_yaml_loads_cleanly(self):
        """A YAML file that is entirely empty (None from safe_load) is a no-op."""
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write("")
            path = f.name
        load_tunables(path)
        self.assertIsNone(get_tunable("any.key"))

    def test_missing_file_is_noop(self):
        load_tunables("/nonexistent/path/tunables.yaml")
        self.assertIsNone(get_tunable("trade.price_demand_multiplier"))

    def test_valid_knobs_round_trip(self):
        yaml_content = textwrap.dedent("""\
            trade.price_demand_multiplier: 1.40
            bounty.reward_superior_max: 10000
            commissary.sellback_rate: 0.50
        """)
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write(yaml_content)
            path = f.name
        load_tunables(path)
        self.assertAlmostEqual(get_tunable("trade.price_demand_multiplier"), 1.40)
        self.assertEqual(get_tunable("bounty.reward_superior_max"), 10000)
        self.assertAlmostEqual(get_tunable("commissary.sellback_rate"), 0.50)

    def test_bad_yaml_is_noop(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write(": : : bad yaml [[[")
            path = f.name
        load_tunables(path)
        self.assertIsNone(get_tunable("any.key"))

    def test_non_mapping_top_level_is_noop(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write("- item1\n- item2\n")
            path = f.name
        load_tunables(path)
        self.assertIsNone(get_tunable("any.key"))

    def test_reload_replaces_previous_tunables(self):
        yaml_v1 = "trade.price_demand_multiplier: 1.40\n"
        yaml_v2 = "trade.price_demand_multiplier: 1.50\n"
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write(yaml_v1)
            path = f.name
        load_tunables(path)
        self.assertAlmostEqual(get_tunable("trade.price_demand_multiplier"), 1.40)
        with open(path, "w", encoding="utf-8") as f:
            f.write(yaml_v2)
        load_tunables(path)
        self.assertAlmostEqual(get_tunable("trade.price_demand_multiplier"), 1.50)

    def test_default_path_file_exists_and_is_valid_yaml(self):
        """data/tunables.yaml exists and parses without error."""
        default_path = PROJECT_ROOT / "data" / "tunables.yaml"
        self.assertTrue(default_path.exists(), "data/tunables.yaml must exist")
        load_tunables(str(default_path))
        # Phase 1 (2026-06-15): the HIGH-priority economy cluster now ships in
        # the YAML at its in-code defaults (behavior-identical to omitting it).
        self.assertAlmostEqual(get_tunable("trade.price_demand_multiplier"), 1.40,
                               msg="Phase 1: economy cluster externalized to the YAML")
        self.assertEqual(get_tunable("p2p.tax_pct"), 5)
        reset_tunables()  # don't leak the real file's knobs into later tests


class TestGetTunable(unittest.TestCase):

    def setUp(self):
        reset_tunables()

    def tearDown(self):
        reset_tunables()

    def test_key_absent_returns_none(self):
        self.assertIsNone(get_tunable("missing.key"))

    def test_key_absent_returns_custom_default(self):
        self.assertEqual(get_tunable("missing.key", 42), 42)

    def test_float_preserved(self):
        yaml_text = "trade.price_source_multiplier: 0.70\n"
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write(yaml_text)
            path = f.name
        load_tunables(path)
        val = get_tunable("trade.price_source_multiplier", 0.70)
        self.assertIsInstance(val, float)
        self.assertAlmostEqual(val, 0.70)

    def test_int_preserved(self):
        yaml_text = "trade.supply_max_luxury_goods: 6\n"
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w",
                                        delete=False, encoding="utf-8") as f:
            f.write(yaml_text)
            path = f.name
        load_tunables(path)
        val = get_tunable("trade.supply_max_luxury_goods", 6)
        self.assertIsInstance(val, int)
        self.assertEqual(val, 6)

    def test_hardcoded_default_unchanged_when_key_absent(self):
        """Canonical usage: call site passes its own literal as default."""
        val = get_tunable("trade.price_demand_multiplier", 1.40)
        self.assertAlmostEqual(val, 1.40)


class TestBootWiring(unittest.TestCase):

    def test_game_server_imports_load_tunables(self):
        """game_server.py must contain the load_tunables boot call."""
        gs_path = PROJECT_ROOT / "server" / "game_server.py"
        src = gs_path.read_text(encoding="utf-8")
        self.assertIn("load_tunables", src)
        self.assertIn("engine.tunables", src)

    def test_tunables_yaml_mentioned_in_game_server(self):
        gs_path = PROJECT_ROOT / "server" / "game_server.py"
        src = gs_path.read_text(encoding="utf-8")
        self.assertIn("tunables.yaml", src)


if __name__ == "__main__":
    unittest.main()
