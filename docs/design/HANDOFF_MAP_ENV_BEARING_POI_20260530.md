# HANDOFF — Map (A+D+B) + env + bearing + dynamic POI feed — 2026-05-30

**Zip:** `SW_MUSH_drop_map_env_bearing_poi_2026-05-30.zip` — **cumulative**; contains everything
below. Apply with `Expand-Archive -Force` over project root. Supersedes the prior cumulative
zip. (Built on the HEAD you uploaded.)

**New source:** `engine/world_time.py`, `engine/bearing.py`
**Changed source:** `engine/area_map.py`, `server/session.py`, `static/client.html`,
`static/spa/m3_adapter.js`, `parser/builtin_commands.py`, `tools/check_map_cardinals.py`
**Changed data:** `data/worlds/clone_wars/planets/{tatooine,nar_shaddaa}.yaml`
**New tests:** map (`test_area_map_emits_slug`, `test_map_cardinals_reverse`,
`spa/test_clickwalk_slugjoin`, `spa/test_map_label_lod`), env (`test_world_time`,
`spa/test_env_substrate_wireup`), bearing (`test_bearing`, `test_bearing_wireup`),
**POI (`test_poi_feed`)**.

---

## NEW — dynamic POI feed (live bounty entities on the map)

The map's `L_Entities` layer renders `dynamic.poi` glyphs and supports kinds
`vendor / mission / bounty / objective / anomaly_t1 / anomaly_t2 / anomaly_t3` — but
`dynamic.poi` was fed **only from static authored landmarks**. Runtime entities (bounty
targets) never reached the map. This adds a live feed, same shape as the contacts feed.

**`server/session.py`** — new `_build_area_pois(db, registry, area_key)`, called in the HUD
augmentation right after contacts; stamps `hud["pois"]`. v1 source: **posted bounty
contracts** whose `target_room_id` falls in a covered room, mapped to render coords via the
same `resolve_area_room_ids` bridge contacts use → `{kind:"bounty", x, y}`. Failure-tolerant
(a bounty-board error returns `[]`, never breaks the HUD).

**`static/spa/m3_adapter.js`** — `_buildDynamic` now appends server `geom.pois` (Y-flipped to
match the landmark POIs) to the landmark-derived list. Validates each entry (`kind` + finite
x/y); invalid/empty entries skipped; **back-compatible** (no `pois` field → landmark-only as
before).

**`static/client.html`** — stores `data.pois → _sw_areaGeom.pois` on both the area-transition
and per-tick paths (mirroring contacts; refreshed every push).

Chain:
`_build_area_pois (bounty target_room_id → render coords) → hud["pois"] → _sw_areaGeom.pois → adapter merge (Y-flip) → L_Entities → bounty crosshair glyph`.

**Scope / extension points (deliberately not wired — documented in the method):**
- **Anomalies** (`anomaly_t1/t2/t3`, incl. world boss t3) anchor to a landmark `room_id` and
  are mappable, BUT they're enumerated **per-region** via
  `wilderness_anomalies.get_anomalies_for_region`, not a global/DB query — pulling them in
  means resolving the area's region first. The `kind` values and render path are already
  there; add the region lookup in `_build_area_pois` when ready.
- **Mission/objective** markers: once a mission carries a render-mappable target room.

Both are a small follow-up each — the renderer and the merge are done; only the server-side
enumeration is missing.

---

## RECAP — earlier this session (in your HEAD; in this zip)

- **Map A** — click-to-walk reachability (slug-join; vertical exits clickable + badges).
- **Map D** — zoom-reveal room labels (BFS depth × zoom; constant on-screen font).
- **Map B** — geometry-true direction words; `check_map_cardinals.py` checks forward **and**
  reverse, collision-aware `--derive`, idempotent `--write`; 4 reverses corrected; gate green.
- **Env substrate** — time-of-day (day-cycle + override) + weather; server emit; client reads.
- **Bearing substrate** — facing from last planar move; `attributes.bearing`; server emit on
  `player_position` + contacts; client plumb; chevron `rotate(bearing)`.

Phase-1 substrate scorecard: time ✅ · weather ✅ · bearing ✅ · furniture ⏸ (not built by
design — every authored area is painted, so the procedural `L_Furniture` path is suppressed;
wiring it now would render nowhere).

---

## Sandbox verification (this drop)

`py_compile session.py` OK; `node --check` client inline script + `m3_adapter.js` OK; server
`_build_area_pois` logic (covered-bounty mapping, empty-map, error-swallow) 4/4; adapter merge
(static+dynamic POIs, Y-flip, validation, back-compat) 6/6; POI static guards 7/7. Full pytest
+ jsdom on your Windows box.

```
run_all_tests.bat
# targeted:
python -m pytest tests/test_poi_feed.py -q
```

**To see it live:** stand in (or near) a covered area (e.g. Mos Eisley) with a posted bounty
whose target NPC is in one of the area's rooms — a red crosshair appears on that room in the
SECTOR MAP. (Generate one via the normal bounty board if none are posted.)

Next candidates: wire **anomalies** into the POI feed (region lookup), or the durable
`dir`-on-`area_geometry.exits` map follow-up. Say the word.
