# -*- coding: utf-8 -*-
"""
tests/test_cities_phase7c_combat.py — Phase 7c city-guard
combat-round triggers (May 23 2026).

Closes the final design §7.2 engagement triggers on top of
Phase 7b (banished-entry):

  - **Attacked-a-citizen-in-this-combat-session** — guards
    engage characters that attacked a citizen during the
    current combat. Tracked via the new
    ``CombatInstance.attacks_made`` set, populated at every
    ``_resolve_attack`` entry (attempt counts, not just hit).
  - **Bountied-target-claimed-by-citizen-BH** — guards engage
    characters with active bounties claimed by a citizen of
    the guard's city. Folded into ``should_city_guard_engage``
    (on-entry) AND evaluated each combat round.

Test sections
=============

CombatInstance.attacks_made:
  1.  TestAttacksMadeInitiallyEmpty
  2.  TestAttacksMadeStampedOnAttack
  3.  TestAttacksMadeMultipleEntries

_has_bounty_claimed_by_citizen:
  4.  TestBountyNoOrg
  5.  TestBountyNoneClaimed
  6.  TestBountyClaimedByCitizen
  7.  TestBountyClaimedByOutsider
  8.  TestBountyClaimedByExpelledCitizen
  9.  TestBountyMultipleClaimsOneCitizen

should_city_guard_engage (Phase 7b + 7c merged):
 10.  TestEngageStillBanished        — Phase 7b path unchanged
 11.  TestEngageBountyTrigger        — new Phase 7c trigger
 12.  TestEngageBountyInGrace        — grace overrides bounty
 13.  TestEngageNeitherTrigger       — no engage when neither fires

should_engage_attacker_of_citizen:
 14.  TestAttackerNotInSet
 15.  TestAttackerNotAttackedCitizen
 16.  TestAttackerAttackedCitizen
 17.  TestAttackerCitizenAttackedCitizen — citizen-on-citizen also fires
 18.  TestAttackerInGrace            — grace overrides
 19.  TestAttackerNonGuardNpc        — no-op on non-guard

evaluate_combat_round_triggers:
 20.  TestEvalNoGuardsInRoom
 21.  TestEvalGuardAlreadyInCombat   — skipped
 22.  TestEvalAttackerTriggerFires
 23.  TestEvalBountyTriggerFires
 24.  TestEvalNeitherFires
 25.  TestEvalCityCachedAcrossGuards — same-city guards share lookup
 26.  TestEvalDissolvedCity          — skipped
 27.  TestEvalFailSoft               — broken DB returns []

End-to-end:
 28.  TestE2EAttackerOfCitizenTriggersGuard
 29.  TestE2EBountyTriggersGuardOnEntry

Per HANDOFF_MAY23_CITIES_PHASE7C_COMBAT.md.
"""

from __future__ import annotations

import json
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine import city_guard_runtime as cgr


DAY = 86400


# ─── _FakeDB ──────────────────────────────────────────────────────


class _FakeDB:
    def __init__(self):
        self.cities = {}
        self.bounties = []   # list[dict] of pc_bounties rows
        self.memberships = {}   # (char_id, org_id) -> dict
        self.banishments = {}   # (city_id, char_id) -> ts
        self.raise_on_bounty_read = False
        self.raise_on_membership_read = False

    def add_city(self, city_id, *, org_id=1, state="active",
                 grace_started_at=0.0):
        self.cities[city_id] = {
            "id": city_id, "name": f"city_{city_id}",
            "org_id": org_id, "state": state,
            "grace_started_at": grace_started_at,
        }

    def add_membership(self, char_id, org_id, *,
                       standing="good"):
        self.memberships[(int(char_id), int(org_id))] = {
            "char_id": char_id, "org_id": org_id,
            "rank_level": 1, "standing": standing,
        }

    def add_bounty(self, target_id, claimed_by, *,
                   state="claimed"):
        self.bounties.append({
            "id": len(self.bounties) + 1,
            "target_id": target_id,
            "claimed_by": claimed_by,
            "state": state,
        })

    def add_banishment(self, city_id, char_id):
        self.banishments[(city_id, char_id)] = (
            time.time() + 30 * DAY)

    async def fetchall(self, sql, params=()):
        s = " ".join(sql.split()).strip()
        # get_city_by_id
        if s.startswith("SELECT * FROM player_cities WHERE id = ?"):
            (cid,) = params
            c = self.cities.get(int(cid))
            return [dict(c)] if c else []
        # bounty query
        if s.startswith("SELECT claimed_by FROM pc_bounties WHERE target_id = ? AND state = 'claimed'"):
            if self.raise_on_bounty_read:
                raise RuntimeError("simulated bounty-read failure")
            (tid,) = params
            return [{"claimed_by": b["claimed_by"]}
                    for b in self.bounties
                    if b["target_id"] == int(tid)
                    and b["state"] == "claimed"
                    and b["claimed_by"] is not None]
        # is_banished
        if s.startswith("SELECT until FROM player_city_banishments WHERE city_id = ? AND char_id = ?"):
            cid, char_id = params
            until = self.banishments.get(
                (int(cid), int(char_id)))
            return [{"until": until}] if until else []
        return []

    async def get_membership(self, char_id, org_id):
        if self.raise_on_membership_read:
            raise RuntimeError("simulated membership failure")
        return self.memberships.get(
            (int(char_id), int(org_id)))


