# -*- coding: utf-8 -*-
"""
tests/test_drop0a_patrol_era_cleanness.py — Drop 0a tail (2026-06-04)

B3 era-cleanness: engine/encounter_patrol.py was emitting hardcoded
"[IMPERIAL BOARDING] Stormtroopers ..." / "[IMPERIAL CUSTOMS] ..." strings
to players in the Clone Wars production era. The boarding authority now
follows the zone's controlling faction (Republic / CIS / Hutt / neutral)
via the existing _default_patrol_name / _board_party helpers.

These tests drive the real _apply_infraction broadcast and assert no
Empire-era tokens leak, plus pin the era-aware label tables.
"""
import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import encounter_patrol as ep  # noqa: E402

_BANNED = ("Imperial", "IMPERIAL", "imperial", "Stormtrooper", "stormtrooper",
           "Empire", "TIE fighter", "Rebel")


def _run(coro):
    return asyncio.run(coro)


class _FakeMgr:
    def __init__(self):
        self.captured = []

    async def broadcast_to_bridge(self, enc, text, session_mgr):
        self.captured.append(text)

    def resolve(self, enc, outcome=None):
        pass


class _FakeDB:
    async def get_character(self, cid):
        return {"id": cid, "credits": 50000}

    async def adjust_credits(self, cid, delta, source):
        return True


class _Enc:
    def __init__(self):
        self.zone_id = "zone_test"
        self.context = {}
        self.target_ship_id = None


# ══════════════════════════════════════════════════════════════════════════
# Era-aware label tables
# ══════════════════════════════════════════════════════════════════════════

class TestPatrolEraTables(unittest.TestCase):
    def test_no_empire_tokens_in_labels(self):
        blob = " ".join(ep._PATROL_NAME_BY_AUTHORITY.values()) + " " + \
               " ".join(ep._BOARD_PARTY_BY_AUTHORITY.values())
        for banned in _BANNED:
            self.assertNotIn(banned, blob,
                             f"era-broken token {banned!r} in patrol labels")

    def test_cw_faction_mappings(self):
        self.assertEqual(ep._BOARD_PARTY_BY_AUTHORITY["republic"], "Clone troopers")
        self.assertEqual(ep._BOARD_PARTY_BY_AUTHORITY["cis"], "B1 battle droids")
        self.assertEqual(ep._PATROL_NAME_BY_AUTHORITY["republic"], "Republic Sector Patrol")


# ══════════════════════════════════════════════════════════════════════════
# _apply_infraction broadcast is era-clean
# ══════════════════════════════════════════════════════════════════════════

class TestApplyInfractionEraClean(unittest.TestCase):
    def _broadcast_for(self, inf_class, authority="republic"):
        orig = ep._zone_authority
        ep._zone_authority = lambda z: authority
        mgr = _FakeMgr()
        try:
            _run(ep._apply_infraction(
                _Enc(), mgr, _FakeDB(), None,
                inf_class=inf_class, reason="contraband detected", char_id=7))
        finally:
            ep._zone_authority = orig
        return "\n".join(mgr.captured)

    def test_fine_branch_is_era_clean(self):
        text = self._broadcast_for(5)  # Class Five -> a fine
        for banned in _BANNED:
            self.assertNotIn(banned, text, f"leaked {banned!r} in fine broadcast")
        # Era-appropriate authority + party present.
        self.assertIn("Republic Sector Patrol", text)
        self.assertIn("Clone troopers", text)
        self.assertIn("board for inspection", text)

    def test_detained_branch_is_era_clean(self):
        text = self._broadcast_for(1)  # Class One, fine (0,0) -> detained
        for banned in _BANNED:
            self.assertNotIn(banned, text, f"leaked {banned!r} in detain broadcast")
        self.assertIn("Republic Sector Patrol", text)
        self.assertIn("detained", text)

    def test_hutt_authority_labels(self):
        text = self._broadcast_for(5, authority="hutt")
        for banned in _BANNED:
            self.assertNotIn(banned, text)
        self.assertIn("Hutt Cartel Customs", text)
        self.assertIn("Cartel enforcers", text)


if __name__ == "__main__":
    unittest.main()
