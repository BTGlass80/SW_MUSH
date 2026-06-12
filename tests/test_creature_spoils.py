# -*- coding: utf-8 -*-
"""
tests/test_creature_spoils.py — Sourcebook Enrichment Lane A **Phase C**
(creature loot-on-kill / field-dressing). Closes economy-audit v1 #16.

Two layers:
  1. PURE resolver tests for ``engine.creature_spoils`` (no DB, no skill RNG).
  2. Death-hook integration tests for
     ``engine.wilderness_encounter_runtime.on_wild_creature_killed`` using a
     fake DB + a patched ``perform_skill_check`` (deterministic success/fail).
     These exercise the **real** creature library (the authored YAML harvest
     blocks) and the **real** ``crafting.add_resource`` sink, so the whole
     spawn-data → spoils → inventory path is verified end-to-end.

Run: ``python3 -m unittest tests.test_creature_spoils``
(No aiosqlite needed — the DB is faked.)
"""
from __future__ import annotations

import asyncio
import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from engine import creature_spoils as CS
from engine import wilderness_encounter_runtime as WR


def _run(coro):
    return asyncio.run(coro)


# ─── Pure resolver tests ─────────────────────────────────────────────────────

class TestSpoilsResolver(unittest.TestCase):

    def _cre(self, **harvest):
        """A minimal creature dict with a harvest block."""
        return {"id": "test_beast", "name": "Test Beast", "harvest": harvest}

    def test_has_spoils_true_false(self):
        self.assertTrue(CS.creature_has_spoils(self._cre(good="hide")))
        self.assertFalse(CS.creature_has_spoils({"id": "x", "name": "X"}))
        self.assertFalse(CS.creature_has_spoils({"harvest": {}}))   # no good
        self.assertFalse(CS.creature_has_spoils({"harvest": {"note": "x"}}))
        self.assertFalse(CS.creature_has_spoils(None))
        self.assertFalse(CS.creature_has_spoils("not a dict"))

    def test_resource_type_default_override_and_t5_reject(self):
        # default → organic
        self.assertEqual(CS.spoils_resource_type(self._cre(good="h")), "organic")
        # valid override
        self.assertEqual(
            CS.spoils_resource_type(self._cre(good="h", resource="chemical")),
            "chemical")
        # a T5 wilderness-only type must NOT be mintable by a beast → organic
        self.assertEqual(
            CS.spoils_resource_type(
                self._cre(good="h", resource="composite_chitin")),
            "organic")
        self.assertEqual(
            CS.spoils_resource_type(
                self._cre(good="h", resource="kyber_shard_minor")),
            "organic")
        # an unknown/typo type → organic
        self.assertEqual(
            CS.spoils_resource_type(self._cre(good="h", resource="bogus")),
            "organic")
        # case-insensitive
        self.assertEqual(
            CS.spoils_resource_type(self._cre(good="h", resource="ORGANIC")),
            "organic")

    def test_resolve_none_when_no_harvest(self):
        self.assertIsNone(CS.resolve_spoils({"id": "x", "name": "X"}, 5))
        self.assertIsNone(CS.resolve_spoils(None, 5))

    def test_quantity_scales_with_margin_and_caps(self):
        c = self._cre(good="hide")          # base yield 1
        self.assertEqual(CS.resolve_spoils(c, 0)["quantity"], 1)   # base
        self.assertEqual(CS.resolve_spoils(c, 5)["quantity"], 1)   # <6 → +0
        self.assertEqual(CS.resolve_spoils(c, 6)["quantity"], 2)   # +1
        self.assertEqual(CS.resolve_spoils(c, 12)["quantity"], 3)  # +2
        self.assertEqual(CS.resolve_spoils(c, 99)["quantity"], 3)  # capped at +2

    def test_quantity_respects_base_yield(self):
        c = {"id": "big", "name": "Big", "harvest": {"good": "hide", "yield": 2}}
        self.assertEqual(CS.resolve_spoils(c, 0)["quantity"], 2)
        self.assertEqual(CS.resolve_spoils(c, 6)["quantity"], 3)
        self.assertEqual(CS.resolve_spoils(c, 12)["quantity"], 4)  # 2 + cap(2)

    def test_quality_scales_and_clamps_to_spoils_ceiling(self):
        c = self._cre(good="hide")
        self.assertEqual(CS.resolve_spoils(c, 0)["quality"], 40.0)
        self.assertEqual(CS.resolve_spoils(c, 5)["quality"], 55.0)   # 40+3*5
        # economy guard: quality caps at the spoils ceiling (65), NOT 100 —
        # a field-dressing can never reach premium grade.
        self.assertEqual(CS.resolve_spoils(c, 25)["quality"],
                         CS._SPOILS_QUALITY_CEILING)
        self.assertEqual(CS.resolve_spoils(c, 999)["quality"],
                         CS._SPOILS_QUALITY_CEILING)
        # a (defensively passed) negative margin clamps to 0 → base quality
        self.assertEqual(CS.resolve_spoils(c, -10)["quality"], 40.0)
        self.assertEqual(CS.resolve_spoils(c, -10)["quantity"], 1)

    def test_spoils_can_never_satisfy_t5_recipes(self):
        """The whole economy-safety argument in one assertion: no spoils stack,
        at any margin, can reach T5_MIN_QUALITY — so creature grinding can
        never feed the premium recipe tier or undercut the harvest economy."""
        from engine.crafting import T5_MIN_QUALITY
        self.assertLess(CS._SPOILS_QUALITY_CEILING, T5_MIN_QUALITY)
        c = {"id": "big", "name": "Big",
             "harvest": {"good": "hide", "yield": 2}}
        for margin in (0, 5, 10, 20, 50, 500):
            self.assertLess(CS.resolve_spoils(c, margin)["quality"],
                            T5_MIN_QUALITY)

    def test_difficulty_default_and_override(self):
        self.assertEqual(CS.spoils_difficulty(self._cre(good="h")),
                         CS.SPOILS_DIFFICULTY)
        self.assertEqual(CS.spoils_difficulty(self._cre(good="h", difficulty=10)),
                         10)
        # invalid / non-positive → default
        self.assertEqual(
            CS.spoils_difficulty(self._cre(good="h", difficulty="x")),
            CS.SPOILS_DIFFICULTY)
        self.assertEqual(
            CS.spoils_difficulty(self._cre(good="h", difficulty=0)),
            CS.SPOILS_DIFFICULTY)

    def test_resolve_carries_good_and_resource(self):
        c = self._cre(good="voroos_hide", resource="organic")
        out = CS.resolve_spoils(c, 0)
        self.assertEqual(out["good"], "voroos_hide")
        self.assertEqual(out["resource_type"], "organic")

    def test_success_and_failure_lines(self):
        spoils = {"good": "wrix_pelt", "resource_type": "organic",
                  "quantity": 2, "quality": 55}
        succ = CS.spoils_success_line("Mara", "Wrix", spoils)
        self.assertIn("wrix_pelt", succ)
        self.assertIn("2x", succ)
        self.assertIn("organic", succ)
        fail = CS.spoils_failure_line("Mara", "Wrix")
        self.assertIn("botches", fail.lower())


