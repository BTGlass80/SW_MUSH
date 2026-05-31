"""
test_m3_assets_icons.py — regression tests for static/spa/m3_assets_icons.js.

Drop 4.1b · Tier 1 #4 · May 26 2026.

Validates the 4 icon families (services, status, attributes, factions),
the Icon wrapper, CW-era faction set, and title-tooltip presence.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
SCRIPTS = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_assets_icons.js",
]


def test_module_exports_four_families() -> None:
    """All 4 icon families + Icon wrapper exported."""
    result = run_with_dom(SCRIPTS, """
        result = {
            keys: Object.keys(window.M3AssetsIcons).sort(),
            services:  Object.keys(window.M3AssetsIcons.SERVICE_ICONS).sort(),
            status:    Object.keys(window.M3AssetsIcons.STATUS_ICONS).sort(),
            attrs:     Object.keys(window.M3AssetsIcons.ATTR_ICONS).sort(),
            factions:  Object.keys(window.M3AssetsIcons.FACTION_ICONS).sort()
        };
    """)
    assert result["keys"] == ["ATTR_ICONS", "FACTION_ICONS",
                              "Icon", "SERVICE_ICONS", "STATUS_ICONS"]
    assert result["services"] == ["bank", "cantina", "comlink", "crafting", "dock",
                                  "mail", "medical", "mission_board", "trainer", "vendor"]
    assert result["status"] == ["aim_held", "force_focused", "in_cover", "stunned", "wounded"]
    assert result["attrs"] == ["dex", "kno", "mec", "per", "str", "tec"]


def test_faction_set_is_cw_canonical() -> None:
    """Faction icons are CW-canonical: NO empire/rebel. Has republic/cis/jedi/etc."""
    result = run_with_dom(SCRIPTS, """
        var keys = Object.keys(window.M3AssetsIcons.FACTION_ICONS).sort();
        result = {
            keys: keys,
            has_empire: keys.indexOf('empire') !== -1,
            has_rebel:  keys.indexOf('rebel') !== -1,
            has_republic: keys.indexOf('republic') !== -1,
            has_cis:    keys.indexOf('cis') !== -1
        };
    """)
    # CW canonical set
    assert "republic" in result["keys"]
    assert "cis" in result["keys"]
    assert "jedi" in result["keys"]
    assert "hutt" in result["keys"]
    # No GCW factions
    assert not result["has_empire"], "FACTION_ICONS leaked an 'empire' icon (era contamination)"
    assert not result["has_rebel"], "FACTION_ICONS leaked a 'rebel' icon (era contamination)"


def test_icon_wrapper_produces_svg() -> None:
    """Calling Icon() returns a real <svg> element with the right viewBox."""
    result = run_with_dom(SCRIPTS, """
        var paths = [
            window.M3Tokens.svgEl('path', { d: 'M 0 0 L 10 10' })
        ];
        var icon = window.M3AssetsIcons.Icon({ c: '#ff0000', size: 32, title: 'Test' }, paths);
        result = {
            tag: icon.tagName,
            width: icon.getAttribute('width'),
            height: icon.getAttribute('height'),
            viewBox: icon.getAttribute('viewBox'),
            stroke: icon.getAttribute('stroke'),
            fill: icon.getAttribute('fill'),
            firstChildTag: icon.childNodes[0].tagName,
            firstChildText: icon.childNodes[0].textContent
        };
    """)
    assert result["tag"] == "svg"
    assert result["width"] == "32"
    assert result["height"] == "32"
    assert result["viewBox"] == "0 0 24 24"
    assert result["stroke"] == "#ff0000"
    assert result["fill"] == "none"
    # title element should be first child
    assert result["firstChildTag"] == "title"
    assert result["firstChildText"] == "Test"


def test_service_icon_vendor_has_three_paths() -> None:
    """SERVICE_ICONS.vendor produces 3 <path> elements inside the title."""
    result = run_with_dom(SCRIPTS, """
        var icon = window.M3AssetsIcons.SERVICE_ICONS.vendor({ c: '#ffa640', size: 20 });
        var tags = [];
        for (var i = 0; i < icon.childNodes.length; i++) tags.push(icon.childNodes[i].tagName);
        result = {
            tags: tags,
            titleText: icon.childNodes[0].textContent
        };
    """)
    assert result["tags"] == ["title", "path", "path", "path"]
    assert result["titleText"] == "Vendor"


def test_attr_icon_mec_has_6_spokes() -> None:
    """ATTR_ICONS.mec produces a circle + 6 spoke <line>s + title = 8 children."""
    result = run_with_dom(SCRIPTS, """
        var icon = window.M3AssetsIcons.ATTR_ICONS.mec({ c: '#ffd07a', size: 18 });
        var counts = { line: 0, circle: 0, title: 0 };
        for (var i = 0; i < icon.childNodes.length; i++) {
            var t = icon.childNodes[i].tagName;
            counts[t] = (counts[t] || 0) + 1;
        }
        result = { total: icon.childNodes.length, counts: counts };
    """)
    assert result["counts"]["title"] == 1
    assert result["counts"]["circle"] == 1   # the central gear circle
    assert result["counts"]["line"] == 6     # 6 spokes around it


def test_faction_republic_has_eight_spokes() -> None:
    """FACTION_ICONS.republic: circle + 8 spokes + center circle + title."""
    result = run_with_dom(SCRIPTS, """
        var icon = window.M3AssetsIcons.FACTION_ICONS.republic({ c: '#ffa640', size: 24 });
        var counts = { line: 0, circle: 0, title: 0 };
        for (var i = 0; i < icon.childNodes.length; i++) {
            var t = icon.childNodes[i].tagName;
            counts[t] = (counts[t] || 0) + 1;
        }
        result = { counts: counts, titleText: icon.childNodes[0].textContent };
    """)
    assert result["counts"]["title"] == 1
    assert result["counts"]["circle"] == 2  # outer ring + filled center
    assert result["counts"]["line"] == 8   # 8 radiating spokes
    assert result["titleText"] == "Galactic Republic"


def test_status_wounded_has_filled_paths() -> None:
    """STATUS_ICONS.wounded uses fill attribute (filled droplet + dot)."""
    result = run_with_dom(SCRIPTS, """
        var icon = window.M3AssetsIcons.STATUS_ICONS.wounded({ c: '#ff5a4a', size: 18 });
        var fills = [];
        for (var i = 0; i < icon.childNodes.length; i++) {
            var f = icon.childNodes[i].getAttribute('fill');
            if (f) fills.push(f);
        }
        result = { fills: fills };
    """)
    # Both the droplet path and the dot circle are filled with the color
    assert result["fills"] == ["#ff5a4a", "#ff5a4a"]


def test_icon_color_swap() -> None:
    """The same icon called with different colors produces different stroke values."""
    result = run_with_dom(SCRIPTS, """
        var amber = window.M3AssetsIcons.SERVICE_ICONS.medical({ c: '#ffa640', size: 24 });
        var red   = window.M3AssetsIcons.SERVICE_ICONS.medical({ c: '#ff5a4a', size: 24 });
        result = {
            amberStroke: amber.getAttribute('stroke'),
            redStroke:   red.getAttribute('stroke')
        };
    """)
    assert result["amberStroke"] == "#ffa640"
    assert result["redStroke"]   == "#ff5a4a"
