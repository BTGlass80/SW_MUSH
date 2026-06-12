# SW_MUSH — Tutorial & World Integrity Bug Fix Design
## Opus Session — April 15, 2026

---

## Executive Summary

A live playthrough of the new-player tutorial exposed **5 bugs** and **1 quality issue**. The most critical is a systemic exit collision problem in `build_mos_eisley.py` that makes **21 rooms unreachable** across all four planets, including Kayson's Weapon Shop (which blocks the starter quest chain at step 2). The remaining bugs affect the First Contact achievement, NPC dialogue formatting, dead NPC cleanup, and combat auto-pose quality.

**Priority ordering:**
1. Exit collisions (Critical — blocks gameplay)
2. First Contact achievement (Medium — achievement never fires)
3. NPC corpse cleanup (Medium — immersion break)
4. Kessa double-quote dialogue (Low — cosmetic)
5. Combat compound pose punctuation (Low — cosmetic)
6. Combat flavor text variety (Enhancement — not a bug)

---

## Bug 1: Exit Direction Collisions (Critical)

### Root Cause

`build_mos_eisley.py` defines room connections in the `EXITS` list as `(from_idx, to_idx, forward_direction, reverse_direction)` tuples. The `create_exit()` function in `db/database.py` (line 983) checks for existing exits and **silently skips** duplicates:

```python
async def create_exit(self, from_room, to_room, direction, name=""):
    existing = await self.find_exit_by_dir(from_room, direction)
    if existing:
        log.debug("Duplicate exit skipped: room %d %s already exists", ...)
        return existing["id"]
```

When two EXITS entries produce the same `(room_id, direction)` pair, the second one is silently dropped. This makes the destination room unreachable from that hub.

### Scope

**21 collisions** across all four planets. The worst offender is Market District (room 8) with **7 dropped exits** including the weapon shop, bank, general store, clinic approach, and dowager queen wreckage.

### Complete Collision List & Fixes

Each fix below changes the **reverse direction** (the exit FROM the hub TO the destination) since that's where collisions occur. The forward direction (from destination back to hub) is unaffected.

#### Tatooine — Mos Eisley Core (14 collisions)

**Room 0: Docking Bay 94 - Entrance** — collision on `north`
- WINNER: `(0, 7, "north", ...)` → Spaceport Row via north ✓
- DROPPED: `(2, 0, "south", "north to Bay 86")` — Bay 86 reverse
- **FIX:** Change `(2, 0, "south", "north to Bay 86")` → `(2, 0, "south", "east to Bay 86")`
  - Rationale: Bay 86 (Customs) is logically east of Bay 94 entrance. Room 0 has east available.

**Room 7: Spaceport Row** — collision on `north`
- WINNER: `(7, 8, "north", ...)` → Market District ✓
- DROPPED: `(17, 7, "south", "north to Inn")` — Inn reverse
- **FIX:** Change `(17, 7, "south", "north to Inn")` → `(17, 7, "south", "northeast to Inn")`
  - Rationale: Room 7 has northeast available.

**Room 7: Spaceport Row** — collision on `south`
- WINNER: `(0, 7, "north", "south to Bay 94")` — Bay 94 reverse ✓
- DROPPED: `(26, 7, "north", "south to Tower")` — Control Tower reverse
- **FIX:** Change `(26, 7, "north", "south to Tower")` → `(26, 7, "north", "southwest to Tower")`
  - Rationale: Room 7 has southwest available.

