"""
test_m3_craft.py — Webify Drop UI-8 (crafting panel) render contract.

Loads static/spa/m3_craft.js under jsdom and exercises M3Craft.render()
against the crafting_state shape engine/crafting.build_crafting_state
emits (protocol ledger v1_4 §1.9). Verifies: craftable-first sort + the
CRAFT button staging the REAL `craft <name>` verb (and absent on blocked
rows); the quantity-vs-quality component split (the P0.1 diagnostics)
rendered as distinct states with both numbers named; SURVEY staging the
real `survey` verb and BUY staging `+craft/buyresources <type> ` (trailing
space — quantity is the player's); the last_result banner classes; the
invented-verb-never guard; and card expansion staging nothing.

M3Craft has no timers; .stop() is convention symmetry only.
"""
from __future__ import annotations

from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
M3_CRAFT = str(REPO_ROOT / "static" / "spa" / "m3_craft.js")

_BASE_JS = """
var cmds = [];
function onCmd(c){ cmds.push(c); }
var box = document.createElement('div');
document.body.appendChild(box);
function mkComp(type, need, minq, have, haveq){
  return { type: type, quantity: need, min_quality: minq,
           have: have, have_at_quality: haveq };
}
function mkSchem(key, name, craftable, comps, extra){
  var s = { key: key, name: name, skill: 'first_aid', difficulty: 10,
            craftable: craftable, components: comps || [],
            output_type: 'consumable', t5: false };
  if (extra) Object.keys(extra).forEach(function(k){ s[k] = extra[k]; });
  return s;
}
"""


def test_craftable_first_and_craft_stages_real_verb():
    out = run_with_dom([M3_CRAFT], _BASE_JS + """
        var data = { resources: [], last_result: null, schematics: [
            mkSchem('zz_blocked', 'ZZ Blocked', false,
                    [mkComp('metal', 3, 40, 0, 0)]),
            mkSchem('medpac_basic', 'Medpac (Basic)', true,
                    [mkComp('chemical', 2, 25, 4, 4)]),
        ]};
        window.M3Craft.resetState();
        window.M3Craft.render(box, data, onCmd);
        var names = Array.prototype.map.call(
            box.querySelectorAll('.m3c-name'),
            function(n){ return n.textContent; });
        var btns = box.querySelectorAll('[data-m3c-craft]');
        btns[0].click();
        window.M3Craft.stop();
        result = {
            names: names,
            craftBtns: btns.length,
            blocked: box.querySelectorAll('.m3c-blocked').length,
            cmds: cmds
        };
    """)
    assert out["names"] == ["Medpac (Basic)", "ZZ Blocked"]   # craftable first
    assert out["craftBtns"] == 1                              # blocked: no button
    assert out["blocked"] == 1
    assert out["cmds"] == ["craft Medpac (Basic)"]            # the REAL verb


def test_component_quantity_vs_quality_states():
    out = run_with_dom([M3_CRAFT], _BASE_JS + """
        var data = { resources: [], last_result: null, schematics: [
            mkSchem('k', 'K', false, [
                mkComp('kyber_shard_minor', 1, 75, 5, 0)])]};
        window.M3Craft.resetState();
        window.M3Craft.render(box, data, onCmd);
        // expand the card; quality-blocked detail names BOTH numbers
        box.querySelector('[data-m3c-toggle]').click();
        window.M3Craft.stop();
        result = {
            // met / quality-blocked / quantity-blocked — the P0.1 split
            met:  window.M3Craft._compState(mkComp('m',2,40,5,3)),
            qual: window.M3Craft._compState(mkComp('m',2,75,5,0)),
            qty:  window.M3Craft._compState(mkComp('m',4,40,1,1)),
            detail: box.querySelector('.m3c-comp-have').textContent,
            stagedOnToggle: cmds.length
        };
    """)
    assert out["met"] == "met"
    assert out["qual"] == "quality"
    assert out["qty"] == "quantity"
    assert out["detail"] == "have 5x — only 0x at q75+"
    assert out["stagedOnToggle"] == 0          # expansion stages nothing


def test_survey_buy_stage_real_verbs_and_nothing_else():
    out = run_with_dom([M3_CRAFT], _BASE_JS + """
        var data = { schematics: [], last_result: null, resources: [
            { type: 'electronic', quantity: 3, quality: 50.0 }]};
        window.M3Craft.resetState();
        window.M3Craft.render(box, data, onCmd);
        box.querySelector('[data-m3c-survey]').click();
        box.querySelector('[data-m3c-buy]').click();
        // invented-verb-never guard: every staged command starts with a
        // verb that exists in the parser registry at HEAD.
        var ok = cmds.every(function(c){
            return c === 'survey' || c.indexOf('craft ') === 0 ||
                   c.indexOf('+craft/buyresources ') === 0;
        });
        window.M3Craft.stop();
        result = { cmds: cmds, realVerbsOnly: ok };
    """)
    assert out["cmds"] == ["survey", "+craft/buyresources electronic "]
    assert out["realVerbsOnly"] is True


def test_last_result_banner_classes_and_empty_states():
    out = run_with_dom([M3_CRAFT], _BASE_JS + """
        function banner(r){
            window.M3Craft.render(box, { schematics: [], resources: [],
                                         last_result: r }, onCmd);
            var el = box.querySelector('.m3c-result');
            return el ? el.className : 'none';
        }
        var s = banner({success:true, partial:false, fumble:false,
                        quality:71, name:'Medpac'});
        var p = banner({success:true, partial:true, fumble:false,
                        quality:40, name:'Medpac'});
        var f = banner({success:false, partial:false, fumble:true,
                        quality:0, name:'Medpac'});
        var n = banner(null);
        window.M3Craft.stop();
        result = {
            s: s, p: p, f: f, n: n,
            empty: box.querySelectorAll('.m3c-empty').length,
            cmds: cmds.length
        };
    """)
    assert out["s"] == "m3c-result success"
    assert out["p"] == "m3c-result partial"
    assert out["f"] == "m3c-result fumble"
    assert out["n"] == "none"
    assert out["empty"] == 2       # no schematics + no materials guidance
    assert out["cmds"] == 0        # empty states stage nothing
