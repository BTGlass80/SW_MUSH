# HANDOFF — T3.20 State-Preservation / Safe-Migration Audit (pre-build spec)

> ## ⚠️ POINT-IN-TIME — audited ~commit `d0c2353`. MAY BE SUPERSEDED.
> Read-only pre-build audit. Re-verify file:line against HEAD before building. **LIVE
> COLLISION: `engine/character.py` is dirty in the session RIGHT NOW** — both T3.20 target
> files (`character.py`, `db/database.py`) are hot, heavily-shared core. Coordinate; do not
> assume a clear surface.

## TL;DR — the foundation is SOUND, but 2 real launch-blockers + 1 small build remain

Audited the schema-evolution mechanism, the drops-28-43 additive-field backfill risk, the
character save/load round-trip, and world-state persistence. Risk tally: **23 OK, 2
LAUNCH-BLOCKER, 3 HIGH, 10 MEDIUM, 5 LOW.** The good news first: the spine is solid; ~80% of
T3.20 is already done.

## ✅ What's already safe (no build needed)

- **A real numbered migration system EXISTS** (`db/database.py:1471-1525`): `MIGRATIONS` dict,
  v2–v43, applied in order gated by `from_version`, each run exactly once, re-run-safe on
  duplicate-column. New columns on existing tables go via `ALTER TABLE ADD COLUMN` inside
  numbered migrations — **NOT** the `CREATE IF NOT EXISTS` trap (that only builds fresh tables).
  *(My earlier quick grep missed this — the deep audit corrected it; there is no "build a
  migration framework" deliverable.)*
- **All drops-28-43 additive fields survive on a pre-existing save — verified per field.**
  Chain `kind`, `active_questline`/questline slot, `completed_steps`, `step_combat_kills`, zone
  `threat_band` (defaults to SETTLED), encounter `min_band`/`max_band` (defaults 1..4) — every
  read uses `.get()/getattr` defaulting. Zero additive field needs a backfill. So the "launch =
  whole backlog to avoid post-launch state surgery" rationale **holds at the schema level.**
- The one destructive migration (v33 mail rebuild) copies data via `INSERT...SELECT` before
  `DROP`. The `save_character` writable-column allowlist (`database.py:1815-1817`) hard-stops
  writing `force_sensitive` or any unknown column (a free integrity guard, and it enforces the
  CLAUDE.md "force_sensitive is never a save_character kwarg" invariant).

## 🔴 LAUNCH-BLOCKERS (both verified at HEAD — a live save that can't load right)

**BLOCKER 1 — corrupted dice value → character CANNOT LOG IN.** `engine/character.py:766,769,782`
call `DicePool.parse()` **unguarded**, while the adjacent `json.loads` calls (lines ~758-763,
775-780) ARE wrapped in try/except — an inconsistency, not a design choice. `dice.py:42`
`text.strip().upper()` throws AttributeError on `None`; `int(...)` at `dice.py:49+` throws
ValueError on garbage like `"4X+2"`. A single corrupted skill/attribute string in one row makes
`from_db_dict` raise → that character cannot log in at all. **Worst class of launch bug.**
*Fix (~15 lines):* a `_safe_pool(raw, char_id, field)` helper — try/except (ValueError,
AttributeError, TypeError), log a warning with char id + field, fall back to `DicePool(0,0)`.
Mirror the existing json.loads guard pattern.

**BLOCKER 2 — silent Force downgrade.** `force_sensitive` is derived from control/sense/alter
keys (`character.py:767-770`), correctly NOT a DB column. If the attributes JSON is malformed,
the load falls back to `attrs={}` and reconstructs `force_sensitive=False` **with no error** — a
path-committed Jedi silently becomes non-Force on that login. There's also no backfill for Force
characters created before the derivation existed. *Fix (~10 lines read-side):* if the row carries
a committed-Force marker but parsed attrs lack control/sense/alter, emit a LOUD warning (and,
per a Brian call, likely fail-safe to `force_sensitive=True` for a path-committed Jedi rather
than silently downgrade).

## 🟡 The ONE genuine net-new build in T3.20: an idempotent data-backfill runner

The migration framework is **DDL-only** — it genuinely cannot express the Force-attribute
backfill (blocker 2 write-side). T3.20's only real plumbing: a one-shot, idempotent
engine-layer backfill pass run after `DB.initialize()` (alongside the existing housing/titles
`ensure_schema` calls in `game_server.py`), with a marker so it runs once. First job: for every
character whose path/template implies Force-sensitivity but whose attributes lack
control/sense/alter, call the existing idempotent Force-attribute seeder. Needs a **v44
migration** for the marker table — **coordinate the next free SCHEMA_VERSION integer with the
session** (see collision).

## Build spec (ordered)

1. **Blocker-1 guard** — `_safe_pool` helper + 3 call-site swaps in `character.py`. Cheap, highest value, do first.
2. **Blocker-2 read guard** — warn-don't-silently-downgrade in `character.py` (+ Brian: fail-safe to Force?).
3. **Backfill runner** — the new idempotent subsystem + v44 migration (the only real build).
4. *(optional, low-pri)* v33 crash-window idempotency hardening.

## Cheap-now vs build-later

~80% is cheap guards on a sound base (blockers 1 & 2 are localized try/except in ONE file;
additive fields already safe; the allowlist is a free guard). The only true build is the
backfill-runner (step 3).

## 🔴 Collision note (elevated — LIVE right now)

`engine/character.py` is **dirty in the session at audit time**, and `db/database.py` is the
single most-shared core module (60 tables, the MIGRATIONS dict, save_character, the writable
allowlist). Specific hazards: (1) the backfill's **v44 migration collides on the version number**
if any other in-flight drop also bumps SCHEMA_VERSION — claim the next integer in coordination.
(2) Editing `from_db_dict`'s parse block risks merge conflicts with any drop touching attribute/
skill/equipment deserialization. **Mitigation:** land T3.20 as its own branch, keep `character.py`
edits surgical (a helper + call-site swaps, not a `from_db_dict` rewrite), and confirm no other
open branch is mid-flight on `database.py` migrations or the writable allowlist before merging.
Do NOT regress the force_sensitive-not-a-kwarg invariant while adding backfill writes.

*Full 43-finding audit in workflow task `wfexi5c4r.output`.*
