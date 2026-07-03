# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_commands.py — REAL-BROWSER break-it for the GROUND COMMAND LOOP.

Surface: the main in-game command input box (#cmd-input-ground), its keydown
wiring (Enter submit, Escape clear, ArrowUp/ArrowDown history), the SEND button,
the local-intercept commands (guide/help → guide overlay), and the echo/render
path (appendEvent → ansiToHtml/escapeHtml) plus the WS round-trip to the parser.

Each scenario boots its OWN fresh server+Chromium (run_scenarios) and the harness
auto-captures pageerror / console.error / http5xx / requestfailed. Where the
auto-capture can't see a fault (a command that wrongly no-ops, a stuck panel,
input box that stops accepting text), we ASSERT a post-condition in-scenario and
raise a clear AssertionError so it lands as the scenario `error` in the report.

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_commands.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────
def _new_player(sess, attempts=2):
    """new_player() but tolerant of this box's boot/contention flake (sibling
    break-it servers compete for CPU). A first-load timeout is a HARNESS artifact,
    not an app bug — retry once before giving up so a transient slow boot doesn't
    masquerade as a surface defect."""
    from playwright.sync_api import TimeoutError as PWTimeout
    last = None
    for _ in range(attempts):
        try:
            return sess.new_player()
        except PWTimeout as e:
            last = e
            sess.page.wait_for_timeout(1500)
    raise last


def _input_value(sess):
    return sess.page.eval_on_selector("#cmd-input-ground", "el => el.value")


def _close_guide_overlay(sess):
    """Dismiss the guide overlay if it is open (Escape, then the close button).
    Returns True if the overlay ended closed."""
    page = sess.page
    if not page.eval_on_selector("#guide-overlay", "el => el && el.classList.contains('show')"):
        return True
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    if not page.eval_on_selector("#guide-overlay", "el => el.classList.contains('show')"):
        return True
    try:
        closer = page.locator(".guide-modal-close").first
        if closer.count() and closer.is_visible():
            closer.click()
            page.wait_for_timeout(250)
    except Exception:
        pass
    return not page.eval_on_selector("#guide-overlay", "el => el.classList.contains('show')")


def _assert_box_responsive(sess, probe="look"):
    """The command box must still accept input and submit after any abuse.
    Type a probe command, confirm it appears in the field, submit it, then
    confirm the field cleared (Enter handler ran)."""
    page = sess.page
    _close_guide_overlay(sess)   # a local-intercept command may have a modal up
    inp = page.locator("#cmd-input-ground")
    inp.click()
    inp.fill(probe)
    got = _input_value(sess)
    assert got == probe, f"command box not accepting input: typed {probe!r}, field holds {got!r}"
    inp.press("Enter")
    page.wait_for_timeout(400)
    after = _input_value(sess)
    assert after == "", f"command box did not clear after Enter (stuck): field holds {after!r}"


def _poselog_count(sess):
    return sess.page.eval_on_selector_all("#pose-log > *", "els => els.length")


# ── scenario 1: oversized / control-char / injection flood ───────────────
def s_oversized_and_injection(sess):
    """Throw oversized, control-char, XSS-/SQLi-shaped, and emoji-flood input at
    the box. None should throw a pageerror or inject markup; the box must remain
    responsive afterward and no <script>/<img> node should appear in the log."""
    _new_player(sess)
    payloads = [
        "x" * 10000,                                  # oversized single token
        "say " + "A" * 8000,                          # oversized with a verb
        ";;;@@@###|||\\\\////***&&&^^^%%%$$$",        # punctuation soup
        "look \t\x07\x1b[31mRED\x1b[0m \x1b[999m",    # tab+bell+ANSI (valid+bogus SGR)
        "<script>window.__xss=1;document.title='PWNED'</script>",  # XSS via echo
        '<img src=x onerror="window.__xss2=1">',      # XSS via img onerror
        "</span></div><b>break</b>",                  # tag-break-out attempt
        "'; DROP TABLE characters;-- ",               # SQLi-shaped
        "say " + "\U0001f600\U0001f680✨" * 300,  # emoji / astral flood
        "say ‮​RTL​ override",         # bidi/zero-width control
    ]
    for p in payloads:
        sess.send(p, settle_ms=250)

    # WRONG-BEHAVIOR / XSS checks the auto-capture won't catch:
    xss = sess.page.evaluate("() => ({a: window.__xss || 0, b: window.__xss2 || 0, title: document.title})")
    assert not xss["a"] and not xss["b"], f"XSS executed via command echo: {xss}"
    # No injected element nodes should exist in the pose log (escaped → text only).
    bad = sess.page.eval_on_selector_all(
        "#pose-log script, #pose-log img, #pose-log b",
        "els => els.length")
    assert bad == 0, f"command echo injected {bad} live element node(s) into the log (XSS escape gap)"
    _assert_box_responsive(sess)


