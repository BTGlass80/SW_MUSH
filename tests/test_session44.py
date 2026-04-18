# -*- coding: utf-8 -*-
"""
tests/test_session44.py — Session 44 Tests

Tests for:
  1. +char command suite (char_commands.py)
       - Module imports, command key/aliases
       - +char/list renders account characters
       - +char/switch sets CHAR_SWITCH state, saves character position
       - +char/delete flow: validation, pending state, confirm
       - Edge cases: only-char block, active-char block, unknown name
  2. Same-faction alt prevention (engine/organizations.py)
       - join_faction blocks when a sibling char is in the same faction
       - join_faction allows when no sibling is in that faction
       - join_faction allows independent alts
  3. Self-trade blocking (parser/builtin_commands.py)
       - TradeCommand source contains account_id comparison guards
       - Both item and credit paths have the guard
  4. WebSocket resize-on-connect (static/client.html)
       - ws.onopen sends a resize message
       - Probe span used to measure char width
  5. wrap_width cap (server/session.py)
       - WebSocket sessions allow up to 100 chars
       - Telnet sessions stay at 80 chars
  6. CHAR_SWITCH SessionState (server/session.py)
       - CHAR_SWITCH value present in SessionState
  7. game_server.py loop structure
       - CHAR_SWITCH handled in handle_new_session loop
"""

import json
import inspect
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# 1. char_commands.py — module structure
# ═══════════════════════════════════════════════════════════════════════

class TestCharCommandModule:

    def test_module_imports_cleanly(self):
        from parser.char_commands import CharCommand, register_char_commands
        assert callable(register_char_commands)

    def test_command_key(self):
        from parser.char_commands import CharCommand
        cmd = CharCommand()
        assert cmd.key == "+char"

    def test_command_aliases(self):
        from parser.char_commands import CharCommand
        cmd = CharCommand()
        assert "+character" in cmd.aliases
        assert "charswitch" in cmd.aliases

    def test_has_all_subcommands(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand)
        assert "_list" in src
        assert "_switch" in src
        assert "_delete" in src
        assert "_confirm_delete" in src

    def test_register_adds_command(self):
        from parser.char_commands import register_char_commands
        from parser.commands import CommandRegistry
        reg = CommandRegistry()
        register_char_commands(reg)
        # Should be findable by key
        result = reg.get("+char")
        assert result is not None

    def test_list_subcommand_queries_account(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._list)
        assert "get_characters" in src
        assert "account" in src

    def test_switch_sets_char_switch_state(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._switch)
        assert "CHAR_SWITCH" in src
        assert "session.state" in src

    def test_switch_clears_character(self):
        """_switch saves position before clearing."""
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._switch)
        assert "save_character" in src

    def test_switch_blocked_for_single_char(self):
        """_switch should block if account has only one character."""
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._switch)
        assert "only one character" in src or "only have one" in src

    def test_delete_requires_name(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._delete)
        assert "not name" in src or "if not name" in src

    def test_delete_blocked_for_last_char(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._delete)
        assert "only character" in src or "only one" in src

    def test_delete_blocked_for_active_char(self):
        """Cannot delete the currently active character."""
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._delete)
        assert "currently active" in src

    def test_delete_sets_pending_state(self):
        from parser.char_commands import CharCommand, _pending_deletes
        src = inspect.getsource(CharCommand._delete)
        assert "_pending_deletes" in src

    def test_confirm_pops_pending_state(self):
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._confirm_delete)
        assert "_pending_deletes.pop" in src

    def test_confirm_soft_deletes(self):
        """Confirm sets is_active=0, not hard-deletes."""
        from parser.char_commands import CharCommand
        src = inspect.getsource(CharCommand._confirm_delete)
        assert "is_active=0" in src or "is_active, 0" in src

    def test_pending_deletes_dict_exists(self):
        from parser.char_commands import _pending_deletes
        assert isinstance(_pending_deletes, dict)

    def test_switch_async(self):
        from parser.char_commands import CharCommand
        assert asyncio.iscoroutinefunction(CharCommand._switch)

    def test_delete_async(self):
        from parser.char_commands import CharCommand
        assert asyncio.iscoroutinefunction(CharCommand._delete)

    def test_list_async(self):
        from parser.char_commands import CharCommand
        assert asyncio.iscoroutinefunction(CharCommand._list)


