"""
test_m3_region.py — Webify Drop UI-2 (Region-control panel) render contract.

Loads static/spa/m3_region.js under jsdom and exercises M3Region.render()
against a representative region_state block (the shape produced by
engine/territory_display.get_region_data_block). Verifies the panel structure,
the viewer-row highlight, the 0-150 influence ladder with 50/100 threshold
ticks, the resource chips (good/bad/best), the active-contest tug-of-war +
countdown, and the unaligned-observer (spectating) state.

IMPORTANT: M3Region.render starts a 1s countdown setInterval for an active
contest. The setup scripts call M3Region.stop() before returning so Node's
event loop drains and the harness process exits (otherwise it would hang).
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_REGION = str(REPO_ROOT / "static" / "spa" / "m3_region.js")


_BLOCK_JS = """
var block = {
  region_slug: 'dune_sea',
  viewer_org: 'hutt_cartel',
  region_name: 'The Dune Sea',
  planet: 'Tatooine',
  security: 'lawless',
  description: 'A trackless ocean of sand.',
  ownership: { org_code: 'hutt_cartel', org_name: 'Hutt Cartel', tier: 'foothold' },
  influence: [
    { org_code: 'hutt_cartel', org_name: 'Hutt Cartel', score: 75, tier: 'foothold', is_viewer: true },
    { org_code: 'bounty_hunters_guild', org_name: 'Bounty Hunters Guild', score: 30, tier: 'no_presence', is_viewer: false }
  ],
  resource_outlook: {
    best:  { type: 'durasteel', multiplier: 1.4 },
    worst: { type: 'water', multiplier: 0.6 },
    all:   { durasteel: 1.4, water: 0.6, food: 1.0 }
  },
  active_contest: {
    challenger_org: 'bounty_hunters_guild',
    defender_org: 'hutt_cartel',
    phase: 'active',
    secs_remaining: 125,
    accumulation: { bounty_hunters_guild: 30, hutt_cartel: 75 }
  }
};
"""


def test_region_panel_structure_and_highlight():
    out = run_with_dom([M3_REGION], _BLOCK_JS + """
        var root = window.M3Region.render(block);

        var infRows = root.querySelectorAll('.rgn-inf-row');
        var meRow = root.querySelector('.rgn-inf-row.me');
        var fillW = meRow.querySelector('.rgn-inf-fill').getAttribute('style');
        var ticks = meRow.querySelectorAll('.rgn-inf-tick');
        var tickLefts = Array.prototype.map.call(ticks, function(t){ return t.getAttribute('style'); });
        // the non-viewer (no_presence) row must omit a tier badge
        var otherRow = infRows[1];

        var resChips = root.querySelectorAll('.rgn-res-chip');
        var dura = null, water = null;
        Array.prototype.forEach.call(resChips, function(c){
            var t = c.querySelector('.rgn-res-type').textContent;
            if (t === 'durasteel') dura = c;
            if (t === 'water') water = c;
        });

        window.M3Region.stop();  // drain the countdown interval so node exits
        result = {
            name: root.querySelector('.rgn-name').textContent,
            secBadge: !!root.querySelector('.room-sec-badge.lawless'),
            secText: root.querySelector('.room-sec-badge.lawless').textContent,
            planet: root.querySelector('.rgn-planet').textContent,
            ownName: root.querySelector('.rgn-own-name').textContent,
            infCount: infRows.length,
            meIsHutt: meRow.querySelector('.rgn-inf-name').textContent,
            meHasYou: !!meRow.querySelector('.rgn-inf-you'),
            meFillWidth: fillW,
            meTierText: meRow.querySelector('.rgn-inf-tier') ? meRow.querySelector('.rgn-inf-tier').textContent : null,
            otherHasTier: !!otherRow.querySelector('.rgn-inf-tier'),
            tickLefts: tickLefts,
            chipCount: resChips.length,
            duraClass: dura.getAttribute('class'),
            waterClass: water.getAttribute('class'),
            duraMult: dura.querySelector('.rgn-res-mult').textContent
        };
    """)

    assert out["name"] == "The Dune Sea"
    assert out["secBadge"] is True
    assert out["secText"] == "LAWLESS"
    assert out["planet"] == "TATOOINE"
    assert out["ownName"] == "Hutt Cartel"

    assert out["infCount"] == 2
    assert out["meIsHutt"] == "Hutt Cartel"
    assert out["meHasYou"] is True
    # score 75 on a 0-150 scale → 50.0% fill
    assert "width:50.0%" in out["meFillWidth"]
    assert out["meTierText"] and "FOOTHOLD" in out["meTierText"]
    # no_presence row hides its tier badge
    assert out["otherHasTier"] is False
    # threshold ticks at 50/150=33.3% and 100/150=66.7%
    assert any("left:33.3%" in s for s in out["tickLefts"])
    assert any("left:66.7%" in s for s in out["tickLefts"])

    assert out["chipCount"] == 3
    assert "good" in out["duraClass"] and "best" in out["duraClass"]
    assert "bad" in out["waterClass"]
    assert out["duraMult"] == "1.40×"


def test_region_active_contest_tug_and_countdown():
    out = run_with_dom([M3_REGION], _BLOCK_JS + """
        var root = window.M3Region.render(block);
        var contest = root.querySelector('.rgn-contest');
        var timer = root.querySelector('.rgn-contest-timer').textContent;
        var tugFill = root.querySelector('.rgn-tug-fill').getAttribute('style');
        window.M3Region.stop();
        result = {
            hasContest: !!contest,
            timer: timer,
            tugFill: tugFill
        };
    """)
    assert out["hasContest"] is True
    # 125s → 2:05
    assert "2:05" in out["timer"]
    # challenger 30 of (30+75)=105 → 28.6%
    assert "width:28.6%" in out["tugFill"]


def test_region_unaligned_is_disabled_not_hidden():
    out = run_with_dom([M3_REGION], _BLOCK_JS + """
        block.viewer_org = 'independent';
        block.influence.forEach(function(o){ o.is_viewer = false; });
        var root = window.M3Region.render(block);
        // outlook + contest still present, but flagged spectating; note shown
        var spectatingBlocks = root.querySelectorAll('.rgn-spectating');
        var note = root.querySelector('.rgn-spectate-note');
        var contest = root.querySelector('.rgn-contest');
        window.M3Region.stop();
        result = {
            spectatingCount: spectatingBlocks.length,
            hasNote: !!note,
            contestStillRendered: !!contest
        };
    """)
    # both the outlook block and the contest wrapper carry the spectating class
    assert out["spectatingCount"] >= 2
    assert out["hasNote"] is True
    assert out["contestStillRendered"] is True  # disabled, NOT hidden


# ── static wire-up guards (no node needed) ───────────────────────────
def test_region_panel_wired_into_client_html():
    html = (REPO_ROOT / "static" / "client.html").read_text(encoding="utf-8")
    for needle in (
        'id="region-panel"',
        'id="region-body"',
        '/static/spa/m3_region.js',
        "case 'region_state':",
        "function handleRegionState(",
        "function hideRegionPanel(",
        "hideRegionPanel();",   # called on room change
        "M3Region.render(",
    ):
        assert needle in html, f"region panel wiring missing from client.html: {needle!r}"


def test_region_state_pushed_by_server():
    sess = (REPO_ROOT / "server" / "session.py").read_text(encoding="utf-8")
    assert "_hud_sidebar_region" in sess, "region sidebar helper missing"
    assert '"type": "region_state"' in sess, "region_state push missing"
    assert "wilderness_region_id" in sess, "region gate (wilderness_region_id) missing"
    assert "get_region_data_block" in sess, "region block producer not called"
