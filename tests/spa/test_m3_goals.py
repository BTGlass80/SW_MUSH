"""
test_m3_goals.py — UX Drop 6 (Goals / objectives tracker) render contract.

Two layers, mirroring tests/spa/test_m3_situation_board.py (jsdom DOM-runtime)
+ test_m3_scene_panel.py (static client.html wiring parse):

  A. jsdom DOM-runtime of static/spa/m3_goals.js — a representative
     goals_status payload renders the questline + mission + bounty rows with
     their progress (step rail / reward / countdown); an all-null payload
     returns null (panel hidden); the action chip stages exactly the authored
     command and NEVER auto-sends; the bounty countdown formats via the shared
     formatter; a re-render with a dropped slot removes that row; server-
     authored titles/names are XSS-escaped.

  B. Static parse of static/client.html + server/session.py — the goals-panel
     DOM ids exist, handleGoalsStatus is defined + dispatched on 'goals_status',
     the module is loaded, and the server pushes goals_status from the new
     _hud_sidebar_goals producer on the existing HUD tick.
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_GOALS = str(REPO_ROOT / "static" / "spa" / "m3_goals.js")
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
SESSION_PY = REPO_ROOT / "server" / "session.py"


_BASE = """
var box = document.createElement('div');
document.body.appendChild(box);
window.M3Goals.init({ escapeHtml: function(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}});
var staged = [];
function stage(cmd){ staged.push(cmd); }
"""

_PAYLOAD_JS = """
var data = {
  questline: { chain_id: 'smuggler_run', title: 'The Kessel Gambit',
               objective: 'Slice the customs terminal at Bay 94.',
               step: 2, total_steps: 4, next_hint: 'Return to Marunt for the payoff.',
               command_to_type: 'chain attempt' },
  mission:   { id: 'm-abc123', title: 'Deliver medpacs to the cantina',
               objective: 'Drop the crate at Chalmun\\'s.', reward: 750,
               stage_cmd: '+missions' },
  bounty:    { id: 'b-xyz789', target_name: 'Tarko Vinn', tier: 'veteran',
               reward: 2400, expires_in_secs: 11030, stage_cmd: 'bounties' }
};
"""


# ════════════════════════════════════════════════════════════════════════
# A. jsdom — m3_goals.js render contract
# ════════════════════════════════════════════════════════════════════════

def test_renders_all_three_goal_rows_with_progress():
    out = run_with_dom([M3_GOALS], _BASE + _PAYLOAD_JS + """
        var node = window.M3Goals.render(data, stage);
        box.appendChild(node);

        var quest = box.querySelector('[data-goal="questline"]');
        var mission = box.querySelector('[data-goal="mission"]');
        var bounty = box.querySelector('[data-goal="bounty"]');

        result = {
            questTitle: quest.querySelector('.m3g-title').textContent,
            questStep: quest.querySelector('.m3g-step').textContent,
            railDots: quest.querySelectorAll('.m3g-dot').length,
            railDone: quest.querySelectorAll('.m3g-dot.done').length,
            railCurrent: quest.querySelectorAll('.m3g-dot.current').length,
            questNext: quest.querySelector('.m3g-next-text').textContent,
            missionTitle: mission.querySelector('.m3g-title').textContent,
            missionReward: mission.querySelector('.m3g-reward').textContent,
            bountyTarget: bounty.querySelector('.m3g-title').textContent,
            bountyTier: bounty.querySelector('.m3g-tier').textContent,
            bountyCount: bounty.querySelector('.m3g-count').textContent
        };
    """)
    assert out["questTitle"] == "The Kessel Gambit"
    assert out["questStep"] == "STEP 2/4"
    # 4 dots; step 2 → 1 done (step 1), 1 current (step 2).
    assert out["railDots"] == 4
    assert out["railDone"] == 1
    assert out["railCurrent"] == 1
    assert "Marunt" in out["questNext"]
    assert out["missionTitle"] == "Deliver medpacs to the cantina"
    assert "750" in out["missionReward"]
    assert out["bountyTarget"] == "Tarko Vinn"
    assert out["bountyTier"] == "Veteran"           # humanized
    # 11030s → 3h 03m via fmtCountdown.
    assert out["bountyCount"] == "3h 03m"


def test_empty_payload_returns_null():
    out = run_with_dom([M3_GOALS], _BASE + """
        var a = window.M3Goals.render(null, stage);
        var b = window.M3Goals.render(undefined, stage);
        var c = window.M3Goals.render({}, stage);
        var d = window.M3Goals.render(
            { questline: null, mission: null, bounty: null }, stage);
        result = { a: a === null, b: b === null, c: c === null, d: d === null };
    """)
    assert out["a"] and out["b"] and out["c"] and out["d"], (
        "no goals must return null so the panel is hidden"
    )


def test_action_chips_stage_authored_command_and_never_send():
    out = run_with_dom([M3_GOALS], _BASE + _PAYLOAD_JS + """
        var node = window.M3Goals.render(data, stage);
        box.appendChild(node);
        // Click every action chip.
        var chips = box.querySelectorAll('.m3g-chip');
        for (var i = 0; i < chips.length; i++){ chips[i].click(); }
        result = { staged: staged, chipCount: chips.length };
    """)
    # The questline TYPE chip stages 'chain attempt'; mission stages '+missions';
    # bounty stages 'bounties' — exactly the authored literals, in row order.
    assert out["chipCount"] == 3
    assert out["staged"] == ["chain attempt", "+missions", "bounties"]


def test_bounty_countdown_uses_shared_formatter():
    out = run_with_dom([M3_GOALS], _BASE + """
        var g = window.M3Goals;
        result = {
            none: g.fmtCountdown(null),
            expired: g.fmtCountdown(0),
            mins: g.fmtCountdown(125),     // 2m 05s
            hours: g.fmtCountdown(11030)   // 3h 03m
        };
    """)
    assert out["none"] == ""
    assert out["expired"] == "EXPIRED"
    assert out["mins"] == "2m 05s"
    assert out["hours"] == "3h 03m"


def test_dropped_slot_is_removed_on_rerender():
    out = run_with_dom([M3_GOALS], _BASE + _PAYLOAD_JS + """
        // First render: all three rows.
        var n1 = window.M3Goals.render(data, stage);
        var firstRows = n1.querySelectorAll('.m3g-row').length;
        // Re-render with the mission dropped.
        data.mission = null;
        var n2 = window.M3Goals.render(data, stage);
        result = {
            firstRows: firstRows,
            secondRows: n2.querySelectorAll('.m3g-row').length,
            hasMission: !!n2.querySelector('[data-goal="mission"]'),
            hasQuest: !!n2.querySelector('[data-goal="questline"]'),
            hasBounty: !!n2.querySelector('[data-goal="bounty"]')
        };
    """)
    assert out["firstRows"] == 3
    assert out["secondRows"] == 2
    assert out["hasMission"] is False        # dropped slot removed
    assert out["hasQuest"] is True
    assert out["hasBounty"] is True


def test_questline_only_renders_without_throw():
    out = run_with_dom([M3_GOALS], _BASE + """
        var data = { questline: { chain_id: 'q', title: 'Solo arc',
                       objective: 'do the thing', step: 1, total_steps: 3,
                       next_hint: '', command_to_type: '' },
                     mission: null, bounty: null };
        var node = window.M3Goals.render(data, stage);
        box.appendChild(node);
        result = {
            rows: box.querySelectorAll('.m3g-row').length,
            hasQuest: !!box.querySelector('[data-goal="questline"]'),
            // empty command_to_type → no TYPE chip
            chips: box.querySelectorAll('.m3g-chip').length
        };
    """)
    assert out["rows"] == 1
    assert out["hasQuest"] is True
    assert out["chips"] == 0     # no authored command → no invented verb chip


def test_titles_and_names_are_xss_escaped():
    out = run_with_dom([M3_GOALS], _BASE + """
        var data = {
          questline: { chain_id: 'q', title: "<script>alert('q')</script>",
                       objective: '<img src=x onerror=alert(2)>',
                       step: 1, total_steps: 1, next_hint: '', command_to_type: '' },
          mission: { id: 'm', title: '<b>boom</b>', objective: 'x', reward: 1,
                     stage_cmd: '+missions' },
          bounty: { id: 'b', target_name: "<img src=x onerror=alert(1)>",
                    tier: 'novice', reward: 1, expires_in_secs: 60, stage_cmd: 'bounties' }
        };
        var node = window.M3Goals.render(data, stage);
        box.appendChild(node);
        result = {
            liveScripts: box.querySelectorAll('script').length,
            liveImgs: box.querySelectorAll('img').length,
            questTitle: box.querySelector('[data-goal="questline"] .m3g-title').textContent,
            bountyTarget: box.querySelector('[data-goal="bounty"] .m3g-title').textContent
        };
    """)
    assert out["liveScripts"] == 0, "questline title must not inject a live <script>"
    assert out["liveImgs"] == 0, "names/objectives must not inject a live <img>"
    # The literal text survives as inert text content.
    assert "<script>" in out["questTitle"]
    assert "<img" in out["bountyTarget"]


def test_countdown_interval_lifecycle():
    """Off-cost-free: start() arms the interval only when there's a live
    countdown; stop() clears it (no leak)."""
    out = run_with_dom([M3_GOALS], _BASE + _PAYLOAD_JS + """
        var node = window.M3Goals.render(data, stage);
        box.appendChild(node);
        var before = window.M3Goals.isTicking();
        window.M3Goals.start(box);
        var afterStart = window.M3Goals.isTicking();
        window.M3Goals.stop();
        var afterStop = window.M3Goals.isTicking();

        // A payload with no bounty countdown must NOT arm the interval.
        var box2 = document.createElement('div');
        var noCount = window.M3Goals.render(
            { questline: null, mission: data.mission, bounty: null }, stage);
        box2.appendChild(noCount);
        window.M3Goals.start(box2);
        var noCountTicking = window.M3Goals.isTicking();
        window.M3Goals.stop();

        result = { before: before, afterStart: afterStart,
                   afterStop: afterStop, noCountTicking: noCountTicking };
    """)
    assert out["before"] is False
    assert out["afterStart"] is True, "start() must arm the countdown interval"
    assert out["afterStop"] is False, "stop() must clear the interval"
    assert out["noCountTicking"] is False, (
        "no live countdown in the panel → no interval armed"
    )


# ════════════════════════════════════════════════════════════════════════
# B. Static wire-up guards (no node needed)
# ════════════════════════════════════════════════════════════════════════

def test_goals_panel_wired_into_client_html():
    html = CLIENT_HTML.read_text(encoding="utf-8")
    for needle in (
        'id="goals-panel"',
        'id="goals-body"',
        "/static/spa/m3_goals.js",
        "case 'goals_status':",
        "function handleGoalsStatus(",
        "function hideGoalsPanel(",
        "function stageFromGoals(",
        "M3Goals.render(",
    ):
        assert needle in html, f"goals panel wiring missing from client.html: {needle!r}"


def test_goals_status_pushed_by_server():
    sess = SESSION_PY.read_text(encoding="utf-8")
    assert "_hud_sidebar_goals" in sess, "goals push helper missing"
    assert '"goals_status"' in sess, "goals_status send missing"
    # Composes the three EXISTING readers (no new system).
    assert "get_questline_status" in sess
    assert "get_mission_board" in sess
    assert "get_bounty_board" in sess
    # Rides the existing HUD tick (called from send_hud_update).
    assert "send_hud_update" in sess


def test_chip_stages_never_autosend_in_module_source():
    """Defense-in-depth: the module must STAGE via the injected callback and
    never call sendCmd/send directly (the invented-verb / no-auto-send rail)."""
    src = (REPO_ROOT / "static" / "spa" / "m3_goals.js").read_text(encoding="utf-8")
    assert "sendCmd" not in src, "goals module must not auto-send commands"
    assert "data-stage-cmd" in src, "action chips must carry the authored literal"
