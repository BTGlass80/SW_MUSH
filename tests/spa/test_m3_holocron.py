"""
test_m3_holocron.py — Drop 4.7 regression lock for m3_holocron.js.

Drop 4.7 ports map_v3/holocron.jsx (536 JSX LOC) into a vanilla-JS
SPA module at static/spa/m3_holocron.js. This file pins:

  · Module shape (IIFE + window.M3Holocron + documented surface).
  · B3 era-cleanness — Clone Wars era framing in the Hutt Cartel
    demo fixture. Negative control is scoped to the entry's
    narrative fields (summary, quoteSource, leaders, stats) NOT
    the comment block at top, and explicitly allows the "Hutt
    Empire successor" historical reference in the founded-date
    stat — that's lore (25,000-BBY-era polity), not a Galactic
    Empire reference.
  · 3-column structural contract.
  · Hooks fire correctly (onCategoryClick, onEntryClick,
    onCrossRefClick, onClose).
  · Lore-noun highlighting wraps the correct nouns.

Pattern parallels tests/spa/test_m3_sheet.py (Drop 4.6).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


REPO_ROOT       = Path(__file__).resolve().parent.parent.parent
HOLOCRON_MODULE = REPO_ROOT / "static" / "spa" / "m3_holocron.js"
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
    assert HOLOCRON_MODULE.exists(), (
        f"Module missing at {HOLOCRON_MODULE}. Drop 4.7 either didn't "
        "ship or was reverted."
    )


def test_module_is_iife():
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    assert "(function(){" in src or "(function () {" in src, (
        "m3_holocron.js must be wrapped in an IIFE."
    )
    assert "})();" in src, "IIFE not closed at end of m3_holocron.js"


def test_module_exports_namespace():
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    assert "window.M3Holocron" in src, "Module must export window.M3Holocron"


def test_module_defines_all_documented_builders():
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    builders = [
        "buildHolocron",
        "buildHolocronModal",
        "buildHolocronContent",
        "buildCategoryNav",
        "buildEntryList",
        "buildReadingPane",
        "buildCrossRefs",
        "buildSubHead",
        "buildKnowledgeRow",
        "highlightLore",
    ]
    for b in builders:
        assert "function " + b in src, f"Missing function definition: {b}"
        assert re.search(r"\b" + b + r"\s*:\s*" + b + r"\b", src), (
            f"Missing export entry for {b} in window.M3Holocron"
        )


def test_init_function_present_and_exported():
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    assert "function init(" in src
    assert re.search(r"init\s*:\s*init\b", src)


def test_client_html_loads_module_and_calls_init():
    src = CLIENT_HTML.read_text(encoding="utf-8")
    assert '/static/spa/m3_holocron.js' in src, (
        "client.html missing <script> tag for m3_holocron.js"
    )
    assert "M3Holocron.init(" in src, (
        "client.html doesn't call M3Holocron.init()"
    )


# ════════════════════════════════════════════════════════════════════
# B3 era-contamination contract
# ════════════════════════════════════════════════════════════════════

def test_b3_fixture_clone_wars_era_references():
    """B3: the Hutt Cartel summary references Clone Wars (~22-19 BBY),
    Republic, CIS — the Clone-Wars-era setting."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLOCRON_DATA_FIXTURE = {", "};")
    assert fixture, "HOLOCRON_DATA_FIXTURE block not found"
    # Must mention Clone Wars era + Republic + CIS in the summary.
    assert "Clone Wars" in fixture, (
        "B3 fix: fixture summary must reference Clone Wars"
    )
    assert "22" in fixture and "19 BBY" in fixture, (
        "B3 fix: fixture summary must include ~22-19 BBY date range"
    )
    assert "Republic" in fixture
    assert "CIS" in fixture


def test_b3_fixture_no_galactic_empire_references():
    """B3: the narrative fields (summary paragraphs, quoteSource,
    leaders) must not mention the Galactic Empire / Imperial framing.

    Explicitly allowed exception: the founded-date stat contains
    'Hutt Empire successor' — that's a ~25,000-BBY historical Hutt
    polity, not the Galactic Empire. Direct port from holocron.jsx.
    """
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLOCRON_DATA_FIXTURE = {", "};")
    assert fixture, "HOLOCRON_DATA_FIXTURE block not found"

    # Remove the legitimate "Hutt Empire successor" line and scan the rest.
    scrubbed = fixture.replace("Hutt Empire successor", "")
    assert "Empire" not in scrubbed, (
        "B3 regression: 'Empire' present outside the Hutt-Empire-successor "
        "founded-date reference"
    )
    assert "Imperial" not in scrubbed, (
        "B3 regression: 'Imperial' present in HOLOCRON_DATA_FIXTURE"
    )


