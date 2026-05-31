"""
test_clickwalk_slugjoin.py — Drop 1 (map click-to-walk) client changes.

Pins the fix that made every adjacent room clickable on the SECTOR MAP,
including vertical/interior moves (down/up/in/out), and that resolves exit
directions via the canonical SLUG join (with NAME as a fallback) instead of
the name-only bridge that silently matched nothing.

Unlike the 4.2c adjacency tests (which inline-reimplemented the algorithm),
these run the ACTUAL production functions extracted from client.html, so the
test and the shipped code cannot drift — the divergence that hid the original
bug.

  · Static guards: the new symbols/markers exist in client.html.
  · Logic (node, no jsdom): _buildAdjacencyByRenderId resolves planar +
    vertical + reverse-edge directions by slug, falls back to name, and stays
    inert (never wrong) when neither matches.
  · DOM (jsdom, auto-skips if absent): _decorateMiniForClickToWalk tags
    compass vs vertical cells distinctly and draws a badge on vertical cells,
    while keeping them clickable (data-travel-dir present).
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

from .spa_dom_harness import run_with_dom, NODE_MODULES

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


# ── helpers ──────────────────────────────────────────────────────────

def _inline_js() -> str:
    html = CLIENT_HTML.read_text(encoding="utf-8")
    m = re.search(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html, re.I)
    assert m, "no inline <script> block found in client.html"
    return m.group(1)


def _clickwalk_block() -> str:
    """Extract the contiguous block of click-to-walk helpers as it ships:
    from `function _snapToCompass8(` through the end of `_addVertBadge`.
    Brace-matched so it is the real source, not a copy."""
    js = _inline_js()
    start = js.index("function _snapToCompass8(")
    end_anchor = js.index("function _addVertBadge(", start)
    depth = 0
    started = False
    end = None
    for k in range(end_anchor, len(js)):
        c = js[k]
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                end = k + 1
                break
    assert end, "could not brace-match end of _addVertBadge"
    return js[start:end]


def _run_node(script: str) -> dict:
    if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
        pytest.skip("node not available")
    with tempfile.NamedTemporaryFile("w", suffix=".mjs", delete=False) as f:
        f.write(script)
        path = f.name
    proc = subprocess.run(["node", path], capture_output=True, text=True)
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}\n{proc.stdout}"
    return json.loads(proc.stdout)


# ── static guards ────────────────────────────────────────────────────

def test_slug_join_and_vertical_markers_present():
    text = CLIENT_HTML.read_text(encoding="utf-8")
    for needle in ("dirBySlug", "function _normSlug", "function _isVerticalDir",
                   "function _addVertBadge", "rm-adj-vert", "data-travel-kind"):
        assert needle in text, f"expected marker missing from client.html: {needle!r}"
    # The window exposures the smoke/Playwright harness relies on stay intact.
    for needle in ("window._sw_decorateMiniForClickToWalk",
                   "window._sw_buildAdjacencyByRenderId"):
        assert needle in text, f"window exposure missing: {needle!r}"


def test_area_map_room_dict_emits_slug_in_server():
    """The server half of the join: build_area_map room dicts carry slug."""
    src = (REPO_ROOT / "engine" / "area_map.py").read_text(encoding="utf-8")
    # the rooms.append block must include a slug key
    block = src[src.index("rooms.append({"): src.index("rooms.append({") + 600]
    assert '"slug"' in block, "build_area_map rooms.append must emit a slug key"


# ── logic (real production function, no jsdom) ───────────────────────

_DRIVER = r"""
%s

const geom = {
  player:{room_id:100},
  rooms:[
    {id:100,slug:'docking_bay_94_entrance',name:'Bay 94 Ent'},
    {id:101,slug:'docking_bay_94_pit',     name:'Bay 94'},
    {id:107,slug:'mos_eisley_street_spaceport_row',name:'Spaceport Row'},
    {id:102,slug:'spaceport_customs_office',name:'Customs'},
    {id:199,slug:'hotel_slug',             name:'Hotel'}
  ],
  exits:[[100,101],[100,107],[102,100],[100,199]]
};
const areaMap = {
  current:900,
  rooms:[
    {id:900,slug:'docking_bay_94_entrance',name:'Docking Bay 94 - Entrance'},
    {id:901,slug:'docking_bay_94_pit',     name:'Docking Bay 94 - Pit Floor'},
    {id:907,slug:'mos_eisley_street_spaceport_row',name:'Mos Eisley Street - Spaceport Row'},
    {id:902,slug:'spaceport_customs_office',name:'Spaceport Customs Office'}
  ],
  edges:[
    {from:901,to:900,dir:'up'},
    {from:900,to:907,dir:'north'},
    {from:900,to:902,dir:'east'}
  ]
};
const r1 = _buildAdjacencyByRenderId(geom, areaMap);

// name fallback: pit room loses slug but its name matches the geom CELL name
const am3 = JSON.parse(JSON.stringify(areaMap));
delete am3.rooms[1].slug; am3.rooms[1].name = 'Bay 94';
const r3 = _buildAdjacencyByRenderId(geom, am3);

// neither slug nor name match -> inert
const am5 = JSON.parse(JSON.stringify(areaMap));
am5.rooms[3].slug='totally_different'; am5.rooms[3].name='Totally Different';
const r5 = _buildAdjacencyByRenderId(geom, am5);