# ═══════════════════════════════════════════════════════════════════════
# 2. Same-faction alt prevention
# ═══════════════════════════════════════════════════════════════════════

class TestSameFactionAltPrevention:

    def test_join_faction_checks_siblings(self):
        """join_faction source must check sibling characters' faction_id."""
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        assert "get_characters" in src, \
            "join_faction must call db.get_characters to check siblings"
        assert "account_id" in src, \
            "join_faction must use account_id to fetch siblings"
        assert "sibling" in src, \
            "join_faction must iterate siblings"

    def test_join_faction_blocks_same_faction_alt(self):
        """join_faction must return False when sibling already in faction."""
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        assert "Two alts may not share" in src or \
               "same faction" in src.lower() or \
               "already in" in src, \
            "join_faction must have a blocking message for same-faction alts"

    def test_same_faction_check_has_try_except(self):
        """Same-faction check must be wrapped in try/except per invariant."""
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        # Find the same-faction block
        idx = src.find("get_characters(account_id)")
        assert idx != -1
        # The except clause is up to 600 chars after the try block
        section = src[max(0, idx - 100): idx + 700]
        assert "except Exception" in section or "except" in section, \
            "Same-faction check must have try/except"

    def test_same_faction_check_skips_self(self):
        """Must skip the character being checked (same char ID)."""
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        assert "sibling[\"id\"] == char[\"id\"]" in src or \
               "sibling['id'] == char['id']" in src, \
            "join_faction must skip the character's own record"

    def test_join_faction_blocks_async(self):
        """join_faction is a coroutine."""
        from engine.organizations import join_faction
        assert asyncio.iscoroutinefunction(join_faction)

    def test_same_faction_check_only_for_known_account(self):
        """Check must be conditional on account_id being set."""
        from engine.organizations import join_faction
        src = inspect.getsource(join_faction)
        assert "if account_id" in src, \
            "Same-faction check must be gated on account_id being truthy"

    def test_join_faction_blocks_simulated(self):
        """Simulate the same-faction alt block with mock objects."""
        async def _run():
            from engine.organizations import join_faction

            calls = []

            class MockDB:
                async def get_organization(self, code):
                    if code == "rebel":
                        return {"id": 10, "name": "Rebel Alliance",
                                "org_type": "faction"}
                    return None

                async def get_membership(self, char_id, org_id):
                    return None  # Not already a member

                async def get_characters(self, account_id):
                    # Return sibling already in rebel faction
                    return [
                        {"id": 1, "name": "MainChar",
                         "faction_id": "independent"},
                        {"id": 2, "name": "AltChar",
                         "faction_id": "rebel"},  # <-- conflict
                    ]

            char = {
                "id": 1,
                "name": "MainChar",
                "faction_id": "independent",
                "account_id": 42,
                "attributes": "{}",
            }

            ok, msg = await join_faction(char, "rebel", MockDB())
            assert ok is False, f"Should block same-faction alt, got ok={ok}: {msg}"
            assert "alt" in msg.lower() or "faction" in msg.lower(), \
                f"Block message should mention alt/faction: {msg}"

        asyncio.get_event_loop().run_until_complete(_run())

    def test_join_faction_allows_different_faction(self):
        """Different factions on alts should be allowed."""
        async def _run():
            from engine.organizations import join_faction
            import time

            class MockDB:
                async def get_organization(self, code):
                    if code == "empire":
                        return {"id": 20, "name": "Galactic Empire",
                                "org_type": "faction"}
                    return None

                async def get_membership(self, char_id, org_id):
                    return None

                async def get_characters(self, account_id):
                    return [
                        {"id": 1, "name": "MainChar",
                         "faction_id": "rebel"},   # rebel on char 1
                        {"id": 3, "name": "AltChar2",
                         "faction_id": "independent"},
                    ]

                async def join_organization(self, *a, **k): pass
                async def save_character(self, *a, **k): pass
                async def log_faction_action(self, *a, **k): pass
                async def get_rank(self, *a, **k): return None
                async def get_issued_equipment(self, *a, **k): return []
                async def issue_equipment(self, *a, **k): return 1

            char = {
                "id": 3, "name": "AltChar2",
                "faction_id": "independent",
                "account_id": 42,
                "attributes": "{}",
                "credits": 0,
            }

            # empire is not rebel — should pass the alt check
            # (may fail later for other mock reasons — we just check it
            #  doesn't fail at the same-faction check)
            ok, msg = await join_faction(char, "empire", MockDB())
            # The only "same faction" fail message mentions "alt"
            assert "alt" not in msg.lower() or ok is True, \
                f"Should not block different-faction alt: {msg}"

        asyncio.get_event_loop().run_until_complete(_run())


