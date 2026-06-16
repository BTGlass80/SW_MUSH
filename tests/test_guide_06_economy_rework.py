"""tests/test_guide_06_economy_rework.py — Guide_06_Economy.md rework verification.

Checks:
  - Commissary section present (§9) with all 4 factions documented.
  - Creature spoils section present (§10) with correct mechanics.
  - Frontmatter no longer references deprecated P2P daily cap.
  - Commands table updated with commissary commands.
  - Era-clean: no "daily P2P transfer cap" in production summary.
  - Accuracy: commissary costs match engine/commissary.py COMMISSARY_STOCK.
  - Accuracy: spoils DC and resource types match engine/creature_spoils.py.
"""

import pathlib
import re

GUIDE_PATH = pathlib.Path("data/guides/Guide_06_Economy.md")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_06_Economy.md not found"


def test_frontmatter_no_stale_p2p_cap():
    text = read_guide()
    # Old summary referenced "daily P2P transfer cap" which was removed
    assert "daily P2P transfer cap" not in text, (
        "Stale 'daily P2P transfer cap' still in guide (feature was removed)"
    )


def test_commissary_section_present():
    text = read_guide()
    assert "Faction Commissary" in text, "Commissary section missing from Guide_06"


def test_commissary_four_factions_covered():
    text = read_guide()
    for faction in ("Republic", "CIS", "Hutt Cartel", "Bounty Hunters' Guild"):
        assert faction in text, f"Faction '{faction}' missing from commissary section"


def test_jedi_no_commissary_noted():
    text = read_guide()
    assert "Jedi Order" in text, "Jedi Order commissary absence not documented"
    # The guide should note they have no commissary
    jedi_block = text[text.find("Jedi Order"):][:200]
    assert "no commissary" in jedi_block.lower() or "No commissary" in jedi_block, (
        "Jedi Order commissary absence not clearly stated"
    )


def test_commissary_costs_accurate():
    text = read_guide()
    # Key costs from engine/commissary.py COMMISSARY_STOCK
    cost_checks = [
        ("Republic Service Uniform", "150"),
        ("DC-17 Hand Blaster", "500"),
        ("DC-15A Blaster Rifle", "1,200"),
        ("Republic Combat Plate", "900"),
        ("Tracking Fob", "350"),
        ("Guild License", "100"),
        ("Binder Cuffs", "200"),
    ]
    for item_name, cost_str in cost_checks:
        # Find item and check cost appears nearby
        idx = text.find(item_name)
        assert idx != -1, f"Commissary item '{item_name}' missing from guide"
        nearby = text[idx:idx + 100]
        assert cost_str in nearby, (
            f"Cost {cost_str} not found near '{item_name}' — may be stale"
        )


def test_commissary_commands_present():
    text = read_guide()
    assert "+commissary" in text, "+commissary command missing from guide"
    assert "+commissary buy" in text, "+commissary buy command missing"
    assert "+commissary sell" in text, "+commissary sell command missing"


def test_creature_spoils_section_present():
    text = read_guide()
    assert "Creature Spoils" in text, "Creature Spoils section missing from Guide_06"


def test_creature_spoils_skill_and_dc():
    text = read_guide()
    assert "Survival" in text, "Survival skill not mentioned in creature spoils section"
    # Default DC is 8 (SPOILS_DIFFICULTY in engine/creature_spoils.py)
    assert "DC 8" in text or "DC: 8" in text or "DC 8" in text or "| 8 |" in text, (
        "Default spoils DC 8 not documented"
    )


def test_creature_spoils_quality_cap():
    text = read_guide()
    # Quality cap is 65 (SPOILS_QUALITY_CEILING)
    assert "65" in text, "Quality cap of 65 not mentioned in creature spoils section"


def test_creature_spoils_no_credits_note():
    text = read_guide()
    # Guide should make clear spoils are not credits
    spoils_idx = text.find("Creature Spoils")
    spoils_block = text[spoils_idx:spoils_idx + 1500]
    assert "not credits" in spoils_block.lower() or "no credit" in spoils_block.lower() or "not raw credits" in spoils_block.lower(), (
        "Guide should clarify creature spoils are not credits"
    )


def test_creature_spoils_creatures_listed():
    text = read_guide()
    # Key creatures with functional spoils in npcs_creatures.yaml
    for creature in ("Magus", "Stalker Lizard", "Wrix", "Hitcher Crab", "Spor Crawler"):
        assert creature in text, f"Creature '{creature}' missing from spoils table"


def test_commands_table_includes_commissary():
    text = read_guide()
    # The updated commands table should include commissary
    assert "Commissary" in text, "Commissary missing from economy commands table"


def test_guide_sections_ordering():
    text = read_guide()
    # Verify the new sections come after the existing ones
    commissary_pos = text.find("Faction Commissary")
    spoils_pos = text.find("Creature Spoils")
    commands_pos = text.find("Economy Commands Quick Reference")
    assert commissary_pos != -1 and spoils_pos != -1 and commands_pos != -1
    assert commissary_pos < spoils_pos < commands_pos, (
        "Guide sections not in expected order: Commissary → Spoils → Commands"
    )


def test_organic_and_chemical_resource_types():
    text = read_guide()
    spoils_idx = text.find("Creature Spoils")
    spoils_block = text[spoils_idx:spoils_idx + 2000]
    assert "Organic" in spoils_block or "organic" in spoils_block, (
        "Organic resource type not mentioned in spoils section"
    )
    assert "Chemical" in spoils_block or "chemical" in spoils_block, (
        "Chemical resource type not mentioned in spoils section (Hitcher Crab/Spor Crawler)"
    )
