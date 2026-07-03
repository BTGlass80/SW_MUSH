---
category: community
order: 5
summary: "Rent a room, buy a private residence, run a shopfront, or claim faction quarters. Storage, trophies, guest access, and the weekly rent cycle."
tags: ["housing", "home", "rent", "storage", "shopfront", "trophy", "real estate", "faction quarters"]
---

# Housing

**Parsec — WEG D6 Revised & Expanded**
**BTGlass80 — July 2026**
**Guide Version 1.0**

---

## How to Read This Guide

Every character needs somewhere to sleep, stash gear, and stop being "the person standing in the cantina." Housing is the system that gives you that place — anything from a rented bunk above a Coruscant cantina to a townhouse with its own storefront to a barracks bed that comes with your faction rank.

This guide covers all five housing tiers, how to rent or buy into each one, what a home actually gives you (storage, trophies, guest access, description control, a cosmetic prestige ladder), the weekly rent cycle and what happens if you fall behind, and the real security risk of owning property in a zone that isn't fully locked down.

If you only have ten minutes, read **§1 The Five Tiers** and **§2 Tier 1: Renting a Room**. That covers what most new characters actually do in their first session — find a rental hub, pay the deposit, move in. Everything past that is for characters who've saved up and want to own something.

This is a new guide. There was no earlier version.

---

## 1. The Five Tiers

Housing comes in five tiers. You don't have to climb them in order — a wealthy new character can walk straight to a real estate broker and buy a Tier 3 home on day one — but most characters start with Tier 1 and work upward as their credits allow.

| Tier | What it is | Cost model | Who it's for |
|---|---|---|---|
| **1 — Rented Room** | A single locked room in a rental hub (inn, cantina back rooms, a flophouse) | Deposit + weekly rent | Anyone; the default starter home |
| **2 — Faction Quarters** | Assigned billet inside your faction's own building | Free — comes with faction rank | Republic, CIS, Jedi Order, and Hutt Cartel members |
| **3 — Private Residence** | A standalone owned home, 1–3 rooms, at a real estate lot | One-time purchase + weekly rent | Characters with real savings who want a permanent base |
| **4 — Shopfront Residence** | An owned home with a public-facing shop room bolted onto the front | One-time purchase + weekly rent | Crafters and merchants who want a dedicated storefront |
| **5 — Organization HQ** | A multi-room complex owned by a player faction/org, not an individual | Purchased from org treasury | Org leaders building a home base for their group |

A few things that cut across all five tiers:

- **Storage, trophies, and a description editor work on any home you own or rent**, Tier 1 included. You don't need to "earn" your way to a nicer home before you can decorate the one you have.
- **`home`** (also `+home`) with no arguments teleports you to your set home location, wherever it is. **`housing`** (also `+home`, `myroom`, `homelocation`) with no arguments shows your current housing status, or — if you don't have a home yet — the locations available on your current planet.
- You can own **more than one home at once**. Up to four Tier 3 private residences and up to two Tier 4 shopfronts (one per planet) can all exist under the same character simultaneously, alongside faction quarters if you have them. Storage, trophies, and sale/checkout act on whichever home you're **standing in**; if you're not inside any of your homes, they act on the one you most recently acquired. `housing list` shows every home you own and flags which one you're currently in.

---

## 2. Tier 1: Renting a Room

This is the fast, cheap option — a private room with a locking door, reachable from a public rental hub. It's the housing equivalent of a starter apartment.

**Finding a room.** Rental hubs exist across the galaxy — hotels, cantina back rooms, station bunkrooms, and flophouses on every playable world, run by an innkeeper or a hospitality droid. Stand near one and type `housing` with no arguments; if you don't already have a home, the status screen lists the housing lots available on your current planet, each with an ID number and how many slots are open.

**Renting.**

```
housing rent <id>
```

Renting costs a flat **500 cr deposit plus 50 cr for the first week's rent** (550 cr total) — the same everywhere, regardless of planet or how rough the neighborhood is. The system builds you a private room off the host location, sets it as your home automatically, and tells you which direction to walk to reach it. From then on:

- **50 cr/week** rent, collected automatically.
- **20 storage slots**, plus the trophy wall and description editor available to every tier (see §7–§8).
- A locked door — nobody without guest access can walk in.

**Leaving.**

```
housing checkout
```

Vacates the room, returns your 500 cr deposit (unless your rent is currently overdue — see §9), and moves anything in storage or on your trophy wall back into your inventory. You can only hold one Tier 1 rental at a time, and you can't rent a second Tier 1 room while you already have *any* home — rent one, then upgrade to something bigger later; you don't stack starter rooms.

---

## 3. Tier 2: Faction Quarters

If you belong to a faction, you don't rent — the faction houses you. Quarters are assigned automatically the moment you reach the qualifying rank, and upgraded or revoked automatically as your rank changes. There's no purchase command; it just happens.

| Faction | Rank 0–1 | Rank 2–3 | Rank 4 | Rank 5+ |
|---|---|---|---|---|
| **Galactic Republic** | Shared bunk, Coco Town barracks (10 storage) | Private cell (30 storage) | Officer's suite, two rooms (50 storage) | Commander's compound, Senate-adjacent (100 storage) |
| **Confederacy of Independent Systems** | Recruit dormitory, Stalgasin Deep Hive (10 storage) | Private alcove (40 storage) | Officer's chamber, two rooms (80 storage) | Council suite, three chambers (100 storage) |
| **Jedi Order** | Initiate cluster (10 storage) | Padawan cell (30 storage, from rank 1) | — | Knight quarters at rank 3 (80 storage); Master suite at rank 5 (100 storage) |
| **Hutt Cartel** | No quarters below rank 2 | Enforcer's safehouse, Nar Shaddaa undercity (30 storage) | Lieutenant's suite (50 storage) | Vigo's penthouse (100 storage) |
| **Bounty Hunters' Guild** | No faction quarters at any rank | — | — | — |

The Bounty Hunters' Guild doesn't house its members — Guild contractors are independent operators by design. If you're a bounty hunter, you're renting or buying like anyone else (or living aboard your ship).

Faction quarters are **free** — no weekly rent, ever — and they come with the same storage, trophy wall, and description tools as any other home. What they don't offer is a guest list you manage yourself in the usual sense; access follows your faction's own rules. Losing your qualifying rank (demotion, expulsion, or leaving the faction) revokes the quarters, and anything inside is returned to your inventory.

---

## 4. Tier 3: Private Residences

This is real ownership — a standalone 1–3 room home, purchased outright at a real estate lot, yours until you choose to sell.

| Type | Rooms | Purchase Price | Weekly Rent | Storage |
|---|---|---|---|---|
| **Small Dwelling** | 1 | 5,000 cr | 100 cr | 40 |
| **Standard Home** | 2 | 12,000 cr | 175 cr | 80 |
| **Large Home** | 3 | 25,000 cr | 250 cr | 120 |

**Buying.**

```
housing buy                    — see available lots and home types
housing buy <type> <lot_id>    — purchase (type: small / standard / large)
```

Typing `housing buy` with no arguments shows every Tier 3 lot open on the galaxy's real estate market, along with the three home types and their prices. Pick a lot ID, pick a type, and the price is debited in full up front — there's no weekly-rent discount for buying in a rougher part of town; the rent listed above is what you pay regardless of zone. If you were renting a Tier 1 room or living in faction quarters, buying a private residence automatically rolls that arrangement over — your old room is checked out for you.

**How many you can own.** Up to **four** Tier 3 private residences at once, anywhere in the galaxy — you are not limited to one per planet. Standard and Large homes get a guest access list (§7); the Small Dwelling does too, in practice, since guest access is gated by tier rather than by home type.

**Selling.**

```
housing sell           — see your refund quote
housing sell confirm   — sell for 50% of the purchase price
```

Everything in storage and on the trophy wall is returned to your inventory before the sale completes.

**A note on Kuat.** The Kuat Drive Yards housing market (the orbital ring and the embassy district) is reserved for characters with meaningful standing with the Republic. If your Republic reputation isn't high enough, those lots simply don't appear in your listing — the broker doesn't advertise property you can't have.

---

## 5. Tier 4: Shopfront Residences

