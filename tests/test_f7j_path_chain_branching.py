# -*- coding: utf-8 -*-
"""
tests/test_f7j_path_chain_branching.py — F.7.j path-flavored Jedi
chain branching.

F.7.j (May 4 2026) splits the formerly-monolithic `jedi_path`
chain in `data/worlds/clone_wars/tutorials/chains.yaml` into two
path-flavored siblings:

  - `jedi_path`              → Path A graduates (Order)
  - `jedi_path_independent`  → Path B graduates (Independent)

Path C deliberately has no chain — Path C does not set
`jedi_path_unlocked` and the Dark Path content is post-launch
(per `from_dust_to_stars_design_v2_clone_wars.md` §7.3).

The mechanism is a new mapped-key prerequisite shape recognized
by `engine.tutorial_chains.is_chain_locked_for_character`:
``{"village_chosen_path": "a"|"b"|"c"}``. Unlike
`{"faction_intent": ...}`, there is NO chargen sentinel — the
Jedi-Path chains MUST stay locked at chargen, so a chargen-fresh
attrs dict (no village_chosen_path set) correctly fails this
prereq.

Test sections:
  1. TestPrereqDictWidening      — `village_chosen_path` shape parses
  2. TestJediPathOrderGate       — `jedi_path` (Path A) gating
  3. TestJediPathIndependentGate — `jedi_path_independent` gating
  4. TestPathCNoUnlock           — Path C never unlocks either chain
  5. TestChargenLockedAtCreation — both chains locked at chargen for
                                   any chargen-fresh attrs dict
  6. TestChainShape              — both chains have the right shape
                                   (drop_room, faction_alignment, etc.)
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _corpus():
    """Helper — load the CW chains corpus once per test."""
    from engine.tutorial_chains import load_tutorial_chains
    return load_tutorial_chains(era="clone_wars")


def _attrs(**kwargs):
    """Helper — build a char_attrs dict with sensible defaults."""
    base = {
        "chargen_complete": False,
        "force_sensitive": False,
        "jedi_path_unlocked": False,
    }
    base.update(kwargs)
    return base


def _path_a_attrs():
    """Char who graduated Village Path A."""
    return _attrs(
        chargen_complete=True,
        force_sensitive=True,
        jedi_path_unlocked=True,
        village_chosen_path="a",
    )


def _path_b_attrs():
    """Char who graduated Village Path B."""
    return _attrs(
        chargen_complete=True,
        force_sensitive=True,
        jedi_path_unlocked=True,
        village_chosen_path="b",
    )


def _path_c_attrs():
    """Char who committed Village Path C (Dark Whispers).

    Path C does NOT set `jedi_path_unlocked` per `village_choice.py`
    `_commit_path_c`; instead it sets `dark_path_unlocked`. Force-
    sensitivity is still set."""
    return _attrs(
        chargen_complete=True,
        force_sensitive=True,
        jedi_path_unlocked=False,        # NOT unlocked for Path C
        dark_path_unlocked=True,
        village_chosen_path="c",
    )


# ──────────────────────────────────────────────────────────────────────
# 1. Prereq-dict widening — `village_chosen_path` shape parses
# ──────────────────────────────────────────────────────────────────────

class TestPrereqDictWidening(unittest.TestCase):
    """The chain corpus loader accepts `village_chosen_path` as a
    mapped-key prereq alongside `faction_intent`. The schema test
    in test_f8_tutorial_chains_yaml.py asserts this is an allowed
    key; here we directly load the corpus and verify the parser
    didn't drop the prereq."""

    def test_corpus_loads_clean_with_new_prereq_shape(self):
        c = _corpus()
        self.assertIsNotNone(c)
        self.assertTrue(c.ok, f"corpus errors: {c.errors!r}")

    def test_jedi_path_carries_village_chosen_path_a(self):
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        # Find the village_chosen_path prereq dict
        found = [p for p in chain.prerequisites
                 if isinstance(p, dict) and "village_chosen_path" in p]
        self.assertEqual(len(found), 1,
                         f"jedi_path prerequisites: {chain.prerequisites!r}")
        self.assertEqual(found[0]["village_chosen_path"], "a")

    def test_jedi_path_independent_carries_village_chosen_path_b(self):
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        found = [p for p in chain.prerequisites
                 if isinstance(p, dict) and "village_chosen_path" in p]
        self.assertEqual(len(found), 1,
                         f"jedi_path_independent prerequisites: "
                         f"{chain.prerequisites!r}")
        self.assertEqual(found[0]["village_chosen_path"], "b")


# ──────────────────────────────────────────────────────────────────────
# 2. jedi_path (Path A — Order) gating
# ──────────────────────────────────────────────────────────────────────

