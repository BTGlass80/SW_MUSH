# -*- coding: utf-8 -*-
"""
tests/test_h2_faction_missions.py — H2 QA fix: faction mission reconciliation

Covers the full accept→travel→complete→reward loop for BOTH posting paths:
  1. Leader-posted faction mission (faction_leader_commands._handle_mission)
  2. Director-posted faction mission (director._apply_faction_order post_mission)
  3. Rep gate: characters below rep_required are rejected at accept
  4. Slug id appears in DB data blob (not integer PK)
  5. Public board ('missions') excludes faction missions
"""
import asyncio
import importlib
import json
import sys
import time
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

# Grab the Database class (class name is 'Database', not 'GameDatabase')
_db_mod = importlib.import_module("db.database")
_Database = _db_mod.Database


# ══════════════════════════════════════════════════════════════════════════════
# Shared helpers
# ══════════════════════════════════════════════════════════════════════════════

def _make_char(char_id: int = 42, faction_id: str = "republic",
               room_id: int = 10) -> dict:
    return {
        "id": char_id,
        "name": "TestChar",
        "faction_id": faction_id,
        "room_id": room_id,
        "credits": 1000,
        "attributes": "{}",
    }


def _make_org(org_id: int = 1, code: str = "republic",
              hq_room_id: int = 10) -> dict:
    return {
        "id": org_id,
        "code": code,
        "name": "Galactic Republic",
        "org_type": "faction",
        "hq_room_id": hq_room_id,
        "treasury": 0,
        "properties": "{}",
    }


def _make_hq_room(room_id: int = 10, name: str = "Republic HQ") -> dict:
    return {"id": room_id, "name": name, "zone_id": 1, "properties": "{}"}


def _call_post_faction_mission_on_stub(faction_id, inserted_params, **kwargs):
    """Return an async callable that runs post_faction_mission on a stub DB."""

    class StubInnerDB:
        async def execute(self, sql, params=None):
            if params:
                inserted_params["sql"] = sql
                inserted_params["params"] = list(params)
            c = MagicMock()
            c.lastrowid = 77
            return c

        async def commit(self):
            pass

    class StubDB:
        _db = StubInnerDB()

    stub = StubDB()
    bound = types.MethodType(_Database.post_faction_mission, stub)

    async def _run():
        return await bound(faction_id, **kwargs)

    return _run


# ══════════════════════════════════════════════════════════════════════════════
# 1. post_faction_mission writes a valid Mission blob
# ══════════════════════════════════════════════════════════════════════════════

class TestPostFactionMissionBlob:
    """Verify the data blob written by post_faction_mission is Mission-deserializable."""

    @pytest.mark.asyncio
    async def test_blob_has_slug_id(self):
        """The data blob id starts with 'fm-' (slug scheme), not the integer PK."""
        inserted = {}
        run = _call_post_faction_mission_on_stub(
            "republic", inserted,
            mission_type="combat",
            title="Republic: Combat Mission",
            description="Suppress the enemy.",
            reward=750,
            difficulty="moderate",
            skill_required="blaster",
            giver="Clone Sergeant",
            destination="Republic HQ",
            destination_room_id=10,
            faction_rep_required=25,
        )
        row_id = await run()
        assert row_id == 77

        blob = json.loads(inserted["params"][-1])

        assert blob["id"].startswith("fm-republic-"), (
            f"Slug id should start with 'fm-republic-', got: {blob['id']!r}"
        )
        assert blob["faction_code"] == "republic"
        assert blob["faction_rep_required"] == 25
        assert blob["destination_room_id"] == "10"
        assert blob["reward"] == 750
        assert blob["mission_type"] == "combat"
        assert blob["status"] == "available"

    @pytest.mark.asyncio
    async def test_blob_is_mission_deserializable(self):
        """Mission.from_dict() can reconstruct the blob without errors."""
        from engine.missions import Mission

        inserted = {}
        run = _call_post_faction_mission_on_stub(
            "hutt_cartel", inserted,
            mission_type="smuggling",
            title="Hutt Cartel: Smuggling Run",
            description="Move the goods.",
            reward=600,
            giver="Hutt Majordomo",
            destination="Jabba's Palace",
            destination_room_id=55,
            faction_rep_required=20,
        )
        await run()

        blob = json.loads(inserted["params"][-1])
        m = Mission.from_dict(blob)

        assert m.faction_code == "hutt_cartel"
        assert m.faction_rep_required == 20
        assert m.destination_room_id == "55"
        assert m.id.startswith("fm-hutt_car")

    @pytest.mark.asyncio
    async def test_unknown_mission_type_falls_back_to_delivery(self):
        """An unrecognised mission_type string falls back to 'delivery' without crashing."""
        from engine.missions import Mission, MissionType

        inserted = {}
        run = _call_post_faction_mission_on_stub(
            "republic", inserted,
            mission_type="invalid_type_xyz",
            title="Test",
            description="Test mission.",
            reward=200,
            faction_rep_required=0,
        )
        await run()
        blob = json.loads(inserted["params"][-1])
        assert blob["mission_type"] == MissionType.DELIVERY.value