A shopfront is a private residence with a public storefront bolted onto the front of it — the trader's version of Tier 3. The shop room(s) are open to any customer; the rooms behind them are yours alone.

| Type | Layout | Purchase Price | Base Weekly Rent | Storage | Vendor Droid Slots |
|---|---|---|---|---|---|
| **Market Stall** | 1 shop + 1 private room | 15,000 cr | 200 cr | 60 | 2 |
| **Merchant's Shop** | 1 shop + 2 private rooms | 28,000 cr | 300 cr | 100 | 3 |
| **Trading House** | 2 shop + 3 private rooms | 40,000 cr | 400 cr | 150 | 4 |

**Buying.**

```
housing shopfront                    — see available lots and shop types
housing shopfront <type> <lot_id>    — purchase (type: stall / shop / trading_house)
```

Shopfront rent is the one place zone security actually moves the price: a shopfront in a fully secured district pays the full weekly rent listed above; a **contested** zone knocks **25% off**; a **lawless** zone knocks **50% off** (with a 50 cr/week floor). Riskier neighborhoods are cheaper to operate in — they're just riskier.

**Why bother over Tier 3.** A shopfront raises your personal vendor droid cap by one for every shopfront you own (base cap is 3; owning shopfronts pushes it up to a maximum of 6), and vendor droids placed in a shopfront's shop room get listed in the planet-wide `market search` directory (see the Player Shops guide) so customers can find you without ever walking past your storefront in person.

**Limits.** Up to **two** shopfronts per character, and no more than **one per planet**.

**Selling.**

```
housing sell           — see your refund quote (also works for shopfronts)
housing sell confirm   — sell for 50% of the purchase price; any placed vendor droids are recalled automatically
```

---

## 6. Tier 5: Organization Headquarters

An HQ is a multi-room complex owned by a player faction or guild, not by any one character. It's purchased and managed through your faction leadership commands rather than the housing family — see the Organizations & Factions guide for the full picture of faction rank and treasury management. The mechanics, briefly:

| Type | Rooms | Purchase Price | Weekly Maintenance | Storage | Guard Slots |
|---|---|---|---|---|---|
| **Small Outpost** | 4 | 50,000 cr | 500 cr | 100 | 2 |
| **Chapter House** | 6 | 100,000 cr | 1,000 cr | 200 | 4 |
| **Fortress** | 9 | 150,000 cr | 1,500 cr | 400 | 6 |

```
faction hq                          — view your org's HQ status
faction hq locations                — see available HQ lots
faction hq purchase <type> <lot_id> — establish an HQ (leader only, paid from org treasury)
faction hq sell [confirm]           — disband the HQ for a 25% refund to the treasury
```

Only your organization's leader can purchase or sell an HQ, and the cost comes out of the org treasury, not your personal wallet. An org can hold exactly one HQ at a time.

---

## 7. Storage, Trophies & Guest Access

These three tools work identically across every tier you own or rent — Tier 1 included.

**Storage.**

```
housing storage           — list what's in your home storage
housing store <item>      — move an item from your inventory into storage
housing retrieve <item>   — move an item back out
```

Storage capacity is set by your home's tier and type (20 slots for a Tier 1 room, up to 120–150 for a Large Home or Trading House — see the tables above). If you're a multi-home owner, these commands act on the home you're currently standing in; away from all of them, they default to the home you most recently acquired.

**Trophies.**

```
housing trophy <item>     — mount an item from inventory on your wall (10 max)
housing untrophy <item>   — take it back down
housing trophies          — list what's mounted
```

Mounted trophies show up in the room's `look` output to anyone who walks in — they're the display case for gear you're proud of. You can un-mount and re-equip a trophy any time; nothing is lost by mounting it.

**Guest access.**

```
housing guest add <player>      — grant entry to a locked home while you're offline
housing guest remove <player>
housing guest list
```

Guest lists are available on any purchased Tier 3 residence (Small Dwelling and up) and on faction quarters; a bare Tier 1 rental is private to you alone. Up to **10 names** on a guest list at once.

**Visiting a shopfront.**

```
housing visit <player>
```

