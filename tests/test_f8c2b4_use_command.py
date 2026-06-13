# -*- coding: utf-8 -*-
"""
tests/test_f8c2b4_use_command.py — F.8.c.2.b₄ `use <item>` parser
command + per-step item reward delivery.

F.8.c.2.b₄ (May 4 2026) closes the last wired-but-inert chain
hook from Phase 2. Adds:

  * ``parser/builtin_commands.py::UseCommand`` — `use <item>`
    parser command. Resolves item by exact key, exact name
    (case-insensitive), or unique partial-name match. Fires
    ``chain_events.on_item_used`` chain hook + the F.8.c.2.c
    graduation finisher.
  * Items can declare ``consumable: true`` to be removed from
    inventory on use, and ``use_message`` for narrative flavor.
  * ``engine/chain_rewards.py::apply_step_rewards`` — per-step
    reward delivery, called from ``chain_events._try_advance``
    after step advance. Currently delivers ``step.reward.items``
    keys as inventory grants tagged ``chain_step: <chain>:<step>``.
  * ``_STEP_ITEM_PROPERTIES`` registry — per-key special properties
    (consumable, use_message, description override). Authored
    entry: ``sealed_data_packet`` for separatist_agent step 2.

After this drop, ``separatist_agent`` step 2 advances at runtime:
  * Step 1 (`say geonosis` advances) → step 1's
    ``reward.items: [sealed_data_packet]`` delivers via
    ``apply_step_rewards``
  * Player runs ``use sealed_data_packet`` → ``UseCommand`` fires
    chain hook ``on_item_used`` → ``_try_advance`` matches step 2's
    ``completion: {type: item_used, item: sealed_data_packet}`` →
    advances to step 3

Test sections
-------------
  1. TestStepItemBuilder        — _build_step_item shape
  2. TestApplyStepRewards       — engine-side step reward delivery
  3. TestSealedPacketProperties — verify the authored override
  4. TestUseCommandResolution   — item resolution (key/name/partial)
  5. TestUseCommandConsumable   — consumable items removed
  6. TestUseCommandChainHook    — chain hook fires + graduation
                                  finisher wired
  7. TestEndToEndSeparatistAgent — full step 1→2→3 advance via real
                                   production hooks
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
    def __init__(self):
        self.inventory = {}     # char_id -> list of item dicts
        self.save_calls = []
        self.removed = []        # (char_id, item_key) pairs
        self.fail_remove = False

    async def get_inventory(self, char_id):
        return list(self.inventory.get(char_id, []))

    async def add_to_inventory(self, char_id, item):
        self.inventory.setdefault(char_id, []).append(item)

    async def remove_from_inventory(self, char_id, item_key):
        if self.fail_remove:
            return False
        items = self.inventory.get(char_id, [])
        for i, item in enumerate(items):
            if isinstance(item, dict) and item.get("key") == item_key:
                items.pop(i)
                self.removed.append((char_id, item_key))
                return True
        return False

    async def save_character(self, char_id, **kwargs):
        self.save_calls.append((char_id, kwargs))

    async def get_organization(self, code):
        return None

    async def get_membership(self, char_id, org_id):
        return None


class _MockSession:
    def __init__(self):
        self.lines = []
        self.character = None
        self.is_in_game = True

    async def send_line(self, line):
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


def _char(char_id=1, room_id=10, attrs=None, notes=None):
    return {
        "id": char_id, "name": "TestPC",
        "credits": 100, "room_id": room_id,
        "attributes": json.dumps(attrs or {}),
        "chargen_notes": json.dumps(notes or {}) if notes else "",
        "faction_id": "independent",
    }


# ─────────────────────────────────────────────────────────────────────
# 1. _build_step_item
# ─────────────────────────────────────────────────────────────────────


class TestStepItemBuilder(unittest.TestCase):

    def test_basic_shape(self):
        from engine.chain_rewards import _build_step_item
        item = _build_step_item(
            "test_token", "test_chain", 3)
        self.assertEqual(item["key"], "test_token")
        self.assertEqual(item["name"], "Test Token")
        self.assertEqual(item["chain_step"], "test_chain:3")
        self.assertIn("acquired_at", item)

    def test_overrides_applied(self):
        from engine.chain_rewards import _build_step_item
        # sealed_data_packet has consumable + use_message overrides
        item = _build_step_item(
            "sealed_data_packet", "separatist_agent", 1)
        self.assertEqual(item["key"], "sealed_data_packet")
        self.assertEqual(item["name"], "Sealed Data Packet")
        self.assertTrue(item.get("consumable"))
        self.assertIn("use_message", item)
        self.assertIn("bio-sig", item["use_message"].lower())


# ─────────────────────────────────────────────────────────────────────
# 2. apply_step_rewards
# ─────────────────────────────────────────────────────────────────────


class TestApplyStepRewards(unittest.TestCase):

    def test_grants_each_item_in_step_reward(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        char = _char(char_id=5)

        # Mock step with reward.items
        step = types.SimpleNamespace(
            step=1, reward={"items": ["a_item", "b_item"]},
        )
        report = _run(apply_step_rewards(
            db, char, step, "test_chain"))

        self.assertEqual(set(report["items_granted"]),
                         {"a_item", "b_item"})
        # Two add_to_inventory calls
        self.assertEqual(len(db.inventory[5]), 2)
        # Each tagged with chain_step
        for item in db.inventory[5]:
            self.assertEqual(item["chain_step"], "test_chain:1")

    def test_handles_empty_reward(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        char = _char()
        step = types.SimpleNamespace(step=1, reward={})
        report = _run(apply_step_rewards(
            db, char, step, "test"))
        self.assertEqual(report["items_granted"], [])

    def test_handles_none_step(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        char = _char()
        report = _run(apply_step_rewards(
            db, char, None, "test"))
        self.assertEqual(report["items_granted"], [])

    def test_failure_tolerant(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        # Make add_to_inventory raise
        async def fail_add(char_id, item):
            raise RuntimeError("inventory fail")
        db.add_to_inventory = fail_add

        char = _char()
        step = types.SimpleNamespace(
            step=1, reward={"items": ["item_a"]},
        )
        report = _run(apply_step_rewards(
            db, char, step, "test"))
        self.assertEqual(report["items_failed"], ["item_a"])
        self.assertEqual(len(report["errors"]), 1)

    # ── T5-questline arc (2026-06-13): per-step credits + rep consumer ──

    def test_grants_step_credits_via_metered_faucet(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        seen = {}

        async def _adjust_credits(char_id, delta, tag):
            seen["call"] = (char_id, delta, tag)
            return 1200  # new balance

        db.adjust_credits = _adjust_credits
        char = _char(char_id=5)
        char["credits"] = 1000
        step = types.SimpleNamespace(step=4, reward={"credits": 200})
        report = _run(apply_step_rewards(db, char, step, "test_chain"))
        self.assertEqual(report["credits_awarded"], 200)
        # Rode the metered adjust_credits faucet with the step tag.
        self.assertEqual(seen["call"], (5, 200, "chain_step_reward"))
        self.assertEqual(char["credits"], 1200)

    def test_grants_step_faction_rep_via_funnel(self):
        from engine.chain_rewards import apply_step_rewards
        import engine.organizations as orgs
        db = _MockDB()
        calls = []

        async def _fake_adjust_rep(char, faction_code, db, *, delta, reason):
            calls.append((faction_code, delta, reason))
            return 28  # new score

        orig = orgs.adjust_rep
        orgs.adjust_rep = _fake_adjust_rep
        try:
            char = _char(char_id=7)
            step = types.SimpleNamespace(
                step=2, reward={"faction_rep": {"jedi_order": 4}})
            report = _run(apply_step_rewards(db, char, step, "ql_chain"))
        finally:
            orgs.adjust_rep = orig
        self.assertEqual(report["rep_awarded"].get("jedi_order"), 28)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "jedi_order")
        self.assertEqual(calls[0][1], 4)
        self.assertIn("chain_step:ql_chain:2", calls[0][2])

    def test_zero_credits_and_zero_rep_no_funnel_calls(self):
        from engine.chain_rewards import apply_step_rewards
        db = _MockDB()
        called = {"credits": False}

        async def _adjust_credits(char_id, delta, tag):
            called["credits"] = True
            return 0
        db.adjust_credits = _adjust_credits
        char = _char()
        step = types.SimpleNamespace(
            step=1, reward={"credits": 0, "faction_rep": {"x": 0}})
        report = _run(apply_step_rewards(db, char, step, "t"))
        self.assertEqual(report["credits_awarded"], 0)
        self.assertFalse(called["credits"])  # 0 credits -> no faucet call


# ─────────────────────────────────────────────────────────────────────
# 3. sealed_data_packet authored entry
# ─────────────────────────────────────────────────────────────────────


class TestSealedPacketProperties(unittest.TestCase):

    def test_packet_has_required_props(self):
        from engine.chain_rewards import _STEP_ITEM_PROPERTIES
        self.assertIn("sealed_data_packet", _STEP_ITEM_PROPERTIES)
        props = _STEP_ITEM_PROPERTIES["sealed_data_packet"]
        self.assertTrue(props.get("consumable"))
        self.assertIn("use_message", props)
        self.assertIn("description", props)


# ─────────────────────────────────────────────────────────────────────
# 4. UseCommand resolution
# ─────────────────────────────────────────────────────────────────────


class TestUseCommandResolution(unittest.TestCase):

    def _setup(self, inventory):
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        db.inventory[1] = list(inventory)
        return UseCommand(), ctx, db, sess

    def test_exact_key_match(self):
        cmd, ctx, db, sess = self._setup([
            {"key": "thing_a", "name": "Apple"},
            {"key": "thing_b", "name": "Banana"},
        ])
        ctx.args = "thing_a"
        _run(cmd.execute(ctx))
        self.assertTrue(any("apple" in l.lower() for l in sess.lines))

    def test_exact_name_match_case_insensitive(self):
        cmd, ctx, db, sess = self._setup([
            {"key": "x_key", "name": "Sealed Data Packet"},
        ])
        ctx.args = "sealed data packet"
        _run(cmd.execute(ctx))
        self.assertTrue(any("packet" in l.lower() for l in sess.lines))

    def test_partial_name_unique(self):
        cmd, ctx, db, sess = self._setup([
            {"key": "x", "name": "Sealed Data Packet"},
        ])
        ctx.args = "packet"
        _run(cmd.execute(ctx))
        self.assertTrue(any("packet" in l.lower() for l in sess.lines))

    def test_partial_name_ambiguous(self):
        cmd, ctx, db, sess = self._setup([
            {"key": "a", "name": "Sealed Data Packet"},
            {"key": "b", "name": "Data Cube"},
        ])
        ctx.args = "data"
        _run(cmd.execute(ctx))
        self.assertTrue(
            any("multiple matches" in l.lower() for l in sess.lines)
        )

    def test_no_args_shows_usage(self):
        cmd, ctx, db, sess = self._setup([])
        ctx.args = ""
        _run(cmd.execute(ctx))
        self.assertTrue(any("usage" in l.lower() for l in sess.lines))

    def test_empty_inventory(self):
        cmd, ctx, db, sess = self._setup([])
        ctx.args = "anything"
        _run(cmd.execute(ctx))
        self.assertTrue(
            any("not carrying" in l.lower() for l in sess.lines)
        )

    def test_no_match(self):
        cmd, ctx, db, sess = self._setup([
            {"key": "x", "name": "A Thing"},
        ])
        ctx.args = "nonexistent"
        _run(cmd.execute(ctx))
        self.assertTrue(
            any("don't have anything" in l.lower() for l in sess.lines)
        )


# ─────────────────────────────────────────────────────────────────────
# 5. UseCommand consumable
# ─────────────────────────────────────────────────────────────────────


class TestUseCommandConsumable(unittest.TestCase):

    def test_consumable_item_removed(self):
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        db.inventory[1] = [
            {"key": "potion", "name": "Potion", "consumable": True},
        ]
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "potion"
        _run(UseCommand().execute(ctx))
        # Removed
        self.assertEqual(len(db.inventory[1]), 0)
        self.assertIn((1, "potion"), db.removed)

    def test_non_consumable_item_kept(self):
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        db.inventory[1] = [
            {"key": "comlink", "name": "Comlink"},  # no consumable
        ]
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "comlink"
        _run(UseCommand().execute(ctx))
        # Not removed
        self.assertEqual(len(db.inventory[1]), 1)
        self.assertEqual(db.removed, [])

    def test_custom_use_message_used(self):
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        db.inventory[1] = [{
            "key": "magic_token",
            "name": "Magic Token",
            "use_message": "The token glows brightly.",
        }]
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "magic_token"
        _run(UseCommand().execute(ctx))
        self.assertTrue(
            any("token glows" in l for l in sess.lines)
        )


# ─────────────────────────────────────────────────────────────────────
# 6. Chain hook + graduation finisher wired
# ─────────────────────────────────────────────────────────────────────


class TestUseCommandChainHook(unittest.TestCase):

    def test_chain_hook_fires_with_item_key(self):
        """Verify UseCommand calls on_item_used with the item key."""
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        db.inventory[1] = [
            {"key": "test_packet", "name": "Test Packet"},
        ]
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "test_packet"

        with patch("engine.chain_events.on_item_used",
                   AsyncMock(return_value=False)) as mock_hook:
            _run(UseCommand().execute(ctx))
            mock_hook.assert_called_once()
            args = mock_hook.call_args
            # on_item_used(db, char, item_key)
            self.assertEqual(args[0][2], "test_packet")

    def test_graduation_finisher_invoked_when_hook_returns_true(self):
        from parser.builtin_commands import UseCommand
        db = _MockDB()
        char = _char(char_id=1)
        db.inventory[1] = [{"key": "x", "name": "X"}]
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "x"

        with patch("engine.chain_events.on_item_used",
                   AsyncMock(return_value=True)), \
             patch("engine.chain_graduation.execute_pending_teleport",
                   AsyncMock(return_value=False)) as mock_grad:
            _run(UseCommand().execute(ctx))
            mock_grad.assert_called_once()


# ─────────────────────────────────────────────────────────────────────
# 7. End-to-end: separatist_agent step 1→2→3 via real hooks
# ─────────────────────────────────────────────────────────────────────


class TestEndToEndSeparatistAgent(unittest.TestCase):

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

    def test_step_1_reward_delivers_packet(self):
        """Player on step 1 says 'geonosis' → step 1 advances → step 1's
        reward.items: [sealed_data_packet] lands in inventory."""
        from engine.chain_events import on_command_executed

        db = _MockDB()
        attrs = {
            "tutorial_chain": {
                "chain_id": "separatist_agent",
                "step": 1,
                "started_at": 1000000,
                "completed_steps": [],
                "completion_state": "active",
            }
        }
        char = _char(char_id=7, attrs=attrs)
        db.inventory[7] = []

        result = _run(on_command_executed(
            db, char, "say", "I hear about Geonosis a lot"))
        self.assertTrue(result)

        # Inventory should now have the packet
        self.assertEqual(len(db.inventory[7]), 1)
        item = db.inventory[7][0]
        self.assertEqual(item["key"], "sealed_data_packet")
        self.assertTrue(item.get("consumable"))
        self.assertIn("use_message", item)

        # Chain advanced to step 2
        new_attrs = json.loads(char["attributes"])
        self.assertEqual(new_attrs["tutorial_chain"]["step"], 2)

    def test_use_packet_advances_step_2_to_3(self):
        """Player on step 2 with packet in inventory runs `use` →
        step 2 advances to step 3."""
        from parser.builtin_commands import UseCommand

        db = _MockDB()
        attrs = {
            "tutorial_chain": {
                "chain_id": "separatist_agent",
                "step": 2,
                "started_at": 1000000,
                "completed_steps": [1],
                "completion_state": "active",
            }
        }
        char = _char(char_id=7, attrs=attrs)
        db.inventory[7] = [{
            "key": "sealed_data_packet",
            "name": "Sealed Data Packet",
            "consumable": True,
            "use_message": "The packet flickers as it reads your bio-sig.",
        }]

        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "sealed_data_packet"

        _run(UseCommand().execute(ctx))

        # Packet consumed (consumable: True)
        self.assertEqual(len(db.inventory[7]), 0)

        # Chain advanced to step 3
        new_attrs = json.loads(char["attributes"])
        self.assertEqual(new_attrs["tutorial_chain"]["step"], 3)

    def test_full_step_1_through_3_walk(self):
        """Combined: say geonosis → packet delivered → use packet → step 3."""
        from engine.chain_events import on_command_executed
        from parser.builtin_commands import UseCommand

        db = _MockDB()
        attrs = {
            "tutorial_chain": {
                "chain_id": "separatist_agent",
                "step": 1,
                "started_at": 1000000,
                "completed_steps": [],
                "completion_state": "active",
            }
        }
        char = _char(char_id=7, attrs=attrs)
        db.inventory[7] = []

        # Step 1 → 2 (say geonosis)
        _run(on_command_executed(
            db, char, "say", "I hear about Geonosis a lot"))

        # Verify step 2 + packet in inventory
        new_attrs = json.loads(char["attributes"])
        self.assertEqual(new_attrs["tutorial_chain"]["step"], 2)
        self.assertEqual(len(db.inventory[7]), 1)

        # Now run use sealed_data_packet
        sess = _MockSession()
        sess.character = char
        ctx = _MockCtx(db=db, session=sess,
                       session_mgr=_MockSessionMgr())
        ctx.args = "sealed_data_packet"
        _run(UseCommand().execute(ctx))

        # Step 2 → 3 + packet consumed
        new_attrs = json.loads(char["attributes"])
        self.assertEqual(new_attrs["tutorial_chain"]["step"], 3)
        self.assertEqual(len(db.inventory[7]), 0)


# ─────────────────────────────────────────────────────────────────────
# UseCommand registration check
# ─────────────────────────────────────────────────────────────────────


class TestUseCommandRegistered(unittest.TestCase):

    def test_use_in_register_all(self):
        """Verify UseCommand is in the builtin_commands register list."""
        import parser.builtin_commands as bc
        # The registry mock is hard to instantiate; instead grep
        # the source to confirm presence.
        src = Path(bc.__file__).read_text(encoding="utf-8")
        self.assertIn("UseCommand()", src)


# ─────────────────────────────────────────────────────────────────────


class TestDropMarker(unittest.TestCase):
    def test_module_docstring_marks_drop_id(self):
        import tests.test_f8c2b4_use_command as mod
        self.assertIn("F.8.c.2.b₄", mod.__doc__ or "")


if __name__ == "__main__":
    unittest.main()
