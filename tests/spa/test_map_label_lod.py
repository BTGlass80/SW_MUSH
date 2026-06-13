"""
test_map_label_lod.py — Drop 2 (D): zoom level-of-detail room labels.

Reported bug: zooming into the SECTOR MAP modal showed no more room info —
only the current room + walkable neighbours were ever labelled, at any zoom.
The modal zoom shrinks the SVG viewBox, so world-unit labels just *grew*; the
label SET never expanded.

Fix:
  · _labelRoomsForNavigation(svg, geom, opts) is now zoom-aware. opts.zoom is
    the zoom FACTOR (1 = fit), opts.viewScale the viewBox-shrink ratio. Labels
    are revealed by BFS depth from the player: depth ≤1 always, ≤2 once zoomed
    in, and ALL named rooms past the inner threshold. Font is × viewScale so a
    label is a roughly constant on-screen size (reveals names, not bigger ones).
  · _installModalZoomPan(svg, onZoom) fires a debounced callback with the
    viewBox-shrink ratio when the zoom level changes (pan excluded).
  · _renderModalViaM3 wires the callback to re-label at the new density.

The jsdom test runs the ACTUAL extracted _labelRoomsForNavigation (brace-
matched from client.html), not a re-implementation.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from .spa_dom_harness import run_with_dom

REPO_ROOT   = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


def _inline_js() -> str:
    html = CLIENT_HTML.read_text(encoding="utf-8")
    m = re.search(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html, re.I)
    assert m, "no inline <script> block found in client.html"
    return m.group(1)


def _extract_fn(name: str) -> str:
    js = _inline_js()
    start = js.index("function " + name + "(")
    depth = 0
    started = False
    for k in range(start, len(js)):
        c = js[k]
        if c == "{":
            depth += 1; started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return js[start:k + 1]
    raise AssertionError("could not brace-match " + name)


# ── static guards ────────────────────────────────────────────────────

def test_label_fn_is_zoom_aware():
    fn = _extract_fn("_labelRoomsForNavigation")
    assert "opts" in fn and "viewScale" in fn and "maxDepth" in fn, (
        "_labelRoomsForNavigation must take zoom/viewScale opts and a depth gate"
    )
    # BFS over the exit graph (not just direct neighbours)
    assert "depthByRid" in fn, "label density must be BFS-depth driven"


def test_zoom_pan_installer_has_onzoom_callback():
    text = CLIENT_HTML.read_text(encoding="utf-8")
    zp_start = text.index("function _installModalZoomPan(")
    zp = text[zp_start: zp_start + 2600]
    assert "onZoom" in zp, "_installModalZoomPan must accept an onZoom callback"
    assert "_zoomRelabelTimer" in zp, "zoom relabel should be debounced"
    # the modal render must wire the callback to re-label
    m3_start = text.index("function _renderModalViaM3(")
    m3 = text[m3_start: m3_start + 4000]
    assert re.search(r"_installModalZoomPan\(\s*bodySvg\s*,\s*function", m3), (
        "_renderModalViaM3 must pass a zoom callback to _installModalZoomPan"
    )
    assert "_labelRoomsForNavigation(bodySvg, geom, { zoom:" in m3, (
        "the zoom callback must re-label at the new density"
    )


# ── jsdom: run the real label fn at increasing zoom ──────────────────

def test_zoom_reveals_more_rooms(tmp_path):
    fn = _extract_fn("_labelRoomsForNavigation")
    mod = fn + "\nwindow._sw_labelRoomsForNavigation = _labelRoomsForNavigation;\n"
    mod_path = tmp_path / "label_fn.js"
    mod_path.write_text(mod, encoding="utf-8")

    setup_js = r"""
        var SVGNS='http://www.w3.org/2000/svg';
        function buildSvg(ids){
          var svg=document.createElementNS(SVGNS,'svg');
          ids.forEach(function(id){
            var g=document.createElementNS(SVGNS,'g');
            g.setAttribute('data-room-id',String(id));
            var rect=document.createElementNS(SVGNS,'rect');
            rect.setAttribute('x','0');rect.setAttribute('y','0');
            rect.setAttribute('width','20');rect.setAttribute('height','20');
            g.appendChild(rect); svg.appendChild(g);
          });
          return svg;
        }
        // chain 100-101-102-103 ; 100-107 ; 200 disconnected
        var geom={player:{room_id:100},
          rooms:[100,101,102,103,107,200].map(function(id){return {id:id,name:'Room '+id};}),
          exits:[[100,101],[101,102],[102,103],[100,107]]};
        function labelled(svg){
          var out=[];
          var ts=svg.querySelectorAll('text.rm-name');
          for(var i=0;i<ts.length;i++){out.push(ts[i].parentNode.getAttribute('data-room-id'));}
          return out.sort();
        }
        function fillOf(svg,id){
          var ts=svg.querySelectorAll('text.rm-name');
          for(var i=0;i<ts.length;i++){ if(ts[i].parentNode.getAttribute('data-room-id')===String(id)) return ts[i].getAttribute('fill'); }
          return null;
        }
        function fsOf(svg,id){
          var ts=svg.querySelectorAll('text.rm-name');
          for(var i=0;i<ts.length;i++){ if(ts[i].parentNode.getAttribute('data-room-id')===String(id)) return parseFloat(ts[i].getAttribute('font-size')); }
          return null;
        }

        var L = window._sw_labelRoomsForNavigation;

        var s1=buildSvg([100,101,102,103,107,200]); L(s1,geom);           // default = fit
        var s2=buildSvg([100,101,102,103,107,200]); L(s2,geom,{zoom:1.8,viewScale:0.55});
        var s3=buildSvg([100,101,102,103,107,200]); L(s3,geom,{zoom:2.5,viewScale:0.4});
        var farLabels = labelled(s3);     // snapshot BEFORE the idempotency re-run
        L(s3,geom,{zoom:1,viewScale:1});  // re-run at fit zoom to test idempotency

        result = {
          fit:        labelled(s1),
          fit_titles: s1.querySelectorAll('title.rm-title').length,
          fit_cur_fill: fillOf(s1,100),
          fit_adj_fill: fillOf(s1,101),
          mid:        labelled(s2),
          mid_far_fill: fillOf(s2,102),
          mid_fs_cur: fsOf(s2,100),
          far:        farLabels,         // far-zoom set, captured pre-collapse
          reidempotent: labelled(s3)     // same svg AFTER the zoom:1 re-run
        };
    """
    out = run_with_dom([mod_path], setup_js)  # auto-skips without jsdom

    # fit: current + adjacent only
    assert out["fit"] == ["100", "101", "107"], out["fit"]
    assert out["fit_titles"] == 6, "hover title on every named cell at all zooms"
    assert out["fit_cur_fill"] == "#ffcf7a"   # current amber
    assert out["fit_adj_fill"] == "#bfe8ef"   # adjacent cyan
    # mid zoom: + depth-2 (102), still excludes depth-3 (103) + disconnected (200)
    assert out["mid"] == ["100", "101", "102", "107"], out["mid"]
    assert out["mid_far_fill"] == "#8fb3ba"   # far = dimmer
    # font scaled by viewScale: 20-unit cell → base 10 → 10*0.55 = 5.5
    assert abs(out["mid_fs_cur"] - (10 * 0.55)) < 0.01, out["mid_fs_cur"]
    # far zoom: ALL named rooms (incl depth-3 and disconnected)
    assert out["far"] == ["100", "101", "102", "103", "107", "200"], out["far"]
    # idempotent: re-running at fit zoom collapsed the set back to 3
    assert out["reidempotent"] == ["100", "101", "107"], out["reidempotent"]
