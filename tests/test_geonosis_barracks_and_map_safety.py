# -*- coding: utf-8 -*-
"""
tests/test_geonosis_barracks_and_map_safety.py

Lane D interior tier — the Gladiator Barracks beneath the Petranaki
Arena (a new ``geonosis_barracks`` zone reached from the arena prep
room), PLUS a map-safety guard that pins the existing exterior layout so
this drop (and any future one) cannot silently move the Geonosis maps.

Geonosis maps render per-zone from each room's (map_x, map_y). The
barracks is purely ADDITIVE — a new zone with its own coordinate grid;
the only edit to a pre-existing room is one new ``barracks:`` doorway on
``geonosis_arena_prep_room`` (its coordinates and every other exit
unchanged). These guards encode exactly that promise:

  * The exterior ``geonosis_surface`` zone — its room set AND every
    room's (map_x, map_y) — is pinned to a golden snapshot.
  * The ``geonosis_petranaki`` zone (the one the barracks connects to)
    is likewise pinned; the prep room keeps its coordinates and its
    three original exits, and only gains the one new doorway.
  * The new ``geonosis_barracks`` zone is well-formed (6 rooms, unique
    ids, no intra-zone coordinate collisions, registered in zones.yaml,
    every exit resolves) and is B3/Q1 clean.

NOTE: the surface snapshot intentionally records a pre-existing
coordinate overlap (geonosis_arena_gate and stalgasin_outsider_compound
both at 50,11). The guard pins exact coordinates rather than asserting
global no-collision, so it neither breaks on nor silently "fixes" that
pre-existing condition — it just freezes the current truth.

Sandbox-runnable: pure YAML parsing, no loader/aiosqlite dependency.
"""
import os
import unittest

import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
GEONOSIS_YAML = os.path.join(CW, "planets", "geonosis.yaml")
ZONES_YAML = os.path.join(CW, "zones.yaml")

# ── Golden snapshot of the EXISTING exterior layout (map-safety pin) ──────────
# If a drop moves any of these rooms, this test fails — that is the point.
EXPECTED_SURFACE = {
    "geonosis_arena_gate": (50, 11),
    "geonosis_cis_recruiter_office": (50, 9),
    "geonosis_droid_staging": (51, 11),
    "geonosis_foundry_approach": (49, 9),
    "geonosis_hive_entrance": (52, 9),
    "geonosis_landing_pad": (50, 10),
    "geonosis_spire_overlook": (52, 10),
    "geonosis_surface_approach": (51, 10),
    "geonosis_surface_market": (51, 9),
    "geonosis_surface_ruins": (49, 10),
    "smugglers_roost_flophouse": (53, 11),
    "stalgasin_offworld_quarter": (51, 11),
    "stalgasin_outsider_compound": (50, 11),  # pre-existing overlap w/ arena_gate
}
EXPECTED_PETRANAKI = {
    "geonosis_arena_floor": (51, 13),
    "geonosis_arena_prep_room": (49, 13),
    "geonosis_arena_stands": (50, 13),
    "geonosis_creature_pens": (51, 12),
    "petranaki_arena_entrance": (50, 12),
}
# The prep room's three ORIGINAL exits (must be preserved, unchanged).
PREP_ROOM_ORIGINAL_EXITS = {
    "floor": "geonosis_arena_floor",
    "entrance": "petranaki_arena_entrance",
    "pens": "geonosis_creature_pens",
}

EXPECTED_BARRACKS = {
    "barracks_muster_yard": (50, 10),
    "barracks_slave_cells": (49, 10),
    "barracks_training_pit": (50, 11),
    "barracks_armory": (51, 10),
    "slavemaster_den": (50, 9),
    "barracks_workparty_staging": (49, 11),
}

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "x-wing", "tie fighter", "tie pilot", "rebel alliance",
)
Q1_FORBIDDEN = (
    "Poggle", "Sun Fac", "Lama Su", "Taun We", "Nala Se",
    "Dooku", "Sidious", "Tyranus", "Grievous",
    "Padmé", "Padme", "Anakin", "Obi-Wan", "Kenobi",
    "Jango", "Boba",
)


