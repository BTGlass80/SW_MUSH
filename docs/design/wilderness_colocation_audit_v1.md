# Wilderness Co-location Audit — Full Surface Sweep

**Date:** May 3, 2026
**Context:** Brian flagged that we were thinking about co-location too
narrowly. Look/say/whisper are obvious, but there are far more PC↔PC
ground interaction surfaces in this codebase, every one of which has
the same potential bug: two PCs in wilderness share a sentinel
`room_id` regardless of where they actually are, so any surface that
uses `room_id` to find "who's here" is broken in wilderness.
**Result of audit:** ~22 distinct surfaces touch PC↔PC ground
interaction. They split cleanly into three buckets.

---

## Bucket 1 — surfaces that NEED co-location filtering (CRITICAL)

These are PC↔PC interactions that should fail silently across
coordinates in wilderness — i.e., a PC at (12, 18) trying to interact
with a PC at (15, 18) should be told "they're not here" exactly the
same as if the target were on a different planet.

### 1.1 Direct PC interactions (12 surfaces)

| # | File | Command(s) | What breaks without filter |
|---|---|---|---|
| 1 | `builtin_commands.py` | **say** | Message reaches PCs at other coords |
| 2 | `builtin_commands.py` | **whisper** | Whisper reaches wrong tile |
| 3 | `builtin_commands.py` | **emote / pose** | Action visible to wrong tile |
| 4 | `builtin_commands.py` | **trade** (offer/accept/decline) | Items transferable across coords |
| 5 | `builtin_commands.py` | **look \<player\>** | Can examine PCs at other tiles |
| 6 | `combat_commands.py` | **attack / shoot / fire / etc.** | **Combat at range across the entire region** |
| 7 | `medical_commands.py` | **heal** | Cross-coord healing |
| 8 | `force_commands.py` | force-push, force-grip, force-throw, etc. | Force powers across coords |
| 9 | `sabacc_commands.py` | sabacc table interactions | Cross-coord card games |
| 10 | `entertainer_commands.py` | morale auras, perform | Aura affects wrong tile |
| 11 | `crafting_commands.py` | **teach** (skill teaching) | Teaching across coords |
| 12 | `espionage_commands.py` | pickpocket-target, eavesdrop targets in same area | Targeting wrong tile |

