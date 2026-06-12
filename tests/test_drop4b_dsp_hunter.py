# -*- coding: utf-8 -*-
"""
tests/test_drop4b_dsp_hunter.py — Drop 4b (hunter.1): the roaming Dark-Side hunter.

Pins the deterministic pursuit feature that gives the dark path a soft, prestige-
domain consequence: a named non-canon hunter picks up the trail of any character
at/over the DSP wanted threshold and closes in over time, surfaced on the BH
board and as escalating personal warnings — shaken only by atoning (dropping
back under the threshold).

Coverage:
  * Pure engine (engine/dsp_hunter.py): deterministic hunter assignment, the
    era/Q1-clean roster, wanted/clear boundaries, the DSP-tier step, progress
    clamping + monotonicity, stage boundaries, primary-quarry selection, and the
    deterministic flavor (warnings / trail-cold / taunt / board suffix).
  * Persistence (real in-memory Database via initialize(), so migration 41 is
    actually exercised — not just byte-pinned): get / upsert insert+update /
    last_notified-intact-on-None / get_all / clear.
  * The tick (dsp_hunter_tick) against stub DB + sessions: pursuit creation +
    hunter assignment, one-shot stage-change warning (no repeat), an offline
    quarry still advancing silently, and an atoned quarry's pursuit being cleared
    with the trail-cold line.
  * Board integration: the notoriety section annotates each wanted line with its
    live pursuit suffix.
"""

import os
import sys
import asyncio
import unittest

os.environ.setdefault("SW_ERA", "clone_wars")

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import dsp_hunter as H            # noqa: E402
from engine import bounty_board as B          # noqa: E402

# Era tokens that must never appear in a hunter name / flavor string.
_BANNED = ("imperial", "empire", "rebel", "stormtrooper", "tie ", "x-wing")
# Canon surnames we deliberately avoid in the invented roster.
_CANON_SURNAMES = ("vos", "fett", "bane", "vizsla", "wren", "skirata", "windu",
                   "kenobi", "skywalker", "dooku")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ─────────────────────────────────────────────────────────────────────────────
