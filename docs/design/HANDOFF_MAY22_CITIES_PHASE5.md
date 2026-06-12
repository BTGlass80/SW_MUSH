# HANDOFF — cities_phase5 (Player Cities v1.2 Phase 5)

**Drop:** `cities_phase5`
**Date:** May 22 2026
**Design source:** `player_cities_design_v1_2.md` §6 (citizen
benefits), §13 Phase 5
**Architecture:** v47 (Tier 2 #4 — Player Cities v1.2
implementation, session 6 of ~10.5–11.5)
**Prereqs:** cities_phase1 + cities_phase2 + cities_phase3 +
cities_phase4 + cities_phase4b applied.

---

## TL;DR

**Citizen benefits shipped: rest-bonus read seam, security upgrade
for citizens in contested/lawless city rooms, citizen-only room
gating with 30%-cap on non-HQ rooms, and `+city home` teleport
with 1-hour cooldown.**

- `engine/player_cities.py` (MODIFIED, +~310 LOC) —
  Phase 5 constants (`CITY_HOME_COOLDOWN_SECONDS`,
  `CITIZEN_ONLY_MAX_FRACTION`), 8 new functions
  (`is_citizen`, `is_rest_bonus_room`,
  `can_enter_city_room`, `_get_last_city_home`,
  `_set_last_city_home`, `get_city_entry_room_id`,
  `can_use_city_home`, `record_city_home_use`).
  `set_room_citizen_only` modified to enforce the 30%-cap
  on non-HQ rooms (Phase 3 shipped the flag write but
  deferred the cap; HQ rooms are exempt per design §6.3).
- `engine/security.py` (MODIFIED, +~50 LOC) — new
  `_apply_city_upgrade` (contested→SECURED for citizens,
  lawless→CONTESTED for citizens), appended to the
  `_finalize` chain AFTER faction-override and claim-upgrade
  so the city upgrade is the most-permissive last word
  for citizens inside their own city.
- `parser/builtin_commands.py::MoveCommand::_check_exit_gates`
  (MODIFIED, +~15 LOC) — appended `can_enter_city_room`
  gate after the conditional room-lock gate. Fail-soft per
  design §6.3 ("cities are public spaces by default").
- `parser/city_commands.py` (MODIFIED, +~80 LOC) — `home`
  moved from placeholder branch to live dispatch; new
  `_handle_home` method (gate via `can_use_city_home`,
  perform teleport, stamp cooldown, trigger look — parallel
  to `housing_commands._go_home`); bare-help updated;
  module docstring updated.
- `tests/test_cities_phase3.py` (MODIFIED, 1 test re-purposed)
  — `test_home_still_phase_5` → `test_home_subcommand_shipped_in_phase_5`
  (pinned-keyset, 6th consecutive drop).
- `tests/test_cities_phase4.py` (MODIFIED, 1 test re-purposed)
  — `test_home_still_phase_5` → `test_home_subcommand_shipped_in_phase_5`.
- `tests/test_cities_phase5.py` (NEW, ~1100 LOC, 34 tests
  across 30 sections).

**Tests:**
- **New suite: 34/34 green** in sandbox
- **Phase 1 + 2 + 3 + 4 + 4b + 5 combined: 280/280 green**
- **Adjacent regression** (security + movement gates):
  **170/170 green when combined**
- **All touched surfaces combined: 450/450 green**

---

## Pre-flight HEAD audit (v47 §6.6 import-load discipline)

Sandbox HEAD reflects cities_phase1 through cities_phase4b applied.
The Phase 5 prereq check ran symbol-level:

```
$ grep "is_citizen\|can_enter_city_room\|can_use_city_home\|_apply_city_upgrade" \
       engine/player_cities.py engine/security.py
# (no output — Phase 5 surface absent at HEAD)

$ grep "_handle_home" parser/city_commands.py
# (no output — home was in placeholder dispatch at HEAD)

$ ls tests/test_cities_phase5.py
ls: ... No such file or directory
```

Phantom confirmed. Phase 1-4b surfaces untouched except for the
two pinned-keyset re-purposed tests and the new movement gate
in `_check_exit_gates`.

**Rest-bonus mechanic audit:** Verified by grep that the existing
engine has no rest-bonus mechanism at any consumer site:

```
$ grep -rn "REST_BONUS\|rest_bonus\|home_logout\|logout_bonus" engine/ parser/ server/
# (no output)
```

So Phase 5 ships only the read seam (`is_rest_bonus_room()`);
the mechanic itself is deferred per design call #4.

