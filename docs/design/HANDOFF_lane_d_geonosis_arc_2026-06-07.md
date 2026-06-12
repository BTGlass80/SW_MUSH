# HANDOFF — Lane D (Geonosis) arc — 2026-06-07

Sourcebook-enrichment **Lane D** taken from foundation through a complete,
self-contained Geonosis vertical slice: factions → contest wiring → an interior
tier → a wilderness region → a dynamic weather event → that event changing the
world. Source throughout: `geonosis_outer_rim_extraction_v1.md` (a WotC d20
sourcebook → **lore only**, creatures re-statted to D6 from scratch).

---

## ⚠️ INSTALL STATE — read this first

Your tree is **behind HEAD** by everything after the interior tier. The chain of
"include this drop with the next" means the work accumulated into one zip.

| Work | Shipped as | Installed? |
|------|-----------|-----------|
| **D1** Geonosis foundation orgs (Stalgasin / Gehenbar) | in the D1+D2+interior rollup | ✅ installed |
| **D2** violence_index → contest aggression + turf narration | in the D1+D2+interior rollup | ✅ installed |
| **Interior tier** — Gladiator Barracks (`geonosis_barracks`) + map-safety guard | `SW_MUSH_lane_d1_d2_interior_geonosis_20260607.zip` | ✅ installed |
| **Wilderness tier** — 4 creatures + the E'Y-Akh region | (carried) | ❌ **not yet** |
| **Flood event** — `EventType.FLOOD` + `+weather` | (carried) | ❌ **not yet** |
| **Flood → encounter wiring** — `event_gate` seam | (carried) | ❌ **not yet** |

**👉 Next action:** install the latest cumulative zip, which contains *all three*
uninstalled pieces as a self-consistent superset:

```
SW_MUSH_lane_d_wilderness_flood_encounters_20260607.zip   (13 files)
Expand-Archive -DestinationPath . -Force
```

It carries the **newest** `geonosis.yaml` / `zones.yaml` / `era.yaml` (cumulative
supersets including the already-installed interior-tier edits), plus the net-new
engine/data/test files. The D1/D2-only files (`organizations.yaml`,
`director_config.yaml`, `engine/contest.py`) were installed with the rollup and
are **not** re-shipped — they're unchanged since.

After installing, run the full `run_all_tests.bat` (your Windows box is ground
truth, ~7,700+). New test files to expect green:

- `tests/test_lane_d_geonosis_wilderness.py` (+19)
- `tests/test_lane_d_ey_akh_flood.py` (+12)
- `tests/test_lane_d_flood_encounters.py` (+11)

(Installed already, for reference: `test_lane_d1_geonosis_orgs.py` +21,
`test_lane_d2_contest_violence.py` +18, `test_geonosis_barracks_and_map_safety.py`
+17.)

---

## What shipped this session (drop by drop)

### D1 — Geonosis foundation orgs *(installed)*
Stalgasin + Gehenbar hive orgs into `organizations.yaml`: both `npc_only` +
`director_managed`, one "Hive Drone" rank, `properties` with
color/axis/violence_index. **No `scale`** (E1 rule: scale only on criminal orgs;
political/military get a posture). Stalgasin axis:separatist VI 88 ("range war",
names Acklay Chopper); Gehenbar axis:republic VI 84 ("bloody", names Typtus of
the 33rd Egg). Registered in `director_config.yaml` + `era.yaml`
`npc_only_factions`. Live consumer: `violence_index` → `format_org_posture_line`
→ `faction info <code>`. Hives stay **out of** `valid_factions` (byte-pinned at 6)
— non-joinability comes from absence, not a flag.

### D2 — violence_index → contest aggression *(installed)*
Wired violence_index into the SYN.3 region-contest engine (`engine/contest.py`),
extend-don't-add. **Fork resolved (lighter path):** did NOT elevate the hives into
the influence-driven region_contests state machine (would break the count-6 pin);
instead made VI matter via a generic live consumer —
`compute_anchor_reinforcements(challenger_influence, challenger_violence_index)`
(bloody ≥70 → +1, range war ≥85 → +2, gated on base>0). Default `None` reproduces
the pre-D2 table exactly. Plus posture clauses in the declaration broadcast and a
`[range war]`/`[bloody]` tag in the status lines, via a failure-tolerant
`_org_violence_index` helper.

