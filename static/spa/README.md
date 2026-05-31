# static/spa/ — Map v3 SPA modules

Vanilla-JS ports of the `map_v3/` prototype JSX files. Loaded by `client.html`
once Drop 4.1e (composition-engine) ships and the SPA surfaces light up.

## Naming convention

Each `map_v3/<name>.jsx` ports to `static/spa/m3_<name>.js`:

| Prototype JSX | Production JS | Window namespace |
|---|---|---|
| `map_v3/tokens.jsx` | `static/spa/m3_tokens.js` | `window.M3Tokens` |
| `map_v3/palettes.jsx` | `static/spa/m3_palettes.js` | `window.M3Palettes` |
| `map_v3/asset-catalog.jsx` | `static/spa/m3_asset_catalog.js` | `window.M3AssetCatalog` |
| ... (rest land in 4.1b-e) | ... | ... |

## Module pattern

Every module follows this skeleton:

```javascript
/* ============================================================================
   m3_<name>.js — <one-line purpose>

   Drop 4.1<X> · Tier 1 #4 · ported from map_v3/<name>.jsx (May 26 2026)
   ============================================================================ */
(function(){
'use strict';

// ... module code ...

// Single export, namespaced under window.M3<Name>
window.M3<Name> = {
  // public surface
};

})();
```

Notes:

- **No React.** No JSX. Vanilla DOM/SVG only. (See `static/map_view.js` for
  the precedent — Drop F.MAP.1 already established this.)
- **No build step.** Files are served as-is from `/static/spa/<name>.js`.
- **IIFE wrapper.** Prevents leaking helpers into the global scope.
- **Single window export.** Named `window.M3<PascalCaseName>` matching the
  filename.
- **Drop-trail comment.** Every module declares which sub-drop ported it
  and when, so future maintainers can trace the lineage.

## SVG creation helpers

`M3Tokens.svgEl(tag, attrs, children)` is the boilerplate-free SVG creator.
Landed in Drop 4.1b alongside `m3_assets_styles.js` and `m3_assets_icons.js`.
Usage:

```javascript
var rect = M3Tokens.svgEl('rect', { x: 10, y: 10, width: 80, height: 80,
                                    fill: '#b46a3a', stroke: '#ffd07a' });
var g    = M3Tokens.svgEl('g', { transform: 'translate(50 50)' }, [rect]);
```

camelCase aliases for SVG attributes (`strokeWidth`, `strokeDasharray`,
`fontFamily`, etc.) are auto-converted to kebab-case. `viewBox` and other
genuinely-camelCase SVG attributes are preserved as-is.

For non-SVG (HTML) elements like asset-catalog, modules use a local `el()`
helper rather than putting an HTML version in M3Tokens (most modules are
SVG-only and don't need it).

## Loading order (when composition-engine ships)

```html
<script src="/static/spa/m3_tokens.js"></script>            <!-- 4.1a -->
<script src="/static/spa/m3_palettes.js"></script>          <!-- 4.1a -->
<script src="/static/spa/m3_asset_catalog.js"></script>     <!-- 4.1b -->
<script src="/static/spa/m3_assets_icons.js"></script>      <!-- 4.1b -->
<script src="/static/spa/m3_assets_styles.js"></script>     <!-- 4.1b -->
<script src="/static/spa/m3_assets_markers.js"></script>    <!-- 4.1c -->
<script src="/static/spa/m3_assets_wilderness.js"></script> <!-- 4.1c -->
<script src="/static/spa/m3_assets_overlays.js"></script>   <!-- 4.1c -->
<script src="/static/spa/m3_assets_landmarks.js"></script>  <!-- 4.1d -->
<script src="/static/spa/m3_composition_engine.js"></script><!-- 4.1e -->
```

Order matters — composition-engine consumes everything below it.

## Tests

See `tests/spa/test_m3_<name>.py` for each module's regression test.
Pattern depends on whether the module touches the DOM:

- **Pure-data modules** (m3_tokens base, m3_palettes) — Node sandbox via
  `spa_dom_harness.run_with_dom()` is overkill but still works; the pre-4.1b
  test files use a simpler direct-Node-eval pattern that doesn't need jsdom.
- **DOM-touching modules** (m3_assets_styles, m3_assets_icons, m3_asset_catalog,
  everything in 4.1c+) — use `spa_dom_harness.py::run_with_dom()`. It spins up
  a jsdom window per test, loads the listed SPA scripts in order, runs the
  test setup script, returns parsed JSON output to Python for assertions.

Playwright still lands later (Q1) when actual browser-only behavior (CSS,
fonts, animations) needs visual verification. jsdom is right-sized for
verifying that an SVG `<g>` has the expected child structure / attributes /
text content; Playwright is for everything beyond that.
