---
key: +armor
title: +Armor — Armor Reference
category: "Commands: Gear"
summary: List all armor with energy/physical protection, DEX penalty, and cost.
aliases: [armor, armorlist]
see_also: [+weapons, +inv, +shop, +soak, wear]
tags: [armor, gear, protection, reference, command]
access_level: 0
examples:
  - cmd: "+armor"
    description: "Show full armor list with protection values."
  - cmd: "armor"
    description: "Alias — same as +armor."
---

Display all armor types in the game — energy and physical
protection ratings, Dexterity penalty, and cost.

SYNTAX

  +armor
  armor
  armorlist

OUTPUT COLUMNS

  Armor       Name of the armor.
  Energy      Dice reduction to energy weapon damage (e.g. +1D).
  Physical    Dice reduction to physical damage.
  DEX Pen     Dexterity penalty imposed by the armor (--  = none).
  Cost        Price in credits at NPC vendors.

WORN ARMOR

  The bottom of the list shows the armor you are currently wearing.

HOW ARMOR WORKS (WEG D6)

  When you are hit, armor adds its protection value to your Strength
  roll to resist damage. Energy weapons check the Energy column;
  physical attacks (slugs, melee) check Physical. Both types of
  protection stack with your Strength dice.

  Heavier armor imposes a DEX penalty — your Dexterity attribute is
  reduced by that amount for all actions, including dodge and agility
  rolls.

EQUIPPING ARMOR

  wear <name>     Put on a piece of armor from your inventory.
  unequip armor   Remove worn armor (goes back to carried inventory).
  +inv            Check what you currently have equipped.

SEE ALSO

  +weapons   List all weapons.
  +soak      Pre-declare CP to spend resisting damage in combat.
  +inv       View equipped gear.
  wear       Equip armor from inventory.

EXAMPLES

  +armor
  → Full armor list. Currently worn armor shown at the bottom.

CHEAT SHEET
  +armor / armor / armorlist   = armor reference list
