# -*- coding: utf-8 -*-
"""
tests/test_w_2_4_combat_wilderness.py — Drop W.2.4.

Closes the wilderness-combat gap left by W.2.3 + W.2.3.1: combat is
now keyed by ``(room_id, wilderness_x, wilderness_y)`` so two combats
at different tiles of the same sentinel sentinel room are distinct
instances; the AttackCommand wilderness gate is lifted; all 19 combat
in-round broadcast helpers thread the Path B ``source_char`` kwarg;
and RespawnCommand uses a pre-respawn char-state snapshot so the
"body carried away" broadcast filters to the wilderness tile char
died at (not the regular respawn room they teleport to).

Five test sections, mirroring the W.2.3 / W.2.3.1 pattern:

  1. ``TestTupleKeying`` — _combat_key_for / _wilderness_anchor_for /
     _get_or_create_combat behaviors on dict+Character objects.
     Two combats at same sentinel + different (wx,wy) are distinct.

  2. ``TestCombatInstanceBroadcastSource`` — CombatInstance carries
     wilderness fields; broadcast_source() returns a Path-B-shaped
     dict.

  3. ``TestCombatHelpersMigrated`` — AST-pinned per-call-site
     assertions that every broadcast/sessions_in_room site in
     combat_commands.py threads source_char=. Backstop: count is 0.

  4. ``TestWildernessGateLifted`` — AttackCommand.execute has no
     [NO COMBAT] string literal and no early-return on
     in_wilderness(char).

  5. ``TestRespawnSnapshot`` — RespawnCommand captures a
     pre-respawn snapshot dict (old_source_char) BEFORE mutating
     char's wilderness fields, and uses it in the old-room
     broadcast.

The counted-leak meta-test pattern (per W.2.3.1) is reused for the
combat_commands.py file: post-W.2.4, the expected unmigrated count
is 0.
"""
from __future__ import annotations

import ast
import os
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


COMBAT_COMMANDS_PATH = PROJECT_ROOT / "parser" / "combat_commands.py"
BUILTIN_COMMANDS_PATH = PROJECT_ROOT / "parser" / "builtin_commands.py"
ENGINE_COMBAT_PATH = PROJECT_ROOT / "engine" / "combat.py"


def _parse(path: Path) -> ast.Module:
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=str(path))


def _calls_in_function(module: ast.Module, fn_name: str):
    for fn in module.body:
        if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == fn_name):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    yield node


def _calls_in_method(module: ast.Module, class_name: str, method_name: str):
    for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                and n.name == class_name]:
        for fn in cls.body:
            if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == method_name):
                for node in ast.walk(fn):
                    if isinstance(node, ast.Call):
                        yield node


def _call_target_name(call: ast.Call):
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _has_kwarg(call: ast.Call, name: str) -> bool:
    return any(kw.arg == name for kw in call.keywords)


# ═════════════════════════════════════════════════════════════════════
# 1. Tuple keying
# ═════════════════════════════════════════════════════════════════════


