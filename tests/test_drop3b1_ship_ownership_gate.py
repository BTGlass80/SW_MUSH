# -*- coding: utf-8 -*-
"""
tests/test_drop3b1_ship_ownership_gate.py — Drop 3b.1 ship-control gate.

Model: **open boarding, gated control.** Anyone may board a docked ship, but
only the owner / authorized crew may take the pilot seat and launch; unowned
hulls fail open. Covers:

  * ``engine/ship_access`` policy helpers (pure).
  * ``PilotCommand`` gate (stranger denied with no state change; owner /
    authorized allowed; unowned hull open).
  * ``+shipcrew`` roster (owner add/remove persists; non-owner rejected;
    authorization round-trips through the pilot gate).
  * Structural pins that the gate stays wired into both PilotCommand and
    LaunchCommand.
"""

import os
import re
import sys
import json
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import ship_access as SA                      # noqa: E402
from parser.commands import CommandContext                 # noqa: E402
from parser.space_commands import PilotCommand             # noqa: E402
from parser.ship_crew_commands import ShipCrewCommand      # noqa: E402


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure policy helpers
# ─────────────────────────────────────────────────────────────────────────────
class TestShipAccessHelpers(unittest.TestCase):
    def test_owner_is_authorized(self):
        self.assertTrue(SA.is_authorized_pilot(7, 7, []))

    def test_listed_crew_authorized(self):
        self.assertTrue(SA.is_authorized_pilot(8, 7, [8, 9]))

    def test_stranger_denied(self):
        self.assertFalse(SA.is_authorized_pilot(99, 7, [8, 9]))

    def test_admin_bypass(self):
        self.assertTrue(SA.is_authorized_pilot(99, 7, [], is_admin=True))

    def test_unowned_fails_open(self):
        self.assertTrue(SA.is_authorized_pilot(99, None, []))
        self.assertTrue(SA.is_authorized_pilot(99, 0, []))

    def test_int_str_coercion(self):
        # owner_id stored int, char id arrives as str (and vice-versa)
        self.assertTrue(SA.is_authorized_pilot("7", 7, []))
        self.assertTrue(SA.is_authorized_pilot(8, "7", ["8"]))

    def test_get_authorized_dedups_and_coerces(self):
        sysd = {"authorized_pilots": ["8", 8, 9, "x", None]}
        self.assertEqual(SA.get_authorized_pilots(sysd), [8, 9])

    def test_get_authorized_empty(self):
        self.assertEqual(SA.get_authorized_pilots({}), [])
        self.assertEqual(SA.get_authorized_pilots(None), [])

    def test_add_remove_roundtrip(self):
        sysd = {}
        self.assertTrue(SA.add_authorized_pilot(sysd, 8))
        self.assertEqual(sysd["authorized_pilots"], [8])
        # idempotent add
        self.assertFalse(SA.add_authorized_pilot(sysd, 8))
        # now authorized via the gate
        self.assertTrue(SA.is_authorized_pilot(8, 7, SA.get_authorized_pilots(sysd)))
        # remove
        self.assertTrue(SA.remove_authorized_pilot(sysd, 8))
        self.assertEqual(sysd["authorized_pilots"], [])
        self.assertFalse(SA.remove_authorized_pilot(sysd, 8))
        self.assertFalse(SA.is_authorized_pilot(8, 7, SA.get_authorized_pilots(sysd)))

    def test_add_invalid_id_noop(self):
        sysd = {}
        self.assertFalse(SA.add_authorized_pilot(sysd, "notanint"))
        self.assertEqual(SA.get_authorized_pilots(sysd), [])


# ─────────────────────────────────────────────────────────────────────────────
# Command stubs
# ─────────────────────────────────────────────────────────────────────────────
class _Sess:
    def __init__(self, char, account=None):
        self.character = char
        self.account = account
        self.is_in_game = True
        self.lines = []

    async def send_line(self, s):
        self.lines.append(s)

    @property
    def last(self):
        return self.lines[-1] if self.lines else ""


class _Mgr:
    async def broadcast_to_room(self, *a, **k):
        pass


class _DB:
    def __init__(self, ship, chars_by_name=None):
        self.ship = ship
        self.updated = []
        self._by_name = {k.lower(): v for k, v in (chars_by_name or {}).items()}

    async def get_ship_by_bridge(self, room_id):
        return self.ship

    async def update_ship(self, sid, **fields):
        self.updated.append((sid, fields))
        self.ship.update(fields)  # reflect for follow-up reads

    async def get_character(self, cid):
        return {"id": cid, "name": f"Char{cid}"}

    async def get_character_by_name(self, name):
        return self._by_name.get((name or "").lower())


def _ship(owner_id=7, authorized=None, crew=None, sid=1):
    return {
        "id": sid, "name": "Test Hull", "owner_id": owner_id,
        "crew": json.dumps(crew or {}),
        "systems": json.dumps({"authorized_pilots": authorized or []}),
        "bridge_room_id": 1000, "docked_at": 50,
    }


def _ctx(sess, db, args=""):
    return CommandContext(
        session=sess, raw_input="", command="", args=args, args_list=[],
        db=db, session_mgr=_Mgr())


