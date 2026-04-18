# -*- coding: utf-8 -*-
"""
tests/test_session58_cleanup_umbrellas.py -- Session 58 feature tests

S58 completes the rename sweep — final cleanup of small modules:

  +shop     (shop_commands)     — forwarding umbrella (13 subcommands)
  +place    (places_commands)   — leaf umbrella (3 switches, admin stays @)
  +spy      (espionage_commands) — leaf umbrella (5 switches)
  +medical  (medical_commands)  — leaf umbrella (3 switches)
  +home     (housing_commands)  — forwarding umbrella (16 subcommands)
  +faction  (faction_commands)  — forwarding umbrella (17+ subcommands)
  +perform  (entertainer_commands) — single-alias add (no umbrella class)
  +sabacc   (sabacc_commands)   — single-alias add (no umbrella class)

S58 introduces the FORWARDING PATTERN for umbrellas whose default-switch
target uses positional-subcommand parsing (FactionCommand, ShopCommand,
HousingCommand). Unknown switches are forwarded to the default class
with the switch name prepended to ctx.args. Verified below.
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. +shop umbrella (forwarding)
# ══════════════════════════════════════════════════════════════════════════════

class TestShopUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.shop_commands import ShopUmbrellaCommand
        self.assertEqual(ShopUmbrellaCommand.key, "+shop")

    def test_valid_switches_includes_forwarding(self):
        """Shop forwarding umbrella must list ShopCommand subcommands."""
        from parser.shop_commands import ShopUmbrellaCommand
        for sw in ["buy", "place", "stock", "collect", "sales"]:
            self.assertIn(sw, ShopUmbrellaCommand.valid_switches)

    def test_shop_command_alias_trimmed(self):
        """ShopCommand.aliases no longer contains +shop — the umbrella claims it."""
        from parser.shop_commands import ShopCommand
        self.assertNotIn("+shop", ShopCommand.aliases)

    def test_switch_impl_populated(self):
        from parser.shop_commands import _SHOP_SWITCH_IMPL
        self.assertEqual(set(_SHOP_SWITCH_IMPL.keys()),
                         {"shop", "browse", "market", "admin"})


class TestShopHelpFile(unittest.TestCase):
    def test_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+shop"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        self.assertGreater(len(e.body), 1500)
        self.assertGreater(len(e.examples), 10)


# ══════════════════════════════════════════════════════════════════════════════
# 2. +place umbrella (leaf, no admin)
# ══════════════════════════════════════════════════════════════════════════════

class TestPlaceUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.places_commands import PlaceUmbrellaCommand
        self.assertEqual(PlaceUmbrellaCommand.key, "+place")

    def test_valid_switches_are_player_only(self):
        """Admin switches (config, set, osucc, ofail, odrop) are NOT
        folded into +place — they stay at their @-prefix native form."""
        from parser.places_commands import PlaceUmbrellaCommand
        self.assertEqual(set(PlaceUmbrellaCommand.valid_switches),
                         {"view", "join", "depart"})

    def test_aliases_cover_bare_verbs(self):
        from parser.places_commands import PlaceUmbrellaCommand
        required = {"places", "place", "join", "sit", "depart", "stand"}
        self.assertFalse(required - set(PlaceUmbrellaCommand.aliases))

    def test_switch_impl_populated(self):
        from parser.places_commands import _PLACE_SWITCH_IMPL
        self.assertEqual(set(_PLACE_SWITCH_IMPL.keys()),
                         {"view", "join", "depart"})


class TestPlaceAdminStaysBare(unittest.TestCase):
    """Admin place commands (@places, @place, etc.) stay at @-prefix."""
    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.places_commands import register_places_commands
        r = CommandRegistry()
        register_places_commands(r)
        return r

    def test_at_places_still_reaches_admin_class(self):
        from parser.places_commands import ConfigPlacesCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("@places"), ConfigPlacesCommand)

    def test_at_place_still_reaches_admin_class(self):
        from parser.places_commands import SetPlaceCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("@place"), SetPlaceCommand)

    def test_tt_mutter_stay_bare(self):
        """RP shortcuts tt, ttooc, mutter must still resolve."""
        r = self._build_registry()
        self.assertIsNotNone(r.get("tt"))
        self.assertIsNotNone(r.get("ttooc"))
        self.assertIsNotNone(r.get("mutter"))


class TestPlaceHelpFile(unittest.TestCase):
    def test_loads_and_documents_no_admin(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+place"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        # Body should explain admin stays at @-prefix
        self.assertIn("@place", e.body)


# ══════════════════════════════════════════════════════════════════════════════
# 3. +spy umbrella (leaf)
# ══════════════════════════════════════════════════════════════════════════════

class TestSpyUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.espionage_commands import SpyCommand
        self.assertEqual(SpyCommand.key, "+spy")

    def test_valid_switches(self):
        from parser.espionage_commands import SpyCommand
        required = {"assess", "eavesdrop", "investigate", "intel", "intercept"}
        self.assertFalse(required - set(SpyCommand.valid_switches))

    def test_aliases_cover_bare_verbs(self):
        from parser.espionage_commands import SpyCommand
        required = {"assess", "size", "eavesdrop", "listen",
                    "investigate", "search", "inspect",
                    "intel", "intercept", "wiretap", "comtap"}
        self.assertFalse(required - set(SpyCommand.aliases))

    def test_alias_map_covers_aliases(self):
        from parser.espionage_commands import SpyCommand, _SPY_ALIAS_TO_SWITCH
        for alias in SpyCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _SPY_ALIAS_TO_SWITCH,
                          f"alias '{alias}' not in map")

    def test_switch_impl_populated(self):
        from parser.espionage_commands import _SPY_SWITCH_IMPL
        self.assertEqual(set(_SPY_SWITCH_IMPL.keys()),
                         {"assess", "eavesdrop", "investigate",
                          "intel", "intercept"})


class TestSpyHelpFile(unittest.TestCase):
    def test_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+spy"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        self.assertGreater(len(e.body), 2000)
        self.assertGreater(len(e.examples), 12)


# ══════════════════════════════════════════════════════════════════════════════
# 4. +medical umbrella (leaf)
# ══════════════════════════════════════════════════════════════════════════════

class TestMedicalUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.medical_commands import MedicalCommand
        self.assertEqual(MedicalCommand.key, "+medical")

    def test_valid_switches(self):
        from parser.medical_commands import MedicalCommand
        self.assertEqual(set(MedicalCommand.valid_switches),
                         {"heal", "accept", "rate"})

    def test_aliases_cover_bare_verbs(self):
        from parser.medical_commands import MedicalCommand
        required = {"heal", "healaccept", "haccept", "healrate", "hrate"}
        self.assertFalse(required - set(MedicalCommand.aliases))

    def test_switch_impl_populated(self):
        from parser.medical_commands import _MEDICAL_SWITCH_IMPL
        self.assertEqual(set(_MEDICAL_SWITCH_IMPL.keys()),
                         {"heal", "accept", "rate"})


class TestMedicalHelpFile(unittest.TestCase):
    def test_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+medical"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        self.assertGreater(len(e.body), 1500)


# ══════════════════════════════════════════════════════════════════════════════
# 5. +home umbrella (forwarding)
# ══════════════════════════════════════════════════════════════════════════════

class TestHomeUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.housing_commands import HomeUmbrellaCommand
        self.assertEqual(HomeUmbrellaCommand.key, "+home")

    def test_valid_switches_includes_forwarding(self):
        """Home forwarding umbrella must list HousingCommand subcommands."""
        from parser.housing_commands import HomeUmbrellaCommand
        for sw in ["view", "sethome", "rent", "storage", "trophy",
                   "shopfront", "guest", "visit"]:
            self.assertIn(sw, HomeUmbrellaCommand.valid_switches)

    def test_housing_command_alias_trimmed(self):
        """HousingCommand.aliases no longer contains 'home' — umbrella owns it."""
        from parser.housing_commands import HousingCommand
        self.assertNotIn("home", HousingCommand.aliases)

    def test_switch_impl_populated(self):
        from parser.housing_commands import _HOME_SWITCH_IMPL
        self.assertEqual(set(_HOME_SWITCH_IMPL.keys()),
                         {"view", "sethome", "admin"})


class TestHomeHelpFile(unittest.TestCase):
    def test_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+home"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        self.assertGreater(len(e.body), 2000)
        self.assertGreater(len(e.examples), 12)


# ══════════════════════════════════════════════════════════════════════════════
# 6. +faction umbrella (forwarding)
# ══════════════════════════════════════════════════════════════════════════════

class TestFactionUmbrella(unittest.TestCase):
    def test_class_exists(self):
        from parser.faction_commands import FactionUmbrellaCommand
        self.assertEqual(FactionUmbrellaCommand.key, "+faction")

    def test_valid_switches_includes_forwarding(self):
        """Faction forwarding umbrella must list FactionCommand subcommands."""
        from parser.faction_commands import FactionUmbrellaCommand
        for sw in ["view", "guild", "specialize", "reputation",
                   "list", "join", "leave", "roster", "missions",
                   "claim", "hq"]:
            self.assertIn(sw, FactionUmbrellaCommand.valid_switches)

    def test_faction_command_alias_trimmed(self):
        """FactionCommand.aliases no longer contains +faction."""
        from parser.faction_commands import FactionCommand
        self.assertNotIn("+faction", FactionCommand.aliases)

    def test_switch_impl_populated(self):
        from parser.faction_commands import _FACTION_SWITCH_IMPL
        self.assertEqual(set(_FACTION_SWITCH_IMPL.keys()),
                         {"view", "guild", "specialize", "reputation"})


class TestFactionHelpFile(unittest.TestCase):
    def test_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+faction"]
        self.assertEqual(len(matching), 1)
        e = matching[0]
        self.assertGreater(len(e.body), 3000)
        self.assertGreater(len(e.examples), 15)


# ══════════════════════════════════════════════════════════════════════════════
# 7. +perform / +sabacc (single-action — no umbrella, just alias)
# ══════════════════════════════════════════════════════════════════════════════

class TestPerformAliasOnly(unittest.TestCase):
    def test_perform_command_has_plus_alias(self):
        from parser.entertainer_commands import PerformCommand
        self.assertIn("+perform", PerformCommand.aliases)

    def test_perform_legacy_aliases_preserved(self):
        from parser.entertainer_commands import PerformCommand
        for alias in ("entertain", "play"):
            self.assertIn(alias, PerformCommand.aliases)

    def test_perform_helpfile_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+perform"]
        self.assertEqual(len(matching), 1)


class TestSabaccAliasOnly(unittest.TestCase):
    def test_sabacc_command_has_plus_alias(self):
        from parser.sabacc_commands import SabaccCommand
        self.assertIn("+sabacc", SabaccCommand.aliases)

    def test_sabacc_legacy_aliases_preserved(self):
        from parser.sabacc_commands import SabaccCommand
        for alias in ("gamble", "cards"):
            self.assertIn(alias, SabaccCommand.aliases)

    def test_sabacc_helpfile_loads(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+sabacc"]
        self.assertEqual(len(matching), 1)


# ══════════════════════════════════════════════════════════════════════════════
# 8. Cross-module: all 20 umbrellas resolve (S54+S55+S56+S57a+S57b+S58)
# ══════════════════════════════════════════════════════════════════════════════

class TestAllTwentyUmbrellasRegister(unittest.TestCase):
    """The COMPLETE umbrella set after the rename sweep.

    Counting method:
      - 12 "full umbrella class" umbrellas: +combat (S54) + +mission,
        +smuggle, +bounty, +quest (S55) + +craft, +crew (S56) + +ship
        (S57a) + +pilot, +gunner, +sensors, +bridge (S57b)
      - 6 full umbrella classes in S58: +shop, +place, +spy, +medical,
        +home, +faction
      - 2 single-action alias-adds (no umbrella class): +perform,
        +sabacc — resolve via regular alias lookup
      TOTAL: 20 canonical +verb forms
    """

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.combat_commands import register_combat_commands
        from parser.mission_commands import register_mission_commands
        from parser.smuggling_commands import register_smuggling_commands
        from parser.bounty_commands import register_bounty_commands
        from parser.narrative_commands import register_narrative_commands
        from parser.crafting_commands import register_crafting_commands
        from parser.crew_commands import register_crew_commands
        from parser.space_commands import register_space_commands
        from parser.shop_commands import register_shop_commands
        from parser.places_commands import register_places_commands
        from parser.espionage_commands import register_espionage_commands
        from parser.medical_commands import register_medical_commands
        from parser.housing_commands import register_housing_commands
        from parser.faction_commands import register_faction_commands
        from parser.entertainer_commands import register_entertainer_commands
        from parser.sabacc_commands import register_sabacc_commands

        r = CommandRegistry()
        register_combat_commands(r)
        register_space_commands(r)
        register_crew_commands(r)
        register_mission_commands(r)
        register_bounty_commands(r)
        register_smuggling_commands(r)
        register_crafting_commands(r)
        register_narrative_commands(r)
        register_shop_commands(r)
        register_places_commands(r)
        register_espionage_commands(r)
        register_medical_commands(r)
        register_housing_commands(r)
        register_faction_commands(r)
        register_entertainer_commands(r)
        register_sabacc_commands(r)
        return r

    def test_all_twenty_plus_verb_keys_resolve(self):
        """Every +verb canonical key must resolve to SOME command class."""
        r = self._build_registry()
        for key in [
            # S54–S57
            "+combat", "+mission", "+smuggle", "+bounty", "+quest",
            "+craft", "+crew", "+ship", "+pilot", "+gunner",
            "+sensors", "+bridge",
            # S58
            "+shop", "+place", "+spy", "+medical", "+home", "+faction",
            "+perform", "+sabacc",
        ]:
            cmd = r.get(key)
            self.assertIsNotNone(cmd, f"+verb key '{key}' does not resolve")

    def test_s58_umbrella_classes_resolve_to_right_types(self):
        from parser.shop_commands import ShopUmbrellaCommand
        from parser.places_commands import PlaceUmbrellaCommand
        from parser.espionage_commands import SpyCommand
        from parser.medical_commands import MedicalCommand
        from parser.housing_commands import HomeUmbrellaCommand
        from parser.faction_commands import FactionUmbrellaCommand
        from parser.entertainer_commands import PerformCommand
        from parser.sabacc_commands import SabaccCommand

        r = self._build_registry()
        self.assertIsInstance(r.get("+shop"), ShopUmbrellaCommand)
        self.assertIsInstance(r.get("+place"), PlaceUmbrellaCommand)
        self.assertIsInstance(r.get("+spy"), SpyCommand)
        self.assertIsInstance(r.get("+medical"), MedicalCommand)
        self.assertIsInstance(r.get("+home"), HomeUmbrellaCommand)
        self.assertIsInstance(r.get("+faction"), FactionUmbrellaCommand)
        # +perform and +sabacc resolve to their single-action classes via alias
        self.assertIsInstance(r.get("+perform"), PerformCommand)
        self.assertIsInstance(r.get("+sabacc"), SabaccCommand)

    def test_bare_home_routes_via_umbrella(self):
        """S58 moved `home` from HousingCommand to the umbrella."""
        from parser.housing_commands import HomeUmbrellaCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("home"), HomeUmbrellaCommand)

    def test_bare_housing_still_routes_to_housing_command(self):
        """Bare 'housing' still reaches HousingCommand (its own key)."""
        from parser.housing_commands import HousingCommand
        r = self._build_registry()
        self.assertIsInstance(r.get("housing"), HousingCommand)

    def test_s58_rp_shortcuts_stay_bare(self):
        """tt, ttooc, mutter are NOT folded into +place."""
        r = self._build_registry()
        for alias in ("tt", "ttooc", "mutter", "mu"):
            cmd = r.get(alias)
            self.assertIsNotNone(cmd, f"Bare RP shortcut '{alias}' lost")

    def test_s58_admin_commands_stay_at_prefix(self):
        """@-prefix admin commands NOT folded into umbrellas."""
        r = self._build_registry()
        for key in ("@places", "@place", "@osucc", "@ofail", "@odrop",
                    "@housing", "@shop"):
            cmd = r.get(key)
            self.assertIsNotNone(cmd, f"Admin command '{key}' lost")


if __name__ == "__main__":
    unittest.main()