Of these, **combat (#6) is the most damaging if missed.** A PC at (5, 5)
could shoot a PC at (35, 35) — 60+ km of desert away — without warning.

### 1.2 Broadcast surfaces (10 sites)

Every `broadcast_to_room` and `broadcast_json_to_room` call site that
fires from a PC action and currently pipes to all sentinel-residents
needs the wilderness filter. Files involved:

- `combat_commands.py` (combat events to onlookers)
- `medical_commands.py` (heal completion narration)
- `entertainer_commands.py` (perform start/end/effect)
- `d6_commands.py` (skill check announcements: `+roll`, etc.)
- `faction_commands.py` (faction action announcements)
- `force_commands.py` (force power outcomes)
- `sabacc_commands.py` (table state broadcasts)
- `scene_commands.py` (scene captures + tagging)
- `espionage_commands.py` (counter-eavesdrop alerts)
- `places_commands.py` (places-mode arrival/departure)

### 1.3 Targeted scans (not yet enumerated above)

- `bounty_commands.py`: bounty target validation. The "claim" path
  checks "are we in the same room as the defeated target." Dead NPCs
  are real rooms (not wilderness yet), so probably safe; **but** if a
  PC bounty is killed in wilderness, the claim check needs co-location.

---

## Bucket 2 — surfaces that DON'T need filtering

These either don't fire in wilderness at all, or use `room_id` for a
purpose that's still correct under sentinel sharing.

| # | File | Why it's safe |
|---|---|---|
| - | `building_commands.py` | Builders set room properties; PCs don't build wilderness rooms (sentinel is admin-managed). Safe. |
| - | `building_tier2.py` | Same reasoning — building system. |
| - | `housing_commands.py` | Houses are regular rooms. PCs don't own wilderness tiles. Safe. |
| - | `places_commands.py` | "Places" are sub-locations within a room (cantina booth, etc.). Wilderness has no places. Safe. |
| - | `mux_commands.py` | `page` is OOC (no room scope), `WHO` is global, `wall` is admin-broadcast. Safe. |
| - | `channel_commands.py` | OOC channels — no room scope. Safe. |
| - | `mission_commands.py` | Missions target specific rooms by ID. Wilderness sentinels don't host missions. Safe. |
| - | `space_commands.py` | Space movement uses ship locations, not character `room_id`. Safe. |
| - | `tutorial_commands.py` | Tutorial zones are NOT wilderness. Safe. |
| - | `news_commands.py` | OOC news. Safe. |
| - | `mail_commands.py` | OOC mail. Safe. |
| - | `attr_commands.py` | Self-introspection (sheet, score). Safe. |
| - | `cp_commands.py` | CP spending — self-only. Safe. |
| - | `event_commands.py` | Events posted to Director. Safe. |
| - | `plot_commands.py` | OOC plot tracking. Safe. |
| - | `crew_commands.py` | Ship crew — uses ship `room_id`, not wilderness. Safe. |
| - | `smuggling_commands.py` | Cargo/contraband, room-based but wilderness PCs can't trigger smuggling directly. Safe. |
| - | `narrative_commands.py` | Self-narration mostly; broadcast goes through say/emote which are already filtered. Safe (transitively). |
| - | `director_commands.py` | Admin/Director only. Safe. |
| - | `faction_leader_commands.py` | Admin/leader only, OOC mostly. Safe. |
| - | `achievement_commands.py` | Self-achievements. Safe. |
| - | `news_commands.py`, `mail_commands.py`, etc. | All OOC or self-only. Safe. |

---

## Bucket 3 — surfaces with edge cases (verify, don't blanket-fix)

| # | File | Edge case |
|---|---|---|
| - | `party_commands.py` | Party invite/accept may use room scope to "find a player here." If so, needs filter. Otherwise safe. |
| - | `bounty_commands.py` | Same-room check on bounty claim — see 1.3 above. PC bounties in wilderness are post-launch (not blocking now), so this can be a TODO. |
| - | `npc_commands.py` | `talk <NPC>`. NPCs don't currently spawn in wilderness sentinels. Long-term, when wilderness encounters spawn NPCs (Drop 5), those NPCs will need co-location-aware presence. Defer to Drop 5. |
| - | `d6_commands.py` | `+roll` broadcasts "X rolls Y" to room. Co-location filter needed if rolling in wilderness. **Add to filter list.** |
| - | `entertainer_commands.py` | Morale aura is a passive effect; auras "in the same place" should respect co-location. **Add to filter list.** |

---

## Architecture: how to fix all of this without writing the same patch 22 times

We have two reasonable paths.

### Path A (current W.2 phase 2 code): per-call-site `wilderness_filter` parameter

Every broadcast site that needs co-location passes
`wilderness_filter=(slug, x, y)` explicitly. Every "find target in
same room" loop manually checks `same_location()`.

**Pros:**
- Each call site is auditable.
- No magic.

**Cons:**
- 22+ surfaces to touch.
- Easy to miss one in a future drop.
- Every new ground-interaction command must remember to do this.

### Path B (recommended): centralize in the broadcast/lookup primitives

Push co-location awareness DOWN into the helpers that everyone uses:

**1. `sessions_in_room(room_id, *, source_char=None)`** —
when `source_char` is provided AND that char is in wilderness,
filter results to sessions whose character has matching wilderness
coords. Default behavior (no `source_char`) is current behavior.

**2. `broadcast_to_room(room_id, text, *, exclude=None, source_char=None)`** —
same: when `source_char` is in wilderness, restrict to matching coords.

**3. `get_characters_in_room(room_id, *, source_char=None)`** —
new keyword. Same filter logic.

**4. `find_session_in_room_by_name(...)`** — every "find target by
name in same room" loop becomes a call to a new helper that consults
co-location.

Once these are in place, every existing call site that passes
`source_char=ctx.session.character` (or just `char`) gets co-location
for free. The pattern becomes:

```python
# Before
for s in ctx.session_mgr.sessions_in_room(room_id):
    ...

# After (one-line addition)
for s in ctx.session_mgr.sessions_in_room(room_id, source_char=char):
    ...
```

**Pros:**
- One implementation, audit-once.
- Future commands that don't add the kwarg get default (no filter)
  behavior, which is wrong-but-safe (visible to too many people).
  Better than wrong-and-dangerous (combat-at-range).
- The forgetting failure mode is "PC in wilderness sees too many
  things," not "PC in wilderness can damage strangers across the desert."

**Cons:**
- Touches widely-used helpers, so the regression sweep needs to be
  thorough.
- Slight ergonomic cost: every relevant call site grows by one kwarg.

---

## Recommendation

**Adopt Path B.** Specifically:

1. **Add `source_char` kwarg** to:
   - `sessions_in_room` (server/session.py)
   - `broadcast_to_room` (server/session.py)
   - `broadcast_json_to_room` (server/session.py)
   - `broadcast_chat` (server/session.py)
   - `db.get_characters_in_room` (db/database.py)

2. **Migrate all PC↔PC interaction call sites** to pass
   `source_char=char`. The Bucket 1 list is the audit target. Bucket 2
   call sites can stay unchanged (their lack of filter is correct).

3. **Replace** the existing `wilderness_filter=(slug, x, y)` parameter
   I added in W.2 phase 2 with `source_char`. The `(slug, x, y)` tuple
   is computed inside the helper from `source_char` instead of by the
   caller. Cleaner contract.

4. **Add a helper** `find_session_at_same_location(session_mgr, source_char, name)`
   — name-prefix search restricted to co-located characters. Used
   everywhere "trade <name>", "heal <name>", "force-push <name>", etc.,
   currently does its own loop.

### Scope impact on W.2 phase 2

The W.2 phase 2 work I've done so far (look/say wilderness fork,
edges, MoveCommand, LookCommand) is **largely correct** — it just
gets simpler when Path B lands.

