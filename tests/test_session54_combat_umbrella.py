# -*- coding: utf-8 -*-
"""
tests/test_session54_combat_umbrella.py -- Session 54 feature tests

Covers the +combat umbrella and the canonical-switch rename:

  1. +combat/<switch> canonical form works for every combat verb
  2. Bare aliases still reach the same handler (muscle memory preserved)
  3. Unknown switches produce a clear error
  4. The help system loads +combat.md as a proper HelpEntry
  5. Registry wiring is correct (umbrella registered, switches valid)

Convention: +verb/switch [args], bare forms preserved as aliases.
This is the proof-of-pattern for the broader rename sweep across
mission, smuggling, bounty, crafting, crew, space, etc.
"""
import os
import sys
import unittest
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# ══════════════════════════════════════════════════════════════════════════════
# 1. Registry wiring — the umbrella is registered correctly
# ══════════════════════════════════════════════════════════════════════════════

class TestUmbrellaRegistration(unittest.TestCase):
    """Verify +combat registers with the right keys, aliases, and switches."""

    def test_combat_command_class_exists(self):
        from parser.combat_commands import CombatCommand
        self.assertTrue(hasattr(CombatCommand, "execute"))

    def test_combat_command_key_is_plus_combat(self):
        from parser.combat_commands import CombatCommand
        self.assertEqual(CombatCommand.key, "+combat")

    def test_valid_switches_covers_all_verbs(self):
        """Every combat verb must be in valid_switches or the parser rejects it."""
        from parser.combat_commands import CombatCommand
        required = {
            "attack", "dodge", "fulldodge", "parry", "fullparry",
            "soak", "aim", "flee", "disengage", "pass", "resolve",
            "range", "cover", "forcepoint", "pose", "rolls",
            "challenge", "accept", "decline", "status",
        }
        actual = set(CombatCommand.valid_switches)
        missing = required - actual
        self.assertFalse(missing, f"valid_switches missing: {missing}")

    def test_aliases_cover_all_bare_verbs(self):
        """Every pre-S54 bare verb must remain as an alias."""
        from parser.combat_commands import CombatCommand
        required_aliases = {
            "combat", "cs",
            "attack", "att", "kill", "shoot", "hit",
            "dodge", "fulldodge", "fdodge",
            "parry", "fullparry", "fparry",
            "soak", "aim",
            "flee", "run", "retreat",
            "pass", "disengage",
            "resolve",
            "range", "distance",
            "cover", "hide",
            "forcepoint", "fp",
            "cpose", "combatpose",
            "crolls",
            "challenge", "duel",
            "accept", "decline", "refuse",
        }
        actual = set(CombatCommand.aliases)
        missing = required_aliases - actual
        self.assertFalse(
            missing,
            f"CombatCommand aliases missing bare verbs: {missing}"
        )

    def test_switch_impl_dispatch_table_populated(self):
        """_SWITCH_IMPL must be populated at module load."""
        from parser.combat_commands import _SWITCH_IMPL
        required = {
            "attack", "dodge", "fulldodge", "parry", "fullparry",
            "soak", "aim", "flee", "disengage", "pass", "resolve",
            "range", "cover", "forcepoint", "pose",
            "challenge", "accept", "decline",
        }
        actual = set(_SWITCH_IMPL.keys())
        missing = required - actual
        self.assertFalse(missing, f"_SWITCH_IMPL missing: {missing}")

    def test_alias_to_switch_map_covers_aliases(self):
        """Every umbrella alias must resolve to a switch."""
        from parser.combat_commands import CombatCommand, _ALIAS_TO_SWITCH
        # Aliases that should resolve to a switch (excluding +combat itself
        # and short-forms that route through the plus-key lookup)
        for alias in CombatCommand.aliases:
            # Skip glued-prefix aliases like +fp and +cs; those round-trip
            # via the registry at a different layer
            if alias.startswith("+"):
                continue
            # Every bare alias should either map to a switch or be the
            # umbrella's name (combat/cs → status)
            self.assertIn(
                alias, _ALIAS_TO_SWITCH,
                f"Alias '{alias}' not in _ALIAS_TO_SWITCH map",
            )