# ─────────────────────────────────────────────────────────────────────────────
# PilotCommand gate
# ─────────────────────────────────────────────────────────────────────────────
class TestPilotGate(unittest.TestCase):
    def test_stranger_denied_no_state_change(self):
        db = _DB(_ship(owner_id=7, authorized=[]))
        sess = _Sess({"id": 99, "name": "Stranger", "room_id": 1000})
        _run(PilotCommand().execute(_ctx(sess, db)))
        self.assertEqual(db.updated, [], "stranger must not seat as pilot")
        self.assertIn("not cleared", sess.last.lower())

    def test_owner_allowed(self):
        db = _DB(_ship(owner_id=7, authorized=[]))
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 1000})
        _run(PilotCommand().execute(_ctx(sess, db)))
        self.assertEqual(len(db.updated), 1)
        _, fields = db.updated[0]
        self.assertEqual(json.loads(fields["crew"]).get("pilot"), 7)

    def test_authorized_crew_allowed(self):
        db = _DB(_ship(owner_id=7, authorized=[8]))
        sess = _Sess({"id": 8, "name": "CoPilot", "room_id": 1000})
        _run(PilotCommand().execute(_ctx(sess, db)))
        self.assertEqual(len(db.updated), 1)
        _, fields = db.updated[0]
        self.assertEqual(json.loads(fields["crew"]).get("pilot"), 8)

    def test_unowned_hull_anyone_flies(self):
        db = _DB(_ship(owner_id=None, authorized=[]))
        sess = _Sess({"id": 99, "name": "Salvager", "room_id": 1000})
        _run(PilotCommand().execute(_ctx(sess, db)))
        self.assertEqual(len(db.updated), 1)

    def test_admin_bypass(self):
        db = _DB(_ship(owner_id=7, authorized=[]))
        sess = _Sess({"id": 99, "name": "Staff", "room_id": 1000},
                     account={"is_admin": 1})
        _run(PilotCommand().execute(_ctx(sess, db)))
        self.assertEqual(len(db.updated), 1)


# ─────────────────────────────────────────────────────────────────────────────
# +shipcrew roster
# ─────────────────────────────────────────────────────────────────────────────
class TestShipCrewRoster(unittest.TestCase):
    def test_owner_add_persists_and_authorizes(self):
        db = _DB(_ship(owner_id=7, authorized=[]),
                 chars_by_name={"bob": {"id": 8, "name": "Bob"}})
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 1000})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="add Bob")))
        # Persisted to systems.authorized_pilots
        sysd = json.loads(db.ship["systems"])
        self.assertIn(8, SA.get_authorized_pilots(sysd))
        # And Bob now passes the pilot gate
        self.assertTrue(SA.is_authorized_pilot(8, 7, SA.get_authorized_pilots(sysd)))

    def test_non_owner_cannot_modify(self):
        db = _DB(_ship(owner_id=7, authorized=[]),
                 chars_by_name={"bob": {"id": 8, "name": "Bob"}})
        sess = _Sess({"id": 99, "name": "Rando", "room_id": 1000})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="add Bob")))
        self.assertEqual(db.updated, [], "non-owner must not change the roster")
        self.assertIn("owner", sess.last.lower())

    def test_owner_remove(self):
        db = _DB(_ship(owner_id=7, authorized=[8]),
                 chars_by_name={"bob": {"id": 8, "name": "Bob"}})
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 1000})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="remove Bob")))
        sysd = json.loads(db.ship["systems"])
        self.assertNotIn(8, SA.get_authorized_pilots(sysd))

    def test_add_unknown_name(self):
        db = _DB(_ship(owner_id=7, authorized=[]), chars_by_name={})
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 1000})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="add Nobody")))
        self.assertEqual(db.updated, [])
        self.assertIn("no character", sess.last.lower())

    def test_list_runs(self):
        db = _DB(_ship(owner_id=7, authorized=[8]))
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 1000})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="")))
        self.assertIn("authorization", sess.last.lower())

    def test_not_aboard_a_ship(self):
        db = _DB(None)  # get_ship_by_bridge returns None
        sess = _Sess({"id": 7, "name": "Owner", "room_id": 5})
        _run(ShipCrewCommand().execute(_ctx(sess, db, args="add Bob")))
        self.assertEqual(db.updated, [])
        self.assertIn("board", sess.last.lower())


# ─────────────────────────────────────────────────────────────────────────────
# Structural pins — the gate must stay wired
# ─────────────────────────────────────────────────────────────────────────────
class TestGateWiredStructural(unittest.TestCase):
    def setUp(self):
        path = os.path.join(PROJECT_ROOT, "parser", "space_commands.py")
        with open(path, encoding="utf-8") as f:
            self.src = f.read()

    def test_pilot_command_calls_gate(self):
        block = self.src.split("class PilotCommand", 1)[1].split("\nclass ", 1)[0]
        self.assertIn("is_authorized_pilot", block,
                      "PilotCommand lost its ownership gate")

    def test_launch_command_calls_gate(self):
        block = self.src.split("class LaunchCommand", 1)[1].split("\nclass ", 1)[0]
        self.assertIn("is_authorized_pilot", block,
                      "LaunchCommand lost its control re-check")


if __name__ == "__main__":
    unittest.main()
