# HANDOFF — Smoke-test coverage gap & discipline restoration (2026-06-12)

## Why this exists

Brian flagged a suspicion: regression/unit tests keep landing per-drop, but the
**smoke discipline may have lapsed**. This handoff is the audit answer plus the
restoration work.

## Verdict — discipline drifted (but the suite is healthy)

The smoke **suite itself is green and earns its keep**: a full
`pytest tests/smoke/ -m smoke` run is **192 passed in ~6m03s** (one documented
`xfail`: the S12 lockon `gunner_stations`-vs-`gunners` field bug, intentionally
pinned). The harness (`tests/harness.py`, in-process `GameServer` on a temp DB,
no listeners) and the ~50–60 scenarios across 35 modules are deep and real
(DB-state seeding, credits-delta asserts, JSON-event asserts) — not shallow
"didn't crash" checks.

**But coverage has drifted.** Per-file `git log` shows the entire smoke tree is
frozen at the `big_catchup` commit (`4d0d07c`). Smoke has historically been
added in periodic **catchup batches** (commit subjects literally read
`big_catchup`, `catchup_01`, `updates3`) rather than per-drop — and the most
recent player-facing drops shipped **strong unit pins but no end-to-end smoke
driver**:

- Commissary + `tracking_fob` skill seam (Drop 13) — unit-tested only at the
  `perform_skill_check` level with a hand-built char dict; no live
  `+commissary buy → inventory → equip → search-bonus` drive.
- Market segmentation + vendor-presence buy gate (Drops 10–11).
- Gundark crafting Lane G `learn`/tuition trainer path (Drop 9) — E7 smoke
  deliberately bypasses the trainer.
- Smuggling-job destinations un-break (2026-06-01).
- Coruscant Underworld region build-out (2026-06-12, in flight).

The CHANGELOG's recurring `"Pending (Brian's Windows gate): smoke it live —"`
notes confirm these loops are being verified **manually** instead of as
automated scenarios. That is the drift.

Design intent (per `smoke_test_harness_design_v1.md` §6) was **per-drop smoke
delivery**, ~85 scenarios across SH1–SH6. The cadence lapsed; the catchup model
let recent drops outrun their drivers.

## Prioritized gap list

| # | Scenario | Pri | Loop | Status |
|---|----------|-----|------|--------|
| 1 | `mission_loop` (missions→accept→mission→complete reward→abandon) | P1 | Faction/Mission core loop — **zero** e2e coverage | **closed this pass** |
| 2 | `buy_vendor_gate` (refusal w/o vendor · success w/ vendor · stock gate) | P2 | Open-market buy gate (Drops 10–11) | **closed this pass** |
| 3 | `craft_trainer` (`learn` usage · trainer-absent refusal · paid/free lesson) | P1 | Crafting trainer lane (Drop 9) | **closed this pass** |
| 4 | `commissary_loop` (rank gate → buy → 350cr debit → inventory skill_bonus → austere-refusal negative) | P1 | Commissary + `tracking_fob` (Drop 13) | **closed (3 pass)** |
| 5 | `smuggling_loop` (board → accept → active run → deliver-refusal) | P2 | Smuggling jobs (2026-06-01) | **closed — SL3 pass; SL1/SL2/SL4 xfail (bug #2 below)** |
| 6 | `craft_quality_buyback_gate` (q≥50 refuse vs q<50 sell) | P3 | NPC buyback quality gate (2026-06-02) | **remaining** |
| 7 | `underworld_anomaly_loot` (region reachability + anomalies/loot) | P3 | Coruscant Underworld (2026-06-12) | **deferred — region in flight in a parallel session** |

### Closed this pass — verified green (`10 passed` together under `-m smoke`)

- **`mission_loop`** (4 scenarios, 31 asserts): board renders → `accept` makes
  the mission active (`mission` shows title/objective) → `complete` pays the
  reward (`get_credits` after > before) → `abandon` returns it to the board.
  Space-mission completion (PATROL/ESCORT/INTERCEPT/SURVEY_ZONE) deferred —
  needs a launched ship in a target zone (space-flight harness), not an
  assertion weakness.
- **`buy_vendor_gate`** (3 scenarios, 15 asserts): refusal with no vendor
  (credits unchanged) → success with a seeded vendor NPC (credits decrease) →
  stock-gate refusal for contraband even with a vendor present.
- **`craft_trainer`** (3 scenarios, 17 asserts): `learn` usage → trainer-absent
  refusal → free/paid lesson with the schematic becoming known and tuition
  debited (Gundark / `anti_vehicle_grenade` / 375 cr).

No `pytest.skip`/`xfail`; all hard-fail assertions; no existing test flipped.

### Closed this pass — batch 2 (P1/P2): `4 passed, 3 xfailed`

- **`commissary_loop`** (3 scenarios): rank-1 BHG member sees `tracking_fob` →
  `+commissary buy` debits exactly 350 cr and lands the item in the inventory
  blob with its `skill_bonus` dict intact → `jedi_order` austere-refusal with no
  debit. Legitimate seeding (a real member *has* a rank-1 `org_memberships`
  row); strong assertions; no masking.
- **`smuggling_loop`** (4 scenarios): SL3 (`smugdeliver` docked-ship gate) is a
  real pass; SL1/SL2/SL4 are honest **`xfail`** documenting bug #2 (driven
  faithfully, no workaround — they XPASS when `current_room` is wired). This is
  deliberately *not* seeded-to-green: that would falsely report a broken loop as
  working.

