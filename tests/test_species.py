"""
Tests for species data loading and validation.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.dice import DicePool
from engine.species import SpeciesRegistry, Species, AttributeRange


SPECIES_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "species")


class TestSpeciesLoading:
    def setup_method(self):
        self.registry = SpeciesRegistry()
        self.registry.load_directory(SPECIES_DIR)

    def test_all_species_loaded(self):
        assert self.registry.count == 9

    def test_species_names(self):
        names = self.registry.list_names()
        assert "Human" in names
        assert "Wookiee" in names
        assert "Trandoshan" in names
        assert "Mon Calamari" in names

    def test_human_attributes(self):
        human = self.registry.get("human")
        assert human is not None
        assert human.name == "Human"
        for attr in ("dexterity", "knowledge", "mechanical",
                     "perception", "strength", "technical"):
            r = human.attributes[attr]
            assert r.min_pool.dice == 2 and r.min_pool.pips == 0
            assert r.max_pool.dice == 4 and r.max_pool.pips == 0

    def test_wookiee_strength(self):
        wookiee = self.registry.get("wookiee")
        assert wookiee is not None
        assert wookiee.attributes["strength"].min_pool.dice == 3
        assert wookiee.attributes["strength"].max_pool.dice == 6

    def test_wookiee_abilities(self):
        wookiee = self.registry.get("wookiee")
        ability_names = [a.name for a in wookiee.special_abilities]
        assert "Berserker Rage" in ability_names
        assert "Climbing Claws" in ability_names

    def test_mon_calamari_swim(self):
        mc = self.registry.get("mon calamari")
        assert mc is not None
        assert mc.swim == 12

    def test_duros_mechanical(self):
        duros = self.registry.get("duros")
        assert duros.attributes["mechanical"].min_pool == DicePool(2, 1)

    def test_case_insensitive_lookup(self):
        assert self.registry.get("HUMAN") is not None
        assert self.registry.get("wOoKiEe") is not None

    def test_missing_species(self):
        assert self.registry.get("ewok") is None


class TestAttributeValidation:
    def setup_method(self):
        self.registry = SpeciesRegistry()
        self.registry.load_directory(SPECIES_DIR)
        self.human = self.registry.get("human")

    def test_valid_allocation(self):
        """18D distributed evenly = 3D each, all within 2D-4D."""
        attrs = {
            "dexterity": DicePool(3, 0),
            "knowledge": DicePool(3, 0),
            "mechanical": DicePool(3, 0),
            "perception": DicePool(3, 0),
            "strength": DicePool(3, 0),
            "technical": DicePool(3, 0),
        }
        errors = self.human.validate_attributes(attrs)
        assert len(errors) == 0

    def test_valid_uneven_allocation(self):
        """18D split unevenly: 4D + 4D + 3D + 3D + 2D + 2D = 18D."""
        attrs = {
            "dexterity": DicePool(4, 0),
            "knowledge": DicePool(4, 0),
            "mechanical": DicePool(3, 0),
            "perception": DicePool(3, 0),
            "strength": DicePool(2, 0),
            "technical": DicePool(2, 0),
        }
        errors = self.human.validate_attributes(attrs)
        assert len(errors) == 0

    def test_below_minimum(self):
        attrs = {
            "dexterity": DicePool(1, 0),  # Below human min of 2D
            "knowledge": DicePool(2, 0),
            "mechanical": DicePool(2, 0),
            "perception": DicePool(2, 0),
            "strength": DicePool(2, 0),
            "technical": DicePool(2, 0),
        }
        errors = self.human.validate_attributes(attrs)
        assert any("below minimum" in e for e in errors)

    def test_above_maximum(self):
        attrs = {
            "dexterity": DicePool(5, 0),  # Above human max of 4D
            "knowledge": DicePool(2, 0),
            "mechanical": DicePool(2, 0),
            "perception": DicePool(2, 0),
            "strength": DicePool(2, 0),
            "technical": DicePool(2, 0),
        }
        errors = self.human.validate_attributes(attrs)
        assert any("exceeds maximum" in e for e in errors)

    def test_missing_attribute(self):
        attrs = {
            "dexterity": DicePool(2, 0),
            "knowledge": DicePool(2, 0),
        }
        errors = self.human.validate_attributes(attrs)
        assert any("Missing" in e for e in errors)


class TestSpeciesDisplay:
    def setup_method(self):
        self.registry = SpeciesRegistry()
        self.registry.load_directory(SPECIES_DIR)

    def test_display_contains_name(self):
        human = self.registry.get("human")
        display = human.format_display()
        assert "Human" in display

    def test_display_contains_homeworld(self):
        wookiee = self.registry.get("wookiee")
        display = wookiee.format_display()
        assert "Kashyyyk" in display

    def test_display_contains_abilities(self):
        trandoshan = self.registry.get("trandoshan")
        display = trandoshan.format_display()
        assert "Regeneration" in display
        assert "Claws" in display