Points you toward a player's public shopfront, if they have one — handy for finding a specific merchant's storefront without knowing the room name.

---

## 8. Naming, Description & Prestige

**Renaming your room.**

```
housing name <new name>
```

Your first rename is free. Every rename after that costs **1,000 cr**.

**Writing a description.**

```
housing describe
```

This opens a line-by-line description editor — type your description a line at a time, then finish with `.done` to save. `.clear` wipes the buffer and starts over, `.show` previews what you've typed so far, and `.cancel` aborts without saving. If you'd rather not write it from scratch, `.suggest` (optionally `.suggest <a style or mood>`) asks the AI for a draft you can `.accept` and then edit or save as-is. Descriptions run 10–2,000 characters and there's no charge for writing or rewriting one — unlike renaming, editing your description is always free.

**Home prestige.**

```
+home prestige         — show your home's current prestige tier
+home prestige buy     — buy the next tier up
```

Prestige is a purely cosmetic credit sink — five escalating tiers of "how nice is this place," each adding a flavor line to your home's status and nothing mechanical. It's there for players with more credits than shopping list. The tiers, in order: **Tastefully Furnished** (5,000 cr), **Finely Appointed** (15,000 cr), **Luxuriously Outfitted** (40,000 cr), **A Connoisseur's Residence** (100,000 cr), and **A Sector-Renowned Estate** (250,000 cr). Each tier is a separate purchase from the last; there's no bundle discount for going straight to the top. Note that prestige applies to your most recently acquired home, not necessarily the one you're currently standing in, if you own more than one.

---

## 9. Rent, Upkeep & Eviction

Rent is collected automatically once a week (real time) for any tier that carries a weekly cost — Tier 1 rentals, Tier 3 residences, and Tier 4 shopfronts. Faction quarters (Tier 2) never charge rent.

**If you can afford it,** the payment is silently deducted and you get a quiet confirmation line if you're online. **If you can't,** nothing is deducted — you're never driven into a negative balance by rent — but the week counts against you as overdue, and you get a warning telling you how many weeks you have left before eviction.

**Four consecutive missed weeks means eviction.** The room is reclaimed automatically. You don't lose anything sitting in storage or on the trophy wall — everything is returned to your inventory the same way a voluntary checkout works — but your deposit (Tier 1 only) is forfeited if you were behind on rent when it happened.

The healthiest habit is the simple one: keep enough in your wallet to cover a week or two of rent, and check `housing` occasionally if you've been away from the game for a while.

---

## 10. Security & Privacy — Locks, Break-Ins & Theft

Your home's door security depends entirely on the security tier of the zone it's built in.

**Secured zones.** The door cannot be picked or forced, and nothing can be stolen from inside. This is the fully safe option — if you want zero risk, rent or buy somewhere secured.

**Contested zones.** The door can be picked with a Very Difficult Security check. Forcing the door outright doesn't work here — only picking does.

**Lawless zones.** The door can be picked with a Difficult Security check, or forced open with a Moderate Brawling (Strength) check. Lawless housing is the cheapest and closest to the best resources — and the most exposed.

An intruder who gets past your door can attempt to steal a **mounted trophy** (never anything sitting in storage — storage is never a theft target) with a Sneak check: Moderate in a lawless zone, or a much harder combined Sneak-and-Security check in a contested one. A failed break-in or theft attempt alerts you immediately if you're online, and every attempt — successful or not — is logged.

```
lockpick             — attempt to pick a housing door you're standing next to (alias: pick)
forcedoor            — attempt to force a housing door in a lawless zone (aliases: breakin, force door)
steal <item>         — attempt to steal a mounted trophy once you're inside (aliases: pilfer, swipe)
housing intrusions   — as an owner, review the log of break-in attempts against your home
```

The practical takeaway: what you display on your trophy wall in a contested or lawless home is a real risk decision, not just decoration. Keep your best gear equipped or in storage, and reserve the trophy wall for things you're willing to lose.

---

## 11. Per-Planet Availability

Housing exists on every playable world, but the mix of tiers varies by planet and by neighborhood.

