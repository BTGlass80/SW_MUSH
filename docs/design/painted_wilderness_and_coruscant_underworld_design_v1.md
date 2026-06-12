# Painted Wilderness + Coruscant Underworld — Design Capture v1

**Status:** Plan of record (captured, not yet implemented). Written 2026-05-31.
**Architecture-of-record:** `sw_d6_mush_architecture_v51.md`
**Companion docs:** `NANO_MAP_PACKAGE.md` (the painting pipeline), `contestable_wilderness_design_v2.md` (wilderness mechanics).

> **Why this file exists.** During the 2026-05-31 session we worked out (a) that
> Coruscant has full content parity with Tatooine *except* its wilderness map
> renderer, and (b) that the hand-drawn "Nano" painting style transfers ~1:1 from
> cities to wilderness. None of that was written down yet. This file is the
> durable record so the plan survives even if it isn't the next thing we build.
> Everything below was verified against HEAD (the 2026-05-30 23:33 tree), not from
> memory — file paths and symbol names are real and current as of that tree.

---

## 1. The painting pipeline today (what wilderness inherits)

Maps are a **hybrid procedural-SVG compositor + optional painted raster substrate**,
all in `static/spa/m3_composition_engine.js`. Layer z-order (bottom→top):

```
atmosphere → substrate → districts → security tint → streets → shadows →
buildings → furniture → weather → time-of-day → haze → labels → entities → compass
```

Key layers for this plan:

- **`L_SubstrateImage`** paints the PNG when `data.substrate_image` is present
  (tier ≤ 1). This is the hand-painted "Nano" art.
- **`L_Buildings`** (procedural building footprints) is **skipped** whenever a
  substrate is present.
- **`L_SubstrateRooms`** then renders the *tactical room layer* — one cell per
  room — and **emits `data-room-id` for every room with `id != null`** (engine
  line ~255). This is what makes rooms clickable under a painting.

The six painted cities live in `static/maps/` (`mos_eisley`, `coruscant_senate`,
`geonosis_stalgasin`, `kuat_city`, `kamino_tipoca`, `nar_shaddaa`). They were
produced per **`NANO_MAP_PACKAGE.md`**: each city painted by Gemini ("Nano
Banana") from a `*_tight_seed.png` (in `static/tools/seeds/`, emitted by
`tools/make_substrate_seed.py`) using a **verbatim-identical style clause** plus
**one shared style-reference image**, so all six read as a single atlas. The
package's §4 specifies the close-zoom micro-overlay: dim the substrate, bring the
tactical room cells forward. Doc principle: **procedural maps are demoted to
dev/fallback once a place is painted.**

**The transfer thesis:** wilderness regions are structurally a city —
sub-regions ≈ districts, POIs ≈ landmark blocks, routes ≈ roads. So the *same*
style clause + *same* style-reference image will make the city→wilderness
transition seamless **by construction** (one atlas, no per-surface art drift).

---

## 2. Coruscant vs Tatooine — parity audit (verified at HEAD)

Coruscant is at **full parity** with Tatooine on data, NPCs, landmarks, and
anomalies, and it has a painted **Senate** substrate. There is exactly **one**
gap: **the wilderness map renderer.**

| Surface | Tatooine | Coruscant | Status |
|---|---|---|---|
| Planet/city data | `planets/tatooine.yaml` | `planets/coruscant*.yaml` | parity |
| Painted substrate | `mos_eisley` | `coruscant_senate` | parity |
| Wilderness region data | `wilderness/dune_sea.yaml` | `wilderness/coruscant_underworld.yaml` (+ `_landmarks.yaml`) | parity |
| Wilderness anomalies | Dune Sea template set | `coruscant_underworld` set (`maze_rogue`, `coruscant_gang_war`, reactivated B1s) in `engine/wilderness_anomalies.py` | parity |
| **Wilderness map renderer** | works (Dune Sea) | **broken — renders Tatooine sand** | **GAP** |
| Painted wilderness substrate | none yet | none yet | both unpainted |

**The gap, precisely:** `static/spa/m3_tier_wilderness_body.js` hardcodes the
**Dune Sea** fixture inline — `var DUNE_SEA = {...}` (≈ line 195), exposed as
`M3TierWildernessBody.DUNE_SEA / .SUB_REGIONS (5) / .POIS (6) / .ROUTES (4)`. The
builder takes **no region parameter**, so navigating to the Coruscant underworld
renders Tatooine dunes. (The *data* for the underworld is complete and correct;
only the renderer is hardwired.)

---

## 3. Coruscant Underworld — scope (decision locked)

**Single-level, 40×40 grid.** This is Brian's May 24 2026 call, **re-confirmed
2026-05-31**, and it is already what the data reflects:
`wilderness/coruscant_underworld.yaml` states "SINGLE-LEVEL region… the Z-axis
collapsed per Brian's May 24 2026 call… mechanically all wilderness landmarks
live on one 40×40 grid."

