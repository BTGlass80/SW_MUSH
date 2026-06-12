# -*- coding: utf-8 -*-
"""
tests/test_lane_d_ey_akh_landmarks.py

Lane D (Geonosis), wilderness-tier follow-up: the two original-content POIs
that close the E'Y-Akh's Geonosis arc —

  * Marmio Mio's Freighter — an original-NPC info-broker SITE (a wrecked
    Action IV transport ringed by six merdeth shells). Marmio Mio is named
    ATMOSPHERICALLY in the room description (like Acklay Chopper in the
    barracks), NOT instantiated as an interactive NPC entity; a full
    interactive Marmio Mio is a separate NPC-system drop.

  * The N'G'Zi Badlands — the eastern terminus where the dune sea breaks
    against rock, authored as a NAMED LANDMARK on the existing `badlands`
    terrain (the lighter path) rather than a distinct sub-region.

Contracts covered:

  1. Both landmarks load via the wilderness loader, with the right terrain,
     in-grid coordinates that collide with nothing, and adjacency that
     resolves to defined landmark ids (no dangling adjacency).

  2. No phantom field: neither new landmark carries `ambient_lines`. That
     field is written into room props by the wilderness writer but has NO
     runtime reader at HEAD (flagged in TODO tech_debt), so all flavor lives
     in `description` (the look-time path). This test PINS that discipline so
     a future edit can't quietly reintroduce a dead field here.

  3. Content fidelity to Geonosis & Outer Rim §1.4: Marmio Mio's site carries
     the wreck + six merdeth shells + the spy/info-broker framing + the
     flood-survival ("ballast tanks") payoff that ties it to EventType.FLOOD;
     the N'G'Zi carries the dune-sea terminus + the wild-acklay hunting ground.

  4. Marmio Mio is atmospheric only — the landmark declares no interactive
     entity field, and `marmio_mio` is not a creature/NPC id in
     npcs_creatures.yaml.

  5. B3 era-cleanness + Q1 canon-cleanness across both new landmarks.

  6. The region as a whole still loads with zero errors/warnings after the
     additions (the loader accepts them; no collision, no broken adjacency).

Sandbox-runnable: the wilderness loader runs without a DB; the rest is YAML.
"""
import os
import unittest

import yaml

from engine.wilderness_loader import load_wilderness_region

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
EY_AKH = os.path.join(CW, "wilderness", "ey_akh.yaml")
CREATURES = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")

NEW_LANDMARKS = ("marmio_mio_freighter", "ng_zi_badlands")

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "x-wing", "tie fighter", "tie pilot", "rebel alliance",
    "rebellion", "moff", "sith",
)
Q1_FORBIDDEN = (
    "Poggle", "Sun Fac", "Hadiss", "Lama Su", "Taun We", "Nala Se",
    "Ko Sai", "Kina Ha", "Dooku", "Sidious", "Tyranus", "Grievous",
    "Padmé", "Padme", "Anakin", "Obi-Wan", "Kenobi", "Jango", "Boba",
    "Sifo-Dyas", "Quinlan", "Vos", "Secura",
)


def _region():
    return load_wilderness_region(EY_AKH)


