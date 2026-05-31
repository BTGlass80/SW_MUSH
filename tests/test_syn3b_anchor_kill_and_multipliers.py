# -*- coding: utf-8 -*-
"""
tests/test_syn3b_anchor_kill_and_multipliers.py — SYN.3.b (2026-05-25).

Pins the culminating-fight + influence-multiplier additions to
``engine/contest.py``, shipped in the combined SYN.3 drop (SYN.3.a +
SYN.3.b rolled up per Brian's call). Per
``contestable_wilderness_design_v2.md`` §2.4 + §3.3.

Companion to ``tests/test_syn3a_region_contest_state_machine.py``:
where SYN.3.a tested the schema + engine surfaces in isolation,
SYN.3.b tests the runtime behaviours that consume them — Anchor
NPC spawn, kill detection, ownership transfer, contest-influence
multipliers, and the cancel-by-admin path.

Test sections
─────────────
  1. TestAnchorHpTier             — _anchor_hp_tier bucket boundaries
  2. TestAnchorTemplates          — every faction key resolves to a template
  3. TestBuildAnchorSheet         — char_sheet shape + anchor_target_hp
  4. TestTwoPhaseTick             — Phase A spawn + Phase B defender-win
  5. TestSpawnRegionAnchor        — landmark pick, NPC create, reinforce count
  6. TestOnNpcKilledInCombat      — challenger kills Anchor → seizure
                                   defender kills Anchor → defender wins
                                   no-faction killer → defender wins
                                   non-Anchor NPC → no-op
  7. TestResolveChallengerWin     — ownership transfer + garrison swap
                                   defender penalty + cooldown
  8. TestContestInfluenceMultipliers — 2× for contestants, 1.5× outnumbered
                                       defender, pass-through for non-cont.
                                       negative deltas untouched
  9. TestAdjustTerritoryInfluenceHook — region_slug kwarg surfaces
 10. TestCancelRegionContest      — admin/exception path
 11. TestDrop6dPhysicallyDeleted   — sanity: removed surfaces gone
 12. TestCallerRetargets          — source-level check that callers point at SYN.3
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
import sys
import time
import unittest
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    """Run a coroutine in a fresh event loop (BugFix5 Py3.14 pattern)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ──────────────────────────────────────────────────────────────────────
# In-memory DB stand-in — extends SYN.3.a's _MiniDB with the surfaces
# SYN.3.b's spawn flow + ownership transfer need.
# ──────────────────────────────────────────────────────────────────────

class _SyncAsyncSqlite:
    def __init__(self):
        self._conn = sqlite3.connect(":memory:")
        self._conn.row_factory = sqlite3.Row

    async def execute(self, sql, params=()):
        self._conn.execute(sql, params)

    async def execute_fetchall(self, sql, params=()):
        cur = self._conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    async def commit(self):
        self._conn.commit()


