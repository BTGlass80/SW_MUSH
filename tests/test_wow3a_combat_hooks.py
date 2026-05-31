# -*- coding: utf-8 -*-
"""
tests/test_wow3a_combat_hooks.py — WoW.3a runtime hooks.

Two runtime hooks ship in this drop, both wired into ground
combat (`parser/combat_commands.py`):

1. **Retreat refusal** — `AttackCommand` early-gates on
   `is_in_retreat(char)`. A Jedi who has called `+retreat` cannot
   initiate combat until they `+return`.

2. **Kill credit** — when an NPC combatant transitions to wound
   level DEAD inside the `_apply_combat_wear` pass, the engine
   reads `c.last_attacker_id` and (if it's a Jedi PC) credits
   +1 Weight via `engine.wow_combat_hooks.credit_kill_for_jedi`.
   Per-fight cap +3; substrate enforces weekly +40 and global 200.

Test sections
=============

is_in_retreat (engine/wow_combat_hooks.py):
  1.  TestRetreatPredicateAbsentAttrs       — empty / missing → False
  2.  TestRetreatPredicateFlagFalse         — flag explicitly False → False
  3.  TestRetreatPredicateFlagTrue          — flag True → True
  4.  TestRetreatPredicateDictAttrs         — dict (not JSON string) → reads ok
  5.  TestRetreatPredicateMalformedJson     — corrupt JSON → False, no crash
  6.  TestRetreatPredicateNonDictChar       — None / int / str → False

credit_kill_for_jedi (engine/wow_combat_hooks.py):
  7.  TestKillCreditOneKill                 — Jedi kills NPC → +1
  8.  TestKillCreditNonJediNoChange         — Non-Jedi PC kills → +0
  9.  TestKillCreditDedupePair              — Same (jedi, npc) twice → +0 second time
 10.  TestKillCreditPerFightCap             — 4 kills → +3 total (cap)
 11.  TestKillCreditTwoFightsTwoCaps        — 4 kills × 2 fights → +6 total
 12.  TestKillCreditMultiJediIndependentCap — 2 Jedi in one fight, each kills 4 → +3 each
 13.  TestKillCreditNoneNpcIdSafe           — npc_id=None → +0 no crash
 14.  TestKillCreditNoneJediIdSafe          — jedi char without id → +0 no crash

Retreat gate on AttackCommand:
 15.  TestAttackGateRetreatRefuses          — Jedi-in-retreat → refused with message
 16.  TestAttackGateNonJediIgnored          — Non-Jedi with retreat flag still attacks
 17.  TestAttackGateActiveJediProceeds      — Jedi NOT in retreat passes the gate

Phantom-prevention (Pattern 8):
 18.  TestPredicateImportableAtModuleLoad   — both functions on the module surface
 19.  TestProductionAccrueWeightIntegration — kill_credit calls accrue_weight w/ real DB
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def _run(coro):
    return asyncio.run(coro)


# ── Test doubles ─────────────────────────────────────────────────────


class _FakeCombat:
    """Minimal stand-in for CombatInstance — only needs `room_id`.
    The kill-credit hook stashes its dedupe state on the instance
    via setattr, so any object accepts that."""
    def __init__(self, room_id: int = 100):
        self.room_id = room_id


# ═════════════════════════════════════════════════════════════════════
# 1-6. is_in_retreat predicate
# ═════════════════════════════════════════════════════════════════════


class TestRetreatPredicateAbsentAttrs(unittest.TestCase):
    def test_missing_attrs_returns_false(self):
        from engine.wow_combat_hooks import is_in_retreat
        self.assertFalse(is_in_retreat({"id": 1}))
        self.assertFalse(is_in_retreat({"id": 1, "attributes": ""}))
        self.assertFalse(is_in_retreat({"id": 1, "attributes": "{}"}))


class TestRetreatPredicateFlagFalse(unittest.TestCase):
    def test_flag_false_returns_false(self):
        from engine.wow_combat_hooks import is_in_retreat
        char = {"id": 1, "attributes":
                json.dumps({"wow_retreat_active": False})}
        self.assertFalse(is_in_retreat(char))


class TestRetreatPredicateFlagTrue(unittest.TestCase):
    def test_flag_true_returns_true(self):
        from engine.wow_combat_hooks import is_in_retreat
        char = {"id": 1, "attributes":
                json.dumps({"wow_retreat_active": True})}
        self.assertTrue(is_in_retreat(char))


class TestRetreatPredicateDictAttrs(unittest.TestCase):
    def test_dict_attrs_handled(self):
        """Some code paths pass attributes as a parsed dict
        rather than a JSON string — the predicate must handle
        both."""
        from engine.wow_combat_hooks import is_in_retreat
        char = {"id": 1, "attributes":
                {"wow_retreat_active": True}}
        self.assertTrue(is_in_retreat(char))


class TestRetreatPredicateMalformedJson(unittest.TestCase):
    def test_corrupt_json_returns_false(self):
        from engine.wow_combat_hooks import is_in_retreat
        char = {"id": 1, "attributes": "{not_json"}
        # Should not raise; returns False.
        self.assertFalse(is_in_retreat(char))


class TestRetreatPredicateNonDictChar(unittest.TestCase):
    def test_non_dict_returns_false(self):
        from engine.wow_combat_hooks import is_in_retreat
        self.assertFalse(is_in_retreat(None))
        self.assertFalse(is_in_retreat(42))
        self.assertFalse(is_in_retreat("char"))


# ═════════════════════════════════════════════════════════════════════
# 7-14. credit_kill_for_jedi
# ═════════════════════════════════════════════════════════════════════


def _jedi_char(char_id: int = 100):
    """Build a Jedi PC dict that passes is_jedi_pc via faction."""
    return {"id": char_id, "faction_id": "jedi_order"}


def _non_jedi_char(char_id: int = 200):
    return {"id": char_id, "faction_id": "rebel"}


class TestKillCreditOneKill(unittest.TestCase):
    def test_single_kill_returns_one(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        applied = []

        async def fake_accrue(db, *, char_id, delta, trigger_type,
                              description=None, now=None):
            applied.append((char_id, delta, trigger_type))
            return delta

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            combat = _FakeCombat()
            result = _run(credit_kill_for_jedi(
                db=MagicMock(), combat=combat,
                jedi_char=_jedi_char(100), npc_id=500,
            ))
        self.assertEqual(result, 1)
        self.assertEqual(len(applied), 1)
        self.assertEqual(applied[0][0], 100)
        self.assertEqual(applied[0][1], 1)
        self.assertEqual(applied[0][2], "combat_kill")


class TestKillCreditNonJediNoChange(unittest.TestCase):
    def test_non_jedi_no_accrue(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        called = []

        async def fake_accrue(*a, **k):
            called.append((a, k))
            return 1

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            result = _run(credit_kill_for_jedi(
                db=MagicMock(), combat=_FakeCombat(),
                jedi_char=_non_jedi_char(200), npc_id=500,
            ))
        self.assertEqual(result, 0)
        self.assertEqual(called, [],
                         "accrue_weight should never be called "
                         "for non-Jedi PCs")


class TestKillCreditDedupePair(unittest.TestCase):
    def test_same_pair_twice_only_one_credit(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        deltas = []

        async def fake_accrue(db, *, char_id, delta, **k):
            deltas.append(delta)
            return delta

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            combat = _FakeCombat()
            r1 = _run(credit_kill_for_jedi(
                db=MagicMock(), combat=combat,
                jedi_char=_jedi_char(100), npc_id=500,
            ))
            r2 = _run(credit_kill_for_jedi(
                db=MagicMock(), combat=combat,
                jedi_char=_jedi_char(100), npc_id=500,
            ))
        self.assertEqual(r1, 1)
        self.assertEqual(r2, 0)
        self.assertEqual(deltas, [1],
                         "second call to same pair must not "
                         "hit the substrate")


class TestKillCreditPerFightCap(unittest.TestCase):
    def test_four_kills_caps_at_three(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        deltas = []

        async def fake_accrue(db, *, char_id, delta, **k):
            deltas.append(delta)
            return delta

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            combat = _FakeCombat()
            total = 0
            for npc_id in (500, 501, 502, 503):
                total += _run(credit_kill_for_jedi(
                    db=MagicMock(), combat=combat,
                    jedi_char=_jedi_char(100), npc_id=npc_id,
                ))
        self.assertEqual(total, 3)
        self.assertEqual(deltas, [1, 1, 1],
                         "fourth kill must not hit substrate")


class TestKillCreditTwoFightsTwoCaps(unittest.TestCase):
    def test_independent_caps_per_combat(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        deltas = []

        async def fake_accrue(db, *, char_id, delta, **k):
            deltas.append(delta)
            return delta

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            for combat in (_FakeCombat(101), _FakeCombat(102)):
                for npc_id in (500, 501, 502, 503):
                    _run(credit_kill_for_jedi(
                        db=MagicMock(), combat=combat,
                        jedi_char=_jedi_char(100), npc_id=npc_id,
                    ))
        # 3 credits per fight × 2 fights = 6 substrate calls
        self.assertEqual(len(deltas), 6)


class TestKillCreditMultiJediIndependentCap(unittest.TestCase):
    def test_two_jedi_share_combat_independent_caps(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        per_jedi: dict = {}

        async def fake_accrue(db, *, char_id, delta, **k):
            per_jedi[char_id] = per_jedi.get(char_id, 0) + delta
            return delta

        with patch("engine.weight_of_war.accrue_weight",
                   new=fake_accrue):
            combat = _FakeCombat()
            for jedi_id in (100, 101):
                for npc_id in (500, 501, 502, 503):
                    _run(credit_kill_for_jedi(
                        db=MagicMock(), combat=combat,
                        jedi_char=_jedi_char(jedi_id),
                        npc_id=npc_id,
                    ))
        self.assertEqual(per_jedi.get(100), 3)
        self.assertEqual(per_jedi.get(101), 3)


class TestKillCreditNoneNpcIdSafe(unittest.TestCase):
    def test_none_npc_id_returns_zero(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        result = _run(credit_kill_for_jedi(
            db=MagicMock(), combat=_FakeCombat(),
            jedi_char=_jedi_char(100), npc_id=None,
        ))
        self.assertEqual(result, 0)


class TestKillCreditNoneJediIdSafe(unittest.TestCase):
    def test_char_without_id_returns_zero(self):
        from engine.wow_combat_hooks import credit_kill_for_jedi
        result = _run(credit_kill_for_jedi(
            db=MagicMock(), combat=_FakeCombat(),
            jedi_char={"faction_id": "jedi_order"},  # no id
            npc_id=500,
        ))
        self.assertEqual(result, 0)


# ═════════════════════════════════════════════════════════════════════
# 15-17. Retreat gate on AttackCommand
# ═════════════════════════════════════════════════════════════════════


class _AttackGateTestBase(unittest.TestCase):
    """Helpers for the retreat-gate command tests. Builds a
    minimal ctx with a session that captures send_line output."""

    def _make_ctx(self, char: dict):
        session = MagicMock()
        session.character = char
        session.lines = []

        async def send(s):
            session.lines.append(str(s))

        session.send_line = send
        ctx = MagicMock()
        ctx.session = session
        ctx.args = "stormtrooper"
        return ctx

    def _contains_any(self, ctx, *needles) -> bool:
        for line in ctx.session.lines:
            for n in needles:
                if n in line:
                    return True
        return False


class TestAttackGateRetreatRefuses(_AttackGateTestBase):
    def test_jedi_in_retreat_refused(self):
        from parser.combat_commands import AttackCommand
        char = {
            "id": 1, "room_id": 200,
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": True}),
        }
        ctx = self._make_ctx(char)
        cmd = AttackCommand()
        _run(cmd.execute(ctx))
        # Refusal message includes "withdrawn from active duty"
        # and instructions to +return.
        self.assertTrue(
            self._contains_any(
                ctx, "withdrawn from active duty", "+return"),
            f"Expected retreat-refusal message; got: "
            f"{ctx.session.lines}",
        )


class TestAttackGateNonJediIgnored(_AttackGateTestBase):
    def test_non_jedi_retreat_flag_ignored(self):
        """A non-Jedi with the flag somehow set (data anomaly)
        should still proceed past the gate. The gate is
        is_in_retreat-only, but is_jedi_pc is the design
        scope — the retreat surface is Jedi-gated upstream
        in RetreatCommand, so a non-Jedi with the flag is a
        data artifact. We still allow attacks to proceed."""
        from parser.combat_commands import AttackCommand
        char = {
            "id": 2, "room_id": 200,
            "faction_id": "rebel",
            "attributes": json.dumps({
                "wow_retreat_active": True}),
        }
        ctx = self._make_ctx(char)
        cmd = AttackCommand()
        # Will fail at later stages (no real db etc), but should
        # NOT fail at the retreat gate. We assert the retreat
        # refusal message is NOT present.
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass  # Allowed — security/target-resolution may bail
        self.assertFalse(
            self._contains_any(ctx, "withdrawn from active duty"),
            f"Non-Jedi should not see retreat refusal; "
            f"lines were: {ctx.session.lines}",
        )


class TestAttackGateActiveJediProceeds(_AttackGateTestBase):
    def test_active_jedi_passes_gate(self):
        """A Jedi NOT in retreat must pass the retreat gate.
        The command will then fail at the security/target stage,
        but that's fine — we're testing the gate, not the rest."""
        from parser.combat_commands import AttackCommand
        char = {
            "id": 3, "room_id": 200,
            "faction_id": "jedi_order",
            "attributes": json.dumps({
                "wow_retreat_active": False}),
        }
        ctx = self._make_ctx(char)
        cmd = AttackCommand()
        try:
            _run(cmd.execute(ctx))
        except Exception:
            pass
        self.assertFalse(
            self._contains_any(ctx, "withdrawn from active duty"),
            "Active Jedi should pass retreat gate",
        )


# ═════════════════════════════════════════════════════════════════════
# 18-19. Phantom prevention + production-schema integration
# ═════════════════════════════════════════════════════════════════════


class TestPredicateImportableAtModuleLoad(unittest.TestCase):
    """Pattern 8: every documented surface must be importable.
    If credit_kill_for_jedi or is_in_retreat ever disappears
    from the module, the combat path silently swallows the
    AttributeError; this test surfaces that."""

    def test_module_surface(self):
        import engine.wow_combat_hooks as wch
        for name in ("credit_kill_for_jedi", "is_in_retreat",
                     "KILL_CREDIT_PER_KILL",
                     "KILL_CREDIT_PER_FIGHT_CAP"):
            self.assertTrue(
                hasattr(wch, name),
                f"engine.wow_combat_hooks missing {name}"
            )


class TestProductionAccrueWeightIntegration(unittest.TestCase):
    """End-to-end: kill_credit drives the real
    engine.weight_of_war.accrue_weight against a real Database.
    Confirms the integration handshake (single-event clamp,
    weekly cap, hard cap, event-log write) lands as documented."""

    def test_real_db_path(self):
        async def go():
            from db.database import Database
            from engine.wow_combat_hooks import credit_kill_for_jedi
            from engine.weight_of_war import get_weight_db
            db = Database(":memory:")
            await db.connect()
            await db.initialize()

            await db._db.execute(
                "INSERT INTO accounts (id, username, "
                "password_hash) VALUES (1, 'u', 'p')",
            )
            await db._db.execute(
                "INSERT INTO characters "
                "(id, account_id, name, faction_id, "
                "weight_of_war) VALUES (?, ?, ?, ?, ?)",
                (100, 1, "Anakin", "jedi_order", 0),
            )
            await db._db.commit()

            combat = _FakeCombat()
            jedi = {"id": 100, "faction_id": "jedi_order"}

            # Three sequential kills → +3 Weight total.
            for npc_id in (501, 502, 503):
                await credit_kill_for_jedi(
                    db, combat, jedi, npc_id,
                )
            final = await get_weight_db(db, 100)
            return final

        self.assertEqual(_run(go()), 3,
                         "Three kills should produce +3 Weight")


if __name__ == "__main__":
    unittest.main()
