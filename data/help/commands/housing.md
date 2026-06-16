---
key: housing
title: Housing — Home Management
category: "Commands: Housing"
summary: Comprehensive housing system. Rent or buy a room, manage storage, set descriptions and trophies, run a shopfront, and control guest access. Also aliased as `+home`.
aliases: [+home, home]
see_also: [+shop, +city, market, sethome]
tags: [housing, economy, social, command]
access_level: 0
examples:
  - cmd: "housing"
    description: "Show your current housing status and available rental locations nearby."
  - cmd: "housing rent 3"
    description: "Rent the Tier 1 room with ID #3 at your current location."
  - cmd: "housing store medpac"
    description: "Move a medpac from your inventory into your home storage."
  - cmd: "housing guest add Han"
    description: "Add player Han to your home's guest access list."
---

The housing system lets you rent or purchase a private room,
store items, decorate with trophies, and optionally run a
player shopfront.

BASIC STATUS

  housing       Show your housing status, any active rental or
                owned room, and available locations nearby.

RENTING (TIER 1)

  housing rent <id>    Rent a Tier 1 room at a nearby rental
                       hub. Weekly rent deducted automatically.
  housing checkout     Vacate your current rental; deposit
                       returned to your account.

PURCHASING (TIER 2+)

  housing buy <id>     Purchase a Tier 2–4 residence outright.
                       Ownership is permanent (no weekly rent).
  housing sell         List your owned home for sale.
  housing sell confirm Confirm the sale.

STORAGE

  housing storage        List the contents of your home storage.
  housing store <item>   Move an item from your inventory into
                          home storage.
  housing retrieve <item> Move an item from storage to inventory.

DESCRIPTIONS AND TROPHIES

  housing name <text>       Rename your room.
  housing describe <text>   Set your room's description.
  housing trophy <item>     Mount an item as a trophy decoration
                             (max 10 trophies).
  housing untrophy <item>   Remove a mounted trophy.
  housing trophies          List all mounted trophies.

GUEST ACCESS

  housing guest add <player>    Add a player to guest access
                                 (they can enter when you're
                                 offline).
  housing guest remove <player> Remove guest access.
  housing guest list            Show current guest list.

SHOPFRONTS (TIER 3+)

Tier 3 and higher residences can be converted to player
shopfronts — a storefront that other players can browse and
buy from even when you are offline.

  housing shopfront <type> <id>  Convert room to shopfront
                                  of the given shop type.
  housing visit <player>         Teleport to another player's
                                  shopfront.
  housing sell [confirm]         Sell your shopfront/home.

TIER OVERVIEW

  Tier 1   Rental room — weekly credits, no ownership.
  Tier 2   Owned apartment — one-time purchase, personal use.
  Tier 3   Owned unit — shopfront-eligible.
  Tier 4   Estate — premium; custom descriptions, extra storage.

ALIASES

`housing` and `+home` are identical. The bare `home` command
(no arguments) teleports you to your set home location.

EXAMPLES

  housing
  → You rent Room 7A at Coruscant Lower Ring Hub. Rent due in 3d.

  housing store lightsaber
  → Lightsaber moved to home storage.

  housing guest add Ahsoka
  → Ahsoka added to your guest list.

  housing visit Fenn
  → You step through the entrance to Fenn's Arms Emporium.

CHEAT SHEET
  housing / +home              = show status
  housing rent <id>            = rent Tier 1 room
  housing checkout             = vacate rental
  housing buy <id>             = purchase Tier 2+ room
  housing store/retrieve <item> = home storage
  housing trophies             = list mounted trophies
  housing trophy/untrophy <i>  = mount/remove trophy
  housing guest add/remove/list = guest access
  housing visit <player>       = go to player shopfront
