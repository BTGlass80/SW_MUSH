# HANDOFF — POI feed completed (objective + vendor) + orphan-module cleanup — 2026-05-30

**Zip:** `SW_MUSH_drop_objective_and_vendor_poi_2026-05-30.zip` —
**combined rolled-up** (5 files). Apply with `Expand-Archive -Force` over
project root. Built on the HEAD you uploaded
(`SW_MUSH_upload_20260530_1828.zip`, the post-anomaly-POI/relayout tree).

> **⚠ One manual step on apply — a file DELETION the zip can't carry.**
> This drop also **deletes** `parser/admin_fp_commands.py` (orphan module, see
> §12). `Expand-Archive -Force` only adds/overwrites — it will **not** remove the
> file. After extracting, delete it manually:
> `Remove-Item parser\admin_fp_commands.py` (or `git rm parser/admin_fp_commands.py`).
> Until you do, `test_admin_fp_module_removed` keeps failing on Windows (it
> asserts the file is gone). Nothing imports the module, so leaving it is inert
> except for that one test.

**Architecture doc:** `sw_d6_mush_architecture_v51.md` — updated, delivered
**standalone** in outputs (architecture docs live outside the code tree, which
is why `Expand-Archive` never carries them). Place it where you keep
architecture docs / project knowledge and discard the prior v51.

**Changed source:** `server/session.py` (`_build_area_pois`),
`engine/missions.py` (`MissionBoard.refresh`)
**Deleted source:** `parser/admin_fp_commands.py` (orphan; see §12 + the ⚠ above)
**Changed tests:** `tests/test_poi_feed.py` (+20; 17 → 37)
**Changed trackers:** `CHANGELOG.md` (2 entries — POI + the deletion),
`TODO.json` (4 `_notes` lines)
**JS:** none — `m3_adapter.js`, `m3_composition_engine.js`,
`m3_assets_markers.js`, `client.html` all verified byte-identical to HEAD.

This rolls up one session's work into a single drop (per the combined-drop
directive): (1) the POI feed completed with two new kinds, and (2) an
orphan-module deletion that clears a carried-forward baseline failure. The
dynamic POI feed's `L_Entities` layer now renders all four *room-anchored*
runtime kinds it was built to carry — **bounty + anomaly + vendor + objective**.
Only mission-giver pins remain, blocked on a field that doesn't exist (§10).

---

## 1 — What shipped

The feed already carried two area-state kinds — **bounty** crosshairs and
**wilderness-anomaly** glyphs (`anomaly_t1/2/3`). This drop adds the other two,
both in the now-familiar shape: **the renderer + adapter were already in place;
only the server-side enumeration onto `L_Entities` was missing.**

### 1a — Objective POI (personal)

Unlike bounty/anomaly (area-state: everything in view, for everyone), the
objective is *personal* — it's the destination of a mission **this** character
accepted. In `_build_area_pois`:

- read `self.character`,
- find that character's missions with
  `status == MissionStatus.ACCEPTED and accepted_by == this char`,
- for each, resolve `destination_room_id` through the same
  `resolve_area_room_ids` render-coord bridge bounties/anomalies/contacts use,
- if that room is in view, append `{kind: "objective", x, y}` — a green star
  (`MK_Objective`), semantically "your objective is *here*".

### 1b — Vendor POI (area-state)

Joins the bounty/anomaly group. Vendor droids are player-owned objects
(`type='vendor_droid'`) anchored to a room when deployed (`shop place`); unplaced
ones sit in inventory with `room_id=NULL`. The sweep is **one batched query**,
mirroring the contacts NPC sweep exactly:

```sql
SELECT room_id FROM objects WHERE type = 'vendor_droid' AND room_id IN (…)
```

— the `?` count bounded by the area's authored rooms (53 for Mos Eisley), so it
adds **a single indexed query per push, not one-per-room**. The `room_id IN`
filter drops unplaced droids automatically. `{kind: "vendor", x, y}` per
shopfront in view — an amber awning (`MK_Vendor`).

Both kinds emit the minimal `{kind, x, y}` shape because `L_Entities` calls each
marker as `build({ p: palette })` — it passes only the palette, no name; every
POI is a positioned glyph (consistent with bounty/anomaly). A vendor's name
would only matter for a future hover label (a separate UI change).

## 2 — The pre-flight finding (why the objective half was smaller than billed)

