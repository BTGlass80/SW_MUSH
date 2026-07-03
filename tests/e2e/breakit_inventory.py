# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_inventory.py — adversarial REAL-BROWSER break-it pass for the
INVENTORY + EQUIPMENT surface (get / drop / wear / wield / remove / equipment +
the inventory modal + the EQUIPPED side panel).

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_inventory.py
Exit 0 = no browser-layer defect captured AND no scenario assertion tripped.

What this drives that the happy path never does:
  * the INV quick-action button (does it actually open the modal?)
  * malformed / oversized / injection-shaped equip/wear/remove args
  * rapid out-of-order wear/remove/equip/unequip (client races, stuck panel)
  * get/drop stubs with junk args
  * clicking the live modal's per-item buttons (EQUIP / LOOK / REMOVE) and the
    backdrop / re-open path (stuck-modal hunt)

Auto-capture (pageerror / console.error / http5xx / requestfailed) covers the JS
faults. A handful of WRONG-BEHAVIOR checks that auto-capture can't see are
asserted directly and, on failure, recorded with a clear BREAKIT_WRONG marker so
the JSON report carries them out.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from playwright.sync_api import TimeoutError as PWTimeout  # noqa: E402
from tests.e2e.breakit_harness import BreakItSession, run_scenarios  # noqa: E402


# ── helpers ──────────────────────────────────────────────────────────────────

def _new_player(sess, attempts: int = 2):
    """new_player() with a retry — under sequential boot load the portal goto can
    stall (a harness/box artifact, not an app bug). Retry once before giving up so
    a load hiccup doesn't masquerade as a scenario failure."""
    last = None
    for i in range(attempts):
        try:
            return sess.new_player()
        except PWTimeout as e:
            last = e
            try:
                sess.page.wait_for_timeout(1500)
            except Exception:
                pass
    raise last

def _pose_text(sess) -> str:
    """Full text of the ground pose log (where server text lines land)."""
    try:
        return sess.page.inner_text("#pose-log")
    except Exception:
        return ""


def _modal_open(sess) -> bool:
    """True iff the inventory modal panel is showing."""
    try:
        cls = sess.page.get_attribute("#inv-modal", "class") or ""
        return "show" in cls.split()
    except Exception:
        return False


def _record_wrong(sess, detail: str) -> None:
    """Surface a wrong-behavior finding the passive capture can't see.

    We emit it through console.error so the harness' own listener records it as a
    captured defect in the JSON report (kind console.error, prefixed BREAKIT_WRONG
    so the human reader can tell it apart from genuine app console spam)."""
    sess.page.evaluate(
        "(m) => console.error('BREAKIT_WRONG ' + m)", detail)
    sess.page.wait_for_timeout(60)


def _settle_in_game(sess, timeout_ms: int = 12000) -> None:
    """Wait for the boot/connect overlay to clear before driving commands. Under a
    loaded box the splash can linger past 'in the game' and intercept the first
    clicks/sends — waiting for it avoids a timing-only flake that isn't an app
    fault."""
    try:
        sess.page.wait_for_selector(
            "#boot-overlay:not(.show)", timeout=timeout_ms)
    except Exception:
        # Fall back to a fixed pause; the overlay may use a different class path.
        try:
            sess.page.wait_for_timeout(1200)
        except Exception:
            pass


def _dismiss_modal(sess) -> None:
    """Force any open inventory modal closed via its own JS handler (not a click —
    a legitimately-open modal overlay intercepts pointer events, which is correct,
    not a wedge)."""
    try:
        sess.page.evaluate(
            "() => { if (window.closeInventoryModal) window.closeInventoryModal(); }")
        sess.page.wait_for_timeout(120)
    except Exception:
        pass


def _cmd_box_alive(sess) -> bool:
    """The ground command input must still accept text after an adversarial run —
    proves the UI didn't wedge. Dismisses any open modal first (an open modal
    legitimately intercepts clicks; that's not a wedged box)."""
    try:
        _dismiss_modal(sess)
        inp = sess.page.query_selector("#cmd-input-ground")
        if not inp:
            return False
        sess.page.fill("#cmd-input-ground", "look")
        ok = (sess.page.input_value("#cmd-input-ground") == "look")
        sess.page.fill("#cmd-input-ground", "")
        return ok
    except Exception:
        return False


