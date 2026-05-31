"""
test_m3_assets_landmarks.py — regression tests for static/spa/m3_assets_landmarks.js.

Drop 4.1d · Tier 1 #4 · May 26 2026.

The 10 LM_* builders + 12-slug LANDMARKS registry must:
  - Return an SVG element for the requested LOD
  - Strip down to a single-element icon at lod='icon'
  - Add detailed flourishes only at lod='detailed'
  - Preserve the JSX source's slug-aliasing (docking_bay_94_pit and
    docking_bay_94_entrance share LM_DockingBay94; lucky_despot_staircase
    and lucky_despot_star_chamber share LM_LuckyDespot)
  - Expose each builder by both short slug (composition engine) AND long
    ident (catalog namespace-fallback chain)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from spa_dom_harness import run_with_dom

SPA_DIR = Path(__file__).resolve().parent.parent.parent / "static" / "spa"
SCRIPTS = [
    SPA_DIR / "m3_tokens.js",
    SPA_DIR / "m3_palettes.js",
    SPA_DIR / "m3_assets_landmarks.js",
]


def test_module_loads_and_exports_twelve_slug_registry() -> None:
    """LANDMARKS exports exactly 12 slug keys, mirroring the JSX registry."""
    result = run_with_dom(SCRIPTS, """
        result = {
            hasNamespace: typeof window.M3AssetsLandmarks === 'object',
            keys: window.M3AssetsLandmarks
                ? Object.keys(window.M3AssetsLandmarks.LANDMARKS).sort()
                : []
        };
    """)
    assert result["hasNamespace"]
    assert result["keys"] == [
        "chalmuans_cantina_main_bar",
        "docking_bay_94_entrance",
        "docking_bay_94_pit",
        "house_of_momaw_nadon",
        "lucky_despot_staircase",
        "lucky_despot_star_chamber",
        "mos_eisley_control_tower",
        "mos_eisley_inn",
        "spaceport_customs_office",
        "spaceport_hotel",
        "spaceport_speeders",
        "transport_depot",
    ]


def test_slug_aliasing_preserves_single_builder_identity() -> None:
    """docking_bay_94_pit and docking_bay_94_entrance must reference the
    SAME builder function (===); same for the two lucky_despot slugs.
    This catches a port mistake where someone wires them up as separate
    copies of the same code."""
    result = run_with_dom(SCRIPTS, """
        var lm = window.M3AssetsLandmarks.LANDMARKS;
        var ns = window.M3AssetsLandmarks;
        result = {
            bay94Identity: lm.docking_bay_94_pit === lm.docking_bay_94_entrance,
            despotIdentity: lm.lucky_despot_staircase === lm.lucky_despot_star_chamber,
            // And both alias targets must also match the long-ident export.
            bay94MatchesLongIdent: lm.docking_bay_94_pit === ns.LM_DockingBay94,
            despotMatchesLongIdent: lm.lucky_despot_staircase === ns.LM_LuckyDespot,
            // 12 slugs map to exactly 10 distinct functions.
            uniqueBuilders: (function() {
                var seen = {};
                Object.values(lm).forEach(function(fn) { seen[fn.name] = true; });
                return Object.keys(seen).length;
            })()
        };
    """)
    assert result["bay94Identity"]
    assert result["despotIdentity"]
    assert result["bay94MatchesLongIdent"]
    assert result["despotMatchesLongIdent"]
    assert result["uniqueBuilders"] == 10


def test_dual_lookup_short_slug_and_long_ident_for_all_builders() -> None:
    """Every LM_* long ident on the namespace resolves to a function and
    matches the function referenced by at least one slug in LANDMARKS."""
    result = run_with_dom(SCRIPTS, """
        var ns = window.M3AssetsLandmarks;
        var lm = ns.LANDMARKS;
        var longIdents = [
            'LM_DockingBay94', 'LM_ChalmunsCantina', 'LM_LuckyDespot',
            'LM_ControlTower', 'LM_CustomsOffice', 'LM_MosEisleyInn',
            'LM_SpaceportHotel', 'LM_MomawNadon', 'LM_TransportDepot',
            'LM_SpeederLot'
        ];
        result = {};
        longIdents.forEach(function(id) {
            var byLong = ns[id];
            var slugMatches = Object.values(lm).filter(function(fn) {
                return fn === byLong;
            }).length;
            result[id] = {
                isFunction: typeof byLong === 'function',
                slugMatches: slugMatches
            };
        });
    """)
    for ident, info in result.items():
        assert info["isFunction"], f"{ident} is not a function on the namespace"
        assert info["slugMatches"] >= 1, \
            f"{ident} is not reachable via any LANDMARKS slug"


def test_every_landmark_returns_svg_at_each_lod() -> None:
    """Every builder, called with each LOD, returns an SVG element."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var lm = window.M3AssetsLandmarks.LANDMARKS;
        var lods = ['icon', 'detail', 'detailed'];
        result = {};
        Object.keys(lm).forEach(function(slug) {
            result[slug] = {};
            lods.forEach(function(lod) {
                var el = lm[slug]({ p: p, lod: lod });
                result[slug][lod] = { tag: el.tagName, ns: el.namespaceURI };
            });
        });
    """)
    for slug, byLod in result.items():
        for lod, info in byLod.items():
            assert info["ns"] == "http://www.w3.org/2000/svg", \
                f"{slug}@{lod} not in SVG namespace"
            assert info["tag"] in ("g", "rect", "ellipse", "circle"), \
                f"{slug}@{lod} returned <{info['tag']}>"


def test_lod_icon_simpler_than_lod_detailed() -> None:
    """For each landmark, the detailed form must have strictly more
    primitive descendants than the icon form."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var lm = window.M3AssetsLandmarks.LANDMARKS;
        function nodeCount(el) {
            var n = 0;
            for (var i = 0; i < el.childNodes.length; i++) {
                n += 1 + nodeCount(el.childNodes[i]);
            }
            return n === 0 ? 1 : n;
        }
        result = {};
        Object.keys(lm).forEach(function(slug) {
            var iconEl = lm[slug]({ p: p, lod: 'icon' });
            var detEl  = lm[slug]({ p: p, lod: 'detailed' });
            result[slug] = { icon: nodeCount(iconEl), detailed: nodeCount(detEl) };
        });
    """)
    for slug, counts in result.items():
        assert counts["detailed"] > counts["icon"], \
            f"{slug}: detailed ({counts['detailed']}) not > icon ({counts['icon']})"


def test_docking_bay_has_12_landing_lights_with_2_extinguished() -> None:
    """LM_DockingBay94 lays down exactly 12 landing-light circles in a ring,
    with positions 3 and 8 deliberately rendered as 'extinguished' (inkFaint
    fill rather than amber). This catches a port mistake in the if/index logic."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsLandmarks.LANDMARKS.docking_bay_94_pit({
            p: p, lod: 'detail'  // includes lights but skips YT-1300 etc.
        });
        // The first three children are the rim path, ledge circle, pit path.
        // Landing-light circles are children 3..14 (12 of them).
        var lights = [];
        for (var i = 3; i < 15; i++) {
            var node = g.childNodes[i];
            if (!node) break;
            lights.push({
                tag: node.tagName,
                fill: node.getAttribute('fill')
            });
        }
        result = {
            count: lights.length,
            amberCount: lights.filter(function(l) { return l.fill === p.amber; }).length,
            faintCount: lights.filter(function(l) { return l.fill === p.inkFaint; }).length
        };
    """)
    assert result["count"] == 12
    assert result["amberCount"] == 10  # 12 - 2 extinguished
    assert result["faintCount"] == 2   # positions 3 and 8


def test_customs_office_has_civic_banner_in_red() -> None:
    """LM_CustomsOffice@detailed includes a red banner (B3 era-neutral
    swap: was 'Imperial-era banner', now generic 'Civic banner') rendered
    with palette.red and ~0.7 opacity. Locks the era-fidelity B3 fix in
    place at the SPA layer."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var g = window.M3AssetsLandmarks.LANDMARKS.spaceport_customs_office({
            p: p, lod: 'detailed'
        });
        // Look for any rect with fill = palette.red.
        var bannerRect = null;
        for (var i = 0; i < g.childNodes.length; i++) {
            var n = g.childNodes[i];
            if (n.tagName === 'rect' && n.getAttribute('fill') === p.red) {
                bannerRect = n;
                break;
            }
        }
        result = {
            found: bannerRect !== null,
            opacity: bannerRect ? bannerRect.getAttribute('opacity') : null,
            width: bannerRect ? bannerRect.getAttribute('width') : null,
            height: bannerRect ? bannerRect.getAttribute('height') : null
        };
    """)
    assert result["found"], "Civic banner rect (palette.red) not found"
    assert result["opacity"] == "0.7"
    # Banner is 6 wide × 14 tall per the JSX source — a portrait stripe.
    assert result["width"] == "6"
    assert result["height"] == "14"


def test_wobble_path_is_deterministic_across_runs() -> None:
    """The wobble helper uses Math.sin with a seed, so the same call
    should produce byte-identical path d attributes on every invocation.
    Two consecutive renders of LM_DockingBay94 must agree on the rim
    path's d attribute (a sanity check that no hidden state crept in)."""
    result = run_with_dom(SCRIPTS, """
        var p = window.M3Palettes.getPalette('tatooine');
        var lm = window.M3AssetsLandmarks.LANDMARKS;
        var g1 = lm.docking_bay_94_pit({ p: p, lod: 'detailed' });
        var g2 = lm.docking_bay_94_pit({ p: p, lod: 'detailed' });
        // First child is the outer rim wobble path.
        var d1 = g1.childNodes[0].getAttribute('d');
        var d2 = g2.childNodes[0].getAttribute('d');
        result = {
            startsWithM: d1.charAt(0) === 'M',
            endsWithZ: d1.charAt(d1.length - 1) === 'Z',
            // Path length is 36 segments per wobble(50,50,42,36,0.5,1):
            // 'M ' + 36 coords joined by ' L ' + ' Z'
            lineSegCount: (d1.match(/L/g) || []).length,
            identical: d1 === d2
        };
    """)
    assert result["startsWithM"]
    assert result["endsWithZ"]
    # Wobble produces n=36 points; format is 'M p0 L p1 L p2 ... L pN-1 Z'
    # So there are n-1 = 35 ' L ' separators.
    assert result["lineSegCount"] == 35
    assert result["identical"], "wobble() output drifted between calls"


def test_palette_swap_changes_landmark_fills() -> None:
    """The same landmark with a different palette uses different fills."""
    result = run_with_dom(SCRIPTS, """
        var tat = window.M3Palettes.getPalette('tatooine');
        var cor = window.M3Palettes.getPalette('coruscant_under');
        var lm = window.M3AssetsLandmarks.LANDMARKS;
        // mos_eisley_inn@icon is a single <circle> — easy to inspect.
        var tatFill = lm.mos_eisley_inn({ p: tat, lod: 'icon' }).getAttribute('fill');
        var corFill = lm.mos_eisley_inn({ p: cor, lod: 'icon' }).getAttribute('fill');
        result = { tat: tatFill, cor: corFill, equal: tatFill === corFill };
    """)
    assert result["tat"]
    assert result["cor"]
    assert not result["equal"]
