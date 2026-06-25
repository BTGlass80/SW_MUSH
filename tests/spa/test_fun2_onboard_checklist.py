"""
test_fun2_onboard_checklist.py — FUN2 tutorial soft-lock fix (panel render).

m3_onboard.js now renders the step's `prereqs` as a live checklist (done/
pending) and LOCKS the TYPE chip when `prereqs_met` is false — so the player
SEES the gate instead of the talk silently stalling.
"""
from __future__ import annotations

from tests.spa.spa_dom_harness import run_with_dom

_SCRIPTS = ["static/spa/m3_onboard.js"]


def _render(data_js: str) -> dict:
    setup = (
        "var body = document.createElement('div');"
        "var staged = [];"
        "window.M3Onboard.render(body, " + data_js + ","
        " function(cmd){ staged.push(cmd); }, function(){});"
        "result = {"
        "  prereqRows: body.querySelectorAll('.m3o-prereq').length,"
        "  doneRows: body.querySelectorAll('.m3o-prereq.done').length,"
        "  locked: !!body.querySelector('.m3o-chip.attempt.locked'),"
        "  hasAttemptChip: !!body.querySelector('.m3o-chip.attempt'),"
        "  text: body.textContent"
        "};"
    )
    return run_with_dom(_SCRIPTS, setup)


_BASE = (
    "{ active:true, chain_id:'republic_soldier', chain_name:'Republic Soldier',"
    " step:1, total_steps:5, completed_steps:[], title:'Reporting In',"
    " objective:'Report in.', npc:'Major Tarrn', npc_role:'instructor',"
    " teaches:[], completion_type:'talk_to_npc',"
    " command_to_type:'talk Major Tarrn',"
)


def test_checklist_renders_with_done_state():
    r = _render(_BASE + " prereqs:[{command:'look',done:true},"
                        "{command:'+sheet',done:false}], prereqs_met:false }")
    assert r["prereqRows"] == 2, r
    assert r["doneRows"] == 1, r
    assert "+sheet" in r["text"]
    assert "look" in r["text"]


def test_type_chip_locked_when_prereqs_unmet():
    r = _render(_BASE + " prereqs:[{command:'look',done:false},"
                        "{command:'+sheet',done:false}], prereqs_met:false }")
    assert r["locked"] is True, r
    assert "DO THE STEPS ABOVE FIRST" in r["text"]


def test_type_chip_unlocked_when_prereqs_met():
    r = _render(_BASE + " prereqs:[{command:'look',done:true},"
                        "{command:'+sheet',done:true}], prereqs_met:true }")
    assert r["locked"] is False, r
    assert r["hasAttemptChip"] is True
    assert "TYPE" in r["text"]


def test_no_checklist_when_no_prereqs():
    # A step without requires_first emits no prereqs key → no checklist, no lock.
    r = _render(_BASE + " }")
    assert r["prereqRows"] == 0
    assert r["locked"] is False
    assert r["hasAttemptChip"] is True
