# -*- coding: utf-8 -*-
"""tests/test_anomaly_wave_reengage_2026_07_03.py

Regression + feature test for EVENT.wave_reengage (2026-07-03).

Multi-phase (tier>=2) combat anomalies — including EVERY staged-cult combat
stage (Hollow Sun / Ember Court / Ashen Hand / Iron Veil / Drowned Choir, all
two-wave) — used to STUTTER between waves: clearing wave 1 spawned wave 2 into
the room, but combat then ended (no live hostiles left in the CombatInstance)
and the player had to type ``attack`` again to engage the fresh wave.

The fix threads the just-spawned wave's NPC ids back from the anomaly kill hook
(``award_combat_anomaly_reward`` -> ``_advance_to_next_phase``) through
``_apply_combat_wear``'s return value, and ``_reengage_anomaly_wave`` adds those
hostiles to the SAME live combat so the fight chains wave -> wave. This mirrors
the existing ``_check_city_guard_engagement`` mid-combat NPC-injection path.

These tests drive the REAL ``parser/combat_commands._apply_combat_wear`` loop
(the seam the engine-only tier-2 tests never hit) plus the REAL
``engine.combat.CombatInstance`` for the injection, using a representative
tier-2 combat anomaly (``hutt_smuggling_convoy``: phase 0 = 2 thugs, phase 1 =
3 hostiles). The staged-cult combat stages route through the identical path, so
this guards them too.

Run: python -m pytest tests/test_anomaly_wave_reengage_2026_07_03.py
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from engine.character import WoundLevel, Character


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Minimal aiosqlite-shaped DB (same shape proven in
#    test_anomaly_defeat_clears_on_incap_2026_07_02). ──────────────────────────
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

    async def fetchall(self, sql, params=()):
        return [dict(r) for r in self.conn.execute(sql, params).fetchall()]

    async def fetchone(self, sql, params=()):
        row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    async def execute(self, sql, params=()):
        return self.conn.execute(sql, params)

    async def commit(self):
        self.conn.commit()

    def seed_zone(self, *, zone_id=1, name="Nar Shaddaa", security="lawless"):
        self.conn.execute("INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
                          (zone_id, name, json.dumps({"security": security})))
        self.conn.commit()

    def seed_room(self, *, room_id, zone_id=1, wilderness_region_id=None, name="Site"):
        self.conn.execute(
            "INSERT INTO rooms (id, name, zone_id, wilderness_region_id) VALUES (?, ?, ?, ?)",
            (room_id, name, zone_id, wilderness_region_id))
        self.conn.commit()

    async def get_room(self, room_id):
        return await self.fetchone("SELECT * FROM rooms WHERE id = ?", (room_id,))

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


# ── Stub combat pieces for driving _apply_combat_wear's NPC branch. ───────────
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
    """Just enough for the wear loop: a combatants dict + a room id."""
    def __init__(self, combatants, room_id=10):
        self.combatants = {c.id: c for c in combatants}
        self.room_id = room_id


class _StubSessionMgr:
    def find_by_character(self, cid):
        return None


TEMPLATE = "hutt_smuggling_convoy"   # tier-2, 2 phases (2 thugs -> 3 hostiles)
REGION = "tatooine_dune_sea"
ROOM_ID = 10
KILLER_ID = 1


class _Base(unittest.TestCase):
    def setUp(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        import parser.combat_commands as CC
        _reset_state_for_tests()
        CC._npc_behaviors.clear()

    def tearDown(self):
        from engine.wilderness_anomalies import _reset_state_for_tests
        import parser.combat_commands as CC
        _reset_state_for_tests()
        CC._npc_behaviors.clear()

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
        self.assertEqual(len(a.spawned_npc_ids), 2)   # phase 0 = 2 thugs
        return db, a, list(a.spawned_npc_ids)

    def _apply_wear(self, db, npc_ids, wound_level):
        """Drive the REAL parser death-scan/reward loop with the given NPCs at
        ``wound_level``. Returns (returned_wave_ids, stub_combat)."""
        import parser.combat_commands as CC
        combat = _StubCombat(
            [_StubCombatant(nid, wound_level, KILLER_ID) for nid in npc_ids],
            room_id=ROOM_ID,
        )
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        wave_ids = _run(CC._apply_combat_wear(combat, ctx, None))
        return wave_ids, combat


class TestApplyWearReportsNextWave(_Base):

    def test_cleared_phase_returns_next_wave_ids(self):
        """THE FEATURE: clearing wave 0 (both thugs INCAPACITATED) makes
        _apply_combat_wear RETURN the freshly-spawned wave-1 hostile ids so the
        caller can chain them into the same combat."""
        db, a, phase0 = self._engage_phase0()
        wave_ids, _ = self._apply_wear(db, phase0, WoundLevel.INCAPACITATED)
        # The stage advanced to phase 1...
        self.assertEqual(a.current_phase, 1)
        self.assertEqual(len(a.spawned_npc_ids), 3)          # phase 1 = 3 hostiles
        # ...and the reported wave ids ARE exactly that fresh, distinct wave.
        self.assertEqual(sorted(wave_ids), sorted(a.spawned_npc_ids))
        for nid in wave_ids:
            self.assertNotIn(nid, phase0)

    def test_mid_phase_kill_reports_no_wave(self):
        """Killing only ONE of the two phase-0 thugs does NOT advance the wave,
        so no re-engage ids are reported (empty list -> caller no-ops)."""
        db, a, phase0 = self._engage_phase0()
        # Incap only the first thug; the second stays HEALTHY in the room.
        import parser.combat_commands as CC
        combat = _StubCombat(
            [_StubCombatant(phase0[0], WoundLevel.INCAPACITATED, KILLER_ID)],
            room_id=ROOM_ID,
        )
        # Keep the survivor on the anomaly so spawned_npc_ids isn't emptied.
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        wave_ids = _run(CC._apply_combat_wear(combat, ctx, None))
        self.assertEqual(a.current_phase, 0)                 # no advance
        self.assertEqual(wave_ids, [])                       # nothing to chain

    def test_final_phase_clear_reports_no_wave(self):
        """Clearing the FINAL phase pays out and reports NO wave (there is no
        next wave to chain — the boss kill ends the encounter)."""
        db, a, phase0 = self._engage_phase0()
        # Advance to the final phase (phase 1).
        w1, _ = self._apply_wear(db, phase0, WoundLevel.INCAPACITATED)
        self.assertEqual(a.current_phase, 1)
        # Now clear the final phase.
        w2, _ = self._apply_wear(db, w1, WoundLevel.INCAPACITATED)
        self.assertTrue(a.resolved)
        self.assertEqual(w2, [])                             # no phantom wave


class TestReengageIntoLiveCombat(_Base):

    def _live_combat_with_pc(self):
        """A real CombatInstance holding one healthy PC (so _combat_finished can
        evaluate a genuine PC-vs-NPC fight)."""
        from engine.combat import CombatInstance
        from engine.character import SkillRegistry
        combat = CombatInstance(room_id=ROOM_ID, skill_reg=SkillRegistry())
        pc = Character.from_npc_sheet(
            KILLER_ID,
            {"name": "Hero", "attributes": {"dexterity": "3D", "perception": "3D"}},
        )
        c = combat.add_combatant(pc)
        c.is_npc = False
        return combat

    def test_next_wave_is_added_to_the_same_combat(self):
        """THE INTEGRATION: the reported wave-1 ids get injected into a live
        CombatInstance as active NPC combatants, and the fight is NOT finished
        (it chains wave -> wave instead of ending)."""
        import parser.combat_commands as CC
        db, a, phase0 = self._engage_phase0()
        wave_ids, _ = self._apply_wear(db, phase0, WoundLevel.INCAPACITATED)
        self.assertEqual(len(wave_ids), 3)

        combat = self._live_combat_with_pc()
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        # Before: only the PC is in this combat -> a lone PC reads as finished.
        self.assertTrue(CC._combat_finished(combat))

        _run(CC._reengage_anomaly_wave(combat, ctx, wave_ids))

        # Each fresh hostile is now a live, active NPC combatant in THIS combat.
        for nid in wave_ids:
            comb = combat.get_combatant(nid)
            self.assertIsNotNone(comb, f"wave NPC {nid} was not added to combat")
            self.assertTrue(comb.is_npc)
            self.assertIsNotNone(comb.char)
            self.assertTrue(comb.char.can_act_now())
            self.assertIn(nid, CC._npc_behaviors)   # behavior registered
        # PC + 3 hostiles who can all act -> a real fight, NOT finished.
        self.assertFalse(CC._combat_finished(combat))

    def test_reengage_is_idempotent(self):
        """Re-running the injection with the same ids adds nothing new (the
        NPCs are already combatants) — defensive against a double-fire."""
        import parser.combat_commands as CC
        db, a, phase0 = self._engage_phase0()
        wave_ids, _ = self._apply_wear(db, phase0, WoundLevel.INCAPACITATED)
        combat = self._live_combat_with_pc()
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        _run(CC._reengage_anomaly_wave(combat, ctx, wave_ids))
        n_after_first = len(combat.combatants)
        _run(CC._reengage_anomaly_wave(combat, ctx, wave_ids))
        self.assertEqual(len(combat.combatants), n_after_first)

    def test_reengage_empty_is_noop(self):
        """An empty wave list is a safe no-op (the common non-anomaly path)."""
        import parser.combat_commands as CC
        db, _a, _p = self._engage_phase0()
        combat = self._live_combat_with_pc()
        ctx = types.SimpleNamespace(db=db, session_mgr=_StubSessionMgr())
        before = len(combat.combatants)
        _run(CC._reengage_anomaly_wave(combat, ctx, []))
        self.assertEqual(len(combat.combatants), before)


if __name__ == "__main__":
    unittest.main()