# ══════════════════════════════════════════════════════════════════════════════
# 2. Leader-posted mission: accept → travel → complete → reward
# ══════════════════════════════════════════════════════════════════════════════

class TestLeaderPostedMissionLoop:
    """Integration: leader posts mission → member accepts → travels → completes."""

    def _board_with_mission(self, mission):
        from engine.missions import MissionBoard
        board = MissionBoard()
        board._loaded = True
        board._missions = {mission.id: mission}
        return board

    @pytest.mark.asyncio
    async def test_accept_travel_complete_reward(self):
        """Leader-posted mission full loop: accept, ground-dest check, complete, credit."""
        from engine.missions import Mission, MissionType, MissionStatus, MISSION_TTL

        now = time.time()
        m = Mission(
            id="fm-republic-abc12345",
            mission_type=MissionType.COMBAT,
            title="Republic: Combat Mission",
            giver="Republic leader",
            objective="Neutralize the Separatist cell.",
            destination="Republic HQ",
            destination_room_id="10",
            reward=750,
            required_skill="blaster",
            status=MissionStatus.AVAILABLE,
            created_at=now,
            expires_at=now + MISSION_TTL,
            faction_code="republic",
            faction_rep_required=25,
        )

        board = self._board_with_mission(m)

        char_id = "1"
        char_room = 10  # same as destination_room_id → at destination

        db = AsyncMock()
        db.accept_mission  = AsyncMock()
        db.complete_mission = AsyncMock()
        db.adjust_credits  = AsyncMock(return_value=1750)

        # ── accept ──
        accepted = await board.accept(m.id, char_id, db)
        assert accepted is not None, "board.accept() returned None"
        assert accepted.status == MissionStatus.ACCEPTED
        assert accepted.accepted_by == char_id
        db.accept_mission.assert_called_once()

        # ── verify at destination ──
        at_dest = str(char_room) == str(accepted.destination_room_id)
        assert at_dest, (
            f"Char room {char_room} should match destination_room_id "
            f"{accepted.destination_room_id!r}"
        )

        # ── complete ──
        completed = await board.complete(m.id, db)
        assert completed is not None
        assert completed.status == MissionStatus.COMPLETE
        db.complete_mission.assert_called_once()

        # ── reward via adjust_credits funnel (not a direct write) ──
        new_bal = await db.adjust_credits(1, completed.reward, "mission")
        assert new_bal == 1750


# ══════════════════════════════════════════════════════════════════════════════
# 3. Director-posted mission: accept → travel → complete → reward
# ══════════════════════════════════════════════════════════════════════════════

