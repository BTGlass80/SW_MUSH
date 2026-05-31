# -*- coding: utf-8 -*-
"""Regression tests for the May 4 2026 NPC dialogue cleanup drop.

This drop addressed seven bugs reported during a parallel-session
playtest (see HANDOFF_MAY04_DIALOGUE_CLEANUP.md):

  1. Title bar was "SW MUSH — Field Kit" (legacy mock name).
  2. .comms-pane.collapsed had height:0 — clipped its own toggle handle.
  3. data/skills.yaml was reloaded synchronously on every command call;
     contributes to "tick loop fell behind" warnings.
  4. talk-to-NPC dialogue (player's directed say + NPC's response)
     never showed up in the IC tab.
  5. NPC prompts only got desc_short, so LLMs invented prices that
     contradicted the room's full description.
  6. Any exception inside _generate_and_display ate the response and
     left the player staring at a "considers..." emote.
  7. Ollama probe timeout was 3s; first WARNING fired even during
     normal warmup; no recovery log line.

Each test targets exactly one fix so a regression points at the
specific bug.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─────────────────────────────────────────────────────────────────────
# Path helpers
# ─────────────────────────────────────────────────────────────────────

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLIENT_HTML = os.path.join(REPO_ROOT, "static", "client.html")
NPC_COMMANDS = os.path.join(REPO_ROOT, "parser", "npc_commands.py")
NPC_BRAIN = os.path.join(REPO_ROOT, "ai", "npc_brain.py")
PROVIDERS = os.path.join(REPO_ROOT, "ai", "providers.py")
CHARACTER = os.path.join(REPO_ROOT, "engine", "character.py")
SPACE_COMMANDS = os.path.join(REPO_ROOT, "parser", "space_commands.py")


@pytest.fixture(scope="module")
def client_html() -> str:
    with open(CLIENT_HTML, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def npc_commands_src() -> str:
    with open(NPC_COMMANDS, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def npc_brain_src() -> str:
    with open(NPC_BRAIN, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def providers_src() -> str:
    with open(PROVIDERS, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def character_src() -> str:
    with open(CHARACTER, "r", encoding="utf-8") as f:
        return f.read()


@pytest.fixture(scope="module")
def space_commands_src() -> str:
    with open(SPACE_COMMANDS, "r", encoding="utf-8") as f:
        return f.read()


# ─────────────────────────────────────────────────────────────────────
# Fix 1: Title bar
# ─────────────────────────────────────────────────────────────────────

class TestTitleBar:
    """The browser-tab title should not say 'Field Kit' — that was the
    original mock name from /mocks/screens/field-kit.jsx.
    """

    def test_title_is_sw_mush_only(self, client_html):
        m = re.search(r"<title>([^<]+)</title>", client_html)
        assert m is not None, "static/client.html missing <title>"
        title = m.group(1)
        assert "Field Kit" not in title, (
            f"Title still references legacy mock name: {title!r}"
        )
        assert "SW MUSH" in title, f"Title lost SW MUSH brand: {title!r}"


# ─────────────────────────────────────────────────────────────────────
# Fix 2: COMMS pane collapse handle visibility
# ─────────────────────────────────────────────────────────────────────

class TestCommsCollapseHandle:
    """When the COMMS pane is collapsed, the handle bar must remain
    visible so the user has a way to re-expand it. The pre-fix CSS
    set height:0 on the entire pane, clipping its own handle.
    """

    def test_collapsed_pane_keeps_handle_height(self, client_html):
        # The pane has height:18px when collapsed (the handle's height).
        # We accept either the literal "18px" or a small px value.
        # Specifically reject the legacy "height: 0" that ate the handle.
        m = re.search(
            r"\.comms-pane\.collapsed\s*\{[^}]*\}",
            client_html,
        )
        assert m is not None, "Missing .comms-pane.collapsed CSS rule"
        block = m.group(0)
        # Forbid the legacy "height: 0" form.
        assert not re.search(
            r"height\s*:\s*0\s*[;}]", block
        ), f"Collapsed pane still uses height:0 (clips the handle): {block}"
        # Require some positive px height (the handle bar).
        assert re.search(
            r"height\s*:\s*\d+px", block
        ), f"Collapsed pane lacks a positive px height for the handle: {block}"


# ─────────────────────────────────────────────────────────────────────
# Fix 3: skills.yaml caching
# ─────────────────────────────────────────────────────────────────────

class TestSkillRegistryCache:
    """A cached SkillRegistry helper should exist in engine/character.py
    and the highest-traffic call sites in parser/space_commands.py
    should use it instead of re-loading the YAML every time.
    """

    def test_cached_helper_exists(self, character_src):
        assert "def get_cached_skill_registry" in character_src, (
            "engine/character.py missing get_cached_skill_registry helper"
        )
        assert "def reset_cached_skill_registry" in character_src, (
            "engine/character.py missing reset_cached_skill_registry helper"
        )

    def test_cached_helper_is_singleton(self):
        from engine.character import (
            get_cached_skill_registry,
            reset_cached_skill_registry,
        )
        reset_cached_skill_registry()
        a = get_cached_skill_registry()
        b = get_cached_skill_registry()
        assert a is b, "get_cached_skill_registry is not returning a singleton"
        # Cache should hold actual skills.
        assert a.count > 0, (
            "Cached SkillRegistry has zero skills — yaml load failed"
        )

    def test_cached_helper_can_be_reset(self):
        from engine.character import (
            get_cached_skill_registry,
            reset_cached_skill_registry,
        )
        a = get_cached_skill_registry()
        reset_cached_skill_registry()
        b = get_cached_skill_registry()
        assert a is not b, "reset_cached_skill_registry didn't drop the cache"

    def test_space_commands_high_traffic_sites_migrated(self, space_commands_src):
        # The gunnery/pilot/maneuver/shields hot paths should not be
        # re-parsing the YAML inline anymore. Specifically: zero
        # occurrences of the explicit 'sr.load_file("data/skills.yaml")'
        # pattern inside parser/space_commands.py.
        bad_pattern = 'sr.load_file("data/skills.yaml")'
        bad_count = space_commands_src.count(bad_pattern)
        assert bad_count == 0, (
            f"parser/space_commands.py still has {bad_count} inline "
            f'sr.load_file("data/skills.yaml") calls — migrate them to '
            "engine.character.get_cached_skill_registry()"
        )

    def test_space_commands_imports_cached_helper(self, space_commands_src):
        # At least one site should import the helper.
        assert "get_cached_skill_registry" in space_commands_src, (
            "parser/space_commands.py never imports get_cached_skill_registry"
        )


# ─────────────────────────────────────────────────────────────────────
# Fix 4: NPC dialogue → IC tab routing
# ─────────────────────────────────────────────────────────────────────

class TestNpcDialogueRoutesToIc:
    """Both directions of talk-to-NPC dialogue (the player's directed say
    and the NPC's response) must be mirrored to the IC comms tab via
    broadcast_chat("ic", ...). Without this, the COMMS pane stays empty
    during NPC conversations even though the main pose log shows the
    exchange.
    """

    def test_player_directed_say_broadcasts_to_ic(self, npc_commands_src):
        # Find the player-directed-say block (the one with "says to NPC, ...")
        # and confirm a broadcast_chat("ic", ...) call sits next to it.
        anchor = 'says to {ansi.npc_name(npc_data.name)}'
        assert anchor in npc_commands_src, (
            "Lost the directed-say render line — refactor breaking?"
        )
        # Within ~30 lines of the anchor, find an ic broadcast_chat.
        idx = npc_commands_src.index(anchor)
        window = npc_commands_src[idx:idx + 2000]
        assert 'broadcast_chat(' in window, (
            "Player's directed say not mirrored to broadcast_chat at all"
        )
        assert '"ic"' in window or "'ic'" in window, (
            "Player's directed say broadcast_chat call not on ic channel"
        )

    def test_npc_response_broadcasts_to_ic_main_path(self, npc_commands_src):
        # The main _generate_and_display body should also call
        # broadcast_chat("ic", npc_data.name, ...).
        # We assert at least 2 ic-channel broadcast_chat calls exist
        # (player's say + NPC's response). The tutorial fast path adds
        # a 3rd, but that's covered by the count being >= 2 here and a
        # separate test below.
        ic_chat_calls = re.findall(
            r"broadcast_chat\(\s*['\"]ic['\"]",
            npc_commands_src,
        )
        assert len(ic_chat_calls) >= 2, (
            f"Expected at least 2 broadcast_chat('ic',...) calls in "
            f"npc_commands.py (player's say + NPC's response), got "
            f"{len(ic_chat_calls)}"
        )

    def test_tutorial_fast_path_also_routes_to_ic(self, npc_commands_src):
        # The tutorial fast-path NPC say should also mirror to IC. We
        # check for a 3rd ic-channel broadcast_chat call.
        ic_chat_calls = re.findall(
            r"broadcast_chat\(\s*['\"]ic['\"]",
            npc_commands_src,
        )
        assert len(ic_chat_calls) >= 3, (
            f"Expected at least 3 broadcast_chat('ic',...) calls "
            f"(main path + tutorial fast-path NPC + player say); got "
            f"{len(ic_chat_calls)}"
        )


# ─────────────────────────────────────────────────────────────────────
# Fix 5: Room desc grounding (desc_long)
# ─────────────────────────────────────────────────────────────────────

class TestRoomDescGrounding:
    """The NPC dialogue path must feed the LLM the *full* room
    description (desc_long) so authored details like prices and
    inventory anchor the response. Pre-fix, only desc_short was
    passed and LLMs invented contradicting numbers.
    """

    def test_helper_function_exists(self, npc_commands_src):
        assert "def _room_desc_for_npc" in npc_commands_src, (
            "Missing _room_desc_for_npc helper in parser/npc_commands.py"
        )

    def test_helper_prefers_desc_long(self):
        from parser.npc_commands import _room_desc_for_npc
        room = {
            "desc_short": "An adequate 40-room hotel near the spaceport.",
            "desc_long": (
                "Forty small rooms at 15 credits per night. Beds are "
                "almost comfortable, sonic showers mostly work."
            ),
        }
        out = _room_desc_for_npc(room)
        assert "15 credits per night" in out, (
            f"_room_desc_for_npc didn't pick desc_long; got: {out!r}"
        )

    def test_helper_falls_back_to_desc_short(self):
        from parser.npc_commands import _room_desc_for_npc
        room = {
            "desc_short": "An adequate 40-room hotel near the spaceport.",
            "desc_long": "",
        }
        out = _room_desc_for_npc(room)
        assert "adequate 40-room hotel" in out

    def test_helper_falls_back_to_legacy_description(self):
        from parser.npc_commands import _room_desc_for_npc
        room = {
            "desc_short": "",
            "desc_long": "",
            "description": "A cantina full of smoke and bad music.",
        }
        out = _room_desc_for_npc(room)
        assert "smoke and bad music" in out

    def test_helper_handles_none_room(self):
        from parser.npc_commands import _room_desc_for_npc
        assert _room_desc_for_npc(None) == ""

    def test_helper_handles_empty_dict(self):
        from parser.npc_commands import _room_desc_for_npc
        assert _room_desc_for_npc({}) == ""

    def test_old_desc_short_only_pattern_gone(self, npc_commands_src):
        # The bug fingerprint: room.get("desc_short", "") if room else ""
        # passed straight to brain.dialogue without considering desc_long.
        # Allow the same string to appear inside the helper itself.
        bad = 'room.get("desc_short", "") if room else ""'
        # The helper shouldn't contain this exact form either (it uses
        # the longer chain). Should be zero occurrences anywhere.
        assert bad not in npc_commands_src, (
            f"Old desc_short-only pattern still present in npc_commands.py"
        )

    def test_brain_marks_room_as_authoritative(self, npc_brain_src):
        # The system-prompt builder should label the room context as
        # factual / authoritative so the LLM anchors to it.
        assert "factual" in npc_brain_src.lower() or "authoritative" in npc_brain_src.lower(), (
            "ai/npc_brain.py doesn't mark room context as factual/authoritative"
        )
        assert "do not contradict" in npc_brain_src.lower(), (
            "ai/npc_brain.py prompt doesn't tell the LLM not to "
            "contradict the room description"
        )


# ─────────────────────────────────────────────────────────────────────
# Fix 6: Silent failure guard in _generate_and_display
# ─────────────────────────────────────────────────────────────────────

class TestSilentFailureGuard:
    """A raised exception in brain.dialogue must not leave the player
    staring at a 'considers...' emote. The handler should catch and
    fall back to a canned line.
    """

    def test_brain_dialogue_call_is_wrapped_in_try(self, npc_commands_src):
        # Find _generate_and_display and confirm the brain.dialogue call
        # sits inside a try-block.
        m = re.search(
            r"async def _generate_and_display\(.*?\n(?=    async def |    def |\Z)",
            npc_commands_src,
            re.DOTALL,
        )
        assert m, "Cannot locate _generate_and_display in npc_commands.py"
        body = m.group(0)
        # Must contain both a try: and a brain.dialogue call.
        assert "brain.dialogue(" in body
        # The dialogue call must be inside a try-block.
        idx = body.index("brain.dialogue(")
        before = body[:idx]
        # Walk backwards from the call to find a 'try:' before any
        # function-level statements unrelated to it.
        assert "try:" in before[-500:], (
            "brain.dialogue() is not wrapped in try/except"
        )

    def test_offline_notice_is_session_scoped_one_shot(self, npc_commands_src):
        # The "AI offline" notice should only fire once per session.
        # Look for the _ai_offline_notified flag.
        assert "_ai_offline_notified" in npc_commands_src, (
            "Missing _ai_offline_notified one-shot flag in npc_commands.py"
        )

    def test_ai_manager_has_is_available(self, providers_src):
        # AIManager needs a top-level is_available so callers don't have
        # to dig into provider internals.
        assert re.search(
            r"async def is_available\([^)]*\)",
            providers_src,
        ), "AIManager.is_available not defined"

    def test_ai_manager_is_available_method(self):
        # Sanity check: instantiable and method is async.
        from ai.providers import AIManager
        mgr = AIManager()
        assert hasattr(mgr, "is_available")
        assert asyncio.iscoroutinefunction(mgr.is_available)


# ─────────────────────────────────────────────────────────────────────
# Fix 7: Ollama probe UX
# ─────────────────────────────────────────────────────────────────────

class TestOllamaProbeUx:
    """The Ollama availability probe should:
      - use an 8s timeout (was 3s — too short for cold starts);
      - log a recovery line when the provider transitions back to
        available;
      - NOT log WARNING on first-startup misses (those were normal
        warmup, but read like fatal errors).
    """

    def test_probe_timeout_is_eight_seconds(self, providers_src):
        # The is_available probe should use an 8s ClientTimeout.
        m = re.search(
            r"is_available[\s\S]{0,1500}?ClientTimeout\(total=(\d+)\)",
            providers_src,
        )
        assert m, "Cannot locate ClientTimeout inside is_available"
        timeout_val = int(m.group(1))
        assert timeout_val >= 8, (
            f"Probe timeout is {timeout_val}s — should be >= 8s "
            "(Ollama can be slow during model warmup)"
        )

    def test_recovery_log_line_present(self, providers_src):
        # Look for the explicit recovery log message.
        assert re.search(
            r"Ollama\s+recovered",
            providers_src,
        ), "Missing Ollama recovery log line"

    def test_first_startup_miss_is_debug_not_warning(self, providers_src):
        # Look at the is_available body. When prev is None (first probe)
        # and the result is False, the code should log at DEBUG, not
        # WARNING. We confirm by checking the structure of the unavailable
        # branch.
        m = re.search(
            r"async def is_available\(self\)[\s\S]+?(?=\n    async def |\n    def |\Z)",
            providers_src,
        )
        assert m, "Cannot locate OllamaProvider.is_available"
        body = m.group(0)
        # The unavailable branch should have a 'prev is True' guard
        # before its log.warning call (so first-startup misses don't
        # trigger WARNING).
        # We allow log.warning to exist, but only behind the prev-is-True
        # check.
        for warn_match in re.finditer(r"log\.warning\(", body):
            # Look at the 200 chars preceding each log.warning call.
            preceding = body[max(0, warn_match.start() - 200):warn_match.start()]
            assert "prev is True" in preceding, (
                "log.warning fires without a 'prev is True' guard — "
                "first-startup misses will still log at WARNING"
            )