class TestJediPathOrderGate(unittest.TestCase):

    def test_locked_for_path_b_grad(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        is_locked, _ = is_chain_locked_for_character(
            chain, _path_b_attrs(),
        )
        self.assertTrue(
            is_locked,
            "jedi_path (Order) must be locked for Path B graduates",
        )

    def test_locked_when_only_chosen_path_missing(self):
        """All other prereqs met but village_chosen_path absent."""
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        attrs = _attrs(
            chargen_complete=True,
            force_sensitive=True,
            jedi_path_unlocked=True,
            # village_chosen_path NOT set
        )
        is_locked, reason = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)

    def test_locked_for_chosen_path_a_with_uppercase(self):
        """The check is case-tolerant — uppercase 'A' should still
        match the prereq 'a'. Defensive: village_choice.py writes
        lowercase, but a malformed chargen_notes JSON could surface
        a different shape."""
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        attrs = _attrs(
            chargen_complete=True,
            force_sensitive=True,
            jedi_path_unlocked=True,
            village_chosen_path="A",
        )
        is_locked, _ = is_chain_locked_for_character(chain, attrs)
        self.assertFalse(
            is_locked,
            "jedi_path should accept case-insensitive 'A' "
            "(normalization in is_chain_locked_for_character)",
        )

    def test_unlocked_for_path_a_grad(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        is_locked, reason = is_chain_locked_for_character(
            chain, _path_a_attrs(),
        )
        self.assertFalse(
            is_locked,
            f"jedi_path (Order) should be unlocked for Path A "
            f"graduates; got reason: {reason!r}",
        )

    def test_path_a_grad_missing_force_sensitive_still_locked(self):
        """Even with village_chosen_path == 'a', the chain stays
        locked if force_sensitive is missing. (Path A always sets
        force_sensitive in _commit_path_a, so this is a defense-
        in-depth test.)"""
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        attrs = _attrs(
            chargen_complete=True,
            force_sensitive=False,   # missing
            jedi_path_unlocked=True,
            village_chosen_path="a",
        )
        is_locked, _ = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)


# ──────────────────────────────────────────────────────────────────────
# 3. jedi_path_independent (Path B — Independent) gating
# ──────────────────────────────────────────────────────────────────────

