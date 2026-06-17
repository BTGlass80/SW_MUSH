"""tests/test_web_landing_accuracy.py — PRELAUNCH.web_landing_retention accuracy guards.

Verifies:
1. The portal.html landing copy names only worlds that exist in the world data.
2. The handle_stats planet constant matches the actual planet YAML count.
3. Kessel / Corellia (non-existent worlds) are absent from the landing copy.
"""

import os
import re

PORTAL_HTML = os.path.join(os.path.dirname(__file__), "..", "static", "portal.html")
WEB_PORTAL_PY = os.path.join(os.path.dirname(__file__), "..", "server", "web_portal.py")
PLANETS_DIR = os.path.join(
    os.path.dirname(__file__), "..", "data", "worlds", "clone_wars", "planets"
)

# Worlds that exist as planet YAMLs in the Clone Wars era.
ACTUAL_PLANETS = {
    "tatooine",
    "coruscant",
    "nar shaddaa",
    "geonosis",
    "kamino",
    "kuat",
}
# Worlds that were once in the landing copy but don't exist in world data.
PHANTOM_WORLDS = {"kessel", "corellia"}


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestLandingCopyAccuracy:
    def test_no_phantom_worlds_in_landing_desc(self):
        html = _read(PORTAL_HTML)
        # Extract landing-desc text (rough search — good enough for a static file).
        for world in PHANTOM_WORLDS:
            assert world not in html.lower(), (
                f"portal.html landing copy still references non-existent world '{world}'"
            )

    def test_actual_planets_present_in_landing_desc(self):
        html = _read(PORTAL_HTML)
        for world in ACTUAL_PLANETS:
            assert world in html.lower(), (
                f"portal.html landing desc does not mention actual planet '{world}'"
            )

    def test_planet_yaml_count_matches_stat_constant(self):
        """Planet YAML count must equal the 'planets' constant in handle_stats."""
        yaml_count = len([
            f for f in os.listdir(PLANETS_DIR) if f.endswith(".yaml")
        ])
        # Extract the hardcoded constant from the source.
        src = _read(WEB_PORTAL_PY)
        m = re.search(r'"planets":\s*(\d+)', src)
        assert m, "Could not find 'planets' constant in web_portal.py handle_stats"
        stat_count = int(m.group(1))
        assert stat_count == yaml_count, (
            f"web_portal.py 'planets' stat is {stat_count} "
            f"but {yaml_count} planet YAMLs exist in {PLANETS_DIR}"
        )

    def test_planets_dir_has_expected_count(self):
        yaml_files = [f for f in os.listdir(PLANETS_DIR) if f.endswith(".yaml")]
        assert len(yaml_files) == 6, (
            f"Expected 6 planet YAMLs, found {len(yaml_files)}: {yaml_files}"
        )