## Bug surfaced by `mission_loop` (CONFIRMED — needs a separate fix + a design call)

The new mission smoke immediately surfaced a real **silent DB-persistence
no-op** — exactly the cross-system wiring class smoke exists to catch. The
in-memory board generates **string** mission ids (`engine/missions.py:404-405`,
`"m-"+uuid`), but `accept_mission` / `complete_mission` / `abandon_mission`
(`db/database.py:2498-2523`) run `UPDATE missions … WHERE id=?` against
`missions.id INTEGER PRIMARY KEY AUTOINCREMENT` (`db/database.py:117`). A string
id never equals an integer PK → **0 rows updated, silently**. The live server
runs off the in-memory board singleton, so a single session behaves correctly;
but accept/complete/abandon is **never persisted**, so a restart drops the
active mission (`get_active_mission` keys on `accepted_by`, which was never
written). NOT fixed here (scope = smoke coverage), and it carries a design fork:
is DB persistence even wanted given the board is the in-memory source of truth,
or should the dead DB calls be removed? → Brian's call. The scenario
deliberately mirrors the in-memory board and does not depend on the broken path.

## Bug #2 surfaced by `smuggling_loop` (CONFIRMED — smuggling board unreachable in prod)

A second, more serious latent bug. `_in_board_room`
(`parser/smuggling_commands.py:38`) reads `ctx.session.current_room` — an
attribute that is **never assigned anywhere** in server/, parser/, or engine/
(verified: every other room-gated command reads `char["room_id"]`; nothing ever
sets `session.current_room`). Accessing it raises `AttributeError`, which the
dispatch wrapper catches and renders as "An error occurred…". Net effect:
`+smugjobs` / `smugaccept` **always error in the live server — the smuggling
board is unreachable.** It went undetected because the loop was only ever
"smoke-tested live, later" (a recurring CHANGELOG "Pending" note) — the precise
failure mode this work targets.

Handling: `mission_loop` was committed seeding around its bug only because the
in-memory board is genuinely how the live server governs that state. The
smuggling bug is different — `current_room` is supposed to exist at runtime and
doesn't — so seeding it would test a path production can't reach and report a
false "smuggling works". Instead, `smuggling_loop` SL1/SL2/SL4 are driven
faithfully and marked **`xfail`** (matching the S12-lockon precedent): they
document the bug, keep the suite green, and **XPASS the moment `current_room` is
wired** (then remove the marks). SL3 (`smugdeliver` docked-ship gate) is
independent of the bug and is a real passing test.

Fix (Brian's call — a design fork): either set
`session.current_room = await db.get_room(char["room_id"])` in the dispatch loop
before command execution (helps any future command that wants the room object),
or rewrite `_in_board_room` to use `char["room_id"]` + a DB lookup like every
other gated command. Not fixed here (scope = smoke coverage).

## Root-cause fix — stop the drift, don't just patch it

The new **`smoke-verifier` agent** (`.claude/agents/smoke-verifier.md`, added
this session) is the mechanism to restore per-drop discipline: it runs
`pytest tests/smoke/ -m smoke` in-process and is now part of CLAUDE.md's drop
verify fan-out (step 3). The standing rule to re-establish:

> A drop that adds a **player-facing command/loop** ships its smoke scenario in
> the same drop — not in the next catchup. If the loop can't be driven
> deterministically yet, log the deferred arm here rather than leaving it to a
> manual "smoke it live" note.

## Harness authoring quick-reference (for the remaining scenarios)

- Scenario: `async def <name>(h):` in `tests/smoke/scenarios/<file>.py`; test
  entry `tests/smoke/test_smoke_<file>.py` with `pytestmark = pytest.mark.smoke`
  and `await <file>.<name>(harness)`.
- `s = await h.login_as("Name", room_id=, credits=, skills={...})`;
  `char_id = s.character["id"]`; `out = await h.cmd(s, "...")`.
- Seed: `await h.db.save_character(char_id, attributes=/inventory=/equipment=/faction_id=)`
  then `s.character = await h.get_char(char_id); s.session.invalidate_char_obj()`.
- NPC seed: engine `create_npc(...)`; or query the `npcs` table like
  `scenarios/ground_combat.py`. Equipment: `engine.items.write_equipment`.
- **Always** run with `-m smoke` (the suite default `addopts` deselect filter is
  `-m "not smoke and not smoke_slow"`; without `-m smoke` you get a false
  "0 selected" green). Never `pytest.skip` to dodge a hard arm.
