# -*- coding: utf-8 -*-
"""
tests/test_hunter2_spawn_reward.py

Drop 4b hunter.2 — the live-spawn climax + reward-on-defeat loop for the
roaming Dark-Side bounty hunter.

Surface
-------
1. TestPureBuilders — engine.dsp_hunter (PURE):
   - DSP_HUNTER_AI_KEY constant
   - _dsp_tier boundaries (marked 4-5 / hunted 6-8 / darkest 9+)
   - hunter_combat_sheet: correct shape + stats scale up by tier
   - hunter_ai_config: hostile + quarry marker + is_dsp_hunter + weapon
   - flavor lines non-empty and name the hunter
2. TestRuntimeSpawn — engine.dsp_hunter_runtime.spawn_hunter (FakeDB):
   - creates an NPC in the quarry's room carrying the marker
   - records spawned_npc_id on the pursuit
   - announces arrival to the room
   - idempotent: a live hunter already present is not duplicated
   (_start_hunter_combat is patched out — the combat kick-off is exercised by
    the live combat suite; here we isolate spawn/record/announce.)
3. TestRewardOnDefeat — engine.dsp_hunter_runtime.on_dsp_hunter_killed:
   - a dead hunter clears its quarry's pursuit, removes the row, announces
   - a dead NON-hunter NPC is a no-op (returns False, nothing cleared)
4. TestDespawn — despawn_hunter removes the NPC and clears the spawn ref.
"""
from __future__ import annotations

import asyncio
import json
import unittest
from unittest.mock import patch, AsyncMock

from engine import dsp_hunter as H
from engine import dsp_hunter_runtime as HR


def _run(coro):
    return asyncio.run(coro)


# ─── Fakes ───────────────────────────────────────────────────────────────────

class _Sess:
    def __init__(self, cid):
        self.character = {"id": cid}
        self.sent = []

    async def send_line(self, msg):
        self.sent.append(msg)

    def text(self):
        return "\n".join(self.sent)


class _SM:
    """room_map: {room_id: [sessions]}"""
    def __init__(self, room_map=None):
        self._room = room_map or {}

    def sessions_in_room(self, room_id):
        return list(self._room.get(room_id, []))

    def sessions_for_character(self, cid):
        return [s for ss in self._room.values() for s in ss
                if s.character.get("id") == cid]


class _FakeDB:
    def __init__(self):
        self.npcs = {}
        self._next = 1
        self.pursuits = {}
        self.deleted = []
        self.cleared = []
        self.created = []

    async def create_npc(self, name, room_id, species="Human", description="",
                         char_sheet_json="{}", ai_config_json="{}"):
        nid = self._next
        self._next += 1
        self.npcs[nid] = {
            "id": nid, "name": name, "room_id": room_id, "species": species,
            "description": description, "char_sheet_json": char_sheet_json,
            "ai_config_json": ai_config_json,
        }
        self.created.append(nid)
        return nid

    async def get_npc(self, nid):
        return dict(self.npcs[nid]) if nid in self.npcs else None

    async def delete_npc(self, nid):
        self.deleted.append(nid)
        self.npcs.pop(nid, None)
        return True

    async def get_dsp_pursuit(self, cid):
        return dict(self.pursuits[cid]) if cid in self.pursuits else None

    async def set_dsp_pursuit_spawn(self, cid, nid):
        self.pursuits.setdefault(cid, {"char_id": cid})["spawned_npc_id"] = nid

    async def clear_dsp_pursuit(self, cid):
        self.cleared.append(cid)
        existed = cid in self.pursuits
        self.pursuits.pop(cid, None)
        return existed

    async def get_characters_in_room(self, room_id, *, source_char=None):
        return []

    async def get_room_property(self, room_id, prop, default=None):
        return default


# ═══════════════════════════════════════════════════════════════════════════
# 1. Pure builders
# ═══════════════════════════════════════════════════════════════════════════

class TestPureBuilders(unittest.TestCase):

    def test_marker_constant(self):
        self.assertEqual(H.DSP_HUNTER_AI_KEY, "dsp_hunter_for")

    def test_tier_boundaries(self):
        self.assertEqual(H._dsp_tier(4), "marked")
        self.assertEqual(H._dsp_tier(5), "marked")
        self.assertEqual(H._dsp_tier(6), "hunted")
        self.assertEqual(H._dsp_tier(8), "hunted")
        self.assertEqual(H._dsp_tier(9), "darkest")
        self.assertEqual(H._dsp_tier(20), "darkest")

    def test_combat_sheet_shape(self):
        sheet = H.hunter_combat_sheet(7, 5)
        for k in ("attributes", "skills", "weapon", "move",
                  "force_points", "character_points", "dark_side_points"):
            self.assertIn(k, sheet)
        self.assertIn("blaster", sheet["skills"])
        self.assertIn("dodge", sheet["skills"])

    def test_combat_sheet_scales_up_by_tier(self):
        def blaster_pips(dsp):
            s = H.hunter_combat_sheet(7, dsp)["skills"]["blaster"]
            return int(str(s).split("D")[0])
        self.assertLess(blaster_pips(4), blaster_pips(6))
        self.assertLess(blaster_pips(6), blaster_pips(10))

    def test_ai_config_marker_and_hostile(self):
        ai = H.hunter_ai_config(7, 7, 10, "Varn Kessate")
        self.assertTrue(ai["hostile"])
        self.assertTrue(ai["is_dsp_hunter"])
        self.assertEqual(ai[H.DSP_HUNTER_AI_KEY], 7)
        self.assertIn("weapon", ai)
        self.assertTrue(ai["fallback_lines"])

    def test_flavor_lines_name_hunter(self):
        name = "Varn Kessate"
        self.assertIn(name, H.arrival_line(name))
        self.assertIn(name, H.defeat_line(name, "Hero"))
        self.assertIn("Hero", H.defeat_line(name, "Hero"))
        self.assertTrue(H.collected_line(name))


