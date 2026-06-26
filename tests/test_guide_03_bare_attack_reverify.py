# -*- coding: utf-8 -*-
"""Guide_03 re-verify: the §3 "Declaring Actions" combat-targeting prose must
stay reconciled with the live bare-`attack` auto-target behaviour shipped in
`cd90ddc` (FUN2 combat first-fight, parser/combat_commands.py).

Why this guard exists
---------------------
The FUN2 path-to-first-fun pass made bare ``attack`` (no target) auto-target the
first hostile NPC in the room, so a newcomer following the tutorial panel's
*literal* hint — which just says ``attack`` — lands a hit instead of getting a
usage error.  Guide_03 §3 is where a player learns the ``attack`` command, and
it had drifted behind that change: the command table read ``attack <target>``
("Attack a specific target") and the targeting prose opened "Type the target's
name after ``attack``", implying a target is mandatory.  A new player reading
the guide would never learn that the bare ``attack`` the tutorial tells them to
type actually works — exactly the test-invisible, new-player-facing drift the
GUIDES re-verify lane exists to catch.

This test pins, all against HEAD so an engine revert/retune fails loudly here:

1. the live ``AttackCommand`` still exposes ``_auto_target_hostile`` and it
   returns the first *hostile* NPC's name (and only a hostile one), so the
   guide's "auto-targets the nearest hostile" claim is real;
2. ``_auto_target_hostile`` returns ``None`` when the room holds no hostile, so
   the guide's "shows you the usage instead of guessing" claim is real;
3. producer -> consumer: ``AttackCommand.execute`` genuinely routes a bare
   ``attack`` through ``_auto_target_hostile`` and falls back to ``_usage_help``
   on ``None``;
4. the guide prose teaches the bare-`attack` auto-target (and that you only ever
   auto-target a real threat, never a bystander/friendly/player), and the
   command table shows the target is optional.
"""
import asyncio
import json
import os
import re

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_03_Ground_Combat.md")
COMBAT_CMD_PATH = os.path.join(PROJECT_ROOT, "parser", "combat_commands.py")

os.environ.setdefault("SW_ERA", "clone_wars")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@pytest.fixture(scope="module")
def guide_text():
    return _read(GUIDE_PATH)


def _hostile_npc(name, npc_id=1):
    return {"id": npc_id, "name": name,
            "ai_config_json": json.dumps({"hostile": True})}


def _friendly_npc(name, npc_id=99):
    return {"id": npc_id, "name": name,
            "ai_config_json": json.dumps({"hostile": False})}


def _auto_target(npcs):
    """Call AttackCommand._auto_target_hostile with a stub ctx/db. Returns the
    chosen NPC name, or None."""
    from unittest.mock import AsyncMock, MagicMock
    from parser.combat_commands import AttackCommand

    db = MagicMock()
    db.get_npcs_in_room = AsyncMock(return_value=list(npcs))
    ctx = MagicMock()
    ctx.db = db
    char = {"id": 1, "room_id": 200}
    return _run(AttackCommand()._auto_target_hostile(ctx, 200, char))


# ── 1. The live engine auto-targets a hostile (and only a hostile) ────────────
class TestEngineAutoTargetsHostile:
    def test_helper_present(self):
        from parser.combat_commands import AttackCommand
        assert callable(getattr(AttackCommand(), "_auto_target_hostile", None))

    def test_picks_the_first_hostile(self):
        name = _auto_target([_hostile_npc("B1 Sim Droid Alpha", 1),
                             _hostile_npc("B1 Sim Droid Bravo", 2)])
        assert name == "B1 Sim Droid Alpha"

    def test_skips_friendlies_for_a_hostile(self):
        name = _auto_target([_friendly_npc("Cantina Patron", 5),
                             _hostile_npc("Tusken Raider", 6)])
        assert name == "Tusken Raider"

    def test_none_when_no_hostile(self):
        # No hostile -> None -> execute() falls through to usage help.
        assert _auto_target([_friendly_npc("Cantina Patron", 5)]) is None
        assert _auto_target([]) is None


# ── 2. Producer -> consumer: bare attack routes through auto-target ───────────
def test_execute_routes_bare_attack_through_auto_target():
    """A bare `attack` (no args) must call _auto_target_hostile and, on None,
    fall back to usage help — the guide claims both behaviours."""
    src = _read(COMBAT_CMD_PATH)
    assert "if not ctx.args:" in src
    assert "self._auto_target_hostile(" in src, (
        "bare `attack` must route through _auto_target_hostile; if this seam "
        "moved, re-verify Guide_03 §3"
    )
    # On no hostile, the path must show usage rather than silently no-op.
    assert "_usage_help(" in src


# ── 3. The guide prose teaches the bare-attack auto-target ────────────────────
class TestGuideTeachesBareAttack:
    def test_subsection_present(self, guide_text):
        assert "You don't have to name a target" in guide_text

    def test_teaches_bare_attack_picks_nearest_hostile(self, guide_text):
        assert "bare `attack`" in guide_text
        assert "nearest hostile" in guide_text

    def test_teaches_tutorial_hint_is_enough(self, guide_text):
        # The tutorial panel's literal hint is just `attack` — say so.
        assert "tutorial panel" in guide_text

    def test_teaches_safe_when_no_hostile(self, guide_text):
        # Never auto-targets a bystander/friendly/player; shows usage instead.
        assert "never a bystander" in guide_text

    def test_command_table_marks_target_optional(self, guide_text):
        # The table row must no longer imply a target is mandatory.
        assert "`attack [target]`" in guide_text
        assert not re.search(r"\|\s*`attack <target>`\s*\|\s*Attack a specific",
                             guide_text)