class _MiniDB:
    """In-memory DB with the surfaces SYN.3.b exercise."""

    def __init__(self):
        self._db = _SyncAsyncSqlite()
        cur = self._db._conn
        cur.executescript("""
            CREATE TABLE rooms (
                id INTEGER PRIMARY KEY,
                name TEXT,
                zone_id INTEGER,
                wilderness_region_id TEXT
            );
            CREATE TABLE organizations (
                id INTEGER PRIMARY KEY,
                code TEXT UNIQUE NOT NULL,
                name TEXT,
                treasury INTEGER DEFAULT 0
            );
            CREATE TABLE memberships (
                char_id INTEGER NOT NULL,
                org_id INTEGER NOT NULL,
                rank_level INTEGER DEFAULT 1,
                PRIMARY KEY (char_id, org_id)
            );
            CREATE TABLE npcs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT,
                room_id INTEGER,
                species TEXT,
                description TEXT,
                char_sheet_json TEXT DEFAULT '{}',
                ai_config_json TEXT DEFAULT '{}'
            );
            CREATE TABLE zones (
                id INTEGER PRIMARY KEY,
                name TEXT,
                properties TEXT DEFAULT '{"security":"lawless"}'
            );
            CREATE TABLE territory_influence (
                zone_id INTEGER NOT NULL,
                org_code TEXT NOT NULL,
                score INTEGER NOT NULL DEFAULT 0,
                last_activity REAL NOT NULL DEFAULT 0,
                last_presence REAL NOT NULL DEFAULT 0,
                PRIMARY KEY (zone_id, org_code)
            );
            CREATE TABLE region_ownership (
                region_slug   TEXT    NOT NULL PRIMARY KEY,
                org_code      TEXT    NOT NULL,
                zone_id       INTEGER,
                claimed_by    INTEGER NOT NULL,
                claimed_at    REAL    NOT NULL,
                maintenance   INTEGER NOT NULL DEFAULT 3000
            );
            CREATE TABLE region_garrison (
                region_slug TEXT    NOT NULL,
                npc_id      INTEGER NOT NULL,
                PRIMARY KEY (region_slug, npc_id)
            );
        """)
        self._db._conn.commit()

    # raw SQL pass-through
    async def fetchall(self, sql, params=()):
        return await self._db.execute_fetchall(sql, params)

    async def execute(self, sql, params=()):
        return await self._db.execute(sql, params)

    async def commit(self):
        await self._db.commit()

    # ORM-style helpers used by territory + contest
    async def get_organization(self, org_code):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM organizations WHERE code = ?", (org_code,)
        )
        return dict(rows[0]) if rows else None

    async def get_membership(self, char_id, org_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM memberships WHERE char_id = ? AND org_id = ?",
            (char_id, org_id),
        )
        return dict(rows[0]) if rows else None

    async def adjust_org_treasury(self, org_id, delta):
        rows = await self._db.execute_fetchall(
            "SELECT treasury FROM organizations WHERE id = ?", (org_id,)
        )
        current = int(rows[0]["treasury"]) if rows else 0
        new_balance = current + int(delta)
        await self._db.execute(
            "UPDATE organizations SET treasury = ? WHERE id = ?",
            (new_balance, org_id),
        )
        await self._db.commit()
        return new_balance

    async def get_room(self, room_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM rooms WHERE id = ?", (room_id,)
        )
        return dict(rows[0]) if rows else None

    async def get_zone(self, zone_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM zones WHERE id = ?", (zone_id,)
        )
        return dict(rows[0]) if rows else None

    async def create_npc(self, name, room_id, species="Human",
                          description="", char_sheet_json="{}",
                          ai_config_json="{}"):
        cur = self._db._conn.execute(
            """INSERT INTO npcs (name, room_id, species, description,
                                 char_sheet_json, ai_config_json)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (name, room_id, species, description, char_sheet_json,
             ai_config_json),
        )
        self._db._conn.commit()
        return cur.lastrowid

    async def get_npc(self, npc_id):
        rows = await self._db.execute_fetchall(
            "SELECT * FROM npcs WHERE id = ?", (npc_id,)
        )
        return dict(rows[0]) if rows else None

    async def update_npc(self, npc_id, **kwargs):
        if not kwargs:
            return
        cols = ", ".join(f"{k} = ?" for k in kwargs)
        params = list(kwargs.values()) + [npc_id]
        await self._db.execute(
            f"UPDATE npcs SET {cols} WHERE id = ?",
            params,
        )
        await self._db.commit()

    # Seed helpers
    def seed_org(self, *, org_id, code, treasury=100_000, name=None):
        self._db._conn.execute(
            "INSERT INTO organizations (id, code, name, treasury) "
            "VALUES (?, ?, ?, ?)",
            (org_id, code, name or code.title(), treasury),
        )
        self._db._conn.commit()

    def seed_membership(self, *, char_id, org_id, rank_level=3):
        self._db._conn.execute(
            "INSERT INTO memberships (char_id, org_id, rank_level) "
            "VALUES (?, ?, ?)",
            (char_id, org_id, rank_level),
        )
        self._db._conn.commit()

    def seed_zone(self, *, zone_id, name, declared_security="lawless"):
        props = json.dumps({"security": declared_security})
        self._db._conn.execute(
            "INSERT INTO zones (id, name, properties) VALUES (?, ?, ?)",
            (zone_id, name, props),
        )
        self._db._conn.commit()

    def seed_region(self, *, slug, zone_id, owner_org_code=None,
                    landmark_count=3, start_room_id=100):
        for i in range(landmark_count):
            self._db._conn.execute(
                "INSERT INTO rooms (id, name, zone_id, wilderness_region_id)"
                " VALUES (?, ?, ?, ?)",
                (start_room_id + i, f"{slug} landmark #{i + 1}",
                 zone_id, slug),
            )
        if owner_org_code:
            self._db._conn.execute(
                """INSERT INTO region_ownership
                   (region_slug, org_code, zone_id, claimed_by, claimed_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (slug, owner_org_code, zone_id, 1, time.time()),
            )
        self._db._conn.commit()

    def seed_influence(self, *, zone_id, org_code, score):
        now = time.time()
        self._db._conn.execute(
            """INSERT INTO territory_influence
               (zone_id, org_code, score, last_activity, last_presence)
               VALUES (?, ?, ?, ?, ?)""",
            (zone_id, org_code, score, now, now),
        )
        self._db._conn.commit()


async def _setup_schema(mdb):
    from engine.contest import ensure_region_contest_schema
    await ensure_region_contest_schema(mdb)


# ──────────────────────────────────────────────────────────────────────
# 1. TestAnchorHpTier
# ──────────────────────────────────────────────────────────────────────

class TestAnchorHpTier(unittest.TestCase):
    """_anchor_hp_tier bucket boundaries."""

    def test_basic_tier(self):
        from engine.contest import _anchor_hp_tier
        self.assertEqual(_anchor_hp_tier(100), "basic")
        self.assertEqual(_anchor_hp_tier(124), "basic")

    def test_strong_tier(self):
        from engine.contest import _anchor_hp_tier
        self.assertEqual(_anchor_hp_tier(125), "strong")
        self.assertEqual(_anchor_hp_tier(149), "strong")

    def test_hardened_tier(self):
        from engine.contest import _anchor_hp_tier
        self.assertEqual(_anchor_hp_tier(150), "hardened")
        self.assertEqual(_anchor_hp_tier(174), "hardened")

    def test_fortress_tier(self):
        from engine.contest import _anchor_hp_tier
        self.assertEqual(_anchor_hp_tier(175), "fortress")
        self.assertEqual(_anchor_hp_tier(200), "fortress")


# ──────────────────────────────────────────────────────────────────────
# 2. TestAnchorTemplates
# ──────────────────────────────────────────────────────────────────────

class TestAnchorTemplates(unittest.TestCase):
    """Every faction key resolves to a template."""

    def test_all_factions_present(self):
        from engine.contest import _REGION_ANCHOR_TEMPLATES
        # GCW + CW factions enumerated in design + organizations.yaml
        for key in [
            "empire", "rebel", "hutt", "bh_guild",
            "republic", "cis", "jedi_order",
            "hutt_cartel", "bounty_hunters_guild",
            "_default",
        ]:
            self.assertIn(key, _REGION_ANCHOR_TEMPLATES,
                          f"missing anchor template for {key}")

    def test_template_shape(self):
        from engine.contest import _REGION_ANCHOR_TEMPLATES
        for key, tmpl in _REGION_ANCHOR_TEMPLATES.items():
            for field in ("name_prefix", "species", "description",
                          "weapon", "faction"):
                self.assertIn(field, tmpl,
                              f"{key} template missing {field}")


# ──────────────────────────────────────────────────────────────────────
# 3. TestBuildAnchorSheet
# ──────────────────────────────────────────────────────────────────────

class TestBuildAnchorSheet(unittest.TestCase):
    """char_sheet shape + anchor_target_hp + scales by HP tier."""

    def test_basic_sheet(self):
        from engine.contest import _build_anchor_sheet, _REGION_ANCHOR_TEMPLATES
        tmpl = _REGION_ANCHOR_TEMPLATES["hutt_cartel"]
        sheet = _build_anchor_sheet(tmpl, 100)
        self.assertEqual(sheet["anchor_target_hp"], 100)
        self.assertEqual(sheet["anchor_tier"], "basic")
        # Tier-2 NPC: STR scales with HP tier
        self.assertEqual(sheet["attributes"]["strength"], "4D")

    def test_fortress_sheet_has_higher_str(self):
        from engine.contest import _build_anchor_sheet, _REGION_ANCHOR_TEMPLATES
        tmpl = _REGION_ANCHOR_TEMPLATES["republic"]
        sheet = _build_anchor_sheet(tmpl, 200)
        self.assertEqual(sheet["anchor_tier"], "fortress")
        self.assertEqual(sheet["attributes"]["strength"], "7D")

    def test_sheet_has_dodge_and_blaster(self):
        from engine.contest import _build_anchor_sheet, _REGION_ANCHOR_TEMPLATES
        tmpl = _REGION_ANCHOR_TEMPLATES["jedi_order"]
        sheet = _build_anchor_sheet(tmpl, 140)
        self.assertIn("dodge", sheet["skills"])
        self.assertIn("blaster", sheet["skills"])
        self.assertIn("brawling", sheet["skills"])

    def test_sheet_includes_weapon(self):
        from engine.contest import _build_anchor_sheet, _REGION_ANCHOR_TEMPLATES
        tmpl = _REGION_ANCHOR_TEMPLATES["cis"]
        sheet = _build_anchor_sheet(tmpl, 100)
        self.assertEqual(sheet["weapon"], tmpl["weapon"])


# ──────────────────────────────────────────────────────────────────────
# 4. TestTwoPhaseTick
# ──────────────────────────────────────────────────────────────────────

class TestTwoPhaseTick(unittest.TestCase):
    """Two-phase tick: Phase A spawn + Phase B defender-win."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            start_room_id=100,
        )

    def _insert_contest(self, *, defender, challenger,
                          accumulation_offset, ends_offset,
                          anchor_npc_id=None):
        """Insert a contest with phase timestamps offset from now."""
        now = time.time()
        _run(self.mdb.execute(
            """INSERT INTO region_contests
               (region_slug, defender_org_code, challenger_org_code,
                zone_id, started_at, accumulation_ends_at, ends_at,
                anchor_npc_id, status)
               VALUES ('dune_sea', ?, ?, 1, ?, ?, ?, ?, 'active')""",
            (defender, challenger,
             now - 7 * 86400, now + accumulation_offset,
             now + ends_offset, anchor_npc_id),
        ))

    def test_phase_a_spawns_anchor_when_culminating_window_opens(self):
        """now >= accum_ends_at AND ends_at > now AND anchor IS NULL → spawn."""
        from engine.contest import tick_region_contest_resolution
        # Influence to scale Anchor HP
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=90)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=70)
        self._insert_contest(
            defender="hutt_cartel", challenger="cis",
            accumulation_offset=-100,   # past
            ends_offset=+3600,           # 1h to go
            anchor_npc_id=None,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        # Anchor pinned
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertIsNotNone(rows[0]["anchor_npc_id"])
        self.assertIsNotNone(rows[0]["anchor_landmark_id"])
        # Status still active
        self.assertEqual(rows[0]["status"], "active")
        # NPC actually exists
        npc = _run(self.mdb.get_npc(rows[0]["anchor_npc_id"]))
        self.assertIsNotNone(npc)
        # Sheet records HP target
        sheet = json.loads(npc["char_sheet_json"])
        self.assertEqual(sheet["anchor_target_hp"], 140)  # 100 + (90-50)

    def test_phase_a_idempotent_when_anchor_already_spawned(self):
        """Already-spawned Anchor doesn't get re-spawned on next tick."""
        from engine.contest import tick_region_contest_resolution
        self._insert_contest(
            defender="hutt_cartel", challenger="cis",
            accumulation_offset=-100,
            ends_offset=+3600,
            anchor_npc_id=999,   # pretend already spawned
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["anchor_npc_id"], 999)  # unchanged

    def test_phase_b_resolves_expired_as_defender_win(self):
        """Expired contest with no Anchor kill → defender wins."""
        from engine.contest import tick_region_contest_resolution
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)
        self._insert_contest(
            defender="hutt_cartel", challenger="cis",
            accumulation_offset=-4 * 3600,
            ends_offset=-10,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests "
            "WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["status"], "resolved_defender")

    def test_phase_a_skipped_before_accumulation_ends(self):
        """In accumulation window — no spawn, no resolution."""
        from engine.contest import tick_region_contest_resolution
        self._insert_contest(
            defender="hutt_cartel", challenger="cis",
            accumulation_offset=+3600,  # future
            ends_offset=+7200,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertIsNone(rows[0]["anchor_npc_id"])
        self.assertEqual(rows[0]["status"], "active")

    def test_phase_a_skipped_if_already_expired(self):
        """Already expired — Phase A's ends_at > now filter excludes it."""
        from engine.contest import tick_region_contest_resolution
        self._insert_contest(
            defender="hutt_cartel", challenger="cis",
            accumulation_offset=-4 * 3600,
            ends_offset=-10,
        )
        _run(tick_region_contest_resolution(self.mdb, session_mgr=None))
        # Phase A is gated on ends_at > now; this contest fell through
        # to Phase B which marked it resolved_defender without an
        # anchor_npc_id (no spawn). Verify Phase B's outcome.
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE region_slug='dune_sea'"))
        self.assertEqual(rows[0]["status"], "resolved_defender")
        self.assertIsNone(rows[0]["anchor_npc_id"])


# ──────────────────────────────────────────────────────────────────────
# 5. TestSpawnRegionAnchor
# ──────────────────────────────────────────────────────────────────────

class TestSpawnRegionAnchor(unittest.TestCase):
    """Landmark pick, NPC create, reinforcement count."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=5,
            start_room_id=200,
        )

    def _new_contest(self, *, defender, challenger,
                       defender_inf=50, challenger_inf=50):
        from engine.contest import declare_region_contest
        if defender_inf:
            self.mdb.seed_influence(
                zone_id=1, org_code=defender, score=defender_inf)
        if challenger_inf:
            self.mdb.seed_influence(
                zone_id=1, org_code=challenger, score=challenger_inf)
        r = _run(declare_region_contest(
            self.mdb, "dune_sea", defender, challenger,
            zone_id=1, session_mgr=None,
        ))
        return r["contest_id"]

    def test_spawn_picks_a_region_landmark(self):
        from engine.contest import _spawn_region_anchor
        cid = self._new_contest(
            defender="hutt_cartel", challenger="cis",
            defender_inf=60, challenger_inf=60,
        )
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?", (cid,)))[0]
        anchor_id = _run(_spawn_region_anchor(
            self.mdb, contest, session_mgr=None))
        self.assertIsNotNone(anchor_id)
        # Landmark must be one of the region's rooms (200..204)
        rows = _run(self.mdb.fetchall(
            "SELECT anchor_landmark_id FROM region_contests WHERE id = ?",
            (cid,)))
        self.assertIn(rows[0]["anchor_landmark_id"], range(200, 205))

    def test_spawn_reinforcement_count_matches_pure_rule(self):
        from engine.contest import (
            _spawn_region_anchor,
            compute_anchor_reinforcements,
        )
        cid = self._new_contest(
            defender="hutt_cartel", challenger="cis",
            defender_inf=50, challenger_inf=150,
        )
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?", (cid,)))[0]
        _run(_spawn_region_anchor(self.mdb, contest, session_mgr=None))
        # Count NPCs in the chosen landmark
        rows = _run(self.mdb.fetchall(
            "SELECT anchor_landmark_id FROM region_contests WHERE id = ?",
            (cid,)))
        landmark_id = rows[0]["anchor_landmark_id"]
        npcs = _run(self.mdb.fetchall(
            "SELECT id FROM npcs WHERE room_id = ?", (landmark_id,)))
        # Anchor + compute_anchor_reinforcements(150) = 1 + 2 = 3
        expected = 1 + compute_anchor_reinforcements(150)
        self.assertEqual(len(npcs), expected)

    def test_spawn_no_landmarks_returns_none(self):
        """Region with zero landmarks → spawn fails gracefully."""
        from engine.contest import _spawn_region_anchor
        # Wipe landmark rows so _get_region_landmarks returns []
        _run(self.mdb.execute(
            "DELETE FROM rooms WHERE wilderness_region_id = ?",
            ("dune_sea",)))
        cid = self._new_contest(
            defender="hutt_cartel", challenger="cis",
            defender_inf=60, challenger_inf=60,
        )
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?", (cid,)))[0]
        result = _run(_spawn_region_anchor(
            self.mdb, contest, session_mgr=None))
        self.assertIsNone(result)

    def test_spawn_unowned_region_uses_default_template(self):
        """defender=None → falls back to _default template."""
        from engine.contest import _spawn_region_anchor
        # Fresh region without owner
        self.mdb.seed_region(
            slug="coruscant_underworld", zone_id=2,
            owner_org_code=None,
            landmark_count=3,
            start_room_id=300,
        )
        from engine.contest import declare_region_contest
        self.mdb.seed_influence(zone_id=2, org_code="cis", score=60)
        r = _run(declare_region_contest(
            self.mdb, "coruscant_underworld", None, "cis",
            zone_id=2, session_mgr=None,
        ))
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (r["contest_id"],)))[0]
        anchor_id = _run(_spawn_region_anchor(
            self.mdb, contest, session_mgr=None))
        self.assertIsNotNone(anchor_id)
        npc = _run(self.mdb.get_npc(anchor_id))
        # _default template's name_prefix
        self.assertIn("Region Anchor", npc["name"])


# ──────────────────────────────────────────────────────────────────────
# 6. TestOnNpcKilledInCombat
# ──────────────────────────────────────────────────────────────────────

class TestOnNpcKilledInCombat(unittest.TestCase):
    """Anchor kill detection + outcome routing."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=3,
            start_room_id=100,
        )
        # Seed contest with Anchor already spawned
        from engine.contest import declare_region_contest, _spawn_region_anchor
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=60)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=60)
        r = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.contest_id = r["contest_id"]
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        self.anchor_npc_id = _run(_spawn_region_anchor(
            self.mdb, contest, session_mgr=None))

    def test_challenger_kills_anchor_wins_region(self):
        from engine.contest import on_npc_killed_in_combat
        killer = {"id": 7, "name": "Acolyte", "faction_id": "cis"}
        result = _run(on_npc_killed_in_combat(
            self.mdb, self.anchor_npc_id, killer, 100,
            session_mgr=None,
        ))
        self.assertIsNotNone(result)
        self.assertEqual(result["status"], "resolved_challenger")
        # Ownership transferred
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_ownership WHERE region_slug = ?",
            ("dune_sea",)))
        self.assertEqual(rows[0]["org_code"], "cis")

    def test_defender_kills_anchor_defender_wins(self):
        """A defender-faction killer is a corner case → defender wins.

        Mechanically rare (Anchor IS the defender NPC), but if some
        defender-coded killer registers as having struck the Anchor,
        the contest resolves for the defender by the same code path.
        """
        from engine.contest import on_npc_killed_in_combat
        killer = {"id": 8, "name": "Hutt Loyalist", "faction_id": "hutt_cartel"}
        result = _run(on_npc_killed_in_combat(
            self.mdb, self.anchor_npc_id, killer, 100,
            session_mgr=None,
        ))
        self.assertEqual(result["status"], "resolved_defender")
        # Ownership UNCHANGED
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_ownership WHERE region_slug = ?",
            ("dune_sea",)))
        self.assertEqual(rows[0]["org_code"], "hutt_cartel")

    def test_no_faction_killer_defender_wins(self):
        """Independent / NPC-on-NPC kill → defender wins by default."""
        from engine.contest import on_npc_killed_in_combat
        killer = {"id": 9, "name": "Lone Wolf", "faction_id": "independent"}
        result = _run(on_npc_killed_in_combat(
            self.mdb, self.anchor_npc_id, killer, 100,
            session_mgr=None,
        ))
        self.assertEqual(result["status"], "resolved_defender")

    def test_none_killer_defender_wins(self):
        """killer_char=None → defender wins by default."""
        from engine.contest import on_npc_killed_in_combat
        result = _run(on_npc_killed_in_combat(
            self.mdb, self.anchor_npc_id, None, 100,
            session_mgr=None,
        ))
        self.assertEqual(result["status"], "resolved_defender")

    def test_non_anchor_npc_is_noop(self):
        from engine.contest import on_npc_killed_in_combat
        # NPC id 99999 isn't anyone's Anchor
        result = _run(on_npc_killed_in_combat(
            self.mdb, 99999, {"id": 1, "faction_id": "cis"}, 100,
            session_mgr=None,
        ))
        self.assertIsNone(result)
        # Contest still active
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests WHERE id = ?",
            (self.contest_id,)))
        self.assertEqual(rows[0]["status"], "active")

    def test_zero_npc_id_is_noop(self):
        from engine.contest import on_npc_killed_in_combat
        result = _run(on_npc_killed_in_combat(
            self.mdb, 0, {"id": 1, "faction_id": "cis"}, 100,
            session_mgr=None,
        ))
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────
# 7. TestResolveChallengerWin
# ──────────────────────────────────────────────────────────────────────

