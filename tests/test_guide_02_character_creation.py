"""Guard: Guide_02 Character Creation is accurate to the live chargen engine + data.

The Opus-owned guides quality pass over the most newcomer-facing guide (every
player builds a character before anything else). Cross-checked every quantified
claim against the live species registry (``data/species/*``), the chargen
template corpus (``data/worlds/clone_wars/chargen_templates.yaml``), the skill
registry, ``engine/creation.py`` / ``engine/creation_wizard.py``, and the
``Character`` starting defaults. Fixed six real, test-invisible drifts:

* **§2 Mon Calamari Move was 10** — the live species carries Move **9**. Every
  other species' Move in the table is correct; only Mon Cal was wrong.
* **§4 "75 skills" (×2)** — the loaded ``SkillRegistry`` carries **76** (same
  drift Guide_01 fixed; ``Powersuit Operation`` added 2026-06-13). Bumped to 76.
* **§3 attribute-abbreviation example** claimed ``s`` is ambiguous ("Strength or
  Sense") and that the matcher errors on ambiguity — but the six base attributes
  each begin with a *different* letter (``_match_attribute`` returns the first
  prefix hit, no ambiguity path), and Sense is a Force skill, not a chargen
  attribute. Rewrote to the real behaviour.
* **§6 "raises your Force Points to 2"** — the live Village/Jedi unlock
  (``engine/village_choice._seed_force_attributes``) seeds 1D Control/Sense/Alter
  (which is what *derives* ``force_sensitive``) but **never writes
  ``force_points``** — FP stays 1. Removed the phantom FP bump and aligned the
  advancement path to the Master–Padawan ``+teach`` bond (per Guide_08).
* **§8 tutorial step labelled "(first character only)"** — the step renders for
  *every* CW character; it is merely *mandatory* for the first character and
  skippable (``next``) for alts. Relabelled.
* **§5 species-switch "resets attributes to minimums"** — ``_cmd_species`` also
  **clears all skills**. Documented the skills-clear.

Plus an Opus completeness pass: added the two special abilities the bullet list
omitted (Trandoshan Vision, Mon Calamari Moist Environment), the +1D Claws / heal
specifics, and the explicit WEG R&E +2D-per-skill creation cap.

Every claim below is cross-checked against HEAD so a future retune that desyncs
the guide fails loudly here instead of silently misleading a new player.

NOTE (engine follow-up, NOT done in this docs pass): WEG R&E says a
Force-sensitive character starts with 2 Force Points, and the retired chargen
Force step honoured that. The PG.3.gates redesign moved Force unlock to the
Village trials but did not carry the FP→2 bump into
``village_choice._seed_force_attributes``. Whether the Village unlock *should*
grant a second FP is a design call (avoid silently editing the engine in a guide
pass); the guide now documents the live behaviour (FP stays 1).
"""
import os
import re

import pytest
import yaml

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides",
                          "Guide_02_Character_Creation.md")
SPECIES_DIR = os.path.join(PROJECT_ROOT, "data", "species")
SKILLS_PATH = os.path.join(PROJECT_ROOT, "data", "skills.yaml")
TEMPLATES_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars",
                              "chargen_templates.yaml")
CREATION_SRC = os.path.join(PROJECT_ROOT, "engine", "creation.py")
WIZARD_SRC = os.path.join(PROJECT_ROOT, "engine", "creation_wizard.py")
GAME_SERVER_SRC = os.path.join(PROJECT_ROOT, "server", "game_server.py")

ATTRS = ("dexterity", "knowledge", "mechanical", "perception",
         "strength", "technical")


