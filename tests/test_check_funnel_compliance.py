# -*- coding: utf-8 -*-
"""
tests/test_check_funnel_compliance.py — `+check` funnel compliance (2026-06-25)

The `+check` command (parser/d6_commands.py CheckCommand) used to resolve a
player's manual skill check with the inline engine.dice.difficulty_check(pool),
which bypassed the perform_skill_check funnel and therefore honored NONE of:
active buffs/debuffs, a carried-tool bonus, the SANDSTORM perception penalty, a
staged combined-action lead bonus, OR the skill_check telemetry emit. Per the
hard invariant "all out-of-combat dice resolve through perform_skill_check",
`+check` now routes through the funnel like every system-driven check.

These tests pin the migration four ways:
  - ROUTING: +check invokes perform_skill_check (spy), not the inline path.
  - BEHAVIOR (deterministic): a carried tool's +1D bonus reaches the roll —
    the effective pool grows (3D -> 4D) and the tool is credited in the
    output — proof the funnel mechanics now apply to a manual check.
  - TELEMETRY: +check now emits a skill_check telemetry event.
  - STRUCTURAL guard: d6_commands imports perform_skill_check and makes no
    difficulty_check() call (a revert turns the board red).
"""
import asyncio
import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.character import SkillRegistry, canonical_skill_key  # noqa: E402
from parser import d6_commands as d6  # noqa: E402
from engine import telemetry  # noqa: E402


_SR = SkillRegistry()
_SR.load_file(os.path.join(PROJECT_ROOT, "data", "skills.yaml"))

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _plain(parts) -> str:
    return _ANSI_RE.sub("", "\n".join(parts))


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line=""):
        self.sent.append(line)


class _FakeSessionMgr:
    def __init__(self):
        self.broadcasts = []

    async def broadcast_to_room(self, room_id, msg, exclude=None, source_char=None):
        self.broadcasts.append((room_id, msg))


def _char(attributes=None, skills=None, inventory=None):
    return {
        "id": 1,
        "name": "Testy",
        "room_id": 10,
        "attributes": json.dumps(attributes or {"dexterity": "3D"}),
        "skills": json.dumps(skills or {}),
        "inventory": json.dumps(inventory) if inventory is not None else "[]",
    }


def _ctx(session, mgr, args=""):
    from parser.commands import CommandContext
    ctx = CommandContext(
        session=session, raw_input=f"+check {args}".strip(), command="+check",
        args=args, args_list=args.split() if args else [], db=None,
        session_mgr=mgr,
    )
    # Pin the skill registry (production loads it lazily off disk on first use).
    ctx._skill_reg_cache = _SR
    return ctx


def _run(coro):
    return asyncio.run(coro)


class TestCheckRoutesThroughFunnel(unittest.TestCase):
    def test_check_calls_perform_skill_check(self):
        calls = []
        real = d6.perform_skill_check

        def _spy(char, skill_name, difficulty, skill_registry=None, **kw):
            calls.append((char, skill_name, difficulty))
            return real(char, skill_name, difficulty, skill_registry, **kw)

        sess = _FakeSession(_char())
        ctx = _ctx(sess, _FakeSessionMgr(), args="blaster 15")
        d6.perform_skill_check = _spy
        try:
            _run(d6.CheckCommand().execute(ctx))
        finally:
            d6.perform_skill_check = real

        self.assertEqual(len(calls), 1,
                         "+check must resolve via the perform_skill_check funnel")
        _char_arg, skill_arg, diff_arg = calls[0]
        self.assertEqual(canonical_skill_key(skill_arg), "blaster")
        self.assertEqual(diff_arg, 15)
        out = _plain(sess.sent)
        self.assertIn("Blaster", out)
        self.assertTrue("SUCCESS" in out or "FAILURE" in out,
                        "+check still renders a pass/fail result line")

    def test_room_sees_abbreviated_result(self):
        sess = _FakeSession(_char())
        mgr = _FakeSessionMgr()
        ctx = _ctx(sess, mgr, args="blaster 5")
        _run(d6.CheckCommand().execute(ctx))
        self.assertEqual(len(mgr.broadcasts), 1)
        room_id, msg = mgr.broadcasts[0]
        self.assertEqual(room_id, 10)
        self.assertIn("Testy", _ANSI_RE.sub("", msg))


class TestToolBonusReachesCheck(unittest.TestCase):
    """Deterministic proof the funnel's mechanics now apply to a manual check.

    The roll total is random, but the EFFECTIVE pool string is deterministic:
    dexterity 3D + an untrained Blaster (falls back to the attribute) = 3D base,
    plus a carried +1D tool = 4D. The old inline path applied no tool bonus, so
    this assertion is red before the migration and green after.
    """

    def test_carried_tool_bonus_applies_and_is_credited(self):
        inv = {"items": [
            {"name": "Targeting Macrobinoculars",
             "skill_bonus": {"skill": "blaster", "bonus": "+1D"}},
        ]}
        sess = _FakeSession(_char(attributes={"dexterity": "3D"}, inventory=inv))
        ctx = _ctx(sess, _FakeSessionMgr(), args="blaster 15")
        _run(d6.CheckCommand().execute(ctx))
        out = _plain(sess.sent)
        self.assertIn("4D", out, "tool +1D must raise the effective pool 3D -> 4D")
        self.assertIn("Targeting Macrobinoculars", out,
                      "the contributing tool must be credited in the output")

    def test_no_tool_means_base_pool(self):
        sess = _FakeSession(_char(attributes={"dexterity": "3D"}))
        ctx = _ctx(sess, _FakeSessionMgr(), args="blaster 15")
        _run(d6.CheckCommand().execute(ctx))
        out = _plain(sess.sent)
        self.assertIn("3D", out)
        self.assertNotIn("Macrobinoculars", out)


class TestCheckEmitsTelemetry(unittest.TestCase):
    def setUp(self):
        telemetry.reset()
        telemetry.configure(enabled=True)

    def tearDown(self):
        telemetry.reset()

    def test_manual_check_emits_skill_check_event(self):
        sess = _FakeSession(_char())
        ctx = _ctx(sess, _FakeSessionMgr(), args="blaster 15")
        _run(d6.CheckCommand().execute(ctx))
        events = [json.loads(line) for line in telemetry.get_sink().drain()]
        skill_events = [e for e in events if e.get("ev") == "skill_check"]
        self.assertEqual(len(skill_events), 1,
                         "+check should emit exactly one skill_check telemetry event")
        ev = skill_events[0]
        self.assertEqual(canonical_skill_key(ev["skill"]), "blaster")
        self.assertEqual(ev["difficulty"], 15)
        self.assertEqual(ev["char_id"], 1)


class TestStructuralGuard(unittest.TestCase):
    def test_d6_commands_uses_funnel_not_inline_dice(self):
        with open(os.path.join(PROJECT_ROOT, "parser", "d6_commands.py"),
                  encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn("from engine.skill_checks import perform_skill_check", src)
        # No inline difficulty_check() call may resolve +check (a revert restores
        # one and turns this red). The symbol may survive only in prose comments.
        self.assertNotIn("difficulty_check(", src)


if __name__ == "__main__":
    unittest.main()
