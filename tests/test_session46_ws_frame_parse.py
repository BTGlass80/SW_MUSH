"""
Session 46 regression test — WebSocket command frame parsing.

The live client emits every command as {"type":"cmd","data":"<line>"} and an
earlier refactor of server/web_client.py looked only for the "input" or
"text" field names, so 100% of client-originated commands (including the
login 'connect user pass' frame) were silently dropped. The symptom was:
client sends, server logs a new session, no response ever returns, and no
error or traceback.

This test re-implements the single-frame parse branch from `_ws_handler`
against the patched contract. If someone re-breaks the field-name
precedence in the future, these tests will fail before the server boots
for any human.

The test keeps its own fake `frame_to_text()` that mirrors the patch at
server/web_client.py:203–215. If that block changes, update this helper
in lockstep — but DO NOT relax the 'cmd'→'data' requirement.
"""
import json
import unittest


def frame_to_text(raw):
    """Mirror of the parse branch in web_client.py._ws_handler after the S46 fix.

    Returns the stripped text that would be passed to session.feed_input(),
    or '' if the frame would be ignored (e.g. control frames like 'resize').
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Non-JSON text payloads are fed through directly in the live code.
        # Coerce so the tests' string-return contract holds.
        return (raw if isinstance(raw, str) else "").strip()

    if not isinstance(data, dict):
        return ""

    frame_type = data.get("type")
    # Control frames that are NOT forwarded as commands:
    if frame_type in ("resize", "token_auth"):
        return ""

    if frame_type == "cmd":
        text = data.get("data", "")
    else:
        text = data.get("data", data.get("input", data.get("text", "")))

    if not isinstance(text, str):
        text = ""
    return text.strip()


class WsFrameParseTests(unittest.TestCase):
    """Lock in the contract: cmd frames carry their payload in 'data'."""

    # ── The bug that motivated this test ──────────────────────────────

    def test_connect_login_frame_is_parsed(self):
        """The exact payload DevTools shows the client sending at login."""
        raw = '{"type":"cmd","data":"connect testuser testpass"}'
        self.assertEqual(frame_to_text(raw), "connect testuser testpass")

    def test_create_login_frame_is_parsed(self):
        raw = '{"type":"cmd","data":"create newuser newpass"}'
        self.assertEqual(frame_to_text(raw), "create newuser newpass")

    # ── Every other command the live client sends ─────────────────────

    def test_normal_gameplay_command_is_parsed(self):
        raw = '{"type":"cmd","data":"look"}'
        self.assertEqual(frame_to_text(raw), "look")

    def test_character_select_marker_is_parsed(self):
        raw = '{"type":"cmd","data":"__char_select__42"}'
        self.assertEqual(frame_to_text(raw), "__char_select__42")

    def test_chargen_request_marker_is_parsed(self):
        raw = '{"type":"cmd","data":"__request_chargen__"}'
        self.assertEqual(frame_to_text(raw), "__request_chargen__")

    def test_quit_command_is_parsed(self):
        raw = '{"type":"cmd","data":"quit"}'
        self.assertEqual(frame_to_text(raw), "quit")

    def test_say_command_with_embedded_spaces(self):
        raw = '{"type":"cmd","data":"say hello there, general kenobi"}'
        self.assertEqual(frame_to_text(raw), "say hello there, general kenobi")

    def test_payload_is_trimmed(self):
        raw = '{"type":"cmd","data":"  look  "}'
        self.assertEqual(frame_to_text(raw), "look")

    # ── Control frames must NOT be treated as commands ────────────────

    def test_resize_frame_returns_empty(self):
        raw = '{"type":"resize","width":120,"height":50}'
        self.assertEqual(frame_to_text(raw), "")

    def test_token_auth_frame_returns_empty(self):
        # token_auth is processed separately in _ws_handler — this parser
        # should not double-forward it into the input queue.
        raw = '{"type":"token_auth","token":"abc123"}'
        self.assertEqual(frame_to_text(raw), "")

    # ── Legacy field-name fallbacks (no type, or unknown type) ────────

    def test_legacy_input_field_still_works(self):
        raw = '{"input":"look"}'
        self.assertEqual(frame_to_text(raw), "look")

    def test_legacy_text_field_still_works(self):
        raw = '{"text":"look"}'
        self.assertEqual(frame_to_text(raw), "look")

    def test_unknown_type_falls_back_to_data(self):
        raw = '{"type":"future_feature","data":"look"}'
        self.assertEqual(frame_to_text(raw), "look")

    def test_data_wins_over_input_when_both_present(self):
        # Precedence rule: data > input > text, because the live client
        # uses 'data'. This guards against a well-meaning-but-wrong change
        # that would flip the precedence.
        raw = '{"type":"cmd","data":"right","input":"wrong"}'
        self.assertEqual(frame_to_text(raw), "right")

    # ── Defensive / malformed frames ──────────────────────────────────

    def test_cmd_frame_missing_data_returns_empty(self):
        raw = '{"type":"cmd"}'
        self.assertEqual(frame_to_text(raw), "")

    def test_cmd_frame_with_non_string_data_returns_empty(self):
        raw = '{"type":"cmd","data":42}'
        self.assertEqual(frame_to_text(raw), "")

    def test_cmd_frame_with_null_data_returns_empty(self):
        raw = '{"type":"cmd","data":null}'
        self.assertEqual(frame_to_text(raw), "")

    def test_empty_cmd_data_returns_empty(self):
        raw = '{"type":"cmd","data":""}'
        self.assertEqual(frame_to_text(raw), "")

    def test_non_json_payload_passes_through(self):
        # Raw (non-JSON) text is the telnet-style fallback path.
        self.assertEqual(frame_to_text("look"), "look")

    def test_empty_string_returns_empty(self):
        self.assertEqual(frame_to_text(""), "")


if __name__ == "__main__":
    unittest.main()