console.log(JSON.stringify({
  r1, r3_pit:r3[101], r5_customs:(r5[102]===undefined?null:r5[102]),
  none:_buildAdjacencyByRenderId(geom,null)
}));
"""


def test_adjacency_resolves_slug_planar_vertical_and_reverse_edge():
    out = _run_node(_DRIVER % _clickwalk_block())
    # pit via reverse edge ('up'->'down'), row forward 'north', customs 'east';
    # Hotel (199) absent from area_map -> inert.
    assert out["r1"] == {"101": "down", "107": "north", "102": "east"}, out["r1"]


def test_vertical_is_reachable_not_filtered():
    out = _run_node(_DRIVER % _clickwalk_block())
    assert out["r1"].get("101") == "down", "pit (down) must be in the adjacency set"


def test_name_fallback_when_slug_missing():
    out = _run_node(_DRIVER % _clickwalk_block())
    assert out["r3_pit"] == "down", "name fallback should still resolve the pit"


def test_inert_when_no_match_and_empty_when_no_area_map():
    out = _run_node(_DRIVER % _clickwalk_block())
    assert out["r5_customs"] is None, "no slug/name match -> cell stays inert"
    assert out["none"] == {}, "no area_map -> empty adjacency, no throw"


# ── DOM decorate (jsdom; auto-skips if jsdom missing) ────────────────

def test_decorate_tags_vertical_distinctly_and_keeps_clickable(tmp_path):
    block = _clickwalk_block()
    # expose the functions on window so setup_js can call them
    module = block + "\n".join([
        "",
        "window._sw_buildAdjacencyByRenderId = _buildAdjacencyByRenderId;",
        "window._sw_decorateMiniForClickToWalk = _decorateMiniForClickToWalk;",
    ])
    mod_path = tmp_path / "clickwalk_extracted.js"
    mod_path.write_text(module, encoding="utf-8")

    setup_js = r"""
        var SVGNS='http://www.w3.org/2000/svg';
        var svg=document.createElementNS(SVGNS,'svg');
        function cell(id,x,y){
          var g=document.createElementNS(SVGNS,'g');
          g.setAttribute('data-room-id',String(id));
          var rect=document.createElementNS(SVGNS,'rect');
          rect.setAttribute('x',String(x)); rect.setAttribute('y',String(y));
          rect.setAttribute('width','20'); rect.setAttribute('height','20');
          g.appendChild(rect); svg.appendChild(g); return g;
        }
        cell(101,0,0); cell(107,40,0); cell(102,80,0); cell(199,120,0);
        var geom={player:{room_id:100},
          rooms:[{id:100,slug:'a',name:'You'},
                 {id:101,slug:'docking_bay_94_pit',name:'Bay 94'},
                 {id:107,slug:'spaceport_row',name:'Row'},
                 {id:102,slug:'customs',name:'Customs'},
                 {id:199,slug:'hotel',name:'Hotel'}],
          exits:[[100,101],[100,107],[102,100],[100,199]]};
        var areaMap={current:900,
          rooms:[{id:900,slug:'a'},{id:901,slug:'docking_bay_94_pit'},
                 {id:907,slug:'spaceport_row'},{id:902,slug:'customs'}],
          edges:[{from:900,to:901,dir:'down'},{from:900,to:907,dir:'north'},
                 {from:900,to:902,dir:'east'}]};
        window._sw_decorateMiniForClickToWalk(svg, geom, areaMap);
        function cls(id){var g=svg.querySelector('g[data-room-id="'+id+'"]');return g;}
        var pit=cls(101), row=cls(107), cust=cls(102), hotel=cls(199);
        result = {
          pit_adj:        pit.classList.contains('rm-adj'),
          pit_vert:       pit.classList.contains('rm-adj-vert'),
          pit_dir:        pit.getAttribute('data-travel-dir'),
          pit_kind:       pit.getAttribute('data-travel-kind'),
          pit_badge:      pit.querySelectorAll('g.rm-vert-badge').length,
          pit_badge_tip:  (pit.querySelector('g.rm-vert-badge title')||{}).textContent || '',
          row_adj:        row.classList.contains('rm-adj'),
          row_vert:       row.classList.contains('rm-adj-vert'),
          row_kind:       row.getAttribute('data-travel-kind'),
          cust_dir:       cust.getAttribute('data-travel-dir'),
          hotel_adj:      hotel.classList.contains('rm-adj')
        };
    """
    out = run_with_dom([mod_path], setup_js)  # skips if no jsdom

    # vertical pit: clickable, distinctly tagged, badged
    assert out["pit_adj"] is True
    assert out["pit_vert"] is True
    assert out["pit_dir"] == "down"
    assert out["pit_kind"] == "vertical"
    assert out["pit_badge"] == 1
    assert out["pit_badge_tip"].startswith("Down to")
    # compass row: clickable, NOT vertical
    assert out["row_adj"] is True
    assert out["row_vert"] is False
    assert out["row_kind"] == "compass"
    # customs resolves a compass word
    assert out["cust_dir"] == "east"
    # hotel has no area_map row -> inert
    assert out["hotel_adj"] is False
