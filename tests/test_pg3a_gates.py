# -*- coding: utf-8 -*-
"""
tests/test_pg3a_gates.py — Progression Gates Phase 3, sub-drop a.

Tests the two non-Village pieces of the PG.3 design landed in this
drop:

  1. Predisposition scoring at chargen — covers the species weight
     map, backstory keyword scoring, RNG roll handling, and the
     end-to-end CreationWizard.get_predisposition() integration.

  2. Play-time accumulation — covers the engine/jedi_gating
     accumulate_play_time DB increment, the gate-passed read helper,
     the per-minute tick handler's idle filter, and the Session
     in-memory cache update.

Out of scope for this drop's tests (PG.3.gates.b will cover):
  - Force-sign trigger consultation
  - Real-time Act/Trial cooldown enforcement
  - Village quest YAML wiring
  - FS checkbox removal from chargen UI

Test sections:
  1. TestSpeciesPredispositionWeights  — map sanity
  2. TestBackstoryScoring              — keyword regex + cap
  3. TestComputePredisposition         — integration of all three inputs
  4. TestAccumulatePlayTime            — DB increment math + clamps
  5. TestForceGateHelpers              — is_force_gate_passed +
                                         force_gate_progress
  6. TestPlaytimeHeartbeatTick         — handler against fake sessions
  7. TestWizardIntegration             — CreationWizard.get_predisposition
  8. TestModuleSelfDocs                — source-level marker for the drop
"""
from __future__ import annotations

import asyncio
import os
import sys
import time
import unittest
from unittest.mock import AsyncMock, MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


