---
key: +home
title: Home — Player Residences, Storage, Shopfronts
category: "Commands: Economy"
summary: All housing verbs under +home/<switch>. View your residence, rent a new home, manage storage, install trophies, open a shopfront, or grant guests access. Includes forwarding to HousingCommand's positional subcommands.
aliases: [home, myroom, homelocation, sethome]
see_also: [housing, shopfront, storage, trophy, residence]
tags: [economy, housing, shopfront, command]
access_level: 0
examples:
  - cmd: "+home"
    description: "View your home/residence status (default)."
  - cmd: "home"
    description: "Same as +home (bare alias preserved — S58 moved this from HousingCommand)."
  - cmd: "myroom"
    description: "Another bare alias — view your residence."
  - cmd: "housing"
    description: "Bare alias still works; routes to HousingCommand directly."
  - cmd: "+home/sethome"
    description: "Set the current room as your home location. Must be an owned residence."
  - cmd: "sethome"
    description: "Same as +home/sethome (bare alias preserved)."
  - cmd: "+home/rent 5"
    description: "Rent residence location #5 (forwarded to HousingCommand positional parser)."
  - cmd: "+home/storage"
    description: "Open your residence storage (deposit/withdraw items)."
  - cmd: "+home/name My Place"
    description: "Rename your residence."
  - cmd: "+home/describe A cozy hovel with two moons visible."
    description: "Set your residence's description."
  - cmd: "+home/trophy blaster"
    description: "Install a trophy — decorative item showing off an achievement."
  - cmd: "+home/buy 5"
    description: "Buy residence #5 outright (Tier 2+ only; rent-to-own path)."
  - cmd: "+home/shopfront"
    description: "Convert your residence to a shopfront (requires Tier 3+)."
  - cmd: "+home/guest add Jex"
    description: "Grant Jex persistent guest access to your residence."
  - cmd: "+home/visit Jex"
    description: "Teleport to Jex's residence (requires guest access from Jex)."
  - cmd: "@housing"
    description: "Admin-only — housing system admin commands (NATIVE @-PREFIX, not under +home)."
---

All housing verbs live under +home/<switch>. Bare forms (home,
myroom, sethome) still work as aliases.

See `+help housing` for the conceptual overview of residence tiers
and the shopfront economy. This page is the command reference.

SWITCH REFERENCE
  /view       View your residence (default — bare +home)
  /sethome    Set current room as your home

  POSITIONAL SUBCOMMANDS (forwarded to HousingCommand):
  /rent <id>      Rent a residence
  /checkout       Vacate your current rental
  /storage        Open residence storage
  /store / /retrieve  Add/remove items from storage
  /name <text>    Rename your residence
  /describe <t>   Set description
  /trophy <item>  Install a trophy
  /untrophy <#>   Remove a trophy
  /trophies       List your installed trophies
  /buy <id>       Purchase a residence outright
  /shopfront      Convert to a shopfront (Tier 3+)
  /sell           Sell your shopfront
  /guest          Manage guest access (add/remove/list)
  /intrusions     See who's visited while you were away
  /visit <player> Teleport to another player's residence

RESIDENCE TIERS

  Tier 1  Small  (bedroom + closet — 5 storage slots, no shopfront)
  Tier 2  Medium (living space — 15 slots, trophy display)
  Tier 3  Large  (separate rooms — 30 slots, shopfront allowed)
  Tier 4  Estate (compound — 60 slots, multi-room, shopfront + NPC quarters)

Higher tiers cost more credits up-front AND more weekly upkeep.
Running out of credits on upkeep day evicts you (items go to a
lost-and-found, recoverable within 7 days).

/sethome

Sets the current room as your home location — the place `+home/visit`
would bring friends to (and where you respawn after death in some
configurations). The room must be an owned residence; you can't
set home to a cantina or public space.

THE UMBRELLA FORWARDING PATTERN (S58)

HousingCommand uses positional-argument subcommands (rent, storage,
trophy, shopfront, etc.) rather than switch syntax. The +home
umbrella recognizes all HousingCommand subcommands as switches and
forwards them — so `+home/rent 5` reaches HousingCommand as
`housing rent 5` and works identically.

This forwarding is transparent — you can type either form:
  +home/rent 5         (canonical)
  housing rent 5       (legacy bare form)
Both reach the same code.

ADMIN COMMANDS — NATIVE @-PREFIX

@housing (admin) stays at its native @-prefix form. Folding it
into +home/admin would shadow its own ctx.switches handling.

CHEAT SHEET
  +home              = view residence (also: home, myroom, housing)
  +home/sethome      = set home (also: sethome)
  +home/rent <id>    = rent residence
  +home/storage      = storage access
  +home/trophy <i>   = install trophy
  +home/shopfront    = enable shopfront
  +home/visit <p>    = visit another residence
  @housing           = admin (NATIVE @-PREFIX)

Sources: Residence system is game-original (inspired by SWG
houses + EVE station/alliance structures). Storage and shopfront
mechanics tie into the economy — see `+help shops` and
`+help economy`.
