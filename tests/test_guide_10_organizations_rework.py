# -*- coding: utf-8 -*-
"""tests/test_guide_10_organizations_rework.py — Guide_10 command accuracy fix.

What this drop changed
----------------------
§10 Commands Quick Reference had 7 wrong commands referencing nonexistent
parser verbs. §3 Equipment Issuance falsely claimed `+faction equipment`
existed. Both sections corrected to match parser/faction_commands.py.

Tests verify
------------
A. Old wrong commands are gone (the stale entries removed from §10).
B. Correct replacement commands are present in §10.
C. Equipment Issuance section no longer claims `+faction equipment`.
D. `faction requisition` documented as the replacement-request verb.
E. Era-cleanliness: no GCW-era faction names.
"""

import pathlib

GUIDE_PATH = pathlib.Path("data/guides/Guide_10_Organizations_Factions.md")


def read_guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


# ── A. Guide exists ────────────────────────────────────────────────────────────

def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_10_Organizations_Factions.md not found"


# ── B. Old wrong commands are gone ────────────────────────────────────────────

def test_faction_equipment_command_removed():
    """"+faction equipment" was a nonexistent command; must not appear in §10 table."""
    text = read_guide()
    # Allow "faction equipment" only as part of inline narrative context (e.g.
    # "faction equipment officer") — the bare table entry "+faction equipment"
    # must be gone.
    assert "`+faction equipment`" not in text, (
        "`+faction equipment` must not appear (command does not exist in parser)"
    )


def test_faction_members_command_removed():
    """`+faction members` was wrong; correct is `faction roster`."""
    text = read_guide()
    assert "`+faction members`" not in text, (
        "`+faction members` must not appear (correct command is `faction roster`)"
    )


def test_faction_comm_command_removed():
    """`+faction comm <msg>` was wrong; correct is `faction channel <message>`."""
    text = read_guide()
    # Must not appear as a bare `+faction comm` command entry
    assert "`+faction comm " not in text, (
        "`+faction comm <msg>` must not appear (correct command is `faction channel`)"
    )


def test_plus_promote_standalone_removed():
    """`+promote <character>` was wrong; correct is `faction promote <character>`."""
    text = read_guide()
    assert "`+promote " not in text, (
        "`+promote <character>` must not appear (correct command is `faction promote`)"
    )


def test_plus_discipline_command_removed():
    """`+discipline <char>` was wrong; correct is `faction warn`/`faction expel`."""
    text = read_guide()
    assert "`+discipline " not in text, (
        "`+discipline <char>` must not appear (correct command is `faction warn`/`faction expel`)"
    )


def test_plus_treasury_standalone_removed():
    """`+treasury` was wrong; correct is `faction treasury`."""
    text = read_guide()
    # "+treasury" might appear in "faction treasury", so check for bare backtick form
    assert "`+treasury`" not in text, (
        "`+treasury` must not appear (correct command is `faction treasury`)"
    )
    assert "`+treasury donate" not in text, (
        "`+treasury donate <amount>` must not appear (correct command is `faction invest`)"
    )


# ── C. Correct replacement commands are present ───────────────────────────────

def test_faction_list_documented():
    text = read_guide()
    assert "`faction list`" in text, "`faction list` must appear in §10 Quick Reference"


def test_faction_join_documented():
    text = read_guide()
    assert "`faction join" in text, "`faction join <code>` must appear in §10 Quick Reference"


def test_faction_roster_documented():
    text = read_guide()
    assert "`faction roster`" in text, (
        "`faction roster` must appear (replaces nonexistent `+faction members`)"
    )


def test_faction_channel_documented():
    text = read_guide()
    assert "`faction channel" in text, (
        "`faction channel <message>` must appear (replaces nonexistent `+faction comm`)"
    )


def test_faction_promote_documented():
    text = read_guide()
    assert "`faction promote" in text, (
        "`faction promote <character>` must appear (replaces nonexistent `+promote`)"
    )


def test_faction_warn_documented():
    text = read_guide()
    assert "`faction warn" in text, (
        "`faction warn <character>` must appear (replaces nonexistent `+discipline`)"
    )


def test_faction_expel_documented():
    text = read_guide()
    assert "`faction expel" in text, (
        "`faction expel <character>` must appear (replaces nonexistent `+discipline`)"
    )


def test_faction_treasury_documented():
    text = read_guide()
    assert "`faction treasury`" in text, (
        "`faction treasury` must appear (replaces nonexistent `+treasury`)"
    )


def test_faction_invest_documented():
    text = read_guide()
    assert "`faction invest" in text, (
        "`faction invest <amount>` must appear (replaces nonexistent `+treasury donate`)"
    )


def test_reputation_command_documented():
    text = read_guide()
    assert "`+reputation`" in text, "`+reputation` must appear in §10 Quick Reference"


def test_guild_list_documented():
    text = read_guide()
    assert "`guild list`" in text, "`guild list` must appear in §10 Quick Reference"


def test_guild_join_documented():
    text = read_guide()
    assert "`guild join" in text, "`guild join <code>` must appear in §10 Quick Reference"


