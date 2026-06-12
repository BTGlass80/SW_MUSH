"""Skill-key resolution unification (2026-06-11, same-day drop 1).

The repo carried two live key dialects for the SAME skills — space-form
(SkillRegistry / chargen / train / MISSION_SKILL_MAP / combat literals)
and underscore-form (every schematics.yaml skill_required; most NPC yaml
skill blocks: 46× melee_combat, 43× first_aid). Nothing translated, so
cross-dialect lookups silently resolved UNTRAINED — and in
skill_checks._skill_to_attr, to the wrong governing attribute (default
"perception"). Live reproduction that motivated the fix: a PC with
Blaster Repair 3D + Technical 3D crafting a blaster rolled **2D raw
Perception**.

engine.character.canonical_skill_key() is now the single translation
point, routed through:
  • SkillRegistry.get
  • Character.get_skill_pool      (combat's resolution surface)
  • Character.advance_skill       (write-side convergence)
  • skill_checks.perform_skill_check ingress, _get_skill_pool,
    _skill_to_attr                (crafting / missions / stims surface)
  • parser/cp_commands train ingress (no split-key writes)

These tests pin the four lookup quadrants, the attribute mapping for
every schematics.yaml skill_required, and a whole-catalog structural
gate so future data-side spellings fail loudly at data-entry time.
"""
import json
import unittest
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _registry():
    from engine.character import SkillRegistry
    reg = SkillRegistry()
    reg.load_file(str(REPO / "data" / "skills.yaml"))
    return reg


def _schematics():
    return yaml.safe_load(
        (REPO / "data" / "schematics.yaml").read_text(encoding="utf-8")
    )["schematics"]


# Skill_required values that are sanctioned WITHOUT a registry entry.
# Each needs an explicit governing-attribute mapping in
# skill_checks._FALLBACK and a comment there pointing back here.
SANCTIONED_NON_REGISTRY = {"craft lightsaber"}


# ──────────────────────────────────────────────────────────────────────
# The helper itself
# ──────────────────────────────────────────────────────────────────────

class TestCanonicalSkillKey(unittest.TestCase):
    def test_separator_normalization(self):
        from engine.character import canonical_skill_key as c
        self.assertEqual(c("blaster_repair"), "blaster repair")
        self.assertEqual(c("Melee_Combat"), "melee combat")
        self.assertEqual(c("  first_aid  "), "first aid")
        self.assertEqual(c("security"), "security")

    def test_sanctioned_aliases(self):
        from engine.character import canonical_skill_key as c
        self.assertEqual(c("computer_prog"), "computer programming/repair")
        self.assertEqual(c("computer programming"),
                         "computer programming/repair")
        # plural/singular drift: MISSION_SKILL_MAP + schematics say
        # "space transports repair"; the registry (and chargen
        # templates) say "space transport repair".
        self.assertEqual(c("space_transports_repair"),
                         "space transport repair")
        self.assertEqual(c("space transports repair"),
                         "space transport repair")
        self.assertEqual(c("pickpocket"), "pick pocket")

    def test_idempotent_and_safe(self):
        from engine.character import canonical_skill_key as c
        self.assertEqual(c(c("blaster_repair")), c("blaster_repair"))
        self.assertEqual(c(""), "")
        self.assertEqual(c(None), "")


# ──────────────────────────────────────────────────────────────────────
# Registry accepts both dialects
# ──────────────────────────────────────────────────────────────────────

class TestRegistryBothDialects(unittest.TestCase):
    def test_underscore_form_resolves(self):
        reg = _registry()
        sd = reg.get("blaster_repair")
        self.assertIsNotNone(sd)
        self.assertEqual(sd.name, "Blaster Repair")
        self.assertEqual(sd.attribute, "technical")

    def test_alias_forms_resolve(self):
        reg = _registry()
        self.assertEqual(reg.get("computer_prog").name,
                         "Computer Programming/Repair")
        self.assertEqual(reg.get("space transports repair").name,
                         "Space Transport Repair")

    def test_unknown_still_none(self):
        reg = _registry()
        self.assertIsNone(reg.get("underwater basket weaving"))
        self.assertIsNone(reg.get("craft_lightsaber"))  # sanctioned via
        # the _FALLBACK attr map, deliberately NOT registry-registered.