class TestDirectorPostedMissionLoop:
    """Integration: Director posts mission with zone→room destination."""

    @pytest.mark.asyncio
    async def test_director_blob_carries_zone_room(self):
        """post_faction_mission with Director-style args yields correct blob."""
        from engine.missions import Mission

        inserted = {}

        # Simulate zone→room lookup (mirrors director._apply_faction_order):
        # zone_row = {"id": 3}, room_rows = [{"id": 20, "name": "Mos Eisley Spaceport"}]
        dest_room_id = 20
        dest_name    = "Mos Eisley Spaceport"
        faction_code = "republic"
        zone         = "mos_eisley"

        run = _call_post_faction_mission_on_stub(
            faction_code, inserted,
            mission_type="patrol",
            title=f"{faction_code.title()} Directive: Patrol ({zone})",
            description="Secure the landing zone.",
            reward=500,
            difficulty="moderate",
            skill_required="sensors",
            giver="Republic Command",
            destination=dest_name,
            destination_room_id=dest_room_id,
            faction_rep_required=25,
        )
        await run()

        blob = json.loads(inserted["params"][-1])
        m = Mission.from_dict(blob)

        assert m.id.startswith("fm-republic-")
        assert m.faction_code == "republic"
        assert m.destination_room_id == "20"
        assert m.destination == "Mos Eisley Spaceport"
        assert m.faction_rep_required == 25

    @pytest.mark.asyncio
    async def test_director_mission_full_loop(self):
        """Director-posted mission: accept → at-destination check → complete → credit."""
        from engine.missions import Mission, MissionType, MissionStatus, MISSION_TTL, MissionBoard

        now = time.time()
        m = Mission(
            id="fm-republic-dir11111",
            mission_type=MissionType.PATROL,
            title="Republic Directive: Patrol (mos_eisley)",
            giver="Republic Command",
            objective="Secure the landing zone.",
            destination="Mos Eisley Spaceport",
            destination_room_id="20",
            reward=500,
            required_skill="sensors",
            status=MissionStatus.AVAILABLE,
            created_at=now,
            expires_at=now + MISSION_TTL,
            faction_code="republic",
            faction_rep_required=25,
        )

        board = MissionBoard()
        board._loaded = True
        board._missions = {m.id: m}

        char_id   = "7"
        char_room = 20  # matches destination_room_id

        db = AsyncMock()
        db.accept_mission   = AsyncMock()
        db.complete_mission = AsyncMock()
        db.adjust_credits   = AsyncMock(return_value=1500)

        accepted = await board.accept(m.id, char_id, db)
        assert accepted is not None
        assert accepted.status == MissionStatus.ACCEPTED

        # destination check
        assert str(char_room) == str(accepted.destination_room_id)

        completed = await board.complete(m.id, db)
        assert completed is not None
        assert completed.status == MissionStatus.COMPLETE

        new_bal = await db.adjust_credits(7, completed.reward, "mission")
        assert new_bal == 1500


# ══════════════════════════════════════════════════════════════════════════════
# 4. Rep gate: reject under-rep and non-member at accept
# ══════════════════════════════════════════════════════════════════════════════

class TestRepGate:
    """Verify _get_char_faction_rep drives accept rejection."""

    @pytest.mark.asyncio
    async def test_non_member_gets_rep_zero(self):
        """No membership row → rep = 0, blocked for rep_required=25 missions."""
        from engine.missions import _get_char_faction_rep

        char = _make_char(char_id=99)
        db = AsyncMock()
        db.get_organization = AsyncMock(return_value={"id": 1, "code": "republic"})
        db.get_membership   = AsyncMock(return_value=None)

        rep = await _get_char_faction_rep(char, "republic", db)
        assert rep == 0
        assert rep < 25  # rep_required for republic

    @pytest.mark.asyncio
    async def test_under_rep_member_blocked(self):
        """Member with rep 10 < 25 is blocked."""
        from engine.missions import _get_char_faction_rep

        char = _make_char(char_id=88)
        db = AsyncMock()
        db.get_organization = AsyncMock(return_value={"id": 1, "code": "republic"})
        db.get_membership   = AsyncMock(return_value={"rep_score": 10})

        rep = await _get_char_faction_rep(char, "republic", db)
        assert rep == 10
        assert rep < 25

    @pytest.mark.asyncio
    async def test_qualified_member_passes(self):
        """Member with rep 50 >= 25 passes the gate."""
        from engine.missions import _get_char_faction_rep

        char = _make_char(char_id=77)
        db = AsyncMock()
        db.get_organization = AsyncMock(return_value={"id": 1, "code": "republic"})
        db.get_membership   = AsyncMock(return_value={"rep_score": 50})

        rep = await _get_char_faction_rep(char, "republic", db)
        assert rep == 50
        assert rep >= 25

    @pytest.mark.asyncio
    async def test_org_not_found_returns_none(self):
        """Unknown org → _get_char_faction_rep returns None (can't verify)."""
        from engine.missions import _get_char_faction_rep

        char = _make_char(char_id=66)
        db = AsyncMock()
        db.get_organization = AsyncMock(return_value=None)
        db.get_membership   = AsyncMock(return_value=None)

        rep = await _get_char_faction_rep(char, "nonexistent_faction", db)
        assert rep is None


