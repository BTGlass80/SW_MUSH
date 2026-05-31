# SW_MUSH Map Substrate — Full Nano Package

**Date:** May 29 2026 · **Scope:** everything needed to produce correct, navigable, visually-consistent painted maps for all six cities, with every mitigation we identified baked in.

This single package supersedes the earlier production guide and the Mos Eisley experiment kit. It assumes the hybrid map system (painted raster substrate under the SVG overlay) and the architecture-of-record (`sw_d6_mush_architecture_v51.md`).

---

## 0. The whole sequence (do it in this order)

1. **Cardinal pre-flight** (§1). Reconcile wrong-way exits on the three affected maps so navigation makes spatial sense. Independent of painting; required before a map goes live. Tool + full inventory: `tools/check_map_cardinals.py`, `CARDINAL_INVENTORY.md`.
2. **Paint all six** in Nano (§2) from the **tight** seeds, in one session, style-locked. Depends only on map `x/y`, so it can run in parallel with (1).
3. **Re-import** (§3): register pins, paste landmarks, uncomment `substrate_image`, smoke-test.
4. **Implement the micro-overlay** (§4) in the render lane: the precision layer that makes zoom-in navigation exact and consistent. Mandatory regardless of how the paintings turn out.

Why this order resolves the concerns you raised:
- *"Click east shouldn't walk west / teleport"* → movement is driven by the exit graph, not the map; the map is display-only today, and §1 makes the rendered geometry agree with the graph's directions. §4's click-to-walk (if added) traverses exits, never coordinate-jumps.
- *"Moving inside a building shouldn't fling me across the map / leave me outside"* → §4's interior handling: building interiors render in their own view, not on the city map. The gameplay graph already tags these moves (`in`/`out`/`up`/`down`).
- *"Painting won't hold up at the micro level"* → it doesn't have to. §4 makes the precise vector overlay the navigable surface at close zoom; the painting recedes to atmosphere. Tight seeds (§2) just keep the backdrop's macro layout clean under it.

---

## 1. Cardinal pre-flight (navigation correctness)

The painted map is becoming a primary nav aid, so the gameplay compass words must agree with where rooms render. They don't, on three maps. Full results and the 37 proposed corrections are in **`CARDINAL_INVENTORY.md`**; the short version:

- **Clean today:** `kamino.tipoca_city`, `geonosis.stalgasin_hive`, `kuat.kuat_city`.
- **Reconcile:** `nar_shaddaa.smugglers_moon` (5), `coruscant.senate_district` (7), `tatooine.mos_eisley` (25).

Recommended fix is **Philosophy B** — treat the rendered `x/y` as truth and relabel the offending direction words to the geometry-correct ones (preserves all paintings + registration; the inventory lists exact changes). For the few rooms whose *names* would become absurd (Mos Eisley's "North End" at the map's south), consider instead nudging their placement (Philosophy A). Per-map, your call — but **this is the live movement graph, so review before applying.** I did not auto-apply.

Wire the gate so it can't regress:
```
python tools/check_map_cardinals.py <area_key> --gate     # exit 1 if wrong-way exits remain
```
Add it to the substrate pre-flight. **A map should not go live (substrate uncommented) until it passes.**

> Painting does not wait on this — the painting derives only from `x/y`. You can paint Mos Eisley while deciding how to reconcile its directions.

---

## 2. Nano production — tight method, all six

### 2.1 The two hard rules (unchanged)
- **IP-neutral language only.** Gemini filters franchise terms and OCRs the input image. Use the per-city translation tables. The seeds are text-free for this reason.
- **Frame as concept-art base layer, NO TEXT.** Avoids garbled-label hallucination.

### 2.2 What you feed
Feed only the **`*_tight_seed.png`** for each city (in `static/tools/seeds/`). The tight seed locks the macro skeleton — crisp district edges, a bright unmistakable road network, the key landmarks as solid blocks, rooms demoted to faint density texture — so Gemini preserves the composition instead of reflowing it. The matching `*_tight_keymap.png` is your labeled reference; **never feed the keymap** (it has text).

