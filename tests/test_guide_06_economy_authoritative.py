# -*- coding: utf-8 -*-
"""
Authoritative cross-check guard for Guide_06_Economy.md (Opus quality pass,
June 2026).

The existing test_guide_06_economy_rework.py checks that section names are
PRESENT. It cannot catch the drift class this guard exists for: a numbers
table that cites a WRONG pay range, partial-pay fraction, multiplier, fine,
or a phantom/era-removed planet versus the live engine constants.

That drift is invisible to every other test (the convention/registry suites
guard commands, not guide prose). The 2026-06-22 authoritative pass found a
dense layer of it: every non-delivery partial-pay fraction was stale (50/75%
vs the live flat 40%), all four SPACE mission pay ranges were wrong, the
smuggling routes still named the era-removed Kessel/Corellia (now Geonosis/
Coruscant), the cargo-trade multipliers cited the pre-v29 50%/200% exploit
spread (now 70%/140%), the smuggling fine was flat 50% (now tiered 25/50),
`perform` was Perception (it's Persuasion/Musical Instrument), the bounty
archetype roster listed phantom types, and a phantom "spor swarms" no-yield.

This guard pins BOTH the engine constants (so a retune fails loudly) AND that
the guide prose reflects them, AND that the killed phantoms stay dead.
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_06_Economy.md")

EN_DASH = "–"


def _guide_text():
    with open(GUIDE_PATH, encoding="utf-8") as f:
        return f.read()


def _range(lo, hi):
    """Render a pay range the way the guide formats it: '1,500–2,500'."""
    return f"{lo:,}{EN_DASH}{hi:,}"


class GuideExists(unittest.TestCase):
    def test_guide_file_present(self):
        self.assertTrue(os.path.isfile(GUIDE_PATH))


class MissionBoard(unittest.TestCase):
    """§2 — board size, 14 types, partial fractions, space pay ranges."""

    def test_board_size_and_refresh(self):
        from engine import missions
        self.assertEqual(missions.BOARD_MIN, 5)
        self.assertEqual(missions.BOARD_MAX, 8)
        self.assertEqual(missions.REFRESH_SECONDS, 1800)
        self.assertEqual(missions.MISSION_TTL, 3600)
        self.assertEqual(missions.MISSION_ACTIVE_TTL, 7200)
        body = _guide_text()
        self.assertIn(f"5{EN_DASH}8", body)
        self.assertIn("every 30 minutes", body)

    def test_fourteen_mission_types(self):
        from engine.missions import MissionType
        self.assertEqual(len(list(MissionType)), 14)
        self.assertIn("14 mission types", _guide_text())

    def test_partial_pay_is_flat_40_except_delivery(self):
        # The headline drift: every non-delivery type pays 0.40 on a partial.
        from engine.skill_checks import MISSION_SKILL_MAP
        for mtype, (_skill, frac) in MISSION_SKILL_MAP.items():
            if mtype == "delivery":
                self.assertEqual(frac, 1.00, "delivery should always pay full")
            else:
                self.assertEqual(
                    frac, 0.40,
                    f"{mtype} partial fraction drifted from 0.40 -> guide stale",
                )
        body = _guide_text()
        self.assertIn("40%", body)
        # The stale 75% partial cells must be gone from the type table.
        self.assertNotIn(f"| 75% |", body)

    def test_space_mission_pay_ranges_match_engine(self):
        from engine import missions
        from engine.missions import MissionType
        body = _guide_text()
        for mtype in (MissionType.PATROL, MissionType.ESCORT,
                      MissionType.INTERCEPT, MissionType.SURVEY_ZONE):
            lo, hi = missions.PAY_RANGES[mtype]
            self.assertIn(
                _range(lo, hi), body,
                f"{mtype.value} pay range {lo}-{hi} not reflected in the guide",
            )
        # Pin the actual values so a retune trips this too.
        self.assertEqual(missions.PAY_RANGES[MissionType.PATROL], (600, 1000))
        self.assertEqual(missions.PAY_RANGES[MissionType.ESCORT], (1500, 2500))
        self.assertEqual(missions.PAY_RANGES[MissionType.INTERCEPT], (2000, 3000))
        self.assertEqual(missions.PAY_RANGES[MissionType.SURVEY_ZONE], (1200, 1800))

    def test_completion_window_and_bonus(self):
        body = _guide_text()
        # Near-miss window is margin >= -2 (miss by <=2), not <=4.
        self.assertIn("missed by 2 or less", body)
        self.assertIn("+20%", body)
        self.assertNotIn("miss by " + chr(0x2264) + "4", body)  # no "miss by ≤4"


class BountyBoard(unittest.TestCase):
    """§3 — tiers, board size, track skills, archetypes."""

    def test_tier_pay_and_weights(self):
        from engine import bounty_board as bb
        from engine.bounty_board import BountyTier
        body = _guide_text()
        expected = {
            BountyTier.EXTRA: (100, 300, 5),
            BountyTier.AVERAGE: (300, 800, 4),
            BountyTier.NOVICE: (800, 1500, 3),
            BountyTier.VETERAN: (1500, 3000, 2),
            BountyTier.SUPERIOR: (3000, 10000, 1),
        }
        for tier, (lo, hi, weight) in expected.items():
            self.assertEqual(bb.PAY_RANGES[tier], (lo, hi))
            self.assertEqual(bb.TIER_WEIGHTS[tier], weight)
            self.assertIn(_range(lo, hi), body)

    def test_board_fills_to_four(self):
        from engine import bounty_board as bb
        self.assertEqual(bb.BOARD_SIZE, 4)
        self.assertEqual(bb.BOARD_MIN, 2)
        self.assertEqual(bb.REFRESH_SECONDS, 2700)
        body = _guide_text()
        self.assertIn("refills toward 4 contracts", body)
        self.assertNotIn("Board holds 3" + EN_DASH + "5", body)

    def test_track_uses_three_skills(self):
        body = _guide_text()
        self.assertIn("Search, Streetwise, or Tracking", body)

    def test_phantom_archetypes_dead(self):
        body = _guide_text()
        for phantom in ("B1 droids", "CIS agents", "Hutt enforcers"):
            self.assertNotIn(phantom, body, f"phantom archetype '{phantom}' resurfaced")
        # The real (era-mapped) military fugitive archetypes are present.
        self.assertIn("clone troopers", body)


class Smuggling(unittest.TestCase):
    """§4 — routes (era worlds), tiered fines, arrival patrol."""

    def test_routes_use_clone_wars_worlds(self):
        from engine.smuggling import ROUTE_TIERS
        # spicerun -> geonosis, corerun -> coruscant (Kessel/Corellia removed).
        self.assertEqual(ROUTE_TIERS["spicerun"][1], "geonosis")
        self.assertEqual(ROUTE_TIERS["corerun"][1], "coruscant")
        body = _guide_text()
        self.assertIn("Geonosis", body)
        self.assertIn("Coruscant", body)

    def test_no_era_removed_worlds_anywhere(self):
        body = _guide_text()
        self.assertNotIn("Kessel", body)
        self.assertNotIn("Corellia", body)

    def test_fine_is_tiered(self):
        from engine.smuggling import FINE_FRACTION_BY_TIER, CargoTier
        self.assertEqual(FINE_FRACTION_BY_TIER[CargoTier.GREY_MARKET], 0.50)
        self.assertEqual(FINE_FRACTION_BY_TIER[CargoTier.BLACK_MARKET], 0.50)
        self.assertEqual(FINE_FRACTION_BY_TIER[CargoTier.CONTRABAND], 0.25)
        self.assertEqual(FINE_FRACTION_BY_TIER[CargoTier.SPICE], 0.25)
        body = _guide_text()
        self.assertIn("**25%**", body)
        self.assertIn("25" + EN_DASH + "50% of job reward", body)  # the sink row

    def test_arrival_patrol_frequencies(self):
        from engine.smuggling import PLANET_PATROL_FREQUENCY
        self.assertEqual(PLANET_PATROL_FREQUENCY["coruscant"], 0.60)
        self.assertEqual(PLANET_PATROL_FREQUENCY["tatooine"], 0.10)
        body = _guide_text()
        self.assertIn("Coruscant (Republic capital)", body)


class CargoTrading(unittest.TestCase):
    """§5 — narrowed multipliers, no Corellia, no stale exploit."""

    def test_multipliers_are_narrowed(self):
        from engine.trading import PRICE_SOURCE, PRICE_DEMAND, TRADE_GOODS
        self.assertEqual(PRICE_SOURCE, 0.70)
        self.assertEqual(PRICE_DEMAND, 1.40)
        self.assertEqual(len(TRADE_GOODS), 8)
        body = _guide_text()
        self.assertIn("70%", body)
        self.assertIn("140%", body)
        # The stale 50%/200% spread must be gone.
        self.assertNotIn("200% price", body)

    def test_luxury_source_is_nar_shaddaa(self):
        from engine.trading import TRADE_GOODS
        self.assertEqual(TRADE_GOODS["luxury_goods"].source, ["nar_shaddaa"])

    def test_stale_exploit_number_removed(self):
        body = _guide_text()
        self.assertNotIn("240,000", body)


class MobHunting(unittest.TestCase):
    """§6 — confirmed-correct, pinned so it can't silently drift."""

    def test_reward_economy(self):
        from engine import hunting_rewards as hr
        self.assertEqual(hr.BASE_REWARD, 15)
        self.assertEqual(hr.DAILY_SOFT_CAP, 400)
        self.assertEqual(hr.OVER_CAP_FLOOR, 3)
        body = _guide_text()
        self.assertIn("15 cr", body)
        self.assertIn("400 cr", body)

    def test_title_thresholds(self):
        from engine.hunting_rewards import TITLE_THRESHOLDS
        self.assertEqual(
            TITLE_THRESHOLDS,
            [(25, "hunter"), (100, "seasoned_hunter"),
             (500, "master_hunter"), (2500, "apex_hunter")],
        )
        body = _guide_text()
        for _thresh, key in TITLE_THRESHOLDS:
            self.assertIn(key, body)


