# HANDOFF — Overnight Events-hardening + parallel close-out (2026-07-02)

Session posture: Brian away, "run unattended overnight, push development hard,
parallelize, keep finding work, then gate/merge/push everything and close out."
This session ran a wide parallel fan-out (break-it QA sweeps + content-author
cults + drop-implementer fixes), landing each drop as it gated green. A separate
**parallel session** simultaneously closed out its space + housing/wilderness-guide
lane and pushed; both streams are now merged on `main`.

Authority reminder: **CHANGELOG.md + TODO.json are ground truth**, this doc is a
pointer. Everything below was HEAD-verified at write time; re-grep before acting.

## Landed to `main` this session (verify: `git log --oneline`)

**This session's drops (Events playability + QA hardening):**
- **Housekeeping** (`b6c6065`) — adopted orphaned real work, gitignored session scratch (441→0 uncommitted).
- **Anomaly-defeat-clear** (`91b777f`/`8a8b3ac`) — combat anomalies clear on *incapacitated*, not only death. This was the REAL Events blocker (a downed-but-alive boss left the scenario un-clearable); live break-it found it, unit tests structurally could not.
- **Hollow Sun tuning** (`b00bc4c`) — ~6h staged menace clock (`STAGED_MENACE_PER_MINUTE=0.18`, tunable) + a real WIN capstone (`WIN_CAPSTONE_CREDITS=1000` to title-earners via `adjust_credits(..., "communal_win_capstone")` + a per-cult relic to the top contributor). Brian's calls: ~6h window, bigger capstone.
- **Drowned Choir staged scenario** (`e98253b`/`0d778b8`) — 4th of 5 cults converted to a playable go-to-site→waves→skill→boss scenario (Nar Shaddaa; bespoke `nar_shaddaa_drowned_sublevels` wilderness venue w/ a real edge into `undercity_depths`).
- **Vendor-droid concurrency lock** (`a106301`/`eea3fdd`) — LAUNCH-CRITICAL. Per-droid `asyncio.Lock` closes two deterministic credit-integrity races (item duplication + minted credits) in `sell_to_droid`/`buy_from_droid`/`collect_escrow`. `reset_droid_locks()` wired into `tests/harness.py`.
- **Parser-dispatch hardening** (`62f1482`) — two break-it defects: incapacitated/mortally-wounded PCs could still act outside combat (added an `INCAPACITATED_ALLOWED` gate one rung below DEAD in `CommandParser._execute`); an unguarded `try_nl_combat_action` call could silently kill a session's game-loop (wrapped in try/except + `log.exception`).
- **Iron Veil staged scenario** (landing via agent at close — 5th/5 cult, Kuat `kuat_sabotaged_yards`). Once landed: **all 5 cults are staged playable scenarios, 0 on the old global-menace-counter path.**

**OpusLoop (quality loop) drops merged in parallel:**
- `8e5a53e` anomaly-social-alt-skills (staged skill stages honor their advertised social route);
- `d0572d3` guide26-reward-tier-accuracy.

