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


# ════════════════════════════════════════════════════════════════════════════
#  Authoritative quality pass (2026-06-23) — cross-check guide facts vs HEAD.
#
#  The block above (the F.7-era accuracy rework) pins the guide text against
#  itself. These guards go further: they pin the documented NUMBERS and STATS
#  to the live engine + data files, so a future engine/data change that drifts
#  away from Guide_02 fails loudly here instead of silently misinforming new
#  players. This is the "engine cross-check guard" pattern the other guide
#  authoritative passes established.
# ════════════════════════════════════════════════════════════════════════════

SPECIES_DIR = pathlib.Path("data/species")
SKILLS_YAML = pathlib.Path("data/skills.yaml")
TEMPLATES_YAML = pathlib.Path("data/worlds/clone_wars/chargen_templates.yaml")

_ATTR_ORDER = ["dexterity", "knowledge", "mechanical", "perception", "strength", "technical"]


def _load_species():
    import yaml
    out = {}
    for f in sorted(SPECIES_DIR.glob("*.yaml")):
        out[f.stem] = yaml.safe_load(f.read_text(encoding="utf-8"))
    return out


def test_nine_species_match_data():
    sp = _load_species()
    assert len(sp) == 9, f"Expected 9 species YAMLs in data/species/, found {len(sp)}"
    assert "Nine playable species" in read_guide(), (
        "§2 must say 'Nine playable species' to match data/species/ (9 files)"
    )


def test_seventy_six_skills_match_data():
    import yaml
    data = yaml.safe_load(SKILLS_YAML.read_text(encoding="utf-8"))
    count = sum(len(v) for v in data.values() if isinstance(v, list))
    assert count == 76, f"Expected 76 skills in data/skills.yaml, found {count}"
    text = read_guide()
    assert "76 skills" in text, "§4 must say '76 skills' to match data/skills.yaml"


def test_starting_defaults_match_character():
    from engine.character import Character
    c = Character()
    assert c.force_points == 1, "New char must start with 1 Force Point"
    assert c.character_points == 5, "New char must start with 5 CP"
    assert c.credits == 1000, "New char must start with 1000 credits"
    text = read_guide()
    assert "1 Force Point" in text, "§7/§6 must document 1 starting Force Point"
    assert "1,000 credits" in text, "§7 must document 1,000 starting credits"
    assert "CP: 5" in text, "§10 sheet example must show CP: 5"


def test_skill_creation_cap_is_2d():
    from engine.chargen_validator import MAX_SKILL_BONUS_PIPS
    assert MAX_SKILL_BONUS_PIPS == 6, "2D creation cap == 6 pips"
    text = read_guide()
    assert "2D cap" in text and "+2D" in text, (
        "§4 must document the WEG R&E +2D-per-skill creation cap"
    )


def test_attribute_and_skill_budgets_documented():
    text = read_guide()
    # 18D attributes (54 pips), 7D skills (21 pips) — WEG R&E baseline that the
    # CreationEngine enforces (engine/creation.py _attr_pips_total/_skill_pips_total).
    assert "18D" in text and "54 pips" in text, "§3 must document 18D / 54 pips of attributes"
    assert "7D" in text and "21 pips" in text, "§4 must document 7D / 21 pips of skills"


def test_village_force_seed_is_1d():
    from engine.village_choice import _FORCE_SEED_DICE, _FORCE_ATTRS
    assert _FORCE_SEED_DICE == "1D", "Village trials seed 1D in each Force discipline"
    assert set(_FORCE_ATTRS) == {"control", "sense", "alter"}
    assert "1D in each of the three Force disciplines" in read_guide(), (
        "§6 must document the 1D Control/Sense/Alter Force seed"
    )


def test_section1_does_not_relist_force_as_a_chargen_step():
    import re
    text = read_guide()
    overview = re.search(r"## 1\. Overview.*?(?=## 2)", text, re.DOTALL)
    assert overview is not None, "§1 Overview not found"
    assert "declare Force sensitivity" not in overview.group(0), (
        "§1 must not list 'declare Force sensitivity' as a chargen step — "
        "STEP_FORCE was removed in PG.3.gates.b; §6 is the authority"
    )


def _guide_template_rows():
    """Return {row-name: [name, DEX, KNO, MEC, PER, STR, TEC, skills]} for the
    §5 template table rows (bolded archetype rows only)."""
    rows = {}
    for line in read_guide().splitlines():
        if line.startswith("| **") and "Key Skills" not in line:
            cols = [c.strip() for c in line.strip().strip("|").split("|")]
            rows[cols[0].strip("* ")] = cols
    return rows


def test_template_attributes_match_yaml():
    """Pin every §5 template attribute column to chargen_templates.yaml."""
    import yaml
    tmpls = yaml.safe_load(TEMPLATES_YAML.read_text(encoding="utf-8"))["templates"]
    label_to_key = {v["label"]: k for k, v in tmpls.items()}
    rows = _guide_template_rows()
    checked = 0
    for label, cols in rows.items():
        if label not in label_to_key:
            continue  # species-table row, not a template
        attrs = tmpls[label_to_key[label]]["attributes"]
        for i, a in enumerate(_ATTR_ORDER):
            assert cols[1 + i] == attrs[a], (
                f"{label} {a}: guide={cols[1 + i]!r} vs yaml={attrs[a]!r}"
            )
        checked += 1
    assert checked == 9, f"Expected to cross-check 9 templates, checked {checked}"


def test_duros_sullustan_ability_mechanics_match_yaml():
    """The tightened §2 ability text must reflect the real species YAML mechanics."""
    sp = _load_species()
    text = read_guide()
    duros = {a["name"]: a["description"] for a in sp["duros"]["special_abilities"]}
    assert "Astrogation" in duros["Natural Pilots"]
    assert "+1D to Astrogation" in text, "§2 Duros ability must cite +1D Astrogation"
    sull = {a["name"]: a["description"] for a in sp["sullustan"]["special_abilities"]}
    assert "Perception" in sull["Enhanced Senses"]
    assert "+1D to Perception" in text, "§2 Sullustan ability must cite +1D Perception"


def test_extreme_species_ranges_match_yaml():
    """Spot-check the §2 species table extremes against data/species/."""
    import re
    sp = _load_species()
    text = read_guide()
    # Wookiee Strength 3D–6D
    w = sp["wookiee"]["attributes"]["strength"]
    assert w["min"] == "3D" and w["max"] == "6D"
    wook_row = next(l for l in text.splitlines() if l.startswith("| **Wookiee**"))
    assert re.search(r"3D[–-]6D", wook_row), f"Wookiee STR 3D–6D missing: {wook_row!r}"
    # Bothan Perception max 4D+2
    b = sp["bothan"]["attributes"]["perception"]
    assert b["max"] == "4D+2"
    both_row = next(l for l in text.splitlines() if l.startswith("| **Bothan**"))
    assert "4D+2" in both_row, f"Bothan PER 4D+2 missing: {both_row!r}"
