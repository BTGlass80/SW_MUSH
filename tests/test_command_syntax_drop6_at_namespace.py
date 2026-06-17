# -*- coding: utf-8 -*-
"""
tests/test_command_syntax_drop6_at_namespace.py
Command-syntax rework — DROP 6: @-namespace collision resolution.

Resolves 6 of the 9 remaining baseline collisions (all in the @ staff
namespace). See command_syntax_rework_design_v2.md. The other 3 / their
alias twins are IC type-3 conflicts (accept / order / investigate /
listen / p / retreat / train) handled in a later drop.

What this drop did:

  Dead / mis-bound building aliases (pure / behaviour-correcting):
    * @set    no longer aliases @succ  -> @succ resolves to @success (correct)
    * @dig    no longer aliases @tel   -> @tel  resolves to @teleport (correct)
    * @open   no longer aliases @tun   -> @tun  resolves to @tunnel  (RESTORED:
              @tun abbreviates @tunnel; @open had wrongly captured it by
              registering later)

  @-key duplicates (one impl was permanently shadowed / dead):
    * @ai     the npc_commands.AIStatusCommand duplicate is DELETED; the richer
              director_commands dashboard is the sole @ai. Its unique
              enable/disable toggle was FOLDED INTO the dashboard.
    * @getattr / @setattr  two genuinely different tools shared these keys. The
              universal object-attribute system (parser/attr_commands.py) keeps
              @getattr / @setattr (it always won). The character-JSON-blob debug
              tool (parser/building_tier2.py) — previously shadowed/dead but
              documented in Guide_27 — is RENAMED to @getcharattr / @setcharattr
              (@gca / @sca) so it is reachable again.
"""
import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from parser.commands import AccessLevel, CommandContext  # noqa: E402
from tests.test_t321_admin_command_access_invariant import (  # noqa: E402
    _build_full_registry,
)

BASELINE_PATH = os.path.join(PROJECT_ROOT, "tests", "data",
                             "command_convention_baseline.json")

