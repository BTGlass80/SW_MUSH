# -*- coding: utf-8 -*-
"""
tests/test_fun2_chargen_couple.py — fun2 template→chain affinity coupling.

Tests:
  1. TestAffinityMap          — every template maps to a real, unlocked chain
  2. TestClashDetection       — republic template + CIS chain → clash detected;
                                CIS template + republic chain → clash detected
  3. TestNoClash              — coherent pairs are NOT flagged
  4. TestIndependentNoClash   — independent/guild templates never clash
  5. TestWizardRecommends     — after template pick, render includes '★ recommended'
                                for the affinity chain
  6. TestWizardClashConfirm   — wizard gates a clash pick behind yes/no confirm
  7. TestWizardClashConfirmNo — 'no' at the confirm prompt clears pending and
                                re-shows the chain menu
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


# ── helpers ────────────────────────────────────────────────────────────────


class _MockReg:
    """Duck-typed registries so CreationWizard.__init__ runs without DB."""
    def get(self, *a, **kw): return None
    def __getattr__(self, name): return lambda *a, **kw: None
    def skills_for_attribute(self, *a, **kw): return []


def _set_era(era_code: str = "clone_wars"):
    from engine.era_state import set_active_config
    set_active_config(types.SimpleNamespace(active_era=era_code))


def _build_wizard(era="clone_wars", is_first_character=True):
    _set_era(era)
    from engine.creation_wizard import CreationWizard
    return CreationWizard(_MockReg(), _MockReg(), width=80,
                          is_first_character=is_first_character)


def _corpus():
    """Return the live CW chain corpus."""
    _set_era("clone_wars")
    from engine.tutorial_chains import load_tutorial_chains
    return load_tutorial_chains()


class _IsolatedBase(unittest.TestCase):
    def tearDown(self):
        from engine.era_state import clear_active_config
        clear_active_config()


# ── 1. Affinity map integrity ──────────────────────────────────────────────


class TestAffinityMap(_IsolatedBase):
    """Every template key in TEMPLATE_CHAIN_AFFINITY maps to a chain that
    (a) exists in the live CW corpus and (b) is not locked."""

    def test_all_affinity_chains_exist_and_are_unlocked(self):
        from engine.creation_wizard import TEMPLATE_CHAIN_AFFINITY
        corpus = _corpus()
        by_id = corpus.by_id()
        for tmpl_key, chain_id in TEMPLATE_CHAIN_AFFINITY.items():
            with self.subTest(template=tmpl_key):
                self.assertIn(
                    chain_id, by_id,
                    f"Affinity chain '{chain_id}' for template '{tmpl_key}' "
                    f"not found in corpus"
                )
                chain = by_id[chain_id]
                self.assertFalse(
                    chain.locked,
                    f"Affinity chain '{chain_id}' for template '{tmpl_key}' "
                    f"is locked — cannot be a default recommendation"
                )

    def test_all_cw_templates_have_affinity_entry(self):
        """Every template in the CW TEMPLATES dict has an affinity mapping."""
        from engine.creation import TEMPLATES
        from engine.creation_wizard import TEMPLATE_CHAIN_AFFINITY
        _set_era("clone_wars")
        for tmpl_key in TEMPLATES:
            with self.subTest(template=tmpl_key):
                self.assertIn(
                    tmpl_key, TEMPLATE_CHAIN_AFFINITY,
                    f"Template '{tmpl_key}' has no TEMPLATE_CHAIN_AFFINITY entry"
                )

    def test_all_cw_templates_have_faction_entry(self):
        """Every CW template has a faction code in TEMPLATE_FACTION."""
        from engine.creation import TEMPLATES
        from engine.creation_wizard import TEMPLATE_FACTION
        _set_era("clone_wars")
        for tmpl_key in TEMPLATES:
            with self.subTest(template=tmpl_key):
                self.assertIn(
                    tmpl_key, TEMPLATE_FACTION,
                    f"Template '{tmpl_key}' has no TEMPLATE_FACTION entry"
                )


# ── 2. Clash detection ────────────────────────────────────────────────────


class TestClashDetection(_IsolatedBase):
    """War-faction crossing is detected as a clash."""

    def _wizard_with_template(self, tmpl_key):
        w = _build_wizard()
        w._selected_template_key = tmpl_key
        # Ensure corpus is loaded (it is, since we used clone_wars era)
        return w

    def test_smuggler_template_plus_republic_soldier_chain_is_clash(self):
        """The canonical identity collision: Smuggler (independent) + Republic
        Soldier chain force-joins the GAR and reskins the player as a clone
        trooper, overriding their smuggler background. Per Brian's decision
        this MUST warn (with confirm) — an independent template picking a
        war-faction chain surfaces the consequence before commit.
        """
        corpus = _corpus()
        rep_soldier = corpus.by_id()["republic_soldier"]
        w = self._wizard_with_template("smuggler")
        msg = w._faction_clash_warning("republic_soldier", rep_soldier)
        self.assertNotEqual(msg, "", "Smuggler + Republic Soldier must warn")
        self.assertIn("republic", msg.lower())

    def test_clone_trooper_template_plus_separatist_commando_is_clash(self):
        """Clone Trooper (republic) + Separatist Commando (cis) = clash."""
        corpus = _corpus()
        chain = corpus.by_id()["separatist_commando"]
        w = self._wizard_with_template("clone_trooper")
        msg = w._faction_clash_warning("separatist_commando", chain)
        self.assertNotEqual(msg, "", "republic+cis should produce a clash warning")
        self.assertIn("cis", msg.lower())

    def test_republic_officer_plus_separatist_agent_is_clash(self):
        """Republic Officer (republic) + Separatist Agent (cis) = clash."""
        corpus = _corpus()
        chain = corpus.by_id()["separatist_agent"]
        w = self._wizard_with_template("republic_officer")
        msg = w._faction_clash_warning("separatist_agent", chain)
        self.assertNotEqual(msg, "", "republic_officer + cis chain should clash")

    def test_cis_field_agent_plus_republic_soldier_is_clash(self):
        """CIS Field Agent (cis) + Republic Soldier (republic) = clash."""
        corpus = _corpus()
        chain = corpus.by_id()["republic_soldier"]
        w = self._wizard_with_template("cis_field_agent")
        msg = w._faction_clash_warning("republic_soldier", chain)
        self.assertNotEqual(msg, "", "cis_field_agent + republic chain should clash")
        self.assertIn("republic", msg.lower())

    def test_separatist_pilot_plus_republic_intelligence_is_clash(self):
        """Separatist Pilot (cis) + Republic Intelligence (republic) = clash."""
        corpus = _corpus()
        chain = corpus.by_id()["republic_intelligence"]
        w = self._wizard_with_template("separatist_pilot")
        msg = w._faction_clash_warning("republic_intelligence", chain)
        self.assertNotEqual(msg, "", "separatist_pilot + republic chain should clash")


# ── 3. Coherent pairs are not flagged ─────────────────────────────────────


class TestNoClash(_IsolatedBase):
    """Coherent template+chain combos produce no warning."""

    def _warn(self, tmpl_key, chain_id):
        corpus = _corpus()
        chain = corpus.by_id()[chain_id]
        w = _build_wizard()
        w._selected_template_key = tmpl_key
        return w._faction_clash_warning(chain_id, chain)

    def test_clone_trooper_plus_republic_soldier_no_clash(self):
        self.assertEqual(self._warn("clone_trooper", "republic_soldier"), "")

    def test_republic_officer_plus_republic_soldier_no_clash(self):
        self.assertEqual(self._warn("republic_officer", "republic_soldier"), "")

    def test_cis_field_agent_plus_separatist_agent_no_clash(self):
        self.assertEqual(self._warn("cis_field_agent", "separatist_agent"), "")

    def test_separatist_pilot_plus_separatist_commando_no_clash(self):
        self.assertEqual(self._warn("separatist_pilot", "separatist_commando"), "")

    def test_bounty_hunter_plus_bounty_hunter_no_clash(self):
        self.assertEqual(self._warn("bounty_hunter", "bounty_hunter"), "")

    def test_smuggler_plus_smuggler_no_clash(self):
        self.assertEqual(self._warn("smuggler", "smuggler"), "")


# ── 4. Independent/guild templates never clash ─────────────────────────────


class TestIndependentWarChainWarns(_IsolatedBase):
    """Independent/guild templates WARN (with confirm) when picking a
    WAR-faction chain — the chain force-joins them to a war faction + issues
    its kit, overriding their background (the canonical collision). They do
    NOT warn for an independent chain (covered in TestNoClash). The warn is a
    surfaced consequence, not a block — the player can still confirm."""

    def _warn(self, tmpl_key, chain_id):
        corpus = _corpus()
        chain = corpus.by_id()[chain_id]
        w = _build_wizard()
        w._selected_template_key = tmpl_key
        return w._faction_clash_warning(chain_id, chain)

    def test_bounty_hunter_plus_republic_soldier_warns(self):
        # BH enlisting in the GAR overrides their guild identity → surface it.
        self.assertNotEqual(self._warn("bounty_hunter", "republic_soldier"), "")

    def test_scoundrel_plus_separatist_commando_warns(self):
        self.assertNotEqual(self._warn("scoundrel", "separatist_commando"), "")

    def test_technician_plus_republic_intelligence_warns(self):
        self.assertNotEqual(self._warn("technician", "republic_intelligence"), "")

    def test_no_template_key_set_no_clash(self):
        """Scratch-path (no template) never generates a clash."""
        corpus = _corpus()
        chain = corpus.by_id()["republic_soldier"]
        w = _build_wizard()
        # _selected_template_key is None on scratch path
        msg = w._faction_clash_warning("republic_soldier", chain)
        self.assertEqual(msg, "")


# ── 5. Wizard render marks recommended chain ──────────────────────────────


class TestWizardRecommends(_IsolatedBase):
    """After template selection, _render_tutorial_chain marks the affinity
    chain with the '★ recommended' badge."""

    def test_clone_trooper_template_marks_republic_soldier_recommended(self):
        w = _build_wizard()
        w._selected_template_key = "clone_trooper"
        # Trigger the render (it also builds _menu_chains)
        output = w._render_tutorial_chain()
        self.assertIn("recommended", output.lower(),
                      "republic_soldier should be marked recommended for clone_trooper")

    def test_smuggler_template_marks_smuggler_chain_recommended(self):
        w = _build_wizard()
        w._selected_template_key = "smuggler"
        output = w._render_tutorial_chain()
        self.assertIn("recommended", output.lower(),
                      "smuggler chain should be marked recommended for smuggler template")

    def test_no_template_no_recommended_badge(self):
        """Scratch path: no '★ recommended' badge since no template chosen."""
        w = _build_wizard()
        # _selected_template_key is None
        output = w._render_tutorial_chain()
        self.assertNotIn("★ recommended", output,
                         "No template → no recommended badge should appear")

    def test_all_templates_render_without_error(self):
        """Every CW template key generates a render without exception."""
        from engine.creation_wizard import TEMPLATE_CHAIN_AFFINITY
        for tmpl_key in TEMPLATE_CHAIN_AFFINITY:
            with self.subTest(template=tmpl_key):
                w = _build_wizard()
                w._selected_template_key = tmpl_key
                output = w._render_tutorial_chain()
                self.assertIsInstance(output, str)
                self.assertGreater(len(output), 0)


# ── 6. Wizard clash-confirm gate ─────────────────────────────────────────


class TestWizardClashConfirm(_IsolatedBase):
    """A clash pick sets _clash_confirm_pending and surfaces a warning;
    'yes' commits it."""

    def _wizard_at_chain_step(self, tmpl_key):
        w = _build_wizard()
        w._selected_template_key = tmpl_key
        w.step = "tutorial_chain"
        # Pre-build the menu by rendering (needed for numeric picks)
        w._render_tutorial_chain()
        return w

    def test_clash_pick_sets_pending_and_returns_warning(self):
        """Picking a clashing chain raises a warning, not an immediate commit."""
        corpus = _corpus()
        chain = corpus.by_id()["separatist_commando"]
        w = _build_wizard()
        w._selected_template_key = "clone_trooper"
        w._chains_corpus = corpus

        display, _prompt, done = w._select_chain_by_id("separatist_commando")
        self.assertFalse(done, "Chain step should not be done")
        self.assertIsNotNone(w._clash_confirm_pending,
                             "_clash_confirm_pending should be set on clash")
        self.assertEqual(w._clash_confirm_pending, "separatist_commando")
        self.assertIn("clash", display.lower(),
                      "Warning message should mention 'clash'")

    def test_yes_after_clash_commits_chain(self):
        """Typing 'yes' after the clash warning commits the chain and advances."""
        corpus = _corpus()
        w = _build_wizard()
        w._selected_template_key = "clone_trooper"
        w._chains_corpus = corpus
        w.step = "tutorial_chain"
        w._render_tutorial_chain()

        # Trigger clash
        w._select_chain_by_id("separatist_commando")
        self.assertIsNotNone(w._clash_confirm_pending)

        # Confirm
        _display, _prompt, done = w._handle_tutorial_chain("yes")
        self.assertIsNone(w._clash_confirm_pending,
                          "Pending should clear after 'yes'")
        self.assertEqual(w._selected_chain_id, "separatist_commando",
                         "Chain should be committed after 'yes'")


# ── 7. Wizard clash-confirm 'no' clears and re-shows menu ─────────────────


class TestWizardClashConfirmNo(_IsolatedBase):
    """'no' at the confirm prompt clears pending and re-shows the chain menu."""

    def test_no_clears_pending_and_returns_to_menu(self):
        corpus = _corpus()
        w = _build_wizard()
        w._selected_template_key = "clone_trooper"
        w._chains_corpus = corpus
        w.step = "tutorial_chain"
        w._render_tutorial_chain()

        # Trigger clash
        w._select_chain_by_id("separatist_commando")
        self.assertIsNotNone(w._clash_confirm_pending)

        # Decline
        display, _prompt, done = w._handle_tutorial_chain("no")
        self.assertIsNone(w._clash_confirm_pending,
                          "Pending should clear after 'no'")
        self.assertIsNone(w._selected_chain_id,
                          "No chain should be committed after 'no'")
        self.assertFalse(done)
        # Should re-render the chain menu
        self.assertIn("tutorial chain", display.lower(),
                      "Menu should re-render after 'no'")


if __name__ == "__main__":
    unittest.main()
