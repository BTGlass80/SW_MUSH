# -*- coding: utf-8 -*-
"""
tests/smoke/test_smoke_telnet.py — Pytest entry points for SH3 Telnet
protocol scenarios (T1-T5) and the F3 Telnet chargen check.

Class-scoped harness: each class boots its own GameServer + temp
SQLite (per design §9 Brian's choice). The Telnet flavor uses the
same in-process boot path as WebSocket — only the per-session
``protocol`` kwarg + send_callback differ.
"""
from __future__ import annotations

import pytest

from tests.smoke.scenarios import telnet_protocol, foundation_telnet


pytestmark = pytest.mark.smoke


class TestTelnetProtocol:
    """Telnet protocol scenarios — sanity checks that core flows
    work identically across the two protocols."""

    async def test_t1_telnet_login_and_look(self, harness):
        await telnet_protocol.t1_telnet_login_and_look(harness)

    async def test_t2_telnet_movement(self, harness):
        await telnet_protocol.t2_telnet_movement(harness)

    async def test_t3_telnet_say_renders_as_text(self, harness):
        await telnet_protocol.t3_telnet_say_renders_as_text(harness)

    async def test_t4_telnet_sheet_renders_as_text(self, harness):
        await telnet_protocol.t4_telnet_sheet_renders_as_text(harness)

    async def test_t5_telnet_combat_text_fallback(self, harness):
        await telnet_protocol.t5_telnet_combat_text_fallback(harness)


class TestTelnetChargen:
    """F3 — the previously-skipped Telnet chargen wizard."""

    async def test_f3_telnet_wizard_intro(self, harness):
        await foundation_telnet.f3_telnet_wizard_intro(harness)
