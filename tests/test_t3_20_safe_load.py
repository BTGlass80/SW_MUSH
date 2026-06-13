# -*- coding: utf-8 -*-
"""tests/test_t3_20_safe_load.py — T3.20 safe character-load (2 launch-blockers).

Both fixes live in engine/character.py::from_db_dict and protect a LIVE save
that would otherwise fail to load right (HANDOFF_t3_20_state_preservation):

  BLOCKER 1 — a single corrupted attribute value (e.g. "4X+2") used to make
  the UNGUARDED DicePool.parse in the attributes loop raise, aborting the whole
  character load -> the player could not log in. Now the bad field is skipped
  with a warning (mirrors the skills-loop guard).

  BLOCKER 2 / FORCE.sensitivity_failsafe_to_jedi (Brian Ruling 5) — force_sensitive
  is DERIVED from control/sense/alter in the attributes JSON. If that blob is
  corrupt/pre-derivation, a path-committed Jedi silently reconstructed as
  force_sensitive=False. Now a committed village_chosen_path (typed column,
  survives blob corruption) fails SAFE to force_sensitive=True + a loud warning.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _row(**over):
    """Minimal characters-table row dict; override per test."""
    base = {"id": 1, "name": "Tester", "attributes": "{}", "skills": "{}"}
    base.update(over)
    return base


class TestBlocker1CorruptedAttrLoads(unittest.TestCase):
    def test_corrupted_attribute_does_not_abort_load(self):
        from engine.character import Character
        # One bad attribute value + one good one. Must NOT raise; good one loads.
        row = _row(attributes='{"dexterity": "4X+2", "strength": "3D"}')
        char = Character.from_db_dict(row)  # must not raise
        self.assertEqual(char.name, "Tester")
        self.assertEqual(str(char.get_attribute("strength")), "3D")

    def test_corrupted_force_attribute_does_not_abort(self):
        from engine.character import Character
        row = _row(attributes='{"control": "GARBAGE", "dexterity": "2D"}')
        char = Character.from_db_dict(row)  # must not raise
        self.assertEqual(str(char.get_attribute("dexterity")), "2D")


class TestBlocker2ForceFailsafe(unittest.TestCase):
    def test_malformed_attrs_committed_jedi_failsafe(self):
        from engine.character import Character
        # Unreadable attributes JSON + a committed path -> fail safe to Jedi.
        row = _row(attributes="{ this is not valid json",
                   village_chosen_path="a")
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive,
                        "committed Jedi with corrupt attrs must load force_sensitive")

    def test_valid_attrs_missing_force_committed_failsafe(self):
        from engine.character import Character
        # Valid JSON but NO control/sense/alter (pre-derivation save) + committed.
        row = _row(attributes='{"dexterity": "3D"}', village_chosen_path="b")
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_path_c_also_failsafe(self):
        from engine.character import Character
        row = _row(attributes="{bad", village_chosen_path="c")
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_uncommitted_does_not_failsafe(self):
        from engine.character import Character
        # No committed path -> no spurious Force grant.
        row = _row(attributes='{"dexterity": "3D"}', village_chosen_path="")
        char = Character.from_db_dict(row)
        self.assertFalse(char.force_sensitive)

    def test_missing_column_does_not_failsafe(self):
        from engine.character import Character
        # An NPC row without the column at all -> no Force grant, no crash.
        row = _row(attributes='{"dexterity": "3D"}')
        char = Character.from_db_dict(row)
        self.assertFalse(char.force_sensitive)


class TestNormalForceUnchanged(unittest.TestCase):
    def test_real_force_attrs_still_derive_sensitive(self):
        from engine.character import Character
        row = _row(attributes='{"control": "2D", "sense": "1D+2", "dexterity": "3D"}')
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)
        self.assertEqual(str(char.get_attribute("control")), "2D")

    def test_corrupt_force_value_but_committed_still_sensitive(self):
        from engine.character import Character
        # Force attr present but its VALUE is garbage (blocker-1 skips it) AND
        # the char is committed -> blocker-2 fail-safe still flags sensitive.
        row = _row(attributes='{"control": "GARBAGE"}', village_chosen_path="a")
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)


if __name__ == "__main__":
    unittest.main()