class TestTupleKeying:
    """``_combat_key_for(char)`` returns the right tuple shape.

    The key invariant is that two PCs at the same wilderness sentinel
    but different (wx, wy) keys produce DIFFERENT combat-instance keys.
    Pre-W.2.4 they would have collapsed onto a single shared
    CombatInstance (the cross-tile combat bug).
    """

    def _import_helpers(self):
        from parser.combat_commands import (
            _combat_key_for,
            _wilderness_anchor_for,
            _get_or_create_combat,
            _remove_combat,
            _active_combats,
        )
        return (_combat_key_for, _wilderness_anchor_for,
                _get_or_create_combat, _remove_combat, _active_combats)

    def test_regular_room_keys_with_none_none(self):
        _combat_key_for, _, _, _, _ = self._import_helpers()
        char = {"id": 1, "room_id": 5,
                "wilderness_region_slug": None,
                "wilderness_x": None, "wilderness_y": None}
        assert _combat_key_for(char) == (5, None, None)

    def test_wilderness_chars_at_same_tile_share_key(self):
        _combat_key_for, _, _, _, _ = self._import_helpers()
        a = {"id": 1, "room_id": 99,
             "wilderness_region_slug": "dune_sea",
             "wilderness_x": 12, "wilderness_y": 18}
        b = {"id": 2, "room_id": 99,
             "wilderness_region_slug": "dune_sea",
             "wilderness_x": 12, "wilderness_y": 18}
        assert _combat_key_for(a) == _combat_key_for(b)
        assert _combat_key_for(a) == (99, 12, 18)

    def test_wilderness_chars_at_different_tiles_have_different_keys(self):
        """The headline W.2.4 invariant: two PCs at the same sentinel
        room_id but different tiles get DIFFERENT keys."""
        _combat_key_for, _, _, _, _ = self._import_helpers()
        a = {"id": 1, "room_id": 99,
             "wilderness_region_slug": "dune_sea",
             "wilderness_x": 12, "wilderness_y": 18}
        b = {"id": 2, "room_id": 99,
             "wilderness_region_slug": "dune_sea",
             "wilderness_x": 35, "wilderness_y": 35}
        assert _combat_key_for(a) != _combat_key_for(b)

    def test_partial_wilderness_state_falls_back_to_regular(self):
        """If wilderness coords are partial (slug present but no x/y, or
        x but no y), the key falls back to (room_id, None, None) so
        the combat doesn't fragment by stale state."""
        _combat_key_for, _, _, _, _ = self._import_helpers()
        # slug present but wx is None
        char = {"id": 1, "room_id": 99,
                "wilderness_region_slug": "dune_sea",
                "wilderness_x": None, "wilderness_y": 18}
        assert _combat_key_for(char) == (99, None, None)
        # wx and wy present but slug is None
        char2 = {"id": 1, "room_id": 99,
                 "wilderness_region_slug": None,
                 "wilderness_x": 12, "wilderness_y": 18}
        assert _combat_key_for(char2) == (99, None, None)

    def test_accepts_character_object_not_just_dict(self):
        """Both dict shape (the normal Path A) and object shape
        (Character / Combatant.char) work."""
        _combat_key_for, _, _, _, _ = self._import_helpers()

        class FakeChar:
            room_id = 7
            wilderness_region_slug = "dune_sea"
            wilderness_x = 4
            wilderness_y = 4
        assert _combat_key_for(FakeChar()) == (7, 4, 4)

    def test_none_char_returns_sentinel_zero(self):
        _combat_key_for, _, _, _, _ = self._import_helpers()
        assert _combat_key_for(None) == (0, None, None)

    def test_get_or_create_combat_seeds_wilderness_anchor(self):
        """``_get_or_create_combat`` reads the char's wilderness
        anchor and seeds the new CombatInstance with it. This is
        what lets combat.broadcast_source() filter the right tile
        without needing a Combatant in scope."""
        (_combat_key_for, _wilderness_anchor_for,
         _get_or_create_combat, _remove_combat, _active_combats
         ) = self._import_helpers()
        # Snapshot existing dict state so this test doesn't pollute.
        old_keys = set(_active_combats.keys())
        try:
            char = {"id": 1001, "room_id": 99,
                    "wilderness_region_slug": "dune_sea",
                    "wilderness_x": 12, "wilderness_y": 18}
            combat = _get_or_create_combat(char)
            assert combat.wilderness_region_slug == "dune_sea"
            assert combat.wilderness_x == 12
            assert combat.wilderness_y == 18
            # The combat is keyed by the tuple, not by raw room_id.
            assert (99, 12, 18) in _active_combats
            assert 99 not in _active_combats  # not the bare int key
        finally:
            # Clean up so we don't pollute other tests in this module.
            for k in list(_active_combats.keys()):
                if k not in old_keys:
                    _active_combats.pop(k, None)

    def test_get_or_create_combat_regular_room_has_none_anchor(self):
        (_combat_key_for, _wilderness_anchor_for,
         _get_or_create_combat, _remove_combat, _active_combats
         ) = self._import_helpers()
        old_keys = set(_active_combats.keys())
        try:
            char = {"id": 1002, "room_id": 5}
            combat = _get_or_create_combat(char)
            assert combat.wilderness_region_slug is None
            assert combat.wilderness_x is None
            assert combat.wilderness_y is None
            assert (5, None, None) in _active_combats
        finally:
            for k in list(_active_combats.keys()):
                if k not in old_keys:
                    _active_combats.pop(k, None)

    def test_remove_combat_accepts_combat_instance(self):
        """_remove_combat must accept a CombatInstance and key off
        its own wilderness fields. This is what auto-resolve +
        ResolveCommand + DisengageCommand use."""
        (_combat_key_for, _,
         _get_or_create_combat, _remove_combat, _active_combats
         ) = self._import_helpers()
        old_keys = set(_active_combats.keys())
        try:
            char = {"id": 1003, "room_id": 99,
                    "wilderness_region_slug": "dune_sea",
                    "wilderness_x": 12, "wilderness_y": 18}
            combat = _get_or_create_combat(char)
            assert (99, 12, 18) in _active_combats
            _remove_combat(combat)
            assert (99, 12, 18) not in _active_combats
        finally:
            for k in list(_active_combats.keys()):
                if k not in old_keys:
                    _active_combats.pop(k, None)


