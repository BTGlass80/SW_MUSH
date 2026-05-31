# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_npc_dialogue.py — Pytest entry points for the
NPC `talk` smoke scenarios (NPC-T-1, NPC-T-2, NPC-T-3).

End-to-end verification of the `talk` parser surface through the
AI-offline graceful-degradation path. Unit coverage of the brain
fallback and parser components lives in
`tests/test_npc_dialogue_cleanup.py`.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import npc_dialogue


pytestmark = pytest.mark.smoke


class TestNpcDialogue:
    """`talk <npc>` — end-to-end live-harness scenarios."""

    async def test_npc_t_1_talk_succeeds_with_fallback(self, harness):
        await npc_dialogue.npc_t_1_talk_succeeds_with_fallback(harness)

    async def test_npc_t_2_no_arg_lists_npcs(self, harness):
        await npc_dialogue.npc_t_2_no_arg_lists_npcs(harness)

    async def test_npc_t_3_unknown_npc_clean_error(self, harness):
        await npc_dialogue.npc_t_3_unknown_npc_clean_error(harness)
