# -*- coding: utf-8 -*-
"""
tests/test_fun2_combat_cp.py — early-game combat CP faucet (fun2-combat-cp, 2026-06-25).

Pins engine/combat_cp.py + the wiring in parser/combat_commands.py:
  * first 5 kills each grant +1 CP (counter increments, total CP rises by 5);
  * the 6th kill grants 0 CP (faucet sealed);
  * each award is tagged "early_combat" (the cp_income telemetry tag);
  * a CP-grant failure (award_milestone_cp dropped) does NOT break the kill
    (counter stays un-incremented; function returns None, no exception raised);
  * a zero cap (tunable = 0) immediately seals the faucet;
  * the seam helper _award_early_combat_cp fires for a dead NPC and sends
    the player-visible "+1 CP" line.
"""
from __future__ import annotations

import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import asyncio

from engine import combat_cp as cc


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ── Fakes ────────────────────────────────────────────────────────────────────

class _FakeDB:
    """Minimal DB stub — tracks CP add calls and saves."""

    def __init__(self):
        self.cp_calls: list[tuple[int, int]] = []   # (char_id, delta)
        self.saved: dict = {}

    async def cp_add_character_points(self, char_id: int, cp: int):
        self.cp_calls.append((char_id, cp))

    async def save_character(self, cid, **fields):
        self.saved.update(fields)


class _DroppingDB(_FakeDB):
    """DB stub whose cp_add raises, so award_milestone_cp returns dropped=True."""

    async def cp_add_character_points(self, char_id: int, cp: int):
        raise RuntimeError("DB write failed (simulated)")


def _char(attrs=None, char_id=7):
    return {
        "id": char_id,
        "name": "Kes Dameron",
        "attributes": json.dumps(attrs or {}),
    }


# ── Unit tests for engine/combat_cp.py ───────────────────────────────────────

