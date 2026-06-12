# -*- coding: utf-8 -*-
"""
tests/test_e1_org_scale_violence.py — Lane E1 (GG11) coverage.

Three layers:
  1. Pure helpers in engine.organizations (scale/violence accessors,
     descriptor, faction-info display line) — the consumer primitives.
  2. organizations.yaml carries the new additive properties.
  3. lore.yaml carries the 9 era-translated GG11 §2 entries, well-formed
     and era-clean (B3).
"""
from __future__ import annotations

import os
import sys
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.organizations import (  # noqa: E402
    ORG_SCALES,
    get_org_scale,
    get_org_violence_index,
    violence_descriptor,
    format_org_posture_line,
)

CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
NEW_LORE_TITLES = [
    "Criminal Organization Tiers", "Criminal Occupations", "The Kajidic",
    "Indentured Servitude", "Haven Worlds", "The Black Market Code",
    "Spice", "Slaver Guilds", "Sector Rangers",
]


class TestScaleAccessor(unittest.TestCase):
    def test_org_scales_tuple(self):
        self.assertEqual(
            ORG_SCALES, ("gang", "guild", "cartel", "syndicate", "empire"))

    def test_dict_props(self):
        self.assertEqual(get_org_scale({"scale": "cartel"}), "cartel")

    def test_org_row_with_json_string_props(self):
        # mirrors a DB row where properties is a JSON string
        self.assertEqual(
            get_org_scale({"properties": '{"scale": "empire"}'}), "empire")

    def test_case_insensitive(self):
        self.assertEqual(get_org_scale({"scale": "  Syndicate "}), "syndicate")

    def test_invalid_scale_is_none(self):
        self.assertIsNone(get_org_scale({"scale": "megacorp"}))

    def test_absent_is_none(self):
        self.assertIsNone(get_org_scale({"violence_index": 50}))
        self.assertIsNone(get_org_scale(None))


class TestViolenceAccessor(unittest.TestCase):
    def test_present(self):
        self.assertEqual(get_org_violence_index({"violence_index": 88}), 88)

    def test_clamped(self):
        self.assertEqual(get_org_violence_index({"violence_index": 150}), 100)
        self.assertEqual(get_org_violence_index({"violence_index": -5}), 0)

    def test_float_coerced(self):
        self.assertEqual(get_org_violence_index({"violence_index": 60.9}), 60)

    def test_absent_returns_default(self):
        self.assertIsNone(get_org_violence_index({"scale": "gang"}))
        self.assertEqual(get_org_violence_index({}, default=50), 50)

    def test_bool_rejected(self):
        # bool is an int subclass; must not be read as a violence value
        self.assertIsNone(get_org_violence_index({"violence_index": True}))

    def test_json_string_props(self):
        self.assertEqual(
            get_org_violence_index({"properties": '{"violence_index": 25}'}), 25)


class TestViolenceDescriptor(unittest.TestCase):
    def test_bands(self):
        self.assertEqual(violence_descriptor(0), "surgical")
        self.assertEqual(violence_descriptor(29), "surgical")
        self.assertEqual(violence_descriptor(30), "pointed")
        self.assertEqual(violence_descriptor(54), "pointed")
        self.assertEqual(violence_descriptor(55), "heated")
        self.assertEqual(violence_descriptor(69), "heated")
        self.assertEqual(violence_descriptor(70), "bloody")
        self.assertEqual(violence_descriptor(84), "bloody")
        self.assertEqual(violence_descriptor(85), "range war")
        self.assertEqual(violence_descriptor(100), "range war")

    def test_clamps_out_of_range(self):
        self.assertEqual(violence_descriptor(999), "range war")
        self.assertEqual(violence_descriptor(-10), "surgical")


