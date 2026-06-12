# SW_MUSH — Organizations & Factions System
## Design Document v1.0
### April 2026 · BTGlass80 · WEG D6 R&E

---

## 1. Design Philosophy

SW_MUSH needs organizations to give players a reason to care about the galactic conflict. Right now the Director AI tracks zone influence for four abstract factions (Imperial, Rebel, Criminal, Independent) and the economy design specifies six reputation factions — but neither system gives a player a *home*. Nobody salutes a zone_influence score.

Organizations fix this by giving factions mechanical teeth: membership, rank, equipment issuance, mission boards, chain of command, and — eventually — player leadership. The system has two layers:

**Factions** are the big political/thematic umbrellas. A PC belongs to exactly one faction (or Independent). Faction determines who your friends are, who your enemies are, what gear you get issued, and what orders you follow.

**Guilds** are professional sub-groups that cross faction lines. A Shipwright's Guild member could be Imperial or Independent. Guilds are primarily about economic access and CP progression — schematics, vendor discounts, workshop access. A PC can belong to multiple guilds.

The key design constraint is the **Director AI handoff model**. Most factions will launch without PC leaders. The Director AI manages them until a qualified player earns the role. This isn't a compromise — it's a feature. The Director provides consistent faction behavior from day one, and the transition to player leadership becomes a *narrative event* rather than a database flag flip.

### 1.1 Guiding Principles

**Factions should feel different to play.** An Imperial pilot and a Rebel soldier should have meaningfully different daily experiences — different mission boards, different NPC interactions, different equipment, different rules of engagement.

**No faction-locking at character creation.** Players join factions in-game, through the tutorial profession chains or through RP. The `Independent` default ensures nobody is locked out of content on day one.

**Director AI is the interim GM, not the permanent one.** Every Director-managed faction is designed to be handed off to a PC leader. The Director's job is to keep the faction alive and active until that player emerges.

**Guilds are opt-in perks, not obligations.** Guild membership should never feel like a tax. Join for the benefits, leave if you want. No penalties for non-membership.

**The system must degrade gracefully.** If the Director API is down, factions still work — scripted automation handles the routine, and player leaders handle the rest. If there are no player leaders *and* no API, factions are just standing labels with static benefits.

---

## 2. Faction Roster

### 2.1 Launch Factions

Five factions at launch, matching the existing zone_influence model plus one explicit default:

| Faction | Code | Type | Director-Managed | Notes |
|---------|------|------|-----------------|-------|
| Galactic Empire | `empire` | Political/Military | Yes (always) | NPC-led by design; a PC could lead a local garrison but not the Empire |
| Rebel Alliance | `rebel` | Political/Military | Yes (initially) | First candidate for PC leadership handoff |
| Hutt Cartel | `hutt` | Criminal | Yes (initially) | Thematically, a PC "underboss" reports to an NPC Hutt |
| Bounty Hunters' Guild | `bh_guild` | Professional | Yes (initially) | Neutral faction; takes contracts from anyone |
| Independent | `independent` | Default | No (never) | No hierarchy, no obligations, no benefits beyond universal access |

### 2.2 Faction Profiles

**Galactic Empire**

The Empire is the most structured faction. Joining means accepting rank, uniform, orders, and a chain of command. In exchange, you get the best equipment issuance in the game — TIE fighters, stormtrooper armor, E-11 blasters — all free, but none of it is *yours*. Imperial-issued gear is flagged `faction_issued: true` and is reclaimed on discharge or desertion. The Empire also provides a barracks bunk (free housing) and a weekly stipend.

Imperial characters operate under rules of engagement: no attacking civilians unprovoked, no smuggling, no dealings with known criminals. Violations are tracked and result in standing loss, demotion, or discharge. The Director AI (or a PC commanding officer) issues missions through the Imperial mission board — patrols, checkpoint duty, customs inspections, combat operations.

The Empire is intentionally the "easy mode" for new players who want structure and direction. You're told where to go, what to do, and you get paid for it. The tradeoff is freedom.

HQ Rooms: Imperial Garrison (Tatooine), Imperial Outpost (Corellia)

**Rebel Alliance**

The Rebellion is scrappier. Equipment issuance exists but is limited — you might get a blaster and a flight suit, but your X-Wing is shared with other pilots and you can't sell it. The Rebellion operates in cells: your commanding officer is your cell leader, not a distant admiral. Missions emphasize sabotage, intelligence gathering, propaganda distribution, and occasional direct action.

Rebel characters have more freedom than Imperials but more danger. The Empire considers you a criminal. Imperial zones with high alert levels will have patrols actively scanning for Rebel affiliation. Getting caught means fines, confiscation, or combat. The Rebellion compensates with higher-risk/higher-reward missions and a sense of purpose that the Empire can't match.

HQ Rooms: Rebel Safe House (Tatooine — hidden room, requires Rebel standing), Rebel Outpost (Nar Shaddaa)

**Hutt Cartel**

The Hutts don't care about your politics. They care about your reliability. Joining the Cartel means working for a Hutt boss (NPC) — running spice, collecting debts, intimidating rivals, managing territory. The Cartel provides no standard-issue equipment but gives access to the black market at reduced prices and exclusive smuggling routes with higher payouts.

Cartel members operate under omertà — you don't talk to Imperials, you don't rat on other Cartel members, and you definitely don't skim from the boss. Violations result in bounties posted on your head (by the Cartel itself). The Cartel's mission board is the most lucrative but also the most dangerous.

HQ Rooms: Jabba's Townhouse (Tatooine), Hutt Palace (Nar Shaddaa)

**Bounty Hunters' Guild**

The Guild is politically neutral. Imperial bounties, Rebel bounties, Hutt bounties — the Guild doesn't discriminate. Membership gives access to the exclusive Guild bounty board (higher-tier targets than the public board), tracking tools, and legal protection (a Guild license means you can carry weapons and hunt targets without Imperial harassment in most zones).