### 2.3 Style lock (consistency across every map)
You wanted one consistent style everywhere. Two mechanisms:
1. **The style clause in the master prompt is verbatim-identical across all six** (below). Don't vary it; vary only geography.
2. **Carry a fixed style-reference image into every generation**, alongside the seed. Paint **one** city first (Mos Eisley is the densest stress test and you have a v1 to compare), pick the keeper, and use *that image* as the style reference for the other five — Gemini takes a reference image for *look* the same way it takes the seed for *layout*. This locks the aesthetic so the six read as one atlas. The same reference governs any future maps and any per-district detail tiles, so the whole game stays visually unified. (Procedural maps for not-yet-painted places are demoted to dev/fallback only — never the player-facing style once a place is painted.)

### 2.4 Interiors (so you don't paint yourself into a corner)
Paint the **city exterior only** — streets and building *exteriors*. **Do not depict building interiors.** The few interior rooms (cantina back room, an audience chamber, etc.) are handled by the interior tier (§4): they live as a separate view, not as features on the city painting. On the city map their hitboxes simply cluster at the building's footprint. So nothing in the painting needs to represent "inside."

### 2.5 The master prompt (reuse verbatim; swap only `{ASPECT}` and `{GEOGRAPHY}`)
```
Concept art / environment plate for the map screen of a science-fantasy
role-playing game. BASE LAYER ONLY. The image must contain absolutely NO
TEXT of any kind — no labels, letters, numbers, signs, legend, or compass
markings. Names are composited later; a clean text-free plate is the point.

Use the attached base image as the EXACT, FIXED spatial layout. Preserve the
composition precisely — do NOT reflow, rescale, rearrange, or re-proportion
anything. Specifically:
  - the bright lines are the main roads/causeways: keep them running exactly
    where they are;
  - each solid colored region is a district: keep its position, size and
    shape, repainting it as ground/urban terrain of the character described;
  - the large GOLD blocks mark key structures that MUST be clearly visible:
    paint a distinct building of the type described on that exact spot;
  - the faint pale rectangles are background density: render them as ordinary
    structures filling that area — do NOT make each one a distinct landmark;
  - any marker at the very edge is an off-map direction, NOT a building.

Style: hand-painted tabletop-RPG sourcebook cartography — painterly,
weathered, warm and tactile, like a printed campaign atlas. Top-down with a
gentle ~10-15 degree oblique tilt so structures show a little height.
Cohesive limited palette. Render at {ASPECT} aspect ratio, filling the frame
edge to edge.

Setting: a lived-in, used-future space-opera world. Low-tech, weathered,
functional. No modern Earth elements, no automobiles, no contemporary
signage, no soldiers or uniformed troops, no franchise iconography.

{GEOGRAPHY}

Final reminders: NO TEXT anywhere — no labels, legend, compass letters, grid,
numbers, title, signature, watermark, or border. Clean painterly terrain to
every edge.
```
Generate 6–8 per city, pick the keeper (reads as the right *kind* of place; the gold-block landmarks present and on-spot; holds up small at ~800–1200px; clean/no text), strip stray text in edit mode if needed, save to the exact filename below.

### 2.6 Per-city briefs

Filenames are load-bearing — the manifest and YAML already expect these exact names.

---

**Senate District (Coruscant)** — `{ASPECT}` **1.125:1** — feed `senate_district_tight_seed.png` — save **`static/maps/coruscant_senate_substrate.png`**
Distinctive: Senate Rotunda (center) · Galactic Museum (upper-right) · Opera House (lower-right).

| Don't say | Say |
|---|---|
| Coruscant | endless planet-wide city, monumental civic architecture horizon-to-horizon |
| Senate Rotunda | colossal ribbed legislative dome, a vast pale mushroom-dome |
| Galactic Museum | grand colonnaded museum palace with a wide plaza |
| Opera House | ornate tiered performance hall, a sculpted droplet shape |
| Jedi Temple | *(off-map — do not depict)* |

`{GEOGRAPHY}`: *Monumental civic heart of an endless planet-wide city — grand government architecture and streams of anti-grav traffic between towers. A broad ceremonial boulevard runs up the middle. Dead center: a colossal ribbed legislative dome, far larger than anything around it. Upper-right: a grand colonnaded museum palace with a plaza. Lower-right: an ornate tiered concert hall. Top-center on the boulevard: an open plaza with a slender monument spire. Right side dense governmental quarter; left side a lower approach. Fill with packed monumental towers and skybridges.*

