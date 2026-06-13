"""
test_m3_shop.py — Webify Drop UI-4b (shop card) render contract.

Loads static/spa/m3_shop.js under jsdom and exercises M3Shop.render() against
the two shop_state shapes parser/shop_commands already emits (browse +
dashboard). Verifies the browse droid picker/focus, the stock rows, the BUY
action staging the REAL `buy <slot> from <shop>` verb, and the owner dashboard
(escrow + recent sales, display-only — no buy buttons). Real-verb guard:
`drop`/`give` never appear.
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_SHOP = str(REPO_ROOT / "static" / "spa" / "m3_shop.js")

_BROWSE_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var data = { mode:'browse', focused_id: 11, droids: [
  { id:11, name:'Tatooine Surplus', desc:'Used gear, cheap.', tier:'gn7',
    placed:true, escrow:0, item_count:2, inventory:[
      { slot:1, name:'Blaster Pistol', price:450, qty:1, quality:60, crafter:'' },
      { slot:2, name:'Comlink', price:25, qty:3, quality:0, crafter:'Jib' } ] },
  { id:22, name:'Dustback Droid', desc:'', tier:'gn4', placed:true, escrow:0,
    item_count:1, inventory:[
      { slot:1, name:'Power Cell', price:10, qty:5, quality:0, crafter:'' } ] }
] };
var box = document.createElement('div');
document.body.appendChild(box);
"""

_DASH_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var data = { mode:'dashboard', owner_name:'Vex', total_escrow: 1280, droids: [
  { id:11, name:'Tatooine Surplus', desc:'', tier:'gn7', placed:true,
    escrow:1280, item_count:1,
    inventory:[ { slot:1, name:'Blaster Pistol', price:450, qty:1, quality:60, crafter:'' } ],
    sales:[ { ts:'06/05 14:30', item:'Comlink', qty:2, net:48, buyer:'Rook' } ] }
] };
var box = document.createElement('div');
document.body.appendChild(box);
"""


def test_browse_renders_stock_and_real_buy_verb():
    out = run_with_dom([M3_SHOP], _BROWSE_JS + """
        window.M3Shop.render(box, data, onCmd);
        var firstName = box.querySelector('.shop-detail-name').textContent;
        var itemCount = box.querySelectorAll('.shop-item').length;

        // BUY the first stock row → real `buy <slot> from <shop name>`
        box.querySelector('.shop-item .inv-btn').click();

        // switch focus to the second droid (client-side) → re-render
        var picks = box.querySelectorAll('.shop-pick');
        var pickCount = picks.length;
        picks[1].click();
        var secondName = box.querySelector('.shop-detail-name').textContent;

        result = {
            firstName: firstName,
            itemCount: itemCount,
            pickCount: pickCount,
            secondName: secondName,
            cmds: cmds,
            joined: cmds.join(' | ')
        };
    """)
    assert out["firstName"] == "Tatooine Surplus"
    assert out["itemCount"] == 2
    assert out["pickCount"] == 2
    assert out["secondName"] == "Dustback Droid"     # focus switched client-side
    assert out["cmds"] == ["buy 1 from Tatooine Surplus"]
    assert "drop" not in out["joined"]
    assert "give" not in out["joined"]


def test_dashboard_shows_escrow_and_sales_display_only():
    out = run_with_dom([M3_SHOP], _DASH_JS + """
        window.M3Shop.render(box, data, onCmd);
        var escrowText = box.querySelector('.shop-dash-escrow').textContent;
        var droidName = box.querySelector('.shop-detail-name').textContent;
        var sale = box.querySelector('.shop-sale');
        result = {
            escrowDigits: escrowText.replace(/[^0-9]/g, ''),
            escrowHasCr: escrowText.indexOf('cr') !== -1,
            droidName: droidName,
            placedTag: !!box.querySelector('.shop-tag-placed'),
            saleBuyer: sale ? box.querySelector('.shop-sale-buyer').textContent : '',
            saleNetDigits: sale ? box.querySelector('.shop-sale-net').textContent.replace(/[^0-9]/g,'') : '',
            buyButtons: box.querySelectorAll('.inv-btn').length
        };
    """)
    assert out["escrowDigits"] == "1280"
    assert out["escrowHasCr"] is True
    assert out["droidName"] == "Tatooine Surplus"
    assert out["placedTag"] is True
    assert out["saleBuyer"] == "Rook"
    assert out["saleNetDigits"] == "48"
    assert out["buyButtons"] == 0           # dashboard is display-only (no BUY)


_VENDOR_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var data = {
    mode: 'vendor',
    vendor_kind: 'commissary',
    faction_code: 'republic',
    rank_level: 0,
    balance: 200,
    items: [
        { key:'republic_uniform', name:'Republic Service Uniform', slot:'armor',
          cost:150, min_rank:0, desc:'Off-white tunic.', mark:'buy' },
        { key:'dc17_pistol',      name:'DC-17 Hand Blaster',       slot:'weapon',
          cost:500, min_rank:0, desc:'Republic sidearm.',  mark:'short' },
        { key:'dc15_blaster_rifle', name:'DC-15A Blaster Rifle',   slot:'weapon',
          cost:1200, min_rank:1, desc:'Clone rifle.',      mark:'rank' }
    ]
};
var box = document.createElement('div');
document.body.appendChild(box);
"""