The Guild has the simplest structure: you hunt, you collect, you get ranked. No orders, no missions beyond what you choose from the board. Rank is earned purely by bounty completions and target tier. The Guild takes a 10% cut of all bounties collected through their board.

HQ Rooms: Bounty Office (Tatooine — already exists as tutorial room), Guild Hall (Corellia)

**Independent**

The default. No membership, no obligations, no benefits. Independents can work with anyone, go anywhere, and answer to no one. They have full access to the public mission board, public bounty board, and all vendor shops at standard prices. What they don't get: faction-specific mission boards, equipment issuance, stipends, faction vendors, or the protection that comes with belonging to something bigger.

Independent is not a faction — it's the absence of one. There's no "Independent HQ" or "Independent mission board." This is intentional. The game should make you *want* to join something.

### 2.3 Faction Relationships

Factions have standing relationships that affect gameplay:

| | Empire | Rebel | Hutt | BH Guild | Independent |
|--|--------|-------|------|----------|-------------|
| **Empire** | — | Hostile | Cautious | Tolerated | Neutral |
| **Rebel** | Hostile | — | Wary | Neutral | Neutral |
| **Hutt** | Cautious | Wary | — | Business | Neutral |
| **BH Guild** | Tolerated | Neutral | Business | — | Neutral |

These relationships affect NPC behavior. An Imperial NPC patrol will scan a Hutt Cartel member for contraband (Cautious) but won't attack on sight. A Rebel caught in an Imperial Lockdown zone gets attacked. The BH Guild's "Tolerated" status with the Empire means Guild members can openly carry weapons in Imperial zones — a significant gameplay advantage.

---

## 3. Data Model

### 3.1 DB Schema

```sql
-- Organizations (factions and guilds)
CREATE TABLE IF NOT EXISTS organizations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT    NOT NULL UNIQUE,
    code            TEXT    NOT NULL UNIQUE,       -- 'empire', 'rebel', 'bh_guild', etc.
    org_type        TEXT    NOT NULL,              -- 'faction' or 'guild'
    parent_org_id   INTEGER DEFAULT NULL,          -- For sub-units (181st → Imperial Navy → Empire)
    leader_id       INTEGER DEFAULT NULL,          -- PC leader (NULL = Director-managed or NPC-led)
    director_managed INTEGER DEFAULT 1,            -- 1 = Director AI handles this org
    hq_room_id      INTEGER DEFAULT NULL,          -- Primary HQ room
    treasury        INTEGER DEFAULT 0,             -- Faction credits pool
    description     TEXT    DEFAULT '',
    motd            TEXT    DEFAULT '',             -- Message of the day, shown on login
    created_at      REAL    NOT NULL,
    FOREIGN KEY (parent_org_id) REFERENCES organizations(id),
    FOREIGN KEY (leader_id)    REFERENCES characters(id),
    FOREIGN KEY (hq_room_id)   REFERENCES rooms(id)
);

-- Memberships
CREATE TABLE IF NOT EXISTS org_memberships (
    char_id         INTEGER NOT NULL,
    org_id          INTEGER NOT NULL,
    rank            INTEGER DEFAULT 0,             -- 0 = recruit, higher = more authority
    title           TEXT    DEFAULT 'Member',      -- Display title: 'Private', 'Underboss', etc.
    standing        TEXT    DEFAULT 'good',         -- 'good', 'neutral', 'probation', 'expelled'
    joined_at       REAL    NOT NULL,
    last_activity   REAL    DEFAULT 0,             -- Last faction-relevant action
    PRIMARY KEY (char_id, org_id),
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (org_id)  REFERENCES organizations(id)
);

-- Faction-issued equipment tracking
CREATE TABLE IF NOT EXISTS faction_equipment (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    org_id          INTEGER NOT NULL,
    item_key        TEXT    NOT NULL,               -- 'tie_fighter', 'e11_blaster', etc.
    item_instance_id INTEGER DEFAULT NULL,          -- Link to objects table if instanced
    issued_at       REAL    NOT NULL,
    reclaimed       INTEGER DEFAULT 0,              -- 1 = taken back on discharge
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (org_id)  REFERENCES organizations(id)
);

-- Faction rank definitions
CREATE TABLE IF NOT EXISTS faction_ranks (
    org_id          INTEGER NOT NULL,
    rank_level      INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    min_standing    TEXT    DEFAULT 'good',
    min_rep_score   INTEGER DEFAULT 0,             -- Minimum faction rep to hold this rank
    permissions     TEXT    DEFAULT '[]',           -- JSON array of permission strings
    PRIMARY KEY (org_id, rank_level),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Faction activity log (feeds Director digest and faction news)
CREATE TABLE IF NOT EXISTS faction_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    org_id          INTEGER NOT NULL,
    char_id         INTEGER DEFAULT NULL,           -- NULL for system/Director actions
    action_type     TEXT    NOT NULL,               -- 'join', 'promote', 'mission', 'violation', 'order', etc.
    details         TEXT    DEFAULT '',
    timestamp       REAL    NOT NULL,
    FOREIGN KEY (org_id)  REFERENCES organizations(id),
    FOREIGN KEY (char_id) REFERENCES characters(id)
);
```

### 3.2 Relationship to Existing Schema

The existing `zone_influence` table already tracks four faction codes: `imperial`, `rebel`, `criminal`, `independent`. The organizations table maps to these via the `code` field. The `hutt` org code maps to `criminal` for zone influence purposes. The `bh_guild` code does not map to any zone influence faction — the Guild is politically neutral and doesn't contest territory.

