# HANDOFF — anomaly POI feed + RELAYOUT test rebase + HUD resilience fix — 2026-05-30

**Zip:** `SW_MUSH_drop_anomaly_poi_and_relayout_tests_2026-05-30.zip` —
**combined rolled-up** (10 files; supersedes the standalone anomaly-poi zip from
earlier today). Apply with `Expand-Archive -Force` over project root. Built on
the HEAD you uploaded (`SW_MUSH_upload_20260530_1527.zip`).

This drop contains the whole session: (1) the anomaly POI feed, (2) a real HUD
resilience fix, (3) rebasing the Mos Eisley **substrate-relayout** test surface
back to green, and (4) a **CHANGELOG + TODO backfill** (the ledger had lapsed
since 2026-05-25 — see §4 below).

**Changed source:** `engine/area_loader.py`, `server/session.py`
**Changed tests:** `test_poi_feed.py` (anomaly feed, +11),
`test_fmap1_area_geometry_loader.py`, `test_fmap2_area_geometry_registry.py`,
`test_fmap2_session_hud.py`, `test_fmap6_session_contacts.py`,
`test_area_loader_substrate.py`
**Changed trackers:** `CHANGELOG.md` (4 reconstructed entries for the gap + this
drop; header v48→v50), `TODO.json` (`last_updated`→2026-05-30, backfill note,
`TD.ARCH_V51` open item)

---

## 1 — Dynamic POI feed: wilderness anomalies (server-side)

Wires live `anomaly_t1/t2/t3` (incl. the Tier-3 world boss) onto the map's
`L_Entities` layer, alongside the existing bounty crosshairs. No JS changed —
the renderer (`MK_AnomalyT1/2/3`), the `L_Entities` kind map, and the adapter
merge were already done; only the server enumeration was missing.

- **`engine/area_loader.py`** — `_RoomLookupEntry` gains an optional
  `region_slug` (default `None`, back-compatible). `resolve_area_room_ids`
  captures `wilderness_region_id` off the room row it **already** fetches —
  **zero extra DB calls** — so the per-tick anomaly sweep can group by region
  without a DB storm.
- **`server/session.py`** `_build_area_pois` — after the bounty sweep, collects
  the covered regions from the room map, enumerates anomalies per region in
  memory (`get_anomalies_for_region`), maps each `anchor_room_id` → render
  coords, and emits `anomaly_t{tier}` (tier clamped to 1..3). Error-tolerant: an
  anomaly failure never breaks the HUD and never drops the bounty POIs.

Still unwired (documented in the method): **mission/objective** markers — they
carry a destination *name*, not a mappable room id yet.

## 2 — HUD resilience fix (`server/session.py` `_hud_area_map`)

**Real bug caught by `test_broken_get_room_falls_back_silently`** — not a stale
test. When the env-substrate drop hoisted `row = await db.get_room(room_id)` out
of the F.MAP.2 try (to feed both the environment substrate and the registry
path), it left that DB read **unguarded**, so a `get_room` failure crashed the
entire HUD push. Now wrapped: on failure it logs and returns, leaving the legacy
`area_map` already emitted. The test is **unchanged** — it correctly encodes the
"HUD push must never crash" invariant; the code now satisfies it. Happy path is
behavior-identical (only the raising path changed).

## 3 — Mos Eisley v51 substrate-relayout test rebase

**Root cause (verified, not assumed):** the entire CW map set migrated to the
**architecture-v51 hybrid raster substrate lane** — every `data/worlds/clone_wars/maps/*.yaml`
now sets `substrate_image` and each has a painted PNG in `static/maps/`. With a
substrate, the client skips the procedural district/building/**street**/furniture
layers (baked into the painting) and keeps labels/entities/weather/chrome on top.
Mos Eisley's tight relayout (`mos_eisley_tight_seed_RELAYOUT.png`) repositioned
rooms to the painting and **zeroed its exit_paths**. New areas (Kuat, Nar
Shaddaa, Geonosis, Kamino, Senate) were also added.

All rebased values are **ground-truth from the loaded fixtures**, not guesses:

