# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_comms.py — REAL-BROWSER adversarial break-it: COMMS / social surface.

Surface under test: say / "/' / pose / : / emote / whisper / page / ooc / comlink /
fcomm / commfreq + the COMMS pane (tabbed IC/OOC/SYS filter, badges) and the pose
log rows those messages render into.

All comms commands go through the single ground command box (#cmd-input-ground) —
there is NO separate comms input. Comms OUTPUT is rendered into the pose log and
mirrored into #comms-body-ground via appendToCommsPane(); the tab strip is
#comms-tabs-ground with setCommsFilter('ground', <filter>).

What we hammer (browser-layer faults the happy path never sees):
  * XSS / HTML-shaped say  — must render as text, never a live <script>/<img> node.
  * oversized message (10k) — must not throw / 5xx / wedge the input.
  * page with no target / no message / nonexistent player / channel-injection name.
  * commfreq boundary frequencies + un-tuned transmit (silent no-op risk).
  * rapid tune/untune churn + rapid comms-tab churn (race / stuck-badge risk).
  * emote / say with control chars, ANSI escapes, lone reset, unterminated SGR.
  * clicking comms tabs while the pane is collapsed (stale/hidden control).
  * setCommsFilter with a bogus filter name (out-of-range UI state).

The auto-capture (pageerror / console.error / http5xx / requestfailed) catches the
crash class. For WRONG-BUT-QUIET behavior we ASSERT post-conditions in-browser and
raise AssertionError (surfaced by run_scenarios as the scenario's `error`).

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_comms.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def _enter(sess):
    """new_player() with relaxed Playwright timeouts. Six fresh server+browser
    boots run back-to-back (one per scenario); under that contention the default
    30s navigation timeout can trip on portal/chargen page.goto even though the
    server is up. Bumping the default nav/action timeout makes the boot resilient
    so a slow box reports REAL comms defects, not boot-contention PWTimeouts."""
    sess.page.set_default_navigation_timeout(90000)
    sess.page.set_default_timeout(45000)
    return sess.new_player()


def _comms_text(sess) -> str:
    """Concatenated visible text of every rendered comms-pane row."""
    return sess.page.eval_on_selector_all(
        "#comms-body-ground .comms-row",
        "els => els.map(e => e.textContent).join('\\n')",
    )


def _assert_input_usable(sess, label: str) -> None:
    """The ground command box must remain present, enabled, and writable."""
    inp = sess.page.locator("#cmd-input-ground")
    if inp.count() == 0:
        raise AssertionError(f"[{label}] command box #cmd-input-ground vanished")
    if inp.is_disabled():
        raise AssertionError(f"[{label}] command box became disabled")
    # Prove it still accepts input and we can clear it.
    inp.click()
    inp.fill("probe-after-" + label)
    if inp.input_value() != "probe-after-" + label:
        raise AssertionError(f"[{label}] command box stopped accepting input")
    inp.fill("")


# ── scenarios ──────────────────────────────────────────────────────────────

def s_xss_and_markup_say(sess):
    """say/emote/ooc HTML-and-script-shaped payloads. The no-html-event-field
    invariant means every one of these must render as inert TEXT — never create a
    live <script>/<img>/<iframe> node in the comms pane or pose log."""
    _enter(sess)
    payloads = [
        'say <script>window.__XSS_FIRED=1<\\/script>',
        'say <img src=x onerror="window.__XSS_FIRED=1">',
        'say <iframe src="javascript:window.__XSS_FIRED=1"></iframe>',
        "emote <b>bolded</b> & <svg/onload=window.__XSS_FIRED=1>",
        "ooc </span><h1>break-out</h1>",
        'say "><img src=x onerror=window.__XSS_FIRED=1>',
    ]
    for p in payloads:
        sess.send(p, settle_ms=300)
    sess.page.wait_for_timeout(800)

    # 1) No injected payload ever executed.
    fired = sess.page.evaluate("() => !!window.__XSS_FIRED")
    if fired:
        raise AssertionError("XSS payload EXECUTED — window.__XSS_FIRED set")
    # 2) No live <script>/<iframe> node was created from message content inside
    #    the pose log or comms pane.
    injected = sess.page.evaluate(
        "() => {"
        "  const scope = [document.getElementById('pose-log'),"
        "    document.getElementById('comms-body-ground')].filter(Boolean);"
        "  let n = 0;"
        "  scope.forEach(s => { n += s.querySelectorAll('script,iframe,svg,img').length; });"
        "  return n;"
        "}"
    )
    if injected:
        raise AssertionError(
            f"message content created {injected} live script/iframe/svg/img node(s) "
            "in pose-log/comms — markup was not escaped")
    _assert_input_usable(sess, "xss")


def s_oversized_and_control_chars(sess):
    """Oversized say (10k), emoji flood, control chars, ANSI escapes (incl. a lone
    reset and an unterminated SGR that ansiToHtml must close cleanly). None may
    throw, 5xx, or leave the input wedged; the comms pane must still render."""
    _enter(sess)
    big = "say " + ("A" * 10000)
    sess.send(big, settle_ms=900)
    _assert_input_usable(sess, "oversized")

    for junk in (
        "say " + "\U0001f680" * 400,             # emoji flood
        "emote \t\x07\x08\x1b[31mred\x1b[0m",     # tab/bell/backspace + complete SGR
        "say \x1b[1;33;44m unterminated color",   # SGR never reset → ansiToHtml must close
        "say \x1b[0m",                            # lone reset, no open span
        "emote \x00\x01\x02\x03 nul-and-friends", # raw control bytes
        "say \r\n\r\n multi newline \n payload",  # embedded newlines
    ):
        sess.send(junk, settle_ms=350)
    sess.page.wait_for_timeout(600)
    _assert_input_usable(sess, "control-chars")
    # The pane should have rendered at least the self-echoes / system rows;
    # a hard render crash would leave it empty AND raise pageerror (captured).


def s_page_target_edge_cases(sess):
    """page with no message, no target, a nonexistent player, an injection-shaped
    name, and a self-page. Each is a validation path that must respond (not 5xx,
    not a silent no-op that wedges _last_paged) and keep the input usable."""
    _enter(sess)
    for cmd in (
        "page",                                   # no args at all
        "page Nobody123XYZ = hello there",        # nonexistent target
        "page = orphaned message",                # empty target, has '='
        "page SomeGhost =",                       # has target, empty message
        "page <script>alert(1)</script> = hi",    # markup-shaped target name
        "page " + ("Z" * 500) + " = long name",   # absurdly long target name
        "page just a message no target no equals",# re-page path with no prior target
    ):
        sess.send(cmd, settle_ms=350)
    sess.page.wait_for_timeout(500)
    _assert_input_usable(sess, "page")
    # The nonexistent-target page must have produced a 'Could not find' style
    # response somewhere visible (pose log), proving it did NOT silently no-op.
    log_text = sess.page.eval_on_selector_all(
        "#pose-log .row, #pose-log .plain-text, #pose-log div",
        "els => els.map(e => e.textContent).join('\\n').toLowerCase()",
    )
    if "nobody123xyz" not in log_text and "could not find" not in log_text \
            and "no player" not in log_text:
        # Not a hard crash, but record it as a quiet no-op finding via console.
        sess.page.evaluate(
            "() => console.error('BREAKIT_OBSERVED: page to nonexistent target "
            "produced no visible response (possible silent no-op)')"
        )


def s_channel_and_freq_injection(sess):
    """ooc/comlink/fcomm/commfreq with empty bodies, boundary + out-of-range
    frequencies, un-tuned transmit, and markup-shaped bodies. Frequency parsing
    and the un-tuned guard are the soft spots; nothing may 5xx or throw."""
    _enter(sess)
    for cmd in (
        "ooc",                                    # empty OOC
        "comlink",                                # empty comlink
        "fcomm",                                  # empty faction comm
        "commfreq",                               # no freq, no msg
        "commfreq 1138 transmit before tuning",   # un-tuned → guarded no-op
        "commfreq 0 below range",                 # freq < 1
        "commfreq 99999 above range",             # freq > 9999
        "commfreq abc not a number",              # non-numeric freq
        "commfreq -5 negative",                   # negative freq
        "commfreq 1.5 float",                     # float freq
        "ooc <script>window.__XSS_FIRED=1</script>",  # markup over OOC
        "comlink <img src=x onerror=window.__XSS_FIRED=1>",
        "tune notanumber",                        # bad tune arg
        "untune 4242",                            # untune one never tuned
    ):
        sess.send(cmd, settle_ms=300)
    sess.page.wait_for_timeout(600)
    if sess.page.evaluate("() => !!window.__XSS_FIRED"):
        raise AssertionError("channel-message XSS payload EXECUTED")
    _assert_input_usable(sess, "freq")


def s_rapid_tune_and_tab_churn(sess):
    """Rapid join/leave (tune/untune) churn + rapid comms-tab switching (incl. a
    bogus filter) + a flood of OOC. Provokes client-side races, stuck unread
    badges, and stale filter state. Post-condition: every real tab still selects,
    and a bogus filter doesn't wedge the pane."""
    _enter(sess)

    # Rapid tune/untune of the same freq — channel-manager churn.
    for _ in range(12):
        sess.send("tune 4242", settle_ms=0)
        sess.send("untune 4242", settle_ms=0)
    sess.page.wait_for_timeout(800)
    _assert_input_usable(sess, "tune-churn")

    # Flood OOC so the comms pane has events + badge activity.
    for i in range(10):
        sess.send(f"ooc flood line {i}", settle_ms=0)
    sess.page.wait_for_timeout(800)

    # Rapid legitimate tab churn.
    for f in ("ic", "ooc", "sys", "all", "ic", "sys", "ooc", "all"):
        sess.page.evaluate("f => setCommsFilter('ground', f)", f)
    # Bogus filter — must not throw and must not wedge the pane.
    sess.page.evaluate("() => setCommsFilter('ground', 'this-is-not-a-tab')")
    sess.page.wait_for_timeout(300)

    # Recover to a real tab and confirm it took effect (active class + render).
    sess.page.evaluate("() => setCommsFilter('ground', 'all')")
    sess.page.wait_for_timeout(300)
    active_ok = sess.page.evaluate(
        "() => { const t = document.querySelector("
        "'#comms-tabs-ground .comms-tab[data-filter=\"all\"]');"
        " return !!t && t.classList.contains('active'); }"
    )
    if not active_ok:
        raise AssertionError("comms 'all' tab did not re-activate after bogus filter")
    _assert_input_usable(sess, "tab-churn")


def s_collapsed_pane_tab_clicks(sess):
    """Collapse the comms pane, then drive setCommsFilter / toggle while it's
    collapsed and click tab buttons that are visually hidden. State must stay
    coherent: re-expanding must render without error and the input stays usable."""
    _enter(sess)
    # Generate some comms content first.
    for i in range(4):
        sess.send(f"ooc pre-collapse {i}", settle_ms=0)
    sess.page.wait_for_timeout(500)

    # Collapse the pane.
    sess.page.evaluate("() => toggleCommsPane('ground')")
    sess.page.wait_for_timeout(200)
    collapsed = sess.page.evaluate(
        "() => document.getElementById('comms-pane-ground')"
        ".classList.contains('collapsed')"
    )
    # Drive filters + more OOC while collapsed (badges should accrue, no crash).
    for f in ("ic", "ooc", "sys", "all"):
        sess.page.evaluate("f => setCommsFilter('ground', f)", f)
    for i in range(5):
        sess.send(f"ooc while-collapsed {i}", settle_ms=0)
    sess.page.wait_for_timeout(500)

    # Fire a tab button's own click handler even though the strip is hidden by
    # the collapsed-pane CSS (a real Playwright click refuses an invisible
    # element; dispatching .click() on the node exercises the SAME stale-control
    # code path — setCommsFilter on a pane that isn't showing the strip).
    sess.page.evaluate(
        "() => { const b = document.querySelector("
        "'#comms-tabs-ground .comms-tab[data-filter=\"ooc\"]');"
        " if (b) b.click(); }"
    )
    sess.page.wait_for_timeout(200)

    # Re-expand and confirm it renders cleanly.
    if collapsed:
        sess.page.evaluate("() => toggleCommsPane('ground')")
    sess.page.wait_for_timeout(400)
    still_collapsed = sess.page.evaluate(
        "() => document.getElementById('comms-pane-ground')"
        ".classList.contains('collapsed')"
    )
    if still_collapsed:
        raise AssertionError("comms pane stuck collapsed after re-toggle")
    _assert_input_usable(sess, "collapsed-pane")


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "comms",
        [
            s_xss_and_markup_say,
            s_oversized_and_control_chars,
            s_page_target_edge_cases,
            s_channel_and_freq_injection,
            s_rapid_tune_and_tab_churn,
            s_collapsed_pane_tab_clicks,
        ],
    ))
