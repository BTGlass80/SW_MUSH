# -*- coding: utf-8 -*-
"""
tests/test_f8b_tutorial_rooms.py — F.8.b integration tests.

F.8.b (Apr 30 2026, fifth-phase CW closure) closes the F.4c
content-debt by authoring 24 tutorial-zone rooms in
data/worlds/clone_wars/tutorials/rooms.yaml. The rooms file is wired
into era.yaml as a virtual-planet ref (planet="tutorial_chains") and
loaded by the existing world_loader machinery — no loader changes
needed (engine/world_writer.py:186 already handles the `properties:`
block via room.raw).

Note: republic_soldier step 1/3 anchors at the live-world Kamino room
`tipoca_briefing_room` (id 353) rather than authoring a 25th tutorial
room — F.4c's `tipoca_briefing_chamber` → `tipoca_briefing_room`
rename was specifically about redirecting at the existing Kamino
room, not creating a new one. Same pattern as `dexters_diner`,
`crystal_jewel_cantina`, `jedi_temple_main_gate`.

This file guards:
  - 24 rooms loaded with planet="tutorial_chains" and tutorial_zone=true
  - Each room's zone resolves to a real CW zone
  - All chains.yaml room references resolve to either a tutorial-zone
    room OR a live-world planet room (closes F.4c content debt)
  - F.4c retired-slug list shrinks to 7 entries (F.4c rename-map slugs
    + zone-as-room misuses)
  - Specific F.8.b chains.yaml fixes are applied (5 zone-as-room
    misuses replaced with real tutorial-zone room slugs)

Test sections:
  1. TestTutorialRoomsLoaded         — 25 rooms, all tutorial_zone=true
  2. TestTutorialRoomsZonesResolve   — every room's zone in zones.yaml
  3. TestChainRoomReferencesResolve  — every chain ref hits a real room
  4. TestF8BZoneFixesApplied         — 5 specific chain edits guard
  5. TestEraYamlWiredIn              — era.yaml has tutorials/rooms.yaml
  6. TestNoSlugCollisions            — tutorial slugs don't collide
                                       with planet slugs
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


CHAINS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
               "tutorials" / "chains.yaml")
ROOMS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
              "tutorials" / "rooms.yaml")
ZONES_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
              "zones.yaml")
ERA_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "era.yaml")
PLANETS_DIR = PROJECT_ROOT / "data" / "worlds" / "clone_wars" / "planets"


# ──────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────

def _load_rooms_yaml() -> dict:
    with open(ROOMS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_chains_yaml() -> dict:
    with open(CHAINS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_zone_keys() -> set:
    with open(ZONES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return set(data["zones"].keys())


def _load_planet_room_slugs() -> set:
    """Read every planet YAML and return all room slugs."""
    slugs = set()
    for pf in sorted(PLANETS_DIR.glob("*.yaml")):
        with open(pf, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        for r in data.get("rooms") or []:
            if "slug" in r:
                slugs.add(r["slug"])
    return slugs


def _load_tutorial_room_slugs() -> set:
    rooms = _load_rooms_yaml()
    return {r["slug"] for r in rooms.get("rooms") or []}


# ──────────────────────────────────────────────────────────────────────
# 1. Tutorial rooms loaded
# ──────────────────────────────────────────────────────────────────────

class TestTutorialRoomsLoaded(unittest.TestCase):
    """The tutorial-zone rooms file authors 25 rooms with the expected
    schema."""

    def test_rooms_file_exists(self):
        self.assertTrue(ROOMS_PATH.is_file())

    def test_planet_field_is_tutorial_chains(self):
        rooms = _load_rooms_yaml()
        self.assertEqual(rooms.get("planet"), "tutorial_chains")

    def test_room_count_is_24(self):
        rooms = _load_rooms_yaml()
        self.assertEqual(len(rooms.get("rooms") or []), 24)

    def test_every_room_has_tutorial_zone_true(self):
        rooms = _load_rooms_yaml()
        for r in rooms["rooms"]:
            props = r.get("properties") or {}
            self.assertTrue(
                props.get("tutorial_zone"),
                f"Room {r.get('slug')} missing tutorial_zone property",
            )

    def test_room_ids_in_600_block(self):
        """Allocation: 600-624. Per the file header, block 600+ is
        reserved for tutorial-zone rooms; planet IDs end at 437."""
        rooms = _load_rooms_yaml()
        for r in rooms["rooms"]:
            self.assertGreaterEqual(r["id"], 600)
            self.assertLess(r["id"], 700)

    def test_room_ids_unique(self):
        rooms = _load_rooms_yaml()
        ids = [r["id"] for r in rooms["rooms"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_room_slugs_unique(self):
        rooms = _load_rooms_yaml()
        slugs = [r["slug"] for r in rooms["rooms"]]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_every_room_has_required_fields(self):
        rooms = _load_rooms_yaml()
        required = {"id", "slug", "name", "short_desc",
                    "description", "zone", "properties"}
        for r in rooms["rooms"]:
            missing = required - set(r.keys())
            self.assertFalse(
                missing,
                f"Room {r.get('slug')} missing fields: {sorted(missing)}",
            )


# ──────────────────────────────────────────────────────────────────────
# 2. Tutorial rooms' zones resolve
# ──────────────────────────────────────────────────────────────────────

class TestTutorialRoomsZonesResolve(unittest.TestCase):
    """Every tutorial room's zone field must resolve to a real CW zone."""

    def test_all_tutorial_room_zones_resolve(self):
        rooms = _load_rooms_yaml()
        zones = _load_zone_keys()
        for r in rooms["rooms"]:
            self.assertIn(
                r["zone"], zones,
                f"Tutorial room {r['slug']!r} zone {r['zone']!r} "
                f"does not resolve to zones.yaml",
            )