**Revised plan for W.2 phase 2:**

| Step | Effort |
|---|---|
| 1. Replace ad-hoc `wilderness_filter` kwarg with `source_char` in session.py | small |
| 2. Add `source_char` kwarg to `db.get_characters_in_room` | small |
| 3. Add `find_session_at_same_location()` helper | small |
| 4. Migrate the Bucket 1 surfaces (12 commands + 10 broadcast sites) | medium — touches several files but mechanical |
| 5. Update LookCommand/MoveCommand wilderness fork to use the new helpers | small (deletes some code) |
| 6. Add whisper wilderness handling | trivial (1 line) |
| 7. Author tests for: helpers, every Bucket 1 surface in wilderness, broadcast filter, name-prefix search | medium |

Total scope: ~1.5 sessions instead of the ~1 session I'd estimated for
the narrow fix. Worth it because Path A would leave us with 22 places
to audit and a higher chance of regressions on every future ground
command.

---

## What to defer

- **NPC co-location (talk to NPC at same tile).** Wilderness NPCs
  don't exist yet — encounters spawn in Drop 5 (`wilderness_system_design_v1.md`
  Drop 5). When they do, the NPC-targeting helpers will already use
  `source_char` filtering for free if we land Path B now.
- **PC bounty in wilderness.** Per userMemory, PC bounty system is
  post-launch. The `bounty_commands.py` claim path's "same room" check
  can use `source_char` when migrated.
- **Co-location-aware auras (cantina morale, future).** Same — the
  `source_char` pattern handles these naturally when they're built.

---

## Testing implications

For W.2 phase 2 to ship "co-location works," the test suite needs
coverage of (roughly):

- `same_location()` truth table (already planned)
- `characters_at_tile()` query (already planned)
- `sessions_in_room(room_id, source_char=...)` filter behavior
- `broadcast_to_room` filter via source_char
- For each Bucket 1 surface: a test placing two PCs at different
  wilderness tiles and verifying the surface respects co-location

The surface-level tests can be parameterized — one base fixture (two
PCs in same region, different tiles), then per-command tests asserting
"wrong-tile target produces 'not here' / 'no effect' / etc." That
keeps the test count manageable.

---

## Bottom line

Brian's instinct is right. Look/say/whisper was the visible tip; the
iceberg is **22 surfaces of PC↔PC ground interaction**, and combat is
the most dangerous one to miss. The architectural fix (Path B,
`source_char` kwarg pushed into broadcast/lookup primitives) costs
~0.5 session more than the narrow fix and saves us from a bug class
that would otherwise leak into every future drop.

I'd recommend pausing the current W.2 phase 2 work as-is, locking
this addendum, and rebooting phase 2 with the wider scope. The ~1500
lines I've written will get refactored down (less code, not more),
and we'll ship a phase 2 that genuinely closes the co-location story
instead of half-closing it.
