# -*- coding: utf-8 -*-
"""
tests/test_cooldowns_unit.py — Code review C6 fix tests (drop K-C6g)

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`engine/cooldowns.py` is the centralized cooldown handler used by
survey, faction switch, trade, and other systems. A regression here
silently lets players spam actions or get permanently locked out.

Coverage:
  - _parse_attrs: valid JSON, dict already, missing key, corrupt JSON.
  - _write_attrs: round-trip through JSON.
  - remaining_cooldown: ready / live / non-numeric expiry / missing key.
  - check_cooldown: True when expired, False when not.
  - set_cooldown: creates the cooldowns dict, mutates in place,
    returns the same char dict (chaining).
  - clear_cooldown: removes one key, removes empty dict, doesn't
    crash on missing key.
  - clear_all_cooldowns: nukes the whole sub-dict.
  - format_remaining: hours/minutes/seconds bands, "ready" at <=0.
  - Cooldown key constants exist and durations are sane.

The `time.time()` call is patched to make every assertion exact.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import cooldowns as cd_module  # noqa: E402
from engine.cooldowns import (  # noqa: E402
    CD_FACTION_SWITCH,
    CD_SURVEY,
    CD_TRADE,
    FACTION_SWITCH_COOLDOWN_S,
    SURVEY_COOLDOWN_S,
    TRADE_COOLDOWN_S,
    _parse_attrs,
    _write_attrs,
    check_cooldown,
    clear_all_cooldowns,
    clear_cooldown,
    format_remaining,
    remaining_cooldown,
    set_cooldown,
)


def make_char(attrs=None):
    """Build a character dict with JSON-encoded attributes."""
    return {
        "id": 42,
        "attributes": json.dumps(attrs or {}),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Internal helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestParseAttrs(unittest.TestCase):
    def test_parse_valid_json(self):
        char = make_char({"foo": "bar"})
        self.assertEqual(_parse_attrs(char), {"foo": "bar"})

    def test_parse_dict_passthrough(self):
        # If attributes is already a dict (not str), pass through
        char = {"id": 1, "attributes": {"foo": "bar"}}
        self.assertEqual(_parse_attrs(char), {"foo": "bar"})

    def test_parse_missing_attributes_key(self):
        char = {"id": 1}
        self.assertEqual(_parse_attrs(char), {})

    def test_parse_none_attributes(self):
        char = {"id": 1, "attributes": None}
        self.assertEqual(_parse_attrs(char), {})

    def test_parse_empty_string(self):
        char = {"id": 1, "attributes": ""}
        self.assertEqual(_parse_attrs(char), {})

    def test_parse_corrupt_json_returns_empty(self):
        char = {"id": 1, "attributes": "{not json"}
        # Should NOT raise
        result = _parse_attrs(char)
        self.assertEqual(result, {})


class TestWriteAttrs(unittest.TestCase):
    def test_write_round_trips_through_json(self):
        char = {"id": 1, "attributes": "{}"}
        _write_attrs(char, {"foo": "bar"})
        self.assertEqual(json.loads(char["attributes"]), {"foo": "bar"})

    def test_write_overwrites_existing(self):
        char = make_char({"old": "value"})
        _write_attrs(char, {"new": "value"})
        self.assertEqual(json.loads(char["attributes"]), {"new": "value"})


# ══════════════════════════════════════════════════════════════════════════════
# remaining_cooldown
# ══════════════════════════════════════════════════════════════════════════════


class TestRemainingCooldown(unittest.TestCase):
    def test_no_cooldowns_dict_returns_zero(self):
        char = make_char({})
        self.assertEqual(remaining_cooldown(char, "survey"), 0.0)

    def test_missing_key_returns_zero(self):
        char = make_char({"cooldowns": {"other": 9999999999}})
        self.assertEqual(remaining_cooldown(char, "survey"), 0.0)

    def test_expired_cooldown_returns_zero(self):
        # expiry was in the past
        char = make_char({"cooldowns": {"survey": 1000.0}})
        with patch("engine.cooldowns.time.time", return_value=2000.0):
            self.assertEqual(remaining_cooldown(char, "survey"), 0.0)

    def test_live_cooldown_returns_seconds_remaining(self):
        # expiry 60s in the future
        char = make_char({"cooldowns": {"survey": 1060.0}})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            self.assertEqual(remaining_cooldown(char, "survey"), 60.0)

    def test_non_numeric_expiry_treated_as_zero(self):
        # If the stored expiry is bogus (string, None), don't crash
        char = make_char({"cooldowns": {"survey": "garbage"}})
        self.assertEqual(remaining_cooldown(char, "survey"), 0.0)

    def test_none_expiry_treated_as_zero(self):
        char = make_char({"cooldowns": {"survey": None}})
        # None passes the float() coercion path -> ValueError -> 0.0
        self.assertEqual(remaining_cooldown(char, "survey"), 0.0)


# ══════════════════════════════════════════════════════════════════════════════
# check_cooldown
# ══════════════════════════════════════════════════════════════════════════════


class TestCheckCooldown(unittest.TestCase):
    def test_returns_true_when_no_cooldown_set(self):
        char = make_char({})
        self.assertTrue(check_cooldown(char, "survey"))

    def test_returns_true_when_expired(self):
        char = make_char({"cooldowns": {"survey": 100.0}})
        with patch("engine.cooldowns.time.time", return_value=200.0):
            self.assertTrue(check_cooldown(char, "survey"))

    def test_returns_false_when_live(self):
        char = make_char({"cooldowns": {"survey": 200.0}})
        with patch("engine.cooldowns.time.time", return_value=100.0):
            self.assertFalse(check_cooldown(char, "survey"))


# ══════════════════════════════════════════════════════════════════════════════
# set_cooldown
# ══════════════════════════════════════════════════════════════════════════════


class TestSetCooldown(unittest.TestCase):
    def test_creates_cooldowns_dict_when_absent(self):
        char = make_char({})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 300)
        attrs = json.loads(char["attributes"])
        self.assertIn("cooldowns", attrs)
        self.assertEqual(attrs["cooldowns"]["survey"], 1300.0)

    def test_appends_to_existing_cooldowns(self):
        char = make_char({"cooldowns": {"existing": 9999.0}})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 60)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["cooldowns"]["existing"], 9999.0)
        self.assertEqual(attrs["cooldowns"]["survey"], 1060.0)

    def test_overwrites_existing_key(self):
        char = make_char({"cooldowns": {"survey": 500.0}})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 100)
        attrs = json.loads(char["attributes"])
        # Old expiry replaced
        self.assertEqual(attrs["cooldowns"]["survey"], 1100.0)

    def test_returns_same_char_dict_for_chaining(self):
        char = make_char({})
        result = set_cooldown(char, "survey", 60)
        self.assertIs(result, char)

    def test_preserves_other_attributes(self):
        char = make_char({"hp": 100, "credits": 500})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 60)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["hp"], 100)
        self.assertEqual(attrs["credits"], 500)


# ══════════════════════════════════════════════════════════════════════════════
# clear_cooldown
# ══════════════════════════════════════════════════════════════════════════════


class TestClearCooldown(unittest.TestCase):
    def test_removes_target_key_only(self):
        char = make_char({"cooldowns": {"survey": 1000.0, "trade": 2000.0}})
        clear_cooldown(char, "survey")
        attrs = json.loads(char["attributes"])
        self.assertNotIn("survey", attrs.get("cooldowns", {}))
        self.assertIn("trade", attrs["cooldowns"])

    def test_removes_cooldowns_dict_when_emptied(self):
        # When the last cooldown is cleared, the cooldowns sub-dict is
        # removed entirely (housekeeping per the impl)
        char = make_char({"cooldowns": {"survey": 1000.0}})
        clear_cooldown(char, "survey")
        attrs = json.loads(char["attributes"])
        self.assertNotIn("cooldowns", attrs)

    def test_missing_key_no_crash(self):
        char = make_char({"cooldowns": {"trade": 1000.0}})
        # Doesn't raise
        clear_cooldown(char, "nonexistent")
        attrs = json.loads(char["attributes"])
        # 'trade' still there
        self.assertEqual(attrs["cooldowns"]["trade"], 1000.0)

    def test_no_cooldowns_dict_no_crash(self):
        char = make_char({})
        clear_cooldown(char, "survey")
        # Should not have invented an empty cooldowns dict
        attrs = json.loads(char["attributes"])
        self.assertNotIn("cooldowns", attrs)

    def test_returns_same_char_dict_for_chaining(self):
        char = make_char({"cooldowns": {"survey": 1000.0}})
        result = clear_cooldown(char, "survey")
        self.assertIs(result, char)


# ══════════════════════════════════════════════════════════════════════════════
# clear_all_cooldowns
# ══════════════════════════════════════════════════════════════════════════════


class TestClearAllCooldowns(unittest.TestCase):
    def test_removes_entire_cooldowns_sub_dict(self):
        char = make_char({
            "cooldowns": {"survey": 1000.0, "trade": 2000.0, "x": 3000.0},
            "hp": 100,
        })
        clear_all_cooldowns(char)
        attrs = json.loads(char["attributes"])
        self.assertNotIn("cooldowns", attrs)
        # Other attributes untouched
        self.assertEqual(attrs["hp"], 100)

    def test_no_cooldowns_dict_no_crash(self):
        char = make_char({"hp": 100})
        clear_all_cooldowns(char)
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["hp"], 100)


# ══════════════════════════════════════════════════════════════════════════════
# format_remaining
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatRemaining(unittest.TestCase):
    def test_zero_returns_ready(self):
        self.assertEqual(format_remaining(0), "ready")

    def test_negative_returns_ready(self):
        self.assertEqual(format_remaining(-5), "ready")

    def test_seconds_only(self):
        self.assertEqual(format_remaining(45), "45s")

    def test_seconds_floor(self):
        # 45.9s should floor to 45s, not round to 46
        self.assertEqual(format_remaining(45.9), "45s")

    def test_one_second(self):
        self.assertEqual(format_remaining(1), "1s")

    def test_minute_boundary(self):
        # exactly 60 -> 1m 00s
        self.assertEqual(format_remaining(60), "1m 00s")

    def test_minutes_with_seconds(self):
        # 125s = 2m 5s; format pads seconds to 2 digits
        self.assertEqual(format_remaining(125), "2m 05s")

    def test_minutes_only_when_no_remainder(self):
        # 120s = 2m 0s -> "2m 00s"
        self.assertEqual(format_remaining(120), "2m 00s")

    def test_hour_boundary(self):
        # exactly 3600 -> 1h 00m
        self.assertEqual(format_remaining(3600), "1h 00m")

    def test_hours_with_minutes(self):
        # 3661s = 1h 1m 1s; format only shows hours+minutes
        self.assertEqual(format_remaining(3661), "1h 01m")

    def test_long_duration(self):
        # 7-day faction switch cooldown = 604800s
        # = 168h 0m
        self.assertEqual(format_remaining(604800), "168h 00m")


# ══════════════════════════════════════════════════════════════════════════════
# Module constants
# ══════════════════════════════════════════════════════════════════════════════


class TestConstants(unittest.TestCase):
    """Pin the cooldown key strings and durations.

    These are imported across many modules — silently changing them
    would create cooldowns that look fresh under one constant name and
    expired under another. The constants are part of the cross-module
    contract.
    """

    def test_survey_key(self):
        self.assertEqual(CD_SURVEY, "survey")

    def test_faction_switch_key(self):
        self.assertEqual(CD_FACTION_SWITCH, "faction_switch")

    def test_trade_key(self):
        self.assertEqual(CD_TRADE, "trade")

    def test_survey_duration_is_5_minutes(self):
        self.assertEqual(SURVEY_COOLDOWN_S, 300)

    def test_faction_switch_duration_is_7_days(self):
        # 7 days * 86400 = 604800
        self.assertEqual(FACTION_SWITCH_COOLDOWN_S, 604800)

    def test_trade_duration_is_30_seconds(self):
        self.assertEqual(TRADE_COOLDOWN_S, 30)

    def test_durations_are_positive(self):
        for name, val in [
            ("SURVEY", SURVEY_COOLDOWN_S),
            ("FACTION_SWITCH", FACTION_SWITCH_COOLDOWN_S),
            ("TRADE", TRADE_COOLDOWN_S),
        ]:
            self.assertGreater(val, 0, f"{name}_COOLDOWN_S not positive")


# ══════════════════════════════════════════════════════════════════════════════
# Integration: round-trip set → check → wait → expire
# ══════════════════════════════════════════════════════════════════════════════


class TestRoundTrip(unittest.TestCase):
    def test_set_then_check_returns_false_immediately(self):
        char = make_char({})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 60)
            self.assertFalse(check_cooldown(char, "survey"))

    def test_set_then_check_returns_true_after_expiry(self):
        char = make_char({})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 60)
        # Time travel forward past the expiry
        with patch("engine.cooldowns.time.time", return_value=1100.0):
            self.assertTrue(check_cooldown(char, "survey"))

    def test_remaining_decreases_over_simulated_time(self):
        char = make_char({})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 100)
        with patch("engine.cooldowns.time.time", return_value=1030.0):
            rem = remaining_cooldown(char, "survey")
        self.assertEqual(rem, 70.0)

    def test_set_clear_check_cycle(self):
        char = make_char({})
        with patch("engine.cooldowns.time.time", return_value=1000.0):
            set_cooldown(char, "survey", 60)
            self.assertFalse(check_cooldown(char, "survey"))
            clear_cooldown(char, "survey")
            # After force-clear, ready immediately
            self.assertTrue(check_cooldown(char, "survey"))


if __name__ == "__main__":
    unittest.main()
