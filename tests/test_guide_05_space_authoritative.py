# -*- coding: utf-8 -*-
"""
Authoritative cross-check guard for Guide_05_Space_Systems.md (Opus quality pass,
2026-06-23).

The June space rework re-graphed the galaxy (6 planets / 28 zones, Corellia +
Kessel removed) and re-priced trade (source 70% / demand 140%), and the CW ship
registry excludes the post-CW hulls. An older guide draft documented the dead
4-planet / 3-lane galaxy, the 50%/200% trade table, and two excluded ships
(B-Wing, Nebulon-B). This guard pins the guide to the live engine so it can't
silently rot back.

Pure cross-check: imports the live trade + ship's-log data and parses the
space-zone + starship YAML directly. No DB, no server.
"""

import os
import re
import sys
import unittest

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

GUIDE_PATH = os.path.join(PROJECT_ROOT, "data", "guides", "Guide_05_Space_Systems.md")
ZONES_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "space_zones.yaml")
BASE_SHIPS_PATH = os.path.join(PROJECT_ROOT, "data", "starships.yaml")
ERA_SHIPS_PATH = os.path.join(PROJECT_ROOT, "data", "worlds", "clone_wars", "starships.yaml")


def _load(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


class TestGuide05Galaxy(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE_PATH)
        cls.body_lc = cls.body.lower()

    def test_file_exists(self):
        self.assertTrue(os.path.exists(GUIDE_PATH))

    def test_all_six_live_planets_documented(self):
        zones = _yaml(ZONES_PATH)["zones"]
        planets = sorted({z["planet"] for z in zones.values() if z.get("planet")})
        # Live graph: 6 planets.
        self.assertEqual(len(planets), 6, f"expected 6 planets, got {planets}")
        alias = {"nar_shaddaa": "nar shaddaa"}
        for p in planets:
            needle = alias.get(p, p).replace("_", " ")
            self.assertIn(needle, self.body_lc,
                          f"planet '{p}' missing from guide")

    def test_dead_planets_not_documented(self):
        """Corellia + Kessel were dropped from the space graph; they must not be
        documented as live planets/trade worlds. (Corellian Run the *lane* may
        still appear — only the bare planet words are forbidden in tables.)"""
        zones = _yaml(ZONES_PATH)["zones"]
        live = {z["planet"] for z in zones.values() if z.get("planet")}
        self.assertNotIn("kessel", live)  # sanity: still gone from the graph
        # Kessel never appears at all in the new guide.
        self.assertNotIn("kessel", self.body_lc)


class TestGuide05Trade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE_PATH)

    def test_price_multipliers_match_engine(self):
        import engine.trading as t
        self.assertEqual(t.PRICE_SOURCE, 0.70)
        self.assertEqual(t.PRICE_DEMAND, 1.40)
        # Guide must state the live multipliers, not the dead 50%/200%.
        self.assertIn("70%", self.body)
        self.assertIn("140%", self.body)
        self.assertNotIn("50%", self.body)
        self.assertNotIn("200%", self.body)

    def test_all_eight_goods_named(self):
        import engine.trading as t
        goods = list(t.TRADE_GOODS.values())
        self.assertEqual(len(goods), 8)
        for g in goods:
            self.assertIn(g.name, self.body, f"trade good '{g.name}' missing")


class TestGuide05Ships(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE_PATH)

    # Generic hull-class terms shared by an excluded ship AND a valid CW ship.
    # "Star Destroyer" is the Imperial-class *and* the Republic Venator — the
    # Venator is a legitimate CW hull, so the bare class term is allowed.
    _GENERIC_CLASS_TERMS = {"Star Destroyer"}

    def test_excluded_hulls_not_documented(self):
        """No CW-excluded hull's distinctive display name may appear in the
        guide. Generic hull-class terms (see _GENERIC_CLASS_TERMS) are exempt
        because a valid CW ship shares them."""
        era = _yaml(ERA_SHIPS_PATH)
        excluded = set(era["registry_hints"]["excluded_global_keys"])
        base = _yaml(BASE_SHIPS_PATH)
        offenders = []
        for key in excluded:
            entry = base.get(key)
            if not isinstance(entry, dict):
                continue
            for field in ("name", "nickname"):
                val = entry.get(field)
                if val and val in self.body and val not in self._GENERIC_CLASS_TERMS:
                    offenders.append((key, field, val))
        self.assertFalse(offenders, f"excluded hulls documented: {offenders}")

    def test_specific_phantom_hulls_absent(self):
        """The two phantoms the old draft documented are gone."""
        self.assertNotIn("B-Wing", self.body)
        self.assertNotIn("Nebulon-B", self.body)

    def test_real_cw_overlay_hulls_documented(self):
        """A representative set of the CW overlay ships must be present."""
        for name in ("ARC-170", "Eta-2 Actis", "Vulture Droid", "Venator",
                     "Acclamator", "LAAT", "Tri-Fighter"):
            self.assertIn(name, self.body, f"CW ship '{name}' missing from guide")


class TestGuide05Titles(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE_PATH)

    def test_titles_match_ships_log(self):
        import engine.ships_log as s
        for m in s.MILESTONES:
            if not m.get("title"):
                continue
            self.assertIn(m["title"], self.body,
                          f"title '{m['title']}' missing")
            # The CP value for the titled threshold must be in the table.
            self.assertRegex(
                self.body,
                rf"{re.escape(m['title'])}.*\|\s*{m['cp']}\s*\|",
                f"title '{m['title']}' CP {m['cp']} not in titles table",
            )


class TestGuide05Commands(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.body = _load(GUIDE_PATH)

    def test_ship_umbrella_switches_documented(self):
        for sw in ("+ship/list", "+ship/info", "+ship/mine", "+ship/install",
                   "+ship/uninstall", "+ship/mods", "+ship/repair"):
            self.assertIn(sw, self.body, f"switch '{sw}' missing from guide")

    def test_no_plus_spawn_phantom(self):
        """The admin spawn verb is @spawn, not +spawn."""
        self.assertNotIn("+spawn", self.body)
        self.assertIn("@spawn", self.body)


if __name__ == "__main__":
    unittest.main()
