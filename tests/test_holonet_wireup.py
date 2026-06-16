# -*- coding: utf-8 -*-
"""
tests/test_holonet_wireup.py — +holonet wire-up (GAME-1 / audit §B)

Tests:
  1. TestHolonetCommand  — parser registers +holonet; WS session receives
                           holonet_state with world_events field
  2. TestQ1Fix           — no canonical Mace Windu strings in HOLONET_DATA_FIXTURE
  3. TestClientHandling  — client.html has handleHolonetState + dispatch case
  4. TestTelnetFallback  — Telnet sessions get a text-only notice, no crash
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _client_html() -> str:
    return (PROJECT_ROOT / "static" / "client.html").read_text(encoding="utf-8")

def _m3_holonet_js() -> str:
    return (PROJECT_ROOT / "static" / "spa" / "m3_holonet.js").read_text(encoding="utf-8")


# ── 1. Parser command ─────────────────────────────────────────────────────────

class TestHolonetCommand(unittest.IsolatedAsyncioTestCase):

    def test_holonet_command_registered(self):
        from parser.commands import CommandRegistry
        from parser.news_commands import register_news_commands
        reg = CommandRegistry()
        register_news_commands(reg)
        cmd = reg.get("+holonet")
        self.assertIsNotNone(cmd, "+holonet must be registered")

    def test_holonet_alias_registered(self):
        from parser.commands import CommandRegistry
        from parser.news_commands import register_news_commands
        reg = CommandRegistry()
        register_news_commands(reg)
        cmd = reg.get("holonet")
        self.assertIsNotNone(cmd, "'holonet' alias must resolve")

    async def test_holonet_ws_sends_holonet_state(self):
        from parser.news_commands import HolonetCommand
        from server.session import Protocol

        sent = {}
        session = MagicMock()
        session.protocol = Protocol.WEBSOCKET
        session.send_json = AsyncMock(side_effect=lambda t, d: sent.update({"type": t, "data": d}))

        ctx = MagicMock()
        ctx.session = session
        ctx.args = ""

        fake_status = [{"type": "KRAYT_SIGHTING", "name": "Krayt Dragon", "zones": ["dune_sea"],
                         "remaining_minutes": 30, "effects": {}, "headline": "Test"}]
        with patch("engine.world_events.get_world_event_manager") as mgr_fn:
            mgr_fn.return_value.get_status.return_value = fake_status
            await HolonetCommand().execute(ctx)

        self.assertEqual(sent.get("type"), "holonet_state")
        events = sent["data"].get("world_events", [])
        self.assertIsInstance(events, list)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["name"], "Krayt Dragon")

    async def test_holonet_ws_sends_empty_events_on_error(self):
        """Engine error → sends holonet_state with empty world_events, no crash."""
        from parser.news_commands import HolonetCommand
        from server.session import Protocol

        sent = {}
        session = MagicMock()
        session.protocol = Protocol.WEBSOCKET
        session.send_json = AsyncMock(side_effect=lambda t, d: sent.update({"type": t, "data": d}))

        ctx = MagicMock()
        ctx.session = session
        ctx.args = ""

        with patch("engine.world_events.get_world_event_manager", side_effect=Exception("boom")):
            await HolonetCommand().execute(ctx)

        self.assertEqual(sent.get("type"), "holonet_state")
        self.assertEqual(sent["data"]["world_events"], [])


# ── 2. Q1 canonical-character fix ────────────────────────────────────────────

class TestQ1Fix(unittest.TestCase):
    """No Mace Windu / M. Windu strings in m3_holonet.js fixture data."""

    def setUp(self):
        self.js = _m3_holonet_js()
        # Strip comment block (first 70 lines) — check in fixture/code only
        self.code = '\n'.join(self.js.split('\n')[70:])

    def test_no_mace_windu_in_data_fixture(self):
        self.assertNotIn('Mace Windu', self.code)

    def test_no_m_windu_abbreviation_in_data_fixture(self):
        self.assertNotIn('M. Windu', self.code)

    def test_replacement_present(self):
        # The replacement text should appear
        self.assertIn('Jedi command en route', self.code)

    def test_faction_movement_replacement(self):
        self.assertIn('Jedi Vanguard deployed', self.code)


# ── 3. Client DOM / JS ───────────────────────────────────────────────────────

class TestClientHandling(unittest.TestCase):

    def setUp(self):
        self.html = _client_html()

    def test_holonet_state_dispatch_case(self):
        self.assertIn("case 'holonet_state'", self.html)

    def test_handle_holonet_state_function(self):
        self.assertIn('function handleHolonetState(', self.html)

    def test_handler_calls_m3holonet(self):
        self.assertIn('M3Holonet.buildHolonetBrowserModal', self.html)

    def test_handler_removes_existing_modal(self):
        self.assertIn('data-holonet-browser="modal"', self.html)

    def test_handler_uses_fixture_data(self):
        self.assertIn('HOLONET_DATA_FIXTURE', self.html)

    def test_handler_merges_live_events(self):
        self.assertIn('world_events', self.html)

    def test_handler_close_function(self):
        self.assertIn('closeHolonet', self.html)


# ── 4. Telnet fallback ───────────────────────────────────────────────────────

class TestTelnetFallback(unittest.IsolatedAsyncioTestCase):

    async def test_telnet_sends_text_notice(self):
        from parser.news_commands import HolonetCommand
        from server.session import Protocol

        lines_sent = []
        session = MagicMock()
        session.protocol = Protocol.TELNET
        session.send_line = AsyncMock(side_effect=lambda t: lines_sent.append(t))

        ctx = MagicMock()
        ctx.session = session
        ctx.args = ""

        await HolonetCommand().execute(ctx)

        self.assertTrue(any(lines_sent), "Telnet must receive at least one line")
        # Must not crash
        session.send_json.assert_not_called()


if __name__ == "__main__":
    unittest.main()
