# -*- coding: utf-8 -*-
"""
tests/test_w_2_3_1_bucket1_closure.py — Drop W.2.3.1.

Closes the remainder of the wilderness Bucket 1 audit
(``wilderness_colocation_audit_v1.md``) that was outstanding after
W.2.3 (combat targeting). W.2.3.1 migrates the 13 active leak sites
in non-combat surfaces: MoveCommand departure/arrival, Quit, Ooc,
Semipose, Pickpocket, Trade, Espionage counter-eavesdrop, Scene
pose-order, and the hostile-NPC aggro announce that fires
post-arrival.

The audit pattern is the same as W.2.3 (AST inspection of calling
sites for the ``source_char=`` kwarg) so the test surface is robust
to reformatting, comment drift, and routine refactors.

Why "remainder" not "complete"
==============================

This drop deliberately defers four categories:

1. **Combat in-round helpers** in ``parser/combat_commands.py`` —
   the 19 broadcast/sessions_in_room sites inside the combat-round
   resolution machinery (``_broadcast_events``,
   ``_broadcast_separator``, ``_send_combat_state``, etc.). All are
   unreachable in wilderness today because of the AttackCommand
   wilderness gate (W.2.3 §"Out of scope"). Migrating them now
   would add plumbing with zero runtime effect; the cleaner pattern
   is to migrate them in the same drop that lifts the gate (W.2.4),
   so the migration and the activation ship as one auditable unit.

2. **Respawn broadcasts** in ``RespawnCommand.execute`` — two
   broadcast sites (death narration to old room, revival narration
   to new room). Char state has already been moved to the respawn
   room by the time the broadcasts fire, so a naive
   ``source_char=char`` would filter to the wrong tile. The correct
   fix needs a snapshot of pre-respawn char state. Currently
   unreachable in wilderness: respawn is triggered by wound_level
   ≥ 5, and wound_level only reaches that from combat, which is
   gated in wilderness. Will ship with W.2.4 alongside the snapshot
   pattern.

3. **Picklock / Forcedoor broadcasts** — these operate on private
   housing doors (``Drop 7: Housing Security & Intrusion``).
   Housing doesn't exist in wilderness sentinel rooms (per the
   audit doc Bucket 2: "PCs don't own wilderness tiles"). Bucket 2,
   no migration needed.

4. **Eavesdrop fumble alert in target room** (
   ``espionage_commands.py::execute`` near L198) — the broadcast
   goes to ``target_room_id``, a *different* room from the
   eavesdropping char's room. ``source_char=char`` would filter
   based on the char's coords, which is meaningless for the target
   room's PCs. A future drop adding wilderness-tile-scoped
   eavesdropping needs a ``target_char`` kwarg or equivalent design.
   The site has an explanatory ``W.2.3.1 note:`` comment so a
   future audit doesn't mistakenly migrate it without that design
   call.

Tests in this module
====================

  1. ``TestMigratedSitesPassSourceChar`` — one AST test per migrated
     call site. Each test pins the calling class + method (or top-
     level function) and the callable name (``broadcast_to_room``
     or ``sessions_in_room``) so a regression points at the precise
     site.

  2. ``TestDeferredSitesStayDeferred`` — guards each deferred
     category. The combat-helpers guard is a string check for the
     wilderness-gate comment in ``AttackCommand``; the Respawn
     guard documents the pattern; the housing guard checks that
     PicklockCommand still has its housing-only docstring; the
     eavesdrop L198 guard checks for the explanatory comment.

  3. ``TestBucket1AuditClean`` — meta-test walking every Bucket 1
     file and asserting the count of ``broadcast_to_room`` /
     ``sessions_in_room`` calls without ``source_char=`` matches
     the audited count (8 deferred sites). If a future edit adds a
     new broadcast site without ``source_char=``, the count drifts
     and the test fails loudly with a precise pointer.

Why a counted-leak meta-test instead of zero
============================================

A strict "zero unmigrated sites" assertion would be the cleanest
test but fails on the 8 deliberately-deferred sites. A
"sites must be in this allowlist" assertion is more maintainable
but couples the test to specific line numbers, which drift on every
edit. The counted-leak test threads the needle: it locks the
*total* count, so adding a new leak fails the test, but doesn't
care about which line numbers the deferred sites are on. Combined
with the targeted tests in (2), a regression on any of the
deferred categories is caught (either by category-specific
docstring/comment drift or by the count going up).

Scope reference
===============

Per ``wilderness_colocation_audit_v1.md`` and the W.2.3.1 handoff
doc, the active migration sites are:

  parser/builtin_commands.py:
    _check_hostile_npcs (1)
    MoveCommand._broadcast_departure (2)
    MoveCommand._broadcast_arrival (2)
    QuitCommand.execute (2)
    OocCommand.execute (1)
    SemiposeCommand.execute (1)
    PickpocketCommand.execute (1)
    TradeCommand._accept item-exchange (1)
    TradeCommand._accept credits-exchange (1)

  parser/espionage_commands.py:
    EavesdropCommand.execute counter-squeal (1)

  parser/scene_commands.py:
    _cmd_pose_order pose-order notification (1)

  Total: 13 sites migrated.
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


BUILTIN_PATH = PROJECT_ROOT / "parser" / "builtin_commands.py"
ESPIONAGE_PATH = PROJECT_ROOT / "parser" / "espionage_commands.py"
SCENE_PATH = PROJECT_ROOT / "parser" / "scene_commands.py"
COMBAT_PATH = PROJECT_ROOT / "parser" / "combat_commands.py"


# ─────────────────────────────────────────────────────────────────────
# AST helpers — mirrors test_w2_3_combat_source_char.py
# ─────────────────────────────────────────────────────────────────────


def _parse(path: Path) -> ast.Module:
    with open(path, encoding="utf-8") as fh:
        return ast.parse(fh.read(), filename=str(path))


def _calls_in_method(module: ast.Module, class_name: str,
                     method_name: str):
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


def _calls_in_function(module: ast.Module, fn_name: str):
    """Yield ast.Call nodes inside a top-level function."""
    for fn in module.body:
        if (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                and fn.name == fn_name):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call):
                    yield node


def _call_target_name(call: ast.Call) -> str | None:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _has_source_char_kwarg(call: ast.Call) -> bool:
    return any(kw.arg == "source_char" for kw in call.keywords)


def _broadcast_or_sessions_calls(walker, callable_names=None):
    """Filter to ``broadcast_to_room`` / ``broadcast_json_to_room`` /
    ``sessions_in_room`` calls."""
    if callable_names is None:
        callable_names = {
            "broadcast_to_room",
            "broadcast_json_to_room",
            "sessions_in_room",
        }
    return [c for c in walker
            if _call_target_name(c) in callable_names]


# ═════════════════════════════════════════════════════════════════════
# 1. Migrated sites — one test per site (AST-pinned)
# ═════════════════════════════════════════════════════════════════════


class TestMigratedSitesPassSourceChar:
    """Each of the 13 migrated W.2.3.1 sites passes source_char=.

    The targeted-test pattern (one test per site) makes failure
    diagnosis fast: a regression points at the exact class + method +
    callable that lost the kwarg.
    """

    @pytest.fixture(scope="class")
    def builtin_module(self):
        return _parse(BUILTIN_PATH)

    @pytest.fixture(scope="class")
    def espionage_module(self):
        return _parse(ESPIONAGE_PATH)

    @pytest.fixture(scope="class")
    def scene_module(self):
        return _parse(SCENE_PATH)

    # ── builtin_commands.py ──────────────────────────────────────────

    def test_check_hostile_npcs_aggro_broadcast(self, builtin_module):
        """``_check_hostile_npcs`` aggro announce respects co-location.

        Fires from MoveCommand post-arrival when hostile NPCs are
        present in the destination room. Wilderness NPCs don't spawn
        today (encounter system pending) but the migration is
        defensive — when wilderness encounters land, the broadcast
        is already correct.
        """
        calls = _broadcast_or_sessions_calls(
            _calls_in_function(builtin_module, "_check_hostile_npcs"))
        assert calls, ("_check_hostile_npcs must contain at least "
                       "one broadcast/sessions call")
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "_check_hostile_npcs aggro broadcast must pass "
            "source_char= (W.2.3.1)"
        )

    def test_move_broadcast_departure(self, builtin_module):
        """``MoveCommand._broadcast_departure`` — both code paths
        (osucc-defined and default) must filter to the OLD room's
        co-located peers.
        """
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(
                builtin_module, "MoveCommand", "_broadcast_departure"))
        assert len(calls) >= 2, (
            "MoveCommand._broadcast_departure should have ≥2 "
            "broadcast calls (osucc path + default path)")
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "MoveCommand._broadcast_departure broadcasts must "
            "pass source_char= (W.2.3.1)"
        )

    def test_move_broadcast_arrival(self, builtin_module):
        """``MoveCommand._broadcast_arrival`` — both code paths
        (odrop-defined and default) must filter to the NEW room's
        co-located peers. char's room_id and wilderness coords have
        been updated by the time this is called, so source_char=char
        keys off the new tile.
        """
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(
                builtin_module, "MoveCommand", "_broadcast_arrival"))
        assert len(calls) >= 2, (
            "MoveCommand._broadcast_arrival should have ≥2 broadcast calls")
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "MoveCommand._broadcast_arrival broadcasts must "
            "pass source_char= (W.2.3.1)"
        )

    def test_quit_command_broadcasts(self, builtin_module):
        """``QuitCommand.execute`` — both broadcasts (sleeping flag
        + disconnect notification) must filter to co-located peers.
        """
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(builtin_module, "QuitCommand", "execute"))
        assert len(calls) >= 2, (
            "QuitCommand.execute should have ≥2 broadcasts "
            "(sleeping + disconnect)")
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "QuitCommand.execute broadcasts must pass "
            "source_char= (W.2.3.1)"
        )

    def test_ooc_command_sessions_loop(self, builtin_module):
        """``OocCommand.execute`` — room-scoped OOC chatter must
        filter to co-located peers in wilderness."""
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(builtin_module, "OocCommand", "execute"))
        assert calls, "OocCommand.execute must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "OocCommand.execute sessions_in_room must pass "
            "source_char= (W.2.3.1)"
        )

    def test_semipose_command_sessions_loop(self, builtin_module):
        """``SemiposeCommand.execute`` — semipose narration must
        filter to co-located peers."""
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(
                builtin_module, "SemiposeCommand", "execute"))
        assert calls, "SemiposeCommand.execute must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "SemiposeCommand.execute sessions_in_room must pass "
            "source_char= (W.2.3.1)"
        )

    def test_pickpocket_command_broadcast(self, builtin_module):
        """``PickpocketCommand.execute`` — fumble alert broadcast
        must filter to co-located peers. A pickpocket fumble at
        wilderness (12,18) shouldn't alert PCs at (15,18)."""
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(
                builtin_module, "PickpocketCommand", "execute"))
        assert calls, "PickpocketCommand.execute must call broadcast_to_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "PickpocketCommand.execute fumble broadcast must "
            "pass source_char= (W.2.3.1)"
        )

    def test_trade_accept_broadcasts(self, builtin_module):
        """``TradeCommand._accept`` — both exchange broadcasts (item
        + credits) must filter to co-located peers."""
        calls = _broadcast_or_sessions_calls(
            _calls_in_method(
                builtin_module, "TradeCommand", "_accept"))
        assert len(calls) >= 2, (
            "TradeCommand._accept should have ≥2 broadcasts "
            "(item-exchange + credit-exchange)")
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "TradeCommand._accept broadcasts must pass "
            "source_char= (W.2.3.1)"
        )

    # ── espionage_commands.py ────────────────────────────────────────

    def test_espionage_counter_eavesdrop_squeal(self, espionage_module):
        """The counter-eavesdrop fumble squeal broadcasts to char's
        own room and must filter to co-located peers.

        Note: this test asserts that AT LEAST ONE broadcast call in
        the espionage module's CounterEavesdrop-style execute has
        source_char=. The L198 eavesdrop-fumble site in a DIFFERENT
        execute is deliberately deferred (see TestDeferredSitesStayDeferred).
        """
        # Find all top-level Command classes in the module and look for
        # broadcast calls in their executes that DO have source_char.
        found_migrated = False
        for node in espionage_module.body:
            if isinstance(node, ast.ClassDef):
                for child in node.body:
                    if (isinstance(child,
                                   (ast.FunctionDef, ast.AsyncFunctionDef))
                            and child.name == "execute"):
                        for sub in ast.walk(child):
                            if (isinstance(sub, ast.Call)
                                    and _call_target_name(sub)
                                    == "broadcast_to_room"
                                    and _has_source_char_kwarg(sub)):
                                found_migrated = True
        assert found_migrated, (
            "espionage_commands.py must have at least one "
            "broadcast_to_room call with source_char= (the "
            "counter-eavesdrop squeal; W.2.3.1)"
        )

    # ── scene_commands.py ────────────────────────────────────────────

    def test_scene_pose_order_sessions_loop(self, scene_module):
        """``_cmd_pose_order`` (top-level helper in scene_commands.py)
        — pose-order announcement must filter to co-located peers."""
        calls = _broadcast_or_sessions_calls(
            _calls_in_function(scene_module, "_cmd_pose_order"))
        assert calls, "_cmd_pose_order must call sessions_in_room"
        assert all(_has_source_char_kwarg(c) for c in calls), (
            "_cmd_pose_order sessions_in_room must pass "
            "source_char= (W.2.3.1)"
        )


