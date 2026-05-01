# -*- coding: utf-8 -*-
"""
tests/test_f5d_jedi_temple_integration.py — F.5d integration test.

F.5d (Apr 30 2026) closes the last F.5 housing slice item: a Jedi PC at
rank 0/1/3/5 sees the right Temple quarters when promoted, and the
quarter-creation flow runs end-to-end through assign_faction_quarters.

Pre-F.5d state:
  - YAML inventory: data/worlds/clone_wars/housing_lots.yaml had the
    jedi_order ladder (rank 0 Initiate / 1 Padawan / 3 Knight / 5 Master)
  - F.5b.1 loaded that ladder into FACTION_QUARTER_TIERS
  - B.1.d.1 added jedi_order to FACTION_HOME_PLANET (→ coruscant)
  - …but FACTION_QUARTER_LOTS lacked the (jedi_order, coruscant) entry
  - So `_entry_room_for_faction("jedi_order") -> None`, and
    `_faction_quarters_locatable("jedi_order") -> False`
  - Net effect: Jedi PC promotion silently no-op'd on quarter assignment

F.5d wires `("jedi_order", "coruscant"): 211` (Jedi Temple — Entrance
Hall) into FACTION_QUARTER_LOTS. This file proves the end-to-end path
works for all four Jedi rank tiers.

Test sections:
  1. TestFactionQuarterLotsHasJediEntry  — dict-level assertion
  2. TestJediQuartersLocatable           — _faction_quarters_locatable
  3. TestJediTemplateLadderTiers         — _best_tier_for_rank coverage
  4. TestAssignFactionQuartersForJedi    — end-to-end at ranks 0/1/3/5
  5. TestJediIsNotInsurgent              — Jedi quarters don't hide
  6. TestF5dDocstringMarker              — source-level guard

Tests use the AsyncMock DB pattern from test_b1d2.
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
    """Run an async test body. asyncio.run() handles loop lifecycle
    correctly across Python 3.10+ on all platforms (Windows proactor +
    POSIX). Mirrors the F.5b.2.x / b1d2 helper."""
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# Mock DB — extends the test_b1d2 pattern with the Jedi Temple anchor
# ──────────────────────────────────────────────────────────────────────

def _mock_db_for_jedi_assign():
    """Mock DB pre-loaded with room 211 (Jedi Temple Entrance Hall).

    Mirrors test_b1d2_housing_codeflow_era_aware._mock_db_for_assign
    but adds the CW Jedi anchor room. Records:
      - db._created_rooms: list of dicts passed to create_room
      - db._created_exits: list of {from, to, direction, name} dicts
      - db._exec_calls:    list of (sql, params) tuples
      - db._character_updates: list of save_character kwargs
    """
    db = MagicMock()
    db._created_rooms = []
    db._created_exits = []
    db._exec_calls = []
    db._commits = 0
    db._inserted_housing_id = 4242
    db._character_updates = []

    # Room 211 — Jedi Temple Entrance Hall, "secured" zone (Temple
    # interior is the most secured zone in the Coruscant build).
    # Other GCW rooms included so cross-faction sanity tests can run
    # against the same mock without needing a second factory.
    db._room_table = {
        22:  {"id": 22,  "name": "Tatooine Militia HQ",
              "properties": json.dumps({"security": "secured"})},
        47:  {"id": 47,  "name": "Outskirts Compound",
              "properties": json.dumps({"security": "lawless"})},
        69:  {"id": 69,  "name": "Undercity Warrens",
              "properties": json.dumps({"security": "lawless"})},
        211: {"id": 211, "name": "Jedi Temple - Entrance Hall",
              "properties": json.dumps({"security": "secured"})},
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
        cur = MagicMock()
        cur.lastrowid = db._inserted_housing_id
        return cur

    async def _fetchall(sql, params=None):
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
        return None

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


def _make_char(faction_code, char_id=100, name="TestPC"):
    return {"id": char_id, "name": name,
            "faction_id": faction_code, "account_id": 1}


# ──────────────────────────────────────────────────────────────────────
# 1. FACTION_QUARTER_LOTS dict-level assertion
# ──────────────────────────────────────────────────────────────────────

class TestFactionQuarterLotsHasJediEntry(unittest.TestCase):
    """The (jedi_order, coruscant) -> 211 entry exists in
    FACTION_QUARTER_LOTS — F.5d's one-line dict change."""

    def test_jedi_order_coruscant_entry_exists(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertIn(("jedi_order", "coruscant"), FACTION_QUARTER_LOTS,
                      "F.5d should add the jedi_order anchor to "
                      "FACTION_QUARTER_LOTS")

    def test_jedi_order_anchors_to_room_211(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertEqual(
            FACTION_QUARTER_LOTS[("jedi_order", "coruscant")],
            211,
            "Jedi anchor should be room 211 (jedi_temple_entrance_hall) "
            "— NOT 210 (main gate, public concourse)",
        )

    def test_existing_gcw_entries_unchanged(self):
        """F.5d is purely additive — it must not touch the GCW entries."""
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertEqual(FACTION_QUARTER_LOTS[("empire", "tatooine")], 22)
        self.assertEqual(FACTION_QUARTER_LOTS[("empire", "corellia")], 107)
        self.assertEqual(FACTION_QUARTER_LOTS[("rebel", "tatooine")], 47)
        self.assertEqual(FACTION_QUARTER_LOTS[("rebel", "nar_shaddaa")], 69)
        self.assertEqual(FACTION_QUARTER_LOTS[("hutt", "tatooine")], 19)
        self.assertEqual(FACTION_QUARTER_LOTS[("hutt", "nar_shaddaa")], 72)


# ──────────────────────────────────────────────────────────────────────
# 2. _faction_quarters_locatable for jedi_order
# ──────────────────────────────────────────────────────────────────────

class TestJediQuartersLocatable(unittest.TestCase):
    """Pre-F.5d this returned False, hitting the 'era rooms not built
    yet' soft-log path. Post-F.5d it returns True."""

    def test_jedi_quarters_locatable_post_f5d(self):
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(
            _faction_quarters_locatable("jedi_order"),
            "Post-F.5d, jedi_order should be locatable: home planet "
            "(coruscant) and quarter-lots entry (211) are both set",
        )

    def test_entry_room_for_jedi_resolves(self):
        from engine.housing import _entry_room_for_faction
        self.assertEqual(
            _entry_room_for_faction("jedi_order"),
            211,
            "_entry_room_for_faction('jedi_order') should resolve to 211",
        )

    def test_remaining_cw_factions_still_unlocatable(self):
        """── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────

        Originally F.5d's scope-guard test, asserting republic/cis/
        hutt_cartel were intentionally NOT covered by F.5d. B.1.d.3
        closed that wider gap, so this assertion is no longer correct.

        Real coverage of all four CW factions being locatable is in:
          tests/test_b1d3_cw_faction_anchors_wired.py
            ::TestCWFactionsLocatable

        This stub remains as a tombstone so the F.5d-era scope
        intent is documented at the original line number for any
        handoff doc or code review that cites it.
        """
        self.skipTest("B.1.d.3 closed this gap — see test_b1d3_cw_faction_anchors_wired")


# ──────────────────────────────────────────────────────────────────────
# 3. _best_tier_for_rank — Jedi ladder coverage at each canonical rank
# ──────────────────────────────────────────────────────────────────────

class TestJediTempleLadderTiers(unittest.TestCase):
    """The architecture v38 §19.3 specifies F.5d as 'Jedi PC at rank
    0/1/3/5 sees right quarters'. These four ranks correspond to the
    four entries authored in housing_lots.yaml's jedi_order ladder:
    Initiate (0) / Padawan (1) / Knight (3) / Master (5).

    Note: ranks 2 and 4 are NOT canonical Jedi ranks. _best_tier_for_rank
    correctly resolves intermediate ranks to the highest-eligible tier:
    rank 2 → Padawan (the rank-1 entry); rank 4 → Knight (rank-3 entry).
    """

    def test_rank_0_resolves_to_initiate(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("jedi_order", 0)
        self.assertIsNotNone(cfg, "Rank 0 should resolve to a tier")
        self.assertIn("Initiate", cfg["label"],
                      "Rank 0 = Initiate Cluster")

    def test_rank_1_resolves_to_padawan(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("jedi_order", 1)
        self.assertIsNotNone(cfg, "Rank 1 should resolve to a tier")
        self.assertIn("Padawan", cfg["label"],
                      "Rank 1 = Padawan Cell")

    def test_rank_3_resolves_to_knight(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("jedi_order", 3)
        self.assertIsNotNone(cfg, "Rank 3 should resolve to a tier")
        self.assertIn("Knight", cfg["label"],
                      "Rank 3 = Knight Quarters")

    def test_rank_5_resolves_to_master(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("jedi_order", 5)
        self.assertIsNotNone(cfg, "Rank 5 should resolve to a tier")
        self.assertIn("Master", cfg["label"],
                      "Rank 5 = Master Suite")

    def test_intermediate_ranks_resolve_to_highest_eligible(self):
        """Rank 2 → Padawan tier (rank-1 entry, since rank-3 not yet met).
        Rank 4 → Knight tier (rank-3 entry, since rank-5 not yet met)."""
        from engine.housing import _best_tier_for_rank
        cfg2 = _best_tier_for_rank("jedi_order", 2)
        self.assertIn("Padawan", cfg2["label"])
        cfg4 = _best_tier_for_rank("jedi_order", 4)
        self.assertIn("Knight", cfg4["label"])

    def test_storage_max_increases_with_rank(self):
        """Sanity: storage_max should be monotonically non-decreasing
        across the 4 canonical Jedi ranks. From the YAML: 10/30/80/100."""
        from engine.housing import _best_tier_for_rank
        s0 = _best_tier_for_rank("jedi_order", 0)["storage_max"]
        s1 = _best_tier_for_rank("jedi_order", 1)["storage_max"]
        s3 = _best_tier_for_rank("jedi_order", 3)["storage_max"]
        s5 = _best_tier_for_rank("jedi_order", 5)["storage_max"]
        self.assertEqual(s0, 10)
        self.assertEqual(s1, 30)
        self.assertEqual(s3, 80)
        self.assertEqual(s5, 100)
        self.assertLess(s0, s1)
        self.assertLess(s1, s3)
        self.assertLess(s3, s5)


# ──────────────────────────────────────────────────────────────────────
# 4. assign_faction_quarters end-to-end at ranks 0/1/3/5
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersForJedi(unittest.TestCase):
    """The headline F.5d test: Jedi PC at each canonical rank actually
    creates a real room, real exit, and real player_housing record.

    Pre-F.5d: assign_faction_quarters('jedi_order', any_rank) bailed at
    line 1602 via the soft-log branch because _entry_room_for_faction
    returned None. The mock would record zero created_rooms.

    Post-F.5d: each rank produces exactly one new room with the
    appropriate Jedi-tier name, anchored to room 211."""

    def test_rank_0_initiate_creates_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Anakin")
        result = _run(assign_faction_quarters(db, char, "jedi_order", 0,
                                              session=sess))
        self.assertIsNotNone(result, "Rank 0 should produce a result")
        self.assertEqual(len(db._created_rooms), 1,
                         "Exactly one room should be created")
        self.assertIn("Initiate", db._created_rooms[0]["name"])
        self.assertIn("Anakin", db._created_rooms[0]["name"])

    def test_rank_1_padawan_creates_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Ahsoka")
        result = _run(assign_faction_quarters(db, char, "jedi_order", 1,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        self.assertIn("Padawan", db._created_rooms[0]["name"])
        self.assertIn("Ahsoka", db._created_rooms[0]["name"])

    def test_rank_3_knight_creates_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Kenobi")
        result = _run(assign_faction_quarters(db, char, "jedi_order", 3,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        self.assertIn("Knight", db._created_rooms[0]["name"])
        self.assertIn("Kenobi", db._created_rooms[0]["name"])

    def test_rank_5_master_creates_quarters(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Yoda")
        result = _run(assign_faction_quarters(db, char, "jedi_order", 5,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        self.assertIn("Master", db._created_rooms[0]["name"])
        self.assertIn("Yoda", db._created_rooms[0]["name"])

    def test_rank_5_quarters_anchored_to_room_211(self):
        """Verify the new room's exit comes FROM room 211 (Entrance Hall)."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Windu")
        _run(assign_faction_quarters(db, char, "jedi_order", 5,
                                     session=sess))
        # At least one exit should be created from 211 to the new room
        from_211_exits = [e for e in db._created_exits if e["from"] == 211]
        self.assertGreaterEqual(
            len(from_211_exits), 1,
            "An exit should be created FROM the Jedi Temple "
            "Entrance Hall (room 211) into the new quarters",
        )

    def test_rank_5_player_housing_insert_fires(self):
        """End-to-end sanity: the SQL INSERT INTO player_housing
        actually runs, meaning the assignment was persisted."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order", name="Yoda")
        _run(assign_faction_quarters(db, char, "jedi_order", 5,
                                     session=sess))
        sql_calls = [c[0] for c in db._exec_calls]
        self.assertTrue(
            any("INSERT INTO player_housing" in s for s in sql_calls),
            "player_housing INSERT should fire end-to-end",
        )

    def test_rank_5_storage_max_persisted_correctly(self):
        """Master suite YAML says storage_max=100. The INSERT params
        should reflect that."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order")
        _run(assign_faction_quarters(db, char, "jedi_order", 5,
                                     session=sess))
        # Find the player_housing INSERT and check storage_max in params
        ph_inserts = [c for c in db._exec_calls
                      if "INSERT INTO player_housing" in c[0]]
        self.assertEqual(len(ph_inserts), 1)
        params = ph_inserts[0][1]
        # storage_max=100 should appear somewhere in the params
        self.assertIn(
            100, params,
            "Master suite storage_max=100 should be persisted",
        )

    def test_below_min_rank_returns_none(self):
        """Negative rank shouldn't crash — it should just bail
        cleanly before creating anything."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order")
        result = _run(assign_faction_quarters(db, char, "jedi_order", -1,
                                              session=sess))
        self.assertIsNone(result)
        self.assertEqual(len(db._created_rooms), 0)


# ──────────────────────────────────────────────────────────────────────
# 5. Jedi quarters are NOT insurgent (no exit hiding)
# ──────────────────────────────────────────────────────────────────────

class TestJediIsNotInsurgent(unittest.TestCase):
    """The Jedi Order is the lawful-state magic-cop arm of the Republic
    in the Clone Wars era. Their quarters are part of a public-facing
    Temple, not safehouses. Promotion should NOT trigger the
    hidden_faction UPDATE that rebel/cis quarters do."""

    def test_jedi_not_in_insurgent_factions_set(self):
        from engine.housing import INSURGENT_FACTIONS, is_insurgent_faction
        self.assertNotIn("jedi_order", INSURGENT_FACTIONS)
        self.assertFalse(is_insurgent_faction("jedi_order"))

    def test_rank_5_no_hidden_faction_sql(self):
        """End-to-end: a Jedi Master assignment should not fire the
        hidden_faction UPDATE that an insurgent assignment would."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_jedi_assign()
        sess = _mock_session()
        char = _make_char("jedi_order")
        _run(assign_faction_quarters(db, char, "jedi_order", 5,
                                     session=sess))
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(
            hidden_calls, [],
            "Jedi quarters must not hide their entry exit — the Temple "
            "is a public lawful-state institution, not an insurgent "
            "safehouse",
        )


# ──────────────────────────────────────────────────────────────────────
# 6. Source-level guard — the F.5d marker comment exists
# ──────────────────────────────────────────────────────────────────────

class TestF5dDocstringMarker(unittest.TestCase):
    """Source-level guard: the F.5d rationale comment block must remain
    in engine/housing.py near FACTION_QUARTER_LOTS. Pattern borrowed
    from F.5b.3.c source-cleanup tests — protects the design intent
    against accidental reverts that revert behavior but leave the
    runtime tests passing."""

    def test_f5d_comment_block_present(self):
        from engine import housing
        with open(housing.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            "F.5d (Apr 30 2026)",
            src,
            "engine/housing.py should contain the F.5d marker "
            "comment near FACTION_QUARTER_LOTS",
        )

    def test_f5d_documents_room_211_choice(self):
        """The comment block must explain WHY room 211 (not 210)."""
        from engine import housing
        with open(housing.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("211", src)
        self.assertIn("jedi_temple_entrance_hall", src)

    def test_f5d_flags_wider_gap(self):
        """── B.1.d.3 (Apr 30 2026): MIGRATED ─────────────────────────────

        Originally asserted the F.5d comment block carried a "WIDER GAP
        NOT CLOSED BY F.5d" flag for the missing republic/cis/
        hutt_cartel anchors. B.1.d.3 closed that gap and retired the
        note in housing.py, so this assertion is obsolete.

        Real coverage of the new B.1.d.3 anchors and their rationale
        is in:
          tests/test_b1d3_cw_faction_anchors_wired.py
            ::TestB1d3DocstringMarker
        """
        self.skipTest("B.1.d.3 retired the WIDER GAP note — see test_b1d3_cw_faction_anchors_wired")


if __name__ == "__main__":
    unittest.main()
