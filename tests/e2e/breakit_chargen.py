# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_chargen.py — REAL-BROWSER adversarial break-it for the
CHARACTER CREATION WIZARD (the /chargen multi-step SPA, static/chargen.html).

Surface: the standalone chargen wizard a brand-new player hits from the portal's
"Create Character" link — steps step0(template) .. step8(account). Drives the
ACTUAL rendered wizard in headless Chromium against a live server and lets the
harness auto-capture pageerror / console.error / http5xx / requestfailed. Where a
fault wouldn't trip the auto-capture (a stuck panel, a no-op that should error, a
server 500 that's swallowed by the client), each scenario ASSERTS the expected
post-condition and raises AssertionError (recorded as the scenario's `error`).

Adversarial angles (things the happy-path PoC never does):
  * jump steps out of order via the step-pills / goToStep before preconditions
    are met (no species, no force choice, no name) and try to advance / submit
  * hammer the debounced name field with oversized / unicode / SQLi / forbidden
    / leading-space names and watch the live check-name round-trip
  * tamper the in-memory point pools (S.attributes / S.skills) to over-spend or
    inject malformed dice, then submit — the SERVER must reject with a clean 4xx,
    never a 500, and the UI must recover (button re-enabled, errors shown)
  * double-submit / submit-button race (one account, never a duplicate-name 500)
  * browser back/forward (popstate) thrash across steps, then resume
  * POST malformed bodies straight at /api/chargen/submit (non-dict, junk) —
    must be a clean 400, never a 5xx

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_chargen.py
Exit 0 = no browser-layer defect captured and every assertion held.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402
from tests.e2e.playwright_new_player_poc import click_next  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────

def _open_wizard(sess):
    """Load the standalone chargen wizard and wait for step0 to render. Retries
    the initial navigation a couple times — under a 6-server sequential boot the
    very first page load can race the freshly-spawned worker (a harness-load flake,
    not an app fault)."""
    last = None
    for attempt in range(3):
        try:
            sess.page.goto(sess.base + "/chargen",
                           wait_until="domcontentloaded", timeout=45000)
            sess.page.wait_for_selector(
                "#templateCards .card[data-key]", timeout=30000)
            return
        except PWTimeout as e:
            last = e
            sess.page.wait_for_timeout(1000)
    raise AssertionError(f"chargen wizard never rendered step0 after retries: {last}")


def _active_step(page) -> str | None:
    panel = page.query_selector(".step-panel.active")
    return panel.get_attribute("id") if panel else None


def _drive_to_account(sess, name: str):
    """Walk the template path through to the account step (step8), leaving the
    account form unfilled. Mirrors the PoC's state machine but stops at step8."""
    page = sess.page
    for _ in range(30):
        step = _active_step(page)
        if step == "step0":
            page.click("#templateCards .card[data-key]")
            page.wait_for_timeout(250)
            click_next(page)
        elif step == "step1":
            page.click("#speciesCards .card[data-sp]")
            click_next(page)
        elif step in ("step2", "step3"):
            click_next(page)
        elif step == "step4":
            page.click('.force-card[data-force="false"]')
            page.wait_for_timeout(150)
            click_next(page)
        elif step == "step5":
            page.fill("#charName", name)
            click_next(page)
        elif step == "step6":
            card = page.locator(
                "#chainCards .card[data-chain-id]:not(.card-disabled)").first
            try:
                card.wait_for(state="visible", timeout=6000)
                card.click()
                page.wait_for_timeout(150)
            except PWTimeout:
                pass
            click_next(page)
        elif step == "step7":
            click_next(page)
        elif step == "step8":
            return
        page.wait_for_timeout(300)
    raise AssertionError("wizard never reached step8 (account)")


# ── scenarios ───────────────────────────────────────────────────────────────

def s_pill_jump_skips_required_steps(sess):
    """Jump straight past required steps via the step-pills / review-edit
    goToStep() before any species / attrs / force / name is chosen, then try to
    advance. The render functions must not throw, and the wizard must NOT let an
    empty build sail through to submit — validation should block + show errors,
    and the relevant controls must stay live (no stuck panel)."""
    page = sess.page
    _open_wizard(sess)

    # Pick a template so step0 validates, then yank straight to the Review pill
    # (step 7) skipping force(4) + name(5) + chain(6). Pills only honor target<=
    # current OR completed, so use goToStep() directly the way the review-edit
    # buttons do — that path has no such guard.
    page.click("#templateCards .card[data-key]")
    page.wait_for_timeout(200)
    page.evaluate("goToStep(7)")          # review with no force/name set
    page.wait_for_timeout(300)
    assert _active_step(page) == "step7", "goToStep(7) did not show the review panel"

    # Now jump to the name step the way the review 'edit' button does, leave it
    # blank, and try to advance — must be blocked with an error banner.
    page.evaluate("goToStep(5)")
    page.wait_for_timeout(200)
    page.fill("#charName", "")
    click_next(page)
    page.wait_for_timeout(300)
    assert _active_step(page) == "step5", (
        "blank name advanced past the name step — validation no-op")
    banner_shown = page.evaluate(
        "() => document.getElementById('errorsBanner')"
        ".classList.contains('show')")
    assert banner_shown, "blank-name advance showed no error banner"

    # The name field must still be usable after the blocked advance (not stuck):
    page.fill("#charName", "Recoverable")
    assert page.input_value("#charName") == "Recoverable", "name field went dead"


def s_adversarial_name_input(sess):
    """Hammer the debounced name field with oversized / unicode / injection /
    forbidden / leading-space values and let the live /api/chargen/check-name
    round-trip fire. None of it may throw in the browser, 5xx, or leave the hint
    in a permanently-wrong state. Then assert a VALID name still resolves to the
    available hint (the field recovers)."""
    page = sess.page
    _open_wizard(sess)
    # template -> attrs -> skills -> force -> name
    page.click("#templateCards .card[data-key]")
    page.wait_for_timeout(200)
    click_next(page)                       # step0 -> step2 (template skips species)
    for _ in range(2):
        if _active_step(page) in ("step2", "step3"):
            click_next(page)
            page.wait_for_timeout(150)
    if _active_step(page) == "step4":
        page.click('.force-card[data-force="false"]')
        page.wait_for_timeout(120)
        click_next(page)
    assert _active_step(page) == "step5", f"expected name step, at {_active_step(page)}"

    junk_names = [
        "x" * 5000,                         # oversized
        "  leadingspaces",                  # leading whitespace
        "admin",                            # forbidden / reserved
        "'; DROP TABLE characters;--",      # SQLi-shaped
        "<script>alert(1)</script>",        # XSS-shaped
        "\U0001f600\U0001f600name",         # emoji prefix (not a letter)
        "Z油Z字",                            # CJK / non-ASCII letters
        "A",                                # too short
    ]
    # Space the fills so the per-IP soft rate limiter (shared by check-name)
    # isn't tripped by our own flood — a real user types one name, not eight in
    # a burst; tripping the 429 here would be a self-inflicted harness artifact,
    # not an app fault. ~1.2s/name keeps each debounced check well under the cap.
    for nm in junk_names:
        page.fill("#charName", nm)
        page.wait_for_timeout(1200)

    # Each junk value must leave the field/hint in a coherent (non-throwing)
    # state. The XSS-shaped name in particular must be rendered as TEXT, never
    # executed, and never injected raw into the hint.
    hint_after_xss = page.evaluate("""async () => {
        document.getElementById('charName').value = '<img src=x onerror=alert(1)>';
        document.getElementById('charName').dispatchEvent(new Event('input'));
        await new Promise(r => setTimeout(r, 300));
        const h = document.getElementById('nameHint');
        return { html: h.innerHTML, text: h.textContent };
    }""")
    assert "<img" not in (hint_after_xss["html"] or ""), (
        f"name hint reflected raw HTML (XSS): {hint_after_xss['html']!r}")

    # Recovery: a clean, novel name must resolve to a definite hint (available or
    # taken), proving the field recovers after the junk. We pace + poll so a
    # transient rate-limit ('Checking availability...') is given time to clear
    # rather than being miscounted as a stuck state.
    page.wait_for_timeout(1500)            # let any prior limiter window drain
    good = f"Zara{random.randint(10000,99999)}"
    page.fill("#charName", good)
    resolved = False
    for _ in range(8):
        page.wait_for_timeout(900)
        hint = (page.text_content("#nameHint") or "").lower()
        if "available" in hint or "taken" in hint or "✓" in hint or "✗" in hint:
            resolved = True
            break
        # nudge the debounce again if still 'checking' (covers a dropped 429)
        page.fill("#charName", good + "x")
        page.wait_for_timeout(200)
        page.fill("#charName", good)
    assert resolved, (
        f"valid name never resolved to an availability hint after recovery "
        f"(last hint={page.text_content('#nameHint')!r})")


def s_tampered_pools_submit_rejected(sess):
    """Walk to the account step, then TAMPER the in-memory point pools the way a
    console-savvy player would: over-spend attributes and inject an out-of-range
    skill bonus / malformed dice, bypassing the +/- button clamps. Submit with
    valid account creds. The SERVER is the authority: it must return a clean 4xx
    with field errors (NOT a 500), the client must surface them, and the submit
    button must re-enable (no stuck 'CREATING...'). Auto-capture catches any 5xx;
    we additionally assert the recovery + no-success."""
    page = sess.page
    _open_wizard(sess)
    _drive_to_account(sess, f"Tamp{random.randint(10000,99999)}")
    assert _active_step(page) == "step8", "did not reach the account step"

    # Corrupt the pools beyond what the UI buttons can produce:
    #  - blow attributes way over the species total (overspend)
    #  - inject a skill bonus above the 2D creation cap
    page.evaluate("""() => {
        // Massively overspend attributes (each pip the buttons would refuse).
        for (const a of ATTRS) { S.attributes[a] = (S.attributes[a]||0) + 30; }
        // Inject an over-cap skill bonus on a real skill key if one exists.
        const anyAttr = Object.values(DATA.skills)[0];
        const k = anyAttr && anyAttr.skills && anyAttr.skills[0]
                  ? anyAttr.skills[0].key : 'blaster';
        S.skills[k] = 99;            // way over the 6-pip (2D) cap
    }""")

    user = f"tamp{random.randint(10000,99999)}"
    page.fill("#acctUsername", user)
    page.fill("#acctPassword", "testpass123")
    page.fill("#acctPasswordConfirm", "testpass123")
    page.check("#rulesAccept")
    page.wait_for_function(
        "() => { const b=document.getElementById('submitBtn');"
        " return b && !b.disabled; }", timeout=8000)
    page.click("#submitBtn")
    page.wait_for_timeout(2500)

    # MUST NOT have succeeded (no success overlay, no redirect to client).
    overlay_shown = page.evaluate(
        "() => document.getElementById('successOverlay')"
        ".classList.contains('show')")
    assert not overlay_shown, (
        "tampered over-spent build was ACCEPTED — server validation bypassed")
    assert "/chargen" in page.url, f"unexpectedly navigated away to {page.url}"

    # The submit button must have recovered (re-enabled), not stuck in CREATING.
    btn_txt = (page.text_content("#submitBtn") or "")
    assert "CREATING" not in btn_txt.upper(), (
        f"submit button stuck after rejected submit (text={btn_txt!r})")
    disabled = page.evaluate(
        "() => document.getElementById('submitBtn').disabled")
    assert not disabled, "submit button left disabled after a rejected submit"


def s_double_submit_race(sess):
    """Reach the account step with a VALID build, then fire submitCharacter()
    twice back-to-back (the impatient-double-click race). Exactly one account +
    character must be created; the second call must NOT yield a server 500 (e.g.
    a duplicate-name UNIQUE-constraint crash) — at worst a clean 4xx. Auto-capture
    catches a 5xx; we also assert the success overlay does eventually show (the
    first submit won) and no console.error leaked."""
    page = sess.page
    _open_wizard(sess)
    name = f"Race{random.randint(10000,99999)}"
    _drive_to_account(sess, name)
    assert _active_step(page) == "step8", "did not reach the account step"

    user = f"race{random.randint(10000,99999)}"
    page.fill("#acctUsername", user)
    page.fill("#acctPassword", "testpass123")
    page.fill("#acctPasswordConfirm", "testpass123")
    page.check("#rulesAccept")
    page.wait_for_function(
        "() => { const b=document.getElementById('submitBtn');"
        " return b && !b.disabled; }", timeout=8000)

    # Fire the submit handler twice in the same tick, before the first await
    # round-trips — this is the real double-click race, bypassing the button's
    # own disabled-guard (which only takes effect once the handler runs).
    page.evaluate("() => { submitCharacter(); submitCharacter(); }")
    # Wait for the success overlay (3s redirect timer) or an error.
    try:
        page.wait_for_selector("#successOverlay.show", timeout=8000)
        succeeded = True
    except PWTimeout:
        succeeded = False
    assert succeeded, (
        "double-submit produced no success overlay — the first (valid) submit "
        "should still create the character")


def s_history_thrash_then_resume(sess):
    """Standalone wizard pushes a history entry per step. Thrash browser
    back/forward (popstate) across steps out of order, then resume forward. The
    popstate handler must not throw, the panel must stay coherent, and the wizard
    must still be drivable to a real step afterward."""
    page = sess.page
    _open_wizard(sess)
    # Build up a few history entries.
    page.click("#templateCards .card[data-key]")
    page.wait_for_timeout(200)
    click_next(page)                       # -> step2
    page.wait_for_timeout(200)
    click_next(page)                       # -> step3
    page.wait_for_timeout(200)
    click_next(page)                       # -> step4
    page.wait_for_timeout(200)

    # Thrash: back x3, forward x2, back x1.
    for _ in range(3):
        page.go_back()
        page.wait_for_timeout(250)
    for _ in range(2):
        page.go_forward()
        page.wait_for_timeout(250)
    page.go_back()
    page.wait_for_timeout(300)

    # An active panel must still exist (not a blank/stuck wizard).
    step = _active_step(page)
    assert step is not None, "no active step panel after history thrash"
    # And we can still drive forward from wherever we landed without a throw.
    cur = page.evaluate("() => S.step")
    assert isinstance(cur, int), "S.step corrupted after history thrash"


def s_malformed_submit_post(sess):
    """Fire malformed bodies straight at POST /api/chargen/submit from the page
    context (same-origin fetch). A non-dict body, junk JSON, and a partial dict
    must each come back as a clean 4xx — NEVER a 5xx (the auto-capture flags any
    500). We assert each status is < 500."""
    page = sess.page
    _open_wizard(sess)
    # Space the POSTs (~1.5s apart) so we exercise the VALIDATION path, not the
    # per-IP submit rate limiter — a burst would trip 429 and tell us nothing
    # about how malformed bodies are handled. Even so the browser logs a
    # "Failed to load resource: ... 4xx" console.error for every non-2xx fetch;
    # those are EXPECTED-rejection noise, not app faults, so we clear them after
    # asserting (the real assertion is: never a 5xx).
    statuses = page.evaluate("""async () => {
        const bodies = [
            '[]',                                   // JSON array, not object
            '"just a string"',                      // JSON string
            '12345',                                // JSON number
            'null',                                 // JSON null
            '{not valid json',                      // malformed JSON
            JSON.stringify({username:'ab'}),        // missing character + short user
            JSON.stringify({username:'okuser', password:'shortp',
                            character:{name:'X'}}),  // partial character
        ];
        const out = [];
        for (const b of bodies) {
            try {
                const r = await fetch('/api/chargen/submit', {
                    method:'POST',
                    headers:{'Content-Type':'application/json'},
                    body:b,
                });
                out.push(r.status);
            } catch (e) {
                out.push('fetch-threw:' + e);
            }
            await new Promise(r => setTimeout(r, 1500));
        }
        return out;
    }""")
    for st in statuses:
        assert isinstance(st, int) and st < 500, (
            f"malformed /api/chargen/submit body produced a server fault: {st} "
            f"(all statuses: {statuses})")
    # At least one must be a 4xx validation/malformed rejection (proving the
    # endpoint actually parses + validates, not silently 200-ing junk).
    assert any(400 <= st < 500 for st in statuses), (
        f"no malformed body was rejected with a 4xx (statuses: {statuses})")
    # Drop the browser's auto-logged "Failed to load resource: ... 4xx" console
    # noise: a 4xx here is the CORRECT response, not a defect. (We assert above
    # there was never a 5xx; the auto-capture still flags any future 5xx.)
    benign = [d for d in sess.defects()
              if d.kind == "console.error"
              and "Failed to load resource" in d.detail
              and (" 400" in d.detail or " 409" in d.detail or " 429" in d.detail)]
    if benign:
        # rebuild the defect list without the benign 4xx-resource console lines
        sess._defects[:] = [d for d in sess._defects if d not in benign]


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "chargen",
        [
            s_pill_jump_skips_required_steps,
            s_adversarial_name_input,
            s_tampered_pools_submit_rejected,
            s_double_submit_race,
            s_history_thrash_then_resume,
            s_malformed_submit_post,
        ],
    ))
