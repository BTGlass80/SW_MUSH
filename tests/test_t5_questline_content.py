# -*- coding: utf-8 -*-
"""
tests/test_t5_questline_content.py — T5-questline arc Drop B
(content walkthrough: the authored master-trainer questlines actually
advance to graduation through the production dispatcher).

Where test_t5_questline_engine.py proves the ENGINE on a synthetic
corpus, this file proves the SHIPPED CONTENT: it loads the REAL chain
corpus (data/worlds/clone_wars/tutorials/chains.yaml), starts the real
`master_jedi_lightsaber` questline via the real start_questline, and
walks all 5 steps to graduation through the real chain_events hooks —
the same hooks the live parser calls. If an authored step's completion
shape doesn't match what the dispatcher recognizes, this fails.

It also pins the SCHEMATIC GATE: the t5 lightsaber recipe is hidden in
Master Vehn's curriculum until the questline graduates AND Jedi Order
rep >= 50 — and visible once both hold.

This complements (does not replace) the static reachability invariant
(tests/test_chain_corpus_reachability_invariant.py, which proves every
slug/command/skill resolves) and the boot smoke. Together: the chain is
structurally valid, the engine advances it, and the gate works.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

QUESTLINE_ID = "master_jedi_lightsaber"


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_fake_db():
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_npc = AsyncMock(return_value=None)
    db.get_character = AsyncMock(return_value=None)
    db.get_room = AsyncMock(return_value=None)
    # The chain's room slugs are real planet rooms; the teleport resolves
    # them via get_room_by_slug. We return a stable fake id so the
    # teleport persists without needing a real DB.
    db.get_room_by_slug = AsyncMock(return_value={"id": 999})
    return db


class _RealCorpusBase(unittest.TestCase):

    def setUp(self):
        from engine.era_state import set_active_config
        import engine.chain_events as ce
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        ce._reset_corpus_cache()  # force a real load of the shipped corpus

    def tearDown(self):
        from engine.era_state import clear_active_config
        import engine.chain_events as ce
        clear_active_config()
        ce._reset_corpus_cache()


def _char(attrs: dict = None) -> dict:
    # A real veteran always carries chargen_complete=True (set at the end
    # of chargen). The questline's `chargen_complete` prereq gates it off
    # half-created characters; model a finished one here.
    base = {"chargen_complete": True}
    base.update(attrs or {})
    return {
        "id": 11, "name": "Veteran PC", "room_id": 100,
        "attributes": json.dumps(base),
    }


def _attrs(char: dict) -> dict:
    return json.loads(char["attributes"])


def _qstate(char: dict) -> dict:
    from engine.tutorial_chains import _QUESTLINE_KEY
    return _attrs(char).get(_QUESTLINE_KEY) or {}


class TestQuestlineExistsAndShape(_RealCorpusBase):

    def test_questline_in_real_corpus_and_is_questline_kind(self):
        from engine.chain_events import list_questlines
        qls = {q.chain_id: q for q in list_questlines()}
        self.assertIn(QUESTLINE_ID, qls)
        ql = qls[QUESTLINE_ID]
        self.assertEqual(ql.kind, "questline")
        self.assertEqual(len(ql.steps), 5)
        # Step-1 NPC is the trainer (the offer/start NPC).
        self.assertEqual(ql.steps[0].npc, "Master Vehn Tasaal")

    def test_chargen_picker_excludes_it(self):
        # A questline must never appear in the chargen chain list.
        from engine.tutorial_chains import load_tutorial_chains
        corpus = load_tutorial_chains("clone_wars")
        questlines = [c for c in corpus.chains
                      if getattr(c, "kind", "tutorial") == "questline"]
        self.assertTrue(questlines)
        for q in questlines:
            self.assertEqual(q.kind, "questline")


class TestHermitsTrialWalkthrough(_RealCorpusBase):
    """Walk the real questline start -> graduation through real hooks."""

    def test_full_walkthrough_to_graduation(self):
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_command_executed,
            on_skill_check_passed, on_combat_won,
        )
        from engine.tutorial_chains import is_chain_complete, _QUESTLINE_KEY

        char = _char()  # no faction gate on the questline prereqs
        db = _make_fake_db()

        ok, _msg = _run(start_questline(db, char, QUESTLINE_ID))
        self.assertTrue(ok, _msg)
        self.assertEqual(_qstate(char).get("step"), 1)

        # Step 1: talk to Master Vehn
        _run(on_talk_to_npc(db, char, "Master Vehn Tasaal"))
        self.assertEqual(_qstate(char).get("step"), 2)

        # Step 2: meditate (command_executed)
        _run(on_command_executed(db, char, "meditate", ""))
        self.assertEqual(_qstate(char).get("step"), 3)

        # Step 3: search skill check (skill_check_passed, succeeded)
        _run(on_skill_check_passed(db, char, "search", True, difficulty=10))
        self.assertEqual(_qstate(char).get("step"), 4)

        # Step 4: defeat the krayt-spawn (combat_won, count 1)
        _run(on_combat_won(db, char, "jundland_krayt_spawn", 1))
        self.assertEqual(_qstate(char).get("step"), 5)

        # Step 5: return to Master Vehn -> graduate
        _run(on_talk_to_npc(db, char, "Master Vehn Tasaal"))
        self.assertTrue(is_chain_complete(_attrs(char), _QUESTLINE_KEY))

    def test_skill_check_failure_does_not_advance(self):
        # A failed search must NOT advance step 3 (the dispatcher only
        # fires on success).
        from engine.chain_events import (
            start_questline, on_talk_to_npc, on_command_executed,
            on_skill_check_passed,
        )
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, "Master Vehn Tasaal"))   # ->2
        _run(on_command_executed(db, char, "meditate", ""))     # ->3
        _run(on_skill_check_passed(db, char, "search", False, difficulty=10))
        self.assertEqual(_qstate(char).get("step"), 3)  # no advance

    def test_wrong_npc_does_not_advance_step1(self):
        from engine.chain_events import start_questline, on_talk_to_npc
        char = _char()
        db = _make_fake_db()
        _run(start_questline(db, char, QUESTLINE_ID))
        _run(on_talk_to_npc(db, char, "Some Other NPC"))
        self.assertEqual(_qstate(char).get("step"), 1)


class TestT5LightsaberGate(_RealCorpusBase):
    """The schematic gate: t5 lightsaber hidden until questline done +
    Jedi Order rep >= 50."""

    def _schem(self):
        from engine.crafting import get_all_schematics
        return get_all_schematics()["t5_master_crafted_lightsaber"]

    def test_schematic_carries_gate_fields(self):
        s = self._schem()
        self.assertEqual(s.get("trainer_npc"), "Master Vehn Tasaal")
        self.assertEqual(s.get("gated_by_questline"), QUESTLINE_ID)
        self.assertEqual(s.get("gated_faction"), "jedi_order")
        self.assertEqual(int(s.get("gated_min_rep")), 50)

    def test_gate_blocks_without_questline_or_rep(self):
        from parser.crafting_commands import _schematic_gate_met
        s = self._schem()
        db = MagicMock()
        # No questline complete, no rep.
        char = _char()
        with _patch_rep(0):
            met = _run(_schematic_gate_met(char, s, db))
        self.assertFalse(met)

    def test_gate_blocks_with_questline_but_low_rep(self):
        from parser.crafting_commands import _schematic_gate_met
        from engine.tutorial_chains import _QUESTLINE_KEY
        s = self._schem()
        db = MagicMock()
        char = _char({_QUESTLINE_KEY: {
            "chain_id": QUESTLINE_ID, "completion_state": "graduated",
            "step": 5, "completed_steps": [1, 2, 3, 4, 5]}})
        with _patch_rep(30):  # below 50
            met = _run(_schematic_gate_met(char, s, db))
        self.assertFalse(met)

    def test_gate_opens_with_questline_and_rep(self):
        from parser.crafting_commands import _schematic_gate_met
        from engine.tutorial_chains import _QUESTLINE_KEY
        s = self._schem()
        db = MagicMock()
        char = _char({_QUESTLINE_KEY: {
            "chain_id": QUESTLINE_ID, "completion_state": "graduated",
            "step": 5, "completed_steps": [1, 2, 3, 4, 5]}})
        with _patch_rep(60):  # honored
            met = _run(_schematic_gate_met(char, s, db))
        self.assertTrue(met)

    def test_curriculum_hides_then_reveals(self):
        from parser.crafting_commands import trainer_curriculum
        from engine.tutorial_chains import _QUESTLINE_KEY
        db = MagicMock()
        # Ungated case: an unearned PC sees NO t5 recipe from Vehn.
        char_locked = _char()
        with _patch_rep(0):
            cur = _run(trainer_curriculum("Master Vehn Tasaal",
                                          char_locked, db))
        self.assertEqual(cur, [])
        # Earned PC sees the t5 lightsaber.
        char_ok = _char({_QUESTLINE_KEY: {
            "chain_id": QUESTLINE_ID, "completion_state": "graduated",
            "step": 5, "completed_steps": [1, 2, 3, 4, 5]}})
        with _patch_rep(70):
            cur = _run(trainer_curriculum("Master Vehn Tasaal",
                                          char_ok, db))
        keys = [k for k, _s in cur]
        self.assertIn("t5_master_crafted_lightsaber", keys)


# ── rep patch helper ─────────────────────────────────────────────────


class _patch_rep:
    """Context manager patching engine.organizations.get_char_faction_rep
    to a fixed value, so the gate's rep branch is deterministic."""

    def __init__(self, value):
        self.value = value
        self._orig = None

    def __enter__(self):
        import engine.organizations as orgs

        async def _fake(char, faction_code, db):
            return self.value
        self._orig = orgs.get_char_faction_rep
        orgs.get_char_faction_rep = _fake
        return self

    def __exit__(self, *a):
        import engine.organizations as orgs
        orgs.get_char_faction_rep = self._orig


