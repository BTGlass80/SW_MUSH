# SW_MUSH — Clone Wars Housing & Real Estate · Design v1

**Date:** April 28, 2026
**Author:** Opus content-lane session (CW Housing)
**Status:** Design-ready. Resolves the open content gap for F.5.
**Type:** Drop design — schedules `data/worlds/clone_wars/housing_lots.yaml` authoring and the Tier 2 faction-quarter rewicker.
**Pre-reads:**
- `player_housing_design_v1.md` (engine spec — already shipped, v26)
- `clone_wars_era_design_v3.md` §2 (planet roster), §3 (faction roster)
- `world_data_extraction_design_v1.md` §3 (target directory layout — `housing_lots.yaml` already a first-class loader output)
- `from_dust_to_stars_design_v2_clone_wars.md` Step 23 ("Safe Harbor" tutorial — already references CW housing)
- `sw_d6_mush_architecture_v37_consolidated.md` §12 (Player Housing — all 9 drops delivered)

---

## 1. Why this exists

Player Housing v1 shipped all 9 drops in v26. The engine, schema, command surface, web HUD, intrusion mechanics, and AI description suggestions are stable. **None of that changes for the CW pivot.** Housing rooms are regular rooms with a `housing_id` flag; any era's content can populate them.

What's missing is **the CW lot table**. The current housing flavor is GCW-only:

| Planet | GCW zones with housing | Flavor |
|---|---|---|
| Tatooine | Residential, Outskirts, Jundland | Adobe domes, homesteads |
| Nar Shaddaa | Promenade, Undercity | High-rises, neon lofts |
| Kessel | Station | Pressurized hab units |
| Corellia | City Center, Old Quarter | Townhouses |

The CW pivot drops Kessel and Corellia, adds Coruscant, Kuat, Kamino, and Geonosis, and reframes Tatooine and Nar Shaddaa. The Tier 2 faction set changes too — Empire/Rebel/Hutt/BHG becomes Republic/CIS/Jedi/Hutt/BHG. This document resolves both gaps.

The CW tutorial's Step 23 ("Safe Harbor") already promises players they can rent in Mos Eisley (cheapest) or Coruscant Coco Town (most networked). This design makes that promise true.

---

## 2. Scope

**In scope:**
- Per-planet / per-zone housing eligibility for all 6 CW planets
- Tier 1 rental NPC locations
- Tier 2 faction-quarter mappings for the new faction set (including the new Jedi Order)
- Tier 3 private-residence lot inventory
- Tier 4 shopfront lot inventory
- Tier 5 organization HQ lot inventory
- Real estate NPC roster
- Tatooine and Nar Shaddaa reskin notes (cosmetic only)
- The exact shape of `data/worlds/clone_wars/housing_lots.yaml`

**Out of scope:**
- Engine changes (none required — engine is stable)
- Schema changes (none — `player_housing` and `housing_lots` already support every tier)
- Web client changes (none — HUD already era-agnostic)
- New commands (none — `housing` family handles everything)
- Tatooine/Nar Shaddaa room rewrites beyond the Tier 2 reskin (covered separately by `clone_wars_era_design_v3.md` §2.3.5–6)

---

## 3. Architecture invariants we must preserve

These come from `player_housing_design_v1.md` and the v26 implementation; this design must not violate any of them.

1. **Security level of host zone determines intrusion rules.** Lawless zone = breakable; contested = breakable with higher difficulty; secured = uncrackable.
2. **Rent discounts by security tier:** secured = 100% rent, contested = 75%, lawless = 50%. CW uses the same multipliers.
3. **Faction quarters are free** — assigned by faction rank, not purchased.
4. **No Tier 4 shopfronts in lawless zones** (the public-shop-room design assumes some baseline lawful behavior). Lawless zones get T1 + T3 only.
5. **Tier 5 org HQs can exist in any security tier**, but lawless HQs are subject to hostile takeover (Drop 6 territory rules).
6. **`HOUSING_LOTS_TIER3` and `HOUSING_LOTS_TIER4` are loaded from data**, not hardcoded. The CW set replaces the GCW set when the era boots.

---

## 4. Eligibility matrix at a glance

This is the master table. Every cell in §6–11 derives from this.

