# -*- coding: utf-8 -*-
"""
tests/test_session45.py — Session 45 Tests

Tests for:
  1. Comms pane HTML structure
       - Both ground and space panes present
       - Handle, tabs (ALL/IC/OOC/SYS), body elements
       - Unread badge spans present
  2. Comms pane CSS
       - .comms-pane, .comms-handle, .comms-tabs, .comms-tab
       - .comms-body, .comms-row variants (cr-comm, cr-ooc, cr-sys)
       - Badge class, collapsed state
  3. Comms pane JS — state variables
       - commsEvents, commsFilter, commsUnread, COMMS_MAX present
  4. Comms pane JS — helper functions
       - isCommsEvent: routes correct event types
       - commsEventFilter: maps to right tab categories
       - buildCommsRow: present and references correct classes
       - appendToCommsPane: increments badges, appends rows
       - reRenderCommsPane: rebuilds from commsEvents array
       - setCommsFilter: updates active tab, clears badge
       - toggleCommsPane: toggles collapsed class
  5. Integration with appendEvent
       - appendEvent calls isCommsEvent and appendToCommsPane
  6. Reset on logout
       - commsEvents = [] on disconnect/reconnect
       - reRenderCommsPane called on reset
"""

import re
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

CLIENT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "static", "client.html",
)


@pytest.fixture(scope="module")
def src():
    with open(CLIENT_PATH) as f:
        return f.read()


@pytest.fixture(scope="module")
def js(src):
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", src, re.DOTALL)
    return "\n".join(scripts)


# ═══════════════════════════════════════════════════════════════════════
# 1. HTML structure
# ═══════════════════════════════════════════════════════════════════════

class TestCommsPaneHTML:

    def test_ground_pane_present(self, src):
        assert 'id="comms-pane-ground"' in src

    def test_space_pane_present(self, src):
        assert 'id="comms-pane-space"' in src

    def test_ground_handle_present(self, src):
        assert "toggleCommsPane('ground')" in src

    def test_space_handle_present(self, src):
        assert "toggleCommsPane('space')" in src

    def test_ground_body_present(self, src):
        assert 'id="comms-body-ground"' in src

    def test_space_body_present(self, src):
        assert 'id="comms-body-space"' in src

    def test_ground_tabs_present(self, src):
        assert 'id="comms-tabs-ground"' in src

    def test_space_tabs_present(self, src):
        assert 'id="comms-tabs-space"' in src

    def test_all_tab_ground(self, src):
        assert "setCommsFilter('ground','all')" in src

    def test_ic_tab_ground(self, src):
        assert "setCommsFilter('ground','ic')" in src

    def test_ooc_tab_ground(self, src):
        assert "setCommsFilter('ground','ooc')" in src

    def test_sys_tab_ground(self, src):
        assert "setCommsFilter('ground','sys')" in src

    def test_all_tab_space(self, src):
        assert "setCommsFilter('space','all')" in src

    def test_ic_tab_space(self, src):
        assert "setCommsFilter('space','ic')" in src

    def test_ooc_tab_space(self, src):
        assert "setCommsFilter('space','ooc')" in src

    def test_sys_tab_space(self, src):
        assert "setCommsFilter('space','sys')" in src

    def test_ground_badges_all(self, src):
        assert 'id="comms-badge-ground-all"' in src

    def test_ground_badges_ic(self, src):
        assert 'id="comms-badge-ground-ic"' in src

    def test_ground_badges_ooc(self, src):
        assert 'id="comms-badge-ground-ooc"' in src

    def test_ground_badges_sys(self, src):
        assert 'id="comms-badge-ground-sys"' in src

    def test_space_badges_present(self, src):
        assert 'id="comms-badge-space-all"' in src

    def test_handle_label(self, src):
        assert "comms-handle-label" in src

    def test_handle_arrow(self, src):
        assert "comms-handle-arrow" in src

    def test_panes_inside_feed_cols(self, src):
        """Comms pane must be inside the feed column divs."""
        # Ground: comms-pane-ground appears after pose-log
        g_log = src.find('id="pose-log"')
        g_pane = src.find('id="comms-pane-ground"')
        assert g_pane > g_log, "ground comms pane must come after ground pose log"

        # Space: comms-pane-space appears after pose-log-space
        s_log = src.find('id="pose-log-space"')
        s_pane = src.find('id="comms-pane-space"')
        assert s_pane > s_log, "space comms pane must come after space pose log"