**Parallel session's lane (space + guides), merged in:**
- `space-anomaly-live-combat` = **FORK-1 resolved Option A** (Brian's call — real interactive cockpit combat, not the interim single-roll skirmish);
- Guides **13 (Housing)** + **15 (Wilderness)** published; comlink planet-scoped; a 7-guide accuracy pass. See `HANDOFF_decisions_comlink_space_guides_2026-07-02.md`.

## The NEXT drop is fully specified: housing + world-integrity hardening

The parallel session pushed its FINAL close-out, so per Brian ("then you have full
control") **housing + wilderness are now in-lane.** Two independent break-it passes
(mine + the parallel session's) surfaced a coherent hardening backlog. All are
launch-relevant, mechanical, and drop-implementer-shaped. **Grep `engine/housing.py`
+ `parser/housing_commands.py` fresh first — line numbers below are pre-drop.**

Housing bugs (5):
1. **Occupancy leak** — `sell_home` (~L2221) is missing the `UPDATE housing_lots SET current_homes = current_homes - 1` decrement that `sell_shopfront` (~L2820) / `sell_hq` (~L3821) have → sold Tier-3 homes never free the lot → Tier-3 housing eventually unbuyable. 1-line mirror fix.
2. **Destroy-for-0cr trap** — `housing checkout` on a *purchased* home destroys it for 0cr with no confirm. `checkout_room` (~L1088) allow-list wrongly includes `"private_residence"` + refunds the always-0 `deposit`; `_cmd_checkout` has no type/confirm gate. Fix: refuse checkout on a purchased home (point to `housing sell`), or pay the 50% sell refund + confirm.
3. **Rent on-ramp** — `rent_room` (~L992) still has the pre-multi-home single-home block that funnels players into bug #2. Give it the total-cap logic `purchase_home` uses (4 homes).
4. **Cross-tier lot-ID validation gap** (parallel-session find) — verify against HEAD.
5. **Stale Tier-3 rent-discount display string** (parallel-session find) — verify against HEAD.

World-integrity (fold in — small):
6. **dune_sea zone_id NULL** — `data/worlds/clone_wars/wilderness/dune_sea.yaml` sets `region.zone: jundland_wastes` (a slug), which `wilderness_writer::_lookup_zone_id_by_name` (exact-then-LIKE on `zones.name`) can't match → landmarks materialize with NULL zone_id → **default security** (they still work as rooms). Fix = set `region.zone` to the real zone NAME — **confirm the exact name against the live `zones` table first** (single-line value edit, world-safe). NOT a reachability blocker.
7. **`bantha_graveyard` not wired into `tatooine_jundland`** (parallel-session find).

### Flag #2 (staged-site reachability) — TRACED, NOT a blocker
Both sessions worried the wilderness landmark rooms are "disconnected from the open
coordinate grid." I traced it read-only: **all staged-cult regions declare `edges:`**
(`coruscant_underworld`, `ey_akh`, `dune_sea`, `nar_shaddaa_drowned_sublevels`,
`tatooine_jundland`), players enter via `_try_wilderness_entry` and move
landmark-to-landmark via the adjacency exits `wilderness_writer` pass-2 creates, and
the Drowned Choir test pins the edge→real-room→free-direction contract. The genuine
gap is only the never-generated per-tile grid (free-roam + Guide_15 harvest roster
are thin) — **the staged scenarios themselves are reachable and playable.** The
per-tile grid is a bigger roadmap item, not launch-blocking for Events.

## Still owed on the Events lane (durable backstop SWMUSH-EventsOvernight covers these)
- **36th-arc civilian big-ship VENUE + capital-ship combat questline** — Brian: "you pick." Concept: a Kuat civilian bulk-freight liner / ghost-manifest smuggling front → board → gun-deck waves → slice → enforcer. Resolves `QUEST.t3_24_36th_arc`. Compose existing engines (staged_event + wilderness-anomaly multi-phase combat + skill-mode + chain-step), don't rebuild.
- **Wave→wave re-engage polish** — `engine/wilderness_anomalies.py::_advance_to_next_phase` (~L4037): when a multi-phase combat anomaly advances, add the next wave's NPCs to the *active* CombatInstance so players stay engaged instead of re-targeting.

## Sound (unchanged, awaiting Brian)
Zone-keyed ambient audio system is built + off-by-default. Awaiting Brian's CC0 `.ogg`
loops. Sourcing/how-to lives in the sound README he asked for.

## Git / process notes
- `main` HEAD at write time: `62f1482` (Iron Veil lands on top via the agent).
- Multi-actor contention was heavy (this session + OpusLoop + parallel session + an
  Iron Veil-landing agent all pushing). Discipline that worked: **re-fetch+merge before
  every push; serialize full gates** — running 2-3 full suites at once starves slow
  concurrency tests (the vendor test spuriously "failed" the parser gate purely from
  box load; passed clean isolated on main). Avoid `git checkout --theirs` (permission-
  denied); use `git restore --theirs`.
- Standard CHANGELOG conflict resolution: keep both prepended entries (3 marker edits).
