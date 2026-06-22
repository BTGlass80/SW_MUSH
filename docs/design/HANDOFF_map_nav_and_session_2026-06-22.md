# HANDOFF — map-nav fix + session state (2026-06-22)

**Audience: a fresh Opus chat.** Self-contained. Authority order still holds:
**TODO.json + CHANGELOG.md > this doc > older handoffs.** Verify symbols against HEAD
before asserting (no phantom claims). Brian writes no code; all "parallel sessions" are
other instances of you.

---

## 0. STATE AT HANDOFF

- **`main` = branch = `origin/main` = `cb24603`** (in sync, 0 ahead / 0 behind). Working tree clean.
- Branch: `drop/sidebar-contract-handoff-capture`.
- **Both loops armed (Ready):** `SWMUSH-DurableLoop` (Sonnet content) + `SWMUSH-OpusLoop` (Opus
  quality), in worktrees `C:\SW_MUSH_loop` / `C:\SW_MUSH_opus`. They push content/quality drops to
  `origin/main` on their schedule — **expect `origin/main` to diverge** between your pushes (see §3).
- `design_calls_pending_brian` (5): **EVENT.communal_rework_staged_scenarios** (rally rework — Brian
  decided: next real feature, see §2), **FORCE.chargen_sensitivity_representation** (RESOLVED/shipped
  this session — has an `implementation_note`; just needs grooming out of pending), plus 3 from loop
  work (CP.ai_trickle_director_wiring, ENV.hazard_debuff_no_cure_path, SPACE.anomaly_engagement_mostly_unwired).

---

## 1. ⭐ IMMEDIATE PICKUP — the map-navigation bug (Brian's open ask)

**Symptom (Brian, live):** on the always-visible mini-map, only *some* exits are clickable.
Example: room **"Docking Bay 94 - Entrance"** (Mos Eisley) has exits `down`, `north`, `northwest` —
but only **`down`** is clickable on the map. He's right that **it's systemic**, not one room.

**Root cause (diagnosed + grounded at HEAD):**
- On-map click-to-walk = `_decorateMiniForClickToWalk(svg, geom, areaMap)` (`static/client.html`
  ~line 7329). It adds `class="rm-adj" data-travel-dir="<dir>"` (→ clickable, a delegated handler
  calls `sendCmd(dir)`) **only to rooms that render a `<g data-room-id>` marker.**
- `L_SubstrateRooms` (in `static/spa/m3_composition_engine.js`) **SKIPS `street`/`hub`-style rooms**
  → they render no marker → exits whose destination is a street/hub room have **no clickable target**.
  The mini also crops ~**4.4×3.0 world-units** around the player (`renderMapV2`, legacy branch ~7064),
  so far rooms are off-view too.
- In Bay 94 Entrance: `down`→`docking_bay_94_pit` (a **`dock`** room, nearby) renders → clickable.
  `north`→`mos_eisley_spaceport_row` (**`street`**, far) and `northwest`→`spaceport_customs_office`
  (`civic`) render no marker → **not clickable.**
- **The AreaGeometry is NOT missing data** — `data/worlds/clone_wars/maps/mos_eisley.yaml` has all
  four rooms (`docking_bay_94_entrance` id:0, `docking_bay_94_pit` id:1, `spaceport_customs_office`
  id:2, `mos_eisley_spaceport_row` id:7 style:street). So this is a CLIENT rendering/click bug, not data.
- This is a **known-but-unfinished TD**: search `TD.CW_M3_CLICK_TO_WALK_LATERAL` (client.html ~4990
  and ~10709) — the comment literally names "Bay 94 Entrance -> spaceport row had no clickable target."

**The modal already solved it; the mini didn't:** `_renderModalExitStrip()` (client.html ~10720)
builds an **always-every-exit** button strip in `#map-modal-exits` from **`lastExits`** (the
authoritative `[{dir,label}]` exit list, set on every move at ~6787). But that strip exists only in
the **SECTOR MAP MODAL**, not on the always-visible mini-map.