class TestResolveChallengerWin(unittest.TestCase):
    """Ownership transfer + defender penalty + cooldown."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=3,
            start_room_id=100,
        )
        from engine.contest import declare_region_contest
        self.mdb.seed_influence(zone_id=1, org_code="hutt_cartel", score=70)
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=60)
        r = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.contest_id = r["contest_id"]

    def test_ownership_transfers_to_winner(self):
        from engine.contest import _resolve_challenger_win
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_ownership WHERE region_slug = ?",
            ("dune_sea",)))
        self.assertEqual(rows[0]["org_code"], "cis")

    def test_defender_pays_penalty_in_parent_zone(self):
        from engine.contest import (
            _resolve_challenger_win,
            REGION_CONTEST_FAILURE_PENALTY,
        )
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id=1 AND org_code='hutt_cartel'"))
        self.assertEqual(rows[0]["score"],
                         70 - REGION_CONTEST_FAILURE_PENALTY)

    def test_defender_on_cooldown_after_loss(self):
        from engine.contest import (
            _resolve_challenger_win,
            is_org_on_contest_cooldown,
        )
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=None))
        self.assertTrue(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "hutt_cartel")))

    def test_unowned_region_win_creates_ownership_row(self):
        from engine.contest import _resolve_challenger_win
        # Drop existing ownership
        _run(self.mdb.execute(
            "DELETE FROM region_ownership WHERE region_slug='dune_sea'"))
        # Re-fetch contest (defender is hutt_cartel from setUp)
        # Manually patch defender_org_code to NULL for this case
        _run(self.mdb.execute(
            "UPDATE region_contests SET defender_org_code=NULL WHERE id=?",
            (self.contest_id,)))
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT * FROM region_ownership WHERE region_slug = ?",
            ("dune_sea",)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["org_code"], "cis")

    def test_resolved_challenger_status_set(self):
        from engine.contest import _resolve_challenger_win
        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=None))
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests WHERE id = ?",
            (self.contest_id,)))
        self.assertEqual(rows[0]["status"], "resolved_challenger")

    def test_broadcast_on_seize(self):
        from engine.contest import _resolve_challenger_win
        sent = []

        class FakeSession:
            is_in_game = True
            async def send_line(self, msg):
                sent.append(msg)

        class FakeMgr:
            all = [FakeSession()]

        contest = _run(self.mdb.fetchall(
            "SELECT * FROM region_contests WHERE id = ?",
            (self.contest_id,)))[0]
        _run(_resolve_challenger_win(
            self.mdb, contest, "cis", session_mgr=FakeMgr()))
        self.assertGreater(len(sent), 0)
        self.assertIn("REGION SEIZED", sent[0])


# ──────────────────────────────────────────────────────────────────────
# 8. TestContestInfluenceMultipliers
# ──────────────────────────────────────────────────────────────────────

class TestContestInfluenceMultipliers(unittest.TestCase):
    """2× doubling + 1.5× outnumbered defender."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=2,
            start_room_id=100,
        )
        from engine.contest import declare_region_contest
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))

    def test_no_contest_passthrough(self):
        """Region has no active contest → delta unchanged."""
        from engine.contest import apply_contest_influence_multipliers
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "cis", "nonexistent_region", 10))
        self.assertEqual(result, 10)

    def test_non_contestant_passthrough(self):
        """Org not in the active contest → delta unchanged."""
        from engine.contest import apply_contest_influence_multipliers
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "republic", "dune_sea", 10))
        self.assertEqual(result, 10)

    def test_challenger_doubled(self):
        """Challenger positive delta → 2×."""
        from engine.contest import apply_contest_influence_multipliers
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "cis", "dune_sea", 10))
        self.assertEqual(result, 20)

    def test_defender_doubled_when_not_outnumbered(self):
        """Defender, equal/more members → 2× only."""
        from engine.contest import apply_contest_influence_multipliers
        # No members on either side → equal (0 == 0), no outnumbered bonus
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "hutt_cartel", "dune_sea", 10))
        self.assertEqual(result, 20)

    def test_defender_outnumbered_triple(self):
        """Defender outnumbered → 2× × 1.5× = 3×."""
        from engine.contest import apply_contest_influence_multipliers
        # 2 defender members, 5 challenger members
        for cid in (101, 102):
            self.mdb.seed_membership(char_id=cid, org_id=1)
        for cid in (201, 202, 203, 204, 205):
            self.mdb.seed_membership(char_id=cid, org_id=2)
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "hutt_cartel", "dune_sea", 10))
        self.assertEqual(result, 30)

    def test_negative_delta_untouched(self):
        from engine.contest import apply_contest_influence_multipliers
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "cis", "dune_sea", -5))
        self.assertEqual(result, -5)

    def test_zero_delta_untouched(self):
        from engine.contest import apply_contest_influence_multipliers
        result = _run(apply_contest_influence_multipliers(
            self.mdb, "cis", "dune_sea", 0))
        self.assertEqual(result, 0)


