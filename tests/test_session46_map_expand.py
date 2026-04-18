"""
Session 46 regression test — map expand modal is present and wired.

Bug observed: the Field Kit client shipped without the fullscreen map
expand that the legacy client had. The tactical radar is ~140px tall
with 4–5px SVG labels; at that size contact names are unreadable. The
ground sector map has the same problem.

The fix restored a shared map modal overlay with variant theming
(amber for ground, cyan for space), click-to-expand via ⛶ buttons on
each mini-map, ESC key dismissal, and backdrop click dismissal.

This test does a series of structural grep-checks against the patched
client.html to confirm all the moving pieces are wired. It's deliberately
text-based rather than running a headless browser — the shape we're
locking down is exactly pattern-detectable, and the JS already passes
`node --check` in the packaging step.
"""
import os
import re
import unittest


HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
CLIENT_HTML = os.path.join(PROJECT_ROOT, "static", "client.html")


class MapExpandModalTests(unittest.TestCase):
    """Lock in every piece of the map-expand feature."""

    @classmethod
    def setUpClass(cls):
        if not os.path.isfile(CLIENT_HTML):
            raise unittest.SkipTest(f"client.html not found at {CLIENT_HTML}")
        with open(CLIENT_HTML, encoding="utf-8") as f:
            cls.html = f.read()

    # ── DOM: modal overlay + inner modal + header + body + legend ────

    def test_modal_overlay_element_exists(self):
        self.assertIn(
            'id="map-modal-overlay"',
            self.html,
            "The map-modal-overlay element is the shared backdrop/container.",
        )

    def test_modal_inner_exists(self):
        self.assertIn('id="map-modal"', self.html)

    def test_modal_has_title_and_sub_and_legend_nodes(self):
        self.assertIn('id="map-modal-title"',  self.html)
        self.assertIn('id="map-modal-sub"',    self.html)
        self.assertIn('id="map-modal-legend"', self.html)
        self.assertIn('id="map-modal-body"',   self.html)

    def test_modal_close_button_wired(self):
        self.assertRegex(
            self.html,
            r'onclick="closeMapModal\(\)"',
            msg="Close button must call closeMapModal().",
        )

    def test_backdrop_click_handler_wired(self):
        self.assertIn('onclick="mapModalBackdropClick(event)"', self.html)

    # ── Expand buttons on each mini-map ──────────────────────────────

    def test_space_radar_has_expand_button(self):
        self.assertRegex(
            self.html,
            r'onclick="openMapModal\(\'space\'\)',
            msg="Tactical strip must have a ⛶ button that opens the space modal.",
        )

    def test_ground_sector_map_has_expand_button(self):
        self.assertRegex(
            self.html,
            r'onclick="openMapModal\(\'ground\'\)',
            msg="Sector map frame must have a ⛶ button that opens the ground modal.",
        )

    # ── CSS: overlay + modal + variant + expand button classes ──────

    def test_css_has_overlay_rule(self):
        self.assertIn(".map-modal-overlay", self.html)
        self.assertIn(".map-modal-overlay.show", self.html)

    def test_css_has_variant_ground_rule(self):
        self.assertIn(".map-modal.variant-ground", self.html)

    def test_css_has_expand_button_rule(self):
        self.assertIn(".map-expand-btn", self.html)

    def test_css_has_responsive_rule(self):
        # The @media (max-width: 900px) rule makes the modal fullscreen
        # on mobile. Guard against it being stripped.
        self.assertRegex(self.html, r"@media\s*\(\s*max-width:\s*900px\s*\)")

    # ── JS: every entry-point function ───────────────────────────────

    def test_js_function_open_map_modal_exists(self):
        self.assertIn("function openMapModal(kind)", self.html)

    def test_js_function_close_map_modal_exists(self):
        self.assertIn("function closeMapModal()", self.html)

    def test_js_function_render_map_modal_exists(self):
        self.assertIn("function renderMapModal(kind)", self.html)

    def test_js_function_backdrop_click_exists(self):
        self.assertIn("function mapModalBackdropClick(evt)", self.html)

    def test_js_open_branches_on_kind(self):
        """openMapModal must handle both 'space' and 'ground' kinds."""
        # Find body of openMapModal (brace-counting)
        start = self.html.find("function openMapModal(kind)")
        self.assertNotEqual(start, -1)
        brace = self.html.find("{", start)
        depth = 0
        end = brace
        for i in range(brace, len(self.html)):
            if self.html[i] == "{":
                depth += 1
            elif self.html[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        body = self.html[brace:end]
        self.assertIn("'space'", body)
        self.assertIn("'ground'", body)
        # Must toggle the variant-ground class for ground view
        self.assertIn("variant-ground", body)

    # ── ESC handler + click-to-expand listener ───────────────────────

    def test_esc_key_handler_installed(self):
        """A keydown listener must dismiss the modal on Escape."""
        # Look for the installation IIFE and the Escape key comparison.
        self.assertIn("installMapModalKeyHandler", self.html)
        self.assertRegex(self.html, r"e\.key\s*===\s*'Escape'")

    def test_click_to_expand_listener_installed(self):
        """Clicking the mini-map SVG should also open the modal."""
        self.assertIn("installMapClickToExpand", self.html)
        # The listener should bind to both the radar and the ground map.
        self.assertIn("s-radar-svg", self.html)
        self.assertIn("g-area-map-svg", self.html)

    # ── renderMapModal must clone the live SVG ───────────────────────

    def test_render_clones_live_svg(self):
        start = self.html.find("function renderMapModal(kind)")
        self.assertNotEqual(start, -1)
        # cloneNode(true) is the load-bearing mechanism
        body = self.html[start : start + 3000]
        self.assertIn(
            "cloneNode(true)",
            body,
            "renderMapModal must clone the live mini-map SVG — that's "
            "how the modal reflects current state without duplicating "
            "the render pipeline.",
        )

    def test_render_upscales_label_fonts(self):
        """Tactical radar labels are tuned for the 140px mini view.
        Without upscaling, 5px SVG labels remain small even at modal
        size relative to the radar geometry. The patch bumps them ~2x.
        """
        start = self.html.find("function renderMapModal(kind)")
        self.assertNotEqual(start, -1)
        body = self.html[start : start + 4000]
        # The patch uses querySelectorAll('text') and a font-size regex.
        self.assertIn("querySelectorAll('text')", body)
        self.assertRegex(body, r"font-size\s*:\s*\\?s\*\(\?\[\\d\.\]\+\)\s*px|font-size\s*:.*?px")


if __name__ == "__main__":
    unittest.main()