| Test | Was | Now | Why |
|---|---|---|---|
| `fmap1::test_bounds_match_prototype` | (2.4,−0.4,14.8,7.6) | (0.88,−3.26,13.73,9.03) | relaid to substrate |
| `fmap1::test_exit_path_count_matches_prototype` | 12 | **0** | streets baked into painting |
| `fmap1::test_label_count_matches_prototype` | 7 (5 street+2 flavor) | **2** (0 street+2 flavor) | street labels baked in |
| `fmap2::test_mos_eisley_slug_count_is_53` | registry total ==53 | **Mos Eisley's own** slugs ==53 | registry now multi-area (168 total) |
| `fmap2::test_lookup_returns_world_coords…` | (3.9, 6.4) | (4.38, 0.0) | `docking_bay_94_pit` relaid (rid 1) |
| `fmap2_session_hud::test_first_push…` | (3.9, 6.4) | (4.38, 0.0) | same room |
| `fmap2_session_hud::test_subsequent_push…` | (5.4, 5.4) | (5.39, 1.43) | `mos_eisley_spaceport_row` relaid (rid 7) |
| `fmap6_session_contacts::test_npc_uses_cantina…` | (2.8, 2.9) | (2.9, 3.7) | `chalmuans_cantina_main_bar` relaid |
| `substrate::test_senate_district_has_no_substrate` | senate has none | **flipped** → senate declares substrate | senate migrated too |

The slug-count test's intent ("Mos Eisley is fully slug-tagged") is preserved by
re-targeting from the registry-wide total to Mos Eisley's own rooms. The senate
test's intent ("substrate_image is optional") is already covered independently by
`TestSubstrateImageField`'s synthetic no-substrate fixtures, so flipping the real
fixture to declare its substrate loses no coverage. Intent preserved everywhere;
nothing was made vacuous.

---

## 4 — CHANGELOG + TODO backfill (the ledger had lapsed)

