"""
test_m3_onboard.py — Webify Drop UI-7 (onboarding panel) render contract.

Loads static/spa/m3_onboard.js under jsdom and exercises
M3Onboard.render() against the onboarding_state shapes
engine/chain_events.build_onboarding_state emits.

Verifies: step rail counts/states; teach chips staging EXACTLY
`token + ' '` with an invented-verb-never guard; the ATTEMPT chip
appearing ONLY for skill_check_passed steps and staging the real
`chain attempt`; step-advance detection (second render with a higher
step shows the STEP COMPLETE flash + pops the freshly filled dot —
first render never flashes); the graduated card whose DISMISS fires
the onDismiss callback; and quick-action coach pulses landing on
mapped data-qa anchors only.
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_ONBOARD = str(REPO_ROOT / "static" / "spa" / "m3_onboard.js")

_BASE_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var dismissed = 0;
function onDismiss(){ dismissed++; }
var box = document.createElement('div');
document.body.appendChild(box);
// Quick-action anchors (mirrors the client's qa-row buttons).
['LOOK','SAY','INV','JOBS'].forEach(function(q){
  var b = document.createElement('button');
  b.setAttribute('data-qa', q);
  b.className = 'qa-btn';
  document.body.appendChild(b);
});
function mkState(step, extra){
  var s = {
    active: true, chain_id: 'bounty_hunter', chain_name: 'Bounty Hunter',
    step: step, total_steps: 3,
    completed_steps: (function(){ var a=[]; for (var i=1;i<step;i++) a.push(i); return a; })(),
    title: 'Step ' + step, objective: 'Do the thing for step ' + step + '.',
    location: 'somewhere', npc: 'Voss', npc_role: 'instructor',
    npc_intro: 'Listen up.', teaches: ['look', '+sheet'],
    completion_type: 'command_executed'
  };
  if (extra) Object.keys(extra).forEach(function(k){ s[k] = extra[k]; });
  return s;
}
"""


def test_rail_chips_and_exact_staged_tokens():
    out = run_with_dom([M3_ONBOARD], _BASE_JS + """
        window.M3Onboard.resetState();
        window.M3Onboard.render(box, mkState(2, { teaches: ['look','+bounties','say'] }),
                                onCmd, onDismiss);

        var dots = box.querySelectorAll('.m3o-dot').length;
        var done = box.querySelectorAll('.m3o-dot.done').length;
        var current = box.querySelectorAll('.m3o-dot.current').length;
        var flashOnFirst = box.querySelectorAll('.m3o-flash').length;

        // Stage every teach chip.
        var chips = box.querySelectorAll('.m3o-chip');
        for (var i = 0; i < chips.length; i++) chips[i].click();

        var attempt = box.querySelectorAll('.m3o-chip.attempt').length;
        var pulsed = document.querySelectorAll('.qa-btn.m3o-pulse').length;
        var pulsedQas = Array.prototype.map.call(
            document.querySelectorAll('.qa-btn.m3o-pulse'),
            function(b){ return b.getAttribute('data-qa'); }).sort();

        result = { dots: dots, done: done, current: current,
                   flashOnFirst: flashOnFirst, attempt: attempt,
                   cmds: cmds, joined: cmds.join('|'),
                   pulsed: pulsed, pulsedQas: pulsedQas };
    """)
    assert out["dots"] == 3
    assert out["done"] == 1            # step 1 completed
    assert out["current"] == 1
    assert out["flashOnFirst"] == 0    # first render never flashes
    assert out["attempt"] == 0         # command_executed → no ATTEMPT chip
    # Exact staged form: token + trailing space, corpus order.
    assert out["cmds"] == ["look ", "+bounties ", "say "]
    for invented in ("drop", "give", "breakfree", "abandon"):
        assert invented not in out["joined"]
    # look→LOOK, +bounties→JOBS, say→SAY; +sheet absent → INV untouched.
    assert out["pulsed"] == 3
    assert out["pulsedQas"] == ["JOBS", "LOOK", "SAY"]


def test_attempt_chip_only_for_skill_checks_and_stages_real_verb():
    out = run_with_dom([M3_ONBOARD], _BASE_JS + """
        window.M3Onboard.resetState();
        window.M3Onboard.render(box,
            mkState(3, { teaches: ['attack'],
                         completion_type: 'skill_check_passed' }),
            onCmd, onDismiss);
        var attempt = box.querySelector('.m3o-chip.attempt');
        attempt.click();
        result = { hasAttempt: !!attempt, cmds: cmds };
    """)
    assert out["hasAttempt"] is True
    assert out["cmds"] == ["chain attempt"]


def test_step_advance_flash_and_dot_pop():
    out = run_with_dom([M3_ONBOARD], _BASE_JS + """
        window.M3Onboard.resetState();
        window.M3Onboard.render(box, mkState(1), onCmd, onDismiss);
        var flash1 = box.querySelectorAll('.m3o-flash').length;

        window.M3Onboard.render(box, mkState(2), onCmd, onDismiss);
        var flash2 = box.querySelectorAll('.m3o-flash').length;
        var popped = box.querySelectorAll('.m3o-dot.pop').length;
        var done2 = box.querySelectorAll('.m3o-dot.done').length;

        // Re-render of the SAME step (idempotent tick) → no flash.
        window.M3Onboard.render(box, mkState(2), onCmd, onDismiss);
        var flash3 = box.querySelectorAll('.m3o-flash').length;

        result = { flash1: flash1, flash2: flash2, flash3: flash3,
                   popped: popped, done2: done2 };
    """)
    assert out["flash1"] == 0
    assert out["flash2"] == 1
    assert out["popped"] == 1          # the freshly current dot pops
    assert out["done2"] == 1
    assert out["flash3"] == 0          # same-step re-render is quiet


def test_graduated_card_and_dismiss():
    out = run_with_dom([M3_ONBOARD], _BASE_JS + """
        window.M3Onboard.resetState();
        window.M3Onboard.render(box,
            { active: false, graduated: true,
              chain_id: 'bounty_hunter', chain_name: 'Bounty Hunter' },
            onCmd, onDismiss);
        var title = box.querySelector('.m3o-grad-title').textContent;
        var name = box.querySelector('.m3o-grad-name').textContent;
        box.querySelector('.m3o-grad-dismiss').click();
        result = { title: title, name: name, dismissed: dismissed,
                   cmds: cmds };
    """)
    assert out["title"] == "CHAIN COMPLETE"
    assert out["name"] == "Bounty Hunter"
    assert out["dismissed"] == 1
    assert out["cmds"] == []           # graduation stages nothing