The existing character `attributes` JSON already has a reserved `"faction"` key (from economy_design_v02-1.md §8). This key now stores the character's org membership IDs rather than a standalone reputation table. Per-faction reputation scores remain in `attributes` JSON under `"faction_rep"`:

```json
{
    "faction": {
        "primary_org_id": 1,
        "guild_ids": [5, 7]
    },
    "faction_rep": {
        "empire": 45,
        "rebel": 20,
        "hutt": 60,
        "bh_guild": 30,
        "traders": 50,
        "underworld": 40
    }
}
```

This preserves the six-faction reputation model from the economy design while adding formal organizational membership.

---

## 4. Rank Systems

### 4.1 Imperial Ranks

| Rank Level | Title | Min Rep | Permissions | Equipment Issued |
|------------|-------|---------|-------------|-----------------|
| 0 | Recruit | 0 | None | Uniform, sidearm |
| 1 | Private | 10 | Faction comms | E-11 blaster, light armor |
| 2 | Corporal | 25 | — | Improved armor |
| 3 | Sergeant | 40 | Lead NPC squads (up to 3) | Sergeant insignia |
| 4 | Lieutenant | 60 | Issue orders, access restricted areas | Officer's sidearm, TIE (if pilot) |
| 5 | Captain | 75 | Faction mission creation, promote to Sgt | — |
| 6 | Commander | 90 | Full faction admin (PC leader rank) | Capital ship access |

**Imperial Specializations** (assigned at rank 1, determines equipment track):
- **Stormtrooper**: Ground combat focus. E-11, armor, grenades.
- **TIE Pilot**: Space combat focus. TIE Fighter issued at rank 1, TIE Interceptor at rank 4.
- **Naval Officer**: Command/support focus. No personal combat gear beyond sidearm. Gets crew coordination bonuses.
- **Intelligence**: Stealth/investigation focus. Civilian clothing (undercover), slicing tools, access to intelligence reports.

### 4.2 Rebel Ranks

| Rank Level | Title | Min Rep | Permissions | Equipment Issued |
|------------|-------|---------|-------------|-----------------|
| 0 | Sympathizer | 0 | Rebel safe house access | Comlink (encrypted) |
| 1 | Operative | 15 | Faction comms, cell missions | Blaster pistol, flight suit |
| 2 | Sergeant | 30 | — | Improved blaster |
| 3 | Lieutenant | 50 | Lead NPC squads (up to 3) | X-Wing assignment (shared) |
| 4 | Cell Leader | 70 | Faction mission creation, recruit | Officer's gear |
| 5 | Commander | 90 | Full faction admin (PC leader rank) | Personal starfighter |

### 4.3 Hutt Cartel Ranks

| Rank Level | Title | Min Rep | Permissions | Equipment Issued |
|------------|-------|---------|-------------|-----------------|
| 0 | Associate | 0 | Black market access | Nothing (buy your own) |
| 1 | Soldier | 15 | Cartel comms, smuggling routes | — |
| 2 | Enforcer | 35 | Debt collection authority | Heavy blaster (discounted) |
| 3 | Lieutenant | 55 | Lead NPC enforcers (up to 3) | — |
| 4 | Underboss | 75 | Cartel mission creation, territory | Personal smuggling ship (loaner) |
| 5 | Vigo | 90 | Full faction admin (PC leader rank) | — |

### 4.4 Bounty Hunters' Guild Ranks

| Rank Level | Title | Min Rep | Permissions | Equipment Issued |
|------------|-------|---------|-------------|-----------------|
| 0 | Novice | 0 | Public bounty board | Binder cuffs, Guild license |
| 1 | Journeyman | 15 | Guild bounty board (higher tiers) | Tracking fob |
| 2 | Hunter | 35 | — | Improved tracking tools |
| 3 | Senior Hunter | 55 | Post player bounties | Guild armor discount |
| 4 | Veteran | 75 | Vote on Guild matters | — |
| 5 | Guildmaster | 90 | Full faction admin (PC leader rank) | — |

### 4.5 Rep Score Changes

Rep scores use the same action-based model as zone influence, but tracked per character:

| Action | Rep Change |
|--------|-----------|
| Complete a faction mission | +3 to issuing faction |
| Complete a faction profession chain step | +5 to relevant faction |
| Kill an enemy faction NPC | +1 to opposing faction, −2 to killed faction |
| Complete a bounty (any source) | +2 to BH Guild |
| Deliver contraband successfully | +2 to Hutt, −1 to Empire |
| Get caught smuggling | −3 to Empire |
| Craft and sell to faction vendor | +1 to Traders' Guild |
| Attend a faction event (Director-generated) | +1 to that faction |
| Rule violation (tracked by Director/leader) | −5 to own faction |
| Inactivity (30+ days no faction activity) | −1/week (floor: 0) |

Rep is capped at 100. Promotion requires both minimum rep *and* a promotion action (Director auto-promotes or PC leader promotes manually).

---

## 5. Scripted Automation

These systems run deterministically on triggers. No AI needed. They work whether the Director API is up or down.

### 5.1 Onboarding Pipeline

When a PC joins a faction via the `faction join <code>` command:

```
1. Validate: PC is not already in a faction (must leave current first)
2. Insert org_memberships row (rank 0, standing 'good')
3. Set character attributes["faction"]["primary_org_id"]
4. Log to faction_log: action_type='join'
5. Fire on_faction_join(char, org) trigger:
   a. Issue starting equipment (per rank 0 table)
   b. Assign barracks/bunk room (if faction provides housing)
   c. Post welcome message to faction channel
   d. Add character to faction comms channel
   e. If faction has a specialization prompt, queue it
6. Broadcast to faction members: "[Name] has joined [Faction] as a [Title]."
```

**Imperial Specialization Flow** (fires after step 5):

