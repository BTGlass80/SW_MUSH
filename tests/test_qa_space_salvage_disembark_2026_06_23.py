# -*- coding: utf-8 -*-
"""
tests/test_qa_space_salvage_disembark_2026_06_23.py — QA break-it regression
(ships / space-combat sweep, 2026-06-23).

Three findings:

#1 [CRASH+CORRUPTION] salvage / mine / harvest crashed on the bridge broadcast.
   They called `ctx.session_mgr.broadcast_to_room(..., exclude_session=ctx.session)`,
   but the signature is `broadcast_to_room(room_id, text, exclude=None,
   source_char=None)` — the wrong kwarg raised TypeError BEFORE `remove_anomaly`,
   so a successful salvage surfaced "An error occurred" AND left the wreck
   infinitely farmable. Fix: `exclude_session=` -> `exclude=` at all three sites.

#2 [CORRUPTION] `disembark` cleared only the pilot seat + gunner stations, not
   the other single-occupancy stations. A disembarking copilot/engineer/navigator/
   commander/sensors left their seat stuck-occupied (and a cleared slot surfaced a
   stale "#None"). Fix: loop over `_SINGLE_STATIONS`.

#3 [CORRUPTION] `sell cargo` removed the cargo (update_ship) BEFORE crediting the
   player and never checked the credit write — a failed credit write left the
   cargo gone with no payment. Fix: credit first (confirm non-None), then remove.

These pin the fixes: a signature contract that makes the wrong kwarg
unrepresentable, plus structural guards on the disembark loop and the sell-cargo
credit-first ordering.
"""
from __future__ import annotations

import inspect
import unittest
from pathlib import Path

from server.session import SessionManager

REPO = Path(__file__).resolve().parent.parent
SC = (REPO / "parser" / "space_commands.py").read_text(encoding="utf-8")
BC = (REPO / "parser" / "builtin_commands.py").read_text(encoding="utf-8")


class TestSalvageBroadcastKwarg(unittest.TestCase):
    def test_broadcast_to_room_param_is_exclude_not_exclude_session(self):
        params = list(
            inspect.signature(SessionManager.broadcast_to_room).parameters)
        self.assertIn("exclude", params)
        self.assertNotIn("exclude_session", params)

    def test_no_exclude_session_kwarg_anywhere_in_space_commands(self):
        # Makes the salvage/mine/harvest crash class unrepresentable: any
        # broadcast_to_room(exclude_session=...) is a TypeError waiting to abort
        # the anomaly cleanup.
        self.assertNotIn("exclude_session", SC)


class TestDisembarkClearsAllStations(unittest.TestCase):
    def _disembark_body(self) -> str:
        i = SC.index("class DisembarkCommand")
        j = SC.index("\nclass ", i + 1)
        return SC[i:j]

    def test_disembark_clears_every_single_station(self):
        body = self._disembark_body()
        self.assertIn("for _station in _SINGLE_STATIONS:", body,
                      "disembark must clear every single-occupancy station")
        # the old pilot-only clear is gone
        self.assertNotIn('if crew.get("pilot") == char_id:', body)

    def test_single_stations_covers_all_seats(self):
        # the constant the loop relies on must include the non-pilot seats.
        self.assertIn('_SINGLE_STATIONS = ["pilot", "copilot", "engineer", '
                      '"navigator", "commander", "sensors"]', SC)


class TestSellCargoCreditFirst(unittest.TestCase):
    def test_credit_award_precedes_cargo_removal(self):
        i = BC.index("async def _handle_sell_cargo")
        body = BC[i:i + 8000]
        cred = body.find(
            'adjust_credits(char["id"], total_revenue, "trade_goods")')
        ship = body.find('update_ship(ship["id"], cargo=')
        self.assertNotEqual(cred, -1, "sell-cargo adjust_credits not found")
        self.assertNotEqual(ship, -1, "sell-cargo update_ship not found")
        self.assertLess(cred, ship,
                        "adjust_credits must precede the cargo-removing "
                        "update_ship (credit-first; the failure-leaves-no-pay fix)")
        self.assertIn("if _bal is None:", body,
                      "the credit write must be confirmed before removing cargo")


if __name__ == "__main__":
    unittest.main()
