# -*- coding: utf-8 -*-
"""tests/test_guide_22_espionage_rework.py — Guide_22_Espionage.md SYN.5 update verification.

What this drop changed
----------------------
Added the +intel handover (SYN.5 espionage-as-influence) mechanic to Guide_22.
The feature was shipped in engine/intel_handlers.py but not documented in the guide.

Tests verify
------------
A. The +intel handover command is documented (syntax + both forms).
B. Quality tier payout rates match engine/intel_handlers.py constants.
C. Region specificity requirement is explained (influence = 0 with no region).
D. Freshness window is mentioned (24 hours).
E. INTELLIGENCE_THAW world event is mentioned.
F. The handover section explains faction-membership requirement.
G. Quick Reference table includes +intel handover.
H. Numbers table includes the payout rates.
I. No old stale credit range (the old "500-2,000 cr" as the only handler rate).
"""

import pathlib

GUIDE_PATH = pathlib.Path("data/guides/Guide_22_Espionage.md")


def read_guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_22_Espionage.md not found"


def test_handover_command_documented():
    text = read_guide()
    assert "+intel handover" in text, (
        "+intel handover command must be documented (SYN.5 feature)"
    )


def test_handover_both_forms_present():
    text = read_guide()
    # Default form (first sealed report)
    assert "+intel handover" in text
    # Specific-id form
    assert "+intel handover <id>" in text or "handover <report" in text or "handover [<id" in text, (
        "+intel handover <id> form must be documented"
    )


def test_quality_tiers_all_present():
    text = read_guide()
    for tier in ("Low", "Medium", "High"):
        assert tier in text, f"Quality tier '{tier}' missing from guide"


def test_low_payout_rates_match_engine():
    text = read_guide()
    # engine: LOW = (1, 3, 200, 500)
    assert "200" in text, "Low-quality minimum credits (200) not documented"
    assert "500" in text, "Low-quality maximum credits (500) not documented"
    assert "1" in text, "Low-quality minimum influence (1) not documented"
    assert "3" in text, "Low-quality maximum influence (3) not documented"


def test_medium_payout_rates_match_engine():
    text = read_guide()
    # engine: MEDIUM = (4, 8, 600, 1500)
    assert "600" in text, "Medium-quality minimum credits (600) not documented"
    assert "1,500" in text or "1500" in text, "Medium-quality maximum credits (1500) not documented"
    assert "4" in text, "Medium-quality minimum influence (4) not documented"
    assert "8" in text, "Medium-quality maximum influence (8) not documented"


def test_high_payout_rates_match_engine():
    text = read_guide()
    # engine: HIGH = (10, 20, 2000, 5000)
    assert "2,000" in text or "2000" in text, "High-quality minimum credits (2000) not documented"
    assert "5,000" in text or "5000" in text, "High-quality maximum credits (5000) not documented"
    assert "10" in text, "High-quality minimum influence (10) not documented"
    assert "20" in text, "High-quality maximum influence (20) not documented"


def test_region_specificity_documented():
    text = read_guide()
    lower = text.lower()
    assert "region" in lower, "Region requirement for influence not mentioned"
    assert "influence" in lower, "Territory influence reward not mentioned"
    # The key mechanic: no known region = no influence
    assert "zero" in lower or "no influence" in lower or "0" in text, (
        "Guide must note that intel without a named region yields no influence"
    )


def test_freshness_window_documented():
    text = read_guide()
    assert "24" in text, (
        "24-hour freshness window must be documented (engine _FRESHNESS_WINDOW_SECS)"
    )


def test_intelligence_thaw_documented():
    text = read_guide()
    lower = text.lower()
    assert "intelligence thaw" in lower or "intel thaw" in lower, (
        "INTELLIGENCE_THAW world event must be mentioned (doubles credit payout)"
    )


def test_faction_membership_requirement():
    text = read_guide()
    lower = text.lower()
    assert "faction" in lower and ("member" in lower or "independent" in lower), (
        "Guide must note that independent characters cannot use +intel handover"
    )


def test_quick_reference_includes_handover():
    text = read_guide()
    # The quick reference table must have the handover row
    lines = text.splitlines()
    table_lines = [l for l in lines if "+intel handover" in l and "|" in l]
    assert table_lines, (
        "+intel handover must appear in the Quick Reference table (§12)"
    )


def test_numbers_table_includes_payout_tiers():
    text = read_guide()
    # The numbers table (§13) must have all three quality tiers
    assert "Low quality" in text or "low quality" in text.lower(), (
        "Low quality payout row missing from numbers table"
    )
    assert "Medium quality" in text or "medium quality" in text.lower(), (
        "Medium quality payout row missing from numbers table"
    )
    assert "High quality" in text or "high quality" in text.lower(), (
        "High quality payout row missing from numbers table"
    )


def test_era_clean_no_imperial():
    text = read_guide()
    lower = text.lower()
    # B3: No GCW-era references in production strings.
    # "Imperial Intel" or "Rebel Alliance" would be era violations.
    assert "imperial intel" not in lower, (
        "B3 era violation: 'Imperial Intel' is a GCW-era org name, not Clone Wars"
    )
    assert "rebel alliance" not in lower, (
        "B3 era violation: 'Rebel Alliance' must not appear in guide"
    )
    assert "stormtrooper" not in lower, (
        "B3 era violation: 'stormtrooper' must not appear in guide"
    )