**Room 7: Spaceport Row** — collision on `west` (3-way)
- WINNER: `(2, 7, "east", "west to Bay 86")` — Bay 86 ✓
- DROPPED: `(5, 7, "east", "west to Bay 91")` — Bay 87/91
- DROPPED: `(25, 7, "east", "west to Hotel")` — Hotel
- **FIX:** Change `(5, 7, "east", "west to Bay 91")` → `(5, 7, "east", "northwest to Bay 91")`
- **FIX:** Change `(25, 7, "east", "west to Hotel")` → `(25, 7, "east", "southwest to Hotel")`
  - Note: southwest was freed by moving Tower to southwest above. Actually let me recheck...
  - Room 7 used directions after previous fixes: north, south, east, west, southeast, northeast, southwest
  - Available: northwest, down, up
  - **Revised:** Bay 91 → `"northwest to Bay 91"`, Hotel → wait, southwest is taken by Tower now.
  - **Re-revised:** Tower → `"southwest to Tower"` takes southwest. Hotel needs a different slot.
  - Room 7 after all fixes: north(Market), south(Bay94), east(Bay87), west(Bay86), southeast(Docking Bay 86), northeast(Inn), southwest(Tower), northwest(Bay91)
  - Available: down, up
  - **FIX for Hotel:** `(25, 7, "east", "up to Hotel")` — Hotel is conceptually "upstairs" from the street.

**Room 8: Market District** — collision on `north`
- WINNER: `(8, 9, "north", ...)` → Government Quarter ✓
- DROPPED: `(16, 8, "south", "north to Market Place")` — Gep's Grill reverse
- **FIX:** Room 8 available directions: down, southeast, up
- Change `(16, 8, "south", "north to Market Place")` → `(16, 8, "south", "up to Market Place")`
  - Rationale: Market Place / Gep's Grill is on a raised platform above the street. "Up" fits.
  - Alternative: If "up" feels wrong, use a named exit. But "up" is clean.

**Room 8: Market District** — collision on `south` (5-way!)
- WINNER: `(7, 8, "north", "south to Spaceport")` — Spaceport Row ✓
- DROPPED: `(8, 11, "south", "north")` — South End (forward direction collision, not reverse)
  - Wait — this is a forward from room 8 going south. But the winner is a reverse going south from 8 to 7. The forward `(8, 11, "south", "north")` means room 8 south → room 11, and room 11 north → room 8. So the `south` from room 8 collides with the reverse of `(7, 8, "north", "south to Spaceport")`. No — the reverse creates `south` from room 8 to room 7. Then `(8, 11, "south", ...)` creates another `south` from room 8 to room 11. Collision.
- DROPPED: `(15, 8, "north", "south to General Store")` — General Store reverse
- DROPPED: `(33, 8, "north", "south to Bank")` — Bank reverse
- DROPPED: `(37, 8, "north", "south to Wreckage")` — Dowager Queen reverse
- **FIXES:** Room 8 available after `north` fix above: down, southeast
  - South End: `(8, 11, "south", "north")` → `(8, 11, "down", "north")`
    - Rationale: Kerner Plaza / South End is "down" the street. "Down" is available. Actually this changes the forward direction from room 8, not the reverse. The EXITS tuple is `(from, to, forward, reverse)`. `(8, 11, "south", "north")` means go south from 8 to reach 11, go north from 11 to reach 8. We need to change the south from room 8. So change to `(8, 11, "southeast", "north")`.
    - Wait, southeast might be needed. Let me allocate carefully.
  - Room 8 total exits needed FROM room 8: Spaceport(south✓), Gov Quarter(north✓), Cantina(west✓), Jabba(northwest✓), Heff(southwest✓), Jawa(northeast✓), Eastern Gate(east✓), South End(?), General Store(?), Bank(?), Weapon Shop(?), Market Place(?), Wreckage(?)
  - That's 13 exits from one room. Only 10 cardinal+ordinal directions exist plus up/down = 12 total.
  - Available slots from room 8: southeast, down, up (3 slots for 5 dropped exits)
  - **We need named/custom exits for some of these.**

Let me reconsider the Market District layout. It's the central hub and realistically needs some rooms accessed via named exits rather than cardinal directions.