# ──────────────────────────────────────────────────────────────────────
# Governing-attribute mapping — the "perception default" pathology
# ──────────────────────────────────────────────────────────────────────

class TestSkillToAttr(unittest.TestCase):
    # Every skill_required value in data/schematics.yaml as of this
    # drop, with its CORRECT governing attribute. Before the fix the
    # starred rows all returned "perception".
    EXPECTED = {
        "blaster_repair": "technical",            # *
        "armor_repair": "technical",              # *
        "droid_repair": "technical",              # *
        "starship_weapon_repair": "technical",    # *
        "space_transports_repair": "technical",   # *
        "first_aid": "technical",                 # *
        "computer_prog": "technical",             # *
        "melee_combat": "dexterity",              # *
        "craft_lightsaber": "technical",          # * (fallback map)
        "security": "technical",
        "medicine": "technical",
        "survival": "knowledge",
        "demolitions": "technical",               # Drop D's skill (b=a)
    }

    def test_attribute_table(self):
        from engine.skill_checks import _skill_to_attr
        reg = _registry()
        for skill, want in self.EXPECTED.items():
            self.assertEqual(
                _skill_to_attr(skill, reg), want,
                f"{skill}: wrong governing attribute")

    def test_perception_default_no_longer_reachable_for_catalog(self):
        from engine.skill_checks import _skill_to_attr
        reg = _registry()
        for s in _schematics():
            req = s.get("skill_required", "")
            self.assertNotEqual(
                _skill_to_attr(req, reg), "perception",
                f"schematic '{s.get('key')}' skill_required '{req}' "
                f"fell to the perception default")


# ──────────────────────────────────────────────────────────────────────
# _get_skill_pool — the four lookup quadrants (dict-shaped chars)
# ──────────────────────────────────────────────────────────────────────

def _pc(skills: dict, technical="3D", perception="2D", dexterity="2D"):
    return {
        "id": 1,
        "attributes": json.dumps({
            "technical": technical, "perception": perception,
            "dexterity": dexterity, "strength": "2D",
            "knowledge": "2D", "mechanical": "2D",
        }),
        "skills": json.dumps(skills),
    }


class TestGetSkillPoolQuadrants(unittest.TestCase):
    def setUp(self):
        self.reg = _registry()

    def _pool(self, char, skill):
        from engine.skill_checks import _get_skill_pool
        return _get_skill_pool(char, skill, self.reg)

    def test_pc_space_dict_underscore_request(self):
        # The crafting quadrant: chargen-shaped PC, schematic-shaped key.
        pc = _pc({"blaster repair": "3D"})
        self.assertEqual(self._pool(pc, "blaster_repair"), (6, 0))

    def test_npc_underscore_dict_space_request(self):
        # The combat/mission quadrant: yaml-shaped NPC, engine-shaped key.
        npc = _pc({"first_aid": "2D+1"})
        self.assertEqual(self._pool(npc, "first aid"), (5, 1))

    def test_matched_forms_unchanged(self):
        pc = _pc({"security": "2D"})
        self.assertEqual(self._pool(pc, "security"), (5, 0))

    def test_untrained_rolls_correct_attribute(self):
        # Before the fix: blaster_repair → perception 2D. Now: technical.
        pc = _pc({})
        self.assertEqual(self._pool(pc, "blaster_repair"), (3, 0))

    def test_plural_transport_mission_quadrant(self):
        # MISSION_SKILL_MAP's "space transports repair" vs the chargen
        # template's registry-canonical "space transport repair".
        pc = _pc({"space transport repair": "1D+1"})
        self.assertEqual(self._pool(pc, "space transports repair"), (4, 1))


