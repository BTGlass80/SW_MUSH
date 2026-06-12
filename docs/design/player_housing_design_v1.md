# SW_MUSH — Player Housing & Homesteads System
## Design Document v1.0
### April 2026 · BTGlass80 · WEG D6 R&E

---

## 1. Design Philosophy

Every Star Wars character has a place they sleep. Han has the *Falcon*. Luke had a moisture farm. Lando had a suite in Cloud City. A bounty hunter keeps a safehouse. An Imperial officer has assigned quarters. A smuggler rents a back room above a cantina. Housing turns SW_MUSH from a place players *visit* into a place they *live* — and that distinction is the single strongest predictor of long-term retention across every multiplayer game genre.

### 1.1 Lessons from Other Games

The research covers 30+ years of player housing across MUDs, MUSHes, and MMOs. The best ideas distill into clear patterns:

**Star Wars Galaxies** — the gold standard. Open-world placement, player-crafted structures, vendor integration, player cities with elected mayors and civic buildings, daily maintenance costs as credit sinks, pack-up-and-move portability. What worked: housing was *useful* (storage, vendors, crafting stations) not just decorative. What failed: abandoned houses littering the landscape when players quit, scarcity of good plots on popular servers, and the later Bespin apartments proving that *location matters* — shops in inconvenient spots got zero foot traffic.

**Ultima Online** — open-world housing so meaningful that plot ownership became a social status symbol. Players could customize every tile of a multi-story building. Houses doubled as shops with NPC vendors. The downside: finite world space meant "haves and have-nots" — latecomers literally couldn't get housing.

**Achaea / Iron Realms MUDs** — text-based housing done right for our medium. Players buy rooms that attach to the world grid, write custom room names and descriptions, add doors/locks, and install functional additions (forges, stables, treasure chests). Rooms cost in-game gold plus premium currency for upgrades. The key insight: *in a text game, the description IS the decoration.* Writing your room's description is the equivalent of placing furniture in a graphical game.

**FFXIV** — beautiful housing, but crippled by artificial scarcity. Lottery systems, prohibitive costs, and limited supply created a system where most players simply couldn't participate. The lesson: **every player must be able to get housing.** Scarcity should be in *quality* and *location*, not in *access*.

**EQ2** — deep decoration system (free-form item placement on any axis), guild halls as social hubs, trophies from adventures displayed on walls. The lesson: housing should **commemorate the journey** — display your lightsaber kills, your smuggling routes, your faction medals.

**SWTOR Strongholds** — instanced apartments tied to specific planets, with hook-based decoration. Accessible but lifeless. The lesson: hook systems feel restrictive and sterile. Free-form (or at least freeform-ish) description is better for text.

**DAoC** — housing neighborhoods visible to all, with vendors and trophy walls. The lesson: **housing should be socially visible**, not hidden behind instance doors.

**General MUD/MUSH tradition** — MUSH culture has always given players room-building tools. The `@dig` command is foundational. SW_MUSH can honor this tradition while adding mechanical depth through the D6 system.

### 1.2 Core Principles

**Universal access, tiered quality.** Every player gets *something* — even if it's just a rented bunk. Premium housing (standalone structures, multi-room estates) requires progression and investment. Nobody is homeless unless they choose to be.

**Housing is useful, not just decorative.** Homes provide storage, rest bonuses, crafting stations, and (for traders) shop integration. A home that's purely cosmetic isn't worth the engineering effort in a text game.

**Faction shapes housing.** An Imperial officer doesn't shop for an apartment — they get billeted. A Hutt enforcer gets a safehouse from the Cartel. A Rebel operative has a cell's hidden bolt-hole. A freighter captain lives on their ship. Faction membership should determine *how* you get housing and *what kind* you get.

**Security zones matter.** Housing in a secured zone is safe. Housing in a contested zone might get robbed. Housing in a lawless zone is a territorial claim that others can challenge. The security_zones_design_v1.md system layers directly onto housing.

**Text descriptions are the decoration system.** Players write (or commission AI-assisted) room descriptions for their homes. This is the MUSH tradition and it's the right call — no furniture item database needed, just good writing.

**Ships are homes too.** The space system already gives players ships with interior rooms. For many archetypes (smugglers, pilots, bounty hunters), their ship IS their home. The housing system should recognize and enhance this rather than compete with it.

**Credit sinks, not credit traps.** Housing costs should be meaningful but not punishing. Rent is a steady drain, not a cliff. Missed payments degrade service, not instant eviction.

---

## 2. Housing Tiers

Five tiers of housing, each serving a different player profile and progression stage.

### 2.1 Tier 0: Ship Berth (Free — Already Exists)

**What it is:** Your ship's interior rooms. Already implemented in the space system.

**Who uses it:** Smugglers, pilots, bounty hunters, any ship owner.

**What it provides:**
- Sleep location (set `home` to a ship room)
- Personal storage (ship cargo hold, already functional)
- Crafting at ship workbench (if installed via ship modifications)

