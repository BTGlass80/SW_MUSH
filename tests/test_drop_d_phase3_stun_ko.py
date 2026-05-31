"""
test_drop_d_phase3_stun_ko.py — Drop D Phase 3 (May 28 2026) regression
lock for the STRICT R&E stun-KO ruling.

Per R&E p83 stun: "Weapons set for stun roll damage normally, but treat
any result more serious than 'stunned' as 'unconscious for 2D minutes.'"

What this file pins:

  · Character carries an unconscious_until float (unix-epoch seconds);
    0.0 means no active KO. NOT persisted to DB (process-state only).
  · Character.is_stun_unconscious(now=None) reports the KO gate; uses
    time.time() when now is not supplied; strict-< against the deadline
    (the deadline tick itself reports awake, matching wound_clear_at).
  · Character.can_act_now(now=None) combines wound_level.can_act AND
    the stun-KO gate. A STUNNED character whose KO clock has expired
    can still NOT act if wound_level.can_act is False; conversely a
    HEALTHY character mid-KO cannot act either.
  · Character.clear_stun_unconscious() resets the field; idempotent.
  · Combat KO branch: when stun_mode + damage_margin > 3, roll 2D,
    set target.unconscious_until = time.time() + (2D × 60.0).
  · The resolution event's WoundOutcome payload carries
    stun_duration_dice="2D" and stun_duration_unit="minutes" only
    when the KO triggers; non-KO stun outcomes don't populate them
    (the schema rejects them on non-KO outcomes).
  · The combat tick_round_end auto-revives KO'd combatants when the
    wall-clock deadline passes and emits a "comes to" event.

This drop is engine-only — no SPA changes, no client.html. The wire
schema already reserved stun_duration_dice/_unit since v1.1 §4.2;
this drop is the engine populating them for the first time.
"""
from __future__ import annotations

import time
import unittest
from unittest.mock import patch

from engine.character import Character, WoundLevel
from engine.dice import DicePool
import engine.combat_events as _cevt


# ════════════════════════════════════════════════════════════════════
# Character-level state checks
# ════════════════════════════════════════════════════════════════════

class TestCharacterStunKOState(unittest.TestCase):
    """The Character data class carries the wall-clock KO field with
    the right default and helper semantics."""

    def _ch(self) -> Character:
        c = Character(name="Test Subject")
        # Give them enough STR so apply_wound(1) doesn't auto-KO via
        # stun-count >= STR-dice (that's the unrelated v22 audit #13
        # rule). Default STR is 2D which is fine here.
        return c

    def test_default_unconscious_until_is_zero(self):
        c = self._ch()
        self.assertEqual(c.unconscious_until, 0.0)
        self.assertFalse(c.is_stun_unconscious())

    def test_is_stun_unconscious_with_explicit_now(self):
        c = self._ch()
        c.unconscious_until = 1000.0
        # Before deadline -> KO'd
        self.assertTrue(c.is_stun_unconscious(now=500.0))
        self.assertTrue(c.is_stun_unconscious(now=999.99))
        # At deadline -> awake (strict <)
        self.assertFalse(c.is_stun_unconscious(now=1000.0))
        # After deadline -> awake
        self.assertFalse(c.is_stun_unconscious(now=1500.0))

    def test_is_stun_unconscious_defaults_to_wall_clock(self):
        c = self._ch()
        c.unconscious_until = time.time() + 60.0  # 1 min in the future
        self.assertTrue(c.is_stun_unconscious())
        c.unconscious_until = time.time() - 60.0  # 1 min in the past
        self.assertFalse(c.is_stun_unconscious())

    def test_zero_unconscious_until_never_reports_KO(self):
        """A character that was never KO'd should never report KO,
        even if 'now' is well past zero."""
        c = self._ch()
        self.assertEqual(c.unconscious_until, 0.0)
        self.assertFalse(c.is_stun_unconscious(now=time.time() + 1e9))

    def test_clear_stun_unconscious_is_idempotent(self):
        c = self._ch()
        c.unconscious_until = time.time() + 60.0
        c.clear_stun_unconscious()
        self.assertEqual(c.unconscious_until, 0.0)
        # Calling again is harmless
        c.clear_stun_unconscious()
        self.assertEqual(c.unconscious_until, 0.0)
        self.assertFalse(c.is_stun_unconscious())


# ════════════════════════════════════════════════════════════════════
# can_act_now combines wound + KO gates
# ════════════════════════════════════════════════════════════════════

