"""tests/test_guide_11_territory_rework.py — Guide_11_Territory_Control.md rework verification.

Checks (post-SYN.1-3 rework):
  - No stale per-org claim caps ("Maximum 3 claims" / "10 total") — retired in SYN.1.b.
  - No retired command faction guard station (per-room guard placement retired in SYN.1.b).
  - Claims section uses region language (not "room" claiming).
  - Region Contest section is present.
  - Garrison auto-deploy is documented.
  - Weekly maintenance cost reflects region rates (2,000 cr + 1,000 cr garrison).
  - faction contest and faction resource_outlook commands present.
  - Era-clean: no "Alliance sentry" (Rebel Alliance — B3 violation) or "Imperial" guard descriptions.
"""

import pathlib
import re

GUIDE_PATH = pathlib.Path("data/guides/Guide_11_Territory_Control.md")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_11_Territory_Control.md not found"


def test_no_stale_per_org_claim_caps():
    text = read_guide()
    # SYN.1.b retired per-org caps; the old guide said "Maximum 3 claims per zone, 10 total"
    assert "Maximum 3 claims" not in text, (
        "Stale 'Maximum 3 claims per zone' cap still in guide (retired in SYN.1.b)"
    )
    assert "10 total per org" not in text, (
        "Stale '10 total per org' cap still in guide (retired in SYN.1.b)"
    )


def test_no_retired_guard_station_command():
    text = read_guide()
    # faction guard station was retired in SYN.1.b — per-room guard placement is gone
    assert "faction guard station" not in text, (
        "'faction guard station' is a retired command and must not appear in the guide"
    )
    assert "guard station" not in text, (
        "'guard station' is a retired mechanic and must not appear in the guide"
    )


def test_region_claiming_language():
    text = read_guide()
    # Guide must use region language, not room language for claims
    assert "wilderness region" in text.lower(), (
        "Guide must explain that faction claim targets a wilderness region, not a room"
    )


def test_region_contest_section_present():
    text = read_guide()
    assert "Region Contest" in text or "region contest" in text.lower(), (
        "Region Contest section missing from Guide_11 (SYN.3 feature)"
    )
    # Key contest mechanics
    assert "Anchor" in text, "Region Anchor NPC mechanic not documented in contest section"
    assert "7" in text, "7-day contest duration not mentioned"
    assert "14" in text, "14-day cooldown not mentioned"


def test_garrison_auto_deploy_documented():
    text = read_guide()
    lower = text.lower()
    assert "auto" in lower or "automatically" in lower, (
        "Guide must state that garrisons auto-deploy on region claim (not manual placement)"
    )
    # Should mention the garrison count
    assert "5" in text, "Garrison size (5 guards) not mentioned"


def test_weekly_maintenance_cost():
    text = read_guide()
    # Region weekly maint = 2,000 cr/region; garrison = 1,000 cr; total 3,000 cr
    assert "2,000" in text, "Region base maintenance cost (2,000 cr/week) not documented"
    assert "1,000" in text, "Garrison upkeep cost (1,000 cr/week) not documented"


def test_faction_contest_command_present():
    text = read_guide()
    assert "faction contest" in text, "'faction contest' command missing from guide"


def test_faction_resource_outlook_command_present():
    text = read_guide()
    assert "faction resource_outlook" in text, (
        "'faction resource_outlook' command missing from guide"
    )


def test_era_clean_no_alliance_sentry():
    text = read_guide()
    # "Alliance sentry" was the old Rebel Alliance guard description — B3 violation
    assert "Alliance sentry" not in text, (
        "B3 era violation: 'Alliance sentry' (Rebel Alliance) must not appear in guide"
    )


def test_era_clean_no_imperial_guard():
    text = read_guide()
    # "Imperial Garrison Guard" is from the GCW-era empire template — B3 violation
    assert "Imperial Garrison Guard" not in text, (
        "B3 era violation: 'Imperial Garrison Guard' must not appear in guide"
    )
    assert "stormtrooper" not in text.lower(), (
        "B3 era violation: stormtrooper guard description must not appear in guide"
    )


def test_cis_guard_era_appropriate():
    text = read_guide()
    # CIS guard must be a Battle Droid, not "Alliance sentry"
    assert "Battle Droid" in text or "battle droid" in text.lower(), (
        "CIS/Separatist guard description must mention Battle Droid (era-appropriate)"
    )


def test_influence_thresholds_present():
    text = read_guide()
    for score, label in [("25", "Presence"), ("50", "Foothold"), ("75", "Dominance"), ("100", "Control")]:
        assert score in text and label in text, (
            f"Influence threshold {score} ({label}) missing from guide"
        )


def test_passive_income_values_present():
    text = read_guide()
    # REGION_PASSIVE_LAWLESS_MIN=100, MAX=250; CONTESTED_MIN=50, MAX=150
    assert "100" in text and "250" in text, (
        "Lawless passive income range (100-250 cr/day) not documented"
    )
    assert "50" in text and "150" in text, (
        "Contested passive income range (50-150 cr/day) not documented"
    )
