---
key: +commissary
title: +Commissary — Faction Gear Requisition
category: "Commands: Economy"
summary: Requisition faction-specific gear using your rank and credits, or sell commissary items back.
aliases: [commissary, "+requisition", requisition]
see_also: [+shop, +inv, +finances, +faction]
tags: [commissary, faction, gear, equipment, buy, command]
access_level: 0
examples:
  - cmd: "+commissary"
    description: "Browse available faction gear for your rank."
  - cmd: "+commissary buy dc15_rifle"
    description: "Purchase a DC-15 Rifle from the commissary."
  - cmd: "+commissary sell dc15_pistol"
    description: "Sell a commissary item back for partial credit."
---

Requisition faction-specific gear available to your rank, or sell
faction items back. The catalog adjusts to show only items your
rank qualifies for.

SYNTAX

  +commissary                  Browse available faction gear
  +commissary buy <key>        Purchase an item (debits credits)
  +commissary sell <key>       Sell a commissary item back

HOW IT WORKS

  The commissary is faction-specific. Items listed depend on your
  faction and your rank within it. Higher rank unlocks heavier
  weapons, specialized armor, and field equipment.

  Items you buy via the commissary can be sold back, but typically
  for less than the purchase price.

  Use the `key` shown in parentheses in the catalog listing when
  buying or selling.

EXAMPLES

  +commissary
  → Shows the catalog with item names, costs, and keys.

  +commissary buy dc15_rifle
  → Purchases the DC-15 Rifle if your rank qualifies and you
    have sufficient credits.

  +commissary sell dc15_pistol
  → Sells back your DC-15 Pistol for partial credit.

SEE ALSO

  +shop      General shops (not faction-locked).
  +inv       View your current inventory.
  +finances  Check earnings, expenses, and pay schedule.
  +faction   View your faction standing and rank.

CHEAT SHEET
  +commissary              browse catalog
  +commissary buy <key>    requisition item
  +commissary sell <key>   sell item back