class TestEarlyCPAward(unittest.TestCase):

    def test_first_kill_awards_one_cp(self):
        db = _FakeDB()
        char = _char()
        out = _run(cc.award_early_combat_cp(db, char))
        self.assertIsNotNone(out)
        self.assertEqual(out["cp_awarded"], 1)
        self.assertEqual(out["kills_credited"], 1)
        self.assertFalse(out["faucet_sealed"])

    def test_counter_persisted_after_award(self):
        db = _FakeDB()
        char = _char()
        _run(cc.award_early_combat_cp(db, char))
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs[cc.EARLY_CP_KEY]["kills"], 1)

    def test_five_kills_award_five_cp_total(self):
        """The first 5 kills each grant +1 CP; counter must reach 5."""
        db = _FakeDB()
        char = _char()
        for i in range(1, 6):
            out = _run(cc.award_early_combat_cp(db, char))
            self.assertIsNotNone(out, f"kill {i} should award CP")
            self.assertEqual(out["cp_awarded"], 1)
            self.assertEqual(out["kills_credited"], i)
        # Total CP granted == 5
        total = sum(delta for _, delta in db.cp_calls)
        self.assertEqual(total, 5)

    def test_fifth_kill_seals_faucet(self):
        db = _FakeDB()
        char = _char()
        for _ in range(4):
            _run(cc.award_early_combat_cp(db, char))
        out = _run(cc.award_early_combat_cp(db, char))
        self.assertTrue(out["faucet_sealed"])
        self.assertEqual(out["kills_credited"], 5)

    def test_sixth_kill_grants_zero_cp(self):
        """After 5 kills the faucet is dry — 6th call returns None."""
        db = _FakeDB()
        char = _char()
        for _ in range(5):
            _run(cc.award_early_combat_cp(db, char))
        out = _run(cc.award_early_combat_cp(db, char))
        self.assertIsNone(out)
        # CP calls must still be exactly 5 (the 6th never hit the funnel)
        self.assertEqual(len(db.cp_calls), 5)

    def test_award_tagged_early_combat(self):
        """CP grants must use the 'early_combat' tag so telemetry can bucket them."""
        db = _FakeDB()
        char = _char()
        # Intercept award_milestone_cp to verify the reason tag.
        calls = []

        original = cc.award_early_combat_cp  # keep reference

        async def _patched(db_, char_):
            from engine.cp_engine import CPEngine
            orig_award = CPEngine.award_milestone_cp

            async def _capture(self, db__, cid, cp, reason=""):
                calls.append(reason)
                return await orig_award(self, db__, cid, cp, reason=reason)

            with patch.object(CPEngine, "award_milestone_cp", _capture):
                return await original(db_, char_)

        _run(_patched(db, char))
        self.assertTrue(calls, "award_milestone_cp must have been called")
        self.assertEqual(calls[0], "early_combat",
                         "reason tag must be 'early_combat'")

    def test_dropped_award_does_not_increment_counter(self):
        """If award_milestone_cp drops the grant, the kill counter must NOT advance."""
        db = _DroppingDB()
        char = _char()
        out = _run(cc.award_early_combat_cp(db, char))
        self.assertIsNone(out, "a dropped grant must return None")
        # Counter must still be 0
        attrs = json.loads(char["attributes"])
        blob = attrs.get(cc.EARLY_CP_KEY, {})
        self.assertEqual(blob.get("kills", 0), 0,
                         "counter must not advance when the CP grant was dropped")

    def test_dropped_award_does_not_raise(self):
        """A CP-grant failure must never propagate — fail-open invariant."""
        db = _DroppingDB()
        char = _char()
        # Must not raise:
        _run(cc.award_early_combat_cp(db, char))

    def test_zero_cap_seals_immediately(self):
        """combat.early_cp_kill_cap: 0 → faucet dry from the start."""
        db = _FakeDB()
        char = _char()
        with patch("engine.tunables.get_tunable", return_value=0):
            out = _run(cc.award_early_combat_cp(db, char))
        self.assertIsNone(out)
        self.assertEqual(len(db.cp_calls), 0)

    def test_get_early_cp_kills_reads_counter(self):
        db = _FakeDB()
        char = _char()
        self.assertEqual(cc.get_early_cp_kills({}), 0)
        _run(cc.award_early_combat_cp(db, char))
        _run(cc.award_early_combat_cp(db, char))
        attrs = json.loads(char["attributes"])
        self.assertEqual(cc.get_early_cp_kills(attrs), 2)

    def test_corrupt_counter_treated_as_zero(self):
        """A corrupted blob value must not crash — self-heals to 0 then 1."""
        db = _FakeDB()
        char = _char({cc.EARLY_CP_KEY: {"kills": "not-an-int"}})
        out = _run(cc.award_early_combat_cp(db, char))
        self.assertIsNotNone(out)
        self.assertEqual(out["kills_credited"], 1)


# ── Seam integration: _award_early_combat_cp in combat_commands.py ───────────

class _FakeSess:
    def __init__(self, char):
        self.character = char
        self.lines: list[str] = []

    async def send_line(self, text):
        self.lines.append(text)


class _FakeMgr:
    def __init__(self, killer_id, sess):
        self._kid = killer_id
        self._sess = sess

    def find_by_character(self, cid):
        return self._sess if int(cid) == self._kid else None


def _dead_npc_combatant(npc_id=99, killer_id=5):
    from engine.character import WoundLevel
    return types.SimpleNamespace(
        id=npc_id, is_npc=True, name="Weequay Thug",
        last_attacker_id=killer_id,
        char=types.SimpleNamespace(wound_level=WoundLevel.DEAD),
    )


