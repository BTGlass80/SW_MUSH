# -*- coding: utf-8 -*-
"""tests/test_interior_maps_wired.py — guard the 3 wired building-interior maps
(drop interiors-wired-2026-06-20).

The Jedi Temple, Coruscant Works, and Gladiator Barracks are wired as live
tier-1a AreaGeometries (data/worlds/clone_wars/maps/*.yaml + a substrate PNG),
auto-discovered by AreaGeometryRegistry. These were chosen because their room
slugs appear in NO other map, so binding is collision-free. This test pins:
  1. each loads + validates + carries its substrate_image,
  2. the substrate PNG exists,
  3. the registry binds every room slug to ITS OWN area (no slug collision with
     the city maps — the exact failure mode that would make navigation
     nondeterministic).
"""
from __future__ import annotations

import os
import pytest

from engine.area_loader import load_area_geometry, AreaGeometryRegistry

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# area_key -> (substrate basename, expected room count)
# The first 3 (2026-06-20) were collision-free; the next 6 (2026-06-21) share
# room slugs with their parent city-overview map (stalgasin_hive / tipoca_city /
# mos_eisley) and bind via the is_interior interior-wins precedence.
INTERIORS = {
    "coruscant.jedi_temple":        ("jedi_temple_substrate.png", 11),
    "coruscant.coruscant_works":    ("coruscant_works_substrate.png", 4),
    "geonosis.gladiator_barracks":  ("gladiator_barracks_substrate.png", 6),
    "tatooine.chalmuns_cantina":    ("chalmuns_cantina_substrate.png", 3),
    "kamino.cloning_halls":         ("cloning_halls_substrate.png", 10),
    "geonosis.deep_hive":           ("deep_hive_substrate.png", 10),
    "geonosis.droid_foundry":       ("droid_foundry_substrate.png", 10),
    "geonosis.petranaki_arena":     ("petranaki_arena_substrate.png", 5),
    "kamino.tipoca_admin":          ("tipoca_admin_substrate.png", 9),
}

# The 6 interiors whose room slugs ALSO live in a parent city-overview map —
# the interior-wins precedence must bind these to the INTERIOR. (slug, interior).
_COLLIDING_INTERIOR_SLUGS = [
    ("geonosis_arena_floor",   "geonosis.petranaki_arena"),
    ("geonosis_creature_pens", "geonosis.petranaki_arena"),
    ("tipoca_growth_chambers", "kamino.cloning_halls"),
    ("tipoca_administration",  "kamino.tipoca_admin"),
    ("chalmuans_cantina_main_bar", "tatooine.chalmuns_cantina"),
    ("geonosis_foundry_main",  "geonosis.droid_foundry"),
]


@pytest.mark.parametrize("area_key,expected", list(INTERIORS.items()))
def test_interior_map_loads_with_substrate(area_key, expected):
    sub_png, n_rooms = expected
    g = load_area_geometry(area_key)               # raises on any validation error
    assert g.substrate_image and g.substrate_image.endswith(sub_png), (
        f"{area_key}: substrate_image not set to {sub_png}"
    )
    assert len(g.rooms) == n_rooms, f"{area_key}: expected {n_rooms} rooms"
    assert all(r.slug for r in g.rooms), (
        f"{area_key}: every interior room must carry a slug (registry binds by slug)"
    )
    p = os.path.join(REPO_ROOT, "static", "maps", sub_png)
    assert os.path.exists(p), f"substrate PNG missing: {p}"


def test_interiors_bind_to_their_own_area():
    reg = AreaGeometryRegistry.load_era("clone_wars")
    for area_key in INTERIORS:
        g = load_area_geometry(area_key)
        for r in g.rooms:
            e = reg.lookup(r.slug)
            assert e is not None, f"{area_key}: slug {r.slug!r} not bound in registry"
            assert e.area_key == area_key, (
                f"{area_key}: slug {r.slug!r} bound to {e.area_key} instead "
                f"(navigation would be nondeterministic / show the wrong map)"
            )


def test_interior_wins_real_slug_collisions_over_city_overview():
    """The 6 newer interiors genuinely share room slugs with their parent
    city-overview map (which is additive-only, so the slug can't be removed
    there). The is_interior precedence in AreaGeometryRegistry._add must bind
    those shared slugs to the INTERIOR, not the city overview."""
    reg = AreaGeometryRegistry.load_era("clone_wars")
    for slug, interior_key in _COLLIDING_INTERIOR_SLUGS:
        e = reg.lookup(slug)
        assert e is not None, f"slug {slug!r} not bound in registry"
        assert e.area_key == interior_key, (
            f"shared slug {slug!r} must bind to the interior {interior_key!r} "
            f"(interior-wins), not {e.area_key!r}"
        )


def test_add_precedence_interior_wins_regardless_of_order():
    """Unit-level: an interior beats a city for a shared slug whichever loads
    first (deterministic, not alphabetical 'second wins')."""
    from engine.area_loader import AreaGeometry, MapRoom, MapBounds

    def _geom(area_key, *, interior):
        return AreaGeometry(
            schema_version=1, area_key=area_key, display_name=area_key,
            planet="x", era="clone_wars", default_terrain="sand", palette="p",
            bounds=MapBounds(0, 0, 1, 1), districts=[], rooms=[
                MapRoom(id=1, name="Shared", zone="z", x=0.5, y=0.5,
                        w=0.1, h=0.1, style="civic", symbol="§",
                        slug="shared_room")
            ], exits=[], exit_paths={}, labels=[], landmarks=[],
            is_interior=interior,
        )

    # city first, then interior → interior wins
    reg = AreaGeometryRegistry()
    reg._add(_geom("city.area", interior=False))
    reg._add(_geom("bldg.interior", interior=True))
    assert reg.lookup("shared_room").area_key == "bldg.interior"

    # interior first, then city → interior STILL wins (city can't steal it)
    reg2 = AreaGeometryRegistry()
    reg2._add(_geom("bldg.interior", interior=True))
    reg2._add(_geom("city.area", interior=False))
    assert reg2.lookup("shared_room").area_key == "bldg.interior"