# Pure engine
# ─────────────────────────────────────────────────────────────────────────────
class TestDspHunterEngine(unittest.TestCase):
    def test_threshold_single_sourced(self):
        # The hunter and the board must agree on who is wanted.
        self.assertEqual(H.DSP_BOUNTY_THRESHOLD, B.DSP_BOUNTY_THRESHOLD)

    def test_hunter_for_is_deterministic_and_in_range(self):
        self.assertEqual(H.hunter_for(0), H.HUNTER_ROSTER[0])
        self.assertEqual(H.hunter_for(0), H.hunter_for(0))
        self.assertEqual(H.hunter_for(len(H.HUNTER_ROSTER)), H.HUNTER_ROSTER[0])
        for cid in range(0, 40):
            self.assertIn(H.hunter_for(cid), H.HUNTER_ROSTER)
        # Garbage id falls back, never raises.
        self.assertIn(H.hunter_for(None), H.HUNTER_ROSTER)

    def test_roster_is_era_and_q1_clean(self):
        for nm in H.HUNTER_ROSTER:
            low = nm.lower()
            for tok in _BANNED:
                self.assertNotIn(tok, low, f"banned token {tok!r} in {nm!r}")
            for sn in _CANON_SURNAMES:
                # surname match on a word boundary
                self.assertNotIn(sn, low.split(), f"canon surname {sn!r} in {nm!r}")

    def test_wanted_and_clear_boundaries(self):
        thr = H.DSP_BOUNTY_THRESHOLD
        self.assertFalse(H.is_wanted(thr - 1))
        self.assertTrue(H.is_wanted(thr))
        self.assertTrue(H.should_clear(thr - 1))
        self.assertFalse(H.should_clear(thr))

    def test_step_by_dsp_tier(self):
        self.assertEqual(H.step_for_dsp(4), H._STEP_MARKED)
        self.assertEqual(H.step_for_dsp(5), H._STEP_MARKED)
        self.assertEqual(H.step_for_dsp(6), H._STEP_HUNTED)
        self.assertEqual(H.step_for_dsp(8), H._STEP_HUNTED)
        self.assertEqual(H.step_for_dsp(9), H._STEP_DARKEST)
        self.assertEqual(H.step_for_dsp(99), H._STEP_DARKEST)
        # deeper fall closes faster
        self.assertGreater(H.step_for_dsp(9), H.step_for_dsp(6))
        self.assertGreater(H.step_for_dsp(6), H.step_for_dsp(4))

    def test_advance_progress_clamps_and_advances(self):
        self.assertEqual(H.advance_progress(0, 4), H._STEP_MARKED)
        self.assertEqual(H.advance_progress(H.PROGRESS_MAX - 1, 9), H.PROGRESS_MAX)
        self.assertEqual(H.advance_progress(H.PROGRESS_MAX, 9), H.PROGRESS_MAX)
        self.assertEqual(H.advance_progress(-5, 4), 0)  # step added then floored to 0
        # monotonic non-decreasing
        p = 0
        for _ in range(50):
            np = H.advance_progress(p, 6)
            self.assertGreaterEqual(np, p)
            p = np
        self.assertEqual(p, H.PROGRESS_MAX)

    def test_pursuit_stage_boundaries(self):
        self.assertEqual(H.pursuit_stage(0), H.STAGE_TRACKING)
        self.assertEqual(H.pursuit_stage(H._CLOSING_AT - 1), H.STAGE_TRACKING)
        self.assertEqual(H.pursuit_stage(H._CLOSING_AT), H.STAGE_CLOSING)
        self.assertEqual(H.pursuit_stage(H._IMMINENT_AT - 1), H.STAGE_CLOSING)
        self.assertEqual(H.pursuit_stage(H._IMMINENT_AT), H.STAGE_IMMINENT)
        self.assertEqual(H.pursuit_stage(H._AT_HEELS_AT - 1), H.STAGE_IMMINENT)
        self.assertEqual(H.pursuit_stage(H._AT_HEELS_AT), H.STAGE_AT_HEELS)

    def test_select_primary_quarry(self):
        self.assertIsNone(H.select_primary_quarry([]))
        self.assertIsNone(H.select_primary_quarry(
            [{"id": 1, "dark_side_points": 1}]))  # sub-threshold filtered
        q = H.select_primary_quarry([
            {"id": 2, "dark_side_points": 6},
            {"id": 5, "dark_side_points": 9},
            {"id": 1, "dark_side_points": 9},  # tie with id 5 → lowest id wins
        ])
        self.assertEqual(q["id"], 1)

    def test_warnings_and_flavor_present(self):
        for st in (H.STAGE_TRACKING, H.STAGE_CLOSING, H.STAGE_IMMINENT, H.STAGE_AT_HEELS):
            line = H.warning_for_stage(st, "Varn Kessate")
            self.assertTrue(line and isinstance(line, str))
        self.assertIsNone(H.warning_for_stage("bogus", "Varn Kessate"))
        # named stages mention the hunter
        for st in (H.STAGE_CLOSING, H.STAGE_IMMINENT, H.STAGE_AT_HEELS):
            self.assertIn("Varn Kessate", H.warning_for_stage(st, "Varn Kessate"))
        self.assertIn("Varn Kessate", H.trail_cold_line("Varn Kessate"))
        self.assertIn("Varn Kessate", H.fallback_taunt("Varn Kessate", H.STAGE_AT_HEELS))

    def test_board_suffix_per_stage(self):
        self.assertEqual(H.board_suffix("bogus"), "")
        for st in (H.STAGE_TRACKING, H.STAGE_CLOSING, H.STAGE_IMMINENT, H.STAGE_AT_HEELS):
            self.assertTrue(H.board_suffix(st))