# ──────────────────────────────────────────────────────────────────────
# 9. TestAdjustTerritoryInfluenceHook
# ──────────────────────────────────────────────────────────────────────

class TestAdjustTerritoryInfluenceHook(unittest.TestCase):
    """adjust_territory_influence applies the multiplier when region_slug
    is passed."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_org(org_id=1, code="hutt_cartel")
        self.mdb.seed_org(org_id=2, code="cis")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=2,
            start_room_id=100,
        )

    def test_no_region_kwarg_no_multiplier(self):
        """Without region_slug, contest multiplier doesn't apply."""
        from engine.territory import adjust_territory_influence
        from engine.contest import declare_region_contest
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        new_score = _run(adjust_territory_influence(
            self.mdb, "cis", 1, 10, reason="test"))
        self.assertEqual(new_score, 10)

    def test_with_region_kwarg_doubled_during_contest(self):
        from engine.territory import adjust_territory_influence
        from engine.contest import declare_region_contest
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        new_score = _run(adjust_territory_influence(
            self.mdb, "cis", 1, 10, reason="test",
            region_slug="dune_sea"))
        self.assertEqual(new_score, 20)

    def test_negative_delta_with_region_unchanged(self):
        from engine.territory import adjust_territory_influence
        from engine.contest import declare_region_contest
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=50)
        _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        new_score = _run(adjust_territory_influence(
            self.mdb, "cis", 1, -10, reason="penalty",
            region_slug="dune_sea"))
        self.assertEqual(new_score, 40)


