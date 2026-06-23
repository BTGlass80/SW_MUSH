# -*- coding: utf-8 -*-
"""
tests/test_fork_env_recovery_2026_06_23.py — ENV recovery fork.

Brian's decision on ENV.hazard_debuff_no_cure_path: "definitely need recovery"
(Option A: wire a real cure path). The desert-heat dehydration and toxic-exposure
debuffs were `duration_seconds: 0` (permanent) with `remove_buff()` having ZERO
callers, so once taken they were permanent with no in-game cure.

This fork:
  * Gives both env debuffs a `duration_seconds` (1200s) so they DECAY once the
    player leaves the hazard -- the hazard tick refreshes the buff (add_buff
    refreshes started_at) while exposed, so the debuff persists in-zone and
    recovers ~20 min after leaving.
  * Adds a `drink` command: an instant active cure for dehydration if the player
    carries a water_canteen (via engine.buffs.remove_buff).
  * (The hazard difficulty double-scaling -- the other half of this fork -- was
    fixed in the batch-2-tail drop.)
"""
from __future__ import annotations

import json
import time
import unittest
from pathlib import Path

from engine.buffs import (
    BUFF_TEMPLATES, add_buff, has_buff, remove_buff, expire_buffs,
    _get_buffs, _set_buffs,
)
from engine.hazards import _has_mitigation

REPO = Path(__file__).resolve().parent.parent
BC_SRC = (REPO / "parser" / "builtin_commands.py").read_text(encoding="utf-8")


class TestEnvDebuffsDecay(unittest.TestCase):
    def test_both_env_debuffs_now_have_a_decay_duration(self):
        self.assertGreater(BUFF_TEMPLATES["dehydration"]["duration_seconds"], 0)
        self.assertGreater(BUFF_TEMPLATES["toxic_exposure"]["duration_seconds"], 0)

    def test_stale_dehydration_decays_on_leaving(self):
        char = {"attributes": json.dumps({})}
        add_buff(char, "dehydration")
        self.assertTrue(has_buff(char, "dehydration"))
        # simulate leaving the heat: the hazard stops refreshing the buff, so it
        # ages past its duration.
        buffs = _get_buffs(char)
        dur = BUFF_TEMPLATES["dehydration"]["duration_seconds"]
        for b in buffs:
            b.started_at = time.time() - (dur + 60)
        _set_buffs(char, buffs)
        expire_buffs(char)
        self.assertFalse(has_buff(char, "dehydration"),
                         "dehydration must decay once the player leaves the heat")


class TestDrinkCure(unittest.TestCase):
    def test_remove_buff_clears_dehydration(self):
        char = {"attributes": json.dumps({})}
        add_buff(char, "dehydration")
        self.assertTrue(has_buff(char, "dehydration"))
        res = remove_buff(char, "dehydration")
        self.assertTrue(res["ok"])
        self.assertFalse(has_buff(char, "dehydration"))

    def test_water_canteen_detected_in_inventory(self):
        with_water = {"inventory": json.dumps({"items": [{"key": "water_canteen"}]}),
                      "equipment": "{}"}
        without = {"inventory": json.dumps({"items": []}), "equipment": "{}"}
        self.assertTrue(_has_mitigation(with_water, ["water_canteen"]))
        self.assertFalse(_has_mitigation(without, ["water_canteen"]))

    def test_drink_command_present_and_registered(self):
        self.assertIn("class DrinkCommand(BaseCommand):", BC_SRC)
        self.assertIn('key = "drink"', BC_SRC)
        self.assertIn("DrinkCommand(),", BC_SRC)


if __name__ == "__main__":
    unittest.main()
