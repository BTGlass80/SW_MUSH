# -*- coding: utf-8 -*-
"""
tests/test_qa_postship_fixes.py — fixes from the 2026-06-21 post-ship QA
break-it campaign (the new combat-reward + interior-map code).

  1. HIGH — the bounty kill hook attributed the kill by scanning THIS round's
     combatant actions (cleared each round by roll_initiative), so a bounty
     target that bled out from a mortal wound on a later round paid no bounty,
     and multi-attacker / killer-also-died kills mis-attributed. Now uses
     c.last_attacker_id (consistent with the anomaly / WoW / mob-grind hooks).
  2. HIGH/MED — tests/harness.py boot omitted titles.ensure_schema, so the
     mob-grind milestone title grant silently failed in-process. Added.
  3. MED — Vela Niree's room was "Chalmun's Cantina - Main Room" (no such
     room); corrected to "... - Main Bar".
  4. LOW — hunting_log_view / on_huntable_kill crashed on a non-numeric
     hunting_log value; guarded with _safe_int.
  5. LOW — AreaGeometry.is_interior now emitted in the to_dict wire payload.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest.mock as mock
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# 1. Bounty hook now attributes via last_attacker_id ─────────────────────
class _BountyDB:
    async def get_npc(self, n):
        return {"id": n, "name": "Mark", "char_sheet_json": "{}",
                "ai_config_json": json.dumps({"hostile": True,
                                              "is_bounty_target": True})}

    async def update_npc(self, n, **f):
        pass

    async def get_character(self, c):
        return None

    async def adjust_credits(self, c, d, t, *, allow_negative=True):
        return 1000


class _BountyCombat:
    def __init__(self):
        self.combatants = {}
        self.room_id = 1

    def remove_combatant(self, c):
        self.combatants.pop(c, None)


class _Mgr:
    def find_by_character(self, c):
        return None


class TestBountyAttribution(unittest.TestCase):
    def test_bounty_fires_via_last_attacker_when_no_action_this_round(self):
        """The QA HIGH repro: a dead bounty target whose killer did NOT
        re-attack this round (combatants empty / actions cleared) must STILL
        pay the bounty, attributed by last_attacker_id."""
        from engine.character import WoundLevel
        from parser.combat_commands import _apply_combat_wear
        npc = types.SimpleNamespace(
            id=99, is_npc=True, name="Mark", last_attacker_id=8, actions=[],
            char=types.SimpleNamespace(wound_level=WoundLevel.DEAD),
        )
        combat = _BountyCombat()  # killer PC NOT present (bled out / left)
        ctx = types.SimpleNamespace(db=_BountyDB(), session_mgr=_Mgr())
        calls = []

        class _Board:
            async def notify_target_killed(self, npc_id, killer_id, db):
                calls.append((npc_id, killer_id))
                return None  # no contract → graceful no-op downstream

        with mock.patch("engine.bounty_board.get_bounty_board",
                        return_value=_Board()):
            _run(_apply_combat_wear(combat, ctx, [npc]))
        self.assertEqual(
            calls, [(99, 8)],
            "the bounty hook must attribute the kill to last_attacker_id (8), "
            "even when no PC re-attacked the downed NPC this round"
        )

    def test_bounty_hook_no_longer_scans_round_actions(self):
        src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8"
        )
        # The bounty hook must use last_attacker_id, not a combatants scan.
        self.assertIn("_killer_id = c.last_attacker_id", src)


# 2. Harness titles schema ──────────────────────────────────────────────
class TestHarnessTitleSchema(unittest.TestCase):
    def test_harness_inits_titles_schema(self):
        src = (PROJECT_ROOT / "tests" / "harness.py").read_text(encoding="utf-8")
        self.assertIn("from engine.titles import ensure_schema", src)


# 3. Vela Niree room ────────────────────────────────────────────────────
class TestVelaRoom(unittest.TestCase):
    def test_vela_room_is_a_real_room(self):
        src = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
               / "npcs_cw_additions.yaml").read_text(encoding="utf-8")
        self.assertIn('room: "Chalmun\'s Cantina - Main Bar"', src)
        self.assertNotIn("Chalmun's Cantina - Main Room", src)


# 4. hunting_log_view tolerates a corrupt blob ──────────────────────────
class TestHuntingViewRobust(unittest.TestCase):
    def test_non_numeric_log_does_not_crash(self):
        from engine.hunting_rewards import hunting_log_view, HUNT_LOG_KEY
        char = {"id": 5, "attributes": json.dumps(
            {HUNT_LOG_KEY: {"kills": "ten", "daily_credits": None,
                            "day": "2026-06-21"}})}
        v = hunting_log_view(char, day_stamp="2026-06-21")  # must not raise
        self.assertEqual(v["kills"], 0)
        self.assertEqual(v["daily_credits"], 0)

    def test_safe_int_helper(self):
        from engine.hunting_rewards import _safe_int
        self.assertEqual(_safe_int("ten"), 0)
        self.assertEqual(_safe_int(None), 0)
        self.assertEqual(_safe_int("42"), 42)
        self.assertEqual(_safe_int(7), 7)


# 5. is_interior in the wire payload ────────────────────────────────────
class TestIsInteriorWire(unittest.TestCase):
    def test_interior_flag_emitted(self):
        from engine.area_loader import load_area_geometry
        g = load_area_geometry("tatooine.chalmuns_cantina")
        self.assertTrue(g.is_interior)
        self.assertTrue(g.to_dict().get("is_interior"))

    def test_non_interior_omits_flag(self):
        from engine.area_loader import AreaGeometry, MapBounds
        g = AreaGeometry(
            schema_version=1, area_key="x.y", display_name="x", planet="p",
            era="clone_wars", default_terrain="sand", palette="p",
            bounds=MapBounds(0, 0, 1, 1), districts=[], rooms=[], exits=[],
            exit_paths={}, labels=[], landmarks=[], is_interior=False,
        )
        self.assertNotIn("is_interior", g.to_dict())


if __name__ == "__main__":
    unittest.main()
