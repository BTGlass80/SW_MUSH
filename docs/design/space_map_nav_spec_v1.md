# Space Navigation Map — Spec v1 (2026-06-13)

Adds the **navigation-aid + info** layer to SPACE that the ground map already has.
Companion to the deferred ground overlay work (`MAP_NAV_OVERLAY_DROP_20260529.md` §4) and
the map-quality effort (`map_automation_framework_v1.md`). Scoped now; built post-backlog
with the rest of the map design-pass.

## The gap (verified against HEAD)

Space today has a **tactical radar** (`static/spa/m3_cockpit.js` — combat range-bands: own
ship, allied dots, hostile boxes) and a **text list** of adjacent zones. There is **no
visual map of space** — no galaxy view, no system view, no visual zone graph. Space sits
OUTSIDE the 7-tier ground zoom ladder (`m3_tier_registry.js`); the cockpit is a parallel UI.

Two design docs (`ground_ux_overhaul_design_v1.md`, `space_overhaul_v3_design.md`) reference
a "zone map" as if it exists — it does not. Radar ≠ navigation aid: the radar shows the
local tactical bubble, not where you can GO or what's THERE.

## The data is already built — only rendering is missing

`data/worlds/clone_wars/space_zones.yaml` (43 entries) is a complete navigable graph,
structurally the space twin of the room exit graph. The `Zone` dataclass
(`engine/npc_space_traffic.py`) carries everything a map needs:

| Field | What it gives the map |
|---|---|
| `id`, `name` | node identity + label |
| `type` (ORBIT / DEEP_SPACE / HYPERSPACE_LANE / DOCK) | node glyph/style |
| `adjacent: [zone_id]` | the EDGES — what you can jump to (navigation) |
| `planet` | which planet a zone orbits (groups system view) |
| `authority` (republic/cis/hutt/contested/neutral) | faction tint (info) |
| `hazards` ({nav_modifier, sensor_penalty}) | danger indicators (info) |

`parser/space_commands.py` already broadcasts `adjacent_zones` (name + type + security) to
the client each tick. So the producer exists; the consumer (a renderer) is the whole job.

## Design — a schematic, NOT a painting

Space is abstract (nodes + jump lanes), not terrain, so it wants a clean **holo/vector
schematic**, not a Nano painting. This is cheaper and more legible than a painted substrate
and needs no Nano pipeline. Two view levels mirror the ground tiers:

### Space-Tier S2 — SYSTEM view (the everyday space map)
The zones of the player's current system (all zones sharing a `planet` + the deep-space /
lane zones touching them). Renders:
- **Nodes**: one per zone, glyph by `type` (orbit ring, dock bracket, lane chevron, deep-space dot).
- **Edges**: lines for each `adjacent` pair — the jump graph. The player's current zone is highlighted; one-hop-reachable zones are emphasized (these are the clickable jump targets).
- **Faction tint**: node fill/border by `authority` (Republic blue, CIS red, Hutt amber, contested hatched, neutral grey) — the at-a-glance "whose space is this."
- **Hazard pips**: a small warning glyph on zones with non-empty `hazards`.
- **Click-to-jump**: clicking a one-hop-adjacent zone issues the jump/nav command for that zone (the space twin of ground click-to-walk). Non-adjacent → no-op or route preview (see S1).

### Space-Tier S1 — GALAXY view (the strategic overview)
All systems as clustered nodes (group zones by `planet`; deep-space/lanes between clusters),
with hyperlane edges between systems. Faction territory shading at the cluster level. This is
the "where am I in the war" view and the multi-hop **route planner**: click a distant
system → highlight the lane path (BFS over `adjacent`) → optionally issue a multi-hop
auto-nav. Read-only is fine for v1 (show the route; player jumps hop-by-hop).

### Where it lives
A new **space view panel** parallel to the cockpit's existing columns — NOT a new ground
tier. Reuse the cockpit's RIGHT column (it already hosts the hyperspace plot) or add a
toggle between RADAR (tactical) and MAP (navigation) in the center. The two are
complementary: radar for combat, map for getting somewhere.

## Build phases (post-backlog, render-lane only)

1. **S2 system map, read-only** — render the zone graph for the current system from the
   `adjacent_zones` feed already on the wire. Nodes + edges + faction tint + hazard pips.
   No new data, no new producer. (The high-value core — this alone replaces "text zone
   list" with a real navigation aid.)
2. **S2 click-to-jump** — wire a node click to the jump command (mirrors ground
   click-to-walk §4(f); same plumbing pattern).
3. **S1 galaxy view + route preview** — cluster by system, hyperlane edges, BFS route
   highlight. The strategic/info layer.
4. **Polish** — animate the player's jump along the edge; live faction-tint updates from the
   Director's zone authority.

## Invariants / cautions

- **Graph-driven, like ground.** Space nav is the `adjacent` graph; the map is display +
  click-to-issue-command. Never coordinate-jump — issue the real nav command (no teleport).
- **Web-first; Telnet degrades** to the existing text zone list ("requires web client" for
  the visual).
- **No phantom producers.** Every field rendered (`authority`, `hazards`, `adjacent`) has a
  live producer in `space_zones.yaml` / the `Zone` dataclass — verified. Don't render a
  field without confirming its producer at build time.
- **No Nano needed.** This is vector/SVG schematic rendering, not painted substrate — it
  does not touch the map-automation framework.

## Open questions for Brian

- **S2 vs S1 split**: is one combined zoomable space view simpler than two, given only ~6
  systems? (Could be a single pan/zoom schematic rather than two tiers.)
- **Radar/map coexistence**: toggle, or both visible (radar small, map large) when not in
  combat?
- **Route auto-nav**: does clicking a distant system in S1 just PREVIEW the route, or
  offer a multi-hop auto-jump? (v1 recommends preview-only.)
