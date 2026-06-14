# HANDOFF — Session 2026-06-13 (Director scope + workflow rules)

> **FRESH-CHAT PICKUP POINT.** `main` = `origin/main` = **`4f175b0`** (in sync,
> all pushed). `design_calls_pending_brian` is EMPTY (confirmed HEAD:TODO.json).
> CHANGELOG.md and TODO.json are already updated in the committed drops — record
> is complete, nothing to reconcile.
> Author: Claude Sonnet 4.6 (handoff-writer agent), 2026-06-13.

---

## TL;DR

Four drops landed on `main` (commits `0b17164`..`4f175b0`), completing: the
Director's native CW faction axis + 34-zone load, the adaptive-spend governor
slice 1, two T3.20 character-load safety fixes, and the Director's economy-eyes
perception layer. Full suite clean at HEAD (9171 pass, 2 not-mine/not-real
strays). No open design calls. The next session's queue is unblocked.

---

## Drops shipped (oldest first)

### 0b17164 — Director multi-zone "living galaxy": native CW faction axis + 34-zone load

Resolved design calls `DIRECTOR.zonestate_cw_faction_axis` (Brian Option A) and
`DIRECTOR.multizone_living_galaxy`.

The pre-drop bug: `ZoneState` hardcoded GCW attributes (`imperial`/`rebel`/
`criminal`) as dataclass fields; `set_faction("republic", 80)` silently orphaned
the value while `compute_alert()` read the stale `imperial=50` default, so every
CW zone computed the same wrong alert. `VALID_ZONES` was 6 hardcoded Mos Eisley
keys that did not match the CW config keys at all.

What landed (all in `engine/director.py`):

- `ZoneState.scores` (`engine/director.py:293`) — faction-agnostic `dict` keyed
  by the era's `VALID_FACTIONS` (CW: `republic/cis/jedi_order/hutt_cartel/
  bhg/independent`). The GCW-named dataclass fields are gone.
- `ALERT_AXIS` (`engine/director.py:177`) — era-resolved role map (`authority` /
  `warfront` / `underworld`) populated from the runtime config's `rewicker_factions`
  block (CW: `authority=republic`, `warfront=cis`, `underworld=hutt_cartel`).
  `compute_alert()` (`engine/director.py:304`) reads `scores` through these
  role keys, so alerts reflect real era influence. The `imperial/rebel/criminal`
  strings in `ALERT_AXIS` are zone-tone AXIS keys (sanctioned do-not-touch
  surface per CLAUDE.md); the mapping layer at `_GCW_TO_CW_FACTION`
  (`engine/director.py:~200`) is separate and handles faction-order normalization
  only.
- `VALID_ZONES` (`engine/director.py:148`) — now `frozenset(DEFAULT_INFLUENCE.keys())`,
  derived from the runtime era config's `zone_baselines`. In CW that resolves to
  34 zones (VERIFIED at HEAD: `len(VALID_ZONES) == len(DEFAULT_INFLUENCE) == 34`
  at runtime; pinned by `tests/test_director_living_galaxy.py::test_valid_zones_is_the_full_config`).
- All consumers re-keyed: digest, HUD, `@director`, security overlay, mission
  spawn bias all read through `ALERT_AXIS` role keys or `ZoneState.get_faction()`.

New test file: `tests/test_director_living_galaxy.py` (184 lines).
Also updated: `engine/missions.py`, `engine/security.py`,
`parser/director_commands.py`, `server/session.py`,
`tests/test_director_cw_faction_mapping.py`.

### e05fe4c — Director adaptive-spend governor slice 1: skip-empty-turns + auto cadence

Resolved `DIRECTOR.adaptive_spend` slice 1 design decisions D (skip-empty-turns
with overnight catch-up exception) and E (auto cadence escalation bounded by a
$30 ceiling).

What landed (all in `engine/director.py`):

- `FIDELITY_INTERVALS` (`engine/director.py:55`) — tier-to-seconds map (`eco`,
  `standard`, `high`, `max`).
- `Director._manual_fidelity` (`engine/director.py:449`) — `Optional[str]`; `None`
  = auto mode; set to a `FIDELITY_INTERVALS` key for manual override (slice 2 will
  surface the setter via `@director fidelity <tier>`).
- `Director._should_skip_turn()` (`engine/director.py:2007`) — evaluates whether
  a faction turn should be skipped (empty server + no catch-up window needed).
- `Director._apply_governor()` (`engine/director.py:2029`) — auto-escalates
  `self._turn_interval` toward `FIDELITY_INTERVALS["high"]` on high-ROI windows,
  bounded by the $30 auto ceiling; respects `_manual_fidelity` when set.
- `Director._governed_turn()` (`engine/director.py:2071`) — wraps the faction turn
  loop, calling `_should_skip_turn` and `_apply_governor` on each tick.
- `Director._count_online()` (`engine/director.py:1999`) — static helper.
- `Director.governor_state` property (`engine/director.py:2058`) — snapshot dict
  for `@director status` / telemetry.

New test file: `tests/test_director_adaptive_spend.py` (194 lines).

### 5f93534 — T3.20 safe character-load: guard attrs parse + Force-sensitivity fail-safe

Closed 2 launch-blockers in `engine/character.py::from_db_dict`.

**BLOCKER 1** (`engine/character.py:868`): the attribute-parse loop and
force-attribute loop now each wrap `DicePool.parse()` in individual
`try/except (ValueError, TypeError, AttributeError)`. A single corrupted attribute
value (e.g. `"4X+2"`) logs a warning and skips that field; it no longer raises
and aborts the entire character load, which had been locking players out on login.
The skills-loop guard (landed in an earlier drop) already existed; this drop
extends the same pattern to the attributes and force-attrs loops.

**BLOCKER 2 / `FORCE.sensitivity_failsafe_to_jedi`** (`engine/character.py:890`):
a path-committed Jedi (any `village_chosen_path` in `{"a","b","c"}`) with a
corrupt or pre-derivation attributes JSON blob previously reconstructed as
`force_sensitive=False`, silently stripping Force access on that login.
The fix: after the attrs loop, if `char.force_sensitive` is still `False` and
`village_chosen_path` is a committed path, set `force_sensitive=True` and emit a
loud `log.warning`. `force_sensitive` is derived state and is never written back
(save_character allowlist already blocks it), so this re-asserts safely on every
load. The read-side guard is complete; the idempotent Force-attribute backfill
RUNNER (write-side) is deferred — see next-up queue below.

New test file: `tests/test_t3_20_safe_load.py` (108 lines).

### 4f175b0 — Director economy-eyes: faucet/sink digest perception (pure read)

Added `Director._compile_economy_digest()` (`engine/director.py:1516`).

Pure-read rollup of `credit_log` (the `adjust_credits` funnel writes tags there)
over a configurable window (default 30 minutes). Returns compact macro signals:
`total_faucet`, `total_sink`, `net_flow`, `transactions`, `top_faucets` (top-5
sources by volume), `top_sinks` (top-5). Result is surfaced as
`digest["economy"]` (`engine/director.py:699`) in the per-turn digest the
Director LLM receives. Explicitly perception-only — this drop does not act on
the economy data; opportunity nudges are the next step (see queue).
Fail-open: returns `{}` if `credit_log` is absent or query fails.

New test file: `tests/test_director_economy_eyes.py` (117 lines).

---

## State of main

- `main` = `origin/main` = `4f175b0`. All 4 drops pushed. CHANGELOG.md and
  TODO.json updated in each drop's commit.
- Full suite at HEAD: **9171 passed, 2 not-mine/not-real strays** (same baseline
  as the previous handoff):
  1. `test_smoke_chain_walkthrough[republic_soldier]` — ordering flake under
     shared multi-file run; passes solo (1 passed in 13s). Not a regression.
  2. `test_no_silent_except_pass_in_production` / `test_session38` — flags
     `except: pass` blocks in untracked parallel-session lore-ingest tools
     (`tools/ingest_batch.py`, `tools/ingest_lore.py`). Not this session's code;
     clears when that session finishes. The test also reports any untracked
     `tools/ingest_*.py` as absent from the clean worktree.
- No regression attributable to any of the 4 drops above.

---

## Workflow rules in effect (carry forward)

Two rules established this session; the next session must respect both.

**Rule 1 — Full suite FOREGROUND only.**
Run the full suite as:

```
python -m pytest tests/ -n auto --dist loadscope -p no:cacheprovider \
  --continue-on-collection-errors -o addopts="" --maxfail=200 -q