async def _make_test_char(db, name="Tester", species="Human"):
    """Insert a minimal account + character; return the char_id."""
    await db._db.execute(
        "INSERT INTO accounts(username, password_hash) VALUES(?, 'x')",
        (name.lower(),),
    )
    await db._db.execute(
        "INSERT INTO characters(account_id, name, species) VALUES(1, ?, ?)",
        (name, species),
    )
    await db._db.commit()
    rows = await db._db.execute_fetchall(
        "SELECT id FROM characters WHERE name=?", (name,),
    )
    return rows[0]["id"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. Species weight map sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestSpeciesPredispositionWeights(unittest.TestCase):

    def test_all_weights_in_unit_range(self):
        """All species weights must be in [0.0, 1.0] — values outside
        this range would risk pushing the final score above the
        ceiling without contribution from text or RNG."""
        from engine.jedi_gating import SPECIES_PREDISPOSITION_WEIGHTS
        for sp, w in SPECIES_PREDISPOSITION_WEIGHTS.items():
            self.assertIsInstance(w, float, f"{sp!r} weight is not a float")
            self.assertGreaterEqual(w, 0.0, f"{sp!r} weight is negative")
            self.assertLessEqual(w, 1.0, f"{sp!r} weight is > 1.0")

    def test_miraluka_strongly_weighted(self):
        """Miraluka are canonically Force-sensitive — should get the
        strongest species boost in the map."""
        from engine.jedi_gating import SPECIES_PREDISPOSITION_WEIGHTS
        miraluka_w = SPECIES_PREDISPOSITION_WEIGHTS.get("miraluka", 0.0)
        for sp, w in SPECIES_PREDISPOSITION_WEIGHTS.items():
            if sp == "miraluka":
                continue
            self.assertGreaterEqual(
                miraluka_w, w,
                f"Miraluka weight ({miraluka_w}) should be >= {sp} ({w})",
            )

    def test_neutral_species_baseline_floor(self):
        """Common galactic species (humans, Twi'leks) shouldn't be
        weighted to zero — they have lore presence in the Order."""
        from engine.jedi_gating import SPECIES_PREDISPOSITION_WEIGHTS
        for sp in ("human", "twi'lek", "twilek"):
            self.assertGreater(
                SPECIES_PREDISPOSITION_WEIGHTS.get(sp, 0.0), 0.0,
                f"{sp} should have a positive (non-zero) weight",
            )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Backstory keyword scoring
# ─────────────────────────────────────────────────────────────────────────────

class TestBackstoryScoring(unittest.TestCase):

    def test_empty_text_scores_zero(self):
        from engine.jedi_gating import _backstory_score
        self.assertEqual(_backstory_score(""), 0.0)
        self.assertEqual(_backstory_score(None or ""), 0.0)

    def test_short_text_scores_zero(self):
        """Anything under 5 chars is treated as no input (matches
        the wizard's own 5-char threshold for accepting backstory)."""
        from engine.jedi_gating import _backstory_score
        self.assertEqual(_backstory_score("hi"), 0.0)
        self.assertEqual(_backstory_score("Jedi"), 0.0)  # exactly 4 chars

    def test_unrelated_text_scores_zero(self):
        from engine.jedi_gating import _backstory_score
        text = "Born on Corellia. Fly fast ships. Never look back."
        self.assertEqual(_backstory_score(text), 0.0)

    def test_force_keyword_fires(self):
        from engine.jedi_gating import _backstory_score
        text = "Always felt the Force calling to me from a young age."
        # 'force' (0.10) + 'calling' (0.05) = 0.15
        self.assertAlmostEqual(_backstory_score(text), 0.15, places=6)

    def test_keyword_cap_enforced(self):
        """Stuffing a paragraph with every keyword maxes at the cap,
        not a sum that would dominate species + RNG."""
        from engine.jedi_gating import _backstory_score, BACKSTORY_TOTAL_CAP
        text = (
            "I am a Jedi seeker on a quest searching for purpose. "
            "I meditate at the ancient Sith temple and have visions "
            "and dreams of my destiny. The mystic spirit of an old "
            "hermit monk in the monastery guides me. The Force calls."
        )
        score = _backstory_score(text)
        self.assertLessEqual(score, BACKSTORY_TOTAL_CAP)
        # Verify the cap actually bites on this input, not coincidentally.
        self.assertEqual(score, BACKSTORY_TOTAL_CAP)

    def test_substring_noise_does_not_fire(self):
        """'forced' and 'jedidiah' should not trigger the 'force' /
        'jedi' keywords — whole-word matching only."""
        from engine.jedi_gating import _backstory_score
        text = "Forced into work as a child. Jedidiah was my master smith."
        self.assertEqual(_backstory_score(text), 0.0)

    def test_meditation_root_match(self):
        """`meditat\\w*` should fire on meditate / meditated / meditation."""
        from engine.jedi_gating import _backstory_score
        for variant in ("I meditate daily.", "He meditated for hours.",
                        "Meditation centers her."):
            self.assertGreater(
                _backstory_score(variant), 0.0,
                f"Should fire on {variant!r}",
            )

    def test_case_insensitive(self):
        from engine.jedi_gating import _backstory_score
        lower = _backstory_score("the force is strong here")
        upper = _backstory_score("THE FORCE IS STRONG HERE")
        mixed = _backstory_score("The Force Is Strong Here")
        self.assertEqual(lower, upper)
        self.assertEqual(lower, mixed)


# ─────────────────────────────────────────────────────────────────────────────
# 3. compute_predisposition end-to-end
# ─────────────────────────────────────────────────────────────────────────────

class TestComputePredisposition(unittest.TestCase):

    def test_zero_inputs_zero_score(self):
        from engine.jedi_gating import compute_predisposition
        self.assertEqual(
            compute_predisposition(species=None, backstory=None),
            0.0,
        )

    def test_score_in_unit_range(self):
        """Even worst-case maxed inputs stay in [0, 1]."""
        from engine.jedi_gating import compute_predisposition
        score = compute_predisposition(
            species="Miraluka",
            backstory=(
                "Force jedi sith meditation visions destiny dreams "
                "prophecy mystic spirit ancient temple sage hermit "
                "monastery monk orphan lost seeker searching calling purpose"
            ),
            rng_roll=0.5,
        )
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    def test_deterministic_with_zero_roll(self):
        """Same species + same backstory + roll=0 must produce the
        same score — required for chargen reproducibility in tests."""
        from engine.jedi_gating import compute_predisposition
        a = compute_predisposition("Human", "Just a smuggler.", 0.0)
        b = compute_predisposition("Human", "Just a smuggler.", 0.0)
        self.assertEqual(a, b)

    def test_negative_roll_clamped(self):
        """Defensive: negative rolls are silently clamped to 0."""
        from engine.jedi_gating import compute_predisposition
        a = compute_predisposition("Human", "", rng_roll=-0.3)
        b = compute_predisposition("Human", "", rng_roll=0.0)
        self.assertEqual(a, b)

    def test_excessive_roll_clamped(self):
        """Defensive: rolls > 0.5 are silently clamped to 0.5."""
        from engine.jedi_gating import compute_predisposition
        a = compute_predisposition("Human", "", rng_roll=10.0)
        b = compute_predisposition("Human", "", rng_roll=0.5)
        self.assertEqual(a, b)

    def test_species_normalization(self):
        """Case + whitespace insensitive on species lookup."""
        from engine.jedi_gating import compute_predisposition
        a = compute_predisposition("Miraluka", "")
        b = compute_predisposition("miraluka", "")
        c = compute_predisposition("  MIRALUKA  ", "")
        self.assertEqual(a, b)
        self.assertEqual(a, c)

    def test_unknown_species_zero_species_contribution(self):
        from engine.jedi_gating import compute_predisposition
        # Unknown species + no backstory + no roll = 0
        self.assertEqual(
            compute_predisposition("XyzNotARealSpecies", "", 0.0),
            0.0,
        )

    def test_typical_jedi_backstory(self):
        """A plausible 'I want to be a Jedi' backstory should score
        respectably but not max out."""
        from engine.jedi_gating import compute_predisposition
        score = compute_predisposition(
            species="Human",
            backstory=(
                "Orphaned on Tatooine, raised by a hermit who taught me "
                "to meditate. Dreams of distant battles."
            ),
            rng_roll=0.0,
        )
        # Human (0.10) + orph (0.04) + hermit (0.05) + meditat (0.06)
        # + dream (0.04) = 0.29
        self.assertAlmostEqual(score, 0.29, places=2)


# ─────────────────────────────────────────────────────────────────────────────
# 4. accumulate_play_time DB increment
# ─────────────────────────────────────────────────────────────────────────────

class TestAccumulatePlayTime(unittest.TestCase):

    def test_first_increment(self):
        async def _check():
            from engine.jedi_gating import accumulate_play_time
            db = await _fresh_db()
            cid = await _make_test_char(db)
            new_total = await accumulate_play_time(db, cid, 60)
            self.assertEqual(new_total, 60)
            await db._db.close()
        _run(_check())

    def test_repeated_increment_accumulates(self):
        async def _check():
            from engine.jedi_gating import accumulate_play_time
            db = await _fresh_db()
            cid = await _make_test_char(db)
            for expected in (60, 120, 180, 240):
                got = await accumulate_play_time(db, cid, 60)
                self.assertEqual(got, expected)
            await db._db.close()
        _run(_check())

    def test_zero_increment_no_op(self):
        async def _check():
            from engine.jedi_gating import accumulate_play_time
            db = await _fresh_db()
            cid = await _make_test_char(db)
            await accumulate_play_time(db, cid, 60)
            after_zero = await accumulate_play_time(db, cid, 0)
            self.assertEqual(after_zero, 60)
            await db._db.close()
        _run(_check())

    def test_negative_increment_rejected(self):
        async def _check():
            from engine.jedi_gating import accumulate_play_time
            db = await _fresh_db()
            cid = await _make_test_char(db)
            with self.assertRaises(ValueError):
                await accumulate_play_time(db, cid, -10)
            await db._db.close()
        _run(_check())

    def test_excessive_increment_capped(self):
        async def _check():
            from engine.jedi_gating import (
                accumulate_play_time, MAX_PLAYTIME_INCREMENT_SECONDS,
            )
            db = await _fresh_db()
            cid = await _make_test_char(db)
            # 1 hour requested; should cap at 600s.
            got = await accumulate_play_time(db, cid, 3600)
            self.assertEqual(got, MAX_PLAYTIME_INCREMENT_SECONDS)
            await db._db.close()
        _run(_check())

    def test_unknown_char_returns_minus_one(self):
        async def _check():
            from engine.jedi_gating import accumulate_play_time
            db = await _fresh_db()
            got = await accumulate_play_time(db, 99999, 60)
            self.assertEqual(got, -1)
            await db._db.close()
        _run(_check())


# ─────────────────────────────────────────────────────────────────────────────
# 5. Gate consultation helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestForceGateHelpers(unittest.TestCase):

    def test_gate_threshold_is_50_hours(self):
        from engine.jedi_gating import PLAY_TIME_GATE_SECONDS
        self.assertEqual(PLAY_TIME_GATE_SECONDS, 50 * 60 * 60)

    def test_fresh_char_gate_not_passed(self):
        from engine.jedi_gating import is_force_gate_passed
        self.assertFalse(is_force_gate_passed({"play_time_seconds": 0}))

    def test_partial_progress_not_passed(self):
        from engine.jedi_gating import is_force_gate_passed
        # 49 hours = 176,400 seconds; one hour shy of the gate.
        self.assertFalse(is_force_gate_passed({
            "play_time_seconds": 49 * 3600,
        }))

    def test_exact_threshold_passed(self):
        from engine.jedi_gating import (
            is_force_gate_passed, PLAY_TIME_GATE_SECONDS,
        )
        self.assertTrue(is_force_gate_passed({
            "play_time_seconds": PLAY_TIME_GATE_SECONDS,
        }))

    def test_above_threshold_passed(self):
        from engine.jedi_gating import is_force_gate_passed
        self.assertTrue(is_force_gate_passed({
            "play_time_seconds": 100 * 3600,
        }))

    def test_missing_column_returns_false(self):
        """A v17 DB row (no column) should report not-passed, not crash
        and not silently report 'passed'."""
        from engine.jedi_gating import is_force_gate_passed
        self.assertFalse(is_force_gate_passed({}))
        self.assertFalse(is_force_gate_passed({"name": "Tester"}))

    def test_garbage_value_returns_false(self):
        from engine.jedi_gating import is_force_gate_passed
        self.assertFalse(is_force_gate_passed({
            "play_time_seconds": "not a number",
        }))

    def test_progress_fraction(self):
        from engine.jedi_gating import (
            force_gate_progress, PLAY_TIME_GATE_SECONDS,
        )
        self.assertEqual(force_gate_progress({"play_time_seconds": 0}), 0.0)
        self.assertEqual(
            force_gate_progress({
                "play_time_seconds": PLAY_TIME_GATE_SECONDS // 2,
            }),
            0.5,
        )
        self.assertEqual(
            force_gate_progress({
                "play_time_seconds": PLAY_TIME_GATE_SECONDS,
            }),
            1.0,
        )
        # Caps at 1.0 even past gate
        self.assertEqual(
            force_gate_progress({
                "play_time_seconds": PLAY_TIME_GATE_SECONDS * 5,
            }),
            1.0,
        )


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tick handler — fake-session integration
# ─────────────────────────────────────────────────────────────────────────────

class _FakeSession:
    """Minimal stand-in for server.session.Session for tick tests."""
    def __init__(self, char_id, in_game=True, idle_for_seconds=0):
        self.id = char_id  # convenient
        self.character = {"id": char_id, "play_time_seconds": 0}
        self._idle_for = idle_for_seconds
        self._in_game = in_game
        # Attribute the real Session has; we set it but the handler
        # uses is_idle_for() not last_activity directly.
        self.last_activity = time.time() - idle_for_seconds

    @property
    def is_in_game(self):
        return self._in_game

    def is_idle_for(self, threshold):
        return self._idle_for > threshold


class _FakeSessionMgr:
    def __init__(self, sessions):
        self._sessions = sessions

    @property
    def all(self):
        return list(self._sessions)


class TestPlaytimeHeartbeatTick(unittest.TestCase):

    def _make_ctx(self, db, sessions):
        from server.tick_scheduler import TickContext
        return TickContext(
            server=MagicMock(),
            db=db,
            session_mgr=_FakeSessionMgr(sessions),
            tick_count=60,
            ships_in_space=[],
        )

    def test_active_session_gets_bumped(self):
        async def _check():
            from server.tick_handlers_progression import (
                playtime_heartbeat_tick,
            )
            db = await _fresh_db()
            cid = await _make_test_char(db)
            sess = _FakeSession(cid, in_game=True, idle_for_seconds=10)
            ctx = self._make_ctx(db, [sess])

            await playtime_heartbeat_tick(ctx)

            rows = await db._db.execute_fetchall(
                "SELECT play_time_seconds FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["play_time_seconds"], 60)
            # In-memory cache should also reflect the bump
            self.assertEqual(sess.character["play_time_seconds"], 60)
            await db._db.close()
        _run(_check())

    def test_idle_session_skipped(self):
        async def _check():
            from server.tick_handlers_progression import (
                playtime_heartbeat_tick, IDLE_THRESHOLD_SECONDS,
            )
            db = await _fresh_db()
            cid = await _make_test_char(db)
            # Idle for longer than threshold
            sess = _FakeSession(cid, in_game=True,
                                idle_for_seconds=IDLE_THRESHOLD_SECONDS + 10)
            ctx = self._make_ctx(db, [sess])

            await playtime_heartbeat_tick(ctx)

            rows = await db._db.execute_fetchall(
                "SELECT play_time_seconds FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["play_time_seconds"], 0)
            await db._db.close()
        _run(_check())

    def test_pre_login_session_skipped(self):
        async def _check():
            from server.tick_handlers_progression import (
                playtime_heartbeat_tick,
            )
            db = await _fresh_db()
            cid = await _make_test_char(db)
            sess = _FakeSession(cid, in_game=False, idle_for_seconds=0)
            ctx = self._make_ctx(db, [sess])

            await playtime_heartbeat_tick(ctx)

            rows = await db._db.execute_fetchall(
                "SELECT play_time_seconds FROM characters WHERE id=?",
                (cid,),
            )
            self.assertEqual(rows[0]["play_time_seconds"], 0)
            await db._db.close()
        _run(_check())

    def test_mixed_sessions(self):
        """Two active, one idle, one pre-login: only the two actives bump."""
        async def _check():
            from server.tick_handlers_progression import (
                playtime_heartbeat_tick, IDLE_THRESHOLD_SECONDS,
            )
            db = await _fresh_db()
            # Three test chars
            await db._db.execute(
                "INSERT INTO accounts(username, password_hash) VALUES('a', 'x')"
            )
            for n in ("Active1", "Active2", "Idle1", "PreLogin1"):
                await db._db.execute(
                    "INSERT INTO characters(account_id, name) VALUES(1, ?)",
                    (n,),
                )
            await db._db.commit()
            rows = await db._db.execute_fetchall(
                "SELECT id, name FROM characters ORDER BY id"
            )
            ids = {r["name"]: r["id"] for r in rows}

            sessions = [
                _FakeSession(ids["Active1"], in_game=True, idle_for_seconds=5),
                _FakeSession(ids["Active2"], in_game=True, idle_for_seconds=30),
                _FakeSession(ids["Idle1"], in_game=True,
                             idle_for_seconds=IDLE_THRESHOLD_SECONDS + 1),
                _FakeSession(ids["PreLogin1"], in_game=False),
            ]
            ctx = self._make_ctx(db, sessions)
            await playtime_heartbeat_tick(ctx)

            for name in ("Active1", "Active2"):
                rows = await db._db.execute_fetchall(
                    "SELECT play_time_seconds FROM characters WHERE id=?",
                    (ids[name],),
                )
                self.assertEqual(
                    rows[0]["play_time_seconds"], 60,
                    f"{name} should have been bumped",
                )
            for name in ("Idle1", "PreLogin1"):
                rows = await db._db.execute_fetchall(
                    "SELECT play_time_seconds FROM characters WHERE id=?",
                    (ids[name],),
                )
                self.assertEqual(
                    rows[0]["play_time_seconds"], 0,
                    f"{name} should NOT have been bumped",
                )
            await db._db.close()
        _run(_check())

    def test_empty_session_list_safe(self):
        async def _check():
            from server.tick_handlers_progression import (
                playtime_heartbeat_tick,
            )
            db = await _fresh_db()
            ctx = self._make_ctx(db, [])
            # Should not raise
            await playtime_heartbeat_tick(ctx)
            await db._db.close()
        _run(_check())

    def test_handler_registered_in_game_server(self):
        """Source-level guard: GameServer.__init__ should register
        playtime_heartbeat. If this trips, someone removed the
        registration without removing the import."""
        path = os.path.join(PROJECT_ROOT, "server", "game_server.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn(
            'register("playtime_heartbeat"', src,
            "playtime_heartbeat tick handler should be registered "
            "in GameServer.__init__",
        )
        self.assertIn(
            "playtime_heartbeat_tick", src,
            "playtime_heartbeat_tick should be imported in game_server.py",
        )


# ─────────────────────────────────────────────────────────────────────────────
# 7. CreationWizard.get_predisposition() integration
# ─────────────────────────────────────────────────────────────────────────────


class _MockReg:
    """Duck-typed registry stand-in (mirrors the pattern in
    tests/test_f8c1_chargen_chain_selection.py)."""
    def get(self, *a, **kw): return None
    def __getattr__(self, name): return lambda *a, **kw: None
    def skills_for_attribute(self, *a, **kw): return []


def _make_test_species(name="Human"):
    """Build a minimal Species dataclass for setting wizard state."""
    from engine.species import Species
    return Species(name=name)


class TestWizardIntegration(unittest.TestCase):

    def _make_wizard(self):
        """Build a CreationWizard with mock registries — same pattern
        as tests/test_f8c1_chargen_chain_selection.py."""
        from engine.creation_wizard import CreationWizard
        return CreationWizard(_MockReg(), _MockReg(), width=80)

    def test_no_species_no_backstory_zero(self):
        w = self._make_wizard()
        # No species set, empty background -> 0.0
        self.assertEqual(w.get_predisposition(rng_roll=0.0), 0.0)

    def test_with_species_only(self):
        w = self._make_wizard()
        w.engine.state.species = _make_test_species("Human")
        score = w.get_predisposition(rng_roll=0.0)
        # Human has weight 0.10 + 0 backstory + 0 roll = 0.10
        self.assertAlmostEqual(score, 0.10, places=6)

    def test_with_backstory_only(self):
        w = self._make_wizard()
        w.background = "I felt the Force calling to me from a young age."
        score = w.get_predisposition(rng_roll=0.0)
        # No species + force (0.10) + calling (0.05) = 0.15
        self.assertAlmostEqual(score, 0.15, places=6)

    def test_full_combination_in_unit_range(self):
        w = self._make_wizard()
        w.engine.state.species = _make_test_species("Miraluka")
        w.background = "Force jedi meditation visions destiny dreams"
        score = w.get_predisposition(rng_roll=0.5)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)
        # Miraluka 0.50 + cap 0.30 + roll 0.5 = 1.30 → ceiling clamps to 1.0
        self.assertEqual(score, 1.0)

    def test_method_signature(self):
        """rng_roll defaults to 0.0 so callers can omit it for
        deterministic test scoring."""
        import inspect
        from engine.creation_wizard import CreationWizard
        sig = inspect.signature(CreationWizard.get_predisposition)
        self.assertIn("rng_roll", sig.parameters)
        self.assertEqual(sig.parameters["rng_roll"].default, 0.0)


# ─────────────────────────────────────────────────────────────────────────────
# 8. Source-level marker for the drop
# ─────────────────────────────────────────────────────────────────────────────

class TestModuleSelfDocs(unittest.TestCase):

    def test_jedi_gating_module_references_design(self):
        path = os.path.join(PROJECT_ROOT, "engine", "jedi_gating.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("PG.3.gates.a", src)
        self.assertIn(
            "progression_gates_and_consequences_design_v1.md", src,
        )

    def test_tick_handler_module_references_design(self):
        path = os.path.join(
            PROJECT_ROOT, "server", "tick_handlers_progression.py",
        )
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("playtime_heartbeat_tick", src)
        self.assertIn("50-hour", src)

    def test_chargen_finalize_stamps_predisposition(self):
        """game_server.py chargen finalize should call get_predisposition
        and persist via UPDATE."""
        path = os.path.join(PROJECT_ROOT, "server", "game_server.py")
        with open(path, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("PG.3.gates.a", src)
        self.assertIn("force_predisposition", src)
        self.assertIn("get_predisposition", src)


if __name__ == "__main__":
    unittest.main()
