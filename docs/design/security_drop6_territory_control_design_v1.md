# Security Drop 6: Territory Control — Design Document
## SW_MUSH · April 11, 2026 · Opus Session 9

---

## 1. What This Is

Territory control lets player organizations claim rooms in contested and lawless zones, upgrade them with defenses and resources, and defend them against rival organizations. It's the endgame group PvP content and the prerequisite for Housing Drop 6 (Organization HQs).

This builds on three existing systems:
- **Security Zones** (Drops 1-5): The three-tier secured/contested/lawless model that determines what combat is allowed where
- **Organizations** (fully delivered): Factions with ranks, treasuries, payroll, equipment, leadership commands
- **Housing** (Drops 1-4): Room creation, exit linking, storage, guest lists, ownership tracking

---

## 2. Design Goals

1. **Give organizations a reason to exist beyond chat channels.** Right now factions give you equipment, a payroll stipend, and a title. Territory gives them something to fight over.

2. **Create meaningful PvP without griefing.** Territory disputes happen in lawless and contested zones, between organizations, over specific rooms. Random ganking of solo players is not the point.

3. **Make lawless zones worth the risk.** The security design doc (§7) promised territory control as the endgame reward for venturing into dangerous space. This delivers on that promise.

4. **Stay within the solo-dev resource budget.** No real-time territory warfare requiring dozens of simultaneous players. Territory shifts happen through accumulated influence, not zerging.

---

## 3. Core Concept: Influence-Based Claims

Territory control is NOT instant capture. It's an influence accumulation system:

- Organizations earn **influence points** in a zone by having members present, completing activities, and spending credits.
- When an org's influence in a zone crosses a threshold, they can **claim** rooms in that zone.
- Claimed rooms get security upgrades (lawless → contested for members), resource nodes, and defensive advantages.
- Rival organizations can **contest** a claim by accumulating their own influence, eventually forcing a handover.

This means territory changes hands over days/weeks of play, not in a 5-minute raid. A small active guild can hold territory against a larger inactive one. The Director AI narrates the ongoing struggle.

---

## 4. Influence Mechanics

### 4.1 Earning Influence

Influence is tracked per (organization, zone_environment) pair in the existing `zone_influence` table. The current Director AI already reads and writes this table for narrative purposes. Territory control repurposes it as a gameplay mechanic.

| Activity | Influence Earned | Notes |
|----------|-----------------|-------|
| Member present in zone | +1/hour | Passive; logged-in character in a room within the zone |
| NPC kill in zone | +2 per kill | Any NPC, any combat |
| Mission completed in zone | +5 per mission | Smuggling delivery, bounty collected, patrol completed |
| Zone investment | +10 per 1,000cr | `faction invest <amount>` — credits from org treasury |
| Territory upgrade installed | +20 one-time | Per upgrade purchased |
| Defending a claim (PvP win) | +15 | Winning a PvP fight in a claimed room |
| Rival member killed in zone | +10 | PvP kill in a contested/lawless zone room |

### 4.2 Losing Influence

| Activity | Influence Lost | Notes |
|----------|---------------|-------|
| No members in zone for 48h | -5/day | Decay; territory requires presence |
| Claim maintenance unpaid | -10/week | Treasury debit; if treasury empty, accelerated decay |
| Member killed in claimed room | -5 per death | Defensive failure |
| Rival org influence > yours | -2/day differential | Pressure from a challenger |

### 4.3 Influence Thresholds

| Threshold | Effect |
|-----------|--------|
| 25 | **Presence** — Org name appears in zone's `look` output: "Hutt Cartel influence is felt here." |
| 50 | **Foothold** — Org can claim rooms in this zone (`faction claim` command) |
| 75 | **Dominance** — Claimed rooms get security upgrade (lawless → contested for members). Passive income from claimed rooms. |
| 100 | **Control** — All rooms in zone show org branding. Rival orgs need 75+ influence to start contesting. Director AI treats the org as the zone authority. |

### 4.4 Influence Cap

Maximum influence per org per zone: **150**. This prevents runaway accumulation and ensures a sufficiently motivated rival can always catch up.

---

## 5. Claiming Rooms

### 5.1 Claim Command

