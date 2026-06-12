"""
test_m3_inventory.py — Webify Drop UI-4a (inventory panel) render contract.

Loads static/spa/m3_inventory.js under jsdom and exercises M3Inventory.render()
against a representative inventory_state block (engine/items.build_inventory_state).
Verifies the equipped cards + carried rows, the quality pips / condition bar,
the D6-pip delta preview, and — critically — that the only staged commands are
verbs that EXIST at HEAD (equip/wear/unequip/remove armor/look) and that
`drop`/`give` are NEVER offered.
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_INV = str(REPO_ROOT / "static" / "spa" / "m3_inventory.js")

_DATA_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var data = {
  equipped: {
    weapon: { key:'blaster_pistol', name:'Blaster Pistol', slot:'weapon',
      quality:50, condition:80, max_condition:100, crafter:'', experiment_count:0,
      stats:{damage:'4D', range:'10/30/120'}, value:500 },
    armor: { key:'padded_armor', name:'Padded Armor', slot:'armor',
      quality:60, condition:40, max_condition:100, crafter:'Tey', experiment_count:1,
      stats:{energy:'1D', physical:'1D+1'}, value:250 }
  },
  carried: [
    { key:'blaster_rifle', name:'Blaster Rifle', slot:'weapon', quality:70,
      condition:90, max_condition:100, crafter:'Mott', experiment_count:0,
      stats:{damage:'5D', range:'30/100/300'}, value:1000, quantity:1 },
    { key:'combat_jumpsuit', name:'Combat Jumpsuit', slot:'armor', quality:50,
      condition:100, max_condition:100, crafter:'', experiment_count:0,
      stats:{energy:'1D+2', physical:'2D'}, value:400, quantity:1 },
    { key:'quest_holocron', name:'Cracked Holocron', slot:'misc', quality:50,
      condition:100, max_condition:100, crafter:'', experiment_count:0,
      stats:{}, value:0, quantity:2 }
  ]
};
var box = document.createElement('div');
document.body.appendChild(box);
"""


def test_structure_and_real_verbs_only():
    out = run_with_dom([M3_INV], _DATA_JS + """
        window.M3Inventory.render(box, data, onCmd);

        var rifle = box.querySelector('.inv-row[data-key="blaster_rifle"]');
        var suit  = box.querySelector('.inv-row[data-key="combat_jumpsuit"]');
        var holo  = box.querySelector('.inv-row[data-key="quest_holocron"]');

        // weapon row: EQUIP (primary) + LOOK (ghost)
        rifle.querySelector('.inv-btn:not(.ghost)').click();   // equip Blaster Rifle
        rifle.querySelector('.inv-btn.ghost').click();         // look Blaster Rifle
        // armor row: WEAR (primary)
        suit.querySelector('.inv-btn:not(.ghost)').click();    // wear Combat Jumpsuit
        // equipped slot cards: UNEQUIP (weapon) + REMOVE (armor)
        box.querySelector('.inv-card[data-slot="weapon"] .inv-btn.ghost').click(); // unequip
        box.querySelector('.inv-card[data-slot="armor"] .inv-btn.ghost').click();  // remove armor

        var allCmdsJoined = cmds.join(' | ');

        result = {
            wName: box.querySelector('.inv-card[data-slot="weapon"] .inv-card-name').textContent,
            aName: box.querySelector('.inv-card[data-slot="armor"] .inv-card-name').textContent,
            armorMod: !!box.querySelector('.inv-card[data-slot="armor"] .inv-mod'),
            carriedCount: box.querySelectorAll('.inv-row').length,
            holoBtns: holo.querySelectorAll('.inv-btn').length,
            rifleBtns: rifle.querySelectorAll('.inv-btn').length,
            cmds: cmds,
            hasDrop: allCmdsJoined.indexOf('drop') !== -1,
            hasGive: allCmdsJoined.indexOf('give') !== -1,
            // quality 70 -> round(3.5)=4 pips on; condition 40% -> warn tier
            rifleQualityOn: rifle.querySelectorAll('.inv-pip.on').length,
            armorCondWarn: !!box.querySelector('.inv-card[data-slot="armor"] .inv-cond.warn')
        };
    """)
    assert out["wName"] == "Blaster Pistol"
    assert out["aName"] == "Padded Armor"
    assert out["armorMod"] is True            # experiment_count 1 → [Modified ×1]
    assert out["carriedCount"] == 3
    assert out["holoBtns"] == 1               # misc item: LOOK only, no equip/wear
    assert out["rifleBtns"] == 2              # weapon: EQUIP + LOOK
    # exact real verbs, in click order
    assert out["cmds"] == [
        "equip Blaster Rifle", "look Blaster Rifle", "wear Combat Jumpsuit",
        "unequip", "remove armor",
    ]
    assert out["hasDrop"] is False            # the phantom verbs are never offered
    assert out["hasGive"] is False
    assert out["rifleQualityOn"] == 4
    assert out["armorCondWarn"] is True


def test_delta_pip_comparison():
    out = run_with_dom([M3_INV], _DATA_JS + """
        window.M3Inventory.render(box, data, onCmd);
        // select the carried rifle (row body click) → re-render with delta footer
        box.querySelector('.inv-row[data-key="blaster_rifle"]').click();

        var rows = box.querySelectorAll('.inv-delta-row');
        var dmgRow = null, rngRow = null;
        Array.prototype.forEach.call(rows, function(r){
            var ax = r.querySelector('.inv-delta-axis').textContent;
            if (ax === 'DMG') dmgRow = r;
            if (ax === 'RNG') rngRow = r;
        });
        result = {
            hasTitle: !!box.querySelector('.inv-delta-title'),
            dmgUp: dmgRow ? (dmgRow.className.indexOf('up') !== -1) : false,
            dmgMark: dmgRow && dmgRow.querySelector('.inv-delta-mark')
                ? dmgRow.querySelector('.inv-delta-mark').textContent : '',
            dmgFrom: dmgRow ? dmgRow.querySelector('.inv-delta-from').textContent : '',
            dmgTo: dmgRow ? dmgRow.querySelector('.inv-delta-to').textContent : '',
            // range strings are not absolute dice → no arrow (honest, not misleading)
            rngHasMark: rngRow ? !!rngRow.querySelector('.inv-delta-mark') : true
        };
    """)
    assert out["hasTitle"] is True
    assert out["dmgFrom"] == "4D"             # equipped pistol
    assert out["dmgTo"] == "5D"               # carried rifle
    assert out["dmgUp"] is True               # 15 pips > 12 pips
    assert out["dmgMark"] == "\u25b2"         # ▲
    assert out["rngHasMark"] is False         # "10/30/120" not pip-comparable


def test_pips_helper_handles_relative_bases():
    out = run_with_dom([M3_INV], """
        result = {
            d4: window.M3Inventory.pipsOf('4D'),
            d5p2: window.M3Inventory.pipsOf('5D+2'),
            d1p2: window.M3Inventory.pipsOf('1D+2'),
            flat: window.M3Inventory.pipsOf('7'),
            strRel: window.M3Inventory.pipsOf('STR+1D'),
            nullv: window.M3Inventory.pipsOf(null)
        };
    """)
    assert out["d4"] == 12
    assert out["d5p2"] == 17
    assert out["d1p2"] == 5
    assert out["flat"] == 7
    assert out["strRel"] is None              # relative base → not comparable
    assert out["nullv"] is None
