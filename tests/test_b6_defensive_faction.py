# -*- coding: utf-8 -*-
"""
tests/test_b6_defensive_faction.py — B.6 defensive `+faction` tests.

Covers three defensive surfaces:

  1. `engine.organizations.is_faction_membership_stale(char, db)` —
     new helper. Returns True when char.faction_id references a code
     that doesn't exist in DB (orphan record).

  2. `engine.organizations.get_all_faction_reps(char, db)` —
     previously hardcoded `FACTIONS = ["empire", "rebel", "hutt", "bh_guild"]`.
     Now derives faction codes from `db.get_all_organizations()`. This
     is the era-clean fix: in a CW DB the function returns CW factions
     (republic/cis/jedi_order/...), not an empty dict.

  3. `engine.organizations.format_faction_status(char, db)` — when
     memberships is empty AND char.faction_id references a non-DB
     faction, the output now contains a "stale record" advisory
     instead of silently saying "Independent."

  4. `parser.faction_commands.FactionCommand._cmd_info` — when called
     with no explicit code AND char.faction_id references a non-DB
     faction, the message distinguishes "your record is stale" from
     the explicit "Unknown faction 'X'."

Tests are asymmetric where possible (FAIL pre-drop, PASS post-drop).
The `is_faction_membership_stale` helper is new and didn't exist
pre-drop; that test family is purely additive.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


def _mock_db_with_orgs(orgs):
    """Build a MagicMock DB whose get_organization/get_all_organizations
    return entries from `orgs` (a list of dicts shaped like real org rows)."""
    db = MagicMock()
    code_to_org = {o["code"]: o for o in orgs}

    async def _get_org(code):
        return code_to_org.get(code)

    async def _get_all_orgs():
        return list(orgs)

    async def _get_membership(char_id, org_id):
        return None

    async def _get_memberships_for_char(char_id):
        return []

    async def _get_org_ranks(org_id):
        return []

    db.get_organization = AsyncMock(side_effect=_get_org)
    db.get_all_organizations = AsyncMock(side_effect=_get_all_orgs)
    db.get_membership = AsyncMock(side_effect=_get_membership)
    db.get_memberships_for_char = AsyncMock(side_effect=_get_memberships_for_char)
    db.get_org_ranks = AsyncMock(side_effect=_get_org_ranks)
    return db


_GCW_FACTIONS = [
    {"id": 1,  "code": "empire",      "name": "Galactic Empire",     "org_type": "faction"},
    {"id": 2,  "code": "rebel",       "name": "Rebel Alliance",      "org_type": "faction"},
    {"id": 3,  "code": "hutt",        "name": "Hutt Cartel",         "org_type": "faction"},
    {"id": 4,  "code": "bh_guild",    "name": "Bounty Hunters Guild","org_type": "faction"},
    {"id": 5,  "code": "independent", "name": "Independent",         "org_type": "faction"},
    # A guild row, to confirm filter excludes guilds.
    {"id": 10, "code": "mechanics_guild", "name": "Mechanics Guild", "org_type": "guild"},
]

_CW_FACTIONS = [
    {"id": 1,  "code": "republic",    "name": "Galactic Republic",
     "org_type": "faction"},
    {"id": 2,  "code": "cis",         "name": "Confederacy of Independent Systems",
     "org_type": "faction"},
    {"id": 3,  "code": "jedi_order",  "name": "Jedi Order",
     "org_type": "faction"},
    {"id": 4,  "code": "hutt_cartel", "name": "Hutt Cartel",
     "org_type": "faction"},
    {"id": 5,  "code": "bounty_hunters_guild",
     "name": "Bounty Hunters Guild", "org_type": "faction"},
    {"id": 6,  "code": "independent", "name": "Independent",
     "org_type": "faction"},
    {"id": 10, "code": "mechanics_guild", "name": "Mechanics Guild",
     "org_type": "guild"},
]


# ──────────────────────────────────────────────────────────────────────
# 1. is_faction_membership_stale
# ──────────────────────────────────────────────────────────────────────

class TestIsFactionMembershipStale(unittest.TestCase):

    def test_independent_is_never_stale(self):
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "independent"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        self.assertFalse(_run(is_faction_membership_stale(char, db)))

    def test_missing_faction_id_is_never_stale(self):
        """char with no faction_id key at all → False."""
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        self.assertFalse(_run(is_faction_membership_stale(char, db)))

    def test_empty_string_faction_id_is_never_stale(self):
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": ""}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        self.assertFalse(_run(is_faction_membership_stale(char, db)))

    def test_valid_gcw_faction_in_gcw_db_is_not_stale(self):
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "empire"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        self.assertFalse(_run(is_faction_membership_stale(char, db)))

    def test_gcw_faction_in_cw_db_is_stale(self):
        """The B.6 motivating case: GCW PC logs into CW DB."""
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "empire"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        self.assertTrue(_run(is_faction_membership_stale(char, db)))

    def test_cw_faction_in_gcw_db_is_stale(self):
        """Symmetric: a CW PC logging into GCW DB is also stale."""
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "republic"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        self.assertTrue(_run(is_faction_membership_stale(char, db)))

    def test_valid_cw_faction_in_cw_db_is_not_stale(self):
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "republic"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        self.assertFalse(_run(is_faction_membership_stale(char, db)))

    def test_db_error_returns_false_conservatively(self):
        """If db.get_organization raises, return False (not True).
        Better to skip the advisory than to surface a false positive."""
        from engine.organizations import is_faction_membership_stale
        char = {"id": 1, "faction_id": "empire"}
        db = MagicMock()
        db.get_organization = AsyncMock(
            side_effect=RuntimeError("transient DB error")
        )
        self.assertFalse(_run(is_faction_membership_stale(char, db)))


# ──────────────────────────────────────────────────────────────────────
# 2. get_all_faction_reps — DB-derived faction list
# ──────────────────────────────────────────────────────────────────────

class TestGetAllFactionRepsEraClean(unittest.TestCase):

    def test_gcw_db_returns_gcw_factions(self):
        """Byte-equivalence guarantee: GCW DB still returns the four
        canonical GCW faction codes (empire, rebel, hutt, bh_guild)."""
        from engine.organizations import get_all_faction_reps
        char = {"id": 1, "attributes": "{}"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        result = _run(get_all_faction_reps(char, db))
        self.assertEqual(
            set(result.keys()),
            {"empire", "rebel", "hutt", "bh_guild"},
        )

    def test_cw_db_returns_cw_factions_not_empty(self):
        """The B.6 fix: against CW DB, returns CW factions instead of
        an empty dict (which is what the hardcoded list produced)."""
        from engine.organizations import get_all_faction_reps
        char = {"id": 1, "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        result = _run(get_all_faction_reps(char, db))
        self.assertGreater(
            len(result), 0,
            "CW DB should produce a non-empty rep map (was empty pre-B.6)"
        )
        self.assertIn("republic", result)
        self.assertIn("cis", result)
        self.assertIn("jedi_order", result)

    def test_independent_excluded_from_rep_map(self):
        """`independent` is a null faction; never include it."""
        from engine.organizations import get_all_faction_reps
        char = {"id": 1, "attributes": "{}"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        result = _run(get_all_faction_reps(char, db))
        self.assertNotIn("independent", result)

    def test_guilds_excluded_from_rep_map(self):
        """org_type='guild' rows are not faction rep targets."""
        from engine.organizations import get_all_faction_reps
        char = {"id": 1, "attributes": "{}"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        result = _run(get_all_faction_reps(char, db))
        self.assertNotIn("mechanics_guild", result)


# ──────────────────────────────────────────────────────────────────────
# 3. format_faction_status — orphan-record advisory
# ──────────────────────────────────────────────────────────────────────

class TestFormatFactionStatusOrphan(unittest.TestCase):

    def test_independent_char_shows_independent_label(self):
        """Baseline: char with faction_id='independent' still shows
        'Independent', no advisory."""
        from engine.organizations import format_faction_status
        char = {"id": 1, "faction_id": "independent", "attributes": "{}"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        out = _run(format_faction_status(char, db))
        self.assertIn("Independent", out)
        self.assertNotIn("stale record", out)

    def test_orphan_char_shows_advisory(self):
        """The B.6 fix: char with faction_id='empire' but no DB row
        shows 'stale record' advisory, not silent 'Independent'."""
        from engine.organizations import format_faction_status
        char = {"id": 1, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        out = _run(format_faction_status(char, db))
        self.assertIn("stale record", out)
        self.assertIn("'empire'", out)

    def test_orphan_advisory_suggests_remediation(self):
        """Advisory tells the user how to fix it."""
        from engine.organizations import format_faction_status
        char = {"id": 1, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        out = _run(format_faction_status(char, db))
        self.assertIn("faction list", out)
        self.assertIn("faction join", out)

    def test_no_crash_on_orphan(self):
        """The headline ask: never crashes, always returns a string."""
        from engine.organizations import format_faction_status
        char = {"id": 1, "faction_id": "empire", "attributes": "{}"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        out = _run(format_faction_status(char, db))
        self.assertIsInstance(out, str)
        self.assertGreater(len(out), 0)


# ──────────────────────────────────────────────────────────────────────
# 4. +faction info defensive routing
# ──────────────────────────────────────────────────────────────────────

class TestFactionInfoDefensive(unittest.TestCase):

    def _make_ctx(self, db, char):
        """Minimal ctx object with .db, .args, .session.send_line capture."""
        ctx = types.SimpleNamespace()
        ctx.db = db
        ctx.args = ""
        sent_lines = []
        ctx.session = types.SimpleNamespace()
        async def _send(line):
            sent_lines.append(line)
        ctx.session.send_line = _send
        ctx.session.character = char
        ctx._sent = sent_lines
        return ctx

    def test_explicit_bad_code_says_unknown(self):
        """`+faction info bogus` → 'Unknown faction "bogus"' (unchanged)."""
        from parser.faction_commands import FactionCommand
        char = {"id": 1, "faction_id": "independent"}
        db = _mock_db_with_orgs(_GCW_FACTIONS)
        ctx = self._make_ctx(db, char)
        cmd = FactionCommand()
        _run(cmd._cmd_info(ctx, char, "bogus"))
        joined = "\n".join(ctx._sent)
        self.assertIn("Unknown faction", joined)
        self.assertIn("bogus", joined)

    def test_implicit_orphan_says_stale_not_unknown(self):
        """`+faction info` (no args) with stale faction_id → advisory
        message, not the bare 'Unknown faction X' (which is misleading
        because the user didn't type the code)."""
        from parser.faction_commands import FactionCommand
        char = {"id": 1, "faction_id": "empire"}
        db = _mock_db_with_orgs(_CW_FACTIONS)
        ctx = self._make_ctx(db, char)
        cmd = FactionCommand()
        _run(cmd._cmd_info(ctx, char, ""))
        joined = "\n".join(ctx._sent)
        # Friendlier wording: tells the player WHAT to do.
        self.assertIn("no longer", joined)
        self.assertIn("faction list", joined)
        self.assertIn("faction join", joined)
        # Should NOT crash, should NOT show only the cryptic message.
        # (We tolerate the word "Unknown" appearing nowhere here, but
        # we don't strictly require it absent — just require the
        # remediation guidance.)


if __name__ == "__main__":
    unittest.main()