class TestJediPathIndependentGate(unittest.TestCase):

    def test_locked_for_path_a_grad(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        is_locked, _ = is_chain_locked_for_character(
            chain, _path_a_attrs(),
        )
        self.assertTrue(
            is_locked,
            "jedi_path_independent must be locked for Path A graduates",
        )

    def test_unlocked_for_path_b_grad(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        is_locked, reason = is_chain_locked_for_character(
            chain, _path_b_attrs(),
        )
        self.assertFalse(
            is_locked,
            f"jedi_path_independent should be unlocked for Path B "
            f"graduates; got reason: {reason!r}",
        )

    def test_locked_when_only_chosen_path_missing(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        attrs = _attrs(
            chargen_complete=True,
            force_sensitive=True,
            jedi_path_unlocked=True,
            # village_chosen_path NOT set
        )
        is_locked, _ = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)


# ──────────────────────────────────────────────────────────────────────
# 4. Path C never unlocks either Jedi chain
# ──────────────────────────────────────────────────────────────────────

class TestPathCNoUnlock(unittest.TestCase):
    """Path C is the Dark Whispers branch. `_commit_path_c` does NOT
    set `jedi_path_unlocked` — the player is exiled from the Order.
    Both Jedi chains must remain locked for any Path C graduate."""

    def test_jedi_path_locked_for_path_c(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        is_locked, _ = is_chain_locked_for_character(
            chain, _path_c_attrs(),
        )
        self.assertTrue(is_locked)

    def test_jedi_path_independent_locked_for_path_c(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        is_locked, _ = is_chain_locked_for_character(
            chain, _path_c_attrs(),
        )
        self.assertTrue(is_locked)


# ──────────────────────────────────────────────────────────────────────
# 5. Both chains stay locked at chargen
# ──────────────────────────────────────────────────────────────────────

class TestChargenLockedAtCreation(unittest.TestCase):
    """At chargen, no character has set `village_chosen_path` — the
    Village quest hasn't run. Both Jedi chains must therefore stay
    locked, even if the chargen wizard's `__chargen_any__` sentinel
    is in play for `faction_intent`."""

    def test_jedi_path_locked_with_chargen_sentinel(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        attrs = {
            "chargen_complete": False,
            "faction_intent": "__chargen_any__",
        }
        is_locked, msg = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)
        # Locked-message preserved (existing UX contract)
        self.assertIn("Jedi", msg)

    def test_jedi_path_independent_locked_with_chargen_sentinel(self):
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        attrs = {
            "chargen_complete": False,
            "faction_intent": "__chargen_any__",
        }
        is_locked, msg = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(is_locked)
        self.assertIn("Jedi", msg)

    def test_chargen_any_does_not_pass_village_chosen_path(self):
        """Critical: the `__chargen_any__` sentinel applies ONLY to
        `faction_intent`. It must NOT be honored for
        `village_chosen_path`, otherwise both Jedi chains would
        appear unlocked at chargen."""
        from engine.tutorial_chains import is_chain_locked_for_character
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        attrs = _attrs(
            chargen_complete=True,
            force_sensitive=True,
            jedi_path_unlocked=True,
            faction_intent="__chargen_any__",
            village_chosen_path="__chargen_any__",  # not honored
        )
        is_locked, _ = is_chain_locked_for_character(chain, attrs)
        self.assertTrue(
            is_locked,
            "village_chosen_path must NOT honor the chargen sentinel; "
            "the Jedi paths must stay locked at chargen.",
        )

    # Note: chargen menu exclusion is exercised by
    # test_f8c1_chargen_chain_selection.py
    # (`test_render_menu_excludes_jedi_path` + the menu-count
    # assertion of 7 — F.7.j adds a second locked chain so the
    # arithmetic 9 chains - 2 locked = 7 menu entries holds).


# ──────────────────────────────────────────────────────────────────────
# 6. Chain shape — drop_room, faction_alignment, archetype_label
# ──────────────────────────────────────────────────────────────────────

class TestChainShape(unittest.TestCase):
    """Verify the F.7.j chains have the right chain-level fields.
    Path A → Coruscant Temple, jedi_order alignment, "Padawan
    (Order)" archetype. Path B → Village Common Square, independent
    alignment, "Padawan (Independent)" archetype."""

    def test_jedi_path_drop_room_is_jedi_temple(self):
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        self.assertEqual(
            chain.graduation.drop_room, "jedi_temple_main_gate",
            "Path A graduates the Order chain into the Coruscant "
            "Temple gate",
        )

    def test_jedi_path_independent_drop_room_is_village(self):
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        self.assertEqual(
            chain.graduation.drop_room, "village_common_square",
            "Path B graduates the Independent chain into the "
            "Village Common Square",
        )

    def test_jedi_path_faction_alignment_is_jedi_order(self):
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        self.assertEqual(chain.faction_alignment, "jedi_order")

    def test_jedi_path_independent_faction_alignment_is_independent(self):
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        self.assertEqual(chain.faction_alignment, "independent")

    def test_jedi_path_archetype_says_order(self):
        c = _corpus()
        chain = c.by_id()["jedi_path"]
        self.assertIn("Order", chain.archetype_label)

    def test_jedi_path_independent_archetype_says_independent(self):
        c = _corpus()
        chain = c.by_id()["jedi_path_independent"]
        self.assertIn("Independent", chain.archetype_label)

    def test_both_chains_locked(self):
        c = _corpus()
        self.assertTrue(c.by_id()["jedi_path"].locked)
        self.assertTrue(c.by_id()["jedi_path_independent"].locked)

    def test_both_chains_have_locked_message(self):
        c = _corpus()
        self.assertTrue(c.by_id()["jedi_path"].locked_message)
        self.assertTrue(c.by_id()["jedi_path_independent"].locked_message)

    def test_both_chains_share_jedi_path_unlocked_prereq(self):
        """Both chains require `jedi_path_unlocked` — the flag is
        set by Path A or Path B commit. Path C does NOT set it,
        which is how Path C is excluded from both Jedi chains."""
        c = _corpus()
        for cid in ("jedi_path", "jedi_path_independent"):
            self.assertIn(
                "jedi_path_unlocked",
                c.by_id()[cid].prerequisites,
                f"{cid} must require jedi_path_unlocked",
            )

    def test_both_chains_share_force_sensitive_prereq(self):
        c = _corpus()
        for cid in ("jedi_path", "jedi_path_independent"):
            self.assertIn(
                "force_sensitive",
                c.by_id()[cid].prerequisites,
                f"{cid} must require force_sensitive",
            )

    def test_both_chains_share_chargen_complete_prereq(self):
        c = _corpus()
        for cid in ("jedi_path", "jedi_path_independent"):
            self.assertIn(
                "chargen_complete",
                c.by_id()[cid].prerequisites,
                f"{cid} must require chargen_complete",
            )


# ──────────────────────────────────────────────────────────────────────
# 7. Source-level guards
# ──────────────────────────────────────────────────────────────────────

class TestF7JSourceMarkers(unittest.TestCase):
    """F.7.j marker present in the engine module + chains.yaml
    (so a future drop that accidentally reverts the split has a
    source-level signal of what was changed)."""

    def test_engine_module_carries_f7j_marker(self):
        from engine import tutorial_chains
        with open(tutorial_chains.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.7.j", src,
                      "engine/tutorial_chains.py must carry the F.7.j "
                      "marker in its docstring")
        self.assertIn("village_chosen_path", src,
                      "engine/tutorial_chains.py must reference the "
                      "new prereq key")

    def test_chains_yaml_carries_f7j_marker(self):
        path = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
                "tutorials" / "chains.yaml")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.7.j", src)
        self.assertIn("jedi_path_independent", src)


if __name__ == "__main__":
    unittest.main()