| Planet | What's there |
|---|---|
| **Coruscant** | The deepest housing market in the galaxy — rental rooms, private residences, shopfronts, and org HQ lots across Coco Town, the Southern Underground, the Gilded Cage alien quarter, and the luxury Calocour Heights district. The Jedi Temple hosts Jedi Order quarters only; no rentals or purchases there. |
| **Kuat** | A restricted, industrial market — a transient hotel at the main spaceport (anyone), plus private residences and Republic Guard faction quarters around the KDY orbital ring and the city embassy, gated to characters with real Republic standing. |
| **Kamino** | The most restricted world in the housing market. Republic faction quarters exist at Tipoca City; the only lodging open to visitors is a small set of officers' quarters out on the ocean platforms. |
| **Geonosis** | Lawless surface flop-housing, a small private-residence lot, and CIS faction quarters deep in the Stalgasin Hive. No shopfronts — the surface doesn't support one. |
| **Tatooine** | The traditional starter world: rental rooms in Mos Eisley and Chalmun's Cantina, private residences in Mos Eisley and the Outskirts (including a hidden Jundland Wastes homestead lot), a market shopfront, and a Hutt-affiliated org HQ lot. |
| **Nar Shaddaa** | Dense rental and residence coverage across the docks, the Corellian Sector, and the Promenade, plus the cheapest and most dangerous lots of all in the Warrens. Hutt Cartel faction quarters and Hutt/Bounty-Hunter org HQ lots are both here. |

Type `housing` while standing on any planet to see exactly what's open near you right now — the listing is always local to your current world.

---

## 12. Worked Examples

**Renting your first room.** You've just arrived on Coruscant with a few hundred credits and nowhere to sleep. You walk into a rental hub in Coco Town and type `housing`. The status screen lists three or four local lots by ID, each showing open slots. You pick one: `housing rent 4`. The system debits 550 cr (500 cr deposit, 50 cr first week), builds your room, and tells you which direction to walk from the lobby. You go there, type `housing describe`, write two lines about your cramped rented room, `.done`, and you're moved in. Total cost: under ten minutes and 550 cr.

**Upgrading to a private residence.** Three months later you've saved 15,000 cr. You visit a real estate lot in the same district and type `housing buy` to see what's open — a Standard Home lot with two units still free. `housing buy standard 7` debits 12,000 cr, checks out your old rental room automatically, and builds you a two-room home with 80 storage slots and a guest list. You add your regular co-op partner with `housing guest add`, so they can drop off gear even when you're offline.

**Opening a shopfront.** You've been crafting weapons for a while and want a dedicated storefront instead of hauling a vendor droid to a public square every session. You find a Market Stall lot in a contested zone and buy in with `housing shopfront stall 12` — 15,000 cr, and because the zone is contested your weekly rent comes to 150 cr instead of the full 200. You place your vendor droid in the shop room; it now shows up in `market search` for anyone browsing that planet's shopfronts, and your personal droid cap rises from 3 to 4.

**Faction quarters, no shopping required.** Your clone trooper reaches Sergeant rank in the Republic. Nothing changes about how you play — but the next time you check `housing`, you're already assigned a private cell in the Coco Town barracks, free of charge, with 30 storage slots. If you'd rather keep your rented room instead, that's fine too; faction quarters don't force a move.

**A break-in you didn't see coming.** You mounted your prize vibroblade on the trophy wall of your Nar Shaddaa Undercity home — lawless zone, cheap rent, real risk. While you're offline, someone works the lock with a Difficult Security check, gets in, and rolls a Moderate Sneak check against your vibroblade. It succeeds. You log back in to a `housing intrusions` entry logging the theft and an empty spot on the wall. Your storage locker — untouched, because storage was never a target — still has everything else you own.

---

## 13. Numbers At A Glance

