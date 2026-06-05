# SW_MUSH — Architecture (v51)
## Star Wars MUSH on Python/aiohttp/aiosqlite — May 30 2026 consolidation
<!-- point-updated 2026-06-04: §1.4-G audit-remediation tail (E1 world-event era-cleanness + E2 dormant-effect wiring); new invariant §4.29; phantom pattern #8; §8.19. Current SCHEMA_VERSION = 40. -->

> **Full consolidation.** v51 supersedes v50 (May 25). It is grounded
> in HEAD as of the May 30 2026 session, and folds in everything that
> landed after v50 was written: the **rest of the SYN wave** (SYN.6 →
> SYN.10, which shipped May 25 but post-dated the v50 doc), the **SPA
> visual port** (Tier-1 #4, drops 4.11 → 4.15 cutover), the **v51 hybrid
> raster substrate map lane** (all six maps painted + four new areas),
> the **map navigation / environment / bearing** substrates, and the
> **dynamic POI feed** (bounty + wilderness anomalies).
>
> The headline change from v50: **the web-client lane is no longer
> "paused behind SYN."** It is now the primary surface that has moved —
> the SPA map renderer is live end-to-end via the substrate lane. What
> remains there is enumerated in §1.5.
>
> A note on the version number: the substrate handoffs
> (`NANO_MAP_PACKAGE.md`, `MAP_NAV_OVERLAY_DROP_20260529.md`) already
> named "architecture v51" as the lane's target doc; this file is that
> doc. If you are reading this and have v50 or earlier in hand: discard
> them. This document is the single architecture-of-record.

---

## §0. Reading guide

- **§1 Current state** — what SW_MUSH is, what's in HEAD, what's
  shipped since v50, the open work.
- **§2 Architecture by layer** — engine / parser / server / data /
  static / tests breakdown with module counts.
- **§3 Roadmap** — three-lane execution model (now mostly converged),
  what's closed since v50, priority ranking, forward plan.
- **§4 Invariants** — the rules that don't move between
  consolidations. v51 adds one new one (§4.28, the substrate render
  contract); §4.25–§4.27 carry over from v50.
- **§5 Process disciplines** — how we work (drop discipline,
  phantom catalog, memory hygiene, tracker-update discipline, etc.).
- **§6 Audit and verification** — the audit anchor, the phantom-pattern
  catalog, HEAD verification matrix.
- **§7 Design doc map** — which design doc owns which surface.
- **§8 Outstanding decisions** — open questions Brian or the
  engineer needs to resolve.
- **§9 Version history** — what each prior consolidation closed.
- **§10 Closing notes** — what v51 retires, what's newly tracked,
  the lesson of this wave.

**What v51 closes vs v50:**

1. **The SYN tail (SYN.6 → SYN.10)** — these shipped 2026-05-25 but
   post-dated the v50 doc, so v50 listed them as open. They're done:
   active harvest + region quality, wilderness anomalies Tier 1/2/3,
   building construction, and display integration. The Contestable
   Wilderness pivot is now end-to-end (SYN.0 → SYN.10).
2. **The web-client SPA visual port (Tier-1 #4, drops 4.11 → 4.15
   cutover)** — the JSX prototype map UI ported into a vanilla-JS SPA
   module suite (`static/spa/m3_*.js`) and wired live through a single
   tier registry. v50 had this lane "paused."
3. **The v51 hybrid raster substrate map lane** — all six CW maps
   migrated to painted substrates (+ four new areas), with cardinal
   fixes, the Mos Eisley relayout, and the `L_SubstrateRooms` tactical
   overlay. New invariant §4.28 governs the render contract.
4. **Map A/D/B + environment + bearing + the dynamic POI feed**
   (bounty + wilderness anomalies), plus a HUD-resilience fix and the
   RELAYOUT test rebase (2026-05-30).
5. **A ledger backfill** — the CHANGELOG/TODO trackers had lapsed
   2026-05-25 → 2026-05-30; reconstructed entries (marked) now cover the
   gap, and the `tracker_update_in_same_drop` discipline resumes.

**What v51 does NOT change:**

- The engine/parser/server layer model.
- `SCHEMA_VERSION` (still 35) — the entire wave is render-/read-path
  only, so it applies with no migration.
- The web-client vision/protocol doc (`web_client_vision_and_protocol_v1_3.md`)
  is still authoritative for that lane's remaining phases.
- Invariants §4.1–§4.27 (carried forward).

---

## §1. Current state

### §1.1 What SW_MUSH is

A Star Wars MUSH built solo by Brian (GitHub: BTGlass80) in
Python 3.14, using aiohttp + aiosqlite + asyncio with a vanilla-JS
web client. Active era is **Clone Wars** (~20 BBY); GCW is
deprecated reference content. WEG D6 R&E ruleset, fidelity is a
hard constraint. Target audience: small RP-leaning playerbase.
Local Mistral 7B for NPC dialogue (RTX 3070, 8GB VRAM); Claude
Haiku for the Director AI when enabled.

Windows desktop is the ground-truth dev box (`run_all_tests.bat`);
MacBook Air M4 is the secondary. The chat sandbox is Linux/Python
3.12 — it runs targeted regression sweeps against HEAD; the full
suite executes on Windows on apply.

### §1.2 What this document is

The architecture-of-record. **v50 is a full consolidation**, not a
delta. It folds the v48 HEAD audit anchor forward (the v48 numbers
are still in §1.3 as the "pre-SYN" baseline) and re-derives counts
against the post-SYN HEAD. It folds the v49 web-client lane
framing forward verbatim — that lane is still open, just on
pause behind the SYN sequence.

### §1.3 Code-state baseline (grounded in HEAD, May 30 2026)

| Surface | v50 (post-SYN.5, May 25) | v51 (May 30) | Δ |
|---|---:|---:|---|
| Engine modules (`engine/*.py`) | 114 | **122** | +8 — SYN.6–10 (`harvest`, `wilderness_anomalies`, `buildings`, `territory_display`) which post-dated the v50 doc, plus the map wave (`world_time`, `bearing`) and adjacent helpers |
| Parser modules (`parser/*.py`) | 55 | **60** | +5 — SYN.9 `player_building_commands`, SYN.10 `region_commands`, plus map/bearing-adjacent surfaces |
| Server modules (`server/*.py`) | 16 | **16** | 0 |
| DB modules (`db/*.py`) | 2 | 2 | 0 |
| Schema version | 35 | **35** | 0 — the SPA/map/substrate wave is **schema-neutral** (all client-render + read-path work) |
| Test files (`tests/test_*.py`) | 253 | **236** | net −17 (some consolidation during the SYN.6–10 + map waves; not a coverage loss — see note) |
| SPA test files (`tests/spa/test_*.py`) | — | **37** | the SPA-port test surface (per-tier-body, adapter, composition, registry, substrate, env/bearing, POI) |
| SPA render modules (`static/spa/m3_*.js`) | — | **27** | the visual-port module suite (chrome, tiers, composition engine, adapters, assets, panels) |
| Painted map areas (`data/worlds/clone_wars/maps/*.yaml`) | 2 (Mos Eisley, Senate) | **6** | +4 painted areas (Kuat City, Smuggler's Moon, Stalgasin Hive, Tipoca City); **all six now carry `substrate_image`** |
| Test methods (Windows full-suite, Brian's ground truth) | ~5,150–5,170 expected | **~4,100+ across ~156+ files** (userMemories anchor) | the two anchors have never reconciled — see note |

**On the test-count anchors.** As in v50, the sandbox-collectible
count and the Windows full-suite count do not reconcile (different
anchors; the gap is sandbox-divergence on smoke scenarios that only
register in sandbox). v51 makes no attempt to reconcile them further.
**The audit anchor remains HEAD verified by import-load against the
sandbox.** Windows full-suite totals are Brian's ground truth via
`run_all_tests.bat`. The `tests/test_*.py` file count moving 253→236
is consolidation, not regression — the per-tier SPA suites moved to
`tests/spa/` (37 files) and several legacy fixtures were merged.

**Schema-neutrality is the load-bearing fact of this wave.** Everything
between v50 and v51 (SPA port, substrate migration, map A/D/B,
env/bearing, POI feeds) touched the client render path and HUD read
path only. `SCHEMA_VERSION` is unchanged at 35. No migration is required
to apply this wave.

**Pre-existing baseline failures carried forward** (independent of the
v50→v51 wave; surfaced during this session's regression isolation):

- `test_cw_era_neutral_carryovers_match_gcw` — technician template
  strength drift GCW↔CW, Brian design call (carried since pre-SYN).
- `test_cw_no_test_character` in `test_f1d_era_switch.py` — **DIAGNOSED
  2026-05-30 (root cause found; fix is a layout call — see new tech-debt
  `TD.CW_BUILD_EXIT_COLLISION`).** The test builds a *fresh* CW DB; it
  doesn't fail on the character count — it **errors in the fixture** because
  the CW world build itself fails validation:
  `Room 40 (outskirts_eastern_gate): direction 'east' is claimed by 2
  exits: ['back from room 41', 'back from room 44']`. This is the **sole**
  blocking error (29 non-blocking warnings remain). Severity: at boot,
  `auto_build_if_needed` swallows the failure into a `log.warning` and
  `backfill_room_slugs` is gated on `report.ok`, so a **fresh CW deploy
  silently comes up with seed rooms only** — no crash, which is why the
  existing dev DB masked it. The fix (resolve the gate↔scavenger-market
  direction so it isn't a second "east") is a **map-layout/cardinal call**:
  the room's coords place 41 due-west of the gate while its description
  says "outside the city wall" (desert-side/east), and the checkpoint (44)
  is also east per its text — so spreading the desert-side rooms across
  east/SE/NE (or re-coording 41) is layout design, Brian's per-map domain
  (cf. the morning's relayout philosophies). Not guessed at here.
- ~~`test_wow3c_dsp_fp_wiring.py::…::test_admin_fp_module_removed`~~ —
  **RESOLVED 2026-05-30.** The orphan `parser/admin_fp_commands.py` was
  deleted (its `@fp` surface had already been folded into `@weight <name>
  fp <delta>` during the WoW.4 consolidation, Weight-of-War scaling
  included; `game_server.py` already had no reference, and a full-tree
  grep found zero other importers). The removal test now passes; all 27
  in the file green.

(The eight RELAYOUT/substrate test failures that existed at the start
of the May 30 session were **rebased to the new geometry** and are no
longer failing — see §1.4.)

### §1.4 What landed since v50 (the SYN tail + the May 26–30 web/map wave)

v50 was written at the close of SYN.5 and framed SYN.6–10 and the
entire web-client lane as still-open. Both are now done. v51 records
two bodies of work: the **remainder of the SYN wave** (which shipped
2026-05-25 but post-dated the v50 doc) and the **May 26–30 web/map
wave** that took the web-client lane from "paused" to "live."

> **Ledger note.** The CHANGELOG/TODO trackers lapsed 2026-05-25 →
> 2026-05-30 and were backfilled on 2026-05-30 (reconstructed entries
> are marked in `CHANGELOG.md`). The reconstruction sourced the two
> map handoffs (`MAP_NAV_OVERLAY_DROP_20260529.md`,
> `NANO_MAP_PACKAGE.md`, `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`) plus
> symbol-level grep of HEAD. Some drop dates are approximate; files and
> tests are HEAD-verified.

**A. The SYN tail (SYN.6 → SYN.10 — shipped 2026-05-25, post-dated v50):**

| Drop | New modules | What it shipped |
|---|---|---|
| **SYN.6** (a/b/c) | `engine/harvest.py` | Active wilderness harvest (skill check + cooldown + 15% non-owner tax); weekly region-quality variance (Monday tick) + Director resource-outlook digest; T5 crafting tier + harvest-node gating + kyber attunement. |
| **SYN.7** (a/a.fix/b) | `engine/wilderness_anomalies.py` (~600 LOC base, now ~143KB w/ T2/T3) | Wilderness anomalies Tier 1 (CW-correct templates, skill resolution) → real NPC combat resolution (6 templates incl. Coruscant) → Tier 2 multi-phase combat. Module-level transient state keyed by `region_slug`; cadence engine; `get_anomalies_for_region` / `resolve_anomaly`. |
| **SYN.8** | (extends `wilderness_anomalies`) | Tier 3 world bosses (Krayt Dragon et al.); multi-phase combat with relocation; participation-scaled loot; during-contest 2× cadence. |
| **SYN.9** | `engine/buildings.py` (~1150 LOC), `parser/player_building_commands.py` | Player-constructed buildings on city-claimed landmarks: 5 categories, 24h construction tick, demolish/evict, effect-lookup helpers, residence storage. |
| **SYN.10** | `engine/territory_display.py` (~890 LOC), `parser/region_commands.py` | Display integration: region look block (auto in wilderness look + `+region`), `+faction contest` / `+faction resource_outlook`, 6 news-format helpers, centralized ANSI palette (the web-UI data contract). |

**B. Web-client lane — SPA visual port (Tier-1 #4, drops 4.11 → 4.15; ~May 26–28, approx):**

The JSX prototype map UI was ported into a self-contained vanilla-JS
SPA module suite (`static/spa/m3_*.js`, 27 modules) and wired live:

- **4.11** `m3_skill_check.js`; **4.12a/b** `m3_sheet.js` patch +
  `m3_assembled_client.js`.
- **4.13** outer-tier triplet: `m3_tier_galaxy_body.js` (474 LOC),
  `m3_tier_system_body.js` (470), `m3_tier_planet_body.js` (623).
- **4.14** inner-tier triplet: `m3_tier_city_body.js` (481),
  `m3_tier_wilderness_body.js` (507), `m3_tier_interior_body.js` (451).
- **4.15 cutover** `m3_tier_registry.js` — the canonical
  `getTierRenderer` lookup; `M3MapNavigator` falls back to it, so all
  six tiers (galaxy/system/planet/city/district/wilderness/interior)
  render through one source of truth.
- **showToast hotfix** — the `Unexpected token 'function'` browser
  syntax error in `static/client.html` cleared.

Per-tier-body test files live in `tests/spa/` with loud-substitution
(absent-palette-key) + era-cleanness + Q1 canonical-name pins.

**C. The v51 hybrid raster substrate map lane (~May 29):**

The entire CW map set migrated to a painted-substrate render model
(see the new §4.28 invariant and §2.5):

- All six `data/worlds/clone_wars/maps/*.yaml` carry `substrate_image`,
  with painted PNGs in `static/maps/`. Under a substrate the client
  skips the procedural district/building/street/furniture layers (baked
  into the painting) and keeps labels/entities/weather/chrome on top.
- **Four new painted areas:** Kuat City, Smuggler's Moon (Nar Shaddaa),
  Stalgasin Hive (Geonosis), Tipoca City (Kamino) — plus their planet
  YAMLs. (Mos Eisley and the Senate pre-existed; the Senate also
  migrated to a substrate.)
- **Cardinal pre-flight:** gameplay compass words made to agree with
  rendered geometry (Coruscant 7 fixes, Nar Shaddaa 5 fixes via
  Philosophy B; **Mos Eisley relaid via Philosophy A** — 48/48 cardinal
  exits, which dropped its `exit_paths` to 0 and street labels, since
  straight ribbons tangle post-relayout and aren't used under a
  substrate). Tools: `check_map_cardinals.py`, `apply_cardinal_fixes.py`,
  `relayout_map.py`.
- **Micro-overlay `L_SubstrateRooms`** (in `m3_composition_engine.js`):
  at close zoom, translucent tactical room cells (precise `data-room-id`
  click targets) over a dimmed painting.

**D. Map A/D/B + environment + bearing + POI feeds (~May 30):**

- **Map A** click-to-walk reachability (slug-join; vertical exits
  clickable). **Map D** zoom-reveal room labels (constant on-screen
  font). **Map B** geometry-true direction words + forward/reverse
  cardinal gate.
- **Environment substrate** (`engine/world_time.py`): time-of-day day
  cycle + override, weather; server emit, client read. **Bearing
  substrate** (`engine/bearing.py`): facing from last planar move;
  `attributes.bearing`; self-chevron rotate.
- **Dynamic POI feed** on the map's `L_Entities` layer. **Area-state**
  kinds (everything in view, for everyone): **bounty** targets (v1), then
  **wilderness anomalies** (`anomaly_t1/t2/t3`, incl. the Tier-3 world
  boss) 2026-05-30, then placed **vendor** droids (player shopfronts,
  `type='vendor_droid'`) 2026-05-30. **Personal** kind (this player's
  own): the accepted-mission **objective** (`destination_room_id` →
  green star) 2026-05-30. `_RoomLookupEntry` carries a free `region_slug`
  (captured off the row `resolve_area_room_ids` already fetches; zero
  extra DB) so the anomaly sweep groups by region with no DB storm; the
  vendor sweep is a single batched `room_id IN (…)` query (the same
  no-storm pattern the contacts NPC sweep uses). Renderer + adapter merge
  for all kinds pre-existed; only the server enumeration was added each
  time. Mission-**giver** pins remain unwired (a giver is a name, not a
  room).

**E. This session (2026-05-30) — anomaly POI + HUD fix + RELAYOUT rebase + tracker backfill:**

- The anomaly POI feed (D, above).
- **HUD resilience fix:** the env-substrate drop had hoisted
  `row = await db.get_room()` out of the F.MAP.2 try in
  `_hud_area_map`, so a `get_room` failure crashed the whole HUD push;
  now guarded → degrades to the legacy `area_map`. Caught by an existing
  failure-tolerance test (the test was right; the code was fixed).
- **RELAYOUT test rebase:** the eight tests pinned to the old procedural
  Mos Eisley geometry rebased to the substrate-relayout values (bounds,
  exit_paths→0, labels→2, slug-count re-targeted to Mos Eisley's own
  rooms now that the registry is multi-area, room coords, senate
  substrate). Verified zero regressions (164 map/HUD + 159 session tests
  green; each cross-checked vs pristine HEAD).
- **Tracker backfill** (the ledger note above).

The userMemories anchor of **~4,100+ tests across ~156+ files** remains
the Windows ground truth; v51 does not re-anchor — that's
`run_all_tests.bat`'s job on apply.

**F. This session (2026-05-30, later) — POI feed completed: objective + vendor:**

Two more runtime POI kinds wired onto `L_Entities`, each in the proven
"renderer was already there, only the server enumeration was missing"
shape (zero JS, schema-neutral, verified byte-identical client):

- **Objective POI** (`server/session.py::_build_area_pois`) — a *personal*
  sweep: reads `self.character`, finds that character's `ACCEPTED`
  missions, and places a green-star `{kind:"objective"}` on each
  `destination_room_id` in view. Pre-flight grep-HEAD overturned the
  prior premise (recorded in this very §1.5 / §10.6) that "missions carry
  a destination name, not a room id" — `Mission.destination_room_id` had
  existed and been populated all along; only the map enumeration was
  missing (Pattern 3, inverted-narrative, caught in pre-flight). Enabling
  co-fix: `engine/missions.py::MissionBoard.refresh` now *lazily* fetches
  the room list when filling the board (gated on `needed > 0`, so idle
  ticks pay no DB cost), so tick-spawned missions also carry a
  destination. +13 tests.
- **Vendor POI** (same method) — an *area-state* sweep joining
  bounty/anomaly: one batched `SELECT room_id FROM objects WHERE
  type='vendor_droid' AND room_id IN (…)` (the contacts-NPC no-storm
  pattern), `{kind:"vendor"}` on each placed shopfront in view. Unplaced
  droids (`room_id` NULL) are excluded by the filter. +7 tests.

With these, the dynamic POI feed renders **all four** runtime kinds it was
built to carry (bounty, anomaly, vendor, objective). Only mission-**giver**
pins remain, and those need a giver→room field that doesn't exist yet.

**G. Audit-remediation tail (2026-06-04) — economy hardening + the world-event narrative layer.**

Since the May 30 consolidation, the audit-remediation lane
(`SW_MUSH_Economy_Audit_FINAL.md`,
`sw_mush_remediation_and_fun_additions_design_v1.md`) continued: the
ledger-chokepoint / death-reconciliation / finances-throttle drops
(0a, 1b, 1c, 2), NPC-vendor buyback price-supports for crafting, the
sabacc-den "criminal-empire" loop (**schema 39 → 40**), and the
vanity-titles / commissary additions all shipped — see `CHANGELOG.md`
for per-drop detail. The two drops recorded here in full are the
**world-event / Director / room-state narrative-layer pass** (E1 + E2),
which closed a live B3 era leak and brought the dormant world-event
mechanics online:

| Drop | Files | What it shipped |
|---|---|---|
| **E1** — B3 era-cleanness + milestone repair | `engine/world_events.py`, `engine/room_states.py`, `engine/director.py`, `data/worlds/gcw/director_config.yaml` | The Director / event / room-state narrative layer was never era-swept and broadcast GCW content ("Imperial/Stormtrooper/Rebel/The Empire") in the live `clone_wars` era, while the era-milestone feature was silently **inert** — `ERA_MILESTONES` was keyed on GCW factions (`imperial`/`rebel`/`criminal`) that `_compute_faction_averages()` no longer produces, so the six above-threshold milestones could never fire and the one below-threshold milestone fired spuriously. Clean **enum rename** `IMPERIAL_CRACKDOWN`/`IMPERIAL_CHECKPOINT`/`REBEL_PROPAGANDA` → `SECURITY_CRACKDOWN`/`SECURITY_CHECKPOINT`/`SEPARATIST_AGITATION` (mechanical effects preserved); `ERA_MILESTONES` replaced with 7 CW milestones keyed `republic`/`cis`/`hutt_cartel` (every key verified ∈ `VALID_FACTIONS`); event vocab / event→state map / overlay special-case moved to CW values; room-state overlays re-skinned CW-clean. +11 DB-free tests. **Deferred:** the Director's *internal* faction model (`ZoneState` GCW fields, `compile_digest` LLM payload, `VALID_FACTION_CODES`) → `TD.DIRECTOR_FACTION_MODEL_GCW` (LLM-context only, no player-string leak). |
| **E2** — dormant world-event effects (passive) + phantom repair | `engine/world_events.py`, `engine/skill_checks.py`, `engine/npc_space_traffic.py`, `engine/director.py`, `parser/bounty_commands.py` | Wired the **passive** dormant effects to their existing faucets (the `get_effect()` pattern, §4.29): `bounty_reward_mult` (bounty payout, before the `bounty` `adjust_credits`), `pirate_spawn_mult` + `patrol_spawn_mult` (`_pick_archetype` spawn weighting), `perception_penalty` (`perform_skill_check`, guarded to the observation family `{perception, search}`, no-op default). **Phantom repaired:** `patrol_spawn_mult` had **never** been consumed — it lived in a `_pick_archetype` definition shadowed by a later same-named one (`_pick_archetype(exclude_hunter=True)`, the one `_spawn` calls); the dead duplicate was deleted and both multipliers consolidated into the live def (proved by consumption tests — patrol share 0.158→0.298, pirate 0.173→0.378). Director vocab += `intelligence_thaw`/`spice_demand`; live "Jabba" Q1 strings → institutional Hutt references. +9 tests. **Deferred:** the 6 **flag** effects (each enables a *new* player interaction) → design pass `T2.E3` (§8.19). |

### §1.5 What's still open

The SYN wave (SYN.0 → SYN.10) and the web-client SPA visual port are
**done** as of v51 — both were the headline open items in v50. What
remains:

**Web client — remaining lane work:**

- **Mission-giver POI pins** — the dynamic POI feed now renders all four
  *room-anchored* runtime kinds (bounty, anomaly, vendor, objective; the
  objective + vendor halves shipped 2026-05-30 — see §1.4-F). The only
  remaining `kind` the renderer knows but the server doesn't emit is the
  mission-**giver** pin (`MK_Mission`): a giver is a *name*, not a room
  id, so there's nothing to map. Wire if/when a mission gains a
  giver-room field — renderer + adapter pass-through are already in
  place, so it'd be another server-enumeration-only drop.
- **Phase-1 protocol substrate tail** — furniture is suppressed by
  design under a substrate (every authored area is painted, so the
  procedural `L_Furniture` path renders nowhere); time/weather/bearing
  shipped. Any remaining server-side substrate emissions (e.g. richer
  per-room furniture for the few non-painted dev areas) are optional.
- **Browser smoke-tests (Brian, Windows):** the substrate micro-overlay
  (`L_SubstrateRooms`) and the new tier renderers can't render in
  sandbox — the per-tier-body + composition tests pin structure, but the
  visual landing (cells on painted features, dim level, click-to-walk
  traversal) needs a browser pass.
- **Phases 2/4/5** (rich panels bulk, diegetic polish, mobile) — mostly
  post-launch per `web_client_vision_and_protocol_v1_3.md`.

**Docs / record:**

- **Architecture-of-record housekeeping** — this v51 doc closes the
  `TD.ARCH_V51` tech-debt item (the substrate lane was undocumented).
  `TODO.json` `architecture_of_record` and the CHANGELOG header now point
  to v51.

**World events / Director (from E1–E2, 2026-06-04):**

- **The 6 world-event FLAG effects** (`contraband_scan`, `rare_vendor`,
  `hutt_auction`/`criminal_rep_gate`, `krayt_bounty`, `brawl_active`,
  `distress_active`) — each *enables a new player interaction* and needs
  a design decision before code; sequenced through design pass `T2.E3`
  (§8.19). E2 wired only the passive multipliers/pip-deltas.
- **Director internal faction model re-key** (`TD.DIRECTOR_FACTION_MODEL_GCW`)
  — E1 cleaned the player-facing narrative layer + repaired the milestone
  feature, but `ZoneState`'s `imperial/rebel/criminal/independent` fields,
  the `compile_digest` LLM payload, and `VALID_FACTION_CODES`
  (`empire`/`rebel`/`hutt`/`bh_guild`, which gate the LLM's faction-orders)
  are still GCW-keyed. LLM-context/internal only (no player-string leak);
  needs a GCW→CW faction-mapping decision. The emergency-fallback baselines
  must stay GCW-byte-equivalent (pinned by `test_f6a3_int_byte_equivalence`).

**Engine — Tier 2 launch-flexible (carried forward, unchanged):**

- **Weight of War mechanic** — MVP_COMPLETE; full implementation pending.
- **PG.2.bounty post-launch follow-ups** — BH-tier vendor
  `check_debt_gate` integration (no consumer yet).
- **PG.3 Act 3 trial implementation** — Act 3 formal Knighting trial
  named but not landed.
- **Padawan-Master expansion** — council politics, formal lineage trees,
  Padawan re-assignment are post-launch.
- **F.7.n** — seed Force attributes so `force_sensitive` survives reload
  (post-launch).

**Design calls (Brian, carried forward unchanged):**

- *Eavesdrop `target_char` model* — open since v45 (documented seam).
- *`skill_check_passed` trigger-site decision* — resolved (explicit
  `chain attempt` command, per v50 §1.4 / TODO T1.2 DONE).
- *SRB.1 §3.6 "failed overdose auto-incapacitates"* — block-and-warn
  shipped; auto-incap post-launch if behavior demands it.
- *SRB.2 Force-fall-check aura integration* — post-launch.
- *Security Model v1 Coruscant naming reconciliation* — live YAML is
  tier-based, catalog wants function-based.

**Content — launch-flexible:**

- **Coruscant Underworld wilderness build (scope locked 2026-05-30)** —
  landmarks YAML shipped; **decision (§8.13): author the full 40×40×3
  region file** on the wilderness substrate. The main pre-launch content
  task.
- **Intel handler NPC seeding** (SYN.5 follow-up) — spawn handlers
  (`ai_config_json::is_intel_handler: true`) at the 9 faction HQs. Single
  small content drop.

### §1.6 What's been steady for a while

- WEG D6 R&E core mechanics — stable since v40.
- Dual WebSocket/Telnet networking — stable since v35 era.
- The web-first design directive — locked since v40.
- The `replaces:` protocol for era-keyed YAML content — locked.
- The phantom-catalog discipline — patterns 1–7 carried forward
  from v48; v50 does not add a new pattern (the SYN wave caught
  three of the existing patterns in flight, all repaired before
  ship; see §5.9 for the SYN-sequence roll-up discipline that
  emerged from the wave).
- The `_FakeDB`-with-mutation-log test fixture pattern (§4.20) —
  used by every SYN test file.
- Boot ordering, era flag (CW), drop-zip packaging discipline —
  all carried forward from v48/v49.
- The Drop 6D contest block deletion is **closed** in SYN.3 — it
  was a parallel-ship retirement pattern (legacy surface deleted
  in same drop the new surface ships). No phantom risk because the
  deletion is HEAD-physical.

---

## §2. Architecture by layer

(Mostly unchanged from v48/v49. The engine/parser/server/data/test
layer shape is what it was. The SYN wave added five engine surfaces
and two parser surfaces; nothing moved between layers. The §2.x
subsections below note the new surfaces only.)

### §2.1 Persistence — `db/`

Unchanged from v48. Schema **v35** (up from v34): SYN.1.b added the
`territory_claims.wilderness_region_slug` column via migration; SYN.3
added `region_contests` + `region_contest_cooldowns` tables; SYN.4
added `player_cities.vitality_state` + `vitality_below_since` columns
via additive `ALTER TABLE` (idempotent — wrapped in try/except since
SQLite < 3.35 lacks `ADD COLUMN IF NOT EXISTS`).

### §2.2 Game engine — `engine/`

**114 modules.** New since v48:

- **`engine/contest.py`** (NEW SYN.3, ~1,700 LOC) — region contest
  state machine. Schema (`region_contests`, `region_contest_
  cooldowns`), 7-day timer, accumulation/culminating-fight phase
  split (`_CULMINATING_SECS = 4h`), Anchor NPC HP-tier scaling
  (`_anchor_hp_tier` → WEG D6 stat dice buckets), 9 faction Anchor
  templates + `_default`. `compute_anchor_hp`, `compute_anchor_
  reinforcements`, `compute_outnumbered_defender_multiplier`,
  `apply_contest_influence_multipliers` (2× both sides + 1.5×
  outnumbered defender on top). Two-phase tick (Phase A: spawn
  Anchor at `accumulation_ends_at`; Phase B: defender-win-by-default
  at `ends_at`). `on_npc_killed_in_combat` kill-detection hook.
  `_resolve_challenger_win` ownership transfer with
  `claimed_by=-contest_id` sentinel.
- **`engine/intel_handlers.py`** (NEW SYN.5, ~520 LOC) — espionage-
  as-influence redemption. Quality tier constants
  (`INTEL_QUALITY_LOW/MEDIUM/HIGH`), heuristic stub
  `evaluate_intel_quality` (T3.15 will replace with real LLM call),
  `sample_intel_reward`, `_is_handler_npc` + `find_handler_in_room`
  (ai_config_json marker `is_intel_handler` + faction match),
  `handover_intel` 5-step validation entry point.
- **`engine/wilderness_encounters.py`** (carried from T2.WENC partial,
  pre-SYN — counted here for first time in v50; v48 undercounted).
- **`engine/wilderness_loader.py`** + **`engine/wilderness_writer.py`**
  (pre-SYN, undercounted in v48).

Substantially expanded since v48:

- **`engine/territory.py`** — gained: `region_ownership` +
  `region_garrison` schemas; `claim_region` / `unclaim_region` /
  `get_region_owner` / `get_org_regions` / `is_region_owned_by` /
  `_get_region_landmarks` / `_get_region_zone` / `spawn_region_
  garrison` / `dismiss_region_garrison` / `tick_region_maintenance`
  / `tick_region_passive_yield` (SYN.1.a). `adjust_territory_
  influence` gained `region_slug=` kwarg routing through SYN.3
  contest multipliers. Drop 6D's 442-line city-map zone-keyed
  contest block **physically deleted** in SYN.3 and replaced with
  a 24-line retirement header pointing at `engine/contest.py`.
  `on_npc_kill` / `on_mission_complete` / `on_pvp_kill` retargeted
  in SYN.5 to gate on `wilderness_region_id` and pass `region_slug=`
  down. New `_resolve_room_region` helper.
- **`engine/security.py`** — gained the wilderness-aware step-4
  branch (SYN.2): rooms with `wilderness_region_id` resolve declared
  security from the region; rooms without one keep the legacy
  zone-keyed path. `_apply_claim_upgrade` retired in SYN.1.b.
- **`engine/player_cities.py`** — gained the +720 LOC SYN.4 section:
  `found_city_in_region` + `claim_landmark_for_city` (parallel-ship
  alongside legacy `found_city` + `claim_room_for_city`),
  `count_active_citizens` + `compute_vitality_threshold` +
  `compute_vitality_state` + `tick_city_vitality` +
  `effective_tax_rate_cap` (vitality state machine),
  `syn4_migrate_dissolve_city_map_cities` (one-shot migration with
  75% refund, idempotent via `syn_migration_state` row).

### §2.3 Parser — `parser/`

**55 modules.** Substantially modified surfaces since v48:

- **`parser/city_commands.py`** — `_handle_found` accepts new
  `+city found <name> in <region_slug>` form (SYN.4); `_handle_claim`
  routes to `claim_landmark_for_city` when the active org's city is
  region-anchored (`wilderness_region_id` set), else falls through
  to legacy.
- **`parser/espionage_commands.py`** — `IntelCommand` gains
  `+intel handover [<id>]` subcommand (SYN.5).
- **`parser/combat_commands.py`** — PvP gate retargeted; NPC death
  hook added per SYN.3.
- **`parser/faction_commands.py`** — `_cmd_seize` deleted (SYN.3
  retired the per-room seize surface; replaced by region-keyed
  challenge flow in `engine/contest.py`, parser command for it not
  yet wired — see §1.5 follow-ups).

### §2.4 Server — `server/`

**16 modules** (unchanged). Modified:

- `server/tick_handlers_economy.py` — gained `city_vitality_tick`
  wrapper (SYN.4).
- `server/game_server.py` — registers `city_vitality` tick at
  `interval=3600, offset=1900` (SYN.4); registers
  `region_maintenance` + `region_passive_yield` (SYN.1.a) and
  `region_contest_tick` (SYN.3).
- `server/session.py` — HUD payload gained contest-status field
  (SYN.3 retarget).

### §2.5 Static client — `static/`

**Substantially advanced since v50.** The web-client lane moved from
paused to live. `static/client.html` remains the served entry point and
HUD host, but the map UI is now a self-contained vanilla-JS SPA module
suite under `static/spa/` (`m3_*.js`, 27 modules):

- **Chrome / orchestration:** `m3_map_navigator.js`,
  `m3_assembled_client.js`, `m3_tier_registry.js`.
- **Tier-body builders** (one per zoom tier):
  `m3_tier_{galaxy,system,planet,city,wilderness,interior}_body.js`.
  The composition engine's `Tier1aBody` covers the district tier.
  `m3_tier_registry.js::getTierRenderer` is the **single source of
  truth** for tier → builder; `M3MapNavigator` falls back to it.
- **Render core / assets:** `m3_composition_engine.js` (the SVG layer
  stack — substrate, districts/buildings, streets, furniture, labels,
  entities, weather, chrome), `m3_adapter.js` (server-geometry → render
  shape), and the `m3_assets_*` / `m3_palettes` / `m3_tokens` modules.
- **Panels:** `m3_sheet.js`, `m3_skill_check.js`, `m3_holocron.js`,
  `m3_holonet.js`, `m3_cockpit.js`, `m3_combat_theater.js`,
  `m3_combat_inspector.js`.

**Hybrid raster substrate lane (new in v51).** When an area declares
`substrate_image`, the renderer paints that PNG at the world bounds
beneath the SVG overlay and **suppresses the procedural
district/building/street/furniture layers** (they're baked into the
painting), keeping labels/entities/weather/chrome on top. At close zoom,
`L_SubstrateRooms` paints translucent tactical room cells (precise
`data-room-id` click targets) over a dimmed painting. See the §4.28
invariant for the render contract.

### §2.6 World data — `data/worlds/`

Structurally expanded since v50. The CW map set now has **six painted
areas** (`data/worlds/clone_wars/maps/*.yaml`), every one carrying a
`substrate_image` pointing at a painted PNG in `static/maps/`: Mos
Eisley, Coruscant Senate, plus the four added in v51 — Kuat City,
Smuggler's Moon (Nar Shaddaa), Stalgasin Hive (Geonosis), Tipoca City
(Kamino) — with matching planet YAMLs. Mos Eisley's map was relaid for
cardinal correctness (its `exit_paths` dropped; streets are in the
painting). Two CW zones carry `resource_signature` blocks from SYN.1.a;
the Drop 6D territory_claims data is wiped via the idempotent SYN.1.b
migration on apply.

### §2.7 Tests — `tests/`

**253 test files** (up from 201 in v48). The SYN wave added 7 new
test files (one per drop) totaling **299 tests**:

- `test_syn1a_region_ownership.py` (43)
- `test_syn2_wilderness_aware_security.py` (24)
- `test_syn3a_region_contest_state_machine.py` (65)
- `test_syn3b_anchor_kill_and_multipliers.py` (53)
- `test_syn4a_city_region_anchor.py` (30)
- `test_syn4b_vitality_and_migration.py` (37)
- `test_syn5_espionage_as_influence.py` (47)

The legacy 520 cities tests are **unchanged** by the SYN wave —
this is the parallel-ship pattern's payoff. Retargeting them to
wilderness fixtures is its own ~2-session refactor that will land
after the SYN.4 migration runs in production and confirms no
orphan legacy cities remain.

### §2.8 Skills directory — `data/skills/` (CP / WEG)

Unchanged from v48.

---

## §3. Roadmap

### §3.1 Three-lane execution model (lanes mostly converged at v51)

Three lanes:

- **Engine lane** — **closed for launch.** The SYN sequence
  (SYN.0 → SYN.10) is fully shipped. Engine is in the post-launch
  follow-up state: PG.2.bounty post-launch, SRB.1/SRB.2 post-launch,
  PG.3 Act 3, F.7.n Force-attribute seeding. Brian-design calls carried
  over (eavesdrop open; `skill_check_passed` resolved).
- **Content lane** — Coruscant Underworld is the main pre-launch content
  item, **scope locked 2026-05-30 to the full 40×40×3 region file** (§8.13).
  Intel-handler
  NPC seeding is a small SYN.5 follow-up content drop.
- **Web client lane** — **substantially shipped.** The SPA visual port
  (4.11→4.15 cutover) is live, the map set renders on the hybrid raster
  substrate lane (§4.28), and map navigation / environment / bearing /
  POI feeds are in. What remains is a browser smoke-test of the
  substrate overlay, mission/objective POI markers, and the
  mostly-post-launch Phases 2/4/5.

### §3.2 Priority ranking (UPDATED v51)

**Tier 1 — Top priority (active focus)**

| # | Item | Lane | Effort | Why |
|---|---|---|---|---|
| **1** | Browser smoke-test the substrate map lane | web-client | Small (~0.5 sess, Brian/Windows) | The substrate micro-overlay + new tier renderers can't render in sandbox; verify cells land on painted features, dim level, click-to-walk traversal. The only launch-gating verification left on the map lane. |
| **2** | Eavesdrop `target_char` design call | design | Small (~0.5 sess) | Open since v45. Brian-design call (documented seam). |
| **3** | Mission-**giver** POI pins | web-client | Small (~0.5 sess) | *Blocked, not ready.* The room-anchored POI feed is complete (bounty + anomaly + vendor + objective shipped 2026-05-30, §1.4-F). The giver pin needs a giver→room field that doesn't exist yet; renderer + adapter are ready for when it does. |

**Tier 2 — Important, queued**

| # | Item | Lane | Effort | Why deferred |
|---|---|---|---|---|
| **4** | **Coruscant Underworld wilderness build** | content | Medium (~1–2 sess) | **Scope locked 2026-05-30 (§8.13): author the full 40×40×3 region file** on the wilderness substrate, consistent with the landmarks YAML. The main pre-launch content task. |
| **5** | Intel handler NPC seeding (SYN.5 follow-up) | content | Small (~0.5 sess) | Spawn `is_intel_handler` NPCs at the 9 faction HQs. |
| **6** | Security Model v1 content reconciliation | data + design | Small (~0.5 sess + call) | Blocked on Coruscant naming-scheme design call. |
| **7** | PG.2.bounty post-launch follow-ups | engine | Small per-drop | BH-tier vendor `check_debt_gate` integration. |
| **8** | SRB.1 / SRB.2 follow-ups | engine + data | Small per-drop | Auto-incap call; Force-fall-check aura integration. |
| **9** | PG.3 Act 3 trial implementation | engine | Small (~1 sess) | Manual fallback (`+knight` via Padawan-Master) exists. |
| **10** | F.7.n Force-attribute seeding | engine | Small | So `force_sensitive` survives reload. |

**Tier 3 — Polish / post-launch**

| # | Item | Why deferred |
|---|---|---|
| **11** | Padawan-Master post-launch expansion (council, lineage trees, re-assignment) | Design names these as post-launch. |
| **12** | Cities post-launch expansion (multi-city-per-org, P2P discovery) + legacy `found_city`/`claim_room_for_city` removal + 520 legacy tests retargeted to wilderness fixtures | After the SYN.4 migration runs in production. ~2 sess. |
| **13** | Director AI Clone-Wars tuning (T3.15) | Will replace SYN.5 intel-quality heuristic stub with a real LLM call. |
| **14** | Space Wildspace expansion | `space_wildspace_design_v1.md` exists. Post-launch. |
| **15** | Web client Phase 2 (rich panels bulk), Phase 4 (diegetic polish), Phase 5 (mobile) | Vision phases per `web_client_vision_and_protocol_v1_3.md`. |

### §3.3 Closed since v50

Two bodies of work (detailed in §1.4):

**The SYN tail (SYN.6 → SYN.10)** — shipped 2026-05-25 but post-dated
the v50 doc:

- **SYN.6** — Active harvest + region resource quality (`engine/harvest.py`).
- **SYN.7** — Wilderness anomalies Tier 1–2 (`engine/wilderness_anomalies.py`).
- **SYN.8** — Wilderness anomalies Tier 3 / world bosses.
- **SYN.9** — Building construction (`engine/buildings.py`, `parser/player_building_commands.py`).
- **SYN.10** — Display integration + launch polish (`engine/territory_display.py`, `parser/region_commands.py`).

**The May 26–30 web/map wave:**

- SPA visual port (Tier-1 #4, drops 4.11 → 4.15 cutover) + showToast fix.
- v51 hybrid raster substrate migration (six maps painted + four new
  areas) + cardinal fixes + Mos Eisley relayout + `L_SubstrateRooms`.
- Map A/D/B + environment + bearing + dynamic POI feed (bounty +
  anomalies).
- HUD resilience fix + RELAYOUT test rebase + CHANGELOG/TODO backfill
  (2026-05-30).

The Contestable Wilderness pivot is now end-to-end; the web-client lane
went from paused to live.

**Audit-remediation tail (2026-06-04, point-update — detailed in §1.4-G):**
ledger chokepoint / death reconciliation / finances throttle (drops 0a,
1b, 1c, 2), NPC-vendor buyback craft price-supports, sabacc dens (schema
39 → 40), vanity titles + commissary, and the world-event narrative-layer
pass — **E1** (B3 era-cleanness + CW milestone repair) and **E2** (dormant
*passive* world-event effects wired + `patrol_spawn_mult` phantom repaired).

### §3.4 Why this ranking

**The engine lane is closed.** The SYN sequence shipped end-to-end; what
remains there is post-launch follow-ups and one open design call.

**The web-client lane has moved from goal to delivered.** v50 ranked it
behind the SYN sequence ("UI which will be the goal as soon as we finish
this SYN pivot"). That goal is now largely met: the SPA port shipped, the
substrate map lane is live, and navigation/environment/bearing/POI feeds
are in. The top web-client item left is a **browser smoke-test** of the
substrate overlay — the one thing the sandbox can't verify — plus the
small mission/objective POI follow-up.

**The remaining design call** (#2, eavesdrop `target_char`) is a small
implementation gated on a Brian decision; the `skill_check_passed` call
that was open v45→v50 is now resolved (explicit `chain attempt`).

**Coruscant Underworld** is the main pre-launch content item —
**scope locked 2026-05-30 (§8.13) to the full 40×40×3 region file**. The
parallel-ship
discipline (§4.27) means it can land independently whenever Brian wants.

### §3.5 Web client lane reference (UNCHANGED from v49)

The authoritative reference for the web-client lane is now
**`web_client_vision_and_protocol_v1_3.md`** (a delta read together with
v1.2). The SPA visual port and the hybrid raster substrate map lane have
since shipped against it; the remaining phases (2/4/5) are mostly
post-launch.

That document subsumes:
- `CLAUDE_DESIGN_BRIEF.md` (folded into vision §7)
- `MAP_REDESIGN_HANDOFF.md` (superseded by vision §7.13)
- `web_client_ux_overhaul_v1.md` (folded into vision §6)
- `ground_ux_overhaul_design_v1.md` (folded into vision §6 / §10.4)
- `web_ux_competitive_analysis.md` (folded into vision §5)

`Map_Redesign_v2.html` remains a valid reference asset (the
per-style room footprint mockup, the fallback layer in the asset
library per vision §7.13.1).

### §3.6 What ships at launch (current reading)

**Launch scope (updated for the SYN sequence):**

- WEG D6 R&E core + chargen.
- Combat (ground + space).
- Economy + trade + crafting + Sabacc + Entertainer aura + lead.
- **Wilderness movement, all wilderness regions including
  Coruscant Underworld once content lands.**
- Tutorial chains (F.8 + F.8.c).
- All security zones + faction-override SECMOD.1, **plus the
  wilderness-aware security branch from SYN.2**.
- All progression gates (PG.1 death, PG.2 bounty, PG.3 Force).
- Padawan-Master (Masters take Padawans, Padawans linked, Masters
  approve Trials, `+teach`/`+learn`/`+spar`).
- Player Cities v1.2 (full) **+ region-anchored cities from SYN.4
  + vitality state machine + 75%-refund migration of legacy cities**.
- Mail, channels, news, places, plots, scenes, espionage, spacer
  quest.
- **Contestable Wilderness end-to-end (SYN.0 → SYN.10): region
  ownership + region contests with Anchor NPCs + region-anchored
  cities + espionage-as-influence + active harvest + wilderness
  anomalies Tier 1/2/3 + building construction + display
  integration.**
- Director AI (Clone Wars era, with intel-quality stub awaiting
  T3.15).
- Web client UX (chargen, modal panels, city panels, HUD) — the
  **SPA port + hybrid-substrate map renderer are live** in
  `static/client.html` via the SPA module suite; remaining web work
  (mission/objective POIs + the Phase 2 panels not pulled into launch) is
  mostly post-launch; a selected Phase 2 subset is now **in** launch (§8.16).

**Post-launch (intentionally deferred):**

- Cities multi-city-per-org, P2P city discovery.
- Padawan-Master council politics, formal lineage trees.
- Space Wildspace expansion.
- Director AI CW prompt tuning (T3.15 — will replace SYN.5
  intel-quality heuristic stub).
- Web client Phase 4 (diegetic polish) and Phase 5 (mobile).
- PG.3 Act 3 formal Knighting trial (Padawan-Master `+knight` is
  the manual fallback).
- Legacy cities tests retargeted to wilderness fixtures + legacy
  founding surfaces removed.

### §3.7 Forward session plan (UPDATED v51)

**Next session:** Brian's call — the launch-gating item is the
**browser smoke-test of the substrate map lane** (Windows; the only
verification the sandbox can't do). Good parallel candidates:
mission/objective POI markers (small), or the Coruscant Underworld
content build.

**Subsequent sessions** (in order, unless Brian re-prioritizes):

1. Browser smoke-test the substrate overlay + new tier renderers; fix
   anything the sandbox couldn't catch (cell placement, dim level,
   click-to-walk traversal).
2. Coruscant Underworld build — author the full 40×40×3 region file
   (scope locked, §8.13).
3. Intel handler NPC seeding (small content + light-seeding drop; resolves
   the live `hq_room_id` per §10.6, since HQ rooms are dynamically created,
   not statically seeded).
4. Eavesdrop `target_char` design call (Tier 1 #2).
5. Launch.

*(Done 2026-05-30: the room-anchored POI feed — bounty + anomaly + vendor +
objective, §1.4-F. Mission-**giver** pins remain, blocked on a giver-room
field, §1.5.)*

**Post-launch:** Web client Phases 2/4/5; cities multi-city + legacy
surface removal + 520 legacy tests retargeted; Padawan-Master council
politics; Space Wildspace; Director AI CW tuning (T3.15); PG.3 Act 3;
F.7.n.

**On the v50 forward plan:** v50 listed SYN.6 as the next session and the
web-client lane as re-opening after SYN.10. Both happened — the SYN tail
and the web/map wave shipped between v50 and v51. The web-client lane is
no longer the parked goal; it's mostly delivered.

---

## §4. Architecture invariants

(All v48/v49/v50 invariants §4.1–§4.27 carry forward unchanged unless
noted. One new invariant added at §4.28 — the hybrid raster substrate
render contract. The §4.13 cities invariants are supplemented by §4.26
region-anchored cities; both are operative.)

### §4.1 Web-first directive

(unchanged.) Features are designed for the web client first.
Graceful Telnet degradation is a nice-to-have, not a veto.
Features requiring the web client show "requires web client" on
Telnet. Telnet port stays alive for admin debugging and purists.

### §4.2 WEG-fidelity invariant (carried forward from v49 strengthening)

Mechanics follow WEG D6 R&E. Departures are explicit design calls,
documented in the relevant design doc. Strengthened in v49 to UI
surfaces: UI controls must represent state the engine canonically
tracks AND send parser commands that canonically exist. See §4.23
for the enforcement discipline.

### §4.3 Audit discipline (unchanged)

Grep HEAD before marking delivered. Every drop's pre-flight audit
grepped HEAD for the prior drop's claims before writing new code.
The SYN wave validated this discipline across 6 sequential drops.

### §4.4 Boot ordering for era flag (unchanged)

Active era is **Clone Wars** (`server/config.py` and
`engine/era_state.py` flipped to `clone_wars`; `use_yaml_director_
data` True). GCW is deprecated reference content.

### §4.5 Seam vs. integration discipline (unchanged)

Ship the contract first with no consumer; wire later. Fail-loud
on seam failures (not silent fallback). The SYN wave used this
extensively: SYN.1.a shipped the `region_slug=` seam on
`adjust_territory_influence` with no consumer; SYN.5 then wired
the consumer at three call sites.

### §4.6 `replaces:` protocol for era-keyed content (unchanged)

### §4.7 Smoke-test discipline (unchanged)

### §4.8 Test ground-truth split (unchanged)

Brian runs full pytest on the Windows dev box. In-sandbox Claude
runs only targeted checks: AST validation of modified files + tests
for the changed module + regression sweep of adjacent surfaces.
**Do NOT run full suite in sandbox** — timeout exceeds 600s.

### §4.9 Chunked delivery (unchanged)

### §4.10 Single-source-of-truth state transitions (unchanged)

The SYN wave reinforces this: the region-contest state machine in
`engine/contest.py` is the single source of truth for contest
state transitions; the Drop 6D zone-keyed contest block was
deleted in SYN.3 specifically because two truth sources would have
diverged.

### §4.11 Security model invariants (UPDATED v50)

Carried forward from v48 with the SYN.2 wilderness-aware branch
added:

- Rooms with `wilderness_region_id` resolve declared security
  from the region (the region's `properties.security` or the
  region default).
- Rooms without `wilderness_region_id` keep the legacy zone-keyed
  path.
- The "cities cannot be founded in secured zones" rule is
  **retired** in SYN.4 — wilderness regions are CONTESTED by
  default, and the city-founding eligibility rule moved to
  region ownership / Foothold influence (50+) per §4.26.

### §4.12 Support role buffs invariants (unchanged)

### §4.13 Player cities invariants (UPDATED v50)

(Carried forward from v48 with the SYN.4 retarget added; see also
the new §4.26.)

- City state is org-anchored. `get_city_by_org(db, org_id)` is the
  canonical lookup.
- Roles: `founder` / `mayor` / `citizen` / `guest` / `outsider` /
  `banished`. Banished is highest priority.
- Grace state machine for maintenance: 1 week flags-off, 2 tax-off,
  3 final warning, 4 dissolve. `grace_started_at` is the single
  source of truth. `guards_active(city)` False in any grace stage.
- Citizen-only rooms subject to a 33% cap; enforcement in
  `set_room_citizen_only`.
- NPC guards (Phase 7+): slot counts per HQ tier (outpost 3 /
  chapter_house 6 / fortress 14), engagement triggers from
  citizen-only intrusion / banished entry / bountied entry /
  attacked-a-citizen-in-this-combat-session. The ATTEMPT counts,
  not the HIT. Citizen-on-citizen still triggers.
- **NEW v50 (SYN.4):** Cities can be region-anchored
  (`wilderness_region_id` set) or legacy city-map (NULL). The
  vitality state machine applies per-tier active-citizen
  thresholds (outpost 1, chapter house 3, fortress 5); below
  threshold → `reduced` immediately, `dormant` after 14d under
  threshold. Recovery is single-tick. Reduced/dormant halves the
  tax cap (via `effective_tax_rate_cap` — seam in place; consumer
  wiring is a follow-up) and blocks expansion. See §4.26.
- **NEW v50 (SYN.4):** Parallel-ship: legacy `found_city` and
  `claim_room_for_city` remain operational for the 520 cities
  tests. The new region-anchored API (`found_city_in_region`,
  `claim_landmark_for_city`) ships alongside. Parser routes by
  active-org-city's `wilderness_region_id`.
- Web UI (Phase 6 web UI): HUD payload `hud["city"]` is the
  transport. Action buttons send the same text the player would
  type. 6 destructive actions go through 5-second two-stage
  confirm.

### §4.14 Wilderness co-location invariant (unchanged)

### §4.15 Map renderer invariants (carried forward from v49)

The map renderer is a three-layer separation: asset library
(hand-authored SVG illustrations), composition engine (runtime
renderer), game data (geometry + state). One renderer for all
viewports; no parallel implementations. Production code must NOT
bypass the asset library by inlining schematic SVGs in panels.
Rooms may declare a `landmark_slug` field; renderer uses
named-landmark illustration when set, falls back to style
primitive otherwise.

### §4.16 Q1 canonical-character policy (unchanged)

Canonical Star Wars characters = EXTREMELY RESTRICTED.
Absence-framing or original-NPC substitution required. Q1 test
family is the standing quality regime — has caught real slips
multiple times (most recently a Tarkin reference during SYN.4
chain-anchor NPC validation).

### §4.17 +pvp opt-in flag invariants (unchanged)

### §4.18 PG.1.death invariants (unchanged)

### §4.19 PG.2.bounty invariants (unchanged)

### §4.20 Test-fixture patterns (unchanged)

The `_MiniDB` + `_FakeDB` patterns continue to be the default for
SYN-wave tests. SYN.4 test fixtures specifically needed to validate
against `Database._CHARACTER_WRITABLE_COLUMNS` allowlist behavior.

### §4.21 Cities web-UI safety pattern (unchanged)

The two-stage confirm pattern is still the canonical destructive-
action UI safety pattern. Future destructive surfaces (housing
dissolve, ship scrap) should reuse `_cityMakeDangerBtn`.

### §4.22 Combat-trigger state (unchanged)

`CombatInstance.attacks_made` is the in-memory record of every
attempted attack. Consumers include
`evaluate_combat_round_triggers` and (SYN.3) `on_npc_killed_in_combat`
for region-contest kill detection. The ATTEMPT counts, not the HIT.

### §4.23 Engine-canonical command discipline (carried forward from v49)

Before merging UI code that sends a parser command, the engineer
must verify the command exists. Before displaying a value, the
engineer must verify the engine field exists. Canonical command
list lives in `web_client_vision_and_protocol_v1_3.md` (+ v1.2 §3.15).
Things that are NOT canonical: `stance`, "Mode <combat|exploration|
social>", hit-point bars/percentage health, mana/energy pools,
armor durability.

### §4.24 Web wire protocol discipline (carried forward from v49)

Every server→client message carries a `schema_version` field.
Server supports last N versions (start with N=2). Client states
preferred version on connect. Schema-discovery endpoint at
`GET /api/protocol/schema`. The §5.10 maintenance rule from the
vision doc applies.

### §4.25 Wilderness-only influence invariant (NEW v50)

**Per design v2 §2.7, the two-tier reward rule for faction
power projection is:**

- **City-map activity (rooms with `wilderness_region_id` NULL):**
  rep + credits + CP only. NO influence delta. The mission/bounty
  awards live in the caller and still fire — only the influence
  hook gates out.
- **Wilderness activity (rooms with `wilderness_region_id` set):**
  rep + credits + CP + influence delta routed through
  `adjust_territory_influence(..., region_slug=<slug>)` so SYN.3
  contest multipliers apply automatically.

The three engine hooks (`on_npc_kill`, `on_mission_complete`,
`on_pvp_kill`) all gate on `wilderness_region_id`. The constants
match design verbatim: `INFLUENCE_NPC_KILL=2`, `INFLUENCE_MISSION=5`,
`INFLUENCE_PVP_WIN=15`. PvP loser pays -5 (also gated on
wilderness; loser penalty short-circuits multipliers via
`apply_contest_influence_multipliers`'s `delta <= 0` early-return).

**Why this is an invariant, not just a behavior:** future reward
hooks (e.g. `on_harvest_success`, `on_anomaly_kill`,
`on_intel_handover`) MUST also gate on `wilderness_region_id` and
route through `region_slug=`. Any new influence-granting code path
that doesn't do this is a regression of the design rule.

The espionage handover (SYN.5) is the first non-combat consumer
of this invariant: `handover_intel` evaluates which region the
intel describes (via `_extract_mentioned_regions`); if no known
wilderness region is named, the credits pay out but influence is
zero. The handler-NPC sits at a faction HQ (city-map room) but
the influence lands in the *region the intel describes*, not where
the handover happens.

### §4.26 Region-anchored cities invariant (NEW v50)

**Per design v2 §2.9, cities anchor on wilderness regions.** Five
city benefits (identity, tax, citizen security upgrade, +city home,
mayor governance) survive unchanged from city-map cities. What
retargets:

- **HQ anchor:** city HQ anchors on a wilderness landmark room
  within the chosen region.
- **Expansion:** claim adjacent landmarks within the same region
  using the existing landmark adjacency graph.
- **Founding requirement:** "org owns the region OR has Foothold
  (50+ influence in parent zone)." Founding in un-owned region
  is allowed (stakes a claim with infrastructure); rival-owned
  region requires contesting via SYN.3 first.
- **Retired rule:** "Cities cannot be founded in secured zones."
  Wilderness regions are CONTESTED by default per SYN.2.

**Vitality:** per HQ tier (outpost 1, chapter house 3, fortress 5)
active citizens within 7-day window. Below threshold → `reduced`
immediately. 14 days below → `dormant`. Recovery is single-tick.
Effects: tax cap halved (seam in place), expansion blocked.

**Parallel-ship pattern:** legacy `found_city` and
`claim_room_for_city` remain operational. The 520 cities tests
stay green without retargeting. New surfaces ship alongside; parser
routes by active-org-city's `wilderness_region_id`. Retirement
depends on the SYN.4 dissolution migration having run in
production.

### §4.27 Parallel-ship discipline for engine API retargets (NEW v50)

When retargeting an engine API to a new model (e.g. zone-keyed →
region-keyed, city-map → wilderness-anchored), **the new surface
ships alongside the old, not in place of it.** The retirement of
the old surface depends on:

1. The migration that translates old data to new having run in
   production.
2. The runtime confirming no orphan legacy state remains.
3. Tests for the old surface having been retargeted to the new
   fixtures.

The retirement is then a separate drop — small, focused on
deletion and cleanup, with a clean audit trail.

**Why this is an invariant:** the alternative (big-bang retarget in
one drop) packages the new surface, the migration, the tests, and
the legacy cleanup all together. That's a higher-risk drop and
typically a longer one. The SYN wave used parallel-ship for SYN.1
(region-keyed alongside zone-keyed influence), SYN.3 (one of the
two non-parallel cases — Drop 6D zone-keyed contest deleted because
runtime data was already pre-wiped), SYN.4 (region-anchored
alongside city-map), and SYN.5 (gates added to existing hooks, no
retirement needed). The pattern compresses to its limit on SYN.3
where the deletion is HEAD-physical because the data migration is
also part of the same wave; everywhere else, deletion is a future
small drop.

**Process implication:** the SYN sequence's "retire legacy
surfaces" follow-up is **after SYN.10 closes** (or whenever the
production-side SYN.4 migration completes, whichever comes later).
~2 sessions: retargets the 520 legacy cities tests to wilderness
fixtures + physically removes `found_city` / `claim_room_for_city`
/ adjacent Drop 6D surfaces.

---

### §4.28 Hybrid raster substrate render contract (NEW v51)

When an `AreaGeometry` declares a non-empty `substrate_image`, the
client render lane MUST:

- Paint the substrate PNG at the world bounds beneath the SVG overlay
  (`L_SubstrateImage`), and
- **Suppress the procedural `L_Districts` / `L_Buildings` / `L_Streets`
  / `L_Furniture` layers** — those features are baked into the painting;
  re-drawing them double-stamps.
- Keep `L_Labels`, `L_Entities` (POIs/NPCs/PCs/player), weather, and
  chrome **on top** of the painting.
- At close zoom (tier ≤ 1), dim the painting and bring `L_SubstrateRooms`
  forward — translucent tactical room cells that emit the same
  `data-room-id` wrapper as `L_Buildings`, so click-to-walk decoration
  attaches under a substrate.

Corollaries that fall out of this contract and are pinned by tests:

- **An area's `exit_paths` and street labels are optional under a
  substrate** — streets are painted, so a relaid area (e.g. Mos Eisley)
  may carry zero `exit_paths` and only flavor labels. Tests asserting
  procedural-era counts must be rebased when an area migrates.
- **`substrate_image` is genuinely optional.** Absence ⇒ fully
  procedural rendering. The loader omits the key from the serialized
  dict when unset/empty (pinned by `test_area_loader_substrate`).
- **Schema-neutral.** Substrate adoption is a YAML + asset + render-lane
  change only; it never bumps `SCHEMA_VERSION`.

**Why this is an invariant:** the substrate lane is now the
player-facing render path for every authored CW area. The suppression
rule is what keeps the painting and the vector overlay from fighting;
the `data-room-id` rule is what keeps navigation exact at close zoom.
Violating either produces the "painting looks right but you can't click
a room" / "buildings drawn twice" failure modes the lane was built to
avoid.

---

### §4.29 World-event mechanical-effect consumption (NEW v51, 2026-06-04)

A world event's behavioural reach is entirely defined by its
`EventDef.mechanical_effects` dict, and an effect is **inert until a
consumer reads it at the metered faucet**. The single consumption
pattern is:

```python
val = get_world_event_manager().get_effect("<effect_key>", <neutral_default>)
```

read at the *faucet* — the exact site that meters the affected mechanic
(the payout `adjust_credits`, the spawn-weight pick, the skill-check pip
sum) — guarded so the neutral default (`1.0` for multipliers, `0` for
pip deltas) is a true no-op when no event is active. Rules:

- **One read per faucet, immediately before the metered action**
  (mirrors the live `smuggling_pay_mult` / `intel_pay_mult` /
  `sell_price_mult` consumers). Don't thread the value through call
  chains.
- **Declaring an effect on an `EventDef` is not wiring it.** A new
  effect key needs a consumer *and* a **consumption test** (activate the
  event, assert the metered mechanic changes). A structural test that
  the key is merely *present on the def* is necessary but not sufficient
  — that exact gap hid the `patrol_spawn_mult` shadow (§6.2 pattern 8).
- **Passive vs. flag effects.** Effects that *scale/modify an existing
  mechanic* (multipliers, pip deltas) are pure implementation and ship
  in implementation drops (E2: `bounty_reward_mult`, `pirate_spawn_mult`,
  `patrol_spawn_mult`, `perception_penalty`). Effects that are *flags
  enabling a new player interaction* (`contraband_scan`, `rare_vendor`,
  `hutt_auction`, `krayt_bounty`, `brawl_active`, `distress_active`)
  require a design decision first and are sequenced through a design pass
  (`T2.E3`, §8.19), per §4.5 (seam vs. integration) and the
  design/implementation-separation cadence.
- **Apply environmental skill modifiers at the central skill check, but
  guard by skill.** `perception_penalty` (SANDSTORM) folds into
  `perform_skill_check`'s pip sum only for the observation family
  (`_ENV_PERCEPTION_SKILLS = {perception, search}`) — never the social
  skills that merely fall back to the PERCEPTION *attribute*. The
  world-event read is the only path in that otherwise-pure function that
  touches the event singleton, and it is a no-op when no event is active.
- **Player-facing event strings obey B3 + Q1.** Event `name` /
  `announce_text` / `expire_text` and the `_zone_display` names render to
  live players in the production era, so they are era-clean (no
  Imperial/Rebel/Empire) and reference canonical figures institutionally
  only (the HUTT_AUCTION "Jabba" → "a Hutt kajidic" fix).

**Why this is an invariant:** world events are the game's ambient
"weather" — they fire on a timer and via the Director in the live era.
An unread effect is a silent dead feature; a leaked GCW/Q1 string is a
canon break shown to every player in the affected zone.

---

## §5. Process disciplines

### §5.1 Architecture rev cadence

Consolidations: every 4–6 weeks or after 8+ drops since the
last full consolidation. **v50 is consolidating early** because
the SYN wave delivered 6 drops in a single session and Brian
asked for a full consolidation rather than a delta. The next
expected consolidation is v51 after SYN.6–SYN.10 close (or a
delta if no SYN milestone has been hit).

Deltas remain acceptable between consolidations but every delta
should be paired with a backup of its parent consolidation.

### §5.2 Project knowledge tier discipline (unchanged)

Design docs are Tier 1 (must persist). Handoff docs are Tier 2
(persist until consolidated). Working notes are Tier 3.

### §5.3 Sourcebook PDF handling (unchanged)

WEG sourcebook PDFs live in project knowledge. Extraction docs
(`WEG40120_extraction_v1.md` etc.) are the live references.

### §5.4 Memory hygiene (unchanged)

UserMemories edits should be made in the same session as the
delivery they describe. userMemories should never be the source
of truth for "what shipped" — always verify against HEAD with
import-load.

### §5.5 Wookieepedia scraping (unchanged)

### §5.6 Drop-zip packaging discipline (unchanged)

Every drop zip is built project-root-mirrored from the actual
sandbox HEAD; Windows-applied via `Expand-Archive -Force`; first
action of every new session is a pre-flight audit with import-load
on items the prior session's handoff claimed shipped.

### §5.7 Long-wave drop discipline (unchanged from v48)

The May 23 cities wave validated 7 sequential drops in one
session. The May 25 SYN wave validated 6 more (some combined,
per §5.9). Pattern requirements: dependencies one-way; each
drop independently complete and testable; session can summarize
and compact mid-wave without losing audit trail; single
architecture consolidation closes the wave.

### §5.8 Design-drop review discipline (carried forward from v49)

Large external design drops (e.g. Claude Design's UI/UX work) get
a structured review against the mechanical/era constraints before
production port begins. Issues are catalogued by severity (blocker
/ high / medium / low). Path B (engineering Claude applies fixes
to the design drop before production port) is the default for
asset-heavy drops where most of the material is salvageable.

### §5.9 SYN-sequence roll-up discipline (NEW v50)

The design doc may scope a drop as N sessions; the engineer may
deliver it as a single combined drop when dependencies allow.
This was Brian's standing call going into the SYN wave: "roll up
multi-half drops into single combined deliveries."

The pattern that worked across the SYN wave:

1. **Original design scoping** estimates effort in sessions
   (e.g. SYN.3 "~1.5 sess", SYN.4 "~2 sess"). This is the
   honest first-cut estimate.
2. **In the implementation session, the engineer checks for
   sub-drop boundaries** — are the sub-drops independently
   shippable, or does sub-drop B require sub-drop A's
   surfaces to even be testable?
3. **If sub-drops are tightly coupled** (e.g. SYN.3.b's
   "Anchor kill + multipliers" tests can't exist without
   SYN.3.a's contest state machine), combine into one drop.
4. **If sub-drops are loosely coupled** (e.g. SYN.4 region
   anchor and SYN.4 vitality could in principle ship
   separately), still combine if the combined size is
   manageable (~720 LOC was the SYN.4 ceiling that worked).
5. **Document the combination** in the handoff so the
   architecture-of-record carries the actual shape, not the
   originally-scoped shape.

**Limits:**

- Don't combine across deletion boundaries. SYN.3's Drop 6D
  block deletion was its own scope; SYN.4's legacy cleanup is
  explicitly a separate future drop because it depends on a
  production-side migration.
- Don't combine across consumer/seam boundaries. If sub-drop B
  exists to wire a consumer that sub-drop A's seam exposes, ship
  the seam first and the consumer second — even if both
  technically fit in one session.
- Don't combine if total size exceeds ~1,500 LOC of changed
  source per drop. The combined drop becomes too risky to
  audit at HEAD.

The May 25 wave demonstrated the discipline works: SYN.3 and
SYN.4 both shipped as combined drops; SYN.1 shipped as a/b split
because the b half was specifically the legacy-caller retargets
that depended on the a half's new surfaces; SYN.5 shipped as a
single drop because it was naturally single-scoped.

### §5.10 Memory anchor refresh (NEW v50)

Per Brian's preference, userMemories should be refreshed at the
end of significant waves to reflect the post-wave state. The May
25 wave is one such wave. The architecture doc (v50) is the
durable anchor; userMemories carries a recent-bias snapshot.

When userMemories disagrees with the architecture doc, the
architecture doc wins. The architecture doc is sandbox-verified;
userMemories is text Brian wrote.

---

## §6. Audit and verification

### §6.1 The audit anchor

The audit anchor is **HEAD verified by import-load**, not any
handoff document or memory note. The SYN wave reinforces this:
every SYN drop's pre-flight grepped HEAD for the prior drop's
claims before writing new code; every SYN drop's tests verify
their own surfaces by import-loading the new symbols.

### §6.2 The phantom-pattern catalog (UPDATED v51)

Eight patterns (v51 adds #8 — the E2 `patrol_spawn_mult` catch). The
May 25 wave caught three of the existing patterns in flight, all
repaired before ship:

1. **Phantom-delivered** — handoff says X shipped, HEAD says no.
2. **Phantom-undelivered** — handoff says X is pending, HEAD says
   shipped. *(Caught in SYN.3: the userMemories' "Drop 6D contest
   block deletion" was scoped as upcoming, but a HEAD grep showed
   the deletion had not happened yet at the start of the session
   — userMemories was the wrong way around. The actual deletion
   shipped in SYN.3.)*
3. **Dual-source drift** — content scrubbed in one location but
   a mirroring literal not scrubbed.
4. **Stale-test-fixture drift** — test fixture mirrors live state;
   state changes but fixture doesn't.
5. **Inverted-narrative phantom** — userMemories records X as open
   when X is delivered at HEAD, or vice-versa.
6. **Sandbox-divergence phantom** — chat sandbox contains files or
   symbols that get reported as "shipped" but never reach Windows.
7. **Import-load syntax phantom** — import-load verification
   statement is syntactically wrong even though the underlying
   symbol exists.
8. **Shadowed-duplicate-definition phantom** — a symbol exists and
   even *contains* the intended logic, but a later same-named
   definition shadows it, so the path that "looks wired" never runs.
   *(Caught in E2: `engine/npc_space_traffic.py` had two
   `_pick_archetype` defs; the world-event-aware one was shadowed by
   a later `_pick_archetype(exclude_hunter=True)` — the one `_spawn`
   actually calls — so `patrol_spawn_mult`, long recorded as "live,"
   had never been consumed at runtime. No test caught it because the
   only coverage asserted the effect was **declared** on the event,
   not **consumed**. Fixed by deleting the dead def and consolidating
   both multipliers into the live one; a structural test now pins
   exactly one `_pick_archetype` definition, and consumption tests pin
   the skew. Lesson hardened into §4.29: declaration ≠ wiring; a new
   effect needs a consumption test, not just a presence test.)*

The SYN.3 case is documented as a phantom-undelivered catch; the E2
case as a shadowed-duplicate catch.

### §6.3 Smoke as wiring-verification (unchanged)

### §6.4 Verification matrix — post-SYN.5 HEAD (May 25 2026)

| Surface | Verified by | Status |
|---|---|---|
| `engine.contest.compute_anchor_hp` (SYN.3) | `from engine.contest import compute_anchor_hp; assert callable(compute_anchor_hp)` | ✓ green |
| `engine.contest.apply_contest_influence_multipliers` (SYN.3) | import-load | ✓ green |
| `engine.contest.on_npc_killed_in_combat` (SYN.3) | import-load | ✓ green |
| `engine.territory.adjust_territory_influence(region_slug=)` (SYN.1.a + SYN.3) | signature inspection + integration test | ✓ green |
| `engine.territory.claim_region` / `unclaim_region` (SYN.1.a) | import-load + test sweep | ✓ green |
| `engine.territory._get_region_landmarks` (SYN.1.a) | import-load | ✓ green |
| `engine.territory.on_npc_kill / on_mission_complete / on_pvp_kill` wilderness gate (SYN.5) | TestInfluenceHooksRetarget (9 tests) | ✓ green |
| `engine.security` wilderness-aware step 4 (SYN.2) | test_syn2 24 tests | ✓ green |
| `engine.player_cities.found_city_in_region` (SYN.4) | test_syn4a 30 tests | ✓ green |
| `engine.player_cities.claim_landmark_for_city` (SYN.4) | test_syn4a | ✓ green |
| `engine.player_cities.tick_city_vitality` (SYN.4) | test_syn4b 37 tests | ✓ green |
| `engine.player_cities.syn4_migrate_dissolve_city_map_cities` (SYN.4) | test_syn4b migration sections | ✓ green |
| `engine.intel_handlers.handover_intel` (SYN.5) | test_syn5 47 tests | ✓ green |
| `engine.intel_handlers.evaluate_intel_quality` (SYN.5) | TestEvaluateIntelQuality 7 tests | ✓ green |
| `parser.espionage_commands.IntelCommand.execute` handover branch (SYN.5) | manual code review (no parser-test infrastructure for the handover path yet) | ✓ wired |
| `parser.city_commands._handle_found` region form (SYN.4) | manual code review + downstream test | ✓ wired |
| `parser.city_commands._handle_claim` route-by-region (SYN.4) | manual code review + downstream test | ✓ wired |
| `server.tick_handlers_economy.city_vitality_tick` (SYN.4) | scheduler registration check | ✓ green |
| `server.game_server` city_vitality registration (SYN.4) | grep at HEAD | ✓ green |
| Schema v35 columns (SYN.1.b + SYN.3 + SYN.4) | `PRAGMA table_info` against sandbox DB after `ensure_schema` | ✓ green |
| Drop 6D contest block deletion (SYN.3) | `grep -n` confirms absence + retirement header present | ✓ green |
| `_apply_claim_upgrade` retirement (SYN.1.b) | grep at HEAD confirms absence | ✓ green |
| Legacy `found_city` + `claim_room_for_city` still operational (parallel-ship) | 520 cities tests green | ✓ green |
| `engine.cooldowns_enabled` (lives in `engine.jedi_gating`, NOT `engine.cooldowns`) | sandbox verification | ✓ corrected during SYN.4 |

All 299 SYN tests pass at HEAD. 1,430-test SYN-and-adjacent sweep
green.

### §6.5 Smoke-flagged design issues (unchanged)

None outstanding from the May 25 wave.

### §6.6 Import-load discipline (unchanged from v48)

Import-load verification statements MUST target module-level
symbols. For method-on-class wiring, the verification statement is
`from <module> import <ClassName>` plus
`assert callable(getattr(<ClassName>, '<method>'))`.

### §6.7 Post-SYN HEAD state (REGENERATED v50)

Engine modules (114): all import-loadable. The new `engine/contest.py`
and `engine/intel_handlers.py` are AST-clean and pass their
respective test sweeps. The expanded `engine/territory.py` retains
all its pre-SYN surfaces (parallel-ship); the new surfaces are
import-load verified per §6.4.

Parser modules (55): all import-loadable. The two retargeted
modules (`parser/city_commands.py` for SYN.4 routing,
`parser/espionage_commands.py` for SYN.5 handover) pass downstream
tests.

Server modules (16): unchanged structurally; `server/game_server.py`
and `server/tick_handlers_economy.py` have new tick registrations
(SYN.1.a, SYN.3, SYN.4).

Schema v35: SYN.1.b column add + SYN.3 two-table add + SYN.4
two-column add. All idempotent via additive ALTER + IF NOT EXISTS
on CREATE.

---

## §7. Design doc map

(Updated for the SYN wave. Other rows carried forward from v48/v49
unchanged.)

| Surface | Design doc | Status |
|---|---|---|
| Contestable Wilderness pivot (all SYN drops) | `contestable_wilderness_design_v2.md` | **LOCKED 2026-05-24; SYN.0–10 SHIPPED** |
| Web client lane (all phases) | `web_client_vision_and_protocol_v1_3.md` | v1.3 current; **SPA visual port + substrate map renderer SHIPPED**; Phases 2/4/5 post-launch |
| Map renderer reference | `Map_Redesign_v2.html` + `NANO_MAP_PACKAGE.md` | Mockup approved; **renderer SHIPPED** as the SPA tier builders + hybrid raster substrate lane (§4.28) |
| Player Cities v1.2 | `player_cities_design_v1_2.md` | Feature-complete pre-SYN; SYN.4 retargets the founding/expansion model |
| Player Cities v1.2 SYN supplements | `contestable_wilderness_design_v2.md` §2.9 | LOCKED |
| Territory contestation | `contestable_wilderness_design_v2.md` §2.4, §3.3 | SYN.3 implementation SHIPPED |
| Espionage-as-influence | `contestable_wilderness_design_v2.md` §2.7, §3.5 | SYN.5 implementation SHIPPED |
| Active harvest | `contestable_wilderness_design_v2.md` §2.5, §3.6 | SYN.6 pending |
| Wilderness anomalies | `contestable_wilderness_design_v2.md` §2.8, §3.7/§3.8 | SYN.7/8 pending |
| Building construction | `contestable_wilderness_design_v2.md` §2.9.3, §3.9 | SYN.9 pending |
| Display integration | `contestable_wilderness_design_v2.md` §2.6, §3.12 | SYN.10 pending |
| Security Model v1 | `security_model_design_v1.md` | live (with SYN.2 wilderness-aware branch added) |
| Progression Gates (PG.1/2/3) | `progression_gates_and_consequences_design_v1.md` | PG.1 + PG.2 + PG.3 Acts 1/2 SHIPPED |
| Padawan-Master | `padawan_master_system_design_v1.md` | launch-scope SHIPPED; council/lineage post-launch |
| Director AI | `director_ai_design_v1.md` | base SHIPPED; T3.15 CW-tuning post-launch |
| Director AI ↔ SYN.5 intel handover | `director_ai_design_v1.md` + `contestable_wilderness_design_v2.md` §2.10 | heuristic stub SHIPPED at SYN.5; T3.15 will swap |
| World events (`engine/world_events.py`) | `sw_mush_remediation_and_fun_additions_design_v1.md` (effects) + §4.29 (consumption invariant) | era-clean (E1) + passive effects wired (E2); 6 FLAG effects open → `T2.E3` (§8.19) |
| Weight of War | `weight_of_war_design_v1.md` | MVP_COMPLETE 2026-05-24 (Brian-confirmed) |
| Combat Posing | `combat_posing_narrative_design.md` | SHIPPED |
| Espionage (base) | `competitive_analysis_feature_designs_v1.md` §F | SHIPPED |
| Player Housing | `player_housing_design_v1.md` | SHIPPED |
| Faction Reputation | `faction_reputation_design_v1.md` | SHIPPED |
| Organizations | `organizations_factions_design_v1.md` | SHIPPED |
| Player Shops | `player_shops_design_v1.md` | SHIPPED |
| Wilderness movement | `wilderness_system_design_v1.md` + supplements | SHIPPED |
| Tutorials | `cw_tutorial_chains_design_v1.md` | SHIPPED |
| Coruscant Underworld build | `cw_content_gap_design_v1.md`, `coruscant_underworld.md` | **scope locked 2026-05-30: full 40×40×3 region file**; content build pending |
| Force-resonant landmarks | `force_resonant_landmarks_design_v1.md` | SHIPPED |
| Jedi Village | `jedi_village_quest_design_v1.md` | SHIPPED |
| Economy (Phase 1) | `economy_design_v02-1.md` + `economy_hardening_design_v1.md` + `economy_bulk_premium_design_v1.md` | SHIPPED |
| Spacer quest | `from_dust_to_stars_design_v2_clone_wars.md` | SHIPPED |
| Sabacc | (Galaxy Guide extraction + parser/sabacc_commands.py) | SHIPPED |
| Hyperspace | `space_overhaul_v3_design.md` + `npc_space_traffic_design_v2.pdf` | base SHIPPED; Wildspace post-launch |
| Encounters/Hazards | `competitive_analysis_feature_mining_v1.md` + supplements | base SHIPPED |
| Spaceflight (cargo/customs/sabacc-on-ship) | `gg6_tramp_freighters_extraction_v1.md` + extractions | SHIPPED |
| Codex (in-game help guides 01–26) | each `Guide_XX_*.md` | SHIPPED |

---

## §8. Outstanding decisions

(Most carried forward from v48/v49. **Three resolved 2026-05-30** —
§8.13 Coruscant Underworld scope, §8.7 SYN.4 migration timing, and §8.16
web-client launch-scope cutoff. §8.10 / §8.15 / §8.17 are **closed** by
the May 26–30 wave shipping. Three smaller design calls remain genuinely
open and non-blocking: Coruscant zone naming (§8.5 / T2.5), SRB.1
overdose auto-incap (§8.5 / T2.10.c), and broadening the morale-flavored
skill set (§8.6 / T2.11.b).)

### §8.1 CW pivot tactical questions

Carried forward from v48 unchanged.

### §8.2 Progression Gates open questions

Carried forward from v48.

### §8.3 Smoke-flagged design issues

None outstanding.

### §8.4 Smoke harness open questions

Carried forward.

### §8.5 Security Model open questions

- Coruscant naming reconciliation (Tier 2 #10).
- Overdose-difficulty bump for cross-type stim attempts: not in
  scope for SECMOD.1; tracked under SRB.1 follow-ups instead.

### §8.6 Support Role Buffs open questions

Carried forward from v48.

### §8.7 Player Cities open questions (UPDATED v50)

(Was v48 "design-locked, feature-complete"; v50 adds the SYN.4
items.)

- **SYN.4 `effective_tax_rate_cap` consumer wiring.** Seam in
  place; the consumer at `set_city_tax_rate` is unwired. Players
  can still set tax up to the base cap regardless of vitality
  state. Small follow-up.
- **SYN.4 dissolution migration application timing — RESOLVED
  2026-05-30: run NOW, as part of this deploy.** The migration is an
  explicit admin invocation (`await
  syn4_migrate_dissolve_city_map_cities(db)`), idempotent via its
  `syn_migration_state` marker. Brian elected to run it with this deploy
  rather than defer to a later checkpoint. Schema-neutral; legacy
  city-map cities dissolve with the 75% refund per the SYN.4 design.
- **Legacy cities tests retargeting.** 520 tests still use legacy
  fixtures. Retargeting them to wilderness fixtures is ~2 sess
  and depends on the migration having run. Post-launch.

### §8.8 Jedi Village build open questions

CLOSED.

### §8.9 Wilderness Co-location remediation open questions

CLOSED (May 17 wave's W.2.4).

### §8.10 Map redesign open questions (CLOSED 2026-05-30)

Closed by the May 26–30 wave: the SPA visual port (4.11→4.15 cutover)
and the hybrid raster substrate map lane (§4.28) shipped. The map
renderer is live in `static/client.html`.

### §8.11 +pvp opt-in tuning

Carried forward from v48. No griefing patterns observed.

### §8.12 Sandbox-divergence phantom prevention

(Carried forward from v48 as Pragmatic discipline with quarterly
Conservative sweep.)

### §8.13 Coruscant Underworld scope (RESOLVED 2026-05-30)

**Decision: author the full standalone 40×40×3 region file** (not the
lighter landmarks-as-anchors grid). This is now a defined content build
— the main pre-launch content task, Tier 2 #4 in §3.2 — not an open
design call. Scope: a full wilderness region body (40×40×3) consistent
with the existing Coruscant Underworld landmarks YAML, on the
contestable-wilderness substrate (region ownership / contests /
encounters apply as for any wilderness region).

### §8.14 Long-wave drop discipline lessons (UNCHANGED from v48)

Validated again by the May 25 SYN wave.

### §8.15 Web client implementation path (CLOSED 2026-05-30)

Path B was chosen and executed — the design drop was ported into the
vanilla-JS SPA module suite and wired live through the tier registry.
No longer on pause; the lane shipped.

### §8.16 Web client launch-scope cutoff (RESOLVED 2026-05-30)

**Decision: pull some Phase 2 rich panels into launch scope** (not
Phase-0/1-only, and not all-of-Phase-2-deferred). The SPA + substrate
map renderer — much of Phase 3 — is already live; launch additionally
includes a selected subset of Phase 2 rich panels. The specific subset
is a follow-up scoping pass against `web_client_vision_and_protocol_v1_3.md`
§9 — the natural candidates are the panels already substantially built
in the SPA suite (sheet, holocron / holonet, cockpit, combat theater /
inspector). Remaining Phase 2 items + Phases 4/5 stay post-launch.

### §8.17 SYN sequence interleave question (CLOSED 2026-05-30)

Moot: the SYN sequence ran to completion (SYN.0 → SYN.10) and the
web-client wave followed, exactly as the default assumption predicted.
No interleave decision is outstanding.

### §8.18 Intel handler NPC seeding follow-up (NEW v50)

SYN.5 ships the engine; the content drop to spawn handler NPCs at
the 9 faction HQs is pending. Without that content drop, `+intel
handover` returns the clean "No intel handler for your faction is
here" message everywhere. Single small YAML or admin-spawn pass.

### §8.19 World-event FLAG-effect interactions (NEW 2026-06-04 — `T2.E3`)

E2 wired the *passive* world-event effects (§1.4-G, §4.29). The six
**flag** effects each enable a *new* player interaction and need a design
decision before implementation (one design pass, then per-effect impl):

- **`contraband_scan`** (SECURITY_CHECKPOINT) — a sale-time **scan risk**
  when selling contraband: what is the consequence (forfeit goods? fine?
  arrest chance?), and at which sale site does it gate?
- **`rare_vendor`** (MERCHANT_ARRIVAL) — a vendor offers **rare stock**
  while active: which items, from which pool, at what price, on which
  vendor surface?
- **`hutt_auction` + `criminal_rep_gate: 30`** (HUTT_AUCTION) — an
  **auction** gated on criminal reputation ≥ 30: new command? what's
  auctioned, bidding model, and where does criminal rep come from?
  (The Q1 "Jabba" *string* is already cleaned; only the *effect* is open.)
- **`krayt_bounty`** (KRAYT_SIGHTING) — a special high-value **bounty /
  hunt**: bounty-board hook or a dedicated target spawn?
- **`brawl_active`** (CANTINA_BRAWL) — a joinable cantina **brawl**: join
  command, resolution (skill check?), reward / risk?
- **`distress_active`** (DISTRESS_SIGNAL) — an answerable **distress
  beacon**: accept command, encounter, reward?

Default lean: reuse existing systems (bounty board, vendor-droid market,
reputation, encounter pipeline) rather than bespoke mechanics. Overlaps
with sourcebook enrichment (krayt ↔ creatures/bounty; hutt_auction ↔
GG11 criminal orgs) — sequence with that lane where natural.

---

## §9. Version history

- **v51 point-update (Jun 4 2026)** — audit-remediation tail folded into
  §1.4-G (not a full re-consolidation). Records what landed since the
  May 30 cut: the economy-hardening lane (ledger chokepoint / death
  reconciliation / finances throttle — drops 0a/1b/1c/2, NPC-buyback
  price-supports, sabacc dens at **schema 39 → 40**, vanity titles +
  commissary) and the **world-event narrative-layer pass** — **E1**
  (B3 era-cleanness: GCW event/room-state strings + a clean enum rename,
  and repair of the inert CW era-milestone feature) and **E2** (the
  dormant *passive* world-event effects wired at their faucets +
  repair of the `patrol_spawn_mult` shadowed-duplicate phantom). New
  invariant **§4.29** (world-event mechanical-effect consumption);
  phantom catalog grows to **eight** (#8 shadowed-duplicate-definition);
  new open decision **§8.19** (the six FLAG-effect interactions, `T2.E3`).
  Deferred seam logged: `TD.DIRECTOR_FACTION_MODEL_GCW` (Director internal
  faction model still GCW-keyed; LLM-context only). Current
  `SCHEMA_VERSION = 40`.
- **v51 (May 30 2026)** — full consolidation. Folds in everything
  after v50: the SYN tail (SYN.6–10, which shipped May 25 but
  post-dated the v50 doc), the SPA visual port (Tier-1 #4, drops
  4.11→4.15 cutover), the hybrid raster substrate map lane (all six
  maps painted + four new areas), map A/D/B + environment + bearing,
  and the dynamic POI feed (bounty + anomalies). New invariant §4.28
  (substrate render contract). The web-client lane is no longer
  "paused behind SYN" — it is the surface that moved. Schema unchanged
  at 35 (the whole wave is render-/read-path only). Records the
  2026-05-25→30 CHANGELOG/TODO ledger lapse + backfill.
- **v50 (May 25 2026)** — full consolidation, the May 25 SYN wave.
  Contestable Wilderness pivot SHIPPED through SYN.5; SYN.6–10
  queued (they in fact shipped the same day, post-doc — captured in
  v51). Three new invariants (§4.25 wilderness-only influence,
  §4.26 region-anchored cities, §4.27 parallel-ship discipline).
  New process discipline (§5.9 SYN-sequence roll-up). Web client
  lane unchanged from v49 (on pause behind SYN).
- **v49 (May 24 2026)** — delta against v48. Web-client lane
  opened as first-class third lane. Vision/protocol doc v1.0 →
  v1.2 + Claude Design drop review folded in. Tier 1 #3 added
  (bug-fix sprint).
- **v48 (May 23 2026)** — full consolidation post-Player-Cities
  v1.2. Closes v47 Tier 1 #3 (HEAD re-audit). Adds invariants
  §4.21 (cities web-UI safety pattern) and §4.22 (combat-trigger
  state). Adds phantom pattern 7 (import-load syntax phantom).
- **v47 (May 21 2026)** — full consolidation post-rebuild wave.
  Recovers v44/v45 structural material from v46 + handoffs. Adds
  phantom pattern 6 (sandbox-divergence) and §6.6 import-load
  discipline.
- **v46 (May 22 2026)** — delta against v45 (lost). Superseded by
  v47.
- **v45 (presumed mid-May 2026)** — NOT IN PROJECT FILES.
  Referenced by v46 but absent.
- **v44 (presumed mid-May 2026)** — NOT IN PROJECT FILES. Material
  recovered into v47.
- **v43 (May 18 2026)** — full consolidation post-May-18 wave.
  Adds inverted-narrative phantom to catalog.
- **v40 (~mid-April 2026)** — earliest reference in current docs
  for the "web-first directive locked since" anchor.

---

## §10. Closing notes

### §10.1 What v50 retires from v49

- v49 Tier 1 #3 was the next-session item (bug-fix sprint).
  **v50 retains it as Tier 1 #3 but explicitly notes it's
  paused behind the SYN sequence.** When SYN.10 closes, this is
  the immediate next item.
- v48 Tier 2 #5–#8 (Security Model + F.MAP.4/5/7) — already
  retired by v49 (subsumed under web-client lane). v50 carries
  v49's retirement.
- v48 Tier 3 #17 #18 (sheet redesign, ground UX overhaul) —
  already retired by v49 (subsumed under web-client Phase 2).
  v50 carries forward.
- The Drop 6D zone-keyed territory contest block — **physically
  deleted in SYN.3**, replaced with a 24-line retirement header
  in `engine/territory.py` pointing at `engine/contest.py`. This
  is the cleanest retirement v50 records: no phantom, no
  parallel-ship period — the deletion shipped in the same drop
  the replacement shipped, because data migration (SYN.1.b)
  preceded it.
- `engine/security.py::_apply_claim_upgrade` — retired in SYN.1.b.

### §10.2 What v50 newly tracks

- The SYN sequence as Tier 1 #4 + Tier 2 #5–#8 (SYN.6 through
  SYN.10).
- Three new invariants: §4.25 (wilderness-only influence), §4.26
  (region-anchored cities), §4.27 (parallel-ship discipline).
- One new process discipline: §5.9 (SYN-sequence roll-up).
- One new audit anchor item: §6.4 verification matrix updated for
  all 299 SYN-wave symbols.
- Two new open questions: §8.17 (SYN sequence interleave with
  web), §8.18 (intel handler NPC seeding content drop).

### §10.3 What v50 keeps unchanged from v48/v49

- The engine/parser/server/data/static/test layer model.
- The phantom-pattern catalog (7 patterns; no new pattern from
  the SYN wave).
- The web-client lane phasing (Phase 0–5 per the vision doc).
- The drop-zip packaging discipline, the import-load verification
  discipline, the memory-hygiene discipline.
- The launch-scope reading (with SYN sequence additions inline).

### §10.4 The lesson of the May 25 SYN wave

**Six drops in one session.** All shipped clean, all green at
HEAD. The combined-drop discipline (§5.9) worked: SYN.3 packaged
the contest state machine + the Drop 6D deletion in one drop
because the data migration preceded the deletion; SYN.4 packaged
region-anchored founding + landmark expansion + vitality + the
75%-refund migration in one drop because they shared the same DB
schema delta. SYN.5 stayed single-scope because it was naturally
one drop's worth.

The parallel-ship discipline (§4.27) was the safety net. SYN.1's
new region-keyed surfaces shipped alongside the existing
zone-keyed ones; SYN.4's new region-anchored founding shipped
alongside the legacy city-map founding. The 520 cities tests
didn't move during the wave — they validated their legacy
surfaces, which the wave didn't touch. The new SYN tests validated
the new surfaces. No fixture retargeting, no test churn.

The wave caught one phantom-undelivered (the Drop 6D deletion was
scheduled in userMemories as upcoming but had not happened) and
one import-source error (`cooldowns_enabled` lives in
`engine.jedi_gating`, not `engine.cooldowns`). Both repaired in
flight. The phantom-pattern catalog from v47/v48 is doing its
job — patterns get named, then they get caught faster the next
time.

**The web-client lane has moved.** v50 documented it as the parked
surface ("no progress to document, only patient parking"). v51 records
the opposite: the SPA visual port shipped end-to-end (4.11→4.15), the
map set migrated to the hybrid raster substrate lane (§4.28), and map
navigation / environment / bearing / POI feeds are live. The same
disciplines that carried the SYN wave carried this one — grep-HEAD
pre-flight caught that the ledger had lapsed and that the substrate
relayout (not this session's work) was what broke the map tests; the
loud-substitution and labeled-fallback patterns kept the new render
modules defensive. The phantom-pattern catalog earned its keep again
this wave: the "inverted-narrative" pattern showed up as memory/handoff
docs listing already-shipped work as pending.

### §10.5 What v50 explicitly does NOT trust

- **userMemories** still references some pre-v51 state (e.g. the SPA
  port listed as ~97% with the inner-tier triplet and cutover still
  "remaining," and no mention of the substrate migration). v51 is
  grounded in HEAD (verified by AST + import-load + the May 30
  regression sweep) and supplements with the map handoffs
  (`MAP_NAV_OVERLAY_DROP_20260529.md`, `NANO_MAP_PACKAGE.md`,
  `HANDOFF_MAP_ENV_BEARING_POI_20260530.md`,
  `HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md`). userMemories
  should be refreshed at Brian's discretion to reflect SYN.0–10 closed,
  the SPA port + cutover shipped, and the substrate lane live.
- Older Contestable Wilderness design iterations (v1 if any exist
  in archive). `contestable_wilderness_design_v2.md` LOCKED
  2026-05-24 is the single source of truth.
- v48 and v49 as authoritative. v50 supersedes both.

### §10.6 The path to launch (current reading)

The two largest surfaces in v50's path — the SYN sequence and the
web-client port — are now **behind us**. What remains is short:

1. **Browser smoke-test the substrate map lane** (Brian, Windows) —
   substrate cells land on painted features, dim level reads right,
   click-to-walk traverses exits. The only thing the sandbox can't
   verify.
2. **Coruscant Underworld build** — author the full 40×40×3 region file
   (scope locked, §8.13).
3. **Intel handler NPC seeding** — spawn handlers at the faction HQs.
   ⚠ Carries a dependency surfaced 2026-05-30: HQ rooms are *dynamically
   created* by `engine/housing.py` (`org_hq` rooms, `organizations.hq_room_id`
   FK) when an org establishes an HQ, **not** statically pre-seeded — so a
   handler seed must resolve the live `hq_room_id`, not a YAML-fixed room
   id, or it dangles. Five factions carry an `hq_room_name`; the "9 HQs"
   figure in the SYN.5 follow-up needs reconciling against that. Treat as a
   small *content + light-seeding* drop, not a pure YAML edit.
4. **Brian's remaining design call** (eavesdrop `target_char`; the
   `skill_check_passed` one is resolved).
5. **Launch.**

*(Retired from this list 2026-05-30: the "mission/objective POI markers"
item — the room-anchored runtime POI feed is complete (bounty + anomaly +
vendor + objective, §1.4-F); only mission-giver pins remain and they're
blocked on a non-existent giver-room field, tracked in §1.5.)*

Post-launch:
- Web-client Phases 2/4/5 (rich panels bulk, diegetic polish, mobile).
- Cities multi-city-per-org, P2P city discovery; legacy cities tests
  retargeted to wilderness fixtures + legacy founding surfaces removed.
- Padawan-Master council politics, formal lineage trees.
- Space Wildspace expansion; Director AI CW prompt tuning (T3.15);
  PG.3 Act 3 formal Knighting trial; F.7.n Force-attribute seeding.
- The v51 architecture doc itself was the doc-side close of `TD.ARCH_V51`.

---

*v51 consolidates the SYN tail and the May 26–30 web/map wave. The
Contestable Wilderness pivot is fully shipped (SYN.0→10); the web-client
SPA visual port is live end-to-end through the tier registry; and the
entire CW map set renders on a hybrid raster substrate (§4.28). The
headline shift from v50: the web-client lane is no longer the parked
surface — it's the one that moved. The wave was schema-neutral, so it
applies with no migration. The 2026-06-04 point-update (§1.4-G) then
folds in the audit-remediation tail: the economy-hardening lane (which
moved the schema to 40) and the world-event narrative-layer pass (E1 +
E2) — closing a live B3 era leak, repairing the inert CW milestone
feature, bringing the dormant passive world-event effects online (new
invariant §4.29), and catching a long-standing `patrol_spawn_mult`
shadow phantom (catalog #8). The path to launch is now short, and what's
left is mostly a browser smoke-test and a few small content/follow-up
drops.*

