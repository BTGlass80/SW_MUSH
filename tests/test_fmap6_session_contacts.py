# -*- coding: utf-8 -*-
"""
tests/test_fmap6_session_contacts.py — F.MAP.6 contacts assembly.

Verifies that ``Session._hud_area_map`` (extended in F.MAP.6) emits a
``contacts`` list when the player is in an AreaGeometry-covered area:

  1. Empty area → ``hud["contacts"] == []`` (still emitted, just empty).
  2. NPCs in covered rooms appear with the right ``kind`` derived from
     ``_classify_npc_role``: hostile→npc_hostile, guard/quest→npc_friend,
     others→npc_neutral.
  3. NPCs in non-covered rooms (slug not in registry) are excluded.
  4. Hired NPCs are excluded (they're conceptually with the hiring PC,
     not a separate marker).
  5. PCs in covered rooms appear as kind="pc"; self is excluded.
  6. PCs in non-covered rooms are excluded.
  7. No registry → no ``contacts`` field at all (legacy-only path).
  8. Player in uncovered room → no ``contacts`` field.
  9. ``contacts`` field's coordinates match the AreaGeometry render
     coords for each NPC/PC's room.

Tests use a FakeDB (no real SQLite) and bypass the protocol layer.
"""
from __future__ import annotations

import asyncio
import json
import sys
import unittest
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.area_loader import AreaGeometryRegistry  # noqa: E402
from server.session import Protocol, Session, SessionState  # noqa: E402


# ── Fakes ──────────────────────────────────────────────────────────────────


class FakeInnerDB:
    """The ``_db`` attribute on Database — F.MAP.6's batch SQL goes
    through ``db._db.execute_fetchall``. Mirrors the production async
    aiosqlite shape just enough for the new code path."""

    def __init__(self, npcs: list):
        # npcs: list[dict] — pre-loaded with whatever fields we need
        self._npcs = npcs
        self.last_query = None
        self.last_params = None

    async def execute_fetchall(self, query, params=()):
        self.last_query = query
        self.last_params = params
        # We only handle the F.MAP.6 query: SELECT * FROM npcs WHERE room_id IN (...)
        if "FROM npcs WHERE room_id IN" in query:
            allowed = set(params)
            return [dict(n) for n in self._npcs
                    if n.get("room_id") in allowed]
        return []


class FakeDB:
    """Minimal db stub for F.MAP.6 contact assembly tests."""

    def __init__(self, room_id_to_slug: dict, npcs: list):
        # room_id → slug (also used for get_room_by_slug reverse)
        self._room_id_to_slug = dict(room_id_to_slug)
        self._slug_to_room_id = {v: k for k, v in room_id_to_slug.items()}
        self._db = FakeInnerDB(npcs)

    async def get_room(self, room_id):
        slug = self._room_id_to_slug.get(room_id)
        if slug is None:
            return None
        return {
            "id": room_id, "name": f"Test {room_id}", "zone_id": 1,
            "desc_short": "", "desc_long": "",
            "properties": json.dumps({"slug": slug}),
        }

    async def get_room_by_slug(self, slug):
        rid = self._slug_to_room_id.get(slug)
        if rid is None:
            return None
        return {"id": rid, "name": f"Slug {slug}", "properties": "{}"}

    async def get_exits(self, room_id):
        return []

    async def get_npcs_in_room(self, room_id):
        # Per-room call — used by legacy build_area_map. Return empty so
        # the legacy payload remains a stub — F.MAP.6 doesn't go through
        # this path.
        return []

    async def get_zone(self, zone_id):
        return None


def _make_session(self_id: int = 1, room_id: int = 1):
    s = Session.__new__(Session)
    s.protocol = Protocol.WEBSOCKET
    s.character = {"id": self_id, "name": "TestSelf", "room_id": room_id}
    s.id = 9001
    s._last_sent_area_key = None
    return s


def _make_session_mgr(registry, other_sessions: list = None):
    """Build a session_mgr with given registry + a list of fake other
    sessions to surface as PC contacts."""
    sm = MagicMock()
    sm._area_registry = registry
    sm._sessions = {s.id: s for s in (other_sessions or [])}
    return sm


