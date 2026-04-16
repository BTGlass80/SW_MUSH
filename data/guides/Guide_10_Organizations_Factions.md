# SW_MUSH Detailed Systems Guide #10
# Organizations & Factions

**SW_MUSH — Star Wars D6 Revised & Expanded**
**BTGlass80 — April 2026**
**Guide Version 1.0**

---

## 1. Overview

### Player Rules

The organizations system divides into two types: **Factions** (major political groups that shape the galaxy) and **Guilds** (professional associations that provide trade bonuses). You can belong to one faction at a time and up to three guilds simultaneously.

Factions are Director AI-managed — they compete for zone influence, trigger world events, and shape the game's ongoing narrative. Guilds are simpler — they provide a 20% CP training discount and define professional communities.

---

## 2. Factions

### Player Rules

Five factions exist:

| Faction | Axis | HQ | Ranks | Stipend Range | Special Features |
|---------|------|-----|-------|---------------|-----------------|
| **Galactic Empire** | Imperial | Kessel Garrison | 7 (Recruit → Commander) | 50–500 cr/week | 4 specializations, best equipment |
| **Rebel Alliance** | Rebel | Nar Shaddaa Promenade | 6 (Sympathizer → Commander) | 25–300 cr/week | Cell missions, encrypted comms |
| **Hutt Cartel** | Criminal | Jabba's Townhouse | 6 (Associate → Vigo) | 100–500 cr/week (rank 3+) | Smuggling routes, debt collection |
| **Bounty Hunters' Guild** | Independent | Nar Shaddaa BH Quarter | 6 (Novice → Guildmaster) | None | Bounty board access, PvP override, tracking fobs |
| **Independent** | Independent | — | 1 (Freelancer) | None | Default; no affiliation |

**Joining a faction:** `faction join <name>`. You receive rank-0 equipment immediately. Switching factions has a 7-day cooldown.

**Leaving:** `faction leave`. All faction-issued equipment is reclaimed.

### Rank Progression

Each faction has 5–7 ranks with minimum reputation requirements. You earn reputation (rep) through faction-aligned actions:

| Action | Rep Gained |
|--------|-----------|
| Complete faction mission | +3 |
| Complete profession chain step | +5 |
| Kill enemy faction NPC | +1 |
| Complete bounty | +2 |
| Deliver contraband (Hutt) | +2 |
| Crafting sale | +1 |
| Faction event attendance | +1 |
| Rule violation | −5 |

When your rep reaches the next rank's threshold, you can be promoted (automatic or by a superior). Promotion issues new rank equipment.

**Example: Empire ranks**

| Level | Title | Min Rep | Equipment | Permissions |
|-------|-------|---------|-----------|------------|
| 0 | Recruit | 0 | Uniform, SE-14C pistol | — |
| 1 | Private | 10 | E-11 rifle, Stormtrooper armor | Faction comms |
| 2 | Corporal | 25 | Improved armor | Faction comms |
| 3 | Sergeant | 40 | — | Lead NPC squad |
| 4 | Lieutenant | 60 | Officer's sidearm | Issue orders, restricted access |
| 5 | Captain | 75 | — | Create missions, promote sergeants |
| 6 | Commander | 90 | — | Full faction admin |

### Imperial Specializations

When you join the Empire, you choose one of four specializations:

| Specialization | Focus | Equipment Issued |
|---------------|-------|-----------------|
| **Stormtrooper** | Ground combat | E-11 Blaster Rifle, Stormtrooper Armor |
| **TIE Pilot** | Space combat | TIE Pilot Flight Suit |
| **Naval Officer** | Command/support | Officer Uniform, Imperial Datapad |
| **Intelligence** | Stealth/slicing | Civilian Cover Package, Slicing Kit |

Type `specialize <number>` after joining.

### Faction Stipends

Weekly payroll from the faction treasury:

