# -*- coding: utf-8 -*-
"""
tests/test_lane_d_flood_encounters.py

Lane D — wiring the E'Y-Akh flood into the wilderness encounter selector.

The flood world event (test_lane_d_ey_akh_flood.py) now *changes the desert*:
the encounter selector grows an ``event_gate`` seam (parallel to the existing
``faction_gate``) so an encounter can be gated on an active world event. Unlike
the storms' mechanical effects (read via the GLOBAL ``get_effect`` path — the
coarse-zone tech-debt), this gate is ZONE-AWARE: a flood-only encounter is
eligible only while the flood is active in the region's own zone.

Contracts:
  * ``EncounterEntry`` carries ``event_gate`` and the loader parses it.
  * ``evaluate_event_gate`` is zone-aware: empty gate → always eligible; a
    flood gate is satisfied only when a flood is active AND affects the
    region's zone — a flood in a DIFFERENT region does not unlock it.
  * In the live E'Y-Akh region, the flood-gated encounters are filtered OUT
    with no flood active and filtered IN once the flood is active, while the
    normal pool is unaffected (the flood adds danger, it doesn't suppress).
  * The flood encounters resolve to real creatures (no phantom) and are
    B3/Q1 clean.

unittest-based (no pytest); resets the world-event singleton per test.
"""
import os
import unittest

import yaml

import engine.world_events as we
from engine.world_events import get_world_event_manager
from engine.wilderness_encounters import (
    EncounterEntry, evaluate_event_gate, _filter_pool,
)
from engine.wilderness_loader import load_wilderness_region

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EY_AKH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                      "wilderness", "ey_akh.yaml")
CREATURES = os.path.join(PROJECT_ROOT, "data", "npcs_creatures.yaml")

FLOOD_ENCOUNTERS = {"flood_drowning_merdeth", "flood_displaced_acklay"}
B3_BANNED = ("imperial", "empire", "stormtrooper", "rebel", "tie ",
             "x-wing", "death star")
Q1_FORBIDDEN = ("poggle", "dooku", "grievous", "padme", "padmé",
                "anakin", "obi-wan", "jango")


class _Region:
    def __init__(self, zone):
        self.zone = zone


def _load_region():
    rep = load_wilderness_region(EY_AKH)
    assert rep.ok, rep.errors[:3]
    return rep.region


def _reset_events():
    we._manager = None  # force get_world_event_manager() to build a fresh one


class TestEventGateSeam(unittest.TestCase):
    def test_entry_has_event_gate_default_empty(self):
        e = EncounterEntry(id="x", type="hostile")
        self.assertEqual(e.event_gate, "")

    def test_loader_parses_event_gate(self):
        entries = _load_region().encounter_pool.entries
        gated = {e.id for e in entries if e.event_gate == "flood"}
        self.assertEqual(
            gated, FLOOD_ENCOUNTERS,
            f"flood-gated encounters mismatch: {gated ^ FLOOD_ENCOUNTERS}",
        )


class TestEventGateZoneAware(unittest.TestCase):
    def setUp(self):
        _reset_events()

    def tearDown(self):
        _reset_events()

    def test_empty_gate_always_eligible(self):
        self.assertTrue(evaluate_event_gate("", _Region("geonosis_ey_akh")))

    def test_flood_gate_false_when_no_flood(self):
        self.assertFalse(evaluate_event_gate("flood", _Region("geonosis_ey_akh")))

    def test_flood_gate_true_when_flood_in_zone(self):
        get_world_event_manager().activate_event("flood")
        self.assertTrue(evaluate_event_gate("flood", _Region("geonosis_ey_akh")))

    def test_flood_gate_false_in_other_region(self):
        """A flood in the E'Y-Akh must NOT unlock flood encounters in a
        different region (zone-aware, not the global leak)."""
        get_world_event_manager().activate_event("flood")
        self.assertFalse(evaluate_event_gate("flood", _Region("tatooine_dune_sea")))


class TestFloodEncounterFiltering(unittest.TestCase):
    def setUp(self):
        _reset_events()
        self.region = _load_region()
        self.entries = self.region.encounter_pool.entries

    def tearDown(self):
        _reset_events()

    def _eligible_ids(self, terrain="dune"):
        elig = _filter_pool(self.entries, terrain=terrain, distance_from_edge=5,
                            char=None, region=self.region)
        return {e.id for e in elig}

    def test_flood_encounters_excluded_without_flood(self):
        ids = self._eligible_ids("dune")
        self.assertNotIn("flood_drowning_merdeth", ids,
                         "flood encounter leaked into normal play.")

    def test_flood_encounters_included_during_flood(self):
        get_world_event_manager().activate_event("flood")
        ids = self._eligible_ids("dune")
        self.assertIn("flood_drowning_merdeth", ids,
                      "flood encounter should be eligible during the flood.")

    def test_normal_pool_unaffected_by_flood(self):
        get_world_event_manager().activate_event("flood")
        ids = self._eligible_ids("dune")
        self.assertIn("merdeth_advance", ids,
                      "the flood should add encounters, not suppress the normal pool.")


class TestFloodEncounterContract(unittest.TestCase):
    def _flood_entries(self):
        return [e for e in _load_region().encounter_pool.entries
                if e.id in FLOOD_ENCOUNTERS]

    def test_flood_encounters_resolve_to_creatures(self):
        with open(CREATURES, encoding="utf-8") as f:
            lib = {n["id"] for n in yaml.safe_load(f)["npcs"]}
        for e in self._flood_entries():
            tmpl = (e.payload or {}).get("npc_template")
            self.assertIn(tmpl, lib,
                          f"flood encounter {e.id} references unknown creature {tmpl!r}.")

    def test_flood_encounters_clean_and_narrated(self):
        for e in self._flood_entries():
            self.assertTrue(e.narrative.strip(), f"{e.id} has no narrative.")
            low = e.narrative.lower()
            for tok in B3_BANNED:
                self.assertNotIn(tok, low, f"{e.id} carries era token {tok!r} (B3).")
            for tok in Q1_FORBIDDEN:
                self.assertNotIn(tok, low, f"{e.id} names canon figure {tok!r} (Q1).")


if __name__ == "__main__":
    unittest.main()
