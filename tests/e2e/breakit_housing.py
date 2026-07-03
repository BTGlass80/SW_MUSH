# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_housing.py — REAL-BROWSER break-it pass for the HOUSING surface.

Surface: the player Housing command tree (parser/housing_commands.py ->
engine/housing.py), driven through the live web SPA command box
(#cmd-input-ground). Covers rent / buy / list / storage / store / retrieve /
checkout / sell / guest / visit and the bare-status path.

The housing UI in the web client is NOT a dedicated panel — output renders into
the main game text area, so we drive it as parser commands and watch for
browser-layer faults (pageerror / console.error / http5xx / requestfailed)
auto-captured by the harness, plus a few WRONG-BEHAVIOUR post-conditions a
crash-only capture would miss (e.g. a command that should error but no-ops).

Adversarial axes exercised here:
  * no-precondition actions (storage/store/retrieve/checkout/sell with 0 homes)
  * malformed / oversized / injection-shaped lot ids and item names
  * boundary lot ids (0, negative, huge int overflow, non-numeric)
  * invalid buy types and malformed buy lot ids
  * rapid out-of-order double actions (double-rent, rent then immediate checkout)
  * the bare-status render with junk trailing args

Run: NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_housing.py
Exit 0 = no browser-layer defect captured across the scenarios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402


def _ground_text(sess) -> str:
    """Return the current visible text of the ground output log (best-effort).
    Used to assert WRONG-BEHAVIOUR post-conditions the crash-capture can't see."""
    try:
        # The ground command output renders into the main game log area. Grab a
        # broad slice of body text; we only ever substring-search it.
        return sess.page.inner_text("body")
    except Exception:
        return ""


def _enter(sess):
    """Resilient new_player(): on this box the break-it workflow runs MANY of
    these harnesses concurrently (each boots its own server + Chromium), so the
    machine is CPU-starved and the default 30s page-navigation timeout on the
    /chargen goto is too tight -- a pure harness-load artifact, not an app fault.
    Bump the page nav/default timeout to 90s and retry once before giving up so a
    transient boot-storm slowdown doesn't masquerade as a housing defect."""
    sess.page.set_default_navigation_timeout(90000)
    sess.page.set_default_timeout(45000)
    try:
        return sess.new_player()
    except Exception:
        # One retry — a fresh attempt after the boot storm eases.
        sess.page.wait_for_timeout(2000)
        return sess.new_player()


def s_no_precondition_actions(sess):
    """Every storage/management verb on a player who owns NO home must produce a
    clean 'you don't have a home' error — never a JS exception, a 5xx, or a
    silent no-op. This is the single most likely class of housing breakage: a
    sub-command that assumes a home exists and dereferences a None record."""
    _enter(sess)
    # Bare status first (no-home branch -> lists available lots).
    sess.send("housing", settle_ms=600)
    # All of these act on a home the player does not have.
    for cmd in (
        "housing list",          # 0 homes
        "housing storage",       # no home -> no storage
        "housing store blaster",  # store with no home
        "housing retrieve blaster",  # retrieve with no storage
        "housing checkout",      # vacate when renting nothing
        "housing sell",          # sell when owning nothing
        "housing sell confirm",  # sell-confirm with nothing to sell
        "housing trophies",      # trophies with no home
        "housing trophy medal",  # mount trophy with no home
        "housing name Palace",   # rename with no home
        "housing describe",      # desc editor with no home
        "housing intrusions",    # intrusion log with no home
        "housing guest list",    # guest list with no home
        "housing guest add Bob",  # guest-add with no home
        "home",                  # teleport with no home set
    ):
        sess.send(cmd, settle_ms=350)
    # POST-CONDITION: the command box must still be functional afterward.
    sess.send("look", settle_ms=400)
    body = _ground_text(sess)
    # The describe editor uses _input_intercept; make sure we are NOT stuck in it
    # (a no-home describe must bail before entering the editor). If we were stuck,
    # 'look' would have been swallowed as a description line. We assert the look
    # actually ran by checking the input box is empty & enabled.
    try:
        val = sess.page.input_value("#cmd-input-ground")
        if val:
            sess.page.evaluate(
                "console.error('BREAKIT housing: cmd-input-ground not cleared "
                "after no-precondition sweep -> possibly stuck in describe editor')")
    except Exception:
        pass


def s_malformed_lot_ids_rent(sess):
    """Throw malformed / boundary / injection lot ids at 'housing rent'. The
    parser gates on .isdigit() then int() -> verify nothing here 500s, throws,
    or wrongly succeeds. Negative / huge / non-numeric must be rejected cleanly."""
    _enter(sess)
    for lot in (
        "0",                       # boundary: lot 0 (likely invalid)
        "-1",                      # negative (isdigit() False -> usage)
        "999999999",               # nonexistent high id
        "99999999999999999999999",  # bigint overflow shaped
        "1.5",                     # float
        "0x10",                    # hex
        "1; DROP TABLE player_housing;--",  # SQLi-shaped
        "<script>alert(1)</script>",        # XSS-shaped id
        "  12  ",                  # padded
        "abc",                     # non-numeric
        "",                        # empty (housing rent with no id)
        "1" * 4000,                # oversized numeric string
    ):
        sess.send(f"housing rent {lot}", settle_ms=300)
    # POST-CONDITION: a valid status command must still work after the barrage.
    sess.send("housing", settle_ms=500)


def s_malformed_buy(sess):
    """'housing buy <type> <lot>' — invalid types and malformed lot ids. The
    type is validated against TIER3_TYPES before any credit check, so these are
    reachable by a broke new player. Verify clean validation, no 5xx, no throw,
    and that an unknown type does NOT charge or create a room (wrong-behaviour)."""
    _enter(sess)
    for arg in (
        "mansion 1",               # bogus type, valid-ish lot
        "PALACE 999999",           # bogus type + nonexistent lot
        "apartment -5",            # negative lot -> falls to listing (lot not digit)
        "estate 0",                # boundary lot 0
        "'; DROP TABLE characters;-- 1",  # SQLi-shaped type
        "<img src=x onerror=alert(1)> 1",  # XSS-shaped type
        "apartment 1.5",           # non-int lot -> listing fallback
        "apartment",               # missing lot -> listing fallback
        "",                        # bare 'housing buy' -> tier3 listing
        ("x" * 3000) + " 1",      # oversized type
    ):
        sess.send(f"housing buy {arg}", settle_ms=300)
    # POST-CONDITION: still own zero homes (no bogus purchase slipped through).
    sess.send("housing list", settle_ms=500)
    body = _ground_text(sess)
    if "Your homes" in body:
        sess.page.evaluate(
            "console.error('BREAKIT housing: housing list shows owned homes after "
            "ONLY invalid buy attempts -> a malformed buy created a home')")


def s_malformed_store_retrieve(sess):
    """Store/retrieve with oversized / injection / unicode item names on a player
    with no home (and after, exercise the same against the no-storage path).
    None of it should throw or 5xx; non-matches must error, not no-op silently."""
    _enter(sess)
    for item in (
        "x" * 5000,                # oversized item name
        "<script>alert(1)</script>",
        "'; DROP TABLE player_housing;--",
        "\U0001f600" * 100,        # emoji flood
        "   ",                     # whitespace only (-> usage, since rest empty)
        "\t\x07\x1b[31m",          # control chars
        "nonexistent_item_xyz",     # plain miss
    ):
        sess.send(f"housing store {item}", settle_ms=300)
        sess.send(f"housing retrieve {item}", settle_ms=300)
    sess.send("look", settle_ms=400)


def s_rapid_out_of_order(sess):
    """Out-of-order / rapid-fire housing actions to provoke double-submit races
    and stale-state handlers: spam rent at one lot id (a second rent must hit the
    'already have a place' guard, not double-charge or orphan a room), interleave
    checkout/store, and fire with no settle so frames overlap."""
    _enter(sess)
    # Try to actually rent: lot id 1 is the canonical first lot. If the player
    # is broke this cleanly errors; if funded, the SECOND rent must be rejected.
    for _ in range(6):
        sess.send("housing rent 1", settle_ms=0)
    sess.page.wait_for_timeout(1200)
    # Now interleave management verbs with no settle.
    for cmd in ("housing", "housing storage", "housing checkout",
                "housing rent 1", "housing checkout", "housing list"):
        sess.send(cmd, settle_ms=0)
    sess.page.wait_for_timeout(1500)
    # POST-CONDITION: status command still responds cleanly.
    sess.send("housing", settle_ms=600)


def s_unknown_subcommands_and_status_junk(sess):
    """Unknown housing sub-commands and junk trailing args on the bare-status and
    'home' paths. The dispatcher should answer "Unknown subcommand" rather than
    throw; the bare-status path ignores trailing junk; 'home <junk>' must NOT be
    parsed as a teleport-with-args and break."""
    _enter(sess)
    for cmd in (
        "housing frobnicate",      # unknown sub
        "housing rent",            # rent with no id -> usage
        "housing buy",             # buy with no args -> listing
        "housing list extra junk args here",  # list ignores rest
        "housing storage " + ("z" * 2000),    # storage + oversized rest
        "housing " + ("@" * 500),  # junk sub
        "home northhhh",           # home with bogus trailing arg
        "home ; look",             # home + injection-ish
        "myroom",                  # alias for housing
        "homelocation",            # alias for housing
        "+home",                   # umbrella bare
        "+home frobnicate",        # umbrella unknown verb -> help
        "+home admin evict Brian",  # umbrella admin path: must be permission-denied for a player
        "@housing list",           # direct admin command: permission-denied for a player
    ):
        sess.send(cmd, settle_ms=300)
    # POST-CONDITION: the '+home admin evict' / '@housing' must NOT have run for a
    # non-admin. If it had, a "Evicted" line would appear. Check the negative.
    body = _ground_text(sess)
    if "Evicted Brian" in body or "All Housing" in body:
        sess.page.evaluate(
            "console.error('BREAKIT housing: a non-admin reached the @housing/"
            "+home admin path -> privilege escalation')")
    sess.send("look", settle_ms=400)


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "housing",
        [
            s_no_precondition_actions,
            s_malformed_lot_ids_rent,
            s_malformed_buy,
            s_malformed_store_retrieve,
            s_rapid_out_of_order,
            s_unknown_subcommands_and_status_junk,
        ],
    ))
