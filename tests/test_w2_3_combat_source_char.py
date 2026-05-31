# -*- coding: utf-8 -*-
"""
tests/test_w2_3_combat_source_char.py — Drop W.2.3.

Verifies that ``parser/combat_commands.py`` threads ``source_char`` into
its target-acquisition and target-notification call sites. This closes
the wilderness Bucket 1 gap that was open in v41 of the architecture
(``wilderness_colocation_audit_v1.md``): combat targeting and PvP
challenge/accept/decline flow now respect wilderness co-location.

Why the migration matters even though wilderness combat is gated
================================================================

``AttackCommand`` has a hard wilderness gate (``[NO COMBAT]`` message)
that prevents combat from starting in any wilderness region today.
That gate alone is sufficient to prevent the audit's
"PC-shoots-PC-60km-across-the-desert" bug. So why migrate now?

1. The gate is defensive but coarse. ``ChallengeCommand``,
   ``AcceptCommand``, and ``DeclineCommand`` (PvP-consent flow) do
   *not* have the gate — and they leak across tiles today: a PC at
   (5,5) can challenge a PC at (35,35) via wilderness sentinel
   sharing. The match → notify → broadcast chain shouldn't reach
   tiles that are 60km of desert away.

2. When the gate eventually comes down (``W.2.4`` — combat-instance
   keying that incorporates wilderness coords), the targeting layer
   in ``AttackCommand`` must be tile-correct *before* the gate is
   removed. Doing the migration now and proving it with tests means
   ``W.2.4`` is the keying redesign only — it doesn't have to also
   audit targeting at the same time.

3. The audit's ``TestBucket1SurfacesUseSourceChar`` did not previously
   include ``parser/combat_commands.py``. That omission is closed by
   ``test_combat_commands_uses_source_char`` here.

Scope of W.2.3
==============

Migration of six call sites in ``parser/combat_commands.py``:

  - ``AttackCommand._find_target``: ``match_in_room`` (target acquisition)
    + ``sessions_in_room`` (target session lookup).
  - ``ChallengeCommand``: ``match_in_room`` (target lookup) +
    ``sessions_in_room`` (target notification).
  - ``AcceptCommand``: ``match_in_room`` (challenger lookup) +
    ``sessions_in_room`` (challenger notification) +
    ``broadcast_to_room`` (room-wide consent announcement).
  - ``DeclineCommand``: ``match_in_room`` (optional challenger lookup).

Eight ``source_char=char`` call-site additions in total.

Out of scope (deferred)
=======================

In-combat broadcast helpers — ``_broadcast_events``,
``_broadcast_separator``, ``_broadcast_events_paced``,
``_send_combat_state``, ``_send_combat_ended`` — and the ~15 broadcast
sites inside the round-resolution machinery are NOT migrated in W.2.3.

Rationale: the ``AttackCommand`` wilderness gate makes those code paths
unreachable in wilderness today. Migrating them now would add ~80 lines
of plumbing that has zero runtime effect until ``W.2.4`` lifts the gate.
The right place to do that work is in the same drop that lifts the gate,
so the migration and the activation ship as one auditable unit.

The ``_active_combats: dict[int, CombatInstance]`` keying is also
deferred. In wilderness, the dict would be keyed by the sentinel
``room_id``, meaning two combats at different tiles would collapse into
one instance — but the gate prevents this from being reachable.
``W.2.4`` is the place to address keying.
"""
from __future__ import annotations

import ast
import asyncio
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


COMBAT_PATH = os.path.join(PROJECT_ROOT, "parser", "combat_commands.py")


# ─────────────────────────────────────────────────────────────────────────────
# Test 1: bucket-1 audit string-grep — combat_commands.py mentions source_char
# ─────────────────────────────────────────────────────────────────────────────


class TestBucket1AuditIncludesCombat:
    """The Bucket 1 audit guarantee should now include combat_commands.py.

    This is the test the v41 audit class
    (``TestBucket1SurfacesUseSourceChar`` in
    ``test_wilderness_drop2_phase2.py``) was missing. The simplest
    forgot-to-migrate-anything check: does the file mention
    ``source_char=`` at all?
    """

    def test_combat_commands_uses_source_char(self):
        with open(COMBAT_PATH, encoding="utf-8") as fh:
            assert "source_char=" in fh.read()


# ─────────────────────────────────────────────────────────────────────────────
# Test 2: AST inspection — every targeted call-site passes source_char
# ─────────────────────────────────────────────────────────────────────────────


def _parse_combat_module():
    with open(COMBAT_PATH, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=COMBAT_PATH)


def _calls_in_method(module, class_name: str, method_name: str):
    """Yield ast.Call nodes inside ``ClassName.method_name``."""
    for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                and n.name == class_name]:
        for fn in cls.body:
            is_method = (
                isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == method_name
            )
            if not is_method:
                continue
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    yield node


def _call_target_name(call: ast.Call) -> str | None:
    """Best-effort extraction of the callable's name as a string.
    Handles ``foo()``, ``a.foo()``, ``a.b.foo()``."""
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _has_source_char_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "source_char" for kw in call.keywords)


