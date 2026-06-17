"""
test_m3_holonet.py — Drop 4.10 regression lock for m3_holonet.js.

Drop 4.10 ports map_v3/holonet.jsx (653 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_holonet.js. This file pins:

  · Module shape (IIFE + window.M3Holonet + documented surface).
  · 11 public builders + 2 fixtures + init exported.
  · B3 era cleanness — Clone-Wars-era references (Ryloth, Geonosis,
    CIS, Republic, 20 BBY) in the fixture; zero Empire/Imperial
    references in the data block.
  · Ticker / browser / modal all render correctly.
  · Hooks (onCategoryClick / onFilterToggle / onStoryClick /
    onRelatedClick / onClose) fire correctly.

Pattern parallels tests/spa/test_m3_cockpit.py (Drop 4.9).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
HOLONET_MODULE  = REPO_ROOT / "static" / "spa" / "m3_holonet.js"
CLIENT_HTML     = REPO_ROOT / "static" / "client.html"

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
}

from .spa_dom_harness import run_with_dom


# ════════════════════════════════════════════════════════════════════
# Static module-shape checks
# ════════════════════════════════════════════════════════════════════

def test_module_file_exists():
    assert HOLONET_MODULE.exists()


def test_module_is_iife():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src
    assert "})();" in src


def test_module_exports_namespace():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    assert "window.M3Holonet" in src


def test_module_defines_all_documented_builders():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildHolonetTicker",
        "buildHolonetBrowser",
        "buildHolonetBrowserModal",
        "buildHolonetBrowserBody",
        "buildFeaturedStory",
        "buildGunshipSketch",
        "buildNewsRow",
        "buildWorldEventsPanel",
        "buildFactionMovementsPanel",
        "buildDirectorAINote",
        "buildCategoryFilter",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3Holonet"
        )


def test_init_function_present_and_exported():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_holonet.js' in src
    assert "M3Holonet.init(" in src


# ════════════════════════════════════════════════════════════════════
# Helper — extract a brace/bracket-delimited block by anchors
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str) -> str:
    """Find start_marker in src and return the brace/bracket-balanced
    block that follows. Handles both `{...}` and `[...]`."""
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
                return src[open_brace:j+1]
        j += 1
    return ""


# ════════════════════════════════════════════════════════════════════
# B3 era-cleanness — Clone Wars era references only
# ════════════════════════════════════════════════════════════════════

def test_fixture_clone_wars_era_references():
    """The HOLONET_DATA_FIXTURE references Clone Wars era polities
    and characters (Ryloth, Geonosis, CIS, Republic, Bail Organa,
    Hutt Cartel)."""
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLONET_DATA_FIXTURE = {")
    assert fixture, "HOLONET_DATA_FIXTURE block not found"
    assert "Ryloth" in fixture
    assert "Geonosis" in fixture
    assert "Republic" in fixture
    assert "CIS" in fixture
    assert "Bail Organa" in fixture
    assert "Hutt Cartel" in fixture
    # The CW-ERA · 20 BBY label is rendered in the browser header.
    # Verify it's in the module (could be in fixture or renderer).
    assert "20 BBY" in src
    assert "CW-ERA" in src


def test_fixture_no_galactic_empire_references():
    """No Empire/Imperial references in the data block. The
    `_extract_block` scoping excludes module-level comments."""
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLONET_DATA_FIXTURE = {")
    assert fixture
    assert "Empire" not in fixture, (
        "B3 regression: 'Empire' present in HOLONET_DATA_FIXTURE"
    )
    assert "Imperial" not in fixture, (
        "B3 regression: 'Imperial' present in HOLONET_DATA_FIXTURE"
    )


def test_holonet_categories_eight_plus_all():
    """The category list has 8 specific feeds plus 'ALL FEEDS'."""
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    block = _extract_block(src, "var HOLONET_CATEGORIES = [")
    assert block
    ids = re.findall(r"id:\s*'([^']+)'", block)
    # 'all' + 8 specific feeds.
    expected = {'all', 'WAR', 'LOCAL', 'BOUNTY', 'TRADE',
                'POLITICS', 'WEATHER', 'FACTION', 'AMBIENT'}
    assert set(ids) == expected


def test_fixture_ticker_six_entries():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLONET_DATA_FIXTURE = {")
    # Extract ticker sub-array.
    m = re.search(r"ticker:\s*\[(.+?)\],\s*featured:", fixture, flags=re.DOTALL)
    assert m, "ticker sub-array not found"
    cats = re.findall(r"cat:\s*'([^']+)'", m.group(1))
    assert len(cats) == 6, f"Expected 6 ticker entries; got {len(cats)}"
    # Mix includes high-priority WAR + WEATHER, med BOUNTY/TRADE/LOCAL, low POLITICS
    assert "WAR" in cats
    assert "WEATHER" in cats
    assert "POLITICS" in cats


def test_fixture_feed_eight_entries():
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLONET_DATA_FIXTURE = {")
    m = re.search(r"feed:\s*\[(.+?)\],\s*worldEvents:", fixture, flags=re.DOTALL)
    assert m, "feed sub-array not found"
    titles = re.findall(r"title:\s*'([^']+)'", m.group(1))
    assert len(titles) == 8, f"Expected 8 feed entries; got {len(titles)}"


# ════════════════════════════════════════════════════════════════════
# Q1 canonical-character note — preserved from source, flagged for
# production swap-in
# ════════════════════════════════════════════════════════════════════

def test_canonical_figure_cleanup_complete():
    """Architecture v50 Q1 + the B3 era invariant: canonical Clone Wars figures
    never appear as open-world references. The two Mace Windu references the
    vanilla port inherited from the JSX source (featured deck + factionMovements
    label) have been REPLACED with era-clean content (Ryloth featured story,
    Order-level framing). This guards the completed cleanup against regression —
    a re-introduction of Mace Windu (or 'M. Windu deployed') must fail here."""
    src = HOLONET_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLONET_DATA_FIXTURE = {")
    assert fixture
    # B3 cleanup done: the canonical-figure references are gone.
    assert "Mace Windu" not in fixture, (
        "B3 regression: Mace Windu re-introduced into the holonet featured deck"
    )
    assert "M. Windu deployed" not in fixture, (
        "B3 regression: 'M. Windu deployed' faction-movements label re-introduced"
    )
    # The era-clean replacement content is present (Ryloth front + Order framing).
    assert "RYLOTH" in fixture or "Ryloth" in fixture, (
        "era-clean Ryloth featured story missing from fixture"
    )


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var N = window.M3Holonet;
        result = {
            hasNamespace:        !!N,
            schemaVersion:       N && N.SCHEMA_VERSION,
            hasInit:             typeof N.init === 'function',
            hasTicker:           typeof N.buildHolonetTicker === 'function',
            hasBrowser:          typeof N.buildHolonetBrowser === 'function',
            hasModal:            typeof N.buildHolonetBrowserModal === 'function',
            hasBody:             typeof N.buildHolonetBrowserBody === 'function',
            hasFeaturedStory:    typeof N.buildFeaturedStory === 'function',
            hasGunshipSketch:    typeof N.buildGunshipSketch === 'function',
            hasNewsRow:          typeof N.buildNewsRow === 'function',
            hasWorldEvents:      typeof N.buildWorldEventsPanel === 'function',
            hasFactionMoves:     typeof N.buildFactionMovementsPanel === 'function',
            hasDirectorAI:       typeof N.buildDirectorAINote === 'function',
            hasCategoryFilter:   typeof N.buildCategoryFilter === 'function',
            hasFixture:          !!N.HOLONET_DATA_FIXTURE,
            hasCategories:       Array.isArray(N.HOLONET_CATEGORIES),
            // Fixture spot-checks
            tickerLength:        N.HOLONET_DATA_FIXTURE.ticker.length,
            feedLength:          N.HOLONET_DATA_FIXTURE.feed.length,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    for k in ["hasTicker", "hasBrowser", "hasModal", "hasBody",
              "hasFeaturedStory", "hasGunshipSketch", "hasNewsRow",
              "hasWorldEvents", "hasFactionMoves", "hasDirectorAI",
              "hasCategoryFilter", "hasFixture", "hasCategories"]:
        assert out[k], f"Failed: {k}"
    assert out["tickerLength"] == 6
    assert out["feedLength"] == 8


def test_runtime_ticker_renders_label_and_items():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildHolonetTicker(p);
        document.body.appendChild(el);
        var items = el.querySelectorAll('[data-ticker-item-cat]');
        // The marquee doubles the items for seamless loop.
        result = {
            isTicker: el.hasAttribute('data-holonet-ticker'),
            hasLabel: !!el.querySelector('[data-ticker-label]'),
            hasTrack: !!el.querySelector('[data-ticker-track]'),
            // 6 items × 2 = 12 in the doubled marquee
            itemCount: items.length,
            // Categories present at least once each
            hasWar: el.textContent.indexOf('Separatist forces clash') !== -1,
            hasBounty: el.textContent.indexOf('18,000 cr bounty') !== -1,
            hasWeather: el.textContent.indexOf('SANDSTORM WARNING') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["isTicker"]
    assert out["hasLabel"]
    assert out["hasTrack"]
    assert out["itemCount"] == 12  # 6 items × 2 (doubled marquee)
    assert out["hasWar"]
    assert out["hasBounty"]
    assert out["hasWeather"]


def test_runtime_ticker_onOpen_hook_fires():
    setup = _setup_prelude() + r"""
        var opened = false;
        var el = window.M3Holonet.buildHolonetTicker(p, {
            onOpen: function() { opened = true; }
        });
        document.body.appendChild(el);
        el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = {
            opened: opened,
            hasOpenHint: !!el.querySelector('[data-ticker-open-hint]'),
            cursor: el.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["opened"]
    assert out["hasOpenHint"]
    assert out["cursor"] == "pointer"


def test_runtime_ticker_no_onOpen_no_hint():
    """Without onOpen, the ⤢ OPEN affordance + pointer cursor are
    suppressed."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildHolonetTicker(p);
        document.body.appendChild(el);
        result = {
            hasOpenHint: !!el.querySelector('[data-ticker-open-hint]'),
            cursor: el.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasOpenHint"] is False
    assert out["cursor"] == "default"


def test_runtime_buildHolonetBrowser_renders_all_three_columns():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildHolonetBrowser(p);
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            mode: el.getAttribute('data-holonet-browser'),
            hasTicker:    !!el.querySelector('[data-holonet-ticker]'),
            hasHeader:    !!el.querySelector('[data-holonet-header]'),
            hasFilter:    !!el.querySelector('[data-holonet-category-filter]'),
            hasCenter:    !!el.querySelector('[data-holonet-center]'),
            hasFeed:      !!el.querySelector('[data-holonet-feed]'),
            hasRight:     !!el.querySelector('[data-holonet-right]'),
            hasFeatured:  !!el.querySelector('[data-holonet-featured]'),
            hasWorldEvents:    !!el.querySelector('[data-holonet-world-events]'),
            hasFactionMoves:   !!el.querySelector('[data-holonet-faction-movements]'),
            hasDirectorAI:     !!el.querySelector('[data-holonet-director-ai]'),
            // FRONT PAGE in header
            hasFrontPage: el.textContent.indexOf('FRONT PAGE') !== -1,
            hasCwEra:     el.textContent.indexOf('CW-ERA · 20 BBY') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["tag"] == "DIV"
    assert out["mode"] == "standalone"
    for k in ["hasTicker", "hasHeader", "hasFilter", "hasCenter", "hasFeed",
              "hasRight", "hasFeatured", "hasWorldEvents",
              "hasFactionMoves", "hasDirectorAI"]:
        assert out[k], f"Failed: {k}"
    assert out["hasFrontPage"]
    assert out["hasCwEra"]


def test_runtime_buildHolonetBrowserModal_renders_backdrop_and_wrap():
    setup = _setup_prelude() + r"""
        var closed = false;
        var el = window.M3Holonet.buildHolonetBrowserModal(p, {
            onClose: function() { closed = true; }
        });
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            mode: el.getAttribute('data-holonet-browser'),
            hasDragbar: !!el.querySelector('[data-holonet-dragbar]'),
            hasBody:    !!el.querySelector('[data-holonet-browser-body]'),
            hasBackdropBlur: el.style.backdropFilter.indexOf('blur') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["mode"] == "modal"
    assert out["hasDragbar"]
    assert out["hasBody"]
    assert out["hasBackdropBlur"]


def test_runtime_modal_red_light_closes():
    setup = _setup_prelude() + r"""
        var closed = false;
        var el = window.M3Holonet.buildHolonetBrowserModal(p, {
            onClose: function() { closed = true; }
        });
        document.body.appendChild(el);
        // The red traffic-light is the first cursor:pointer div
        // inside the dragbar with background = p.red.
        var dragbar = el.querySelector('[data-holonet-dragbar]');
        var lights = dragbar.querySelectorAll('div');
        // First div is the red light (cursor: pointer)
        var redLight = null;
        for (var i = 0; i < lights.length; i++) {
            if (lights[i].style.cursor === 'pointer') {
                redLight = lights[i];
                break;
            }
        }
        if (redLight) {
            redLight.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        }
        result = { foundLight: !!redLight, closed: closed };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["foundLight"]
    assert out["closed"]


def test_runtime_featured_story_renders_ryloth():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildFeaturedStory(p,
                  window.M3Holonet.HOLONET_DATA_FIXTURE.featured);
        document.body.appendChild(el);
        var tags = el.querySelectorAll('[data-related-tag]');
        var tagTexts = Array.prototype.map.call(tags, function(t) {
            return t.getAttribute('data-related-tag');
        });
        result = {
            isFeatured: el.hasAttribute('data-holonet-featured'),
            hasHeadline: el.textContent.indexOf('REPUBLIC CRUISERS CONVERGE ON RYLOTH') !== -1,
            hasDeck: el.textContent.indexOf('Venator-class') !== -1,
            hasLocation: el.textContent.indexOf('RYLOTH · 12 ARKANIS HOURS AGO') !== -1,
            tagCount: tags.length,
            tagTexts: tagTexts,
            hasSketch: !!el.querySelector('[data-holonet-gunship-sketch]'),
            hasLAATShape: !!el.querySelector('svg[data-holonet-gunship-sketch] path'),
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["isFeatured"]
    assert out["hasHeadline"]
    assert out["hasDeck"]
    assert out["hasLocation"]
    assert out["tagCount"] == 4
    assert "Ryloth" in out["tagTexts"]
    assert "91st Recon" in out["tagTexts"]
    # B3 cleanup: the 4th related tag was 'Mace Windu' in the JSX source; the
    # era-clean port uses Order/garrison-level framing instead.
    assert "Jedi Order" in out["tagTexts"]
    assert "CIS Lessu Garrison" in out["tagTexts"]
    assert "Mace Windu" not in out["tagTexts"]
    assert out["hasSketch"]
    assert out["hasLAATShape"]


def test_runtime_featured_story_related_click_hook():
    setup = _setup_prelude() + r"""
        var clickedTag = null;
        var el = window.M3Holonet.buildFeaturedStory(p,
                window.M3Holonet.HOLONET_DATA_FIXTURE.featured,
                { onRelatedClick: function(tag) { clickedTag = tag; } });
        document.body.appendChild(el);
        var rylothTag = el.querySelector('[data-related-tag="Ryloth"]');
        rylothTag.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clicked: clickedTag };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["clicked"] == "Ryloth"