| Faction | Rank 1 | Rank 2 | Rank 3 | Rank 4 | Rank 5 |
|---------|--------|--------|--------|--------|--------|
| Empire | 50 cr | 100 cr | 200 cr | 350 cr | 500 cr |
| Rebel | 25 cr | 50 cr | 100 cr | 200 cr | 300 cr |
| Hutt | — | — | 100 cr | 250 cr | 500 cr |
| BH Guild | — | — | — | — | — |

Stipends are paid from the faction's treasury. If the treasury runs dry, payments stop.

### 🔧 Developer Internals

**File:** `engine/organizations.py` (~996 lines)

**Constants:**
- `FACTION_SWITCH_COOLDOWN = 604800` (7 days)
- `REP_GAINS` dict: Maps action keys to rep delta values
- `STIPEND_TABLE` dict: Maps `(faction_code, rank_level)` → credit amount
- `EQUIPMENT_CATALOG` dict: ~20 equipment items with name, slot, description
- `RANK_0_EQUIPMENT`, `RANK_1_EQUIPMENT`: Per-faction starting gear
- `IMPERIAL_SPEC_EQUIPMENT`: Per-specialization equipment

**`join_faction(char, faction_code, db, session)`** (lines 340–422):
1. Checks 7-day cooldown
2. Reclaims equipment from previous faction
3. Joins new faction via DB
4. Records cooldown timestamp
5. Issues rank-0 equipment
6. Prompts Imperial specialization if applicable
7. Clears faction_intent (tutorial migration)
8. Logs to narrative system
9. Assigns faction quarters (housing hook)

**`leave_faction(char, db, session)`** (lines 425–465): Reclaims equipment, updates DB, records cooldown, revokes faction quarters.

**`promote(char, org_code, db, promoter_char)`** (lines 546–603): Validates rep threshold, updates rank level, issues new equipment, triggers housing hook.

**`faction_payroll_tick(db)`** (lines 606–669): Called from tick loop. Iterates all faction members, checks standing and rank, pays stipend from treasury, logs disbursement.

**`adjust_rep(char, faction_code, db, action_key)`** (lines 690–725): Applies delta from `REP_GAINS`, clamps 0–100. Works for both members (DB membership table) and non-members (attributes JSON `faction_rep`).

---

## 3. Equipment Issuance

### Player Rules

When you join a faction or get promoted, you receive **faction-issued equipment** — weapons, armor, and utility items appropriate to your rank and specialization. This equipment is marked as faction-issued and will be **reclaimed** if you leave the faction.

Imperial Stormtroopers get an E-11 Blaster Rifle and Stormtrooper Armor. Rebel Operatives get a DL-18 Pistol and flight suit. Bounty Hunters get binder cuffs and a guild license. Each rank adds more gear.

### 🔧 Developer Internals

**`issue_equipment(char, org_code, db, item_keys, session)`** (lines 133–174): Adds items to inventory via `db.add_to_inventory()` with `faction_issued: True` flag. Records in `issued_equipment` table for reclamation tracking.

**`reclaim_equipment(char, org_code, db, session)`** (lines 177–206): Removes all faction-issued items for this org from inventory. Marks as reclaimed in DB. Reports count to player.

---

## 4. Guilds

### Player Rules

Six professional guilds provide trade community and a **20% CP training discount**:

| Guild | Focus | Weekly Dues |
|-------|-------|------------|
| **Mechanics' Guild** | Ship and equipment repair | 50 cr |
| **Shipwrights' Guild** | Ship modification and construction | 75 cr |
| **Medics' Guild** | Healing, bacta, combat medicine | 50 cr |
| **Slicers' Collective** | Computer intrusion, electronic warfare | 60 cr |
| **Entertainers' Guild** | Performance, music, social arts | 25 cr |
| **Scouts' Guild** | Surveying, pathfinding, wilderness | 40 cr |

**Joining:** `guild join <name>`. Max 3 guilds at once.
**Leaving:** `guild leave <name>`.

