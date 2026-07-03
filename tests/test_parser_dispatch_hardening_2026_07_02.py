# -*- coding: utf-8 -*-
"""
tests/test_parser_dispatch_hardening_2026_07_02.py — two parser-dispatch
defects found by a break-it QA pass (2026-07-02), both in
``parser/commands.py``.

FIX A — Incapacitated / Mortally-Wounded characters could still freely act
(move/talk/look) outside combat. ``CommandParser._execute``'s dead-state
intercept only gated ``wound_level >= WoundLevel.DEAD`` (6); there was no
gate for ``INCAPACITATED`` (4) or ``MORTALLY_WOUNDED`` (5), even though
``combat.declare_action`` already refuses those at ``>= INCAPACITATED``
with "You can't act in your current condition." Added a matching
intercept one rung down the wound ladder (excludes DEAD, which the
existing block already owns), gated by a new
``CommandParser.INCAPACITATED_ALLOWED`` set. Allowed-set choice (mirrors
the conservative DEAD_ALLOWED shape): DEAD_ALLOWED's passive/status
commands (look/l, help/+help/?/commands/+commands, who/+who,
quit/@quit/logout, respawn — harmless here since RespawnCommand
self-guards on wound_level < DEAD with "You're not dead!") plus OOC
chatter (ooc/+ooc). Movement + active IC commands (attack, say, emote,
etc.) are blocked.

FIX B — the ``try_nl_combat_action`` call in ``parse_and_dispatch`` was
the only dispatch call in that function not wrapped in try/except. An
AI-layer fault (DB hiccup in ``SceneContext.build``, an NPC despawning
mid-combat) propagated out of the coroutine and killed the session's
``_game_loop`` task permanently (the loop's ``await
self.parser.parse_and_dispatch(...)`` call in
``server/game_server.py`` has no surrounding try/except either) — the
player would get zero output forever. Now wrapped + logged, mirroring
every other guarded dispatch surface in the same function.
"""
from __future__ import annotations

import asyncio
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("SW_ERA", "clone_wars")

from engine.character import WoundLevel  # noqa: E402
from engine import telemetry  # noqa: E402
from engine import tunables  # noqa: E402
from parser.commands import (  # noqa: E402
    BaseCommand,
    CommandContext,
    CommandParser,
    CommandRegistry,
)


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ══════════════════════════════════════════════════════════════════════════
# FIX A — incapacitated/mortally-wounded action gate
# ══════════════════════════════════════════════════════════════════════════

class _FakeSession:
    """Just enough Session surface for CommandParser._execute."""

    def __init__(self, *, character=None, in_game=True, sid=1):
        self.id = sid
        self.character = character
        self.is_in_game = in_game
        self.account = None
        self.lines: list = []

    async def send_line(self, msg=""):
        self.lines.append(msg)

    async def send_prompt(self):
        pass

    async def send_hud_update(self, **kw):
        pass


class _Move(BaseCommand):
    key = "move"

    async def execute(self, ctx):
        await ctx.session.send_line("You move.")


class _Attack(BaseCommand):
    key = "attack"

    async def execute(self, ctx):
        await ctx.session.send_line("You attack!")


class _Look(BaseCommand):
    key = "look"
    aliases = ["l"]

    async def execute(self, ctx):
        await ctx.session.send_line("You see a room.")


class _Respawn(BaseCommand):
    key = "respawn"

    async def execute(self, ctx):
        await ctx.session.send_line("You respawn.")


def _ctx(session, command):
    return CommandContext(
        session=session,
        raw_input=command,
        command=command,
        args="",
        args_list=[],
        switches=[],
        db=None,
        session_mgr=None,
    )


def _make_registry() -> CommandRegistry:
    reg = CommandRegistry()
    reg.register(_Move())
    reg.register(_Attack())
    reg.register(_Look())
    reg.register(_Respawn())
    return reg


