# -*- coding: utf-8 -*-
"""
tests/test_achievements_unit.py — Code review C6 fix tests

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`achievements.py` was on the priority list because it tracks
progression — a regression here would silently break milestone
rewards. This file adds unit-test coverage of the pure /
deterministic surface:

  - CATEGORY_ORDER and CATEGORY_LABELS consistency
  - load_achievements with the live data/achievements.yaml
  - load_achievements with a synthetic YAML in a temp directory
  - get_all_achievements / get_achievement lookup
  - _matches_filters predicate (zone filter)
  - _BY_EVENT indexing populated correctly
  - Per-achievement field invariants on the live data

Async / DB-bound surface (`check_achievement`,
`_complete_achievement`, all the `on_*` event handlers,
`get_achievements_status`) is left to integration tests with a real
DB. Out of scope for this unit-test drop.
"""
import os
import sys
import textwrap
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import achievements as ach_module  # noqa: E402
from engine.achievements import (  # noqa: E402
    CATEGORY_ORDER,
    CATEGORY_LABELS,
    load_achievements,
    get_all_achievements,
    get_achievement,
    _matches_filters,
)


# ══════════════════════════════════════════════════════════════════════════════
# Category constants
# ══════════════════════════════════════════════════════════════════════════════


class TestCategoryConstants(unittest.TestCase):
    def test_every_ordered_category_has_label(self):
        for cat in CATEGORY_ORDER:
            self.assertIn(cat, CATEGORY_LABELS,
                          f"category {cat!r} in CATEGORY_ORDER but not LABELS")

    def test_every_label_has_category_in_order(self):
        for cat in CATEGORY_LABELS:
            self.assertIn(cat, CATEGORY_ORDER,
                          f"category {cat!r} in LABELS but not CATEGORY_ORDER")

    def test_no_duplicate_categories_in_order(self):
        self.assertEqual(len(CATEGORY_ORDER), len(set(CATEGORY_ORDER)))

    def test_labels_are_title_case_strings(self):
        for cat, label in CATEGORY_LABELS.items():
            self.assertIsInstance(label, str)
            self.assertTrue(label,
                            f"category {cat!r} has empty label")
            # First char should be uppercase
            self.assertTrue(label[0].isupper(),
                            f"label {label!r} for {cat!r} not title case")


# ══════════════════════════════════════════════════════════════════════════════
# load_achievements — live data
# ══════════════════════════════════════════════════════════════════════════════