# ─── Death-hook integration tests ────────────────────────────────────────────

class _FakeDB:
    """Minimal async DB faking get_npc / delete_npc / save_character."""

    def __init__(self):
        self.npcs = {}
        self._next = 1
        self.deleted = []
        self.saved = []   # list of (char_id, kwargs)

    def seed_npc(self, *, name, ai_config: dict, room_id=10):
        nid = self._next
        self._next += 1
        self.npcs[nid] = {
            "id": nid, "name": name, "room_id": room_id,
            "char_sheet_json": "{}",
            "ai_config_json": json.dumps(ai_config),
        }
        return nid

    async def get_npc(self, nid):
        return dict(self.npcs[nid]) if nid in self.npcs else None

    async def delete_npc(self, nid):
        self.deleted.append(nid)
        self.npcs.pop(nid, None)
        return True

    async def save_character(self, cid, **kwargs):
        self.saved.append((cid, kwargs))
        return True


class _Sess:
    def __init__(self, cid):
        self.character = {"id": cid}
        self.sent = []

    async def send_line(self, msg):
        self.sent.append(msg)


class _SM:
    def __init__(self, room_map=None):
        self._room = room_map or {}

    def sessions_in_room(self, room_id):
        return list(self._room.get(room_id, []))


def _wild_ai(creature_id):
    """The marker shape that build_creature_ai_config stamps at spawn."""
    return {"is_wilderness_encounter": True, "creature_id": creature_id}


def _killer():
    # add_resource only needs id + inventory; perform_skill_check is patched.
    return {"id": 99, "name": "Mara", "inventory": "{}",
            "attributes": {}, "skills": {}}


def _force_check(success: bool, margin: int = 0):
    """Build a patch target for perform_skill_check returning a fixed result,
    while recording the difficulty it was called with."""
    calls = {}

    def _fake(char, skill, difficulty, *a, **kw):
        calls["skill"] = skill
        calls["difficulty"] = difficulty
        return SimpleNamespace(success=success, margin=margin,
                               roll=difficulty + margin,
                               critical_success=False, fumble=False)
    return _fake, calls


