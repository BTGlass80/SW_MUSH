# mos_eisley — Nano CITY paint brief — STYLE-REF / NAMELESS variant (experiment)

EXPERIMENT TEMPLATE — not the canonical generated brief. This is the input for
the **style-reference experiment** (`tools/mapgen/style_ref_experiment.py`,
handoff §3d). Two deliberate changes vs the generated brief
(`mos_eisley_paint_brief.md`):

  1. **Nameless** — every proper-noun landmark/district name is stripped and
     described by TYPE + POSITION only. Names OCR'd off the seed leaked as text
     labels and tripped the franchise filter in earlier iterations.
  2. **Dual-image / style-locked** — the prompt expects TWO attached images
     (spatial SEED first, painterly STYLE PLATE second) and tells Gemini which
     is which. The style plate is the existing hand-made painting, fed as the
     art-style anchor to pull output toward painterly + away from the
     tactical-grid / VTT look the schematic seed induces on its own.

- **Feed seed (1st image):** `static/tools/seeds/mos_eisley_tight_seed.png`
  (regenerated with the warm-desert hue override by the experiment harness)
- **Style plate (2nd image):** `static/maps/mos_eisley_substrate.png` (the
  current hand-made painting — STYLE ONLY, not layout)
- **Aspect:** 1.046:1
- 7 key features, ~53 background structures, 7 zones.

## Prompt (the harness passes this verbatim; both images attached)

```
Concept-art / environment plate for the map screen of a science-fantasy
role-playing game. BASE LAYER ONLY. The image must contain absolutely NO TEXT
of any kind — no labels, letters, numbers, signs, legend, compass markings,
title, signature, watermark, or border. Names are composited later; a clean
text-free plate is the entire point.

TWO reference images are attached, with different jobs:
  • The FIRST attached image is the SPATIAL LAYOUT. Treat it as the exact,
    fixed composition. Do NOT reflow, rescale, rearrange, or re-proportion
    anything. Keep every road, zone, feature-block and structure exactly where
    it sits in this first image.
  • The SECOND attached image is the ART STYLE to emulate. Copy its painterly
    look — its warm palette, hand-shaded brushwork, soft lighting, tactile
    weathered surfaces and gentle oblique tilt. Do NOT copy any of its content,
    shapes, or layout; the layout comes ONLY from the first image. Paint the
    first image's layout in the second image's style.

Reading the FIRST (layout) image:
  - the bright lines are the main roads/routes: keep them running exactly where
    they are;
  - each solid colored region is a zone: keep its position, size and shape,
    repainting it as warm desert ground/terrain of the character described
    below;
  - the larger blocks mark key features that MUST be clearly visible: paint a
    distinct feature of the type described on that exact spot;
  - the faint pale rectangles are background density: render them as ordinary
    structures filling that area — do NOT make each one a distinct landmark;
  - any marker at the very edge is an off-map direction, NOT a building.

CRITICAL TERRAIN RULE: this is a hot, arid DESERT settlement. There is NO water
anywhere — no sea, lake, river, pond, harbour, canal, or blue water of any
kind. NOTHING in the image is blue. Every surface is warm: sand, dust, ochre
stone, sun-bleached rock, weathered tan structures. If a zone reads cool,
repaint it warm desert.

Style: hand-painted tabletop-RPG sourcebook cartography — painterly, weathered,
warm and tactile, like a printed campaign atlas, matching the SECOND attached
image. Top-down with a gentle ~10-15 degree oblique tilt so structures show a
little height. Cohesive limited warm palette. Render at 1.046:1 aspect ratio,
filling the frame edge to edge. This is a PAINTING, not a schematic, blueprint,
floor-plan, battle-map, hex grid, or virtual-tabletop token map.

Setting: a lived-in, used-future space-opera frontier town. Low-tech,
weathered, functional. No modern-Earth elements, no automobiles, no
contemporary signage, no soldiers or uniformed troops, no franchise iconography.

Subject: a lived-in frontier desert settlement built up across the whole map;
keep the roads and open ground between zones clear.

Zones — repaint each colored region in place as its ground type:
  • lower-center: an open landing field of circular docking pits and parked
    freighters;
  • center: a dense crowded market quarter of stalls and low blocky buildings;
  • left of center: a seedy strip of cantinas and dives;
  • upper-center: a small orderly civic quarter;
  • center: thinning ramshackle outskirts fading toward open ground;
  • right of center: rocky badlands and broken canyon country;
  • right of center: open empty sand dunes.

Key features — paint each on its marked block, nowhere else, and NO other major
landmarks (the faint pale rectangles are ~53 ordinary background buildings,
fill them as generic structures, NOT distinct landmarks):
  • lower-left: a circular landing pad / docking berth for a starship.
  • lower-center: a large grounded vessel repurposed as a structure.
  • center: a half-buried old starship wreck jutting from the ground.
  • left of center: a notorious cantina, the busiest dive around.
  • far-east edge, mid-height: a field of giant bleached skeletal bones in open
    desert.
  • lower-center: an opulent fortified townhouse of a local crime boss.
  • upper-left: a tall slender navigation/comms tower.

Off-map directions (paint ONLY a road/trail leaving the frame that way, NOT a
structure):
  • toward the upper-right;
  • toward the far-east edge, mid-height.

Final reminders: NO TEXT anywhere. NO water, nothing blue. A painterly desert
atlas plate in the style of the second image, clean warm terrain to every edge.
```