**Revised Room 8 allocation:**
| Destination | Current (broken) | Fix | Rationale |
|---|---|---|---|
| Spaceport Row (7) | south ✓ | keep | Main street south |
| Gov Quarter (9) | north ✓ | keep | Main street north |
| Cantina (12) | west ✓ | keep | Cantina to the west |
| Jabba's (18) | northwest ✓ | keep | Already working |
| Heff's (28) | southwest ✓ | keep | Already working |
| Jawa Traders (29) | northeast ✓ | keep | Already working |
| Eastern Gate (40) | east ✓ | keep | Already working |
| South End (11) | south → **DROPPED** | `southeast` | Down the street southeast toward Kerner Plaza |
| General Store (15) | south → **DROPPED** | `down to General Store` | Sunken shop entrance |
| Bank (33) | south → **DROPPED** | `up to Bank` | Bank is on a raised foundation |
| Weapon Shop (27) | west → **DROPPED** | `southeast to Weapon Shop` | Wait, southeast is taken by South End now |

Conflict again. Let me just allocate all at once:

| Destination | Direction from Room 8 |
|---|---|
| Spaceport Row (7) | south |
| Gov Quarter (9) | north |
| Cantina (12) | west |
| Jabba's (18) | northwest |
| Heff's (28) | southwest |
| Jawa Traders (29) | northeast |
| Eastern Gate (40) | east |
| **South End (11)** | **southeast** |
| **Weapon Shop (27)** | **down to Weapon Shop** |
| **General Store (15)** | **up to General Store** |
| **Bank (33)** | `bank` (named exit) |
| **Market Place (16)** | `market` (named exit) |
| **Wreckage (37)** | `wreckage` (named exit) |

This uses all 10 directions + up + down + 3 named exits. Named exits work in the engine — players type the exit name (e.g., `bank`, `market`, `wreckage`). The `_split_exit` function already handles this by taking the first word as the direction key.

Actually, let me reconsider. "down" and "up" from a street feel odd. Better to use named exits for the shops. Let me look at how `_split_exit` works:

```python
# From build_mos_eisley.py (need to check)
```

Actually, the existing code already uses named exits like `"in"`, `"out"`, `"back"`, `"coded lift"`, `"bay aurek"`, `"platform besh"`, `"behind hangars"`, `"workshop"`, `"forge"`, `"guild hall"`, `"hidden"`, `"weapons cache"`. So named exits are fully supported.

**Final Room 8 allocation (revised):**

| Destination | Direction from Room 8 | EXITS change |
|---|---|---|
| South End (11) | southeast | Change `(8, 11, "south", "north")` → `(8, 11, "southeast", "northwest")` |
| Weapon Shop (27) | southeast to Weapon Shop | **Collision with South End!** |

Okay, only `southeast` and `down`/`up` are available as standard directions. Let me use named exits more aggressively:

| Destination | Direction from Room 8 | Type |
|---|---|---|
| South End (11) | southeast | cardinal |
| Weapon Shop (27) | down to Weapon Shop | vertical — "descend steps to the weapon shop" |
| General Store (15) | `store` | named |
| Bank (33) | `bank` | named |
| Market Place (16) | `market` | named |
| Wreckage (37) | `wreckage` | named |

This works. 10 cardinals + southeast + down = 12 standard slots, with 4 named exits.

**But wait** — will tutorial hints and quest chain references still work? The starter quest says "go to the weapon shop in the market district." A player needs to discover the `down` exit. The `look` output shows exits, so `down (Weapon Shop)` would appear. That's fine — maybe even better than a cardinal direction since it stands out.

Actually, thinking about this more carefully from a MUSH UX perspective: having shops accessible via named exits from a hub street is very standard MUSH design. `store`, `bank`, `weapon shop` etc. are how MUSHes typically handle dense hub areas. Let me use that pattern.

**Final Room 8 allocation (v3):**

| Destination | Exit from Room 8 | Reverse to Room 8 |
|---|---|---|
| South End (11) | `southeast` | `northwest` |
| Weapon Shop (27) | `weapon shop` | `east` (keep forward unchanged) |
| General Store (15) | `store` | `north` (keep forward unchanged) |
| Bank (33) | `bank` | `north` (keep forward unchanged) |
| Market Place (16) | `grill` | `south` (keep forward unchanged) |
| Wreckage (37) | `wreckage` | `north` (keep forward unchanged) |

