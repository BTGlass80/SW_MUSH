"""Guard: Guide_01 WEG D6 Core Mechanics is accurate to the live engine + data.

The Opus-owned guides quality pass. Guide_01 is the foundational rules guide —
the dice system every other guide references — so it makes a dense set of
*quantified* claims that must track HEAD exactly. This pass cross-checked all of
them and fixed four real drifts:

* **§2 said "75 skills"** — the loaded ``SkillRegistry`` carries **76** (the
  ``Powersuit Operation`` Mechanical skill was added 2026-06-13). Bumped to 76.
* **§2 ``+roll 4D+2`` example showed normal dice "3, 5, 2"** — ``roll_d6_pool``
  sorts the normal dice **descending** (``reverse=True``), so the engine never
  renders that order. Fixed to "5, 3, 2".
* **§10 taught "Clone Trooper Armor" (+1D/+2D/−1D Dex)** — there is no such
  registry row. Those exact stats are the real ``improved_armor`` ("Improved
  Body Armor"). Renamed the phantom to the real item.
* **§4 partial-success said "(missions, repairs, bounties) … by 4 or fewer"** —
  the window is system-specific: repairs use ``margin >= -4`` but missions use
  ``margin >= -2``, and bounties resolve via combat/capture (no margin window).
  Rewrote to the accurate per-system thresholds and dropped bounties.

Every other §3–§11 claim verified clean and is pinned below so a future engine
retune that desyncs the guide fails loudly here instead of silently misleading
new players.
"""
import os
import re

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_01_WEG_D6_Core_Mechanics.md")
WEAPONS_PATH = os.path.join(PROJECT_ROOT, "data", "weapons.yaml")
SKILLS_PATH = os.path.join(PROJECT_ROOT, "data", "skills.yaml")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def weapons():
    with open(WEAPONS_PATH, "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    # key the registry by exact display name (the 16 names the guide uses are
    # each unique exact strings in weapons.yaml).
    by_name = {}
    for key, row in data.items():
        by_name.setdefault(row["name"], []).append((key, row))
    return data, by_name


# ── §2: skill count tracks the loaded registry ───────────────────────────────

class TestSkillCount:
    def test_guide_claims_76(self, guide):
        assert "**76 skills**" in guide

    def test_registry_has_76(self):
        from engine.character import SkillRegistry
        reg = SkillRegistry()
        reg.load_file(SKILLS_PATH)
        assert len(reg.all_skills()) == 76

    def test_no_phantom_skill_names(self, guide):
        # Every skill the §1/§2 prose names must be a real registered skill.
        from engine.character import SkillRegistry, canonical_skill_key
        reg = SkillRegistry()
        reg.load_file(SKILLS_PATH)
        named = [
            "Blaster", "Dodge", "Melee Combat", "Brawling Parry", "Grenade",
            "Lightsaber", "Pick Pocket", "Running", "Streetwise", "Survival",
            "Languages", "Intimidation", "Tactics", "Willpower", "Alien Species",
            "Bureaucracy", "Space Transports", "Starfighter Piloting",
            "Astrogation", "Sensors", "Starship Gunnery", "Capital Ship Piloting",
            "Bargain", "Command", "Con", "Persuasion", "Search", "Sneak", "Hide",
            "Gambling", "Investigation", "Brawling", "Climbing/Jumping", "Lifting",
            "Stamina", "Swimming", "First Aid", "Computer Programming/Repair",
            "Space Transport Repair", "Security", "Demolitions", "Medicine",
        ]
        for name in named:
            assert name in guide, f"guide dropped skill mention {name!r}"
            assert reg.get(canonical_skill_key(name)) is not None, \
                f"phantom skill taught: {name!r}"


# ── §4: difficulty ladder == engine.dice.Difficulty ──────────────────────────

class TestDifficultyLadder:
    EXPECTED = {
        "Very Easy": 5, "Easy": 10, "Moderate": 15,
        "Difficult": 20, "Very Difficult": 25, "Heroic": 30,
    }

    def test_matches_engine_enum(self, guide):
        from engine.dice import Difficulty
        for name, value in self.EXPECTED.items():
            assert Difficulty.from_name(name).value == value
            # guide table renders "| Very Easy | 5 |" etc.
            assert re.search(rf"\|\s*{re.escape(name)}\s*\|\s*{value}\b", guide), \
                f"guide difficulty row drift: {name} {value}"


# ── §6: scale table == engine.dice.Scale ─────────────────────────────────────

class TestScaleTable:
    EXPECTED = {
        "Character": 0, "Speeder": 2, "Walker": 4, "Starfighter": 6,
        "Corvette": 9, "Capital": 12,
    }

    def test_matches_engine_enum(self, guide):
        from engine.dice import Scale
        for name, value in self.EXPECTED.items():
            assert Scale.from_name(name).value == value
            assert re.search(rf"\|\s*{re.escape(name)}\s*\|\s*{value}\b", guide), \
                f"guide scale row drift: {name} {value}"

    def test_death_star_scale_18(self, guide):
        from engine.dice import Scale
        assert Scale.DEATH_STAR.value == 18
        assert "18" in guide  # the disclaimed Death Star reference

    def test_char_vs_starfighter_diff_is_6(self):
        from engine.dice import Scale
        assert abs(Scale.difference(Scale.CHARACTER, Scale.STARFIGHTER)) == 6

    def test_scale_examples_are_clone_wars_era(self, guide):
        # §6 examples were partly GCW-flavored; the pass made Walker + Capital
        # match the already-CW Starfighter row.
        assert "AT-TE" in guide
        assert "Venator-class Star Destroyer" in guide
        assert "Acclamator" in guide
        # the GCW/Imperial walker examples are gone
        assert "AT-AT" not in guide
        assert "AT-ST" not in guide


# ── §10: weapon / armor stats == data/weapons.yaml ───────────────────────────

class TestWeaponStats:
    # (display name, weapons.yaml key, expected damage, expected cost)
    RANGED = [
        ("Hold-Out Blaster", "hold_out_blaster", "3D+1", 275),
        ("Blaster Pistol", "blaster_pistol", "4D", 500),
        ("Heavy Blaster Pistol", "heavy_blaster_pistol", "5D", 750),
        ("Blaster Rifle", "blaster_rifle", "5D", 1000),
        ("Sporting Blaster", "sporting_blaster", "3D+1", 300),
        ("Light Repeating Blaster", "light_repeating_blaster", "6D", 2000),
        ("Bowcaster", "bowcaster", "4D", 900),
    ]
    MELEE = [
        ("Knife", "knife", "STR+1D", 25),
        ("Vibroblade", "vibroblade", "STR+3D", 250),
        ("Vibroaxe", "vibroaxe", "STR+3D+1", 500),
        ("Force Pike", "force_pike", "STR+2D", 500),
    ]

    @pytest.mark.parametrize("name,key,dmg,cost", RANGED + MELEE)
    def test_weapon_matches_registry_and_guide(self, weapons, guide, name, key, dmg, cost):
        data, _ = weapons
        row = data[key]
        assert row["name"] == name
        assert row["damage"] == dmg, f"{key} damage drift"
        assert row["cost"] == cost, f"{key} cost drift"
        # guide table row carries the name, the damage, and the comma-cost
        assert name in guide
        assert dmg in guide
        assert f"{cost:,}" in guide, f"guide missing cost {cost:,} for {name}"

    def test_lightsaber_flat_5d_no_sale(self, weapons, guide):
        data, _ = weapons
        row = data["lightsaber"]
        assert row["name"] == "Lightsaber"
        assert row["damage"] == "5D"
        assert row["cost"] == 0  # unavailable for sale -> guide shows "—"
        assert "Lightsaber" in guide and "5D (flat)" in guide


class TestArmorStats:
    # (display name, key, energy, physical, has_dex_penalty)
    ARMOR = [
        ("Blast Vest", "blast_vest", "+1D", "+1D", False),
        ("Blast Helmet", "blast_helmet", "+1D", "+1D", False),
        ("Improved Body Armor", "improved_armor", "+1D", "+2D", True),
        ("Bounty Hunter Armor", "bounty_hunter_armor", "+2D", "+3D", True),
    ]

    @pytest.mark.parametrize("name,key,energy,physical,has_pen", ARMOR)
    def test_armor_matches_registry_and_guide(self, weapons, guide, name, key, energy, physical, has_pen):
        data, _ = weapons
        row = data[key]
        assert row["name"] == name
        assert row["protection_energy"] == energy, f"{key} energy drift"
        assert row["protection_physical"] == physical, f"{key} physical drift"
        assert bool(row.get("dexterity_penalty")) == has_pen, f"{key} dex-penalty drift"
        assert name in guide

    def test_clone_trooper_armor_phantom_removed(self, weapons, guide):
        # The pre-pass phantom must be gone from the guide AND absent from the
        # registry (proving the rename targeted a real row, not invention).
        data, by_name = weapons
        assert "Clone Trooper Armor" not in guide
        assert "Clone Trooper Armor" not in by_name
        assert "Improved Body Armor" in by_name  # the real replacement


# ── §4: partial-success thresholds are system-specific ───────────────────────

class TestPartialSuccess:
    def test_engine_thresholds(self):
        src = _read(os.path.join(PROJECT_ROOT, "engine", "skill_checks.py"))
        assert "margin >= -2" in src   # mission partial window
        assert "margin >= -4" in src   # repair partial window

    def test_guide_states_both_windows(self, guide):
        assert "by up to 4" in guide   # repairs
        assert "by up to 2" in guide   # missions
        # the inaccurate blanket bounty claim is gone
        assert "missions, repairs, bounties" not in guide


# ── §7: wound ladder + stun-KO == engine.character ───────────────────────────

class TestWoundAndStun:
    def test_wound_penalties(self):
        from engine.character import WoundLevel
        assert WoundLevel.WOUNDED.penalty_dice == 1        # -1D
        assert WoundLevel.WOUNDED_TWICE.penalty_dice == 2  # -2D
        assert WoundLevel.HEALTHY.penalty_dice == 0

    def test_can_act_ladder(self):
        from engine.character import WoundLevel
        assert WoundLevel.WOUNDED_TWICE.can_act is True
        assert WoundLevel.INCAPACITATED.can_act is False
        assert WoundLevel.MORTALLY_WOUNDED.can_act is False
        assert WoundLevel.DEAD.can_act is False

    def test_guide_lists_levels(self, guide):
        for level in ("Healthy", "Stunned", "Wounded", "Wounded Twice",
                      "Incapacitated", "Mortally Wounded", "Dead"):
            assert level in guide

    def test_stun_ko_threshold_is_strength_dice(self, guide):
        # engine gate: active stun count >= Strength dice -> incapacitated.
        src = _read(os.path.join(PROJECT_ROOT, "engine", "character.py"))
        assert "len(self.stun_timers) >= str_dice" in src
        assert "Strength dice" in guide
        assert "unconscious" in guide


# ── §2: dice-rolling commands resolve to the canonical keys ──────────────────

class TestCommands:
    def test_roll_and_check_keys(self):
        from parser.d6_commands import RollCommand, CheckCommand
        assert RollCommand.key == "+roll"
        assert RollCommand.aliases == []   # bare `roll` deleted by the rework
        assert CheckCommand.key == "+check"
        assert CheckCommand.aliases == []  # bare `check` deleted by the rework

    def test_guide_uses_canonical_forms(self, guide):
        assert "+roll" in guide
        assert "+check" in guide
        # the deleted bare forms must not be taught as commands
        assert "> roll " not in guide
        assert "> check " not in guide


# ── §11: the documented data-flow symbols all exist ──────────────────────────

class TestDataFlowSymbols:
    def test_dice_symbols(self):
        from engine.dice import difficulty_check, roll_d6_pool, roll_wild_die  # noqa: F401
        assert callable(difficulty_check)
        assert callable(roll_d6_pool)
        assert callable(roll_wild_die)

    def test_skill_check_symbols(self):
        from engine.skill_checks import perform_skill_check, _get_skill_pool  # noqa: F401
        assert callable(perform_skill_check)
        assert callable(_get_skill_pool)

    def test_character_symbols(self):
        from engine.character import SkillDef, WoundLevel  # noqa: F401
        assert SkillDef is not None and WoundLevel is not None

    def test_guide_references_real_paths(self, guide):
        for path in ("parser/d6_commands.py", "engine/dice.py",
                     "engine/skill_checks.py"):
            assert path in guide
        for sym in ("CheckCommand", "difficulty_check", "roll_d6_pool",
                    "roll_wild_die", "perform_skill_check", "_get_skill_pool",
                    "SkillDef"):
            assert sym in guide


# ── §1: chargen attribute rules == data/species ──────────────────────────────

class TestChargen:
    def test_human(self, guide):
        with open(os.path.join(PROJECT_ROOT, "data", "species", "human.yaml"),
                  "r", encoding="utf-8") as fh:
            human = yaml.safe_load(fh)
        assert human["attribute_dice"] == "18D"
        for attr in human["attributes"].values():
            assert attr["min"] == "2D" and attr["max"] == "4D"
        assert "18D" in guide
        assert "2D and 4D" in guide

    def test_wookiee(self, guide):
        with open(os.path.join(PROJECT_ROOT, "data", "species", "wookiee.yaml"),
                  "r", encoding="utf-8") as fh:
            wk = yaml.safe_load(fh)
        assert wk["attributes"]["strength"]["min"] == "3D"
        assert wk["attributes"]["strength"]["max"] == "6D"
        assert wk["attributes"]["knowledge"]["max"] == "2D+1"
        assert "3D to 6D" in guide
        assert "2D+1" in guide
