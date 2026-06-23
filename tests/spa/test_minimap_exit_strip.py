"""
test_minimap_exit_strip.py — always-visible mini-map click-to-move fix
(drop sidebar-contract-handoff-capture, 2026-06-22).

THE BUG (Brian, live): on the always-visible mini-map only SOME exits were
clickable. Root cause: on-map click-to-walk (_decorateMiniForClickToWalk) only
tags rooms that render a <g data-room-id> marker, but L_SubstrateRooms skips
street/hub-style rooms — so an exit whose destination is a street/hub (e.g.
"Docking Bay 94 - Entrance" -> spaceport row) had NO clickable target. The
sector-map MODAL already solved this with an always-every-exit button strip
sourced from lastExits (_renderModalExitStrip); the always-visible mini did not.

THE FIX: a shared _buildExitStrip() now backs both the modal strip and a new
always-visible mini strip (#g-map-exits), refreshed on every room change. Every
exit is clickable regardless of which rooms draw markers — killing the class,
not just Bay 94.

Like test_clickwalk_slugjoin, the DOM test runs the ACTUAL production functions
extracted from client.html (brace-/anchor-sliced, not re-implemented) so the
test and shipped code cannot drift.
"""
from __future__ import annotations

import re
from pathlib import Path

from .spa_dom_harness import run_with_dom

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


# ── helpers ──────────────────────────────────────────────────────────

def _inline_js() -> str:
    html = CLIENT_HTML.read_text(encoding="utf-8")
    m = re.search(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html, re.I)
    assert m, "no inline <script> block found in client.html"
    return m.group(1)


def _exit_strip_block() -> str:
    """The contiguous exit-strip helpers as they ship: from `function
    _buildExitStrip(` through the window export of _renderMiniExitStrip."""
    js = _inline_js()
    start = js.index("function _buildExitStrip(")
    end_anchor = "window._sw_renderMiniExitStrip = _renderMiniExitStrip;"
    end = js.index(end_anchor, start) + len(end_anchor)
    return js[start:end]


# ── static guards: the symbols + wiring exist in client.html ─────────

def test_minimap_exit_strip_symbols_present():
    text = CLIENT_HTML.read_text(encoding="utf-8")
    for needle in (
        "function _buildExitStrip(",
        "function _renderMiniExitStrip(",
        'id="g-map-exits"',
        ".map-exits {",
        ".map-exits .mm-exit-btn",
        "window._sw_renderMiniExitStrip",
    ):
        assert needle in text, f"expected marker missing from client.html: {needle!r}"