### Interior tier — Gladiator Barracks + map-safety guard *(installed)*
6-room `geonosis_barracks` zone (ids 438–443) beneath the Petranaki Arena —
Acklay Chopper's domain (muster yard, cells, training pit, armory, slavemaster's
den, work-party staging). Reached from `geonosis_arena_prep_room` via a reciprocal
zone-transition. **Map-safety proven by diff:** zero deleted/modified lines in
`geonosis.yaml`; every change an addition; the only existing-room edit a single
`barracks:` doorway. The guard (`test_geonosis_barracks_and_map_safety.py`) pins
the exterior `geonosis_surface` room set **and** every (map_x, map_y) to a golden
snapshot — **any future drop that moves a Geonosis room fails it.**

### Wilderness tier — the E'Y-Akh + 4 creatures *(NOT installed)*
- **4 creatures** appended to `data/npcs_creatures.yaml` (now 18): `acklay`,
  `mutant_acklay`, `merdeth`, `mip_swarm`. WotC-lore → **D6 re-stats from
  scratch** (§1.8 stubs), marked NOT-WEG-transcriptions, flagged for dev-box
  calibration. **Faithful:** only the merdeth has "grab" → it carries the Lane A
  `special_attack.restraint.kind: grapple`; the others carry **no invented
  restraint**.
- **Region** `wilderness/ey_akh.yaml` (NEW): `geonosis_ey_akh`, 30×30 grid,
  terrains dune/badlands/ebon_sea_shore/crater, a 5-entry encounter pool spawning
  all 4 creatures (terrain-gated, no orphans), landmarks the **Ebon Sea** (the
  acklay habitat — pays off the barracks capture-run hook) and **Golbah's Pit**.
- **Map-safety:** the on-foot edge room (`ey_akh_desert_edge`, id 444) lives in
  the NEW `geonosis_ey_akh` zone (surface stays at 13 rooms); the only existing
  edit a single `desert:` doorway on `geonosis_surface_ruins`. Desert tiles are
  loader-wired from the region's `edges:` block.
- **No invented ambient hazard** — terrains use only `extreme_heat`/`none`; the
  Pit's poison is lore, not a mechanical field with no consumer.

