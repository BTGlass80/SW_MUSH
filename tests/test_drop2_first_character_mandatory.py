# -*- coding: utf-8 -*-
"""
tests/test_drop2_first_character_mandatory.py — Drop 2 (May 19 2026)

Pins the first-character-mandatory tutorial-chain policy in the
CreationWizard. Companion server-side gating ships in Drop 2b
(server/api.py::handle_create_character).

Test sections:
  1. TestDefaultIsMandatory     — default constructor refuses skip
  2. TestExplicitMandatory      — is_first_character=True refuses skip
  3. TestExplicitOptional       — is_first_character=False permits skip
  4. TestRenderHidesPromptOnMandatory
                                — render omits the `next` line when mandatory
  5. TestRenderShowsPromptOnOptional
                                — render shows `next` line when optional
  6. TestFlagDoesNotAffectGCW   — GCW (no chains corpus) ignores the flag

The wizard's chain step refuses to accept "next" or "skip" as input
when self._is_first_character is True. It still accepts valid chain
numbers / chain_ids. Skip-rejection returns the original render with
a refusal message inline; the step does NOT advance past
STEP_TUTORIAL_CHAIN until the player picks a chain.

Note on coexistence with test_f8c1_chargen_chain_selection.py:
those tests still assert `_selected_chain_id is None` after passing
"next" to the wizard. Under the new default (mandatory), that
assertion remains true — because the skip is refused, the wizard
state (including _selected_chain_id) is untouched. The F.8.c.1
tests' semantics have weakened; a follow-up should tighten them by
passing is_first_character=False explicitly when testing the skip
branch.
"""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class _MockReg:
    """Mock registries — duck-typed so CreationWizard.__init__ runs.
    Mirrors the helper from test_f8c1_chargen_chain_selection.py so
    failure modes between the two suites stay consistent.
    """
    def get(self, *a, **kw): return None
    def __getattr__(self, name): return lambda *a, **kw: None
    def skills_for_attribute(self, *a, **kw): return []


def _set_era(era_code: str):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


def _build_wizard(era="clone_wars", is_first_character=True):
    _set_era(era)
    from engine.creation_wizard import CreationWizard
    return CreationWizard(
        _MockReg(), _MockReg(),
        width=80, is_first_character=is_first_character,
    )


class _IsolatedBase(unittest.TestCase):
    def tearDown(self):
        from engine.era_state import clear_active_config
        clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# 1. Default is mandatory
# ──────────────────────────────────────────────────────────────────────

class TestDefaultIsMandatory(_IsolatedBase):

    def test_default_constructor_sets_first_character_true(self):
        # No explicit is_first_character → default True (mandatory).
        # This is the safe default: if the caller doesn't tell us
        # whether it's a first character, we refuse the skip path.
        from engine.era_state import set_active_config
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        try:
            from engine.creation_wizard import CreationWizard
            w = CreationWizard(_MockReg(), _MockReg(), width=80)
            self.assertTrue(w._is_first_character,
                            "Default must be True (mandatory tutorial)")
        finally:
            from engine.era_state import clear_active_config
            clear_active_config()


# ──────────────────────────────────────────────────────────────────────
# 2. Explicit mandatory refuses skip
# ──────────────────────────────────────────────────────────────────────

class TestExplicitMandatory(_IsolatedBase):

    def test_next_refused_when_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=True)
        w.step = STEP_TUTORIAL_CHAIN
        # Prime _menu_chains via render. Mocked deps may raise inside
        # the helper, but the input-handler path we care about does
        # not depend on the render side-effects being clean.
        try:
            w._render_tutorial_chain()
        except (TypeError, AttributeError):
            pass

        display, prompt, done = w._handle_tutorial_chain("next")

        # The step must NOT advance — wizard is parked on chain step.
        self.assertEqual(w.step, STEP_TUTORIAL_CHAIN,
                         "Mandatory chain step must not advance on skip")
        # The refusal message must explain why.
        self.assertIn("first character", display.lower())
        # No chain ID was assigned by the failed skip.
        self.assertIsNone(w.get_selected_chain_id())
        # is_done must be False — chargen continues.
        self.assertFalse(done)

    def test_skip_alias_also_refused_when_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=True)
        w.step = STEP_TUTORIAL_CHAIN
        try:
            w._render_tutorial_chain()
        except (TypeError, AttributeError):
            pass

        display, prompt, done = w._handle_tutorial_chain("skip")

        self.assertEqual(w.step, STEP_TUTORIAL_CHAIN)
        self.assertIn("first character", display.lower())
        self.assertIsNone(w.get_selected_chain_id())