# ═══════════════════════════════════════════════════════════════════════
# 2. CSS
# ═══════════════════════════════════════════════════════════════════════

class TestCommsCSS:

    def test_comms_pane_class(self, src):
        assert ".comms-pane {" in src or ".comms-pane{" in src

    def test_comms_handle_class(self, src):
        assert ".comms-handle {" in src or ".comms-handle{" in src

    def test_comms_tabs_class(self, src):
        assert ".comms-tabs {" in src or ".comms-tabs{" in src

    def test_comms_tab_class(self, src):
        assert ".comms-tab {" in src or ".comms-tab{" in src

    def test_comms_tab_active(self, src):
        assert ".comms-tab.active" in src

    def test_comms_body_class(self, src):
        assert ".comms-body {" in src or ".comms-body{" in src

    def test_comms_row_class(self, src):
        assert ".comms-row {" in src or ".comms-row{" in src

    def test_cr_comm_class(self, src):
        assert ".comms-row.cr-comm" in src or ".cr-comm" in src

    def test_cr_ooc_class(self, src):
        assert ".comms-row.cr-ooc" in src or ".cr-ooc" in src

    def test_cr_sys_class(self, src):
        assert ".comms-row.cr-sys" in src or ".cr-sys" in src

    def test_comms_badge_class(self, src):
        assert ".comms-badge" in src

    def test_badge_show_class(self, src):
        assert ".comms-badge.show" in src

    def test_collapsed_state(self, src):
        assert ".comms-pane.collapsed" in src

    def test_collapsed_hides_body(self, src):
        assert ".comms-pane.collapsed .comms-body" in src

    def test_collapsed_hides_tabs(self, src):
        assert ".comms-pane.collapsed .comms-tabs" in src

    def test_handle_arrow_rotation(self, src):
        assert "comms-handle-arrow" in src
        # Arrow rotates 180deg when collapsed
        assert "rotate(180deg)" in src


# ═══════════════════════════════════════════════════════════════════════
# 3. JS state variables
# ═══════════════════════════════════════════════════════════════════════

class TestCommsStateVars:

    def test_comms_events_array(self, js):
        assert "var commsEvents" in js or "commsEvents =" in js

    def test_comms_max(self, js):
        assert "COMMS_MAX" in js

    def test_comms_filter_object(self, js):
        assert "commsFilter" in js
        assert "ground" in js
        assert "space" in js

    def test_comms_unread_object(self, js):
        assert "commsUnread" in js

    def test_comms_unread_has_tabs(self, js):
        assert "'all'" in js or '"all"' in js
        assert "'ic'" in js or '"ic"' in js
        assert "'ooc'" in js or '"ooc"' in js
        assert "'sys'" in js or '"sys"' in js


# ═══════════════════════════════════════════════════════════════════════
# 4. JS functions
# ═══════════════════════════════════════════════════════════════════════