def _make_other_session(char_id: int, name: str, room_id: int):
    s = Session.__new__(Session)
    s.protocol = Protocol.WEBSOCKET
    s.character = {"id": char_id, "name": name, "room_id": room_id}
    s.id = 1000 + char_id
    s.state = SessionState.IN_GAME
    return s


def _run(coro):
    return asyncio.run(coro)


def _build_registry():
    """Build a registry against the production CW maps and seed it
    with a slug→room_id map for the FakeDB."""
    reg = AreaGeometryRegistry.load_era("clone_wars")
    geom = reg._areas["tatooine.mos_eisley"]
    # Production room ids match the AreaGeometry render ids 1:1 (the
    # accidental alignment we leverage). Use slug → render_id+1000 to
    # make the FakeDB ids visually distinct in test output.
    slug_to_rid = {r.slug: r.id + 1000 for r in geom.rooms if r.slug}
    return reg, slug_to_rid


# ── Section 1 — No registry: contacts not emitted ─────────────────────────


class TestNoRegistryNoContacts(unittest.TestCase):
    def test_no_registry_means_no_contacts_field(self):
        sess = _make_session(room_id=1001)
        # FakeDB without registry — Bay 94 slug
        db = FakeDB({1001: "docking_bay_94_pit"}, [])
        sm = _make_session_mgr(registry=None)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        self.assertNotIn("contacts", hud)


# ── Section 2 — Empty area still emits contacts ───────────────────────────


class TestEmptyAreaEmitsEmptyList(unittest.TestCase):
    """Even with no PCs and no NPCs in any covered room, the contacts
    field must be present (empty array). The renderer reads
    geom.contacts on every render — undefined would mean 'don't update'
    while empty array means 'no contacts'."""

    def test_empty_area_emits_empty_contacts(self):
        sess = _make_session(self_id=1, room_id=1001)
        reg, slug_to_rid = _build_registry()
        db = FakeDB({v: k for k, v in slug_to_rid.items()}, [])
        sm = _make_session_mgr(registry=reg, other_sessions=[])
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        self.assertIn("contacts", hud)
        self.assertEqual(hud["contacts"], [])


# ── Section 3 — NPCs role-classified to the right kind ────────────────────


class TestNpcRoleClassification(unittest.TestCase):
    """The renderer expects kinds: pc | npc_friend | npc_hostile |
    npc_neutral. Verify the role mapping is what F.MAP.6 advertises."""

    def setUp(self):
        self.reg, self.slug_to_rid = _build_registry()
        self.room_id_to_slug = {v: k for k, v in self.slug_to_rid.items()}
        # Seed NPCs across various rooms with various dispositions
        # Bay 94 = render id 1, slug docking_bay_94_pit, prod id 1001
        # Cantina Bar = render id 13, slug chalmuans_cantina_main_bar, prod id 1013
        # Tusken camp = render id 50, slug jundland_tusken_overlook, prod id 1050
        self.npcs = [
            {"id": 1, "name": "Bartender Wuher", "room_id": 1013,
             "ai_config_json": json.dumps({}),
             "char_sheet_json": "{}", "hired_by": None,
             "species": "Human", "description": ""},
            {"id": 2, "name": "Stormtrooper Patrol", "room_id": 1001,
             "ai_config_json": json.dumps({"combat_behavior": "aggressive"}),
             "char_sheet_json": "{}", "hired_by": None,
             "species": "Human", "description": ""},
            {"id": 3, "name": "Tusken Raider", "room_id": 1050,
             "ai_config_json": json.dumps({"hostile": True}),
             "char_sheet_json": "{}", "hired_by": None,
             "species": "Tusken", "description": ""},
            {"id": 4, "name": "Jawa Trader", "room_id": 1001,
             "ai_config_json": json.dumps({}),
             "char_sheet_json": "{}", "hired_by": None,
             "species": "Jawa", "description": ""},
        ]
        self.sess = _make_session(self_id=1, room_id=1001)
        self.db = FakeDB(self.room_id_to_slug, self.npcs)
        self.sm = _make_session_mgr(self.reg)

    def test_hostile_classified_as_npc_hostile(self):
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=self.sm))
        self.assertIn("contacts", hud)
        names_by_kind = {c["name"]: c["kind"] for c in hud["contacts"]}
        self.assertEqual(names_by_kind.get("Tusken Raider"), "npc_hostile")

    def test_guard_classified_as_npc_friend(self):
        # _classify_npc_role identifies "patrol" name + aggressive combat as guard
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=self.sm))
        names_by_kind = {c["name"]: c["kind"] for c in hud["contacts"]}
        self.assertEqual(names_by_kind.get("Stormtrooper Patrol"), "npc_friend")

    def test_bartender_classified_as_npc_neutral(self):
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=self.sm))
        names_by_kind = {c["name"]: c["kind"] for c in hud["contacts"]}
        # Wuher matches the bartender keyword; that role is neutral
        self.assertEqual(names_by_kind.get("Bartender Wuher"), "npc_neutral")

    def test_unclassified_npc_falls_back_to_neutral(self):
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=self.sm))
        names_by_kind = {c["name"]: c["kind"] for c in hud["contacts"]}
        self.assertEqual(names_by_kind.get("Jawa Trader"), "npc_neutral")