| Planet | Zone | Security | T1 rental | T2 faction | T3 private | T4 shopfront | T5 org HQ |
|---|---|---|:-:|:-:|:-:|:-:|:-:|
| **Coruscant** | westport_district | secured | ✓ (hotel) | — | — | — | — |
| | senate_district | secured | — | — | — | — | — |
| | jedi_temple | secured | — | ✓ Jedi | — | — | — |
| | coco_town | contested | ✓ | ✓ Republic | ✓ | ✓ | ✓ Republic |
| | calocour_heights | secured | — | — | ✓ luxury | ✓ luxury | — |
| | southern_underground | lawless | ✓ | ✓ Hutt, ✓ BHG | ✓ | — | ✓ BHG, ✓ Indep |
| | gilded_cage | contested | ✓ | — | ✓ | ✓ | ✓ Indep |
| **Kuat** | kuat_main_spaceport | secured | ✓ (transient) | — | — | — | — |
| | kdy_orbital_ring | secured | — | ✓ Republic | ✓ Rep-rep gated | — | — |
| | kuat_city_embassy | secured | ✓ | — | ✓ Rep-rep gated | — | — |
| **Kamino** | tipoca_city_platform | secured | — | ✓ Republic | — | — | — |
| | cloning_facilities | secured | — | — | — | — | — |
| | ocean_platforms | contested | ✓ (limited stay) | — | — | — | — |
| **Geonosis** | stalgasin_hive_surface | lawless | ✓ | — | ✓ (CIS/indep) | — | ✓ CIS |
| | stalgasin_deep_hive | lawless | — | ✓ CIS | — | — | — |
| | petranaki_arena | contested | — | — | — | — | — |
| | droid_foundries | lawless | — | — | — | — | — |
| **Tatooine** | mos_eisley_core | secured | ✓ | — | ✓ | ✓ | — |
| | spaceport_district | contested | ✓ (cantina back) | — | — | ✓ | — |
| | chalmuns_cantina | contested | ✓ | — | — | — | — |
| | jabbas_townhouse | contested | — | ✓ Hutt | — | — | ✓ Hutt |
| | outskirts | contested | — | — | ✓ | — | ✓ Indep |
| | jundland_wastes | lawless | — | — | ✓ (homestead) | — | — |
| **Nar Shaddaa** | nar_shaddaa_docks | contested | ✓ | — | — | ✓ | — |
| | corellian_sector | contested | ✓ | — | ✓ | ✓ | — |
| | nar_shaddaa_upper | contested | ✓ (Promenade) | — | ✓ | ✓ | ✓ BHG |
| | nar_shaddaa_undercity | lawless | ✓ | ✓ Hutt | ✓ | — | ✓ Hutt |
| | warrens | lawless | — | — | ✓ (cheap, dangerous) | — | — |

**Reading notes:**
- A blank cell means the tier is not offered in that zone, by design. Senate District has no housing because it's government territory; Petranaki Arena has none because it's a public execution venue; etc.
- "Rep-rep gated" means the lot is listed only for characters meeting a Republic reputation threshold (≥ +25). The real estate NPC says "I'm afraid I can't show you our Kuat-side properties without a clearance, citizen."
- Coruscant has the most housing variety, by design. It's the canonical hub.
- Kuat is deliberately restricted — it's a Republic shipyard, not a residential planet.
- Kamino is even more restricted — only Republic clone troopers and Republic-faction PCs can live there at all.
- Geonosis offers lawless surface flop housing and the CIS faction quarters; nothing else.

---

## 5. Per-faction Tier 2 mapping (the new wrinkle)

GCW had four factions with quarters: Empire, Rebel, Hutt, BHG. CW adds **Jedi Order** and renames Empire→Republic, Rebel→CIS. The structure stays the same — faction rank gates the upgrade ladder — but the room descriptions and locations change entirely.

### 5.1 Republic Quarters

The GCW Imperial path mapped to a single garrison on Tatooine. The CW Republic spans the galaxy, so quarters can be on **either** Coruscant Coco Town (the canonical "Coruscant Guard barracks" slot) **or** Kuat KDY Orbital Ring (industrial deployment). System assigns by character backstory (where they enlisted) or default to Coruscant.

| Rank | Tier | Location | Description theme |
|---|---|---|---|
| 0–1 | Bunk | Coruscant Coco Town — Republic Guard barracks | Crisp white-and-blue walls, locker, bunk, holosched display |
| 2–3 | Private | Coruscant Coco Town — same building, private cell | Functional officer's room, desk terminal, Republic crest |
| 4 | Suite | Coruscant Coco Town — officer wing | Two rooms: bedroom + briefing room with holotable |
| 5 (Major+) | Commander suite | Coruscant Senate-adjacent — Judicial Forces compound | Three rooms, secure comms, war-room access |

**Alternate Kuat track** (for shipwright/industrial-leaning Republic PCs): rank 2+ can request reassignment to Kuat KDY Orbital Ring quarters. Same tier benefits, different flavor (engineer dormitories, prototype-ship view). One-time choice at rank 2; cannot toggle.

### 5.2 CIS Quarters

CIS quarters are in the **Stalgasin Deep Hive** on Geonosis. Lawless zone, but faction-protected — the hive's Geonosian guards count CIS members as friendlies.