class TestLoadAchievementsLive(unittest.TestCase):
    """Tests against the real data/achievements.yaml."""

    def setUp(self):
        # Reset module state between tests so we don't carry
        # state across tests.
        ach_module._ACHIEVEMENTS = []
        ach_module._BY_KEY = {}
        ach_module._BY_EVENT = {}

    def test_live_yaml_loads_nonempty(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        n = load_achievements()
        self.assertGreater(n, 0,
                           "live achievements.yaml should load >= 1 entries")

    def test_live_yaml_each_entry_has_required_fields(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        for ach in get_all_achievements():
            self.assertIn("key", ach)
            self.assertIn("name", ach)
            self.assertIn("category", ach)
            self.assertIn("trigger", ach)
            self.assertIsInstance(ach["trigger"], dict)

    def test_live_yaml_no_duplicate_keys(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        keys = [a["key"] for a in get_all_achievements()]
        self.assertEqual(
            len(keys), len(set(keys)),
            f"duplicate keys: {[k for k in keys if keys.count(k) > 1]}"
        )

    def test_live_yaml_categories_are_known(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        known = set(CATEGORY_ORDER) | {"misc"}
        for ach in get_all_achievements():
            self.assertIn(
                ach["category"], known,
                f"{ach['key']}: unknown category {ach['category']!r}"
            )

    def test_live_yaml_cp_rewards_are_nonnegative(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        for ach in get_all_achievements():
            self.assertGreaterEqual(
                ach.get("cp_reward", 0), 0,
                f"{ach['key']}: negative cp_reward"
            )

    def test_live_yaml_requires_chains_resolve(self):
        """If achievement A 'requires' B, then B must also be defined.
        Catches dangling prerequisite references."""
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        all_keys = {a["key"] for a in get_all_achievements()}
        for ach in get_all_achievements():
            req = ach.get("requires")
            if req is not None:
                self.assertIn(
                    req, all_keys,
                    f"{ach['key']}: requires={req!r} not in defined keys"
                )

    def test_get_achievement_returns_known_key(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        all_achs = get_all_achievements()
        if not all_achs:
            self.skipTest("no achievements loaded")
        first = all_achs[0]
        looked_up = get_achievement(first["key"])
        self.assertIsNotNone(looked_up)
        self.assertEqual(looked_up["key"], first["key"])

    def test_get_achievement_returns_none_for_unknown(self):
        live = Path(PROJECT_ROOT) / "data" / "achievements.yaml"
        if not live.is_file():
            self.skipTest("data/achievements.yaml not present")
        load_achievements()
        self.assertIsNone(get_achievement("__nonexistent_xyz_key__"))


# ══════════════════════════════════════════════════════════════════════════════
# load_achievements — synthetic YAML
# ══════════════════════════════════════════════════════════════════════════════


class TestLoadAchievementsSynthetic(unittest.TestCase):
    """Tests with a temp YAML so we can exercise the loader's edge cases
    without polluting (or depending on) the live data file."""

    def setUp(self):
        ach_module._ACHIEVEMENTS = []
        ach_module._BY_KEY = {}
        ach_module._BY_EVENT = {}

    def _load_synthetic(self, body: str) -> int:
        """Write `body` to a temp file at the location load_achievements
        looks at (relative to engine/), then call load_achievements.
        Returns the count loaded.
        """
        with TemporaryDirectory() as td:
            data_dir = Path(td) / "data"
            data_dir.mkdir()
            yaml_path = data_dir / "achievements.yaml"
            yaml_path.write_text(textwrap.dedent(body).lstrip("\n"))
            # Patch __file__ so the loader resolves to our temp path
            fake_engine = Path(td) / "engine" / "achievements.py"
            fake_engine.parent.mkdir()
            fake_engine.write_text("# stub\n")
            with patch.object(ach_module, "__file__", str(fake_engine)):
                return load_achievements()

    def test_loads_two_achievements_from_synthetic_yaml(self):
        body = """
            achievements:
              - key: alpha
                name: Alpha
                description: First test
                category: combat
                cp_reward: 1
                trigger: { event: foo, count: 1 }
              - key: beta
                name: Beta
                description: Second test
                category: combat
                cp_reward: 2
                trigger: { event: foo, count: 5 }
        """
        n = self._load_synthetic(body)
        self.assertEqual(n, 2)
        self.assertEqual(len(get_all_achievements()), 2)

    def test_missing_yaml_returns_zero(self):
        with TemporaryDirectory() as td:
            fake_engine = Path(td) / "engine" / "achievements.py"
            fake_engine.parent.mkdir()
            fake_engine.write_text("# stub\n")
            with patch.object(ach_module, "__file__", str(fake_engine)):
                # No data/achievements.yaml in td
                n = load_achievements()
            self.assertEqual(n, 0)

    def test_empty_achievements_list_returns_zero(self):
        n = self._load_synthetic("achievements: []\n")
        self.assertEqual(n, 0)

    def test_entry_without_key_is_skipped(self):
        body = """
            achievements:
              - name: "no key here"
                trigger: { event: foo }
              - key: gamma
                name: Gamma
                trigger: { event: foo, count: 1 }
        """
        n = self._load_synthetic(body)
        self.assertEqual(n, 1)
        keys = {a["key"] for a in get_all_achievements()}
        self.assertEqual(keys, {"gamma"})

    def test_by_event_index_populated(self):
        body = """
            achievements:
              - key: a
                name: A
                trigger: { event: shoot_blaster, count: 1 }
              - key: b
                name: B
                trigger: { event: shoot_blaster, count: 5 }
              - key: c
                name: C
                trigger: { event: drink_juma, count: 1 }
        """
        self._load_synthetic(body)
        self.assertIn("shoot_blaster", ach_module._BY_EVENT)
        self.assertIn("drink_juma", ach_module._BY_EVENT)
        self.assertEqual(len(ach_module._BY_EVENT["shoot_blaster"]), 2)
        self.assertEqual(len(ach_module._BY_EVENT["drink_juma"]), 1)

    def test_entry_with_no_event_isnt_in_by_event_index(self):
        body = """
            achievements:
              - key: weird
                name: Weird
                trigger: {}
        """
        n = self._load_synthetic(body)
        self.assertEqual(n, 1)
        self.assertEqual(ach_module._BY_EVENT, {})

    def test_default_field_values(self):
        body = """
            achievements:
              - key: minimal
                trigger: { event: foo }
        """
        self._load_synthetic(body)
        a = get_achievement("minimal")
        self.assertIsNotNone(a)
        self.assertEqual(a["name"], "minimal")  # falls back to key
        self.assertEqual(a["description"], "")
        self.assertEqual(a["category"], "misc")
        self.assertEqual(a["icon"], "●")
        self.assertEqual(a["cp_reward"], 0)
        self.assertIsNone(a["requires"])


# ══════════════════════════════════════════════════════════════════════════════
# _matches_filters predicate
# ══════════════════════════════════════════════════════════════════════════════


class TestMatchesFilters(unittest.TestCase):
    def test_no_filter_always_matches(self):
        self.assertTrue(_matches_filters({}, {}))
        self.assertTrue(_matches_filters({}, {"zone": "spaceport"}))
        self.assertTrue(_matches_filters(
            {"event": "foo"}, {"zone": "anywhere"}
        ))

    def test_zone_filter_matches_when_equal(self):
        self.assertTrue(_matches_filters(
            {"zone": "spaceport"}, {"zone": "spaceport"}
        ))

    def test_zone_filter_rejects_when_different(self):
        self.assertFalse(_matches_filters(
            {"zone": "spaceport"}, {"zone": "cantina"}
        ))

    def test_zone_filter_rejects_when_missing_in_kwargs(self):
        self.assertFalse(_matches_filters(
            {"zone": "spaceport"}, {}
        ))

    def test_zone_filter_rejects_when_kwarg_value_is_none(self):
        self.assertFalse(_matches_filters(
            {"zone": "spaceport"}, {"zone": None}
        ))


if __name__ == "__main__":
    unittest.main()