class TestPostureLine(unittest.TestCase):
    def test_both_fields(self):
        line = format_org_posture_line(
            {"scale": "cartel", "violence_index": 88})
        self.assertIsNotNone(line)
        self.assertIn("Cartel", line)
        self.assertIn("range war", line)  # 88 is the 85+ band
        self.assertIn("88/100", line)

    def test_violence_only(self):
        line = format_org_posture_line({"violence_index": 25})
        self.assertIsNotNone(line)
        self.assertIn("surgical", line)
        self.assertNotIn("Scale", line)

    def test_scale_only(self):
        line = format_org_posture_line({"scale": "gang"})
        self.assertIsNotNone(line)
        self.assertIn("Gang", line)
        self.assertNotIn("Posture", line)

    def test_neither_returns_none(self):
        # craft guilds / unset player orgs surface nothing
        self.assertIsNone(format_org_posture_line({"dues_weekly": 100}))
        self.assertIsNone(format_org_posture_line({}))


class TestOrganizationsYaml(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CW, "organizations.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cls.fac = {f["code"]: f for f in data.get("factions", [])}

    def test_hutt_cartel_is_empire_scale(self):
        p = self.fac["hutt_cartel"]["properties"]
        self.assertEqual(p.get("scale"), "empire")
        self.assertEqual(p.get("violence_index"), 88)

    def test_bhg_is_guild_scale(self):
        self.assertEqual(
            self.fac["bounty_hunters_guild"]["properties"].get("scale"), "guild")

    def test_state_factions_have_no_criminal_scale(self):
        for code in ("republic", "cis", "jedi_order"):
            self.assertIsNone(
                self.fac[code]["properties"].get("scale"),
                f"{code} should carry no criminal scale")

    def test_every_violence_index_in_range_and_valid_scale(self):
        for code, fac in self.fac.items():
            p = fac.get("properties", {})
            if "violence_index" in p:
                self.assertIsInstance(p["violence_index"], int)
                self.assertGreaterEqual(p["violence_index"], 0)
                self.assertLessEqual(p["violence_index"], 100)
            if "scale" in p:
                self.assertIn(p["scale"], ORG_SCALES)

    def test_accessors_read_yaml_rows(self):
        # the helpers must work on the actual seeded shape
        hc = self.fac["hutt_cartel"]["properties"]
        self.assertEqual(get_org_scale(hc), "empire")
        self.assertEqual(violence_descriptor(get_org_violence_index(hc)), "range war")


class TestLoreEntries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(CW, "lore.yaml"), encoding="utf-8") as f:
            data = yaml.safe_load(f)
        cls.entries = data.get("entries", [])
        cls.by_title = {e["title"]: e for e in cls.entries}

    def test_all_nine_present(self):
        for t in NEW_LORE_TITLES:
            self.assertIn(t, self.by_title, f"missing lore entry: {t}")

    def test_each_well_formed(self):
        for t in NEW_LORE_TITLES:
            e = self.by_title[t]
            self.assertTrue(e.get("keywords"), f"{t} has no keywords")
            self.assertTrue(e.get("category"), f"{t} has no category")
            self.assertGreater(len(e.get("content", "")), 120,
                               f"{t} content too short")

    def test_b3_era_clean(self):
        # No GCW-era markers in the new underworld lore. NOTE: 'empire' is
        # allowed (criminal-empire scale tier); we ban only unambiguous
        # GCW tokens. 'rebel' is NOT banned ('rebellions' is legitimate).
        forbidden = [
            "imperial", "stormtrooper", "tie fighter", "tie pilot",
            "x-wing", "xwing", "death star", "rebel alliance",
            "the rebellion", "moff ", "galactic empire",
        ]
        for t in NEW_LORE_TITLES:
            e = self.by_title[t]
            blob = (e.get("content", "") + " " + e.get("keywords", "")).lower()
            for tok in forbidden:
                self.assertNotIn(tok, blob, f"B3 violation in {t!r}: {tok!r}")

    def test_kajidic_extends_not_restates_hutt_cartel(self):
        # The Kajidic must coexist with the existing Hutt Cartel entry
        self.assertIn("The Hutt Cartel", self.by_title)
        self.assertIn("The Kajidic", self.by_title)
        self.assertNotEqual(
            self.by_title["The Hutt Cartel"]["content"],
            self.by_title["The Kajidic"]["content"])


if __name__ == "__main__":
    unittest.main()
