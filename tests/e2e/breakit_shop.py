# -*- coding: utf-8 -*-
"""
tests/e2e/breakit_shop.py — REAL-BROWSER adversarial break-it for the SHOP /
VENDOR surface (buying & selling at vendors).

Surface map (verified against HEAD):
  * Parser, reachable by a fresh player:
      - `browse` / `browse <name>`          -> shop_state mode:'browse' push
      - `buy <slot> from <shop>`            -> _handle_buy_from_droid (vendor droid)
      - `buy <weapon>`                      -> NPC vendor (vendor-presence gated)
      - `sell <item>` / `sell <res> to <shop>`
      - `+commissary [buy|sell <key>]`      -> shop_state mode:'vendor' push
                                               (gated: must be in a faction;
                                                a fresh player is 'independent')
  * Web: the `shop_state` WS push -> handleShopState() -> M3Shop.render() draws
    a modal; BUY buttons STAGE a command into #cmd-input-ground (never auto-send).

Adversarial angles:
  - buy with no shop present / invalid slot / huge slot / negative / non-numeric
  - sell an item not owned / slot 0 / to a nonexistent shop
  - +commissary buy/sell of bogus keys while not in a faction (graceful?)
  - rapid-fire buy/browse (client races, modal stuck)
  - injection / oversized args through the buy/sell parser
  - DIRECTLY drive the renderer (handleShopState) with malformed shop_state
    payloads a buggy/edge server could emit — the render path is real app code
    and must be defensive (undefined slot/price/qty, null droids, NaN, etc.)

Run:  NODE_OPTIONS=--use-system-ca python tests/e2e/breakit_shop.py
Exit 0 = no browser-layer defect captured across the scenarios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from tests.e2e.breakit_harness import run_scenarios  # noqa: E402
from tests.e2e.playwright_new_player_poc import (  # noqa: E402
    drive_wizard, login_and_enter,
)


# ── resilient new-player ───────────────────────────────────────────────────────
#
# On this box the single-threaded aiohttp server's event loop briefly blocks
# under boot + tick load, so static JS assets dribble in ~10s apart and a
# `domcontentloaded` goto on /client.html can blow past 30s. That is a
# server/box PERF artifact (the tick loop logs "fell behind"), NOT a shop bug —
# but it stops the harness `new_player()` from ever reaching the shop surface.
# This wrapper navigates with wait_until='commit' (don't block on the slow asset
# graph) and waits on the specific elements the flow needs, with long timeouts.

def new_player_resilient(sess, name: str | None = None) -> dict:
    import random
    suffix = random.randint(100000, 999999)
    name = name or f"Brk{suffix}"
    user, pw = f"brk{suffix}", "testpass123"
    pg = sess.page
    pg.goto(sess.base + "/chargen", wait_until="commit")
    pg.wait_for_selector("#templateCards .card[data-key]", timeout=60000)
    drive_wizard(pg, name, user, pw)
    pg.wait_for_selector("#successOverlay", state="visible", timeout=60000)
    pg.goto(sess.base + "/client.html", wait_until="commit")
    # login_and_enter waits for #login-user etc.; those are in the inline HTML so
    # they exist even before the slow external JS finishes loading.
    login_and_enter(pg, user, pw)
    return {"name": name, "user": user, "pw": pw}


# ── helpers ────────────────────────────────────────────────────────────────────

def _wait_for_m3shop(sess) -> None:
    """The shop renderer lives in the externally-loaded m3_shop.js, which on
    this box can dribble in ~10s after the inline HTML. Wait for the exported
    window.M3Shop before driving it."""
    sess.page.wait_for_function("() => !!window.M3Shop", timeout=60000)


def _push_shop_state(sess, payload) -> str:
    """Drive the REAL render function (window.M3Shop.render — the same code
    handleShopState invokes on a shop_state WS push) with a crafted payload,
    into the real #shop-modal-body, with the real stage callback (mirroring
    stageFromShop: close the modal + stage via the exported stageRawCommand).
    Returns '' on success or the thrown error string.

    NOTE: handleShopState itself is NOT exported to window (it's an internal IIFE
    function reached only via the WS 'shop_state' dispatch), and neither is
    openShopModal — so we exercise the exported render building block
    (M3Shop.render), which is exactly what handleShopState feeds the push to.
    The optional openShopModal call below is a best-effort no-op when unexported;
    the render itself (the code under test) runs regardless."""
    return sess.page.evaluate(
        """(data) => {
            try {
                if (!window.M3Shop) return 'M3Shop missing';
                var body = document.getElementById('shop-modal-body');
                window.M3Shop.resetFocus();
                var t = document.getElementById('shop-modal-title');
                if (t) t.textContent = window.M3Shop.titleFor(data);
                window.M3Shop.render(body, data, function(cmd){
                    if (window.closeShopModal) window.closeShopModal();
                    if (window.stageRawCommand) window.stageRawCommand(cmd);
                });
                if (window.openShopModal) window.openShopModal();
                return '';
            } catch (e) { return String(e && e.stack || e); }
        }""",
        payload)


# ── scenarios ──────────────────────────────────────────────────────────────────

def s_buy_no_shop_present(sess):
    """A fresh starter room has no vendor droids. Every buy/browse variant must
    degrade to a clean 'no vendor' message — never a JS error, 5xx, or hang."""
    new_player_resilient(sess)
    sess.send("browse")                       # lists droids (none)
    sess.send("browse Nonexistent Shop")      # named droid, absent
    sess.send("buy 1 from Ghost Emporium")    # buy-from-droid, no droid
    sess.send("buy 0 from Ghost Emporium")    # slot 0
    sess.send("buy -5 from Ghost Emporium")   # negative slot
    sess.send("buy 999999 from Ghost Emporium")  # huge slot
    sess.send("buy zzz from Ghost Emporium")  # non-numeric, no name match
    # The command box must still be live afterwards.
    assert sess.page.locator("#cmd-input-ground").is_visible()


def s_sell_not_owned(sess):
    """Selling things the player doesn't own / malformed sell args. None should
    500 or throw client-side."""
    new_player_resilient(sess)
    sess.send("sell")                                  # bare
    sess.send("sell nonexistent_item_xyz")             # not owned
    sess.send("sell 0")                                # slot-shaped junk
    sess.send("sell -1 to Ghost Shop")                 # negative to absent shop
    sess.send("sell durasteel to Ghost Shop")          # resource to absent shop
    sess.send("sell " + ("z" * 4000))                  # oversized item name
    sess.send("sell '; DROP TABLE objects;-- to Shop") # SQLi-shaped
    assert sess.page.locator("#cmd-input-ground").is_visible()


def s_commissary_bogus(sess):
    """+commissary surface. A fresh player is faction 'independent', so the
    happy path is gated — but the parser must say so cleanly and never error,
    including buy/sell of bogus keys and injection-shaped keys."""
    new_player_resilient(sess)
    sess.send("+commissary")                       # status (not in faction)
    sess.send("+commissary buy")                   # missing key
    sess.send("+commissary buy not_a_real_key")    # bogus key
    sess.send("+commissary buy dc15_blaster_rifle")  # real key, no faction/rank
    sess.send("+commissary sell")                  # missing key
    sess.send("+commissary sell not_a_real_key")   # bogus sell key
    sess.send("+commissary buy <script>alert(1)</script>")  # XSS-shaped key
    sess.send("requisition buy " + ("k" * 3000))   # alias + oversized key
    assert sess.page.locator("#cmd-input-ground").is_visible()


def s_rapid_browse_buy(sess):
    """Hammer browse + buy-from + +commissary with no settle to provoke client
    races, double-submit handlers, or a stuck/duplicated shop modal."""
    new_player_resilient(sess)
    for _ in range(12):
        sess.send("browse", settle_ms=0)
        sess.send("buy 1 from Ghost", settle_ms=0)
        sess.send("+commissary", settle_ms=0)
    sess.page.wait_for_timeout(2000)
    # Whatever the last push was, the modal must not be wedged open with no way
    # to close, and the input must still work.
    assert sess.page.locator("#cmd-input-ground").is_visible()


def s_render_malformed_shop_state(sess):
    """Drive the REAL render path (M3Shop.render, the function handleShopState
    invokes on a shop_state push) with the malformed / edge shop_state payloads
    a buggy or boundary server push could carry. The renderer must be defensive
    — any thrown error here is an app defect in the SPA render code (the server
    genuinely controls every field below)."""
    new_player_resilient(sess)
    _wait_for_m3shop(sess)

    import json
    payloads = [
        # 1. browse with totally missing droids key
        {"mode": "browse"},
        # 2. browse, droids null
        {"mode": "browse", "droids": None},
        # 3. browse, a droid with no inventory + missing fields
        {"mode": "browse", "droids": [{"id": 1}]},
        # 4. browse, inventory item missing slot/price/qty/name
        {"mode": "browse", "focused_id": 1,
         "droids": [{"id": 1, "name": "X", "inventory": [{}]}]},
        # 5. browse, item fields wrong types (price string, qty null, quality str)
        {"mode": "browse", "focused_id": 1,
         "droids": [{"id": 1, "name": "X", "item_count": 1,
                     "inventory": [{"slot": "abc", "name": None,
                                    "price": "free", "qty": None,
                                    "quality": "high", "crafter": 123}]}]},
        # 6. multi-droid picklist, one droid null-ish
        {"mode": "browse",
         "droids": [{"id": 1, "name": "A", "tier": "gn4", "item_count": 0},
                    {"id": 2, "name": "B", "tier": None, "item_count": None}]},
        # 7. dashboard, total_escrow NaN-ish, droid sales malformed
        {"mode": "dashboard", "owner_name": None, "total_escrow": None,
         "droids": [{"id": 1, "name": "S", "tier": "gn7", "placed": True,
                     "escrow": None, "inventory": [{"slot": None}],
                     "sales": [{}]}]},
        # 8. vendor (commissary) mode, items missing mark/cost/key
        {"mode": "vendor", "vendor_kind": "commissary",
         "faction_code": None, "balance": None, "items": [{}]},
        # 9. vendor mode, item with bogus mark + huge cost
        {"mode": "vendor", "faction_code": "republic", "balance": -1,
         "items": [{"key": "x", "name": "Y", "cost": 1e308,
                    "mark": "wtf", "min_rank": None}]},
        # 10. unknown mode entirely -> falls through to renderBrowse
        {"mode": "totally_unknown_mode"},
        # 11. empty object
        {},
        # 12. price is a giant number -> toLocaleString must not choke
        {"mode": "browse", "focused_id": 1,
         "droids": [{"id": 1, "name": "X",
                     "inventory": [{"slot": 1, "name": "Gold", "price": 1e21,
                                    "qty": 1}]}]},
        # 13. injection-shaped strings in names (must be text, not HTML)
        {"mode": "browse", "focused_id": 1,
         "droids": [{"id": 1, "name": "<img src=x onerror=alert(1)>",
                     "desc": "<script>alert(2)</script>",
                     "inventory": [{"slot": 1,
                                    "name": "<b>x</b>", "price": 10, "qty": 1,
                                    "crafter": "<i>c</i>"}]}]},
    ]

    bad = []
    for i, p in enumerate(payloads, 1):
        err = _push_shop_state(sess, p)
        if err:
            bad.append(f"payload#{i} {json.dumps(p)[:120]} -> {err[:300]}")
        # modal should be openable/closable each time; close it for the next
        sess.page.evaluate("() => { try { window.closeShopModal(); } catch(e){} }")
        sess.page.wait_for_timeout(60)

    if bad:
        # Mark it unmissable in the console (auto-captured) AND assert.
        sess.page.evaluate("(m) => console.error('SHOP_RENDER_THREW ' + m)",
                           " || ".join(bad))
        raise AssertionError("M3Shop.render threw on malformed push:\n  "
                             + "\n  ".join(bad))

    # 14. XSS verification: confirm the injection strings rendered as TEXT, not
    # live DOM (no injected <img>/<script> element in the modal body).
    _push_shop_state(sess, {"mode": "browse", "focused_id": 1,
                            "droids": [{"id": 1,
                                        "name": "<img src=x onerror=alert(9)>",
                                        "inventory": [{"slot": 1, "name": "n",
                                                       "price": 1, "qty": 1}]}]})
    injected = sess.page.evaluate(
        "() => { var b=document.getElementById('shop-modal-body');"
        " return b ? b.querySelectorAll('img,script').length : -1; }")
    assert injected == 0, f"shop modal injected {injected} live HTML nodes (XSS)"


def s_stage_buy_from_modal(sess):
    """Render a real-shaped browse push, click the BUY button, and verify the
    documented contract: BUY calls onCommand with EXACTLY `buy <slot> from
    <shop>` (it STAGES, never auto-sends). A wrong-behavior check the
    auto-capture can't see. We render via M3Shop.render with a CAPTURING
    onCommand so the assertion is independent of the (un-exported) modal-open
    wiring; M3Shop.render is the same function handleShopState calls, so the
    BUY-button -> onCommand path under test is identical to production."""
    new_player_resilient(sess)
    _wait_for_m3shop(sess)

    err = sess.page.evaluate(
        """() => {
            try {
                window.__buyCmd = null;
                var body = document.getElementById('shop-modal-body');
                var data = {mode:'browse', focused_id:7, droids:[
                    {id:7, name:'Test Bay', item_count:1, inventory:[
                        {slot:3, name:'Vibroblade', price:250, qty:1, quality:60}
                    ]}]};
                window.M3Shop.resetFocus();
                window.M3Shop.render(body, data, function(cmd){
                    window.__buyCmd = cmd;
                });
                return '';
            } catch (e) { return String(e && e.stack || e); }
        }""")
    assert not err, f"render threw: {err}"

    # Fire the rendered BUY button's real click handler. We dispatch the click
    # in-page (rather than a Playwright pointer click) because we render into the
    # modal body WITHOUT opening the modal (openShopModal is not exported), so
    # the body sits behind the cockpit overlays — a pointer click is intercepted.
    # The button's click LISTENER (the code under test) fires identically either
    # way; this isolates the BUY->onCommand contract, not modal z-order.
    clicked = sess.page.evaluate(
        """() => {
            var btns = document.querySelectorAll('#shop-modal-body button.inv-btn');
            for (var i = 0; i < btns.length; i++) {
                if ((btns[i].textContent || '').indexOf('BUY') !== -1) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
        }""")
    assert clicked, "no BUY button rendered in the shop modal body"
    sess.page.wait_for_timeout(150)

    staged = sess.page.evaluate("() => window.__buyCmd")
    assert staged == "buy 3 from Test Bay", \
        f"BUY produced wrong/empty command: {staged!r}"


if __name__ == "__main__":
    sys.exit(run_scenarios(
        "shop",
        [
            s_buy_no_shop_present,
            s_sell_not_owned,
            s_commissary_bogus,
            s_rapid_browse_buy,
            s_render_malformed_shop_state,
            s_stage_buy_from_modal,
        ],
    ))