class OtherIncomeAndSinks(unittest.TestCase):
    """§7/§8/§10 — perform skill, fuel/docking/weapon ranges, sellback."""

    def test_perform_skill_not_perception(self):
        body = _guide_text()
        self.assertIn("Persuasion check", body)
        self.assertIn("Musical Instrument", body)
        self.assertNotIn("Perception-based check", body)

    def test_sink_ranges(self):
        body = _guide_text()
        self.assertIn("60" + EN_DASH + "100 cr", body)        # launch fuel
        self.assertIn("25" + EN_DASH + "7,000 cr", body)      # NPC weapons
        self.assertNotIn("275" + EN_DASH + "5,000 cr", body)  # stale weapon range
        self.assertNotIn("50" + EN_DASH + "100 cr", body)     # stale launch fuel

    def test_commissary_sellback(self):
        from engine.commissary import COMMISSARY_SELLBACK_RATE
        self.assertEqual(COMMISSARY_SELLBACK_RATE, 0.50)
        self.assertIn("50% refund", _guide_text())


class CreatureSpoils(unittest.TestCase):
    """§11 — DC, quality cap, no phantom swarm."""

    def test_spoils_constants(self):
        from engine import creature_spoils as cs
        self.assertEqual(cs.SPOILS_DIFFICULTY, 8)
        self.assertEqual(cs._SPOILS_QUALITY_CEILING, 65.0)

    def test_no_phantom_spor_swarm(self):
        body = _guide_text()
        self.assertNotIn("spor swarms", body)
        # The real no-yield nuisance creatures remain documented.
        self.assertIn("worrt", body)
        self.assertIn("shredder bat", body)


if __name__ == "__main__":
    unittest.main()