```
1. Present specialization options: Stormtrooper, TIE Pilot, Naval Officer, Intelligence
2. On selection, store in attributes["faction"]["specialization"]
3. Issue specialization-specific equipment:
   - Stormtrooper: E-11 blaster rifle, stormtrooper armor
   - TIE Pilot: Flight suit, TIE/ln from faction ship pool
   - Naval Officer: Officer's uniform, datapad
   - Intelligence: Civilian clothes, slicing kit
4. Assign to relevant barracks room:
   - Stormtrooper → Barracks room
   - TIE Pilot → Pilot quarters
   - Naval Officer → Officer quarters
   - Intelligence → Civilian cover location
```

### 5.2 Equipment Issuance and Reclamation

Faction-issued items are tracked in the `faction_equipment` table. They behave like normal items but with restrictions:

- Cannot be sold to NPC vendors (sell command refuses with: "This is faction-issued equipment and cannot be sold.")
- Cannot be traded to non-faction members
- On discharge/expulsion, all faction_equipment items with `reclaimed=0` are removed from inventory and the rows updated to `reclaimed=1`
- Destroyed items are logged but not replaced automatically (replacement requires a requisition — see §6.3)

Ships issued by factions (TIE Fighters, X-Wings, loaner freighters) follow the same model but with an additional constraint: they're registered to the faction, not the pilot. The pilot has operational control but cannot modify, sell, or transfer the ship. Modification requires explicit permission from a rank 5+ leader or Director approval.

### 5.3 Payroll Tick

Runs on the existing 1s tick loop, checked once per game-day (every 86400 ticks):

```python
async def faction_payroll_tick(db):
    """Pay faction stipends to eligible members."""
    for org in await db.get_all_organizations():
        if org['treasury'] <= 0:
            continue
        members = await db.get_org_members(org['id'], min_standing='good')
        for member in members:
            rank = await db.get_faction_rank_def(org['id'], member['rank'])
            stipend = STIPEND_TABLE.get((org['code'], member['rank']), 0)
            if stipend > 0 and org['treasury'] >= stipend:
                await db.add_credits(member['char_id'], stipend)
                await db.update_org_treasury(org['id'], -stipend)
                # Log for economy tracking
```

**Stipend Table:**

| Faction | Rank 0 | Rank 1 | Rank 2 | Rank 3 | Rank 4 | Rank 5+ |
|---------|--------|--------|--------|--------|--------|---------|
| Empire | 0 | 50/wk | 100/wk | 200/wk | 350/wk | 500/wk |
| Rebel | 0 | 25/wk | 50/wk | 100/wk | 200/wk | 300/wk |
| Hutt | 0 | 0 | 0 | 100/wk | 250/wk | 500/wk |
| BH Guild | 0 | 0 | 0 | 0 | 0 | 0 |

The Bounty Hunters' Guild pays no stipends — income is purely from bounty collection. The Hutt Cartel pays nothing at lower ranks — you earn through jobs. Imperial stipends are the highest because the Empire is a proper military with a payroll.

### 5.4 Faction Treasury Income

Faction treasuries are refilled by:

- **Tax on faction missions**: 10% of mission payout goes to faction treasury
- **Faction vendor sales**: 15% markup on faction vendor items goes to treasury
- **Director injection**: The Director can inject credits during faction turns (represents off-screen logistics — Imperial supply shipments, Rebel fundraising, Hutt business income)
- **Admin command**: `@faction treasury add <code> <amount>` for manual adjustment

Treasury depletion warning fires at 10% of starting balance. If treasury hits 0, stipends stop and the Director receives a "faction financial crisis" flag in its next digest.

### 5.5 Standing and Violations

Standing tracks a member's good behavior. Three levels:

| Standing | Effect |
|----------|--------|
| Good | Full access, eligible for promotion |
| Probation | Cannot be promoted, no stipend, 30-day timer to resolve |
| Expelled | Removed from faction, equipment reclaimed, 90-day rejoin cooldown |

**Automatic standing triggers** (scripted, no AI):

- Miss 3 consecutive faction missions (if assigned by Director/leader) → Probation
- Attack a same-faction PC or NPC → Probation
- Get caught with contraband while Imperial → Probation
- Probation expires after 30 days of good behavior → Back to Good
- Second probation within 90 days → Expelled

**Director/Leader standing actions** (judgment calls):

- Promote: Director or rank 5+ PC can promote members who meet rep requirements
- Demote: Director or rank 5+ PC can demote for cause
- Pardon: Director or rank 5+ PC can lift Probation early
- Expel: Director or rank 5+ PC can expel for severe violations

---

## 6. Director AI Faction Management

### 6.1 Integration with Existing Director System

The Director AI already runs a 30-minute faction turn that processes a world-state digest and returns influence adjustments, narrative events, ambient text, and news headlines. Organization management extends this with a new section in the digest and a new output type.

**Digest Extension** (added to the existing JSON payload):

```json
{
    "faction_status": {
        "empire": {
            "member_count": 4,
            "active_last_24h": 2,
            "treasury": 15000,
            "pending_promotions": ["char_id_7"],
            "recent_violations": [],
            "unassigned_missions": 3,
            "open_requisitions": ["char_id_12: TIE replacement"]
        },
        "rebel": {
            "member_count": 2,
            "active_last_24h": 1,
            "treasury": 3000,
            "pending_promotions": [],
            "recent_violations": ["char_id_5: missed 2 missions"],
            "unassigned_missions": 0,
            "open_requisitions": []
        }
    }
}
```

Target additional payload: ~200 tokens. Total digest remains under 700 tokens.

**Output Extension** (new optional field in Director response):

