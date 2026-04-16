"""
Tests for Character model, skill resolution, wound tracking, serialization.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.dice import DicePool
from engine.character import (
    Character, WoundLevel, SkillRegistry, ATTRIBUTE_NAMES,
)

SKILLS_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "skills.yaml")


def make_registry():
    reg = SkillRegistry()
    reg.load_file(SKILLS_PATH)
    return reg


def make_char():
    c = Character(name="Han Solo", species_name="Human")
    c.dexterity = DicePool(4, 0)
    c.knowledge = DicePool(3, 0)
    c.mechanical = DicePool(4, 1)
    c.perception = DicePool(3, 2)
    c.strength = DicePool(3, 0)
    c.technical = DicePool(3, 1)
    c.add_skill("blaster", DicePool(2, 1))
    c.add_skill("dodge", DicePool(1, 0))
    c.add_skill("starship gunnery", DicePool(1, 2))
    c.add_skill("space transports", DicePool(2, 0))
    c.add_skill("streetwise", DicePool(2, 0))
    c.add_skill("bargain", DicePool(1, 1))
    c.add_skill("con", DicePool(2, 0))
    c.add_skill("starfighter repair", DicePool(1, 0))
    return c


class TestSkillRegistry:
    def test_load(self):
        reg = make_registry()
        assert reg.count > 70

    def test_lookup(self):
        reg = make_registry()
        sd = reg.get("blaster")
        assert sd is not None
        assert sd.attribute == "dexterity"

    def test_case_insensitive(self):
        reg = make_registry()
        assert reg.get("DODGE") is not None
        assert reg.get("First Aid") is not None

    def test_attribute_mapping(self):
        reg = make_registry()
        assert reg.get_attribute_for("astrogation") == "mechanical"
        assert reg.get_attribute_for("brawling") == "strength"
        assert reg.get_attribute_for("security") == "technical"

    def test_skills_for_attribute(self):
        reg = make_registry()
        dex_skills = reg.skills_for_attribute("dexterity")
        names = [s.name for s in dex_skills]
        assert "Blaster" in names
        assert "Dodge" in names
        assert "Lightsaber" in names

    def test_specializations(self):
        reg = make_registry()
        sd = reg.get("blaster")
        assert "Heavy Blaster Pistol" in sd.specializations


class TestCharacterSkills:
    def test_trained_skill(self):
        reg = make_registry()
        c = make_char()
        pool = c.get_skill_pool("blaster", reg)
        # dexterity 4D + blaster bonus 2D+1 = 6D+1
        assert pool.dice == 6 and pool.pips == 1

    def test_untrained_skill(self):
        reg = make_registry()
        c = make_char()
        pool = c.get_skill_pool("lightsaber", reg)
        # No skill bonus, falls back to dexterity 4D
        assert pool.dice == 4 and pool.pips == 0

    def test_different_attribute(self):
        reg = make_registry()
        c = make_char()
        pool = c.get_skill_pool("space transports", reg)
        # mechanical 4D+1 + bonus 2D = 6D+1
        assert pool.dice == 6 and pool.pips == 1

    def test_effective_pool_with_wounds(self):
        reg = make_registry()
        c = make_char()
        c.wound_level = WoundLevel.WOUNDED  # -1D
        pool = c.get_effective_pool("blaster", reg)
        # 6D+1 - 1D = 5D+1
        assert pool.dice == 5 and pool.pips == 1

    def test_effective_pool_multi_action(self):
        reg = make_registry()
        c = make_char()
        pool = c.get_effective_pool("blaster", reg, num_actions=3)
        # 6D+1 - 2D (3 actions) = 4D+1
        assert pool.dice == 4 and pool.pips == 1

    def test_effective_pool_wounds_plus_multi(self):
        reg = make_registry()
        c = make_char()
        c.wound_level = WoundLevel.WOUNDED  # -1D
        pool = c.get_effective_pool("blaster", reg, num_actions=2)
        # 6D+1 - 1D wound - 1D multi = 4D+1
        assert pool.dice == 4 and pool.pips == 1


class TestWoundLevel:
    def test_from_margin_healthy(self):
        assert WoundLevel.from_damage_margin(0) == WoundLevel.HEALTHY
        assert WoundLevel.from_damage_margin(-5) == WoundLevel.HEALTHY

    def test_from_margin_stunned(self):
        assert WoundLevel.from_damage_margin(1) == WoundLevel.STUNNED
        assert WoundLevel.from_damage_margin(3) == WoundLevel.STUNNED

    def test_from_margin_wounded(self):
        assert WoundLevel.from_damage_margin(4) == WoundLevel.WOUNDED
        assert WoundLevel.from_damage_margin(8) == WoundLevel.WOUNDED

    def test_from_margin_incapacitated(self):
        assert WoundLevel.from_damage_margin(9) == WoundLevel.INCAPACITATED

    def test_from_margin_mortal(self):
        assert WoundLevel.from_damage_margin(13) == WoundLevel.MORTALLY_WOUNDED

    def test_from_margin_dead(self):
        assert WoundLevel.from_damage_margin(16) == WoundLevel.DEAD

    def test_stacking_wounds(self):
        """R&E p59: Wounded + Wounded = Incapacitated."""
        c = Character(name="Test")
        c.apply_wound(5)  # Wounded
        assert c.wound_level == WoundLevel.WOUNDED
        c.apply_wound(5)  # Wounded again -> Incapacitated per R&E
        assert c.wound_level == WoundLevel.INCAPACITATED

    def test_incap_plus_wound(self):
        """R&E p59: Incapacitated + Wounded = Mortally Wounded."""
        c = Character(name="Test")
        c.wound_level = WoundLevel.INCAPACITATED
        c.apply_wound(5)  # Wounded on top of Incap
        assert c.wound_level == WoundLevel.MORTALLY_WOUNDED

    def test_mortally_wounded_plus_wound(self):
        """R&E p59: Mortally Wounded + any wound = Dead."""
        c = Character(name="Test")
        c.wound_level = WoundLevel.MORTALLY_WOUNDED
        c.apply_wound(5)
        assert c.wound_level == WoundLevel.DEAD

    def test_stun_accumulation(self):
        """R&E p59: Stuns >= STR dice = knocked unconscious."""
        c = Character(name="Test")
        c.strength = DicePool(3, 0)  # 3D STR
        c.apply_wound(2)  # Stun 1
        c.apply_wound(2)  # Stun 2
        assert c.wound_level == WoundLevel.STUNNED
        assert c.active_stun_count == 2
        c.apply_wound(2)  # Stun 3 = STR dice -> unconscious (Incapacitated)
        assert c.wound_level == WoundLevel.INCAPACITATED
        assert c.active_stun_count == 3

    def test_escalating_wound(self):
        c = Character(name="Test")
        c.apply_wound(5)   # Wounded
        c.apply_wound(10)  # Incapacitated (higher severity replaces)
        assert c.wound_level == WoundLevel.INCAPACITATED

    def test_can_act(self):
        assert WoundLevel.HEALTHY.can_act is True
        assert WoundLevel.WOUNDED.can_act is True
        assert WoundLevel.WOUNDED_TWICE.can_act is True
        assert WoundLevel.INCAPACITATED.can_act is False
        assert WoundLevel.DEAD.can_act is False


class TestSerialization:
    def test_roundtrip(self):
        c = make_char()
        c.character_points = 12
        c.wound_level = WoundLevel.WOUNDED
        db_dict = c.to_db_dict()

        c2 = Character.from_db_dict({
            "id": 1, "account_id": 1,
            **db_dict,
        })

        assert c2.name == "Han Solo"
        assert c2.species_name == "Human"
        assert c2.dexterity.dice == 4
        assert c2.mechanical.pips == 1
        assert c2.character_points == 12
        assert c2.wound_level == WoundLevel.WOUNDED

        # Skills preserved
        assert "blaster" in c2.skills
        assert c2.skills["blaster"].dice == 2
        assert c2.skills["blaster"].pips == 1

    def test_force_sensitive_roundtrip(self):
        c = Character(name="Luke", force_sensitive=True)
        c.control = DicePool(3, 1)
        c.sense = DicePool(2, 2)
        c.alter = DicePool(1, 0)
        db_dict = c.to_db_dict()

        c2 = Character.from_db_dict({"id": 2, **db_dict})
        assert c2.force_sensitive is True
        assert c2.control.dice == 3 and c2.control.pips == 1
        assert c2.sense.dice == 2 and c2.sense.pips == 2


class TestCharacterSheet:
    def test_sheet_contains_name(self):
        reg = make_registry()
        c = make_char()
        sheet = c.format_sheet(reg)
        assert "Han Solo" in sheet

    def test_sheet_contains_skills(self):
        reg = make_registry()
        c = make_char()
        sheet = c.format_sheet(reg)
        assert "Blaster" in sheet
        assert "6D+1" in sheet  # blaster total

    def test_sheet_contains_attributes(self):
        reg = make_registry()
        c = make_char()
        sheet = c.format_sheet(reg)
        assert "DEXTERITY" in sheet
        assert "4D" in sheet