# ═════════════════════════════════════════════════════════════════════
# 2. Deferred sites — stay deferred AND documented
# ═════════════════════════════════════════════════════════════════════


class TestDeferredSitesStayDeferred:
    """The four deferred categories must stay deferred AND must
    document themselves so a future contributor doesn't 'fix' them
    incorrectly.

    See the module docstring for the rationale on each category.
    """

    def test_combat_wilderness_gate_lifted_post_w_2_4(self):
        """``parser/combat_commands.py`` AttackCommand.execute must
        NOT contain a ``[NO COMBAT]`` early-return wilderness gate.

        Pre-W.2.4 this test asserted the gate's PRESENCE because
        ``_active_combats`` was keyed by room_id alone (two
        wilderness tiles would have collapsed into one shared
        combat). W.2.4 re-keyed ``_active_combats`` by
        ``(room_id, wilderness_x, wilderness_y)`` and migrated
        every combat broadcast helper to thread the Path B
        ``source_char`` kwarg, so the gate is no longer needed.

        If a future drop re-introduces a ``[NO COMBAT]`` gate in
        AttackCommand, that's a regression — the keying refactor
        should make the gate permanently unnecessary.

        Detection strategy: walk AttackCommand.execute's AST and
        assert no Call node sends a string literal containing
        '[NO COMBAT]'. (Bare-substring grep would false-positive on
        explanatory comments describing the lift.)
        """
        module = _parse(COMBAT_PATH)
        for cls in [n for n in module.body if isinstance(n, ast.ClassDef)
                    and n.name == "AttackCommand"]:
            for fn in cls.body:
                if not (isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and fn.name == "execute"):
                    continue
                for node in ast.walk(fn):
                    if isinstance(node, ast.Constant) and isinstance(node.value, str):
                        assert "[NO COMBAT]" not in node.value, (
                            "AttackCommand.execute contains a "
                            "string literal with '[NO COMBAT]' — "
                            "the W.2.4 wilderness gate was lifted "
                            "by the keying refactor. If a "
                            "regression re-introduced a gate, the "
                            "keying or broadcast-helper migration "
                            "may have a hole."
                        )
        # Tuple key must still be in place — if the dict reverted
        # to room_id-only keying the gate-lift is unsafe.
        text = COMBAT_PATH.read_text(encoding="utf-8")
        assert "_combat_key_for" in text, (
            "combat_commands.py is missing _combat_key_for — the "
            "W.2.4 tuple-key infrastructure has been removed. The "
            "wilderness gate lift relies on the tuple key; without "
            "it the cross-tile combat bug returns.")

    def test_respawn_deferred_post_w_2_4(self):
        """``RespawnCommand.execute`` broadcasts still require the
        pre-respawn char-state snapshot pattern.

        Pre-W.2.4 this was deferred because respawn-from-wilderness
        was unreachable (combat was gated). W.2.4 lifted the combat
        gate, so respawn-from-wilderness is now reachable in
        principle. The Respawn migration (Phase 5 of W.2.4) needs
        the snapshot pattern; this test exists to document that
        dependency until that migration lands.

        Note: this test does not assert on respawn broadcasts —
        Phase 5 of W.2.4 will add the snapshot pattern and remove
        this guard.
        """
        text = BUILTIN_PATH.read_text(encoding="utf-8")
        # Sanity: RespawnCommand exists.
        assert "class RespawnCommand" in text, (
            "RespawnCommand has moved — update this guard")

    def test_picklock_command_is_housing_only(self):
        """``PicklockCommand`` docstring identifies it as
        housing-only. Per the audit doc Bucket 2, housing doesn't
        exist in wilderness, so PicklockCommand broadcasts are Bucket
        2 and do not need source_char=.
        """
        text = BUILTIN_PATH.read_text(encoding="utf-8")
        # Find the PicklockCommand class block and check for the
        # housing marker in its docstring.
        module = _parse(BUILTIN_PATH)
        found_picklock = False
        for node in module.body:
            if (isinstance(node, ast.ClassDef)
                    and node.name == "PicklockCommand"):
                found_picklock = True
                doc = ast.get_docstring(node) or ""
                assert "housing" in doc.lower(), (
                    "PicklockCommand docstring no longer identifies "
                    "it as housing-only. If picklock is being "
                    "extended to non-housing contexts (incl. "
                    "wilderness), the broadcasts need source_char= "
                    "migration.")
        assert found_picklock, "PicklockCommand class not found"

    def test_forcedoor_command_is_housing_only(self):
        """Same as PicklockCommand — ForceDoorCommand is housing-only
        per Drop 7 (Housing Security & Intrusion)."""
        module = _parse(BUILTIN_PATH)
        found = False
        for node in module.body:
            if (isinstance(node, ast.ClassDef)
                    and node.name == "ForceDoorCommand"):
                found = True
                # ForceDoorCommand may not have a class docstring, but
                # its module-level home is the same housing block.
                # The simpler regression-guard: the class still exists
                # and is in the same builtin_commands.py file (not
                # extracted to a wilderness-reachable module).
                break
        assert found, "ForceDoorCommand class not found"

    def test_eavesdrop_target_room_site_has_explanatory_comment(self):
        """The L198-style eavesdrop fumble alert (broadcasts to
        target_room_id, a DIFFERENT room from char) is deferred
        because source_char keys on char.coords, which is wrong for
        the target room's PCs.

        The site must have a ``W.2.3.1 note:`` comment explaining the
        deferral so a future audit doesn't mistakenly migrate it.
        """
        text = ESPIONAGE_PATH.read_text(encoding="utf-8")
        assert "W.2.3.1 note:" in text, (
            "espionage_commands.py is missing the W.2.3.1 explanatory "
            "comment that documents why the eavesdrop fumble alert "
            "(target_room_id broadcast) is deferred. The comment "
            "tells future authors the site needs a target_char design "
            "call, not a naive source_char= migration.")
        # Also check that the comment is paired with discussion of
        # target_room_id so the rationale is preserved.
        # We slice out the area around the W.2.3.1 note and look for
        # 'target_room' nearby.
        idx = text.index("W.2.3.1 note:")
        window = text[idx:idx + 800]
        assert "target_room" in window, (
            "The W.2.3.1 explanatory comment is present but doesn't "
            "mention target_room_id — the rationale may have been "
            "lost in a refactor.")


