# -*- coding: utf-8 -*-
"""
tests/test_pvp_display_surfaces.py — +pvp display surface hooks
(May 18 2026).

Companion to test_pvp_flag_unit.py (which covers the parser command,
cooldown, and SECURED-zone invariants) and tests/smoke/test_smoke_pvp_flag.py
(which covers end-to-end PvP flag scenarios).

This file pins the three display surfaces the May 18 rollup left as
follow-ups:

  1. `look` room-occupant rendering shows `[PvP]` marker for flagged
     PCs.
  2. `+sheet` payload (web client) carries `pvp_flagged: bool` in the
     `points` block alongside `force_sensitive`.
  3. HUD area contact roster carries `pvp_flagged: bool` on each PC
     entry alongside name/x/y/kind.

Each test is narrowly scoped — drive the production function with a
minimal char_dict and inspect what it produces. No DB, no harness.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ═════════════════════════════════════════════════════════════════════
# 1. Sheet payload — pvp_flagged in the points block
# ═════════════════════════════════════════════════════════════════════


class TestSheetPayloadPvpFlagged(unittest.TestCase):
    """build_sheet_payload exposes pvp_flagged to the web client."""

    def _payload_for(self, pvp_flagged_value):
        from engine.sheet_renderer import build_sheet_payload
        from engine.character import SkillRegistry

        skill_reg = SkillRegistry()
        skills_yaml = PROJECT_ROOT / "data" / "skills.yaml"
        if skills_yaml.exists():
            skill_reg.load_file(str(skills_yaml))

        # Minimal valid char_dict — enough for Character.from_db_dict to
        # work without raising. Attributes/skills/equipment are stored
        # as JSON strings (the DB column shape).
        char_dict = {
            "id":            1,
            "account_id":    1,
            "name":          "TestChar",
            "species":       "Human",
            "template":      "",
            "wound_level":   0,
            "force_sensitive": 0,
            "credits":       0,
            "character_points": 0,
            "force_points":  0,
            "dark_side_points": 0,
            "move":          10,
            "description":   "",
            "attributes": json.dumps({
                "dexterity": "2D", "knowledge": "2D",
                "mechanical": "2D", "perception": "2D",
                "strength": "2D", "technical": "2D",
            }),
            "skills":        json.dumps({}),
            "equipment":     json.dumps({}),
            "room_id":       1,
            # The field under test:
            "pvp_flagged":   pvp_flagged_value,
        }
        return build_sheet_payload(char_dict, skill_reg)

    def test_sheet_payload_pvp_flagged_false(self):
        payload = self._payload_for(0)
        self.assertIn("points", payload)
        self.assertIn(
            "pvp_flagged", payload["points"],
            "Sheet payload's `points` block must carry `pvp_flagged` "
            "so the web client can render it alongside force_sensitive. "
            f"Got points keys: {sorted(payload['points'].keys())}"
        )
        self.assertEqual(payload["points"]["pvp_flagged"], False)
        self.assertIsInstance(
            payload["points"]["pvp_flagged"], bool,
            "pvp_flagged must be a bool (the field shape "
            "the web client expects), not an int truthy."
        )

    def test_sheet_payload_pvp_flagged_true(self):
        payload = self._payload_for(1)
        self.assertEqual(payload["points"]["pvp_flagged"], True)

    def test_sheet_payload_pvp_flagged_missing_defaults_false(self):
        """A char_dict with no pvp_flagged key (older DB row from
        before schema v27) should produce pvp_flagged=False, not
        raise."""
        from engine.sheet_renderer import build_sheet_payload
        from engine.character import SkillRegistry

        skill_reg = SkillRegistry()
        char_dict = {
            "id":            1,
            "account_id":    1,
            "name":          "TestChar",
            "species":       "Human",
            "template":      "",
            "wound_level":   0,
            "force_sensitive": 0,
            "credits":       0,
            "character_points": 0,
            "force_points":  0,
            "dark_side_points": 0,
            "move":          10,
            "description":   "",
            "attributes": json.dumps({
                "dexterity": "2D", "knowledge": "2D",
                "mechanical": "2D", "perception": "2D",
                "strength": "2D", "technical": "2D",
            }),
            "skills":        json.dumps({}),
            "equipment":     json.dumps({}),
            "room_id":       1,
            # Deliberately no pvp_flagged key
        }
        payload = build_sheet_payload(char_dict, skill_reg)
        self.assertEqual(payload["points"]["pvp_flagged"], False)


# ═════════════════════════════════════════════════════════════════════
# 2. HUD contact roster — pvp_flagged on PC entries
# ═════════════════════════════════════════════════════════════════════
#
# _build_area_contacts is a Session method that takes (db, registry,
# area_key, session_mgr) and returns a list of contact dicts. The PC
# loop reads from session_mgr._sessions.values(). We construct a
# fake session_mgr + fake sessions and inspect the returned list.


class _FakeSession:
    """Stand-in for _ClientSession.character with pvp_flagged."""
    def __init__(self, char_id, name, room_id, pvp_flagged=False):
        self.character = {
            "id": char_id, "name": name, "room_id": room_id,
            "pvp_flagged": 1 if pvp_flagged else 0,
        }
        self.is_in_game = True


class _FakeSessionMgr:
    def __init__(self, sessions):
        # Keyed by id like the real manager
        self._sessions = {id(s): s for s in sessions}

    @property
    def all(self):
        # _build_area_contacts now iterates session_mgr.all (the real
        # SessionManager.all @property), not _sessions.values() directly.
        return list(self._sessions.values())


class _FakeAreaEntry:
    """Stand-in for AreaGeometry entry — has .x and .y."""
    def __init__(self, x, y):
        self.x = x
        self.y = y


class TestContactRosterPvpFlagged(unittest.TestCase):
    """_build_area_contacts surfaces pvp_flagged on each PC entry."""

    def _make_self_session(self):
        # The session whose perspective we're building from (excluded
        # from its own contact roster).
        s = _FakeSession(char_id=99, name="Self", room_id=1)
        return s

    def test_pc_entry_carries_pvp_flagged_false(self):
        """An unflagged PC's contact entry has pvp_flagged=False."""
        import asyncio
        from server.session import Session

        self_sess = self._make_self_session()
        # Bypass __init__: we just need the method, not a real socket.
        sess = Session.__new__(Session)
        sess.character = self_sess.character

        other = _FakeSession(2, "Alice", room_id=10, pvp_flagged=False)
        mgr = _FakeSessionMgr([self_sess, other])

        # Fake the room_id_map: room 10 → AreaEntry at (5, 7)
        room_id_map = {10: _FakeAreaEntry(5, 7)}

        # Patch the registry lookup the method does internally — we
        # call the private _build_area_contacts directly by mocking
        # the registry-resolve step. The production code awaits this
        # method, so our fake must be async.
        class _FakeRegistry:
            async def resolve_area_room_ids(self, area_key, db):
                return room_id_map

        async def go():
            return await sess._build_area_contacts(
                db=None, registry=_FakeRegistry(),
                area_key="test_area", session_mgr=mgr,
            )

        result = asyncio.new_event_loop().run_until_complete(go())
        pcs = [c for c in result if c.get("kind") == "pc"]
        self.assertEqual(
            len(pcs), 1,
            f"Expected exactly one PC (Alice) in roster, got "
            f"{len(pcs)}: {pcs!r}"
        )
        self.assertIn(
            "pvp_flagged", pcs[0],
            f"PC entry must carry pvp_flagged. Got keys: "
            f"{sorted(pcs[0].keys())}"
        )
        self.assertEqual(pcs[0]["pvp_flagged"], False)
        self.assertIsInstance(pcs[0]["pvp_flagged"], bool)

    def test_pc_entry_carries_pvp_flagged_true(self):
        """A flagged PC's contact entry has pvp_flagged=True."""
        import asyncio
        from server.session import Session

        self_sess = self._make_self_session()
        sess = Session.__new__(Session)
        sess.character = self_sess.character

        other = _FakeSession(2, "Bob", room_id=10, pvp_flagged=True)
        mgr = _FakeSessionMgr([self_sess, other])
        room_id_map = {10: _FakeAreaEntry(5, 7)}

        class _FakeRegistry:
            async def resolve_area_room_ids(self, area_key, db):
                return room_id_map

        async def go():
            return await sess._build_area_contacts(
                db=None, registry=_FakeRegistry(),
                area_key="test_area", session_mgr=mgr,
            )

        result = asyncio.new_event_loop().run_until_complete(go())
        pcs = [c for c in result if c.get("kind") == "pc"]
        self.assertEqual(len(pcs), 1)
        self.assertEqual(pcs[0]["pvp_flagged"], True)


