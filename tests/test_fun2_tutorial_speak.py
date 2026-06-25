"""
test_fun2_tutorial_speak.py — FUN2 tutorial soft-lock fix (engine side).

The starter tutorial step 1 gates `talk Major Tarrn` behind
requires_first:[look,+sheet] and silently refused the advance, stranding the
player. The fix surfaces the gate two ways (the gating logic itself is
unchanged — see test_f8c2b5_requires_first):
  - build_onboarding_state now emits a `prereqs` checklist + `prereqs_met`,
  - npe_prereq_hint() returns a one-line hint when the player talks to the
    active step's NPC with unmet prereqs.
"""
from __future__ import annotations

import json
import unittest

from engine.chain_events import (
    _reset_corpus_cache, build_onboarding_state, npe_prereq_hint,
)


def _char(satisfied=None, chain="republic_soldier", step=1):
    state = {
        "chain_id": chain, "step": step, "started_at": 1000000,
        "completed_steps": [], "completion_state": "active",
    }
    if satisfied is not None:
        state["step_progress_satisfied"] = list(satisfied)
    return {
        "id": 42, "name": "Test PC",
        "attributes": json.dumps({"tutorial_chain": state}),
    }


class _Base(unittest.TestCase):
    def setUp(self):
        _reset_corpus_cache()

    def tearDown(self):
        _reset_corpus_cache()


class TestChecklistPayload(_Base):
    def test_prereqs_present_none_done(self):
        st = build_onboarding_state(_char(satisfied=[]))
        self.assertTrue(st and st.get("active"))
        pr = st.get("prereqs")
        self.assertTrue(pr, "step 1 must expose a prereqs checklist")
        cmds = [p["command"] for p in pr]
        self.assertIn("look", cmds)
        self.assertIn("+sheet", cmds)
        self.assertTrue(all(p["done"] is False for p in pr))
        self.assertFalse(st.get("prereqs_met"))

    def test_prereqs_partial(self):
        st = build_onboarding_state(_char(satisfied=[0]))  # index 0 (look) done
        pr = st["prereqs"]
        self.assertTrue(pr[0]["done"])
        self.assertFalse(pr[1]["done"])
        self.assertFalse(st["prereqs_met"])

    def test_prereqs_all_done(self):
        st = build_onboarding_state(_char(satisfied=[0, 1]))
        self.assertTrue(st["prereqs_met"])
        self.assertTrue(all(p["done"] for p in st["prereqs"]))


class TestPrereqHint(_Base):
    def test_hint_fires_for_active_npc_unmet(self):
        h = npe_prereq_hint(_char(satisfied=[]), "Major Tarrn")
        self.assertTrue(h)
        self.assertTrue("+sheet" in h or "look" in h)

    def test_hint_lists_only_missing(self):
        h = npe_prereq_hint(_char(satisfied=[0]), "Major Tarrn")  # look done
        self.assertTrue(h)
        self.assertIn("+sheet", h)

    def test_no_hint_when_all_met(self):
        self.assertIsNone(npe_prereq_hint(_char(satisfied=[0, 1]), "Major Tarrn"))

    def test_no_hint_wrong_npc(self):
        self.assertIsNone(npe_prereq_hint(_char(satisfied=[]), "Some Other Guy"))

    def test_partial_npc_name_matches(self):
        # the talk resolver may pass a partial — substring match both ways
        self.assertTrue(npe_prereq_hint(_char(satisfied=[]), "Tarrn"))


if __name__ == "__main__":
    unittest.main()
