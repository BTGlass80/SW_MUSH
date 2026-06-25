"""
test_fun_followups_talk.py — `talk <multi-word NPC>` parse fix.

The tutorial's first instructed action is `talk Major Tarrn`, but TalkCommand
split on the first word (npc="Major", message="Tarrn") so it SAID "Tarrn" to
the NPC instead of opening dialogue (fun-assessment finding, live-confirmed).
The fix resolves the FULL argument as an NPC name first (→ default greeting),
falling back to the <npc> <message> split only when the whole thing isn't an
NPC present.

Static parse of parser/npc_commands.py (the behavioral path needs a live AI
manager + NPC; the live Playwright probe confirmed the behavior — this guards
the parse logic against regression).
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
NPC_CMDS = REPO_ROOT / "parser" / "npc_commands.py"


def _talk_execute() -> str:
    src = NPC_CMDS.read_text(encoding="utf-8")
    i = src.find("class TalkCommand")
    assert i != -1, "TalkCommand not found"
    j = src.find("async def execute", i)
    # grab a generous window of the execute body
    return src[j: j + 1600]


def test_talk_tries_full_args_as_npc_first():
    body = _talk_execute()
    # The full argument is resolved as an NPC before any first-word split.
    i_full = body.find("_find_npc_in_room(ctx, full)")
    assert i_full != -1, (
        "TalkCommand must try the FULL args as an NPC name "
        "(_find_npc_in_room(ctx, full)) so multi-word names like 'Major Tarrn' "
        "open dialogue instead of saying the 2nd word")
    i_split = body.find("ctx.args.split(None, 1)")
    assert i_split != -1, "the <npc> <message> split fallback should still exist"
    assert i_full < i_split, (
        "the full-name resolution must come BEFORE the first-word split")


def test_talk_full_match_uses_default_greeting():
    body = _talk_execute()
    # On a full-name match, message defaults to the greeting (no 2nd word leaks
    # in as the message).
    assert re.search(r"if\s+npc_row:\s*\n\s*npc_name\s*=\s*full\s*\n\s*message\s*=\s*[\"']Hello",
                     body), (
        "a full-name NPC match must use the default greeting, not a split message")