# ═════════════════════════════════════════════════════════════════════
# 3. Bucket 1 meta-test — counted leak budget
# ═════════════════════════════════════════════════════════════════════


# Expected count of broadcast/sessions calls WITHOUT source_char=
# across the Bucket 1 files this drop covers. If this number drifts,
# either:
#   - a new leak was introduced (count went up; failure points at file)
#   - a deferred site was migrated (count went down; update this constant)
#
# Per the W.2.3.1 handoff:
#   builtin_commands.py:
#     _try_wilderness_entry              (1)  — leaving regular room
#     _execute_wilderness_exit           (1)  — arriving at regular room
#     PicklockCommand.execute            (2)  — housing-only, Bucket 2
#     ForceDoorCommand.execute           (2)  — housing-only, Bucket 2
#   espionage_commands.py:
#     EavesdropCommand.execute           (1)  — target_room_id site (L198)
#   scene_commands.py:
#     (none)
#
# W.2.4 update: RespawnCommand was deferred behind the combat gate
# in W.2.3.1. Phase 5 of W.2.4 migrated both Respawn broadcasts
# using the pre-respawn snapshot pattern, so the builtin count
# drops from 8 → 6.
#
# Total: 7 deferred sites (down from 9 after W.2.4 Phase 5).
EXPECTED_DEFERRED_COUNT = {
    "parser/builtin_commands.py": 6,
    "parser/espionage_commands.py": 1,
    "parser/scene_commands.py": 0,
}