**The 20% CP discount** is the primary mechanical benefit. When you `train` a skill, guild membership reduces the CP cost. A 5 CP training costs 4 CP for a guild member. This applies to any skill, not just guild-related ones — it's a flat discount on all advancement.

### 🔧 Developer Internals

**`join_guild(char, guild_code, db)`** (lines 509–526): Checks max 3 guilds via `get_memberships_for_char()` filtering by `org_type == "guild"`.

**`get_guild_cp_multiplier(char, db)`** (lines 674–685): Returns `0.8` (1.0 − 0.20) if the character is in any guild with standing != "expelled". Called by `TrainCommand` in `cp_commands.py`.

**Guild dues:** Defined in `organizations.yaml` as `dues_weekly`. Deducted by a weekly tick handler (in `server/tick_handlers_economy.py`).

---

## 5. Director AI Integration

### Player Rules

Factions are **Director-managed** — the Director AI uses faction influence data to:
- Shift zone security levels (Imperial crackdown, criminal surge)
- Generate faction-themed world events and news
- Issue NPC faction orders (patrol assignments, raids)
- Award CP ticks for quality faction roleplay
- Publish faction digests in the news system

Player actions (killing NPCs, completing missions, smuggling) shift faction influence scores in each zone. Over weeks of play, this creates a dynamic, player-driven political landscape.

### 🔧 Developer Internals

Each faction has a `director_managed: true` flag and an `axis` property (imperial, rebel, criminal, independent) that maps to the Director's zone influence model. The `adjust_rep()` function hooks into the Director's faction digest system, and faction-related actions are logged to the narrative system for Director awareness.

---

## 6. Faction Intent (Tutorial Migration)

### Player Rules

If you chose a faction alignment during the tutorial's profession chain, your choice is remembered. When you next log in, you're automatically joined to that faction with a brief notification.

### 🔧 Developer Internals

**`faction_intent_migration(char, db, session)`** (lines 470–504): Called on login. Checks `attributes["faction_intent"]`. If set and character is still Independent, auto-calls `join_faction()`. Graceful-drop: never blocks login.

---

## 7. Commands Quick Reference

| Command | Syntax | Description |
|---------|--------|-------------|
| `faction` | `faction` | Show your faction status |
| `faction join` | `faction join <name>` | Join a faction |
| `faction leave` | `faction leave` | Leave your faction |
| `faction list` | `faction list` | List all factions |
| `faction info` | `faction info <name>` | View faction details |
| `specialize` | `specialize <1-4>` | Choose Imperial specialization |
| `guild` | `guild` | Show your guild memberships |
| `guild join` | `guild join <name>` | Join a guild (max 3) |
| `guild leave` | `guild leave <name>` | Leave a guild |
| `guild list` | `guild list` | List all guilds |

**Leader commands** (rank 4+):
| Command | Description |
|---------|-------------|
| `faction promote <player>` | Promote a member |
| `faction demote <player>` | Demote a member |
| `faction kick <player>` | Remove a member |
| `faction treasury` | View faction treasury |
| `faction invest <amount>` | Invest credits into territory influence |

---

## 8. File Reference

| File | Lines | Purpose |
|------|-------|---------|
| `engine/organizations.py` | ~996 | Faction/guild join/leave, rank progression, equipment issuance/reclamation, payroll, rep adjustment, guild CP discount, Imperial specialization, seed loader |
| `parser/faction_commands.py` | ~740 | faction/guild commands, specialize command |
| `parser/faction_leader_commands.py` | ~560 | Leader-only commands (promote, demote, kick, treasury, invest) |
| `data/organizations.yaml` | ~200 | 5 factions (with full rank tables) + 6 guilds |
| `engine/territory.py` | ~768 | Territory influence (connected to faction invest) |

**Total organizations system:** ~2,496 lines of engine/parser code + ~200 lines of data.

---

*End of Guide #10 — Organizations & Factions*
*Next: Guide #11 — Territory Control*
