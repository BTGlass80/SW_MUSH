# -*- coding: utf-8 -*-
"""
Tests for Guide_05_Space_Systems.md and Guide_24_Encounters_Hazards.md rework (June 2026).

Guide_05: Verifies Wildspace ship mods subsection added to §11.
Guide_24: Verifies era-cleanness fixes (CIS→Republic Dead Drop; imperial refs removed).
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE05_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_05_Space_Systems.md")
GUIDE24_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_24_Encounters_Hazards.md")

_ERA_VIOLATIONS = [
    r"\bImperial(?! Sourcebook)\b",
    r"\bGalactic Empire\b",
    r"\bRebel Alliance\b",
    r"\bGalactic Civil War\b",
    r"\bGCW\b",
]
_ERA_RE = [re.compile(p) for p in _ERA_VIOLATIONS]


def _load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _era_violations(text):
    """Return list of (line_no, line, pattern) for any era-violation."""
    out = []
    for i, line in enumerate(text.split("\n"), start=1):
        for pat in _ERA_RE:
            m = pat.search(line)
            if m:
                out.append((i, line.strip(), pat.pattern))
    return out


class TestGuide05WildspaceMods(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE05_PATH)

    def test_file_exists(self):
        self.assertTrue(os.path.exists(GUIDE05_PATH))

    def test_wildspace_mods_section_present(self):
        self.assertIn("Wildspace Ship Mods", self.body)

    def test_mining_laser_mk1_present(self):
        self.assertIn("Mining Laser Mk1", self.body)

    def test_mining_laser_mk2_present(self):
        self.assertIn("Mining Laser Mk2", self.body)

    def test_salvage_arm_mk1_present(self):
        self.assertIn("Reinforced Salvage Arm Mk1", self.body)

    def test_salvage_arm_mk2_present(self):
        self.assertIn("Reinforced Salvage Arm Mk2", self.body)

    def test_onboard_refinery_present(self):
        self.assertIn("Onboard Refinery", self.body)

    def test_refine_command_mentioned(self):
        self.assertIn("`refine`", self.body)

    def test_hutt_rep_gate_mentioned(self):
        self.assertIn("Hutt Cartel 25+", self.body)

    def test_republic_rep_gate_mentioned(self):
        self.assertIn("Republic 25+", self.body)

    def test_deep_mining_mk2_explained(self):
        self.assertIn("deep mining", self.body)

    def test_intact_extraction_mk2_explained(self):
        self.assertIn("intact extraction", self.body)

    def test_venn_kator_trainer_named(self):
        self.assertIn("Venn Kator", self.body)

    def test_era_clean(self):
        viols = _era_violations(self.body)
        if viols:
            detail = "\n".join(f"  line {n}: {t!r}" for n, t, _ in viols)
            self.fail(f"Guide_05 era violations:\n{detail}")


class TestGuide24EraFixes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE24_PATH)

    def test_file_exists(self):
        self.assertTrue(os.path.exists(GUIDE24_PATH))

    def test_no_cis_anomaly_row(self):
        """CIS is not an anomaly type — was a wrong entry."""
        self.assertNotIn("| **CIS**", self.body)

    def test_republic_dead_drop_anomaly_row(self):
        self.assertIn("Republic Dead Drop", self.body)

    def test_numbers_table_no_imperial(self):
        """Numbers-at-a-glance anomaly list must not name 'imperial'."""
        for line in self.body.split("\n"):
            if "Anomaly types" in line and "|" in line:
                self.assertNotIn("imperial", line.lower(),
                                 f"'imperial' found in anomaly types table line: {line!r}")

    def test_numbers_table_has_republic_dead_drop(self):
        for line in self.body.split("\n"):
            if "Anomaly types" in line and "|" in line:
                self.assertIn("republic dead drop", line.lower(),
                              f"'republic dead drop' missing from anomaly types table: {line!r}")

    def test_no_imperial_outpost_reference(self):
        self.assertNotIn("imperial outpost", self.body.lower())

    def test_era_clean(self):
        viols = _era_violations(self.body)
        if viols:
            detail = "\n".join(f"  line {n}: {t!r}" for n, t, _ in viols)
            self.fail(f"Guide_24 era violations:\n{detail}")
