# -*- coding: utf-8 -*-
"""
tests/test_wilderness_zone_resolves_2026_07_03.py — wilderness-zone-integrity
guard.

Root cause (drop `wilderness-zone-integrity`, 2026-07-03): every wilderness
region's ``region.zone`` value is looked up against ``zones`` by exact DB
``name`` (``engine/wilderness_writer.py::_lookup_zone_id_by_name``). The DB
``name`` column is set by ``engine/world_writer.py::_write_zones`` L140 as
``zone.raw.get("name", slug)`` — and no zone in
``data/worlds/clone_wars/zones.yaml`` declares an explicit ``name:`` field
(they use ``name_match:`` for the security-tone lookup instead), so every
zone's effective DB name is just its YAML slug key.

``data/worlds/clone_wars/wilderness/dune_sea.yaml`` used to set
``region.zone: jundland_wastes`` — a slug that does not exist anywhere in
zones.yaml (real Tatooine slugs are ``tatooine_jundland`` and
``tatooine_dune_sea``). The lookup silently returned NULL, so every Dune Sea
landmark room (including the Hollow Sun staged-cult site) landed with a NULL
``zone_id`` and inherited default security instead of the intended lawless
Tatooine-outback posture. Fixed by pointing ``region.zone`` at
``tatooine_dune_sea`` (the region's own zone, matching the pattern every
other wilderness region already follows).

This module is the static guard so the class of bug (a wilderness region's
``region.zone`` naming a zone slug that doesn't actually exist) cannot
silently recur: it mirrors the writer's effective-name resolution EXACTLY
(no LIKE-fallback laxity) against every wilderness region file that declares
a `region.zone`.
"""
from __future__ import annotations

import os

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
ZONES_YAML = os.path.join(CW, "zones.yaml")
WILDERNESS_DIR = os.path.join(CW, "wilderness")
DUNE_SEA_YAML = os.path.join(WILDERNESS_DIR, "dune_sea.yaml")


def _load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _effective_zone_names() -> set:
    """Mirror engine/world_writer.py::_write_zones L140 EXACTLY:
    a zone's DB `name` is `zone.raw.get("name", slug)` for every top-level
    key under `zones:` in zones.yaml. No zone in the live file declares an
    explicit `name:`, but this must stay a live mirror (not a hardcoded
    assumption) so it keeps catching regressions if that ever changes.
    """
    data = _load_yaml(ZONES_YAML)
    zones = data["zones"]
    names = set()
    for slug, block in zones.items():
        block = block or {}
        names.add(block.get("name", slug))
    return names


def _wilderness_region_zone_files():
    """Yield (filename, region_zone) for every wilderness YAML that
    declares a `region.zone` value. Files without a `region:` block (e.g.
    landmark-include fragments, edge-connection single-room files) are
    skipped — they don't independently resolve a zone."""
    out = []
    for fname in sorted(os.listdir(WILDERNESS_DIR)):
        if not fname.endswith(".yaml"):
            continue
        path = os.path.join(WILDERNESS_DIR, fname)
        data = _load_yaml(path)
        if not isinstance(data, dict):
            continue
        region = data.get("region")
        if not isinstance(region, dict):
            continue
        zone = region.get("zone")
        if zone is None:
            continue
        out.append((fname, zone))
    return out


class TestEveryWildernessRegionZoneResolves:
    """Every wilderness region's `region.zone` must name a zone that
    actually exists in zones.yaml — an EXACT match against the writer's
    effective DB name set, not the writer's fragile LIKE fallback."""

    def test_at_least_one_region_zone_file_found(self):
        # Guards against the loop silently finding nothing (e.g. a path
        # typo) and the test suite passing vacuously.
        pairs = _wilderness_region_zone_files()
        assert len(pairs) >= 5, (
            f"Expected several wilderness region files with a region.zone "
            f"value; found only {pairs!r}"
        )

    def test_every_region_zone_resolves_to_a_real_zone(self):
        effective_names = _effective_zone_names()
        pairs = _wilderness_region_zone_files()
        unresolved = [
            (fname, zone) for fname, zone in pairs
            if zone not in effective_names
        ]
        assert unresolved == [], (
            f"These wilderness region files name a region.zone that does "
            f"not resolve to any real zone in zones.yaml (would land "
            f"landmarks with NULL zone_id at build time): {unresolved!r}"
        )


class TestDuneSeaSpecifically:
    """Focused regression coverage for the bug that was actually found:
    dune_sea.yaml's region.zone must be the fixed, resolvable value."""

    def test_dune_sea_region_zone_is_tatooine_dune_sea(self):
        data = _load_yaml(DUNE_SEA_YAML)
        assert data["region"]["zone"] == "tatooine_dune_sea"

    def test_dune_sea_region_zone_resolves(self):
        data = _load_yaml(DUNE_SEA_YAML)
        zone = data["region"]["zone"]
        assert zone in _effective_zone_names()

    def test_dune_sea_region_zone_is_not_the_old_nonexistent_slug(self):
        # jundland_wastes never existed as a zone slug; pin against
        # regressing back to it (or any other typo'd slug that happens
        # to LIKE-match "jundland").
        data = _load_yaml(DUNE_SEA_YAML)
        assert data["region"]["zone"] != "jundland_wastes"


# ─────────────────────────────────────────────────────────────────────────────
# Runtime layer: writing the real Dune Sea region against a real (in-memory)
# schema, seeded with the real tatooine zones, actually assigns a non-NULL
# zone_id matching tatooine_dune_sea. Mirrors tests/test_dune_sea_minimal.py's
# _fresh_db + write_wilderness_region pattern.
# ─────────────────────────────────────────────────────────────────────────────

import asyncio  # noqa: E402


def _run(coro):
    return asyncio.run(coro)


async def _fresh_db():
    from db.database import Database
    db = Database(":memory:")
    await db.connect()
    await db.initialize()
    return db


class TestDuneSeaLandmarksGetRealZoneId:

    def test_landmark_room_zone_id_matches_tatooine_dune_sea(self):
        async def _check():
            from engine.wilderness_loader import load_wilderness_region
            from engine.wilderness_writer import write_wilderness_region

            db = await _fresh_db()
            # Seed the zone the same way a real world build would: the DB
            # `name` column is the zone's effective name (its slug, since
            # zones.yaml declares no explicit `name:`).
            zone_id = await db.create_zone("tatooine_dune_sea")

            fr_path = os.path.join(WILDERNESS_DIR, "force_resonant_landmarks.yaml")
            rep = load_wilderness_region(DUNE_SEA_YAML, force_resonant_path=fr_path)
            assert rep.ok, f"region failed to load: {rep.errors}"

            wr = await write_wilderness_region(rep.region, db)
            assert wr.errors == [], wr.errors
            # If the zone lookup fell back to NULL, the writer logs a
            # warning — assert there is none, then confirm every landmark
            # room actually carries the resolved zone_id.
            assert not any("NULL zone_id" in w for w in wr.warnings), wr.warnings

            assert wr.landmark_room_ids, "no landmarks written"
            for slug, room_id in wr.landmark_room_ids.items():
                rows = await db._db.execute_fetchall(
                    "SELECT zone_id FROM rooms WHERE id=?", (room_id,),
                )
                assert rows[0]["zone_id"] == zone_id, (
                    f"landmark {slug!r} has zone_id={rows[0]['zone_id']!r}, "
                    f"expected {zone_id!r} (tatooine_dune_sea)"
                )
            await db._db.close()
        _run(_check())