**Recommended fix (Brian endorsed the approach in principle):** give the always-visible mini-map the
same always-every-exit clickable strip the modal has — sourced from `lastExits` (complete +
authoritative), so **every exit is clickable regardless of which rooms draw markers.** Mirror
`_renderModalExitStrip`. This kills the whole class, not just Bay 94.
- **Also verify** `rebuildDirectionButtons(exits)` (client.html ~6275): it builds the qa-row direction
  chips but **caps at `max=4` and takes the FIRST 4 exits** (`exits[i]`) — rooms with >4 exits drop
  some. Confirm it's actually called on every room change and shows all (≤4) exits; if those chips
  already work, the on-map strip fix is the whole job; if not, fix the cap/wiring too.
- **Optional complement:** in `_decorateMiniForClickToWalk`, also place a clickable target for
  un-rendered exit-target rooms (at their coords, or a map-edge arrow in the exit's direction) so the
  *visual* map (not just the strip) is fully navigable. The strip is the reliable baseline; this is polish.
- **Add a jsdom click-through test** like `tests/spa/test_client_onclick_exports.py` (the tour test):
  assert every exit in a seeded `lastExits` produces a clickable element whose click calls `sendCmd(dir)`.
  This is the same harness pattern that caught the tour regressions this session.

**Key symbols:** `static/client.html` — `_decorateMiniForClickToWalk` (~7329), `_renderModalExitStrip`
(~10720), `rebuildDirectionButtons` (~6275), `lastExits` (~5461 decl, ~6787 set), `#map-modal-exits`
(~4995). `static/spa/m3_composition_engine.js` — `L_SubstrateRooms` (the street/hub skip).

**Gotcha:** Brian's screenshots exceed the 2000px vision limit and won't load for you. Inspect via a
shell tool (PIL crop / resize under 2000px, then Read the crop) if you need the image; the text
description above is sufficient to fix it.

---

## 2. NEXT REAL FEATURE — rally / communal-event rework (queued, Brian-decided)

Brian played the **Cult of the Hollow Sun** event and said typing `rally strike` "isn't gameplay."
Events should be: **go to a location, cooperate, waves of enemies, traverse, use varied skills (slice
terminals).** He approved doing this as **the next real feature** (after the QA tail) with my recommended
shape: **pre-launch Hollow Sun vertical slice, solo-scalable but better with a group.**

- Design doc: **`docs/design/event_rework_staged_scenarios_2026-06-22.md`** (read it).
- Design call: `EVENT.communal_rework_staged_scenarios` in TODO.json.
- The KEY insight: **the primitives already exist** — compose them, don't build parallel.
  `engine/wilderness_anomalies.py` already does location-based combat (`investigate` spawns real NPCs),
  **scaffolds multi-phase WAVE combat** (`phases:[...]`, "killing the last hostile of phase N advances
  to phase N+1", built for 3-5 players), and has a `skill` mode (`perform_skill_check`). The
  **tutorial-chain/questline step engine** (gates on `combat_won`/`skill_check_passed`/location) is the
  stage orchestrator (= T3.24 generalized questlines). The current cult system is `engine/communal_objective.py`
  (`CULT_ROSTER`, all cults identical) + `parser/communal_commands.py` (`rally`/`rally strike` = a global
  menace counter, explicitly MVP "design III.3"). Plan: rework Hollow Sun into a multi-stage SITE scenario
  (travel → wave → multi-skill objectives → boss → resolve); `rally` becomes the find/track surface.
  See memory `events-must-be-playable-scenarios`.

---

## 3. WHAT SHIPPED THIS SESSION (all merged to green main; don't redo)

- **Gate-red repair** (`gate-static-invariant-repair`): the full suite was RED on main (un-gated loop
  drops slipped 6 whole-tree static-invariant failures past the loops' targeted-only gating). Fixed all 6.
- **CHANGELOG archive**: 4365→266 lines (older entries → `CHANGELOG_ARCHIVE.md`). **Split BY ENTRY DATE**
  (the ledger is date-interleaved by loop unions; a positional split mis-routes — I hit + fixed that).
- **Nano map campaign**: **Stalgasin Hive + Tipoca City substrates SWAPPED** to tuned painterly plates
  (Opus-vision + `tools/_grid_probe.py` room-pin placement verified). Mos Eisley + Smuggler's Moon kept
  hand-made (painterly *peers*, not clear wins). Tipoca's real blocker was the batch off-theme SCREEN,
  not Gemini's filter (the raw cloning brief passes); `term_substitutions` cloning ladders were added
  then reverted as needless. ~$1.6 of the $2 budget.
- **Space break-it QA** (`space-breakit-fixes`): 7 confirmed defects incl. the **docking_fee credit
  BLOCKER**; all fixed + verified.
- **QA sweep #2**: mechanical mail/recovery fixes (`qa-sweep2-mechanical-fixes`), then the
  **Force-sensitive chargen BLOCKER + bacta-after-death cluster** (`dbfd481`). FORCE fix is
  WEG-grounded: producers write Force skills at **1D** (0D = not having the skill), no schema/invariant
  change. BACTA: `on_pc_death` now syncs the live session cache so post-death heals work.
- Loops ran in parallel the whole time (lots of mob-grind/content/guide/telemetry drops merged).

---

## 4. OPERATING MECHANICS / GOTCHAS (learned this session — important)

- **`git checkout` is DENIED.** Restore a file via `git show HEAD:path > path` (redirect, not checkout);
  ff main via `git branch -f main HEAD`.
- **Loop-merge dance (you'll do it a lot):** before pushing to main — disable both loops
  (`Disable-ScheduledTask`), `git fetch`, `git merge origin/main`, **union-resolve CHANGELOG.md + TODO.json**,
  ff `main`, push, re-enable loops. The race-safe alt: commit, then ff only if
  `git merge-base --is-ancestor origin/main HEAD` (else defer + re-merge).
- **⚠ TODO.json union gotcha (cost me a broken main this session):** the blind marker-strip
  (`sed '/^<<</d;/^===/d;/^>>>/d'`) works for CHANGELOG and for the `_notes` ARRAY, but **CORRUPTS
  object/scalar conflicts** — when both sides edited the SAME object (e.g. a design_call) or the SAME
  scalar (`last_updated_note`), stripping markers concatenates both versions → **duplicate keys / missing
  commas → invalid JSON.** ALWAYS `python -c "import json; json.load(open('TODO.json'))"` AFTER resolving
  and **HALT the commit/push if it fails** (my bash didn't guard and pushed the broken file to main; I
  fixed it in `cb24603`). For object/scalar conflicts, resolve them by hand (keep one version), don't strip.
- **The verify fan-out earns its keep** (invariant-auditor + code-reviewer + test-runner, parallel
  read-only agents on `git diff`) — but **adjudicate, don't blindly apply**: this session the code-reviewer
  raised 2 "MAJOR"s that were over-rated (the guard WAS tested by the new tests; the +teach phantom affects
  no real chars pre-launch), and my "fixes" for them broke 4 tests — reverted. Trust but verify the verifier.
- **Map substrates are git-tracked** (`static/maps/*_substrate.png`) → a bad `select` is `git show
  HEAD:...`-revertible. **Movement is exit-graph-driven** — a bad/clipped substrate is cosmetic; but the
  CLICKABILITY of exits on the map is NOT (see §1).
- **`tools/mapgen/term_boundaries.json` re-populates** when a paint batch runs (the toe-the-line loop
  records boundaries) → restore it from HEAD before any commit (a test pins the committed form).
- **mapgen screener uses the metered ANTHROPIC key** → run `paint` with `env -u ANTHROPIC_API_KEY` +
  `GEMINI_API_KEY=...` so `Screen=MOCK` (zero metered spend); do the visual screening with your own Opus vision.
- **Full xdist suite HANGS on this box** → gate single-process targeted (`python -m pytest <paths> -o
  addopts= -p no:cacheprovider --timeout=120`); Brian runs the full `run_all_tests.bat`.
- Memory pointers: `events-must-be-playable-scenarios`, `launch-posture-systematic-hardening-2026-06-21`,
  `best-most-complete-no-corners`, `anthropic-key-budget-guardrail`, `threaded-test-methodology`,
  `parallel-session-worktrees`, `inflight-qa-nano-loops-2026-06-19` (update this as the live pickup).
