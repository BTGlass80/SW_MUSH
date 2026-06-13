# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_smuggling_loop.py — Pytest entry points for SL1-SL4.

Exercises the SMUGGLING job loop end-to-end:
  SL1: +smugjobs board renders in a board-eligible room
  SL2: smugaccept <id> → job ACCEPTED → +smugjob shows active run
  SL3: smugdeliver from a non-docked state returns the docked-ship refusal
  SL4: +smugjobs from a non-board room returns the cantina/docking-bay refusal

CONFIRMED PRODUCTION BUG → SL1/SL2/SL4 are xfail (see the scenarios module
docstring): `_in_board_room` (parser/smuggling_commands.py:38) reads
`ctx.session.current_room`, which is never assigned anywhere in the codebase,
so every `+smugjobs` / `smugaccept` errors and the board is unreachable in the
live server. These three arms are driven FAITHFULLY (no workaround) and will
XPASS the moment the wiring is fixed — at which point remove the xfail marks.
SL3 is independent of the bug (no `_in_board_room` call) and is a real pass.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import smuggling_loop


pytestmark = pytest.mark.smoke

_BUG = (
    "Smuggling board unreachable in the live server: _in_board_room reads "
    "ctx.session.current_room, which is never assigned (parser/"
    "smuggling_commands.py:38). Remove this xfail when current_room is wired."
)


class TestSmugglingLoop:
    """Smuggling board → accept → active-run display → deliver-refusal gate."""

    @pytest.mark.xfail(reason=_BUG, strict=False)
    async def test_sl1_board_renders_in_cantina(self, harness):
        await smuggling_loop.sl1_board_renders_in_cantina(harness)

    @pytest.mark.xfail(reason=_BUG, strict=False)
    async def test_sl2_accept_and_view_active_run(self, harness):
        await smuggling_loop.sl2_accept_and_view_active_run(harness)

    async def test_sl3_deliver_refusal_not_docked(self, harness):
        await smuggling_loop.sl3_deliver_refusal_not_docked(harness)

    @pytest.mark.xfail(reason=_BUG, strict=False)
    async def test_sl4_board_refused_outside_eligible_room(self, harness):
        await smuggling_loop.sl4_board_refused_outside_eligible_room(harness)