class TestCommsJSFunctions:

    def test_is_comms_event_defined(self, js):
        assert "function isCommsEvent" in js

    def test_is_comms_event_handles_comm_in(self, js):
        m = re.search(r"function isCommsEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m, "isCommsEvent not found"
        body = m.group(1)
        assert "comm-in" in body, "isCommsEvent must handle comm-in"

    def test_is_comms_event_handles_ooc(self, js):
        m = re.search(r"function isCommsEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        assert "ooc" in m.group(1)

    def test_is_comms_event_handles_sys(self, js):
        m = re.search(r"function isCommsEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "sys" in body, "isCommsEvent must handle sys-* types"

    def test_comms_event_filter_defined(self, js):
        assert "function commsEventFilter" in js

    def test_comms_event_filter_ic(self, js):
        m = re.search(r"function commsEventFilter\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "'ic'" in body or '"ic"' in body

    def test_comms_event_filter_ooc(self, js):
        m = re.search(r"function commsEventFilter\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "'ooc'" in body or '"ooc"' in body

    def test_build_comms_row_defined(self, js):
        assert "function buildCommsRow" in js

    def test_build_comms_row_handles_comm_in(self, js):
        m = re.search(r"function buildCommsRow\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "comm-in" in body

    def test_build_comms_row_handles_ooc(self, js):
        m = re.search(r"function buildCommsRow\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        assert "ooc" in m.group(1)

    def test_build_comms_row_has_timestamp(self, js):
        m = re.search(r"function buildCommsRow\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "tStamp" in body or "toLocaleTimeString" in body

    def test_append_to_comms_pane_defined(self, js):
        assert "function appendToCommsPane" in js

    def test_append_to_comms_pane_iterates_both_sides(self, js):
        m = re.search(r"function appendToCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "ground" in body and "space" in body

    def test_append_to_comms_pane_handles_badges(self, js):
        m = re.search(r"function appendToCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "commsUnread" in body
        assert "classList.add" in body

    def test_re_render_comms_pane_defined(self, js):
        assert "function reRenderCommsPane" in js

    def test_re_render_comms_pane_clears_body(self, js):
        m = re.search(r"function reRenderCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "innerHTML = ''" in body or 'innerHTML=""' in body

    def test_re_render_iterates_comms_events(self, js):
        m = re.search(r"function reRenderCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        assert "commsEvents" in m.group(1)

    def test_set_comms_filter_defined(self, js):
        assert "function setCommsFilter" in js

    def test_set_comms_filter_updates_state(self, js):
        m = re.search(r"function setCommsFilter\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "commsFilter" in body

    def test_set_comms_filter_clears_badge(self, js):
        m = re.search(r"function setCommsFilter\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "commsUnread" in body
        assert "classList.remove" in body

    def test_set_comms_filter_calls_rerender(self, js):
        m = re.search(r"function setCommsFilter\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        assert "reRenderCommsPane" in m.group(1)

    def test_toggle_comms_pane_defined(self, js):
        assert "function toggleCommsPane" in js

    def test_toggle_comms_pane_toggles_collapsed(self, js):
        m = re.search(r"function toggleCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "collapsed" in body
        assert "classList" in body

    def test_toggle_clears_unread_on_expand(self, js):
        m = re.search(r"function toggleCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "commsUnread" in body


# ═══════════════════════════════════════════════════════════════════════
# 5. Integration with appendEvent
# ═══════════════════════════════════════════════════════════════════════

class TestAppendEventIntegration:

    def test_append_event_calls_is_comms_event(self, js):
        m = re.search(r"function appendEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m, "appendEvent not found"
        body = m.group(1)
        assert "isCommsEvent" in body, \
            "appendEvent must call isCommsEvent to check if event belongs in comms pane"

    def test_append_event_calls_append_to_comms_pane(self, js):
        m = re.search(r"function appendEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "appendToCommsPane" in body, \
            "appendEvent must call appendToCommsPane for qualifying events"

    def test_append_event_conditional_routing(self, js):
        m = re.search(r"function appendEvent\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        # Should be conditional: if (isCommsEvent(ev)) appendToCommsPane(ev)
        assert "if" in body, \
            "appendEvent should conditionally route to comms pane"


# ═══════════════════════════════════════════════════════════════════════
# 6. Reset on logout
# ═══════════════════════════════════════════════════════════════════════

class TestCommsReset:

    def test_comms_events_reset_on_logout(self, js):
        # Find the logout/reconnect block where poseEvents is reset
        idx = js.find("commsEvents = []")
        assert idx != -1, "commsEvents must be cleared on logout/reconnect"

    def test_comms_unread_reset_on_logout(self, js):
        idx = js.find("commsUnread = {")
        assert idx != -1, "commsUnread must be reset on logout/reconnect"

    def test_re_render_called_on_reset(self, js):
        # The logout block has 'poseEvents = []; commsEvents = []' together
        # Search for the reset block specifically (not the var declaration)
        reset_idx = js.find("poseEvents = [];\n  commsEvents = []")
        if reset_idx == -1:
            reset_idx = js.find("poseEvents = [];\ncommsEvents = []")
        assert reset_idx != -1, "logout reset block with commsEvents not found"
        nearby = js[reset_idx: reset_idx + 400]
        assert "reRenderCommsPane" in nearby, \
            "reRenderCommsPane must be called after commsEvents reset"

    def test_comms_max_limits_array(self, js):
        """COMMS_MAX must be used to cap commsEvents array."""
        m = re.search(r"function appendToCommsPane\(.*?\{(.*?)^}", js, re.MULTILINE | re.DOTALL)
        assert m
        body = m.group(1)
        assert "COMMS_MAX" in body or "commsEvents.shift" in body, \
            "appendToCommsPane must cap commsEvents at COMMS_MAX"