# ─── Row factories ────────────────────────────────────────────────


def _guard_row(npc_id, city_id):
    return {
        "id": npc_id, "name": f"Guard{npc_id}",
        "ai_config_json": json.dumps({
            "city_guard_for_city_id": city_id,
            "hostile": False,
        }),
        "template": "guard_basic",
        "current_room_id": 100,
        "wound_level": 0,
        "strength_dice": 3,
        "blaster_dice": 4,
    }


def _non_guard_row(npc_id):
    return {
        "id": npc_id, "name": f"Civilian{npc_id}",
        "ai_config_json": json.dumps({"hostile": False}),
    }


# ═════════════════════════════════════════════════════════════════════
# 1-3. CombatInstance.attacks_made
# ═════════════════════════════════════════════════════════════════════


class TestAttacksMadeInitiallyEmpty(unittest.TestCase):
    def test_field_exists_and_empty(self):
        from engine.combat import CombatInstance
        from engine.character import SkillRegistry
        ci = CombatInstance(room_id=1, skill_reg=SkillRegistry())
        self.assertEqual(ci.attacks_made, set())


class TestAttacksMadeStampedOnAttack(unittest.TestCase):
    """Smoke-check: when _resolve_attack runs (via a minimal
    combat setup), the (attacker, target) tuple is added."""

    def test_attempted_attack_recorded(self):
        from engine.combat import (
            CombatInstance, CombatAction, ActionType,
        )
        from engine.character import SkillRegistry
        from engine.character import Character
        ci = CombatInstance(room_id=1, skill_reg=SkillRegistry())

        # Build two minimal characters
        c1 = Character.from_db_dict({
            "id": 10, "name": "Attacker", "strength_dice": 3,
            "strength_pip": 0, "dexterity_dice": 3,
            "dexterity_pip": 0, "knowledge_dice": 2,
            "knowledge_pip": 0, "mechanical_dice": 2,
            "mechanical_pip": 0, "perception_dice": 2,
            "perception_pip": 0, "technical_dice": 2,
            "technical_pip": 0, "blaster_dice": 4,
            "blaster_pip": 0, "wound_level": 0, "stun_count": 0,
            "credits": 0, "skills_json": "{}",
            "attributes_json": "{}",
            "force_skills_json": "{}", "force_powers_json": "[]",
            "char_points": 0, "force_points": 1,
            "dark_side_points": 0,
        })
        c2 = Character.from_db_dict({
            "id": 20, "name": "Target", "strength_dice": 3,
            "strength_pip": 0, "dexterity_dice": 3,
            "dexterity_pip": 0, "knowledge_dice": 2,
            "knowledge_pip": 0, "mechanical_dice": 2,
            "mechanical_pip": 0, "perception_dice": 2,
            "perception_pip": 0, "technical_dice": 2,
            "technical_pip": 0, "blaster_dice": 4,
            "blaster_pip": 0, "wound_level": 0, "stun_count": 0,
            "credits": 0, "skills_json": "{}",
            "attributes_json": "{}",
            "force_skills_json": "{}", "force_powers_json": "[]",
            "char_points": 0, "force_points": 1,
            "dark_side_points": 0,
        })
        ci.add_combatant(c1)
        ci.add_combatant(c2)
        # Declare an attack from 10 → 20
        action = CombatAction(
            action_type=ActionType.ATTACK, target_id=20,
            skill="blaster", weapon_damage="4D",
        )
        # Invoke _resolve_attack directly
        actor = ci.combatants[10]
        ci._resolve_attack(actor, action, num_actions=1)
        # Verify the attempt was stamped
        self.assertIn((10, 20), ci.attacks_made)


