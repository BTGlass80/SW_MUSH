# -*- coding: utf-8 -*-
"""
tests/test_get_drop_redirect_stubs.py — drop 32 newbie-friendly redirect
stubs for get / take / drop.

A new player reflexively types these verbs (from every other text game).
SW_MUSH has no ground-item system (a deliberate design non-goal); the
stubs replace the dead-end "Huh? Unknown command." with a pointer to the
REAL ways items move (examine / buy / loot / craft / give; sell / unequip
/ give). Pure redirects — no state change, no ground-item system.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _registry():
    from parser.commands import CommandRegistry
    from parser.builtin_commands import register_all
    r = CommandRegistry()
    register_all(r)
    return r


def test_get_take_aliases_all_resolve():
    r = _registry()
    from parser.builtin_commands import GetTakeCommand
    for verb in ("get", "take", "pickup", "grab"):
        cmd = r.get(verb)
        assert cmd is not None, f"{verb!r} did not register"
        assert isinstance(cmd, GetTakeCommand), (
            f"{verb!r} resolved to {type(cmd).__name__}, not GetTakeCommand")


def test_drop_aliases_resolve():
    r = _registry()
    from parser.builtin_commands import DropStubCommand
    for verb in ("drop", "discard"):
        cmd = r.get(verb)
        assert cmd is not None, f"{verb!r} did not register"
        assert isinstance(cmd, DropStubCommand)


def test_stubs_do_not_clobber_existing_commands():
    """The new verbs must not collide with existing builtins."""
    r = _registry()
    for verb in ("loot", "give", "sell", "look", "use"):
        assert r.get(verb) is not None, (
            f"existing command {verb!r} was clobbered by the redirect stubs")


def test_help_text_points_to_real_mechanics():
    from parser.builtin_commands import GetTakeCommand, DropStubCommand
    get_help = GetTakeCommand().help_text.lower()
    # get/take should mention the real acquisition paths.
    for word in ("examine", "buy", "loot", "+craft"):
        assert word in get_help, (
            f"get/take help should mention {word!r}")
    drop_help = DropStubCommand().help_text.lower()
    for word in ("sell", "unequip", "give"):
        assert word in drop_help, (
            f"drop help should mention {word!r}")


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
