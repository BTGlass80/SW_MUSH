# HANDOFF — Drop 4.18 · Generated Nano Paint Briefs (wilderness; city core in place)
**2026-05-31** · applies on top of Drop 4.17 (which applies on 4.15c → 4.15b)

## TL;DR
The Nano/Gemini paint *prompt* is now **generated from the same projected grid
data that builds the seed**, so the prompt is as faithful as the seed and can't
drift from the map. You stop hand-writing `{GEOGRAPHY}` for wilderness — the
generator emits a ready-to-paste prompt per region. The reusable core
(`paint_brief_common.py`) is built so the **city** brief generator (next) is a
thin layer on top.

## Why this drop
We were feeding Nano very broad terms while sitting on the full grid. Two facts
drove the design:
- **Numeric coordinates are useless to img2img models** — they have no spatial
  addressing; "obelisk at (97,79)" is noise. What they obey is the seed image +
  RELATIVE language + density cues + vivid nouns.
- **The data behind the coordinates is gold** if translated into that language.
So the generator translates the projection into three faithful channels:
placement (relative regions), per-feature visuals (authored `short_desc`), and
a terrain-texture line — all grid-derived, one source.

## What shipped
**`tools/paint_brief_common.py` (NEW)** — shared paint-brief core:
- `MASTER_PROMPT` — the canonical style wrapper (NANO_MAP_PACKAGE §2.5 now
  points here; the generator fills `{ASPECT}`/`{GEOGRAPHY}`).
- `relative_region(ox,oy,W,H)` — position → painter phrase ("upper-left",
  "center", "far-west edge, mid-height"). y-down, north=top.
- `placement_clause(nodes,W,H)` — landmarks placed on their gold blocks;
  **edge-aware exits** (a border exit → "off-map trail leaving the frame"; an
  interior exit → "in-place stairwell/shaft/manhole", not a direction).
- `visual_from_desc(short_desc,description)` — the paintable sentence, trimming
  narrative tails ("…defaced — someone wanted it forgotten" → "…defaced";
  "Sister Vitha keeps the watch" dropped).
- `coarse_region_phrase` / `cardinal_word` / `aspect_phrase` — density + aspect.

**`tools/gen_wilderness_overview.py` (modified)** — now also emits
`static/tools/seeds/<slug>_paint_brief.md`: the full master prompt with a
generated `{GEOGRAPHY}` (subject + dominant terrain + an honesty line naming the
real feature count and "keep them spaced" + the placement clause + per-feature
authored visuals + "no other major landmarks"). Nodes are enriched with authored
`short_desc`/`description`/`terrain`; the collapsed village gets a synthesized
visual from its central member. New `--briefs-out` flag (default
`static/tools/seeds`). The overview YAML + JS regenerate **byte-identically** to
4.17 (deterministic projection) — only the briefs are new output.

**Generated briefs (NEW):**
- `static/tools/seeds/tatooine_dune_sea_paint_brief.md` — open dunes everywhere;
  HIDDEN VILLAGE center, ANCHOR STONES lower-right, RUINED OBELISK upper-left,
  HERMIT'S HUT lower-center; Jundland = off-map west trail; authored visuals per
  feature; keep 4 features spaced.
- `static/tools/seeds/coruscant_underworld_paint_brief.md` — dark ferrocrete
  strata; 5 features placed; SURFACE ENTRY = in-place shaft (it's a vertical
  exit, mid-grid, not an edge direction).

**Docs:** NANO_MAP_PACKAGE §2.5 points at the canonical wrapper; §6.3 replaced
the hand-written wilderness `{GEOGRAPHY}` with "open the generated brief, copy
the fenced prompt"; §6.5 contents updated. MAP_PLAN records 4.18 and lists the
**city paint-brief generator** as the next item (shared core already in place).

## Tests
- `tests/test_paint_brief_faithful.py` (**NEW, 15 passed**): relative-placement
  quadrants + edges; flavor-tail trimming + description fallback; aspect;
  edge-aware exit phrasing; brief embeds master prompt + correct aspect + each
  landmark's relative placement + authored visual (tails NOT leaked); dominant
  terrain + real count + "no other major landmarks"; underworld interior exit =
  shaft; era-clean; count matches real landmarks (no invented POIs).
- `tests/test_wilderness_overview_faithful.py` (4.17) re-run: **14 passed** (YAML/
  JS regenerate identically, so the projection locks still hold).
- Combined: **29 passed**. All touched Python AST-clean.

> Full pytest (~4,854) is yours on Windows; sandbox ran the changed-module
> suites only.

## How to use (per region)
1. Open `static/tools/seeds/<slug>_paint_brief.md`, copy the fenced prompt.
2. Attach the matching `static/tools/seeds/<slug>_tight_seed.png`, run Nano.
3. Save to `static/maps/<slug>_substrate.png`.
4. Re-run `gen_wilderness_overview.py` — `substrate_image` auto-engages; pins
   stay grid-faithful (no pin-drag).

## Next: city paint-brief generator
The city briefs in NANO_MAP_PACKAGE §3 are still hand-written. The next drop
reuses `paint_brief_common.py` against the city map YAMLs (room `map_x`/`map_y`,
districts): project room/district positions → placement + density bins (cities
are dense, so the binning pays off here) + per-room flavor, replacing the
hand-written city `{GEOGRAPHY}`. The shared core means it's mostly a new
data-loader + a city-specific geography assembler.

## Boundaries / honest state
- **Nothing painted yet** — briefs are ready, no PNG exists; Tier-1b renders the
  procedural fallback until you paint + re-run.
- **Browser smoke + full pytest pending on your hardware.**
- City briefs not yet generated (next drop); only wilderness so far.
- Flavor extraction is heuristic — it trims obvious narrative tails but may keep
  an evocative lore sentence (e.g. underworld "The Reaper is a creature, a gang,
  or a rumor"). Authored and harmless; tighten the heuristic later if wanted.

## Apply
`Expand-Archive -DestinationPath . -Force` (root-mirrored). Depends on 4.17.
