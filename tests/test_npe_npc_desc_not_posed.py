# -*- coding: utf-8 -*-
"""
tests/test_npe_npc_desc_not_posed.py — NPE polish (2026-06-20).

Regression guard for the "post-combat huge text" defect: a defeated /
present NPC's full physical description re-rendered in the loud, bright
pose style instead of the dim description style.

Root cause (found 2026-06-20, not a server pose emitter): the room-
contents render in parser/builtin_commands.py emitted the NPC name and
its description on ONE line — "<Name> is here. <desc>". The web client's
text classifier (static/client.html simplePoseMatch) parses that as
name="<Name>", verb="is", rest="here. <desc>" and, once the NPC is a
known actor (it posed during combat), renders the whole thing as a
bright NPC *pose* row. The fix splits the line server-side (description
on its own wrapped line, mirroring LookCommand._look_at) and adds a
client-side presence-line guard as defense-in-depth.

These tests pin both halves:
  1. SERVER (behavioral): _look_room_contents emits "<Name> is here."
     and the description on SEPARATE lines — never combined.
  2. CLIENT (proxy / source-assert): client.html carries the
     isPresenceLine guard so a "<Name> is here ..." line is never
     classified as a pose, mirroring the test style used for other
     client.html invariants (test_onboard_tour_per_character.py).
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ─────────────────────────────────────────────────────────────────────
# Fakes — capture every line the look render emits.
# ─────────────────────────────────────────────────────────────────────

class _CapturingSession:
    """Records send_line / send_prose emissions as (kind, text) tuples."""
    wrap_width = 80

    def __init__(self):
        self.emitted = []  # list[tuple[str, str]]

    async def send_line(self, text: str = ""):
        self.emitted.append(("line", text))

    async def send_prose(self, text: str, indent: str = "  "):
        # The production code routes the NPC description through here on
        # its OWN line; record it verbatim (no re-wrap needed for the test).
        self.emitted.append(("prose", f"{indent}{text}"))


class _FakeDB:
    """Minimal db stub: one described NPC in the room, nothing else."""
    def __init__(self, npcs):
        self._npcs = npcs

    async def get_characters_in_room(self, room_id):
        return []

    async def get_npcs_in_room(self, room_id):
        return list(self._npcs)

    async def get_corpses_in_room(self, room_id):
        return []

    async def get_objects_in_room(self, room_id, kind):
        return []


class _FakeCtx:
    def __init__(self, db):
        self.db = db


# ─────────────────────────────────────────────────────────────────────
# 1. Server — name and description on separate lines
# ─────────────────────────────────────────────────────────────────────

class TestNpcDescOnSeparateLine(unittest.TestCase):

    NPC_NAME = "Gundark"
    DESC = ("A hulking reek-hide brute looms over the sand, tusks scarred "
            "from a hundred pit-fights.")
    DESC_NEEDLE = "hulking reek-hide brute"

    def _render(self, npcs):
        from parser.builtin_commands import LookCommand
        cmd = LookCommand.__new__(LookCommand)  # method uses ctx/session, not self
        sess = _CapturingSession()
        ctx = _FakeCtx(_FakeDB(npcs))
        char = {"id": 1, "room_id": 7}
        room = {"id": 7}
        asyncio.new_event_loop().run_until_complete(
            cmd._look_room_contents(ctx, sess, char, room)
        )
        return sess.emitted

    def test_name_and_desc_never_on_same_line(self):
        npc = {"id": 50, "name": self.NPC_NAME, "description": self.DESC}
        emitted = self._render([npc])
        # The defect line: a single emission carrying BOTH "is here" and the
        # description. That is exactly what the client mis-poses.
        offenders = [
            text for _kind, text in emitted
            if "is here" in text and self.DESC_NEEDLE in text
        ]
        self.assertEqual(
            offenders, [],
            "NPC name + description must NOT share a line — the web client "
            "mis-classifies '<Name> is here. <desc>' as a bright pose. "
            f"Offending emission(s): {offenders!r}"
        )

    def test_name_line_present_and_short(self):
        npc = {"id": 50, "name": self.NPC_NAME, "description": self.DESC}
        emitted = self._render([npc])
        name_lines = [t for _k, t in emitted
                      if self.NPC_NAME in t and "is here" in t]
        self.assertTrue(
            name_lines,
            "Expected a '<Name> is here.' line for the present NPC."
        )
        # And that line must NOT carry the description text.
        self.assertNotIn(
            self.DESC_NEEDLE, name_lines[0],
            "The '<Name> is here.' line must not include the description."
        )

    def test_description_still_shown(self):
        """The fix must not DROP the description — it moves it to its own
        line, it does not hide it."""
        npc = {"id": 50, "name": self.NPC_NAME, "description": self.DESC}
        emitted = self._render([npc])
        self.assertTrue(
            any(self.DESC_NEEDLE in t for _k, t in emitted),
            "The NPC description must still be rendered (on its own line)."
        )

    def test_bracket_description_suppressed(self):
        """A bracketed/system description ('[...]') is still suppressed —
        only the name line shows (pre-existing behavior preserved)."""
        npc = {"id": 51, "name": "Droid", "description": "[no-look marker]"}
        emitted = self._render([npc])
        self.assertFalse(
            any("no-look marker" in t for _k, t in emitted),
            "Bracketed descriptions must remain suppressed."
        )
        self.assertTrue(
            any("Droid" in t and "is here" in t for _k, t in emitted),
            "The name line must still render for a bracket-desc NPC."
        )


# ─────────────────────────────────────────────────────────────────────
# 2. Client — presence-line guard present in classifier
# ─────────────────────────────────────────────────────────────────────

class TestClientPresenceGuard(unittest.TestCase):

    def test_client_has_presence_line_guard(self):
        src = (PROJECT_ROOT / "static" / "client.html").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "isPresenceLine", src,
            "static/client.html must guard simplePoseMatch with an "
            "isPresenceLine check so '<Name> is here ...' room-presence "
            "lines are never classified as poses."
        )
        # The guard must actually gate the pose branch.
        self.assertIn(
            "!isPresenceLine", src,
            "The simplePoseMatch pose branch must require !isPresenceLine."
        )


if __name__ == "__main__":
    unittest.main()
