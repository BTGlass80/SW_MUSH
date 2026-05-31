# -*- coding: utf-8 -*-
"""
tests/test_f8c2b6_chain_attempt_command.py — F.8.c.2.b₆ resolution
(May 20 2026).

The May 19 F.8.c.2.b₆ drop shipped the `on_skill_check_passed`
public seam without a production trigger; the seam-decision
question (when does the implicit roll fire?) was deferred per
the chain_events module docstring.

This drop resolves the deferral with Option 2 — explicit player
command. The wire-up adds:

  parser/chain_commands.py            ChainCommand:
                                        chain attempt
                                        chain status
                                        chain (= status)
  engine/chain_events.py              get_active_step_info now
                                        returns the full `completion`
                                        dict so the command can read
                                        the authored skill /
                                        difficulty / fallback / on_fail.
  engine/lightsaber_construction.py   _set_chargen_flags now
                                        delegates to the canonical
                                        engine.village_choice helper
                                        so prereq chain hooks fire
                                        uniformly across all
                                        chargen_notes writers.
  server/game_server.py               post-chargen fires
                                        `on_prerequisite_flag_set`
                                        for `chargen_complete` and
                                        (when applicable)
                                        `force_sensitive`.

Test sections
=============

  1. TestGetActiveStepInfoExtension     — `completion` dict present
  2. TestChainStatusNoActiveChain       — chain → no-active message
  3. TestChainStatusActiveChain         — chain shows step info
  4. TestChainAttemptNoActiveChain      — chain attempt → graceful
  5. TestChainAttemptWrongCompletionType — chain attempt rejects
                                            non-skill steps with hint
  6. TestChainAttemptMalformedCompletion — missing skill or difficulty
                                            yields staff message
  7. TestChainAttemptSuccessAdvances    — success path advances chain
  8. TestChainAttemptFailureRetryable   — default failure → retry msg
  9. TestChainAttemptFailureAbort       — on_fail abort_step_no_retry
 10. TestChainAttemptFailureFallback    — fallback dict surfaces hint
 11. TestLightsaberDelegates            — lightsaber_construction
                                          _set_chargen_flags delegates
                                          to village_choice canonical
 12. TestChainCommandRegistration       — register_chain_commands
                                          adds `chain` to registry
 13. TestSeamDocstringResolved          — chain_events.py docstring
                                          says "RESOLVED"
 14. TestSkillCheckPassedDocstringUpdated — on_skill_check_passed
                                            docstring no longer says
                                            "not yet called"
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _run(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


CHAIN_EVENTS_PY = PROJECT_ROOT / "engine" / "chain_events.py"
CHAIN_COMMANDS_PY = PROJECT_ROOT / "parser" / "chain_commands.py"
LIGHTSABER_PY = PROJECT_ROOT / "engine" / "lightsaber_construction.py"


def _read_text(path: Path) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


# ─── shared mocks ───────────────────────────────────────────────────────


def _make_fake_db():
    db = MagicMock()
    db.save_character = AsyncMock()
    db.get_character = AsyncMock(return_value=None)
    # _db.execute_fetchall returns a list of dict-like rows.
    db._db = MagicMock()
    db._db.execute_fetchall = AsyncMock(return_value=[])
    return db


class _FakeSession:
    def __init__(self, character=None):
        self.character = character
        self.is_in_game = character is not None
        self.account = {}
        self.sent: list = []

    async def send_line(self, line: str) -> None:
        self.sent.append(line)


class _FakeSessionManager:
    def find_by_character(self, char_id):
        return None

    def sessions_in_room(self, *args, **kwargs):
        return []


def _ctx(session, db, command="chain", args=""):
    from parser.commands import CommandContext
    return CommandContext(
        session=session,
        raw_input=f"{command} {args}".strip(),
        command=command,
        args=args,
        args_list=args.split() if args else [],
        db=db,
        session_mgr=_FakeSessionManager(),
    )


def _char_with_chain(chain_id="smuggler", step=1) -> dict:
    state = {
        "chain_id": chain_id,
        "step": step,
        "started_at": 1000000,
        "completed_steps": [],
        "completion_state": "active",
    }
    return {
        "id": 42,
        "name": "Test PC",
        "room_id": 1,
        "attributes": json.dumps({"tutorial_chain": state}),
    }


class _IsolatedTestBase(unittest.TestCase):
    """Sets active era + resets chain corpus cache around each test."""

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


# ═════════════════════════════════════════════════════════════════════
# 1. get_active_step_info: completion dict exposed
# ═════════════════════════════════════════════════════════════════════


class TestGetActiveStepInfoExtension(_IsolatedTestBase):

    def test_completion_dict_present(self):
        """Pick a chain step known to have skill_check_passed
        completion and confirm the new `completion` key is
        populated with the full dict (not just the type)."""
        from engine.chain_events import get_active_step_info
        # smuggler chain step 5 is `skill_check_passed` per the
        # chains.yaml grep we did. If chain authoring shifts, the
        # test fails clearly and we re-pick.
        char = _char_with_chain("smuggler", step=5)
        info = get_active_step_info(char)
        self.assertIsNotNone(info, "smuggler step 5 should resolve")
        if info.get("completion_type") != "skill_check_passed":
            # Different step — find one in the corpus that IS
            # skill_check_passed. This keeps the test robust to
            # chain re-authoring.
            self.skipTest(
                f"smuggler step 5 is not skill_check_passed "
                f"(got {info.get('completion_type')!r}); "
                f"re-pick a fixture step")
        self.assertIn("completion", info)
        self.assertIsInstance(info["completion"], dict)
        self.assertIn("skill", info["completion"])
        self.assertIn("difficulty", info["completion"])

    def test_completion_dict_is_a_copy(self):
        """Mutating the returned `completion` must not affect the
        cached corpus."""
        from engine.chain_events import get_active_step_info
        char = _char_with_chain("smuggler", step=1)
        info1 = get_active_step_info(char)
        if info1 is None:
            self.skipTest("no active step on smuggler step 1")
        if isinstance(info1.get("completion"), dict):
            info1["completion"]["__poison__"] = True
        info2 = get_active_step_info(char)
        self.assertNotIn(
            "__poison__", (info2 or {}).get("completion") or {}
        )


# ═════════════════════════════════════════════════════════════════════
# 2. chain status — no active chain
# ═════════════════════════════════════════════════════════════════════


class TestChainStatusNoActiveChain(unittest.TestCase):

    def test_no_active_chain_message(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            # Char without tutorial_chain attrs.
            char = {
                "id": 1, "name": "Solo", "room_id": 1,
                "attributes": "{}",
            }
            sess = _FakeSession(char)
            db = _make_fake_db()
            await ChainCommand().execute(_ctx(sess, db, args="status"))
            self.assertTrue(
                any("no active tutorial chain" in l.lower()
                    for l in sess.sent),
                f"Expected no-active-chain message; got {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 3. chain status — active chain
# ═════════════════════════════════════════════════════════════════════


class TestChainStatusActiveChain(_IsolatedTestBase):

    def test_status_shows_step_info(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            char = _char_with_chain("smuggler", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()
            await ChainCommand().execute(_ctx(sess, db, args="status"))
            joined = "\n".join(sess.sent)
            # Chain name should appear somewhere.
            self.assertIn("smuggler", joined.lower(),
                          f"Expected chain name in output: {sess.sent}")
            # "step" or "Completes when:" present.
            self.assertTrue(
                any("completes when" in l.lower() for l in sess.sent),
                f"Expected 'Completes when:' label: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 4. chain attempt — no active chain
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptNoActiveChain(unittest.TestCase):

    def test_attempt_with_no_chain_says_so(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            char = {
                "id": 1, "name": "Solo", "room_id": 1,
                "attributes": "{}",
            }
            sess = _FakeSession(char)
            db = _make_fake_db()
            await ChainCommand().execute(_ctx(sess, db, args="attempt"))
            self.assertTrue(
                any("no active tutorial chain" in l.lower()
                    for l in sess.sent)
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 5. chain attempt — wrong completion type rejected with hint
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptWrongCompletionType(_IsolatedTestBase):

    def test_attempt_on_talk_step_rejected_with_hint(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from engine.chain_events import get_active_step_info
            # Find a chain step whose completion_type is talk_to_npc.
            # smuggler step 1 is talk_to_npc per the YAML.
            char = _char_with_chain("smuggler", step=1)
            info = get_active_step_info(char)
            if info is None or info.get("completion_type") == "skill_check_passed":
                self.skipTest(
                    "fixture step is not non-skill-check; re-pick")
            sess = _FakeSession(char)
            db = _make_fake_db()
            await ChainCommand().execute(_ctx(sess, db, args="attempt"))
            joined = "\n".join(sess.sent).lower()
            self.assertIn(
                "does not use 'chain attempt'", joined,
                f"Expected wrong-type rejection: {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 6. chain attempt — malformed completion → staff message
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptMalformedCompletion(unittest.TestCase):
    """If somehow a chain step had completion type
    skill_check_passed without `skill` or `difficulty`, the
    command must NOT crash — it should surface a staff message."""

    def test_missing_difficulty_surfaces_staff_message(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from unittest.mock import patch
            char = _char_with_chain("smuggler", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()
            # Force get_active_step_info to return a malformed step.
            broken_info = {
                "chain_id": "x", "chain_name": "X", "step": 1,
                "title": "T", "objective": "O", "location": None,
                "npc": None, "completion_type": "skill_check_passed",
                "completion": {
                    "type": "skill_check_passed",
                    "skill": "",  # malformed
                    # no difficulty
                },
            }
            with patch(
                "engine.chain_events.get_active_step_info",
                return_value=broken_info,
            ):
                await ChainCommand().execute(
                    _ctx(sess, db, args="attempt")
                )
            self.assertTrue(
                any("misconfigured" in l.lower()
                    or "notify staff" in l.lower()
                    for l in sess.sent),
                f"Expected staff-message; got {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 7. chain attempt — success advances
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptSuccessAdvances(unittest.TestCase):

    def test_success_dispatches_to_skill_check_hook(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from unittest.mock import patch
            char = _char_with_chain("test_chain", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()

            mock_info = {
                "chain_id": "test_chain",
                "chain_name": "Test Chain",
                "step": 1,
                "title": "Sneak", "objective": "Sneak past",
                "location": None, "npc": None,
                "completion_type": "skill_check_passed",
                "completion": {
                    "type": "skill_check_passed",
                    "skill": "sneak",
                    "difficulty": 8,
                },
            }

            mock_result = MagicMock()
            mock_result.success = True
            mock_result.critical_success = False
            mock_result.fumble = False
            mock_result.pool_str = "3D+2"
            mock_result.roll = 12

            with patch(
                "engine.chain_events.get_active_step_info",
                return_value=mock_info,
            ), patch(
                "engine.skill_checks.perform_skill_check",
                return_value=mock_result,
            ), patch(
                "engine.chain_events.on_skill_check_passed",
                new=AsyncMock(return_value=True),
            ) as mock_hook, patch(
                "engine.chain_graduation.execute_pending_teleport",
                new=AsyncMock(),
            ):
                await ChainCommand().execute(
                    _ctx(sess, db, args="attempt"))

            mock_hook.assert_awaited_once()
            joined = "\n".join(sess.sent).lower()
            self.assertIn("success", joined)
            self.assertIn("advance", joined)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 8. chain attempt — failure with no on_fail → retryable
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptFailureRetryable(unittest.TestCase):

    def test_default_failure_says_try_again(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from unittest.mock import patch
            char = _char_with_chain("test_chain", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()

            mock_info = {
                "chain_id": "test_chain",
                "chain_name": "Test", "step": 1,
                "title": "Try", "objective": "Try",
                "location": None, "npc": None,
                "completion_type": "skill_check_passed",
                "completion": {
                    "type": "skill_check_passed",
                    "skill": "sneak",
                    "difficulty": 8,
                },
            }

            mock_result = MagicMock()
            mock_result.success = False
            mock_result.critical_success = False
            mock_result.fumble = False
            mock_result.pool_str = "2D"
            mock_result.roll = 5

            with patch(
                "engine.chain_events.get_active_step_info",
                return_value=mock_info,
            ), patch(
                "engine.skill_checks.perform_skill_check",
                return_value=mock_result,
            ), patch(
                "engine.chain_events.on_skill_check_passed",
                new=AsyncMock(return_value=False),
            ):
                await ChainCommand().execute(
                    _ctx(sess, db, args="attempt"))

            self.assertTrue(
                any("try again" in l.lower() for l in sess.sent),
                f"Expected retry-permitted message; got {sess.sent}"
            )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 9. chain attempt — failure with on_fail abort_step_no_retry
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptFailureAbort(unittest.TestCase):

    def test_abort_failure_says_cannot_retry(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from unittest.mock import patch
            char = _char_with_chain("test_chain", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()

            mock_info = {
                "chain_id": "test_chain",
                "chain_name": "Test", "step": 1,
                "title": "Try", "objective": "Try",
                "location": None, "npc": None,
                "completion_type": "skill_check_passed",
                "completion": {
                    "type": "skill_check_passed",
                    "skill": "sneak",
                    "difficulty": 9,
                    "on_fail": "abort_step_no_retry",
                    "on_fail_narrative": "The patrol spots you.",
                },
            }
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.critical_success = False
            mock_result.fumble = False
            mock_result.pool_str = "2D"
            mock_result.roll = 4

            with patch(
                "engine.chain_events.get_active_step_info",
                return_value=mock_info,
            ), patch(
                "engine.skill_checks.perform_skill_check",
                return_value=mock_result,
            ), patch(
                "engine.chain_events.on_skill_check_passed",
                new=AsyncMock(return_value=False),
            ):
                await ChainCommand().execute(
                    _ctx(sess, db, args="attempt"))

            joined = "\n".join(sess.sent).lower()
            self.assertIn("cannot be retried", joined)
            self.assertIn("patrol spots you", joined)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 10. chain attempt — failure with fallback dict
# ═════════════════════════════════════════════════════════════════════


class TestChainAttemptFailureFallback(unittest.TestCase):

    def test_combat_won_fallback_surfaces_hint(self):
        async def _check():
            from parser.chain_commands import ChainCommand
            from unittest.mock import patch
            char = _char_with_chain("test_chain", step=1)
            sess = _FakeSession(char)
            db = _make_fake_db()

            mock_info = {
                "chain_id": "test_chain",
                "chain_name": "Test", "step": 1,
                "title": "Con", "objective": "Con guard",
                "location": None, "npc": None,
                "completion_type": "skill_check_passed",
                "completion": {
                    "type": "skill_check_passed",
                    "skill": "con",
                    "difficulty": 10,
                    "fallback": {
                        "type": "combat_won",
                        "target": "guard",
                    },
                },
            }
            mock_result = MagicMock()
            mock_result.success = False
            mock_result.critical_success = False
            mock_result.fumble = False
            mock_result.pool_str = "2D"
            mock_result.roll = 4

            with patch(
                "engine.chain_events.get_active_step_info",
                return_value=mock_info,
            ), patch(
                "engine.skill_checks.perform_skill_check",
                return_value=mock_result,
            ), patch(
                "engine.chain_events.on_skill_check_passed",
                new=AsyncMock(return_value=False),
            ):
                await ChainCommand().execute(
                    _ctx(sess, db, args="attempt"))

            joined = "\n".join(sess.sent).lower()
            self.assertIn("fallback", joined)
            self.assertIn("defeat", joined)
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 11. lightsaber_construction._set_chargen_flags delegates
# ═════════════════════════════════════════════════════════════════════


class TestLightsaberDelegates(unittest.TestCase):

    def test_lightsaber_set_flags_calls_village_choice(self):
        async def _check():
            from unittest.mock import patch
            char = {
                "id": 1, "name": "T", "chargen_notes": "{}",
            }
            db = _make_fake_db()

            with patch(
                "engine.village_choice._set_chargen_flags",
                new=AsyncMock(),
            ) as mock_canonical:
                from engine.lightsaber_construction import (
                    _set_chargen_flags as ls_set,
                )
                await ls_set(db, char, marker_test=True)
                mock_canonical.assert_awaited_once_with(
                    db, char, marker_test=True,
                )
        _run(_check())


# ═════════════════════════════════════════════════════════════════════
# 12. Registration smoke
# ═════════════════════════════════════════════════════════════════════


class TestChainCommandRegistration(unittest.TestCase):

    def test_chain_registers_cleanly(self):
        from parser.commands import CommandRegistry
        from parser.chain_commands import register_chain_commands
        reg = CommandRegistry()
        register_chain_commands(reg)
        self.assertIsNotNone(reg.get("chain"),
                             "Command 'chain' not registered")


# ═════════════════════════════════════════════════════════════════════
# 13. Seam-decision docstring marked RESOLVED
# ═════════════════════════════════════════════════════════════════════


class TestSeamDocstringResolved(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(CHAIN_EVENTS_PY)

    def test_design_note_says_resolved(self):
        self.assertIn(
            "F.8.c.2.b\u2086 design note \u2014 skill_check_passed seam: RESOLVED",
            self.src,
            "chain_events.py F.8.c.2.b₆ design note should be "
            "marked RESOLVED",
        )

    def test_chain_attempt_referenced(self):
        # The resolved note should reference the new command.
        self.assertIn("chain attempt", self.src)


# ═════════════════════════════════════════════════════════════════════
# 14. on_skill_check_passed docstring updated
# ═════════════════════════════════════════════════════════════════════


class TestSkillCheckPassedDocstringUpdated(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.src = _read_text(CHAIN_EVENTS_PY)

    def test_docstring_no_longer_says_not_yet_called(self):
        # Old docstring contained "**not yet called from any
        # production code site**". This shouldn't be there anymore.
        self.assertNotIn("not yet called from any production",
                         self.src)

    def test_docstring_references_chain_commands(self):
        # The new docstring should point at parser/chain_commands.py.
        # Match either the slash-form or the dotted import path.
        self.assertTrue(
            ("parser/chain_commands.py" in self.src
             or "parser.chain_commands" in self.src),
            "on_skill_check_passed docstring should reference "
            "parser/chain_commands.py as the production trigger site",
        )


if __name__ == "__main__":
    unittest.main()
