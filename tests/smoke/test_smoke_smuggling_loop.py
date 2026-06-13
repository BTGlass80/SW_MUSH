# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_smuggling_loop.py — Pytest entry points for SL1-SL4.

Exercises the SMUGGLING job loop end-to-end:
  SL1: +smugjobs board renders in a board-eligible room
  SL2: smugaccept <id> → job ACCEPTED → +smugjob shows active run
  SL3: smugdeliver from a non-docked state returns the docked-ship refusal
  SL4: +smugjobs from a non-board room returns the cantina/docking-bay refusal

Bug FIXED (2026-06-12): `_in_board_room` (parser/smuggling_commands.py) was
reading `ctx.session.current_room`, which was never assigned anywhere in the
codebase; now reads room from DB via `ctx.db.get_room(char["room_id"])`.
All four arms are live passing tests.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import smuggling_loop


pytestmark = pytest.mark.smoke


class TestSmugglingLoop:
    """Smuggling board → accept → active-run display → deliver-refusal gate."""

    async def test_sl1_board_renders_in_cantina(self, harness):
        await smuggling_loop.sl1_board_renders_in_cantina(harness)

    async def test_sl2_accept_and_view_active_run(self, harness):
        await smuggling_loop.sl2_accept_and_view_active_run(harness)

    async def test_sl3_deliver_refusal_not_docked(self, harness):
        await smuggling_loop.sl3_deliver_refusal_not_docked(harness)

    async def test_sl4_board_refused_outside_eligible_room(self, harness):
        await smuggling_loop.sl4_board_refused_outside_eligible_room(harness)