class TestSeamWiring(unittest.TestCase):
    """_award_early_combat_cp fires correctly from the pre_npcs snapshot."""

    def _run_seam(self, *, pre, combatants, killer_id=5, online=True,
                  char_attrs=None):
        from parser.combat_commands import _award_early_combat_cp

        db = _FakeDB()
        killer = _char(char_attrs, char_id=killer_id)
        sess = _FakeSess(killer)
        mgr = _FakeMgr(killer_id, sess) if online else _FakeMgr(-1, sess)
        combat = types.SimpleNamespace(combatants=combatants)
        ctx = types.SimpleNamespace(db=db, session_mgr=mgr)
        _run(_award_early_combat_cp(combat, ctx, pre))
        return killer, sess, db

    def test_dead_npc_awards_cp_and_sends_line(self):
        npc = _dead_npc_combatant()
        killer, sess, db = self._run_seam(pre=[npc], combatants={})
        self.assertEqual(len(db.cp_calls), 1, "exactly one CP grant should fire")
        self.assertTrue(sess.lines, "the killer must receive a '+1 CP' message")
        self.assertIn("+1 CP", sess.lines[0])

    def test_survivor_npc_does_not_award(self):
        """NPC still in combat.combatants → not killed → no award."""
        npc = _dead_npc_combatant()
        killer, sess, db = self._run_seam(pre=[npc],
                                          combatants={npc.id: npc})
        self.assertEqual(len(db.cp_calls), 0)
        self.assertFalse(sess.lines)

    def test_offline_killer_does_not_award(self):
        npc = _dead_npc_combatant()
        killer, sess, db = self._run_seam(pre=[npc], combatants={},
                                          online=False)
        self.assertEqual(len(db.cp_calls), 0)

    def test_cap_exhausted_sixth_kill_no_award(self):
        """After 5 prior kills the 6th NPC death must yield no CP."""
        pre_kills = {cc.EARLY_CP_KEY: {"kills": 5}}
        npc = _dead_npc_combatant()
        killer, sess, db = self._run_seam(pre=[npc], combatants={},
                                          char_attrs=pre_kills)
        self.assertEqual(len(db.cp_calls), 0,
                         "faucet sealed after cap — no CP for kill 6")
        self.assertFalse(sess.lines)

    def test_faucet_sealed_message_sent_on_fifth_kill(self):
        """The final-kill message should mention the bonus is complete."""
        pre_kills = {cc.EARLY_CP_KEY: {"kills": 4}}
        npc = _dead_npc_combatant()
        killer, sess, db = self._run_seam(pre=[npc], combatants={},
                                          char_attrs=pre_kills)
        self.assertEqual(len(db.cp_calls), 1)
        self.assertTrue(sess.lines)
        self.assertIn("Early combat bonus complete", sess.lines[0])

    def test_no_pre_npcs_is_noop(self):
        """Empty pre_npcs must not crash and awards nothing."""
        from parser.combat_commands import _award_early_combat_cp
        db = _FakeDB()
        combat = types.SimpleNamespace(combatants={})
        ctx = types.SimpleNamespace(db=db, session_mgr=None)
        _run(_award_early_combat_cp(combat, ctx, []))
        self.assertEqual(len(db.cp_calls), 0)


# ── Wiring guard: both resolve_round call sites present ──────────────────────

class TestWiringGuard(unittest.TestCase):

    def _combat_src(self):
        return (PROJECT_ROOT / "parser" / "combat_commands.py").read_text(
            encoding="utf-8"
        )

    def test_early_cp_hook_called_at_both_resolve_sites(self):
        src = self._combat_src()
        count = src.count(
            "await _award_early_combat_cp(combat, ctx, _pre_npcs)"
        )
        self.assertEqual(
            count, 2,
            "the early-combat CP hook must fire at BOTH resolve_round call "
            "sites (normal + admin)"
        )

    def test_engine_module_exists(self):
        mod = PROJECT_ROOT / "engine" / "combat_cp.py"
        self.assertTrue(mod.exists(), "engine/combat_cp.py must exist")

    def test_tunable_registered_in_yaml(self):
        yaml_text = (PROJECT_ROOT / "data" / "tunables.yaml").read_text(
            encoding="utf-8"
        )
        self.assertIn("combat.early_cp_kill_cap", yaml_text)

    def test_engine_module_compiles(self):
        import py_compile
        py_compile.compile(
            str(PROJECT_ROOT / "engine" / "combat_cp.py"),
            doraise=True,
        )


if __name__ == "__main__":
    unittest.main()
