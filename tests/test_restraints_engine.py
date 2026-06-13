"""CRAFT.HOOK.restraints — engine core (state model + consent/defeat gate).

Tests engine/restraints.py in isolation. The verb layer (cuff/uncuff/escape/
allow restrain) + the move/attack/equip gates + the binders item land in the
follow-up slice that wires this core to the player surface. Design:
docs/design/restraints_system_design_v1.md.

The Brian-decided PvP norm under test: a PC may be cuffed only if DEFEATED
(wound_level >= INCAPACITATED) or CONSENTING; never a healthy unwilling PC.
NPCs need no consent.
"""
import json
import unittest

import engine.restraints as R


class TestConsentDefeatGate(unittest.TestCase):
    """The Brian PvP norm: consent/defeat-gated."""

    def test_healthy_unwilling_pc_rejected(self):
        ok, reason = R.can_be_restrained({"attributes": "{}", "wound_level": 0})
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_defeated_pc_allowed(self):
        # wound_level >= INCAPACITATED (4)
        ok, _ = R.can_be_restrained({"attributes": "{}", "wound_level": 4})
        self.assertTrue(ok)

    def test_mortally_wounded_pc_allowed(self):
        ok, _ = R.can_be_restrained({"attributes": "{}", "wound_level": 5})
        self.assertTrue(ok)

    def test_wounded_but_not_incapacitated_rejected(self):
        # wound_level 3 (WOUNDED_TWICE) is NOT defeated.
        ok, _ = R.can_be_restrained({"attributes": "{}", "wound_level": 3})
        self.assertFalse(ok)

    def test_consenting_pc_allowed(self):
        c = {"attributes": "{}", "wound_level": 0}
        R.set_consent(c, True)
        ok, _ = R.can_be_restrained(c)
        self.assertTrue(ok)

    def test_npc_allowed_without_consent(self):
        ok, _ = R.can_be_restrained({"attributes": "{}", "wound_level": 0},
                                    is_npc=True)
        self.assertTrue(ok)

    def test_already_restrained_rejected(self):
        c = {"attributes": "{}", "wound_level": 4}
        R.apply_restraint(c, applied_by="X", applied_by_id=1)
        ok, _ = R.can_be_restrained(c)
        self.assertFalse(ok)

    def test_malformed_wound_level_safe(self):
        ok, _ = R.can_be_restrained({"attributes": "{}", "wound_level": "bad"})
        self.assertFalse(ok)  # treated as 0 → not defeated


class TestApplyReadRelease(unittest.TestCase):

    def test_apply_sets_state(self):
        c = {"attributes": "{}", "wound_level": 4}
        self.assertFalse(R.is_restrained(c))
        R.apply_restraint(c, applied_by="Vos", applied_by_id=7,
                          escape_difficulty=15)
        self.assertTrue(R.is_restrained(c))
        st = R.get_restraint(c)
        self.assertEqual(st["applied_by"], "Vos")
        self.assertEqual(st["applied_by_id"], 7)
        self.assertEqual(st["item_key"], "binders")
        self.assertEqual(st["escape_difficulty"], 15)
        self.assertIn("applied_at", st)

    def test_get_restraint_none_when_free(self):
        self.assertIsNone(R.get_restraint({"attributes": "{}"}))

    def test_release_clears_state(self):
        c = {"attributes": "{}", "wound_level": 4}
        R.apply_restraint(c, applied_by="V", applied_by_id=7)
        self.assertTrue(R.release_restraint(c))
        self.assertFalse(R.is_restrained(c))

    def test_release_when_free_returns_false(self):
        self.assertFalse(R.release_restraint({"attributes": "{}"}))

    def test_state_survives_json_string_roundtrip(self):
        # The DB shape is a JSON string — apply must write it back as a string
        # so save_character persists it (logout survival).
        c = {"attributes": json.dumps({"foo": "bar"}), "wound_level": 4}
        R.apply_restraint(c, applied_by="V", applied_by_id=7)
        self.assertIsInstance(c["attributes"], str)  # shape preserved
        reloaded = {"attributes": c["attributes"]}
        self.assertTrue(R.is_restrained(reloaded))   # survives reload
        # Unrelated attrs preserved.
        self.assertEqual(json.loads(c["attributes"])["foo"], "bar")

    def test_dict_attributes_shape_preserved(self):
        c = {"attributes": {"foo": "bar"}, "wound_level": 4}
        R.apply_restraint(c, applied_by="V", applied_by_id=7)
        self.assertIsInstance(c["attributes"], dict)  # stays dict in-memory


class TestReleaseAuthority(unittest.TestCase):

    def _restraint(self, captor_id=7):
        c = {"attributes": "{}", "wound_level": 4}
        R.apply_restraint(c, applied_by="Captor", applied_by_id=captor_id)
        return R.get_restraint(c)

    def test_captor_can_release(self):
        self.assertTrue(R.can_release(self._restraint(7), 7))

    def test_third_party_cannot_release(self):
        self.assertFalse(R.can_release(self._restraint(7), 9))

    def test_admin_can_release_anyone(self):
        self.assertTrue(R.can_release(self._restraint(7), 9, is_admin=True))


class TestConsentToggle(unittest.TestCase):

    def test_set_and_clear_consent(self):
        c = {"attributes": "{}"}
        R.set_consent(c, True)
        self.assertTrue(R.restraint_consent(c))
        R.set_consent(c, False)
        self.assertFalse(R.restraint_consent(c))

    def test_consent_absent_defaults_false(self):
        self.assertFalse(R.restraint_consent({"attributes": "{}"}))


class TestEscape(unittest.TestCase):

    def test_escape_noop_when_free(self):
        escaped, diff = R.attempt_escape({"attributes": "{}"})
        self.assertFalse(escaped)
        self.assertEqual(diff, 0)

    def test_escape_uses_restraint_difficulty(self):
        # A character with a huge Strength always beats DC 15; confirm the
        # check runs against the stored difficulty and reports it.
        c = {
            "attributes": json.dumps({
                "strength": "12D",  # absurdly strong → reliable success
            }),
            "skills": "{}",
            "wound_level": 0,
        }
        R.apply_restraint(c, applied_by="V", applied_by_id=7,
                          escape_difficulty=15)
        escaped, diff = R.attempt_escape(c)
        self.assertEqual(diff, 15)
        self.assertTrue(escaped)
        # attempt_escape does NOT auto-clear — the verb layer does on success.
        self.assertTrue(R.is_restrained(c))


if __name__ == "__main__":
    unittest.main()
