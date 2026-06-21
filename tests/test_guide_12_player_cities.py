"""tests/test_guide_12_player_cities.py — Guide_12_Player_Cities.md quality-pass verification.

Authoritative quality pass (Opus loop, 2026-06-21). Guards the guide against the
accuracy drift the prior version carried:

  - No phantom "Guide #13" cross-reference (no Guide_13 exists; housing is `@housing`).
  - Launch-gating reality documented (`+city found` is off at launch via
    `cities.found_enabled`, which defaults False in data/tunables.yaml).
  - The `+city guards` NPC-guard subsystem (shipped, omitted from the old guide) is
    documented, and its numbers match the engine constants at HEAD.
  - The `+city found <name> in <region>` founding syntax is documented.
  - Founding costs + guard slot caps match the engine, not stale invented values.
  - Section numbering is contiguous after the inserted guards section.
  - Era-clean (no Imperial/Empire/Rebel/TIE in a production string).
"""

import pathlib
import re

import pytest

GUIDE_PATH = pathlib.Path("data/guides/Guide_12_Player_Cities.md")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_12_Player_Cities.md not found"


def test_no_phantom_guide_13_reference():
    text = read_guide()
    # There is no Guide_13 (the corpus skips 13 and 15). Housing is `@housing`.
    assert "Guide #13" not in text, (
        "Phantom 'Guide #13 — Housing' cross-reference still present "
        "(no Guide_13 exists; reference the housing system / @housing instead)"
    )


def test_launch_gating_documented():
    text = read_guide()
    # Brian decision 2026-06-16 #7: cities are a launch feature-flag, gated OFF.
    # Engine enforces it via get_tunable("cities.found_enabled", False).
    assert "cities.found_enabled" in text, (
        "Guide must document the launch gate (cities.found_enabled) — founding "
        "is disabled at launch and players will hit the 'not available' message"
    )
    assert re.search(r"off at launch|disabled at launch|not available at launch",
                     text, re.IGNORECASE), (
        "Guide must state plainly that city founding is off at launch"
    )


def test_found_in_region_syntax_present():
    text = read_guide()
    assert "in <region" in text or "in vertical_bazaar" in text, (
        "Guide must document the '+city found <name> in <region>' founding form"
    )


def test_city_guards_section_present():
    text = read_guide()
    assert "City Guards" in text, "Guide must document the +city guards subsystem"
    for cmd in ("+city guards assign", "+city guards remove"):
        assert cmd in text, f"Guide quick reference must include {cmd!r}"


def test_guard_slot_caps_match_engine():
    text = read_guide()
    from engine.player_cities import CITY_GUARD_SLOTS_BY_HQ_TIER
    # The guide states city-pool slots as 3 / 6 / 14 — pin them to the engine.
    assert CITY_GUARD_SLOTS_BY_HQ_TIER == {
        "outpost": 3, "chapter_house": 6, "fortress": 14
    }, "Engine guard-slot caps changed; update Guide_12 §10 + §16 to match"
    for n in ("3", "6", "14"):
        assert n in text


def test_guard_cost_and_upkeep_match_engine():
    text = read_guide()
    from engine.territory import GUARD_COST
    from engine.player_cities import CITY_GUARD_MAINT_PER_WEEK_CR
    assert GUARD_COST == 500, "Station cost changed; update Guide_12"
    assert CITY_GUARD_MAINT_PER_WEEK_CR == 200, "Guard upkeep changed; update Guide_12"
    assert "500 cr" in text, "Guide must state the 500 cr one-time station cost"
    assert "200 cr" in text, "Guide must state the 200 cr/week guard upkeep"


def test_founding_costs_unchanged():
    text = read_guide()
    # The headline credit sinks the guide teaches.
    for amount in ("25,000", "75,000", "200,000"):
        assert amount in text, f"Founding cost {amount} missing from guide"


def test_section_numbering_contiguous():
    text = read_guide()
    nums = [int(m.group(1)) for m in re.finditer(r"^## (\d+)\.", text, re.MULTILINE)]
    assert nums == list(range(1, len(nums) + 1)), (
        f"Section numbering not contiguous after guards insertion: {nums}"
    )


def test_era_clean():
    text = read_guide()
    for term in (" Imperial", "Empire", "Rebel", "TIE "):
        assert term not in text, f"Era-dirty term {term!r} in Guide_12 production text"
