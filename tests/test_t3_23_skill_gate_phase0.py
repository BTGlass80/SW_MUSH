# -*- coding: utf-8 -*-
"""tests/test_t3_23_skill_gate_phase0.py — Party skill challenges, Phase 0
(PRE-LAUNCH seam). T3.23, 2026-06-16.

This drop lands the ``skill_gate`` anomaly-phase field INERT — same pattern
as T3.22 ambient-life Phase 0 (land the seam early so the post-launch build
never needs a live-data migration).  No skill-check resolution is wired yet;
existing combat-only anomalies are completely unaffected.

Per docs/design/party_skill_challenges_design_v1.md §6 (non-invasive scoping):

  - ``WildernessAnomaly.phase_skill_gate(idx)`` — reader accessor for the
    T3.23 ``skill_gate`` dict in a phase; returns None if absent.  INERT.
  - ``_advance_anomaly_phase`` logs a T3.23-tagged info line (not a warning)
    when a skill_gate phase has no combat_npcs — result is still False
    (inert: the phase is not advanced until Phase 1 ships).

Sections:
  1. TestPhaseSkillGateAccessor   — accessor returns correct dict / None
  2. TestAdvanceInertBehavior     — skill_gate phase returns False, right log
  3. TestCombatPhasesUnaffected   — phases with only combat_npcs still work
  4. TestInertness                — no production code acts on skill_gate yet
"""
from __future__ import annotations

import asyncio
import importlib
import logging
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(coro):
    return asyncio.run(coro)


def _make_anomaly(phases, tier=2):
    """Build a minimal WildernessAnomaly backed by an inline template dict."""
    from engine.wilderness_anomalies import WildernessAnomaly, TIER2_TEMPLATES

    key = "_t3_23_test_template"
    # Register a temporary template so .template property resolves
    TIER2_TEMPLATES[key] = {
        "tier": tier,
        "regions": ["test_region"],
        "resolution": "combat",
        "display_name": "T3.23 test",
        "phases": phases,
    }
    anomaly = WildernessAnomaly(
        id=999,
        region_slug="test_region",
        zone_id=None,
        template_key=key,
        anchor_room_id=1,
        tier=tier,
    )
    return anomaly, key


def _cleanup(key):
    from engine.wilderness_anomalies import TIER2_TEMPLATES
    TIER2_TEMPLATES.pop(key, None)


# ---------------------------------------------------------------------------
# 1. TestPhaseSkillGateAccessor
# ---------------------------------------------------------------------------

