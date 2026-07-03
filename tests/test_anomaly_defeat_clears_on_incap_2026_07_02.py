# -*- coding: utf-8 -*-
"""tests/test_anomaly_defeat_clears_on_incap_2026_07_02.py

Regression for EVENT.anomaly_clear_on_defeat (2026-07-02).

A live break-it playthrough of the Cult of the Hollow Sun found its combat
stages (and, by the shared code path, Ember Court / Ashen Hand and every
`resolution:"combat"` wilderness anomaly) were **unwinnable through the normal
`attack` loop**: combat ends the instant the last hostile can no longer act
(``CombatInstance.is_over`` -> ``active_combatants`` -> ``can_act_now`` fires at
``>= INCAPACITATED``), and the room/combat cleanup removes the downed NPC at that
same threshold — but the anomaly kill-hook in ``parser/combat_commands.py``
(``_apply_combat_wear``) only fired the clear/phase-advance at ``>= DEAD``. Since
a finishing blow rarely one-shots straight to DEAD, the last zealot was
incapacitated, vanished, and the stage stuck forever.

The existing tier-2 tests (test_syn7b) call ``award_combat_anomaly_reward``
DIRECTLY, so they cover the anomaly ENGINE but never exercised the PARSER gate —
this file closes that gap by driving the real ``_apply_combat_wear`` loop with
NPCs left at INCAPACITATED (not DEAD), and asserting the anomaly advances.

The fix aligns the anomaly clear with the game's own victory semantics (the
bounty capture-chain + combat achievements already treat incapacitation as a
win). Uses a representative tier-2 combat anomaly (``hutt_smuggling_convoy``);
the Hollow Sun stages ``hollow_sun_shrine_assault`` / ``hollow_sun_hierophant``
route through the identical ``_apply_combat_wear`` -> ``award_combat_anomaly_reward``
path, so this guards them too.

Run: python -m pytest tests/test_anomaly_defeat_clears_on_incap_2026_07_02.py
"""
from __future__ import annotations