| Quantity | Value |
|---|---|
| Tier 1 deposit | 500 cr (refunded on checkout unless rent is overdue) |
| Tier 1 weekly rent | 50 cr |
| Tier 1 storage | 20 slots |
| Small Dwelling / Standard Home / Large Home cost | 5,000 / 12,000 / 25,000 cr |
| Small / Standard / Large weekly rent | 100 / 175 / 250 cr |
| Small / Standard / Large storage | 40 / 80 / 120 slots |
| Max Tier 3 homes owned at once | 4, anywhere in the galaxy |
| Market Stall / Merchant's Shop / Trading House cost | 15,000 / 28,000 / 40,000 cr |
| Stall / Shop / Trading House weekly rent (secured zone) | 200 / 300 / 400 cr |
| Shopfront rent discount | −25% contested, −50% lawless (50 cr/week floor) |
| Stall / Shop / Trading House storage | 60 / 100 / 150 slots |
| Vendor droid slots (Stall / Shop / Trading House) | 2 / 3 / 4 |
| Max shopfronts owned | 2 total, 1 per planet |
| Personal vendor droid cap | 3 base, +1 per shopfront owned, capped at 6 |
| Small Outpost / Chapter House / Fortress cost | 50,000 / 100,000 / 150,000 cr |
| Small Outpost / Chapter House / Fortress weekly maintenance | 500 / 1,000 / 1,500 cr |
| Home / shopfront / HQ resale refund | 50% / 50% / 25% of purchase price |
| Storage/trophy wall/description editor availability | Any tier, including Tier 1 |
| Guest list cap | 10 names |
| Guest list availability | Tier 3+ residences and faction quarters |
| Trophy wall cap | 10 items |
| Room rename cost | Free first time, 1,000 cr after |
| Room description length | 10–2,000 characters, always free to change |
| Home prestige tiers | 5,000 / 15,000 / 40,000 / 100,000 / 250,000 cr (5 tiers) |
| Rent collection interval | Weekly (real time) |
| Weeks overdue before eviction | 4 |
| Lockpick difficulty — contested / lawless | Very Difficult (25) / Difficult (20) |
| Force door difficulty — lawless only | Moderate Brawling/Strength (15) |
| Theft difficulty — contested / lawless | Heroic Sneak+Security (30) / Moderate Sneak (15) |
| Theft target | Mounted trophies only — never storage |

---

## 14. Commands Quick Reference

| Command | What it does |
|---|---|
| `housing` (aliases: `+home`, `myroom`, `homelocation`) | Show your housing status, or nearby lots if you have none |
| `home` (alias: `+home`) | Teleport to your set home location |
| `housing list` | List every home you own |
| `sethome` | Set your current room (must be a home you own/rent) as your recall home |
| `housing rent <id>` | Rent a Tier 1 room |
| `housing checkout` | Vacate a Tier 1 rental (deposit refunded) |
| `housing buy [<type> <lot_id>]` | View Tier 3 lots, or purchase (`small`/`standard`/`large`) |
| `housing shopfront [<type> <lot_id>]` | View Tier 4 lots, or purchase (`stall`/`shop`/`trading_house`) |
| `housing sell [confirm]` | Sell your Tier 3 residence or Tier 4 shopfront (50% refund) |
| `housing storage` | List home storage contents |
| `housing store <item>` | Move an item into storage |
| `housing retrieve <item>` | Move an item out of storage |
| `housing trophy <item>` / `untrophy <item>` / `trophies` | Mount, un-mount, or list wall trophies |
| `housing guest add / remove / list <player>` | Manage guest access |
| `housing name <text>` | Rename your room (free first time, 1,000 cr after) |
| `housing describe` | Open the room description editor |
| `housing visit <player>` | Head toward a player's public shopfront |
| `housing intrusions` | Review break-in attempts logged against your home |
| `+home prestige [buy]` | View or upgrade your home's cosmetic prestige tier |
| `lockpick` (alias: `pick`) | Attempt to pick a housing door |
| `forcedoor` (aliases: `breakin`, `force door`) | Attempt to force a housing door (lawless zones only) |
| `steal <item>` (aliases: `pilfer`, `swipe`) | Attempt to steal a mounted trophy |
| `faction hq [locations / purchase <type> <lot> / sell]` | Org-leader HQ management (Tier 5, treasury-funded) |

---

*See also: [Player Cities](#/guide/player-cities), [Economy](#/guide/economy), [Security Zones](#/guide/security-zones), [Player Shops & Trading](#/guide/player-shops), [Organizations & Factions](#/guide/organizations-factions).*

*End of Guide #13 — Housing*
