# -*- coding: utf-8 -*-
"""tests/test_director_economy_prompt.py — Director economy prompt-tuning.

Closes the director_scope_and_adaptive_spend_v1.md follow-ups: the paid LLM
turn now KNOWS about the digest['economy'] block (economy-eyes, §3/§4) and the
optional recommend_fidelity advisory (adaptive-spend slice 2, decision F). Both
were already produced/consumed in engine/director.py, but the LLM was never
told they exist — so the system prompt in
data/worlds/clone_wars/director_config.yaml is where this lands.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestEconomyPrompt(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cw = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
              / "director_config.yaml")
        if not cw.exists():
            raise unittest.SkipTest("clone_wars director_config.yaml not present")
        from engine.director_config_loader import get_director_runtime_config
        cls.prompt = get_director_runtime_config("clone_wars").system_prompt
        cls.lower = cls.prompt.lower()

    def test_prompt_describes_the_economy_block(self):
        self.assertIn("economy", self.lower)
        # name the block's real keys so the LLM can actually read it
        self.assertTrue(
            any(k in self.lower for k in ("faucet", "net_flow", "top_faucets")),
            "economy section must reference the digest['economy'] keys",
        )

    def test_prompt_encodes_decision_a_seeds_not_levers(self):
        self.assertIn("never", self.lower)
        self.assertTrue(
            ("price" in self.lower) or ("yield" in self.lower),
            "must forbid manipulating prices/yields directly (decision A)",
        )
        self.assertIn("opportunit", self.lower)  # seeds opportunities

    def test_prompt_offers_the_recommend_fidelity_advisory(self):
        # The slice-2 advisory channel only works if the LLM knows it exists.
        self.assertIn("recommend_fidelity", self.lower)
        # the distinctive tiers it may pick ("eco" is skipped — it collides
        # with the substring of "economy")
        for tier in ("standard", "high", "max"):
            self.assertIn(tier, self.lower)

    def test_added_sections_are_era_clean(self):
        # Scope the check to THIS drop's additions (the ECONOMY + SPEND ADVISORY
        # text). The pre-existing prompt body carries a sanctioned CW metaphor
        # ("the robes of rebellion" for the Separatists) that the runtime
        # era-guard would flag — re-litigating the established prompt voice is
        # out of scope here; we only guarantee our own additions are clean.
        from engine.era_validator import era_violations
        idx = self.prompt.find("ECONOMY:")
        self.assertGreater(idx, -1, "ECONOMY section missing from the prompt")
        bad = era_violations(self.prompt[idx:])
        self.assertEqual(bad, [], f"off-era tokens in the added economy/advisory text: {bad}")


if __name__ == "__main__":
    unittest.main()