class TestTargetAcquisitionCallSites:
    """Each known target-acquisition path passes source_char.

    AST-based so it survives reformatting and is robust to comment
    drift. Each test pinpoints a specific class + method + callable
    so a regression points the diagnostician at the exact site.
    """

    @pytest.fixture(scope="class")
    def module(self):
        return _parse_combat_module()

    def test_attack_command_find_target_match_in_room(self, module):
        """AttackCommand._find_target must call match_in_room with
        source_char=. This is the headline guarantee of W.2.3 — it is
        what would prevent combat-at-range if the wilderness combat
        gate is ever lifted.
        """
        calls = [
            c for c in _calls_in_method(module, "AttackCommand", "_find_target")
            if _call_target_name(c) == "match_in_room"
        ]
        assert calls, "AttackCommand._find_target must call match_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "AttackCommand._find_target's match_in_room call(s) "
            "must pass source_char= (W.2.3)"
        )

    def test_attack_command_find_target_sessions_in_room(self, module):
        """The target-session lookup loop in _find_target uses
        sessions_in_room with source_char=. Belt-and-braces: by the
        time we reach this loop, match_in_room (above) already
        filtered, so the candidate is co-located. But future edits
        that add sites to this method shouldn't quietly drop the
        kwarg.
        """
        calls = [
            c for c in _calls_in_method(module, "AttackCommand", "_find_target")
            if _call_target_name(c) == "sessions_in_room"
        ]
        assert calls, "AttackCommand._find_target must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "AttackCommand._find_target's sessions_in_room call(s) "
            "must pass source_char= (W.2.3)"
        )

    def test_challenge_command_match_in_room(self, module):
        """ChallengeCommand has no wilderness gate — its match_in_room
        is the only thing standing between a wilderness PC and a PvP
        challenge they shouldn't be able to issue.
        """
        calls = [
            c for c in _calls_in_method(module, "ChallengeCommand", "execute")
            if _call_target_name(c) == "match_in_room"
        ]
        assert calls, "ChallengeCommand.execute must call match_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls)

    def test_challenge_command_target_session_lookup(self, module):
        calls = [
            c for c in _calls_in_method(module, "ChallengeCommand", "execute")
            if _call_target_name(c) == "sessions_in_room"
        ]
        assert calls, "ChallengeCommand.execute must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls)

    def test_accept_command_match_in_room(self, module):
        calls = [
            c for c in _calls_in_method(module, "AcceptCommand", "execute")
            if _call_target_name(c) == "match_in_room"
        ]
        assert calls, "AcceptCommand.execute must call match_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls)

    def test_accept_command_challenger_session_lookup(self, module):
        calls = [
            c for c in _calls_in_method(module, "AcceptCommand", "execute")
            if _call_target_name(c) == "sessions_in_room"
        ]
        assert calls, "AcceptCommand.execute must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls)

    def test_accept_command_room_broadcast(self, module):
        """Room-wide PvP-consent announcement respects co-location.
        A third PC at a different wilderness tile shouldn't see the
        announcement (information leak)."""
        calls = [
            c for c in _calls_in_method(module, "AcceptCommand", "execute")
            if _call_target_name(c) == "broadcast_to_room"
        ]
        assert calls, "AcceptCommand.execute must call broadcast_to_room"
        assert all(_has_source_char_kwarg(c) for c in calls)

    def test_decline_command_match_in_room(self, module):
        """DeclineCommand only calls match_in_room when args are
        present (named decline). The call must still pass source_char.
        """
        calls = [
            c for c in _calls_in_method(module, "DeclineCommand", "execute")
            if _call_target_name(c) == "match_in_room"
        ]
        assert calls, "DeclineCommand.execute must call match_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls)


# ─────────────────────────────────────────────────────────────────────────────
# Test 3: regression-guard that the W.2.4 gate-lift wasn't reverted.
#
# Pre-W.2.4: this section asserted the wilderness gate was PRESENT
# in AttackCommand.execute (the [NO COMBAT] early-return). W.2.4
# closed the cross-tile combat bug class by re-keying _active_combats
# to (room_id, wilderness_x, wilderness_y) and threading source_char
# through every combat broadcast helper. The gate is no longer needed
# and was removed. This section now asserts the gate is ABSENT.
# ─────────────────────────────────────────────────────────────────────────────


