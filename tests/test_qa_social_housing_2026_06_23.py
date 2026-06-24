# -*- coding: utf-8 -*-
"""
tests/test_qa_social_housing_2026_06_23.py — QA-campaign fix regression suite.

Covers drop-34 (2026-06-23) fixes:
  1. Bare `who` / `online` → redirect to `+who` (WhoStubCommand).
  2. OOC / comlink channel broadcasts do NOT double-send to web (websocket)
     sessions (send_line skipped; chat-json only for web).
  3. get_available_lots(db, planet=...) filters by planet when supplied.
"""
import asyncio
import importlib
import json
import types
import pytest


# ── 1. WhoStubCommand exists and points at +who ───────────────────────────────

def test_who_stub_command_is_registered():
    """WhoStubCommand must be importable from builtin_commands."""
    import parser.builtin_commands as bc
    assert hasattr(bc, "WhoStubCommand"), (
        "WhoStubCommand not found in parser.builtin_commands"
    )


def test_who_stub_command_key():
    """WhoStubCommand.key must be 'who' (the missing bare form)."""
    import parser.builtin_commands as bc
    cmd = bc.WhoStubCommand()
    assert cmd.key == "who"


def test_who_stub_command_aliases_include_online():
    """WhoStubCommand must alias 'online' as well."""
    import parser.builtin_commands as bc
    cmd = bc.WhoStubCommand()
    assert "online" in (cmd.aliases or []), (
        f"Expected 'online' in aliases; got {cmd.aliases!r}"
    )


def test_who_stub_not_full_who():
    """WhoStubCommand must NOT be WhoCommand — it's a redirect, not a full impl."""
    import parser.builtin_commands as bc
    assert bc.WhoStubCommand is not bc.WhoCommand


def test_who_stub_execute_mentions_plus_who():
    """WhoStubCommand.execute must mention '+who' in its output."""
    import parser.builtin_commands as bc

    sent = []

    class _FakeSession:
        character = {"id": 1, "name": "Tester"}
        async def send_line(self, text):
            sent.append(text)

    class _FakeCtx:
        session = _FakeSession()
        args = ""
        raw_input = "who"
        db = None
        session_mgr = None

    cmd = bc.WhoStubCommand()
    asyncio.run(cmd.execute(_FakeCtx()))

    combined = " ".join(sent)
    assert "+who" in combined, (
        f"Expected '+who' in redirect output; got: {combined!r}"
    )


# ── 2. Channel broadcast: web sessions get JSON only, telnet gets text only ───

def _make_fake_session(is_web: bool, has_character: bool = True):
    """Build a minimal session mock for channel broadcast tests."""
    class _Proto:
        value = "websocket" if is_web else "telnet"

    class _Sess:
        protocol = _Proto()
        character = {"id": 99, "name": "Alice"} if has_character else None
        sent_lines = []
        sent_jsons = []

        async def send_line(self, text):
            self.sent_lines.append(text)

        async def send_json(self, msg_type, data):
            self.sent_jsons.append((msg_type, data))

    return _Sess()


def _make_session_mgr(*sessions):
    class _Mgr:
        all = list(sessions)
    return _Mgr()


def test_broadcast_ooc_web_no_duplicate():
    """Web session: broadcast_ooc must send chat-json but NOT send_line."""
    from server.channels import ChannelManager
    cm = ChannelManager()

    sess = _make_fake_session(is_web=True)
    mgr = _make_session_mgr(sess)

    asyncio.run(
        cm.broadcast_ooc(mgr, "Bob", "hello")
    )

    assert len(sess.sent_lines) == 0, (
        f"Web session should not receive send_line; got {sess.sent_lines!r}"
    )
    assert len(sess.sent_jsons) == 1, (
        f"Web session should receive exactly 1 chat-json; got {sess.sent_jsons!r}"
    )
    msg_type, data = sess.sent_jsons[0]
    assert msg_type == "chat"
    assert data["channel"] == "ooc"
    assert data["from"] == "Bob"


def test_broadcast_ooc_telnet_text_only():
    """Telnet session: broadcast_ooc must send_line only, no JSON."""
    from server.channels import ChannelManager
    cm = ChannelManager()

    sess = _make_fake_session(is_web=False)
    mgr = _make_session_mgr(sess)

    asyncio.run(
        cm.broadcast_ooc(mgr, "Bob", "hello")
    )

    assert len(sess.sent_lines) == 1, (
        f"Telnet session should receive exactly 1 send_line; got {sess.sent_lines!r}"
    )
    assert len(sess.sent_jsons) == 0, (
        f"Telnet session should not receive JSON; got {sess.sent_jsons!r}"
    )
    assert "OOC" in sess.sent_lines[0] or "Bob" in sess.sent_lines[0]


