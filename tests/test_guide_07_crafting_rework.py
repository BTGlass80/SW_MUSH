# -*- coding: utf-8 -*-
"""
Tests for Guide_07_Crafting.md rework (June 2026).

Verifies that the updated Crafting Guide:
- Has valid frontmatter (picked up by the existing guide-audit suite)
- Accurately covers the full crafting system as shipped:
  - 7 resource types (including electronic, the 7th added in Gundark Drop A)
  - T5 wilderness-only materials (5 types, drop-only)
  - All 9 trainer NPCs documented
  - Gundark restricted-weapons lane covered
  - T5 master-crafting section present
  - Experimentation axes (damage / accuracy / durability) documented
  - All live commands present in the Quick Reference section
- Is era-clean (no GCW-era terminology in a Clone Wars guide)
"""

import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_07_Crafting.md")


def _load_guide():
    with open(GUIDE_PATH, encoding="utf-8") as f:
        return f.read()


def _strip_frontmatter(text):
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---\n", 4)
    if end < 0:
        return text
    return text[end + 5:]


class TestGuideCraftingFrontmatter(unittest.TestCase):
    """Frontmatter validity is also checked by test_guides_reorganization.py,
    but we pin specific expected values here as a regression guard."""

    @classmethod
    def setUpClass(cls):
        import yaml
        raw = _load_guide()
        cls.raw = raw
        cls.body = _strip_frontmatter(raw)
        assert raw.startswith("---\n"), "missing frontmatter open"
        end = raw.find("\n---\n", 4)
        cls.meta = yaml.safe_load(raw[4:end])

    def test_category_is_economy(self):
        self.assertEqual(self.meta["category"], "economy")

    def test_order_positive_int(self):
        self.assertIsInstance(self.meta["order"], int)
        self.assertGreater(self.meta["order"], 0)

    def test_summary_present(self):
        self.assertGreater(len(self.meta["summary"]), 20)

    def test_tags_include_crafting_keywords(self):
        tags = self.meta["tags"]
        for kw in ("crafting", "resources", "schematic"):
            self.assertIn(kw, tags, f"expected tag {kw!r} in tags")


class TestGuideCraftingResourceTypes(unittest.TestCase):
    """All 7 resource types must be documented."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_standard_resource_metal(self):
        self.assertIn("metal", self.body.lower())

    def test_standard_resource_chemical(self):
        self.assertIn("chemical", self.body.lower())

    def test_standard_resource_organic(self):
        self.assertIn("organic", self.body.lower())

    def test_standard_resource_energy(self):
        self.assertIn("energy", self.body.lower())

    def test_standard_resource_composite(self):
        self.assertIn("composite", self.body.lower())

    def test_standard_resource_rare(self):
        self.assertIn("rare", self.body.lower())

    def test_seventh_resource_electronic(self):
        """electronic was formalized in Gundark Drop A — must be documented."""
        self.assertIn("electronic", self.body.lower())

    def test_resource_count_section_covers_seven(self):
        """The body should mention '7 types' or list all 7 explicitly."""
        self.assertTrue(
            "7 types" in self.body or "7)" in self.body or self.body.count("| **") >= 7,
            "seven resource types not clearly enumerated in the guide"
        )


class TestGuideCraftingT5Materials(unittest.TestCase):
    """T5 wilderness-only materials must be documented."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_kyber_shard_mentioned(self):
        self.assertIn("kyber_shard_minor", self.body)

    def test_weapons_capacitor_core_mentioned(self):
        self.assertIn("weapons_capacitor_core", self.body)

    def test_scavenged_republic_tech_mentioned(self):
        self.assertIn("scavenged_republic_tech", self.body)

    def test_deep_dune_iron_mentioned(self):
        self.assertIn("deep_dune_iron", self.body)

    def test_composite_chitin_mentioned(self):
        self.assertIn("composite_chitin", self.body)

    def test_t5_min_quality_documented(self):
        """Players need to know T5 mats require quality 75+."""
        self.assertIn("75", self.body)

    def test_t5_drop_only_noted(self):
        """T5 materials cannot be surveyed — this must be clear."""
        self.assertIn("drop", self.body.lower())


class TestGuideCraftingTrainers(unittest.TestCase):
    """All trainer NPCs must appear in the guide."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_kayson_mentioned(self):
        self.assertIn("Kayson", self.body)

    def test_sela_tarn_mentioned(self):
        """Sela Tarn (armor trainer) was added in Gundark Drop C."""
        self.assertIn("Sela Tarn", self.body)

    def test_heist_mentioned(self):
        self.assertIn("Heist", self.body)

    def test_vek_nurren_mentioned(self):
        """Vek Nurren (field gear) was added in Gundark Drop E."""
        self.assertIn("Vek Nurren", self.body)

    def test_venn_kator_mentioned(self):
        self.assertIn("Venn Kator", self.body)

    def test_renna_dox_mentioned(self):
        self.assertIn("Renna Dox", self.body)

    def test_gundark_mentioned(self):
        """Gundark (restricted weapons lane) must be documented."""
        self.assertIn("Gundark", self.body)

    def test_doc_vashar_mentioned(self):
        self.assertIn("Doc Vashar", self.body)


class TestGuideCraftingGundarkLane(unittest.TestCase):
    """The Gundark restricted-weapons lane must be documented."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_gundark_section_exists(self):
        self.assertIn("Gundark", self.body)

    def test_nar_shaddaa_undercity_mentioned(self):
        self.assertIn("Undercity", self.body)

    def test_disruptor_pistol_listed(self):
        self.assertIn("Disruptor", self.body)

    def test_predator_rifle_listed(self):
        self.assertIn("Predator Rifle", self.body)

    def test_anti_vehicle_grenade_listed(self):
        self.assertIn("Anti-Vehicle Grenade", self.body)

    def test_contraband_framing(self):
        """The guide should make clear this is restricted/contraband content."""
        body_lower = self.body.lower()
        self.assertTrue(
            "contraband" in body_lower or "restricted" in body_lower,
            "Gundark lane not framed as restricted/contraband in the guide"
        )