---

**Nar Shaddaa** — `{ASPECT}` **0.692:1 (PORTRAIT)** — feed `smugglers_moon_tight_seed.png` — save **`static/maps/nar_shaddaa_substrate.png`**
Distinctive: Hutt Emissary Tower (upper-center) · The Promenade (upper-mid) · Docking Bay Aurek (mid) · Fighting Pits (lower-right).

| Don't say | Say |
|---|---|
| Nar Shaddaa / Smuggler's Moon | vertical frontier slum-moon, a grimy vice-city built downward in tiers |
| Hutt Emissary Tower | crime-lord's audience spire — fat, gaudy, fortified, NOT a graceful palace |
| The Promenade | garish neon vice-strip of cantinas and dens |
| Docking Bay Aurek | industrial freighter docking bay cut into the structure |
| Fighting Pits | sunken oval blood-sport pit ringed by seating |

`{GEOGRAPHY}`: *A vertical frontier slum-moon, read top-to-bottom as a descent. TOP (widest): a garish neon vice-strip. Below: an industrial tier of freighter docking bays. Below that: a dark decaying under-tier. BOTTOM: the grimiest sump around a glowing reactor stack. Distinctive, top to bottom — upper-center a fat fortified crime-lord's audience spire (not a fairy-tale palace); below it a sprawling neon entertainment hall; mid-frame a docking-bay mouth open to the void; lower-right a sunken blood-sport pit. Layered scaffolding, pipework, smog, harsh light.*

---

**Geonosis (Stalgasin Hive)** — `{ASPECT}` **1.0:1 (square)** — feed `stalgasin_hive_tight_seed.png` — save **`static/maps/geonosis_stalgasin_substrate.png`**
Distinctive: Stalgasin Hive spire (upper-right) · Droid Foundry (center-left) · Petranaki Arena (bottom) · Landing Pad (center).

| Don't say | Say |
|---|---|
| Geonosis / Geonosian | arid red-rock desert world of insectile mud-spire hives |
| Stalgasin Hive | towering organic termite-mound spire of red stone, pocked with openings |
| Droid Foundry | smoking subterranean foundry complex, vents and slag |
| Petranaki Arena | open-air oval execution arena, sand pit ringed by tiered stone seating |
| Geonosian Spire (the far one) | *(off-map — do not depict)* |

`{GEOGRAPHY}`: *Arid red-rock desert of insectile mud-spire hives, baked orange-red stone and dust. Center: an open flat rock landing field. Upper-right: a towering organic termite-mound spire-hive rising far above the plain. Center-left: a smoking subterranean foundry complex. Bottom: a great open-air oval arena. West = foundry district; upper-right = deep hive; south = arena; center = exposed surface. Fill with smaller mud-spires, outcrops, dust.*

---

**Kamino (Tipoca City)** — `{ASPECT}` **1.375:1** — feed `tipoca_city_tight_seed.png` — save **`static/maps/kamino_tipoca_substrate.png`**
Distinctive: Main Corridor hub (center) · Cloning Access (center-right) · Growth Chambers (right) · Landing Platform (left).

| Don't say | Say |
|---|---|
| Kamino / Kaminoan | storm-lashed all-ocean world; a stilt-city of white domed pods on slender legs above a raging sea |
| clones / cloning halls | rounded laboratory dome-pods, smooth white organic architecture |
| Tipoca Main Corridor | central connecting hub-dome / elevated causeway |
| Landing Platform | exposed circular landing platform on stilts, lashed by rain |
| Aiwha Stable | open sea-creature pen at the water's edge |

`{GEOGRAPHY}`: *A single stilt-city on a storm-lashed all-ocean world — smooth white domed pods on slender legs high above a raging grey-green sea, linked by elevated causeways under perpetual rain. No land, only dark water and storm sky. A central east-west causeway spine links the pods. Center: the main hub-dome. To its right: two large rounded laboratory pods (the most prominent structures). Left: an exposed circular landing platform on stilts. Lower-left: an open sea-creature pen. Pale, wet, gleaming, blue-grey.*

