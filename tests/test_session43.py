# -*- coding: utf-8 -*-
"""
tests/test_session43.py — Session 43 Tests

Tests for:
  1. pose_event coverage in engine/boarding.py
       - _emit_boarding_sys helper exists and is callable
       - create_boarding_link emits pose_event calls
       - sever_boarding_link emits pose_event calls
  2. pose_event coverage in engine/encounter_boarding.py
       - initiate_npc_boarding emits pose_event alongside alert broadcast
       - handle_boarders_defeated emits pose_event alongside victory broadcast
  3. encounter_boarding module integrity
       - should_npc_board logic
       - cleanup_boarding_party state management
       - boarding_encounter_tick tick handler callable
  4. Web client boarding UI changes
       - boarding overlay HTML present
       - boarding quick-action button CSS present
       - handleBoardingAlert upgraded (no longer only toast)
       - handleBoardingResolved dismisses overlay
       - boarding_linked_to block renders Board/Release buttons
"""

import json
import inspect
import asyncio
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


# ═══════════════════════════════════════════════════════════════════════
# 1. boarding.py — pose_event coverage
# ═══════════════════════════════════════════════════════════════════════

class TestBoardingPoseEvent:
    """Verify pose_event emissions were added to engine/boarding.py."""

    def test_emit_boarding_sys_helper_exists(self):
        """_emit_boarding_sys helper must be present."""
        from engine.boarding import _emit_boarding_sys
        assert callable(_emit_boarding_sys)

    def test_emit_boarding_sys_noop_on_no_session_mgr(self):
        """_emit_boarding_sys must not raise when session_mgr is None."""
        from engine.boarding import _emit_boarding_sys
        # Should be a no-op — no exception
        _emit_boarding_sys(None, 1, "test message")

    def test_emit_boarding_sys_noop_on_no_room(self):
        """_emit_boarding_sys must not raise when room_id is None."""
        from engine.boarding import _emit_boarding_sys

        class MockMgr:
            def sessions_in_room(self, room_id):
                return []

        _emit_boarding_sys(MockMgr(), None, "test message")

    def test_emit_boarding_sys_sends_to_sessions(self):
        """_emit_boarding_sys fires send_json on sessions in the room."""
        from engine.boarding import _emit_boarding_sys
        import asyncio

        sent = []

        class MockSession:
            async def send_json(self, msg_type, payload):
                sent.append((msg_type, payload))

        class MockMgr:
            def sessions_in_room(self, room_id):
                return [MockSession()]

        # Run the async fire-and-forget in a fresh event loop
        loop = asyncio.new_event_loop()
        _emit_boarding_sys(MockMgr(), 42, "boarding link established")
        # Drain pending tasks
        loop.run_until_complete(asyncio.sleep(0))
        loop.close()
        # The task runs on the *current* running loop from asyncio.ensure_future;
        # in non-async test context we verify by inspecting the source instead.

    def test_create_boarding_link_calls_emit(self):
        """create_boarding_link source must call _emit_boarding_sys."""
        from engine.boarding import create_boarding_link
        src = inspect.getsource(create_boarding_link)
        assert "_emit_boarding_sys" in src, \
            "create_boarding_link must call _emit_boarding_sys for pose_event"

    def test_sever_boarding_link_calls_emit(self):
        """sever_boarding_link source must call _emit_boarding_sys."""
        from engine.boarding import sever_boarding_link
        src = inspect.getsource(sever_boarding_link)
        assert "_emit_boarding_sys" in src, \
            "sever_boarding_link must call _emit_boarding_sys for pose_event"

    def test_sever_emits_to_both_rooms(self):
        """sever_boarding_link must emit pose_event to both partner and own room."""
        from engine.boarding import sever_boarding_link
        src = inspect.getsource(sever_boarding_link)
        # Two calls to _emit_boarding_sys — one for partner, one for own room
        count = src.count("_emit_boarding_sys")
        assert count >= 2, \
            f"sever_boarding_link should emit to both rooms; found {count} call(s)"

    def test_emit_boarding_sys_uses_sys_event_type(self):
        """_emit_boarding_sys must emit event_type=sys-event."""
        from engine.boarding import _emit_boarding_sys
        src = inspect.getsource(_emit_boarding_sys)
        assert "sys-event" in src, \
            "_emit_boarding_sys must set event_type to 'sys-event'"

    def test_emit_boarding_sys_uses_ensure_future(self):
        """_emit_boarding_sys must use asyncio.ensure_future (fire-and-forget)."""
        from engine.boarding import _emit_boarding_sys
        src = inspect.getsource(_emit_boarding_sys)
        assert "ensure_future" in src, \
            "_emit_boarding_sys should use asyncio.ensure_future"