# ═══════════════════════════════════════════════════════════════════════
# 3. Self-trade blocking
# ═══════════════════════════════════════════════════════════════════════

class TestSelfTradeBlocking:

    def test_trade_offer_item_path_has_account_check(self):
        """Item trade path must compare account_id before creating offer."""
        from parser.builtin_commands import TradeCommand
        src = inspect.getsource(TradeCommand._offer)
        # Ensure account_id comparison is present
        assert "account_id" in src, \
            "TradeCommand._offer must check account_id for self-trade"

    def test_trade_offer_credit_path_has_account_check(self):
        """Credit trade path must also compare account_id."""
        from parser.builtin_commands import TradeCommand
        src = inspect.getsource(TradeCommand._offer)
        # Should appear twice — once for each path
        count = src.count("own_account == tgt_account")
        assert count >= 2, \
            f"Both item and credit paths need the account check; found {count}"

    def test_trade_block_message_mentions_alts(self):
        """Block message must mention alternate characters."""
        from parser.builtin_commands import TradeCommand
        src = inspect.getsource(TradeCommand._offer)
        assert "alternate characters" in src or "alts" in src.lower(), \
            "Self-trade block message must mention alt characters"

    def test_trade_block_returns_early(self):
        """Self-trade check must return early (not proceed to offer)."""
        from parser.builtin_commands import TradeCommand
        src = inspect.getsource(TradeCommand._offer)
        # The return should come right after the block message
        assert "TRADE BLOCKED" in src, \
            "Must display [TRADE BLOCKED] message"

    def test_trade_block_safe_on_missing_account(self):
        """Block must be safe when account is None (no crash)."""
        from parser.builtin_commands import TradeCommand
        src = inspect.getsource(TradeCommand._offer)
        # Should guard: ctx.session.account["id"] if ctx.session.account else None
        assert "if ctx.session.account" in src or \
               "session.account[" in src, \
            "Self-trade check must handle None account safely"


# ═══════════════════════════════════════════════════════════════════════
# 4. WebSocket resize-on-connect
# ═══════════════════════════════════════════════════════════════════════

