# -*- coding: utf-8 -*-
"""
tests/test_b1f_rewicker_boundary.py — B.1.f (rewicker boundary fixes) tests.

Per architecture v38 §19.7 and `b1_audit_v1.md` §3, B.1.f closes the
final B.1 sub-drop: the small set of code-flow sites where a faction
literal is compared or used as a dictionary key. The audit's initial
scope listed four files but verification (Apr 29) pared it to two
real code-flow sites:

  1. `engine/espionage.py::_FACTION_FINDINGS` — keyed by faction
     code; CW orgs (republic, cis, jedi_order, hutt_cartel,
     bounty_hunters_guild) had no entry, so a CW PC investigating
     a CW-claimed room saw only the generic finding. Now extended
     with era-themed clues for all five CW orgs.

  2. `engine/organizations.py::promote_character` rank-1 specialization
     gate — pre-drop a hardcoded `org_code == "empire"` literal.
     Post-drop uses `faction_has_specialization(org_code)` so the
     rank-1 spec re-prompt fires for any spec-eligible faction
     (Empire in GCW, Republic in CW). The B.1.b.2 work landed
     `REPUBLIC_SPEC_EQUIPMENT` and `_SPEC_CONFIG_BY_FACTION` so
     `faction_has_specialization("republic")` already returns True
     in the post-B.1.b tree.

The two sites the audit also called out are verified era-clean and
need no change:

  - `engine/security.py::_apply_director_overlay` reads `zs.imperial`
    which is a Director **axis name** (era-stable per B.1.c
    `ORG_TO_AXIS`); both `empire` (GCW) and `republic` (CW) map
    onto the `imperial` axis. Module-level docstring mentions
    "Imperial crackdown" but that text is dev-facing, not user-
    facing.

  - `server/session.py::_hud_alert_level` builds
    `factions = {"imperial": ..., "rebel": ..., "criminal": ...,
    "independent": ...}` using the same Director axis names.
    The HUD `alert_faction` field is plumbing for a future web HUD
    consumer; no display surface reads it yet, and when one ships
    it should rewicker at render time, not at the routing-key layer.

GCW byte-equivalence is preserved by both fixes by construction.
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


# ──────────────────────────────────────────────────────────────────────
# 1. Espionage faction findings — CW orgs now produce themed clues
# ──────────────────────────────────────────────────────────────────────

class TestEspionageFactionFindingsKeysExtended(unittest.TestCase):
    """All five CW orgs now have entries in _FACTION_FINDINGS."""

    def test_republic_findings_present(self):
        from engine.espionage import _FACTION_FINDINGS
        self.assertIn("republic", _FACTION_FINDINGS)
        self.assertGreater(len(_FACTION_FINDINGS["republic"]), 0)

    def test_cis_findings_present(self):
        from engine.espionage import _FACTION_FINDINGS
        self.assertIn("cis", _FACTION_FINDINGS)
        self.assertGreater(len(_FACTION_FINDINGS["cis"]), 0)

    def test_jedi_order_findings_present(self):
        from engine.espionage import _FACTION_FINDINGS
        self.assertIn("jedi_order", _FACTION_FINDINGS)
        self.assertGreater(len(_FACTION_FINDINGS["jedi_order"]), 0)

    def test_hutt_cartel_findings_present(self):
        from engine.espionage import _FACTION_FINDINGS
        self.assertIn("hutt_cartel", _FACTION_FINDINGS)
        self.assertGreater(len(_FACTION_FINDINGS["hutt_cartel"]), 0)

    def test_bounty_hunters_guild_findings_present(self):
        from engine.espionage import _FACTION_FINDINGS
        self.assertIn("bounty_hunters_guild", _FACTION_FINDINGS)
        self.assertGreater(len(_FACTION_FINDINGS["bounty_hunters_guild"]), 0)


class TestEspionageFactionFindingsCWThemed(unittest.TestCase):
    """CW pools mention era-appropriate flavor (Republic / Separatist /
    Jedi / Cartel / Guild) and avoid GCW-only references like Empire,
    ISB, or Alliance."""

    def test_republic_pool_mentions_republic_or_clone(self):
        from engine.espionage import _FACTION_FINDINGS
        joined = " ".join(_FACTION_FINDINGS["republic"]).lower()
        self.assertTrue(
            "republic" in joined or "clone" in joined or "phase" in joined,
            f"Republic pool should mention Republic/clone/Phase: {joined!r}",
        )

    def test_cis_pool_mentions_separatist_or_droid(self):
        from engine.espionage import _FACTION_FINDINGS
        joined = " ".join(_FACTION_FINDINGS["cis"]).lower()
        self.assertTrue(
            "separatist" in joined or "droid" in joined or "confederacy" in joined,
            f"CIS pool should mention Separatist/droid/Confederacy: {joined!r}",
        )

    def test_jedi_order_pool_mentions_jedi_or_saber(self):
        from engine.espionage import _FACTION_FINDINGS
        joined = " ".join(_FACTION_FINDINGS["jedi_order"]).lower()
        self.assertTrue(
            "jedi" in joined or "saber" in joined or "meditation" in joined,
            f"Jedi pool should mention Jedi/saber/meditation: {joined!r}",
        )

    def test_cw_pools_avoid_gcw_only_terms(self):
        """CW pools should not name Empire / ISB / Alliance / Stormtrooper."""
        from engine.espionage import _FACTION_FINDINGS
        gcw_terms = ["empire", "imperial", "isb", "alliance", "stormtrooper",
                     "rebel"]
        for cw_org in ["republic", "cis", "jedi_order"]:
            joined = " ".join(_FACTION_FINDINGS[cw_org]).lower()
            for term in gcw_terms:
                self.assertNotIn(
                    term, joined,
                    f"{cw_org} pool leaks GCW term {term!r}: {joined!r}",
                )


class TestEspionageFindingsLookupBehavior(unittest.IsolatedAsyncioTestCase):
    """The lookup site (line ~242) is era-agnostic dict access; verify
    a CW claim now produces a faction-themed finding."""

    async def test_cw_claim_produces_themed_finding_at_margin_3(self):
        """A CW Republic claim should produce a Republic-themed finding."""
        from engine import espionage

        room = {"id": 100}
        char = {"id": 1, "name": "Tester", "faction_id": "republic"}

        # Mock get_claim to return a Republic claim
        async def fake_get_claim(db, room_id):
            return {"org_code": "republic"}

        # Force deterministic random
        with patch.object(espionage.random, "choice",
                          side_effect=lambda lst: lst[0]):
            with patch("engine.territory.get_claim",
                       side_effect=fake_get_claim):
                # Mock db so the recent-visitors block at margin >= 7
                # doesn't crash; we're testing margin=3.
                db = MagicMock()
                db.fetchall = AsyncMock(return_value=[])
                findings = await espionage.generate_investigation_findings(
                    db, char, room, margin=3,
                )

        # Should include the first Republic finding
        republic_pool = espionage._FACTION_FINDINGS["republic"]
        self.assertTrue(
            any(rep in findings for rep in republic_pool),
            f"No Republic finding emitted: {findings!r}",
        )

    async def test_retired_gcw_org_code_produces_no_faction_finding(self):
        """A retired GCW org_code (empire) is no longer in _FACTION_FINDINGS;
        the era-agnostic .get(org, []) lookup yields no faction-themed finding."""
        from engine import espionage

        self.assertNotIn("empire", espionage._FACTION_FINDINGS)

        room = {"id": 100}
        char = {"id": 1, "name": "Tester", "faction_id": "empire"}

        async def fake_get_claim(db, room_id):
            return {"org_code": "empire"}

        with patch.object(espionage.random, "choice",
                          side_effect=lambda lst: lst[0]):
            with patch("engine.territory.get_claim",
                       side_effect=fake_get_claim):
                db = MagicMock()
                db.fetchall = AsyncMock(return_value=[])
                # Must not raise; empire simply has no themed pool now.
                findings = await espionage.generate_investigation_findings(
                    db, char, room, margin=3,
                )
        self.assertIsInstance(findings, list)


# ──────────────────────────────────────────────────────────────────────
# 2. Organizations rank-1 specialization gate — generalized
# ──────────────────────────────────────────────────────────────────────

class TestSpecializationGateRefactor(unittest.TestCase):
    """Source-level inspection that the hardcoded `org_code == "empire"`
    literal in the rank-1 spec gate is gone, replaced with the
    faction_has_specialization helper."""

    def _read_organizations_source(self):
        import engine.organizations as org_module
        path = org_module.__file__
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()

    def test_hardcoded_empire_specialization_literal_removed(self):
        """The pre-drop `org_code != "empire"` literal in promote_character
        should no longer appear in the spec gate."""
        src = self._read_organizations_source()
        # The exact pre-drop strings:
        pre_drop_neg = 'org_code != "empire"'
        pre_drop_pos_with_comment = 'org_code == "empire" and next_level == 1'
        self.assertNotIn(
            pre_drop_neg, src,
            f"Hardcoded {pre_drop_neg!r} still present in organizations.py",
        )
        self.assertNotIn(
            pre_drop_pos_with_comment, src,
            f"Hardcoded {pre_drop_pos_with_comment!r} still present",
        )

    def test_faction_has_specialization_used_in_spec_gate(self):
        """The new helper-driven gate should be present."""
        src = self._read_organizations_source()
        # The post-drop call shape:
        self.assertIn(
            "faction_has_specialization(org_code)", src,
            "faction_has_specialization(org_code) should drive spec gate",
        )

    def test_b1f_anchor_comment_present(self):
        """The B.1.f drop anchor comment should be present for traceability."""
        src = self._read_organizations_source()
        self.assertIn("B.1.f", src,
                      "B.1.f anchor comment should be present in organizations.py")


class TestSpecializationGateBehavior(unittest.TestCase):
    """faction_has_specialization() returns the right answers for the
    factions that drive the rank-1 gate."""

    def test_empire_no_specialization_post_retirement(self):
        """GCW Empire no longer has a specialization flow (retired)."""
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("empire"))

    def test_republic_has_specialization(self):
        """CW Republic has specialization (B.1.b.2 added this)."""
        from engine.organizations import faction_has_specialization
        self.assertTrue(faction_has_specialization("republic"))

    def test_rebel_no_specialization(self):
        """Rebel: rank-up issues normal equipment, no spec gate."""
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("rebel"))

    def test_hutt_no_specialization(self):
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("hutt"))

    def test_cis_no_specialization(self):
        """CIS: rank-up issues normal equipment, no spec gate (per B.1.b.2)."""
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("cis"))

    def test_jedi_order_no_specialization(self):
        """Jedi Order: rank-up issues normal equipment, no spec gate."""
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("jedi_order"))

    def test_unknown_faction_no_specialization(self):
        """Unknown faction codes return False, not a crash."""
        from engine.organizations import faction_has_specialization
        self.assertFalse(faction_has_specialization("nonexistent_faction"))


class TestB1fNonChangeSites(unittest.TestCase):
    """The audit listed two more sites that verification confirmed are
    already era-clean. These tests guard against future regressions
    that might re-introduce GCW-only assumptions at those sites."""

    def test_security_uses_axis_name_not_faction_code(self):
        """`engine/security.py::_apply_director_overlay` reads `zs.imperial`,
        which is the Director **axis name** (era-stable per B.1.c
        `ORG_TO_AXIS`), not the faction code. Both empire (GCW) and
        republic (CW) map onto the `imperial` axis, so this code path
        is era-correct without changes."""
        import engine.security as sec
        path = sec.__file__
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        # Should still read from the imperial axis
        self.assertIn('zs, "imperial"', src,
                      "_apply_director_overlay should still read zs.imperial axis")
        # Should NOT have introduced any era-specific check
        self.assertNotIn('== "empire"', src,
                         "security.py should not compare to faction code 'empire'")
        self.assertNotIn('== "republic"', src,
                         "security.py should not compare to faction code 'republic'")

    def test_session_hud_uses_axis_names_in_factions_dict(self):
        """`server/session.py::_hud_alert_level` builds a factions dict
        keyed by Director axis names, not faction codes. The HUD's
        `alert_faction` field is era-stable plumbing for future web
        HUD consumers."""
        import server.session as sess
        path = sess.__file__
        with open(path, "r", encoding="utf-8") as fh:
            src = fh.read()
        # Should still build the axis-keyed dict
        self.assertIn('"imperial": zs.imperial', src,
                      "session.py should still use 'imperial' axis key")
        self.assertIn('"rebel": zs.rebel', src)
        self.assertIn('"criminal": zs.criminal', src)
        self.assertIn('"independent": zs.independent', src)


if __name__ == "__main__":
    unittest.main()
