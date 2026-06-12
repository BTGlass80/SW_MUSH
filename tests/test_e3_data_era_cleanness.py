# -*- coding: utf-8 -*-
"""
tests/test_e3_data_era_cleanness.py

B3 era-cleanness guard for the clone_wars production *data* slice swept on
2026-06-05 (T2.CW.codebase_era_sweep). Three player-facing leaks were fixed:

  1. zones.yaml geonosis_petranaki narrative_tone — "Death Star plans" (a
     proper noun from the future) softened to "superweapon schematics".
     The Geonosian-superweapon reference itself is era-accurate deep canon
     (~22 BBY) and is kept; only the anachronistic name is removed.
  2. tutorials/rooms.yaml Smugglers' Alley — a leaked "Imperial — well,
     Republic" slip a 20 BBY vendor could not make, cut to "Republic patrols".
  3. planets/coruscant.yaml Opera House short_desc — "Imperial City" (the
     GCW-era name for Galactic City) fixed to "Galactic City".

This guard asserts the player-facing string VALUES in the three touched files
carry no GCW proper nouns, while deliberately NOT flagging the legitimate
era-mapping keys (`imperial: republic`), `replaces:` rewicker metadata,
"no Empire" disclaimers in comments, or lowercase "rebellion" (= the CIS
secession). The sanctioned dark-future-self prophecy lives in engine/
village_trials.py, not data, and is out of scope here.
"""
from __future__ import annotations

import os
import re
import unittest

import yaml

_CW = os.path.join("data", "worlds", "clone_wars")
_ZONES = os.path.join(_CW, "zones.yaml")
_ROOMS = os.path.join(_CW, "tutorials", "rooms.yaml")
_CORUSCANT = os.path.join(_CW, "planets", "coruscant.yaml")

# Proper nouns that must never appear in player-facing data strings.
_FORBIDDEN = re.compile(
    r"\b(death star|imperial city|stormtrooper|x-wing|tie fighter|"
    r"tie interceptor|moff|the empire|imperial navy|rebel alliance)\b",
    re.IGNORECASE,
)

# Keys whose VALUES are shown to players (the strings B3 governs).
_PLAYER_FACING_KEYS = ("short_desc", "description", "narrative_tone",
                       "name", "long_desc", "text")


def _player_facing_strings(obj):
    """Yield every player-facing string value in a loaded YAML structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str) and k in _PLAYER_FACING_KEYS:
                yield v
            else:
                yield from _player_facing_strings(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _player_facing_strings(it)


class TestDataEraCleanness(unittest.TestCase):

    def _scan(self, path):
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        hits = []
        for s in _player_facing_strings(data):
            m = _FORBIDDEN.search(s)
            if m:
                hits.append((m.group(0), s[:80]))
        return hits

    def test_zones_no_forbidden_proper_nouns(self):
        self.assertEqual(self._scan(_ZONES), [],
                         "GCW proper noun in zones.yaml player-facing text")

    def test_tutorial_rooms_no_forbidden_proper_nouns(self):
        self.assertEqual(self._scan(_ROOMS), [],
                         "GCW proper noun in tutorials/rooms.yaml")

    def test_coruscant_no_forbidden_proper_nouns(self):
        self.assertEqual(self._scan(_CORUSCANT), [],
                         "GCW proper noun in coruscant.yaml player-facing text")

    # Specific regression pins for the three fixed lines.
    def test_specific_fixes_applied(self):
        z = open(_ZONES, encoding="utf-8").read()
        self.assertNotIn("Death Star", z)
        self.assertIn("superweapon schematics", z)  # Geonosian canon kept

        r = open(_ROOMS, encoding="utf-8").read()
        self.assertNotIn("Imperial — well", r)
        self.assertIn("for Republic\n      patrols", r)

        c = open(_CORUSCANT, encoding="utf-8").read()
        self.assertNotIn("Imperial City", c)
        self.assertIn("Galactic City", c)

    # Confirm the legitimate era-mapping keys are NOT disturbed by the sweep
    # (these are infrastructure, not player-facing strings).
    def test_era_mapping_keys_preserved(self):
        org = open(os.path.join(_CW, "organizations.yaml"), encoding="utf-8").read()
        self.assertIn("empire:", org)  # GCW->CW archetype mapping key intact


if __name__ == "__main__":
    unittest.main()