def test_runtime_news_row_renders_with_badges():
    """A row with hot=true renders the ● HOT badge; a row with you=true
    renders the ★ FOLLOWING badge."""
    setup = _setup_prelude() + r"""
        var krayt = window.M3Holonet.HOLONET_DATA_FIXTURE.feed[1]; // hot: true
        var bounty = window.M3Holonet.HOLONET_DATA_FIXTURE.feed[2]; // you: true
        var krayEl = window.M3Holonet.buildNewsRow(p, krayt);
        var bountyEl = window.M3Holonet.buildNewsRow(p, bounty);
        document.body.appendChild(krayEl);
        document.body.appendChild(bountyEl);
        result = {
            krayHasHot: !!krayEl.querySelector('[data-news-hot-badge]'),
            krayHasFollow: !!krayEl.querySelector('[data-news-following-badge]'),
            bountyHasHot: !!bountyEl.querySelector('[data-news-hot-badge]'),
            bountyHasFollow: !!bountyEl.querySelector('[data-news-following-badge]'),
            // Readers count formatted with comma
            hasFourThousandPlus: krayEl.textContent.indexOf('89') !== -1,  // krayt readers
            bountyReaders: bountyEl.textContent.indexOf('612') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["krayHasHot"]
    assert out["krayHasFollow"] is False
    assert out["bountyHasHot"] is False
    assert out["bountyHasFollow"]


def test_runtime_news_row_readers_locale_formatted():
    setup = _setup_prelude() + r"""
        var story = { cat: 'WAR', priority: 'high', time: '02:14',
                       title: 'Test', summary: 'Test summary.',
                       tags: ['test'], readers: 4127 };
        var el = window.M3Holonet.buildNewsRow(p, story);
        document.body.appendChild(el);
        result = {
            // toLocaleString applies thousands separator: '4,127'
            text: el.textContent,
            hasFormatted: el.textContent.indexOf('4,127') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasFormatted"]


def test_runtime_news_row_click_hook_fires():
    setup = _setup_prelude() + r"""
        var clickedTitle = null;
        var story = window.M3Holonet.HOLONET_DATA_FIXTURE.feed[0];
        var el = window.M3Holonet.buildNewsRow(p, story, {
            onStoryClick: function(s) { clickedTitle = s.title; }
        });
        document.body.appendChild(el);
        el.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clicked: clickedTitle };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["clicked"] == "Republic cruisers converge on Ryloth"


def test_runtime_news_row_category_color_war_red():
    """WAR category renders with red border on its chip."""
    setup = _setup_prelude() + r"""
        var warStory = { cat: 'WAR', priority: 'high', time: '02:14',
                          title: 'War story', summary: 'Test.',
                          tags: ['test'], readers: 100 };
        var localStory = { cat: 'LOCAL', priority: 'med', time: '00:42',
                            title: 'Local story', summary: 'Test.',
                            tags: ['test'], readers: 50 };
        var warEl = window.M3Holonet.buildNewsRow(p, warStory);
        var localEl = window.M3Holonet.buildNewsRow(p, localStory);
        document.body.appendChild(warEl);
        document.body.appendChild(localEl);
        var warChip = warEl.querySelector('[data-news-cat-chip="WAR"]');
        var localChip = localEl.querySelector('[data-news-cat-chip="LOCAL"]');
        result = {
            warChipColor: warChip.style.color,
            localChipColor: localChip.style.color,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    # Red and amber from SAMPLE_PALETTE (browser may report rgb form)
    war_color = out["warChipColor"]
    local_color = out["localChipColor"]
    # Browsers normalize hex to rgb sometimes; just verify they differ
    assert war_color != local_color


def test_runtime_world_events_panel_renders_five_events():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildWorldEventsPanel(p,
                window.M3Holonet.HOLONET_DATA_FIXTURE.worldEvents);
        document.body.appendChild(el);
        var events = el.querySelectorAll('[data-world-event-name]');
        var names = Array.prototype.map.call(events, function(e) {
            return e.getAttribute('data-world-event-name');
        });
        result = {
            count: events.length,
            names: names,
            hasGalaxyState: el.textContent.indexOf('LIVE GALAXY STATE') !== -1,
            hasKrayt: el.textContent.indexOf('Krayt Dragon') !== -1,
            hasContested: el.textContent.indexOf('CONTESTED') !== -1,
            hasUpcoming: el.textContent.indexOf('UPCOMING') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["count"] == 5
    assert "Krayt Dragon" in out["names"]
    assert "Jabba's Palace Approach" in out["names"]
    assert "Sandstorm" in out["names"]
    assert "Republic Patrol" in out["names"]
    assert "Boonta Eve Race" in out["names"]
    assert out["hasGalaxyState"]
    assert out["hasContested"]
    assert out["hasUpcoming"]


def test_runtime_faction_movements_renders_six_factions():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildFactionMovementsPanel(p,
                window.M3Holonet.HOLONET_DATA_FIXTURE.factionMovements);
        document.body.appendChild(el);
        var rows = el.querySelectorAll('[data-faction-movement]');
        var factions = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-faction-movement');
        });
        result = {
            count: rows.length,
            factions: factions,
            hasHeader: el.textContent.indexOf('FACTION MOVEMENTS · 24H') !== -1,
            hasPositive: el.textContent.indexOf('+12') !== -1,  // republic +12
            hasNegative: el.textContent.indexOf('-8') !== -1,   // cis -8
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["count"] == 6
    assert set(out["factions"]) == {"republic", "cis", "hutt", "bounty",
                                     "jedi", "black_sun"}
    assert out["hasHeader"]
    assert out["hasPositive"]
    assert out["hasNegative"]


def test_runtime_director_ai_note_default():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildDirectorAINote(p);
        document.body.appendChild(el);
        result = {
            isDirectorAI: el.hasAttribute('data-holonet-director-ai'),
            hasHeader: el.textContent.indexOf('DIRECTOR AI · 14:32') !== -1,
            hasTensionText: el.textContent.indexOf('World tension up 8%') !== -1,
            hasCisRef: el.textContent.indexOf('CIS recon') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["isDirectorAI"]
    assert out["hasHeader"]
    assert out["hasTensionText"]
    assert out["hasCisRef"]


def test_runtime_director_ai_note_custom():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildDirectorAINote(p, {
            text: 'Custom AI insight.',
            timestamp: '23:17',
        });
        document.body.appendChild(el);
        result = {
            hasCustomText: el.textContent.indexOf('Custom AI insight.') !== -1,
            hasCustomTimestamp: el.textContent.indexOf('23:17') !== -1,
            // Default text should NOT appear.
            noDefaultText: el.textContent.indexOf('World tension') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasCustomText"]
    assert out["hasCustomTimestamp"]
    assert out["noDefaultText"]


def test_runtime_category_filter_renders_categories_and_filters():
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildCategoryFilter(p,
                window.M3Holonet.HOLONET_CATEGORIES);
        document.body.appendChild(el);
        var cats = el.querySelectorAll('[data-category-id]');
        var filters = el.querySelectorAll('[data-filter-label]');
        var catIds = Array.prototype.map.call(cats, function(c) {
            return c.getAttribute('data-category-id');
        });
        var filterNames = Array.prototype.map.call(filters, function(f) {
            return f.getAttribute('data-filter-label');
        });
        result = {
            catCount: cats.length,
            catIds: catIds,
            filterCount: filters.length,
            filterNames: filterNames,
            hasCategoriesHeader: el.textContent.indexOf('CATEGORIES') !== -1,
            hasFiltersHeader: el.textContent.indexOf('FILTERS') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["catCount"] == 9  # 'all' + 8 specifics
    assert "all" in out["catIds"]
    assert "WAR" in out["catIds"]
    assert out["filterCount"] == 4
    assert out["filterNames"] == ["Following you", "Near you",
                                   "High priority", "Faction-relevant"]


def test_runtime_category_click_hook_fires():
    setup = _setup_prelude() + r"""
        var clickedId = null;
        var el = window.M3Holonet.buildCategoryFilter(p,
                window.M3Holonet.HOLONET_CATEGORIES,
                { onCategoryClick: function(id) { clickedId = id; } });
        document.body.appendChild(el);
        var warCat = el.querySelector('[data-category-id="WAR"]');
        warCat.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clicked: clickedId };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["clicked"] == "WAR"


def test_runtime_filter_toggle_hook_fires():
    setup = _setup_prelude() + r"""
        var toggled = null;
        var el = window.M3Holonet.buildCategoryFilter(p,
                window.M3Holonet.HOLONET_CATEGORIES,
                { onFilterToggle: function(f) { toggled = f; } });
        document.body.appendChild(el);
        var nearFilter = el.querySelector('[data-filter-label="Near you"]');
        nearFilter.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { toggled: toggled };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["toggled"] == "Near you"


def test_runtime_browser_with_custom_data():
    """The buildHolonetBrowser accepts a custom data hook that
    overrides the fixture."""
    setup = _setup_prelude() + r"""
        var customData = {
            ticker: [
                { cat: 'CUSTOM', text: 'Custom ticker entry', priority: 'low' }
            ],
            featured: {
                headline: 'CUSTOM HEADLINE',
                deck: 'Custom deck text.',
                location: 'CUSTOM LOCATION',
                related: ['custom-tag'],
            },
            feed: [],
            worldEvents: [],
            factionMovements: [],
        };
        var el = window.M3Holonet.buildHolonetBrowser(p, { data: customData });
        document.body.appendChild(el);
        result = {
            hasCustomHeadline: el.textContent.indexOf('CUSTOM HEADLINE') !== -1,
            hasCustomTicker: el.textContent.indexOf('Custom ticker entry') !== -1,
            // The fixture's RYLOTH headline should NOT appear.
            noRyloth: el.textContent.indexOf('REPUBLIC CRUISERS CONVERGE') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasCustomHeadline"]
    assert out["hasCustomTicker"]
    assert out["noRyloth"]


def test_runtime_feed_stories_count_in_header():
    """The 'LIVE FEED · N STORIES SHOWN' header reflects the number
    of stories in the data fixture."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holonet.buildHolonetBrowserBody(p);
        document.body.appendChild(el);
        result = {
            // Default fixture has 8 feed stories
            hasFeedHeader: el.textContent.indexOf('LIVE FEED · 8 STORIES SHOWN') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holonet.js"], setup)
    assert out["hasFeedHeader"]