Pre-flight caught that **both trackers were stale since 2026-05-25 (SYN.10)** —
the SPA visual port (4.11→4.15 cutover + showToast), the **v51 hybrid raster
substrate migration** (all six maps painted + 4 new areas: Kuat City,
Smuggler's Moon, Stalgasin Hive, Tipoca City), the map A/D/B + env/bearing work,
and the bounty POI feed all shipped without CHANGELOG/TODO entries. (This is why
the relayout was a surprise in §3 — the migration that caused it was never
logged.)

Brought current honestly:
- **`CHANGELOG.md`** — prepended a marked backfill banner + **4 reconstructed
  entries** (2026-05-26→30) built from first-party handoffs
  (`MAP_NAV_OVERLAY_DROP_20260529.md`, `NANO_MAP_PACKAGE.md`,
  `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`) plus symbol-level grep of HEAD.
  Files/tests are HEAD-verified; some dates are marked approximate. Stale header
  ref v48→v50. Discipline (`tracker_update_in_same_drop`) resumes now.
- **`TODO.json`** — `last_updated`→2026-05-30; a `_notes` backfill line; and a
  new tech-debt item **`TD.ARCH_V51`** capturing that `NANO_MAP_PACKAGE.md` names
  `sw_d6_mush_architecture_v51.md` as the architecture-of-record but no v51 doc
  exists and the field still points to v50. (Round-tripped byte-identical except
  my edits — no reformat noise.)

---

## 5 — Architecture doc v51 (closes TD.ARCH_V51)

Wrote **`sw_d6_mush_architecture_v51.md`** (delivered standalone in outputs —
architecture docs live outside the code tree, which is why `Expand-Archive`
never carried v50). It's a surgical revision of v50, not a rewrite: header/§0,
§1.3 code-state (re-grounded at HEAD May 30 — **schema-neutral at 35**), §1.4
"what landed since v50", §1.5 (trimmed), §2.5/§2.6, a new invariant **§4.28**
(hybrid raster substrate render contract), §3 roadmap (re-ranked — engine +
web-client lanes now closed for launch), §9 version history, §10 closing.

The doc folds in two bodies of work v50 didn't have: the **SYN tail**
(SYN.6→SYN.10 — they shipped 2026-05-25 but post-dated the v50 doc, so v50
listed them as open) and the **May 26–30 web/map wave** (SPA port, substrate
migration, map A/D/B, env/bearing, POI feeds). The headline shift recorded: the
web-client lane is no longer "paused behind SYN" — it's the surface that moved.

Then in `TODO.json`: `architecture_of_record` flipped **v50→v51** and
`TD.ARCH_V51` marked **resolved**; in `CHANGELOG.md`: companion-line header →
v51 and a contemporaneous v51 doc-drop entry added (above the backfill banner,
since it isn't reconstructed).

**To apply v51:** place `sw_d6_mush_architecture_v51.md` wherever you keep
architecture docs / project knowledge and discard v50. The code zip
(`TODO.json` + `CHANGELOG.md` + the 8 code/test files) applies with
`Expand-Archive -Force` as usual; the v51 `.md` is **not** in the zip by design.

---

## 6 — Design-call resolutions (2026-05-30) + a deploy action item

Three roadblocking design calls were put to Brian and resolved; recorded in
v51 §8 (+ propagated to §1.5/§3/§7/§10) and `TODO.json`:

- **§8.13 Coruscant Underworld** → **author the full 40×40×3 region file**
  (not landmarks-as-anchors). Now Tier 2 #4 — the main pre-launch content
  build, no longer a design call.
- **§8.7 SYN.4 city-dissolution migration** → **run now, as part of this
  deploy.**
- **§8.16 web-client launch scope** → **pull a selected Phase 2 panel subset
  into launch** (candidates already built in the SPA suite; rest of Phase 2 +
  Phases 4/5 post-launch).

Also closed §8.10 / §8.15 / §8.17 as moot (map renderer + web port shipped;
SYN ran to completion). Three smaller design calls remain open + non-blocking:
T2.5 (Coruscant zone naming), T2.10.c (SRB.1 overdose auto-incap), T2.11.b
(broaden morale-flavored skill set).

> **⚠ Deploy action item (per the §8.7 decision):** this zip does NOT run the
> migration — it's an admin invocation. During this deploy, run
> `await syn4_migrate_dissolve_city_map_cities(db)` once (idempotent via its
> `syn_migration_state` marker; schema-neutral; legacy city-map cities dissolve
> with a 75% refund). The zip applies the code/tests/trackers; the migration is
> the one manual step you chose to run alongside it.

---

## Sandbox verification

- `py_compile session.py area_loader.py` — OK; `session.py` AST OK.
- **All 10 originally-failing tests now pass.** The 5 formerly-failing files run
  **88 passed** clean.
- **Zero regressions:** comprehensive map/HUD/area/env/bearing/poi/substrate/
  contacts sweep → **164 passed, 10 skipped** (skips are jsdom-gated SPA tests);
  DB-backed session sweep (`session43/44/47` + all `_hud_area_map` callers +
  `poi_feed`) → **159 passed, 1 skipped**. Each result was cross-checked against
  the pristine upload to attribute failures correctly.
- No JS changed (`m3_adapter.js`, `client.html`, `m3_composition_engine.js`
  byte-identical to HEAD).

```
run_all_tests.bat
# targeted:
python -m pytest tests/test_poi_feed.py tests/test_fmap1_area_geometry_loader.py \
  tests/test_fmap2_area_geometry_registry.py tests/test_fmap2_session_hud.py \
  tests/test_fmap6_session_contacts.py tests/test_area_loader_substrate.py -q
```

**To see anomalies live:** stand in/near a wilderness area covered by an
AreaGeometry with an active anomaly (spawn one, or use `anomalies` to find an id)
whose anchor room is in view — a pulsing tier-colored glyph appears on that room
in the SECTOR MAP, alongside any bounty crosshairs.

---

## Note — the 10 failures were the full pre-existing set I flagged earlier

This drop clears every failure called out in the prior handoff. Two were *not*
relayout (the HUD-resilience bug above was a code regression; the slug-count test
needed re-targeting for the now-multi-area registry); the other eight were the
substrate-relayout coordinate/structure drift.

---

## Next candidates

- **Architecture-of-record update** — the v51 substrate migration (all 6 areas
  painted) and new areas (Kuat/Nar Shaddaa/Geonosis/Kamino/Senate) should be
  recorded in `sw_d6_mush_architecture_v50.md`.
- **Mission/objective POI markers** — needs a mappable target-room field on
  missions first.
- Durable `dir`-on-`area_geometry.exits` map follow-up (from the prior handoff).

Say the word.
