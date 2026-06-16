# -*- coding: utf-8 -*-
"""
tests/test_help_leadership_force_misc.py — help-corpus completeness batch 7.

Verifies that sixteen newly-added help files load cleanly and carry the
expected frontmatter:

  data/help/commands/+lead.md          — lead a combined action
  data/help/commands/+joinlead.md      — join a combined action
  data/help/commands/+plots.md         — list story arcs / plots
  data/help/commands/+region.md        — wilderness region info
  data/help/commands/+commissary.md    — faction gear requisition
  data/help/commands/+credits.md       — credit balance check
  data/help/commands/+rpprefs.md       — RP preferences
  data/help/commands/+recap.md         — narrative recap
  data/help/commands/+quests.md        — personal quests list
  data/help/commands/+intel.md         — intelligence reports
  data/help/commands/+roster.md        — crew roster
  data/help/commands/+pvp.md           — PvP flag toggle
  data/help/commands/+powers.md        — Force powers list
  data/help/commands/+forcestatus.md   — Force status sheet
  data/help/commands/+meditate.md      — Jedi meditation
  data/help/commands/+title.md         — decorative character titles
"""

from __future__ import annotations

import os
import unittest

from data.help_topics import HelpEntry
from engine.help_loader import load_help_file

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.dirname(_HERE)
_CMD_DIR = os.path.join(_REPO_ROOT, "data", "help", "commands")

_LEAD_PATH        = os.path.join(_CMD_DIR, "+lead.md")
_JOINLEAD_PATH    = os.path.join(_CMD_DIR, "+joinlead.md")
_PLOTS_PATH       = os.path.join(_CMD_DIR, "+plots.md")
_REGION_PATH      = os.path.join(_CMD_DIR, "+region.md")
_COMMISSARY_PATH  = os.path.join(_CMD_DIR, "+commissary.md")
_CREDITS_PATH     = os.path.join(_CMD_DIR, "+credits.md")
_RPPREFS_PATH     = os.path.join(_CMD_DIR, "+rpprefs.md")
_RECAP_PATH       = os.path.join(_CMD_DIR, "+recap.md")
_QUESTS_PATH      = os.path.join(_CMD_DIR, "+quests.md")
_INTEL_PATH       = os.path.join(_CMD_DIR, "+intel.md")
_ROSTER_PATH      = os.path.join(_CMD_DIR, "+roster.md")
_PVP_PATH         = os.path.join(_CMD_DIR, "+pvp.md")
_POWERS_PATH      = os.path.join(_CMD_DIR, "+powers.md")
_FORCESTATUS_PATH = os.path.join(_CMD_DIR, "+forcestatus.md")
_MEDITATE_PATH    = os.path.join(_CMD_DIR, "+meditate.md")
_TITLE_PATH       = os.path.join(_CMD_DIR, "+title.md")

_ALL_PATHS = [
    _LEAD_PATH, _JOINLEAD_PATH, _PLOTS_PATH, _REGION_PATH,
    _COMMISSARY_PATH, _CREDITS_PATH, _RPPREFS_PATH, _RECAP_PATH,
    _QUESTS_PATH, _INTEL_PATH, _ROSTER_PATH, _PVP_PATH,
    _POWERS_PATH, _FORCESTATUS_PATH, _MEDITATE_PATH, _TITLE_PATH,
]


def _load(path: str) -> HelpEntry:
    entry = load_help_file(path, HelpEntry)
    assert entry is not None, f"load_help_file returned None for {path}"
    return entry


# ═══════════════════════════════════════════════════════════════════════════
# 1.  Files exist on disk
# ═══════════════════════════════════════════════════════════════════════════

