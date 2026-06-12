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
