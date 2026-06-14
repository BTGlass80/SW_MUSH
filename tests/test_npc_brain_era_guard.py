# -*- coding: utf-8 -*-
"""tests/test_npc_brain_era_guard.py — era-guard on the primary NPC dialogue path.

ai/npc_brain.py::NPCBrain.dialogue() returns the local model's output straight
to the player (the `talk <npc>` path — the highest-traffic LLM->player surface).
A Mistral prompted for "Star Wars" reliably emits GCW-era content, so the
generated line is now (a) framed with ERA_PROMPT_HINT and (b) dropped to a
canned in-era fallback if it still leaks off-era, and an off-era line is never
persisted to NPC memory.
"""
from __future__ import annotations

import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from ai.npc_brain import NPCBrain, NPCData, NPCConfig

_FALLBACK = "The cantina hums with low chatter."


class _FakeAIConfig:
    tier1_model = "mistral:latest"
    tier2_model = "mistral:latest"
    tier3_model = ""


class _FakeAI:
    """Minimal AIManager stand-in: returns a canned generate() response."""
    def __init__(self, response):
        self._response = response
        self.config = _FakeAIConfig()

    async def generate(self, **kwargs):
        return self._response


def _brain(response):
    npc = NPCData(
        id=1, name="Wuher", species="human",
        ai_config=NPCConfig(
            enabled=True, personality="surly bartender",
            fallback_lines=[_FALLBACK],
        ),
    )
    return NPCBrain(npc, _FakeAI(response))


class TestNpcBrainEraGuard(unittest.IsolatedAsyncioTestCase):
    async def test_off_era_token_response_uses_fallback(self):
        brain = _brain("Stormtroopers just stormed the cantina, citizen.")
        resp = await brain.dialogue("what's the news?", db=None)
        self.assertEqual(resp, _FALLBACK)
        self.assertNotIn("Stormtrooper", resp)

    async def test_canonical_figure_response_uses_fallback(self):
        brain = _brain("Anakin Skywalker was just in here asking the same.")
        resp = await brain.dialogue("seen anyone?", db=None)
        self.assertEqual(resp, _FALLBACK)

    async def test_clean_in_era_response_passes_through(self):
        clean = "What'll it be, offworlder? Credits up front."
        brain = _brain(clean)
        resp = await brain.dialogue("a drink", db=None)
        self.assertEqual(resp, clean)

    async def test_off_era_response_not_persisted_to_memory(self):
        brain = _brain("The Empire pays well for informants like you.")
        saved = []

        async def _spy_save(db, char_id, player_input, npc_response):
            saved.append(npc_response)

        brain._save_memory = _spy_save  # type: ignore[assignment]

        class _FakeDB:
            async def fetchall(self, *a, **k):
                return []

        resp = await brain.dialogue("hi", player_name="Han",
                                    player_char_id=7, db=_FakeDB())
        self.assertEqual(resp, _FALLBACK)
        self.assertEqual(saved, [], "an off-era (fallback) line must not be saved")

    async def test_clean_response_is_persisted(self):
        clean = "Mind the Hutt's enforcers near the door."
        brain = _brain(clean)
        saved = []

        async def _spy_save(db, char_id, player_input, npc_response):
            saved.append(npc_response)

        brain._save_memory = _spy_save  # type: ignore[assignment]

        class _FakeDB:
            async def fetchall(self, *a, **k):
                return []

        resp = await brain.dialogue("hi", player_name="Han",
                                    player_char_id=7, db=_FakeDB())
        self.assertEqual(resp, clean)
        self.assertEqual(saved, [clean])


class TestNpcBrainSystemPromptEra(unittest.TestCase):
    def test_prompt_carries_era_hint_and_drops_gcw_phrasing(self):
        brain = _brain("unused")
        prompt = brain._build_system_prompt()
        self.assertIn("Clone Wars", prompt)
        self.assertNotIn("in a Star Wars setting", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
