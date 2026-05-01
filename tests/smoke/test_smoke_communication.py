# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_communication.py — Pytest entry points for C1-C8.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import communication


pytestmark = pytest.mark.smoke


class TestCommunication:
    """Say, pose, emote, whisper, page, OOC, dice, finger."""

    async def test_c1_say_local_broadcast(self, harness):
        await communication.c1_say_local_broadcast(harness)

    async def test_c2_pose_local_broadcast(self, harness):
        await communication.c2_pose_local_broadcast(harness)

    async def test_c3_emote_command(self, harness):
        await communication.c3_emote_command(harness)

    async def test_c4_whisper_targeted(self, harness):
        await communication.c4_whisper_targeted(harness)

    async def test_c5_page_cross_room(self, harness):
        await communication.c5_page_cross_room(harness)

    async def test_c6_ooc_channel(self, harness):
        await communication.c6_ooc_channel(harness)

    async def test_c7_roll_dice(self, harness):
        await communication.c7_roll_dice(harness)

    async def test_c8_finger_lookup(self, harness):
        await communication.c8_finger_lookup(harness)
