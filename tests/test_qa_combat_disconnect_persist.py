# -*- coding: utf-8 -*-
"""
tests/test_qa_combat_disconnect_persist.py — QA break-it HIGH
(2026-06-20): FP/CP/wound not persisted on a mid-round disconnect.

The 2026-06-20 break-it campaign found that the player's authoritative
post-round state save in `_apply_combat_wear` was gated on the session
existing (`if sess and sess.character:`). A player who spent a Force Point
or Character Points on a combat bonus and then disconnected before the
round resolved had those points REFUNDED on reconnect (an FP/CP-dup via
disconnect), and the wound was lost too.

Fix: the `db.save_character(c.id, wound_level, character_points,
force_points)` DB write now runs ALWAYS (keyed on c.id), independent of the
session; only the in-memory session mirror + the PC-death hook still need a
live session.

This path is fixture-heavy to drive end to end (full combat resolution), so
— mirroring tests/test_qa_rerun_findings.py for the same combat-persist
class — these are structural source guards.
"""
from __future__ import annotations

import sys
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestCombatDisconnectPersist(unittest.TestCase):
    def setUp(self):
        self.src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8"
        )

    def test_post_round_persist_is_unconditional(self):
        self.assertIn("Persist the AUTHORITATIVE post-round state", self.src,
                      "the always-persist intent comment must be present")

    def test_db_save_runs_before_the_session_gate(self):
        """The FP/CP/wound DB write must appear OUTSIDE (before) the
        `if sess and sess.character:` session-mirror gate — so a disconnected
        player's spent points are still persisted."""
        anchor = self.src.find("Persist the AUTHORITATIVE post-round state")
        self.assertNotEqual(anchor, -1)
        region = self.src[anchor:anchor + 1400]
        save_idx = region.find("force_points=c.char.force_points")
        gate_idx = region.find("if sess and sess.character:")
        self.assertNotEqual(save_idx, -1, "FP persist save not found")
        self.assertNotEqual(gate_idx, -1, "session gate not found")
        self.assertLess(
            save_idx, gate_idx,
            "the player FP/CP/wound DB save_character must run BEFORE / OUTSIDE "
            "the `if sess and sess.character:` gate — otherwise a disconnect "
            "refunds combat-spent FP/CP (the QA disconnect-dup bug)."
        )

    def test_all_three_fields_persisted(self):
        anchor = self.src.find("Persist the AUTHORITATIVE post-round state")
        region = self.src[anchor:anchor + 1400]
        for field in ("wound_level=c.char.wound_level.value",
                      "character_points=c.char.character_points",
                      "force_points=c.char.force_points"):
            self.assertIn(field, region,
                          f"post-round persist must include {field}")


if __name__ == "__main__":
    unittest.main()
