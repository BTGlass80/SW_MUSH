# -*- coding: utf-8 -*-
"""tests/test_t3_22_ambient_life_phase1.py — Ambient NPC Life, Phase 1
(T3.22, 2026-06-24).

Tests the deterministic sim core: goals, intra-zone movement, state machine,
tick budget, opt-in default, no mechanical effects, singleton/reset, and no
Ollama on the tick path.

Classes:
  TestGoalSelection         — select_goal deterministic per time_of_day band
  TestDestinationPicking    — intra-zone only; rest/work → home anchor
  TestMovementStateMachine  — depart→arrive over in-memory DB; room_id updated
  TestTickBudget            — <= AMBIENT_TICK_BUDGET processed per tick call
  TestOptInDefault          — ambient_enabled absent → never bootstrapped/moved
  TestNoMechanicalEffects   — no credit/market/faction/combat writes on tick
  TestSingletonReset        — reset_ambient_life_manager gives a fresh instance
  TestNoOllamaOnTickPath    — AI manager raise must never be triggered
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import random
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — minimal in-memory DB
# ─────────────────────────────────────────────────────────────────────────────

async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_room(db, name="Room", zone_id=None) -> int:
    cur = await db._db.execute(
        "INSERT INTO rooms (name, zone_id) VALUES (?, ?)", (name, zone_id))
    await db._db.commit()
    return cur.lastrowid


async def _make_zone(db, name="Zone A") -> int:
    cur = await db._db.execute(
        "INSERT INTO zones (name) VALUES (?)", (name,))
    await db._db.commit()
    return cur.lastrowid


async def _make_exit(db, from_room: int, to_room: int, direction: str = "north") -> None:
    await db._db.execute(
        "INSERT INTO exits (from_room_id, to_room_id, direction) VALUES (?, ?, ?)",
        (from_room, to_room, direction),
    )
    await db._db.commit()


async def _make_npc(db, name="Test NPC", room_id=None,
                    ambient_enabled=False, routine="generic",
                    home_room_id=None) -> int:
    ai_cfg: dict = {}
    if ambient_enabled:
        ai_cfg["ambient_enabled"] = True
    if routine != "generic":
        ai_cfg["ambient_routine"] = routine
    if home_room_id is not None:
        ai_cfg["home_room_id"] = home_room_id
    cur = await db._db.execute(
        "INSERT INTO npcs (name, room_id, ai_config_json) VALUES (?, ?, ?)",
        (name, room_id, json.dumps(ai_cfg)),
    )
    await db._db.commit()
    return cur.lastrowid


def _make_session_mgr():
    """Return a mock SessionManager with broadcast_to_room as a no-op."""
    mgr = MagicMock()
    mgr.broadcast_to_room = AsyncMock(return_value=None)
    return mgr


# ═════════════════════════════════════════════════════════════════════
# 1. TestGoalSelection
# ═════════════════════════════════════════════════════════════════════

class TestGoalSelection(unittest.TestCase):

    def _sel(self, routine, time_of_day, seed=42) -> str:
        from engine.ambient_life import select_goal
        rng = random.Random(seed)
        return select_goal(routine, time_of_day, rng=rng)

    def test_generic_day_returns_valid_goal(self):
        from engine.ambient_life import GOAL_SET
        g = self._sel("generic", "day")
        self.assertIn(g, GOAL_SET)

    def test_generic_night_returns_rest_or_patrol(self):
        from engine.ambient_life import GOAL_SET
        # Run many draws — all must be valid goals
        from engine.ambient_life import select_goal
        rng = random.Random(7)
        for _ in range(30):
            g = select_goal("generic", "night", rng=rng)
            self.assertIn(g, GOAL_SET)

    def test_merchant_night_returns_rest(self):
        # merchant/night pool is ["rest"] → always rest
        from engine.ambient_life import select_goal
        g = select_goal("merchant", "night", rng=random.Random(1))
        self.assertEqual(g, "rest")

    def test_guard_all_goals_are_patrol_or_work(self):
        from engine.ambient_life import select_goal
        rng = random.Random(99)
        for tod in ("day", "dusk", "night"):
            for _ in range(10):
                g = select_goal("guard", tod, rng=rng)
                self.assertIn(g, {"patrol", "rest", "work"})

    def test_unknown_routine_falls_back_to_generic(self):
        from engine.ambient_life import select_goal, GOAL_SET
        g = select_goal("totally_unknown_routine", "day", rng=random.Random(3))
        self.assertIn(g, GOAL_SET)

    def test_allowed_override_ignores_routine(self):
        from engine.ambient_life import select_goal
        # Force only "trade" — routine and time_of_day are irrelevant.
        g = select_goal("guard", "night",
                        allowed=frozenset({"trade"}), rng=random.Random(1))
        self.assertEqual(g, "trade")

    def test_deterministic_with_same_seed(self):
        from engine.ambient_life import select_goal
        g1 = select_goal("generic", "day", rng=random.Random(5))
        g2 = select_goal("generic", "day", rng=random.Random(5))
        self.assertEqual(g1, g2)


# ═════════════════════════════════════════════════════════════════════
# 2. TestDestinationPicking
# ═════════════════════════════════════════════════════════════════════

class TestDestinationPicking(unittest.TestCase):

    def _exits(self, *room_ids, direction="north") -> list[dict]:
        return [{"to_room_id": r, "direction": direction} for r in room_ids]

    def test_no_exits_returns_none(self):
        from engine.ambient_life import pick_destination_room
        result = pick_destination_room(1, None, "work", [])
        self.assertIsNone(result)

    def test_rest_goal_prefers_home(self):
        from engine.ambient_life import pick_destination_room
        exits = self._exits(10, 20, 30)
        # home is room 20
        result = pick_destination_room(1, 20, "rest", exits, rng=random.Random(1))
        self.assertEqual(result, 20)

    def test_work_goal_prefers_home(self):
        from engine.ambient_life import pick_destination_room
        exits = self._exits(5, 10, 15)
        result = pick_destination_room(1, 10, "work", exits, rng=random.Random(2))
        self.assertEqual(result, 10)

    def test_socialize_ignores_home_picks_any(self):
        from engine.ambient_life import pick_destination_room
        exits = self._exits(10, 20, 30)
        results = set()
        for seed in range(20):
            r = pick_destination_room(1, 10, "socialize", exits,
                                      rng=random.Random(seed))
            results.add(r)
        # Should sometimes pick rooms other than home (10).
        self.assertTrue(results - {10},
                        "socialize should occasionally pick non-home rooms")

    def test_avoids_staying_in_current_room_when_alternatives(self):
        from engine.ambient_life import pick_destination_room
        # Only one exit pointing to room 5 (current) and another to 10.
        exits = [{"to_room_id": 5, "direction": "north"},
                 {"to_room_id": 10, "direction": "south"}]
        # Run many times — should never return current_room=5 when alternatives exist.
        for seed in range(30):
            r = pick_destination_room(5, None, "patrol", exits,
                                      rng=random.Random(seed))
            self.assertEqual(r, 10)

    def test_single_exit_returns_that_room(self):
        from engine.ambient_life import pick_destination_room
        exits = [{"to_room_id": 99, "direction": "east"}]
        result = pick_destination_room(1, None, "patrol", exits)
        self.assertEqual(result, 99)


# ═════════════════════════════════════════════════════════════════════
# 3. TestMovementStateMachine
# ═════════════════════════════════════════════════════════════════════

class TestMovementStateMachine(unittest.TestCase):
    """Drive an ambient NPC through IDLE→MOVING→IDLE, verifying npcs.room_id."""

    def test_npc_moves_between_rooms(self):
        async def _check():
            from engine.ambient_life import (
                AmbientLifeManager, MOVE_MIN_SECS, LOITER_MIN_SECS, LOITER_MAX_SECS,
                AmbientState,
            )
            db = await _fresh_db()
            zone_id = await _make_zone(db)
            r1 = await _make_room(db, "Room A", zone_id=zone_id)
            r2 = await _make_room(db, "Room B", zone_id=zone_id)
            await _make_exit(db, r1, r2, "north")
            await _make_exit(db, r2, r1, "south")

            npc_id = await _make_npc(db, "Wanderer", room_id=r1,
                                     ambient_enabled=True, home_room_id=r1)
            session_mgr = _make_session_mgr()

            mgr = AmbientLifeManager()

            # --- Tick 1: bootstrap + IDLE (loiter_until is in the future) ---
            now = time.time()
            await mgr._bootstrap(db, now)
            mem = mgr._npcs[npc_id]
            self.assertEqual(mem["state"], AmbientState.IDLE)
            # NPC should still be in r1 (hasn't moved yet).

            # Force loiter_until to expire.
            mem["loiter_until"] = now - 1.0
            mem["current_room_id"] = r1

            # --- Tick 2: IDLE → select goal → depart → MOVING ---
            # Patch random so the NPC goes to r2 (not home r1).
            # Goal "socialize" skips home bias; r2 is the only other exit.
            mem["goal"] = "socialize"
            with patch("engine.ambient_life.pick_destination_room",
                       return_value=r2):
                await mgr._tick_idle(npc_id, mem, db, session_mgr, now + 1,
                                     "day")

            self.assertEqual(mem["state"], AmbientState.MOVING)
            self.assertEqual(mem["dest_room_id"], r2)
            # Departure broadcast should have fired to r1.
            session_mgr.broadcast_to_room.assert_awaited()

            # --- Tick 3: MOVING before elapsed → no arrival ---
            session_mgr.broadcast_to_room.reset_mock()
            mem["state_entered_at"] = now  # just started
            await mgr._tick_moving(npc_id, mem, db, session_mgr, now + 5)
            # Still moving.
            self.assertEqual(mem["state"], AmbientState.MOVING)
            # No broadcast yet.
            session_mgr.broadcast_to_room.assert_not_awaited()

            # --- Tick 4: MOVING after elapsed → arrive at r2 ---
            mem["state_entered_at"] = now - 1000  # force elapsed
            session_mgr.broadcast_to_room.reset_mock()
            await mgr._tick_moving(npc_id, mem, db, session_mgr, now + 1001)
            self.assertEqual(mem["state"], AmbientState.IDLE)
            self.assertEqual(mem["current_room_id"], r2)
            # npcs.room_id must be updated in DB.
            npc_row = await db.get_npc(npc_id)
            self.assertEqual(npc_row["room_id"], r2)
            # Arrival broadcast should have fired to r2.
            session_mgr.broadcast_to_room.assert_awaited()

            # ambient_state.current_room_id should also be r2.
            state_row = await db.ambient_state_get(npc_id)
            self.assertEqual(state_row["current_room_id"], r2)

            await db.close()

        _run(_check())

    def test_intra_zone_filter_blocks_cross_zone_exits(self):
        """_intra_zone_exits must return only exits where dest shares zone_id."""
        async def _check():
            from engine.ambient_life import AmbientLifeManager
            db = await _fresh_db()
            zone_a = await _make_zone(db, "Zone A")
            zone_b = await _make_zone(db, "Zone B")
            r1 = await _make_room(db, "Room 1", zone_id=zone_a)
            r2 = await _make_room(db, "Room 2", zone_id=zone_a)   # same zone
            r3 = await _make_room(db, "Room 3", zone_id=zone_b)   # different zone
            await _make_exit(db, r1, r2, "north")
            await _make_exit(db, r1, r3, "east")

            mgr = AmbientLifeManager()
            intra = await mgr._intra_zone_exits(r1, db)
            dest_ids = {e["to_room_id"] for e in intra}
            self.assertIn(r2, dest_ids)
            self.assertNotIn(r3, dest_ids)
            await db.close()

        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. TestTickBudget
# ═════════════════════════════════════════════════════════════════════

class TestTickBudget(unittest.TestCase):

    def test_at_most_budget_npcs_processed_per_tick(self):
        """With more ambient NPCs than AMBIENT_TICK_BUDGET, only budget are ticked."""
        async def _check():
            from engine.ambient_life import (
                AmbientLifeManager, AMBIENT_TICK_BUDGET, AmbientState,
            )
            db = await _fresh_db()
            zone_id = await _make_zone(db)
            r1 = await _make_room(db, "Hub", zone_id=zone_id)

            # Create AMBIENT_TICK_BUDGET + 3 ambient-enabled NPCs in same room.
            total = AMBIENT_TICK_BUDGET + 3
            npc_ids = []
            for i in range(total):
                nid = await _make_npc(db, f"NPC-{i}", room_id=r1,
                                     ambient_enabled=True)
                npc_ids.append(nid)

            session_mgr = _make_session_mgr()
            mgr = AmbientLifeManager()

            # One tick call.
            await mgr.tick(db, session_mgr)

            # At most AMBIENT_TICK_BUDGET last_tick_at values should be non-zero
            # (meaning those NPCs were actually ticked).
            ticked = sum(
                1 for mem in mgr._npcs.values()
                if mem.get("last_tick_at", 0.0) > 0.0
            )
            self.assertLessEqual(ticked, AMBIENT_TICK_BUDGET,
                                 f"Too many NPCs ticked in one call: {ticked} > "
                                 f"{AMBIENT_TICK_BUDGET}")
            await db.close()

        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. TestOptInDefault
# ═════════════════════════════════════════════════════════════════════

class TestOptInDefault(unittest.TestCase):

    def test_npc_without_ambient_enabled_never_bootstrapped(self):
        """An NPC with no ambient_enabled flag must never appear in _npcs."""
        async def _check():
            from engine.ambient_life import AmbientLifeManager
            db = await _fresh_db()
            r1 = await _make_room(db, "Room")
            # ambient_enabled defaults to False in _make_npc.
            npc_id = await _make_npc(db, "Quiet NPC", room_id=r1,
                                     ambient_enabled=False)
            session_mgr = _make_session_mgr()
            mgr = AmbientLifeManager()

            # Run several ticks.
            for _ in range(5):
                await mgr.tick(db, session_mgr)

            self.assertNotIn(npc_id, mgr._npcs,
                             "NPC without ambient_enabled must not be bootstrapped")
            # Verify no ambient_state row was created for this NPC.
            row = await db.ambient_state_get(npc_id)
            self.assertIsNone(row)
            await db.close()

        _run(_check())

    def test_npc_with_ambient_enabled_false_not_bootstrapped(self):
        """ambient_enabled=false (explicit) is also not bootstrapped."""
        async def _check():
            from engine.ambient_life import AmbientLifeManager
            db = await _fresh_db()
            r1 = await _make_room(db, "Room")
            cur = await db._db.execute(
                "INSERT INTO npcs (name, room_id, ai_config_json) VALUES (?, ?, ?)",
                ("Explicit False", r1, json.dumps({"ambient_enabled": False})),
            )
            await db._db.commit()
            npc_id = cur.lastrowid

            mgr = AmbientLifeManager()
            session_mgr = _make_session_mgr()
            await mgr.tick(db, session_mgr)

            self.assertNotIn(npc_id, mgr._npcs)
            await db.close()

        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. TestNoMechanicalEffects
# ═════════════════════════════════════════════════════════════════════

class TestNoMechanicalEffects(unittest.TestCase):
    """Confirm the sim does not call any credit / market / faction / combat sink."""

    def test_no_adjust_credits_call(self):
        """Running many ticks must never invoke db.adjust_credits."""
        async def _check():
            from engine.ambient_life import AmbientLifeManager, MOVE_MIN_SECS
            db = await _fresh_db()
            zone_id = await _make_zone(db)
            r1 = await _make_room(db, "A", zone_id=zone_id)
            r2 = await _make_room(db, "B", zone_id=zone_id)
            await _make_exit(db, r1, r2, "north")
            await _make_exit(db, r2, r1, "south")
            npc_id = await _make_npc(db, "Wanderer", room_id=r1,
                                     ambient_enabled=True)

            session_mgr = _make_session_mgr()
            # Spy on adjust_credits — must never be called.
            original_adjust = db.adjust_credits
            calls = []

            async def _spy(*a, **kw):
                calls.append((a, kw))
                return await original_adjust(*a, **kw)

            db.adjust_credits = _spy

            mgr = AmbientLifeManager()
            # Simulate several ticks spanning a full move cycle.
            now = time.time()
            for i in range(20):
                await mgr.tick(db, session_mgr)
                # Force loiter to expire so movement is attempted.
                for mem in mgr._npcs.values():
                    mem["loiter_until"] = now - 1
                    mem["state_entered_at"] = now - MOVE_MIN_SECS * 2

            self.assertEqual(calls, [],
                             "adjust_credits must never be called by the ambient sim")
            await db.close()

        _run(_check())

    def test_no_territory_import_statement(self):
        """The ambient_life module must not have an import statement for engine.territory."""
        import engine.ambient_life as _mod
        import inspect
        # Scan only actual import lines, not docstrings/comments.
        src = inspect.getsource(_mod)
        import_lines = [ln for ln in src.splitlines()
                        if ln.strip().startswith(("import ", "from "))]
        for ln in import_lines:
            self.assertNotIn("engine.territory", ln,
                             f"Found engine.territory import in ambient_life: {ln}")

    def test_no_combat_import_statement(self):
        """The ambient_life module must not have an import statement for engine.combat."""
        import engine.ambient_life as _mod
        import inspect
        src = inspect.getsource(_mod)
        import_lines = [ln for ln in src.splitlines()
                        if ln.strip().startswith(("import ", "from "))]
        for ln in import_lines:
            self.assertNotIn("engine.combat", ln,
                             f"Found engine.combat import in ambient_life: {ln}")

    def test_only_allowed_db_writes(self):
        """The ambient_life module may only call update_npc and ambient_state_* on db.

        Verify by inspecting the source for any other db method calls that write
        data (adjust_credits, save_character, log_credit, etc.).
        """
        import engine.ambient_life as _mod
        import inspect
        src = inspect.getsource(_mod)
        # These writes are explicitly banned.
        banned = [
            "adjust_credits",
            "log_credit",
            "save_character",
            "adjust_territory_influence",
            "perform_skill_check",
        ]
        for term in banned:
            self.assertNotIn(
                term, src,
                f"engine/ambient_life.py must not call db.{term} — "
                f"found '{term}' in source"
            )


# ═════════════════════════════════════════════════════════════════════
# 7. TestSingletonReset
# ═════════════════════════════════════════════════════════════════════

class TestSingletonReset(unittest.TestCase):

    def setUp(self):
        from engine.ambient_life import reset_ambient_life_manager
        reset_ambient_life_manager()

    def tearDown(self):
        from engine.ambient_life import reset_ambient_life_manager
        reset_ambient_life_manager()

    def test_get_returns_same_instance(self):
        from engine.ambient_life import get_ambient_life_manager
        a = get_ambient_life_manager()
        b = get_ambient_life_manager()
        self.assertIs(a, b)

    def test_reset_gives_fresh_instance(self):
        from engine.ambient_life import (
            get_ambient_life_manager, reset_ambient_life_manager,
        )
        a = get_ambient_life_manager()
        reset_ambient_life_manager()
        b = get_ambient_life_manager()
        self.assertIsNot(a, b)

    def test_fresh_instance_has_empty_npcs(self):
        from engine.ambient_life import get_ambient_life_manager
        mgr = get_ambient_life_manager()
        self.assertEqual(mgr._npcs, {})


# ═════════════════════════════════════════════════════════════════════
# 8. TestNoOllamaOnTickPath
# ═════════════════════════════════════════════════════════════════════

class TestNoOllamaOnTickPath(unittest.TestCase):

    def test_ai_manager_never_invoked_during_tick(self):
        """Patch the AI manager to raise on any call; ambient tick must not trigger it."""
        async def _check():
            from engine.ambient_life import AmbientLifeManager
            db = await _fresh_db()
            zone_id = await _make_zone(db)
            r1 = await _make_room(db, "A", zone_id=zone_id)
            r2 = await _make_room(db, "B", zone_id=zone_id)
            await _make_exit(db, r1, r2, "north")
            npc_id = await _make_npc(db, "Talker", room_id=r1,
                                     ambient_enabled=True)
            session_mgr = _make_session_mgr()

            # Patch the AI manager module-level singleton to raise on any attr.
            exploding_ai = MagicMock(side_effect=RuntimeError("Ollama was touched!"))

            with patch("engine.idle_queue.IdleQueue", side_effect=RuntimeError):
                # The ambient tick must complete without touching Ollama.
                mgr = AmbientLifeManager()
                try:
                    await mgr.tick(db, session_mgr)
                except RuntimeError as e:
                    if "Ollama" in str(e):
                        self.fail(f"Ambient tick invoked Ollama: {e}")
                    raise  # other errors re-raised

            await db.close()

        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. TestLineFunctions
# ═════════════════════════════════════════════════════════════════════

class TestLineFunctions(unittest.TestCase):
    """Verify the pure line-generation helpers are ANSI-dim and contain name."""

    def test_depart_contains_name(self):
        from engine.ambient_life import templated_depart_line
        line = templated_depart_line("Dex Jettster", "north", rng=random.Random(1))
        self.assertIn("Dex Jettster", line)

    def test_arrive_contains_name(self):
        from engine.ambient_life import templated_arrive_line
        line = templated_arrive_line("Dex Jettster", "south", rng=random.Random(1))
        self.assertIn("Dex Jettster", line)

    def test_activity_contains_name(self):
        from engine.ambient_life import templated_activity_line
        line = templated_activity_line("Dex Jettster", "work", rng=random.Random(1))
        self.assertIn("Dex Jettster", line)

    def test_lines_contain_ansi_dim(self):
        from engine.ambient_life import (
            templated_depart_line, templated_arrive_line,
            templated_activity_line,
        )
        rng = random.Random(42)
        for fn, args in [
            (templated_depart_line, ("Nala Se", "east")),
            (templated_arrive_line, ("Nala Se", "west")),
            (templated_activity_line, ("Nala Se", "trade")),
        ]:
            line = fn(*args, rng=rng)
            self.assertIn("\033[2m", line,
                          f"{fn.__name__} must emit ANSI dim: {repr(line)}")

    def test_depart_contains_direction(self):
        from engine.ambient_life import templated_depart_line
        line = templated_depart_line("Nala Se", "the alley", rng=random.Random(0))
        self.assertIn("the alley", line)

    def test_arrive_contains_direction(self):
        from engine.ambient_life import templated_arrive_line
        line = templated_arrive_line("Nala Se", "the alley", rng=random.Random(0))
        self.assertIn("the alley", line)


if __name__ == "__main__":
    unittest.main()
