---
key: +shipyard
title: Shipyard — Kuat Drive Yards Ship Brokerage
category: "Commands: Ships"
summary: Browse and purchase civilian starships at the Kuat Drive Yards brokerage. +shipyard lists the available hulls and prices; +shipyard buy <hull> [name] completes the purchase.
aliases: [shipyard, "+broker", "+buyship"]
see_also: [+ship, +spacedock, +pilot, +bridge, +shipcrew, +sensors]
tags: [ships, economy, purchase, command]
access_level: 0
examples:
  - cmd: "+shipyard"
    description: "Browse the civilian ship catalog and see current prices."
  - cmd: "+shipyard buy yt_1300"
    description: "Purchase a YT-1300 freighter with the default name."
  - cmd: "+shipyard buy ghtroc My Ship"
    description: "Purchase a Ghtroc 720 freighter and name it 'My Ship'."
---

Browse and buy a starship at the Kuat Drive Yards civilian brokerage.
Available at KDY showrooms on Kuat; all hulls are Clone Wars-era civilian
market ships — no military procurement here.

TWO STEPS

  +shipyard                        Browse the catalog; see what you can afford
  +shipyard buy <hull> [name]      Purchase a hull; optional name follows the key

USAGE

  +shipyard
      Shows the civilian catalog with hull keys, names, class, and price.
      Hulls you can afford display in green; those out of reach in red.
      Also shows your current credit balance.

  +shipyard buy <hull> [name]
      Buys the named hull. The hull argument can be the registry key
      (e.g. yt_1300) or a partial name match (e.g. 'ghtroc' or 'consular').
      The optional name lets you christen the ship on purchase; if omitted
      the hull's default name is used. Name can be changed later with
      'shipname' once aboard.

CIVILIAN CATALOG (Clone Wars era)

  z_95            Z-95 Headhunter        Light fighter
  ghtroc_720      Ghtroc 720             Light freighter
  yt_1300         YT-1300 Transport      Light freighter
  firespray       Firespray-31           Patrol/pursuit craft
  yt_2400         YT-2400 Transport      Freighter
  consular_cruiser  Consular-class       Diplomatic cruiser (whale tier)

Prices are pulled live from the ship registry; what you see in the catalog
is what you pay.

REQUIREMENTS

  - You must be at a Kuat Drive Yards brokerage location to BUY
    (Kuat Deporin Shipyards, Kuat Ileu Shipyards, or KDY Ring Commercial)
  - You can browse the catalog (+shipyard alone) from anywhere
  - Enough credits for the hull price
  - You may own at most 8 ships (hard cap to limit landing-pad sprawl)

DELIVERY

Ships are delivered to the Kuat landing pad. After purchase:
  1. Travel to the Kuat landing pad
  2. `board <ship name>` to step aboard
  3. Explore your bridge

The disembark exit takes you back to the pad. Boarding is via name,
not a room exit, so multiple ships sharing the pad don't collide.

MILITARY SHIPS

Military hulls (ARC-170, LAAT, V-19, Eta-2, CIS droid fighters) require
faction membership and rank. They are not on the civilian market here.

CREDITS HANDLING

Credits are debited at purchase via the ledger chokepoint. If anything
downstream fails (delivery room unavailable, registry error) you are
automatically refunded — the brokerage never keeps your credits on a
failed delivery.

EXAMPLES

  (At the KDY brokerage showroom)
  +shipyard
  → Kuat Drive Yards — Ship Brokerage (civilian listings)
      z_95            Z-95 Headhunter     Light fighter       8,000 cr
      ghtroc_720      Ghtroc 720          Light freighter    40,000 cr
      ...
      Your credits: 95,000 cr
      Buy with:  +shipyard buy <hull> [name]

  +shipyard buy yt_1300 Millennium Hawk
  → Purchase complete — Millennium Hawk (YT-1300 Transport) is yours for
    120,000 cr. Balance: -25,000 cr... (if short, errors out cleanly)

  (Not at the brokerage)
  +shipyard
  → Shows catalog with note: "Travel to a Kuat Drive Yards brokerage to purchase."

CHEAT SHEET
  +shipyard              = browse catalog
  +shipyard buy <hull>   = buy with default name
  +shipyard buy <hull> <name> = buy and name your ship
  aliases: shipyard / +broker / +buyship