class TestWebSocketResize:

    @pytest.fixture(scope="class")
    def client_src(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "static", "client.html",
        )
        with open(path) as f:
            return f.read()

    def test_ws_onopen_sends_resize(self, client_src):
        """ws.onopen must send a resize message."""
        import re
        m = re.search(
            r"ws\.onopen\s*=\s*function\(\)\s*\{(.*?)^\s*\};",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m, "ws.onopen function not found"
        body = m.group(1)
        assert "resize" in body, \
            "ws.onopen must send a resize message"
        assert "ws.send" in body, \
            "ws.onopen must call ws.send with the resize"

    def test_resize_includes_width(self, client_src):
        """Resize message must include a width field."""
        assert '"resize"' in client_src or "'resize'" in client_src
        assert "width" in client_src

    def test_resize_uses_probe_span(self, client_src):
        """Must use a probe element to measure monospace char width."""
        import re
        m = re.search(
            r"ws\.onopen\s*=\s*function\(\)\s*\{(.*?)^\s*\};",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert "probe" in body, \
            "ws.onopen should use a probe element for char width measurement"
        assert "font-mono" in body or "font-family" in body.lower(), \
            "Probe must use monospace font"

    def test_resize_clamps_width(self, client_src):
        """Width must be clamped to a sane range."""
        import re
        m = re.search(
            r"ws\.onopen\s*=\s*function\(\)\s*\{(.*?)^\s*\};",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert "Math.min" in body or "Math.max" in body, \
            "Width must be clamped with Math.min/max"

    def test_resize_nonfatal_try_catch(self, client_src):
        """Resize send must be wrapped in try/catch (non-fatal)."""
        import re
        m = re.search(
            r"ws\.onopen\s*=\s*function\(\)\s*\{(.*?)^\s*\};",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert "try" in body and "catch" in body, \
            "Resize must be in a try/catch so it never blocks login"


# ═══════════════════════════════════════════════════════════════════════
# 5. wrap_width cap (server/session.py)
# ═══════════════════════════════════════════════════════════════════════

class TestWrapWidthCap:

    def test_websocket_allows_up_to_100(self):
        """WebSocket wrap_width must allow up to 100 chars."""
        from server.session import Session, Protocol
        s = Session.__new__(Session)
        s.protocol = Protocol.WEBSOCKET
        s.width = 120
        assert s.wrap_width == 100, \
            f"WebSocket wrap_width should cap at 100, got {s.wrap_width}"

    def test_websocket_respects_narrow_width(self):
        """WebSocket wrap_width must honour actual width when below cap."""
        from server.session import Session, Protocol
        s = Session.__new__(Session)
        s.protocol = Protocol.WEBSOCKET
        s.width = 80
        assert s.wrap_width == 80, \
            f"WebSocket wrap_width should be 80 for width=80, got {s.wrap_width}"

    def test_telnet_stays_at_80(self):
        """Telnet wrap_width must still cap at 80."""
        from server.session import Session, Protocol
        s = Session.__new__(Session)
        s.protocol = Protocol.TELNET
        s.width = 120
        assert s.wrap_width == 80, \
            f"Telnet wrap_width should cap at 80, got {s.wrap_width}"

    def test_telnet_narrow(self):
        """Telnet respects narrower actual width."""
        from server.session import Session, Protocol
        s = Session.__new__(Session)
        s.protocol = Protocol.TELNET
        s.width = 60
        assert s.wrap_width == 60


# ═══════════════════════════════════════════════════════════════════════
# 6. CHAR_SWITCH SessionState
# ═══════════════════════════════════════════════════════════════════════

class TestCharSwitchState:

    def test_char_switch_in_session_state(self):
        """CHAR_SWITCH must be a member of SessionState."""
        from server.session import SessionState
        assert hasattr(SessionState, "CHAR_SWITCH"), \
            "SessionState must have CHAR_SWITCH value"

    def test_char_switch_value(self):
        """CHAR_SWITCH value must be a non-empty string."""
        from server.session import SessionState
        assert SessionState.CHAR_SWITCH.value, \
            "CHAR_SWITCH must have a non-empty string value"

    def test_char_switch_distinct_from_others(self):
        """CHAR_SWITCH must be distinct from IN_GAME, AUTHENTICATED, etc."""
        from server.session import SessionState
        other_values = {
            SessionState.CONNECTED.value,
            SessionState.AUTHENTICATED.value,
            SessionState.IN_GAME.value,
            SessionState.DISCONNECTING.value,
        }
        assert SessionState.CHAR_SWITCH.value not in other_values


# ═══════════════════════════════════════════════════════════════════════
# 7. game_server.py loop structure
# ═══════════════════════════════════════════════════════════════════════

class TestGameServerLoop:

    def test_char_switch_import_in_game_server(self):
        """game_server must import register_char_commands."""
        import server.game_server as gs
        src = inspect.getsource(gs)
        assert "register_char_commands" in src, \
            "game_server must import and register char_commands"

    def test_char_switch_registered(self):
        """register_char_commands must be called in GameServer.__init__."""
        import server.game_server as gs
        src = inspect.getsource(gs.GameServer.__init__)
        assert "register_char_commands" in src, \
            "GameServer.__init__ must call register_char_commands"

    def test_handle_new_session_loops_on_char_switch(self):
        """handle_new_session must loop back to char select on CHAR_SWITCH."""
        import server.game_server as gs
        src = inspect.getsource(gs.GameServer.handle_new_session)
        assert "CHAR_SWITCH" in src, \
            "handle_new_session must handle CHAR_SWITCH state"
        assert "while" in src, \
            "handle_new_session must use a while loop for char switching"

    def test_char_switch_resets_character(self):
        """Loop must clear session.character on CHAR_SWITCH."""
        import server.game_server as gs
        src = inspect.getsource(gs.GameServer.handle_new_session)
        assert "session.character = None" in src, \
            "handle_new_session must clear session.character on CHAR_SWITCH"

    def test_char_switch_resets_state(self):
        """Loop must reset state to AUTHENTICATED before char select."""
        import server.game_server as gs
        src = inspect.getsource(gs.GameServer.handle_new_session)
        assert "SessionState.AUTHENTICATED" in src, \
            "handle_new_session must reset to AUTHENTICATED on CHAR_SWITCH"