# ═══════════════════════════════════════════════════════════════════════════
# 2. Runtime spawn
# ═══════════════════════════════════════════════════════════════════════════

class TestRuntimeSpawn(unittest.TestCase):

    def setUp(self):
        self.db = _FakeDB()
        self.quarry = {"id": 7, "room_id": 42}
        self.sess = _Sess(7)
        self.sm = _SM({42: [self.sess]})

    @patch.object(HR, "_start_hunter_combat", new_callable=AsyncMock)
    def test_spawn_creates_marked_npc_and_records(self, _mock_combat):
        npc_id = _run(HR.spawn_hunter(self.db, self.sm, self.quarry, dsp=10))
        self.assertIsNotNone(npc_id)
        row = self.db.npcs[npc_id]
        self.assertEqual(row["room_id"], 42)
        ai = json.loads(row["ai_config_json"])
        self.assertEqual(ai[H.DSP_HUNTER_AI_KEY], 7)
        self.assertTrue(ai["hostile"])
        # recorded on the pursuit
        self.assertEqual(self.db.pursuits[7]["spawned_npc_id"], npc_id)
        # arrival announced to the room
        self.assertTrue(any("trail ends" in m.lower() or "steps out" in m.lower()
                            for m in self.sess.sent))
        # combat kick-off was invoked
        _mock_combat.assert_awaited()

    @patch.object(HR, "_start_hunter_combat", new_callable=AsyncMock)
    def test_spawn_is_idempotent(self, _mock_combat):
        first = _run(HR.spawn_hunter(self.db, self.sm, self.quarry, dsp=10))
        n_after_first = len(self.db.created)
        second = _run(HR.spawn_hunter(self.db, self.sm, self.quarry, dsp=10))
        self.assertEqual(first, second)
        self.assertEqual(len(self.db.created), n_after_first,
                         "a second hunter should not be created in the same room")


# ═══════════════════════════════════════════════════════════════════════════
# 3. Reward-on-defeat
# ═══════════════════════════════════════════════════════════════════════════

class TestRewardOnDefeat(unittest.TestCase):

    def setUp(self):
        self.db = _FakeDB()
        self.sess = _Sess(7)
        self.sm = _SM({42: [self.sess]})

    def _seed_hunter(self, quarry_id=7, room_id=42):
        ai = H.hunter_ai_config(quarry_id, quarry_id, 10, "Varn Kessate")
        nid = self.db._next
        self.db._next += 1
        self.db.npcs[nid] = {
            "id": nid, "name": "Varn Kessate", "room_id": room_id,
            "species": "Human", "description": "",
            "char_sheet_json": "{}", "ai_config_json": json.dumps(ai),
        }
        self.db.pursuits[quarry_id] = {
            "char_id": quarry_id, "hunter_name": "Varn Kessate",
            "spawned_npc_id": nid,
        }
        return nid

    def test_defeat_clears_pursuit_and_removes_row(self):
        nid = self._seed_hunter()
        ok = _run(HR.on_dsp_hunter_killed(
            self.db, nid, {"id": 99, "name": "Hero"}, 42, session_mgr=self.sm))
        self.assertTrue(ok)
        self.assertIn(7, self.db.cleared)
        self.assertIn(nid, self.db.deleted)
        self.assertTrue(any("Hero" in m for m in self.sess.sent))

    def test_non_hunter_npc_is_noop(self):
        nid = self.db._next
        self.db._next += 1
        self.db.npcs[nid] = {
            "id": nid, "name": "City Guard", "room_id": 42,
            "ai_config_json": "{}", "char_sheet_json": "{}",
        }
        ok = _run(HR.on_dsp_hunter_killed(
            self.db, nid, {"id": 99, "name": "Hero"}, 42, session_mgr=self.sm))
        self.assertFalse(ok)
        self.assertEqual(self.db.cleared, [])
        self.assertEqual(self.db.deleted, [])


# ═══════════════════════════════════════════════════════════════════════════
# 4. Despawn
# ═══════════════════════════════════════════════════════════════════════════

class TestDespawn(unittest.TestCase):

    def test_despawn_removes_and_clears_ref(self):
        db = _FakeDB()
        db.npcs[5] = {"id": 5, "name": "Varn Kessate", "room_id": 42,
                      "ai_config_json": "{}", "char_sheet_json": "{}"}
        db.pursuits[7] = {"char_id": 7, "spawned_npc_id": 5}
        _run(HR.despawn_hunter(db, 5, quarry_id=7))
        self.assertIn(5, db.deleted)
        self.assertIsNone(db.pursuits[7]["spawned_npc_id"])


if __name__ == "__main__":
    unittest.main()
