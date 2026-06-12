# SW MUSH Map Redesign — Design Brief for Claude Design

**Purpose:** Kickoff prompt for a Claude Design session to mock up the new map system.
**Companion document:** `MAP_REDESIGN_HANDOFF.md` — the full technical handoff. Read it for data model, schema, and migration. This brief is the design-side subset.
**Authored:** 2026-05-03

---

## What you're designing

A redesigned in-game map for **SW MUSH**, a Star Wars text-RP MUD with a web client. The current map is a node-link graph (dots and lines) and the human owner has identified that it doesn't feel like a place. You're producing visual mockups for a new system that renders **actual geography** — districts, streets, landmarks — across multiple zoom tiers from a single building's interior all the way out to the galaxy.

The map is described by the human as a **keystone of the player experience.** Players consult it constantly during active play. It is not a utility minimap; it is a primary view.

## What's already decided

These are not up for debate; design within them:

- **Aesthetic anchor: terminal/HUD datapad.** The existing client uses IBM Plex Mono and Plex Sans, dark backgrounds, amber/cyan accents. The map continues that — it should read as a datapad reading, not a Google Maps slice. Faint glow, scanline-y feel acceptable. CRT distortion only if it doesn't hurt readability.
- **Color palette continues existing CSS variables:** `--cock-amber` (#ffa640), `--cock-cyan` (#6ee8ff), `--cock-red` (#ff5a4a), with planet-specific palette overlays (Tatooine = sand/amber low contrast; Coruscant senate = clean blue-white; Coruscant lower = smudgy red/orange; Nar Shaddaa = neon magenta/cyan; Kamino = cool teal/silver; Geonosis = rust/oxide red).
- **Five zoom tiers** (details below), all driven by the same data — different filters, not different sources.
- **Tactical space combat radar (existing) is unchanged.** That's the FFG-style abstract arcs/ranges view used in combat. Keep it. Your space tier work is separate strategic views ABOVE it.
- **Tech: SVG + CSS transforms.** Not WebGL, not Canvas (with one exception — the optional tile substrate is a single PNG raster). CSS `transform: scale/translate` is the zoom mechanic.
- **Performance budget:** ≤16 ms client render per frame, ≤50 KB asset per area (tile raster ≤30 KB on top). Animation limited to opacity/transform/color.

## Five zoom tiers — design briefs per tier

You'll produce mockups for each. Each tier is a different zoom level on the same data.

### Tier 0 — Site view (one room or interior cluster, ~5 rooms)
Floor plan of an interior. Doors visible, NPCs as small markers, items optional. Either simplified isometric or pure top-down (your call). Most-detailed tier; lowest information density per square pixel.

### Tier 1 — District view (one zone, ~10–25 rooms)
**Most-used view in active play.** A neighborhood-scale plan: building footprints distinguishable, streets drawn as actual paths (not point-to-point arrows — they bend), street names along the streets, district name floating overhead at low opacity, player marker prominent. Optimize for legibility-at-a-glance during rapid travel. This is where players spend most of their time.

### Tier 2 — City view (whole city, ~50–100 rooms)
Districts as filled colored polygons with strong borders. Major streets as wider lines. Room interiors collapsed to small dots or building markers (no labels). District names large. Major landmarks visible (Jabba's Palace pin, the Sarlacc, etc.). Tile substrate (sand/duracrete texture) prominent here.

### Tier 3 — Planet view (one planet)
Top-down or stylized-abstract planet body. Cities as labeled pins. Wilderness regions (Dune Sea, Jundland Wastes) as colored polygons. Hyperspace beacon at one position. Atmosphere overlay/glow for flavor. Planet name and key stats.

### Tier 4a — System view
Top-down 2D of one star system. Star at center (with glow). Planet at orbit (drawn as circle on its orbital arc). Moons. Hyperspace lane endpoints labeled at edges ("→ Corellian Run"). Player ship as distinct marker; scanned other ships as small contacts.

### Tier 4b — Sector view
A flat 2D arrangement of sectors (think hex grid or labeled boxes). Hyperspace lanes as polylines connecting them. Current sector highlighted. Other systems as pins.

### Tier 4c — Galaxy view
Canonical Star Wars galaxy disc. Sector outlines. Era-specific factional shading: Republic core glowing blue, CIS-aligned worlds rust-red, Hutt space green, Outer Rim grey/dim. Major hyperspace routes (Corellian Run, Hydian Way, Perlemian, etc.) as bright lines.

## What's drawn at each tier — the visual layers

In z-order (bottom to top):

1. **Tile substrate** — optional palette-quantized PNG (sand, duracrete, water, void). Tiers 1–2 mostly. ≤6–8 colors.
2. **District fills + borders** — colored polygons with subtle borders. Tiers 1–2.
3. **Exit paths** — straight lines OR polylines for streets/alleys/corridors. Per-path styling. Tiers 0–1.
4. **Room footprints + symbols** — rooms have a polygon footprint (often a small rect), with an optional symbol glyph rendered on top. Tiers 0–2 (simplified at higher tiers).
5. **Labels** — text annotations placed at world coords with min-zoom/max-zoom visibility. Different label kinds: street, district, landmark, warning, flavor.
6. **Landmarks** — icon markers at point positions. Different from rooms.
7. **Player marker** — separate layer, always on top, smooth-animated between positions.
8. **NPC/other-player markers** — same layer as player, smaller distinct shapes.

## The marker system (design heavily)

The player marker is the most-rendered element. It must be:
- Always visible (never obscured).
- Distinct from all other markers (suggested: chevron with pulsing outer ring in `--cock-cyan`).
- Smoothly lerped between positions on room change (~150 ms; never teleports).
- At low zoom, fixed-size on-screen — does not shrink with the rest of the map.

Other markers — distinct shapes:
- Other PCs: cyan, smaller chevron.
- NPCs friendly: amber dot.
- NPCs hostile: red triangle.
- NPCs neutral / unknown: grey dot.

(These match the existing radar legend conventions in the client CSS.)

## Tier transitions

- Smooth zoom in/out animation between tiers.
- Cross-fade layers as tier changes (district fills fade in, room interiors fade out, etc.).
- Camera follows the player when zoomed in; pans to a point of interest when manually navigated.
- Breadcrumb indicator in a corner: `MOS EISLEY ▸ SPACEPORT ▸ Bay 94`.

## Mobile / narrow viewport

The right column hides on narrow viewports today. The new map needs a mobile variant — likely a full-screen takeover with a "back to game" button and finger-friendly zoom/pan. The existing modal-expand pattern is the entry point.

## Rapid-travel constraint translated for design

Players move room-to-room every few seconds in active scenes. The map cannot:
- Flicker on transitions.
- Re-layout existing elements (only the player marker should move).
- Run animations longer than 150 ms.
- Show "loading" states between rooms within the same area.

The *underlying architecture* sends the area geometry once when the player enters an area, then sends only position deltas on every move. As a designer this means: assume the map is stable; design for the player marker as the primary moving element.

## Concrete pilot area: Mos Eisley

**The first city to mock up is Mos Eisley.** It's the smallest and most-tested. Reference materials:

- 54 hand-built rooms with `map_x`/`map_y` already authored (range roughly 0–14 on both axes, integer-aligned).
- 7 zones: spaceport, market (streets), civic, cantina, outskirts, jundland (wilderness edge), plus a connecting wilderness region (Dune Sea).
- Iconic landmarks: Docking Bay 94, Chalmun's Cantina, Jabba's Palace, Kerner Plaza, Lucky Despot, the Dowager Queen wreckage, the Westport.
- Aesthetic: dusty, sand-bleached duracrete, twin-suns glare, low-contrast amber palette, sprawling layout (no real grid — buildings cluster around a few main streets).

Produce mockups at tiers 0, 1, 2 for Mos Eisley. Tier 3 (Tatooine planet view) too if time allows. Tiers 4a/b/c can be a separate later pass.

## Deliverables expected

1. **Mockups for each tier** of Mos Eisley (PNG or SVG, full-detail, treat as final-quality target).
2. **Mockup for one other planet at tier 1** to test the palette-overlay system — recommend Coruscant Senate or Nar Shaddaa Topside (most aesthetically distinct from Tatooine).
3. **Marker system sheet** — player, other-PC, NPC variants, all sizes/states.
4. **Label/icon system sheet** — typography hierarchy, district label style, street label style, landmark icon style for ~10 key landmarks (cantina, dock, temple, palace, market, medical, vendor, etc.).
5. **Transition behavior reference** — describe (in words or a short storyboard) what happens visually on:
   - Zoom in from city → district → site
   - Player crosses a room boundary
   - Player crosses an area boundary (e.g. Mos Eisley → Dune Sea wilderness)
6. **Component spec for the developer handoff** — when the implementation session picks this up, they need: SVG asset specs, color hex values, font sizes/weights, animation timings, CSS transform conventions.

## Hard constraints recap

- SVG + CSS transforms (no WebGL, no Canvas-as-rendering-context except optional tile PNG).
- Render budget: 16 ms per frame (60 fps).
- Asset budget: ≤50 KB per area (tile raster ≤30 KB on top).
- Animation: opacity, transform, color only — no filters/blurs in the hot path.
- Continues the existing terminal-HUD aesthetic — this is a refinement, not a redesign of the visual language of the game.
- **Y-axis: north = +y in world coords** (Y-up). Render layer flips at SVG via `scale(1, -1)` on the world group.

## What you should NOT design

- The tactical combat radar (already exists, keep as-is).
- The web-based geometry editor (separate work, after pilot).
- Site interiors of every building (just enough variety to show the tier-0 pattern).
- Era-specific factional UI elements (the system supports multi-era; the visual language is era-neutral).

## If you have questions

The full handoff document `MAP_REDESIGN_HANDOFF.md` answers:
- Why the current map fails (§4 — diagnosis with file:line refs).
- The proposed data architecture (§6 — two-layer split).
- The schema specifics (§7 — SQL DDL, YAML format).
- The migration path (§8 — phases).
- The performance pattern (§6.4 — geometry-once + position-deltas).
- Open vs. closed decisions (§10).

Read those sections if a design question hinges on them.

---

*End of design brief.*