# The 6 @-namespace collision signatures this drop removed from the baseline.
RESOLVED_SIGNATURES = {
    "alias:@succ", "alias:@tel", "alias:@tun",
    "key:@ai", "key:@getattr", "key:@setattr",
}


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class TestAtNamespaceWinners(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reg = _build_full_registry()

    def _winner(self, name):
        cmd = self.reg.get(name)
        self.assertIsNotNone(cmd, f"{name} resolves to nothing")
        return type(cmd).__module__, type(cmd).__name__

    # ── dead / mis-bound building aliases now resolve correctly ──────────
    def test_succ_resolves_to_success(self):
        mod, cls = self._winner("@succ")
        self.assertEqual((mod, cls),
                         ("parser.building_tier2", "SuccessCommand"))

    def test_tel_resolves_to_teleport(self):
        mod, cls = self._winner("@tel")
        self.assertEqual((mod, cls),
                         ("parser.building_commands", "TeleportCommand"))

    def test_tun_resolves_to_tunnel_not_open(self):
        # Behaviour-correcting: @tun abbreviates @tunnel, and @open no longer
        # captures it.
        mod, cls = self._winner("@tun")
        self.assertEqual((mod, cls),
                         ("parser.building_commands", "TunnelCommand"))

    # ── @ai is a single dashboard; the npc duplicate is gone ─────────────
    def test_ai_resolves_to_director_dashboard(self):
        mod, cls = self._winner("@ai")
        self.assertEqual((mod, cls),
                         ("parser.director_commands", "AIStatusCommand"))

    def test_npc_commands_has_no_aistatuscommand(self):
        import parser.npc_commands as npc
        self.assertFalse(
            hasattr(npc, "AIStatusCommand"),
            "The shadowed npc_commands.AIStatusCommand duplicate must be "
            "deleted, not merely unregistered.")

    def test_ai_aliases_preserved(self):
        # The dashboard's own @ollama/@idle aliases are unaffected.
        for alias in ("@ollama", "@idle"):
            mod, cls = self._winner(alias)
            self.assertEqual((mod, cls),
                             ("parser.director_commands", "AIStatusCommand"))

    # ── @getattr / @setattr stay the universal object-attr system ────────
    def test_getattr_setattr_are_universal_objectattr(self):
        gm, gc = self._winner("@getattr")
        sm, sc = self._winner("@setattr")
        self.assertEqual((gm, gc), ("parser.attr_commands", "GetAttrUCommand"))
        self.assertEqual((sm, sc), ("parser.attr_commands", "SetAttrExtCommand"))
        # Still BUILDER (unchanged), aligned with @lattr.
        self.assertEqual(self.reg.get("@getattr").access_level,
                         AccessLevel.BUILDER)
        self.assertEqual(self.reg.get("@setattr").access_level,
                         AccessLevel.BUILDER)

    # ── the char-JSON debug tool is reachable again under new keys ───────
    def test_charattr_tool_reachable(self):
        for key in ("@getcharattr", "@gca"):
            mod, cls = self._winner(key)
            self.assertEqual((mod, cls),
                             ("parser.building_tier2", "GetAttrCommand"))
        for key in ("@setcharattr", "@sca"):
            mod, cls = self._winner(key)
            self.assertEqual((mod, cls),
                             ("parser.building_tier2", "SetAttrCommand"))

    def test_charattr_tool_is_admin(self):
        # Distinct from the BUILDER universal system; raw character-sheet
        # writes stay ADMIN-gated (and satisfy the @-namespace >= BUILDER
        # invariant).
        for key in ("@getcharattr", "@setcharattr"):
            self.assertEqual(self.reg.get(key).access_level, AccessLevel.ADMIN)

    def test_charattr_old_keys_no_longer_point_at_dev_tool(self):
        # @ga / @sa were the old char-attr aliases; they must not resolve to
        # the building_tier2 dev tool anymore (clean rename, no back-compat).
        for key in ("@ga", "@sa"):
            cmd = self.reg.get(key)
            if cmd is not None:
                self.assertNotEqual(type(cmd).__module__, "parser.building_tier2")


# ── behavioural: the folded-in @ai enable/disable toggle works ───────────
class _FakeConfig:
    def __init__(self):
        self.enabled = True
        self.default_provider = "ollama"
        self.default_model = "mistral"


class _FakeAIManager:
    def __init__(self):
        self.config = _FakeConfig()

    async def check_status(self):
        return {}


class _FakeSessionMgr:
    def __init__(self):
        self._ai_manager = _FakeAIManager()


class _CapturingSession:
    def __init__(self):
        self.lines = []

    async def send_line(self, text):
        self.lines.append(text)


class TestAiEnableDisableFolded(unittest.TestCase):
    def _ctx(self, args, smgr):
        sess = _CapturingSession()
        ctx = CommandContext(
            session=sess,
            raw_input="@ai " + args,
            command="@ai",
            args=args,
            args_list=args.split() if args else [],
            db=None,
        )
        ctx.session_mgr = smgr
        ctx.server = None
        return ctx, sess

    def _cmd(self):
        from parser.director_commands import AIStatusCommand
        return AIStatusCommand()

    def test_disable_flips_enabled_false(self):
        smgr = _FakeSessionMgr()
        self.assertTrue(smgr._ai_manager.config.enabled)
        ctx, sess = self._ctx("disable", smgr)
        _run(self._cmd().execute(ctx))
        self.assertFalse(smgr._ai_manager.config.enabled)
        self.assertTrue(any("disabled" in ln for ln in sess.lines))

    def test_enable_flips_enabled_true(self):
        smgr = _FakeSessionMgr()
        smgr._ai_manager.config.enabled = False
        ctx, sess = self._ctx("enable", smgr)
        _run(self._cmd().execute(ctx))
        self.assertTrue(smgr._ai_manager.config.enabled)
        self.assertTrue(any("enabled" in ln for ln in sess.lines))

    def test_enable_without_ai_manager_is_graceful(self):
        class _Empty:
            pass
        ctx, sess = self._ctx("enable", _Empty())
        _run(self._cmd().execute(ctx))  # must not raise
        self.assertTrue(any("not found" in ln.lower() for ln in sess.lines))


class TestBaselineShrank(unittest.TestCase):
    def test_resolved_signatures_absent_from_baseline(self):
        with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
            baseline = json.load(fh)
        collisions = set(baseline["collisions"])
        leftover = RESOLVED_SIGNATURES & collisions
        self.assertEqual(
            leftover, set(),
            "These @-namespace collisions were resolved by Drop 6 and must be "
            f"absent from the baseline: {sorted(leftover)}")

    def test_remaining_collisions_are_the_ic_tail(self):
        with open(BASELINE_PATH, "r", encoding="utf-8") as fh:
            baseline = json.load(fh)
        # No @-namespace collision should remain.
        at_collisions = [c for c in baseline["collisions"]
                         if c.split(":", 1)[1].startswith("@")]
        self.assertEqual(at_collisions, [],
                         f"Unexpected leftover @-collisions: {at_collisions}")


if __name__ == "__main__":
    unittest.main()
