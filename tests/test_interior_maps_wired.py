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
INTERIORS = {
    "coruscant.jedi_temple":        ("jedi_temple_substrate.png", 11),
    "coruscant.coruscant_works":    ("coruscant_works_substrate.png", 4),
    "geonosis.gladiator_barracks":  ("gladiator_barracks_substrate.png", 6),
}


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


def test_interiors_bind_without_slug_collision():
    reg = AreaGeometryRegistry.load_era("clone_wars")
    for area_key in INTERIORS:
        g = load_area_geometry(area_key)
        for r in g.rooms:
            e = reg.lookup(r.slug)
            assert e is not None, f"{area_key}: slug {r.slug!r} not bound in registry"
            assert e.area_key == area_key, (
                f"{area_key}: slug {r.slug!r} COLLIDES — bound to {e.area_key} "
                f"instead (would make navigation nondeterministic)"
            )