**What it doesn't provide:**
- Visitor access while owner is offline (ship despawns)
- Vendor droid placement (ships are not valid placement zones)
- Rest bonus (ships are functional, not comfortable — unless upgraded)

**Housing enhancement:** A new ship modification, `Crew Quarters Upgrade`, adds a comfort rating to one interior room. Setting your home location to an upgraded crew quarters grants a small rest bonus (+5% CP tick rate for the first hour of play each day). This uses the existing ship modification system from space_expansion_v2.

### 2.2 Tier 1: Rented Room (500cr deposit + 50cr/week)

**What it is:** A single room in an existing NPC-owned building — a hotel room, a back room above a cantina, a bunkhouse. The room is a real room in the game world, linked via a lockable door to the host building.

**Who uses it:** New players, independents, characters who don't need or want a full residence. The "starter apartment" — everyone can afford this within their first session.

**What it provides:**
- A private room with a lockable door (key issued at rental)
- Personal storage locker: 20 item slots
- Sleep location (`home` command teleports here)
- Basic rest bonus: +5% CP tick for first hour daily
- Player-writable room description (one free change, 1,000cr per subsequent change)

**What it doesn't provide:**
- Vendor droid placement
- Crafting station
- Guest access list (it's private — owner-only)

**Locations available:**

| Planet | Building | Zone | Security |
|--------|----------|------|----------|
| Tatooine | Mos Eisley Hotel (existing room 9) | residential | Secured |
| Tatooine | Back Room, Chalmun's Cantina | cantina | Secured |
| Nar Shaddaa | Flophouse, Promenade | promenade | Contested |
| Nar Shaddaa | Smuggler's Den Bunkroom | undercity | Lawless |
| Kessel | Station Barracks | station | Contested |
| Corellia | Coronet Inn | city_center | Secured |

Each location has a finite number of rental slots (5-10 per building). This creates mild social scarcity — the cantina back room is more fun than the hotel, so it fills up first — but total supply exceeds likely demand.

**Rent mechanics:**
- 50cr/week deducted automatically from the character's wallet on the payroll tick (same tick as faction stipends)
- If wallet is empty: 2-week grace period. Room is preserved but the lock stops working (anyone can enter). After 2 weeks of non-payment, room contents are mailed to the character as a package and the room reverts to "available."
- Voluntary checkout: `housing checkout` — deposit refunded, room cleared.

### 2.3 Tier 2: Faction Quarters (Free with Faction Membership)

**What it is:** Assigned housing provided by faction membership. This is the housing path for players who join a faction — they don't need to rent because the faction houses them.

**Who uses it:** Imperial soldiers, Rebel operatives, Hutt Cartel enforcers, anyone with faction membership at rank 1+.

**Each faction provides different housing flavor:**

**Imperial Quarters:**
- **Rank 0-1:** Barracks bunk (shared room with other low-rank Imperials, no privacy, storage locker only). Room is in the Imperial Garrison.
- **Rank 2-3:** Private quarters in the Garrison. Own room, lockable door, 30 item storage, desk terminal.
- **Rank 4+:** Officer's suite. Multi-room housing (bedroom + office), 50 item storage, holoterminal, guest list. Officers can invite other characters in.
- **Rank 6 (Commander):** Commander's quarters. 3 rooms, personal meeting room, 100 item storage, secured comms terminal. The "penthouse" of Imperial housing.

The Garrison interior already has room descriptions referencing "Officers' and Pilots' Quarters" (Level 6 in the WEG sourcebook images). This maps directly.

**Rebel Safehouse:**
- **Rank 0:** No housing (sympathizers don't know safehouse locations)
- **Rank 1-2:** Shared bunk in a hidden safehouse. Location is secret — the room is reached via a concealed exit from a public area. Room description emphasizes improvised comfort, cargo crates as furniture, dim lighting.
- **Rank 3+:** Private cell room in the safehouse. Own space, secured door, 40 item storage.
- **Rank 5 (Commander):** Command quarters with planning table, encrypted terminal, 80 item storage.

The Rebel safehouse doesn't exist yet in the world — it would be added as a small zone (3-5 rooms) accessible via a hidden exit in a contested-zone room on Tatooine, plus equivalents on other planets. The hidden exit requires Rebel faction membership to use — non-Rebels don't even see it in `look`.

**Hutt Cartel:**
- **Rank 0-1:** No assigned housing (associates sleep where they can)
- **Rank 2 (Enforcer):** Safehouse room in Nar Shaddaa undercity. Functional, not comfortable. 30 item storage.
- **Rank 3+ (Lieutenant):** Private suite in a Hutt-controlled building. Better furnished, 50 item storage, personal stash (hidden compartment — other players can't see contents even if they enter).
- **Rank 5 (Vigo):** Luxury penthouse. 3 rooms, 100 item storage, Hutt opulence descriptions. Guard NPC at the door.

**Bounty Hunters' Guild:**
- The Guild doesn't provide housing. Bounty hunters are independent operators — they rent rooms, live on their ships, or buy their own place. This is thematically correct. The Guild provides the license and the jobs, not a roof.

**Mechanics:**
- Faction quarters are assigned automatically when a member reaches the qualifying rank (via the promotion flow in organizations.py)
- Quarters are revoked on demotion below qualifying rank, expulsion, or voluntary departure. Contents are mailed as a package.
- No rent cost — faction membership is the "rent." The faction treasury absorbs the implied cost.
- Faction quarters cannot host vendor droids (no commerce in military/criminal housing).

### 2.4 Tier 3: Private Residence (5,000–25,000cr purchase + 100cr/week rent)

**What it is:** A standalone 1-3 room home owned by the player, linked to the game world via a door from a public room. This is the "real" housing — a home you own, describe, and customize.

**Who uses it:** Mid-to-late-game players who want a permanent home base. Traders, established independents, anyone who's accumulated some wealth.

**Structure types:**

| Type | Rooms | Cost | Weekly Rent | Storage | Special |
|------|-------|------|-------------|---------|---------|
| Small Dwelling | 1 | 5,000cr | 100cr | 40 items | — |
| Standard Home | 2 | 12,000cr | 175cr | 80 items | Guest access list |
| Large Home | 3 | 25,000cr | 250cr | 120 items | Guest list + 1 vendor droid slot |

**How purchasing works:**
- Player visits a real estate NPC on any planet (one per planet, in the commercial district)
- Real estate NPC lists available "lots" — these are specific public rooms where a new exit can link to the player's home. Each room has a maximum number of housing exits (typically 2-4, set by the builder).
- Player selects a lot, pays the purchase price, and the system creates 1-3 new rooms linked via a lockable exit from the host room.
- The player gets one free room rename and one free room description write per room.

**Planet-specific housing flavors:**

| Planet | Available Zones | Flavor |
|--------|----------------|--------|
| Tatooine | Residential (secured), Outskirts (contested) | Adobe domes, underground dwellings, moisture farm homesteads |
| Nar Shaddaa | Promenade (contested), Undercity (lawless) | High-rise apartments, converted cargo bays, neon-lit lofts |
| Kessel | Station (contested) | Spartan station modules, pressurized hab units |
| Corellia | City Center (secured), Old Quarter (contested) | Townhouses, flat above a shop, converted warehouse |

**The security zone of the host room determines the housing's effective security.** A home in the Mos Eisley residential zone (secured) is completely safe — nobody can break in. A home in Nar Shaddaa's undercity (lawless) can potentially be broken into (see §6 Security & Intrusion).

**Customization:**
- `housing name <room#> <text>` — Rename a room (1,000cr after the first free change)
- `housing describe <room#>` — Enter description editor for a room (1,000cr after first free change)
- `housing guest add <player>` — Grant another player access through your locked door
- `housing guest remove <player>` — Revoke access

**Description guidelines:** Players write their own room descriptions. The system enforces a minimum length (50 characters) and maximum (2,000 characters). Descriptions should be written in second person ("You see...") to match the game's `look` convention. Offensive content is subject to admin moderation (same content filter as character names and shop names). For players who struggle with writing, a future integration could offer AI-assisted description generation via the Director AI ("describe a modest Tatooine dwelling with a workbench and sleeping mat").

### 2.5 Tier 4: Shopfront Residence (15,000–40,000cr + 200cr/week)

**What it is:** A home with an integrated public-facing shop room. The front room is publicly accessible and can host vendor droids; the back rooms are private residence. This is the trader's dream — live above your shop.

**Who uses it:** Crafters, merchants, established traders who want their vendor droids in a thematic location rather than plopped in a public square.

**Structure types:**

| Type | Rooms | Cost | Weekly Rent | Storage | Shop Slots |
|------|-------|------|-------------|---------|------------|
| Market Stall | 1 shop + 1 private | 15,000cr | 200cr | 60 items | 2 vendor droids |
| Merchant's Shop | 1 shop + 2 private | 28,000cr | 300cr | 100 items | 3 vendor droids |
| Trading House | 2 shop + 3 private | 40,000cr | 400cr | 150 items | 4 vendor droids |

**Shop room behavior:**
- The shop room(s) are publicly accessible — anyone can walk in without being on the guest list
- Vendor droids placed in shop rooms get a `browse` bonus: they appear in a planet-wide shop directory (`market search` command)
- The shop room inherits the security level of the host zone — a shop in a secured zone means no combat inside
- The private rooms behind the shop are locked and owner/guest-only

**Integration with existing vendor droid system:**
- The vendor droid system (player_shops_design_v1.md) already handles placement, buy/sell, and transactions
- Shopfront residences simply provide *better* placement locations than public rooms — dedicated space, higher vendor droid limits, and market directory visibility
- The per-character vendor droid cap (currently 3) is increased by 1 for each shopfront owned (max 6 total)
- Vendor droids in shopfronts don't count against the 2-per-room public placement limit (the shopfront IS the shop)

**Thematic examples:**
- Kaylee Voss buys a Market Stall in Mos Eisley Market. The front room is "Voss Custom Arms" — she writes a description of a clean, well-lit weapons shop with display cases. Her GN-7 vendor droid stands behind the counter. The back room is her private quarters where she sleeps and stores materials.
- Gorba the Hutt Enforcer buys a Trading House in Nar Shaddaa's Promenade. Two shop rooms sell weapons and spice (through vendor droids). Three private rooms serve as his personal residence, complete with a description of gaudy Hutt-style luxury.

### 2.6 Tier 5: Organization Headquarters (50,000–150,000cr from org treasury)

**What it is:** A faction or guild headquarters — a multi-room complex owned by an organization, not an individual. This is the endgame group housing.

**Who uses it:** Player-run faction chapters, guild halls, organization leadership.

**This builds on the territory control concept** from security_zones_design_v1.md §7 ("Future — Territory Control (Phase 2)"). Organization HQs are the first concrete implementation of that feature — a claimed space in the world owned by a player group.

**Structure:**

| Type | Rooms | Cost | Weekly Maint. | Features |
|------|-------|------|---------------|----------|
| Small Outpost | 3-5 | 50,000cr | 500cr | Meeting room, armory/storage, 2 NPC guard slots |
| Chapter House | 5-8 | 100,000cr | 1,000cr | All above + barracks (member housing), comm center, 4 NPC guard slots |
| Fortress | 8-12 | 150,000cr | 1,500cr | All above + war room, prisoner cell, hangar bay link, 6 NPC guard slots |

**Mechanics:**
- Purchased by organization leader using org treasury funds (`faction hq purchase <type>`)
- Placed in a specific zone via the real estate system (same lot mechanics as private housing)
- Organization members at rank 1+ can enter freely; non-members require invitation or faction-override rules
- Meeting room provides a private channel for in-person faction discussions
- Armory provides shared organization storage (separate from personal inventory)
- Barracks rooms function as Tier 2 housing for members — members can set their home here
- NPC guard slots: the org can station NPC guards (from the org's NPC pool) at the HQ. Guards challenge non-members and fight intruders in contested/lawless zones.

**In lawless zones**, an org HQ functions as a territorial claim — the HQ's rooms become *contested* (for non-members) even though the surrounding zone is lawless. This means org members are safe inside their base, but outsiders can still attack if they force entry. This is the foundation for the territory control PvP described in the security zones design.

**Maintenance:**
- Weekly maintenance from org treasury (same payroll tick)
- If treasury is depleted: guards stop functioning first, then doors unlock, then after 4 weeks the HQ is "abandoned" and reverts to unclaimed rooms
- Director AI receives HQ status in its faction digest for narrative purposes

---

## 3. The `housing` Command Family

### 3.1 Player Commands

| Command | Aliases | Function |
|---------|---------|----------|
| `housing` | `home` | Show your current housing status (tier, location, rent due, storage used) |
| `housing rent <location>` | — | Rent a Tier 1 room at the specified location |
| `housing checkout` | `housing leave` | Vacate your rented room (deposit refunded) |
| `housing buy <type>` | — | Purchase a Tier 3/4 home at a real estate NPC |
| `housing name <text>` | — | Set/change the name of a room you own (while standing in it) |
| `housing describe` | `housing desc` | Enter the room description editor for a room you own |
| `housing guest add <player>` | — | Add a player to your guest access list |
| `housing guest remove <player>` | — | Remove a player from your guest access list |
| `housing guest list` | — | View your current guest list |
| `housing lock` | — | Lock/unlock your home's door (while at the entrance) |
| `housing storage` | `housing stash` | View contents of your home storage locker |
| `housing store <item>` | — | Place an item from inventory into home storage |
| `housing retrieve <item>` | — | Take an item from home storage into inventory |
| `housing sell` | — | Sell your home back to the real estate NPC (50% of purchase price refunded, room is cleared) |
| `housing upgrade <type>` | — | Upgrade your home (e.g., add a room, add storage) |
| `housing trophy <item>` | — | Mount an item as a room trophy (visible in `look`, not removable by guests) |

### 3.2 Admin Commands

| Command | Function |
|---------|----------|
| `@housing list [planet]` | List all housing — rented, owned, faction, org HQs |
| `@housing inspect <player>` | View a player's housing details |
| `@housing evict <player>` | Force-evict a player (admin moderation) |
| `@housing lots <room_id>` | View/modify available housing lots on a room |
| `@housing lots <room_id> = <max>` | Set max housing exits for a room |

### 3.3 Organization Leader Commands

| Command | Function |
|---------|----------|
| `faction hq purchase <type>` | Buy an org HQ (from real estate NPC) |
| `faction hq storage` | View/manage org armory storage |
| `faction hq guard assign <npc>` | Station an NPC guard at the HQ |
| `faction hq guard remove <npc>` | Remove an NPC guard |
| `faction hq upgrade <type>` | Upgrade the HQ (add rooms, guard slots) |

---

## 4. Room Description System

### 4.1 The Description Editor

When a player uses `housing describe`, they enter a line editor (similar to `@desc` in traditional MUSH codebases):

```
> housing describe

  ══════════════════════════════════════════
   ROOM DESCRIPTION EDITOR
  ══════════════════════════════════════════
   Room: Kaylee's Workshop
   Current length: 0 / 2000 characters
  ──────────────────────────────────────────
   Type your description. Use .done to save,
   .clear to start over, .cancel to abort.
  ──────────────────────────────────────────

> A cluttered workbench dominates the center of this small
> room, its surface covered in blaster components, tools,
> and half-finished projects. The walls are lined with
> shelving units holding neatly organized bins of parts —
> power cells, focusing crystals, trigger assemblies. A
> narrow cot is wedged into the far corner, half-buried
> under spare clothing and tech manuals. A faded poster of
> a SoroSuub J-type diplomatic barge hangs above the cot,
> its corners curling in the dry heat.
> .done

  Description saved. (326 / 2000 characters)
```

### 4.2 AI-Assisted Descriptions (Future Enhancement)

For players who want help writing, a future command could leverage the Director AI (or the local Ollama model):

```
> housing describe assist

  What kind of room is this?
  1. Living quarters
  2. Workshop / crafting space
  3. Shop / storefront
  4. Office / command post
  5. Other (describe)

> 2

  Describe the feel you want (one sentence):
> A cramped but organized weapons workshop on Tatooine

  Generating description...

  "Blaster components line every surface of this compact
   workshop. Despite the clutter, there's an underlying
   order — power packs sorted by charge level, barrels
   racked by caliber, tools hanging from a pegboard in
   order of use. The dry Tatooine heat seeps through the
   sandstone walls, keeping solder flux at the perfect
   viscosity. A magnifying lamp on an adjustable arm
   illuminates the main workbench, where a half-assembled
   DL-44 awaits its owner's return."

  Use this description? (yes/edit/regenerate/cancel)
```

This is a quality-of-life feature, not a launch requirement. It routes through the existing Ollama/Mistral inference pipeline with a short system prompt constraining output to room descriptions.

### 4.3 Trophies

Trophies are items mounted in your room that appear in the `look` output. They serve the EQ2 "commemorate the journey" function:

```
Kaylee's Workshop [PRIVATE]
  A cluttered workbench dominates the center of this small room...

  [Mounted on the wall]
   ◆ Modified DL-44 Heavy Blaster — "First custom build" (Quality: 82)
   ◆ Imperial Scout Helmet — trophy from a Jundland encounter
   ◆ Shipwright's Guild Certificate — signed by Master Kator
```

Mechanically, a trophy is an inventory item moved to the room's `trophies` list in the DB. It's visible to anyone who enters the room but can only be removed by the owner. Items used as trophies retain all their stats — you can un-mount and re-equip them.

---

## 5. Storage System

### 5.1 Home Storage

Each housing tier provides a personal storage locker — a persistent inventory separate from the character's carried inventory.

**Storage commands work only inside your home:**
- `housing store <item>` — move item from inventory to storage
- `housing retrieve <item>` — move item from storage to inventory
- `housing storage` — list all stored items

**Storage is type-aware:** Items, resources, and equipment all stored in the same pool. Storage counts are by slot (an item stack = 1 slot, like vendor droids).

### 5.2 Organization Armory

Org HQs provide shared storage accessible by members of sufficient rank:

- Rank 2+ can view armory contents
- Rank 3+ can deposit items
- Rank 4+ can withdraw items
- Rank 5+ (leaders) can manage access rules

This creates a faction equipment depot — the Empire issues gear from the armory, the Rebels share resources, the Cartel stockpiles contraband.

---

## 6. Security & Intrusion

Housing security integrates directly with the security zones system.

### 6.1 Secured Zone Housing

Homes in secured zones (Mos Eisley residential, Coronet city center, etc.) are fully protected:
- Doors are locked and cannot be picked or forced
- No combat can occur inside (inherits secured zone rules)
- Uninvited characters cannot enter under any circumstances
- This is the "safe space" housing — players who want zero risk live here

### 6.2 Contested Zone Housing

Homes in contested zones (Mos Eisley outskirts, Nar Shaddaa promenade, Corellia port district):
- Doors can be picked with a **Very Difficult** Security check (difficulty 25)
- Failed pick attempts alert the owner (if online) and are logged
- NPC guards (if org HQ) challenge intruders
- Once inside, contested zone PvP rules apply (challenge/consent required for player combat)
- Theft is possible: items in the main room can be stolen via a **Heroic** Sneak + Security combined check (difficulty 30+). Storage lockers cannot be cracked.

### 6.3 Lawless Zone Housing

Homes in lawless zones (Jundland Wastes, Nar Shaddaa undercity, Kessel mines):
- Doors can be forced (Strength check, difficulty 15) or picked (Security, difficulty 20)
- All combat rules are unrestricted inside
- Theft from the main room requires only a **Moderate** Sneak check (difficulty 15)
- Storage lockers can be cracked with a **Very Difficult** Security + Slicing combined check (difficulty 30)
- This is high-risk housing — but it's cheap (50% rent discount) and located near the best resources

### 6.4 Why Live in Dangerous Zones?

The same incentives from security_zones_design_v1.md §7 apply:
- **50% rent discount** on housing in lawless zones
- **25% rent discount** on housing in contested zones
- **Proximity to rare resources** — lawless zones have the best survey nodes
- **+25% CP tick bonus** for time spent in lawless zones (stacks with rest bonus)
- **Black market access** — certain NPC vendors only operate near lawless housing
- **Territory control** — org HQs in lawless zones are the endgame territorial claim

---

## 7. Economy Integration

### 7.1 Credit Flow

Housing is a major new credit sink, which the economy needs as the playerbase matures.

**Faucets (money in):**
- Shopfront vendor droid sales (existing system, now with better placement)
- Property appreciation: none (intentional — housing is a utility, not a speculation vehicle)

**Sinks (money out):**

| Sink | Amount | Frequency |
|------|--------|-----------|
| Tier 1 deposit | 500cr | One-time |
| Tier 1 rent | 50cr/week | Weekly tick |
| Tier 3 purchase | 5,000-25,000cr | One-time |
| Tier 3 rent | 100-250cr/week | Weekly tick |
| Tier 4 purchase | 15,000-40,000cr | One-time |
| Tier 4 rent | 200-400cr/week | Weekly tick |
| Tier 5 purchase | 50,000-150,000cr | One-time (from org treasury) |
| Tier 5 maintenance | 500-1,500cr/week | Weekly tick (from org treasury) |
| Room rename | 1,000cr | Per change |
| Room description change | 1,000cr | Per change (after first free) |

**Target impact on economy:** A typical active player with a Tier 3 Standard Home pays 175cr/week in rent — about 8-15% of a typical week's income (assuming ~1,000-2,000cr/hr × 5-10 hours/week = 5,000-20,000cr/week). This is noticeable but not punishing, matching the economy design's target of ~200-400cr/hr in basic living expenses.

### 7.2 Integration with Existing Systems

**Vendor droids:** Shopfront residences provide premium placement for vendor droids. The `browse` command shows droids in shopfronts with a "[SHOP]" tag. The `market search` command (future) lists all shopfront vendors by planet.

**Crafting:** Homes can have crafting stations installed as upgrades (2,000cr each). A crafting station in your home works identically to a public workbench but is private — you don't compete for access. This encourages crafters to invest in housing.

**Faction payroll:** Faction housing is free but faction membership costs are implicit (faction duties, mission requirements, the faction itself paying maintenance from treasury). This ties housing to the faction economy loop.

**Director AI:** The Director receives housing data in its digest — how many homes exist per planet, vacancy rates, org HQ locations. This informs narrative decisions: "Mos Eisley's residential district is overcrowded — the Director generates a housing boom subplot" or "Nar Shaddaa's undercity has new territorial claims — the Director escalates gang conflict narratives."

---

## 8. Schema Changes

### 8.1 New Tables

```sql
-- Player housing records
CREATE TABLE IF NOT EXISTS player_housing (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    char_id         INTEGER NOT NULL,
    tier            INTEGER NOT NULL DEFAULT 1,     -- 1-5
    housing_type    TEXT    NOT NULL,                -- 'rented_room', 'faction_quarters', 
                                                    -- 'private_small', 'private_standard',
                                                    -- 'private_large', 'shopfront_stall',
                                                    -- 'shopfront_merchant', 'shopfront_trading',
                                                    -- 'org_outpost', 'org_chapter', 'org_fortress'
    org_id          INTEGER DEFAULT NULL,            -- Non-null for faction/org housing
    entry_room_id   INTEGER NOT NULL,                -- Room with the door to this home
    room_ids        TEXT    NOT NULL DEFAULT '[]',   -- JSON array of room IDs belonging to this home
    storage         TEXT    NOT NULL DEFAULT '[]',   -- JSON array of stored items
    storage_max     INTEGER NOT NULL DEFAULT 20,
    trophies        TEXT    NOT NULL DEFAULT '[]',   -- JSON array of trophy items
    guest_list      TEXT    NOT NULL DEFAULT '[]',   -- JSON array of char_ids
    purchase_price  INTEGER DEFAULT 0,
    weekly_rent     INTEGER DEFAULT 0,
    rent_paid_until REAL    DEFAULT 0,               -- Timestamp of last rent payment
    rent_overdue    INTEGER DEFAULT 0,               -- Weeks of missed rent
    created_at      REAL    NOT NULL,
    last_activity   REAL    DEFAULT 0,
    FOREIGN KEY (char_id) REFERENCES characters(id),
    FOREIGN KEY (org_id) REFERENCES organizations(id)
);

-- Available housing lots (slots on public rooms for player homes)
CREATE TABLE IF NOT EXISTS housing_lots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    room_id         INTEGER NOT NULL,                -- Public room where the home connects
    planet          TEXT    NOT NULL,
    zone            TEXT    NOT NULL,
    max_homes       INTEGER NOT NULL DEFAULT 2,      -- Max housing exits from this room
    current_homes   INTEGER NOT NULL DEFAULT 0,
    allowed_tiers   TEXT    NOT NULL DEFAULT '[3,4]', -- JSON array of allowed housing tiers
    FOREIGN KEY (room_id) REFERENCES rooms(id)
);
```

### 8.2 Modified Tables

```sql
-- Rooms table: add housing ownership flag
ALTER TABLE rooms ADD COLUMN housing_id INTEGER DEFAULT NULL 
    REFERENCES player_housing(id);
-- When non-null, this room belongs to a player home

-- Characters table: home location
-- Already has a 'home' field in attributes JSON — reuse for housing room_id
```

### 8.3 Schema Version

This would be schema **v11** (v10 is the shop_transactions + owner_id migration from the player shops design).

---

## 9. Files Modified/Created

| File | Change |
|------|--------|
| `engine/housing.py` | **NEW** — Housing lifecycle: create, rent, buy, evict, upgrade, storage ops, trophy system |
| `parser/housing_commands.py` | **NEW** — All `housing` commands, description editor, guest management |
| `engine/security.py` | Extend `get_effective_security()` to check housing intrusion rules |
| `db/database.py` | Add `player_housing` and `housing_lots` tables, housing CRUD methods |
| `engine/organizations.py` | Add faction quarter assignment on rank change, org HQ purchase |
| `parser/admin_commands.py` | Add `@housing` admin commands |
| `build_mos_eisley.py` | Add housing lots to existing rooms, create rental NPC locations |
| `engine/npc_loader.py` | Add real estate NPC(s) to `PLANET_NPCS` |
| `data/housing_types.yaml` | **NEW** — Housing type definitions (costs, storage, allowed zones) |
| `game_server.py` | Add housing rent tick to game loop, register housing commands |
| `static/client.html` | Housing status in HUD, storage panel in web sidebar |

---

## 10. Implementation Plan

### Drop 1: Rented Rooms (Tier 1)
- `engine/housing.py` — core housing record CRUD, rent/checkout flow
- `parser/housing_commands.py` — `housing`, `housing rent`, `housing checkout`, `housing lock`, `housing storage/store/retrieve`
- Schema migration for `player_housing` and `housing_lots` tables
- `build_mos_eisley.py` — add 6 rental locations across 4 planets
- Real estate NPC stubs (Tier 1 is handled by innkeeper NPCs)
- Rent tick in game loop
- **Est. effort: Medium**

### Drop 2: Description Editor + Trophies
- Line editor for `housing describe`
- Trophy mount/unmount system
- Room description display in `look` (show housing owner, trophies)
- Room name changes (`housing name`)
- **Est. effort: Small-Medium**

### Drop 3: Faction Quarters (Tier 2)
- Faction quarter assignment logic in `engine/organizations.py`
- Create faction housing rooms (Imperial Garrison quarters, Rebel safehouse, Hutt safehouse)
- Wire promotion/demotion hooks to housing assignment
- Hidden exits for Rebel safehouses
- **Est. effort: Medium**

### Drop 4: Private Residences (Tier 3)
- Real estate NPC and lot system
- Home purchase/sell flow
- Guest access list
- Multi-room homes (room creation, exit linking)
- `housing upgrade` command
- **Est. effort: Medium-Large**

### Drop 5: Shopfronts (Tier 4)
- Shopfront purchase flow
- Public shop room + private residence rooms
- Vendor droid integration (increased caps, market directory)
- `market search` command for finding shopfront vendors
- **Est. effort: Medium**

### Drop 6: Organization HQs (Tier 5)
- Org HQ purchase from org treasury
- Shared armory storage
- NPC guard slots
- Lawless zone security override (HQ rooms become contested)
- Wire into Director AI digest
- **Est. effort: Large**

### Drop 7: Security & Intrusion
- Lock picking checks (Security skill)
- Break-in mechanics for contested/lawless zone housing
- Theft mechanics (Sneak + Security combined checks)
- Intrusion logging and owner alerts
- **Est. effort: Medium**

### Drop 8: Web Client Integration
- Housing status in HUD
- Storage panel in web sidebar
- Description editor in web UI (textarea instead of line editor)
- Housing map markers (show your home location)
- **Est. effort: Medium**

### Drop 9: Polish & AI Descriptions (Optional)
- AI-assisted description generation
- Housing inspection for visitors ("You see a well-kept home belonging to...")
- `housing visit <player>` — shortcut to walk to a player's public shopfront
- Housing leaderboard / directory ("Finest homes on Tatooine")
- **Est. effort: Small-Medium**

---

## 11. Interaction with Ship Housing

Ships and ground housing coexist. A player can have both:
- `home` command goes to whichever location the player has set as home (ship berth or ground housing)
- `sethome` (new command) lets the player choose which is their primary home
- Rest bonus: only the *primary* home provides the CP tick bonus (no double-dipping)
- Storage: ship cargo hold and home storage are separate pools (both accessible)

Many archetypes will never buy ground housing — a smuggler who lives on their YT-1300 is perfectly valid. The ship berth (Tier 0) is a first-class housing option, not a fallback.

For players who own both a ship and a shopfront, the ship provides mobile housing while the shopfront provides a fixed business address. This mirrors the SWG pattern where traders maintained city shops but traveled in their ships.

---

## 12. Open Questions

1. **Should housing provide a logout bonus?** If a player logs out inside their home, should they get a "rested" state that provides bonus CP for the first hour of the next session? Recommendation: Yes, small bonus (+5% CP tick for 1 hour). This encourages players to return to their home before logging off, which creates foot traffic and social encounters.

2. **Roommates?** Should two players be able to co-own a Tier 3 home and split rent? Recommendation: Not at launch. The guest list provides visitor access; co-ownership adds complexity around eviction and disputes. Defer to v2 if there's demand.

3. **Pets in housing?** If/when a creature companion system exists, should pets be storable in your home? Recommendation: Yes, when applicable. For now, it's a schema-ready concept (trophies list could hold creature references).

4. **Housing destruction in Director events?** Should a major Director event (Imperial bombardment, Hutt gang war) be able to damage or destroy player housing? Recommendation: Temporary displacement only. The Director can lock players out of their home for the duration of an event ("Your home is in the quarantine zone — Imperial troops have sealed the block.") but never permanently destroys player-owned content. The emotional investment is too high to risk.

5. **Furniture items?** Should there be a furniture crafting system (chairs, tables, beds) that can be placed in homes? Recommendation: Defer. In a text game, the room description IS the furniture. Functional furniture (crafting stations, storage upgrades) is implemented as housing upgrades, not as placed items. Decorative furniture is handled by the player writing it into their description. This avoids the complexity of an object placement system while honoring the MUSH tradition of descriptive freedom.

6. **Housing as quest location?** Can the Director send a player a quest that takes place inside their own home (e.g., "A suspicious package arrives at your door")? Recommendation: Yes, excellent idea for a future Director AI enhancement. Home invasion quests, delivery events, surprise NPC visitors — all great content that makes housing feel alive. Defer until the Director AI integration is more mature.

7. **Cross-planet housing?** Can a player own homes on multiple planets? Recommendation: Yes, but limit to one Tier 3/4 home per planet (max 4 total). This prevents one player from monopolizing lots but allows a trader to have shops on multiple worlds, mirroring the SWG multi-planet vendor model.

8. **Faction housing on all planets?** Should each faction have housing on every planet, or just their "home" planet? Recommendation: Home planet gets full housing (barracks → commander's suite), other planets get basic outpost rooms (Tier 1 equivalent). Imperial officers get quarters on Tatooine (Garrison) and Corellia (CorSec liaison office), but not on Nar Shaddaa or Kessel. Rebels have cells wherever they have presence. Hutts have safehouses on Nar Shaddaa and Tatooine (Jabba's connections).

---

## 13. Architecture Invariants

- **All housing rent deductions go through a single `process_housing_rent()` function.** No shortcuts. Same pattern as `perform_skill_check()` for dice rolls.
- **Housing rooms are regular rooms in the DB.** They have the same schema as world-built rooms. The `housing_id` column on `rooms` is the only thing that marks them as player-owned.
- **Default is no housing.** Characters start with no home. They can set their ship as home or rent. No automatic housing assignment except via faction membership.
- **Descriptions are stored in the room record.** The room's `description` field holds the player-written text. No separate description table.
- **Telnet parity.** The description editor, storage commands, and all housing operations work identically on Telnet and WebSocket. The web client adds visual convenience (storage panel, HUD badge) but never gates content.
- **Housing data is included in character export/import.** If a character is deleted, their housing is reclaimed (contents mailed). If the game is backed up, housing rooms and descriptions are included in the world DB.

---

## 14. Architecture Doc Changes

The following sections should be added/modified in the architecture document for v20+:

**New section: §14F Player Housing & Homesteads**
- Subsections: Housing Tiers, Description System, Storage, Security Integration, Economy Impact
- References this design doc for full specification

**Modified: §3.4 Database Layer**
- Add `player_housing` and `housing_lots` tables to schema v11

**Modified: §3.5 Tick Loop**
- Add housing rent tick (every 604800 ticks = 1 week, aligned with faction payroll)

**Modified: §12 Economy**
- Add housing as a credit sink category
- Update credit flow diagram with housing costs

**Modified: §14E Player Shop System**
- Note shopfront integration and increased vendor droid caps

**Modified: §17 Remaining Roadmap**
- Add Priority I: Player Housing (after shops and security zones)

---

*End of Player Housing & Homesteads Design Document — Version 1.0*
*Reference: security_zones_design_v1.md, organizations_factions_design_v1.md, player_shops_design_v1.md, economy_design_v02-1.md, space_expansion_v2_design.md, sw_d6_mush_architecture_v19.md*