```json
{
    "faction_orders": [
        {
            "faction": "empire",
            "action": "promote",
            "target_char_id": 7,
            "new_rank": 2,
            "reason": "Consistent mission completion, 3 patrol kills this week"
        },
        {
            "faction": "empire",
            "action": "post_mission",
            "mission_type": "patrol",
            "zone": "spaceport",
            "reward": 500,
            "description": "Increased rebel activity near Docking Bay 94. Patrol and report."
        },
        {
            "faction": "rebel",
            "action": "warn",
            "target_char_id": 5,
            "reason": "Two missed assignments. One more results in probation."
        },
        {
            "faction": "empire",
            "action": "approve_requisition",
            "target_char_id": 12,
            "item": "tie_ln"
        }
    ]
}
```

### 6.2 Director Decision Categories

The Director handles these judgment calls for `director_managed=1` factions:

**Promotions**: When a member meets rep requirements and has consistent recent activity, the Director recommends promotion. Promotions are logged in faction_log and announced on the faction channel.

**Mission Generation**: The Director creates faction-specific missions based on world state. Imperial crackdown in progress? More patrol missions for Imperial members. Rebel influence rising? Sabotage missions for Rebel operatives. Spice prices high? Cartel smuggling runs.

**Disciplinary Actions**: The Director issues warnings before escalating to probation. It considers context — a brand new member missing a mission gets a gentle reminder, a rank 3 member doing the same gets a formal warning.

**Equipment Requisitions**: When a member's faction-issued ship is destroyed or equipment lost, they can submit a requisition (`faction requisition <item>`). The Director approves or denies based on treasury balance, member standing, and how the equipment was lost. Losing a TIE in combat against Rebels? Approved. Crashing your TIE into an asteroid while drunk-flying? Denied, and you're on probation.

**Strategic Decisions**: The Director can order faction-wide posture changes — "All Imperial patrols to the spaceport district" or "Rebel cell goes dark for 24 hours" — which adjust NPC patrol routes, mission availability, and ambient text. These feed back into the existing zone_influence model.

### 6.3 Director System Prompt Extension

Added to the existing Director system prompt:

```
FACTION MANAGEMENT:
You also manage the internal affairs of factions marked as director_managed.
Your responsibilities:
- Promote members who meet requirements and show consistent activity
- Generate faction-appropriate missions based on current world state
- Issue warnings and discipline for rule violations
- Approve or deny equipment requisitions based on merit and treasury
- Make strategic posture decisions that affect NPC behavior

Guidelines:
- Promote conservatively. A player should feel they EARNED their rank.
- Missions should reflect the current galactic situation, not be random.
- Discipline should escalate: reminder → warning → probation → expulsion.
- Equipment requisitions approved unless the member caused the loss negligently.
- Strategic decisions should create interesting gameplay, not punish players.

When generating faction_orders, use the fixed action types:
promote, demote, warn, probation, expel, pardon,
post_mission, approve_requisition, deny_requisition,
strategic_order, faction_announcement
```

### 6.4 Validation Rules for Director Faction Orders

Same bounded-context approach as existing Director events:

- `action` must be in the VALID_FACTION_ACTIONS frozenset
- `target_char_id` must be a valid member of the specified faction
- `new_rank` for promotions cannot skip more than 1 rank level
- `mission_type` must be in VALID_MISSION_TYPES
- `reward` for missions clamped to 100–5,000 credits
- `item` for requisitions must be in the faction's equipment catalog
- Strategic orders limited to 1 per faction per turn

Invalid orders are logged and silently dropped. The faction state doesn't change.

---

## 7. Player Faction Leadership

### 7.1 The Handoff

When a PC reaches rank 5+ and the admin (or Director) designates them as faction leader:

```python
async def handoff_faction_leadership(db, org_id, new_leader_id):
    """Transfer faction from Director management to PC leadership."""
    # 1. Verify new leader is rank 5+ and standing=good
    # 2. Set organizations.leader_id = new_leader_id
    # 3. Set organizations.director_managed = 0
    # 4. Log to faction_log: action_type='leadership_handoff'
    # 5. Broadcast: "[Name] has assumed command of [Faction]."
    # 6. Grant faction leader command access
```

After handoff, the Director stops generating faction_orders for that org. The Director still includes the faction in its digest (for zone influence decisions) but defers to the PC leader for internal affairs.

The Director can be re-enabled if the PC leader goes inactive (30+ days) or voluntarily steps down. `@faction director enable <code>` toggles it back.

### 7.2 Faction Leader Commands

Available to members with rank 5+ (or the designated leader):

```
faction promote <member> [rank]     -- Promote a member (max: your rank - 1)
faction demote <member> [rank]      -- Demote a member
faction warn <member> <reason>      -- Issue a formal warning (logged)
faction probation <member>          -- Put a member on probation
faction pardon <member>             -- Lift probation
faction expel <member>              -- Expel a member (equipment reclaimed)
faction mission create <type> <reward> <desc>  -- Post a mission to faction board
faction mission assign <mission_id> <member>   -- Assign a mission to a member
faction announce <message>          -- Broadcast to all faction members
faction motd <message>              -- Set message of the day
faction treasury                    -- View treasury balance
faction requisition approve <id>    -- Approve equipment request
faction requisition deny <id>       -- Deny equipment request
faction roster                      -- Full member list with ranks/standing
faction log [n]                     -- View recent faction activity log
```

### 7.3 What Leaders Can't Do

- Promote above their own rank minus one
- Access treasury credits directly (treasury is for stipends and equipment, not personal use)
- Change faction relationships (those are hardcoded and global)
- Override admin commands
- Expel another rank 5+ member (requires admin intervention)

---

## 8. Guild System

### 8.1 Design

Guilds are simpler than factions. No ranks (just member/non-member), no equipment issuance, no Director management, no leadership handoff. Guilds are passive membership perks with optional flavor.

A character can belong to multiple guilds simultaneously. Guild membership has no faction restrictions unless explicitly noted.