def test_mini_strip_refreshed_on_every_room_change():
    """_renderMiniExitStrip() must be called at BOTH room-change branches
    (exits present + no-exits), right where the qa-row chips rebuild."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    # present-exits branch
    assert re.search(
        r"rebuildDirectionButtons\(data\.exits\);\s*\r?\n\s*_renderMiniExitStrip\(\);",
        text,
    ), "mini strip not refreshed on the exits-present room change"
    # empty branch
    assert re.search(
        r"rebuildDirectionButtons\(\[\]\);\s*\r?\n\s*_renderMiniExitStrip\(\);",
        text,
    ), "mini strip not cleared on the no-exits room change"


def test_modal_strip_still_delegates_to_shared_builder():
    """Regression: the modal strip keeps working — it now delegates to the
    shared _buildExitStrip with the modal-close afterClick."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    assert "_buildExitStrip($('map-modal-exits')" in text, \
        "modal strip no longer delegates to _buildExitStrip"
    assert "_buildExitStrip($('g-map-exits'), null)" in text, \
        "mini strip no longer delegates to _buildExitStrip"


# ── DOM behaviour (jsdom; auto-skips if jsdom missing) ───────────────

_SETUP = r"""
    // production globals the strip functions close over
    window.$ = function (id) { return document.getElementById(id); };
    var sent = [];
    window.sendCmd = function (d) { sent.push(d); };
    var closed = 0;
    window.closeMapModal = function () { closed++; };

    var mini = document.createElement('div');  mini.id = 'g-map-exits';
    var modal = document.createElement('div'); modal.id = 'map-modal-exits';
    document.body.appendChild(mini); document.body.appendChild(modal);

    function dirs(box) {
      return Array.prototype.map.call(
        box.querySelectorAll('button.mm-exit-btn'),
        function (b) { return b.getAttribute('data-cmd'); });
    }
    function clickDir(box, dir) {
      Array.prototype.forEach.call(box.querySelectorAll('button.mm-exit-btn'),
        function (b) { if (b.getAttribute('data-cmd') === dir) b.click(); });
    }

    // CASE 1 — Bay 94: down=pit(marker), north=spaceport_row(STREET, no marker),
    // northwest=customs. All three must become clickable; the street exit is the
    // one the old on-map decoration could not reach.
    window.lastExits = [
      { dir: 'down',      label: 'Pit Floor' },
      { dir: 'north',     label: 'Spaceport Row' },
      { dir: 'northwest', label: 'Customs Office' },
    ];
    window._renderMiniExitStrip();
    var miniDirs = dirs(mini);
    clickDir(mini, 'north');                 // walk the markerless street exit

    // CASE 2 — no exits clears the strip
    window.lastExits = [];
    window._renderMiniExitStrip();
    var emptyCount = mini.querySelectorAll('button.mm-exit-btn').length;

    // CASE 3 — modal regression: shared builder + modal-close afterClick
    window.lastExits = [{ dir: 'south', label: '' }];
    window._renderModalExitStrip();
    var modalCount = modal.querySelectorAll('button.mm-exit-btn').length;
    clickDir(modal, 'south');

    // CASE 4 — a room with MORE THAN 4 exits. The mini strip is UNCAPPED (unlike
    // the 4-chip qa-row), so every exit renders and the flex row wraps. This is
    // the >4-exit navigation gap Brian flagged.
    window.lastExits = [
      { dir: 'north', label: '' }, { dir: 'south', label: '' },
      { dir: 'east',  label: '' }, { dir: 'west',  label: '' },
      { dir: 'up',    label: '' }, { dir: 'down',  label: '' },
    ];
    window._renderMiniExitStrip();
    var sixDirs = dirs(mini);

    result = {
      miniDirs: miniDirs,
      sent: sent,
      emptyCount: emptyCount,
      modalCount: modalCount,
      closed: closed,
      sixCount: sixDirs.length,
      sixDirs: sixDirs,
    };
"""


def test_every_exit_is_clickable_including_markerless_streets(tmp_path):
    block = _exit_strip_block()
    module = block + "\n".join([
        "",
        "window._buildExitStrip = _buildExitStrip;",
        "window._renderModalExitStrip = _renderModalExitStrip;",
        "window._renderMiniExitStrip = _renderMiniExitStrip;",
    ])
    mod_path = tmp_path / "exit_strip_extracted.js"
    mod_path.write_text(module, encoding="utf-8")

    out = run_with_dom([mod_path], _SETUP)  # skips if no jsdom

    # CASE 1: all three exits rendered, in order, incl the markerless street.
    assert out["miniDirs"] == ["down", "north", "northwest"], out["miniDirs"]
    # clicking the street exit routed to sendCmd (it would have been dead on-map).
    assert "north" in out["sent"], out["sent"]
    # CASE 2: empty exits -> empty strip (:empty CSS hides it).
    assert out["emptyCount"] == 0
    # CASE 3: modal strip still builds + its click closes the modal.
    assert out["modalCount"] == 1
    assert "south" in out["sent"]
    assert out["closed"] == 1, "modal afterClick (closeMapModal) did not fire"
    # CASE 4: >4 exits all render (uncapped) — the 6-exit room is fully navigable.
    assert out["sixCount"] == 6, out["sixDirs"]
    assert out["sixDirs"] == ["north", "south", "east", "west", "up", "down"], \
        out["sixDirs"]
