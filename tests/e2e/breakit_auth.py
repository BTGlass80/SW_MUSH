# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_auth.py — adversarial REAL-BROWSER break-it for the AUTH surface.

Surface = the /client.html login form (#boot-state-login) + the character-select
boot state (#boot-state-charselect). These run BEFORE the game loop, over the live
WebSocket, so a happy-path login test never exercises the failure edges:

  * empty / wrong / injection-shaped credentials
  * rapid double-submit (double `connect` lines on one socket)
  * submit / select when the precondition is absent (socket not OPEN, list empty)
  * selecting a character id that does NOT belong to the account (server silently
    ignores unknown ids in its __char_select__ loop — does the client get stuck?)
  * +NEW character button spam
  * reload mid-login

Each scenario ASSERTS post-conditions where it can (the form still works, no panel
is stuck) and raises AssertionError on wrong/stuck behaviour the auto-capture can't
see; the harness records that as a scenario error. Browser-layer faults (pageerror,
console.error, http5xx, requestfailed) are auto-captured into session.defects().

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_auth.py
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import BreakItSession, run_scenarios  # noqa: E402
from tests.e2e.playwright_new_player_poc import drive_wizard  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def _relax_timeouts(sess) -> None:
    """This is a personal dev box that also hosts the Claude session; each
    scenario boots its OWN server+Chromium, so back-to-back runs starve the box
    and the default 30s nav timeout flakes. Give navigation/actions generous
    headroom so a slow boot is not mistaken for an app defect."""
    sess.page.set_default_timeout(60000)
    sess.page.set_default_navigation_timeout(60000)


def _goto(sess, path: str, tries: int = 3) -> None:
    """Navigate with retry — a slow first paint under box contention should not
    fail the scenario (that would be a harness artifact, not an app defect)."""
    last = None
    for _ in range(tries):
        try:
            sess.page.goto(sess.base + path, wait_until="domcontentloaded",
                           timeout=60000)
            return
        except Exception as e:  # noqa: BLE001
            last = e
            sess.page.wait_for_timeout(1000)
    raise last


def _make_account(sess) -> dict:
    """Create ONE account+character via the real chargen wizard, but do NOT
    enter the game — leave us with a known username/password we can log in with
    fresh (so the char-select PICKER appears on the next login)."""
    _relax_timeouts(sess)
    suffix = random.randint(100000, 999999)
    name = f"Brk{suffix}"
    user, pw = f"brk{suffix}", "testpass123"
    p = sess.page
    _goto(sess, "/chargen")
    p.wait_for_selector("#templateCards .card[data-key]", timeout=40000)
    drive_wizard(p, name, user, pw)
    p.wait_for_selector("#successOverlay", state="visible", timeout=25000)
    return {"name": name, "user": user, "pw": pw}


def _open_login(sess) -> None:
    """Load the client and wait for the login form to be visible/usable.

    NOTE: the socket var (`ws`) is IIFE-local — `window.ws` is intentionally NOT
    exposed (client.html:5442 says window.* is debug-only). So we cannot poll the
    socket directly; instead we wait for the boot overlay to flip to the LOGIN
    state, which only happens inside ws.onopen's +600ms timer — i.e. it IS the
    socket-open signal. The #boot-state-login div's display flips from none to ''.
    """
    _goto(sess, "/client.html")
    sess.page.wait_for_selector("#login-user", state="visible", timeout=45000)
    sess.page.wait_for_function(
        "() => { var el = document.getElementById('boot-state-login');"
        " return el && getComputedStyle(el).display !== 'none'; }",
        timeout=45000)
    sess.page.wait_for_timeout(400)  # let onopen's resize/probe settle


def _login_to_charselect(sess, user: str, pw: str) -> None:
    """Sign in with a known account that already has >=1 char so the PICKER
    (#boot-state-charselect) renders rather than going straight into the game."""
    _open_login(sess)
    sess.page.fill("#login-user", user)
    sess.page.fill("#login-pass", pw)
    sess.page.click("#login-submit")
    sess.page.wait_for_selector("#boot-state-charselect", state="visible", timeout=45000)
    sess.page.wait_for_selector("#charselect-list > *", timeout=45000)


def _login_error_text(sess) -> str:
    el = sess.page.query_selector("#login-error")
    return (el.text_content() or "").strip() if el else ""


# ── scenarios ───────────────────────────────────────────────────────────────

def s_empty_and_whitespace_creds(sess):
    """Submit with empty fields and whitespace-only fields. Expect the inline
    'Both fields required.' validation, NO websocket send, and the form must
    stay usable afterwards (a real account can still log in)."""
    acct = _make_account(sess)
    _open_login(sess)

    # 1) totally empty -> client-side validation, no send
    sess.page.click("#login-submit")
    sess.page.wait_for_timeout(300)
    assert "required" in _login_error_text(sess).lower(), \
        f"empty submit gave no 'required' error: {_login_error_text(sess)!r}"

    # 2) whitespace-only username (trimmed to empty) + a password
    sess.page.fill("#login-user", "    ")
    sess.page.fill("#login-pass", "x")
    sess.page.click("#login-submit")
    sess.page.wait_for_timeout(300)
    assert "required" in _login_error_text(sess).lower(), \
        "whitespace-only username should trim to empty and be rejected client-side"

    # POST-CONDITION: the form still works -> a real account logs in cleanly.
    sess.page.fill("#login-user", acct["user"])
    sess.page.fill("#login-pass", acct["pw"])
    sess.page.click("#login-submit")
    sess.page.wait_for_selector("#boot-state-charselect", state="visible", timeout=45000)


def s_injection_shaped_creds(sess):
    """Wrong creds shaped like SQLi / XSS / oversized / control-char payloads.
    The server must reject them (auth_status ok:false) WITHOUT a 5xx or a JS
    exception, the inline error must surface, and the form must remain usable."""
    _open_login(sess)
    payloads = [
        ("' OR '1'='1", "' OR '1'='1"),                 # SQLi-shaped
        ("admin'--", "whatever"),                        # SQLi comment
        ("<script>alert(1)</script>", "<img src=x onerror=alert(1)>"),  # XSS-shaped
        ("a" * 5000, "b" * 5000),                        # oversized
        ("nul\x00byte", "pw\x07bell"),                   # control chars
        ("user with spaces", "pass with spaces"),        # split-mangling
        ("名前\U0001f600", "пароль"),                     # unicode/emoji
    ]
    for user, pw in payloads:
        sess.page.fill("#login-user", user)
        sess.page.fill("#login-pass", pw)
        sess.page.click("#login-submit")
        sess.page.wait_for_timeout(450)
        # must NOT have advanced to charselect on a bad credential
        cs = sess.page.query_selector("#boot-state-charselect")
        cs_visible = cs and cs.is_visible()
        assert not cs_visible, \
            f"bogus credential {user[:20]!r} unexpectedly reached charselect"

    # POST-CONDITION: after all that junk the form is still alive — empty submit
    # still yields the client-side validation (handler not wedged).
    sess.page.fill("#login-user", "")
    sess.page.fill("#login-pass", "")
    sess.page.click("#login-submit")
    sess.page.wait_for_timeout(300)
    assert "required" in _login_error_text(sess).lower(), \
        "login handler appears wedged after injection-shaped attempts"


def s_rapid_double_submit(sess):
    """Hammer the CONNECT button many times with valid creds (no settle) to
    provoke a double-`connect` race / a stuck 'awaitingAuth' / a second auth
    while the first is in flight. Expect to land in charselect exactly once and
    with a live socket."""
    acct = _make_account(sess)
    _open_login(sess)
    # Fire 8 submit clicks SYNCHRONOUSLY in one JS turn — before the event loop
    # yields to process any auth_status / char_select reply — so all 8 `connect`
    # lines hit one OPEN socket back-to-back (the genuine double-submit race). We
    # do this in-page because Playwright's .click() waits for stability between
    # clicks, by which point the button has already transitioned away on success.
    # submitLogin() clears #login-pass each call, so we re-set it each iteration.
    sess.page.evaluate(
        """({user, pw}) => {
            var btn = document.getElementById('login-submit');
            for (var i = 0; i < 8; i++) {
                document.getElementById('login-user').value = user;
                document.getElementById('login-pass').value = pw;
                btn.click();
            }
        }""",
        {"user": acct["user"], "pw": acct["pw"]},
    )
    sess.page.wait_for_selector("#boot-state-charselect", state="visible", timeout=45000)
    sess.page.wait_for_timeout(1200)
    # Reaching the picker proves the socket round-tripped. Post-condition: the
    # picker is coherent — exactly the one character we made, no duplicate rows
    # from the 8 stacked `connect` lines, and the row is clickable (selecting it
    # enters the game). That exercises the double-submit didn't corrupt state.
    n = sess.page.eval_on_selector_all("#charselect-list > *", "els => els.length")
    assert n == 1, f"expected exactly 1 char row after rapid submit, got {n} " \
        "(duplicate/corrupted picker from stacked connect lines?)"
    sess.page.click("#charselect-list > *")
    sess.page.wait_for_selector("#cmd-input-ground", state="visible", timeout=45000)


def s_select_nonexistent_character(sess):
    """THE stuck-state probe. selectCharacter() (client.html) paints
    '▸ ENTERING GAME AS …' the instant you click a row and sends
    `__char_select__<id>` over the socket. The server's __char_select__ loop does
    `int(line.split('__')[-1])` and, if NO character matches that id, SILENTLY
    ignores it — no break, no error reply, no state change. So a client that ever
    sends an id not on the account is wedged on the 'entering' splash forever.

    The legit UI only wires real ids, so to exercise the SERVER contract we drive
    a raw second WebSocket from page JS: log the account in over it, drain the
    char_select payload, then send a bogus id and watch for ANY reply. A correct
    server should reject/redraw; the silent-ignore is the finding. We also assert
    a VALID id over the same raw socket DOES enter the game (control), proving the
    bogus-id silence is specifically the unknown-id path, not a dead socket."""
    acct = _make_account(sess)
    _open_login(sess)  # need a page with same-origin so the WS handshake is allowed

    # Run the whole raw-socket dialogue inside the page so it shares origin/cookies.
    result = sess.page.evaluate(
        """async ({user, pw}) => {
        function open() {
          return new Promise((res, rej) => {
            const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
            const s = new WebSocket(proto + '//' + location.host + '/ws');
            s.__msgs = [];
            s.onmessage = (e) => s.__msgs.push(e.data);
            s.onopen = () => res(s);
            s.onerror = (e) => rej(new Error('ws error'));
            setTimeout(() => rej(new Error('ws open timeout')), 15000);
          });
        }
        function sleep(ms){ return new Promise(r=>setTimeout(r,ms)); }
        function lastTypes(s){
          return s.__msgs.map(m => { try { return JSON.parse(m).type; }
                                     catch(_) { return 'text'; } });
        }
        const s = await open();
        // authenticate
        s.send(JSON.stringify({ input: 'connect ' + user + ' ' + pw }));
        // wait for the char_select payload to arrive
        let realId = null;
        for (let i = 0; i < 40 && realId === null; i++) {
          await sleep(250);
          for (const m of s.__msgs) {
            try {
              const o = JSON.parse(m);
              if (o.type === 'char_select' && o.characters && o.characters.length) {
                realId = o.characters[0].id;
              }
            } catch(_) {}
          }
        }
        if (realId === null) return { phase: 'auth', error: 'never got char_select' };

        // ── send a BOGUS id and watch for any reply for 3s ──
        const beforeBogus = s.__msgs.length;
        s.send(JSON.stringify({ input: '__char_select__999999999' }));
        await sleep(3000);
        const bogusReplies = s.__msgs.slice(beforeBogus);
        const bogusTypes = bogusReplies.map(m => {
          try { return JSON.parse(m).type; } catch(_) { return 'text'; } });

        // ── control: send the REAL id, expect to enter the game (hud_update) ──
        const beforeReal = s.__msgs.length;
        s.send(JSON.stringify({ input: '__char_select__' + realId }));
        let gotHud = false;
        for (let i = 0; i < 40 && !gotHud; i++) {
          await sleep(250);
          for (const m of s.__msgs.slice(beforeReal)) {
            try { if (JSON.parse(m).type === 'hud_update') gotHud = true; } catch(_) {}
          }
        }
        try { s.close(); } catch(_) {}
        return {
          realId,
          bogusReplyCount: bogusReplies.length,
          bogusTypes,
          validIdEnteredGame: gotHud,
        };
        }""",
        {"user": acct["user"], "pw": acct["pw"]},
    )

    # Control must hold: the valid id DOES enter the game (socket & path healthy).
    assert result.get("validIdEnteredGame"), (
        f"control failed — valid __char_select__ did not enter game: {result!r}. "
        "Cannot isolate the unknown-id behaviour."
    )
    # The finding: a bogus id elicited NO reply at all — the player who somehow
    # sends a stale/foreign id is stranded on the 'ENTERING GAME' splash with no
    # error and no recovery. Assert NON-silence to flag it.
    assert result.get("bogusReplyCount", 0) > 0, (
        "SILENT NO-OP: server received __char_select__999999999 (an id not on the "
        "account) and sent ZERO reply — no error, no re-draw, no disconnect. The "
        "client's selectCharacter() has already painted the 'ENTERING GAME' splash, "
        "so the player is permanently stuck with no feedback. "
        f"(control: a valid id DID enter the game) raw={result!r}"
    )


def s_new_char_button_and_logout_spam(sess):
    """On the picker, spam the +NEW CHARACTER button and the LOGOUT button.
    +NEW fires __request_chargen__ over the WS (server replies chargen_start);
    repeated clicks must not throw or duplicate. LOGOUT must cleanly drop to boot
    and re-offer the login form (not leave a dead socket + visible picker)."""
    acct = _make_account(sess)
    _login_to_charselect(sess, acct["user"], acct["pw"])

    newbtn = sess.page.query_selector("#charselect-new")
    assert newbtn and newbtn.is_visible(), "+NEW button missing (can_create false?)"
    for _ in range(6):
        try:
            newbtn.click(timeout=1000)
        except Exception:
            break  # button may navigate/overlay; spamming a stale node is fine
    sess.page.wait_for_timeout(800)

    # Reload back to a known login, then exercise LOGOUT from the picker.
    _login_to_charselect(sess, acct["user"], acct["pw"])
    sess.page.click("#charselect-logout")
    sess.page.wait_for_timeout(1200)
    # After logout the picker must NOT still be the visible state; the client
    # should be back on boot/login (logout() resets to boot then reconnects).
    cs = sess.page.query_selector("#boot-state-charselect")
    assert not (cs and cs.is_visible()), \
        "charselect still visible after LOGOUT — logout left a stuck picker"


def s_reload_mid_login(sess):
    """Submit valid creds and immediately reload the page mid-auth. A reload must
    yield a clean fresh login form (fresh socket), not a half-initialised state,
    a dead socket, or a console.error from a torn-down handler."""
    acct = _make_account(sess)
    _open_login(sess)
    sess.page.fill("#login-user", acct["user"])
    sess.page.fill("#login-pass", acct["pw"])
    sess.page.click("#login-submit")
    # reload almost immediately (race the auth round-trip)
    sess.page.wait_for_timeout(60)
    sess.page.reload(wait_until="domcontentloaded")
    # fresh form must come back up and reconnect (boot flips to login on ws.onopen)
    sess.page.wait_for_selector("#login-user", state="visible", timeout=45000)
    sess.page.wait_for_function(
        "() => { var el = document.getElementById('boot-state-login');"
        " return el && getComputedStyle(el).display !== 'none'; }",
        timeout=45000)
    sess.page.wait_for_timeout(400)
    # and it must still be functional: log in for real
    sess.page.fill("#login-user", acct["user"])
    sess.page.fill("#login-pass", acct["pw"])
    sess.page.click("#login-submit")
    sess.page.wait_for_selector("#boot-state-charselect", state="visible", timeout=45000)


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "auth",
        [
            s_empty_and_whitespace_creds,
            s_injection_shaped_creds,
            s_rapid_double_submit,
            s_select_nonexistent_character,
            s_new_char_button_and_logout_spam,
            s_reload_mid_login,
        ],
    ))
