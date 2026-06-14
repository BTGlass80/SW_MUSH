# LIVE LANE MAP — concurrent sessions (2026-06-13)

> Deconfliction note for two concurrent Claude sessions on ONE codebase
> (sole dev = Brian; "parallel sessions" are both me — see memory
> `sole-developer-deconflict-with-self`). This file is the live source of
> truth for who-owns-what over the next few hours. Update it when a lane
> changes. The MAIN session owns commit/merge/push.

## Session A — MAIN (Director + combat economy track)

**MERGED to `main` + pushed — `main` = `e05fe4c` (origin updated):**
- Director multi-zone "living galaxy" / native CW faction-axis rewrite
  (`0b17164`) — resolved `DIRECTOR.zonestate_cw_faction_axis` (Brian:
  Option A) + `DIRECTOR.multizone_living_galaxy`.
- Director adaptive-spend governor **slice 1** (`e05fe4c`) — skip-empty-turns
  + auto cadence governor (`engine/director.py` only).
- Full-suite gate green (only the 2 documented not-mine strays). **Rebase /
  branch your parser work off `e05fe4c`.**

**Ordered queue + files I will be IN (AVOID these):**
1. **Armor/consumable crafted-quality → combat** (NOW) — `engine/combat.py`,
   `engine/items.py`, `engine/character.py` (+ equipment-instance migration).
   Pure engine; ZERO parser overlap.
2. **Force-sensitivity fail-safe (T3.20)** — `engine/character.py` load path
   (bundled with #1 to avoid self-collision).
3. **Adaptive-spend governor slice 2** — `@director fidelity` toggle +
   `recommend_fidelity` advisory in **`parser/director_commands.py`**.
   **DEFERRED until the parser lane is clear** (see OVERLAP) — I will NOT
   touch `parser/` while Session B is active there.
4. **Post-launch scaffolding sweep** (T3.13/14/16) — schema/state + UI seams.
5. **Free-LLM enrichment** — route templated surfaces through local Ollama.

## Session B — PARALLEL (command-syntax rework, parser)

**Lane (Brian-assigned 2026-06-13):** command-syntax normalization across
the parser — normalize `+`/`@` prefixes, add switches, kill "German word"
run-on verbs. ADDITIVE via aliases (per memory `command-syntax-rework`).
MUST precede the doc rework.

Owns: `parser/` broadly (command files + the parser/dispatch layer).

## Session C — PARALLEL (wilderness content) — DROP COMPLETE

**Lane:** wilderness encounter content — closed a No-phantom-producers bug.
Four live encounter `npc_template` refs (dewback, tusken_warrior, maze_predator,
underworld_thug) did not resolve in the creature library, so those encounters
fired narrative but spawned NOTHING (`spawn_encounter_creatures` → `[]`).
Authored the 4 faithful WEG D6 stat blocks + a global resolution guard.

**Files (all OUTSIDE A's and B's sets — zero collision):**
`data/npcs_creatures.yaml`, `tests/test_wilderness_encounter_template_resolution.py`
(new), `tests/test_lane_a_creatures_tatooine.py`, `CHANGELOG.md` (additive
prepend), `TODO.json` (appended `tier_1_active[0]` + `tech_debt[0]`; did NOT
touch `design_calls_*`).

Verified green (27 contracts+guard / 118 spawner regression / 227 smoke / e2e
spawn proof). **UNCOMMITTED** in the shared tree per "MAIN owns commit/merge/
push" — fold in at the next integration off `e05fe4c`. Flagged a pre-existing,
deliberately-deferred quirk: `TD.ENCOUNTER_COUNT_RANGE_IGNORED` (encounters
ignore their `[lo,hi]` count range and spawn the pack minimum; honoring it is a
galaxy-wide difficulty decision, not a content-drop change).

## Session D — (this session) free-LLM enrichment + era-guard — ACTIVE

**Acting MAIN for now** (owns commit/merge/push this shift; `main` = `e564a2e`,
pushed). Lane = Session A's deferred #5 "free-LLM enrichment, route templated
surfaces through local Ollama," now opened.

**Shipped (merged + pushed):** Ollama runtime era-guard — new
`engine/era_validator.py` (single-source era canon + `era_violations`/
`is_era_clean`/`ERA_PROMPT_HINT`) wired into `engine/idle_queue.py`'s 4 tasks;
`tools/ingest_lore.py` + `tests/test_laneb_era_cleanness.py` migrated onto the
shared tuple.

**Files I own this shift (AVOID — I'm actively in these):**
`engine/era_validator.py`, `engine/idle_queue.py`, `tools/ingest_lore.py`, a
forthcoming `engine/variant_pool.py` (generic keyed variant-pool pre-generator,
generalizing the bark cache), and `tests/test_era_validator.py` +
`tests/test_idle_queue_*.py` + `tests/test_variant_pool*.py`.

**Explicitly NOT touching** (other lanes): `parser/` (Session B), and the
combat-economy engine files `engine/combat.py`/`items.py`/`character.py`/
`director.py` (Session A). Enrichment surfaces that live in those files
(combat prose, mission/bounty one-liners in `parser/`) are DEFERRED until those
lanes clear — I'll only wire surfaces in files no one else owns.

## ⚠️ SHARED WORKING TREE — concurrent edits to the SAME FILE clobber
Both sessions edit ONE working tree (not isolated git worktrees). Two sessions
writing the same file = last-write-wins, **silent data loss** (NOT a git merge
conflict that warns you). So: **never edit a file the other session is actively
in.** Re-read a shared file immediately before editing (an Edit that fails with
"file modified since read" means the other session touched it — re-read, don't
force). Lanes above are split by file ownership precisely to avoid this.

## OVERLAP — `parser/director_commands.py` (PAUSED)

Session A's only parser need is adaptive-spend **slice 2** (`@director
fidelity` + advisory), which is now **DEFERRED** (queue #3). So for now
**Session B owns `parser/director_commands.py` outright** — normalize it
freely. Before A starts slice 2 it will (a) confirm B is done with that file
via this note, then (b) build on B's normalized version. No concurrent
editing of it.

## Shared high-churn files (both append; never overwrite)
- `CHANGELOG.md` — prepend your own dated entry; don't reflow others'.
- `TODO.json` — edit your own keys; A owns `design_calls_*`. Re-read right
  before editing; validate JSON parses before committing.

## No blockers
`design_calls_pending_brian` is EMPTY. API path / SSL / cost telemetry live.
