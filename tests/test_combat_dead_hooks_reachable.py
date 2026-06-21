# -*- coding: utf-8 -*-
"""
tests/test_combat_dead_hooks_reachable.py — COMBAT.dead_gated_hooks_inert fix
(2026-06-21).

The DEAD-gated reward hooks inside `_apply_combat_wear` (bounty auto-collect,
anomaly-on-kill, WoW.3a Jedi-weight) were STRUCTURALLY INERT: `resolve_round()`
runs `_cleanup()` which removes DEAD combatants from `combat.combatants` BEFORE
`_apply_combat_wear` iterates, so a just-killed NPC was never present and its
hooks never fired.

Fix: `_apply_combat_wear(combat, ctx, pre_npcs)` now also iterates the
pre-resolution NPC snapshot entries that LEFT combat this round at wound_level
DEAD (killed) — so the existing hooks reach them. This test proves a
just-killed NPC (absent from `combat.combatants` but present in the snapshot)
is now processed (its NPC branch runs → `update_npc` is called for it → the
DEAD-gated hooks reach it).
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


class _ApplyDB:
    def __init__(self, npc_ai=None):
        self.updated = []
        self._ai = npc_ai if npc_ai is not None else {"hostile": True}

    async def get_npc(self, nid):
        return {"id": nid, "name": "Mob", "char_sheet_json": "{}",
                "ai_config_json": json.dumps(self._ai)}

    async def update_npc(self, nid, **f):
        self.updated.append(nid)

    async def get_character(self, cid):
        return None

    async def adjust_credits(self, cid, delta, tag, *, allow_negative=True):
        return 1000


class _ApplyCombat:
    def __init__(self, combatants):
        self.combatants = combatants
        self.room_id = 1
        self.removed = []

    def remove_combatant(self, cid):
        self.removed.append(cid)
        self.combatants.pop(cid, None)


class _ApplyMgr:
    def find_by_character(self, cid):
        return None


def _dead_npc(npc_id=99, killer_id=5):
    from engine.character import WoundLevel
    return types.SimpleNamespace(
        id=npc_id, is_npc=True, name="Mob",
        last_attacker_id=killer_id, actions=[],
        char=types.SimpleNamespace(wound_level=WoundLevel.DEAD),
    )


class TestDeadHooksReachable(unittest.TestCase):
    def test_newly_dead_npc_is_processed(self):
        from parser.combat_commands import _apply_combat_wear
        npc = _dead_npc(99)
        combat = _ApplyCombat({})  # _cleanup already removed the dead NPC
        db = _ApplyDB()
        ctx = types.SimpleNamespace(db=db, session_mgr=_ApplyMgr())
        _run(_apply_combat_wear(combat, ctx, [npc]))
        self.assertIn(
            99, db.updated,
            "a just-killed NPC from the pre-resolution snapshot must be "
            "processed by _apply_combat_wear so the DEAD-gated reward hooks "
            "(bounty/anomaly/WoW.3a) reach it — this is the inertness fix."
        )

    def test_no_snapshot_means_no_extra_processing(self):
        """Backwards-compatible: with no snapshot (pre_npcs=None) only the live
        combatants are processed (no crash, no phantom NPC)."""
        from parser.combat_commands import _apply_combat_wear
        combat = _ApplyCombat({})
        db = _ApplyDB()
        ctx = types.SimpleNamespace(db=db, session_mgr=_ApplyMgr())
        _run(_apply_combat_wear(combat, ctx))  # no pre_npcs
        self.assertEqual(db.updated, [])

    def test_survivor_in_snapshot_not_reprocessed(self):
        """An NPC still alive in combat is processed once (via combatants) and
        excluded from _newly_dead (it's still in combat.combatants)."""
        from parser.combat_commands import _apply_combat_wear
        from engine.character import WoundLevel
        alive = types.SimpleNamespace(
            id=77, is_npc=True, name="Alive", last_attacker_id=5, actions=[],
            char=types.SimpleNamespace(wound_level=WoundLevel.HEALTHY),
        )
        combat = _ApplyCombat({77: alive})
        db = _ApplyDB()
        ctx = types.SimpleNamespace(db=db, session_mgr=_ApplyMgr())
        _run(_apply_combat_wear(combat, ctx, [alive]))
        self.assertEqual(db.updated.count(77), 1)

    def test_call_sites_pass_the_snapshot(self):
        src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8"
        )
        self.assertEqual(
            src.count("await _apply_combat_wear(combat, ctx, _pre_npcs)"), 2,
            "both resolve_round call sites must pass the pre-resolution snapshot "
            "to _apply_combat_wear so the kill hooks reach dead NPCs."
        )
        self.assertIn("_newly_dead", src)


if __name__ == "__main__":
    unittest.main()
