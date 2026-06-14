# Map Tier Cohesion — Design Spec v1 (2026-06-13)

**The decision that must be made BEFORE any Nano painting.** Brian's concern (correct,
verified against HEAD): there are 7 zoom tiers but only 1–2 painted substrates per planet,
the outer tiers can't render paintings at all, and wilderness is a bolt-on. The map design
is not in a final cohesive state, and the Nano effort ("how many paintings, at what tiers,
in what style") is downstream of resolving this. This doc forces the decisions.

## Verified findings (HEAD, file:line)

**1. Only TWO tiers can render a painting.** `substrate_image` is consumed by exactly
`m3_composition_engine.js` (tier 1a district/city, lines 805–818) and
`m3_tier_wilderness_body.js` (tier 1b, lines 437–470). The galaxy / system / planet / interior
tier bodies have **zero** substrate code — they are hard procedural SVG. Confirmed: none of
`m3_tier_{galaxy,system,planet}_body.js` reference `substrate`.

**2. Coverage grid (6 planets × 7 tiers):**

| Planet | Galaxy 4c | System 4a | Planet 3 | City 1a | Wilderness 1b | Interior 0 |
|---|---|---|---|---|---|---|
| Tatooine | proc | proc | proc | **Mos Eisley painted** | **Dune Sea painted** | proc |
| Coruscant | proc | proc | proc | **Senate painted** | **Underworld painted** | proc |
| Kuat | proc | proc | proc | **Kuat City painted** | — none | proc |
| Kamino | proc | proc | proc | **Tipoca painted** | — none | proc |
| Geonosis | proc | proc | proc | **Stalgasin painted** | — none | proc |
| Nar Shaddaa | proc | proc | proc | **Smugglers Moon painted** | — none | proc |

8 paintings total: 6 cities (1a) + 2 wilderness (1b). **Every other tier on every planet is
procedural.** Each painted planet has ONE painted city and at most one painted wilderness.

**3. The "style cliff."** Zooming galaxy→system→planet you see procedural schematic SVG;
then at the city you hit a hand-painted raster with no intermediate painted level. The
transition is a hard aesthetic break, not a graded zoom.

**4. Wilderness is a bolt-on, not a zoom child.** `m3_tier_wilderness_body.js:36-37`:
region selection "remains the deferred UI-wiring drop — until then the showcase/registry
default to Dune Sea" (line 361: `opts.region || resolveRegion(...) || DUNE_SEA`). You do NOT
reach wilderness by clicking a region on the planet tier; tier 3's regions are inert SVG
polygons (`m3_tier_planet_body.js` REGIONS array). Wilderness is a separate modal track.

## BRIAN'S DECISIONS (2026-06-13) — ratified

- **D1 = "attempt paint below galaxy, procedural fallback per tier."** Galaxy (4c) stays
  procedural, definitely (a painted galaxy is the worst Nano case — filter risk + no value
  over a clean holo-schematic). EVERY tier below galaxy — system (4a), planet (3), city (1a),
  wilderness (1b), interior (0) — should **attempt a painting**, BECAUSE automation makes the
  attempt cheap and the screener + human-in-loop catch failures. Per tier, if the painting
  overreaches (Nano can't hold the layout/style, or it screens off-theme), **fall back to the
  existing procedural renderer for that tier** — which already exists for all of them. So this
  is option A (paint everything) MINUS galaxy, with a per-tier procedural safety net. This is
  bolder than the original "procedural outer" recommendation and is correct given the
  automation: the cost of *trying* a painted planet/system is now low, and the fallback is
  free (the procedural code already ships).
- **D2 = yes, but likely OBE.** Build the visual bridge IF a cliff remains — but if the
  painted-tier attempt succeeds down through planet/system, there is no cliff to bridge
  (only the galaxy↔system seam remains, procedural↔painted). Treat the bridge as
  contingent: implement only the galaxy→system seam polish, skip the rest if paintings land.
- **D3 = yes.** Integrate wilderness as a true zoom child of planet (finish the deferred
  navigator wiring). Non-contingent.

IMPLICATION FOR THE NANO QUEUE: the queue GROWS vs. the original rec — it now includes
**attempted system + planet paintings per world**, not just city+wilderness. But each is an
*attempt* with a procedural fallback, so the risk is bounded: a failed planet painting costs
a few generations + a screen, then reverts to the proc renderer that ships today. The
framework must support a per-tier "painted | fell-back-to-procedural" outcome (see below).

## The three decisions that gate Nano

### DECISION 1 — Which tiers are painted vs. procedural? (the style policy)

This is the central call. Three coherent options:

- **A. Paint everything** — planet/system/galaxy paintings too (~18+ new paintings).
  Uniform painted style at every zoom. Maximum cohesion, maximum cost AND maximum Nano risk
  (a painted *galaxy* is exactly where the content filter / off-theme drift bites hardest).
- **B. Procedural outer, painted inner — MADE DELIBERATE (recommended).** Galaxy/system/
  planet stay procedural *schematic* (the "holo-display" look); city + wilderness are
  painted. The cliff becomes a *designed* transition: the outer tiers are intentionally a
  ship's-computer schematic, the inner tiers are the real place. Requires a **visual bridge**
  (below) so the shift reads as intentional, not broken. Lowest cost, lowest Nano risk,
  and it matches the fiction (you read a holomap at range, you see the real street up close).
- **C. Hybrid** — paint planet overviews for the 2–3 major hub worlds only. A compromise;
  less cohesive than A or B.

**Recommendation: B.** The procedural outer tiers aren't a deficiency to paint over — a
clean holo-schematic galaxy/system/planet is *better* navigation + info (faction overlays,
routes, labels stay legible) than a painting would be, and it's the one place Nano is
weakest. Reserve painting for human-scale tiers (city/wilderness/interior) where atmosphere
matters and the seed-grid keeps Nano honest.

### DECISION 2 — How does the style cliff become a designed transition? (the bridge)

If B (or C), specify the bridge so galaxy→city doesn't feel like two different apps:
- **Consistent chrome** across all tiers (same frame, palette accents, label font) so the
  *container* reads as one map even as the *content* shifts schematic→painted.
- **Foreshadow paintability**: a city marker on the planet tier that HAS a painted map gets a
  visual hint (skyline glyph / glow / hover-thumbnail of its substrate) so the zoom-in is
  anticipated, not a surprise.
- **Optionally** a thin painted "establishing band" at tier 3 (a hand-painted horizon strip
  or planet-surface texture) to ease the jump — only if B's pure-schematic reads too cold.

### DECISION 3 — Is wilderness a peer of city, integrated into the zoom? (the hierarchy)

Today wilderness is a bolt-on defaulting to Dune Sea. Two coherent end-states:
- **Integrate it**: tier-3 planet regions become *clickable* and zoom into their tier-1b
  wilderness painting (the deferred navigator wiring). Wilderness becomes a true zoom child
  of planet, peer to city. This is the cohesive answer and it's mostly the already-deferred
  UI-wiring drop (`m3_tier_wilderness_body.js:36`).
- **Keep it modal**: wilderness stays a region-selector view, explicitly documented as a
  parallel track, not a zoom child. Cheaper, but the incoherence Brian noticed remains.

**Recommendation: integrate** (finish the deferred wiring) — it's the difference between
"7 cohesive tiers" and "5 tiers + a side door." It's render/UI work, no new data.

## Engineering consequence of D1 (flagged now)

The system (4a) and planet (3) tier renderers have ZERO substrate code today (verified — only
`m3_composition_engine.js` and `m3_tier_wilderness_body.js` consume `substrate_image`). So
"attempt to paint planet/system" requires those renderers to GAIN the same
substrate-or-procedural-fallback branch the city/wilderness tiers already have:
`if (data.substrate_image) render painting; else <existing procedural body>`. This is additive
render-lane work (the procedural body stays as the else-branch = the free fallback), modeled
exactly on `m3_composition_engine.js:805-818`. The map YAML for planet/system tiers also needs
a (commented-until-painted) `substrate_image:` slot. None of this is hard, but it's real work
that precedes painting those tiers — budget it in the design-pass before the Nano queue.

## Coverage policy (D1 = attempt-paint-below-galaxy)

- **Tier 3 planet / system / galaxy: PROCEDURAL, by design.** No paintings. Pin this so no
  future drop adds a one-off planet painting that re-opens the cliff.
- **Tier 1a city: every city map MUST ship with a `substrate_image`.** No procedural-only
  cities (a procedural city next to a painted one is the *within-tier* cliff). Today 6/6
  rollout cities are painted — keep that invariant; budget the paint when a new city lands.
- **Tier 1b wilderness: major regions painted, minor procedural — but document which.** Today
  2 painted (Dune Sea, Underworld). The other Tatooine regions (Jundland, Northern Dunes,
  Xelric, Outer Wastes) are procedural-only — decide per region whether they're "major
  enough" to paint, and record it, so coverage is intentional not accidental.
- **Tier 0 interior: procedural, by design** (floor plans don't want atmosphere paintings).

## How this gates the Nano framework

The `tools/mapgen/` framework paints whatever seed+brief it's given — it doesn't care which
tier. But the BATCH LIST (what to paint) comes from this spec:
- Under Decision B, the Nano queue = **city substrates + major-wilderness substrates only**.
  That's ~6 cities + ~2–4 wilderness = the existing 8 plus any new cities/major regions —
  NOT 18+ planet/system/galaxy paintings.
- So this spec **bounds the Nano effort** and kills the most filter-risky paintings (galaxy/
  planet) before they're ever attempted. **This is why the design must precede Nano.**

## Build sequence (post-backlog, render-lane; no game-data risk)

1. **Ratify Decision 1/2/3** (Brian — this is the design fork; the recommendations above are
   defensible defaults).
2. **Pin the coverage policy** as invariants/tests (procedural tier-3, no-procedural-city,
   documented wilderness coverage).
3. **Build the visual bridge** (chrome consistency + city-marker paintability hint).
4. **Integrate wilderness** (finish the `m3_tier_wilderness_body.js:36` deferred navigator
   wiring so planet regions zoom into wilderness).
5. **THEN Nano**: paint/repaint only the city + major-wilderness substrates the policy
   names, via `tools/mapgen/`. The outer tiers never go to Nano.

## Open questions for Brian (the actual forks)

- **Decision 1**: A (paint all), B (procedural-outer/painted-inner, recommended), or C (hybrid)?
- **Decision 2**: pure schematic outer tiers, or a thin painted establishing band at tier 3?
- **Decision 3**: integrate wilderness as a zoom child (recommended), or keep it modal?
- **Wilderness coverage**: which of the minor Tatooine regions (Jundland, Northern Dunes,
  Xelric, Outer Wastes) are "major enough" to paint vs. stay procedural?
