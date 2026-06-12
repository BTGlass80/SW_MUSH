"""
test_m3_scroll_on_move.py — Drop UI-1 (scroll-on-move fix) client changes.

Pins the fix that makes a room change re-anchor the live stream to the new
room banner regardless of the player's current scroll position, plus the
one-beat highlight sweep that draws the eye to the landing.

The clunk being fixed: when scrolled up reading history, issuing a movement
command appended the new-room banner but did NOT re-anchor scroll — it merely
bumped the unread pill, so the player never visibly "landed" in the new room.

Like test_clickwalk_slugjoin, this runs the ACTUAL production functions
extracted from client.html (brace-matched, not re-implemented), so the test
and the shipped code cannot drift.

  · Static guards: the new symbols/markers exist in client.html + the CSS.
  · Logic (node, no jsdom): renderEventToActiveLog re-anchors on a
    'room-enter' event from a scrolled-up position and applies the sweep
    class, while a 'pose' event from the same position does neither.
"""
from __future__ import annotations

import json
import re
import subprocess
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"


# ── helpers ──────────────────────────────────────────────────────────

def _inline_js() -> str:
    html = CLIENT_HTML.read_text(encoding="utf-8")
    m = re.search(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html, re.I)
    assert m, "no inline <script> block found in client.html"
    return m.group(1)


def _brace_match(js: str, start: int) -> int:
    """Return the index just past the function body that begins at `start`."""
    depth = 0
    started = False
    for k in range(start, len(js)):
        c = js[k]
        if c == "{":
            depth += 1
            started = True
        elif c == "}":
            depth -= 1
            if started and depth == 0:
                return k + 1
    raise AssertionError("could not brace-match function body")


def _render_and_anchor_block() -> str:
    """Extract `renderEventToActiveLog` + `anchorRoomEnterRow` as they ship
    (brace-matched, contiguous), so the test exercises real source."""
    js = _inline_js()
    start = js.index("function renderEventToActiveLog(")
    anchor_start = js.index("function anchorRoomEnterRow(", start)
    end = _brace_match(js, anchor_start)
    return js[start:end]


def _run_node(script: str) -> dict:
    try:
        if subprocess.run(["node", "--version"], capture_output=True).returncode != 0:
            pytest.skip("node not available")
    except (FileNotFoundError, OSError):
        pytest.skip("node not available")
    with tempfile.NamedTemporaryFile(
        "w", suffix=".mjs", delete=False, encoding="utf-8"
    ) as f:
        f.write(script)
        path = f.name
    proc = subprocess.run(
        ["node", path], capture_output=True, text=True, encoding="utf-8"
    )
    assert proc.returncode == 0, f"node failed:\n{proc.stderr}\n{proc.stdout}"
    return json.loads(proc.stdout)


# ── static guards ────────────────────────────────────────────────────

def test_scroll_on_move_symbols_present():
    text = CLIENT_HTML.read_text(encoding="utf-8")
    for needle in (
        "function anchorRoomEnterRow(",
        "ev.t === 'room-enter'",     # the re-anchor branch in renderEventToActiveLog
        "room-enter-sweep",          # the highlight class
        "@keyframes m3-room-sweep",  # the token-only sweep animation
    ):
        assert needle in text, f"expected scroll-on-move marker missing: {needle!r}"


def test_sweep_keyframes_use_only_tokens():
    """The sweep must not introduce a new colour — it glows the existing
    accent tokens (matches the no-new-colors law)."""
    text = CLIENT_HTML.read_text(encoding="utf-8")
    m = re.search(r"@keyframes m3-room-sweep\s*\{([\s\S]*?)\}\s*\}", text)
    # grab just the keyframes body (up to its closing brace pair)
    m = re.search(r"@keyframes m3-room-sweep\s*\{([\s\S]*?)\n\}", text)
    assert m, "could not isolate m3-room-sweep keyframes body"
    body = m.group(1)
    # only var(--accent…) / transparent colours, no hex / rgb literals
    assert "var(--accent" in body, "sweep should use the accent tokens"
    assert not re.search(r"#[0-9a-fA-F]{3,6}", body), "sweep introduced a hex colour"
    assert "rgb(" not in body and "rgba(" not in body, "sweep introduced an rgb literal"


# ── logic (real production functions, no jsdom) ──────────────────────

