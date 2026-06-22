"""tests/test_guide_24_encounters_hazards_authoritative.py

Authoritative Opus quality-pass guard for Guide_24_Encounters_Hazards.md.
Complements the Sonnet-draft guard ``test_guide_05_24_rework.py`` (era
fixes); this file pins the corrections the authoritative pass made against
HEAD and cross-checks the guide's quoted numbers against the live engine
constants so a future balance change that moves a constant forces the
guide to move with it.

Drift this pass corrected (verified against engine/hazards.py,
engine/buffs.py, engine/space_encounters.py, engine/encounter_pirate.py,
engine/space_anomalies.py, parser/space_commands.py and
data/schematics.yaml at HEAD):
  - Radiation tests at base difficulty 15 (Difficult) — the guide said
    "varies"/"10+".
  - Radiation applies the *Toxic Exposure* debuff (buff_type
    "toxic_exposure"), NOT a phantom "Radiation Sickness".
  - Urban danger HAS a mitigation item (anti_theft_alarm, single-use) —
    the guide said "none".
  - Urban-danger theft is 5% of credits capped at severity*100 cr, not a
    flat "10-50 cr".
  - Dehydration is -1 pip to BOTH Strength and Dexterity per stack,
    max 3 (→ -1D STR / -1D DEX at full) — the guide said "-1D STR" and a
    scenario said "-3D Strength".
  - Mitigation gear durability: water_canteen / cooling_unit / breath_mask
    are durable (max_uses 0); radiation_suit (10) and anti_theft_alarm (1)
    are consumable — the guide said items "don't consume on use".
  - cooling_unit is taught by Vek Nurren, not "Venn Kator".
  - Hazard debuffs persist (no cure path); gear prevents new checks rather
    than curing existing stacks.
  - Pirate negotiate reduces tribute to 1/2 the demand (1/4 on a critical),
    not "1/3".
  - Space anomalies are engaged via scan/deepscan + `salvage` (derelicts);
    the phantom `investigate <anomaly_id>` (a wilderness verb) was removed.
"""

import pathlib
import re

import yaml

GUIDE_PATH = pathlib.Path("data/guides/Guide_24_Encounters_Hazards.md")
SCHEMATICS_PATH = pathlib.Path("data/schematics.yaml")


def read_guide():
    return GUIDE_PATH.read_text(encoding="utf-8")


def _schematic(key):
    data = yaml.safe_load(SCHEMATICS_PATH.read_text(encoding="utf-8"))
    for entry in data.get("schematics", []):
        if entry.get("key") == key:
            return entry
    raise AssertionError(f"schematic {key!r} not found in data/schematics.yaml")


# ── Hazard cross-checks against engine/hazards.py + engine/buffs.py ──────

def test_radiation_difficulty_matches_engine():
    from engine.hazards import HAZARD_TYPES
    assert HAZARD_TYPES["radiation"]["base_difficulty"] == 15, (
        "Engine moved radiation base_difficulty; update the guide."
    )
    text = read_guide()
    # Guide must quote 15 / Difficult for radiation, never the old "10+".
    assert "Stamina vs. 15" in text and "Stamina vs. 10+" not in text, (
        "Guide must state radiation is Stamina vs. 15 (Difficult), not 10+."
    )


def test_radiation_uses_toxic_exposure_not_phantom_sickness():
    from engine.hazards import HAZARD_TYPES
    assert HAZARD_TYPES["radiation"]["buff_type"] == "toxic_exposure"
    text = read_guide()
    assert "Radiation Sickness" not in text, (
        "Phantom debuff: radiation applies Toxic Exposure, not 'Radiation "
        "Sickness'."
    )


def test_urban_danger_has_anti_theft_alarm_mitigation():
    from engine.hazards import HAZARD_TYPES
    assert HAZARD_TYPES["urban_danger"]["mitigation_items"] == ["anti_theft_alarm"]
    text = read_guide().lower()
    assert "anti-theft alarm" in text, (
        "Urban danger HAS a mitigation item (anti_theft_alarm); the guide "
        "must document it, not claim 'none'."
    )


def test_urban_danger_theft_is_percentage_not_flat_range():
    text = read_guide()
    assert "10-50 cr" not in text, "Old flat theft range must be gone."
    assert "5% of" in text and "severity" in text.lower(), (
        "Theft is 5% of credits capped at severity*100 cr — document the "
        "real formula."
    )


def test_dehydration_modifiers_match_engine():
    from engine.buffs import BUFF_TEMPLATES
    dehy = BUFF_TEMPLATES["dehydration"]
    assert dehy["stat_modifiers"] == {"strength": -1, "dexterity": -1}
    assert dehy["max_stacks"] == 3
    text = read_guide()
    # The guide must mention both STR and DEX for dehydration and never the
    # old "-3D Strength" scenario value.
    assert "−3D" not in text and "-3D Strength" not in text, (
        "Dehydration at 3 stacks is -1D STR / -1D DEX (3 pips), not -3D."
    )
    assert "Dexterity" in text, (
        "Dehydration also reduces Dexterity — the guide must say so."
    )


def test_toxic_exposure_is_single_stack_minus_1d_str():
    from engine.buffs import BUFF_TEMPLATES
    tox = BUFF_TEMPLATES["toxic_exposure"]
    assert tox["stat_modifiers"] == {"strength": -3}
    assert tox["max_stacks"] == 1