# ──────────────────────────────────────────────────────────────────────
# 10. TestCancelRegionContest
# ──────────────────────────────────────────────────────────────────────

class TestCancelRegionContest(unittest.TestCase):
    """Admin/exception path: cancel → status='failed', no penalties."""

    def setUp(self):
        self.mdb = _MiniDB()
        _run(_setup_schema(self.mdb))
        self.mdb.seed_zone(zone_id=1, name="Tatooine")
        self.mdb.seed_region(
            slug="dune_sea", zone_id=1,
            owner_org_code="hutt_cartel",
            landmark_count=2,
            start_room_id=100,
        )
        from engine.contest import declare_region_contest
        r = _run(declare_region_contest(
            self.mdb, "dune_sea", "hutt_cartel", "cis",
            zone_id=1, session_mgr=None,
        ))
        self.contest_id = r["contest_id"]

    def test_cancel_sets_failed_status(self):
        from engine.contest import cancel_region_contest
        result = _run(cancel_region_contest(
            self.mdb, self.contest_id, reason="admin test"))
        self.assertTrue(result["ok"])
        rows = _run(self.mdb.fetchall(
            "SELECT status FROM region_contests WHERE id = ?",
            (self.contest_id,)))
        self.assertEqual(rows[0]["status"], "failed")

    def test_cancel_no_penalty(self):
        """Cancel does NOT apply the failure penalty."""
        from engine.contest import cancel_region_contest
        self.mdb.seed_influence(zone_id=1, org_code="cis", score=80)
        _run(cancel_region_contest(
            self.mdb, self.contest_id, reason="admin test"))
        rows = _run(self.mdb.fetchall(
            "SELECT score FROM territory_influence "
            "WHERE zone_id=1 AND org_code='cis'"))
        self.assertEqual(rows[0]["score"], 80)

    def test_cancel_no_cooldown(self):
        from engine.contest import (
            cancel_region_contest, is_org_on_contest_cooldown,
        )
        _run(cancel_region_contest(
            self.mdb, self.contest_id, reason="admin test"))
        self.assertFalse(_run(is_org_on_contest_cooldown(
            self.mdb, "dune_sea", "cis")))

    def test_cancel_rejects_unknown_id(self):
        from engine.contest import cancel_region_contest
        result = _run(cancel_region_contest(self.mdb, 99999))
        self.assertFalse(result["ok"])

    def test_cancel_rejects_already_resolved(self):
        from engine.contest import cancel_region_contest
        _run(cancel_region_contest(self.mdb, self.contest_id))
        # Second cancel of the same contest should fail
        result = _run(cancel_region_contest(self.mdb, self.contest_id))
        self.assertFalse(result["ok"])