class TestAttacksMadeMultipleEntries(unittest.TestCase):
    """Set semantics: repeated attacks dedupe."""

    def test_dedupe(self):
        from engine.combat import CombatInstance
        from engine.character import SkillRegistry
        ci = CombatInstance(room_id=1, skill_reg=SkillRegistry())
        ci.attacks_made.add((10, 20))
        ci.attacks_made.add((10, 20))
        ci.attacks_made.add((10, 30))
        self.assertEqual(len(ci.attacks_made), 2)
        self.assertIn((10, 20), ci.attacks_made)
        self.assertIn((10, 30), ci.attacks_made)


# ═════════════════════════════════════════════════════════════════════
# 4-9. _has_bounty_claimed_by_citizen
# ═════════════════════════════════════════════════════════════════════


class TestBountyNoOrg(unittest.IsolatedAsyncioTestCase):
    async def test_no_org_returns_false(self):
        db = _FakeDB()
        result = await cgr._has_bounty_claimed_by_citizen(
            db, target_char_id=100, city={"org_id": 0})
        self.assertFalse(result)


class TestBountyNoneClaimed(unittest.IsolatedAsyncioTestCase):
    async def test_no_bounty_returns_false(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        result = await cgr._has_bounty_claimed_by_citizen(
            db, 100, db.cities[1])
        self.assertFalse(result)


class TestBountyClaimedByCitizen(
        unittest.IsolatedAsyncioTestCase):
    async def test_citizen_claim_returns_true(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5)   # 99 is a citizen
        db.add_bounty(target_id=100, claimed_by=99)
        result = await cgr._has_bounty_claimed_by_citizen(
            db, 100, db.cities[1])
        self.assertTrue(result)


class TestBountyClaimedByOutsider(
        unittest.IsolatedAsyncioTestCase):
    async def test_outsider_claim_returns_false(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        # 99 is NOT in org 5
        db.add_bounty(target_id=100, claimed_by=99)
        result = await cgr._has_bounty_claimed_by_citizen(
            db, 100, db.cities[1])
        self.assertFalse(result)


class TestBountyClaimedByExpelledCitizen(
        unittest.IsolatedAsyncioTestCase):
    async def test_expelled_citizen_does_not_count(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5, standing="expelled")
        db.add_bounty(target_id=100, claimed_by=99)
        result = await cgr._has_bounty_claimed_by_citizen(
            db, 100, db.cities[1])
        self.assertFalse(result)


class TestBountyMultipleClaimsOneCitizen(
        unittest.IsolatedAsyncioTestCase):
    async def test_one_citizen_one_outsider_triggers(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5)
        # The same target somehow has two claims (unusual but
        # data-allowed). One citizen, one outsider.
        db.add_bounty(target_id=100, claimed_by=88)  # outsider
        db.add_bounty(target_id=100, claimed_by=99)  # citizen
        result = await cgr._has_bounty_claimed_by_citizen(
            db, 100, db.cities[1])
        self.assertTrue(result)


# ═════════════════════════════════════════════════════════════════════
# 10-13. should_city_guard_engage (Phase 7b + 7c merged)
# ═════════════════════════════════════════════════════════════════════


class TestEngageStillBanished(unittest.IsolatedAsyncioTestCase):
    """The Phase 7b path still works after adding the 7c trigger."""
    async def test_banished_still_engages(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_banishment(1, 100)
        guard = _guard_row(1001, city_id=1)
        char = {"id": 100}
        self.assertTrue(
            await cgr.should_city_guard_engage(db, guard, char))


class TestEngageBountyTrigger(unittest.IsolatedAsyncioTestCase):
    async def test_bounty_triggers_engage(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5)
        db.add_bounty(target_id=100, claimed_by=99)
        guard = _guard_row(1001, city_id=1)
        char = {"id": 100}
        self.assertTrue(
            await cgr.should_city_guard_engage(db, guard, char))


class TestEngageBountyInGrace(unittest.IsolatedAsyncioTestCase):
    async def test_grace_overrides_bounty(self):
        db = _FakeDB()
        db.add_city(1, org_id=5,
                    grace_started_at=time.time() - 3 * DAY)
        db.add_membership(99, 5)
        db.add_bounty(target_id=100, claimed_by=99)
        guard = _guard_row(1001, city_id=1)
        char = {"id": 100}
        self.assertFalse(
            await cgr.should_city_guard_engage(db, guard, char))


class TestEngageNeitherTrigger(unittest.IsolatedAsyncioTestCase):
    async def test_no_trigger_no_engage(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        # No banishment, no bounty
        guard = _guard_row(1001, city_id=1)
        char = {"id": 100}
        self.assertFalse(
            await cgr.should_city_guard_engage(db, guard, char))


# ═════════════════════════════════════════════════════════════════════
# 14-19. should_engage_attacker_of_citizen
# ═════════════════════════════════════════════════════════════════════


class TestAttackerNotInSet(unittest.IsolatedAsyncioTestCase):
    async def test_no_attacks_no_engage(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        guard = _guard_row(1001, city_id=1)
        self.assertFalse(
            await cgr.should_engage_attacker_of_citizen(
                db, guard, 100, set()))


class TestAttackerNotAttackedCitizen(
        unittest.IsolatedAsyncioTestCase):
    async def test_attacker_hit_non_citizen(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        # Attacker 100 attacked 200, but 200 is not a citizen
        guard = _guard_row(1001, city_id=1)
        self.assertFalse(
            await cgr.should_engage_attacker_of_citizen(
                db, guard, 100, {(100, 200)}))


class TestAttackerAttackedCitizen(
        unittest.IsolatedAsyncioTestCase):
    async def test_attacker_hit_citizen_triggers(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)  # 50 is a citizen
        guard = _guard_row(1001, city_id=1)
        self.assertTrue(
            await cgr.should_engage_attacker_of_citizen(
                db, guard, 100, {(100, 50)}))


class TestAttackerCitizenAttackedCitizen(
        unittest.IsolatedAsyncioTestCase):
    """Sibling fights still summon the cops."""
    async def test_citizen_on_citizen_triggers(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(40, 5)  # attacker is a citizen
        db.add_membership(50, 5)  # target is also a citizen
        guard = _guard_row(1001, city_id=1)
        self.assertTrue(
            await cgr.should_engage_attacker_of_citizen(
                db, guard, 40, {(40, 50)}))


class TestAttackerInGrace(unittest.IsolatedAsyncioTestCase):
    async def test_grace_overrides_attacker_trigger(self):
        db = _FakeDB()
        db.add_city(1, org_id=5,
                    grace_started_at=time.time() - 3 * DAY)
        db.add_membership(50, 5)
        guard = _guard_row(1001, city_id=1)
        self.assertFalse(
            await cgr.should_engage_attacker_of_citizen(
                db, guard, 100, {(100, 50)}))


class TestAttackerNonGuardNpc(unittest.IsolatedAsyncioTestCase):
    async def test_non_guard_never_engages(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)
        non_guard = _non_guard_row(2001)
        self.assertFalse(
            await cgr.should_engage_attacker_of_citizen(
                db, non_guard, 100, {(100, 50)}))


# ═════════════════════════════════════════════════════════════════════
# 20-27. evaluate_combat_round_triggers
# ═════════════════════════════════════════════════════════════════════


class TestEvalNoGuardsInRoom(unittest.IsolatedAsyncioTestCase):
    async def test_empty_returns_empty(self):
        db = _FakeDB()
        result = await cgr.evaluate_combat_round_triggers(
            db, room_id=100, combatant_ids=[10, 20],
            attacks_made={(10, 20)},
            room_npc_rows=[])
        self.assertEqual(result, [])


class TestEvalGuardAlreadyInCombat(
        unittest.IsolatedAsyncioTestCase):
    async def test_guard_already_in_skipped(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)
        guard = _guard_row(1001, city_id=1)
        # Guard 1001 is already a combatant — should NOT be re-added
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 50, 1001],
            {(10, 50)}, [guard])
        self.assertEqual(result, [])


class TestEvalAttackerTriggerFires(
        unittest.IsolatedAsyncioTestCase):
    async def test_returns_guard_on_citizen_attack(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)
        guard = _guard_row(1001, city_id=1)
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 50],
            {(10, 50)}, [guard])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["id"], 1001)


class TestEvalBountyTriggerFires(
        unittest.IsolatedAsyncioTestCase):
    async def test_returns_guard_on_bounty(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5)
        db.add_bounty(target_id=10, claimed_by=99)
        guard = _guard_row(1001, city_id=1)
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 20],
            set(), [guard])
        self.assertEqual(len(result), 1)


