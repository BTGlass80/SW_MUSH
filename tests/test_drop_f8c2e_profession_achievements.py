# -*- coding: utf-8 -*-
"""
tests/test_drop_f8c2e_profession_achievements.py — F.8.c.2.e
profession-category achievement catalog authoring.

F.8.c.2.e (May 4 2026) closes a loose end from F.8.c.2.d. The
seven graduation achievement keys referenced in chains.yaml's
graduation.achievements lists were stamped onto
chargen_notes.graduation_achievements as a fallback by
chain_rewards.apply_graduation_rewards, but absent from the
achievement catalog. With this drop's authoring landed,
chain_rewards's catalog-mark path now fires alongside the
chargen_notes stamp, awarding CP and sending the standard
achievement notification.

Tests
-----
   1. Catalog presence — all 7 keys load via get_achievement
   2. Schema conformance — required fields present, well-formed
   3. Coverage — every unlocked CW chain has its graduation
      achievement in the catalog
   4. Distinct keys — no two chains reference the same achievement
   5. End-to-end — F.8.c.2.d's catalog-mark path fires (and the
      chargen_notes fallback still stamps alongside, preserving
      idempotency)
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CHAIN_TO_ACHIEVEMENT = {
    "republic_soldier":      "sworn_to_the_republic",
    "republic_intelligence": "recruited_in_shadow",
    "separatist_commando":   "raised_the_red_flag",
    "separatist_agent":      "sleeper_in_the_capital",
    "bounty_hunter":         "first_contract",
    "smuggler":              "first_run",
    "shipwright_trader":     "first_repair",
}


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


# ─────────────────────────────────────────────────────────────────────
# 1. Catalog presence
# ─────────────────────────────────────────────────────────────────────


class TestCatalogPresence(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from engine.achievements import load_achievements
        load_achievements()  # Idempotent; safe to call from tests

    def test_all_seven_keys_loadable(self):
        from engine.achievements import get_achievement
        for chain_id, ach_key in CHAIN_TO_ACHIEVEMENT.items():
            ach = get_achievement(ach_key)
            self.assertIsNotNone(
                ach,
                f"achievement {ach_key} for chain {chain_id} "
                f"missing from catalog",
            )


# ─────────────────────────────────────────────────────────────────────
# 2. Schema conformance
# ─────────────────────────────────────────────────────────────────────


class TestSchemaConformance(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        from engine.achievements import load_achievements
        load_achievements()

    def test_each_has_required_fields(self):
        from engine.achievements import get_achievement
        required = ("key", "name", "description", "category",
                    "icon", "cp_reward", "trigger")
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            self.assertIsNotNone(ach)
            missing = [f for f in required if f not in ach]
            self.assertEqual(missing, [],
                             f"{ach_key} missing fields: {missing}")

    def test_category_is_profession(self):
        from engine.achievements import get_achievement
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            self.assertEqual(
                ach["category"], "profession",
                f"{ach_key} is not category=profession",
            )

    def test_trigger_event_is_chain_graduation(self):
        """The trigger event is informational (chain_rewards
        calls _complete_achievement directly, not via event-match
        dispatcher) but consistency matters for catalog-wide tooling."""
        from engine.achievements import get_achievement
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            self.assertEqual(
                ach["trigger"].get("event"),
                "chain_graduation",
                f"{ach_key} trigger event is not chain_graduation",
            )

    def test_trigger_count_is_one(self):
        from engine.achievements import get_achievement
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            self.assertEqual(
                int(ach["trigger"].get("count", 0)), 1,
                f"{ach_key} trigger count is not 1",
            )

    def test_trigger_chain_id_matches_mapping(self):
        from engine.achievements import get_achievement
        for chain_id, ach_key in CHAIN_TO_ACHIEVEMENT.items():
            ach = get_achievement(ach_key)
            self.assertEqual(
                ach["trigger"].get("chain_id"),
                chain_id,
                f"{ach_key} trigger chain_id mismatch",
            )

    def test_cp_reward_in_reasonable_range(self):
        from engine.achievements import get_achievement
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            cp = ach["cp_reward"]
            self.assertGreaterEqual(cp, 1,
                                    f"{ach_key} CP < 1")
            self.assertLessEqual(cp, 5,
                                 f"{ach_key} CP > 5 (suspect)")

    def test_description_mentions_chain_or_completion(self):
        """Soft check — descriptions should hint at chain completion."""
        from engine.achievements import get_achievement
        for ach_key in CHAIN_TO_ACHIEVEMENT.values():
            ach = get_achievement(ach_key)
            desc = ach["description"].lower()
            keywords = ("graduated", "completion", "tutorial",
                        "trained", "passed")
            self.assertTrue(
                any(k in desc for k in keywords),
                f"{ach_key} description doesn't hint at "
                f"chain graduation: {ach['description']!r}",
            )


# ─────────────────────────────────────────────────────────────────────
# 3. Chain coverage
# ─────────────────────────────────────────────────────────────────────


class TestChainCoverage(unittest.TestCase):
    """Every unlocked CW chain's graduation.achievements list has
    a matching catalog entry. Catches a future authoring slip
    where someone adds an achievement key to a chain's graduation
    block but forgets the catalog entry."""

    @classmethod
    def setUpClass(cls):
        import yaml
        with open(PROJECT_ROOT / "data/worlds/clone_wars/"
                  "tutorials/chains.yaml", encoding="utf-8") as f:
            cls.chains_doc = yaml.safe_load(f)

    def test_every_unlocked_chain_achievement_is_in_catalog(self):
        from engine.achievements import (
            load_achievements, get_achievement,
        )
        load_achievements()
        unmatched = []
        for chain in self.chains_doc["chains"]:
            if chain.get("locked"):
                continue
            grad = chain.get("graduation", {})
            for ach_key in grad.get("achievements", []) or []:
                if get_achievement(ach_key) is None:
                    unmatched.append((chain["chain_id"], ach_key))
        self.assertEqual(
            unmatched, [],
            f"Chain achievements with no catalog entry: {unmatched}",
        )


# ─────────────────────────────────────────────────────────────────────
# 4. Distinct keys
# ─────────────────────────────────────────────────────────────────────


class TestDistinctKeys(unittest.TestCase):

    def test_no_chain_shares_an_achievement_key(self):
        # Mapping value-set should equal mapping length
        keys = list(CHAIN_TO_ACHIEVEMENT.values())
        self.assertEqual(
            len(keys), len(set(keys)),
            "Two chains share an achievement key",
        )


# ─────────────────────────────────────────────────────────────────────
# 5. End-to-end — F.8.c.2.d catalog-mark path now fires
# ─────────────────────────────────────────────────────────────────────


class _MockDB:
    def __init__(self):
        self.save_calls = []
        self.inventory_calls = []
        self.cp_award_calls = []  # (char_id, points)
        self.upserted_progress = []  # (char_id, key, progress, completed)

    async def save_character(self, char_id, **kwargs):
        self.save_calls.append((char_id, kwargs))

    async def add_to_inventory(self, char_id, item):
        self.inventory_calls.append((char_id, item))

    async def cp_add_character_points(self, char_id, points):
        # _complete_achievement → CP award path
        self.cp_award_calls.append((char_id, points))

    async def get_organization(self, code):
        return None

    async def get_membership(self, char_id, org_id):
        return None


def _char(char_id=1, credits=100, attrs=None, notes=None):
    return {
        "id": char_id,
        "name": "TestPC",
        "credits": credits,
        "room_id": 10,
        "attributes": json.dumps(attrs or {}),
        "chargen_notes": json.dumps(notes or {}) if notes else "",
        "faction_id": "independent",
    }


class _MockGraduation:
    def __init__(self, **kw):
        self.drop_room = kw.get("drop_room", "test_drop")
        self.credits = kw.get("credits", 0)
        self.faction_rep = kw.get("faction_rep", {})
        self.items = kw.get("items", [])
        self.achievements = kw.get("achievements", [])
        self.follow_up_hint = kw.get("follow_up_hint", "")


class TestEndToEndCatalogMark(unittest.TestCase):
    """Verify F.8.c.2.d's apply_graduation_rewards now hits the
    catalog path (cp_add_character_points + _upsert_progress)
    AND retains the chargen_notes fallback (so legacy data is
    still preserved). Both paths fire on the same call."""

    def setUp(self):
        # Stub out the upsert helper which writes to a real DB
        # table we don't have in our mock. Patch at module level
        # so the achievement system's _complete_achievement path
        # runs cleanly.
        from unittest.mock import patch, AsyncMock
        self._upsert_patcher = patch(
            "engine.achievements._upsert_progress",
            AsyncMock(return_value=None),
        )
        self._upsert_patcher.start()
        # Reload the catalog (some other test may have wiped it)
        from engine.achievements import load_achievements
        load_achievements()

    def tearDown(self):
        self._upsert_patcher.stop()

    def test_catalog_mark_fires_for_known_key(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(
            achievements=["sworn_to_the_republic"],
        )
        report = _run(apply_graduation_rewards(
            db, char, {}, grad,
            "republic_soldier", chain_label="Republic Soldier",
        ))

        # Catalog path fired: CP awarded
        self.assertEqual(len(db.cp_award_calls), 1)
        char_id, cp = db.cp_award_calls[0]
        self.assertEqual(char_id, char["id"])
        self.assertEqual(cp, 3)  # All seven are 3 CP

        # chargen_notes fallback still stamped
        notes = json.loads(char["chargen_notes"])
        self.assertIn("sworn_to_the_republic",
                      notes.get("graduation_achievements", []))
        # Report counts the achievement
        self.assertIn("sworn_to_the_republic", report["achievements"])

    def test_unknown_key_falls_back_chargen_notes_only(self):
        from engine.chain_rewards import apply_graduation_rewards
        db = _MockDB()
        char = _char()
        grad = _MockGraduation(
            achievements=["totally_made_up_achievement"],
        )
        report = _run(apply_graduation_rewards(
            db, char, {}, grad, "test_chain",
        ))

        # Catalog path didn't fire (key missing)
        self.assertEqual(len(db.cp_award_calls), 0)
        # chargen_notes fallback still stamped
        notes = json.loads(char["chargen_notes"])
        self.assertIn(
            "totally_made_up_achievement",
            notes.get("graduation_achievements", []),
        )

    def test_all_seven_chain_achievements_award_cp(self):
        from engine.chain_rewards import apply_graduation_rewards
        for chain_id, ach_key in CHAIN_TO_ACHIEVEMENT.items():
            db = _MockDB()
            char = _char(char_id=1)
            grad = _MockGraduation(achievements=[ach_key])
            _run(apply_graduation_rewards(
                db, char, {}, grad, chain_id,
            ))
            self.assertEqual(
                len(db.cp_award_calls), 1,
                f"chain {chain_id} achievement {ach_key} did not "
                f"fire the CP award path",
            )


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_drop_f8c2e_profession_achievements as mod
        self.assertIn("F.8.c.2.e", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
