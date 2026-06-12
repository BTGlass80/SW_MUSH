# -*- coding: utf-8 -*-
"""
tests/test_lane_d2_contest_violence.py — Lane D2 guards.

Lane D drop 2 wires the org Violence Index (the E1 primitive D1 put on
the Geonosian hives) into the SYN.3 region-contest machinery — the
"violence_index drives territory-contest aggression + Director
turf-dispute narration" half of the lane. Two live consumers, both an
*extension* of the existing contest engine (no schema change, no
valid_factions change):

  1. AGGRESSION — ``compute_anchor_reinforcements`` gains an optional
     ``challenger_violence_index``. A "bloody"-band challenger (VI >= 70)
     commits +1 reinforcement to the culminating fight; a "range war"
     challenger (VI >= 85) commits +2. Wired at the live spawn site
     (``_spawn_region_anchor`` looks up the challenger org's VI).
  2. NARRATION — the declaration broadcast and the ``faction status``
     contest line carry a posture phrase / tag keyed on the same VI via
     ``violence_descriptor``.

Backward-compatibility is the load-bearing constraint: the default
``challenger_violence_index=None`` must reproduce the pre-D2 reinforcement
table exactly (the SYN.3.b spawn test pins ``1 + compute_anchor_reinforcements(150)``).

Live-consumer proof: hutt_cartel (VI 88, in valid_factions, can be a
contest challenger) and the D1 hives (stalgasin 88, gehenbar 84) all
feed the new bands — this test loads their real VIs from
organizations.yaml and asserts the mechanic responds.

Sandbox-runnable: imports only the pure contest helpers + org helpers
+ yaml (no aiosqlite). The full async contest flow is covered by
tests/test_syn3a/test_syn3b on Brian's Windows box.
"""
import asyncio
import json
import os
import unittest

import yaml

from engine.contest import (
    compute_anchor_reinforcements,
    _CONTEST_POSTURE_CLAUSE,
    _org_violence_index,
    REGION_CONTEST_BLOODY_VI,
    REGION_CONTEST_RANGE_WAR_VI,
)
from engine.organizations import violence_descriptor, get_org_violence_index

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORGS_YAML = os.path.join(
    PROJECT_ROOT, "data", "worlds", "clone_wars", "organizations.yaml")


