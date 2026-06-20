# -*- coding: utf-8 -*-
"""Nano map alignment (2026-06-20): the Jedi Temple Meditation Garden pin must
sit on the painted greenhouse.

Brian's live playtest: the painted garden sits at the (1.2, 4.8) cell, but the
Meditation Garden room was coded at (1.2, 3.0) — so the nav pin labelled a plain
room "Garden" and put "Medical Bay" on the actual greenhouse. Fixed by swapping
the two rooms' grid positions (and the garden landmark + the two hub corridors
that feed them). This guards the alignment so a future edit can't silently
re-introduce the mismatch.
"""
from __future__ import annotations

import os

import yaml

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.path.join(REPO, "data", "worlds", "clone_wars", "maps", "jedi_temple.yaml")


def _load():
    with open(MAP, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _room(raw, slug):
    for r in raw["rooms"]:
        if r["slug"] == slug:
            return r
    raise AssertionError(f"room {slug} not found")


def test_meditation_garden_sits_on_the_painted_garden_cell():
    raw = _load()
    garden = _room(raw, "jedi_temple_meditation_garden")
    assert (garden["x"], garden["y"]) == (1.2, 4.8), (
        "Meditation Garden must sit at the (1.2, 4.8) cell where the substrate "
        "paints the greenhouse"
    )


def test_medical_bay_moved_off_the_garden_cell():
    raw = _load()
    medbay = _room(raw, "jedi_temple_medical_bay")
    assert (medbay["x"], medbay["y"]) == (1.2, 3.0), (
        "Medical Bay must not occupy the painted-garden cell"
    )


def test_garden_landmark_pin_matches_the_room():
    raw = _load()
    garden_lm = next(lm for lm in raw["landmarks"] if lm["id"] == "garden")
    assert list(garden_lm["pos"]) == [1.2, 4.8], (
        "the Meditation Garden landmark pin must track the room to the painted cell"
    )


def test_hub_corridor_to_garden_ends_at_the_garden_cell():
    raw = _load()
    path = raw["exit_paths"]["211-216"]["path"]
    assert list(path[-1]) == [1.2, 4.8], (
        "the entrance-hall->garden corridor must terminate at the garden's new cell"
    )
