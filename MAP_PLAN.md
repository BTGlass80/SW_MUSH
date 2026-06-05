# SW_MUSH — Map System Plan (the whole thread, spelled out)

*Last updated 2026-05-31 (Drop 4.16). Supersedes scattered handoff notes; fold into
`sw_d6_mush_architecture_v51.md` §8 when this stabilizes.*

This is the single place that explains how maps work, what's built, what's painted,
and what's left. Read top to bottom.

---

## 1. There are TWO kinds of map (this is the thing that's easy to lose)

| | **Tactical / area map** | **Region overview map** |
|---|---|---|
| What it shows | the player's **actual rooms** in their current area | a stylized **whole-region** picture |
| Where | the live mini-map + the ⛶ sector modal | the ⊕ Holocarta navigator, Tier-1b |
| Source of geometry | server `AreaGeometry` (rooms/districts/streets) via `M3Adapter.fromAreaGeometry` | a hand-authored region descriptor (POIs, terrain zones, routes) |
| Renderer | `M3CompositionEngine.Tier1aBody` | `m3_tier_wilderness_body.js` (Tier-1b) |
| Click-to-walk | yes (room cells) | no (it's an overview; you read it, then move) |
| Painted substrate | per **city** (Mos Eisley, Senate, …) | per **region** (Dune Sea, Underworld, …) |

Both use the **same hybrid renderer** (below) and the **same painting pipeline** — the
only real difference is the seed grammar (streets vs terrain) and the data source.

---

## 2. The hybrid renderer (how any map draws)

Every map is a **procedural SVG compositor** with an **optional painted raster
substrate** underneath:

```
background atmosphere → SUBSTRATE (painted PNG, if present) → districts/terrain →
security tint → streets/routes → shadows → landmarks/POIs → labels → overlays
```

- **No painting yet?** The procedural layers render a complete, coherent hand-drawn
  map on their own (vector districts/terrain + vector landmarks). This is the
  *fallback*, and it's in the right art idiom — not a blank grid.
- **Painting present?** `L_SubstrateImage` paints the PNG and the procedural
  ground/district/terrain layers **drop out** ("substrate-first"); POIs, routes, and
  labels stay **on top** so the map is still navigable.
- **Close zoom (tier ≤ 1):** the micro-overlay (`L_SubstrateRooms`) dims the painting
  and brings crisp **vector room cells** (with `data-room-id` for click-to-walk)
  forward. So the painting is *atmosphere*; the vector layer is the *precision
  surface*. This is why a painting "doesn't have to hold up at the micro level."

Substrate wiring:
- **Cities:** `substrate_image:` line in the area map YAML (commented until painted).
- **Regions:** `substrate_image:` key in the region fixture in
  `m3_tier_wilderness_body.js` (commented hint pre-placed — Drop 4.16).

---

## 3. The navigator tier ladder (the ⊕ overview map)

`M3MapNavigator` is a zoom/pan/crumb ladder: **galaxy → system → planet → city →
district(1a) → WILDERNESS(1b) → interior(0)**. As of Drop 4.15c it is **live** behind
the ⊕ button (additive; the ⛶ tactical modal is untouched). Status by tier:

- **1b (wilderness):** live + region-aware — renders the player's region (Dune Sea vs
  Coruscant Underworld), derived from the live area via `M3Adapter.regionKeyForArea`.
  **This is the lane we've been building (4.15a/b/c + 4.16).**
- **1a (district):** live — renders the player's real area geometry (`data`
  forwarded, Drop 4.15c).
- **galaxy / system / planet / city:** **demo fixtures** for now (e.g. a Tatooine
  planet plate). Making these data-driven is separate future work.

---

## 4. The painting pipeline (one diagram for both kinds)

```
 map YAML  ──make_substrate_seed.py──▶  *_tight_seed.png   ──┐
 (city)                                  (+ *_tight_keymap)   │  feed seed (+ the ONE
                                                              ├─▶ shared style-reference
 region overview YAML ──(--wilderness)─▶ *_tight_seed.png ───┘   image) to Gemini "Nano"
 (Drop 4.16)                             (terrain blobs +              │
                                          POI gold-blocks +            ▼
                                          faint tracks)        ..._substrate.png  (painted)
                                                                       │
 make_register_manifest.py ─▶ manifests/<area_key>.json ──▶ map_register.html
   (pins from landmarks)                                    (drag pins onto features,
                                                             EXPORT YAML)
                                                                       │
                                                                       ▼
                                          uncomment substrate_image  ──▶  renders painted
                                          (YAML for city / JS fixture     (substrate-first;
                                           for region)                     overlay on top)
```