def _planet():
    with open(GEONOSIS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _zones():
    with open(ZONES_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _rooms():
    return _planet()["rooms"]


def _by_zone(zone):
    return {r["slug"]: r for r in _rooms() if r.get("zone") == zone}


def _by_slug(slug):
    for r in _rooms():
        if r.get("slug") == slug:
            return r
    return None


def _all_slugs():
    return {r["slug"] for r in _rooms()}


def _coords(room):
    return (room.get("map_x"), room.get("map_y"))


def _text(room):
    return (room.get("description") or "") + " " + (room.get("short_desc") or "")


class TestExteriorMapUnchanged(unittest.TestCase):
    """The barracks must not have perturbed the existing maps."""

    def test_surface_room_set_pinned(self):
        got = set(_by_zone("geonosis_surface"))
        self.assertEqual(
            got, set(EXPECTED_SURFACE),
            "geonosis_surface room set changed — the exterior layout must "
            "stay frozen. Added/removed: "
            f"{got ^ set(EXPECTED_SURFACE)}",
        )

    def test_surface_coords_pinned(self):
        rooms = _by_zone("geonosis_surface")
        for slug, xy in EXPECTED_SURFACE.items():
            self.assertEqual(
                _coords(rooms[slug]), xy,
                f"exterior room {slug!r} moved to {_coords(rooms[slug])} "
                f"(expected {xy}). This would shift the surface map.",
            )

    def test_petranaki_room_set_pinned(self):
        got = set(_by_zone("geonosis_petranaki"))
        self.assertEqual(
            got, set(EXPECTED_PETRANAKI),
            "geonosis_petranaki room set changed; the barracks must be its "
            f"own zone, not added to petranaki. Diff: {got ^ set(EXPECTED_PETRANAKI)}",
        )

    def test_petranaki_coords_pinned(self):
        rooms = _by_zone("geonosis_petranaki")
        for slug, xy in EXPECTED_PETRANAKI.items():
            self.assertEqual(_coords(rooms[slug]), xy,
                             f"petranaki room {slug!r} moved.")

    def test_prep_room_unchanged_except_new_doorway(self):
        """The single existing-room edit: prep room keeps its coords and
        all three original exits; it only GAINS the barracks doorway."""
        prep = _by_slug("geonosis_arena_prep_room")
        self.assertEqual(_coords(prep), (49, 13),
                         "the prep room must not move.")
        exits = prep.get("exits") or {}
        for direction, target in PREP_ROOM_ORIGINAL_EXITS.items():
            self.assertEqual(
                exits.get(direction), target,
                f"prep room exit {direction!r} was rewired or removed "
                f"(expected -> {target}).",
            )
        self.assertEqual(
            exits.get("barracks"), "barracks_muster_yard",
            "prep room should gain a 'barracks' doorway to the muster yard.",
        )


class TestBarracksZone(unittest.TestCase):
    def test_six_rooms_present(self):
        got = _by_zone("geonosis_barracks")
        self.assertEqual(
            set(got), set(EXPECTED_BARRACKS),
            f"geonosis_barracks rooms mismatch: {set(got) ^ set(EXPECTED_BARRACKS)}",
        )

    def test_coords_match_and_no_intra_zone_collision(self):
        rooms = _by_zone("geonosis_barracks")
        for slug, xy in EXPECTED_BARRACKS.items():
            self.assertEqual(_coords(rooms[slug]), xy, f"{slug} coords.")
        coords = [_coords(r) for r in rooms.values()]
        self.assertEqual(
            len(coords), len(set(coords)),
            "two barracks rooms share a map cell — fix the new layout.",
        )

    def test_ids_unique_and_in_range(self):
        ids = [r["id"] for r in _rooms() if r.get("zone") == "geonosis_barracks"]
        self.assertEqual(len(ids), len(set(ids)), "duplicate barracks room id.")
        self.assertTrue(all(438 <= i <= 443 for i in ids),
                        f"barracks ids out of the allotted 438-443 range: {ids}")
        # And globally unique across the planet.
        all_ids = [r["id"] for r in _rooms()]
        self.assertEqual(len(all_ids), len(set(all_ids)),
                         "duplicate room id somewhere in geonosis.yaml.")

    def test_zone_registered_in_zones_yaml(self):
        zdefs = _zones().get("zones", _zones())
        self.assertIn(
            "geonosis_barracks", zdefs,
            "geonosis_barracks must be registered in zones.yaml or the "
            "loader emits a 'nonexistent zone' error.",
        )

    def test_every_room_zone_is_registered(self):
        zdefs = _zones().get("zones", _zones())
        used = {r.get("zone") for r in _rooms() if r.get("zone")}
        missing = [z for z in used if z not in zdefs]
        self.assertEqual(missing, [], f"zones used but not in zones.yaml: {missing}")


class TestBarracksConnection(unittest.TestCase):
    def test_reciprocal_arena_link(self):
        # prep -> barracks (checked above) and barracks -> prep.
        muster = _by_slug("barracks_muster_yard")
        self.assertEqual(
            (muster.get("exits") or {}).get("arena"),
            "geonosis_arena_prep_room",
            "the muster yard should link back to the arena prep room "
            "(reciprocal with the prep room's barracks doorway).",
        )

    def test_all_barracks_exits_resolve(self):
        slugs = _all_slugs()
        bad = []
        for r in _rooms():
            if r.get("zone") != "geonosis_barracks":
                continue
            for direction, target in (r.get("exits") or {}).items():
                if target not in slugs:
                    bad.append((r["slug"], direction, target))
        self.assertEqual(bad, [], f"barracks exits to nonexistent rooms: {bad}")

    def test_interior_is_connected(self):
        # Every barracks room is reachable from the muster yard hub (each
        # has a path; minimally, each non-hub room exits to the yard).
        rooms = _by_zone("geonosis_barracks")
        for slug, r in rooms.items():
            if slug == "barracks_muster_yard":
                continue
            targets = set((r.get("exits") or {}).values())
            self.assertIn(
                "barracks_muster_yard", targets,
                f"{slug} has no path back to the muster yard hub.",
            )


class TestBarracksEraAndCanon(unittest.TestCase):
    def test_descriptions_era_clean(self):
        rooms = _by_zone("geonosis_barracks")
        for slug, r in rooms.items():
            low = _text(r).lower()
            for bad in B3_BANNED:
                self.assertNotIn(bad, low,
                                 f"{slug} carries banned era token {bad!r} (B3).")
        # zone tone too
        tone = (_zones().get("zones", _zones())
                .get("geonosis_barracks", {}).get("narrative_tone", "")).lower()
        for bad in B3_BANNED:
            self.assertNotIn(bad, tone, f"barracks zone tone carries {bad!r} (B3).")

    def test_no_canonical_figures(self):
        rooms = _by_zone("geonosis_barracks")
        for slug, r in rooms.items():
            txt = _text(r)
            for name in Q1_FORBIDDEN:
                self.assertNotIn(name, txt,
                                 f"{slug} names canonical figure {name!r} (Q1).")

    def test_acklay_chopper_named_as_handler(self):
        # The original NPC who runs the barracks should be present (proof
        # the handler is the original, not a canonical figure).
        blob = " ".join(_text(r) for r in _by_zone("geonosis_barracks").values())
        self.assertIn("Acklay Chopper", blob,
                      "the barracks should name its slavemaster Acklay Chopper.")

    def test_ebon_sea_wilderness_hook_present(self):
        staging = _by_slug("barracks_workparty_staging")
        self.assertIn(
            "Ebon Sea", _text(staging),
            "the work-party staging room should set up the Ebon Sea "
            "capture-run hook for the future wilderness tier.",
        )


if __name__ == "__main__":
    unittest.main()
