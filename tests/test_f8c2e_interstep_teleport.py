# -*- coding: utf-8 -*-
"""
tests/test_f8c2e_interstep_teleport.py — F.8.c.2.e inter-step teleport.

Closes the movement gap that stranded players mid-chain. The tutorial
rooms (data/worlds/clone_wars/tutorials/rooms.yaml) carry NO walkable
exits by policy — the header EXIT POLICY promises the chain state
machine relays the player between step rooms on advancement. That
relay existed ONLY for graduation (engine/chain_graduation.apply_
graduation); the inter-step case was never implemented, so a player
stranded at the first step whose authored ``location`` differed from
the chain's ``starting_room``. The reported symptom: a fresh bounty
hunter accepts the Tarko Vinn bounty at the chapter house (step 2),
advances to step 3 (the warrens), and is never moved — ``chain
attempt`` then refuses via its location guard.

This drop adds:
  * engine/chain_graduation.py::apply_step_teleport — engine-side
    inter-step move (resolve slug, persist room, stamp
    ``pending_step_room_id``). Distinct flag from graduation so the
    parser finisher delivers an ordinary arrival, not the graduation
    summary.
  * engine/chain_events.py::_try_advance — calls apply_step_teleport
    on a non-graduation advance (the ``elif new_step is not None``
    branch).
  * engine/chain_graduation.py::execute_pending_teleport — now handles
    BOTH the graduation flag (terminal flavor + reward summary, take
    priority) and the inter-step flag (light "you make your way"
    arrival). _clear_pending drops either flag.
  * parser/faction_commands.py — ``+factions``/``factions`` aliased to
    the ``+faction`` umbrella so the graduation step (all 7 chains'
    final ``command_executed: +factions``) actually resolves and fires
    the chain hook.

Test sections
-------------
   1. TestApplyStepTeleport     — engine-side inter-step persistence
   2. TestStepTeleportUI        — parser finisher renders arrival
   3. TestEndToEndInterStep     — _try_advance teleports on advance
                                  (incl. the bounty_hunter repro)
   4. TestFactionsAlias         — +factions resolves to the umbrella
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


def _fresh_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)


def _run(coro):
    _fresh_loop()
    return asyncio.get_event_loop().run_until_complete(coro)


class _MockDB:
    """Minimal async DB stand-in. Records save_character calls and
    answers get_room / get_room_by_slug from a small in-memory map.
    Mirrors tests/test_f8c2c_chain_graduation.py::_MockDB."""

    def __init__(self):
        self.rooms = {}
        self.slug_to_room = {}
        self.save_calls = []
        self.save_should_raise = False

    def add_room(self, room_id: int, name: str, slug: str = ""):
        props = {"slug": slug} if slug else {}
        room = {
            "id": room_id, "name": name,
            "properties": json.dumps(props),
        }
        self.rooms[room_id] = room
        if slug:
            self.slug_to_room[slug] = room

    async def get_room(self, room_id):
        return self.rooms.get(int(room_id))

    async def get_room_by_slug(self, slug):
        if not slug or not slug.strip():
            return None
        return self.slug_to_room.get(slug.strip())

    async def save_character(self, char_id, **kwargs):
        if self.save_should_raise:
            raise RuntimeError("save_character intentional failure")
        self.save_calls.append((char_id, kwargs))


def _char(char_id=1, room_id=10, attrs=None):
    return {
        "id": char_id,
        "name": "TestPC",
        "room_id": room_id,
        "attributes": json.dumps(attrs or {}),
    }


# ─────────────────────────────────────────────────────────────────────
# 1. apply_step_teleport
# ─────────────────────────────────────────────────────────────────────


class TestApplyStepTeleport(unittest.TestCase):

    def test_persists_room_and_stamps_step_flag(self):
        from engine.chain_graduation import apply_step_teleport
        db = _MockDB()
        db.add_room(613, "Warrens Safehouse",
                    "nar_shaddaa_warrens_safehouse")
        char = _char(char_id=5, room_id=612)
        attrs = {"tutorial_chain": {
            "chain_id": "bounty_hunter", "step": 3,
            "completion_state": "active",
        }}
        result = _run(apply_step_teleport(
            db, char, attrs, "nar_shaddaa_warrens_safehouse"))

        self.assertEqual(result, 613)
        # save_character called with the new room_id
        self.assertEqual(len(db.save_calls), 1)
        _cid, kwargs = db.save_calls[0]
        self.assertEqual(kwargs.get("room_id"), 613)
        # in-tick char dict mutated
        self.assertEqual(char["room_id"], 613)
        # the STEP flag is stamped, NOT the graduation flag
        state = attrs["tutorial_chain"]
        self.assertEqual(state["pending_step_room_id"], 613)
        self.assertNotIn("pending_drop_room_id", state)

    def test_no_op_when_already_in_room(self):
        from engine.chain_graduation import apply_step_teleport
        db = _MockDB()
        db.add_room(612, "Chapter House",
                    "nar_shaddaa_bhg_chapter_house")
        char = _char(room_id=612)  # already here
        attrs = {"tutorial_chain": {}}
        result = _run(apply_step_teleport(
            db, char, attrs, "nar_shaddaa_bhg_chapter_house"))
        self.assertEqual(result, 612)
        # No move, no flag (consecutive steps share a room)
        self.assertEqual(len(db.save_calls), 0)
        self.assertNotIn(
            "pending_step_room_id", attrs.get("tutorial_chain", {}))

    def test_no_op_for_empty_or_none_slug(self):
        from engine.chain_graduation import apply_step_teleport
        db = _MockDB()
        char = _char(room_id=10)
        attrs = {"tutorial_chain": {}}
        self.assertIsNone(_run(apply_step_teleport(db, char, attrs, "")))
        self.assertIsNone(_run(apply_step_teleport(db, char, attrs, None)))
        self.assertIsNone(
            _run(apply_step_teleport(db, char, attrs, "   ")))
        self.assertEqual(len(db.save_calls), 0)
        self.assertEqual(char["room_id"], 10)

    def test_returns_none_for_unresolvable_slug(self):
        from engine.chain_graduation import apply_step_teleport
        db = _MockDB()
        char = _char(room_id=10)
        attrs = {"tutorial_chain": {}}
        result = _run(apply_step_teleport(db, char, attrs, "no_such_room"))
        self.assertIsNone(result)
        # Failure-tolerant: player stays put, no flag, no strand-worse
        self.assertEqual(char["room_id"], 10)
        self.assertEqual(len(db.save_calls), 0)
        self.assertNotIn(
            "pending_step_room_id", attrs.get("tutorial_chain", {}))

    def test_returns_none_when_save_fails(self):
        from engine.chain_graduation import apply_step_teleport
        db = _MockDB()
        db.add_room(613, "Warrens", "warrens_slug")
        db.save_should_raise = True
        char = _char(room_id=612)
        attrs = {"tutorial_chain": {}}
        result = _run(apply_step_teleport(db, char, attrs, "warrens_slug"))
        self.assertIsNone(result)
        # room not changed because persist failed
        self.assertEqual(char["room_id"], 612)


# ─────────────────────────────────────────────────────────────────────
# 2. execute_pending_teleport — inter-step arrival rendering
# ─────────────────────────────────────────────────────────────────────


class _MockSession:
    def __init__(self):
        self.character = None
        self.lines = []

    async def send_line(self, line: str):
        self.lines.append(line)


class _MockSessionMgr:
    def __init__(self):
        self._registry = {}


class _MockCtx:
    def __init__(self, db=None, session=None, session_mgr=None,
                 raw_input="", command="", args="", args_list=None):
        self.db = db
        self.session = session
        self.session_mgr = session_mgr
        self.raw_input = raw_input
        self.command = command
        self.args = args
        self.args_list = args_list or []


class _MockLookCommand:
    def __init__(self):
        self.calls = 0

    async def execute(self, ctx):
        self.calls += 1
        await ctx.session.send_line("[mock-look output]")


class TestStepTeleportUI(unittest.TestCase):

    def _setup(self, char_room_id=612, pending_room_id=613,
               flag="pending_step_room_id"):
        db = _MockDB()
        db.add_room(pending_room_id, "Warrens Safehouse", "warrens_slug")
        db.add_room(char_room_id, "Chapter House", "chapter_slug")
        attrs = {"tutorial_chain": {
            "chain_id": "bounty_hunter", "step": 3,
            "completion_state": "active",
            flag: pending_room_id,
        }}
        char = _char(char_id=5, room_id=char_room_id, attrs=attrs)
        session = _MockSession()
        session.character = char
        session_mgr = _MockSessionMgr()
        look = _MockLookCommand()
        session_mgr._registry["look"] = look
        ctx = _MockCtx(db, session, session_mgr)
        return db, char, session, ctx, look

    def test_inter_step_delivers_light_arrival_and_clears_flag(self):
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, ctx, look = self._setup()

        result = _run(execute_pending_teleport(ctx, char))
        self.assertTrue(result)
        # synthetic look ran
        self.assertEqual(look.calls, 1)
        # session room synced
        self.assertEqual(ctx.session.character["room_id"], 613)
        # the STEP flag was cleared
        attrs = json.loads(char["attributes"])
        self.assertNotIn(
            "pending_step_room_id", attrs.get("tutorial_chain", {}))

    def test_inter_step_does_not_show_graduation_flavor(self):
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, ctx, look = self._setup()
        _run(execute_pending_teleport(ctx, char))
        joined = "\n".join(session.lines)
        # No terminal "training complete" line on a mid-chain move
        self.assertNotIn("training is complete", joined.lower())
        # The light relocation line IS present
        self.assertIn("make your way", joined.lower())

    def test_graduation_flag_still_shows_graduation_flavor(self):
        # Regression guard: the graduation path is unchanged and takes
        # priority — same finisher, graduation flag set.
        from engine.chain_graduation import execute_pending_teleport
        db, char, session, ctx, look = self._setup(
            flag="pending_drop_room_id")
        _run(execute_pending_teleport(ctx, char))
        joined = "\n".join(session.lines).lower()
        self.assertIn("training is complete", joined)


# ─────────────────────────────────────────────────────────────────────
# 3. End-to-end via _try_advance
# ─────────────────────────────────────────────────────────────────────


class TestEndToEndInterStep(unittest.TestCase):
    """Verify _try_advance teleports the player to the NEW step's room
    on a non-graduation advance, against the real CW corpus."""

    def setUp(self):
        from engine.era_state import set_active_config
        from engine.chain_events import _reset_corpus_cache
        set_active_config(types.SimpleNamespace(active_era="clone_wars"))
        _reset_corpus_cache()

    def tearDown(self):
        from engine.era_state import clear_active_config
        from engine.chain_events import _reset_corpus_cache
        clear_active_config()
        _reset_corpus_cache()

    def test_bounty_hunter_accept_moves_player_to_warrens(self):
        """THE REPRODUCTION: a fresh bounty hunter at step 2 (chapter
        house) accepts the Tarko Vinn bounty and is relayed to the
        warrens (step 3) instead of being stranded."""
        from engine.chain_events import on_bounty_accepted

        db = _MockDB()
        db.add_room(612, "BHG Chapter House",
                    "nar_shaddaa_bhg_chapter_house")
        db.add_room(613, "Warrens Safehouse",
                    "nar_shaddaa_warrens_safehouse")

        attrs = {"tutorial_chain": {
            "chain_id": "bounty_hunter",
            "step": 2,
            "started_at": 1000000,
            "completed_steps": [1],
            "completion_state": "active",
        }}
        char = {
            "id": 7, "name": "Hunter", "room_id": 612,
            "attributes": json.dumps(attrs),
        }

        result = _run(on_bounty_accepted(
            db, char, "tutorial_bhg_tarko_vinn"))
        self.assertTrue(result, "bounty accept should advance the chain")

        # Player is now in the warrens, not stranded at the chapter house
        self.assertEqual(char["room_id"], 613)

        new_attrs = json.loads(char["attributes"])
        state = new_attrs["tutorial_chain"]
        self.assertEqual(state["step"], 3)
        self.assertEqual(state["completion_state"], "active")
        self.assertEqual(state["pending_step_room_id"], 613)
        # Not a graduation
        self.assertNotIn("pending_drop_room_id", state)

    def test_command_step_advance_teleports(self):
        """separatist_commando step 1 (+sheet, briefing) -> step 2
        (drill pit). The +sheet advance should relay the player to the
        drill pit room."""
        from engine.chain_events import on_command_executed

        db = _MockDB()
        db.add_room(200, "Cadre Briefing", "geonosis_foundry_briefing")
        db.add_room(201, "Drill Pit", "geonosis_foundry_drill_pit")

        attrs = {"tutorial_chain": {
            "chain_id": "separatist_commando",
            "step": 1,
            "started_at": 1000000,
            "completed_steps": [],
            "completion_state": "active",
        }}
        char = {
            "id": 8, "name": "Commando", "room_id": 200,
            "attributes": json.dumps(attrs),
        }

        result = _run(on_command_executed(db, char, "+sheet", ""))
        self.assertTrue(result)
        self.assertEqual(char["room_id"], 201)
        state = json.loads(char["attributes"])["tutorial_chain"]
        self.assertEqual(state["step"], 2)
        self.assertEqual(state["pending_step_room_id"], 201)

    def test_unresolvable_next_room_does_not_strand_worse(self):
        """If the next step's room slug can't be resolved (not staged
        in the DB), the advance still happens; the player simply stays
        put rather than vanishing. Failure-tolerance guard."""
        from engine.chain_events import on_bounty_accepted

        db = _MockDB()
        db.add_room(612, "BHG Chapter House",
                    "nar_shaddaa_bhg_chapter_house")
        # NOTE: deliberately NOT staging the warrens room.
        attrs = {"tutorial_chain": {
            "chain_id": "bounty_hunter", "step": 2,
            "started_at": 1000000, "completed_steps": [1],
            "completion_state": "active",
        }}
        char = {
            "id": 9, "name": "Hunter", "room_id": 612,
            "attributes": json.dumps(attrs),
        }
        result = _run(on_bounty_accepted(
            db, char, "tutorial_bhg_tarko_vinn"))
        # Chain still advanced...
        self.assertTrue(result)
        state = json.loads(char["attributes"])["tutorial_chain"]
        self.assertEqual(state["step"], 3)
        # ...but no teleport happened (room unresolved) — player stays.
        self.assertEqual(char["room_id"], 612)
        self.assertNotIn("pending_step_room_id", state)


# ─────────────────────────────────────────────────────────────────────
# 4. +factions alias resolves (graduation completion fix)
# ─────────────────────────────────────────────────────────────────────


class TestFactionsAlias(unittest.TestCase):
    """The graduation step of all 7 chains completes on
    `command_executed: +factions`. The alias must resolve to the
    +faction umbrella so the command runs and the chain hook fires."""

    def test_plus_factions_alias_present_bare_factions_excluded(self):
        from parser.faction_commands import FactionUmbrellaCommand
        cmd = FactionUmbrellaCommand()
        self.assertIn("+factions", cmd.aliases)
        # The bare "factions" is DELIBERATELY not aliased — it would
        # run the command but ctx.command="factions" wouldn't match the
        # "+factions" completion, a silent "did it but didn't advance"
        # trap. Lock that out so a future well-meaning edit can't
        # reintroduce it.
        self.assertNotIn("factions", cmd.aliases)
        self.assertEqual(cmd.key, "+faction")

    def test_registry_resolves_plus_factions_to_umbrella(self):
        from parser.commands import CommandRegistry
        from parser.faction_commands import FactionUmbrellaCommand
        reg = CommandRegistry()
        reg.register(FactionUmbrellaCommand())
        # The exact graduation-completion literal must resolve.
        self.assertIsNotNone(reg.get("+factions"))
        self.assertIs(reg.get("+factions"), reg.get("+faction"))
        # Bare "factions" must NOT resolve (no prefix match either) so
        # there is no silent non-advancing trap.
        self.assertIsNone(reg.get("factions"))


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_f8c2e_interstep_teleport as mod
        self.assertIn("F.8.c.2.e", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
