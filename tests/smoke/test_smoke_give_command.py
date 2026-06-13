# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_give_command.py — Pytest entry points for the
`give` command end-to-end scenarios (GV-1 … GV-5).

`give <item> to <player-or-NPC>` is a one-way item hand-off, authored
2026-06-12 alongside the tutorial-chain fixes (the Smuggler chain's
"give crate to Dyn" step had no producing command). Credits route
through `trade` (consented + 5% tax sink); `give` is items only.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import give_command


pytestmark = pytest.mark.smoke


class TestGiveCommand:
    """`give` — end-to-end live-harness scenarios."""

    async def test_gv_1_give_item_to_player(self, harness):
        await give_command.gv_1_give_item_to_player(harness)

    async def test_gv_2_credits_redirect_to_trade(self, harness):
        await give_command.gv_2_credits_redirect_to_trade(harness)

    async def test_gv_3_give_to_self_refused(self, harness):
        await give_command.gv_3_give_to_self_refused(harness)

    async def test_gv_4_give_to_absent_target(self, harness):
        await give_command.gv_4_give_to_absent_target(harness)

    async def test_gv_5_give_item_to_npc(self, harness):
        await give_command.gv_5_give_item_to_npc(harness)