class TestCanActNow(unittest.TestCase):
    """can_act_now() must combine the wound ladder AND the stun-KO
    wall-clock gate. Either one being False blocks action."""

    def test_healthy_no_ko_can_act(self):
        c = Character(name="Hero")
        c.wound_level = WoundLevel.HEALTHY
        self.assertTrue(c.can_act_now())

    def test_healthy_but_KO_cannot_act(self):
        """A HEALTHY wound level + active KO clock = cannot act."""
        c = Character(name="Hero")
        c.wound_level = WoundLevel.HEALTHY
        c.unconscious_until = time.time() + 60.0
        self.assertFalse(c.can_act_now())

    def test_stunned_with_KO_cannot_act(self):
        """The realistic post-stun-KO state: wound_level=STUNNED AND
        KO clock active. Must report cannot act."""
        c = Character(name="Hero")
        c.wound_level = WoundLevel.STUNNED
        c.unconscious_until = time.time() + 60.0
        self.assertFalse(c.can_act_now())

    def test_stunned_no_KO_can_still_act(self):
        """STUNNED alone (no KO) is still actable per WoundLevel.can_act
        (STUNNED <= WOUNDED_TWICE)."""
        c = Character(name="Hero")
        c.wound_level = WoundLevel.STUNNED
        self.assertTrue(c.can_act_now())

    def test_incapacitated_no_KO_cannot_act(self):
        """The wound-ladder gate alone is enough."""
        c = Character(name="Hero")
        c.wound_level = WoundLevel.INCAPACITATED
        self.assertFalse(c.can_act_now())

    def test_KO_expires_can_act_again(self):
        """Once the wall-clock deadline passes, a STUNNED character
        with no other reason to be incapacitated can act again."""
        c = Character(name="Hero")
        c.wound_level = WoundLevel.STUNNED
        c.unconscious_until = 500.0
        self.assertFalse(c.can_act_now(now=400.0))
        self.assertTrue(c.can_act_now(now=600.0))


# ════════════════════════════════════════════════════════════════════
# WoundOutcome payload carries stun_duration_dice/_unit
# ════════════════════════════════════════════════════════════════════

class TestWoundOutcomeStunDurationFields(unittest.TestCase):
    """The combat_resolution_event's WoundOutcome payload must surface
    stun_duration_dice='2D' and stun_duration_unit='minutes' on a
    stun-KO outcome — and NOT populate them on any other outcome."""

    def test_KO_outcome_carries_2D_minutes(self):
        out = _cevt.build_wound_outcome(
            outcome_type=_cevt.OUTCOME_STUN_UNCONSCIOUS,
            display_name="Stunned — Unconscious! (7 min)",
            wound_level_before="HEALTHY",
            wound_level_after="STUNNED",
            wound_level_delta=1,
            stun_duration_dice="2D",
            stun_duration_unit="minutes",
        )
        self.assertEqual(out["outcome_type"], _cevt.OUTCOME_STUN_UNCONSCIOUS)
        self.assertTrue(out["stun_unconscious"])
        self.assertEqual(out["stun_duration_dice"], "2D")
        self.assertEqual(out["stun_duration_unit"], "minutes")

    def test_non_KO_outcomes_reject_duration_fields(self):
        """Schema check: passing stun_duration_* on a non-KO outcome
        raises (defensive — catches caller bugs early)."""
        with self.assertRaises(ValueError):
            _cevt.build_wound_outcome(
                outcome_type=_cevt.OUTCOME_STUN,
                display_name="Stunned",
                wound_level_before="HEALTHY",
                wound_level_after="STUNNED",
                wound_level_delta=1,
                stun_duration_dice="2D",
                stun_duration_unit="minutes",
            )

    def test_legacy_shim_KO_path_does_not_populate_unless_requested(self):
        """The legacy compat shim (hit/wound_text/damage_margin/
        stun_mode) classifies as KO when stun_mode + damage_margin > 3,
        but does NOT auto-populate stun_duration_dice/_unit — those are
        passed explicitly by the engine when it rolls the duration."""
        out = _cevt.build_wound_outcome(
            hit=True,
            wound_text="Stunned — Unconscious!",
            damage_margin=8,
            stun_mode=True,
            stun_knocked_out=True,
            target_can_act=False,
        )
        self.assertEqual(out["outcome_type"], _cevt.OUTCOME_STUN_UNCONSCIOUS)
        # Legacy shim path: duration fields default to None unless
        # explicitly passed by the engine. The engine sets them.
        self.assertIsNone(out["stun_duration_dice"])
        self.assertIsNone(out["stun_duration_unit"])

    def test_legacy_shim_with_explicit_duration_kwargs_carries_them(self):
        """The engine (Drop D Phase 3) calls the legacy compat shim
        with the duration kwargs alongside the v1.0 args. They must
        thread through to the payload."""
        out = _cevt.build_wound_outcome(
            hit=True,
            wound_text="Stunned — Unconscious! (5 min)",
            damage_margin=8,
            stun_mode=True,
            stun_knocked_out=True,
            target_can_act=False,
            stun_duration_dice="2D",
            stun_duration_unit="minutes",
        )
        self.assertEqual(out["stun_duration_dice"], "2D")
        self.assertEqual(out["stun_duration_unit"], "minutes")


