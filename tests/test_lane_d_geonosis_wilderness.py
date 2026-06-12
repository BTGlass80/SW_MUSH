# -*- coding: utf-8 -*-
"""
tests/test_lane_d_geonosis_wilderness.py

Lane D wilderness tier — the E'Y-Akh (Geonosis's dune-sea wilderness region)
plus the 4 D6-re-statted Geonosis creatures its encounter pool spawns.

Covers four contracts:

  1. Creatures: the 4 net-new Geonosis fauna parse with the creature schema,
     the merdeth carries the Lane A grapple/restraint (a live consumer), the
     acklay/mutant_acklay/mip_swarm faithfully carry NO invented grab, and the
     provenance is marked as a WotC-lore D6 re-stat (not a WEG transcription).

  2. Region: ey_akh.yaml loads via the wilderness loader, has the expected grid
     and landmarks (Ebon Sea, Golbah's Pit), uses only known ambient hazards
     (no invented toxin field with no engine consumer), and is registered in
     era.yaml content_refs.wilderness.

  3. Encounter contract (no phantom / no orphan): every encounter
     payload.npc_template resolves to a creature id in npcs_creatures.yaml, and
     every Geonosis creature has at least one live encounter referencing it.

  4. Map-safety: the on-foot edge room lives in the NEW geonosis_ey_akh zone
     (so the pinned geonosis_surface set stays at 13), the surface connection is
     a single added doorway on geonosis_surface_ruins (its coordinates and its
     original `east` exit unchanged), and the new zone is registered.

Sandbox-runnable: the wilderness loader runs without a DB; everything else is
YAML parsing.
"""
import os
import unittest

import yaml

from engine.wilderness_loader import load_wilderness_region

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CW = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars")
EY_AKH = os.path.join(CW, "wilderness", "ey_akh.yaml")
CREATURES = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")
ZONES = os.path.join(CW, "zones.yaml")
ERA = os.path.join(CW, "era.yaml")
GEONOSIS = os.path.join(CW, "planets", "geonosis.yaml")

GEO_IDS = {"acklay", "mutant_acklay", "merdeth", "mip_swarm"}

B3_BANNED = (
    "imperial", "empire", "stormtrooper", "death star",
    "x-wing", "tie fighter", "tie pilot", "rebel alliance",
)
Q1_FORBIDDEN = (
    "Poggle", "Sun Fac", "Hadiss", "Lama Su", "Taun We", "Nala Se",
    "Dooku", "Sidious", "Tyranus", "Grievous",
    "Padmé", "Padme", "Anakin", "Obi-Wan", "Kenobi", "Jango", "Boba",
)


def _creatures():
    with open(CREATURES, encoding="utf-8") as f:
        return {n["id"]: n for n in yaml.safe_load(f)["npcs"]}