```

with `timeout:540000` (9 min). NEVER background with `&` then await — a detached
process is not harness-tracked and the session hangs. Strip any `-x` in
`pytest.ini` before running (it defeats `--maxfail=200`).

**Rule 2 — Per-session git worktrees.**
Each concurrent session works in its own `git worktree` off main. Drive a
non-default worktree via `git -C <path> <cmd>` or absolute paths. This session's
worktree is `C:/SW_MUSH_dev` (branch `opus-wt`); the default tree `c:\SW_MUSH`
is a separate worktree on a different branch with uncommitted strays from other
sessions — do NOT analyze or commit there.

---

## Next-up queue (all unblocked; design_calls_pending_brian = [])

1. **Director step-4 soft economic NUDGES** — act on `digest["economy"]` per
   Brian decision A: opportunity seeds (caravans, rare buyers, bounties). NEVER
   touch price or yield levers directly. The perception layer (`_compile_economy_digest`)
   is live; the action layer is the next build. Lives in `engine/director.py`;
   no new seams needed.

2. **Adaptive-spend governor slice 2** — manual `@director fidelity <tier>` toggle
   (sets `Director._manual_fidelity`) + persistence across restarts + the optional
   `recommend_fidelity` advisory field surfaced via `@director status`. Touches
   `parser/director_commands.py`. Coordinate with any concurrent parser-rework
   session (the command-syntax-rework plan in memory may be live).

3. **Post-launch scaffolding sweep T3.13/14/16** — pre-launch schema/state + UI
   seams for Padawan-Master (T3.13), multi-city Cities (T3.14), and Wildspace
   (T3.16). Goal: these systems drop in post-launch without a live migration
   (the ambient-Phase-0 pattern already proven by the ambient NPC scaffolding
   drop). No gameplay logic yet — seams only.

4. **Free-LLM enrichment** — route templated surfaces
   (`wilderness_anomalies` / `missions` / `bounty_board` / `encounter_texture`)
   through local Ollama (Mistral 7B). Highest-value aliveness work per the design
   doc, and it costs nothing. Pairs well with a quiet session.

5. **T3.20 deferred follow-up — Force-attribute backfill RUNNER (write-side).**
   The read-side fail-safe (BLOCKER 2, drop `5f93534`) is live: path-committed
   Jedi load correctly even with corrupt/missing attrs. The RUNNER that
   idempotently writes the missing `control/sense/alter` keys back to the DB
   (so the warning eventually goes quiet) is still unbuilt. Low urgency pre-launch
   (the fail-safe is safe), but worth a small focused drop soon.

---

## Standing charter

Per memory `overnight-autonomy-posture`: decide+build+log, conservative balance,
features-first/harden-last, consent/defeat gates on restraints. Brian's 4 standing
calls are locked. Stop only for irreversible actions or genuine design forks. The
pending-design-calls queue is empty — the next session has full autonomy on the
items above.