```
faction claim              — show your org's claimable rooms in the current zone
faction claim <room_id>    — claim a specific room (costs 5,000cr from treasury)
faction unclaim <room_id>  — release a claimed room
faction territory          — show all your org's claims across all zones
```

### 5.2 Claim Rules

- Org must have **50+ influence** in the zone
- Claiming costs **5,000cr** from the org treasury (one-time)
- Weekly maintenance: **200cr/room** from treasury (same payroll tick)
- Maximum claims per zone: **3 rooms** (prevents monopolization)
- Maximum total claims per org: **10 rooms** across all zones
- Only rooms in **contested or lawless** zones can be claimed (secured zones are Imperial/government territory)
- The claiming character must be **rank 3+** in the organization
- Can only claim rooms that are NOT already claimed by another org (no instant hostile takeover — see §6 Contesting)

### 5.3 What a Claimed Room Gets

When an org claims a room, these changes apply:

1. **Security Upgrade**: If the zone is lawless, the claimed room becomes effectively **contested** for org members (they can't be attacked without consent) while remaining lawless for non-members. This is the key defensive benefit — your claimed territory is safer for your people.

2. **Room Tag**: `look` output shows `[CLAIMED — Hutt Cartel]` in the room name, color-coded to the org.

3. **Guard NPC Slot**: The org can station one NPC guard per claimed room (from the org's NPC pool, or a generic guard that the system spawns). Guards challenge non-members entering the room and fight hostile intruders.

4. **Resource Node**: Claimed rooms in lawless zones generate a passive resource every 24h (crafting material, credits, or intel items). This is the economic incentive for territory.

5. **Org Storage Access**: Members can access the org's shared armory from any claimed room (`faction armory` command).

---

## 6. Contesting Territory

### 6.1 The Contest Mechanic

Territory doesn't change hands through a single battle. It changes through sustained pressure:

1. **Rival org accumulates influence** in the zone through presence, kills, and investment (§4.1).
2. When the rival's influence reaches **75% of the holding org's influence**, a **contest** is declared automatically. The Director AI announces it: *"The Rebel Alliance is contesting Hutt Cartel territory in the Nar Shaddaa Undercity."*
3. During the contest period (7 real days), both orgs' influence decays at **2x normal rate** unless maintained by active presence.
4. If the challenger's influence **exceeds** the holder's at the end of 7 days, all claimed rooms in that zone transfer to the challenger. The Director narrates the takeover.
5. If the holder maintains higher influence, the contest ends and the challenger's influence drops by 25 (the failed assault cost).

### 6.2 PvP During Contests

During an active contest, PvP rules change in the contested zone:
- Members of the two orgs involved can attack each other **without consent** in the zone, regardless of security level (except secured zones)
- This is the territory war — actual fights matter, because kills affect influence (§4.1, §4.2)
- Non-involved players are unaffected — they still need normal PvP consent rules

### 6.3 Hostile Takeover (Lawless Only)

In lawless zones ONLY, there's an accelerated path: if the challenger kills a guard NPC in a claimed room AND has 50+ influence, they can immediately `faction claim` that specific room, even though it's currently claimed by another org. The existing claim is dissolved. This creates dramatic "raid" moments in lawless territory.

---

## 7. Schema Changes

```sql
-- New table: territory claims
CREATE TABLE IF NOT EXISTS territory_claims (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id        INTEGER NOT NULL REFERENCES organizations(id),
    room_id       INTEGER NOT NULL,
    zone_env      TEXT    NOT NULL,
    claimed_at    REAL    NOT NULL,
    maintenance   INTEGER NOT NULL DEFAULT 200,
    guard_npc_id  INTEGER DEFAULT NULL,
    upgrades      TEXT    NOT NULL DEFAULT '[]',
    UNIQUE(room_id)
);

-- New table: active contests
CREATE TABLE IF NOT EXISTS territory_contests (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_env      TEXT    NOT NULL,
    holder_org_id INTEGER NOT NULL,
    challenger_org_id INTEGER NOT NULL,
    started_at    REAL    NOT NULL,
    ends_at       REAL    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'active',
    UNIQUE(zone_env, status)
);

-- Extend zone_influence with territory-specific fields (already exists, just use it)
```

No migration needed for `zone_influence` — it already has `zone_id` (TEXT, the zone environment key), `faction` (TEXT), and `score` (INTEGER). We'll use `faction` = org code (e.g., "empire", "rebel", "hutt").

---

## 8. Integration Points

### 8.1 Security Engine (`engine/security.py`)

Extend `get_effective_security()` to check territory claims:

```python
# After Director overlay check, before property inheritance:
# If room is claimed by an org, and the querying character is a member,
# upgrade lawless → contested (member safety)
claim = await db.get_territory_claim(room_id)
if claim:
    char_org = character.get("faction_id") if character else None
    claim_org_code = await db.get_org_code(claim["org_id"])
    if char_org == claim_org_code:
        if base == SecurityLevel.LAWLESS:
            base = SecurityLevel.CONTESTED
```

**Problem**: `get_effective_security()` currently doesn't take a character argument — it returns the same security level regardless of who's asking. Territory control makes security *contextual* per character.

**Solution**: Add an optional `character` parameter to `get_effective_security()`. When provided and the room is claimed, org members get the upgraded security level. When not provided (backward compat), claimed rooms return base security. All existing call sites pass `None` initially and can be upgraded incrementally.

### 8.2 Organizations Engine (`engine/organizations.py`)

New functions:
- `claim_room(org_id, room_id, db)` — create claim record, debit treasury
- `unclaim_room(org_id, room_id, db)` — dissolve claim, remove guard
- `get_org_claims(org_id, db)` — list all claims
- `get_territory_status(org_code, zone_env, db)` — influence + claims summary
- `process_territory_maintenance(db)` — weekly tick deducts maintenance, decays influence

### 8.3 Director AI (`engine/director.py`)

The Director already tracks zone influence and uses it for narrative events. Territory control extends this:
- Director narrates when influence thresholds are crossed
- Director announces contests
- Director narrates claim changes (takeovers, abandonments)
- Territory status feeds into the Director's faction digest for richer narrative

### 8.4 Housing Drop 6 (Organization HQs)

Territory claims are the prerequisite for org HQs. An org HQ is essentially a multi-room territory claim with enhanced features (armory, barracks, meeting room, guard slots). The `territory_claims` table and the influence system serve as the foundation. Housing Drop 6 builds on top with the specific HQ room types and management commands from `player_housing_design_v1.md §2.6`.

### 8.5 Look Command (`parser/builtin_commands.py`)

Add claimed territory tag to room display:
```
Nar Shaddaa - Undercity Corridor [LAWLESS] [CLAIMED — Hutt Cartel]
```

Also show influence presence at the 25+ threshold:
```
  The Hutt Cartel's influence is felt here.
```

### 8.6 Web Client

- Territory claims appear in the HUD as a badge on the room name
- A new `faction territory` command renders an ASCII map of claims
- Contest alerts appear in the news/comms feed
- Quick buttons add `faction territory` in explore mode when the player's org has active claims

---

## 9. Tick Integration

Territory maintenance runs on the same weekly payroll tick (offset to avoid collision):

```python
# game_server.py tick loop — at offset 518400 (6 days, between payroll and housing)
if self._tick_counter % 604_800 == 518_400:
    from engine.organizations import process_territory_maintenance
    await process_territory_maintenance(self.db, self.session_mgr)
```

Territory influence accrual (passive presence) runs on a lighter hourly tick:

```python
# Every 3600 ticks (1 hour)
if self._tick_counter % 3600 == 1800:
    from engine.organizations import tick_territory_influence
    await tick_territory_influence(self.db, self.session_mgr)
```

---

## 10. Implementation Plan

### Drop 6A: Influence Gameplay (Medium)
- Wire influence earning into existing combat/mission/smuggling handlers
- `faction invest` command (treasury → influence)
- `faction influence` command (show influence across zones)
- Influence decay tick
- `look` output shows influence presence at 25+ threshold
- **No new tables yet** — uses existing `zone_influence`

### Drop 6B: Room Claiming (Medium)
- `territory_claims` table + schema migration
- `faction claim/unclaim/territory` commands
- Claim validation (influence threshold, treasury, rank)
- Weekly maintenance tick
- `look` claimed room tag
- Security upgrade for claimed rooms (lawless → contested for members)
- `get_effective_security()` character parameter extension

### Drop 6C: Guards & Resources (Medium)
- Guard NPC spawning in claimed rooms
- Guard AI (challenge non-members, fight hostiles)
- Resource node generation (daily tick, crafting materials/credits)
- `faction armory` access from claimed rooms

### Drop 6D: Contesting & PvP (Medium-Large)
- `territory_contests` table
- Auto-contest detection (rival influence threshold)
- Contest PvP rules (no-consent between rival orgs during contest)
- Contest resolution (7-day timer, influence comparison)
- Hostile takeover in lawless zones (kill guard → immediate claim)
- Director AI contest narration

### Drop 6E: Web Client & Polish (Small)
- Territory badge in HUD
- Contest alerts in news feed
- `faction territory` ASCII map
- Tooltips for territory-related UI elements

---

## 11. Interaction with Housing Drop 6 (Org HQs)

Housing Drop 6 (Organization Headquarters) builds directly on the territory claim system:

- An org HQ is a **multi-room territory claim** purchased with `faction hq purchase`
- The HQ rooms are linked to a claimed room (the HQ entrance is in claimed territory)
- HQ barracks provide Tier 2 housing for members (same as faction quarters)
- HQ armory is a shared org storage pool (extends the `faction armory` from Drop 6C)
- HQ guards use the same guard NPC system from Drop 6C but with more slots

The sequencing is: Drop 6A-6D deliver the territory system, then Housing Drop 6 adds the HQ layer on top.

---

## 12. What NOT to Build

1. **Real-time territory warfare** (siege mechanics, synchronized raids). The playerbase is too small for this. Influence accumulation is the right pacing.
2. **Territory in secured zones.** The Empire controls secured space. Period. Player orgs fight over contested and lawless zones.
3. **Automated territory defense** (turrets, mines, traps). Too complex for the current codebase. Guard NPCs are sufficient.
4. **Territory loss on org leader inactivity.** The maintenance cost + influence decay already handles this. If the treasury runs dry and nobody's present, claims naturally dissolve.
5. **Cross-planet territory wars.** Each planet's zones are independent. A Hutt claim on Nar Shaddaa doesn't affect Tatooine. This keeps the scope manageable.

---

## 13. Architecture Invariants

- **All influence changes go through a single `adjust_territory_influence()` function.** Same pattern as `perform_skill_check()` for dice rolls and `process_housing_rent()` for rent.
- **Territory claims are room-level, not zone-level.** An org claims specific rooms, not entire zones. This prevents monopolization and creates natural chokepoints.
- **Security upgrade is contextual per character.** `get_effective_security(room_id, db, character=None)` returns different results for org members vs. non-members in claimed rooms. All existing call sites continue to work with `character=None` (backward compat).
- **Contests have a fixed duration (7 real days).** No way to accelerate or skip. This prevents rapid territory flipping and gives both sides time to respond.
- **Treasury is the universal cost.** Claiming, maintenance, investment — all costs come from the org treasury. This ties territory control into the economy system.
- **Director AI is informed but not required.** Territory changes work mechanically even if the Director AI is offline. The Director adds narrative flavor but doesn't gate gameplay.

---

## 14. Files Modified/Created

| File | Change |
|------|--------|
| `engine/security.py` | Add `character` param to `get_effective_security()`, claim-based security upgrade |
| `engine/organizations.py` | Territory functions: claim/unclaim/invest, influence tick, maintenance tick, contest logic |
| `engine/territory.py` | **NEW** — Territory-specific engine: influence accrual, contest state machine, resource generation |
| `parser/faction_commands.py` | `faction claim/unclaim/territory/invest/influence` commands |
| `parser/faction_leader_commands.py` | Leader-level territory commands (claim requires rank 3+) |
| `parser/builtin_commands.py` | Claim tag in `look`, influence presence line |
| `parser/combat_commands.py` | Contest PvP no-consent override |
| `db/database.py` | `territory_claims` and `territory_contests` tables, CRUD methods |
| `server/game_server.py` | Territory maintenance tick, influence accrual tick |
| `engine/director.py` | Territory events in faction digest, contest narration |
| `static/client.html` | Territory badge, contest alerts, tooltips |

---

*End of Security Drop 6 Design Document — Version 1.0*
*Reference: security_zones_design_v1.md, organizations_factions_design_v1.md, player_housing_design_v1.md, economy_design_v02-1.md*
