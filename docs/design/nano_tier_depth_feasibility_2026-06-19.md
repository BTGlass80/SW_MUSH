# Nano map-depth TEST — tier feasibility (2026-06-19)

Resolves the `MAP.nano_tier_depth_test` design call (Brian: "drill down into the
sub-layers / higher levels we lost in the painted maps, as a test"). Question:
can we seed a FAITHFUL Nano painting for the tiers the painted-map move dropped —
building INTERIOR (lower) and PLANET / SYSTEM / GALAXY (higher)? Grounded in a
HEAD investigation of the tier renderers + world data.

## How the working painted path works (the thing to mirror)
`tools/make_substrate_seed.py` projects an **AreaGeometry YAML**
(`data/worlds/<era>/maps/*.yaml`: `bounds` + `districts[].polygon` + `rooms[].x/y/w/h`
+ `exit_paths[].path` + `landmarks[].pos`) into a text-free seed PNG. Consumed at
exactly two tiers: `1a` city (`m3_composition_engine.js`, via `substrate_image`) and
`1b` wilderness (`m3_tier_wilderness_body.js`). The other four tiers are **pure
procedural SVG built from HARDCODED JS fixtures, not data** (`m3_tier_registry.js`:
only `1a` consumes live `data`).

The real question per tier is therefore NOT "does a renderer exist" but **"does real
coordinate data exist to drive a faithful seed, or would a seed just retrace the
hardcoded fixtures?"**

## Verdict by tier

| Tier | Geometry today | Real data to seed from | Faithfully seedable? |
|---|---|---|---|
| **0 Interior** | Hardcoded cantina ROOM/FURNITURE fixtures (`m3_tier_interior_body.js`) | **Multi-room interior zones HAVE real `map_x`/`map_y` per room + exit graph** (e.g. `coruscant.yaml` Jedi Temple 11 rooms, Senate building) — already paintable as a zone-map (cf. `data/worlds/clone_wars/maps/senate_district.yaml`). Single-room furniture: none. | **YES** for multi-room building interiors (reuse the EXISTING seed tool on a per-building zone-map). **NO** for furniture-level floorplans (no furniture geometry data). |
| **3 Planet** | Hardcoded 8 cities + 5 region blobs (`m3_tier_planet_body.js`) | Only ONE real city per planet (the Mos Eisley street grid). No planet-surface POI frame, no region polygons; the 8 fixture cities don't exist as places. | **NO** — seeding would paint **phantom cities** (no-phantom-producers violation). Data affirms keeping it procedural (D1=B). |
| **4a System** | Hardcoded 5 orbital bodies, polar (`m3_tier_system_body.js`) | `space_zones.yaml` = topology graph (adjacency/type/planet), **no x/y or orbital coords**. | **NO** (faithful). Only a synthesized graph-schematic — same risk as painting the fixture, no fidelity gain. D1=B upheld. |
| **4c Galaxy** | Hardcoded 13 systems, polar; some off-manifest (`m3_tier_galaxy_body.js`) | Lane/planet NAMES only in `space_zones.yaml`; **no galactic coordinates**. | **NO** — and explicitly excluded by `map_tier_cohesion_spec_v1.md` D1=B ("a painted galaxy is the worst Nano case"). Do not build. |

## Bottom line
The **only** tier where existing data supports a faithful, non-phantom seed is the
**building INTERIOR (multi-room-zone case)** — and it needs **NO new tooling**: a
building is a small AreaGeometry zone-map (exactly like `senate_district.yaml`), so
authoring a per-building zone-map YAML (bounds from the zone's `map_x`/`map_y`, one
room footprint each, exit-graph corridors, an entrance landmark) and running the
existing `make_substrate_seed.py` produces an honest seed.

**Planet / system / galaxy are DATA-BLOCKED, not merely design-deferred:** the
renderers are decorative fixtures with no backing coordinates, so any seed there
would trace invented geometry (phantom-producer violation) or synthesize a layout
(no fidelity over the procedural body). The data **affirmatively supports** the
ratified D1=B "procedural outer / paint inner" call rather than overriding it.

**Recommended TEST scope:** ONE multi-room interior — the **Jedi Temple** is richest
(11 rooms, clean entrance hub `jedi_temple_entrance_hall`) — authored as a per-building
zone-map + the existing seed tool + style-ref paint. That is the lone tier where
automation can recover real map depth from real data. Cost: a few candidates (~$1).
