# -*- coding: utf-8 -*-
"""
tests/test_qa_l2_force_0d_lockout.py — L2 0D force-attribute handling.

HARD INVARIANT (CLAUDE.md): `force_sensitive` is DERIVED from the PRESENCE of
control/sense/alter keys in the attributes JSON — regardless of dice value. A
character whose three keys are all '0D' (an untrained Force-sensitive) is
`force_sensitive=True`; the 0D "lockout" is solved by MESSAGING (guide them to
`+teach`), not by demoting `force_sensitive`.

History (resolved 2026-06-24): two autonomous loop drops contradicted each other
on this. `140c4d9` (this file, originally) added a `from_db_dict` non-zero guard
so all-0D → `force_sensitive=False`; `3e1e00c` then re-aligned the code to the
key-presence invariant (all-0D + keys → True) and fixed the lockout via the
`+teach` message instead (see `tests/test_l2_force_0d_lockout_fix.py`). The live
code (`engine/character.py` `from_db_dict`: "key presence → force-sensitive
(invariant)") follows `3e1e00c`; the original assertions here were stale and have
been corrected to match the invariant + the live behaviour.
"""
import json
import unittest

from engine.character import Character
from engine.dice import DicePool


def _make_db_row(force_attrs: dict) -> dict:
    """Build a minimal DB-row dict with the given force attributes."""
    attrs = {
        "DEX": "2D", "KNO": "2D", "MEC": "2D",
        "PER": "2D", "STR": "2D", "TEC": "2D",
    }
    attrs.update(force_attrs)
    return {
        "id": 1,
        "account_id": 1,
        "name": "TestChar",
        "species": "Human",
        "template": "",
        "room_id": 1,
        "description": "",
        "character_points": 5,
        "force_points": 1,
        "credits": 1000,
        "dark_side_points": 0,
        "wound_level": 0,
        "in_combat": 0,
        "in_hyperspace": 0,
        "docked_at": None,
        "is_active": 1,
        "village_chosen_path": None,
        "attributes": json.dumps(attrs),
        "skills": "{}",
        "inventory": "[]",
        "equipped_weapon": "",
        "worn_armor": "",
        "faction_id": "independent",
        "chargen_notes": "{}",
    }


class TestForce0DLockout(unittest.TestCase):
    """Chars with '0D' force attributes must not be force_sensitive."""

    def test_all_zero_dice_still_force_sensitive(self):
        """control=sense=alter='0D' with keys present => force_sensitive=True.

        Key presence is the invariant trigger, not value. An untrained
        Force-sensitive (all 0D) stays force_sensitive and is guided to +teach.
        """
        row = _make_db_row({"control": "0D", "sense": "0D", "alter": "0D"})
        char = Character.from_db_dict(row)
        self.assertTrue(
            char.force_sensitive,
            "0D force attrs with the keys present MUST mark the char "
            "force-sensitive (key-presence invariant); the lockout is fixed via "
            "messaging, not by demoting force_sensitive.",
        )

    def test_zero_pips_still_force_sensitive(self):
        """control=sense=alter='0D+0' with keys present => force_sensitive=True."""
        row = _make_db_row({"control": "0D+0", "sense": "0D+0", "alter": "0D+0"})
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_nonzero_dice_is_force_sensitive(self):
        """control=sense=alter='1D' => force_sensitive=True."""
        row = _make_db_row({"control": "1D", "sense": "1D", "alter": "1D"})
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_mixed_some_zero_some_nonzero_is_force_sensitive(self):
        """If at least one attribute is non-zero, the char is force_sensitive."""
        row = _make_db_row({"control": "2D", "sense": "0D", "alter": "0D"})
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_pips_only_is_force_sensitive(self):
        """0D+2 (pip-only) counts as non-zero => force_sensitive=True."""
        row = _make_db_row({"control": "0D+2", "sense": "0D", "alter": "0D"})
        char = Character.from_db_dict(row)
        self.assertTrue(char.force_sensitive)

    def test_no_force_attrs_not_force_sensitive(self):
        """No force attribute keys => force_sensitive=False."""
        row = _make_db_row({})
        char = Character.from_db_dict(row)
        self.assertFalse(char.force_sensitive)

    def test_zero_dice_pools_are_loaded(self):
        """Even with 0D, the attribute pool is loaded (dice=0, pips=0)."""
        row = _make_db_row({"control": "0D", "sense": "0D", "alter": "0D"})
        char = Character.from_db_dict(row)
        for attr in ("control", "sense", "alter"):
            pool = char.get_attribute(attr)
            self.assertIsInstance(pool, DicePool)
            self.assertTrue(pool.is_zero(), f"{attr} should be zero-pool")

    def test_failsafe_committed_path_with_zero_dice_still_force_sensitive(self):
        """Path-committed char (village_chosen_path='a') with 0D gets Force
        via the failsafe (a committed Force user whose attrs are zero
        should not be silently stripped of Force-sensitivity)."""
        attrs = {
            "DEX": "2D", "KNO": "2D", "MEC": "2D",
            "PER": "2D", "STR": "2D", "TEC": "2D",
            "control": "0D", "sense": "0D", "alter": "0D",
        }
        row = {
            "id": 2,
            "account_id": 1,
            "name": "Jedi",
            "species": "Human",
            "template": "",
            "room_id": 1,
            "description": "",
            "character_points": 5,
            "force_points": 1,
            "credits": 1000,
            "dark_side_points": 0,
            "wound_level": 0,
            "in_combat": 0,
            "in_hyperspace": 0,
            "docked_at": None,
            "is_active": 1,
            "village_chosen_path": "a",
            "attributes": json.dumps(attrs),
            "skills": "{}",
            "inventory": "[]",
            "equipped_weapon": "",
            "worn_armor": "",
            "faction_id": "independent",
            "chargen_notes": "{}",
        }
        char = Character.from_db_dict(row)
        self.assertTrue(
            char.force_sensitive,
            "Path-committed Jedi must stay force_sensitive=True via failsafe, "
            "even if force attrs are currently 0D.",
        )