The morning's handoff (`HANDOFF_ANOMALY_POI_AND_RELAYOUT_TESTS_20260530.md` §1,
and the prior v51 §1.5 / §10.6 item 2) listed mission/objective markers as
blocked because "missions carry a destination *name*, not a room id yet."
**Grep-HEAD overturned that.** `engine/missions.py::Mission` has had
`destination_room_id: Optional[str]` all along (dataclass field, serialized in
`to_dict`/`from_dict`), and the ground-mission generator already populates it
from a real DB room. The prior author had looked only at `_hud_active_jobs`,
which *displays* `m.destination` (the human-readable name) for the jobs panel,
and concluded the room id didn't exist. It did. **The field was there; only the
map enumeration was missing.** This is the discipline rule "grep HEAD before
claiming delivered or undelivered" doing its job — Pattern 3 (inverted-narrative),
caught in pre-flight before a line was written.

## 3 — Enabling co-fix: `MissionBoard.refresh` lazy room fetch

For the objective marker to fire, accepted missions need a populated
`destination_room_id`. The player-facing board path (`+missions` →
`ensure_loaded(db, rooms)`) already supplied rooms. But the **per-tick** board
housekeeping (`server/tick_handlers_economy.py::board_housekeeping_tick`) calls
`ensure_loaded(db)` with **no** rooms, so tick-spawned missions were generated
with `destination_room_id=None` and could never show an objective.

Fix — in `MissionBoard.refresh`, **lazily** fetch the room list only when
actually filling the board:

```python
needed = BOARD_MAX - len(self._missions)
if needed > 0:
    if rooms is None and hasattr(db, "get_all_rooms"):
        try:
            rooms = await db.get_all_rooms()
        except Exception as _re:
            log.warning(...)           # degrades to name-only destinations
    new_missions = generate_board(destination_rooms=rooms, count=needed)
```

- **Zero per-tick DB cost** — `ensure_loaded` only calls `refresh` past
  `REFRESH_SECONDS` (30 min), and the fetch is further gated on `needed > 0`.
- **Every existing caller is byte-identical** — callers that pass `rooms` skip
  the fetch (`rooms is None` guard).
- **Guarded** — a fetch failure logs and proceeds with name-only destinations.

Space missions deliberately set `destination_room_id=None` (zone targets, not
ground rooms) and so are correctly skipped by the objective sweep — no marker,
no error.

## 4 — Zero JS, verified

The whole render path already existed and is **byte-identical to HEAD**
(diff-checked against the pristine upload, in clean-room):

- `m3_assets_markers.js` — `MK_Objective` (green star), `MK_Vendor` (amber
  awning), both in `MARKERS`.
- `m3_composition_engine.js` — `L_Entities` `poiMap.objective` and
  `poiMap.vendor` (lines 560/563).
- `m3_adapter.js` — `_buildDynamic` appends server `geom.pois` with a
  finite-coord + has-kind guard, passing `kind` through unchanged (no
  whitelist), Y-flipped to match landmarks.
- `client.html` — stores `data.pois → _sw_areaGeom.pois` on both paths.

## 5 — Tests (+20 in `tests/test_poi_feed.py`, 17 → 37)

Objective sweep (8): maps an accepted mission's destination; skips un-accepted /
another character's / out-of-view / no-`destination_room_id` (space mission) /
no-`character` (bare session); swallows board errors while preserving bounty
POIs; coexists with bounty + anomaly.

Vendor sweep (7): maps placed droids; asserts the sweep is a **single batched,
type-gated** query with params == the covered room ids (the two properties that
keep it cheap and correct); skips out-of-view; swallows query errors while
preserving bounty POIs; an **all-four-kinds-coexist** test (bounty + anomaly +
vendor + objective land together).

Lazy-rooms refresh (3): empty board + no rooms → `refresh` fetches rooms once and
missions get real destination ids; full board → no fetch; explicit rooms → used
as-is, no redundant `get_all_rooms`.

Static guards (4): `test_server_wires_objective_sweep`,
`test_server_wires_vendor_sweep` (source has the type-gated IN-query +
`{kind:"vendor"}`), `test_composition_engine_renders_objective_kind`,
`test_composition_engine_renders_vendor_kind` (poiMap maps both — else the
glyphs silently vanish, same invariant as the anomaly guard).

**Static-guard slice-window note.** Two existing guards slice the method body by
fixed offset: `test_server_stamps_pois_on_hud` (`[:2500]`, asserts
`"kind": "bounty"`) and `test_server_wires_anomaly_sweep` (`[:3500]`). The
objective docstring swap was kept **length-neutral**, and the vendor sweep was
placed **after** the anomaly block (not after bounty), so every existing needle
keeps its offset. Re-measured before each run: `"kind": "bounty"` sits at 2476
(< 2500); the anomaly import at 3013 (< 3500). ✓

