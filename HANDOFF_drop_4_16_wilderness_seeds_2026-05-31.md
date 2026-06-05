# HANDOFF — Drop 4.16: Wilderness Substrate Seeds + Nano Package

**Date:** 2026-05-31
**Architecture-of-record:** `sw_d6_mush_architecture_v51.md`
**Builds on:** 4.15a/b/c (Tier-1b region selection + live ⊕ overview map)
**Apply:** `Expand-Archive -DestinationPath . -Force` from the project root. Root-mirrored.
**This drop is both a code drop AND your ready-to-run Nano package.**

---

## TL;DR

This is the painted-wilderness design's **§4b enabler** plus the **Nano package for
the two wilderness regions**. `make_substrate_seed.py` now has a `--wilderness` mode
(soft terrain blobs + POI gold-blocks + faint tracks); the **Dune Sea** and
**Coruscant Underworld** seeds/keymaps/manifests are generated and in the tree; and
`NANO_MAP_PACKAGE.md` §6 spells out exactly what to feed Gemini and where to save the
result. **Read `MAP_PLAN.md` first** — it re-draws the whole map plan end to end (you
asked for the thread; that's it).

Nothing is painted yet (that's your Nano pass). The procedural fallback still renders,
so the game is unaffected until you paint + uncomment.

---

## A. What shipped (verified green in-sandbox)

**Tools (2):**
- `tools/make_substrate_seed.py` — new `--wilderness` mode (`render_wilderness`):
  reads a region *overview spec*, renders blurred soft terrain zones (per `terrain`
  hue), gold POI building-blocks (distinctive) / grey dots (generic), faint tracks,
  + a labeled keymap. City `render()` path untouched (byte-stable).
- `tools/make_register_manifest.py` — `DISTINCTIVE_ICONS` widened with wilderness POI
  icons (`farm, tents, pit, spire, shaft, factory, hideout, maze`); additive, cities
  unaffected. Reads the overview spec's `landmarks` unchanged → 6-pin manifests.

**Data (2 new region overview specs):**
- `data/worlds/clone_wars/maps/tatooine_dune_sea_overview.yaml`
- `data/worlds/clone_wars/maps/coruscant_underworld_overview.yaml`
  Transcribed faithfully from the 4.15a Tier-1b fixtures (same 700×600 space), with
  `terrain_zones` (soft blobs) + `routes` + `landmarks` (POIs = pins) + a pinned
  `substrate_image` (manifest metadata).

**Generated artifacts (the Nano package payload):**
- `static/tools/seeds/{tatooine_dune_sea,coruscant_underworld}_tight_seed.png` —
  **feed these to Gemini.**
- `..._tight_keymap.png` (labeled refs) + loose `..._seed/_keymap.png` (previews).
- `static/tools/manifests/{tatooine_dune_sea,coruscant_underworld}.json` — 6 pins
  each (4 distinctive), substrate field = the canonical `/static/maps/<region>_substrate.png`.

**Renderer fixture (1):**
- `static/spa/m3_tier_wilderness_body.js` — commented `substrate_image` hints
  pre-placed in DUNE_SEA + CORUSCANT_UNDERWORLD (post-paint = one-line uncomment).
  Inert until uncommented; the 32 wilderness tests stay green.

**Docs (2):**
- `NANO_MAP_PACKAGE.md` — **§6 wilderness addendum**: prompt bullet substitutions
  (zones=terrain, faint lines=tracks), Dune Sea + Underworld briefs (`{ASPECT}` 1.167,
  IP-neutral `{GEOGRAPHY}`, save paths), re-import steps, package contents.
- `MAP_PLAN.md` — **the whole map system spelled out** (two map kinds, hybrid
  renderer, tier ladder, pipeline diagram, status, Nano route).

**Tests (1 new file):**
- `tests/test_wilderness_substrate_seed.py` — **13 passed.** Specs well-formed +
  era-clean + single-level; `--wilderness` renders at the right aspect and rejects
  city YAMLs; manifests build (6 pins / 4 distinctive, fractions in [0,1], canonical
  substrate path); package §6 has both briefs + save paths + IP-neutral geography;
  fixtures carry commented hints.
- Regression: the 32 wilderness body/region tests (4.14/4.15a) stay green; both tools
  AST-clean; the wilderness body `node --check`s clean.

---

## B. How to run the Nano pass (your box, Gemini/Nano Banana)

1. **Paint one first as the style anchor.** If you haven't yet picked an atlas keeper,
   the Dune Sea is a good first wilderness target. Feed
   `static/tools/seeds/tatooine_dune_sea_tight_seed.png` + the §2.5 master prompt with
   `{ASPECT}` = **1.167:1** and the Dune Sea `{GEOGRAPHY}` (package §6.3), applying the
   two §6.2 bullet substitutions. Generate 6–8, pick the keeper, save to
   **`static/maps/tatooine_dune_sea_substrate.png`**.
2. **Carry that keeper as the style-reference image** into the Underworld generation
   (and ideally the six cities) so the atlas reads as one hand. Feed
   `coruscant_underworld_tight_seed.png`, `{ASPECT}` 1.167, the Underworld
   `{GEOGRAPHY}` → save **`static/maps/coruscant_underworld_substrate.png`**.
3. **Register pins:** open
   `http://<host>/static/tools/map_register.html?manifest=/static/tools/manifests/<area_key>.json`,
   confirm the 4 distinctive pins sit on their painted features (drag to fix), EXPORT.
4. **Wire it:** uncomment the `substrate_image:` hint for that region in
   `static/spa/m3_tier_wilderness_body.js`. Done — Tier-1b now paints, with the POIs
   on top.

Never feed a keymap to Gemini (it has text; Gemini OCRs + filters). The seeds are
text-free for exactly this reason.

---

## C. Honest boundaries (no phantom-delivery)

1. **Nothing is painted yet.** This drop produces the seeds/specs/package; the actual
   PNGs come from your Nano pass. The renderer keeps showing the procedural fallback
   until you paint + uncomment — verified by the 32 still-green tests.
2. **Browser smoke pending (your hardware).** The seed *images* are verified visually
   in-sandbox (terrain blobs soft, gold POIs on-spot, north-up, distinct warm/cold
   palettes). The full loop — paint → register → uncomment → renders substrate-first
   at Tier-1b with the overlay on top — needs the in-browser pass after you paint.
3. **Two sources kept in lockstep by hand.** The overview specs are transcribed from
   the JS Tier-1b fixtures. They match now; if you edit one, edit the other. The clean
   fix (generate the JS fixture from the spec) is listed in `MAP_PLAN.md` §6.4 — a
   future consolidation, not done here.
4. **Region pre-selection still wants the server field** (from 4.15c §C): ⊕ lands on
   the right region only when the live `area_key` equals the region slug, until the
   server emits `wilderness_region_id`/`region_key` on the area payload.

---

## D. Recommended next steps (your pick)

1. **Paint the Dune Sea** (the proof) → register → uncomment → browser-confirm. This
   validates the whole pipeline end-to-end for the first time.
2. **Paint the Coruscant Underworld** (Nar Shaddaa flavor) once the proof holds.
3. **Server region emission** — finishes ⊕'s region pre-selection robustly.
4. **Single-source the fixtures** (`MAP_PLAN.md` §6.4) — kill the spec↔fixture drift.
5. **Six-city Nano pass** — the city package (§1–5) has been ready; same style
   reference unifies cities + wilderness.

Full pytest on your Windows box + the §B browser pass are the ground-truth gates.