class TestIncapacitatedActionGate(unittest.TestCase):

    def setUp(self):
        telemetry.reset()
        tunables.reset_tunables()
        self.reg = _make_registry()
        self.parser = CommandParser(self.reg, db=None, session_mgr=None)

    def tearDown(self):
        telemetry.reset()
        tunables.reset_tunables()

    def _dispatch(self, wound_level, command):
        sess = _FakeSession(character={"id": 1, "wound_level": wound_level})
        cmd = self.reg.get(command)
        _run(self.parser._execute(cmd, _ctx(sess, command)))
        return sess.lines

    # ── regression pin: HEALTHY is unaffected ──────────────────────────
    def test_healthy_char_can_move_and_attack(self):
        for cmd_name, expect in (("move", "You move."),
                                  ("attack", "You attack!")):
            lines = self._dispatch(WoundLevel.HEALTHY, cmd_name)
            self.assertIn(expect, lines,
                          f"HEALTHY char must still be able to {cmd_name}")

    # ── INCAPACITATED blocks movement + active IC, allows passive ─────
    def test_incapacitated_blocks_movement(self):
        lines = self._dispatch(WoundLevel.INCAPACITATED, "move")
        self.assertTrue(
            any("can't act in your current condition" in ln.lower()
                for ln in lines),
            f"INCAPACITATED must refuse movement. Got: {lines}",
        )
        self.assertNotIn("You move.", lines)

    def test_incapacitated_blocks_active_ic_command(self):
        lines = self._dispatch(WoundLevel.INCAPACITATED, "attack")
        self.assertTrue(
            any("can't act in your current condition" in ln.lower()
                for ln in lines),
            f"INCAPACITATED must refuse an active IC command. Got: {lines}",
        )
        self.assertNotIn("You attack!", lines)

    def test_incapacitated_allows_look(self):
        lines = self._dispatch(WoundLevel.INCAPACITATED, "look")
        self.assertIn("You see a room.", lines,
                      "INCAPACITATED must still allow passive/status 'look'")

    # ── MORTALLY_WOUNDED gated the same as INCAPACITATED ───────────────
    def test_mortally_wounded_blocks_movement(self):
        lines = self._dispatch(WoundLevel.MORTALLY_WOUNDED, "move")
        self.assertTrue(
            any("can't act in your current condition" in ln.lower()
                for ln in lines),
            f"MORTALLY_WOUNDED must refuse movement. Got: {lines}",
        )
        self.assertNotIn("You move.", lines)

    def test_mortally_wounded_blocks_active_ic_command(self):
        lines = self._dispatch(WoundLevel.MORTALLY_WOUNDED, "attack")
        self.assertTrue(
            any("can't act in your current condition" in ln.lower()
                for ln in lines),
            f"MORTALLY_WOUNDED must refuse an active IC command. Got: {lines}",
        )

    def test_mortally_wounded_allows_look(self):
        lines = self._dispatch(WoundLevel.MORTALLY_WOUNDED, "look")
        self.assertIn("You see a room.", lines)

    # ── DEAD still owns its own gate + message (not the incap one) ────
    def test_dead_still_refuses_with_dead_message(self):
        lines = self._dispatch(WoundLevel.DEAD, "attack")
        self.assertTrue(
            any("you are dead" in ln.lower() for ln in lines),
            f"DEAD must keep its own 'You are DEAD' message. Got: {lines}",
        )
        self.assertFalse(
            any("can't act in your current condition" in ln.lower()
                for ln in lines),
            "DEAD must not fall through to the incapacitated message",
        )

    def test_dead_allows_respawn(self):
        lines = self._dispatch(WoundLevel.DEAD, "respawn")
        self.assertIn("You respawn.", lines)


# ══════════════════════════════════════════════════════════════════════════
# FIX B — unguarded NL-combat dispatch call
# ══════════════════════════════════════════════════════════════════════════

class TestNLCombatDispatchGuarded(unittest.TestCase):
    """Live-harness regression: an AI-layer fault inside the NL-combat
    intercept must not kill the session's game loop task."""

    @classmethod
    def setUpClass(cls):
        from tests.harness import _LiveHarness
        cls.harness = _run(_LiveHarness.boot("clone_wars"))

    @classmethod
    def tearDownClass(cls):
        _run(cls.harness.shutdown())
        try:
            import engine.world_events as _we
            _we._manager = None
        except Exception:
            pass

    def test_nl_combat_fault_returns_clean_message_and_survives(self):
        async def go():
            h = self.harness
            s = await h.login_as("NLFaultPC", room_id=1, credits=0)

            import parser.combat_commands as cc

            async def _boom(ctx, raw_input):
                raise RuntimeError(
                    "SceneContext.build DB hiccup (simulated break-it repro)"
                )

            orig = cc.try_nl_combat_action
            cc.try_nl_combat_action = _boom
            try:
                # An unrecognized word with a real character in play routes
                # into the NL-combat intercept (parse_and_dispatch), which
                # is now guarded.
                out = await h.cmd(s, "qxzzybarknotarealcommand")
            finally:
                cc.try_nl_combat_action = orig

            self.assertIn(
                "error occurred processing your command", out.lower(),
                f"a guarded NL-combat fault must surface the clean generic "
                f"error line. Output: {out!r}",
            )

            # Load-bearing: the game loop task backing this session must
            # still be alive (pre-fix, the unguarded raise propagated out
            # of parse_and_dispatch -> _game_loop, silently killing the
            # task and permanently zeroing this session's output).
            self.assertFalse(
                s._game_task.done(),
                "the session's game loop task must survive a guarded "
                "NL-combat intercept fault",
            )

            # And dispatch must still actually be working, not just
            # "not yet garbage collected" -- a normal follow-up command
            # must produce real output.
            out2 = await h.cmd(s, "look")
            self.assertTrue(
                out2.strip(),
                "session must still respond to commands after the "
                "guarded NL-combat fault",
            )

        _run(go())


if __name__ == "__main__":
    unittest.main()
