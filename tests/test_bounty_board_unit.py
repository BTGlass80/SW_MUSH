# -*- coding: utf-8 -*-
"""
tests/test_bounty_board_unit.py — Code review C6 fix tests

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`bounty_board.py` was on the priority list for testing because it's
economy-impacting. This file adds unit-test coverage of the pure /
deterministic surface:

  - BountyContract.to_dict / from_dict round-trip
  - BountyTier and BountyStatus enum coverage
  - _scale_reward bounds + 50cr rounding
  - _pick_tier weighting (statistical sanity)
  - _gen_id format
  - _pick_fugitive_room avoidance heuristic
  - format_bounty_board / format_contract_detail headline structure

Async / DB-backed surface (`generate_bounty`, `BountyBoard.refresh`)
is left to integration tests with a live DB; those are out of scope
for this unit-test drop and require real NPC and room data.
"""
import os
import random
import sys
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine.bounty_board import (  # noqa: E402
    BountyContract,
    BountyTier,
    BountyStatus,
    PAY_RANGES,
    TIER_WEIGHTS,
    FUGITIVE_ARCHETYPES,
    _gen_id,
    _pick_tier,
    _scale_reward,
    _pick_fugitive_room,
    format_bounty_board,
    format_contract_detail,
)


# ══════════════════════════════════════════════════════════════════════════════
# Enums
# ══════════════════════════════════════════════════════════════════════════════


class TestBountyTierEnum(unittest.TestCase):
    def test_all_tiers_have_pay_range(self):
        for tier in BountyTier:
            self.assertIn(tier, PAY_RANGES,
                          f"{tier} missing from PAY_RANGES")
            lo, hi = PAY_RANGES[tier]
            self.assertGreater(hi, lo)
            self.assertGreater(lo, 0)

    def test_all_tiers_have_spawn_weight(self):
        for tier in BountyTier:
            self.assertIn(tier, TIER_WEIGHTS,
                          f"{tier} missing from TIER_WEIGHTS")
            self.assertGreater(TIER_WEIGHTS[tier], 0)

    def test_pay_ranges_increase_with_tier(self):
        # Order from cheapest to most expensive
        order = [BountyTier.EXTRA, BountyTier.AVERAGE, BountyTier.NOVICE,
                 BountyTier.VETERAN, BountyTier.SUPERIOR]
        prev_hi = 0
        for tier in order:
            lo, hi = PAY_RANGES[tier]
            self.assertGreaterEqual(lo, prev_hi // 2,
                                    f"{tier}.lo dipped relative to previous tier")
            prev_hi = hi

    def test_spawn_weights_decrease_with_tier(self):
        # extras most common, superiors rarest
        order = [BountyTier.EXTRA, BountyTier.AVERAGE, BountyTier.NOVICE,
                 BountyTier.VETERAN, BountyTier.SUPERIOR]
        weights = [TIER_WEIGHTS[t] for t in order]
        for i in range(1, len(weights)):
            self.assertLessEqual(weights[i], weights[i - 1],
                                 f"weight at index {i} ({weights[i]}) > "
                                 f"index {i-1} ({weights[i-1]})")


class TestBountyStatusEnum(unittest.TestCase):
    def test_all_status_values_are_distinct_strings(self):
        values = [s.value for s in BountyStatus]
        self.assertEqual(len(values), len(set(values)),
                         "duplicate status values")
        for v in values:
            self.assertIsInstance(v, str)


# ══════════════════════════════════════════════════════════════════════════════
# BountyContract round-trip
# ══════════════════════════════════════════════════════════════════════════════