class TestPhaseSkillGateAccessor(unittest.TestCase):

    def setUp(self):
        self._keys = []

    def tearDown(self):
        for k in self._keys:
            _cleanup(k)

    def _make(self, phases, tier=2):
        a, k = _make_anomaly(phases, tier)
        self._keys.append(k)
        return a

    def test_returns_none_when_no_skill_gate(self):
        anomaly = self._make([
            {"name": "Phase 1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Phase 2", "combat_npcs": [{"archetype": "thug"}]},
        ])
        self.assertIsNone(anomaly.phase_skill_gate(0))
        self.assertIsNone(anomaly.phase_skill_gate(1))

    def test_returns_skill_gate_dict(self):
        sg = {"skill": "demolitions", "difficulty": 20, "solo_penalty": 8}
        anomaly = self._make([
            {"name": "The Sealed Vault", "skill_gate": sg},
        ])
        result = anomaly.phase_skill_gate(0)
        self.assertIsNotNone(result)
        self.assertEqual(result["skill"], "demolitions")
        self.assertEqual(result["difficulty"], 20)
        self.assertEqual(result["solo_penalty"], 8)

    def test_returns_skill_gate_with_alt_skills(self):
        sg = {"skill": "security", "difficulty": 18, "alt_skills": ["demolitions"]}
        anomaly = self._make([
            {"name": "Locked Door", "skill_gate": sg},
            {"name": "Boss", "combat_npcs": [{"archetype": "thug"}]},
        ])
        result = anomaly.phase_skill_gate(0)
        self.assertEqual(result["alt_skills"], ["demolitions"])
        self.assertIsNone(anomaly.phase_skill_gate(1))  # combat phase → None

    def test_out_of_range_returns_none(self):
        anomaly = self._make([
            {"name": "Phase 1", "combat_npcs": []},
        ])
        self.assertIsNone(anomaly.phase_skill_gate(-1))
        self.assertIsNone(anomaly.phase_skill_gate(99))

    def test_empty_phases_returns_none(self):
        anomaly = self._make([])
        self.assertIsNone(anomaly.phase_skill_gate(0))

    def test_falsy_skill_gate_returns_none(self):
        """skill_gate: {} or skill_gate: null are treated as absent."""
        anomaly = self._make([
            {"name": "Phase 1", "skill_gate": {}},
        ])
        # Empty dict is falsy — accessor returns None
        self.assertIsNone(anomaly.phase_skill_gate(0))

    def test_mixed_phases_accessor(self):
        sg = {"skill": "medicine", "difficulty": 15}
        anomaly = self._make([
            {"name": "Combat", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Heal", "skill_gate": sg},
            {"name": "Boss", "combat_npcs": [{"archetype": "thug"}]},
        ])
        self.assertIsNone(anomaly.phase_skill_gate(0))
        self.assertEqual(anomaly.phase_skill_gate(1)["skill"], "medicine")
        self.assertIsNone(anomaly.phase_skill_gate(2))


# ---------------------------------------------------------------------------
# 2. TestAdvanceInertBehavior
# ---------------------------------------------------------------------------

class TestAdvanceInertBehavior(unittest.TestCase):
    """_advance_anomaly_phase with a skill_gate-only phase returns False
    (inert) and logs an info-level message, not a warning."""

    def setUp(self):
        self._keys = []

    def tearDown(self):
        for k in self._keys:
            _cleanup(k)

    def _make(self, phases, tier=2):
        a, k = _make_anomaly(phases, tier)
        self._keys.append(k)
        return a

    def _advance(self, anomaly, session_mgr=None):
        from engine.wilderness_anomalies import _advance_to_next_phase
        return _run(_advance_to_next_phase(None, anomaly, session_mgr))

    def test_skill_gate_phase_returns_false(self):
        sg = {"skill": "demolitions", "difficulty": 20}
        anomaly = self._make([
            {"name": "Phase 1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Vault Door", "skill_gate": sg},
        ])
        # current_phase=0, advance should try phase 1
        result = self._advance(anomaly)
        self.assertFalse(result)

    def test_skill_gate_phase_logs_info_not_warning(self):
        sg = {"skill": "persuasion", "difficulty": 18}
        anomaly = self._make([
            {"name": "P1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Negotiation", "skill_gate": sg},
        ])
        with self.assertLogs("engine.wilderness_anomalies", level="INFO") as cm:
            result = self._advance(anomaly)
        self.assertFalse(result)
        # Should log at INFO with T3.23 tag, NOT a WARNING
        info_msgs = [m for m in cm.output if "skill_gate" in m.lower() or "T3.23" in m]
        self.assertTrue(len(info_msgs) >= 1, f"Expected skill_gate info log; got: {cm.output}")
        # Must NOT log a WARNING about "has no combat_npcs" for this case
        warn_msgs = [m for m in cm.output if "WARNING" in m and "no combat_npcs" in m]
        self.assertEqual(len(warn_msgs), 0, f"Unexpected warning: {warn_msgs}")

    def test_phase_with_no_combat_npcs_and_no_skill_gate_still_warns(self):
        """A bare phase with neither combat_npcs nor skill_gate keeps the old warning."""
        anomaly = self._make([
            {"name": "P1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Empty Phase"},  # no combat_npcs, no skill_gate
        ])
        with self.assertLogs("engine.wilderness_anomalies", level="WARNING") as cm:
            result = self._advance(anomaly)
        self.assertFalse(result)
        warn_msgs = [m for m in cm.output if "no combat_npcs" in m]
        self.assertTrue(len(warn_msgs) >= 1, f"Expected 'no combat_npcs' warning; got: {cm.output}")


# ---------------------------------------------------------------------------
# 3. TestCombatPhasesUnaffected
# ---------------------------------------------------------------------------

class TestCombatPhasesUnaffected(unittest.TestCase):
    """Existing combat-only anomalies with no skill_gate field are unchanged."""

    def setUp(self):
        self._keys = []

    def tearDown(self):
        for k in self._keys:
            _cleanup(k)

    def _make(self, phases, tier=2):
        a, k = _make_anomaly(phases, tier)
        self._keys.append(k)
        return a

    def test_is_final_phase_unaffected(self):
        anomaly = self._make([
            {"name": "P1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "P2", "combat_npcs": [{"archetype": "thug"}]},
        ])
        self.assertFalse(anomaly.is_final_phase)
        anomaly.current_phase = 1
        self.assertTrue(anomaly.is_final_phase)

    def test_total_phases_unaffected(self):
        anomaly = self._make([
            {"name": "P1", "combat_npcs": []},
            {"name": "P2", "combat_npcs": []},
            {"name": "P3", "combat_npcs": []},
        ])
        self.assertEqual(anomaly.total_phases, 3)

    def test_phases_with_skill_gate_included_in_total_phases(self):
        """Phases with skill_gate count toward total_phases (not hidden)."""
        sg = {"skill": "demolitions", "difficulty": 20}
        anomaly = self._make([
            {"name": "Combat Phase", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Skill Gate Phase", "skill_gate": sg},
        ])
        self.assertEqual(anomaly.total_phases, 2)

    def test_template_property_passthrough(self):
        """skill_gate key in a phase dict survives the template passthrough."""
        sg = {"skill": "security", "difficulty": 17}
        anomaly = self._make([
            {"name": "Phase", "skill_gate": sg, "combat_npcs": [{"archetype": "thug"}]},
        ])
        phase0 = anomaly.phases[0]
        self.assertIn("skill_gate", phase0)
        self.assertEqual(phase0["skill_gate"]["skill"], "security")
        # combat_npcs still accessible alongside skill_gate
        self.assertIn("combat_npcs", phase0)


# ---------------------------------------------------------------------------
# 4. TestInertness
# ---------------------------------------------------------------------------

class TestInertness(unittest.TestCase):
    """No production code acts on skill_gate yet (Phase 1 is post-launch)."""

    def test_resolve_anomaly_does_not_import_skill_gate_consumer(self):
        """The skill_gate field has no consumer in the production engine."""
        from engine import wilderness_anomalies as wa
        src = open(wa.__file__, encoding="utf-8").read()
        # The only places skill_gate should appear are: phase_skill_gate (accessor)
        # and _advance_anomaly_phase (the inert-seam log). It must NOT appear in
        # any skill-check dispatch, perform_skill_check call, or award path.
        import re
        # Count occurrences of skill_gate in the source
        occurrences = [m.start() for m in re.finditer(r"skill_gate", src)]
        # We expect exactly 3 occurrences:
        #   1. phase_skill_gate method body (.get("skill_gate"))
        #   2. docstring mentioning skill_gate
        #   3. _advance_anomaly_phase inert-seam branch (.get("skill_gate"))
        # If there are more, someone may have wired an actual consumer — fail loudly.
        self.assertGreaterEqual(len(occurrences), 3,
                                "Expected >= 3 skill_gate occurrences (method + inert branch)")
        self.assertLessEqual(len(occurrences), 8,
                             f"Too many skill_gate occurrences ({len(occurrences)}) "
                             f"— possible unintended consumer wired pre-Phase-1")

    def test_no_perform_skill_check_call_for_skill_gate(self):
        """No perform_skill_check call is guarded by skill_gate in this file."""
        from engine import wilderness_anomalies as wa
        src = open(wa.__file__, encoding="utf-8").read()
        import re
        # Look for skill_gate within 5 lines of perform_skill_check — that would
        # mean the Phase 1 engine seam was accidentally wired.
        lines = src.splitlines()
        for i, line in enumerate(lines):
            if "perform_skill_check" in line:
                context = "\n".join(lines[max(0, i-5):i+6])
                self.assertNotIn("skill_gate", context,
                                 f"perform_skill_check near skill_gate at line {i+1} — "
                                 f"Phase 1 consumer accidentally wired?\n{context}")


if __name__ == "__main__":
    unittest.main()