# ═════════════════════════════════════════════════════════════════════
# 2. CombatInstance carries wilderness fields and broadcast_source()
# ═════════════════════════════════════════════════════════════════════


class TestCombatInstanceBroadcastSource:
    """``CombatInstance`` now carries wilderness coords and
    ``broadcast_source()`` returns a Path-B-shaped dict for filtering."""

    def _make_combat(self, wilderness=False):
        from engine.combat import CombatInstance
        from engine.character import SkillRegistry
        reg = SkillRegistry()
        if wilderness:
            return CombatInstance(
                99, reg,
                wilderness_region_slug="dune_sea",
                wilderness_x=12, wilderness_y=18,
            )
        return CombatInstance(5, reg)

    def test_regular_combat_wilderness_fields_are_none(self):
        combat = self._make_combat()
        assert combat.wilderness_region_slug is None
        assert combat.wilderness_x is None
        assert combat.wilderness_y is None

    def test_wilderness_combat_carries_anchor(self):
        combat = self._make_combat(wilderness=True)
        assert combat.wilderness_region_slug == "dune_sea"
        assert combat.wilderness_x == 12
        assert combat.wilderness_y == 18

    def test_broadcast_source_returns_path_b_dict(self):
        """``broadcast_source()`` returns a dict with room_id +
        wilderness_region_slug + wilderness_x + wilderness_y so the
        Path B helpers can filter correctly."""
        combat = self._make_combat(wilderness=True)
        src = combat.broadcast_source()
        assert src["room_id"] == 99
        assert src["wilderness_region_slug"] == "dune_sea"
        assert src["wilderness_x"] == 12
        assert src["wilderness_y"] == 18

    def test_broadcast_source_regular_combat_is_no_op_filter(self):
        """For regular-room combat, broadcast_source() has all
        wilderness fields None, so the Path B helper's in_wilderness()
        check returns False and the broadcast hits everyone in the
        room (same behavior as pre-W.2.4)."""
        combat = self._make_combat()
        src = combat.broadcast_source()
        assert src["room_id"] == 5
        assert src["wilderness_region_slug"] is None
        assert src["wilderness_x"] is None
        assert src["wilderness_y"] is None

        # Defensive: check the actual Path B in_wilderness() returns
        # False for this synthetic dict.
        from engine.wilderness_movement import in_wilderness
        assert not in_wilderness(src)

    def test_broadcast_source_wilderness_combat_in_wilderness(self):
        combat = self._make_combat(wilderness=True)
        from engine.wilderness_movement import in_wilderness
        assert in_wilderness(combat.broadcast_source())


# ═════════════════════════════════════════════════════════════════════
# 3. Combat helpers all thread source_char
# ═════════════════════════════════════════════════════════════════════


class TestCombatHelpersMigrated:
    """Every broadcast/sessions_in_room call site in
    combat_commands.py threads ``source_char=``. AST-pinned per-helper
    plus a counted-leak backstop.
    """

    @pytest.fixture(scope="class")
    def module(self):
        return _parse(COMBAT_COMMANDS_PATH)

    def test_broadcast_events_helper_accepts_source_char(self, module):
        """Helper signature has source_char kwarg."""
        for fn in module.body:
            if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == "_broadcast_events"):
                arg_names = [a.arg for a in fn.args.args]
                kwarg_names = [a.arg for a in fn.args.kwonlyargs]
                assert "source_char" in arg_names + kwarg_names, (
                    "_broadcast_events lost its source_char kwarg")
                return
        pytest.fail("_broadcast_events function not found")

    def test_broadcast_events_paced_helper_accepts_source_char(self, module):
        for fn in module.body:
            if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == "_broadcast_events_paced"):
                arg_names = [a.arg for a in fn.args.args]
                kwarg_names = [a.arg for a in fn.args.kwonlyargs]
                assert "source_char" in arg_names + kwarg_names
                return
        pytest.fail("_broadcast_events_paced function not found")

    def test_send_combat_ended_helper_accepts_source_char(self, module):
        for fn in module.body:
            if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and fn.name == "_send_combat_ended"):
                arg_names = [a.arg for a in fn.args.args]
                kwarg_names = [a.arg for a in fn.args.kwonlyargs]
                assert "source_char" in arg_names + kwarg_names
                return
        pytest.fail("_send_combat_ended function not found")

    def test_send_combat_state_uses_broadcast_source(self, module):
        """``_send_combat_state(combat, ...)`` reads ``combat.broadcast_source()``
        internally. It doesn't take a source_char kwarg because it has
        combat in scope and can pull from there. AST check: does its
        body mention broadcast_source?"""
        text = COMBAT_COMMANDS_PATH.read_text(encoding="utf-8")
        # Find the _send_combat_state function and inspect its
        # source-text body via slicing.
        idx = text.find("async def _send_combat_state(")
        assert idx >= 0, "_send_combat_state not found"
        end = text.find("\nasync def ", idx + 10)
        body = text[idx:end if end > 0 else idx + 2000]
        assert "broadcast_source" in body, (
            "_send_combat_state must call combat.broadcast_source() "
            "to filter to the right tile (W.2.4)")

    def test_zero_unmigrated_broadcast_sites(self):
        """Counted-leak backstop: every broadcast/sessions site in
        combat_commands.py threads source_char (or has it on the
        enclosing function signature). Total: 0 unmigrated."""
        unmigrated = _unmigrated_in(COMBAT_COMMANDS_PATH)
        assert unmigrated == [], (
            f"combat_commands.py has unmigrated broadcast/sessions sites:\n"
            + "\n".join(f"  L{ln} | {snippet}" for ln, snippet in unmigrated))


