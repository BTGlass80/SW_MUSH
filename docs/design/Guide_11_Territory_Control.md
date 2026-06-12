# SW_MUSH Detailed Systems Guide #11
# Territory Control

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

### Player Rules

Territory Control is an influence-based system that lets player organizations claim and hold rooms in contested and lawless zones. Your faction earns influence through member activity — combat, missions, investment — and once you cross key thresholds, you can claim rooms, station guards, and generate passive income.

This is the endgame organizational content: it turns abstract faction membership into concrete territorial power with visible map presence.

---

## 2. Influence

### Player Rules

Each organization tracks an **influence score** (0–150) per zone. Influence determines what your faction can do in that zone:

| Threshold | Score | Effect |
|-----------|-------|--------|
| **Presence** | 25+ | Org name appears in `look` output |
| **Foothold** | 50+ | Can claim rooms in this zone |
| **Dominance** | 75+ | Security upgrade + passive income from claims |
| **Control** | 100+ | Full zone branding |

**Earning influence:**

| Action | Influence Gained |
|--------|-----------------|
| Member present in zone (hourly) | +1 per member |
| Kill NPC in zone | +2 |
| Complete mission/bounty/smuggling in zone | +5 |
| PvP victory in zone | +15 |
| Invest 1,000 credits from treasury | +10 |

**Investment:** `faction invest <amount>` spends org treasury credits to boost influence. Minimum 1,000 cr, maximum 10,000 cr per investment. Requires rank 3+.

**Influence decay:** If no org members are present in a zone for 48 hours, influence decays at −5 per day. Active presence resets the timer. This means you have to maintain a real presence — you can't just invest once and walk away.

### 🔧 Developer Internals

**File:** `engine/territory.py` (~1,938 lines)

**Constants:** `INFLUENCE_CAP = 150`, `THRESHOLD_PRESENCE = 25`, `THRESHOLD_FOOTHOLD = 50`, `THRESHOLD_DOMINANCE = 75`, `THRESHOLD_CONTROL = 100`.

**`adjust_territory_influence(db, org_code, zone_id, delta, reason)`** (lines 217–257) — The single entry point for ALL influence changes. Architecture invariant. Uses `INSERT ... ON CONFLICT DO UPDATE` for upsert. Clamps 0–150. Logs changes. Triggers contest checks on positive changes.

**`tick_territory_presence(db, session_mgr)`** (lines 417–458) — Hourly tick. Iterates all logged-in sessions, groups by zone and org, grants `INFLUENCE_PRESENCE_HOURLY × member_count`. Updates `last_presence` timestamp.

**`tick_territory_decay(db)`** (lines 463–485) — Daily tick. Finds orgs where `last_presence < now - 48hrs` and applies `−DECAY_RATE_PER_DAY`.

**Earning hooks:** `on_npc_kill()`, `on_mission_complete()`, `on_pvp_kill()` — Each resolves the character's room to a zone_id and calls `adjust_territory_influence()`. Hooked into `SmugDeliverCommand`, `BountyCollectCommand`, `CompleteMissionCommand`, and combat kill handlers.

**`invest_influence(db, char, org_code, amount)`** (lines 364–412) — Validates rank 3+, treasury balance, min/max amounts, secured zone block. Debits treasury, grants `(amount // 1000) × 10` influence.

**DB tables:** `territory_influence` (zone_id, org_code, score, last_activity, last_presence), `territory_claims` (room_id, org_code, zone_id, claimed_by, claimed_at, maintenance, guard_npc_id).

**Important:** Territory influence uses a SEPARATE table from the Director's `zone_influence`. Different systems, different purposes. `ORG_TO_AXIS` mapping bridges territory orgs to Director faction axes for narrative digest.

---

## 3. Room Claiming

### Player Rules

Once your org has **50+ influence** (Foothold threshold) in a zone, rank 3+ members can claim rooms:

```
faction claim                — Claim the room you're standing in
faction unclaim               — Release a claimed room
faction territory             — View all your org's claims
```

