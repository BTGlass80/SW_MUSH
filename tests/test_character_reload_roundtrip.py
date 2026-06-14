# -*- coding: utf-8 -*-
"""tests/test_character_reload_roundtrip.py — T3.20 state-preservation.

A reload-round-trip INVARIANT for the most important persisted entity: a player
Character (`scope_notes` c — codify the (de)serialization contract). It locks
the `to_db_dict` <-> `from_db_dict` CORE-field contract: build a Character from a
realistic DB row, round-trip it through `to_db_dict` -> `from_db_dict`, and assert
every core persisted field survives unchanged. This catches the silent
save-data-loss class where a field is added to one serializer but not the other,
or a column key is renamed — drift that no per-feature test would notice.

SCOPE NOTE: `to_db_dict` is the CORE-column serializer; the typed-column extras
(`wound_state`, `wound_clear_at`, `village_chosen_path`) and per-slot equipment
INSTANCES are written by `save_character` / specific setters, NOT by `to_db_dict`
(documented in engine/character.py). So this asserts the core round-trip, not
those out-of-band columns — that boundary is the contract, and it is pinned here.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _rich_row():
    from engine.character import ATTRIBUTE_NAMES
    # A force-sensitive character so control/sense/alter -> force_sensitive
    # round-trips too. Use the live ATTRIBUTE_NAMES so the row stays valid if
    # the attribute set ever changes.
    attrs = {a: "3D+1" for a in ATTRIBUTE_NAMES}
    attrs.update({"control": "2D", "sense": "2D+1", "alter": "1D+2"})
    return {
        "id": 42,
        "account_id": 7,
        "name": "Round Trip Test",
        "species": "Twi'lek",
        "template": "smuggler",
        "attributes": json.dumps(attrs),
        "skills": json.dumps({"blaster": "1D+1", "dodge": "2D",
                              "space_transports": "1D"}),
        "wound_level": 2,
        "character_points": 7,
        "force_points": 3,
        "dark_side_points": 1,
        "credits": 4250,
        "room_id": 88,
        "description": "A wary Twi'lek pilot with a price on their head.",
        "equipment": json.dumps({"weapon": "blaster_pistol", "armor": "padded_vest"}),
        "chargen_notes": "rolled hot, owes the Hutts",
        "village_chosen_path": "b",
    }


class TestCharacterReloadRoundTrip(unittest.TestCase):
    def setUp(self):
        from engine.character import Character
        self.Character = Character
        self.c1 = Character.from_db_dict(_rich_row())
        self.c2 = Character.from_db_dict(self.c1.to_db_dict())

    def test_scalar_fields_survive(self):
        for f in ("name", "species_name", "template", "room_id", "description",
                  "character_points", "force_points", "dark_side_points",
                  "credits", "chargen_notes"):
            self.assertEqual(getattr(self.c2, f), getattr(self.c1, f),
                             f"field {f!r} did not survive the reload round-trip")

    def test_wound_level_survives(self):
        self.assertEqual(self.c2.wound_level, self.c1.wound_level)

    def test_attributes_survive(self):
        from engine.character import ATTRIBUTE_NAMES
        for a in ATTRIBUTE_NAMES:
            self.assertEqual(str(self.c2.get_attribute(a)),
                             str(self.c1.get_attribute(a)),
                             f"attribute {a!r} drifted across the round-trip")

    def test_force_sensitivity_and_force_attrs_survive(self):
        self.assertTrue(self.c1.force_sensitive)        # sanity: built FS
        self.assertEqual(self.c2.force_sensitive, self.c1.force_sensitive)
        for fa in ("control", "sense", "alter"):
            self.assertEqual(str(self.c2.get_attribute(fa)),
                             str(self.c1.get_attribute(fa)),
                             f"force attribute {fa!r} drifted across the round-trip")

    def test_skills_survive(self):
        s1 = {k: str(v) for k, v in self.c1.skills.items()}
        s2 = {k: str(v) for k, v in self.c2.skills.items()}
        self.assertEqual(s2, s1, "skills drifted across the reload round-trip")

    def test_equipment_keys_survive(self):
        self.assertEqual(self.c2.equipped_weapon, self.c1.equipped_weapon)
        self.assertEqual(self.c2.worn_armor, self.c1.worn_armor)

    def test_to_db_dict_is_stable_under_round_trip(self):
        # The strongest single guard: re-serializing the reloaded character must
        # reproduce the exact same core DB dict (deterministic serialization).
        self.assertEqual(self.c2.to_db_dict(), self.c1.to_db_dict())


if __name__ == "__main__":
    unittest.main()