---

**Kuat City** — `{ASPECT}` **1.5:1** — feed `kuat_city_tight_seed.png` — save **`static/maps/kuat_city_substrate.png`**
Distinctive: Shuttle Landing Pad (upper-left) · Andris Grand Hotel (upper-left-center) · Republic Liaison Office (right).

| Don't say | Say |
|---|---|
| Kuat | refined wealthy Core-World garden capital — clean air, greenery, pale spires |
| Kuat Drive Yards / orbital ring | *(off-map — do not depict; no shipyards, no industry)* |
| Shuttle Landing Pad | tidy circular civic shuttle pad ringed by gardens |
| Andris Grand Hotel | opulent luxury grand hotel, a graceful tower with terraced planted balconies |
| Republic Liaison Office | stately diplomatic palace in formal gardens with a reflecting pool |

`{GEOGRAPHY}`: *A refined wealthy garden capital — clean warm air, manicured greenery, ornamental water, elegant pale spires; an orderly diplomatic quarter, bright and peaceful. Tree-lined boulevards run east-west through the center. Upper-left: a tidy circular shuttle pad ringed by gardens. Just right of it: an opulent grand hotel with terraced planted balconies. Right: a stately diplomatic palace in formal gardens with a reflecting pool. Top-center: an open market plaza. West = arrival gateway; center = green civic boulevard; east = embassy quarter. No industry, no docks, no machinery.*

---

**Mos Eisley (Tatooine)** — `{ASPECT}` **1.55:1** — feed `mos_eisley_tight_seed.png` — save **`static/maps/mos_eisley_substrate_tight.png`** *(new A/B name; leave the existing `mos_eisley_substrate.png` untouched so you can compare)*
Distinctive: Docking Bay 94 pit (upper-left) · Lucky Despot beached barge (center-left) · Dowager Queen wreck (far upper-left) · Chalmun's Cantina (left-center) · Krayt bone field (far right).

| Don't say | Say |
|---|---|
| Mos Eisley / Tatooine | dusty desert frontier spaceport town on a twin-sun desert world; low sand-colored domes and blocky structures, sun-baked |
| Docking Bay 94 | a circular sunken landing pit for a starship, open to the sky |
| Lucky Despot | a large derelict sail-barge beached in the sand, repurposed as a building |
| Dowager Queen | a half-buried old starship wreck jutting from the dunes |
| Chalmun's Cantina | a notorious domed cantina, the busiest dive in town |
| Krayt Graveyard | a field of giant bleached skeletal bones in the open desert |
| Jabba's Palace / The Sarlacc | *(off-map — do not depict)* |

`{GEOGRAPHY}`: *A dusty desert frontier spaceport town under twin suns, sand and heat-haze, fading to open desert at the edges. Top band: the spaceport — circular landing pits and parked freighters. Center: a crowded market quarter of stalls and dense low buildings. Lower-left: a seedy cluster of cantinas. Bottom: a small civic quarter. Upper-right of center: sparser outskirts thinning into sand. Lower-right: rocky badlands and canyons. Far-right edge: open empty dunes. Key structures: upper-left a sunken circular landing pit; far upper-left a half-buried ship wreck; left-of-center a notorious domed cantina; center-left a large beached barge repurposed as a building; far right a field of giant bleached bones.*

---

## 3. Re-import (per city, ~5 min each)

Everything but the painting is pre-built: geometry validates, manifests exist (`static/tools/manifests/<area_key>.json`), and each map's `substrate_image:` line is present but commented. Steps:

1. Save the painting to the exact filename (§2.6).
2. Serve the game (substrate must be same-origin, not `file://`).
3. Open `http://<host>/static/tools/map_register.html?area=<area_key>` — pins load pre-seeded. Confirm the ~3 distinctive pins sit on their painted features (drag to fix); generics need only be in-zone; edge pointers are edge-fine. **EXPORT YAML → COPY.**
4. Paste the `landmarks:` block into `data/worlds/clone_wars/maps/<basename>.yaml`.
5. Uncomment the real `substrate_image: /static/maps/..._substrate.png` line.
6. Run the **cardinal gate** (§1) and **smoke-test**: painting fills the modal, correct orientation, distinctive labels on features, click-to-walk works, weather/time overlays trigger, resize re-renders.

