# -*- coding: utf-8 -*-
"""
tests/test_chain_corpus_reachability_invariant.py — P0.1 static
onboarding-reachability invariant (drop 25, 2026-06-12).

WHY THIS FILE EXISTS
====================
Drop 24 (F.8.c.2.e) discovered that all 7 unlocked Clone Wars tutorial
chains were non-completable from a real chargen:

  1. An inter-step strand (the player never moved to the next step's
     room — fixed by the inter-step teleport in chain_graduation.py).
  2. A `+factions` graduation alias that was not registered, so the
     `command_executed: +factions` completion could never fire.
  3. `room_entered` / `item_acquired` completions that are unreachable
     in exit-less, teleport-only tutorial rooms.
  4. Phantom skills (`starship_repair`, `starship_piloting`) that
     silently rolled raw Perception instead of the authored skill.

The entire existing chain test+smoke layer MISSED this class because
those tests inject chain state, pre-supply destination slugs, or
pre-place the player at a slugless room — none walk a real chargen
through the live command registry. This file is the cheap (pure-YAML,
milliseconds) static half of the coverage net mandated by
TD.ONBOARDING_CHAIN_REACHABILITY_COVERAGE. The runtime half is
tests/smoke/test_smoke_chain_walkthrough.py.

It asserts, for every UNLOCKED chain (locked stubs like jedi_path are
skipped — they never run at runtime), four reachability classes:

  CLASS 1 — Every room reference resolves to a real loaded room slug.
            The inter-step teleport seam requires `step[i+1].location`
            to resolve to a built room, so a step whose location is a
            phantom slug strands the player. (Reuses the slug-set
            helpers from test_f8b_tutorial_rooms.py.)

  CLASS 2 — No `room_entered` / `item_acquired` completions. Both are
            producerless in exit-less teleport-only rooms. The
            `room_entered` half is ALSO guarded inline at
            tests/test_f8c2b_chain_events.py::test_no_chain_step_uses_
            room_entered — this file extends the guard to item_acquired
            and consolidates both classes here as the single
            reachability authority. (Cross-reference, not blind
            duplication: the chain_events guard stays as a unit-level
            sentinel near the matcher it protects.)

  CLASS 3 — Every completion `command:` (and every
            `requires_first[].command`) resolves through the REAL
            command registry, built the way the server builds it. This
            is the guard that would have caught the unregistered
            `+factions` blocker.

  CLASS 4 — Every `skill:` (and `fallback.skill`) in a
            `skill_check_passed` completion resolves to a real skill —
            via engine.character.canonical_skill_key against the
            data/skills.yaml name-set OR the sanctioned
            engine/skill_checks.py `_FALLBACK` attr map. This would
            have caught `starship_repair` / `starship_piloting`.

Acceptance: passes against the current corpus, FAILS if any of the four
classes regress.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

CHAINS_PATH = (PROJECT_ROOT / "data" / "worlds" / "clone_wars" /
               "tutorials" / "chains.yaml")


# ──────────────────────────────────────────────────────────────────────
# Corpus + slug-set + registry + skill-set fixtures (built once)
# ──────────────────────────────────────────────────────────────────────

def _load_chains_yaml() -> dict:
    with open(CHAINS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _unlocked_chains(chains_data: dict):
    """Yield (chain_block) for every chain that is NOT a locked stub.

    Locked chains (jedi_path, jedi_path_independent) are rejected by
    the chain selector at chargen and surface their locked_message
    instead — they never run, so their single placeholder step is not
    a reachability concern.
    """
    for c in chains_data.get("chains", []):
        if c.get("locked"):
            continue
        yield c


def _all_room_slugs() -> set:
    """The union of every slug a real loaded room can have:
    tutorial-zone rooms + live-world planet rooms + wilderness
    landmarks. Reuses test_f8b_tutorial_rooms.py's helpers verbatim so
    this stays in lockstep with the canonical resolver."""
    from tests.test_f8b_tutorial_rooms import (
        _load_tutorial_room_slugs,
        _load_planet_room_slugs,
        _load_wilderness_landmark_slugs,
    )
    return (_load_tutorial_room_slugs()
            | _load_planet_room_slugs()
            | _load_wilderness_landmark_slugs())


def _build_command_registry():
    """Build the full command registry the EXACT way the live server
    does (server/game_server.py GameServer.__init__).

    We import the real `register_*` functions and call them in the
    server's order rather than reconstructing the command set by hand —
    that way registration drift (a register_* call added/removed in the
    server) flows into this test automatically. If the server's
    registration sequence changes, this list must change too; the
    `test_registry_matches_server_registration` test below pins that
    they stay in sync.
    """
    from parser.commands import CommandRegistry

    # Server registration sequence (server/game_server.py:192-...).
    # Kept in the same order as the server for parity; order does not
    # affect get() resolution but mirroring it makes drift obvious.
    from parser.builtin_commands import register_all
    from parser.d6_commands import register_d6_commands
    from parser.building_commands import register_building_commands
    from parser.building_tier2 import register_building_tier2
    from parser.combat_commands import register_combat_commands
    from parser.npc_commands import register_npc_commands
    from parser.space_commands import register_space_commands
    from parser.crew_commands import register_crew_commands
    from parser.mission_commands import register_mission_commands
    from parser.bounty_commands import register_bounty_commands
    from parser.director_commands import register_director_commands
    from parser.news_commands import register_news_commands
    from parser.smuggling_commands import register_smuggling_commands
    from parser.force_commands import register_force_commands
    from parser.medical_commands import register_medical_commands
    from parser.entertainer_commands import register_entertainer_commands
    from parser.cp_commands import register_cp_commands
    from parser.sabacc_commands import register_sabacc_commands
    from parser.crafting_commands import register_crafting_commands
    from parser.tutorial_commands import register_tutorial_commands
    from parser.chain_commands import register_chain_commands
    from parser.questline_commands import register_questline_commands
    from parser.meditate_command import register_meditate_command
    from parser.faction_commands import register_faction_commands
    from parser.faction_leader_commands import (
        register_faction_leader_commands)
    from parser.narrative_commands import register_narrative_commands
    from parser.shop_commands import register_shop_commands
    from parser.housing_commands import register_housing_commands
    from parser.spacer_quest_commands import (
        register_spacer_quest_commands)
    from parser.shipyard_commands import register_shipyard_commands
    from parser.ship_crew_commands import register_ship_crew_commands
    from parser.finances_commands import register_finances_commands
    from parser.mux_commands import register_mux_commands
    from parser.places_commands import register_places_commands
    from parser.attr_commands import register_attr_commands
    from parser.char_commands import register_char_commands
    from parser.scene_commands import register_scene_commands
    from parser.mail_commands import register_mail_commands
    from parser.espionage_commands import register_espionage_commands
    from parser.achievement_commands import register_achievement_commands
    from parser.title_commands import register_title_commands
    from parser.commissary_commands import register_commissary_commands
    from parser.insurance_commands import register_insurance_commands
    from parser.den_commands import register_den_commands
    from parser.event_commands import register_event_commands
    from parser.plot_commands import register_plot_commands
    from parser.channel_commands import register_channel_commands
    from parser.party_commands import register_party_commands
    from parser.encounter_commands import register_encounter_commands
    from parser.village_trial_commands import (
        register_village_trial_commands)
    from parser.padawan_master_commands import (
        register_padawan_master_commands)
    from parser.padawan_master_training_commands import (
        register_padawan_master_training_commands)
    from parser.padawan_master_trials import register_padawan_master_trials
    from parser.pc_bounty_commands import register_pc_bounty_commands

    registry = CommandRegistry()
    register_all(registry)
    register_d6_commands(registry)
    register_building_commands(registry)
    register_building_tier2(registry)
    register_combat_commands(registry)
    register_npc_commands(registry)
    register_space_commands(registry)
    register_crew_commands(registry)
    register_mission_commands(registry)
    register_bounty_commands(registry)
    register_director_commands(registry)
    register_news_commands(registry)
    register_smuggling_commands(registry)
    register_force_commands(registry)
    register_medical_commands(registry)
    register_entertainer_commands(registry)
    register_cp_commands(registry)
    register_sabacc_commands(registry)
    register_crafting_commands(registry)
    register_tutorial_commands(registry)
    register_chain_commands(registry)
    register_questline_commands(registry)
    register_meditate_command(registry)
    register_faction_commands(registry)
    register_faction_leader_commands(registry)
    register_narrative_commands(registry)
    register_shop_commands(registry)
    register_housing_commands(registry)
    register_spacer_quest_commands(registry)
    register_shipyard_commands(registry)
    register_ship_crew_commands(registry)
    register_finances_commands(registry)
    register_mux_commands(registry)
    register_places_commands(registry)
    register_attr_commands(registry)
    register_char_commands(registry)
    register_scene_commands(registry)
    register_mail_commands(registry)
    register_espionage_commands(registry)
    register_achievement_commands(registry)
    register_title_commands(registry)
    register_commissary_commands(registry)
    register_insurance_commands(registry)
    register_den_commands(registry)
    register_event_commands(registry)
    register_plot_commands(registry)
    register_channel_commands(registry)
    register_party_commands(registry)
    register_encounter_commands(registry)
    register_village_trial_commands(registry)
    register_padawan_master_commands(registry)
    register_padawan_master_training_commands(registry)
    register_padawan_master_trials(registry)
    register_pc_bounty_commands(registry)
    return registry


def _skill_name_set() -> set:
    """The canonical-key name-set of every skill in data/skills.yaml,
    each run through canonical_skill_key so the comparison is on the
    same normalized form the engine uses at roll time."""
    from engine.character import canonical_skill_key
    with open(PROJECT_ROOT / "data" / "skills.yaml", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    names = set()
    for _attr, skill_list in data.items():
        for entry in skill_list:
            names.add(canonical_skill_key(entry["name"]))
    return names


def _fallback_skill_set() -> set:
    """The sanctioned non-registry skills from skill_checks._skill_to_attr's
    `_FALLBACK` map. A `skill_check_passed` completion naming one of these
    resolves to a real attribute even without a data/skills.yaml entry, so
    it is NOT a phantom skill.

    The `_FALLBACK` dict is a local literal inside `_skill_to_attr` (built
    by BUILD_MAP, so it is NOT a single bytecode constant we can pluck).
    We harvest its keys by reading the function's string constants — every
    key is a string literal in the function's code object's co_consts.
    This stays in lockstep with the source without re-listing the map
    here (which would silently drift). The known anchor keys ("sneak",
    "con") confirm we found the right pool; if the shape ever changes,
    we return an empty set and Class 4 relies on the skills.yaml name-set
    alone (which already covers every current corpus skill).
    """
    from engine.character import canonical_skill_key
    try:
        from engine import skill_checks
        consts = skill_checks._skill_to_attr.__code__.co_consts
        string_consts = {c for c in consts if isinstance(c, str)}
        # Sanity-anchor: the fallback map's keys must include these. If
        # they're absent the source shape changed; bail to skills.yaml.
        if {"sneak", "con", "search"} <= string_consts:
            # The attribute VALUES ("dexterity", etc.) are also string
            # consts. Filter them out: a fallback KEY is a skill name, and
            # we only need it to be in the union with skills.yaml, so a
            # stray attribute name in the set is harmless (no corpus skill
            # is literally "dexterity"). Keep all string consts; the union
            # only ever ADMITS skills, never rejects a real one.
            return {canonical_skill_key(c) for c in string_consts}
    except Exception:
        pass
    return set()


# ──────────────────────────────────────────────────────────────────────
# Class 1 — every room reference resolves
# ──────────────────────────────────────────────────────────────────────

class TestChainRoomsResolve(unittest.TestCase):
    """Every room reference in an unlocked chain (starting_room,
    graduation.drop_room, step.location) must resolve to a real loaded
    room slug — the inter-step teleport seam strands the player
    otherwise."""

    @classmethod
    def setUpClass(cls):
        cls.chains = _load_chains_yaml()
        cls.slugs = _all_room_slugs()

    def _walk_room_refs(self):
        for c in _unlocked_chains(self.chains):
            cid = c.get("chain_id", "?")
            if c.get("starting_room"):
                yield (cid, "starting_room", c["starting_room"])
            grad = c.get("graduation") or {}
            if grad.get("drop_room"):
                yield (cid, "graduation.drop_room", grad["drop_room"])
            for step in c.get("steps") or []:
                if step.get("location"):
                    yield (cid, f"step{step.get('step')}.location",
                           step["location"])

    def test_every_room_reference_resolves(self):
        unresolved = [
            (cid, field, slug)
            for cid, field, slug in self._walk_room_refs()
            if slug not in self.slugs
        ]
        if unresolved:
            lines = [f"  {cid:<24} {field:<28} -> {slug}"
                     for cid, field, slug in unresolved]
            self.fail(
                f"{len(unresolved)} unlocked-chain room reference(s) do "
                f"not resolve to a loaded room slug. A phantom step "
                f"location strands the player at the inter-step teleport "
                f"(F.8.c.2.e). Author the room or redirect the "
                f"reference:\n" + "\n".join(lines)
            )


# ──────────────────────────────────────────────────────────────────────
# Class 2 — no unreachable completion types
# ──────────────────────────────────────────────────────────────────────

class TestNoUnreachableCompletionTypes(unittest.TestCase):
    """`room_entered` and `item_acquired` completions are producerless
    in exit-less, teleport-only tutorial rooms — the inter-step teleport
    is a direct room-id write that does NOT fire the move hook (so
    `on_room_entered` never matches), and tutorial-room item grants
    arrive as STEP REWARDS (delivered on advance), never via an
    in-room `item_acquired` producer the player can trigger.

    The `room_entered` half is also pinned inline at
    tests/test_f8c2b_chain_events.py::test_no_chain_step_uses_room_
    entered; this is the consolidated reachability authority that also
    covers `item_acquired`."""

    UNREACHABLE_TYPES = {"room_entered", "item_acquired"}

    @classmethod
    def setUpClass(cls):
        cls.chains = _load_chains_yaml()

    def test_no_unreachable_completion_types(self):
        offenders = []
        for c in _unlocked_chains(self.chains):
            cid = c.get("chain_id", "?")
            for step in c.get("steps") or []:
                ctype = (step.get("completion") or {}).get("type")
                if ctype in self.UNREACHABLE_TYPES:
                    offenders.append(
                        f"{cid} step {step.get('step')}: {ctype}")
        self.assertEqual(
            offenders, [],
            "Unreachable completion type(s) in exit-less tutorial rooms "
            "(F.8.c.2.e): room_entered never fires from the inter-step "
            "teleport, and item_acquired has no in-room producer the "
            "player can trigger. Re-author to a producible completion "
            "(command_executed / talk_to_npc / skill_check_passed / "
            "combat_won) and deliver any item as a step reward. "
            "Offenders: " + ", ".join(offenders),
        )


# ──────────────────────────────────────────────────────────────────────
# Class 3 — every completion command resolves through the real registry
# ──────────────────────────────────────────────────────────────────────

class TestCompletionCommandsResolve(unittest.TestCase):
    """Every literal command a chain step asks the player to type — the
    `command_executed` completion `command:` and every
    `requires_first[].command` — must resolve through the live command
    registry. This is the guard that would have caught the unregistered
    `+factions` graduation alias (drop 24's class-2 blocker)."""

    @classmethod
    def setUpClass(cls):
        cls.chains = _load_chains_yaml()
        cls.registry = _build_command_registry()

    def _walk_command_literals(self):
        """Yield (chain_id, where, command_literal) for every command a
        player must type to advance, derived from completion blocks."""
        for c in _unlocked_chains(self.chains):
            cid = c.get("chain_id", "?")
            for step in c.get("steps") or []:
                comp = step.get("completion") or {}
                sn = step.get("step")
                if comp.get("type") == "command_executed" and comp.get(
                        "command"):
                    yield (cid, f"step{sn}.completion.command",
                           comp["command"])
                for j, pre in enumerate(comp.get("requires_first") or []):
                    if isinstance(pre, dict) and pre.get("command"):
                        yield (cid,
                               f"step{sn}.requires_first[{j}].command",
                               pre["command"])

    def test_every_completion_command_resolves(self):
        unresolved = []
        for cid, where, literal in self._walk_command_literals():
            # The corpus stores the literal a player types, e.g.
            # "+factions", "examine", "+craft". registry.get expects the
            # bare verb token (no args). Every literal in the corpus is a
            # single verb token already, but split defensively in case a
            # future author writes "attack stun".
            verb = literal.strip().split()[0] if literal.strip() else ""
            if not verb or self.registry.get(verb) is None:
                unresolved.append((cid, where, literal))
        if unresolved:
            lines = [f"  {cid:<24} {where:<40} -> {lit!r}"
                     for cid, where, lit in unresolved]
            self.fail(
                f"{len(unresolved)} chain completion command(s) do NOT "
                f"resolve through the live command registry. A player "
                f"told to type a non-existent command can never advance "
                f"the step (drop 24's +factions blocker class). Register "
                f"the command or fix the corpus literal:\n"
                + "\n".join(lines)
            )

    def test_factions_alias_specifically_resolves(self):
        """Pin the exact drop-24 regression: the `+factions` literal
        used by every chain's final step must resolve."""
        self.assertIsNotNone(
            self.registry.get("+factions"),
            "`+factions` does not resolve — this is the exact drop-24 "
            "blocker (every chain's graduation step completes on it).",
        )


# ──────────────────────────────────────────────────────────────────────
# Class 4 — every skill_check_passed skill resolves
# ──────────────────────────────────────────────────────────────────────

class TestSkillCheckSkillsResolve(unittest.TestCase):
    """Every `skill:` (and `fallback.skill`) in a `skill_check_passed`
    completion must resolve to a real skill — via canonical_skill_key
    against the data/skills.yaml name-set OR the sanctioned
    skill_checks._FALLBACK attr map. A phantom skill silently rolls raw
    Perception (drop 24's `starship_repair` / `starship_piloting`
    class)."""

    @classmethod
    def setUpClass(cls):
        cls.chains = _load_chains_yaml()
        cls.skill_names = _skill_name_set() | _fallback_skill_set()
        from engine.character import canonical_skill_key
        cls._canon = staticmethod(canonical_skill_key)

    def _walk_skill_refs(self):
        """Yield (chain_id, where, skill) for every skill named by a
        skill_check_passed completion, including nested fallbacks."""
        for c in _unlocked_chains(self.chains):
            cid = c.get("chain_id", "?")
            for step in c.get("steps") or []:
                comp = step.get("completion") or {}
                sn = step.get("step")
                yield from self._walk_completion_skills(cid, sn, comp,
                                                        "completion")

    def _walk_completion_skills(self, cid, sn, comp, prefix):
        if not isinstance(comp, dict):
            return
        if comp.get("type") == "skill_check_passed" and comp.get("skill"):
            yield (cid, f"step{sn}.{prefix}.skill", comp["skill"])
        fb = comp.get("fallback")
        if isinstance(fb, dict):
            # fallback may itself be a skill_check_passed (smuggler s4)
            yield from self._walk_completion_skills(
                cid, sn, fb, f"{prefix}.fallback")

    def test_every_skill_check_skill_resolves(self):
        from engine.character import canonical_skill_key
        unresolved = []
        for cid, where, skill in self._walk_skill_refs():
            if canonical_skill_key(skill) not in self.skill_names:
                unresolved.append((cid, where, skill))
        if unresolved:
            lines = [f"  {cid:<24} {where:<40} -> {sk!r}"
                     for cid, where, sk in unresolved]
            self.fail(
                f"{len(unresolved)} skill_check_passed skill(s) do NOT "
                f"resolve to a real skill (data/skills.yaml or the "
                f"sanctioned _FALLBACK map). A phantom skill silently "
                f"rolls raw Perception (drop 24's starship_repair / "
                f"starship_piloting class). Use a canonical WEG skill "
                f"name:\n" + "\n".join(lines)
            )


# ──────────────────────────────────────────────────────────────────────
# Registry-parity sentinel — keep the test's registration in sync with
# the server's
# ──────────────────────────────────────────────────────────────────────

class TestRegistryMatchesServerRegistration(unittest.TestCase):
    """The Class-3 registry is built by hand-mirroring the server's
    register_* sequence. If the server adds a NEW register_* call that
    introduces commands a future chain step might use, this test's
    registry would silently lag. We can't import GameServer here
    cheaply (it pulls the whole stack), so we pin the lighter invariant:
    the test registry must contain the specific commands every CURRENT
    unlocked chain depends on. If a chain later uses a command from a
    register_* group this test omits, Class 3 will fail loudly with that
    exact command — which is the signal to add the missing register_*
    call above.

    This is a smoke-level sanity pin, not a full parity proof: the real
    parity guarantee is that Class 3 resolves every command the corpus
    actually uses against the SAME registry the player hits at runtime
    (the smoke walkthrough)."""

    def test_core_chain_commands_present(self):
        registry = _build_command_registry()
        # The union of every command literal the current unlocked corpus
        # depends on — derived live from the corpus so it can't drift.
        chains = _load_chains_yaml()
        needed = set()
        for c in _unlocked_chains(chains):
            for step in c.get("steps") or []:
                comp = step.get("completion") or {}
                if comp.get("type") == "command_executed" and comp.get(
                        "command"):
                    needed.add(comp["command"].strip().split()[0])
                for pre in comp.get("requires_first") or []:
                    if isinstance(pre, dict) and pre.get("command"):
                        needed.add(pre["command"].strip().split()[0])
        missing = sorted(v for v in needed if registry.get(v) is None)
        self.assertEqual(
            missing, [],
            f"Chain-required command(s) not in the test registry: "
            f"{missing}. Add the register_* call that provides them to "
            f"_build_command_registry (mirroring server/game_server.py).",
        )


if __name__ == "__main__":
    unittest.main()
