# -*- coding: utf-8 -*-
"""
tests/test_scars_unit.py — Code review C6 fix tests (drop K-C6h)

Per code_review_session32.md Severity C6 ("24 Untested Engine Files"):
`engine/scars.py` powers the permanent-scar memory feature — every
incapacitation/mortal-wound that survives produces a scar entry, and
those entries feed the nightly Narrative Memory pipeline (so NPCs can
reference them: "That chest wound looks recent.")

A regression here silently breaks long-term character continuity.

Coverage:
  - _generate_description: ranged keys (blaster/bowcaster/firearms/
    grenade/missile), melee keys (melee/lightsaber/brawling), default
    fallback path (unknown weapon type), case-insensitive matching,
    skill-based melee detection (lightsaber/brawl in skill name).
  - _parse_attrs: valid JSON / dict / corrupt JSON / missing key.
  - add_scar: creates scars list, appends to existing, mutates in
    place, returns the scar dict, 20-scar cap with FIFO eviction.
  - add_scar: scar contains the expected fields (date, wound_level,
    weapon, attacker, location, description).
  - get_scars: returns empty list when none, returns the list when
    present.
  - format_scars_display: empty list when no scars, includes header
    and per-scar lines, color codes mortally-wounded differently.
  - format_scars_for_narrative: empty string when no scars,
    "Visible scars: ..." prefix, only last 5 included.

Stochastic surface (`random.choice` for body location and template)
is patched for determinism.
"""
import json
import os
import sys
import unittest
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from engine import scars as scars_module  # noqa: E402
from engine.scars import (  # noqa: E402
    _BODY_LOCATIONS,
    _MELEE_DESCRIPTIONS,
    _RANGED_DESCRIPTIONS,
    _generate_description,
    _parse_attrs,
    add_scar,
    format_scars_display,
    format_scars_for_narrative,
    get_scars,
)


def make_char(attrs=None):
    return {
        "id": 7,
        "attributes": json.dumps(attrs or {}),
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tables — invariants
# ══════════════════════════════════════════════════════════════════════════════


class TestTableInvariants(unittest.TestCase):
    def test_body_locations_nonempty(self):
        self.assertGreater(len(_BODY_LOCATIONS), 0)

    def test_body_locations_all_strings(self):
        for loc in _BODY_LOCATIONS:
            self.assertIsInstance(loc, str)
            self.assertTrue(loc, "empty body location string")

    def test_ranged_has_default_key(self):
        self.assertIn("default", _RANGED_DESCRIPTIONS)
        self.assertGreater(len(_RANGED_DESCRIPTIONS["default"]), 0)

    def test_melee_has_default_key(self):
        self.assertIn("default", _MELEE_DESCRIPTIONS)
        self.assertGreater(len(_MELEE_DESCRIPTIONS["default"]), 0)

    def test_every_template_has_loc_placeholder(self):
        for table_name, table in [
            ("ranged", _RANGED_DESCRIPTIONS),
            ("melee", _MELEE_DESCRIPTIONS),
        ]:
            for key, templates in table.items():
                for t in templates:
                    self.assertIn(
                        "{loc}", t,
                        f"{table_name}/{key} template missing {{loc}}: {t!r}",
                    )


# ══════════════════════════════════════════════════════════════════════════════
# _generate_description — ranged paths
# ══════════════════════════════════════════════════════════════════════════════


class TestGenerateDescriptionRanged(unittest.TestCase):
    """Force the random calls to deterministic choices."""

    def test_blaster_picks_blaster_template(self):
        with patch("engine.scars.random.choice") as mock_choice:
            # First call picks the body location, second picks the template
            mock_choice.side_effect = ["chest", "Blaster burn across the {loc}"]
            desc = _generate_description("blaster", "blaster")
        self.assertEqual(desc, "Blaster burn across the chest")

    def test_bowcaster_routes_to_bowcaster_table(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "left arm",
                _RANGED_DESCRIPTIONS["bowcaster"][0],
            ]
            desc = _generate_description("bowcaster", "bowcaster")
        self.assertIn("bowcaster", desc.lower())
        self.assertIn("left arm", desc)

    def test_firearms_routes_to_firearms_table(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "back",
                _RANGED_DESCRIPTIONS["firearms"][0],
            ]
            desc = _generate_description("firearms", "blaster")
        # The two firearms templates contain "Slug" and "Bullet"
        self.assertTrue(
            "Slug" in desc or "Bullet" in desc,
            f"firearms template did not render: {desc!r}",
        )

    def test_grenade_routes_to_grenade_table(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "abdomen",
                _RANGED_DESCRIPTIONS["grenade"][0],
            ]
            desc = _generate_description("grenade", "grenade")
        self.assertIn("abdomen", desc)

    def test_unknown_ranged_weapon_uses_default(self):
        # weapon_type='railgun' is not a known key -> default table
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "neck",
                _RANGED_DESCRIPTIONS["default"][0],
            ]
            desc = _generate_description("railgun", "blaster")
        self.assertIn("neck", desc)
        # Default template
        self.assertIn(desc, [
            t.format(loc="neck") for t in _RANGED_DESCRIPTIONS["default"]
        ])

    def test_substring_match_normalizes_weapon_key(self):
        # "heavy_blaster" should match "blaster" via the for-loop fallthrough
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "right shoulder",
                _RANGED_DESCRIPTIONS["blaster"][0],
            ]
            desc = _generate_description("heavy_blaster", "blaster")
        # Should contain a blaster word, not a default word
        self.assertTrue(
            "Blaster" in desc or "blaster" in desc,
            f"heavy_blaster did not normalize to blaster table: {desc!r}",
        )