## 6 — Sandbox + clean-room verification

- `py_compile` + AST parse: `server/session.py`, `engine/missions.py`,
  `tests/test_poi_feed.py` — OK.
- Working tree: `test_poi_feed.py` **37 passed**; map/HUD/contacts/substrate
  **201**; mission + jobs **138**; vendor-droid-touching (`cities_phase4`,
  `session39`) **73** — all green.
- **Clean-room** (combined zip applied over a *fresh* pristine via `unzip -o`,
  the `Expand-Archive -Force` sim, **then the manual `rm parser/admin_fp_commands.py`**):
  - `test_poi_feed.py` (37) + `test_wow3c_dsp_fp_wiring.py` (27) → **64 passed**;
  - all `test_wow*` + contacts + HUD + mission + jobs → **360 passed**;
  - core map/area/substrate/POI → **175 passed**.
  - **JS byte-identity** vs pristine: all four files IDENTICAL.
  - **Diff inventory** vs pristine: exactly the five zip files differ, **plus
    `parser/admin_fp_commands.py` present only in pristine** (i.e. correctly
    deleted in the applied tree). Nothing else moved.

> **Pre-existing failure (not this drop), flagged so it isn't misattributed.**
> In a broad session sweep, `tests/test_area_map_emits_slug.py::
> test_every_room_carries_slug` fails **only when a prior test in the same
> process closed the event loop** — that file uses the deprecated
> `asyncio.get_event_loop().run_until_complete()`. It passes in isolation (3/3)
> and **reproduces identically on the pristine upload** with the same ordering
> (`1 failed, 165 passed` on both trees, halted by `-x` from `pytest.ini`).
> Sandbox-only cross-file ordering artifact; my edits touch neither
> `build_area_map` nor that file. Runs clean on your Windows `run_all_tests.bat`.

```
run_all_tests.bat
# targeted:
python -m pytest tests/test_poi_feed.py -q
```

## 7 — To see it live

- **Objective:** accept a **ground** mission whose destination room is in your
  current area's map view (e.g. a Mos Eisley mission with a Mos Eisley
  destination). A green star appears on that room in the SECTOR MAP. Space
  missions show none (zone target) — by design.
- **Vendor:** deploy a vendor droid in a room in view (`shop place`). An amber
  awning glyph appears on that room. Recall it (`shop recall`) and it vanishes
  on the next push.
- Both render alongside any bounty crosshairs and anomaly glyphs.

## 8 — Architecture v51 updates (in the standalone `.md`)

- **§1.4-F** (new block) — records both POI drops, the pre-flight finding, and
  the lazy-rooms co-fix.
- **§1.4-D** — POI line rewritten to list all four kinds, split area-state vs
  personal.
