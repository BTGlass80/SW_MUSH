# -*- coding: utf-8 -*-
"""
tests/test_fork_space_anomaly_engage_2026_06_23.py — SPACE anomaly-engagement fork.

Resolves SPACE.anomaly_engagement_mostly_unwired (Brian: "we need to fix that" ->
build the real per-type engagement). 6 of 7 anomaly types had no engagement
command, yet every scan readout told the player to type `course anomaly <id>` --
which only routed adjacent ZONES, so it failed. Only derelict (salvage) was wired.

This fork routes `course anomaly <id>` to a per-type dispatcher: derelict and
mineral_vein redirect to their dedicated verbs (salvage / mine); distress, cache,
pirates, imperial (Republic dead-drop) and mynock each resolve through
perform_skill_check (dice funnel) -> adjust_credits (credit funnel) ->
remove_anomaly, with the governing skill + difficulty following each readout's
design. The scan readouts are now true for all 7 types.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from parser.space_commands import _ANOMALY_ENGAGE, CourseCommand
from engine.space_anomalies import Anomaly

REPO = Path(__file__).resolve().parent.parent
SRC = (REPO / "parser" / "space_commands.py").read_text(encoding="utf-8")


class TestEngagementSpec(unittest.TestCase):
    def test_all_five_unwired_types_specced(self):
        for t in ("distress", "cache", "pirates", "imperial", "mynock"):
            self.assertIn(t, _ANOMALY_ENGAGE)
        # derelict/mineral_vein redirect to salvage/mine, not the generic spec
        self.assertNotIn("derelict", _ANOMALY_ENGAGE)
        self.assertNotIn("mineral_vein", _ANOMALY_ENGAGE)

    def test_specs_well_formed(self):
        for t, spec in _ANOMALY_ENGAGE.items():
            self.assertIn("mechanic", spec, f"{t} spec missing mechanic")
            m = spec["mechanic"]
            if m == "combat":
                # pirates: spawns hostiles into live combat — no pre-roll skill,
                # no engage faucet (reward is the fire-kill bounty + wreck)
                self.assertNotIn("skill", spec)
                self.assertNotIn("tag", spec)
                continue
            self.assertIn("one_shot", spec, f"{t} spec missing one_shot")
            if m == "two_step":
                self.assertEqual(len(spec["steps"]), 2, f"{t} needs 2 steps")
                for skill, diff in spec["steps"]:
                    self.assertIsInstance(skill, str)
                    self.assertIsInstance(diff, int)
            else:
                self.assertIn("skill", spec, f"{t} spec missing skill")
                self.assertIn("diff", spec, f"{t} spec missing diff")
            # credit-bearing mechanics (faucet, two_step, detach_damage,
            # slice_or_patrol) all carry a valid credits range + anomaly_ tag
            self.assertEqual(len(spec["credits"]), 2)
            self.assertLess(spec["credits"][0], spec["credits"][1])
            self.assertTrue(spec["tag"].startswith("anomaly_"))


class TestWiring(unittest.TestCase):
    def test_course_routes_anomaly_and_method_exists(self):
        self.assertIn('if _raw.lower().split()[:1] == ["anomaly"]:', SRC)
        self.assertIn("async def _engage_anomaly(self, ctx, raw):", SRC)
        self.assertTrue(hasattr(CourseCommand, "_engage_anomaly"))

    def test_resolution_uses_the_funnels(self):
        body = SRC[SRC.index("async def _engage_anomaly"):
                   SRC.index("async def _validate_helm")]
        self.assertIn("perform_skill_check(char, skill, diff", body)
        self.assertIn('adjust_credits(char["id"], amount, spec["tag"])', body)
        self.assertIn("remove_anomaly(zone_id, target.id)", body)


class TestEngagementResolves(unittest.TestCase):
    def test_fully_scanned_anomaly_meets_the_gate(self):
        a = Anomaly(id=1, zone_id="z", anomaly_type="cache", resolution=3)
        self.assertGreaterEqual(a.resolution, a.scans_needed)

    def test_engagement_skills_actually_roll(self):
        # every engagement skill must (a) be a real skill SLUG, not a governing
        # ATTRIBUTE name -- the old bug passed technical/mechanical, which
        # _get_skill_pool can't find, so the check silently rolled untrained
        # attribute dice -- and (b) produce a real skill-check result so the
        # dispatcher never falls into the graceful except.
        from engine.character import SkillRegistry
        from engine.skill_checks import perform_skill_check
        import os
        sr = SkillRegistry()
        sr.load_file(os.path.join("data", "skills.yaml"))
        char = {"id": 1, "skills": json.dumps({}),
                "attributes": json.dumps({"dexterity": "2D", "knowledge": "2D",
                                          "mechanical": "2D", "perception": "2D",
                                          "strength": "2D", "technical": "2D"})}
        attrs = {"dexterity", "knowledge", "mechanical", "perception",
                 "strength", "technical"}
        pairs = []
        for t, spec in _ANOMALY_ENGAGE.items():
            m = spec["mechanic"]
            if m == "two_step":
                pairs += [(t, s, d) for (s, d) in spec["steps"]]
            elif m == "combat":
                continue  # spawns hostiles, no pre-roll skill
            else:
                pairs.append((t, spec["skill"], spec["diff"]))
        for t, skill, diff in pairs:
            self.assertNotIn(skill, attrs,
                             f"{t}: {skill!r} is an ATTRIBUTE name, not a skill slug")
            r = perform_skill_check(char, skill, diff, sr)
            self.assertIsNotNone(r, f"{t}: skill {skill!r} did not roll")
            self.assertTrue(hasattr(r, "success"), f"{t}: result has no .success")


if __name__ == "__main__":
    unittest.main()