Hmm, but this changes how rooms display exits. Currently exits show as `south (Spaceport)` — a direction with a label. Named exits would show as `weapon shop (Kayson's Weapon Shop)`. Let me check how the exit display renders:

Actually, looking at the transcript more carefully:
```
Exits: south (Spaceport), north (Mos Eisley Street - Government Quarter), west (Cantina)
       northwest (Jabba's Townhouse - Main Entrance), southwest (Heff's Souvenirs), 
       northeast (Jawa Traders), east (Eastern Gate)
```

The format is `direction (room_name)`. Named exits would appear as `weapon shop (Kayson's Weapon Shop)`. That works — it's discoverable and clear.

But actually, on reflection, the simplest fix that minimizes player confusion and matches the existing UX is to just use the remaining cardinal/ordinal directions plus up/down where they make spatial sense. We have exactly 3 standard slots left (southeast, up, down) for 6 rooms. So we need 3 named exits minimum.

Let me pick the most important rooms for standard directions:

| Destination | Exit from Room 8 | Notes |
|---|---|---|
| South End (11) | `southeast` | Major navigation artery |
| Weapon Shop (27) | `down` | "Descend steps to the weapon shop" — weapon shops are often in cellars |
| General Store (15) | `up` | "Steps up to the general store" |
| Bank (33) | `bank` | Named exit |
| Market Place (16) | `grill` or `market` | Named exit |
| Wreckage (37) | `wreckage` | Named exit |

**This is the final allocation.** It uses all 12 standard directions from room 8 and 3 named exits.

---

Continuing with the remaining collisions:

**Room 8: Market District** — collision on `west`
- Already addressed above: Weapon Shop gets `down` instead of `west`.

**Room 9: Government Quarter** — collision on `north`
- WINNER: `(9, 10, "north", ...)` → North End ✓
- DROPPED: `(22, 9, "south", "north to Gov District")` — Militia HQ reverse
- **FIX:** Change reverse to `northeast to Militia HQ`
  - Room 9 available: northeast, northwest, southwest, down, up

**Room 9: Government Quarter** — collision on `west`
- WINNER: `(20, 9, "east", "west to Prefect")` → Government Offices ✓
- DROPPED: `(35, 9, "east", "west to Clinic")` — Clinic reverse
- **FIX:** Change reverse to `northwest to Clinic`
  - Room 9 available after Militia fix: northwest, southwest, down, up

**Room 10: North End** — collision on `south`
- WINNER: `(9, 10, "north", "south to Inner Curve")` → Gov Quarter ✓
- DROPPED: `(39, 10, "north", "south to Notsub")` — Notsub Shipping reverse
- **FIX:** Change reverse to `southeast to Notsub`
  - Room 10 available: east, northeast, northwest, southeast, southwest, down, up

**Room 10: North End** — collision on `west`
- WINNER: `(6, 10, "east", "west to Bay 95")` → Docking Bay 92 ✓
- DROPPED: `(36, 10, "east", "west to Monastery")` — Dim-U Monastery reverse
- **FIX:** Change reverse to `northwest to Monastery`

