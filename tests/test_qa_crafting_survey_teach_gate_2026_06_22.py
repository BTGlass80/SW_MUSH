# -*- coding: utf-8 -*-
"""
tests/test_qa_crafting_survey_teach_gate_2026_06_22.py — QA break-it regression.

Two MEDIUM defects found by the crafting/gathering break-it sweep (2026-06-22):

#1  survey always used the CITY quality band regardless of zone.
    The survey command (parser/crafting_commands.py) classified the room by name
    to pick resource TYPES (get_survey_resources via _OUTDOOR_ZONE_KEYWORDS:
    outdoor => metal/organic) but called survey_quality_from_margin(margin)
    WITHOUT is_outdoor, so the quality band was always the city 30-60 instead of
    the designed outdoor 60-90. Outdoor harvesting silently yielded
    systematically lower-quality (and thus fewer) resources than intended.
    Fix: a shared engine.crafting.is_outdoor_zone() now drives BOTH the type
    selection and the quality band, and the command passes is_outdoor.

#2  teach bypassed the T5 questline/rep gate that learn enforces.
    LearnCommand checks _schematic_gate_met before add_known_schematic;
    TeachCommand did not — so a player who had earned a gated T5 recipe could
    teach it to anyone, who could then craft it (can_craft checks resources
    only). Fix: TeachCommand now checks _schematic_gate_met(target_char, ...)
    and refuses to teach a gated recipe to a target who hasn't earned it (an
    ungated schematic always passes, so ordinary teaching is unaffected).

Run: python -m pytest tests/test_qa_crafting_survey_teach_gate_2026_06_22.py
"""
from __future__ import annotations

import asyncio
import re
import unittest
from pathlib import Path

from engine.crafting import is_outdoor_zone, survey_quality_from_margin
from parser import crafting_commands


REPO = Path(__file__).resolve().parent.parent
CMD_SRC = (REPO / "parser" / "crafting_commands.py").read_text(encoding="utf-8")


def _run(coro):
    return asyncio.run(coro)


# ─── #1 survey quality band ──────────────────────────────────────────────────

class TestOutdoorSurveyQuality(unittest.TestCase):
    def test_is_outdoor_zone_classifies_outdoor_names(self):
        for name in ("Jundland Wastes - Canyon Mouth", "Dune Sea Outskirts",
                     "Desert Mesa Overlook", "Open Plains"):
            self.assertTrue(is_outdoor_zone(name), name)

    def test_is_outdoor_zone_classifies_city_names(self):
        for name in ("Mos Eisley Market", "Docking Bay 94", "Civic District",
                     "city", ""):
            self.assertFalse(is_outdoor_zone(name), name)

    def test_outdoor_band_is_60_to_90(self):
        # margin 0 -> base; high margin -> ceiling
        self.assertEqual(survey_quality_from_margin(0, is_outdoor=True), 60.0)
        self.assertEqual(survey_quality_from_margin(100, is_outdoor=True), 90.0)

    def test_city_band_is_30_to_60(self):
        self.assertEqual(survey_quality_from_margin(0, is_outdoor=False), 30.0)
        self.assertEqual(survey_quality_from_margin(100, is_outdoor=False), 60.0)

    def test_outdoor_strictly_better_than_city_at_same_margin(self):
        for margin in (0, 3, 10):
            self.assertGreater(
                survey_quality_from_margin(margin, is_outdoor=True),
                survey_quality_from_margin(margin, is_outdoor=False),
                margin)

    def test_survey_command_wires_is_outdoor(self):
        # The fix: the command must pass is_outdoor=is_outdoor_zone(room_name).
        self.assertRegex(
            CMD_SRC,
            r"survey_quality_from_margin\(\s*result\.margin,\s*"
            r"is_outdoor=is_outdoor_zone\(room_name\)\s*\)",
            "survey command no longer passes is_outdoor=is_outdoor_zone(room_name)")


# ─── #2 teach gate ───────────────────────────────────────────────────────────

class TestTeachSchematicGate(unittest.TestCase):
    def test_ungated_schematic_is_always_met(self):
        ok = _run(crafting_commands._schematic_gate_met(
            {"attributes": "{}"}, {"key": "blaster_pistol_basic"}, db=None))
        self.assertTrue(ok)

    def test_questline_gated_schematic_blocked_without_completion(self):
        # A char who has NOT completed the gating questline fails the gate.
        gated = {"key": "t5_master_lightsaber",
                 "gated_by_questline": "hermit_trial"}
        ok = _run(crafting_commands._schematic_gate_met(
            {"attributes": "{}"}, gated, db=None))
        self.assertFalse(ok)

    def test_teach_checks_gate_before_adding_schematic(self):
        # The fix: TeachCommand must call _schematic_gate_met(target_char, ...)
        # BEFORE add_known_schematic(target_char, ...) — the missing check that
        # let teach bypass the gate learn enforces.
        m = crafting_commands.TeachCommand.execute
        src = CMD_SRC
        gate_i = src.find("_schematic_gate_met(target_char")
        add_i = src.find('add_known_schematic(target_char, schematic["key"])')
        self.assertNotEqual(gate_i, -1, "teach gate check missing")
        self.assertNotEqual(add_i, -1, "teach add_known_schematic call missing")
        self.assertLess(gate_i, add_i,
                        "gate check must precede add_known_schematic in teach")


if __name__ == "__main__":
    unittest.main()