import asyncio
import json
import random
import sqlite3
import sys
import time
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.character import WoundLevel


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Minimal aiosqlite-shaped DB: enough for resolve_anomaly (investigate spawn)
#    + _apply_combat_wear (get/update npc, per-participant payout). Mirrors the
#    proven test_syn7b _MiniDB, plus update_npc (the one method the parser path
#    needs that the engine-only tests never did). ─────────────────────────────
class _MiniDB:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE rooms (id INTEGER PRIMARY KEY, name TEXT, zone_id INTEGER,
                                wilderness_region_id TEXT, properties TEXT);
            CREATE TABLE zones (id INTEGER PRIMARY KEY, name TEXT,
                                properties TEXT DEFAULT '{"security":"lawless"}');
            CREATE TABLE characters (id INTEGER PRIMARY KEY, name TEXT,
                                attributes TEXT DEFAULT '{}', skills TEXT DEFAULT '{}',
                                credits INTEGER DEFAULT 0, inventory TEXT DEFAULT '{}',
                                faction_id TEXT DEFAULT 'independent', room_id INTEGER);
            CREATE TABLE npcs (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                                room_id INTEGER, species TEXT DEFAULT 'Human',
                                description TEXT DEFAULT '', char_sheet_json TEXT DEFAULT '{}',
                                ai_config_json TEXT DEFAULT '{}');
            """
        )
        self.conn.commit()

    # generic
    async def fetchall(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    async def fetchone(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()

    # rooms / zones
    def seed_zone(self, *, zone_id=1, name="Tatooine", security="lawless"):
        self.conn.execute("INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
                          (zone_id, name, json.dumps({"security": security})))
        self.conn.commit()

    def seed_room(self, *, room_id, zone_id=1, wilderness_region_id=None, name="Dune Site"):
        self.conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self.conn.commit()

    async def get_room(self, room_id):
        return await self.fetchone("SELECT * FROM rooms WHERE id = ?", (room_id,))

    # characters
    def seed_character(self, *, char_id=1, faction_id="independent", room_id=10, credits=0):
        self.conn.execute(
            "INSERT INTO characters (id, name, faction_id, room_id, credits, attributes, skills) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (char_id, f"Char{char_id}", faction_id, room_id, credits,
             json.dumps({"survival": "3D", "blaster": "3D"}), json.dumps({})))
        self.conn.commit()

    async def get_character(self, char_id):
        return await self.fetchone("SELECT * FROM characters WHERE id = ?", (char_id,))

    async def get_characters_in_room(self, room_id):
        return await self.fetchall("SELECT * FROM characters WHERE room_id = ?", (room_id,))

    async def adjust_credits(self, char_id, delta, source, **kw):
        if char_id == 0:
            return 0
        self.conn.execute("UPDATE characters SET credits = credits + ? WHERE id = ?",
                          (delta, char_id))
        self.conn.commit()
        row = await self.get_character(char_id)
        return int(row["credits"]) if row else 0

    async def save_character(self, char_id, **kw):
        if not kw:
            return
        cols = ", ".join(f"{k} = ?" for k in kw)
        self.conn.execute(f"UPDATE characters SET {cols} WHERE id = ?",
                          list(kw.values()) + [char_id])
        self.conn.commit()

    # npcs
    async def create_npc(self, name, room_id, species="Human", description="",
                         char_sheet_json="{}", ai_config_json="{}"):
        cur = self.conn.execute(
            "INSERT INTO npcs (name, room_id, species, description, char_sheet_json, "
            "ai_config_json) VALUES (?, ?, ?, ?, ?, ?)",
            (name, room_id, species, description, char_sheet_json, ai_config_json))
        self.conn.commit()
        return cur.lastrowid

    async def get_npc(self, npc_id):
        return await self.fetchone("SELECT * FROM npcs WHERE id = ?", (npc_id,))

    async def update_npc(self, npc_id, **kw):
        if not kw:
            return
        cols = ", ".join(f"{k} = ?" for k in kw)
        self.conn.execute(f"UPDATE npcs SET {cols} WHERE id = ?",
                          list(kw.values()) + [npc_id])
        self.conn.commit()

    async def get_npcs_in_room(self, room_id):
        return await self.fetchall("SELECT * FROM npcs WHERE room_id = ?", (room_id,))


def _make_char(char_id=1, room_id=10, faction_id="independent"):
    return {"id": char_id, "name": f"Char{char_id}", "faction_id": faction_id,
            "room_id": room_id, "credits": 0,
            "attributes": json.dumps({"survival": "3D", "blaster": "3D"}),
            "skills": json.dumps({}), "inventory": json.dumps({})}


# ── Stub combat pieces: _apply_combat_wear's NPC branch only reads
#    c.is_npc / c.id / c.name / c.char.wound_level / c.last_attacker_id. ───────
class _StubChar:
    def __init__(self, wound_level):
        self.wound_level = wound_level


class _StubCombatant:
    def __init__(self, npc_id, wound_level, attacker_id, name="Hostile"):
        self.id = npc_id
        self.is_npc = True
        self.name = name
        self.char = _StubChar(wound_level)
        self.last_attacker_id = attacker_id
        self.actions = []


class _StubCombat:
    def __init__(self, combatants, room_id=10):
        self.combatants = {c.id: c for c in combatants}
        self.room_id = room_id


class _StubSessionMgr:
    def find_by_character(self, cid):
        return None


TEMPLATE = "hutt_smuggling_convoy"   # tier-2, 2-phase; proven in test_syn7b
REGION = "tatooine_dune_sea"
ROOM_ID = 10
KILLER_ID = 1


class _Base(unittest.TestCase):
    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()

    def tearDown(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        _reset_state_for_tests()

    def _engage_phase0(self):
        """Spawn a tier-2 anomaly + investigate to spawn phase-0 hostiles.
        Returns (db, anomaly, phase0_npc_ids)."""
        from engine.wilderness_anomalies import (
            _anomalies, WildernessAnomaly, TIER2_DURATION_SECS, resolve_anomaly,
        )
        db = _MiniDB()
        db.seed_zone(zone_id=1)
        db.seed_room(room_id=ROOM_ID, zone_id=1, wilderness_region_id=REGION)
        db.seed_character(char_id=KILLER_ID, room_id=ROOM_ID, credits=0)
        now = time.time()
        a = WildernessAnomaly(
            id=1, region_slug=REGION, zone_id=1, template_key=TEMPLATE,
            anchor_room_id=ROOM_ID, tier=2, expiry=now + TIER2_DURATION_SECS,
        )
        _anomalies[REGION] = [a]
        _run(resolve_anomaly(db, _make_char(KILLER_ID, ROOM_ID), 1))
        self.assertEqual(a.current_phase, 0)
        self.assertGreaterEqual(len(a.spawned_npc_ids), 1)
        return db, a, list(a.spawned_npc_ids)

    def _apply_wear(self, db, npc_ids, wound_level):
        """Drive the REAL parser death-scan/reward loop with every phase NPC
        left at ``wound_level`` (as it is after a finishing blow)."""
        import parser.combat_commands as CC
        combat = _StubCombat(
            [_StubCombatant(nid, wound_level, KILLER_ID) for nid in npc_ids],
            room_id=ROOM_ID,
        )
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        _run(CC._apply_combat_wear(combat, ctx, None))
        return combat


class TestAnomalyClearsOnDefeat(_Base):

    def test_incapacitated_last_hostile_advances_the_stage(self):
        """THE REGRESSION: the last phase-0 hostile left at INCAPACITATED (not
        DEAD) must advance the anomaly to phase 1 through the parser hook.
        Pre-fix this stuck at phase 0 forever (the break-it blocker)."""
        db, a, phase0 = self._engage_phase0()
        self._apply_wear(db, phase0, WoundLevel.INCAPACITATED)
        self.assertEqual(
            a.current_phase, 1,
            "an INCAPACITATED final phase-0 hostile did not advance the stage "
            "-- the DEAD-only gate regressed",
        )
        # Phase 1 spawned a fresh, distinct hostile set.
        self.assertTrue(a.spawned_npc_ids)
        for nid in a.spawned_npc_ids:
            self.assertNotIn(nid, phase0)

    def test_mortally_wounded_last_hostile_also_advances(self):
        """MORTALLY_WOUNDED (5) is likewise can't-act / defeated -> advances."""
        db, a, phase0 = self._engage_phase0()
        self._apply_wear(db, phase0, WoundLevel.MORTALLY_WOUNDED)
        self.assertEqual(a.current_phase, 1)

    def test_dead_last_hostile_still_advances(self):
        """Backward-compat: a literal DEAD clear still advances (the fix only
        LOWERS the threshold, it does not break the original path)."""
        db, a, phase0 = self._engage_phase0()
        self._apply_wear(db, phase0, WoundLevel.DEAD)
        self.assertEqual(a.current_phase, 1)

    def test_merely_stunned_hostile_does_NOT_advance(self):
        """Guard against over-lowering the gate: a STUNNED (1) NPC can still act
        and is NOT defeated, so it must NOT clear the phase."""
        db, a, phase0 = self._engage_phase0()
        self._apply_wear(db, phase0, WoundLevel.STUNNED)
        self.assertEqual(
            a.current_phase, 0,
            "a merely-STUNNED hostile wrongly advanced the stage -- the gate "
            "was lowered too far (should be >= INCAPACITATED)",
        )

    def test_healthy_hostile_does_NOT_advance(self):
        """A HEALTHY hostile (still fully in the fight) never clears the phase."""
        db, a, phase0 = self._engage_phase0()
        self._apply_wear(db, phase0, WoundLevel.HEALTHY)
        self.assertEqual(a.current_phase, 0)


if __name__ == "__main__":
    unittest.main()