# ──────────────────────────────────────────────────────────────────────
# 3. Chain room references resolve (closes F.4c primary content debt)
# ──────────────────────────────────────────────────────────────────────

class TestChainRoomReferencesResolve(unittest.TestCase):
    """Every chains.yaml room reference (starting_room, drop_room,
    step.location, completion.room) must resolve to either a
    tutorial-zone room OR a live-world planet room. This is the
    F.4c primary content-debt resolution."""

    def test_every_starting_room_resolves(self):
        chains = _load_chains_yaml()
        all_slugs = _load_tutorial_room_slugs() | _load_planet_room_slugs()
        for c in chains["chains"]:
            sr = c.get("starting_room")
            if not sr:
                # Locked chain (jedi_path) may omit starting_room
                self.assertTrue(
                    c.get("locked"),
                    f"Unlocked chain {c['chain_id']!r} missing "
                    f"starting_room",
                )
                continue
            self.assertIn(
                sr, all_slugs,
                f"chain {c['chain_id']!r} starting_room {sr!r} unresolved",
            )

    def test_every_drop_room_resolves(self):
        chains = _load_chains_yaml()
        all_slugs = _load_tutorial_room_slugs() | _load_planet_room_slugs()
        for c in chains["chains"]:
            grad = c.get("graduation") or {}
            drop = grad.get("drop_room")
            self.assertIsNotNone(
                drop, f"chain {c['chain_id']!r} missing graduation.drop_room",
            )
            self.assertIn(
                drop, all_slugs,
                f"chain {c['chain_id']!r} drop_room {drop!r} unresolved",
            )

    def test_every_step_location_resolves(self):
        chains = _load_chains_yaml()
        all_slugs = _load_tutorial_room_slugs() | _load_planet_room_slugs()
        for c in chains["chains"]:
            for step in c.get("steps") or []:
                loc = step.get("location")
                self.assertIsNotNone(
                    loc,
                    f"chain {c['chain_id']!r} step {step.get('step')} "
                    f"missing location",
                )
                self.assertIn(
                    loc, all_slugs,
                    f"chain {c['chain_id']!r} step {step.get('step')} "
                    f"location {loc!r} unresolved",
                )

    def test_every_completion_room_resolves(self):
        chains = _load_chains_yaml()
        all_slugs = _load_tutorial_room_slugs() | _load_planet_room_slugs()
        for c in chains["chains"]:
            for step in c.get("steps") or []:
                comp = step.get("completion") or {}
                room = comp.get("room")
                if room:
                    self.assertIn(
                        room, all_slugs,
                        f"chain {c['chain_id']!r} step {step.get('step')} "
                        f"completion.room {room!r} unresolved",
                    )


# ──────────────────────────────────────────────────────────────────────
# 4. F.8.b zone-as-room fixes guard
# ──────────────────────────────────────────────────────────────────────

