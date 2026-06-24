# -*- coding: utf-8 -*-
"""
tests/test_l2_force_0d_lockout_fix.py

L2 fix: a Force-sensitive character whose control/sense/alter attributes are
all "0D" (new character who hasn't been taught yet) should:
  1. Still read as force_sensitive=True via key-presence in load_from_db.
  2. Receive a clear "untrained / use +teach" message from ForceCommand
     instead of the confusing "you lack the Force skill(s) needed" message.

Before the fix:
  - load_from_db used `if not pool.is_zero()` so a 0D pool did NOT trigger
    force_sensitive=True via the key-presence path (only the explicit JSON
    flag did). CLAUDE.md invariant: key presence → force_sensitive.
  - ForceCommand printed "You lack the Force skill(s) needed: Control. You
    must develop Control..." which is confusing for a character who IS
    Force-sensitive but simply hasn't trained yet.

After the fix:
  - Any force_attr key present in the attrs blob → force_sensitive=True
    (value 0D or not; this matches the architecture invariant).
  - ForceCommand prints the actionable "+teach" guidance message.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.character import Character
from engine.dice import DicePool


# ── helpers ──────────────────────────────────────────────────────────────────

def _db_row(control="0D", sense="0D", alter="0D", *, explicit_flag=None,
            extra_attrs=None):
    """Build a minimal DB row dict with force attrs at the given values."""
    attrs = {"dexterity": "3D", "knowledge": "2D", "mechanical": "2D",
             "perception": "2D", "strength": "3D", "technical": "2D"}
    if control is not None:
        attrs["control"] = control
    if sense is not None:
        attrs["sense"] = sense
    if alter is not None:
        attrs["alter"] = alter
    if extra_attrs:
        attrs.update(extra_attrs)
    row = {"id": 1, "name": "Padawan", "room_id": 10,
           "attributes": json.dumps(attrs), "skills": "{}",
           "wound_level": 0, "dark_side_points": 0}
    if explicit_flag is not None:
        # Inject force_sensitive into the JSON blob (old path)
        blob = json.loads(row["attributes"])
        blob_outer = {"force_sensitive": explicit_flag}
        # force_sensitive is stored at top-level of the character sheet JSON
        # (the 'attributes' column actually stores the full sheet blob for
        # from_db_dict; it just needs the force_sensitive key at the right level).
        # Actually in from_db_dict, sheet is the parsed JSON of attributes column.
        row["attributes"] = json.dumps({**blob, "force_sensitive_flag_injection": True})
    return row


def _char_from_row(row):
    return Character.from_db_dict(row)


def _run(coro):
    return asyncio.run(coro)


# ── fake parser plumbing (mirror test_drop4a_social_force.py pattern) ────────

class _FakeSession:
    def __init__(self, character):
        self.character = character
        self.sent = []

    async def send_line(self, line=""):
        self.sent.append(line)

    def invalidate_char_obj(self):
        pass


class _FakeDB:
    async def get_characters_in_room(self, room_id, source_char=None):
        return []

    async def get_npcs_in_room(self, room_id):
        return []

    async def save_character(self, char_id, **fields):
        pass


class _FakeSessionMgr:
    async def broadcast_to_room(self, room_id, msg, exclude=None,
                                source_char=None):
        pass


def _ctx(session, db, args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"force {args}".strip(),
        command="force",
        args=args,
        args_list=args.split() if args else [],
        db=db,
        session_mgr=_FakeSessionMgr(),
    )


# ── engine fix: load_from_db key-presence rule ───────────────────────────────

class TestLoadFromDbKeyPresence(unittest.TestCase):
    """force_sensitive is True when the key is present, even at 0D."""

    def test_all_three_at_0d_sets_force_sensitive(self):
        row = {"id": 1, "name": "X", "room_id": 1,
               "attributes": json.dumps(
                   {"dexterity": "3D", "control": "0D",
                    "sense": "0D", "alter": "0D"}),
               "skills": "{}"}
        char = Character.from_db_dict(row)
        self.assertTrue(
            char.force_sensitive,
            "key presence (even at 0D) must set force_sensitive=True")

    def test_nonzero_force_attrs_set_force_sensitive(self):
        row = {"id": 1, "name": "X", "room_id": 1,
               "attributes": json.dumps(
                   {"dexterity": "3D", "control": "2D",
                    "sense": "1D", "alter": "1D"}),
               "skills": "{}"}
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_no_force_keys_leaves_force_sensitive_false(self):
        row = {"id": 1, "name": "X", "room_id": 1,
               "attributes": json.dumps({"dexterity": "3D"}),
               "skills": "{}"}
        char = Character.from_db_dict(row)
        self.assertFalse(char.force_sensitive)

    def test_0d_attrs_preserved_in_roundtrip(self):
        row = {"id": 1, "name": "X", "room_id": 1,
               "attributes": json.dumps(
                   {"dexterity": "3D", "control": "0D",
                    "sense": "0D", "alter": "0D"}),
               "skills": "{}"}
        char = Character.from_db_dict(row)
        self.assertEqual(str(char.control), "0D")
        self.assertEqual(str(char.sense), "0D")
        self.assertEqual(str(char.alter), "0D")

    def test_partial_force_keys_set_force_sensitive(self):
        # Only 'control' present → still force_sensitive
        row = {"id": 1, "name": "X", "room_id": 1,
               "attributes": json.dumps(
                   {"dexterity": "3D", "control": "0D"}),
               "skills": "{}"}
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)


# ── parser fix: ForceCommand gives actionable message for 0D skills ──────────

class TestForceCommand0DMessage(unittest.TestCase):
    """ForceCommand should tell 0D Force-sensitive chars to use +teach."""

    def _char_dict_0d(self):
        return {"id": 1, "name": "Padawan", "room_id": 10,
                "attributes": json.dumps(
                    {"dexterity": "3D", "control": "0D",
                     "sense": "0D", "alter": "0D"}),
                "skills": "{}",
                "wound_level": 0, "dark_side_points": 0}

    def _char_dict_trained(self, control="3D"):
        return {"id": 2, "name": "Jedi", "room_id": 10,
                "attributes": json.dumps(
                    {"dexterity": "3D", "control": control,
                     "sense": "3D", "alter": "2D"}),
                "skills": "{}",
                "wound_level": 0, "dark_side_points": 0}

    def _char_dict_non_fs(self):
        return {"id": 3, "name": "Smuggler", "room_id": 10,
                "attributes": json.dumps({"dexterity": "3D"}),
                "skills": "{}",
                "wound_level": 0, "dark_side_points": 0}

    def test_0d_gets_untrained_message_not_lack_message(self):
        from parser.force_commands import ForceCommand
        char = self._char_dict_0d()
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB(), args="control_pain")
        _run(ForceCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertNotIn(
            "You lack the Force skill(s) needed",
            joined,
            "old 'lack the skill' message must not appear for 0D Force-sensitive",
        )
        self.assertIn(
            "+teach",
            joined,
            "actionable +teach guidance must appear for 0D Force-sensitive",
        )
        self.assertIn(
            "untrained",
            joined.lower(),
            "message should mention the skill is untrained",
        )

    def test_non_force_sensitive_gets_not_fs_message(self):
        from parser.force_commands import ForceCommand
        char = self._char_dict_non_fs()
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB(), args="control_pain")
        _run(ForceCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("not Force-sensitive", joined)

    def test_unknown_power_gives_unknown_power_message(self):
        from parser.force_commands import ForceCommand
        char = self._char_dict_0d()
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB(), args="no_such_power")
        _run(ForceCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("Unknown Force power", joined)

    def test_0d_control_single_skill_message(self):
        from parser.force_commands import ForceCommand
        # control_pain only needs Control; make Sense+Alter trained so we
        # isolate the single-skill 0D case.
        char = {"id": 4, "name": "Padawan", "room_id": 10,
                "attributes": json.dumps(
                    {"dexterity": "3D", "control": "0D",
                     "sense": "3D", "alter": "2D"}),
                "skills": "{}",
                "wound_level": 0, "dark_side_points": 0}
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB(), args="control_pain")
        _run(ForceCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("+teach", joined)
        self.assertIn("Control", joined)

    def test_no_args_gives_usage_not_untrained(self):
        from parser.force_commands import ForceCommand
        char = self._char_dict_0d()
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB(), args="")
        _run(ForceCommand().execute(ctx))
        joined = "\n".join(sess.sent)
        self.assertIn("Usage", joined)


if __name__ == "__main__":
    unittest.main()
