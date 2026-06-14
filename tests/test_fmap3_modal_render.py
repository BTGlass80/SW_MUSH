# -*- coding: utf-8 -*-
"""
tests/test_fmap3_modal_render.py — F.MAP.3 modal renderer wiring.

F.MAP.3 (May 5 2026) extended the expanded map modal to use the
F.MAP.1 MapView renderer when an AreaGeometry is cached for the
player's current area. The legacy clone-and-scale path is preserved
as fallback for non-covered areas.

Tests verify the wiring is present in client.html — same structural
pattern as test_session46_map_expand.py. The actual visual behavior
is covered by the smoke harness in tools/_smoke_fmap3_modal.py
(sandbox-only, not part of the suite).
"""
from __future__ import annotations

import os
import re
import unittest

import pytest

pytestmark = pytest.mark.slow  # heavy: regex scans over full client.html

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
CLIENT_HTML = os.path.join(PROJECT_ROOT, "static", "client.html")


class FMap3ModalWiringTests(unittest.TestCase):
    """Structural checks that F.MAP.3 modal wiring is present."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLIENT_HTML):
            raise unittest.SkipTest(f"client.html not found at {CLIENT_HTML}")
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    # ── Tier rail HTML ─────────────────────────────────────────────────

    def test_tier_rail_container_exists(self):
        """The tier rail sits in the modal head between the sub-title
        and the close button. Hidden by default; openMapModal flips
        it on for ground when AreaGeometry is cached."""
        self.assertIn('id="map-modal-tier-rail"', self.html)

    def test_tier_1_button_exists(self):
        self.assertRegex(
            self.html,
            r'<button class="mm-tier-btn"[^>]*data-tier="1"[^>]*onclick="setMapModalTier\(1\)"',
        )

    def test_tier_2_button_exists(self):
        self.assertRegex(
            self.html,
            r'<button class="mm-tier-btn"[^>]*data-tier="2"[^>]*onclick="setMapModalTier\(2\)"',
        )

    def test_tier_button_labels_match_design(self):
        """Labels per design-handoff Map_Redesign_v2.html — TIER 1 ·
        DISTRICT and TIER 2 · CITY."""
        self.assertIn("TIER 1 · DISTRICT", self.html)
        self.assertIn("TIER 2 · CITY", self.html)

    # ── Tier rail CSS ──────────────────────────────────────────────────

    def test_tier_rail_css_class_styled(self):
        # The rail should be flex-arranged
        self.assertRegex(
            self.html,
            r"\.map-modal-head \.mm-tier-rail \{[^}]*display:\s*flex",
        )

    def test_tier_button_active_state_styled(self):
        """Active tier button uses cock-amber for color + border, with
        a subtle background tint. Locked down so the visual signal
        (which tier is selected) doesn't drift."""
        self.assertRegex(
            self.html,
            r"\.map-modal-head \.mm-tier-btn\.active \{[^}]*cock-amber",
        )

    # ── openMapModal: tier rail visibility logic ──────────────────────

    def test_openMapModal_hides_rail_for_space(self):
        """Space modal (tactical radar) doesn't have tiers — must
        keep the rail hidden."""
        # Space branch sets display='none' on the rail
        self.assertRegex(
            self.html,
            r"if \(kind === 'space'\)[\s\S]{0,2000}rail\.style\.display = 'none'",
        )

    def test_openMapModal_shows_rail_only_when_geometry_cached(self):
        """Ground modal: rail visible only when window._sw_areaGeom and
        window.MapView are both present. Without geometry the modal
        falls back to the legacy clone-and-scale path which has no tier
        concept — showing tier buttons that do nothing would confuse."""
        self.assertRegex(
            self.html,
            r"rail\.style\.display = \(window\._sw_areaGeom &&[\s\S]{0,200}'flex' : 'none'",
        )

    # ── renderMapModal: branch on AreaGeometry cache ──────────────────

    def test_renderMapModal_branches_to_v2_path(self):
        """When ground + geometry + MapView are all available,
        renderMapModal calls _renderMapModalV2 and skips the legacy
        clone-and-scale path."""
        self.assertRegex(
            self.html,
            r"if \(kind === 'ground' && window\._sw_areaGeom &&[\s\S]{0,200}_renderMapModalV2",
        )

    def test_renderMapModal_legacy_path_preserved(self):
        """The legacy clone-and-scale path (cloneNode + label scale +
        collision resolve) must still be reachable for non-covered
        areas. Probe a few unique markers from the legacy logic."""
        self.assertIn("_resolveModalLabelCollisions", self.html)
        self.assertIn("PAD_FACTOR", self.html)
        self.assertIn("LABEL_SCALE", self.html)

    # ── _renderMapModalV2: tier-aware opts ────────────────────────────

    def test_renderMapModalV2_uses_full_bounds_viewbox(self):
        """The modal viewBox is the area's full bounds — NOT the
        mini's tier-1 player crop. Confirm the function reads
        geom.bounds and constructs vbX/vbY/vbW/vbH from it.

        Window widened from 500 to 2000 chars: Drop 4.2b inserted the
        M3 composition-engine short-circuit branch (m3Ready check +
        _renderModalViaM3 call) ahead of the legacy bounds computation.
        The M3 branch doesn't touch geom.bounds, so bounds extraction
        legitimately sits ~1.2k chars past the function open now. The
        test's intent — 'the function derives the viewBox from
        geom.bounds' — is unchanged."""
        self.assertRegex(
            self.html,
            r"function _renderMapModalV2\([^)]*\)\s*\{[\s\S]{0,2000}geom\.bounds",
        )

    def test_renderMapModalV2_tier_1_uses_full_room_mode(self):
        """Tier 1 (default) shows full room footprints, district
        labels OFF (per design — district labels light up at tier 2)."""
        m = re.search(
            r"if \(tier === 2\) \{([\s\S]+?)\} else \{([\s\S]+?)\}",
            self.html,
        )
        self.assertIsNotNone(m, "tier branch in _renderMapModalV2 not found")
        tier1_block = m.group(2)
        self.assertIn("'full'", tier1_block)
        self.assertIn("showDistrictLabels: false", tier1_block)

    def test_renderMapModalV2_tier_2_uses_dot_mode_with_district_labels(self):
        """Tier 2 (city) collapses rooms to dots, district labels ON,
        landmarks pop."""
        m = re.search(
            r"if \(tier === 2\) \{([\s\S]+?)\} else \{",
            self.html,
        )
        self.assertIsNotNone(m, "tier-2 block not found")
        tier2_block = m.group(1)
        self.assertIn("'dot'", tier2_block)
        self.assertIn("showDistrictLabels: true", tier2_block)
        self.assertIn("zoomTier:           2", tier2_block)

    # ── setMapModalTier: re-render + button highlight ────────────────

    def test_setMapModalTier_validates_input(self):
        """Only tier 1 and tier 2 are valid — anything else is a no-op."""
        self.assertRegex(
            self.html,
            r"function setMapModalTier\(tier\)[\s\S]{0,200}if \(tier !== 1 && tier !== 2\) return",
        )

    def test_setMapModalTier_short_circuits_when_unchanged(self):
        """Clicking the already-active tier shouldn't re-render."""
        self.assertRegex(
            self.html,
            r"if \(mapModalCurrentTier === tier\) return",
        )

    def test_setMapModalTier_re_renders_via_v2(self):
        """Re-render goes through _renderMapModalV2, NOT the legacy
        path. Locks down that switching tiers in the modal can't
        accidentally fall back to the clone-scale logic."""
        self.assertRegex(
            self.html,
            r"function setMapModalTier\(tier\)[\s\S]{0,800}_renderMapModalV2\(",
        )

    def test_setMapModalTier_skips_when_no_geometry(self):
        """Defensive: if the modal got opened in legacy mode (no
        cached geometry) and somebody calls setMapModalTier
        externally, it must no-op rather than try to render."""
        self.assertRegex(
            self.html,
            r"function setMapModalTier\([\s\S]{0,500}window\._sw_areaGeom",
        )

    # ── Tier button highlight ─────────────────────────────────────────

    def test_updateModalTierButtons_function_exists(self):
        self.assertIn("function _updateModalTierButtons(", self.html)

    def test_updateModalTierButtons_sets_active_class(self):
        self.assertRegex(
            self.html,
            r"function _updateModalTierButtons\(tier\)[\s\S]{0,400}b\.classList\.toggle\('active', t === tier\)",
        )

    # ── Tooling export ─────────────────────────────────────────────────

    def test_setMapModalTier_exposed_to_window(self):
        """For the smoke harness (tools/_smoke_fmap3_modal.py) and
        in-browser debug. setMapModalTier is IIFE-scoped otherwise."""
        self.assertRegex(
            self.html,
            r"window\.setMapModalTier\s*=\s*setMapModalTier",
        )

    # ── Module state initialization ───────────────────────────────────

    def test_tier_state_variable_initialized(self):
        """Default tier is 1 (district view). Persists across
        modal open/close — opening at the same tier is a feature
        once Brian gets used to it."""
        self.assertRegex(
            self.html,
            r"var mapModalCurrentTier\s*=\s*1",
        )


class FMap3LegacyPathPreservation(unittest.TestCase):
    """Negative tests — F.MAP.3 must NOT have broken any legacy modal
    path. Mirrors a subset of test_session46_map_expand.py to make
    sure the legacy chrome/handlers still wire up the same way."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLIENT_HTML):
            raise unittest.SkipTest(f"client.html not found at {CLIENT_HTML}")
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    def test_modal_overlay_still_exists(self):
        self.assertIn('id="map-modal-overlay"', self.html)

    def test_modal_close_button_still_wired(self):
        self.assertIn('onclick="closeMapModal()"', self.html)

    def test_modal_backdrop_click_handler_still_wired(self):
        self.assertIn('onclick="mapModalBackdropClick(event)"', self.html)

    def test_legacy_render_function_still_exists(self):
        self.assertIn("function renderMapModal(", self.html)

    def test_space_modal_still_uses_radar_clone(self):
        """Space modal must NOT route through MapView (different
        renderer entirely). Confirm the kind=='space' path still
        clones #s-radar-svg."""
        # The legacy path's srcId resolution
        self.assertRegex(
            self.html,
            r"var srcId = \(kind === 'space'\) \? 's-radar-svg'",
        )


if __name__ == "__main__":
    unittest.main()
