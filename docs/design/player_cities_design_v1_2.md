# Player Cities — Design v1.2

**Status:** Locked decisions, ready for implementation breakdown
**Author:** Brian + Claude (design session, May 2026)
**Builds on:** `player_housing_design_v1.md` (Tier 5 Org HQ), `security_drop6_territory_control_design_v1.md` (territory claims, contests), `Guide_11_Territory_Control.md`, `organizations_factions_design_v1.md`, `wilderness_system_design_v1.md`, `clone_wars_era_design_v3.md`
**Era:** Clone Wars (~20 BBY). Republic vs. CIS. No Rebel/Imperial framing.

**Changelog from v1.1:**
- New §21: Territory contestation for cities (Drop 6D integration)
- New §22: Raid window mechanic (replaces Drop 6D's instant hostile takeover for city tiles)
- New §23: Variable guard density (1/2/3 tiers by tile type)
- §7 (NPC guards) updated to reference variable density
- §8.4 (hostile takeover out of scope) replaced — it's now in scope via §21–§22
- Wilderness regions gain per-zone influence (small extension to `wilderness_system_design_v1.md`)
- Drop 6D is now a hard prerequisite for shipping cities

**Changelog from v1:**
- Added §18 (Wilderness City Variant), §19 (Hidden City Mode), §20 (Director Encounter Exposure)
- Schema fields for wilderness/hidden cities
- Phased delivery extended with wilderness phases

---

## 0. What this is and isn't

**This is:** an extension of the existing Tier 5 Organization HQ system from "single multi-room building" to "claimed cluster of contiguous rooms forming a player-governed city."

**This is not:** a new economy, a new combat layer, a new server-load mechanic, or a real-time-warfare PvP system. It explicitly inherits Drop 6's principle that **the playerbase is too small for siege mechanics**. Cities grow and dissolve through influence and treasury, not through coordinated raids.

The pitch in one sentence: a player organization that has built up enough HQ infrastructure can claim multiple contiguous rooms in a contested or lawless zone, designate them as a city, install a governance layer, collect taxes from city activity, and grant member privileges. SWG city governance was a top-tier retention driver; this is the WEG-D6-shaped version of that.

---

## 1. Locked decisions

- **Cities are organization-owned**, not individual-owned. A city is always a property of a faction or guild.
- **Cities require an existing Org HQ** as the city center. You cannot found a city without first building an HQ.
- **Cities exist only in contested or lawless zones, OR in wilderness regions.** No player cities in secured zones — the Republic (or local government) controls those areas.
- **Two city variants exist:** *settled cities* (zone-based, hand-built rooms — see §1–§17) and *frontier cities* (wilderness coordinate-based — see §18). Same schema, same governance, different founding flow and exposure profile.
- **City rooms are still claimed via the existing territory-control system.** A city is a *cluster of claims under unified governance*, not a parallel claim mechanism.
- **Cities have a hard size cap** scaling with HQ tier. Small Outpost = 5-room city, Chapter House = 10-room city, Fortress = 20-room city.
- **Tax revenue feeds the org treasury** and is the city's economic engine.
- **Mayor role** is a designated org member (default = org leader, can be delegated). Mayor handles day-to-day commands; org leadership controls structural decisions.
- **NPC guards scale with city size and influence** — bigger cities, more guards.
- **Cities cannot expand into another org's claimed territory** — implicit conflict resolution. Two orgs adjacent to each other simply have two cities.
- **City naming is owner-controlled** with an admin moderation hook (no slurs, no impersonating canon Star Wars locations like "Mos Eisley" if it's a system zone name).

---

## 2. Founding a city

### 2.1 Prerequisites

To found a city, the organization must have:

1. An existing Tier 5 Organization HQ (any size — Small Outpost, Chapter House, or Fortress)
2. The HQ must be located in a contested or lawless zone (per existing HQ rules)
3. **At least 50 influence in the zone** where the HQ resides (per existing territory mechanics — same threshold as a single room claim)
4. **Treasury balance ≥ founding cost** (see §2.3)
5. **Org rank requirement:** Only the org leader (rank 5+) can found a city. The leader can delegate the Mayor role afterward.

### 2.2 The founding process

```
[Org leader stands in their HQ entrance room]
        ↓
+city found <name>
        ↓
[Validation: prereqs met, name not duplicate, name not reserved]
        ↓
[Treasury debited founding cost]
        ↓
[HQ rooms designated as City Center (read-only — these are always part of the city)]
        ↓
[City created in active state with 0 expansion rooms claimed]
```

The city's **City Center** is the HQ itself — those rooms are immutable, always part of the city, and cannot be unclaimed without dissolving the city entirely.

### 2.3 Founding cost (one-time)

| HQ Tier | Founding Cost | Max City Size |
|---|---|---|
| Small Outpost (3–5 rooms) | 25,000 cr | 5 expansion rooms (~10 total with HQ) |
| Chapter House (5–8 rooms) | 75,000 cr | 10 expansion rooms (~18 total with HQ) |
| Fortress (8–12 rooms) | 200,000 cr | 20 expansion rooms (~32 total with HQ) |

The founding cost is a one-time sink. **Expansion rooms are claimed individually after founding** using the existing territory-claim costs (see Drop 6).

### 2.4 Why these numbers

- **25,000 cr Small Outpost city** — about 6 weeks of small-org weekly stipends. Cheap enough that a new guild can aim for it; expensive enough that frivolous founding doesn't happen.
- **200,000 cr Fortress city** — endgame milestone, requires sustained group activity and treasury management. Roughly the cost of a fully-loaded ship.
- **Size cap scaling** — prevents a Small Outpost from accreting a Fortress-sized city without earning the upgrade. Org HQ upgrades are the gating mechanism for city size.

---

## 3. Expanding a city

### 3.1 Claiming expansion rooms

After founding, the city expands by claiming additional rooms via the existing territory-claim system:

```
+city claim <room-id-or-direction>
```

- Must be **contiguous** — the claimed room must share an exit with an existing city room (City Center or already-claimed expansion).
- Must be in the **same zone** as the City Center (cross-zone cities are not supported — keeps complexity manageable).
- Must respect the **size cap** for the city's HQ tier.
- Costs the standard territory-claim treasury debit (per Drop 6: 5,000 cr per room).
- Requires sufficient influence (per Drop 6: each new claim consumes a portion of zone influence).

### 3.2 Releasing rooms

```
+city release <room>
```

- Removes a room from the city.
- Refunds 50% of the claim cost to the treasury (matches housing sell-back rate).
- Cannot release the City Center (HQ rooms) — those require dissolving the entire city.
- Useful for shrinking a city that's become too maintenance-heavy.

### 3.3 Maximum expansion rate

To prevent overnight land-grabs, expansion is **rate-limited**: max 1 new claim per 24 hours per city. This forces deliberate growth and gives rival orgs time to react via influence accumulation.

---

## 4. City governance

### 4.1 Roles

| Role | Default | Granted By | Permissions |
|---|---|---|---|
| **Founder** | Org leader at founding | Immutable | Can dissolve the city; reassign Mayor; set tax rates; transfer founding control with org leadership transfer |
| **Mayor** | Org leader (initially same as Founder) | Founder via `+city mayor <player>` | Day-to-day governance: set city motd, approve room descriptions, manage NPC guard placement, banish (see §4.4), set ambient tone |
| **Citizen** | Any org member | Implicit by org membership | Rest bonus inside city, free movement, use city services, participate in city events |
| **Guest** | Anyone via Mayor approval | `+city guest add <player>` | Free movement, no rest bonus, cannot use restricted services |
| **Outsider** | Anyone not in the above | Default | May enter contested-zone city rooms; may not enter restricted rooms; pays visitor tax on transactions |

### 4.2 Mayor commands

```
+city motd <text>           — Set the city's motd shown on entry
+city tax view              — View current tax rates
+city tax set <rate>        — Set city tax rate (0%–10%)
+city guards                — View NPC guards stationed in city
+city guards assign <npc>   — Station an NPC guard in current room
+city guards remove <npc>   — Recall an NPC guard
+city guest add <player>    — Add player to city guest list
+city guest remove <player> — Remove player from city guest list
+city banish <player>       — Banish a player from the city for 30 days
+city unbanish <player>     — Lift a banishment
+city events                — View scheduled city events / Director-AI flavor
```

### 4.3 Founder-only commands

```
+city mayor <player>        — Assign or change Mayor (founder only)
+city dissolve              — Dissolve the city (irreversible, all rooms unclaimed)
+city ratecap <pct>         — Set max tax rate the Mayor can choose (default 10%)
```

### 4.4 Banishment

A banished player cannot enter any city room (including the City Center) for the duration. Attempted entry shows a "you are not welcome here" message and they bounce back to the previous room.

- Banishment lasts 30 days by default
- Stacks across cities — banishing in one city does not banish in another
- Cannot banish org leadership of rival orgs without admin approval (anti-griefing)
- Admin can void a banishment with `@city void-banish`

---

## 5. Taxation

### 5.1 What gets taxed

The city's tax rate (0%–10%, set by Mayor) applies to:

| Activity | Tax basis |
|---|---|
| Vendor droid sales | Tax % of each sale within city |
| Bargain transactions with city-zone NPC vendors | Tax % of transaction |
| Sabacc house rake | City takes Tax % of the rake (so a 10% rake at 5% city tax = 0.5% to city) |
| Bounty board postings *within city* | Tax % of posting fee |
| Faction stipend collection by visitors | No (only citizens collect stipends, and citizens are exempt) |

### 5.2 What does NOT get taxed

- Citizen-to-citizen credit transfers
- Bank deposits/withdrawals
- Crafting (no taxation point — crafting doesn't have a transaction)
- Movement, communication, or any free action
- Ship docking fees (those go to the planet's spaceport, not the city)
- Faction stipends (those come from org treasury, not city economy)

### 5.3 Tax flow

```
[Player buys widget for 1000 cr from vendor droid in city]
        ↓
[Vendor takes its 1000 cr, deducts existing 1-2% listing fee]
        ↓
[City tax (e.g., 5%) = 50 cr deducted from vendor's net]
        ↓
[50 cr → city treasury (which is the org treasury, tagged as city revenue)]
```

City revenue is **tagged in the org treasury** so the Mayor can see how much the city is generating week over week. This visibility is important for governance feedback.

### 5.4 Tax rate tradeoffs

- **0% tax:** City is a magnet for vendors and visitors but generates no revenue. Good for newly-founded cities trying to bootstrap.
- **5% tax:** Sweet spot. Generates meaningful revenue without driving away commerce.
- **10% tax (max):** Maximum extraction. Drives away vendors who can find lower-tax alternatives. Director AI may flag this in narrative ("merchants grumble about the punishing tax rates in [city]").

The 10% cap exists because:
- Higher rates drive business out of the city entirely (no income at all).
- Anti-griefing — a hostile takeover Mayor can't bleed members dry.
- WEG R&E has historically modeled "oppressive taxation" as a flavor element of authoritarian-controlled worlds, not as a stacking economic mechanic.

### 5.5 Visitor vs citizen taxation

By default, **citizens pay city tax just like visitors do** — a city's tax falls equally on everyone doing business there. A future v2 could add a `+city tax citizens-exempt` toggle for cities that want to favor members, but this adds accounting complexity and is deferred.

---

## 6. Citizen benefits

A citizen of a city (= an org member of the city's owning organization) gets:

### 6.1 Rest bonus
- Logging out inside any city room counts as logging out at home (per the existing housing rest-bonus mechanic).
- This works even if the citizen has no personal Tier 1–4 housing.
- Rest bonus applies to City Center rooms and expansion rooms equally.

### 6.2 Security upgrade
- City rooms in contested zones are treated as **secured for citizens** but **contested for non-citizens**. This is the same mechanic Drop 6 applies to claimed rooms; cities just extend it across more rooms.
- City rooms in lawless zones are treated as **contested for citizens** but **lawless for non-citizens** — citizens still aren't fully safe in lawless space, but they get consent-gated PvP rather than open PvP.

### 6.3 Citizen-only rooms
- The Mayor can flag specific city rooms as **citizen-only**. Non-citizens (including guests) cannot enter.
- Use case: barracks, treasury vault, war room, private chambers.
- Limit: at most 30% of city rooms can be citizen-only. The City Center HQ rooms count as citizen-only by default and don't reduce the available 30%.

### 6.4 City teleport (limited)
- `+city home` from anywhere on the same planet teleports the citizen to the City Center entrance room.
- 1-hour cooldown.
- Disabled if the citizen is in combat, in space, or off-planet.
- This is the same logic as the personal `home` command but pointed at the city.

---

## 7. NPC guards

### 7.1 Guard slots scale with city size

| HQ Tier | HQ Guard Slots (existing) | Additional City Guard Slots | Total |
|---|---|---|---|
| Small Outpost | 2 | 3 | 5 |
| Chapter House | 4 | 6 | 10 |
| Fortress | 6 | 14 | 20 |

The total guard pool is split between HQ slots (which station inside the HQ structure) and city-level slots (which station on expansion tiles). City-level guard slots can be placed on expansion tiles OR clustered on the City Center entrance per the variable-density rules in §23. Mayor-level command.

### 7.2 Guard behavior

- Guards challenge non-citizens in citizen-only rooms (existing behavior).
- Guards engage hostile non-citizens in any city room when:
  - The non-citizen has attacked a citizen in this combat session
  - The non-citizen is a banished player attempting entry
  - The non-citizen has an active bounty claimed by a citizen BH
- Guards do not attack random outsiders just for being non-citizens. Cities are public spaces by default.

### 7.3 Guard cost

- Each guard costs 200 cr/week from city treasury (= org treasury) for upkeep.
- A maxed-out Fortress city with 20 guards costs 4,000 cr/week in guard upkeep alone.
- Guards stop functioning if treasury is depleted (per existing HQ rules).

---

## 8. City decay and dissolution

### 8.1 Maintenance costs

City weekly maintenance, paid from org treasury:

| Component | Weekly Cost |
|---|---|
| HQ base maintenance (existing) | 500 / 1,000 / 1,500 cr |
| Per expansion room | 100 cr |
| Per NPC guard | 200 cr |

A 10-room expansion city with 8 guards and a Chapter House HQ pays: 1,000 + (10 × 100) + (8 × 200) = **3,600 cr/week**.

### 8.2 Treasury depletion behavior

When the org treasury cannot cover maintenance:

1. **Week 1:** Guards stop functioning. City still works, but defenses are down.
2. **Week 2:** Citizen-only flags are removed (all rooms become public). Mayor cannot apply new flags.
3. **Week 3:** Tax collection ceases. The city becomes economically dormant.
4. **Week 4:** City automatically dissolves. All expansion rooms unclaimed, HQ reverts to standalone HQ status. City Founder receives a notification.

This 4-week grace period gives the org time to refill the treasury or wind down the city deliberately.

### 8.3 Dissolution — Founder action

The Founder can dissolve the city at any time with `+city dissolve`. This:
- Confirmed via a 30-second prompt.
- Refunds 25% of expansion-room claim costs to the treasury (less generous than voluntary release because it's a bulk action).
- HQ reverts to standalone HQ.
- All citizen banishments are voided.
- Director AI receives a narrative event to mention in flavor text.

### 8.4 Hostile takeover

Cities are contestable through the Drop 6D mechanics (influence contests + raid window). See §21 for full city-level contestation rules and §22 for the raid window mechanic that replaces Drop 6D's single-guard hostile takeover for city tiles. The City Center HQ remains protected by existing Tier 5 HQ rules (treasury depletion or admin only) and cannot be raided directly.

---

## 9. Director AI integration

The Director AI receives city status in its faction digest:

- Active cities and their owners
- City sizes (rooms claimed)
- Recent treasury health (delta over the last week)
- Recent citizen activity (logins in city, transactions, kudos)
- Banishment events
- Founding and dissolution events

The Director uses this for:
- **Ambient narration** — "Word in the Coronet spaceport is that the [Org] settlement on the outskirts is thriving" / "...struggling" / "...has been abandoned"
- **Faction action prompts** — A rival faction may take influence-building actions in zones near a successful enemy city
- **Ambient faction NPC dialogue** — citizens of nearby NPC settlements reference player cities organically
- **News broadcasts** — A new city founding is a planetary news event

This is purely flavor — the Director cannot dissolve a city, change tax rates, or otherwise affect city mechanics.

---

## 10. Schema additions

```sql
CREATE TABLE IF NOT EXISTS player_cities (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    org_id          INTEGER NOT NULL,
    hq_id           INTEGER NOT NULL,
    zone_id         INTEGER,                        -- NULL for wilderness cities
    is_wilderness   INTEGER NOT NULL DEFAULT 0,     -- 0 = settled, 1 = frontier
    wilderness_region_id INTEGER,                   -- non-NULL when is_wilderness=1
    wilderness_x    INTEGER,                        -- city center coords (= HQ landmark)
    wilderness_y    INTEGER,
    is_hidden       INTEGER NOT NULL DEFAULT 0,     -- 1 = hidden city (Search-gated)
    search_difficulty INTEGER DEFAULT 20,           -- when is_hidden=1
    visibility_factions TEXT DEFAULT '[]',          -- JSON list of faction codes that auto-discover
    founded_at      REAL NOT NULL,
    founder_id      INTEGER NOT NULL,
    mayor_id        INTEGER NOT NULL,
    tax_rate        REAL NOT NULL DEFAULT 0.0,      -- 0.0 to 0.10
    rate_cap        REAL NOT NULL DEFAULT 0.10,     -- founder-set max
    motd            TEXT DEFAULT '',
    state           TEXT NOT NULL DEFAULT 'active', -- active | grace | dissolved
    grace_started_at REAL DEFAULT 0,
    revenue_total   INTEGER DEFAULT 0,
    revenue_week    INTEGER DEFAULT 0,
    week_start_ts   REAL NOT NULL,
    FOREIGN KEY (org_id) REFERENCES organizations(id),
    FOREIGN KEY (hq_id) REFERENCES org_hqs(id),
    FOREIGN KEY (founder_id) REFERENCES characters(id),
    FOREIGN KEY (mayor_id) REFERENCES characters(id)
);

CREATE TABLE IF NOT EXISTS player_city_rooms (
    city_id     INTEGER NOT NULL,
    room_id     INTEGER NOT NULL,
    is_center   INTEGER NOT NULL DEFAULT 0,    -- 1 = HQ room, 0 = expansion
    citizen_only INTEGER NOT NULL DEFAULT 0,
    claimed_at  REAL NOT NULL,
    PRIMARY KEY (city_id, room_id),
    FOREIGN KEY (city_id) REFERENCES player_cities(id)
);

CREATE TABLE IF NOT EXISTS player_city_banishments (
    city_id     INTEGER NOT NULL,
    char_id     INTEGER NOT NULL,
    until       REAL NOT NULL,
    issued_by   INTEGER NOT NULL,
    issued_at   REAL NOT NULL,
    PRIMARY KEY (city_id, char_id)
);

CREATE TABLE IF NOT EXISTS player_city_guests (
    city_id     INTEGER NOT NULL,
    char_id     INTEGER NOT NULL,
    added_by    INTEGER NOT NULL,
    added_at    REAL NOT NULL,
    PRIMARY KEY (city_id, char_id)
);

CREATE INDEX idx_city_rooms_room ON player_city_rooms(room_id);
CREATE INDEX idx_city_org ON player_cities(org_id);
CREATE INDEX idx_city_zone ON player_cities(zone_id);
CREATE INDEX idx_city_wilderness ON player_cities(wilderness_region_id, wilderness_x, wilderness_y);
```

The `player_city_rooms` table is the lookup primary used by `look`, movement, and tax-collection code. A room belongs to at most one city. For wilderness cities, "rooms" are the landmark rows in the `rooms` table that anchor the city center and each expansion claim — same table, just rows that also have `wilderness_region_id`/`x`/`y` set.

---

## 11. Command surface

### 11.1 Player commands (informational)

| Command | Function |
|---|---|
| `+city info` | Show info about the city you're standing in (or your home city if not in one) |
| `+city map` | ASCII map of the current city |
| `+city citizens` | List online citizens of the current city |
| `+city tax view` | View tax rate of the current city |
| `+city home` | Teleport to your home city's center (1-hour cooldown) |
| `+city list` | List all known player cities (planet-scoped) |

### 11.2 Mayor commands (see §4.2)

### 11.3 Founder commands (see §4.3)

### 11.4 Founding/expansion

```
+city found <name>          — Found a new city (requires HQ + 50 influence + treasury)
+city claim <direction>     — Claim adjacent room as expansion
+city release <room>        — Release expansion room
```

### 11.5 Admin commands

```
@city list                  — All cities, all planets
@city inspect <name>        — Detailed city status (treasury history, banishments, citizens)
@city void-banish <city> <player>   — Lift admin-flagged banishment
@city dissolve <name>       — Force dissolve (admin moderation)
@city rename <name> <new>   — Admin rename
```

---

## 12. Look output integration

When inside a city room, `look` adds:

```
Coronet - South Market District [CONTESTED] [CITY: Veiled Hand Compound]
  ─ A Veiled Hand citizen will find this area secured.
  ─ Mayor: Tara Vex
  ─ Tax rate: 5%

A bustling market square...
```

When the player is a citizen, the security upgrade is reflected in the badge ("CONTESTED" → "SECURED" for that player). When the player is banished:

```
Coronet - South Market District [CONTESTED] [CITY: Veiled Hand Compound]
  ⚠ You are not welcome here. Move along.
```

---

## 13. Phased delivery plan

### Phase 1: Schema + founding/dissolution
- All `player_cities` / `player_city_rooms` / `player_city_banishments` / `player_city_guests` tables
- `+city found`, `+city dissolve` commands
- Tax rate field present but no tax collection yet
- HQ-as-City-Center linkage
- **Effort:** Small. ~0.5 sessions.

### Phase 2: Expansion + claim integration
- `+city claim`, `+city release` commands
- Contiguity validation
- Size-cap enforcement
- 24-hour expansion rate-limit
- Hook into existing Drop 6 territory-claim infrastructure
- **Effort:** Medium. ~1 session.

### Phase 3: Governance
- Mayor / Founder role assignments
- All `+city motd / guards / guest / banish` commands
- Citizen-only room flagging
- Look output integration
- **Effort:** Medium. ~1 session.

### Phase 4: Taxation
- Tax collection hook into vendor droid sales, NPC vendor transactions, sabacc rake, bounty postings
- Treasury tagging (city revenue tracking)
- Director AI digest integration
- **Effort:** Medium. ~1 session.

### Phase 5: Citizen benefits
- Rest bonus extension
- Security upgrade for citizens (extend Drop 6's `get_effective_security()`)
- `+city home` teleport
- **Effort:** Small. ~0.5 sessions.

### Phase 6: Polish
- Maintenance tick + grace period state machine
- Web client UI: city panel, citizen list, tax stats
- Help topics
- Admin tooling
- **Effort:** Medium. ~1 session.

**Settled-city subtotal:** ~5 sessions.

### Phase 7: Wilderness city variant (frontier cities — see §18)
- `is_wilderness` schema field active
- `+city found` accepts wilderness coords as City Center anchor
- Expansion via adjacent-tile claiming (replaces room-exit contiguity)
- Wilderness landmark rows generated for each claimed expansion tile
- Founding cost +50% applied
- **Effort:** Medium. ~1 session.

### Phase 8: Hidden city mode (see §19)
- `is_hidden` + `search_difficulty` + `visibility_factions` fields active
- Outsider visibility gated through existing `wilderness_discoveries` table
- `+city reveal` Mayor command (publish coords to a player)
- Citizen auto-discovery on first entry
- **Effort:** Small-Medium. ~0.5–1 session.

### Phase 9: Director encounter exposure (see §20)
- Wilderness city event roll on the Director's weekly tick
- CW-era event table (Separatist landing, Republic recon, raider party, sandstorm damage, etc.)
- Treasury / function impact resolution
- Look-output flagging of recent events
- **Effort:** Medium. ~1 session.

**Wilderness-extension subtotal:** ~2.5–3 sessions.
**Total (settled + frontier):** ~7.5–8 sessions.

---

## 14. Open questions

1. **Multiple cities per organization.** Can one org found cities on different planets? Recommend: yes, but each requires its own HQ. Cities are planet-scoped; an org with three HQs across three planets can run three cities. Lock as default.

2. **Tax exemptions for crafting guilds.** Should crafter-focused guilds be able to set a "no tax on crafting-material vendors" exemption? Defer — crafting transactions aren't taxed in v1 anyway.

3. **City-vs-city diplomacy.** Should adjacent cities be able to formalize a non-aggression pact, trade agreement, or shared defense? Future feature. For v1, cities are mutually independent and any cooperation is via free-form RP.

4. **City reputation.** Should a city have a separate reputation score that affects merchant willingness, NPC behavior, etc.? Future feature. The org's existing standing handles this implicitly.

5. **Founding cost discounts.** Should founding be discounted if the org has high zone influence? Defer — the founding cost is meant to be a real commitment.

6. **Naming reservations.** Should certain names be reserved (canonical Star Wars locations like "Mos Espa," "Theed")? Recommend: yes, maintain a blocklist in code. Canon-naming is a slippery slope and admin moderation is a backstop.

7. **Visual city emblems / flags.** Should the city have a customizable emblem rendered in the web client HUD? Future polish — defer.

---

## 15. Architecture invariants

- A room belongs to **at most one city**. Enforced at insert time.
- City Center rooms (HQ) cannot be released individually — only the entire city dissolves.
- The Founder is immutable for the city's lifetime. If the org leadership transfers, the new leader can dissolve and re-found.
- Tax collection runs through a single `apply_city_tax(transaction)` function. No bypass paths.
- All city state transitions go through `process_city_event()`. No shortcuts.
- The 24-hour expansion rate-limit is per-city, persisted to DB. Cannot be reset by reload.
- City teleport (`+city home`) shares the same cooldown infrastructure as personal `home`.

---

## 16. Test plan

### Unit / integration

- Found a city; verify schema, HQ linkage, treasury debit.
- Claim a non-contiguous room; verify rejection.
- Exceed size cap; verify rejection.
- Dissolve a city; verify all expansion rooms unclaimed, treasury refunded correctly.
- Banish a player; verify movement bounce.
- Tax flow: vendor sale in city, verify city treasury increment.
- Treasury depletion: simulate 4 weeks of insufficient funds, verify state machine progression.

### Manual / GM

- Found a Small Outpost city, expand to 5 rooms, walk through citizen vs. non-citizen experience.
- Set tax to 10%, observe Director AI flavor text appearance over a week.
- Hostile non-citizen attacks a citizen in a city room; verify guard response.
- Banish a player, attempt re-entry; verify message and bounce.

---

## 17. Documentation updates required

- `Guide_11_Territory_Control.md` — add city section, point to this doc.
- `Guide_10_Organizations_Factions.md` — add Mayor role, link to city governance.
- `player_housing_design_v1.md` — note that Tier 5 HQs can be expanded into cities.
- `security_drop6_territory_control_design_v1.md` — note that cities are clusters of claims with unified governance.
- `Guide_06_Economy.md` — note that vendor sales in cities incur city tax.
- New help topic: `+help city` covering all citizen-facing commands.
- `wilderness_system_design_v1.md` — note that frontier cities anchor at remote-HQ wilderness landmarks (§18).

---

## 18. Wilderness City Variant (Frontier Cities)

### 18.1 Why this variant exists

The settled-city design (§1–§17) is the right answer for groups operating in canon-anchored zones — Coronet docks, Nar Shaddaa promenade, the Theed outskirts. But a different archetype wants a different home: groups who want **distance from canon**, **autonomy from local government**, and **tax revenue worth fighting for in a frontier setting**.

In MMO terms, the wilderness variant is the EVE low-sec / null-sec equivalent. Higher reward potential, higher risk surface, and a different relationship with discoverability. The settled variant is high-sec by analogy — protected by zone rules, lower revenue ceiling, but stable.

The mechanic is one system. Variants differ in founding flow, exposure, and a few cost knobs.

### 18.2 What changes

| Aspect | Settled City | Frontier (Wilderness) City |
|---|---|---|
| Location | Contested or lawless zone room | Wilderness coordinates inside a region |
| Founding cost | Per §2.3 | +50% on §2.3 (frontier construction is harder) |
| HQ entrance | Hand-built room | Wilderness landmark row (real `rooms` entry with coords) |
| Expansion | Adjacent room via shared exit | Adjacent tile in same region (cardinal/diagonal) |
| Default security | Inherits zone (contested or lawless) | Inherits region (typically lawless) |
| Hidden mode available | No (zone rooms are public) | Yes — see §19 |
| Director event exposure | Minimal (existing zone hooks) | Active (see §20) |
| Tax revenue ceiling | Standard | +25% (lower commerce competition; remote location premium) |
| Visitor traffic | Typically higher | Typically lower; citizens-only by default for hidden mode |

### 18.3 Founding a frontier city

Prerequisites are the same as §2.1 with two modifications:

1. **HQ must be a wilderness Tier 5 variant** (`faction_hq_remote` per `wilderness_system_design_v1.md` §6.4). A settled HQ in a city zone cannot anchor a frontier city.
2. **Influence requirement** is replaced by **regional faction-influence threshold** — the org must have ≥30% of the region's faction-influence tilt (per `wilderness_system_design_v1.md` §6.5). This is coarser than the per-zone influence used for settled cities; wilderness regions don't have per-tile claims.

Founding command takes the wilderness coordinates of the existing remote HQ implicitly:

```
+city found <name>           — Founds at the HQ's wilderness landmark coords
```

The HQ's landmark becomes the City Center; further expansion claims tiles adjacent to it.

### 18.4 Expansion in the wilderness

```
+city claim <direction>      — Claim adjacent wilderness tile (n / ne / e / se / s / sw / w / nw)
```

Each claimed tile becomes a **landmark row in `rooms`** with `wilderness_region_id`/`x`/`y` set, plus a `player_city_room` row linking it to the city. Players moving through the region see the tile as a city expansion landmark instead of empty terrain.

Claim validation:
- Must be **orthogonally or diagonally adjacent** to an existing city tile.
- Must be **within the same wilderness region** as the City Center.
- Must respect the **size cap** for the city's HQ tier (§2.3).
- Must not conflict with another existing landmark at those coordinates (one tile, one landmark).
- Costs the standard claim treasury debit (5,000 cr per tile, matches §3.1).

The 24-hour rate limit (§3.3) still applies.

### 18.5 Tile-level descriptions

Each claimed tile gets a builder-controllable description, just like settled-city expansion rooms. Default: a generic "an outpost building of [city name]" line that the Mayor can override with `+city describe <coords>` while standing on the tile.

### 18.6 Movement into and within frontier cities

Citizens entering a frontier city tile from adjacent wilderness see standard city look output (per §12) overlaid on the wilderness terrain banner:

```
Dune Sea (24, 18) [LAWLESS] [CITY: Aurek Compound]
  ─ A Aurek Compound citizen will find this area secured.
  ─ Mayor: Ren Calidar
  ─ Tax rate: 6%

A cluster of prefab structures rises from the dunes...
```

Outsiders without visibility see the underlying terrain only — no city banner, no Mayor info — unless the city is non-hidden (see §19).

### 18.7 Frontier city benefits

In addition to the standard citizen benefits (§6):

- **Wilderness rest bonus stacks normally.** Logging out in a frontier city tile counts as logging out at home, like any other city.
- **No water/stamina drain inside city tiles.** Once inside the city footprint, citizens are out of the harsh wilderness — the frontier-city bubble functions as a habitable enclave.
- **Bonus to wilderness `search` rolls in surrounding tiles** for citizens (+1D, capped). The city's presence gives its members an awareness of their territory.

### 18.8 Frontier city costs

In addition to standard maintenance (§8.1):

- **+50% founding cost** as noted in §18.2.
- **+50% per-tile maintenance** (150 cr/week vs. 100 cr/week settled). Wilderness logistics are expensive.
- **Higher Director event exposure** — see §20.

---

## 19. Hidden City Mode

### 19.1 What it is

A frontier city can be founded in **hidden mode**, in which case the city is not visible to outsiders unless they:

1. Successfully roll `search` on the city's center tile against the configured difficulty,
2. Are members of a faction in the city's `visibility_factions` list, or
3. Have been explicitly granted coords by a citizen via the existing `share coords` mechanic.

This is the frontier-city analogue of EVE's "you have to find my space before you can affect it" property. Hidden cities have lower visitor traffic (and thus lower visitor-tax revenue) but much lower exposure.

Hidden mode is a **founding-time choice**. A founder cannot toggle it later — that would invite exploit patterns where you flip-flop visibility based on who's online. Re-founding is the path if the org changes its mind.

### 19.2 Hidden city configuration

| Field | Default | Range | Effect |
|---|---|---|---|
| `is_hidden` | 0 | 0 or 1 | Master toggle |
| `search_difficulty` | 20 | 15–30 | Search target for outsider discovery |
| `visibility_factions` | `[]` | JSON list of faction codes | Auto-discover for these factions |

A search_difficulty of 15 (Moderate) makes the city findable by any reasonably skilled scout. 25 (Difficult) makes it a serious investment. 30 (Heroic) makes the city effectively private — only contacts (via shared coords) and faction allies will find it.

### 19.3 Outsider perception

When an outsider stands on the City Center tile of a hidden city and has not discovered it:

- The tile renders as standard wilderness terrain (no city banner).
- A `search` command at sufficient skill reveals the city — a `wilderness_discoveries` row is written, and from then on the tile shows the full city banner to that outsider.
- The Mayor optionally receives a notification when an outsider discovers their hidden city. This is a privacy-vs-paranoia toggle: `+city alerts on/off`.

Once discovered by an outsider, that outsider can navigate to the city normally. The discovery is per-character, not global. A discovered hidden city does not become "publicly known" — each outsider has to find it themselves (or be told).

### 19.4 Citizens and hidden cities

- Citizens auto-discover the city on the first time they enter a citizen room. No search roll needed.
- Citizens can `+city share <player>` to grant a non-citizen the discovery (writes a `wilderness_discoveries` row directly). This is the "I'll bring my friend home" mechanic.
- A Mayor can `+city share` more broadly without a per-player limit, but it logs to the city event log so the org can see who got told.

### 19.5 Frontier city visibility recap

| City Type | Visibility |
|---|---|
| Settled (zone-based) | Public — no hiding mechanism |
| Frontier, not hidden | Public to anyone in the wilderness region |
| Frontier, hidden | Citizens auto-discover; outsiders need search/share/faction |

### 19.6 Hidden mode is not invincibility

A hidden city still has Director event exposure (§20). Director-narrated events that "happen to" the city happen whether or not it's hidden — the Director represents the universe at large, not specific PCs trying to find you. A Separatist landing party finding your settlement is an event, not a Search roll.

---

## 20. Director Encounter Exposure

### 20.1 Why frontier cities have it

Settled cities have implicit risks — zone influence shifts, rival orgs in the same neighborhood, contested-zone rules. Frontier cities operate in lawless wilderness where those forces don't apply. Without compensating risk, the frontier variant becomes pure upside ("more revenue, no downsides"), which collapses the design.

The Director encounter system provides that risk. It's also the only model that fits — Drop 6 explicitly forbids siege mechanics ("the playerbase is too small"), so the threat must be **environmental and Director-driven**, not coordinated PvP.

This is the EVE low-sec sov-attack equivalent, modeled with NPCs and Director narration instead of an alliance of 200 players. Clone Wars era specifically: Separatist incursions, Republic recon sweeps, opportunistic raiders, hostile native fauna.

### 20.2 The weekly event roll

Once per week, on the same tick as city maintenance, the Director rolls for each active frontier city:

- **Roll d100** against an exposure threshold.
- **Default exposure: 15** (15% chance of an event per week).
- **Modifiers:**
  - +5 per 5 expansion tiles claimed (visibility scales with footprint)
  - −5 if hidden mode (harder to target what you can't see — but doesn't drop to 0)
  - −5 if the city's region has a "low traffic" Director state
  - +5 if the city's region has a "high traffic" Director state (Separatist push, Republic operation, etc.)

A maxed Fortress hidden city in a quiet region: ~15% per week. A wide-open Small Outpost in an active region: ~30% per week.

### 20.3 Event table (Clone Wars era)

When an event fires, the Director rolls on a region-flavored table. Generic CW-era events:

| Roll | Event | Effect |
|---|---|---|
| 1–20 | **Separatist landing party** | B1/B2 droid squad spawns near city; if not driven off in 24h real time, treasury debited 1,000 cr per remaining tile |
| 21–35 | **Republic recon sweep** | Clone troopers visit; faction-locked outcome (see §20.4) |
| 36–50 | **Hostile native incident** | Region-appropriate creatures (krayt dragons on Tatooine, akk dogs on Haruun Kal, etc.) damage city — treasury debited 500–2,000 cr |
| 51–65 | **Opportunistic raider band** | NPC pirates / Death Watch / Hutt enforcers attempt theft; citizens can engage to defend |
| 66–80 | **Supply chain disruption** | Tax revenue halved for the next week |
| 81–90 | **Severe weather / environmental** | All NPC guards stunned for 24h real time; city defenseless |
| 91–95 | **Refugee influx** | NPCs spawn requesting shelter; Mayor decision affects faction reputation |
| 96–100 | **Director-curated narrative event** | Hand-authored by Director AI, often quest-hook-shaped |

This is the v1 table. Each region can override or extend with regional flavor (Tatooine: Tusken raid > Separatist landing; Coruscant Underworld: Crimson Dawn agents > Republic recon, etc.).

### 20.4 Faction-locked outcomes

The Republic recon sweep event resolves differently based on the city's owning org's faction:

- **Republic-aligned org:** Friendly inspection; Mayor optionally hosts officers, gains minor faction rep.
- **CIS-aligned org:** Hostile encounter; clones may impound treasury or arrest citizens. Real consequences if the city can't bribe or fight off.
- **Neutral / fringe org:** Probing visit; bribery option (1,000–5,000 cr) closes the event quietly. Refusal escalates to repeated visits.

This makes the city's faction allegiance matter mechanically. A neutral Hutt-aligned settlement on Republic-friendly Tatooine pays a recurring "tax" to keep the clones moving on. A CIS-aligned cell on a Republic-leaning world has the inverse problem — Republic patrols are the recurring threat.

### 20.5 Defending against events

- **NPC guards engage hostile spawn events automatically.** A well-defended city with 8 guards will probably handle a raider band; a Small Outpost with 3 guards will struggle.
- **Citizens can engage**, and citizen response is the core gameplay hook — a Director event creates a real reason for the org to convene at the city. This is content generation, not just a tax.
- **The 24-hour real-time response window** is the key tuning parameter. Long enough that an active org can respond; short enough that absentee orgs lose treasury and learn to be present.
- **Mayor-issued alerts** broadcast to all online citizens: "[City] is under attack — Separatist droids spotted in the western quarter." The web client surfaces this in the news feed.

### 20.6 Event narration

The Director AI writes the event prose. A Separatist landing event reads like a small adventure — droid squad descriptions, terrain advantages, a B1 commando captain or tactical droid speaking aggressively. The mechanical resolution is treasury / faction / NPC, but the *experience* is a story beat.

### 20.7 Exposure cap

To prevent runaway loss spirals, no city can take more than one event per week, and a successfully-defended event grants 1 week of immunity to further events ("the area has been quiet since"). This caps catastrophic compounding.

### 20.8 Schema additions for §20

```sql
CREATE TABLE IF NOT EXISTS player_city_events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id         INTEGER NOT NULL,
    event_type      TEXT NOT NULL,        -- 'separatist_landing' | 'republic_sweep' | etc.
    fired_at        REAL NOT NULL,
    resolves_at     REAL NOT NULL,        -- 24h after fire by default
    state           TEXT NOT NULL DEFAULT 'active',  -- active | defended | unresolved | mayor_resolved
    treasury_impact INTEGER DEFAULT 0,
    faction_rep_delta TEXT DEFAULT '{}',   -- JSON of faction code → delta
    narrative       TEXT DEFAULT '',
    FOREIGN KEY (city_id) REFERENCES player_cities(id)
);

ALTER TABLE player_cities ADD COLUMN last_event_at REAL DEFAULT 0;
ALTER TABLE player_cities ADD COLUMN event_immunity_until REAL DEFAULT 0;
```

---

## 21. Territory Contestation for Cities

### 21.1 The decision

Cities are contestable through Drop 6D's existing influence-contest mechanic, with one city-specific extension: **if all of a city's expansion tiles transfer to a challenger, the City Center automatically dissolves**, the city collapses, and the HQ reverts to a standalone HQ in whatever zone it sits in. This is the EVE-low-sec analogue — sustained organizational pressure can take a city, but only sustained pressure.

### 21.2 How a city contest works

1. **Challenger accumulates influence** in the city's zone (settled cities) or wilderness region (frontier cities) through the standard Drop 6D earning hooks: presence, NPC kills, missions, PvP victories, treasury investment.
2. **Contest auto-fires** when the challenger's influence reaches **75% of the holder's influence**, per Drop 6D §6.1.
3. **Contest period: 7 real days.** Both sides' influence decays at 2× normal rate during the contest unless maintained by active presence. The contesting orgs gain no-consent PvP rights against each other in the contested zone (Drop 6D §6.2).
4. **Resolution at 7 days:**
   - If the challenger's influence exceeds the holder's, **all expansion tiles transfer** to the challenger. They become claims of the challenger's organization. The challenger inherits the visual claim tags and the security upgrade.
   - If the holder retains the lead, the challenger loses 25 influence (failed assault cost, per Drop 6D §6.1).
5. **City collapse check.** If the resolution leaves the city with **zero remaining expansion tiles** (i.e., all were transferred), the city collapses:
   - The city record is set to `dissolved` state.
   - All citizen-only flags are voided.
   - All banishments are voided.
   - The HQ rooms revert to standalone HQ status (the HQ continues to exist, but it's no longer a city).
   - The Founder receives a notification.
   - Director AI receives a high-priority narrative event.
   - The challenging org keeps the transferred expansion tiles as ordinary claims (NOT a new city — they'd have to found one separately if they want one).

### 21.3 Why expansion tiles transfer to the challenger, not get destroyed

Two reasons:
- **Resources stay valued.** A successful conqueror inherits the build-out of the city they took. This rewards the conquest meaningfully.
- **Fewer state transitions.** Tiles becoming claims of the new owner is mechanically simpler than tiles being destroyed and re-established.

The conquering org doesn't get the city's name, motd, or governance state — those die with the city. They get the rooms.

### 21.4 City Center remains protected

The City Center HQ rooms are **not contestable** through this mechanic. They follow existing Tier 5 HQ rules — treasury depletion (4 weeks) or admin action. This is the design contract: HQs are durable; cities (the cluster of claims around them) are contestable.

A conqueror who takes all expansion tiles ends the city but does not take the HQ. The defeated org keeps their HQ, just without the city wrapped around it. They can re-found a new city if they rebuild influence and treasury.

### 21.5 Wilderness regions get per-zone influence

For frontier cities to be fully contestable, **wilderness regions must support per-zone influence the same way zone-based areas do**. This is a small extension to `wilderness_system_design_v1.md` §6.5, which currently has only coarse "regional faction-influence tilt."

The change:
- Each wilderness region is treated as a single zone for Drop 6 influence purposes.
- Influence accrual hooks (presence, kills, missions, PvP) fire when characters are in the region's tiles, exactly as they fire in zone rooms.
- The `zone_influence` table gets rows keyed by `(org, wilderness_region_id)`.
- Frontier city contests fire and resolve through the same Drop 6D state machine as settled-city contests.

The "regional faction-influence tilt" mentioned in the wilderness design is preserved as a coarser **derived** signal for Director AI and the player-facing wilderness UI; it's now a function of the per-zone influence rather than a separate value.

### 21.6 Per-tile PvP in wilderness is unchanged

Per-tile PvP (combat between players on the same wilderness tile) works exactly as it does today — governed by the existing security level and PvP consent rules. No changes. What's added is per-region influence accrual; what's NOT added is per-tile influence claiming or per-tile contests. That would be the "tedious PvP and micro-management" the wilderness design correctly avoids.

The **city** as a contestable unit has tile-level mechanics (raid window per §22), but those are city-specific, not wilderness-general.

### 21.7 Schema additions for §21

No new tables. Drop 6D's existing `territory_contests` table handles city contests as well — a contest's entries reference the zone, and at resolution time the contest resolution code checks whether any of the transferred claims belong to a city. If yes, the city-collapse check (§21.2) runs.

```sql
-- Existing table from Drop 6D, no changes needed:
-- territory_contests (id, zone_id, challenger_org, holder_org, started_at, ends_at, state)

-- Wilderness extension (small):
ALTER TABLE zone_influence ADD COLUMN wilderness_region_id INTEGER DEFAULT NULL;
-- When wilderness_region_id is non-null, this row is for a wilderness region rather than a zone.
-- zone_id may also be non-null for backwards compatibility; treatment is mutually exclusive.
```

### 21.8 Drop 6D is now a hard prerequisite

Player cities cannot ship before Drop 6D. Without contestation, cities are pure upside with no swap mechanic — exactly the design failure §20 (Director events) was added to mitigate. Director events provide environmental risk, but they don't let *players* fight for territory. Drop 6D does.

The roadmap implication: Drop 6D moves up to before the cities feature can deliver. (Drop 6D was already "Planned" in the existing roadmap; this just hardens the dependency.)

---

## 22. Raid Window Mechanic

### 22.1 Why this replaces single-guard hostile takeover for cities

Drop 6D's hostile takeover mechanic (kill guard + 50 influence → instant claim transfer) works fine for **individual non-city claims** — small stakes, single-room target, a successful raid is proportionate. But it's catastrophic for cities because:

- Most city tiles have 0–1 guards (guard pool spread thin across many tiles)
- WEG D6 guards die quickly to a competent party
- No cooldown means repeated attempts
- No defender notification means raids happen invisibly
- Cumulative effect: a 4-player party could take a Small Outpost city in 3 days through expansion-tile attrition, without ever winning a contest

That's vandalism, not territory swap. It also breaks the Drop 6 design principle that "territory changes hands over days/weeks of play, not in a 5-minute raid." Cities need a different mechanic.

### 22.2 The raid window

When attackers kill all guards on a city expansion tile (per §22.4), instead of an instant claim transfer:

1. **The tile enters a raid window** lasting 7 real days.
2. During the raid window:
   - The tile's resource node generation is **disabled**.
   - The tile's citizen-only flag is **suspended** (citizens lose their security upgrade on this tile).
   - The tile shows a **`[RAIDED]`** tag in look output, citizen and outsider visibility alike.
   - Citizen-only access restrictions are lifted (the tile becomes effectively public).
   - The city treasury takes a **one-time 1,000 cr penalty** at raid start.
3. After 7 days, the raid window expires and the tile reverts to normal city-tile state — unless raided again, in which case the window resets.
4. Defenders can **clear the raid window early** by killing or driving off the attacking party still in the tile. If the tile is empty of attackers for 24 continuous hours after the initial raid, the window auto-clears (the raiders moved on, the city secured the area).

### 22.3 Sustained raids escalate to city contest

If a single attacker org raids **50% or more of a city's expansion tiles within a rolling 14-day window**, a city-level contest auto-fires per §21.2 — the standard Drop 6D 7-day contest, with the attacker as challenger.

This is the path to actually taking a city: prove sustained pressure through raids, then the system promotes that pressure to a contest. Raids alone don't take cities; raids prove you have the operational tempo to force a contest, and the contest swaps territory.

If 50% of tiles get raided but the attacks are spread across multiple distinct attacker orgs, no auto-contest fires. The city is just being beleaguered — Director AI flavor narrates this, but no swap mechanic triggers.

### 22.4 What "kill all guards" means

Per the Option A decision (variable guard density §23 + raid trigger):

- A tile with 1 guard requires killing that 1 guard.
- A tile with 2 guards requires killing both, in a single combat session.
- A tile with 3 guards (City Center, where this matters most) requires killing all 3 in a single combat session.
- "Single combat session" = the standard combat session boundary; if combat ends with surviving guards, no raid credit even if survivors are weak.
- If the attackers retreat or are repulsed before all guards fall, surviving guards remain and the raid attempt fails. No partial credit.

### 22.5 City Center cannot be raided

The City Center HQ rooms are **not eligible for the raid window mechanic**. Killing all guards on the HQ entrance does not open a raid window. The HQ is protected by Tier 5 HQ rules end-to-end. Attackers wanting to take a city must do it through the contest mechanic (§21), which never targets the HQ directly — the HQ falls only as a consequence of city collapse from total expansion-tile loss.

This is the load-bearing rule that makes cities defensible. If the City Center could be raided like any other tile, the whole strategic depth collapses.

### 22.6 Defender notification

When a raid window opens on a tile, the system broadcasts a **defender alert** to all online citizens of the city:

```
⚠ ALERT: [Tile name] in [City name] has been raided.
  Resources disabled. Security suspended for 7 days unless cleared.
```

This alert fires at raid start. It does NOT fire at "guards being attacked" — the alert is for the consequence, not the initial combat. (The combat alerting is handled by §23.5 for multi-guard tiles.)

The Mayor and Founder receive a more detailed report including which tile, who raided (if known from combat logs), and current raid count toward the 50%-in-14-days threshold.

### 22.7 Guard respawn pace

After a successful raid:
- Killed guards on that tile are **gone immediately** (not auto-respawning).
- Defenders can pay full re-station cost (200 cr each per Mayor command `+city guards assign <tile> <count>`) to replace them at any time, including during the raid window.
- A fresh guard placed during the raid window does NOT clear the raid window (the resource/security debuffs persist for the full 7 days even if guards are restored).
- A guard placed during the raid window IS subject to attack again — re-raiding a tile during the window resets the 7-day clock from the new raid.

### 22.8 Cost accounting

The raid penalty (1,000 cr per raided tile) is a meaningful but not crippling number:
- A single raid on a Small Outpost (5 expansion tiles, weekly maintenance ~2,000 cr): 1,000 cr penalty + lost resource node revenue ≈ 25% of the city's weekly budget. Painful but recoverable.
- 50% raid coverage on a Fortress (20 tiles, hits 10): 10,000 cr penalty + 10 disabled resource nodes ≈ 1.5–2 weeks of treasury drain. Forces the contest to actually be defended.

These numbers are tunable starting points. If raiding feels too cheap, raise the penalty and lengthen the window. If it feels too punishing, do the opposite.

### 22.9 Schema additions for §22

```sql
CREATE TABLE IF NOT EXISTS city_tile_raids (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    city_id         INTEGER NOT NULL,
    room_id         INTEGER NOT NULL,            -- the raided expansion tile
    raider_org_id   INTEGER NOT NULL,
    raided_at       REAL NOT NULL,
    expires_at      REAL NOT NULL,                -- raided_at + 7 days
    state           TEXT NOT NULL DEFAULT 'active',  -- active | cleared | expired
    cleared_at      REAL DEFAULT 0,
    FOREIGN KEY (city_id) REFERENCES player_cities(id)
);

CREATE INDEX idx_raids_city ON city_tile_raids(city_id, state);
CREATE INDEX idx_raids_org_window ON city_tile_raids(raider_org_id, raided_at);
```

The `idx_raids_org_window` supports the rolling-14-day query for the auto-contest threshold.

---

## 23. Variable Guard Density

### 23.1 Why guard slots vary by tile type

City tiles are not equivalent. The City Center is the irreplaceable core; citizen-only rooms are Mayor-flagged as important; standard expansion tiles are everything else. The defensive mechanic should reflect this — and the gameplay payoff is real strategic depth in how a Mayor allocates a fixed guard pool.

The total guard pool stays as designed in v1 (§7.1): 5 / 10 / 20 by HQ tier. What changes is **how those slots can be distributed** across tiles.

### 23.2 The density tiers

| Tile type | Max guards stationed |
|---|---|
| Standard expansion tile | 1 |
| Citizen-only expansion tile (Mayor-flagged) | 2 |
| City Center entrance room | 3 |
| HQ interior rooms (existing HQ guard pool) | 1 (unchanged from existing HQ rules) |

City Center entrance gets 3 because it's the hardest target — see §22.5, the HQ is not raidable, so attackers wanting to dismantle the city work through expansion tiles, but the **psychological** anchor of "the heart of the city has the most guards" matters even though the HQ isn't raidable. Citizens see 3 guards at the entrance and feel the city is well-defended.

### 23.3 Mayor allocation strategy

A Chapter House city (10-tile cap, 10 city-level guards) creates real choices:

- **Spread thin:** 1 guard per tile, all 10 tiles defended at minimum. Easy raids on each, but no tile is undefended.
- **Cluster on importance:** 3 on Center + 2 each on 3 citizen-only + 1 each on 2 expansion = 5 hard tiles + 2 soft tiles + 3 undefended. Concentrates strength but leaves gaps.
- **Asymmetric:** 3 on Center + 1 each on 7 expansion = balanced single-guard perimeter with a hard core.

There's no objectively right answer. The strategy depends on the city's threat profile, citizen activity patterns, and what the Mayor prioritizes.

### 23.4 Allocation command

```
+city guards assign <tile> <count>
```

Stations `count` guards on the named tile, drawing from the city guard pool. Validated against the density cap for that tile type. Cost: 200 cr/guard/week (unchanged).

```
+city guards rebalance
```

Mayor utility command — shows current allocation across all tiles plus available unstationed guard slots. No mechanical effect, just visibility.

```
+city guards remove <tile> [count]
```

Removes guards from a tile. If count is omitted, removes all guards. Returns the slots to the pool for reallocation (no refund of weekly cost already paid).

### 23.5 Defender alert on multi-guard tiles

When combat begins on a tile with **2 or more stationed guards**, the system broadcasts an alert to all online citizens immediately at combat start (not at guard death):

```
⚠ ALERT: [Tile name] in [City name] is under attack — combat in progress.
  Guards remaining: 3/3
```

This fires at combat start and updates as guards fall. The intent: multi-guard tiles are sieges, and sieges should be visible to defenders. Single-guard tiles (the soft perimeter) don't fire this alert — those are the exposed flanks, intentionally lighter on defender visibility.

The City Center, with 3 guards by default, becomes a true siege event when attacked. Defenders have time to respond. Attackers committing to a Center raid know defenders will probably show up. This is the design intent.

### 23.6 Multi-guard combat resolution

Per Option A from the design discussion: **all guards must fall in a single combat session for the raid window to open**.

- If attackers kill 2 of 3 guards but retreat or are driven off, the surviving guard remains. No raid window opens. Surviving guards do NOT auto-heal — they retain wound levels until naturally healed or replaced via the Mayor command (which also resets wounds).
- If attackers kill 2 of 3 guards and stay engaged with the third, combat continues normally. If the third is killed before combat ends, the raid window opens (full effect, regardless of how the other two went down).
- Combat session boundary is the standard combat session — no special rule for guard fights.

### 23.7 No partial-credit raid

There is no partial raid. You took the tile (all guards down) or you didn't (any survived). Partial raid mechanics invite optimization that isn't fun ("damage exactly enough to mark the tile, retreat") and add accounting complexity for marginal payoff.

### 23.8 Schema additions for §23

```sql
ALTER TABLE player_city_rooms ADD COLUMN guard_count INTEGER DEFAULT 0;
-- Count of stationed guards; max enforced per density tier (1/2/3) at command time.
```

Existing guard NPC infrastructure handles individual guard records; this column tracks the stationed count for fast lookup during combat-start alerts and raid-window resolution.

### 23.9 Power balance unchanged

Total guard pool is unchanged: 5/10/20 per HQ tier. Total weekly cost is unchanged: 200 cr per stationed guard. The lever is *placement strategy*, not pool size. This is by design — variable density adds depth without inflating defensive ceiling.

### 23.10 Phase 10 in delivery plan

Add to §13 phased delivery:

### Phase 10: Variable guard density + defender alerts (§23)
- `guard_count` column on `player_city_rooms`
- `+city guards assign / remove / rebalance` commands
- Density cap enforcement (1/2/3 by tile type)
- Multi-guard combat-start alert broadcast
- All-guards-must-fall raid trigger logic
- **Effort:** Small-Medium. ~0.5–1 session.

### Phase 11: Raid window mechanic (§22)
- `city_tile_raids` table
- Raid trigger on guards-down event
- 7-day window state machine
- Resource/security debuff application
- Treasury penalty
- Defender alert broadcast
- 50%-tiles-in-14-days auto-contest detection
- Auto-clear when attackers leave for 24h
- **Effort:** Medium. ~1.5 sessions.

### Phase 12: City contest integration (§21)
- Hook Drop 6D contest resolution to check city membership
- City collapse logic on full expansion-tile loss
- Wilderness region per-zone influence extension
- HQ revert-to-standalone state transition
- **Effort:** Small-Medium. ~1 session.

**Phases 10–12 subtotal:** ~3–3.5 sessions.
**New total (settled + frontier + contestation):** ~10.5–11.5 sessions.

These three phases are tightly coupled and should ship together. Drop 6D must ship before Phase 12. Phases 10 and 11 can ship in either order but Phase 11 needs Phase 10's guard-count infrastructure to enforce "all guards must fall."

---

*End of design v1.2.*