# ── Section 4 — NPCs in non-covered rooms excluded ────────────────────────


class TestNpcsExcludedWhenRoomNotCovered(unittest.TestCase):
    def test_npc_in_uncovered_room_omitted(self):
        reg, slug_to_rid = _build_registry()
        room_id_to_slug = {v: k for k, v in slug_to_rid.items()}
        # Add an NPC in production room 9999 — NOT in the slug map.
        # The F.MAP.6 SQL filters by room_id IN (...) — only resolves
        # to rooms WITHIN the area, so 9999 is naturally outside the
        # IN-clause. But for thoroughness verify even if it leaked in
        # somehow, the kind would never resolve.
        npcs = [
            {"id": 1, "name": "Off-map NPC", "room_id": 9999,
             "ai_config_json": "{}", "char_sheet_json": "{}",
             "hired_by": None, "species": "Human", "description": ""},
        ]
        sess = _make_session(self_id=1, room_id=1001)
        db = FakeDB(room_id_to_slug, npcs)
        sm = _make_session_mgr(reg)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        self.assertEqual(hud["contacts"], [])


# ── Section 5 — Hired NPCs excluded ────────────────────────────────────────


class TestHiredNpcsExcluded(unittest.TestCase):
    """Hired NPCs follow their hiring PC and conceptually share the
    PC's marker. Listing them as separate contacts would clutter the
    map with the player's own retinue."""

    def test_hired_npc_omitted(self):
        reg, slug_to_rid = _build_registry()
        room_id_to_slug = {v: k for k, v in slug_to_rid.items()}
        npcs = [
            {"id": 1, "name": "Hired Mercenary", "room_id": 1001,
             "ai_config_json": "{}", "char_sheet_json": "{}",
             "hired_by": 42,  # hired
             "species": "Human", "description": ""},
            {"id": 2, "name": "Free NPC", "room_id": 1001,
             "ai_config_json": "{}", "char_sheet_json": "{}",
             "hired_by": None,
             "species": "Human", "description": ""},
        ]
        sess = _make_session(self_id=1, room_id=1001)
        db = FakeDB(room_id_to_slug, npcs)
        sm = _make_session_mgr(reg)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        names = [c["name"] for c in hud["contacts"]]
        self.assertIn("Free NPC", names)
        self.assertNotIn("Hired Mercenary", names)


# ── Section 6 — PCs in covered rooms ──────────────────────────────────────


class TestPcContactRoster(unittest.TestCase):
    def setUp(self):
        self.reg, self.slug_to_rid = _build_registry()
        self.room_id_to_slug = {v: k for k, v in self.slug_to_rid.items()}
        self.sess = _make_session(self_id=1, room_id=1001)
        self.db = FakeDB(self.room_id_to_slug, [])

    def test_other_pc_in_covered_room_appears(self):
        other = _make_other_session(2, "PartnerPC", 1013)  # cantina
        sm = _make_session_mgr(self.reg, other_sessions=[other])
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=sm))
        kinds_by_name = {c["name"]: c["kind"] for c in hud["contacts"]}
        self.assertEqual(kinds_by_name.get("PartnerPC"), "pc")

    def test_self_excluded_from_contacts(self):
        # Even if self appears in session_mgr._sessions, must be excluded
        myself = _make_other_session(1, "TestSelf", 1001)
        sm = _make_session_mgr(self.reg, other_sessions=[myself])
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=sm))
        names = [c["name"] for c in hud["contacts"]]
        self.assertNotIn("TestSelf", names)

    def test_pc_in_uncovered_room_excluded(self):
        other = _make_other_session(2, "OffMapPC", 99999)
        sm = _make_session_mgr(self.reg, other_sessions=[other])
        hud = {}
        _run(self.sess._hud_area_map(hud, self.db, 1001, session_mgr=sm))
        names = [c["name"] for c in hud["contacts"]]
        self.assertNotIn("OffMapPC", names)


