# -*- coding: utf-8 -*-
"""
tests/test_b5_org_rewicker.py — B.5 organization-axis legacy rewicker tests.

Per architecture v38 §19.7 (B.5 — PC `faction_intent` migration). Brian's
decision (Apr 29): auto-rewicker on login with a clear notification.

Three layers under test:

  1. `engine.organizations.get_org_rewicker_map(db, era)` — loads the
     `legacy_rewicker.factions` dict from
     `data/worlds/<era>/organizations.yaml`. Returns {} for GCW (no map)
     and for any era without the YAML or section.

  2. `engine.organizations.apply_org_rewicker(char, db, era, session)`
     — the migration entry point. Reads char.faction_id and
     attributes.faction_intent; if either references a code that
     doesn't exist in the current DB BUT does have a rewicker target,
     swaps it (and persists). Returns a summary dict.

  3. The CW orgs YAML's `legacy_rewicker.factions` section is well-
     formed (the data layer of B.5).

Tests are asymmetric where possible (FAIL pre-B.5, PASS post-B.5).
The migration helpers are new and didn't exist pre-drop; that test
family is purely additive but the byte-equivalence check on GCW is
the regression gate.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


def _reset_era_state():
    from engine.era_state import clear_active_config
    clear_active_config()


# Faction shapes — same as B.6 tests for consistency.
_GCW_FACTIONS = [
    {"id": 1, "code": "empire",      "name": "Galactic Empire",     "org_type": "faction"},
    {"id": 2, "code": "rebel",       "name": "Rebel Alliance",      "org_type": "faction"},
    {"id": 3, "code": "hutt",        "name": "Hutt Cartel",         "org_type": "faction"},
    {"id": 4, "code": "bh_guild",    "name": "Bounty Hunters Guild","org_type": "faction"},
    {"id": 5, "code": "independent", "name": "Independent",         "org_type": "faction"},
]

_CW_FACTIONS = [
    {"id": 1, "code": "republic",              "name": "Galactic Republic", "org_type": "faction"},
    {"id": 2, "code": "cis",                   "name": "Confederacy",       "org_type": "faction"},
    {"id": 3, "code": "jedi_order",            "name": "Jedi Order",        "org_type": "faction"},
    {"id": 4, "code": "hutt_cartel",           "name": "Hutt Cartel",       "org_type": "faction"},
    {"id": 5, "code": "bounty_hunters_guild",  "name": "Bounty Hunters Guild", "org_type": "faction"},
    {"id": 6, "code": "independent",           "name": "Independent",       "org_type": "faction"},
]


def _mock_db_with_orgs(orgs):
    """Mock DB with get_organization, get_all_organizations,
    save_character. save_character mutations are recorded on db._saves."""
    db = MagicMock()
    code_to_org = {o["code"]: o for o in orgs}
    saves = []

    async def _get_org(code):
        return code_to_org.get(code)

    async def _get_all_orgs():
        return list(orgs)

    async def _save_character(char_id, **kwargs):
        saves.append({"char_id": char_id, **kwargs})

    db.get_organization = AsyncMock(side_effect=_get_org)
    db.get_all_organizations = AsyncMock(side_effect=_get_all_orgs)
    db.save_character = AsyncMock(side_effect=_save_character)
    db._saves = saves
    return db


# ──────────────────────────────────────────────────────────────────────
# 1. get_org_rewicker_map — YAML data load
# ──────────────────────────────────────────────────────────────────────

class TestGetOrgRewickerMap(unittest.TestCase):
    """The rewicker map must be loadable from the live CW orgs YAML and
    return {} for GCW (no rewicker exists for GCW; it IS the legacy era)."""

    def test_gcw_returns_empty_map(self):
        from engine.organizations import get_org_rewicker_map
        result = _run(get_org_rewicker_map(None, era="gcw"))
        self.assertEqual(result, {})

    def test_clone_wars_returns_full_map(self):
        from engine.organizations import get_org_rewicker_map
        result = _run(get_org_rewicker_map(None, era="clone_wars"))
        # Must contain at least the canonical four GCW codes.
        self.assertIn("empire", result)
        self.assertIn("rebel", result)
        self.assertIn("hutt", result)
        self.assertIn("bh_guild", result)
        self.assertIn("independent", result)
        # Verify the canonical mappings.
        self.assertEqual(result["empire"], "republic")
        self.assertEqual(result["rebel"], "cis")
        self.assertEqual(result["hutt"], "hutt_cartel")
        self.assertEqual(result["bh_guild"], "bounty_hunters_guild")
        self.assertEqual(result["independent"], "independent")

    def test_unknown_era_returns_empty_map(self):
        """Era with no YAML file → empty dict, no crash."""
        from engine.organizations import get_org_rewicker_map
        result = _run(get_org_rewicker_map(None, era="bogus_era_99"))
        self.assertEqual(result, {})


# ──────────────────────────────────────────────────────────────────────
# 2. apply_org_rewicker — happy paths
# ──────────────────────────────────────────────────────────────────────

class TestApplyOrgRewickerHappyPaths(unittest.TestCase):
    """The headline scenarios."""

    def test_gcw_pc_in_cw_db_faction_id_rewickered(self):
        """The B.5 motivating case: GCW PC with faction_id='empire'
        logs into CW DB → faction_id becomes 'republic' and is persisted."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertTrue(result["migrated"])
        self.assertEqual(result["faction_id_before"], "empire")
        self.assertEqual(result["faction_id_after"], "republic")
        # Char dict was mutated in-place
        self.assertEqual(char["faction_id"], "republic")
        # Persisted via save_character
        self.assertTrue(any(s.get("faction_id") == "republic"
                            for s in db._saves))

    def test_gcw_pc_in_cw_db_faction_intent_rewickered(self):
        """faction_intent='rebel' (from tutorial) → 'cis' on login."""
        from engine.organizations import apply_org_rewicker
        char = {
            "id": 42,
            "faction_id": "independent",
            "attributes": json.dumps({"faction_intent": "rebel"}),
        }
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertTrue(result["migrated"])
        self.assertEqual(result["intent_before"], "rebel")
        self.assertEqual(result["intent_after"], "cis")
        # Verify attributes were persisted
        self.assertTrue(any("attributes" in s for s in db._saves))

    def test_both_faction_id_and_intent_rewickered(self):
        """If both are set, both get migrated in one call."""
        from engine.organizations import apply_org_rewicker
        char = {
            "id": 42,
            "faction_id": "empire",
            "attributes": json.dumps({"faction_intent": "hutt"}),
        }
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertTrue(result["migrated"])
        self.assertEqual(result["faction_id_after"], "republic")
        self.assertEqual(result["intent_after"], "hutt_cartel")

    def test_canonical_mapping_for_each_gcw_faction(self):
        """All four canonical GCW codes rewicker to their CW targets."""
        from engine.organizations import apply_org_rewicker
        cases = [
            ("empire",   "republic"),
            ("rebel",    "cis"),
            ("hutt",     "hutt_cartel"),
            ("bh_guild", "bounty_hunters_guild"),
        ]
        for gcw_code, cw_code in cases:
            with self.subTest(gcw_code=gcw_code):
                char = {"id": 42, "faction_id": gcw_code,
                        "attributes": "{}"}
                db = _mock_db_with_orgs(_CW_FACTIONS)
                result = _run(apply_org_rewicker(char, db, era="clone_wars"))
                self.assertTrue(result["migrated"],
                                f"{gcw_code} should rewicker to {cw_code}")
                self.assertEqual(result["faction_id_after"], cw_code)