# ── scenario 2: command history navigation abuse ─────────────────────────
def s_history_navigation(sess):
    """Fill history with junk (incl. injection-shaped + huge entries), then hammer
    ArrowUp past the top and ArrowDown past the bottom. History recall must not
    throw, must not inject markup when the recalled value is re-displayed, and the
    box must stay responsive."""
    _new_player(sess)
    seeds = [
        "look",
        "<script>window.__h=1</script>",
        "x" * 5000,
        "'; DELETE FROM x;--",
        "say hi \x1b[31m",
        "inventory",
    ]
    for s in seeds:
        sess.send(s, settle_ms=120)

    page = sess.page
    inp = page.locator("#cmd-input-ground")
    inp.click()
    # ArrowUp far past the top of history (history length is bounded; over-press it)
    for _ in range(20):
        inp.press("ArrowUp")
        page.wait_for_timeout(30)
    top = _input_value(sess)
    assert top == seeds[0], f"ArrowUp past top should clamp to oldest {seeds[0]!r}, got {top!r}"
    # ArrowDown far past the bottom — should return to an empty/draft field, not crash
    for _ in range(20):
        inp.press("ArrowDown")
        page.wait_for_timeout(30)
    bottom = _input_value(sess)
    assert bottom == "", f"ArrowDown past bottom should restore empty draft, got {bottom!r}"
    # Recalling the injection-shaped entry must not have executed it.
    assert page.evaluate("() => window.__h || 0") == 0, "history recall executed injected script"
    _assert_box_responsive(sess)


# ── scenario 3: rapid double-submit / Enter+SEND races ───────────────────
def s_rapid_double_submit(sess):
    """Provoke double-submit: hammer Enter with no settle, click SEND while the
    field is mid-fill, and interleave Enter+button. Must not throw; the field
    must end empty (not stuck with leftover text) and the box must stay live."""
    _new_player(sess)
    page = sess.page
    inp = page.locator("#cmd-input-ground")
    btn = page.locator("#send-btn-ground")

    # 25 rapid Enter submits with zero settle
    for _ in range(25):
        inp.click()
        inp.fill("look")
        inp.press("Enter")
    page.wait_for_timeout(50)

    # Enter then immediate SEND click on an already-empty field (double-fire path)
    inp.click()
    inp.fill("inventory")
    inp.press("Enter")
    btn.click()                      # second submit on now-empty field → must no-op cleanly
    page.wait_for_timeout(50)

    # SEND button click with text staged, repeated fast
    for _ in range(10):
        inp.fill("look")
        btn.click()
    page.wait_for_timeout(800)

    end = _input_value(sess)
    assert end == "", f"field left non-empty after rapid submits (stuck): {end!r}"
    _assert_box_responsive(sess)


# ── scenario 4: local-intercept guide/help spam (stuck-overlay hunt) ─────
def s_guide_overlay_spam(sess):
    """guide/help/+guide are intercepted CLIENT-SIDE (open the guide overlay, no
    server round-trip). Spam them and confirm the overlay isn't permanently stuck
    over the command box and the box recovers. A stuck modal that swallows the
    input is a real UX defect the auto-capture can't see."""
    _new_player(sess)
    page = sess.page

    # NOTE: while the modal is OPEN it (correctly) covers the command box, so we
    # must dismiss it between commands — we cannot type the next command through
    # an open modal (that is expected behaviour, not a bug). The real question is:
    # does the overlay ALWAYS dismiss via Escape, or can repeated open churn wedge
    # it open over the input? Drive open/close cycles for every intercept alias.
    aliases = ("guide", "help", "+guide", "guides", "+guides", "guide", "help")
    for cmd in aliases:
        sess.send(cmd, settle_ms=200)               # box is clear → click+open OK
        opened = page.eval_on_selector(
            "#guide-overlay", "el => el.classList.contains('show')")
        assert opened, (
            f"command {cmd!r} did not open the guide overlay (local intercept "
            "in sendCmd broke)")
        # Dismiss the way a player does, then assert it actually closed.
        closed = _close_guide_overlay(sess)
        assert closed, (
            f"guide overlay opened by {cmd!r} would NOT dismiss (Escape + close "
            "button both failed) — modal stuck over the command box")

    # After all that overlay churn the command box must be live again.
    _assert_box_responsive(sess, probe="look")