# ──────────────────────────────────────────────────────────────────────
# 11. TestDrop6dPhysicallyDeleted
# ──────────────────────────────────────────────────────────────────────

class TestDrop6dPhysicallyDeleted(unittest.TestCase):
    """Sanity: Drop 6D contest surfaces are physically gone."""

    def test_territory_lacks_drop6d_contest_functions(self):
        import engine.territory as tt
        for sym in [
            "ensure_contest_schema",
            "get_active_contest",
            "get_contests_for_org",
            "is_in_active_contest",
            "_declare_contest",
            "check_and_declare_contests",
            "tick_contest_resolution",
            "_transfer_zone_claims",
            "hostile_takeover_claim",
            "get_contest_status_lines",
        ]:
            self.assertFalse(
                hasattr(tt, sym),
                f"engine.territory still has the deleted symbol {sym!r}",
            )

    def test_territory_lacks_drop6d_constants(self):
        import engine.territory as tt
        for sym in [
            "CONTEST_DURATION_SECS",
            "CONTEST_TRIGGER_RATIO",
            "CONTEST_DECAY_MULTIPLIER",
            "CONTEST_FAILURE_PENALTY",
        ]:
            self.assertFalse(
                hasattr(tt, sym),
                f"engine.territory still has the deleted constant {sym!r}",
            )

    def test_faction_commands_lacks_cmd_seize(self):
        from parser.faction_commands import FactionCommand
        self.assertFalse(
            hasattr(FactionCommand, "_cmd_seize"),
            "parser.faction_commands.FactionCommand still has _cmd_seize",
        )