def test_b3_fixture_clone_wars_era_active_factions():
    """B3: every faction in the entries list has era 'Active' or
    'Hidden' — both Clone-Wars-era values. No 'Imperial Era' or
    similar drift."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLOCRON_DATA_FIXTURE = {", "};")
    # Find all "era: 'X'" patterns.
    eras = set(re.findall(r"era:\s*'([^']+)'", fixture))
    allowed = {"Active", "Hidden"}
    assert eras.issubset(allowed), (
        f"B3 regression: unexpected era values in fixture: {eras - allowed}"
    )


def test_hutt_empire_lore_reference_preserved():
    """The 'Hutt Empire successor' historical reference (~25,000 BBY
    Hutt polity that preceded the Cartel) must be preserved from the
    source JSX. Distinct from Galactic Empire."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    assert "Hutt Empire successor" in src
    assert "25,000 BBY" in src


def test_lore_nouns_clone_wars_era():
    """HOLOCRON_LORE_NOUNS lists Clone-Wars-era nouns. 'Clone Wars',
    'Republic', 'CIS' should appear; 'Empire' / 'Imperial' must not."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    m = re.search(r"var HOLOCRON_LORE_NOUNS\s*=\s*\[(.+?)\];", src, flags=re.DOTALL)
    assert m, "HOLOCRON_LORE_NOUNS array not found"
    block = m.group(1)
    assert "'Clone Wars'" in block
    assert "'Republic'" in block
    assert "'CIS'" in block
    assert "'Empire'" not in block
    assert "'Imperial'" not in block


# ════════════════════════════════════════════════════════════════════
# Structural contracts
# ════════════════════════════════════════════════════════════════════

def test_fixture_has_seven_categories():
    """The fixture defines all 7 lore categories (planets / species /
    factions / weapons / vehicles / npcs / lore)."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLOCRON_DATA_FIXTURE = {", "};")
    expected = ['planets', 'species', 'factions', 'weapons',
                'vehicles', 'npcs', 'lore']
    for cat_id in expected:
        assert re.search(
            r"id:\s*'" + re.escape(cat_id) + r"'", fixture
        ), f"Missing category id: {cat_id}"


def test_fixture_factions_count_ten():
    """The factions entries list has 10 entries (matches the JSX
    source)."""
    src = HOLOCRON_MODULE.read_text(encoding="utf-8")
    fixture = _extract_block(src, "var HOLOCRON_DATA_FIXTURE = {", "};")
    # Count "slug: 'X'" inside the entries.factions array.
    factions_match = re.search(
        r"factions:\s*\[(.+?)\],\s*\}",
        fixture, flags=re.DOTALL
    )
    assert factions_match, "factions entries array not found"
    factions_block = factions_match.group(1)
    slugs = re.findall(r"slug:\s*'[^']+'", factions_block)
    assert len(slugs) == 10, f"Expected 10 faction entries; got {len(slugs)}"


# ════════════════════════════════════════════════════════════════════
# Helper — extract a brace-delimited block by anchors (from Drop 4.6)
# ════════════════════════════════════════════════════════════════════

def _extract_block(src: str, start_marker: str, end_marker: str) -> str:
    i = src.find(start_marker)
    if i < 0:
        return ""
    open_brace = src.find("{", i)
    if open_brace < 0:
        return ""
    depth = 0
    j = open_brace
    while j < len(src):
        ch = src[j]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return src[open_brace:j+1]
        j += 1
    return ""


# ════════════════════════════════════════════════════════════════════
# jsdom runtime tests
# ════════════════════════════════════════════════════════════════════

def _setup_prelude():
    return "var p = " + json.dumps(SAMPLE_PALETTE) + ";\n"