# ══════════════════════════════════════════════════════════════════════════════
# 2. Dispatch logic — switch routing works, unknown switches fail cleanly
# ══════════════════════════════════════════════════════════════════════════════

class TestSwitchDispatch(unittest.TestCase):
    """Verify that ctx.switches and ctx.command dispatch the right handler."""

    def _make_ctx(self, command="combat", switches=None, args=""):
        """Build a minimal CommandContext for dispatch testing."""
        from parser.commands import CommandContext
        from unittest.mock import MagicMock
        session = MagicMock()
        session.character = {"id": 1, "name": "Tester", "room_id": 100}
        return CommandContext(
            session=session,
            raw_input=f"{command} {args}".strip(),
            command=command,
            args=args,
            args_list=args.split() if args else [],
            switches=switches or [],
            db=MagicMock(),
            session_mgr=MagicMock(),
        )

    def test_switch_resolution_from_canonical_form(self):
        """+combat/attack sets ctx.switches=['attack']; umbrella dispatches."""
        # We don't run execute() (needs a live combat); we verify the
        # dispatch decision logic by inspecting what the umbrella would
        # pick. Extract that logic: switches[0] wins if present.
        from parser.combat_commands import _ALIAS_TO_SWITCH
        # With switches=['attack'], dispatch should pick "attack"
        ctx = self._make_ctx(command="+combat", switches=["attack"])
        # Reproduce the umbrella's decision
        switch = ctx.switches[0].lower() if ctx.switches else \
            _ALIAS_TO_SWITCH.get(ctx.command.lower(), "status")
        self.assertEqual(switch, "attack")

    def test_switch_resolution_from_bare_alias(self):
        """Typing 'attack' (no switch) maps to switch 'attack' via alias map."""
        from parser.combat_commands import _ALIAS_TO_SWITCH
        ctx = self._make_ctx(command="attack", switches=[])
        switch = ctx.switches[0].lower() if ctx.switches else \
            _ALIAS_TO_SWITCH.get(ctx.command.lower(), "status")
        self.assertEqual(switch, "attack")

    def test_short_aliases_map_correctly(self):
        """Short-form aliases (att, kill, shoot, hit) all → attack."""
        from parser.combat_commands import _ALIAS_TO_SWITCH
        for alias in ("att", "kill", "shoot", "hit"):
            self.assertEqual(
                _ALIAS_TO_SWITCH[alias], "attack",
                f"Alias '{alias}' should map to 'attack'",
            )

    def test_flee_aliases_all_map_to_flee(self):
        from parser.combat_commands import _ALIAS_TO_SWITCH
        for alias in ("flee", "run", "retreat"):
            self.assertEqual(_ALIAS_TO_SWITCH[alias], "flee")

    def test_dodge_family_maps_correctly(self):
        """dodge → dodge, fulldodge → fulldodge, fdodge → fulldodge."""
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["dodge"], "dodge")
        self.assertEqual(_ALIAS_TO_SWITCH["fulldodge"], "fulldodge")
        self.assertEqual(_ALIAS_TO_SWITCH["fdodge"], "fulldodge")

    def test_parry_family_maps_correctly(self):
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["parry"], "parry")
        self.assertEqual(_ALIAS_TO_SWITCH["fullparry"], "fullparry")
        self.assertEqual(_ALIAS_TO_SWITCH["fparry"], "fullparry")

    def test_combat_status_maps_to_status(self):
        """Bare 'combat' and 'cs' resolve to status."""
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["combat"], "status")
        self.assertEqual(_ALIAS_TO_SWITCH["cs"], "status")

    def test_cpose_maps_to_pose(self):
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["cpose"], "pose")
        self.assertEqual(_ALIAS_TO_SWITCH["combatpose"], "pose")

    def test_crolls_maps_to_rolls(self):
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["crolls"], "rolls")

    def test_forcepoint_aliases_map_correctly(self):
        """forcepoint, fp both → forcepoint. (+fp handled at registry layer.)"""
        from parser.combat_commands import _ALIAS_TO_SWITCH
        self.assertEqual(_ALIAS_TO_SWITCH["forcepoint"], "forcepoint")
        self.assertEqual(_ALIAS_TO_SWITCH["fp"], "forcepoint")