# ──────────────────────────────────────────────────────────────────────
# 12. TestCallerRetargets — source-level check
# ──────────────────────────────────────────────────────────────────────

class TestCallerRetargets(unittest.TestCase):
    """Source-level check that callers now reach into engine.contest."""

    def test_session_hud_calls_region_surfaces(self):
        src = (PROJECT_ROOT / "server" / "session.py").read_text(
            encoding="utf-8")
        self.assertIn("get_region_owner", src,
                      "session._hud_territory must use get_region_owner")
        self.assertIn("get_active_region_contest", src,
                      "session._hud_territory must use "
                      "get_active_region_contest")
        # And the deleted Drop 6D imports must be gone. Use a
        # token-level check: scan for `get_active_contest` NOT
        # followed by `_region_contest` etc. (substring containment
        # would falsely match `get_active_region_contest`).
        import re
        bad = re.search(r"\bget_active_contest\b", src)
        self.assertIsNone(
            bad,
            "session.py still references the deleted "
            "get_active_contest (zone-keyed Drop 6D surface)")

    def test_combat_pvp_gate_uses_region(self):
        src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8")
        self.assertIn("is_region_in_active_contest", src,
                      "combat_commands PvP gate must use "
                      "is_region_in_active_contest")
        # Drop 6D import gone — use token-level check to avoid
        # matching the substring inside `is_region_in_active_contest`.
        import re
        bad = re.search(r"(?<!region_)\bis_in_active_contest\b", src)
        self.assertIsNone(
            bad,
            "combat_commands still references the deleted "
            "is_in_active_contest (zone-keyed Drop 6D surface)")

    def test_combat_npc_death_calls_on_npc_killed_in_combat(self):
        src = (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8")
        self.assertIn("on_npc_killed_in_combat", src,
                      "combat_commands must call on_npc_killed_in_combat "
                      "after NPC death")
        # Drop 6D hostile-takeover call gone (no substring overlap).
        self.assertNotIn("hostile_takeover_claim", src,
                         "combat_commands still calls hostile_takeover_claim")

    def test_tick_handler_calls_region_resolution(self):
        src = (PROJECT_ROOT / "server" / "tick_handlers_economy.py").read_text(
            encoding="utf-8")
        self.assertIn("tick_region_contest_resolution", src,
                      "tick handler must call tick_region_contest_resolution")
        # Token-level check: `tick_contest_resolution` is a substring
        # of `tick_region_contest_resolution`, so use a word-boundary
        # regex instead of plain assertNotIn.
        import re
        bad = re.search(
            r"(?<!region_)\btick_contest_resolution\b", src)
        self.assertIsNone(
            bad,
            "tick handler still references the deleted "
            "tick_contest_resolution (zone-keyed Drop 6D surface)")


if __name__ == "__main__":
    unittest.main()