def _unmigrated_in(path: Path) -> list[tuple[int, str]]:
    """Return (line, snippet) for broadcast/sessions sites without
    source_char= within a 15-line window. Mirrors the W.2.3.1 helper."""
    import re as _re
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out = []
    needles = ("broadcast_to_room(", "broadcast_json_to_room(",
               "sessions_in_room(")
    for i, line in enumerate(lines):
        if any(skip in line for skip in ("log.warning", "log.debug")):
            continue
        if "async def " in line or line.lstrip().startswith("def "):
            continue
        if not any(n in line for n in needles):
            continue
        window = "\n".join(lines[i:i + 15])
        if "source_char=" not in window:
            out.append((i + 1, line.strip()[:80]))
    return out


# ═════════════════════════════════════════════════════════════════════
# 4. AttackCommand wilderness gate is lifted
# ═════════════════════════════════════════════════════════════════════


class TestWildernessGateLifted:
    """AttackCommand.execute no longer refuses wilderness combat.

    Pre-W.2.4 had an early ``return`` inside ``execute`` when
    ``in_wilderness(char)`` was true. W.2.4 removed it. This test
    locks the removal — re-introducing the gate would block legitimate
    wilderness combat after the keying refactor made it safe.
    """

    def test_no_no_combat_string_in_attack_execute(self):
        module = _parse(COMBAT_COMMANDS_PATH)
        for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                    and n.name == "AttackCommand"]:
            for fn in cls.body:
                if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and fn.name == "execute"):
                    continue
                for node in ast.walk(fn):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        assert "[NO COMBAT]" not in node.value, (
                            "AttackCommand.execute still emits a "
                            "[NO COMBAT] gate message — the W.2.4 "
                            "gate-lift was reverted.")

    def test_no_in_wilderness_early_return_in_attack_execute(self):
        """Stronger guard: no ``in_wilderness(char):`` followed by a
        ``return`` within the first ~30 lines of AttackCommand.execute.
        (This is the structural shape of the pre-W.2.4 gate.)

        Detection: walk AttackCommand.execute looking for an If whose
        test is an in_wilderness(...) call and whose body contains a
        bare Return.
        """
        module = _parse(COMBAT_COMMANDS_PATH)
        for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                    and n.name == "AttackCommand"]:
            for fn in cls.body:
                if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and fn.name == "execute"):
                    continue
                for node in ast.walk(fn):
                    if not isinstance(node, ast.If):
                        continue
                    test = node.test
                    # Match: in_wilderness(...) directly OR
                    # any call inside the if-test where _call_target_name
                    # is in_wilderness.
                    is_in_wild = False
                    for sub in ast.walk(test):
                        if (isinstance(sub, ast.Call)
                                and _call_target_name(sub) == "in_wilderness"):
                            is_in_wild = True
                            break
                    if not is_in_wild:
                        continue
                    # If body contains a Return, that's the gate.
                    for body_node in ast.walk(ast.Module(body=node.body,
                                                         type_ignores=[])):
                        if isinstance(body_node, ast.Return):
                            pytest.fail(
                                "AttackCommand.execute has an "
                                "in_wilderness(...) → return early-exit. "
                                "This is the pre-W.2.4 wilderness gate; "
                                "the W.2.4 keying refactor made it "
                                "unnecessary and it should be removed.")

    def test_tuple_key_helper_still_present(self):
        """Belt-and-braces: the gate lift is only safe because the
        tuple-key infrastructure is in place. Asserts the helper is
        still importable."""
        from parser.combat_commands import _combat_key_for
        assert callable(_combat_key_for)


