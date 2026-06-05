# -*- coding: utf-8 -*-
"""
tests/test_e1_event_era_cleanness.py — E1 (2026-06-04).

Pins the B3 era-cleanness + milestone-repair pass over the Director /
world-event / room-state narrative layer:

  * The three legacy GCW world events (Imperial Crackdown / Imperial
    Checkpoint / Rebel Propaganda) are renamed to era-clean CW equivalents
    (Security Crackdown / Security Checkpoint / Separatist Agitation) and
    carry no "Imperial / Stormtrooper / Rebel / Empire" player-facing strings.
  * room_states overlay text/keys are era-clean.
  * director.ERA_MILESTONES was inert in CW (keyed on GCW factions the live
    VALID_FACTIONS no longer contains); it is re-keyed to the live CW factions
    so it can actually fire, and its headlines are era-clean.

All DB-free / import-only.
"""
from __future__ import annotations
import os
import re
import pytest

from engine.world_events import EventType, EVENT_DEFS, VALID_EVENT_TYPES
from engine.room_states import STATE_DESCRIPTIONS
from engine.director import ERA_MILESTONES, VALID_FACTIONS

# ── Forbidden GCW tokens (B3 era-cleanness) ──────────────────────────────────
# Word-boundaried / case-managed to avoid false positives (e.g. "TIE" must not
# match "duties"/"cities"; "republic"/"confederacy"/"clone" are CW-clean).
_FORBIDDEN = [
    re.compile(r"imperial", re.I),
    re.compile(r"\bempire\b", re.I),
    re.compile(r"\brebel", re.I),        # rebel / rebels / rebellion / Rebel Alliance
    re.compile(r"stormtrooper", re.I),
    re.compile(r"\bTIE\b"),              # TIE fighter (case-sensitive token)
    re.compile(r"x-wing", re.I),
]

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)


def _gcw_hits(text: str) -> list[str]:
    text = text or ""
    return [p.pattern for p in _FORBIDDEN if p.search(text)]


def _src(rel_path: str) -> str:
    with open(os.path.join(_ROOT, rel_path), encoding="utf-8") as fh:
        return fh.read()


# ── world_events: enum rename ────────────────────────────────────────────────

def test_event_enum_renamed_to_cw():
    members = EventType.__members__
    assert "SECURITY_CRACKDOWN" in members
    assert "SECURITY_CHECKPOINT" in members
    assert "SEPARATIST_AGITATION" in members
    assert EventType.SECURITY_CRACKDOWN.value == "security_crackdown"
    assert EventType.SECURITY_CHECKPOINT.value == "security_checkpoint"
    assert EventType.SEPARATIST_AGITATION.value == "separatist_agitation"
    for gone in ("IMPERIAL_CRACKDOWN", "IMPERIAL_CHECKPOINT", "REBEL_PROPAGANDA"):
        assert gone not in members, f"legacy GCW enum member still present: {gone}"
    for gone_val in ("imperial_crackdown", "imperial_checkpoint", "rebel_propaganda"):
        assert gone_val not in VALID_EVENT_TYPES, gone_val


# ── world_events: every event def is era-clean ───────────────────────────────

def test_all_event_defs_player_strings_era_clean():
    offenders = {}
    for etype, edef in EVENT_DEFS.items():
        for field in ("name", "announce_text", "expire_text"):
            hits = _gcw_hits(getattr(edef, field, ""))
            if hits:
                offenders[f"{etype.value}.{field}"] = hits
    assert not offenders, f"GCW tokens in event strings: {offenders}"


# ── world_events: effects preserved + dormant key renamed ────────────────────

def test_event_effects_preserved_and_dormant_key_renamed():
    sc = EVENT_DEFS[EventType.SECURITY_CRACKDOWN].mechanical_effects
    assert sc.get("smuggling_pay_mult") == 1.5
    assert sc.get("patrol_spawn_mult") == 2.0
    sa = EVENT_DEFS[EventType.SEPARATIST_AGITATION].mechanical_effects
    assert sa.get("cis_influence_tick") == 1
    assert "rebel_influence_tick" not in sa
    # the legacy dormant key must not survive anywhere in the catalog
    for etype, edef in EVENT_DEFS.items():
        assert "rebel_influence_tick" not in edef.mechanical_effects, etype.value


def test_world_events_source_free_of_legacy_event_tokens():
    src = _src("engine/world_events.py")
    # the comment block legitimately *names* the legacy members once to explain
    # the rename; assert the live identifiers/values are gone instead. (The
    # dormant-key rename is guarded structurally by the EVENT_DEFS scan above.)
    for tok in ('"imperial_crackdown"', '"imperial_checkpoint"', '"rebel_propaganda"'):
        assert tok not in src, f"legacy token literal still in world_events.py: {tok}"


# ── room_states: era-clean ───────────────────────────────────────────────────

def test_room_states_keys_renamed():
    for present in ("security_crackdown", "separatist_agitation",
                    "republic_control", "cis_presence"):
        assert present in STATE_DESCRIPTIONS, present
    for gone in ("imperial_crackdown", "rebel_propaganda",
                 "imperial_control", "rebel_presence"):
        assert gone not in STATE_DESCRIPTIONS, gone


def test_room_states_text_era_clean():
    offenders = {k: _gcw_hits(v) for k, v in STATE_DESCRIPTIONS.items() if _gcw_hits(v)}
    assert not offenders, f"GCW tokens in room-state text: {offenders}"


# ── director: milestone table re-keyed + functional ──────────────────────────

def test_era_milestones_faction_keys_are_live_factions():
    """Every milestone faction MUST be in VALID_FACTIONS or its average lookup
    silently returns 0 and the milestone is inert (the original GCW bug)."""
    bad = [m[0] for m in ERA_MILESTONES if m[0] not in VALID_FACTIONS]
    assert not bad, f"milestone factions not in live VALID_FACTIONS: {bad}"


def test_era_milestones_event_types_valid():
    bad = [m[4] for m in ERA_MILESTONES
           if m[4] is not None and m[4] not in VALID_EVENT_TYPES]
    assert not bad, f"milestone evt_type not a valid event: {bad}"


def test_era_milestones_headlines_era_clean():
    offenders = {m[2]: _gcw_hits(m[3]) for m in ERA_MILESTONES if _gcw_hits(m[3])}
    assert not offenders, f"GCW tokens in milestone headlines: {offenders}"


def test_below_threshold_special_case_matches_table():
    """The hardcoded below-threshold branch key must exist in the table, so the
    'fires when avg is below' milestone and the dispatch logic cannot drift."""
    keys = [m[2] for m in ERA_MILESTONES]
    assert "power_vacuum" in keys
    src = _src("engine/director.py")
    assert 'era_key == "power_vacuum"' in src
    # the legacy below-threshold key must be gone from both table and logic
    assert "imperial_retreat" not in keys
    assert "imperial_retreat" not in src


def test_director_source_free_of_legacy_event_tokens():
    """Vocab set, event→state map, and the crackdown special-case must all use
    the renamed CW event values."""
    src = _src("engine/director.py")
    for tok in ("imperial_crackdown", "imperial_checkpoint", "rebel_propaganda"):
        assert tok not in src, f"legacy event token still in director.py: {tok}"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