### Flood event *(NOT installed)*
`EventType.FLOOD` + EventDef in `engine/world_events.py`, riding the storm
machinery (extend-don't-add). Region-scoped (`preferred_zones:
["geonosis_ey_akh"]`), long/rare (60–120 min, ~1/18h — rarer than the rarest
storm), with the drowning-merdeth + shell lore in announce/clear. One declared
effect — `perception_penalty: -3` (−1D) — with a **live** consumer
(`skill_checks`). Surfaced in `+weather` (added `flood` to the command's weather
set; added a `geonosis_ey_akh` display name).

### Flood → encounter wiring *(NOT installed)*
The flood now **changes the desert**. New `event_gate` seam on the wilderness
selector (`engine/wilderness_encounters.py`), parallel to `faction_gate`: an
encounter gated `event_gate: flood` is eligible only while the flood is active —
and `evaluate_event_gate` is **ZONE-AWARE** (matches the event's `zones_affected`
against the region's zone), so a flood in the E'Y-Akh does *not* unlock flood
encounters in the dune sea. Two flood-gated encounters in `ey_akh.yaml`
(`flood_drowning_merdeth`, `flood_displaced_acklay`), referencing existing
creatures. The normal pool is unaffected — the flood **adds** danger.

**The flood mechanic is now complete** (event + perception effect + zone-aware
encounter wiring).

---

## Lane D — what's left

1. **Marmio Mio's wrecked freighter** — an original-NPC info-broker site in the
   E'Y-Akh (a half-buried Action IV transport ringed by six merdeth shells; the
   "stranded trader" is actually a multi-hive spy). A landmark in `ey_akh.yaml`
   + the NPC. **Note:** Geonosis defines no interactive NPC entities in the
   planet file (NPCs there are atmospheric-in-description); a full interactive
   Marmio Mio is an NPC-system drop, or reference her atmospherically like Acklay
   Chopper.
2. **N'G'Zi badlands** as a distinct sub-region (there's already a `badlands`
   terrain in `ey_akh.yaml` — decide: named landmark within ey_akh vs. its own
   region).
3. **Then: the Kamino build** (the other half of the §1.x extraction — Tipoca
   City, the cloning facilities; Q1 keeps Lama Su / Taun We / Nala Se as
   institutional/absence framing).

After Lane D: **Lane C** (vendor/purchasable gear families can ship now as credit
sinks; craftable/lootable gated behind Drop-5 farming) and **Lane F**.

---

## Disciplines & gotchas reinforced this session

- **Map-safety pattern (Brian's explicit concern, now codified):** new areas go in
  a **new zone**, never the pinned exterior. The only existing-room edit is a
  single added doorway (never move a room, never delete/rewire an exit). Prove it
  by diffing against the upload (expect zero `<` lines) and pin coordinates in a
  golden-snapshot guard. The barracks guard now protects all of `geonosis_surface`.
- **No-phantom forced creatures + region together.** Lane A never shipped orphan
  creatures; they land with the encounter pool that consumes them. (The Lane A
  orphan test is biome-scoped via `TATOOINE_IDS`, but the principle is global.)
- **WotC = lore only.** The Geonosis creatures are D6 re-stats from scratch,
  explicitly *not* WEG transcriptions; the tests assert the source string says so.
- **Never declare a mechanical field without a live consumer.** The flood's
  `perception_penalty` is consumed by `skill_checks` (test proves it via a source
  check); no invented toxin hazard for Golbah's Pit (the engine has no toxin
  consumer); the merdeth grapple wires into the Lane A restraint machinery.
- **The world-events coarse-zone tech-debt — and the right direction out of it.**
  The storms/flood broadcast globally and the combat/skill consumers read the
  global `get_effect` path (the flagged tech-debt; the flood is no worse than the
  storms here). But the **new `event_gate` seam uses the ZONED `zones_affected`
  check** — the first zone-aware world-event consumer, a step *toward* retiring the
  debt rather than extending the leak. That seam is now reusable for any
  event-driven encounter.
- **Test-isolation gotcha (cost a debugging cycle):** the world-events singleton is
  `engine.world_events._manager` (NOT `_world_event_manager`). Reset it with
  `we._manager = None` between tests, or a flood activated in one test leaks into
  the next.
- **Pre-existing, flagged-not-fixed:** arena floor room 422 names
  Padmé/Anakin/Obi-Wan in a past-tense lore reference (the AotC chaining posts).
  Left untouched (out of scope + rewording would violate map-safety); flagged in
  `TODO.json` if a strict Q1 pass wants it later.

---

## Authoritative references for the next session

- `CHANGELOG.md` (newest at top) and `TODO.json` `_notes` — the real record;
  the architecture doc `sw_d6_mush_architecture_v51.md` is **stale**, don't trust
  it for current state.
- `sourcebook_enrichment_roadmap_v1.md` — Lanes A–F. Lane A complete; B complete;
  E complete through E2; **D in progress (this arc)**; C gated behind Drop-5; F
  remaining.
- **Regression split:** full `run_all_tests.bat` (~7,700+) on the Windows dev box
  is ground truth. Sandbox runs targeted `python3 -m unittest` only — `pytest` /
  `aiosqlite` / `aiohttp` / `ruamel` are absent there (import errors from those
  are environment limits, **not** failures). `load_wilderness_region` and the
  world-event manager **do** run in the sandbox.

---

## Deliverable

`SW_MUSH_lane_d_wilderness_flood_encounters_20260607.zip` — 13 files, atomic
root-mirrored, integrity-verified. Install with
`Expand-Archive -DestinationPath . -Force` from the project root.