# ── scenarios ─────────────────────────────────────────────────────────────────

def s_inv_quickaction_button(sess):
    """HEADLINE HUNT: the INV quick-action button.

    The button is markup `data-qa="INV" data-cmd="inventory" data-action="send"`,
    so clicking it sends the literal command `inventory`. The server's only
    inventory verb is `+inv` (bare `inventory`/`inv`/`i` were deleted in the
    command-syntax rework), so `inventory` is an UNKNOWN command — the modal never
    opens and the player gets `Huh? Unknown command: 'inventory'`. Assert the
    modal opens; if it doesn't, record the wrong behavior."""
    _new_player(sess)
    _settle_in_game(sess)
    sess.page.wait_for_timeout(400)
    btn = sess.page.query_selector('.qa-btn[data-qa="INV"]')
    if btn is None:
        _record_wrong(sess, "INV quick-action button not found in qa-row")
        return
    btn.click()
    sess.page.wait_for_timeout(900)
    if not _modal_open(sess):
        pose = _pose_text(sess)
        sig = "Huh? Unknown command" if "Huh? Unknown command" in pose else "(no unknown-command line)"
        _record_wrong(
            sess,
            "INV quick-action button did NOT open the inventory modal. "
            "It sends data-cmd='inventory', but the server command is '+inv' "
            f"(bare 'inventory' is unregistered). Server replied: {sig}.")
    # The command box must still work either way.
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after INV button click")


def s_inv_modal_open_close_cycle(sess):
    """The REAL inventory verb (`+inv`) must open the modal, and open/close/re-open
    must not wedge it. Sends `+inv` (triggers the inventory_state push), checks the
    modal opens, closes via the X, re-opens, closes via backdrop, re-opens via the
    command again. Stuck-modal hunt."""
    _new_player(sess)
    _settle_in_game(sess)
    sess.send("+inv", settle_ms=900)
    if not _modal_open(sess):
        _record_wrong(sess, "`+inv` did not open the inventory modal at all")
        return
    # Close via the X button.
    sess.page.click("#inv-modal .inv-modal-close")
    sess.page.wait_for_timeout(400)
    if _modal_open(sess):
        _record_wrong(sess, "inventory modal stuck OPEN after clicking the close (X) button")
    # Re-open via command, close via backdrop overlay click.
    sess.send("+inv", settle_ms=800)
    if not _modal_open(sess):
        _record_wrong(sess, "inventory modal did not RE-open after first close")
        return
    sess.page.click("#inv-modal-overlay", position={"x": 8, "y": 8})
    sess.page.wait_for_timeout(400)
    if _modal_open(sess):
        _record_wrong(sess, "inventory modal stuck OPEN after backdrop click")
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after inventory modal cycle")


def s_adversarial_equip_args(sess):
    """Throw malformed / oversized / injection-shaped / wrong-slot args at the
    equip/wear/remove/unequip verbs. None should produce a JS exception, a 5xx, or
    a console.error; each should refuse gracefully. Also verifies the command box
    survives."""
    _new_player(sess)
    _settle_in_game(sess)
    for junk in (
        "equip nonexistent_blaster_9000",          # no such weapon
        "wield a vibroblade that does not exist",   # alias, missing item
        "wear the_one_ring_of_power",               # no such armor
        "equip " + "z" * 4000,                       # oversized weapon name
        "wear " + "armor " * 500,                    # oversized armor name
        "equip <script>alert('x')</script>",        # XSS-shaped
        "wear '; DROP TABLE characters;--",         # SQLi-shaped
        "remove leg",                                # remove non-armor target
        "remove",                                    # remove with no arg
        "unequip",                                   # unequip with nothing equipped
        "wear \t\x07\x1b[31mbantha hide",           # control chars + ANSI
        "equip \U0001f5e1\U0001f5e1\U0001f5e1",      # emoji "weapon"
    ):
        sess.send(junk, settle_ms=300)
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after adversarial equip/wear args")


