"""
Tests for MSSP (Mud Server Status Protocol) telnet option support.

MSSP (option 70) lets listing crawlers (MudVerse, MUDStats, Grapevine) auto-index
the game.  Verifies: payload framing, key-value encoding, fail-open transport
injection, and the required-field roster.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock

from server.telnet_handler import (
    TelnetHandler,
    _IAC, _SB, _SE, _WILL, _MSSP_OPT, _MSSP_VAR, _MSSP_VAL,
)


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_handler(game_name="Test Game", telnet_port=4000, player_count=0):
    game = MagicMock()
    game.config.game_name = game_name
    game.config.telnet_port = telnet_port
    game.session_mgr.count = player_count
    return TelnetHandler(game)


def _parse_mssp(payload: bytes) -> dict:
    """Parse MSSP key-value pairs from a _build_mssp_payload() result."""
    header = bytes([_IAC, _WILL, _MSSP_OPT, _IAC, _SB, _MSSP_OPT])
    footer = bytes([_IAC, _SE])
    assert payload[:len(header)] == header, "bad MSSP header"
    assert payload[-len(footer):] == footer, "bad MSSP footer"
    body = payload[len(header) : -len(footer)]

    result: dict = {}
    i = 0
    while i < len(body):
        if body[i] != _MSSP_VAR:
            break
        i += 1
        key_end = body.index(_MSSP_VAL, i)
        key = body[i:key_end].decode("utf-8")
        i = key_end + 1
        # value ends at next MSSP_VAR marker or end of body
        val_end = i
        while val_end < len(body) and body[val_end] != _MSSP_VAR:
            val_end += 1
        result[key] = body[i:val_end].decode("utf-8")
        i = val_end
    return result


# ── payload structure ─────────────────────────────────────────────────────────

class TestMSSPPayloadStructure:
    def test_returns_bytes(self):
        assert isinstance(_make_handler()._build_mssp_payload(), bytes)

    def test_header_iac_will_mssp(self):
        p = _make_handler()._build_mssp_payload()
        assert p[0] == _IAC
        assert p[1] == _WILL
        assert p[2] == _MSSP_OPT

    def test_sb_mssp_follows_will(self):
        p = _make_handler()._build_mssp_payload()
        assert p[3] == _IAC
        assert p[4] == _SB
        assert p[5] == _MSSP_OPT

    def test_ends_with_iac_se(self):
        p = _make_handler()._build_mssp_payload()
        assert p[-2] == _IAC
        assert p[-1] == _SE

    def test_minimum_length(self):
        # 3 (WILL) + 3 (SB) + at least one kv pair + 2 (SE) > 20
        p = _make_handler()._build_mssp_payload()
        assert len(p) > 20


# ── key-value encoding ────────────────────────────────────────────────────────

class TestMSSPKeyValues:
    def test_name_matches_config(self):
        pairs = _parse_mssp(_make_handler(game_name="Phantom Sector").
                            _build_mssp_payload())
        assert pairs["NAME"] == "Phantom Sector"

    def test_players_is_integer_and_correct(self):
        pairs = _parse_mssp(_make_handler(player_count=5)._build_mssp_payload())
        assert pairs["PLAYERS"].isdigit()
        assert int(pairs["PLAYERS"]) == 5

    def test_players_zero_when_empty(self):
        pairs = _parse_mssp(_make_handler(player_count=0)._build_mssp_payload())
        assert pairs["PLAYERS"] == "0"

    def test_uptime_is_integer(self):
        pairs = _parse_mssp(_make_handler()._build_mssp_payload())
        assert pairs["UPTIME"].isdigit()
        assert int(pairs["UPTIME"]) > 0

    def test_port_matches_config(self):
        pairs = _parse_mssp(_make_handler(telnet_port=4567)._build_mssp_payload())
        assert pairs["PORT"] == "4567"

    def test_required_fields_all_present(self):
        pairs = _parse_mssp(_make_handler()._build_mssp_payload())
        required = ("NAME", "PLAYERS", "UPTIME", "PORT", "STATUS", "CODEBASE",
                    "LANGUAGE", "CRAWL DELAY")
        for key in required:
            assert key in pairs, f"Required MSSP field missing: {key}"

    def test_no_iac_byte_in_body(self):
        """Body must not contain raw IAC (0xFF) — would corrupt telnet framing."""
        p = _make_handler(game_name="Safe Name")._build_mssp_payload()
        body = p[6:-2]  # strip 6-byte header and 2-byte SE footer
        assert 255 not in body, "IAC byte in MSSP body corrupts telnet framing"

    def test_crawl_delay_is_numeric(self):
        pairs = _parse_mssp(_make_handler()._build_mssp_payload())
        assert pairs["CRAWL DELAY"].isdigit()


# ── transport injection ───────────────────────────────────────────────────────

class TestMSSPTransportInjection:
    @pytest.mark.asyncio
    async def test_shell_writes_mssp_to_transport(self):
        """_shell() writes MSSP bytes to writer._transport before the session."""
        transport = MagicMock()
        writer = MagicMock()
        writer._transport = transport
        writer.get_extra_info = MagicMock(return_value=None)
        writer.drain = AsyncMock()
        writer.close = MagicMock()

        reader = MagicMock()

        game = MagicMock()
        game.config.game_name = "Test"
        game.config.telnet_port = 4000
        game.session_mgr.count = 0
        game.session_mgr.add = MagicMock()
        game.session_mgr.remove = MagicMock()
        game.handle_new_session = AsyncMock()

        handler = TelnetHandler(game)
        await handler._shell(reader, writer)

        assert transport.write.called
        written = transport.write.call_args[0][0]
        assert isinstance(written, bytes)
        assert written[0] == _IAC
        assert written[1] == _WILL
        assert written[2] == _MSSP_OPT

    @pytest.mark.asyncio
    async def test_shell_continues_on_mssp_failure(self):
        """Transport.write failure must not abort the session."""
        transport = MagicMock()
        transport.write.side_effect = RuntimeError("transport closed")
        writer = MagicMock()
        writer._transport = transport
        writer.get_extra_info = MagicMock(return_value=None)
        writer.drain = AsyncMock()
        writer.close = MagicMock()

        reader = MagicMock()

        game = MagicMock()
        game.config.game_name = "Test"
        game.config.telnet_port = 4000
        game.session_mgr.count = 0
        game.session_mgr.add = MagicMock()
        game.session_mgr.remove = MagicMock()
        game.handle_new_session = AsyncMock()

        handler = TelnetHandler(game)
        # Should not raise despite the transport error
        await handler._shell(reader, writer)
        # Session was still added and removed (full session lifecycle)
        game.session_mgr.add.assert_called_once()
        game.handle_new_session.assert_called_once()
