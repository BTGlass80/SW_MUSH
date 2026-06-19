---
key: buy
title: Buy — Purchase Weapons, Items, and Cargo
category: "Commands: Economy"
summary: Buy a weapon or item at a commissary, from a vendor droid, or cargo from the market.
aliases: [purchase]
see_also: [sell, +shop, +inv, +weapons, +credits, trading]
tags: [economy, shop, vendor, command]
access_level: 0
examples:
  - cmd: "buy blaster pistol"
    description: "Buy a DL-44 Blaster Pistol at the local commissary."
  - cmd: "buy cargo spice 5"
    description: "Buy 5 tons of spice from the planetary market."
  - cmd: "buy medpac from Dex's Droid Shop"
    description: "Buy a medpac from a specific vendor droid shop."
---

Buy a weapon, item, or trade goods. Three purchase modes exist
depending on what and where you are buying.

COMMISSARY / OPEN MARKET

  buy <item name>    — purchase a common item at market price
  purchase <name>    — alias for buy

  Only Availability-1 common items (blasters, basic armor, medpacs)
  are on the open market. Rare or crafted gear requires a player
  shop, loot, or the crafting system.

  Type `weapons` to list purchasable weapons.
  Type `market` to browse tradeable goods.

VENDOR DROIDS (player shops)

  buy <item> from <shop name>    — buy from a specific vendor droid

  Player-run shops carry a broader inventory at player-set prices.
  Use `+shop` to browse shops in the current area.

CARGO (trading)

  buy cargo <good> <tons>    — buy trade goods for resale

  Cargo is purchased at the current planet's market price and fills
  your ship's hold. Sell it at another planet for profit.

  See `+help trading` for the cargo trade system.

NOTES

  Credits are deducted immediately. Purchased items go straight to
  your inventory (check with `+inv`). There are no refunds — use
  `sell <item>` to recoup partial value from unwanted gear.

CHEAT SHEET

  buy <name>                 — commissary / open market
  buy <item> from <shop>     — vendor droid
  buy cargo <good> <tons>    — trading cargo