Steps 1–2 (seed tooling) are **engineering, no art dependency**. Steps 3–5 (paint,
register, wire) are **art passes** that land incrementally — the procedural fallback
always renders in the meantime, so nothing is ever broken by an unpainted region.

---

## 5. "Is painted the right idea?" — settled

**Yes, for both kinds — but de-risk it once before scaling.** The procedural
alternative is itself hand-authored art, so painting is strictly higher quality at
similar authoring cost, and maps are stable (low regeneration tax). The catch: **zero
substrates have been painted yet** and the pipeline has never run end-to-end with a
real Gemini image. So the recommended first move is **one real paint proof** (Mos
Eisley from its existing seed, or now the Dune Sea from its new wilderness seed) →
register → confirm it renders in-browser with the overlay — before committing to the
full six-city + N-region atlas.

---

## 6. Status — what's DONE vs WHAT'S LEFT

**Done (in your tree):**
- Hybrid renderer + substrate-first + micro-overlay (`m3_composition_engine.js`).
- Cardinal validation/correction tools; all six city maps pass `check_map_cardinals`.
- City seed pipeline: `make_substrate_seed.py --tight`, six city tight seeds + keymaps,
  manifests, `map_register.html` — packaged in `NANO_MAP_PACKAGE.md` (§1–5).
- **Tier-1b region selection (4.15a/b/c):** wilderness body renders any region
  substrate-first; navigator/assembled-client forward region/regionKey + live data;
  `M3Adapter.regionKeyForArea`; **live ⊕ overview map** in `client.html`.
- **Wilderness seed pipeline (4.16):** `make_substrate_seed.py --wilderness`; Dune Sea
  + Coruscant Underworld overview specs; their tight seeds + keymaps + manifests;
  `NANO_MAP_PACKAGE.md` §6 (wilderness briefs).
- **Faithful wilderness overview (4.17):** `tools/gen_wilderness_overview.py` projects the
  REAL navigable-grid landmarks (north=y+1) into the 700×600 overview, collapsing the
  Jedi-village cluster and reading region exits from the grid edges. It emits BOTH the
  overview YAML (seed/manifest) and the live `m3_wilderness_overview_data.js`, which
  `resolveRegion` prefers over the showcase fixtures — so the Tier-1b map cannot drift
  from the grid. Coordinate convention unified to SVG y-down across overview/seed/manifest/
  renderer; substrate auto-engages on PNG presence. This is the single-source fix below,
  now DONE.
- **Generated paint briefs (4.18):** `tools/paint_brief_common.py` (shared core) +
  `gen_wilderness_overview.py` now emit a full ready-to-paste Nano prompt per region
  (`static/tools/seeds/<slug>_paint_brief.md`). Placement (relative regions), per-feature
  visuals (from each landmark's authored `short_desc`), and terrain texture are all derived
  from the grid — so the PROMPT is as faithful as the seed and can't drift. Edge exits read
  as off-map trails, interior exits as in-place shafts.

**Left:**
1. **City paint-brief generator** — reuse `paint_brief_common.py` against the city map
   YAMLs (room `map_x`/`map_y`, districts) to generate city `{GEOGRAPHY}` briefs the way
   wilderness now does: project room/district positions → placement + density bins +
   per-room flavor. Replaces the hand-written §3 city briefs. (Bigger lane; the shared core
   is already in place.)
2. **Paint the substrates** (Nano) — feed `static/tools/seeds/<slug>_paint_brief.md` (the
   generated prompt) + the matching tight seed. After painting, re-run the generator
   (substrate auto-engages; pins stay grid-faithful — do NOT drag pins).
3. **Server region emission** — emit `wilderness_region_id`/`region_key` on the area
   payload so ⊕'s region pre-selection is robust regardless of `area_key` shape
   (small server drop; Phase-1 protocol-substrate category).
4. **Upper navigator tiers** (galaxy/system/planet/city) → data-driven (separate lane).

---

## 7. The Nano route — what to hand the painter

Everything is in **`NANO_MAP_PACKAGE.md`**:
- §2.5 master prompt (verbatim; swap `{ASPECT}` + `{GEOGRAPHY}`), §2.6 city briefs.
- **§6 wilderness addendum:** two bullet substitutions (zones=terrain, faint
  lines=tracks) + Dune Sea + Underworld briefs + re-import steps.
- One **shared style-reference image** (paint one keeper first, reuse as the look
  reference for all the rest) is what keeps the whole atlas visually unified.

Seeds to feed live in `static/tools/seeds/` (`*_tight_seed.png`). Keymaps are your
labeled reference — **never feed a keymap** (it has text; Gemini OCRs + filters).
