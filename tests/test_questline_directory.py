# -*- coding: utf-8 -*-
"""
tests/test_questline_directory.py — the `mastery browse` galaxy-wide
questline directory (discoverability surface).

Background. Questlines (`kind: questline` chains) are opt-in mid-game
arcs started via `mastery start <id>`. Before this drop the ONLY way to
learn a questline existed was to physically stand with its giver NPC and
`talk` (or `mastery` in that room) — `get_questline_offer` is room-scoped.
With 15 questlines (5 master-trainer + 10 accessible freelance arcs)
scattered across Nar Shaddaa / Tatooine / Coruscant / Kuat / Geonosis,
that made nearly all of them invisible: real launch content nobody could
find.

This drop adds `engine.chain_events.list_questline_directory(char)` (a
pure read over the same corpus + gate the in-room offer uses) and the
`mastery browse` consumer that renders it. It surfaces NO capability
`mastery start` didn't already grant — `start_questline` already validates
the gate and teleports from anywhere, so the only thing previously hidden
was the EXISTENCE of an id, not access to it. The directory honestly shows
locked arcs (dimmed, with the gate reason) and `start` still enforces
every gate.

These tests pin:
  * the engine helper enumerates the whole corpus and partitions it by
    the character's standing (available / locked / completed / active);
  * the partition agrees with the gate (`is_chain_locked_for_character`)
    and with the in-room offer (`get_questline_offer`) — directory and
    talk-offer never disagree about eligibility;
  * the one-at-a-time rule surfaces (an active questline pins to the top
    and the others are reported but flagged not-yet-startable);
  * the `mastery browse` parser command renders the directory + start ids,
    and `mastery all`/`directory`/`catalog` alias to it;
  * the bare-`mastery` no-offer fallback now points at `mastery browse`.
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def _plain(parts) -> str:
    return _ANSI_RE.sub("", "\n".join(parts))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _char(attrs: dict = None) -> dict:
    base = {"chargen_complete": True}
    base.update(attrs or {})
    return {
        "id": 7, "name": "Browser PC", "room_id": 100,
        "attributes": json.dumps(base),
    }


class _RealCorpusBase(unittest.TestCase):
    def setUp(self):
        from engine.era_state import set_active_config
        import engine.chain_events as ce
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        ce._reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        import engine.chain_events as ce
        clear_active_config()
        ce._reset_corpus_cache()

    def _directory(self, char):
        from engine.chain_events import list_questline_directory
        return list_questline_directory(char)


# ── Engine helper ─────────────────────────────────────────────────────


class TestDirectoryEngineHelper(_RealCorpusBase):

    def test_enumerates_entire_questline_corpus(self):
        from engine.chain_events import list_questlines
        all_qls = list_questlines()
        self.assertGreaterEqual(len(all_qls), 10,
                                "corpus should hold the questline catalog")
        directory = self._directory(_char())
        self.assertEqual(
            {e["chain_id"] for e in directory},
            {q.chain_id for q in all_qls},
            "directory must list EVERY kind:questline chain, no more/less")

    def test_entry_shape_complete(self):
        directory = self._directory(_char())
        required = {
            "chain_id", "chain_name", "archetype_label", "faction_alignment",
            "giver_npc", "start_zone", "start_location", "objective",
            "status", "reason",
        }
        for e in directory:
            self.assertTrue(required.issubset(e.keys()),
                            f"missing keys on {e.get('chain_id')}")
            # Every questline must name a giver + a start location so the
            # directory line is never a dead pointer.
            self.assertTrue(e["giver_npc"],
                            f"{e['chain_id']} has no giver NPC")
            self.assertTrue(e["start_location"],
                            f"{e['chain_id']} has no start location")
            self.assertIn(e["status"],
                          {"available", "locked", "completed", "active"})

    def test_fresh_chargen_char_all_available(self):
        # Every shipped questline is gated only on chargen_complete, so a
        # fresh character sees them ALL as startable — that is exactly the
        # content that was previously undiscoverable.
        directory = self._directory(_char())
        statuses = {e["status"] for e in directory}
        self.assertEqual(statuses, {"available"},
                         "a chargen-complete char should find every "
                         "questline available")
        for e in directory:
            self.assertEqual(e["reason"], "",
                             "available entries carry no lock reason")

    def test_pre_chargen_char_all_locked_with_reason(self):
        # A character missing chargen_complete is locked out of every
        # questline; the directory reports each with a non-empty reason
        # (the gate's own message), never silently dropping it.
        char = {"id": 8, "name": "Nascent", "room_id": 1,
                "attributes": json.dumps({})}
        directory = self._directory(char)
        self.assertTrue(directory, "directory still lists the catalog")
        for e in directory:
            self.assertEqual(e["status"], "locked", e["chain_id"])
            self.assertTrue(e["reason"], f"{e['chain_id']} lock has no reason")

    def test_completed_questline_partitioned_and_ordered_last(self):
        from engine.tutorial_chains import _QUESTLINE_KEY
        target = self._directory(_char())[0]["chain_id"]
        char = _char({_QUESTLINE_KEY: {
            "chain_id": target, "completion_state": "graduated"}})
        directory = self._directory(char)
        by_id = {e["chain_id"]: e for e in directory}
        self.assertEqual(by_id[target]["status"], "completed")
        # Completed sorts to the tail.
        statuses = [e["status"] for e in directory]
        self.assertEqual(statuses[-1], "completed",
                         "completed entries order last")
        # Everything else stays available.
        others = [e for e in directory if e["chain_id"] != target]
        self.assertTrue(all(e["status"] == "available" for e in others))

    def test_active_questline_pinned_first(self):
        from engine.tutorial_chains import _QUESTLINE_KEY
        target = self._directory(_char())[0]["chain_id"]
        char = _char({_QUESTLINE_KEY: {
            "chain_id": target, "completion_state": "active", "step": 1}})
        directory = self._directory(char)
        self.assertEqual(directory[0]["chain_id"], target)
        self.assertEqual(directory[0]["status"], "active")
        # Exactly one active (one-at-a-time slot).
        self.assertEqual(
            sum(1 for e in directory if e["status"] == "active"), 1)
        # The rest are reported (still available status) — the parser adds
        # the "finish your active questline first" caveat at render time.
        others = [e for e in directory if e["chain_id"] != target]
        self.assertTrue(all(e["status"] == "available" for e in others))

    def test_directory_agrees_with_in_room_offer(self):
        # The directory and a per-giver `talk` offer must never disagree
        # about eligibility — both run the SAME gate. For each available
        # entry, talking to its giver yields an unlocked offer for the
        # same chain.
        from engine.chain_events import get_questline_offer
        char = _char()
        directory = self._directory(char)
        for e in directory:
            if e["status"] != "available":
                continue
            offer = get_questline_offer(char, e["giver_npc"])
            self.assertIsNotNone(
                offer, f"giver {e['giver_npc']} offers nothing")
            self.assertFalse(
                offer.get("locked"),
                f"directory says available but offer is locked: "
                f"{e['chain_id']}")
            # The giver's offered chain is among the directory entries for
            # that giver (givers map 1:1 to a questline by design).
            self.assertEqual(offer["chain_id"], e["chain_id"])


# ── Parser command ────────────────────────────────────────────────────


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = True
        self.sent = []

    async def send_line(self, line=""):
        self.sent.append(line)


def _ctx(session, args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"mastery {args}".strip(),
        command="mastery",
        args=args,
        args_list=args.split() if args else [],
        db=None,
        session_mgr=None,
    )


class TestMasteryBrowseCommand(_RealCorpusBase):

    def _browse(self, char, args="browse"):
        from parser.questline_commands import QuestCommand
        sess = _FakeSession(char)
        ctx = _ctx(sess, args=args)
        _run(QuestCommand().execute(ctx))
        return _plain(sess.sent), sess.sent

    def test_browse_renders_directory_and_start_ids(self):
        out, _ = self._browse(_char())
        self.assertIn("GALAXY QUESTLINE DIRECTORY", out)
        self.assertIn("AVAILABLE NOW", out)
        # The exact `mastery start <id>` is rendered for accessible arcs,
        # so the directory is actionable, not just informational.
        from engine.chain_events import list_questlines
        ids = [q.chain_id for q in list_questlines()]
        rendered_ids = [cid for cid in ids
                        if f"mastery start {cid}" in out]
        self.assertEqual(
            len(rendered_ids), len(ids),
            "every available questline shows its start id")

    def test_browse_aliases_route_to_browse(self):
        for alias in ("all", "directory", "catalog"):
            out, _ = self._browse(_char(), args=alias)
            self.assertIn("GALAXY QUESTLINE DIRECTORY", out,
                          f"`mastery {alias}` should open the directory")

    def test_browse_with_active_shows_caveat(self):
        from engine.tutorial_chains import _QUESTLINE_KEY
        from engine.chain_events import list_questlines
        target = list_questlines()[0].chain_id
        char = _char({_QUESTLINE_KEY: {
            "chain_id": target, "completion_state": "active", "step": 1}})
        out, _ = self._browse(char)
        self.assertIn("ACTIVE", out)
        # While on a questline, others are not directly startable — the
        # caveat appears instead of bare start lines.
        self.assertIn("finish your active questline first", out)

    def test_browse_with_completed_lists_it_done(self):
        from engine.tutorial_chains import _QUESTLINE_KEY
        from engine.chain_events import list_questlines
        target = list_questlines()[0]
        char = _char({_QUESTLINE_KEY: {
            "chain_id": target.chain_id, "completion_state": "graduated"}})
        out, _ = self._browse(char)
        self.assertIn("COMPLETED", out)
        self.assertIn(target.chain_name, out)

    def test_bare_mastery_no_offer_points_to_browse(self):
        # A player with no active questline standing in a room with no
        # giver gets nudged to `mastery browse` rather than dead-ended.
        from parser.questline_commands import QuestCommand

        class _NoNPCDB:
            async def get_npcs_in_room(self, room_id):
                return []

        sess = _FakeSession(_char())
        from parser.commands import CommandContext
        ctx = CommandContext(
            session=sess, raw_input="mastery", command="mastery",
            args="", args_list=[], db=_NoNPCDB(), session_mgr=None,
        )
        _run(QuestCommand().execute(ctx))
        out = _plain(sess.sent)
        self.assertIn("no active questline", out.lower())
        self.assertIn("mastery browse", out)


if __name__ == "__main__":
    unittest.main()