# ── Section 7 — Coordinates match the AreaGeometry's render coords ────────


class TestContactCoordinatesMatchRenderCoords(unittest.TestCase):
    """A contact in the cantina must have the cantina's render coords
    (x≈2.9, y≈3.7 from the relaid YAML) regardless of what production
    room id the cantina has."""

    def test_npc_uses_cantina_render_coords(self):
        reg, slug_to_rid = _build_registry()
        room_id_to_slug = {v: k for k, v in slug_to_rid.items()}
        cantina_rid = slug_to_rid["chalmuans_cantina_main_bar"]
        npcs = [
            {"id": 1, "name": "Wuher", "room_id": cantina_rid,
             "ai_config_json": "{}", "char_sheet_json": "{}",
             "hired_by": None, "species": "Human", "description": ""},
        ]
        sess = _make_session(self_id=1, room_id=1001)
        db = FakeDB(room_id_to_slug, npcs)
        sm = _make_session_mgr(reg)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        c = hud["contacts"][0]
        self.assertAlmostEqual(c["x"], 2.9, places=4)
        self.assertAlmostEqual(c["y"], 3.7, places=4)


# ── Section 8 — Player in uncovered room → no contacts field ─────────────


class TestPlayerInUncoveredRoomNoContacts(unittest.TestCase):
    def test_uncovered_room_no_contacts_field(self):
        reg, slug_to_rid = _build_registry()
        # The player is in a slug that DOES exist in production but
        # ISN'T in the AreaGeometry — registry.lookup returns None,
        # so the contacts assembly never runs.
        room_id_to_slug = {v: k for k, v in slug_to_rid.items()}
        room_id_to_slug[99999] = "docking_bay_92"  # production but not in AreaGeometry
        sess = _make_session(self_id=1, room_id=99999)
        db = FakeDB(room_id_to_slug, [])
        sm = _make_session_mgr(reg)
        hud = {}
        _run(sess._hud_area_map(hud, db, 99999, session_mgr=sm))
        # Legacy area_map should be there
        self.assertIn("area_map", hud)
        # But none of the F.MAP.2/F.MAP.6 fields
        self.assertNotIn("area_geometry", hud)
        self.assertNotIn("player_position", hud)
        self.assertNotIn("contacts", hud)


# ── Section 9 — Failure tolerance: contacts assembly never breaks HUD ─────


class TestContactsAssemblyFailureTolerance(unittest.TestCase):
    """Per architecture: failure in the F.MAP.6 contacts assembly
    must NOT break the F.MAP.2 area_geometry/player_position augmentation.
    Each layer is independently try/except guarded."""

    def test_broken_inner_db_doesnt_break_player_position(self):
        reg, slug_to_rid = _build_registry()
        room_id_to_slug = {v: k for k, v in slug_to_rid.items()}
        # Replace _db with one that always raises
        class BrokenInnerDB:
            async def execute_fetchall(self, *a, **kw):
                raise RuntimeError("simulated DB outage")
        sess = _make_session(self_id=1, room_id=1001)
        db = FakeDB(room_id_to_slug, [])
        db._db = BrokenInnerDB()
        sm = _make_session_mgr(reg)
        hud = {}
        _run(sess._hud_area_map(hud, db, 1001, session_mgr=sm))
        # F.MAP.2 layer still works
        self.assertIn("player_position", hud)
        self.assertIn("area_geometry", hud)
        # F.MAP.6 layer: contacts present (the SQL failed but the PC
        # roster sweep didn't depend on it). Empty list is acceptable.
        self.assertIn("contacts", hud)


if __name__ == "__main__":
    unittest.main()
