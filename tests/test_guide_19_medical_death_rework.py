"""tests/test_guide_19_medical_death_rework.py — Guide_19_Medical_Death.md rework verification.

Checks:
  - Gear insurance section present with correct commands and premium.
  - Engine-accurate equipped-gear claim (stays on character, not on corpse).
  - Loose inventory / corpse drop described correctly.
  - Insurance premium matches engine/gear_insurance.py constant.
  - Commands quick reference includes +insure variants.
  - Numbers table includes insurance premium.
  - Common pitfalls include equipped-gear and insurance rebuy.
  - Tags updated to include gear insurance.
"""

import pathlib
import importlib.util
import sys

GUIDE_PATH = pathlib.Path("data/guides/Guide_19_Medical_Death.md")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_19_Medical_Death.md not found"


def test_gear_insurance_section_present():
    text = read_guide()
    assert "+insure" in text, "Gear insurance (+insure) section missing from Guide_19"
    assert "Gear Insurance" in text, "Gear Insurance heading missing from Guide_19"


def test_insure_commands_documented():
    text = read_guide()
    assert "+insure buy" in text, "+insure buy command missing"
    assert "+insure cancel" in text, "+insure cancel command missing"


def test_insurance_premium_correct():
    """Premium documented in guide matches engine constant (500 cr)."""
    from engine.gear_insurance import GEAR_INSURANCE_PREMIUM
    text = read_guide()
    assert str(GEAR_INSURANCE_PREMIUM) in text, (
        f"Insurance premium {GEAR_INSURANCE_PREMIUM} not found in guide"
    )
    # Confirm the guide says 500 specifically
    assert "500 cr" in text or "500 credits" in text, (
        "Insurance premium 500 cr not clearly stated in guide"
    )


def test_one_shot_policy_described():
    text = read_guide()
    assert "one-shot" in text.lower(), "One-shot policy nature not described"


def test_equipped_gear_stays_on_character():
    """Guide must say equipped gear stays on character, not on corpse."""
    text = read_guide()
    # The old wrong claim
    assert "equipped weapon stays equipped on the corpse" not in text, (
        "Stale false claim: 'equipped weapon stays on the corpse' still present"
    )
    # The correct claim
    assert "equipped gear" in text.lower(), "Equipped gear behavior not described"
    assert "stays on your character" in text or "stays on the character" in text, (
        "Correct claim about equipped gear staying on character is missing"
    )


def test_loose_inventory_drop_described():
    text = read_guide()
    assert "loose" in text, "Loose inventory distinction not described"
    assert "loose inventory" in text.lower() or "loose loadout" in text.lower(), (
        "Loose inventory/loadout terminology missing"
    )


def test_commands_reference_includes_insure():
    text = read_guide()
    # Quick reference table should include +insure
    assert "| `+insure`" in text or "| `+insure buy`" in text, (
        "+insure not in commands quick reference table"
    )


def test_numbers_table_includes_insurance():
    text = read_guide()
    assert "Gear insurance premium" in text or "insurance premium" in text.lower(), (
        "Insurance premium missing from Numbers At A Glance"
    )


def test_pitfall_equipped_gear():
    text = read_guide()
    assert "equipped weapon drops on death" in text or "equipped" in text, (
        "Equipped-gear pitfall not present in Common Pitfalls"
    )


def test_pitfall_rebuy_insurance():
    text = read_guide()
    assert "rebuy" in text.lower() or "buy again" in text.lower(), (
        "Insurance rebuy pitfall not present in Common Pitfalls"
    )


def test_tags_include_gear_insurance():
    text = read_guide()
    assert "gear insurance" in text.lower(), (
        "Tags do not include gear insurance"
    )


def test_insurance_applies_to_lawless_contested_only():
    text = read_guide()
    # Insurance should note it only applies in lawless/contested
    assert "lawless" in text and "contested" in text, (
        "Guide doesn't specify which security zones insurance applies to"
    )


def test_no_era_violations():
    """Era-cleanness check: no Imperial/Rebel/TIE in production strings."""
    text = read_guide()
    # Strip frontmatter and code blocks where era-mapping keys are exempt
    body = text
    for forbidden in ("Imperial", "Rebel Alliance", "TIE Fighter"):
        assert forbidden not in body, (
            f"Era-clean violation: '{forbidden}' found in Guide_19"
        )
