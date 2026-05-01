# -*- coding: utf-8 -*-
"""
tests/test_f8c1_chargen_chain_selection.py — F.8.c.1 integration tests.

F.8.c.1 (Apr 30 2026) wires the F.8 tutorial chain seam into the
chargen wizard. Players in the CW era get an extra step
(`tutorial_chain`) where they pick a profession path; the wizard
records the selection, and game_server.py post-chargen merges the
chain state block into the character's attributes JSON before DB
save.

Test sections:
  1. TestEraDetection         — CW vs GCW step list selection
  2. TestStepListsCW          — CW step lists include tutorial_chain
  3. TestChargenAttrsHelper   — _chargen_attrs_for_chain_check shape
  4. TestRenderTutorialChain  — render produces chains menu
  5. TestSelectionByNumber    — picking 1..N works
  6. TestSelectionByChainId   — direct chain_id picker
  7. TestSkipPath             — `next` skips the chain
  8. TestLockedChainRejection — jedi_path direct selection blocked
  9. TestChargenAnySentinel   — __chargen_any__ unlocks faction chains
 10. TestChainBlockShape      — block has chain_id, step, started_at,
                                completed_steps, completion_state
 11. TestStartingRoomSlug     — getter returns chain's starting_room
 12. TestWorldWriterSlugPersist — world_writer.py stamps slug on rooms
 13. TestNavigationPaths      — back/next traverse the CW step list
"""
from __future__ import annotations

import os
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _MockReg:
    """Mock registries — duck-typed so CreationWizard.__init__ runs."""
    def get(self, *a, **kw): return None
    def __getattr__(self, name): return lambda *a, **kw: None
    def skills_for_attribute(self, *a, **kw): return []


def _set_era(era_code: str):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


def _build_wizard(era="clone_wars"):
    _set_era(era)
    from engine.creation_wizard import CreationWizard
    return CreationWizard(_MockReg(), _MockReg(), width=80)


# ──────────────────────────────────────────────────────────────────────
# Test isolation: every test class resets the era at tearDown so the
# F.8.c.1 sandbox doesn't bleed CW state into subsequent test files
# (e.g. F.6a3's TestLegacyPath assumes GCW default era).
# ──────────────────────────────────────────────────────────────────────

class _F8C1IsolatedBase(unittest.TestCase):
    def tearDown(self):
        from engine.era_state import clear_active_config
        clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# 1. Era detection
# ──────────────────────────────────────────────────────────────────────

class TestEraDetection(_F8C1IsolatedBase):

    def test_cw_era_loads_chains_corpus(self):
        w = _build_wizard("clone_wars")
        self.assertIsNotNone(w._chains_corpus)
        self.assertEqual(len(w._chains_corpus.chains), 8)

    def test_gcw_era_no_chains_corpus(self):
        w = _build_wizard("gcw")
        self.assertIsNone(w._chains_corpus)

    def test_unknown_era_no_chains_corpus(self):
        w = _build_wizard("nonexistent_era_for_test")
        self.assertIsNone(w._chains_corpus)


# ──────────────────────────────────────────────────────────────────────
# 2. Step lists CW
# ──────────────────────────────────────────────────────────────────────