**Room 22: Militia HQ** — collision on `south`
- WINNER: `(22, 9, "south", ...)` → Gov Quarter ✓ (forward direction)
- DROPPED: `(23, 22, "north", "south to Stables")` — Stables reverse
- **FIX:** Change reverse to `east to Stables`
  - Room 22 has almost everything available (only `south` is used after the earlier fix changes it to... wait. Let me re-check.
  - Original: `(22, 9, "south", "north to Gov District")`. We're changing the REVERSE to `northeast to Militia HQ` from room 9. The forward `"south"` from room 22 to room 9 stays.
  - So room 22 still has `south` used. The collision is that `(23, 22, "north", "south to Stables")` creates another `south` from room 22 to room 23. 
  - **FIX:** Change `(23, 22, "north", "south to Stables")` → `(23, 22, "north", "east to Stables")`

#### Tatooine — Outskirts (2 collisions)

**Room 40: Eastern Gate** — collision on `west`
- WINNER: `(40, 8, "west", ...)` → Market District ✓
- DROPPED: `(44, 40, "east", "west to Checkpoint")` — Checkpoint reverse
- **FIX:** Change reverse to `south to Checkpoint`
  - Room 40 available: south, northeast, northwest, southeast, southwest, down, up

**Room 41: Scavenger Market** — collision on `west`
- WINNER: `(41, 40, "west", ...)` → Eastern Gate ✓
- DROPPED: `(43, 41, "east", "west to Track")` — Speeder Track reverse
- **FIX:** Change reverse to `north to Track`
  - Room 41 available: north, east, northeast, northwest, southeast, southwest, down, up

#### Nar Shaddaa (3 collisions)

**Room 56: Promenade** — collision on `north`
- WINNER: `(56, 59, "north", ...)` → Smugglers' Guild ✓
- DROPPED: `(76, 56, "south", "north through Enforcer Alley")` — Enforcer Alley reverse
- **FIX:** Change reverse to `east through Enforcer Alley`
  - Room 56 available: east, southwest

**Room 64: Undercity Market** — collision on `down`
- WINNER: `(64, 65, "down", ...)` → Undercity Depths ✓
- DROPPED: `(75, 64, "up", "down to Floating Market")` — Floating Market reverse
- **FIX:** Change reverse to `west to Floating Market`
  - Room 64 available: north, northeast, northwest, southeast, southwest, west

**Room 65: Undercity Depths** — collision on `up`
- WINNER: `(64, 65, "down", "up")` → Undercity Market ✓
- DROPPED: `(79, 65, "down", "up to Warrens")` — Warrens Entry Shaft reverse
- **FIX:** Change reverse to `north to Warrens`
  - Room 65 available: north, east, south, northeast, northwest, southeast, southwest, down

#### Kessel (1 collision)

**Room 87: Mine Entrance** — collision on `up`
- WINNER: `(85, 87, "down", "up to Checkpoint")` → Garrison Checkpoint ✓
- DROPPED: `(92, 87, "down", "up to Shaft Junction")` — Shaft Junction reverse
- **FIX:** Change reverse to `down to Shaft Junction`
  - Wait, that creates `down` from room 87 to room 92. Room 87 already has `east` used. `down` should be available. Actually the forward direction of (92, 87) is `"down"` from room 92 to room 87. The reverse is from room 87 to room 92. So `down` from 87 would go to 92 — but that means going down from mine entrance goes deeper. That's correct!
  - Actually wait, room 87 IS the mine entrance. Going `up` goes to checkpoint (surface). Going `down` should go deeper (shaft junction). That's correct.
  - **FIX:** Change `(92, 87, "down", "up to Shaft Junction")` → `(92, 87, "down", "down to Shaft Junction")`

#### Corellia (2 collisions — 1 is a true duplicate)

**Room 100: Treasure Ship Row** — collision on `west`
- WINNER: `(97, 100, "east", "west to Concourse")` → Starport Concourse ✓
- DROPPED: `(100, 113, "west", ...)` → Old Quarter Market (forward from 100)
- **FIX:** Change `(100, 113, "west", "east to Treasure Ship Row")` → `(100, 113, "southwest", "northeast to Treasure Ship Row")`
  - Room 100 available: southwest (after checking existing: south, north, east, west, northeast)
  - Actually wait — `west` from room 100 collides with the reverse of `(97, 100, "east", "west to Concourse")`. So we need to change the forward direction of `(100, 113, ...)` from `west` to something else.
  - Room 100 used: south(101), north(107), east(102), west(Concourse reverse), northeast(105)
  - Available: southwest, northwest, southeast, down, up
  - **FIX:** `(100, 113, "southwest", "northeast to Treasure Ship Row")`

**Rooms 103/117: Blue Sector ↔ Casino** — DUPLICATE exits
- `(103, 117, "east", "west to Blue Sector")` ← first entry
- `(117, 103, "west", "east to Casino")` ← second entry, creates the SAME exits!
  - First creates: 103→117 east, 117→103 west
  - Second creates: 117→103 west (DUPLICATE, dropped), 103→117 east (DUPLICATE, dropped)
- **FIX:** Delete the second entry `(117, 103, "west", "east to Casino")` entirely. It's redundant.

---

### Implementation: EXITS Changes

All changes are in `build_mos_eisley.py` in the `EXITS` list. Each change modifies one string in one tuple. Here are the exact line-level changes:

```python
# Room 0 collision: Bay 86 reverse
# OLD: (2, 0, "south", "north to Bay 86"),
# NEW: (2, 0, "south", "east to Bay 86"),

# Room 7 collision: Inn reverse
# OLD: (17, 7, "south", "north to Inn"),
# NEW: (17, 7, "south", "northeast to Inn"),

# Room 7 collision: Tower reverse
# OLD: (26, 7, "north", "south to Tower"),
# NEW: (26, 7, "north", "southwest to Tower"),

# Room 7 collision: Bay 91 reverse
# OLD: (5, 7, "east", "west to Bay 91"),
# NEW: (5, 7, "east", "northwest to Bay 91"),

# Room 7 collision: Hotel reverse
# OLD: (25, 7, "east", "west to Hotel"),
# NEW: (25, 7, "east", "up to Hotel"),

# Room 8 collision: South End forward
# OLD: (8, 11, "south", "north"),
# NEW: (8, 11, "southeast", "northwest"),

# Room 8 collision: Weapon Shop reverse
# OLD: (27, 8, "east", "west to Weapon Shop"),
# NEW: (27, 8, "east", "down to Weapon Shop"),

# Room 8 collision: General Store reverse
# OLD: (15, 8, "north", "south to General Store"),
# NEW: (15, 8, "north", "up to General Store"),

# Room 8 collision: Market Place reverse
# OLD: (16, 8, "south", "north to Market Place"),
# NEW: (16, 8, "south", "grill"),

# Room 8 collision: Bank reverse
# OLD: (33, 8, "north", "south to Bank"),
# NEW: (33, 8, "north", "bank"),

# Room 8 collision: Dowager Queen reverse
# OLD: (37, 8, "north", "south to Wreckage"),
# NEW: (37, 8, "north", "wreckage"),

# Room 9 collision: Militia HQ reverse
# OLD: (22, 9, "south", "north to Gov District"),
# NEW: (22, 9, "south", "northeast to Militia HQ"),

# Room 9 collision: Clinic reverse
# OLD: (35, 9, "east", "west to Clinic"),
# NEW: (35, 9, "east", "northwest to Clinic"),

# Room 10 collision: Notsub reverse
# OLD: (39, 10, "north", "south to Notsub"),
# NEW: (39, 10, "north", "southeast to Notsub"),

# Room 10 collision: Monastery reverse
# OLD: (36, 10, "east", "west to Monastery"),
# NEW: (36, 10, "east", "northwest to Monastery"),

# Room 22 collision: Stables reverse
# OLD: (23, 22, "north", "south to Stables"),
# NEW: (23, 22, "north", "east to Stables"),

# Room 40 collision: Checkpoint reverse
# OLD: (44, 40, "east", "west to Checkpoint"),
# NEW: (44, 40, "east", "south to Checkpoint"),

# Room 41 collision: Speeder Track reverse
# OLD: (43, 41, "east", "west to Track"),
# NEW: (43, 41, "east", "north to Track"),

# Room 56 collision: Enforcer Alley reverse
# OLD: (76, 56, "south", "north through Enforcer Alley"),
# NEW: (76, 56, "south", "east through Enforcer Alley"),

# Room 64 collision: Floating Market reverse
# OLD: (75, 64, "up", "down to Floating Market"),
# NEW: (75, 64, "up", "west to Floating Market"),

# Room 65 collision: Warrens reverse
# OLD: (79, 65, "down", "up to Warrens"),
# NEW: (79, 65, "down", "north to Warrens"),

# Room 87 collision: Shaft Junction reverse
# OLD: (92, 87, "down", "up to Shaft Junction"),
# NEW: (92, 87, "down", "down to Shaft Junction"),

# Room 100 collision: Old Quarter Market forward
# OLD: (100, 113, "west", "east to Treasure Ship Row"),
# NEW: (100, 113, "southwest", "northeast to Treasure Ship Row"),

# Rooms 103/117: DELETE duplicate exit
# DELETE: (117, 103, "west", "east to Casino"),
```

### Post-Fix Validation

After making changes, re-run the collision audit script (provided separately) to confirm zero collisions. Then rebuild the world:
```bash
python build_mos_eisley.py
```

### Web Client Map Coordinates

The `MAP_COORDS` dict (line ~2220 in `build_mos_eisley.py`) may need minor adjustments for rooms that changed directions, but coordinates are room-level, not exit-level, so no changes should be needed.

---

## Bug 2: First Contact Achievement Never Fires

### Root Cause

`parser/builtin_commands.py` line ~889:

```python
if others and hasattr(ctx.session, "game_server"):
    from engine.achievements import on_pc_conversation
    await on_pc_conversation(ctx.db, char["id"], session=ctx.session)
```

**`Session` objects never have a `game_server` attribute.** The handler objects (`TelnetHandler`, `WebSocketHandler`) store it as `self.game`, but that's on the handler, not the session. This guard always evaluates `False`.

The `combat_victory` achievement (which works correctly) does NOT use this guard — it calls `on_combat_victory()` directly.

### Fix

Remove the `hasattr` guard entirely. The `try/except` block already handles any failures safely:

```python
# OLD (line ~886-893):
        # Achievement: pc_conversation (2+ PCs in room)
        try:
            others = [s for s in ctx.session_mgr.sessions_in_room(room_id) or []
                      if s.character and s.character.get("id") != char["id"]]
            if others and hasattr(ctx.session, "game_server"):
                from engine.achievements import on_pc_conversation
                await on_pc_conversation(ctx.db, char["id"], session=ctx.session)
        except Exception:
            pass

# NEW:
        # Achievement: pc_conversation (2+ PCs in room)
        try:
            others = [s for s in ctx.session_mgr.sessions_in_room(room_id) or []
                      if s.character and s.character.get("id") != char["id"]]
            if others:
                from engine.achievements import on_pc_conversation
                await on_pc_conversation(ctx.db, char["id"], session=ctx.session)
        except Exception:
            pass
```

### File
`parser/builtin_commands.py` — single string change in the `SayCommand.execute()` method.

---

## Bug 3: Incapacitated NPCs Remain Visible in Room

### Root Cause

When combat ends, `_remove_combat()` clears the combat instance but doesn't touch the NPC's room presence. The NPC remains in the `npcs` table with its original `room_id`, so `look` still shows it with its full alive description.

### Fix

At combat end in `parser/combat_commands.py`, after the achievement hook and before `_remove_combat()`, add NPC cleanup logic:

```python
# After the achievement block, before _remove_combat():

# Clean up incapacitated/dead NPCs
try:
    for c in combat.combatants.values():
        if c.is_npc and c.char and c.char.wound_level.value >= 4:
            # Incapacitated or worse — remove from room
            await ctx.db.execute(
                "UPDATE npcs SET room_id = NULL WHERE id = ?",
                (c.id,)
            )
except Exception:
    log.warning("NPC cleanup after combat failed", exc_info=True)
```

Setting `room_id = NULL` hides the NPC from `get_npcs_in_room()` queries. The NPC data is preserved for respawn systems.

**Note:** Tutorial NPCs (Sand Raider) should probably be fully deleted since they're single-use. Check if the NPC has a tutorial flag and use `delete_npc()` if so. But `room_id = NULL` is a safe minimum fix.

### Respawn Consideration

For non-tutorial NPCs (e.g., hostile NPCs in the Jundland Wastes), we probably want a respawn timer rather than permanent removal. That's a separate feature. For now, `room_id = NULL` is correct — the ambient event system or a future respawn tick can restore them.

### File
`parser/combat_commands.py` — add ~8 lines after the achievement block in `_try_auto_resolve()`.

---

## Bug 4: Kessa Double-Quoted Dialogue

### Root Cause

`parser/npc_commands.py` line ~338:

```python
await ctx.session_mgr.broadcast_to_room(
    char["room_id"],
    f'  {ansi.npc_name(npc_data.name)} says, "{response}"',
)
```

The `response` from the AI/LLM often includes its own wrapping quotes. The display code adds another pair. Result: `Kessa Dray says, ""Next, we're heading...""`.

### Fix

Strip leading/trailing quotes from the AI response before wrapping:

```python
# Before the broadcast line:
response = response.strip().strip('"').strip("'").strip('"').strip('"')
```

This handles:
- Standard double quotes `"..."`
- Single quotes `'...'`
- Smart/curly quotes `"..."` (if the LLM returns them)

### File
`parser/npc_commands.py` — add one line before each `broadcast_to_room` call that wraps `response` in quotes. There are two such locations: the tutorial NPC AI path (line ~338) and the general NPC AI path (line ~380ish after persuasion logic). Both need the strip.

---

## Bug 5: Combat Compound Pose Punctuation

### Root Cause

`engine/combat_flavor.py` line 264:

```python
combined += f", then {extra}"
```

The first action pose already ends with a period (e.g., "scoring the surface but doing no real harm."). Appending `, then` creates "...no real harm., then braces..."

### Fix

Strip trailing punctuation from `combined` before appending:

```python
# OLD:
combined += f", then {extra}"

# NEW:
combined = combined.rstrip(".!") + f", then {extra}"
```

### Additional: "parrying with melee parry" phrasing

`engine/combat.py` line 1555:

```python
f"{c.name} braces, parrying with {r.action.skill or 'melee parry'}."
```

The raw skill name "melee parry" reads awkwardly. Fix:

```python
# Map raw skill names to display-friendly text
_PARRY_DISPLAY = {
    "melee parry": "a melee guard",
    "brawling parry": "bare hands",
    "lightsaber": "their lightsaber",
}
skill_display = _PARRY_DISPLAY.get(
    (r.action.skill or "melee parry").lower(),
    r.action.skill or "melee parry"
)
f"{c.name} braces, parrying with {skill_display}."
```

### Files
- `engine/combat_flavor.py` — one line change in `generate_compound_npc_pose()`
- `engine/combat.py` — small change around line 1555

---

## Enhancement: Combat Flavor Text Variety

Not a bug. The `miss_close` bucket has only 3 phrases, so a 5-round fight virtually guarantees repeats. Add more variety:

```yaml
# Additional miss_close options:
"but the shot skips off armor plating."
"barely grazing past."  
"deflected at the last instant."
"the shot absorbed by cover."
"scraping past without purchase."

# Additional miss_wild options:
"the shot hitting nothing but air."
"firing wide into the dust."
"missing entirely."

# Additional hit_glancing options:
"nicking them with a shallow hit."
"skimming past but drawing blood."
"tagging them with a partial hit."
```

### File
`engine/combat_flavor.py` — add entries to the `CONNECTION_TEXT` dict.

---

## Implementation Order for Sonnet

1. **EXITS changes in `build_mos_eisley.py`** — 24 string changes + 1 line deletion
2. **Achievement fix in `builtin_commands.py`** — remove `hasattr` guard (1 line)
3. **NPC cleanup in `combat_commands.py`** — add cleanup block (~8 lines)
4. **Quote stripping in `npc_commands.py`** — add strip line (2 locations)
5. **Punctuation fix in `combat_flavor.py`** — 1 line change
6. **Parry display in `combat.py`** — small change (~5 lines)
7. **Flavor variety in `combat_flavor.py`** — add list entries

After all changes: rebuild world, run collision audit, test tutorial playthrough.

---

## Validation Script

Include with delivery — a standalone Python script that parses the EXITS list and reports any remaining collisions. Run after every build script change.

---

*End of design document.*