def test_hazard_check_interval_is_five_minutes():
    from engine.hazards import HAZARD_CHECK_INTERVAL
    assert HAZARD_CHECK_INTERVAL == 300
    assert "5 minutes" in read_guide()


def test_mitigation_durability_matches_schematics():
    # Durable gear: max_uses == 0
    for key in ("water_canteen", "cooling_unit", "breath_mask"):
        assert int(_schematic(key).get("max_uses", 0)) == 0, (
            f"{key} is documented as durable; schematic says otherwise."
        )
    # Consumable gear
    assert int(_schematic("radiation_suit")["max_uses"]) == 10
    assert int(_schematic("anti_theft_alarm")["max_uses"]) == 1
    text = read_guide()
    assert "don't consume on use" not in text, (
        "Stale claim: radiation suit / anti-theft alarm DO consume uses."
    )
    assert "Consumable" in text and "Durable" in text, (
        "Mitigation table must distinguish durable vs consumable gear."
    )


def test_cooling_unit_crafter_is_vek_nurren_not_venn_kator():
    assert _schematic("cooling_unit")["trainer_npc"] == "Vek Nurren"
    text = read_guide()
    assert "Venn Kator" not in text, (
        "cooling_unit is taught by Vek Nurren; 'Venn Kator' is a wrong "
        "crafter attribution."
    )
    assert "Vek Nurren" in text


def test_prevention_not_cure_documented():
    text = read_guide().lower()
    assert "prevents" in text and "does not cure" in text, (
        "Hazard debuffs persist (duration 0, no remove_buff caller); the "
        "guide must state mitigation prevents rather than cures."
    )


# ── Encounter cross-checks against engine/space_encounters.py ────────────

def test_encounter_cooldowns_match_engine():
    from engine.space_encounters import (
        ENCOUNTER_COOLDOWNS, ENCOUNTER_COOLDOWN_ANY,
        MAX_ACTIVE_ENCOUNTERS_PER_ZONE, DEFAULT_CHOICE_DEADLINE,
    )
    assert ENCOUNTER_COOLDOWNS["patrol"] == 600
    assert ENCOUNTER_COOLDOWNS["pirate"] == 900
    assert ENCOUNTER_COOLDOWNS["hunter"] == 1800
    assert ENCOUNTER_COOLDOWN_ANY == 180
    assert MAX_ACTIVE_ENCOUNTERS_PER_ZONE == 1
    assert DEFAULT_CHOICE_DEADLINE == 60


def test_pirate_demand_range_and_reduction():
    from engine.encounter_pirate import DEMAND_MIN, DEMAND_MAX
    assert (DEMAND_MIN, DEMAND_MAX) == (500, 3000)
    # The reduction is 1/2 (success) / 1/4 (critical), never 1/3.
    src = pathlib.Path("engine/encounter_pirate.py").read_text(encoding="utf-8")
    assert "demand // 2" in src and "demand // 4" in src
    assert "demand // 3" not in src
    text = read_guide()
    assert "1/3 the demand" not in text, "Old (wrong) 1/3 reduction must be gone."
    assert "half" in text.lower() and "quarter" in text.lower()


# ── Anomaly cross-checks against engine/space_anomalies.py + parser ──────

def test_seven_anomaly_types_present():
    from engine.space_anomalies import ANOMALY_TYPES
    assert len(ANOMALY_TYPES) == 7
    keys = {t[1] for t in ANOMALY_TYPES}
    assert keys == {
        "derelict", "distress", "cache", "pirates",
        "mineral_vein", "imperial", "mynock",
    }


def test_dead_drop_decode_is_slicing_difficult_20():
    src = pathlib.Path("engine/space_anomalies.py").read_text(encoding="utf-8")
    assert "Slicing check (Difficult, diff 20)" in src
    text = read_guide()
    assert "Slicing check (Difficult, diff 20)" in text
    # Era overlay → players see "Republic patrol", never "Imperial patrol".
    assert "Imperial patrol" not in text


def test_no_phantom_anomaly_investigate_command():
    text = read_guide()
    # `investigate <anomaly_id>` is a wilderness verb, not a space command;
    # `course anomaly <id>` is the engine's own (unwired) readout hint.
    assert "investigate <anomaly_id>" not in text, (
        "Phantom command: space anomalies are not engaged via "
        "`investigate <anomaly_id>`."
    )
    assert "course anomaly" not in text
    # The live anomaly loop (scan/deepscan/salvage) must be present.
    assert "salvage" in text and "deepscan" in text


def test_salvage_is_the_wired_derelict_engagement():
    """Cross-check that salvage really targets derelict anomalies."""
    src = pathlib.Path("parser/space_commands.py").read_text(encoding="utf-8")
    assert 'a.anomaly_type == "derelict"' in src


# ── Era cleanness ────────────────────────────────────────────────────────

_ERA_RE = [re.compile(p) for p in (
    r"\bImperial(?! Sourcebook)\b",
    r"\bGalactic Empire\b",
    r"\bRebel Alliance\b",
    r"\bGalactic Civil War\b",
    r"\bGCW\b",
)]


def test_era_clean():
    viols = []
    for i, line in enumerate(read_guide().split("\n"), start=1):
        for pat in _ERA_RE:
            if pat.search(line):
                viols.append((i, line.strip()))
    assert not viols, "Guide_24 era violations:\n" + "\n".join(
        f"  line {n}: {t!r}" for n, t in viols
    )
