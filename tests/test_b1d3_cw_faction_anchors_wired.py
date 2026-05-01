# -*- coding: utf-8 -*-
"""
tests/test_b1d3_cw_faction_anchors_wired.py — B.1.d.3 integration tests.

B.1.d.3 (Apr 30 2026) closes the wider CW faction-quarters gap that
F.5d explicitly flagged. Pre-B.1.d.3 state (post-F.5d):

  - jedi_order: locatable, real assignment (F.5d wired it)
  - republic:   home_planet=coruscant, ladder loaded, but no anchor —
                _faction_quarters_locatable returned False
  - cis:        home_planet=geonosis, ladder loaded, but no anchor
  - hutt_cartel: home_planet=nar_shaddaa, ladder loaded, but no anchor

B.1.d.3 wires:
  - ("republic",    "coruscant"):    259  (Coco Town - Civic Block)
  - ("cis",         "geonosis"):     418  (Geonosis - Deep Hive Tunnel)
  - ("hutt_cartel", "nar_shaddaa"):   71  (Hutt Emissary Tower - Audience Chamber)

After B.1.d.3, all four CW factions have working faction quarters
end-to-end through assign_faction_quarters.

Test sections:
  1. TestFactionQuarterLotsHasCWAnchors    — dict-level
  2. TestCWFactionsLocatable              — _faction_quarters_locatable
  3. TestCWFactionLadderTiers             — _best_tier_for_rank coverage
  4. TestAssignFactionQuartersForRepublic — end-to-end at canonical ranks
  5. TestAssignFactionQuartersForCIS      — end-to-end + insurgent hiding
  6. TestAssignFactionQuartersForHuttCartel — end-to-end (non-insurgent)
  7. TestB1d3DocstringMarker              — source-level guard

Tests use the AsyncMock DB pattern from test_f5d_jedi_temple_integration.
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
    correctly across Python 3.10+ on all platforms."""
    return asyncio.run(coro)


# ──────────────────────────────────────────────────────────────────────
# Mock DB — pre-loaded with all three new CW anchor rooms
# ──────────────────────────────────────────────────────────────────────

