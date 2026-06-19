# -*- coding: utf-8 -*-
"""
tests/test_species_b3_era_clean.py — B3 era-cleanness guard for data/species/*.yaml

Fixes dropped by Guide_01 quality pass (flagged, left to a follow-up fire because
that drop was engine+data READ-ONLY):
  - wookiee.yaml story_factor: "Imperial enslavement" → CW-era Clone Wars line
  - bothan.yaml description: "Rebellion the plans to the second Death Star" → removed
  - mon_calamari.yaml description: "Rebel Alliance's finest capital ships" → removed
  - mon_calamari.yaml story_factor: "Rebel Alliance's strongest supporters" → Republic

These are production strings (loaded into chargen / +help species / species sheet),
not comments or era-mapping config, so B3 applies.
"""
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
SPECIES_DIR = os.path.join(PROJECT_ROOT, "data", "species")


def _load(filename: str) -> str:
    with open(os.path.join(SPECIES_DIR, filename), encoding="utf-8") as fh:
        return fh.read()


class TestWookieeB3(unittest.TestCase):
    def setUp(self):
        self.content = _load("wookiee.yaml")

    def test_no_imperial_in_story_factors(self):
        self.assertNotIn("Imperial", self.content)

    def test_cw_era_replacement_present(self):
        self.assertIn("Clone Wars", self.content)

    def test_kashyyyk_mentioned(self):
        self.assertIn("Kashyyyk", self.content)

    def test_republic_alliance_present(self):
        self.assertIn("Republic", self.content)


class TestBothanB3(unittest.TestCase):
    def setUp(self):
        self.content = _load("bothan.yaml")

    def test_no_rebellion_in_description(self):
        self.assertNotIn("Rebellion", self.content)

    def test_no_death_star_in_description(self):
        self.assertNotIn("Death Star", self.content)

    def test_cw_era_flavor_present(self):
        # Replacement mentions Republic and Separatist clients
        self.assertIn("Republic", self.content)
        self.assertIn("Separatist", self.content)

    def test_spynet_description_intact(self):
        self.assertIn("intelligence network", self.content)


class TestMonCalamariB3(unittest.TestCase):
    def setUp(self):
        self.content = _load("mon_calamari.yaml")

    def test_no_rebel_alliance_in_description(self):
        self.assertNotIn("Rebel Alliance", self.content)

    def test_no_rebel_in_story_factors(self):
        # Catch both "Rebel Alliance" and bare "Rebel"
        self.assertNotIn("Rebel", self.content)

    def test_cw_era_story_factor_present(self):
        self.assertIn("Galactic Republic", self.content)

    def test_shipbuilding_description_intact(self):
        self.assertIn("capital warships", self.content)

    def test_amphibious_ability_intact(self):
        self.assertIn("Amphibious", self.content)


class TestAllSpeciesNoEraViolations(unittest.TestCase):
    """Blanket guard: no B3 terms in any species YAML production string."""

    B3_TERMS = ["Imperial", "Rebel Alliance", "Galactic Empire", "TIE Fighter", "Death Star"]

    def _species_files(self):
        return [
            f for f in os.listdir(SPECIES_DIR)
            if f.endswith(".yaml")
        ]

    def test_no_b3_terms_in_any_species_file(self):
        violations = []
        for fname in self._species_files():
            content = _load(fname)
            for term in self.B3_TERMS:
                if term in content:
                    violations.append(f"{fname}: contains '{term}'")
        self.assertEqual(
            violations, [],
            "B3 era violation(s) in species files:\n" + "\n".join(violations),
        )


if __name__ == "__main__":
    unittest.main()