### 8.2 Launch Guilds

| Guild | Code | Requirement | Benefits |
|-------|------|-------------|----------|
| Shipwright's Union | `shipwrights` | Know 2+ ship component schematics | 15% discount on ship parts, access to guild workshop rooms |
| Medical Corps | `medics` | First Aid 4D+ | Buy restricted medical supplies, +1D to heal checks in med bay rooms |
| Traders' Guild | `traders` | Complete Trader's Hall tutorial | 10% better sell prices at NPC vendors |
| Slicer's Network | `slicers` | Computer Programming/Repair 4D+ | Access to slicing tools vendor, faction intelligence data |
| Mechanics' Union | `mechanics` | Any repair skill 4D+ | 15% discount on repair parts, access to guild workshop rooms |

### 8.3 Guild Commands

```
guild list                  -- Show all available guilds and requirements
guild join <code>           -- Join a guild (if requirements met)
guild leave <code>          -- Leave a guild (instant, no penalty)
guild info <code>           -- Show guild description and member count
+guilds                     -- Show your current guild memberships
```

### 8.4 Implementation Notes

Guild benefits are implemented as modifier checks in existing systems:

- **Vendor discount**: `resolve_bargain_check()` applies guild modifier before the opposed roll
- **Restricted items**: `buy` command checks guild membership before allowing purchase
- **Skill bonus**: `perform_skill_check()` checks if character is in relevant guild AND in a guild-flagged room
- **Information access**: `+news` command shows additional intelligence entries for Slicer's Network members

No new engine files needed for guilds. The `org_memberships` table handles it, and the benefits are wired as modifiers into existing systems.

---

## 9. Integration with Existing Systems

### 9.1 Director AI Digest

The existing faction turn digest (§4.2 of director_ai_design_v1.md) gains the `faction_status` block. The Director's system prompt gains the faction management section. Budget impact is minimal — the additional payload is ~200 input tokens and ~100 output tokens per turn. At 48 turns/day, that's ~14,400 additional tokens/day, roughly $0.10/day or $3/month. Well within the $20/month budget with current headroom.

### 9.2 Zone Influence

Faction membership creates a stronger link between player actions and zone influence. Currently, killing an Imperial NPC gives +1 Rebel influence regardless of who did it. With factions:

- Killing an enemy NPC as a faction member gives +2 to your faction's zone influence (up from +1)
- Completing a faction mission gives +1 to your faction's zone influence in the mission zone
- Faction events (Director-generated) contribute +2 to the sponsoring faction's zone influence

This makes faction membership *matter* for the macro game state.

### 9.3 Economy

Faction membership modifies the economy in several ways:

- **Faction vendor access**: Each faction has exclusive vendors (e.g., Imperial Armory sells military-grade gear unavailable elsewhere)
- **Mission board filtering**: Faction members see faction-specific missions *in addition to* the public board. These missions generally pay 25% more than public equivalents.
- **Stipends**: See §5.3
- **Equipment issuance**: See §5.2
- **Black market access**: Hutt Cartel members get Tier 2–3 smuggling jobs at reduced risk (-10% patrol chance)

### 9.4 Tutorial Profession Chains

The existing profession chains (§13 of tutorial_system_design.md) already grant faction reputation on completion. With the organization system live, chain completion also triggers a faction join prompt:

- Complete "Imperial Service" chain → "Would you like to formally enlist in the Galactic Empire? (yes/no)"
- Complete "Rebel Cell" chain → "The Alliance could use someone like you. Join the Rebel Alliance? (yes/no)"
- Complete "Underworld" chain → "The Cartel has noticed your work. Become a made member? (yes/no)"
- Complete "Hunter's Mark" chain → "The Guild recognizes your skills. Join the Bounty Hunters' Guild? (yes/no)"

This creates a natural onramp from the tutorial system into faction play.

### 9.5 CP Progression

Faction activity contributes to CP ticks:

- Completing a faction mission: +10 ticks (in addition to standard mission ticks)
- Promotion: +25 ticks (one-time bonus)
- Faction event participation: +5 ticks

These are subject to the existing weekly cap of 300 ticks.

### 9.6 Communication Channels

Each faction gets a dedicated comms channel (already supported by ChannelManager):

- `imperial` — Imperial secure channel
- `rebel` — Rebel encrypted channel
- `cartel` — Hutt Cartel frequency
- `guild` — Bounty Hunters' Guild net

Auto-joined on faction membership, auto-removed on departure. Faction channels use the existing channel system — no new infrastructure.

### 9.7 PC Narrative Memory

The PC narrative memory system (pc_narrative_memory_design_v1.md) already tracks faction standing arcs. With formal organizations, the summarization pipeline gains structured data:

- Long record includes current faction, rank, title, standing
- Director annotations reference faction context ("Potential Rebel Cell leader candidate — active, well-liked, rank 4")
- Quest hooks can be faction-gated ("This character is Hutt rank 3 — eligible for Vigo promotion arc")

---

## 10. Commands Summary

### 10.1 Player Commands

| Command | Aliases | Function |
|---------|---------|----------|
| `faction join <code>` | `enlist` | Join a faction |
| `faction leave` | `resign`, `desert` | Leave current faction (equipment reclaimed) |
| `+faction` | `factioninfo`, `myfaction` | Show your faction, rank, standing, rep |
| `faction roster` | — | List members of your faction (rank 3+) |
| `faction missions` | — | Show faction-specific mission board |
| `faction requisition <item>` | — | Request replacement equipment |
| `faction channel <message>` | — | Send message on faction channel |
| `guild list` | `guilds` | Show available guilds |
| `guild join <code>` | — | Join a guild |
| `guild leave <code>` | — | Leave a guild |
| `+guilds` | `myguilds` | Show your guild memberships |

### 10.2 Faction Leader Commands (Rank 5+)

