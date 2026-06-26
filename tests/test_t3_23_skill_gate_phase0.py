# -*- coding: utf-8 -*-
"""tests/test_t3_23_skill_gate_phase0.py — Party skill challenges, Phase 0
seam (T3.23, 2026-06-16) — RE-VERIFIED for Phase 1 (2026-06-26).

This file originally landed the ``skill_gate`` anomaly-phase field INERT
(same pattern as T3.22 ambient-life Phase 0 — land the seam early so the
post-launch build never needs a live-data migration). T3.23 **Phase 1**
has since wired the skill-check resolution; the accessor + the structural
guards below still hold, and the advance-behavior tests now assert the
ACTIVE behavior (advancing into a skill_gate phase moves the pointer and
returns True). The full Phase-1 behavioral walk lives in
``tests/test_t3_23_party_skill_gate_phase1.py``. Existing combat-only
anomalies remain completely unaffected (no skill_gate key → old behavior).

Per docs/design/party_skill_challenges_design_v1.md §6 (non-invasive scoping):

  - ``WildernessAnomaly.phase_skill_gate(idx)`` — reader accessor for the
    T3.23 ``skill_gate`` dict in a phase; returns None if absent.
  - ``_advance_to_next_phase`` logs a T3.23-tagged info line (not a warning)
    when advancing into a skill_gate phase, moves the phase pointer, and
    returns True (the phase then awaits an investigate attempt).

Sections:
  1. TestPhaseSkillGateAccessor   — accessor returns correct dict / None
  2. TestAdvanceInertBehavior     — advancing into a skill_gate phase works
  3. TestCombatPhasesUnaffected   — phases with only combat_npcs still work
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
    """_advance_to_next_phase advancing into a skill_gate-only phase moves
    the phase pointer, returns True, and logs an info-level message (not a
    warning). A phase with neither combat_npcs nor skill_gate still warns
    and returns False."""

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

    def test_advance_into_skill_gate_phase_returns_true(self):
        # T3.23 Phase 1: advancing INTO a skill_gate phase moves the phase
        # pointer (no NPCs to spawn) and returns True — the phase then
        # waits for an investigate attempt.
        sg = {"skill": "demolitions", "difficulty": 20}
        anomaly = self._make([
            {"name": "Phase 1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Vault Door", "skill_gate": sg},
        ])
        # current_phase=0, advance should move to phase 1 (the skill gate)
        result = self._advance(anomaly)
        self.assertTrue(result)
        self.assertEqual(anomaly.current_phase, 1)
        self.assertEqual(anomaly.spawned_npc_ids, [])

    def test_skill_gate_phase_logs_info_not_warning(self):
        sg = {"skill": "persuasion", "difficulty": 18}
        anomaly = self._make([
            {"name": "P1", "combat_npcs": [{"archetype": "thug"}]},
            {"name": "Negotiation", "skill_gate": sg},
        ])
        with self.assertLogs("engine.wilderness_anomalies", level="INFO") as cm:
            result = self._advance(anomaly)
        # Phase 1: the advance succeeds (pointer moved into the gate).
        self.assertTrue(result)
        # Should log at INFO mentioning the skill_gate phase, NOT a WARNING
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
# (Former section 4 — TestInertness — was retired when T3.23 Phase 1 wired
# the skill_gate consumer. The active behavioral coverage now lives in
# tests/test_t3_23_party_skill_gate_phase1.py.)
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    unittest.main()