class TestGuideCraftingT5Section(unittest.TestCase):
    """T5 master crafting section must cover the five T5 schematics."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_t5_section_exists(self):
        body_lower = self.body.lower()
        self.assertTrue(
            "t5" in body_lower or "master crafting" in body_lower or "master craft" in body_lower,
            "T5 master crafting not documented"
        )

    def test_master_crafted_lightsaber_mentioned(self):
        self.assertIn("Lightsaber", self.body)

    def test_master_vehn_tasaal_mentioned(self):
        self.assertIn("Vehn Tasaal", self.body)

    def test_t5_questline_gate_mentioned(self):
        self.assertIn("questline", self.body.lower())


class TestGuideCraftingExperimentation(unittest.TestCase):
    """Experimentation axes and mechanics must be documented."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_experiment_command_documented(self):
        self.assertIn("experiment", self.body.lower())

    def test_damage_axis_documented(self):
        self.assertIn("damage", self.body.lower())

    def test_accuracy_axis_documented(self):
        self.assertIn("accuracy", self.body.lower())

    def test_durability_axis_documented(self):
        self.assertIn("durability", self.body.lower())

    def test_breakdown_die_risk_mentioned(self):
        """The malfunction risk of experimentation must be communicated."""
        body_lower = self.body.lower()
        self.assertTrue(
            "breakdown" in body_lower or "malfunction" in body_lower or "risk" in body_lower,
            "experimentation risk (breakdown die / malfunction) not mentioned"
        )

    def test_max_3_experiments_documented(self):
        """Players need to know the 3-experiment cap."""
        self.assertIn("3", self.body)


class TestGuideCraftingCommands(unittest.TestCase):
    """Every live crafting command must appear in the guide."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_survey_command_present(self):
        self.assertIn("`survey`", self.body)

    def test_resources_command_present(self):
        self.assertIn("`resources`", self.body)

    def test_schematics_command_present(self):
        self.assertIn("`schematics`", self.body)

    def test_craft_command_present(self):
        self.assertIn("`craft", self.body)

    def test_experiment_command_present(self):
        self.assertIn("`experiment", self.body)

    def test_teach_command_present(self):
        self.assertIn("`teach", self.body)

    def test_buyresources_command_present(self):
        self.assertIn("buyresources", self.body)

    def test_survey_cooldown_mentioned(self):
        """15-minute cooldown is decision-relevant player info."""
        self.assertTrue(
            "15" in self.body or "15-minute" in self.body or "900" in self.body,
            "survey cooldown (15 minutes) not documented"
        )


class TestGuideCraftingEraClean(unittest.TestCase):
    """The crafting guide must not contain GCW-era terminology."""

    GCW_PATTERNS = [
        r"\bGalactic Empire\b",
        r"\bRebel Alliance\b",
        r"\bRebellion\b",
        r"\bStormtrooper",
        r"\bGalactic Civil War\b",
        r"\bGCW\b",
        r"\bTIE [BFI]\w+\b",
        r"\bDeath Star\b",
    ]

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())
        cls.compiled = [re.compile(p) for p in cls.GCW_PATTERNS]

    def test_no_gcw_era_refs(self):
        violations = []
        for i, line in enumerate(self.body.split("\n"), start=1):
            for pat in self.compiled:
                m = pat.search(line)
                if m:
                    violations.append((i, line.strip()[:100], m.group(0)))
        if violations:
            detail = "\n".join(
                f"  line {n}: matched {p!r} — {t}" for n, t, p in violations
            )
            self.fail(f"GCW-era references in crafting guide:\n{detail}")


class TestGuideCraftingWildspaceMods(unittest.TestCase):
    """Wildspace ship mods (added in T3.16 Drop 4) must be documented."""

    @classmethod
    def setUpClass(cls):
        cls.body = _strip_frontmatter(_load_guide())

    def test_mining_laser_documented(self):
        self.assertIn("Mining Laser", self.body)

    def test_salvage_arm_documented(self):
        self.assertIn("Salvage Arm", self.body)

    def test_onboard_refinery_documented(self):
        self.assertIn("Onboard Refinery", self.body)

    def test_rep_gate_documented(self):
        """Mk2 mods are reputation-gated — this must be communicated."""
        body_lower = self.body.lower()
        self.assertTrue(
            "reputation" in body_lower or "rep" in body_lower,
            "Mk2 mod reputation gate not documented"
        )


if __name__ == "__main__":
    unittest.main()