# ─────────────────────────────────────────────────────────────────────────────
# Persistence — real in-memory Database (exercises migration 41)
# ─────────────────────────────────────────────────────────────────────────────
class TestDspHunterPersistence(unittest.TestCase):
    def test_migration_creates_table_and_crud(self):
        async def go():
            from db.database import Database
            db = Database(":memory:")
            await db.connect()
            await db.initialize()  # runs base schema + migrations 1..41

            # Table exists (migration 41 ran).
            rows = await db._db.execute_fetchall(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name='dsp_hunter_pursuit'")
            self.assertTrue(rows, "migration 41 did not create dsp_hunter_pursuit")

            # Empty to start.
            self.assertIsNone(await db.get_dsp_pursuit(7))
            self.assertEqual(await db.get_all_dsp_pursuits(), [])

            # Insert.
            await db.upsert_dsp_pursuit(7, "Varn Kessate", 5, "tracking")
            row = await db.get_dsp_pursuit(7)
            self.assertEqual(row["hunter_name"], "Varn Kessate")
            self.assertEqual(row["progress"], 5)
            self.assertEqual(row["stage"], "tracking")
            self.assertEqual(row["last_notified_stage"] or "", "")

            # Update without last_notified leaves it intact.
            await db.upsert_dsp_pursuit(7, "Varn Kessate", 45, "closing")
            row = await db.get_dsp_pursuit(7)
            self.assertEqual(row["progress"], 45)
            self.assertEqual(row["stage"], "closing")
            self.assertEqual(row["last_notified_stage"] or "", "")

            # Update WITH last_notified writes it.
            await db.upsert_dsp_pursuit(7, "Varn Kessate", 45, "closing",
                                        last_notified_stage="closing")
            row = await db.get_dsp_pursuit(7)
            self.assertEqual(row["last_notified_stage"], "closing")

            # get_all reflects the single row.
            allp = await db.get_all_dsp_pursuits()
            self.assertEqual(len(allp), 1)
            self.assertEqual(allp[0]["char_id"], 7)

            # Clear.
            self.assertTrue(await db.clear_dsp_pursuit(7))
            self.assertIsNone(await db.get_dsp_pursuit(7))
            self.assertFalse(await db.clear_dsp_pursuit(7))  # idempotent

            await db.close()

        _run(go())


# ─────────────────────────────────────────────────────────────────────────────
# Tick orchestration — stub DB + sessions
# ─────────────────────────────────────────────────────────────────────────────
class _StubDB:
    def __init__(self, wanted):
        self._wanted = wanted          # list of {id,name,dark_side_points}
        self.pursuits = {}             # char_id -> row dict

    async def get_dsp_wanted_characters(self, threshold, limit=50):
        return [w for w in self._wanted
                if int(w.get("dark_side_points", 0)) >= int(threshold)]

    async def get_dsp_pursuit(self, cid):
        return dict(self.pursuits[cid]) if cid in self.pursuits else None

    async def get_all_dsp_pursuits(self):
        return [dict(v) for v in self.pursuits.values()]

    async def upsert_dsp_pursuit(self, cid, hunter, progress, stage,
                                 last_notified_stage=None):
        prev = self.pursuits.get(cid, {})
        ln = prev.get("last_notified_stage", "") if last_notified_stage is None \
            else last_notified_stage
        self.pursuits[cid] = {
            "char_id": cid, "hunter_name": hunter, "progress": progress,
            "stage": stage, "last_notified_stage": ln, "updated_at": 0.0,
        }

    async def clear_dsp_pursuit(self, cid):
        return bool(self.pursuits.pop(cid, None))


class _StubSession:
    def __init__(self, cid, name="X"):
        self.character = {"id": cid, "name": name}
        self.is_in_game = True
        self.lines = []

    async def send_line(self, text=""):
        self.lines.append(text)


class _StubSessionMgr:
    def __init__(self, sessions):
        self.all = sessions


class _Ctx:
    def __init__(self, db, session_mgr, tick_count=1):
        self.db = db
        self.session_mgr = session_mgr
        self.tick_count = tick_count
        self.server = None


def _tick():
    from server.tick_handlers_progression import dsp_hunter_tick
    return dsp_hunter_tick


class TestDspHunterTick(unittest.TestCase):
    def test_creates_pursuit_and_assigns_hunter(self):
        db = _StubDB([{"id": 7, "name": "Darth Test", "dark_side_points": 6}])
        ctx = _Ctx(db, _StubSessionMgr([]))  # offline
        _run(_tick()(ctx))
        self.assertIn(7, db.pursuits)
        self.assertEqual(db.pursuits[7]["hunter_name"], H.hunter_for(7))
        self.assertEqual(db.pursuits[7]["progress"], H.step_for_dsp(6))

    def test_offline_quarry_advances_without_warning(self):
        db = _StubDB([{"id": 7, "name": "Darth Test", "dark_side_points": 9}])
        ctx = _Ctx(db, _StubSessionMgr([]))
        _run(_tick()(ctx))
        # advanced, but no last_notified set (nobody to warn)
        self.assertEqual(db.pursuits[7]["progress"], H.step_for_dsp(9))
        self.assertEqual(db.pursuits[7]["last_notified_stage"], "")

    def test_online_quarry_warned_once_per_stage(self):
        sess = _StubSession(7, "Darth Test")
        db = _StubDB([{"id": 7, "name": "Darth Test", "dark_side_points": 5}])
        ctx = _Ctx(db, _StubSessionMgr([sess]))
        # tick 1: enters 'tracking', warns once
        _run(_tick()(ctx))
        self.assertEqual(db.pursuits[7]["stage"], "tracking")
        self.assertEqual(db.pursuits[7]["last_notified_stage"], "tracking")
        self.assertEqual(len(sess.lines), 1)
        # tick 2: still 'tracking' (Marked steps +5 → 10, < closing@40); no repeat
        _run(_tick()(ctx))
        self.assertEqual(db.pursuits[7]["stage"], "tracking")
        self.assertEqual(len(sess.lines), 1, "must not re-warn the same stage")

    def test_stage_change_warns_again(self):
        sess = _StubSession(7, "Darth Test")
        # Pre-seed a pursuit already near the closing boundary, last warned 'tracking'.
        db = _StubDB([{"id": 7, "name": "Darth Test", "dark_side_points": 9}])
        db.pursuits[7] = {"char_id": 7, "hunter_name": H.hunter_for(7),
                          "progress": 38, "stage": "tracking",
                          "last_notified_stage": "tracking", "updated_at": 0.0}
        ctx = _Ctx(db, _StubSessionMgr([sess]))
        _run(_tick()(ctx))  # 38 + 14 = 52 → closing
        self.assertEqual(db.pursuits[7]["stage"], "closing")
        self.assertEqual(db.pursuits[7]["last_notified_stage"], "closing")
        self.assertEqual(len(sess.lines), 1)
        self.assertIn(H.hunter_for(7).lower(), sess.lines[0].lower())

    def test_atoned_quarry_cleared_with_trail_cold(self):
        sess = _StubSession(7, "Redeemed")
        # Pursuit exists, but the character is no longer in the wanted list.
        db = _StubDB([])  # nobody wanted now
        db.pursuits[7] = {"char_id": 7, "hunter_name": "Varn Kessate",
                          "progress": 60, "stage": "closing",
                          "last_notified_stage": "closing", "updated_at": 0.0}
        ctx = _Ctx(db, _StubSessionMgr([sess]))
        _run(_tick()(ctx))
        self.assertNotIn(7, db.pursuits, "atoned quarry's pursuit must clear")
        self.assertTrue(any("lost the trail" in l for l in sess.lines))

    def test_non_wanted_never_tracked(self):
        db = _StubDB([{"id": 7, "name": "Saint", "dark_side_points": 1}])
        ctx = _Ctx(db, _StubSessionMgr([]))
        _run(_tick()(ctx))
        self.assertEqual(db.pursuits, {})


# ─────────────────────────────────────────────────────────────────────────────
# Board integration
# ─────────────────────────────────────────────────────────────────────────────
class TestBoardIntegration(unittest.TestCase):
    def test_section_annotates_pursuit(self):
        wanted = [
            {"id": 1, "name": "Darth Test", "dark_side_points": 7},
            {"id": 2, "name": "Grey One", "dark_side_points": 4},
        ]
        pursuits = {1: {"char_id": 1, "stage": "imminent"},
                    2: {"char_id": 2, "stage": "tracking"}}
        out = B.format_dsp_notoriety_section(wanted, pursuits)
        body = "\n".join(out)
        self.assertIn("closing in", body)            # imminent suffix
        self.assertIn("has the trail", body)         # tracking suffix

    def test_section_without_pursuits_is_unannotated(self):
        wanted = [{"id": 1, "name": "Darth Test", "dark_side_points": 7}]
        out = B.format_dsp_notoriety_section(wanted)  # no pursuits arg
        body = "\n".join(out)
        self.assertNotIn("hunter", body.lower())

    def test_empty_when_no_one_wanted(self):
        self.assertEqual(B.format_dsp_notoriety_section([], {}), [])


if __name__ == "__main__":
    unittest.main()
