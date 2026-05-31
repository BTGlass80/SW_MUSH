# -*- coding: utf-8 -*-
"""
tests/test_fmap6_client_dispatch.py — F.MAP.6 client.html structural
tests for contacts handling.

Verifies the client-side wiring is in place:
  1. The HUD update handler reads `data.contacts` and stamps it on
     `window._sw_areaGeom.contacts` in BOTH the full-refresh branch
     (area transition) AND the steady-state branch (position update).
  2. The modal is re-rendered when contacts change AND the modal is
     open (so the modal stays in sync).
  3. Array.isArray() guards every read — defensive against malformed
     payloads.
"""
from __future__ import annotations

import os
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
CLIENT_HTML = os.path.join(PROJECT_ROOT, "static", "client.html")


class FMap6ClientDispatchTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLIENT_HTML):
            raise unittest.SkipTest(f"client.html not found at {CLIENT_HTML}")
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_contacts_read_in_full_refresh_branch(self):
        """The area_geometry branch must stamp data.contacts onto the
        cached geom. Without this, the renderer keeps the stale
        contact list from the previous area."""
        # Pattern: "Array.isArray(data.contacts)" appearing inside the
        # area_geometry branch
        self.assertIn(
            "Array.isArray(data.contacts)",
            self.html,
            "contacts must be read via Array.isArray guard",
        )
        self.assertIn(
            "window._sw_areaGeom.contacts = data.contacts",
            self.html,
            "contacts must be stamped on cached geom",
        )

    def test_contacts_read_in_steady_state_branch(self):
        """The player_position-only branch (per-tick steady-state) must
        ALSO update contacts — they change every tick when other
        people enter/leave the area."""
        # The pattern should appear at least twice in the file:
        # once in each branch.
        self.assertGreaterEqual(
            self.html.count("Array.isArray(data.contacts)"),
            2,
            "contacts handling must appear in both full-refresh and "
            "steady-state branches",
        )

    def test_modal_resync_on_full_refresh(self):
        """When the modal is open and a new geometry/contacts pushes,
        the modal must re-render too — otherwise it drifts out of
        sync with the live mini-map."""
        self.assertRegex(
            self.html,
            r"if \(mapModalOpen[\s\S]{0,400}_renderMapModalV2",
        )

    def test_modal_uses_current_tier(self):
        """When re-rendering the modal, must pass mapModalCurrentTier
        — re-rendering at tier 1 when the user had selected tier 2
        would silently revert their choice."""
        self.assertIn(
            "_renderMapModalV2(body, window._sw_areaGeom, mapModalCurrentTier)",
            self.html,
        )

    def test_player_position_guarded_by_area_match(self):
        """Cross-area position updates (without a fresh area_geometry)
        must NOT stamp contacts — the cached geom is for the wrong
        area. The guard is `data.player_position.area_key === window._sw_areaGeom.area_key`."""
        self.assertRegex(
            self.html,
            r"data\.player_position\.area_key === window\._sw_areaGeom\.area_key",
        )


if __name__ == "__main__":
    unittest.main()
