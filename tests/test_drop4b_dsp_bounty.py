# -*- coding: utf-8 -*-
"""
tests/test_drop4b_dsp_bounty.py — Drop 4b (2026-06-04)

Dark-Side Notoriety — the auto-DSP bounty (Part V / Drop 4 decision (c)).

A high-DSP character automatically draws a bounty. The "wanted" state is
DERIVED from dark_side_points (no new table, no AI cost), FACTION-AGNOSTIC
(it tracks the dark side, not any player faction), and the reward is
STATUS / PRESTIGE only — it never touches the credit / insurance / claim
flow of the pc_bounties system.

This drop ships the trigger + the BH-board surface. The roaming-hunter NPC,
the reward-on-kill loop, and the communal-rally villain are tracked as
follow-on design (see the handoff).

Engine helpers are pure/deterministic; the query method is tested against a
recording stand-in; the parser crossing-notice and board surface are driven
through the real command paths with fakes.
"""
import asyncio
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import bounty_board as bb  # noqa: E402
from engine.force_powers import POWERS, ForcePowerResult  # noqa: E402
import parser.force_commands as fc  # noqa: E402
import parser.pc_bounty_commands as pbc  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


# ══════════════════════════════════════════════════════════════════════════
# ENGINE — DSP notoriety helpers
# ══════════════════════════════════════════════════════════════════════════

class TestDspNotorietyEngine(unittest.TestCase):
    def test_threshold_and_wanted(self):
        self.assertEqual(bb.DSP_BOUNTY_THRESHOLD, 4)
        self.assertFalse(bb.is_dsp_wanted(3))
        self.assertTrue(bb.is_dsp_wanted(4))
        self.assertTrue(bb.is_dsp_wanted(9))

    def test_crossing_fires_once(self):
        self.assertTrue(bb.crossed_into_wanted(3, 4))   # crosses
        self.assertTrue(bb.crossed_into_wanted(0, 6))   # leaps past
        self.assertFalse(bb.crossed_into_wanted(4, 5))  # already wanted
        self.assertFalse(bb.crossed_into_wanted(1, 3))  # still below
        self.assertFalse(bb.crossed_into_wanted(5, 4))  # not increasing into

    def test_tiers(self):
        self.assertEqual(bb.dsp_bounty_tier(4), "Marked")
        self.assertEqual(bb.dsp_bounty_tier(5), "Marked")
        self.assertEqual(bb.dsp_bounty_tier(6), "Hunted")
        self.assertEqual(bb.dsp_bounty_tier(9), "Darkest of the Dark")

    def test_section_filters_and_sorts(self):
        rows = [
            {"name": "Low", "dark_side_points": 1},      # excluded
            {"name": "Mid", "dark_side_points": 4},      # Marked
            {"name": "High", "dark_side_points": 9},     # top
        ]
        lines = bb.format_dsp_notoriety_section(rows)
        self.assertTrue(lines, "section should render for wanted chars")
        body = "\n".join(lines)
        self.assertIn("Dark-Side Notoriety", body)
        self.assertIn("High", body)
        self.assertIn("Mid", body)
        self.assertNotIn("Low", body)
        # High (9) listed before Mid (4).
        self.assertLess(body.index("High"), body.index("Mid"))

    def test_section_empty_when_none_wanted(self):
        self.assertEqual(
            bb.format_dsp_notoriety_section(
                [{"name": "Pure", "dark_side_points": 0}]),
            [])
        self.assertEqual(bb.format_dsp_notoriety_section([]), [])

    def test_reward_is_prestige_not_credits(self):
        line = bb.format_dsp_notoriety_line("Maul", 7)
        self.assertIn("prestige", line.lower())
        self.assertNotIn("cr", line.lower().replace("credits", ""))  # no credit figure


# ══════════════════════════════════════════════════════════════════════════
# DB — get_dsp_wanted_characters (recording stand-in)
# ══════════════════════════════════════════════════════════════════════════

class TestDspWantedQuery(unittest.TestCase):
    def test_query_params_and_dict_rows(self):
        from db.database import Database

        class _FakeConn:
            def __init__(self, rows):
                self._rows = rows
                self.calls = []

            async def execute_fetchall(self, sql, params):
                self.calls.append((sql, params))
                return self._rows

        class _Stub:
            pass

        async def _q():
            s = _Stub()
            s._db = _FakeConn([{"id": 1, "name": "X", "dark_side_points": 7}])
            rows = await Database.get_dsp_wanted_characters(s, 4, 50)
            return s, rows

        s, rows = _run(_q())
        self.assertEqual(rows, [{"id": 1, "name": "X", "dark_side_points": 7}])
        # threshold + limit bound in order; query filters on dark_side_points.
        self.assertEqual(s._db.calls[0][1], (4, 50))
        self.assertIn("dark_side_points", s._db.calls[0][0])


# ══════════════════════════════════════════════════════════════════════════
# PARSER plumbing
# ══════════════════════════════════════════════════════════════════════════

class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.sent = []

    async def send_line(self, line=""):
        self.sent.append(line)


class _FakeSessionMgr:
    def find_by_character(self, char_id):
        return None

    async def broadcast_to_room(self, *a, **k):
        pass