# ═════════════════════════════════════════════════════════════════════
# 5. RespawnCommand pre-respawn snapshot pattern
# ═════════════════════════════════════════════════════════════════════


class TestRespawnSnapshot:
    """RespawnCommand captures char's wilderness anchor BEFORE
    mutating room_id and uses the snapshot for the old-room broadcast.

    Without the snapshot, the old-room broadcast would use char's
    post-respawn coords (regular respawn room), and the Path B filter
    would route nothing to PCs at the wilderness tile where char died.
    """

    @pytest.fixture(scope="class")
    def module(self):
        return _parse(BUILTIN_COMMANDS_PATH)

    def test_respawn_execute_builds_old_source_char_dict(self, module):
        """RespawnCommand.execute must build a dict named (by
        convention) ``old_source_char`` BEFORE the
        ``char["room_id"] = respawn_room`` assignment.

        Detection: walk RespawnCommand.execute, find the first
        Assign node that targets ``char["room_id"]`` with a Name
        value of ``respawn_room``; assert that a prior statement
        (or expression) assigns to ``old_source_char``.
        """
        for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                    and n.name == "RespawnCommand"]:
            for fn in cls.body:
                if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and fn.name == "execute"):
                    continue
                # Find lineno of `char["room_id"] = respawn_room`
                mutate_line = None
                for stmt in ast.walk(fn):
                    if isinstance(stmt, ast.Assign):
                        for tgt in stmt.targets:
                            if (isinstance(tgt, ast.Subscript)
                                    and isinstance(tgt.value, ast.Name)
                                    and tgt.value.id == "char"
                                    and isinstance(tgt.slice, ast.Constant)
                                    and tgt.slice.value == "room_id"):
                                if (isinstance(stmt.value, ast.Name)
                                        and stmt.value.id == "respawn_room"):
                                    mutate_line = stmt.lineno
                                    break
                assert mutate_line is not None, (
                    "RespawnCommand.execute missing the "
                    "char['room_id'] = respawn_room assignment "
                    "— code shape changed; update this test")
                # Find any Assign to a Name 'old_source_char' before
                # the mutation.
                snapshot_line = None
                for stmt in ast.walk(fn):
                    if isinstance(stmt, ast.Assign):
                        for tgt in stmt.targets:
                            if (isinstance(tgt, ast.Name)
                                    and tgt.id == "old_source_char"):
                                if (snapshot_line is None
                                        or stmt.lineno < snapshot_line):
                                    snapshot_line = stmt.lineno
                assert snapshot_line is not None, (
                    "RespawnCommand.execute does not capture an "
                    "old_source_char snapshot before mutating "
                    "char['room_id']. W.2.4 Phase 5 introduced this "
                    "pattern; reverting it re-introduces the "
                    "wilderness-respawn broadcast leak.")
                assert snapshot_line < mutate_line, (
                    f"old_source_char (L{snapshot_line}) is "
                    f"captured AFTER char['room_id'] mutation "
                    f"(L{mutate_line}). The snapshot must precede "
                    f"mutation; otherwise it reads post-respawn "
                    f"coords.")
                return
        pytest.fail("RespawnCommand class not found in builtin_commands.py")

    def test_respawn_old_room_broadcast_uses_snapshot(self, module):
        """The broadcast to the OLD room must thread
        ``source_char=old_source_char`` (not source_char=char)."""
        for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                    and n.name == "RespawnCommand"]:
            for fn in cls.body:
                if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and fn.name == "execute"):
                    continue
                # Find a broadcast_to_room call that passes
                # source_char=old_source_char.
                found = False
                for node in ast.walk(fn):
                    if (isinstance(node, ast.Call)
                            and _call_target_name(node) == "broadcast_to_room"):
                        for kw in node.keywords:
                            if (kw.arg == "source_char"
                                    and isinstance(kw.value, ast.Name)
                                    and kw.value.id == "old_source_char"):
                                found = True
                                break
                        if found:
                            break
                assert found, (
                    "RespawnCommand.execute must have a "
                    "broadcast_to_room call with "
                    "source_char=old_source_char (the pre-respawn "
                    "snapshot). W.2.4 Phase 5 wired this; reverting "
                    "it re-introduces the wilderness-respawn leak.")
                return
        pytest.fail("RespawnCommand class not found")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