def test_vendor_mode_renders_commissary_panel():
    """Vendor mode renders: title, balance, item rows; BUY only for mark=buy;
    rank-locked row has no BUY button; short row has no BUY button;
    staged action is '+commissary buy <key>' (not bare 'buy ...'); no sell verb."""
    out = run_with_dom([M3_SHOP], _VENDOR_JS + """
        window.M3Shop.render(box, data, onCmd);

        // Title contains faction name
        var titleText = box.querySelector('.shop-dash-title') ?
            box.querySelector('.shop-dash-title').textContent : '';

        // Balance appears somewhere
        var balanceText = box.querySelector('.shop-dash-escrow') ?
            box.querySelector('.shop-dash-escrow').textContent : '';

        // Count item rows
        var itemCount = box.querySelectorAll('.shop-item').length;

        // BUY the affordable row (republic_uniform)
        var allBtns = box.querySelectorAll('.shop-item .inv-btn');
        var buyBtnCount = allBtns.length;
        if (allBtns.length > 0) allBtns[0].click();

        // Rank-locked row must have no button — check text for 'rank'.
        // The fixture has TWO unplaced tags (a 'short' row AND a 'rank'
        // row); querySelector returns the first (short), so collect ALL
        // tag texts and let the assertion look for the rank one.
        var rankTags = box.querySelectorAll('.shop-tag-unplaced');
        var rankTagText = '';
        for (var i = 0; i < rankTags.length; i++){
            rankTagText += rankTags[i].textContent + ' | ';
        }

        result = {
            titleText: titleText,
            balanceText: balanceText,
            itemCount: itemCount,
            buyBtnCount: buyBtnCount,
            cmds: cmds,
            joined: cmds.join(' | '),
            rankTagText: rankTagText
        };
    """)
    # Panel header rendered
    assert "commissary" in out["titleText"].lower() or "republic" in out["titleText"].lower()
    # Balance shown
    assert "200" in out["balanceText"] or "cr" in out["balanceText"]
    # All 3 items rendered
    assert out["itemCount"] == 3
    # Only the mark:'buy' item gets a button (1 of 3)
    assert out["buyBtnCount"] == 1
    # The staged command is the commissary verb, not the bare shop buy verb
    assert out["cmds"] == ["+commissary buy republic_uniform"]
    assert "buy " not in out["joined"].replace("+commissary buy ", "")
    # No sell/estate verbs
    assert "sell" not in out["joined"]
    assert "drop" not in out["joined"]
    assert "give" not in out["joined"]
    # Rank-locked row shows rank indicator
    assert "rank" in out["rankTagText"].lower()


def test_vendor_mode_rank_locked_no_buy_button():
    """Rank-locked items (mark:'rank') never have a BUY button."""
    out = run_with_dom([M3_SHOP], """
        var box = document.createElement('div');
        document.body.appendChild(box);
        var data = {
            mode: 'vendor', vendor_kind: 'commissary',
            faction_code: 'republic', rank_level: 0, balance: 50000,
            items: [
                { key:'dc15_blaster_rifle', name:'DC-15A Blaster Rifle',
                  slot:'weapon', cost:1200, min_rank:1, desc:'Clone rifle.',
                  mark:'rank' }
            ]
        };
        window.M3Shop.render(box, data, function(){});
        result = {
            buyBtns: box.querySelectorAll('.inv-btn').length,
            rankTag: !!box.querySelector('.shop-tag-unplaced')
        };
    """)
    assert out["buyBtns"] == 0
    assert out["rankTag"] is True


def test_vendor_mode_empty_commissary():
    """Empty items list (faction with no commissary) shows empty-note."""
    out = run_with_dom([M3_SHOP], """
        var box = document.createElement('div');
        document.body.appendChild(box);
        var data = {
            mode: 'vendor', vendor_kind: 'commissary',
            faction_code: 'jedi_order', rank_level: 5, balance: 99999,
            items: []
        };
        window.M3Shop.render(box, data, function(){});
        result = {
            note: !!box.querySelector('.inv-empty-note'),
            buyBtns: box.querySelectorAll('.inv-btn').length
        };
    """)
    assert out["note"] is True
    assert out["buyBtns"] == 0


def test_browse_empty_room_note():
    out = run_with_dom([M3_SHOP], """
        var box = document.createElement('div');
        document.body.appendChild(box);
        window.M3Shop.render(box, { mode:'browse', focused_id:null, droids:[] }, function(){});
        result = { note: !!box.querySelector('.inv-empty-note'),
                   txt: box.querySelector('.inv-empty-note').textContent };
    """)
    assert out["note"] is True
    assert "No vendor droids" in out["txt"]