See §7.2 for full list.

### 10.3 Admin Commands

| Command | Function |
|---------|----------|
| `@faction create <n> <code> <type>` | Create a new organization |
| `@faction delete <code>` | Delete an organization |
| `@faction leader <code> <player>` | Set faction leader (triggers handoff) |
| `@faction director <enable/disable> <code>` | Toggle Director management |
| `@faction treasury add <code> <amount>` | Add credits to treasury |
| `@faction treasury remove <code> <amount>` | Remove credits from treasury |
| `@faction rank set <player> <rank>` | Admin rank override |
| `@faction standing set <player> <standing>` | Admin standing override |
| `@faction info <code>` | Full org details (admin view) |

---

## 11. Data Files

### 11.1 Faction Definitions — `data/factions.yaml`

```yaml
empire:
  name: "Galactic Empire"
  type: faction
  director_managed: true
  description: "The Galactic Empire maintains order through military strength."
  hq_rooms:
    tatooine: "Imperial Garrison"
    corellia: "Imperial Outpost"
  specializations:
    - stormtrooper
    - tie_pilot
    - naval_officer
    - intelligence
  starting_equipment:
    stormtrooper: ["e11_blaster", "stormtrooper_armor"]
    tie_pilot: ["flight_suit", "tie_ln"]
    naval_officer: ["officer_uniform", "hold_out_blaster"]
    intelligence: ["civilian_clothes", "slicing_kit"]
  rank_titles:
    0: "Recruit"
    1: "Private"
    2: "Corporal"
    3: "Sergeant"
    4: "Lieutenant"
    5: "Captain"
    6: "Commander"
  stipends:
    0: 0
    1: 50
    2: 100
    3: 200
    4: 350
    5: 500

rebel:
  name: "Rebel Alliance"
  type: faction
  director_managed: true
  description: "The Alliance to Restore the Republic fights for freedom."
  hq_rooms:
    tatooine: "Rebel Safe House"
    nar_shaddaa: "Rebel Outpost"
  specializations: []
  starting_equipment:
    default: ["encrypted_comlink", "blaster_pistol"]
  rank_titles:
    0: "Sympathizer"
    1: "Operative"
    2: "Sergeant"
    3: "Lieutenant"
    4: "Cell Leader"
    5: "Commander"
  stipends:
    0: 0
    1: 25
    2: 50
    3: 100
    4: 200
    5: 300

hutt:
  name: "Hutt Cartel"
  type: faction
  director_managed: true
  description: "The Hutt crime families control the Outer Rim's shadow economy."
  zone_influence_code: "criminal"
  hq_rooms:
    tatooine: "Jabba's Townhouse"
    nar_shaddaa: "Hutt Palace"
  specializations: []
  starting_equipment:
    default: []
  rank_titles:
    0: "Associate"
    1: "Soldier"
    2: "Enforcer"
    3: "Lieutenant"
    4: "Underboss"
    5: "Vigo"
  stipends:
    0: 0
    1: 0
    2: 0
    3: 100
    4: 250
    5: 500

bh_guild:
  name: "Bounty Hunters' Guild"
  type: faction
  director_managed: true
  description: "The Guild regulates the bounty hunting profession across the galaxy."
  hq_rooms:
    tatooine: "Bounty Office"
    corellia: "Guild Hall"
  specializations: []
  starting_equipment:
    default: ["binder_cuffs", "guild_license"]
  rank_titles:
    0: "Novice"
    1: "Journeyman"
    2: "Hunter"
    3: "Senior Hunter"
    4: "Veteran"
    5: "Guildmaster"
  stipends: {}

independent:
  name: "Independent"
  type: faction
  director_managed: false
  description: "No faction affiliation. Free to work with anyone."
  hq_rooms: {}
  specializations: []
  starting_equipment: {}
  rank_titles: {}
  stipends: {}
```

### 11.2 Guild Definitions — `data/guilds.yaml`

```yaml
shipwrights:
  name: "Shipwright's Union"
  type: guild
  description: "Master builders and modifiers of starships."
  requirement:
    type: "schematics_known"
    min_count: 2
    category: "ship_component"
  benefits:
    vendor_discount: 0.15
    room_bonus_skill: "space_transports_repair"
    room_bonus_amount: 1

medics:
  name: "Medical Corps"
  type: guild
  description: "Healers and field medics across the galaxy."
  requirement:
    type: "skill_minimum"
    skill: "first_aid"
    min_dice: 4
    min_pips: 0
  benefits:
    restricted_items: ["bacta_tank_supplies", "surgical_kit"]
    room_bonus_skill: "first_aid"
    room_bonus_amount: 1

traders:
  name: "Traders' Guild"
  type: guild
  description: "Honest merchants and legitimate commerce."
  requirement:
    type: "tutorial_complete"
    tutorial: "traders_hall"
  benefits:
    sell_price_bonus: 0.10
    trade_route_info: true

slicers:
  name: "Slicer's Network"
  type: guild
  description: "Information brokers and code breakers."
  requirement:
    type: "skill_minimum"
    skill: "computer_programming_repair"
    min_dice: 4
    min_pips: 0
  benefits:
    restricted_items: ["slicing_kit_advanced", "data_spike"]
    intel_access: true

mechanics:
  name: "Mechanics' Union"
  type: guild
  description: "Repair specialists and technical experts."
  requirement:
    type: "skill_minimum_any"
    skills: ["space_transports_repair", "repulsorlift_repair", "starship_weapon_repair"]
    min_dice: 4
    min_pips: 0
  benefits:
    vendor_discount: 0.15
    room_bonus_skill: null
    room_bonus_amount: 1
```

---

## 12. Implementation Plan

### 12.1 Files to Create

