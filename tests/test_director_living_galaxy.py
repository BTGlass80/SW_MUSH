# -*- coding: utf-8 -*-
"""tests/test_director_living_galaxy.py — DIRECTOR.zonestate_cw_faction_axis
(Brian 2026-06-13, Option A: native CW axis rewrite + multi-zone load).

The blocker this drop clears: the Director tracked 6 hardcoded Mos Eisley
zone keys that did not match the CW config keys, and ZoneState hardcoded the
GCW axis (imperial/rebel/criminal/independent). So every CW set_faction()
silently orphaned, and compute_alert() read a stale imperial=50 default —
EVERY zone computed the same wrong alert (HIGH_ALERT). After this drop:

  * VALID_ZONES is the full era config zone set (34 in CW).
  * ZoneState holds a faction-agnostic `scores` dict keyed by the era's
    VALID_FACTIONS, and compute_alert() reads the three alert axes
    (authority/warfront/underworld) resolved from the config rewicker.
  * The galaxy is DIFFERENTIATED — zones read distinct, sensible alerts.

These pins guard against a regression back to the stale-default bug and the
"every zone the same" degeneracy.
"""
from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _zone_from_config(zone_key):
    """Build a seeded ZoneState exactly the way ensure_loaded() does."""
    from engine.director import ZoneState, VALID_FACTIONS, DEFAULT_INFLUENCE
    zs = ZoneState(zone_key=zone_key)
    defaults = DEFAULT_INFLUENCE.get(zone_key, {})
    for f in VALID_FACTIONS:
        zs.set_faction(f, defaults.get(f, 30))
    zs.compute_alert()
    return zs


class TestAlertAxisResolution(unittest.TestCase):
    def test_axes_resolve_to_cw_factions(self):
        from engine.director import ALERT_AXIS, VALID_FACTIONS
        # CW config rewicker maps imperial->republic, rebel->cis,
        # criminal->hutt_cartel. Each resolved axis must be a real era faction.
        self.assertEqual(ALERT_AXIS["authority"], "republic")
        self.assertEqual(ALERT_AXIS["warfront"], "cis")
        self.assertEqual(ALERT_AXIS["underworld"], "hutt_cartel")
        for role, faction in ALERT_AXIS.items():
            self.assertIn(faction, VALID_FACTIONS, f"{role} axis not a faction")


class TestMultiZoneLoad(unittest.TestCase):
    def test_valid_zones_is_the_full_config(self):
        from engine.director import VALID_ZONES, DEFAULT_INFLUENCE
        self.assertEqual(set(VALID_ZONES), set(DEFAULT_INFLUENCE.keys()))
        # Sanity: the CW config is the full galaxy, not the legacy 6.
        self.assertGreaterEqual(len(VALID_ZONES), 30)

    def test_no_stale_mos_eisley_only_keys(self):
        from engine.director import VALID_ZONES
        # The legacy keys that never matched the CW config are gone.
        self.assertNotIn("government", VALID_ZONES)
        self.assertNotIn("jabba", VALID_ZONES)


class TestZoneStateScoresDict(unittest.TestCase):
    def test_get_set_roundtrip_and_clamp(self):
        from engine.director import ZoneState, MIN_INFLUENCE, MAX_INFLUENCE
        zs = ZoneState(zone_key="z")
        self.assertEqual(zs.get_faction("republic"), 0)   # empty -> 0
        zs.set_faction("republic", 80)
        self.assertEqual(zs.get_faction("republic"), 80)
        zs.set_faction("republic", 999)                   # clamp high
        self.assertEqual(zs.get_faction("republic"), MAX_INFLUENCE)
        zs.set_faction("republic", -5)                    # clamp low
        self.assertEqual(zs.get_faction("republic"), MIN_INFLUENCE)

    def test_scores_is_a_dict_not_hardcoded_attrs(self):
        from engine.director import ZoneState
        zs = ZoneState(zone_key="z")
        self.assertIsInstance(zs.scores, dict)
        # No hardcoded GCW attributes survive the native rewrite.
        self.assertFalse(hasattr(zs, "imperial"))
        self.assertFalse(hasattr(zs, "criminal"))