class TestBountyContractRoundTrip(unittest.TestCase):
    def _make(self, **overrides) -> BountyContract:
        defaults = dict(
            id="b-deadbeef",
            tier=BountyTier.AVERAGE,
            target_name="Krom",
            target_species="Rodian",
            target_archetype="thug",
            crime_description="armed robbery",
            posting_org="Imperial Garrison",
            tip="Last seen near the cantina district.",
            reward=500,
            reward_alive_bonus=100,
            target_npc_id=None,
            target_room_id=None,
            status=BountyStatus.POSTED,
            claimed_by=None,
            posted_at=1234567.0,
            claimed_at=None,
            expires_at=None,
            collected_at=None,
        )
        defaults.update(overrides)
        return BountyContract(**defaults)

    def test_to_dict_from_dict_round_trip(self):
        c = self._make()
        d = c.to_dict()
        c2 = BountyContract.from_dict(d)
        self.assertEqual(c.id, c2.id)
        self.assertEqual(c.tier, c2.tier)
        self.assertEqual(c.reward, c2.reward)
        self.assertEqual(c.target_name, c2.target_name)
        self.assertEqual(c.posted_at, c2.posted_at)

    def test_round_trip_preserves_all_fields(self):
        c = self._make(
            target_npc_id=42, target_room_id=12,
            status=BountyStatus.CLAIMED, claimed_by="char-7",
            expires_at=9999999.0,
        )
        c2 = BountyContract.from_dict(c.to_dict())
        for fld in ("id", "tier", "target_name", "target_species",
                    "target_archetype", "crime_description", "posting_org",
                    "tip", "reward", "reward_alive_bonus",
                    "target_npc_id", "target_room_id",
                    "status", "claimed_by", "posted_at", "claimed_at",
                    "expires_at", "collected_at"):
            self.assertEqual(getattr(c, fld), getattr(c2, fld),
                             f"field {fld} did not survive round-trip")

    def test_from_dict_handles_missing_optional_fields(self):
        # The minimum-viable dict — only required fields
        d = {
            "id": "b-min", "tier": "extra", "target_name": "X",
            "target_species": "Human", "target_archetype": "thug",
            "crime_description": "x", "posting_org": "x", "tip": "x",
            "reward": 100,
        }
        c = BountyContract.from_dict(d)
        self.assertEqual(c.id, "b-min")
        self.assertEqual(c.reward_alive_bonus, 0)
        self.assertEqual(c.status, BountyStatus.POSTED)
        self.assertIsNone(c.target_npc_id)


# ══════════════════════════════════════════════════════════════════════════════
# Generation helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestGenId(unittest.TestCase):
    def test_id_starts_with_b_dash(self):
        for _ in range(20):
            self.assertTrue(_gen_id().startswith("b-"))

    def test_ids_are_unique(self):
        ids = {_gen_id() for _ in range(50)}
        self.assertEqual(len(ids), 50)

    def test_id_length_is_predictable(self):
        # "b-" + 8-char uuid prefix
        self.assertEqual(len(_gen_id()), 10)


class TestScaleReward(unittest.TestCase):
    def test_reward_within_tier_range(self):
        # Run many trials per tier to bound the random output
        random.seed(42)
        for tier in BountyTier:
            lo, hi = PAY_RANGES[tier]
            for _ in range(20):
                r = _scale_reward(tier)
                # _scale_reward rounds to nearest 50 — value can sit
                # within the tier range; rounding may push by ±25
                self.assertGreaterEqual(r, lo - 25,
                                        f"{tier} produced {r} below {lo}-25")
                self.assertLessEqual(r, hi + 25,
                                     f"{tier} produced {r} above {hi}+25")

    def test_reward_rounds_to_50cr(self):
        random.seed(123)
        for tier in BountyTier:
            for _ in range(10):
                r = _scale_reward(tier)
                self.assertEqual(r % 50, 0,
                                 f"{tier} produced {r} (not a multiple of 50)")


class TestPickTier(unittest.TestCase):
    def test_pick_tier_returns_known_tier(self):
        random.seed(7)
        for _ in range(20):
            self.assertIn(_pick_tier(), set(BountyTier))

    def test_extras_appear_more_often_than_superiors(self):
        # With weights 5:1 in favor of extras, over 1000 picks the
        # difference should be obvious. 5x weight ratio → expect ~5x
        # the count; we use a loose lower bound to keep the test
        # statistically robust.
        random.seed(2026)
        counts = {t: 0 for t in BountyTier}
        for _ in range(1000):
            counts[_pick_tier()] += 1
        self.assertGreater(counts[BountyTier.EXTRA],
                           counts[BountyTier.SUPERIOR] * 2,
                           f"extras={counts[BountyTier.EXTRA]} should be >> "
                           f"superiors={counts[BountyTier.SUPERIOR]}; got {counts}")


