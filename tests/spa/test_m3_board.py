"""
test_m3_board.py — Webify Drop UI-5 (bounty board) render contract.

Loads static/spa/m3_board.js under jsdom and exercises M3Board.render()
against the board_state shape engine/bounty_board.build_board_state
emits. Verifies: claimed-first sort (then reward desc), the CLAIMED
badge + TRACK staging the REAL `+bounty/track` verb, ACCEPT staging the
REAL `+bounty/claim <id>` verb (and ACCEPT suppressed while the viewer
holds a claim), tier filtering, the urgent countdown class under 30
minutes, the CHAIN tag on chain_bounty_id, and details expansion.

Every test calls M3Board.stop() before returning so the 1s countdown
interval drains and Node exits (same convention as M3Region).
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_BOARD = str(REPO_ROOT / "static" / "spa" / "m3_board.js")

_BASE_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var box = document.createElement('div');
document.body.appendChild(box);
function mkContract(id, tier, reward, extra){
  var c = {
    id: id, tier: tier, target_name: 'T-' + id,
    target_species: 'Human', target_archetype: 'thug',
    crime_description: 'wanted for testing', posting_org: 'Port Authority',
    tip: 'Seen near the cantina.', reward: reward, reward_alive_bonus: 0,
    target_npc_id: 1, target_room_id: 2, status: 'posted',
    claimed_by: null, chain_bounty_id: '', expires_in_secs: 7200
  };
  if (extra) Object.keys(extra).forEach(function(k){ c[k] = extra[k]; });
  return c;
}
"""


def test_render_sorts_and_accept_stages_real_claim_verb():
    out = run_with_dom([M3_BOARD], _BASE_JS + """
        var data = { claimed_id: null, contracts: [
            mkContract('b-low',  'extra',    200),
            mkContract('b-high', 'superior', 9000),
            mkContract('b-mid',  'novice',   900,
                       { chain_bounty_id: 'tutorial_bhg_tarko_vinn' })
        ] };
        window.M3Board.resetState();
        window.M3Board.render(box, data, onCmd);

        var names = Array.prototype.map.call(
            box.querySelectorAll('.m3b-name'),
            function(n){ return n.textContent; });
        var chainTags = box.querySelectorAll('.m3b-badge.chain').length;
        var openCount = box.querySelector('.m3b-open-count').textContent;

        // ACCEPT on the top (highest-reward) card → +bounty/claim <id>
        box.querySelector('.m3b-act.accept').click();

        window.M3Board.stop();
        result = {
            names: names,
            chainTags: chainTags,
            openCount: openCount,
            cmds: cmds,
            joined: cmds.join(' | ')
        };
    """)
    assert out["names"] == ["T-b-high", "T-b-mid", "T-b-low"]   # reward desc
    assert out["chainTags"] == 1
    assert "3 open contracts" in out["openCount"]
    assert out["cmds"] == ["+bounty/claim b-high"]
    # Real-verb guard: no invented verbs anywhere in staged output.
    assert "abandon" not in out["joined"]
    assert "breakfree" not in out["joined"]


def test_claimed_pins_first_with_track_and_no_accepts():
    out = run_with_dom([M3_BOARD], _BASE_JS + """
        var data = { claimed_id: 'b-mine', contracts: [
            mkContract('b-rich', 'superior', 9000),
            mkContract('b-mine', 'novice',   900,
                       { status: 'claimed', claimed_by: '7',
                         expires_in_secs: 3000 })
        ] };
        window.M3Board.resetState();
        window.M3Board.render(box, data, onCmd);

        var names = Array.prototype.map.call(
            box.querySelectorAll('.m3b-name'),
            function(n){ return n.textContent; });
        var claimedBadges = box.querySelectorAll('.m3b-badge.claimed').length;
        var acceptBtns = box.querySelectorAll('.m3b-act.accept').length;

        // TRACK on the claimed card → +bounty/track (no id)
        box.querySelector('.m3b-act.primary').click();

        window.M3Board.stop();
        result = {
            names: names,
            claimedBadges: claimedBadges,
            acceptBtns: acceptBtns,
            cmds: cmds
        };
    """)
    # Claimed pinned first despite lower reward.
    assert out["names"] == ["T-b-mine", "T-b-rich"]
    assert out["claimedBadges"] == 1
    # One claim at a time: ACCEPT suppressed everywhere while claimed.
    assert out["acceptBtns"] == 0
    assert out["cmds"] == ["+bounty/track"]


def test_tier_filter_and_details_expand():
    out = run_with_dom([M3_BOARD], _BASE_JS + """
        var data = { claimed_id: null, contracts: [
            mkContract('b-vet', 'veteran', 2500),
            mkContract('b-ext', 'extra',   150)
        ] };
        window.M3Board.resetState();
        window.M3Board.render(box, data, onCmd);
        var before = box.querySelectorAll('.m3b-card').length;

        // Filter to veteran only.
        var chips = box.querySelectorAll('.m3b-chip');
        var vetChip = null;
        for (var i = 0; i < chips.length; i++){
            if (chips[i].getAttribute('data-filter') === 'veteran') vetChip = chips[i];
        }
        vetChip.click();
        var after = box.querySelectorAll('.m3b-card').length;
        var shownName = box.querySelector('.m3b-name').textContent;

        // Expand details on the remaining card.
        var detailsBtn = null;
        var acts = box.querySelectorAll('.m3b-act');
        for (var j = 0; j < acts.length; j++){
            if (acts[j].getAttribute('data-act') === 'details') detailsBtn = acts[j];
        }
        detailsBtn.click();
        var detailText = box.querySelector('.m3b-details').textContent;
        var hasTip = detailText.indexOf('Seen near the cantina.') !== -1;
        var hasOrg = detailText.indexOf('Port Authority') !== -1;
        var hasId  = detailText.indexOf('b-vet') !== -1;

        window.M3Board.stop();
        result = { before: before, after: after, shownName: shownName,
                   hasTip: hasTip, hasOrg: hasOrg, hasId: hasId,
                   cmds: cmds };
    """)
    assert out["before"] == 2
    assert out["after"] == 1
    assert out["shownName"] == "T-b-vet"
    assert out["hasTip"] and out["hasOrg"] and out["hasId"]
    assert out["cmds"] == []          # filter/details stage nothing


def test_countdown_urgent_class_and_empty_state():
    out = run_with_dom([M3_BOARD], _BASE_JS + """
        var data = { claimed_id: null, contracts: [
            mkContract('b-soon', 'average', 500, { expires_in_secs: 900 }),
            mkContract('b-late', 'average', 400, { expires_in_secs: 7200 }),
            mkContract('b-none', 'average', 300, { expires_in_secs: null })
        ] };
        window.M3Board.resetState();
        window.M3Board.render(box, data, onCmd);

        var urgent = box.querySelectorAll('.m3b-count.urgent').length;
        var counts = box.querySelectorAll('.m3b-count').length;

        // Empty board → empty-state copy, no cards.
        window.M3Board.render(box, { claimed_id: null, contracts: [] }, onCmd);
        var cards = box.querySelectorAll('.m3b-card').length;
        var emptyText = box.querySelector('.m3b-empty').textContent;

        window.M3Board.stop();
        result = { urgent: urgent, counts: counts, cards: cards,
                   emptyText: emptyText };
    """)
    assert out["urgent"] == 1          # only the 15-minute contract
    assert out["counts"] == 2          # null expiry renders no countdown
    assert out["cards"] == 0
    assert "No active bounties" in out["emptyText"]