def _mock_db_for_cw_assign():
    """Mock DB pre-loaded with rooms 259/418/71 (the three B.1.d.3
    CW anchors) plus 211 (the F.5d jedi_order anchor) and the GCW
    rooms used by other test classes that share this fixture pattern.

    Mirrors test_f5d_jedi_temple_integration._mock_db_for_jedi_assign.
    """
    db = MagicMock()
    db._created_rooms = []
    db._created_exits = []
    db._exec_calls = []
    db._commits = 0
    db._inserted_housing_id = 4242
    db._character_updates = []

    # Each anchor room has a security level chosen to match the YAML
    # ladder narrative:
    #   - 259 (Coco Town Civic Block): "contested" — Coco Town is
    #     mid-levels, mixed-security; the Republic chapter house is
    #     a secured pocket within it, but the entry-room itself is
    #     the public civic block.
    #   - 418 (Geonosis Deep Hive Tunnel): "secured" — deep hive,
    #     Geonosian sentinels, restricted access.
    #   - 71 (Hutt Emissary Tower Audience): "contested" — mirrors
    #     the GCW Jabba's Townhouse (room 19) "contested" pattern.
    db._room_table = {
        # GCW
        22:  {"id": 22,  "name": "Tatooine Militia HQ",
              "properties": json.dumps({"security": "secured"})},
        47:  {"id": 47,  "name": "Outskirts Compound",
              "properties": json.dumps({"security": "lawless"})},
        69:  {"id": 69,  "name": "Undercity Warrens",
              "properties": json.dumps({"security": "lawless"})},
        # F.5d
        211: {"id": 211, "name": "Jedi Temple - Entrance Hall",
              "properties": json.dumps({"security": "secured"})},
        # B.1.d.3 — three new anchors
        259: {"id": 259, "name": "Coruscant - Coco Town - Civic Block",
              "properties": json.dumps({"security": "contested"})},
        418: {"id": 418, "name": "Geonosis - Deep Hive Tunnel",
              "properties": json.dumps({"security": "secured"})},
        71:  {"id": 71,  "name": "Nar Shaddaa - Hutt Emissary Tower - "
                                 "Audience Chamber",
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
# 1. FACTION_QUARTER_LOTS dict-level assertions
# ──────────────────────────────────────────────────────────────────────

class TestFactionQuarterLotsHasCWAnchors(unittest.TestCase):
    """The three B.1.d.3 entries exist with the chosen room IDs."""

    def test_republic_coruscant_anchor(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertIn(("republic", "coruscant"), FACTION_QUARTER_LOTS)
        self.assertEqual(FACTION_QUARTER_LOTS[("republic", "coruscant")],
                         259, "Republic anchor should be room 259 "
                         "(coco_town_civic_block)")

    def test_cis_geonosis_anchor(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertIn(("cis", "geonosis"), FACTION_QUARTER_LOTS)
        self.assertEqual(FACTION_QUARTER_LOTS[("cis", "geonosis")],
                         418, "CIS anchor should be room 418 "
                         "(geonosis_deep_tunnel)")

    def test_hutt_cartel_nar_shaddaa_anchor(self):
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertIn(("hutt_cartel", "nar_shaddaa"), FACTION_QUARTER_LOTS)
        self.assertEqual(FACTION_QUARTER_LOTS[("hutt_cartel", "nar_shaddaa")],
                         71, "Hutt Cartel anchor should be room 71 "
                         "(hutt_emissary_tower_audience)")

    def test_existing_entries_unchanged(self):
        """B.1.d.3 is purely additive — F.5d + GCW entries unchanged."""
        from engine.housing import FACTION_QUARTER_LOTS
        # GCW
        self.assertEqual(FACTION_QUARTER_LOTS[("empire", "tatooine")], 22)
        self.assertEqual(FACTION_QUARTER_LOTS[("empire", "corellia")], 107)
        self.assertEqual(FACTION_QUARTER_LOTS[("rebel", "tatooine")], 47)
        self.assertEqual(FACTION_QUARTER_LOTS[("rebel", "nar_shaddaa")], 69)
        self.assertEqual(FACTION_QUARTER_LOTS[("hutt", "tatooine")], 19)
        self.assertEqual(FACTION_QUARTER_LOTS[("hutt", "nar_shaddaa")], 72)
        # F.5d
        self.assertEqual(FACTION_QUARTER_LOTS[("jedi_order", "coruscant")],
                         211)

    def test_dict_size_after_b1d3(self):
        """6 GCW + 1 F.5d + 3 B.1.d.3 = 10 entries."""
        from engine.housing import FACTION_QUARTER_LOTS
        self.assertEqual(
            len(FACTION_QUARTER_LOTS), 10,
            "Post-B.1.d.3 FACTION_QUARTER_LOTS should have exactly "
            "10 entries (6 GCW + 1 F.5d jedi + 3 B.1.d.3 CW)",
        )


# ──────────────────────────────────────────────────────────────────────
# 2. _faction_quarters_locatable for all three CW factions
# ──────────────────────────────────────────────────────────────────────

class TestCWFactionsLocatable(unittest.TestCase):
    """Pre-B.1.d.3 these returned False; post-B.1.d.3 all return True."""

    def test_republic_locatable(self):
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("republic"))

    def test_cis_locatable(self):
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("cis"))

    def test_hutt_cartel_locatable(self):
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("hutt_cartel"))

    def test_jedi_order_still_locatable(self):
        """Sanity: F.5d's locatable result still holds post-B.1.d.3."""
        from engine.housing import _faction_quarters_locatable
        self.assertTrue(_faction_quarters_locatable("jedi_order"))

    def test_entry_rooms_resolve(self):
        from engine.housing import _entry_room_for_faction
        self.assertEqual(_entry_room_for_faction("republic"), 259)
        self.assertEqual(_entry_room_for_faction("cis"), 418)
        self.assertEqual(_entry_room_for_faction("hutt_cartel"), 71)

    def test_bhg_still_unlocatable(self):
        """BHG has no faction quarters per cw_housing_design_v1.md §5.5
        — explicitly null in housing_lots.yaml. Should remain
        unlocatable post-B.1.d.3."""
        from engine.housing import _faction_quarters_locatable
        self.assertFalse(_faction_quarters_locatable("bounty_hunters_guild"))


# ──────────────────────────────────────────────────────────────────────
# 3. _best_tier_for_rank — ladder coverage at canonical ranks
# ──────────────────────────────────────────────────────────────────────

class TestCWFactionLadderTiers(unittest.TestCase):
    """Each CW faction's ladder resolves correctly at its canonical
    ranks. Ranks taken from data/worlds/clone_wars/housing_lots.yaml."""

    # Republic: ranks 0/2/4/5
    def test_republic_rank_0_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("republic", 0)
        self.assertIsNotNone(cfg)
        self.assertIn("Bunk", cfg["label"])  # Republic Guard - Shared Bunk

    def test_republic_rank_5_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("republic", 5)
        self.assertIsNotNone(cfg)
        self.assertIn("Commander", cfg["label"])

    # CIS: ranks 0/2/4/5
    def test_cis_rank_0_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("cis", 0)
        self.assertIsNotNone(cfg)
        # First CIS tier is the spartan dormitory in Stalgasin Hive
        self.assertIn("Hive", cfg["label"])

    def test_cis_rank_5_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("cis", 5)
        self.assertIsNotNone(cfg)
        self.assertIn("Council", cfg["label"])

    # Hutt Cartel: ranks 2/3/5 — note the ladder STARTS at rank 2,
    # there's no rank-0 entry. This is intentional per the YAML
    # (you don't get cartel housing as a fresh recruit).
    def test_hutt_cartel_rank_0_returns_none(self):
        from engine.housing import _best_tier_for_rank
        # No rank-0 hutt_cartel tier — returns None.
        cfg = _best_tier_for_rank("hutt_cartel", 0)
        self.assertIsNone(
            cfg,
            "Hutt Cartel ladder starts at rank 2; rank 0 should be None",
        )

    def test_hutt_cartel_rank_2_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("hutt_cartel", 2)
        self.assertIsNotNone(cfg)
        self.assertIn("Enforcer", cfg["label"])

    def test_hutt_cartel_rank_5_resolves(self):
        from engine.housing import _best_tier_for_rank
        cfg = _best_tier_for_rank("hutt_cartel", 5)
        self.assertIsNotNone(cfg)
        self.assertIn("Vigo", cfg["label"])


# ──────────────────────────────────────────────────────────────────────
# 4. assign_faction_quarters end-to-end — Republic
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersForRepublic(unittest.TestCase):
    """Republic PCs at rank 0 (Bunk) and rank 5 (Commander) get real
    quarters anchored to room 259."""

    def test_rank_0_creates_bunk(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("republic", name="Rex")
        result = _run(assign_faction_quarters(db, char, "republic", 0,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        # YAML room_name template: "{name}'s Bunk"
        self.assertIn("Bunk", db._created_rooms[0]["name"])
        self.assertIn("Rex", db._created_rooms[0]["name"])

    def test_rank_5_creates_commander_compound(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("republic", name="Cody")
        result = _run(assign_faction_quarters(db, char, "republic", 5,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        self.assertIn("Commander", db._created_rooms[0]["name"])
        self.assertIn("Cody", db._created_rooms[0]["name"])

    def test_rank_5_anchored_to_room_259(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("republic")
        _run(assign_faction_quarters(db, char, "republic", 5,
                                     session=sess))
        from_259 = [e for e in db._created_exits if e["from"] == 259]
        self.assertGreaterEqual(
            len(from_259), 1,
            "Republic Commander quarters should anchor to room 259 "
            "(Coco Town Civic Block)",
        )

    def test_republic_not_insurgent(self):
        """Republic is the lawful state — no exit hiding."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("republic")
        _run(assign_faction_quarters(db, char, "republic", 5,
                                     session=sess))
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(
            hidden_calls, [],
            "Republic quarters must not hide entry exit",
        )


# ──────────────────────────────────────────────────────────────────────
# 5. assign_faction_quarters end-to-end — CIS (insurgent)
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersForCIS(unittest.TestCase):
    """CIS is the era's insurgent challenger (per
    INSURGENT_FACTIONS = {'rebel', 'cis'}). Their quarter exits get
    hidden_faction='cis' so they're invisible to Republic PCs."""

    def test_rank_0_creates_dormitory(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("cis", name="Dooku")
        result = _run(assign_faction_quarters(db, char, "cis", 0,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)

    def test_rank_5_creates_council_suite(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("cis", name="Ventress")
        result = _run(assign_faction_quarters(db, char, "cis", 5,
                                              session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        # YAML room_name template: "Marshal {name}'s Suite"
        self.assertIn("Marshal", db._created_rooms[0]["name"])
        self.assertIn("Ventress", db._created_rooms[0]["name"])

    def test_rank_5_anchored_to_room_418(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("cis")
        _run(assign_faction_quarters(db, char, "cis", 5, session=sess))
        from_418 = [e for e in db._created_exits if e["from"] == 418]
        self.assertGreaterEqual(
            len(from_418), 1,
            "CIS Council Suite should anchor to room 418 "
            "(Geonosis Deep Hive Tunnel)",
        )

    def test_cis_is_insurgent_quarters_hide_exit(self):
        """The B.1.d.2 INSURGENT_FACTIONS generalization should fire
        for CIS — entry exit gets hidden_faction='cis'."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("cis")
        _run(assign_faction_quarters(db, char, "cis", 5, session=sess))
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(
            len(hidden_calls), 1,
            "CIS quarters MUST hide the entry exit (insurgent faction)",
        )
        sql, params = hidden_calls[0]
        self.assertEqual(
            params[0], "cis",
            "hidden_faction value should be the literal 'cis'",
        )


# ──────────────────────────────────────────────────────────────────────
# 6. assign_faction_quarters end-to-end — Hutt Cartel (non-insurgent)
# ──────────────────────────────────────────────────────────────────────

class TestAssignFactionQuartersForHuttCartel(unittest.TestCase):
    """Hutt Cartel is independent-criminal — overt enough to not need
    exit hiding (mirrors the GCW hutt pattern)."""

    def test_rank_0_returns_none(self):
        """Hutt Cartel ladder starts at rank 2 — rank 0 should bail."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel")
        result = _run(assign_faction_quarters(db, char, "hutt_cartel",
                                              0, session=sess))
        self.assertIsNone(result)
        self.assertEqual(len(db._created_rooms), 0)

    def test_rank_2_creates_enforcer_safehouse(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel", name="Bossk")
        result = _run(assign_faction_quarters(db, char, "hutt_cartel",
                                              2, session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        self.assertIn("Enforcer", db._created_rooms[0]["name"])

    def test_rank_5_creates_vigo_penthouse(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel", name="Jabba")
        result = _run(assign_faction_quarters(db, char, "hutt_cartel",
                                              5, session=sess))
        self.assertIsNotNone(result)
        self.assertEqual(len(db._created_rooms), 1)
        # YAML room_name template: "Vigo {name}'s Penthouse"
        self.assertIn("Vigo", db._created_rooms[0]["name"])
        self.assertIn("Jabba", db._created_rooms[0]["name"])

    def test_rank_5_anchored_to_room_71(self):
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel")
        _run(assign_faction_quarters(db, char, "hutt_cartel", 5,
                                     session=sess))
        from_71 = [e for e in db._created_exits if e["from"] == 71]
        self.assertGreaterEqual(
            len(from_71), 1,
            "Hutt Vigo Penthouse should anchor to room 71 "
            "(Hutt Emissary Tower Audience Chamber)",
        )

    def test_hutt_cartel_not_insurgent(self):
        """Mirrors GCW hutt — independent-criminal, not insurgent.
        No exit hiding."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel")
        _run(assign_faction_quarters(db, char, "hutt_cartel", 5,
                                     session=sess))
        hidden_calls = [c for c in db._exec_calls
                        if "hidden_faction" in c[0]]
        self.assertEqual(
            hidden_calls, [],
            "Hutt Cartel quarters must NOT hide entry exit "
            "(non-insurgent — mirrors GCW hutt pattern)",
        )

    def test_rank_5_storage_max_persisted(self):
        """YAML says Vigo Penthouse storage_max=100."""
        from engine.housing import assign_faction_quarters
        db = _mock_db_for_cw_assign()
        sess = _mock_session()
        char = _make_char("hutt_cartel")
        _run(assign_faction_quarters(db, char, "hutt_cartel", 5,
                                     session=sess))
        ph_inserts = [c for c in db._exec_calls
                      if "INSERT INTO player_housing" in c[0]]
        self.assertEqual(len(ph_inserts), 1)
        params = ph_inserts[0][1]
        self.assertIn(100, params,
                      "Vigo Penthouse storage_max=100 should persist")


# ──────────────────────────────────────────────────────────────────────
# 7. Source-level guard — B.1.d.3 marker comment
# ──────────────────────────────────────────────────────────────────────

class TestB1d3DocstringMarker(unittest.TestCase):
    """Source-level guard mirroring F.5d's pattern. Protects design
    intent against accidental reverts."""

    def test_b1d3_comment_block_present(self):
        from engine import housing
        with open(housing.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            "B.1.d.3 (Apr 30 2026)", src,
            "engine/housing.py should contain the B.1.d.3 marker "
            "comment near FACTION_QUARTER_LOTS",
        )

    def test_b1d3_documents_each_anchor_choice(self):
        """The comment block should explain WHY each room was chosen."""
        from engine import housing
        with open(housing.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        # All three slugs and IDs should be mentioned in the rationale
        self.assertIn("coco_town_civic_block", src)
        self.assertIn("259", src)
        self.assertIn("geonosis_deep_tunnel", src)
        self.assertIn("418", src)
        self.assertIn("hutt_emissary_tower_audience", src)
        # Room 71 might appear in multiple places; check it's at least
        # in the comment that mentions hutt_emissary_tower_audience.

    def test_f5d_wider_gap_note_retired(self):
        """The F.5d 'WIDER GAP NOT CLOSED' block should be removed
        (or rephrased) post-B.1.d.3 — the gap IS closed now. If the
        block survives verbatim, we have a stale comment.

        Note: the literal phrase "WIDER GAP" might still appear if a
        future drop reuses the convention. For now it's a quick
        check that the F.5d-specific block is gone."""
        from engine import housing
        with open(housing.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        # The exact F.5d phrase that named the gap should no longer
        # be present — B.1.d.3 closed it.
        self.assertNotIn(
            "WIDER GAP NOT CLOSED BY F.5d", src,
            "The F.5d 'WIDER GAP NOT CLOSED' note should be retired "
            "by B.1.d.3 — that gap is closed now",
        )


if __name__ == "__main__":
    unittest.main()