def s_rapid_wear_remove_equip(sess):
    """Fire wear/remove/equip/unequip out of order with NO settle, to provoke
    client-side races, double-submit handlers, or a corrupted EQUIPPED side panel.
    Then verify the EQUIPPED panel (#g-equip-list) is still coherently rendered and
    the command box is alive."""
    _new_player(sess)
    _settle_in_game(sess)
    seq = [
        "remove armor", "unequip", "remove armor", "unequip",   # remove nothing, twice
        "wear nothing", "equip nothing",                        # equip nothing
        "remove armor", "wear nothing", "unequip", "equip nothing",
        "remove armor", "unequip", "wear nothing", "equip nothing",
    ]
    for c in seq:
        sess.send(c, settle_ms=0)   # NO settle — provoke client-side races
    sess.page.wait_for_timeout(1800)
    # Now confirm the inventory_state panel push still works after the churn — but
    # send it on its own (the modal it opens legitimately covers the input, so we
    # never rapid-fire a command underneath it).
    sess.send("+inv", settle_ms=800)
    _dismiss_modal(sess)
    # EQUIPPED side panel must still hold a sane child structure, not a JS-error gap.
    try:
        n_children = sess.page.eval_on_selector(
            "#g-equip-list", "el => el.children.length")
        if n_children < 1:
            _record_wrong(sess, "#g-equip-list rendered with ZERO children after rapid equip churn")
    except Exception as e:
        _record_wrong(sess, f"could not read #g-equip-list after rapid churn: {e}")
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after rapid wear/remove churn")


def s_get_drop_stubs(sess):
    """get/drop are intentional stubs (Parsec has no ground items). Hit them with
    junk / oversized / injection args; they must respond with a graceful pointer,
    never a 5xx or JS exception, and never silently wedge the input."""
    _new_player(sess)
    _settle_in_game(sess)
    for junk in (
        "get",                         # bare
        "drop",                        # bare
        "get " + "x" * 4000,           # oversized
        "drop <script>alert(1)</script>",
        "take the entire galaxy",
        "grab '; DROP TABLE x;--",
        "discard \U0001f600" * 1,      # emoji
        "pickup nothing at all here",
    ):
        sess.send(junk, settle_ms=250)
    pose = _pose_text(sess)
    # The stub must actually answer (not be an unknown-command dead-end for the
    # bare verb). A graceful pointer mentions sell/unequip/give or examine/buy/loot.
    if "Huh? Unknown command: 'get'" in pose or "Huh? Unknown command: 'drop'" in pose:
        _record_wrong(sess, "get/drop bare verb fell through to 'Huh? Unknown command' instead of the stub pointer")
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after get/drop junk")


def s_modal_item_buttons(sess):
    """Open the live `+inv` modal and click its per-item controls (EQUIP / WEAR /
    LOOK / UNEQUIP / REMOVE) plus a carried-row select, to exercise the modal's
    button wiring and the staging path. A click must STAGE a command into the input
    (never auto-send, never throw) and must not leave the modal stuck."""
    _new_player(sess)
    _settle_in_game(sess)
    sess.send("+inv", settle_ms=900)
    if not _modal_open(sess):
        # Not a defect by itself here (covered by another scenario); just skip the
        # button checks since there's no modal to click.
        _record_wrong(sess, "`+inv` did not open modal — cannot exercise modal item buttons")
        return
    # Click every button rendered inside the modal body; none should throw or 5xx.
    btns = sess.page.query_selector_all("#inv-modal-body .inv-btn")
    for b in btns:
        try:
            b.click()
            sess.page.wait_for_timeout(150)
            # Clicking a staging button closes the modal and fills the input.
            if not _modal_open(sess):
                sess.send("+inv", settle_ms=700)  # re-open for the next button
        except Exception as e:
            _record_wrong(sess, f"clicking a modal .inv-btn threw: {e}")
            break
    # Click a carried row (select → delta footer re-render) if any exist.
    rows = sess.page.query_selector_all("#inv-modal-body .inv-row")
    if rows:
        try:
            rows[0].click()
            sess.page.wait_for_timeout(200)
            rows[0].click()  # toggle off
            sess.page.wait_for_timeout(200)
        except Exception as e:
            _record_wrong(sess, f"clicking a carried row threw: {e}")
    if not _cmd_box_alive(sess):
        _record_wrong(sess, "command box wedged after exercising modal item buttons")


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "inventory",
        [
            s_inv_quickaction_button,
            s_inv_modal_open_close_cycle,
            s_adversarial_equip_args,
            s_rapid_wear_remove_equip,
            s_get_drop_stubs,
            s_modal_item_buttons,
        ],
    ))