class TestPerformSkillCheckEndToEnd(unittest.TestCase):
    def test_trained_crafter_pool(self):
        from engine.skill_checks import perform_skill_check
        pc = _pc({"blaster repair": "3D"})
        # lead_bonus=0 suppresses the combined-action auto-consume
        # (test isolation — no singleton touch).
        r = perform_skill_check(pc, "blaster_repair", 15,
                                skill_registry=_registry(), lead_bonus=0)
        self.assertEqual(r.pool_str, "6D",
                         "trained Blaster Repair must roll attr+skill, "
                         "not the old 2D raw-Perception path")


# ──────────────────────────────────────────────────────────────────────
# Character.get_skill_pool — combat's resolution surface
# ──────────────────────────────────────────────────────────────────────

class TestCharacterGetSkillPool(unittest.TestCase):
    def _char(self, skills):
        from engine.character import Character
        from engine.dice import DicePool
        ch = Character()
        ch.dexterity = DicePool(3, 0)
        ch.skills = {k: DicePool.parse(v) for k, v in skills.items()}
        return ch

    def test_underscore_npc_dict_melee_combat(self):
        # 46 NPC yaml blocks carry "melee_combat:". Combat queries
        # "melee combat". Before the fix these NPCs attacked and
        # parried at raw attribute.
        reg = _registry()
        ch = self._char({"melee_combat": "2D"})
        pool = ch.get_skill_pool("melee combat", reg)
        self.assertEqual((pool.dice, pool.pips), (5, 0))

    def test_underscore_npc_dict_brawling_parry(self):
        reg = _registry()
        ch = self._char({"brawling_parry": "1D+2"})
        pool = ch.get_skill_pool("brawling parry", reg)
        self.assertEqual((pool.dice, pool.pips), (4, 2))

    def test_unknown_skill_still_zero_pool(self):
        reg = _registry()
        ch = self._char({})
        pool = ch.get_skill_pool("underwater basket weaving", reg)
        self.assertEqual((pool.dice, pool.pips), (0, 0))


# ──────────────────────────────────────────────────────────────────────
# Whole-catalog structural gates — Drop B+ mass-application safety
# ──────────────────────────────────────────────────────────────────────

class TestWholeCatalogResolution(unittest.TestCase):
    def test_every_skill_required_resolves(self):
        from engine.character import canonical_skill_key
        reg = _registry()
        for s in _schematics():
            req = s.get("skill_required", "")
            canon = canonical_skill_key(req)
            if canon in SANCTIONED_NON_REGISTRY:
                continue
            self.assertIsNotNone(
                reg.get(canon),
                f"schematic '{s.get('key')}' skill_required '{req}' "
                f"does not resolve to a registered skill — fix the "
                f"data or add a sanctioned alias")

    def test_mission_skill_map_resolves(self):
        from engine.skill_checks import MISSION_SKILL_MAP
        reg = _registry()
        for mtype, (skill, _frac) in MISSION_SKILL_MAP.items():
            self.assertIsNotNone(
                reg.get(skill),
                f"MISSION_SKILL_MAP['{mtype}'] skill '{skill}' "
                f"does not resolve")


# ──────────────────────────────────────────────────────────────────────
# Source pins — write-side convergence
# ──────────────────────────────────────────────────────────────────────

class TestWriteSitePins(unittest.TestCase):
    def _code(self, path):
        text = path.read_text(encoding="utf-8")
        return "\n".join(
            ln for ln in text.splitlines()
            if not ln.lstrip().startswith("#"))

    def test_train_command_canonicalizes(self):
        code = self._code(REPO / "parser" / "cp_commands.py")
        self.assertIn("canonical_skill_key(skill_name)", code)

    def test_advance_skill_canonicalizes(self):
        code = self._code(REPO / "engine" / "character.py")
        self.assertIn("key = canonical_skill_key(skill_name)", code)

    def test_chokepoint_ingress_canonicalizes(self):
        code = self._code(REPO / "engine" / "skill_checks.py")
        self.assertIn("skill_name = canonical_skill_key(skill_name)", code)


if __name__ == "__main__":
    unittest.main()
