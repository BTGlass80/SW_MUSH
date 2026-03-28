"""Tests for free-form character creation engine."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.creation import CreationEngine, TEMPLATES
from engine.species import SpeciesRegistry
from engine.character import SkillRegistry

DATA = os.path.join(os.path.dirname(__file__), "..", "data")


def make_engine():
    sp = SpeciesRegistry()
    sp.load_directory(os.path.join(DATA, "species"))
    sk = SkillRegistry()
    sk.load_file(os.path.join(DATA, "skills.yaml"))
    return CreationEngine(sp, sk)


class TestFreeFormCreation:
    def test_initial_display(self):
        e = make_engine()
        display, prompt = e.get_initial_display()
        assert "CHARACTER CREATION" in display
        assert "create>" in prompt

    def test_set_name(self):
        e = make_engine()
        d, p, done = e.process_input("name Han Solo")
        assert "Han Solo" in d
        assert e.state.name == "Han Solo"
        assert not done

    def test_set_attribute(self):
        e = make_engine()
        d, p, done = e.process_input("set dex 4D")
        assert "Dexterity" in d or "dexterity" in d.lower()
        assert e.state.attributes["dexterity"].dice == 4

    def test_set_attribute_prefix(self):
        e = make_engine()
        e.process_input("set str 3D+2")
        assert e.state.attributes["strength"].dice == 3
        assert e.state.attributes["strength"].pips == 2

    def test_attribute_enforces_min(self):
        e = make_engine()
        d, p, done = e.process_input("set dex 1D")
        assert "min" in d.lower()

    def test_attribute_enforces_max(self):
        e = make_engine()
        d, p, done = e.process_input("set dex 5D")
        assert "max" in d.lower()

    def test_skill_add(self):
        e = make_engine()
        d, p, done = e.process_input("skill blaster 2D+1")
        assert "blaster" in e.state.skills
        assert e.state.skills["blaster"].dice == 2

    def test_skill_partial_match(self):
        e = make_engine()
        d, p, done = e.process_input("skill starfighter pilot 2D")
        assert "starfighter piloting" in e.state.skills

    def test_unskill(self):
        e = make_engine()
        e.process_input("skill blaster 2D")
        assert "blaster" in e.state.skills
        e.process_input("unskill blaster")
        assert "blaster" not in e.state.skills

    def test_species_change(self):
        e = make_engine()
        e.process_input("set dex 3D")
        e.process_input("skill blaster 1D")
        d, p, done = e.process_input("species wookiee")
        assert e.state.species.name == "Wookiee"
        # Skills should be cleared
        assert len(e.state.skills) == 0
        # Attributes should be at wookiee minimums
        assert e.state.attributes["strength"].dice == 3

    def test_species_list(self):
        e = make_engine()
        d, p, done = e.process_input("species")
        assert "Human" in d
        assert "Wookiee" in d

    def test_info(self):
        e = make_engine()
        d, p, done = e.process_input("info wookiee")
        assert "Kashyyyk" in d

    def test_template_apply(self):
        e = make_engine()
        d, p, done = e.process_input("template smuggler")
        assert e.state.attributes["dexterity"].dice == 3
        assert "blaster" in e.state.skills

    def test_template_list(self):
        e = make_engine()
        d, p, done = e.process_input("template")
        assert "smuggler" in d.lower()
        assert "bounty" in d.lower()

    def test_undo(self):
        e = make_engine()
        e.process_input("set dex 4D")
        assert e.state.attributes["dexterity"].dice == 4
        e.process_input("undo")
        assert e.state.attributes["dexterity"].dice == 2  # back to human min

    def test_undo_empty(self):
        e = make_engine()
        d, p, done = e.process_input("undo")
        assert "Nothing" in d

    def test_sheet_display(self):
        e = make_engine()
        e.process_input("name Test")
        d, p, done = e.process_input("sheet")
        assert "DEXTERITY" in d or "Dexterity" in d

    def test_list_skills(self):
        e = make_engine()
        d, p, done = e.process_input("list dex")
        assert "Blaster" in d
        assert "Dodge" in d

    def test_done_validates_name(self):
        e = make_engine()
        d, p, done = e.process_input("done")
        assert not done
        assert "Name" in d

    def test_done_validates_attr_points(self):
        e = make_engine()
        e.process_input("name Test")
        d, p, done = e.process_input("done")
        assert not done
        assert "pips remaining" in d.lower() or "points" in d.lower()

    def test_full_creation(self):
        e = make_engine()
        e.process_input("name Han Solo")
        e.process_input("template smuggler")
        d, p, done = e.process_input("done")
        assert done
        char = e.get_character()
        assert char.name == "Han Solo"
        assert char.species_name == "Human"
        assert char.dexterity.dice == 3 and char.dexterity.pips == 1
        assert "blaster" in char.skills

    def test_edit_after_template(self):
        e = make_engine()
        e.process_input("template smuggler")
        e.process_input("set per 3D+2")
        assert e.state.attributes["perception"].dice == 3
        assert e.state.attributes["perception"].pips == 2

    def test_help(self):
        e = make_engine()
        d, p, done = e.process_input("help")
        assert "name" in d.lower()
        assert "set" in d.lower()
        assert "done" in d.lower()
