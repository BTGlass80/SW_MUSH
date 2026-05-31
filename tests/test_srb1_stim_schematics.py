# -*- coding: utf-8 -*-
"""
tests/test_srb1_stim_schematics.py — SRB.1 (a) stim crafting schematics.

Per support_role_buffs_design_v1.md §3.4 ("Stim economics"):
- Stimpacks craftable by anyone with First Aid (typical price 200 cr).
- (A)medicine consumables craftable by trained medics only
  (typical price 800–2000 cr).

Before this drop, only `stimpack_field` existed in
`data/schematics.yaml`. The other three stim families
(`adrenaline_shot`, `focus_stim`, `combat_stim`) had buff templates,
parser commands, and catalog entries, but no crafting recipes — so
the medic economic loop was open. v48 §3.2 Tier 2 #10(a) lists this
gap; this drop closes it.

Test sections
=============

 1. TestAllFourStimsHaveSchematics
    Every key in parser/medical_commands.py::_STIM_CATALOG has at
    least one schematic whose output_key matches.

 2. TestStimSchematicsLoadCleanly
    Each of the four schematic keys is loadable via
    engine/crafting.py::get_schematic without error.

 3. TestStimSchematicsRequiredFields
    Each stim schematic exposes the standard schematic contract
    (key, name, skill_required, difficulty, components, output_type,
    output_key, base_cost, trainer_npc).

 4. TestStimComponentShape
    Components are non-empty lists of {type, quantity, min_quality}
    triples — matches the loader contract used by engine/crafting.py.

 5. TestAdvancedStimsTaughtByHeist
    The three (A)medicine stim schematics name `Heist` as the trainer
    NPC — the existing medical-skill trainer used by `medpac_basic`,
    `medpac_advanced`, and `stimpack_field`.

 6. TestAdvancedStimsRequireMedicine
    `adrenaline_shot_field`, `focus_stim_field`, `combat_stim_field`
    all require `medicine` (the WEG (A)medicine skill key). Only the
    basic `stimpack_field` may use `first_aid`. This enforces the
    design §3.4 split that medic-only consumables exist as a real
    economic profession choice.

 7. TestStimSchematicPricingBands
    Pricing falls in design §3.4 bands:
      - stimpack: cheap (≤ 300 cr)  — basic first aid product
      - adrenaline / focus / combat: 800–2000 cr — medic-only band

 8. TestStimSchematicDifficultyMatchesApplication
    The crafting difficulty for each advanced stim matches the
    application difficulty in _STIM_CATALOG. Design §3.3 says
    adrenaline=15, focus=15, combat=20 for application — keeping
    crafting at the same numbers means the same skill investment
    that unlocks application also unlocks crafting.

 9. TestStimSchematicOutputTypeIsConsumable
    All four stim schematics produce consumables (output_type =
    'consumable') — they're inventory items, not weapons or ship
    components.

10. TestStimSchematicKeysUnique
    The four stim schematic keys do not collide with any other
    schematic key in the file. (Smoke test against accidental
    duplication during YAML editing.)

11. TestCombatStimIsTheHardestStim
    Combat stim has the highest difficulty AND the highest base_cost
    of the four — it's the cap of both progression and price
    per design §3.3 and §3.4.

12. TestStimSchematicCountMinimum
    At least four stim schematics exist (one per _STIM_CATALOG
    entry). Future additions are allowed; this is a floor.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _all_stim_schematics() -> dict:
    """Return {schematic_key: schematic_dict} for all stim schematics."""
    from engine.crafting import get_all_schematics
    return {
        key: s for key, s in get_all_schematics().items()
        if s.get("output_key") in {
            "stimpack", "adrenaline_shot", "focus_stim", "combat_stim",
        }
    }


def _stim_catalog_keys() -> set:
    from parser.medical_commands import _STIM_CATALOG
    return set(_STIM_CATALOG.keys())


# ---------------------------------------------------------------------------
# 1. All four stims have schematics
# ---------------------------------------------------------------------------

class TestAllFourStimsHaveSchematics(unittest.TestCase):
    def test_every_catalog_key_has_a_schematic(self):
        catalog_keys = _stim_catalog_keys()
        stim_outputs = {s["output_key"] for s in _all_stim_schematics().values()}
        missing = catalog_keys - stim_outputs
        self.assertFalse(
            missing,
            f"Stim catalog keys without a schematic: {missing}. "
            f"Every entry in parser/medical_commands.py::_STIM_CATALOG "
            f"needs a crafting recipe so the medic economic loop closes.",
        )


# ---------------------------------------------------------------------------
# 2. Each stim schematic loads cleanly
# ---------------------------------------------------------------------------

class TestStimSchematicsLoadCleanly(unittest.TestCase):
    EXPECTED_KEYS = (
        "stimpack_field",
        "adrenaline_shot_field",
        "focus_stim_field",
        "combat_stim_field",
    )

    def test_each_key_loads(self):
        from engine.crafting import get_schematic
        for key in self.EXPECTED_KEYS:
            with self.subTest(key=key):
                s = get_schematic(key)
                self.assertIsNotNone(
                    s,
                    f"Schematic {key!r} returned None from "
                    f"engine.crafting.get_schematic. Check "
                    f"data/schematics.yaml.",
                )


# ---------------------------------------------------------------------------
# 3. Required schematic fields present
# ---------------------------------------------------------------------------

class TestStimSchematicsRequiredFields(unittest.TestCase):
    REQUIRED_FIELDS = (
        "key", "name", "skill_required", "difficulty",
        "components", "output_type", "output_key", "base_cost",
        "trainer_npc",
    )

    def test_required_fields(self):
        stims = _all_stim_schematics()
        self.assertGreaterEqual(len(stims), 4)
        for skey, s in stims.items():
            for field in self.REQUIRED_FIELDS:
                with self.subTest(schematic=skey, field=field):
                    self.assertIn(
                        field, s,
                        f"Stim schematic {skey!r} missing required "
                        f"field {field!r}.",
                    )


# ---------------------------------------------------------------------------
# 4. Component-shape sanity
# ---------------------------------------------------------------------------

class TestStimComponentShape(unittest.TestCase):
    def test_components_are_non_empty_list_of_triples(self):
        for skey, s in _all_stim_schematics().items():
            with self.subTest(schematic=skey):
                comps = s.get("components")
                self.assertIsInstance(comps, list, f"{skey} components not a list")
                self.assertGreater(len(comps), 0, f"{skey} components empty")
                for i, c in enumerate(comps):
                    self.assertIn("type", c, f"{skey}[{i}] no type")
                    self.assertIn("quantity", c, f"{skey}[{i}] no quantity")
                    self.assertIn("min_quality", c, f"{skey}[{i}] no min_quality")
                    self.assertIsInstance(c["quantity"], int)
                    self.assertGreater(c["quantity"], 0)
                    self.assertIsInstance(c["min_quality"], int)
                    self.assertGreaterEqual(c["min_quality"], 0)
                    self.assertLessEqual(c["min_quality"], 100)


# ---------------------------------------------------------------------------
# 5. Heist teaches all advanced stims
# ---------------------------------------------------------------------------

class TestAdvancedStimsTaughtByHeist(unittest.TestCase):
    ADVANCED_KEYS = (
        "adrenaline_shot_field",
        "focus_stim_field",
        "combat_stim_field",
    )

    def test_heist_is_trainer(self):
        from engine.crafting import get_schematic
        for key in self.ADVANCED_KEYS:
            with self.subTest(schematic=key):
                s = get_schematic(key)
                self.assertEqual(
                    s["trainer_npc"], "Heist",
                    f"{key} trainer should be Heist (existing medical "
                    f"trainer) but is {s['trainer_npc']!r}",
                )


# ---------------------------------------------------------------------------
# 6. Advanced stims require (A)medicine
# ---------------------------------------------------------------------------

class TestAdvancedStimsRequireMedicine(unittest.TestCase):
    def test_basic_stim_first_aid(self):
        from engine.crafting import get_schematic
        s = get_schematic("stimpack_field")
        self.assertEqual(s["skill_required"], "first_aid")

    def test_advanced_stims_require_medicine(self):
        from engine.crafting import get_schematic
        for key in ("adrenaline_shot_field",
                    "focus_stim_field",
                    "combat_stim_field"):
            with self.subTest(schematic=key):
                s = get_schematic(key)
                self.assertEqual(
                    s["skill_required"], "medicine",
                    f"{key} should require 'medicine' (the WEG "
                    f"(A)medicine skill key) per design §3.4, not "
                    f"{s['skill_required']!r}",
                )


# ---------------------------------------------------------------------------
# 7. Pricing bands match design §3.4
# ---------------------------------------------------------------------------

class TestStimSchematicPricingBands(unittest.TestCase):
    def test_stimpack_cheap(self):
        from engine.crafting import get_schematic
        s = get_schematic("stimpack_field")
        self.assertLessEqual(
            s["base_cost"], 300,
            "Stimpack (basic first aid product) should be in the "
            "≤ 300 cr band per design §3.4",
        )

    def test_advanced_stims_in_band(self):
        from engine.crafting import get_schematic
        for key in ("adrenaline_shot_field",
                    "focus_stim_field",
                    "combat_stim_field"):
            with self.subTest(schematic=key):
                s = get_schematic(key)
                self.assertGreaterEqual(
                    s["base_cost"], 800,
                    f"{key} below 800 cr — design §3.4 medic-only band "
                    f"is 800–2000 cr (typical price 800–2000 cr).",
                )
                self.assertLessEqual(
                    s["base_cost"], 2000,
                    f"{key} above 2000 cr — design §3.4 medic-only band "
                    f"is 800–2000 cr.",
                )


# ---------------------------------------------------------------------------
# 8. Crafting difficulty matches application difficulty
# ---------------------------------------------------------------------------

class TestStimSchematicDifficultyMatchesApplication(unittest.TestCase):
    """The difficulty for crafting a stim should match the difficulty
    for applying it (design §3.3). Same skill investment unlocks
    both phases of the loop."""

    def test_difficulties_align(self):
        from engine.crafting import get_schematic
        from parser.medical_commands import _STIM_CATALOG
        pairs = (
            ("adrenaline_shot_field", "adrenaline_shot"),
            ("focus_stim_field", "focus_stim"),
            ("combat_stim_field", "combat_stim"),
        )
        for schem_key, catalog_key in pairs:
            with self.subTest(schematic=schem_key):
                s = get_schematic(schem_key)
                cat = _STIM_CATALOG[catalog_key]
                self.assertEqual(
                    s["difficulty"], cat["difficulty"],
                    f"{schem_key} crafting difficulty "
                    f"({s['difficulty']}) does not match application "
                    f"difficulty ({cat['difficulty']}) for "
                    f"{catalog_key!r}.",
                )


# ---------------------------------------------------------------------------
# 9. Output type
# ---------------------------------------------------------------------------

class TestStimSchematicOutputTypeIsConsumable(unittest.TestCase):
    def test_output_type(self):
        for skey, s in _all_stim_schematics().items():
            with self.subTest(schematic=skey):
                self.assertEqual(
                    s["output_type"], "consumable",
                    f"{skey} should be output_type='consumable', is "
                    f"{s['output_type']!r}",
                )


# ---------------------------------------------------------------------------
# 10. Keys unique
# ---------------------------------------------------------------------------

class TestStimSchematicKeysUnique(unittest.TestCase):
    def test_keys_unique(self):
        # If get_all_schematics()'s comprehension would have collided,
        # we wouldn't see the duplicate — re-parse the raw YAML to
        # check for actual duplicates.
        import yaml
        from engine.crafting import SCHEMATICS_YAML
        with open(SCHEMATICS_YAML, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        keys = [s["key"] for s in raw.get("schematics", [])]
        seen: set = set()
        dupes: set = set()
        for k in keys:
            if k in seen:
                dupes.add(k)
            seen.add(k)
        self.assertFalse(
            dupes,
            f"Duplicate schematic keys in data/schematics.yaml: {dupes}",
        )


# ---------------------------------------------------------------------------
# 11. Combat stim is the hardest and the priciest
# ---------------------------------------------------------------------------

class TestCombatStimIsTheHardestStim(unittest.TestCase):
    def test_combat_stim_caps_difficulty_and_price(self):
        from engine.crafting import get_schematic
        combat = get_schematic("combat_stim_field")
        for other_key in ("stimpack_field",
                          "adrenaline_shot_field",
                          "focus_stim_field"):
            other = get_schematic(other_key)
            with self.subTest(other=other_key):
                self.assertGreaterEqual(
                    combat["difficulty"], other["difficulty"],
                    f"combat_stim_field difficulty should be ≥ "
                    f"{other_key} per design §3.3",
                )
                self.assertGreaterEqual(
                    combat["base_cost"], other["base_cost"],
                    f"combat_stim_field base_cost should be ≥ "
                    f"{other_key} per design §3.4",
                )


# ---------------------------------------------------------------------------
# 12. Stim schematic count floor
# ---------------------------------------------------------------------------

class TestStimSchematicCountMinimum(unittest.TestCase):
    def test_at_least_four_stim_schematics(self):
        stims = _all_stim_schematics()
        self.assertGreaterEqual(
            len(stims), 4,
            f"Expected ≥ 4 stim schematics (one per _STIM_CATALOG "
            f"entry); found {len(stims)}.",
        )


if __name__ == "__main__":
    unittest.main()