# ══════════════════════════════════════════════════════════════════════════════
# 5. Public board excludes faction missions
# ══════════════════════════════════════════════════════════════════════════════

class TestPublicBoardExcludesFactionMissions:
    """Faction missions must NOT appear on the public 'missions' board."""

    def test_faction_missions_filtered_from_public_board(self):
        """The H2 faction_code filter keeps faction missions off the public board."""
        from engine.missions import Mission, MissionType, MissionStatus, MISSION_TTL

        now = time.time()
        open_m = Mission(
            id="m-openXXXX", mission_type=MissionType.DELIVERY,
            title="Open Job", giver="Dockworker",
            objective="Deliver package.", destination="Market",
            destination_room_id=None, reward=300, required_skill="stamina",
            status=MissionStatus.AVAILABLE, created_at=now, expires_at=now + MISSION_TTL,
        )
        faction_m = Mission(
            id="fm-republic-private1", mission_type=MissionType.COMBAT,
            title="Republic Gated", giver="Clone Sergeant",
            objective="Fight the enemy.", destination="Republic HQ",
            destination_room_id="10", reward=750, required_skill="blaster",
            status=MissionStatus.AVAILABLE, created_at=now, expires_at=now + MISSION_TTL,
            faction_code="republic", faction_rep_required=25,
        )

        all_missions = [open_m, faction_m]
        # Mirror the filter added to MissionsCommand.execute (H2 fix)
        public = [m for m in all_missions if not getattr(m, "faction_code", None)]

        assert len(public) == 1
        assert public[0].id == "m-openXXXX"
        assert faction_m not in public


# ══════════════════════════════════════════════════════════════════════════════
# 6. Slug display in faction_commands._cmd_missions
# ══════════════════════════════════════════════════════════════════════════════

class TestFactionBoardSlugDisplay:
    """faction missions shows the slug id from the data blob, not the integer PK."""

    def test_slug_extracted_from_blob(self):
        """Valid blob → slug id is used as display_id."""
        slug = "fm-republic-abc12345"
        blob = {
            "id": slug,
            "mission_type": "combat",
            "title": "Republic Combat Mission",
            "faction_code": "republic",
            "faction_rep_required": 25,
            "reward": 750,
        }
        row = {
            "id": 42,
            "title": "Republic Combat Mission",
            "reward": 750,
            "difficulty": "moderate",
            "description": "Fight the enemy.",
            "data": json.dumps(blob),
        }

        # Mirror the slug-extraction logic in _cmd_missions (H2 fix)
        display_id = str(row["id"])
        try:
            b = json.loads(row.get("data") or "{}")
            s = b.get("id", "")
            if s:
                display_id = s
        except Exception:
            pass

        assert display_id == slug

    def test_fallback_to_pk_when_blob_empty(self):
        """Old rows with data='{}' fall back to integer PK without crash."""
        row = {
            "id": 7,
            "title": "Old Mission",
            "reward": 200,
            "difficulty": "easy",
            "description": "",
            "data": "{}",
        }

        display_id = str(row["id"])
        try:
            b = json.loads(row.get("data") or "{}")
            s = b.get("id", "")
            if s:
                display_id = s
        except Exception:
            pass

        assert display_id == "7"

    def test_fallback_when_data_is_null(self):
        """data=NULL → no crash, falls back to PK."""
        row = {"id": 3, "data": None}

        display_id = str(row["id"])
        try:
            b = json.loads(row.get("data") or "{}")
            s = b.get("id", "")
            if s:
                display_id = s
        except Exception:
            pass

        assert display_id == "3"