# ── scenario 5: empty / whitespace / single ultra-long token boundary ────
def s_empty_and_boundary(sess):
    """Empty and whitespace-only must clear the field and NOT throw / NOT push a
    'Not connected' or error row (sendCmd early-returns for blank input). A single
    20k-char no-space token must not throw or wedge the layout. Then confirm the
    box still works. (Auto-capture flags any pageerror/console.error these raise;
    the explicit checks catch field-stuck + wrong-feedback that capture can't see.)"""
    _new_player(sess)
    page = sess.page
    inp = page.locator("#cmd-input-ground")

    # Blank submits: field must clear and the client must NOT surface any error/
    # not-sent notice for them (a blank is a silent no-op, never an error). We read
    # the pose-log text (DOM, not an IIFE-local global) for a not-sent marker.
    for blank in ("", "   ", "\t\t", "\n", "     \t   "):
        inp.click()
        inp.fill(blank)
        inp.press("Enter")
        page.wait_for_timeout(120)
        assert _input_value(sess) == "", f"field not cleared after blank submit {blank!r}"
    log_txt = page.eval_on_selector("#pose-log", "el => el.textContent || ''")
    assert "command not sent" not in log_txt.lower(), (
        "a blank/whitespace submit produced a 'command not sent' notice; empty "
        "input must silently no-op, not be treated as a real command")

    # Single ultra-long no-space token (no verb, no spaces) — boundary for the
    # server parser + the client echo/layout. Must not throw or wedge the box.
    sess.send("Z" * 20000, settle_ms=400)
    _assert_box_responsive(sess)


# ── scenario 6: network blip mid-command (offline → submit → recover) ────
def s_network_blip_and_recover(sess):
    """Drop the network at the browser layer (context.set_offline) so the live WS
    breaks, fire commands during the outage, then restore the network. Adversarial
    target: a command submitted while the socket is down must NOT throw an uncaught
    JS exception, and once the network returns the command box must work again
    (the client auto-reconnects). Uses the REAL network layer — not any IIFE-local
    handle — so it exercises the genuine dropped-link path a player hits."""
    _new_player(sess)
    page = sess.page
    ctx = page.context

    inp = page.locator("#cmd-input-ground")
    # Go offline — the open WS will error/close; auto-reconnect attempts will fail.
    ctx.set_offline(True)
    page.wait_for_timeout(600)

    # Fire several commands during the outage. sendCmd's `ws.readyState !== OPEN`
    # guard should keep these from throwing; worst case it appends a sys notice.
    for _ in range(4):
        inp.click()
        inp.fill("look")
        inp.press("Enter")
        page.wait_for_timeout(150)
        assert _input_value(sess) == "", "field did not clear on submit during outage"

    # Restore the network and give the client time to auto-reconnect.
    ctx.set_offline(False)
    page.wait_for_timeout(4000)

    # The command box must be usable again after recovery. (If the reconnect path
    # left the box wedged or the field stuck, this raises a clear AssertionError.)
    _close_guide_overlay(sess)
    inp.click()
    inp.fill("look")
    assert _input_value(sess) == "look", (
        "command box not accepting input after network recovery (reconnect wedged "
        "the input)")
    inp.press("Enter")
    page.wait_for_timeout(500)
    assert _input_value(sess) == "", "field did not clear after post-recovery submit"


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "commands",
        [
            s_oversized_and_injection,
            s_history_navigation,
            s_rapid_double_submit,
            s_guide_overlay_spam,
            s_empty_and_boundary,
            s_network_blip_and_recover,
        ],
    ))