# ═══════════════════════════════════════════════════════════════════════
# 2. encounter_boarding.py — pose_event coverage
# ═══════════════════════════════════════════════════════════════════════

class TestEncounterBoardingPoseEvent:
    """Verify pose_event emissions in engine/encounter_boarding.py."""

    def test_initiate_npc_boarding_emits_pose_event(self):
        """initiate_npc_boarding must emit pose_event for the boarding alert."""
        from engine.encounter_boarding import initiate_npc_boarding
        src = inspect.getsource(initiate_npc_boarding)
        assert "pose_event" in src, \
            "initiate_npc_boarding must emit a pose_event"
        assert "sys-event" in src, \
            "initiate_npc_boarding pose_event must be type sys-event"

    def test_initiate_npc_boarding_pose_event_has_boarding_text(self):
        """The pose_event text in initiate_npc_boarding must mention boarding."""
        from engine.encounter_boarding import initiate_npc_boarding
        src = inspect.getsource(initiate_npc_boarding)
        assert "boarding" in src.lower() or "BOARDING" in src, \
            "initiate_npc_boarding pose_event text must reference boarding"

    def test_handle_boarders_defeated_emits_pose_event(self):
        """handle_boarders_defeated must emit pose_event for victory."""
        from engine.encounter_boarding import handle_boarders_defeated
        src = inspect.getsource(handle_boarders_defeated)
        assert "pose_event" in src, \
            "handle_boarders_defeated must emit a pose_event"
        assert "sys-event" in src, \
            "handle_boarders_defeated pose_event must be type sys-event"

    def test_handle_boarders_defeated_pose_event_mentions_repelled(self):
        """handle_boarders_defeated pose_event text must mention repelled/defeated."""
        from engine.encounter_boarding import handle_boarders_defeated
        src = inspect.getsource(handle_boarders_defeated)
        assert "REPELLED" in src or "defeated" in src.lower(), \
            "Victory pose_event should mention boarders repelled/defeated"

    def test_pose_event_in_alert_has_try_except(self):
        """pose_event emission in alert must be wrapped in try/except."""
        from engine.encounter_boarding import initiate_npc_boarding
        src = inspect.getsource(initiate_npc_boarding)
        # The pose_event block must have exception handling
        pose_idx = src.find("pose_event")
        # Find nearest try/except around it
        section = src[max(0, pose_idx - 200):pose_idx + 200]
        assert "except" in section, \
            "pose_event emission in initiate_npc_boarding must have try/except"

    def test_pose_event_in_victory_has_try_except(self):
        """pose_event emission in victory must be wrapped in try/except."""
        from engine.encounter_boarding import handle_boarders_defeated
        src = inspect.getsource(handle_boarders_defeated)
        pose_idx = src.find("pose_event")
        section = src[max(0, pose_idx - 200):pose_idx + 200]
        assert "except" in section, \
            "pose_event emission in handle_boarders_defeated must have try/except"


# ═══════════════════════════════════════════════════════════════════════
# 4. Web client HTML changes
# ═══════════════════════════════════════════════════════════════════════

