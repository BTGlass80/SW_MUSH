# -*- coding: utf-8 -*-
"""tests/test_t319_objective_telemetry.py — T3.19 objective-funnel emitters.

The telemetry BREADTH pass (catalog C): a single ``objective`` event emitted
at the lifecycle chokepoints of the three board systems, so one site each
captures an entire start/complete/abandon funnel:

  * ``MissionBoard.accept|complete|abandon``  → kind="mission"
  * ``BountyBoard.claim|collect``             → kind="bounty"
  * ``SmugglingBoard.accept|complete|fail|dump_cargo`` → kind="smuggling"

The contract (Brian, telemetry_purpose_clarified): emit is non-blocking
(buffer only), fail-open (a telemetry break NEVER disturbs the accept/complete
/abandon path it observes), and records a real transition only after the DB
mutation lands. These tests drive the real board methods with a no-op stub DB
and drain the module-singleton sink — nothing is written to disk.
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


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class _StubDB:
    """No-op async DB — the boards persist through these; we only assert the
    telemetry side-effect. _save_job swallows its own errors, so even a raising
    stub would be safe, but a clean no-op keeps the test about telemetry."""
    async def accept_mission(self, *a, **k):
        pass

    async def complete_mission(self, *a, **k):
        pass

    async def abandon_mission(self, *a, **k):
        pass

    async def update_bounty(self, *a, **k):
        pass

    async def execute(self, *a, **k):
        pass

    async def commit(self, *a, **k):
        pass


def _objs():
    """Drain the singleton sink and return only the objective records."""
    from engine import telemetry
    recs = [json.loads(ln) for ln in telemetry.get_sink().drain()]
    return [r for r in recs if r.get("ev") == "objective"]


# ── dataclass builders (only the fields the emitters read matter) ───────────
def _mission(mid="m1", reward=500, status=None, accepted_by=None):
    from engine.missions import Mission, MissionType, MissionStatus
    return Mission(
        id=mid, mission_type=MissionType.DELIVERY, title="Run", giver="Vex",
        objective="deliver", destination="Dock 7", destination_room_id=None,
        reward=reward, required_skill="space transports",
        status=status or MissionStatus.AVAILABLE, accepted_by=accepted_by,
        faction_code="republic",
    )


def _contract(cid="c1", reward=800, bonus=200, status=None, claimed_by=None,
              npc_id=None):
    from engine.bounty_board import BountyContract, BountyTier, BountyStatus
    return BountyContract(
        id=cid, tier=next(iter(BountyTier)), target_name="Tarko Vinn",
        target_species="human", target_archetype="thug",
        crime_description="theft", posting_org="BHG", tip="last seen Mos Eisley",
        reward=reward, reward_alive_bonus=bonus, target_npc_id=npc_id,
        target_room_id=None, status=status or BountyStatus.POSTED,
        claimed_by=claimed_by,
    )


def _job(jid="j1", reward=400, fine=100, status=None, accepted_by=None):
    from engine.smuggling import SmugglingJob, CargoTier, JobStatus
    return SmugglingJob(
        id=jid, tier=CargoTier.GREY_MARKET, cargo_type="spice",
        contact_name="Greedo", dropoff_name="Docking Bay 94", reward=reward,
        fine=fine, patrol_chance=0.2, status=status or JobStatus.AVAILABLE,
        accepted_by=accepted_by,
    )


# ══════════════════════════════════════════════════════════════════════════
# 1. The emit_objective helper (schema + coercion + None-drop + fail-open)
# ══════════════════════════════════════════════════════════════════════════
class TestEmitObjectiveHelper(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        telemetry.reset()  # fresh singleton per test

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_envelope_and_core_fields(self):
        from engine.telemetry import emit_objective
        emit_objective("mission", "start", 7, oid="m1", reward=500,
                       mission_type="delivery")
        recs = _objs()
        self.assertEqual(len(recs), 1)
        r = recs[0]
        self.assertEqual(r["ev"], "objective")
        self.assertEqual(r["kind"], "mission")
        self.assertEqual(r["phase"], "start")
        self.assertEqual(r["char_id"], 7)
        self.assertEqual(r["oid"], "m1")
        self.assertEqual(r["reward"], 500)
        self.assertEqual(r["mission_type"], "delivery")

    def test_char_id_coerced_to_int(self):
        from engine.telemetry import emit_objective
        emit_objective("bounty", "complete", "42", oid="c1", reward=1)
        self.assertEqual(_objs()[0]["char_id"], 42)

    def test_none_extra_fields_dropped(self):
        from engine.telemetry import emit_objective
        emit_objective("mission", "abandon", 1, oid="m1", reward=0,
                       faction=None, mission_type="combat")
        r = _objs()[0]
        self.assertNotIn("faction", r)
        self.assertEqual(r["mission_type"], "combat")

    def test_uncoercible_char_id_kept_not_raised(self):
        from engine.telemetry import emit_objective
        # int(["x"]) raises TypeError → caught, char_id kept as-is, still emits.
        emit_objective("smuggling", "start", ["x"], oid="j1", reward=10)
        self.assertEqual(_objs()[0]["char_id"], ["x"])

    def test_helper_never_raises_on_bad_extra(self):
        from engine.telemetry import emit_objective
        # A non-serializable extra must not raise (emit degrades via default=str).
        try:
            emit_objective("mission", "start", 1, oid="m", reward=0,
                           weird=object())
        except Exception as e:  # pragma: no cover
            self.fail(f"emit_objective raised: {e}")


# ══════════════════════════════════════════════════════════════════════════
# 2. Mission funnel — start / complete / abandon
# ══════════════════════════════════════════════════════════════════════════
class TestMissionEmitters(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        from engine.missions import MissionBoard
        telemetry.reset()
        self.board = MissionBoard()
        self.db = _StubDB()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_accept_emits_start(self):
        m = _mission(reward=500)
        self.board._missions[m.id] = m
        out = _run(self.board.accept(m.id, "7", self.db))
        self.assertIsNotNone(out)
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("mission", "start"))
        self.assertEqual(r[0]["char_id"], 7)
        self.assertEqual(r[0]["reward"], 500)
        self.assertEqual(r[0]["faction"], "republic")

    def test_complete_emits_complete_with_acceptor(self):
        from engine.missions import MissionStatus
        m = _mission(status=MissionStatus.ACCEPTED, accepted_by="7")
        self.board._missions[m.id] = m
        _run(self.board.complete(m.id, self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("mission", "complete"))
        self.assertEqual(r[0]["char_id"], 7)

    def test_abandon_emits_with_prev_char(self):
        from engine.missions import MissionStatus
        m = _mission(status=MissionStatus.ACCEPTED, accepted_by="9")
        self.board._missions[m.id] = m
        _run(self.board.abandon(m.id, self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("mission", "abandon"))
        # captured BEFORE accepted_by was cleared
        self.assertEqual(r[0]["char_id"], 9)

    def test_no_emit_when_transition_rejected(self):
        # accept on an already-accepted mission returns None → no telemetry.
        from engine.missions import MissionStatus
        m = _mission(status=MissionStatus.ACCEPTED, accepted_by="1")
        self.board._missions[m.id] = m
        out = _run(self.board.accept(m.id, "2", self.db))
        self.assertIsNone(out)
        self.assertEqual(_objs(), [])

    def test_telemetry_break_does_not_break_accept(self):
        # Fail-open contract: a raising emitter must not stop the accept.
        from engine import telemetry
        orig = telemetry.emit_objective

        def _boom(*a, **k):
            raise RuntimeError("telemetry down")

        telemetry.emit_objective = _boom
        try:
            m = _mission()
            self.board._missions[m.id] = m
            out = _run(self.board.accept(m.id, "7", self.db))
            self.assertIsNotNone(out)            # gameplay succeeded anyway
        finally:
            telemetry.emit_objective = orig


# ══════════════════════════════════════════════════════════════════════════
# 3. Bounty funnel — start / complete (incl. auto-collect on kill)
# ══════════════════════════════════════════════════════════════════════════
class TestBountyEmitters(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        from engine.bounty_board import BountyBoard
        telemetry.reset()
        self.board = BountyBoard()
        self.db = _StubDB()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_claim_emits_start(self):
        c = _contract(reward=800)
        self.board._contracts[c.id] = c
        _run(self.board.claim(c.id, "5", self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("bounty", "start"))
        self.assertEqual(r[0]["char_id"], 5)
        self.assertEqual(r[0]["reward"], 800)
        self.assertEqual(r[0]["target"], "Tarko Vinn")

    def test_collect_alive_includes_bonus(self):
        from engine.bounty_board import BountyStatus
        c = _contract(reward=800, bonus=200, status=BountyStatus.CLAIMED,
                      claimed_by="5")
        self.board._contracts[c.id] = c
        _run(self.board.collect(c.id, alive=True, db=self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("bounty", "complete"))
        self.assertEqual(r[0]["reward"], 1000)   # base + alive bonus
        self.assertTrue(r[0]["alive"])

    def test_collect_dead_no_bonus(self):
        from engine.bounty_board import BountyStatus
        c = _contract(reward=800, bonus=200, status=BountyStatus.CLAIMED,
                      claimed_by="5")
        self.board._contracts[c.id] = c
        _run(self.board.collect(c.id, alive=False, db=self.db))
        r = _objs()
        self.assertEqual(r[0]["reward"], 800)
        self.assertFalse(r[0]["alive"])

    def test_auto_collect_on_kill_routes_through(self):
        # notify_target_killed → collect(), so one 'complete' is emitted.
        from engine.bounty_board import BountyStatus
        c = _contract(status=BountyStatus.CLAIMED, claimed_by="5", npc_id=77)
        self.board._contracts[c.id] = c
        _run(self.board.notify_target_killed(77, "5", self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("bounty", "complete"))
        self.assertFalse(r[0]["alive"])          # kills always count as dead


# ══════════════════════════════════════════════════════════════════════════
# 4. Smuggling funnel — start / complete / abandon (bust + jettison)
# ══════════════════════════════════════════════════════════════════════════
class TestSmugglingEmitters(unittest.TestCase):
    def setUp(self):
        from engine import telemetry
        from engine.smuggling import SmugglingBoard
        telemetry.reset()
        self.board = SmugglingBoard()
        self.db = _StubDB()

    def tearDown(self):
        from engine import telemetry
        telemetry.reset()

    def test_accept_emits_start(self):
        j = _job(reward=400)
        self.board._jobs[j.id] = j
        _run(self.board.accept(j.id, 3, self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]), ("smuggling", "start"))
        self.assertEqual(r[0]["char_id"], 3)
        self.assertEqual(r[0]["reward"], 400)
        self.assertEqual(r[0]["cargo"], "spice")

    def test_complete_emits_complete(self):
        from engine.smuggling import JobStatus
        j = _job(status=JobStatus.ACCEPTED, accepted_by=3)
        self.board._jobs[j.id] = j
        _run(self.board.complete(3, self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]),
                         ("smuggling", "complete"))

    def test_fail_emits_abandon_with_reason_and_fine(self):
        from engine.smuggling import JobStatus
        j = _job(fine=100, status=JobStatus.ACCEPTED, accepted_by=3)
        self.board._jobs[j.id] = j
        _run(self.board.fail(3, self.db, reason="caught"))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]),
                         ("smuggling", "abandon"))
        self.assertEqual(r[0]["reason"], "caught")
        self.assertEqual(r[0]["fine"], 100)

    def test_dump_emits_abandon_dumped(self):
        from engine.smuggling import JobStatus
        j = _job(status=JobStatus.ACCEPTED, accepted_by=3)
        self.board._jobs[j.id] = j
        _run(self.board.dump_cargo(3, self.db))
        r = _objs()
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["kind"], r[0]["phase"]),
                         ("smuggling", "abandon"))
        self.assertEqual(r[0]["reason"], "dumped")
        self.assertNotIn("fine", r[0])           # jettison forfeits nothing


if __name__ == "__main__":
    unittest.main()
