---
key: get
title: Get / Drop — Items in Parsec
category: "Commands: Gear"
summary: Parsec has no ground items. Explains how to get items and what to do instead of dropping them.
aliases: [take, pickup, grab, drop, discard]
see_also: [buy, loot, +craft, sell, give, +inv]
tags: [gear, items, command]
access_level: 0
examples:
  - cmd: "buy blaster pistol"
    description: "How you actually acquire items: purchase at a commissary."
  - cmd: "loot trooper"
    description: "Take items from a fallen enemy after combat."
  - cmd: "sell medpac"
    description: "Instead of dropping: sell unwanted items for credits."
---

Parsec does not use a ground-item or drop system. Items do not
sit on floors and you cannot pick them up from rooms.

HOW TO GET ITEMS

  buy <name>           — commissary or market (common gear)
  buy <item> from <shop>  — vendor droid (player shops)
  loot <name>          — take from a defeated enemy's corpse
  +craft               — craft items using the crafting system
  give / hand          — receive an item another player hands to you
  +mission / chains    — quest rewards often grant specific items

INSTEAD OF DROP

  sell <item>          — convert gear to credits at an NPC vendor
  unequip              — put away equipped weapon (stays in inventory)
  remove armor         — take off armor (stays in inventory)
  give <item> to <player>  — hand it to someone else

WHY NO GROUND ITEMS

  A ground-item system would require persistent room objects and
  a full pickup/drop economy. Parsec routes item acquisition through
  vendors, loot, crafting, and quests — these are the intended
  sources and sinks.

CHEAT SHEET

  buy / loot / +craft      — acquire items
  sell / unequip / give    — dispose of items