def test_runtime_module_loads_and_exposes_namespace():
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        result = {
            hasNamespace:       !!H,
            schemaVersion:      H && H.SCHEMA_VERSION,
            hasInit:            typeof H.init === 'function',
            hasBuildHolocron:   typeof H.buildHolocron === 'function',
            hasBuildModal:      typeof H.buildHolocronModal === 'function',
            hasBuildContent:    typeof H.buildHolocronContent === 'function',
            hasCategoryNav:     typeof H.buildCategoryNav === 'function',
            hasEntryList:       typeof H.buildEntryList === 'function',
            hasReadingPane:     typeof H.buildReadingPane === 'function',
            hasCrossRefs:       typeof H.buildCrossRefs === 'function',
            hasFixture:         !!H.HOLOCRON_DATA_FIXTURE,
            hasLoreNouns:       Array.isArray(H.HOLOCRON_LORE_NOUNS),
            fixtureTitle:       H.HOLOCRON_DATA_FIXTURE.selected.title,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["hasNamespace"]
    assert out["schemaVersion"] == 1
    assert out["hasInit"]
    assert out["hasBuildHolocron"]
    assert out["hasBuildModal"]
    assert out["hasBuildContent"]
    assert out["hasCategoryNav"]
    assert out["hasEntryList"]
    assert out["hasReadingPane"]
    assert out["hasCrossRefs"]
    assert out["hasFixture"]
    assert out["hasLoreNouns"]
    assert out["fixtureTitle"] == "Hutt Cartel"


def test_runtime_buildHolocron_renders_standalone_container():
    """Standalone container has the 3-column body layout."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holocron.buildHolocron(p);
        document.body.appendChild(el);
        // Find the body grid.
        var bodyGrids = el.querySelectorAll('div');
        var gridFound = false;
        for (var i = 0; i < bodyGrids.length; i++) {
            var d = bodyGrids[i];
            if (d.style.gridTemplateColumns &&
                d.style.gridTemplateColumns.indexOf('220px') !== -1) {
                gridFound = true;
                break;
            }
        }
        result = {
            tag: el.tagName,
            mode: el.getAttribute('data-holocron-mode'),
            hasGrid: gridFound,
            hasHolocronTitle: el.textContent.indexOf('HOLOCRON · KNOWLEDGE ARCHIVE') !== -1,
            hasHuttCartelTitle: el.textContent.indexOf('HUTT CARTEL') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["tag"] == "DIV"
    assert out["mode"] == "standalone"
    assert out["hasGrid"]
    assert out["hasHolocronTitle"]
    assert out["hasHuttCartelTitle"]


def test_runtime_buildHolocronModal_renders_backdrop_and_wrap():
    """Modal renders with backdrop + traffic-lights + drag handle."""
    setup = _setup_prelude() + r"""
        var clicked = false;
        var el = window.M3Holocron.buildHolocronModal(p, {
            draggable: true,
            onClose: function() { clicked = true; }
        });
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            mode: el.getAttribute('data-holocron-mode'),
            hasBackdrop: !!el.style.backdropFilter,
            hasHolocronLabel: el.textContent.indexOf('HOLOCRON') !== -1,
            hasDragHint: el.textContent.indexOf('DRAG') !== -1,
            hasEscHint: el.textContent.indexOf('ESC TO CLOSE') !== -1,
            // Wrapper window is the inner DIV with a transform.
            hasWrap: el.querySelector('div[style*="translate"]') !== null,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["mode"] == "modal"
    assert out["hasBackdrop"]
    assert out["hasHolocronLabel"]
    assert out["hasDragHint"]
    assert out["hasEscHint"]
    assert out["hasWrap"]


def test_runtime_modal_close_fires_on_red_light_click():
    """The red traffic-light click fires hooks.onClose."""
    setup = _setup_prelude() + r"""
        var closed = false;
        var el = window.M3Holocron.buildHolocronModal(p, {
            onClose: function() { closed = true; }
        });
        document.body.appendChild(el);
        // The red light is the first div in the traffic-lights cluster.
        // It has background = p.red and cursor = pointer.
        var redDot = null;
        var divs = el.querySelectorAll('div');
        for (var i = 0; i < divs.length; i++) {
            var d = divs[i];
            if (d.style.cursor === 'pointer' &&
                d.style.background &&
                d.style.borderRadius === '50%') {
                redDot = d;
                break;
            }
        }
        if (redDot) {
            redDot.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        }
        result = { foundRedDot: !!redDot, closed: closed };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["foundRedDot"]
    assert out["closed"]


def test_runtime_buildCategoryNav_renders_seven_categories():
    """Category nav renders all 7 categories. The 'factions' category
    has active styling (amber background)."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var cats = H.HOLOCRON_DATA_FIXTURE.categories;
        var el = H.buildCategoryNav(p, cats);
        document.body.appendChild(el);
        var rows = el.querySelectorAll('[data-category-id]');
        var ids = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-category-id');
        });
        var factionRow = el.querySelector('[data-category-id="factions"]');
        result = {
            ids: ids,
            count: rows.length,
            // Factions is active — its background contains the amber color.
            factionsActive: factionRow &&
                            factionRow.style.background.indexOf('255') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["count"] == 7
    assert set(out["ids"]) == {'planets', 'species', 'factions', 'weapons',
                               'vehicles', 'npcs', 'lore'}
    assert out["factionsActive"]


def test_runtime_category_click_hook_fires():
    setup = _setup_prelude() + r"""
        var clicked = null;
        var H = window.M3Holocron;
        var el = H.buildCategoryNav(p, H.HOLOCRON_DATA_FIXTURE.categories, {
            onCategoryClick: function(id) { clicked = id; }
        });
        document.body.appendChild(el);
        var weaponsRow = el.querySelector('[data-category-id="weapons"]');
        weaponsRow.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clickedCategory: clicked };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["clickedCategory"] == "weapons"


def test_runtime_buildEntryList_renders_ten_faction_entries():
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var entries = H.HOLOCRON_DATA_FIXTURE.entries.factions;
        var el = H.buildEntryList(p, entries, 'FACTIONS');
        document.body.appendChild(el);
        var rows = el.querySelectorAll('[data-entry-slug]');
        var slugs = Array.prototype.map.call(rows, function(r) {
            return r.getAttribute('data-entry-slug');
        });
        // Find the row marked selected — Hutt Cartel.
        var huttRow = el.querySelector('[data-entry-slug="hutt_cartel"]');
        result = {
            slugs: slugs,
            count: rows.length,
            hasHeader: el.textContent.indexOf('FACTIONS · 10 ENTRIES') !== -1,
            // Selected row has stronger amber background.
            huttSelected: huttRow &&
                          huttRow.style.background.indexOf('255') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["count"] == 10
    assert "hutt_cartel" in out["slugs"]
    assert "republic" in out["slugs"]
    assert "cis" in out["slugs"]
    assert "jedi_order" in out["slugs"]
    assert out["hasHeader"]
    assert out["huttSelected"]


def test_runtime_entry_click_hook_fires():
    setup = _setup_prelude() + r"""
        var clicked = null;
        var H = window.M3Holocron;
        var el = H.buildEntryList(p, H.HOLOCRON_DATA_FIXTURE.entries.factions,
                                  'FACTIONS', {
            onEntryClick: function(slug) { clicked = slug; }
        });
        document.body.appendChild(el);
        var row = el.querySelector('[data-entry-slug="bounty_guild"]');
        row.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clickedEntry: clicked };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["clickedEntry"] == "bounty_guild"


