# Map Navigation Drop — cardinal fixes + micro-overlay (May 29 2026)

Two changes, both requested. One touches the gameplay exit graph; one touches the production map renderer.

---

## 1. Cardinal fixes — gameplay exit directions now match the map (Philosophy B)

Treated the rendered map `x/y` as spatial truth and rewrote wrong-way compass words to the geometry-correct ones, so "go north" moves the marker up on the map.

**Applied + verified (shipped):**
- `data/worlds/clone_wars/planets/coruscant.yaml` — **7 fixes**, now **0 mismatches**.
- `data/worlds/clone_wars/planets/nar_shaddaa.yaml` — **5 fixes**, now **0 mismatches**.

Verification: `check_map_cardinals.py --all` → both clean; `area_loader` loads both; inline comments preserved; re-emitted with matching indent so the diff is **only the changed direction lines** (Coruscant 14 lines = 7 before/after; Nar Shaddaa 10). Collision-safe — the applier resolves contested octants greedily (e.g. `senate_esplanade→monument_plaza` became `northeast`, not `north`, because `north` was already taken) and verified **0 duplicate-direction rooms**.

**Mos Eisley (Tatooine) — fixed by relayout (Philosophy A), now 0 mismatches.** Rather than relabel directions, the room `x/y` were re-solved so the layout agrees with the gameplay directions. A constraint solver (`tools/relayout_map.py`) rotates each cardinal exit to its correct compass angle at its original length (absolute angles pin orientation; a centroid pin handles translation; light repulsion prevents overlap). Result: **48/48 cardinal exits ok, 0 mismatches**, loader passes, rooms well-spread (min spacing 0.29, no overlap), and the spine now ascends correctly (spaceport → market → government → north_end runs south→north, so "North End" is finally at the north).

Consequences of the relayout (all expected for Philosophy A, and you're repainting anyway):
- **New aspect ~1:1** (was 1.55 landscape). The directionally-correct city is near-square. The tight seed was regenerated at the new aspect — paint from `mos_eisley_tight_seed.png` (it reflects the corrected layout).
- **Streets + street-labels removed.** Straight room-to-room ribbons tangle after a relayout and would mislead the painting, so `exit_paths` (and the labels referencing them) were dropped. They aren't used under a substrate at runtime; paint streets in organically, then re-author paths/labels when you finalize.
- **Districts regenerated** as bounding boxes of their member rooms. Because directional layout intermingles district members, the boxes overlap somewhat — treat **rooms + landmarks as ground truth** and paint district character loosely. (Tatooine's planet/gameplay file is untouched — only the display map changed.)
- **Landmark registration is stale** (positions were against the old painting); re-register during the repaint's reimport step.

**Tools (shipped):** `tools/check_map_cardinals.py` (validate · `--derive` · `--gate`), `tools/apply_cardinal_fixes.py` (apply Philosophy B · collision-safe · `--dry-run` · `--all`). Wire `--gate` into substrate pre-flight so a map can't go live with wrong-way exits.

---

## 2. Micro-overlay — tactical room layer under the substrate (production renderer)

**Finding:** the production modal uses the **M3 composition engine** (`static/spa/m3_composition_engine.js`, `Tier1aBody`), not legacy `map_view.js`. And under a painted substrate it rendered **no room layer at all** — the painting was a static picture with only labels + the player marker on top. So there were zero interactive room cells under a substrate.

**Change (3 edits, `m3_composition_engine.js`):**
- **`L_SubstrateRooms`** (new): at close zoom (tier ≤ 1) paints each room as a translucent, glowing tactical cell over the painting — precise click targets and a holo-map read, not opaque fake buildings. Mirrors `L_Buildings`' projection exactly and emits the same `data-room-id` wrapper.
- **Substrate dim:** `L_SubstrateImage` takes a tier-driven opacity; at tier ≤ 1 the painting drops to 0.5 so the tactical layer reads as the navigable surface. Full opacity at tier ≥ 2.
- **Wiring:** the tactical layer is pushed after weather, before labels/entities (so labels + player marker stay on top).

This is the precision mechanism: at city/planet zoom you see the painting; zoom into a district/site and crisp room cells come forward over a dimmed backdrop. Because the cells emit `data-room-id` (render-room-id namespace), the **click-to-walk decoration already in `client.html`** (`class="rm-adj"` + `data-travel-dir`) now has something to attach to under substrates — combined with the cardinal fixes, "click the room east of you" can walk east.

**Verified in sandbox:** `node --check` clean; exports intact (`M3CompositionEngine.Tier1aBody`); adapter confirmed to pass room `id/x/y/w/h` through even under a substrate; structural test of `L_SubstrateRooms` (skips streets, emits `data-room-id` and omits when absent, draws rect+circle per cell, non-scaling stroke).

**Needs your Windows browser smoke-test** (can't render in sandbox): that the cells land on the painted features, the dim level feels right, and clicking a cell actually traverses the exit. Tunables are constants at the top of the two spots (`subOpacity = 0.5`, `tier <= 1` gates, cell `fill-opacity 0.10` / `stroke 1.3`).

---

## Not built (flagged follow-ons)
- **(e) Interior tier** — when an `in`/`out`/`up`/`down`-into-a-building exit is taken, render the building's interior as its own view instead of moving the marker on the city map (resolves "moving inside flings me across the map / leaves me outside"). The data signal exists; needs an interior-grouping map + the inner-tier renderer (Drop 4.14 territory).
- **(f) Click-to-walk handler** — the decoration hook exists in `client.html`; verify in-browser that the click actually issues the exit traversal under substrates (my layer enables it structurally; I couldn't exercise the handler).
- **(d) Landmark `min_zoom` tiering** — optional: set distinctive landmarks to persist across tiers and author POIs at `min_zoom 0/max_zoom 1`. Left untouched to avoid churning your freshly hand-registered landmark blocks.
- **Legacy `map_view.js`** not modified (production is M3); add the same two layers there only if you want fallback parity.

---

## Files in this drop
```
data/worlds/clone_wars/maps/mos_eisley.yaml        # relayout (0 mismatches), districts/streets/bounds regen
data/worlds/clone_wars/planets/coruscant.yaml      # 7 cardinal fixes
data/worlds/clone_wars/planets/nar_shaddaa.yaml    # 5 cardinal fixes
static/spa/m3_composition_engine.js                # micro-overlay (3 edits)
static/tools/seeds/mos_eisley_tight_seed.png       # regenerated from corrected layout (~1:1)
static/tools/seeds/mos_eisley_tight_keymap.png     # labeled reference
tools/check_map_cardinals.py                        # validator
tools/apply_cardinal_fixes.py                       # cardinal applier (collision-safe)
tools/relayout_map.py                               # Philosophy-A layout solver
```
All six maps now pass `check_map_cardinals.py --all` with **0 mismatches**. Root-mirrored: `Expand-Archive -DestinationPath . -Force`. Run the full pytest suite on your box; sandbox did AST + targeted/structural checks only.