| File | Contents |
|------|----------|
| `engine/organizations.py` | OrgManager singleton: join/leave/promote/demote, payroll tick, onboarding pipeline, equipment issuance/reclamation, standing management |
| `parser/faction_commands.py` | Player faction commands: join, leave, +faction, roster, missions, requisition |
| `parser/faction_leader_commands.py` | Leader commands: promote, demote, warn, probation, expel, mission create, announce |
| `parser/guild_commands.py` | Guild commands: list, join, leave, +guilds |
| `parser/faction_admin_commands.py` | Admin @faction commands |
| `data/factions.yaml` | Faction definitions (see §11.1) |
| `data/guilds.yaml` | Guild definitions (see §11.2) |

### 12.2 Files to Modify (via patch)

| File | Changes |
|------|---------|
| `db/database.py` | Add organizations, org_memberships, faction_equipment, faction_ranks, faction_log table DDL + CRUD methods |
| `server/game_server.py` | Wire OrgManager init, faction commands registration, payroll tick |
| `engine/director.py` | Add faction_status to digest, parse faction_orders from response |
| `engine/skill_checks.py` | Add guild bonus modifier to perform_skill_check |
| `parser/combat_commands.py` | Add faction kill rep hook |
| `parser/mission_commands.py` | Add faction mission tick and rep hook |
| `parser/smuggling_commands.py` | Add Hutt rep modifier |
| `engine/economy.py` (or buy/sell commands) | Add guild/faction vendor discount modifier |
| `engine/cp_engine.py` | Add faction activity tick sources |
| `build_mos_eisley.py` | Add HQ room creation, faction channel setup |

### 12.3 Delivery Sequence

**Drop 1: Schema + Core Engine** — `data/factions.yaml`, `data/guilds.yaml`, DB schema additions, `engine/organizations.py` (OrgManager with join/leave/standing logic, no Director integration yet), `parser/faction_commands.py` (join, leave, +faction). Players can join factions and see their status.

**Drop 2: Equipment + Onboarding** — Onboarding pipeline, equipment issuance/reclamation, specialization flow (Imperial), barracks assignment. Joining a faction now *does something visible*.

**Drop 3: Faction Missions + Payroll** — Faction-specific mission board, payroll tick, treasury system, stipends. Faction membership now has economic value.

**Drop 4: Rank + Director Integration** — Rank definitions, promotion/demotion logic, Director digest extension, Director faction_orders parsing. Factions are now actively managed by the Director AI.

**Drop 5: Leader Commands + Guilds** — Player leader commands, handoff mechanism, guild system (join/leave/benefits). Full system live.

**Drop 6: Integration Patches** — Wire faction bonuses into skill checks, combat hooks, CP ticks, economy modifiers, tutorial chain prompts, narrative memory. Everything talks to everything.

Each drop is independently useful. Drop 1 alone lets players identify with a faction. Drops 1–3 work without the Director API.

---

## 13. Architecture Doc Changes

The following sections should be added/modified in the architecture document for v17:

**New section: §19 Organizations & Factions**
- Subsections: Faction Model, Guild Model, Rank System, Director Integration, Player Leadership
- References this design doc for full specification

**Modified: §3.4 Database Layer**
- Add organizations, org_memberships, faction_equipment, faction_ranks, faction_log to schema v9

**Modified: §3.5 Tick Loop**
- Add faction payroll tick (every 86400 ticks)

**Modified: §4 Director AI (or cross-reference director_ai_design_v1.md)**
- Note faction_status digest extension and faction_orders output type

**Modified: §12 Economy**
- Add faction vendor discounts, guild vendor discounts, faction stipends, equipment issuance
- Reference faction treasury income/outflow

**Modified: §15.4 Communication Channels**
- Add faction channels: imperial, rebel, cartel, guild

**Modified: §16 Completed Features** (when delivered)
- Add line for each completed drop

**Modified: §17 Remaining Roadmap**
- Priority C (Faction Reputation) status → Subsumed by Organizations & Factions system

---

## 14. Open Questions

1. **Should desertion have narrative consequences beyond equipment loss?** An Imperial who deserts could get a bounty posted. A Rebel who turns coat could be flagged by Director for Imperial Intelligence recruitment. This adds flavor but complexity.

2. **Faction PvP rules?** Currently combat is unrestricted. Should same-faction PvP be prohibited, penalized, or free? Recommendation: penalized (standing loss) but not blocked — MUSH culture values player agency.

3. **Cross-faction cooperation?** Can an Imperial and a Rebel team up? Mechanically yes, but should there be rep penalties? Recommendation: no mechanical block, but NPC reactions change (Imperial patrol sees you with a known Rebel? Suspicion.).

4. **Guild advancement?** Current design is binary (member/not). Should guilds have ranks too? Recommendation: not at launch. Keep guilds simple. Add ranks later if there's demand.

5. **Faction ship pools?** TIE Fighters come from a faction ship pool. How large? Unlimited (abstracted as "the Empire has lots of TIEs") or finite (creates interesting scarcity)? Recommendation: unlimited for now. Finite pools add bookkeeping without proportional fun for a small playerbase.

6. **Sub-organizations at launch?** The schema supports parent_org_id for nesting (181st Fighter Group → Imperial Navy → Empire). Worth building sub-orgs now or defer? Recommendation: defer. Schema is ready; UI and Director logic can wait.

7. **Faction-locked planets?** Should Kessel be Hutt-controlled (requiring Hutt standing to dock freely)? Recommendation: not at launch. All planets open. Add faction-controlled zones as an expansion once the playerbase supports territorial conflict.

---

*End of Organizations & Factions Design Document — Version 1.0*
*Reference: director_ai_design_v1.md, economy_design_v02-1.md, tutorial_system_design.md, pc_narrative_memory_design_v1.md, sw_d6_mush_architecture_v16.md*
