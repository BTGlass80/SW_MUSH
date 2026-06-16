# -*- coding: utf-8 -*-
"""tests/test_guide_02_chargen_rework.py — Guide_02_Character_Creation.md accuracy pass.

What this drop changed
----------------------
Corrected Guide_02 against the live chargen engine for the Clone Wars era:

- §5 Templates: replaced the GCW-era template table (7 templates including the
  now-removed Jedi Apprentice and Soldier) with the CW-era set from
  data/worlds/clone_wars/chargen_templates.yaml (9 templates). Fixed wrong
  attribute values for Separatist Pilot (MEC was 4D+1, now 4D; PER was 2D+2,
  now 3D) and Technician (KNO was 3D, now 3D+2; TEC was 4D+2, now 4D).

- §6 Force Sensitivity: rewrote entirely. The chargen Force Sensitivity step
  was removed per PG.3.gates.b (May 2026); characters start non-sensitive and
  unlock via Village quest. Old text incorrectly described a Yes/No chargen
  choice and claimed the Jedi Apprentice template was the path to starting with
  Force skills.

- §7 Starting Equipment: corrected. Characters start with 1,000 credits and NO
  default equipment (no blaster pistol / comlink granted at chargen). Gear
  comes from tutorial chains and vendor purchases.

- §8 Wizard: removed the Force Sensitivity step; added Tutorial Chain step.

- §11 Persistence: section was an empty heading — added actual content.

Tests verify
------------
A. Nine templates documented (not seven).
B. Jedi Apprentice not listed as a template row in the template section.
C. Soldier template not listed.
D. Clone Trooper template present with correct attributes.
E. Republic Officer template present.
F. Republic Pilot template present.
G. CIS Field Agent template present.
H. Separatist Pilot has correct MEC (4D) not the old wrong value (4D+1).
I. Technician has correct KNO (3D+2) not the old wrong value (3D alone).
J. Force sensitivity is stated as NOT chosen at chargen.
K. Village quest / Village trials mentioned as the unlock path.
L. Starting credits 1,000 present.
M. No claim that a blaster pistol is granted at chargen.
N. Tutorial Chain step mentioned in wizard section.
O. Persistence section has actual content (not just a heading).
P. Guide exists and has a reasonable length.
"""

import pathlib

GUIDE_PATH = pathlib.Path("data/guides/Guide_02_Character_Creation.md")


def read_guide() -> str:
    return GUIDE_PATH.read_text(encoding="utf-8")


# ── Structural ──────────────────────────────────────────────────────────────

def test_guide_exists():
    assert GUIDE_PATH.exists(), "Guide_02_Character_Creation.md not found"


def test_guide_has_reasonable_length():
    text = read_guide()
    assert len(text) > 5_000, "Guide is suspiciously short — likely truncated"


# ── A/B/C: template count + removed templates ────────────────────────────────

def test_nine_templates_documented():
    text = read_guide()
    assert "Nine pre-built templates" in text, (
        "Guide must say 'Nine pre-built templates' (CW era has 9)"
    )


def test_jedi_apprentice_not_a_template():
    text = read_guide()
    # "Jedi Apprentice" may appear in §6 prose referencing the old GCW era,
    # but must NOT appear as a template table row (prefixed with | **).
    import re
    template_rows = re.findall(r"^\|\s*\*\*(.+?)\*\*", text, re.MULTILINE)
    assert "Jedi Apprentice" not in template_rows, (
        "Jedi Apprentice was removed from CW-era templates "
        "(Jedi PCs are village-gated) and must not appear as a template row"
    )


def test_soldier_template_not_present():
    text = read_guide()
    import re
    template_rows = re.findall(r"^\|\s*\*\*(.+?)\*\*", text, re.MULTILINE)
    assert "Soldier" not in template_rows, (
        "The generic Soldier template was replaced by Clone Trooper in CW era"
    )


# ── D-G: new CW templates present ────────────────────────────────────────────

def test_clone_trooper_template_present():
    text = read_guide()
    assert "Clone Trooper" in text, "Clone Trooper template must be documented"


def test_republic_officer_template_present():
    text = read_guide()
    assert "Republic Officer" in text, "Republic Officer template must be documented"


def test_republic_pilot_template_present():
    text = read_guide()
    assert "Republic Pilot" in text, "Republic Pilot template must be documented"


def test_cis_field_agent_template_present():
    text = read_guide()
    assert "CIS Field Agent" in text, "CIS Field Agent template must be documented"


# ── H: Separatist Pilot correct attributes ───────────────────────────────────

def test_separatist_pilot_mec_4d_not_4d_plus_1():
    text = read_guide()
    # The Separatist Pilot row must contain "4D" for MEC and NOT "4D+1"
    # (the old wrong value). Find the template table section.
    import re
    sep_row = next(
        (line for line in text.splitlines() if "Separatist Pilot" in line and line.startswith("|")),
        None,
    )
    assert sep_row is not None, "Separatist Pilot row not found in template table"
    assert "4D+1" not in sep_row, (
        f"Separatist Pilot MEC must be 4D (not 4D+1). Row: {sep_row!r}"
    )
    assert "4D" in sep_row, (
        f"Separatist Pilot row must contain MEC 4D. Row: {sep_row!r}"
    )


