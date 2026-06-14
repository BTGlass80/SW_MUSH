# -*- coding: utf-8 -*-
"""tests/test_era_validator.py — the shared Clone Wars era-cleanness authority
(engine/era_validator.py) and its first runtime consumer (the Ollama idle queue).

Covers three things this drop introduced:

  1. The canon constants are the SINGLE source of truth — the era-cleanness
     test and the lore-ingestion tool now import the SAME tuple, so they can't
     drift (identity guard).
  2. ``era_violations`` / ``is_era_clean`` behave as a runtime guard:
     case-insensitive, catches the GCW token set AND canonical figures, passes
     genuine Clone-Wars prose.
  3. The idle queue actually DROPS off-era LLM output before it caches/serves —
     the real bug this drop fixes (Mistral was prompted "Galactic Civil War"
     with no validator between its output and players).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import era_validator
from engine.era_validator import (
    BANNED_ERA_TOKENS,
    CANONICAL_FIGURES,
    ERA_PROMPT_HINT,
    era_violations,
    is_era_clean,
)


# ── 1. Canon + drift prevention ─────────────────────────────────────────────

class TestCanonAndDriftPrevention(unittest.TestCase):
    def test_banned_tokens_cover_core_gcw_terms(self):
        # Lock the load-bearing members; a future edit that drops one fails here.
        for tok in ("Imperial", "Empire", "Stormtrooper", "TIE fighter",
                    "X-Wing", "Galactic Civil War", "Death Star", "Order 66"):
            self.assertIn(tok, BANNED_ERA_TOKENS)

    def test_canonical_figures_present(self):
        for fig in ("Anakin", "Dooku", "Grievous", "Palpatine", "Yoda"):
            self.assertIn(fig, CANONICAL_FIGURES)

    def test_era_cleanness_test_imports_shared_tuple(self):
        # The era-cleanness suite must use THIS tuple, not a private copy.
        import tests.test_laneb_era_cleanness as laneb
        self.assertIs(laneb._BANNED, BANNED_ERA_TOKENS,
                      "test_laneb_era_cleanness must import BANNED_ERA_TOKENS "
                      "(found a divergent local copy — drift risk)")

    def test_ingest_tool_imports_shared_tuples(self):
        import importlib
        ingest = importlib.import_module("tools.ingest_lore")
        self.assertIs(ingest._BANNED, BANNED_ERA_TOKENS)
        self.assertIs(ingest._CANONICAL_FIGURES, CANONICAL_FIGURES)


# ── 2. Runtime guard behavior ───────────────────────────────────────────────

class TestEraViolations(unittest.TestCase):
    def test_clean_clone_wars_prose_passes(self):
        clean = ("A Republic gunship thunders overhead while clone troopers "
                 "secure the Hutt-controlled spaceport.")
        self.assertTrue(is_era_clean(clean))
        self.assertEqual(era_violations(clean), [])

    def test_case_insensitive_token_catch(self):
        # The model emits arbitrary casing; the guard must catch all of them.
        for txt in ("the EMPIRE returns", "an imperial patrol",
                    "swarming Stormtroopers", "a lone tie fighter"):
            self.assertFalse(is_era_clean(txt), f"missed: {txt!r}")

    def test_canonical_figure_catch(self):
        self.assertFalse(is_era_clean("Heard Anakin passed through the cantina."))
        self.assertFalse(is_era_clean("Nute Gunray raised the spice tax again."))

    def test_empty_text_is_clean(self):
        self.assertTrue(is_era_clean(""))
        self.assertEqual(era_violations(None), [])  # type: ignore[arg-type]

    def test_violations_reports_tokens(self):
        hits = era_violations("Imperial stormtroopers boarded the freighter")
        self.assertIn("imperial", hits)
        self.assertIn("stormtrooper", hits)

    def test_prompt_hint_is_clone_wars_framed(self):
        self.assertIn("Clone Wars", ERA_PROMPT_HINT)
        self.assertIn("CIS", ERA_PROMPT_HINT)


# ── 3. The actual fix: idle queue drops off-era LLM output ───────────────────

class _FakeAI:
    """Minimal stand-in for AIManager: returns a queued canned response."""
    def __init__(self, response: str):
        self._response = response

    async def generate(self, **kwargs) -> str:
        return self._response


class TestIdleQueueEraGuard(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        from engine import idle_queue
        self.idle_queue = idle_queue
        idle_queue._bark_cache.clear()
        idle_queue._housing_desc_cache.clear()

    def tearDown(self):
        self.idle_queue._bark_cache.clear()
        self.idle_queue._housing_desc_cache.clear()

    async def test_ambient_barks_drop_off_era_lines(self):
        from engine.idle_queue import AmbientBarkTask
        barks = json.dumps([
            "The cantina reeks of engine grease tonight.",   # clean
            "Blasted Imperial patrols are everywhere.",       # off-era token
            "Heard Anakin Skywalker passed through.",         # canonical figure
        ])
        task = AmbientBarkTask(npc_id=42, npc_name="Wuher", species="human",
                               personality="surly bartender")
        await task.execute(_FakeAI(barks), db=None)

        entry = self.idle_queue._bark_cache.get(42)
        self.assertIsNotNone(entry, "clean bark should still be cached")
        cached = entry["barks"]
        self.assertEqual(len(cached), 1, f"off-era barks not dropped: {cached}")
        self.assertIn("engine grease", cached[0])

    async def test_all_off_era_barks_leaves_cache_empty(self):
        from engine.idle_queue import AmbientBarkTask
        barks = json.dumps([
            "The Empire tightens its grip.",
            "Stormtroopers everywhere today.",
        ])
        task = AmbientBarkTask(npc_id=99, npc_name="Spy", species="rodian",
                               personality="paranoid")
        await task.execute(_FakeAI(barks), db=None)
        # Nothing clean survived -> no cache entry (static room flavor covers).
        self.assertIsNone(self.idle_queue._bark_cache.get(99))

    async def test_housing_desc_off_era_not_cached(self):
        from engine.idle_queue import HousingDescTask
        off_era = ("You stand in a grim Imperial garrison checkpoint, "
                   "stormtroopers eyeing every passerby.")
        task = HousingDescTask(housing_id=7, room_name="Bunk", planet="Tatooine")
        await task.execute(_FakeAI(off_era), db=None)
        self.assertIsNone(self.idle_queue._housing_desc_cache.get(7),
                          "off-era housing desc must not be cached")

    async def test_housing_desc_clean_is_cached(self):
        from engine.idle_queue import HousingDescTask
        clean = ("You stand in a cramped sandstone hovel; twin-sun light "
                 "filters through a dust-caked vent as a moisture vaporator hums.")
        task = HousingDescTask(housing_id=8, room_name="Hovel", planet="Tatooine")
        await task.execute(_FakeAI(clean), db=None)
        self.assertEqual(self.idle_queue._housing_desc_cache.get(8), clean)


# ── 4. Regression guard: the reported bug is gone ───────────────────────────

class TestNoGcwPromptRegression(unittest.TestCase):
    def test_idle_queue_source_has_no_gcw_era_prompt(self):
        """The fixed bug: HousingDescTask hardcoded 'Galactic Civil War era'
        in a Clone Wars game. Lock it out of the source for good."""
        path = os.path.join(PROJECT_ROOT, "engine", "idle_queue.py")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        self.assertNotIn("Galactic Civil War", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
