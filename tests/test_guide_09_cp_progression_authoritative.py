# -*- coding: utf-8 -*-
"""tests/test_guide_09_cp_progression_authoritative.py

Opus authoritative quality pass on Guide_09_CP_Progression.md (drop
guide-09-cp-progression-authoritative). Guards the facts the pass corrected
against the LIVE engine — these were test-invisible drift the convention/
constant suite did not catch:

  * §2 Source 4 "AI Evaluator Trickle" was a PHANTOM FAUCET — engine
    `award_ai_trickle` has zero callers, so it cannot be earned today. The
    guide must not present it as a live income source.
  * §3 claimed WEG training-time + a teacher requirement for `train` — no
    such mechanic exists; skill advancement is instant. The guide must say so.
  * §6 undercounted Ship's Log milestone CP (listed 7 capstones ≈260 CP);
    the live MILESTONES table totals 410 CP across 17 progressive tiers.

Plus the behavioural fix the pass surfaced: `+kudos <player> <message>` now
resolves the target (the matcher used to startswith() the FULL args, so any
trailing message broke target lookup) and delivers the sanitized message.
"""

import ast
import asyncio
import pathlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

GUIDE = pathlib.Path("data/guides/Guide_09_CP_Progression.md")
CP_COMMANDS = pathlib.Path("parser/cp_commands.py")


def _guide():
    return GUIDE.read_text(encoding="utf-8")


# ── Guide accuracy vs live engine ────────────────────────────────────────────

def test_ai_trickle_not_presented_as_live_source():
    text = _guide()
    # Three active sources, not four.
    assert "Three income sources feed the tick pool" in text
    assert "Four income sources" not in text
    # If the AI evaluator is mentioned at all it must be flagged not-yet-active.
    if "AI-evaluator" in text or "AI Evaluator" in text:
        assert "not yet active" in text.lower() or "planned" in text.lower()


def test_ai_trickle_is_admin_gated_and_dormant():
    """The AI-evaluator trickle is now WIRED -- but only to the MANUAL @director
    admin grant, and DORMANT by default -- so it is NOT an automatic income
    source. (CP fork 2026-06-23 added the admin-gated caller; the guide still
    says it is not a source you can earn from by default.)"""
    import engine.cp_engine as _ce
    assert _ce.is_cp_ai_trickle_enabled() is False, (
        "the AI CP trickle must default DORMANT (off at launch)")
    callers = []
    for d in ("engine", "parser", "server", "ai"):
        for p in pathlib.Path(d).glob("**/*.py"):
            if p.name == "cp_engine.py":
                continue
            try:
                src = p.read_text(encoding="utf-8")
            except Exception:
                continue
            if "award_ai_trickle(" in src:
                callers.append(p.as_posix())
    assert callers == ["parser/director_commands.py"], (
        "award_ai_trickle's ONLY caller must be the @director admin command "
        "(a manual grant, not an auto/AI prose scorer); got %r" % (callers,))


def test_training_is_instant_no_phantom_teacher():
    text = _guide()
    assert "Advancement is instant." in text
    # The phantom WEG training-time/teacher claims must be gone.
    assert "5 days vs. 10 days" not in text
    assert "A teacher halves training time" not in text


def test_milestone_total_matches_engine():
    """The guide's stated all-milestone CP total must equal the live sum."""
    from engine.ships_log import MILESTONES
    total = sum(m["cp"] for m in MILESTONES)
    assert total == 410, f"engine milestone CP total changed to {total}"
    text = _guide()
    assert "410 CP" in text, "Guide_09 §6 must state the real 410 CP total"
    # The old undercount must be gone.
    assert "260+ bonus CP" not in text


def test_guild_discount_still_documented():
    text = _guide()
    assert "20% discount" in text
    from engine.organizations import GUILD_CP_DISCOUNT
    assert GUILD_CP_DISCOUNT == 0.20


def test_canonical_command_keys():
    text = _guide()
    assert "`+cpstatus`" in text
    assert "`+kudos <player> [message]`" in text
    assert "`+scenebonus <poses>`" in text


def test_cp_commands_syntax_valid():
    ast.parse(CP_COMMANDS.read_text(encoding="utf-8"))


# ── Engine fix: +kudos <player> <message> resolves the target ────────────────

def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def _make_ctx(args, giver, target):
    giver_sess = SimpleNamespace(character=giver, send_line=AsyncMock())
    target_sess = SimpleNamespace(character=target, send_line=AsyncMock())
    sessions = {giver["id"]: giver_sess, target["id"]: target_sess}
    session_mgr = SimpleNamespace(
        _sessions=sessions,
        find_by_character=lambda cid: sessions.get(cid),
    )
    db = SimpleNamespace(kudos_count_received_this_week=AsyncMock(return_value=1))
    ctx = SimpleNamespace(
        session=giver_sess, args=args, session_mgr=session_mgr, db=db,
    )
    return ctx, giver_sess, target_sess


def _patch_engine(monkeypatch_award):
    import parser.cp_commands as cc
    fake_engine = SimpleNamespace(award_kudos=monkeypatch_award)
    cc.get_cp_engine = lambda: fake_engine  # type: ignore
    return cc


def test_kudos_with_message_resolves_target_and_delivers_message():
    import parser.cp_commands as cc
    orig = cc.get_cp_engine
    award = AsyncMock(return_value={"success": True, "ticks_awarded": 35})
    try:
        _patch_engine(award)
        ctx, giver_sess, target_sess = _make_ctx(
            "Tundra Great scene at the cantina!",
            {"id": 1, "name": "Giver"}, {"id": 2, "name": "Tundra"},
        )
        asyncio.run(cc.KudosCommand().execute(ctx))
        # Target was resolved despite the trailing message (the old bug).
        award.assert_awaited_once()
        call_args = award.await_args.args
        assert call_args[1] == 1 and call_args[2] == 2
        # The message reached the recipient's session.
        delivered = " ".join(c.args[0] for c in target_sess.send_line.await_args_list)
        assert "Great scene at the cantina!" in delivered
    finally:
        cc.get_cp_engine = orig


def test_kudos_bare_name_prefix_still_works():
    import parser.cp_commands as cc
    orig = cc.get_cp_engine
    award = AsyncMock(return_value={"success": True, "ticks_awarded": 35})
    try:
        _patch_engine(award)
        ctx, _, _ = _make_ctx(
            "Tun", {"id": 1, "name": "Giver"}, {"id": 2, "name": "Tundra"},
        )
        asyncio.run(cc.KudosCommand().execute(ctx))
        award.assert_awaited_once()
        assert award.await_args.args[2] == 2
    finally:
        cc.get_cp_engine = orig


def test_kudos_message_is_sanitized():
    import parser.cp_commands as cc
    orig = cc.get_cp_engine
    award = AsyncMock(return_value={"success": True, "ticks_awarded": 35})
    try:
        _patch_engine(award)
        ctx, _, target_sess = _make_ctx(
            "Tundra nice\x07bell\nnewline",
            {"id": 1, "name": "Giver"}, {"id": 2, "name": "Tundra"},
        )
        asyncio.run(cc.KudosCommand().execute(ctx))
        delivered = " ".join(c.args[0] for c in target_sess.send_line.await_args_list)
        # Control chars from the injected message are stripped before display.
        assert "\x07" not in delivered
        # The message body still gets through (sans control bytes).
        assert "nice" in delivered and "newline" in delivered
    finally:
        cc.get_cp_engine = orig
