# Developer Internals — Guide_11_Territory_Control.md

Extracted from `data/guides/Guide_11_Territory_Control.md` during the help-guides rework (PRELAUNCH.help_guides_rework, Phase A). This is the developer-facing track that used to live inline in the player guide; it is NOT player-facing and is NOT loaded by the game. Treat it as reference docs, and re-verify any file:line citation against HEAD before trusting it.

---

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

### 🔧 Developer Internals

**`claim_room(db, char, org_code, room_id)`** (lines 633–730) — Comprehensive validation: rank check, room exists, zone exists, character in room, not secured, influence ≥ 50, no existing claim, per-zone cap (3), total cap (10), not player housing, treasury ≥ 5,000. Creates `territory_claims` row.

**`unclaim_room(db, char, org_code, room_id)`** — Validates membership and rank. Removes claim, dismisses guard NPC if present. Does NOT refund the claim cost.

**`is_room_claimed_by(db, room_id, org_code)`** — Used by `engine/security.py::_apply_claim_upgrade()` to upgrade lawless → contested for org members. This is the bridge between territory and security.

**Weekly maintenance:** `tick_claim_maintenance(db)` — Daily tick handler checks all claims. If `treasury < maintenance`, the claim lapses (auto-unclaimed). Guard NPCs are also dismissed on lapse.

### 🔧 Developer Internals

**`spawn_guard_npc(db, claim, org_code)`** — Creates NPC using the per-org template from `_GUARD_TEMPLATES` dict (lines 76–140). Each template defines name_prefix, species, description, combat stats, weapon, and faction label. NPC is created with `combat_behavior: "aggressive"` and placed in the claimed room. The `guard_npc_id` is stored on the claim row.

**`dismiss_guard_npc(db, claim)`** — Removes the NPC from the room and clears `guard_npc_id`.

**Guard upkeep:** Added to claim maintenance. `GUARD_WEEKLY_UPKEEP = 100` cr/week on top of `CLAIM_WEEKLY_MAINT = 200` cr/week = 300 cr/week total for a guarded room.

### 🔧 Developer Internals

**`_RESOURCE_YIELDS` dict** (lines 145–162): Maps `(security, influence_tier)` to lists of `(resource_type, min_qty, max_qty, credit_bonus)` tuples.

**`tick_resource_nodes(db)`** — Daily tick. Iterates all claims, determines zone security and influence tier, rolls random yield from the appropriate pool, credits go to org treasury, resources go to org storage.

**Org storage limits:** `ORG_STORAGE_MAX_ITEMS = 50`, `ORG_STORAGE_MAX_RESOURCES = 200`.

### 🔧 Developer Internals

**`get_zone_influence_line(db, zone_id)`** (lines 536–562) — Returns a single dim line for `look` output. Uses per-org flavor text. Returns `None` if no org has ≥ 25 influence.

**`get_influence_status_lines(db, org_code)`** (lines 509–533) — Returns formatted multi-line dashboard with progress bars using `█`/`░` and ANSI colors. Sorted by score descending.

**`get_territory_digest(db)`** (lines 567–588) — Compiles `{zone_name: {org_code: score}}` dict for Director AI narrative integration.

## 7. Implementation Status

| Drop | Scope | Status |
|------|-------|--------|
| **6A** | Influence earning hooks, invest, display, decay tick | ✅ Delivered |
| **6B** | Room claiming, unclaiming, security upgrade, look tags, maintenance | ✅ Delivered |
| **6C** | Guard NPC spawning, resource node tick, org storage | ✅ Delivered |
| **6D** | Contest state machine, 7-day timer, rival org no-consent PvP, hostile takeover | Planned |
| **6E** | Web client territory badge, contest alerts, faction territory ASCII map | Planned |

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