_DRIVER = r"""
// ---- minimal stubs for the handful of globals the two functions touch ----
const AUTOSCROLL_THRESHOLD_PX = 30;
let newSinceScroll = 0;

function mkClassList() {
  const s = new Set();
  return {
    add: (c) => s.add(c),
    remove: (c) => s.delete(c),
    contains: (c) => s.has(c),
    _set: s,
  };
}

// Fake log simulating "scrolled up in history": not at bottom.
const log = {
  scrollTop: 999, scrollHeight: 5000, clientHeight: 400,
  _appended: [],
  appendChild(el) { this._appended.push(el); },
  getBoundingClientRect() { return { top: 80 }; },
};
const pill = { classList: mkClassList() };
const pillCount = { textContent: null };

function activeLogEl() { return log; }
function activePillEl() { return pill; }
function activePillCountEl() { return pillCount; }

// buildRow stub — the scroll fix lives entirely in renderEventToActiveLog /
// anchorRoomEnterRow, so a faithful fake row is sufficient (and avoids buildRow's
// escapeHtml/ansi deps). The fake row reports a top BELOW the log top so the
// element->container delta is a real, non-zero re-anchor.
function buildRow(ev) {
  return {
    _t: ev.t,
    classList: mkClassList(),
    offsetTop: 4200,
    getBoundingClientRect() { return { top: 200 }; },
  };
}

// Capture deferred work instead of firing it (mirrors the test harness, where
// rAF/setTimeout don't run before the process exits).
const rafCbs = [];
const window = { requestAnimationFrame: (cb) => { rafCbs.push(cb); return rafCbs.length; } };
function requestAnimationFrame(cb) { rafCbs.push(cb); return rafCbs.length; }
const timeouts = [];
function setTimeout(cb, ms) { timeouts.push(ms); return timeouts.length; }

// ---- the real production source under test ----
%s

// ---- exercise ----
// 1) a normal pose from the scrolled-up position: must NOT re-anchor, must show pill.
log.scrollTop = 999;
const poseRow = (function(){ const r = renderEventToActiveLog({ t: 'pose', who: 'x', text: 'hi' }); return log._appended[log._appended.length-1]; })();
const afterPose = { scrollTop: log.scrollTop, pillShown: pill.classList.contains('show'), sweep: poseRow.classList.contains('room-enter-sweep'), newSince: newSinceScroll };

// reset visible state, then 2) a room-enter from the scrolled-up position: MUST re-anchor + sweep + clear pill.
pill.classList.remove('show');
newSinceScroll = 5;
log.scrollTop = 999;
rafCbs.length = 0; timeouts.length = 0;
renderEventToActiveLog({ t: 'room-enter', name: 'Cantina', security: 'lawless' });
const enterRow = log._appended[log._appended.length-1];
const afterEnter = {
  scrollTop: log.scrollTop,
  reAnchored: log.scrollTop !== 999,
  sweep: enterRow.classList.contains('room-enter-sweep'),
  pillShown: pill.classList.contains('show'),
  newSince: newSinceScroll,
  rafScheduled: rafCbs.length,      // the re-pin
  timeoutScheduled: timeouts.length, // the sweep-clear
};

console.log(JSON.stringify({ afterPose, afterEnter }));
"""


def test_room_enter_reanchors_while_pose_does_not():
    out = _run_node(_DRIVER % _render_and_anchor_block())

    # A pose from a scrolled-up position leaves scroll alone and raises the pill.
    assert out["afterPose"]["scrollTop"] == 999, "pose must not yank scroll"
    assert out["afterPose"]["pillShown"] is True, "pose should bump the unread pill"
    assert out["afterPose"]["sweep"] is False, "pose must not get the room sweep"
    assert out["afterPose"]["newSince"] >= 1

    # A room-enter from the same position re-anchors, sweeps, and clears the pill.
    e = out["afterEnter"]
    assert e["reAnchored"] is True, "room-enter must re-anchor scroll regardless of position"
    assert e["scrollTop"] != 999
    assert e["sweep"] is True, "room-enter banner must get the highlight sweep"
    assert e["pillShown"] is False, "landing on a new room clears the unread pill"
    assert e["newSince"] == 0, "newSinceScroll resets on a room landing"
    assert e["rafScheduled"] >= 1, "a rAF re-pin should be scheduled"
    assert e["timeoutScheduled"] >= 1, "the sweep-clear timeout should be scheduled"