def test_separatist_pilot_per_3d_not_2d_plus_2():
    text = read_guide()
    import re
    sep_row = next(
        (line for line in text.splitlines() if "Separatist Pilot" in line and line.startswith("|")),
        None,
    )
    assert sep_row is not None, "Separatist Pilot row not found in template table"
    cols = [c.strip() for c in sep_row.split("|")]
    # Row format: | Template | DEX | KNO | MEC | PER | STR | TEC | Key Skills |
    # cols[0]="" cols[1]=template cols[2]=DEX cols[3]=KNO cols[4]=MEC
    # cols[5]=PER cols[6]=STR cols[7]=TEC cols[8]=skills
    per_col = cols[5] if len(cols) > 5 else ""
    assert per_col == "3D", (
        f"Separatist Pilot PER must be 3D (not 2D+2). Got: {per_col!r}"
    )


# ── I: Technician correct attributes ─────────────────────────────────────────

def test_technician_kno_3d_plus_2():
    text = read_guide()
    tech_row = next(
        (line for line in text.splitlines() if line.startswith("| **Technician**")),
        None,
    )
    assert tech_row is not None, "Technician row not found in template table"
    cols = [c.strip() for c in tech_row.split("|")]
    kno_col = cols[3] if len(cols) > 3 else ""
    assert kno_col == "3D+2", (
        f"Technician KNO must be 3D+2 (not 3D). Got: {kno_col!r}"
    )


def test_technician_tec_4d():
    text = read_guide()
    tech_row = next(
        (line for line in text.splitlines() if line.startswith("| **Technician**")),
        None,
    )
    assert tech_row is not None, "Technician row not found in template table"
    cols = [c.strip() for c in tech_row.split("|")]
    tec_col = cols[7] if len(cols) > 7 else ""
    assert tec_col == "4D", (
        f"Technician TEC must be 4D (not 4D+2). Got: {tec_col!r}"
    )


# ── J/K: Force sensitivity via Village quest ─────────────────────────────────

def test_force_not_chosen_at_chargen():
    text = read_guide()
    assert "not chosen at character creation" in text, (
        "§6 must state that Force sensitivity is not chosen at character creation"
    )


def test_village_quest_mentioned_as_unlock():
    text = read_guide()
    assert "Village" in text and ("trials" in text or "quest" in text), (
        "§6 must mention the Jedi Village / Village trials as the Force unlock path"
    )


def test_all_characters_start_non_sensitive():
    text = read_guide()
    assert "non-Force-sensitive" in text or "non-sensitive" in text, (
        "§6 must state that all characters start non-Force-sensitive"
    )


# ── L/M: Starting credits / no default equipment ─────────────────────────────

def test_starting_credits_1000():
    text = read_guide()
    assert "1,000 credits" in text, "Starting credits of 1,000 must be mentioned"


def test_no_blaster_granted_at_chargen():
    text = read_guide()
    # Old incorrect claim: "A blaster pistol (500 credits) or other sidearm"
    # New correct text: gear comes from tutorial chains / vendors
    assert "blaster pistol (500 credits) or other sidearm" not in text, (
        "Guide must not claim a blaster pistol is granted at chargen "
        "(characters start with no default equipment)"
    )


def test_equipment_from_tutorial_chains():
    text = read_guide()
    assert "tutorial chain" in text.lower(), (
        "§7 must explain that equipment comes from tutorial chains"
    )


# ── N: Tutorial Chain step in wizard ─────────────────────────────────────────

def test_tutorial_chain_step_in_wizard():
    text = read_guide()
    assert "Tutorial Chain" in text, (
        "§8 wizard step list must include the Tutorial Chain selection step "
        "(added in F.8.c.1)"
    )


def test_force_sensitivity_not_a_wizard_step():
    text = read_guide()
    # The wizard step list should NOT list "Force Sensitivity" as a step
    import re
    wizard_section_match = re.search(
        r"## 8\. The Creation Wizard.*?(?=## \d)", text, re.DOTALL
    )
    if wizard_section_match:
        wizard_section = wizard_section_match.group(0)
        # Should not have a numbered step mentioning "Force Sensitivity"
        assert not re.search(r"\d+\.\s+\*\*Force Sensitivity\*\*", wizard_section), (
            "Force Sensitivity must not appear as a numbered wizard step "
            "(step was removed in PG.3.gates.b May 2026)"
        )


# ── O: Persistence section has content ───────────────────────────────────────

def test_persistence_section_has_content():
    text = read_guide()
    import re
    match = re.search(r"## 11\. Persistence.*?(?=---|\Z)", text, re.DOTALL)
    assert match is not None, "Section 11 not found"
    section = match.group(0)
    # Must be more than just a heading — must have actual paragraph content
    content_lines = [
        line for line in section.splitlines()
        if line.strip() and not line.startswith("#") and line.strip() != "---"
    ]
    assert len(content_lines) >= 3, (
        "§11 Persistence must have actual paragraph content (was an empty heading)"
    )
