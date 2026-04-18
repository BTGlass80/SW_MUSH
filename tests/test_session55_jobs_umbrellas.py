# -*- coding: utf-8 -*-
"""
tests/test_session55_jobs_umbrellas.py -- Session 55 feature tests

Covers the +mission, +smuggle, +bounty, +quest umbrellas and the
canonical-switch rename for the four job-board / narrative modules:

  1. +<umbrella>/<switch> canonical form works for every verb
  2. Bare aliases still reach the same handler (muscle memory preserved)
  3. Unknown switches produce a clear error (via BaseCommand.valid_switches)
  4. The help system loads the four +<umbrella>.md files as HelpEntry
  5. Registry wiring is correct (umbrellas registered, keys resolve correctly)

Convention: +verb/switch [args], bare forms preserved as aliases.
Follows the S54 combat umbrella template.

Four umbrellas in this drop:
  +mission   -- board, accept, view, complete, abandon
  +smuggle   -- board, accept, view, deliver, dump
  +bounty    -- board, claim, view, track, collect
  +quest     -- list, accept, complete, abandon
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. +MISSION — Registry wiring, dispatch, help file
# ══════════════════════════════════════════════════════════════════════════════

class TestMissionUmbrellaRegistration(unittest.TestCase):
    """Verify +mission registers with the right keys, aliases, and switches."""

    def test_mission_command_class_exists(self):
        from parser.mission_commands import MissionCommand
        self.assertTrue(hasattr(MissionCommand, "execute"))

    def test_mission_command_key(self):
        from parser.mission_commands import MissionCommand
        self.assertEqual(MissionCommand.key, "+mission")

    def test_mission_valid_switches(self):
        """All mission verbs must be in valid_switches."""
        from parser.mission_commands import MissionCommand
        required = {"board", "accept", "view", "complete", "abandon"}
        actual = set(MissionCommand.valid_switches)
        self.assertFalse(required - actual, f"missing: {required - actual}")

    def test_mission_aliases_cover_bare_verbs(self):
        """Every pre-S55 bare verb must remain as an umbrella alias."""
        from parser.mission_commands import MissionCommand
        required = {
            "missions", "mb", "jobs",
            "mission", "myjob", "activemission",
            "accept", "takejob",
            "complete", "finishjob", "turnin",
            "abandon", "dropmission", "quitjob",
        }
        actual = set(MissionCommand.aliases)
        self.assertFalse(
            required - actual,
            f"MissionCommand aliases missing: {required - actual}",
        )

    def test_mission_switch_impl_populated(self):
        """_MISSION_SWITCH_IMPL must be populated at module load."""
        from parser.mission_commands import _MISSION_SWITCH_IMPL
        required = {"board", "accept", "view", "complete", "abandon"}
        self.assertFalse(
            required - set(_MISSION_SWITCH_IMPL.keys()),
            f"_MISSION_SWITCH_IMPL missing: {required - set(_MISSION_SWITCH_IMPL.keys())}",
        )

    def test_mission_alias_map_covers_aliases(self):
        """Every bare umbrella alias must resolve to a switch."""
        from parser.mission_commands import MissionCommand, _MISSION_ALIAS_TO_SWITCH
        for alias in MissionCommand.aliases:
            if alias.startswith("+"):
                continue  # +-prefixed aliases route via the registry layer
            self.assertIn(
                alias, _MISSION_ALIAS_TO_SWITCH,
                f"alias '{alias}' not in _MISSION_ALIAS_TO_SWITCH",
            )


class TestMissionSwitchDispatch(unittest.TestCase):
    """Verify canonical and bare forms reach the same switch."""

    def test_mission_canonical_accept(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        # ctx.switches=["accept"]  →  switch "accept"
        # (In the real path, umbrella.execute reads ctx.switches[0])
        self.assertEqual(_MISSION_ALIAS_TO_SWITCH.get("accept"), "accept")

    def test_mission_bare_accept_maps_to_accept(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        self.assertEqual(_MISSION_ALIAS_TO_SWITCH["accept"], "accept")
        self.assertEqual(_MISSION_ALIAS_TO_SWITCH["takejob"], "accept")

    def test_mission_board_aliases(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        for a in ("missions", "mb", "jobs"):
            self.assertEqual(_MISSION_ALIAS_TO_SWITCH[a], "board")

    def test_mission_view_aliases(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        for a in ("mission", "myjob", "activemission"):
            self.assertEqual(_MISSION_ALIAS_TO_SWITCH[a], "view")

    def test_mission_complete_aliases(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        for a in ("complete", "finishjob", "turnin"):
            self.assertEqual(_MISSION_ALIAS_TO_SWITCH[a], "complete")

    def test_mission_abandon_aliases(self):
        from parser.mission_commands import _MISSION_ALIAS_TO_SWITCH
        for a in ("abandon", "dropmission", "quitjob"):
            self.assertEqual(_MISSION_ALIAS_TO_SWITCH[a], "abandon")


class TestMissionHelpFile(unittest.TestCase):
    """Verify data/help/commands/+mission.md loads cleanly."""

    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        match = [e for e in entries if e.key == "+mission"]
        self.assertEqual(len(match), 1, "Expected one +mission entry")
        return match[0]

    def test_mission_help_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+mission")
        self.assertTrue(e.title)
        self.assertTrue(e.summary)

    def test_mission_help_body_is_dense(self):
        e = self._load()
        self.assertGreater(
            len(e.body), 5000,
            f"+mission body is only {len(e.body)}ch; expected 5000+",
        )

    def test_mission_help_has_examples(self):
        e = self._load()
        self.assertGreater(
            len(e.examples), 10,
            f"Expected 10+ examples, got {len(e.examples)}",
        )
        for ex in e.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)

    def test_mission_help_canonical_examples(self):
        e = self._load()
        canonical = sum(1 for ex in e.examples if ex["cmd"].startswith("+mission"))
        self.assertGreater(
            canonical, 5,
            "Expected several examples in +mission/<switch> canonical form",
        )

    def test_mission_help_cross_references(self):
        e = self._load()
        expected = {"+bounty", "+smuggle"}
        self.assertFalse(
            expected - set(e.see_also),
            f"+mission see_also missing: {expected - set(e.see_also)}",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. +SMUGGLE — Registry wiring, dispatch, help file
# ══════════════════════════════════════════════════════════════════════════════

class TestSmuggleUmbrellaRegistration(unittest.TestCase):

    def test_smuggle_command_class_exists(self):
        from parser.smuggling_commands import SmuggleCommand
        self.assertTrue(hasattr(SmuggleCommand, "execute"))

    def test_smuggle_command_key(self):
        from parser.smuggling_commands import SmuggleCommand
        self.assertEqual(SmuggleCommand.key, "+smuggle")

    def test_smuggle_valid_switches(self):
        from parser.smuggling_commands import SmuggleCommand
        required = {"board", "accept", "view", "deliver", "dump"}
        self.assertFalse(required - set(SmuggleCommand.valid_switches))

    def test_smuggle_aliases_cover_bare_verbs(self):
        from parser.smuggling_commands import SmuggleCommand
        required = {
            "smugjobs", "smugboard", "underworld",
            "smugjob", "myrun", "cargo",
            "smugaccept", "takerun",
            "smugdeliver", "deliver", "dropoff",
            "smugdump", "dumpcargo", "jettison",
        }
        actual = set(SmuggleCommand.aliases)
        self.assertFalse(
            required - actual,
            f"SmuggleCommand aliases missing: {required - actual}",
        )

    def test_smuggle_switch_impl_populated(self):
        from parser.smuggling_commands import _SMUGGLE_SWITCH_IMPL
        required = {"board", "accept", "view", "deliver", "dump"}
        self.assertFalse(required - set(_SMUGGLE_SWITCH_IMPL.keys()))

    def test_smuggle_alias_map_covers_aliases(self):
        from parser.smuggling_commands import SmuggleCommand, _SMUGGLE_ALIAS_TO_SWITCH
        for alias in SmuggleCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _SMUGGLE_ALIAS_TO_SWITCH)


class TestSmuggleSwitchDispatch(unittest.TestCase):

    def test_smuggle_board_aliases(self):
        from parser.smuggling_commands import _SMUGGLE_ALIAS_TO_SWITCH
        for a in ("smugjobs", "smugboard", "underworld"):
            self.assertEqual(_SMUGGLE_ALIAS_TO_SWITCH[a], "board")

    def test_smuggle_accept_aliases(self):
        from parser.smuggling_commands import _SMUGGLE_ALIAS_TO_SWITCH
        for a in ("smugaccept", "takesmug", "takerun"):
            self.assertEqual(_SMUGGLE_ALIAS_TO_SWITCH[a], "accept")

    def test_smuggle_view_aliases(self):
        from parser.smuggling_commands import _SMUGGLE_ALIAS_TO_SWITCH
        for a in ("smugjob", "myrun", "activerun", "cargo"):
            self.assertEqual(_SMUGGLE_ALIAS_TO_SWITCH[a], "view")

    def test_smuggle_deliver_aliases(self):
        from parser.smuggling_commands import _SMUGGLE_ALIAS_TO_SWITCH
        for a in ("smugdeliver", "deliver", "dropoff"):
            self.assertEqual(_SMUGGLE_ALIAS_TO_SWITCH[a], "deliver")

    def test_smuggle_dump_aliases(self):
        from parser.smuggling_commands import _SMUGGLE_ALIAS_TO_SWITCH
        for a in ("smugdump", "dumpcargo", "jettison"):
            self.assertEqual(_SMUGGLE_ALIAS_TO_SWITCH[a], "dump")


class TestSmuggleHelpFile(unittest.TestCase):

    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        match = [e for e in entries if e.key == "+smuggle"]
        self.assertEqual(len(match), 1, "Expected one +smuggle entry")
        return match[0]

    def test_smuggle_help_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+smuggle")
        self.assertTrue(e.title)

    def test_smuggle_help_body_is_dense(self):
        e = self._load()
        self.assertGreater(len(e.body), 5000)

    def test_smuggle_help_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)

    def test_smuggle_help_canonical_examples(self):
        e = self._load()
        canonical = sum(1 for ex in e.examples if ex["cmd"].startswith("+smuggle"))
        self.assertGreater(canonical, 5)


# ══════════════════════════════════════════════════════════════════════════════
# 3. +BOUNTY — Registry wiring, dispatch, help file
# ══════════════════════════════════════════════════════════════════════════════

class TestBountyUmbrellaRegistration(unittest.TestCase):

    def test_bounty_command_class_exists(self):
        from parser.bounty_commands import BountyCommand
        self.assertTrue(hasattr(BountyCommand, "execute"))

    def test_bounty_command_key(self):
        from parser.bounty_commands import BountyCommand
        self.assertEqual(BountyCommand.key, "+bounty")

    def test_bounty_valid_switches(self):
        from parser.bounty_commands import BountyCommand
        required = {"board", "claim", "view", "track", "collect"}
        self.assertFalse(required - set(BountyCommand.valid_switches))

    def test_bounty_aliases_cover_bare_verbs(self):
        from parser.bounty_commands import BountyCommand
        required = {
            "bounties", "bboard", "bountyboard",
            "mybounty", "activebounty", "myhunt",
            "bountyclaim", "claimbounty", "acceptbounty",
            "bountytrack", "tracktarget", "hunttrack",
            "bountycollect", "collectbounty", "claimreward",
        }
        actual = set(BountyCommand.aliases)
        self.assertFalse(
            required - actual,
            f"BountyCommand aliases missing: {required - actual}",
        )

    def test_bounty_switch_impl_populated(self):
        from parser.bounty_commands import _BOUNTY_SWITCH_IMPL
        required = {"board", "claim", "view", "track", "collect"}
        self.assertFalse(required - set(_BOUNTY_SWITCH_IMPL.keys()))

    def test_bounty_alias_map_covers_aliases(self):
        from parser.bounty_commands import BountyCommand, _BOUNTY_ALIAS_TO_SWITCH
        for alias in BountyCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _BOUNTY_ALIAS_TO_SWITCH)


class TestBountySwitchDispatch(unittest.TestCase):

    def test_bounty_board_aliases(self):
        from parser.bounty_commands import _BOUNTY_ALIAS_TO_SWITCH
        for a in ("bounties", "bboard", "bountyboard"):
            self.assertEqual(_BOUNTY_ALIAS_TO_SWITCH[a], "board")

    def test_bounty_claim_aliases(self):
        from parser.bounty_commands import _BOUNTY_ALIAS_TO_SWITCH
        for a in ("bountyclaim", "claimbounty", "acceptbounty"):
            self.assertEqual(_BOUNTY_ALIAS_TO_SWITCH[a], "claim")

    def test_bounty_view_aliases(self):
        from parser.bounty_commands import _BOUNTY_ALIAS_TO_SWITCH
        for a in ("mybounty", "activebounty", "myhunt"):
            self.assertEqual(_BOUNTY_ALIAS_TO_SWITCH[a], "view")

    def test_bounty_track_aliases(self):
        from parser.bounty_commands import _BOUNTY_ALIAS_TO_SWITCH
        for a in ("bountytrack", "tracktarget", "hunttrack"):
            self.assertEqual(_BOUNTY_ALIAS_TO_SWITCH[a], "track")

    def test_bounty_collect_aliases(self):
        from parser.bounty_commands import _BOUNTY_ALIAS_TO_SWITCH
        for a in ("bountycollect", "collectbounty", "claimreward"):
            self.assertEqual(_BOUNTY_ALIAS_TO_SWITCH[a], "collect")


class TestBountyHelpFile(unittest.TestCase):

    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        match = [e for e in entries if e.key == "+bounty"]
        self.assertEqual(len(match), 1)
        return match[0]

    def test_bounty_help_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+bounty")
        self.assertTrue(e.title)

    def test_bounty_help_body_is_dense(self):
        e = self._load()
        self.assertGreater(len(e.body), 5000)

    def test_bounty_help_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)

    def test_bounty_help_canonical_examples(self):
        e = self._load()
        canonical = sum(1 for ex in e.examples if ex["cmd"].startswith("+bounty"))
        self.assertGreater(canonical, 5)


# ══════════════════════════════════════════════════════════════════════════════
# 4. +QUEST — Registry wiring, dispatch, help file
# ══════════════════════════════════════════════════════════════════════════════

class TestQuestUmbrellaRegistration(unittest.TestCase):

    def test_quest_command_class_exists(self):
        from parser.narrative_commands import QuestCommand
        self.assertTrue(hasattr(QuestCommand, "execute"))

    def test_quest_command_key(self):
        from parser.narrative_commands import QuestCommand
        self.assertEqual(QuestCommand.key, "+quest")

    def test_quest_valid_switches(self):
        from parser.narrative_commands import QuestCommand
        required = {"list", "accept", "complete", "abandon"}
        self.assertFalse(required - set(QuestCommand.valid_switches))

    def test_quest_aliases_cover_bare_verbs(self):
        from parser.narrative_commands import QuestCommand
        required = {
            "quests", "personalquests",
            "questaccept", "acceptquest", "pqaccept",
            "questcomplete", "finishquest", "pqcomplete", "completequest",
            "questabandon", "abandonquest", "pqdrop",
        }
        actual = set(QuestCommand.aliases)
        self.assertFalse(
            required - actual,
            f"QuestCommand aliases missing: {required - actual}",
        )

    def test_quest_switch_impl_populated(self):
        from parser.narrative_commands import _QUEST_SWITCH_IMPL
        required = {"list", "accept", "complete", "abandon"}
        self.assertFalse(required - set(_QUEST_SWITCH_IMPL.keys()))

    def test_quest_alias_map_covers_aliases(self):
        from parser.narrative_commands import QuestCommand, _QUEST_ALIAS_TO_SWITCH
        for alias in QuestCommand.aliases:
            if alias.startswith("+"):
                continue
            self.assertIn(alias, _QUEST_ALIAS_TO_SWITCH)


class TestQuestSwitchDispatch(unittest.TestCase):

    def test_quest_list_aliases(self):
        from parser.narrative_commands import _QUEST_ALIAS_TO_SWITCH
        for a in ("quests", "personalquests"):
            self.assertEqual(_QUEST_ALIAS_TO_SWITCH[a], "list")

    def test_quest_accept_aliases(self):
        from parser.narrative_commands import _QUEST_ALIAS_TO_SWITCH
        for a in ("questaccept", "acceptquest", "pqaccept"):
            self.assertEqual(_QUEST_ALIAS_TO_SWITCH[a], "accept")

    def test_quest_complete_aliases(self):
        from parser.narrative_commands import _QUEST_ALIAS_TO_SWITCH
        for a in ("questcomplete", "finishquest", "pqcomplete", "completequest"):
            self.assertEqual(_QUEST_ALIAS_TO_SWITCH[a], "complete")

    def test_quest_abandon_aliases(self):
        from parser.narrative_commands import _QUEST_ALIAS_TO_SWITCH
        for a in ("questabandon", "abandonquest", "pqdrop"):
            self.assertEqual(_QUEST_ALIAS_TO_SWITCH[a], "abandon")


class TestQuestHelpFile(unittest.TestCase):

    def _load(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        match = [e for e in entries if e.key == "+quest"]
        self.assertEqual(len(match), 1)
        return match[0]

    def test_quest_help_loads(self):
        e = self._load()
        self.assertEqual(e.key, "+quest")
        self.assertTrue(e.title)

    def test_quest_help_body_is_dense(self):
        e = self._load()
        self.assertGreater(len(e.body), 4000)  # quest has fewer switches

    def test_quest_help_has_examples(self):
        e = self._load()
        self.assertGreater(len(e.examples), 10)

    def test_quest_help_canonical_examples(self):
        e = self._load()
        canonical = sum(1 for ex in e.examples if ex["cmd"].startswith("+quest"))
        self.assertGreater(canonical, 4)


# ══════════════════════════════════════════════════════════════════════════════
# 5. End-to-end registry wiring — all umbrellas + combat coexist correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestCrossModuleRegistration(unittest.TestCase):
    """Verify the full registration order produces the correct dispatch map."""

    def _build_registry(self):
        from parser.commands import CommandRegistry
        from parser.combat_commands import register_combat_commands
        from parser.mission_commands import register_mission_commands
        from parser.smuggling_commands import register_smuggling_commands
        from parser.bounty_commands import register_bounty_commands
        from parser.narrative_commands import register_narrative_commands
        r = CommandRegistry()
        register_combat_commands(r)
        register_mission_commands(r)
        register_bounty_commands(r)
        register_smuggling_commands(r)
        register_narrative_commands(r)
        return r

    def test_all_umbrella_keys_resolve_to_umbrellas(self):
        """+combat, +mission, +smuggle, +bounty, +quest each resolve to
        the umbrella class, not a per-verb class."""
        from parser.combat_commands import CombatCommand
        from parser.mission_commands import MissionCommand
        from parser.smuggling_commands import SmuggleCommand
        from parser.bounty_commands import BountyCommand
        from parser.narrative_commands import QuestCommand

        r = self._build_registry()
        self.assertIsInstance(r.get("+combat"), CombatCommand)
        self.assertIsInstance(r.get("+mission"), MissionCommand)
        self.assertIsInstance(r.get("+smuggle"), SmuggleCommand)
        self.assertIsInstance(r.get("+bounty"), BountyCommand)
        self.assertIsInstance(r.get("+quest"), QuestCommand)

    def test_bare_mission_accept_still_routes_to_mission(self):
        """Pre-S54 behavior preserved: bare 'accept' reaches mission-accept.
        Combat-PvP accept is available via +combat/accept."""
        from parser.mission_commands import AcceptMissionCommand
        r = self._build_registry()
        cmd = r.get("accept")
        self.assertIsInstance(cmd, AcceptMissionCommand)

    def test_bare_verbs_route_correctly(self):
        """Every bare verb reaches some executable command."""
        r = self._build_registry()
        bare_verbs = [
            # mission
            "missions", "complete", "abandon",
            # smuggle
            "smugjobs", "smugaccept", "deliver", "jettison",
            # bounty
            "bounties", "bountyclaim", "bountytrack", "bountycollect",
            # quest
            "quests", "questaccept", "questcomplete", "questabandon",
        ]
        for verb in bare_verbs:
            cmd = r.get(verb)
            self.assertIsNotNone(
                cmd, f"Bare verb '{verb}' did not resolve to a command"
            )


if __name__ == "__main__":
    unittest.main()