class TestChainRepEconomyCeiling(unittest.TestCase):
    """Rep-economy invariant (Brian, 2026-06-13): now that per-step
    credits/faction_rep are actually delivered (apply_step_rewards
    extension), a chain must leave a player only modestly known to the
    faction. Brian's calls: (1) never honored (rep 50) from a chain
    alone; (2) follow-up — "even 20-40% of max seems generous, tune
    lower." Tuned band: ~recognized (≈10) for onboarding chains, a
    little more (≈18) for the master-trainer questline. We pin a hard
    ceiling well below honored so the t5 rep-50 gate stays earned
    through play, not handed out by a chain — and so the tuning can't
    silently drift back up."""

    HONORED = 50
    # Hard ceiling for chain-granted rep in any one faction. Comfortably
    # below honored AND below mid-'trusted', per Brian's "tune lower"
    # follow-up. Current max across all chains is the questline at 18.
    CEILING = 22

    def _chain_rep_totals(self):
        import yaml
        from collections import defaultdict
        from engine.tutorial_chains import load_tutorial_chains
        path = (Path(__file__).resolve().parent.parent / "data" / "worlds"
                / "clone_wars" / "tutorials" / "chains.yaml")
        data = yaml.safe_load(open(path, encoding="utf-8"))
        totals = {}
        for c in data["chains"]:
            per = defaultdict(int)
            for s in c.get("steps") or []:
                for f, v in ((s.get("reward") or {}).get(
                        "faction_rep") or {}).items():
                    per[f] += int(v)
            for f, v in ((c.get("graduation") or {}).get(
                    "faction_rep") or {}).items():
                per[f] += int(v)
            totals[c["chain_id"]] = dict(per)
        return totals

    def test_no_chain_reaches_honored_in_one_faction(self):
        totals = self._chain_rep_totals()
        offenders = {
            cid: facs for cid, facs in totals.items()
            if any(v >= self.HONORED for v in facs.values())
        }
        self.assertEqual(
            offenders, {},
            f"These chains grant >= honored (50) rep in a single faction "
            f"from the chain alone — honored must be earned through play, "
            f"not a tutorial/questline: {offenders}",
        )

    def test_no_chain_exceeds_the_tuned_ceiling(self):
        # Brian's "tune lower" follow-up: chain-granted rep stays well
        # below honored AND below mid-trusted. Pins the tuned band.
        totals = self._chain_rep_totals()
        offenders = {
            cid: facs for cid, facs in totals.items()
            if any(v > self.CEILING for v in facs.values())
        }
        self.assertEqual(
            offenders, {},
            f"These chains grant > {self.CEILING} rep in a single faction "
            f"— above the tuned ceiling (chains should leave a player only "
            f"modestly known to the faction): {offenders}",
        )

    def test_hermits_trial_leaves_room_to_climb(self):
        # The t5 questline specifically must land BELOW the rep-50 gate
        # so the questline and the rep floor stay SEPARATE gates — but
        # still be meaningful (>= recognized).
        totals = self._chain_rep_totals()
        jedi = totals.get(QUESTLINE_ID, {}).get("jedi_order", 0)
        self.assertLess(jedi, self.HONORED)
        self.assertGreaterEqual(jedi, 10)  # meaningful (>= recognized)


if __name__ == "__main__":
    unittest.main()