class TestAttackWildernessGateLifted:
    """The AttackCommand wilderness gate was lifted by W.2.4.

    Pre-W.2.4 this class asserted the gate's PRESENCE because
    ``_active_combats`` was keyed by room_id alone — two wilderness
    tiles would have collapsed into one shared combat. W.2.4 re-keyed
    ``_active_combats`` by ``(room_id, wilderness_x, wilderness_y)``
    and migrated every combat broadcast helper to thread the Path B
    ``source_char`` kwarg, so the gate is no longer needed.

    These tests fail loudly if a future edit re-introduces the gate
    (which would block legitimate wilderness combat after the keying
    refactor made it safe).
    """

    @pytest.fixture(scope="class")
    def module(self):
        return _parse_combat_module()

    def test_gate_lifted_no_in_wilderness_early_return(self, module):
        """AttackCommand.execute must NOT contain an
        ``if in_wilderness(char): return`` pattern. The W.2.4 keying
        refactor made the gate unnecessary; re-introducing it would
        block legitimate wilderness combat.
        """
        attack_classes = [n for n in module.body
                          if isinstance(n, ast.ClassDef)
                          and n.name == "AttackCommand"]
        assert attack_classes, "AttackCommand class must exist"
        execute_fns = [
            fn for fn in attack_classes[0].body
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
            and fn.name == "execute"
        ]
        assert execute_fns, "AttackCommand.execute must exist"

        # Walk the execute body for an `if in_wilderness(...)` whose body
        # contains a Return. That's the structural shape of the pre-W.2.4
        # gate. Bare references to in_wilderness (e.g., in a comment-
        # adjacent log call or a defensive check elsewhere) are fine.
        for node in ast.walk(execute_fns[0]):
            if not isinstance(node, ast.If):
                continue
            mentions_in_wild = False
            for sub in ast.walk(node.test):
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Name)
                        and sub.func.id == "in_wilderness"):
                    mentions_in_wild = True
                    break
                if (isinstance(sub, ast.Call)
                        and isinstance(sub.func, ast.Attribute)
                        and sub.func.attr == "in_wilderness"):
                    mentions_in_wild = True
                    break
            if not mentions_in_wild:
                continue
            for body_node in ast.walk(
                    ast.Module(body=node.body, type_ignores=[])):
                if isinstance(body_node, ast.Return):
                    pytest.fail(
                        "AttackCommand.execute has an "
                        "`if in_wilderness(...) → return` early-exit. "
                        "This is the pre-W.2.4 wilderness gate; the "
                        "W.2.4 keying refactor (tuple-keyed "
                        "_active_combats + combat.broadcast_source() "
                        "Path B contract) made the gate unnecessary. "
                        "If a regression re-introduced a gate, the "
                        "keying or broadcast-helper migration may "
                        "have a hole."
                    )

    def test_tuple_key_helper_still_present(self):
        """Belt-and-braces: the gate lift is only safe because the
        tuple-key infrastructure is in place. Asserts the helper is
        importable. If a future drop reverts the keying refactor
        WITHOUT reinstating the gate, this test catches it.
        """
        from parser.combat_commands import _combat_key_for
        assert callable(_combat_key_for), (
            "_combat_key_for missing — the W.2.4 tuple-key "
            "infrastructure has been removed. The wilderness gate "
            "lift relies on the tuple key; without it the "
            "cross-tile combat bug returns.")


# ─────────────────────────────────────────────────────────────────────────────
# Test 4: end-to-end — AttackCommand actually delivers source_char to
# match_in_room when invoked. Proves the AST evidence above isn't
# textual-but-unwired.
# ─────────────────────────────────────────────────────────────────────────────


class TestAttackTargetMatchReceivesSourceChar:
    """When AttackCommand._find_target runs, the match_in_room call it
    makes really does pass source_char to the matcher.

    Done by monkey-patching engine.matching.match_in_room to a recorder
    and calling AttackCommand._find_target with a fabricated ctx.
    """

    def test_match_in_room_called_with_source_char_equal_to_attacker(self):
        async def _check():
            from parser import combat_commands as cc
            from engine import matching as matching_mod

            captured = {}

            class _FakeMatch:
                found = False
                result = None
                candidate = None
                id = None

                def error_message(self, name):
                    return f"no match for {name}"

            async def _fake_match_in_room(*args, **kwargs):
                captured["args"] = args
                captured["kwargs"] = dict(kwargs)
                # Return a NOT_FOUND match so the method exits early
                # via the "you don't see X here" branch — we just need
                # to capture the call arguments.
                from engine.matching import MatchResult
                m = _FakeMatch()
                m.result = MatchResult.NOT_FOUND
                return m

            # Patch the symbol that combat_commands resolves at the
            # local `from engine.matching import match_in_room` site.
            orig = matching_mod.match_in_room
            matching_mod.match_in_room = _fake_match_in_room
            try:
                attacker = {"id": 7, "name": "Attacker", "room_id": 999,
                            "wilderness_region_slug": "dune_sea",
                            "wilderness_x": 5, "wilderness_y": 5}

                # Minimal fake ctx
                class _Sess:
                    character = attacker

                    async def send_line(self, *a, **k): pass

                class _SM:
                    def sessions_in_room(self, room_id, *, source_char=None):
                        return []

                class _Ctx:
                    session = _Sess()
                    session_mgr = _SM()
                    db = None

                attack = cc.AttackCommand()
                result = await attack._find_target(
                    _Ctx(), "Bystander", 999, attacker
                )
                # NOT_FOUND path returns None
                assert result is None
                # Critically: the call was made with source_char=attacker
                assert "source_char" in captured["kwargs"], (
                    "AttackCommand._find_target must pass source_char "
                    "to match_in_room"
                )
                assert captured["kwargs"]["source_char"] is attacker
            finally:
                matching_mod.match_in_room = orig

        asyncio.run(_check())
