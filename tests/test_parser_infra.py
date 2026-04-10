#!/usr/bin/env python3
"""
Test suite for Drop 1 — Parser Infrastructure.
Tests prefix extraction, switch parsing, and semipose.
Run from project root:  python -m pytest tests/test_parser_infra.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from parser.commands import (
    CommandParser, CommandRegistry, CommandContext, BaseCommand, AccessLevel
)


# ── Helpers ──────────────────────────────────────────────────────────

class StubCommand(BaseCommand):
    key = "say"
    aliases = ["'", '"']
    access_level = AccessLevel.ANYONE
    last_ctx = None

    async def execute(self, ctx):
        StubCommand.last_ctx = ctx


class EmoteStub(BaseCommand):
    key = "emote"
    aliases = [":", "pose", "em"]
    access_level = AccessLevel.ANYONE
    last_ctx = None

    async def execute(self, ctx):
        EmoteStub.last_ctx = ctx


class SemiposeStub(BaseCommand):
    key = ";"
    aliases = ["semipose"]
    access_level = AccessLevel.ANYONE
    last_ctx = None

    async def execute(self, ctx):
        SemiposeStub.last_ctx = ctx


class SheetStub(BaseCommand):
    key = "+sheet"
    aliases = ["sheet", "score"]
    access_level = AccessLevel.ANYONE
    valid_switches = ["brief", "skills", "combat"]
    last_ctx = None

    async def execute(self, ctx):
        SheetStub.last_ctx = ctx


class HelpStub(BaseCommand):
    key = "+help"
    aliases = ["help", "?"]
    access_level = AccessLevel.ANYONE
    valid_switches = ["search"]
    last_ctx = None

    async def execute(self, ctx):
        HelpStub.last_ctx = ctx


class LookStub(BaseCommand):
    key = "look"
    aliases = ["l"]
    access_level = AccessLevel.ANYONE
    last_ctx = None

    async def execute(self, ctx):
        LookStub.last_ctx = ctx


def make_parser():
    reg = CommandRegistry()
    reg.register(StubCommand())
    reg.register(EmoteStub())
    reg.register(SemiposeStub())
    reg.register(SheetStub())
    reg.register(HelpStub())
    reg.register(LookStub())

    parser = CommandParser(reg, db=MagicMock(), session_mgr=MagicMock())
    return parser


def make_session():
    s = MagicMock()
    s.send_line = AsyncMock()
    s.send_prompt = AsyncMock()
    s.send_hud_update = AsyncMock()
    s.is_in_game = False
    s.character = None
    s.account = None
    return s


# ── Tests ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_quote_prefix_glued():
    """'hello → command say, args hello"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "'hello there")
    assert StubCommand.last_ctx is not None
    assert StubCommand.last_ctx.command == "'"
    assert StubCommand.last_ctx.args == "hello there"


@pytest.mark.asyncio
async def test_doublequote_prefix_glued():
    '''"hello → command say, args hello'''
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, '"hello there')
    assert StubCommand.last_ctx.command == '"'
    assert StubCommand.last_ctx.args == "hello there"


@pytest.mark.asyncio
async def test_colon_prefix_glued():
    """:waves → command emote, args waves"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, ":waves cheerfully")
    assert EmoteStub.last_ctx is not None
    assert EmoteStub.last_ctx.command == ":"
    assert EmoteStub.last_ctx.args == "waves cheerfully"


@pytest.mark.asyncio
async def test_semicolon_prefix_glued():
    """;'s blaster → command ;, args 's blaster"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, ";'s blaster hums")
    assert SemiposeStub.last_ctx is not None
    assert SemiposeStub.last_ctx.command == ";"
    assert SemiposeStub.last_ctx.args == "'s blaster hums"


@pytest.mark.asyncio
async def test_quote_with_space():
    """' hello (with space) still works"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "' hello there")
    assert StubCommand.last_ctx.command == "'"
    assert StubCommand.last_ctx.args == "hello there"


@pytest.mark.asyncio
async def test_switch_parsing():
    """+sheet/brief → command +sheet, switches [brief]"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "+sheet/brief")
    assert SheetStub.last_ctx is not None
    assert SheetStub.last_ctx.command == "+sheet"
    assert SheetStub.last_ctx.switches == ["brief"]
    assert SheetStub.last_ctx.args == ""


@pytest.mark.asyncio
async def test_switch_with_args():
    """+help/search combat → command +help, switches [search], args combat"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "+help/search combat")
    assert HelpStub.last_ctx is not None
    assert HelpStub.last_ctx.command == "+help"
    assert HelpStub.last_ctx.switches == ["search"]
    assert HelpStub.last_ctx.args == "combat"


@pytest.mark.asyncio
async def test_multiple_switches():
    """+sheet/brief/skills → switches [brief, skills]"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "+sheet/brief/skills")
    assert SheetStub.last_ctx.switches == ["brief", "skills"]


@pytest.mark.asyncio
async def test_no_switch():
    """+sheet with no switch → switches []"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "+sheet")
    assert SheetStub.last_ctx.switches == []


@pytest.mark.asyncio
async def test_invalid_switch_rejected():
    """+sheet/bogus → error message, command not executed"""
    parser = make_parser()
    session = make_session()
    SheetStub.last_ctx = None
    await parser.parse_and_dispatch(session, "+sheet/bogus")
    # The session should have received an error about the bad switch
    session.send_line.assert_called()
    error_msg = session.send_line.call_args_list[0][0][0]
    assert "Unknown switch" in error_msg
    assert "/bogus" in error_msg


@pytest.mark.asyncio
async def test_bare_word_still_works():
    """look still works as a bare word command"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "look")
    assert LookStub.last_ctx is not None
    assert LookStub.last_ctx.command == "look"


@pytest.mark.asyncio
async def test_bare_alias_for_plus_command():
    """sheet (bare) still works as alias for +sheet"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "sheet")
    assert SheetStub.last_ctx is not None
    # Command name in ctx is what the user typed
    assert SheetStub.last_ctx.command == "sheet"


@pytest.mark.asyncio
async def test_glued_prefix_no_switch_extraction():
    """Colon prefix should not try to parse switches from args"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, ":foo/bar")
    assert EmoteStub.last_ctx is not None
    assert EmoteStub.last_ctx.command == ":"
    # The /bar should be part of args, not treated as a switch
    assert EmoteStub.last_ctx.switches == []
    assert "foo/bar" in EmoteStub.last_ctx.args


@pytest.mark.asyncio
async def test_context_switches_default():
    """CommandContext.switches defaults to empty list"""
    ctx = CommandContext(
        session=MagicMock(),
        raw_input="test",
        command="test",
        args="",
        args_list=[],
    )
    assert ctx.switches == []


@pytest.mark.asyncio
async def test_empty_input():
    """Empty input sends prompt, no crash"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "")
    session.send_prompt.assert_called_once()


@pytest.mark.asyncio
async def test_whitespace_only():
    """Whitespace-only input sends prompt, no crash"""
    parser = make_parser()
    session = make_session()
    await parser.parse_and_dispatch(session, "   ")
    session.send_prompt.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