class TestHelpFilesExist(unittest.TestCase):
    def test_lead_exists(self):
        self.assertTrue(os.path.isfile(_LEAD_PATH), f"Missing: {_LEAD_PATH}")

    def test_joinlead_exists(self):
        self.assertTrue(os.path.isfile(_JOINLEAD_PATH), f"Missing: {_JOINLEAD_PATH}")

    def test_plots_exists(self):
        self.assertTrue(os.path.isfile(_PLOTS_PATH), f"Missing: {_PLOTS_PATH}")

    def test_region_exists(self):
        self.assertTrue(os.path.isfile(_REGION_PATH), f"Missing: {_REGION_PATH}")

    def test_commissary_exists(self):
        self.assertTrue(os.path.isfile(_COMMISSARY_PATH), f"Missing: {_COMMISSARY_PATH}")

    def test_credits_exists(self):
        self.assertTrue(os.path.isfile(_CREDITS_PATH), f"Missing: {_CREDITS_PATH}")

    def test_rpprefs_exists(self):
        self.assertTrue(os.path.isfile(_RPPREFS_PATH), f"Missing: {_RPPREFS_PATH}")

    def test_recap_exists(self):
        self.assertTrue(os.path.isfile(_RECAP_PATH), f"Missing: {_RECAP_PATH}")

    def test_quests_exists(self):
        self.assertTrue(os.path.isfile(_QUESTS_PATH), f"Missing: {_QUESTS_PATH}")

    def test_intel_exists(self):
        self.assertTrue(os.path.isfile(_INTEL_PATH), f"Missing: {_INTEL_PATH}")

    def test_roster_exists(self):
        self.assertTrue(os.path.isfile(_ROSTER_PATH), f"Missing: {_ROSTER_PATH}")

    def test_pvp_exists(self):
        self.assertTrue(os.path.isfile(_PVP_PATH), f"Missing: {_PVP_PATH}")

    def test_powers_exists(self):
        self.assertTrue(os.path.isfile(_POWERS_PATH), f"Missing: {_POWERS_PATH}")

    def test_forcestatus_exists(self):
        self.assertTrue(os.path.isfile(_FORCESTATUS_PATH), f"Missing: {_FORCESTATUS_PATH}")

    def test_meditate_exists(self):
        self.assertTrue(os.path.isfile(_MEDITATE_PATH), f"Missing: {_MEDITATE_PATH}")

    def test_title_exists(self):
        self.assertTrue(os.path.isfile(_TITLE_PATH), f"Missing: {_TITLE_PATH}")


# ═══════════════════════════════════════════════════════════════════════════
# 2.  +lead
# ═══════════════════════════════════════════════════════════════════════════

class TestLeadHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_LEAD_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+lead")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("lead", self.entry.title.lower())

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_command_skill(self):
        self.assertIn("command", self.entry.body.lower())

    def test_body_mentions_difficulty(self):
        self.assertIn("diff", self.entry.body.lower())

    def test_examples_present(self):
        self.assertGreaterEqual(len(self.entry.examples), 1)


# ═══════════════════════════════════════════════════════════════════════════
# 3.  +joinlead
# ═══════════════════════════════════════════════════════════════════════════

class TestJoinleadHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_JOINLEAD_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+joinlead")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_see_also_contains_lead(self):
        self.assertIn("+lead", self.entry.see_also)

    def test_body_mentions_bonus(self):
        self.assertIn("bonus", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 4.  +plots
# ═══════════════════════════════════════════════════════════════════════════

class TestPlotsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PLOTS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+plots")

    def test_title_set(self):
        self.assertTrue(self.entry.title)
        self.assertIn("plot", self.entry.title.lower())

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_scene(self):
        self.assertIn("scene", self.entry.body.lower())

    def test_examples_include_create(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("create" in c for c in cmds), "Missing create example")


# ═══════════════════════════════════════════════════════════════════════════
# 5.  +region
# ═══════════════════════════════════════════════════════════════════════════

class TestRegionHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_REGION_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+region")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_exploration(self):
        self.assertIn("exploration", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_influence(self):
        self.assertIn("influence", self.entry.body.lower())

    def test_alias_reg(self):
        self.assertIn("+reg", self.entry.aliases)


# ═══════════════════════════════════════════════════════════════════════════
# 6.  +commissary
# ═══════════════════════════════════════════════════════════════════════════

class TestCommissaryHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_COMMISSARY_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+commissary")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_economy(self):
        self.assertIn("economy", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_faction(self):
        self.assertIn("faction", self.entry.body.lower())

    def test_body_mentions_rank(self):
        self.assertIn("rank", self.entry.body.lower())

    def test_examples_include_buy(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("buy" in c for c in cmds), "Missing buy example")


# ═══════════════════════════════════════════════════════════════════════════
# 7.  +credits
# ═══════════════════════════════════════════════════════════════════════════

class TestCreditsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_CREDITS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+credits")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_economy(self):
        self.assertIn("economy", self.entry.category.lower())

    def test_alias_balance(self):
        self.assertIn("balance", self.entry.aliases)

    def test_alias_wallet(self):
        self.assertIn("wallet", self.entry.aliases)

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_credits(self):
        self.assertIn("credit", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 8.  +rpprefs
# ═══════════════════════════════════════════════════════════════════════════

class TestRpPrefsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RPPREFS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+rpprefs")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_social(self):
        self.assertIn("social", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_finger(self):
        self.assertIn("finger", self.entry.body.lower())

    def test_body_mentions_yes_no_maybe(self):
        body_lower = self.entry.body.lower()
        self.assertIn("yes", body_lower)
        self.assertIn("no", body_lower)
        self.assertIn("maybe", body_lower)

    def test_examples_include_set(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("set" in c for c in cmds), "Missing set example")


# ═══════════════════════════════════════════════════════════════════════════
# 9.  +recap
# ═══════════════════════════════════════════════════════════════════════════

class TestRecapHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_RECAP_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+recap")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_roleplay(self):
        self.assertIn("roleplay", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_history(self):
        self.assertIn("+history", self.entry.aliases)

    def test_body_mentions_director(self):
        self.assertIn("director", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 10.  +quests
# ═══════════════════════════════════════════════════════════════════════════

class TestQuestsHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_QUESTS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+quests")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_roleplay(self):
        self.assertIn("roleplay", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_director(self):
        self.assertIn("director", self.entry.body.lower())

    def test_body_mentions_accept(self):
        self.assertIn("accept", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 11.  +intel
# ═══════════════════════════════════════════════════════════════════════════

class TestIntelHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_INTEL_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+intel")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_espionage(self):
        self.assertIn("espionage", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_handover(self):
        self.assertIn("handover", self.entry.body.lower())

    def test_body_mentions_sealed(self):
        self.assertIn("seal", self.entry.body.lower())

    def test_examples_include_create(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("create" in c for c in cmds), "Missing create example")


# ═══════════════════════════════════════════════════════════════════════════
# 12.  +roster
# ═══════════════════════════════════════════════════════════════════════════

class TestRosterHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_ROSTER_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+roster")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_ships(self):
        self.assertIn("ship", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_wage(self):
        self.assertIn("wage", self.entry.body.lower())

    def test_body_mentions_station(self):
        self.assertIn("station", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 13.  +pvp
# ═══════════════════════════════════════════════════════════════════════════

class TestPvpHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_PVP_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+pvp")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_combat(self):
        self.assertIn("combat", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_body_mentions_contested(self):
        self.assertIn("contested", self.entry.body.lower())

    def test_body_mentions_cooldown(self):
        self.assertIn("cooldown", self.entry.body.lower())

    def test_body_mentions_secured_zone(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "secured" in body_lower or "jedi temple" in body_lower,
            "pvp body should mention secured zones",
        )

    def test_examples_include_on_and_off(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("on" in c for c in cmds), "Missing 'on' example")
        self.assertTrue(any("off" in c for c in cmds), "Missing 'off' example")


# ═══════════════════════════════════════════════════════════════════════════
# 14.  +powers
# ═══════════════════════════════════════════════════════════════════════════

class TestPowersHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_POWERS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+powers")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_powers(self):
        self.assertIn("powers", self.entry.aliases)

    def test_body_mentions_control_sense_alter(self):
        body_lower = self.entry.body.lower()
        self.assertIn("control", body_lower)
        self.assertIn("sense", body_lower)
        self.assertIn("alter", body_lower)


# ═══════════════════════════════════════════════════════════════════════════
# 15.  +forcestatus
# ═══════════════════════════════════════════════════════════════════════════

class TestForceStatusHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_FORCESTATUS_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+forcestatus")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_fstatus(self):
        self.assertIn("fstatus", self.entry.aliases)

    def test_body_mentions_force_points(self):
        self.assertIn("force point", self.entry.body.lower())

    def test_body_mentions_dark_side(self):
        self.assertIn("dark side", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 16.  +meditate
# ═══════════════════════════════════════════════════════════════════════════

class TestMeditateHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_MEDITATE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+meditate")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_force(self):
        self.assertIn("force", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_meditate(self):
        self.assertIn("meditate", self.entry.aliases)

    def test_body_mentions_force_point(self):
        self.assertIn("force point", self.entry.body.lower())

    def test_body_mentions_weight(self):
        self.assertIn("weight", self.entry.body.lower())

    def test_body_mentions_daily(self):
        body_lower = self.entry.body.lower()
        self.assertTrue(
            "daily" in body_lower or "once per day" in body_lower or "24" in body_lower,
            "meditate body should mention daily limit",
        )

    def test_body_mentions_temple(self):
        self.assertIn("temple", self.entry.body.lower())


# ═══════════════════════════════════════════════════════════════════════════
# 17.  +title
# ═══════════════════════════════════════════════════════════════════════════

class TestTitleHelp(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = _load(_TITLE_PATH)

    def test_key(self):
        self.assertEqual(self.entry.key, "+title")

    def test_title_set(self):
        self.assertTrue(self.entry.title)

    def test_category_character(self):
        self.assertIn("character", self.entry.category.lower())

    def test_access_level(self):
        self.assertEqual(self.entry.access_level, 0)

    def test_alias_titles(self):
        self.assertIn("title", self.entry.aliases)

    def test_body_mentions_credits(self):
        self.assertIn("credit", self.entry.body.lower())

    def test_body_mentions_buy(self):
        self.assertIn("buy", self.entry.body.lower())

    def test_examples_include_buy_and_set(self):
        cmds = [ex["cmd"] for ex in self.entry.examples]
        self.assertTrue(any("buy" in c for c in cmds), "Missing buy example")
        self.assertTrue(any("set" in c for c in cmds), "Missing set example")