**Schema audit (cleared):** No new tables or columns needed.
Phase 5 touches `player_city_rooms.citizen_only` (existing from
Phase 1), `characters.attributes` (existing JSON blob), and
`player_housing.entry_room_id` (existing from housing system).
Cooldown state stored in `attributes` JSON parallel to the
existing `last_sabacc` pattern.

---

## Phase 5 design calls (locked, May 22 2026)

**Design call #1: "Same planet" implemented as "same zone."**
Design §6.4 says the teleport is planet-scoped, but zones in
`data/worlds/clone_wars/zones.yaml` don't carry an explicit
`planet` attribute — planet is currently a soft concept inferred
via `engine.trading` and the Director. Phase 5 ships the
implementable invariant: same zone_id. This is STRICTER than the
design (only same-zone counts, not other-zone-on-same-planet),
but is loose enough for actual Clone Wars zones today since
cities are zone-anchored and most actionable destinations are in
the same zone. If a future drop adds a zone→planet attribute,
`can_use_city_home` can be updated to honor the looser planet
check in 2-3 lines.

**Design call #2: 30%-cap on `citizen_only` counts only
expansion rooms.** HQ rooms (`is_center=1`) are citizen-only by
default per the design wording in §6.3 ("The City Center HQ rooms
count as citizen-only by default and don't reduce the available
30%"). Implementation: when `set_room_citizen_only(flag=True)`
is requested on a non-HQ room, count current non-HQ
`citizen_only` rooms vs total non-HQ rooms; reject if adding
this one would exceed 30% (rounded to nearest whole room, with
at least 1 always allowed so brand-new cities aren't blocked on
rounding). HQ rooms are not counted; the founder can always flag
all 4 HQ rooms citizen-only without consuming the cap.

**Design call #3: `+city home` cooldown survives logout.** Stored
in `characters.attributes` JSON as `last_city_home` (epoch
seconds), parallel to the existing `last_sabacc` cooldown.
Survives reboots and is durable across sessions, matching the
design's "1-hour cooldown" intent. Otherwise a player could log
out and back in to dodge it.

**Design call #4: Rest-bonus MECHANIC itself is not shipped —
only the `is_rest_bonus_room()` read seam.** The current engine
has no rest-bonus mechanic at any consumer site (verified by
grep above). Adding the mechanic would be an unrelated system
feature with its own design space (recovery rates, what counts as
"rest," login/logout state machine integration, etc.). Phase 5
ships the cities-side answer (`is_rest_bonus_room`) so the future
mechanic gets city support for free.

---

## Code map

### 1. `engine/player_cities.py` (additive)

**New constants:**

```python
CITY_HOME_COOLDOWN_SECONDS = 60 * 60      # 1 hour per design §6.4
CITIZEN_ONLY_MAX_FRACTION = 0.30          # design §6.3
```

**New read seams:**

- `is_citizen(db, char, city) -> bool` — convenience wrapper
  around `get_city_role` (Phase 3). True iff role is
  `founder|mayor|citizen`. Guests and banished users are NOT
  citizens.

- `is_rest_bonus_room(db, char, room_id) -> bool` — §6.1 seam.
  True iff char is a citizen AND room is in their city. The
  rest-bonus mechanic itself is a separate system feature
  (deferred per design call #4); this is the seam future
  consumers will call.

**New movement gate:**

- `can_enter_city_room(db, char, room_id) -> (ok, reason)` —
  §6.3 movement gate. Returns `(False, reason)` iff:
  - the room is in a city
  - the room is flagged `citizen_only`
  - char is NOT a citizen of that city (banished, guest, or
    outsider all fail)

  Returns `(True, "")` otherwise. Failure-soft on internal
  errors (logs + falls open).

**New teleport machinery:**

- `_get_last_city_home(char) -> float` / `_set_last_city_home(char, ts) -> str`
  — read/write helpers for the `last_city_home` attribute in
  `characters.attributes` JSON. Parallel to `_get_last_sabacc` /
  `_set_last_sabacc`.

- `get_city_entry_room_id(db, city) -> Optional[int]` — resolves
  a city to its HQ entry room via `player_cities.hq_id →
  player_housing.entry_room_id`. Per Phase 2 invariant, the
  entry_room is the doorstep (outward-facing) and NOT in
  `player_city_rooms`.

- `can_use_city_home(db, char) -> (ok, dest_room_id, reason)` —
  §6.4 teleport gate. Checks (in order):
  1. char is a member of an org (not independent)
  2. The org has an active city
  3. char is a citizen (founder/mayor/citizen) — banished blocked
  4. char is not in combat (`in_combat` or `combat_state` attribute)
  5. char is not in space (char's room has a valid zone_id)
  6. char is currently in the same zone as the city
     (per Phase 5 design call #1)
  7. Cooldown elapsed (`CITY_HOME_COOLDOWN_SECONDS`)

  Returns `dest_room_id` on success.

- `record_city_home_use(db, char)` — stamps `last_city_home` in
  attributes JSON. Stamps only AFTER the move actually commits;
  caller is responsible for ordering (parser does the move
  first, then this stamp).

**`set_room_citizen_only` modification:** 30%-cap enforcement
added when `flag=True` and the target is not a HQ room. HQ
rooms (`is_center=1`) are exempt from the cap per design call
#2. Cap formula: `max(1, int(0.30 * non_hq_total))`. Min-1
prevents lockout on small cities where 0.30 * 2 = 0 would block
all citizen-only flagging.

### 2. `engine/security.py` (additive)

**New chain step `_apply_city_upgrade`:**

```python
async def _apply_city_upgrade(base, room_id, character, db):
    if character is None:
        return base
    if base not in (CONTESTED, LAWLESS):
        return base  # only these get upgraded
    city = await get_city_for_room(db, int(room_id))
    if not city:
        return base
    if not await is_citizen(db, character, city):
        return base
    # Citizen — apply the upgrade.
    if base == CONTESTED:
        return SECURED
    if base == LAWLESS:
        return CONTESTED
```

**Updated `_finalize` chain:**

```python
base = await _apply_faction_override(base, room, character, db)
base = await _apply_claim_upgrade(base, room_id, character, db)
base = await _apply_city_upgrade(base, room_id, character, db)  # NEW
return base
```

Order matters: city upgrade is most-permissive last word so a
citizen inside their own city gets the strongest available
security tier — even if a faction-override upstream downgraded
SECURED → LAWLESS, a citizen in their own city can be lifted
back to SECURED (via CONTESTED). That's the correct behavior:
a citizen of City X is safe in City X's contested zone, even if
some hostile faction has secured-stronghold rooms in the same
zone that would normally downgrade to lawless for them.

### 3. `parser/builtin_commands.py::MoveCommand::_check_exit_gates`

Appended new gate after the conditional room-lock gate
(F.7.e):

```python
# Player Cities Phase 5 §6.3 gate.
try:
    from engine.player_cities import can_enter_city_room
    _allowed, _reason = await can_enter_city_room(
        ctx.db, char, new_room_id,
    )
    if not _allowed:
        await session.send_line(f"  \033[1;33m{_reason}\033[0m")
        return True
except Exception:
    log.warning(
        "_check_exit_gates: city gate failed", exc_info=True,
    )
```

Yellow-text rejection consistent with the other movement gates
(housing private room, org HQ room, conditional room-lock).
Fail-soft per design §6.3.

### 4. `parser/city_commands.py`

**Dispatch:** `home` moved out of placeholder branch into the
live dispatch table:

```python
# ── Phase 5 subcommands ────────────────────────────────────────
if sub == "home":
    await self._handle_home(ctx, char, rest)
    return
```

**New `_handle_home` method:** Gate via `can_use_city_home`;
on success, perform teleport (set room_id, save_character),
stamp cooldown via `record_city_home_use`, send arrival message,
trigger look (parallel to `housing_commands._go_home`). Cooldown
is stamped AFTER the move actually commits — otherwise a save
failure would burn the cooldown for free.

**Bare-help update:** `+city home` moves from "Coming soon" to
"Available now" list with the line:

```
+city home                 Teleport to city HQ entry (citizen
                            only; 1-hour cooldown).
```

**Module docstring update:** Phase 5 added to the umbrella
header (Phases 1 + 2 + 3 + 4 + 5 → updated to reflect home is
live).

### 5. `tests/test_cities_phase3.py` (1 test re-purposed)

`test_home_still_phase_5` was a pinned-keyset assertion that
`+city home` echoed "Phase 5" in the placeholder output. Phase 5
makes home live, so the test was naturally invalidated.
Re-purposed to `test_home_subcommand_shipped_in_phase_5`: asserts
the bare-help advertises `+city home` under "Available now:".

### 6. `tests/test_cities_phase4.py` (1 test re-purposed)

Same re-purpose pattern for `TestPhase5HomeStillPlaceholder`.

### 7. `tests/test_cities_phase5.py` (new)

34 tests across 30 sections:

```
1.     Constants                       (2 tests)
2-3.   is_citizen + is_rest_bonus_room (4 tests)
4-8.   can_enter_city_room             (5 tests: open, citizen,
                                         outsider blocked, guest
                                         blocked, banished blocked)
9-13.  _apply_city_upgrade + e2e       (6 tests: contested→SECURED,
                                         lawless→CONTESTED, non-
                                         citizen no-upgrade,
                                         SECURED-stays, end-to-end
                                         via get_effective_security
                                         for citizen + outsider)
14-17. set_room_citizen_only 30%-cap   (4 tests: cap, HQ-exempt,
                                         small-city-min-1, clear-
                                         always-OK)
18-25. can_use_city_home                (8 tests: every rejection
                                         branch + happy path)
26.    record_city_home_use             (1 test)
27-29. Parser flow                      (3 tests: happy path,
                                         cooldown surface, in-space
                                         surface)
30.    Phase membership                  (1 test)
```

**Key shared fixture: `_setup_founded_city`** — extends the
Phase 4 `_setup_taxable_city` pattern with founder, citizen,
outsider, guest, AND an `outside_room` in a different zone for
cross-zone tests. Defaults zone security to "contested" so
`_apply_city_upgrade` tests can exercise contested→SECURED
naturally.

**Test infrastructure note:** The `player_city_rooms` schema has
columns `(city_id, room_id, is_center, citizen_only, claimed_at)`
— NO `claim_cost` column. The `_add_expansion_rooms` test helper
direct-INSERTs into this table (bypassing the
`claim_room_for_city` validation pipeline) for tests that need
N expansion rooms quickly. Caught and corrected during test
authoring.

---

## Substrate decisions

### Engine

1. **`can_use_city_home` is a single state-machine read.** All 7
   checks (membership, city, citizenship, combat, space,
   same-zone, cooldown) happen in one function call. The parser
   just calls it and renders the reason. This matches the
   `apply_city_tax` chokepoint discipline from Phase 4.

2. **City upgrade is most-permissive last in `_finalize`.** A
   citizen in their own city should be safer than any other
   resolver step can make them. Order: faction_override (downgrade)
   → claim_upgrade (lift) → city_upgrade (lift). Citizens
   inside their own city's contested rooms get SECURED;
   citizens in lawless city rooms get CONTESTED.

3. **Rest-bonus is a read seam, not a mechanic.** `is_rest_bonus_room`
   returns True/False for "this room counts as home for this
   character." Future rest-bonus consumers (logout state machine,
   wound recovery rate adjustment, etc.) can read this without
   knowing anything about cities.

4. **30%-cap with min-1 floor.** Cities with very few expansion
   rooms (e.g., 2 rooms = 0 at 30%) get min-1 so brand-new cities
   aren't blocked from any citizen-only flagging. HQ rooms are
   fully exempt — a Mayor can flag all 4 HQ rooms citizen-only
   without consuming the cap. This matches the design wording
   exactly.

5. **Cooldown timestamp lives in `attributes` JSON.** Parallel
   to `last_sabacc` and the Phase 3 banishment system. Durable
   across logout (per design call #3); no separate cooldown
   table.

### Parser

6. **`+city home` is a single-step parser.** No subcommands —
   just `+city home` triggers the teleport (or shows a reason
   why not). Simpler than the multi-action surfaces (`+city tax
   view/set/ratecap`).

7. **Look triggered post-teleport.** Parallel to `_go_home` in
   housing_commands. The user expects to see where they ended
   up; this matches the existing teleport UX.

8. **Move gate fails open.** Per design §6.3 ("cities are public
   spaces by default"), any unexpected error in
   `can_enter_city_room` logs and lets the move through.
   Better to leak occasional access than to silently break
   every movement on a transient DB hiccup.

---

## Files

```
engine/player_cities.py             — MODIFIED (additive), +~310 LOC
engine/security.py                  — MODIFIED, +~50 LOC (new chain step)
parser/city_commands.py             — MODIFIED, +~80 LOC
parser/builtin_commands.py          — MODIFIED, +~15 LOC (movement gate)
tests/test_cities_phase3.py         — MODIFIED, 1 test re-purposed
tests/test_cities_phase4.py         — MODIFIED, 1 test re-purposed
tests/test_cities_phase5.py         — NEW, 34 tests
HANDOFF_MAY22_CITIES_PHASE5.md      — this document
```

`db/database.py`, `server/game_server.py`,
`server/tick_handlers_economy.py` are **not** modified.

---

## How to apply on Windows

```powershell
# From SW_MUSH project root. Prereqs: cities_phase1 + cities_phase2
# + cities_phase3 + cities_phase4 + cities_phase4b must be applied first.
Expand-Archive -DestinationPath . -Force ..\SW_MUSH_cities_phase5_drop_20260522.zip

# Targeted tests
python -m pytest tests/test_cities_phase5.py -v      # expect 34/34
python -m pytest tests/test_cities_phase1.py -v      # expect 57/57
python -m pytest tests/test_cities_phase2.py -v      # expect 45/45
python -m pytest tests/test_cities_phase3.py -v      # expect 83/83
python -m pytest tests/test_cities_phase4.py -v      # expect 45/45
python -m pytest tests/test_cities_phase4b.py -v     # expect 16/16

# Adjacent regression (security + movement)
python -m pytest tests/test_b1f_rewicker_boundary.py -v
python -m pytest tests/test_security_resolver_runtime.py -v
python -m pytest tests/test_secmod1_admin_security.py -v
python -m pytest tests/test_f7e_room_locks.py -v
python -m pytest tests/test_srb2_morale_aura.py -v

# Full Windows regression
.\run_all_tests.bat
```

---

## Pre-flight discipline notes

This drop validated v47 §6.6 import-load discipline + three
discoveries worth tracking:

- **Same-zone-as-planet pragmatic implementation.** Zones don't
  carry an explicit planet attribute in the YAML world data, so
  "same planet" is implemented as "same zone." Documented as
  Phase 5 design call #1; the function `can_use_city_home` can be
  updated in 2-3 lines if a zone→planet attribute lands later.

- **Rest-bonus mechanic deferred.** Verified by grep that no
  existing engine code consumes a rest-bonus mechanic. Phase 5
  ships only the read seam; the mechanic itself is a separate
  system feature for a future drop.

- **30%-cap design wording honored literally.** HQ rooms exempt
  from the cap (they're citizen-only by default and don't reduce
  the available 30%). Min-1 floor prevents rounding lockouts on
  small cities.

- **Two pinned-keyset tests re-purposed.** Sixth consecutive
  drop using the same discipline (Phases 2, 3, 4, 4b, 5
  re-purposes confirm the pattern works as expected). When a
  placeholder graduates to live, the test that asserted "still
  placeholder" is the canonical signal that the contract changed
  — re-purpose, don't work around.

No new phantom patterns introduced. v47 §6.2 catalog unchanged.

---

## What's next

**Phase 6 — Admin tools** (Medium effort ~0.5–1 sessions):

- `@city void-banish <city>` — admin override to wipe banishments
  (per design §11.3)
- `@city set-rate-cap <city> <pct>` — admin override of the
  Founder-controlled rate cap (per design §11.3)
- `@city dissolve <city>` — admin-forced dissolution (per design
  §11.3)
- `@city list-all` — admin view of all cities including
  dissolved
- `@city audit <city>` — admin view of all governance events
  for a city (banishments, tax changes, mayor reassignments, etc.)

**Phase 6/7 — NPC guards** (Larger effort ~1+ sessions):

- Guard slots scaling with HQ tier (design §7.1: 5/10/20)
- Guard assignment (`+city guards assign <npc>`) to expansion
  tiles or clustered at HQ entrance
- Guard behavior (engage hostile non-citizens per design §7.2:
  attacker-of-citizen, banished player attempting entry, bountied
  by citizen BH)
- Guard upkeep cost (200 cr/week per design §7.3) — wires into
  the existing weekly tick

**Phase 8+ — wilderness / hidden city variants** (Future):

- Hidden city variant for criminal orgs (Hutts, Black Sun) per
  design §10
- Wilderness expansion variant for shanty-towns / outposts

**Pre-existing baseline failures** (NOT in Phase 5 scope):

- 4 silent except/pass blocks flagged by
  `test_session38.py::TestSilentExceptInvariant`
  (death.py:438, pc_bounty_commands.py:1466,
  builtin_commands.py:319, padawan_master_training_commands.py:713).
  Pre-existing; each needs its own focused review.

---

*cities_phase5 closes. Player Cities Phase 5 (citizen benefits)
shipped. Tier 2 #4 progresses from **5/~10.5–11.5 sessions
delivered** to **6/~10.5–11.5**. The player-facing surface is
now complete: founding, expansion, governance, taxation, and
citizen benefits. Phase 6 (admin tools) is the next medium-size
piece, with Phase 7 (NPC guards) as the larger follow-up.*