class TestComputeAlertNativeSemantics(unittest.TestCase):
    """The original-bug repro + the native CW alert mapping."""

    def test_repro_set_republic_yields_lockdown_not_stale_default(self):
        # THE bug: set_faction('republic',80) used to leave imperial=50 and
        # compute_alert returned HIGH_ALERT off the stale default. Now it
        # must read the real authority influence -> LOCKDOWN.
        from engine.director import ZoneState, AlertLevel
        zs = ZoneState(zone_key="z")
        zs.set_faction("republic", 80)
        self.assertEqual(zs.compute_alert(), AlertLevel.LOCKDOWN)

    def test_axis_thresholds(self):
        from engine.director import ZoneState, AlertLevel
        cases = [
            ({"republic": 75}, AlertLevel.LOCKDOWN),     # authority >= 70
            ({"republic": 55}, AlertLevel.HIGH_ALERT),   # authority 50-69
            ({"hutt_cartel": 80}, AlertLevel.UNDERWORLD),  # underworld >= 70
            ({"cis": 50}, AlertLevel.UNREST),            # warfront >= 40
            ({"independent": 60}, AlertLevel.LAX),       # no threat axis
            ({"republic": 35, "cis": 20, "hutt_cartel": 45}, AlertLevel.STANDARD),
        ]
        for scores, expected in cases:
            zs = ZoneState(zone_key="z")
            for f, v in scores.items():
                zs.set_faction(f, v)
            self.assertEqual(zs.compute_alert(), expected, f"{scores}")

    def test_jedi_order_and_bhg_are_overlays_not_alert_drivers(self):
        # A pure Jedi/bhg spike with no authority/warfront/underworld must
        # not by itself raise a dramatic alert (they are atmospheric in v1).
        from engine.director import ZoneState, AlertLevel
        zs = ZoneState(zone_key="z")
        zs.set_faction("jedi_order", 95)
        zs.set_faction("bhg", 60)
        self.assertIn(zs.compute_alert(),
                      (AlertLevel.LAX, AlertLevel.STANDARD))


class TestGalaxyIsDifferentiated(unittest.TestCase):
    """Guards the 'every zone reads the same wrong alert' degeneracy."""

    def test_config_zones_span_multiple_alert_levels(self):
        from engine.director import VALID_ZONES
        levels = Counter(
            _zone_from_config(zk).alert_level for zk in VALID_ZONES)
        # A living galaxy: at least 4 distinct alert levels in play.
        self.assertGreaterEqual(len(levels), 4, dict(levels))

    def test_representative_zones_read_correctly(self):
        from engine.director import AlertLevel
        expect = {
            "senate_district": AlertLevel.LOCKDOWN,      # Republic capital
            "kamino_tipoca": AlertLevel.LOCKDOWN,        # restricted military
            "geonosis_foundries": AlertLevel.UNREST,     # CIS warfront
            "nar_shaddaa_promenade": AlertLevel.UNDERWORLD,  # Hutt turf
            "tatooine_mos_eisley": AlertLevel.UNDERWORLD,
            "tatooine_dune_sea": AlertLevel.LAX,         # backwater
        }
        for zk, lvl in expect.items():
            self.assertEqual(_zone_from_config(zk).alert_level, lvl, zk)


class TestMissionBiasBaselineNeutral(unittest.TestCase):
    """missions._pick_type biases only when a dramatic alert holds >=40% of
    zones; the baseline galaxy must be neutral (no permanent spawn skew)."""

    def test_no_dramatic_level_dominates_baseline(self):
        from engine.director import VALID_ZONES, AlertLevel
        levels = [_zone_from_config(zk).alert_level for zk in VALID_ZONES]
        n = len(levels)
        for lvl in (AlertLevel.LOCKDOWN, AlertLevel.UNDERWORLD,
                    AlertLevel.UNREST):
            share = sum(1 for x in levels if x == lvl) / n
            self.assertLess(share, 0.4,
                            f"{lvl.value} share {share:.2f} would skew spawns")


class TestLocalDeltasAreEraCorrect(unittest.TestCase):
    def test_smuggling_boosts_underworld_axis(self):
        from engine.director import DirectorAI, ZoneState, ALERT_AXIS
        d = DirectorAI()
        zs = ZoneState(zone_key="tatooine_mos_eisley")
        zs.set_faction(ALERT_AXIS["underworld"], 50)
        zs.set_faction(ALERT_AXIS["authority"], 40)
        d._zones["tatooine_mos_eisley"] = zs
        d._digest.record_mission("smuggling")
        before = zs.get_faction(ALERT_AXIS["underworld"])
        d.apply_player_action_deltas()        # must not raise on dict scores
        after = zs.get_faction(ALERT_AXIS["underworld"])
        self.assertGreater(after, before)


if __name__ == "__main__":
    unittest.main()