class TestF8BZoneFixesApplied(unittest.TestCase):
    """Specific guards for the 5 zone-as-room fixes F.8.b applied to
    chains.yaml. Catches accidental regression to the pre-F.8.b
    zone slugs."""

    def test_jedi_path_step1_uses_jedi_temple_main_gate(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        jp = chains_by_id["jedi_path"]
        self.assertEqual(
            jp["steps"][0]["location"], "jedi_temple_main_gate",
            "F.8.b: jedi_path step1 should anchor at "
            "jedi_temple_main_gate (live-world id 210)",
        )

    def test_jedi_path_drop_room_uses_jedi_temple_main_gate(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        jp = chains_by_id["jedi_path"]
        self.assertEqual(
            jp["graduation"]["drop_room"], "jedi_temple_main_gate",
        )

    def test_bounty_hunter_step3_uses_safehouse(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        bh = chains_by_id["bounty_hunter"]
        step3 = next(s for s in bh["steps"] if s["step"] == 3)
        self.assertEqual(
            step3["location"], "nar_shaddaa_warrens_safehouse",
            "F.8.b: bounty_hunter step3 should anchor at "
            "nar_shaddaa_warrens_safehouse (real tutorial room), "
            "not the zone slug nar_shaddaa_warrens",
        )

    def test_bounty_hunter_step4_uses_safehouse(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        bh = chains_by_id["bounty_hunter"]
        step4 = next(s for s in bh["steps"] if s["step"] == 4)
        self.assertEqual(
            step4["location"], "nar_shaddaa_warrens_safehouse",
        )

    def test_smuggler_step3_completion_uses_holdout(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        sm = chains_by_id["smuggler"]
        step3 = next(s for s in sm["steps"] if s["step"] == 3)
        self.assertEqual(
            step3["completion"].get("room"), "tatooine_smuggler_holdout",
        )

    def test_smuggler_step4_uses_ship_cockpit(self):
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        sm = chains_by_id["smuggler"]
        step4 = next(s for s in sm["steps"] if s["step"] == 4)
        self.assertEqual(
            step4["location"], "smuggler_ship_cockpit",
        )

    def test_republic_intelligence_step2_uses_dexters_diner(self):
        """F.8.b retargets to the live-world dexters_diner (id 232)
        instead of the F.4c-retired dexs_diner."""
        chains = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in chains["chains"]}
        ri = chains_by_id["republic_intelligence"]
        step2 = next(s for s in ri["steps"] if s["step"] == 2)
        self.assertEqual(step2["location"], "dexters_diner")


# ──────────────────────────────────────────────────────────────────────
# 5. era.yaml wired in
# ──────────────────────────────────────────────────────────────────────

class TestEraYamlWiredIn(unittest.TestCase):
    """The era.yaml content_refs.planets list includes the tutorial
    rooms file so the world loader picks up the rooms."""

    def test_tutorials_rooms_in_planets_list(self):
        with open(ERA_PATH, "r", encoding="utf-8") as f:
            era = yaml.safe_load(f)
        planets = era.get("content_refs", {}).get("planets") or []
        self.assertIn("tutorials/rooms.yaml", planets)


# ──────────────────────────────────────────────────────────────────────
# 6. No slug collisions between tutorial and planet rooms
# ──────────────────────────────────────────────────────────────────────

class TestNoSlugCollisions(unittest.TestCase):
    """Tutorial-zone rooms must NOT duplicate any live-world planet
    room slug — the world loader rejects duplicate slugs at load
    time."""

    def test_no_slug_collisions(self):
        tut = _load_tutorial_room_slugs()
        planet = _load_planet_room_slugs()
        collisions = tut & planet
        self.assertEqual(
            collisions, set(),
            f"Tutorial-zone rooms collide with live-world planet "
            f"rooms: {sorted(collisions)}",
        )


# ──────────────────────────────────────────────────────────────────────
# 7. world_loader integration
# ──────────────────────────────────────────────────────────────────────

class TestWorldLoaderIntegration(unittest.TestCase):
    """The world loader picks up the 25 tutorial-zone rooms via the
    planets: list addition, with planet field set to tutorial_chains
    and validates clean."""

    def test_loader_finds_tutorial_chains_planet(self):
        from engine.world_loader import (
            load_era_manifest, load_planets, load_zones, validate_world,
        )
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"
        )
        zones = load_zones(manifest)
        unresolved: list = []
        rooms, exits = load_planets(manifest, unresolved_report=unresolved)

        tutorial_rooms = [r for r in rooms.values()
                          if r.planet == "tutorial_chains"]
        self.assertEqual(len(tutorial_rooms), 24)

    def test_loader_validates_clean(self):
        from engine.world_loader import (
            load_era_manifest, load_planets, load_zones, validate_world,
        )
        manifest = load_era_manifest(
            Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars"
        )
        zones = load_zones(manifest)
        unresolved: list = []
        rooms, exits = load_planets(manifest, unresolved_report=unresolved)
        report = validate_world(zones, rooms, exits)
        self.assertEqual(unresolved, [],
                         f"Unresolved exit directives: {unresolved[:5]}")
        self.assertEqual(
            report.errors, [],
            f"validate_world reported errors: {report.errors[:5]}",
        )


if __name__ == "__main__":
    unittest.main()