# ═════════════════════════════════════════════════════════════════════
# 3. look output — [PvP] marker for flagged PCs
# ═════════════════════════════════════════════════════════════════════
#
# The look rendering is inside _look_room_contents in
# parser/builtin_commands.py. Driving the full execute() is fixture-
# heavy; instead, we test the marker logic as a string-level check
# on the exact format string the production code uses. This is a
# proxy test — if the production string changes, this test breaks
# and the next person updating look output knows to keep the marker.


class TestLookOutputPvpMarker(unittest.TestCase):
    """The look output's other-player render includes [PvP] for
    flagged players. Proxy test: read the production source and
    confirm the marker is in the format-string block."""

    def test_look_renders_pvp_marker_for_flagged(self):
        src = (PROJECT_ROOT / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        # The production block: pvp_str ternary + format string
        # incorporating it. Look for the literal "[PvP]" marker and
        # the conditional read of pvp_flagged.
        self.assertIn(
            "[PvP]", src,
            "parser/builtin_commands.py must contain a [PvP] literal "
            "for the look-output marker. If you renamed the marker, "
            "update this test."
        )
        self.assertIn(
            'other.get("pvp_flagged")', src,
            "parser/builtin_commands.py must read other.get('pvp_flagged') "
            "in the look-render path. If the read shape changed, "
            "update this test."
        )

    def test_look_marker_only_for_flagged(self):
        """The marker block uses a ternary on pvp_flagged so unflagged
        players get an empty string, not the marker. Defensive: a
        future regression might unconditionally append the marker."""
        src = (PROJECT_ROOT / "parser" / "builtin_commands.py").read_text(
            encoding="utf-8"
        )
        # The production line is:
        #   pvp_str = " \033[1;31m[PvP]\033[0m" if other.get("pvp_flagged") else ""
        # The "else \"\"" branch is what makes this conditional.
        # If someone removes the ternary's empty-string branch this
        # check goes red.
        self.assertIn(
            'if other.get("pvp_flagged") else ""', src,
            "Look-output [PvP] marker must be conditional on "
            "pvp_flagged with an empty-string fallback. A regression "
            "that always appends the marker would be visually wrong "
            "and would mislead players about who's actually flagged."
        )


if __name__ == "__main__":
    unittest.main()