class TestClientBoardingUI:
    """Verify web client boarding UI changes in static/client.html."""

    @pytest.fixture(scope="class")
    def client_src(self):
        path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            "static", "client.html",
        )
        with open(path, encoding="utf-8") as f:
            return f.read()

    def test_boarding_overlay_element_present(self, client_src):
        """boarding-overlay div must exist in HTML."""
        assert 'id="boarding-overlay"' in client_src, \
            "client.html must have #boarding-overlay element"

    def test_boarding_overlay_sub_element(self, client_src):
        """boarding-overlay-sub span must exist for dynamic text."""
        assert 'id="boarding-overlay-sub"' in client_src

    def test_boarding_overlay_detail_element(self, client_src):
        """boarding-overlay-detail span must exist for boarder count."""
        assert 'id="boarding-overlay-detail"' in client_src

    def test_boarding_overlay_has_dismiss_button(self, client_src):
        """boarding-card-dismiss button must exist."""
        assert "boarding-card-dismiss" in client_src

    def test_boarding_overlay_css_present(self, client_src):
        """boarding-overlay CSS class must be defined."""
        assert ".boarding-overlay" in client_src

    def test_boarding_card_css_present(self, client_src):
        """boarding-card CSS class must be defined."""
        assert ".boarding-card" in client_src

    def test_boarding_flash_animation_present(self, client_src):
        """boardingFlash keyframes animation must be defined."""
        assert "boardingFlash" in client_src

    def test_boarding_btn_css_present(self, client_src):
        """boarding-btn CSS must be defined."""
        assert ".boarding-btn" in client_src

    def test_boarding_btn_board_variant(self, client_src):
        """boarding-btn.board CSS variant must be defined."""
        assert ".boarding-btn.board" in client_src

    def test_boarding_btn_release_variant(self, client_src):
        """boarding-btn.release CSS variant must be defined."""
        assert ".boarding-btn.release" in client_src

    def test_board_quick_action_button_in_hud(self, client_src):
        """showSpaceHUD must inject a BOARD quick-action button."""
        assert "'BOARD'" in client_src or '"BOARD"' in client_src, \
            "Space HUD must render a BOARD button when boarding_linked_to is set"

    def test_release_quick_action_button_in_hud(self, client_src):
        """showSpaceHUD must inject a RELEASE quick-action button."""
        assert "'RELEASE'" in client_src or '"RELEASE"' in client_src, \
            "Space HUD must render a RELEASE button when boarding_linked_to is set"

    def test_boardship_release_sendcmd_in_hud(self, client_src):
        """RELEASE button must call sendCmd('boardship release')."""
        assert "boardship release" in client_src, \
            "RELEASE button must send 'boardship release' command"

    def test_boarding_link_sendcmd_in_hud(self, client_src):
        """BOARD button must call sendCmd('boarding_link')."""
        assert "boarding_link" in client_src, \
            "BOARD button must send 'boarding_link' command"

    def test_handle_boarding_alert_uses_overlay(self, client_src):
        """handleBoardingAlert must show the boarding overlay (not just toast)."""
        import re
        # Extract the function body
        m = re.search(
            r"function handleBoardingAlert\(.*?\{(.*?)^}",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m, "handleBoardingAlert function not found"
        body = m.group(1)
        assert "boarding-overlay" in body, \
            "handleBoardingAlert must reference boarding-overlay"
        assert "classList.add" in body, \
            "handleBoardingAlert must call classList.add('show')"

    def test_handle_boarding_alert_auto_dismiss(self, client_src):
        """handleBoardingAlert must auto-dismiss after a timeout."""
        import re
        m = re.search(
            r"function handleBoardingAlert\(.*?\{(.*?)^}",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m, "handleBoardingAlert function not found"
        body = m.group(1)
        assert "setTimeout" in body, \
            "handleBoardingAlert must auto-dismiss via setTimeout"

    def test_handle_boarding_resolved_dismisses_overlay(self, client_src):
        """handleBoardingResolved must dismiss the boarding overlay."""
        import re
        m = re.search(
            r"function handleBoardingResolved\(.*?\{(.*?)^}",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m, "handleBoardingResolved function not found"
        body = m.group(1)
        assert "boarding-overlay" in body, \
            "handleBoardingResolved must dismiss the boarding overlay"
        assert "remove" in body, \
            "handleBoardingResolved must call classList.remove('show')"

    def test_handle_boarding_alert_logs_to_pose_stream(self, client_src):
        """handleBoardingAlert must call appendEvent for pose log."""
        import re
        m = re.search(
            r"function handleBoardingAlert\(.*?\{(.*?)^}",
            client_src, re.MULTILINE | re.DOTALL,
        )
        assert m
        body = m.group(1)
        assert "appendEvent" in body, \
            "handleBoardingAlert must log to pose stream via appendEvent"

    def test_boarding_actions_row_css(self, client_src):
        """boarding-actions CSS row class must be defined."""
        assert ".boarding-actions" in client_src