def test_guild_leave_documented():
    text = read_guide()
    assert "`guild leave" in text, "`guild leave <code>` must appear in §10 Quick Reference"


# ── D. Equipment Issuance section accuracy ────────────────────────────────────

def test_equipment_auto_issued_not_command_claimed():
    """+faction equipment must not be claimed as the way to get gear."""
    text = read_guide()
    assert "+faction equipment" not in text, (
        "§3 Equipment Issuance must not claim `+faction equipment` exists"
    )


def test_faction_requisition_documented():
    """faction requisition must appear as the replacement-request verb."""
    text = read_guide()
    assert "faction requisition" in text, (
        "`faction requisition` must be documented as how to request replacement gear"
    )


def test_equipment_auto_issuance_described():
    """Guide must explain equipment is issued automatically on promotion."""
    text = read_guide()
    lower = text.lower()
    assert "automatically" in lower or "automatic" in lower, (
        "Equipment Issuance section must explain gear is automatically issued on promotion"
    )


# ── E. Era cleanness ─────────────────────────────────────────────────────────

def test_era_clean_no_imperial():
    text = read_guide()
    lower = text.lower()
    assert "imperial army" not in lower, "B3 era violation: 'Imperial Army' in guide"
    assert "rebel alliance" not in lower, "B3 era violation: 'Rebel Alliance' in guide"
    assert "stormtrooper" not in lower, "B3 era violation: 'stormtrooper' in guide"


# ── F. Authoritative quality pass (2026-06-22): data accuracy vs the seed ──────
# Cross-checks Guide_10 against data/worlds/clone_wars/organizations.yaml and
# engine/organizations.py ground truth. The prior pass corrected §10 commands;
# this pass corrected the rank tables, guild model, and phantom-mechanic claims.

def test_bhg_guildmaster_rank_present():
    """BHG has 6 ranks (0-5); the level-5 Guildmaster (faction_admin) must be
    documented — the seed defines it and the guide previously stopped at Veteran."""
    text = read_guide()
    assert "Guildmaster" in text, (
        "BHG rank table must include the Guildmaster rank (level 5, min_rep 90) "
        "per organizations.yaml"
    )
    assert "Novice → Veteran" not in text, (
        "BHG rank-count must read 'Novice → Guildmaster' (6 ranks), not "
        "'Novice → Veteran' (5)"
    )


def test_guild_cap_is_three_not_unlimited():
    """join_guild enforces MAX_GUILD_MEMBERSHIPS = 3; the guide must not claim
    'any number of guilds.'"""
    text = read_guide()
    lower = text.lower()
    assert "any number of guild" not in lower, (
        "Guild cap is 3 (MAX_GUILD_MEMBERSHIPS), not 'any number of guilds'"
    )
    assert "up to three guild" in lower, (
        "Guide must state the up-to-three-guild membership cap"
    )


def test_guild_dues_range_accurate():
    """organizations.yaml guild dues are 25–75 cr/week (not the old 50–100 claim)."""
    text = read_guide()
    assert "50–100" not in text, (
        "Stale guild-dues range '50–100' — real seed dues are 25–75 cr/week"
    )
    assert "25–75" in text, "Guide must document the real 25–75 cr/week guild-dues range"


def test_no_phantom_guild_join_skillgate():
    """join_guild enforces NO skill check / audition to be admitted — the guide
    must not claim those phantom gates exist."""
    text = read_guide()
    assert "Performance audition" not in text, (
        "Phantom mechanic: join_guild requires no Performance audition"
    )
    assert "Mechanical Repair check above a threshold" not in text, (
        "Phantom mechanic: join_guild requires no Mechanical Repair skill check"
    )


def test_real_guild_benefit_cp_discount_documented():
    """The one real mechanical guild benefit is the flat 20% CP training discount
    (GUILD_CP_DISCOUNT = 0.20, get_guild_cp_multiplier)."""
    text = read_guide()
    assert "20%" in text, "Guide must document the 20% CP training discount"
    assert "#/guide/cp-progression" in text, (
        "Guide must cross-link CP Progression for the discount mechanic"
    )


def test_slicers_collective_real_name():
    """The seed display name is 'Slicers' Collective', not 'Slicers' Guild'."""
    text = read_guide()
    assert "Slicers' Collective" in text, (
        "Guild's real name is 'Slicers' Collective' per organizations.yaml"
    )
    assert "Slicers' Guild" not in text, (
        "Stale name 'Slicers' Guild' — real display name is 'Slicers' Collective'"
    )


def test_jedi_hq_real_room_name():
    """Jedi HQ seed room is 'Jedi Temple - Entrance Hall', not a phantom
    'Main Hall' room."""
    text = read_guide()
    assert "Entrance Hall" in text, (
        "Jedi HQ room is the Entrance Hall (hq_room_name in organizations.yaml)"
    )
    assert "Main Hall" not in text, (
        "Phantom room: the Jedi HQ is 'Entrance Hall', not 'Main Hall'"
    )