- **§1.5** — the "Mission/objective POI markers" open item replaced with
  "Mission-**giver** POI pins" (the only `kind` the renderer knows but the
  server can't emit, blocked on a giver-room field).
- **§3 roadmap table + forward plan, §10.6 path-to-launch** — POI markers
  retired from the launch list (feed complete); intel-handler seeding annotated
  with the dependency below.

## 9 — A dependency I surfaced (intel-handler seeding)

Investigated the next candidate (the SYN.5 "intel handler NPC seeding" follow-up)
and found it is **not a pure YAML edit**: HQ rooms are *dynamically created* by
`engine/housing.py` (`org_hq` rooms, `organizations.hq_room_id` FK) when an org
establishes an HQ — not statically pre-seeded. A handler seed must therefore
resolve the **live** `hq_room_id`, not a YAML-fixed room id, or the NPC dangles.
Also: five factions carry an `hq_room_name`, so the "9 HQs" figure in the
follow-up needs reconciling. I did **not** guess at a seed — recorded in v51
§10.6 / §3 and TODO `_notes` as a small *content + light-seeding* drop awaiting
that decision.

## 10 — What remains on the POI feed

- **Mission-giver pins** (`MK_Mission`, amber exclamation) — needs a giver→room
  field that doesn't exist (`giver` is a name). Renderer + `poiMap.mission` +
  adapter pass-through are already in place, so it'd be another
  server-enumeration-only drop the day a mission gains a giver-room field.

## 11 — Next candidates

- **Browser smoke-test the substrate map lane** (Windows) — still the top
  launch-gating item; the objective star + vendor awning are two more glyphs to
  eye in that pass.
- **Coruscant Underworld 40×40×3 region build** (§8.13, scope locked) — the main
  pre-launch content task.
- **Intel handler NPC seeding** — once the live-`hq_room_id` approach in §9 is
  decided.

Say the word.

## 12 — Orphan-module deletion: `parser/admin_fp_commands.py`

Cleared a carried-forward baseline failure listed in v51 §1.3. The test
`test_wow3c_dsp_fp_wiring.py::TestNoLeftoverAdminFpModule::test_admin_fp_module_removed`
asserts the module is gone (its `@fp` admin surface was folded into
`@weight <name> fp <delta> [for <reason>]` — the `fp` subform — during the WoW.4
consolidation). The module had simply never been deleted.

Pre-flight before removing (so this isn't a phantom deletion that drops live
behavior):
- The replacement is live: `@weight <name> fp <delta>` exists in the weight
  commands and still routes positive deltas through
  `engine.weight_of_war.fp_award_after_weight` (the same §7.2 Weight-of-War
  award multiplier the old `@fp` applied). So functionality is preserved.
- `server/game_server.py` already had **no** reference (the test's 2nd/3rd
  assertions).
- A full-tree grep (`--include=*.py`, excluding the module itself and the
  removal test) found **zero** other importers.

Result: removal test passes; the file is now 27/27, and all `test_wow*` suites
stay green (360 passed in the clean-room sweep that included this deletion).

**Apply reminder (repeat of the ⚠ at top):** the zip can't carry a deletion —
`Remove-Item parser\admin_fp_commands.py` after extracting.

## 13 — Finding (NOT fixed here): fresh CW builds are blocked — `TD.CW_BUILD_EXIT_COLLISION`

While diagnosing the other carried-forward baseline failure
(`test_cw_no_test_character`), I found it's not a test-count issue — it **errors
in its fixture** because the **CW world build fails validation at HEAD**:

```
Room 40 (outskirts_eastern_gate): direction 'east' is claimed by 2 exits:
  ['back from room 41', 'back from room 44']
```

(`data/worlds/clone_wars/planets/tatooine.yaml`, the outskirts `exits:` block.)
It's the **sole** blocking error (29 non-blocking warnings remain), and it
**reproduces on pristine HEAD** — independent of this session's work.

**Severity.** At boot, `game_server.auto_build_if_needed` swallows the build
`RuntimeError` into a `log.warning`, and `backfill_room_slugs` is gated on
`report.ok`. So a **fresh CW deploy silently comes up with seed rooms only** (no
world content) — it does **not** crash. The existing dev DB masks this (auto-build
is skipped when the DB is non-empty), which is why it's been sitting unnoticed
behind a "baseline test failure" label. The fresh-build test catches it.

**Why I did not fix it.** The resolution is a **map-layout / cardinal-correctness
design call**, and the authored signals conflict: room 41's coords (7,3) put it
**due-west** of the gate (8,3), but its description says "Outside the city wall"
(**desert-side / east**), and the checkpoint (44) is **also** east per its text.
Grid-adjacency hints that the gate's existing direct `west`→room 8 (city, x=5)
"should" instead hit the adjacent market (41, x=7). There's no derivable ground
truth, and this is exactly the per-map cardinal-philosophy territory you decided
case-by-case on May 29–30. Guessing a direction would either contradict the
coords (worsening the cardinal-vs-geometry agreement the relayout work was
fixing) or change navigation topology — so I left it for your call.

**Options (in `TD.CW_BUILD_EXIT_COLLISION`):**
- **A — re-coord (matches description):** move room 41 to a free desert-side tile
  (e.g. SE of the gate) and set the 40↔41 exit to southeast/northwest so coords +
  direction + description agree.
- **B — ordinal deconfliction (keep coords):** give 40↔41 a free ordinal (e.g.
  gate `southeast`→market). Resolves the collision; worsens cardinal-vs-coord
  agreement.
- **C — re-route the west corridor:** gate `west`→market (adjacent), market
  `west`→city, instead of the gate jumping straight to room 8. Changes topology.

**Verification once chosen:**
`python -c "from engine.world_loader import load_world_dry_run as L; print(L('clone_wars').report.ok)"`
must print `True`, and `tests/test_f1d_era_switch.py` (incl. `test_cw_no_test_character`,
which then asserts exactly 1 built character) must pass.

This finding is recorded in `TODO.json` (`TD.CW_BUILD_EXIT_COLLISION`, HIGH) and
v51 §1.3 (the `test_cw_no_test_character` line, reframed from a vague baseline
failure to this diagnosed root cause). No code shipped for it — it's a
decision-ready writeup, not a guess.