class TestPickFugitiveRoom(unittest.TestCase):
    def test_avoids_docking_bays(self):
        rooms = [
            {"id": 1, "name": "Docking Bay 94"},
            {"id": 2, "name": "Cantina Common Room"},
            {"id": 3, "name": "Landing Pad 7"},
            {"id": 4, "name": "Market Stalls"},
        ]
        random.seed(0)
        # Run many trials to check the avoidance is consistent
        picks = {_pick_fugitive_room(rooms)["id"] for _ in range(30)}
        # Should never include rooms with avoid keywords
        self.assertNotIn(1, picks, "should avoid Docking Bay 94")
        self.assertNotIn(3, picks, "should avoid Landing Pad 7")
        # Should pick from the safe set
        self.assertTrue(picks.issubset({2, 4}))

    def test_falls_back_when_no_safe_rooms(self):
        # All rooms are docking bays — function falls back to picking any
        rooms = [
            {"id": 1, "name": "Docking Bay 94"},
            {"id": 2, "name": "Bay 86"},
        ]
        random.seed(1)
        result = _pick_fugitive_room(rooms)
        self.assertIn(result["id"], {1, 2})

    def test_returns_none_on_empty_list(self):
        self.assertIsNone(_pick_fugitive_room([]))


# ══════════════════════════════════════════════════════════════════════════════
# Format helpers
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatBountyBoard(unittest.TestCase):
    def test_empty_board_renders_no_active_message(self):
        lines = format_bounty_board([])
        text = "\n".join(lines)
        self.assertIn("No active bounties", text)

    def test_populated_board_includes_each_contract(self):
        c1 = BountyContract(
            id="b-a1", tier=BountyTier.NOVICE, target_name="Krom",
            target_species="Rodian", target_archetype="thug",
            crime_description="x", posting_org="y", tip="z",
            reward=900, reward_alive_bonus=0,
            target_npc_id=None, target_room_id=None,
        )
        c2 = BountyContract(
            id="b-b2", tier=BountyTier.SUPERIOR, target_name="Vex",
            target_species="Human", target_archetype="bounty_hunter",
            crime_description="x", posting_org="y", tip="z",
            reward=5000, reward_alive_bonus=500,
            target_npc_id=None, target_room_id=None,
        )
        text = "\n".join(format_bounty_board([c1, c2]))
        self.assertIn("b-a1", text)
        self.assertIn("b-b2", text)
        self.assertIn("Krom", text)
        self.assertIn("Vex", text)
        # Reward formatting includes thousands separator
        self.assertIn("5,000cr", text)
        # Alive bonus is shown only when nonzero
        self.assertIn("+500cr alive", text)
        self.assertNotIn("+0cr alive", text)


class TestFormatContractDetail(unittest.TestCase):
    def test_detail_includes_all_key_fields(self):
        c = BountyContract(
            id="b-x", tier=BountyTier.AVERAGE,
            target_name="Krom", target_species="Rodian",
            target_archetype="thug",
            crime_description="armed robbery and assault",
            posting_org="Imperial Garrison",
            tip="Last seen near the cantina district.",
            reward=500, reward_alive_bonus=100,
            target_npc_id=None, target_room_id=None,
        )
        text = "\n".join(format_contract_detail(c))
        self.assertIn("Krom", text)
        self.assertIn("Rodian", text)
        self.assertIn("armed robbery", text)
        self.assertIn("Imperial Garrison", text)
        self.assertIn("cantina district", text)
        self.assertIn("500", text)

    def test_claimed_contract_shows_time_remaining(self):
        c = BountyContract(
            id="b-clm", tier=BountyTier.AVERAGE,
            target_name="Krom", target_species="Rodian",
            target_archetype="thug",
            crime_description="x", posting_org="y", tip="z",
            reward=500, reward_alive_bonus=0,
            target_npc_id=None, target_room_id=None,
            status=BountyStatus.CLAIMED,
            claimed_by="char-7",
            expires_at=time.time() + 7320,  # 2h 2m from now
        )
        text = "\n".join(format_contract_detail(c))
        self.assertIn("Time remaining", text)
        # 7320s = 2h2m; formatter shows "2h 2m"
        self.assertIn("2h", text)


# ══════════════════════════════════════════════════════════════════════════════
# Misc invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestModuleInvariants(unittest.TestCase):
    def test_fugitive_archetypes_are_nonempty(self):
        self.assertGreater(len(FUGITIVE_ARCHETYPES), 0)
        for a in FUGITIVE_ARCHETYPES:
            self.assertIsInstance(a, str)
            self.assertTrue(a)


if __name__ == "__main__":
    unittest.main()