def test_broadcast_comlink_web_no_duplicate():
    """Web session: broadcast_comlink must send chat-json but NOT send_line."""
    from server.channels import ChannelManager
    cm = ChannelManager()

    sess = _make_fake_session(is_web=True)
    mgr = _make_session_mgr(sess)

    asyncio.run(
        cm.broadcast_comlink(mgr, "Rey", "comlink test")
    )

    assert len(sess.sent_lines) == 0, (
        f"Web session should not receive send_line; got {sess.sent_lines!r}"
    )
    assert len(sess.sent_jsons) == 1, (
        f"Web session should receive exactly 1 chat-json; got {sess.sent_jsons!r}"
    )
    msg_type, data = sess.sent_jsons[0]
    assert msg_type == "chat"
    assert data["channel"] == "ic"
    assert "COMLINK" in data["text"]


def test_broadcast_comlink_telnet_text_only():
    """Telnet session: broadcast_comlink must send_line only."""
    from server.channels import ChannelManager
    cm = ChannelManager()

    sess = _make_fake_session(is_web=False)
    mgr = _make_session_mgr(sess)

    asyncio.run(
        cm.broadcast_comlink(mgr, "Rey", "comlink test")
    )

    assert len(sess.sent_lines) == 1
    assert len(sess.sent_jsons) == 0


def test_broadcast_ooc_no_character_skipped():
    """Sessions without a character must be skipped entirely."""
    from server.channels import ChannelManager
    cm = ChannelManager()

    sess = _make_fake_session(is_web=True, has_character=False)
    mgr = _make_session_mgr(sess)

    count = asyncio.run(
        cm.broadcast_ooc(mgr, "Bob", "hello")
    )

    assert count == 0
    assert len(sess.sent_lines) == 0
    assert len(sess.sent_jsons) == 0


# ── 3. get_available_lots planet filter ───────────────────────────────────────

class _FakeDb:
    """Minimal async DB mock that captures the SQL and params passed to fetchall."""
    def __init__(self, rows=()):
        self._rows = rows
        self.last_sql = None
        self.last_params = ()

    async def fetchall(self, sql, params=()):
        self.last_sql = sql
        self.last_params = params
        return self._rows


def test_get_available_lots_no_planet_no_filter():
    """get_available_lots(db) without planet must pass no bind params (no planet = ? binding)."""
    from engine.housing import get_available_lots
    db = _FakeDb()
    asyncio.run(get_available_lots(db))
    # No planet binding — params must be empty (the only sentinel we need).
    assert db.last_params == (), (
        f"Without planet arg, expected empty params; got {db.last_params!r}"
    )
    # SQL must not carry `planet = ?` — the ORDER BY planet is fine.
    sql_lower = (db.last_sql or "").lower()
    assert "planet = ?" not in sql_lower and "planet=?" not in sql_lower, (
        "Without planet arg, SQL must not contain 'planet = ?' predicate"
    )


def test_get_available_lots_with_planet_adds_filter():
    """get_available_lots(db, planet='tatooine') must add AND planet = ? clause."""
    from engine.housing import get_available_lots
    db = _FakeDb()
    asyncio.run(
        get_available_lots(db, planet="tatooine")
    )
    assert "planet" in (db.last_sql or "").lower(), (
        "With planet arg, query must include planet filter"
    )
    assert db.last_params == ("tatooine",), (
        f"Expected ('tatooine',) as params; got {db.last_params!r}"
    )


def test_get_available_lots_with_planet_none_no_filter():
    """get_available_lots(db, planet=None) is the same as no planet — no filter."""
    from engine.housing import get_available_lots
    db = _FakeDb()
    asyncio.run(
        get_available_lots(db, planet=None)
    )
    # params should be empty (no planet binding)
    assert db.last_params == ()


# ── 4. _planet_for_room zone-prefix parsing ──────────────────────────────────

@pytest.mark.parametrize("zone_name,expected", [
    ("tatooine_mos_eisley",   "tatooine"),
    ("tatooine_spaceport",    "tatooine"),
    ("nar_shaddaa_landing",   "nar_shaddaa"),
    ("nar_shaddaa_undercity", "nar_shaddaa"),
    ("coruscant_upper_level", "coruscant"),
    ("geonosis_deep_hive",    "geonosis"),
    ("kamino_tipoca_city",    "kamino"),
    ("kuat_main_spaceport",   "kuat"),
    ("space_tatooine",        None),   # orbit zone — not a planet surface
    ("wilderness_tile",       None),   # wilderness — no planet match
    ("",                      None),   # empty
])
def test_planet_for_room_zone_prefix(zone_name, expected):
    """_planet_for_room derives the correct planet (or None) from a zone slug."""
    from engine.housing import _planet_for_room

    class _ZoneRow:
        def __getitem__(self, key):
            return zone_name if key == "name" else None

    class _Db:
        async def fetchall(self, sql, params=()):
            if "rooms" in sql and zone_name:
                return [_ZoneRow()]
            return []

    result = asyncio.run(
        _planet_for_room(_Db(), room_id=1)
    )
    assert result == expected, (
        f"zone_name={zone_name!r}: expected {expected!r}, got {result!r}"
    )


def test_planet_for_room_no_rows_returns_none():
    """_planet_for_room returns None when room is not in the DB."""
    from engine.housing import _planet_for_room

    class _Db:
        async def fetchall(self, sql, params=()):
            return []

    result = asyncio.run(
        _planet_for_room(_Db(), room_id=999999)
    )
    assert result is None
