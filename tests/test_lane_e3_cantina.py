# -*- coding: utf-8 -*-
"""
tests/test_lane_e3_cantina.py — Sourcebook Enrichment Lane E3 (Wretched Hive §2C).

The d66 Cantina Encounter Table, delivered to its two consumers:
  * engine/cantina_encounters.py — the 36-entry table + a true-WEG d66 roll
    (two d6 read as tens/ones, NOT summed).
  * +cantina (parser/scene_commands.CantinaEncounterCommand) — a BUILDER-gated GM
    scene-seeding tool that rolls the table and poses the beat to the room
    (handles the disruptive plot-hook entries intentionally).
  * data/ambient_events.yaml cantina pool — enriched with the atmospheric,
    background-appropriate subset (the disruptive entries are GM-only).

Era-translated (no off-era military framing — B3) and original-cast (no canonical
named figures — Q1).

DEFERRED (flagged, NOT shipped): the venue front_owner/true_owner split and the
§2A/§2B venue-profile schema — there is no investigation/territory consumer in
HEAD (housing carries a single shopfront_owner_id, no venue model), so the
flag-pair would be schema-ahead-of-consumer. It ships with its mechanic later.
"""
from __future__ import annotations
import os
import random
import yaml

from engine.cantina_encounters import (
    CANTINA_ENCOUNTERS, D66_CODES, roll_cantina_encounter,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


# ── The d66 table ───────────────────────────────────────────────────────────

def test_d66_table_complete_and_well_formed():
    assert len(D66_CODES) == 36
    assert set(CANTINA_ENCOUNTERS) == set(D66_CODES)
    for code in D66_CODES:
        tens, ones = divmod(code, 10)
        assert 1 <= tens <= 6 and 1 <= ones <= 6, f"bad d66 code {code}"
        assert CANTINA_ENCOUNTERS[code].strip(), f"empty entry for {code}"


def test_roll_is_true_d66_and_covers_all_codes():
    # Deterministic for a seeded RNG; returns the table text for the code.
    code, text = roll_cantina_encounter(random.Random(42))
    assert code in CANTINA_ENCOUNTERS and text == CANTINA_ENCOUNTERS[code]
    # Every code is reachable (and only valid codes appear) — proves tens/ones,
    # not a 2..12 sum (a sum could never produce 11/16/61/66 uniformly).
    seen = set()
    r = random.Random(1)
    for _ in range(6000):
        c, _t = roll_cantina_encounter(r)
        assert c in CANTINA_ENCOUNTERS
        seen.add(c)
    assert seen == set(D66_CODES), f"unreachable codes: {set(D66_CODES) - seen}"


def test_d66_strings_b3_clean():
    banned = ("imperial", "empire", "stormtrooper", "rebel", "tie ", "x-wing", "death star")
    for code, text in CANTINA_ENCOUNTERS.items():
        low = text.lower()
        for tok in banned:
            assert tok not in low, f"d66 {code} carries banned token {tok!r}: {text}"


def test_d66_strings_q1_clean():
    # The source book is almost entirely original; no canonical figures should
    # have crept in via era-translation.
    canon = ("jabba", "anakin", "obi-wan", "obi wan", "yoda", "dooku",
             "grievous", "palpatine", "mace windu", "chalmun", "evazan")
    for code, text in CANTINA_ENCOUNTERS.items():
        low = text.lower()
        for tok in canon:
            assert tok not in low, f"d66 {code} names canon figure {tok!r}: {text}"


# ── The +cantina GM command ─────────────────────────────────────────────────

def test_cantina_command_registered_and_staff_gated():
    from parser.commands import CommandRegistry, AccessLevel
    from parser.scene_commands import register_scene_commands
    reg = CommandRegistry()
    register_scene_commands(reg)
    cmd = reg.get("+cantina")
    assert cmd is not None, "+cantina not registered"
    assert reg.get("+cantinaroll") is not None, "+cantinaroll alias missing"
    assert cmd.access_level == AccessLevel.BUILDER, "+cantina must be staff-gated"


def test_cantina_command_reads_the_table():
    with open(os.path.join(_ROOT, "parser", "scene_commands.py"), encoding="utf-8") as fh:
        src = fh.read()
    assert "class CantinaEncounterCommand(" in src
    assert "roll_cantina_encounter" in src
    assert "broadcast_to_room" in src
    assert "CantinaEncounterCommand()" in src   # in register_scene_commands


# ── Ambient cantina pool enrichment (atmospheric subset) ─────────────────────

def test_cantina_ambient_pool_enriched_without_losing_originals():
    with open(os.path.join(_ROOT, "data", "ambient_events.yaml"), encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    cantina = data.get("cantina")
    assert isinstance(cantina, list) and cantina, "cantina pool missing"
    texts = [e["text"] if isinstance(e, dict) else e for e in cantina]
    # an original line is retained
    assert any("wipes down the same spot" in t for t in texts), "lost an original cantina line"
    # an atmospheric d66 line was added
    assert any("high-stakes sabacc hand" in t for t in texts), "d66 atmospheric line not added"
    # the disruptive plot hooks stayed OUT of the passive pool
    for forbidden in ("thermal detonator", "taking hostages", "tactical team", "shoves the deed"):
        assert not any(forbidden in t.lower() for t in texts), \
            f"disruptive d66 beat leaked into the passive ambient pool: {forbidden!r}"
