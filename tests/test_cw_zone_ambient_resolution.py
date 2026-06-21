# tests/test_cw_zone_ambient_resolution.py
#
# CW zone slug → ambient pool key resolution guard.
# Regression for the bug where CW zone slugs fell through to "default"
# because _ZONE_NAME_TO_KEY only contained GCW descriptive zone names.
# Every CW zone slug must resolve to a real pool key (not "default")
# so static ambient events actually fire in CW zones.
#
# Covers engine/ambient_events.py::_resolve_zone_key + _ZONE_NAME_TO_KEY.

import pytest

from engine.ambient_events import _resolve_zone_key


# ── Explicit-mapping cases (slug ≠ pool key) ────────────────────────────────

@pytest.mark.parametrize("zone_slug,expected_pool_key", [
    # Kamino
    ("kamino_tipoca_city",      "kamino_tipoca"),
    ("kamino_cloning_halls",    "kamino_training"),
    ("kamino_ocean_platform",   "kamino_ocean"),
    # Geonosis
    ("geonosis_petranaki",      "geonosis_arena"),
    ("geonosis_surface",        "geonosis_wastes"),
    ("geonosis_deep_hive",      "geonosis_tunnels"),
    ("geonosis_barracks",       "geonosis_arena"),
    ("geonosis_ey_akh",         "geonosis_wastes"),
    # Kuat
    ("kdy_orbital_ring",        "kuat_orbital"),
    ("kuat_city_embassy",       "kuat_surface"),
    ("kuat_main_spaceport",     "kuat_transit"),
    # Coruscant extras
    ("coruscant_underworld",    "southern_underground"),
    ("entertainment_district",  "commercial_district"),
])
def test_cw_explicit_slug_mappings(zone_slug, expected_pool_key):
    assert _resolve_zone_key(zone_slug) == expected_pool_key


# ── Direct-fallback cases (slug == pool key, no explicit entry needed) ───────

@pytest.mark.parametrize("zone_slug", [
    "senate_district",
    "jedi_temple",
    "monumental_district",
    "commercial_district",
    "southern_underground",
    "geonosis_foundries",
    "space_coruscant",
    "space_kuat",
    "space_kamino",
    "space_geonosis",
])
def test_cw_direct_slug_passthrough(zone_slug):
    # These slugs ARE the pool key — resolver should return them verbatim.
    assert _resolve_zone_key(zone_slug) == zone_slug


# ── GCW legacy zone names still work ────────────────────────────────────────

@pytest.mark.parametrize("gcw_name,expected_key", [
    ("Cantina District",  "cantina"),
    ("cantina",           "cantina"),
    ("Spaceport District", "spaceport"),
    ("spaceport",         "spaceport"),
    ("Central Streets",   "streets"),
    ("Commercial District", "shops"),
    ("Jabba's Territory", "jabba"),
    ("Government District", "government"),
])
def test_gcw_legacy_zone_names(gcw_name, expected_key):
    assert _resolve_zone_key(gcw_name) == expected_key


# ── Tatooine CW zone slugs resolved by substring fallback ───────────────────

@pytest.mark.parametrize("zone_slug,expected_key", [
    ("tatooine_cantina",    "cantina"),
    ("tatooine_spaceport",  "spaceport"),
    ("tatooine_market",     "streets"),  # "market" substring → streets
])
def test_tatooine_cw_slugs_via_substring(zone_slug, expected_key):
    assert _resolve_zone_key(zone_slug) == expected_key


# ── Edge cases ───────────────────────────────────────────────────────────────

def test_none_zone_returns_default():
    assert _resolve_zone_key(None) == "default"


def test_empty_zone_returns_default():
    assert _resolve_zone_key("") == "default"
