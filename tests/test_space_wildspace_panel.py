# -*- coding: utf-8 -*-
"""
tests/test_space_wildspace_panel.py — T3.16 Drop 5: wildspace web-panel data

Verifies that build_space_state emits the wildspace panel fields and that
the client.html contains the new DOM elements + JS function.
"""
from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# ── helpers ───────────────────────────────────────────────────────────────────

def _client_html() -> str:
    return (PROJECT_ROOT / "static" / "client.html").read_text(encoding="utf-8")


# ── 1. Server payload fields ──────────────────────────────────────────────────

class TestWildspacePanelPayload(unittest.IsolatedAsyncioTestCase):
    """build_space_state includes wildspace fields."""

    def _make_zone(self, is_wildspace=True, theater="sieges"):
        z = MagicMock()
        z.name = "Geonosis Front"
        z.type = MagicMock(); z.type.value = "deep_space"
        z.desc = ""
        z.planet = None
        z.hazards = {}
        z.adjacent = []
        z.wildspace = is_wildspace
        z.wildspace_theater = theater if is_wildspace else None
        return z

    def _make_ship(self, zone_id="geonosis_front"):
        return {
            "id": 1, "name": "Shadowfast", "template": "light_freighter",
            "systems": json.dumps({"current_zone": zone_id}),
            "mods": "[]", "docked_at": None,
        }

    async def test_wildspace_zone_sets_is_wildspace_true(self):
        zone = self._make_zone(is_wildspace=True, theater="sieges")
        ship = self._make_ship("geonosis_front")
        from parser.space_commands import build_space_state
        db = MagicMock(); db.fetchone = MagicMock(return_value=None)
        sm = MagicMock()

        cache_pool = {"ore_node": MagicMock(kind="mining"),
                      "debris_field": MagicMock(kind="derelict")}

        with patch("engine.npc_space_traffic.ZONES", {"geonosis_front": zone}), \
             patch("engine.npc_space_traffic.get_space_security", return_value="lawless"), \
             patch("engine.starships.get_ship_registry", return_value={}), \
             patch("engine.starships.get_space_grid", return_value=MagicMock(get_ships_in_zone=MagicMock(return_value=[]))), \
             patch("engine.space_anomalies.get_anomalies_for_zone", return_value=[]), \
             patch("engine.starships.is_silent_running", return_value=False), \
             patch("engine.space_caches.get_cache_pool", return_value=cache_pool), \
             patch("engine.space_encounters.get_encounter_manager", side_effect=Exception("no enc")):
            state = await build_space_state(ship, char_id=1, db=db, session_mgr=sm)

        self.assertTrue(state["is_wildspace"])
        self.assertEqual(state["wildspace_theater"], "sieges")
        summary = state["wildspace_cache_summary"]
        kinds = {e["kind"] for e in summary}
        self.assertIn("mining", kinds)
        self.assertIn("derelict", kinds)

    async def test_non_wildspace_zone_sets_is_wildspace_false(self):
        zone = self._make_zone(is_wildspace=False, theater=None)
        ship = self._make_ship("coruscant_orbit")
        from parser.space_commands import build_space_state
        db = MagicMock()
        sm = MagicMock()

        with patch("engine.npc_space_traffic.ZONES", {"coruscant_orbit": zone}), \
             patch("engine.npc_space_traffic.get_space_security", return_value="safe"), \
             patch("engine.starships.get_ship_registry", return_value={}), \
             patch("engine.starships.get_space_grid", return_value=MagicMock(get_ships_in_zone=MagicMock(return_value=[]))), \
             patch("engine.space_anomalies.get_anomalies_for_zone", return_value=[]), \
             patch("engine.starships.is_silent_running", return_value=False), \
             patch("engine.space_encounters.get_encounter_manager", side_effect=Exception("no enc")):
            state = await build_space_state(ship, char_id=1, db=db, session_mgr=sm)

        self.assertFalse(state["is_wildspace"])
        self.assertIsNone(state["wildspace_theater"])
        self.assertEqual(state["wildspace_cache_summary"], [])

    async def test_ship_mod_fields_present_in_payload(self):
        """ship_mod_* keys are always present (zero values when no mods)."""
        zone = self._make_zone(is_wildspace=True)
        ship = self._make_ship("geonosis_front")
        from parser.space_commands import build_space_state
        db = MagicMock()
        sm = MagicMock()

        with patch("engine.npc_space_traffic.ZONES", {"geonosis_front": zone}), \
             patch("engine.npc_space_traffic.get_space_security", return_value="lawless"), \
             patch("engine.starships.get_ship_registry", return_value={}), \
             patch("engine.starships.get_space_grid", return_value=MagicMock(get_ships_in_zone=MagicMock(return_value=[]))), \
             patch("engine.space_anomalies.get_anomalies_for_zone", return_value=[]), \
             patch("engine.starships.is_silent_running", return_value=False), \
             patch("engine.space_caches.get_cache_pool", return_value={}), \
             patch("engine.space_encounters.get_encounter_manager", side_effect=Exception("no enc")):
            state = await build_space_state(ship, char_id=1, db=db, session_mgr=sm)

        for key in ("ship_mod_mining_pips", "ship_mod_mining_cd", "ship_mod_deep_mining",
                    "ship_mod_salvage_pips", "ship_mod_salvage_comp",
                    "ship_mod_intact_ext", "ship_mod_refinery"):
            self.assertIn(key, state, f"Missing key: {key}")


# ── 2. Client DOM elements ────────────────────────────────────────────────────

class TestWildspacePanelDOM(unittest.TestCase):
    """client.html has wildspace panel DOM + JS."""

    def setUp(self):
        self.html = _client_html()

    def test_wildspace_panel_div_exists(self):
        self.assertIn('id="wildspace-panel"', self.html)

    def test_theater_badge_element_exists(self):
        self.assertIn('id="ws-theater-badge"', self.html)

    def test_cache_row_element_exists(self):
        self.assertIn('id="ws-cache-row"', self.html)

    def test_mods_element_exists(self):
        self.assertIn('id="ws-mods"', self.html)

    def test_update_wildspace_panel_js_function_defined(self):
        self.assertIn('function updateWildspacePanel(', self.html)

    def test_update_called_from_handle_space_state(self):
        self.assertIn('updateWildspacePanel(data)', self.html)

    def test_css_theater_badge_class(self):
        self.assertIn('.wildspace-theater-badge', self.html)

    def test_css_wc_badge_class(self):
        self.assertIn('.wc-badge', self.html)

    def test_css_ws_mod_row_class(self):
        self.assertIn('.ws-mod-row', self.html)

    def test_panel_hidden_by_default(self):
        # Panel must default to display:none
        idx = self.html.find('id="wildspace-panel"')
        snippet = self.html[max(0, idx-50):idx+100]
        self.assertIn('display:none', snippet)


if __name__ == "__main__":
    unittest.main()