> **Reconciliation note.** Architecture §8.13 / an older `design_calls_resolved`
> entry described the underworld as "40×40×**3**." That was superseded by the
> single-level call. The "×3" figure is **stale** — treat single-level 40×40 as
> ground truth. (This file is the canonical reconciliation; the TODO ledger was
> corrected in the same 2026-05-31 pass.)

**Geography/prose direction:** the underworld is a **vertical descent** (levels
1313, the sublevels, USCRU fringe), not desert. When writing its region/POI prose
and choosing terrain tints, borrow the **Nar Shaddaa** brief (smog, neon, strata,
verticality), **not** the Dune Sea brief. The mechanical grid stays flat; the
*flavor* is depth.

---

## 4. The two enablers (the actual work)

### 4a. Generalize `m3_tier_wilderness_body.js` — "render region R, substrate-first"

Refactor from **"Dune Sea hardcoded"** to **"render the region passed in,
substrate-first."** Concretely:

- Accept a region identifier / region-data object (the same way the city/district
  tier bodies already consume per-area data) instead of the inline `DUNE_SEA`
  constant.
- Read `SUB_REGIONS` / `POIS` / `ROUTES` from the region's data, not from module
  constants. Keep the existing Dune Sea fixture as the **fallback/dev default**
  (loud-substitution pattern — documented in the module header, exercised by a
  test that omits region data).
- **Substrate-first:** when the region carries a `substrate_image`, paint it
  (mirror `L_SubstrateImage`) and let the tactical layer come forward at close
  zoom; when it doesn't, fall back to the **procedural sand-/terrain-plate** that
  exists today. This is the same hybrid contract the city renderer already honors.

**Double-duty payoff:** this single refactor *also* fixes the Coruscant underworld
map (§2 gap) — the underworld becomes "just another region R," procedural until
painted. **This is the highest-leverage item: one change closes the parity gap
and unblocks every future wilderness region (painted or not).**

### 4b. Add a wilderness seed mode to `tools/make_substrate_seed.py`

The city seed mode emits crisp district boundaries + bright causeways. Wilderness
wants a different seed grammar so Nano paints terrain, not streets:

- **Soft terrain zones** (dunes, flats, canyon, badlands) as blended blobs, not
  hard-edged districts.
- **POI gold-blocks** at landmark coordinates (same convention as city landmarks,
  so the painter treats them identically).
- **Faint routes** (tracks/trails) rather than bright paved causeways.

Use the **same style clause and the same shared style-reference image** as the
cities (§1) so the atlas stays unified.

---

## 5. The fallback already rhymes (low risk)

If a wilderness region is *not yet painted*, the procedural fallback is already in
the right idiom: `static/spa/m3_assets_wilderness.js` ships hand-drawn **vector
landmarks** (Tusken camp, sandcrawler, krayt skeleton, Jabba's palace, moisture
farm) in the same visual language as the city landmark vectors. So an unpainted
region degrades to a coherent hand-drawn look, not a blank grid — the same way the
cities looked before their substrates landed.

---

## 6. Recommended sequence

1. **4a first** (generalize the wilderness body, substrate-first + region param).
   This alone closes the Coruscant parity gap and makes the Dune Sea data-driven.
   Verifiable in-sandbox via AST + a fixture-omitted module test; full render
   check on Windows.
2. **4b** (wilderness seed mode) — needed before any painting.
3. **Paint Dune Sea** from a wilderness seed (proves the pipeline end-to-end on a
   region we already understand).
4. **Paint the Coruscant underworld** (Nar Shaddaa flavor brief, §3), single-level.
5. Repeat per region as content grows.

Steps 1–2 are engineering (no art dependency); 3–5 are art passes that can land
incrementally because the procedural fallback (§5) always renders.

---

## 7. Open questions / unknowns

- **Region-data shape for the wilderness body.** 4a needs to settle exactly which
  object the generalized builder consumes (the region YAML directly vs an adapter
  payload like the city tiers use). Pre-flight against `m3_adapter.js` before
  coding.
- **Substrate pinning for wilderness POIs.** Cities pin distinctive landmarks to
  painted features and allow generics to be merely "in-zone" (NANO_MAP_PACKAGE
  §4). Wilderness POIs are mostly distinctive (krayt graveyard, Tusken overlook) —
  expect most to need feature-accurate pins.
- **Underworld vertical illusion on a flat grid.** Single-level grid + "descent"
  flavor: decide whether depth is conveyed purely by art/prose or also by a
  tier-label affordance. Not blocking; a polish call.

---

*End of capture. If this plan is picked up, fold its decisions into
`sw_d6_mush_architecture_v51.md` §8 (wilderness) and retire this file to an
`archive/` once implemented, per the usual doc-of-record discipline.*