| Rank | Tier | Location | Description theme |
|---|---|---|---|
| 0–1 | Bunk | Stalgasin Deep Hive — recruit dormitory | Carved chitinous walls, spartan bedroll, low orange light |
| 2–3 | Cell | Same hive — private alcove | Vaulted ceiling, basic furnishings, encrypted comms station |
| 4 | Suite | Same hive — officer's chamber | Two rooms, war-planning slate, droid-courier dock |
| 5 (Marshal+) | Council suite | Stalgasin Deep Hive — Council approach | Three rooms, holotable, restricted to senior CIS officers |

**Note on hostility:** Republic-aligned PCs can break into CIS quarters in theory (lawless zone), but the deep hive is heavily guarded by NPCs, making it suicidal in practice. This is the intended deterrent.

### 5.3 Jedi Order Quarters

This is **new** — GCW had no Jedi housing. All Jedi quarters are inside the **Jedi Temple** zone on Coruscant (secured, Jedi-faction-only access).

Jedi quarters are gated by **two** axes: faction rank AND chargen path. A Padawan never gets a Master suite, even if they accumulate the rank, because the Master suite requires Master-rank progression which requires the Trials. Practical effect: rank-3 quarters are the cap until the Knight Trial completes.

| Rank | Tier | Location | Description theme |
|---|---|---|---|
| 0 (Initiate) | Dorm | Jedi Temple — Initiate Cluster | Communal sleeping arrangement, simple cot, robed initiates moving quietly |
| 1–2 (Padawan) | Padawan cell | Jedi Temple — Padawan Wing | Single small room shared with one's Master next door, datapads, spare robes |
| 3 (Knight) | Knight quarters | Jedi Temple — Knight Wing | Two rooms — meditation chamber + private cell, view of upper Coruscant skyline |
| 5 (Master) | Master suite | Jedi Temple — Master Wing | Three rooms — meditation hall, Padawan teaching alcove, private chamber |

**Note on storage:** Jedi storage caps mirror non-Jedi tiers (30/40/80/120 by rank), but Jedi quarters cannot host vendor droids — Jedi don't run shops.

### 5.4 Hutt Cartel Quarters

**Identical to GCW.** The Hutt Cartel is era-portable; Nar Shaddaa is unchanged in CW. No content rewrite needed beyond minor flavor tweaks (e.g., "war profiteer" hooks in the higher-tier descriptions).

| Rank | Tier | Location | Description theme |
|---|---|---|---|
| 0–1 | — | (no faction housing) | — |
| 2 | Safehouse room | Nar Shaddaa Undercity | Functional, Hutt sigil, sealed footlocker |
| 3+ | Private suite | Nar Shaddaa Undercity / Tatooine Jabba's Townhouse | Furnished, hidden compartment storage |
| 5 (Vigo) | Penthouse | Nar Shaddaa Promenade — Hutt-controlled tower | Three rooms, Hutt opulence, NPC guard at door |

**Tatooine Jabba's Townhouse slot** is added at rank 3+ as an alternate location (player choice at promotion). This gives Hutt PCs geographic flexibility.

### 5.5 Bounty Hunters Guild — no quarters (unchanged)

The Guild remains housing-agnostic. BHG members rent rooms, live on their ships, or buy private/shopfront housing like any independent. The BHG **chapter house** in Coruscant Southern Underground is a Tier 5 org-HQ slot, not a member quarter.

### 5.6 Independent — no quarters (default)

Unaligned PCs do not receive faction quarters. They use Tier 1 rentals or progress to Tier 3+ on their own credits.

---

## 6. Tier 1 rental locations (CW)

One rental host NPC per qualifying location. Rental hosts are usually innkeepers, cantina staff, or front-desk droids. Lots are "rooms in a building" — the same structural pattern as GCW's Mos Eisley Hotel.