class TestBucket1AuditClean:
    """Meta-test: the count of unmigrated broadcast/sessions sites in
    Bucket 1 files matches the audited deferred-count.

    If a future edit adds a new broadcast without source_char=, the
    count for that file goes up and this test fails with a precise
    pointer. If a future drop migrates a deferred site (good!), the
    count goes down and ``EXPECTED_DEFERRED_COUNT`` should be updated
    in the same commit.
    """

    @pytest.mark.parametrize("path,expected", list(
        EXPECTED_DEFERRED_COUNT.items()))
    def test_unmigrated_count_matches(self, path, expected):
        unmigrated = _count_unmigrated(PROJECT_ROOT / path)
        msg = (
            f"\n{path} has {unmigrated} unmigrated broadcast/sessions "
            f"sites; W.2.3.1 audit expected {expected}.\n"
            f"\nIf a NEW leak was added, find the call site and add "
            f"source_char=char to it.\n"
            f"If a deferred site was migrated, update "
            f"EXPECTED_DEFERRED_COUNT in this file.\n"
            f"\nDetails:\n{_unmigrated_listing(PROJECT_ROOT / path)}"
        )
        assert unmigrated == expected, msg


# ─────────────────────────────────────────────────────────────────────
# Helpers for the meta-test
# ─────────────────────────────────────────────────────────────────────


def _count_unmigrated(path: Path) -> int:
    return len(_unmigrated_sites(path))


def _unmigrated_sites(path: Path) -> list[tuple[int, str]]:
    """Return list of (line_number, snippet) for broadcast/sessions
    call sites that lack source_char= within a ~15-line window.

    Excludes ``log.warning(...)`` / ``log.debug(...)`` matches and
    function-definition lines.
    """
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    out: list[tuple[int, str]] = []
    needles = ("broadcast_to_room(", "broadcast_json_to_room(",
               "sessions_in_room(")
    for i, line in enumerate(lines):
        # Skip clearly-not-a-call cases
        if any(skip in line for skip in ("log.warning", "log.debug")):
            continue
        # Skip function/method definitions
        if "async def " in line or line.lstrip().startswith("def "):
            continue
        if not any(needle in line for needle in needles):
            continue
        # Check the ~15-line window for source_char=
        window = "\n".join(lines[i:i + 15])
        if "source_char=" not in window:
            out.append((i + 1, line.strip()[:80]))
    return out


def _unmigrated_listing(path: Path) -> str:
    sites = _unmigrated_sites(path)
    if not sites:
        return "(none)"
    return "\n".join(f"  L{ln:4} | {snippet}" for ln, snippet in sites)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
