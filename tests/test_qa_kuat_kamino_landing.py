# -*- coding: utf-8 -*-
"""
tests/test_qa_kuat_kamino_landing.py — QA break-it: kuat/kamino landing
(2026-06-20).

The break-it campaign found that landing a ship from `kuat_orbit` or
`kamino_orbit` dumped it on **Tatooine** (Docking Bay 94). Root cause:
`LandCommand`'s `_BAY_SEARCH` (parser/space_commands.py) mapped only
tatooine/nar_shaddaa/coruscant/geonosis, so kuat + kamino fell through to
the generic `"Docking Bay"` query and `find_rooms` returned Tatooine's bay
first. Cascade: relaunching from the Tatooine bay then defaulted to
`coruscant_orbit` (a third planet).

Fix: add kuat + kamino to `_BAY_SEARCH` with landing rooms whose names
carry the planet token, so the reverse `get_orbit_zone_for_room` mapping
(`bay_planet_map`: kuat->kuat_orbit, kamino/tipoca->kamino_orbit) round-trips
on relaunch.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import unittest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class TestBaySearchHasKuatKamino(unittest.TestCase):
    def setUp(self):
        self.src = (PROJECT_ROOT / "parser" / "space_commands.py").read_text(
            encoding="utf-8"
        )

    def _bay_search_block(self) -> str:
        m = re.search(r"_BAY_SEARCH\s*=\s*\{(.*?)\}", self.src, re.S)
        self.assertIsNotNone(m, "_BAY_SEARCH dict not found")
        return m.group(1)

    def test_kuat_and_kamino_present(self):
        block = self._bay_search_block()
        self.assertIn('"kuat"', block,
                      "kuat must have a docking-bay search (else it lands on Tatooine)")
        self.assertIn('"kamino"', block,
                      "kamino must have a docking-bay search (else it lands on Tatooine)")

    def test_bay_rooms_carry_planet_token(self):
        """The chosen landing rooms must contain their planet token so the
        reverse get_orbit_zone_for_room mapping round-trips (no cascade)."""
        block = self._bay_search_block()
        self.assertRegex(block, r'"kuat"\s*:\s*"Kuat[^"]*"')
        self.assertRegex(block, r'"kamino"\s*:\s*"Kamino[^"]*"')


class TestOrbitRoundTrip(unittest.TestCase):
    """The reverse mapping must send a ship that landed at the kuat/kamino
    bay back to the matching orbit (not the coruscant_orbit default)."""

    def test_landing_rooms_map_back_to_their_orbit(self):
        from engine import npc_space_traffic as nst
        try:
            from engine.era_state import set_active_era
            set_active_era("clone_wars")
        except Exception:
            pass
        nst.reload_zone_graph()
        cases = {
            "Kuat - Main Spaceport Arrivals": "kuat_orbit",
            "Kamino - Landing Platform Alpha": "kamino_orbit",
        }
        for room, want in cases.items():
            got = nst.get_orbit_zone_for_room(room)
            self.assertEqual(
                got, want,
                f"relaunching from {room!r} must orbit {want} (got {got}) — "
                f"a wrong value is the cross-planet cascade bug."
            )

    def test_cw_bay_planet_map_has_kuat_kamino(self):
        import yaml
        zpath = (PROJECT_ROOT / "data" / "worlds" / "clone_wars"
                 / "space_zones.yaml")
        raw = yaml.safe_load(zpath.read_text(encoding="utf-8")) or {}
        bpm = raw.get("bay_planet_map", {})
        self.assertEqual(bpm.get("kuat"), "kuat_orbit")
        self.assertEqual(bpm.get("kamino"), "kamino_orbit")


if __name__ == "__main__":
    unittest.main()
