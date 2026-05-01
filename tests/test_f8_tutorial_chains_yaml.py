# -*- coding: utf-8 -*-
"""
tests/test_f8_tutorial_chains_yaml.py — F.8 Phase 1 integration tests.

F.8 Phase 1 (Apr 30 2026):
  - data/worlds/clone_wars/tutorials/chains.yaml: 2 zone-slug fixes
    tracking parallel CW zones.yaml renames
    (kamino_tipoca → kamino_tipoca_city, kuat_orbital →
    kuat_main_spaceport).
  - engine/tutorial_chains.py: chain loader + state-machine helpers
    consuming the chains.yaml above.

This file ports the 219 checks of tools/verify_tutorial_chains.py
into pytest as the gating regression for F.8.b runtime integration,
plus state-machine behavior tests covering the new state shape:

    attributes["tutorial_chain"] = {
        "chain_id": <str>, "step": <int>, "started_at": <ts>,
        "completed_steps": [<int>], "completion_state": "active" | "graduated",
    }

Test sections:
  1. TestChainsYAMLShape           — top-level + per-chain shape
  2. TestChainsZoneCrossRefs       — all starting_zone resolve to zones.yaml
                                     + F.8 zone-fix regression guard
  3. TestChainsFactionCrossRefs    — faction_alignment + faction_rep resolve
  4. TestChainsPrerequisites       — flag/dict prereq schema
  5. TestChainsCompletionTypes     — step.completion.type validity
  6. TestJediPathLockedStub        — locked-chain shape
  7. TestChainUniqueness           — chain_id and chain_name are unique
  8. TestLoaderHappyPath           — load_tutorial_chains ok
  9. TestLoaderUnknownEra          — unknown era returns None gracefully
 10. TestStateMachineSelect        — select_chain initializes state
 11. TestStateMachineAdvance       — advance_step walks 1..N then graduates
 12. TestStateMachineLockedChain   — is_chain_locked_for_character logic
 13. TestStateMachineFactionIntent — faction_intent prereq enforcement
 14. TestStateMachineHelpers       — get_current_step / get_active_chain_id /
                                     reset_chain_state / is_chain_complete
 15. TestF8DocstringMarkers        — source-level guards
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


CHAINS_PATH = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
               "tutorials" / "chains.yaml")
ZONES_PATH = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
              "zones.yaml")
ORGS_PATH = (Path(PROJECT_ROOT) / "data" / "worlds" / "clone_wars" /
             "organizations.yaml")


# ──────────────────────────────────────────────────────────────────────
# Shared fixtures
# ──────────────────────────────────────────────────────────────────────

def _load_chains_yaml() -> dict:
    with open(CHAINS_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_zone_keys() -> set:
    with open(ZONES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return set(data["zones"].keys())


def _load_faction_codes() -> set:
    """Load both faction codes and guild codes from organizations.yaml.
    Tutorial chains reference both — Shipwright/Trader aligns to
    shipwrights_guild — so we treat them as a single ID-space for
    cross-reference purposes (mirrors verify_tutorial_chains.py)."""
    with open(ORGS_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    codes = {f["code"] for f in data.get("factions", [])}
    codes |= {g["code"] for g in data.get("guilds", [])}
    return codes


# ──────────────────────────────────────────────────────────────────────
# 1. Top-level + per-chain shape (validator port: §1, §2)
# ──────────────────────────────────────────────────────────────────────

class TestChainsYAMLShape(unittest.TestCase):
    """The chains.yaml file parses as YAML and matches the top-level
    schema. Mirrors verify_tutorial_chains.py::test_top_level."""

    def test_yaml_parses(self):
        data = _load_chains_yaml()
        self.assertIsInstance(data, dict)

    def test_schema_version_is_one(self):
        data = _load_chains_yaml()
        self.assertEqual(data.get("schema_version"), 1)

    def test_chains_key_present(self):
        data = _load_chains_yaml()
        self.assertIn("chains", data)

    def test_chains_is_list(self):
        data = _load_chains_yaml()
        self.assertIsInstance(data["chains"], list)

    def test_chains_count_is_eight(self):
        data = _load_chains_yaml()
        self.assertEqual(len(data["chains"]), 8)

    def test_each_chain_has_required_fields(self):
        data = _load_chains_yaml()
        required = {
            "chain_id", "chain_name", "description", "archetype_label",
            "faction_alignment", "starting_zone", "prerequisites",
            "duration_minutes", "locked", "graduation", "steps",
        }
        for c in data["chains"]:
            cid = c.get("chain_id", "<unknown>")
            missing = required - set(c.keys())
            self.assertFalse(
                missing, f"chain {cid!r} missing fields: {sorted(missing)}",
            )


# ──────────────────────────────────────────────────────────────────────
# 2. starting_zone cross-references (validator port — closes the F.8.1
#    zone-slug-drift gap)
# ──────────────────────────────────────────────────────────────────────

class TestChainsZoneCrossRefs(unittest.TestCase):
    """Every chain's starting_zone resolves to zones.yaml.

    F.8 ships two zone-slug fixes in chains.yaml to track parallel
    renames in CW zones.yaml:
      - kamino_tipoca → kamino_tipoca_city
      - kuat_orbital → kuat_main_spaceport

    These were drift caused by the zones.yaml's working-tree renames
    being authored ahead of the chain content updates. The chains
    file's third drifted slug (jundland_dune_sea_edge) was already
    fixed pre-F.8 to tatooine_dune_sea — F.8 doesn't touch that
    line."""

    def test_all_starting_zones_resolve(self):
        data = _load_chains_yaml()
        zones = _load_zone_keys()
        for c in data["chains"]:
            sz = c["starting_zone"]
            self.assertIn(
                sz, zones,
                f"chain {c['chain_id']!r} starting_zone {sz!r} "
                f"does not resolve to zones.yaml",
            )

    def test_f8_zone_fixes_applied(self):
        """Specific guard for the two F.8 zone-slug fixes."""
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}

        # republic_soldier on Kamino — kamino_tipoca → kamino_tipoca_city
        self.assertEqual(
            chains_by_id["republic_soldier"]["starting_zone"],
            "kamino_tipoca_city",
            "F.8 fix: republic_soldier should anchor at "
            "kamino_tipoca_city, not the pre-F.8 kamino_tipoca",
        )
        # shipwright_trader on Kuat — kuat_orbital → kuat_main_spaceport
        self.assertEqual(
            chains_by_id["shipwright_trader"]["starting_zone"],
            "kuat_main_spaceport",
            "F.8 fix: shipwright_trader should anchor at "
            "kuat_main_spaceport, not the pre-F.8 kuat_orbital",
        )


# ──────────────────────────────────────────────────────────────────────
# 3. Faction cross-references (validator port)
# ──────────────────────────────────────────────────────────────────────

class TestChainsFactionCrossRefs(unittest.TestCase):
    """Every faction_alignment + graduation.faction_rep code resolves
    to organizations.yaml (factions or guilds ID-space)."""

    def test_faction_alignment_resolves(self):
        data = _load_chains_yaml()
        codes = _load_faction_codes()
        for c in data["chains"]:
            fa = c.get("faction_alignment")
            if fa is None:
                continue  # null is allowed for unaligned chains
            self.assertIn(
                fa, codes,
                f"chain {c['chain_id']!r} faction_alignment {fa!r} "
                f"unresolved",
            )

    def test_graduation_faction_rep_resolves(self):
        data = _load_chains_yaml()
        codes = _load_faction_codes()
        for c in data["chains"]:
            grad = c.get("graduation", {})
            for fac, delta in (grad.get("faction_rep") or {}).items():
                self.assertIn(
                    fac, codes,
                    f"chain {c['chain_id']!r} graduation.faction_rep "
                    f"key {fac!r} unresolved",
                )
                self.assertIsInstance(delta, int)


# ──────────────────────────────────────────────────────────────────────
# 4. Prerequisites schema (validator port)
# ──────────────────────────────────────────────────────────────────────

class TestChainsPrerequisites(unittest.TestCase):
    """Prerequisites are either string flags from the allowed set, or
    {key: value} maps where the only allowed key is faction_intent."""

    def test_prerequisite_strings_in_allowed_set(self):
        from engine.tutorial_chains import ALLOWED_PREREQUISITE_FLAGS
        data = _load_chains_yaml()
        for c in data["chains"]:
            for pr in c.get("prerequisites") or []:
                if isinstance(pr, str):
                    self.assertIn(
                        pr, ALLOWED_PREREQUISITE_FLAGS,
                        f"chain {c['chain_id']!r} unknown prerequisite "
                        f"flag {pr!r}",
                    )

    def test_prerequisite_dicts_use_faction_intent_only(self):
        codes = _load_faction_codes()
        data = _load_chains_yaml()
        for c in data["chains"]:
            for pr in c.get("prerequisites") or []:
                if isinstance(pr, dict):
                    for k, v in pr.items():
                        self.assertEqual(
                            k, "faction_intent",
                            f"chain {c['chain_id']!r} unknown mapped "
                            f"prerequisite key {k!r}",
                        )
                        self.assertIn(
                            v, codes,
                            f"chain {c['chain_id']!r} faction_intent "
                            f"{v!r} unresolved",
                        )


# ──────────────────────────────────────────────────────────────────────
# 5. completion.type schema (validator port)
# ──────────────────────────────────────────────────────────────────────

class TestChainsCompletionTypes(unittest.TestCase):
    """Every step.completion.type is in the allowed set."""

    def test_all_completion_types_allowed(self):
        from engine.tutorial_chains import ALLOWED_COMPLETION_TYPES
        data = _load_chains_yaml()
        for c in data["chains"]:
            for step in c.get("steps") or []:
                ct = step.get("completion", {}).get("type")
                self.assertIn(
                    ct, ALLOWED_COMPLETION_TYPES,
                    f"chain {c['chain_id']!r} step {step.get('step')} "
                    f"completion.type {ct!r} not allowed",
                )

    def test_npc_role_allowed(self):
        from engine.tutorial_chains import ALLOWED_NPC_ROLES
        data = _load_chains_yaml()
        for c in data["chains"]:
            for step in c.get("steps") or []:
                role = step.get("npc_role")
                self.assertIn(
                    role, ALLOWED_NPC_ROLES,
                    f"chain {c['chain_id']!r} step {step.get('step')} "
                    f"npc_role {role!r} not allowed",
                )


# ──────────────────────────────────────────────────────────────────────
# 6. Jedi Path locked stub (validator port)
# ──────────────────────────────────────────────────────────────────────

class TestJediPathLockedStub(unittest.TestCase):
    """The Jedi Path chain is correctly stubbed and locked."""

    def test_jedi_path_present(self):
        data = _load_chains_yaml()
        ids = [c["chain_id"] for c in data["chains"]]
        self.assertIn("jedi_path", ids)

    def test_jedi_path_is_locked(self):
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}
        self.assertTrue(chains_by_id["jedi_path"].get("locked"))

    def test_jedi_path_has_locked_message(self):
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}
        self.assertTrue(chains_by_id["jedi_path"].get("locked_message"))

    def test_jedi_path_requires_unlock_flag(self):
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}
        self.assertIn(
            "jedi_path_unlocked",
            chains_by_id["jedi_path"]["prerequisites"],
        )

    def test_jedi_path_requires_force_sensitive(self):
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}
        self.assertIn(
            "force_sensitive",
            chains_by_id["jedi_path"]["prerequisites"],
        )

    def test_jedi_path_duration_zero(self):
        data = _load_chains_yaml()
        chains_by_id = {c["chain_id"]: c for c in data["chains"]}
        self.assertEqual(
            chains_by_id["jedi_path"].get("duration_minutes"), 0,
        )


# ──────────────────────────────────────────────────────────────────────
# 7. Chain uniqueness (validator port)
# ──────────────────────────────────────────────────────────────────────

class TestChainUniqueness(unittest.TestCase):

    def test_chain_ids_unique(self):
        data = _load_chains_yaml()
        ids = [c["chain_id"] for c in data["chains"]]
        self.assertEqual(len(ids), len(set(ids)),
                         f"duplicate chain_ids: {ids}")

    def test_chain_names_unique(self):
        data = _load_chains_yaml()
        names = [c["chain_name"] for c in data["chains"]]
        self.assertEqual(len(names), len(set(names)),
                         f"duplicate chain_names: {names}")


# ──────────────────────────────────────────────────────────────────────
# 8. Loader happy path
# ──────────────────────────────────────────────────────────────────────

class TestLoaderHappyPath(unittest.TestCase):
    """load_tutorial_chains(era='clone_wars') returns a clean corpus."""

    def test_corpus_loads_clean(self):
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains(era="clone_wars")
        self.assertIsNotNone(corpus)
        self.assertTrue(corpus.ok,
                        f"corpus had errors: {corpus.errors[:3]}")

    def test_corpus_has_eight_chains(self):
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains(era="clone_wars")
        self.assertEqual(len(corpus.chains), 8)

    def test_corpus_by_id_lookup(self):
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains(era="clone_wars")
        by_id = corpus.by_id()
        for cid in ("republic_soldier", "jedi_path", "smuggler",
                    "shipwright_trader"):
            self.assertIn(cid, by_id)

    def test_step_dataclasses_typed(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, TutorialStep,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        rs = corpus.by_id()["republic_soldier"]
        self.assertEqual(len(rs.steps), 5)
        for step in rs.steps:
            self.assertIsInstance(step, TutorialStep)


# ──────────────────────────────────────────────────────────────────────
# 9. Loader: unknown era returns None gracefully
# ──────────────────────────────────────────────────────────────────────

class TestLoaderUnknownEra(unittest.TestCase):
    """An era without a tutorials/chains.yaml file returns None,
    not an error."""

    def test_gcw_returns_none(self):
        from engine.tutorial_chains import load_tutorial_chains
        # GCW has no chain-based tutorial
        result = load_tutorial_chains(era="gcw")
        self.assertIsNone(result)

    def test_unknown_era_returns_none(self):
        from engine.tutorial_chains import load_tutorial_chains
        result = load_tutorial_chains(era="fake_era_for_test")
        self.assertIsNone(result)


# ──────────────────────────────────────────────────────────────────────
# 10. State machine: chain selection
# ──────────────────────────────────────────────────────────────────────

class TestStateMachineSelect(unittest.TestCase):

    def test_select_initializes_state(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["republic_soldier"]
        char = {"chargen_complete": True, "faction_intent": "republic"}
        select_chain(char, chain, now=1234567890)

        self.assertIn("tutorial_chain", char)
        state = char["tutorial_chain"]
        self.assertEqual(state["chain_id"], "republic_soldier")
        self.assertEqual(state["step"], 1)
        self.assertEqual(state["started_at"], 1234567890)
        self.assertEqual(state["completed_steps"], [])
        self.assertEqual(state["completion_state"], "active")

    def test_select_returns_state_block(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        result = select_chain(char, chain, now=42)
        self.assertEqual(result["chain_id"], "smuggler")
        # Also persisted in char attrs
        self.assertEqual(char["tutorial_chain"], result)


# ──────────────────────────────────────────────────────────────────────
# 11. State machine: step advancement and graduation
# ──────────────────────────────────────────────────────────────────────

class TestStateMachineAdvance(unittest.TestCase):

    def test_walk_chain_to_graduation(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain, advance_step,
            get_current_step, is_chain_complete,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["republic_soldier"]
        char = {"chargen_complete": True, "faction_intent": "republic"}
        select_chain(char, chain, now=0)

        # Walk through 5 steps; 5th advance should graduate
        for expected_step_num in range(1, 6):
            current = get_current_step(char, corpus)
            self.assertIsNotNone(current)
            self.assertEqual(current.step, expected_step_num)
            new_step, graduated = advance_step(char, corpus)
            if expected_step_num < 5:
                self.assertFalse(graduated)
                self.assertIsNotNone(new_step)
            else:
                self.assertTrue(graduated)
                self.assertIsNone(new_step)

        # State is now graduated
        self.assertTrue(is_chain_complete(char))
        self.assertIsNone(get_current_step(char, corpus))

    def test_completed_steps_accumulate(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain, advance_step,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        select_chain(char, chain)
        advance_step(char, corpus)
        advance_step(char, corpus)
        self.assertEqual(
            char["tutorial_chain"]["completed_steps"], [1, 2],
        )

    def test_advance_with_no_active_chain(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, advance_step,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        char = {"chargen_complete": True}
        new_step, graduated = advance_step(char, corpus)
        self.assertIsNone(new_step)
        self.assertFalse(graduated)


# ──────────────────────────────────────────────────────────────────────
# 12. State machine: locked-chain rejection
# ──────────────────────────────────────────────────────────────────────

class TestStateMachineLockedChain(unittest.TestCase):

    def test_jedi_path_locked_for_normal_pc(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["jedi_path"]
        char = {"chargen_complete": True}
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertTrue(is_locked)
        # Reason should include the chain's locked_message text
        self.assertIn("Jedi", reason)

    def test_jedi_path_unlocked_with_all_flags(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["jedi_path"]
        char = {
            "chargen_complete": True,
            "force_sensitive": True,
            "jedi_path_unlocked": True,
        }
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertFalse(is_locked,
                         f"Jedi Path should be unlocked when all "
                         f"flags set; reason: {reason!r}")

    def test_unlocked_chain_with_missing_chargen(self):
        """An unlocked chain whose prereqs aren't met still gets
        rejected, but with a different message than locked chains."""
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {}  # No chargen_complete
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertTrue(is_locked)
        # Generic prereq-missing message, not Jedi-specific
        self.assertNotIn("Jedi", reason)
        self.assertIn("requirements", reason.lower())

    def test_unlocked_chain_with_all_prereqs(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertFalse(is_locked)


# ──────────────────────────────────────────────────────────────────────
# 13. State machine: faction_intent enforcement
# ──────────────────────────────────────────────────────────────────────

class TestStateMachineFactionIntent(unittest.TestCase):
    """faction_intent is a {key: value} prereq. The character's
    `faction_intent` attribute must exactly match the chain's required
    value."""

    def test_republic_chain_blocked_for_unaligned_pc(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["republic_soldier"]
        char = {"chargen_complete": True}  # No faction_intent
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertTrue(is_locked)

    def test_republic_chain_blocked_for_cis_intent(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["republic_soldier"]
        char = {"chargen_complete": True, "faction_intent": "cis"}
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertTrue(is_locked)

    def test_republic_chain_unlocked_for_republic_intent(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["republic_soldier"]
        char = {"chargen_complete": True, "faction_intent": "republic"}
        is_locked, reason = is_chain_locked_for_character(chain, char)
        self.assertFalse(is_locked,
                         f"Republic chain should unlock for republic "
                         f"intent; reason: {reason!r}")


# ──────────────────────────────────────────────────────────────────────
# 14. State machine: helpers
# ──────────────────────────────────────────────────────────────────────

class TestStateMachineHelpers(unittest.TestCase):

    def test_get_active_chain_id_when_active(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain, get_active_chain_id,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        select_chain(char, chain)
        self.assertEqual(get_active_chain_id(char), "smuggler")

    def test_get_active_chain_id_when_no_chain(self):
        from engine.tutorial_chains import get_active_chain_id
        self.assertIsNone(get_active_chain_id({}))

    def test_get_active_chain_id_when_graduated(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain, advance_step,
            get_active_chain_id,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        select_chain(char, chain)
        # Walk to graduation
        while not char["tutorial_chain"]["completion_state"] == "graduated":
            new_step, grad = advance_step(char, corpus)
            if grad:
                break
        # No active chain after graduation
        self.assertIsNone(get_active_chain_id(char))

    def test_reset_chain_state_clears(self):
        from engine.tutorial_chains import (
            load_tutorial_chains, select_chain, reset_chain_state,
        )
        corpus = load_tutorial_chains(era="clone_wars")
        chain = corpus.by_id()["smuggler"]
        char = {"chargen_complete": True}
        select_chain(char, chain)
        self.assertIn("tutorial_chain", char)
        reset_chain_state(char)
        self.assertNotIn("tutorial_chain", char)

    def test_reset_chain_state_no_op_when_absent(self):
        from engine.tutorial_chains import reset_chain_state
        char = {"foo": "bar"}
        reset_chain_state(char)  # Should not raise
        self.assertEqual(char, {"foo": "bar"})


# ──────────────────────────────────────────────────────────────────────
# 15. Source-level guards
# ──────────────────────────────────────────────────────────────────────

class TestF8DocstringMarkers(unittest.TestCase):

    def test_engine_module_present(self):
        from engine import tutorial_chains
        for name in (
            "load_tutorial_chains", "TutorialChain", "TutorialStep",
            "Graduation", "TutorialChainsCorpus",
            "is_chain_locked_for_character", "select_chain",
            "get_current_step", "advance_step", "is_chain_complete",
            "get_active_chain_id", "reset_chain_state",
            "ALLOWED_COMPLETION_TYPES", "ALLOWED_NPC_ROLES",
            "ALLOWED_PREREQUISITE_FLAGS",
        ):
            self.assertTrue(
                hasattr(tutorial_chains, name),
                f"engine.tutorial_chains missing {name}",
            )

    def test_f8_marker_in_engine_module(self):
        from engine import tutorial_chains
        with open(tutorial_chains.__file__, "r", encoding="utf-8") as f:
            src = f.read()
        self.assertIn("F.8 (Apr 30 2026)", src)
        # Phase split documented
        self.assertIn("Phase 1", src)
        self.assertIn("Phase 2", src)

    def test_chains_yaml_has_eight_chain_entries(self):
        with open(CHAINS_PATH, "r", encoding="utf-8") as f:
            src = f.read()
        # 8 chain_id entries
        self.assertEqual(src.count("chain_id:"), 8)


if __name__ == "__main__":
    unittest.main()