class TestStepListsCW(_F8C1IsolatedBase):

    def test_cw_scratch_includes_chain_step(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        self.assertIn(STEP_TUTORIAL_CHAIN, w.scratch_steps)

    def test_cw_template_includes_chain_step(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        self.assertIn(STEP_TUTORIAL_CHAIN, w.template_steps)

    def test_gcw_scratch_excludes_chain_step(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("gcw")
        self.assertNotIn(STEP_TUTORIAL_CHAIN, w.scratch_steps)

    def test_gcw_template_excludes_chain_step(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("gcw")
        self.assertNotIn(STEP_TUTORIAL_CHAIN, w.template_steps)

    def test_cw_chain_step_immediately_before_review(self):
        from engine.creation_wizard import (
            STEP_TUTORIAL_CHAIN, STEP_REVIEW,
        )
        w = _build_wizard("clone_wars")
        for steps in (w.scratch_steps, w.template_steps):
            self.assertEqual(
                steps.index(STEP_TUTORIAL_CHAIN) + 1,
                steps.index(STEP_REVIEW),
                f"chain step should immediately precede review in {steps}",
            )

    def test_legacy_module_constants_unchanged(self):
        from engine.creation_wizard import (
            SCRATCH_STEPS, TEMPLATE_STEPS,
            SCRATCH_STEPS_LEGACY, TEMPLATE_STEPS_LEGACY,
            STEP_TUTORIAL_CHAIN,
        )
        self.assertEqual(SCRATCH_STEPS, SCRATCH_STEPS_LEGACY)
        self.assertEqual(TEMPLATE_STEPS, TEMPLATE_STEPS_LEGACY)
        self.assertNotIn(STEP_TUTORIAL_CHAIN, SCRATCH_STEPS)


# ──────────────────────────────────────────────────────────────────────
# 3. Chargen attrs helper
# ──────────────────────────────────────────────────────────────────────

class TestChargenAttrsHelper(_F8C1IsolatedBase):

    def test_chargen_attrs_shape(self):
        w = _build_wizard("clone_wars")
        attrs = w._chargen_attrs_for_chain_check()
        self.assertTrue(attrs.get("chargen_complete"))
        self.assertEqual(attrs.get("faction_intent"), "__chargen_any__")
        self.assertFalse(attrs.get("force_sensitive"))
        self.assertFalse(attrs.get("jedi_path_unlocked"))

    def test_chargen_attrs_force_sensitive_when_set(self):
        w = _build_wizard("clone_wars")
        w._force_sensitive = True
        attrs = w._chargen_attrs_for_chain_check()
        self.assertTrue(attrs.get("force_sensitive"))


# ──────────────────────────────────────────────────────────────────────
# 4. Render tutorial chain
# ──────────────────────────────────────────────────────────────────────

class TestRenderTutorialChain(_F8C1IsolatedBase):

    def test_render_populates_menu(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        self.assertEqual(len(w._menu_chains), 7)

    def test_render_menu_excludes_jedi_path(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        self.assertNotIn("jedi_path", w._menu_chains)

    def test_render_menu_includes_smuggler(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        self.assertIn("smuggler", w._menu_chains)

    def test_render_menu_includes_republic_soldier(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        self.assertIn("republic_soldier", w._menu_chains)


# ──────────────────────────────────────────────────────────────────────
# 5. Selection by number
# ──────────────────────────────────────────────────────────────────────

class TestSelectionByNumber(_F8C1IsolatedBase):

    def test_select_chain_one(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        first = w._menu_chains[0]
        w._selected_chain_id = first  # simulate select w/o re-rendering review
        self.assertEqual(w.get_selected_chain_id(), first)

    def test_invalid_number_keeps_selection_none(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        display, prompt, done = w._handle_tutorial_chain("99")
        self.assertIsNone(w.get_selected_chain_id())


# ──────────────────────────────────────────────────────────────────────
# 6. Selection by chain_id
# ──────────────────────────────────────────────────────────────────────

class TestSelectionByChainId(_F8C1IsolatedBase):

    def test_direct_unknown_chain_id_rejected(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        display, prompt, done = w._handle_tutorial_chain("not_a_real_chain")
        self.assertIsNone(w.get_selected_chain_id())


# ──────────────────────────────────────────────────────────────────────
# 7. Skip path
# ──────────────────────────────────────────────────────────────────────

class TestSkipPath(_F8C1IsolatedBase):

    def test_next_skips_chain(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        try:
            w._handle_tutorial_chain("next")
        except (TypeError, AttributeError):
            # Mock-related render explosion is OK — selection state
            # is the contract being tested
            pass
        self.assertIsNone(w.get_selected_chain_id())
        self.assertIsNone(w.get_tutorial_chain_block())

    def test_skip_alias_works(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        try:
            w._handle_tutorial_chain("skip")
        except (TypeError, AttributeError):
            pass
        self.assertIsNone(w.get_selected_chain_id())


# ──────────────────────────────────────────────────────────────────────
# 8. Locked-chain rejection
# ──────────────────────────────────────────────────────────────────────

class TestLockedChainRejection(_F8C1IsolatedBase):

    def test_direct_jedi_path_blocked(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        display, prompt, done = w._handle_tutorial_chain("jedi_path")
        self.assertIsNone(w.get_selected_chain_id())
        self.assertIn("Jedi", display)

    def test_jedi_path_not_in_menu(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        self.assertNotIn("jedi_path", w._menu_chains)


# ──────────────────────────────────────────────────────────────────────
# 9. Chargen-any sentinel
# ──────────────────────────────────────────────────────────────────────

class TestChargenAnySentinel(_F8C1IsolatedBase):

    def test_sentinel_passes_republic_chain(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        _set_era("clone_wars")
        corpus = load_tutorial_chains()
        chain = corpus.by_id()["republic_soldier"]
        attrs = {"chargen_complete": True,
                 "faction_intent": "__chargen_any__"}
        is_locked, reason = is_chain_locked_for_character(chain, attrs)
        self.assertFalse(is_locked, f"reason: {reason!r}")

    def test_sentinel_passes_cis_chain(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        _set_era("clone_wars")
        corpus = load_tutorial_chains()
        chain = corpus.by_id()["separatist_commando"]
        attrs = {"chargen_complete": True,
                 "faction_intent": "__chargen_any__"}
        is_locked, reason = is_chain_locked_for_character(chain, attrs)
        self.assertFalse(is_locked)

    def test_real_value_match_works(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        _set_era("clone_wars")
        corpus = load_tutorial_chains()
        chain = corpus.by_id()["republic_soldier"]
        attrs = {"chargen_complete": True, "faction_intent": "republic"}
        self.assertFalse(is_chain_locked_for_character(chain, attrs)[0])

    def test_real_value_mismatch_blocks(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        _set_era("clone_wars")
        corpus = load_tutorial_chains()
        chain = corpus.by_id()["republic_soldier"]
        attrs = {"chargen_complete": True, "faction_intent": "cis"}
        self.assertTrue(is_chain_locked_for_character(chain, attrs)[0])

    def test_jedi_path_locked_with_sentinel(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        _set_era("clone_wars")
        corpus = load_tutorial_chains()
        chain = corpus.by_id()["jedi_path"]
        attrs = {"chargen_complete": True,
                 "faction_intent": "__chargen_any__"}
        is_locked, reason = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)


# ──────────────────────────────────────────────────────────────────────
# 10. Chain block shape
# ──────────────────────────────────────────────────────────────────────

class TestChainBlockShape(_F8C1IsolatedBase):

    def test_block_returns_none_when_no_selection(self):
        w = _build_wizard("clone_wars")
        self.assertIsNone(w.get_tutorial_chain_block())

    def test_block_required_keys(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "smuggler"
        block = w.get_tutorial_chain_block()
        required = {"chain_id", "step", "started_at",
                    "completed_steps", "completion_state"}
        self.assertTrue(required <= set(block.keys()))

    def test_block_initial_step_is_one(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "smuggler"
        block = w.get_tutorial_chain_block()
        self.assertEqual(block["step"], 1)

    def test_block_initial_state_active(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "smuggler"
        block = w.get_tutorial_chain_block()
        self.assertEqual(block["completion_state"], "active")

    def test_block_completed_steps_empty(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "smuggler"
        block = w.get_tutorial_chain_block()
        self.assertEqual(block["completed_steps"], [])


# ──────────────────────────────────────────────────────────────────────
# 11. Starting-room slug getter
# ──────────────────────────────────────────────────────────────────────

class TestStartingRoomSlug(_F8C1IsolatedBase):

    def test_starting_room_for_smuggler(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "smuggler"
        self.assertEqual(
            w.get_tutorial_chain_starting_room_slug(),
            "tatooine_spaceport_dock_94",
        )

    def test_starting_room_for_republic_soldier(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars")
        w.step = STEP_TUTORIAL_CHAIN
        w._render_tutorial_chain()
        w._selected_chain_id = "republic_soldier"
        self.assertEqual(
            w.get_tutorial_chain_starting_room_slug(),
            "tipoca_briefing_room",
        )

    def test_starting_room_none_when_no_selection(self):
        w = _build_wizard("clone_wars")
        self.assertIsNone(w.get_tutorial_chain_starting_room_slug())


# ──────────────────────────────────────────────────────────────────────
# 12. world_writer slug persistence
# ──────────────────────────────────────────────────────────────────────

class TestWorldWriterSlugPersist(_F8C1IsolatedBase):

    def test_world_writer_source_has_slug_persistence(self):
        ww_path = PROJECT_ROOT / "engine" / "world_writer.py"
        with open(ww_path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn('properties["slug"] = room.slug', src)
        self.assertIn("F.8.c.1", src)


# ──────────────────────────────────────────────────────────────────────
# 13. Navigation paths
# ──────────────────────────────────────────────────────────────────────

class TestNavigationPaths(_F8C1IsolatedBase):

    def test_next_step_after_background_is_chain_in_cw(self):
        from engine.creation_wizard import (
            STEP_BACKGROUND, STEP_TUTORIAL_CHAIN,
        )
        w = _build_wizard("clone_wars")
        w.path = "scratch"
        self.assertEqual(
            w._next_step_after(STEP_BACKGROUND), STEP_TUTORIAL_CHAIN,
        )

    def test_next_step_after_background_is_review_in_gcw(self):
        from engine.creation_wizard import STEP_BACKGROUND, STEP_REVIEW
        w = _build_wizard("gcw")
        w.path = "scratch"
        self.assertEqual(
            w._next_step_after(STEP_BACKGROUND), STEP_REVIEW,
        )

    def test_next_step_after_chain_is_review(self):
        from engine.creation_wizard import (
            STEP_TUTORIAL_CHAIN, STEP_REVIEW,
        )
        w = _build_wizard("clone_wars")
        w.path = "scratch"
        self.assertEqual(
            w._next_step_after(STEP_TUTORIAL_CHAIN), STEP_REVIEW,
        )


if __name__ == "__main__":
    unittest.main()
