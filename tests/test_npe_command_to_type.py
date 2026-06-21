# -*- coding: utf-8 -*-
"""
tests/test_npe_command_to_type.py — NPE-A tutorial hand-off clarity
(2026-06-20).

Pins the structured `command_to_type` field added to tutorial-chain
steps (the single canonical command a new player types to make progress),
end to end:
  * the YAML loader carries command_to_type onto TutorialStep;
  * the producer (get_active_step_info / build_onboarding_state) surfaces
    it to the web onboarding panel;
  * EVERY authored command_to_type's leading verb is a real registered
    command (no phantom verbs);
  * skill_check_passed steps carry NO command_to_type (the panel already
    renders their dedicated ATTEMPT chip — avoids a double spotlight);
  * the consumer (m3_onboard.js) renders the spotlight chip.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.tutorial_chains import load_tutorial_chains
from engine.chain_events import get_active_step_info, build_onboarding_state


def _active_char(chain_id: str, step: int = 1) -> dict:
    attrs = {"tutorial_chain": {"completion_state": "active",
                                "chain_id": chain_id, "step": step}}
    return {"id": 1, "name": "Newbie", "attributes": json.dumps(attrs)}


class TestCommandToTypeCorpus(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.corpus = load_tutorial_chains("clone_wars")

    def test_loader_carries_command_to_type(self):
        rs = self.corpus.by_id().get("republic_soldier")
        self.assertIsNotNone(rs)
        self.assertEqual(rs.steps[0].command_to_type, "talk Major Tarrn")
        self.assertEqual(rs.steps[1].command_to_type, "attack")
        self.assertEqual(rs.steps[2].command_to_type, "+missions")

    def test_skill_steps_have_no_spotlight(self):
        """skill_check_passed steps must leave command_to_type empty so
        the panel does not render BOTH a spotlight and the ATTEMPT chip."""
        offenders = []
        for chain in self.corpus.by_id().values():
            for step in chain.steps:
                ctype = (step.completion or {}).get("type")
                if ctype == "skill_check_passed" and step.command_to_type:
                    offenders.append(
                        f"{chain.chain_id} step {step.step}: "
                        f"command_to_type={step.command_to_type!r}"
                    )
        self.assertEqual(
            offenders, [],
            "skill_check_passed steps must have an empty command_to_type "
            "(the ATTEMPT chip is their spotlight): " + "; ".join(offenders)
        )

    def test_no_phantom_verb_in_any_command_to_type(self):
        """Every authored command_to_type's leading verb must resolve in
        the live command registry (no phantom verbs reach a new player)."""
        from tests.test_t321_admin_command_access_invariant import (
            _build_full_registry,
        )
        reg = _build_full_registry()
        self.assertGreaterEqual(len(reg.all_commands), 300,
                                "registry built too small — import broke")
        bad = []
        for chain in self.corpus.by_id().values():
            for step in chain.steps:
                cmd = (step.command_to_type or "").strip()
                if not cmd:
                    continue
                verb = cmd.split()[0]
                if reg.get(verb) is None:
                    bad.append(f"{chain.chain_id} step {step.step}: "
                               f"'{cmd}' (verb '{verb}' not registered)")
        self.assertEqual(
            bad, [],
            "command_to_type values must lead with a REAL registered "
            "command — phantom verbs found: " + "; ".join(bad)
        )

    def test_command_to_type_count_is_reasonable(self):
        """Sanity: a meaningful number of early steps got a spotlight."""
        n = sum(1 for c in self.corpus.by_id().values()
                for s in c.steps if s.command_to_type)
        self.assertGreaterEqual(
            n, 12, f"expected the early-step spotlights to be authored, got {n}"
        )


class TestCommandToTypeProducer(unittest.TestCase):
    def test_get_active_step_info_surfaces_it(self):
        char = _active_char("republic_soldier", step=1)
        info = get_active_step_info(char)
        self.assertIsNotNone(info, "expected an active step for the crafted char")
        self.assertIn("command_to_type", info)
        self.assertEqual(info["command_to_type"], "talk Major Tarrn")

    def test_onboarding_state_surfaces_it(self):
        char = _active_char("republic_soldier", step=2)
        state = build_onboarding_state(char)
        self.assertIsNotNone(state)
        self.assertTrue(state.get("active"))
        self.assertEqual(state.get("command_to_type"), "attack")

    def test_step_without_spotlight_emits_empty(self):
        """A skill step (republic_intelligence step 3 = sneak) surfaces an
        empty command_to_type, not a phantom one."""
        char = _active_char("republic_intelligence", step=3)
        info = get_active_step_info(char)
        self.assertIsNotNone(info)
        self.assertEqual(info.get("command_to_type"), "")


class TestCommandToTypeConsumer(unittest.TestCase):
    def test_panel_renders_spotlight_chip(self):
        src = (PROJECT_ROOT / "static" / "spa" / "m3_onboard.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("command_to_type", src,
                      "m3_onboard.js must read data.command_to_type")
        self.assertIn("data-teach-cmd", src,
                      "the spotlight must stage the full runnable command")
        self.assertIn("TYPE", src,
                      "the spotlight chip should be labelled for the player")


if __name__ == "__main__":
    unittest.main()
