# -*- coding: utf-8 -*-
"""tests/test_guide_early_combat_cp_reverify.py

GUIDES re-verify lane (2026-06-25): the FUN2 early-combat CP faucet
(`a281e5a`, `engine/combat_cp.py`) added a brand-new way combat touches a
character's CP total — the first N NPC kills a character ever lands each grant
+1 CP (lifetime-sealed, tunable ``combat.early_cp_kill_cap``, default 5).

Two guides made test-invisible claims that this drop contradicts:

* **Guide_03 §12** asserted hunting "structurally cannot touch your character's
  progression" — now false: the first few kills DO award CP. (The narrower,
  still-true claims — the credit/prestige *trickle* pays "zero Character Points"
  and "can *never* buy skill growth" — are preserved; only the over-broad
  progression claim is corrected, plus the exception is now documented.)
* **Guide_09 §6** (Milestone CP Bonuses — "how you earn CP") never listed the
  early-combat faucet at all.

These tests pin both guides' early-combat documentation against the LIVE
mechanic (the engine default cap + the tunable), so a future change to the
faucet forces a guide update, and so the corrected prose can't silently rot
back to the old contradiction.
"""
from __future__ import annotations

import os
import unittest

GUIDES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "data", "guides",
)


def _read(name: str) -> str:
    with open(os.path.join(GUIDES_DIR, name), encoding="utf-8") as fh:
        return fh.read()


class TestEarlyCombatCpEngineContract(unittest.TestCase):
    """The guides describe a default of five kills — that must match the live
    engine default and the tunables.yaml value, or the prose is wrong."""

    def test_engine_default_cap_is_five(self) -> None:
        from engine.combat_cp import _DEFAULT_KILL_CAP

        self.assertEqual(
            _DEFAULT_KILL_CAP, 5,
            "Early-combat CP default cap changed; update Guide_03 §12 and "
            "Guide_09 §6 ('default five'/'default 5') to match.",
        )

    def test_tunable_default_resolves_to_engine_default(self) -> None:
        from engine.combat_cp import _DEFAULT_KILL_CAP
        from engine.tunables import get_tunable

        # In the default config (tunables.yaml ships combat.early_cp_kill_cap: 5)
        # the resolved tunable must equal the engine default the guides cite.
        self.assertEqual(
            int(get_tunable("combat.early_cp_kill_cap", _DEFAULT_KILL_CAP)),
            _DEFAULT_KILL_CAP,
        )


class TestGuide03EarlyCpExceptionDocumented(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _read("Guide_03_Ground_Combat.md")

    def test_preserves_trickle_zero_cp_claims(self) -> None:
        """The narrower, still-true claims about the credit/prestige trickle
        must survive — the existing guide-03 authoritative test pins these."""
        self.assertIn("zero Character Points", self.text)
        self.assertIn("can *never* buy skill growth", self.text)

    def test_drops_false_progression_overclaim(self) -> None:
        """The over-broad 'cannot touch your character's progression' claim is
        now false (early-combat CP does touch it) and must be gone."""
        self.assertNotIn(
            "structurally cannot touch your character's progression",
            self.text,
        )

    def test_documents_early_cp_exception(self) -> None:
        # Names the faucet's tunable + describes the one-time first-blood grant.
        self.assertIn("combat.early_cp_kill_cap", self.text)
        self.assertIn("first blood", self.text.lower())
        self.assertIn("+1 CP", self.text)
        # Cross-links the authoritative description in CP Progression.
        self.assertIn("cp-progression", self.text.lower())


class TestGuide09EarlyCpFaucetDocumented(unittest.TestCase):
    def setUp(self) -> None:
        self.text = _read("Guide_09_CP_Progression.md")

    def test_lists_early_combat_faucet(self) -> None:
        self.assertIn("combat.early_cp_kill_cap", self.text)
        self.assertIn("first blood", self.text.lower())
        self.assertIn("+1 CP", self.text)

    def test_describes_lifetime_seal_and_outside_tick_cap(self) -> None:
        lowered = self.text.lower()
        self.assertIn("lifetime-sealed", lowered)
        # It is a direct CP grant, not a tick source — must be framed as
        # outside the weekly tick cap (the §6 milestone-bonus contract).
        self.assertIn("outside the weekly tick cap", lowered)

    def test_does_not_inflate_tick_source_count(self) -> None:
        """The faucet is a §6 milestone-style grant, NOT a 4th tick source —
        §2 must still say 'Three income sources' (pinned by the authoritative
        test); guard against a careless edit that reframes it as a tick feed."""
        self.assertIn("Three income sources feed the tick pool", self.text)
        self.assertNotIn("Four income sources", self.text)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