# ──────────────────────────────────────────────────────────────────────
# 3. apply_org_rewicker — no-op cases (the byte-equivalence guarantees)
# ──────────────────────────────────────────────────────────────────────

class TestApplyOrgRewickerNoOps(unittest.TestCase):
    """The "must not migrate" cases — these are the regression gates."""

    def test_gcw_era_is_noop(self):
        """In GCW era, the map is empty → no migration regardless of state.

        This is the byte-equivalence gate for production. A GCW PC
        logging into a GCW server must see no change in behavior."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="gcw"))

        self.assertFalse(result["migrated"])
        # No save_character calls in no-op path
        self.assertEqual(len(db._saves), 0)
        # Char unmutated
        self.assertEqual(char["faction_id"], "empire")

    def test_already_current_era_is_noop(self):
        """A CW PC with faction_id='republic' in CW DB → no migration."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "republic", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertFalse(result["migrated"])
        self.assertEqual(len(db._saves), 0)

    def test_independent_is_noop(self):
        """faction_id='independent' is era-agnostic; no migration."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "independent", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertFalse(result["migrated"])

    def test_unmappable_code_left_as_is(self):
        """A faction_id of e.g. 'nonexistent' (not in rewicker map) is
        left as-is for B.6's stale-record advisory to surface."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "nonexistent", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertFalse(result["migrated"])
        self.assertEqual(char["faction_id"], "nonexistent")  # unchanged

    def test_no_faction_id_no_intent_is_noop(self):
        """Char with neither faction_id nor faction_intent → no-op."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertFalse(result["migrated"])


# ──────────────────────────────────────────────────────────────────────
# 4. apply_org_rewicker — error handling
# ──────────────────────────────────────────────────────────────────────

class TestApplyOrgRewickerErrorHandling(unittest.TestCase):
    """Graceful-drop guarantees."""

    def test_db_error_during_save_does_not_raise(self):
        """If save_character raises mid-migration, function logs and
        returns a summary; doesn't crash the login flow."""
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        db.save_character = AsyncMock(side_effect=RuntimeError("DB locked"))

        # Should not raise.
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))
        # Returns a summary dict (whatever state was reached).
        self.assertIsInstance(result, dict)
        self.assertIn("migrated", result)

    def test_db_error_during_get_organization_does_not_raise(self):
        from engine.organizations import apply_org_rewicker
        char = {"id": 42, "faction_id": "empire", "attributes": "{}"}
        db = MagicMock()
        db.get_organization = AsyncMock(
            side_effect=RuntimeError("transient")
        )
        # Should not raise.
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))
        self.assertIsInstance(result, dict)
        self.assertFalse(result["migrated"])

    def test_rewicker_target_missing_from_db_logs_and_skips(self):
        """If the rewicker map points at a target that isn't in the DB
        (e.g., misconfigured or partial seed), leave the legacy code
        as-is and continue. Defensive for misconfigured deployments."""
        from engine.organizations import apply_org_rewicker
        # CW DB without 'republic' (unlikely but defensive)
        cw_minus_republic = [o for o in _CW_FACTIONS
                             if o["code"] != "republic"]
        char = {"id": 42, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(cw_minus_republic)
        result = _run(apply_org_rewicker(char, db, era="clone_wars"))

        self.assertFalse(result["migrated"])
        self.assertEqual(char["faction_id"], "empire")  # left as-is


# ──────────────────────────────────────────────────────────────────────
# 5. CW YAML data integrity
# ──────────────────────────────────────────────────────────────────────

class TestCWOrgsYamlRewickerSection(unittest.TestCase):
    """The data layer of B.5: legacy_rewicker section in CW orgs YAML
    must be present and well-formed."""

    def setUp(self):
        import yaml
        cw_yaml = os.path.join(
            PROJECT_ROOT, "data", "worlds", "clone_wars", "organizations.yaml",
        )
        with open(cw_yaml, encoding="utf-8") as f:
            self.data = yaml.safe_load(f)

    def test_legacy_rewicker_section_present(self):
        self.assertIn("legacy_rewicker", self.data)
        self.assertIn("factions", self.data["legacy_rewicker"])

    def test_canonical_gcw_codes_all_mapped(self):
        m = self.data["legacy_rewicker"]["factions"]
        for gcw_code in ("empire", "rebel", "hutt", "bh_guild", "independent"):
            self.assertIn(gcw_code, m,
                          f"Missing rewicker entry for {gcw_code}")

    def test_independent_passthrough(self):
        m = self.data["legacy_rewicker"]["factions"]
        self.assertEqual(m["independent"], "independent")

    def test_targets_are_real_cw_codes(self):
        """Every rewicker target must match an actual CW faction code."""
        m = self.data["legacy_rewicker"]["factions"]
        cw_codes = {f["code"] for f in self.data["factions"]}
        for gcw_code, cw_target in m.items():
            self.assertIn(
                cw_target, cw_codes,
                f"Rewicker maps {gcw_code} -> {cw_target} but {cw_target} "
                f"is not a CW faction in the same YAML."
            )

    def test_factions_section_unchanged_count(self):
        """Adding legacy_rewicker must not have disturbed the factions
        section (regression gate against accidental edits)."""
        self.assertEqual(len(self.data.get("factions", [])), 8)


if __name__ == "__main__":
    unittest.main()