def _read(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture(scope="module")
def guide():
    return _read(GUIDE_PATH)


@pytest.fixture(scope="module")
def species_reg():
    from engine.species import SpeciesRegistry
    reg = SpeciesRegistry()
    reg.load_directory(SPECIES_DIR)
    return reg


@pytest.fixture(scope="module")
def skill_reg():
    from engine.character import SkillRegistry
    reg = SkillRegistry()
    reg.load_file(SKILLS_PATH)
    return reg


@pytest.fixture(scope="module")
def templates():
    with open(TEMPLATES_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["templates"]


# ── §2: species table ────────────────────────────────────────────────────────

def _parse_species_table_moves(guide_text):
    """Return {species_name: move_int} parsed from the §2 markdown table."""
    moves = {}
    for line in guide_text.splitlines():
        m = re.match(r"\|\s*\*\*(.+?)\*\*\s*\|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.split("|")]
        # cells: ['', '**Name**', 'Homeworld', dex, kno, mec, per, str, tec, move, abilities, '']
        if len(cells) < 11:
            continue
        move_cell = cells[9]
        if not move_cell.isdigit():
            continue
        moves[m.group(1).strip()] = int(move_cell)
    return moves


class TestSpeciesTable:
    GUIDE_TO_REG = {
        "Human": "Human", "Bothan": "Bothan", "Duros": "Duros",
        "Mon Calamari": "Mon Calamari", "Rodian": "Rodian",
        "Sullustan": "Sullustan", "Trandoshan": "Trandoshan",
        "Twi'lek": "Twi'lek", "Wookiee": "Wookiee",
    }

    def test_nine_species(self, species_reg):
        assert species_reg.count == 9

    def test_guide_lists_all_nine(self, guide):
        moves = _parse_species_table_moves(guide)
        assert set(moves) == set(self.GUIDE_TO_REG)

    def test_every_move_matches_registry(self, guide, species_reg):
        """Every species' Move in the table == the live species Move."""
        moves = _parse_species_table_moves(guide)
        for gname, rname in self.GUIDE_TO_REG.items():
            sp = species_reg.get(rname)
            assert sp is not None, rname
            assert moves[gname] == sp.move, (
                f"{gname}: guide Move {moves[gname]} != registry {sp.move}")

    def test_mon_calamari_move_is_9(self, guide, species_reg):
        # The specific drift this pass fixed — pin it both ways.
        assert species_reg.get("Mon Calamari").move == 9
        assert "| 9 | Amphibious, Moist Environment |" in guide
        assert "| 10 | Amphibious, Moist Environment |" not in guide

    def test_attribute_ranges_match(self, guide, species_reg):
        """Spot-check the load-bearing extreme ranges named in §2 prose."""
        wk = species_reg.get("Wookiee")
        assert str(wk.attributes["strength"].min_pool) == "3D"
        assert str(wk.attributes["strength"].max_pool) == "6D"
        assert str(wk.attributes["knowledge"].max_pool) == "2D+1"
        assert str(wk.attributes["perception"].max_pool) == "2D+1"
        bo = species_reg.get("Bothan")
        assert str(bo.attributes["perception"].max_pool) == "4D+2"
        assert str(bo.attributes["strength"].max_pool) == "2D+2"


class TestSpecialAbilities:
    def test_documented_abilities_are_real(self, guide, species_reg):
        """Every species ability the bullet list names exists in the registry."""
        live = {ab.name for sp in species_reg.list_all()
                for ab in sp.special_abilities}
        # the two this pass added were previously missing from the bullets
        assert "Vision" in live
        assert "Moist Environment" in live
        for name in ("Berserker Rage", "Climbing Claws", "Regeneration",
                     "Claws", "Vision", "Natural Pilots", "Amphibious",
                     "Moist Environment", "Direction Sense", "Enhanced Senses",
                     "Lekku Communication"):
            assert name in live, name

    def test_guide_documents_new_abilities(self, guide):
        assert "Trandoshan Vision" in guide
        assert "Mon Calamari Moist Environment" in guide


# ── §3/§4: budgets, abbreviations, skill count, 2D cap ───────────────────────

class TestBudgets:
    def _engine(self, species_reg, skill_reg):
        from engine.creation import CreationEngine
        return CreationEngine(species_reg, skill_reg)

    def test_attribute_budget_18D(self, guide, species_reg, skill_reg):
        eng = self._engine(species_reg, skill_reg)
        assert eng._attr_pips_total() == 54  # 18D
        assert "**18D**" in guide

    def test_skill_budget_7D(self, guide, species_reg, skill_reg):
        eng = self._engine(species_reg, skill_reg)
        assert eng._skill_pips_total() == 21  # 7D
        assert "**7D**" in guide

    def test_single_letter_abbreviations_unambiguous(self, species_reg, skill_reg):
        """Each base attribute has a unique initial — the §3 claim."""
        eng = self._engine(species_reg, skill_reg)
        for letter, attr in (("d", "dexterity"), ("k", "knowledge"),
                             ("m", "mechanical"), ("p", "perception"),
                             ("s", "strength"), ("t", "technical")):
            assert eng._match_attribute(letter) == attr, letter
        initials = [a[0] for a in ATTRS]
        assert len(set(initials)) == 6  # all distinct → no ambiguity

    def test_guide_dropped_sense_ambiguity_claim(self, guide):
        assert "could be Strength or Sense" not in guide
        assert "Unknown attribute" in guide


class TestSkillCount:
    def test_registry_has_76(self, skill_reg):
        assert len(skill_reg.all_skills()) == 76

    def test_guide_says_76_not_75(self, guide):
        assert "76 skills" in guide
        assert "75 skills" not in guide


class TestSkillCap:
    def test_cap_constant_is_2D(self):
        from engine.chargen_validator import MAX_SKILL_BONUS_PIPS
        assert MAX_SKILL_BONUS_PIPS == 6  # 2D

    def test_guide_documents_2D_cap(self, guide):
        assert "2D cap" in guide
        # the cap is enforced at both seams the guide claims
        src = _read(CREATION_SRC)
        assert "MAX_SKILL_BONUS_PIPS" in src


# ── §5: templates ────────────────────────────────────────────────────────────

class TestTemplates:
    def test_nine_templates(self, templates, guide):
        assert len(templates) == 9
        assert "Nine pre-built templates" in guide

    def test_every_template_label_in_guide(self, templates, guide):
        for key, tmpl in templates.items():
            assert tmpl["label"] in guide, tmpl["label"]

    def test_all_templates_human(self, templates):
        # §5 prose: "Applying a template sets the species to Human".
        for key, tmpl in templates.items():
            assert tmpl["species"] == "Human", key

    def test_species_switch_clears_skills(self, guide):
        # §5 now documents that switching species clears skills.
        assert "clears all skills" in guide
        src = _read(CREATION_SRC)
        # _cmd_species resets minimums AND clears skills
        assert "skills.clear()" in src


# ── §6: Force sensitivity is unlocked in play, FP stays 1 ────────────────────

class TestForceSensitivity:
    def test_step_force_not_in_live_ladders(self):
        from engine import creation_wizard as cw
        for steps in (cw.SCRATCH_STEPS_CW, cw.TEMPLATE_STEPS_CW,
                      cw.SCRATCH_STEPS_LEGACY, cw.TEMPLATE_STEPS_LEGACY):
            assert cw.STEP_FORCE not in steps

    def test_guide_says_no_chargen_toggle(self, guide):
        assert "not chosen at character creation" in guide
        assert "no chargen toggle" in guide

    def test_no_phantom_fp_to_2_claim(self, guide):
        assert "raises your Force Points to 2" not in guide
        assert "Force Points stay at **1**" in guide

    def test_village_unlock_seeds_disciplines_not_fp(self):
        """The live unlock seeds Control/Sense/Alter, never writes force_points."""
        src = _read(os.path.join(PROJECT_ROOT, "engine", "village_choice.py"))
        assert "_FORCE_ATTRS = (\"control\", \"sense\", \"alter\")" in src
        assert "_FORCE_SEED_DICE = \"1D\"" in src
        assert "force_points" not in src  # unlock never touches FP

    def test_guide_points_to_teach_bond(self, guide):
        assert "+teach" in guide


# ── §7/§10: starting defaults ────────────────────────────────────────────────

class TestStartingDefaults:
    def _char(self):
        from engine.character import Character
        return Character()

    def test_credits_1000(self, guide):
        assert self._char().credits == 1000
        assert "**1,000 credits.**" in guide
        assert "Credits: 1,000" in guide

    def test_force_points_1(self, guide):
        assert self._char().force_points == 1
        assert "**1 Force Point.**" in guide
        assert "FP: 1" in guide

    def test_cp_5(self, guide):
        assert self._char().character_points == 5
        assert "CP: 5" in guide

    def test_dsp_0(self, guide):
        assert self._char().dark_side_points == 0
        assert "DSP: 0" in guide

    def test_blaster_pistol_price(self, guide):
        """§7's '~500 cr' blaster pistol matches the catalog."""
        weapons = yaml.safe_load(_read(os.path.join(PROJECT_ROOT, "data",
                                                     "weapons.yaml")))
        assert weapons["blaster_pistol"]["cost"] == 500


# ── §8/§9: command surface resolves ──────────────────────────────────────────

class TestCommandSurface:
    FREEFORM_VERBS = ("name", "species", "info", "template", "set", "skill",
                      "unskill", "list", "undo", "sheet", "review", "done",
                      "help")

    def test_freeform_verbs_resolve(self, species_reg, skill_reg):
        """Every §9 free-form command is handled (never 'Unknown command')."""
        from engine.creation import CreationEngine
        eng = CreationEngine(species_reg, skill_reg)
        for verb in self.FREEFORM_VERBS:
            display, _, _ = eng.process_input(verb)
            assert "Unknown command" not in display, verb

    def test_quit_handled_at_creation_loop(self):
        """§9 documents `quit` to abort — intercepted by the creation loop."""
        src = _read(GAME_SERVER_SRC)
        assert 'line.lower() == "quit"' in src

    def test_wizard_nav_commands_present(self):
        """§8 navigation verbs are real wizard tokens."""
        src = _read(WIZARD_SRC)
        for token in ('low == "back"', 'low == "free"', 'low == "guided"',
                      'low == "help"'):
            assert token in src, token

    def test_tutorial_step_first_char_mandatory(self, guide):
        # §8 relabel: step shows for all, mandatory for the first character.
        assert "mandatory for your first character" in guide
        src = _read(WIZARD_SRC)
        assert "_is_first_character" in src