def _run(coro):
    """Run a coroutine in a fresh event loop (BugFix5 Py3.14 pattern)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _faction_vi(code):
    orgs = yaml.safe_load(open(ORGS_YAML, encoding="utf-8"))
    for f in orgs.get("factions", []) or []:
        if f.get("code") == code:
            row = {"properties": json.dumps(f.get("properties", {}))}
            return get_org_violence_index(row)
    return None


class TestReinforcementBackwardCompat(unittest.TestCase):
    """The pre-D2 influence-only table must hold for the default
    (no-posture) call — the SYN.3.b spawn test depends on it."""

    def test_documented_table_unchanged_without_vi(self):
        cases = {40: 0, 80: 0, 100: 0, 125: 1, 149: 1, 150: 2}
        for inf, expect in cases.items():
            self.assertEqual(compute_anchor_reinforcements(inf), expect)

    def test_none_equals_pre_d2(self):
        for inf in (0, 100, 125, 150):
            self.assertEqual(
                compute_anchor_reinforcements(inf),
                compute_anchor_reinforcements(inf, None),
            )


class TestReinforcementViBands(unittest.TestCase):
    def test_range_war_adds_two(self):
        # 150 influence -> base 2; range-war posture -> +2 = 4.
        self.assertEqual(compute_anchor_reinforcements(150, 88), 4)
        self.assertEqual(compute_anchor_reinforcements(150, 85), 4)

    def test_bloody_adds_one(self):
        self.assertEqual(compute_anchor_reinforcements(125, 72), 2)  # 1+1
        self.assertEqual(compute_anchor_reinforcements(150, 84), 3)  # 2+1

    def test_sub_bloody_no_bonus(self):
        self.assertEqual(compute_anchor_reinforcements(125, 40), 1)
        self.assertEqual(compute_anchor_reinforcements(125, 69), 1)

    def test_band_boundaries(self):
        # Exactly at the band edges.
        self.assertEqual(compute_anchor_reinforcements(125, REGION_CONTEST_BLOODY_VI), 2)
        self.assertEqual(
            compute_anchor_reinforcements(125, REGION_CONTEST_RANGE_WAR_VI - 1), 2)
        self.assertEqual(
            compute_anchor_reinforcements(125, REGION_CONTEST_RANGE_WAR_VI), 3)

    def test_posture_does_not_manufacture_a_force(self):
        # Below the influence floor, base is 0 and posture cannot add.
        self.assertEqual(compute_anchor_reinforcements(80, 95), 0)
        self.assertEqual(compute_anchor_reinforcements(100, 99), 0)

    def test_bool_is_not_treated_as_vi(self):
        # bool is an int subclass; must be ignored, not read as a posture.
        self.assertEqual(compute_anchor_reinforcements(150, True), 2)
        self.assertEqual(compute_anchor_reinforcements(150, False), 2)

    def test_bands_match_violence_descriptor(self):
        # The mechanic's thresholds must equal the narration bands so the
        # two never drift.
        self.assertEqual(violence_descriptor(REGION_CONTEST_BLOODY_VI), "bloody")
        self.assertEqual(violence_descriptor(REGION_CONTEST_RANGE_WAR_VI), "range war")
        self.assertEqual(violence_descriptor(REGION_CONTEST_BLOODY_VI - 1), "heated")


class TestNarrationClauseMap(unittest.TestCase):
    def test_covers_all_descriptor_bands(self):
        # Every band violence_descriptor can emit must have a clause, or
        # the declaration broadcast would silently drop the posture line.
        bands = {violence_descriptor(v) for v in (0, 40, 60, 78, 95)}
        for b in bands:
            self.assertIn(
                b, _CONTEST_POSTURE_CLAUSE,
                f"narration clause map missing band {b!r}.",
            )
        # And exactly the five canonical bands.
        self.assertEqual(
            set(_CONTEST_POSTURE_CLAUSE),
            {"surgical", "pointed", "heated", "bloody", "range war"},
        )

    def test_range_war_clause_reads_naturally(self):
        self.assertIn("range war", _CONTEST_POSTURE_CLAUSE["range war"].lower())


class TestOrgViolenceIndexHelper(unittest.TestCase):
    """_org_violence_index must be failure-tolerant — a None result is
    the contract that lets the contest narration/aggression fall back to
    posture-free behaviour rather than raising mid-tick."""

    def test_none_org_code(self):
        class _Db:
            async def get_organization(self, code):
                raise AssertionError("should not be called for falsy code")
        self.assertIsNone(_run(_org_violence_index(_Db(), None)))

    def test_db_without_get_organization(self):
        class _Bare:
            pass
        self.assertIsNone(_run(_org_violence_index(_Bare(), "stalgasin")))

    def test_get_organization_raises(self):
        class _Db:
            async def get_organization(self, code):
                raise RuntimeError("db down")
        self.assertIsNone(_run(_org_violence_index(_Db(), "stalgasin")))

    def test_missing_org_returns_none(self):
        class _Db:
            async def get_organization(self, code):
                return None
        self.assertIsNone(_run(_org_violence_index(_Db(), "nope")))

    def test_resolves_violence_index_from_row(self):
        class _Db:
            async def get_organization(self, code):
                return {"properties": json.dumps({"violence_index": 88})}
        self.assertEqual(_run(_org_violence_index(_Db(), "stalgasin")), 88)


class TestLiveConsumerLinkage(unittest.TestCase):
    """Tie the real org VIs (the hives from D1 + hutt_cartel) to the D2
    mechanic, proving the consumer is live and the hives inherit it."""

    def test_hutt_cartel_is_a_range_war_challenger(self):
        vi = _faction_vi("hutt_cartel")
        self.assertIsNotNone(vi, "hutt_cartel should carry a violence_index")
        # hutt_cartel is in valid_factions and can challenge a region, so
        # this is the immediate live consumer of the reinforcement bonus.
        self.assertEqual(violence_descriptor(vi), "range war")
        self.assertEqual(compute_anchor_reinforcements(150, vi), 4)

    def test_d1_hives_feed_the_mechanic(self):
        stalgasin_vi = _faction_vi("stalgasin")
        gehenbar_vi = _faction_vi("gehenbar")
        self.assertEqual(stalgasin_vi, 88)
        self.assertEqual(gehenbar_vi, 84)
        # Stalgasin (range war) -> +2; Gehenbar (bloody) -> +1, when each
        # fields a max influence force.
        self.assertEqual(compute_anchor_reinforcements(150, stalgasin_vi), 4)
        self.assertEqual(compute_anchor_reinforcements(150, gehenbar_vi), 3)


if __name__ == "__main__":
    unittest.main()