(If you adopt the tight Mos Eisley, point its YAML `substrate_image` at `mos_eisley_substrate_tight.png` once you've judged it the keeper, then drop the `_tight` suffix when you promote it.)

---

## 4. Micro-overlay spec (render lane) — the precision layer

A modest edit to `static/map_view.js` plus a caller-side zoom policy. **No repaint, no geometry change.** Rooms already render *over* the substrate (stack order `map_view.js:15`) and visibility is already zoom-gated (`:428` landmarks, `:590` labels). Four wirings:

**(a) Zoom-driven `showRooms` under a substrate.** `renderRooms` already supports `full`/`dot`/`dot+player`/`hide`. Drive it off `zoomTier` (0 site · 1 district · 2 city · 3 planet):
- tier 3/2: `showRooms:"hide"` (or `"dot"`) → painting dominant, major landmark pins only.
- tier 1/0: `showRooms:"full"` → precise room cells + glyphs come forward.

**(b) Substrate dim at close tiers.** Add an `opacity` to `renderSubstrate` (default 1.0); at tier ≤1 render the substrate ~0.4–0.5 (or lay a dark scrim), so the overlay reads as the truth and the loose paint recedes to texture.

**(c) Tactical room-cell style.** `full` mode currently paints an opaque `roomFill` rect (buries the painting). Add a substrate-aware variant: translucent fill + glowing accent border (`vector-effect:non-scaling-stroke`) + glyph — a holo-tactical overlay over art, not rectangles pretending to be buildings. Gate on "substrate present AND zoomTier ≤ 1".

**(d) Landmark + label tiering (the navigation densification).**
- **Majors persist:** set the distinctive landmarks `min_zoom:0, max_zoom:3` so they stay visible at every tier (they're currently `min 2/max 3`, which hides them on zoom-in — backwards).
- **POIs on zoom-in:** author secondary points of interest (shops, services, specific rooms) as landmarks/labels `min_zoom:0, max_zoom:1` so they surface only once zoomed into a district/site, atop the receded painting.

**(e) Interior tier (resolves "moving inside flings me / leaves me outside").** When the player takes an `in`/`out` (or `up`/`down`-into-a-structure) exit — which the gameplay graph already tags — transition to an **interior view** that renders just that building's rooms, instead of moving the marker on the city map. Same-building movement then happens in the interior view (you're shown inside), and the city map is unaffected. This is the inner-tier renderer already on the roadmap; the data signal (`in`/`out`/`up`/`down`) exists now. Formalize an "interior group" (which rooms belong to which building) so the interior view knows what to render.

**(f) Click-to-walk (if/when added).** A map click must *traverse the exit* from the current room to the clicked adjacent room (issue that exit's direction) — never a coordinate jump. No direct exit → no move (or pathfind). This keeps movement graph-driven; combined with §1, "click east" then reliably walks east. The map is display-only today, so there is no teleport risk until this is deliberately wired.

The net at site zoom: dimmed painting + glowing room cells + persistent majors + dense POIs + true interiors = exact, readable, spatially-honest navigation that never depends on the painting's fine detail — and because (a)–(c) are identical on every map, the close-range experience is consistent everywhere.

---

## 5. Package contents

- `tools/check_map_cardinals.py` — cardinal validator (`--derive`, `--gate`).
- `CARDINAL_INVENTORY.md` — full six-map results + the 37 proposed corrections + reconciliation recommendation.
- `tools/make_substrate_seed.py` — seed generator with `--tight`.
- `static/tools/seeds/*_tight_seed.png` (×6) — **feed these to Gemini.**
- `static/tools/seeds/*_tight_keymap.png` (×6) — labeled references (your eyes only).
- This guide.

Not re-shipped (already in your tree, unchanged): the six map YAMLs, the manifests, the existing `mos_eisley_substrate.png`, and the standard (loose) seeds — regenerate the latter any time with `make_substrate_seed.py <area_key>` (no `--tight`).
