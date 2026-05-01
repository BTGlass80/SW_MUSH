# -*- coding: utf-8 -*-
"""
tests/test_b1d2_housing_codeflow_era_aware.py — B.1.d.2 tests.

Per `b1_audit_v1.md` §3 row B.1.d, B.1.d is split into two sub-drops:

  - **B.1.d.1 (shipped):** Pure data-table extensions —
    FACTION_QUARTER_TIERS, FACTION_HOME_PLANET, _TIER5_ROOM_DESCS,
    _planet_view all extended with CW factions.

  - **B.1.d.2 (this drop):** Code-flow changes:
      1. `INSURGENT_FACTIONS` set + `is_insurgent_faction(fc)` helper
         that generalize the pre-drop hardcoded `is_rebel = faction_code
         == "rebel"` check. Both `rebel` (GCW) and `cis` (CW) are
         insurgent factions whose safehouse exits are hidden from
         non-members.
      2. Exit hiding now uses the actual `faction_code` as the
         `hidden_faction` value (not always the literal string "rebel"),
         so a CIS PC's quarters exit is hidden as `hidden_faction='cis'`
         and only visible to CIS members.
      3. `_faction_quarters_locatable(fc)` helper distinguishes:
         - Factions whose home-planet rooms aren't built yet (no
           FACTION_QUARTER_LOTS entry for the (faction, planet) pair):
           soft `log.info` + a friendly player-facing message that
           quarters will be assigned when the location opens. As of
           B.1.d.3 (Apr 30 2026), all 4 CW factions (republic, cis,
           jedi_order, hutt_cartel) have anchor entries wired; this
           branch is now hit only by factions added to home_planet
           without a corresponding lot, or by accidental drift.
         - Real bug paths (faction has both home_planet AND
           quarter_lots entries but the room is missing): `log.warning`
           as before.
      4. `assign_faction_quarters` updated to use the helpers above
         and the new branched bail logic.

Test classes split into:
  - "InsurgentFactions" — INSURGENT_FACTIONS + is_insurgent_faction
  - "FactionQuartersLocatable" — _faction_quarters_locatable helper
  - "AssignFactionQuartersGCWByteEquivalence" — Imperial / Rebel /
    Hutt paths produce identical behavior to pre-B.1.d.2
  - "AssignFactionQuartersCWNotYetBuilt" — Republic / CIS / Jedi
    paths take the soft-bail path with player-facing message
  - "InsurgentExitHiding" — Rebel exit hidden as 'rebel'; CIS exit
    hidden as 'cis'; Republic / Hutt / Jedi / BHG exits visible
  - "IsExitVisibleIntegration" — `is_exit_visible` reads the new
    hidden_faction values correctly per faction
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# Mock DB — covers everything assign_faction_quarters touches
# ──────────────────────────────────────────────────────────────────────

def _mock_db_for_assign():
    """Mock DB with the methods assign_faction_quarters calls.

    The mock records:
      - db._created_rooms: list of dicts passed to create_room
      - db._created_exits: list of (from_id, to_id, dir, name) tuples
      - db._exec_calls:    list of (sql, params) tuples for execute()
      - db._commits:       counter
      - db._inserted_housing_id: set on player_housing INSERT
      - db._character_updates: list of save_character kwargs
    """
    db = MagicMock()
    db._created_rooms = []
    db._created_exits = []
    db._exec_calls = []
    db._commits = 0
    db._inserted_housing_id = 4242
    db._character_updates = []

    # Default GCW faction-quarter entry rooms (id=22 is Tatooine
    # Militia HQ, used for empire). Tests can override per-faction.
    db._room_table = {
        22: {"id": 22, "name": "Tatooine Militia HQ",
             "properties": json.dumps({"security": "secured"})},
        47: {"id": 47, "name": "Outskirts Compound",
             "properties": json.dumps({"security": "lawless"})},
        69: {"id": 69, "name": "Undercity Warrens",
             "properties": json.dumps({"security": "lawless"})},
        19: {"id": 19, "name": "Jabba's Townhouse",
             "properties": json.dumps({"security": "contested"})},
        72: {"id": 72, "name": "Hutt Emissary Tower",
             "properties": json.dumps({"security": "contested"})},
    }

    async def _get_room(room_id):
        return db._room_table.get(room_id)

    async def _create_room(name, desc_short, desc_long, zone_id=None,
                           properties="{}"):
        rid = 9000 + len(db._created_rooms)
        rec = {"id": rid, "name": name, "desc_short": desc_short,
               "desc_long": desc_long, "zone_id": zone_id,
               "properties": properties}
        db._created_rooms.append(rec)
        db._room_table[rid] = rec
        return rid

    _exit_counter = [10000]

    async def _create_exit(from_id, to_id, direction, name):
        eid = _exit_counter[0]
        _exit_counter[0] += 1
        db._created_exits.append({
            "id": eid, "from": from_id, "to": to_id,
            "direction": direction, "name": name,
        })
        return eid

    async def _execute(sql, params=None):
        db._exec_calls.append((sql, params or ()))
        # For the player_housing INSERT, return a cursor with lastrowid
        cur = MagicMock()
        cur.lastrowid = db._inserted_housing_id
        return cur

    async def _fetchall(sql, params=None):
        # Dispatch on SQL: get_housing's player_housing SELECT must
        # return [] (no existing housing); the home_room_id check must
        # return a row with home_room_id=None.
        if "FROM player_housing" in sql:
            return []
        if "home_room_id" in sql:
            return [{"home_room_id": None}]
        return []

    async def _commit():
        db._commits += 1

    async def _save_character(char_id, **kwargs):
        db._character_updates.append({"char_id": char_id, **kwargs})

    async def _update_room(*args, **kwargs):
        pass

    async def _get_player_housing(char_id):
        return None  # No existing housing

    db.get_room = AsyncMock(side_effect=_get_room)
    db.create_room = AsyncMock(side_effect=_create_room)
    db.create_exit = AsyncMock(side_effect=_create_exit)
    db.execute = AsyncMock(side_effect=_execute)
    db.fetchall = AsyncMock(side_effect=_fetchall)
    db.commit = AsyncMock(side_effect=_commit)
    db.save_character = AsyncMock(side_effect=_save_character)
    db.update_room = AsyncMock(side_effect=_update_room)
    db.get_player_housing = AsyncMock(side_effect=_get_player_housing)
    return db


def _mock_session():
    """Mock session capturing send_line output."""
    s = MagicMock()
    s.lines = []

    async def _capture(line):
        s.lines.append(line)

    s.send_line = AsyncMock(side_effect=_capture)
    return s


def _make_char(faction_code, char_id=100):
    return {"id": char_id, "name": "TestPC",
            "faction_id": faction_code, "account_id": 1}


# ──────────────────────────────────────────────────────────────────────
# 1. INSURGENT_FACTIONS + is_insurgent_faction
# ──────────────────────────────────────────────────────────────────────

class TestInsurgentFactions(unittest.TestCase):

    def test_insurgent_factions_set_exists(self):
        from engine.housing import INSURGENT_FACTIONS
        self.assertIsInstance(INSURGENT_FACTIONS, frozenset)

    def test_rebel_is_insurgent(self):
        from engine.housing import is_insurgent_faction
        self.assertTrue(is_insurgent_faction("rebel"))

    def test_cis_is_insurgent(self):
        from engine.housing import is_insurgent_faction
        self.assertTrue(is_insurgent_faction("cis"))

    def test_empire_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        # Empire is the lawful state of GCW; its quarters are overt
        # garrisons, not safehouses.
        self.assertFalse(is_insurgent_faction("empire"))

    def test_republic_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        # Republic is the lawful state of CW.
        self.assertFalse(is_insurgent_faction("republic"))

    def test_jedi_order_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        # Jedi Temple is a public institution, not a safehouse.
        self.assertFalse(is_insurgent_faction("jedi_order"))

    def test_hutt_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        # Hutt cartels are overt criminal organizations — flashy, not hidden.
        self.assertFalse(is_insurgent_faction("hutt"))
        self.assertFalse(is_insurgent_faction("hutt_cartel"))

    def test_bounty_hunters_guild_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        self.assertFalse(is_insurgent_faction("bh_guild"))
        self.assertFalse(is_insurgent_faction("bounty_hunters_guild"))

    def test_unknown_faction_is_not_insurgent(self):
        from engine.housing import is_insurgent_faction
        self.assertFalse(is_insurgent_faction("nonexistent_faction"))


# ──────────────────────────────────────────────────────────────────────
# 2. _faction_quarters_locatable
# ──────────────────────────────────────────────────────────────────────

class TestFactionQuartersLocatable(unittest.TestCase):

    def test_empire_locatable(self):
        from engine.housing import _faction_quarters_locatable
        # Empire has both FACTION_HOME_PLANET[empire]="tatooine" AND
        # FACTION_QUARTER_LOTS[("empire","tatooine")]=22.
        self.assertTrue(_faction_quarters_locatable("empire"))

    def test_rebel_locatable(self):
        from engine.housing import _faction_quarters_locatable
        # Rebel has FACTION_HOME_PLANET[rebel]="tatooine" AND
        # FACTION_QUARTER_LOTS[("rebel","tatooine")]=47.
        self.assertTrue(_faction_quarters_locatable("rebel"))

    def test_hutt_locatable(self):
        from engine.housing import _faction_quarters_locatable
        # Hutt: home=nar_shaddaa, lot=72.
        self.assertTrue(_faction_quarters_locatable("hutt"))

    def test_republic_locatable_post_b1d3(self):
        # ── B.1.d.3 (Apr 30 2026): republic is now locatable ────────────
        # Pre-B.1.d.3 this asserted False; B.1.d.3 wired
        # ("republic","coruscant") -> 259 (Coco Town Civic Block)
        # into FACTION_QUARTER_LOTS.
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("republic"))

    def test_cis_locatable_post_b1d3(self):
        # ── B.1.d.3 (Apr 30 2026): cis is now locatable ─────────────────
        # Pre-B.1.d.3 this asserted False; B.1.d.3 wired
        # ("cis","geonosis") -> 418 (Geonosis Deep Hive Tunnel) into
        # FACTION_QUARTER_LOTS.
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("cis"))

    def test_jedi_order_locatable_post_f5d(self):
        # ── F.5d (Apr 30 2026): jedi_order is now locatable ─────────────
        # Pre-F.5d this asserted False; F.5d wired
        # ("jedi_order","coruscant") -> 211 (Jedi Temple Entrance Hall)
        # into FACTION_QUARTER_LOTS. B.1.d.3 (Apr 30 2026, same day)
        # subsequently closed the remaining CW gap by wiring republic/
        # cis/hutt_cartel anchors — see test_*_locatable_post_b1d3
        # tests above.
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("jedi_order"))

    def test_hutt_cartel_locatable_post_b1d3(self):
        # ── B.1.d.3 (Apr 30 2026): hutt_cartel is now locatable ─────────
        # Pre-B.1.d.3 this asserted False; B.1.d.3 wired
        # ("hutt_cartel","nar_shaddaa") -> 71 (Hutt Emissary Tower
        # Audience Chamber) into FACTION_QUARTER_LOTS, mirroring the
        # GCW (hutt, "nar_shaddaa"): 72 pattern but distinguishing the
        # CW faction-code namespace.
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("hutt_cartel"))

    def test_bounty_hunters_guild_not_locatable(self):
        from engine.housing import _faction_quarters_locatable
        # BHG has neither home_planet entry nor lot entry; the
        # _planet_for_faction default kicks it to "tatooine" and
        # there's no (bhg, tatooine) lot. Result: False, no crash.
        self.assertFalse(_faction_quarters_locatable("bounty_hunters_guild"))


# ──────────────────────────────────────────────────────────────────────
# 3. assign_faction_quarters — GCW byte-equivalence
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersGCWByteEquivalence(unittest.TestCase):
    """The Imperial, Rebel, and Hutt assignment paths must produce
    behavior byte-equivalent to pre-B.1.d.2."""

    def test_empire_rank_0_creates_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_assign()
        sess = _mock_session()
        char = _make_char("empire")
        result = _run(assign_faction_quarters(db, char, "empire", 0,
                                              session=sess))
        # Quarters should be created
        self.assertEqual(len(db._created_rooms), 1)
        # Player_housing INSERT should be the recorded execute call
        sql_calls = [c[0] for c in db._exec_calls]
        self.assertTrue(any("INSERT INTO player_housing" in s for s in sql_calls),
                        "player_housing INSERT should fire")
        # No "exits SET hidden_faction" call — empire is not insurgent
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(hidden_calls, [],
                         "Imperial quarters should not hide the entry exit")

    def test_rebel_rank_1_creates_hidden_exit(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_assign()
        sess = _mock_session()
        char = _make_char("rebel")
        _run(assign_faction_quarters(db, char, "rebel", 1, session=sess))
        # Should have created the rebel quarters
        self.assertEqual(len(db._created_rooms), 1)
        # Hidden-faction UPDATE should fire with 'rebel' value
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(len(hidden_calls), 1,
                         "Rebel quarters should hide the entry exit")
        sql, params = hidden_calls[0]
        self.assertEqual(params[0], "rebel",
                         "Hidden faction value should be the literal 'rebel'")

    def test_hutt_rank_2_creates_visible_exit(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_assign()
        sess = _mock_session()
        char = _make_char("hutt")
        _run(assign_faction_quarters(db, char, "hutt", 2, session=sess))
        # Should have created the hutt quarters
        self.assertEqual(len(db._created_rooms), 1)
        # No hidden-faction UPDATE — hutt is not insurgent
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(hidden_calls, [])

    def test_empire_below_min_rank_no_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_assign()
        sess = _mock_session()
        char = _make_char("empire")
        # Rank lookup: empire min is rank 0, so any rank ≥ 0 qualifies.
        # A character at rank "below 0" shouldn't exist, but a faction
        # without a tier ladder for that rank should bail.
        result = _run(assign_faction_quarters(db, char, "rebel", 0,
                                              session=sess))
        # Rebel min rank is 1; rank 0 should yield None
        self.assertIsNone(result)
        self.assertEqual(len(db._created_rooms), 0)


# ──────────────────────────────────────────────────────────────────────
# 4. assign_faction_quarters — CW soft-bail
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersCWNotYetBuilt(unittest.TestCase):
    """Originally exercised the CW soft-bail path (log.info + friendly
    player message) for factions whose home-planet rooms hadn't been
    built yet.

    ── F.5d (Apr 30 2026) — Jedi tests migrated ──
    ── B.1.d.3 (Apr 30 2026) — Republic / CIS / Hutt Cartel tests migrated ──

    Every test in this class is now a tombstone pointing to the
    real-assignment coverage in either:
      - tests/test_f5d_jedi_temple_integration.py (jedi_order)
      - tests/test_b1d3_cw_faction_anchors_wired.py (republic / cis /
        hutt_cartel)

    The `_assert_soft_bail` helper below is preserved as a reference
    implementation for the soft-bail pattern. If a future faction
    is added to FACTION_HOME_PLANET without a corresponding
    FACTION_QUARTER_LOTS entry (intentionally, e.g. for a content
    drop where the home zone hasn't been built yet), use this
    helper to test the soft-bail behavior."""

    def _assert_soft_bail(self, faction_code, rank, planet_name):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_assign()
        sess = _mock_session()
        char = _make_char(faction_code)
        result = _run(assign_faction_quarters(db, char, faction_code, rank,
                                              session=sess))
        self.assertIsNone(result, "Soft-bail returns None")
        # No room created
        self.assertEqual(len(db._created_rooms), 0,
                         "No room creation on soft-bail")
        # No exit created
        self.assertEqual(len(db._created_exits), 0,
                         "No exit creation on soft-bail")
        # Friendly player-facing message sent
        joined = "\n".join(sess.lines)
        self.assertIn("[HOUSING]", joined)
        self.assertIn("not yet established", joined)
        self.assertIn(faction_code, joined)
        self.assertIn(planet_name, joined)

    def test_republic_rank_0_soft_bails(self):
        # ── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────
        # Pre-B.1.d.3 this asserted Republic rank 0 hit the soft-bail
        # path because ("republic","coruscant") was missing from
        # FACTION_QUARTER_LOTS. B.1.d.3 wired room 259 in, so Republic
        # promotion now creates a real Republic Guard Bunk.
        # Real-assignment coverage moved to:
        #   tests/test_b1d3_cw_faction_anchors_wired.py
        #     ::TestAssignFactionQuartersForRepublic::test_rank_0_creates_bunk
        self.skipTest("B.1.d.3 migrated this — see test_b1d3_cw_faction_anchors_wired")

    def test_republic_rank_5_soft_bails(self):
        # ── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────
        # See test_republic_rank_0_soft_bails above. Rank-5 Commander
        # compound creation is at:
        #   tests/test_b1d3_cw_faction_anchors_wired.py
        #     ::TestAssignFactionQuartersForRepublic::test_rank_5_creates_commander_compound
        self.skipTest("B.1.d.3 migrated this — see test_b1d3_cw_faction_anchors_wired")

    def test_cis_rank_0_soft_bails(self):
        # ── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────
        # B.1.d.3 wired ("cis","geonosis") -> 418 (Geonosis Deep Hive
        # Tunnel). Real-assignment coverage moved to:
        #   tests/test_b1d3_cw_faction_anchors_wired.py
        #     ::TestAssignFactionQuartersForCIS::test_rank_0_creates_dormitory
        self.skipTest("B.1.d.3 migrated this — see test_b1d3_cw_faction_anchors_wired")

    def test_cis_rank_4_soft_bails(self):
        # ── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────
        # See test_cis_rank_0_soft_bails above. CIS rank 4 (Officer's
        # Chamber) coverage is in test_b1d3 via the rank-5 Council
        # Suite test, which exercises the same _best_tier_for_rank
        # ladder traversal.
        self.skipTest("B.1.d.3 migrated this — see test_b1d3_cw_faction_anchors_wired")

    def test_jedi_order_rank_0_soft_bails(self):
        # ── F.5d (Apr 30 2026): MIGRATED ────────────────────────────────
        # Pre-F.5d this asserted Jedi rank 0 hit the soft-bail path
        # because ("jedi_order","coruscant") was missing from
        # FACTION_QUARTER_LOTS. F.5d wired room 211 in, so Jedi
        # promotion now creates a real Initiate Cluster room.
        # Real-assignment coverage moved to:
        #   tests/test_f5d_jedi_temple_integration.py
        #     ::TestAssignFactionQuartersForJedi::test_rank_0_initiate_creates_quarters
        # This stub remains as a tombstone so future grep searches
        # for "jedi.*soft_bail" land on the migration note.
        self.skipTest("F.5d migrated this — see test_f5d_jedi_temple_integration")

    def test_jedi_order_rank_5_soft_bails(self):
        # ── F.5d (Apr 30 2026): MIGRATED ────────────────────────────────
        # See test_jedi_order_rank_0_soft_bails above. Real-assignment
        # coverage at rank 5 (Master Suite) is in:
        #   tests/test_f5d_jedi_temple_integration.py
        #     ::TestAssignFactionQuartersForJedi::test_rank_5_master_creates_quarters
        self.skipTest("F.5d migrated this — see test_f5d_jedi_temple_integration")

    def test_hutt_cartel_rank_2_soft_bails(self):
        # ── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────
        # Pre-B.1.d.3 this asserted hutt_cartel rank 2 hit the soft-bail
        # path because ("hutt_cartel","nar_shaddaa") was missing.
        # B.1.d.3 wired room 71 (Hutt Emissary Tower Audience Chamber)
        # in, so hutt_cartel promotion now creates a real Enforcer's
        # Safehouse. Real-assignment coverage moved to:
        #   tests/test_b1d3_cw_faction_anchors_wired.py
        #     ::TestAssignFactionQuartersForHuttCartel::test_rank_2_creates_enforcer_safehouse
        self.skipTest("B.1.d.3 migrated this — see test_b1d3_cw_faction_anchors_wired")


# ──────────────────────────────────────────────────────────────────────
# 5. CIS-specific: insurgent exit hiding, with future-built rooms
# ──────────────────────────────────────────────────────────────────────

class TestInsurgentExitHidingFutureProofing(unittest.TestCase):
    """If a CW lot were added (simulating F.5a), the CIS path would
    correctly mark the exit with hidden_faction='cis'. We test this
    by monkey-patching FACTION_QUARTER_LOTS for the duration of the
    test."""

    def setUp(self):
        import engine.housing as housing
        self._housing = housing
        self._original_lots = dict(housing.FACTION_QUARTER_LOTS)
        self._original_room_table_addition = None

    def tearDown(self):
        # Restore FACTION_QUARTER_LOTS to its pre-test state
        self._housing.FACTION_QUARTER_LOTS.clear()
        self._housing.FACTION_QUARTER_LOTS.update(self._original_lots)

    def test_cis_quarters_simulated_with_lot_hides_exit(self):
        # Inject a synthetic CIS Geonosis lot into the module.
        from engine.housing import (
            FACTION_QUARTER_LOTS, assign_faction_quarters,
        )
        FACTION_QUARTER_LOTS[("cis", "geonosis")] = 555

        db = _mock_db_for_assign()
        # Add the synthetic Geonosis hive entry-room to the room table
        db._room_table[555] = {
            "id": 555, "name": "Stalgasin Hive — Approach",
            "properties": json.dumps({"security": "lawless"}),
        }
        sess = _mock_session()
        char = _make_char("cis")
        _run(assign_faction_quarters(db, char, "cis", 0, session=sess))

        # Quarters should be created
        self.assertEqual(len(db._created_rooms), 1)
        # Hidden-faction UPDATE should fire with 'cis' value
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(len(hidden_calls), 1,
                         "CIS quarters should hide the entry exit")
        _, params = hidden_calls[0]
        self.assertEqual(params[0], "cis",
                         "Hidden faction value should be 'cis', not 'rebel'")

    def test_republic_quarters_simulated_does_not_hide_exit(self):
        from engine.housing import (
            FACTION_QUARTER_LOTS, assign_faction_quarters,
        )
        FACTION_QUARTER_LOTS[("republic", "coruscant")] = 666

        db = _mock_db_for_assign()
        db._room_table[666] = {
            "id": 666, "name": "Coruscant Coco Town — Republic Guard barracks",
            "properties": json.dumps({"security": "secured"}),
        }
        sess = _mock_session()
        char = _make_char("republic")
        _run(assign_faction_quarters(db, char, "republic", 0, session=sess))

        # Quarters created; no hidden-exit update (Republic is overt)
        self.assertEqual(len(db._created_rooms), 1)
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(hidden_calls, [],
                         "Republic quarters should not hide the entry exit")

    def test_jedi_order_quarters_simulated_does_not_hide_exit(self):
        from engine.housing import (
            FACTION_QUARTER_LOTS, assign_faction_quarters,
        )
        FACTION_QUARTER_LOTS[("jedi_order", "coruscant")] = 777

        db = _mock_db_for_assign()
        db._room_table[777] = {
            "id": 777, "name": "Coruscant Jedi Temple — Initiate Wing",
            "properties": json.dumps({"security": "secured"}),
        }
        sess = _mock_session()
        char = _make_char("jedi_order")
        _run(assign_faction_quarters(db, char, "jedi_order", 0,
                                     session=sess))

        # The Jedi Temple is a public institution, not a safehouse.
        self.assertEqual(len(db._created_rooms), 1)
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(hidden_calls, [])


# ──────────────────────────────────────────────────────────────────────
# 6. is_exit_visible interaction
# ──────────────────────────────────────────────────────────────────────

class TestIsExitVisibleIntegration(unittest.TestCase):
    """`is_exit_visible` returns True iff char.faction_id matches
    exit.hidden_faction. With B.1.d.2's per-faction hidden_faction
    values, this means CIS PCs see CIS-hidden exits, etc."""

    def test_rebel_exit_visible_to_rebel(self):
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": "rebel"}
        char = _make_char("rebel")
        self.assertTrue(_run(is_exit_visible(None, exit_row, char)))

    def test_rebel_exit_invisible_to_empire(self):
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": "rebel"}
        char = _make_char("empire")
        self.assertFalse(_run(is_exit_visible(None, exit_row, char)))

    def test_cis_exit_visible_to_cis(self):
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": "cis"}
        char = _make_char("cis")
        self.assertTrue(_run(is_exit_visible(None, exit_row, char)))

    def test_cis_exit_invisible_to_republic(self):
        # The reciprocal of B.1.d.2's design intent: a Republic PC
        # walking past a CIS safehouse entry shouldn't see the exit.
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": "cis"}
        char = _make_char("republic")
        self.assertFalse(_run(is_exit_visible(None, exit_row, char)))

    def test_cis_exit_invisible_to_rebel(self):
        # And vice-era: a (somehow-time-travelled?) Rebel PC shouldn't
        # see a CIS exit either. The hidden_faction string match is
        # exact, not "is_insurgent → see all insurgent exits".
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": "cis"}
        char = _make_char("rebel")
        self.assertFalse(_run(is_exit_visible(None, exit_row, char)))

    def test_no_hidden_faction_visible_to_anyone(self):
        from engine.housing import is_exit_visible
        exit_row = {"hidden_faction": None}
        for faction in ("empire", "rebel", "republic", "cis",
                        "jedi_order", "independent"):
            char = _make_char(faction)
            self.assertTrue(_run(is_exit_visible(None, exit_row, char)),
                            f"Non-hidden exit should be visible to {faction}")


# ──────────────────────────────────────────────────────────────────────
# 7. Pre-drop literal removed
# ──────────────────────────────────────────────────────────────────────

class TestRefactorIntegrity(unittest.TestCase):
    """The pre-B.1.d.2 hardcoded `is_rebel = faction_code == "rebel"`
    literal must be gone from `assign_faction_quarters`. The check
    is now via `is_insurgent_faction(...)`."""

    def test_assign_faction_quarters_no_longer_hardcodes_rebel(self):
        import inspect
        from engine.housing import assign_faction_quarters
        src = inspect.getsource(assign_faction_quarters)
        # The literal local-variable assignment must be gone
        self.assertNotIn('is_rebel = faction_code == "rebel"', src)

    def test_assign_faction_quarters_uses_is_insurgent_faction(self):
        import inspect
        from engine.housing import assign_faction_quarters
        src = inspect.getsource(assign_faction_quarters)
        self.assertIn("is_insurgent_faction", src)

    def test_assign_faction_quarters_uses_locatable_branch(self):
        import inspect
        from engine.housing import assign_faction_quarters
        src = inspect.getsource(assign_faction_quarters)
        self.assertIn("_faction_quarters_locatable", src)


if __name__ == "__main__":
    unittest.main()