| Planet | Zone | Host building | NPC | Slots | Weekly rent (after security adj.) |
|---|---|---|---|---|---|
| Coruscant | westport_district | Westport Travelers' Hotel | clerk droid `WX-9` | 6 | 50cr (secured = full rate) |
| Coruscant | coco_town | The Outlander (cantina rooms) | "Doola" the bartender | 5 | 38cr (contested = 75%) |
| Coruscant | southern_underground | Crystal Jewel Cantina back rooms | Wesseri (innkeeper) | 6 | 25cr (lawless = 50%) |
| Coruscant | gilded_cage | The Mosaic Hotel | Iri Camas (Twi'lek) | 4 | 38cr |
| Kuat | kuat_main_spaceport | Spaceport Concourse Hotel | KDY hospitality droid | 4 | 50cr |
| Kuat | kuat_city_embassy | Embassy Inn | Talvik Maru (human, KDY-affiliated) | 3 | 50cr |
| Kamino | ocean_platforms | Visiting Officers' Quarters | clone trooper CT-3372 ("Splash") | 3 | 38cr (visitor permits, max 2-week stay) |
| Geonosis | stalgasin_hive_surface | Smuggler's Roost flophouse | Vez Garra (Weequay) | 4 | 25cr |
| Tatooine | mos_eisley_core | Mos Eisley Hotel | (existing NPC, reskin) | 6 | 50cr |
| Tatooine | spaceport_district | Chalmun's Cantina back room | (existing NPC, reskin) | 4 | 38cr |
| Nar Shaddaa | nar_shaddaa_docks | Dock District Flophouse | (existing NPC, reskin) | 4 | 38cr |
| Nar Shaddaa | nar_shaddaa_upper | Promenade Inn | (existing NPC, reskin) | 4 | 38cr |
| Nar Shaddaa | nar_shaddaa_undercity | Smuggler's Den Bunkroom | (existing NPC, reskin) | 5 | 25cr |

**Total CW T1 inventory:** 13 host buildings, 58 rental slots. (GCW has 6 buildings / ~30 slots, so this is ~2× expansion, justified by larger world and Coruscant being the canonical hub.)

**Kamino note:** Tipoca City Platform is **not** rentable. Only the outer Ocean Platforms host visitor lodging, and the system enforces a 2-week stay cap — after which the rental auto-checks-out. This is enforced by the existing rent-tick code; we just author a lot with `max_stay_weeks: 2`. (Schema change: not needed; the existing `rent_overdue` / `rent_paid_until` fields can be reused with a bool flag in the lot record.)

---

## 7. Tier 3 private residence lots (CW)

Tier 3 is the "you own a home" sweet spot. Costs unchanged from `player_housing_design_v1.md` §2.4 (5,000 / 12,000 / 25,000 cr × 100/175/250 weekly rent), discounted by security tier.

### 7.1 Lot inventory

| Planet | Zone | Host room (slug) | Max homes per host | Allowed types | Notes |
|---|---|---|---|---|---|
| Coruscant | coco_town | `coco_town_residential_walk` | 4 | studio, standard, deluxe | Mid-level apartments |
| Coruscant | coco_town | `coco_town_loft_district` | 3 | standard, deluxe | Larger flats |
| Coruscant | calocour_heights | `calocour_marketing_row` | 2 | deluxe only | Luxury — premium pricing |
| Coruscant | calocour_heights | `calocour_overlook_terrace` | 2 | deluxe only | Sky-view condos |
| Coruscant | southern_underground | `underground_tenement_block` | 4 | studio, standard | 50% rent — risky neighborhood |
| Coruscant | gilded_cage | `gilded_cage_alien_quarter` | 4 | studio, standard, deluxe | Diverse, contested |
| Kuat | kdy_orbital_ring | `kdy_engineer_apartments` | 3 | studio, standard | **Republic rep ≥ +25 gated** |
| Kuat | kuat_city_embassy | `embassy_residential_row` | 2 | standard, deluxe | **Republic rep ≥ +25 gated** |
| Geonosis | stalgasin_hive_surface | `stalgasin_offworld_quarter` | 3 | studio, standard | Smuggler/independent niche; 50% rent |
| Tatooine | mos_eisley_core | (existing GCW lot, reskinned) | 4 | studio, standard, deluxe | Existing inventory |
| Tatooine | outskirts | (existing GCW lot, reskinned) | 3 | standard, deluxe | Existing — homestead theme |
| Tatooine | jundland_wastes | (existing GCW lot, reskinned) | 2 | standard, deluxe | 50% rent — Tusken risk, hidden compound |
| Nar Shaddaa | corellian_sector | (existing GCW lot, reskinned) | 3 | studio, standard | Existing |
| Nar Shaddaa | nar_shaddaa_upper | (existing GCW lot, reskinned) | 3 | standard, deluxe | Existing — Promenade flats |
| Nar Shaddaa | nar_shaddaa_undercity | (existing GCW lot, reskinned) | 4 | studio, standard | 50% rent — existing |
| Nar Shaddaa | warrens | **NEW** `warrens_squat_block` | 3 | studio only | 50% rent — deepest, cheapest, most dangerous |

**Total CW T3 inventory:** 16 host rooms. Tatooine and Nar Shaddaa contribute 6 (existing, reskin only). Coruscant contributes 6, Kuat 2, Geonosis 1, plus the new Warrens lot.

### 7.2 Real estate NPC roster

| Planet | NPC | Location | Notes |
|---|---|---|---|
| Coruscant | "Verusi Realty" — Maani Verusi (human broker) | Coco Town main concourse | Handles Coco Town, Calocour, Southern Underground, Gilded Cage |
| Kuat | "KDY Housing Officer" — Lt. Jandar Sek | Kuat City Embassy reception | Handles KDY ring + Embassy; verifies Republic clearance |
| Tatooine | (existing GCW NPC) | Mos Eisley | Reskin only — drop "Imperial property records" mentions |
| Nar Shaddaa | (existing GCW NPC) | Promenade | Reskin only — add "war-time vacancy specials" flavor |
| Geonosis | "Vrethaal" — Geonosian smuggler-broker | Stalgasin Hive Surface market | Off-books real estate; only handles the one offworld-quarter lot |
| Kamino | — | — | No real estate NPC. No T3 inventory. |

---

## 8. Tier 4 shopfront lots (CW)

Shopfronts are public-shop-room + private-residence combos. Per invariant §3, **no shopfronts in lawless zones**. This eliminates Southern Underground, Geonosis, Jundland, Undercity, and Warrens from T4 eligibility.

| Planet | Zone | Host room | Allowed types | Notes |
|---|---|---|---|---|
| Coruscant | coco_town | `coco_town_market_arcade` | stall, merchant, trading | The "most networked" anchor — 4 lots |
| Coruscant | calocour_heights | `calocour_boutique_row` | merchant, trading | Luxury — 2 lots |
| Coruscant | gilded_cage | `gilded_cage_bazaar` | stall, merchant | Alien-quarter market — 3 lots |
| Tatooine | mos_eisley_core | (existing — Mos Eisley Market) | stall, merchant, trading | Existing GCW lot |
| Tatooine | spaceport_district | (existing — Chalmun's exterior) | stall | Existing — small lot |
| Nar Shaddaa | nar_shaddaa_docks | (existing) | stall, merchant | Existing |
| Nar Shaddaa | corellian_sector | (existing) | merchant, trading | Existing |
| Nar Shaddaa | nar_shaddaa_upper | (existing — Promenade) | merchant, trading | Existing — premium |

**Total CW T4 inventory:** 8 host rooms. Coruscant contributes 3 new lots; Tatooine and Nar Shaddaa retain their 5 existing lots (reskin only).

**Coco Town Market Arcade is the flagship CW shopfront location.** Per the FDtS Step 23 promise that "Coco Town is the most networked," this lot should support all three shopfront types and have the highest visibility in `market search` results. Implementation: no engine change needed — the existing market-search ordering already favors Coco Town zone tags via the host-zone Director influence baseline.

---

## 9. Tier 5 organization HQ lots (CW)

GCW has 6 lots across 4 planets. CW expands to 8 lots across 6 planets to give each major faction at least one home turf and to spread BHG/Hutt presence across both major hub planets.

| # | Planet | Zone | Host room | Recommended faction | Tier types allowed |
|---|---|---|---|---|---|
| 1 | Coruscant | coco_town | `coco_town_civic_block` | Republic-aligned player factions | outpost, chapter_house, fortress |
| 2 | Coruscant | southern_underground | `bhg_chapter_house` | BHG | chapter_house, fortress |
| 3 | Coruscant | southern_underground | `crystal_jewel_alley` | Independent (mercenary, smuggler crews) | outpost, chapter_house |
| 4 | Coruscant | gilded_cage | `gilded_cage_courtyard` | Independent (alien fraternal orgs) | outpost, chapter_house |
| 5 | Geonosis | stalgasin_hive_surface | `stalgasin_outsider_compound` | CIS-aligned player factions | outpost, chapter_house, fortress |
| 6 | Tatooine | jabbas_townhouse | (existing GCW lot, reskin) | Hutt | outpost, chapter_house, fortress |
| 7 | Tatooine | outskirts | (existing GCW lot, reskin) | Independent | outpost, chapter_house |
| 8 | Nar Shaddaa | nar_shaddaa_undercity | (existing GCW lot, reskin) | Hutt | chapter_house, fortress |
| 9 | Nar Shaddaa | nar_shaddaa_upper | **NEW** `promenade_corporate_tower` | BHG, Independent merc orgs | chapter_house, fortress |

That's 9, not 8 — I added the Nar Shaddaa Promenade slot because the BHG presence is canonical there (the Hunters' Guild had a chapter on the Smuggler's Moon long before CW). Easy to drop if 8 is preferred.

**Faction-tier defaults** (existing engine concept — "recommended faction" doesn't lock out other orgs, just biases the description templates):

- BHG slots get bounty-hunter-themed descriptions (trophy walls, bounty boards, armor lockers).
- Hutt slots get Hutt-opulent descriptions (gilded everything, hookah lounges).
- Republic slots get military-formal descriptions (briefing rooms, signal-secure comms).
- CIS slots get industrial-Geonosian descriptions (hive-carved chambers, droid maintenance bays).
- Independent slots get neutral generic descriptions (the org leader writes their own).

---

## 10. Tatooine and Nar Shaddaa reskin notes

Cosmetic only. No structural housing changes — every existing GCW lot remains in its existing zone with its existing slot count. The only deltas are string-level:

### 10.1 Tatooine

- **Mos Eisley Hotel descriptions:** drop "Imperial customs notices" and "stormtrooper patrol schedule"; replace with "Republic patrol notice (rare)" or simply "local prefect's bulletin."
- **Chalmun's back-room:** remove any "wanted poster for Rebel sympathizers"; replace with "wanted poster for war deserters" or remove entirely.
- **Outskirts homesteads:** drop references to Lars-family neighbors; era-neutralize to "the Whitesun homestead, two ridges over" (canon-friendly).
- **Jundland hidden compound:** drop "smuggler hideout from Imperial patrols" → "smuggler hideout from Republic and CIS sweeps alike."
- **Real estate NPC:** rename if the GCW NPC has an Imperial-flavored name; drop any "Imperial property records" line.

### 10.2 Nar Shaddaa

- **Undercity Hutt safehouse:** add a one-line flavor about "war-profiteer guests passing through" — Hutts profit from both sides.
- **Promenade penthouse:** drop "Imperial Moff diplomatic visit" memorabilia → "Senate diplomatic credential, recently expired."
- **Real estate NPC:** add "wartime vacancy bonuses" patter to the spiel.

These are all 1–2 line edits in the host-room descriptions, nothing structural.

---

## 11. The `housing_lots.yaml` shape

Per `world_data_extraction_design_v1.md` §3, each era has its own `housing_lots.yaml` under `data/worlds/<era>/`. Here's the target shape for `data/worlds/clone_wars/housing_lots.yaml`:

```yaml
# Tier 1 rental hosts
tier1_rental_hosts:
  - id: westport_travelers_hotel
    planet: coruscant
    zone: westport_district
    host_room: westport_arrivals_hotel_lobby   # slug, resolved at load
    npc: rental_clerk_wx9
    slots: 6
    weekly_rent_base: 50
    description_theme: corporate_chain
  - id: outlander_rooms
    planet: coruscant
    zone: coco_town
    host_room: outlander_cantina
    npc: doola_bartender
    slots: 5
    weekly_rent_base: 50
    description_theme: cantina_back_room
  # ... all 13 entries

# Tier 3 private residence lots
tier3_lots:
  - id: coco_town_residential_walk
    planet: coruscant
    zone: coco_town
    host_room: coco_town_residential_walk
    max_homes: 4
    allowed_types: [studio, standard, deluxe]
    description_theme: midlevel_apartment
  - id: kdy_engineer_apartments
    planet: kuat
    zone: kdy_orbital_ring
    host_room: kdy_engineer_apartments
    max_homes: 3
    allowed_types: [studio, standard]
    description_theme: industrial_dormitory
    rep_gate:
      faction: republic
      min_value: 25
  # ... all 16 entries

# Tier 4 shopfront lots
tier4_lots:
  - id: coco_town_market_arcade
    planet: coruscant
    zone: coco_town
    host_room: coco_town_market_arcade
    max_homes: 4
    allowed_types: [stall, merchant, trading]
    description_theme: bustling_arcade
    market_search_priority: 100   # flagship CW shopfront location
  # ... all 8 entries

# Tier 5 organization HQ lots
tier5_lots:
  - id: coco_town_civic_block
    planet: coruscant
    zone: coco_town
    host_room: coco_town_civic_block
    max_homes: 1   # one HQ per host room for T5
    allowed_types: [outpost, chapter_house, fortress]
    recommended_faction: republic
    description_theme: republic_civic
  # ... all 9 entries

# Tier 2 faction quarter assignments (NEW for CW — replaces FACTION_QUARTER_TIERS hardcode)
faction_quarters:
  republic:
    default_location:
      planet: coruscant
      zone: coco_town
      building: republic_guard_barracks
    alternate_locations:
      - planet: kuat
        zone: kdy_orbital_ring
        building: kdy_engineer_dormitory
        rank_minimum: 2
    tiers:
      - rank_min: 0
        rank_max: 1
        type: bunk
        rooms: 1
        storage_max: 20
        description_theme: republic_bunk
      - rank_min: 2
        rank_max: 3
        type: private
        rooms: 1
        storage_max: 30
        description_theme: republic_officer_cell
      - rank_min: 4
        rank_max: 4
        type: suite
        rooms: 2
        storage_max: 50
        description_theme: republic_officer_suite
      - rank_min: 5
        type: commander_suite
        rooms: 3
        storage_max: 100
        description_theme: republic_judicial_suite
        location_override:           # commander rank moves to Senate-adjacent
          planet: coruscant
          zone: senate_district
          building: judicial_forces_compound
  cis:
    default_location:
      planet: geonosis
      zone: stalgasin_deep_hive
      building: cis_recruit_dormitory
    tiers: # ... mirrors structure
  jedi_order:
    default_location:
      planet: coruscant
      zone: jedi_temple
      building: jedi_temple_dormitories
    tiers:
      - rank_min: 0
        rank_max: 0
        type: dorm
        rooms: 1
        storage_max: 20
        description_theme: jedi_initiate_cluster
      - rank_min: 1
        rank_max: 2
        type: padawan_cell
        rooms: 1
        storage_max: 30
        description_theme: jedi_padawan_wing
      - rank_min: 3
        rank_max: 4
        type: knight_quarters
        rooms: 2
        storage_max: 80
        description_theme: jedi_knight_wing
      - rank_min: 5
        type: master_suite
        rooms: 3
        storage_max: 120
        description_theme: jedi_master_wing
        gating:
          requires_trial: knight_trial   # hooks into existing Jedi advancement
  hutt_cartel:
    # ... mirrors GCW Hutt structure with minor flavor adjustments
  bhg: null    # No faction quarters — BHG members rent or own privately
```

**Loader notes** (for whoever ships the YAML loader piece in F.5):

1. The `host_room` field is a **slug** that the loader resolves to a room ID via the room-slug map produced by `world_data_extraction_design_v1.md`'s extractor. This means lot YAML never references hardcoded room IDs.
2. `description_theme` strings map to template descriptions in a sibling `housing_descriptions.yaml` (or could be inlined; recommend separate file for translatability).
3. `rep_gate` is the new field — `engine/housing.py::list_available_lots()` needs a one-line check to filter lots whose rep gate the requesting character doesn't meet. This is a **micro-engine change** (~10 lines) — the only engine work this design implies. See §13.
4. `gating.requires_trial` for Jedi master suite hooks into the existing Jedi-rank progression logic. Already a no-op if the trial system isn't shipped — Jedi can't reach rank 5 without the trial regardless.
5. `faction_quarters` replaces the `FACTION_QUARTER_TIERS` Python hardcode currently in `engine/housing.py`. This is the second micro-engine change (data-fy the table).

---

## 12. Files affected

| File | Change | Type |
|---|---|---|
| `data/worlds/clone_wars/housing_lots.yaml` | NEW — full inventory above | Data |
| `data/worlds/clone_wars/housing_descriptions.yaml` | NEW — description theme strings | Data |
| `data/worlds/clone_wars/npcs.yaml` | ADD — 5 new real-estate / rental-host NPCs | Data |
| `engine/housing.py` | Two micro-changes: `rep_gate` filtering in `list_available_lots()`, data-fy `FACTION_QUARTER_TIERS` to load from era YAML | Engine (small) |
| `engine/npc_loader.py` | Already era-aware as of F.1a — no change | — |
| `data/worlds/gcw/housing_lots.yaml` | NEW — extracted from existing hardcodes for parity (per Drop 0 invariant) | Data |
| `tests/test_housing_lots_loader.py` | NEW — load both eras, assert lot counts and rep_gate behavior | Test |
| `tests/test_jedi_quarters.py` | NEW — verify Jedi tier ladder, including rank-5/trial gating | Test |
| Architecture doc v37+ | Note CW housing under Priority F.5 | Doc |

**Engine change estimate:** ~80 LOC across `housing.py`, two small tests. The bulk of the work is YAML authoring.

---

## 13. The two micro-engine changes

These are small enough to ship inside F.5 without a separate drop. Calling them out so they don't get missed.

### 13.1 `rep_gate` filtering in `list_available_lots()`

```python
# engine/housing.py — new lot-filter helper
def _passes_rep_gate(character, lot) -> bool:
    rep_gate = lot.get("rep_gate")
    if not rep_gate:
        return True
    char_rep = character.faction_reputation.get(rep_gate["faction"], 0)
    return char_rep >= rep_gate["min_value"]

# Existing list_available_lots() filters with a one-liner addition:
lots = [lot for lot in tier3_lots if _passes_rep_gate(character, lot)]
```

A character with insufficient Republic rep simply doesn't see the Kuat lots in the broker's listing. The broker NPC's response can mention it ("I'd love to show you our Kuat properties, but I need to see your clearance papers first"), or omit it silently — design choice. **Recommend silent omission**, with the broker's intro patter mentioning it generically.

### 13.2 `FACTION_QUARTER_TIERS` data-fication

Currently a Python dict in `engine/housing.py`. The CW YAML structure in §11 supports the same fields plus the new ones (`alternate_locations`, `gating`). Refactor:

```python
# Before (hardcoded):
FACTION_QUARTER_TIERS = {
    "imperial": {...},
    "rebel": {...},
    "hutt": {...},
}

# After (data-loaded):
FACTION_QUARTER_TIERS = load_faction_quarters_from_yaml(active_era)
```

This is byte-equivalent for GCW once the GCW `housing_lots.yaml` is authored from the existing hardcodes (parallel work to Drop 0).

---

## 14. Open questions (and recommended resolutions)

### 14.1 Should Kuat allow CIS-aligned PCs *any* T1 lodging?

Lore says no — KSF would deport them. But mechanically, locking out an entire faction from a hub planet is harsh.

**Recommendation:** Yes, allow Kuat Main Spaceport T1 only (transient hotel). The lore is "you can land at the spaceport but you can't ride the lifts up to the ring." A 2-week stay cap (same as Kamino) keeps it honest.

### 14.2 Should Coruscant Senate District have any housing?

Senators live there in canon, but PCs aren't Senators. Allowing T3 lots there opens the door to "I bought a flat next to the Chancellor."

**Recommendation:** No housing in Senate District. Period. Players who want "I live near power" buy a Calocour Heights deluxe instead.

### 14.3 Should the Jedi Temple have non-Jedi accessible housing?

Visiting diplomats stay there in canon (shrouded chambers, Jedi guest hospitality).

**Recommendation:** No. Keep the Temple Jedi-only. "Visiting diplomat" housing is too narrow a player niche to justify the engine complexity around faction-rank gating without faction membership.

### 14.4 Should Tatooine retain its Jundland Wastes housing?

Jundland is a wilderness-edge zone. The current GCW design has a hidden-compound homestead lot there. CW Jundland has the same Tusken risk and no faction shift.

**Recommendation:** Yes, retain. Wastes housing is a great fit for the lawless-zone discount loop and it's existing content. No reskin needed beyond removing any "Imperial scout patrol" references.

### 14.5 Should Geonosis have a player shopfront anywhere?

Lawless rules say no T4 in lawless zones. Stalgasin Hive Surface is lawless. So: no.

**Recommendation:** Confirmed no T4 on Geonosis. Smugglers who want to sell Separatist gear can do it via Tatooine or Nar Shaddaa T4 lots (with appropriate `market search` filtering for Separatist contraband, which is a future concern).

### 14.6 Should Jedi Master suites be limited in count?

If 50 players all reach rank 5 simultaneously, do we have 50 Master suites in the Temple? The current engine (no per-faction lot count) treats faction quarters as inexhaustible — same as GCW Imperial quarters.

**Recommendation:** Treat as inexhaustible, same as other faction quarters. The Jedi Order's canonical roster is in the thousands; we can absorb 50 PCs without breaking immersion. Revisit if the playerbase ever reaches that scale.

### 14.7 What about player-ranchers / moisture farmers on Tatooine?

The existing Outskirts homestead lot fills this niche. No additional design needed.

### 14.8 What about Coruscant Underworld wilderness housing?

The wilderness system (F.5 sibling) handles this with a separate `wilderness_caches` mechanic, not housing. PCs may build a "stash" in a wilderness tile, but that's a wilderness feature, not Tier 1–5 housing. **Out of scope for this design.**

---

## 15. What this design does NOT cover

To be explicit about what F.5 implementers should expect:

1. **Wilderness housing** (Coruscant Underworld stashes). Separate design, separate system.
2. **Ship housing for the new ship classes** — every CW-era ship retains existing Tier 0 ship-berth behavior; nothing new needed.
3. **Player-built crafting stations in homes** — design exists in player_housing_design_v1.md §7.2, no era changes needed.
4. **Org HQ guard NPC stat blocks for CW** — those are in `data/worlds/clone_wars/npcs.yaml` (per F.1a) and out of scope here.
5. **Coruscant Senate "honorary residence" perks** for Republic high-rep PCs. Cute, complex, not necessary at launch.

---

## 16. Drop sequencing within F.5

F.5 in v37 is "Coruscant Underworld wilderness + housing + test characters." This design covers the housing slice. Suggested sub-ordering:

- **F.5a — `housing_lots.yaml` + `housing_descriptions.yaml` authoring + GCW parity extraction.** Pure data work. Includes the GCW extraction so Drop 0's equivalence test passes. ~2 sessions.
- **F.5b — Engine micro-changes** (rep gate + `FACTION_QUARTER_TIERS` data-fication) + tests. ~1 session.
- **F.5c — Real-estate NPC authoring in `npcs.yaml`** (5 new NPCs). Tiny. Can fold into F.5a if convenient.
- **F.5d — Jedi Temple integration test** — a Jedi PC at rank 0/1/3/5 sees the right quarters. ~½ session.

Wilderness and test characters proceed in parallel — they don't touch any of the housing files.

---

## 17. Architecture-doc updates

For the next architecture rollup (v38):

- §12 Player Housing — add subsection: "**v38 — CW era support.** `data/worlds/clone_wars/housing_lots.yaml` adds 13 T1 hosts, 16 T3 lots, 8 T4 shopfront lots, 9 T5 org-HQ lots, and 5 faction-quarter ladders (Republic, CIS, Jedi Order, Hutt Cartel, BHG-null). Engine adds `rep_gate` lot filtering and data-loaded `FACTION_QUARTER_TIERS`. GCW housing data extracted to `data/worlds/gcw/housing_lots.yaml` for parity."
- §19.3 Tier 2 — under Priority F, mark F.5 with sub-status reflecting housing design completion.
- §25 design docs — add `cw_housing_design_v1.md` reference.

---

*End of CW Housing & Real Estate Design Document — Version 1.0*
*Reference: player_housing_design_v1.md, clone_wars_era_design_v3.md, world_data_extraction_design_v1.md, from_dust_to_stars_design_v2_clone_wars.md, sw_d6_mush_architecture_v37_consolidated.md*