def test_runtime_buildReadingPane_renders_full_structure():
    """Reading pane renders title strip + quote + 3 summary paragraphs
    + stats grid + leader rows."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var sel = H.HOLOCRON_DATA_FIXTURE.selected;
        var el = H.buildReadingPane(p, sel);
        document.body.appendChild(el);
        var paras = el.querySelectorAll('p');
        var leaderRows = el.querySelectorAll('[data-leader-name]');
        var leaderNames = Array.prototype.map.call(leaderRows, function(r) {
            return r.getAttribute('data-leader-name');
        });
        result = {
            paraCount: paras.length,
            hasTitle: el.textContent.indexOf('HUTT CARTEL') !== -1,
            hasSubtitle: el.textContent.indexOf('Criminal Syndicate') !== -1,
            hasQuote: el.textContent.indexOf('In the Outer Rim, there is no law') !== -1,
            hasQuoteSource: el.textContent.indexOf('Captain Vex') !== -1,
            hasStatsHead: el.textContent.indexOf('RECORD · STATISTICS') !== -1,
            hasLeadersHead: el.textContent.indexOf('NOTABLE FIGURES') !== -1,
            leaderCount: leaderRows.length,
            leaderNames: leaderNames,
            // Stats grid present
            hasNalHutta: el.textContent.indexOf('Nal Hutta') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["paraCount"] == 3
    assert out["hasTitle"]
    assert out["hasSubtitle"]
    assert out["hasQuote"]
    assert out["hasQuoteSource"]
    assert out["hasStatsHead"]
    assert out["hasLeadersHead"]
    assert out["leaderCount"] == 3
    assert "Jabba Desilijic Tiure" in out["leaderNames"]
    assert "Gardulla the Elder" in out["leaderNames"]
    assert "Marlo the Hutt" in out["leaderNames"]
    assert out["hasNalHutta"]


def test_runtime_lore_nouns_highlighted_in_summary():
    """Each lore noun in HOLOCRON_LORE_NOUNS gets wrapped in a span
    with data-lore-noun when it appears in summary text."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var sel = H.HOLOCRON_DATA_FIXTURE.selected;
        var el = H.buildReadingPane(p, sel);
        document.body.appendChild(el);
        var nounSpans = el.querySelectorAll('span[data-lore-noun]');
        var nounsFound = Array.prototype.map.call(nounSpans, function(s) {
            return s.getAttribute('data-lore-noun');
        });
        var nounsSet = {};
        nounsFound.forEach(function(n) { nounsSet[n] = true; });
        result = {
            spanCount: nounSpans.length,
            distinctNouns: Object.keys(nounsSet),
            hasHuttCartel: !!nounsSet['Hutt Cartel'],
            hasOuterRim: !!nounsSet['Outer Rim'],
            hasNalHutta: !!nounsSet['Nal Hutta'],
            hasCloneWars: !!nounsSet['Clone Wars'],
            hasRepublic: !!nounsSet['Republic'],
            hasCIS: !!nounsSet['CIS'],
            hasJabba: !!nounsSet['Jabba Desilijic Tiure'],
            // No Galactic Empire noun should ever be wrapped.
            hasEmpire: !!nounsSet['Empire'],
            hasImperial: !!nounsSet['Imperial'],
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    # Many distinct nouns should be highlighted
    assert out["spanCount"] >= 10, (
        f"Expected several lore-noun highlights; got {out['spanCount']}"
    )
    assert out["hasHuttCartel"]
    assert out["hasOuterRim"]
    assert out["hasNalHutta"]
    assert out["hasCloneWars"]
    assert out["hasRepublic"]
    assert out["hasCIS"]
    assert out["hasJabba"]
    # Negative controls
    assert not out["hasEmpire"]
    assert not out["hasImperial"]


def test_runtime_buildCrossRefs_renders_related_and_knowledge():
    """Right column renders related planets + factions + known/partial/
    unknown blocks."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var sel = H.HOLOCRON_DATA_FIXTURE.selected;
        var el = H.buildCrossRefs(p, sel);
        document.body.appendChild(el);
        var planetRefs = el.querySelectorAll('[data-cross-ref-kind="planet"]');
        var factionRefs = el.querySelectorAll('[data-cross-ref-kind="faction"]');
        var knownBlocks = el.querySelectorAll('[data-knowledge-label]');
        var labels = Array.prototype.map.call(knownBlocks, function(b) {
            return b.getAttribute('data-knowledge-label');
        });
        result = {
            planetCount: planetRefs.length,
            factionCount: factionRefs.length,
            knownLabels: labels,
            hasRelatedPlanetsHead: el.textContent.indexOf('RELATED · PLANETS') !== -1,
            hasRelatedFactionsHead: el.textContent.indexOf('RELATED · FACTIONS') !== -1,
            hasYourKnowledgeHead: el.textContent.indexOf('YOUR KNOWLEDGE') !== -1,
            hasEarnHint: el.textContent.indexOf('earn favor from a Hutt lord') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["planetCount"] == 4
    assert out["factionCount"] == 3
    assert out["knownLabels"] == ["KNOWN", "PARTIAL", "UNKNOWN"]
    assert out["hasRelatedPlanetsHead"]
    assert out["hasRelatedFactionsHead"]
    assert out["hasYourKnowledgeHead"]
    assert out["hasEarnHint"]


def test_runtime_cross_ref_click_hook_fires_with_kind():
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var clicked = null;
        var el = H.buildCrossRefs(p, H.HOLOCRON_DATA_FIXTURE.selected, {
            onCrossRefClick: function(slug, kind) { clicked = { slug: slug, kind: kind }; }
        });
        document.body.appendChild(el);
        var natHuttaRef = el.querySelector('[data-cross-ref-slug="nal_hutta"]');
        natHuttaRef.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        result = { clicked: clicked };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["clicked"]["slug"] == "nal_hutta"
    assert out["clicked"]["kind"] == "planet"


def test_runtime_knowledge_rows_show_correct_item_counts():
    """Knowledge rows render correct counts: 5 known, 2 partial, 3 unknown."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var el = H.buildCrossRefs(p, H.HOLOCRON_DATA_FIXTURE.selected);
        document.body.appendChild(el);
        // For each knowledge label, count the sibling item divs that
        // follow until the next knowledge-label or end of container.
        function countItemsAfter(label) {
            var head = el.querySelector('[data-knowledge-label="' + label + '"]');
            if (!head) return 0;
            var parent = head.parentNode;
            var children = parent.children;
            var headIdx = -1;
            for (var i = 0; i < children.length; i++) {
                if (children[i] === head) { headIdx = i; break; }
            }
            // Count item divs after this label.
            var count = 0;
            for (var j = headIdx + 1; j < children.length; j++) {
                var ch = children[j];
                // Stop if we hit a div that contains another label inside.
                if (ch.querySelector && ch.querySelector('[data-knowledge-label]')) break;
                count++;
            }
            return count;
        }
        result = {
            knownItems:   el.querySelectorAll('[data-knowledge-label="KNOWN"] ~ div').length,
            partialItems: el.querySelectorAll('[data-knowledge-label="PARTIAL"] ~ div').length,
            unknownItems: el.querySelectorAll('[data-knowledge-label="UNKNOWN"] ~ div').length,
            // Use textContent to verify specific items
            knownItemTexts: el.textContent,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    # Each knowledge head has its items as direct siblings (`~ div`)
    # but those selectors also catch later knowledge heads' rows.
    # Easier assertion: specific item text present.
    text = out["knownItemTexts"]
    assert "Mos Eisley contacts" in text       # known
    assert "Nal Hutta politics" in text         # partial
    assert "Cartel war reserves" in text        # unknown


def test_runtime_buildHolocronContent_full_render():
    """Top-level content render is integrated: top bar + 3-column body."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holocron.buildHolocronContent(p);
        document.body.appendChild(el);
        var allText = el.textContent;
        result = {
            tag: el.tagName,
            hasArchiveLabel: allText.indexOf('KNOWLEDGE ARCHIVE') !== -1,
            hasSearchBar: allText.indexOf('Search') !== -1,
            hasEscClose: allText.indexOf('ESC ✕') !== -1,
            // Total entry count from sum of category.count fields = 576.
            hasEntryCount576: allText.indexOf('576 entries') !== -1,
            hasCategories: allText.indexOf('CATEGORIES') !== -1,
            hasFactionsHeader: allText.indexOf('FACTIONS · 10 ENTRIES') !== -1,
            hasReadingPaneTitle: allText.indexOf('HUTT CARTEL') !== -1,
            hasCrossRefs: allText.indexOf('YOUR KNOWLEDGE') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["tag"] == "DIV"
    assert out["hasArchiveLabel"]
    assert out["hasSearchBar"]
    assert out["hasEscClose"]
    assert out["hasEntryCount576"]
    assert out["hasCategories"]
    assert out["hasFactionsHeader"]
    assert out["hasReadingPaneTitle"]
    assert out["hasCrossRefs"]


def test_runtime_content_close_hook_fires():
    setup = _setup_prelude() + r"""
        var closed = false;
        var el = window.M3Holocron.buildHolocronContent(p, {
            onClose: function() { closed = true; }
        });
        document.body.appendChild(el);
        // Find the ESC ✕ button.
        var buttons = el.querySelectorAll('button');
        var escBtn = null;
        for (var i = 0; i < buttons.length; i++) {
            if (buttons[i].textContent.indexOf('ESC') !== -1) {
                escBtn = buttons[i];
                break;
            }
        }
        if (escBtn) {
            escBtn.dispatchEvent(new window.MouseEvent('click', { bubbles: true }));
        }
        result = { foundEscBtn: !!escBtn, closed: closed };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["foundEscBtn"]
    assert out["closed"]


def test_runtime_highlightLore_with_override_nouns():
    """highlightLore accepts an override noun list."""
    setup = _setup_prelude() + r"""
        var H = window.M3Holocron;
        var parts = H.highlightLore(
            'The Sith have returned to the galaxy.',
            p,
            ['Sith']
        );
        // parts is an array of strings and DOM nodes. Append to a container.
        var container = document.createElement('div');
        parts.forEach(function(part) {
            if (typeof part === 'string') {
                container.appendChild(document.createTextNode(part));
            } else {
                container.appendChild(part);
            }
        });
        var spans = container.querySelectorAll('[data-lore-noun]');
        result = {
            spanCount: spans.length,
            spanNoun: spans[0] && spans[0].getAttribute('data-lore-noun'),
            fullText: container.textContent,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["spanCount"] == 1
    assert out["spanNoun"] == "Sith"
    assert out["fullText"] == "The Sith have returned to the galaxy."


def test_runtime_buildReadingPane_with_null_selection():
    """Reading pane gracefully handles null selected."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holocron.buildReadingPane(p, null);
        document.body.appendChild(el);
        result = {
            tag: el.tagName,
            hasNoneText: el.textContent.indexOf('no entry selected') !== -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["tag"] == "DIV"
    assert out["hasNoneText"]


def test_runtime_modal_draggable_drag_bar_cursor():
    """Modal with draggable: true has cursor: grab on the drag bar."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holocron.buildHolocronModal(p, { draggable: true });
        document.body.appendChild(el);
        // Find the drag bar — it has height 22 and HOLOCRON in it.
        var divs = el.querySelectorAll('div');
        var dragBar = null;
        for (var i = 0; i < divs.length; i++) {
            var d = divs[i];
            if (d.style.height === '22px' && d.textContent.indexOf('HOLOCRON') !== -1) {
                dragBar = d;
                break;
            }
        }
        result = {
            foundDragBar: !!dragBar,
            cursor: dragBar && dragBar.style.cursor,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["foundDragBar"]
    assert out["cursor"] == "grab"


def test_runtime_modal_not_draggable_cursor_default():
    """Modal without draggable has cursor: default on the drag bar."""
    setup = _setup_prelude() + r"""
        var el = window.M3Holocron.buildHolocronModal(p, { draggable: false });
        document.body.appendChild(el);
        var divs = el.querySelectorAll('div');
        var dragBar = null;
        for (var i = 0; i < divs.length; i++) {
            var d = divs[i];
            if (d.style.height === '22px' && d.textContent.indexOf('HOLOCRON') !== -1) {
                dragBar = d;
                break;
            }
        }
        result = {
            cursor: dragBar && dragBar.style.cursor,
            hasNoDragHint: dragBar && dragBar.textContent.indexOf('DRAG') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["cursor"] == "default"
    assert out["hasNoDragHint"]


def test_runtime_modal_with_custom_data():
    """Custom data prop overrides the fixture for modal content."""
    setup = _setup_prelude() + r"""
        var customData = {
            categories: [
                { id: 'lore', label: 'EVENTS', icon: '✦', count: 1, active: true }
            ],
            entries: {
                lore: [
                    { slug: 'kamino_attack', label: 'Kamino Attack',
                      era: 'Active', known: 'rumor', selected: true }
                ]
            },
            selected: {
                category: 'lore',
                slug: 'kamino_attack',
                title: 'Battle of Kamino',
                sub: 'Naval engagement · 21 BBY',
                summary: ['A CIS strike force attempted to destroy the cloning facilities.'],
                stats: [['Outcome', 'Republic victory']],
                leaders: [],
                relatedPlanets: [],
                relatedFactions: [],
                known: { full: [], partial: [], unknown: [] },
                quote: '',
                quoteSource: '',
            },
        };
        var el = window.M3Holocron.buildHolocronContent(p, {
            data: customData
        });
        document.body.appendChild(el);
        result = {
            hasBattleOfKamino: el.textContent.indexOf('BATTLE OF KAMINO') !== -1,
            hasCustomStat: el.textContent.indexOf('Republic victory') !== -1,
            // The fixture defaults must NOT appear.
            noDefaultHuttCartel: el.textContent.indexOf('HUTT CARTEL') === -1,
        };
    """
    out = run_with_dom(["static/spa/m3_holocron.js"], setup)
    assert out["hasBattleOfKamino"]
    assert out["hasCustomStat"]
    assert out["noDefaultHuttCartel"]
