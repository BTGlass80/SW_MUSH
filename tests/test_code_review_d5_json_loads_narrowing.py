# -*- coding: utf-8 -*-
"""
tests/test_code_review_d5_json_loads_narrowing.py — Code review D5 fix tests

Per code_review_session32.md Severity D5 ("Unprotected json.loads()
calls"): broad `except Exception:` blocks around `json.loads` were
narrowed to `except (json.JSONDecodeError, TypeError, ...)` and a
warning log was added so DB corruption surfaces instead of silently
producing empty data.

This drop covered the 3 sites that were too broad:
  - engine/area_map.py:_parse_room_props
  - engine/area_map.py service-detection block
  - engine/buffs.py:_get_buffs

The other 8 json.loads sites surveyed in the same review (character.py,
cooldowns.py, crafting.py — 8 sites) already used the narrow guard
pattern and a `bounty_board.py` site was left broad on purpose because
the catch covers BountyContract.from_dict shape errors as well. See the
handoff doc for the full audit table.

Coverage:
  - test_area_map_parse_room_props_handles_malformed_json
  - test_area_map_parse_room_props_handles_non_string_input
  - test_area_map_parse_room_props_handles_valid_json
  - test_buffs_get_buffs_handles_malformed_json
  - test_buffs_get_buffs_handles_corrupt_buff_dict
  - test_buffs_get_buffs_handles_valid_input
  - test_area_map_logs_warning_on_corruption
  - test_buffs_logs_warning_on_corruption
"""
import json
import logging
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.area_map import _parse_room_props  # noqa: E402
from engine.buffs import _get_buffs  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════════
# area_map._parse_room_props
# ══════════════════════════════════════════════════════════════════════════════


class TestAreaMapParseRoomProps(unittest.TestCase):
    def test_area_map_parse_room_props_handles_malformed_json(self):
        result = _parse_room_props({"id": 1, "properties": "NOT_VALID_JSON"})
        self.assertEqual(result, {})

    def test_area_map_parse_room_props_handles_non_string_input(self):
        # When properties is already a dict, no JSON parse is needed
        result = _parse_room_props({
            "id": 2, "properties": {"environment": "tundra"},
        })
        self.assertEqual(result, {"environment": "tundra"})

    def test_area_map_parse_room_props_handles_valid_json(self):
        payload = json.dumps({"environment": "desert", "lit": True})
        result = _parse_room_props({"id": 3, "properties": payload})
        self.assertEqual(result, {"environment": "desert", "lit": True})

    def test_area_map_parse_room_props_handles_empty_string(self):
        # Empty string is invalid JSON
        result = _parse_room_props({"id": 4, "properties": ""})
        self.assertEqual(result, {})

    def test_area_map_parse_room_props_handles_missing_field(self):
        # row.get("properties", "{}") default is "{}", which IS valid JSON
        result = _parse_room_props({"id": 5})
        self.assertEqual(result, {})


# ══════════════════════════════════════════════════════════════════════════════
# buffs._get_buffs
# ══════════════════════════════════════════════════════════════════════════════


class TestBuffsGetBuffs(unittest.TestCase):
    def test_buffs_get_buffs_handles_malformed_json(self):
        result = _get_buffs({"id": 100, "attributes": "NOT_VALID_JSON"})
        self.assertEqual(result, [])

    def test_buffs_get_buffs_handles_corrupt_buff_dict(self):
        # active_buffs entries that aren't dicts get filtered out; entries
        # that are dicts but with missing/wrong fields make Buff.from_dict
        # raise a KeyError or TypeError. The narrowed except catches
        # TypeError + ValueError so corruption returns [] without crashing.
        attrs = json.dumps({"active_buffs": ["not_a_dict", 42, None]})
        result = _get_buffs({"id": 101, "attributes": attrs})
        self.assertEqual(result, [])

    def test_buffs_get_buffs_handles_valid_input(self):
        # Empty active_buffs is the no-op base case
        attrs = json.dumps({"active_buffs": []})
        result = _get_buffs({"id": 102, "attributes": attrs})
        self.assertEqual(result, [])

    def test_buffs_get_buffs_handles_missing_attributes_field(self):
        # No 'attributes' key → defaults to "{}" → empty buff list
        result = _get_buffs({"id": 103})
        self.assertEqual(result, [])

    def test_buffs_get_buffs_handles_dict_attributes_already_parsed(self):
        # Some callers pass attributes as a dict, not JSON string
        result = _get_buffs({"id": 104, "attributes": {"active_buffs": []}})
        self.assertEqual(result, [])


# ══════════════════════════════════════════════════════════════════════════════
# Logging — corruption must be visible, not silent
# ══════════════════════════════════════════════════════════════════════════════


class _CapturingHandler(logging.Handler):
    """Captures log records so we can assert on them."""
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class TestCorruptionLogging(unittest.TestCase):
    def setUp(self):
        self.handler = _CapturingHandler()
        # Attach to both engine.area_map and engine.buffs loggers
        self.area_logger = logging.getLogger("engine.area_map")
        self.buffs_logger = logging.getLogger("engine.buffs")
        self.area_logger.addHandler(self.handler)
        self.buffs_logger.addHandler(self.handler)
        self.area_logger.setLevel(logging.WARNING)
        self.buffs_logger.setLevel(logging.WARNING)

    def tearDown(self):
        self.area_logger.removeHandler(self.handler)
        self.buffs_logger.removeHandler(self.handler)

    def test_area_map_logs_warning_on_corruption(self):
        _parse_room_props({"id": 999, "properties": "BAD JSON"})
        warnings = [r for r in self.handler.records
                    if r.levelno == logging.WARNING and "area_map" in r.name]
        self.assertEqual(len(warnings), 1)
        msg = warnings[0].getMessage()
        self.assertIn("999", msg, "log should include room id for diagnosis")
        self.assertIn("Malformed", msg)

    def test_buffs_logs_warning_on_corruption(self):
        _get_buffs({"id": 888, "attributes": "BAD JSON"})
        warnings = [r for r in self.handler.records
                    if r.levelno == logging.WARNING and "buffs" in r.name]
        self.assertEqual(len(warnings), 1)
        msg = warnings[0].getMessage()
        self.assertIn("888", msg, "log should include char id for diagnosis")

    def test_no_log_on_valid_input(self):
        _parse_room_props({"id": 1, "properties": "{}"})
        _get_buffs({"id": 2, "attributes": "{}"})
        warnings = [r for r in self.handler.records
                    if r.levelno == logging.WARNING]
        self.assertEqual(warnings, [],
                         "valid input must not produce warnings")


if __name__ == "__main__":
    unittest.main()
