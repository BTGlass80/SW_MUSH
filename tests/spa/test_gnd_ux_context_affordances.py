"""
test_gnd_ux_context_affordances.py — UX Drop 1 client-contract verification.

Static-parse asserts (no jsdom required) that the clickable-affordances drop
shipped correctly across static/spa/m3_affordances.js + static/client.html:

  A) m3_affordances.js module exists, exposes window.M3Affordances with the
     public API, and is included by client.html.
  B) M3Affordances is initialized with sendCmd (DI) in client.html.
  C) CLAIM maps to the REAL `+bounty/collect` verb (no argument) — both in the
     module's commandForAction and in the qa-row injection descriptor.
  D) FLEE maps to the real `flee` verb and is gated on combat.
  E) Entity names are made clickable (makeNameClickable wired into the HERE
     panel for npcs / players / vendor droids).
  F) SELL appears on vendor rows gated on sellable loadout.
  G) Context flags (_inCombat, _roomHasBountyTarget) are derived in
     handleHudUpdate and consumed by the quick-button build.
  H) No new inline onclick handlers (the dead-handler class — all dispatch is
     addEventListener / sendCmd).
  I) No GCW/Imperial tokens in the new module.
"""
from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CLIENT_HTML = REPO_ROOT / "static" / "client.html"
AFFORDANCES_JS = REPO_ROOT / "static" / "spa" / "m3_affordances.js"


def _html() -> str:
    return CLIENT_HTML.read_text(encoding="utf-8")


def _js() -> str:
    return AFFORDANCES_JS.read_text(encoding="utf-8")


# ─── A. Module exists + API + included ────────────────────────────────


def test_module_file_exists():
    assert AFFORDANCES_JS.exists(), "static/spa/m3_affordances.js missing"


def test_module_exposes_namespace():
    js = _js()
    assert "window.M3Affordances" in js, "M3Affordances global not exported"


def test_module_public_api():
    js = _js()
    for fn in ("makeNameClickable", "decorateBountyRow", "commandForAction",
               "hasSellableLoadout", "extraQuickButtons", "roomHasBountyTarget",
               "init"):
        assert fn in js, f"M3Affordances.{fn} missing"


def test_module_included_in_client():
    html = _html()
    assert "spa/m3_affordances.js" in html, (
        "m3_affordances.js not <script>-included in client.html"
    )


# ─── B. DI init ───────────────────────────────────────────────────────


def test_module_initialized_with_sendCmd():
    html = _html()
    assert re.search(r"M3Affordances\.init\(\s*\{\s*sendCmd", html), (
        "M3Affordances.init({ sendCmd: ... }) not called in client.html"
    )


# ─── C. CLAIM → +bounty/collect (no arg) ──────────────────────────────


def test_claim_maps_to_bounty_collect_in_module():
    js = _js()
    # commandForAction('claim') returns '+bounty/collect' with NO argument.
    assert re.search(r"action\s*===\s*'claim'\s*\)\s*return\s*'\+bounty/collect'",
                     js), "claim does not map to bare '+bounty/collect'"


def test_claim_qarow_descriptor_is_bounty_collect():
    js = _js()
    # The FLEE/CLAIM extraQuickButtons descriptors carry the real verbs.
    assert "cmd: '+bounty/collect'" in js, (
        "CLAIM qa-row descriptor cmd is not '+bounty/collect'"
    )


def test_claim_has_no_phantom_contract_argument():
    js = _js()
    # Guard against the roadmap's wrong sketch ('+bounty/collect <id>').
    assert "+bounty/collect '" not in js.replace("'+bounty/collect'", ""), (
        "claim command appears to append an argument; +bounty/collect takes none"
    )


# ─── D. FLEE → flee, gated on combat ──────────────────────────────────


def test_flee_descriptor_present():
    js = _js()
    assert "cmd: 'flee'" in js, "FLEE descriptor cmd is not 'flee'"


def test_flee_gated_on_in_combat():
    js = _js()
    assert re.search(r"ctx\.inCombat", js), (
        "FLEE injection not gated on ctx.inCombat"
    )


# ─── E. Clickable names wired in the HERE panel ───────────────────────


def _here_panel_body(html: str) -> str:
    start = html.find("function renderHerePanel(")
    assert start != -1, "renderHerePanel not found"
    # Bound the slice at the NEXT top-level function so the whole body
    # (incl. the trailing vendor-droid block with SELL) is captured.
    end = html.find("\nfunction ", start + 1)
    if end == -1:
        end = start + 9000
    return html[start:end]


def test_name_click_wired_for_npcs_and_players():
    body = _here_panel_body(_html())
    # makeNameClickable should be invoked at least 3 times (npc, player, vendor).
    assert body.count("makeNameClickable") >= 3, (
        "makeNameClickable not wired for all entity types in renderHerePanel"
    )


def test_makeNameClickable_dispatches_look():
    js = _js()
    assert re.search(r"_dispatch\(\s*'look '\s*\+\s*name\s*\)", js), (
        "makeNameClickable does not dispatch 'look <name>'"
    )


def test_quest_role_gets_name_class():
    # Guide-protect: a quest-giver/guide NPC renders with the .here-name.quest
    # accent — the nameCls chain must add the 'quest' class (else the CSS rule
    # is dead).
    body = _here_panel_body(_html())
    assert re.search(r"role\s*===\s*'quest'\s*\)\s*nameCls\s*\+=\s*' quest'",
                     body), "renderHerePanel does not add the 'quest' name class"


# ─── F. SELL on vendor rows, gated on loadout ─────────────────────────


def test_sell_button_gated_on_loadout():
    body = _here_panel_body(_html())
    assert "hasSellableLoadout" in body, (
        "SELL not gated on M3Affordances.hasSellableLoadout in renderHerePanel"
    )
    assert "sendCmd('sell')" in body, "SELL button does not send the 'sell' verb"


# ─── G. Context flags derived + consumed ──────────────────────────────


def _handleHudUpdate_body(html: str) -> str:
    start = html.find("function handleHudUpdate(data)")
    assert start != -1, "handleHudUpdate not found"
    return html[start: start + 35000]


def test_in_combat_flag_derived():
    body = _handleHudUpdate_body(_html())
    assert "_inCombat" in body and "data.in_combat" in body, (
        "_inCombat not derived from data.in_combat in handleHudUpdate"
    )


def test_bounty_target_flag_derived():
    body = _handleHudUpdate_body(_html())
    assert "_roomHasBountyTarget" in body and "roomHasBountyTarget" in body, (
        "_roomHasBountyTarget not derived in handleHudUpdate"
    )


def test_flags_consumed_in_explore_build():
    html = _html()
    start = html.find("function _buildExploreButtons()")
    assert start != -1, "_buildExploreButtons not found"
    body = html[start: start + 2500]
    assert "extraQuickButtons" in body, (
        "_buildExploreButtons does not consume M3Affordances.extraQuickButtons"
    )


# ─── H. No new inline onclick (dead-handler class) ────────────────────


def test_no_inline_onclick_in_module():
    js = _js()
    assert "onclick" not in js.lower(), (
        "m3_affordances.js uses inline onclick; must use addEventListener"
    )


# ─── I. Era cleanness in the new module ───────────────────────────────


def test_no_gcw_tokens_in_module():
    js = _js()
    for tok in (r"\bempire\b", r"\brebel\b", r"\bTIE\b", r"\bimperial\b"):
        assert not re.search(tok, js, re.IGNORECASE), (
            f"GCW/Imperial token {tok} in m3_affordances.js"
        )