class TestEvalNeitherFires(unittest.IsolatedAsyncioTestCase):
    async def test_neither_trigger_no_engage(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        guard = _guard_row(1001, city_id=1)
        # Attack happened but target wasn't a citizen, and no
        # bounty exists.
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 20],
            {(10, 20)}, [guard])
        self.assertEqual(result, [])


class TestEvalCityCachedAcrossGuards(
        unittest.IsolatedAsyncioTestCase):
    """Two guards from the same city → one city lookup."""
    async def test_multiple_guards_one_lookup(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)
        # Wrap fetchall to count get_city_by_id calls
        original_fetchall = db.fetchall
        city_lookup_calls = []

        async def counting_fetchall(sql, params=()):
            if "FROM player_cities WHERE id" in sql:
                city_lookup_calls.append(params)
            return await original_fetchall(sql, params)

        db.fetchall = counting_fetchall
        g1 = _guard_row(1001, city_id=1)
        g2 = _guard_row(1002, city_id=1)
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 50],
            {(10, 50)}, [g1, g2])
        self.assertEqual(len(result), 2)
        # The city cache means we should see at most ONE lookup
        # for city_id=1 across both guards
        city_1_lookups = [c for c in city_lookup_calls
                          if c == (1,)]
        self.assertEqual(len(city_1_lookups), 1)