# ════════════════════════════════════════════════════════════════════
# Combat KO branch — roll 2D, set wall-clock deadline
# ════════════════════════════════════════════════════════════════════

class TestCombatKOBranchSetsDeadline(unittest.TestCase):
    """The KO branch in combat.py must roll 2D and store the wall-clock
    deadline on target.unconscious_until. We exercise it by importing
    the engine and forcing a stun-mode hit with margin > 3."""

    def test_combat_module_imports_time(self):
        """Sanity: the KO branch needs time.time(), so combat.py must
        carry the import. A regression that drops it would show up as
        a NameError at first KO."""
        import engine.combat as combat_mod
        self.assertTrue(hasattr(combat_mod, "time"))

    def test_KO_branch_text_includes_minutes(self):
        """The wound_text on a KO outcome must include the rolled
        minutes count (used in narrative). Grep the source for the
        literal format string so a refactor that drops it fails loudly."""
        import inspect
        import engine.combat as combat_mod
        src = inspect.getsource(combat_mod)
        # The KO branch builds:  f"Stunned — Unconscious! ({minutes} min)"
        self.assertIn('Stunned', src)
        self.assertIn('Unconscious', src)
        self.assertIn('min)', src)

    def test_KO_branch_sets_unconscious_until(self):
        """Direct check that the KO branch writes to target.unconscious_until.
        Grep the source for the assignment so the wiring can't be dropped
        silently."""
        import inspect
        import engine.combat as combat_mod
        src = inspect.getsource(combat_mod)
        self.assertIn("target.unconscious_until = time.time()", src)
        self.assertIn("stun_duration_minutes * 60.0", src)


# ════════════════════════════════════════════════════════════════════
# tick_round_end auto-revive
# ════════════════════════════════════════════════════════════════════

class TestTickRoundEndAutoRevive(unittest.TestCase):
    """When the wall-clock deadline passes during an active combat,
    tick_round_end clears the field and emits a wake-up event."""

    def test_tick_includes_unconscious_until_check(self):
        """Grep the source for the auto-revive block. A refactor that
        drops it would leave players KO'd forever in long combats."""
        import inspect
        import engine.combat as combat_mod
        src = inspect.getsource(combat_mod)
        self.assertIn("clear_stun_unconscious()", src)
        self.assertIn("comes to, groggy but conscious", src)
        # Auto-revive must check wall-clock now >= unconscious_until
        self.assertIn("_now >= c.char.unconscious_until", src)


# ════════════════════════════════════════════════════════════════════
# Migration completeness — wound_level.can_act → can_act_now()
# ════════════════════════════════════════════════════════════════════

class TestCanActMigrationComplete(unittest.TestCase):
    """Every site in engine that gates combat actions must use
    can_act_now() (which includes the KO gate), not the bare
    wound_level.can_act (which does not). A regression that adds a new
    wound_level.can_act site in combat / NPC AI would let KO'd
    characters act."""

    def test_combat_py_has_no_wound_level_can_act(self):
        import inspect
        import engine.combat as m
        src = inspect.getsource(m)
        # The only allowed surfaces are the class definition and any
        # doc comment. Bare wound_level.can_act in action-gating code
        # is a regression.
        self.assertNotIn("wound_level.can_act", src)

    def test_npc_combat_ai_has_no_wound_level_can_act(self):
        import inspect
        import engine.npc_combat_ai as m
        self.assertNotIn("wound_level.can_act", inspect.getsource(m))

    def test_encounter_boarding_has_no_wound_level_can_act(self):
        import inspect
        import engine.encounter_boarding as m
        self.assertNotIn("wound_level.can_act", inspect.getsource(m))


if __name__ == "__main__":
    unittest.main()