class TestWildCreatureKilledHook(unittest.TestCase):

    def test_non_wilderness_npc_is_untouched(self):
        """A plain NPC (no is_wilderness_encounter) → False, NOT deleted."""
        db = _FakeDB()
        nid = db.seed_npc(name="Cantina Patron",
                          ai_config={"faction": "independent"})
        out = _run(WR.on_wild_creature_killed(db, nid, _killer(), 10))
        self.assertFalse(out)
        self.assertNotIn(nid, db.deleted)          # corpse left for its owner
        self.assertEqual(db.saved, [])

    def test_get_npc_none_returns_false(self):
        db = _FakeDB()
        out = _run(WR.on_wild_creature_killed(db, 12345, _killer(), 10))
        self.assertFalse(out)

    def test_wilderness_without_harvest_despawns_no_grant(self):
        """A real wilderness creature with NO harvest block (shredder_bat):
        carcass despawned (this hook owns cleanup), but no spoils granted."""
        db = _FakeDB()
        nid = db.seed_npc(name="Shredder Bat",
                          ai_config=_wild_ai("shredder_bat"))
        fake, _ = _force_check(success=True, margin=10)
        with patch("engine.skill_checks.perform_skill_check", fake):
            out = _run(WR.on_wild_creature_killed(db, nid, _killer(), 10))
        self.assertTrue(out)
        self.assertIn(nid, db.deleted)             # despawned
        self.assertEqual(db.saved, [])             # nothing granted

    def test_wilderness_harvest_success_grants_resource(self):
        """voroos (real yaml: organic, yield 2) + Survival success → an organic
        stack lands in the killer's inventory; save_character + delete called."""
        db = _FakeDB()
        nid = db.seed_npc(name="Voroos", ai_config=_wild_ai("voroos"))
        killer = _killer()
        sm = _SM({10: [_Sess(99)]})
        fake, calls = _force_check(success=True, margin=6)
        with patch("engine.skill_checks.perform_skill_check", fake):
            out = _run(WR.on_wild_creature_killed(
                db, nid, killer, 10, session_mgr=sm))
        self.assertTrue(out)
        self.assertIn(nid, db.deleted)
        # the field-dressing DC came from the creature's harvest block (default 8)
        self.assertEqual(calls["skill"], "survival")
        self.assertEqual(calls["difficulty"], 8)
        # resource landed in inventory.resources as an organic stack
        inv = json.loads(killer["inventory"])
        res = inv.get("resources", [])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["type"], "organic")
        # yield 2 (base) + 1 (margin 6 // 6) = 3
        self.assertEqual(res[0]["quantity"], 3)
        # persisted via save_character(inventory=...)
        self.assertEqual(len(db.saved), 1)
        self.assertEqual(db.saved[0][0], 99)
        self.assertIn("inventory", db.saved[0][1])
        # a success line was announced to the room
        self.assertTrue(any("voroos_hide" in m for m in sm._room[10][0].sent))

    def test_wilderness_harvest_failure_no_grant_still_despawns(self):
        """A botched field-dressing grants nothing but still despawns the
        carcass and announces the failure."""
        db = _FakeDB()
        nid = db.seed_npc(name="Wrix", ai_config=_wild_ai("wrix"))
        killer = _killer()
        sm = _SM({10: [_Sess(99)]})
        fake, _ = _force_check(success=False, margin=-3)
        with patch("engine.skill_checks.perform_skill_check", fake):
            out = _run(WR.on_wild_creature_killed(
                db, nid, killer, 10, session_mgr=sm))
        self.assertTrue(out)
        self.assertIn(nid, db.deleted)             # still despawned
        self.assertEqual(db.saved, [])             # nothing granted
        self.assertEqual(json.loads(killer["inventory"]).get("resources", []), [])
        self.assertTrue(any("botches" in m.lower()
                            for m in sm._room[10][0].sent))

    def test_chemical_source_reads_higher_dc(self):
        """spor_crawler (real yaml: chemical venom, difficulty 10) proves both
        the chemical-resource path and the data-driven (raised) DC."""
        db = _FakeDB()
        nid = db.seed_npc(name="Spor Crawler",
                          ai_config=_wild_ai("spor_crawler"))
        killer = _killer()
        fake, calls = _force_check(success=True, margin=0)
        with patch("engine.skill_checks.perform_skill_check", fake):
            out = _run(WR.on_wild_creature_killed(db, nid, killer, 10))
        self.assertTrue(out)
        self.assertEqual(calls["difficulty"], 10)  # raised DC from harvest block
        res = json.loads(killer["inventory"]).get("resources", [])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0]["type"], "chemical")

    def test_killer_none_despawns_silently(self):
        """A killer-less death (e.g. environmental) despawns the carcass with
        no roll, no grant, no announce — but is still handled (True)."""
        db = _FakeDB()
        nid = db.seed_npc(name="Stalker Lizard",
                          ai_config=_wild_ai("stalker_lizard"))
        sm = _SM({10: [_Sess(99)]})
        out = _run(WR.on_wild_creature_killed(db, nid, None, 10, session_mgr=sm))
        self.assertTrue(out)
        self.assertIn(nid, db.deleted)
        self.assertEqual(db.saved, [])
        self.assertEqual(sm._room[10][0].sent, [])

    def test_unknown_creature_id_still_despawns(self):
        """A wilderness spawn whose creature_id can't be resolved in the
        library still gets its carcass cleaned up (no grant)."""
        db = _FakeDB()
        nid = db.seed_npc(name="Mystery", ai_config=_wild_ai("does_not_exist"))
        out = _run(WR.on_wild_creature_killed(db, nid, _killer(), 10))
        self.assertTrue(out)
        self.assertIn(nid, db.deleted)
        self.assertEqual(db.saved, [])


if __name__ == "__main__":
    unittest.main()