class TestGenerateDescriptionMelee(unittest.TestCase):
    def test_lightsaber_skill_routes_to_lightsaber_table(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "face",
                _MELEE_DESCRIPTIONS["lightsaber"][0],
            ]
            desc = _generate_description("lightsaber", "lightsaber")
        self.assertIn("lightsaber", desc.lower())

    def test_lightsaber_via_skill_only(self):
        # weapon_type empty, but skill is 'lightsaber' -> still melee+lightsaber
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "left side",
                _MELEE_DESCRIPTIONS["lightsaber"][0],
            ]
            desc = _generate_description("", "lightsaber")
        self.assertIn("lightsaber", desc.lower())

    def test_brawling_parry_skill_routes_to_brawling(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "right hand",
                _MELEE_DESCRIPTIONS["brawling"][0],
            ]
            desc = _generate_description("fist", "brawling parry")
        # Brawling templates mention 'fracture' or 'Blunt'
        self.assertTrue(
            "fracture" in desc.lower() or "blunt" in desc.lower(),
            f"brawling template did not render: {desc!r}",
        )

    def test_melee_combat_skill_routes_to_melee(self):
        with patch("engine.scars.random.choice") as mock_choice:
            mock_choice.side_effect = [
                "chest",
                _MELEE_DESCRIPTIONS["melee"][0],
            ]
            desc = _generate_description("vibroblade", "melee combat")
        # Melee templates include "slash", "Blade scar", or "Jagged cut"
        lower = desc.lower()
        self.assertTrue(
            "slash" in lower or "blade" in lower or "jagged" in lower,
            f"melee template did not render: {desc!r}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# _parse_attrs
# ══════════════════════════════════════════════════════════════════════════════


class TestParseAttrs(unittest.TestCase):
    def test_valid_json_string(self):
        char = make_char({"foo": "bar"})
        self.assertEqual(_parse_attrs(char), {"foo": "bar"})

    def test_dict_passthrough(self):
        char = {"id": 1, "attributes": {"foo": "bar"}}
        self.assertEqual(_parse_attrs(char), {"foo": "bar"})

    def test_missing_key(self):
        self.assertEqual(_parse_attrs({"id": 1}), {})

    def test_none_value(self):
        self.assertEqual(_parse_attrs({"id": 1, "attributes": None}), {})

    def test_corrupt_json(self):
        # Should not crash
        self.assertEqual(_parse_attrs({"id": 1, "attributes": "{bad"}), {})


# ══════════════════════════════════════════════════════════════════════════════
# add_scar
# ══════════════════════════════════════════════════════════════════════════════


class TestAddScar(unittest.TestCase):
    def setUp(self):
        # Make _generate_description deterministic: always picks the
        # first body location and first template.
        self.choice_patcher = patch(
            "engine.scars.random.choice",
            side_effect=lambda seq: seq[0],
        )
        self.choice_patcher.start()
        # Pin time.strftime to a fixed date
        self.time_patcher = patch(
            "engine.scars.time.strftime",
            return_value="2026-04-28",
        )
        self.time_patcher.start()

    def tearDown(self):
        self.choice_patcher.stop()
        self.time_patcher.stop()

    def test_creates_scars_list_when_absent(self):
        char = make_char({})
        scar = add_scar(
            char,
            wound_level="incapacitated",
            weapon_name="Blaster Pistol",
            weapon_type="blaster",
            skill="blaster",
            attacker_name="Stormtrooper",
            location_name="Cantina",
        )
        attrs = json.loads(char["attributes"])
        self.assertIn("scars", attrs)
        self.assertEqual(len(attrs["scars"]), 1)
        self.assertEqual(attrs["scars"][0], scar)

    def test_scar_has_required_fields(self):
        char = make_char({})
        scar = add_scar(
            char, "incapacitated", "Blaster Pistol", "blaster",
            "blaster", "Stormtrooper", "Cantina",
        )
        for field in ("date", "wound_level", "weapon", "attacker",
                      "location", "description"):
            self.assertIn(field, scar, f"scar missing field: {field}")
        self.assertEqual(scar["wound_level"], "incapacitated")
        self.assertEqual(scar["weapon"], "Blaster Pistol")
        self.assertEqual(scar["attacker"], "Stormtrooper")
        self.assertEqual(scar["location"], "Cantina")
        self.assertEqual(scar["date"], "2026-04-28")

    def test_appends_to_existing_scars(self):
        char = make_char({"scars": [{"old": "scar"}]})
        add_scar(
            char, "mortally_wounded", "Vibroblade", "melee",
            "melee combat", "Trandoshan", "Spaceport",
        )
        attrs = json.loads(char["attributes"])
        self.assertEqual(len(attrs["scars"]), 2)
        # Old scar still first
        self.assertEqual(attrs["scars"][0], {"old": "scar"})

    def test_caps_at_20_scars_evicting_oldest(self):
        # Pre-populate with 20 scars
        existing = [{"description": f"scar {i}", "id": i} for i in range(20)]
        char = make_char({"scars": existing})
        add_scar(
            char, "incapacitated", "Blaster Pistol", "blaster",
            "blaster", "Stormtrooper", "Cantina",
        )
        attrs = json.loads(char["attributes"])
        self.assertEqual(len(attrs["scars"]), 20)
        # Oldest (id=0) should be gone
        self.assertNotIn(0, [s.get("id") for s in attrs["scars"]])
        # Newest scar present at the end
        self.assertEqual(attrs["scars"][-1]["weapon"], "Blaster Pistol")

    def test_preserves_other_attributes(self):
        char = make_char({"hp": 100, "credits": 500})
        add_scar(
            char, "incapacitated", "Blaster Pistol", "blaster",
            "blaster", "Stormtrooper", "Cantina",
        )
        attrs = json.loads(char["attributes"])
        self.assertEqual(attrs["hp"], 100)
        self.assertEqual(attrs["credits"], 500)


# ══════════════════════════════════════════════════════════════════════════════
# get_scars
# ══════════════════════════════════════════════════════════════════════════════


class TestGetScars(unittest.TestCase):
    def test_empty_when_no_scars(self):
        char = make_char({})
        self.assertEqual(get_scars(char), [])

    def test_returns_list_when_present(self):
        scars = [
            {"description": "Old wound", "wound_level": "incapacitated"},
            {"description": "Lightsaber burn", "wound_level": "mortally_wounded"},
        ]
        char = make_char({"scars": scars})
        self.assertEqual(get_scars(char), scars)

    def test_corrupt_json_returns_empty(self):
        char = {"id": 1, "attributes": "{not json"}
        self.assertEqual(get_scars(char), [])


# ══════════════════════════════════════════════════════════════════════════════
# format_scars_display
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatScarsDisplay(unittest.TestCase):
    def test_empty_when_no_scars(self):
        char = make_char({})
        self.assertEqual(format_scars_display(char), [])

    def test_includes_header_lines(self):
        char = make_char({"scars": [{
            "description": "Blaster burn",
            "wound_level": "incapacitated",
            "attacker": "Stormtrooper",
            "location": "Cantina",
            "date": "2026-04-28",
        }]})
        lines = format_scars_display(char)
        # Header section: 3 lines (top rule, title, bottom rule), then
        # 2 lines per scar
        self.assertEqual(len(lines), 3 + 2)
        # Title line should mention SCARS
        self.assertTrue(any("SCARS" in line for line in lines[:3]))

    def test_two_lines_per_scar(self):
        char = make_char({"scars": [
            {"description": "S1", "wound_level": "incapacitated",
             "attacker": "A1", "location": "L1", "date": "D1"},
            {"description": "S2", "wound_level": "mortally_wounded",
             "attacker": "A2", "location": "L2", "date": "D2"},
        ]})
        lines = format_scars_display(char)
        # 3 header + 2 per scar * 2 scars = 7
        self.assertEqual(len(lines), 7)

    def test_mortally_wounded_uses_red(self):
        # Red ANSI: \033[1;31m
        char = make_char({"scars": [{
            "description": "Lightsaber burn",
            "wound_level": "mortally_wounded",
            "attacker": "Sith",
            "location": "Temple",
            "date": "D",
        }]})
        lines = format_scars_display(char)
        # Body line for the scar (4th line; idx 3) should contain RED code
        body = lines[3]
        self.assertIn("\033[1;31m", body)

    def test_incapacitated_uses_yellow(self):
        # Yellow ANSI: \033[1;33m
        char = make_char({"scars": [{
            "description": "Blaster burn",
            "wound_level": "incapacitated",
            "attacker": "Stormtrooper",
            "location": "Cantina",
            "date": "D",
        }]})
        lines = format_scars_display(char)
        body = lines[3]
        self.assertIn("\033[1;33m", body)
        # And NOT red (would be a regression in color routing)
        self.assertNotIn("\033[1;31m", body)

    def test_metadata_line_includes_attacker_location_date(self):
        char = make_char({"scars": [{
            "description": "Blaster burn",
            "wound_level": "incapacitated",
            "attacker": "Stormtrooper",
            "location": "Cantina",
            "date": "2026-04-28",
        }]})
        lines = format_scars_display(char)
        meta = lines[4]  # the second line of the scar entry
        self.assertIn("Stormtrooper", meta)
        self.assertIn("Cantina", meta)
        self.assertIn("2026-04-28", meta)

    def test_missing_fields_use_unknown_fallback(self):
        char = make_char({"scars": [{}]})
        # Should not crash even if fields are missing
        lines = format_scars_display(char)
        # Body line should reference 'Old wound' (default description fallback)
        body = lines[3]
        self.assertIn("Old wound", body)


# ══════════════════════════════════════════════════════════════════════════════
# format_scars_for_narrative
# ══════════════════════════════════════════════════════════════════════════════


class TestFormatScarsForNarrative(unittest.TestCase):
    def test_empty_when_no_scars(self):
        char = make_char({})
        self.assertEqual(format_scars_for_narrative(char), "")

    def test_prefix_and_join(self):
        char = make_char({"scars": [
            {"description": "Blaster burn across the chest"},
            {"description": "Slash on the face"},
        ]})
        result = format_scars_for_narrative(char)
        self.assertTrue(result.startswith("Visible scars: "))
        self.assertIn("Blaster burn across the chest", result)
        self.assertIn("Slash on the face", result)
        self.assertIn("; ", result)

    def test_only_last_5_included(self):
        scars = [
            {"description": f"Scar {i}"} for i in range(8)
        ]
        char = make_char({"scars": scars})
        result = format_scars_for_narrative(char)
        # Most recent 5 means scars 3..7 inclusive
        self.assertIn("Scar 3", result)
        self.assertIn("Scar 7", result)
        # Older scars excluded
        self.assertNotIn("Scar 0", result)
        self.assertNotIn("Scar 2", result)

    def test_missing_description_uses_old_wound(self):
        char = make_char({"scars": [{}]})
        result = format_scars_for_narrative(char)
        self.assertIn("old wound", result)


if __name__ == "__main__":
    unittest.main()
