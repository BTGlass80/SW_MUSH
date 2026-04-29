# -*- coding: utf-8 -*-
"""
tests/test_json_safe.py — Drop K-D5b tests

Exercises engine/json_safe.py:
    safe_json_loads(raw, default, context=None)
    load_ship_systems(ship)
    load_json_field(row, field, default, row_id_key="id")

Coverage:
  - Valid JSON parses correctly
  - None / empty string returns default silently
  - Already-parsed dict/list passes through
  - Malformed JSON returns default and logs warning
  - load_ship_systems coerces non-dict JSON to {}
  - load_ship_systems handles missing 'systems' field
  - load_json_field reads the right column and uses the right id key
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

from engine.json_safe import (  # noqa: E402
    safe_json_loads,
    load_ship_systems,
    load_json_field,
)


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class _LogCaptureBase(unittest.TestCase):
    def setUp(self):
        self.handler = _CapturingHandler()
        self.logger = logging.getLogger("engine.json_safe")
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.WARNING)

    def tearDown(self):
        self.logger.removeHandler(self.handler)

    def warnings(self):
        return [r for r in self.handler.records
                if r.levelno == logging.WARNING]


# ══════════════════════════════════════════════════════════════════════════════
# safe_json_loads
# ══════════════════════════════════════════════════════════════════════════════


class TestSafeJsonLoads(_LogCaptureBase):
    def test_valid_json_parses(self):
        self.assertEqual(safe_json_loads('{"a": 1}'), {"a": 1})
        self.assertEqual(safe_json_loads("[1,2,3]"), [1, 2, 3])
        self.assertEqual(safe_json_loads('"hello"'), "hello")
        self.assertEqual(self.warnings(), [])

    def test_none_returns_default_silently(self):
        self.assertEqual(safe_json_loads(None, default={}), {})
        self.assertIsNone(safe_json_loads(None))
        self.assertEqual(self.warnings(), [])

    def test_empty_string_returns_default_silently(self):
        self.assertEqual(safe_json_loads("", default=[]), [])
        self.assertEqual(self.warnings(), [])

    def test_already_parsed_dict_passes_through(self):
        d = {"key": "value"}
        self.assertIs(safe_json_loads(d, default={}), d)
        self.assertEqual(self.warnings(), [])

    def test_already_parsed_list_passes_through(self):
        lst = [1, 2, 3]
        self.assertIs(safe_json_loads(lst, default=[]), lst)
        self.assertEqual(self.warnings(), [])

    def test_malformed_json_returns_default_and_logs(self):
        result = safe_json_loads("NOT VALID JSON", default={})
        self.assertEqual(result, {})
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("Parse failed", warnings[0].getMessage())

    def test_context_appears_in_warning_message(self):
        safe_json_loads("BAD", default={}, context="ship 42 systems")
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("ship 42 systems", warnings[0].getMessage())

    def test_no_context_omits_source_identifier(self):
        safe_json_loads("BAD", default={})
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        # Without context, message says "Parse failed:" not "Parse failed for X:"
        self.assertIn("Parse failed:", warnings[0].getMessage())
        self.assertNotIn("Parse failed for", warnings[0].getMessage())

    def test_default_default_is_none(self):
        # If caller doesn't specify default, default is None
        self.assertIsNone(safe_json_loads("BAD"))


# ══════════════════════════════════════════════════════════════════════════════
# load_ship_systems
# ══════════════════════════════════════════════════════════════════════════════


class TestLoadShipSystems(_LogCaptureBase):
    def test_valid_ship_systems_parses(self):
        ship = {"id": 1, "systems": json.dumps({"hull": 100, "shields": 50})}
        result = load_ship_systems(ship)
        self.assertEqual(result, {"hull": 100, "shields": 50})

    def test_missing_systems_returns_empty_dict(self):
        ship = {"id": 1}
        result = load_ship_systems(ship)
        self.assertEqual(result, {})
        # No warning — missing field is the routine case
        self.assertEqual(self.warnings(), [])

    def test_none_systems_returns_empty_dict(self):
        ship = {"id": 1, "systems": None}
        self.assertEqual(load_ship_systems(ship), {})
        self.assertEqual(self.warnings(), [])

    def test_empty_systems_returns_empty_dict(self):
        ship = {"id": 1, "systems": ""}
        self.assertEqual(load_ship_systems(ship), {})
        self.assertEqual(self.warnings(), [])

    def test_malformed_systems_logs_warning_with_ship_id(self):
        ship = {"id": 99, "systems": "NOT JSON"}
        result = load_ship_systems(ship)
        self.assertEqual(result, {})
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("ship 99", warnings[0].getMessage())

    def test_already_parsed_dict_passes_through(self):
        ship = {"id": 1, "systems": {"hull": 100}}
        result = load_ship_systems(ship)
        self.assertEqual(result, {"hull": 100})
        self.assertEqual(self.warnings(), [])

    def test_non_dict_json_coerces_to_empty(self):
        # Some bug or hand-edit made systems an array instead of dict
        ship = {"id": 7, "systems": json.dumps([1, 2, 3])}
        result = load_ship_systems(ship)
        self.assertEqual(result, {})
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("not a dict", warnings[0].getMessage())
        # Match either "Ship 7" (capitalized in coercion warning) or
        # "ship 7" (lowercase in parse-failure warning)
        self.assertIn("7", warnings[0].getMessage())

    def test_aiosqlite_row_with_get_method_works(self):
        # aiosqlite Row objects have a get() method but are not dicts
        class FakeRow:
            def __init__(self, **kw):
                self._d = kw
            def get(self, k, default=None):
                return self._d.get(k, default)
        row = FakeRow(id=42, systems=json.dumps({"hull": 75}))
        result = load_ship_systems(row)
        self.assertEqual(result, {"hull": 75})


# ══════════════════════════════════════════════════════════════════════════════
# load_json_field
# ══════════════════════════════════════════════════════════════════════════════


class TestLoadJsonField(_LogCaptureBase):
    def test_reads_specified_field(self):
        row = {"id": 1, "equipment": json.dumps(["sword", "shield"])}
        result = load_json_field(row, "equipment", default=[])
        self.assertEqual(result, ["sword", "shield"])

    def test_missing_field_returns_default(self):
        row = {"id": 1}
        self.assertEqual(load_json_field(row, "equipment", default=[]), [])

    def test_default_none_when_unspecified(self):
        self.assertIsNone(load_json_field({}, "x"))

    def test_corruption_warning_includes_row_id_key(self):
        row = {"char_id": 555, "attrs": "BROKEN"}
        load_json_field(row, "attrs", default={}, row_id_key="char_id")
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        msg = warnings[0].getMessage()
        self.assertIn("char_id=555", msg)
        self.assertIn("attrs", msg)

    def test_default_row_id_key_is_id(self):
        row = {"id": 100, "data": "BAD"}
        load_json_field(row, "data", default={})
        warnings = self.warnings()
        self.assertEqual(len(warnings), 1)
        self.assertIn("id=100", warnings[0].getMessage())


if __name__ == "__main__":
    unittest.main()
