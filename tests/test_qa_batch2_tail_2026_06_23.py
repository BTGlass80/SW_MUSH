# -*- coding: utf-8 -*-
"""
tests/test_qa_batch2_tail_2026_06_23.py — QA break-it regression (batch-2 tail:
hazards double-scale + admin/@-command sweeps, 2026-06-23).

(a) [hazards] Environmental hazard difficulty double-scaled with severity:
    check_hazard_for_character read the ALREADY-severity-scaled stored difficulty,
    then added (severity-1)*3 AGAIN -> a severity-3 hazard hit DC 22 instead of
    the intended 16. Fix: use the stored value as-is; scale only the raw-base
    fallback once.

(b) [admin, CORRUPTION] ADMIN > BUILDER privilege hierarchy not enforced: an
    account with is_admin=1, is_builder=0 (the state `@grant <char> = admin`
    produces) was denied EVERY builder tool (@teleport/@set/@destroy/...). Fix:
    the BUILDER gate passes for is_builder OR is_admin.

(c) [admin, CRASH] `@lore add priority=<non-number>` threw an unhandled
    ValueError -> generic "An error occurred" to the admin. Fix: a try/except
    with a clean "Priority must be a number" message.
"""
from __future__ import annotations

import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HAZ = (REPO / "engine" / "hazards.py").read_text(encoding="utf-8")
CMD = (REPO / "parser" / "commands.py").read_text(encoding="utf-8")
DIR = (REPO / "parser" / "director_commands.py").read_text(encoding="utf-8")


class TestHazardDoubleScale(unittest.TestCase):
    def test_stored_difficulty_used_as_is(self):
        i = HAZ.index("def check_hazard_for_character")
        body = HAZ[i:i + 1500]
        self.assertIn('if "difficulty" in hazard_cfg:', body)
        # the double-applying line must be gone from the check
        self.assertNotIn("difficulty += (severity - 1) * 3", body,
                         "the stored difficulty is already severity-scaled; "
                         "re-applying it double-scales the DC")


class TestAdminInheritsBuilder(unittest.TestCase):
    def test_builder_gate_passes_for_admin(self):
        i = CMD.index("if self.access_level == AccessLevel.BUILDER:")
        block = CMD[i:i + 700]
        self.assertIn('_live_account_flag(ctx, "is_builder")', block)
        self.assertIn('_live_account_flag(ctx, "is_admin")', block,
                      "the BUILDER gate must also pass for an admin "
                      "(ADMIN > BUILDER hierarchy)")


class TestLorePriorityGuard(unittest.TestCase):
    def test_priority_parse_is_guarded(self):
        i = DIR.index("result = await add_lore(")
        # look just before the add_lore call for the guarded parse
        block = DIR[max(0, i - 400):i + 50]
        self.assertIn("_priority = int(params.get", block)
        self.assertIn("except (ValueError, TypeError):", block)
        self.assertNotIn('priority=int(params.get("priority", "5")),', DIR,
                         "the unguarded int(priority) that crashed @lore is gone")


if __name__ == "__main__":
    unittest.main()