class _FakeDB:
    def __init__(self, pcs=None, npcs=None, wanted=None, pc_bounties=None):
        self._pcs = pcs or []
        self._npcs = npcs or []
        self._wanted = wanted or []
        self._pc_bounties = pc_bounties or []
        self.saves = []

    async def get_characters_in_room(self, room_id, source_char=None):
        return [c for c in self._pcs if c.get("room_id") == room_id]

    async def get_npcs_in_room(self, room_id):
        return [n for n in self._npcs if n.get("room_id") == room_id]

    async def save_character(self, char_id, **fields):
        self.saves.append((char_id, fields))

    async def get_dsp_wanted_characters(self, threshold, limit=50):
        return [w for w in self._wanted
                if int(w.get("dark_side_points", 0)) >= threshold]

    async def list_active_pc_bounties(self, limit=50):
        return list(self._pc_bounties)

    async def get_character(self, cid):
        for c in self._pcs:
            if c.get("id") == cid:
                return c
        return None


def _ctx(session, db):
    from parser.commands import CommandContext
    return CommandContext(session=session, raw_input="x", command="x",
                          args="", args_list=[], db=db,
                          session_mgr=_FakeSessionMgr())


# ══════════════════════════════════════════════════════════════════════════
# PARSER — crossing notice through ForceCommand.execute (resolve patched)
# ══════════════════════════════════════════════════════════════════════════

class TestCrossingNotice(unittest.TestCase):
    def _caster(self, dsp):
        return {"id": 1, "name": "Jedi", "room_id": 10, "wound_level": 0,
                "dark_side_points": dsp,
                "attributes": json.dumps(
                    {"control": "3D", "sense": "3D", "alter": "3D"}),
                "skills": "{}"}

    def _npc(self):
        return {"id": 50, "name": "Mook", "room_id": 10, "species": "Human",
                "char_sheet_json": json.dumps(
                    {"attributes": {"perception": "2D"}})}

    def _run_cast(self, caster, power="dominate_mind", dsp_delta=1):
        sess = _FakeSession(caster)
        db = _FakeDB(pcs=[], npcs=[self._npc()])
        ctx = _ctx(sess, db)
        ctx.args = f"{power} Mook"

        def fake_resolve(power_key, char, skill_reg, target_char=None,
                         extra_diff=0, *, weight_difficulty_mod=0,
                         extra_dsp_on_fail=0, target_is_npc=False):
            char.dark_side_points += dsp_delta  # mimic a dark power's DSP
            kind = "domination" if power_key == "dominate_mind" else "suggestion"
            return ForcePowerResult(power=POWERS[power_key], success=True,
                                    roll=20, difficulty=10, margin=10,
                                    narrative="ok", effect_kind=kind,
                                    dsp_gained=dsp_delta)

        orig = fc.resolve_force_power
        fc.resolve_force_power = fake_resolve
        try:
            _run(fc.ForceCommand().execute(ctx))
        finally:
            fc.resolve_force_power = orig
        return sess

    def test_crossing_fires_notice(self):
        sess = self._run_cast(self._caster(dsp=3))  # 3 -> 4 crosses
        self.assertTrue(any("[BOUNTY]" in s for s in sess.sent),
                        f"expected a bounty notice on crossing; got {sess.sent}")
        self.assertTrue(any("Marked" in s for s in sess.sent))

    def test_no_notice_when_already_wanted(self):
        sess = self._run_cast(self._caster(dsp=4))  # 4 -> 5, not a crossing
        self.assertFalse(any("[BOUNTY]" in s for s in sess.sent),
                         "no crossing notice once already wanted")

    def test_no_notice_when_no_dsp_gain(self):
        # Light power (suggestion) that does not raise DSP -> no crossing.
        sess = self._run_cast(self._caster(dsp=3), power="affect_mind",
                              dsp_delta=0)
        self.assertFalse(any("[BOUNTY]" in s for s in sess.sent))


# ══════════════════════════════════════════════════════════════════════════
# PARSER — BH board surfaces the notoriety section
# ══════════════════════════════════════════════════════════════════════════

class TestBoardSurface(unittest.TestCase):
    def test_board_shows_notoriety_for_bh_member(self):
        char = {"id": 1, "name": "Hunter", "room_id": 10,
                "faction_id": "bounty_hunters_guild"}
        db = _FakeDB(pc_bounties=[],
                     wanted=[{"id": 2, "name": "Vader", "dark_side_points": 8},
                             {"id": 3, "name": "Pure", "dark_side_points": 0}])
        sess = _FakeSession(char)
        ctx = _ctx(sess, db)
        _run(pbc.BountyCommand()._handle_board(ctx, char))
        body = "\n".join(sess.sent)
        self.assertIn("Dark-Side Notoriety", body)
        self.assertIn("Vader", body)
        self.assertNotIn("Pure", body)

    def test_non_bh_member_refused(self):
        char = {"id": 9, "name": "Civilian", "room_id": 10, "faction_id": ""}
        sess = _FakeSession(char)
        ctx = _ctx(sess, _FakeDB())
        _run(pbc.BountyCommand()._handle_board(ctx, char))
        self.assertTrue(any("BH Guild members only" in s for s in sess.sent))


if __name__ == "__main__":
    unittest.main()