def _region_yaml():
    with open(EY_AKH, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _region():
    rep = load_wilderness_region(EY_AKH)
    return rep


def _zones():
    with open(ZONES, encoding="utf-8") as f:
        d = yaml.safe_load(f)
    return d.get("zones", d)


def _geonosis_rooms():
    with open(GEONOSIS, encoding="utf-8") as f:
        return {r["slug"]: r for r in yaml.safe_load(f)["rooms"]}


def _era_text():
    with open(ERA, encoding="utf-8") as f:
        return f.read()


class TestGeonosisCreatures(unittest.TestCase):
    def test_four_creatures_present_and_schema(self):
        lib = _creatures()
        for cid in GEO_IDS:
            self.assertIn(cid, lib, f"creature {cid} missing from npcs_creatures.yaml")
            c = lib[cid]
            for field in ("name", "species", "scale", "description",
                          "char_sheet", "natural_attack", "source"):
                self.assertIn(field, c, f"{cid} missing schema field {field!r}")
            attrs = c["char_sheet"]["attributes"]
            for a in ("dexterity", "perception", "strength",
                      "knowledge", "mechanical", "technical"):
                self.assertIn(a, attrs, f"{cid} missing attribute {a!r}")

    def test_merdeth_carries_lane_a_grapple(self):
        """The merdeth's barbed-tentacle grab routes through the Lane A
        restraint machinery — a live consumer for this drop."""
        merdeth = _creatures()["merdeth"]
        sa = merdeth.get("special_attack", {}).get("restraint", {})
        self.assertEqual(
            sa.get("kind"), "grapple",
            "merdeth must declare special_attack.restraint.kind == grapple "
            "(the source gives it 'barbed tentacles + grab').",
        )
        self.assertTrue(sa.get("hold_damage"), "merdeth grapple needs hold_damage.")

    def test_no_invented_grab_on_acklays_or_mips(self):
        """Faithful to §1.8: only the merdeth has 'grab'. The acklay,
        mutant acklay, and mip swarm must NOT have an invented restraint."""
        lib = _creatures()
        for cid in ("acklay", "mutant_acklay", "mip_swarm"):
            self.assertNotIn(
                "restraint", lib[cid].get("special_attack", {}) or {},
                f"{cid} has a restraint the source does not grant (invented mechanic).",
            )

    def test_provenance_marks_wotc_d6_restat(self):
        """These are WotC-lore D6 re-stats, NOT WEG transcriptions — the
        source string must not falsely claim WEG/COTG provenance."""
        lib = _creatures()
        for cid in GEO_IDS:
            src = lib[cid]["source"].lower()
            self.assertIn("re-stat", src,
                          f"{cid} source should mark it a from-scratch D6 re-stat.")
            self.assertNotIn("cotg", src, f"{cid} must not claim COTG provenance.")
            self.assertNotIn("weg40", src, f"{cid} must not claim a WEG SKU.")

    def test_creature_strings_era_and_canon_clean(self):
        lib = _creatures()
        for cid in GEO_IDS:
            blob = (lib[cid].get("description", "") + " "
                    + " ".join(lib[cid].get("special", []) or []))
            low = blob.lower()
            for bad in B3_BANNED:
                self.assertNotIn(bad, low, f"{cid} desc carries era token {bad!r} (B3).")
            for name in Q1_FORBIDDEN:
                self.assertNotIn(name, blob, f"{cid} desc names canon figure {name!r} (Q1).")


class TestRegion(unittest.TestCase):
    def test_region_loads(self):
        rep = _region()
        self.assertTrue(rep.ok, f"ey_akh failed to load: {rep.errors[:3]}")
        self.assertEqual(rep.region.slug, "geonosis_ey_akh")

    def test_grid(self):
        reg = _region().region
        self.assertEqual((reg.grid_width, reg.grid_height), (30, 30))

    def test_terrains_use_known_hazards_only(self):
        """No invented ambient hazard — the engine only consumes
        extreme_heat (and 'none'). Golbah's Pit poison stays in lore."""
        terrains = _region_yaml()["terrains"]
        for tname, t in terrains.items():
            haz = t.get("ambient_hazard", "none")
            self.assertIn(
                haz, ("extreme_heat", "none"),
                f"terrain {tname!r} declares ambient_hazard {haz!r} with no "
                f"engine consumer — only extreme_heat/none are wired.",
            )

    def test_landmarks_present(self):
        ids = {lm["id"] for lm in _region_yaml()["landmarks"]}
        for lm in ("ebon_sea", "golbah_pit"):
            self.assertIn(lm, ids, f"landmark {lm!r} missing from the region.")

    def test_region_registered_in_era(self):
        self.assertIn(
            "wilderness/ey_akh.yaml", _era_text(),
            "ey_akh.yaml must be registered in era.yaml content_refs.wilderness.",
        )


class TestEncounterContract(unittest.TestCase):
    def _entries(self):
        return _region().region.encounter_pool.entries

    def test_encounters_present(self):
        ids = {e.id for e in self._entries()}
        for eid in ("merdeth_advance", "mip_scouts", "wild_acklay_hunt",
                    "ebon_sea_ambush"):
            self.assertIn(eid, ids, f"encounter {eid} missing from the E'Y-Akh pool.")

    def test_every_template_resolves(self):
        """No phantom: every payload.npc_template is a real creature id."""
        lib = set(_creatures())
        bad = []
        for e in self._entries():
            tmpl = (e.payload or {}).get("npc_template")
            if tmpl and tmpl not in lib:
                bad.append((e.id, tmpl))
        self.assertEqual(bad, [], f"encounters referencing nonexistent creatures: {bad}")

    def test_no_orphan_geonosis_creatures(self):
        """No phantom: every Geonosis creature has a live E'Y-Akh encounter."""
        referenced = {(e.payload or {}).get("npc_template") for e in self._entries()}
        orphans = GEO_IDS - referenced
        self.assertEqual(
            orphans, set(),
            f"Geonosis creatures with no encounter (phantom risk): {orphans}",
        )

    def test_encounters_have_narrative(self):
        for e in self._entries():
            self.assertTrue(e.narrative.strip(), f"encounter {e.id} has no narrative.")

    def test_encounter_strings_era_and_canon_clean(self):
        for e in self._entries():
            low = e.narrative.lower()
            for bad in B3_BANNED:
                self.assertNotIn(bad, low, f"encounter {e.id} carries era token {bad!r}.")
            for name in Q1_FORBIDDEN:
                self.assertNotIn(name, e.narrative, f"encounter {e.id} names {name!r} (Q1).")


class TestWildernessMapSafety(unittest.TestCase):
    def test_surface_set_still_thirteen(self):
        rooms = _geonosis_rooms()
        surf = [s for s, r in rooms.items() if r.get("zone") == "geonosis_surface"]
        self.assertEqual(
            len(surf), 13,
            "geonosis_surface must stay at 13 rooms — the edge room belongs in "
            f"the new geonosis_ey_akh zone, not the surface. Got {len(surf)}.",
        )

    def test_surface_ruins_doorway_is_addition_only(self):
        ruins = _geonosis_rooms()["geonosis_surface_ruins"]
        self.assertEqual((ruins["map_x"], ruins["map_y"]), (49, 10),
                         "geonosis_surface_ruins must not move.")
        exits = ruins["exits"]
        self.assertEqual(
            exits.get("east"), "geonosis_landing_pad",
            "the original `east` exit must be unchanged.",
        )
        self.assertEqual(
            exits.get("desert"), "ey_akh_desert_edge",
            "geonosis_surface_ruins should gain a `desert` doorway to the edge room.",
        )

    def test_edge_room_in_ey_akh_zone(self):
        edge = _geonosis_rooms()["ey_akh_desert_edge"]
        self.assertEqual(edge["zone"], "geonosis_ey_akh",
                         "the edge room must be in the geonosis_ey_akh zone.")
        self.assertEqual(
            edge["exits"].get("ruins"), "geonosis_surface_ruins",
            "the edge room should link back to the surface ruins.",
        )

    def test_ey_akh_zone_registered(self):
        self.assertIn(
            "geonosis_ey_akh", _zones(),
            "geonosis_ey_akh must be registered in zones.yaml.",
        )


if __name__ == "__main__":
    unittest.main()
