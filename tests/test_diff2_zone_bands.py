# -*- coding: utf-8 -*-
"""
tests/test_diff2_zone_bands.py — DIFF.2 zone labeling + UI surfacing.

Per difficulty_tiers_design_v1.md §5/§8. Pins:
  - every CW zone carries a valid threat_band in its properties;
  - no zone violates frontier≠lawless;
  - the chain starting zones resolve to the bands the design assigns;
  - the threat_band YAML insertion stayed additive (the file still
    parses and every zone still has its security property).

The runtime `look` header tag + `+threat` command are smoke-verified in
tests/smoke/scenarios/era_clone_wars.py-adjacent coverage; this file is
the data/static layer.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

ZONES_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "zones.yaml")

_VALID_BANDS = {"frontier", "settled", "contested_marches", "wilds"}


def _zones() -> dict:
    with open(ZONES_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)["zones"]


class TestEveryZoneHasValidBand(unittest.TestCase):

    def test_every_zone_has_a_threat_band(self):
        missing = []
        for slug, z in _zones().items():
            props = z.get("properties") or {}
            if "threat_band" not in props:
                missing.append(slug)
        self.assertEqual(
            missing, [],
            f"DIFF.2: zones missing a threat_band: {missing}")

    def test_every_band_value_is_valid(self):
        bad = []
        for slug, z in _zones().items():
            band = (z.get("properties") or {}).get("threat_band")
            if band not in _VALID_BANDS:
                bad.append((slug, band))
        self.assertEqual(
            bad, [],
            f"DIFF.2: invalid threat_band values: {bad}")

    def test_security_property_still_present(self):
        """The additive insertion must not have clobbered the existing
        security property on any zone."""
        missing = []
        for slug, z in _zones().items():
            props = z.get("properties") or {}
            if "security" not in props:
                missing.append(slug)
        self.assertEqual(
            missing, [],
            f"DIFF.2: zones lost their security property: {missing}")


class TestNoFrontierLawlessConflict(unittest.TestCase):

    def test_no_zone_is_frontier_and_lawless(self):
        from engine.threat_band import frontier_lawless_conflict
        offenders = []
        for slug, z in _zones().items():
            props = z.get("properties") or {}
            if frontier_lawless_conflict(props.get("threat_band"),
                                         props.get("security")):
                offenders.append(slug)
        self.assertEqual(
            offenders, [],
            f"DIFF.2: zones violate frontier≠lawless: {offenders}")


class TestStartingZonesAreSafeBands(unittest.TestCase):
    """The 7 unlocked chains' starting zones must be low-threat
    (Frontier or Settled) so the onboarding chains run in safe water —
    a graduating newbie should not be dropped straight into the Wilds."""

    # chain_id → starting zone (from chains.yaml starting rooms; verified
    # against the world build).
    _START_ZONES = {
        "republic_soldier": "kamino_tipoca_city",
        "republic_intelligence": "monumental_district",
        "separatist_commando": "geonosis_foundries",
        "separatist_agent": "southern_underground",
        "bounty_hunter": "nar_shaddaa_promenade",
        "smuggler": "tatooine_spaceport",
        "shipwright_trader": "kuat_main_spaceport",
    }

    def test_starting_zones_are_frontier_or_settled(self):
        zones = _zones()
        too_hot = []
        for chain, zslug in self._START_ZONES.items():
            band = (zones.get(zslug, {}).get("properties") or {}).get(
                "threat_band")
            if band not in ("frontier", "settled"):
                too_hot.append((chain, zslug, band))
        self.assertEqual(
            too_hot, [],
            f"DIFF.2: chain starting zones too dangerous for newbies "
            f"(must be frontier/settled): {too_hot}")


class TestBandDistribution(unittest.TestCase):
    """Sanity: the world should USE the full band range — at least one
    zone in each band — so the difficulty gradient actually exists."""

    def test_all_four_bands_used(self):
        used = {(z.get("properties") or {}).get("threat_band")
                for z in _zones().values()}
        for band in _VALID_BANDS:
            self.assertIn(
                band, used,
                f"DIFF.2: no zone uses the {band!r} band — the gradient "
                f"is incomplete.")


if __name__ == "__main__":
    unittest.main()
