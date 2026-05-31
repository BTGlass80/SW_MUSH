"""
test_m3_assembled_client.py — Drop 4.12b regression lock for
m3_assembled_client.js.

Drop 4.12b ports map_v3/assembled-client.jsx (701 JSX LOC) into a
vanilla-JS SPA module at static/spa/m3_assembled_client.js. This is
the integration target — full field-kit shell composing every prior
m3_* module via defensive DI.

What this file pins:

  · Module shape (IIFE + window.M3AssembledClient + documented surface).
  · 10 public sub-builders + create() handle + buildAssembledClient()
    + DEMO_CHARACTER + init exported.
  · B3 era cleanness — Tatooine / Mos Eisley / Republic / 20 BBY
    references in the demo data; zero Empire/Imperial/Rebel/TIE/
    X-wing references.
  · Shell layout: holonet ticker slot + status bar + 3-column body
    (LeftHUD + CenterFeed + RightCartridge) + command strip.
  · Stateful create() handle owns popup + cartridge state.
  · Defensive DI fallbacks for all four dependency modules render
    labeled placeholders rather than crashing.
  · Cartridge swap: MAP / INV / JOBS / LORE renders correct body.
  · Popup state machine: sheet / holocron / holonet / map mount
    into popup layer; close unmounts.

Pattern parallels tests/spa/test_m3_holonet.py (Drop 4.10) and
tests/spa/test_m3_skill_check.py (Drop 4.11).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
AC_MODULE = REPO_ROOT / "static" / "spa" / "m3_assembled_client.js"
SHEET_MODULE = REPO_ROOT / "static" / "spa" / "m3_sheet.js"
CLIENT_HTML = REPO_ROOT / "static" / "client.html"

SAMPLE_PALETTE = {
    "amber":     "#ffc857",
    "red":       "#ff5a4a",
    "green":     "#7ce068",
    "cyan":      "#7ce0d0",
    "gold":      "#d4a44b",
    "ink":       "#d6cbb7",
    "inkBright": "#fff4d6",
    "inkDim":    "#a09584",
    "inkFaint":  "#6b6253",
    "sky":       "#2a2418",
    "skyDeep":   "#1a160c",
    "body":      "#cdc3b0",
    "fg":        "#d6cbb7",
}

from .spa_dom_harness import run_with_dom


# ════════════════════════════════════════════════════════════════════
# Static module-shape checks
# ════════════════════════════════════════════════════════════════════

def test_module_file_exists():
    assert AC_MODULE.exists()


def test_module_is_iife():
    src = AC_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src
    assert "})();" in src


def test_module_exports_namespace():
    src = AC_MODULE.read_text(encoding="utf-8")
    assert "window.M3AssembledClient" in src


def test_module_defines_all_documented_builders():
    src = AC_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildAssembledClient",
        "buildStatusBar",
        "buildLeftHUD",
        "buildCenterFeed",
        "buildCommsTabs",
        "buildRightCartridge",
        "buildMiniMap",
        "buildMiniInv",
        "buildMiniJobs",
        "buildMiniLore",
        "buildCommandStrip",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3AssembledClient"
        )


def test_create_function_present_and_exported():
    src = AC_MODULE.read_text(encoding="utf-8")
    assert "function create(" in src
    assert re.search(r"create\s*:\s*create\b", src)


def test_init_function_present_and_exported():
    src = AC_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert "/static/spa/m3_assembled_client.js" in src
    assert "M3AssembledClient.init(" in src


# ════════════════════════════════════════════════════════════════════
# Helper — extract a brace-delimited block by anchor
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str) -> str:
    i = src.find(start_marker)
    if i < 0:
        return ""
    open_brace = -1
    opener = None
    for j in range(i, len(src)):
        if src[j] in "{[":
            open_brace = j
            opener = src[j]
            break
    if open_brace < 0:
        return ""
    closer = "}" if opener == "{" else "]"
    depth = 0
    j = open_brace
    while j < len(src):
        ch = src[j]
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return src[open_brace:j + 1]
        j += 1
    return ""


# ════════════════════════════════════════════════════════════════════
# B3 era-cleanness
# ════════════════════════════════════════════════════════════════════

def test_demo_character_clean():
    """DEMO_CHARACTER block contains no era-contamination tokens."""
    src = AC_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var DEMO_CHARACTER = {")
    assert block, "DEMO_CHARACTER block not found"
    for tok in ("Empire", "Imperial", "Rebel", "Rebellion", "Stormtrooper",
                "Vader", "Death Star", "ISB", "X-wing"):
        assert tok not in block, f"B3 regression: '{tok}' in DEMO_CHARACTER"


def test_status_bar_renders_cw_era_labels():
    """The status bar must show the CW-era location and timestamp
    labels. These are inline strings in buildStatusBar — pull the
    function body and assert."""
    src = AC_MODULE.read_text(encoding="utf-8")
    # We can verify the string literals are present in the module source.
    assert "TATOOINE \\u00b7 MOS EISLEY \\u00b7 DOCKING BAY 94" in src \
        or "TATOOINE · MOS EISLEY · DOCKING BAY 94" in src
    assert "20 BBY" in src


def test_no_era_contamination_module_wide_data():
    """No Empire/Imperial/Rebel/TIE/X-wing/Stormtrooper/Vader/Death-
    Star/ISB references in the module source EXCEPT inside comments.
    A coarse module-wide check: strip block + line comments, then
    grep. This protects against future fixture edits."""
    src = AC_MODULE.read_text(encoding="utf-8")
    # Strip /* ... */ block comments.
    no_block = re.sub(r"/\*.*?\*/", "", src, flags=re.DOTALL)
    # Strip // line comments.
    no_line = re.sub(r"//[^\n]*", "", no_block)
    for tok in ("Empire", "Imperial", "Rebel", "Rebellion", "Stormtrooper",
                "Vader", "Death Star", "ISB"):
        # TIE and X-wing are too narrow to grep without false positives
        # at module scope (TIE could match attacker.actor.title style
        # accessors in unrelated code) — handled per-fixture above.
        assert tok not in no_line, (
            f"B3 regression: '{tok}' in module source outside comments"
        )


# ════════════════════════════════════════════════════════════════════
# Q1 canonical-character preservation note
# ════════════════════════════════════════════════════════════════════

def test_canonical_character_references_preserved_from_source():
    """Drop 4.12b preserves the JSX source's references to Greedo
    (Rodian hostile in the bay) and the Mynock ship name. Per the
    v50 source-fidelity policy, these stay verbatim and are queued
    for the Q1-hardening sweep."""
    src = AC_MODULE.read_text(encoding="utf-8")
    # These appear in the feed item strings, not in a single fixture
    # block, so we just grep the module source.
    assert "Greedo" in src
    assert "Mynock" in src


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        result = {
            hasNamespace:        !!N,
            schemaVersion:       N && N.SCHEMA_VERSION,
            hasInit:             typeof N.init === 'function',
            hasCreate:           typeof N.create === 'function',
            hasBuildClient:      typeof N.buildAssembledClient === 'function',
            hasBuildStatusBar:   typeof N.buildStatusBar === 'function',
            hasBuildLeftHUD:     typeof N.buildLeftHUD === 'function',
            hasBuildCenterFeed:  typeof N.buildCenterFeed === 'function',
            hasBuildCommsTabs:   typeof N.buildCommsTabs === 'function',
            hasBuildRight:       typeof N.buildRightCartridge === 'function',
            hasBuildMiniMap:     typeof N.buildMiniMap === 'function',
            hasBuildMiniInv:     typeof N.buildMiniInv === 'function',
            hasBuildMiniJobs:    typeof N.buildMiniJobs === 'function',
            hasBuildMiniLore:    typeof N.buildMiniLore === 'function',
            hasBuildCmdStrip:    typeof N.buildCommandStrip === 'function',
            hasDemoChar:         !!(N && N.DEMO_CHARACTER),
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k, expected in [
        ("hasNamespace", True), ("schemaVersion", 1),
        ("hasInit", True), ("hasCreate", True),
        ("hasBuildClient", True), ("hasBuildStatusBar", True),
        ("hasBuildLeftHUD", True), ("hasBuildCenterFeed", True),
        ("hasBuildCommsTabs", True), ("hasBuildRight", True),
        ("hasBuildMiniMap", True), ("hasBuildMiniInv", True),
        ("hasBuildMiniJobs", True), ("hasBuildMiniLore", True),
        ("hasBuildCmdStrip", True), ("hasDemoChar", True),
    ]:
        assert r[k] == expected, f"{k} = {r[k]}"


def test_runtime_buildAssembledClient_renders_full_shell():
    """The stateless builder lays out all four layout slots."""
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildAssembledClient(p);
        document.body.appendChild(el);
        result = {
            tag:              el.tagName,
            isAssembled:      el.getAttribute('data-assembled-client') === '1',
            hasStatusBar:     !!el.querySelector('[data-status-bar]'),
            hasLeftHUD:       !!el.querySelector('[data-left-hud]'),
            hasCenterFeed:    !!el.querySelector('[data-center-feed]'),
            hasRightCart:     !!el.querySelector('[data-right-cartridge]'),
            hasCommsTabs:     !!el.querySelector('[data-comms-tabs]'),
            hasCmdStrip:      !!el.querySelector('[data-command-strip]'),
            hasMainGrid:      !!el.querySelector('[data-main-grid]'),
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["tag"]            == "DIV"
    assert r["isAssembled"]    is True
    assert r["hasStatusBar"]   is True
    assert r["hasLeftHUD"]     is True
    assert r["hasCenterFeed"]  is True
    assert r["hasRightCart"]   is True
    assert r["hasCommsTabs"]   is True
    assert r["hasCmdStrip"]    is True
    assert r["hasMainGrid"]    is True


def test_runtime_status_bar_renders_cw_labels():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildStatusBar(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasLocation:  text.indexOf('TATOOINE') >= 0 &&
                          text.indexOf('MOS EISLEY') >= 0 &&
                          text.indexOf('DOCKING BAY 94') >= 0,
            hasBBY:       text.indexOf('20 BBY') >= 0,
            hasOpName:    text.indexOf('TEY VOSS') >= 0,
            hasMarker:    text.indexOf('FIELD DATAPAD') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["hasLocation"]  is True
    assert r["hasBBY"]       is True
    assert r["hasOpName"]    is True
    assert r["hasMarker"]    is True


def test_runtime_left_hud_renders_identity_vitals_attrs_status():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildLeftHUD(p, N.DEMO_CHARACTER);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasOperative:   text.indexOf('OPERATIVE') >= 0,
            hasName:        text.indexOf('TEY VOSS') >= 0,
            hasVitals:      text.indexOf('VITALS') >= 0,
            hasWounded:     text.indexOf('WOUNDED') >= 0,
            hasFP:          text.indexOf('FP') >= 0,
            hasDSP:         text.indexOf('DSP') >= 0,
            hasCP:          text.indexOf('CP') >= 0,
            hasAttrs:       text.indexOf('ATTRIBUTES') >= 0,
            hasDEX:         text.indexOf('DEX') >= 0,
            hasStatusHdr:   text.indexOf('STATUS') >= 0,
            hasSheetBtn:    text.indexOf('+SHEET') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k in ("hasOperative", "hasName", "hasVitals", "hasWounded",
              "hasFP", "hasDSP", "hasCP", "hasAttrs", "hasDEX",
              "hasStatusHdr", "hasSheetBtn"):
        assert r[k] is True, f"{k} missing from LeftHUD"


def test_runtime_left_hud_sheet_button_fires_hook():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var clicks = 0;
        var el = N.buildLeftHUD(p, N.DEMO_CHARACTER, {
            onSheet: function() { clicks++; },
        });
        document.body.appendChild(el);
        var btn = el.querySelector('[data-sheet-open-btn]');
        if (btn) btn.click();
        result = { foundBtn: !!btn, clicks: clicks };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["foundBtn"]  is True
    assert r["clicks"]    == 1


def test_runtime_center_feed_renders_room_banner_and_six_items():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildCenterFeed(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasYouAreIn:    text.indexOf('YOU ARE IN') >= 0,
            hasBay94:       text.indexOf('Docking Bay 94') >= 0,
            hasSecured:     text.indexOf('SECURED') >= 0,
            hasDuracrete:   text.indexOf('duracrete') >= 0,
            hasAlsoHere:    text.indexOf('ALSO HERE') >= 0,
            hasYenn:        text.indexOf('Yenn Karac') >= 0,
            hasMak:         text.indexOf('Mak Torrin') >= 0,
            hasGreedo:      text.indexOf('Greedo') >= 0,
            hasTey:         text.indexOf('Tey Voss') >= 0,
            hasRepublic:    text.indexOf('Republic') >= 0,
            hasBlasterFire: text.indexOf('blaster fire') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k in ("hasYouAreIn", "hasBay94", "hasSecured", "hasDuracrete",
              "hasAlsoHere", "hasYenn", "hasMak", "hasGreedo",
              "hasTey", "hasRepublic", "hasBlasterFire"):
        assert r[k] is True, f"{k} missing from CenterFeed"


def test_runtime_center_feed_hot_noun_click_fires_hook():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var clicks = 0;
        var el = N.buildCenterFeed(p, {
            onHolocron: function() { clicks++; },
        });
        document.body.appendChild(el);
        // Find the duracrete hot noun by text content
        var spans = el.querySelectorAll('span');
        var hot = null;
        for (var i = 0; i < spans.length; i++) {
            if (spans[i].textContent === 'duracrete') {
                hot = spans[i];
                break;
            }
        }
        if (hot) hot.click();
        result = { foundHot: !!hot, clicks: clicks };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["foundHot"]  is True
    assert r["clicks"]    == 1


def test_runtime_comms_tabs_renders_six_tabs_with_badges():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildCommsTabs(p);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            text:           text,
            hasAll:         text.indexOf('ALL') >= 0,
            hasIC:          text.indexOf('IC') >= 0,
            hasOOC:         text.indexOf('OOC') >= 0,
            hasSystem:      text.indexOf('SYSTEM') >= 0,
            hasComlink:     text.indexOf('COMLINK') >= 0,
            hasHolonet:     text.indexOf('HOLONET') >= 0,
            hasPreviewIC:   text.indexOf('Mynock') >= 0,
            hasPreviewSys:  text.indexOf('Greedo enters') >= 0,
            hasMakPreview:  text.indexOf('Mak: ') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k in ("hasAll", "hasIC", "hasOOC", "hasSystem", "hasComlink",
              "hasHolonet", "hasPreviewIC", "hasPreviewSys", "hasMakPreview"):
        assert r[k] is True, f"{k} missing from CommsTabs"


def test_runtime_right_cartridge_default_is_map():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildRightCartridge(p);
        document.body.appendChild(el);
        var body = el.querySelector('[data-current-cartridge]');
        var text = el.textContent;
        result = {
            currentCart: body && body.getAttribute('data-current-cartridge'),
            hasHolocarta: text.indexOf('HOLOCARTA') >= 0,
            hasExits: text.indexOf('EXITS') >= 0,
            // INV body should NOT be present
            hasLoadout: text.indexOf('LOADOUT') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["currentCart"]   == "MAP"
    assert r["hasHolocarta"]  is True
    assert r["hasExits"]      is True
    assert r["hasLoadout"]    is False


def test_runtime_right_cartridge_swap_to_inv():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildRightCartridge(p, 'INV');
        document.body.appendChild(el);
        var body = el.querySelector('[data-current-cartridge]');
        var text = el.textContent;
        result = {
            currentCart: body && body.getAttribute('data-current-cartridge'),
            hasLoadout: text.indexOf('LOADOUT') >= 0,
            hasBlaster: text.indexOf('HVY BLASTER PISTOL') >= 0,
            hasSoak: text.indexOf('SOAK') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["currentCart"]  == "INV"
    assert r["hasLoadout"]   is True
    assert r["hasBlaster"]   is True
    assert r["hasSoak"]      is True


def test_runtime_right_cartridge_swap_to_jobs():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildRightCartridge(p, 'JOBS');
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasActive: text.indexOf('ACTIVE JOBS') >= 0,
            hasSpiceRun: text.indexOf('Spice Run') >= 0,
            hasBounty: text.indexOf('Bounty') >= 0,
            hasUrgent: text.indexOf('URGENT') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k in ("hasActive", "hasSpiceRun", "hasBounty", "hasUrgent"):
        assert r[k] is True, f"{k} missing from JOBS cartridge"


def test_runtime_right_cartridge_swap_to_lore():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildRightCartridge(p, 'LORE');
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasHolocron: text.indexOf('HOLOCRON') >= 0,
            hasHutt: text.indexOf('HUTT CARTEL') >= 0,
            hasLastOpened: text.indexOf('Last opened') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["hasHolocron"]    is True
    assert r["hasHutt"]        is True
    assert r["hasLastOpened"]  is True


def test_runtime_cartridge_tab_click_fires_hook():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var clicked = null;
        var el = N.buildRightCartridge(p, 'MAP', {
            onCartridgeClick: function(t) { clicked = t; },
        });
        document.body.appendChild(el);
        var jobsTab = el.querySelector('[data-cartridge-tab="JOBS"]');
        if (jobsTab) jobsTab.click();
        result = { clicked: clicked, foundTab: !!jobsTab };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["foundTab"]  is True
    assert r["clicked"]   == "JOBS"


def test_runtime_minimap_renders_placeholder_when_no_tier_renderer():
    """Without hooks.getTierRenderer, the mini-map shows the labeled
    placeholder. Mirrors the M3MapNavigator _defaultTierRenderer seam."""
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildMiniMap(p);
        document.body.appendChild(el);
        var placeholder = el.querySelector('[data-default-tier-body]');
        var text = placeholder && placeholder.textContent;
        result = {
            hasPlaceholder: !!placeholder,
            tier:           placeholder && placeholder.getAttribute('data-default-tier-body'),
            hasNotWired:    text && text.indexOf('NOT WIRED') >= 0,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["hasPlaceholder"]  is True
    assert r["tier"]            == "1a"
    assert r["hasNotWired"]     is True


def test_runtime_minimap_uses_tier_renderer_when_provided():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var calls = [];
        var el = N.buildMiniMap(p, {
            getTierRenderer: function(tier, args) {
                calls.push({ tier: tier, w: args.width, h: args.height });
                var div = document.createElement('div');
                div.setAttribute('data-mock-tier-renderer', tier);
                div.textContent = 'MOCK TIER ' + tier;
                return div;
            },
        });
        document.body.appendChild(el);
        var mock = el.querySelector('[data-mock-tier-renderer]');
        result = {
            hasMock: !!mock,
            mockTier: mock && mock.getAttribute('data-mock-tier-renderer'),
            callCount: calls.length,
            firstCall: calls[0] || null,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["hasMock"]      is True
    assert r["mockTier"]     == "1a"
    assert r["callCount"]    == 1
    assert r["firstCall"]["tier"]  == "1a"
    assert r["firstCall"]["w"]     == 332
    assert r["firstCall"]["h"]     == 230


def test_runtime_minimap_expand_button_fires_hook():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var clicks = 0;
        var el = N.buildMiniMap(p, {
            onMap: function() { clicks++; },
        });
        document.body.appendChild(el);
        var btn = el.querySelector('[data-map-expand-btn]');
        if (btn) btn.click();
        result = { foundBtn: !!btn, clicks: clicks };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["foundBtn"]  is True
    assert r["clicks"]    == 1


def test_runtime_minilore_open_button_fires_hook():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var clicks = 0;
        var el = N.buildMiniLore(p, {
            onHolocron: function() { clicks++; },
        });
        document.body.appendChild(el);
        var btn = el.querySelector('[data-holocron-open-btn]');
        if (btn) btn.click();
        result = { foundBtn: !!btn, clicks: clicks };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["foundBtn"]  is True
    assert r["clicks"]    == 1


def test_runtime_command_strip_renders():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var el = N.buildCommandStrip(p, 84);
        document.body.appendChild(el);
        var text = el.textContent;
        result = {
            hasLook: text.indexOf('LOOK') >= 0,
            hasPose: text.indexOf('POSE') >= 0,
            hasSay: text.indexOf('SAY') >= 0,
            hasBoard: text.indexOf('BOARD') >= 0,
            hasSend: text.indexOf('SEND') >= 0,
            hasCmdAttr: el.getAttribute('data-command-strip') === '1',
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    for k in ("hasLook", "hasPose", "hasSay", "hasBoard", "hasSend",
              "hasCmdAttr"):
        assert r[k] is True, f"{k} missing from CommandStrip"


# ════════════════════════════════════════════════════════════════════
# Stateful create() handle
# ════════════════════════════════════════════════════════════════════

def test_runtime_create_handle_initial_state():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var h = N.create(p);
        document.body.appendChild(h.element);
        var s = h.getState();
        result = {
            tag:             h.element.tagName,
            isContainer:     h.element.getAttribute('data-assembled-client-container') === '1',
            hasShellLayer:   !!h.element.querySelector('[data-shell-layer]'),
            hasPopupLayer:   !!h.element.querySelector('[data-popup-layer]'),
            popupNull:       s.popup === null,
            cartDefault:     s.cartridge,
            hasOpenPopup:    typeof h.openPopup === 'function',
            hasClosePopup:   typeof h.closePopup === 'function',
            hasSetCartridge: typeof h.setCartridge === 'function',
            hasDestroy:      typeof h.destroy === 'function',
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["tag"]              == "DIV"
    assert r["isContainer"]      is True
    assert r["hasShellLayer"]    is True
    assert r["hasPopupLayer"]    is True
    assert r["popupNull"]        is True
    assert r["cartDefault"]      == "MAP"
    assert r["hasOpenPopup"]     is True
    assert r["hasClosePopup"]    is True
    assert r["hasSetCartridge"]  is True
    assert r["hasDestroy"]       is True


def test_runtime_create_handle_setCartridge_swaps_body():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var changes = [];
        var h = N.create(p, {
            onCartridgeChange: function(name) { changes.push(name); },
        });
        document.body.appendChild(h.element);

        var body1 = h.element.querySelector('[data-current-cartridge]');
        var cart1 = body1.getAttribute('data-current-cartridge');

        h.setCartridge('INV');
        var body2 = h.element.querySelector('[data-current-cartridge]');
        var cart2 = body2.getAttribute('data-current-cartridge');

        // Same-target setCartridge is no-op (no onChange fire).
        h.setCartridge('INV');

        h.setCartridge('JOBS');
        var body3 = h.element.querySelector('[data-current-cartridge]');
        var cart3 = body3.getAttribute('data-current-cartridge');

        result = {
            cart1: cart1, cart2: cart2, cart3: cart3,
            changes: changes,
            getStateCart: h.getState().cartridge,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["cart1"]         == "MAP"
    assert r["cart2"]         == "INV"
    assert r["cart3"]         == "JOBS"
    assert r["changes"]       == ["INV", "JOBS"]   # no dupe for same-name
    assert r["getStateCart"]  == "JOBS"


def test_runtime_create_handle_openPopup_mounts_into_popup_layer():
    """openPopup with no dep modules loaded mounts a labeled fallback,
    and closePopup unmounts it."""
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var changes = [];
        var h = N.create(p, {
            onPopupChange: function(name) { changes.push(name); },
        });
        document.body.appendChild(h.element);

        // Initially no popup
        var popupLayer = h.element.querySelector('[data-popup-layer]');
        var beforeChildren = popupLayer.children.length;

        // Open sheet popup (M3Sheet not loaded → fallback)
        h.openPopup('sheet');
        var afterChildren = popupLayer.children.length;
        var fallback = popupLayer.querySelector('[data-missing-dep]');
        var popupState = h.getState().popup;

        // Close
        h.closePopup();
        var finalChildren = popupLayer.children.length;
        var finalPopup = h.getState().popup;

        result = {
            beforeChildren:  beforeChildren,
            afterChildren:   afterChildren,
            hasFallback:     !!fallback,
            fallbackName:    fallback && fallback.getAttribute('data-missing-dep'),
            popupStateOpen:  popupState,
            finalChildren:   finalChildren,
            finalPopup:      finalPopup,
            changes:         changes,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["beforeChildren"]   == 0
    assert r["afterChildren"]    == 1
    assert r["hasFallback"]      is True
    assert r["fallbackName"]     == "M3Sheet"
    assert r["popupStateOpen"]   == "sheet"
    assert r["finalChildren"]    == 0
    assert r["finalPopup"]       is None
    assert r["changes"]          == ["sheet", None]


def test_runtime_create_handle_popup_swap_closes_previous():
    """Opening a different popup while one is already open auto-closes
    the previous before mounting the new."""
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var h = N.create(p);
        document.body.appendChild(h.element);

        h.openPopup('sheet');
        var afterSheet = h.element.querySelector('[data-popup-layer]').children.length;
        var sheetEl = h.element.querySelector('[data-missing-dep]');
        var sheetDep = sheetEl && sheetEl.getAttribute('data-missing-dep');

        h.openPopup('holocron');
        var afterHolocron = h.element.querySelector('[data-popup-layer]').children.length;
        var holEl = h.element.querySelector('[data-missing-dep]');
        var holDep = holEl && holEl.getAttribute('data-missing-dep');

        result = {
            afterSheet:    afterSheet,
            sheetDep:      sheetDep,
            afterHolocron: afterHolocron,
            holDep:        holDep,
            currentPopup:  h.getState().popup,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["afterSheet"]     == 1
    assert r["sheetDep"]       == "M3Sheet"
    # Still one popup child — but it's the holocron fallback now.
    assert r["afterHolocron"]  == 1
    assert r["holDep"]         == "M3Holocron"
    assert r["currentPopup"]   == "holocron"


def test_runtime_create_handle_destroy_clears_dom():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var h = N.create(p);
        document.body.appendChild(h.element);
        h.openPopup('sheet');

        var inDomBefore = !!document.body.querySelector('[data-assembled-client-container]');
        var hadPopup = !!document.body.querySelector('[data-missing-dep]');

        h.destroy();

        var inDomAfter = !!document.body.querySelector('[data-assembled-client-container]');
        var stillPopup = !!document.body.querySelector('[data-missing-dep]');

        result = {
            inDomBefore: inDomBefore,
            hadPopup: hadPopup,
            inDomAfter: inDomAfter,
            stillPopup: stillPopup,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["inDomBefore"]  is True
    assert r["hadPopup"]     is True
    assert r["inDomAfter"]   is False
    assert r["stillPopup"]   is False


def test_runtime_create_handle_start_cartridge_option():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var h = N.create(p, { startCartridge: 'LORE' });
        document.body.appendChild(h.element);
        var body = h.element.querySelector('[data-current-cartridge]');
        result = {
            cart: body.getAttribute('data-current-cartridge'),
            state: h.getState().cartridge,
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["cart"]   == "LORE"
    assert r["state"]  == "LORE"


# ════════════════════════════════════════════════════════════════════
# Cross-module integration tests — load m3_sheet alongside and verify
# the sheet popup mounts the real character sheet modal
# (instead of the fallback).
# ════════════════════════════════════════════════════════════════════

def test_runtime_sheet_popup_uses_real_m3sheet_when_loaded():
    """When M3Sheet is loaded, openPopup('sheet') mounts the real
    character sheet modal (not the missing-dep fallback)."""
    setup = _setup_prelude() + r"""
        // Init M3Sheet too.
        if (window.M3Sheet && window.M3Sheet.init) {
            window.M3Sheet.init({});
        }
        var N = window.M3AssembledClient;
        var h = N.create(p);
        document.body.appendChild(h.element);
        h.openPopup('sheet');

        var popupLayer = h.element.querySelector('[data-popup-layer]');
        var sheetBackdrop = popupLayer.querySelector('[data-sheet-mode]');
        var fallback = popupLayer.querySelector('[data-missing-dep]');
        var sheetChar = popupLayer.querySelector('[data-sheet-character]');

        result = {
            popupState:    h.getState().popup,
            hasSheetModal: !!sheetBackdrop,
            mode:          sheetBackdrop && sheetBackdrop.getAttribute('data-sheet-mode'),
            hasFallback:   !!fallback,
            sheetCharName: sheetChar && sheetChar.getAttribute('data-sheet-character'),
        };
    """
    r = run_with_dom([SHEET_MODULE, AC_MODULE], setup)
    assert r["popupState"]    == "sheet"
    assert r["hasSheetModal"] is True
    assert r["mode"]          == "modal"
    assert r["hasFallback"]   is False
    assert r["sheetCharName"] == "TEY VOSS"


def test_runtime_init_idempotent():
    setup = _setup_prelude() + r"""
        var N = window.M3AssembledClient;
        var threw = false;
        try {
            N.init();
            N.init({});
            N.init({ escapeHtml: function(s) { return s; } });
            N.init();
        } catch (e) {
            threw = true;
        }
        var el = N.buildAssembledClient(p);
        document.body.appendChild(el);
        result = {
            threw: threw,
            renders: el.tagName === 'DIV',
        };
    """
    r = run_with_dom([AC_MODULE], setup)
    assert r["threw"]    is False
    assert r["renders"]  is True