class TestEvalDissolvedCity(unittest.IsolatedAsyncioTestCase):
    async def test_dissolved_skipped(self):
        db = _FakeDB()
        db.add_city(1, org_id=5, state="dissolved")
        db.add_membership(50, 5)
        guard = _guard_row(1001, city_id=1)
        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [10, 50],
            {(10, 50)}, [guard])
        self.assertEqual(result, [])


class TestEvalFailSoft(unittest.IsolatedAsyncioTestCase):
    async def test_broken_db_returns_empty(self):
        class BrokenDB:
            async def fetchall(self, *a, **kw):
                raise RuntimeError("boom")

            async def get_membership(self, *a, **kw):
                raise RuntimeError("boom")

        guard = _guard_row(1001, city_id=1)
        result = await cgr.evaluate_combat_round_triggers(
            BrokenDB(), 100, [10, 20],
            {(10, 20)}, [guard])
        # Returns [] without raising
        self.assertEqual(result, [])


# ═════════════════════════════════════════════════════════════════════
# 28-29. End-to-end integration
# ═════════════════════════════════════════════════════════════════════


class TestE2EAttackerOfCitizenTriggersGuard(
        unittest.IsolatedAsyncioTestCase):
    """A non-citizen attacks a citizen. Guard joins.

    Composite check exercising the full
    evaluate_combat_round_triggers → returned guard list path.
    """
    async def test_full_path(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(50, 5)  # citizen
        # Non-citizen 99 attacks citizen 50
        # Guard 1001 isn't in combat yet
        guard = _guard_row(1001, city_id=1)
        # Other NPCs in the room: a non-guard, an unrelated
        # guard from a different (in-grace) city
        db.add_city(2, org_id=6,
                    grace_started_at=time.time() - DAY)
        guard_g2 = _guard_row(1002, city_id=2)
        non_guard = _non_guard_row(3001)

        result = await cgr.evaluate_combat_round_triggers(
            db, 100, [99, 50],
            {(99, 50)}, [guard, guard_g2, non_guard])
        # Only the healthy-city guard 1001 should fire
        ids = sorted(r["id"] for r in result)
        self.assertEqual(ids, [1001])


class TestE2EBountyTriggersGuardOnEntry(
        unittest.IsolatedAsyncioTestCase):
    """A bountied target enters a room with a city guard.
    Verified via the entry-shaped should_city_guard_engage,
    which Phase 7c extended to fold in the bounty trigger."""
    async def test_bounty_on_entry(self):
        db = _FakeDB()
        db.add_city(1, org_id=5)
        db.add_membership(99, 5)
        db.add_bounty(target_id=200, claimed_by=99)
        guard = _guard_row(1001, city_id=1)
        # Entering character 200 has a citizen-claimed bounty
        result = await cgr.should_city_guard_engage(
            db, guard, {"id": 200})
        self.assertTrue(result)


if __name__ == "__main__":
    unittest.main()
