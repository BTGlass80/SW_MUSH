# -*- coding: utf-8 -*-
"""
tests/test_anomaly_social_alt_skills_2026_07_02.py

Pins the deferred follow-up from HANDOFF_events_playable_fix_tune_2026-07-02
§"Deferred quick follow-ups" #1: the 3 staged-cult skill stages
(hollow_sun_cistern_slice / ember_court_relay_slice / ashen_hand_informant_turn)
ADVERTISE a "turn the farmers / rally the laborers / buy back the informants"
social route in their long_desc + the staged_event stage `skills[]` pool, but
`_resolve_anomaly_skill` only ever rolled primary_skill/secondary_skill — so a
face character was told they could resolve the stage, then got rolled on a slicer
skill they had 0D in.

Fix under test:
  * each of the 3 templates gains an `alt_skills` list.
  * `_resolve_anomaly_skill` now rolls the first of primary → secondary →
    alt_skills the character has trained (reusing the tested `_pick_best_of_skills`
    role-substitution helper — NOT dice min-maxing).
  * Backward-compat: a template with no `alt_skills` behaves byte-identically to
    the old two-skill `_pick_better_skill` path.

Cross-surface invariant: every skill the staged_event stage advertises must be
rollable by the anomaly template it maps to (advertised ⊆ rollable).
"""
from __future__ import annotations

import sys
import time
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Reuse the SYN.7.a in-memory harness (both pytest collection modes).
try:
    from tests.test_syn7a_wilderness_anomalies import (
        _run, _MiniDB, _make_char, _AnomalyTestCase,
    )
except ImportError:  # rootdir-insertion collection
    from test_syn7a_wilderness_anomalies import (  # type: ignore
        _run, _MiniDB, _make_char, _AnomalyTestCase,
    )


class TestAnomalySocialAltSkills(_AnomalyTestCase):
    """Integration: drive the REAL resolve_anomaly → _resolve_anomaly_skill
    path and assert which skill the resolver chose."""

    def _setup(self, *, template_key, skills, faction_id="independent"):
        from engine.wilderness_anomalies import _anomalies, WildernessAnomaly
        mdb = _MiniDB()
        mdb.seed_zone(zone_id=1)
        mdb.seed_room(room_id=10, zone_id=1, wilderness_region_id="r1")
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug="r1", zone_id=1,
            template_key=template_key,
            anchor_room_id=10,
            expiry=now + 600,
        )
        _anomalies["r1"] = [a]
        char = _make_char(char_id=1, room_id=10, faction_id=faction_id,
                          skills=skills)
        # Seed the char row so the ledger chokepoint has a row to update
        # (mirrors TestResolveAnomalySuccess._setup_with_anomaly).
        mdb._db._conn.execute(
            "INSERT INTO characters (id, credits, faction_id) VALUES (?, ?, ?)",
            (char["id"], char.get("credits", 0), faction_id))
        return mdb, char, a

    def test_social_char_resolves_hollow_sun_via_persuasion(self):
        """A face with only persuasion (no slicer skills) rolls the
        advertised social route, not a 0D security check."""
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup(
            template_key="hollow_sun_cistern_slice",
            skills={"persuasion": "5D"})
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["skill_used"], "persuasion")

    def test_slicer_still_uses_primary_security(self):
        """Backward-compat: a character trained in the primary skill still
        rolls it — alt_skills is a fallback, not a min-max override."""
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup(
            template_key="hollow_sun_cistern_slice",
            skills={"security": "5D", "persuasion": "5D"})
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["skill_used"], "security")

    def test_ashen_hand_slicer_uses_alt_security(self):
        """ashen_hand primary/secondary are persuasion/investigation; a
        char with only the alt 'security' still resolves the stage."""
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup(
            template_key="ashen_hand_informant_turn",
            skills={"security": "5D"})
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["skill_used"], "security")

    def test_untrained_char_falls_back_to_primary(self):
        """No trained candidate → fall back to primary (candidates[0]),
        exactly as the pre-fix path did."""
        from engine.wilderness_anomalies import resolve_anomaly
        mdb, char, a = self._setup(
            template_key="hollow_sun_cistern_slice",
            skills={})
        out = _run(resolve_anomaly(mdb, char, 1))
        self.assertTrue(out["ok"])
        self.assertEqual(out["skill_used"], "security")


class TestAltSkillsHelperBackCompat(unittest.TestCase):
    """Pure: adding alt_skills to the resolver must not change behavior for
    a two-skill template (no alt_skills present)."""

    def test_pick_best_of_skills_matches_pick_better_skill(self):
        from engine.wilderness_anomalies import (
            _pick_best_of_skills, _pick_better_skill,
        )
        import json as _json
        cases = [
            {"medicine": "5D"},               # primary trained
            {"survival": "5D"},               # secondary trained
            {"medicine": "5D", "survival": "5D"},  # both trained
            {},                                # neither trained
            {"blaster": "5D"},                # unrelated skill trained
        ]
        for sk in cases:
            char = {"skills": _json.dumps(sk)}
            self.assertEqual(
                _pick_best_of_skills(char, ["medicine", "survival"]),
                _pick_better_skill(char, "medicine", "survival"),
                f"divergence for skills={sk}",
            )


class TestStagedSkillStagesRollable(unittest.TestCase):
    """Cross-surface invariant: every skill a staged-cult skill stage
    ADVERTISES (staged_event stage `skills[]`) must actually be rollable by
    the anomaly template it maps to (primary ∪ secondary ∪ alt_skills).

    This is the contract the drop enforces — it fails if a future edit adds
    an advertised skill without making it rollable (or renames a template)."""

    def test_advertised_skills_are_rollable(self):
        from engine.staged_event import STAGED_CULTS, KIND_SKILL
        from engine.wilderness_anomalies import SCENARIO_TEMPLATES
        checked = 0
        for cult_key, stages in STAGED_CULTS.items():
            for stage in stages:
                if stage.get("kind") != KIND_SKILL:
                    continue
                tmpl_key = stage["anomaly_template"]
                tmpl = SCENARIO_TEMPLATES.get(tmpl_key)
                self.assertIsNotNone(
                    tmpl, f"{cult_key} skill stage maps to unknown template "
                          f"{tmpl_key!r}")
                self.assertEqual(
                    tmpl.get("resolution"), "skill",
                    f"{tmpl_key} is not a resolution:'skill' template")
                rollable = {tmpl.get("primary_skill"), tmpl.get("secondary_skill")}
                rollable |= set(tmpl.get("alt_skills") or [])
                rollable.discard(None)
                advertised = set(stage.get("skills") or [])
                missing = advertised - rollable
                self.assertEqual(
                    missing, set(),
                    f"{cult_key}/{stage.get('key')} advertises skills that "
                    f"{tmpl_key} cannot roll: {sorted(missing)}")
                checked += 1
        # All 3 staged cults have exactly one KIND_SKILL stage today.
        self.assertEqual(checked, 3,
                         f"expected 3 staged skill stages, checked {checked}")


if __name__ == "__main__":
    unittest.main()
