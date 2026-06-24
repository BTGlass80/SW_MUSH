"""QA-drop 2026-06-23: structural guards for three confirmed live-play defects.

1. First Blood achievement gate — combat_commands.py must use can_act_now()
   PLUS a no-hostile-NPC-surviving check (not the old wound_level.value < 5).

2. Pose-deadline countdown NaN — client.html must parse the ISO deadline
   string to epoch-ms before computing remaining seconds, at both sites:
   _updatePosingPanelTick and handleCombatState.

3. Comms-pane tab mis-categorization — commsEventFilter must branch on
   ev.channel for comm-in events instead of always returning ['all','ic'].
"""

import pathlib
import re
import ast

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _src(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# 1. First Blood — achievement must gate on can_act_now() + win check
# ─────────────────────────────────────────────────────────────────────────────

def test_first_blood_no_longer_uses_wound_level_value_lt_5():
    """The old gate `wound_level.value < 5` admits INCAPACITATED PCs (value 4).
    It must be gone from the achievement block."""
    s = _src("parser/combat_commands.py")
    # The old pattern must not appear in the achievement section.
    # We search for it globally; the chain-events block further down uses
    # wound_level only in comments, not as a live guard.
    assert "c.char.wound_level.value < 5" not in s, (
        "Old `wound_level.value < 5` gate still present — INCAPACITATED PCs "
        "(value 4) would incorrectly receive the First Blood achievement"
    )


def test_first_blood_uses_can_act_now_for_pc_survivor_check():
    """Surviving PC check must use can_act_now(), which covers the wound
    ladder AND the stun-KO wall-clock gate."""
    s = _src("parser/combat_commands.py")
    # The achievement block uses can_act_now() for PCs.
    assert "c.char.can_act_now()" in s, (
        "Achievement survivor gate must use c.char.can_act_now() "
        "(covers incapacitated + stun-KO, not just wound level)"
    )


def test_first_blood_gates_on_no_surviving_npc():
    """The win check: no hostile NPC may still be able to act when the
    achievement fires.  The fix introduces _active_npcs_remain."""
    s = _src("parser/combat_commands.py")
    assert "_active_npcs_remain" in s, (
        "Achievement block must compute _active_npcs_remain to gate the "
        "award — otherwise a PC who went down (fight ended via other means) "
        "could still receive First Blood"
    )
    assert "not _active_npcs_remain" in s, (
        "Achievement block must guard with 'not _active_npcs_remain'"
    )


def test_combat_commands_parses_cleanly():
    """Syntax check: parser/combat_commands.py must compile without error."""
    src = _src("parser/combat_commands.py")
    ast.parse(src, filename="parser/combat_commands.py")  # raises SyntaxError if broken


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pose-deadline countdown NaN fix
# ─────────────────────────────────────────────────────────────────────────────

def _client_html() -> str:
    return _src("static/client.html")


def test_pose_deadline_parsed_to_epoch_in_posingpaneltick():
    """_updatePosingPanelTick must parse the ISO deadline string to epoch-ms
    before computing remaining seconds.  The old subtraction
    `d.pose_deadline - Date.now() / 1000` yields NaN because pose_deadline
    is an ISO string, not a number."""
    html = _client_html()
    # New pattern: new Date(d.pose_deadline).getTime()
    assert "new Date(d.pose_deadline).getTime()" in html, (
        "_updatePosingPanelTick must call new Date(d.pose_deadline).getTime() "
        "to convert the ISO string to epoch-ms before computing remaining seconds"
    )
    # Old pattern must be gone
    assert "d.pose_deadline - Date.now() / 1000" not in html, (
        "Old `d.pose_deadline - Date.now() / 1000` still present — "
        "subtracting an ISO string from a number yields NaN"
    )


def test_pose_deadline_parsed_to_epoch_in_handlecombatstate():
    """handleCombatState (#ch-deadline pill) must also parse the ISO deadline."""
    html = _client_html()
    assert "new Date(data.pose_deadline).getTime()" in html, (
        "handleCombatState must call new Date(data.pose_deadline).getTime() "
        "to convert the ISO string to epoch-ms"
    )
    assert "data.pose_deadline - Date.now() / 1000" not in html, (
        "Old `data.pose_deadline - Date.now() / 1000` still present — "
        "subtracting an ISO string from a number yields NaN"
    )


def test_both_deadline_sites_use_epoch_subtraction():
    """Both sites must compute (epochMs - Date.now()) / 1000, not
    (isoString - Date.now() / 1000)."""
    html = _client_html()
    # The corrected pattern divides the whole difference by 1000
    pattern = r"new Date\([^)]+\)\.getTime\(\) - Date\.now\(\)\) / 1000"
    matches = re.findall(pattern, html)
    assert len(matches) >= 2, (
        f"Expected at least 2 epoch-ms deadline computations, found {len(matches)}: "
        "both _updatePosingPanelTick and handleCombatState must be fixed"
    )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Comms-pane tab filter — comm-in must branch on ev.channel
# ─────────────────────────────────────────────────────────────────────────────

def test_comms_filter_branches_on_channel_for_comm_in():
    """commsEventFilter must not unconditionally return ['all','ic'] for every
    comm-in event.  It must check ev.channel to separate OOC from IC traffic."""
    html = _client_html()
    # Old single-line return for comm-in must be gone
    assert "if (ev.t === 'comm-in') return ['all', 'ic'];" not in html, (
        "commsEventFilter still routes ALL comm-in events to IC — "
        "OOC channel messages are mis-categorized"
    )


def test_comms_filter_ooc_channel_routes_to_ooc():
    """The new branch must explicitly map channel==='ooc' to ['all','ooc']."""
    html = _client_html()
    # The corrected function body contains the channel check
    assert "ev.channel === 'ooc'" in html, (
        "commsEventFilter must check ev.channel === 'ooc' to route OOC "
        "comm-in events to the OOC tab"
    )
    assert "'all', 'ooc'" in html, (
        "commsEventFilter must return ['all','ooc'] for OOC comm-in events"
    )


def test_comms_filter_ic_channel_routes_to_ic():
    """Non-OOC comm-in events must still go to IC."""
    html = _client_html()
    # The else branch still returns ic
    assert "'all', 'ic'" in html, (
        "commsEventFilter must still return ['all','ic'] for IC comm-in events"
    )


def test_buildcommsrow_category_derivation_still_uses_filter():
    """buildCommsRow derives `cat` from commsEventFilter(ev)[1] — confirm
    the call is still there so category routing stays unified."""
    html = _client_html()
    assert "commsEventFilter(ev)[1]" in html, (
        "buildCommsRow must still call commsEventFilter(ev)[1] to derive "
        "the category — direct derivation would split the routing logic"
    )


def test_handlechatmsg_sets_channel_on_comm_in_event():
    """handleChatMsg must propagate msg.channel onto the comm-in event so
    commsEventFilter can inspect ev.channel."""
    html = _client_html()
    # The handler copies channel from the server message
    assert "channel: msg.channel" in html, (
        "handleChatMsg must set channel: msg.channel on the comm-in event "
        "so commsEventFilter can distinguish OOC from IC"
    )