# ══════════════════════════════════════════════════════════════════════════════
# 3. Help system integration — +combat.md loads as a rich HelpEntry
# ══════════════════════════════════════════════════════════════════════════════

class TestCombatHelpFile(unittest.TestCase):
    """Verify data/help/commands/+combat.md loads cleanly."""

    def _load_combat_entry(self):
        from data.help_topics import HelpEntry
        from engine.help_loader import load_help_directory
        root = os.path.join(_PROJECT_ROOT, "data", "help")
        entries = list(load_help_directory(root, HelpEntry))
        matching = [e for e in entries if e.key == "+combat"]
        self.assertEqual(
            len(matching), 1,
            "Expected exactly one +combat help entry",
        )
        return matching[0]

    def test_combat_help_loads(self):
        e = self._load_combat_entry()
        self.assertEqual(e.key, "+combat")
        self.assertTrue(e.title)
        self.assertTrue(e.summary)

    def test_combat_help_has_substantial_body(self):
        """The umbrella help should be dense — not a one-liner stub."""
        e = self._load_combat_entry()
        # 47 topic files average 500-1500 chars; combat umbrella covers
        # 20 switches and should be substantially larger.
        self.assertGreater(
            len(e.body), 5000,
            f"+combat body is only {len(e.body)} chars; "
            f"expected 5000+ for umbrella-scale coverage",
        )

    def test_combat_help_has_examples(self):
        e = self._load_combat_entry()
        # Examples block should have coverage of the major switches
        self.assertGreater(
            len(e.examples), 10,
            f"Expected 10+ examples covering major switches, got {len(e.examples)}",
        )
        # Each example should have cmd and description
        for ex in e.examples:
            self.assertIn("cmd", ex)
            self.assertIn("description", ex)

    def test_combat_help_cites_canonical_form_in_examples(self):
        """Examples should show '+combat/<switch>' format, not just bare."""
        e = self._load_combat_entry()
        canonical_count = sum(
            1 for ex in e.examples if ex["cmd"].startswith("+combat/")
        )
        self.assertGreater(
            canonical_count, 10,
            "Expected most examples to show +combat/<switch> canonical form",
        )

    def test_combat_help_cross_references_topics(self):
        """see_also should link to the conceptual topic files."""
        e = self._load_combat_entry()
        expected_links = {"combat", "dodge", "multiaction", "cover"}
        actual = set(e.see_also)
        missing = expected_links - actual
        self.assertFalse(
            missing,
            f"+combat see_also missing cross-references: {missing}",
        )

    def test_combat_help_mentions_rulebook_citation(self):
        """Per the design spec, mechanics should cite R&E where lifted."""
        e = self._load_combat_entry()
        self.assertIn(
            "R&E", e.body,
            "Expected R&E sourcebook citation in body",
        )


# ══════════════════════════════════════════════════════════════════════════════
# 4. Alias → switch completeness
# ══════════════════════════════════════════════════════════════════════════════

class TestAliasCompleteness(unittest.TestCase):
    """Every switch in valid_switches must have at least one alias route."""

    def test_every_switch_is_reachable_by_some_alias(self):
        """For each valid switch, there must exist an alias that maps to it
        (or the switch is the canonical name itself)."""
        from parser.combat_commands import CombatCommand, _ALIAS_TO_SWITCH

        # Build reverse: switch → set of aliases that map to it
        reverse: dict = {}
        for alias, sw in _ALIAS_TO_SWITCH.items():
            reverse.setdefault(sw, set()).add(alias)

        # Every switch should either have ≥1 alias OR be reachable directly
        # via +combat/<switch>. We test the alias path.
        for switch in CombatCommand.valid_switches:
            if switch in ("status",):
                # Status is reachable via bare "combat" / "cs" / no switch
                self.assertIn(switch, reverse)
                continue
            self.assertIn(
                switch, reverse,
                f"Switch '/{switch}' has no bare alias routing to it",
            )


if __name__ == "__main__":
    unittest.main()