**Claiming rules:**
- Must be standing in the room to claim
- Room must be in a contested or lawless zone (secured = Imperial controlled, can't claim)
- Maximum 3 claims per zone, 10 total per org
- Costs 5,000 credits from org treasury (one-time)
- Weekly maintenance: 200 credits per room from treasury
- Player-owned housing can't be claimed
- Existing claims can't be overridden (must be contested — see Drop 6D)

**What claimed rooms get:**
- Lawless rooms are treated as **contested** for org members (PvP consent protection on your own turf)
- A visible claim tag in `look` output
- Can station a guard NPC (see section 4)
- Generate passive resource income (see section 5)

### 🔧 Developer Internals

**`claim_room(db, char, org_code, room_id)`** (lines 633–730) — Comprehensive validation: rank check, room exists, zone exists, character in room, not secured, influence ≥ 50, no existing claim, per-zone cap (3), total cap (10), not player housing, treasury ≥ 5,000. Creates `territory_claims` row.

**`unclaim_room(db, char, org_code, room_id)`** — Validates membership and rank. Removes claim, dismisses guard NPC if present. Does NOT refund the claim cost.

**`is_room_claimed_by(db, room_id, org_code)`** — Used by `engine/security.py::_apply_claim_upgrade()` to upgrade lawless → contested for org members. This is the bridge between territory and security.

**Weekly maintenance:** `tick_claim_maintenance(db)` — Daily tick handler checks all claims. If `treasury < maintenance`, the claim lapses (auto-unclaimed). Guard NPCs are also dismissed on lapse.

---

## 4. Guard NPCs

### Player Rules

Rank 3+ members can station a guard NPC in a claimed room:

```
faction guard station          — Station a guard (500 credits one-time + 100 cr/week upkeep)
faction guard dismiss          — Remove a guard
```

Guards are faction-flavored NPCs with appropriate stats, descriptions, and equipment:
- **Imperial:** Stormtrooper with E-11 rifle, white armor, 5D Blaster
- **Rebel:** Alliance sentry with A280 rifle, 4D+2 Blaster
- **Hutt:** Gamorrean enforcer with vibroaxe, 5D Brawling
- **BH Guild:** Sharp-eyed hunter with heavy blaster, 5D+1 Blaster

Guards are **aggressive** combat NPCs — they'll attack hostile intruders in the claimed room. They add weekly upkeep (100 cr) on top of the room's base maintenance (200 cr).

### 🔧 Developer Internals

**`spawn_guard_npc(db, claim, org_code)`** — Creates NPC using the per-org template from `_GUARD_TEMPLATES` dict (lines 76–140). Each template defines name_prefix, species, description, combat stats, weapon, and faction label. NPC is created with `combat_behavior: "aggressive"` and placed in the claimed room. The `guard_npc_id` is stored on the claim row.

**`dismiss_guard_npc(db, claim)`** — Removes the NPC from the room and clears `guard_npc_id`.

**Guard upkeep:** Added to claim maintenance. `GUARD_WEEKLY_UPKEEP = 100` cr/week on top of `CLAIM_WEEKLY_MAINT = 200` cr/week = 300 cr/week total for a guarded room.

---

## 5. Resource Nodes (Passive Income)

### Player Rules

Claimed rooms generate passive resources via a daily tick, scaled by zone security and influence tier:

| Security | Influence Tier | Daily Yield |
|----------|---------------|-------------|
| Contested | Foothold (50+) | 50–150 credits |
| Contested | Dominant (75+) | 100–300 credits + 1–2 metal |
| Contested | Control (100+) | 150–400 credits + 1–2 metal + 1 rare |
| Lawless | Foothold (50+) | 75–200 credits |
| Lawless | Dominant (75+) | 150–400 credits + 2–4 metal + 1–2 chemical |
| Lawless | Control (100+) | 250–600 credits + 2–4 metal + 2–4 chemical + 1–2 rare |

Resources go into org shared storage. Lawless zones yield more than contested — higher risk, higher reward.

### 🔧 Developer Internals

**`_RESOURCE_YIELDS` dict** (lines 145–162): Maps `(security, influence_tier)` to lists of `(resource_type, min_qty, max_qty, credit_bonus)` tuples.

**`tick_resource_nodes(db)`** — Daily tick. Iterates all claims, determines zone security and influence tier, rolls random yield from the appropriate pool, credits go to org treasury, resources go to org storage.

**Org storage limits:** `ORG_STORAGE_MAX_ITEMS = 50`, `ORG_STORAGE_MAX_RESOURCES = 200`.

---

## 6. Display Integration

### Player Rules

Territory influence is visible throughout the game:

**In `look` output:** When any org has 25+ influence in your zone, a presence line appears:
```
  The Empire's presence is felt here — patrols and informants.
```

For claimed rooms, a claim tag appears:
```
  [CLAIMED: Galactic Empire]
```

**In `faction influence`:** An influence dashboard with per-zone progress bars:
```
── Territory Influence ──
  Spaceport District              ████████████░░░░░░░░  65/150 [FOOTHOLD]
  Cantina District                ██████░░░░░░░░░░░░░░  30/150 [PRESENCE]
  Jundland Wastes                 ████████████████░░░░  95/150 [DOMINANT]

  Thresholds: 25 Presence · 50 Foothold · 75 Dominant · 100 Control
```

### 🔧 Developer Internals

**`get_zone_influence_line(db, zone_id)`** (lines 536–562) — Returns a single dim line for `look` output. Uses per-org flavor text. Returns `None` if no org has ≥ 25 influence.

**`get_influence_status_lines(db, org_code)`** (lines 509–533) — Returns formatted multi-line dashboard with progress bars using `█`/`░` and ANSI colors. Sorted by score descending.

**`get_territory_digest(db)`** (lines 567–588) — Compiles `{zone_name: {org_code: score}}` dict for Director AI narrative integration.

---

## 7. Implementation Status

| Drop | Scope | Status |
|------|-------|--------|
| **6A** | Influence earning hooks, invest, display, decay tick | ✅ Delivered |
| **6B** | Room claiming, unclaiming, security upgrade, look tags, maintenance | ✅ Delivered |
| **6C** | Guard NPC spawning, resource node tick, org storage | ✅ Delivered |
| **6D** | Contest state machine, 7-day timer, rival org no-consent PvP, hostile takeover | Planned |
| **6E** | Web client territory badge, contest alerts, faction territory ASCII map | Planned |

---

## 8. Commands Quick Reference

| Command | Description |
|---------|-------------|
| `faction influence` | View influence across all zones |
| `faction invest <amount>` | Invest treasury credits into zone influence |
| `faction claim` | Claim the room you're in |
| `faction unclaim` | Release a claimed room |
| `faction territory` | View all org claims |
| `faction guard station` | Station a guard NPC (500 cr + 100 cr/week) |
| `faction guard dismiss` | Remove a guard NPC |

---

## 9. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/territory.py` | ~1,938 | Influence system, claiming, guard spawning, resource nodes, decay, presence tick, Director digest, contest stub |
| `parser/faction_leader_commands.py` | ~560 | Territory commands (claim, unclaim, invest, guard) |
| `engine/security.py` | ~249 | _apply_claim_upgrade() — lawless→contested for org members |
| `engine/organizations.py` | ~996 | Faction membership, treasury management |

**Total territory system:** ~1,938 lines of dedicated engine code (the largest single engine file after combat.py and npc_space_traffic.py).

---

*End of Guide #11 — Territory Control*
*Next: Guide #12 — Player Housing*
