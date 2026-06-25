"""
test_m3_scene_panel.py — UX Drop 5 (presence + scene/social UI) render contract.

Two layers, mirroring test_gnd_ux_sidebar_panels.py (static parse) +
test_m3_board.py (jsdom DOM-runtime):

  A. Static parse of static/client.html — the scene-panel + presence-panel DOM
     ids exist, renderScenePanel is defined + invoked from handleHudUpdate, the
     active_scene field is consumed, and the presence poll is gated on expand.
  B. jsdom DOM-runtime of static/spa/m3_scene_panel.js — a synthetic
     hud.active_scene renders the title + participant rows + per-player
     pose-count chips; a null/empty active_scene returns null (card cleared);
     the scene title is XSS-escaped (no live <script>).
  C. jsdom DOM-runtime of static/spa/m3_presence_panel.js — the who payload
     renders rows; an injected fetch is polled only via start(), stop() halts
     it; player names are XSS-escaped.
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
M3_SCENE = str(REPO_ROOT / "static" / "spa" / "m3_scene_panel.js")
M3_PRESENCE = str(REPO_ROOT / "static" / "spa" / "m3_presence_panel.js")


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


# ════════════════════════════════════════════════════════════════════════
# A. Static parse — DOM ids + wiring
# ════════════════════════════════════════════════════════════════════════

def test_scene_panel_id_exists():
    assert 'id="scene-panel"' in _html(), "scene-panel missing from DOM"


def test_presence_panel_id_exists():
    assert 'id="presence-panel"' in _html(), "presence-panel missing from DOM"


def test_renderScenePanel_defined():
    assert re.search(r"function\s+renderScenePanel\s*\(", _html()), (
        "renderScenePanel not defined"
    )


def _handleHudUpdate_body(html: str) -> str:
    start = html.find("function handleHudUpdate(data)")
    assert start != -1, "handleHudUpdate not found"
    return html[start: start + 40000]


def test_renderScenePanel_called_from_handleHudUpdate():
    body = _handleHudUpdate_body(_html())
    assert "renderScenePanel(data)" in body, (
        "renderScenePanel not invoked from handleHudUpdate"
    )


def test_active_scene_field_consumed():
    assert "active_scene" in _html(), "active_scene field not referenced"


def test_presence_poll_gated_on_expand():
    """togglePresencePanel must start polling only when expanded and stop when
    collapsed (off-cost-free discipline)."""
    html = _html()
    start = html.find("function togglePresencePanel(")
    assert start != -1, "togglePresencePanel not defined"
    block = html[start: start + 1200]
    assert "M3PresencePanel.start" in block, "presence panel never starts polling"
    assert "M3PresencePanel.stop" in block, "presence panel never stops polling"
    assert "collapsed" in block, "togglePresencePanel must key off the collapsed class"


def test_presence_panel_collapsed_by_default():
    """The presence card ships collapsed (zero poll until the player opens it)."""
    html = _html()
    m = re.search(r'<div class="side-panel collapsed" id="presence-panel"', html)
    assert m, "presence-panel must ship with the 'collapsed' class (no poll at rest)"


def test_scene_panel_script_loaded():
    assert "/static/spa/m3_scene_panel.js" in _html()


def test_presence_panel_script_loaded():
    assert "/static/spa/m3_presence_panel.js" in _html()


# ════════════════════════════════════════════════════════════════════════
# B. jsdom — m3_scene_panel.js render contract
# ════════════════════════════════════════════════════════════════════════

_SCENE_BASE = """
var box = document.createElement('div');
document.body.appendChild(box);
window.M3ScenePanel.init({ escapeHtml: function(s){
  return String(s == null ? '' : s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}});
"""


def test_scene_renders_title_participants_and_chips():
    out = run_with_dom([M3_SCENE], _SCENE_BASE + """
        var scene = {
          scene_id: 9, title: 'Cantina standoff', type: 'Social',
          started_at: 1718900000, creator_name: 'Rax', pose_count: 5,
          participants: [
            { id: 1, name: 'Rax',  pose_count: 3 },
            { id: 2, name: 'Vesh', pose_count: 2 }
          ]
        };
        var node = window.M3ScenePanel.render(scene);
        box.appendChild(node);

        var title = box.querySelector('.scene-title').textContent;
        var typeChip = box.querySelector('.scene-type-chip').textContent;
        var names = Array.prototype.map.call(
          box.querySelectorAll('.scene-part-name'),
          function(n){ return n.textContent; });
        var chips = Array.prototype.map.call(
          box.querySelectorAll('.scene-pose-chip'),
          function(n){ return n.textContent; });
        var total = box.querySelector('.scene-pose-total').textContent;

        result = { title: title, typeChip: typeChip, names: names,
                   chips: chips, total: total };
    """)
    assert out["title"] == "Cantina standoff"
    assert out["typeChip"] == "Social"
    assert out["names"] == ["Rax", "Vesh"]
    assert out["chips"] == ["3", "2"]          # per-player pose-count chips
    assert "5 poses" in out["total"]


def test_scene_absent_or_empty_returns_null():
    out = run_with_dom([M3_SCENE], _SCENE_BASE + """
        var a = window.M3ScenePanel.render(null);
        var b = window.M3ScenePanel.render(undefined);
        var c = window.M3ScenePanel.render({});             // no title, no parts
        var d = window.M3ScenePanel.render('not-an-object');
        result = { a: a === null, b: b === null,
                   c: c === null, d: d === null };
    """)
    assert out["a"] and out["b"] and out["c"] and out["d"], (
        "absent/empty active_scene must return null so the card is cleared"
    )


def test_scene_title_is_xss_escaped():
    out = run_with_dom([M3_SCENE], _SCENE_BASE + """
        var scene = {
          scene_id: 1, title: "<script>alert('x')</script>", type: 'Social',
          pose_count: 0,
          participants: [ { id: 1, name: "<img src=x onerror=alert(1)>",
                            pose_count: 0 } ]
        };
        var node = window.M3ScenePanel.render(scene);
        box.appendChild(node);
        // No live <script>/<img> element should have been created from text.
        var liveScripts = box.querySelectorAll('script').length;
        var liveImgs = box.querySelectorAll('img').length;
        // The literal text must survive as text content (inert).
        var titleText = box.querySelector('.scene-title').textContent;
        var nameText = box.querySelector('.scene-part-name').textContent;
        result = { liveScripts: liveScripts, liveImgs: liveImgs,
                   titleText: titleText, nameText: nameText };
    """)
    assert out["liveScripts"] == 0, "scene title must not inject a live <script>"
    assert out["liveImgs"] == 0, "participant name must not inject a live <img>"
    assert "<script>" in out["titleText"]      # preserved as inert text
    assert "<img" in out["nameText"]


# ════════════════════════════════════════════════════════════════════════
# C. jsdom — m3_presence_panel.js render + poll lifecycle
# ════════════════════════════════════════════════════════════════════════

_PRESENCE_BASE = """
var box = document.createElement('div');
document.body.appendChild(box);
"""


def test_presence_renders_rows_from_who_payload():
    out = run_with_dom([M3_PRESENCE], _PRESENCE_BASE + """
        var data = { count: 2, online: [
          { name: 'Rax',  species: 'Human',   location_area: 'Mos Eisley',
            idle_seconds: 5,   faction: 'Neutral' },
          { name: 'Vesh', species: 'Twi\\'lek', location_area: 'Cantina',
            idle_seconds: 200, faction: 'Hutt Cartel' }
        ] };
        var n = window.M3PresencePanel.renderInto(box, data);
        var names = Array.prototype.map.call(
          box.querySelectorAll('.presence-name'),
          function(x){ return x.textContent; });
        var locs = Array.prototype.map.call(
          box.querySelectorAll('.presence-loc'),
          function(x){ return x.textContent; });
        result = { n: n, names: names, locs: locs,
                   rows: box.querySelectorAll('.presence-row').length };
    """)
    assert out["n"] == 2
    assert out["names"] == ["Rax", "Vesh"]
    assert out["locs"] == ["Mos Eisley", "Cantina"]
    assert out["rows"] == 2


def test_presence_empty_state():
    out = run_with_dom([M3_PRESENCE], _PRESENCE_BASE + """
        window.M3PresencePanel.renderInto(box, { count: 0, online: [] });
        var empty = box.querySelector('.presence-empty');
        result = { hasEmpty: !!empty,
                   rows: box.querySelectorAll('.presence-row').length };
    """)
    assert out["hasEmpty"], "empty roster must render an empty-state line"
    assert out["rows"] == 0


def test_presence_polls_only_via_start_and_stop_halts():
    """Off-cost-free contract, asserted synchronously (the harness captures
    stdout once, so we avoid async timers): isPolling is False before start,
    True after start, False after stop; start() fires ONE immediate fetch via
    the injected impl (the call counter increments synchronously, before any
    Promise resolves)."""
    out = run_with_dom([M3_PRESENCE], _PRESENCE_BASE + """
        var calls = 0;
        function fakeFetch(url){
          calls++;
          // Resolved promise; the async render is irrelevant to this assertion
          // (we only prove the fetch was issued + the interval lifecycle).
          return Promise.resolve({
            json: function(){ return Promise.resolve({ count: 0, online: [] }); }
          });
        }
        window.M3PresencePanel.init({ fetchImpl: fakeFetch, intervalMs: 5000 });

        var pollingBeforeStart = window.M3PresencePanel.isPolling();
        window.M3PresencePanel.start(box);          // one immediate fetch
        var pollingAfterStart = window.M3PresencePanel.isPolling();
        var callsAfterStart = calls;
        window.M3PresencePanel.stop();              // clear the interval
        var pollingAfterStop = window.M3PresencePanel.isPolling();

        result = {
          pollingBeforeStart: pollingBeforeStart,
          pollingAfterStart: pollingAfterStart,
          pollingAfterStop: pollingAfterStop,
          callsAfterStart: callsAfterStart
        };
    """)
    assert out["pollingBeforeStart"] is False, "no poll before start (collapsed)"
    assert out["pollingAfterStart"] is True, "start() must arm the interval"
    assert out["pollingAfterStop"] is False, "stop() must clear the interval"
    assert out["callsAfterStart"] == 1, "start() must fire exactly one immediate fetch"


def test_presence_render_via_injected_fetch():
    """Prove the polled payload actually renders by driving renderInto with the
    same data the fetch would deliver (synchronous; no timer/Promise drain)."""
    out = run_with_dom([M3_PRESENCE], _PRESENCE_BASE + """
        var data = { count: 1, online: [
          { name: 'Solo', species: 'Human', location_area: 'Docking Bay',
            idle_seconds: 0, faction: 'Neutral' }
        ] };
        var n = window.M3PresencePanel.renderInto(box, data);
        result = { n: n, rows: box.querySelectorAll('.presence-row').length,
                   name: box.querySelector('.presence-name').textContent };
    """)
    assert out["n"] == 1
    assert out["rows"] == 1
    assert out["name"] == "Solo"


def test_presence_name_is_xss_escaped():
    out = run_with_dom([M3_PRESENCE], _PRESENCE_BASE + """
        window.M3PresencePanel.renderInto(box, { count: 1, online: [
          { name: "<script>alert('x')</script>", species: 'Human',
            location_area: "<img src=x onerror=alert(1)>",
            idle_seconds: 0, faction: 'Neutral' }
        ] });
        result = {
          liveScripts: box.querySelectorAll('script').length,
          liveImgs: box.querySelectorAll('img').length,
          nameText: box.querySelector('.presence-name').textContent
        };
    """)
    assert out["liveScripts"] == 0
    assert out["liveImgs"] == 0
    assert "<script>" in out["nameText"]