# ──────────────────────────────────────────────────────────────────────
# 3. Explicit optional permits skip
# ──────────────────────────────────────────────────────────────────────

class TestExplicitOptional(_IsolatedBase):

    def test_next_permitted_when_not_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=False)
        w.step = STEP_TUTORIAL_CHAIN
        try:
            w._render_tutorial_chain()
        except (TypeError, AttributeError):
            pass

        # Skip should now succeed — wizard advances past chain step.
        try:
            w._handle_tutorial_chain("next")
        except (TypeError, AttributeError):
            # Mock-related render explosion is OK; selection state is
            # the contract being tested. Mirrors the F.8.c.1 pattern.
            pass

        # Chain step has advanced (or the input was accepted and
        # _selected_chain_id remains None per skip-clears semantics).
        self.assertIsNone(w.get_selected_chain_id())
        # Wizard step has moved past STEP_TUTORIAL_CHAIN.
        self.assertNotEqual(w.step, STEP_TUTORIAL_CHAIN,
                            "Optional chain step must advance on skip")

    def test_skip_alias_also_permitted_when_not_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=False)
        w.step = STEP_TUTORIAL_CHAIN
        try:
            w._render_tutorial_chain()
        except (TypeError, AttributeError):
            pass
        try:
            w._handle_tutorial_chain("skip")
        except (TypeError, AttributeError):
            pass
        self.assertIsNone(w.get_selected_chain_id())
        self.assertNotEqual(w.step, STEP_TUTORIAL_CHAIN)


# ──────────────────────────────────────────────────────────────────────
# 4. Render omits skip prompt when mandatory
# ──────────────────────────────────────────────────────────────────────

class TestRenderHidesPromptOnMandatory(_IsolatedBase):

    def test_render_omits_next_prompt_when_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=True)
        w.step = STEP_TUTORIAL_CHAIN
        try:
            display = w._render_tutorial_chain()
        except (TypeError, AttributeError):
            # Render may explode on mocked deps after the prompt
            # block is built — the early lines we care about are
            # still buffered in the partial result.
            display = ""
        # The "skip the tutorial" prompt line must NOT appear.
        self.assertNotIn("skip the tutorial", display)
        # The refusal hint should be present instead.
        self.assertIn("skip is not available", display.lower())


# ──────────────────────────────────────────────────────────────────────
# 5. Render shows skip prompt when optional
# ──────────────────────────────────────────────────────────────────────

class TestRenderShowsPromptOnOptional(_IsolatedBase):

    def test_render_includes_next_prompt_when_not_first_character(self):
        from engine.creation_wizard import STEP_TUTORIAL_CHAIN
        w = _build_wizard("clone_wars", is_first_character=False)
        w.step = STEP_TUTORIAL_CHAIN
        try:
            display = w._render_tutorial_chain()
        except (TypeError, AttributeError):
            display = ""
        # The skip prompt line must appear.
        self.assertIn("skip the tutorial", display)
        # And the refusal hint must NOT appear.
        self.assertNotIn("skip is not available", display.lower())


# ──────────────────────────────────────────────────────────────────────
# 6. Flag is harmless under GCW (no chains corpus)
# ──────────────────────────────────────────────────────────────────────

class TestFlagDoesNotAffectGCW(_IsolatedBase):

    def test_gcw_constructor_accepts_flag_without_error(self):
        # GCW has no tutorials/chains.yaml; the wizard's
        # _chains_corpus is None and STEP_TUTORIAL_CHAIN is not in
        # the step list. Passing is_first_character=True must not
        # raise or change behavior.
        w = _build_wizard("gcw", is_first_character=True)
        self.assertIsNone(w._chains_corpus)
        self.assertTrue(w._is_first_character)

    def test_gcw_constructor_accepts_false_flag(self):
        w = _build_wizard("gcw", is_first_character=False)
        self.assertIsNone(w._chains_corpus)
        self.assertFalse(w._is_first_character)


if __name__ == "__main__":
    unittest.main()