def _region_yaml():
    with open(EY_AKH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _landmark(reg, lid):
    return next((l for l in reg.landmarks if l.id == lid), None)


def _creature_ids():
    with open(CREATURES, encoding="utf-8") as f:
        return {n["id"] for n in yaml.safe_load(f)["npcs"]}


class TestRegionStillLoads(unittest.TestCase):
    def test_region_loads_clean_after_additions(self):
        rep = _region()
        self.assertTrue(rep.ok, f"ey_akh failed to load: {rep.errors[:3]}")
        # The additions must not introduce loader errors OR warnings
        # (a warning would mean an unresolved adjacency / undefined terrain).
        self.assertEqual(rep.errors, [], f"loader errors: {rep.errors}")
        self.assertEqual(rep.warnings, [], f"loader warnings: {rep.warnings}")

    def test_all_landmark_coordinates_unique(self):
        reg = _region().region
        coords = [l.coordinates for l in reg.landmarks]
        self.assertEqual(
            len(coords), len(set(coords)),
            f"duplicate landmark coordinates: {coords}",
        )


class TestNewLandmarksPresent(unittest.TestCase):
    def test_both_new_landmarks_present(self):
        reg = _region().region
        ids = {l.id for l in reg.landmarks}
        for lid in NEW_LANDMARKS:
            self.assertIn(lid, ids, f"landmark {lid!r} missing from the region.")

    def test_marmio_on_dune_terrain(self):
        lm = _landmark(_region().region, "marmio_mio_freighter")
        self.assertIsNotNone(lm)
        self.assertEqual(
            lm.terrain, "dune",
            "the freighter is half-buried in the open dune sea, not the rock.",
        )

    def test_ngzi_on_badlands_terrain(self):
        lm = _landmark(_region().region, "ng_zi_badlands")
        self.assertIsNotNone(lm)
        self.assertEqual(
            lm.terrain, "badlands",
            "the N'G'Zi is anchored to the existing `badlands` terrain "
            "(the lighter path — terminus POI, not its own region).",
        )

    def test_coordinates_in_grid_bounds(self):
        reg = _region().region
        w, h = reg.grid_width, reg.grid_height
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            x, y = lm.coordinates
            self.assertTrue(
                0 <= x < w and 0 <= y < h,
                f"{lid} coords {lm.coordinates} out of {w}x{h} grid.",
            )

    def test_adjacency_resolves_to_defined_landmarks(self):
        reg = _region().region
        ids = {l.id for l in reg.landmarks}
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            self.assertTrue(lm.adjacency, f"{lid} should declare an adjacency.")
            for adj in lm.adjacency:
                self.assertIn(
                    adj, ids,
                    f"{lid} adjacency {adj!r} is not a defined landmark "
                    f"(would be a dangling exit / loader warning).",
                )


class TestNoPhantomAmbientField(unittest.TestCase):
    """`ambient_lines` on a landmark is a DEAD field at HEAD (written by the
    writer into wilderness_ambient_lines, but nothing reads that prop). Pin
    that the new landmarks carry no ambient_lines — flavor goes in description.
    """

    def test_new_landmarks_have_no_ambient_lines(self):
        reg = _region().region
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            self.assertEqual(
                lm.ambient_lines, [],
                f"{lid} must not carry ambient_lines (no runtime reader at "
                f"HEAD — it would be a phantom field). Put flavor in "
                f"`description`.",
            )

    def test_new_landmarks_have_substantive_descriptions(self):
        # The flavor that would (wrongly) go in ambient_lines lives here.
        reg = _region().region
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            self.assertGreater(
                len(lm.description), 300,
                f"{lid} needs a substantive look-time description.",
            )
            self.assertTrue(
                lm.short_desc.strip(), f"{lid} needs a short_desc."
            )


class TestMarmioContentFidelity(unittest.TestCase):
    def setUp(self):
        self.lm = _landmark(_region().region, "marmio_mio_freighter")
        self.blob = (self.lm.short_desc + " " + self.lm.description).lower()

    def test_wreck_and_six_merdeth_shells(self):
        self.assertIn("action iv", self.blob,
                      "the site is a wrecked Action IV transport (§1.4).")
        self.assertIn("six", self.blob)
        self.assertIn("merdeth shell", self.blob,
                      "ringed by six colossal merdeth shells (§1.4).")

    def test_marmio_named_atmospherically(self):
        self.assertIn("marmio mio", self.blob,
                      "Marmio Mio is named in the description (original NPC, "
                      "Q1-OK) — atmospheric reference, like Acklay Chopper.")

    def test_spy_info_broker_framing(self):
        # The "stranded trader is actually a multi-hive spy / info-broker
        # with divided loyalties" twist (§1.4 NPC entry).
        self.assertTrue(
            any(t in self.blob for t in ("speeder bike", "probe droid")),
            "the hidden speeder bike / probe droids hint at the spy role.",
        )
        self.assertTrue(
            any(t in self.blob for t in ("sells", "secret", "loyalt")),
            "the divided-loyalty info-broker framing should be present.",
        )

    def test_flood_ballast_payoff(self):
        # Ties the site to EventType.FLOOD: "On ballast tanks during the
        # flood" — why she survives out here when nothing else does.
        self.assertIn("ballast", self.blob,
                      "the freighter rides the flood out on its ballast tanks "
                      "(§1.4) — the payoff that links this POI to the flood.")
        self.assertIn("flood", self.blob)

    def test_marmio_is_not_an_interactive_npc_entity(self):
        # Atmospheric only: the landmark declares no interactive-entity field,
        # and marmio_mio is not a creature/NPC id in npcs_creatures.yaml.
        for k in ("npc", "npc_template", "entity", "vendor", "quest_giver"):
            self.assertNotIn(
                k, self.lm.properties,
                f"marmio_mio_freighter must not declare an interactive "
                f"`{k}` here (that's a separate NPC-system drop).",
            )
        self.assertNotIn(
            "marmio_mio", _creature_ids(),
            "Marmio Mio must not be a creature/NPC id yet — she's atmospheric.",
        )


class TestNgziContentFidelity(unittest.TestCase):
    def setUp(self):
        self.lm = _landmark(_region().region, "ng_zi_badlands")
        self.blob = (self.lm.short_desc + " " + self.lm.description).lower()

    def test_dune_sea_terminus(self):
        # "the E'Y-Akh ... ending at the N'G'Zi badlands" — the boundary.
        self.assertTrue(
            any(t in self.blob for t in ("dune sea", "the sand", "the dunes")),
            "the N'G'Zi is framed as where the dune sea ends.",
        )
        self.assertTrue(
            any(t in self.blob for t in ("rock", "badland", "butte", "ravine")),
            "shattered-rock badlands terrain language should be present.",
        )

    def test_wild_acklay_hunting_ground(self):
        # The wild_acklay_hunt encounter (terrains [badlands, ebon_sea_shore])
        # dens here — the POI should pay that off.
        self.assertIn("acklay", self.blob,
                      "the N'G'Zi is the wild acklays' hunting ground.")


class TestEraAndCanonClean(unittest.TestCase):
    def test_new_landmarks_b3_clean(self):
        reg = _region().region
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            blob = (lm.name + " " + lm.short_desc + " " + lm.description).lower()
            for bad in B3_BANNED:
                self.assertNotIn(
                    bad, blob,
                    f"{lid} carries era token {bad!r} (B3).",
                )

    def test_new_landmarks_q1_clean(self):
        reg = _region().region
        for lid in NEW_LANDMARKS:
            lm = _landmark(reg, lid)
            blob = lm.name + " " + lm.short_desc + " " + lm.description
            for name in Q1_FORBIDDEN:
                self.assertNotIn(
                    name, blob,
                    f"{lid} names canon figure {name!r} (Q1).",
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
