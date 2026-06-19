---
key: sell
title: Sell — Liquidate Gear and Cargo
category: "Commands: Economy"
summary: Sell your equipped weapon, a carried item, or cargo to an NPC vendor or vendor droid.
aliases: []
see_also: [buy, trade, +shop, +inv, +credits, trading]
tags: [economy, shop, vendor, command]
access_level: 0
examples:
  - cmd: "sell"
    description: "Sell your equipped weapon to the nearest NPC vendor for 25-50% market value."
  - cmd: "sell medpac"
    description: "Sell a carried item (medpac) by name."
  - cmd: "sell cargo spice 3"
    description: "Sell 3 tons of spice from your ship's hold."
  - cmd: "sell medpac to Dex's Droid Shop"
    description: "Sell an item to a player vendor droid buy-order."
---

Sell gear or cargo for credits. NPC vendors buy common goods at
25-50% of their base value.

SELL EQUIPPED WEAPON

  sell               — sell your currently-equipped weapon (no arg)
  sell weapon        — alias for bare sell
  sell equipped      — alias for bare sell

  Bare `sell` offloads whatever is in your weapon slot. The credits
  appear immediately; the item is removed from your slot.

SELL A CARRIED ITEM

  sell <item name>   — liquidate a carried inventory item by name

  Use partial names: `sell medpac` finds "Medpac" in your pack.
  Crafted items (quality > Avail-1) are refused by NPC vendors — list
  those on a vendor droid shop instead.

SELL CARGO

  sell cargo <good> <tons>          — sell from your ship's hold
  sell cargo <good> <tons> to here  — sell at current planet

  See `+help trading` for cargo profit mechanics.

SELL TO A VENDOR DROID (buy-order)

  sell <item> to <shop name>    — fulfill a player shop's buy order

  Player shops may post buy-orders for specific items. This path
  pays at the shop's posted buy-price, which can exceed NPC rates.

NOTES

  To move credits between players, use `trade`, not `sell`.
  Crafted gear is better sold via your own vendor droid (`+shop`).

CHEAT SHEET

  sell                      — sell equipped weapon
  sell <item>               — sell carried item
  sell cargo <good> <tons>  — sell from ship hold
  sell <item> to <shop>     — vendor droid buy-order
