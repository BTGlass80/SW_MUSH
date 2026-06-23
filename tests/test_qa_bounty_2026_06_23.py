# -*- coding: utf-8 -*-
"""
tests/test_qa_bounty_2026_06_23.py — QA break-it regression (bounty sweep).

#1 [CORRUPTION] NPC bounty reward lost if the hunter was OFFLINE at the target's
   bleed-out death. The kill hook trapped the only adjust_credits inside an
   `if _sess and _sess.character:` guard, but notify_target_killed had already
   marked the contract COLLECTED (irreversible) -> offline hunter paid nothing.
   Fix: award credits unconditionally; gate only the in-game message on a session.

#2 [SWALLOW] reward_alive_bonus advertised on the board but never paid — every
   collect/total_reward call hardcoded alive=False. Fix: the manual +bounty/collect
   now detects a CAPTURED-alive target (wound_level == 5, mortally wounded but not
   dead) and passes alive=True, so the bonus is actually awarded.

#3 [SWALLOW] +pcbounty cancel with a corrupt/empty contributors_json silently
   refunded $0 (refunds=[] -> no credit, no error -> escrow swallowed). Fix: a
   fallback refunds the whole pool to the poster who is canceling.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from parser.pc_bounty_commands import _proportional_refunds

REPO = Path(__file__).resolve().parent.parent
CC = (REPO / "parser" / "combat_commands.py").read_text(encoding="utf-8")
BCMD = (REPO / "parser" / "bounty_commands.py").read_text(encoding="utf-8")
PCB = (REPO / "parser" / "pc_bounty_commands.py").read_text(encoding="utf-8")


class TestOfflineHunterCredit(unittest.TestCase):
    def test_adjust_credits_is_outside_the_session_guard(self):
        i = CC.index("await _board.notify_target_killed(")
        body = CC[i:i + 2200]
        award = body.find("_new_bal = await ctx.db.adjust_credits(")
        guard = body.find("if _sess and _sess.character:")
        self.assertNotEqual(award, -1, "unconditional bounty award missing")
        self.assertNotEqual(guard, -1)
        self.assertLess(award, guard,
                        "the bounty adjust_credits must run BEFORE/outside the "
                        "`if _sess` guard so an offline hunter is still paid")


class TestAliveBonusWired(unittest.TestCase):
    def test_collect_passes_captured_alive(self):
        self.assertIn("captured_alive = (wound == 5)", BCMD)
        self.assertIn("board.collect(contract.id, captured_alive, ctx.db)", BCMD)
        self.assertIn("board.total_reward(collected, alive=captured_alive)", BCMD)

    def test_old_hardcoded_alive_false_is_gone(self):
        self.assertNotIn("board.collect(contract.id, False, ctx.db)", BCMD)


class TestCancelRefundFallback(unittest.TestCase):
    def test_empty_contributors_falls_back_to_poster(self):
        self.assertIn("if not contributors:", PCB)
        self.assertIn('"poster_id": ctx.session.character["id"]', PCB)

    def test_proportional_refunds_single_poster_gets_whole_pool(self):
        out = _proportional_refunds([{"poster_id": 5, "amount": 1000}], 750)
        self.assertEqual(out, [{"poster_id": 5, "refund": 750}])


if __name__ == "__main__":
    unittest.main()
